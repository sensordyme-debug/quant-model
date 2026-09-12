"""F-8: fit the label the forecast actually has, instead of harvesting it every 30 minutes.

F-7 closed every construction axis on F-1's forecast (dwell, hysteresis band, EWMA, conviction
gate, decile width, and the stacked cells of the two that moved the number most) and refused all
nineteen on power. It left exactly one axis open, and it is not a book axis at all. F-7's clause 2
measured the forecast's information coefficient against the demeaned cumulative return `h`
intervals ahead and found that **it does not decay - it rises**:

    h = 1 (30 min)  IC +0.01133   <- the label F-1 trains on
    h = 4 (2 h)     IC +0.01447
    h = 7 (3.5 h)   IC +0.02064
    h = 10 (5 h)    IC +0.02115

Every F-7 construction harvested a multi-hour signal with a model fitted to the **worst horizon
that signal has**. F-8 fits the label directly: same panel, same 38 features, same walk-forward,
same learner, and the only thing that changes is what the model is asked to predict.

    python scripts/ml_f8.py --predict          # walk-forward per label -> data/f1/f8_preds.parquet
    python scripts/ml_f8.py --book             # the books, the controls, the verdict
    python scripts/ml_f8.py --book --record    # ... and append DIAGNOSTIC rows to the ledger
    python scripts/ml_f8.py --predict --importance

**Run it with `INTRADAY_DATA_DIR=data/minute_alpaca`.** F-7 found and documented the hazard: the
cost model reads `data/minute_alpaca/_splits.json`, and without it `share_scale()` is 1.0, the
per-share commission on the reverse-split leveraged names is charged on share counts four orders
of magnitude too small, and the whole cost line is understated by ~0.28 bps of turnover while
gross, turnover and IC all still look right. This module prints the store it costed against.

--------------------------------------------------------------------------------------------
PRE-REGISTERED - written in full before any F-8 number was read
--------------------------------------------------------------------------------------------

**Clause 0 - the prior, stated out loud.** Three refusals (F-1 on cost, F-3 on absence, F-7 on
power) all landed on IC +0.011 to +0.014 and single-digit bps per dollar turned. The honest prior
is that F-8 finds IC ~+0.02 on a longer label, converts it to ~3.5 bps per dollar turned, and
fails a cost line that prices at 2.5-3.7. F-8 is the last item on this track unless it clears the
hurdle outright; "promising but underpowered" is a refusal, not a follow-up.

**Clause 1 - the labels.** From F-1's panel, unchanged. The decision grid is 11 points per session
(slot k = 0..10, decided on the 5-minute bar ending at 09:55+30k, filled at the open of the next
bar 10:00+30k, and slot 10's own exit at 15:30 is the sleeve's flatten). `fwd` at slot k is the
log return the book captures over that interval, and consecutive slots chain exactly
(`fwd[k]` ends where `fwd[k+1]` begins), so the h-interval return is the sum of h consecutive
`fwd` values **inside the same session with no missing slot** - a gap invalidates that row and
every longer horizon built on it. Four labels, each demeaned across the names present at the same
timestamp because a dollar-neutral book earns the cross-section and not the level:

  - `h4`, `h7`, `h10`   fixed horizon, defined only where slot k + h <= 11 (8, 5 and 2 slots).
  - `close`             hold to the 15:30 flatten: horizon 11 - k, defined at every slot. This is
                        the label the deployed convention actually implies, and it is the only one
                        that keeps the whole panel.

  `h1` is F-1's own label and needs no refit - its 2019-2026 out-of-sample predictions are already
  frozen in `data/f1/preds_test_ext.parquet` from F-7's power extension. It is the benchmark
  column in every table below: **the question F-8 asks is whether the same book, fed the same
  features through the same learner, does better when the label matches the hold.**

**Clause 2 - the walk-forward, fixed from the start at F-7's extended window.** Test years
2019-2026 (8 years, ~1,900 sessions), year Y trained on <= Y-2 and early-stopped on Y-1, expanding
window, nothing re-tuned and no hyperparameter search: the learner is `sweep_f1.GRID["mid"]`,
F-1's own stage-1 selection, `random_state=0`. Changing the label and the learner at once would
make the comparison unreadable, so the learner does not move. 675 sessions could not resolve a
t of 1.3 in F-7 and will not here.

**Clause 3 - the books, and why turnover is fixed rather than swept.** A hold of L intervals
trades once in and once out, so **every book below turns exactly 2x equity per session** and the
sweep F-7 already exhausted cannot be re-run by accident:

  - `session(L)`   one decision per session at slot 0 (fill 10:00), top/bottom decile, held to the
                   15:30 flatten. The backlog's own construction and the minimum-turnover book
                   this panel can express.
  - `cohort_close` a sub-book of gross 1/11 opened at **every** slot on the `close` prediction and
                   held to the flatten. Same 2x turnover as `session`, eleven entry points instead
                   of one, so it is the same bet with ~11x the breadth.
  - `cohort_h`     a sub-book of gross 1/(12-h) opened at every slot where the h-interval hold
                   still fits in the session, held h intervals. Weights are **netted across live
                   cohorts** before turnover is charged, which is what a real book would do.

  Each book is run on each label's prediction, plus on `h1`, so the label axis is read at constant
  construction. Decile 0.10 throughout, gross 1.0, equity $1M, flat overnight, unwind priced at the
  last decision bar's open (F-1's and F-7's convention).

**Clause 4 - the control, with its cost column.** Every reported cell is re-run on a seeded
per-timestamp permutation of the prediction. F-7's finding stands as a pre-registered check: a
control is only clean if **both** its gross bps is indistinguishable from zero **and** its cost bps
matches the real cell's. A real cell that costs materially more than its own control is selecting
expensive names, and that selection cost is not removable by any construction.

**Clause 5 - the hurdle, inherited rather than rediscovered.** Net = turnover x (gross_bps -
cost_bps), and cost_bps is a property of the instrument and the names selected, not of the
construction. F-7 measured 2.392 bps on an unselective decile book and 3.697-4.090 bps once a gate
selected for wide predicted moves. **Each cell is judged against its own measured cost column**,
and the reported multiple is over F-1's 0.797 bps per dollar turned.

**Clause 6 - regimes and stability, the two things the job asks to judge on.** Out-of-sample net
after costs is reported per test year (all 8) and by the causal trailing 20-session realized
volatility tercile of SPY. Permutation importance is computed on each retrain's validation year
for the winning label and compared across retrains by Spearman rank correlation, with the sign
stability of the magnitudes reported alongside - F-7 showed a stable ranking over sign-flipping
magnitudes, which is what a weak true signal read through noise looks like.

**Clause 7 - the pass rule.** Net P&L per day positive with **t > 2 pooled over 2019-2026** and
positive in **at least 5 of the 8 test years**. Nothing deploys otherwise, and nothing deploys from
this file at all: `algorithms/intraday/active/signal.py` and `live/intraday_config.json` are not
touched, so no deploy gate and no `--replay` is owed.

**Clause 8 - what would reopen the track, decided before the numbers.** If the best cell clears
clause 7, the next step is a separate pre-registration for execution (participation caps, the
IBKR-store cross-check) and not a wider grid. If it fails with gross bps above its own cost line
but t <= 2, the finding is reported as underpowered and the track still closes - F-7 already spent
an iteration learning that a 2.5x window turns that cell to zero. If gross bps is below the cost
line, the supervised class is priced a fourth way and the track closes for good.
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

LEDGER = REPO / "research" / "experiments.jsonl"
OUT = REPO / "data" / "f1"
PREDS = OUT / "f8_preds.parquet"
IMP = OUT / "importance_f8.csv"
EXT = OUT / "preds_test_ext.parquet"

EQUITY = 1_000_000.0
N_SLOTS = 11                       # decision points per session, 0..10
FIRST_TEST_YEAR = 2019
DECILE = 0.10

#: fixed-horizon labels, in decision intervals of 30 minutes
HORIZONS = {"h4": 4, "h7": 7, "h10": 10}
#: `close` = hold to the 15:30 flatten, horizon 11 - slot, defined at every slot
LABELS = ["h4", "h7", "h10", "close"]
#: F-1's own 30-minute label - the benchmark, already frozen by F-7's power extension
BENCH = "h1"

F1_GROSS_BPS = 0.797               # F-1's gross per dollar turned, the multiple's denominator


# ------------------------------------------------------------------------------------- labels


def add_labels(panel: pd.DataFrame) -> pd.DataFrame:
    """Clause 1: chain `fwd` inside each session into the four horizons, then demean per timestamp.

    A missing slot breaks the chain: the cumulative return is invalidated at that horizon and at
    every longer one, so no label is ever built across a data gap.
    """
    p = panel.copy()
    p["ts"] = pd.to_datetime(p["ts"])
    mins = (p["ts"].dt.hour - 9) * 60 + p["ts"].dt.minute - 30
    p["slot"] = ((mins - 25) // 30).astype("int8")
    p = p.sort_values(["sym", "day", "slot"]).reset_index(drop=True)

    g = p.groupby(["sym", "day"], sort=False)
    fwd = p["fwd"].astype("float64")
    slot = p["slot"].astype("int16")
    cum = fwd.copy()
    cums = {1: cum.copy()}
    for h in range(2, N_SLOTS + 1):
        nxt = g["fwd"].shift(-(h - 1))
        nslot = g["slot"].shift(-(h - 1))
        ok = nslot == slot + (h - 1)
        cum = (cum + nxt).where(ok)
        cums[h] = cum.copy()

    for name, h in HORIZONS.items():
        p[f"c_{name}"] = cums[h].where(slot + h <= N_SLOTS)
    close = np.full(len(p), np.nan)
    sl = slot.to_numpy()
    for h in range(1, N_SLOTS + 1):
        m = (N_SLOTS - sl) == h
        if m.any():
            close[m] = cums[h].to_numpy()[m]
    p["c_close"] = close

    for name in LABELS:
        c = f"c_{name}"
        p[f"y_{name}"] = (p[c] - p.groupby("ts", sort=False)[c].transform("mean")).astype("float32")
        p.drop(columns=[c], inplace=True)
    return p


# ------------------------------------------------------------------------------ walk-forward


def build_predictions(importance: bool = False, labels: list[str] | None = None) -> pd.DataFrame:
    panel = pd.read_parquet(f1.PANEL)
    p = add_labels(panel)
    del panel
    params = dict(f1.GRID["mid"])
    years = [y for y in sorted(p["year"].unique()) if y >= FIRST_TEST_YEAR]
    print(f"panel {len(p):,} rows, {p['sym'].nunique()} symbols, {p['day'].nunique():,} sessions; "
          f"learner 'mid' {params}")
    print(f"label coverage: " + "  ".join(
        f"{l}={int(p[f'y_{l}'].notna().sum()):,}" for l in LABELS))

    frames, models = [], {}
    for name in (labels or LABELS):
        col = f"y_{name}"
        sub = p.dropna(subset=[col]).copy()
        sub["y"] = sub[col]
        print(f"\n--- label {name}: {len(sub):,} rows, slots "
              f"{sorted(sub['slot'].unique().tolist())}")
        for year in years:
            trn = sub[sub.year <= year - 2]
            vld = sub[sub.year == year - 1]
            tst = sub[sub.year == year]
            if not (len(trn) and len(vld) and len(tst)):
                continue
            t0 = time.time()
            model, pt = f1.fit_predict(trn, vld, tst, dict(params))
            icm, ict = f1.ic_stats(tst, pt)
            keep = tst[["ts", "day", "year", "sym", "slot", "entry_px", "fwd"]].copy()
            keep["label"] = name
            keep["pred"] = pt
            frames.append(keep)
            if name == "close":
                models[int(year)] = (model, vld)
            print(f"  {year}: train<={year-2} ({len(trn):,}) valid {year-1} ({len(vld):,}) "
                  f"test ({len(tst):,}) iters {model.n_iter_:>4}  IC {icm:+.5f} (t {ict:+.2f})  "
                  f"({time.time()-t0:.0f}s)")
        del sub

    out = pd.concat(frames, ignore_index=True)
    OUT.mkdir(parents=True, exist_ok=True)
    out.to_parquet(PREDS, index=False)
    print(f"\nfrozen: {len(out):,} rows -> {PREDS}")

    if importance and models:
        run_importance(models)
    return out


def run_importance(models: dict) -> None:
    """Clause 6: permutation importance per retrain on the `close` label, and its stability."""
    from sklearn.inspection import permutation_importance
    print("\n=== permutation importance, label 'close', on each retrain's validation year ===")
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
    yrs = sorted(models)
    print("\nSpearman rank correlation between retrains:")
    print(imp[yrs].rank().corr(method="spearman").to_string(float_format=lambda x: f"{x:.3f}"))
    sign = (imp[yrs] > 0).sum(axis=1)
    print(f"\nfeatures with a positive importance in all {len(yrs)} retrains: "
          f"{int((sign == len(yrs)).sum())} of {len(f1.FEATURES)}; "
          f"sign-flipping (mixed): {int(((sign > 0) & (sign < len(yrs))).sum())}")
    print(f"importance -> {IMP}")


# ---------------------------------------------------------------------------------- simulator


def _decile(pred: np.ndarray, ok: np.ndarray, decile: float, gross: float) -> np.ndarray:
    """Top/bottom decile of `pred` among the eligible names, each side to gross/2."""
    w = np.zeros(len(pred))
    idx = np.flatnonzero(ok)
    if len(idx) < 6:
        return w
    order = idx[np.argsort(pred[idx], kind="stable")]
    k = max(1, int(round(decile * len(idx))))
    w[order[-k:]] = gross / 2.0 / k
    w[order[:k]] = -gross / 2.0 / k
    return w


def _day_matrices(g: pd.DataFrame, syms: np.ndarray):
    n = len(syms)
    pos = {s: i for i, s in enumerate(syms)}
    P = np.full((N_SLOTS, n), np.nan)
    F = np.full((N_SLOTS, n), np.nan)
    X = np.full((N_SLOTS, n), np.nan)
    for k, sym, pr, fw, px in zip(g["slot"].to_numpy(), g["sym"].to_numpy(),
                                  g["pred"].to_numpy(float), g["fwd"].to_numpy(float),
                                  g["entry_px"].to_numpy(float)):
        j = pos[sym]
        P[k, j], F[k, j], X[k, j] = pr, fw, px
    return P, F, X


def simulate(frame: pd.DataFrame, kind: str, h: int | None = None, decile: float = DECILE,
             gross: float = 1.0, costs: bool = True, scramble: int | None = None) -> pd.DataFrame:
    """One row per session: gross, cost, net, turnover.

    `kind`:
      "session"      one cohort opened at slot 0 and held to the flatten
      "cohort_close" a cohort of gross/11 opened at every slot, each held to the flatten
      "cohort_h"     a cohort of gross/(12-h) opened at every slot where an h-hold still fits
    Cohort weights are summed (netted) before turnover is charged.
    """
    rng = np.random.default_rng(scramble) if scramble is not None else None
    rows = []
    for day, g in frame.groupby("day", sort=True):
        syms = np.unique(g["sym"].to_numpy())
        P, F, X = _day_matrices(g, syms)
        if rng is not None:
            for k in range(N_SLOTS):
                ok = np.isfinite(P[k])
                if ok.sum() > 1:
                    v = P[k, ok]
                    P[k, ok] = rng.permutation(v)

        if kind == "session":
            entries, hold, sub = [0], {0: N_SLOTS}, gross
        elif kind == "cohort_close":
            entries = list(range(N_SLOTS))
            hold = {k: N_SLOTS - k for k in entries}
            sub = gross / N_SLOTS
        elif kind == "cohort_h":
            entries = list(range(0, N_SLOTS - h + 1))
            hold = {k: h for k in entries}
            sub = gross / len(entries)
        else:
            raise ValueError(kind)

        W = np.zeros((N_SLOTS, len(syms)))
        for k in entries:
            L = hold[k]
            ok = np.isfinite(P[k]) & np.isfinite(X[k])
            for j in range(k, k + L):
                ok &= np.isfinite(F[j])
            w = _decile(P[k], ok, decile, sub)
            if not w.any():
                continue
            W[k:k + L] += w

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
                if costs:
                    for s, d, q, nt in zip(syms[m], dw[m], px[m], notional):
                        if not np.isfinite(q) or q <= 0:
                            continue
                        sh = np.sign(d) * nt / q
                        cost += ic.commission(sh, float(q), f7_scale(s, day)) + ic.slippage(sh, float(q))
            prev = cur
        rows.append({"day": day, "gross": pnl, "cost": cost, "turnover": turn})

    sess = pd.DataFrame(rows)
    sess["net"] = sess["gross"] - sess["cost"]
    return sess


_SCALE: dict = {}


def f7_scale(sym: str, day) -> float:
    key = (sym, day)
    v = _SCALE.get(key)
    if v is None:
        v = ic.share_scale(sym, day)
        _SCALE[key] = v
    return v


# ------------------------------------------------------------------------------------ reports


def summarize(sess: pd.DataFrame, label: str) -> dict:
    net = sess["net"].to_numpy()
    turn = float(sess["turnover"].mean())
    gross = float(sess["gross"].mean())
    gbps = 1e4 * gross / turn if turn else float("nan")
    cbps = 1e4 * float(sess["cost"].mean()) / turn if turn else float("nan")
    return {"label": label, "sessions": len(sess), "net_day": float(net.mean()),
            "t": f1.tstat(net), "gross_day": gross, "cost_day": float(sess["cost"].mean()),
            "turn_day": turn, "gross_bps": gbps, "mult": gbps / F1_GROSS_BPS, "cost_bps": cbps,
            "edge_bps": gbps - cbps, "gross_t": f1.tstat(sess["gross"].to_numpy()),
            "worst": float(net.min()), "win": float((net > 0).mean())}


HDR = (f"{'cell':<28} {'sess':>5} {'gr bps':>7} {'x F-1':>6} {'gr t':>6} {'cost bps':>8} "
       f"{'edge':>7} {'turn/day':>10} {'$/day':>8} {'t':>6} {'worst':>8} {'win':>6}")


def print_table(rows: list[dict], hdr: bool = True) -> None:
    if hdr:
        print(HDR)
        print("-" * len(HDR))
    for r in rows:
        print(f"{r['label']:<28} {r['sessions']:>5} {r['gross_bps']:>7.3f} {r['mult']:>6.2f} "
              f"{r['gross_t']:>6.2f} {r['cost_bps']:>8.3f} {r['edge_bps']:>+7.3f} "
              f"{r['turn_day']:>10,.0f} {r['net_day']:>8,.0f} {r['t']:>6.2f} "
              f"{r['worst']:>8,.0f} {r['win']:>6.1%}")


def ic_vs(frame: pd.DataFrame, pred_col: str, y_col: str) -> tuple[float, float]:
    d = frame[["ts", pred_col, y_col]].dropna()
    ics = (d.groupby("ts", sort=False)
           .apply(lambda g: g[pred_col].corr(g[y_col], method="spearman") if len(g) > 5 else np.nan,
                  include_groups=False).dropna().to_numpy())
    return (float(ics.mean()), f1.tstat(ics)) if len(ics) else (float("nan"), float("nan"))


def record(tag: str, r: dict, sess: pd.DataFrame, params: dict, extra: dict) -> None:
    net = sess["net"].to_numpy()
    n = len(sess)
    ret = net / EQUITY
    sd = ret.std(ddof=1) if n > 1 else 0.0
    rec = {"ts": dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
           "algorithm": "intraday/f8_label", "class": "ml", "tag": tag, "commit": "",
           "run_dir": "", "track": "F-8", "params": params,
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
                     "Worst Day": f"{net.min():.0f}",
                     "Win Rate": f"{100 * (net > 0).mean():.0f}%",
                     "Sharpe Ratio": f"{(ret.mean() / sd * np.sqrt(252)) if sd else float('nan'):.3f}",
                     "Diagnostic": "true",
                     **{k: str(v) for k, v in extra.items()}}}
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, default=str) + "\n")


# ---------------------------------------------------------------------------------------- main


def price_grid() -> pd.DataFrame:
    """Every (slot, name) the panel has over the test window, with its fill price and interval
    return - independent of which slots a given label happens to be defined on.

    A book that holds past the last slot its label covers still needs those intervals priced, so
    the grid and the prediction are kept separate: the prediction decides, the grid pays.
    """
    p = pd.read_parquet(f1.PANEL, columns=["ts", "day", "year", "sym", "entry_px", "fwd"])
    p["ts"] = pd.to_datetime(p["ts"])
    p = p[p["year"] >= FIRST_TEST_YEAR].copy()
    mins = (p["ts"].dt.hour - 9) * 60 + p["ts"].dt.minute - 30
    p["slot"] = ((mins - 25) // 30).astype("int8")
    return p.reset_index(drop=True)


def load_frames() -> dict[str, pd.DataFrame]:
    """One simulation frame per label: the full price grid with that label's prediction merged on."""
    grid = price_grid()
    out = {}
    pr = pd.read_parquet(PREDS)
    pr["ts"] = pd.to_datetime(pr["ts"])
    for name, g in pr.groupby("label", sort=False):
        out[name] = grid.merge(g[["ts", "sym", "pred"]], on=["ts", "sym"], how="left")
    ext = pd.read_parquet(EXT)
    ext["ts"] = pd.to_datetime(ext["ts"])
    out[BENCH] = grid.merge(ext[["ts", "sym", "pred"]], on=["ts", "sym"], how="left")
    return out


