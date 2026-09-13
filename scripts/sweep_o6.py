"""O-6 - the chain's ONE strong skill: is it incremental over the tape, or a restatement of it?

WHY THIS ITEM, AND WHY IT IS THE LAST ONE THIS STORE CAN ANSWER.

Five O-items have been measured and five have been refused, and all five refusals are about the
same thing: what it costs to COLLECT an edge. O-2 refused the SPY 0DTE credit spread on the
options round trip (~230 bps of risked capital against a gross of +0.783%), O-3 closed selection
(cover tops out at 1.043 with full hindsight), O-4 disqualified free trade-print feeds (an
estimator blind to the spread cannot refuse a bad trade), and O-5 moved the same chain signal into
SPY itself - cutting the round trip 68x to 3.41 bps - and found the DIRECTIONAL edge shrank to
match, best cover 0.963, zero cells above 1.

But O-5 printed one number it never examined. Its Gate-0 control was

    corr(rn_half, |forward move|) = +0.540 at t = +60.0   (8,777 cells)

and it was reported only as evidence that the feature extraction was not broken. That is the
single largest statistic this track has ever produced, it is about MAGNITUDE rather than
direction, and O-5's own closing sentence conceded the chain "forecasts magnitude superbly". A
magnitude forecast is not a return signal, so the cost wall that killed O-2/O-3/O-5 does not
apply to it at all: a better |move| nowcast changes POSITION SIZE, and sizing is free. It is also
the exact quantity the ML track's F-12 found to be the only thing in this repository that can be
forecast well ("the risk model is 32x better than the return model").

So the last open question on this store is not whether the chain knows something. It is whether
what the chain knows is ALREADY ON THE TAPE.

HYPOTHESIS. At a fixed intraday clock, the 0DTE chain's risk-neutral half-interquartile span
(rn_half) carries information about the magnitude of the REMAINING session's move in SPY that is
not contained in the realized tape observable at the same instant.

WHY THIS IS NOT O-1 RE-OPENED. O-1 tested prior-day / end-of-day / 1-week SPY implied vol as a
GATE on the intraday sleeve and found the payoff regressor is the volatility SURPRISE. Three
things differ. (a) The observation is same-session and intraday - the chain at 12:00 prices the
move that has not happened yet, conditional on everything that has. (b) The target here is
|move| itself, not sleeve P&L, so nothing about a particular strategy's payoff shape enters.
(c) The question is INCREMENTAL, not absolute: O-1 never regressed an implied measure against the
realized tape available at the same moment, so it could not have separated "the chain knows" from
"the chain re-reads what the tape already said".

WHY THIS IS NOT O-5 RE-OPENED. O-5's closing instruction was "do not re-open as a feature, clock,
horizon or instrument question" - and that instruction is about DIRECTION, which is what O-5
measured and what all 20 of its cells traded. Magnitude was its control and was never tested for
incrementality, never taken out of sample, and never given an economic threshold. This item
changes the target, not the feature set: it adds NO new chain feature and NO new clock.

THE PRE-REGISTERED DESIGN, IN FULL, BEFORE ANY RUN.

  0. NO NEW FEATURE EXTRACTION. The chain side is read from O-5's FROZEN cache
     `results/options/o5_features.parquet` (9,445 cells, 1,890 sessions, 2016-01-08..2026-09-10).
     Not rebuilt, not re-masked, not extended. Gate 0 re-derives O-5's pooled control from it and
     stops the study unless it reproduces +0.540 to within 0.005.

  1. THE TARGET. y = log(max(|fwd|, 1e-5)), where `fwd` is O-5's own forward return - entered at
     the open of the minute bar one full minute after the clock, exited at the open of the 15:50
     bar, on real consolidated SPY minute bars. Logs because every quantity here is a scale and
     the raw target has a heavy right tail; the same transform is applied to every predictor, so
     no predictor is advantaged by it. Spearman on the RAW target is reported beside it.

  2. THE TAPE BASELINE - four predictors, all computable strictly at or before the clock, all
     from `data/minute_alpaca/SPY.parquet`, which is the same file O-5 priced its trades on:

       rv_sofar    sqrt(sum of squared 1-minute log returns), 09:30 -> the clock. The realized
                   vol of the session so far. This is the obvious competitor and the one that
                   makes the test meaningful, because the chain sees it too.
       rng_sofar   (max high - min low) / open over the same window. Range carries information
                   about a session's character that a sum of squares does not.
       rv20        standard deviation of the previous 20 sessions' close-to-close log returns,
                   STRICTLY prior sessions. The slow-moving level.
       absret_1    |previous session's close-to-close log return|. The fast one-day carry-over.

     The chain predictor is log(rn_half). DECLARED SIGN: POSITIVE (a wider risk-neutral
     distribution means a larger residual move). A negative coefficient is reported as a failure
     of the declaration, never re-labelled.

  3. THE SAMPLE. rn_half uses O-3's stricter both-rights mask and is therefore missing on 7%
     (10:00) to 13% (14:00) of cells. BOTH models are fitted on exactly the feature-complete
     subset so the comparison is like-for-like. O-5 established that this mask drops the CALM
     sessions preferentially (mean |move| 13.3 bps where it drops out against 38.7 bps where it
     survives); the surviving sample is therefore tilted volatile, which is stated here as a
     limit on external validity and is identical for both models.

  4. STAGE A - univariate. Pearson corr with y and Spearman with |fwd|, per predictor per clock.
     Descriptive: it establishes which single series is the better forecaster, and no verdict
     turns on it.

  5. STAGE B - INCREMENTAL, in sample. OLS of y on [const + the four tape predictors], then the
     same with log(rn_half) added. The statistic is the t of the rn_half coefficient, computed
     with Newey-West standard errors at 5 lags because realized vol is persistent and OLS t's
     would be overstated. With 5 clocks the Bonferroni two-sided threshold is |t| > 2.576 and it
     is printed next to every row. Delta-R-squared is reported beside it, because a t can be
     large on an increment too small to matter.

  6. STAGE C - CAUSAL, OUT OF SAMPLE, and this is the decisive stage. Expanding window: for each
     session i after a 250-session burn-in, both models are re-fitted on sessions strictly before
     i and asked to predict session i. Compared on out-of-sample RMSE of y and on out-of-sample
     R-squared, with a Diebold-Mariano test (Newey-West, 5 lags) on the squared-error difference.
     PASS REQUIRES BOTH: the chain model's OOS RMSE is lower overall, AND it is lower in at least
     two of the three a-priori regimes 2016-2019 / 2020-2023 / 2024-2026. That is this
     repository's standing two-of-three rule applied to a forecast instead of a P&L.

  7. STAGE D - ECONOMIC, pre-registered so it cannot be chosen afterwards. The OOS forecasts of
     Stage C are turned into a size: sigma_hat = exp(y_hat), and the normalized move is
     |fwd| / sigma_hat - what a book sized off the forecast actually experiences. A better
     forecast gives a tighter normalized move and fewer tail breaches. MATERIAL is declared in
     advance as a >= 5% relative reduction in the standard deviation of the normalized move, or
     a >= 10% relative reduction in the count of 3-sigma breaches. Anything smaller is a
     statistical result without an economic one and is reported as such.

  8. NO POST-HOC PREDICTOR, NO POST-HOC CLOCK, NO POST-HOC THRESHOLD, NO POST-HOC TARGET.
     Anything discovered after the first run is labelled a finding, never a result.

WHAT EACH OUTCOME MEANS, WRITTEN DOWN BEFORE THE RUN SO NEITHER IS A SURPRISE.

  If the increment is real and material, then the only surviving product of this 176 MB store is
  a RISK input, not a return signal, and it should be handed to the tracks that size positions -
  and the Theta VALUE ask in BLOCKERS.md gains a second, cheaper justification than SPXW.

  If the increment is not material, then the chain's one strong skill is a restatement of the
  tape, the store has nothing left to give at any cost level, and O-4's advice to stop scheduling
  this scope until VALUE is restored becomes unconditional rather than a judgement call.

Run (default python, NOT py -3.11, which has no pyarrow):

    python scripts/sweep_o6.py --record
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "results" / "options" / "o5_features.parquet"

CLOCKS = ["10:00", "11:00", "12:00", "13:00", "14:00"]
SESSION_OPEN = "09:30"
EPS = 1e-5             # floor under |fwd| before the log; 1e-5 = 0.1 bp
TAPE = ["rv_sofar", "rng_sofar", "rv20", "absret_1"]
# post-hoc robustness only (Stage F): a deliberately harder tape baseline. A weak baseline is the
# most likely way an "incremental" finding is wrong, so the chain is also run against a tape model
# that carries the RECENT 30 minutes and a fast 5-session level in addition to the four above.
TAPE_STRONG = TAPE + ["rv_30m", "rv5"]
CHAIN = "rn_half"
NW_LAGS = 5
BONFERRONI_T = 2.576   # two-sided alpha 0.05 over 5 clocks
BURN_IN = 250          # sessions before the first out-of-sample prediction
REGIMES = {"2016-2019": ("2016-01-01", "2019-12-31"),
           "2020-2023": ("2020-01-01", "2023-12-31"),
           "2024-2026": ("2024-01-01", "2026-12-31")}
SD_MATERIAL = 0.05     # Stage D: >= 5% relative reduction in sd of the normalized move
BREACH_MATERIAL = 0.10  # Stage D: >= 10% relative reduction in 3-sigma breaches
CONTROL_TARGET = 0.540  # O-5's pooled control, to be reproduced within 0.005
CONTROL_TOL = 0.005


# ------------------------------------------------------------------ the tape
def tape_panel() -> pd.DataFrame:
    """Realized predictors per (day, clock), all strictly causal at the clock.

    One pass over the SPY minute store. `rv20` and `absret_1` use only sessions strictly before
    the day they are attached to; `rv_sofar` and `rng_sofar` use only bars at or before the clock.
    """
    df = pd.read_parquet(ROOT / "data" / "minute_alpaca" / "SPY.parquet")
    df = df.tz_convert("America/New_York")
    df["day"] = df.index.strftime("%Y-%m-%d")
    df["hhmm"] = df.index.strftime("%H:%M")
    df = df[df["hhmm"] >= SESSION_OPEN]

    # prior-session series first: close-to-close, one value per day, then shifted.
    closes = df.groupby("day", sort=True)["c"].last()
    ret = np.log(closes / closes.shift(1))
    rv20 = ret.rolling(20).std().shift(1)          # strictly prior 20 sessions
    rv5 = ret.rolling(5).std().shift(1)            # strictly prior 5 sessions (Stage F only)
    absret_1 = ret.abs().shift(1)                  # strictly prior session

    rows: list[dict] = []
    for day, g in df.groupby("day", sort=False):
        hhmm = g["hhmm"].to_numpy()
        o = g["o"].to_numpy()
        h = g["h"].to_numpy()
        lo = g["l"].to_numpy()
        c = g["c"].to_numpy()
        if len(g) < 2:
            continue
        lr = np.diff(np.log(c), prepend=np.log(c[0]))
        for clock in CLOCKS:
            k = int(np.searchsorted(hhmm, clock, side="right"))   # bars strictly at/before clock
            if k < 5:
                continue
            j = max(0, k - 30)                      # the last 30 minutes before the clock
            rows.append({"date": day, "clock": clock,
                         "rv_sofar": float(np.sqrt(np.sum(lr[:k] ** 2))),
                         "rng_sofar": float((h[:k].max() - lo[:k].min()) / o[0]),
                         "rv20": float(rv20.get(day, np.nan)),
                         "absret_1": float(absret_1.get(day, np.nan)),
                         "rv_30m": float(np.sqrt(np.sum(lr[j:k] ** 2))),
                         "rv5": float(rv5.get(day, np.nan)),
                         "px_open": float(o[0])})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ statistics
def nw_se(X: np.ndarray, resid: np.ndarray, xtx_inv: np.ndarray, lags: int) -> np.ndarray:
    """Newey-West standard errors for an OLS fit. Bartlett kernel."""
    n = len(resid)
    u = X * resid[:, None]
    S = u.T @ u
    for L in range(1, min(lags, n - 1) + 1):
        w = 1.0 - L / (lags + 1.0)
        G = u[L:].T @ u[:-L]
        S += w * (G + G.T)
    V = xtx_inv @ S @ xtx_inv
    return np.sqrt(np.maximum(np.diag(V), 0.0))


def ols(y: np.ndarray, X: np.ndarray) -> dict:
    """OLS with Newey-West t's. X must already carry its own intercept column."""
    xtx_inv = np.linalg.pinv(X.T @ X)
    beta = xtx_inv @ (X.T @ y)
    resid = y - X @ beta
    se = nw_se(X, resid, xtx_inv, NW_LAGS)
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - float((resid ** 2).sum()) / ss_tot if ss_tot > 0 else np.nan
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(se > 0, beta / se, np.nan)
    return {"beta": beta, "t": t, "r2": r2, "resid": resid}


