#!/usr/bin/env python
"""A-17: does an inverse-VaR DE-RISK SWITCH off the REALIZED TAPE cut the intraday sleeve's tail?

    py -3.14 scripts/sweep_a17.py                 # the whole page
    py -3.14 scripts/sweep_a17.py --record        # + DIAGNOSTIC ledger rows

No backtest runs here. Every number comes off series already on disk: A-8's persisted sleeve
P&L (`results/a8/daily_control.csv`, 2,686 sessions of the SHIPPED config), the Alpaca SPY
minute store, and S-29's `data/regime/vix.csv`. The quantile solver and the pinball loss are
IMPORTED from `scripts/sweep_o8.py` and not re-implemented.

WHY THIS ITEM
-------------
O-9 (options track) measured, on SPY and out of sample, that the inverse-VaR switch

    q_hat_t  = expanding-window one-step-ahead 5% quantile regression on four tape features
    budget_t = median(|q_hat_s|) over s < t, expanding, >= 60 prior forecasts   [CAUSAL]
    e_t      = min(1, budget_t / |q_hat_t|)                                     [CUT-ONLY]

cuts the 5% tail of the resulting book 8.0-15.5% AT MATCHED AVERAGE EXPOSURE, at 5 of 5 clocks,
with the mean unchanged inside one SE and a timing placebo ruling out the scale-mixture
explanation. That was the part of O-9 that survived; it uses NO options data and costs nothing
to run. The options track owns no book to de-risk, so it handed the switch here as A-17.

WHAT THIS TEST MUST NOT REPEAT
------------------------------
A-15 REFUSED a magnitude nowcast as a SIZE input on MECHANISM: this sleeve is paid by the
volatility SURPRISE (+$2,651/day per sd, t +8.41) and not by the forecastable part (-$230/day,
t -0.73). A de-risk switch is a different functional - it is paid by the lower quantile alone -
but A-15's mechanism is the first thing to check, and clause 6 below does exactly that, because
if the switch cuts exposure on precisely the days this book is paid, a tail win is bought with
mean.

THE TRAP, NAMED BEFORE ANY NUMBER
---------------------------------
The control book LOSES MONEY (-$324/day over 2,686 sessions). A switch that only ever cuts
therefore "wins" on every statistic by simply holding less. So, exactly as O-9 did:

  * every arm is rescaled to ONE matched average exposure M = min over arms of mean(e_raw);
  * CONST - a flat book at exposure M, i.e. "an unconditional de-risk of the same average
    exposure" - is the control every headline is quoted against, NOT the unscaled sleeve;
  * the unscaled sleeve is printed as context and can never be the comparator.

THE PRE-REGISTERED DESIGN, IN FULL, BEFORE ANY RUN
--------------------------------------------------
 0. NO NEW DATA, NO NEW HARNESS RUN, NOTHING SHIPS. `live/intraday_config.json` is not read or
    written; no runner-loaded or scheduled file is touched. With --record the script appends
    DIAGNOSTIC ledger rows and nothing else.

 1. IDENTITY. `daily_control.csv` must reproduce A-14/A-15's published control book: -$262 /
    -$512 / -$134 per day by regime, -$324 full period, 2,686 sessions. Tolerance $1/day. A
    mismatch means this is not the series the journal describes and the run stops.

 2. THE CLOCK DEVIATION, DECLARED. O-9's switch reads `rv_sofar` and `rng_sofar` - WITHIN-SESSION
    features at five intraday clocks. This book's size multiplier must be linear in k to be
    scored off a persisted daily P&L series (A-15's linearity assumption, whose only breakage is
    the loss limit, priced in clause 5), and the sleeve's first ORB entry is minute 15 (09:45).
    So the switch here is PRE-OPEN and the two within-session features are replaced by their
    strictly-prior-session analogues. This is a real deviation and it can only WEAKEN the
    transplant, never flatter it: a pre-open forecast sees strictly less than a 10:00 one.

        rv20      SPY realized vol, prior 20 sessions of close-to-close log returns [shift(1)]
        absret_1  |SPY prior session close-to-close return|
        rng_1     SPY prior session (high - low) / open
        vix_lag   prior session's VIX close

 3. THE THREE ARMS. One shared feature set; what differs is WHAT the 5% quantile is fitted on.
        SW_SPY     q_hat forecasts SPY's own session return quantile - O-9's literal object,
                   transplanted. A-17's text names SPY, so this arm is the item as written.
        SW_SLEEVE  q_hat forecasts THE SLEEVE'S OWN session return quantile. The switch protects
                   this book, so the honest target is this book. Declared as the arm most likely
                   to work and therefore the one whose failure is most informative.
        SW_INVVOL  e_t = min(1, median(rv20 over s<t) / rv20_t) - no quantile regression at all.
                   The complexity control: if a two-line inverse-vol rule matches the fitted
                   switch, the estimator has not earned itself.
    tau = 0.05, expanding window, one-step-ahead, 250-session burn-in (O-8's constants, imported).
    budget: expanding median of PAST |q_hat|, >= 60 priors. Cap at 1.0 - the switch NEVER levers
    up, because A-15 already refused sizing up on a forecastable quantity.

 4. THE HEADLINE, AND WHAT REPLACES O-9's "4 of 5 CLOCKS". There is one clock here, so the
    unanimity leg cannot be run and is NOT silently dropped: it is replaced by the regime leg
    (2016-2019 / 2020-2023 / 2024-2026, the standing two-of-three rule) plus a block bootstrap.
    Judged against CONST at matched exposure, on the book's daily returns. PASS requires ALL of:
      (a) ES5 cut > 0 and q05 cut > 0 (ES5 is the primary: it averages the whole tail, while
          q05 on 2,686 rows is one order statistic near rank 134);
      (b) the ES5 cut >= 5% (ECON_MATERIAL, O-8/O-9's constant, unchanged);
      (c) a 99% block bootstrap CI on the ES5 cut excluding zero, resampling WHOLE SESSIONS in
          blocks of 5;
      (d) positive ES5 cut in 2 of 3 regimes;
      (e) mean $/day not worse than CONST's by more than one SE of the difference. A tail win
          bought with mean is REFUSED-BY-MEAN, because holding less already does that.
    Max drawdown is reported beside every book because the item asks about drawdown, but it is
    ONE path statistic on ONE sample and is descriptive, never decisive.

 5. FEASIBILITY, and why it is easier here than in A-15. The daily loss limit is a LEVEL (2.5%),
    so a scaled book stops on a different set of sessions. This switch is CUT-ONLY at the raw
    stage, but the matched-exposure rescale can push e above 1, so the check is still owed. Every
    headline is re-scored under A-15's loss-limit-aware book (a session whose SCALED intraday low
    crosses the limit realizes the stop plus the control's own measured 0.098-point flatten
    overshoot) and both numbers are printed. If they disagree in SIGN the limit-aware one wins.

 6. MECHANISM, the A-15 check. cov(e, pnl) decomposes the mean effect: a cut-only switch that
    correlates NEGATIVELY with this book's P&L is selling the days it is paid on. Reported with
    the split of A-15's finding - regress sleeve P&L on the forecastable part of |SPY move| and
    on the surprise - so a failure here is diagnosed rather than merely recorded.

 7. THE PLACEBO O-9 USED, which can only destroy a pass. Permute q_hat across sessions (200
    seeded draws): the exposure MARGINAL is preserved exactly and only the timing is destroyed.
    A real switch must sit outside the 5-95 band of that distribution. This is the leg that rules
    out the scale-mixture explanation - "any random exposure schedule shrinks a tail" - and O-9
    reported it as the thing that made its own result believable.

 8. VERDICT VOCABULARY, fixed in advance. PASS (all of 4a-e, placebo clear) / REFUSED-BY-MEAN /
    REFUSED-BY-TAIL / INDISTINGUISHABLE-FROM-NOISE (inside the placebo band) / REFUSED-BY-CONTROL
    (SW_INVVOL matches the fitted arms, i.e. the estimator bought nothing).
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

from sweep_o8 import qreg  # noqa: E402  - the quantile solver is O-8's, unchanged

REPO = HERE.parent
A8 = REPO / "results" / "a8"
OUT = REPO / "results" / "a17"
SPY_MIN = REPO / "data" / "minute_alpaca" / "SPY.parquet"
VIX_CSV = REPO / "data" / "regime" / "vix.csv"
EXPERIMENTS = REPO / "research" / "experiments.jsonl"

EQUITY = 1_000_000.0
EPS = 1e-12
REGIMES = [("2016-2019", 2016, 2019), ("2020-2023", 2020, 2023), ("2024-2026", 2024, 2026)]

PUBLISHED_CONTROL = {"2016-2019": -262.0, "2020-2023": -512.0, "2024-2026": -134.0}
PUBLISHED_FULL = -324.0
PUBLISHED_SESSIONS = 2686

TAU = 0.05                # the 5% VaR, O-8's TAU_LO
BURN_IN = 250             # sessions before a forecast is emitted, O-8's constant
MIN_BUDGET_OBS = 60       # prior forecasts before the budget exists, O-9's constant
CAP = 1.0                 # cut-only: the switch never levers up
FEATURES = ["rv20", "absret_1", "rng_1", "vix_lag"]
ECON_MATERIAL = 5.0       # percent, O-8/O-9's constant
DAILY_LOSS_LIMIT = 0.025  # intraday_common.DAILY_LOSS_LIMIT, asserted at load
BOOT_REPS = 20_000
BOOT_BLOCK = 5
BOOT_ALPHA = 0.01         # 99% CI
PLACEBO_REPS = 200
RNG_SEED = 17


# ------------------------------------------------------------------------------- statistics
def tstat(x: np.ndarray) -> tuple[float, float, float]:
    n = len(x)
    if n < 2:
        return float("nan"), float("nan"), float("nan")
    se = float(x.std(ddof=1) / np.sqrt(n))
    m = float(x.mean())
    return m, se, (m / se if se else float("nan"))


def book_stats(pnl: np.ndarray, ret: np.ndarray) -> dict:
    """Yearly-reset $1M book, identical convention to `sweep_a15.book_stats`."""
    m, se, t = tstat(pnl)
    path = np.concatenate([[EQUITY], EQUITY * np.cumprod(1.0 + ret)])
    peak = np.maximum.accumulate(path)
    sd = ret.std(ddof=1)
    return {"$/day": m, "se": se, "t": t,
            "sharpe": float(ret.mean() / sd * np.sqrt(252)) if sd else float("nan"),
            "max_dd_%": -float((path / peak - 1.0).min()) * 100,
            "q05_%": q05(ret) * 100, "ES5_%": es05(ret) * 100,
            "worst_%": float(ret.min()) * 100}


def q05(v: np.ndarray) -> float:
    return float(np.quantile(v, TAU))


def es05(v: np.ndarray) -> float:
    c = np.quantile(v, TAU)
    lo = v[v <= c]
    return float(lo.mean()) if len(lo) else float("nan")


def tail_cut(new: np.ndarray, base: np.ndarray, fn=es05) -> float:
    """Percent by which `new` SHRINKS the (negative) lower tail of `base`. Positive = better."""
    b, n = fn(base), fn(new)
    if not np.isfinite(b) or b >= 0:
        return float("nan")
    return 100.0 * (1.0 - n / b)


def table(rows, title: str, note: str = "") -> pd.DataFrame:
    df = pd.DataFrame(rows)
    print(f"\n--- {title}")
    if note:
        print(f"    {note}")
    with pd.option_context("display.width", 200, "display.max_columns", 60,
                           "display.float_format", lambda v: f"{v:,.4f}"):
        print(df.to_string(index=False))
    return df


# ------------------------------------------------------------------------------------ data
def load_control() -> pd.DataFrame:
    f = A8 / "daily_control.csv"
    if not f.exists():
        sys.exit(f"missing {f} - run `python scripts/sweep_a8.py --cells control` first")
    d = pd.read_csv(f)
    d["day"] = pd.to_datetime(d["day"]).dt.date
    d = d.sort_values("day").reset_index(drop=True)
    d["year"] = [x.year for x in d["day"]]
    with np.errstate(divide="ignore", invalid="ignore"):
        d["eq_open"] = np.where(np.abs(d["ret"]) > EPS, d["pnl"] / d["ret"], EQUITY)
    d["low_ret"] = d["low"] / d["eq_open"] - 1.0
    return d


def spy_panel() -> pd.DataFrame:
    """Per-session SPY features. Every column is a function of STRICTLY PRIOR sessions."""
    df = pd.read_parquet(SPY_MIN).tz_convert("America/New_York")
    df["day"] = df.index.strftime("%Y-%m-%d")
    df["hhmm"] = df.index.strftime("%H:%M")
    df = df[df["hhmm"] >= "09:30"]
    g = df.groupby("day", sort=True)
    op, cl = g["o"].first(), g["c"].last()
    hi, lo = g["h"].max(), g["l"].min()
    out = pd.DataFrame({"absmove": (cl / op - 1.0).abs(), "rng_same": (hi - lo) / op})
    ret = np.log(cl / cl.shift(1))
    out["rv20"] = ret.rolling(20).std().shift(1)      # strictly prior 20 sessions
    out["absret_1"] = ret.abs().shift(1)              # prior session's |close-to-close|
    out["rng_1"] = out["rng_same"].shift(1)           # prior session's range
    out = out.reset_index().rename(columns={"index": "day"})
    out["day"] = pd.to_datetime(out["day"]).dt.date
    return out


def vix_panel() -> pd.DataFrame:
    v = pd.read_csv(VIX_CSV)
    v["day"] = pd.to_datetime(v["date"]).dt.date
    v = v.sort_values("day").reset_index(drop=True)
    v["vix_lag"] = v["vix"].shift(1)                  # row d is the close of d, so shift is causal
    return v[["day", "vix_lag"]]


# ------------------------------------------------------------------------------- the switch
def oos_quantiles(X: np.ndarray, y: np.ndarray, tau: float = TAU,
                  burn: int = BURN_IN) -> np.ndarray:
    """Expanding-window one-step-ahead tau-quantile forecasts. NaN over the burn-in.

    Same loop as `sweep_o8.oos_quantiles`: warm-started IRLS, columns scaled by their in-sample
    sd for numerics only (quantile regression is affine-equivariant, so the fitted value cannot
    move). `X` carries the intercept in column 0.
    """
    out = np.full(len(y), np.nan)
    beta = None
    for i in range(burn, len(y)):
        Xi, yi = X[:i], y[:i]
        sd = Xi[:, 1:].std(axis=0)
        sd = np.where(sd > 0, sd, 1.0)
        Xs = np.column_stack([Xi[:, 0], Xi[:, 1:] / sd])
        beta = qreg(Xs, yi, tau, beta0=beta)
        out[i] = float(np.concatenate([[1.0], X[i, 1:] / sd]) @ beta)
    return out


def exposure(q: np.ndarray) -> np.ndarray:
    """budget_t = expanding median of PAST |q_hat|; e_t = min(CAP, budget_t/|q_hat_t|). O-9."""
    a = pd.Series(np.abs(q))
    budget = a.expanding(min_periods=MIN_BUDGET_OBS).median().shift(1)
    return np.minimum(CAP, budget.to_numpy() / np.maximum(np.abs(q), EPS))


def inverse_vol_exposure(rv: np.ndarray) -> np.ndarray:
    """The complexity control: the same shape with the raw feature in place of a fitted q_hat."""
    a = pd.Series(rv)
    budget = a.expanding(min_periods=BURN_IN).median().shift(1)
    return np.minimum(CAP, budget.to_numpy() / np.maximum(rv, EPS))


def limit_aware(e: np.ndarray, ret: np.ndarray, low_ret: np.ndarray,
                overshoot: float) -> np.ndarray:
    """Session returns of an e-scaled book that obeys the daily loss limit as a LEVEL. A-15."""
    stopped = (e * low_ret) <= -DAILY_LOSS_LIMIT
    return np.where(stopped, -(DAILY_LOSS_LIMIT + overshoot), e * ret)


# ------------------------------------------------------------------------------- the clauses
def clause1(d: pd.DataFrame) -> bool:
    rows, ok = [], True
    for name, lo, hi in REGIMES:
        s = d[(d.year >= lo) & (d.year <= hi)]
        got, want = float(s["pnl"].mean()), PUBLISHED_CONTROL[name]
        hit = abs(got - want) <= 1.0
        ok &= hit
        rows.append({"regime": name, "n": len(s), "$/day": got, "published": want, "ok": hit})
    got = float(d["pnl"].mean())
    hit = abs(got - PUBLISHED_FULL) <= 1.0 and len(d) == PUBLISHED_SESSIONS
    ok &= hit
    rows.append({"regime": "full", "n": len(d), "$/day": got, "published": PUBLISHED_FULL,
                 "ok": hit})
    table(rows, "CLAUSE 1 - identity against A-14/A-15's published control book",
          "a mismatch means this is not the series the journal describes")
    return bool(ok)


def build(d: pd.DataFrame) -> pd.DataFrame:
    spy = spy_panel()
    vix = vix_panel()
    m = d.merge(spy, on="day", how="left").merge(vix, on="day", how="left")
    return m


def arms(m: pd.DataFrame) -> dict[str, np.ndarray]:
    """The three raw exposure schedules. Every one is a function of strictly prior sessions."""
    X = np.column_stack([np.ones(len(m))] + [m[c].to_numpy(dtype=float) for c in FEATURES])
    out = {}
    # Both fitted arms forecast a SIGNED session return, because a 5% quantile of a magnitude is
    # not a downside VaR. SW_SPY's target is SPY's open-to-close (O-9's `fwd`); SW_SLEEVE's is the
    # sleeve's own session return.
    spy_ret = m["spy_oc"].to_numpy(dtype=float)
    q_spy = oos_quantiles(X, spy_ret)
    q_slv = oos_quantiles(X, m["ret"].to_numpy(dtype=float))
    out["SW_SPY"] = exposure(q_spy)
    out["SW_SLEEVE"] = exposure(q_slv)
    out["SW_INVVOL"] = inverse_vol_exposure(m["rv20"].to_numpy(dtype=float))
    out["_q_spy"], out["_q_slv"] = q_spy, q_slv
    return out


def matched(e: dict[str, np.ndarray], mask: np.ndarray) -> tuple[dict[str, np.ndarray], float]:
    """Rescale every arm to the SAME average exposure M = min over arms of mean(e_raw). O-9."""
    lvl = min(float(e[k][mask].mean()) for k in e if not k.startswith("_"))
    out = {k: e[k][mask] * (lvl / e[k][mask].mean()) for k in e if not k.startswith("_")}
    out["CONST"] = np.full(int(mask.sum()), lvl)
    return out, lvl


def score(exp: dict[str, np.ndarray], m: pd.DataFrame, mask: np.ndarray,
          overshoot: float) -> tuple[pd.DataFrame, dict]:
    pnl, ret = m["pnl"].to_numpy()[mask], m["ret"].to_numpy()[mask]
    low = m["low_ret"].to_numpy()[mask]
    rows, books = [], {}
    for label, e in exp.items():
        lin_ret, lim_ret = e * ret, limit_aware(e, ret, low, overshoot)
        b_lin = book_stats(e * pnl, lin_ret)
        b_lim = book_stats(lim_ret * m["eq_open"].to_numpy()[mask], lim_ret)
        books[label] = {"e": e, "lin": lin_ret, "lim": lim_ret}
        rows.append({"arm": label, "mean_e": float(e.mean()), "sd_e": float(e.std(ddof=1)),
                     "min_e": float(e.min()), "$/day": b_lin["$/day"], "se": b_lin["se"],
                     "sharpe": b_lin["sharpe"], "q05_%": b_lin["q05_%"], "ES5_%": b_lin["ES5_%"],
                     "max_dd_%": b_lin["max_dd_%"], "worst_%": b_lin["worst_%"],
                     "lim_ES5_%": b_lim["ES5_%"], "lim_max_dd_%": b_lim["max_dd_%"],
                     "n_stopped": int(((e * low) <= -DAILY_LOSS_LIMIT).sum())})
    return pd.DataFrame(rows), books


def bootstrap_cut(new: np.ndarray, base: np.ndarray, rng: np.random.Generator,
                  fn=es05) -> dict:
    """99% CI on the relative tail cut, resampling WHOLE SESSIONS in blocks of BOOT_BLOCK."""
    n = len(new)
    point = tail_cut(new, base, fn)
    nblocks = int(np.ceil(n / BOOT_BLOCK))
    draws = np.empty(BOOT_REPS)
    for r in range(BOOT_REPS):
        starts = rng.integers(0, n, size=nblocks)
        sel = np.concatenate([np.arange(s, s + BOOT_BLOCK) % n for s in starts])[:n]
        draws[r] = tail_cut(new[sel], base[sel], fn)
    draws = draws[np.isfinite(draws)]
    lo = float(np.percentile(draws, 100.0 * BOOT_ALPHA / 2.0))
    hi = float(np.percentile(draws, 100.0 * (1.0 - BOOT_ALPHA / 2.0)))
    return {"cut_%": point, "ci_lo_%": lo, "ci_hi_%": hi,
            "excludes_zero": bool(lo > 0.0 or hi < 0.0), "reps": int(len(draws))}


def placebo(e: np.ndarray, ret: np.ndarray, const: np.ndarray,
            rng: np.random.Generator) -> dict:
    """Permute the exposure schedule across sessions: same marginal, no timing. O-9's control B."""
    real = tail_cut(e * ret, const * ret, es05)
    draws = np.empty(PLACEBO_REPS)
    for r in range(PLACEBO_REPS):
        draws[r] = tail_cut(rng.permutation(e) * ret, const * ret, es05)
    draws = draws[np.isfinite(draws)]
    p5, p95 = float(np.percentile(draws, 5)), float(np.percentile(draws, 95))
    return {"real_cut_%": real, "placebo_mean_%": float(draws.mean()),
            "placebo_p5_%": p5, "placebo_p95_%": p95,
            "outside_band": bool(real > p95 or real < p5),
            "pct_of_placebos_beaten": float((draws < real).mean() * 100)}


