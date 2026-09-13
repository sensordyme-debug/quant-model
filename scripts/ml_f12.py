"""F-12: every F run so far forecast the numerator. Forecast the denominator instead.

The F track closed on F-11 with a standing sentence: *"reopening the supervised class needs a
new mechanism - a different instrument, a different frequency, or a different label family -
not another construction on this one."* F-12 is the third of those. It is the first F iteration
that **fits a new model on a new label**, and the first that acts on the book's **sd** rather
than its mean.

**Why risk, and why now.** Three separate F runs have reported the same incidental fact about
this feature set and none has acted on it: *the only family of features that survives a retrain
is the volatility family.* F-11 section (10) put numbers on it - over 8 test years, mean pairwise
Spearman of the yearly importance rankings +0.434, no feature in the top 10 of every year, and
the four that come closest are `vol_rel6` (rank mean 6.8), `m_rvol_ratio` (7.5), `rvol_ratio`
(7.9) and `cs_rvol_ratio` (10.1). A model asked to forecast direction keeps reaching for the
volatility features, which is what a model does when the thing it can actually resolve is not
the thing it was asked for. The signed cross-sectional return has an IC of ~+0.02; the
*magnitude* of an intraday move is one of the most forecastable objects in finance.

**And the book has never used it.** t = mean / se. F-7 moved the book, F-8 the label, F-10 the
breadth, F-11 the cost - all of them the numerator of the P&L, none of them the denominator of
the t. F-8's session book equal-weights its decile legs at gross/(2k), which is the allocation
that is correct only if every name carries the same risk. On this universe it does not come
close: the panel holds SOXS, SOXL and TQQQ-class leveraged sleeves next to LLY, COST and TMO,
and a 3x semiconductor ETF's session move is several times a mega-cap pharma's. Equal dollars
across that is a book whose variance is dominated by four names.

**The construction.** A second supervised model, same 38 causal features, same walk-forward,
same learner, **new label**: `|y_close|`, the absolute demeaned cumulative return from the
decision to the 15:30 flatten. That is exactly the per-name risk contribution of a
dollar-neutral book (the book's P&L is invariant to a common additive shift, so the
idiosyncratic magnitude is the right object). Its prediction, `sigma_hat`, is then used in two
places that no F run has touched:

    sizing:    w_i = (gross/2) * sigma_i^-p / sum_side(sigma_j^-p)      p in {0, 0.5, 1, 2}
    selection: score_i = pred_i / sigma_hat_i                            (information ratio)

p = 0 is F-8 exactly. **p = 1 is the primary cell and it needs no tuning**: with uncorrelated
names the optimal weight is alpha_i / sigma_i^2, so p = 1 is optimal when alpha scales with
vol and p = 2 when alpha is constant across names, and those two bracket every plausible
view. The ladder spans both; the decision reads p = 1.

**The one thing that is guaranteed:** turnover is *identical* at every p. Each side sums to
gross/2 on entry and to zero at the flatten regardless of how the dollars are split inside it,
so the ladder holds F-8's $1,995,861/day exactly and every bps column is like-for-like. There
is no turnover confound in this file.

    python scripts/ml_f12.py --fit                # walk-forward risk model -> f12_risk.parquet
    python scripts/ml_f12.py --books              # the sizing ladder, IR rank, controls, decision
    python scripts/ml_f12.py --books --record     # ... and append DIAGNOSTIC rows to the ledger
    python scripts/ml_f12.py --importance         # risk-model feature stability vs the return model

**Run it with `INTRADAY_DATA_DIR=data/minute_alpaca`** (F-7's documented cost hazard:
`_splits.json` lives only in that store and without it the cost line is understated by ~0.06
bps of turnover). Run it as `py -3.14` - only 3.14 has `pyarrow` on this machine.

--------------------------------------------------------------------------------------------
PRE-REGISTERED - written in full before any F-12 number was read
--------------------------------------------------------------------------------------------

**Clause 0 - the prior, stated out loud.** Two things are expected and one is not. (a) The risk
model will forecast well - a rank IC on `|y_close|` of **+0.25 to +0.45**, an order of magnitude
above the return model's +0.02 - and its feature importance will be **much more stable** than
the return model's +0.434 Spearman, because it is being asked for the thing the features
describe. (b) Inverse-vol sizing will cut the book's sd, by **10-25%**. (c) The part that is a
genuine experiment: **what it does to the mean.** If the forecast's alpha is concentrated in
exactly the high-vol names the lever de-weights, the mean falls by as much as the sd and t does
not move. The honest prior is that it moves a little and not enough: **sd down ~15%, mean down
~10%, t from +1.47 to roughly +1.6, refused on clause 5** - the same shape as F-11. What would
be genuinely new, and is not expected, is the mean holding flat while the sd falls.

There is one analytic floor worth stating, because it is the reason this is worth a run at all.
If alpha_i is proportional to sigma_i - the pessimistic case above, where the forecast's edge
lives entirely in the volatile names - then the equal-weight book's information ratio is
sum(sigma) / sqrt(sum sigma^2) and the inverse-vol book's is sqrt(k), and by Cauchy-Schwarz the
second is **always at least the first**, with equality only when every sigma is identical. So on
the pessimistic assumption the lever is weakly positive; it can only lose if alpha rises with
vol *faster than linearly*. The experiment is asking which side of linear this panel sits on.

**Clause 1 - what is frozen, and what is new.** New: one model, on the label `|y_close|`, fitted
by the same `sweep_f1.fit_predict` with the same `GRID["mid"]` hyper-parameters, the same 38
features, the same expanding walk-forward (train <= year-2, validate year-1, test year), the
same 8 test years. **Nothing else moves.** The alpha predictions are re-read frozen from
`data/f1/f8_preds.parquet`; no return model is re-fitted, no feature is added, no
hyper-parameter is tuned on anything. Book: F-8's winning cell - label `close`, `session` book
(one decision at slot 0, fill 10:00, held to the 15:30 flatten), decile 0.10, gross 1.0, equity
$1M, flat overnight, 2019-2026. **The p = 0 cell must reproduce F-8's published numbers (gross
4.256, cost 2.724, net $305.7/day, t +1.474) or the run is void.**

**Clause 2 - strict causality, and the eligible set is shared.** `sigma_hat` for a session is
produced by a model whose training data ends two calendar years earlier and whose features are
the same causal ones F-1 built; no session's size is set by anything dated after its own
decision minute. A name is eligible only if it has a finite prediction, a finite entry price, an
unbroken forward chain to the flatten **and** a finite `sigma_hat` - the *same* eligible set for
every cell in the file, so no cell can win by trading a different universe. If that changes the
p = 0 cell at all, clause 1 catches it and the run is void.

**Clause 3 - the cells.**
  (a) **the sizing ladder** p in {0, 0.5, 1, 2} on `sigma_hat`. **p = 0 is the identity and
      p = 1 is the primary cell**; the rest are sensitivity. A monotone fall in the book's sd is
      the minimum sign that the lever does what it is built to do.
  (b) **the free baseline**: the same ladder on `atr` - the panel's own causal 20-bar mean of
      (high-low)/close, available to any desk for nothing. **The ML risk model must beat this or
      it is not an ML result**, only a re-derivation of trailing range. Reported at p = 1.
  (c) **the selection channel**: rank on `pred / sigma_hat` instead of `pred` at p = 0, and the
      same at p = 1. This changes *which* names are held rather than how much of each, and is
      the denominator's analogue of F-11's net-alpha ranking.
  (d) **the overlap test with F-11**: p = 1 layered on F-11's lambda = 1 net-alpha ranking. Low
      vol and high price are correlated on this universe, so an inverse-vol book tilts toward
      cheap-to-trade names on its own. If the two levers combined are worth no more than either
      alone, they are one lever wearing two hats and the file must say so.
  (e) **a concentration cap** at p = 2 (no name above 3x its equal-weight share, renormalized),
      because p = 2 on a 3:1 vol spread can put a third of a side in one name.

**Clause 4 - two controls, both coded as gates.**
  (i) **Scrambled alpha, real sizing.** Per-timestamp permuted `pred`, 3 seeds, at p = 1. The
      zero-forecast book's gross must stay indistinguishable from zero. If inverse-vol sizing
      earns gross with no forecast at all, the lever is a static tilt toward low-vol names and
      not an improvement to this book. Failing this voids the decision.
  (ii) **Scrambled sigma, real alpha.** Per-timestamp permuted `sigma_hat`, 3 seeds, at p = 1:
      the same weight *dispersion*, assigned to the wrong names. This is the control that
      matters, because it separates "sizing unequally helps" from "sizing by this forecast
      helps". The real cell must beat the scrambled-sigma cell's mean t by more than that
      cell's own seed spread. Failing this voids the *explanation* and the cell is reported as
      unexplained dispersion rather than as a risk forecast.

**Clause 5 - the decision rule, fixed before the numbers, and it is F-8's own.** Read on the
**p = 1, `sigma_hat`, uncapped cell only**:
  - **PASS** iff pooled **t > 2.0** and **>= 5 of 8 test years net positive**. A pass reopens
    the F track as a paper-deploy candidate and owes a fresh harness run, not a deployment.
  - **REFUSE** otherwise.
  The p or cell that maximises t is reported but **may not be read as the result** - it is
  selected on the same sessions it is scored on.

**Clause 6 - the decomposition, and F-11's paired rule, which is now standing.** (a) Every
change in t is split into its mean channel and its sd channel before it is believed. (b) Any
comparison between two cells is run **paired on the shared sessions**, never as two separately
noisy t's side by side - F-11's finding was that a t of +1.47 against +1.88 was a paired
improvement of t +0.70. Both are coded here, not remarked.

**Clause 7 - what F-12 does not claim.** (a) It does not touch the *training* channel: the
return model is still F-8's, fitted on all 56 names with no knowledge of the risk forecast. (b)
It does not re-time the book - the risk forecast is used cross-sectionally within a session,
never to scale the book's gross across sessions, because F-8's regime table shows the dead
regime is the low-vol one and a vol-targeting overlay would size *into* it. That is a separate
hypothesis and it is not tested here. (c) Nothing deploys from this file:
`algorithms/intraday/active/signal.py` and `live/intraday_config.json` are not touched, so no
deploy gate and no `--replay` is owed.

**Clause 8 - what happens to the track afterwards, decided now.** A refusal closes the *label
family* axis alongside the other five, and the honest reading then becomes that this feature
set on this panel does not support a t = 2 book by any construction - at which point the F
track's remaining reopening is a different instrument or a different frequency, neither of
which is in this scope. A pass produces a harness request and a journal entry, not a
deployment.
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
import ml_f7 as f7  # noqa: E402
import ml_f8 as f8  # noqa: E402
import ml_f11 as f11  # noqa: E402

LEDGER = REPO / "research" / "experiments.jsonl"
OUT = REPO / "data" / "f1"
RISK = OUT / "f12_risk.parquet"
IMP = OUT / "importance_f12.csv"
CELLS_CSV = OUT / "f12_risksize.csv"

LABEL = "close"                       # clause 1
EQUITY = f8.EQUITY
N_SLOTS = f8.N_SLOTS
DECILE = f8.DECILE
POWERS = [0.0, 0.5, 1.0, 2.0]         # clause 3(a)
CTRL_SEEDS = 3                        # clause 4
CAP = 3.0                             # clause 3(e): 3x the equal-weight share
SIGMA_FLOOR_BPS = 1.0                 # a predicted risk below 1 bp is a model artifact

F8_CELL = {"gross_bps": 4.256, "cost_bps": 2.724, "net_day": 305.7, "t": 1.474}
TARGET_T = 2.0                        # clause 5, inherited from F-8 clause 7
MIN_YEARS = 5                         # clause 5, inherited from F-8 clause 7


# --------------------------------------------------------------------- the risk model (clause 1)


def build_risk(importance: bool = False) -> pd.DataFrame:
    """Walk-forward fit of `|y_close|`, the new label family. Frozen to `f12_risk.parquet`.

    Identical machinery to F-8 in every respect except the label: same 38 features, same
    `GRID["mid"]` learner, same expanding train <= year-2 / validate year-1 / test year split,
    same 8 test years. The label is the absolute value of F-8's own `y_close`, which is the
    per-name risk contribution of a dollar-neutral book.
    """
    panel = pd.read_parquet(f1.PANEL)
    p = f8.add_labels(panel)
    del panel
    p = p.dropna(subset=["y_close"]).copy()
    p["y"] = p["y_close"].abs().astype("float32")
    params = dict(f1.GRID["mid"])
    years = [y for y in sorted(p["year"].unique()) if y >= f8.FIRST_TEST_YEAR]
    print(f"panel {len(p):,} rows, {p['sym'].nunique()} symbols, {p['day'].nunique():,} sessions")
    print(f"label |y_close|: mean {1e4 * p['y'].mean():.1f} bps, "
          f"median {1e4 * p['y'].median():.1f}, p95 {1e4 * p['y'].quantile(0.95):.1f}")
    print(f"learner 'mid' {params}; test years {years}")

    frames, models = [], {}
    for year in years:
        trn = p[p.year <= year - 2]
        vld = p[p.year == year - 1]
        tst = p[p.year == year]
        if not (len(trn) and len(vld) and len(tst)):
            continue
        t0 = time.time()
        model, pt = f1.fit_predict(trn, vld, tst, dict(params))
        icm, ict = f1.ic_stats(tst, pt)
        # the level fit, which the sizing actually consumes: R^2 across all test rows
        yt = tst["y"].to_numpy() * 1e4
        r2 = 1.0 - float(((yt - pt) ** 2).sum() / ((yt - yt.mean()) ** 2).sum())
        keep = tst[["ts", "day", "year", "sym", "slot"]].copy()
        keep["sigma"] = pt
        frames.append(keep)
        models[int(year)] = (model, vld)
        print(f"  {year}: train<={year-2} ({len(trn):,}) valid {year-1} ({len(vld):,}) "
              f"test ({len(tst):,}) iters {model.n_iter_:>4}  rank IC {icm:+.4f} "
              f"(t {ict:+.1f})  R2 {r2:+.4f}  ({time.time()-t0:.0f}s)")

    out = pd.concat(frames, ignore_index=True)
    OUT.mkdir(parents=True, exist_ok=True)
    out.to_parquet(RISK, index=False)
    print(f"\nfrozen: {len(out):,} rows -> {RISK}")
    print(f"sigma_hat over the test window: min {out['sigma'].min():.2f}, "
          f"median {out['sigma'].median():.2f}, p95 {out['sigma'].quantile(0.95):.2f}, "
          f"max {out['sigma'].max():.2f} bps; "
          f"non-positive {int((out['sigma'] <= 0).sum()):,}")

    if importance and models:
        _importance(models)
    return out


def _importance(models: dict) -> None:
    """Clause 3 of the job brief: is the *risk* model's feature ranking stable?"""
    from sklearn.inspection import permutation_importance
    print("\n=== permutation importance, label |y_close|, on each retrain's validation year ===")
    imps = {}
    for year, (model, vld) in sorted(models.items()):
        s = vld.sample(min(120_000, len(vld)), random_state=0)
        r = permutation_importance(model, s[f1.FEATURES].to_numpy(dtype=np.float32),
                                   s["y"].to_numpy(), n_repeats=3, random_state=0,
                                   scoring="neg_mean_squared_error", n_jobs=1)
        imps[year] = pd.Series(r.importances_mean, index=f1.FEATURES)
        print(f"  {year} done")
    imp = pd.DataFrame(imps)
    imp["rank_mean"] = imp.rank(ascending=False).mean(axis=1)
    imp = imp.sort_values("rank_mean")
    imp.to_csv(IMP)
    print(imp.head(15).to_string(float_format=lambda x: f"{x: .3e}"))
    print(f"importance -> {IMP}")


