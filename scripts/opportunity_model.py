"""Phase 1, second half: fit the opportunity forecast and find out how good it actually is.

WHAT A GATE NEEDS, AND WHY A CORRELATION IS NOT IT
----------------------------------------------------
The surviving finding from the previous study was a correlation: overnight range against RTH
range, r about 0.4. A correlation cannot gate anything, because a gate has to emit a decision
at 09:29 from a number it computed without seeing the day it is deciding about.

So this module fits the forecast properly and reports the only number that can justify a
gate: **out-of-sample R-squared against the expanding historical mean**. If that is not
comfortably positive, there is no opportunity model and Phases 2 through 7 are gating on
noise. Everything downstream depends on this one table, which is why it is computed first and
in isolation.

THE PROTOCOL
------------
Expanding window, one step ahead, refit every day, minimum 60 days of history before the
first forecast. The coefficients that produce the forecast for day k are estimated on days
1..k-1 and on nothing else. There is no shuffling and no k-fold, because both would let a
future day inform a past prediction through the fitted coefficients, and in a time series
that is a leak even when every feature is causal.

WHY FOUR MODELS AND NOT ONE
----------------------------
  mean          the expanding historical mean. The benchmark everything is scored against.
  prev          yesterday's RTH range and realised volatility. The null that matters, because
                volatility clusters and "overnight predicts today" may just be "this week is
                volatile".
  overnight     the overnight description alone, with no yesterday. Isolates what the
                overnight session contributes on its own.
  full          both. The question is whether this beats `prev`, not whether it beats `mean`.

Reporting `overnight` separately is what makes the incremental claim falsifiable. A model
that beats the mean tells you volatility clusters, which everyone knows.

RIDGE, AND WHY
--------------
Fifteen correlated predictors on sixty observations is a badly conditioned problem and plain
least squares will fit the noise in the early folds, which shows up as a wildly negative
out-of-sample R-squared that says more about the conditioning than the data. A small fixed
ridge penalty is applied, standardised on the training window only. The penalty is a declared
constant, not tuned - tuning it against the out-of-sample score would be exactly the leak
this protocol exists to prevent.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from opportunity_panel import PREDICTORS  # noqa: E402

MIN_TRAIN = 60
#: Declared in advance. Not tuned against any score in this module.
RIDGE = 1.0

OVERNIGHT_ONLY = tuple(f for f in PREDICTORS if not f.startswith("prev_")
                       and f not in ("on_over_prev_range", "vol_state"))
PREV_ONLY = ("prev_rth_range_pct", "prev_rth_rv_pct", "vol_state")

TARGETS = (("rth_range_pct", "RTH range %"),
           ("rth_rv_pct", "RTH realised vol %"))


def _fit_predict(Xtr: np.ndarray, ytr: np.ndarray, xte: np.ndarray) -> float:
    """Standardised ridge. Standardisation uses the TRAINING window only."""
    mu, sd = Xtr.mean(axis=0), Xtr.std(axis=0)
    sd = np.where(sd > 1e-12, sd, 1.0)
    Z = (Xtr - mu) / sd
    Z = np.column_stack([np.ones(len(Z)), Z])
    ym = ytr.mean()
    A = Z.T @ Z + RIDGE * np.eye(Z.shape[1])
    A[0, 0] -= RIDGE                       # never penalise the intercept
    beta = np.linalg.solve(A, Z.T @ (ytr - ym))
    z = np.concatenate([[1.0], (xte - mu) / sd])
    return float(ym + z @ beta)


def walk_forward(g: pd.DataFrame, feats: tuple[str, ...], target: str) -> np.ndarray:
    X = g[list(feats)].to_numpy(dtype=float)
    y = g[target].to_numpy(dtype=float)
    pred = np.full(len(g), np.nan)
    for k in range(MIN_TRAIN, len(g)):
        m = np.isfinite(y[:k]) & np.isfinite(X[:k]).all(axis=1)
        if m.sum() < MIN_TRAIN or not np.isfinite(X[k]).all():
            continue
        try:
            pred[k] = _fit_predict(X[:k][m], y[:k][m], X[k])
        except np.linalg.LinAlgError:
            continue
    return pred


def expanding_mean(y: np.ndarray) -> np.ndarray:
    out = np.full(len(y), np.nan)
    for k in range(MIN_TRAIN, len(y)):
        v = y[:k][np.isfinite(y[:k])]
        if len(v) >= MIN_TRAIN:
            out[k] = float(v.mean())
    return out


def oos_r2(y: np.ndarray, pred: np.ndarray, bench: np.ndarray) -> tuple[float, int]:
    m = np.isfinite(y) & np.isfinite(pred) & np.isfinite(bench)
    if m.sum() < 30:
        return np.nan, int(m.sum())
    sse = float(np.sum((y[m] - pred[m]) ** 2))
    ssb = float(np.sum((y[m] - bench[m]) ** 2))
    return (1.0 - sse / ssb if ssb > 0 else np.nan), int(m.sum())


def main() -> int:
    p = pd.read_parquet(REPO / "research" / "opportunity_panel.parquet")
    rows = []

    print("=" * 100)
    print("PHASE 1 - OPPORTUNITY FORECAST QUALITY, out-of-sample, expanding window, causal")
    print("=" * 100)
    print("R-squared is against the expanding historical mean. 'incremental' is the full")
    print("model scored against the prev-day model, which is the claim that matters.\n")

    for tgt, tlabel in TARGETS:
        print(f"--- target: {tlabel} " + "-" * (78 - len(tlabel)))
        print(f"{'sym':5} {'n_oos':>6} {'R2 prev':>9} {'R2 overnight':>13} {'R2 full':>9} "
              f"{'incremental':>12}")
        for sym, g in p.groupby("symbol"):
            g = g.sort_values("tdate").reset_index(drop=True)
            y = g[tgt].to_numpy(dtype=float)
            bench = expanding_mean(y)
            p_prev = walk_forward(g, PREV_ONLY, tgt)
            p_on = walk_forward(g, OVERNIGHT_ONLY, tgt)
            p_full = walk_forward(g, PREDICTORS, tgt)
            r_prev, _ = oos_r2(y, p_prev, bench)
            r_on, _ = oos_r2(y, p_on, bench)
            r_full, n = oos_r2(y, p_full, bench)
            incr, _ = oos_r2(y, p_full, p_prev)
            rows.append({"target": tgt, "symbol": sym, "n_oos": n, "r2_prev": r_prev,
                         "r2_overnight": r_on, "r2_full": r_full, "incremental": incr})
            print(f"{sym:5} {n:6d} {r_prev:9.3f} {r_on:13.3f} {r_full:9.3f} {incr:12.3f}")
        print()

    print("=" * 100)
    print("THE SAME MODEL, ASKED FOR DIRECTION INSTEAD  (the control that must fail)")
    print("=" * 100)
    print("If the opportunity model can 'predict' signed return, something is leaking.\n")
    print(f"{'sym':5} {'n_oos':>6} {'R2 signed return':>18} {'R2 |return|':>13}")
    for sym, g in p.groupby("symbol"):
        g = g.sort_values("tdate").reset_index(drop=True)
        for tgt, lbl in (("rth_ret_pct", "signed"), ("rth_absret_pts", "abs")):
            y = g[tgt].to_numpy(dtype=float)
            r, n = oos_r2(y, walk_forward(g, PREDICTORS, tgt), expanding_mean(y))
            if lbl == "signed":
                sr, sn = r, n
            else:
                ar = r
        print(f"{sym:5} {sn:6d} {sr:18.3f} {ar:13.3f}")

    out = pd.DataFrame(rows)
    out.to_csv(REPO / "research" / "opportunity_model.csv", index=False)
    print(f"\nwrote {REPO / 'research' / 'opportunity_model.csv'}")

    print("\n" + "=" * 100)
    print("WHICH PREDICTORS CARRY IT  (standardised ridge coefficients, full sample, ES/NQ)")
    print("=" * 100)
    print("In-sample and for description only - the out-of-sample table above is the evidence.")
    print(f"{'predictor':24}" + "".join(f"{s:>10}" for s in ["ES", "NQ", "MES", "MNQ"]))
    coefs = {}
    for sym, g in p.groupby("symbol"):
        g = g.dropna(subset=[*PREDICTORS, "rth_range_pct"])
        X = g[list(PREDICTORS)].to_numpy(dtype=float)
        y = g["rth_range_pct"].to_numpy(dtype=float)
        mu, sd = X.mean(axis=0), X.std(axis=0)
        sd = np.where(sd > 1e-12, sd, 1.0)
        Z = np.column_stack([np.ones(len(X)), (X - mu) / sd])
        A = Z.T @ Z + RIDGE * np.eye(Z.shape[1])
        A[0, 0] -= RIDGE
        coefs[sym] = np.linalg.solve(A, Z.T @ (y - y.mean()))[1:]
    for i, f in enumerate(PREDICTORS):
        print(f"{f:24}" + "".join(f"{coefs[s][i]:10.3f}" for s in ["ES", "NQ", "MES", "MNQ"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
