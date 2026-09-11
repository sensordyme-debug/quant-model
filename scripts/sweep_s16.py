#!/usr/bin/env python
"""S-16: is the champion's instrument leverage the cheapest way to buy its volatility?

S-15 removed each of the champion's switches one at a time and found two that point the
same way: the 3x proxies (cell e) are better risk-adjusted when they are *off*, and the
drawdown overlay (cell g) is the only switch whose paired daily statistic is significant,
with the sign against it. S-15 never ran them together, and it never asked what the
unlevered book does when the exposure it loses is bought back with account leverage
instead of instrument leverage.

That is one question with a structural answer behind it. Reg-T charges 50% of notional for
an ordinary ETF and IBKR marks a 3x ETF up to 100%, so per unit of *economic exposure* the
3x sleeve costs 0.333 of margin and the unlevered sleeve costs 0.5 - the proxies are 33%
cheaper in margin, which is why the champion reaches ~2.25x exposure on a 0.75 budget while
the unlevered book stops at 1.5x. The cells below price what that cheaper exposure earns.

    python scripts/sweep_s16.py              # table + paired daily statistics
    python scripts/sweep_s16.py --list       # which run each cell resolved to

Nothing here promotes anything; `scripts/evaluate.py` does that and the margin budget is an
open owner question in research/BLOCKERS.md.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sweep_s15 import (daily_log_returns, equity_curve, ledger_rows,  # noqa: E402
                       paired, pct, trading_days)

REPO = Path(__file__).resolve().parents[1]
TRADING_DAYS = 252

#: cell -> (label, the substring that identifies its row in the ledger tag)
CELLS = [
    ("control", "champion (S-12, shipped)", "S-16 control"),
    ("e", "(e) proxies off, budget 0.75", "S-15 attribution (e)"),
    ("g", "(g) overlay off, budget 0.75", "S-15 attribution (g)"),
    ("e_g", "(e+g) proxies+overlay off, 0.75", "S-16 (e+g) levered proxies off AND"),
    ("e_b080", "(e) proxies off, budget 0.80", "S-16 (e only, budget 0.80)"),
    ("e_w_b080", "(e+wide dd) budget 0.80", "S-16 (e+dd wide, budget 0.80)"),
    ("e_g_b078", "(e+g) budget 0.78", "S-16 (e+g) shelf: proxies off, overlay off, margin_budget 0.78"),
    ("e_g_b080", "(e+g) budget 0.80", "S-16 (e+g, budget 0.80) proxies off"),
    ("e_g_b082", "(e+g) budget 0.82", "S-16 (e+g) shelf: proxies off, overlay off, margin_budget 0.82"),
]

#: Max gross weight the margin budget allows, given the margin charged per dollar of
#: notional for the instruments each cell actually holds (0.5 unlevered, 1.0 for a 3x ETF).
#: Economic exposure is that gross times the leverage of what is held.
STRUCTURE = {
    "control": (0.75, "3x proxies", 0.75, 2.25),
    "e": (0.75, "unlevered", 1.50, 1.50),
    "g": (0.75, "3x proxies", 0.75, 2.25),
    "e_g": (0.75, "unlevered", 1.50, 1.50),
    "e_b080": (0.80, "unlevered", 1.60, 1.60),
    "e_w_b080": (0.80, "unlevered", 1.60, 1.60),
    "e_g_b078": (0.78, "unlevered", 1.56, 1.56),
    "e_g_b080": (0.80, "unlevered", 1.60, 1.60),
    "e_g_b082": (0.82, "unlevered", 1.64, 1.64),
}


def resolve(rows: list[dict]) -> dict[str, dict]:
    """Latest ledger row per cell, so a re-run supersedes without editing this file."""
    out = {}
    for key, _label, needle in CELLS:
        hits = [r for r in rows if needle in (r.get("tag") or "")]
        if hits:
            out[key] = hits[-1]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="print the resolved run per cell and exit")
    args = ap.parse_args()

    rows = resolve(ledger_rows())
    missing = [k for k, _l, _n in CELLS if k not in rows]
    if args.list or missing:
        for key, label, _needle in CELLS:
            row = rows.get(key)
            print(f"  {key:<11} {label:<34} {row['ts'] if row else 'MISSING'}")
        if missing:
            print(f"\nmissing cells: {', '.join(missing)} - run scripts/_s16_runs.sh")
        if args.list:
            return 0
        return 1

    sessions = trading_days()
    curves = {k: daily_log_returns(equity_curve(REPO / rows[k]["run_dir"], sessions))
              for k in rows}
    base = curves["control"]
    base_car = pct(rows["control"]["stats"]["Compounding Annual Return"])

    print("=== S-16: instrument leverage vs account leverage, full period 2012-01-03..2026-09-04 ===\n")
    header = (f"{'cell':<34}{'budget':>7}{'held':>11}{'gross':>7}{'exp':>6}"
              f"{'orders':>8}{'CAR%':>9}{'dCAR':>8}{'Sharpe':>8}{'MaxDD%':>8}{'std':>7}"
              f"{'fees$':>10}{'PSR%':>7}")
    print(header)
    print("-" * len(header))
    for key, label, _needle in CELLS:
        stats = rows[key]["stats"]
        car = pct(stats["Compounding Annual Return"])
        budget, held, gross, exposure = STRUCTURE[key]
        d = "" if key == "control" else f"{car - base_car:+8.2f}"
        print(f"{label:<34}{budget:>7.2f}{held:>11}{gross:>7.2f}{exposure:>6.2f}"
              f"{int(pct(stats['Total Orders'])):>8}{car:>9.3f}{d:>8}"
              f"{pct(stats['Sharpe Ratio']):>8.3f}{pct(stats['Drawdown']):>8.1f}"
              f"{pct(stats['Annual Standard Deviation']):>7.3f}"
              f"{pct(stats['Total Fees']):>10,.0f}"
              f"{pct(stats['Probabilistic Sharpe Ratio']):>7.1f}")
    print("\n  gross / exp are the ceilings the budget allows, not realized averages: an "
          "unlevered\n  basket runs at 2 x budget, a 3x basket at 1 x budget for three times "
          "the exposure.")

    print("\n=== paired daily log returns, cell minus champion (what the swap is worth) ===\n")
    head2 = (f"{'cell':<34}{'bps/day':>10}{'t':>8}{'days':>8}{'ann.%':>9}"
             f"{'IS bps':>9}{'IS t':>7}{'OOS bps':>9}{'OOS t':>7}")
    print(head2)
    print("-" * len(head2))
    split = pd.Timestamp("2020-01-01").date()
    for key, label, _needle in CELLS:
        if key == "control":
            continue
        bps, t, n = paired(curves[key], base)
        ann = (math.exp(bps / 1e4 * TRADING_DAYS) - 1.0) * 100.0
        is_bps, is_t, _ = paired(curves[key][curves[key].index < split], base[base.index < split])
        oos_bps, oos_t, _ = paired(curves[key][curves[key].index >= split], base[base.index >= split])
        print(f"{label:<34}{bps:>10.2f}{t:>8.2f}{n:>8}{ann:>9.2f}"
              f"{is_bps:>9.2f}{is_t:>7.2f}{oos_bps:>9.2f}{oos_t:>7.2f}")

    print("\n  Sign convention is the reverse of S-15: a positive number is what the *cell* "
          "earns over\n  the shipped champion. IS = 2012-2019, OOS = 2020-2026, the halves "
          "S-12 was promoted on.\n  One path carries S-13's +/-0.3 CAR of scatter; the t is "
          "on the paired daily series.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
