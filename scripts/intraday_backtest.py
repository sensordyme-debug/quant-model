#!/usr/bin/env python
"""Minute-bar backtester for the intraday sleeve (the research harness for algorithms/intraday).

    python scripts/intraday_backtest.py                       # active sleeve, all stored sessions
    python scripts/intraday_backtest.py --strategy orb        # one sub-strategy alone
    python scripts/intraday_backtest.py --start 2026-08-01 --end 2026-09-09
    python scripts/intraday_backtest.py --params '{"per_symbol":0.2}' --tag "wider cap"
    python scripts/intraday_backtest.py --split 2026-08-15    # in-sample / out-of-sample report

Mechanics (identical to scripts/intraday_trader.py):
  * decisions on the close of each completed 1-minute bar, fills at the next bar's open plus
    intraday_common.SLIPPAGE_BPS and IBKR commission;
  * targets -> whole shares, changed only when the delta exceeds MIN_CHANGE of equity;
  * per-symbol and gross caps come from the strategy; the framework adds the daily loss limit
    (flatten and stop for the day) and the end-of-day flatten at FLATTEN_MINUTE;
  * equity is marked to the bar close; daily P&L is booked on the session's last bar.
AUD-21 (2026-09-12): a pending order whose symbol prints no bar at the fill minute is now held on
the wire until it does (`--legacy-fills` restores the old decision-close fill), sizing nets what is
already pending exactly as the live trader does, `RISK["nav_frac"]` lets the loss limit be measured
against account NAV rather than sleeve equity, drawdown is reported on the intraday path as well as
the end-of-day marks, and turnover is a fraction of average rather than starting equity.
AUD-07 (2026-09-13): every session is trimmed to ITS OWN calendar close on load, so the 21 early
closes in the Alpaca store no longer carry their 13:00-15:59 post-market prints as RTH bars
(`--no-calendar-trim` restores the old store view), and the forced end-of-day fill - a position
the framework failed to flatten, dumped into whatever bar the store ends on - is counted on every
run instead of only when A-11's participation cap is set. `--strict-eod` turns that count into a
non-zero exit.
Records a line in research/experiments.jsonl with algorithm "intraday/<strategy>".
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import intraday_common  # noqa: E402
from intraday_common import (DAILY_LOSS_LIMIT, FLATTEN_MINUTE, GROSS_HARD_CAP, MIN_CHANGE,  # noqa: E402
                             PER_SYMBOL_HARD_CAP, REPO, SLIPPAGE_BPS, UNIVERSE, commission,
                             load_universe, sessions, share_scale, slippage, volume_limits)

sys.path.insert(0, str(REPO / "algorithms" / "intraday"))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from base import features  # noqa: E402


def validate_bars(bars: dict, strict: bool = True) -> None:
    """Refuse to research on a store that fails validation. Part 17 / AUD-13.

    Runs before any session is simulated. A FAIL - a zero or NaN price, a bar on a market
    holiday, a duplicate timestamp, a tz-naive index - stops the run, because a result
    computed on a broken store is worse than no result: it enters the ledger and gets
    compared against. WARNs (zero-volume bars, intraday gaps, after-hours rows on an early
    close) are printed and the run continues, since the caller may legitimately accept them.
    """
    try:
        from quant_brain.core.dataquality import Severity, validate_store
        from quant_brain.markets.equity_us import CALENDAR
    except Exception as exc:  # noqa: BLE001 - never let the validator be the outage
        print(f"[data] validation unavailable ({type(exc).__name__}); continuing unvalidated")
        return
    rep = validate_store(bars, CALENDAR)
    for f in rep.of(Severity.WARN):
        print(f"[data] {f.line().strip()}")
    if rep.failed:
        for f in rep.of(Severity.FAIL)[:10]:
            print(f"[data] {f.line().strip()}")
        if strict:
            raise SystemExit(f"[data] REFUSED: {rep.summary()}")
    print(f"[data] {rep.summary()}")


def flatten_minute_for(day) -> int:
    """The bar index at which to start flattening on THIS session. AUD-07.

    Must agree with `intraday_trader.flatten_minute_for`, or the harness and the live path
    disagree on exactly the days the live path used to break. `RISK["flatten_minute"]` is
    still honoured when a research run overrides it deliberately; only the SHIPPED value is
    made calendar-aware, because an override is a stated experiment and must not be silently
    moved.
    """
    if RISK["flatten_minute"] != SHIPPED_RISK["flatten_minute"]:
        return int(RISK["flatten_minute"])
    try:
        from quant_brain.markets.equity_us import CALENDAR
        m = CALENDAR.minutes_before_close(day, 390 - FLATTEN_MINUTE)
    except Exception:  # noqa: BLE001
        return int(RISK["flatten_minute"])
    return int(RISK["flatten_minute"]) if m is None else int(m)

EXPERIMENTS = REPO / "research" / "experiments.jsonl"

#: Framework risk limits for a research run. Defaults are exactly the shared constants the live
#: trader uses; --risk overrides them *for the backtest only* so A-7 can price them. Shipping a
#: change means editing scripts/intraday_common.py and replaying a session (AGENTS.md rule a).
#: `part_cap` is A-11's participation cap and is 0.0 = OFF in the shipped constants, i.e. the live
#: trader has no such cap and this default reproduces every prior A-track run bit for bit.
#: `nav_frac` is AUD-21: the LIVE loss limit is -2.5% of the ACCOUNT NAV while the harness's P&L
#: is the sleeve's, so at the deployed equity_frac of 0.25 the live limit is 4x looser than the
#: one this harness enforced. Setting `nav_frac` to the deployed equity_frac makes the two the
#: same rule; 1.0 (the default) is the pre-2026-09-12 behaviour and keeps every earlier row exact.
RISK = {"daily_loss_limit": DAILY_LOSS_LIMIT, "per_symbol_hard_cap": PER_SYMBOL_HARD_CAP,
        "gross_hard_cap": GROSS_HARD_CAP, "min_change": MIN_CHANGE, "flatten_minute": FLATTEN_MINUTE,
        "part_cap": 0.0, "nav_frac": 1.0}
SHIPPED_RISK = dict(RISK)

#: AUD-21: how a pending order is filled when the symbol has no bar at the fill minute.
#: "next_bar" (the default from 2026-09-12) carries the order until the symbol actually prints and
#: fills it at that bar's open - the live trader's behaviour, since an order on the wire stays on
#: the wire. "decision_close" is what the harness did before: it filled at the DECISION bar's own
#: close, a zero-latency fill at a price that minute never traded, and silently DROPPED the order
#: when the symbol had not printed at all yet that session. 5.5% of the Alpaca store's minute cells
#: and 0.6% of the IBKR store's are missing, so this is not a corner case. Kept only to reproduce
#: rows already in research/experiments.jsonl (`--legacy-fills`).
FILL_MODEL = "next_bar"


def set_slippage(bps: float | None) -> float | None:
    """Charge a different slippage in the BACKTEST ONLY (A-5 prices the cost model this way).

    `intraday_common.slippage()` reads the module global at call time, so rebinding it here also
    changes what `Book.fill` charges. Shipping a change means editing scripts/intraday_common.py,
    which the live trader imports, and replaying a session (AGENTS.md rule a).
    """
    if bps is None or float(bps) == SLIPPAGE_BPS:
        return None
    intraday_common.SLIPPAGE_BPS = float(bps)
    return float(bps)


def warn_loss_limit_base() -> str:
    """AUD-21: say out loud when the run's loss limit is tighter than the deployed sleeve's.

    `DAILY_LOSS_LIMIT` is 2.5% of ACCOUNT NAV (intraday_trader.py:596), and the sleeve is only
    `equity_frac` of that account, so the live rule lets the sleeve lose 2.5%/`equity_frac` of its
    OWN equity. A harness run at the default `nav_frac` of 1.0 stops the book 1/`equity_frac`
    earlier than the live trader would - A-13 measured 30 such stop-outs in 674 sessions, worth
    +$205/day and 5.6 points of drawdown. Silence here is how that went unnoticed for two days.
    """
    frac = RISK["nav_frac"]
    try:
        deployed = float(json.loads((REPO / "live" / "intraday_config.json")
                                    .read_text(encoding="utf-8"))["equity_frac"])
    except Exception:  # noqa: BLE001 - a research run must not depend on the live config
        return ""
    if abs(frac - deployed) < 1e-9 or deployed >= 1.0:
        return ""
    msg = (f"AUD-21 note: loss limit charged against sleeve equity / {frac:g}; the deployed sleeve "
           f"runs at equity_frac {deployed:g}, so live is {frac / deployed:.1f}x looser. "
           f"Pass --nav-frac {deployed:g} to model the live rule.")
    print(msg)
    return msg


def set_risk(overrides: dict | None) -> dict:
    """Apply research overrides to RISK; returns the ones that actually differ from the shipped constants."""
    changed = {}
    for k, v in (overrides or {}).items():
        if k not in RISK:
            sys.exit(f"unknown risk key {k!r}; known: {sorted(RISK)}")
        RISK[k] = float(v)
        if RISK[k] != SHIPPED_RISK[k]:
            changed[k] = RISK[k]
    return changed


def load_strategy(name: str):
    path = REPO / "algorithms" / "intraday" / name / "signal.py"
    if not path.exists():
        sys.exit(f"no strategy at {path}")
    spec = importlib.util.spec_from_file_location(f"intraday_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class Book:
    """Positions, cash and marks for one sleeve. Shared with the live trader's replay mode."""

    def __init__(self, equity: float):
        self.cash = equity
        self.pos: dict[str, int] = {}
        self.trades: list[dict] = []
        self.costs = 0.0

    def value(self, prices: dict[str, float]) -> float:
        return self.cash + sum(q * prices.get(s, 0.0) for s, q in self.pos.items())

    def fill(self, when, sym: str, delta: int, price: float, reason: str = ""):
        if delta == 0:
            return
        px = price * (1 + math.copysign(1, delta) * 0)  # slippage charged explicitly below
        # share_scale is 1.0 on the raw IBKR store; on the split-adjusted Alpaca store it converts
        # the adjusted share count back to the shares IBKR would really have charged for.
        cost = commission(delta, px, share_scale(sym, when.date())) + slippage(delta, px)
        self.cash -= delta * px + cost
        self.costs += cost
        self.pos[sym] = self.pos.get(sym, 0) + delta
        # on an adjusted store the share count is a float multiple of the split factor, so an
        # exact zero can leave a ~1e-16 relative residue; treat that as flat.
        if self.pos[sym] == 0 or abs(self.pos[sym]) < 1e-9 * abs(delta):
            del self.pos[sym]
        self.trades.append({"t": when, "sym": sym, "qty": delta, "px": px, "cost": cost, "why": reason})


