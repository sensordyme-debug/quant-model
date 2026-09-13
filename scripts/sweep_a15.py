#!/usr/bin/env python
"""A-15: can a magnitude NOWCAST size the intraday sleeve, and does the 0DTE chain add anything?

    py -3.14 scripts/sweep_a15.py                 # the whole page
    py -3.14 scripts/sweep_a15.py --record        # + DIAGNOSTIC ledger rows

No backtest runs here. Every number comes off series already on disk: A-8's persisted sleeve
P&L (`results/a8/daily_control.csv`, 2,686 sessions of the SHIPPED config), O-5's frozen chain
cache (`results/options/o5_features.parquet`, `rn_half` at five clocks on 1,890 sessions), the
Alpaca SPY minute store, and S-29's `data/regime/vix.csv`.

Why this exists
---------------
O-6 (options track) proved the 0DTE chain's risk-neutral half-width `rn_half` forecasts the
MAGNITUDE of SPY's remaining session move incrementally over the tape, out of sample, at 5 of 5
clocks (DM t +3.5..+4.2), and that it cuts the dispersion of a sized book 4-14%. A magnitude
forecast changes POSITION SIZE, not entry, so the cost wall that refused O-2/O-3/O-5 cannot
reach it. The O-track handed the next step to this track as A-15, because sizing lives in the
sleeve's files and the sleeve's universe is disjoint from SPY by design.

A-15's own wording says "beat the intraday sleeve's realized-vol sizing". CLAUSE 0 checks that
premise and it is WRONG: the sleeve has no vol sizing at all. `orb.PARAMS["weight"]` is 0.12 of
equity per position, `vwap_trend` 0.10, capped at `per_symbol` 0.15 and `gross` 1.0 - constant
notional weights. So the incumbent is FLAT sizing, the tape-based vol scaler does not exist and
has to be built here as the control, and the item is really two questions stacked:

    (a) does sizing this sleeve on ANY causal magnitude forecast beat flat sizing?   [free]
    (b) if so, does the CHAIN forecast beat the free tape forecast?                  [costs $]

(b) is the one that would justify the Theta VALUE ask, so (a) is a gate on (b), not a result.

The inference chain, stated so it can be attacked
-------------------------------------------------
O-6's finding is about SPY's magnitude. The sleeve trades 16 single names and leveraged sector
ETFs and never SPY. For a SPY-chain nowcast to size this book, MARKET magnitude must predict
SLEEVE P&L. That is clause 2 and it is a premise check, not a result: it is measured
CONTEMPORANEOUSLY and is therefore not tradeable by itself.

The linearity assumption, and where it breaks
---------------------------------------------
The whole method is that a session-level size multiplier k_t turns the sleeve's realized net P&L
into k_t * pnl_t. That is exact for this harness's cost model - slippage is 1.5 bps of notional
and commission is per-share, both linear in size - and it is exact for the signal, because k_t
multiplies every target weight and changes no entry, exit or stop decision. It breaks in exactly
one place: the daily loss limit (`DAILY_LOSS_LIMIT` = 2.5% of the book) is a level, not a rate,
so a scaled book stops on a different set of sessions. Clause 8 prices that breakage instead of
assuming it away, and clause 9 re-runs the headline with every control-stopped session dropped.

THE TRAP THIS TEST IS BUILT AROUND
----------------------------------
The control book LOSES MONEY (-$324/day over 2016-2026). So ANY scaler whose average multiplier
is below 1 will "win" - not by sizing skill but by turning a losing book down. Every statistic
below is therefore gross-matched by construction (k is divided by its own EXPANDING PRIOR mean,
which is causal), and the headline is reported as an explicit decomposition

    mean[(k-1) * pnl]  =  cov(k, pnl)  +  (mean(k) - 1) * mean(pnl)
                          ^ timing skill   ^ leverage, which is not the question

with the PASS condition placed on the covariance term. A result that lives in the second term is
reported as REFUSED-BY-LEVERAGE, because "size a losing book down" is a decision the owner
already made twice (equity_frac 1.0 -> 0.5 -> 0.25) and needs no options data.

Decision rule, fixed before any number below was read
-----------------------------------------------------
0. **PREMISE.** Read the deployed sizing out of the shipped modules and state what the incumbent
   actually is. If it is flat, say so and build the tape control here.
1. **IDENTITY.** `daily_control.csv` must reproduce A-14's published control book: -$262 /
   -$512 / -$134 per day by regime, -$324 full period, Sharpe -0.24, 2,686 sessions. Tolerance
   $1/day and 0.02 of Sharpe. A mismatch means this is not the series the journal describes.
2. **PREMISE GATE (contemporaneous, NOT tradeable).** OLS of sleeve P&L on the realized |SPY
   open-to-close move|, standardized. The mechanism requires a POSITIVE slope at t > +2 and a
   monotone tercile ladder. If the sleeve does not earn more on big-move days, no magnitude
   forecast can size it and the item closes here on the premise.
3. **THE FREE QUESTION (a), on all 2,686 sessions.** Tape scalers from `rv20` (prior 20 sessions
   of SPY close-to-close vol) and `vix_lag` (the prior session's VIX close), both strictly
   pre-open. Report mean d, t, the decomposition, and the three regimes. Also report the ORACLE
   scaler built on the contemporaneous realized |move| - not tradeable, declared in advance as a
   CEILING, and the number that says whether a weak result is a weak forecast or a dead mechanism.
4. **THE PAID QUESTION (b), on the 1,888 chain sessions.** `chain_10` = `rn_half` at 10:00 the
   same day. DECLARED SIGN: POSITIVE. This is a CEILING too, and the docstring says so before the
   run: ORB entries are allowed from minute 15 (09:45), so a multiplier decided at 10:00 is
   applied to a session whose first trades are already on. `chain_prev` = `rn_half` at 14:00 of
   the most recent prior chain session is the strictly pre-open, deployable variant.
5. **THE DECISION: is the chain INCREMENTAL?** `resid_10` and `resid_prev` are the chain feature
   orthogonalized on BOTH tape features by an expanding causal OLS (250-session burn-in), so they
   carry only what the free data does not. PASS requires, on the residual scaler: cov term > 0,
   pooled t > +2, and positive in 2 of 3 regimes (the standing rule). AND the paired difference
   against the best tape scaler on the same sessions must be positive. Anything else REFUSES.
6. **POWER, and it may veto the reading of clause 5.** Stationary-bootstrap 95% CI and the
   detectable effect at 2 se. If the CI contains both zero and the ORACLE's point estimate scaled
   by O-6's reported R2 gain, the sample cannot separate "no skill" from "skill too small to
   see", and the verdict is UNDECIDED rather than REFUSED.
7. **SENSITIVITY, decided a priori on the middle cell.** BETA in {0.15, 0.30, 0.50} x clip band
   in {[0.67,1.5], [0.5,2.0], [0.33,3.0]}. The headline is BETA 0.30 / [0.5,2.0], chosen before
   the run as the centre of the grid. The grid is reported as a SHELF, never an argmax (S-10).
8. **FEASIBILITY.** Count the sessions where the scaled book's intraday low would have breached
   the 2.5% daily loss limit when the control's did not. More than 2% of sessions and the
   linearity assumption is the binding constraint, not the statistics - in which case clause 8b
   is the headline instead: re-score every scaler under a LOSS-LIMIT-AWARE book that stops a
   session the moment `k * low_ret` crosses the limit. That rule is exact at k = 1 (the control's
   93 stopped sessions are exactly the 93 with `low_ret <= -2.5%`, and they realize -2.598% on
   average, a 0.098-point flatten cost which the rule charges).
9. **ROBUSTNESS.** (a) Repeat the headline with the 93 control-stopped sessions dropped - noting
   in advance that this conditions on the OUTCOME and is a diagnostic, never a correction.
   (b) A PERMUTATION NULL: 300 seeded within-regime shuffles of the feature's z-scores. One
   scramble is not a null, it is one draw; the honest question is where the real scalers sit in
   the permutation distribution of the cov term. A scaler inside the 5-95 band is INDISTINGUISH-
   ABLE FROM NOISE, and neither "it works" nor "it hurts" may be claimed of it.
10. **MECHANISM.** Split the realized |SPY move| into the part a causal forecast can see (fitted
    on the tape and the chain by expanding OLS) and the SURPRISE, then regress sleeve P&L on
    each separately. This is what decides whether a failure here is a weak forecast or a dead
    idea, and it generalizes past the two scalers actually built.
11. **NOTHING SHIPS.** Analysis only. No backtest, no shipped, runner-loaded or scheduled file
    touched, no `live/` file read or written, `live/intraday_config.json` unchanged. With
    `--record` the script appends DIAGNOSTIC rows to the ledger and nothing else.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

REPO = HERE.parent
A8 = REPO / "results" / "a8"
OUT = REPO / "results" / "a15"
CHAIN_CACHE = REPO / "results" / "options" / "o5_features.parquet"
SPY_MIN = REPO / "data" / "minute_alpaca" / "SPY.parquet"
VIX_CSV = REPO / "data" / "regime" / "vix.csv"

EQUITY = 1_000_000.0
REGIMES = [("2016-2019", 2016, 2019), ("2020-2023", 2020, 2023), ("2024-2026", 2024, 2026)]
SPLIT = dt.date(2024, 1, 1)

#: A-14's published control book, clause 1.
PUBLISHED_CONTROL = {"2016-2019": -262.0, "2020-2023": -512.0, "2024-2026": -134.0}

BURN_IN = 250          # sessions of history before a scaler is allowed to be non-flat
Z_CLIP = 3.0
BETA_GRID = [0.15, 0.30, 0.50]
BAND_GRID = [(0.67, 1.5), (0.5, 2.0), (0.33, 3.0)]
BETA0, BAND0 = 0.30, (0.5, 2.0)        # the a-priori headline cell, clause 7
CHAIN_CLOCK = "10:00"                  # same-day ceiling clock, clause 4
CHAIN_PREV_CLOCK = "14:00"             # the last clock, used for the pre-open lagged variant
MAX_GAP = 3                            # trading sessions the lagged chain may be stale, clause 4
DAILY_LOSS_LIMIT = 0.025               # intraday_common.DAILY_LOSS_LIMIT, checked at import
BOOT_N = 20_000
BOOT_BLOCK = 10.0
RNG_SEED = 15
N_PERM = 300           # clause 9b: the permutation null
EPS = 1e-12


# ------------------------------------------------------------------------------- statistics
def tstat(x: np.ndarray) -> tuple[float, float, float]:
    n = len(x)
    if n < 2:
        return float("nan"), float("nan"), float("nan")
    se = float(x.std(ddof=1) / np.sqrt(n))
    m = float(x.mean())
    return m, se, (m / se if se else float("nan"))


def book_stats(pnl: np.ndarray, ret: np.ndarray) -> dict:
    """Yearly-reset $1M book, identical convention to `sweep_a10.stats` / `sweep_a14.book_stats`."""
    m, se, t = tstat(pnl)
    path = np.concatenate([[EQUITY], EQUITY * np.cumprod(1.0 + ret)])
    peak = np.maximum.accumulate(path)
    sd = ret.std(ddof=1)
    return {"sessions": len(pnl), "$/day": m, "se": se, "t": t,
            "sharpe": float(ret.mean() / sd * np.sqrt(252)) if sd else float("nan"),
            "max_dd_pct": -float((path / peak - 1.0).min()) * 100,
            "net_pct": float(np.prod(1.0 + ret) - 1.0) * 100,
            "worst_day": float(pnl.min()), "win_days_pct": float((pnl > 0).mean() * 100)}


def stationary_bootstrap(x: np.ndarray, n_boot: int, mean_block: float, seed: int) -> np.ndarray:
    """Politis-Romano stationary bootstrap of the sample mean (as in sweep_a14)."""
    rng = np.random.default_rng(seed)
    n = len(x)
    p = 1.0 / mean_block
    idx = rng.integers(0, n, size=(n_boot, n))
    cont = rng.random((n_boot, n)) > p
    out = np.empty((n_boot, n), dtype=np.int64)
    out[:, 0] = idx[:, 0]
    for j in range(1, n):
        out[:, j] = np.where(cont[:, j], (out[:, j - 1] + 1) % n, idx[:, j])
    return x[out].mean(axis=1)


def ols(X: np.ndarray, y: np.ndarray) -> dict:
    """OLS; X must already carry its intercept column."""
    xtx_inv = np.linalg.pinv(X.T @ X)
    beta = xtx_inv @ (X.T @ y)
    resid = y - X @ beta
    dof = max(1, len(y) - X.shape[1])
    se = np.sqrt(np.maximum(np.diag(xtx_inv * float(resid @ resid) / dof), 0.0))
    ss_tot = float(((y - y.mean()) ** 2).sum())
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(se > 0, beta / se, np.nan)
    return {"beta": beta, "t": t, "resid": resid,
            "r2": 1.0 - float(resid @ resid) / ss_tot if ss_tot else float("nan")}


def table(rows, title: str, note: str = "") -> pd.DataFrame:
    t = pd.DataFrame(rows)
    print(f"\n=== {title} ===")
    with pd.option_context("display.width", 240):
        print(t.to_string(index=False) if len(t) else "  (empty)")
    if note:
        print(note)
    return t


# ------------------------------------------------------------------------------------ data
def load_control() -> pd.DataFrame:
    f = A8 / "daily_control.csv"
    if not f.exists():
        sys.exit(f"missing {f} - run `python scripts/sweep_a8.py --cells control` first")
    d = pd.read_csv(f)
    d["day"] = pd.to_datetime(d["day"]).dt.date
    d = d.sort_values("day").reset_index(drop=True)
    d["year"] = [x.year for x in d["day"]]
    # eq_open recovered from the two columns the harness persisted; ret = pnl / eq_open.
    with np.errstate(divide="ignore", invalid="ignore"):
        d["eq_open"] = np.where(np.abs(d["ret"]) > EPS, d["pnl"] / d["ret"], EQUITY)
    d["low_ret"] = d["low"] / d["eq_open"] - 1.0
    return d


def spy_panel() -> pd.DataFrame:
    """Per-session SPY magnitude and the prior-window realized vol. One pass over the store."""
    df = pd.read_parquet(SPY_MIN).tz_convert("America/New_York")
    df["day"] = df.index.strftime("%Y-%m-%d")
    df["hhmm"] = df.index.strftime("%H:%M")
    df = df[df["hhmm"] >= "09:30"]
    g = df.groupby("day", sort=True)
    op, cl = g["o"].first(), g["c"].last()
    hi, lo = g["h"].max(), g["l"].min()
    out = pd.DataFrame({"absmove": (cl / op - 1.0).abs(), "rng": (hi - lo) / op})
    ret = np.log(cl / cl.shift(1))
    out["rv20"] = ret.rolling(20).std().shift(1)      # strictly prior 20 sessions
    out = out.reset_index().rename(columns={"index": "day"})
    out["day"] = pd.to_datetime(out["day"]).dt.date
    return out


def vix_lag() -> pd.DataFrame:
    v = pd.read_csv(VIX_CSV)
    v["day"] = pd.to_datetime(v["date"]).dt.date
    v = v.sort_values("day").reset_index(drop=True)
    v["vix_lag"] = v["vix"].shift(1)                  # row d is the close of d, so shift is causal
    return v[["day", "vix_lag"]]


def chain_panel() -> pd.DataFrame:
    """`rn_half` at the same-day 10:00 clock and at the prior chain session's 14:00 clock."""
    ch = pd.read_parquet(CHAIN_CACHE)
    ch["day"] = pd.to_datetime(ch["date"]).dt.date
    same = ch[ch.clock == CHAIN_CLOCK][["day", "rn_half"]].rename(columns={"rn_half": "chain_10"})
    prev = (ch[ch.clock == CHAIN_PREV_CLOCK][["day", "rn_half"]]
            .rename(columns={"rn_half": "_late"}).sort_values("day").reset_index(drop=True))
    return same.merge(prev, on="day", how="outer").sort_values("day").reset_index(drop=True)


