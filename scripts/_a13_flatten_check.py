#!/usr/bin/env python
"""A-13 side check: how much of the control's gap to A-10's published row is AUD-07's flatten?

A-13's `control` cell is the pre-AUD-21 harness, so it should land on A-10's 2026-09-10 figures.
It matches on structure (674 sessions, 39.07 vs 39.1 trades/day, 30 vs 30 loss-limit days) and not
on $/day (-132.5 vs -65). The one harness change committed in between that can move a P&L is
AUD-07's calendar-aware flatten, which on the 21 early closes of this window now targets zero 22
bars before the REAL close instead of at a minute index the session never reaches. This runs the
control both ways and prints the difference; it writes nothing.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[1]
os.environ.setdefault("INTRADAY_DATA_DIR", str(REPO_DIR / "data" / "minute_alpaca"))

import datetime as dt  # noqa: E402
import sys  # noqa: E402
from concurrent.futures import ProcessPoolExecutor  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO_DIR / "algorithms" / "intraday"))

import intraday_backtest as ib  # noqa: E402
from base import features  # noqa: E402
from intraday_common import UNIVERSE, load_universe  # noqa: E402
from sweep_a13 import DEPLOYED, EQUITY  # noqa: E402

YEARS = (2024, 2025, 2026)


def _const_flatten(_day):
    return int(ib.RISK["flatten_minute"])


def job(spec):
    calendar, year = spec
    if not calendar:
        ib.flatten_minute_for = _const_flatten
    ib.FILL_MODEL = "decision_close"
    lo, hi = dt.date(year, 1, 1), dt.date(year, 12, 31)
    bars = load_universe(UNIVERSE, lo, hi)
    feats = {s: features(d, gap_true_range=True) for s, d in bars.items()}
    strat = ib.load_strategy("active")
    s = ib.run(strat, bars, EQUITY, {**strat.PARAMS, **DEPLOYED}, lo, hi, False, feats_all=feats)
    return calendar, year, s["sessions"], s["avg_daily_pnl"], s["trades_per_day"], s["stopped_days"]


def main() -> int:
    jobs = [(c, y) for c in (True, False) for y in YEARS]
    agg = {True: [], False: []}
    with ProcessPoolExecutor(max_workers=6) as ex:
        for cal, year, n, pnl, tpd, stops in ex.map(job, jobs):
            print(f"  calendar={cal!s:5s} {year}: {n:4d} sessions  $/day {pnl:>9,.2f}  "
                  f"tr/day {tpd:5.2f}  stops {stops:3d}", flush=True)
            agg[cal].append((n, pnl, tpd, stops))
    for cal in (True, False):
        rows = agg[cal]
        n = sum(r[0] for r in rows)
        print(f"{'calendar-aware (AUD-07, current)' if cal else 'FLATTEN_MINUTE constant (as A-10 ran)':40s}"
              f" {n} sessions  $/day {sum(r[0] * r[1] for r in rows) / n:>9,.2f}"
              f"  tr/day {sum(r[0] * r[2] for r in rows) / n:5.2f}  stops {sum(r[3] for r in rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
