"""F-14: every F run so far read the same 38 features. Price the FEATURE SET axis.

F-12 closed with a sentence that names its own binding constraint: *"the honest reading is that
**this feature set** on this panel does not support a t = 2 book by any construction available in
this scope."* Six axes are now priced on this panel - construction (F-7), label horizon (F-8),
breadth (F-10), cost-aware selection (F-11), sizing and label family (F-12), frequency (F-1's own
11-slot grid) - and all six were run on **one** feature matrix, `sweep_f1.FEATURES`, unchanged
since F-1. That matrix is 38 columns and every one of them is a deterministic transform of
**5-minute OHLCV**: returns at four lookbacks, session return, gap, VWAP deviation, range/ATR,
realised-vol ratio, relative volume, position in range, time of day, their SPY copies, their SPY
residuals and their cross-sectional ranks.

**What it does not contain is direction of flow.** A 5-minute bar's OHLCV cannot tell you whether
the 5 minutes were bought or sold: `r6` says where the price ended, `vol_rel` says how much traded,
and neither says which side lifted. The 1-minute bars underneath the panel can, approximately, and
they are already on disk - the panel throws them away at `to_5min()`. The tick rule applied at
1-minute resolution (sign of each minute's return times its volume) and the close-location value
((c-l)-(h-c))/(h-l) are the two standard bar-level order-flow proxies, and **neither is recoverable
from the 5-minute frame the panel keeps**. They are a genuinely new information channel on the same
store, not another transform of the old one.

So F-14 asks the one question the F track has never asked: **is the IC ceiling this panel keeps
hitting (+0.011 signed at 30 minutes, +0.021 to the flatten) a property of the market, or of the
features?** Three arms, identical in every other respect - the same walk-forward, the same learner,
the same seed, the same label, the same book:

    base   38 features   = F-8's `close` model exactly, re-fitted; the identity cell
    flow   20 features   = the new family alone; does it carry anything on its own?
    both   58 features   = the question

    python scripts/ml_f14.py --flow          # 1-minute flow features -> data/f1/f14_flow.parquet
    python scripts/ml_f14.py --fit           # walk-forward, 3 arms -> data/f1/f14_preds.parquet
    python scripts/ml_f14.py --books         # IC, books, paired tests, regimes, the decision
    python scripts/ml_f14.py --books --record   # ... and append DIAGNOSTIC rows to the ledger
    python scripts/ml_f14.py --control       # clause 6: the scrambled-flow refit
    python scripts/ml_f14.py --importance    # clause 4(e): how much of the tree is the new family

**Run it with `INTRADAY_DATA_DIR=data/minute_alpaca`** (F-7's documented cost hazard: `_splits.json`
lives only in that store and without it the per-share commission on the reverse-split leveraged
names is charged on share counts four orders of magnitude too small). Run it as `py -3.14` - only
3.14 has `pyarrow` on this machine. **No shipped or runner-loaded file is touched**, so no deploy
gate and no `--replay` is owed.

--------------------------------------------------------------------------------------------
PRE-REGISTERED - written in full before any F-14 number was read
--------------------------------------------------------------------------------------------

**Clause 0 - the prior, stated out loud.** Bar-level flow proxies are a weak version of the real
object (they need the trade tape and this store has only OHLCV), and this panel's forecast has
never moved outside IC +0.011..+0.021 under any change. The honest prior is: `flow` alone scores a
rank IC of **+0.003 to +0.008** - real, because relative volume already works on this panel and the
signed version should be no worse - `both` scores **+0.022 to +0.025** against base's +0.021, the
session book's t moves from **+1.474 to roughly +1.6**, and it is **refused on clause 5** like
F-8, F-10, F-11 and F-12 before it. The one result that would be a surprise rather than a
confirmation is `flow` alone clearing +0.015, which would say the family is orthogonal rather than
a noisy copy of what is already there.

**Clause 1 - the identity cell, and it has to be exact.** The `base` arm re-fits F-8's `close`
model. Same panel rows, same label, same `GRID["mid"]`, same seed 0, same expanding split, same
8 test years - so its predictions must match `data/f1/f8_preds.parquet` to floating point, and its
session book must read **gross 4.256 bps, cost 2.724 bps, net $305.7/day, t +1.474 on 1,933
sessions**. This is why the flow features are **merged, never inner-joined**: a row with no flow
coverage keeps its 38 columns and carries NaN in the new 20 (`HistGradientBoostingRegressor`
handles NaN natively), so the row set is F-8's exactly and the three arms are read at constant
sample. If clause 1 does not print an exact match, nothing else in this file is readable.

**Clause 2 - the features, and what each one is for.** Twenty columns, all built from 1-minute
bars, all strictly causal: the window for a decision at 5-minute bar `T` (start 09:55 + 30k) ends
at the **1-minute bar starting T+4**, i.e. the last minute of the decision bar, which is exactly
the information a live loop has when it decides. Nothing reads the fill bar at T+5.

  direction of flow (the point of the file)
    `ofi5`, `ofi30`, `ofi_sess`   tick-rule signed volume share, sum(sign(r_1m) * v) / sum(v),
                                  over the last 5 / 30 minutes and the session to date. Zero-return
                                  minutes inherit the last non-zero sign within the session.
    `updn30`                      share of up-minutes in the last 30, unweighted by volume: the
                                  sign-only control that separates persistence from size.
    `clv5`, `clv30`, `clv_sess`   volume-weighted close-location value, sum(v*((c-l)-(h-c))/(h-l))
                                  / sum(v) - Chaikin money flow. Where a minute has h == l the bar
                                  contributes 0, not a divide by zero.
  path shape (what 5-minute bars average away)
    `eff5`, `eff30`               |sum r_1m| / sum|r_1m|: how much of the move was direction and
                                  how much was churn. `rng_atr` measures the range; this measures
                                  whether the range went anywhere.
    `amihud30`                    log1p(1e9 * sum|r_1m| / sum(dollar volume)) - price impact per
                                  dollar, the one liquidity feature the panel has never had.
    `dvol30`                      log dollar volume over the last 30 minutes, the denominator in
                                  levels (`vol_rel` is in shares against its own slot median).
  market and cross-section, the same three transforms every F feature already gets
    `m_ofi30`, `m_clv30`, `m_eff30`          SPY copies.
    `x_ofi30`, `x_clv30`                     residual against SPY.
    `cs_ofi30`, `cs_clv30`, `cs_eff30`, `cs_ofi_sess`   cross-sectional percentile ranks.

  Rolling windows never cross a session boundary: sums are cumulative **within the day** and the
  30-minute window at slot 0 is exactly the 09:30-09:59 minutes, so no feature at any slot reads
  the prior session's tape.

**Clause 3 - the arms, and the one thing that does not move.** Label `y_close` (F-8's own choice
and the label the deployed convention implies), learner `sweep_f1.GRID["mid"]` (F-1's stage-1
selection), `random_state=0`, expanding walk-forward with year Y trained on <= Y-2 and early-stopped
on Y-1, test years 2019-2026. **No hyperparameter search.** Changing the feature set and the
learner at once would make the comparison unreadable, and F-1's stage 1 already reported that the
four grid cells early-stop within ~30 trees of each other. If the flow family needs a bigger tree
to pay, that is a finding for a successor and not a knob to turn here.

**Clause 4 - the read-outs, in this order, so the answer cannot be assembled after the fact.**
  (a) per-timestamp rank IC on `y_close` by test year, per arm, with its t;
  (b) F-8's `session` book (slot 0, decile 0.10, held to the 15:30 flatten) per arm: gross bps,
      cost bps, turnover, net $/day, t, worst day, years positive;
  (c) **paired per session**, `both` minus `base`, decomposed into gross and cost - F-11's standing
      rule, that two t's printed side by side is not a comparison;
  (d) the regime split the job brief asks for: terciles of the market's own trailing realised vol;
  (e) permutation importance on each retrain's validation year: what share of the total the flow
      family carries, and whether its ranking is stable across the 8 retrains (F-12's second
      criterion, where the return model scored +0.434 and the risk model +0.772).

**Clause 5 - the pass rule, fixed before the first fit.** The `both` book passes only if **all
three** hold: net t > **2.0** pooled over the 8 test years; net positive in >= **5 of 8** years;
and the paired `both - base` net difference positive at **t > 2**. Anything less is a **refusal** -
"better but underpowered" is what F-8's clause 0 already ruled is not a follow-up. A refusal here
deploys nothing and promotes nothing.

**Clause 6 - the control, and it is at the feature level because the claim is about features.**
F-12's standing rule (b) is that any new signal must be run against a **scrambled version of
itself**, not only against a null book. So the `both` arm is re-fitted with every flow column
permuted **within its timestamp** - which preserves each feature's marginal distribution, its
cross-sectional dispersion and its correlation with the other flow columns, and destroys only the
name it is attached to. If `both_scrambled` keeps the gain, the gain is the extra columns and not
the flow in them, and the finding is the pipeline.

**Clause 7 - what a refusal would close.** Turnover is ~constant across arms (one decision, decile
0.10, in and out) but cost is not, because the arms choose different names and IBKR charges per
share; the comparison is therefore on **net**, per F-11. And if the flow family adds nothing, then
the one channel in this store that is *not* a transform of 5-minute OHLCV returns has been tried,
and F-12's sentence upgrades from "this feature set does not support a t = 2 book" to "**this
panel** does not" - which is a stronger and more useful closing statement than another axis.
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
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
import intraday_common as ic  # noqa: E402
import sweep_f1 as f1  # noqa: E402
import ml_f8 as f8  # noqa: E402

LEDGER = REPO / "research" / "experiments.jsonl"
OUT = REPO / "data" / "f1"
FLOW = OUT / "f14_flow.parquet"
PREDS = OUT / "f14_preds.parquet"
CELLS = OUT / "f14_arms.csv"
IMP = OUT / "importance_f14.csv"

LABEL = "close"
EQUITY = f8.EQUITY
N_SLOTS = f8.N_SLOTS
DECILE = f8.DECILE
EPS = 1e-12

#: clause 2. Own-name flow and path features, built from 1-minute bars.
OWN_FLOW = ["ofi5", "ofi30", "ofi_sess", "updn30", "clv5", "clv30", "clv_sess",
            "eff5", "eff30", "amihud30", "dvol30"]
MKT_FLOW = ["m_ofi30", "m_clv30", "m_eff30"]
RESID_FLOW = ["x_ofi30", "x_clv30"]
RANK_FLOW_OF = ["ofi30", "clv30", "eff30", "ofi_sess"]
RANK_FLOW = [f"cs_{c}" for c in RANK_FLOW_OF]
FLOW_FEATS = OWN_FLOW + MKT_FLOW + RESID_FLOW + RANK_FLOW

ARMS = {"base": None, "flow": None, "both": None}      # feature lists filled in at import time
ARMS["base"] = list(f1.FEATURES)
ARMS["flow"] = list(FLOW_FEATS)
ARMS["both"] = list(f1.FEATURES) + list(FLOW_FEATS)


# ------------------------------------------------------------------- clause 2: the flow features


def _roll_within_day(x: pd.Series, day: np.ndarray, w: int) -> np.ndarray:
    """Trailing sum of `x` over the last `w` bars, never crossing a session boundary.

    Cumulative within the day, minus the cumulative `w` bars back when that many bars exist in
    the same session; otherwise the partial sum from the session open. No value at any bar reads
    the prior session.
    """
    s = pd.Series(np.asarray(x, dtype="float64"), index=pd.RangeIndex(len(x)))
    grp = pd.Series(day, index=s.index)
    cum = s.groupby(grp, sort=False).cumsum()
    n = grp.groupby(grp, sort=False).cumcount()
    back = cum.shift(w)
    return (cum - back.where(n >= w, 0.0)).to_numpy()


def flow_one(df: pd.DataFrame) -> pd.DataFrame:
    """Causal 1-minute flow/path features for one symbol, evaluated at every minute bar."""
    c, h, l, v = df["c"], df["h"], df["l"], df["v"].astype("float64")
    day = np.asarray(pd.Index(df.index.date))

    logc = np.log(c)
    r = pd.Series(logc.to_numpy(), index=df.index).groupby(day, sort=False).diff()
    r = r.fillna(0.0)                       # the session's first minute carries no signed info
    absr = r.abs()

    # tick rule: zero-return minutes inherit the last non-zero sign inside the same session
    sgn = pd.Series(np.sign(r.to_numpy()), index=df.index).replace(0.0, np.nan)
    sgn = sgn.groupby(day, sort=False).ffill().fillna(0.0)
    sv = sgn.to_numpy() * v.to_numpy()

    rng = (h - l).to_numpy()
    clv = np.where(rng > 0, ((c - l).to_numpy() - (h - c).to_numpy()) / np.maximum(rng, EPS), 0.0)
    mf = clv * v.to_numpy()
    dv = (c * v).to_numpy()
    up = (r.to_numpy() > 0).astype("float64")

    f = pd.DataFrame(index=df.index)
    for w, tag in ((5, "5"), (30, "30")):
        vw = _roll_within_day(v.to_numpy(), day, w)
        f[f"ofi{tag}"] = _roll_within_day(sv, day, w) / np.maximum(vw, EPS)
        f[f"clv{tag}"] = _roll_within_day(mf, day, w) / np.maximum(vw, EPS)
        f[f"eff{tag}"] = (np.abs(_roll_within_day(r.to_numpy(), day, w))
                          / np.maximum(_roll_within_day(absr.to_numpy(), day, w), EPS))

    cv = pd.Series(v.to_numpy(), index=f.index).groupby(day, sort=False).cumsum().to_numpy()
    f["ofi_sess"] = (pd.Series(sv, index=f.index).groupby(day, sort=False).cumsum().to_numpy()
                     / np.maximum(cv, EPS))
    f["clv_sess"] = (pd.Series(mf, index=f.index).groupby(day, sort=False).cumsum().to_numpy()
                     / np.maximum(cv, EPS))
    f["updn30"] = _roll_within_day(up, day, 30) / 30.0

    d30 = _roll_within_day(dv, day, 30)
    f["amihud30"] = np.log1p(1e9 * _roll_within_day(absr.to_numpy(), day, 30)
                             / np.maximum(d30, EPS))
    f["dvol30"] = np.log1p(d30)
    return f


def decision_minutes(idx: pd.DatetimeIndex) -> np.ndarray:
    """The last 1-minute bar of each 5-minute decision bar: starts 09:59, 10:29, ... 14:59."""
    mod = (idx.hour - 9) * 60 + idx.minute - 30
    wanted = [f1.FIRST_DECISION + f1.STEP * f1.BAR * k + (f1.BAR - 1) for k in range(f1.N_DECISIONS)]
    return np.isin(mod, wanted)


def build_flow(symbols: list[str] | None = None) -> pd.DataFrame:
    """Flow features for every tradable name at the 11 decision points, plus the SPY copies."""
    store = sorted(p.stem for p in ic.DATA_DIR.glob("*.parquet"))
    syms = symbols or store
    tradable = [s for s in syms if s not in f1.EXCLUDE]

    mkt = ic.load_bars(f1.MARKET)
    if mkt.empty:
        raise SystemExit(f"no {f1.MARKET} bars in {ic.DATA_DIR}")
    mfl = flow_one(mkt)
    mdm = decision_minutes(mfl.index)
    m = mfl[mdm][["ofi30", "clv30", "eff30"]].copy()
    m.columns = MKT_FLOW
    # index by the DECISION bar's start, which is 4 minutes earlier - the panel's own `ts`
    m.index = m.index - pd.Timedelta(minutes=f1.BAR - 1)

    rows = []
    for i, s in enumerate(tradable, 1):
        t0 = time.time()
        bars = ic.load_bars(s)
        if len(bars) < 25_000:
            print(f"  [{i:>2}/{len(tradable)}] {s:<6} skipped ({len(bars):,} minute bars)")
            continue
        f = flow_one(bars)
        dm = decision_minutes(f.index)
        sub = f[dm].copy()
        sub.index = sub.index - pd.Timedelta(minutes=f1.BAR - 1)
        sub["sym"] = s
        rows.append(sub)
        print(f"  [{i:>2}/{len(tradable)}] {s:<6} {len(sub):>7,} rows  ({time.time()-t0:.1f}s)")

    flow = pd.concat(rows)
    flow = flow.join(m, how="left")
    flow["x_ofi30"] = flow["ofi30"] - flow["m_ofi30"]
    flow["x_clv30"] = flow["clv30"] - flow["m_clv30"]
    flow = flow.reset_index().rename(columns={"index": "ts", "date": "ts"})

    g = flow.groupby("ts", sort=False)
    for c in RANK_FLOW_OF:
        flow[f"cs_{c}"] = g[c].rank(pct=True)

    flow = flow.replace([np.inf, -np.inf], np.nan)
    for c in FLOW_FEATS:
        flow[c] = flow[c].astype("float32")
    return flow[["ts", "sym"] + FLOW_FEATS].sort_values(["ts", "sym"]).reset_index(drop=True)


# --------------------------------------------------------------------- clause 3: the three arms


def load_panel() -> pd.DataFrame:
    """F-8's labelled panel with the flow family MERGED ON (clause 1: never inner-joined)."""
    panel = pd.read_parquet(f1.PANEL)
    p = f8.add_labels(panel)
    del panel
    flow = pd.read_parquet(FLOW)
    flow["ts"] = pd.to_datetime(flow["ts"])
    n0 = len(p)
    p = p.merge(flow, on=["ts", "sym"], how="left")
    assert len(p) == n0, "the flow merge duplicated rows - (ts, sym) is not unique in the store"
    cov = float(p["ofi30"].notna().mean())
    print(f"panel {len(p):,} rows; flow coverage {100 * cov:.2f}% "
          f"({int(p['ofi30'].isna().sum()):,} rows carry NaN flow and are KEPT, clause 1)")
    return p


