"""F-21: widen the F panel from 56 names to 62 - and find out first WHO OWNS the six new ones.

The Alpaca store grew six symbols at 01:0x on 2026-09-13 (DIA, GLD, TLT, XLE, XLF, XLK). F-19
pinned its rebuild to the old 56 on purpose, so that it measured two data fixes and not a new
cross-section at the same time, and filed the widening here. F-19's stated mechanism is that six
liquid sector/asset ETFs give the within-timestamp ranks a MACRO AXIS that 56 single names do not
have: `cs_r12` over 56 megacaps ranks a name against its peers, and over 62 it ranks it against
rates, gold, energy and the tape as well.

F-19 also attached a condition to the item - "it must check AGENTS.md's disjointness rule (DIA is
an index vehicle; the daily sleeve's claim on it needs checking before it is traded)" - and that
check is clause 1, run FIRST, because it decides which arms below are even admissible. It is not a
formality: `sweep_f1.EXCLUDE` names 7 symbols, the daily champion's traded ETF sleeve
(`algorithms/s1_momo/signals.py:68 RANK_UNIVERSE`) names 9, and the difference is exactly the six
that arrived. So `python scripts/sweep_f1.py --build` TODAY would silently make six instruments the
deployed daily champion holds tradable in this track's panel.

Run with INTRADAY_DATA_DIR=data/minute_alpaca. No shipped or runner-loaded file is touched, so no
deploy gate and no `--replay` is owed. `data/f1/panel.parquet` is NOT modified; the wide panel is a
new file beside it.

PRE-REGISTERED CLAUSES (written before a number of this run was read; clause 0 is the prior).

0. THE PRIOR, with its mechanism and its falsifier. I expect the widening to be REFUSED as a source
   of edge and I expect the reason to be visible in the decomposition rather than in the headline.
   Mechanism for the prior: the book is a DECILE book, and `round(0.10 * 56) = 6 = round(0.10 * 62)`
   - the widening buys zero extra book width, so every dollar of any effect has to come through the
   9 `cs_*` columns and 6 names' worth of extra training rows, against a model whose mean rank IC is
   +0.0097 and whose edge is 1.30 bps on a 2.72 bps cost line. FALSIFIER, and it is the only thing
   that would make me report a positive: `wide62_feat` clearing clause 5's hurdle AND its paired
   effect exceeding clause 6's noise band. I expect neither.

1. THE DISJOINTNESS CHECK, and it runs before anything is built because it is a RED LINE and not a
   result. Every name the widened panel would trade is tested against the daily champion's own
   universes read from `algorithms/s1_momo/signals.py` and against `ic.DAILY_SLEEVE_UNIVERSE`. Any
   name that fails is feature-eligible and TRADE-INELIGIBLE, permanently and whatever it scores.

2. THE PIN. The wide panel is truncated to the CLEAN panel's last session so the two books span the
   same calendar (the six new files carry two sessions the 56 do not). Verified, not assumed: the
   session sets must be equal and the 56 names' row count must be unchanged by the widening.

3. IDENTITY. `base56` is F-19's clean base re-costed here and must reproduce it on every printed
   digit: mean rank IC +0.00971, gross 4.023 bps, cost 2.720 bps, net $258/day, t +1.203, 1,933
   sessions. F-19 rule (a): a reproduction test against a cache is worth exactly what the cache's
   provenance is worth, so the wide panel gets its own fingerprint stamp.

4. THE DECOMPOSITION, which is the reason this run has four arms and not two. Widening changes four
   separable things, and only the first three are admissible:
     (i)   the 9 `cs_*` within-timestamp ranks, now over 62 names - real information, incumbents;
     (ii)  6 names' worth of extra TRAINING rows;
     (iii) the label `y`, demeaned over 62 rather than 56 - note this is a per-timestamp CONSTANT
           shift, so it cannot change any within-timestamp ordering, only the regression target;
     (iv)  six new TRADABLES in the decile book - inadmissible under clause 1.
   `wide62_feat` carries (i)-(iii) and books only the 56. `wide62_traded` adds (iv) and is
   DIAGNOSTIC ONLY. `wide62_etfonly` books ONLY the six, which attributes any gain in
   `wide62_traded` to the names rather than to the ranks.

5. THE HURDLE, unchanged since F-8: adopted only on net t > 2.0 AND >= 5 of 8 years positive AND a
   positive paired arm-minus-base at t > 2.0. Anything else is REFUSED. Plus a clause-1 override
   that no number can lift: an arm that trades a daily-sleeve name is never adopted.

6. THE YARDSTICK, F-19 rule (c): the base book spans $176/day across a ~1% change in the panel's
   rows. Every paired effect below is stated next to that number, and an effect smaller than it is
   reported as inside construction noise rather than as a result.

7. THE CONTROL that separates "a macro axis" from "a wider denominator". `wide62_scram` rebuilds
   the wide panel with the six ETFs' own feature values permuted ACROSS SESSIONS within each
   time-of-day slot: they keep their marginal distributions, they keep their place in every rank
   denominator and in the label's mean, and they lose their contemporaneous link to the tape. If
   `wide62_feat` and `wide62_scram` land together, the widening is arithmetic and not information.

8. FEATURE-IMPORTANCE STABILITY, reported whatever clause 5 says: permutation importance per
   retrain on that retrain's validation year, the Spearman rank correlation between retrains, and -
   the question this run exists to answer - where the 9 `cs_*` columns sit in the ranking at 56
   names against 62. A widening that is doing what F-19 says it does must move `cs_*` UP.

9. THE FIX, on clause 1's authority and needing no hurdle because it is a guard and not a result:
   if clause 1 fails, `sweep_f1.EXCLUDE` gains the offending names so that a naive `--build` cannot
   make them tradable. Verified before it is written: the widened EXCLUDE must reproduce TODAY's
   56-name panel universe exactly, so the fix changes no number this track has ever printed.

10. CLAUSE 10 IS POST-HOC and says so in its own docstring: `--cohort`, added after clause 8's slot
   table was read. It is reported as a diagnostic, adopts nothing, and exists only to open a
   pre-registered successor. Written down here so the record shows WHEN it was added.

Usage (in order; every step is idempotent and writes into data/f1/):
    INTRADAY_DATA_DIR=data/minute_alpaca py -3.14 scripts/ml_f21.py --check       # clause 1
    INTRADAY_DATA_DIR=data/minute_alpaca py -3.14 scripts/ml_f21.py --build       # clause 2  318s
    INTRADAY_DATA_DIR=data/minute_alpaca py -3.14 scripts/ml_f21.py --scramble    # clause 7
    INTRADAY_DATA_DIR=data/minute_alpaca py -3.14 scripts/ml_f21.py --fit --arms wide,scram
    INTRADAY_DATA_DIR=data/minute_alpaca py -3.14 scripts/ml_f21.py --books --record
    INTRADAY_DATA_DIR=data/minute_alpaca py -3.14 scripts/ml_f21.py --ic --tails  # the mechanism
    INTRADAY_DATA_DIR=data/minute_alpaca py -3.14 scripts/ml_f21.py --importance  # clause 8
    INTRADAY_DATA_DIR=data/minute_alpaca py -3.14 scripts/ml_f21.py --cohort      # clause 10
    INTRADAY_DATA_DIR=data/minute_alpaca py -3.14 scripts/ml_f21.py --verify-fix  # clause 9  261s
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import inspect
import json
import re
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
import ml_f14 as f14  # noqa: E402

LEDGER = REPO / "research" / "experiments.jsonl"
OUT = REPO / "data" / "f1"
WIDE = OUT / "f21_panel62.parquet"
WIDE_SCRAM = OUT / "f21_panel62_scram.parquet"
WIDE_META = OUT / "f21_panel62.meta.json"
PREDS = OUT / "f21_preds.parquet"
CELLS = OUT / "f21_arms.csv"
IMP = OUT / "f21_importance.csv"
CHECK = OUT / "f21_check.json"

#: F-20's prediction store holds the `base` arm fitted on the CLEAN 56-name panel, and F-20
#: clause 3 verified it reproduces F-19 to the printed digit. Reused rather than refitted.
BASE_PREDS = OUT / "f20_preds.parquet"
BASE_ARM = "base"

LABEL = "close"
EQUITY = f8.EQUITY
DECILE = f8.DECILE

#: clause 6: F-19's construction-noise yardstick, in net $/day of the base book.
NOISE = 176.0

#: clause 3: F-19's clean base, the identity target.
CLEAN_BASE = {"ic": 0.00971, "gross_bps": 4.023, "cost_bps": 2.720, "net": 258.0, "t": 1.203}

#: clause 4: arm -> (which panel, which names the BOOK may hold, admissible under clause 1)
ARMS = {
    "base56":        ("clean", "incumbents", True),
    "wide62_feat":   ("wide",  "incumbents", True),
    "wide62_scram":  ("scram", "incumbents", True),
    "wide62_traded": ("wide",  "all",        False),
    "wide62_etfonly": ("wide", "new",        False),
}


# ----------------------------------------------------------------- clause 1: the disjointness check


def daily_universe() -> dict[str, list[str]]:
    """The daily champion's own universes, read from its shipped signal module.

    Parsed rather than imported: `algorithms/s1_momo/signals.py` builds frozen dataclasses at
    import time and does not load cleanly outside LEAN's loader on 3.14. The three list literals
    are read verbatim, so this cannot drift from the file without the regex failing loudly.
    """
    src = (REPO / "algorithms" / "s1_momo" / "signals.py").read_text(encoding="utf-8")
    out = {}
    for name in ("RANK_UNIVERSE", "SECTOR_SLEEVE", "MEGACAP_SLEEVE"):
        m = re.search(rf"^{name} = (\[[^]]*\])", src, re.M)
        if m is None:
            raise SystemExit(f"clause 1: could not read {name} from signals.py - refusing to guess")
        out[name] = list(eval(m.group(1)))
    return out


def check() -> dict:
    """Who owns the six new names? Runs before anything is built (clause 1)."""
    store = sorted(p.stem for p in ic.DATA_DIR.glob("*.parquet"))
    tradable = [s for s in store if s not in f1.EXCLUDE]
    incumbents = sorted(pd.read_parquet(f1.PANEL, columns=["sym"])["sym"].unique().tolist())
    new = [s for s in tradable if s not in set(incumbents)]

    du = daily_universe()
    claimed = set(du["RANK_UNIVERSE"]) | set(du["SECTOR_SLEEVE"]) | ic.DAILY_SLEEVE_UNIVERSE
    bad = [s for s in tradable if s in claimed]

    print(f"store {ic.DATA_DIR}: {len(store)} symbols, {len(tradable)} tradable after EXCLUDE")
    print(f"clean panel: {len(incumbents)} names;  NEW since it was built: {new}")
    print(f"\nsweep_f1.EXCLUDE      ({len(f1.EXCLUDE)}): {sorted(f1.EXCLUDE)}")
    print(f"champion RANK_UNIVERSE ({len(du['RANK_UNIVERSE'])}): {du['RANK_UNIVERSE']}")
    print(f"ic.DAILY_SLEEVE_UNIVERSE ({len(ic.DAILY_SLEEVE_UNIVERSE)}): "
          f"{sorted(ic.DAILY_SLEEVE_UNIVERSE)}")
    print(f"\nclause 1: names sweep_f1 would TRADE that the daily sleeve CLAIMS: {bad or '(none)'}")
    for s in bad:
        where = [k for k, v in du.items() if s in v]
        if s in ic.DAILY_SLEEVE_UNIVERSE:
            where.append("ic.DAILY_SLEEVE_UNIVERSE")
        print(f"    {s:<5} claimed by {', '.join(where)}")
    verdict = "PASS" if not bad else "FAIL - these are FEATURE-ELIGIBLE and TRADE-INELIGIBLE"
    print(f"clause 1 verdict: {verdict}")

    # clause 9's precondition, verified before any edit: does the widened EXCLUDE reproduce today's
    # panel universe exactly? If it does not, the fix would change a number and must not be made.
    would = [s for s in store if s not in (set(f1.EXCLUDE) | set(bad))]
    same = would == incumbents
    print(f"\nclause 9 precondition: EXCLUDE + {len(bad)} names -> {len(would)} tradable; "
          f"today's panel has {len(incumbents)} -> {'IDENTICAL' if same else 'DIFFERENT'}")
    if not same:
        print(f"    symmetric difference: {sorted(set(would) ^ set(incumbents))}")

    rec = {"store": str(ic.DATA_DIR), "n_store": len(store), "tradable": tradable,
           "incumbents": incumbents, "new": new, "claimed_by_daily": bad,
           "clause1": verdict, "clause9_reproduces_today": bool(same)}
    OUT.mkdir(parents=True, exist_ok=True)
    CHECK.write_text(json.dumps(rec, indent=1), encoding="utf-8")
    print(f"written: {CHECK}")
    return rec


# --------------------------------------------------------------------- clause 2: the wide panel


def build() -> None:
    """Build the 62-name panel, pinned to the clean panel's calendar."""
    rec = check()
    syms = rec["tradable"]
    clean = pd.read_parquet(f1.PANEL, columns=["ts", "sym", "day"])
    last_day = str(clean["day"].max())
    print(f"\nclause 2: building {len(syms)} names, truncated at the clean panel's last day "
          f"{last_day}")

    saved = set(f1.EXCLUDE)
    t0 = time.time()
    try:
        # The widening is the experiment, so EXCLUDE is lifted for the six under test ONLY here,
        # in this process, and never on disk. `build_panel` filters on the module constant, so
        # passing `symbols` alone would not be enough.
        f1.EXCLUDE = {s for s in saved if s not in set(syms)}
        panel = f1.build_panel(syms)
    finally:
        f1.EXCLUDE = saved

    panel = panel[panel["day"] <= last_day].reset_index(drop=True)
    panel.to_parquet(WIDE, index=False)
    print(f"\nwide panel: {len(panel):,} rows x {len(f1.FEATURES)} features -> {WIDE} "
          f"({time.time() - t0:.0f}s)")

    # clause 2's two assertions, printed and then enforced
    ds_w = set(panel["day"].unique())
    ds_c = set(clean["day"].unique())
    n_inc_w = int(panel["sym"].isin(rec["incumbents"]).sum())
    print(f"  names {panel['sym'].nunique()}  sessions {len(ds_w):,} (clean {len(ds_c):,})  "
          f"incumbent rows {n_inc_w:,} (clean panel {len(clean):,})")
    print(f"  n_cs: clean-panel median {int(pd.read_parquet(f1.PANEL, columns=['n_cs'])['n_cs'].median())}"
          f"  wide median {int(panel['n_cs'].median())}")
    assert ds_w == ds_c, f"clause 2: session sets differ ({len(ds_w ^ ds_c)} days)"
    assert n_inc_w == len(clean), "clause 2: the widening changed the incumbents' row count"
    print("  clause 2: PASS - same sessions, incumbent rows unchanged")
    stamp(WIDE, len(syms))


