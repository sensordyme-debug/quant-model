"""O-7 - is O-6's PASS a SIZING input, or a volatility-regime detector wearing one's clothes?

WHY THIS ITEM, AND WHY IT IS THE HIGHEST-VALUE ONE LEFT ON THIS TRACK.

O-6 is the only PASS this track has produced. It showed that the 0DTE chain's risk-neutral
half-span `rn_half` forecasts the magnitude of the remaining session's move in SPY with skill the
realized tape does not already contain: out-of-sample R-squared on log|move| rises +0.027 to
+0.044 at all five clocks, Diebold-Mariano t +3.5 to +4.2, and it survives both a one-hour buffer
and a strengthened tape baseline. On the back of that it opened **A-15** and handed `iterate`/`ml`
an instruction to test an `rn_half`-based size scaler against the sleeve's realized-vol sizing.

O-6 also wrote down, in its own caveats, the single thing that would make that handoff overstated
and never tested it:

    "measured on SPY only, on a sample tilted volatile by O-3's mask (it drops calm sessions
     preferentially - O-5 measured mean |move| 13.3 bps where it drops out against 38.7 bps
     where it survives)"

That caveat is only dangerous in one specific way, and it is the way that matters economically. A
sizing rule does not need help on days when the tape is already screaming. `rv_sofar` at 12:00 on
a 3% day tells the sizer everything it needs. **The expensive error is the quiet morning that ends
in a move** - the state where a realized-vol sizer is structurally blind and a forward-looking
risk-neutral measure is the only thing that could see. If O-6's increment lives entirely in the
volatile state, then what it found is a **volatility-regime detector**, largely redundant with the
tape's own regime read, and A-15 should be re-labelled before another track spends a slot on it.
If the increment survives in the **calm** state, the finding is stronger than O-6 claimed and the
handoff is safe.

The external-validity caveat (SPY only) cannot be closed from disk - the store has exactly one
underlying and Theta is still HTTP 403 on `history/quote` (re-checked live at the top of this run,
`listening True serving True`). The volatility-conditioning caveat CAN be, from the same frozen
inputs, with no new feature, no new clock and no new target. That is this item.

HYPOTHESIS. The chain's incremental magnitude skill over the tape is a GENERAL input to position
size, not a volatility-state detector: it survives out of sample in the CALM volatility state,
where a realized-vol sizer is weakest.

WHAT IS AND IS NOT NEW HERE. Nothing on the measurement side is new. The panel, the frozen O-5
chain cache, the four-predictor tape baseline, the target, the five clocks, the 250-session
burn-in and the expanding-window OOS protocol are IMPORTED from `sweep_o6.py` and re-run
unmodified, so Stage C reproduces to the digit before anything is conditioned. The only new object
in this file is the STATE VARIABLE the out-of-sample errors are partitioned by.

THE PRE-REGISTERED DESIGN, IN FULL, BEFORE ANY RUN.

  0. GATE 0 / GATE 1. O-6's own Gate 0 (its reproduction of O-5's pooled control to within 0.005)
     must pass, and O-6's Stage C table must reproduce with all five clocks at PASS. If either
     fails, the study stops - there is no point conditioning a result that no longer exists.

  1. THE STATE VARIABLE: `rv20`, the standard deviation of the previous 20 sessions' close-to-close
     log returns, STRICTLY prior sessions. It is known BEFORE the session being forecast opens, so
     the partition cannot be contaminated by the outcome, and a real sizer would know it at the
     same moment. It is deliberately NOT the strongest tape predictor: the point is a clean state
     label, not a competitive split.

     REJECTED IN ADVANCE, and why, so it cannot be swapped in afterwards: splitting on `rv_sofar`
     at the clock is also causal, but it is one of the baseline's own fitted inputs, so the split
     would condition on the thing being tested. It is carried as Stage 4, an explicitly SECONDARY
     robustness read, and the verdict does not turn on it.

  2. THE PARTITION IS CAUSAL. Session i is labelled calm / mid / volatile by where its `rv20` sits
     against the 33.3rd and 66.7th percentiles of `rv20` over sessions STRICTLY BEFORE i within
     the same clock's feature-complete subset, with a 100-session minimum history. No full-sample
     quantile is used anywhere. Rows without enough history to label are dropped from the stage,
     not assigned to a bucket.

  3. STAGE 1 - DECISIVE. Per clock, per state: out-of-sample RMSE of the tape model and of the
     tape+chain model on exactly O-6's OOS forecasts, the relative difference, the change in OOS
     R-squared, and a Diebold-Mariano t on the squared-error difference (Newey-West, 5 lags). A
     state with fewer than 100 OOS rows at a clock is reported as unavailable, never judged.

     POOLED CALM STATISTIC. Pooling five clocks by stacking rows would treat the same session
     five times as five independent observations. Instead the loss difference is averaged ACROSS
     CLOCKS WITHIN A SESSION first, giving one number per session, and the DM t is computed on
     that date-ordered series. Declared here so the pooling rule is not chosen after seeing it.

     PASS REQUIRES BOTH:
       (i)  the chain model has lower OOS RMSE in the CALM state at >= 4 of 5 clocks, AND the
            pooled calm DM t exceeds +2.576 - the same Bonferroni bar O-6 used; AND
       (ii) the two-of-three rule, applied to volatility states instead of calendar regimes: the
            chain wins >= 2 of the 3 states at >= 4 of 5 clocks.
     PARTIAL: (ii) holds and (i) fails. The increment is real but VOLATILITY-CONDITIONAL, and
            A-15 must be re-labelled from "size scaler" to "volatility-state input" before any
            track spends a slot on it.
     FAIL:  neither holds. O-6's pooled result is then carried by a subset of sessions and the
            handoff should be withdrawn.

  4. STAGE 2 - WHERE THE SKILL LIVES. Descriptive, no verdict: delta OOS R-squared per state per
     clock, beside the mean |fwd| of each state, so the profile of the increment across the
     volatility axis is on the record whatever the verdict is.

  5. STAGE 3 - THE ECONOMIC LEG, per state. The OOS forecast is turned into a size exactly as in
     O-6: sigma_hat = exp(y_hat), normalized move z = |fwd| / sigma_hat. Reported per state: the
     standard deviation of z and the 3-sigma breach count.

     ONE DELIBERATE CHANGE FROM O-6, DECLARED IN ADVANCE WITH ITS REASON. O-6 found that a raw
     3.0 cut charges the two models' different mean(z) levels as a tail difference, and had to
     rescale post hoc. Here the LEVEL-SCALED breach count (each model rescaled to mean(z) = 1
     within the state) is PRE-REGISTERED as primary and the raw count is printed beside it. This
     is a correction O-6 already justified, adopted before this run rather than after it.

     MATERIAL in the calm state uses O-6's own bar: >= 5% relative reduction in sd(z), or >= 10%
     relative reduction in the scaled breach count.

  6. STAGE 4 - TWO ATTACKS, both committed here before the first run.
     (a) THE MASK. The feature-complete mask drops calm sessions preferentially, so the "calm"
         bucket might be calm-by-`rv20` while being volatile in fact. Per state, the mask's
         survival rate and the mean |fwd| of dropped vs kept cells are printed. If the calm
         bucket's survivors are themselves a volatile-selected subsample, the calm verdict is
         about those survivors and says so.
     (b) THE OTHER STATE VARIABLE. The whole of Stage 1 re-run on `rv_sofar` terciles (causal, same
         construction). SECONDARY: it can corroborate or qualify, it cannot overturn, because it
         conditions on a fitted input.

  7. NO POST-HOC STATE, NO POST-HOC BAR, NO POST-HOC CLOCK. Anything found after the first run is
     labelled a finding, never a result.

WHAT EACH OUTCOME MEANS, WRITTEN DOWN BEFORE THE RUN.

  PASS    -> the chain is a general risk input. A-15 stands as written and gains the one piece of
             evidence it was missing: the increment is there in the state where realized-vol
             sizing is blind.
  PARTIAL -> the chain is a regime detector. A-15 is re-labelled and its expected value drops,
             because the tape has its own regime read and the overlap is the whole question.
  FAIL    -> O-6's pooled number is carried by a subsample; the handoff is withdrawn and this
             store has nothing left to give at any cost level.

This track ships nothing either way: no shipped file, no runner-loaded file, no config, no
champion. Evidence only.

Run (default python, NOT py -3.11, which has no pyarrow):

    python scripts/sweep_o7.py --record
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sweep_o6 import (  # noqa: E402  - the measurement side is imported, never re-implemented
    CHAIN,
    CLOCKS,
    TAPE,
    build_panel,
    dm_stat,
    fmt,
    gate0,
    record,
    stage_c,
)

STATES = ["calm", "mid", "volatile"]
MIN_HIST = 100          # sessions of history before a row can be labelled
MIN_CELL = 100          # OOS rows below which a (clock, state) cell is unavailable, not judged
POOLED_T = 2.576        # the Bonferroni bar O-6 used, re-used for the pooled calm DM t
CLOCK_MAJORITY = 4      # ">= 4 of 5 clocks" in both legs of the PASS rule
SD_MATERIAL = 0.05
BREACH_MATERIAL = 0.10


# ------------------------------------------------------------- the causal partition
def causal_terciles(vals: np.ndarray) -> np.ndarray:
    """Label each row calm/mid/volatile against the terciles of STRICTLY PRIOR rows.

    No full-sample quantile is used. Rows with fewer than MIN_HIST prior finite values are left
    unlabelled ("") and are dropped by the caller rather than pushed into a bucket.
    """
    out = np.array([""] * len(vals), dtype=object)
    for i in range(len(vals)):
        v = vals[i]
        if not np.isfinite(v):
            continue
        hist = vals[:i]
        hist = hist[np.isfinite(hist)]
        if len(hist) < MIN_HIST:
            continue
        lo, hi = np.percentile(hist, [100.0 / 3.0, 200.0 / 3.0])
        out[i] = "calm" if v <= lo else ("mid" if v <= hi else "volatile")
    return out


def label_states(oos: pd.DataFrame, col: str) -> pd.DataFrame:
    """Attach a causal state label per clock, on the clock's own date-ordered OOS rows."""
    parts = []
    for clock in CLOCKS:
        d = oos[oos.clock == clock].sort_values("date").reset_index(drop=True).copy()
        d["state"] = causal_terciles(d[col].to_numpy(dtype=float))
        parts.append(d)
    out = pd.concat(parts, ignore_index=True)
    return out[out.state != ""].reset_index(drop=True)