BOOKS = [("session", None, "session(hold to flatten)"),
         ("cohort_close", None, "cohort_close(11 entries)"),
         ("cohort_h", 7, "cohort_h7"),
         ("cohort_h", 4, "cohort_h4")]


def run_books(record_rows: bool = False) -> None:
    print(f"cost store: {ic.DATA_DIR}  (slippage {ic.SLIPPAGE_BPS} bps; "
          f"splits file present: {(Path(ic.DATA_DIR) / '_splits.json').exists()})")
    frames = load_frames()
    order = [BENCH] + [l for l in LABELS if l in frames]
    print(f"labels available: {order}")

    # ---- the label x book grid, at constant construction
    print("\n=== the grid: same book, same features, same learner - only the LABEL moves ===")
    cells: dict[tuple, tuple[dict, pd.DataFrame]] = {}
    for kind, h, bname in BOOKS:
        rows = []
        for lab in order:
            fr = frames[lab]
            if kind == "cohort_h" and h is not None and lab in HORIZONS and HORIZONS[lab] != h:
                pass  # still run it: the label axis is read at constant construction
            sess = simulate(fr, kind, h=h)
            r = summarize(sess, f"{bname} <- {lab}")
            rows.append(r)
            cells[(kind, h, lab)] = (r, sess)
        print()
        print_table(rows)

    # ---- the decisive comparison, isolated
    print("\n=== clause 3's question: does matching the label to the hold beat F-1's h1? ===")
    best = max(cells.items(), key=lambda kv: kv[1][0]["net_day"])
    (bk, bh, blab), (brow, bsess) = best
    bench_row = cells[(bk, bh, BENCH)][0]
    print(f"  best cell overall : {brow['label']:<32} gross {brow['gross_bps']:.3f} bps "
          f"({brow['mult']:.2f}x F-1) cost {brow['cost_bps']:.3f}  net ${brow['net_day']:,.0f}/day "
          f"t {brow['t']:+.2f}")
    print(f"  same book on h1   : {bench_row['label']:<32} gross {bench_row['gross_bps']:.3f} bps "
          f"({bench_row['mult']:.2f}x F-1) cost {bench_row['cost_bps']:.3f}  "
          f"net ${bench_row['net_day']:,.0f}/day t {bench_row['t']:+.2f}")

    # ---- per-year and regime for the best cell and its h1 benchmark
    print("\n=== clause 6: out-of-sample net per test year (the best cell vs its h1 benchmark) ===")
    bench_sess = cells[(bk, bh, BENCH)][1]
    yr = pd.DataFrame({"day": bsess["day"]})
    yr["year"] = pd.to_datetime(yr["day"]).dt.year
    print(f"{'year':<6} {'sess':>5} {'best net$':>10} {'t':>6} {'h1 net$':>10} {'t':>6}")
    years_pos = 0
    per_year_rows = []
    for y, idx in yr.groupby("year").groups.items():
        a = bsess.loc[idx]
        b = bench_sess.loc[bench_sess["day"].isin(a["day"])]
        ra = summarize(a, f"best {y}")
        rb = summarize(b, f"h1 {y}")
        per_year_rows.append((y, ra))
        years_pos += int(ra["net_day"] > 0)
        print(f"{y:<6} {len(a):>5} {ra['net_day']:>10,.0f} {ra['t']:>6.2f} "
              f"{rb['net_day']:>10,.0f} {rb['t']:>6.2f}")

    reg = f7.vol_regime(bsess["day"].to_numpy())
    print("\nby causal SPY realized-vol tercile (best cell vs its h1 benchmark):")
    rmap = bsess["day"].astype(str).map(reg)
    bmap = bench_sess["day"].astype(str).map(reg)
    for name in ["low vol", "mid vol", "high vol", "n/a"]:
        m = (rmap == name).to_numpy()
        if m.sum() <= 5:
            continue
        r = summarize(bsess[m], name)
        rb = summarize(bench_sess[(bmap == name).to_numpy()], name)
        print(f"  {name:<9} {int(m.sum()):>5} sess  gross {r['gross_bps']:>6.3f} bps "
              f"(h1 {rb['gross_bps']:>6.3f})  cost {r['cost_bps']:>6.3f}  "
              f"net ${r['net_day']:>7,.0f}/day t {r['t']:>+5.2f}  "
              f"(h1 ${rb['net_day']:>7,.0f} t {rb['t']:>+5.2f})")

    # ---- the label ladder: the one number this iteration exists to produce
    print("\n=== the label ladder on the session book: gross bps per dollar turned by label ===")
    print(f"{'label':<8} {'horizon':>9} {'gross bps':>10} {'x h1':>6} {'gr t':>6} {'net $/day':>10} {'t':>6}")
    for lab in order:
        r = cells[("session", None, lab)][0]
        hh = "11 - slot" if lab == "close" else (str(HORIZONS[lab]) if lab in HORIZONS else "1")
        base = cells[("session", None, BENCH)][0]["gross_bps"]
        print(f"{lab:<8} {hh:>9} {r['gross_bps']:>10.3f} {r['gross_bps'] / base:>6.2f} "
              f"{r['gross_t']:>6.2f} {r['net_day']:>10,.0f} {r['t']:>6.2f}")

    # ---- clause 4: the control, with its cost column
    print("\n=== clause 4: scrambled-prediction controls (gross AND cost must both be clean) ===")
    ctrl_rows = []
    for kind, h, bname in BOOKS:
        cs = simulate(frames[blab], kind, h=h, scramble=1234)
        cr = summarize(cs, f"CONTROL {bname}")
        ctrl_rows.append((cr, cells[(kind, h, blab)][0], cs))
    print_table([c for c, _, _ in ctrl_rows])
    print("\ncost-selection check (clause 4): real cost bps vs its own control's")
    for c, real, _ in ctrl_rows:
        print(f"  {real['label']:<32} real {real['cost_bps']:.3f}  control {c['cost_bps']:.3f}  "
              f"selection premium {real['cost_bps'] - c['cost_bps']:+.3f} bps")

    # ---- clause 4, the stronger version: one control seed cannot say whether 0.5 bps is noise
    print("\nfive-seed control on the best book (the real cell's gross must sit far outside this):")
    gs = []
    for seed in (1234, 7, 101, 2718, 31415):
        r = summarize(simulate(frames[blab], bk, h=bh, scramble=seed), f"seed {seed}")
        gs.append(r["gross_bps"])
        print(f"  seed {seed:<6} gross {r['gross_bps']:>+7.3f} bps  cost {r['cost_bps']:.3f}  "
              f"net ${r['net_day']:>7,.0f}/day")
    gs = np.asarray(gs)
    z = (brow["gross_bps"] - gs.mean()) / gs.std(ddof=1)
    print(f"  control gross {gs.mean():+.3f} +/- {gs.std(ddof=1):.3f} bps; real cell "
          f"{brow['gross_bps']:.3f} sits {z:.1f} control sd above it")

    # ---- how much data would the pooled statistic need? t scales with sqrt(sessions).
    need = (2.0 / brow["t"]) ** 2 * brow["sessions"] if brow["t"] > 0 else float("inf")
    print(f"\npower: t {brow['t']:+.2f} on {brow['sessions']:,} sessions -> t = 2 needs "
          f"{need:,.0f} sessions ({need / 252:.1f} years) at this effect size. The Alpaca store "
          f"starts in 2016 and the walk-forward burns three years, so the ceiling is ~7.7 years.")

    # ---- clause 7: the verdict
    n_years = len(per_year_rows)
    passed = brow["net_day"] > 0 and brow["t"] > 2 and years_pos >= 5
    print(f"\nPRE-REGISTERED RULE (clause 7): net > 0 with t > 2 pooled 2019-2026 and positive "
          f"in >= 5 of 8 test years")
    print(f"  best cell {brow['label']}: ${brow['net_day']:,.0f}/day at t {brow['t']:+.2f}; "
          f"positive years {years_pos}/{n_years}  ->  {'PASS' if passed else 'REFUSED'}")
    npass = sum(1 for (_, _, lab), (r, _) in cells.items()
                if r["net_day"] > 0 and r["t"] > 2)
    print(f"  cells passing clause 7 on the pooled statistic: {npass} of {len(cells)}")

    if record_rows:
        params = {"learner": "mid", "decile": DECILE, "window": "2019-2026", "features": len(f1.FEATURES)}
        for (kind, h, lab), (r, sess) in cells.items():
            record(f"F-8 DIAGNOSTIC: book {kind}{h or ''} on label {lab} "
                   f"(walk-forward 2019-2026, learner 'mid')",
                   r, sess, {**params, "book": f"{kind}{h or ''}", "label": lab},
                   {"Regime": "2019-2026", "Book": f"{kind}{h or ''}", "Label": lab})
        for c, _real, csess in ctrl_rows:
            record(f"F-8 DIAGNOSTIC CONTROL: {c['label']} on label {blab}, "
                   f"prediction permuted within each decision point",
                   c, csess, {**params, "book": c["label"], "label": blab, "scramble": 1234},
                   {"Regime": "2019-2026", "Control": "true"})
        print(f"\nrecorded {len(cells) + len(ctrl_rows)} diagnostic rows in {LEDGER}")


