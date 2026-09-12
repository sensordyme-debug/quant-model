#!/usr/bin/env python
"""A-13 / AUD-21: price the intraday harness's own biases on the deployed book.

    python scripts/sweep_a13.py --workers 15                    # 2024-2026 attribution
    python scripts/sweep_a13.py --workers 11 --years 2016 ... --cells control all

Why this exists
---------------
The 2026-09-12 operator audit filed AUD-21 [iterate]: six defects in
`scripts/intraday_backtest.py` and `algorithms/intraday/base.py`, "all in its own favour". Three
of them can change a P&L; three are reporting. Every A-track verdict on this sleeve - including
A-10's -$65/day for the deployed ORB book, which is the number `research/BLOCKERS.md` asks the
owner to decide on - was measured through them. This script prices the three that can move money,
one at a time and together, on the same store, params and yearly-reset convention A-10 used, so
the correction is attributable rather than a single new headline.

The three defects that can move money
-------------------------------------
* **fill**: a pending order whose symbol printed no bar at the fill minute was booked at the
  DECISION bar's own close - zero latency, at a price that minute never showed - or silently
  dropped if the symbol had not printed at all yet. 5.494% of the Alpaca store's (symbol, session,
  minute) cells are missing and 0.563% of the IBKR store's, so this is not a corner case. Fixed:
  the order stays on the wire until the symbol prints, and sizing nets what is pending exactly as
  `intraday_trader.py:562` does.
* **atr**: bar 0's true range used the PREVIOUS session's close, so every overnight gap was booked
  as one minute of range, inflating `atr14` for minutes 4-13. `orb` reads `atr14` only from minute
  15, and a complete session's `rolling(14)` at minute >= 14 no longer contains bar 0 - so the
  prediction below is that this is inert except where bars are MISSING and the window still
  reaches back to bar 0.
* **nav**: the live loss limit is -2.5% of ACCOUNT NAV while the harness charged it against SLEEVE
  equity, so at the deployed `equity_frac` of 0.25 the live limit is 4x looser. A-10 recorded 30
  loss-limit days for ORB on 2024-2026 that the live trader would not have taken.

Pre-registered clauses (fixed before the first run; see research/journal.md)
---------------------------------------------------------------------------
1. **Identity.** The `control` cell is the three legacy switches on. It must reproduce A-10's
   published `orb` figures for the same regime up to the harness changes committed since
   2026-09-10 (AUD-07's calendar-aware flatten), and must equal a fixed-harness run to the cent
   on any window with no missing bars.
2. **Direction.** The audit claims all six defects favour the harness. Every fixed cell must
   therefore be <= control in $/day. A cell that IMPROVES $/day past the materiality threshold
   refutes the audit's characterisation for that defect and is reported as such.
3. **Materiality.** A defect is material if it moves $/day by more than 10% of |control $/day| or
   moves the pooled t by more than 0.25.
4. **atr prediction.** `atr` differs from `control` only through sparse sessions; the count of
   (symbol, session) pairs whose range-close bar still sees bar 0 is measured directly and must be
   under 10% for the prediction to stand.
5. **nav direction.** A 4x looser limit can only remove stop-outs: `stopped_days` must fall and
   `worst_day` must not improve.
6. **Deploy gate.** `base.py` is loaded by the live trader. The atr fix ships only if the unit
   suite and `intraday_trader.py --replay <last stored session>` both pass.
7. **Withdrawal.** If the legacy switches do not reproduce the pre-fix harness on the IBKR store,
   nothing is concluded and nothing ships.

Costs are the shipped ones. Each calendar year is a fresh $1,000,000 book (A-10's convention) so a
dollar of 2016 P&L is comparable with a dollar of 2026 P&L and eleven years of compounding cannot
let the last two years own the sample.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[1]
# Must be set before intraday_common is imported (it reads the env var at import time) and it is
# inherited by the spawned workers, so every process in this sweep reads the same store.
os.environ.setdefault("INTRADAY_DATA_DIR", str(REPO_DIR / "data" / "minute_alpaca"))

import argparse  # noqa: E402
import datetime as dt  # noqa: E402
import sys  # noqa: E402
from concurrent.futures import ProcessPoolExecutor  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import intraday_backtest as ib  # noqa: E402
from intraday_common import DATA_DIR, REPO, UNIVERSE, load_universe  # noqa: E402

sys.path.insert(0, str(REPO / "algorithms" / "intraday"))
from base import features  # noqa: E402

EQUITY = 1_000_000.0
OUT = REPO / "results" / "a13"

#: live/intraday_config.json as of 2026-09-11 (equity_frac 0.25, ORB alone). The book being priced.
DEPLOYED = {"alloc": {"orb": 1.0, "vwap_trend": 0.0, "late_momo": 0.0},
            "per_symbol": 0.15, "gross": 1.5,
            "sub_params": {"late_momo": {"direction": -1}, "orb": {"disaster_atr": 4.0}}}
EQUITY_FRAC = 0.25

#: (fill model, legacy atr, nav_frac). `control` is the harness every A-track row was measured on.
CELLS = {
    "control": ("decision_close", True, 1.0),
    "fill":    ("next_bar", True, 1.0),
    "atr":     ("decision_close", False, 1.0),
    "nav":     ("decision_close", True, EQUITY_FRAC),
    "all":     ("next_bar", False, EQUITY_FRAC),
}
YEARS = list(range(2024, 2027))


def _job(spec):
    """One (cell, year): load once, run the deployed book under this cell's harness switches."""
    cell, year, symbols = spec
    fill, legacy_atr, nav_frac = CELLS[cell]
    lo, hi = dt.date(year, 1, 1), dt.date(year, 12, 31)
    bars = load_universe(symbols or UNIVERSE, lo, hi)
    if not bars:
        return cell, year, None
    feats = {s: features(df, gap_true_range=legacy_atr) for s, df in bars.items()}
    ib.FILL_MODEL = fill
    ib.RISK["nav_frac"] = nav_frac
    strat = ib.load_strategy("active")
    params = {**strat.PARAMS, **DEPLOYED}
    s = ib.run(strat, bars, EQUITY, params, lo, hi, False, feats_all=feats)
    d = s.pop("daily")
    return cell, year, {"daily": d, "trades_per_day": s["trades_per_day"], "trades": s["trades"],
                        "costs_per_day": s["costs_per_day"], "stopped_days": s["stopped_days"],
                        "turnover_per_day_x": s["turnover_per_day_x"],
                        "dd_eod": s["max_drawdown_pct"], "dd_path": s["max_drawdown_intraday_pct"]}