def mechanism(m: pd.DataFrame, mask: np.ndarray, e: np.ndarray) -> list[dict]:
    """Clause 6: is the cut aimed at the days this book is paid on? A-15's split, re-used."""
    pnl = m["pnl"].to_numpy()[mask]
    absmove = m["absmove"].to_numpy()[mask]
    rows = []
    kb, pb = float(e.mean()), float(pnl.mean())
    cov = float(np.mean((e - kb) * (pnl - pb)))
    rows.append({"term": "cov(e, pnl) $/day", "value": cov,
                 "reading": "negative = the switch sells the days the book is paid"})
    rows.append({"term": "(mean_e - 1) * mean(pnl) $/day", "value": (kb - 1.0) * pb,
                 "reading": "the leverage term - not the question"})
    rows.append({"term": "corr(e, |SPY move|)", "value": float(np.corrcoef(e, absmove)[0, 1]),
                 "reading": "the switch is supposed to cut on loud days"})
    rows.append({"term": "corr(e, pnl)", "value": float(np.corrcoef(e, pnl)[0, 1]),
                 "reading": "A-15: this book is paid by the SURPRISE, not the forecast"})
    return rows


def record(rows: list[dict], commit: str) -> None:
    with EXPERIMENTS.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    print(f"[ledger] appended {len(rows)} DIAGNOSTIC rows to {EXPERIMENTS}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--record", action="store_true", help="append DIAGNOSTIC ledger rows")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(RNG_SEED)

    import intraday_common
    assert abs(intraday_common.DAILY_LOSS_LIMIT - DAILY_LOSS_LIMIT) < 1e-12, "loss limit drifted"

    print("A-17 - inverse-VaR de-risk switch off the realized tape, on the intraday sleeve.")
    print(f"    tau={TAU}  burn_in={BURN_IN}  budget_min_obs={MIN_BUDGET_OBS}  cap={CAP}")
    print(f"    features (ALL strictly pre-open): {', '.join(FEATURES)}")

    d = load_control()
    if not clause1(d):
        print("\nREFUSED AT CLAUSE 1: the control book is not the published one. Nothing else runs.")
        return 1

    # the control's own flatten overshoot, measured (A-15 clause 8): its stopped sessions realize
    # worse than the -2.5% trigger, and the limit-aware book must charge the same amount.
    stopped = d["stopped"].astype(bool).to_numpy()
    overshoot = float(-d["ret"].to_numpy()[stopped].mean() - DAILY_LOSS_LIMIT)
    print(f"\n[control] {int(stopped.sum())} stopped sessions realize "
          f"{d['ret'].to_numpy()[stopped].mean() * 100:.3f}% -> flatten overshoot "
          f"{overshoot * 100:.3f} points, charged by the limit-aware book")

    m = build(d)
    # SPY's SIGNED open-to-close return is the quantile target for SW_SPY (a downside VaR needs a
    # signed variable); `absmove` is kept for the mechanism leg only.
    spy = pd.read_parquet(SPY_MIN).tz_convert("America/New_York")
    spy["day"] = spy.index.strftime("%Y-%m-%d")
    spy["hhmm"] = spy.index.strftime("%H:%M")
    spy = spy[spy["hhmm"] >= "09:30"]
    g = spy.groupby("day", sort=True)
    oc = (g["c"].last() / g["o"].first() - 1.0).rename("spy_oc").reset_index()
    oc["day"] = pd.to_datetime(oc["day"]).dt.date
    m = m.merge(oc, on="day", how="left")

    feat_ok = np.all(np.isfinite(m[FEATURES + ["spy_oc"]].to_numpy(dtype=float)), axis=1)
    print(f"[data] {int(feat_ok.sum())} of {len(m)} sessions carry every feature")
    m = m.loc[feat_ok].reset_index(drop=True)

    e = arms(m)
    mask = np.all([np.isfinite(e[k]) for k in ("SW_SPY", "SW_SLEEVE", "SW_INVVOL")], axis=0)
    print(f"[oos] {int(mask.sum())} sessions survive the burn-in and the budget window "
          f"({m['day'].iloc[np.flatnonzero(mask)[0]]} .. {m['day'].iloc[np.flatnonzero(mask)[-1]]})")

    exp, lvl = matched(e, mask)
    print(f"[match] matched average exposure M = {lvl:.4f}")

    # context only, and never a comparator: the unscaled book on the same sessions.
    raw = book_stats(m["pnl"].to_numpy()[mask], m["ret"].to_numpy()[mask])
    print(f"[context] the UNSCALED sleeve on these sessions: {raw['$/day']:,.0f} $/day, "
          f"ES5 {raw['ES5_%']:.3f}%, max dd {raw['max_dd_%']:.2f}%")

    # Persist the schedules themselves: the report's strongest sentence is about how CLOSE two of
    # them are, and a reader must be able to check that without re-running the fits.
    ex_df = pd.DataFrame({"day": m["day"].to_numpy()[mask],
                          **{k: exp[k] for k in ("SW_SPY", "SW_SLEEVE", "SW_INVVOL", "CONST")}})
    ex_df.to_csv(OUT / "exposures.csv", index=False)
    corr = ex_df[["SW_SPY", "SW_SLEEVE", "SW_INVVOL"]].corr()
    print("\n--- exposure schedules, pairwise correlation")
    print(corr.to_string())

    tbl, books = score(exp, m, mask, overshoot)
    table(tbl.to_dict("records"), "CLAUSE 4 - the books, ALL at matched average exposure",
          "CONST is the comparator; the unscaled sleeve above is context")
    tbl.to_csv(OUT / "books.csv", index=False)

    ret = m["ret"].to_numpy()[mask]
    eqo = m["eq_open"].to_numpy()[mask]
    const = exp["CONST"]
    base_lin, base_lim = books["CONST"]["lin"], books["CONST"]["lim"]
    dd_const = book_stats(np.zeros(len(base_lin)), base_lin)["max_dd_%"]
    cut_rows = []
    for label in ("SW_SPY", "SW_SLEEVE", "SW_INVVOL"):
        lin = books[label]["lin"]
        dd = (lin - base_lin) * eqo
        cut_rows.append({
            "arm": label,
            "ES5_cut_%": tail_cut(lin, base_lin, es05),
            "q05_cut_%": tail_cut(lin, base_lin, q05),
            "ES5_cut_limaware_%": tail_cut(books[label]["lim"], base_lim, es05),
            "d_$/day_vs_CONST": tstat(dd)[0],
            "se_d": tstat(dd)[1],
            "t_d": tstat(dd)[2],
            "d_max_dd_pts": book_stats(np.zeros(len(lin)), lin)["max_dd_%"] - dd_const,
        })
    cuts = table(cut_rows, "CLAUSE 4a/4b/5 - tail cut against CONST at the same average exposure",
                 f"positive = the tail SHRANK; ECON_MATERIAL bar is {ECON_MATERIAL}%")
    cuts.to_csv(OUT / "cuts.csv", index=False)

    # 4c - the bootstrap, on the primary arm and the headline statistic.
    boot_rows = []
    for label in ("SW_SPY", "SW_SLEEVE", "SW_INVVOL"):
        b = bootstrap_cut(books[label]["lin"], books["CONST"]["lin"], np.random.default_rng(RNG_SEED))
        b["arm"] = label
        boot_rows.append(b)
    boots = table(boot_rows, "CLAUSE 4c - 99% block bootstrap on the ES5 cut (whole sessions, block 5)")
    boots.to_csv(OUT / "bootstrap.csv", index=False)

    # 4d - the regimes.
    years = m["year"].to_numpy()[mask]
    reg_rows = []
    for name, lo, hi in REGIMES:
        sel = (years >= lo) & (years <= hi)
        if sel.sum() < 100:
            continue
        row = {"regime": name, "n": int(sel.sum())}
        for label in ("SW_SPY", "SW_SLEEVE", "SW_INVVOL"):
            row[f"{label}_ES5_cut_%"] = tail_cut(books[label]["lin"][sel],
                                                 books["CONST"]["lin"][sel], es05)
        reg_rows.append(row)
    regs = table(reg_rows, "CLAUSE 4d - ES5 cut by regime (the standing two-of-three rule)")
    regs.to_csv(OUT / "regimes.csv", index=False)

    # 4d(ii) - the same cut YEAR BY YEAR. Not a pass condition; it is how a reader sees whether a
    # weak regime cell is decay or noise, which a three-cell split cannot show.
    yr_rows = []
    for y in sorted(set(years.tolist())):
        sel = years == y
        if sel.sum() < 60:
            continue
        row = {"year": int(y), "n": int(sel.sum())}
        for label in ("SW_SPY", "SW_SLEEVE", "SW_INVVOL"):
            row[f"{label}_%"] = tail_cut(books[label]["lin"][sel], base_lin[sel], es05)
        yr_rows.append(row)
    yrs = table(yr_rows, "CLAUSE 4d(ii) - ES5 cut year by year (descriptive, not a pass condition)")
    yrs.to_csv(OUT / "years.csv", index=False)

    # 7 - the placebo.
    plac_rows = []
    for label in ("SW_SPY", "SW_SLEEVE", "SW_INVVOL"):
        p = placebo(exp[label], ret, const, np.random.default_rng(RNG_SEED + 1))
        p["arm"] = label
        plac_rows.append(p)
    placs = table(plac_rows, "CLAUSE 7 - timing placebo: exposure marginal kept, timing destroyed",
                  "a switch inside the 5-95 band is INDISTINGUISHABLE FROM NOISE")
    placs.to_csv(OUT / "placebo.csv", index=False)

    # 6 - the mechanism.
    mech_rows = []
    for label in ("SW_SPY", "SW_SLEEVE", "SW_INVVOL"):
        for r in mechanism(m, mask, exp[label]):
            r["arm"] = label
            mech_rows.append(r)
    mech = table(mech_rows, "CLAUSE 6 - mechanism: what is the switch actually selling?")
    mech.to_csv(OUT / "mechanism.csv", index=False)

    # ------------------------------------------------------------------ the verdict, by the rule
    print("\n=== VERDICT (clause 8 vocabulary, applied to the rule fixed in clause 4)")
    verdicts = {}
    for label in ("SW_SPY", "SW_SLEEVE", "SW_INVVOL"):
        c = cuts[cuts.arm == label].iloc[0]
        b = boots[boots.arm == label].iloc[0]
        p = placs[placs.arm == label].iloc[0]
        n_reg = sum(1 for _, r in regs.iterrows() if r[f"{label}_ES5_cut_%"] > 0)
        a = bool(c["ES5_cut_%"] > 0 and c["q05_cut_%"] > 0)
        bb = bool(c["ES5_cut_%"] >= ECON_MATERIAL)
        cc = bool(b["excludes_zero"])
        dd = bool(n_reg >= 2)
        ee = bool(c["d_$/day_vs_CONST"] >= -abs(c["se_d"]))
        if not p["outside_band"]:
            v = "INDISTINGUISHABLE-FROM-NOISE"
        elif not a or not bb or not cc or not dd:
            v = "REFUSED-BY-TAIL"
        elif not ee:
            v = "REFUSED-BY-MEAN"
        else:
            v = "PASS"
        verdicts[label] = v
        print(f"  {label:10s} ES5cut {c['ES5_cut_%']:+7.2f}%  q05cut {c['q05_cut_%']:+7.2f}%  "
              f"CI[{b['ci_lo_%']:+.2f},{b['ci_hi_%']:+.2f}]  regimes {n_reg}/3  "
              f"d$/day {c['d_$/day_vs_CONST']:+,.0f} (t {c['t_d']:+.2f})  "
              f"placebo_outside={bool(p['outside_band'])}  ->  {v}")
    fitted_best = max(("SW_SPY", "SW_SLEEVE"),
                      key=lambda k: cuts[cuts.arm == k].iloc[0]["ES5_cut_%"])
    inv = cuts[cuts.arm == "SW_INVVOL"].iloc[0]["ES5_cut_%"]
    best = cuts[cuts.arm == fitted_best].iloc[0]["ES5_cut_%"]
    if verdicts[fitted_best] == "PASS" and np.isfinite(inv) and inv >= best:
        verdicts[fitted_best] = "REFUSED-BY-CONTROL"
        print(f"  -> {fitted_best} downgraded to REFUSED-BY-CONTROL: the two-line inverse-vol "
              f"rule cuts {inv:+.2f}% against the fitted switch's {best:+.2f}%.")

    # ------------------------------------------------------------------ the sensitivity SHELF
    # S-10's standing rule: a parameter result is reported as a SHELF, never as an argmax. The
    # headline cell (250 / 60 / all four features) was fixed in the docstring before the run; this
    # grid exists to show whether it is a plateau or a spike, and it can only weaken the reading.
    print("\n--- CLAUSE 9 - sensitivity shelf on the PASSING arm's construction "
          "(headline cell is burn 250 / budget 60 / 4 features)")
    sens_rows = []
    base_days = m["day"].to_numpy()
    for burn in (250, 500):
        for budobs in (60, 120, 250):
            for fname, fset in (("4feat", FEATURES), ("tape3", ["rv20", "absret_1", "rng_1"])):
                Xs = np.column_stack([np.ones(len(m))]
                                     + [m[c].to_numpy(dtype=float) for c in fset])
                qs = oos_quantiles(Xs, m["ret"].to_numpy(dtype=float), burn=burn)
                a = pd.Series(np.abs(qs))
                bud = a.expanding(min_periods=budobs).median().shift(1)
                es = np.minimum(CAP, bud.to_numpy() / np.maximum(np.abs(qs), EPS))
                mk = np.isfinite(es)
                r, lr = m["ret"].to_numpy()[mk], m["low_ret"].to_numpy()[mk]
                lv = float(es[mk].mean())
                ee = es[mk] * (lv / es[mk].mean())
                cn = np.full(int(mk.sum()), lv)
                sens_rows.append({"burn": burn, "budget_obs": budobs, "features": fname,
                                  "n": int(mk.sum()), "mean_e": lv,
                                  "ES5_cut_%": tail_cut(ee * r, cn * r, es05),
                                  "q05_cut_%": tail_cut(ee * r, cn * r, q05),
                                  "d_max_dd_pts": (book_stats(np.zeros(len(r)), ee * r)["max_dd_%"]
                                                   - book_stats(np.zeros(len(r)), cn * r)["max_dd_%"]),
                                  "headline": bool(burn == BURN_IN and budobs == MIN_BUDGET_OBS
                                                   and fname == "4feat")})
    sens = table(sens_rows, "CLAUSE 9 - SW_SLEEVE construction shelf (12 cells)",
                 "read as a plateau or a spike; the headline cell is flagged, never chosen here")
    sens.to_csv(OUT / "sensitivity.csv", index=False)
    pos = int((sens["ES5_cut_%"] > 0).sum())
    print(f"    {pos} of {len(sens)} cells cut the tail; "
          f"range {sens['ES5_cut_%'].min():+.2f}% .. {sens['ES5_cut_%'].max():+.2f}%, "
          f"median {sens['ES5_cut_%'].median():+.2f}%")

    (OUT / "verdict.json").write_text(json.dumps(verdicts, indent=1), encoding="utf-8")

    if args.record:
        try:
            commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                             cwd=REPO, text=True).strip()
        except Exception:  # noqa: BLE001
            commit = ""
        ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        days = m["day"].to_numpy()[mask]
        rows = []
        for label in ("SW_SPY", "SW_SLEEVE", "SW_INVVOL", "CONST"):
            c = cuts[cuts.arm == label].iloc[0] if label != "CONST" else None
            t = tbl[tbl.arm == label].iloc[0]
            rows.append({
                "ts": ts, "algorithm": "intraday/a17_derisk", "class": "diagnostic",
                "tag": f"A-17 {label}: O-9's inverse-VaR de-risk switch on the intraday sleeve, "
                       f"matched average exposure {lvl:.4f} (DIAGNOSTIC)",
                "commit": commit, "run_dir": "", "track": "A-17",
                "params": {"arm": label, "tau": TAU, "burn_in": BURN_IN, "cap": CAP,
                           "features": FEATURES, "matched_exposure": round(lvl, 6)},
                "start": str(days[0]), "end": str(days[-1]),
                "stats": {"Sessions": str(int(mask.sum())),
                          "Avg Daily PnL": f"{t['$/day']:.0f}",
                          "Sharpe Ratio": f"{t['sharpe']:.3f}",
                          "Drawdown": f"{t['max_dd_%']:.3f}%",
                          "ES5 pct": f"{t['ES5_%']:.4f}",
                          "q05 pct": f"{t['q05_%']:.4f}",
                          "Worst Day pct": f"{t['worst_%']:.4f}",
                          "Mean Exposure": f"{t['mean_e']:.4f}",
                          "ES5 Cut vs CONST pct": ("" if c is None else f"{c['ES5_cut_%']:.3f}"),
                          "Verdict": verdicts.get(label, "control"),
                          "Diagnostic": "true"}})
        record(rows, commit)

    print(f"\n[out] {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