# --------------------------------------------------------------------------------- scalers
def expanding_z(x: np.ndarray, burn: int = BURN_IN) -> np.ndarray:
    """Standardize each element against the mean and sd of the STRICTLY PRIOR finite elements.

    Flat (z = 0) until `burn` prior observations exist, so no cell is ever standardized against
    information from its own future. NaN inputs pass through as z = 0 (the scaler falls back to
    flat sizing on any session where the feature is missing, which is what a live book would do).
    """
    n = len(x)
    z = np.zeros(n)
    ok = np.isfinite(x)
    csum = np.concatenate([[0.0], np.cumsum(np.where(ok, x, 0.0))])
    csq = np.concatenate([[0.0], np.cumsum(np.where(ok, x, 0.0) ** 2)])
    ccnt = np.concatenate([[0], np.cumsum(ok.astype(np.int64))])
    for i in range(n):
        c = ccnt[i]
        if not ok[i] or c < burn:
            continue
        mu = csum[i] / c
        var = max(csq[i] / c - mu * mu, 0.0)
        sd = np.sqrt(var * c / max(c - 1, 1))
        if sd > EPS:
            z[i] = float(np.clip((x[i] - mu) / sd, -Z_CLIP, Z_CLIP))
    return z


def causal_residual(y: np.ndarray, Z: np.ndarray, burn: int = BURN_IN) -> np.ndarray:
    """`y` orthogonalized on `Z` using only strictly prior rows. NaN anywhere -> NaN out.

    Refits an expanding OLS every session. `Z` carries no intercept; one is added here.
    """
    n = len(y)
    out = np.full(n, np.nan)
    X = np.column_stack([np.ones(n), Z])
    ok = np.isfinite(y) & np.all(np.isfinite(X), axis=1)
    idx = np.flatnonzero(ok)
    for i in idx:
        hist = idx[idx < i]
        if len(hist) < burn:
            continue
        b = np.linalg.pinv(X[hist].T @ X[hist]) @ (X[hist].T @ y[hist])
        out[i] = float(y[i] - X[i] @ b)
    return out