def targets_to_orders(targets: dict[str, float], book: Book, prices: dict[str, float], equity: float,
                      day: dt.date | None = None, caps: dict[str, float] | None = None,
                      clipped: list | None = None, pending: dict[str, int] | None = None):
    """Same sizing rules as scripts/intraday_trader.py:Trader.targets_to_orders.

    The whole-share floor is applied at the price that was really quoted, not the adjusted one:
    on a split-adjusted store a 2016 share of SOXS is priced in the millions, so flooring the
    adjusted count would silently size every early position to zero. `f` is 1.0 on the raw IBKR
    store, where this reduces to the shipped `floor(w * equity / px)` exactly.

    A-11: when `RISK["part_cap"]` is non-zero, `caps[sym]` is the maximum share count this bar may
    trade (a share of the trailing median volume of the minute the order will fill in). The
    no-trade band is still tested on the *desired* delta - the strategy re-decides every minute, so
    a clipped order is worked over several bars rather than suppressed - and the clip is applied to
    what actually executes. `caps=None` (the default) is the shipped, uncapped behaviour.

    AUD-21/AUD-06: `pending` is what is already on the wire and not yet filled. The live trader
    sizes against `book.pos + pending` (intraday_trader.py:562) so a delta that has been sent but
    not booked is not sent again; under FILL_MODEL "next_bar" an order can now survive more than
    one bar in the harness too, so the harness must net it the same way. `pending=None` is the
    pre-2026-09-12 behaviour, where the dict was cleared every bar and could not survive.
    """
    orders = {}
    cap, gross_cap, min_change = RISK["per_symbol_hard_cap"], RISK["gross_hard_cap"], RISK["min_change"]
    gross = sum(abs(w) for w in targets.values())
    scale = min(1.0, gross_cap / gross) if gross > gross_cap else 1.0
    wire = pending or {}
    for sym in set(targets) | set(book.pos) | set(wire):
        px = prices.get(sym)
        if not px or px <= 0:
            continue
        w = max(-cap, min(cap, float(targets.get(sym, 0.0)) * scale))
        f = share_scale(sym, day) if day is not None else 1.0
        if w:
            real = math.floor(abs(w) * equity / (px * f))       # whole shares at the real price
            tgt = math.copysign(real * f, w)
            tgt = int(tgt) if f == 1.0 else tgt
        else:
            tgt = 0
        cur = book.pos.get(sym, 0) + wire.get(sym, 0)
        delta = tgt - cur
        if delta and (abs(delta) * px >= min_change * equity or tgt == 0):
            if caps is not None:
                lim = caps.get(sym)
                if lim is not None and lim == lim and abs(delta) > lim:  # lim == lim rejects NaN
                    if clipped is not None:
                        clipped.append({"sym": sym, "want": abs(delta), "got": lim, "px": px})
                    delta = math.copysign(math.floor(lim / f) * f, delta)
                    delta = int(delta) if f == 1.0 else delta
                    if not delta:
                        continue
            orders[sym] = delta
    return orders


