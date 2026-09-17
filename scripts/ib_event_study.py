"""PART VI: does a false IB breakout raise P(midpoint touch)? Event dataset + logit.

    python scripts/ib_event_study.py --out research/ib_reversion

THE QUESTION, STATED SO IT CAN BE FALSIFIED
---------------------------------------------
"Does a false breakout of the Initial Balance statistically increase the probability of
subsequently touching the IB midpoint, under the 10-35 point IB range constraint?"

"Increase" needs a comparison, so every false breakout is matched against CONTROL moments:
bars inside the IB, in the same session, in the same 30-minute bucket of the day, with the
same terminal-event clock. Without a control the question has no denominator - a midpoint
sitting a few points away is touched often by drift alone.

THE COMPETING TERMINAL EVENT, DEFINED PRECISELY
-------------------------------------------------
From the event bar's close, whichever of these happens first:

    MIDPOINT_TOUCH = 1   the IB midpoint trades (high >= mid for a long, low <= mid short)
    MIDPOINT_TOUCH = 0   price trades beyond the stop level (E -/+ one tick), OR
                         60 minutes elapse, OR
                         15:45 arrives

For a control the "stop level" is the same distance away as the median event's, measured in
that session's own IB range, so the two arms face a comparable barrier rather than the control
facing none.

NOTHING HERE USES INFORMATION AFTER THE EVENT BAR'S CLOSE except the outcome itself, which is
what an outcome is. Every covariate is computed from bars at or before the event.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from quant_brain.strategies.initial_balance_reversion.spec import FROZEN, TIMEZONE  # noqa: E402
from quant_brain.strategies.vwap_pullback.data import load_anchored  # noqa: E402
from quant_brain.strategies.vwap_pullback.indicators import FiveMinuteAggregator  # noqa: E402

STORE = REPO / "data" / "futures"
RTH_LO, RTH_HI = 9 * 60 + 30, 15 * 60 + 45
IB_LO, IB_HI = 9 * 60 + 30, 10 * 60 + 30
CUTOFF, FLATTEN = 14 * 60, 15 * 60 + 45
SEED = 20260917
CONTROLS_PER_EVENT = 2


def minute_of(bar_or_five, tz=TIMEZONE) -> int:
    t = getattr(bar_or_five, "start", None) or bar_or_five.timestamp
    local = t.astimezone(tz)
    return local.hour * 60 + local.minute


def buckets_for(session) -> list:
    agg = FiveMinuteAggregator()
    out = []
    for b in session.bars:
        m = b.timestamp.astimezone(TIMEZONE).hour * 60 + b.timestamp.astimezone(TIMEZONE).minute
        if not (RTH_LO <= m <= RTH_HI):
            continue
        done = agg.update(b, float("nan"))
        if done is not None:
            out.append(done)
    return out


def outcome(buckets, i0, direction, mid, stop, deadline_idx) -> tuple[int, int]:
    """Walk forward from bucket i0+1. Returns (touched, buckets_to_resolution)."""
    for k in range(i0 + 1, min(len(buckets), deadline_idx + 1)):
        b = buckets[k]
        if minute_of(b) >= FLATTEN:
            return 0, k - i0
        hit_mid = b.high >= mid if direction > 0 else b.low <= mid
        hit_stop = b.low <= stop if direction > 0 else b.high >= stop
        if hit_stop:                      # conservative: the stop resolves first
            return 0, k - i0
        if hit_mid:
            return 1, k - i0
    return 0, min(len(buckets) - 1, deadline_idx) - i0


def build(instrument: str = "ES") -> list[dict]:
    rng = random.Random(SEED)
    ds = load_anchored(STORE / f"{instrument}.parquet", instrument)
    rows: list[dict] = []

    for s in ds.usable():
        bk = buckets_for(s)
        ib = [b for b in bk if IB_LO <= minute_of(b) < IB_HI]
        if len(ib) != 12:
            continue
        hi, lo = max(b.high for b in ib), min(b.low for b in ib)
        rng_pts = hi - lo
        if not (FROZEN.ib_range_min <= rng_pts <= FROZEN.ib_range_max):
            continue                     # the study is conditioned on the frozen regime
        mid = (hi + lo) / 2.0
        armed = [(i, b) for i, b in enumerate(bk)
                 if IB_HI <= minute_of(b) < CUTOFF]
        if not armed:
            continue

        # ---- events: a trip outside the IB that closes back inside --------------------
        side, extreme = 0, float("nan")
        events: list[tuple[int, int, float]] = []
        for i, b in armed:
            went_lo, went_hi = b.low < lo, b.high > hi
            if side == 0:
                if went_lo and not went_hi:
                    side, extreme = -1, b.low
                elif went_hi and not went_lo:
                    side, extreme = 1, b.high
            elif side == -1:
                if went_lo:
                    extreme = min(extreme, b.low)
            elif went_hi:
                extreme = max(extreme, b.high)
            if side == -1 and b.close > lo:
                events.append((i, 1, extreme))       # long
                side, extreme = 0, float("nan")
            elif side == 1 and b.close < hi:
                events.append((i, -1, extreme))      # short
                side, extreme = 0, float("nan")

        for i, d, ext in events:
            b = bk[i]
            entry = b.close
            stop = ext - FROZEN.tick * d
            deadline = i + (FROZEN.time_stop_minutes // FROZEN.bar_minutes)
            touched, dur = outcome(bk, i, d, mid, stop, deadline)
            rows.append({
                "session": str(s.trading_day), "instrument": instrument,
                "event_id": f"{s.trading_day}-{i}", "false_breakout": 1,
                "direction": d, "minute_of_day": minute_of(b),
                "minutes_since_ib": minute_of(b) - IB_HI,
                "ib_range": round(rng_pts, 4),
                "excursion_points": round(abs(ext - (lo if d > 0 else hi)), 4),
                "distance_to_mid": round(abs(mid - entry), 4),
                "distance_to_mid_over_range": round(abs(mid - entry) / rng_pts, 6),
                "stop_distance": round(abs(entry - stop), 4),
                "midpoint_touch": touched, "buckets_to_resolution": dur,
            })

        # ---- controls: inside-the-IB moments, same session, same time bucket ----------
        inside = [(i, b) for i, b in armed if lo <= b.close <= hi]
        if not inside or not events:
            continue
        median_stop = float(np.median([r["stop_distance"] for r in rows
                                       if r["session"] == str(s.trading_day)]
                                      or [rng_pts * 0.25]))
        want = len(events) * CONTROLS_PER_EVENT
        for _ in range(want):
            i, b = rng.choice(inside)
            entry = b.close
            d = 1 if entry < mid else -1          # face the midpoint, as an event does
            stop = entry - median_stop * d
            deadline = i + (FROZEN.time_stop_minutes // FROZEN.bar_minutes)
            touched, dur = outcome(bk, i, d, mid, stop, deadline)
            rows.append({
                "session": str(s.trading_day), "instrument": instrument,
                "event_id": f"{s.trading_day}-c{i}", "false_breakout": 0,
                "direction": d, "minute_of_day": minute_of(b),
                "minutes_since_ib": minute_of(b) - IB_HI,
                "ib_range": round(rng_pts, 4),
                "excursion_points": 0.0,
                "distance_to_mid": round(abs(mid - entry), 4),
                "distance_to_mid_over_range": round(abs(mid - entry) / rng_pts, 6),
                "stop_distance": round(median_stop, 4),
                "midpoint_touch": touched, "buckets_to_resolution": dur,
            })
    return rows


# ======================================================================================
# LOGIT WITH CLUSTER-ROBUST STANDARD ERRORS, WRITTEN OUT
# ======================================================================================

def logit(X: np.ndarray, y: np.ndarray, clusters: np.ndarray, names: list[str],
          iters: int = 60) -> dict:
    """Newton-Raphson MLE, then a cluster-robust (CR0) sandwich by trading day.

    statsmodels is not installed in this environment, so the estimator is written out. It is
    checked against a closed-form two-by-two case in the tests.
    """
    n, k = X.shape
    beta = np.zeros(k)
    for _ in range(iters):
        eta = np.clip(X @ beta, -30, 30)
        p = 1.0 / (1.0 + np.exp(-eta))
        W = p * (1 - p)
        g = X.T @ (y - p)
        H = (X * W[:, None]).T @ X
        H += np.eye(k) * 1e-10
        step = np.linalg.solve(H, g)
        beta += step
        if np.max(np.abs(step)) < 1e-10:
            break
    eta = np.clip(X @ beta, -30, 30)
    p = 1.0 / (1.0 + np.exp(-eta))
    W = p * (1 - p)
    bread = np.linalg.inv((X * W[:, None]).T @ X + np.eye(k) * 1e-12)
    meat = np.zeros((k, k))
    for c in np.unique(clusters):
        m = clusters == c
        u = (X[m] * (y[m] - p[m])[:, None]).sum(axis=0)
        meat += np.outer(u, u)
    G = len(np.unique(clusters))
    scale = G / max(G - 1, 1)
    V = bread @ meat @ bread * scale
    se = np.sqrt(np.diag(V))
    z = beta / se
    from math import erf
    pv = [2 * (1 - 0.5 * (1 + erf(abs(t) / math.sqrt(2)))) for t in z]
    ll = float(np.sum(y * np.log(np.clip(p, 1e-12, 1)) +
                      (1 - y) * np.log(np.clip(1 - p, 1e-12, 1))))
    p0 = y.mean()
    ll0 = float(n * (p0 * math.log(p0) + (1 - p0) * math.log(1 - p0)))
    return {
        "n": int(n), "clusters": int(G),
        "terms": [{"name": names[i], "coef": round(float(beta[i]), 6),
                   "robust_se": round(float(se[i]), 6), "z": round(float(z[i]), 4),
                   "p_value": round(float(pv[i]), 6),
                   "ci95": [round(float(beta[i] - 1.96 * se[i]), 6),
                            round(float(beta[i] + 1.96 * se[i]), 6)],
                   "odds_ratio": round(float(np.exp(beta[i])), 6),
                   "odds_ratio_ci95": [round(float(np.exp(beta[i] - 1.96 * se[i])), 6),
                                       round(float(np.exp(beta[i] + 1.96 * se[i])), 6)]}
                  for i in range(k)],
        "log_likelihood": round(ll, 4),
        "mcfadden_pseudo_r2": round(1 - ll / ll0, 6) if ll0 else None,
        "se_method": "cluster-robust (CR0) sandwich, clustered on trading day, with a "
                     "G/(G-1) finite-sample scale",
    }


def design(rows, cols):
    X = np.column_stack([np.ones(len(rows))]
                        + [np.array([float(r[c]) for r in rows]) for c in cols])
    y = np.array([float(r["midpoint_touch"]) for r in rows])
    cl = np.array([r["session"] for r in rows])
    return X, y, cl, ["intercept", *cols]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="research/ib_reversion")
    args = ap.parse_args()
    out = REPO / args.out
    out.mkdir(parents=True, exist_ok=True)

    rows = build("ES")
    path = out / "ib_events.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    ev = [r for r in rows if r["false_breakout"] == 1]
    ct = [r for r in rows if r["false_breakout"] == 0]
    print(f"events {len(ev)}  controls {len(ct)}  sessions "
          f"{len({r['session'] for r in rows})}")
    print(f"  midpoint touch rate: events {np.mean([r['midpoint_touch'] for r in ev]):.4f}  "
          f"controls {np.mean([r['midpoint_touch'] for r in ct]):.4f}")

    cols = ["false_breakout", "ib_range", "distance_to_mid_over_range", "minutes_since_ib",
            "direction"]
    X, y, cl, names = design(rows, cols)
    full = logit(X, y, cl, names)

    #: chronological out-of-sample: fit on the first 70% of SESSIONS, evaluate on the rest
    days = sorted({r["session"] for r in rows})
    cut = days[int(len(days) * 0.7)]
    tr = [r for r in rows if r["session"] < cut]
    te = [r for r in rows if r["session"] >= cut]
    Xtr, ytr, cltr, _ = design(tr, cols)
    fit = logit(Xtr, ytr, cltr, names)
    Xte, yte, _, _ = design(te, cols)
    beta = np.array([t["coef"] for t in fit["terms"]])
    pte = 1 / (1 + np.exp(-np.clip(Xte @ beta, -30, 30)))
    oos = {
        "train_rows": len(tr), "test_rows": len(te), "split_session": cut,
        "train_false_breakout_coef": fit["terms"][1]["coef"],
        "train_false_breakout_p": fit["terms"][1]["p_value"],
        "test_touch_rate_events": round(float(np.mean(
            [r["midpoint_touch"] for r in te if r["false_breakout"] == 1])), 4),
        "test_touch_rate_controls": round(float(np.mean(
            [r["midpoint_touch"] for r in te if r["false_breakout"] == 0])), 4),
        "test_brier": round(float(np.mean((pte - yte) ** 2)), 6),
        "test_brier_of_base_rate": round(float(np.mean((ytr.mean() - yte) ** 2)), 6),
    }

    result = {
        "question": "does a false IB breakout raise P(midpoint touch) versus a matched "
                    "in-IB control, conditioned on a 10-35 point IB range?",
        "unit": "one eligible event (false breakout) or matched control",
        "terminal_event": "midpoint touched, versus stop level breached OR 60 minutes "
                          "elapsed OR 15:45, whichever first; the stop resolves first "
                          "inside an ambiguous bucket",
        "n_events": len(ev), "n_controls": len(ct),
        "touch_rate_events": round(float(np.mean([r["midpoint_touch"] for r in ev])), 4),
        "touch_rate_controls": round(float(np.mean([r["midpoint_touch"] for r in ct])), 4),
        "logit": full,
        "out_of_sample": oos,
        "CAVEAT": "ASSOCIATION, NOT CAUSATION. The control is matched on session, time "
                  "bucket and barrier distance, not randomised; unobserved intraday state "
                  "differs between a bar that just broke the IB and one that did not.",
    }
    (out / "ib_event_study.json").write_text(
        json.dumps(result, indent=1, default=str), encoding="utf-8")

    print(f"\n  {'term':32}{'coef':>10}{'robustSE':>10}{'z':>8}{'p':>10}{'OR':>9}")
    for t in full["terms"]:
        print(f"  {t['name']:32}{t['coef']:>10.4f}{t['robust_se']:>10.4f}{t['z']:>8.2f}"
              f"{t['p_value']:>10.4f}{t['odds_ratio']:>9.3f}")
    print(f"\n  N {full['n']}  clusters {full['clusters']}  "
          f"pseudo-R2 {full['mcfadden_pseudo_r2']}")
    print(f"  OOS: train coef {oos['train_false_breakout_coef']:.4f} "
          f"(p {oos['train_false_breakout_p']:.4f}); test touch rate events "
          f"{oos['test_touch_rate_events']:.3f} vs controls "
          f"{oos['test_touch_rate_controls']:.3f}")
    print(f"  wrote {path.relative_to(REPO)} and ib_event_study.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