def run_ic(record_rows: bool = False) -> None:
    """Clause 2/6 diagnostic: each model's IC against every label, on the same rows."""
    panel = pd.read_parquet(f1.PANEL, columns=["ts", "day", "year", "sym", "fwd"])
    p = add_labels(panel.assign(fwd=panel["fwd"]))
    p = p[p.year >= FIRST_TEST_YEAR]
    ycols = [f"y_{l}" for l in LABELS]
    frames = load_frames()
    print(f"\n=== IC of each model's prediction against each label, 2019-2026 ===")
    print(f"{'model':<8} " + " ".join(f"{c[2:]:>16}" for c in ycols))
    for lab in [BENCH] + LABELS:
        if lab not in frames:
            continue
        fr = frames[lab][["ts", "sym", "pred"]]
        m = p.merge(fr, on=["ts", "sym"], how="inner")
        cells = []
        for c in ycols:
            icm, ict = ic_vs(m, "pred", c)
            cells.append(f"{icm:+.5f}({ict:+.1f})")
        print(f"{lab:<8} " + " ".join(f"{c:>16}" for c in cells))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--predict", action="store_true")
    ap.add_argument("--labels", nargs="*", default=None)
    ap.add_argument("--book", action="store_true")
    ap.add_argument("--ic", action="store_true")
    ap.add_argument("--importance", action="store_true")
    ap.add_argument("--record", action="store_true")
    args = ap.parse_args()

    if args.predict:
        build_predictions(importance=args.importance, labels=args.labels)
    if args.ic:
        run_ic()
    if args.book:
        run_books(record_rows=args.record)
    if not (args.predict or args.book or args.ic):
        ap.print_help()


if __name__ == "__main__":
    main()