def stats(d: pd.DataFrame) -> dict:
    """Pooled statistics on a concatenated daily frame (each year started from a fresh book)."""
    n = len(d)
    if n < 2:
        return {}
    pnl, ret = d["pnl"].values, d["ret"].values
    se = pnl.std(ddof=1) / np.sqrt(n)
    growth = float(np.prod(1.0 + ret))
    eq = EQUITY * np.cumprod(1.0 + ret)
    peak = np.maximum.accumulate(np.concatenate([[EQUITY], eq]))
    return {"sessions": n, "$/day": pnl.mean(), "se": se, "t": pnl.mean() / se if se else float("nan"),
            "sharpe": ret.mean() / ret.std(ddof=1) * np.sqrt(252) if ret.std(ddof=1) else float("nan"),
            "car_pct": ((growth ** (252 / n)) - 1.0) * 100,
            "max_dd_pct": -float((np.concatenate([[EQUITY], eq]) / peak - 1.0).min()) * 100,
            "worst_day": pnl.min(), "win_days_pct": (pnl > 0).mean() * 100}


def paired(a: pd.DataFrame, b: pd.DataFrame) -> dict:
    """Paired difference cell - control on the sessions both ran, which is every session."""
    m = a.merge(b, on="day", suffixes=("_a", "_b"))
    diff = m["pnl_a"].values - m["pnl_b"].values
    n = len(diff)
    se = diff.std(ddof=1) / np.sqrt(n) if n > 1 else float("nan")
    return {"n": n, "d$/day": diff.mean(), "t": diff.mean() / se if se else float("nan")}


