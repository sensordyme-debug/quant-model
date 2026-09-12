"""F-7: is there a lower-turnover expression of F-1's own forecast that clears its own cost floor?

F-1 found the first positive out-of-sample gross edge on the intraday side of this repository
(pooled IC **+0.01133 at t +4.74**, gross **+$1,102/day at t +3.04**) and refused it on arithmetic
rather than on judgement: the book turns **$13.83M/day on $1M** and the forecast is worth
**0.797 bps per dollar turned** against **0.892 bps of commission and regulatory fees** and
**2.392 bps** once the shipped 1.5 bps slippage constant is charged. F-1's closing paragraph said
"do not re-open as a feature, model or horizon question" and named the one thing that would change
the arithmetic - *a lower-turnover expression of the same forecast* - then followed only the
**daily** route (F-3, refused: 0.304 bps per dollar turned, IC t +0.18).

The within-session route was never tried, and it is the only one left that needs no new model, no
new feature and no new label. **This iteration changes nothing about the forecast.** F-1's
walk-forward is reproduced bit-for-bit, its out-of-sample predictions are frozen to a cache, and
the only thing that varies is the **book built on top of them** - which trades to pay for, not
which names to rank.

    python scripts/ml_f7.py --predict           # reproduce F-1's walk-forward -> data/f1/preds_test.parquet
    python scripts/ml_f7.py --book              # the construction sweep on the frozen forecast
    python scripts/ml_f7.py --book --record     # ... and append DIAGNOSTIC rows to the ledger
    python scripts/ml_f7.py --predict --importance   # permutation importance on each retrain

--------------------------------------------------------------------------------------------
PRE-REGISTERED, all of it written before a single construction number was read
--------------------------------------------------------------------------------------------

**The arithmetic that has to be beaten.** A dollar-neutral book's net is
`turnover x (gross_bps - cost_bps)`. Cost bps per dollar traded is a property of the instrument,
not of the construction: 0.892 of commission + SEC/TAF, 2.392 with the shipped slippage. F-1's
forecast pays 0.797. So **any** construction must raise gross bps per dollar turned by a factor of
**1.12x to clear commission at literally zero spread** and **3.00x to clear the shipped cost**.
Turnover reduction alone cannot pass: cutting turnover by 10x while cutting gross by 10x leaves
gross bps per dollar exactly where it was, and merely walks the loss toward zero. **The pass rule
is on net dollars, not on bps** (clause 7).

**Clause 1 - identity.** The frozen predictions, run through this module's own simulator at
F-1's decile 0.10 book, must reproduce F-1's ledger row `20260911T155155Z`: gross $1,102/day,
net -$2,206/day, turnover $13,831,037/day, IC +0.01133. F-1's `fit_predict` passes
`random_state=0`, so this is an exact test, not an approximate one. If it fails, nothing below is
read and the iteration reports the reproduction failure instead.

**Clause 2 - the mechanism is measured before any book is built, and it predicts the answer.**
A construction that holds a position for `k` decision intervals instead of one earns, per dollar
traded, roughly `sum_{h=1..k} IC(h) / IC(1)` times what the one-interval book earns, where `IC(h)`
is the forecast's information coefficient against the demeaned return `h` intervals ahead. That
sum is computable from the frozen predictions with no book at all. **Pre-registered prediction:
if `sum_{h=1..k} IC(h)/IC(1)` does not reach 3.0 for any k <= 11, no dwell/band construction can
clear the shipped cost, and the refusal is arithmetic rather than empirical.** The table is
reported either way, because it is the reusable number: it prices the forecast's persistence.

**Clause 3 - the constructions.** Every one is causal and reads only the frozen prediction:
  - `base(d)`     F-1's book: top/bottom decile `d`, equal-weighted, gross 1.0, full rebalance.
  - `dwell(k,d)`  the same book, re-decided only every k-th decision point, held in between.
  - `band(e,x)`   hysteresis: enter the long side at rank percentile >= 1-e, stay until it falls
                  below 1-x (x > e). Each side equal-weighted to gross/2, so the book stays
                  dollar-neutral with unequal counts. Turnover falls without breadth falling.
  - `ewma(l,d)`   the decile rule applied to a within-session EWMA of the prediction (reset every
                  morning, since the book is flat overnight). Removes churn driven by prediction
                  noise rather than by news.
  - `conv(m,d)`   conviction gate: inside the decile sets keep only names whose predicted
                  |alpha| in bps exceeds `m x` the one-way cost. F-1's decile takes a fixed count
                  every timestamp whether or not the model sees anything; this spends the cost
                  only where the forecast claims it is covered. Predictions are in basis points by
                  construction (F-1 trains on `y * 1e4`), so the comparison needs no calibration.
  - stacked cells of the two that move the number most.

**Clause 4 - the control that can refuse the construction.** Every construction is re-run on a
**per-timestamp random permutation of the prediction**, seeded, at the same parameters. It has the
same turnover profile and the same breadth, and it must produce gross bps per dollar turned
indistinguishable from zero. If a construction improves the random book's bps as much as the real
book's, the improvement is the construction's arithmetic and not the forecast's persistence.

**Clause 5 - the decisive column is gross bps per dollar turned, not net dollars per day.** A
construction that trades a tenth as much has a tenth of the loss and looks better on every
dollar-denominated statistic while being exactly as unprofitable. Every table below leads with
gross bps and quotes the multiple over F-1's 0.797.

**Clause 6 - regimes.** Out-of-sample P&L after costs is reported by test year (2024/2025/2026,
the axis on which F-1's edge decayed +0.0192 -> +0.0113 -> -0.0001) and by the causal trailing
20-session realized volatility tercile of SPY. A construction that only works in one regime is
reported as such and not aggregated away.

**Clause 7 - the pass rule, identical to F-1's so the two are comparable.** Net P&L per day
positive with t > 2 pooled over 2024-2026 **and** positive in at least two of the three test
years. Nothing deploys otherwise, and nothing deploys from this file at all without a separate
pre-registration - `algorithms/intraday/active/signal.py` and `live/intraday_config.json` are not
touched here.
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
import intraday_common as ic  # noqa: E402
import sweep_f1 as f1  # noqa: E402

LEDGER = REPO / "research" / "experiments.jsonl"
OUT = REPO / "data" / "f1"
PRED = OUT / "preds_test.parquet"
IMP = OUT / "importance_f7.csv"

EQUITY = 1_000_000.0
#: F-1's ledger row 20260911T155155Z - the identity target for clause 1.
F1_REF = {"gross_day": 1102.0, "net_day": -2206.0, "turn_day": 13_831_037.0,
          "gross_bps": 0.797, "cost_bps": 2.392, "ic": 0.01133}
#: The cost floor a construction has to clear, in bps per dollar turned. Not negotiable: the
#: first is IBKR commission + SEC/TAF alone, the second adds the shipped slippage constant.
FLOOR_COMMISSION = 0.892
FLOOR_SHIPPED = 2.392


# ------------------------------------------------------------------------------ frozen forecast


def build_predictions(importance: bool = False) -> pd.DataFrame:
    """Reproduce F-1's stage-2 walk-forward exactly and cache the out-of-sample predictions."""
    panel = pd.read_parquet(f1.PANEL)
    panel["ts"] = pd.to_datetime(panel["ts"])
    params = dict(f1.GRID["mid"])  # F-1's stage-1 selection, recorded in every F-1 ledger row
    print(f"panel {len(panel):,} rows, {panel['sym'].nunique()} symbols, "
          f"{panel['day'].nunique():,} sessions; model 'mid' {params}")

    frames, models = [], {}
    for year in sorted(panel[panel.year >= 2024].year.unique()):
        trn = panel[panel.year <= year - 2]
        vld = panel[panel.year == year - 1]
        tst = panel[panel.year == year]
        t0 = time.time()
        model, pt = f1.fit_predict(trn, vld, tst, dict(params))
        icm, ict = f1.ic_stats(tst, pt)
        keep = tst[["ts", "day", "year", "sym", "entry_px", "fwd", "y"]].copy()
        keep["pred"] = pt
        frames.append(keep)
        models[int(year)] = (model, vld)
        print(f"  {year}: train<={year-2} ({len(trn):,}) valid {year-1} ({len(vld):,}) "
              f"test ({len(tst):,}) iters {model.n_iter_:>4}  IC {icm:+.5f} (t {ict:+.2f})  "
              f"({time.time()-t0:.0f}s)")

    test = pd.concat(frames, ignore_index=True)
    OUT.mkdir(parents=True, exist_ok=True)
    test.to_parquet(PRED, index=False)
    icm, ict = f1.ic_stats(test, test["pred"].to_numpy())
    print(f"\nfrozen: {len(test):,} rows -> {PRED}")
    print(f"pooled out-of-sample IC {icm:+.5f} (t {ict:+.2f})   "
          f"[F-1 reported {F1_REF['ic']:+.5f} at t +4.74]")

    if importance:
        from sklearn.inspection import permutation_importance
        print("\n=== permutation importance on each retrain's validation year ===")
        imps = {}
        for year, (model, vld) in models.items():
            sub = vld.sample(min(120_000, len(vld)), random_state=0)
            r = permutation_importance(model, sub[f1.FEATURES].to_numpy(dtype=np.float32),
                                       sub["y"].to_numpy(), n_repeats=3, random_state=0,
                                       scoring="neg_mean_squared_error", n_jobs=1)
            imps[year] = pd.Series(r.importances_mean, index=f1.FEATURES)
            print(f"  {year} done")
        imp = pd.DataFrame(imps)
        imp["rank_mean"] = imp.rank(ascending=False).mean(axis=1)
        imp = imp.sort_values("rank_mean")
        imp.to_csv(IMP)
        print(imp.head(15).to_string(float_format=lambda x: f"{x: .3e}"))
        print("\nrank correlation between retrains (stability of what the model reads):")
        print(imp[list(models)].rank().corr(method="spearman").to_string(
            float_format=lambda x: f"{x:.3f}"))
    return test


