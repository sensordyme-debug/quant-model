#!/usr/bin/env python
"""C-11: adversarial verification of A-17's PASS (`SW_SLEEVE` cuts the sleeve's ES5 +11.08%).

    py -3.14 scripts/verify_c11.py

A-17 (`iterate`, commit aacadaa) is the strongest positive claim of the last 24 hours and the
newest entry in any journal. No promotion is contested: `research/champion.json` is byte-identical
to its last commit and nothing today asks to move it. So the brief falls to the claim.

WHAT IS BEING ATTACKED, EXACTLY
-------------------------------
A-17's headline: a cut-only exposure switch `e_t = min(1, budget_t / |q_hat_t|)`, where `q_hat_t`
is an expanding one-step-ahead 5% quantile regression of THE SLEEVE'S OWN session return on four
strictly-pre-open tape features, cuts the sleeve's 5% expected shortfall by +11.08% against a flat
book at the same average exposure, with a 99% block bootstrap CI of [+5.76, +16.52], 3 of 3
regimes, and max drawdown 53.41% -> 42.32%.

THE FIVE LEGS, PRE-REGISTERED HERE BEFORE ANY NUMBER IS LOOKED AT
-----------------------------------------------------------------
 1. REPRODUCTION, from persisted series only. `results/a17/exposures.csv` (the four MATCHED
    schedules) and `results/a8/daily_control.csv` (the control book) are joined on `day` and every
    headline in `cuts.csv` / `books.csv` is recomputed from scratch by code that shares nothing
    with `sweep_a17.py`. A mismatch beyond 1e-9 refutes the entry on arithmetic.

 2. CAUSALITY, empirically rather than by reading alone. The code read is reported in the journal;
    the test here is the one a code read cannot do: re-score the SAME schedule shifted one session
    FORWARD (e_{t-1} applied at t). A switch that works because volatility clusters must keep most
    of its cut under a one-day lag. A switch whose cut COLLAPSES under a one-day lag is aligned to
    session t in a way that a pre-open forecast should not be, and that is a look-ahead signature.
    The anti-causal direction (e_{t+1} at t, i.e. an explicit one-day peek) is scored too, as the
    scale against which "collapses" is judged.

 3. THE BLOCK BOOTSTRAP'S BLOCK LENGTH - the leg this script exists for. A-17 resamples WHOLE
    SESSIONS IN BLOCKS OF 5. The statistic is a 5% expected shortfall: it is an average over ~118
    days that are not scattered uniformly, they are volatility clusters. If the block is shorter
    than the cluster, the bootstrap treats one crisis as many independent observations and the CI
    is too narrow BY CONSTRUCTION. Re-run the identical resampler at block = 1, 5, 10, 21, 63, 126,
    252 sessions, and at CALENDAR-YEAR blocks, and report the block length at which the 99% CI
    first contains zero. Clause 4c is a pass condition, so this is decisive for the verdict even
    though it cannot move the point estimate.

 4. THE POOLED FIGURE'S CONCENTRATION, made quantitative. A-17 states the limit in words ("negative
    in 5 of 10 years ... carried by 2018 and 2020"). Three arithmetic consequences it does not
    state: (a) leave-one-year-out on the pooled cut; (b) the EQUAL-WEIGHT-BY-YEAR cut and the
    MEDIAN year, against A-17's own ECON_MATERIAL = 5% bar; (c) where the pooled 5% tail actually
    lives, by year.

 5. THE DRAWDOWN HEADLINE'S SCALE. "-11.09 points" is a difference of two max drawdowns, and max
    drawdown is NOT scale-invariant under compounding, while the ES5 RATIO is (proved numerically
    here). The matched level M = 0.7703 is `min` over the three arms' realised mean exposure -
    a constant knowable only after the whole sample. Re-price the drawdown delta across M to show
    how much of "-11.09 points" is the switch and how much is the ex-post choice of M.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
A8 = REPO / "results" / "a8"
A17 = REPO / "results" / "a17"
OUT = REPO / "results" / "c11"
SPY_MIN = REPO / "data" / "minute_alpaca" / "SPY.parquet"

EQUITY = 1_000_000.0
TAU = 0.05
ECON_MATERIAL = 5.0
BOOT_REPS = 20_000
BOOT_ALPHA = 0.01
SEED = 17
ARMS = ("SW_SPY", "SW_SLEEVE", "SW_INVVOL")


def q05(v):
    return float(np.quantile(v, TAU))


def es05(v):
    c = np.quantile(v, TAU)
    lo = v[v <= c]
    return float(lo.mean()) if len(lo) else float("nan")


def tail_cut(new, base, fn=es05):
    b, n = fn(base), fn(new)
    if not np.isfinite(b) or b >= 0:
        return float("nan")
    return 100.0 * (1.0 - n / b)


def max_dd(ret):
    path = np.concatenate([[EQUITY], EQUITY * np.cumprod(1.0 + ret)])
    peak = np.maximum.accumulate(path)
    return -float((path / peak - 1.0).min()) * 100


def show(rows, title, note=""):
    df = pd.DataFrame(rows)
    print(f"\n--- {title}")
    if note:
        print(f"    {note}")
    with pd.option_context("display.width", 220, "display.max_columns", 60,
                           "display.float_format", lambda v: f"{v:,.4f}"):
        print(df.to_string(index=False))
    return df


# ------------------------------------------------------------------------------ leg 1: repro
def load() -> pd.DataFrame:
    for f in (A17 / "exposures.csv", A8 / "daily_control.csv"):
        if not f.exists():
            sys.exit(f"missing {f}")
    ex = pd.read_csv(A17 / "exposures.csv")
    ex["day"] = pd.to_datetime(ex["day"]).dt.date
    ctl = pd.read_csv(A8 / "daily_control.csv")
    ctl["day"] = pd.to_datetime(ctl["day"]).dt.date
    m = ex.merge(ctl[["day", "pnl", "ret", "low", "stopped"]], on="day", how="left")
    assert m["ret"].notna().all(), "a session in exposures.csv is absent from the control book"
    m["year"] = [d.year for d in m["day"]]
    return m.sort_values("day").reset_index(drop=True)


def leg1(m: pd.DataFrame) -> dict:
    pub_cuts = pd.read_csv(A17 / "cuts.csv").set_index("arm")
    pub_books = pd.read_csv(A17 / "books.csv").set_index("arm")
    ret = m["ret"].to_numpy()
    base = m["CONST"].to_numpy() * ret
    rows, worst = [], 0.0
    for a in ARMS + ("CONST",):
        e = m[a].to_numpy()
        lin = e * ret
        got = {"mean_e": float(e.mean()), "ES5_%": es05(lin) * 100, "q05_%": q05(lin) * 100,
               "max_dd_%": max_dd(lin)}
        want = {k: float(pub_books.loc[a, k]) for k in got}
        d = max(abs(got[k] - want[k]) for k in got)
        row = {"arm": a, **{f"{k}": got[k] for k in got}, "max_abs_dev_vs_books.csv": d}
        if a != "CONST":
            c_got = tail_cut(lin, base, es05)
            c_want = float(pub_cuts.loc[a, "ES5_cut_%"])
            q_got = tail_cut(lin, base, q05)
            q_want = float(pub_cuts.loc[a, "q05_cut_%"])
            dd_got = max_dd(lin) - max_dd(base)
            dd_want = float(pub_cuts.loc[a, "d_max_dd_pts"])
            d = max(d, abs(c_got - c_want), abs(q_got - q_want), abs(dd_got - dd_want))
            row.update({"ES5_cut_%": c_got, "pub_ES5_cut_%": c_want,
                        "d_max_dd_pts": dd_got, "pub_d_max_dd_pts": dd_want,
                        "max_abs_dev_vs_books.csv": d})
        worst = max(worst, d)
        rows.append(row)
    show(rows, "LEG 1 - independent reproduction from exposures.csv + daily_control.csv",
         "every column recomputed here; `pub_` columns are A-17's persisted artifacts")
    ok = worst < 1e-9
    print(f"    worst absolute deviation across all reproduced quantities: {worst:.3e}  "
          f"-> {'REPRODUCES' if ok else 'DOES NOT REPRODUCE'}")
    return {"reproduces": bool(ok), "worst_abs_dev": worst, "n_sessions": int(len(m))}


# --------------------------------------------------------------------------- leg 2: causality
def leg2(m: pd.DataFrame) -> dict:
    ret = m["ret"].to_numpy()
    rows, out = [], {}
    for a in ARMS:
        e = m[a].to_numpy()
        for name, shift in (("as published (e_t)", 0), ("LAGGED one day (e_{t-1})", 1),
                            ("PEEK one day (e_{t+1})", -1)):
            s = pd.Series(e).shift(shift)
            mk = s.notna().to_numpy()
            es = s.to_numpy()[mk]
            r = ret[mk]
            # rematch to the shifted schedule's own mean so the comparator stays honest
            const = np.full(mk.sum(), float(es.mean()))
            cut = tail_cut(es * r, const * r, es05)
            rows.append({"arm": a, "alignment": name, "n": int(mk.sum()), "mean_e": float(es.mean()),
                         "ES5_cut_%": cut})
            out[f"{a}|{shift}"] = cut
    show(rows, "LEG 2 - causality by alignment: does the cut survive a one-day lag?",
         "volatility clusters -> a lagged schedule keeps most of a REAL cut; "
         "a collapse to ~0 is a same-session-alignment (look-ahead) signature")
    for a in ARMS:
        keep = 100.0 * out[f"{a}|1"] / out[f"{a}|0"] if out[f"{a}|0"] else float("nan")
        peek = out[f"{a}|-1"]
        print(f"    {a:10s} lag-1 retains {keep:6.1f}% of the published cut; "
              f"an explicit one-day peek would give {peek:+6.2f}%")
    return out


# -------------------------------------------------------- leg 3: the bootstrap's block length
def block_boot(new, base, block, rng, reps=BOOT_REPS):
    """A-17's circular block resampler, index construction vectorised (same draws, same RNG)."""
    n = len(new)
    nb = int(np.ceil(n / block))
    offs = np.arange(block)
    draws = np.empty(reps)
    for r in range(reps):
        starts = rng.integers(0, n, size=nb)
        sel = ((starts[:, None] + offs) % n).ravel()[:n]
        draws[r] = tail_cut(new[sel], base[sel], es05)
    draws = draws[np.isfinite(draws)]
    return (float(np.percentile(draws, 100 * BOOT_ALPHA / 2)),
            float(np.percentile(draws, 100 * (1 - BOOT_ALPHA / 2))), draws)