def sparse_sessions(years, symbols=None) -> dict:
    """Clause 4: how often can the corrected atr14 differ at all?

    `orb` caches the opening range on the first bar whose `minute >= 15`. `atr14` there is
    rolling(14) over the bars the symbol actually printed, so bar 0 is still inside the window
    exactly when that bar is at positional index < 14 - i.e. when the symbol printed fewer than 15
    bars in its first 16 minutes. Counted here directly rather than inferred.
    """
    hit = tot = 0
    for y in years:
        bars = load_universe(symbols or UNIVERSE, dt.date(y, 1, 1), dt.date(y, 12, 31))
        for df in bars.values():
            mins = (df.index.hour - 9) * 60 + df.index.minute - 30
            f = pd.DataFrame({"m": mins}, index=df.index)
            for _, g in f.groupby(df.index.date):
                arr = g["m"].values
                w = np.flatnonzero(arr >= 15)
                if not len(w):
                    continue
                tot += 1
                hit += int(w[0] < 14)
    return {"pairs": tot, "bar0_in_window": hit, "pct": 100.0 * hit / tot if tot else float("nan")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, default=15)
    ap.add_argument("--years", nargs="*", type=int, default=YEARS)
    ap.add_argument("--cells", nargs="*", default=list(CELLS))
    ap.add_argument("--symbols", nargs="*", help="subset of the universe (smoke tests only)")
    ap.add_argument("--sparse-only", action="store_true", help="clause 4 count only, no backtests")
    ap.add_argument("--record", action="store_true", help="append DIAGNOSTIC rows to the ledger")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"store: {DATA_DIR}")

    sp = sparse_sessions(args.years, args.symbols)
    print(f"\nclause 4: (symbol, session) pairs whose opening-range bar still sees bar 0: "
          f"{sp['bar0_in_window']:,} of {sp['pairs']:,} = {sp['pct']:.2f}%")
    if args.sparse_only:
        return 0

    jobs = [(c, y, args.symbols) for c in args.cells for y in args.years]
    print(f"{len(jobs)} jobs ({len(args.cells)} cells x {len(args.years)} years), {args.workers} workers; "
          f"each year is a fresh ${EQUITY:,.0f} book on the deployed ORB config")
    per = {c: {} for c in args.cells}
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for cell, year, out in ex.map(_job, jobs):
            if out is None:
                print(f"  {cell} {year}: no bars", flush=True)
                continue
            per[cell][year] = out
            print(f"  {cell:8s} {year}: {len(out['daily']):4d} sessions  $/day "
                  f"{out['daily']['pnl'].mean():>8,.0f}  tr/day {out['trades_per_day']:5.1f}  "
                  f"stops {out['stopped_days']:3d}", flush=True)

    daily = {c: pd.concat([per[c][y]["daily"] for y in sorted(per[c])], ignore_index=True)
             .sort_values("day").reset_index(drop=True) for c in args.cells if per[c]}
    for c, d in daily.items():
        d.to_csv(OUT / f"daily_{c}.csv", index=False)

    rows = []
    base = daily.get("control")
    for c in args.cells:
        if c not in daily:
            continue
        s = stats(daily[c])
        agg = {"trades/day": np.mean([per[c][y]["trades_per_day"] for y in per[c]]),
               "costs/day": np.mean([per[c][y]["costs_per_day"] for y in per[c]]),
               "stops": sum(per[c][y]["stopped_days"] for y in per[c])}
        p = paired(daily[c], base) if base is not None and c != "control" else {"d$/day": 0.0, "t": float("nan")}
        rows.append({"cell": c, **{k: round(v, 3) for k, v in s.items()}, **{k: round(v, 2) for k, v in agg.items()},
                     "d$/day vs control": round(p["d$/day"], 2), "paired t": round(p["t"], 2)})
    t = pd.DataFrame(rows)
    print(f"\n=== AUD-21: the deployed ORB book under each harness cell, {DATA_DIR.name}, "
          f"{int(rows[0]['sessions'])} sessions ===")
    with pd.option_context("display.width", 250):
        print(t.to_string(index=False))
    t.to_csv(OUT / "cells.csv", index=False)

    if args.record:
        span = f"{min(args.years)}-{max(args.years)}"
        for c in args.cells:
            if c not in daily:
                continue
            s = stats(daily[c])
            fake = {"sessions": s["sessions"], "net_profit_pct": float("nan"), "cagr_pct": s["car_pct"],
                    "sharpe": s["sharpe"], "max_drawdown_pct": s["max_dd_pct"], "avg_daily_pnl": s["$/day"],
                    "worst_day": s["worst_day"],
                    "trades": sum(per[c][y]["trades"] for y in per[c]),
                    "trades_per_day": np.mean([per[c][y]["trades_per_day"] for y in per[c]]),
                    "costs_per_day": np.mean([per[c][y]["costs_per_day"] for y in per[c]]),
                    "stopped_days": sum(per[c][y]["stopped_days"] for y in per[c])}
            fake["net_profit_pct"] = fake["cagr_pct"]
            ib.record("active", f"DIAGNOSTIC A-13/AUD-21 harness cell {c} [{span}] "
                                f"(deployed ORB, yearly-reset $1M, alpaca)", fake, DEPLOYED,
                      dt.date(min(args.years), 1, 1), dt.date(max(args.years), 12, 31))
    return 0


if __name__ == "__main__":
    sys.exit(main())
