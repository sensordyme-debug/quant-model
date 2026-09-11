#!/usr/bin/env python
"""S-18: the promotion case for the unlevered cell, judged half by half and cost by cost.

The candidate is S-16's (e+g) at the **unchanged** 0.75 margin budget - the shipped signal
held in unlevered parents (`S1_PROXY=off`) with the drawdown breaker removed
(`S1_DD_HALVE=9.0 S1_DD_FLAT=9.0`). S-16 refused it by 0.001 CAR points; S-17 showed that
margin exists only at exactly zero spread, which is LEAN's default rather than a modelling
choice, and that at 1 bp or 2 bp the cell wins on CAR, Sharpe and drawdown at once.

What was missing was evidence about *when* it wins. S-15 found that the last promotion's
edge (S-12's allocation tilt) was in-sample only, so a candidate that is a dead heat over
fourteen years has to be split before it is trusted. This reads the halves S-12 itself was
promoted on - IS 2012-2019, OOS 2020-2026 - at 0 bp and at 2 bp, with the champion run on
the same halves at the same spread, plus the no-trade band measured on the candidate rather
than on the champion.

    python scripts/sweep_s18.py            # tables, paired statistics, promotion arithmetic
    python scripts/sweep_s18.py --list     # which run each cell resolved to

It prints the case. It does not promote: that is `scripts/evaluate.py`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sweep_s15 import (daily_log_returns, equity_curve, ledger_rows,  # noqa: E402
                       paired, pct, trading_days)

REPO = Path(__file__).resolve().parents[1]

#: key -> (label, ledger-tag substring, period, spread bps, which book)
CELLS = [
    # Full period. All four already exist; S-18 re-runs none of them.
    ("champ_full_sl0", "champion, full, 0 bp", "S-17 control", "full", 0.0, "champion"),
    ("champ_full_sl2", "champion, full, 2 bp", "S-17 spread: champion + 2 bp", "full", 2.0, "champion"),
    ("cand_full_sl0", "candidate, full, 0 bp", "S-16 (e+g) levered proxies off AND", "full", 0.0, "candidate"),
    ("cand_full_sl2", "candidate, full, 2 bp",
     "S-16 (e+g) budget 0.75: proxies off, overlay off, 2 bp", "full", 2.0, "candidate"),

    # The halves. The champion's 0 bp halves are S-12's own promotion runs.
    ("champ_is_sl0", "champion, IS 2012-2019, 0 bp", "S-12f invvol window=21 IS", "is", 0.0, "champion"),
    ("champ_oos_sl0", "champion, OOS 2020-2026, 0 bp", "S-12f invvol window=21 OOS", "oos", 0.0, "champion"),
    ("champ_is_sl2", "champion, IS 2012-2019, 2 bp", "S-18 champion IS 2012-2019 at 2 bp", "is", 2.0, "champion"),
    ("champ_oos_sl2", "champion, OOS 2020-2026, 2 bp", "S-18 champion OOS 2020-2026 at 2 bp", "oos", 2.0, "champion"),
    ("cand_is_sl0", "candidate, IS 2012-2019, 0 bp", "S-18 (e+g) budget 0.75 IS 2012-2019 at 0 bp", "is", 0.0, "candidate"),
    ("cand_oos_sl0", "candidate, OOS 2020-2026, 0 bp", "S-18 (e+g) budget 0.75 OOS 2020-2026 at 0 bp", "oos", 0.0, "candidate"),
    ("cand_is_sl2", "candidate, IS 2012-2019, 2 bp", "S-18 (e+g) budget 0.75 IS 2012-2019 at 2 bp", "is", 2.0, "candidate"),
    ("cand_oos_sl2", "candidate, OOS 2020-2026, 2 bp", "S-18 (e+g) budget 0.75 OOS 2020-2026 at 2 bp", "oos", 2.0, "candidate"),

    # The band, on the candidate's own book.
    ("cand_band03_sl0", "candidate + band 0.03, full, 0 bp",
     "S-18 (e+g) budget 0.75 + min_order_value 0.03 at 0 bp", "full", 0.0, "band"),
    ("cand_band03_sl2", "candidate + band 0.03, full, 2 bp",
     "S-18 (e+g) budget 0.75 + min_order_value 0.03 at 2 bp", "full", 2.0, "band"),
]

LABEL = {k: l for k, l, *_ in CELLS}
METRICS = ["Compounding Annual Return", "Sharpe Ratio", "Drawdown",
           "Annual Standard Deviation", "Probabilistic Sharpe Ratio"]


def resolve(rows: list[dict]) -> dict[str, dict]:
    out = {}
    for key, _label, needle, *_rest in CELLS:
        hits = [r for r in rows if needle in (r.get("tag") or "")]
        if hits:
            out[key] = hits[-1]
    return out


def stat(row: dict, name: str) -> float:
    return pct(row["stats"].get(name))


def row_line(label: str, r: dict) -> str:
    return (f"{label:34s} {int(pct(r['stats']['Total Orders'])):>7,d} "
            f"{stat(r, 'Compounding Annual Return'):>8.3f} {stat(r, 'Sharpe Ratio'):>7.3f} "
            f"{stat(r, 'Drawdown'):>7.1f} {stat(r, 'Annual Standard Deviation'):>6.3f} "
            f"{stat(r, 'Probabilistic Sharpe Ratio'):>6.1f} "
            f"{r['stats'].get('Total Fees', ''):>10s}")


HEAD = (f"{'cell':34s} {'orders':>7s} {'CAR%':>8s} {'Sharpe':>7s} {'MaxDD%':>7s} "
        f"{'std':>6s} {'PSR%':>6s} {'fees':>10s}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    got = resolve(ledger_rows())
    if args.list:
        for key, label, needle, *_ in CELLS:
            r = got.get(key)
            print(f"{key:16s} {label:34s} -> "
                  f"{r['run_dir'] if r else 'MISSING (run scripts/_s18_runs.sh)'}")
        return 0
    missing = [k for k, *_ in CELLS if k not in got]
    if missing:
        print(f"missing cells: {missing}  -> run scripts/_s18_runs.sh", file=sys.stderr)

    # 1. Head to head at each spread, full period and both halves.
    for bps in (0.0, 2.0):
        print(f"\n### Head to head at {bps:.0f} bp of spread\n")
        print(HEAD)
        for period in ("full", "is", "oos"):
            pair = [k for k, _l, _n, p, b, w in CELLS
                    if p == period and b == bps and w in ("champion", "candidate")]
            for key in sorted(pair, key=lambda k: dict((c[0], c[5]) for c in CELLS)[k]):
                if key in got:
                    print(row_line(LABEL[key], got[key]))
            if len(pair) == 2 and all(k in got for k in pair):
                champ = next(k for k in pair if dict((c[0], c[5]) for c in CELLS)[k] == "champion")
                cand = next(k for k in pair if k != champ)
                d_car = (stat(got[cand], "Compounding Annual Return")
                         - stat(got[champ], "Compounding Annual Return"))
                d_sh = stat(got[cand], "Sharpe Ratio") - stat(got[champ], "Sharpe Ratio")
                d_dd = stat(got[cand], "Drawdown") - stat(got[champ], "Drawdown")
                print(f"{'  -> candidate minus champion':34s} {'':>7s} {d_car:>+8.3f} "
                      f"{d_sh:>+7.3f} {d_dd:>+7.1f}\n")

    # 2. Paired daily statistics, candidate minus champion, within each window and spread.
    sessions = trading_days()
    curves = {}
    for key in got:
        try:
            curves[key] = equity_curve(REPO / got[key]["run_dir"], sessions)
        except Exception as exc:                                    # noqa: BLE001
            print(f"  (no equity curve for {key}: {exc})", file=sys.stderr)

    print("\n### Paired daily log returns, candidate minus champion, same window and spread\n")
    print(f"{'window':>8s} {'spread':>7s} {'bps/day':>8s} {'t':>7s} {'ann.%':>7s} {'n':>6s}")
    for period in ("full", "is", "oos"):
        for bps in (0.0, 2.0):
            cand = next((k for k, _l, _n, p, b, w in CELLS
                         if p == period and b == bps and w == "candidate"), None)
            champ = next((k for k, _l, _n, p, b, w in CELLS
                          if p == period and b == bps and w == "champion"), None)
            if cand in curves and champ in curves:
                d, t, n = paired(daily_log_returns(curves[cand]), daily_log_returns(curves[champ]))
                print(f"{period:>8s} {bps:>6.0f}bp {d:>8.2f} {t:>7.2f} {d * 252 / 100:>7.2f} {n:>6d}")
    print("\n  A t near zero is the expected reading and not a failure: the case for this cell\n"
          "  was never that it earns more. It is that it earns the same with less risk, less\n"
          "  leverage and less commission.")

    # 3. The band, measured on the candidate rather than on the champion.
    print("\n### The no-trade band on the candidate's own book\n")
    print(HEAD)
    for key in ("cand_full_sl0", "cand_band03_sl0", "cand_full_sl2", "cand_band03_sl2"):
        if key in got:
            print(row_line(LABEL[key], got[key]))
    for bps, base, wide in ((0.0, "cand_full_sl0", "cand_band03_sl0"),
                            (2.0, "cand_full_sl2", "cand_band03_sl2")):
        if base in curves and wide in curves:
            d, t, n = paired(daily_log_returns(curves[wide]), daily_log_returns(curves[base]))
            d_car = (stat(got[wide], "Compounding Annual Return")
                     - stat(got[base], "Compounding Annual Return"))
            print(f"  band 0.03 minus 0.01 at {bps:.0f} bp: {d_car:+.3f} CAR, "
                  f"{d:+.2f} bps/day, t {t:+.2f}, n {n}")
    print("\n  S-17 measured +0.57 CAR (t +1.22) for this band on the *champion*, whose 4,735\n"
          "  orders include a 3x sleeve that re-weights on every vol drift. The candidate\n"
          "  already trades a cheaper book, so the same band buys far less here.")

    # 4. The promotion arithmetic, stated in the two columns champion.json will record.
    print("\n### Promotion arithmetic (the rules in research/champion.json)\n")
    for bps, champ, cand in ((0.0, "champ_full_sl0", "cand_full_sl0"),
                             (2.0, "champ_full_sl2", "cand_full_sl2")):
        if champ not in got or cand not in got:
            continue
        c, k = got[cand], got[champ]
        car_ok = stat(c, "Compounding Annual Return") > stat(k, "Compounding Annual Return")
        sh_ok = stat(c, "Sharpe Ratio") >= stat(k, "Sharpe Ratio") - 0.03
        dd_ok = stat(c, "Drawdown") <= stat(k, "Drawdown") + 1.0
        abs_ok = stat(c, "Drawdown") <= 35.0
        print(f"  at {bps:.0f} bp: CAR {'PASS' if car_ok else 'FAIL'} "
              f"({stat(c, 'Compounding Annual Return'):.3f} vs "
              f"{stat(k, 'Compounding Annual Return'):.3f}), "
              f"Sharpe {'PASS' if sh_ok else 'FAIL'} ({stat(c, 'Sharpe Ratio'):.3f} vs "
              f"{stat(k, 'Sharpe Ratio'):.3f}), DD {'PASS' if dd_ok else 'FAIL'} "
              f"({stat(c, 'Drawdown'):.1f} vs {stat(k, 'Drawdown'):.1f}), "
              f"cap {'PASS' if abs_ok else 'FAIL'}  ->  "
              f"{'BEATS champion' if all((car_ok, sh_ok, dd_ok, abs_ok)) else 'refused'}")
    print("\n  The 0 bp column is LEAN's default cost model and charges nothing per order; the\n"
          "  2 bp column is the honest one (S-17: the hard floor of a half-cent tick is\n"
          "  0.27-0.77 bp on these names, and the crossover between the two books is 0.03 bp).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