def fit_arms(arms: list[str], scramble_flow: int | None = None,
             importance: bool = False) -> pd.DataFrame:
    """Walk-forward fit of `y_close` under each feature set. Everything else is held fixed."""
    p = load_panel()
    p = p.dropna(subset=["y_close"]).copy()
    p["y"] = p["y_close"]
    params = dict(f1.GRID["mid"])
    years = [y for y in sorted(p["year"].unique()) if y >= f8.FIRST_TEST_YEAR]

    if scramble_flow is not None:
        rng = np.random.default_rng(scramble_flow)
        print(f"clause 6 control: permuting {len(FLOW_FEATS)} flow columns within each timestamp")
        idx = p.groupby("ts", sort=False).cumcount().to_numpy()      # only to size the groups
        del idx
        for c in FLOW_FEATS:
            p[c] = (p.groupby("ts", sort=False)[c]
                    .transform(lambda s: rng.permutation(s.to_numpy())).astype("float32"))

    print(f"label y_close: {len(p):,} rows, {p['sym'].nunique()} symbols, "
          f"{p['day'].nunique():,} sessions; learner 'mid' {params}; test years {years}")

    frames, models, ics = [], {}, []
    saved = list(f1.FEATURES)
    try:
        for arm in arms:
            feats = ARMS[arm]
            f1.FEATURES = feats                       # fit_predict reads the module global
            print(f"\n--- arm {arm}: {len(feats)} features")
            for year in years:
                trn = p[p.year <= year - 2]
                vld = p[p.year == year - 1]
                tst = p[p.year == year]
                if not (len(trn) and len(vld) and len(tst)):
                    continue
                t0 = time.time()
                model, pt = f1.fit_predict(trn, vld, tst, dict(params))
                icm, ict = f1.ic_stats(tst, pt)
                ics.append({"arm": arm, "year": int(year), "ic": icm, "ic_t": ict,
                            "iters": int(model.n_iter_)})
                keep = tst[["ts", "day", "year", "sym", "slot", "entry_px", "fwd"]].copy()
                keep["arm"] = arm
                keep["pred"] = pt
                frames.append(keep)
                if importance:
                    models[(arm, int(year))] = (model, vld, feats)
                print(f"  {year}: train<={year-2} ({len(trn):,}) valid {year-1} ({len(vld):,}) "
                      f"test ({len(tst):,}) iters {model.n_iter_:>4}  rank IC {icm:+.5f} "
                      f"(t {ict:+.1f})  ({time.time()-t0:.0f}s)")
    finally:
        f1.FEATURES = saved

    out = pd.concat(frames, ignore_index=True)
    icd = pd.DataFrame(ics)
    print("\n=== clause 4(a): per-timestamp rank IC on y_close, by arm and test year ===")
    piv = icd.pivot(index="year", columns="arm", values="ic")
    print(piv.round(5).to_string())
    print("\nmean " + "  ".join(f"{a} {piv[a].mean():+.5f}" for a in piv.columns))
    if importance and models:
        _importance(models)
    return out, icd


