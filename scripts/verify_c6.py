"""C-6: does O-7's PASS survive its own pre-registered disqualifier?

TARGET. O-7 (`research/journal_options.md`, 2026-09-13) is the only PASS produced in the last
24 hours, and it is being used to add a second justification to the Theta VALUE subscription ask
in `research/BLOCKERS.md` - i.e. it is a claim that asks the owner to spend money. Its verdict
rests on a two-legged pre-registered rule. Leg (ii) (the two-of-three rule over volatility states,
>= 4 of 5 clocks) passes 5 of 5 and is not in dispute here. Leg (i) is carried by a single number:

    pooled calm Diebold-Mariano t = +2.613   against a bar of +2.576

O-7 is candid that this is marginal: it prints the Newey-West lag sensitivity (Stage 5) showing the
statistic FAILS at lags 0 and 2, and it prints the mask attack (Stage 4a) and says it lands. Those
are disclosed and are not the attack. The attack is on a choice the pre-registration made and
justified, where the justification does not hold.

THE ATTACK, stated before any number was read.

O-7 clause 1 fixes `rv20` as the primary state variable and rejects `rv_sofar` IN ADVANCE, in
these words:

    "REJECTED IN ADVANCE, and why, so it cannot be swapped in afterwards: splitting on `rv_sofar`
     at the clock is also causal, but it is one of the baseline's own fitted inputs, so the split
     would condition on the thing being tested. It is carried as Stage 4, an explicitly SECONDARY
     robustness read, and the verdict does not turn on it."

The disqualifying property is membership of the fitted baseline. But `sweep_o6.TAPE` is

    TAPE = ["rv_sofar", "rng_sofar", "rv20", "absret_1"]

and `sweep_o7.py` imports that very constant. `rv20` is a fitted input of BOTH the tape baseline
and the tape+chain model, exactly as `rv_sofar` is. The stated reason for demoting the secondary
variable applies verbatim to the primary one. The two variables are not distinguished by the
criterion the pre-registration used to rank them - and they disagree on the verdict: `rv20` gives
leg (i) = True (PASS), `rv_sofar` gives pooled calm t +2.033 (PARTIAL).

So the question this file answers is the one O-7's own design says it wanted to answer and did not:
WHAT IS THE VERDICT UNDER A CAUSAL VOLATILITY-STATE LABEL THAT IS NOT A FITTED INPUT? If leg (i)
holds under state labels outside TAPE, O-7's PASS survives its own rule and the ranking was
harmless. If it does not, the PASS is carried by the choice of a fitted splitter and the honest
verdict is PARTIAL - which is the outcome O-7 itself defined as "re-label A-15 before any track
spends a slot on it", and which changes what the BLOCKERS.md ask is allowed to claim.

STAGES (all fixed before the first run).

  A. IDENTITY. Rebuild O-7's inputs through its own imports - `build_panel`, `gate0`, `stage_c`,
     `label_states`, `stage_1` - and reproduce Stage 1 on `rv20` to the printed digit. If the
     pooled calm t is not +2.6131 the target has moved and nothing below is interpretable.

  B. MEMBERSHIP, and whether it is load-bearing. Assert `rv20 in TAPE`. Membership alone is the
     logical point, but a token regressor would make it a technicality, so measure how much the
     baseline actually leans on `rv20`: its Newey-West t in the full-sample tape fit, and the OOS
     R-squared the tape model loses when `rv20` is dropped, per clock.

  C. THE REPLACEMENT SPLITTERS - the decisive stage. Three causal volatility-state labels, none
     of them in TAPE, none of them read by either model, all computed from the same SPY minute
     store with the same `.shift(1)` discipline as `rv20`:
       rv60      prior 60 sessions' close-to-close log-return sd   (longer memory, same channel)
       gapvol20  prior 20 sessions' sd of the overnight log gap    (a different channel entirely:
                 the tape models see no overnight information at all)
       rng20     prior 20 sessions' mean (high-low)/open           (range rather than returns)
     Each is pushed through O-7's OWN `label_states` and `stage_1`, unmodified, so the tercile
     construction, the 100-session minimum history, the MIN_CELL floor, the pooling rule and the
     bar are all O-7's. Only the splitter changes.

     THE RULE, fixed here: leg (i) is robust if it holds (pooled calm t > 2.576) under a MAJORITY
     of the three non-fitted splitters. If it holds under none, the PASS is an artifact of the
     splitter choice. Reported either way, with leg (ii) beside it, because leg (ii) is what O-7
     calls "not marginal" and it deserves to be checked under the same labels.

  D. DISTRIBUTION-FREE. The DM t is a normal-theory statistic on a per-session mean of squared-
     error differences of a log-magnitude, which is heavy-tailed. O-7 checked the Newey-West lag
     but not the distributional assumption. Stationary (Politis-Romano) block bootstrap, mean
     block length 5, 20,000 resamples of the centred per-session series, one-sided p against
     H0: mean(d) <= 0. The pre-registered bar +2.576 is a one-sided p of 0.00494; the question is
     whether the bootstrap p clears it.

  E. THE DIRECTION OF THE CORRECTION. Stage 5 shows the t RISING with the Newey-West lag
     (2.487 -> 2.790). That means the Bartlett correction is SHRINKING the standard error below
     its iid value, i.e. the series is negatively autocorrelated at these lags. `sweep_o6`'s own
     docstring justifies Newey-West as protection against overstatement ("realized vol is
     persistent and OLS t's would be overstated"). Report se_nw / se_iid for the pooled calm
     series, so it is on the record whether the correction that produces the PASS is operating in
     the direction its justification claims.

This file ships nothing, promotes nothing and touches no runner-loaded, scheduled or live file.
It writes no ledger row: the critic track records evidence in its journal.

Run (default python, NOT py -3.11, which has no pyarrow):

    python scripts/verify_c6.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from sweep_o6 import (  # noqa: E402
    CLOCKS,
    CHAIN,
    NW_LAGS,
    SESSION_OPEN,
    TAPE,
    build_panel,
    design,
    fmt,
    gate0,
    nw_se,
    stage_c,
)
from sweep_o7 import (  # noqa: E402
    MIN_HIST,
    POOLED_T,
    label_states,
    stage_1,
    _errs,
)

ROOT = REPO
O7_POOLED_T_RV20 = 2.6131      # the number this file must reproduce before it may argue
O7_TOL = 5e-4
BOOT_B = 20_000
BOOT_BLOCK = 5.0
SEED = 20260913


# --------------------------------------------------------------- stage C inputs
def extra_state_vars() -> pd.DataFrame:
    """Causal per-session volatility labels that are NOT in TAPE.

    Same store and the same `.shift(1)` discipline `sweep_o6.tape_panel` uses for `rv20`: every
    value attached to day D is computed from sessions STRICTLY BEFORE D.
    """
    df = pd.read_parquet(ROOT / "data" / "minute_alpaca" / "SPY.parquet")
    df = df.tz_convert("America/New_York")
    df["day"] = df.index.strftime("%Y-%m-%d")
    df["hhmm"] = df.index.strftime("%H:%M")
    df = df[df["hhmm"] >= SESSION_OPEN]

    g = df.groupby("day", sort=True)
    closes = g["c"].last()
    opens = g["o"].first()
    highs = g["h"].max()
    lows = g["l"].min()

    ret = np.log(closes / closes.shift(1))
    gap = np.log(opens / closes.shift(1))          # overnight, unseen by either model
    rng = (highs - lows) / opens

    out = pd.DataFrame({
        "date": closes.index,
        "rv60": ret.rolling(60).std().shift(1).to_numpy(),
        "gapvol20": gap.rolling(20).std().shift(1).to_numpy(),
        "rng20": rng.rolling(20).mean().shift(1).to_numpy(),
    })
    return out.reset_index(drop=True)


# --------------------------------------------------------------- stage B
def stage_b(panel: pd.DataFrame) -> pd.DataFrame:
    """Is `rv20` a load-bearing regressor in the baseline, or a token one?"""
    rows = []
    reduced = [c for c in TAPE if c != "rv20"]
    for clock in CLOCKS:
        d = panel[panel.clock == clock].dropna(subset=TAPE + [CHAIN, "y"]).reset_index(drop=True)
        X = design(d, TAPE)
        y = d.y.to_numpy()
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        resid = y - X @ beta
        se = nw_se(X, resid, np.linalg.inv(X.T @ X), NW_LAGS)
        j = 1 + TAPE.index("rv20")               # +1 for the intercept column
        # in-sample R2 of the full tape fit vs the same fit without rv20
        Xr = design(d, reduced)
        br, *_ = np.linalg.lstsq(Xr, y, rcond=None)
        rr = y - Xr @ br
        ss = float(((y - y.mean()) ** 2).sum())
        rows.append({"clock": clock, "n": len(d),
                     "rv20_beta": float(beta[j]), "rv20_NW_t": float(beta[j] / se[j]),
                     "R2_tape": 1.0 - float(resid @ resid) / ss,
                     "R2_tape_no_rv20": 1.0 - float(rr @ rr) / ss,
                     "dR2_from_rv20": (float(rr @ rr) - float(resid @ resid)) / ss})
    return pd.DataFrame(rows)


# --------------------------------------------------------------- stage D
def pooled_calm_series(lab: pd.DataFrame) -> np.ndarray:
    """O-7's pooled calm loss-difference series, built with O-7's own rule."""
    calm = lab[lab.state == "calm"].copy()
    _, e_t, e_c = _errs(calm)
    calm["d"] = e_t - e_c
    return calm.groupby("date", sort=True)["d"].mean().to_numpy()


def nw_var(d: np.ndarray, lags: int) -> float:
    n = len(d)
    e = d - d.mean()
    S = float(e @ e)
    for L in range(1, min(lags, n - 1) + 1):
        w = 1.0 - L / (lags + 1.0)
        S += 2.0 * w * float(e[L:] @ e[:-L])
    return S / (n ** 2)


def stationary_bootstrap_p(s: np.ndarray, b: int, block: float, seed: int) -> tuple[float, float]:
    """One-sided p for H0: mean(s) <= 0, and the bootstrap's own 0.5% critical t.

    Politis-Romano stationary bootstrap: geometric block lengths with mean `block`, wrapped
    indices, so the serial dependence O-7 corrects for with Newey-West is preserved by
    resampling rather than modelled. The series is centred so the resamples are draws under H0.
    """
    rng = np.random.default_rng(seed)
    n = len(s)
    obs_mean = float(s.mean())
    obs_t = obs_mean / np.sqrt(nw_var(s, NW_LAGS))
    centred = s - obs_mean
    p_geom = 1.0 / block

    ts = np.empty(b)
    for k in range(b):
        idx = np.empty(n, dtype=np.int64)
        i = 0
        while i < n:
            start = rng.integers(0, n)
            L = min(int(rng.geometric(p_geom)), n - i)
            idx[i:i + L] = (start + np.arange(L)) % n
            i += L
        r = centred[idx]
        v = nw_var(r, NW_LAGS)
        ts[k] = r.mean() / np.sqrt(v) if v > 0 else 0.0

    return float((ts >= obs_t).mean()), float(np.quantile(ts, 1.0 - 0.00494))


# --------------------------------------------------------------- main
def main() -> int:
    print("=" * 78)
    print("C-6: O-7's leg (i) under state labels that are not fitted inputs")
    print("=" * 78)

    panel = build_panel()
    print(f"\npanel: {len(panel):,} rows  {panel.date.nunique():,} sessions  "
          f"{panel.date.min()}..{panel.date.max()}")

    g, ok = gate0(panel)
    print("\n=== GATE 0 (O-6's own) ===")
    print(fmt(g))
    if not ok:
        print("GATE 0 FAILED - stop.")
        return 1

    c_tab, oos = stage_c(panel)
    if not bool(c_tab["PASS"].all()):
        print("GATE 1 FAILED - O-6 no longer reproduces; nothing to condition.")
        return 1
    print(f"GATE 1 ok: O-6 Stage C reproduces, 5 of 5 clocks, {len(oos):,} OOS rows.")

    # ---------------------------------------------------------- A. identity
    print("\n=== STAGE A: reproduce O-7 Stage 1 on rv20 ===")
    lab20 = label_states(oos, "rv20")
    t1, s1 = stage_1(lab20, "rv20")
    print(f"  pooled calm DM t = {s1['pooled_calm_DM_t']:+.4f} on "
          f"{s1['pooled_calm_sessions']:,} sessions   verdict {s1['verdict']}")
    delta = abs(s1["pooled_calm_DM_t"] - O7_POOLED_T_RV20)
    print(f"  O-7 journal says +{O7_POOLED_T_RV20}  |delta| = {delta:.2e}  "
          f"{'IDENTITY OK' if delta <= O7_TOL else 'IDENTITY FAILED'}")
    if delta > O7_TOL:
        print("  the target has moved; the argument below would not be about O-7.")
        return 1

    # ---------------------------------------------------------- B. membership
    print("\n=== STAGE B: is the primary splitter a fitted input, and is it load-bearing? ===")
    print(f"  sweep_o6.TAPE = {TAPE}")
    print(f"  'rv20'     in TAPE : {'rv20' in TAPE}        <- O-7's PRIMARY splitter")
    print(f"  'rv_sofar' in TAPE : {'rv_sofar' in TAPE}        <- rejected in advance FOR THIS")
    print(fmt(stage_b(panel)))

    # ---------------------------------------------------------- C. replacements
    print("\n=== STAGE C (DECISIVE): leg (i) under causal splitters that are NOT in TAPE ===")
    extra = extra_state_vars()
    oos2 = oos.merge(extra, on="date", how="left")
    assert len(oos2) == len(oos), "the state-variable merge changed the row count"

    rows = []
    for col in ("rv20", "rv_sofar", "rv60", "gapvol20", "rng20"):
        in_tape = col in TAPE
        lab = label_states(oos2, col)
        tab, s = stage_1(lab, col)
        rows.append({"splitter": col, "in_TAPE": in_tape,
                     "labelled_rows": len(lab),
                     "calm_wins": s["calm_clock_wins"],
                     "pooled_calm_t": s["pooled_calm_DM_t"],
                     "sessions": s["pooled_calm_sessions"],
                     "leg_i": s["leg_i_calm"],
                     "clocks_2of3": s["clocks_winning_2of3_states"],
                     "leg_ii": s["leg_ii_two_of_three"],
                     "verdict": s["verdict"]})
    tabC = pd.DataFrame(rows)
    print(fmt(tabC))

    nonfitted = tabC[~tabC.in_TAPE]
    hold = int(nonfitted.leg_i.sum())
    print(f"\n  leg (i) holds under {hold} of {len(nonfitted)} non-fitted splitters "
          f"(bar: a majority, i.e. >= {len(nonfitted) // 2 + 1})")
    print(f"  leg (ii) holds under {int(nonfitted.leg_ii.sum())} of {len(nonfitted)}")
    robust = hold >= len(nonfitted) // 2 + 1
    print(f"  >>> leg (i) ROBUST TO THE SPLITTER: {robust}")

    # ---------------------------------------------------------- D. bootstrap
    print("\n=== STAGE D: distribution-free check on the pooled calm statistic ===")
    for col in ("rv20", "rv60", "gapvol20", "rng20"):
        lab = label_states(oos2, col)
        s = pooled_calm_series(lab)
        t_obs = s.mean() / np.sqrt(nw_var(s, NW_LAGS))
        p, crit = stationary_bootstrap_p(s, BOOT_B, BOOT_BLOCK, SEED)
        print(f"  {col:<9} n={len(s):>4}  t={t_obs:+.4f}  "
              f"bootstrap one-sided p={p:.4f}  (bar 0.00494)  "
              f"boot 0.5% crit t={crit:+.3f}   {'CLEARS' if p <= 0.00494 else 'FAILS'}")

    # ---------------------------------------------------------- E. NW direction
    print("\n=== STAGE E: which way is the Newey-West correction pointing? ===")
    for col in ("rv20", "rv60", "gapvol20", "rng20"):
        lab = label_states(oos2, col)
        s = pooled_calm_series(lab)
        se_iid = np.sqrt(nw_var(s, 0))
        se_nw = np.sqrt(nw_var(s, NW_LAGS))
        print(f"  {col:<9} se_iid={se_iid:.6e}  se_NW5={se_nw:.6e}  "
              f"ratio={se_nw / se_iid:.4f}  "
              f"{'NW SHRINKS the SE (inflates t)' if se_nw < se_iid else 'NW widens the SE'}")

    print("\n" + "=" * 78)
    print(f"C-6 RESULT: O-7 leg (i) robust to a non-fitted splitter = {robust}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