# ------------------------------------------------------------------------------- the allocation


def resize(w: np.ndarray, sigma: np.ndarray, p: float, gross: float = 1.0,
           cap: float = 0.0) -> tuple[np.ndarray, int]:
    """Re-split each side's gross/2 across the names the selector chose, in proportion to
    sigma^-p. p = 0 returns `w` untouched, so the identity cell is exact by construction.

    Turnover is unaffected at every p: each side still sums to gross/2 on entry and to zero at
    the flatten, so the ladder is like-for-like in every bps column (the docstring's one
    guarantee). What does change is *which* names carry the dollars, so the cost column moves.
    """
    if p == 0.0:
        return w, 0
    out = np.zeros_like(w)
    capped = 0
    for sgn in (1.0, -1.0):
        sel = np.flatnonzero(np.sign(w) == sgn)
        if len(sel) == 0:
            continue
        s = sigma[sel]
        if not np.isfinite(s).all() or (s <= 0).any():
            out[sel] = w[sel]           # clause 2 makes this unreachable; fail safe, not silent
            continue
        u = s ** (-p)
        u = u / u.sum()
        if cap > 0:
            lim = cap / len(sel)
            capped += int((u > lim).sum())
            u = np.minimum(u, lim)
            u = u / u.sum()
        out[sel] = sgn * gross / 2.0 * u
    return out, capped


