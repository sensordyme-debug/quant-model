#!/usr/bin/env python
"""A-7: price the intraday sleeve's *framework* risk limits, not its signals.

A-1 and A-2 showed the signal layer is spent: every signal-level control either rotates return
between the halves or shrinks the position. The untested surface is the framework constants in
scripts/intraday_common.py - the daily loss limit, the per-symbol cap and the sleeve gross.
This sweeps them on the deployed mix over the same 9-month window the A-track has used
throughout (2025-12-15 .. 2026-09-08, split 2026-06-15, 124 IS / 59 OOS sessions).

    python scripts/sweep_a7.py                 # full sweep, 8 workers
    python scripts/sweep_a7.py --only limit    # one family
    python scripts/sweep_a7.py --record        # also append rows to research/experiments.jsonl

Judged on OOS Sharpe, worst day, loss-limit days and the *cost of stopping early*: for every
session a cell halted, what the no-limit cell earned on that same session from open to close.
Overrides apply to the backtest only; shipping one means editing intraday_common.py and
replaying a session (AGENTS.md rule a).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import intraday_backtest as ib  # noqa: E402
from intraday_common import REPO, UNIVERSE, load_universe  # noqa: E402

START, END, SPLIT = dt.date(2025, 12, 15), dt.date(2026, 9, 8), dt.date(2026, 6, 15)
EQUITY = 1_000_000.0
OUT = REPO / "results" / "a7"

#: The deployed config (live/intraday_config.json as of A-2), which is the control.
DEPLOYED = {"alloc": {"orb": 1.0, "vwap_trend": 0.0, "late_momo": 1.0},
            "per_symbol": 0.15, "gross": 1.5,
            "sub_params": {"late_momo": {"direction": -1}, "orb": {"disaster_atr": 4.0}}}


def cells(only: str | None, caps=None, skip_control: bool = False) -> list[dict]:
    """(name, family, risk overrides, strategy param overrides)."""
    out = [{"name": "control (limit 2.5%, cap 0.15, gross 1.5)", "family": "control", "risk": {}, "params": {}}]
    for lim in (0.015, 0.020, 0.030, 0.035, 1.0):
        label = "no limit" if lim >= 1.0 else f"limit {lim*100:.1f}%"
        out.append({"name": label, "family": "limit", "risk": {"daily_loss_limit": lim}, "params": {}})
    for cap in (caps or (0.10, 0.20, 0.25)):
        out.append({"name": f"per-symbol {cap:.2f}", "family": "cap",
                    "risk": {"per_symbol_hard_cap": max(0.20, cap)}, "params": {"per_symbol": cap}})
    for g in (1.0, 1.25, 2.0):
        out.append({"name": f"gross {g:.2f}", "family": "gross",
                    "risk": {"gross_hard_cap": max(1.6, g * 1.05)}, "params": {"gross": g}})
    if only:
        out = [c for c in out if c["family"] in (() if skip_control else ("control",)) + (only,)]
    return out


_BARS: dict = {}
_FEATS: dict = {}
_STRAT = None
SHIPPED = {"daily_loss_limit": 0.025, "per_symbol_hard_cap": 0.20, "gross_hard_cap": 1.6,
           "min_change": 0.02, "flatten_minute": 368}


def _init(start, end):
    """Each worker loads the bar store and the causal features once, then reuses them per cell."""
    global _STRAT
    from base import features
    _BARS.update(load_universe(UNIVERSE, start, end))
    _FEATS.update({s: features(df) for s, df in _BARS.items()})
    _STRAT = ib.load_strategy("active")


def _job(spec):
    cell, half, lo, hi = spec
    ib.RISK.update(SHIPPED)
    ib.RISK.update(cell["risk"])
    params = {**_STRAT.PARAMS, **DEPLOYED, **cell["params"]}
    s = ib.run(_STRAT, _BARS, EQUITY, params, lo, hi, False, feats_all=_FEATS)
    daily = s.pop("daily")
    return cell["name"], cell["family"], half, s, daily.to_dict("records"), params


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", choices=["limit", "cap", "gross"])
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--start"); ap.add_argument("--end"); ap.add_argument("--split")
    ap.add_argument("--caps", nargs="*", type=float, help="override the per-symbol cap family values")
    ap.add_argument("--skip-control", action="store_true", help="cells already run in an earlier pass")
    args = ap.parse_args()
    start = dt.date.fromisoformat(args.start) if args.start else START
    end = dt.date.fromisoformat(args.end) if args.end else END
    split = dt.date.fromisoformat(args.split) if args.split else SPLIT

    cs = cells(args.only, args.caps, args.skip_control)
    halves = {"IS": (start, split - dt.timedelta(days=1)), "OOS": (split, end)}
    jobs = [(c, h, *halves[h]) for c in cs for h in ("IS", "OOS")]
    print(f"{len(cs)} cells, {len(jobs)} half-runs, {args.workers} workers, {start}..{end} split {split}")
    OUT.mkdir(parents=True, exist_ok=True)
    res: dict[tuple[str, str], dict] = {}
    dailies: dict[tuple[str, str], pd.DataFrame] = {}
    fams: dict[str, str] = {}
    with ProcessPoolExecutor(max_workers=args.workers, initializer=_init, initargs=(start, end)) as ex:
        for name, fam, half, s, daily, params in ex.map(_job, jobs):
            res[(name, half)] = s
            fams[name] = fam
            dailies[(name, half)] = pd.DataFrame(daily)
            print(f"  done {name:<38} {half:<4} CAR {s['cagr_pct']:7.1f}  Sharpe {s['sharpe']:5.2f}  "
                  f"worst {s['worst_day']:>10,.0f}  stops {s['stopped_days']}")
            if args.record:
                ib.RISK.update(SHIPPED)
                ib.RISK.update(next(c["risk"] for c in cs if c["name"] == name))
                lo, hi = (start, split) if half == "IS" else (split, end)
                ib.record("active", f"A-7 {name} [{'IS<' if half == 'IS' else 'OOS>='}{split}]",
                          s, params, lo, hi)

    rows = []
    for name in [c["name"] for c in cs]:
        r = {"cell": name, "family": fams[name]}
        for half in ("IS", "OOS"):
            s = res[(name, half)]
            r[f"{half} CAR"] = round(s["cagr_pct"], 1)
            r[f"{half} Sharpe"] = round(s["sharpe"], 2)
            r[f"{half} DD"] = round(s["max_drawdown_pct"], 1)
            r[f"{half} $/day"] = round(s["avg_daily_pnl"])
            r[f"{half} worst"] = round(s["worst_day"])
            r[f"{half} stops"] = s["stopped_days"]
            r[f"{half} tr/day"] = round(s["trades_per_day"], 1)
        r["total P&L"] = round(sum(res[(name, h)]["avg_daily_pnl"] * res[(name, h)]["sessions"] for h in ("IS", "OOS")))
        rows.append(r)
    table = pd.DataFrame(rows)
    print(f"\n=== A-7 framework risk limits, deployed mix, {start}..{end} split {split} ===")
    print(table.to_string(index=False))
    table.to_csv(OUT / "sweep.csv", index=False)

    # cost of stopping early: what the no-limit cell earned on the sessions a cell halted
    if ("no limit", "IS") in dailies:
        print("\n=== cost of stopping early (return of the same session with the limit off) ===")
        base = {h: dailies[("no limit", h)].set_index("day") for h in ("IS", "OOS")}
        for name in [c["name"] for c in cs if c["family"] in ("control", "limit")]:
            if name == "no limit":
                continue
            for half in ("IS", "OOS"):
                d = dailies[(name, half)]
                halted = d[d["stopped"]]
                if halted.empty:
                    print(f"  {name:<24} {half:<4} no halts")
                    continue
                b = base[half].reindex(halted["day"])
                print(f"  {name:<24} {half:<4} {len(halted)} halts; halted-cell mean ret "
                      f"{halted['ret'].mean()*100:6.2f}%  vs limit-off same days {b['ret'].mean()*100:6.2f}%  "
                      f"(median stop minute {int(halted['stop_minute'].median())})")
    for k, d in dailies.items():
        d.to_csv(OUT / f"daily_{k[1]}_{k[0].replace(' ', '_').replace('%','pct').replace('(','').replace(')','').replace(',','')}.csv", index=False)
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