def _importance(models: dict) -> None:
    """Clause 4(e): how much of the tree is the new family, and is its ranking stable?"""
    from sklearn.inspection import permutation_importance
    print("\n=== clause 4(e): permutation importance on each retrain's validation year ===")
    rows = []
    for (arm, year), (model, vld, feats) in sorted(models.items()):
        s = vld.sample(min(120_000, len(vld)), random_state=0)
        r = permutation_importance(model, s[feats].to_numpy(dtype=np.float32),
                                   s["y"].to_numpy() * 1e4, n_repeats=3, random_state=0,
                                   scoring="neg_mean_squared_error", n_jobs=1)
        imp = pd.Series(r.importances_mean, index=feats)
        for k, v in imp.items():
            rows.append({"arm": arm, "year": year, "feature": k, "imp": float(v)})
        tot = imp.clip(lower=0).sum()
        fl = imp.reindex(FLOW_FEATS).clip(lower=0).sum()
        print(f"  {arm:<5} {year}: flow family carries "
              f"{100 * fl / tot if tot > 0 else float('nan'):>5.1f}% of positive importance; "
              f"top 5 {', '.join(imp.sort_values(ascending=False).head(5).index)}")
    df = pd.DataFrame(rows)
    IMP.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(IMP, index=False)

    for arm, sub in df.groupby("arm"):
        piv = sub.pivot(index="feature", columns="year", values="imp")
        ranks = piv.rank(ascending=False)
        cors = [ranks[a].corr(ranks[b], method="spearman")
                for i, a in enumerate(ranks.columns) for b in ranks.columns[i + 1:]]
        top = {c: set(ranks[c].nsmallest(10).index) for c in ranks.columns}
        allyr = set.intersection(*top.values())
        pair = set.union(*[a & b for a in top.values() for b in top.values() if a is not b]) \
            if len(top) > 1 else set()
        print(f"\n  {arm}: mean pairwise Spearman of yearly importance ranks "
              f"{np.mean(cors):+.3f} ({min(cors):+.3f}..{max(cors):+.3f}); "
              f"in every year's top 10: {sorted(allyr) if allyr else 'none'}")
        del pair
        print(f"         most persistent: " + ", ".join(
            f"{k} ({v:.1f})" for k, v in ranks.mean(axis=1).nsmallest(6).items()))
    print(f"\nwritten: {IMP}")