def _day_matrices(g: pd.DataFrame, syms: np.ndarray):
    n = len(syms)
    pos = {s: i for i, s in enumerate(syms)}
    P = np.full((N_SLOTS, n), np.nan)
    F = np.full((N_SLOTS, n), np.nan)
    X = np.full((N_SLOTS, n), np.nan)
    S = np.full(n, np.nan)          # sigma_hat at slot 0
    A = np.full(n, np.nan)          # atr at slot 0, the free baseline
    C = np.full(n, np.nan)          # F-11's round-trip cost estimate
    for k, sym, pr, fw, px, sg, at, cb in zip(
            g["slot"].to_numpy(), g["sym"].to_numpy(), g["pred"].to_numpy(float),
            g["fwd"].to_numpy(float), g["entry_px"].to_numpy(float),
            g["sigma"].to_numpy(float), g["atr"].to_numpy(float), g["c_bps"].to_numpy(float)):
        j = pos[sym]
        P[k, j], F[k, j], X[k, j] = pr, fw, px
        if k == 0:
            S[j], A[j], C[j] = sg, at, cb
    return P, F, X, S, A, C


def simulate(frame: pd.DataFrame, p: float = 0.0, risk: str = "ml", rank: str = "alpha",
             lam: float = 0.0, cap: float = 0.0, decile: float = DECILE, gross: float = 1.0,
             scramble_pred: int | None = None, scramble_sigma: int | None = None) -> pd.DataFrame:
    """F-8's `session` book with risk-based sizing. One row per session.

    `risk`: "ml" = `sigma_hat`, "atr" = the free trailing-range baseline (clause 3(b)).
    `rank`: "alpha" = F-8's decile on `pred`, "ir" = decile on `pred / sigma_hat` (clause 3(c)),
            "net" = F-11's two-sided net-alpha selection at `lam` (clause 3(d)).
    P&L, turnover and cost accounting are F-8's, unchanged and per fill.
    """
    rp = np.random.default_rng(scramble_pred) if scramble_pred is not None else None
    rs = np.random.default_rng(scramble_sigma) if scramble_sigma is not None else None
    rows = []
    for day, g in frame.groupby("day", sort=True):
        syms = np.unique(g["sym"].to_numpy())
        P, F, X, S, A, C = _day_matrices(g, syms)
        if rp is not None:
            for k in range(N_SLOTS):
                m = np.isfinite(P[k])
                if m.sum() > 1:
                    P[k, m] = rp.permutation(P[k, m])

        # clause 2: one eligible set for every cell in the file
        ok = np.isfinite(P[0]) & np.isfinite(X[0]) & np.isfinite(S) & np.isfinite(A) & np.isfinite(C)
        for j in range(N_SLOTS):
            ok &= np.isfinite(F[j])

        sig = np.where(risk == "atr", A, np.maximum(S, SIGMA_FLOOR_BPS))
        if rs is not None:
            m = ok & np.isfinite(sig)
            if m.sum() > 1:
                sig = sig.copy()
                sig[m] = rs.permutation(sig[m])

        if rank == "ir":
            score = P[0] / np.where(np.isfinite(sig) & (sig > 0), sig, np.nan)
            w = f8._decile(score, ok & np.isfinite(score), decile, gross)
        elif rank == "net":
            w = f11.select(P[0], C, ok, decile, gross, lam, False, greedy=True)
        else:
            w = f8._decile(P[0], ok, decile, gross)
        w, capped = resize(w, sig, p, gross, cap)

        W = np.zeros((N_SLOTS, len(syms)))
        if w.any():
            W[0:N_SLOTS] += w

        fwd0 = np.where(np.isfinite(F), F, 0.0)
        pnl = float((W * np.expm1(fwd0)).sum() * EQUITY)

        turn = 0.0
        cost = 0.0
        prev = np.zeros(len(syms))
        for k in range(N_SLOTS + 1):
            cur = W[k] if k < N_SLOTS else np.zeros(len(syms))
            px = X[min(k, N_SLOTS - 1)]
            dw = cur - prev
            m = np.abs(dw) > 1e-12
            if m.any():
                notional = np.abs(dw[m]) * EQUITY
                turn += float(notional.sum())
                for s, d, q, nt in zip(syms[m], dw[m], px[m], notional):
                    if not np.isfinite(q) or q <= 0:
                        continue
                    sh = np.sign(d) * nt / q
                    cost += ic.commission(sh, float(q), f8.f7_scale(s, day)) + ic.slippage(sh, float(q))
            prev = cur
        # effective breadth: 1 / sum(u^2) over the entry weights, the number of equally-sized
        # names this book is really holding. Equal weight makes it equal `names`.
        aw = np.abs(W[0])
        hhi = float((aw ** 2).sum())
        rows.append({"day": day, "gross": pnl, "cost": cost, "turnover": turn,
                     "names": int((aw > 1e-12).sum()),
                     "eff_n": (float(aw.sum()) ** 2 / hhi) if hhi > 0 else 0.0,
                     "capped": capped})

    sess = pd.DataFrame(rows)
    sess["net"] = sess["gross"] - sess["cost"]
    return sess