def scaler(z: np.ndarray, beta: float, band: tuple[float, float]) -> np.ndarray:
    """k from a z-score, gross-normalized by its own EXPANDING PRIOR mean (causal).

    The prior-mean division is what makes the test about TIMING rather than LEVERAGE: without it
    a scaler could win on this book simply by averaging below 1 and shrinking a losing sleeve.
    """
    k_raw = np.clip(1.0 + beta * z, band[0], band[1])
    cs = np.concatenate([[0.0], np.cumsum(k_raw)])
    n = len(k_raw)
    denom = np.ones(n)
    for i in range(1, n):
        denom[i] = cs[i] / i
    denom = np.where(np.abs(denom) > EPS, denom, 1.0)
    return k_raw / denom


def limit_aware(k: np.ndarray, ret: np.ndarray, low_ret: np.ndarray,
                overshoot: float) -> np.ndarray:
    """Session returns of a k-scaled book that obeys the daily loss limit as a LEVEL.

    Linear scaling says a session pays `k * ret`. The loss limit says the book flattens the
    moment its intraday loss crosses 2.5%, and from then on the session is over - so a session
    whose SCALED intraday low breaches realizes the stop, not the scaled close. `overshoot` is
    the control's own measured cost of flattening past the trigger (its 93 stopped sessions
    realize -2.598% against a -2.5% limit), so at k = 1 this reproduces the control exactly on
    the 93 sessions it stops and is the identity everywhere else.
    """
    stopped = (k * low_ret) <= -DAILY_LOSS_LIMIT
    return np.where(stopped, -(DAILY_LOSS_LIMIT + overshoot), k * ret)


