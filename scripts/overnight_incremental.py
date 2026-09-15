"""Does the overnight session tell us anything YESTERDAY did not already say?

WHY THE SURVIVING RESULT IS NOT YET A FINDING
---------------------------------------------
Two hypotheses survived Bonferroni on all four instruments at t between 5.6 and 7.7:
overnight range predicts the regular session's range, and overnight volume does too. Those
are large, consistent, and exactly what anyone would expect.

Which is the problem. Volatility is autocorrelated at every horizon anybody has ever
measured, so "a volatile overnight precedes a volatile day" may be nothing more than "a
volatile week is a volatile week". If that is all it is, the overnight session is not an
information source - it is a thermometer reading the same weather as yesterday's close, and
a forecast built on yesterday's range alone would do the same work without staying up.

THE TEST
--------
Regress today's regular-session range on yesterday's regular-session range, then ask whether
adding the overnight session's range improves the fit out of sample. The comparison is
nested, so the only honest measures are the incremental R-squared and the t on the added
coefficient, both computed on data the coefficients were not fitted to.

Fitting is expanding-window and strictly causal: the forecast for day k uses coefficients
estimated on days 1..k-1 only. A single in-sample R-squared would answer a different and
much easier question.

WHY IT MATTERS EVEN THOUGH IT IS NOT DIRECTIONAL
-------------------------------------------------
A range forecast cannot tell you which way to bet, so on its own it earns nothing. What it
can do is size and gate: a Combine dies from a $2,000 trailing drawdown far more often than
it dies from a bad direction, and knowing at 09:29 that today is likely to be a wide day is
a risk input even when it is not a return input. So the question is worth settling properly
rather than dismissing - but it must be settled as a risk finding, and never quietly promoted
into a claim about returns.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

MIN_TRAIN = 60          # days before the first out-of-sample forecast is made


def _ols(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    return np.linalg.lstsq(X, y, rcond=None)[0]


def walk_forward(df: pd.DataFrame, features: list[str], target: str) -> np.ndarray:
    """Strictly causal one-step-ahead forecasts. Returns NaN before MIN_TRAIN."""
    X = np.column_stack([np.ones(len(df))] + [df[f].to_numpy(dtype=float) for f in features])
    y = df[target].to_numpy(dtype=float)
    pred = np.full(len(df), np.nan)
    for k in range(MIN_TRAIN, len(df)):
        Xt, yt = X[:k], y[:k]
        m = np.isfinite(yt) & np.isfinite(Xt).all(axis=1)
        if m.sum() < MIN_TRAIN or not np.isfinite(X[k]).all():
            continue
        try:
            beta = _ols(Xt[m], yt[m])
        except np.linalg.LinAlgError:
            continue
        pred[k] = float(X[k] @ beta)
    return pred


def oos_r2(y: np.ndarray, pred: np.ndarray, bench: np.ndarray) -> float:
    """R-squared of the model against a benchmark forecast, on the shared valid rows."""
    m = np.isfinite(y) & np.isfinite(pred) & np.isfinite(bench)
    if m.sum() < 30:
        return np.nan
    sse = float(np.sum((y[m] - pred[m]) ** 2))
    ssb = float(np.sum((y[m] - bench[m]) ** 2))
    return 1.0 - sse / ssb if ssb > 0 else np.nan


def main() -> int:
    from overnight_hypotheses import futures_features

    fut = futures_features(pd.read_parquet(REPO / "research" / "overnight_panel.parquet"))
    fut = fut.sort_values(["symbol", "tdate"])

    print("=" * 94)
    print("DOES OVERNIGHT ADD TO YESTERDAY? out-of-sample, expanding window, causal")
    print("=" * 94)
    print("target: today's regular-session range, as a percentage of the open\n")
    print(f"{'sym':5} {'n_oos':>6} {'R2 vs mean':>11} {'R2 prev-day':>12} "
          f"{'R2 +overnight':>14} {'incremental':>12} {'t(beta_on)':>11}")

    for sym, g in fut.groupby("symbol"):
        g = g.copy()
        g["prev_range"] = g["rth_range_pct"].shift(1)
        g["prev_absret"] = g["rth_abs_ret_pct"].shift(1)
        g = g.dropna(subset=["rth_range_pct", "prev_range", "on_range_pct"]).reset_index(drop=True)
        y = g["rth_range_pct"].to_numpy(dtype=float)

        # Benchmark 0: the expanding mean, i.e. no model at all.
        mean_pred = np.full(len(g), np.nan)
        for k in range(MIN_TRAIN, len(g)):
            mean_pred[k] = float(np.nanmean(y[:k]))

        p_prev = walk_forward(g, ["prev_range", "prev_absret"], "rth_range_pct")
        p_both = walk_forward(g, ["prev_range", "prev_absret", "on_range_pct", "on_volume_z"],
                              "rth_range_pct")

        r2_mean = oos_r2(y, mean_pred, mean_pred)          # zero by construction, printed as 0
        r2_prev = oos_r2(y, p_prev, mean_pred)
        r2_both = oos_r2(y, p_both, mean_pred)
        incr = oos_r2(y, p_both, p_prev)                   # against prev-day as the benchmark

        # In-sample t on the overnight coefficients, with the previous day already in.
        m = np.isfinite(g[["prev_range", "prev_absret", "on_range_pct", "on_volume_z"]]).all(axis=1)
        gg = g[m]
        X = np.column_stack([np.ones(len(gg)), gg["prev_range"], gg["prev_absret"],
                             gg["on_range_pct"], gg["on_volume_z"]]).astype(float)
        yy = gg["rth_range_pct"].to_numpy(dtype=float)
        beta = _ols(X, yy)
        resid = yy - X @ beta
        s2 = float(resid @ resid) / (len(yy) - X.shape[1])
        cov = s2 * np.linalg.pinv(X.T @ X)
        t_on = beta[3] / np.sqrt(cov[3, 3])

        print(f"{sym:5} {int(np.isfinite(p_both).sum()):6d} {r2_mean:11.3f} {r2_prev:12.3f} "
              f"{r2_both:14.3f} {incr:12.3f} {t_on:11.2f}")

    print("\n" + "=" * 94)
    print("AND THE SAME QUESTION FOR DIRECTION, WHICH IS THE ONE THAT WOULD PAY")
    print("=" * 94)
    print("target: today's regular-session RETURN (signed), same causal protocol\n")
    print(f"{'sym':5} {'n_oos':>6} {'R2 vs mean':>11} {'best feature set':>18}")
    for sym, g in fut.groupby("symbol"):
        g = g.copy()
        g["prev_ret"] = g["rth_ret_pct"].shift(1)
        g = g.dropna(subset=["rth_ret_pct", "prev_ret", "on_ret_pct"]).reset_index(drop=True)
        y = g["rth_ret_pct"].to_numpy(dtype=float)
        mean_pred = np.full(len(g), np.nan)
        for k in range(MIN_TRAIN, len(g)):
            mean_pred[k] = float(np.nanmean(y[:k]))
        feats = ["on_ret_pct", "gap_pct", "on_close_loc", "on_persistence",
                 "on_range_pct", "prev_ret"]
        g2 = g.dropna(subset=feats).reset_index(drop=True)
        y2 = g2["rth_ret_pct"].to_numpy(dtype=float)
        mp2 = np.full(len(g2), np.nan)
        for k in range(MIN_TRAIN, len(g2)):
            mp2[k] = float(np.nanmean(y2[:k]))
        p = walk_forward(g2, feats, "rth_ret_pct")
        print(f"{sym:5} {int(np.isfinite(p).sum()):6d} {oos_r2(y2, p, mp2):11.3f} "
              f"{'all overnight':>18}")

    print("\nA negative out-of-sample R-squared means the model forecasts the direction WORSE")
    print("than assuming the historical average, which is the expected result when the true")
    print("coefficients are zero and the fitting is honest.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