def summarize(sess: pd.DataFrame, label: str) -> dict:
    r = f8.summarize(sess, label)
    r["names"] = float(sess["names"].mean())
    r["eff_n"] = float(sess["eff_n"].mean())
    r["sd"] = float(sess["net"].to_numpy().std(ddof=1))
    return r


HDR = (f"{'cell':<24} {'sess':>5} {'nm':>4} {'effN':>5} {'gr bps':>7} {'cost bps':>8} "
       f"{'edge':>7} {'turn/day':>10} {'$/day':>8} {'t':>6} {'sd':>7} {'worst':>9} {'win':>5}")


def line(r: dict) -> str:
    return (f"{r['label']:<24} {r['sessions']:>5} {r['names']:>4.1f} {r['eff_n']:>5.1f} "
            f"{r['gross_bps']:>7.3f} {r['cost_bps']:>8.3f} {r['edge_bps']:>7.3f} "
            f"{r['turn_day']:>10,.0f} {r['net_day']:>8,.0f} {r['t']:>+6.2f} {r['sd']:>7,.0f} "
            f"{r['worst']:>9,.0f} {100 * r['win']:>4.0f}%")


# ----------------------------------------------------------------------------------- the frame


def load_frame() -> pd.DataFrame:
    """F-8's `close` simulation frame, with `sigma_hat`, `atr` and F-11's cost estimate merged on."""
    frame = f11.add_cost(f8.load_frames()[LABEL])
    risk = pd.read_parquet(RISK)
    risk["ts"] = pd.to_datetime(risk["ts"])
    frame = frame.merge(risk[["ts", "sym", "sigma"]], on=["ts", "sym"], how="left")
    atr = pd.read_parquet(f1.PANEL, columns=["ts", "sym", "year", "atr"])
    atr["ts"] = pd.to_datetime(atr["ts"])
    atr = atr[atr["year"] >= f8.FIRST_TEST_YEAR]
    frame = frame.merge(atr[["ts", "sym", "atr"]], on=["ts", "sym"], how="left")
    return frame