def year_boot(new, base, years, rng, reps=BOOT_REPS):
    """Resample whole CALENDAR YEARS with replacement - the honest block for a crisis-driven tail."""
    idx = {y: np.flatnonzero(years == y) for y in np.unique(years)}
    ys = list(idx)
    draws = np.empty(reps)
    for r in range(reps):
        pick = rng.choice(ys, size=len(ys), replace=True)
        sel = np.concatenate([idx[y] for y in pick])
        draws[r] = tail_cut(new[sel], base[sel], es05)
    draws = draws[np.isfinite(draws)]
    return (float(np.percentile(draws, 100 * BOOT_ALPHA / 2)),
            float(np.percentile(draws, 100 * (1 - BOOT_ALPHA / 2))), draws)


def acf(x, lmax: int) -> np.ndarray:
    x = np.asarray(x, float) - np.mean(x)
    d = float((x * x).sum())
    return np.array([float((x[:len(x) - k] * x[k:]).sum()) / d for k in range(lmax + 1)])


def dependence(m: pd.DataFrame) -> dict:
    """The block length is not a free choice: it has to reach the schedule's own memory.

    A block bootstrap whose block is short relative to the resampled series' integrated
    autocorrelation time treats one episode as many independent observations, so the CI is
    too narrow BY CONSTRUCTION. This measures the number A-17's block=5 has to be judged against.
    """
    rows, out = [], {}
    for a in ARMS:
        s = acf(m[a].to_numpy(), 400)
        neg = int(np.argmax(s < 0)) if (s < 0).any() else len(s)
        tau = float(1 + 2 * s[1:neg].sum())            # integrated autocorrelation time
        hl = int(np.argmax(s < 0.5)) if (s < 0.5).any() else -1
        out[a] = tau
        rows.append({"series": a, "acf_1": s[1], "acf_5": s[5], "acf_21": s[21], "acf_63": s[63],
                     "acf_126": s[126], "half_life_lags": hl, "integrated_tau_sessions": tau})
    s = acf(np.abs(m["ret"].to_numpy()), 400)
    rows.append({"series": "|sleeve ret|", "acf_1": s[1], "acf_5": s[5], "acf_21": s[21],
                 "acf_63": s[63], "acf_126": s[126],
                 "half_life_lags": int(np.argmax(s < 0.5)), "integrated_tau_sessions": float("nan")})
    show(rows, "LEG 3a - the memory of the series the bootstrap resamples",
         "the block has to reach the integrated tau; A-17 used 5")
    return out


