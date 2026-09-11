#!/usr/bin/env python
"""S-17: what the daily champion's 24.404% assumes about execution, and what it costs.

Fourteen S-track iterations have judged cells against each other on a number that charges
commission and **no spread at all**. That is not an approximation someone chose - it is
LEAN's default: `DefaultBrokerageModel.GetSlippageModel` returns `NullSlippageModel.Instance`
and `InteractiveBrokersBrokerageModel` does not override it, so every fill in this repository
is booked at the exact opening print. `EquityFillModel.MarketOnOpenFill` *does* apply a
slippage model when one is set, so the omission is priceable, and `S1_SLIPPAGE_BPS` prices it.

The second assumption is the fill-timing convention, which the live log settles as a fact
rather than a worry (`scripts/daily_fills.py`): the backtest reads closes through day D and
fills at the **open of D+1**, while `scripts/paper_trade.py` reads the last complete yfinance
bar at 15:45 ET - **D-1's close, in 6 of 6 measured fills** - and fills at **D's close**. Both
act on the same signal date and fill a full session apart. `S1_SIGNAL_LAG=1` is the upper
bound on that (it adds one session of staleness *and* keeps the D+1 open fill, so it is one
overnight gap more stale than the live path, never less).

    python scripts/sweep_s17.py            # tables + paired daily statistics
    python scripts/sweep_s17.py --list      # which run each cell resolved to

Nothing here promotes anything. What it can do is change which cells are comparable at all.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sweep_s15 import (daily_log_returns, equity_curve, ledger_rows,  # noqa: E402
                       paired, pct, trading_days)

REPO = Path(__file__).resolve().parents[1]

#: key -> (label, ledger-tag substring, slippage bps, group)
CELLS = [
    ("control", "champion, 0 bp (shipped)", "S-17 control", 0.0, "spread"),
    ("sl1", "champion, 1 bp", "S-17 spread: champion + 1 bp", 1.0, "spread"),
    ("sl2", "champion, 2 bp", "S-17 spread: champion + 2 bp", 2.0, "spread"),
    ("sl5", "champion, 5 bp", "S-17 spread: champion + 5 bp", 5.0, "spread"),
    ("sl10", "champion, 10 bp", "S-17 spread: champion + 10 bp", 10.0, "spread"),

    ("lag1", "champion + 1 session of lag, 0 bp", "S-17 lag: champion + 1 session", 0.0, "lag"),
    ("lag1_sl2", "champion + 1 session of lag, 2 bp", "S-17 lag+spread", 2.0, "lag"),

    ("eg75", "S-16 (e+g) budget 0.75, 0 bp", "S-16 (e+g) levered proxies off AND", 0.0, "s16"),
    ("eg75_sl1", "S-16 (e+g) budget 0.75, 1 bp",
     "S-16 (e+g) budget 0.75: proxies off, overlay off, 1 bp", 1.0, "s16"),
    ("eg75_sl2", "S-16 (e+g) budget 0.75, 2 bp",
     "S-16 (e+g) budget 0.75: proxies off, overlay off, 2 bp", 2.0, "s16"),
    ("eg80", "S-16 (e+g) budget 0.80, 0 bp", "S-16 (e+g, budget 0.80) proxies off", 0.0, "s16"),
    ("eg80_sl2", "S-16 (e+g) budget 0.80, 2 bp", "S-17 spread on S-16 (e+g) budget 0.80", 2.0, "s16"),

    ("band03_sl2", "band 0.03, 2 bp", "S-17 band at 2 bp slippage: min_order_value 0.03", 2.0, "band"),
    ("band08_sl2", "band 0.08, 2 bp", "S-17 band at 2 bp slippage: min_order_value 0.08", 2.0, "band"),
]

#: S-13's zero-spread band sweep, for the columns this iteration does not re-run.
S13_BAND = {0.01: (24.40, 0.921, 25.1, 4735), 0.03: (24.34, 0.917, 25.5, 2737),
            0.08: (24.47, 0.920, 25.4, 1727)}


def resolve(rows: list[dict]) -> dict[str, dict]:
    out = {}
    for key, _label, needle, _bps, _grp in CELLS:
        hits = [r for r in rows if needle in (r.get("tag") or "")]
        if hits:
            out[key] = hits[-1]
    return out


def stat(row: dict, name: str) -> float:
    return pct(row["stats"].get(name))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    got = resolve(ledger_rows())
    missing = [k for k, *_ in CELLS if k not in got]
    if args.list:
        for key, label, needle, bps, grp in CELLS:
            r = got.get(key)
            print(f"{key:12s} {grp:7s} {label:36s} -> "
                  f"{r['run_dir'] if r else 'MISSING (run scripts/_s17_runs.sh)'}")
        return 0
    if missing:
        print(f"missing cells: {missing}  -> run scripts/_s17_runs.sh", file=sys.stderr)

    sessions = trading_days()
    curves = {}
    for key in got:
        try:
            curves[key] = equity_curve(REPO / got[key]["run_dir"], sessions)
        except Exception as exc:                                    # noqa: BLE001
            print(f"  (no equity curve for {key}: {exc})", file=sys.stderr)

    def table(keys, title):
        print(f"\n### {title}")
        print(f"\n{'cell':36s} {'orders':>7s} {'CAR%':>7s} {'dCAR':>6s} {'Sharpe':>7s} "
              f"{'MaxDD%':>7s} {'std':>6s} {'PSR%':>6s} {'fees':>10s}")
        base = stat(got["control"], "Compounding Annual Return") if "control" in got else None
        for key in keys:
            r = got.get(key)
            label = dict((k, l) for k, l, *_ in CELLS)[key]
            if not r:
                print(f"{label:36s} {'MISSING':>7s}")
                continue
            car = stat(r, "Compounding Annual Return")
            d = f"{car - base:+.2f}" if base is not None else ""
            print(f"{label:36s} {int(pct(r['stats']['Total Orders'])):>7,d} {car:>7.3f} "
                  f"{d:>6s} {stat(r, 'Sharpe Ratio'):>7.3f} {stat(r, 'Drawdown'):>7.1f} "
                  f"{stat(r, 'Annual Standard Deviation'):>6.3f} "
                  f"{stat(r, 'Probabilistic Sharpe Ratio'):>6.1f} "
                  f"{r['stats'].get('Total Fees', ''):>10s}")

    table([k for k, *_rest in CELLS if _rest[3] == "spread"],
          "1. The spread the harness has never charged (shipped champion)")

    # Cost per basis point, fitted on the spread ladder: the champion's own price of a spread.
    ladder = [(bps, stat(got[k], "Compounding Annual Return"))
              for k, _l, _n, bps, grp in CELLS if grp == "spread" and k in got]
    if len(ladder) >= 3:
        base = ladder[0][1]
        print("\n  CAR points lost per bp of spread, and what the measured cost implies:")
        for bps, car in ladder[1:]:
            print(f"    {bps:>5.1f} bp -> {car:7.3f}%  ({car - base:+.2f} CAR, "
                  f"{(car - base) / bps:+.3f} per bp)")
        slope = sum((c - base) / b for b, c in ladder[1:]) / len(ladder[1:])
        measured = 2.9   # scripts/daily_fills.py, 6 fills over 2 paper sessions
        print(f"\n    mean slope {slope:+.3f} CAR per bp.  At the +{measured} bp measured on the "
              f"live paper fills\n    the champion's honest full-period CAR is about "
              f"{base + slope * measured:.1f}%, not {base:.3f}%.")
        # Turnover implied by the slope: dCAR/dbps ~= -turnover_per_year, in units of equity.
        print(f"    The slope is also a turnover meter: {abs(slope):.3f} CAR per bp means the "
              f"book trades\n    ~{abs(slope) * 1e4 / 1e2:.0f}x its equity a year in one-way "
              f"notional, all of it paying that spread.")

    table([k for k, *_rest in CELLS if _rest[3] == "lag"],
          "2. The fill-timing convention (an upper bound on the live path's staleness)")
    table([k for k, *_rest in CELLS if _rest[3] == "s16"],
          "3. Does the spread re-rank S-16's parked frontier?")

    # Where does the ranking flip? S-16 had to refuse (e+g) at budget 0.75 because it missed
    # the champion's CAR by 0.001 points. That margin only exists at exactly zero spread.
    cross = [(0.0, "control", "eg75"), (1.0, "sl1", "eg75_sl1"), (2.0, "sl2", "eg75_sl2")]
    print("\n  The crossover, (e+g) at the unchanged 0.75 budget minus the champion:")
    for bps, champ, cand in cross:
        if champ in got and cand in got:
            a = stat(got[cand], "Compounding Annual Return")
            b = stat(got[champ], "Compounding Annual Return")
            print(f"    {bps:>4.1f} bp   {a:7.3f} vs {b:7.3f}  ->  {a - b:+.3f} CAR, "
                  f"Sharpe {stat(got[cand], 'Sharpe Ratio'):+.3f} vs "
                  f"{stat(got[champ], 'Sharpe Ratio'):.3f}, "
                  f"DD {stat(got[cand], 'Drawdown'):.1f} vs {stat(got[champ], 'Drawdown'):.1f}")
    print("  A half-cent tick is 0.27 bp on XLK, 0.71 on TQQQ and 0.77 on XLE, so the hard\n"
          "  floor of what a real fill costs is already past the crossover.")

    print("\n### 4. The owner's no-trade band, with the spread charged")
    print(f"\n{'band':>6s} {'orders':>7s} {'CAR% @0bp':>10s} {'CAR% @2bp':>10s} "
          f"{'Sharpe @2bp':>12s} {'MaxDD% @2bp':>12s}")
    band_cells = {0.01: "sl2", 0.03: "band03_sl2", 0.08: "band08_sl2"}
    for band, key in band_cells.items():
        r = got.get(key)
        z = S13_BAND[band]
        if not r:
            print(f"{band:>6.2f} {z[3]:>7,d} {z[0]:>10.2f} {'MISSING':>10s}")
            continue
        print(f"{band:>6.2f} {int(pct(r['stats']['Total Orders'])):>7,d} {z[0]:>10.2f} "
              f"{stat(r, 'Compounding Annual Return'):>10.3f} "
              f"{stat(r, 'Sharpe Ratio'):>12.3f} {stat(r, 'Drawdown'):>12.1f}")
    print("\n  S-13 left this to the owner because the saving is a spread the backtest did not\n"
          "  model. It is modelled now, so the band is a research question again.")

    # Paired daily statistics against the shipped champion, on the sessions both are marked.
    if "control" in curves:
        base_r = daily_log_returns(curves["control"])
        print(f"\n### 5. Paired daily log returns, cell minus the shipped champion\n")
        print(f"{'cell':36s} {'bps/day':>8s} {'t':>7s} {'ann.%':>7s} {'n':>6s}")
        for key, label, _n, _b, _g in CELLS:
            if key == "control" or key not in curves:
                continue
            d, t, n = paired(daily_log_returns(curves[key]), base_r)
            print(f"{label:36s} {d:>8.2f} {t:>7.2f} {d * 252 / 100:>7.2f} {n:>6d}")

    # The comparison that actually decides anything. Section 5's base is the champion with
    # NO spread charged, so a candidate that pays one is being compared with a book that does
    # not - which is precisely the error this whole iteration is about. Charge both.
    if "sl2" in curves:
        print("\n### 6. Like for like: candidate minus the champion at the SAME spread (2 bp)\n")
        base2 = daily_log_returns(curves["sl2"])
        car2 = stat(got["sl2"], "Compounding Annual Return")
        print(f"{'cell':36s} {'CAR%':>7s} {'dCAR':>6s} {'bps/day':>8s} {'t':>7s} {'n':>6s}")
        for key in ("eg75_sl2", "eg80_sl2", "band03_sl2", "band08_sl2", "lag1_sl2"):
            if key not in curves:
                continue
            label = dict((k, l) for k, l, *_ in CELLS)[key]
            d, t, n = paired(daily_log_returns(curves[key]), base2)
            car = stat(got[key], "Compounding Annual Return")
            print(f"{label:36s} {car:>7.3f} {car - car2:>+6.2f} {d:>8.2f} {t:>7.2f} {n:>6d}")
        print(f"\n  Champion at 2 bp is {car2:.3f}% / "
              f"{stat(got['sl2'], 'Sharpe Ratio'):.3f} / "
              f"DD {stat(got['sl2'], 'Drawdown'):.1f}%.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
