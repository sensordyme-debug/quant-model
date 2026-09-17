"""PART 2-5: opportunity frequency and the entry-information gate, across mechanism families.

    python scripts/mechanism_screen.py --instrument NQ --split dev

Fourteen intraday mechanisms, each a HYPOTHESIS with no assumed edge. For each one this
measures how often it fires and whether the bar it fires on predicts the next 1-30 minutes
better than a matched random entry in the same session at the same time of day.

NOTHING IS OPTIMISED HERE. Every parameter is fixed a priori at a conventional value and
written into the definition below. The script has no parameter arguments and no search loop,
because a screen that can be re-run with different numbers is a search whether or not anyone
calls it one.

THE SPLIT, DECLARED BEFORE ANY RESULT IS SEEN
-----------------------------------------------
    dev       first 60% of sessions     screening happens here and only here
    val       next 20%                  looked at once, for candidates that survive dev
    holdout   final 20%                 NOT TOUCHED in this phase

WHY SESSION-CLUSTERED INFERENCE
---------------------------------
Events overlap: a 30-minute forward window started on consecutive bars shares 29 minutes of
its outcome with its neighbour, so the naive t-statistic over events counts the same
information many times. `docs` FINDING "window overlap" records this defect replicating out
of sample in this repository. The primary statistic here is therefore computed over SESSION
MEANS - one observation per session - and the naive event-level t is printed beside it so the
inflation is visible rather than hidden.

MULTIPLE TESTING
------------------
Fourteen mechanisms times six horizons is 84 trials, and a null produces about four
"significant" results at alpha = 0.05 by construction. Benjamini-Hochberg FDR is applied
across the whole family and only the adjusted verdict is reported as a survival.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from quant_brain.core import multipletest as MT  # noqa: E402
from quant_brain.research import feasibility as F  # noqa: E402
from quant_brain.strategies.vwap_pullback.data import load_anchored  # noqa: E402
from quant_brain.strategies.vwap_pullback.spec import TIMEZONE  # noqa: E402

STORE = REPO / "data" / "futures"
HORIZONS = (1, 3, 5, 10, 15, 30)

#: The decision window, in minutes past ET midnight. 09:30 so an opening-range mechanism can
#: see its own range form; 15:30 to match the Combine's intraday character and leave room for
#: the longest forward horizon before the 15:45 session end.
OPEN_MIN, DECIDE_FROM, DECIDE_TO, SESSION_END = 9 * 60 + 30, 9 * 60 + 45, 15 * 60 + 30, 15 * 60 + 45
OPENING_RANGE_END = 9 * 60 + 45          # 09:30-09:44 inclusive forms the range

SEED = 20260916
RANDOM_CONTROLS_PER_EVENT = 5


@dataclass
class Session:
    day: str
    minute: np.ndarray          # minute of ET day
    o: np.ndarray
    h: np.ndarray
    lo: np.ndarray
    c: np.ndarray
    v: np.ndarray
    vwap: np.ndarray            # 18:00-anchored, causal
    sigma: np.ndarray


def build(instrument: str) -> list[Session]:
    ds = load_anchored(STORE / f"{instrument}.parquet", instrument)
    out = []
    for s in ds.usable():
        n = len(s.bars)
        minute = np.empty(n, dtype=np.int32)
        o = np.empty(n); h = np.empty(n); lo = np.empty(n); c = np.empty(n); v = np.empty(n)
        for i, b in enumerate(s.bars):
            et = b.timestamp.astimezone(TIMEZONE)
            minute[i] = et.hour * 60 + et.minute
            o[i], h[i], lo[i], c[i], v[i] = b.open, b.high, b.low, b.close, b.volume
        #: the session VWAP and its dispersion, accumulated forward only
        tp = (h + lo + c) / 3.0
        cv = np.cumsum(tp * v)
        cw = np.cumsum(v)
        with np.errstate(invalid="ignore", divide="ignore"):
            vwap = np.where(cw > 0, cv / cw, np.nan)
            cv2 = np.cumsum(tp * tp * v)
            var = np.where(cw > 0, cv2 / cw - vwap * vwap, np.nan)
            sigma = np.sqrt(np.maximum(var, 0.0))
        out.append(Session(str(s.trading_day), minute, o, h, lo, c, v, vwap, sigma))
    return out


def _roll_max(x: np.ndarray, n: int) -> np.ndarray:
    """Rolling max of the PREVIOUS n values (excludes the current bar). Causal."""
    out = np.full_like(x, np.nan)
    for i in range(n, len(x)):
        out[i] = x[i - n:i].max()
    return out


def _roll_min(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full_like(x, np.nan)
    for i in range(n, len(x)):
        out[i] = x[i - n:i].min()
    return out


def _roll_mean(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full_like(x, np.nan)
    cs = np.cumsum(np.insert(x, 0, 0.0))
    out[n - 1:] = (cs[n:] - cs[:-n]) / n
    return out


def _atr(h, lo, c, n=14) -> np.ndarray:
    prev = np.roll(c, 1); prev[0] = c[0]
    tr = np.maximum(h - lo, np.maximum(np.abs(h - prev), np.abs(lo - prev)))
    return _roll_mean(tr, n)


# ======================================================================================
# THE MECHANISMS. Each returns (long_mask, short_mask). No parameter is searched.
# ======================================================================================

def mechanisms(s: Session, prior_high: float, prior_low: float) -> dict:
    m, c, h, lo, o, v = s.minute, s.c, s.h, s.lo, s.o, s.v
    vwap, sig = s.vwap, s.sigma
    n = len(c)
    atr = _atr(h, lo, c, 14)
    vol20 = _roll_mean(v, 20)
    hi20, lo20 = _roll_max(h, 20), _roll_min(lo, 20)
    hi5, lo5 = _roll_max(h, 5), _roll_min(lo, 5)
    rng20 = hi20 - lo20
    #: CAUSAL reference level. An earlier draft used the median of `rng20` over the WHOLE
    #: session, which is the denominator-lookahead pattern `docs` records as replicating out
    #: of sample. This is a trailing mean of the PREVIOUS 120 bars and sees nothing forward.
    rng20_ref = _roll_mean(np.nan_to_num(rng20, nan=0.0), 120)
    rng20_ref = np.r_[np.nan, rng20_ref[:-1]]
    prev_c = np.roll(c, 1); prev_c[0] = c[0]
    prev_h = np.roll(h, 1); prev_h[0] = h[0]
    prev_l = np.roll(lo, 1); prev_l[0] = lo[0]

    #: running session extremes, EXCLUDING the current bar
    rth = m >= OPEN_MIN
    sess_hi = np.full(n, np.nan); sess_lo = np.full(n, np.nan)
    run_h, run_l = -np.inf, np.inf
    for i in range(n):
        if rth[i]:
            sess_hi[i], sess_lo[i] = run_h, run_l
            run_h, run_l = max(run_h, h[i]), min(run_l, lo[i])

    #: opening range 09:30-09:44
    orb = (m >= OPEN_MIN) & (m < OPENING_RANGE_END)
    or_hi = h[orb].max() if orb.any() else np.nan
    or_lo = lo[orb].min() if orb.any() else np.nan

    with np.errstate(invalid="ignore", divide="ignore"):
        z = (c - vwap) / np.where(sig > 0, sig, np.nan)

    can = (m >= DECIDE_FROM) & (m <= DECIDE_TO) & np.isfinite(vwap) & np.isfinite(atr)
    heavy = v > 1.2 * vol20
    up, down = c > o, c < o

    M: dict[str, tuple[np.ndarray, np.ndarray]] = {}

    # 1 VWAP pullback: above VWAP, this bar dips to touch it, closes back up
    M["vwap_pullback"] = (can & (prev_c > vwap) & (lo <= vwap) & (c > vwap) & up,
                          can & (prev_c < vwap) & (h >= vwap) & (c < vwap) & down)
    # 2 VWAP reclaim: was below for 5 bars, now closes above
    below5 = np.r_[[False] * 5, [(c[i - 5:i] < vwap[i - 5:i]).all() for i in range(5, n)]]
    above5 = np.r_[[False] * 5, [(c[i - 5:i] > vwap[i - 5:i]).all() for i in range(5, n)]]
    M["vwap_reclaim"] = (can & below5 & (c > vwap), can & above5 & (c < vwap))
    # 3 opening-range continuation
    M["orb_continuation"] = (can & (c > or_hi) & (prev_c <= or_hi),
                             can & (c < or_lo) & (prev_c >= or_lo))
    # 4 opening-range failure: poked out, closed back inside
    M["orb_failure"] = (can & (prev_h > or_hi) & (c < or_hi) & down,
                        can & (prev_l < or_lo) & (c > or_lo) & up)
    # 5 trend pullback: above VWAP, 3 red bars, then a green close
    red3 = np.r_[[False] * 3, [(c[i - 3:i] < o[i - 3:i]).all() for i in range(3, n)]]
    grn3 = np.r_[[False] * 3, [(c[i - 3:i] > o[i - 3:i]).all() for i in range(3, n)]]
    M["trend_pullback"] = (can & (c > vwap) & red3 & up, can & (c < vwap) & grn3 & down)
    # 6 volatility expansion: range > 2x ATR, with direction
    M["vol_expansion"] = (can & ((h - lo) > 2.0 * atr) & up,
                          can & ((h - lo) > 2.0 * atr) & down)
    # 7 compression then expansion: 20-bar range in the bottom half, then a breakout
    tight = rng20 < 0.5 * rng20_ref
    M["compression_break"] = (can & tight & (c > hi20), can & tight & (c < lo20))
    # 8 failed breakout: made a 20-bar high last bar, closes back below it
    M["failed_breakout"] = (can & (prev_h > hi20) & (c < hi20) & down,
                            can & (prev_l < lo20) & (c > lo20) & up)
    # 9 range breakout on volume
    M["range_breakout"] = (can & (c > hi20) & heavy, can & (c < lo20) & heavy)
    # 10 mean reversion after displacement: |z| > 2 against the move
    M["mean_reversion_z2"] = (can & (z < -2.0), can & (z > 2.0))
    # 11 prior-session high/low interaction
    M["prior_day_level"] = (can & (lo <= prior_low) & (c > prior_low) & up,
                            can & (h >= prior_high) & (c < prior_high) & down)
    # 12 session high/low rejection
    M["session_hl_rejection"] = (can & (lo <= sess_lo) & (c > sess_lo) & up,
                                 can & (h >= sess_hi) & (c < sess_hi) & down)
    # 13 momentum continuation after compression: 5-bar range tight, close takes the 5-bar hi
    tight5 = (hi5 - lo5) < atr
    M["momentum_after_compression"] = (can & tight5 & (c > hi5) & heavy,
                                       can & tight5 & (c < lo5) & heavy)
    # 14 time-of-day momentum: first hour, take the 20-bar extreme
    first_hour = can & (m < OPEN_MIN + 60)
    M["tod_momentum_open"] = (first_hour & (c > hi20), first_hour & (c < lo20))
    # 15 time-of-day mean reversion: last 90 minutes, fade a 2-sigma stretch
    late = can & (m >= DECIDE_TO - 90)
    M["tod_meanrev_late"] = (late & (z < -1.5), late & (z > 1.5))
    return M


# ======================================================================================
# MEASUREMENT
# ======================================================================================

def forward(s: Session, h: int) -> np.ndarray:
    """close[i+h] - close[i], NaN once the window would run past the session end."""
    n = len(s.c)
    out = np.full(n, np.nan)
    if h < n:
        out[:n - h] = s.c[h:] - s.c[:n - h]
    return out


def non_overlapping(idx: np.ndarray, h: int) -> np.ndarray:
    """Greedily thin an event index so no two forward windows share a minute.

    WITHOUT THIS THE SCREEN MEASURES NOTHING TRADEABLE. Twenty-one events in one afternoon,
    each looking thirty minutes ahead, are twenty-one readings of the same move: the mean is
    not a per-trade expectation, the count is not a trade count, and multiplying them gives
    $2,896 a session, which is how the first version of this script "found" an edge worth
    a Combine pass per day. One position at a time is also the only thing the account could
    actually hold.
    """
    keep, last = [], -10**9
    for i in idx:
        if i - last >= h:
            keep.append(i)
            last = i
    return np.array(keep, dtype=int)


def screen(sessions: list[Session], instrument: str) -> dict:
    """Frequency and forward information, measured on NON-OVERLAPPING events only.

    Two counts are reported and they mean different things. `events_total` is how often the
    condition appears - the OPPORTUNITY. `tradeable_per_session` is how many of those survive
    the one-position-at-a-time thinning at a given horizon - what an account could act on.
    """
    rng = np.random.default_rng(SEED)
    point = F.POINT_VALUE[instrument]
    rt_cost = F.round_turn_cost(instrument, 1)

    fwd = {h: [forward(s, h) for s in sessions] for h in HORIZONS}
    masks: dict[str, list[tuple[np.ndarray, np.ndarray]]] = {}
    eligible = []
    prior_h = prior_l = np.nan
    for s in sessions:
        M = mechanisms(s, prior_h, prior_l)
        for name, pair in M.items():
            masks.setdefault(name, []).append(pair)
        rth = s.minute >= OPEN_MIN
        prior_h = s.h[rth].max() if rth.any() else np.nan
        prior_l = s.lo[rth].min() if rth.any() else np.nan
        eligible.append((s.minute >= DECIDE_FROM) & (s.minute <= DECIDE_TO))

    results = {}
    for name in masks:
        raw_counts = np.array([int(masks[name][i][0].sum() + masks[name][i][1].sum())
                               for i in range(len(sessions))], dtype=float)
        horizons = {}
        for h in HORIZONS:
            ev_mean, ct_mean, kept_counts, all_signed = [], [], [], []
            for si, s in enumerate(sessions):
                lg, sh = masks[name][si]
                idx = np.flatnonzero(lg | sh)
                if idx.size == 0:
                    kept_counts.append(0)
                    continue
                keep = non_overlapping(idx, h)
                sign = np.where(lg[keep], 1.0, -1.0)
                f = fwd[h][si]
                signed = f[keep] * sign
                ok = np.isfinite(signed)
                keep, sign, signed = keep[ok], sign[ok], signed[ok]
                kept_counts.append(int(keep.size))
                if keep.size == 0:
                    continue

                #: THE MATCHED CONTROL. Same session, same direction, and - the part an
                #: earlier draft got wrong - the SAME TIME OF DAY, to within a 30-minute
                #: bucket, drawn only from bars whose own forward window is complete.
                #:
                #: Without the time match, a mechanism that fires in the last ninety minutes
                #: was being compared with random bars from the whole session, and bars near
                #: the close were then silently dropped for having a NaN outcome - so the
                #: control was both the wrong hour and biased toward the morning. That is how
                #: `tod_meanrev_late` produced a control mean of -14.6 points and an
                #: apparent 21-point edge.
                valid = np.flatnonzero(eligible[si] & np.isfinite(f))
                if valid.size == 0:
                    kept_counts[-1] = 0
                    continue
                vmin = s.minute[valid]
                cs_parts = []
                for k_i, k_sign in zip(keep, sign, strict=True):
                    bucket = s.minute[k_i] // 30
                    pool = valid[vmin // 30 == bucket]
                    if pool.size == 0:
                        pool = valid
                    draw = rng.choice(pool, size=RANDOM_CONTROLS_PER_EVENT, replace=True)
                    cs_parts.append(f[draw] * k_sign)
                cs = np.concatenate(cs_parts)
                cs = cs[np.isfinite(cs)]
                if cs.size == 0:
                    kept_counts[-1] = 0
                    continue

                ev_mean.append(float(signed.mean()))
                ct_mean.append(float(cs.mean()))
                all_signed.extend(signed.tolist())

            a, b = np.array(ev_mean), np.array(ct_mean)
            e = np.array(all_signed)
            kept = np.array(kept_counts, dtype=float)
            if a.size < 5:
                horizons[h] = {"sessions_with_events": int(a.size), "insufficient": True}
                continue

            diff = a - b
            sd = float(a.std(ddof=1))
            sdd = float(diff.std(ddof=1))
            t_clustered = float(a.mean() / (sd / math.sqrt(a.size))) if sd > 0 else float("nan")
            t_ctrl = float(diff.mean() / (sdd / math.sqrt(diff.size))) if sdd > 0 else float("nan")
            t_naive = (float(e.mean() / (e.std(ddof=1) / math.sqrt(e.size)))
                       if e.size > 1 and e.std(ddof=1) > 0 else float("nan"))
            ci = 1.96 * sd / math.sqrt(a.size) if sd > 0 else float("nan")
            gross = float(e.mean()) * point
            per_session = float(kept.mean())
            horizons[h] = {
                "sessions_with_events": int(a.size),
                "events_non_overlapping": int(e.size),
                "tradeable_per_session": round(per_session, 4),
                "mean_points": round(float(e.mean()), 5),
                "median_points": round(float(np.median(e)), 5),
                "hit_rate": round(float((e > 0).mean()), 4),
                "t_session_clustered": round(t_clustered, 3),
                "t_vs_matched_control": round(t_ctrl, 3),
                "t_naive_event_level": round(t_naive, 3),
                "ci95_session_mean_points": [round(float(a.mean() - ci), 5),
                                             round(float(a.mean() + ci), 5)],
                "effect_size_cohens_d": round(float(a.mean() / sd), 4) if sd > 0 else None,
                "control_mean_points": round(float(b.mean()), 5),
                "gross_dollars_per_trade": round(gross, 2),
                "cost_per_round_turn": round(rt_cost, 2),
                "net_dollars_per_trade": round(gross - rt_cost, 2),
                "net_dollars_per_session": round((gross - rt_cost) * per_session, 2),
                "beats_control": bool(a.mean() > b.mean()),
            }

        freq = {
            "events_total": int(raw_counts.sum()),
            "raw_events_per_session_mean": round(float(raw_counts.mean()), 4),
            "raw_events_per_session_median": float(np.median(raw_counts)),
            "p25": float(np.percentile(raw_counts, 25)),
            "p75": float(np.percentile(raw_counts, 75)),
            "max_per_session": int(raw_counts.max()) if raw_counts.size else 0,
            "pct_sessions_ge1": round(float((raw_counts >= 1).mean()), 4),
            "pct_sessions_ge2": round(float((raw_counts >= 2).mean()), 4),
            "pct_sessions_ge3": round(float((raw_counts >= 3).mean()), 4),
            "sessions": len(sessions),
        }
        #: the class is set on TRADEABLE frequency at a 15-minute hold, not on raw events
        h15 = horizons.get(15, {})
        tps = h15.get("tradeable_per_session", 0.0)
        freq["tradeable_per_session_at_h15"] = tps
        freq["opportunity_class"] = "A" if tps >= 2.0 else "B" if tps >= 0.5 else "C"
        results[name] = {"frequency": freq, "horizons": horizons}
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--instrument", default="NQ", choices=("NQ", "MNQ"))
    ap.add_argument("--split", default="dev", choices=("dev", "val", "holdout"))
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    allses = build(args.instrument)
    n = len(allses)
    d, v = int(n * 0.6), int(n * 0.8)
    part = {"dev": allses[:d], "val": allses[d:v], "holdout": allses[v:]}[args.split]
    print(f"{args.instrument} {args.split}: {len(part)} of {n} sessions "
          f"({part[0].day} .. {part[-1].day})")

    res = screen(part, args.instrument)

    #: multiple testing across every (mechanism, horizon) trial in the family
    trials, tstats = [], []
    for name, r in res.items():
        for h, d_ in r["horizons"].items():
            if d_.get("insufficient"):
                continue
            trials.append((name, h))
            tstats.append(d_["t_vs_matched_control"])
    p = MT.pvalues_from_t(np.nan_to_num(np.array(tstats), nan=0.0))
    bh = MT.benjamini_hochberg(p, alpha=0.05)
    for (name, h), pv, rej, adj in zip(trials, p, bh.rejected, bh.adjusted, strict=True):
        d_ = res[name]["horizons"][h]
        d_["p_vs_control"] = round(float(pv), 5)
        d_["bh_adjusted_p"] = round(float(adj), 5)
        #: FDR on a TWO-SIDED p-value rejects a strongly NEGATIVE result too. A mechanism
        #: that reliably loses is a finding about its inverse, not a surviving candidate, so
        #: survival additionally requires the effect to point the way the hypothesis claims.
        d_["fdr_rejected_two_sided"] = bool(rej)
        d_["survives_fdr"] = bool(rej and d_["t_vs_matched_control"] > 0)

    out = {"instrument": args.instrument, "split": args.split,
           "sessions": len(part), "trials": len(trials),
           "first_day": part[0].day, "last_day": part[-1].day,
           "seed": SEED, "results": res}
    dest = REPO / (args.out or f"research/mechanisms/{args.instrument}_{args.split}.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")

    print(f"\n{'mechanism':28}{'raw/s':>7}{'trd/s':>7}{'cls':>4}{'>=1':>6}"
          f"{'h':>4}{'$/trade':>9}{'$/sess':>9}{'t_ctrl':>8}{'FDR':>5}")
    for name, r in sorted(res.items()):
        f = r["frequency"]
        ok = [(h, d_) for h, d_ in r["horizons"].items() if not d_.get("insufficient")]
        if not ok:
            print(f"{name:28}{f['raw_events_per_session_mean']:>7.2f}{0.0:>7.2f}"
                  f"{f['opportunity_class']:>4}{f['pct_sessions_ge1']:>6.0%}"
                  f"{'-':>4}{'-':>9}{'-':>9}{'-':>8}{'-':>5}")
            continue
        #: reported at the horizon with the best NET SESSION economics, which is what the
        #: objective needs - not the best per-trade figure, which a mechanism firing twice a
        #: month can win without being deployable at all
        bh_, bd = max(ok, key=lambda kv: kv[1]["net_dollars_per_session"])
        print(f"{name:28}{f['raw_events_per_session_mean']:>7.2f}"
              f"{bd['tradeable_per_session']:>7.2f}{f['opportunity_class']:>4}"
              f"{f['pct_sessions_ge1']:>6.0%}{bh_:>4}"
              f"{bd['net_dollars_per_trade']:>9.2f}{bd['net_dollars_per_session']:>9.2f}"
              f"{bd['t_vs_matched_control']:>8.2f}"
              f"{'Y' if bd['survives_fdr'] else 'n':>5}")
    print(f"\n{len(trials)} trials, BH-FDR alpha=0.05, "
          f"{sum(1 for _, r in res.items() for d_ in r['horizons'].values() if d_.get('survives_fdr'))} "
          f"survive")
    print(f"wrote {dest.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