# --------------------------------------------------------------------------------- simulator


class Slices:
    """The frozen forecast pre-grouped by decision point - built once, reused by every cell."""

    def __init__(self, test: pd.DataFrame):
        d = test.sort_values(["ts", "sym"]).reset_index(drop=True)
        self.days, self.slices = [], []
        for ts, g in d.groupby("ts", sort=True):
            self.days.append(g["day"].iloc[0])
            self.slices.append((g["sym"].to_numpy(), g["pred"].to_numpy(float),
                                g["fwd"].to_numpy(float), g["entry_px"].to_numpy(float)))
        self.day_arr = np.asarray(self.days)
        # decision index inside its own session: 0..10, the `dwell` clock
        self.k_in_day = np.zeros(len(self.days), dtype=int)
        seen: dict = {}
        for i, day in enumerate(self.days):
            self.k_in_day[i] = seen.get(day, 0)
            seen[day] = self.k_in_day[i] + 1
        self._scale: dict = {}

    def scale(self, sym: str, day) -> float:
        key = (sym, day)
        s = self._scale.get(key)
        if s is None:
            s = ic.share_scale(sym, day)
            self._scale[key] = s
        return s


def _decile_weights(pred: np.ndarray, decile: float, gross: float) -> np.ndarray:
    n = len(pred)
    k = max(1, int(round(decile * n)))
    order = pred.argsort()
    w = np.zeros(n)
    w[order[-k:]] = gross / 2.0 / k
    w[order[:k]] = -gross / 2.0 / k
    return w


