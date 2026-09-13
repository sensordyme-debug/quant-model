"""F-1: a walk-forward supervised forecaster on the ten-year Alpaca minute store.

The backlog's top item, and the one mechanism class this loop has never tried: stop hand-
designing rules and let a gradient-boosted tree read the cross-section.

    python scripts/sweep_f1.py --build            # build data/f1/panel.parquet from the store
    python scripts/sweep_f1.py --train            # walk-forward fit + book simulation
    python scripts/sweep_f1.py --train --record   # ... and append rows to the ledger

Design, all of it pre-registered before any fit was read:

- **Bars.** 1-minute Alpaca SIP bars (`data/minute_alpaca`, 63 symbols, 2016-01-04..2026-09-09)
  resampled to 5 minutes, regular session only. Prices and volumes are split-adjusted, so the
  share-count corrections A-10 built (`intraday_common.share_scale`) are applied to every
  commission.
- **Decision points.** The book rebalances every 30 minutes. A decision is taken on the close of
  the 5-minute bar starting at 09:55, 10:25, ... 14:55 (11 per session), filled at the open of the
  next bar (10:00 ... 15:00) and unwound at the open of the bar 30 minutes later (10:30 ... 15:30).
  That is the deployed sleeve's own convention (`CONTRACT.md`: decide on a completed bar, fill at
  the next open) and it leaves the book flat well before the 15:38 ET flatten.
- **Target.** `log(open[t+7] / open[t+1])` - the return the book can actually capture - minus its
  cross-sectional mean at the same timestamp, because a dollar-neutral book earns the spread and
  not the level. Costs are charged in the simulation, not in the label; a label net of costs would
  only shift every name by the same constant per timestamp and vanishes under the demeaning.
- **Features.** Causal by construction: every one reads bars up to and including the decision bar.
  Per name: returns at 5/15/30/60 minutes, session return, overnight gap, VWAP deviation in ATR
  units and in bps, range/ATR, realized-vol ratio, volume against the trailing 20-session median
  of the *same* time-of-day slot, position in the session range, time-of-day, day-of-week, prior
  day's return. Market (SPY) copies of the return and VWAP features, the residual of each return
  against SPY's, and the cross-sectional percentile rank of nine features across the tradable
  names at that timestamp.
- **Universe.** Every name in the store except the index vehicles the daily champion trades or
  inverts (SPY/QQQ/IWM/TQQQ/UPRO/SQQQ/SPXU); those stay as market features only. 56 tradable
  names, which keeps AGENTS.md's disjointness rule.
- **Split.** Train 2016-2021, validate 2022-2023 (hyperparameters and early stopping), test
  2024-2026 with a yearly expanding-window retrain: year Y is predicted by a model trained on
  2016..Y-2 and early-stopped on Y-1.
- **Book.** Long the top decile, short the bottom decile of the prediction, equal-weighted,
  gross 1.0x of sleeve equity, rebalanced at every decision point, flat overnight. Costs are
  `intraday_common`'s: 1.5 bps of slippage plus IBKR commission plus the sell-side regulatory
  pass-throughs.
- **Pre-registered pass rule** (fixed before the first fit was read, the A-track's rule adapted to
  a three-year test window): net P&L per day positive with t > 2 pooled over 2024-2026 **and**
  positive in at least two of the three test years. Nothing deploys otherwise.
- **Falsification control.** The identical pipeline trained on a target shuffled within each
  timestamp. It must produce nothing; if it does not, the finding is the pipeline and not the
  market.
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
if str(REPO) not in sys.path:          # so `quant_brain` resolves when run as a script
    sys.path.insert(0, str(REPO))
import intraday_common as ic  # noqa: E402
from quant_brain.core import labels as qb_labels  # noqa: E402

LEDGER = REPO / "research" / "experiments.jsonl"
OUT = REPO / "data" / "f1"
PANEL = OUT / "panel.parquet"

MARKET = "SPY"
#: Index vehicles the daily sleeve holds or inverts. Features only, never traded here.
EXCLUDE = {"SPY", "QQQ", "IWM", "TQQQ", "UPRO", "SQQQ", "SPXU"}

BAR = 5                      # minutes per bar
HOLD = 6                     # bars held = 30 minutes
STEP = 6                     # bars between decisions = 30 minutes
FIRST_DECISION = 25          # minutes after 09:30 of the first decision bar's START (09:55)
N_DECISIONS = 11             # 09:55 .. 14:55

SLOT_LOOKBACK = 20           # sessions for the same-slot volume median
EPS = 1e-12

BASE_FEATS = ["r1", "r3", "r6", "r12", "r_sess", "gap", "vwap_atr", "vwap_bps", "rng_atr",
              "rvol_ratio", "vol_rel", "vol_rel6", "pos_range", "atr", "prev_ret", "tod", "dow"]
MKT_FEATS = ["m_r1", "m_r3", "m_r6", "m_r12", "m_r_sess", "m_vwap_atr", "m_rvol_ratio"]
RESID_FEATS = ["x_r1", "x_r3", "x_r6", "x_r12", "x_r_sess"]
RANK_OF = ["r1", "r3", "r6", "r12", "r_sess", "vwap_atr", "vol_rel", "rvol_ratio", "x_r6"]
RANK_FEATS = [f"cs_{c}" for c in RANK_OF]
FEATURES = BASE_FEATS + MKT_FEATS + RESID_FEATS + RANK_FEATS


# --------------------------------------------------------------------------------------- panel


def to_5min(df: pd.DataFrame) -> pd.DataFrame:
    """1-minute bars -> 5-minute bars labelled at their START, regular session only."""
    if df.empty:
        return df
    agg = df.resample(f"{BAR}min", label="left", closed="left").agg(
        o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"), v=("v", "sum"))
    agg = agg.dropna(subset=["c"])
    t = agg.index.time
    return agg[(t >= ic.SESSION_OPEN) & (t < ic.SESSION_CLOSE)]


def slot_volume_median(df: pd.DataFrame) -> pd.Series:
    """Trailing median volume of the same time-of-day slot over the prior SLOT_LOOKBACK sessions.

    Strictly causal: the value for session D is built from sessions before D only (the same
    construction as intraday_common.volume_limits, at 5-minute resolution).
    """
    slot = (df.index.hour - 9) * 60 + df.index.minute - 30
    day = pd.Index(df.index.date, name="day")
    piv = df["v"].groupby([day, slot]).sum().unstack()
    med = piv.shift(1).rolling(SLOT_LOOKBACK, min_periods=5).median()
    flat = med.stack()
    key = pd.MultiIndex.from_arrays([day, slot])
    return pd.Series(flat.reindex(key).to_numpy(), index=df.index, dtype="float64")


def features_one(df5: pd.DataFrame) -> pd.DataFrame:
    """Causal per-bar features for one symbol's 5-minute frame."""
    f = pd.DataFrame(index=df5.index)
    c, h, l, o, v = df5["c"], df5["h"], df5["l"], df5["o"], df5["v"]
    day = pd.Index(df5.index.date)
    g = c.groupby(day)

    logc = np.log(c)
    f["r1"] = logc.diff(1)
    f["r3"] = logc.diff(3)
    f["r6"] = logc.diff(6)
    f["r12"] = logc.diff(12)

    sess_open = o.groupby(day).transform("first")
    f["r_sess"] = np.log(c / sess_open)
    prev_close = g.last().shift(1).reindex(day).to_numpy()
    f["gap"] = np.log(sess_open.to_numpy() / np.maximum(prev_close, EPS))
    prev_prev = g.last().shift(2).reindex(day).to_numpy()
    f["prev_ret"] = np.log(np.maximum(prev_close, EPS) / np.maximum(prev_prev, EPS))

    # ATR-ish: trailing 20-bar mean of (h-l)/c, which never reads its own bar's extremes forward.
    tr = ((h - l) / c).rolling(20, min_periods=5).mean()
    f["atr"] = tr
    f["rng_atr"] = ((h - l) / c) / (tr + EPS)

    # Session VWAP, cumulative within the day (uses this bar, which a live loop also has).
    tp = (h + l + c) / 3.0
    pv = (tp * v).groupby(day).cumsum()
    vv = v.groupby(day).cumsum()
    vwap = pv / (vv + EPS)
    f["vwap_bps"] = 1e4 * (c / (vwap + EPS) - 1.0)
    f["vwap_atr"] = (c / (vwap + EPS) - 1.0) / (tr + EPS)

    rv12 = f["r1"].rolling(12, min_periods=6).std()
    rv78 = f["r1"].rolling(78, min_periods=30).std()
    f["rvol_ratio"] = rv12 / (rv78 + EPS)

    med = slot_volume_median(df5)
    f["vol_rel"] = np.log((v + 1.0) / (med + 1.0))
    v6 = v.rolling(6, min_periods=3).sum()
    m6 = med.rolling(6, min_periods=3).sum()
    f["vol_rel6"] = np.log((v6 + 1.0) / (m6 + 1.0))

    hi = h.groupby(day).cummax()
    lo = l.groupby(day).cummin()
    f["pos_range"] = (c - lo) / (hi - lo + EPS)

    f["tod"] = ((df5.index.hour - 9) * 60 + df5.index.minute - 30) / BAR
    f["dow"] = df5.index.dayofweek
    return f