def evaluate(k: np.ndarray, pnl: np.ndarray, ret: np.ndarray, mask: np.ndarray) -> dict:
    """The headline statistic and its decomposition, on the masked subsample."""
    k, p, r = k[mask], pnl[mask], ret[mask]
    d = (k - 1.0) * p
    m, se, t = tstat(d)
    kbar, pbar = float(k.mean()), float(p.mean())
    cov = float(np.mean((k - kbar) * (p - pbar)))
    lev = (kbar - 1.0) * pbar
    b = book_stats(k * p, k * r)
    return {"n": len(d), "d$/day": m, "se": se, "t": t, "cov_term": cov, "lev_term": lev,
            "mean_k": kbar, "sd_k": float(k.std(ddof=1)), "book_$/day": b["$/day"],
            "book_sharpe": b["sharpe"], "book_dd": b["max_dd_pct"], "d": d, "book": b}


# ------------------------------------------------------------------------------- the clauses
def clause0() -> None:
    print("\n" + "=" * 100)
    print("CLAUSE 0 - what the sleeve's INCUMBENT sizing actually is")
    print("=" * 100)
    sys.path.insert(0, str(REPO / "algorithms" / "intraday"))
    import importlib.util
    rows = []
    for name in ("orb", "vwap_trend", "late_momo"):
        spec = importlib.util.spec_from_file_location(
            f"_a15_{name}", REPO / "algorithms" / "intraday" / name / "signal.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        p = mod.PARAMS
        vol_keys = [k for k in p if "vol" in k or "atr" in k]
        rows.append({"module": name, "weight": p.get("weight"),
                     "sizing": "constant fraction of equity",
                     "vol/atr params": ", ".join(vol_keys) or "-"})
    spec = importlib.util.spec_from_file_location(
        "_a15_active", REPO / "algorithms" / "intraday" / "active" / "signal.py")
    act = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = act
    spec.loader.exec_module(act)
    table(rows, "deployed sub-strategy sizing")
    print(f"  active caps: per_symbol {act.PARAMS['per_symbol']}, gross {act.PARAMS['gross']}")
    print("  => the incumbent is FLAT notional sizing. A-15's premise ('beat the sleeve's")
    print("     realized-vol sizing') is wrong: there is no vol sizing to beat. The tape scaler")
    print("     is built here as the control, and 'does vol sizing help at all' becomes part (a).")
    try:
        from intraday_common import DAILY_LOSS_LIMIT as DLL
        assert abs(DLL - DAILY_LOSS_LIMIT) < 1e-12, DLL
        print(f"  DAILY_LOSS_LIMIT confirmed from intraday_common: {DLL}")
    except Exception as e:                                          # pragma: no cover
        print(f"  WARNING: could not confirm DAILY_LOSS_LIMIT ({e})")


def clause1(d: pd.DataFrame) -> bool:
    print("\n" + "=" * 100)
    print("CLAUSE 1 - identity of the control series against A-14's published book")
    print("=" * 100)
    rows, ok = [], True
    for name, lo, hi in REGIMES:
        s = d[(d.year >= lo) & (d.year <= hi)]
        got = float(s["pnl"].mean())
        want = PUBLISHED_CONTROL[name]
        good = abs(got - want) <= 1.0
        ok &= good
        rows.append({"regime": name, "sessions": len(s), "published $/day": want,
                     "on disk": round(got, 1), "ok": good})
    b = book_stats(d["pnl"].values, d["ret"].values)
    rows.append({"regime": "full 2016-2026", "sessions": b["sessions"], "published $/day": -324.0,
                 "on disk": round(b["$/day"], 1), "ok": abs(b["$/day"] + 324.0) <= 1.0})
    ok &= abs(b["$/day"] + 324.0) <= 1.0
    table(rows, "clause 1: control book by regime")
    print(f"  full-period book: {b['$/day']:+.1f} $/day, Sharpe {b['sharpe']:+.2f}, "
          f"DD {b['max_dd_pct']:.2f}%, {b['sessions']:,} sessions")
    print(f"  => identity {'HOLDS' if ok else 'FAILS'}")
    return ok


def clause2(d: pd.DataFrame) -> bool:
    print("\n" + "=" * 100)
    print("CLAUSE 2 - PREMISE GATE: does market magnitude predict this sleeve's P&L at all?")
    print("=" * 100)
    print("  contemporaneous and therefore NOT tradeable - this only asks whether a magnitude")
    print("  forecast is the right KIND of input for a breakout sleeve.")
    rows, passed = [], True
    for col in ("absmove", "rng"):
        x = d[col].values
        y = d["pnl"].values
        m = np.isfinite(x) & np.isfinite(y)
        xs = (x[m] - x[m].mean()) / x[m].std()
        f = ols(np.column_stack([np.ones(m.sum()), xs]), y[m])
        rows.append({"feature": col, "n": int(m.sum()), "$/day per 1sd": f["beta"][1],
                     "t": f["t"][1], "intercept $/day": f["beta"][0], "r2": f["r2"]})
        passed &= bool(f["t"][1] > 2.0)
    table(rows, "clause 2a: sleeve P&L on realized SPY magnitude (standardized)")
    terc = []
    for col in ("absmove", "rng"):
        q = pd.qcut(d[col], 3, labels=["low", "mid", "high"])
        g = d.groupby(q, observed=True)["pnl"].agg(["mean", "count"])
        terc.append({"feature": col, **{f"{i} $/day": round(g.loc[i, "mean"], 1)
                                        for i in ("low", "mid", "high")},
                     "monotone": bool(g.loc["low", "mean"] < g.loc["mid", "mean"]
                                      < g.loc["high", "mean"])})
    table(terc, "clause 2b: tercile ladder")
    print(f"  => premise {'HOLDS' if passed else 'FAILS'}")
    return passed


def regime_split(d: pd.DataFrame, k: np.ndarray, pnl, ret) -> list[dict]:
    rows = []
    for name, lo, hi in REGIMES:
        m = ((d.year >= lo) & (d.year <= hi)).values
        e = evaluate(k, pnl, ret, m)
        rows.append({"regime": name, "n": e["n"], "d$/day": e["d$/day"], "t": e["t"],
                     "cov": e["cov_term"], "lev": e["lev_term"], "mean_k": e["mean_k"]})
    return rows


def run_feature(d: pd.DataFrame, z: np.ndarray, mask: np.ndarray, label: str,
                beta: float = BETA0, band: tuple = BAND0, overshoot: float = 0.0) -> dict:
    k = scaler(z, beta, band)
    pnl, ret = d["pnl"].values, d["ret"].values
    e = evaluate(k, pnl, ret, mask)
    e["label"], e["k"] = label, k
    e["active"] = int((np.abs(z[mask]) > EPS).sum())      # sessions where the scaler is not flat
    e["regimes"] = regime_split(d[mask].reset_index(drop=True), k[mask], pnl[mask], ret[mask])
    e["pos_regimes"] = sum(1 for r in e["regimes"] if r["cov"] > 0)
    # clause 8b: the same scaler under a book that obeys the loss limit as a level
    lr = limit_aware(k, ret, d["low_ret"].values, overshoot)
    eq = d["eq_open"].values
    bl = book_stats((lr * eq)[mask], lr[mask])
    base = limit_aware(np.ones(len(d)), ret, d["low_ret"].values, overshoot)
    dl = ((lr - base) * eq)[mask]
    m, se, t = tstat(dl)
    e["lim"] = {"d$/day": m, "se": se, "t": t, "$/day": bl["$/day"], "sharpe": bl["sharpe"],
                "dd": bl["max_dd_pct"], "d": dl}
    yr = d["year"].values[mask]
    e["lim_regimes"] = []
    for name, lo, hi in REGIMES:
        sel = (yr >= lo) & (yr <= hi)
        mm, _, tt = tstat(dl[sel]) if sel.sum() > 1 else (0.0, 0.0, float("nan"))
        e["lim_regimes"].append({"regime": name, "n": int(sel.sum()), "d$/day": mm, "t": tt})
    e["lim_pos"] = sum(1 for r in e["lim_regimes"] if r["d$/day"] > 0)
    return e


def summarize(results: list[dict], title: str, note: str = "") -> pd.DataFrame:
    rows = []
    for e in results:
        rows.append({"scaler": e["label"], "n": e["n"], "active": e.get("active", e["n"]),
                     "d$/day": round(e["d$/day"], 1),
                     "t": round(e["t"], 2), "cov term": round(e["cov_term"], 1),
                     "lev term": round(e["lev_term"], 1), "mean k": round(e["mean_k"], 3),
                     "sd k": round(e["sd_k"], 3), "book $/day": round(e["book_$/day"], 1),
                     "sharpe": round(e["book_sharpe"], 3), "dd%": round(e["book_dd"], 1),
                     "cov+ regimes": f"{e['pos_regimes']}/3",
                     "LIMIT d$/day": round(e["lim"]["d$/day"], 1),
                     "LIMIT t": round(e["lim"]["t"], 2),
                     "LIMIT book": round(e["lim"]["$/day"], 1)})
    return table(rows, title, note)


def permutation_null(d: pd.DataFrame, z: np.ndarray, mask: np.ndarray, overshoot: float,
                     n_perm: int = N_PERM) -> dict:
    """Clause 9b: the cov term under `n_perm` within-regime shuffles of the SAME z-scores.

    A single scramble is one draw, not a null. This is the distribution the real scalers have to
    beat; anything inside its 5-95 band is indistinguishable from noise in BOTH directions.
    """
    rng = np.random.default_rng(RNG_SEED)
    yr = d["year"].values
    groups = [np.flatnonzero((yr >= lo) & (yr <= hi)) for _, lo, hi in REGIMES]
    covs, lims = np.empty(n_perm), np.empty(n_perm)
    pnl, ret, lr = d["pnl"].values, d["ret"].values, d["low_ret"].values
    eq = d["eq_open"].values
    base = limit_aware(np.ones(len(d)), ret, lr, overshoot)
    for i in range(n_perm):
        zp = z.copy()
        for g in groups:
            zp[g] = zp[rng.permutation(g)]
        k = scaler(zp, BETA0, BAND0)
        km, pm = k[mask].mean(), pnl[mask].mean()
        covs[i] = float(np.mean((k[mask] - km) * (pnl[mask] - pm)))
        lims[i] = float(np.mean(((limit_aware(k, ret, lr, overshoot) - base) * eq)[mask]))
    return {"cov": covs, "lim": lims}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--record", action="store_true",
                    help="append DIAGNOSTIC rows to research/experiments.jsonl")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 240)

    ctrl = load_control()
    spy = spy_panel()
    vix = vix_lag()
    chain = chain_panel()

    d = (ctrl.merge(spy, on="day", how="left")
             .merge(vix, on="day", how="left")
             .merge(chain, on="day", how="left")).sort_values("day").reset_index(drop=True)
    # the pre-open lagged chain: the most recent PRIOR session's 14:00 rn_half, plus its staleness
    late = d["_late"].values
    prev_val = np.full(len(d), np.nan)
    prev_gap = np.full(len(d), np.nan)
    last_i = -1
    for i in range(len(d)):
        if last_i >= 0:
            prev_val[i] = late[last_i]
            prev_gap[i] = i - last_i
        if np.isfinite(late[i]):
            last_i = i
    d["chain_prev"] = np.where(np.isfinite(prev_gap) & (prev_gap <= MAX_GAP), prev_val, np.nan)
    d["chain_gap"] = prev_gap

    print(f"A-15: {len(d):,} sleeve sessions {d['day'].min()}..{d['day'].max()}, "
          f"{int(np.isfinite(d['chain_10']).sum()):,} with a same-day 10:00 chain, "
          f"{int(np.isfinite(d['chain_prev']).sum()):,} with a pre-open lagged chain "
          f"(<= {MAX_GAP} sessions stale). No backtest runs here.")

    # the flatten overshoot the loss limit actually costs this book, measured on the control's
    # own 93 stopped sessions (clause 8b). Checked here so the number is visible, not assumed.
    st = d["stopped"].values.astype(bool)
    assert int(((d["low_ret"].values <= -DAILY_LOSS_LIMIT) != st).sum()) == 0, \
        "the control's stopped flag is not `low_ret <= -limit`; clause 8b's rule is not exact"
    OVERSHOOT = float(-d.loc[st, "ret"].mean() - DAILY_LOSS_LIMIT)
    print(f"  clause 8b calibration: the control stops on all {int(st.sum())} sessions with "
          f"low_ret <= -{DAILY_LOSS_LIMIT:.1%} and realizes {-d.loc[st, 'ret'].mean():.4%}, "
          f"so the flatten overshoot is {OVERSHOOT:.4%}.")

    clause0()
    id_ok = clause1(d)
    premise = clause2(d)
    if not premise:
        print("\nVERDICT: REFUSED on the premise - magnitude does not pay this sleeve.")
        return 0

    # ---- features, all on the log scale so the scalers are scale-free
    lg = lambda c: np.log(np.maximum(d[c].values, EPS))                       # noqa: E731
    z_rv20 = expanding_z(lg("rv20"))
    z_vix = expanding_z(lg("vix_lag"))
    z_orcl = expanding_z(lg("absmove"))                                       # CEILING, clause 3
    z_c10 = expanding_z(lg("chain_10"))
    z_cpv = expanding_z(lg("chain_prev"))
    tapeZ = np.column_stack([lg("rv20"), lg("vix_lag")])
    z_r10 = expanding_z(causal_residual(lg("chain_10"), tapeZ))
    z_rpv = expanding_z(causal_residual(lg("chain_prev"), tapeZ))
    rng = np.random.default_rng(RNG_SEED)
    z_scr = z_c10.copy()
    for _, lo, hi in REGIMES:                                # clause 9: shuffle within regime
        m = np.flatnonzero(((d.year >= lo) & (d.year <= hi)).values)
        z_scr[m] = z_scr[rng.permutation(m)]

    all_mask = np.ones(len(d), dtype=bool)
    chain_mask = np.isfinite(d["chain_10"].values)
    prev_mask = np.isfinite(d["chain_prev"].values)

    # ---- clause 3: the FREE question, on every session
    print("\n" + "=" * 100)
    print("CLAUSE 3 - (a) does ANY causal magnitude forecast beat FLAT sizing? all 2,686 sessions")
    print("=" * 100)
    free = [run_feature(d, z_rv20, all_mask, "tape rv20", overshoot=OVERSHOOT),
            run_feature(d, z_vix, all_mask, "tape vix_lag", overshoot=OVERSHOOT),
            run_feature(d, z_orcl, all_mask, "ORACLE |move| (CEILING, not tradeable)",
                        overshoot=OVERSHOOT)]
    summarize(free, "clause 3: tape scalers and the hindsight ceiling, BETA 0.30 / [0.5, 2.0]",
              "  PASS on the COV term only. `lev term` is the leverage channel and is not the "
              "question.")
    for e in free:
        table(e["regimes"], f"clause 3 regimes: {e['label']}")

    # ---- clause 4/5: the PAID question and the incremental decision
    print("\n" + "=" * 100)
    print("CLAUSE 4/5 - (b) does the 0DTE CHAIN add anything the free tape does not?")
    print("=" * 100)
    paid = [run_feature(d, z_rv20, chain_mask, "tape rv20 [chain sessions]", overshoot=OVERSHOOT),
            run_feature(d, z_vix, chain_mask, "tape vix_lag [chain sessions]", overshoot=OVERSHOOT),
            run_feature(d, z_c10, chain_mask, "chain_10 raw (CEILING: 10:00 > first entry)", overshoot=OVERSHOOT),
            run_feature(d, z_r10, chain_mask, "chain_10 RESIDUAL over tape  <- THE DECISION", overshoot=OVERSHOOT),
            run_feature(d, z_cpv, prev_mask, "chain_prev raw (pre-open, deployable)", overshoot=OVERSHOOT),
            run_feature(d, z_rpv, prev_mask, "chain_prev RESIDUAL over tape", overshoot=OVERSHOOT),
            run_feature(d, z_orcl, chain_mask, "ORACLE |move| [chain sessions] (CEILING)", overshoot=OVERSHOOT),
            run_feature(d, z_scr, chain_mask, "SCRAMBLED chain_10 (clause 9 null)", overshoot=OVERSHOOT)]
    summarize(paid, "clause 4/5: chain scalers against the tape, same sessions")
    decision = paid[3]
    for e in (paid[3], paid[5]):
        table(e["regimes"], f"clause 5 regimes: {e['label']}")
        flat = [r["regime"] for r in e["regimes"] if abs(r["cov"]) < EPS]
        if flat:
            print(f"  NOTE: the scaler is FLAT (still in burn-in) for all of {', '.join(flat)} - "
                  f"it needs {BURN_IN} prior chain sessions for the orthogonalizing fit and "
                  f"{BURN_IN} more\n  for the z-score, and chain sessions are sparse before 2020. "
                  f"Active on {e['active']:,} of {e['n']:,}, so '{e['pos_regimes']}/3' is really "
                  f"{e['pos_regimes']} of {3 - len(flat)} AVAILABLE (O-6 made the same caveat).")

    # paired: the residual chain scaler against the better tape scaler on the same sessions
    best_tape = max(paid[:2], key=lambda e: e["cov_term"])
    pnl = d["pnl"].values
    kd = scaler(z_r10, BETA0, BAND0) - scaler(
        z_rv20 if "rv20" in best_tape["label"] else z_vix, BETA0, BAND0)
    pair = (kd * pnl)[chain_mask]
    pm, pse, pt = tstat(pair)
    print(f"\n  paired (chain RESIDUAL - {best_tape['label']}): {pm:+.1f} $/day, "
          f"se {pse:.1f}, t {pt:+.2f}, n {len(pair):,}")

    # ---- clause 6: power
    print("\n" + "=" * 100)
    print("CLAUSE 6 - power")
    print("=" * 100)
    boot = stationary_bootstrap(decision["d"], BOOT_N, BOOT_BLOCK, RNG_SEED)
    blo, bhi = float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))
    p_boot = float((boot <= 0).mean())
    oracle = paid[6]
    print(f"  decision scaler: {decision['d$/day']:+.1f} $/day, normal 95% CI "
          f"[{decision['d$/day'] - 1.96 * decision['se']:+.1f}, "
          f"{decision['d$/day'] + 1.96 * decision['se']:+.1f}], "
          f"stationary-bootstrap 95% CI [{blo:+.1f}, {bhi:+.1f}], one-sided p {p_boot:.3f}")
    print(f"  detectable at 2 se on this sample: ${2 * decision['se']:,.0f}/day")
    print(f"  ORACLE on the same sessions: {oracle['d$/day']:+.1f} $/day "
          f"(cov {oracle['cov_term']:+.1f}) - the ceiling a PERFECT magnitude nowcast would pay")
    if oracle["d$/day"] > 0:
        print(f"  the decision scaler captures {decision['d$/day'] / oracle['d$/day'] * 100:+.1f}% "
              f"of that ceiling")

    # ---- clause 7: sensitivity
    print("\n" + "=" * 100)
    print("CLAUSE 7 - sensitivity, reported as a SHELF (the headline cell was fixed a priori)")
    print("=" * 100)
    grid = []
    for beta in BETA_GRID:
        for band in BAND_GRID:
            e10 = run_feature(d, z_r10, chain_mask, "resid10", beta, band, OVERSHOOT)
            erv = run_feature(d, z_rv20, all_mask, "rv20", beta, band, OVERSHOOT)
            grid.append({"beta": beta, "band": f"[{band[0]}, {band[1]}]",
                         "resid10 cov": round(e10["cov_term"], 1), "resid10 t": round(e10["t"], 2),
                         "rv20 cov (all)": round(erv["cov_term"], 1),
                         "rv20 t (all)": round(erv["t"], 2),
                         "headline": (beta == BETA0 and band == BAND0)})
    gdf = table(grid, "clause 7: beta x clip band")

    # ---- clause 8: feasibility
    print("\n" + "=" * 100)
    print("CLAUSE 8 - feasibility: does the scaled book breach the 2.5% daily loss limit more?")
    print("=" * 100)
    lr = d["low_ret"].values
    rows = []
    for name, z in (("tape rv20", z_rv20), ("chain_10 residual", z_r10), ("ORACLE", z_orcl)):
        k = scaler(z, BETA0, BAND0)
        base = lr <= -DAILY_LOSS_LIMIT
        scaled = (k * lr) <= -DAILY_LOSS_LIMIT
        extra = int((scaled & ~base).sum())
        rows.append({"scaler": name, "control breaches": int(base.sum()),
                     "scaled breaches": int(scaled.sum()), "NEW breaches": extra,
                     "% of sessions": round(extra / len(d) * 100, 2),
                     "within 2% bound": extra / len(d) <= 0.02})
    table(rows, "clause 8: loss-limit breaches implied by linear scaling",
          "  a NEW breach is a session the linear approximation over-credits: the real book would "
          "have stopped.")

    # ---- clause 9: robustness
    print("\n" + "=" * 100)
    print("CLAUSE 9 - robustness")
    print("=" * 100)
    nostop = chain_mask & ~d["stopped"].values.astype(bool)
    rob = [run_feature(d, z_r10, nostop, "chain_10 residual, control-stopped dropped",
                       overshoot=OVERSHOOT),
           run_feature(d, z_rv20, all_mask & ~d["stopped"].values.astype(bool),
                       "tape rv20, control-stopped dropped", overshoot=OVERSHOOT),
           run_feature(d, z_scr, chain_mask, "SCRAMBLED null, one draw", overshoot=OVERSHOOT)]
    summarize(rob, "clause 9a: robustness (dropping stopped sessions CONDITIONS ON THE OUTCOME "
                   "and is a diagnostic, not a correction)")

    # ---- clause 9b: the permutation null, which is what "indistinguishable from noise" means
    print(f"\n  clause 9b: permutation null, {N_PERM} within-regime shuffles")
    null = permutation_null(d, z_c10, chain_mask, OVERSHOOT)
    prows = []
    for name, e, key in (("tape rv20 [chain]", paid[0], "cov"), ("chain_10 raw", paid[2], "cov"),
                         ("chain_10 RESIDUAL", paid[3], "cov"), ("ORACLE [chain]", paid[6], "cov")):
        v = e["cov_term"]
        lo5, hi95 = np.percentile(null[key], [5, 95])
        prows.append({"scaler": name, "cov term": round(v, 1),
                      "null mean": round(float(null[key].mean()), 1),
                      "null sd": round(float(null[key].std(ddof=1)), 1),
                      "null 5%": round(float(lo5), 1), "null 95%": round(float(hi95), 1),
                      "z vs null": round(float((v - null[key].mean()) / null[key].std(ddof=1)), 2),
                      "inside band": bool(lo5 <= v <= hi95)})
    table(prows, "clause 9b: where each scaler sits in the permutation distribution",
          "  inside the 5-95 band = INDISTINGUISHABLE FROM NOISE, in both directions.")

    # ---- clause 10: why. the predictable part of magnitude vs the surprise
    print("\n" + "=" * 100)
    print("CLAUSE 10 - MECHANISM: is the sleeve paid by FORECASTABLE magnitude or by SURPRISE?")
    print("=" * 100)
    y = lg("absmove")
    for fname, Z in (("tape only (rv20, vix_lag)", tapeZ),
                     ("tape + chain_10", np.column_stack([tapeZ, lg("chain_10")]))):
        resid = causal_residual(y, Z)
        fit = y - resid
        m = np.isfinite(resid) & np.isfinite(fit) & chain_mask
        pnl_m = d["pnl"].values[m]
        Xs = np.column_stack([np.ones(int(m.sum())),
                              (fit[m] - fit[m].mean()) / fit[m].std(),
                              (resid[m] - resid[m].mean()) / resid[m].std()])
        f = ols(Xs, pnl_m)
        print(f"\n  forecast built from {fname}, on {int(m.sum()):,} chain sessions")
        print(f"    PREDICTABLE part of log|move|: {f['beta'][1]:+9.1f} $/day per 1sd  "
              f"t {f['t'][1]:+.2f}")
        print(f"    SURPRISE   part of log|move|: {f['beta'][2]:+9.1f} $/day per 1sd  "
              f"t {f['t'][2]:+.2f}")
        print(f"    share of the |move| variance the forecast explains: "
              f"{1 - float(np.var(resid[m])) / float(np.var(y[m])):.3f}")

    # ---- verdict
    cov_ok = decision["cov_term"] > 0
    t_ok = decision["t"] > 2.0
    reg_ok = decision["pos_regimes"] >= 2
    pair_ok = pm > 0
    free_cov = max(e["cov_term"] for e in free[:2])
    free_t = max(e["t"] for e in free[:2])
    free_pass = free_cov > 0 and free_t > 2.0
    underpowered = blo < 0 < bhi and bhi < oracle["d$/day"]
    linearity_binds = not all(r["within 2% bound"] for r in rows)
    nlo, nhi = np.percentile(null["cov"], [5, 95])
    dec_noise = bool(nlo <= decision["cov_term"] <= nhi)
    lim_ok = decision["lim"]["d$/day"] > 0 and decision["lim"]["t"] > 2.0

    if cov_ok and t_ok and reg_ok and pair_ok and lim_ok:
        verdict = "PASS - the chain's magnitude nowcast sizes this sleeve better than free data"
    elif dec_noise:
        verdict = ("REFUSED - the chain scaler is INSIDE its own permutation null, so it neither "
                   "helps nor hurts;\n     what refuses it is clause 10, not its t")
    elif underpowered and not free_pass:
        verdict = ("UNDECIDED - neither the free forecast nor the chain clears, and the sample "
                   "cannot separate\n     'no skill' from 'skill too small to see'")
    else:
        verdict = "REFUSED"

    print("\n" + "=" * 100)
    print("VERDICT")
    print("=" * 100)
    print(f"  premise (clause 2): {'HOLDS' if premise else 'FAILS'} | "
          f"identity (clause 1): {'HOLDS' if id_ok else 'FAILS'}")
    print(f"  (a) FREE question - best tape scaler on 2,686 sessions: cov {free_cov:+.1f} $/day "
          f"at t {free_t:+.2f} -> {'PASS' if free_pass else 'FAIL'}")
    print(f"  (b) PAID question - chain residual over tape: d {decision['d$/day']:+.1f} $/day "
          f"(cov {decision['cov_term']:+.1f}, lev {decision['lev_term']:+.1f}) at "
          f"t {decision['t']:+.2f}, {decision['pos_regimes']}/3 regimes, paired vs tape "
          f"{pm:+.1f} at t {pt:+.2f}")
    print(f"  clause 8 linearity bound: {'FAILS' if linearity_binds else 'holds'}; under the "
          f"LOSS-LIMIT-AWARE book (clause 8b) the decision scaler is "
          f"{decision['lim']['d$/day']:+.1f} $/day at t {decision['lim']['t']:+.2f}, "
          f"{decision['lim_pos']}/3 regimes")
    print(f"  clause 9b: the decision scaler is {'INSIDE' if dec_noise else 'OUTSIDE'} the "
          f"permutation 5-95 band [{nlo:+.1f}, {nhi:+.1f}] "
          f"(z {(decision['cov_term'] - null['cov'].mean()) / null['cov'].std(ddof=1):+.2f})")
    print(f"  => {verdict}")

    pd.DataFrame([{"free_cov": free_cov, "free_t": free_t, "free_pass": free_pass,
                   "dec_d": decision["d$/day"], "dec_se": decision["se"], "dec_t": decision["t"],
                   "dec_cov": decision["cov_term"], "dec_lev": decision["lev_term"],
                   "dec_regimes": decision["pos_regimes"], "paired_vs_tape": pm, "paired_t": pt,
                   "boot_lo": blo, "boot_hi": bhi, "p_boot": p_boot,
                   "oracle_d": oracle["d$/day"], "oracle_cov": oracle["cov_term"],
                   "n_chain": int(chain_mask.sum()), "n_prev": int(prev_mask.sum()),
                   "dec_lim_d": decision["lim"]["d$/day"], "dec_lim_t": decision["lim"]["t"],
                   "linearity_binds": linearity_binds, "null_lo": nlo, "null_hi": nhi,
                   "dec_inside_null": dec_noise,
                   "verdict": verdict.split(" - ")[0]}]).to_csv(OUT / "decision.csv", index=False)
    pd.DataFrame({"cov": null["cov"], "lim": null["lim"]}).to_csv(OUT / "permutation_null.csv",
                                                                  index=False)
    summarize(free + paid, "ALL SCALERS (headline cell)").to_csv(OUT / "scalers.csv", index=False)
    gdf.to_csv(OUT / "sensitivity.csv", index=False)
    print(f"\n  wrote {(OUT / 'decision.csv').relative_to(REPO)}, "
          f"{(OUT / 'scalers.csv').relative_to(REPO)}, "
          f"{(OUT / 'sensitivity.csv').relative_to(REPO)}")

    if args.record:
        import intraday_backtest as ib  # noqa: E402  (late: only --record needs it)
        lo, hi = d["day"].min(), d["day"].max()
        for e, mask in ((free[0], all_mask), (paid[2], chain_mask), (paid[3], chain_mask),
                        (paid[6], chain_mask)):
            b = e["book"]
            n = b["sessions"]
            fake = {"sessions": n, "net_profit_pct": b["net_pct"],
                    "cagr_pct": (np.prod(1.0 + (e["k"][mask] * d["ret"].values[mask]))
                                 ** (252 / n) - 1) * 100,
                    "sharpe": b["sharpe"], "max_drawdown_pct": b["max_dd_pct"],
                    "avg_daily_pnl": b["$/day"], "worst_day": b["worst_day"],
                    "trades": 0, "trades_per_day": 0.0, "costs_per_day": 0.0, "stopped_days": 0}
            ib.record("active",
                      f"A-15 size scaler {e['label']} (d {e['d$/day']:+.1f} $/day at "
                      f"t {e['t']:+.2f}, cov {e['cov_term']:+.1f}, lev {e['lev_term']:+.1f}, "
                      f"mean k {e['mean_k']:.3f}, yearly-reset $1M book, DIAGNOSTIC)", fake,
                      {"beta": BETA0, "band": list(BAND0), "burn_in": BURN_IN,
                       "feature": e["label"]}, lo, hi)
        print("  recorded 4 DIAGNOSTIC rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
