"""O-9 - COSTING O-8's VaR RESULT: is `rn_half` a DE-RISK SWITCH worth having?

WHY THIS ITEM, AND WHY IT IS THE LAST ONE THIS SCOPE OWNS.

O-8 refused the chain's asymmetry as a tail forecaster (pooled DM t -0.401, declared sign wrong
at 4 of 5 clocks) but its SECONDARY read was positive, monotone and unanimous: adding `rn_half`
to a tape-only 5% VaR model cut the out-of-sample pinball loss 3.0% to 8.0%, RISING THROUGH THE
DAY, at 5 of 5 clocks. That number is a STATISTICAL improvement in a loss function. It has never
been converted into money, and a loss-function improvement is not a product.

Every other consumer of this signal is already closed:
  * O-6 proved `rn_half` forecasts the magnitude of the remaining move incrementally to the tape.
  * O-7 proved that skill is general across volatility states.
  * A-15 REFUSED it as a position-SIZE input, on mechanism: the intraday sleeve is paid for the
    volatility SURPRISE (+$2,651/day per sd, t +8.41) and not for the forecastable part
    (-$230/day, t -0.73). Scaling size by a predictable quantity scales the part that does not pay.
  * OWNER-5 records that the Theta VALUE-tier ask has therefore lost its stated justification.

A DE-RISK SWITCH IS A DIFFERENT FUNCTIONAL AND THAT IS THE WHOLE ITEM. A-15's refusal is about
the MEAN of a book's P&L - sizing up where the forecast says "loud" does not pay because the mean
is paid by surprise. A de-risk switch is not paid by the mean; it is paid by the LOWER QUANTILE
alone, which is exactly the object O-8 measured skill in, and the daily track already ships one
(S-40's crisis switch), so the shape has a consumer in this repository.

HYPOTHESIS. The 0DTE chain's `rn_half`, consumed through the 5% VaR model of O-8, produces an
intraday de-risk switch whose reduction in the downside tail of the resulting book is (a) larger
than the identical switch built from the realized tape alone, and (b) not reproducible by
de-levering unconditionally to the same average exposure.

THE PRE-REGISTERED DESIGN, IN FULL, BEFORE ANY RUN.

  0. NO NEW DATA, NO NEW FEATURE, NO NEW CLOCK, NO NEW ESTIMATOR. Theta is HTTP 403 on
     `history/quote` (FREE tier), so the store is frozen at 1,891 sessions ending 2026-09-10 and
     this item is answerable with the subscription lapsed - which is the point. The chain side is
     O-5's frozen cache; the tape, clocks, burn-in, expanding-window protocol, regimes and the
     quantile solver are IMPORTED from `sweep_o6.py` / `sweep_o8.py` and not re-implemented.

  1. THE TWO MODELS, exactly O-8's M0 and M1 - the asymmetry block M2 is REFUSED and is absent:
       M0  TAPE          rv_sofar, rng_sofar, rv20, absret_1
       M1  TAPE+rn_half  M0 plus the chain's symmetric magnitude
     tau = 0.05, expanding window, one-step-ahead, 250-session burn-in, per clock. Identical to
     O-8, so Stage C's pinball numbers here must reproduce O-8's `d_pin_M1vM0_%` column.

  2. THE SWITCH, declared before any run. The forecast 5% quantile is a risk budget statement,
     so the switch is inverse-risk and it only ever CUTS:

         budget_t = median(|q_hat_s|) over s < t, expanding, >= 60 prior sessions   [CAUSAL]
         e_raw_t  = min(1.0, budget_t / |q_hat_t|)

     The cap at 1.0 is not cosmetic: A-15 refused sizing UP on a forecastable quantity, so a
     switch that levers up on calm days would be re-running a refused claim. This one de-risks
     on loud days and is flat otherwise. `budget_t` uses an EXPANDING median of PAST forecasts -
     O-8's Stage D used a full-sample median, which is a small but real look-ahead, and Gate 3
     asserts the fix.

  3. THE CONTROL THE BACKLOG NAMES, AND WHY IT IS THE RIGHT ONE. A switch that de-risks on
     average "wins" on any book by simply holding less, so every headline is quoted at MATCHED
     AVERAGE EXPOSURE. The matching level is M = min(mean e_raw over SW0, SW1), each book is
     scaled by M / mean(e_raw), and CONST is a flat book at exposure M - i.e. literally "an
     unconditional de-risk of the same average exposure".

     A note on the frontier control that is NOT used, stated in advance so its absence is not a
     silent choice. The stronger control would match mean P&L rather than mean exposure. It
     cannot be resolved on this sample: the forward return's mean is +1.46 to +0.25 bps against
     an sd of 75 to 42 bps, so the standard error of the mean over ~1,600 sessions is ~1.9 bps -
     LARGER THAN THE MEAN ITSELF. Matching on it would be matching on noise. Instead the mean
     P&L of every book is reported WITH its standard error, together with cov(e, fwd), so the
     reader can see directly that at matched exposure the mean is unchanged within noise - which
     is what makes matched-exposure and matched-mean-P&L the same comparison here.

  4. THE DECISIVE TEST: SW1 against SW0 - the chain against the tape, both switches, same
     construction, same average exposure. Judged on the 5% quantile of the book's daily return.
     PASS on this leg requires ALL THREE:
       (a) SW1's 5% tail smaller in magnitude than SW0's at >= 4 of 5 clocks;
       (b) the average relative tail cut across the five clocks >= 5% (ECON_MATERIAL, O-8's
           constant, unchanged);
       (c) a 99% block-bootstrap confidence interval on that average excluding zero, resampling
           WHOLE SESSIONS (all clocks together, block length 5) so cross-clock and serial
           dependence survive the resample.

  5. THE REGIMES LEG: the two-of-three rule at >= 4 of 5 clocks, on 2016-2019 / 2020-2023 /
     2024-2026. Judged on ES5 (the mean of the worst 5%) and NOT on the 5% quantile, declared
     here and for one reason: a regime cell holds ~550 sessions, so its 5% quantile is a single
     order statistic around rank 27 and is mostly noise, while ES5 averages that whole tail. The
     q05 figure is printed beside it and is descriptive.

  6. TWO CONTROLS THAT CAN ONLY DESTROY A PASS AND CAN NEVER CREATE ONE.
     Control A - STANDALONE VALUE. SW1 against CONST at matched average exposure. If the switch
       does not beat a flat book at the same exposure, there is nothing for the chain to be
       incremental TO, and the verdict is downgraded whatever leg 4 says.
     Control B - TIMING, NOT DISPERSION. A non-constant exposure series changes a book's tail
       even with random timing, because a scale mixture is not the scale it averages to. So the
       q_hat series is PERMUTED across sessions within a clock - marginal distribution of
       exposure preserved exactly, timing destroyed - 200 times, and the real switch must beat
       the 95th PERCENTILE of the placebo's tail cut at >= 4 of 5 clocks. Beating a single
       shuffled draw would prove nothing.

  7. NO POST-HOC BUDGET, NO POST-HOC CAP, NO POST-HOC CLOCK, NO POST-HOC TAU, NO POST-HOC
     QUANTILE. The switch's functional form, the cap, the matching rule, the material bar and the
     bootstrap are all fixed above. Anything discovered after the first run is a finding.

WHAT EACH OUTCOME MEANS, WRITTEN DOWN BEFORE THE RUN.

  PASS: the store has a product after all - not a size scaler (A-15 closed that) but a
  drawdown-avoidance switch, and it is the fresh, costed justification OWNER-5 asks for before
  the VALUE tier is bought. This track would still ship nothing; it would hand a pre-registered
  item to whoever owns de-risking.

  REFUSED: O-8's 3-8% pinball improvement is real and worth no money, every consumer of
  `rn_half` is now closed on evidence rather than exhaustion, the O-track has no open item, and
  `research-options` should be unscheduled rather than left to spend tokens.

Run (default python, NOT py -3.11, which has no pyarrow):

    python scripts/sweep_o9.py --record
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sweep_o6 import (  # noqa: E402  - the measurement side is imported, never re-implemented
    BURN_IN,
    CLOCKS,
    REGIMES,
    build_panel,
    fmt,
    gate0,
    record,
)
from sweep_o8 import (  # noqa: E402  - the quantile machinery is O-8's, unchanged
    M0,
    M1,
    TAU_LO,
    ECON_MATERIAL,
    CLOCK_MAJORITY,
    MIN_CELL,
    design,
    gate_solver,
    oos_quantiles,
    panel,
    pinball,
)

CAP = 1.0              # the switch only ever CUTS exposure (A-15 refused sizing UP)
MIN_BUDGET_OBS = 60    # expanding-median warm-up before the switch is allowed to trade
BOOT_REPS = 2000       # block-bootstrap replicates for the decisive CI
BOOT_BLOCK = 5         # sessions per block
BOOT_ALPHA = 0.01      # 99% CI, matching the Bonferroni posture O-6/O-7/O-8 used
PLACEBO_REPS = 200     # permutations of q_hat for Control B
PLACEBO_PCTL = 95.0    # the real switch must beat this percentile of the placebo
SEED = 20260913


# ------------------------------------------------------------------ the switch
def exposure(q: np.ndarray) -> np.ndarray:
    """budget_t = expanding median of PAST |q_hat|; e_t = min(CAP, budget_t/|q_hat_t|).

    NaN until MIN_BUDGET_OBS prior forecasts exist. Strictly causal by construction: the
    `.shift(1)` is what makes budget_t a function of s < t only, and Gate 3 re-asserts it.
    """
    a = pd.Series(np.abs(q))
    budget = a.expanding(min_periods=MIN_BUDGET_OBS).median().shift(1)
    e = np.minimum(CAP, budget.to_numpy() / np.maximum(np.abs(q), 1e-12))
    return e


def books(d: pd.DataFrame) -> dict[str, np.ndarray]:
    """SW0, SW1 and CONST on one clock, all at the SAME mean exposure."""
    e0, e1 = exposure(d.q0.to_numpy()), exposure(d.q1.to_numpy())
    m = np.isfinite(e0) & np.isfinite(e1)
    e0, e1, y = e0[m], e1[m], d.fwd.to_numpy()[m]
    lvl = float(min(e0.mean(), e1.mean()))          # the matched average exposure
    e0 = e0 * (lvl / e0.mean())
    e1 = e1 * (lvl / e1.mean())
    return {"mask": m, "level": lvl, "e0": e0, "e1": e1, "y": y,
            "SW0": e0 * y, "SW1": e1 * y, "CONST": np.full(len(y), lvl) * y}


def q05(v: np.ndarray) -> float:
    return float(np.quantile(v, 0.05))


def es05(v: np.ndarray) -> float:
    c = np.quantile(v, 0.05)
    lo = v[v <= c]
    return float(lo.mean()) if len(lo) else float("nan")


def tail_cut(new: np.ndarray, base: np.ndarray, fn=q05) -> float:
    """Percent by which `new` SHRINKS the (negative) lower tail of `base`. Positive = better."""
    b, n = fn(base), fn(new)
    if not np.isfinite(b) or b >= 0:
        return float("nan")
    return 100.0 * (1.0 - n / b)


# ------------------------------------------------------------------ stage C (reproduce O-8)
def stage_c(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, keep = [], []
    for clock in CLOCKS:
        d = df[df.clock == clock].reset_index(drop=True)
        q0 = oos_quantiles(d, M0, TAU_LO)
        q1 = oos_quantiles(d, M1, TAU_LO)
        m = np.isfinite(q0) & np.isfinite(q1)
        d = d.loc[m].copy()
        d["q0"], d["q1"] = q0[m], q1[m]
        y = d.fwd.to_numpy()
        l0 = pinball(y, d.q0.to_numpy(), TAU_LO)
        l1 = pinball(y, d.q1.to_numpy(), TAU_LO)
        keep.append(d)
        rows.append({"clock": clock, "n_oos": len(d),
                     "pin_M0_tape": float(l0.mean()), "pin_M1_+half": float(l1.mean()),
                     "d_pin_M1vM0_%": 100.0 * (l1.mean() / l0.mean() - 1.0),
                     "breach_M0_%": 100.0 * float((y < d.q0.to_numpy()).mean()),
                     "breach_M1_%": 100.0 * float((y < d.q1.to_numpy()).mean())})
    return pd.DataFrame(rows), pd.concat(keep, ignore_index=True)


# ------------------------------------------------------------------ gate 3 (causality + match)
def gate3(oos: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for clock in CLOCKS:
        d = oos[oos.clock == clock].reset_index(drop=True)
        b = books(d)
        rows.append({"check": f"mean exposure matched SW0 vs SW1 {clock}",
                     "value": float(abs(b["e0"].mean() - b["e1"].mean())), "target": 0.0,
                     "ok": bool(abs(b["e0"].mean() - b["e1"].mean()) < 1e-9)})
        # causality: recomputing the budget from a series whose FUTURE is destroyed must not
        # change a single exposure the switch actually used.
        q = d.q1.to_numpy().copy()
        cut = len(q) // 2
        e_full = exposure(q)[:cut]
        q_trunc = q[:cut]
        e_trunc = exposure(q_trunc)
        same = np.allclose(e_full, e_trunc, equal_nan=True)
        rows.append({"check": f"budget_t independent of s>=t {clock}",
                     "value": float(np.nanmax(np.abs(e_full - e_trunc))) if len(e_full) else 0.0,
                     "target": 0.0, "ok": bool(same)})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ stage D (the economics)
def stage_d(oos: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    rows, wide = [], {}
    for clock in CLOCKS:
        d = oos[oos.clock == clock].reset_index(drop=True)
        b = books(d)
        d = d.loc[b["mask"]].copy()
        y = b["y"]
        out = {"clock": clock, "n": len(y), "mean_exposure": b["level"],
               "sd_exposure_SW1": float(b["e1"].std()),
               "corr_e1_absfwd": float(np.corrcoef(b["e1"], np.abs(y))[0, 1])}
        for lab in ("CONST", "SW0", "SW1"):
            v = b[lab]
            out[f"mean_{lab}_bps"] = 1e4 * float(v.mean())
            out[f"se_mean_{lab}_bps"] = 1e4 * float(v.std(ddof=1) / np.sqrt(len(v)))
            out[f"q05_{lab}_bps"] = 1e4 * q05(v)
            out[f"es05_{lab}_bps"] = 1e4 * es05(v)
            out[f"sd_{lab}_bps"] = 1e4 * float(v.std())
        out["cut_q05_SW1vSW0_%"] = tail_cut(b["SW1"], b["SW0"], q05)
        out["cut_es05_SW1vSW0_%"] = tail_cut(b["SW1"], b["SW0"], es05)
        out["cut_q05_SW1vCONST_%"] = tail_cut(b["SW1"], b["CONST"], q05)
        out["cut_q05_SW0vCONST_%"] = tail_cut(b["SW0"], b["CONST"], q05)
        out["clock_won"] = bool(out["cut_q05_SW1vSW0_%"] > 0)
        out["ctrlA_beats_const"] = bool(out["cut_q05_SW1vCONST_%"] > 0)
        # regimes, judged on ES5 as declared
        d["_sw0"], d["_sw1"] = b["SW0"], b["SW1"]
        wins = 0
        for name in REGIMES:
            g = d[d.regime == name]
            out[f"{name}_n"] = len(g)
            if len(g) < MIN_CELL:
                out[f"{name}_cut_es05_%"] = np.nan
                continue
            c = tail_cut(g._sw1.to_numpy(), g._sw0.to_numpy(), es05)
            out[f"{name}_cut_es05_%"] = c
            wins += int(c > 0)
        out["regimes_won"] = wins
        rows.append(out)
        wide[clock] = {"date": d.date.to_numpy(), "SW0": b["SW0"], "SW1": b["SW1"],
                       "CONST": b["CONST"], "q1": d.q1.to_numpy(), "y": y, "e1": b["e1"]}
    return pd.DataFrame(rows), wide


# ------------------------------------------------------------------ the block bootstrap
def bootstrap(wide: dict, rng: np.random.Generator, fn=q05) -> dict:
    """99% CI on the AVERAGE relative tail cut (SW1 vs SW0) across clocks.

    Resamples WHOLE SESSIONS in blocks of BOOT_BLOCK, so a replicate keeps both the cross-clock
    dependence within a day and the serial dependence across days. `fn` is the tail functional:
    q05 is the DECLARED headline; es05 is run only as a labelled secondary that cannot move the
    verdict (it is this design's REGIMES statistic, not its decisive one).
    """
    dates = sorted(set().union(*[set(w["date"]) for w in wide.values()]))
    pos = {dt: i for i, dt in enumerate(dates)}
    nd = len(dates)
    cols = {}
    for clock, w in wide.items():
        a0, a1 = np.full(nd, np.nan), np.full(nd, np.nan)
        idx = np.array([pos[dt] for dt in w["date"]])
        a0[idx], a1[idx] = w["SW0"], w["SW1"]
        cols[clock] = (a0, a1)

    def avg_cut(sel: np.ndarray) -> float:
        cuts = []
        for clock in CLOCKS:
            a0, a1 = cols[clock]
            s0, s1 = a0[sel], a1[sel]
            m = np.isfinite(s0) & np.isfinite(s1)
            if m.sum() < 200:
                continue
            cuts.append(tail_cut(s1[m], s0[m], fn))
        c = [x for x in cuts if np.isfinite(x)]
        return float(np.mean(c)) if c else float("nan")

    point = avg_cut(np.arange(nd))
    nblocks = int(np.ceil(nd / BOOT_BLOCK))
    draws = np.empty(BOOT_REPS)
    for r in range(BOOT_REPS):
        starts = rng.integers(0, nd, size=nblocks)
        sel = np.concatenate([np.arange(s, s + BOOT_BLOCK) % nd for s in starts])[:nd]
        draws[r] = avg_cut(sel)
    draws = draws[np.isfinite(draws)]
    lo = float(np.percentile(draws, 100.0 * BOOT_ALPHA / 2.0))
    hi = float(np.percentile(draws, 100.0 * (1.0 - BOOT_ALPHA / 2.0)))
    return {"stat": fn.__name__, "avg_cut_q05_%": point, "ci_lo_%": lo, "ci_hi_%": hi,
            "ci_excludes_zero": bool(lo > 0.0 or hi < 0.0), "reps": int(len(draws)),
            "sessions": nd}


# ------------------------------------------------------------------ control B (the placebo)
def placebo(wide: dict, rng: np.random.Generator) -> pd.DataFrame:
    """Permute q_hat across sessions: same exposure distribution, no timing. 200 draws."""
    rows = []
    for clock in CLOCKS:
        w = wide[clock]
        y, real = w["y"], w["SW1"]
        real_cut = tail_cut(real, w["CONST"], q05)
        lvl = float(w["e1"].mean())
        draws = np.empty(PLACEBO_REPS)
        for r in range(PLACEBO_REPS):
            q = rng.permutation(w["q1"])
            e = exposure(q)
            m = np.isfinite(e)
            e = e * (lvl / e[m].mean())
            v = np.where(m, e * y, np.nan)
            v = v[np.isfinite(v)]
            const = np.full(len(v), lvl) * y[m]
            draws[r] = tail_cut(v, const, q05)
        draws = draws[np.isfinite(draws)]
        bar = float(np.percentile(draws, PLACEBO_PCTL))
        rows.append({"clock": clock, "real_cut_vs_CONST_%": real_cut,
                     "placebo_mean_%": float(draws.mean()),
                     f"placebo_p{int(PLACEBO_PCTL)}_%": bar,
                     "beats_placebo": bool(real_cut > bar), "draws": int(len(draws))})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--record", action="store_true", help="append DIAGNOSTIC rows to the ledger")
    args = ap.parse_args()
    rng = np.random.default_rng(SEED)

    raw = build_panel()
    g0, g0_ok = gate0(raw)
    print("=== GATE 0 (imported from O-6: O-5's control must reproduce) ===")
    print(fmt(g0))
    if not g0_ok:
        print("GATE 0 FAILED - stopping.")
        return 1

    df = panel()
    start, end = df.date.min(), df.date.max()
    print(f"\npanel: {len(df):,} feature-complete rows  {df.date.nunique():,} sessions  "
          f"{start}..{end}")

    print("\n=== GATE 1 + GATE 2 (O-8's solver and calibration gates, unchanged) ===")
    gs = gate_solver(df)
    print(fmt(gs))
    if not bool(gs.ok.all()):
        print("SOLVER GATE FAILED - stopping.")
        return 1

    print(f"\n=== STAGE C: OOS 5% VaR, M1 vs M0 - must reproduce O-8's d_pin_M1vM0_% ===")
    tc, oos = stage_c(df)
    print(fmt(tc))

    print("\n=== GATE 3 (new): the switch is causal and the books are exposure-matched ===")
    g3 = gate3(oos)
    print(fmt(g3))
    if not bool(g3.ok.all()):
        print("GATE 3 FAILED - stopping.")
        return 1

    print("\n=== STAGE D (DECISIVE): the de-risk switch, at matched average exposure ===")
    td, wide = stage_d(oos)
    show = ["clock", "n", "mean_exposure", "corr_e1_absfwd", "mean_CONST_bps", "mean_SW1_bps",
            "se_mean_SW1_bps", "q05_CONST_bps", "q05_SW0_bps", "q05_SW1_bps",
            "cut_q05_SW1vSW0_%", "cut_es05_SW1vSW0_%", "cut_q05_SW0vCONST_%",
            "cut_q05_SW1vCONST_%", "regimes_won", "clock_won"]
    print(fmt(td[show]))
    print("\n  regime detail (ES5 cut, SW1 vs SW0 - the declared regimes statistic):")
    print(fmt(td[["clock"] + [f"{n}_cut_es05_%" for n in REGIMES]
                 + [f"{n}_n" for n in REGIMES]]))

    print("\n=== THE DECISIVE BOOTSTRAP (99% CI, whole sessions, blocks of 5) ===")
    bs = bootstrap(wide, rng)
    print(f"  average q05 cut SW1 vs SW0 across 5 clocks: {bs['avg_cut_q05_%']:+.3f}%")
    print(f"  99% CI [{bs['ci_lo_%']:+.3f}%, {bs['ci_hi_%']:+.3f}%]   "
          f"excludes zero: {bs['ci_excludes_zero']}   ({bs['reps']} reps, "
          f"{bs['sessions']:,} sessions)")

    print("\n--- SECONDARY, LABELLED, AND UNABLE TO MOVE THE VERDICT: the same bootstrap on")
    print("    ES5 (mean of the worst 5%). ES5 is this design's REGIMES statistic, declared for")
    print("    that leg because a 5% quantile on a ~550-row cell is one order statistic. It is")
    print("    NOT the decisive statistic and is reported only to show whether the refusal")
    print("    below survives a change to the more stable tail estimator.")
    bs_es = bootstrap(wide, np.random.default_rng(SEED + 1), es05)
    print(f"  average ES5 cut SW1 vs SW0 across 5 clocks: {bs_es['avg_cut_q05_%']:+.3f}%")
    print(f"  99% CI [{bs_es['ci_lo_%']:+.3f}%, {bs_es['ci_hi_%']:+.3f}%]   "
          f"excludes zero: {bs_es['ci_excludes_zero']}")

    print("\n=== CONTROL B (placebo: same exposure distribution, timing destroyed) ===")
    pb = placebo(wide, rng)
    print(fmt(pb))

    clocks_won = int(td.clock_won.sum())
    leg_a = clocks_won >= CLOCK_MAJORITY
    leg_b = bool(bs["avg_cut_q05_%"] >= 100.0 * ECON_MATERIAL)
    leg_c = bool(bs["ci_excludes_zero"] and bs["avg_cut_q05_%"] > 0)
    decisive = bool(leg_a and leg_b and leg_c)
    regimes_ok = int((td.regimes_won >= 2).sum()) >= CLOCK_MAJORITY
    ctrlA = int(td.ctrlA_beats_const.sum()) >= CLOCK_MAJORITY
    ctrlB = int(pb.beats_placebo.sum()) >= CLOCK_MAJORITY

    final = "PASS" if (decisive and regimes_ok) else ("PARTIAL" if regimes_ok else "REFUSED")
    downgraded = ""
    if final == "PASS" and not (ctrlA and ctrlB):
        final, downgraded = "PARTIAL", " (downgraded by a control)"

    v = {"clocks_won_SW1vSW0": clocks_won, "leg_a_clocks": leg_a,
         "avg_cut_q05_%": bs["avg_cut_q05_%"], "leg_b_material": leg_b,
         "ci_lo_%": bs["ci_lo_%"], "ci_hi_%": bs["ci_hi_%"], "leg_c_bootstrap": leg_c,
         "decisive_leg": decisive,
         "clocks_2of3_regimes": int((td.regimes_won >= 2).sum()), "regimes_leg": regimes_ok,
         "ctrlA_standalone_clocks": int(td.ctrlA_beats_const.sum()), "ctrlA_ok": ctrlA,
         "ctrlB_placebo_clocks": int(pb.beats_placebo.sum()), "ctrlB_ok": ctrlB,
         "verdict": final}

    print("\n" + "=" * 78)
    print(f"  leg (a) SW1 beats SW0 at >= {CLOCK_MAJORITY}/5 clocks: {leg_a} ({clocks_won}/5)")
    print(f"  leg (b) average cut >= {100.0 * ECON_MATERIAL:.0f}%: {leg_b} "
          f"({bs['avg_cut_q05_%']:+.3f}%)")
    print(f"  leg (c) 99% CI excludes zero: {leg_c}")
    print(f"  regimes, 2-of-3 at >= {CLOCK_MAJORITY}/5 clocks: {regimes_ok} "
          f"({v['clocks_2of3_regimes']}/5)")
    print(f"  control A, switch beats a flat book at same exposure: {ctrlA} "
          f"({v['ctrlA_standalone_clocks']}/5)")
    print(f"  control B, real timing beats the p{int(PLACEBO_PCTL)} placebo: {ctrlB} "
          f"({v['ctrlB_placebo_clocks']}/5)")
    print(f"O-9 VERDICT: {final}{downgraded}")
    print("=" * 78)

    if args.record:
        for _, r in tc.iterrows():
            record("odte_o9_derisk", "O-9 stageC OOS 5% VaR M1 vs M0 (O-8 reproduction)",
                   dict(r), start, end)
        for _, r in td[show].iterrows():
            record("odte_o9_derisk", "O-9 stageD de-risk switch at matched average exposure",
                   dict(r), start, end)
        for _, r in pb.iterrows():
            record("odte_o9_derisk", "O-9 controlB placebo (exposure distribution, no timing)",
                   dict(r), start, end)
        record("odte_o9_derisk", "O-9 decisive bootstrap, q05 (DECLARED headline)",
               dict(bs), start, end)
        record("odte_o9_derisk", "O-9 SECONDARY bootstrap, ES5 (cannot move the verdict)",
               dict(bs_es), start, end)
        record("odte_o9_derisk", f"O-9 VERDICT {final}", dict(v), start, end)
        print("recorded to research/experiments.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