def decision_mask(idx: pd.DatetimeIndex) -> np.ndarray:
    mod = (idx.hour - 9) * 60 + idx.minute - 30
    return np.isin(mod, [FIRST_DECISION + STEP * BAR * k for k in range(N_DECISIONS)])


#: sidecar written next to the panel recording WHAT built it (F-19)
PANEL_META = OUT / "panel.meta.json"


def panel_fingerprint() -> dict:
    """A hash of every function and constant that decides what a panel row contains.

    Deliberately not a file mtime. An mtime trips on a comment and is then ignored, which is the
    failure mode that produced F-19 in the first place; this hashes the SOURCE of the builder,
    the loader and the label mask, so a cosmetic edit is silent and a real one is not.
    """
    import hashlib
    import inspect
    from quant_brain.core import labels as qb_labels

    srcs = []
    for fn in (build_panel, features_one, to_5min, slot_volume_median, decision_mask,
               ic.load_bars, ic.calendar_trim, qb_labels.forward_span_mask):
        try:
            srcs.append(inspect.getsource(fn))
        except (OSError, TypeError):
            srcs.append(f"<source unavailable: {getattr(fn, '__name__', fn)}>")
    consts = repr([BAR, HOLD, STEP, FIRST_DECISION, N_DECISIONS, SLOT_LOOKBACK, MARKET,
                   sorted(EXCLUDE), BASE_FEATS, MKT_FEATS, RESID_FEATS, RANK_FEATS, RANK_OF])
    store = sorted(ic.DATA_DIR.glob("*.parquet"))
    return {"code": hashlib.sha256(("\n".join(srcs) + consts).encode()).hexdigest()[:16],
            "store_dir": str(ic.DATA_DIR), "store_files": len(store),
            "store_newest": max((q.stat().st_mtime for q in store), default=0.0),
            "stamped": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}


