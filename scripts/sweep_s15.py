#!/usr/bin/env python
"""S-15: where does the champion's 24.4% CAR actually come from?

S-14 measured the ranker's cross-sectional contribution at +2.02 bps/day (t = 2.07) and
that raised the obvious question nobody had priced: the loop has spent S-9 through S-14
tuning the ranker, so how much of the book's return is the ranker at all?

The strategy's own docstring says the pieces are separable - "momentum picks *what*, the
regime filter decides *whether*, the vol target and drawdown overlay decide *how much*" -
and every piece is reachable through an `S1_*` environment override, so each cell is the
shipped algorithm with one switch removed. `scripts/_s15_runs.sh` produces the runs; this
script reads their LEAN output and prints the attribution.

    python scripts/sweep_s15.py                 # table + paired daily statistics
    python scripts/sweep_s15.py --list          # which run each cell resolved to

Two numbers per cell, and they answer different questions:

  * **CAR delta** - what removing the switch does to the compounded result. This is the
    honest "what would the book have earned", but it is one path, so it carries the path
    scatter S-13 measured at +/-0.3 CAR.
  * **paired daily log-return difference and its t** - the same comparison made on 3,700
    daily observations instead of one terminal value. Both books are marked every session
    by LEAN, so the difference is a paired sample and its standard error is meaningful.

Nothing here promotes or refuses anything: S-15's output is a table and a sentence about
where the return comes from.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
LEDGER = REPO / "research" / "experiments.jsonl"
TRADING_DAYS = 252

#: cell -> (label, the substring that identifies its row in the ledger tag)
CELLS = [
    ("control", "champion (S-12, shipped)", "S-15 attribution control"),
    ("a_noskill", "(a) no ranking (top 9, equal)", "S-15 attribution (a) "),
    ("a2_volmatched", "(a2) no ranking, vol-matched", "S-15 attribution (a2)"),
    ("b_noregime", "(b) regime filter off", "S-15 attribution (b)"),
    ("d_equal", "(d) allocation tilt off", "S-15 attribution (d)"),
    ("e_noproxy", "(e) levered proxies off", "S-15 attribution (e)"),
    ("g_nodd", "(g) drawdown overlay off", "S-15 attribution (g)"),
    ("f_beta", "(f) no skill at all", "S-15 attribution (f)"),
]

STATS = ["Total Orders", "Compounding Annual Return", "Sharpe Ratio", "Drawdown",
         "Annual Standard Deviation", "Total Fees", "Probabilistic Sharpe Ratio"]


def ledger_rows() -> list[dict]:
    rows = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def resolve(rows: list[dict]) -> dict[str, dict]:
    """Latest ledger row per cell. Latest, so a re-run supersedes without editing this file."""
    out = {}
    for key, _label, needle in CELLS:
        hits = [r for r in rows if needle in (r.get("tag") or "")]
        if hits:
            out[key] = hits[-1]
    return out


def pct(value) -> float:
    if value is None:
        return float("nan")
    return float(str(value).replace("%", "").replace("$", "").replace(",", ""))


def _series(payload: dict, chart: str, series: str) -> pd.Series:
    values = payload["charts"][chart]["series"][series]["values"]
    width = len(values[0])
    frame = pd.DataFrame(values, columns=["ts", "open", "high", "low", "close"][:width])
    frame["date"] = pd.to_datetime(frame["ts"], unit="s").dt.date
    return frame.groupby("date")[frame.columns[-2]].last()


def trading_days() -> set:
    """The real NYSE sessions in the sample, taken from LEAN's own SPY daily bars.

    LEAN marks the book on every *calendar* day, so the equity chart carries ~1,670
    weekend and holiday rows with a zero return; pooling those into a paired daily mean
    would divide the per-day edge by 1.45. The chart's own Benchmark series cannot be used
    to find the sessions - it is plotted one day late and repeats values - so the calendar
    comes from the bars the algorithm actually traded on.
    """
    sys.path.insert(0, str(REPO / "scripts"))
    import lean_prices                                     # noqa: E402  (path set above)
    return set(lean_prices.load_closes(["SPY"]).index.date)


def equity_curve(run_dir: Path, sessions: set) -> pd.Series:
    """Strategy equity on trading days only, indexed by date."""
    result = next((c for c in sorted(run_dir.glob("*.json"))
                   if not any(x in c.name for x in
                              ("summary", "order-events", "data-monitor"))), None)
    if result is None:
        raise SystemExit(f"no LEAN result json in {run_dir}")
    payload = json.loads(result.read_text(encoding="utf-8"))
    equity = _series(payload, "Strategy Equity", "Equity")
    return equity[[d in sessions for d in equity.index]]


def daily_log_returns(curve: pd.Series) -> pd.Series:
    return np.log(curve.astype(float)).diff().dropna()


def paired(a: pd.Series, b: pd.Series) -> tuple[float, float, int]:
    """(mean difference in bps/day, t, n) of `a - b` over the days both books are marked."""
    joined = pd.concat([a, b], axis=1, join="inner").dropna()
    diff = joined.iloc[:, 0] - joined.iloc[:, 1]
    n = len(diff)
    if n < 2:
        return float("nan"), float("nan"), n
    se = diff.std(ddof=1) / math.sqrt(n)
    return float(diff.mean() * 1e4), float(diff.mean() / se) if se > 0 else float("nan"), n


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
            print(f"  {key:<11} {label:<32} {row['ts'] if row else 'MISSING'}")
        if missing:
            print(f"\nmissing cells: {', '.join(missing)} - run scripts/_s15_runs.sh")
        if args.list:
            return 0
        return 1

    sessions = trading_days()
    curves = {k: daily_log_returns(equity_curve(REPO / rows[k]["run_dir"], sessions))
              for k in rows}
    base = curves["control"]
    base_car = pct(rows["control"]["stats"]["Compounding Annual Return"])

    print("=== S-15 attribution: the champion with one switch removed, full period ===\n")
    header = (f"{'cell':<32}{'orders':>8}{'CAR%':>9}{'dCAR':>8}{'Sharpe':>8}"
              f"{'MaxDD%':>8}{'std':>7}{'fees$':>10}{'PSR%':>7}")
    print(header)
    print("-" * len(header))
    for key, label, _needle in CELLS:
        stats = rows[key]["stats"]
        car = pct(stats["Compounding Annual Return"])
        d = "" if key == "control" else f"{car - base_car:+8.2f}"
        print(f"{label:<32}{int(pct(stats['Total Orders'])):>8}{car:>9.3f}{d:>8}"
              f"{pct(stats['Sharpe Ratio']):>8.3f}{pct(stats['Drawdown']):>8.1f}"
              f"{pct(stats['Annual Standard Deviation']):>7.3f}"
              f"{pct(stats['Total Fees']):>10,.0f}"
              f"{pct(stats['Probabilistic Sharpe Ratio']):>7.1f}")

    print("\n=== paired daily log returns, champion minus cell (what the switch is worth) ===\n")
    head2 = (f"{'switch removed':<32}{'bps/day':>10}{'t':>8}{'days':>8}{'ann.%':>9}"
             f"{'IS bps':>9}{'IS t':>7}{'OOS bps':>9}{'OOS t':>7}")
    print(head2)
    print("-" * len(head2))
    # S-12's recorded halves, so the split is the one the champion was promoted on rather
    # than a new one chosen here.
    split = pd.Timestamp("2020-01-01").date()
    for key, label, _needle in CELLS:
        if key == "control":
            continue
        bps, t, n = paired(base, curves[key])
        ann = (math.exp(bps / 1e4 * TRADING_DAYS) - 1.0) * 100.0
        is_bps, is_t, _ = paired(base[base.index < split], curves[key][curves[key].index < split])
        oos_bps, oos_t, _ = paired(base[base.index >= split], curves[key][curves[key].index >= split])
        print(f"{label:<32}{bps:>10.2f}{t:>8.2f}{n:>8}{ann:>9.2f}"
              f"{is_bps:>9.2f}{is_t:>7.2f}{oos_bps:>9.2f}{oos_t:>7.2f}")

    print("\n  Read: a positive number is what the champion earns *because* the switch is on.")
    print("  The t is on 3,689 paired trading days; the CAR delta is one path and carries "
          "S-13's +/-0.3 scatter.")
    print("  IS = 2012-2019, OOS = 2020-2026, the halves S-12 was promoted on.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
