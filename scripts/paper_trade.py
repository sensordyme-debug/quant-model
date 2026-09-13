#!/usr/bin/env python
"""IBKR paper-trading runner for the champion strategy (ib_async, IB Gateway on 127.0.0.1:4002).

Safety gates, all enforced before any order is sent:
  * live/APPROVED_PAPER.md must exist (the human's go-ahead for paper orders)
  * the connected account id must start with "DU" (IBKR paper accounts)
  * live/HALT must not exist; if it does, every position is flattened and the run stops
  * --dry-run computes and prints the orders and stops

Usage:
  python scripts/paper_trade.py --check                  # connect, print account and positions
  python scripts/paper_trade.py --mock --dry-run          # whole pipeline, no IB, no orders
  python scripts/paper_trade.py --dry-run                 # real paper account, no orders
  python scripts/paper_trade.py                           # rebalance the paper account
  python scripts/paper_trade.py --flatten                 # close every position now
  python scripts/paper_trade.py --signal s1_momo          # override the champion
  python scripts/paper_trade.py --order-type MOO          # PRE-OPEN: market-on-open orders

Order types (S-23). The default MKT is what the 15:45 ET scheduled task sends and nothing
about it changed. MOO exists so the runner can be moved to a pre-open slot and finally trade
the backtest's own convention: LEAN decides on the last complete close and fills at the NEXT
session's open, which is exactly what a pre-open run with market-on-open orders does, while
the 15:45 path fills a whole session later (research/BLOCKERS.md, S-19/S-22: ~1.9 CAR points,
+1.85 on an honestly-costed book). IBKR expresses market-on-open as orderType MKT with
tif OPG and rejects it outside 04:00-09:28 ET, so --order-type MOO refuses to run outside
that window rather than having the exchange refuse the orders one at a time. Moving the
scheduled task is the human's (AGENTS.md); this flag is the half the loop can supply.

The signal module contract is algorithms/SIGNAL_CONTRACT.md. Fills and decisions are logged to
live/log/YYYY-MM-DD.jsonl; the last run's targets go to live/state/last_run.json.
Exit codes: 0 ok, 1 error, 2 halted, 3 refused by a safety gate.
"""
import argparse
import datetime as dt
import importlib.util
import json
import math
import sys
from pathlib import Path

from quant_brain.brokers.ibkr import IBKRAdapter
from quant_brain.core.execution import (
    OrderIntent,
    OrderType,
    RoutedExecutor,
    Side,
)
from quant_brain.core.risk import RiskChain

#: Empty preserves the wire exactly: this runner never set an orderRef, and
#: ib_async defaults it to "". Named so the choice is visible rather than
#: accidental, and so a future change to it is one edit.
ORDER_REF = ""


REPO = Path(__file__).resolve().parents[1]
# Run as `python scripts/paper_trade.py`, sys.path[0] is scripts/, so the repo root is not
# importable and `import quant_brain` would fail. Added here rather than at the call site so
# there is one place that knows it.
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
LIVE = REPO / "live"
LOG_DIR = LIVE / "log"
STATE_DIR = LIVE / "state"
APPROVAL = LIVE / "APPROVED_PAPER.md"
HALT = LIVE / "HALT"
ALERTS = LIVE / "alerts.json"          # {"channel": "telegram", "target": "<chat id>"}; optional
CHAMPION = REPO / "research" / "champion.json"

IB_SYMBOL_MAP = {"BRK-B": "BRK B", "BRKB": "BRK B", "BF-B": "BF B"}

#: No-trade band, as a fraction of net liquidation. This must track
#: `algorithms/s1_momo/main.py:self.min_order_value`, because the backtest bands orders at
#: a fraction of *equity* and the runner has to reproduce the backtest's order list for
#: the I-1 pre-deploy comparison to mean anything.
#:
#: It did not, until 2026-09-09. The runner banded at a flat $200 while the backtest bands
#: at 1% of equity - $1,000 on the $100k paper account, and $24,000 by the end of the
#: backtest's compounding. `scripts/compare_orders.py` measured the gap on LEAN's own bars:
#: the runner would have placed **9,196 orders against the backtest's 4,653**, agreeing on
#: only 36.6% of decision dates, and every single disagreement was the runner sending a
#: small drift adjustment the backtest bands out. Those are exactly the return-neutral
#: orders S-13 measured (63% of the champion's order count buy nothing) - so the old
#: constant would have paid a real spread, live, on thousands of orders the research says
#: are worthless.
MIN_ORDER_VALUE = 0.01

#: Absolute floor under the fractional band, so a small account does not send $20 orders.
#: At the paper account's size the fraction dominates ($1,000 > $200) and the runner
#: matches LEAN exactly; this only binds below ~$20k of net liquidation.
MIN_NOTIONAL = 200.0
FILL_WAIT_SECONDS = 90

#: IBKR accepts an opening-auction order (tif OPG) only between 04:00 and 09:28 ET. Outside
#: that window every order would be rejected individually, which would leave the book half
#: rebalanced, so --order-type MOO checks the clock once, up front, and refuses.
MOO_WINDOW_ET = (dt.time(4, 0), dt.time(9, 28))