def by_year(sess: pd.DataFrame) -> pd.Series:
    y = pd.Series(pd.to_datetime(sess["day"]).dt.year.to_numpy(), index=sess.index)
    return sess.groupby(y)["net"].mean().round(0)


def paired(a: pd.DataFrame, b: pd.DataFrame, name: str) -> None:
    """Clause 6(b): the comparison is paired on the shared sessions, never two t's side by side."""
    assert (a["day"].to_numpy() == b["day"].to_numpy()).all()
    d = b["net"].to_numpy() - a["net"].to_numpy()
    dc = a["cost"].to_numpy() - b["cost"].to_numpy()
    dg = b["gross"].to_numpy() - a["gross"].to_numpy()
    print(f"{name:<28} net {d.mean():>+8,.0f} (t {f1.tstat(d):>+5.2f}, "
          f"{100 * (d > 0).mean():>3.0f}% of sessions)   "
          f"gross {dg.mean():>+8,.0f} (t {f1.tstat(dg):>+5.2f})   "
          f"cost {dc.mean():>+7,.0f} (t {f1.tstat(dc):>+6.2f})")


def record(tag: str, r: dict, sess: pd.DataFrame, params: dict, extra: dict) -> None:
    net = sess["net"].to_numpy()
    n = len(sess)
    ret = net / EQUITY
    sd = ret.std(ddof=1) if n > 1 else 0.0
    rec = {"ts": dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
           "algorithm": "intraday/f12_risksize", "class": "ml", "tag": tag, "commit": "",
           "run_dir": "", "track": "F-12", "params": params,
           "start": str(sess["day"].min()), "end": str(sess["day"].max()),
           "stats": {"Sessions": str(n),
                     "Avg Daily PnL": f"{net.mean():.0f}",
                     "t": f"{f1.tstat(net):.2f}",
                     "Gross Per Day": f"{sess['gross'].mean():.0f}",
                     "Costs Per Day": f"{sess['cost'].mean():.0f}",
                     "Turnover Per Day": f"{sess['turnover'].mean():.0f}",
                     "Gross Bps Per Turnover": f"{r['gross_bps']:.3f}",
                     "Cost Bps Per Turnover": f"{r['cost_bps']:.3f}",
                     "Edge Bps Per Turnover": f"{r['edge_bps']:.3f}",
                     "Names Held": f"{r['names']:.1f}",
                     "Effective Names": f"{r['eff_n']:.1f}",
                     "Daily SD": f"{r['sd']:.0f}",
                     "Worst Day": f"{net.min():.0f}",
                     "Win Rate": f"{100 * (net > 0).mean():.0f}%",
                     "Sharpe Ratio": f"{(ret.mean() / sd * np.sqrt(252)) if sd else float('nan'):.3f}",
                     "Diagnostic": "true",
                     **{k: str(v) for k, v in extra.items()}}}
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, default=str) + "\n")


# --------------------------------------------------------------------------------------- main