def _side_weights(long_m: np.ndarray, short_m: np.ndarray, gross: float) -> np.ndarray:
    """Equal weight inside each side, each side to gross/2. Flat if either side is empty."""
    nl, ns = int(long_m.sum()), int(short_m.sum())
    w = np.zeros(len(long_m))
    if nl == 0 or ns == 0:
        return w
    w[long_m] = gross / 2.0 / nl
    w[short_m] = -gross / 2.0 / ns
    return w


def target_book(kind: str, pred: np.ndarray, held: np.ndarray, p: dict,
                gross: float = 1.0) -> np.ndarray:
    """The target weights at one decision point. `held` is the book carried in (for hysteresis)."""
    n = len(pred)
    if kind in ("base", "dwell", "ewma"):
        return _decile_weights(pred, p["decile"], gross)

    if kind == "band":
        # rank percentile in [0,1]; 1.0 is the most positive prediction
        pct = pred.argsort().argsort() / max(n - 1, 1)
        e, x = p["enter"], p["exit"]
        long_m = (pct >= 1.0 - e) | ((held > 0) & (pct >= 1.0 - x))
        short_m = (pct <= e) | ((held < 0) & (pct <= x))
        both = long_m & short_m
        long_m, short_m = long_m & ~both, short_m & ~both
        return _side_weights(long_m, short_m, gross)

    if kind == "conv":
        k = max(1, int(round(p["decile"] * n)))
        order = pred.argsort()
        thr = p["mult"] * FLOOR_SHIPPED          # one-way cost in bps; pred is already in bps
        long_m = np.zeros(n, bool)
        short_m = np.zeros(n, bool)
        long_m[order[-k:]] = True
        short_m[order[:k]] = True
        long_m &= pred >= thr
        short_m &= pred <= -thr
        return _side_weights(long_m, short_m, gross)

    if kind == "bandconv":
        pct = pred.argsort().argsort() / max(n - 1, 1)
        e, x = p["enter"], p["exit"]
        thr = p["mult"] * FLOOR_SHIPPED
        long_m = ((pct >= 1.0 - e) & (pred >= thr)) | ((held > 0) & (pct >= 1.0 - x))
        short_m = ((pct <= e) & (pred <= -thr)) | ((held < 0) & (pct <= x))
        both = long_m & short_m
        long_m, short_m = long_m & ~both, short_m & ~both
        return _side_weights(long_m, short_m, gross)

    raise ValueError(kind)