def leg3(m: pd.DataFrame) -> dict:
    taus = dependence(m)
    ret = m["ret"].to_numpy()
    years = m["year"].to_numpy()
    base = m["CONST"].to_numpy() * ret
    blocks = (1, 5, 10, 13, 21, 30, 59, 63, 90, 126, 252)
    rows, verdict = [], {}
    for a in ARMS:
        lin = m[a].to_numpy() * ret
        point = tail_cut(lin, base, es05)
        first_zero = None
        for block in blocks:
            lo, hi, draws = block_boot(lin, base, block, np.random.default_rng(SEED))
            exc = bool(lo > 0 or hi < 0)
            if not exc and first_zero is None:
                first_zero = block
            rows.append({"arm": a, "block_sessions": str(block), "cut_%": point,
                         "ci_lo_%": lo, "ci_hi_%": hi, "excludes_zero": exc,
                         "P(cut<ECON_MATERIAL)_%": 100.0 * float((draws < ECON_MATERIAL).mean()),
                         "published_leg": block == 5,
                         "~integrated_tau": abs(block - taus[a]) < 6})
        lo, hi, draws = year_boot(lin, base, years, np.random.default_rng(SEED))
        exc = bool(lo > 0 or hi < 0)
        rows.append({"arm": a, "block_sessions": "calendar-year", "cut_%": point,
                     "ci_lo_%": lo, "ci_hi_%": hi, "excludes_zero": exc,
                     "P(cut<ECON_MATERIAL)_%": 100.0 * float((draws < ECON_MATERIAL).mean()),
                     "published_leg": False, "~integrated_tau": False})
        verdict[a] = {"integrated_tau_sessions": taus[a],
                      "first_block_including_zero": first_zero,
                      "year_block_excludes_zero": exc, "year_ci": [lo, hi]}
    df = show(rows, "LEG 3 - clause 4c re-run across block lengths (identical resampler, 20k reps, 99%)",
              "A-17's published leg is block=5; `~integrated_tau` flags the block that reaches "
              "the schedule's own memory")
    df.to_csv(OUT / "block_length.csv", index=False)
    return verdict