def run_books(record_rows: bool = False) -> None:
    t_start = time.time()
    print(f"cost store: {ic.DATA_DIR}  (slippage {ic.SLIPPAGE_BPS} bps; "
          f"splits file present: {(Path(ic.DATA_DIR) / '_splits.json').exists()})")
    frame = load_frame()
    sub = frame[frame["slot"] == 0]
    per = sub.groupby("sym")["sigma"].median().sort_values()
    print(f"\nsigma_hat (predicted |move to flatten|) at slot 0, median by name: "
          f"{per.iloc[0]:.1f} ({per.index[0]}) to {per.iloc[-1]:.1f} ({per.index[-1]}) bps, "
          f"universe median {per.median():.1f} - a {per.iloc[-1] / per.iloc[0]:.1f}x spread")
    print("  quietest 5:", ", ".join(f"{s} {v:.0f}" for s, v in per.head(5).items()))
    print("  loudest  5:", ", ".join(f"{s} {v:.0f}" for s, v in per.tail(5)[::-1].items()))
    rho = sub[["sigma", "atr", "c_bps"]].corr(method="spearman")
    print(f"  Spearman: sigma_hat vs atr {rho.loc['sigma', 'atr']:+.3f}, "
          f"sigma_hat vs round-trip cost {rho.loc['sigma', 'c_bps']:+.3f} "
          f"(clause 3(d): the overlap with F-11)")

    rows: list[dict] = []
    keep: dict[str, pd.DataFrame] = {}

    def cell(name: str, label: str, **kw) -> dict:
        sess = simulate(frame, **kw)
        r = summarize(sess, label)
        r.update(cell=name, p=kw.get("p", 0.0), risk=kw.get("risk", "ml"),
                 rank=kw.get("rank", "alpha"), cap=kw.get("cap", 0.0), kind="real")
        rows.append(r)
        keep[name] = sess
        print(line(r))
        return r

    print("\n=== clause 3(a): the sizing ladder on sigma_hat ===")
    print(HDR)
    for p in POWERS:
        cell(f"p{p:g}", f"p = {p:g}", p=p, risk="ml")

    print("\n=== clause 3(b): the free baseline - the same ladder on trailing ATR ===")
    print(HDR)
    for p in [0.5, 1.0, 2.0]:
        cell(f"atr_p{p:g}", f"atr p = {p:g}", p=p, risk="atr")

    print("\n=== clause 3(c)/(d)/(e): selection, the F-11 overlap, and the cap ===")
    print(HDR)
    cell("ir_p0", "IR rank, p = 0", p=0.0, rank="ir")
    cell("ir_p1", "IR rank, p = 1", p=1.0, rank="ir")
    cell("net_p0", "F-11 lam=1, p = 0", p=0.0, rank="net", lam=1.0)
    cell("net_p1", "F-11 lam=1, p = 1", p=1.0, rank="net", lam=1.0)
    cell("p2_cap", f"p = 2, cap {CAP:g}x", p=2.0, cap=CAP)

    # ---- clause 1: the identity check, as a gate, before anything is read
    base = next(r for r in rows if r["cell"] == "p0")
    ok_identity = (abs(base["gross_bps"] - F8_CELL["gross_bps"]) < 0.002
                   and abs(base["cost_bps"] - F8_CELL["cost_bps"]) < 0.002
                   and abs(base["net_day"] - F8_CELL["net_day"]) < 1.0
                   and abs(base["t"] - F8_CELL["t"]) < 0.01)
    print(f"\nclause 1 identity vs F-8: gross {base['gross_bps']:.3f}/{F8_CELL['gross_bps']}, "
          f"cost {base['cost_bps']:.3f}/{F8_CELL['cost_bps']}, "
          f"net {base['net_day']:.1f}/{F8_CELL['net_day']}, t {base['t']:.3f}/{F8_CELL['t']}"
          f"  -> {'OK' if ok_identity else 'VOID'}")
    if not ok_identity:
        print("!! clause 1 fails: the frozen cell does not reproduce. The run is void.")
        return
    turns = {r["cell"]: r["turn_day"] for r in rows}
    spread = max(turns.values()) - min(turns.values())
    print(f"turnover across every sizing cell: {min(turns.values()):,.0f} - "
          f"{max(turns.values()):,.0f} /day (spread ${spread:,.0f}); the ladder is like-for-like "
          f"in every bps column by construction")

    # ---- clause 4: the two controls, coded as gates
    print("\n=== clause 4(i): scrambled ALPHA, real inverse-vol sizing (3 seeds, p = 1) ===")
    print(HDR)
    ca = []
    for s in range(CTRL_SEEDS):
        sess = simulate(frame, p=1.0, scramble_pred=8100 + s)
        r = summarize(sess, f"ctrl alpha s{s}")
        r.update(cell=f"ctrl_alpha_s{s}", p=1.0, risk="ml", rank="alpha", cap=0.0, kind="control")
        rows.append(r)
        keep[r["cell"]] = sess
        ca.append(r)
        print(line(r))

    print("\n=== clause 4(ii): scrambled SIGMA, real alpha (3 seeds, p = 1) ===")
    print("  same weight dispersion, assigned to the wrong names - the control that separates")
    print("  'sizing unequally helps' from 'sizing by this forecast helps'")
    print(HDR)
    cs = []
    for s in range(CTRL_SEEDS):
        sess = simulate(frame, p=1.0, scramble_sigma=8200 + s)
        r = summarize(sess, f"ctrl sigma s{s}")
        r.update(cell=f"ctrl_sigma_s{s}", p=1.0, risk="ml", rank="alpha", cap=0.0, kind="control")
        rows.append(r)
        keep[r["cell"]] = sess
        cs.append(r)
        print(line(r))

    prim = next(r for r in rows if r["cell"] == "p1")
    ctrl_gross_t = float(np.mean([r["gross_t"] for r in ca]))
    gate_i = abs(ctrl_gross_t) < 2.0
    cs_t = np.array([r["t"] for r in cs])
    gate_ii = prim["t"] > cs_t.mean() + cs_t.std(ddof=1)
    print(f"\nclause 4(i)  zero-forecast gross under inverse-vol sizing: mean t "
          f"{ctrl_gross_t:+.2f} -> {'PASS' if gate_i else 'FAIL - the decision is void'}")
    print(f"clause 4(ii) real p=1 t {prim['t']:+.3f} vs scrambled-sigma t "
          f"{cs_t.mean():+.3f} +/- {cs_t.std(ddof=1):.3f} -> "
          f"{'PASS, the sizing is the forecast' if gate_ii else 'FAIL - unexplained dispersion'}")
    if not gate_i:
        print("!! clause 4(i) fails: inverse-vol sizing earns gross with no forecast. Void.")
        return

    # ---- clause 6(a): the decomposition
    print("\n=== clause 6(a): where the change in t comes from ===")
    print(f"{'channel':<14} {'p = 0':>12} {'p = 1':>12} {'ratio':>8}")
    for key, lab in [("net_day", "mean $/day"), ("sd", "sd $/day"), ("t", "t"),
                     ("eff_n", "effective N")]:
        rt = prim[key] / base[key] if base[key] else float("nan")
        print(f"{lab:<14} {base[key]:>12,.1f} {prim[key]:>12,.1f} {rt:>8.3f}")

    # ---- clause 6(b): every comparison paired on the shared sessions
    print("\n=== clause 6(b): paired on the session, never two t's side by side ===")
    print(f"{'comparison':<28} {'delta net $/day':>22} {'delta gross':>26} {'delta cost':>24}")
    for a_cell, b_cell, name in [
            ("p0", "p1", "p1 - p0 (the primary)"),
            ("p0", "p2", "p2 - p0"),
            ("p0", "atr_p1", "atr p1 - p0 (free)"),
            ("atr_p1", "p1", "p1 - atr p1 (the ML part)"),
            ("p0", "ir_p0", "IR rank - p0"),
            ("net_p0", "net_p1", "p1 on F-11 - F-11 alone"),
            ("p1", "net_p1", "F-11 on p1 - p1 alone")]:
        if a_cell in keep and b_cell in keep:
            paired(keep[a_cell], keep[b_cell], name)

    # ---- clause 5: the decision, on the primary cell only
    print("\n=== clause 5: the decision, read on p = 1, sigma_hat, uncapped ===")
    yr_base, yr_prim = by_year(keep["p0"]), by_year(keep["p1"])
    print(f"{'year':<7} " + " ".join(f"{y:>8}" for y in yr_prim.index))
    print(f"{'p = 0':<7} " + " ".join(f"{v:>8,.0f}" for v in yr_base.values))
    print(f"{'p = 1':<7} " + " ".join(f"{v:>8,.0f}" for v in yr_prim.values))
    pos = int((yr_prim > 0).sum())
    passed = prim["t"] > TARGET_T and pos >= MIN_YEARS
    print(f"\np = 1: t {prim['t']:+.3f} (hurdle {TARGET_T}), {pos}/{len(yr_prim)} years positive "
          f"(hurdle {MIN_YEARS}), net ${prim['net_day']:,.0f}/day, "
          f"edge {prim['edge_bps']:+.3f} bps -> **{'PASS' if passed else 'REFUSE'}**")
    best = max((r for r in rows if r["kind"] == "real"), key=lambda r: r["t"])
    print(f"best cell on the test set (clause 5: may NOT be read as the result): "
          f"{best['label']} t {best['t']:+.2f}, net ${best['net_day']:,.0f}/day")

    # ---- regimes, which the job brief asks for explicitly
    print("\n=== out-of-sample P&L after costs, by causal SPY vol tercile ===")
    for c in ["p0", "p1", "p2"]:
        if c not in keep:
            continue
        reg = f11.by_regime(keep[c])
        print(f"\n{c}:")
        print(f"  {'regime':<10} {'sess':>5} {'gr bps':>7} {'cost bps':>8} {'$/day':>8} {'t':>6}")
        for r in reg.to_dict("records"):
            print(f"  {r['regime']:<10} {r['sessions']:>5} {r['gross_bps']:>7.3f} "
                  f"{r['cost_bps']:>8.3f} {r['net_day']:>8,.0f} {r['t']:>+6.2f}")

    # ---- what the sizing changed: dollars by name
    print("\n=== what the sizing changed: share of book dollars by name, p = 0 vs p = 1 ===")
    share: dict[str, dict[str, float]] = {}
    for c, p in [("p0", 0.0), ("p1", 1.0)]:
        acc: dict[str, float] = {}
        for day, g in frame.groupby("day", sort=True):
            syms = np.unique(g["sym"].to_numpy())
            P, F, X, S, A, C = _day_matrices(g, syms)
            ok = np.isfinite(P[0]) & np.isfinite(X[0]) & np.isfinite(S) & np.isfinite(A) & np.isfinite(C)
            for j in range(N_SLOTS):
                ok &= np.isfinite(F[j])
            w, _ = resize(f8._decile(P[0], ok, DECILE, 1.0),
                          np.maximum(S, SIGMA_FLOOR_BPS), p)
            for s, v in zip(syms, np.abs(w)):
                if v > 1e-12:
                    acc[s] = acc.get(s, 0.0) + float(v)
        tot = sum(acc.values())
        share[c] = {k: 100 * v / tot for k, v in acc.items()}
    tab = pd.DataFrame(share).fillna(0.0)
    tab["sigma"] = per
    tab["delta"] = tab["p1"] - tab["p0"]
    print(tab.sort_values("delta").head(6).to_string(float_format=lambda x: f"{x:.2f}"))
    print("  ...")
    print(tab.sort_values("delta").tail(6).to_string(float_format=lambda x: f"{x:.2f}"))

    out = pd.DataFrame(rows)
    out.to_csv(CELLS_CSV, index=False)
    print(f"\nwrote {CELLS_CSV.relative_to(REPO)}  ({len(out)} cells, "
          f"{time.time() - t_start:.0f}s)")

    if record_rows:
        for r in rows:
            sess = keep.get(r["cell"])
            if sess is None:
                continue
            record(f"F-12 {r['label']}", r, sess,
                   {"label": LABEL, "book": "session", "decile": DECILE, "power": r["p"],
                    "risk": r["risk"], "rank": r["rank"], "cap": r["cap"]},
                   {"Cell Kind": r["kind"], "Risk Label": "abs(y_close)"})
        print(f"recorded {sum(1 for r in rows if r['cell'] in keep)} DIAGNOSTIC rows")