def stamp_panel(path: Path | None = None) -> dict:
    """Record the fingerprint of the code and store that produced the panel at `path`."""
    fp = panel_fingerprint()
    meta = {"panel": (path or PANEL).name, **fp}
    PANEL_META.write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return meta


def check_panel_fresh(loud: bool = True) -> list[str]:
    """Warn if the cached panel was not built by the code and store now on disk (F-19).

    F-19 found `panel.parquet` a day behind this track's own AUD-20 fix and behind D-6's AUD-07
    trim, and F-14, F-15, F-16 and F-17 all ran on it - each one passing a "base reproduces F-8
    to the printed digit" check, because all four were comparing the same stale file with itself.
    A reproduction test against a cache cannot detect a stale cache.

    Deliberately a WARNING and not an exception: several scripts load the panel mid-run and a
    hard failure here would cost more than it saves. Returns the reasons so a caller that wants
    to be strict can be.
    """
    if not PANEL.exists():
        return []
    now = panel_fingerprint()
    if not PANEL_META.exists():
        why = ["no panel.meta.json - this panel predates the F-19 stamp, provenance unknown"]
    else:
        was = json.loads(PANEL_META.read_text(encoding="utf-8"))
        why = []
        if was.get("code") != now["code"]:
            why.append(f"builder/loader source changed ({was.get('code')} -> {now['code']})")
        if was.get("store_dir") != now["store_dir"]:
            why.append(f"store changed ({was.get('store_dir')} -> {now['store_dir']})")
        if now["store_files"] != was.get("store_files"):
            why.append(f"store has {now['store_files']} symbols, panel built on "
                       f"{was.get('store_files')}")
        if now["store_newest"] > was.get("store_newest", 0.0) + 1.0:
            why.append("a store file is newer than the panel")
    if why and loud:
        print(f"WARNING: {PANEL.name} may be stale - " + "; ".join(why)
              + "\n         rebuild with `python scripts/sweep_f1.py --build`. F-19 measured a "
                "$176/day swing in the base book from exactly this.", flush=True)
    return why


