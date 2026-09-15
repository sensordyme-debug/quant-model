"""The last candidate: is directional efficiency an INVERTED-U in forecast volatility?

WHY THIS WAS NEARLY MISSED
---------------------------
Every test so far has been a rank correlation, which measures a monotone relationship. The
path-shape table shows something a monotone test is blind to. Pooled across instruments,
median efficiency by forecast-volatility quintile runs:

    ETF       0.447   0.465   0.485   0.514   0.482      peak at Q4
    FUTURES   0.434   0.536   0.514   0.483   0.394      peak at Q2

Both rise and then fall. A Spearman coefficient on that shape is near zero, and near zero is
exactly what Phase 2 reported. If the shape is real, the linear tests were asking the wrong
question.

THE MECHANISM THIS WOULD IMPLY
--------------------------------
It is a plausible story rather than a fitted curve, and it is worth stating before the test so
the test can contradict it. Very quiet sessions have no information to price and drift
aimlessly inside a narrow range: low efficiency because there is no move to make. Very violent
sessions are two-sided - disagreement, repricing, forced liquidation - and reverse repeatedly:
low efficiency because the move keeps being undone. In between sits a session with enough
information to move and enough consensus to move one way.

The futures panel supports the story at its extremes: the top quintile has the most direction
changes (11.4 versus 9.0 in Q2), the lowest efficiency (0.394 versus 0.536) and the highest
share of two-sided chop (44.1% versus 26.8%).

HOW IT IS TESTED, AND THE TRAP AVOIDED
----------------------------------------
Fitting a quadratic and reporting its p-value would be too easy: a quadratic has an extra
degree of freedom and will bend toward any wiggle in the data. Three defences:

  1. The SAME search/holdout split as the linear search. The curvature coefficient must be
     estimated on the first 70% and hold its sign and significance on the last 30%.
  2. The peak LOCATION must be stable. A real inverted-U puts its maximum in roughly the same
     place in both halves; a fitted wiggle moves it wherever the noise is.
  3. A monotone alternative must be beaten out of sample. If a straight line does as well on
     held-out data, the curvature is decoration.

Only if all three hold is there anything here. The prior, after everything else in this
programme, is that they will not.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from efficiency_volatility import prepare  # noqa: E402

SPLIT = 0.70
TARGETS = ("eff_range", "eff_vol", "eff_mfe")


def fit_quadratic(x: np.ndarray, y: np.ndarray) -> dict:
    """OLS on [1, z, z^2] with z the standardised predictor. Returns coefficients and t."""
    m = np.isfinite(x) & np.isfinite(y)
    x, y = x[m], y[m]
    n = len(x)
    if n < 80:
        return {"n": n, "b1": np.nan, "b2": np.nan, "t2": np.nan, "peak_z": np.nan,
                "r2": np.nan}
    z = (x - x.mean()) / (x.std() if x.std() > 0 else 1.0)
    X = np.column_stack([np.ones(n), z, z ** 2])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    dof = n - 3
    s2 = float(resid @ resid) / dof
    cov = s2 * np.linalg.pinv(X.T @ X)
    t2 = beta[2] / np.sqrt(cov[2, 2]) if cov[2, 2] > 0 else np.nan
    peak = -beta[1] / (2 * beta[2]) if beta[2] != 0 else np.nan
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return {"n": n, "b1": float(beta[1]), "b2": float(beta[2]), "t2": float(t2),
            "peak_z": float(peak), "r2": 1.0 - float(resid @ resid) / ss_tot
            if ss_tot > 0 else np.nan}


def oos_sse(xs: np.ndarray, ys: np.ndarray, xh: np.ndarray, yh: np.ndarray,
            degree: int) -> float:
    """Fit on the search half, score sum of squared error on the holdout half."""
    ms = np.isfinite(xs) & np.isfinite(ys)
    mh = np.isfinite(xh) & np.isfinite(yh)
    if ms.sum() < 80 or mh.sum() < 40:
        return np.nan
    xs2, ys2, xh2, yh2 = xs[ms], ys[ms], xh[mh], yh[mh]
    mu, sd = xs2.mean(), xs2.std() or 1.0
    zs, zh = (xs2 - mu) / sd, (xh2 - mu) / sd
    Xs = np.column_stack([np.ones(len(zs))] + [zs ** k for k in range(1, degree + 1)])
    Xh = np.column_stack([np.ones(len(zh))] + [zh ** k for k in range(1, degree + 1)])
    beta, *_ = np.linalg.lstsq(Xs, ys2, rcond=None)
    return float(((yh2 - Xh @ beta) ** 2).sum())


def main() -> int:
    panels = {
        "ETF": prepare(pd.read_parquet(REPO / "research" / "efficiency_etf.parquet"), "etf"),
        "FUTURES": prepare(
            pd.read_parquet(REPO / "research" / "efficiency_futures.parquet"), "futures"),
    }

    print("=" * 106)
    print("IS DIRECTIONAL EFFICIENCY AN INVERTED-U IN FORECAST VOLATILITY?")
    print("A real inverted-U needs b2 < 0, stable across the split, with a stable peak,")
    print("and must beat a straight line on held-out data.")
    print("=" * 106)

    rows = []
    for name, p in panels.items():
        print(f"\n--- {name} " + "-" * 92)
        print(f"{'sym':5} {'target':10} {'n_s':>5} {'b2 search':>10} {'t2 search':>10} "
              f"{'b2 hold':>9} {'t2 hold':>9} {'peak_s':>7} {'peak_h':>7} "
              f"{'OOS quad<lin':>13}")
        for sym, g in p.groupby("symbol"):
            g = g.sort_values("tdate").reset_index(drop=True)
            cut = int(len(g) * SPLIT)
            s, h = g.iloc[:cut], g.iloc[cut:]
            for tgt in TARGETS:
                xs = s["fc_vol"].to_numpy(dtype=float)
                ys = s[tgt].to_numpy(dtype=float)
                xh = h["fc_vol"].to_numpy(dtype=float)
                yh = h[tgt].to_numpy(dtype=float)
                fs, fh = fit_quadratic(xs, ys), fit_quadratic(xh, yh)
                sse1 = oos_sse(xs, ys, xh, yh, 1)
                sse2 = oos_sse(xs, ys, xh, yh, 2)
                better = (np.isfinite(sse1) and np.isfinite(sse2) and sse2 < sse1)
                rows.append({"panel": name, "symbol": sym, "target": tgt,
                             "b2_search": fs["b2"], "t2_search": fs["t2"],
                             "b2_hold": fh["b2"], "t2_hold": fh["t2"],
                             "peak_search": fs["peak_z"], "peak_hold": fh["peak_z"],
                             "oos_quad_better": better, "n_search": fs["n"]})
                print(f"{sym:5} {tgt:10} {fs['n']:5d} {fs['b2']:10.5f} {fs['t2']:10.2f} "
                      f"{fh['b2']:9.5f} {fh['t2']:9.2f} {fs['peak_z']:7.2f} "
                      f"{fh['peak_z']:7.2f} {'yes' if better else 'no':>13}")

    out = pd.DataFrame(rows)
    out.to_csv(REPO / "research" / "efficiency_nonlinear.csv", index=False)

    print("\n" + "=" * 106)
    print("VERDICT")
    print("=" * 106)
    n = len(out)
    neg_s = out.b2_search < 0
    neg_both = neg_s & (out.b2_hold < 0)
    sig_s = out.t2_search.abs() > 1.96
    sig_both = sig_s & (out.t2_hold.abs() > 1.96) & neg_both
    peak_stable = (out.peak_search - out.peak_hold).abs() < 1.0
    print(f"  cells tested                                    {n}")
    print(f"  curvature NEGATIVE in search (inverted-U)       {int(neg_s.sum())}")
    print(f"  negative in BOTH halves                         {int(neg_both.sum())}")
    print(f"  significant in both halves AND negative in both {int(sig_both.sum())}")
    print(f"  peak location stable (within 1 sd)              {int(peak_stable.sum())}")
    print(f"  quadratic beats a line OUT OF SAMPLE            "
          f"{int(out.oos_quad_better.sum())} of {n}")
    full = sig_both & peak_stable & out.oos_quad_better
    print(f"\n  cells passing ALL THREE criteria                {int(full.sum())}")
    if full.any():
        print("\n  survivors:")
        for _, r in out[full].iterrows():
            print(f"    {r['panel']:8} {r['symbol']:5} {r['target']:10} "
                  f"b2_s={r['b2_search']:+.5f} t2_s={r['t2_search']:+.2f} "
                  f"b2_h={r['b2_hold']:+.5f} t2_h={r['t2_hold']:+.2f}")
    else:
        print("\n  NONE. The inverted-U seen in the quintile table does not survive a")
        print("  split-half test with a stable peak and an out-of-sample comparison")
        print("  against a straight line.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