# ------------------------------------------------ risk-model vs return-model feature stability


def run_importance() -> None:
    """The job brief's second criterion, asked of both models so the contrast is visible."""
    for name, path in [("return model |F-8, y_close|", f8.IMP), ("risk model |F-12, |y_close||", IMP)]:
        if not path.exists():
            print(f"{name}: {path.name} missing - run --fit --importance first")
            continue
        imp = pd.read_csv(path, index_col=0)
        years = [c for c in imp.columns if c.isdigit()]
        ranks = imp[years].rank(ascending=False)
        rho = ranks.corr(method="spearman").to_numpy()
        iu = np.triu_indices(len(years), 1)
        pair = rho[iu]
        k = 10
        tops = {y: set(ranks.index[ranks[y] <= k]) for y in years}
        ov = [len(tops[a] & tops[b]) / k for i, a in enumerate(years) for b in years[i + 1:]]
        always = set.intersection(*tops.values()) if tops else set()
        print(f"\n=== {name}: {len(years)} test years, {len(imp)} features ===")
        print(f"mean pairwise Spearman of the yearly rankings: {pair.mean():+.3f} "
              f"(min {pair.min():+.3f}, max {pair.max():+.3f})")
        print(f"mean top-{k} overlap between year pairs: {100 * np.mean(ov):.0f}%")
        print(f"features in the top-{k} of every year: "
              f"{', '.join(sorted(always)) if always else '(none)'}")
        print(f"\n{'feature':<18} {'rank mean':>10} {'rank sd':>9} " +
              " ".join(f"{y:>6}" for y in years))
        for s in ranks.mean(axis=1).sort_values().head(10).index:
            print(f"{s:<18} {ranks.loc[s].mean():>10.1f} {ranks.loc[s].std():>9.1f} " +
                  " ".join(f"{ranks.loc[s, y]:>6.0f}" for y in years))


# ------------------------------------------------------------------------- POST-RUN diagnostics