def build_panel(symbols: list[str] | None = None, verbose: bool = True) -> pd.DataFrame:
    """Assemble the modelling panel: one row per (timestamp, symbol) decision point."""
    store = sorted(p.stem for p in ic.DATA_DIR.glob("*.parquet"))
    syms = symbols or store
    tradable = [s for s in syms if s not in EXCLUDE]

    mkt5 = to_5min(ic.load_bars(MARKET))
    if mkt5.empty:
        raise SystemExit(f"no {MARKET} bars in {ic.DATA_DIR} - the market features need it")
    mf = features_one(mkt5)
    mkt = mf[["r1", "r3", "r6", "r12", "r_sess", "vwap_atr", "rvol_ratio"]].copy()
    mkt.columns = MKT_FEATS

    rows = []
    for i, s in enumerate(tradable, 1):
        t0 = time.time()
        df5 = to_5min(ic.load_bars(s))
        if len(df5) < 5000:
            if verbose:
                print(f"  [{i:>2}/{len(tradable)}] {s:<6} skipped ({len(df5)} bars)")
            continue
        f = features_one(df5)
        dm = decision_mask(df5.index)

        # tradeable forward return: fill at the next bar's open, unwind HOLD bars later
        nxt_open = df5["o"].shift(-1)
        exit_open = df5["o"].shift(-(1 + HOLD))
        same_day = pd.Index(df5.index.date).to_numpy()
        exit_day = pd.Series(same_day, index=df5.index).shift(-(1 + HOLD)).to_numpy()
        fwd = np.log(exit_open / nxt_open)
        fwd = fwd.where(pd.Series(exit_day == same_day, index=df5.index), np.nan)
        # AUD-20: the day check above is necessary and not sufficient. `.shift` moves ROWS,
        # so a within-day gap makes a window that is labelled a 30-minute return actually
        # span longer, while still passing the same-day test. Measured on the Alpaca store
        # (which AGENTS.md recommends for statistical power): 73 within-day gaps of 10-45
        # minutes, 163 of 190,394 same-day windows mislabelled, the worst spanning 2h10m.
        # Zero on the IBKR store, so this changes no shipped number - it removes the
        # dependence on the store happening to be gapless.
        span_ok = qb_labels.forward_span_mask(df5.index, 1 + HOLD, BAR * (1 + HOLD))
        fwd = fwd.where(span_ok, np.nan)

        sub = f[dm].copy()
        sub["fwd"] = fwd[dm]
        sub["entry_px"] = nxt_open[dm]
        sub["sym"] = s
        sub = sub.dropna(subset=["fwd", "entry_px", "r12", "vol_rel", "rvol_ratio", "atr"])
        rows.append(sub)
        if verbose:
            print(f"  [{i:>2}/{len(tradable)}] {s:<6} {len(sub):>7,} rows  ({time.time()-t0:.1f}s)")

    panel = pd.concat(rows)
    panel = panel.join(mkt, how="left")
    for c in ["r1", "r3", "r6", "r12", "r_sess"]:
        panel[f"x_{c}"] = panel[c] - panel[f"m_{c}"]

    panel = panel.reset_index().rename(columns={"index": "ts", "date": "ts"})
    panel["day"] = panel["ts"].dt.date.astype("string")
    panel["year"] = panel["ts"].dt.year.astype("int16")

    # Cross-sectional percentile ranks within each timestamp, and the demeaned label.
    g = panel.groupby("ts", sort=False)
    for c in RANK_OF:
        panel[f"cs_{c}"] = g[c].rank(pct=True)
    panel["y"] = panel["fwd"] - g["fwd"].transform("mean")
    panel["n_cs"] = g["fwd"].transform("size").astype("int16")

    for c in FEATURES + ["fwd", "y", "entry_px"]:
        panel[c] = panel[c].astype("float32")
    panel = panel[["ts", "day", "year", "sym", "n_cs", "entry_px", "fwd", "y"] + FEATURES]
    panel = panel.replace([np.inf, -np.inf], np.nan)
    return panel.sort_values(["ts", "sym"]).reset_index(drop=True)


# --------------------------------------------------------------------------- model + simulation


class _Ridge:
    """Linear baseline on the same features - the control for 'is the tree adding anything'."""

    n_iter_ = 0

    def __init__(self, alpha: float):
        self.alpha = alpha

    def fit(self, X, y, X_val=None, y_val=None):
        from sklearn.linear_model import Ridge
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        from sklearn.impute import SimpleImputer
        self.p = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                               Ridge(alpha=self.alpha))
        self.p.fit(X, y)
        return self

    def predict(self, X):
        return self.p.predict(X)


def fit_predict(train: pd.DataFrame, valid: pd.DataFrame, test: pd.DataFrame,
                params: dict, seed: int = 0, shuffle_y: bool = False):
    from sklearn.ensemble import HistGradientBoostingRegressor

    # Labels are carried in BASIS POINTS, not in log-return units. sklearn's early stop compares
    # the raw squared-error loss against an absolute `tol` of 1e-7; a 30-minute demeaned return has
    # a variance of ~1e-6, so in native units the tolerance is a tenth of the whole signal and the
    # fit stops at iteration 1 every time. The scaling is a pure change of units and does not touch
    # the ranking the book trades.
    ytr = train["y"].to_numpy() * 1e4
    if shuffle_y:
        rng = np.random.default_rng(seed + 991)
        ytr = (train.assign(_y=ytr).groupby("ts", sort=False)["_y"]
               .transform(lambda s: rng.permutation(s.to_numpy())).to_numpy())

    p = dict(params)
    if "ridge_alpha" in p:
        model = _Ridge(p["ridge_alpha"])
    else:
        model = HistGradientBoostingRegressor(
            loss="squared_error", random_state=seed, validation_fraction=None,
            early_stopping=p.pop("early_stopping", True),
            n_iter_no_change=p.pop("n_iter_no_change", 20), **p)
    Xtr = train[FEATURES].to_numpy(dtype=np.float32)
    Xva = valid[FEATURES].to_numpy(dtype=np.float32)
    # sklearn's own validation_fraction would slice the training set at random, which leaks
    # across time; the explicit (X_val, y_val) keeps the early stop strictly out of sample.
    if getattr(model, "early_stopping", True) is False:
        model.fit(Xtr, ytr)
    else:
        model.fit(Xtr, ytr, X_val=Xva, y_val=valid["y"].to_numpy() * 1e4)
    pred = model.predict(test[FEATURES].to_numpy(dtype=np.float32))
    return model, pred