# ------------------------------------------------------------ leg 4: where the pooled cut lives
def leg4(m: pd.DataFrame) -> dict:
    ret = m["ret"].to_numpy()
    years = m["year"].to_numpy()
    base = m["CONST"].to_numpy() * ret
    lin = m["SW_SLEEVE"].to_numpy() * ret
    full = tail_cut(lin, base, es05)

    # (c) where the pooled 5% tail lives
    thr = np.quantile(base, TAU)
    tail_mask = base <= thr
    loc = [{"year": int(y), "sessions": int((years == y).sum()),
            "in_pooled_5%_tail": int(tail_mask[years == y].sum()),
            "share_of_tail_%": 100.0 * tail_mask[years == y].sum() / tail_mask.sum()}
           for y in sorted(set(years.tolist()))]
    show(loc, "LEG 4c - where the pooled 5% tail actually lives (CONST's own worst sessions)",
         f"{int(tail_mask.sum())} sessions make up the statistic every headline is an average over")

    # (a) leave-one-year-out, plus the two named carriers
    rows = [{"dropped": "nothing (published)", "n": int(len(lin)), "ES5_cut_%": full,
             "delta_vs_full": 0.0, "clears_5%_bar": full >= ECON_MATERIAL}]
    drops = [[y] for y in sorted(set(years.tolist()))] + [[2018, 2020]]
    for dy in drops:
        k = ~np.isin(years, dy)
        c = tail_cut(lin[k], base[k], es05)
        rows.append({"dropped": "+".join(str(x) for x in dy), "n": int(k.sum()), "ES5_cut_%": c,
                     "delta_vs_full": c - full, "clears_5%_bar": c >= ECON_MATERIAL})
    lo1 = show(rows, "LEG 4a - leave-one-year-out on the pooled ES5 cut",
               f"A-17's own ECON_MATERIAL bar is {ECON_MATERIAL}%")

    # (b) year-balanced readings
    yr = []
    for y in sorted(set(years.tolist())):
        k = years == y
        if k.sum() < 60:
            continue
        yr.append({"year": int(y), "n": int(k.sum()), "ES5_cut_%": tail_cut(lin[k], base[k], es05)})
    ydf = pd.DataFrame(yr)
    npos = int((ydf["ES5_cut_%"] > 0).sum())
    eqw, med = float(ydf["ES5_cut_%"].mean()), float(ydf["ES5_cut_%"].median())
    print(f"\nLEG 4b - year-balanced readings of the SAME schedule:")
    print(f"    pooled (session-weighted) cut ......... {full:+7.2f}%   clears {ECON_MATERIAL}% bar: "
          f"{full >= ECON_MATERIAL}")
    print(f"    equal-weight-by-year mean cut ......... {eqw:+7.2f}%   clears {ECON_MATERIAL}% bar: "
          f"{eqw >= ECON_MATERIAL}")
    print(f"    MEDIAN year's cut ..................... {med:+7.2f}%   clears {ECON_MATERIAL}% bar: "
          f"{med >= ECON_MATERIAL}")
    print(f"    years with a positive cut ............. {npos} of {len(ydf)}  "
          f"(two-sided sign test p = {sign_p(npos, len(ydf)):.3f})")
    lo1.to_csv(OUT / "leave_one_year_out.csv", index=False)
    return {"pooled_%": full, "equal_weight_year_%": eqw, "median_year_%": med,
            "years_positive": npos, "years": int(len(ydf)),
            "sign_test_p": sign_p(npos, len(ydf)),
            "drop_2018_2020_%": float(lo1[lo1.dropped == "2018+2020"].iloc[0]["ES5_cut_%"])}