# ------------------------------------------------------------------------- clause 4(b): the book


def frame_for(preds: pd.DataFrame, arm: str) -> pd.DataFrame:
    """F-8's price grid with this arm's prediction merged on - his `session` book, unchanged."""
    grid = f8.price_grid()
    g = preds[preds["arm"] == arm]
    return grid.merge(g[["ts", "sym", "pred"]], on=["ts", "sym"], how="left")


def by_year(sess: pd.DataFrame) -> pd.Series:
    y = pd.Series(pd.to_datetime(sess["day"]).dt.year.to_numpy(), index=sess.index)
    return sess.groupby(y)["net"].mean().round(0)


def paired(a: pd.DataFrame, b: pd.DataFrame, name: str) -> dict:
    """Clause 4(c): paired on the shared sessions, decomposed. Never two t's side by side."""
    assert (a["day"].to_numpy() == b["day"].to_numpy()).all()
    d = b["net"].to_numpy() - a["net"].to_numpy()
    dg = b["gross"].to_numpy() - a["gross"].to_numpy()
    dc = a["cost"].to_numpy() - b["cost"].to_numpy()
    print(f"{name:<28} net {d.mean():>+8,.0f} (t {f1.tstat(d):>+5.2f}, "
          f"{100 * (d > 0).mean():>3.0f}% of sessions)   "
          f"gross {dg.mean():>+8,.0f} (t {f1.tstat(dg):>+5.2f})   "
          f"cost {dc.mean():>+7,.0f} (t {f1.tstat(dc):>+6.2f})")
    return {"d_net": float(d.mean()), "d_net_t": f1.tstat(d),
            "d_gross": float(dg.mean()), "d_gross_t": f1.tstat(dg),
            "d_cost": float(dc.mean()), "d_cost_t": f1.tstat(dc)}