def simulate(df: pd.DataFrame, pred: np.ndarray, equity: float = 1_000_000.0,
             decile: float = 0.10, gross: float = 1.0, costs: bool = True) -> pd.DataFrame:
    """Long the top decile / short the bottom decile of `pred`, rebalanced every decision point.

    Returns one row per session: gross P&L, costs, net P&L, turnover.
    """
    d = df[["ts", "day", "sym", "entry_px", "fwd"]].copy()
    d["pred"] = pred
    out_rows = []
    prev_w: dict[str, float] = {}
    prev_day = None

    for ts, grp in d.groupby("ts", sort=True):
        day = grp["day"].iloc[0]
        if day != prev_day:
            if prev_day is not None and prev_w:
                # overnight flatten is priced at the last rebalance's exit, i.e. one more turn
                pass
            prev_w = {}
            prev_day = day
        n = len(grp)
        k = max(1, int(round(decile * n)))
        order = grp["pred"].to_numpy().argsort()
        syms = grp["sym"].to_numpy()
        w = np.zeros(n)
        w[order[-k:]] = gross / 2.0 / k
        w[order[:k]] = -gross / 2.0 / k
        new_w = dict(zip(syms, w))

        pnl = float(np.dot(w, np.expm1(grp["fwd"].to_numpy())) * equity)

        turn = 0.0
        cost = 0.0
        px = dict(zip(syms, grp["entry_px"].to_numpy()))
        for s in set(new_w) | set(prev_w):
            dw = new_w.get(s, 0.0) - prev_w.get(s, 0.0)
            if abs(dw) < 1e-12:
                continue
            notional = abs(dw) * equity
            turn += notional
            if costs:
                p = float(px.get(s, np.nan))
                if not np.isfinite(p) or p <= 0:
                    continue
                sh = np.sign(dw) * notional / p
                cost += (ic.commission(sh, p, ic.share_scale(s, day))
                         + ic.slippage(sh, p))
        out_rows.append({"ts": ts, "day": day, "gross": pnl, "cost": cost,
                         "net": pnl - cost, "turnover": turn, "n": n})
        prev_w = new_w

    # the last book of each session must be unwound into the flatten
    per = pd.DataFrame(out_rows)
    tail = []
    for day, grp in d.groupby("day", sort=True):
        last_ts = grp["ts"].max()
        g = grp[grp["ts"] == last_ts]
        n = len(g)
        k = max(1, int(round(decile * n)))
        order = g["pred"].to_numpy().argsort()
        w = np.zeros(n)
        w[order[-k:]] = gross / 2.0 / k
        w[order[:k]] = -gross / 2.0 / k
        c = 0.0
        if costs:
            for wi, s, p in zip(w, g["sym"].to_numpy(), g["entry_px"].to_numpy()):
                if abs(wi) < 1e-12 or not np.isfinite(p) or p <= 0:
                    continue
                notional = abs(wi) * equity
                sh = -np.sign(wi) * notional / p
                c += ic.commission(sh, float(p), ic.share_scale(s, day)) + ic.slippage(sh, float(p))
        tail.append({"day": day, "flatten_cost": c, "flatten_turn": float(np.abs(w).sum() * equity)})
    tl = pd.DataFrame(tail).set_index("day")

    sess = per.groupby("day").agg(gross=("gross", "sum"), cost=("cost", "sum"),
                                  turnover=("turnover", "sum"), rebals=("net", "size"))
    sess = sess.join(tl)
    sess["cost"] = sess["cost"] + sess["flatten_cost"]
    sess["turnover"] = sess["turnover"] + sess["flatten_turn"]
    sess["net"] = sess["gross"] - sess["cost"]
    return sess.reset_index()