def simulate(sl: Slices, kind: str, p: dict, gross: float = 1.0, costs: bool = True,
             scramble: int | None = None) -> pd.DataFrame:
    """One row per session: gross, cost, net, turnover - for any construction in `target_book`.

    `scramble` is clause 4's control: the prediction is permuted inside each decision point, so
    the construction, the breadth and the turnover profile are preserved and only the forecast is
    destroyed.
    """
    rng = np.random.default_rng(scramble) if scramble is not None else None
    lam = p.get("lam")
    dwell = int(p.get("dwell", 1))

    rows = []
    prev_w: dict[str, float] = {}
    prev_day = None
    ewma_state: dict[str, float] = {}
    target_prev: np.ndarray | None = None

    for i, (syms, pred, fwd, px) in enumerate(sl.slices):
        day = sl.days[i]
        new_session = day != prev_day
        if new_session:
            if prev_w:
                rows.append(_flatten_row(prev_day, prev_w, last_px, last_syms, sl, costs))
            prev_w, ewma_state, target_prev, prev_day = {}, {}, None, day

        pr = pred.copy()
        if rng is not None:
            pr = rng.permutation(pr)
        if kind == "ewma":
            pr = np.array([(lam * pr[j] + (1 - lam) * ewma_state[s])
                           if s in ewma_state else pr[j] for j, s in enumerate(syms)])
            ewma_state = dict(zip(syms, pr))

        held = np.array([prev_w.get(s, 0.0) for s in syms])
        if dwell > 1 and sl.k_in_day[i] % dwell != 0 and target_prev is not None:
            w = held                                    # hold the carried book, trade nothing
        else:
            w = target_book(kind, pr, held, p, gross)
        target_prev = w

        pnl = float(np.dot(w, np.expm1(fwd)) * EQUITY)
        new_w = {s: v for s, v in zip(syms, w)}

        turn = 0.0
        cost = 0.0
        pxm = dict(zip(syms, px))
        for s in set(new_w) | set(prev_w):
            dw = new_w.get(s, 0.0) - prev_w.get(s, 0.0)
            if abs(dw) < 1e-12:
                continue
            notional = abs(dw) * EQUITY
            turn += notional
            if costs:
                q = float(pxm.get(s, np.nan))
                if not np.isfinite(q) or q <= 0:
                    continue
                sh = np.sign(dw) * notional / q
                cost += ic.commission(sh, q, sl.scale(s, day)) + ic.slippage(sh, q)
        rows.append({"day": day, "gross": pnl, "cost": cost, "turnover": turn})
        prev_w = {s: v for s, v in new_w.items() if abs(v) > 1e-12}
        last_px, last_syms = px, syms

    if prev_w:
        rows.append(_flatten_row(prev_day, prev_w, last_px, last_syms, sl, costs))

    per = pd.DataFrame(rows)
    sess = per.groupby("day").agg(gross=("gross", "sum"), cost=("cost", "sum"),
                                  turnover=("turnover", "sum"))
    sess["net"] = sess["gross"] - sess["cost"]
    return sess.reset_index()


def _flatten_row(day, prev_w: dict, px: np.ndarray, syms: np.ndarray, sl: Slices,
                 costs: bool) -> dict:
    """The 15:30 unwind, priced at the last decision bar's entry price (F-1's own convention)."""
    pxm = dict(zip(syms, px))
    c, turn = 0.0, 0.0
    for s, w in prev_w.items():
        if abs(w) < 1e-12:
            continue
        notional = abs(w) * EQUITY
        turn += notional
        q = float(pxm.get(s, np.nan))
        if not costs or not np.isfinite(q) or q <= 0:
            continue
        sh = -np.sign(w) * notional / q
        c += ic.commission(sh, q, sl.scale(s, day)) + ic.slippage(sh, q)
    return {"day": day, "gross": 0.0, "cost": c, "turnover": turn}


# ------------------------------------------------------------------------------------ reports


def summarize(sess: pd.DataFrame, label: str) -> dict:
    net = sess["net"].to_numpy()
    turn = float(sess["turnover"].mean())
    gross = float(sess["gross"].mean())
    gbps = 1e4 * gross / turn if turn else float("nan")
    return {"label": label, "sessions": len(sess),
            "net_day": float(net.mean()), "t": f1.tstat(net),
            "gross_day": gross, "cost_day": float(sess["cost"].mean()), "turn_day": turn,
            "gross_bps": gbps, "mult": gbps / F1_REF["gross_bps"],
            "cost_bps": 1e4 * float(sess["cost"].mean()) / turn if turn else float("nan"),
            "gross_t": f1.tstat(sess["gross"].to_numpy()),
            "worst": float(net.min()), "win": float((net > 0).mean())}


HDR = (f"{'cell':<26} {'sess':>4} {'gr bps':>7} {'x F-1':>6} {'gr t':>6} {'cost bps':>8} "
       f"{'turn/day':>11} {'$/day':>9} {'t':>6} {'worst':>9} {'win':>6}")


def print_table(rows: list[dict], hdr: bool = True) -> None:
    if hdr:
        print(HDR)
        print("-" * len(HDR))
    for r in rows:
        print(f"{r['label']:<26} {r['sessions']:>4} {r['gross_bps']:>7.3f} {r['mult']:>6.2f} "
              f"{r['gross_t']:>6.2f} {r['cost_bps']:>8.3f} {r['turn_day']:>11,.0f} "
              f"{r['net_day']:>9,.0f} {r['t']:>6.2f} {r['worst']:>9,.0f} {r['win']:>6.1%}")


