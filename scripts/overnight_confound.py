"""The confound test: is the futures result about futures, or about the fifteen months it covers?

WHY THIS TEST DECIDES THE SECTION
---------------------------------
Measured on the futures store, holding only the overnight session has an annualised Sharpe of
1.68 on ES against 1.17 for buy and hold - a ratio of 1.44, which reads as a real improvement
on beta. Measured on ten years of SPY the same construction has a ratio of 0.92, which reads
as beta made slightly worse.

Both cannot be a fact about the overnight session. Either futures behave differently from the
ETF that tracks the same index - implausible, since ES and SPY are arbitraged to within a
basis point - or one of the two samples is unrepresentative. The futures store covers
2025-06 to 2026-09, and it was chosen by what a data vendor happened to hand us, not by
anything about the market.

The test is therefore trivial and conclusive: restrict SPY and QQQ to the futures store's own
date range and recompute. If the ratio jumps from 0.92 to something near 1.44, the finding
belongs to the calendar, not to the instrument, and the futures store cannot speak to it.

A NOTE ON WHY THIS IS THE FIRST THING TO RUN
--------------------------------------------
Every hypothesis in the rest of the brief - the ten overnight-to-open mechanisms, the
cross-market work, the volatility conditioning - will be estimated on those same 312 days. If
those 312 days are an unusual sample for the single most basic quantity in the study, that is
a fact every later result has to be read against, and it is cheaper to learn it now than
after fifty hypotheses have been tested on it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from overnight_replicate import _stats  # noqa: E402


def bootstrap_ratio_ci(on: np.ndarray, bh: np.ndarray, n_boot: int = 10_000,
                       seed: int = 20260914) -> tuple[float, float]:
    """A confidence interval for the Sharpe ratio of ratios, by paired resampling.

    Paired, because the two legs are the same sessions: resampling them independently would
    destroy the correlation that makes the comparison meaningful in the first place.
    """
    rng = np.random.default_rng(seed)
    n = len(on)
    out = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, n)
        a, b = on[idx], bh[idx]
        sa = np.mean(a) / np.std(a, ddof=1) if np.std(a, ddof=1) > 0 else np.nan
        sb = np.mean(b) / np.std(b, ddof=1) if np.std(b, ddof=1) > 0 else np.nan
        out[i] = sa / sb if sb not in (0, np.nan) else np.nan
    out = out[np.isfinite(out)]
    return float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))


def main() -> int:
    fut = pd.read_parquet(REPO / "research" / "overnight_panel.parquet")
    etf = pd.read_parquet(REPO / "research" / "etf_overnight_panel.parquet")
    etf["tdate"] = pd.to_datetime(etf["tdate"])

    lo, hi = pd.Timestamp("2025-06-09"), pd.Timestamp("2026-09-10")

    print("=" * 88)
    print("THE SAME CONSTRUCTION, THE SAME ETFs, TWO DIFFERENT DATE RANGES")
    print("=" * 88)
    print(f"{'sym':5} {'period':22} {'n':>5} {'ON mean%':>9} {'ON t':>6} "
          f"{'Sh ON':>6} {'Sh B&H':>7} {'ratio':>6}  95% CI on ratio")
    for sym, g in etf.groupby("symbol"):
        for label, sub in (("2016-01 .. 2026-09 (all)", g),
                           ("2025-06 .. 2026-09 (fut)", g[(g.tdate >= lo) & (g.tdate <= hi)])):
            on = sub["on_ret_pct"].to_numpy()
            bh = sub["day_ret_pct"].to_numpy()
            so, sb = _stats(on), _stats(bh)
            ratio = so["sharpe_ann"] / sb["sharpe_ann"]
            clo, chi = bootstrap_ratio_ci(on, bh)
            print(f"{sym:5} {label:22} {so['n']:5d} {so['mean_pct']:9.4f} {so['t']:6.2f} "
                  f"{so['sharpe_ann']:6.2f} {sb['sharpe_ann']:7.2f} {ratio:6.2f}  "
                  f"[{clo:.2f}, {chi:.2f}]")
        print()

    print("=" * 88)
    print("THE FUTURES, FOR SIDE-BY-SIDE COMPARISON OVER THE IDENTICAL DATES")
    print("=" * 88)
    print(f"{'sym':5} {'n':>5} {'ON mean%':>9} {'ON t':>6} {'Sh ON':>6} {'Sh B&H':>7} "
          f"{'ratio':>6}  95% CI on ratio")
    for sym, g in fut.groupby("symbol"):
        on = g["on_ret_pct"].to_numpy()
        bh = (g["on_ret_pct"] + g["gap_pct"] + g["rth_ret_pct"]).to_numpy()
        so, sb = _stats(on), _stats(bh)
        clo, chi = bootstrap_ratio_ci(on, bh)
        print(f"{sym:5} {so['n']:5d} {so['mean_pct']:9.4f} {so['t']:6.2f} "
              f"{so['sharpe_ann']:6.2f} {sb['sharpe_ann']:7.2f} "
              f"{so['sharpe_ann'] / sb['sharpe_ann']:6.2f}  [{clo:.2f}, {chi:.2f}]")

    print("\n" + "=" * 88)
    print("HOW UNUSUAL IS THE FUTURES WINDOW? every 312-session block of SPY since 2016")
    print("=" * 88)
    spy = etf[etf.symbol == "SPY"].reset_index(drop=True)
    w = 312
    ratios, on_ts = [], []
    for i in range(0, len(spy) - w):
        s = spy.iloc[i:i + w]
        on, bh = s["on_ret_pct"].to_numpy(), s["day_ret_pct"].to_numpy()
        sa = np.mean(on) / np.std(on, ddof=1)
        sb = np.mean(bh) / np.std(bh, ddof=1)
        if sb != 0:
            ratios.append(sa / sb)
            on_ts.append(np.mean(on) / (np.std(on, ddof=1) / np.sqrt(w)))
    ratios, on_ts = np.array(ratios), np.array(on_ts)
    ratios = ratios[np.isfinite(ratios)]
    obs_ratio = 1.44   # ES, from above
    print(f"rolling 312-day Sharpe ratio (overnight / buy-and-hold), n={len(ratios)} windows")
    for q in (5, 25, 50, 75, 95):
        print(f"  p{q:<3} {np.percentile(ratios, q):7.2f}")
    print(f"  ES observed value {obs_ratio:.2f} sits at percentile "
          f"{(ratios < obs_ratio).mean():.1%} of SPY's own history")
    print(f"\n  fraction of 312-day windows where overnight-only beats buy-and-hold "
          f"risk-adjusted: {(ratios > 1).mean():.1%}")
    print(f"  fraction where the overnight mean itself clears |t| > 1.96: "
          f"{(np.abs(on_ts) > 1.96).mean():.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
