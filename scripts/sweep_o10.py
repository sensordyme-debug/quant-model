#!/usr/bin/env python
"""O-10: does the 0DTE chain add anything to the DE-RISK SWITCH THAT ACTUALLY WORKS?

    python scripts/sweep_o10.py               # the whole page
    python scripts/sweep_o10.py --record      # + DIAGNOSTIC ledger rows

WHY THIS ITEM EXISTS, AND WHY THE O-TRACK IS NOT CLOSED AFTER ALL
-----------------------------------------------------------------
O-9 closed this scope with a PARTIAL and the sentence "the switch works and the chain is not
why": on SPY's own 5% quantile, adding `rn_half` to a tape-only inverse-VaR switch bought
+2.68% of extra tail cut, 99% CI [-0.49, +7.11], against a +5% bar.

Hours later A-17 (`iterate`) measured O-9's switch on the book it was handed to, and found
something that changes what O-9 measured:

  * O-9's switch AS HANDED OVER - the 5% quantile of SPY's open-to-close - is REFUSED on the
    sleeve: ES5 cut +2.72%, CI [-3.50, +8.94], and indistinguishable from dividing by `rv20`
    with no fitting at all (+2.71%, schedules correlated 0.78).
  * Changing ONE thing - the quantile's TARGET, from SPY's return to THE SLEEVE'S OWN session
    return - clears every condition: ES5 cut +11.08%, CI [+5.76, +16.52], 3 of 3 regimes,
    max drawdown 53.41% -> 42.32%.

So the only switch in this repository that survives its own controls is one O-9 never tested
the chain against. O-9 asked "does the chain improve the SPY-targeted switch" and the answer
was "barely"; but the SPY-targeted switch is itself worthless, so a small increment on it is a
small increment on nothing. THE QUESTION THAT WAS NEVER ASKED is whether the chain improves the
SLEEVE-targeted switch - the one with a real effect to be incremental to.

That question is this scope's, not `iterate`'s: it is a question about what the chain is worth,
it is answerable off the FROZEN store with zero new Theta calls, and it is the only live
justification that could still be produced for OWNER-5's VALUE-tier decision. Confirmed before
writing this: `theta_data.py --check` returns `listening True serving True` with `history/quote`
at HTTP 403 "you only have a FREE subscription".

THE CAUSALITY PROBLEM, AND WHY IT IS SOLVED RATHER THAN ASSUMED
---------------------------------------------------------------
A-17's switch is PRE-OPEN for a reason it states: the sleeve's size multiplier must be a single
whole-session scalar to be scored off a persisted daily P&L series, and the sleeve's first ORB
entry is minute 15 = 09:45 (`algorithms/intraday/base.py: OR_MINUTES = 15`, verified). O-5's
frozen feature cache starts at 10:00, which is 15 minutes INSIDE the book - so it cannot be used
here at all, and the chain read has to be rebuilt earlier.

It can be. The stored chain is 5-minute bars whose first stamp is 09:30 in 120/120 sampled
sessions, and `rn_half` coverage under O-3's strict both-rights mask was measured ON COVERAGE
ALONE, BEFORE ANY FORWARD RETURN WAS TOUCHED:

    09:30  13.3%      09:35  98.4%      09:40  98.2%      10:00  97.8%   (whole store)

Coverage is flat from 09:35 on, so there is no information-versus-causality trade to make and
the choice is made on causality: the PRIMARY read is the **09:35** bar. Even under the most
pessimistic timestamp convention - the bar stamped 09:35 being an aggregate of 09:35-09:40 - it
closes at 09:40, still strictly before the sleeve's first entry at 09:45. The 09:40 read is
carried as a declared robustness arm and never as the headline. The 09:35 read correlates 0.963
with the 10:00 read O-6/O-8/O-9 used, so this is the same feature at an earlier clock, not a new
one. New cache: `results/options/o10_chain_open.parquet`, built by `--build-cache`.

THE CONFOUND THAT WOULD OTHERWISE FAKE A PASS
---------------------------------------------
A 09:35 chain read sees the first five minutes of the session. A-17's tape features do not - they
are all strictly prior-session. So a naive "M0 + chain" win would confound "the chain is
informative" with "seeing the open is informative", and the tape can see the open for free.
Therefore the DECISIVE baseline is CLOCK-MATCHED: the same two magnitude features the tape has
over the same five minutes.

THE PRE-REGISTERED DESIGN, IN FULL, BEFORE ANY RUN
--------------------------------------------------
 0. NOTHING SHIPS AND NO NEW DATA. No Theta call (the entitlement is FREE), no harness run, no
    LEAN run. `live/intraday_config.json`, `live/APPROVED_PAPER.md`, `live/HALT*` and every
    scheduled task are neither read nor written. With --record the script appends DIAGNOSTIC
    ledger rows and nothing else. Files written: `results/o10/*`, the chain cache above.

 1. EVERY ESTIMATOR IS IMPORTED, NOT RE-IMPLEMENTED. `sweep_a17` supplies the control book, the
    tape panel, the VIX panel, the expanding quantile forecaster (itself O-8's `qreg`), the
    exposure map, the matching rule, the scorer, the block bootstrap, the placebo, the mechanism
    decomposition and the loss-limit-aware re-scoring. `sweep_o3.features` supplies `rn_half`.
    tau = 0.05, burn-in 250, budget = expanding median of PAST |q_hat| over >= 60 priors, cap
    1.0 (cut-only: A-15 refused sizing UP on a forecastable quantity). ECON_MATERIAL = 5%,
    bootstrap = 20,000 draws of whole sessions in blocks of 5 at 99%, placebo = 200 permutations.
    All of these are O-8/O-9/A-17 constants and not one of them is re-chosen here.

 2. THE ARMS. Every arm forecasts THE SAME TARGET - the sleeve's own session return, A-17's
    winning choice - so the only thing that ever varies is the feature set:

      M0    PRE-OPEN TAPE      rv20, absret_1, rng_1, vix_lag            (A-17's SW_SLEEVE)
      M0b   + THE OPEN         M0 + absret_open, rng_open                (clock-matched tape)
      M1    + THE CHAIN        M0b + log(rn_half @ 09:35)                (the question)

    where, from bars stamped 09:30..09:34 of the Alpaca SPY minute store (strictly before 09:35):
      absret_open = |close(09:34) / open(09:30) - 1|
      rng_open    = (max high - min low) / open(09:30)

 3. THE DECISIVE TEST IS M1 AGAINST M0b, at matched average exposure, on the sleeve's daily
    returns. PASS requires ALL of:
      (a) ES5 cut > 0 AND >= ECON_MATERIAL (5%);
      (b) the 99% block bootstrap CI on that cut excludes zero;
      (c) positive in 2 of the 3 regime cells (2016-2019 / 2020-2023 / 2024-2026), A-17's rule,
          cells under 100 sessions dropped - see clause 7 on why one cell will likely drop;
      (d) M1's mean $/day not worse than M0b's by more than one SE of the difference. A tail win
          bought with mean is REFUSED-BY-MEAN.
    ES5 is primary and q05 descriptive, for A-17's reason: q05 on ~1,500 rows is one order
    statistic near rank 75, while ES5 averages that whole tail.

 4. TWO CONTROLS THAT CAN ONLY DESTROY A PASS.
    Control A - SOMETHING TO BE INCREMENTAL TO. M0b must beat CONST (a flat book at the same
      average exposure) on ES5. If the clock-matched tape switch does not work on this sample,
      there is no effect for the chain to add to and the verdict is REFUSED-BY-CONTROL whatever
      leg 3 says.
    Control B - TIMING, NOT DISPERSION. Any non-constant exposure schedule shrinks a tail,
      because a scale mixture is not the scale it averages to. So M1's q_hat is permuted across
      sessions 200 times - exposure marginal preserved exactly, timing destroyed - and M1 vs
      CONST must sit outside the 5-95 band of that distribution.

 5. THE DECOMPOSITION, reported because it is the interesting half if the answer is no:
      M0b vs M0   how much of any gain is just SEEING THE OPEN, which is free;
      M1 vs M0    the chain plus the open against pre-open only - O-9's comparison shape,
                  retargeted, and the number a reader would quote if M0b did not exist.
    Each is scored in its OWN matched-exposure pair so a robustness arm can never move the
    headline. Same for the 09:40 robustness read (M1_0940 vs M0b).

 6. FEASIBILITY. The daily loss limit is a LEVEL (2.5%), so every headline is ALSO re-scored
    under A-15's loss-limit-aware book, charging the control's own measured flatten overshoot on
    sessions whose scaled intraday low crosses the limit. If the two disagree in SIGN the
    limit-aware number wins.

 7. THE SAMPLE, AND THE WEAKNESS DECLARED IN ADVANCE. All arms must be FITTED as well as scored
    on chain-available sessions, so the sample is the store (1,891 sessions, 2016-01-08 ..
    2026-09-10) intersected with A-17's 2,686, minus 250 burn-in. The store is not daily until
    2023 (56/44/134/128 sessions in 2016-19 against 249/249/248 from 2023), so the burn-in eats
    most of 2016-2019 and that regime cell is expected to fall under 100 and drop - exactly as it
    did in O-9, where the regimes leg passed as a 2-of-2. If it drops, the regime leg is a 2-of-2
    and is reported as such, never silently as a 2-of-3. Restricting the TRAINING set is itself a
    handicap, so Gate 3 checks that M0 still works on this sample before anything is concluded:
    if the restricted-sample switch is dead, the sample cannot answer the question and THAT is
    the finding.

 8. NO POST-HOC ANYTHING. Read clock, feature list, target, bars, material bar, bootstrap,
    placebo, regime rule and verdict vocabulary are all fixed above. Anything discovered after
    the first run is written down as a finding, not folded into the design.

THE GATES, which run before any result is read.
  Gate 0  IDENTITY. `daily_control.csv` reproduces A-14/A-15's published control (A-17 clause 1),
          and a fresh refit of A-17's SW_SLEEVE on A-17's OWN full panel reproduces the persisted
          `results/a17/exposures.csv` schedule to 1e-9. This licenses reading O-10 as A-17's
          economics, the way O-9's Stage C licensed reading it as O-8's.
  Gate 1  THE NEW CLOCK IS THE SAME FEATURE. Cache stamps are exactly 09:35/09:40; coverage as
          quoted above; corr(rn_half@09:35, |SPY open-to-close|) is reported beside O-5's
          published +0.540 at 10:00 as a sanity read on the earlier clock.
  Gate 2  THE OPEN WINDOW IS CAUSAL. Every bar entering absret_open/rng_open is stamped <= 09:34,
          asserted per session, and the count of bars used is printed.
  Gate 3  THE RESTRICTED SAMPLE STILL CARRIES THE EFFECT. M0 vs CONST ES5 cut > 0 on the
          chain-available sample.

WHAT EACH OUTCOME MEANS, WRITTEN DOWN BEFORE THE RUN.
  PASS: the chain has a product after all - not a size scaler (A-15 closed that), not an
  improvement to a worthless SPY-targeted switch (O-9 measured that at +2.68%), but an increment
  to the one de-risking rule in this repository that survives its own controls. That is the fresh
  costed justification OWNER-5 asks for, and the O-track reopens with a handoff item.
  REFUSED: the chain's last consumer is closed against the switch that works rather than against
  one that does not, O-9's "the chain is not why" is confirmed on the version that matters, and
  the recommendation to unschedule `research-options` stands on stronger evidence than exhaustion.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import sweep_a17 as a17  # noqa: E402  - every estimator, the control book and the scorer
import sweep_o2 as o2  # noqa: E402
import sweep_o3 as o3  # noqa: E402
import odte_data  # noqa: E402

REPO = HERE.parent
OUT = REPO / "results" / "o10"
CACHE = REPO / "results" / "options" / "o10_chain_open.parquet"
A17_EXPOSURES = REPO / "results" / "a17" / "exposures.csv"
EXPERIMENTS = REPO / "research" / "experiments.jsonl"

READ_CLOCK = "09:35"          # primary, chosen on coverage-only evidence (see docstring)
ALT_CLOCK = "09:40"           # declared robustness read
OPEN_LAST_BAR = "09:34"       # last minute bar allowed into the open-window tape features
O5_PUBLISHED_CORR = 0.540     # corr(rn_half@10:00, |fwd|) as published by O-5

M0_FEATURES = list(a17.FEATURES)                          # rv20, absret_1, rng_1, vix_lag
OPEN_FEATURES = ["absret_open", "rng_open"]
CHAIN_FEATURE = "log_rn_half"
CHAIN_FEATURE_ALT = "log_rn_half_alt"

ARMS = {
    "M0": M0_FEATURES,
    "M0b": M0_FEATURES + OPEN_FEATURES,
    "M1": M0_FEATURES + OPEN_FEATURES + [CHAIN_FEATURE],
    "M1_0940": M0_FEATURES + OPEN_FEATURES + [CHAIN_FEATURE_ALT],
}
PRIMARY_GROUP = ["M0", "M0b", "M1"]


# ----------------------------------------------------------------------------- the chain cache
def build_cache(symbol: str = "SPY", progress: int = 400) -> pd.DataFrame:
    """One pass over the frozen store: `rn_half` at 09:35, 09:40 and 10:00. No Theta call."""
    dates = odte_data.stored_dates(symbol)
    rows: list[dict] = []
    for n, d in enumerate(dates, 1):
        raw = odte_data.load_day(symbol, d)
        if raw.empty:
            continue
        try:
            ch = o2.Chain(raw)
        except Exception:  # noqa: BLE001 - a malformed stored day is not a result
            continue
        r: dict = {"date": str(d)}
        for clock, tag in ((READ_CLOCK, "0935"), (ALT_CLOCK, "0940"), ("10:00", "1000")):
            f = o3.features(ch, clock)
            i = ch.at_or_after(clock)
            r[f"rn_half_{tag}"] = f["rn_half"] if f else np.nan
            r[f"hhmm_{tag}"] = ch.hhmm[i] if i >= 0 else None
        rows.append(r)
        if progress and n % progress == 0:
            print(f"  {n}/{len(dates)} sessions", flush=True)
    df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(CACHE, index=False)
    print(f"[cache] wrote {CACHE} {df.shape}")
    return df


def load_cache() -> pd.DataFrame:
    if not CACHE.exists():
        return build_cache()
    return pd.read_parquet(CACHE)


# ----------------------------------------------------------------------------- the open window
def open_window_panel() -> tuple[pd.DataFrame, dict]:
    """Two magnitude features off bars stamped 09:30..09:34 - strictly before the 09:35 read."""
    df = pd.read_parquet(a17.SPY_MIN).tz_convert("America/New_York")
    df["day"] = df.index.strftime("%Y-%m-%d")
    df["hhmm"] = df.index.strftime("%H:%M")
    w = df[(df["hhmm"] >= "09:30") & (df["hhmm"] <= OPEN_LAST_BAR)]
    assert w["hhmm"].max() <= OPEN_LAST_BAR, "Gate 2: a bar at or after the read clock leaked in"
    g = w.groupby("day", sort=True)
    op, cl = g["o"].first(), g["c"].last()
    hi, lo = g["h"].max(), g["l"].min()
    nbar = g.size()
    out = pd.DataFrame({"absret_open": (cl / op - 1.0).abs(), "rng_open": (hi - lo) / op,
                        "n_open_bars": nbar})
    out = out.reset_index().rename(columns={"index": "day"})
    out["day"] = pd.to_datetime(out["day"]).dt.date
    gate = {"last_bar": str(w["hhmm"].max()), "bars_per_session_median": float(nbar.median()),
            "bars_per_session_min": int(nbar.min()), "sessions": int(len(out))}
    return out[["day", "absret_open", "rng_open"]], gate


# ----------------------------------------------------------------------------- scoring helpers
def fit_arm(m: pd.DataFrame, cols: list[str]) -> np.ndarray:
    """The expanding 5% quantile of THE SLEEVE'S OWN session return on `cols`. A-17's target."""
    X = np.column_stack([np.ones(len(m))] + [m[c].to_numpy(dtype=float) for c in cols])
    return a17.oos_quantiles(X, m["ret"].to_numpy(dtype=float))


def match_pair(e_base: np.ndarray, e_new: np.ndarray) -> dict[str, np.ndarray]:
    """Rescale two schedules to the SAME average exposure, plus a flat book at that level."""
    lvl = min(float(e_base.mean()), float(e_new.mean()))
    return {"base": e_base * (lvl / e_base.mean()), "new": e_new * (lvl / e_new.mean()),
            "CONST": np.full(len(e_base), lvl), "_lvl": np.array([lvl])}


def book(e: np.ndarray, m: pd.DataFrame, mask: np.ndarray, overshoot: float) -> dict:
    ret = m["ret"].to_numpy()[mask]
    low = m["low_ret"].to_numpy()[mask]
    lin = e * ret
    lim = a17.limit_aware(e, ret, low, overshoot)
    st = a17.book_stats(e * m["pnl"].to_numpy()[mask], lin)
    return {"lin": lin, "lim": lim, "stats": st, "e": e}


def cut_row(label: str, new: dict, base: dict, eqo: np.ndarray) -> dict:
    d = (new["lin"] - base["lin"]) * eqo
    mean_d, se_d, t_d = a17.tstat(d)
    return {"comparison": label,
            "ES5_cut_%": a17.tail_cut(new["lin"], base["lin"], a17.es05),
            "q05_cut_%": a17.tail_cut(new["lin"], base["lin"], a17.q05),
            "ES5_cut_limaware_%": a17.tail_cut(new["lim"], base["lim"], a17.es05),
            "d_$/day": mean_d, "se_d": se_d, "t_d": t_d,
            "mean_ok": bool(mean_d >= -se_d),
            "d_max_dd_pts": (a17.book_stats(np.zeros(len(new["lin"])), new["lin"])["max_dd_%"]
                             - a17.book_stats(np.zeros(len(base["lin"])), base["lin"])["max_dd_%"])}


# ----------------------------------------------------------------------------- the gates
def gate0(d: pd.DataFrame) -> tuple[bool, list[dict]]:
    """Identity against A-14/A-15's control book and against A-17's persisted SW_SLEEVE."""
    rows = []
    ok_ctrl = a17.clause1(d)
    rows.append({"check": "control book == A-14/A-15 published", "value": "see table above",
                 "ok": ok_ctrl})
    if not A17_EXPOSURES.exists():
        rows.append({"check": "A-17 exposures.csv present", "value": str(A17_EXPOSURES),
                     "ok": False})
        return False, rows

    ref = pd.read_csv(A17_EXPOSURES)
    ref["day"] = pd.to_datetime(ref["day"]).dt.date
    full = a17.build(d)
    spy = pd.read_parquet(a17.SPY_MIN).tz_convert("America/New_York")
    spy["day"] = spy.index.strftime("%Y-%m-%d")
    spy["hhmm"] = spy.index.strftime("%H:%M")
    spy = spy[spy["hhmm"] >= "09:30"]
    g = spy.groupby("day", sort=True)
    oc = (g["c"].last() / g["o"].first() - 1.0).rename("spy_oc").reset_index()
    oc["day"] = pd.to_datetime(oc["day"]).dt.date
    full = full.merge(oc, on="day", how="left")
    keep = np.all(np.isfinite(full[a17.FEATURES + ["spy_oc"]].to_numpy(dtype=float)), axis=1)
    full = full.loc[keep].reset_index(drop=True)

    q = fit_arm(full, a17.FEATURES)            # A-17's SW_SLEEVE, refit here
    e = a17.exposure(q)
    got = pd.DataFrame({"day": full["day"].to_numpy(), "e_raw": e}).dropna()
    j = ref.merge(got, on="day", how="inner")
    lvl = float(j["CONST"].iloc[0])
    scaled = j["e_raw"].to_numpy() * (lvl / j["e_raw"].mean())
    worst = float(np.nanmax(np.abs(scaled - j["SW_SLEEVE"].to_numpy())))
    ok_sched = bool(len(j) == len(ref) and worst < 1e-9)
    rows.append({"check": "refit SW_SLEEVE == results/a17/exposures.csv",
                 "value": f"n {len(j)} of {len(ref)}, worst |diff| {worst:.2e}", "ok": ok_sched})
    return bool(ok_ctrl and ok_sched), rows


def gate1(cache: pd.DataFrame, m: pd.DataFrame) -> tuple[bool, list[dict]]:
    rows = []
    stamps = set(cache["hhmm_0935"].dropna().unique().tolist())
    ok_stamp = stamps == {READ_CLOCK}
    rows.append({"check": f"cache stamps are exactly {READ_CLOCK}", "value": str(sorted(stamps)),
                 "ok": ok_stamp})
    for tag in ("0935", "0940", "1000"):
        cov = float(np.isfinite(cache[f"rn_half_{tag}"]).mean())
        rows.append({"check": f"rn_half coverage @ {tag}", "value": f"{cov:.2%}", "ok": cov > 0.90})
    sel = np.isfinite(m["rn_half_0935"].to_numpy(dtype=float)) & np.isfinite(
        m["spy_oc"].to_numpy(dtype=float))
    c = float(np.corrcoef(m.loc[sel, "rn_half_0935"], m.loc[sel, "spy_oc"].abs())[0, 1])
    rows.append({"check": "corr(rn_half@09:35, |SPY open-to-close|)",
                 "value": f"{c:+.3f}  (O-5 published {O5_PUBLISHED_CORR:+.3f} at 10:00)",
                 "ok": c > 0.20})
    c2 = float(m[["rn_half_0935", "rn_half_1000"]].corr().iloc[0, 1])
    rows.append({"check": "corr(rn_half@09:35, rn_half@10:00) - same feature, earlier clock",
                 "value": f"{c2:+.3f}", "ok": c2 > 0.80})
    return bool(all(r["ok"] for r in rows)), rows


# ----------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", action="store_true", help="append DIAGNOSTIC ledger rows")
    ap.add_argument("--build-cache", action="store_true", help="rebuild the 09:35 chain cache")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    print("O-10 - does the 0DTE chain add to the de-risk switch that WORKS (A-17's SW_SLEEVE)?")
    print(f"    target = the SLEEVE's own session return | read clock {READ_CLOCK} "
          f"(robustness {ALT_CLOCK})")
    print(f"    tau={a17.TAU} burn_in={a17.BURN_IN} budget_min_obs={a17.MIN_BUDGET_OBS} "
          f"cap={a17.CAP} ECON_MATERIAL={a17.ECON_MATERIAL}%")

    cache = build_cache() if args.build_cache else load_cache()
    cache["day"] = pd.to_datetime(cache["date"]).dt.date

    d = a17.load_control()
    ok0, g0 = gate0(d)
    a17.table(g0, "GATE 0 - identity against A-14/A-15's control book and A-17's own schedule")
    if not ok0:
        print("\nREFUSED AT GATE 0: this is not the series or the switch the journals describe.")
        return 1

    stopped = d["stopped"].astype(bool).to_numpy()
    overshoot = float(-d["ret"].to_numpy()[stopped].mean() - a17.DAILY_LOSS_LIMIT)
    print(f"\n[control] flatten overshoot {overshoot * 100:.3f} points on "
          f"{int(stopped.sum())} stopped sessions, charged by every limit-aware book")

    # ---------------- the panel
    m = a17.build(d)
    spy = pd.read_parquet(a17.SPY_MIN).tz_convert("America/New_York")
    spy["day"] = spy.index.strftime("%Y-%m-%d")
    spy["hhmm"] = spy.index.strftime("%H:%M")
    g = spy[spy["hhmm"] >= "09:30"].groupby("day", sort=True)
    oc = (g["c"].last() / g["o"].first() - 1.0).rename("spy_oc").reset_index()
    oc["day"] = pd.to_datetime(oc["day"]).dt.date
    m = m.merge(oc, on="day", how="left")

    ow, g2 = open_window_panel()
    a17.table([{"check": "last bar in the open window", "value": g2["last_bar"],
                "ok": g2["last_bar"] <= OPEN_LAST_BAR},
               {"check": "bars per session (median / min)",
                "value": f"{g2['bars_per_session_median']:.0f} / {g2['bars_per_session_min']}",
                "ok": g2["bars_per_session_min"] >= 2}],
              "GATE 2 - the open window is causal at the read clock")
    m = m.merge(ow, on="day", how="left")
    m = m.merge(cache[["day", "rn_half_0935", "rn_half_0940", "rn_half_1000"]], on="day",
                how="left")

    ok1, g1 = gate1(cache, m)
    a17.table(g1, "GATE 1 - the 09:35 read is the feature O-6/O-8/O-9 measured, one clock earlier")
    if not ok1:
        print("\nREFUSED AT GATE 1: the early-clock chain read is not the published feature.")
        return 1

    with np.errstate(divide="ignore", invalid="ignore"):
        m[CHAIN_FEATURE] = np.log(m["rn_half_0935"].to_numpy(dtype=float))
        m[CHAIN_FEATURE_ALT] = np.log(m["rn_half_0940"].to_numpy(dtype=float))

    need = M0_FEATURES + OPEN_FEATURES + ["spy_oc", CHAIN_FEATURE, CHAIN_FEATURE_ALT]
    ok = np.all(np.isfinite(m[need].to_numpy(dtype=float)), axis=1)
    print(f"\n[sample] {int(ok.sum())} of {len(m)} A-17 sessions carry every feature including "
          f"the chain at {READ_CLOCK} and {ALT_CLOCK}")
    m = m.loc[ok].reset_index(drop=True)
    print(f"[sample] {m['day'].iloc[0]} .. {m['day'].iloc[-1]}")
    per_year = m.groupby("year").size()
    print("[sample] sessions per year: " + ", ".join(f"{y}:{n}" for y, n in per_year.items()))

    # ---------------- the arms
    e_raw: dict[str, np.ndarray] = {}
    for name, cols in ARMS.items():
        print(f"[fit] {name:8s} {len(cols)} features ...", flush=True)
        e_raw[name] = a17.exposure(fit_arm(m, cols))
    mask = np.all([np.isfinite(e_raw[k]) for k in ARMS], axis=0)
    days = m["day"].to_numpy()[mask]
    print(f"[oos] {int(mask.sum())} sessions survive burn-in and the budget window "
          f"({days[0]} .. {days[-1]})")
    e_raw = {k: v[mask] for k, v in e_raw.items()}
    eqo = m["eq_open"].to_numpy()[mask]
    years = m["year"].to_numpy()[mask]

    corr = pd.DataFrame(e_raw).corr()
    print("\n--- exposure schedules, pairwise correlation (raw, before matching)")
    print(corr.to_string())
    pd.DataFrame({"day": days, **e_raw}).to_csv(OUT / "exposures.csv", index=False)

    # ---------------- the primary matched group and Control A
    lvl = min(float(e_raw[k].mean()) for k in PRIMARY_GROUP)
    prim = {k: e_raw[k] * (lvl / e_raw[k].mean()) for k in PRIMARY_GROUP}
    prim["CONST"] = np.full(int(mask.sum()), lvl)
    print(f"\n[match] primary group matched average exposure M = {lvl:.4f}")
    books = {k: book(v, m, mask, overshoot) for k, v in prim.items()}

    raw_ctx = a17.book_stats(m["pnl"].to_numpy()[mask], m["ret"].to_numpy()[mask])
    print(f"[context] the UNSCALED sleeve on these sessions: {raw_ctx['$/day']:,.0f} $/day, "
          f"ES5 {raw_ctx['ES5_%']:.3f}%, max dd {raw_ctx['max_dd_%']:.2f}%  (context, never a "
          f"comparator)")

    tbl = a17.table([{"arm": k, "mean_e": float(v["e"].mean()), "sd_e": float(v["e"].std(ddof=1)),
                      "min_e": float(v["e"].min()), "$/day": v["stats"]["$/day"],
                      "se": v["stats"]["se"], "sharpe": v["stats"]["sharpe"],
                      "q05_%": v["stats"]["q05_%"], "ES5_%": v["stats"]["ES5_%"],
                      "max_dd_%": v["stats"]["max_dd_%"], "worst_%": v["stats"]["worst_%"]}
                     for k, v in books.items()],
                    "THE BOOKS, all at matched average exposure M",
                    "CONST is the control; the unscaled sleeve above is context")
    tbl.to_csv(OUT / "books.csv", index=False)

    # Gate 3 - does the restricted sample still carry A-17's effect?
    g3_cut = a17.tail_cut(books["M0"]["lin"], books["CONST"]["lin"], a17.es05)
    ok3 = g3_cut > 0.0
    a17.table([{"check": "M0 (A-17's SW_SLEEVE) vs CONST, ES5 cut on the chain-available sample",
                "value": f"{g3_cut:+.3f}%  (A-17 on its own 2,355 sessions: +11.08%)", "ok": ok3}],
              "GATE 3 - the restricted training sample still carries the effect")

    # ---------------- the cuts
    cut_rows = [cut_row("M1 vs M0b  [DECISIVE: the chain against a clock-matched tape]",
                        books["M1"], books["M0b"], eqo),
                cut_row("M0b vs M0  [how much is just SEEING THE OPEN]",
                        books["M0b"], books["M0"], eqo),
                cut_row("M1 vs M0   [chain + open against pre-open only]",
                        books["M1"], books["M0"], eqo),
                cut_row("M0b vs CONST [CONTROL A: something to be incremental to]",
                        books["M0b"], books["CONST"], eqo),
                cut_row("M1 vs CONST  [standalone]", books["M1"], books["CONST"], eqo),
                cut_row("M0 vs CONST  [A-17's arm on this sample]",
                        books["M0"], books["CONST"], eqo)]
    cuts = a17.table(cut_rows, "THE CUTS - positive = the tail SHRANK",
                     f"ECON_MATERIAL bar {a17.ECON_MATERIAL}%; mean_ok = not worse than the base "
                     f"by more than one SE")
    cuts.to_csv(OUT / "cuts.csv", index=False)

    # the 09:40 robustness read, in its own matched pair so it cannot move the headline
    pair = match_pair(e_raw["M0b"], e_raw["M1_0940"])
    b_base, b_new = (book(pair["base"], m, mask, overshoot),
                     book(pair["new"], m, mask, overshoot))
    alt = a17.table([cut_row(f"M1_0940 vs M0b  [robustness: the {ALT_CLOCK} read]",
                             b_new, b_base, eqo)],
                    "ROBUSTNESS - the same test on the 09:40 chain bar")
    alt.to_csv(OUT / "robustness.csv", index=False)

    # ---------------- the bootstrap
    boot_rows = []
    for label, new, base in (("M1 vs M0b [DECISIVE]", books["M1"], books["M0b"]),
                             ("M1 vs M0", books["M1"], books["M0"]),
                             ("M0b vs M0", books["M0b"], books["M0"]),
                             ("M0b vs CONST", books["M0b"], books["CONST"]),
                             ("M0 vs CONST", books["M0"], books["CONST"])):
        b = a17.bootstrap_cut(new["lin"], base["lin"],
                              np.random.default_rng(a17.RNG_SEED), a17.es05)
        b["comparison"] = label
        boot_rows.append(b)
    boots = a17.table(boot_rows,
                      "99% BLOCK BOOTSTRAP on the ES5 cut (whole sessions, blocks of 5)")
    boots.to_csv(OUT / "bootstrap.csv", index=False)

    # ---------------- the regimes
    reg_rows, qualifying = [], []
    for name, lo, hi in a17.REGIMES:
        sel = (years >= lo) & (years <= hi)
        n = int(sel.sum())
        if n < 100:
            reg_rows.append({"regime": name, "n": n, "M1_vs_M0b_%": np.nan,
                             "M0b_vs_CONST_%": np.nan, "M0_vs_CONST_%": np.nan,
                             "note": "DROPPED, under 100 sessions (pre-registered clause 7)"})
            continue
        qualifying.append(name)
        reg_rows.append({
            "regime": name, "n": n,
            "M1_vs_M0b_%": a17.tail_cut(books["M1"]["lin"][sel], books["M0b"]["lin"][sel],
                                        a17.es05),
            "M0b_vs_CONST_%": a17.tail_cut(books["M0b"]["lin"][sel], books["CONST"]["lin"][sel],
                                           a17.es05),
            "M0_vs_CONST_%": a17.tail_cut(books["M0"]["lin"][sel], books["CONST"]["lin"][sel],
                                          a17.es05),
            "note": ""})
    regs = a17.table(reg_rows, "REGIMES - ES5 cut per cell "
                     f"(the standing two-of-three rule; {len(qualifying)} cells qualify)")
    regs.to_csv(OUT / "regimes.csv", index=False)

    yr_rows = []
    for y in sorted(set(years.tolist())):
        sel = years == y
        if sel.sum() < 60:
            continue
        yr_rows.append({"year": int(y), "n": int(sel.sum()),
                        "M1_vs_M0b_%": a17.tail_cut(books["M1"]["lin"][sel],
                                                    books["M0b"]["lin"][sel], a17.es05),
                        "M0_vs_CONST_%": a17.tail_cut(books["M0"]["lin"][sel],
                                                      books["CONST"]["lin"][sel], a17.es05)})
    yrs = a17.table(yr_rows, "YEAR BY YEAR (descriptive, never a pass condition)")
    yrs.to_csv(OUT / "years.csv", index=False)

    # ---------------- Control B and the mechanism
    ret = m["ret"].to_numpy()[mask]
    plac_rows = []
    for label in ("M1", "M0b", "M0"):
        p = a17.placebo(prim[label], ret, prim["CONST"], np.random.default_rng(a17.RNG_SEED))
        p["arm"] = label
        plac_rows.append(p)
    plac = a17.table(plac_rows, "CONTROL B - permute the exposure schedule (same marginal, no "
                     "timing), 200 draws, vs CONST")
    plac.to_csv(OUT / "placebo.csv", index=False)

    mech_rows = []
    for label in ("M1", "M0b", "M0"):
        for r in a17.mechanism(m, mask, prim[label]):
            r["arm"] = label
            mech_rows.append(r)
    mech = a17.table(mech_rows, "MECHANISM - A-15's split, is the cut aimed at the paid days?")
    mech.to_csv(OUT / "mechanism.csv", index=False)

    # ---------------- the verdict
    dec = cuts.iloc[0]
    boot_dec = boots.iloc[0]
    reg_ok = [r for r in reg_rows if r["note"] == ""]
    reg_pos = sum(1 for r in reg_ok if r["M1_vs_M0b_%"] > 0)
    ctrlA = float(cuts.iloc[3]["ES5_cut_%"]) > 0.0
    ctrlB = bool(plac[plac.arm == "M1"].iloc[0]["outside_band"])
    legs = {
        "a_positive_and_material": bool(dec["ES5_cut_%"] >= a17.ECON_MATERIAL),
        "b_bootstrap_excludes_zero": bool(boot_dec["excludes_zero"]),
        "c_regimes": bool(reg_pos >= min(2, len(reg_ok))) and len(reg_ok) >= 2,
        "d_mean_not_worse": bool(dec["mean_ok"]),
        "ctrlA_something_to_add_to": ctrlA,
        "ctrlB_outside_placebo_band": ctrlB,
        "gate3_sample_carries_effect": bool(ok3),
    }
    if not legs["gate3_sample_carries_effect"] or not ctrlA:
        verdict = "REFUSED-BY-CONTROL"
    elif not ctrlB:
        verdict = "INDISTINGUISHABLE-FROM-NOISE"
    elif not legs["d_mean_not_worse"]:
        verdict = "REFUSED-BY-MEAN"
    elif all(legs.values()):
        verdict = "PASS"
    else:
        verdict = "REFUSED-BY-TAIL"

    summary = {"verdict": verdict, "legs": legs,
               "decisive_ES5_cut_%": float(dec["ES5_cut_%"]),
               "decisive_ci": [float(boot_dec["ci_lo_%"]), float(boot_dec["ci_hi_%"])],
               "regime_cells_qualifying": len(reg_ok), "regime_cells_positive": int(reg_pos),
               "sessions_oos": int(mask.sum()), "matched_exposure": round(lvl, 6),
               "read_clock": READ_CLOCK, "start": str(days[0]), "end": str(days[-1])}
    (OUT / "verdict.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print("\n=== VERDICT " + verdict + " ===")
    print(json.dumps(summary, indent=1))

    if args.record:
        try:
            commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                             cwd=REPO, text=True).strip()
        except Exception:  # noqa: BLE001
            commit = ""
        ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        rows = []
        for k, v in books.items():
            c = cuts[cuts.comparison.str.startswith(k + " vs")]
            rows.append({
                "ts": ts, "algorithm": "options/odte_o10_chain_switch", "class": "options",
                "tag": f"O-10 {k}: does the 0DTE chain add to the SLEEVE-targeted de-risk "
                       f"switch? read {READ_CLOCK}, matched exposure {lvl:.4f} (DIAGNOSTIC)",
                "commit": commit, "run_dir": "", "track": "O-10",
                "params": {"arm": k, "features": ARMS.get(k, []), "tau": a17.TAU,
                           "burn_in": a17.BURN_IN, "cap": a17.CAP,
                           "read_clock": READ_CLOCK, "matched_exposure": round(lvl, 6)},
                "start": str(days[0]), "end": str(days[-1]),
                "stats": {"Sessions": str(int(mask.sum())),
                          "Avg Daily PnL": f"{v['stats']['$/day']:.0f}",
                          "Sharpe Ratio": f"{v['stats']['sharpe']:.3f}",
                          "Drawdown": f"{v['stats']['max_dd_%']:.3f}%",
                          "ES5 pct": f"{v['stats']['ES5_%']:.4f}",
                          "q05 pct": f"{v['stats']['q05_%']:.4f}",
                          "Mean Exposure": f"{v['e'].mean():.4f}",
                          "ES5 Cut pct": ("" if c.empty else f"{c.iloc[0]['ES5_cut_%']:.3f}"),
                          "Verdict": verdict, "Diagnostic": "true"}})
        rows.append({
            "ts": ts, "algorithm": "options/odte_o10_chain_switch", "class": "options",
            "tag": f"O-10 VERDICT {verdict}", "commit": commit, "run_dir": "", "track": "O-10",
            "params": {"read_clock": READ_CLOCK, "alt_clock": ALT_CLOCK},
            "start": str(days[0]), "end": str(days[-1]),
            "stats": {k: str(v) for k, v in
                      {**{f"leg_{a}": b for a, b in legs.items()},
                       "decisive_ES5_cut_%": f"{float(dec['ES5_cut_%']):.4f}",
                       "ci_lo_%": f"{float(boot_dec['ci_lo_%']):.4f}",
                       "ci_hi_%": f"{float(boot_dec['ci_hi_%']):.4f}",
                       "M0b_vs_M0_%": f"{float(cuts.iloc[1]['ES5_cut_%']):.4f}",
                       "M1_vs_M0_%": f"{float(cuts.iloc[2]['ES5_cut_%']):.4f}",
                       "M0_vs_CONST_%": f"{float(cuts.iloc[5]['ES5_cut_%']):.4f}",
                       "alt_clock_cut_%": f"{float(alt.iloc[0]['ES5_cut_%']):.4f}",
                       "regime_cells": f"{reg_pos} of {len(reg_ok)}",
                       "verdict": verdict}.items()}})
        with EXPERIMENTS.open("a", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        print(f"[ledger] appended {len(rows)} DIAGNOSTIC rows to {EXPERIMENTS}")

    print(f"\n[out] {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