def market_regime() -> pd.Series:
    """Clause 4(d): terciles of SPY's own trailing 20-session realised vol, causal."""
    mkt = ic.load_bars(f1.MARKET)
    day = pd.Index(mkt.index.date)
    close = mkt["c"].groupby(day).last()
    r = np.log(close / close.shift(1))
    rv = r.rolling(20, min_periods=10).std().shift(1)          # shift: today reads yesterday
    q = rv.rank(pct=True)
    lab = pd.Series(np.where(q <= 1 / 3, "low", np.where(q <= 2 / 3, "mid", "high")),
                    index=rv.index)
    lab[rv.isna()] = "na"
    lab.index = pd.Index([str(d) for d in lab.index])
    return lab


def record(tag: str, r: dict, sess: pd.DataFrame, params: dict, extra: dict) -> None:
    net = sess["net"].to_numpy()
    n = len(sess)
    ret = net / EQUITY
    sd = ret.std(ddof=1) if n > 1 else 0.0
    rec = {"ts": dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
           "algorithm": "intraday/f14_features", "class": "ml", "tag": tag, "commit": "",
           "run_dir": "", "track": "F-14", "params": params,
           "start": str(sess["day"].min()), "end": str(sess["day"].max()),
           # `stats`, string-valued: F-8's and F-12's convention, which is what reads the ledger.
           "stats": {"Sessions": str(n),
                     "Avg Daily PnL": f"{net.mean():.0f}",
                     "t": f"{f1.tstat(net):.2f}",
                     "Gross Per Day": f"{sess['gross'].mean():.0f}",
                     "Costs Per Day": f"{sess['cost'].mean():.0f}",
                     "Turnover Per Day": f"{sess['turnover'].mean():.0f}",
                     "Gross Bps Per Turnover": f"{r['gross_bps']:.3f}",
                     "Cost Bps Per Turnover": f"{r['cost_bps']:.3f}",
                     "Edge Bps Per Turnover": f"{r['edge_bps']:.3f}",
                     "Worst Day": f"{net.min():.0f}",
                     "Win Rate": f"{100 * (net > 0).mean():.0f}%",
                     "Sharpe Ratio": f"{(ret.mean() / sd * np.sqrt(252)) if sd else float('nan'):.3f}",
                     "Diagnostic": "true",
                     **{k: str(v) for k, v in extra.items()}}}
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, default=str) + "\n")


