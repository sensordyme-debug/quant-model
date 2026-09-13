"""F-17: point F-16's causal gate at the WHOLE candidate space the track has accumulated.

F-14 fitted 19 flow columns as a family and lost. F-15 fitted 19 auction columns as a family and
lost, while 3 of them - chosen after reading the test window - gained. F-16 made that selection
causal and found the reusable rule: *a gate earns its keep in the windows where it admits
NOTHING*. The causal arm beat the test-set-selected oracle purely by declining to add anything in
2019-2023.

F-16's gate has never been shown a candidate it was not already expecting to like. It ran on one
family, six parents, one store. F-17 is the first run that makes it choose: **17 parents from two
disjoint stores in one pool**, per-year floor, per-year admission, and - because eleven of the
seventeen are near-copies of each other (`ofi5`/`ofi30`/`ofi_sess`) in a way the six auction
columns never were - a within-pool redundancy leg that F-16 did not need.

The question F-14 left open and named: it refused its flow family AS A FAMILY, and F-15 (a) says a
family should be admitted at the size its members justify. For flow that may be one or two columns
in some years and zero in others, and it has never been measured.

No new data. `data/f1/f14_flow.parquet`, `f15_famA.parquet` and `f15_famB.parquet` are read
unchanged. No shipped or runner-loaded file is touched, so no deploy gate and no `--replay`.

PRE-REGISTERED CLAUSES (written before a number of this run was read; clause 0 is the prior).

0. THE PRIOR.  F-16's q50 floor sits at the MEDIAN |IC| of the 38 incumbents measured on a TRAIN
   window, which reads 0.0077-0.0148 - a high bar (F-16 c). The flow family's pooled-test |IC|s in
   F-14 ran 0.002-0.010 with `ofi_sess`, `clv_sess` and `dvol30` at the top, so I expect flow to
   clear that floor in the LATE windows only, if at all, and I expect the within-pool leg to cut
   whatever does clear it down to one or two columns because `ofi5`/`ofi30`/`ofi_sess` are one
   signal at three widths. Concretely: I expect 0-2 flow parents admitted per year, the pooled
   admitted set to be dominated by the auction columns F-16 already found (`auc_osz_adv`,
   `auc_ofade`), an abstention rate at or above F-16's 5 of 8 years, and the `pooled` arm to land
   at or slightly below F-16's causal arm ($412/day, t +1.969) because the extra candidates can
   only add columns in windows where F-16 abstained - which (F-16 a) is where abstaining was
   worth the most. I expect REFUSAL on clause 5. The honest expected outcome is "the wider pool
   does not help, and the reason is that width was never the binding constraint".

1. IDENTITY AND SAMPLE.  Same frozen learner (`GRID["mid"]`), seed, label `y_close`, 8 test years,
   decile 0.10, no hyperparameter search. Two identity checks, both of which must hold:
   (a) `base` must reproduce the frozen F-8/F-12/F-14/F-15/F-16 numbers to the printed digit:
       mean rank IC +0.01030, gross 4.256 bps, cost 2.724 bps, net $305.7/day, t +1.474,
       1,933 sessions.
   (b) `auction_only` - the pooled gate restricted to F-16's six parents - must reproduce F-16's
       per-year admitted sets exactly (none/none/none/none/none/`auc_osz_adv`/`auc_ofade`/
       `auc_ofade`). If it does not, the merge of the flow store changed the sample and the run is
       void. This is the leg that makes F-17 comparable to F-16 rather than merely similar.
   All alt columns are MERGED, never inner-joined; uncovered rows keep NaN and are KEPT.

2. CAUSALITY.  For test year Y the gate reads rows with `year <= Y - 1` and nothing else - exactly
   the train + validation data the model at Y sees. Floor, candidate ICs, candidate-incumbent
   correlations and candidate-candidate correlations are all recomputed on that window.

3. THE CANDIDATE POOL, 17 parents from two stores.  A floor test needs a per-timestamp rank IC, so
   its domain is the CROSS-SECTIONAL channel only (F-15 3b): market-level columns (`m_*`, `iv_*`)
   have no per-timestamp rank IC and are OUT OF SCOPE, not silently dropped. The pool is the 11
   own-name flow columns and the 6 own auction columns. Their `x_` and `cs_` companions are not
   separately screened - by F-15 (b) a parent is admitted with whatever companions it has, or not
   at all.

4. THE GATE, run once per test year on the clause-2 window, in this order:
   (a) FLOOR (F-15 a).  floor = MEDIAN |mean per-timestamp rank IC| over the 38 incumbents on the
       window. |IC| < floor -> REJECT. F-16 (d) settled the threshold: q50, the tighter of the two
       it measured, is worth 3x the effect at a third of the exposure. No other threshold is run.
   (b) REDUNDANCY AGAINST INCUMBENTS (F-14 a).  REJECT a candidate >= 0.50 correlated (median
       per-timestamp |Spearman|) with an incumbent whose |IC| on the same window is larger.
   (c) REDUNDANCY WITHIN THE POOL, new in F-17 and pre-registered here.  Survivors of (a) and (b)
       are taken in descending |IC| and a candidate >= 0.50 correlated with an ALREADY-ADMITTED
       candidate is REJECTED. F-16 never needed this leg: its six auction parents are six distinct
       measurements of one tape. Eleven of F-17's seventeen are the same construction at three
       horizons, and F-15's whole finding was that weak-and-numerous dilutes. The set that would
       have been admitted WITHOUT this leg is reported as a diagnostic so its cost is visible.

5. THE HURDLE, unchanged since F-8: `pooled` is adopted only on net t > 2.0 pooled AND >= 5 of 8
   test years positive AND a positive paired `pooled - base` at t > 2.0. Anything else is REFUSED.

6. ARMS.  `base`; `pooled` (the pre-registered arm, both families, clause 4a-c); `flow_only` and
   `auction_only` (the same gate restricted to one store, which decomposes `pooled` and supplies
   clause 1b); `pooled_scrambled` (F-14 b standing control: the gate runs on REAL data and admits
   the real per-year set, the fit reads those columns permuted WITHIN each timestamp - same width,
   same marginals, same schedule, no information).

7. TURNOVER CONTROL.  One decision per session, decile 0.10, in and out, so turnover is equal
   across arms and the bps columns are like-for-like. The run prints the spread.

8. REPORTED OUTCOMES, not diagnostics (F-16 a and b).  Three numbers are part of the deliverable
   whatever clause 5 says, and are printed for every gated arm:
   (a) THE ABSTENTION RATE: how many of the 8 windows admitted nothing, and what share of sessions
       the arm is therefore identical to `base` on.
   (b) THE PAIRED-ON-ACTIVE statistic: the paired effect against `base` restricted to the sessions
       where the gate admitted something, with its t and its n. Never the pooled t of an arm whose
       feature set varies by window.
   (c) WHICH parents each store contributes per year, and the mean pairwise Jaccard of the
       admitted sets.

Usage:
    INTRADAY_DATA_DIR=data/minute_alpaca python scripts/ml_f17.py --gate
    INTRADAY_DATA_DIR=data/minute_alpaca python scripts/ml_f17.py --fit
    INTRADAY_DATA_DIR=data/minute_alpaca python scripts/ml_f17.py --books --record
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from itertools import combinations
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
import ml_f14 as f14  # noqa: E402
import ml_f15 as f15  # noqa: E402
import ml_f16 as f16  # noqa: E402

LEDGER = REPO / "research" / "experiments.jsonl"
OUT = REPO / "data" / "f1"
PREDS = OUT / "f17_preds.parquet"
CELLS = OUT / "f17_arms.csv"
GATE = OUT / "f17_gate.csv"
ADMIT = OUT / "f17_admitted.json"

LABEL = "close"
EQUITY = f8.EQUITY
DECILE = f8.DECILE

#: clause 3: the cross-sectional candidate pool, by store.
PARENTS_FLOW = list(f14.OWN_FLOW)                       # 11 own-name flow columns
PARENTS_AUC = list(f15.AUC_OWN)                         # 6 own auction columns
PARENTS = PARENTS_FLOW + PARENTS_AUC
STORE = {**{c: "flow" for c in PARENTS_FLOW}, **{c: "auction" for c in PARENTS_AUC}}

#: every alt column either store can supply - the universe companions are drawn from.
ALT_ALL = list(f14.FLOW_FEATS) + list(f15.ALT_FEATS)

#: F-15 (b): an admitted parent brings its companions; a rejected one takes them away.
COMPANIONS = {p: [c for c in (f"x_{p}", f"cs_{p}") if c in set(ALT_ALL)] for p in PARENTS}

#: every column the gated arms could ever touch - the pool the scramble control permutes.
POOL = PARENTS + [c for p in PARENTS for c in COMPANIONS[p]]

CORR_DROP = 0.50            # clause 4b and 4c
FLOOR_Q = 0.50              # clause 4a, settled by F-16 (d): only q50 is run
IC_TS_SAMPLE = 4_000
CORR_TS_SAMPLE = 600


# ---------------------------------------------------------------------------- the merged panel


def load_panel(scramble: int | None = None, cols: list[str] | None = None) -> pd.DataFrame:
    """F-8's labelled panel with BOTH stores merged on (clause 1: never inner-joined).

    Flow joins on (ts, sym) - it is a 5-minute bar feature. Family A joins on (day, sym) and
    family B on (day, slot) - they are daily auction/chain features broadcast across the session.
    """
    panel = pd.read_parquet(f1.PANEL)
    p = f8.add_labels(panel)
    del panel
    n0 = len(p)

    flow = pd.read_parquet(f14.FLOW)
    flow["ts"] = pd.to_datetime(flow["ts"])
    p = p.merge(flow, on=["ts", "sym"], how="left")
    assert len(p) == n0, "the flow merge duplicated rows - (ts, sym) is not unique in the store"
    del flow

    a = pd.read_parquet(OUT / "f15_famA.parquet")
    b = pd.read_parquet(OUT / "f15_famB.parquet")
    p["_day"] = pd.to_datetime(p["ts"]).dt.date
    a["day"] = pd.to_datetime(a["day"]).dt.date
    b["day"] = pd.to_datetime(b["day"]).dt.date
    p = p.merge(a.rename(columns={"day": "_day"}), on=["_day", "sym"], how="left")
    p = p.merge(b.rename(columns={"day": "_day"}), on=["_day", "slot"], how="left")
    assert len(p) == n0, "the alt merge duplicated rows"

    for c in ALT_ALL:
        p[c] = p[c].astype("float32")
    print(f"panel {len(p):,} rows; flow coverage {100 * p['ofi30'].notna().mean():.2f}%, "
          f"auction coverage {100 * p['auc_cdrift'].notna().mean():.2f}%, "
          f"chain coverage {100 * p['iv_strad'].notna().mean():.2f}% "
          f"(uncovered rows carry NaN and are KEPT, clause 1)")

    if scramble is not None:
        rng = np.random.default_rng(scramble)
        tgt = cols or POOL
        print(f"clause 6 control: permuting {len(tgt)} alt columns within each timestamp")
        for c in tgt:
            p[c] = (p.groupby("ts", sort=False)[c]
                    .transform(lambda s: rng.permutation(s.to_numpy())).astype("float32"))
    return p


# ------------------------------------------------------------------------- clauses 2-4: the gate


def causal_gate(p: pd.DataFrame, year: int, verbose: bool = True) -> tuple[dict, list[dict]]:
    """Clause 2 + 4: the gate on `year <= year - 1` only.

    Returns (admitted per store-restriction, per-candidate rows). The three restrictions - `flow`,
    `auction`, `pooled` - share one pass over the window: legs (a) and (b) are per-candidate and
    identical across restrictions, and only leg (c), which is greedy over the surviving set, has
    to be replayed per restriction.
    """
    w = p[p["year"] <= year - 1].dropna(subset=["y_close"])
    wi = f16._subsample_ts(w, IC_TS_SAMPLE)
    wc = f16._subsample_ts(w, CORR_TS_SAMPLE)
    inc = list(f1.FEATURES)

    inc_ic = {c: f16._ic(wi, c)[0] for c in inc}
    floor = float(np.nanquantile([abs(v) for v in inc_ic.values()], FLOOR_Q))

    rows = []
    for c in PARENTS:
        m, t = f16._ic(wi, c)
        best_c, best_n = 0.0, ""
        for j in inc:
            cs = f15._per_ts_spearman(wc, c, j)
            v = float(np.nanmedian(np.abs(cs))) if len(cs) else np.nan
            if np.isfinite(v) and v > best_c:
                best_c, best_n = v, j
        redundant = bool(best_c >= CORR_DROP and abs(inc_ic.get(best_n, 0.0)) >= abs(m))
        below = not (np.isfinite(m) and abs(m) >= floor)
        rows.append({"year": int(year), "store": STORE[c], "feature": c, "ic": m, "ic_t": t,
                     "max_corr": best_c, "vs": best_n, "floor": floor,
                     "verdict_ab": "below floor" if below else
                                   ("redundant" if redundant else "survives"),
                     "pass_ab": bool(not below and not redundant)})
        if verbose:
            print(f"    {STORE[c]:<8} {c:<14} IC {m:+.5f} (t {t:+6.1f})  max|rho| {best_c:.3f} "
                  f"vs {best_n:<10} -> {rows[-1]['verdict_ab']}", flush=True)

    surv = sorted([r for r in rows if r["pass_ab"]], key=lambda r: -abs(r["ic"]))
    by_feat = {r["feature"]: r for r in rows}
    admitted, kept_par, dropped_c, displaced = {}, {}, {}, {}
    for restrict in ("pooled", "flow", "auction"):
        pool = [r for r in surv if restrict == "pooled" or r["store"] == restrict]
        keep, drops, disp = [], [], {}
        for r in pool:                                              # clause 4c, greedy on |IC|
            worst, blocker = 0.0, ""
            for k in keep:
                cs = f15._per_ts_spearman(wc, r["feature"], k)
                v = float(np.nanmedian(np.abs(cs))) if len(cs) else np.nan
                if np.isfinite(v) and v > worst:
                    worst, blocker = v, k
            if worst >= CORR_DROP:
                drops.append((r["feature"], round(worst, 3)))
                # F-23: an admission is not a property of its candidate. Record, against the
                # column that blocked this one, WHAT it blocked - the rival's |IC|, the pair's
                # median per-timestamp |Spearman|, and the |IC| margin the decision turned on.
                prev = disp.get(blocker)
                if prev is None or abs(r["ic"]) > abs(prev["rival_ic"]):
                    disp[blocker] = {"rival": r["feature"], "rival_ic": r["ic"],
                                     "rival_ic_t": r["ic_t"], "pair_rho": worst,
                                     "gap": abs(by_feat[blocker]["ic"]) - abs(r["ic"])}
            else:
                keep.append(r["feature"])
        kept_par[restrict] = keep
        dropped_c[restrict] = drops
        displaced[restrict] = disp
        admitted[restrict] = [x for c in keep for x in [c] + COMPANIONS[c]]

    if verbose:
        print(f"    window {len(w):,} rows, {w['year'].min()}-{w['year'].max()}; "
              f"floor q50 {floor:.5f}; {len(surv)} of {len(PARENTS)} survive (a)+(b): "
              f"{[r['feature'] for r in surv] or 'none'}")
        for restrict in ("pooled", "flow", "auction"):
            print(f"    ADMITTED[{restrict:<8}] parents {kept_par[restrict] or 'none'}"
                  + (f"  (clause 4c dropped {dropped_c[restrict]})"
                     if dropped_c[restrict] else ""))
            for c in kept_par[restrict]:
                print("      " + describe_admission(by_feat[c], displaced[restrict].get(c), floor))
    for r in rows:
        r["admitted_pooled"] = r["feature"] in kept_par["pooled"]
        r["dropped_4c"] = r["pass_ab"] and r["feature"] not in kept_par["pooled"]
        d = displaced["pooled"].get(r["feature"])
        r["displaced"] = d["rival"] if d else ""
        r["displaced_ic"] = d["rival_ic"] if d else float("nan")
        r["displaced_rho"] = d["pair_rho"] if d else float("nan")
        r["displaced_gap"] = d["gap"] if d else float("nan")
        r["floor_margin"] = abs(r["ic"]) - floor
        r["ic_se"] = ic_se(r)
        r["resolved"] = resolution(r, d)
    return admitted, rows


# ------------------------------------------------------------- F-23: is the admission resolvable?


def ic_se(r: dict) -> float:
    """Standard error of a candidate's mean per-timestamp rank IC, backed out of its own t.

    `f16._ic` returns (mean, t) with t = mean / se, so se = |mean| / |t| and no second pass over
    the window is needed.
    """
    m, t = r.get("ic"), r.get("ic_t")
    if m is None or t is None or not np.isfinite(m) or not np.isfinite(t) or t == 0:
        return float("nan")
    return abs(float(m)) / abs(float(t))


def resolution(r: dict, d: dict | None) -> str:
    """F-23's cheap rule, pre-registered by F-23 and first used here.

    An admission whose |IC| margin over the rival it displaced is smaller than the CANDIDATE'S OWN
    IC standard error is reported as UNRESOLVED rather than as an admission: the gate cannot tell
    the two columns apart, so the arm downstream is one draw from a coin flip and its result must
    not be read as a property of the column that happened to win.
    """
    if not r.get("admitted_pooled"):
        return ""
    if d is None:
        return "UNCONTESTED"
    se = ic_se(r)
    if not np.isfinite(se) or not np.isfinite(d["gap"]):
        return "UNRESOLVED"
    return "RESOLVED" if abs(d["gap"]) > se else "UNRESOLVED"


def describe_admission(r: dict, d: dict | None, floor: float) -> str:
    """One line per admission: what it beat, by how much, and whether that margin is readable."""
    margin = abs(r["ic"]) - floor
    head = (f"{r['feature']:<14} |IC| {abs(r['ic']):.5f} (se {ic_se(r):.5f}, "
            f"{margin:+.5f} over the floor)")
    if d is None:
        return head + "  displaced nothing -> UNCONTESTED"
    verdict = "RESOLVED" if (np.isfinite(ic_se(r)) and abs(d["gap"]) > ic_se(r)) else "UNRESOLVED"
    return (head + f"  displaced {d['rival']:<12} |IC| {abs(d['rival_ic']):.5f} "
            f"at |rho| {d['pair_rho']:.3f}; gap {d['gap']:+.5f} -> {verdict}")


def gate() -> None:
    p = load_panel()
    p = p.dropna(subset=["y_close"]).copy()
    years = [y for y in sorted(p["year"].unique()) if y >= f8.FIRST_TEST_YEAR]
    all_rows, admit = [], {k: {} for k in ("pooled", "flow", "auction")}
    for year in years:
        print(f"\n--- gate for test year {year} (reads year <= {year - 1} only)")
        t0 = time.time()
        a, rows = causal_gate(p, year)
        for k in admit:
            admit[k][str(year)] = a[k]
        all_rows += rows
        print(f"    ({time.time() - t0:.0f}s)")
    GATE.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(all_rows).to_csv(GATE, index=False)
    ADMIT.write_text(json.dumps(admit, indent=1), encoding="utf-8")
    for k in admit:
        report_admitted(admit[k], k)
    check_identity_1b(admit["auction"])
    print(f"\nwritten: {GATE}\nwritten: {ADMIT}")


def check_identity_1b(auction: dict[str, list[str]]) -> bool:
    """Clause 1(b): the pooled run's auction-only gate must reproduce F-16's admitted sets."""
    ref_path = OUT / "f16_admitted.json"
    if not ref_path.exists():
        print("\nclause 1(b): F-16's admitted sets are not on disk - identity check SKIPPED")
        return False
    ref = json.loads(ref_path.read_text(encoding="utf-8")).get("q50", {})
    ok = True
    print("\n=== clause 1(b): auction-only gate against F-16's q50 admitted sets ===")
    for y in sorted(set(ref) | set(auction)):
        a = sorted(c for c in auction.get(y, []) if c in PARENTS)
        b = sorted(c for c in ref.get(y, []) if c in PARENTS)
        same = a == b
        ok &= same
        print(f"  {y}: F-17 {', '.join(a) or '(none)':<28} F-16 {', '.join(b) or '(none)':<20} "
              f"{'match' if same else 'DIFFER'}")
    print(f"  clause 1(b): {'PASS - the flow merge did not change the sample' if ok else 'FAIL'}")
    return ok


def report_admitted(admit: dict[str, list[str]], name: str) -> dict:
    """Clause 8(c) + 8(a): what was admitted, by year and by store, and how often nothing was."""
    print(f"\n=== clause 8: what the causal gate admits under `{name}`, by test year ===")
    par = {y: [c for c in v if c in PARENTS] for y, v in admit.items()}
    for y, v in sorted(par.items()):
        fl = [c for c in v if STORE[c] == "flow"]
        au = [c for c in v if STORE[c] == "auction"]
        print(f"  {y}: {len(v)} parents -> flow {fl or '-'} | auction {au or '-'}")
    sets = [set(v) for _, v in sorted(par.items())]
    js = [len(a & b) / len(a | b) if (a | b) else 1.0 for a, b in combinations(sets, 2)]
    empty = sum(not s for s in sets)
    flow_yrs = sum(any(STORE[c] == "flow" for c in s) for s in sets)
    always = set.intersection(*sets) if sets and all(sets) else set()
    print(f"  clause 8(a) ABSTENTION: {empty}/{len(sets)} windows admitted NOTHING")
    print(f"  flow contributes at least one parent in {flow_yrs}/{len(sets)} windows")
    print(f"  mean pairwise Jaccard: {np.mean(js):+.3f} ({min(js):.3f}..{max(js):.3f})")
    print(f"  admitted in EVERY year: {sorted(always) if always else 'none'}")
    return {"jaccard": float(np.mean(js)), "empty": int(empty), "flow_years": int(flow_yrs),
            "always": sorted(always), "per_year": {y: sorted(v) for y, v in par.items()}}


# ------------------------------------------------------------------------------ clause 6: fit


#: arm -> (which admitted set it uses, whether it reads the scrambled panel)
ARMS = {"base": (None, False),
        "pooled": ("pooled", False),             # the pre-registered arm
        "flow_only": ("flow", False),
        "auction_only": ("auction", False),      # clause 1(b) reference
        "pooled_scrambled": ("pooled", True)}    # F-14 (b) control


def _add_for(arm: str, year: int, admit: dict) -> list[str]:
    which = ARMS[arm][0]
    return [] if which is None else list(admit[which].get(str(year), []))


def fit(only: list[str] | None = None) -> None:
    if not ADMIT.exists():
        raise SystemExit("run --gate first")
    admit = json.loads(ADMIT.read_text(encoding="utf-8"))
    params = dict(f1.GRID["mid"])
    base = list(f1.FEATURES)
    want = [a for a in ARMS if only is None or a in only]
    frames, ics = [], []
    reuse: dict[int, pd.DataFrame] = {}
    reuse_ic: dict[int, dict] = {}

    for scr in (None, 0):
        arms = [a for a in want if ARMS[a][1] == (scr is not None)]
        if not arms:
            continue
        p = load_panel(scramble=scr, cols=POOL)
        p = p.dropna(subset=["y_close"]).copy()
        p["y"] = p["y_close"]
        years = [y for y in sorted(p["year"].unique()) if y >= f8.FIRST_TEST_YEAR]
        saved = list(f1.FEATURES)
        try:
            for arm in arms:
                print(f"\n--- arm {arm}")
                for year in years:
                    add = [c for c in _add_for(arm, year, admit) if c not in base]
                    feats = base + add
                    trn, vld, tst = (p[p.year <= year - 2], p[p.year == year - 1],
                                     p[p.year == year])
                    if not (len(trn) and len(vld) and len(tst)):
                        continue
                    #: the fit is deterministic in the data, the features and the seed, so an arm
                    #: with an empty admitted set IS the base fit - copy it, do not re-spend it.
                    if not add and arm != "base" and int(year) in reuse:
                        k = reuse[int(year)].copy()
                        k["arm"] = arm
                        frames.append(k)
                        r = reuse_ic[int(year)]
                        ics.append({**r, "arm": arm})
                        print(f"  {year}: 38 feats, admitted set EMPTY -> identical to base "
                              f"(rank IC {r['ic']:+.5f}), reused", flush=True)
                        continue
                    f1.FEATURES = feats
                    t0 = time.time()
                    model, pt = f1.fit_predict(trn, vld, tst, dict(params))
                    icm, ict = f1.ic_stats(tst, pt)
                    row = {"arm": arm, "year": int(year), "ic": icm, "ic_t": ict,
                           "n_feat": len(feats)}
                    ics.append(row)
                    k = tst[["ts", "day", "year", "sym", "slot", "entry_px", "fwd"]].copy()
                    k["arm"] = arm
                    k["pred"] = pt
                    frames.append(k)
                    if arm == "base":
                        reuse[int(year)] = k
                        reuse_ic[int(year)] = dict(row)
                    print(f"  {year}: {len(feats):>2} feats  train<={year-2} ({len(trn):,}) "
                          f"test ({len(tst):,})  iters {model.n_iter_:>4}  "
                          f"rank IC {icm:+.5f} (t {ict:+.1f})  ({time.time()-t0:.0f}s)",
                          flush=True)
        finally:
            f1.FEATURES = saved
        del p

    out = pd.concat(frames, ignore_index=True)
    if only is not None and PREDS.exists():
        old = pd.read_parquet(PREDS)
        out = pd.concat([old[~old["arm"].isin(set(out["arm"]))], out], ignore_index=True)
    out.to_parquet(PREDS, index=False)
    icd = pd.DataFrame(ics)
    print("\n=== per-timestamp rank IC on y_close, by arm and test year ===")
    piv = icd.pivot(index="year", columns="arm", values="ic")
    print(piv.round(5).to_string())
    print("mean " + "  ".join(f"{a} {piv[a].mean():+.5f}" for a in piv.columns))
    print("\nfeature count by arm and year")
    print(icd.pivot(index="year", columns="arm", values="n_feat").to_string())
    print(f"\nwritten: {PREDS}")


# ---------------------------------------------------------------------------- clauses 5-8: books


def record(tag: str, r: dict, sess: pd.DataFrame, params: dict, extra: dict) -> None:
    net = sess["net"].to_numpy()
    n = len(sess)
    ret = net / EQUITY
    sd = ret.std(ddof=1) if n > 1 else 0.0
    rec = {"ts": dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
           "algorithm": "intraday/f17_poolgate", "class": "ml", "tag": tag, "commit": "",
           "run_dir": "", "track": "F-17", "params": params,
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


def books(record_rows: bool = False) -> None:
    preds = pd.read_parquet(PREDS)
    preds["ts"] = pd.to_datetime(preds["ts"])
    admit = json.loads(ADMIT.read_text(encoding="utf-8"))
    reg = f14.market_regime()
    arms = [a for a in ARMS if a in set(preds["arm"])]

    print(f"costed against {ic.DATA_DIR}")
    sess, rows = {}, []
    for arm in arms:
        sess[arm] = f8.simulate(f14.frame_for(preds, arm), "session", decile=DECILE)
        rows.append(f8.summarize(sess[arm], f"session/{arm}"))

    print("\n=== clause 5: F-8's session book, one decision per session, held to the flatten ===")
    f8.print_table(rows)

    tv = pd.Series({a: sess[a]["turnover"].mean() for a in arms})
    print(f"\nclause 7: turnover spread across arms ${tv.max() - tv.min():,.0f} "
          f"(mean ${tv.mean():,.0f})")

    print("\n=== net $/day by test year ===")
    yr = pd.DataFrame({a: f14.by_year(sess[a]) for a in arms})
    print(yr.to_string())
    print("years positive: " + "  ".join(f"{a} {int((yr[a] > 0).sum())}/{len(yr)}" for a in arms))

    print("\n=== paired per session against base ===")
    pairs = {a: f14.paired(sess["base"], sess[a], f"{a} - base") for a in arms if a != "base"}

    print("\n=== clause 8(a)+(b): abstention and the paired effect ON ACTIVE SESSIONS ONLY ===")
    yrs = pd.to_datetime(sess["base"]["day"]).dt.year.to_numpy()
    active = {}
    for arm in arms:
        key = ARMS[arm][0]
        if key is None:
            continue
        act = np.array([bool(admit[key].get(str(y), [])) for y in yrs])
        d = sess[arm]["net"].to_numpy() - sess["base"]["net"].to_numpy()
        assert np.allclose(d[~act], 0.0), f"{arm} moved in a year with an empty admitted set"
        empty_y = sum(1 for y in sorted(set(yrs)) if not admit[key].get(str(y), []))
        t_act = f1.tstat(d[act]) if act.sum() > 2 else float("nan")
        active[arm] = {"n_active": int(act.sum()), "empty_years": int(empty_y),
                       "d_active": float(d[act].mean()) if act.sum() else 0.0, "t_active": t_act}
        print(f"  {arm:<18} abstains in {empty_y}/{len(set(yrs))} windows; active on "
              f"{act.sum():>4}/{len(act)} sessions ({100 * act.mean():.0f}%)")
        print(f"  {'':<18} paired on ACTIVE only: {active[arm]['d_active']:>+8,.0f}/day "
              f"(t {t_act:+.2f}); spread over the whole sample "
              f"{d[act].sum() / len(act):>+7,.0f}/day")

    print("\n=== regimes: terciles of SPY trailing 20-session realised vol ===")
    print(f"{'cell':<18}" + "".join(f"{k:>12}" for k in ("low", "mid", "high")))
    for arm in arms:
        s = sess[arm].copy()
        s["reg"] = s["day"].astype(str).map(reg)
        m = s.groupby("reg")["net"].mean()
        print(f"{arm:<18}" + "".join(f"{m.get(k, float('nan')):>12,.0f}"
                                    for k in ("low", "mid", "high")))

    stab = {k: report_admitted(admit[k], k) for k in admit}
    check_identity_1b(admit["auction"])

    lut = {x["label"]: x for x in rows}
    r, b = lut["session/pooled"], lut["session/base"]
    n_pos = int((yr["pooled"] > 0).sum())
    dp = pairs.get("pooled", {})
    ok = (r["t"] > 2.0) and (n_pos >= 5) and (dp.get("d_net_t", -9) > 2.0)
    print("\n=== clause 5: the pre-registered pass rule (pooled arm only) ===")
    print(f"  net t > 2.0                : {r['t']:+.3f}   {'PASS' if r['t'] > 2 else 'FAIL'}")
    print(f"  >= 5 of {len(yr)} years positive   : {n_pos}/{len(yr)}      "
          f"{'PASS' if n_pos >= 5 else 'FAIL'}")
    print(f"  paired pooled-base t > 2.0 : {dp.get('d_net_t', float('nan')):+.3f}   "
          f"{'PASS' if dp.get('d_net_t', -9) > 2 else 'FAIL'}")
    print(f"\nDECISION: {'ACCEPT' if ok else 'REFUSE'}  "
          f"(base t {b['t']:+.3f} -> pooled t {r['t']:+.3f})")

    CELLS.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(CELLS, index=False)
    if record_rows:
        for x in rows:
            arm = x["label"].split("/")[1]
            key = ARMS[arm][0]
            record(f"F-17 {x['label']}: F-16's causal gate over the POOLED 17-parent candidate "
                   f"space (flow + auction), selection causal on train+validation only",
                   x, sess[arm],
                   {"arm": arm, "label": LABEL, "decile": DECILE, "learner": "mid",
                    "pool": len(PARENTS), "floor_q": FLOOR_Q},
                   {"Admitted": json.dumps(stab.get(key or "", {}).get("per_year", {})),
                    "Abstention": json.dumps(active.get(arm, {})),
                    "Jaccard": f"{stab.get(key or 'pooled', {}).get('jaccard', float('nan')):.3f}",
                    "Paired vs base": json.dumps(pairs.get(arm, {}))})
        print(f"\nrecorded {len(rows)} DIAGNOSTIC rows -> {LEDGER}")
    print(f"cells -> {CELLS}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--fit", action="store_true")
    ap.add_argument("--arms", default=None, help="comma-separated subset for --fit")
    ap.add_argument("--books", action="store_true")
    ap.add_argument("--record", action="store_true")
    a = ap.parse_args()
    if a.gate:
        gate()
    if a.fit:
        fit(only=a.arms.split(",") if a.arms else None)
    if a.books:
        books(record_rows=a.record)
    if not (a.gate or a.fit or a.books):
        ap.print_help()


if __name__ == "__main__":
    main()