def tstat(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 2:
        return float("nan")
    sd = x.std(ddof=1)
    return float(x.mean() / (sd / np.sqrt(n))) if sd > 0 else float("nan")


def ic_stats(df: pd.DataFrame, pred: np.ndarray) -> tuple[float, float]:
    """Per-timestamp Spearman information coefficient: mean and its t-statistic."""
    d = pd.DataFrame({"ts": df["ts"].to_numpy(), "y": df["y"].to_numpy(), "p": pred})
    ics = d.groupby("ts").apply(
        lambda g: g["p"].corr(g["y"], method="spearman") if len(g) > 5 else np.nan,
        include_groups=False).dropna().to_numpy()
    return float(np.mean(ics)), tstat(ics)


# ------------------------------------------------------------------------------------- reports


def summarize(sess: pd.DataFrame, label: str) -> dict:
    n = len(sess)
    net = sess["net"].to_numpy()
    turn = float(sess["turnover"].mean())
    gross = float(sess["gross"].mean())
    # The decisive statistic for a book that turns 12x its equity a day: what the signal earns per
    # dollar traded, against what a dollar traded costs (1.5 bps of slippage + commission ~= 1.8).
    return {"label": label, "sessions": n,
            "net_day": float(net.mean()), "t": tstat(net),
            "gross_day": gross, "cost_day": float(sess["cost"].mean()), "turn_day": turn,
            "gross_bps": 1e4 * gross / turn if turn else float("nan"),
            "cost_bps": 1e4 * float(sess["cost"].mean()) / turn if turn else float("nan"),
            "gross_t": tstat(sess["gross"].to_numpy()),
            "worst": float(net.min()), "win": float((net > 0).mean()),
            "sharpe": float(net.mean() / net.std(ddof=1) * np.sqrt(252)) if net.std(ddof=1) else float("nan")}


def print_table(rows: list[dict]) -> None:
    hdr = (f"{'cell':<40} {'sess':>5} {'$/day':>9} {'t':>6} {'gross$':>8} {'gr t':>6} "
           f"{'gr bps':>7} {'cost bps':>8} {'turn/day':>11} {'worst':>9} {'win':>6}")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['label']:<40} {r['sessions']:>5} {r['net_day']:>9,.0f} {r['t']:>6.2f} "
              f"{r['gross_day']:>8,.0f} {r['gross_t']:>6.2f} {r['gross_bps']:>7.3f} "
              f"{r['cost_bps']:>8.3f} {r['turn_day']:>11,.0f} "
              f"{r['worst']:>9,.0f} {r['win']:>6.1%}")