# ------------------------------------------------------------------------------------ the books


def run_books(record_rows: bool = False) -> None:
    preds = pd.read_parquet(PREDS)
    preds["ts"] = pd.to_datetime(preds["ts"])
    arms = [a for a in ("base", "flow", "both", "both_scrambled") if a in set(preds["arm"])]
    print(f"costed against {ic.DATA_DIR}  (_splits.json present: "
          f"{(ic.DATA_DIR / 'splits.json').exists() or (ic.DATA_DIR / '_splits.json').exists()})")

    sess, rows = {}, []
    for arm in arms:
        s = f8.simulate(frame_for(preds, arm), "session", decile=DECILE)
        sess[arm] = s
        rows.append(f8.summarize(s, f"session/{arm}"))

    print("\n=== clause 4(b): F-8's session book, one decision per session, held to the flatten ===")
    f8.print_table(rows)

    print("\n=== net $/day by test year ===")
    yr = pd.DataFrame({a: by_year(sess[a]) for a in arms})
    print(yr.to_string())
    print("years positive: " + "  ".join(f"{a} {int((yr[a] > 0).sum())}/{len(yr)}" for a in arms))

    print("\n=== clause 4(c): paired per session, decomposed ===")
    pairs = {}
    for arm in arms:
        if arm == "base":
            continue
        pairs[arm] = paired(sess["base"], sess[arm], f"{arm} - base")

    print("\n=== clause 4(d): regime split, terciles of SPY trailing 20-session realised vol ===")
    reg = market_regime()
    print(f"{'cell':<16}" + "".join(f"{k:>12}" for k in ("low", "mid", "high")))
    for arm in arms:
        s = sess[arm].copy()
        s["reg"] = s["day"].astype(str).map(reg)
        m = s.groupby("reg")["net"].mean()
        print(f"{arm:<16}" + "".join(f"{m.get(k, float('nan')):>12,.0f}"
                                     for k in ("low", "mid", "high")))

    # ---------------------------------------------------------------------------- the decision
    r = {x["label"]: x for x in rows}["session/both"]
    b = {x["label"]: x for x in rows}["session/base"]
    n_pos = int((yr["both"] > 0).sum())
    dp = pairs.get("both", {})
    ok = (r["t"] > 2.0) and (n_pos >= 5) and (dp.get("d_net_t", -9) > 2.0)
    print("\n=== clause 5: the pre-registered pass rule ===")
    print(f"  net t > 2.0                : {r['t']:+.3f}   {'PASS' if r['t'] > 2 else 'FAIL'}")
    print(f"  >= 5 of 8 years positive   : {n_pos}/8      "
          f"{'PASS' if n_pos >= 5 else 'FAIL'}")
    print(f"  paired both-base t > 2.0   : {dp.get('d_net_t', float('nan')):+.3f}   "
          f"{'PASS' if dp.get('d_net_t', -9) > 2 else 'FAIL'}")
    print(f"\nDECISION: {'ACCEPT' if ok else 'REFUSE'}  "
          f"(base t {b['t']:+.3f} -> both t {r['t']:+.3f})")

    pd.DataFrame(rows).to_csv(CELLS, index=False)
    print(f"cells -> {CELLS}")

    if record_rows:
        for x in rows:
            arm = x["label"].split("/")[1]
            record(f"F-14 {x['label']}: feature-set axis, label close, session book",
                   x, sess[arm],
                   {"arm": arm, "features": len(ARMS.get(arm, ARMS['both'])), "label": LABEL,
                    "model": "mid", "decile": DECILE, "gross": 1.0},
                   {"paired_vs_base": pairs.get(arm, {})})
        print(f"recorded {len(rows)} DIAGNOSTIC rows -> {LEDGER}")