def log_event(kind: str, **fields) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    rec = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "event": kind, **fields}
    with (LOG_DIR / f"{dt.date.today():%Y-%m-%d}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def record_alert(text: str, delivered: bool, error: str = "") -> None:
    """P-1: the durable half of the alert path - `live/log/alerts-<date>.jsonl`.

    The chat push failed silently on 2026-09-09 (missing Telegram token) and the only trace was a
    `notify_failed` line inside that day's own trading log. Every alert now also lands in one file
    the daily review reads, with `delivered` saying whether it actually left the machine.
    """
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        rec = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
               "event": "alert", "source": "paper", "text": text[:3500],
               "delivered": delivered, "error": error}
        with (LOG_DIR / f"alerts-{dt.date.today():%Y-%m-%d}.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")
    except Exception:  # noqa: BLE001 - a broken alert path must never stop trading
        pass


def notify(text: str) -> None:
    """Push a short message through OpenClaw's chat channel (Telegram etc.) if live/alerts.json
    exists, and always leave a durable record either way. Never raises: a broken alert path must
    not stop or alter trading."""
    delivered, err = False, ""
    try:
        import os
        import shutil
        import subprocess
        if not ALERTS.exists():
            err = "no live/alerts.json"
        else:
            cfg = json.loads(ALERTS.read_text(encoding="utf-8"))
            channel, target = cfg.get("channel"), str(cfg.get("target", ""))
            if not channel or not target:
                err = "alerts.json has no channel/target"
            else:
                node_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "nodejs"
                entry = node_dir / "node_modules" / "openclaw" / "dist" / "index.js"
                if (node_dir / "node.exe").exists() and entry.exists():
                    cmd = [str(node_dir / "node.exe"), str(entry)]
                elif shutil.which("openclaw"):
                    cmd = [shutil.which("openclaw")]
                else:
                    cmd = None
                    err = "openclaw CLI not found"
                if cmd:
                    cmd += ["message", "send", "--channel", channel, "--target", target,
                            "--message", text[:3500]]
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
                    delivered = res.returncode == 0
                    if not delivered:
                        err = (res.stderr or res.stdout)[-400:]
    except Exception as exc:  # noqa: BLE001
        err = str(exc)[:400]
    record_alert(text, delivered, err)
    if not delivered:
        log_event("notify_failed", error=err)


class DemoSignal:
    """Buy-and-hold SPY. Only for pipeline tests."""
    UNIVERSE = ["SPY"]
    PARAMS = {}

    @staticmethod
    def target_weights(closes, as_of=None, params=None, state=None):
        return {"SPY": 1.0}