# ------------------------------------------------------------- stage 1
def _errs(d: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    y = d.y.to_numpy()
    return y, (y - d.f_tape.to_numpy()) ** 2, (y - d.f_chain.to_numpy()) ** 2


def stage_1(lab: pd.DataFrame, state_name: str) -> tuple[pd.DataFrame, dict]:
    rows = []
    for clock in CLOCKS:
        c = lab[lab.clock == clock]
        row: dict = {"clock": clock, "n": len(c)}
        wins = 0
        for st in STATES:
            g = c[c.state == st]
            if len(g) < MIN_CELL:
                row[f"{st}_n"] = len(g)
                row[f"{st}_dRMSE_%"] = np.nan
                row[f"{st}_DM_t"] = np.nan
                continue
            y, e_t, e_c = _errs(g)
            a, b = float(np.sqrt(e_t.mean())), float(np.sqrt(e_c.mean()))
            ss = float(((y - y.mean()) ** 2).sum())
            row[f"{st}_n"] = len(g)
            row[f"{st}_dRMSE_%"] = 100.0 * (b / a - 1.0)
            row[f"{st}_DM_t"] = dm_stat(e_t - e_c)
            row[f"{st}_dOOSR2"] = (e_t.sum() - e_c.sum()) / ss if ss > 0 else np.nan
            wins += int(b < a)
        row["states_won"] = wins
        rows.append(row)
    tab = pd.DataFrame(rows)

    # pooled CALM statistic: average the loss difference across clocks WITHIN a session first,
    # so the same session is one observation and not five correlated ones.
    calm = lab[lab.state == "calm"].copy()
    _, e_t, e_c = _errs(calm)
    calm["d"] = e_t - e_c
    per_session = calm.groupby("date", sort=True)["d"].mean().to_numpy()
    pooled_t = dm_stat(per_session)

    calm_clock_wins = int((tab["calm_dRMSE_%"] < 0).sum())
    two_of_three_clocks = int((tab["states_won"] >= 2).sum())
    leg_i = bool(calm_clock_wins >= CLOCK_MAJORITY and np.isfinite(pooled_t)
                 and pooled_t > POOLED_T)
    leg_ii = bool(two_of_three_clocks >= CLOCK_MAJORITY)
    verdict = "PASS" if (leg_i and leg_ii) else ("PARTIAL" if leg_ii else "FAIL")
    summary = {"state_var": state_name, "calm_clock_wins": calm_clock_wins,
               "pooled_calm_DM_t": pooled_t, "pooled_calm_sessions": len(per_session),
               "clocks_winning_2of3_states": two_of_three_clocks,
               "leg_i_calm": leg_i, "leg_ii_two_of_three": leg_ii, "verdict": verdict}
    return tab, summary


# ------------------------------------------------------------- stage 2
def stage_2(lab: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for clock in CLOCKS:
        c = lab[lab.clock == clock]
        row: dict = {"clock": clock}
        for st in STATES:
            g = c[c.state == st]
            if len(g) < MIN_CELL:
                row[f"{st}_dOOSR2"] = np.nan
                row[f"{st}_mean|fwd|bps"] = np.nan
                continue
            y, e_t, e_c = _errs(g)
            ss = float(((y - y.mean()) ** 2).sum())
            row[f"{st}_dOOSR2"] = (e_t.sum() - e_c.sum()) / ss if ss > 0 else np.nan
            row[f"{st}_mean|fwd|bps"] = 1e4 * float(g.fwd.abs().mean())
        rows.append(row)
    return pd.DataFrame(rows)


# ------------------------------------------------------------- stage 3
def stage_3(lab: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for clock in CLOCKS:
        for st in STATES:
            g = lab[(lab.clock == clock) & (lab.state == st)]
            if len(g) < MIN_CELL:
                continue
            mv = g.fwd.abs().to_numpy()
            out: dict = {"clock": clock, "state": st, "n": len(g)}
            for label, col in (("tape", "f_tape"), ("chain", "f_chain")):
                z = mv / np.exp(g[col].to_numpy())
                out[f"sd_{label}"] = float(z.std())
                out[f"br3s_{label}"] = int((z / z.mean() > 3.0).sum())   # primary, pre-registered
                out[f"br3raw_{label}"] = int((z > 3.0).sum())            # printed beside it
            out["d_sd_%"] = 100.0 * (out["sd_chain"] / out["sd_tape"] - 1.0)
            out["d_br3s_%"] = (100.0 * (out["br3s_chain"] / out["br3s_tape"] - 1.0)
                               if out["br3s_tape"] else np.nan)
            out["MATERIAL"] = bool(out["d_sd_%"] <= -100 * SD_MATERIAL
                                   or (np.isfinite(out["d_br3s_%"])
                                       and out["d_br3s_%"] <= -100 * BREACH_MATERIAL))
            rows.append(out)
    return pd.DataFrame(rows)


# ------------------------------------------------------------- stage 4a
def stage_4a(panel: pd.DataFrame) -> pd.DataFrame:
    """The mask attack: is the 'calm' bucket calm-by-rv20 but volatile in fact?

    Runs on the FULL panel (before the feature-complete dropna), so the dropped cells are still
    present and their |fwd| can be compared with the survivors' inside the same state.
    """
    rows = []
    for clock in CLOCKS:
        d = panel[panel.clock == clock].sort_values("date").reset_index(drop=True).copy()
        d["state"] = causal_terciles(d["rv20"].to_numpy(dtype=float))
        d = d[d.state != ""]
        keep = np.isfinite(d[CHAIN].to_numpy()) & np.isfinite(d["fwd"].to_numpy())
        for st in STATES:
            m = (d.state == st).to_numpy()
            k = m & keep
            dr = m & ~keep
            if m.sum() == 0:
                continue
            rows.append({"clock": clock, "state": st, "n_cells": int(m.sum()),
                         "survival_%": 100.0 * k.sum() / m.sum(),
                         "kept_mean|fwd|bps": 1e4 * float(d.loc[k, "fwd"].abs().mean())
                         if k.sum() else np.nan,
                         "dropped_mean|fwd|bps": 1e4 * float(d.loc[dr, "fwd"].abs().mean())
                         if dr.sum() else np.nan})
    return pd.DataFrame(rows)


# ------------------------------------------------------------- stage 5
def dm_stat_lags(d: np.ndarray, lags: int) -> float:
    """DM t on a loss-difference series at an arbitrary Newey-West lag. Stage 5 only."""
    n = len(d)
    if n < 30:
        return float("nan")
    e = d - d.mean()
    S = float(e @ e)
    for L in range(1, min(lags, n - 1) + 1):
        w = 1.0 - L / (lags + 1.0)
        S += 2.0 * w * float(e[L:] @ e[:-L])
    var = S / (n ** 2)
    return d.mean() / np.sqrt(var) if var > 0 else float("nan")


def stage_5(lab: pd.DataFrame) -> pd.DataFrame:
    """POST-HOC, ADDED AFTER THE FIRST RUN AND LABELLED AS SUCH. It cannot change the verdict.

    Leg (i) of the pre-registered rule is carried by a pooled calm DM t that clears its bar by a
    hair. A statistic that marginal has to be shown to be marginal rather than described as
    'passing', so its sensitivity to the one free choice in it - the Newey-West lag, fixed at 5
    by O-6 and inherited here - is printed. The pre-registered verdict stands on lag 5.
    """
    calm = lab[lab.state == "calm"].copy()
    _, e_t, e_c = _errs(calm)
    calm["d"] = e_t - e_c
    s = calm.groupby("date", sort=True)["d"].mean().to_numpy()
    return pd.DataFrame([{"NW_lags": L, "pooled_calm_DM_t": dm_stat_lags(s, L),
                          "clears_bar": bool(dm_stat_lags(s, L) > POOLED_T)}
                         for L in (0, 2, 5, 10, 20)])


# ------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--record", action="store_true", help="append DIAGNOSTIC rows to the ledger")
    args = ap.parse_args()

    panel = build_panel()
    start, end = panel.date.min(), panel.date.max()
    print(f"panel: {len(panel):,} rows  {panel.date.nunique():,} sessions  {start}..{end}")

    print("\n=== GATE 0: O-6's own gate, unmodified ===")
    g, ok = gate0(panel)
    print(fmt(g))
    if not ok:
        print("GATE 0 FAILED - the frozen cache no longer reproduces O-5's control. Stop.")
        return 1

    print("\n=== GATE 1: does O-6's Stage C reproduce? (5 of 5 clocks must PASS) ===")
    c_tab, oos = stage_c(panel)
    print(fmt(c_tab[["clock", "n_oos", "oosR2_tape", "oosR2_chain", "d_rmse_%", "DM_t",
                     "regimes_won", "PASS"]]))
    if not bool(c_tab["PASS"].all()):
        print("GATE 1 FAILED - O-6's result does not reproduce; there is nothing to condition.")
        return 1
    print("GATE 1 ok: O-6 reproduces, 5 of 5 clocks.")

    # --------------------------------------------------------- primary state variable
    lab = label_states(oos, "rv20")
    print(f"\nlabelled OOS rows (causal rv20 terciles): {len(lab):,} of {len(oos):,}")
    print(lab.groupby(["state"]).size().to_string())

    print("\n=== STAGE 1 (DECISIVE): the increment, split by EX-ANTE volatility state (rv20) ===")
    t1, s1 = stage_1(lab, "rv20")
    print(fmt(t1[["clock", "calm_n", "calm_dRMSE_%", "calm_DM_t",
                  "mid_n", "mid_dRMSE_%", "mid_DM_t",
                  "volatile_n", "volatile_dRMSE_%", "volatile_DM_t", "states_won"]]))
    print(f"\n  calm-state clock wins        : {s1['calm_clock_wins']} of 5   "
          f"(pre-registered bar: >= {CLOCK_MAJORITY})")
    print(f"  pooled calm DM t (by session): {s1['pooled_calm_DM_t']:+.3f}  on "
          f"{s1['pooled_calm_sessions']:,} sessions   (bar: > +{POOLED_T})")
    print(f"  clocks winning 2 of 3 states : {s1['clocks_winning_2of3_states']} of 5   "
          f"(bar: >= {CLOCK_MAJORITY})")
    print(f"  leg (i) calm = {s1['leg_i_calm']}   leg (ii) two-of-three = "
          f"{s1['leg_ii_two_of_three']}")
    print(f"  >>> STAGE 1 VERDICT: {s1['verdict']}")

    print("\n=== STAGE 2 (descriptive): where the skill lives ===")
    t2 = stage_2(lab)
    print(fmt(t2))

    print("\n=== STAGE 3 (economic): what a book sized off the forecast experiences, per state ===")
    t3 = stage_3(lab)
    print(fmt(t3[["clock", "state", "n", "sd_tape", "sd_chain", "d_sd_%",
                  "br3s_tape", "br3s_chain", "d_br3s_%", "br3raw_tape", "br3raw_chain",
                  "MATERIAL"]]))
    calm3 = t3[t3.state == "calm"]
    print(f"\n  calm state: MATERIAL at {int(calm3.MATERIAL.sum())} of {len(calm3)} clocks; "
          f"mean d_sd_% = {calm3['d_sd_%'].mean():+.2f}")

    print("\n=== STAGE 4a (attack): the feature-complete mask, per state ===")
    t4a = stage_4a(panel)
    print(fmt(t4a))

    print("\n=== STAGE 4b (SECONDARY attack): the same split on rv_sofar at the clock ===")
    lab2 = label_states(oos, "rv_sofar")
    t4b, s4b = stage_1(lab2, "rv_sofar")
    print(fmt(t4b[["clock", "calm_n", "calm_dRMSE_%", "calm_DM_t",
                   "mid_dRMSE_%", "volatile_dRMSE_%", "states_won"]]))
    print(f"  calm-state clock wins {s4b['calm_clock_wins']} of 5, pooled calm DM t "
          f"{s4b['pooled_calm_DM_t']:+.3f}, verdict (secondary, cannot overturn): "
          f"{s4b['verdict']}")

    print("\n=== STAGE 5 (POST-HOC, cannot change the verdict): how marginal is leg (i)? ===")
    t5 = stage_5(lab)
    print(fmt(t5))

    print("\n" + "=" * 78)
    print(f"O-7 VERDICT (primary, rv20): {s1['verdict']}")
    print("=" * 78)

    if args.record:
        for _, r in t1.iterrows():
            record("odte_o7_volstate", "O-7 stage1 increment by ex-ante rv20 state",
                   {k: v for k, v in r.items()}, start, end)
        for _, r in t3.iterrows():
            record("odte_o7_volstate", "O-7 stage3 sized-book dispersion by state",
                   {k: v for k, v in r.items()}, start, end)
        for _, r in t4a.iterrows():
            record("odte_o7_volstate", "O-7 stage4a mask survival by state",
                   {k: v for k, v in r.items()}, start, end)
        for _, r in t4b.iterrows():
            record("odte_o7_volstate", "O-7 stage4b SECONDARY split on rv_sofar",
                   {k: v for k, v in r.items()}, start, end)
        for _, r in t5.iterrows():
            record("odte_o7_volstate", "O-7 stage5 POST-HOC NW-lag sensitivity of leg (i)",
                   {k: v for k, v in r.items()}, start, end)
        record("odte_o7_volstate", f"O-7 VERDICT {s1['verdict']}", dict(s1), start, end)
        print("recorded to research/experiments.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