def persistence_table(test: pd.DataFrame, max_h: int = 11) -> pd.DataFrame:
    """Clause 2: IC(h) and the cumulative multiple a k-interval hold can earn per dollar traded.

    IC(h) is the per-timestamp Spearman correlation of the frozen prediction with the demeaned
    cumulative return over the next h intervals, built from the same `fwd` column the book is
    paid in (interval h is `fwd` shifted h-1 forward inside the same session), so it is the same
    object the simulator earns and not a separate return series.
    """
    d = test.sort_values(["sym", "ts"]).copy()
    grp = d.groupby(["sym", "day"], sort=False)["fwd"]
    cum = pd.Series(0.0, index=d.index)
    rows = []
    for h in range(1, max_h + 1):
        cum = cum + grp.shift(-(h - 1))
        sub = d.assign(cum=cum).dropna(subset=["cum"])
        # a dollar-neutral book earns the cross-sectional spread, so demean at each timestamp
        sub["cum"] = sub["cum"] - sub.groupby("ts", sort=False)["cum"].transform("mean")
        ics = (sub.groupby("ts", sort=False)
               .apply(lambda g: g["pred"].corr(g["cum"], method="spearman")
                      if len(g) > 5 else np.nan, include_groups=False).dropna().to_numpy())
        rows.append({"h": h, "minutes": 30 * h, "n_ts": len(ics), "ic": float(ics.mean()),
                     "ic_t": f1.tstat(ics)})
    out = pd.DataFrame(rows)
    out["ic_rel"] = out["ic"] / out["ic"].iloc[0]
    # sum_{j=1..k} IC(j)/IC(1) is what a k-interval hold earns per dollar traded relative to the
    # one-interval book, because the hold trades once and collects k intervals of forecast.
    out["cum_mult"] = out["ic_rel"].cumsum()
    return out


def vol_regime(days: np.ndarray) -> pd.Series:
    """Causal trailing 20-session realized volatility of SPY, cut into terciles over the test."""
    spy = ic.load_bars("SPY")
    if spy.empty:
        return pd.Series("n/a", index=pd.Index(sorted(set(days)), name="day"))
    close = spy["c"].groupby(spy.index.date).last()
    rv = np.log(close).diff().rolling(20, min_periods=10).std().shift(1) * np.sqrt(252)
    rv.index = pd.Index(rv.index, name="day")
    rv = rv.reindex(pd.Index(sorted(set(days)), name="day"))
    q1, q2 = rv.quantile(1 / 3), rv.quantile(2 / 3)
    return pd.Series(np.where(rv.isna(), "n/a", np.where(rv <= q1, "low vol",
                     np.where(rv <= q2, "mid vol", "high vol"))), index=rv.index)


def record(tag: str, r: dict, sess: pd.DataFrame, params: dict, extra: dict) -> None:
    net = sess["net"].to_numpy()
    n = len(sess)
    ret = net / EQUITY
    years = n / 252.0
    car = (100 * ((1 + ret).prod() ** (1 / years) - 1)
           if years > 0 and (1 + ret).min() > 0 else float("nan"))
    curve = np.cumprod(1 + ret)
    dd = 100 * float((1 - curve / np.maximum.accumulate(curve)).max()) if n else 0.0
    sd = ret.std(ddof=1)
    rec = {"ts": dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
           "algorithm": "intraday/f7_turnover", "class": "ml", "tag": tag, "commit": "",
           "run_dir": "", "track": "F-7", "params": params,
           "start": str(sess["day"].min()), "end": str(sess["day"].max()),
           "stats": {"Sessions": str(n), "Avg Daily PnL": f"{net.mean():.0f}",
                     "t": f"{f1.tstat(net):.2f}",
                     "Gross Per Day": f"{sess['gross'].mean():.0f}",
                     "Costs Per Day": f"{sess['cost'].mean():.0f}",
                     "Turnover Per Day": f"{sess['turnover'].mean():.0f}",
                     "Gross Bps Per Turnover": f"{r['gross_bps']:.3f}",
                     "Gross Bps Multiple Of F1": f"{r['mult']:.2f}",
                     "Cost Bps Per Turnover": f"{r['cost_bps']:.3f}",
                     "Worst Day": f"{net.min():.0f}",
                     "Win Rate": f"{100 * (net > 0).mean():.0f}%",
                     "Compounding Annual Return": f"{car:.3f}%",
                     "Sharpe Ratio": f"{(ret.mean() / sd * np.sqrt(252)) if sd else float('nan'):.3f}",
                     "Drawdown": f"{dd:.3f}%", **{k: str(v) for k, v in extra.items()}}}
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")


# --------------------------------------------------------------------------------------- main


#: Clause 3's grid. Fixed before the first number was read.
CELLS = [
    ("base",     dict(decile=0.10),                          "base decile 0.10"),
    ("base",     dict(decile=0.04),                          "base decile 0.04"),
    ("dwell",    dict(decile=0.10, dwell=2),                 "dwell 2 (60 min)"),
    ("dwell",    dict(decile=0.10, dwell=3),                 "dwell 3 (90 min)"),
    ("dwell",    dict(decile=0.10, dwell=6),                 "dwell 6 (3 h)"),
    ("dwell",    dict(decile=0.10, dwell=11),                "dwell 11 (once a day)"),
    ("band",     dict(enter=0.10, exit=0.25),                "band 0.10/0.25"),
    ("band",     dict(enter=0.10, exit=0.40),                "band 0.10/0.40"),
    ("band",     dict(enter=0.04, exit=0.20),                "band 0.04/0.20"),
    ("band",     dict(enter=0.04, exit=0.40),                "band 0.04/0.40"),
    ("ewma",     dict(decile=0.10, lam=0.50),                "ewma 0.50"),
    ("ewma",     dict(decile=0.10, lam=0.25),                "ewma 0.25"),
    ("conv",     dict(decile=0.10, mult=0.5),                "conv 0.5x cost"),
    ("conv",     dict(decile=0.10, mult=1.0),                "conv 1.0x cost"),
    ("conv",     dict(decile=0.10, mult=2.0),                "conv 2.0x cost"),
    ("conv",     dict(decile=0.34, mult=2.0),                "conv 2.0x, wide decile"),
    ("bandconv", dict(enter=0.10, exit=0.40, mult=1.0),      "band 0.10/0.40 + conv 1.0x"),
    ("bandconv", dict(enter=0.10, exit=0.40, mult=2.0),      "band 0.10/0.40 + conv 2.0x"),
    ("band",     dict(enter=0.10, exit=0.40, dwell=2),       "band 0.10/0.40 + dwell 2"),
]