def run(strategy, bars: dict[str, pd.DataFrame], equity0: float, params: dict | None,
        start: dt.date | None = None, end: dt.date | None = None, verbose: bool = False,
        feats_all: dict | None = None, collect_trades: bool = False):
    feats_all = feats_all if feats_all is not None else {s: features(df) for s, df in bars.items()}
    days = [d for d in sessions(bars) if (start is None or d >= start) and (end is None or d <= end)]
    book = Book(equity0)
    state: dict = {}
    daily = []
    orders_total = 0
    part_cap = RISK["part_cap"]
    # A-11: trailing median volume per (session, minute-of-day), strictly prior sessions only.
    vlim = {s: volume_limits(df) for s, df in bars.items()} if part_cap else {}
    clipped: list = []
    forced_eod = {"orders": 0, "notional": 0.0, "days": set()}
    t0 = time.time()
    for day in days:
        flat_minute = flatten_minute_for(day)
        # per-session slices (positional views for speed)
        fd = {s: f[f["day"] == day] for s, f in feats_all.items()}
        fd = {s: f for s, f in fd.items() if len(f) >= 30}
        if not fd:
            continue
        # union of bar times this session
        times = sorted(set().union(*[set(f.index) for f in fd.values()]))
        # positional cursors
        idx = {s: 0 for s in fd}
        vrow = {s: v.loc[day] for s, v in vlim.items() if day in v.index} if part_cap else None
        eq_open = book.value({s: f["o"].iloc[0] for s, f in fd.items()})
        eq_low = eq_open
        stopped = False
        stop_minute = -1
        pending: dict[str, int] = {}
        for i, t in enumerate(times):
            # advance cursors to bars <= t
            cur_rows = {}
            for s, f in fd.items():
                j = idx[s]
                while j < len(f) and f.index[j] <= t:
                    j += 1
                idx[s] = j
                if j:
                    cur_rows[s] = j
            # 1) fill pending orders at this bar's open
            if pending:
                carried = {}
                for s, delta in pending.items():
                    j = cur_rows.get(s)
                    row = fd[s].iloc[j - 1] if j else None
                    if row is None or row.name != t:
                        # AUD-21: this symbol printed no bar at t. The order is on the wire, so
                        # it stays there until the symbol trades again; the old harness instead
                        # booked it at the DECISION bar's own close (zero latency, a price that
                        # minute never showed) or, when the symbol had not printed at all yet,
                        # dropped it in silence.
                        if FILL_MODEL == "next_bar":
                            carried[s] = delta
                            continue
                        if row is None:
                            continue
                        px = float(row["c"])
                    else:
                        px = float(row["o"])
                    book.fill(t, s, delta, px)
                    orders_total += 1
                pending = carried
            closes = {s: float(fd[s].iloc[j - 1]["c"]) for s, j in cur_rows.items()}
            equity = book.value(closes)
            eq_low = min(eq_low, equity)      # AUD-21: the drawdown path, not just its EOD marks
            minute = int((t.hour - 9) * 60 + t.minute - 30)
            # 2) risk: daily loss limit, end-of-day flatten. AUD-21: the live limit is a fraction
            # of ACCOUNT NAV, which is the sleeve's equity divided by `nav_frac`.
            if not stopped and equity - eq_open <= -RISK["daily_loss_limit"] * eq_open / RISK["nav_frac"]:
                stopped = True
                stop_minute = minute
                if verbose:
                    print(f"{day} {t.time()} daily loss limit hit: {equity - eq_open:,.0f}")
            if stopped or minute >= flat_minute:
                targets = {}
            else:
                view = {s: fd[s].iloc[:j] for s, j in cur_rows.items()}
                targets = strategy.decide(t, view, dict(book.pos), equity, state, params) or {}
            # the order placed now fills at the NEXT bar's open, so it is worked in minute + 1
            caps = ({s: part_cap * float(r.get(minute + 1, float("nan")))
                     for s, r in vrow.items()} if vrow is not None else None)
            if FILL_MODEL == "next_bar":
                new = targets_to_orders(targets, book, closes, equity, day, caps, clipped, pending)
                for s, d in new.items():
                    q = pending.get(s, 0) + d
                    if q:
                        pending[s] = q
                    else:
                        pending.pop(s, None)
            else:
                pending = targets_to_orders(targets, book, closes, equity, day, caps, clipped)
            if minute >= flat_minute and book.pos and not pending:
                pending = {s: -q for s, q in book.pos.items()}
                if caps is not None:   # the flatten is worked too: 22 bars exist between 15:38 and the close
                    for s in list(pending):
                        lim = caps.get(s)
                        if lim is not None and lim == lim and abs(pending[s]) > lim:
                            f_ = share_scale(s, day)
                            q = math.copysign(math.floor(lim / f_) * f_, pending[s])
                            pending[s] = int(q) if f_ == 1.0 else q
                            if not pending[s]:
                                del pending[s]
        # end of session: anything still open is closed at the last bar's close (should be none)
        last_closes = {s: float(f["c"].iloc[-1]) for s, f in fd.items()}
        for s, q in list(book.pos.items()):
            px_eod = last_closes.get(s, closes.get(s, 0.0))
            forced_eod["orders"] += 1
            forced_eod["notional"] += abs(q) * px_eod
            forced_eod["days"].add(day)
            book.fill(times[-1], s, -q, px_eod, "eod")
            orders_total += 1
        eq_close = book.value({})
        daily.append({"day": day, "pnl": eq_close - eq_open, "ret": eq_close / eq_open - 1.0, "equity": eq_close,
                      "low": min(eq_low, eq_close),
                      "trades": sum(1 for tr in book.trades if tr["t"].date() == day), "stopped": stopped,
                      "stop_minute": stop_minute})
    elapsed = time.time() - t0
    s = summarize(daily, book, equity0, elapsed)
    # AUD-07: an "eod" fill is the framework failing to flatten inside the session and dumping the
    # position into the last bar the STORE happens to hold, at a price nothing was worked into.
    # It was counted only when A-11's participation cap was on, so the harness could close a book
    # against a post-market print and say nothing. Reported unconditionally now, per AUD-07's
    # "make the harness count and fail on 'eod' fills"; `--strict-eod` is the failing half.
    s["forced_eod_orders"] = forced_eod["orders"]
    s["forced_eod_notional"] = forced_eod["notional"]
    s["forced_eod_days"] = sorted(str(d) for d in forced_eod["days"])
    if part_cap:
        # what the cap actually did: how much size it refused, and whether it left anything to be
        # dumped into the closing bar (the one fill in the session that cannot be worked).
        want = sum(c["want"] * c["px"] for c in clipped)
        got = sum(c["got"] * c["px"] for c in clipped)
        s["clipped_orders"] = len(clipped)
        s["clipped_notional_refused"] = want - got
    if collect_trades:
        # opt-in because the list is large; A-9 uses it to attribute P&L to (symbol, session)
        s["trades_log"] = book.trades
    return s