def load_signal(name: str):
    if name == "demo":
        return DemoSignal
    folder = REPO / "algorithms" / name
    path = next((folder / f for f in ("signal.py", "signals.py") if (folder / f).exists()), None)
    if path is None:
        sys.exit(f"no signal.py or signals.py in {folder} (see algorithms/SIGNAL_CONTRACT.md)")
    spec = importlib.util.spec_from_file_location(f"signal_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod            # dataclasses and annotations need the module registered
    # A signal may import helpers that sit beside it (s1_momo/universe.py, D-3). LEAN puts
    # the algorithm folder on PYTHONPATH; loading by file path does not, so do it here or
    # those imports fail at exec time with the runner otherwise perfectly configured.
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
    spec.loader.exec_module(mod)
    fn = getattr(mod, "target_weights", None) or getattr(mod, "compute_weights", None)
    universe = next((getattr(mod, a) for a in ("UNIVERSE", "TRADED_UNIVERSE", "ALL_TICKERS") if hasattr(mod, a)), None)
    if fn is None or not universe:
        sys.exit(f"{path} must define a universe list (UNIVERSE or TRADED_UNIVERSE) and target_weights(...)")
    mod.target_weights = fn
    mod.UNIVERSE = list(universe)
    return mod


def call_signal(sig, closes, as_of, state):
    """Call target_weights with whichever of (closes, as_of, params, equity_curve, state) it accepts.

    Accepts a plain {symbol: weight} dict or a (weights, diagnostics) tuple; diagnostics may
    carry a 'state' dict that is persisted and fed back next run.
    """
    import inspect
    fn = sig.target_weights
    try:
        names = set(inspect.signature(fn).parameters)
    except (TypeError, ValueError):
        names = {"closes"}
    kwargs = {}
    if "as_of" in names:
        kwargs["as_of"] = as_of
    if "params" in names:
        kwargs["params"] = getattr(sig, "PARAMS", None)
    if "equity_curve" in names:
        kwargs["equity_curve"] = list(state.get("equity_curve", []))
    if "state" in names:
        kwargs["state"] = dict(state.get("signal_state", {}))
    result = fn(closes, **kwargs)
    diag = {}
    if isinstance(result, tuple):
        result, diag = result[0], (result[1] if len(result) > 1 and isinstance(result[1], dict) else {})
    weights = {str(k): float(v) for k, v in dict(result).items() if abs(float(v)) > 0}
    if isinstance(diag.get("state"), dict):
        state["signal_state"] = diag["state"]
    return weights, diag


def champion_name() -> str | None:
    if CHAMPION.exists():
        return json.loads(CHAMPION.read_text(encoding="utf-8")).get("algorithm")
    return None


def fetch_history_yf(symbols, period="2y"):
    import yfinance as yf
    import pandas as pd
    data = yf.download(list(symbols), period=period, auto_adjust=True, progress=False, group_by="column")
    closes = data["Close"] if isinstance(data.columns, pd.MultiIndex) else data[["Close"]].rename(columns={"Close": symbols[0]})
    closes = closes.dropna(how="all")
    # drop today's unfinished session so the signal only sees completed closes
    today = pd.Timestamp(dt.date.today())
    closes = closes[closes.index < today]
    return closes


def fetch_history_ib(ib, symbols, days=500):
    """Daily closes from IB. C-5c: today's unfinished bar is dropped, as yfinance's is.

    `reqHistoricalData` with `endDateTime=""` returns a bar for the session in progress, so
    at the deployed 15:45 ET task time the last row of this frame was a *mid-session print*
    carrying today's date. Nothing downstream could tell it from a close: the signal ranked
    and sized on it, and `data_faults` passed it because its staleness clause tested only
    `day < prev`. The two history sources sat on one line of `main()` with opposite
    conventions, which is the only reason the deployed path (yfinance, no arguments) was
    never wrong. Both ends are now closed - here at the source, and symmetrically in
    `data_faults` for any source this runner grows later.
    """
    from ib_async import Stock, util
    import pandas as pd
    frames = {}
    for sym in symbols:
        contract = Stock(IB_SYMBOL_MAP.get(sym, sym), "SMART", "USD")
        bars = ib.reqHistoricalData(contract, endDateTime="", durationStr=f"{days} D", barSizeSetting="1 day",
                                    whatToShow="ADJUSTED_LAST", useRTH=True, formatDate=1)
        if bars:
            df = util.df(bars).set_index("date")["close"]
            df.index = pd.to_datetime(df.index)
            frames[sym] = df
        ib.sleep(0.3)
    closes = pd.DataFrame(frames).sort_index()
    # the same filter `fetch_history_yf` applies, stated once per source rather than shared,
    # because IB stamps `date` as a plain date and yfinance as a tz-naive Timestamp and the
    # comparison must be made against each source's own index type.
    if len(closes):
        today = pd.Timestamp(dt.date.today())
        closes = closes[closes.index < today]
    return closes


def load_state():
    """Read the real account's state. Every scope reads this file; only PAPER writes it.

    A dry run SHOULD read live state - it is simulating what would happen from where the
    account actually is. What it must not do is write back, which is what `save_state`'s
    scope routing now prevents (AUD-04).
    """
    p = STATE_DIR / "last_run.json"
    state = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    # The file on disk today was written by simulated runs before the scope routing above
    # existed: equity 100000, equity_curve [100000 x4], "dry_run": true - all MockAccount.
    # Warn rather than refuse: the champion ships with the drawdown breaker off, so this is
    # currently inert, and refusing here would stop the 15:45 rebalance over state it does
    # not read. Made loud so it is fixed deliberately rather than discovered by a
    # liquidation the first time the breaker is switched on.
    try:
        from quant_brain.core.state import is_contaminated
        if is_contaminated(state):
            msg = (f"{p} was written by a simulated run (dry_run/mock). Its equity and "
                   f"equity_curve are not the account's. Safe while the drawdown breaker is "
                   f"off; delete the file to let the next real run rebuild it.")
            print(f"WARNING: {msg}")
            log_event("state_contaminated", path=str(p), detail=msg)
    except Exception:  # noqa: BLE001 - a diagnostic must never stop the runner
        pass
    return state


def previous_session(today: "dt.date") -> "dt.date | None":
    """The last completed US equity session strictly before `today`, or None if unknown.

    `fetch_history_yf` deliberately drops today's unfinished bar, so on any run this is the
    date the signal's last row is *supposed* to carry. A weekend, a holiday and an early
    close all differ here and none of them is `today - 1`, which is why this reads the
    exchange calendar rather than subtracting a day. Returns None - and therefore raises no
    fault - when the calendar cannot cover the date: a coverage gap must never be the reason
    the account stops trading (the C-3 rule, from a unit test that read free memory).

    `check_covered` is called explicitly because `trading_days` does NOT enforce the
    calendar's own coverage contract: past `coverage_end` (2027-12-31 today) it keeps
    answering from the weekday rule, so it would return a holiday as "the previous session"
    and this gate would refuse to trade over a date the calendar never verified. Asking the
    one entry point that raises is what makes the fallback reachable.
    """
    try:
        from quant_brain.markets.equity_us import CALENDAR
        start = today - dt.timedelta(days=12)
        CALENDAR.check_covered(start)
        CALENDAR.check_covered(today)
        days = CALENDAR.trading_days(start, today - dt.timedelta(days=1))
        return days[-1] if days else None
    except Exception:  # noqa: BLE001
        return None


def data_faults(closes, universe, as_of, prev_session=None) -> list[str]:
    """AUD-13 / S-37: every way the history frame can be wrong before it becomes an order.

    The runner used to `print("warning: no history for ...")` and carry on. It cannot: the
    signal treats a defective frame as information, not as an error, and each of the three
    shapes below produces a *different* wrong book with nothing in the log to distinguish it
    from a decision.

      * a missing or all-NaN universe column -> `target_weights` runs
        `dropna(axis=1, how="all")` first, so the name is simply not in the ranking. If the
        missing one is `REGIME_TICKER`, `risk_on` returns `"SPY missing"` and the whole book
        is liquidated under a reason that reads like a risk decision.
      * a NaN in the last row -> `.ffill()` carries yesterday's close forward, so the name is
        ranked on a stale price AND sized at it (`closes[s].dropna().iloc[-1]` below).
      * an `as_of` older than the previous session -> the same staleness over every name at
        once, which no per-column check can see.
      * an `as_of` NEWER than the previous session -> the last row is a session still in
        progress, so every name is ranked and sized on a mid-session print as if it were a
        close (C-5c). S-37 left this side out on the argument that it is "a different defect"
        belonging to the source, and then never fixed the source: `fetch_history_ib` applied
        no date filter at all while `fetch_history_yf` dropped today, so the hole was held
        shut by nothing but the deployed task passing no arguments. It is reported here under
        its own message rather than as staleness, which is what that argument was protecting.

    Only names that have already printed a close are required to have one, so a name added to
    the universe before its own inception cannot stop the account trading. On the reference
    daily store that narrowing is free - the audit's predicate as filed fires on 0 of 3,690
    sessions - and it is kept because the store the runner actually reads is yfinance, not
    this one. Held-but-untargeted names are deliberately NOT checked: they have no price only
    when they are already being reported as stuck by `plan_orders`, and refusing to trade over
    one would block the sale this runner exists to make.

    Returns a list of human-readable faults; empty means the frame is usable.
    """
    import pandas as pd

    faults = []
    absent = [s for s in universe if s not in closes.columns]
    if absent:
        faults.append(f"no column for {absent}")
    empty = [s for s in universe if s in closes.columns and closes[s].dropna().empty]
    if empty:
        faults.append(f"column is entirely NaN for {empty}")
    if len(closes):
        last = closes.iloc[-1]
        stale = [s for s in universe
                 if s in closes.columns and s not in empty and pd.isna(last[s])]
        if stale:
            faults.append(f"no close in the last row ({closes.index[-1].date()}) for {stale}")
    else:
        faults.append("history frame is empty")
    if prev_session is not None and as_of is not None:
        # Both sides are normalized to `datetime.date`: `previous_session` returns one and the
        # frame's index gives a `Timestamp`, and comparing the two raises rather than
        # returning False. A TypeError here would crash the runner inside the gate that exists
        # to stop it trading safely, which is the worst place in the file to have one.
        day = as_of.date() if hasattr(as_of, "date") else as_of
        prev = prev_session.date() if hasattr(prev_session, "date") else prev_session
        if day < prev:
            faults.append(f"as_of {day} is older than the previous session {prev}")
        elif day > prev:
            faults.append(f"as_of {day} is newer than the previous session {prev} - the last "
                          f"row is a session still in progress, not a close")
    return faults


def save_state(state, *, scope=None):
    """Persist run state into the scope that produced it.

    AUD-04: `--mock` and `--dry-run` used to write this exact file, so seven simulated runs
    put `MockAccount.net_liq = 100_000` into the live equity curve and drove `held_age` to
    15. It was harmless only because the champion ships with the drawdown breaker off -
    switching it on reads a ~90% drawdown against a fabricated `equity_high` and liquidates
    a real book.

    The fix is structural rather than a conditional: the scope selects a `StateStore`, and a
    simulated store has no reachable path to the live file. `base=STATE_DIR` keeps the
    existing test isolation working, because `tests/conftest.py` redirects `STATE_DIR` into
    tmp_path and every scope root is derived from it.
    """
    from quant_brain.core.state import StateScope, StateStore

    store = StateStore.open(scope or StateScope.PAPER, base=STATE_DIR)
    store.write_json("last_run.json", state)


class MockAccount:
    account = "DU0000000"
    net_liq = 100_000.0

    def __init__(self):
        self.positions = {}       # symbol -> shares

    def prices(self, symbols, closes):
        return {s: float(closes[s].dropna().iloc[-1]) for s in symbols if s in closes}


def plan_orders(targets, positions, prices, net_liq, min_order_value=None):
    """Return [(symbol, delta_shares, price, target_shares, current_shares)] for symbols that move.

    The band is `max(MIN_NOTIONAL, min_order_value * net_liq)`, which is the same rule
    `algorithms/s1_momo/main.py:submit_targets` applies, so the plan this returns is the
    plan the backtest would have produced from the same targets and holdings.
    `scripts/compare_orders.py` asserts that equivalence on every date of the champion's
    sample and is the pre-deploy gate for backlog I-1.
    """
    band = MIN_ORDER_VALUE if min_order_value is None else min_order_value
    threshold = max(MIN_NOTIONAL, band * net_liq)
    plan = []
    symbols = sorted(set(targets) | set(positions))
    for sym in symbols:
        w = float(targets.get(sym, 0.0))
        px = prices.get(sym)
        if px is None or px <= 0:
            plan.append((sym, None, px, None, positions.get(sym, 0)))
            continue
        target_shares = int(math.copysign(math.floor(abs(w) * net_liq / px), w)) if w else 0
        current = int(positions.get(sym, 0))
        delta = target_shares - current
        if delta != 0 and abs(delta) * max(px, 0.01) >= threshold:
            plan.append((sym, delta, px, target_shares, current))
    return plan


def now_et() -> dt.datetime:
    from zoneinfo import ZoneInfo
    return dt.datetime.now(ZoneInfo("America/New_York"))


def moo_window_ok(when: dt.datetime | None = None) -> bool:
    """True when IBKR would accept a tif=OPG order (04:00-09:28 ET on a weekday)."""
    when = when or now_et()
    lo, hi = MOO_WINDOW_ET
    return when.weekday() < 5 and lo <= when.time() <= hi


#: The runner's --order-type spellings, as venue-independent intents.
ORDER_TYPES = {
    "MKT": OrderType.MARKET,
    "MOC": OrderType.MARKET_ON_CLOSE,
    "MOO": OrderType.MARKET_ON_OPEN,
}


def intent_for(order_type: str, symbol: str, delta: int) -> OrderIntent:
    """One OrderIntent per supported --order-type. No broker vocabulary above this line."""
    if order_type not in ORDER_TYPES:
        raise ValueError(f"unsupported order type {order_type!r}")
    return OrderIntent(symbol=symbol, side=Side.of(delta), quantity=abs(delta),
                       order_type=ORDER_TYPES[order_type], tag=ORDER_REF)


def build_order(order_type: str, action: str, qty: int):
    """Kept as a shim over the adapter's construction, deliberately.

    Its tests pin the exact IBKR objects for MKT, MOC and MOO. Delegating rather than
    deleting means those tests now certify the adapter's output, which makes them an
    equivalence proof between the inline construction this runner used to do and the
    construction it does now - the check that the migration changed nothing on the wire.
    """
    from quant_brain.brokers.ibkr import build_ib_order
    side = Side.BUY if action == "BUY" else Side.SELL
    return build_ib_order(OrderIntent(symbol="", side=side, quantity=qty,
                                      order_type=ORDER_TYPES[order_type]
                                      if order_type in ORDER_TYPES else _reject(order_type)))


def _reject(order_type: str):
    raise ValueError(f"unsupported order type {order_type!r}")


#: Hard ceiling on initial margin the runner will ever ask a paper account to post, as a
#: fraction of net liquidation. The signal's own budget is 0.75 (backlog S-6); this is an
#: independent backstop, so a signal bug that asked for size could not silently place it.
MAX_MARGIN_USED = 1.0


def margin_used(targets, sig) -> float:
    """Initial margin the target book consumes per dollar of equity.

    Uses the signal module's own MARGIN_REQ table when it publishes one (S-1 does), and
    falls back to Reg-T 50% otherwise. Returning gross when nothing is known would be
    wrong in the *unsafe* direction, so the fallback is the conservative 100%.
    """
    table = getattr(sig, "MARGIN_REQ", {})
    default = getattr(sig, "BASE_MARGIN_REQ", 0.5) if table else 1.0
    return sum(abs(w) * table.get(sym, default) for sym, w in targets.items())


def print_plan(plan, net_liq, targets, sig=None):
    gross = sum(abs(v) for v in targets.values())
    used = margin_used(targets, sig) if sig is not None else float("nan")
    print(f"net liquidation {net_liq:,.2f}   target gross exposure {gross:.2f}x   "
          f"initial margin {used:.2f} of {MAX_MARGIN_USED:.2f}")
    if used > MAX_MARGIN_USED:
        sys.exit(f"ABORT: target book needs {used:.2f}x initial margin, ceiling is "
                 f"{MAX_MARGIN_USED:.2f}x. No orders sent.")
    if not plan:
        print("no orders needed")
        return
    print(f"{'symbol':<8}{'current':>10}{'target':>10}{'delta':>10}{'price':>12}{'notional':>14}")
    for sym, delta, px, tgt, cur in plan:
        if delta is None:
            print(f"{sym:<8}{cur:>10}{'?':>10}{'no price':>10}")
            continue
        print(f"{sym:<8}{cur:>10}{tgt:>10}{delta:>+10}{px:>12.2f}{delta * px:>14,.2f}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--signal", help="algorithm name under algorithms/ (default: research/champion.json)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=4002, help="4002 IB Gateway paper, 7497 TWS paper")
    ap.add_argument("--client-id", type=int, default=17)
    ap.add_argument("--history", choices=["yfinance", "ib"], default="yfinance",
                    help="history source for the signal (yfinance matches the backtest data)")
    ap.add_argument("--order-type", choices=["MKT", "MOC", "MOO"], default="MKT",
                    help="MKT fills now (the deployed 15:45 path), MOC at the closing auction, "
                         "MOO at the next opening auction (pre-open runs only, 04:00-09:28 ET)")
    ap.add_argument("--ignore-clock", action="store_true",
                    help="skip the MOO submission-window check (testing only; IBKR still enforces it)")
    ap.add_argument("--dry-run", action="store_true", help="compute and print orders, send nothing")
    ap.add_argument("--mock", action="store_true", help="no IB connection; fake paper account for pipeline tests")
    ap.add_argument("--check", action="store_true", help="connect, print account summary and positions, exit")
    ap.add_argument("--flatten", action="store_true", help="close every position and exit")
    args = ap.parse_args()

    # ---- clock gate (before the connection, so a mis-scheduled run costs nothing) -------
    if args.order_type == "MOO" and not (args.ignore_clock or args.dry_run or args.mock):
        et = now_et()
        if not moo_window_ok(et):
            lo, hi = MOO_WINDOW_ET
            msg = (f"REFUSED: --order-type MOO needs a weekday between {lo:%H:%M} and {hi:%H:%M} ET "
                   f"(IBKR rejects tif=OPG outside it); it is {et:%a %H:%M} ET. No orders sent.")
            print(msg)
            log_event("refused", reason="moo_window", now_et=et.isoformat(timespec="seconds"))
            notify("paper_trade " + msg)
            return 3

    # ---- connection -------------------------------------------------------------------
    ib = None
    if args.mock:
        acct = MockAccount()
        account_id, net_liq, positions = acct.account, acct.net_liq, dict(acct.positions)
        print(f"[mock] account {account_id} net liquidation {net_liq:,.2f}")
    else:
        from ib_async import IB, Stock, MarketOrder, Order
        ib = IB()
        try:
            ib.connect(args.host, args.port, clientId=args.client_id, timeout=20)
        except Exception as exc:  # noqa: BLE001
            print(f"cannot connect to IB Gateway at {args.host}:{args.port}: {exc}")
            print("Is IB Gateway running and logged in, with API enabled on that port?")
            log_event("connect_failed", host=args.host, port=args.port, error=str(exc))
            notify(f"paper_trade: cannot connect to IB Gateway {args.host}:{args.port}. Book unchanged. "
                   "Is Gateway logged in (weekly IB Key) and the paper disclaimer accepted?")
            return 1
        accounts = ib.managedAccounts()
        account_id = accounts[0] if accounts else ""
        summary = {row.tag: row.value for row in ib.accountSummary(account_id) if row.currency in ("USD", "BASE", "")}
        net_liq = float(summary.get("NetLiquidation", 0) or 0)
        positions = {}
        for pos in ib.positions(account_id):
            sym = pos.contract.symbol.replace(" ", "-")
            positions[sym] = positions.get(sym, 0) + int(pos.position)
        print(f"account {account_id}  net liquidation {net_liq:,.2f}  positions {positions or 'none'}")
        if args.check:
            for tag in ("TotalCashValue", "BuyingPower", "GrossPositionValue", "AvailableFunds", "UnrealizedPnL", "RealizedPnL"):
                if tag in summary:
                    print(f"  {tag}: {summary[tag]}")
            items = [p for p in ib.portfolio(account_id) if p.position]
            if items:
                print(f"\n{'symbol':<8}{'shares':>10}{'avg cost':>12}{'price':>12}{'mkt value':>16}{'unreal P&L':>14}")
                for p in sorted(items, key=lambda x: -abs(x.marketValue)):
                    print(f"{p.contract.symbol:<8}{p.position:>10g}{p.averageCost:>12.2f}{p.marketPrice:>12.2f}"
                          f"{p.marketValue:>16,.2f}{p.unrealizedPNL:>14,.2f}")
                print(f"{'total':<8}{'':>10}{'':>12}{'':>12}{sum(p.marketValue for p in items):>16,.2f}"
                      f"{sum(p.unrealizedPNL for p in items):>14,.2f}")
            today_log = LOG_DIR / f"{dt.date.today():%Y-%m-%d}.jsonl"
            if today_log.exists():
                fills = [json.loads(l) for l in today_log.read_text(encoding="utf-8").splitlines() if '"event": "fill"' in l]
                if fills:
                    print("\ntoday's fills:")
                    for f_ in fills:
                        print(f"  {f_.get('symbol'):<8}{f_.get('status'):<12}filled {f_.get('filled')} @ {f_.get('avg_price')}")
            ib.disconnect()
            return 0

    # ---- safety gates -----------------------------------------------------------------
    if not account_id.startswith("DU"):
        print(f"REFUSED: account {account_id!r} is not an IBKR paper account (paper ids start with DU)")
        log_event("refused", reason="not_paper_account", account=account_id)
        notify(f"paper_trade REFUSED: connected account {account_id!r} is not a paper account. No orders.")
        if ib:
            ib.disconnect()
        return 3

    if HALT.exists() or args.flatten:
        reason = "HALT file present" if HALT.exists() else "--flatten"
        print(f"FLATTEN: {reason}; closing {len(positions)} positions")
        log_event("flatten", reason=reason, positions=positions)
        if not args.dry_run and ib and positions:
            held = {s_: q_ for s_, q_ in positions.items() if q_}
            contracts = {s_: Stock(IB_SYMBOL_MAP.get(s_, s_), "SMART", "USD") for s_ in held}
            if contracts:
                ib.qualifyContracts(*contracts.values())
            # FLATTEN intents: the risk chain cannot reduce or refuse these, which is the
            # whole point of the emergency path (AUD-06 / AUD-08).
            routed = RoutedExecutor(RiskChain(),
                                    IBKRAdapter(ib, contracts, order_ref=ORDER_REF),
                                    on_event=lambda ev, **kw: log_event(ev, **kw))
            trades = [a.handle for a in routed.flatten(held, tag=ORDER_REF) if a.accepted]
            ib.sleep(FILL_WAIT_SECONDS)
            for t in trades:
                log_event("fill", symbol=t.contract.symbol, status=t.orderStatus.status,
                          filled=t.orderStatus.filled, avg_price=t.orderStatus.avgFillPrice)
            notify(f"paper_trade FLATTEN ({reason}): " + ", ".join(
                f"{t.contract.symbol} {t.orderStatus.status} {t.orderStatus.filled}@{t.orderStatus.avgFillPrice}" for t in trades))
        else:
            notify(f"paper_trade FLATTEN requested ({reason}); dry run or nothing to close. Positions: {positions or 'none'}")
        if ib:
            ib.disconnect()
        return 2

    # ---- signal -----------------------------------------------------------------------
    name = args.signal or champion_name()
    if not name:
        print("REFUSED: no champion in research/champion.json and no --signal given")
        log_event("refused", reason="no_champion")
        if ib:
            ib.disconnect()
        return 3
    sig = load_signal(name)
    universe = list(sig.UNIVERSE)
    # Sleeve isolation: the account is shared with the intraday sleeve (scripts/intraday_trader.py),
    # which trades a disjoint universe and is flat by 15:40 ET. Only positions in THAT sleeve's
    # universe are left alone. Everything else is this runner's responsibility, including names the
    # champion used to trade and no longer targets: on 2026-09-11 S-18 retired the 3x proxies, TQQQ
    # dropped out of the signal universe, and the old rule ("outside the universe = foreign") left
    # 3,227 TQQQ sitting in the account after the rebalance. Such names now get a zero target.
    try:
        sys.path.insert(0, str(REPO / "scripts"))
        from intraday_common import UNIVERSE as _INTRADAY_UNIVERSE
    except Exception:  # noqa: BLE001
        _INTRADAY_UNIVERSE = []
    foreign = {s: q for s, q in positions.items() if s in _INTRADAY_UNIVERSE}
    if foreign:
        print(f"leaving positions outside this signal's universe alone: {foreign}")
        log_event("foreign_positions_ignored", positions=foreign)
        positions = {s: q for s, q in positions.items() if s in universe}
    # History for the signal universe PLUS any held name outside it, so a position the champion no
    # longer targets still has a price and can be sold to its zero target.
    fetch_syms = list(universe) + [s for s in positions if s not in universe]
    closes = fetch_history_yf(fetch_syms) if (args.history == "yfinance" or ib is None) else fetch_history_ib(ib, fetch_syms)
    as_of = closes.index[-1] if len(closes) else None
    # AUD-13 / S-37: the data-completeness gate, BEFORE the signal is called, so a defective
    # frame can never become an order. Refusing holds yesterday's book for one session, which
    # S-37 clause 5 measured against the alternative (the spurious flatten the defect causes)
    # on the same corrupted sessions; the numbers are in research/journal_daily.md.
    faults = data_faults(closes, universe, as_of, previous_session(dt.date.today()))
    if faults:
        detail = "; ".join(faults)
        print(f"REFUSED: history is not usable: {detail}")
        log_event("refused", reason="data_incomplete", faults=faults,
                  as_of=str(as_of.date()) if as_of is not None else None, source=args.history)
        notify(f"paper_trade REFUSED: {args.history} history is not usable, no orders sent and the "
               f"book is unchanged. {detail}")
        if ib:
            ib.disconnect()
        return 3
    state = load_state()
    curve = [float(x) for x in state.get("equity_curve", [])]
    if not curve or str(state.get("as_of")) != str(as_of.date()):
        curve.append(float(net_liq))           # one equity point per trading day
    state.update({"equity": net_liq, "equity_high": max(curve), "equity_curve": curve[-2000:]})
    targets, diag = call_signal(sig, closes, as_of, state)
    prices = {s: float(closes[s].dropna().iloc[-1]) for s in set(targets) | set(positions) if s in closes.columns and not closes[s].dropna().empty}
    plan = plan_orders(targets, positions, prices, net_liq)
    print(f"signal {name} as of {as_of.date()}  targets {targets}")
    if diag:
        shown = {k: v for k, v in diag.items() if k != "state"}
        print(f"diagnostics {json.dumps(shown, default=str)[:600]}")
    print_plan(plan, net_liq, targets, sig)
    log_event("plan", signal=name, as_of=str(as_of.date()), targets=targets, net_liq=net_liq, diagnostics=diag,
              orders=[{"symbol": s, "delta": d, "price": p} for s, d, p, _, _ in plan if d is not None])
    # AUD-04: the scope is derived from the run's own flags, so a simulation physically
    # cannot reach live/state/last_run.json. `for_run` resolves any flag combination to the
    # least privileged scope, so a future flag cannot fail open to PAPER.
    from quant_brain.core.state import StateScope
    save_state({**state, "signal": name, "as_of": str(as_of.date()), "targets": targets,
                "ran_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "dry_run": args.dry_run or args.mock},
               scope=StateScope.for_run(mock=args.mock, dry_run=args.dry_run))

    mode = "MOCK" if args.mock else ("DRY RUN" if args.dry_run else "LIVE PAPER")
    order_lines = [f"{'BUY' if d > 0 else 'SELL'} {abs(d)} {s} @~{p:.2f}" for s, d, p, _, _ in plan if d is not None]
    plan_text = (f"paper_trade [{mode}] {account_id} NLV {net_liq:,.0f} signal {name} as of {as_of.date()} "
                 f"({diag.get('reason', '')}) targets {targets or 'flat'}; orders: "
                 + ("; ".join(order_lines) if order_lines else "none"))
    if args.dry_run or args.mock:
        print("dry run: no orders sent")
        notify(plan_text)
        if ib:
            ib.disconnect()
        return 0
    if not APPROVAL.exists():
        print(f"REFUSED: {APPROVAL} is missing; create it to allow paper orders")
        log_event("refused", reason="no_approval_file")
        notify("paper_trade REFUSED: live/APPROVED_PAPER.md is missing, no orders sent. " + plan_text)
        ib.disconnect()
        return 3

    # ---- execution --------------------------------------------------------------------
    # Signal -> OrderIntent -> risk -> adapter -> broker. The contracts are qualified up
    # front because qualification is a connection-time concern, not a per-order one.
    live = [(sym, delta, px) for sym, delta, px, _tgt, _cur in plan if delta]
    contracts = {sym: Stock(IB_SYMBOL_MAP.get(sym, sym), "SMART", "USD")
                 for sym, _d, _p in live}
    if contracts:
        ib.qualifyContracts(*contracts.values())
    adapter = IBKRAdapter(ib, contracts, order_ref=ORDER_REF)
    routed = RoutedExecutor(RiskChain(), adapter,
                            on_event=lambda ev, **kw: log_event(ev, **kw))
    ref_price = {sym: px for sym, _d, px in live}
    acks = routed.submit([intent_for(args.order_type, sym, delta) for sym, delta, _p in live])
    trades = []
    for ack in acks:
        sym = ack.intent.symbol
        action = "BUY" if ack.intent.side is Side.BUY else "SELL"
        qty = int(abs(ack.intent.quantity))
        if not ack.accepted:
            log_event("order_rejected", symbol=sym, action=action, qty=qty,
                      type=args.order_type, reason=ack.reason)
            print(f"REJECTED {action} {qty} {sym}: {ack.reason}")
            continue
        trades.append(ack.handle)
        log_event("order", symbol=sym, action=action, qty=qty, type=args.order_type,
                  ref_price=ref_price.get(sym))
        print(f"sent {action} {qty} {sym} ({args.order_type})")
    # MKT is expected to fill inside the wait; MOC and MOO fill at an auction that has not
    # happened yet, so the run only confirms that the exchange accepted them.
    ib.sleep(FILL_WAIT_SECONDS if args.order_type == "MKT" else 5)
    queued = args.order_type == "MOO"
    fill_lines = []
    for t in trades:
        st = t.orderStatus
        log_event("fill", symbol=t.contract.symbol, status=st.status, filled=st.filled, remaining=st.remaining,
                  avg_price=st.avgFillPrice, type=args.order_type)
        print(f"{t.contract.symbol}: {st.status} filled {st.filled} @ {st.avgFillPrice}")
        fill_lines.append(f"{t.contract.symbol} {st.status} {st.filled:g}@{st.avgFillPrice:.2f}" + (f" (rem {st.remaining:g})" if st.remaining else ""))
    label = "queued for the open" if queued else "fills"
    notify(plan_text + f" | {label}: " + ("; ".join(fill_lines) if fill_lines else "none"))
    ib.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
