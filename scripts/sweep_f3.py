"""F-3: the F-1 supervised method at a DAILY horizon, on the daily sleeve.

F-1 refused a real forecast on arithmetic, not on significance: a cross-sectional signal
worth 0.797 bps per dollar traded cannot survive a 0.892 bps commission floor when the book
turns 13.8x its equity every day. This item asks the only question that refusal leaves open -
what the same method does where the turnover is a hundredth of that.

    python scripts/sweep_f3.py --build        # data/f3/panel.parquet from the LEAN daily store
    python scripts/sweep_f3.py --train        # selection, walk-forward, book sim, controls
    python scripts/sweep_f3.py --train --record --export   # ... ledger rows + the LEAN score file

Design, pre-registered before any fit was read
----------------------------------------------
- **Bars.** LEAN's own daily store (`scripts/lean_prices.py`, the bytes the engine consumes),
  dividend-adjusted, 1998-2026.
- **Universe.** The ETF sleeve only: `RANK_UNIVERSE` (9) + S-14's `SECTOR_SLEEVE` (8) +
  `MACRO_SLEEVE` (5) = 22 names. The 50 megacaps on disk are excluded **entirely, features
  included**: that list is the 2026 survivor set (S-7), so a feature built from it - breadth,
  a cross-sectional rank, a market proxy - would leak the same information the tradable
  universe was forbidden. SPY doubles as the market reference and is also tradable, exactly
  as in the champion.
- **Decision convention.** Decide on the close of day `t` with bars up to and including `t`;
  fill at the **open of `t+1`**. That is the shipped algorithm's own convention (MarketOnOpen
  on the next bar) and it is why this panel needs opens, which `lean_prices.load_ohlcv` now
  returns.
- **Target.** `log(open[t+1+h] / open[t+1])` minus its cross-sectional mean at the same date,
  in basis points. `h` (5 or 21 sessions) is chosen on the validation window like any other
  hyperparameter. Demeaned because a sleeve that always holds three of nine names earns the
  spread, not the level; the level is what the regime filter already trades.
- **Features.** 41, every one causal by construction (nothing reads a bar after `t`): returns
  at 5/21/63/126/252 sessions and the two skip-5 variants the champion blends, distance from
  the 20/50/200-day averages in ATR units, ATR relative to price, realized vol at 21 and 63
  sessions and their ratio, vol-adjusted momentum, volume against its own trailing 60-session
  median, position in the 252-session range, 63-session drawdown, beta and correlation to SPY
  and the SPY-residual of 21-session momentum; seven SPY features broadcast to every row; the
  cross-sectional percentile rank of ten of those within the day; month and day-of-week.
- **Split.** Selection: train <= 2007, validate 2008-2011, and the pair (model, horizon) with
  the best validation IC wins. Test: **2012-2026, the champion's own backtest window**, with a
  yearly expanding retrain - year Y is predicted by a model trained on <= Y-2 and early-stopped
  on Y-1. Nothing in the LEAN comparison window was seen by selection or by fitting, so the
  full-period LEAN run is comparable to `champion.json` directly rather than on a sub-window.
- **Book (stage 1, in pandas).** Long the top / short the bottom `decile` of the prediction,
  equal-weighted, rebalanced daily, and the decisive column reported as **gross bps per dollar
  turned over against the cost floor** - F-1's lesson, which is that P&L hides the arithmetic.
- **Book (stage 2, in LEAN).** The prediction replaces the champion's momentum score as the
  *ranking* input and nothing else (`S1_ML_SCORES` / `S1_ML_MODE`, both defaulting to off, so
  a run with no environment reproduces the shipped hash). Judged by `scripts/evaluate.py` at
  the same cost model as the champion (S-18's `stats_by_spread` rule), at 0 bp and at 2 bp.
- **Pre-registered pass rule.** The LEAN book must return "BEATS champion" from `evaluate.py`
  at the 2 bp column **and** beat the champion's CAR in the 2020-2026 out-of-sample half.
  Anything less is refused and nothing ships.
- **Controls.** (1) A falsification run on labels shuffled within each date - it must find
  nothing. (2) A ridge baseline on the identical features - F-1's edge lived in the
  interactions, and this is the control that says whether a tree earns its complexity.

Three facts carried forward from F-1, each of which cost an hour there
---------------------------------------------------------------------
- The label must be in basis points: sklearn's early stop compares the raw squared-error loss
  against an absolute `tol` of 1e-7, so in native return units the fit stops at iteration 1.
- Early stopping must use an explicit time-ordered `X_val`/`y_val`; `validation_fraction`
  slices the training set at random and leaks across time.
- Report the ridge baseline next to the tree, always.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "algorithms" / "s1_momo"))
import intraday_common as ic                              # noqa: E402
from lean_prices import load_ohlcv                        # noqa: E402

LEDGER = REPO / "research" / "experiments.jsonl"
OUT = REPO / "data" / "f3"
PANEL = OUT / "panel.parquet"
SCORES = OUT / "ml_scores.csv"

#: The ETF sleeve, copied here rather than imported so the panel does not depend on whichever
#: sleeve preset the algorithm happens to ship (S-14 added the last thirteen).
RANK_UNIVERSE = ["SPY", "QQQ", "IWM", "DIA", "XLK", "XLF", "XLE", "TLT", "GLD"]
SECTOR_SLEEVE = ["XLV", "XLY", "XLP", "XLI", "XLU", "XLB", "XLRE", "XLC"]
MACRO_SLEEVE = ["EFA", "HYG", "IEF", "SLV", "VNQ"]
TRADABLE = RANK_UNIVERSE + SECTOR_SLEEVE + MACRO_SLEEVE
MARKET = "SPY"

MIN_HISTORY = 252        # sessions a name needs before it can appear in a row (the champion's gate)
MIN_NAMES = 6            # dates with fewer priced names are dropped: a rank is meaningless there
HORIZONS = (5, 21)

SELECT_TRAIN_END = 2007
SELECT_VALID = (2008, 2011)
TEST_START = 2012        # the champion's backtest window opens here

EPS = 1e-12

RANKED_FEATURES = ["ret_5", "ret_21", "ret_63", "ret_252", "dist_ma50", "dist_ma200",
                   "vol_21", "vol_ratio", "vol_z", "mom_riskadj"]

FEATURES: list[str] = []          # filled by build_panel / loaded with the panel


# ------------------------------------------------------------------------------ panel


def _log_ret(px: pd.DataFrame, n: int) -> pd.DataFrame:
    return np.log(px / px.shift(n))


def build_panel() -> pd.DataFrame:
    """One row per (date, tradable name) with 41 causal features and both labels."""
    data = load_ohlcv(TRADABLE)
    op, hi, lo, cl, vo = (data["open"], data["high"], data["low"], data["close"], data["volume"])

    # True range needs the previous close, so it is causal at t by construction.
    prev_close = cl.shift(1)
    tr = pd.concat([(hi - lo).stack(), (hi - prev_close).abs().stack(),
                    (lo - prev_close).abs().stack()], axis=1).max(axis=1).unstack()
    tr = tr.reindex_like(cl)
    atr20 = tr.rolling(20, min_periods=15).mean()

    r1 = np.log(cl / cl.shift(1))
    feats: dict[str, pd.DataFrame] = {}

    for n in (5, 21, 63, 126, 252):
        feats[f"ret_{n}"] = _log_ret(cl, n)
    # The champion's own convention: skip the last week on the slow horizons.
    feats["ret_126_skip5"] = np.log(cl.shift(5) / cl.shift(126))
    feats["ret_252_skip5"] = np.log(cl.shift(5) / cl.shift(252))

    for n in (20, 50, 200):
        ma = cl.rolling(n, min_periods=int(n * 0.8)).mean()
        feats[f"dist_ma{n}"] = (cl - ma) / atr20.replace(0.0, np.nan)
    feats["atr_rel"] = atr20 / cl

    feats["vol_21"] = r1.rolling(21, min_periods=15).std() * np.sqrt(252)
    feats["vol_63"] = r1.rolling(63, min_periods=40).std() * np.sqrt(252)
    feats["vol_ratio"] = feats["vol_21"] / feats["vol_63"].replace(0.0, np.nan)
    feats["mom_riskadj"] = feats["ret_21"] / feats["vol_21"].replace(0.0, np.nan)

    vmed = vo.rolling(60, min_periods=30).median()
    feats["vol_z"] = np.log((vo + 1.0) / (vmed + 1.0))
    feats["vol_5_60"] = np.log((vo.rolling(5).mean() + 1.0) / (vmed + 1.0))

    hi252 = cl.rolling(252, min_periods=200).max()
    lo252 = cl.rolling(252, min_periods=200).min()
    feats["range_pos"] = (cl - lo252) / (hi252 - lo252).replace(0.0, np.nan)
    feats["dd_63"] = cl / cl.rolling(63, min_periods=40).max() - 1.0

    # Beta / correlation / residual momentum against SPY.
    m1 = r1[MARKET]
    cov = r1.rolling(63, min_periods=40).cov(m1)
    mvar = m1.rolling(63, min_periods=40).var()
    beta = cov.div(mvar.replace(0.0, np.nan), axis=0)
    feats["beta_63"] = beta
    feats["corr_63"] = r1.rolling(63, min_periods=40).corr(m1)
    feats["resid_21"] = feats["ret_21"].sub(beta.mul(feats["ret_21"][MARKET], axis=0))

    # Market features, identical across names at a date. The model needs them to condition
    # the cross-section on the regime; the demeaned label makes the level itself untradable.
    mkt = {
        "mkt_ret_5": feats["ret_5"][MARKET], "mkt_ret_21": feats["ret_21"][MARKET],
        "mkt_ret_63": feats["ret_63"][MARKET], "mkt_vol_21": feats["vol_21"][MARKET],
        "mkt_vol_ratio": feats["vol_ratio"][MARKET], "mkt_dist_ma200": feats["dist_ma200"][MARKET],
        "mkt_dd_63": feats["dd_63"][MARKET],
    }

    # Labels: fill at the open of t+1, exit at the open of t+1+h. Plus the one-session
    # forward return the daily-rebalanced book in `simulate` actually earns.
    entry = op.shift(-1)
    labels = {h: np.log(op.shift(-(1 + h)) / entry) for h in HORIZONS}
    fwd1 = np.log(op.shift(-2) / entry)

    priced = cl.notna() & (cl.rolling(MIN_HISTORY, min_periods=MIN_HISTORY).count() == MIN_HISTORY)

    long = []
    for name, frame in feats.items():
        long.append(frame.where(priced).stack(future_stack=True).rename(name))
    panel = pd.concat(long, axis=1)
    panel.index.names = ["date", "sym"]
    panel = panel.reset_index()

    for k, series in mkt.items():
        panel[k] = panel["date"].map(series)
    panel["entry_px"] = [entry.at[d, s] for d, s in zip(panel["date"], panel["sym"])]
    panel["fwd1"] = [fwd1.at[d, s] for d, s in zip(panel["date"], panel["sym"])]
    for h in HORIZONS:
        panel[f"y_{h}"] = [labels[h].at[d, s] for d, s in zip(panel["date"], panel["sym"])]

    # Only `entry_px` is required: a row whose label runs off the end of the store still
    # carries a usable feature vector, and dropping it would leave the last `h` sessions of
    # the LEAN comparison window with no score (they would silently fall back to momentum).
    # Training, the IC and the book each filter on what they need.
    panel = panel.dropna(subset=["entry_px"])
    panel = panel[panel[["ret_252", "vol_63", "dist_ma200"]].notna().all(axis=1)]

    # Cross-sectional percentile ranks, computed after the row set is final so a rank is a
    # rank among the names actually tradable that day.
    for f in RANKED_FEATURES:
        panel[f"r_{f}"] = panel.groupby("date")[f].rank(pct=True)
    panel["n_cs"] = panel.groupby("date")["sym"].transform("size")
    panel = panel[panel["n_cs"] >= MIN_NAMES]

    panel["month"] = panel["date"].dt.month.astype(float)
    panel["dow"] = panel["date"].dt.dayofweek.astype(float)
    panel["year"] = panel["date"].dt.year

    # Demean the labels within the date, in basis points (see the module docstring).
    for h in HORIZONS:
        panel[f"y_{h}"] = 1e4 * (panel[f"y_{h}"] - panel.groupby("date")[f"y_{h}"].transform("mean"))

    return panel.sort_values(["date", "sym"]).reset_index(drop=True)


def feature_names(panel: pd.DataFrame) -> list[str]:
    skip = {"date", "sym", "year", "entry_px", "fwd1", "n_cs"} | {f"y_{h}" for h in HORIZONS}
    return [c for c in panel.columns if c not in skip]


# ------------------------------------------------------------------- model + simulation


class _Ridge:
    """Linear baseline on the same features - the control for 'is the tree adding anything'."""

    n_iter_ = 0

    def __init__(self, alpha: float):
        self.alpha = alpha

    def fit(self, X, y, X_val=None, y_val=None):
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import Ridge
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        self.p = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                               Ridge(alpha=self.alpha))
        self.p.fit(X, y)
        return self

    def predict(self, X):
        return self.p.predict(X)


def fit_predict(train: pd.DataFrame, valid: pd.DataFrame, test: pd.DataFrame, params: dict,
                target: str, feats: list[str], seed: int = 0, shuffle_y: bool = False):
    from sklearn.ensemble import HistGradientBoostingRegressor

    # A row whose label runs off the end of the store is a prediction row, never a fit row.
    train = train[train[target].notna()]
    valid = valid[valid[target].notna()]
    ytr = train[target].to_numpy(dtype=float)
    if shuffle_y:
        rng = np.random.default_rng(seed + 991)
        ytr = (train.assign(_y=ytr).groupby("date", sort=False)["_y"]
               .transform(lambda s: rng.permutation(s.to_numpy())).to_numpy())

    p = dict(params)
    if "ridge_alpha" in p:
        model = _Ridge(p["ridge_alpha"])
    else:
        model = HistGradientBoostingRegressor(
            loss="squared_error", random_state=seed, validation_fraction=None,
            early_stopping=p.pop("early_stopping", True),
            n_iter_no_change=p.pop("n_iter_no_change", 20), **p)
    Xtr = train[feats].to_numpy(dtype=np.float32)
    Xva = valid[feats].to_numpy(dtype=np.float32)
    if getattr(model, "early_stopping", True) is False:
        model.fit(Xtr, ytr)
    else:
        model.fit(Xtr, ytr, X_val=Xva, y_val=valid[target].to_numpy(dtype=float))
    return model, model.predict(test[feats].to_numpy(dtype=np.float32))


def tstat(x) -> float:
    x = np.asarray(x, dtype=float)
    if len(x) < 2:
        return float("nan")
    sd = x.std(ddof=1)
    return float(x.mean() / (sd / np.sqrt(len(x)))) if sd > 0 else float("nan")


def ic_stats(df: pd.DataFrame, pred: np.ndarray, target: str) -> tuple[float, float]:
    """Per-date Spearman information coefficient: mean and its t-statistic."""
    d = pd.DataFrame({"date": df["date"].to_numpy(), "y": df[target].to_numpy(), "p": pred})
    d = d.dropna(subset=["y"])
    ics = d.groupby("date").apply(
        lambda g: g["p"].corr(g["y"], method="spearman") if len(g) > 5 else np.nan,
        include_groups=False).dropna().to_numpy()
    return float(np.mean(ics)), tstat(ics)


def simulate(df: pd.DataFrame, pred: np.ndarray, equity: float = 1_000_000.0,
             decile: float = 0.15, gross: float = 1.0, spread_bps: float = 0.0,
             long_only: bool = False) -> pd.DataFrame:
    """Long the top / short the bottom `decile`, equal-weighted, rebalanced every session."""
    d = df[["date", "sym", "entry_px", "fwd1"]].copy()
    d["pred"] = pred
    d = d.dropna(subset=["fwd1"])      # the last two dates have no open[t+2] to exit at
    rows: list[dict] = []
    prev_w: dict[str, float] = {}

    for date, grp in d.groupby("date", sort=True):
        n = len(grp)
        k = max(1, int(round(decile * n)))
        order = grp["pred"].to_numpy().argsort()
        syms = grp["sym"].to_numpy()
        w = np.zeros(n)
        if long_only:
            w[order[-k:]] = gross / k
        else:
            w[order[-k:]] = gross / 2.0 / k
            w[order[:k]] = -gross / 2.0 / k
        new_w = dict(zip(syms, w))

        pnl = float(np.dot(w, np.expm1(grp["fwd1"].to_numpy())) * equity)

        turn = cost = 0.0
        px = dict(zip(syms, grp["entry_px"].to_numpy()))
        for s in set(new_w) | set(prev_w):
            dw = new_w.get(s, 0.0) - prev_w.get(s, 0.0)
            if abs(dw) < 1e-12:
                continue
            notional = abs(dw) * equity
            turn += notional
            p = float(px.get(s, np.nan))
            if not np.isfinite(p) or p <= 0:
                continue
            sh = np.sign(dw) * notional / p
            cost += ic.commission(sh, p, 1.0) + spread_bps * 1e-4 * notional
        rows.append({"date": date, "gross": pnl, "cost": cost, "net": pnl - cost,
                     "turnover": turn, "n": n})
        prev_w = new_w

    out = pd.DataFrame(rows)
    out["net"] = out["gross"] - out["cost"]
    return out


def summarize(sess: pd.DataFrame, label: str) -> dict:
    net = sess["net"].to_numpy()
    turn = float(sess["turnover"].mean())
    gross = float(sess["gross"].mean())
    cost = float(sess["cost"].mean())
    sd = net.std(ddof=1) if len(net) > 1 else float("nan")
    return {"label": label, "sessions": len(sess),
            "net_day": float(net.mean()), "t": tstat(net),
            "gross_day": gross, "cost_day": cost, "turn_day": turn,
            "gross_bps": 1e4 * gross / turn if turn else float("nan"),
            "cost_bps": 1e4 * cost / turn if turn else float("nan"),
            "gross_t": tstat(sess["gross"].to_numpy()),
            "worst": float(net.min()), "win": float((net > 0).mean()),
            "sharpe": float(net.mean() / sd * np.sqrt(252)) if sd else float("nan")}


def print_table(rows: list[dict]) -> None:
    hdr = (f"{'cell':<34} {'days':>5} {'$/day':>9} {'t':>6} {'gross$':>8} {'gr t':>6} "
           f"{'gr bps':>7} {'cost bps':>8} {'turn/day':>11} {'worst':>9} {'win':>6} {'Sharpe':>7}")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['label']:<34} {r['sessions']:>5} {r['net_day']:>9,.0f} {r['t']:>6.2f} "
              f"{r['gross_day']:>8,.0f} {r['gross_t']:>6.2f} {r['gross_bps']:>7.3f} "
              f"{r['cost_bps']:>8.3f} {r['turn_day']:>11,.0f} {r['worst']:>9,.0f} "
              f"{r['win']:>6.1%} {r['sharpe']:>7.2f}")


def record(tag: str, sess: pd.DataFrame, params: dict, extra: dict) -> None:
    net = sess["net"].to_numpy()
    eq = 1_000_000.0
    n = len(sess)
    ret = net / eq
    years = n / 252.0
    car = 100 * ((1 + ret).prod() ** (1 / years) - 1) if years > 0 and (1 + ret).min() > -1 else float("nan")
    curve = np.cumprod(1 + ret)
    dd = 100 * float((1 - curve / np.maximum.accumulate(curve)).max()) if n else 0.0
    sd = ret.std(ddof=1)
    rec = {"ts": dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
           "algorithm": "daily/f3_gbdt", "class": "ml", "tag": tag, "commit": "",
           "run_dir": "", "track": "F-3", "params": params,
           "start": str(pd.Timestamp(sess["date"].min()).date()),
           "end": str(pd.Timestamp(sess["date"].max()).date()),
           "stats": {"Sessions": str(n),
                     "Avg Daily PnL": f"{net.mean():.0f}",
                     "t": f"{tstat(net):.2f}",
                     "Gross Per Day": f"{sess['gross'].mean():.0f}",
                     "Costs Per Day": f"{sess['cost'].mean():.0f}",
                     "Turnover Per Day": f"{sess['turnover'].mean():.0f}",
                     "Gross Bps Per Turnover": f"{1e4 * sess['gross'].mean() / sess['turnover'].mean():.3f}",
                     "Cost Bps Per Turnover": f"{1e4 * sess['cost'].mean() / sess['turnover'].mean():.3f}",
                     "Worst Day": f"{net.min():.0f}",
                     "Win Rate": f"{100 * (net > 0).mean():.0f}%",
                     "Compounding Annual Return": f"{car:.3f}%",
                     "Sharpe Ratio": f"{(ret.mean() / sd * np.sqrt(252)) if sd else float('nan'):.3f}",
                     "Drawdown": f"{dd:.3f}%",
                     **{k: str(v) for k, v in extra.items()}}}
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")


# -------------------------------------------------------------------------------- main


GRID = {
    "small": dict(max_iter=400, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=200,
                  l2_regularization=1.0, max_features=0.7),
    "mid": dict(max_iter=600, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=500,
                l2_regularization=1.0, max_features=0.7),
    "deep": dict(max_iter=600, learning_rate=0.03, max_leaf_nodes=63, min_samples_leaf=1000,
                 l2_regularization=5.0, max_features=0.6),
    "slow": dict(max_iter=3000, learning_rate=0.01, max_leaf_nodes=31, min_samples_leaf=1000,
                 l2_regularization=5.0, max_features=0.7, n_iter_no_change=100),
    "ridge": dict(ridge_alpha=1000.0),
}


def diagnose(decile: float, spread_bps: float, record_rows: bool = False) -> None:
    """Why the LEAN cells lost: score the forecast on the nine names the champion ranks.

    The panel is 22 names wide, but the shipped sleeve ranks `RANK_UNIVERSE` and holds three
    of it. Demeaning is a per-date constant so it cannot change an ordering, but the question
    "does this forecast order *that* sleeve better than the momentum blend does" is the one the
    LEAN runs answer with a number and this answers with a mechanism. The momentum blend is
    rebuilt here exactly as `signals.blended_momentum` computes it (lookbacks 20/60/120/252,
    skip 5 on the two slow horizons), from the same store, so the two scores are comparable.
    """
    panel = pd.read_parquet(PANEL)
    panel["date"] = pd.to_datetime(panel["date"])
    scores = pd.read_csv(SCORES, index_col=0)
    scores.index = pd.to_datetime(scores.index)

    cl = load_ohlcv(RANK_UNIVERSE)["close"]
    horizons = {20: 0, 60: 0, 120: 5, 252: 5}
    blend = sum(np.log(cl.shift(skip) / cl.shift(n)) for n, skip in horizons.items()) / len(horizons)

    d = panel[panel["sym"].isin(RANK_UNIVERSE) & (panel["year"] >= TEST_START)].copy()
    d["ml"] = [scores.at[dt_, s] if (dt_ in scores.index and s in scores.columns) else np.nan
               for dt_, s in zip(d["date"], d["sym"])]
    d["mom"] = [blend.at[dt_, s] if dt_ in blend.index else np.nan
                for dt_, s in zip(d["date"], d["sym"])]
    d = d.dropna(subset=["ml", "mom", "y_5"])
    # Re-demean the label within the nine, which is the cross-section actually being ranked.
    d["y9"] = d["y_5"] - d.groupby("date")["y_5"].transform("mean")

    def ics(col: str, frame: pd.DataFrame) -> tuple[float, float]:
        s = frame.groupby("date").apply(
            lambda g: g[col].corr(g["y9"], method="spearman") if len(g) > 4 else np.nan,
            include_groups=False).dropna()
        return float(s.mean()), tstat(s.to_numpy())

    print(f"\n=== the nine names the champion ranks, {TEST_START}-{panel.year.max()} "
          f"({d['date'].nunique():,} sessions) ===")
    print(f"{'score':<28} {'IC':>9} {'t':>7}")
    for lab, mask in (("pooled", d["date"].notna()),
                      ("IS 2012-2019", d["date"].dt.year <= 2019),
                      ("OOS 2020-2026", d["date"].dt.year >= 2020)):
        for col, name in (("ml", "F-3 GBDT forecast"), ("mom", "champion momentum blend")):
            m, t = ics(col, d[mask])
            print(f"{name + ' [' + lab + ']':<28} {m:>+9.5f} {t:>+7.2f}")
    agree = d.groupby("date").apply(lambda g: g["ml"].corr(g["mom"], method="spearman"),
                                    include_groups=False).mean()
    print(f"\nmean per-date rank correlation between the two scores: {agree:+.3f}")

    # And the top-3-of-9 book each score would hold, unlevered, with no other machinery: no
    # regime filter, no vol target, no margin budget. The difference between these two rows is
    # the ranking and nothing else.
    print()
    books = {name: simulate(d, d[col].to_numpy(), decile=3.0 / 9.0, spread_bps=spread_bps,
                            long_only=True)
             for col, name in (("ml", "GBDT top-3 of 9"), ("mom", "momentum top-3 of 9"))}
    print_table([summarize(b, k) for k, b in books.items()])
    if record_rows:
        for k, b in books.items():
            m, t = ics("ml" if k.startswith("GBDT") else "mom", d)
            record(f"F-3 diagnosis, {k} unlevered on the champion's own sleeve "
                   f"(no regime filter, no vol target, no margin budget)", b,
                   {"universe": 9, "top_n": 3, "spread_bps": spread_bps},
                   {"IC": f"{m:.5f}", "IC t": f"{t:.2f}", "Regime": "2012-2026"})
        print(f"\nrecorded 2 rows in {LEDGER}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--export", action="store_true", help="write data/f3/ml_scores.csv for LEAN")
    ap.add_argument("--decile", type=float, default=0.15)
    ap.add_argument("--spread-bps", type=float, default=2.0)
    ap.add_argument("--importance", action="store_true")
    ap.add_argument("--select-only", action="store_true")
    ap.add_argument("--diagnose", action="store_true",
                    help="score the exported forecast against the champion's own nine names")
    ap.add_argument("--model", choices=sorted(GRID), default=None)
    ap.add_argument("--horizon", type=int, choices=list(HORIZONS), default=None)
    args = ap.parse_args()

    if args.diagnose:
        diagnose(args.decile, args.spread_bps, args.record)
        return

    if args.build or not PANEL.exists():
        OUT.mkdir(parents=True, exist_ok=True)
        print("building panel from the LEAN daily store ...")
        panel = build_panel()
        panel.to_parquet(PANEL, index=False)
        print(f"panel: {len(panel):,} rows -> {PANEL}")
        print(f"  {panel['date'].min().date()} .. {panel['date'].max().date()}  "
              f"{panel['sym'].nunique()} symbols  {panel['date'].nunique():,} sessions")
        print(f"  median names per date: {panel['n_cs'].median():.0f}")
    if not args.train:
        return

    panel = pd.read_parquet(PANEL)
    panel["date"] = pd.to_datetime(panel["date"])
    feats = feature_names(panel)
    print(f"panel {len(panel):,} rows, {panel['sym'].nunique()} symbols, "
          f"{panel['date'].nunique():,} sessions, {panel['year'].min()}-{panel['year'].max()}, "
          f"{len(feats)} features")

    tr = panel[panel.year <= SELECT_TRAIN_END]
    va = panel[(panel.year >= SELECT_VALID[0]) & (panel.year <= SELECT_VALID[1])]
    print(f"selection: train <= {SELECT_TRAIN_END} ({len(tr):,} rows)  "
          f"valid {SELECT_VALID[0]}-{SELECT_VALID[1]} ({len(va):,} rows)")

    # ---- stage 1: (model, horizon) chosen on the validation window only
    print(f"\n=== stage 1: selection on <= {SELECT_TRAIN_END} -> {SELECT_VALID[0]}-{SELECT_VALID[1]} ===")
    cells = ({args.model: GRID[args.model]} if args.model else GRID)
    horizons = [args.horizon] if args.horizon else list(HORIZONS)
    sel = []
    for h in horizons:
        target = f"y_{h}"
        for name, p in cells.items():
            t0 = time.time()
            model, pv = fit_predict(tr, va, va, p, target, feats)
            icm, ict = ic_stats(va, pv, target)
            row = summarize(simulate(va, pv, decile=args.decile, spread_bps=args.spread_bps),
                            f"valid h{h} {name}")
            row["ic"], row["ic_t"], row["iters"] = icm, ict, model.n_iter_
            sel.append((name, h, p, row))
            print(f"  h{h:>2} {name:<6} iters {model.n_iter_:>4}  IC {icm:+.5f} (t {ict:+.2f})  "
                  f"gross {row['gross_bps']:+.3f} bps  net ${row['net_day']:>8,.0f}/day  "
                  f"t {row['t']:+.2f}  ({time.time()-t0:.0f}s)")
    print()
    print_table([r for _, _, _, r in sel])
    best = max(sel, key=lambda x: x[3]["ic"])
    print(f"\nselected on validation IC: {best[0]}, horizon {best[1]}  {best[2]}")
    if args.select_only:
        return

    # ---- stage 2: walk-forward over the champion's window, yearly expanding retrain
    name, horizon, params = best[0], best[1], best[2]
    target = f"y_{horizon}"
    print(f"\n=== stage 2: walk-forward {TEST_START}-{panel.year.max()} (retrain each year) ===")
    preds, frames, models = [], [], {}
    for year in sorted(panel[panel.year >= TEST_START].year.unique()):
        trn = panel[panel.year <= year - 2]
        vld = panel[panel.year == year - 1]
        tst = panel[panel.year == year]
        t0 = time.time()
        model, pt = fit_predict(trn, vld, tst, params, target, feats)
        icm, ict = ic_stats(tst, pt, target)
        row = summarize(simulate(tst, pt, decile=args.decile, spread_bps=args.spread_bps),
                        f"test {year}")
        print(f"  {year}: train<={year-2} ({len(trn):>7,}) valid ({len(vld):>6,}) "
              f"test ({len(tst):>6,}) iters {model.n_iter_:>4}  IC {icm:+.5f} (t {ict:+.2f})  "
              f"gross {row['gross_bps']:+.3f} bps  net ${row['net_day']:>7,.0f}/day  "
              f"({time.time()-t0:.0f}s)")
        preds.append(pt)
        frames.append(tst)
        models[year] = model

    test = pd.concat(frames, ignore_index=True)
    pred = np.concatenate(preds)
    icm, ict = ic_stats(test, pred, target)
    print(f"\npooled out-of-sample IC {icm:+.5f} (t {ict:+.2f}) over {test['date'].nunique():,} sessions")

    rows = []
    books = {
        "ls gross only": simulate(test, pred, decile=args.decile, spread_bps=0.0),
        f"ls +{args.spread_bps:g}bp": simulate(test, pred, decile=args.decile,
                                               spread_bps=args.spread_bps),
        "long-only top": simulate(test, pred, decile=args.decile, spread_bps=args.spread_bps,
                                  long_only=True),
    }
    # `ls gross only` still pays commission; the honest gross line has neither.
    g = books["ls gross only"].copy()
    g["cost"] = 0.0
    books = {"ls NO costs": g, **books}
    for k, v in books.items():
        rows.append(summarize(v, k))

    # halves, on the net book at the shipped spread
    net_book = books[f"ls +{args.spread_bps:g}bp"]
    for lab, mask in (("IS 2012-2019", net_book["date"].dt.year <= 2019),
                      ("OOS 2020-2026", net_book["date"].dt.year >= 2020)):
        rows.append(summarize(net_book[mask], lab))

    # ---- controls
    print("\n=== controls ===")
    sh_preds, sh_frames = [], []
    for year in sorted(panel[panel.year >= TEST_START].year.unique()):
        _, pt = fit_predict(panel[panel.year <= year - 2], panel[panel.year == year - 1],
                            panel[panel.year == year], params, target, feats, shuffle_y=True)
        sh_preds.append(pt)
        sh_frames.append(panel[panel.year == year])
    sh_test, sh_pred = pd.concat(sh_frames, ignore_index=True), np.concatenate(sh_preds)
    sh_ic, sh_ic_t = ic_stats(sh_test, sh_pred, target)
    sh_book = simulate(sh_test, sh_pred, decile=args.decile, spread_bps=args.spread_bps)
    rows.append(summarize(sh_book, "falsification (shuffled)"))
    print(f"  falsification: IC {sh_ic:+.5f} (t {sh_ic_t:+.2f}) against the model's {icm:+.5f}")

    rd_preds, rd_frames = [], []
    for year in sorted(panel[panel.year >= TEST_START].year.unique()):
        _, pt = fit_predict(panel[panel.year <= year - 2], panel[panel.year == year - 1],
                            panel[panel.year == year], GRID["ridge"], target, feats)
        rd_preds.append(pt)
        rd_frames.append(panel[panel.year == year])
    rd_test, rd_pred = pd.concat(rd_frames, ignore_index=True), np.concatenate(rd_preds)
    rd_ic, rd_ic_t = ic_stats(rd_test, rd_pred, target)
    rows.append(summarize(simulate(rd_test, rd_pred, decile=args.decile,
                                   spread_bps=args.spread_bps), "ridge baseline"))
    print(f"  ridge baseline: IC {rd_ic:+.5f} (t {rd_ic_t:+.2f})")

    print()
    print_table(rows)

    # ---- IC by year, the decay F-1 found
    print("\nIC by test year:")
    for year in sorted(test.year.unique()):
        m = test.year == year
        y_ic, y_t = ic_stats(test[m], pred[m.to_numpy()], target)
        print(f"  {year}: IC {y_ic:+.5f} (t {y_t:+.2f})")

    if args.importance:
        from sklearn.inspection import permutation_importance
        last = max(models)
        tst = panel[(panel.year == last) & panel[target].notna()]
        r = permutation_importance(models[last], tst[feats].to_numpy(dtype=np.float32),
                                   tst[target].to_numpy(dtype=float), n_repeats=3,
                                   random_state=0, scoring="neg_mean_squared_error")
        imp = pd.Series(r.importances_mean, index=feats).sort_values(ascending=False)
        print(f"\npermutation importance, model {last} (top 12):")
        print(imp.head(12).to_string())

    if args.export:
        OUT.mkdir(parents=True, exist_ok=True)
        wide = (pd.DataFrame({"date": test["date"].to_numpy(), "sym": test["sym"].to_numpy(),
                              "score": pred})
                .pivot(index="date", columns="sym", values="score").sort_index())
        wide.index = wide.index.strftime("%Y-%m-%d")
        wide.round(6).to_csv(SCORES, index_label="date")
        print(f"\nwrote {SCORES}  {wide.shape[0]:,} dates x {wide.shape[1]} names "
              f"({wide.index[0]} .. {wide.index[-1]})")

    if args.record:
        base = {"features": len(feats), "model": name, "horizon": horizon,
                "decile": args.decile, "spread_bps": args.spread_bps, **params}
        for r, book in [(rows[0], books["ls NO costs"]),
                        (rows[1], books["ls gross only"]),
                        (rows[2], books[f"ls +{args.spread_bps:g}bp"]),
                        (rows[3], books["long-only top"])]:
            record(f"F-3 walk-forward GBDT {TEST_START}-{panel.year.max()}: {r['label']}",
                   book, base, {"IC": f"{icm:.5f}", "IC t": f"{ict:.2f}", "Regime": "2012-2026"})
        record("F-3 falsification control: labels shuffled within each date", sh_book, base,
               {"IC": f"{sh_ic:.5f}", "IC t": f"{sh_ic_t:.2f}", "Regime": "2012-2026"})
        print(f"\nrecorded 5 rows in {LEDGER}")


if __name__ == "__main__":
    main()