def summarize(daily, book: Book, equity0: float, elapsed: float):
    d = pd.DataFrame(daily)
    if d.empty:
        return {"error": "no sessions"}
    rets = d["ret"].values
    n = len(rets)
    eq = d["equity"].values
    peak = np.maximum.accumulate(np.concatenate([[equity0], eq]))
    dd = (np.concatenate([[equity0], eq]) / peak - 1.0).min()
    mean, std = rets.mean(), rets.std(ddof=1) if n > 1 else float("nan")
    sharpe = (mean / std * math.sqrt(252)) if std and std > 0 else float("nan")
    total_ret = eq[-1] / equity0 - 1.0
    cagr = (1 + total_ret) ** (252 / n) - 1.0 if n else float("nan")
    wins = [t for t in book.trades]
    per_day_trades = d["trades"].mean()
    # AUD-21: turnover is a fraction of the equity that was actually working, not of the equity the
    # book started with eleven years ago. On a book that grows or shrinks the two differ by the
    # growth factor and the old number flattered a losing book.
    eq_mean = float(np.mean(np.concatenate([[equity0], eq])))
    turnover = sum(abs(t["qty"]) * t["px"] for t in book.trades) / eq_mean / n if n else 0
    # AUD-21: the drawdown path includes the intraday troughs, not only the end-of-day marks. The
    # EOD figure is kept under its old name so ledger rows stay comparable.
    if "low" in d:
        path = np.empty(2 * n + 1)
        path[0], path[1::2], path[2::2] = equity0, d["low"].values, eq
        dd_intra = float((path / np.maximum.accumulate(path) - 1.0).min())
    else:
        dd_intra = dd
    return {
        "max_drawdown_intraday_pct": -dd_intra * 100,
        "sessions": n, "net_profit_pct": total_ret * 100, "cagr_pct": cagr * 100, "sharpe": sharpe,
        "max_drawdown_pct": -dd * 100, "avg_daily_pnl": d["pnl"].mean(), "daily_pnl_std": d["pnl"].std(ddof=1) if n > 1 else 0,
        "best_day": d["pnl"].max(), "worst_day": d["pnl"].min(), "win_days_pct": (d["pnl"] > 0).mean() * 100,
        "trades": len(book.trades), "trades_per_day": per_day_trades, "turnover_per_day_x": turnover,
        "costs_total": book.costs, "costs_per_day": book.costs / n, "stopped_days": int(d["stopped"].sum()),
        "elapsed_s": elapsed, "daily": d,
    }