# --------------------------------------------------------------- post-run, explicitly post-run


def run_post() -> None:
    """POST-RUN, barred from clause 5: what do the flow columns predict on their own?

    The three arms answer "does a tree fed this family do better". They cannot answer "does the
    family contain a signal at all", because a tree that finds nothing and a family that holds
    nothing print the same table. The univariate per-timestamp rank IC of each raw column against
    `y_close` separates them, and it needs no model.
    """
    p = load_panel()
    p = p.dropna(subset=["y_close"]).copy()
    p = p[p["year"] >= f8.FIRST_TEST_YEAR]
    print(f"\n=== POST-RUN: univariate rank IC vs y_close, test window only "
          f"({len(p):,} rows, {p['day'].nunique():,} sessions) ===")
    print(f"{'feature':<14}{'rank IC':>10}{'t':>8}   {'family':<8}")
    ref = ["r6", "r_sess", "vol_rel", "rvol_ratio", "gap", "vwap_atr"]
    for fam, cols in (("flow", FLOW_FEATS), ("base", ref)):
        for c in cols:
            sub = p[["ts", c, "y_close"]].dropna()
            sub = sub.rename(columns={"y_close": "y"})
            icm, ict = f1.ic_stats(sub, sub[c].to_numpy())
            print(f"{c:<14}{icm:>+10.5f}{ict:>+8.1f}   {fam:<8}")

    print("\n=== POST-RUN: is the family orthogonal or redundant? "
          "max |Spearman| of each flow column against the 38 ===")
    s = p.sample(min(200_000, len(p)), random_state=0)
    for c in FLOW_FEATS:
        cor = s[list(f1.FEATURES)].corrwith(s[c], method="spearman").abs()
        print(f"{c:<14} max {cor.max():.3f} vs {cor.idxmax():<14} "
              f"(median over the 38: {cor.median():.3f})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--post", action="store_true", help="post-run univariate IC + redundancy")
    ap.add_argument("--flow", action="store_true", help="build the 1-minute flow features")
    ap.add_argument("--fit", action="store_true", help="walk-forward fit of the three arms")
    ap.add_argument("--control", action="store_true", help="clause 6: scrambled-flow refit")
    ap.add_argument("--books", action="store_true")
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--importance", action="store_true")
    ap.add_argument("--arms", nargs="*", default=None)
    ap.add_argument("--symbols", nargs="*", default=None)
    args = ap.parse_args()

    if args.flow:
        OUT.mkdir(parents=True, exist_ok=True)
        print(f"building flow features from {ic.DATA_DIR} ...")
        fl = build_flow(args.symbols)
        fl.to_parquet(FLOW, index=False)
        print(f"\nflow: {len(fl):,} rows x {len(FLOW_FEATS)} features -> {FLOW}")
        print(f"  {fl['ts'].min()} .. {fl['ts'].max()}  {fl['sym'].nunique()} symbols")
        print(fl[FLOW_FEATS].describe().T[["mean", "std", "min", "max"]].round(4).to_string())

    if args.fit:
        arms = args.arms or ["base", "flow", "both"]
        out, _ = fit_arms(arms, importance=args.importance)
        if PREDS.exists() and args.arms:
            old = pd.read_parquet(PREDS)
            old["ts"] = pd.to_datetime(old["ts"])
            out = pd.concat([old[~old["arm"].isin(arms)], out], ignore_index=True)
        out.to_parquet(PREDS, index=False)
        print(f"\nfrozen: {len(out):,} rows -> {PREDS}")

    if args.control:
        out, _ = fit_arms(["both"], scramble_flow=20260914)
        out["arm"] = "both_scrambled"
        if PREDS.exists():
            old = pd.read_parquet(PREDS)
            old["ts"] = pd.to_datetime(old["ts"])
            out = pd.concat([old[old["arm"] != "both_scrambled"], out], ignore_index=True)
        out.to_parquet(PREDS, index=False)
        print(f"\nfrozen: {len(out):,} rows -> {PREDS}")

    if args.importance and not args.fit:
        fit_arms(["both"], importance=True)

    if args.post:
        run_post()

    if args.books:
        run_books(args.record)


if __name__ == "__main__":
    main()