def dm_stat(d: np.ndarray) -> float:
    """Diebold-Mariano t on a loss-difference series, Newey-West at NW_LAGS."""
    n = len(d)
    if n < 30:
        return float("nan")
    dm = d.mean()
    e = d - dm
    S = float(e @ e)
    for L in range(1, min(NW_LAGS, n - 1) + 1):
        w = 1.0 - L / (NW_LAGS + 1.0)
        S += 2.0 * w * float(e[L:] @ e[:-L])
    var = S / (n ** 2)
    return dm / np.sqrt(var) if var > 0 else float("nan")


def logs(v: np.ndarray) -> np.ndarray:
    return np.log(np.maximum(v, EPS))


def design(d: pd.DataFrame, cols: list[str]) -> np.ndarray:
    return np.column_stack([np.ones(len(d))] + [logs(d[c].to_numpy()) for c in cols])


def regime_of(dates: np.ndarray) -> np.ndarray:
    out = np.array(["other"] * len(dates), dtype=object)
    for name, (a, b) in REGIMES.items():
        out[(dates >= a) & (dates <= b)] = name
    return out


# ------------------------------------------------------------------ the panel
def build_panel() -> pd.DataFrame:
    chain = pd.read_parquet(CACHE)
    tape = tape_panel()
    df = chain.merge(tape, on=["date", "clock"], how="inner", suffixes=("", "_tape"))
    df["y"] = logs(df.fwd.abs().to_numpy())
    df["regime"] = regime_of(df.date.to_numpy())
    return df.sort_values(["clock", "date"]).reset_index(drop=True)