def print_summary(name: str, s: dict, label: str = ""):
    if "error" in s:
        print(f"{name}: {s['error']}")
        return
    print(f"\n=== {name} {label} ({s['sessions']} sessions, {s['elapsed_s']:.0f}s) ===")
    keys = [("net_profit_pct", "net profit %", "{:.2f}"), ("cagr_pct", "annualized %", "{:.1f}"),
            ("sharpe", "Sharpe (daily)", "{:.2f}"), ("max_drawdown_pct", "max drawdown % (EOD)", "{:.2f}"),
            ("max_drawdown_intraday_pct", "max drawdown % (path)", "{:.2f}"),
            ("avg_daily_pnl", "avg daily P&L $", "{:,.0f}"), ("daily_pnl_std", "daily P&L std $", "{:,.0f}"),
            ("best_day", "best day $", "{:,.0f}"), ("worst_day", "worst day $", "{:,.0f}"),
            ("win_days_pct", "winning days %", "{:.0f}"), ("trades", "trades", "{}"),
            ("trades_per_day", "trades/day", "{:.1f}"), ("turnover_per_day_x", "turnover/day (x equity)", "{:.2f}"),
            ("costs_per_day", "costs/day $", "{:,.0f}"), ("stopped_days", "loss-limit days", "{}")]
    for k, lab, fmt in keys:
        print(f"  {lab:<26}{fmt.format(s[k])}")
    if s.get("forced_eod_orders"):
        d = s.get("forced_eod_days") or []
        print(f"  {'forced eod fills':<26}{s['forced_eod_orders']} on {len(d)} session(s), "
              f"${s['forced_eod_notional']:,.0f} (AUD-07: not worked, not flattened) "
              f"{', '.join(d[:5])}{' ...' if len(d) > 5 else ''}")