def run_post(record_rows: bool = False) -> None:
    """POST-RUN, DECLARED AS SUCH. None of this may change clause 5's decision, which is read on
    the pre-registered p = 1 cell alone and is a refusal.

    The ladder refused for a reason clause 0 named in advance as the *only* way the lever could
    lose: by Cauchy-Schwarz, inverse-vol weighting is weakly better than equal weighting whenever
    alpha_i is proportional to sigma_i, so a loss means alpha rises with vol **faster than
    linearly**. These three diagnostics price that claim instead of asserting it.

      (1) The counterfactual mean. If alpha_i = c * sigma_i exactly, the p = 1 book's mean is
          c * harmonic-mean(sigma) against the p = 0 book's c * arithmetic-mean(sigma), so
          HM/AM over the *held* name-days is the mean ratio the linear case predicts. Compare
          it with what happened.
      (2) The elasticity itself. Held name-days bucketed by sigma_hat; the realised per-dollar
          alpha of each bucket against its sigma gives the exponent directly.
      (3) The other direction. p < 0 tilts *into* the loud names. It is not pre-registered, it
          is selected on the same sessions it is scored on, and it is reported only because a
          refusal that names a direction is worth more than one that does not.
    """
    print("=" * 94)
    print("POST-RUN. Clause 5's decision is already fixed (REFUSE on p = 1) and nothing below")
    print("can change it. Every cell here is read on the same sessions it was chosen on.")
    print("=" * 94)
    frame = load_frame()

    # ---- (1)/(2): the held name-days, their sigma and their realised per-dollar alpha
    recs = []
    for day, g in frame.groupby("day", sort=True):
        syms = np.unique(g["sym"].to_numpy())
        P, F, X, S, A, C = _day_matrices(g, syms)
        ok = np.isfinite(P[0]) & np.isfinite(X[0]) & np.isfinite(S) & np.isfinite(A) & np.isfinite(C)
        for j in range(N_SLOTS):
            ok &= np.isfinite(F[j])
        w = f8._decile(P[0], ok, DECILE, 1.0)
        held = np.flatnonzero(np.abs(w) > 1e-12)
        if len(held) == 0:
            continue
        tot = np.expm1(np.where(np.isfinite(F), F, 0.0)).sum(axis=0)
        for j in held:
            recs.append((float(np.maximum(S[j], SIGMA_FLOOR_BPS)),
                         float(np.sign(w[j]) * tot[j] * 1e4)))
    d = pd.DataFrame(recs, columns=["sigma", "alpha_bps"])
    am, hm = d["sigma"].mean(), len(d) / (1.0 / d["sigma"]).sum()
    print(f"\n(1) held name-days: {len(d):,};  sigma_hat arithmetic mean {am:.1f} bps, "
          f"harmonic mean {hm:.1f}")
    print(f"    if alpha were exactly proportional to sigma, the p = 1 mean would be "
          f"HM/AM = {hm / am:.3f} of the p = 0 mean.")
    print(f"    it was 0.521 (see clause 6(a)), i.e. the lever cost "
          f"{100 * (hm / am - 0.521) / (hm / am):.0f}% more than the linear case allows.")

    print("\n(2) the elasticity, measured: held name-days by sigma_hat quintile")
    d["q"] = pd.qcut(d["sigma"], 5, labels=False)
    print(f"    {'quintile':<9} {'n':>8} {'sigma bps':>10} {'alpha bps':>10} {'alpha t':>8} "
          f"{'alpha/sigma':>12}")
    xs, ys = [], []
    for q, gq in d.groupby("q"):
        s, a_ = gq["sigma"].mean(), gq["alpha_bps"].mean()
        print(f"    {int(q) + 1:<9} {len(gq):>8,} {s:>10.1f} {a_:>10.2f} "
              f"{f1.tstat(gq['alpha_bps'].to_numpy()):>+8.2f} {a_ / s:>12.4f}")
        if a_ > 0:
            xs.append(np.log(s))
            ys.append(np.log(a_))
    if len(xs) > 2:
        beta = float(np.polyfit(xs, ys, 1)[0])
        print(f"    log-log slope of alpha on sigma: beta = {beta:+.3f}  "
              f"(beta = 1 is the break-even for inverse-vol sizing; "
              f"beta > 1 means equal weight is already under-allocated to vol)")

    # ---- (3) the other direction
    print("\n(3) the untested direction: p < 0 tilts INTO the loud names (post-run, test-set)")
    print(HDR)
    rows, keep = [], {}
    for p in [-1.0, -0.5, 0.0, 1.0]:
        sess = simulate(frame, p=p)
        r = summarize(sess, f"p = {p:g}")
        r.update(cell=f"post_p{p:g}", p=p, risk="ml", rank="alpha", cap=0.0, kind="post-run")
        rows.append(r)
        keep[r["cell"]] = sess
        print(line(r))
    print("\n    paired against p = 0, on the shared sessions (clause 6(b)):")
    print(f"    {'comparison':<28} {'delta net $/day':>22} {'delta gross':>26} {'delta cost':>24}")
    for c in ["post_p-1", "post_p-0.5"]:
        paired(keep["post_p0"], keep[c], f"    {c[5:]} - p0")
    yr = by_year(keep["post_p-1"])
    print(f"\n    p = -1 by year: " + "  ".join(f"{y}:{v:,.0f}" for y, v in yr.items()))
    print(f"    p = -1 is NOT a result. It is the maximum of a ladder read on its own test set, "
          f"it has\n    no control, and clause 5 already refused. It is a hypothesis for a "
          f"future iteration, and the\n    honest version of it would be pre-registered, "
          f"controlled and fitted out of sample.")

    if record_rows:
        for r in rows:
            record(f"F-12 post-run {r['label']}", r, keep[r["cell"]],
                   {"label": LABEL, "book": "session", "decile": DECILE, "power": r["p"],
                    "risk": "ml", "rank": "alpha", "cap": 0.0},
                   {"Cell Kind": "post-run", "Risk Label": "abs(y_close)"})
        print(f"\nrecorded {len(rows)} post-run DIAGNOSTIC rows")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fit", action="store_true", help="walk-forward fit of the risk label")
    ap.add_argument("--books", action="store_true", help="the sizing ladder and the decision")
    ap.add_argument("--post", action="store_true", help="post-run diagnostics (cannot decide)")
    ap.add_argument("--importance", action="store_true", help="feature stability, both models")
    ap.add_argument("--record", action="store_true", help="append DIAGNOSTIC ledger rows")
    a = ap.parse_args()
    if a.fit:
        build_risk(importance=a.importance)
    elif a.importance and not a.books:
        run_importance()
    if a.post:
        run_post(record_rows=a.record)
    if a.books or not (a.fit or a.importance or a.post):
        run_books(record_rows=a.record)


if __name__ == "__main__":
    main()