def fmt(df: pd.DataFrame) -> str:
    if df.empty:
        return "  (empty)"
    return df.to_string(index=False, float_format=lambda v: f"{v:,.4f}")


# ------------------------------------------------------------------ gate 0
def gate0(df: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    m = np.isfinite(df.rn_half) & np.isfinite(df.fwd)
    ctrl = float(np.corrcoef(df.loc[m, "rn_half"], df.loc[m, "fwd"].abs())[0, 1])
    n = int(m.sum())
    t_ctrl = ctrl * np.sqrt((n - 2) / max(1e-12, 1 - ctrl ** 2))
    # the join is checked on the price the two sides agree on: O-5's px_ref (the bar at the
    # clock) against this module's own independently computed session open, via their ratio.
    gap = (df.px_ref / df.px_open - 1.0).abs()
    rows = [{"check": "O-5 control corr(rn_half,|fwd|)", "value": ctrl, "n": n,
             "target": CONTROL_TARGET, "ok": abs(ctrl - CONTROL_TARGET) <= CONTROL_TOL},
            {"check": "control t", "value": t_ctrl, "n": n, "target": 5.0, "ok": t_ctrl > 5.0},
            {"check": "chain/tape join rows kept", "value": float(len(df)), "n": len(df),
             "target": 9000.0, "ok": len(df) > 9000},
            {"check": "median |px_ref/px_open - 1| (sanity, not a tolerance)",
             "value": float(gap.median()), "n": len(df), "target": np.nan, "ok": True}]
    out = pd.DataFrame(rows)
    return out, bool(out.ok.all())


# ------------------------------------------------------------------ stage A
def stage_a(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for clock in CLOCKS:
        d = df[df.clock == clock].dropna(subset=TAPE + [CHAIN, "y"])
        for col in TAPE + [CHAIN]:
            x = logs(d[col].to_numpy())
            r = float(np.corrcoef(x, d.y.to_numpy())[0, 1])
            sp = float(pd.Series(d[col].to_numpy()).corr(
                pd.Series(d.fwd.abs().to_numpy()), method="spearman"))
            rows.append({"clock": clock, "predictor": col, "n": len(d),
                         "corr(log x, y)": r, "spearman(x, |fwd|)": sp})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ stage B
def stage_b(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for clock in CLOCKS:
        d = df[df.clock == clock].dropna(subset=TAPE + [CHAIN, "y"])
        y = d.y.to_numpy()
        fit_t = ols(y, design(d, TAPE))
        fit_tc = ols(y, design(d, TAPE + [CHAIN]))
        fit_c = ols(y, design(d, [CHAIN]))
        rows.append({"clock": clock, "n": len(d),
                     "R2_tape": fit_t["r2"], "R2_chain_only": fit_c["r2"],
                     "R2_tape+chain": fit_tc["r2"],
                     "dR2": fit_tc["r2"] - fit_t["r2"],
                     "beta_rn_half": float(fit_tc["beta"][-1]),
                     "t_rn_half(NW)": float(fit_tc["t"][-1]),
                     "sign_ok": bool(fit_tc["beta"][-1] > 0),
                     "|t|>2.576": bool(abs(fit_tc["t"][-1]) > BONFERRONI_T)})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ stage C
def oos_forecasts(d: pd.DataFrame, cols: list[str]) -> np.ndarray:
    """Expanding-window one-step-ahead predictions. NaN over the burn-in."""
    X = design(d, cols)
    y = d.y.to_numpy()
    out = np.full(len(d), np.nan)
    for i in range(BURN_IN, len(d)):
        Xi, yi = X[:i], y[:i]
        beta, *_ = np.linalg.lstsq(Xi, yi, rcond=None)
        out[i] = float(X[i] @ beta)
    return out


def stage_c(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, keep = [], []
    for clock in CLOCKS:
        d = df[df.clock == clock].dropna(subset=TAPE + [CHAIN, "y"]).reset_index(drop=True)
        f_t = oos_forecasts(d, TAPE)
        f_tc = oos_forecasts(d, TAPE + [CHAIN])
        m = np.isfinite(f_t) & np.isfinite(f_tc)
        d = d.loc[m].copy()
        d["f_tape"], d["f_chain"] = f_t[m], f_tc[m]
        keep.append(d)
        y = d.y.to_numpy()
        e_t, e_c = (y - d.f_tape.to_numpy()) ** 2, (y - d.f_chain.to_numpy()) ** 2
        ss = float(((y - y.mean()) ** 2).sum())
        row = {"clock": clock, "n_oos": len(d),
               "rmse_tape": float(np.sqrt(e_t.mean())),
               "rmse_chain": float(np.sqrt(e_c.mean())),
               "d_rmse_%": 100.0 * (np.sqrt(e_c.mean()) / np.sqrt(e_t.mean()) - 1.0),
               "oosR2_tape": 1.0 - e_t.sum() / ss, "oosR2_chain": 1.0 - e_c.sum() / ss,
               "DM_t": dm_stat(e_t - e_c)}      # positive DM = chain loses less
        wins = 0
        for name in REGIMES:
            g = d[d.regime == name]
            row[f"{name}_n"] = len(g)
            if len(g) < 100:
                # the 250-session burn-in eats into the first regime, and the feature-complete
                # subset shrinks with the clock; a regime with too few OOS rows is reported as
                # unavailable rather than judged, so "2 of 3" can mean "2 of 2 available".
                row[f"{name}_d_rmse_%"] = np.nan
                continue
            yy = g.y.to_numpy()
            a = float(np.sqrt((((yy - g.f_tape.to_numpy()) ** 2)).mean()))
            b = float(np.sqrt((((yy - g.f_chain.to_numpy()) ** 2)).mean()))
            row[f"{name}_d_rmse_%"] = 100.0 * (b / a - 1.0)
            wins += int(b < a)
        row["regimes_won"] = wins
        row["PASS"] = bool(row["rmse_chain"] < row["rmse_tape"] and wins >= 2)
        rows.append(row)
    return pd.DataFrame(rows), pd.concat(keep, ignore_index=True)


# ------------------------------------------------------------------ stage D
def stage_d(oos: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for clock in CLOCKS:
        d = oos[oos.clock == clock]
        mv = d.fwd.abs().to_numpy()
        out = {"clock": clock, "n": len(d)}
        for label, col in (("tape", "f_tape"), ("chain", "f_chain")):
            z = mv / np.exp(d[col].to_numpy())
            out[f"sd_{label}"] = float(z.std())
            out[f"mean_{label}"] = float(z.mean())
            out[f"breach3_{label}"] = int((z > 3.0).sum())
            # POST-HOC, labelled: exp(y_hat) is a conditional geometric mean, not a sigma, and the
            # two models sit at different levels, so a raw 3.0 cut counts the level difference as
            # a risk difference. Rescaling each model to mean(z) = 1 removes that and leaves only
            # the shape of the tail. Reported beside the raw count, never instead of it.
            out[f"breach3s_{label}"] = int((z / z.mean() > 3.0).sum())
        out["d_sd_%"] = 100.0 * (out["sd_chain"] / out["sd_tape"] - 1.0)
        out["d_breach_%"] = (100.0 * (out["breach3_chain"] / out["breach3_tape"] - 1.0)
                             if out["breach3_tape"] else np.nan)
        out["d_breach_scaled_%"] = (100.0 * (out["breach3s_chain"] / out["breach3s_tape"] - 1.0)
                                    if out["breach3s_tape"] else np.nan)
        out["MATERIAL"] = bool(out["d_sd_%"] <= -100 * SD_MATERIAL
                               or (np.isfinite(out["d_breach_%"])
                                   and out["d_breach_%"] <= -100 * BREACH_MATERIAL))
        rows.append(out)
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ post-hoc attacks
def stage_e(df: pd.DataFrame) -> pd.DataFrame:
    """POST-HOC. The stale-chain test: can any sub-hour timing artifact explain the increment?

    The store is 5-minute bid/ask SNAPSHOTS stamped at the interval tick, and O-5 enters one full
    minute after the clock, so a leak would need the stamp to mean something other than it says.
    Rather than argue from a column name, this widens the gap to a full hour: every predictor -
    chain AND tape - is read at clock C, and the target is the move measured from the NEXT
    clock's entry (C + 60 min) to 15:50. Nothing within an hour of the chain read is traded. If
    the increment survives, no timing artifact of this kind is available to explain it.
    """
    rows = []
    for a, b in zip(CLOCKS[:-1], CLOCKS[1:]):
        left = df[df.clock == a].set_index("date")
        right = df[df.clock == b].set_index("date")
        d = left[TAPE + [CHAIN]].join(right[["fwd"]].rename(columns={"fwd": "fwd_late"}),
                                      how="inner").dropna()
        if len(d) < 300:
            continue
        d = d.assign(y=logs(d.fwd_late.abs().to_numpy()))
        y = d.y.to_numpy()
        f_t, f_tc = ols(y, design(d, TAPE)), ols(y, design(d, TAPE + [CHAIN]))
        rows.append({"read_at": a, "traded_from": b, "n": len(d),
                     "R2_tape": f_t["r2"], "R2_tape+chain": f_tc["r2"],
                     "dR2": f_tc["r2"] - f_t["r2"],
                     "beta_rn_half": float(f_tc["beta"][-1]),
                     "t_rn_half(NW)": float(f_tc["t"][-1]),
                     "survives": bool(f_tc["beta"][-1] > 0
                                      and f_tc["t"][-1] > BONFERRONI_T)})
    return pd.DataFrame(rows)


def stage_f(df: pd.DataFrame) -> pd.DataFrame:
    """POST-HOC. The harder baseline: is the chain incremental only because the tape model is weak?

    A weak control is the commonest way an "incremental information" claim is wrong. TAPE_STRONG
    adds the realized vol of the LAST 30 MINUTES before the clock - the tape's own nowcast, and
    the closest realized analogue of what a 0DTE chain prices - and a fast 5-session level.
    """
    rows = []
    for clock in CLOCKS:
        d = df[df.clock == clock].dropna(subset=TAPE_STRONG + [CHAIN, "y"])
        y = d.y.to_numpy()
        f_s = ols(y, design(d, TAPE_STRONG))
        f_sc = ols(y, design(d, TAPE_STRONG + [CHAIN]))
        rows.append({"clock": clock, "n": len(d),
                     "R2_strongtape": f_s["r2"], "R2_strong+chain": f_sc["r2"],
                     "dR2": f_sc["r2"] - f_s["r2"],
                     "beta_rn_half": float(f_sc["beta"][-1]),
                     "t_rn_half(NW)": float(f_sc["t"][-1]),
                     "survives": bool(f_sc["beta"][-1] > 0
                                      and f_sc["t"][-1] > BONFERRONI_T)})
    return pd.DataFrame(rows)


def stage_f_oos(df: pd.DataFrame) -> pd.DataFrame:
    """POST-HOC. Stage C re-run against TAPE_STRONG - out of sample, two-of-three."""
    rows = []
    for clock in CLOCKS:
        d = df[df.clock == clock].dropna(subset=TAPE_STRONG + [CHAIN, "y"]).reset_index(drop=True)
        f_s, f_sc = oos_forecasts(d, TAPE_STRONG), oos_forecasts(d, TAPE_STRONG + [CHAIN])
        m = np.isfinite(f_s) & np.isfinite(f_sc)
        d = d.loc[m].copy()
        y = d.y.to_numpy()
        e_s, e_c = (y - f_s[m]) ** 2, (y - f_sc[m]) ** 2
        row = {"clock": clock, "n_oos": len(d),
               "rmse_strong": float(np.sqrt(e_s.mean())),
               "rmse_strong+chain": float(np.sqrt(e_c.mean())),
               "d_rmse_%": 100.0 * (np.sqrt(e_c.mean()) / np.sqrt(e_s.mean()) - 1.0),
               "DM_t": dm_stat(e_s - e_c)}
        wins = 0
        for name in REGIMES:
            g = np.asarray(d.regime == name)
            if g.sum() < 100:
                continue
            wins += int(np.sqrt(e_c[g].mean()) < np.sqrt(e_s[g].mean()))
        row["regimes_won"] = wins
        row["PASS"] = bool(row["rmse_strong+chain"] < row["rmse_strong"] and wins >= 2)
        rows.append(row)
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ ledger
def record(name: str, tag: str, row: dict, start: str, end: str) -> None:
    import json
    from datetime import datetime, timezone
    led = ROOT / "research" / "experiments.jsonl"
    rec = {"ts": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
           "algorithm": f"options/{name}", "class": "options", "tag": tag,
           "commit": "", "run_dir": "", "track": "options",
           "params": {k: str(row[k]) for k in ("clock", "predictor") if k in row},
           "start": start, "end": end,
           "stats": {k: (f"{v:.4f}" if isinstance(v, float) else str(v))
                     for k, v in row.items() if k not in ("clock", "predictor")}}
    with led.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")


# ------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--record", action="store_true", help="append DIAGNOSTIC rows to the ledger")
    args = ap.parse_args()

    df = build_panel()
    start, end = df.date.min(), df.date.max()
    print(f"panel: {len(df):,} rows  {df.date.nunique():,} sessions  {start}..{end}")
    print(f"feature-complete (rn_half present): {int(np.isfinite(df.rn_half).sum()):,}")

    print("\n=== GATE 0: does O-5's control reproduce from the frozen cache? ===")
    g, ok = gate0(df)
    print(fmt(g))
    if not ok:
        print("\nGATE 0 FAILED - no verdict is issued.")
        return 1

    print("\n=== STAGE A: univariate skill (descriptive; no verdict turns on it) ===")
    a = stage_a(df)
    print(fmt(a))

    print("\n=== STAGE B: is rn_half INCREMENTAL over the tape, in sample? "
          f"(Newey-West, Bonferroni |t| > {BONFERRONI_T}) ===")
    b = stage_b(df)
    print(fmt(b))
    print(f"\n  clocks with |t| > {BONFERRONI_T}: {int(b['|t|>2.576'].sum())} of {len(b)}"
          f"   declared sign (positive) held: {int(b.sign_ok.sum())} of {len(b)}")
    print(f"  mean delta-R-squared from adding the chain: {b.dR2.mean():+.4f}")

    print("\n=== STAGE C: causal, out of sample (the decisive stage; two-of-three) ===")
    c, oos = stage_c(df)
    cols = ["clock", "n_oos", "rmse_tape", "rmse_chain", "d_rmse_%", "oosR2_tape",
            "oosR2_chain", "DM_t"] + [f"{k}_d_rmse_%" for k in REGIMES] + \
        ["regimes_won", "PASS"]
    print(fmt(c[cols]))
    print(f"\n  clocks passing two-of-three: {int(c.PASS.sum())} of {len(c)}")

    print("\n=== STAGE D: does the increment change a book's risk? "
          f"(MATERIAL declared in advance: sd -{SD_MATERIAL:.0%} or breaches "
          f"-{BREACH_MATERIAL:.0%}) ===")
    dd = stage_d(oos)
    print(fmt(dd))
    print(f"\n  clocks MATERIAL on the pre-registered threshold: "
          f"{int(dd.MATERIAL.sum())} of {len(dd)}")

    print("\n=== VERDICT ===")
    stat_pass = int(c.PASS.sum())
    econ_pass = int(dd.MATERIAL.sum())
    if stat_pass and econ_pass:
        print(f"  PASS - the chain is incremental on {stat_pass} of {len(c)} clocks out of "
              f"sample and MATERIAL on {econ_pass}. The store's surviving product is a RISK "
              f"input.")
    elif stat_pass:
        print(f"  STATISTICAL ONLY - incremental out of sample on {stat_pass} of {len(c)} "
              f"clocks, but MATERIAL on {econ_pass} of {len(dd)}. Real and too small to size on.")
    else:
        print(f"  REFUSED - 0 of {len(c)} clocks clear two-of-three out of sample. "
              f"The chain's magnitude skill is a restatement of the tape.")
    best = c.loc[c["d_rmse_%"].idxmin()]
    print(f"  best clock, chosen with full hindsight: {best.clock}  OOS RMSE "
          f"{best['d_rmse_%']:+.3f}% vs the tape, DM t {best.DM_t:+.2f}, "
          f"regimes won {int(best.regimes_won)} of 3")

    print("\n=== STAGE E (post-hoc): stale-chain test - everything read at C, traded from C+60m "
          "===")
    e = stage_e(df)
    print(fmt(e))
    print(f"\n  pairs where the increment survives a full-hour buffer: "
          f"{int(e.survives.sum())} of {len(e)}")

    print("\n=== STAGE F (post-hoc): against a HARDER tape (adds rv_30m and rv5), in sample ===")
    f = stage_f(df)
    print(fmt(f))
    print(f"\n  clocks where the increment survives the harder baseline: "
          f"{int(f.survives.sum())} of {len(f)}")

    print("\n=== STAGE F-OOS (post-hoc): Stage C against the harder tape, two-of-three ===")
    fo = stage_f_oos(df)
    print(fmt(fo))
    print(f"\n  clocks passing two-of-three against the harder tape: "
          f"{int(fo.PASS.sum())} of {len(fo)}")

    if args.record:
        n = 0
        for _, r in a.iterrows():
            record("odte_o6_magnitude", f"DIAGNOSTIC O-6 stage A {r.predictor} @ {r.clock} "
                   f"[univariate skill on log|move|]", r.to_dict(), start, end)
            n += 1
        for _, r in b.iterrows():
            record("odte_o6_magnitude", f"DIAGNOSTIC O-6 stage B @ {r.clock} "
                   f"[incremental rn_half over tape, in sample, NW]", r.to_dict(), start, end)
            n += 1
        for _, r in c.iterrows():
            record("odte_o6_magnitude", f"DIAGNOSTIC O-6 stage C @ {r.clock} "
                   f"[expanding-window OOS RMSE, two-of-three]", r.to_dict(), start, end)
            n += 1
        for _, r in dd.iterrows():
            record("odte_o6_magnitude", f"DIAGNOSTIC O-6 stage D @ {r.clock} "
                   f"[normalized move, sd and 3-sigma breaches]", r.to_dict(), start, end)
            n += 1
        print(f"\nrecorded {n} DIAGNOSTIC rows under options/odte_o6_magnitude")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