def stamp(path: Path, n_syms: int) -> None:
    """F-19 rule (a), extended to this panel: record WHAT built it, not when."""
    fp = f1.panel_fingerprint()
    meta = {"panel": path.name, **fp, "symbols": n_syms,
            "built_by": "scripts/ml_f21.py", "f21_check": CHECK.name}
    WIDE_META.write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(f"  stamped {WIDE_META.name}: code {fp['code']}, {n_syms} symbols, "
          f"store {fp['store_files']} files")


def scramble_panel() -> None:
    """Clause 7: the six ETFs keep their marginals and their place in the denominator, and lose
    their contemporaneous link to the tape.

    Permuted ACROSS SESSIONS within each time-of-day slot, per name, with one permutation shared by
    every column of that (name, slot) so the ETF's own feature vector stays internally coherent -
    a row that is scrambled column-by-column would be a different and much easier thing to beat.
    The `cs_*` ranks and the label mean are then RECOMPUTED, because they are properties of the
    cross-section and must see the scrambled values (F-20 rule (d)).
    """
    rec = json.loads(CHECK.read_text(encoding="utf-8"))
    new = rec["new"]
    p = pd.read_parquet(WIDE)
    p["ts"] = pd.to_datetime(p["ts"])
    mins = (p["ts"].dt.hour - 9) * 60 + p["ts"].dt.minute - 30
    p["_slot"] = ((mins - 25) // 30).astype("int8")

    cols = [c for c in f1.BASE_FEATS + f1.RESID_FEATS if c in p.columns] + ["fwd", "entry_px"]
    rng = np.random.default_rng(2021)
    n_moved = 0
    for s in new:
        for sl in sorted(p.loc[p["sym"] == s, "_slot"].unique()):
            m = (p["sym"] == s) & (p["_slot"] == sl)
            idx = np.flatnonzero(m.to_numpy())
            if len(idx) < 3:
                continue
            perm = idx[rng.permutation(len(idx))]
            for c in cols:
                p.loc[p.index[idx], c] = p[c].to_numpy()[perm]
            n_moved += len(idx)
    print(f"clause 7: permuted {n_moved:,} rows across sessions within slot, "
          f"{len(new)} names x {len(cols)} columns (one permutation per name-slot)")

    g = p.groupby("ts", sort=False)
    for c in f1.RANK_OF:
        p[f"cs_{c}"] = g[c].rank(pct=True).astype("float32")
    p["y"] = (p["fwd"] - g["fwd"].transform("mean")).astype("float32")
    p = p.drop(columns=["_slot"])
    p.to_parquet(WIDE_SCRAM, index=False)
    print(f"  cs_* and y RECOMPUTED on the scrambled cross-section -> {WIDE_SCRAM}")


# ------------------------------------------------------------------------ clauses 4, 8: the fit


def _panel_path(which: str) -> Path:
    return {"clean": f1.PANEL, "wide": WIDE, "scram": WIDE_SCRAM}[which]


def _load(which: str) -> pd.DataFrame:
    p = f8.add_labels(pd.read_parquet(_panel_path(which)))
    p = p.dropna(subset=["y_close"]).copy()
    p["y"] = p["y_close"]
    print(f"  panel '{which}': {len(p):,} rows, {p['sym'].nunique()} names, "
          f"{p['day'].nunique():,} sessions")
    return p


def fit(which: list[str] | None = None, keep_models: bool = False) -> dict:
    """Walk-forward fit on each distinct panel. One fit serves every arm that shares its panel."""
    params = dict(f1.GRID["mid"])
    want = which or ["wide", "scram"]
    frames, ics, models = [], [], {}
    for w in want:
        if not _panel_path(w).exists():
            print(f"panel '{w}' not built - skipped")
            continue
        print(f"\n--- panel {w}")
        p = _load(w)
        years = [y for y in sorted(p["year"].unique()) if y >= f8.FIRST_TEST_YEAR]
        for year in years:
            trn, vld, tst = p[p.year <= year - 2], p[p.year == year - 1], p[p.year == year]
            if not (len(trn) and len(vld) and len(tst)):
                continue
            t0 = time.time()
            model, pt = f1.fit_predict(trn, vld, tst, dict(params))
            icm, ict = f1.ic_stats(tst, pt)
            ics.append({"panel": w, "year": int(year), "ic": icm, "ic_t": ict})
            k = tst[["ts", "day", "year", "sym", "slot", "entry_px", "fwd"]].copy()
            k["panel"] = w
            k["pred"] = pt
            frames.append(k)
            if keep_models and w == "wide":
                models[int(year)] = (model, vld)
            print(f"  {year}: train<={year-2} ({len(trn):,})  test ({len(tst):,})  "
                  f"iters {model.n_iter_:>4}  rank IC {icm:+.5f} (t {ict:+.1f})  "
                  f"({time.time()-t0:.0f}s)", flush=True)
        del p

    out = pd.concat(frames, ignore_index=True)
    if PREDS.exists():
        old = pd.read_parquet(PREDS)
        old["ts"] = pd.to_datetime(old["ts"])
        out = pd.concat([old[~old["panel"].isin(set(out["panel"]))], out], ignore_index=True)
    out.to_parquet(PREDS, index=False)
    icd = pd.DataFrame(ics)
    print("\n=== per-timestamp rank IC on y_close, by panel and test year ===")
    print(icd.pivot(index="year", columns="panel", values="ic").round(5).to_string())
    print(f"written: {PREDS}")
    return models


def ic_like_for_like() -> None:
    """The wide fit's raw IC is NOT comparable with the clean fit's, and this says by how much.

    Each panel's `y_close` is demeaned over its OWN cross-section and scored over its OWN names, so
    "+0.0119 at 62 names against +0.0097 at 56" compares two different targets on two different
    samples. The honest comparison holds both fixed: every arm's prediction is scored against the
    CLEAN panel's `y_close`, on the 56 incumbents only, on the same timestamps.
    """
    rec = json.loads(CHECK.read_text(encoding="utf-8"))
    inc = set(rec["incumbents"])
    c = f8.add_labels(pd.read_parquet(f1.PANEL))
    c = c[(c["year"] >= f8.FIRST_TEST_YEAR) & c["y_close"].notna()][["ts", "sym", "y_close"]]
    c["ts"] = pd.to_datetime(c["ts"])

    preds = pd.read_parquet(PREDS)
    preds["ts"] = pd.to_datetime(preds["ts"])
    base = pd.read_parquet(BASE_PREDS)
    base["ts"] = pd.to_datetime(base["ts"])
    srcs = {"base56": base[base["arm"] == BASE_ARM]}
    for w in sorted(set(preds["panel"])):
        srcs[f"wide62_{'feat' if w == 'wide' else w}"] = preds[preds["panel"] == w]

    print("\n=== rank IC against the CLEAN panel's y_close, 56 incumbents, same timestamps ===")
    out = {}
    for name, g in srcs.items():
        g = g[g["sym"].isin(inc)][["ts", "sym", "pred"]]
        m = c.merge(g, on=["ts", "sym"], how="inner")
        icm, ict = f1.ic_stats(m.assign(y=m["y_close"]), m["pred"].to_numpy())
        yr = m.assign(year=m["ts"].dt.year).groupby("year").apply(
            lambda d: f1.ic_stats(d.assign(y=d["y_close"]), d["pred"].to_numpy())[0],
            include_groups=False)
        out[name] = yr
        print(f"  {name:<14} n {len(m):>10,}  mean rank IC {icm:+.5f} (t {ict:+.2f})")
    print("\nby test year:")
    print(pd.DataFrame(out).round(5).to_string())
    d = pd.DataFrame(out)
    if {"base56", "wide62_feat", "wide62_scram"} <= set(d.columns):
        print(f"\n  widening vs base   {d['wide62_feat'].mean() - d['base56'].mean():+.5f}")
        print(f"  widening vs scram  "
              f"{d['wide62_feat'].mean() - d['wide62_scram'].mean():+.5f}")


def tails() -> None:
    """WHERE in the cross-section the IC moved - because the book only monetises the tails.

    `ic_like_for_like` finds the widened model forecasting BETTER on the same rows and the same
    target, while `books` finds it earning LESS. Both cannot be wrong, so the two statistics must
    be measuring different parts of the same cross-section. The book is a DECILE book: it holds
    round(0.10 x n) names a side and is indifferent to every ordering in between. Rank IC is not.
    This prints, per arm, on identical rows: the full-cross-section IC, the DECILE SPREAD the book
    actually monetises, and the IC computed inside the middle the book never touches.
    """
    rec = json.loads(CHECK.read_text(encoding="utf-8"))
    inc = set(rec["incumbents"])
    c = f8.add_labels(pd.read_parquet(f1.PANEL))
    c = c[(c["year"] >= f8.FIRST_TEST_YEAR) & c["y_close"].notna()][["ts", "sym", "y_close"]]
    c["ts"] = pd.to_datetime(c["ts"])

    preds = pd.read_parquet(PREDS)
    preds["ts"] = pd.to_datetime(preds["ts"])
    base = pd.read_parquet(BASE_PREDS)
    base["ts"] = pd.to_datetime(base["ts"])
    srcs = {"base56": base[base["arm"] == BASE_ARM]}
    for w in sorted(set(preds["panel"])):
        srcs[f"wide62_{'feat' if w == 'wide' else w}"] = preds[preds["panel"] == w]

    print("\n=== clause 0's arithmetic, made a measurement: IC vs the DECILE SPREAD ===")
    print(f"{'arm':<15}{'full IC':>12}{'decile spread bps':>20}{'t':>8}"
          f"{'middle IC':>12}{'ts':>10}")
    per_slot = {}
    for name, g in srcs.items():
        g = g[g["sym"].isin(inc)][["ts", "sym", "pred"]]
        m = c.merge(g, on=["ts", "sym"], how="inner").dropna(subset=["pred", "y_close"])
        mins = (m["ts"].dt.hour - 9) * 60 + m["ts"].dt.minute - 30
        m["slot"] = ((mins - 25) // 30).astype("int8")
        full, _ = f1.ic_stats(m.assign(y=m["y_close"]), m["pred"].to_numpy())
        spread, mids, slots = [], [], []
        for (ts, sl), d in m.groupby(["ts", "slot"], sort=False):
            n = len(d)
            if n < 12:
                continue
            k = max(1, int(round(DECILE * n)))
            y = d["y_close"].to_numpy()
            order = np.argsort(d["pred"].to_numpy(), kind="stable")
            spread.append(float(y[order[-k:]].mean() - y[order[:k]].mean()))
            slots.append(int(sl))
            mid = order[k:n - k]
            if len(mid) > 5:
                mids.append(float(pd.Series(d["pred"].to_numpy()[mid])
                                  .corr(pd.Series(y[mid]), method="spearman")))
        sp = np.array(spread) * 1e4
        mi = np.array([v for v in mids if v == v])
        per_slot[name] = pd.Series(sp).groupby(pd.Series(slots)).mean()
        print(f"{name:<15}{full:>+12.5f}{sp.mean():>+20.3f}{f1.tstat(sp):>+8.2f}"
              f"{mi.mean():>+12.5f}{len(sp):>10,}")
    print("\n  'decile spread' = mean y of the top round(0.10 x n) by prediction minus the bottom,\n"
          "  in bps, per timestamp - the only ordering the book is paid for. 'middle IC' is the\n"
          "  rank correlation inside the names the book never holds.")

    ps = pd.DataFrame(per_slot)
    print("\n=== the decile spread BY SLOT, in bps - and F-8's `session` book trades SLOT 0 ONLY ===")
    print(ps.round(3).to_string())
    if {"base56", "wide62_feat"} <= set(ps.columns):
        d = ps["wide62_feat"] - ps["base56"]
        print(f"\n  wide62_feat - base56, slot 0 only : {d.loc[0]:+.3f} bps")
        print(f"  wide62_feat - base56, slots 1-10  : {d.loc[1:].mean():+.3f} bps")
        print(f"  the book is paid for slot 0. Slots 1-10 are forecast quality it never collects.")


def importance() -> None:
    """Clause 8: permutation importance per retrain, on BOTH panels, and where `cs_*` sits."""
    from sklearn.inspection import permutation_importance
    params = dict(f1.GRID["mid"])
    tables = {}
    for w in ("clean", "wide"):
        print(f"\n--- importance, panel {w}")
        p = _load(w)
        years = [y for y in sorted(p["year"].unique()) if y >= f8.FIRST_TEST_YEAR]
        cols = {}
        for year in years:
            trn, vld = p[p.year <= year - 2], p[p.year == year - 1]
            if not (len(trn) and len(vld)):
                continue
            t0 = time.time()
            model, _ = f1.fit_predict(trn, vld, p[p.year == year], dict(params))
            s = vld.sample(min(80_000, len(vld)), random_state=0)
            r = permutation_importance(model, s[f1.FEATURES].to_numpy(dtype=np.float32),
                                       s["y"].to_numpy(), n_repeats=3, random_state=0,
                                       scoring="neg_mean_squared_error", n_jobs=1)
            cols[int(year)] = pd.Series(r.importances_mean, index=f1.FEATURES)
            print(f"  {year} done ({time.time()-t0:.0f}s)", flush=True)
        tables[w] = pd.DataFrame(cols)
        del p

    rows = []
    for w, imp in tables.items():
        yrs = sorted(imp.columns)
        rk = imp.rank(ascending=False)
        corr = rk.corr(method="spearman")
        off = corr.to_numpy()[np.triu_indices(len(yrs), 1)]
        sign = (imp[yrs] > 0).sum(axis=1)
        print(f"\n=== panel {w}: {len(yrs)} retrains ===")
        print(f"  mean pairwise Spearman between retrains: {off.mean():+.3f} "
              f"(min {off.min():+.3f}, max {off.max():+.3f})")
        print(f"  positive in all {len(yrs)} retrains: {int((sign == len(yrs)).sum())} of "
              f"{len(f1.FEATURES)};  sign-flipping: {int(((sign > 0) & (sign < len(yrs))).sum())}")
        cs = [c for c in f1.RANK_FEATS if c in rk.index]
        print(f"  mean rank of the 9 cs_* columns (1 = most important): "
              f"{rk.loc[cs].mean(axis=1).mean():.1f} of {len(f1.FEATURES)}")
        print("  top 10 by mean rank: " + ", ".join(rk.mean(axis=1).nsmallest(10).index))
        for c in f1.FEATURES:
            rows.append({"panel": w, "feature": c, "mean_rank": float(rk.loc[c].mean()),
                         "mean_imp": float(imp.loc[c, yrs].mean()),
                         "is_cs": c in f1.RANK_FEATS,
                         **{f"y{y}": float(imp.loc[c, y]) for y in yrs}})
    d = pd.DataFrame(rows)
    d.to_csv(IMP, index=False)

    piv = d.pivot(index="feature", columns="panel", values="mean_rank")
    if {"clean", "wide"} <= set(piv.columns):
        piv["move"] = piv["clean"] - piv["wide"]          # positive = more important at 62 names
        cs = piv.loc[[c for c in f1.RANK_FEATS if c in piv.index]]
        print("\n=== clause 8: the 9 cs_* columns, mean importance rank at 56 vs 62 names ===")
        print(cs.round(2).to_string())
        print(f"  cs_* mean rank  56 names {cs['clean'].mean():.1f}  ->  62 names "
              f"{cs['wide'].mean():.1f}   ({'UP' if cs['move'].mean() > 0 else 'DOWN'} "
              f"{abs(cs['move'].mean()):.1f} places)")
        print("\n  largest moves, either direction:")
        print(piv.reindex(piv["move"].abs().sort_values(ascending=False).index)
              .head(8).round(2).to_string())
    print(f"\nwritten: {IMP}")


# --------------------------------------------------------------------------- clauses 3-7: books


def _grid(which: str, names: list[str] | None) -> pd.DataFrame:
    p = pd.read_parquet(_panel_path(which),
                        columns=["ts", "day", "year", "sym", "entry_px", "fwd"])
    p["ts"] = pd.to_datetime(p["ts"])
    p = p[p["year"] >= f8.FIRST_TEST_YEAR]
    if names is not None:
        p = p[p["sym"].isin(names)]
    mins = (p["ts"].dt.hour - 9) * 60 + p["ts"].dt.minute - 30
    p = p.copy()
    p["slot"] = ((mins - 25) // 30).astype("int8")
    return p.reset_index(drop=True)


def books(record_rows: bool = False) -> None:
    rec = json.loads(CHECK.read_text(encoding="utf-8"))
    inc, new = rec["incumbents"], rec["new"]
    names = {"incumbents": inc, "new": new, "all": None}

    preds = pd.read_parquet(PREDS)
    preds["ts"] = pd.to_datetime(preds["ts"])
    base = pd.read_parquet(BASE_PREDS)
    base["ts"] = pd.to_datetime(base["ts"])
    base = base[base["arm"] == BASE_ARM]

    have = set(preds["panel"])
    arms = [a for a, (w, _, _) in ARMS.items() if w == "clean" or w in have]
    print(f"costed against {ic.DATA_DIR};  arms: {arms}")

    sess, rows = {}, []
    for arm in arms:
        which, who, _ = ARMS[arm]
        src = base if which == "clean" else preds[preds["panel"] == which]
        g = _grid(which, names[who]).merge(src[["ts", "sym", "pred"]], on=["ts", "sym"], how="left")
        sess[arm] = f8.simulate(g, "session", decile=DECILE)
        rows.append(f8.summarize(sess[arm], f"session/{arm}"))
        print(f"  {arm:<16} {len(sess[arm]):,} sessions, "
              f"{g['sym'].nunique()} names in the book", flush=True)

    print("\n=== F-8's session book, one decision per session, held to the flatten ===")
    f8.print_table(rows)
    lut = {x["label"]: x for x in rows}

    b = lut["session/base56"]
    print("\n=== clause 3: identity against F-19's clean base ===")
    for k, want, tol in (("gross_bps", CLEAN_BASE["gross_bps"], 5e-3),
                         ("cost_bps", CLEAN_BASE["cost_bps"], 5e-3),
                         ("t", CLEAN_BASE["t"], 5e-3),
                         ("net_day", CLEAN_BASE["net"], 0.5)):
        got = b.get(k, float("nan"))
        print(f"  {k:<10} F-19 {want:+10.5f}   F-21 {got:+10.5f}   "
              f"{'match' if abs(got - want) < tol else 'DIFFER'}")

    print("\n=== book width: the decile is 6 names a side at BOTH 56 and 62 (clause 0) ===")
    for n in (len(inc), len(inc) + len(new)):
        print(f"  {n} names -> round({DECILE} x {n}) = {max(1, int(round(DECILE * n)))} per side")

    print("\n=== net $/day by test year ===")
    yr = pd.DataFrame({a: f14.by_year(sess[a]) for a in arms})
    print(yr.to_string())
    print("years positive: " + "  ".join(f"{a} {int((yr[a] > 0).sum())}/{len(yr)}" for a in arms))

    print("\n=== paired per session against base56 ===")
    pairs = {}
    for a in arms:
        if a == "base56":
            continue
        if (sess[a]["day"].to_numpy() != sess["base56"]["day"].to_numpy()).any():
            print(f"  {a}: session sets differ - paired test SKIPPED (clause 2 should have caught "
                  f"this)")
            continue
        pairs[a] = f14.paired(sess["base56"], sess[a], f"{a} - base56")
    print(f"\nclause 6 yardstick: F-19 measured ${NOISE:.0f}/day of spread in this very book from a "
          f"~1% change in the panel's rows. Every paired effect above is stated against it.")
    for a, d in pairs.items():
        eff = d.get("d_net", float("nan"))
        print(f"  {a:<16} paired {eff:>+8,.0f}/day  ->  "
              f"{'INSIDE construction noise' if abs(eff) < NOISE else 'larger than the noise'}")

    if "wide62_feat" in pairs and "wide62_scram" in pairs:
        a, s = pairs["wide62_feat"]["d_net"], pairs["wide62_scram"]["d_net"]
        print(f"\n=== clause 7: the information control ===")
        print(f"  wide62_feat  {a:>+8,.0f}/day      wide62_scram {s:>+8,.0f}/day      "
              f"difference {a - s:>+8,.0f}/day")
        print(f"  -> {'the widening beats its own scramble' if a > s else 'THE SCRAMBLE WINS - the '
              'widening is arithmetic, not information'}")

    print("\n=== regimes: terciles of SPY trailing 20-session realised vol ===")
    reg = f14.market_regime()
    print(f"{'cell':<18}" + "".join(f"{k:>12}" for k in ("low", "mid", "high")))
    for arm in arms:
        s = sess[arm].copy()
        s["reg"] = s["day"].astype(str).map(reg)
        m = s.groupby("reg")["net"].mean()
        print(f"{arm:<18}" + "".join(f"{m.get(k, float('nan')):>12,.0f}"
                                     for k in ("low", "mid", "high")))

    print("\n=== clause 5: the pre-registered pass rule ===")
    for arm in arms:
        if arm == "base56":
            continue
        r, dp = lut[f"session/{arm}"], pairs.get(arm, {})
        n_pos = int((yr[arm] > 0).sum())
        ok = (r["t"] > 2.0) and (n_pos >= 5) and (dp.get("d_net_t", -9) > 2.0)
        adm = ARMS[arm][2]
        print(f"  {arm:<16} net t {r['t']:+.3f} {'PASS' if r['t'] > 2 else 'FAIL'}   "
              f"years {n_pos}/{len(yr)} {'PASS' if n_pos >= 5 else 'FAIL'}   "
              f"paired t {dp.get('d_net_t', float('nan')):+.3f} "
              f"{'PASS' if dp.get('d_net_t', -9) > 2 else 'FAIL'}   -> "
              f"{'ACCEPT' if (ok and adm) else 'REFUSE'}"
              f"{'' if adm else '  (clause 1: DIAGNOSTIC ONLY, trades daily-sleeve names)'}")

    pd.DataFrame(rows).to_csv(CELLS, index=False)
    if record_rows:
        for x in rows:
            arm = x["label"].split("/")[1]
            which, who, adm = ARMS[arm]
            record(f"F-21 {x['label']}: widening the F panel from {len(inc)} to "
                   f"{len(inc) + len(new)} names ({', '.join(new)}); panel '{which}', book over "
                   f"'{who}'" + ("" if adm else " - DIAGNOSTIC, trades daily-sleeve names"),
                   x, sess[arm],
                   {"arm": arm, "panel": which, "book": who, "label": LABEL, "decile": DECILE,
                    "learner": "mid", "n_names_panel": len(inc) + len(new) if which != "clean"
                    else len(inc), "admissible": adm},
                   {"Paired vs base56": json.dumps(pairs.get(arm, {})),
                    "Clause1": rec["clause1"], "New names": json.dumps(new)})
        print(f"\nrecorded {len(rows)} DIAGNOSTIC rows -> {LEDGER}")
    print(f"cells -> {CELLS}")


def verify_fix() -> None:
    """Clause 9: prove the widened EXCLUDE rebuilds TODAY's panel bit for bit, then re-stamp it.

    The fix changes `panel_fingerprint()` - `EXCLUDE` is one of the constants it hashes - so after
    it lands every F-script would warn that `panel.parquet` was built by different code. That
    warning exists because of F-19 and must not be silenced by assertion: it is silenced by REBUILD.
    The 56-name panel is rebuilt under the new constant and compared with the file on disk column
    by column, and the stamp is refreshed only if nothing moved.
    """
    cur = pd.read_parquet(f1.PANEL)
    print(f"on disk: {len(cur):,} rows x {cur.shape[1]} cols, {cur['sym'].nunique()} names")
    t0 = time.time()
    new = f1.build_panel(verbose=False)
    print(f"rebuilt under EXCLUDE({len(f1.EXCLUDE)}): {len(new):,} rows x {new.shape[1]} cols, "
          f"{new['sym'].nunique()} names ({time.time() - t0:.0f}s)")
    if list(cur.columns) != list(new.columns) or len(cur) != len(new):
        raise SystemExit("clause 9 FAILED: shape moved - the fix is NOT content-neutral, revert it")
    moved = []
    for c in cur.columns:
        a, b = cur[c].to_numpy(), new[c].to_numpy()
        if a.dtype.kind in "fc":
            same = np.isclose(a, b, rtol=0, atol=0, equal_nan=True)
        else:
            same = a == b
        if not same.all():
            moved.append((c, int((~same).sum())))
    if moved:
        print(f"clause 9 FAILED: {len(moved)} columns moved: {moved[:10]}")
        raise SystemExit("the fix is NOT content-neutral - revert it")
    print(f"clause 9: PASS - all {cur.shape[1]} columns identical to the bit over {len(cur):,} rows")
    f1.stamp_panel()
    print("  panel.meta.json re-stamped: same content, new builder fingerprint")
    print(f"  check_panel_fresh now says: {f1.check_panel_fresh(loud=False) or 'FRESH'}")


def cohort() -> None:
    """CLAUSE 10, and it is POST-HOC - opened after clause 8's slot table was read, not before.

    The slot table says the widening's whole gain sits in slots 1-10 and the `session` book opens
    at slot 0 only. F-8 already owns a book that opens at EVERY slot (`cohort_close`, gross/11 per
    entry, each held to the flatten), so the implication is testable for the cost of a simulation.
    It is reported as a DIAGNOSTIC and it can adopt nothing: a book chosen after seeing the
    statistic that recommends it is a selection, and this track has refused four families on
    exactly that reasoning. Its only legitimate use is to open a PRE-REGISTERED successor.
    """
    rec = json.loads(CHECK.read_text(encoding="utf-8"))
    inc = rec["incumbents"]
    preds = pd.read_parquet(PREDS)
    preds["ts"] = pd.to_datetime(preds["ts"])
    base = pd.read_parquet(BASE_PREDS)
    base["ts"] = pd.to_datetime(base["ts"])
    srcs = {"base56": ("clean", base[base["arm"] == BASE_ARM]),
            "wide62_feat": ("wide", preds[preds["panel"] == "wide"]),
            "wide62_scram": ("scram", preds[preds["panel"] == "scram"])}

    sess, rows = {}, []
    for name, (which, g) in srcs.items():
        gr = _grid(which, inc).merge(g[["ts", "sym", "pred"]], on=["ts", "sym"], how="left")
        sess[name] = f8.simulate(gr, "cohort_close", decile=DECILE)
        rows.append(f8.summarize(sess[name], f"cohort_close/{name}"))
        print(f"  {name:<14} done", flush=True)
    print("\n=== clause 10 (POST-HOC): F-8's cohort_close book, one entry at EVERY slot ===")
    f8.print_table(rows)
    print("\n=== paired per session against base56 ===")
    pairs = {a: f14.paired(sess["base56"], sess[a], f"{a} - base56")
             for a in sess if a != "base56"}
    yr = pd.DataFrame({a: f14.by_year(sess[a]) for a in sess})
    print("\n=== net $/day by test year ===")
    print(yr.to_string())
    print("years positive: " + "  ".join(f"{a} {int((yr[a] > 0).sum())}/{len(yr)}" for a in sess))
    for a, d in pairs.items():
        print(f"  {a:<14} paired {d['d_net']:>+8,.0f}/day (t {d['d_net_t']:+.2f})  ->  "
              f"{'INSIDE construction noise' if abs(d['d_net']) < NOISE else 'larger than the noise'}")
    print("\n  REPORTED, NOT ADOPTED: the book was chosen after the statistic. Whatever it says, "
          "the\n  decision belongs to a pre-registered successor.")
    pd.DataFrame(rows).to_csv(OUT / "f21_cohort.csv", index=False)


def record(tag: str, r: dict, sess: pd.DataFrame, params: dict, extra: dict) -> None:
    net = sess["net"].to_numpy()
    n = len(sess)
    ret = net / EQUITY
    sd = ret.std(ddof=1) if n > 1 else 0.0
    rec = {"ts": dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
           "algorithm": "intraday/f21_wide62", "class": "ml", "tag": tag, "commit": "",
           "run_dir": "", "track": "F-21", "params": params,
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
                     "Sharpe Ratio":
                         f"{(ret.mean() / sd * np.sqrt(252)) if sd else float('nan'):.3f}",
                     "Diagnostic": "true",
                     **{k: str(v) for k, v in extra.items()}}}
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, default=str) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--scramble", action="store_true")
    ap.add_argument("--fit", action="store_true")
    ap.add_argument("--arms", default=None, help="comma-separated panels for --fit: wide,scram")
    ap.add_argument("--ic", action="store_true")
    ap.add_argument("--tails", action="store_true")
    ap.add_argument("--cohort", action="store_true")
    ap.add_argument("--verify-fix", dest="verify_fix", action="store_true")
    ap.add_argument("--importance", action="store_true")
    ap.add_argument("--books", action="store_true")
    ap.add_argument("--record", action="store_true")
    a = ap.parse_args()
    if a.check:
        check()
    if a.build:
        build()
    if a.scramble:
        scramble_panel()
    if a.fit:
        fit(a.arms.split(",") if a.arms else None)
    if a.ic:
        ic_like_for_like()
    if a.tails:
        tails()
    if a.verify_fix:
        verify_fix()
    if a.cohort:
        cohort()
    if a.importance:
        importance()
    if a.books:
        books(record_rows=a.record)
    if not any((a.check, a.build, a.scramble, a.fit, a.ic, a.tails, a.cohort, a.importance,
                a.books, a.verify_fix)):
        ap.print_help()


if __name__ == "__main__":
    main()