def record(name: str, tag: str, sess: pd.DataFrame, params: dict, extra: dict) -> None:
    net = sess["net"].to_numpy()
    eq = 1_000_000.0
    n = len(sess)
    ret = net / eq
    years = n / 252.0
    car = 100 * ((1 + ret).prod() ** (1 / years) - 1) if years > 0 and (1 + ret).min() > 0 else float("nan")
    curve = np.cumprod(1 + ret)
    dd = 100 * float((1 - curve / np.maximum.accumulate(curve)).max()) if n else 0.0
    sd = ret.std(ddof=1)
    rec = {"ts": dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
           "algorithm": f"intraday/{name}", "class": "ml", "tag": tag, "commit": "",
           "run_dir": "", "track": "F-1", "params": params,
           "start": str(sess["day"].min()), "end": str(sess["day"].max()),
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


# ---------------------------------------------------------------------------------------- main


GRID = {
    "small": dict(max_iter=400, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=500,
                  l2_regularization=1.0, max_features=0.7),
    "mid": dict(max_iter=600, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=1000,
                l2_regularization=1.0, max_features=0.7),
    "deep": dict(max_iter=600, learning_rate=0.03, max_leaf_nodes=63, min_samples_leaf=2000,
                 l2_regularization=5.0, max_features=0.6),
    # Patient cell: the three above all early-stop within ~30 trees, so the question "would more
    # capacity find more" is answered rather than assumed.
    "slow": dict(max_iter=3000, learning_rate=0.01, max_leaf_nodes=31, min_samples_leaf=2000,
                 l2_regularization=5.0, max_features=0.7, n_iter_no_change=100),
    # No early stop at all: a fixed budget, so the validation IC is read against pure capacity.
    "fixed": dict(max_iter=300, learning_rate=0.02, max_leaf_nodes=31, min_samples_leaf=2000,
                  l2_regularization=5.0, max_features=0.7, early_stopping=False),
    "ridge": dict(ridge_alpha=1000.0),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--decile", type=float, default=0.10)
    ap.add_argument("--importance", action="store_true")
    ap.add_argument("--select-only", action="store_true",
                    help="run stage 1 (model selection on the validation window) and stop")
    ap.add_argument("--model", choices=sorted(GRID), default=None,
                    help="skip stage 1 and use this grid cell (must be stage 1's own choice)")
    args = ap.parse_args()

    if args.build or not PANEL.exists():
        OUT.mkdir(parents=True, exist_ok=True)
        print(f"building panel from {ic.DATA_DIR} ...")
        panel = build_panel(args.symbols)
        panel.to_parquet(PANEL, index=False)
        stamp_panel()
        print(f"\npanel: {len(panel):,} rows x {len(FEATURES)} features -> {PANEL}")
        print(f"  {panel['ts'].min()} .. {panel['ts'].max()}  "
              f"{panel['sym'].nunique()} symbols  {panel['day'].nunique():,} sessions")
        print(f"  median names per timestamp: {panel['n_cs'].median():.0f}")
    if not args.train:
        return

    check_panel_fresh()
    panel = pd.read_parquet(PANEL)
    panel["ts"] = pd.to_datetime(panel["ts"])
    print(f"panel {len(panel):,} rows, {panel['sym'].nunique()} symbols, "
          f"{panel['day'].nunique():,} sessions, {panel['year'].min()}-{panel['year'].max()}")

    tr = panel[panel.year <= 2021]
    va = panel[(panel.year >= 2022) & (panel.year <= 2023)]
    print(f"train {len(tr):,} rows  valid {len(va):,} rows")

    # ---- stage 1: hyperparameters, chosen on the validation window only
    print("\n=== stage 1: model selection on 2016-2021 -> 2022-2023 ===")
    sel = []
    for name, p in ({args.model: GRID[args.model]} if args.model else GRID).items():
        t0 = time.time()
        model, pv = fit_predict(tr, va, va, p)
        icm, ict = ic_stats(va, pv)
        s = simulate(va, pv, decile=args.decile)
        row = summarize(s, f"valid {name}")
        row["ic"], row["ic_t"], row["iters"] = icm, ict, model.n_iter_
        sel.append((name, p, row, s))
        print(f"  {name:<6} iters {model.n_iter_:>4}  IC {icm:+.5f} (t {ict:+.2f})  "
              f"net ${row['net_day']:>8,.0f}/day  t {row['t']:+.2f}  ({time.time()-t0:.0f}s)")
    print()
    print_table([r for _, _, r, _ in sel])
    best = max(sel, key=lambda x: x[2]["ic"])
    print(f"\nselected on validation IC: {best[0]}  {best[1]}")
    if args.select_only:
        return

    # ---- stage 2: walk-forward test, yearly expanding-window retrain
    print("\n=== stage 2: walk-forward test 2024-2026 (retrain each year) ===")
    params = best[1]
    preds, frames, models = [], [], {}
    for year in sorted(panel[panel.year >= 2024].year.unique()):
        trn = panel[panel.year <= year - 2]
        vld = panel[panel.year == year - 1]
        tst = panel[panel.year == year]
        t0 = time.time()
        model, pt = fit_predict(trn, vld, tst, params)
        icm, ict = ic_stats(tst, pt)
        s = summarize(simulate(tst, pt, decile=args.decile), f"test {year}")
        s["ic"], s["ic_t"] = icm, ict
        models[year] = (model, vld)
        print(f"  {year}: train<= {year-2} ({len(trn):,}) valid {year-1} ({len(vld):,}) "
              f"test ({len(tst):,}) iters {model.n_iter_:>4}  IC {icm:+.5f} (t {ict:+.2f})  "
              f"net ${s['net_day']:>8,.0f}/day  t {s['t']:+.2f}  ({time.time()-t0:.0f}s)")
        preds.append(pt)
        frames.append(tst)

    test = pd.concat(frames)
    pred = np.concatenate(preds)
    sess_test = simulate(test, pred, decile=args.decile)
    pooled = summarize(sess_test, "TEST pooled 2024-2026")
    icm, ict = ic_stats(test, pred)
    pooled["ic"], pooled["ic_t"] = icm, ict

    per_year = []
    for year in sorted(test.year.unique()):
        m = test.year == year
        row = summarize(simulate(test[m], pred[m.to_numpy()], decile=args.decile), f"test {year}")
        row["ic"], row["ic_t"] = ic_stats(test[m], pred[m.to_numpy()])
        per_year.append(row)

    print()
    print_table(per_year + [pooled])
    print(f"\npooled out-of-sample IC {icm:+.5f} (t {ict:+.2f})")

    # gross-only view: is there any edge at all before costs?
    gross_only = summarize(simulate(test, pred, decile=args.decile, costs=False), "TEST gross only")

    # ---- stage 2b: concentration steelman. If the edge is real it should be strongest in the
    # narrowest slice of the cross-section, and the gross bps per dollar turned over is the
    # cost-free statistic that decides whether ANY execution could pay for it.
    print("\n=== stage 2b: concentration (gross bps per dollar turned over is the decisive column) ===")
    conc = []
    for dec in (0.04, 0.10, 0.20, 0.34):
        conc.append(summarize(simulate(test, pred, decile=dec), f"test 24-26 decile {dec:.2f}"))
    print_table(conc)

    # ---- stage 3: the falsification control
    print("\n=== stage 3: falsification control (labels shuffled within each timestamp) ===")
    cpreds, cframes = [], []
    for year in sorted(panel[panel.year >= 2024].year.unique()):
        trn = panel[panel.year <= year - 2]
        vld = panel[panel.year == year - 1]
        tst = panel[panel.year == year]
        _, pc = fit_predict(trn, vld, tst, params, shuffle_y=True)
        cpreds.append(pc)
        cframes.append(tst)
    ctest, cpred = pd.concat(cframes), np.concatenate(cpreds)
    csess = simulate(ctest, cpred, decile=args.decile)
    ctrl = summarize(csess, "CONTROL shuffled labels")
    cicm, cict = ic_stats(ctest, cpred)
    ctrl["ic"], ctrl["ic_t"] = cicm, cict
    print_table([ctrl, gross_only])
    print(f"control out-of-sample IC {cicm:+.5f} (t {cict:+.2f})")

    # ---- verdict against the pre-registered rule
    years_pos = sum(1 for r in per_year if r["net_day"] > 0)
    passed = pooled["net_day"] > 0 and pooled["t"] > 2 and years_pos >= 2
    print(f"\nPRE-REGISTERED RULE: net>0 and t>2 pooled, and positive in >=2 of 3 test years")
    print(f"  pooled ${pooled['net_day']:,.0f}/day at t {pooled['t']:+.2f}; "
          f"positive years {years_pos}/3  ->  {'PASS' if passed else 'REFUSED'}")

    # A-5's question, asked of this book: how cheap would execution have to be? The slippage
    # constant is the only negotiable part of the cost; commission and the regulatory fees are not.
    print("\nbreakeven slippage (the cost constant that would make each cell net zero; "
          f"the harness charges {ic.SLIPPAGE_BPS} bps):")
    for r in conc + [pooled]:
        fixed = r["cost_bps"] - ic.SLIPPAGE_BPS          # commission + SEC/TAF, not negotiable
        print(f"  {r['label']:<40} gross {r['gross_bps']:>6.3f} bps  "
              f"commission {fixed:>5.3f} bps  ->  breakeven slippage "
              f"{r['gross_bps'] - fixed:>+6.3f} bps")

    if args.importance:
        print("\n=== feature importance (permutation on each retrain's validation year) ===")
        from sklearn.inspection import permutation_importance
        imps = {}
        for year, (model, vld) in models.items():
            sub = vld.sample(min(120_000, len(vld)), random_state=0)
            r = permutation_importance(model, sub[FEATURES].to_numpy(dtype=np.float32),
                                       sub["y"].to_numpy(), n_repeats=3, random_state=0,
                                       scoring="neg_mean_squared_error", n_jobs=1)
            imps[year] = pd.Series(r.importances_mean, index=FEATURES)
        imp = pd.DataFrame(imps)
        imp["rank_mean"] = imp.rank(ascending=False).mean(axis=1)
        imp = imp.sort_values("rank_mean")
        print(imp.head(15).to_string(float_format=lambda x: f"{x: .3e}"))
        print(f"\nrank correlation between retrains: "
              f"{imp[list(models)].rank().corr(method='spearman').to_string()}")

    if args.record:
        base = {"features": len(FEATURES), "decile": args.decile, "hold_min": HOLD * BAR,
                "rebalance_min": STEP * BAR, "model": best[0], **params}
        for r, year in zip(per_year, sorted(test.year.unique())):
            m = test.year == year
            record("f1_gbdt", f"F-1 walk-forward GBDT, test year {year} (train<={year-2}, valid {year-1})",
                   simulate(test[m], pred[m.to_numpy()], decile=args.decile), base,
                   {"IC": f"{r['ic']:.5f}", "IC t": f"{r['ic_t']:.2f}", "Regime": str(year)})
        record("f1_gbdt", "F-1 walk-forward GBDT, pooled out-of-sample 2024-2026 (the verdict row)",
               sess_test, base, {"IC": f"{icm:.5f}", "IC t": f"{ict:.2f}",
                                 "Regime": "2024-2026", "Verdict": "PASS" if passed else "REFUSED"})
        record("f1_gbdt", "F-1 falsification control: identical pipeline, labels shuffled within each timestamp",
               csess, base, {"IC": f"{cicm:.5f}", "IC t": f"{cict:.2f}", "Regime": "2024-2026"})
        record("f1_gbdt", "F-1 walk-forward GBDT, pooled out-of-sample 2024-2026 GROSS ONLY (no costs)",
               simulate(test, pred, decile=args.decile, costs=False), base,
               {"IC": f"{icm:.5f}", "Regime": "2024-2026"})
        b_row = best[2]
        record("f1_gbdt", f"F-1 validation window 2022-2023, selected model '{best[0]}' (in-sample for selection)",
               best[3], base, {"IC": f"{b_row['ic']:.5f}", "Regime": "2022-2023"})
        print(f"\nrecorded {5} rows in {LEDGER}")


if __name__ == "__main__":
    main()