#: Post-hoc power extension (clause 8, added after the pre-registered grid was read - see the
#: journal). The same walk-forward started in 2019 instead of 2024, which multiplies the
#: out-of-sample window by ~2.5x. NOTHING is re-tuned on it: the cells are exactly the ones the
#: pre-registered grid printed, at the parameters it printed them at. Early test years train on
#: less history (the 2019 model sees 2016-2017 only), which biases against the finding.
EXTEND_CELLS = ["base decile 0.10", "dwell 6 (3 h)", "conv 1.0x cost", "conv 2.0x cost",
                "band 0.10/0.40 + conv 2.0x"]


def build_predictions_extended(first_year: int = 2019) -> pd.DataFrame:
    panel = pd.read_parquet(f1.PANEL)
    panel["ts"] = pd.to_datetime(panel["ts"])
    params = dict(f1.GRID["mid"])
    frames = []
    for year in sorted(panel[panel.year >= first_year].year.unique()):
        trn = panel[panel.year <= year - 2]
        vld = panel[panel.year == year - 1]
        tst = panel[panel.year == year]
        t0 = time.time()
        model, pt = f1.fit_predict(trn, vld, tst, dict(params))
        icm, ict = f1.ic_stats(tst, pt)
        keep = tst[["ts", "day", "year", "sym", "entry_px", "fwd", "y"]].copy()
        keep["pred"] = pt
        frames.append(keep)
        print(f"  {year}: train<={year-2} ({len(trn):,}) test ({len(tst):,}) "
              f"iters {model.n_iter_:>4}  IC {icm:+.5f} (t {ict:+.2f})  ({time.time()-t0:.0f}s)")
        sys.stdout.flush()
    out = pd.concat(frames, ignore_index=True)
    out.to_parquet(OUT / "preds_test_ext.parquet", index=False)
    return out


