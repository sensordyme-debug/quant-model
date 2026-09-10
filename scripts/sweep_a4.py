#!/usr/bin/env python
"""A-4: judge the intraday sleeve on the sessions it was never tuned on.

scripts/intraday_data.py --months 12 extended the minute store from 183 sessions
(2025-12-15 .. 2026-09-08, the window every A-track parameter was chosen on) to 260
(2025-08-26 .. 2026-09-08). The 77 sessions before 2025-12-15 are therefore a genuine
holdout: no A-track cell, allocation, stop or filter has ever seen them.

    python scripts/sweep_a4.py               # deployed mix and its two modules, both windows
    python scripts/sweep_a4.py --record      # also append rows to research/experiments.jsonl

Judged on the holdout half: average daily P&L after costs, Sharpe, worst day. A module that
is positive on the tuning window and negative on the holdout is a fitted module, not an edge.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import intraday_backtest as ib  # noqa: E402
from intraday_common import REPO, UNIVERSE, load_universe  # noqa: E402

#: full store minus today's partial session
START, END = dt.date(2025, 8, 26), dt.date(2026, 9, 8)
#: everything before this was fetched on 2026-09-09 and has never been tuned on
SPLIT = dt.date(2025, 12, 15)
EQUITY = 1_000_000.0
OUT = REPO / "results" / "a4"

#: live/intraday_config.json as of A-2 - the control.
DEPLOYED = {"alloc": {"orb": 1.0, "vwap_trend": 0.0, "late_momo": 1.0},
            "per_symbol": 0.15, "gross": 1.5,
            "sub_params": {"late_momo": {"direction": -1}, "orb": {"disaster_atr": 4.0}}}

CELLS = [
    {"name": "deployed mix (orb + late fade)", "params": {}},
    {"name": "orb only", "params": {"alloc": {"orb": 1.0, "vwap_trend": 0.0, "late_momo": 0.0}}},
    {"name": "late fade only", "params": {"alloc": {"orb": 0.0, "vwap_trend": 0.0, "late_momo": 1.0}}},
]

_BARS: dict = {}
_FEATS: dict = {}
_STRAT = None


def _init(start, end):
    global _STRAT
    from base import features
    _BARS.update(load_universe(UNIVERSE, start, end))
    _FEATS.update({s: features(df) for s, df in _BARS.items()})
    _STRAT = ib.load_strategy("active")


def _job(spec):
    cell, half, lo, hi = spec
    params = {**_STRAT.PARAMS, **DEPLOYED, **cell["params"]}
    s = ib.run(_STRAT, _BARS, EQUITY, params, lo, hi, False, feats_all=_FEATS)
    daily = s.pop("daily")
    return cell["name"], half, s, daily.to_dict("records"), params


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--start"); ap.add_argument("--end"); ap.add_argument("--split")
    args = ap.parse_args()
    start = dt.date.fromisoformat(args.start) if args.start else START
    end = dt.date.fromisoformat(args.end) if args.end else END
    split = dt.date.fromisoformat(args.split) if args.split else SPLIT

    halves = {"HOLD": (start, split - dt.timedelta(days=1)), "TUNE": (split, end)}
    jobs = [(c, h, *halves[h]) for c in CELLS for h in ("HOLD", "TUNE")]
    print(f"{len(CELLS)} cells, {len(jobs)} half-runs, {args.workers} workers, {start}..{end} split {split}")
    OUT.mkdir(parents=True, exist_ok=True)
    res: dict[tuple[str, str], dict] = {}
    dailies: dict[tuple[str, str], pd.DataFrame] = {}
    with ProcessPoolExecutor(max_workers=args.workers, initializer=_init, initargs=(start, end)) as ex:
        for name, half, s, daily, params in ex.map(_job, jobs):
            res[(name, half)] = s
            dailies[(name, half)] = pd.DataFrame(daily)
            print(f"  done {name:<32} {half:<5} CAR {s['cagr_pct']:7.1f}  Sharpe {s['sharpe']:5.2f}  "
                  f"$/day {s['avg_daily_pnl']:>9,.0f}  worst {s['worst_day']:>10,.0f}  stops {s['stopped_days']}",
                  flush=True)
            if args.record:
                lo, hi = halves[half]
                label = "HOLDOUT<" if half == "HOLD" else "TUNED>="
                ib.record("active", f"A-4 {name} [{label}{split}]", s, params, lo, hi)

    rows = []
    for cell in CELLS:
        name = cell["name"]
        r = {"cell": name}
        for half in ("HOLD", "TUNE"):
            s = res[(name, half)]
            r[f"{half} CAR"] = round(s["cagr_pct"], 1)
            r[f"{half} Sharpe"] = round(s["sharpe"], 2)
            r[f"{half} DD"] = round(s["max_drawdown_pct"], 1)
            r[f"{half} $/day"] = round(s["avg_daily_pnl"])
            r[f"{half} cost/day"] = round(s["costs_per_day"])
            r[f"{half} worst"] = round(s["worst_day"])
            r[f"{half} win%"] = round(s["win_days_pct"])
            r[f"{half} tr/day"] = round(s["trades_per_day"], 1)
            r[f"{half} stops"] = s["stopped_days"]
        r["total P&L"] = round(sum(res[(name, h)]["avg_daily_pnl"] * res[(name, h)]["sessions"]
                                   for h in ("HOLD", "TUNE")))
        rows.append(r)
    table = pd.DataFrame(rows)
    print(f"\n=== A-4 holdout vs tuning window, {start}..{end} split {split} ===")
    print(table.to_string(index=False))
    table.to_csv(OUT / "sweep.csv", index=False)

    # monthly path of each cell over the whole store, so a bad half can be read as a run of
    # months rather than a single event
    print("\n=== monthly P&L ($) ===")
    monthly = {}
    for cell in CELLS:
        name = cell["name"]
        d = pd.concat([dailies[(name, h)] for h in ("HOLD", "TUNE")], ignore_index=True)
        d["day"] = pd.to_datetime(d["day"])
        monthly[name] = d.set_index("day")["pnl"].resample("ME").sum().round(0)
    m = pd.DataFrame(monthly)
    m.index = m.index.strftime("%Y-%m")
    print(m.to_string())
    m.to_csv(OUT / "monthly.csv")

    # is the holdout distinguishable from the tuning window, or is it sample noise?
    print("\n=== Welch t on daily P&L, holdout vs tuning (no scipy: t only) ===")
    import numpy as np
    for cell in CELLS:
        name = cell["name"]
        a = dailies[(name, "HOLD")]["pnl"].values.astype(float)
        b = dailies[(name, "TUNE")]["pnl"].values.astype(float)
        se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
        t = (a.mean() - b.mean()) / se
        t0 = a.mean() / (a.std(ddof=1) / np.sqrt(len(a)))
        print(f"  {name:<32} hold {a.mean():>9,.0f}/day (n={len(a)})  tune {b.mean():>9,.0f}/day "
              f"(n={len(b)})  t={t:+.2f}   holdout vs zero t={t0:+.2f}")

    for k, d in dailies.items():
        d.to_csv(OUT / f"daily_{k[1]}_{k[0].replace(' ', '_').replace('(', '').replace(')', '')}.csv", index=False)
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
