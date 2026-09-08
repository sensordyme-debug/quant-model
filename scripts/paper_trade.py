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

REPO = Path(__file__).resolve().parents[1]
LIVE = REPO / "live"
LOG_DIR = LIVE / "log"
STATE_DIR = LIVE / "state"
APPROVAL = LIVE / "APPROVED_PAPER.md"
HALT = LIVE / "HALT"
CHAMPION = REPO / "research" / "champion.json"

IB_SYMBOL_MAP = {"BRK-B": "BRK B", "BRKB": "BRK B", "BF-B": "BF B"}
MIN_NOTIONAL = 200.0          # skip trades smaller than this many dollars
FILL_WAIT_SECONDS = 90


def log_event(kind: str, **fields) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    rec = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "event": kind, **fields}
    with (LOG_DIR / f"{dt.date.today():%Y-%m-%d}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")


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
    return pd.DataFrame(frames).sort_index()


def load_state():
    p = STATE_DIR / "last_run.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_state(state):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / "last_run.json").write_text(json.dumps(state, indent=2, default=str) + "\n", encoding="utf-8")


class MockAccount:
    account = "DU0000000"
    net_liq = 100_000.0

    def __init__(self):
        self.positions = {}       # symbol -> shares

    def prices(self, symbols, closes):
        return {s: float(closes[s].dropna().iloc[-1]) for s in symbols if s in closes}


def plan_orders(targets, positions, prices, net_liq):
    """Return [(symbol, delta_shares, price, target_shares, current_shares)] for symbols that move."""
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
        if delta != 0 and abs(delta) * px >= MIN_NOTIONAL:
            plan.append((sym, delta, px, target_shares, current))
    return plan


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
    ap.add_argument("--order-type", choices=["MKT", "MOC"], default="MKT")
    ap.add_argument("--dry-run", action="store_true", help="compute and print orders, send nothing")
    ap.add_argument("--mock", action="store_true", help="no IB connection; fake paper account for pipeline tests")
    ap.add_argument("--check", action="store_true", help="connect, print account summary and positions, exit")
    ap.add_argument("--flatten", action="store_true", help="close every position and exit")
    args = ap.parse_args()

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
            for tag in ("TotalCashValue", "BuyingPower", "GrossPositionValue", "AvailableFunds"):
                if tag in summary:
                    print(f"  {tag}: {summary[tag]}")
            ib.disconnect()
            return 0

    # ---- safety gates -----------------------------------------------------------------
    if not account_id.startswith("DU"):
        print(f"REFUSED: account {account_id!r} is not an IBKR paper account (paper ids start with DU)")
        log_event("refused", reason="not_paper_account", account=account_id)
        if ib:
            ib.disconnect()
        return 3

    if HALT.exists() or args.flatten:
        reason = "HALT file present" if HALT.exists() else "--flatten"
        print(f"FLATTEN: {reason}; closing {len(positions)} positions")
        log_event("flatten", reason=reason, positions=positions)
        if not args.dry_run and ib and positions:
            trades = []
            for sym, qty in positions.items():
                if qty == 0:
                    continue
                contract = Stock(IB_SYMBOL_MAP.get(sym, sym), "SMART", "USD")
                ib.qualifyContracts(contract)
                trades.append(ib.placeOrder(contract, MarketOrder("SELL" if qty > 0 else "BUY", abs(qty))))
            ib.sleep(FILL_WAIT_SECONDS)
            for t in trades:
                log_event("fill", symbol=t.contract.symbol, status=t.orderStatus.status,
                          filled=t.orderStatus.filled, avg_price=t.orderStatus.avgFillPrice)
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
    closes = fetch_history_yf(universe) if (args.history == "yfinance" or ib is None) else fetch_history_ib(ib, universe)
    missing = [s for s in universe if s not in closes.columns or closes[s].dropna().empty]
    if missing:
        print(f"warning: no history for {missing}")
    as_of = closes.index[-1]
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
    save_state({**state, "signal": name, "as_of": str(as_of.date()), "targets": targets,
                "ran_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "dry_run": args.dry_run or args.mock})

    if args.dry_run or args.mock:
        print("dry run: no orders sent")
        if ib:
            ib.disconnect()
        return 0
    if not APPROVAL.exists():
        print(f"REFUSED: {APPROVAL} is missing; create it to allow paper orders")
        log_event("refused", reason="no_approval_file")
        ib.disconnect()
        return 3

    # ---- execution --------------------------------------------------------------------
    trades = []
    for sym, delta, px, tgt, cur in plan:
        if delta is None:
            continue
        contract = Stock(IB_SYMBOL_MAP.get(sym, sym), "SMART", "USD")
        ib.qualifyContracts(contract)
        action = "BUY" if delta > 0 else "SELL"
        order = MarketOrder(action, abs(delta)) if args.order_type == "MKT" else Order(action=action, totalQuantity=abs(delta), orderType="MOC", tif="DAY")
        trade = ib.placeOrder(contract, order)
        trades.append(trade)
        log_event("order", symbol=sym, action=action, qty=abs(delta), type=args.order_type, ref_price=px)
        print(f"sent {action} {abs(delta)} {sym} ({args.order_type})")
    ib.sleep(FILL_WAIT_SECONDS if args.order_type == "MKT" else 5)
    for t in trades:
        st = t.orderStatus
        log_event("fill", symbol=t.contract.symbol, status=st.status, filled=st.filled, remaining=st.remaining, avg_price=st.avgFillPrice)
        print(f"{t.contract.symbol}: {st.status} filled {st.filled} @ {st.avgFillPrice}")
    ib.disconnect()
    return 0


if __name__ == "__main__":
    sys.exit(main())