def record(name: str, tag: str, s: dict, params, start, end):
    if "error" in s:
        return
    rec = {"ts": dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"), "algorithm": f"intraday/{name}",
           "class": "intraday", "tag": tag, "commit": "", "run_dir": "", "track": "intraday",
           "params": params or {}, "start": str(start), "end": str(end),
           "stats": {"Total Orders": str(s["trades"]), "Net Profit": f"{s['net_profit_pct']:.3f}%",
                     "Compounding Annual Return": f"{s['cagr_pct']:.3f}%", "Sharpe Ratio": f"{s['sharpe']:.3f}",
                     "Drawdown": f"{s['max_drawdown_pct']:.3f}%", "Trades Per Day": f"{s['trades_per_day']:.1f}",
                     "Avg Daily PnL": f"{s['avg_daily_pnl']:.0f}", "Costs Per Day": f"{s['costs_per_day']:.0f}",
                     "Worst Day": f"{s['worst_day']:.0f}", "Loss Limit Days": str(s["stopped_days"]),
                     "Sessions": str(s["sessions"])}}
    if "max_drawdown_intraday_pct" in s:   # AUD-21; "Drawdown" stays EOD so old rows compare
        rec["stats"]["Drawdown Intraday"] = f"{s['max_drawdown_intraday_pct']:.3f}%"
    if FILL_MODEL != "next_bar":
        rec["fill_model"] = FILL_MODEL
    if RISK != SHIPPED_RISK:
        rec["risk"] = dict(RISK)
    if intraday_common.SLIPPAGE_BPS != SLIPPAGE_BPS:
        rec["slippage_bps"] = intraday_common.SLIPPAGE_BPS
    # Provenance: the intraday harness runs on 3.14 (it needs pyarrow) while the LEAN path
    # runs on 3.11, and both write this file. Stamping env_key makes a cross-environment
    # comparison detectable. Never allowed to break a recorded run.
    try:
        import sys as _sys
        if str(REPO) not in _sys.path:
            _sys.path.insert(0, str(REPO))
        from quant_brain.core.provenance import Provenance
        prov = Provenance.capture(experiment_id=f"intraday/{name}@{rec['ts']}", repo=REPO,
                                  config={"params": params, "risk": dict(RISK)},
                                  strategy_version=name)
        rec["provenance"] = prov.to_dict()
        rec["env_key"] = prov.env_key
        rec["reproducible"] = prov.reproducible
        rec["commit"] = prov.git_commit[:12]
    except Exception as exc:  # noqa: BLE001
        rec["provenance_error"] = f"{type(exc).__name__}: {exc}"[:200]
    with EXPERIMENTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strategy", default="active")
    ap.add_argument("--symbols", nargs="*")
    ap.add_argument("--start"); ap.add_argument("--end")
    ap.add_argument("--split", help="date: report in-sample (< split) and out-of-sample (>= split) separately")
    ap.add_argument("--no-validate", action="store_true",
                    help="downgrade data-validation FAILs to warnings (diagnostics only)")
    ap.add_argument("--equity", type=float, default=1_000_000)
    ap.add_argument("--params", help="JSON overrides for the strategy PARAMS")
    ap.add_argument("--risk", help='JSON overrides for the framework risk limits, research only, e.g. '
                                   '\'{"daily_loss_limit":0.02,"per_symbol_hard_cap":0.25}\'')
    ap.add_argument("--slippage-bps", type=float, help="override intraday_common.SLIPPAGE_BPS, research only")
    ap.add_argument("--nav-frac", type=float,
                    help="AUD-21: sleeve equity as a fraction of ACCOUNT NAV, so the daily loss "
                         "limit is charged against the same base the live trader uses. Pass the "
                         "deployed live/intraday_config.json equity_frac to model the live rule; "
                         "the default of 1.0 is the (tighter) limit every pre-2026-09-12 row ran on.")
    ap.add_argument("--legacy-fills", action="store_true",
                    help="AUD-21: restore the pre-2026-09-12 fill model (a missing bar filled at the "
                         "decision bar's own close). Only for reproducing an existing ledger row.")
    ap.add_argument("--legacy-atr", action="store_true",
                    help="AUD-21: restore the pre-2026-09-12 atr14, whose bar-0 true range included "
                         "the overnight gap. Only for reproducing an existing ledger row.")
    ap.add_argument("--strict-eod", action="store_true",
                    help="AUD-07: exit 2 if any session ended with a position dumped into the last "
                         "stored bar. Every such fill is a flatten the framework failed to work.")
    ap.add_argument("--no-calendar-trim", action="store_true",
                    help="AUD-07: keep bars at or after the session's own calendar close (the 21 "
                         "early closes in the Alpaca store carry post-market prints). Reproduction "
                         "of a pre-2026-09-13 ledger row only.")
    ap.add_argument("--tag", default="")
    ap.add_argument("--no-record", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    if args.no_calendar_trim:
        intraday_common.CALENDAR_TRIM = False
        print("AUD-07: calendar trim OFF (post-close bars kept), research reproduction only")
    global FILL_MODEL
    if args.legacy_fills:
        FILL_MODEL = "decision_close"
        print("AUD-21: legacy fill model (missing bar -> decision close), research reproduction only")
    if args.legacy_atr:
        print("AUD-21: legacy atr14 (bar-0 true range spans the overnight gap), reproduction only")
    strategy = load_strategy(args.strategy)
    params = {**strategy.PARAMS, **(json.loads(args.params) if args.params else {})}
    overrides = json.loads(args.risk) if args.risk else {}
    if args.nav_frac is not None:
        overrides["nav_frac"] = args.nav_frac
    changed = set_risk(overrides)
    if changed:
        print(f"risk overrides (backtest only): {changed}")
    warn_loss_limit_base()
    if set_slippage(args.slippage_bps) is not None:
        print(f"slippage override (backtest only): {intraday_common.SLIPPAGE_BPS} bps (shipped {SLIPPAGE_BPS})")
    start = dt.date.fromisoformat(args.start) if args.start else None
    end = dt.date.fromisoformat(args.end) if args.end else None
    bars = load_universe(args.symbols or UNIVERSE, start, end)
    validate_bars(bars, strict=not args.no_validate)
    if not bars:
        sys.exit("no bars in data/minute; run scripts/intraday_data.py first")
    print(f"{len(bars)} symbols, {len(sessions(bars))} sessions on disk")
    feats = {s: features(df, gap_true_range=args.legacy_atr) for s, df in bars.items()}
    if args.split:
        split = dt.date.fromisoformat(args.split)
        s_is = run(strategy, bars, args.equity, params, start, split - dt.timedelta(days=1), args.verbose, feats)
        s_oos = run(strategy, bars, args.equity, params, split, end, args.verbose, feats)
        print_summary(args.strategy, s_is, f"IN-SAMPLE < {split}")
        print_summary(args.strategy, s_oos, f"OUT-OF-SAMPLE >= {split}")
        if not args.no_record:
            # AUD-21: the in-sample row ends the day BEFORE the split, which is the window it ran.
            record(args.strategy, f"{args.tag} [IS<{split}]", s_is, params, start,
                   split - dt.timedelta(days=1))
            record(args.strategy, f"{args.tag} [OOS>={split}]", s_oos, params, split, end)
        n_eod = s_is.get("forced_eod_orders", 0) + s_oos.get("forced_eod_orders", 0)
        if args.strict_eod and n_eod:
            print(f"REFUSED (--strict-eod): {n_eod} forced end-of-day fills")
            return 2
        return 0
    s = run(strategy, bars, args.equity, params, start, end, args.verbose, feats)
    print_summary(args.strategy, s)
    if "daily" in s and args.verbose:
        print(s["daily"][["day", "pnl", "trades", "stopped"]].to_string(index=False))
    if not args.no_record:
        record(args.strategy, args.tag, s, params, start, end)
    if args.strict_eod and s.get("forced_eod_orders"):
        print(f"REFUSED (--strict-eod): {s['forced_eod_orders']} forced end-of-day fills on "
              f"{len(s['forced_eod_days'])} session(s)")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