def sign_p(k: int, n: int) -> float:
    from math import comb
    tail = sum(comb(n, i) for i in range(0, min(k, n - k) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


# --------------------------------------------------------------- leg 5: the drawdown's scale
def leg5(m: pd.DataFrame) -> dict:
    ret = m["ret"].to_numpy()
    e = m["SW_SLEEVE"].to_numpy()
    shape = e / e.mean()                       # the switch's SHAPE, mean 1 by construction
    rows = []
    for M in (0.40, 0.60, 0.7703, 0.90, 1.00, 1.30):
        arm, const = shape * M * ret, M * ret
        rows.append({"matched_M": M, "arm_dd_%": max_dd(arm), "const_dd_%": max_dd(const),
                     "d_max_dd_pts": max_dd(arm) - max_dd(const),
                     "ES5_cut_%": tail_cut(arm, const, es05),
                     "published_M": abs(M - 0.7703) < 1e-4})
    df = show(rows, "LEG 5 - the drawdown headline across the matched level M",
              "M = min over the three arms' realised mean exposure, i.e. an EX-POST constant; "
              "the ES5 cut is exactly scale-invariant, the drawdown delta is not")
    spread = float(df["d_max_dd_pts"].max() - df["d_max_dd_pts"].min())
    es_spread = float(df["ES5_cut_%"].max() - df["ES5_cut_%"].min())
    print(f"    drawdown delta ranges {df['d_max_dd_pts'].min():+.2f} .. "
          f"{df['d_max_dd_pts'].max():+.2f} points across M (spread {spread:.2f} points); "
          f"ES5 cut spread across the same M: {es_spread:.2e} points")
    df.to_csv(OUT / "drawdown_scale.csv", index=False)
    return {"dd_pts_spread_across_M": spread, "es5_cut_spread_across_M": es_spread}


# ----------------------------------------------------- extra: the SPY panel's session boundary
def leg6() -> dict:
    """A-17's feature panel keeps every Alpaca bar with hhmm >= '09:30' - including post-market."""
    if not SPY_MIN.exists():
        return {"checked": False}
    df = pd.read_parquet(SPY_MIN).tz_convert("America/New_York")
    hhmm = df.index.strftime("%H:%M")
    day = df.index.strftime("%Y-%m-%d")
    keep = hhmm >= "09:30"
    post = keep & (hhmm >= "16:00")
    s = pd.DataFrame({"day": day[keep], "hhmm": hhmm[keep]})
    last = s.groupby("day")["hhmm"].max()
    n_post_close = int((last >= "16:00").sum())
    print(f"\n--- LEG 6 - the SPY feature panel's session boundary (`hhmm >= '09:30'`)")
    print(f"    bars kept: {int(keep.sum()):,}; of those {int(post.sum()):,} are at or after 16:00")
    print(f"    sessions whose LAST kept bar is post-16:00: {n_post_close:,} of {len(last):,} "
          f"({100.0 * n_post_close / len(last):.1f}%)")
    if n_post_close:
        print("    DEFECT: `spy_oc` (SW_SPY's quantile TARGET) and `rng_same` are extended-hours")
        print("    figures rather than 09:30-16:00 ones. Not look-ahead - a pre-open forecast may")
        print("    legally read yesterday's post-market - but the wrong definition of a close.")
    else:
        print("    NO DEFECT. The hypothesis this leg was written to test (D-6 found 22,081")
        print("    post-market rows in the Alpaca store, so `hhmm >= '09:30'` should admit them)")
        print("    is FALSE for SPY: the filter's upper edge is never exercised and `spy_oc` is a")
        print("    true regular-hours open-to-close. Recorded as a refuted attack, not a finding.")
    return {"checked": True, "bars_kept": int(keep.sum()), "bars_post_1600": int(post.sum()),
            "sessions_last_bar_post_close": n_post_close, "sessions": int(len(last))}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print("C-11 - adversarial verification of A-17's PASS (SW_SLEEVE, ES5 cut +11.08%)")
    m = load()
    print(f"[data] {len(m)} matched sessions, {m['day'].iloc[0]} .. {m['day'].iloc[-1]}")
    v = {"leg1_reproduction": leg1(m), "leg2_causality": leg2(m), "leg3_block_length": leg3(m),
         "leg4_concentration": leg4(m), "leg5_drawdown_scale": leg5(m), "leg6_spy_panel": leg6()}
    (OUT / "verdict.json").write_text(json.dumps(v, indent=1, default=float), encoding="utf-8")
    print(f"\n[out] {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
