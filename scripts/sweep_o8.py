"""O-8 - the chain's ASYMMETRY: does the 0DTE put wing forecast the DOWNSIDE TAIL of the day?

WHY THIS ITEM, AND WHY IT IS THE ONE THING THIS STORE HAS NEVER BEEN ASKED.

Seven O-items are closed and the track's own closing sentence (O-7) is that everything this
176 MB store contains lives in ONE number: `rn_half`, half the risk-neutral interquartile span -
a SYMMETRIC scale. O-6 proved it forecasts the magnitude of the remaining session's move with
skill the tape does not contain; O-7 proved that skill is general across volatility states and
economically material to anything sized to |move|; and A-15 then refused the only book in this
repository that could have consumed it, because the intraday sleeve is paid for the volatility
SURPRISE (t +8.41) and not for the PREDICTABLE part (t -0.73).

But the chain also prices ASYMMETRY, and this track has tested that exactly once, for exactly one
thing. O-5 took `rn_skew` (the chain's own dP/dK at 0.5% either side of spot) and `rn_tail` (the
same read at 2.0% - the crash-premium tilt) and asked whether they forecast the DIRECTION of the
remaining move. They do not: best cover 0.963, zero cells above 1, and O-5 closed direction with
the instruction not to re-open it "as a feature, clock, horizon or instrument question".

A conditional MEAN and a conditional QUANTILE are not the same object, and the difference is not
a technicality - it is the entire economics of this item:

  * The conditional mean of a return is a TRADEABLE expectation. If the chain knew it, the chain
    would price it away. O-5's null result is what an efficient market is supposed to look like
    and it is unsurprising in hindsight.
  * The 5th percentile of a return is NOT a tradeable expectation in the same sense. The
    risk-neutral left wing is a physical tail probability MULTIPLIED BY a pricing kernel that is
    largest exactly there. That makes the put wing a BIASED estimator of the physical tail and
    says nothing at all about whether it is an INFORMATIVE one. A de-risking switch does not need
    an unbiased tail, it needs a tail that moves when the real one moves.

And a downside tail has a consumer in this repository that magnitude does not. A-15 refused
`rn_half` as a SIZE scaler because the sleeve's P&L is not paid for predictable magnitude. Nothing
in A-15 is about the LEFT tail: a de-risk/flatten switch is paid for avoiding drawdown, which is a
functional of the lower quantile alone, and the daily track ships one (S-40's crisis switch).

So: one question left, on features that are already in the frozen cache, against a target that has
never been run, with a consumer that has not already refused it.

HYPOTHESIS. The 0DTE chain's risk-neutral ASYMMETRY (`rn_skew` at 0.5% of spot and `rn_tail` at
2.0%) carries information about the LOWER CONDITIONAL QUANTILE of the remaining session's move in
SPY that is contained neither in the realized tape nor in the chain's own symmetric magnitude
measure `rn_half`.

WHAT MAKES THIS A REAL TEST AND NOT A RESTATEMENT OF O-6. The baseline is not the tape. The
baseline is the tape PLUS `rn_half` - the thing this track has already proven is real. If the
asymmetry block only beats the tape, it has found O-6's result again through a wider door and that
is a REFUSAL here, not a pass. The comparison that decides this item is M2 against M1 below.

THE PRE-REGISTERED DESIGN, IN FULL, BEFORE ANY RUN.

  0. NO NEW FEATURE EXTRACTION, NO NEW CLOCK, NO NEW DATA. The chain side is O-5's FROZEN cache
     `results/options/o5_features.parquet`; the tape side, the five clocks, the 250-session
     burn-in, the expanding-window protocol, the regime split and the Diebold-Mariano statistic
     are IMPORTED from `sweep_o6.py` and not re-implemented. Theta is HTTP 403 on `history/quote`
     (FREE subscription) so the store is frozen at 1,891 sessions ending 2026-09-10 regardless.

  1. THE TARGET: `fwd` ITSELF, SIGNED. O-5's own forward return - in at the open of the minute
     bar one full minute after the clock, out at the open of the 15:50 bar, real consolidated SPY
     minute bars. No absolute value and no log: the left tail of a signed return is the object,
     and taking |.| or log destroys exactly the asymmetry being tested.

  2. THE ESTIMATOR: LINEAR QUANTILE REGRESSION (pinball loss), tau = 0.05. Not a binary
     exceedance model, because binarising needs an arbitrary threshold that would have to be
     chosen - and every choice of threshold is a researcher degree of freedom this track does not
     get to spend. The pinball loss at tau = 0.05 IS the loss function of a 5% VaR, so the
     statistical test and the economic object are the same quantity.

  3. THE THREE NESTED MODELS, all in levels (a quantile is proportional to a scale, so scale
     predictors enter linearly and dimensionally correctly):

       M0  TAPE          rv_sofar, rng_sofar, rv20, absret_1      (sweep_o6.TAPE, unchanged)
       M1  TAPE+rn_half  M0 plus the chain's SYMMETRIC magnitude  <- THE BASELINE THAT DECIDES
       M2  M1+ASYM       M1 plus rn_skew AND rn_tail as a BLOCK

     The asymmetry block is fixed at TWO columns, declared here, and is the same two distances
     O-5 declared. `rn_drift` and `d_rn_skew` are in the cache and are NOT in the block; they are
     reported in Stage A descriptively and may not be swapped in afterwards.

     DECLARED SIGNS. `rn_tail` = P_rn(move <= -2%) - P_rn(move >= +2%), so a HIGHER value is a
     relatively FATTER left wing and must push the 5% quantile DOWN: coefficient NEGATIVE. Same
     construction and same declaration for `rn_skew` at 0.5%. A positive fitted coefficient is
     reported as a failure of the declaration and is never re-labelled.

  4. THE SAMPLE. Every model is fitted on exactly the rows where all of TAPE, rn_half, rn_skew,
     rn_tail and fwd are finite, so the three models see an identical panel. `rn_half` carries
     O-3's stricter both-rights mask and is the binding constraint (92.9% coverage); O-5 measured
     that this mask drops calm sessions preferentially and O-7 measured the survival rates, so the
     sample is tilted volatile. Stated as a limit on external validity, identical for all three.

  5. GATES, all before any verdict.
       Gate 0  sweep_o6.gate0 - O-5's pooled control corr(rn_half,|fwd|) reproduces to 0.005.
       Gate 1  the quantile-regression solver reproduces a scipy.optimize.linprog EXACT solution
               of the same program on a 400-row subsample to within 1e-6 of pinball loss. An
               IRLS solver that is quietly wrong would manufacture any result asked of it.
       Gate 2  in-sample calibration: the fitted tau = 0.05 line is breached on 3%-7% of rows.

  6. STAGE C - CAUSAL, OUT OF SAMPLE, DECISIVE. Expanding window, one-step-ahead, refit every
     session after a 250-session burn-in, per clock. Compared on out-of-sample MEAN PINBALL LOSS
     with a Diebold-Mariano t (Newey-West, 5 lags) on the loss difference.

     PASS REQUIRES BOTH LEGS:
       (i)  M2's OOS pinball loss below M1's at >= 4 of 5 clocks, AND a pooled DM t > +2.576,
            where pooling averages the loss difference ACROSS CLOCKS WITHIN A SESSION FIRST so
            that one session is one observation and not five.
       (ii) the two-of-three regimes rule: M2 beats M1 in >= 2 of the 3 a-priori regimes
            2016-2019 / 2020-2023 / 2024-2026, at >= 4 of 5 clocks.
     PARTIAL is defined in advance as (ii) without (i). Anything else is REFUSED.

     REPORTED ALONGSIDE, SECONDARY, AND UNABLE TO CHANGE THE VERDICT: M1 against M0, which asks
     whether O-6's proven magnitude skill translates into VaR at all. That is a different claim
     about a different feature and is carried as context, not as this item's result.

  7. STAGE D - ECONOMIC, pre-registered. The OOS 5% quantile is turned into the de-risk switch
     that would consume it: exposure_t = min(1, budget / |q_hat_t|), each model's exposure series
     then rescaled to the SAME mean exposure so the comparison is at matched average risk, and
     the two books compared on the 5th percentile of exposure * fwd. MATERIAL is declared in
     advance as a >= 5% relative improvement in that quantile at matched mean exposure.
     Calibration (realised breach rate against the nominal 5%) is reported beside it.

  8. STAGE E - THE PLACEBO, which can destroy a PASS and can never create one. The identical
     comparison at tau = 0.95. If the asymmetry block improves the UPPER quantile by as much as
     the lower one at >= 4 of 5 clocks, then what it is carrying is symmetric scale leaking in
     beside `rn_half`, the finding is re-labelled "scale, not asymmetry", and the verdict is
     downgraded to PARTIAL at best.

  9. NO POST-HOC PREDICTOR, NO POST-HOC TAU, NO POST-HOC CLOCK, NO POST-HOC THRESHOLD. Anything
     discovered after the first run is labelled a finding, never a result.

WHAT EACH OUTCOME MEANS, WRITTEN DOWN BEFORE THE RUN SO NEITHER IS A SURPRISE.

  PASS: the store has a SECOND product and it is a downside-risk nowcast rather than a size
  scaler - the one shape A-15's refusal does not reach. It would be handed to whoever owns
  de-risking as a pre-registered item, and this track would still ship nothing.

  REFUSED: the chain's entire content is the one symmetric number O-6 found, the asymmetry
  the put wing is famous for is a pricing kernel and not a forecast, and O-4's advice to stop
  scheduling this scope until Theta VALUE is restored becomes unconditional. That is a clean and
  useful negative and it closes the store on evidence rather than on exhaustion.

Run (default python, NOT py -3.11, which has no pyarrow):

    python scripts/sweep_o8.py --record
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
    TAPE,
    build_panel,
    dm_stat,
    fmt,
    gate0,
    record,
)

HALF = "rn_half"
ASYM = ["rn_skew", "rn_tail"]          # the pre-registered block, fixed at two columns
M0 = list(TAPE)
M1 = list(TAPE) + [HALF]
M2 = list(TAPE) + [HALF] + ASYM
NEED = M2 + ["fwd"]

TAU_LO = 0.05                          # the primary target: a 5% VaR
TAU_HI = 0.95                          # Stage E placebo only
POOLED_T = 2.576                       # Bonferroni bar over 5 clocks, as O-6/O-7 used
CLOCK_MAJORITY = 4                     # ">= 4 of 5 clocks" in both legs
MIN_CELL = 100                         # OOS rows below which a regime is unavailable, not judged
ECON_MATERIAL = 0.05                   # Stage D: >= 5% relative improvement in the book's 5% tail


# ------------------------------------------------------------ the quantile-regression solver
def qreg(X: np.ndarray, y: np.ndarray, tau: float, beta0: np.ndarray | None = None,
         iters: int = 200, tol: float = 1e-10, eps: float = 1e-7) -> np.ndarray:
    """Linear quantile regression by IRLS (the same algorithm statsmodels' QuantReg uses).

    statsmodels is not installed on this machine, so the solver is written out here and Gate 1
    checks it against an EXACT linear-programming solution rather than trusting it. `beta0` is a
    warm start - in the expanding window the previous session's fit is a very good one, which is
    what makes ~46,000 refits affordable.
    """
    if beta0 is not None and len(beta0) == X.shape[1]:
        beta = beta0.astype(float).copy()
    else:
        beta = np.linalg.lstsq(X, y, rcond=None)[0]
    for _ in range(iters):
        r = y - X @ beta
        w = np.where(r >= 0.0, tau, 1.0 - tau) / np.maximum(np.abs(r), eps)
        xw = X * w[:, None]
        A = X.T @ xw
        b = xw.T @ y
        try:
            new = np.linalg.solve(A, b)
        except np.linalg.LinAlgError:
            new = np.linalg.lstsq(A, b, rcond=None)[0]
        step = float(np.max(np.abs(new - beta)))
        beta = new
        if step < tol:
            break
    return beta


def pinball(y: np.ndarray, q: np.ndarray, tau: float) -> np.ndarray:
    """Per-observation pinball (check) loss. This IS the loss function of a tau-VaR."""
    d = y - q
    return np.where(d >= 0.0, tau * d, (tau - 1.0) * d)


def qreg_exact(X: np.ndarray, y: np.ndarray, tau: float) -> np.ndarray:
    """Gate 1 only: the same program solved exactly as an LP. Slow, never used in the study."""
    from scipy.optimize import linprog
    n, k = X.shape
    # variables: [beta+ (k), beta- (k), u (n), v (n)];  y = X(b+ - b-) + u - v,  u,v >= 0
    c = np.concatenate([np.zeros(2 * k), np.full(n, tau), np.full(n, 1.0 - tau)])
    Aeq = np.hstack([X, -X, np.eye(n), -np.eye(n)])
    res = linprog(c, A_eq=Aeq, b_eq=y, bounds=[(0, None)] * (2 * k + 2 * n), method="highs")
    if not res.success:
        return np.full(k, np.nan)
    return res.x[:k] - res.x[k:2 * k]


# ------------------------------------------------------------------ panel
def panel() -> pd.DataFrame:
    df = build_panel()
    df = df.dropna(subset=NEED).copy()
    return df.sort_values(["clock", "date"]).reset_index(drop=True)


def design(d: pd.DataFrame, cols: list[str]) -> np.ndarray:
    """Intercept plus the predictors IN LEVELS. Quantile regression is affine-equivariant, so
    the column scaling applied inside the OOS loop cannot change a fitted value."""
    return np.column_stack([np.ones(len(d))] + [d[c].to_numpy(dtype=float) for c in cols])


# ------------------------------------------------------------------ gates 1 and 2
def gate_solver(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    d = df[df.clock == "12:00"].head(400)
    X, y = design(d, M2), d.fwd.to_numpy()
    sd = X[:, 1:].std(axis=0)
    Xs = np.column_stack([X[:, 0], X[:, 1:] / sd])            # numerics only, not a model change
    for tau in (TAU_LO, TAU_HI):
        b_irls = qreg(Xs, y, tau)
        b_lp = qreg_exact(Xs, y, tau)
        l_irls = float(pinball(y, Xs @ b_irls, tau).mean())
        l_lp = float(pinball(y, Xs @ b_lp, tau).mean())
        rows.append({"check": f"IRLS vs exact LP pinball, tau={tau}", "irls": l_irls,
                     "lp": l_lp, "excess": l_irls - l_lp, "n": len(d),
                     "ok": bool(np.isfinite(l_lp) and (l_irls - l_lp) <= 1e-6)})
    for tau in (TAU_LO, TAU_HI):
        for clock in CLOCKS:
            g = df[df.clock == clock]
            Xg, yg = design(g, M2), g.fwd.to_numpy()
            s = Xg[:, 1:].std(axis=0)
            Xg = np.column_stack([Xg[:, 0], Xg[:, 1:] / s])
            br = float((yg < Xg @ qreg(Xg, yg, tau)).mean())
            rows.append({"check": f"in-sample breach rate {clock}, tau={tau}", "irls": br,
                         "lp": tau, "excess": br - tau, "n": len(g),
                         "ok": bool(abs(br - tau) <= 0.02)})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ stage A (descriptive)
def stage_a(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for clock in CLOCKS:
        d = df[df.clock == clock]
        y = d.fwd.to_numpy()
        lo = y < np.quantile(y, 0.05)
        for col in [HALF] + ASYM + ["rn_drift", "d_rn_skew"]:
            x = d[col].to_numpy(dtype=float)
            rows.append({"clock": clock, "predictor": col, "n": len(d),
                         "spearman(x, fwd)": float(pd.Series(x).corr(pd.Series(y), "spearman"),),
                         "spearman(x, |fwd|)": float(
                             pd.Series(x).corr(pd.Series(np.abs(y)), "spearman")),
                         "mean(x | worst 5%)": float(x[lo].mean()),
                         "mean(x | rest)": float(x[~lo].mean())})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ stage C (decisive)
def oos_quantiles(d: pd.DataFrame, cols: list[str], tau: float) -> np.ndarray:
    """Expanding-window one-step-ahead tau-quantile forecasts. NaN over the burn-in."""
    X = design(d, cols)
    y = d.fwd.to_numpy()
    out = np.full(len(d), np.nan)
    beta = None
    for i in range(BURN_IN, len(d)):
        Xi, yi = X[:i], y[:i]
        sd = Xi[:, 1:].std(axis=0)
        sd = np.where(sd > 0, sd, 1.0)
        Xs = np.column_stack([Xi[:, 0], Xi[:, 1:] / sd])
        beta = qreg(Xs, yi, tau, beta0=beta)
        xr = np.concatenate([[1.0], X[i, 1:] / sd])
        out[i] = float(xr @ beta)
    return out


def stage_c(df: pd.DataFrame, tau: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, keep = [], []
    for clock in CLOCKS:
        d = df[df.clock == clock].reset_index(drop=True)
        q0 = oos_quantiles(d, M0, tau)
        q1 = oos_quantiles(d, M1, tau)
        q2 = oos_quantiles(d, M2, tau)
        m = np.isfinite(q0) & np.isfinite(q1) & np.isfinite(q2)
        d = d.loc[m].copy()
        d["q0"], d["q1"], d["q2"] = q0[m], q1[m], q2[m]
        y = d.fwd.to_numpy()
        d["l0"] = pinball(y, d.q0.to_numpy(), tau)
        d["l1"] = pinball(y, d.q1.to_numpy(), tau)
        d["l2"] = pinball(y, d.q2.to_numpy(), tau)
        d["tau"] = tau
        keep.append(d)
        row = {"clock": clock, "tau": tau, "n_oos": len(d),
               "pin_M0_tape": float(d.l0.mean()),
               "pin_M1_+half": float(d.l1.mean()),
               "pin_M2_+asym": float(d.l2.mean()),
               "d_pin_M2vM1_%": 100.0 * (d.l2.mean() / d.l1.mean() - 1.0),
               "DM_t_M2vM1": dm_stat(d.l1.to_numpy() - d.l2.to_numpy()),
               "d_pin_M1vM0_%": 100.0 * (d.l1.mean() / d.l0.mean() - 1.0),
               "DM_t_M1vM0": dm_stat(d.l0.to_numpy() - d.l1.to_numpy())}
        wins = 0
        for name in REGIMES:
            g = d[d.regime == name]
            row[f"{name}_n"] = len(g)
            if len(g) < MIN_CELL:
                row[f"{name}_d_pin_%"] = np.nan
                continue
            row[f"{name}_d_pin_%"] = 100.0 * (g.l2.mean() / g.l1.mean() - 1.0)
            wins += int(g.l2.mean() < g.l1.mean())
        row["regimes_won"] = wins
        row["clock_won"] = bool(d.l2.mean() < d.l1.mean())
        rows.append(row)
    return pd.DataFrame(rows), pd.concat(keep, ignore_index=True)


def pooled_dm(oos: pd.DataFrame) -> tuple[float, int]:
    """DM t on the M2-vs-M1 loss difference, averaged ACROSS CLOCKS WITHIN A SESSION first."""
    g = oos.assign(d=oos.l1 - oos.l2).groupby("date", sort=True)["d"].mean()
    return float(dm_stat(g.to_numpy())), int(len(g))


def verdict(tab: pd.DataFrame, pooled_t: float) -> dict:
    clocks_won = int(tab.clock_won.sum())
    leg_i = bool(clocks_won >= CLOCK_MAJORITY and pooled_t > POOLED_T)
    leg_ii = int((tab.regimes_won >= 2).sum()) >= CLOCK_MAJORITY
    v = "PASS" if (leg_i and leg_ii) else ("PARTIAL" if leg_ii else "REFUSED")
    return {"clocks_won": clocks_won, "pooled_DM_t": pooled_t, "leg_i_statistical": leg_i,
            "clocks_2of3_regimes": int((tab.regimes_won >= 2).sum()), "leg_ii_regimes": leg_ii,
            "verdict": v}


# ------------------------------------------------------------------ stage D (economic)
def stage_d(oos: pd.DataFrame) -> pd.DataFrame:
    """The de-risk switch the 5% quantile would feed, at MATCHED mean exposure."""
    rows = []
    for clock in CLOCKS:
        d = oos[oos.clock == clock]
        y = d.fwd.to_numpy()
        out = {"clock": clock, "n": len(d)}
        books = {}
        for label, col in (("M1", "q1"), ("M2", "q2")):
            q = d[col].to_numpy()
            out[f"breach_{label}_%"] = 100.0 * float((y < q).mean())
            budget = float(np.median(np.abs(q)))          # the switch sits at its own median risk
            e = np.minimum(1.0, budget / np.maximum(np.abs(q), 1e-9))
            e = e / e.mean()                              # matched mean exposure, by construction
            books[label] = e * y
            out[f"tail5_{label}_bps"] = 1e4 * float(np.quantile(books[label], 0.05))
            out[f"es5_{label}_bps"] = 1e4 * float(
                books[label][books[label] <= np.quantile(books[label], 0.05)].mean())
        out["d_tail5_%"] = 100.0 * (out["tail5_M2_bps"] / out["tail5_M1_bps"] - 1.0)
        out["d_es5_%"] = 100.0 * (out["es5_M2_bps"] / out["es5_M1_bps"] - 1.0)
        # both tail numbers are negative, so a SMALLER magnitude is the improvement
        out["MATERIAL"] = bool(out["d_tail5_%"] <= -100.0 * ECON_MATERIAL)
        rows.append(out)
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ stage F (signs)
def stage_f(df: pd.DataFrame, tau: float) -> pd.DataFrame:
    """Full-sample fitted coefficients on the asymmetry block, against the declared signs."""
    rows = []
    for clock in CLOCKS:
        d = df[df.clock == clock]
        X, y = design(d, M2), d.fwd.to_numpy()
        sd = X[:, 1:].std(axis=0)
        b = qreg(np.column_stack([X[:, 0], X[:, 1:] / sd]), y, tau)
        # back out per-1-sd effects, which is what the declaration is about
        rows.append({"clock": clock, "tau": tau, "n": len(d),
                     "b_rn_half_per_sd_bps": 1e4 * float(b[1 + M2.index(HALF)]),
                     "b_rn_skew_per_sd_bps": 1e4 * float(b[1 + M2.index("rn_skew")]),
                     "b_rn_tail_per_sd_bps": 1e4 * float(b[1 + M2.index("rn_tail")]),
                     "skew_sign_ok": bool(b[1 + M2.index("rn_skew")] < 0),
                     "tail_sign_ok": bool(b[1 + M2.index("rn_tail")] < 0)})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--record", action="store_true", help="append DIAGNOSTIC rows to the ledger")
    args = ap.parse_args()

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
          f"{start}..{end}   (all of {', '.join(NEED)} finite)")
    print(f"rn_tail == 0 exactly on {100.0 * float((df.rn_tail == 0).mean()):.1f}% of rows "
          f"(O-5's mass point: on calm days both 2% wings are worthless)")

    print("\n=== GATE 1 + GATE 2 (the solver, and its calibration) ===")
    gs = gate_solver(df)
    print(fmt(gs))
    if not bool(gs.ok.all()):
        print("SOLVER GATE FAILED - stopping.")
        return 1

    print("\n=== STAGE A (descriptive, no verdict turns on it) ===")
    ta = stage_a(df)
    print(fmt(ta))

    print(f"\n=== STAGE C (DECISIVE): OOS pinball loss at tau={TAU_LO}, "
          f"expanding window, {BURN_IN}-session burn-in ===")
    print("    M2 (tape + rn_half + asymmetry) against M1 (tape + rn_half) is the test;")
    print("    M1 against M0 is SECONDARY context and cannot change the verdict.")
    tc, oos = stage_c(df, TAU_LO)
    print(fmt(tc))
    pt, npool = pooled_dm(oos)
    v = verdict(tc, pt)
    print(f"\n  pooled DM t (session-pooled across clocks, n={npool:,}): {pt:+.3f} "
          f"against a bar of +{POOLED_T}")
    print(f"  leg (i) statistical: {v['leg_i_statistical']}  "
          f"(clocks won {v['clocks_won']}/5)")
    print(f"  leg (ii) two-of-three regimes at >= 4 of 5 clocks: {v['leg_ii_regimes']}  "
          f"(clocks with >= 2 regimes won: {v['clocks_2of3_regimes']}/5)")

    print("\n=== STAGE F: fitted asymmetry coefficients against the DECLARED signs ===")
    tf = stage_f(df, TAU_LO)
    print(fmt(tf))

    print("\n=== STAGE D (economic): the de-risk switch at matched mean exposure ===")
    td = stage_d(oos)
    print(fmt(td))

    print(f"\n=== STAGE E (PLACEBO, can destroy a PASS, can never create one): tau={TAU_HI} ===")
    te, oos_hi = stage_c(df, TAU_HI)
    print(fmt(te))
    pt_hi, _ = pooled_dm(oos_hi)
    # the placebo bites if the upper tail improves at least as much as the lower one
    lo_imp = tc.set_index("clock")["d_pin_M2vM1_%"]
    hi_imp = te.set_index("clock")["d_pin_M2vM1_%"]
    placebo_hits = int((hi_imp <= lo_imp).sum())
    print(f"\n  pooled DM t at tau={TAU_HI}: {pt_hi:+.3f}")
    print(f"  clocks where the UPPER tail improves at least as much as the lower: "
          f"{placebo_hits}/5  (>= {CLOCK_MAJORITY} means 'scale, not asymmetry')")
    placebo_bites = placebo_hits >= CLOCK_MAJORITY
    final = v["verdict"]
    if placebo_bites and final == "PASS":
        final = "PARTIAL"
    v["placebo_hits"] = placebo_hits
    v["placebo_bites"] = bool(placebo_bites)
    v["final"] = final

    print("\n" + "=" * 78)
    print(f"O-8 VERDICT: {final}"
          + ("" if final == v["verdict"] else f"  (downgraded from {v['verdict']} by the placebo)"))
    print("=" * 78)

    if args.record:
        for _, r in tc.iterrows():
            record("odte_o8_tail", f"O-8 stageC OOS pinball tau={TAU_LO} M2 vs M1 vs M0",
                   dict(r), start, end)
        for _, r in te.iterrows():
            record("odte_o8_tail", f"O-8 stageE PLACEBO OOS pinball tau={TAU_HI}",
                   dict(r), start, end)
        for _, r in td.iterrows():
            record("odte_o8_tail", "O-8 stageD de-risk switch at matched mean exposure",
                   dict(r), start, end)
        for _, r in tf.iterrows():
            record("odte_o8_tail", "O-8 stageF asymmetry coefficients vs declared signs",
                   dict(r), start, end)
        record("odte_o8_tail", f"O-8 VERDICT {final}", dict(v), start, end)
        print("recorded to research/experiments.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
