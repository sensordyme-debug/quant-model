"""F-16: make the gate CAUSAL. Run the screen INSIDE the walk-forward, at every retrain.

F-15 measured that 19 columns of a new store cost the book -$148/day while 3 of those 19 gained
+$60/day, posted the highest gross this track has recorded on this label (4.643 bps against base's
4.256) and were the first arm ever positive in the low-vol tercile. But the 3 columns were chosen
AFTER reading the test window. `lean3` is therefore a selection artefact, not a result, and
F-15's own closing sentence says so.

F-16 is the one experiment that can tell the two apart. The gate that picked those 3 columns -
F-14 (a)'s correlation rule plus F-15 (a)'s incumbent-floor rule - is re-run at every retrain on
TRAIN + VALIDATION ONLY, the survivors are admitted, and the model is fit on them. Nothing in the
feature-selection path may see the year it trades. If the causal selection reproduces `lean3`, the
auction tape is a real addition to the panel and F-14's closing statement ("this panel does not
support a t = 2 book") needs rewriting. If the admitted set churns from year to year, then
F-15 (9)'s importance collapse is the whole story and F-14 stands as written.

No new data: `data/f1/f15_famA.parquet` and `f15_famB.parquet` are read unchanged.

PRE-REGISTERED CLAUSES (written before a number of this run was read; clause 0 is the prior).

0. THE PRIOR.  I expect the causal gate to admit 2-4 parent columns per year, and `auc_ofade` -
   F-15's survivor, |IC| 0.0069, sign-stable in 7 of 8 test years - to be admitted in at least 6 of
   the 8. I expect `auc_ojump` to be admitted in most years too: it is 0.905 correlated with `gap`
   but carries 6x `gap`'s |IC|, so F-14 (a) as written keeps it. I expect the per-year admitted
   sets to be moderately stable (mean pairwise Jaccard 0.5-0.8), which would be a much better
   number than F-15 (9)'s importance collapse (+0.001) and is the reportable finding either way.
   I expect the `causal` arm to land BETWEEN base ($306/day) and the oracle `lean3` ($365/day),
   say $280-$380/day at t +1.3 to +1.8, and to be REFUSED on clause 5 - because no arm of any
   construction this track has ever fitted has reached t = 2.0, and a causal selection can only be
   weaker than the oracle one it is imitating. The honest expected outcome is "mechanism partly
   confirmed, significance not reached".

1. IDENTITY AND SAMPLE.  F-15's `load_panel` unchanged: alt columns MERGED, never inner-joined,
   uncovered rows kept carrying NaN. The `base` arm must reproduce F-8/F-12/F-14/F-15's frozen
   numbers to the printed digit: mean rank IC +0.01030, gross 4.256 bps, cost 2.724 bps, net
   $305.7/day, t +1.474, 1,933 sessions. Same learner (`GRID["mid"]`), same seed, same label
   `y_close`, same 8 test years, no hyperparameter search.

2. CAUSALITY OF THE SELECTION, which is the whole point.  For test year Y the gate reads rows with
   `year <= Y - 1` and nothing else - exactly the train + validation data the model at Y sees. The
   floor, the candidate ICs and the candidate-incumbent correlations are all recomputed on that
   window. The feature columns themselves are already causal by F-15 clause 2 and are unchanged.

3. THE CANDIDATE POOL, and why it is 6 and not 19.  A floor test needs a per-timestamp rank IC, so
   its domain is the CROSS-SECTIONAL channel only. F-15 (3b) established that a market-level
   column's per-timestamp rank IC is undefined, not zero; `m_auc_*` and the whole `iv_*` family B
   therefore cannot be screened by this gate and are OUT OF SCOPE for F-16, not silently dropped.
   The pool is the 6 own auction columns: `auc_osz_z`, `auc_osz_adv`, `auc_ofade`, `auc_ojump`,
   `auc_csz_z`, `auc_cdrift`. Their `x_` and `cs_` companions are NOT separately screened - by
   F-15 (b), a column is admitted as a TRIPLE or not at all, so an admitted parent brings whatever
   companions exist for it and a rejected parent takes its companions with it.

4. THE GATE, run once per test year on the clause-2 window, in this order:
   (a) FLOOR (F-15 a).  Compute the mean per-timestamp rank IC of all 38 incumbents on the window.
       floor = the MEDIAN of |IC| over the 38. A candidate with |IC| < floor is REJECTED. This is
       the leg F-14 did not have and the leg that would have admitted 3 of 19 rather than 19.
   (b) REDUNDANCY (F-14 a).  Max median per-timestamp |Spearman| against each of the 38. REJECT a
       candidate that is >= 0.50 correlated with an incumbent whose |IC| on the same window is
       larger. Order matters only for reporting; both legs must pass.
   (c) The admitted set is the survivors plus their companions, and it is recorded per year.

5. THE HURDLE, unchanged since F-8: `causal` is adopted only on net t > 2.0 pooled AND >= 5 of 8
   test years positive AND a positive paired `causal - base` at t > 2.0. Anything else is REFUSED.

6. CONTROLS AND REFERENCE ARMS.
   - `causal_scrambled` (F-14 b, standing procedure): the gate runs on the REAL data and admits
     the real per-year set, but the fit reads those columns permuted WITHIN each timestamp. Same
     width, same marginals, same per-year schedule, no information. It separates "the causal gate
     found signal" from "the causal gate found width".
   - `lean3` (F-15 7): the oracle, test-set-selected, fixed at all years. Barred from clause 5 -
     it cannot accept anything. It is the number `causal` is trying to reproduce honestly, and
     printing both in one run makes the comparison exact rather than cross-run.
   - `causal_p25`: ADDED AFTER the q50 gate pass was read (see the note on FLOOR_Q) and therefore
     NOT pre-registered and barred from clause 5. The median-incumbent floor turned out to admit
     nothing in most years, which makes the pre-registered arm nearly a copy of base; the 25th
     percentile of the same incumbent |IC| distribution is the same rule at a looser threshold,
     still computed on train + validation only. It exists so the run can say whether the finding
     is a property of the auction tape or of my choice of threshold.

7. TURNOVER CONTROL.  One decision per session, decile 0.10, in and out, so turnover is equal
   across arms to the dollar and the bps columns are like-for-like. The run prints the spread.

8. THE SECONDARY DELIVERABLE, which is reportable whatever clause 5 says: WHICH columns the causal
   gate admits in each year, the mean pairwise Jaccard of those sets, and whether `auc_ofade` -
   the oracle's pick - is among them. That answers the mechanism question even if the book does
   not move.

Usage:
    INTRADAY_DATA_DIR=data/minute_alpaca python scripts/ml_f16.py --gate
    INTRADAY_DATA_DIR=data/minute_alpaca python scripts/ml_f16.py --fit
    INTRADAY_DATA_DIR=data/minute_alpaca python scripts/ml_f16.py --books --record
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

LEDGER = REPO / "research" / "experiments.jsonl"
OUT = REPO / "data" / "f1"
PREDS = OUT / "f16_preds.parquet"
CELLS = OUT / "f16_arms.csv"
GATE = OUT / "f16_gate.csv"
ADMIT = OUT / "f16_admitted.json"

LABEL = "close"
EQUITY = f8.EQUITY
DECILE = f8.DECILE

#: clause 3: the cross-sectional candidate pool - the 6 own auction columns, nothing else.
PARENTS = ["auc_osz_z", "auc_osz_adv", "auc_ofade", "auc_ojump", "auc_csz_z", "auc_cdrift"]

#: clause 3 / F-15 (b): an admitted parent brings its companions; a rejected one takes them away.
COMPANIONS = {p: [c for c in (f"x_{p}", f"cs_{p}") if c in set(f15.ALT_FEATS)] for p in PARENTS}

#: every column the causal arm could ever touch - the pool the scramble control permutes.
POOL = PARENTS + [c for p in PARENTS for c in COMPANIONS[p]]

CORR_DROP = 0.50            # clause 4b, F-14 (a) as written
IC_TS_SAMPLE = 4_000        # timestamps used for the floor and candidate ICs
CORR_TS_SAMPLE = 600        # timestamps used for the candidate-incumbent correlations


def _subsample_ts(p: pd.DataFrame, n: int) -> pd.DataFrame:
    ts = pd.Index(sorted(p["ts"].unique()))
    if len(ts) <= n:
        return p
    keep = ts[:: max(1, len(ts) // n)]
    return p[p["ts"].isin(keep)]


def _ic(df: pd.DataFrame, col: str) -> tuple[float, float]:
    per = f15._per_ts_spearman(df, col, "y_close")
    if len(per) < 30:
        return float("nan"), float("nan")
    return float(per.mean()), f1.tstat(per)


#: clause 4a is a quantile of the incumbent |IC| distribution. `q50` (the median incumbent) is the
#: PRE-REGISTERED floor. `q25` is a SECOND SPECIFICATION added after the q50 pass was seen to be
#: nearly degenerate - it is still computed causally on train+validation only, but it was not
#: pre-registered, so it is a robustness arm and is barred from clause 5.
FLOOR_Q = {"q50": 0.50, "q25": 0.25}


def causal_gate(p: pd.DataFrame, year: int, verbose: bool = True) -> tuple[dict, list[dict]]:
    """Clause 2 + 4: the gate on `year <= year - 1` only. Returns (admitted per floor, rows)."""
    w = p[(p["year"] <= year - 1)].dropna(subset=["y_close"])
    wi = _subsample_ts(w, IC_TS_SAMPLE)
    wc = _subsample_ts(w, CORR_TS_SAMPLE)
    inc = list(f1.FEATURES)

    inc_ic = {c: _ic(wi, c)[0] for c in inc}
    absic = [abs(v) for v in inc_ic.values()]
    floors = {k: float(np.nanquantile(absic, q)) for k, q in FLOOR_Q.items()}
    strongest = max(inc_ic, key=lambda c: abs(inc_ic[c]))

    rows, admitted = [], {k: [] for k in floors}
    for c in PARENTS:
        m, t = _ic(wi, c)
        best_c, best_n = 0.0, ""
        for j in inc:
            cs = f15._per_ts_spearman(wc, c, j)
            v = float(np.nanmedian(np.abs(cs))) if len(cs) else np.nan
            if np.isfinite(v) and v > best_c:
                best_c, best_n = v, j
        redundant = bool(best_c >= CORR_DROP and abs(inc_ic.get(best_n, 0.0)) >= abs(m))
        row = {"year": int(year), "feature": c, "ic": m, "ic_t": t, "max_corr": best_c,
               "vs": best_n, "redundant": redundant}
        for k, fl in floors.items():
            keep = bool(np.isfinite(m) and abs(m) >= fl) and not redundant
            row[f"floor_{k}"] = fl
            row[f"verdict_{k}"] = "keep" if keep else (
                "redundant" if redundant else "below floor")
            if keep:
                admitted[k] += [c] + COMPANIONS[c]
        rows.append(row)
        if verbose:
            print(f"    {c:<14} IC {m:+.5f} (t {t:+5.1f})  max|rho| {best_c:.3f} "
                  f"vs {best_n:<10} -> q50 {row['verdict_q50']:<11} q25 {row['verdict_q25']}",
                  flush=True)
    if verbose:
        print(f"    window {len(w):,} rows, {w['year'].min()}-{w['year'].max()}; floors "
              + ", ".join(f"{k} {v:.5f}" for k, v in floors.items())
              + f"; strongest incumbent {strongest} |IC| {abs(inc_ic[strongest]):.5f}")
        for k in floors:
            print(f"    ADMITTED[{k}] {len(admitted[k])}: {admitted[k]}", flush=True)
    return admitted, rows


def gate() -> None:
    """Clause 4 and 8: run the causal gate for every test year and record the admitted sets."""
    p = f15.load_panel()
    p = p.dropna(subset=["y_close"]).copy()
    years = [y for y in sorted(p["year"].unique()) if y >= f8.FIRST_TEST_YEAR]
    all_rows, admit = [], {k: {} for k in FLOOR_Q}
    for year in years:
        print(f"\n--- gate for test year {year} (reads year <= {year - 1} only)")
        t0 = time.time()
        a, rows = causal_gate(p, year)
        for k in FLOOR_Q:
            admit[k][str(year)] = a[k]
        all_rows += rows
        print(f"    ({time.time() - t0:.0f}s)")
    GATE.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(all_rows).to_csv(GATE, index=False)
    ADMIT.write_text(json.dumps(admit, indent=1), encoding="utf-8")
    for k in FLOOR_Q:
        report_admitted(admit[k], k)
    print(f"\nwritten: {GATE}\nwritten: {ADMIT}")


def report_admitted(admit: dict[str, list[str]], floor: str = "q50") -> dict:
    """Clause 8: the secondary deliverable - stability of the causally admitted set."""
    print(f"\n=== clause 8: what the CAUSAL gate admits at floor {floor}, by test year ===")
    par = {y: [c for c in v if c in PARENTS] for y, v in admit.items()}
    for y, v in sorted(par.items()):
        print(f"  {y}: {len(v)} parents -> {', '.join(v) if v else '(none)'}")
    sets = [set(v) for _, v in sorted(par.items())]
    js = [len(a & b) / len(a | b) if (a | b) else 1.0 for a, b in combinations(sets, 2)]
    ofade = sum("auc_ofade" in s for s in sets)
    always = set.intersection(*sets) if sets and all(sets) else set()
    print(f"  mean pairwise Jaccard of the admitted parent sets: {np.mean(js):+.3f} "
          f"({min(js):.3f}..{max(js):.3f})")
    print(f"  the oracle's pick `auc_ofade` admitted in {ofade}/{len(sets)} years")
    print(f"  admitted in EVERY year: {sorted(always) if always else 'none'}")
    return {"jaccard": float(np.mean(js)), "ofade_years": int(ofade),
            "always": sorted(always), "per_year": {y: sorted(v) for y, v in par.items()}}


# ------------------------------------------------------------------------------- clause 4-6: fit


#: arm -> (which admitted set it uses, whether it reads the scrambled panel)
ARMS = {"base": (None, False),
        "causal": ("q50", False),            # the pre-registered arm
        "causal_p25": ("q25", False),        # the robustness specification, barred from clause 5
        "causal_scrambled": ("q50", True),   # F-14 (b) control: same width, no information
        "lean3": ("lean3", False)}           # F-15's oracle, test-set-selected, barred


def _add_for(arm: str, year: int, admit: dict) -> list[str]:
    which = ARMS[arm][0]
    if which is None:
        return []
    if which == "lean3":
        return list(f15.LEAN_ARMS["lean3"])
    return list(admit[which].get(str(year), []))


def fit() -> None:
    if not ADMIT.exists():
        raise SystemExit("run --gate first")
    admit = json.loads(ADMIT.read_text(encoding="utf-8"))
    params = dict(f1.GRID["mid"])
    base = list(f1.FEATURES)
    frames, ics = [], []
    #: (arm, year) whose feature set is exactly `base`: the fit is deterministic in the data, the
    #: features and the seed, so it IS the base fit. Copy it rather than spending the minute again.
    reuse: dict[tuple[str, int], pd.DataFrame] = {}

    for scr in (None, 0):
        arms = [a for a in ARMS if ARMS[a][1] == (scr is not None)]
        p = f15.load_panel(scramble=scr, cols=POOL)
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
                    if not add and arm != "base" and ("base", int(year)) in reuse:
                        k = reuse[("base", int(year))].copy()
                        k["arm"] = arm
                        frames.append(k)
                        r = next(x for x in ics if x["arm"] == "base" and x["year"] == year)
                        ics.append({**r, "arm": arm})
                        print(f"  {year}: 38 feats, admitted set EMPTY -> identical to base "
                              f"(rank IC {r['ic']:+.5f}), reused", flush=True)
                        continue
                    f1.FEATURES = feats
                    t0 = time.time()
                    model, pt = f1.fit_predict(trn, vld, tst, dict(params))
                    icm, ict = f1.ic_stats(tst, pt)
                    ics.append({"arm": arm, "year": int(year), "ic": icm, "ic_t": ict,
                                "n_feat": len(feats)})
                    k = tst[["ts", "day", "year", "sym", "slot", "entry_px", "fwd"]].copy()
                    k["arm"] = arm
                    k["pred"] = pt
                    frames.append(k)
                    if arm == "base":
                        reuse[("base", int(year))] = k
                    print(f"  {year}: {len(feats):>2} feats  train<={year-2} ({len(trn):,}) "
                          f"test ({len(tst):,})  iters {model.n_iter_:>4}  "
                          f"rank IC {icm:+.5f} (t {ict:+.1f})  ({time.time()-t0:.0f}s)",
                          flush=True)
        finally:
            f1.FEATURES = saved
        del p

    out = pd.concat(frames, ignore_index=True)
    out.to_parquet(PREDS, index=False)
    icd = pd.DataFrame(ics)
    print("\n=== per-timestamp rank IC on y_close, by arm and test year ===")
    piv = icd.pivot(index="year", columns="arm", values="ic")
    print(piv.round(5).to_string())
    print("mean " + "  ".join(f"{a} {piv[a].mean():+.5f}" for a in piv.columns))
    print("\nfeature count by arm and year")
    print(icd.pivot(index="year", columns="arm", values="n_feat").to_string())
    print(f"\nwritten: {PREDS}")


# ----------------------------------------------------------------------------- clauses 5-7: books


def record(tag: str, r: dict, sess: pd.DataFrame, params: dict, extra: dict) -> None:
    net = sess["net"].to_numpy()
    n = len(sess)
    ret = net / EQUITY
    sd = ret.std(ddof=1) if n > 1 else 0.0
    rec = {"ts": dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
           "algorithm": "intraday/f16_causalgate", "class": "ml", "tag": tag, "commit": "",
           "run_dir": "", "track": "F-16", "params": params,
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
    reg = f14.market_regime()
    arms = [a for a in ARMS if a in set(preds["arm"])]

    print(f"costed against {ic.DATA_DIR}  (_splits.json present: "
          f"{(ic.DATA_DIR / 'splits.json').exists() or (ic.DATA_DIR / '_splits.json').exists()})")

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

    print("\n=== paired per session against base, decomposed ===")
    pairs = {}
    for arm in arms:
        if arm != "base":
            pairs[arm] = f14.paired(sess["base"], sess[arm], f"{arm} - base")
    if "causal" in sess and "lean3" in sess:
        pairs["causal_vs_lean3"] = f14.paired(sess["lean3"], sess["causal"], "causal - lean3")

    print("\n=== regimes: terciles of SPY trailing 20-session realised vol ===")
    print(f"{'cell':<18}" + "".join(f"{k:>12}" for k in ("low", "mid", "high")))
    for arm in arms:
        s = sess[arm].copy()
        s["reg"] = s["day"].astype(str).map(reg)
        m = s.groupby("reg")["net"].mean()
        print(f"{arm:<18}" + "".join(f"{m.get(k, float('nan')):>12,.0f}"
                                    for k in ("low", "mid", "high")))

    admit = json.loads(ADMIT.read_text(encoding="utf-8")) if ADMIT.exists() else {}
    stab = {k: report_admitted(admit[k], k) for k in admit}

    lut = {x["label"]: x for x in rows}
    r, b = lut["session/causal"], lut["session/base"]
    n_pos = int((yr["causal"] > 0).sum())
    dp = pairs.get("causal", {})
    ok = (r["t"] > 2.0) and (n_pos >= 5) and (dp.get("d_net_t", -9) > 2.0)
    print("\n=== clause 5: the pre-registered pass rule (causal arm only) ===")
    print(f"  net t > 2.0                : {r['t']:+.3f}   {'PASS' if r['t'] > 2 else 'FAIL'}")
    print(f"  >= 5 of {len(yr)} years positive   : {n_pos}/{len(yr)}      "
          f"{'PASS' if n_pos >= 5 else 'FAIL'}")
    print(f"  paired causal-base t > 2.0 : {dp.get('d_net_t', float('nan')):+.3f}   "
          f"{'PASS' if dp.get('d_net_t', -9) > 2 else 'FAIL'}")
    print(f"\nDECISION: {'ACCEPT' if ok else 'REFUSE'}  "
          f"(base t {b['t']:+.3f} -> causal t {r['t']:+.3f})")

    CELLS.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(CELLS, index=False)
    if record_rows:
        for x in rows:
            arm = x["label"].split("/")[1]
            record(f"F-16 {x['label']}: the F-14/F-15 gate run INSIDE the walk-forward, "
                   f"selection causal on train+validation only",
                   x, sess[arm],
                   {"arm": arm, "label": LABEL, "decile": DECILE, "learner": "mid",
                    "pool": len(PARENTS)},
                   {"Admitted": json.dumps(stab.get(ARMS[arm][0] or "", {}).get("per_year", {})),
                    "Jaccard": f"{stab.get('q50', {}).get('jaccard', float('nan')):.3f}",
                    "Paired vs base": json.dumps(pairs.get(arm, {}))})
        print(f"\nrecorded {len(rows)} DIAGNOSTIC rows -> {LEDGER}")
    print(f"cells -> {CELLS}")


def post() -> None:
    """POST-RUN. The pooled t of a per-year arm is not the arm's own t when the arm IS base in
    most years. Read the paired effect only on the sessions where the gate admitted something."""
    preds = pd.read_parquet(PREDS)
    preds["ts"] = pd.to_datetime(preds["ts"])
    admit = json.loads(ADMIT.read_text(encoding="utf-8"))
    sess = {a: f8.simulate(f14.frame_for(preds, a), "session", decile=DECILE)
            for a in ("base", "causal", "causal_p25", "causal_scrambled", "lean3")}
    yrs = pd.to_datetime(sess["base"]["day"]).dt.year.to_numpy()

    print("\n=== POST-RUN: the arm is `base` wherever the gate admitted nothing ===")
    for arm, key in (("causal", "q50"), ("causal_p25", "q25"), ("causal_scrambled", "q50")):
        act = np.array([bool(admit[key].get(str(y), [])) for y in yrs])
        d = sess[arm]["net"].to_numpy() - sess["base"]["net"].to_numpy()
        assert np.allclose(d[~act], 0.0), f"{arm} moved in a year with an empty admitted set"
        print(f"  {arm:<18} active on {act.sum():>4}/{len(act)} sessions "
              f"({100 * act.mean():.0f}%, years "
              f"{sorted({int(y) for y in yrs[act]})})")
        print(f"  {'':<18} paired on ACTIVE sessions only: {d[act].mean():>+8,.0f}/day "
              f"(t {f1.tstat(d[act]):+.2f}); annualised over the whole sample that is "
              f"{d[act].sum() / len(act):>+7,.0f}/day")
    print("\n  (the pooled t of `causal` is 5/8 years of `base` plus 3 years of the gate; the "
          "paired-on-active t is what the gate itself is worth)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--fit", action="store_true")
    ap.add_argument("--books", action="store_true")
    ap.add_argument("--post", action="store_true")
    ap.add_argument("--record", action="store_true")
    a = ap.parse_args()
    if a.gate:
        gate()
    if a.fit:
        fit()
    if a.books:
        books(record_rows=a.record)
    if a.post:
        post()
    if not (a.gate or a.fit or a.books or a.post):
        ap.print_help()


if __name__ == "__main__":
    main()