def run_extended(record_rows: bool = False) -> None:
    print("=== clause 8 (POST-HOC power extension): the same walk-forward from 2019 ===")
    p = OUT / "preds_test_ext.parquet"
    test = pd.read_parquet(p) if p.exists() else build_predictions_extended()
    test["ts"] = pd.to_datetime(test["ts"])
    icm, ict = f1.ic_stats(test, test["pred"].to_numpy())
    print(f"\nextended OOS: {len(test):,} rows, {test['day'].nunique()} sessions, "
          f"{int(test['year'].min())}-{int(test['year'].max())}, pooled IC {icm:+.5f} (t {ict:+.2f})\n")
    sl = Slices(test)
    year_of = dict(zip(test["day"], test["year"]))
    lookup = {label: (kind, prm) for kind, prm, label in CELLS}
    rows, sessions = [], {}
    for label in EXTEND_CELLS:
        kind, prm = lookup[label]
        s = simulate(sl, kind, prm)
        r = summarize(s, label)
        r["kind"], r["params"] = kind, prm
        rows.append(r)
        sessions[label] = s
        print_table([r], hdr=(label == EXTEND_CELLS[0]))
        sys.stdout.flush()
    print("\nper test year, net $/day (t):")
    years = sorted({int(y) for y in year_of.values()})
    print(f"  {'cell':<26}" + "".join(f"{y:>16}" for y in years))
    for r in rows:
        s = sessions[r["label"]].assign(year=lambda d: d["day"].map(year_of))
        cells = []
        for y in years:
            n = s.loc[s["year"] == y, "net"].to_numpy()
            cells.append(f"{n.mean():>9,.0f} ({f1.tstat(n):>+4.1f})" if len(n) else " " * 16)
        print(f"  {r['label']:<26}" + "".join(f"{c:>16}" for c in cells))
    print("\n  control (prediction permuted per timestamp):")
    for label in EXTEND_CELLS[-2:]:
        kind, prm = lookup[label]
        print_table([summarize(simulate(sl, kind, prm, scramble=7), f"CTRL {label}"[:26])],
                    hdr=(label == EXTEND_CELLS[-2]))
    print("\n  pre-registered rule on the extended window "
          "(net>0 at t>2 pooled, positive in a majority of test years):")
    for r in rows:
        s = sessions[r["label"]].assign(year=lambda d: d["day"].map(year_of))
        pos = sum(1 for y in years if s.loc[s["year"] == y, "net"].mean() > 0)
        ok = r["net_day"] > 0 and r["t"] > 2 and pos > len(years) / 2
        print(f"    {r['label']:<26} net {r['net_day']:>9,.0f}/day  t {r['t']:>+6.2f}  "
              f"positive years {pos}/{len(years)}  gross {r['gross_bps']:.3f} bps "
              f"({r['mult']:.2f}x)  -> {'PASS' if ok else 'REFUSED'}")
        if record_rows:
            record(f"F-7 DIAGNOSTIC clause 8 power extension: '{r['label']}' on a 2019-2026 "
                   f"walk-forward (1,933 OOS sessions, no re-tuning)", r, sessions[r["label"]],
                   {"features": len(f1.FEATURES), "model": "mid", "hold_min": 30,
                    "rebalance_min": 30, "construction": r["kind"], **r["params"]},
                   {"Regime": "2019-2026", "Positive Years": f"{pos}/{len(years)}",
                    "Verdict": "PASS" if ok else "REFUSED", "IC": f"{icm:.5f}"})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--predict", action="store_true", help="reproduce F-1's walk-forward and cache it")
    ap.add_argument("--importance", action="store_true", help="permutation importance per retrain")
    ap.add_argument("--book", action="store_true", help="the construction sweep on the frozen forecast")
    ap.add_argument("--extend", action="store_true", help="clause 8: the same cells on a 2019-2026 walk-forward")
    ap.add_argument("--record", action="store_true")
    args = ap.parse_args()

    if args.predict or not PRED.exists():
        build_predictions(importance=args.importance)
    if args.extend:
        run_extended(record_rows=args.record)
    if not args.book:
        return

    test = pd.read_parquet(PRED)
    test["ts"] = pd.to_datetime(test["ts"])
    icm, ict = f1.ic_stats(test, test["pred"].to_numpy())
    print(f"frozen forecast: {len(test):,} rows, {test['day'].nunique()} sessions, "
          f"{test['sym'].nunique()} names, pooled IC {icm:+.5f} (t {ict:+.2f})")
    print(f"cost store: {ic.DATA_DIR}  (splits {'loaded' if ic._splits() else 'ABSENT'})")

    sl = Slices(test)
    print(f"{len(sl.slices):,} decision points, "
          f"{np.bincount(sl.k_in_day).tolist()} per slot\n")

    # ---- clause 1: identity against F-1's ledger row
    print("=== clause 1: identity against F-1 ledger row 20260911T155155Z ===")
    base_sess = simulate(sl, "base", dict(decile=0.10))
    base = summarize(base_sess, "base decile 0.10")
    ok = True
    for k, label in (("gross_day", "gross $/day"), ("net_day", "net $/day"),
                     ("turn_day", "turnover/day"), ("gross_bps", "gross bps")):
        got, want = base[k], F1_REF[k]
        tol = max(1.0, abs(want) * 0.005)
        good = abs(got - want) <= tol
        ok &= good
        print(f"  {label:<14} {got:>14,.3f}   F-1 {want:>14,.3f}   "
              f"{'OK' if good else 'MISMATCH'}")
    print(f"  IC             {icm:>14.5f}   F-1 {F1_REF['ic']:>14.5f}")
    if not ok:
        print("\nCLAUSE 1 FAILED - the frozen forecast does not reproduce F-1. "
              "Nothing below is read; fix the reproduction first.")
        if ic.DATA_DIR.name != "minute_alpaca":
            print(f"  first suspect: the store is {ic.DATA_DIR}, which has no "
                  f"{ic.SPLITS_FILE}, so share_scale() is 1.0 everywhere and the commission "
                  f"is charged on split-ADJUSTED share counts. F-1 ran on the Alpaca store; "
                  f"re-run with INTRADAY_DATA_DIR=data/minute_alpaca. The book is identical "
                  f"either way (gross and turnover still match) - only the cost column moves, "
                  f"by ~0.28 bps of turnover.")
        return
    print("  -> identity holds; the forecast below is F-1's, unchanged.\n")

    # ---- clause 2: the mechanism, measured before any construction
    print("=== clause 2: forecast persistence - what a k-interval hold can earn per dollar ===")
    pers = persistence_table(test)
    print(f"{'h':>3} {'minutes':>8} {'IC(h)':>9} {'t':>7} {'IC(h)/IC(1)':>12} {'cum mult':>9}")
    print("-" * 52)
    for _, r in pers.iterrows():
        print(f"{int(r['h']):>3} {int(r['minutes']):>8} {r['ic']:>+9.5f} {r['ic_t']:>+7.2f} "
              f"{r['ic_rel']:>12.3f} {r['cum_mult']:>9.3f}")
    best_k = int(pers["cum_mult"].idxmax()) + 1
    best_mult = float(pers["cum_mult"].max())
    need_comm = FLOOR_COMMISSION / F1_REF["gross_bps"]
    need_ship = FLOOR_SHIPPED / F1_REF["gross_bps"]
    print(f"\n  best cumulative multiple {best_mult:.3f} at k={best_k} "
          f"({30 * best_k} minutes)")
    print(f"  needed to clear commission only ({FLOOR_COMMISSION} bps): {need_comm:.2f}x")
    print(f"  needed to clear shipped cost   ({FLOOR_SHIPPED} bps): {need_ship:.2f}x")
    print(f"  clause 2 prediction: dwell/band constructions "
          f"{'CAN' if best_mult >= need_ship else 'CANNOT'} clear the shipped cost.\n")

    # ---- clause 3 + 4: the constructions and their scrambled controls
    print("=== clause 3: constructions on the frozen forecast (pooled 2024-2026) ===")
    rows, sessions = [], {}
    for kind, p, label in CELLS:
        t0 = time.time()
        s = simulate(sl, kind, p)
        r = summarize(s, label)
        r["kind"], r["params"] = kind, p
        rows.append(r)
        sessions[label] = s
        print_table([r], hdr=(label == CELLS[0][2]))
        sys.stdout.flush()
        del t0
    print()

    best_rows = sorted(rows, key=lambda r: -r["gross_bps"])[:4]
    print("=== clause 4: control - identical construction, prediction permuted per timestamp ===")
    ctrl_rows = []
    for r in best_rows + [rows[0]]:
        c = summarize(simulate(sl, r["kind"], r["params"], scramble=7),
                      f"CTRL {r['label']}"[:26])
        c["kind"], c["params"] = r["kind"], r["params"]
        ctrl_rows.append(c)
    print_table(ctrl_rows)
    print()

    # ---- clause 6: regimes, on the best construction and on the base book
    print("=== clause 6: by regime (test year, and causal SPY trailing-vol tercile) ===")
    reg = vol_regime(test["day"].to_numpy())
    year_of = dict(zip(test["day"], test["year"]))
    show = [rows[0], best_rows[0]]
    if best_rows[0]["label"] != best_rows[1]["label"]:
        show.append(best_rows[1])
    for r in show:
        s = sessions[r["label"]]
        s = s.assign(year=s["day"].map(year_of), regime=s["day"].map(reg))
        sub = []
        for y in sorted(s["year"].dropna().unique()):
            sub.append(summarize(s[s["year"] == y], f"  {r['label'][:16]} {int(y)}"[:26]))
        for g in ("low vol", "mid vol", "high vol"):
            m = s["regime"] == g
            if m.any():
                sub.append(summarize(s[m], f"  {r['label'][:14]} {g}"[:26]))
        print_table([r] + sub)
        print()

    # ---- clause 7: the pre-registered verdict
    print("=== clause 7: pre-registered pass rule (net>0 at t>2 pooled, positive in >=2 of 3 years) ===")
    verdicts = []
    for r in rows:
        s = sessions[r["label"]].assign(year=lambda d: d["day"].map(year_of))
        pos = sum(1 for y in sorted(s["year"].dropna().unique())
                  if s.loc[s["year"] == y, "net"].mean() > 0)
        ok = r["net_day"] > 0 and r["t"] > 2 and pos >= 2
        verdicts.append((r, pos, ok))
        print(f"  {r['label']:<26} net {r['net_day']:>9,.0f}/day  t {r['t']:>+6.2f}  "
              f"positive years {pos}/3  gross {r['gross_bps']:.3f} bps "
              f"({r['mult']:.2f}x, floor {FLOOR_SHIPPED})  -> {'PASS' if ok else 'REFUSED'}")
    n_pass = sum(1 for _, _, ok in verdicts if ok)
    print(f"\nVERDICT: {n_pass} of {len(verdicts)} cells pass. "
          f"Best gross bps per dollar turned: {best_rows[0]['gross_bps']:.3f} "
          f"({best_rows[0]['label']}), {best_rows[0]['mult']:.2f}x F-1, "
          f"against floors {FLOOR_COMMISSION} (commission) and {FLOOR_SHIPPED} (shipped).")

    if args.record:
        base_params = {"features": len(f1.FEATURES), "model": "mid", "hold_min": 30,
                       "rebalance_min": 30, "source": "F-1 frozen walk-forward predictions"}
        for r, pos, ok in verdicts:
            record(f"F-7 DIAGNOSTIC construction '{r['label']}' on F-1's frozen forecast "
                   f"(pooled OOS 2024-2026)", r, sessions[r["label"]],
                   {**base_params, "construction": r["kind"], **r["params"]},
                   {"Regime": "2024-2026", "Positive Years": f"{pos}/3",
                    "Verdict": "PASS" if ok else "REFUSED", "IC": f"{icm:.5f}"})
        for c in ctrl_rows:
            record(f"F-7 DIAGNOSTIC control: '{c['label']}' with the prediction permuted "
                   f"inside each decision point", c,
                   simulate(sl, c["kind"], c["params"], scramble=7),
                   {**base_params, "construction": c["kind"], "scramble": 7, **c["params"]},
                   {"Regime": "2024-2026", "Verdict": "CONTROL"})
        print(f"\nrecorded {len(verdicts) + len(ctrl_rows)} DIAGNOSTIC rows in {LEDGER}")
        pers.to_csv(OUT / "f7_persistence.csv", index=False)
        print(f"persistence table -> {OUT / 'f7_persistence.csv'}")


if __name__ == "__main__":
    main()
