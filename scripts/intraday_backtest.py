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
from base import features  # noqa: E402

EXPERIMENTS = REPO / "research" / "experiments.jsonl"

#: Framework risk limits for a research run. Defaults are exactly the shared constants the live
#: trader uses; --risk overrides them *for the backtest only* so A-7 can price them. Shipping a
#: change means editing scripts/intraday_common.py and replaying a session (AGENTS.md rule a).
#: `part_cap` is A-11's participation cap and is 0.0 = OFF in the shipped constants, i.e. the live
#: trader has no such cap and this default reproduces every prior A-track run bit for bit.
RISK = {"daily_loss_limit": DAILY_LOSS_LIMIT, "per_symbol_hard_cap": PER_SYMBOL_HARD_CAP,
        "gross_hard_cap": GROSS_HARD_CAP, "min_change": MIN_CHANGE, "flatten_minute": FLATTEN_MINUTE,
        "part_cap": 0.0}
SHIPPED_RISK = dict(RISK)


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
                      clipped: list | None = None):
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
    """
    orders = {}
    cap, gross_cap, min_change = RISK["per_symbol_hard_cap"], RISK["gross_hard_cap"], RISK["min_change"]
    gross = sum(abs(w) for w in targets.values())
    scale = min(1.0, gross_cap / gross) if gross > gross_cap else 1.0
    for sym in set(targets) | set(book.pos):
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
        cur = book.pos.get(sym, 0)
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
    forced_eod = {"orders": 0, "notional": 0.0}
    t0 = time.time()
    for day in days:
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
                for s, delta in pending.items():
                    j = cur_rows.get(s)
                    if j is None:
                        continue
                    row = fd[s].iloc[j - 1]
                    if row.name != t:          # no bar for this symbol at t; fill at last close
                        px = float(row["c"])
                    else:
                        px = float(row["o"])
                    book.fill(t, s, delta, px)
                    orders_total += 1
                pending = {}
            closes = {s: float(fd[s].iloc[j - 1]["c"]) for s, j in cur_rows.items()}
            equity = book.value(closes)
            minute = int((t.hour - 9) * 60 + t.minute - 30)
            # 2) risk: daily loss limit, end-of-day flatten
            if not stopped and equity - eq_open <= -RISK["daily_loss_limit"] * eq_open:
                stopped = True
                stop_minute = minute
                if verbose:
                    print(f"{day} {t.time()} daily loss limit hit: {equity - eq_open:,.0f}")
            if stopped or minute >= RISK["flatten_minute"]:
                targets = {}
            else:
                view = {s: fd[s].iloc[:j] for s, j in cur_rows.items()}
                targets = strategy.decide(t, view, dict(book.pos), equity, state, params) or {}
            # the order placed now fills at the NEXT bar's open, so it is worked in minute + 1
            caps = ({s: part_cap * float(r.get(minute + 1, float("nan")))
                     for s, r in vrow.items()} if vrow is not None else None)
            pending = targets_to_orders(targets, book, closes, equity, day, caps, clipped)
            if minute >= RISK["flatten_minute"] and book.pos and not pending:
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
            book.fill(times[-1], s, -q, px_eod, "eod")
            orders_total += 1
        eq_close = book.value({})
        daily.append({"day": day, "pnl": eq_close - eq_open, "ret": eq_close / eq_open - 1.0, "equity": eq_close,
                      "trades": sum(1 for tr in book.trades if tr["t"].date() == day), "stopped": stopped,
                      "stop_minute": stop_minute})
    elapsed = time.time() - t0
    s = summarize(daily, book, equity0, elapsed)
    if part_cap:
        # what the cap actually did: how much size it refused, and whether it left anything to be
        # dumped into the closing bar (the one fill in the session that cannot be worked).
        want = sum(c["want"] * c["px"] for c in clipped)
        got = sum(c["got"] * c["px"] for c in clipped)
        s["clipped_orders"] = len(clipped)
        s["clipped_notional_refused"] = want - got
        s["forced_eod_orders"] = forced_eod["orders"]
        s["forced_eod_notional"] = forced_eod["notional"]
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
    turnover = sum(abs(t["qty"]) * t["px"] for t in book.trades) / equity0 / n if n else 0
    return {
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
            ("sharpe", "Sharpe (daily)", "{:.2f}"), ("max_drawdown_pct", "max drawdown %", "{:.2f}"),
            ("avg_daily_pnl", "avg daily P&L $", "{:,.0f}"), ("daily_pnl_std", "daily P&L std $", "{:,.0f}"),
            ("best_day", "best day $", "{:,.0f}"), ("worst_day", "worst day $", "{:,.0f}"),
            ("win_days_pct", "winning days %", "{:.0f}"), ("trades", "trades", "{}"),
            ("trades_per_day", "trades/day", "{:.1f}"), ("turnover_per_day_x", "turnover/day (x equity)", "{:.2f}"),
            ("costs_per_day", "costs/day $", "{:,.0f}"), ("stopped_days", "loss-limit days", "{}")]
    for k, lab, fmt in keys:
        print(f"  {lab:<26}{fmt.format(s[k])}")


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
    ap.add_argument("--equity", type=float, default=1_000_000)
    ap.add_argument("--params", help="JSON overrides for the strategy PARAMS")
    ap.add_argument("--risk", help='JSON overrides for the framework risk limits, research only, e.g. '
                                   '\'{"daily_loss_limit":0.02,"per_symbol_hard_cap":0.25}\'')
    ap.add_argument("--slippage-bps", type=float, help="override intraday_common.SLIPPAGE_BPS, research only")
    ap.add_argument("--tag", default="")
    ap.add_argument("--no-record", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    strategy = load_strategy(args.strategy)
    params = {**strategy.PARAMS, **(json.loads(args.params) if args.params else {})}
    changed = set_risk(json.loads(args.risk) if args.risk else None)
    if changed:
        print(f"risk overrides (backtest only): {changed}")
    if set_slippage(args.slippage_bps) is not None:
        print(f"slippage override (backtest only): {intraday_common.SLIPPAGE_BPS} bps (shipped {SLIPPAGE_BPS})")
    start = dt.date.fromisoformat(args.start) if args.start else None
    end = dt.date.fromisoformat(args.end) if args.end else None
    bars = load_universe(args.symbols or UNIVERSE, start, end)
    if not bars:
        sys.exit("no bars in data/minute; run scripts/intraday_data.py first")
    print(f"{len(bars)} symbols, {len(sessions(bars))} sessions on disk")
    if args.split:
        split = dt.date.fromisoformat(args.split)
        s_is = run(strategy, bars, args.equity, params, start, split - dt.timedelta(days=1), args.verbose)
        s_oos = run(strategy, bars, args.equity, params, split, end, args.verbose)
        print_summary(args.strategy, s_is, f"IN-SAMPLE < {split}")
        print_summary(args.strategy, s_oos, f"OUT-OF-SAMPLE >= {split}")
        if not args.no_record:
            record(args.strategy, f"{args.tag} [IS<{split}]", s_is, params, start, split)
            record(args.strategy, f"{args.tag} [OOS>={split}]", s_oos, params, split, end)
        return 0
    s = run(strategy, bars, args.equity, params, start, end, args.verbose)
    print_summary(args.strategy, s)
    if "daily" in s and args.verbose:
        print(s["daily"][["day", "pnl", "trades", "stopped"]].to_string(index=False))
    if not args.no_record:
        record(args.strategy, args.tag, s, params, start, end)
    return 0


if __name__ == "__main__":
    sys.exit(main())
