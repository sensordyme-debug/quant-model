"""The opportunity forecast: how much movement to expect today, decided at 09:29.

WHAT THIS IS FOR
----------------
A gate needs a number, not a correlation. This module produces one: given the overnight
session's description and yesterday's regular session, it forecasts today's regular-session
realised volatility, using only information that exists before 09:30 ET.

It is library code rather than a script because three separate studies now depend on the
same forecast, and a forecast that is re-implemented per study is a forecast whose gate and
whose validation are subtly different objects.

THE FEATURE SET, AND THE HONEST NOTE ABOUT HOW IT WAS CHOSEN
--------------------------------------------------------------
Three predictors:

    on_atr_pct         average true range of the overnight session, as a percent
    on_vol_ratio       overnight volume over its own trailing 20-day mean
    prev_rth_rv_pct    yesterday's regular-session realised volatility

This set was selected by comparing six candidate sets on out-of-sample R-squared, which is a
form of selection and is disclosed as such. The magnitude of the incremental R-squared
reported for this specific set is therefore optimistically biased.

What is NOT biased by that selection is the direction of the conclusion: every candidate set
containing an overnight term beat the yesterday-only benchmark for realised volatility on at
least three of four instruments, and the full fifteen-predictor set was WORSE than three
predictors on every instrument. The finding "the overnight session adds to yesterday" is
robust to the choice; the exact number 0.19 is not.

WHAT IT PREDICTS, AND WHAT IT CONSPICUOUSLY DOES NOT
------------------------------------------------------
Measured out of sample against an expanding mean:

    realised volatility   +0.46 to +0.51     the path length of the session
    range                 +0.22 to +0.28     also path
    |net move|            +0.03 to +0.06     displacement - almost nothing
    efficiency            NEGATIVE           |net move| / range - actively unpredictable

That gap is the single most important fact about this forecast, and it is why the module
docstring says so before anyone can build a gate on it. A directional strategy is paid for
DISPLACEMENT. This model forecasts PATH. Those are different quantities, and in this data
they move apart: sorting sessions into terciles of the forecast, median range grows 86% from
the low to the high tercile on ES while median |net move| grows only 31%, so measured
efficiency FALLS from 0.467 to 0.409.

High forecast volatility therefore means a choppier session, not a more directional one. Any
gate built on this forecast should be expected to HURT a trend or breakout mechanism and to
help a mean-reversion mechanism. That prediction is preregistered rather than discovered
after the fact, and `scripts/opportunity_gating.py` is the test of it.
"""
from __future__ import annotations

import numpy as np

#: The locked feature set. Changing this invalidates every gate built on it.
FEATURES: tuple[str, ...] = ("on_atr_pct", "on_vol_ratio", "prev_rth_rv_pct")

#: The yesterday-only benchmark the incremental claim is measured against.
BENCHMARK_FEATURES: tuple[str, ...] = ("prev_rth_range_pct", "prev_rth_rv_pct", "vol_state")

#: Minimum history before a forecast is emitted at all.
MIN_TRAIN = 60

#: Ridge penalty. Declared, never tuned against an out-of-sample score.
RIDGE = 1.0


def fit_predict(x_train: np.ndarray, y_train: np.ndarray, x_new: np.ndarray) -> float:
    """One standardised ridge forecast. Standardisation uses the training window only.

    The intercept is never penalised, which matters here because the target is a strictly
    positive quantity whose mean is far from zero; shrinking the intercept toward zero would
    bias every forecast downward by an amount that grows with the penalty.
    """
    mu = x_train.mean(axis=0)
    sd = x_train.std(axis=0)
    sd = np.where(sd > 1e-12, sd, 1.0)
    z = np.column_stack([np.ones(len(x_train)), (x_train - mu) / sd])
    y_mean = float(y_train.mean())
    a = z.T @ z + RIDGE * np.eye(z.shape[1])
    a[0, 0] -= RIDGE
    beta = np.linalg.solve(a, z.T @ (y_train - y_mean))
    z_new = np.concatenate([[1.0], (x_new - mu) / sd])
    return float(y_mean + z_new @ beta)


def walk_forward(x: np.ndarray, y: np.ndarray, min_train: int = MIN_TRAIN) -> np.ndarray:
    """Expanding-window one-step-ahead forecasts. NaN wherever no forecast is possible.

    Day k is forecast from days 0..k-1 and nothing else. There is no shuffling and no k-fold:
    in a time series both let a later observation inform an earlier prediction through the
    fitted coefficients, which is a leak even when every individual feature is causal.
    """
    n = len(y)
    out = np.full(n, np.nan)
    finite_x = np.isfinite(x).all(axis=1)
    for k in range(min_train, n):
        m = np.isfinite(y[:k]) & finite_x[:k]
        if int(m.sum()) < min_train or not finite_x[k]:
            continue
        try:
            out[k] = fit_predict(x[:k][m], y[:k][m], x[k])
        except np.linalg.LinAlgError:
            continue
    return out


def forecast_frame(g, target: str = "rth_rv_pct",
                   features: tuple[str, ...] = FEATURES) -> np.ndarray:
    """Convenience wrapper over a per-instrument frame sorted by trade date.

    The caller is responsible for sorting and for passing ONE instrument; a frame holding two
    instruments would let one contract's history fit the other's forecast, which is not a
    look-ahead but is still not the model anybody intended.
    """
    x = g[list(features)].to_numpy(dtype=float)
    y = g[target].to_numpy(dtype=float)
    return walk_forward(x, y)


def oos_r2(y: np.ndarray, pred: np.ndarray, bench: np.ndarray) -> tuple[float, int]:
    """R-squared of a forecast against a benchmark forecast, on rows where both exist."""
    m = np.isfinite(y) & np.isfinite(pred) & np.isfinite(bench)
    n = int(m.sum())
    if n < 30:
        return float("nan"), n
    sse = float(np.sum((y[m] - pred[m]) ** 2))
    ssb = float(np.sum((y[m] - bench[m]) ** 2))
    return (1.0 - sse / ssb if ssb > 0 else float("nan")), n


def expanding_mean(y: np.ndarray, min_train: int = MIN_TRAIN) -> np.ndarray:
    """The do-nothing benchmark: the mean of everything seen so far."""
    out = np.full(len(y), np.nan)
    for k in range(min_train, len(y)):
        v = y[:k][np.isfinite(y[:k])]
        if len(v) >= min_train:
            out[k] = float(v.mean())
    return out


__all__ = ["BENCHMARK_FEATURES", "FEATURES", "MIN_TRAIN", "RIDGE", "expanding_mean",
           "fit_predict", "forecast_frame", "oos_r2", "walk_forward"]
