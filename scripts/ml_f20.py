"""F-20: rebuild the flow store on the patched loader, then re-ask F-17's flow question on the
CLEAN substrate - because F-17's flow verdict was fitted against dirty incumbents and a dirty floor.

F-19 rebuilt `panel.parquet`, `f15_famA.parquet` and `f15_famB.parquet` and deliberately left the
19-column flow store alone, on the argument that F-14 and F-17 both REFUSED the flow family and a
cleaner tape does not rescue a family whose loss F-17 (5) traced to one 2020 regime break. That
argument is about the CONCLUSION, and it is probably right. It says nothing about the SUBSTRATE,
and F-19's own rule (a) is that a cache whose inputs have moved has unknown content until it is
rebuilt. `data/f1/f14_flow.parquet` was written 2026-09-12 22:41, before AUD-07's calendar trim
reached `ic.load_bars` (04:04 today) and before the store grew six symbols (01:0x today).

Two questions, and they are separable, which is the reason this run exists:

  (A) does the trim move the FLOW STORE ITSELF?  Clause 0 says no, for any row that survives the
      merge, and gives the mechanism. This is a falsifiable prior about the data, not a hope.
  (B) does F-17's flow REFUSAL survive the CLEAN PANEL?  It must be re-asked whatever (A) says,
      because the gate's floor and all 38 incumbents are panel columns and F-19 (3) moved 36.4% of
      the panel's rows. F-17's flow numbers ($205/day, the |IC| inversion, the 2020 break) were
      measured against a floor and a cross-section that no longer exist.

No new data pull. No shipped or runner-loaded file is touched, so no deploy gate and no `--replay`
is owed. What it MAY change on disk is `data/f1/f14_flow.parquet`, keeping the original beside it as
`f14_flow.dirty.parquet`, exactly as F-19 did for the three stores it replaced.

PRE-REGISTERED CLAUSES (written before a number of this run was read; clause 0 is the prior).

0. THE PRIOR, with its mechanism and its falsifier.  I expect the rebuild to change ZERO rows that
   survive the merge with the clean panel, and I expect to be able to say so before running it.
   Every column in `ml_f14.flow_one` is a strictly WITHIN-SESSION trailing window: `_roll_within_day`
   groups by calendar date and never crosses a session boundary, `*_sess` is a within-day cumsum,
   and the market copies `m_*` are the same construction on SPY. The bars AUD-07 removes all fall
   AFTER that session's calendar close. A bar at 13:05 on a 13:00 close can therefore only enter a
   window evaluated at 13:05 or later - i.e. only the 13:25/13:55/14:25/14:55 decision slots, which
   are exactly the rows the clean panel no longer has. So the dirty flow store should differ from
   the rebuilt one ONLY on rows that never reach a fit. FALSIFIER: any surviving (ts, sym) row whose
   flow columns move, or any change in the merged coverage rate. If the falsifier fires, the
   mechanism is wrong and every flow number this track has printed is in question, not just F-17's.
   For (B) I expect the flow family to be REFUSED again and I expect the refusal to be MORE
   decisive, not less: F-19 showed the clean panel's incumbents keep a slightly lower mean rank IC
   (+0.00971 vs +0.01030), which LOWERS the q50 floor and should admit MORE flow, and F-17 (3)'s
   finding is that admitting flow is what loses money. Concretely: at or above 3 of 8 windows with
   a flow admission, and `flow_only` at or below the clean base's $258/day.

1. THE PIN, which is the whole reason F-19 stayed comparable.  The rebuild runs on EXACTLY the 56
   names the clean panel carries, not the 62 the store now holds. `cs_ofi30` and its three siblings
   are within-timestamp percentile ranks, so a 62-name cross-section would change every rank in
   every row and F-20 would be measuring the trim AND a wider universe at once. Widening is F-21.
   Verified, not assumed: the rebuilt store's name set must equal the panel's, and (ts, sym) must
   be unique.

2. THE DIFF, reported per column and split by whether the row survives.  Rows the dirty store holds
   at or after their own session's close are counted (they are the fake ones), and separately the
   count of rows present in BOTH stores whose values move. F-19 (3) is the precedent: the naive
   question "how many rows were removed" understated that run by a factor of 460, because the
   contamination travelled through trailing medians and cross-sectional ranks into rows that were
   never removed. The same two channels exist here (`cs_*` ranks; no trailing median), so the
   surviving-row count is the number that matters and it is reported first.

3. IDENTITY.  `base` reads no flow column, so on the clean panel it must reproduce F-19's clean base
   to the printed digit: mean rank IC +0.00971, gross 4.023 bps, cost 2.720 bps, net $258/day,
   t +1.203, 1,933 sessions. This is the control that proves the rest of the pipeline is unchanged,
   and per F-19 rule (a) it is worth exactly as much as the freshness stamp behind it - which is why
   clause 6 extends the stamp to cover the flow store.

4. THE GATE is F-17's, unchanged and re-run, not re-tuned: q50 floor over the 38 incumbents on
   `year <= Y-1`, redundancy against incumbents at |rho| >= 0.50, then F-17's within-pool leg. The
   candidate pool is F-17's 17 parents so that the auction half supplies a second identity check
   (F-19 says the clean auction gate admits NOTHING in 8/8 windows; if it admits something here the
   merge changed the sample and the run is void). What is NEW is only the substrate.

5. THE HURDLE, unchanged since F-8: adopted only on net t > 2.0 AND >= 5 of 8 years positive AND a
   positive paired arm-minus-base at t > 2.0. Anything else is REFUSED.

6. THE YARDSTICK, which is F-19 rule (c) and applies to every cell below.  The base book spans
   $176/day across a ~1% change in the panel's rows. Any effect this run reports is stated NEXT TO
   that number, and an effect smaller than it is reported as inside construction noise rather than
   as a result. F-17's flow effect was -$101/day, so the prior is that F-20 cannot resolve it
   either way - and saying so is the deliverable, not a failure of the run.

7. THE CONTROL, which is F-17 (c)'s surviving rule: print the scramble control's net. `flow_scram`
   runs the gate on REAL data, admits the real per-year set, and reads those columns permuted
   WITHIN each timestamp - same width, same marginals, same schedule, no information. F-17's pooled
   arm finished BELOW its own scramble; an arm that cannot beat its scramble has not been shown to
   read anything.

8. REPORTED OUTCOMES whatever clause 5 says: the abstention rate, the paired-on-active statistic,
   and - F-19 rule (b), the newest rule this track has - each ADMITTED column's exposure to the
   defect that was just removed from its own inputs. F-19 found the one column its gate ever
   admitted (`auc_ofade`) was the most contaminated in its family and lost a third of its |IC| when
   the contamination went. A screen selects on apparent strength, so it selects FOR whatever
   inflates it. Every admission here is reported with its clause-2 changed-row share.

9. INSTALL, on clause 2's authority and needing no hurdle because it is hygiene rather than a
   result: if the rebuilt store is valid (clause 1) the rebuilt file REPLACES `f14_flow.parquet`
   and the original is kept as `f14_flow.dirty.parquet`. F-20 then closes as a substrate item
   whatever clause 5 decides about flow.

Usage:
    INTRADAY_DATA_DIR=data/minute_alpaca python scripts/ml_f20.py --build
    INTRADAY_DATA_DIR=data/minute_alpaca python scripts/ml_f20.py --diff
    INTRADAY_DATA_DIR=data/minute_alpaca python scripts/ml_f20.py --gate
    INTRADAY_DATA_DIR=data/minute_alpaca python scripts/ml_f20.py --fit
    INTRADAY_DATA_DIR=data/minute_alpaca python scripts/ml_f20.py --books --record
    INTRADAY_DATA_DIR=data/minute_alpaca python scripts/ml_f20.py --install
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
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
import ml_f15 as f15  # noqa: E402
import ml_f17 as f17  # noqa: E402

LEDGER = REPO / "research" / "experiments.jsonl"
OUT = REPO / "data" / "f1"
FLOW_NEW = OUT / "f20_flow.parquet"
FLOW_OLD = f14.FLOW
PREDS = OUT / "f20_preds.parquet"
CELLS = OUT / "f20_arms.csv"
GATE = OUT / "f20_gate.csv"
ADMIT = OUT / "f20_admitted.json"
DIFF = OUT / "f20_diff.csv"

LABEL = "close"
EQUITY = f8.EQUITY
DECILE = f8.DECILE

#: clause 6: F-19's construction-noise yardstick, in net $/day of the base book.
NOISE = 176.0

#: clause 3: F-19's clean base, the identity target.
CLEAN_BASE = {"ic": 0.00971, "gross_bps": 4.023, "cost_bps": 2.720, "net": 258.0, "t": 1.203}


# ------------------------------------------------------------------- clause 1: the pinned rebuild


def pin() -> tuple[list[str], str]:
    """The CLEAN panel's universe and last session - clause 1."""
    o = pd.read_parquet(f1.PANEL, columns=["sym", "day"])
    return sorted(o["sym"].unique().tolist()), str(o["day"].max())


def build() -> None:
    """Rebuild the 19-column flow store through the PATCHED loader, pinned to the panel's names."""
    OUT.mkdir(parents=True, exist_ok=True)
    syms, last_day = pin()
    store = sorted(p.stem for p in ic.DATA_DIR.glob("*.parquet"))
    extra = [s for s in store if s not in set(syms) | set(f1.EXCLUDE)]
    print(f"store {ic.DATA_DIR}   calendar trim: {ic.CALENDAR_TRIM}")
    print(f"clause 1: pinned to the clean panel's {len(syms)} names, last day {last_day}")
    print(f"          the store also holds {len(extra)} tradable names the panel has never "
          f"seen: {extra} (F-21, NOT this run)")
    t0 = time.time()
    fl = f14.build_flow(syms)
    fl.to_parquet(FLOW_NEW, index=False)
    print(f"\nflow: {len(fl):,} rows x {len(f14.FLOW_FEATS)} features -> {FLOW_NEW} "
          f"({time.time() - t0:.0f}s)")
    print(f"  {fl['ts'].min()} .. {fl['ts'].max()}  {fl['sym'].nunique()} symbols")
    assert not fl.duplicated(["ts", "sym"]).any(), "clause 1: (ts, sym) is not unique"
    assert sorted(fl["sym"].unique()) == syms, "clause 1: the rebuilt universe is not the panel's"
    print("  clause 1: PASS - (ts, sym) unique and the universe equals the clean panel's")


# ------------------------------------------------------------------------------ clause 2: the diff


def _close_map() -> dict:
    """day -> that session's calendar close timestamp, from the loader's own calendar."""
    mkt = ic.load_bars(f1.MARKET)
    idx = pd.DatetimeIndex(mkt.index)
    return pd.Series(idx, index=idx.date).groupby(level=0).max().to_dict()


def diff() -> None:
    """How much of the dirty flow store was fake, and how much of the REST of it moved."""
    old = pd.read_parquet(FLOW_OLD)
    new = pd.read_parquet(FLOW_NEW)
    for d in (old, new):
        d["ts"] = pd.to_datetime(d["ts"])
    feats = [c for c in f14.FLOW_FEATS if c in old.columns and c in new.columns]
    print(f"dirty {len(old):,} rows x {old['sym'].nunique()} names "
          f"({old['ts'].min().date()}..{old['ts'].max().date()})")
    print(f"clean {len(new):,} rows x {new['sym'].nunique()} names "
          f"({new['ts'].min().date()}..{new['ts'].max().date()})")

    # (a) the fake rows: a decision bar at or after its own session's last continuous minute
    cm = _close_map()
    for tag, d in (("dirty", old), ("clean", new)):
        day = d["ts"].dt.date
        close = day.map(cm)
        fake = d["ts"] >= close
        print(f"  {tag}: {int(fake.sum()):,} rows at or after their session's close, on "
              f"{int(day[fake].nunique())} sessions and {int(d.loc[fake, 'sym'].nunique())} names")

    # (b) the rows present in both: did anything the panel can still see move?
    k = ["ts", "sym"]
    j = old.merge(new, on=k, how="inner", suffixes=("_o", "_n"))
    print(f"\nclause 2: {len(j):,} rows present in BOTH stores "
          f"({len(old) - len(j):,} dirty-only, {len(new) - len(j):,} clean-only)")
    rows, any_ch = [], np.zeros(len(j), dtype=bool)
    for c in feats:
        a, b = j[f"{c}_o"].to_numpy(), j[f"{c}_n"].to_numpy()
        ch = ~((np.isclose(a, b, rtol=1e-6, atol=1e-9)) | (np.isnan(a) & np.isnan(b)))
        any_ch |= ch
        rows.append({"col": c, "changed": int(ch.sum()), "pct": 100.0 * ch.mean(),
                     "max_abs_delta": float(np.nanmax(np.abs(a - b))) if ch.any() else 0.0})
    dd = pd.DataFrame(rows).sort_values("changed", ascending=False)
    print(dd.to_string(index=False, float_format=lambda v: f"{v:.6g}"))
    sess = int(pd.Series(j.loc[any_ch, "ts"]).dt.date.nunique()) if any_ch.any() else 0
    print(f"\nclause 2 HEADLINE: {int(any_ch.sum()):,} of {len(j):,} shared rows "
          f"({100 * any_ch.mean():.4f}%) have at least one changed column, over {sess} sessions")
    print(f"clause 0 falsifier: {'NOT FIRED - the prior holds' if not any_ch.any() else 'FIRED'}")
    dd.to_csv(DIFF, index=False)
    print(f"written: {DIFF}")

    # (c) what the panel actually merges: coverage on the clean panel, both ways
    p = pd.read_parquet(f1.PANEL, columns=["ts", "sym"])
    p["ts"] = pd.to_datetime(p["ts"])
    for tag, d in (("dirty", old), ("clean", new)):
        m = p.merge(d[k + ["ofi30"]], on=k, how="left")
        print(f"  merged onto the clean panel ({len(p):,} rows): {tag} covers "
              f"{100 * m['ofi30'].notna().mean():.2f}%")


# --------------------------------------------------------------------- clauses 4-8: gate and book

#: arm -> (which admitted set, whether the fit reads the scrambled panel)
ARMS = {"base": (None, False),
        "flow_only": ("flow", False),
        "flow_scram": ("flow", True),
        "auction_only": ("auction", False),
        "pooled": ("pooled", False)}


def _use_new_flow() -> None:
    """Point F-17's loader at the REBUILT store without installing it."""
    f14.FLOW = FLOW_NEW if FLOW_NEW.exists() else FLOW_OLD
    print(f"flow store in use: {f14.FLOW.name}")


def gate() -> None:
    _use_new_flow()
    f1.check_panel_fresh()
    p = f17.load_panel()
    p = p.dropna(subset=["y_close"]).copy()
    years = [y for y in sorted(p["year"].unique()) if y >= f8.FIRST_TEST_YEAR]
    all_rows, admit = [], {k: {} for k in ("pooled", "flow", "auction")}
    for year in years:
        print(f"\n--- gate for test year {year} (reads year <= {year - 1} only)")
        t0 = time.time()
        a, rows = f17.causal_gate(p, year)
        for k in admit:
            admit[k][str(year)] = a[k]
        all_rows += rows
        print(f"    ({time.time() - t0:.0f}s)")
    pd.DataFrame(all_rows).to_csv(GATE, index=False)
    ADMIT.write_text(json.dumps(admit, indent=1), encoding="utf-8")
    for k in admit:
        f17.report_admitted(admit[k], k)
    compare_gate(admit)
    print(f"\nwritten: {GATE}\nwritten: {ADMIT}")


def compare_gate(admit: dict) -> None:
    """Clause 4's second identity check and the F-17 comparison, side by side."""
    ref = OUT / "f17_admitted.json"
    if not ref.exists():
        print("\nF-17's admitted sets are not on disk - comparison SKIPPED")
        return
    old = json.loads(ref.read_text(encoding="utf-8"))
    print("\n=== clause 4: what the gate admits, F-17 (dirty panel) vs F-20 (clean panel) ===")
    for which in ("flow", "auction", "pooled"):
        print(f"  --- {which}")
        for y in sorted(admit[which]):
            a = sorted(c for c in old.get(which, {}).get(y, []) if c in f17.PARENTS)
            b = sorted(c for c in admit[which].get(y, []) if c in f17.PARENTS)
            print(f"    {y}  F-17 {', '.join(a) or '(none)':<26} F-20 {', '.join(b) or '(none)':<26}"
                  f"{'  same' if a == b else '  DIFFER'}")
    au = [c for y in admit["auction"] for c in admit["auction"][y] if c in f15.AUC_OWN]
    print(f"\n  clause 4 identity: the clean auction gate admits {len(au)} parents across all "
          f"windows; F-19 says 0 -> {'PASS' if not au else 'FAIL, the run is void'}")


def fit(only: list[str] | None = None) -> None:
    """F-17's walk-forward fit, with F-20's arms and the rebuilt store."""
    _use_new_flow()
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
        p = f17.load_panel(scramble=scr, cols=f17.POOL)
        p = p.dropna(subset=["y_close"]).copy()
        p["y"] = p["y_close"]
        years = [y for y in sorted(p["year"].unique()) if y >= f8.FIRST_TEST_YEAR]
        saved = list(f1.FEATURES)
        try:
            for arm in arms:
                print(f"\n--- arm {arm}")
                for year in years:
                    which = ARMS[arm][0]
                    add = [c for c in (admit[which].get(str(year), []) if which else [])
                           if c not in base]
                    feats = base + add
                    trn, vld, tst = (p[p.year <= year - 2], p[p.year == year - 1],
                                     p[p.year == year])
                    if not (len(trn) and len(vld) and len(tst)):
                        continue
                    if not add and arm != "base" and int(year) in reuse:
                        k = reuse[int(year)].copy()
                        k["arm"] = arm
                        frames.append(k)
                        r = reuse_ic[int(year)]
                        ics.append({**r, "arm": arm})
                        print(f"  {year}: {len(base)} feats, admitted set EMPTY -> identical to "
                              f"base (rank IC {r['ic']:+.5f}), reused", flush=True)
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
                          f"rank IC {icm:+.5f} (t {ict:+.1f})  ({time.time()-t0:.0f}s)", flush=True)
        finally:
            f1.FEATURES = saved
        del p

    out = pd.concat(frames, ignore_index=True)
    if only is not None and PREDS.exists():
        old = pd.read_parquet(PREDS)
        old["ts"] = pd.to_datetime(old["ts"])
        out = pd.concat([old[~old["arm"].isin(set(out["arm"]))], out], ignore_index=True)
    out.to_parquet(PREDS, index=False)
    icd = pd.DataFrame(ics)
    print("\n=== per-timestamp rank IC on y_close, by arm and test year ===")
    piv = icd.pivot(index="year", columns="arm", values="ic")
    print(piv.round(5).to_string())
    print("mean " + "  ".join(f"{a} {piv[a].mean():+.5f}" for a in piv.columns))
    print(f"\nwritten: {PREDS}")


def record(tag: str, r: dict, sess: pd.DataFrame, params: dict, extra: dict) -> None:
    net = sess["net"].to_numpy()
    n = len(sess)
    ret = net / EQUITY
    sd = ret.std(ddof=1) if n > 1 else 0.0
    rec = {"ts": dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
           "algorithm": "intraday/f20_cleanflow", "class": "ml", "tag": tag, "commit": "",
           "run_dir": "", "track": "F-20", "params": params,
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
    print("\n=== F-8's session book, one decision per session, held to the flatten ===")
    f8.print_table(rows)

    tv = pd.Series({a: sess[a]["turnover"].mean() for a in arms})
    print(f"\nturnover spread across arms ${tv.max() - tv.min():,.0f} (mean ${tv.mean():,.0f})")

    lut = {x["label"]: x for x in rows}
    b = lut["session/base"]
    print("\n=== clause 3: identity against F-19's clean base ===")
    for k, want, tol in (("gross_bps", CLEAN_BASE["gross_bps"], 5e-3),
                         ("cost_bps", CLEAN_BASE["cost_bps"], 5e-3),
                         ("t", CLEAN_BASE["t"], 5e-3),
                         ("net_day", CLEAN_BASE["net"], 0.5)):
        got = b.get(k, float("nan"))
        print(f"  {k:<10} F-19 {want:+10.5f}   F-20 {got:+10.5f}   "
              f"{'match' if abs(got - want) < tol else 'DIFFER'}")

    print("\n=== net $/day by test year ===")
    yr = pd.DataFrame({a: f14.by_year(sess[a]) for a in arms})
    print(yr.to_string())
    print("years positive: " + "  ".join(f"{a} {int((yr[a] > 0).sum())}/{len(yr)}" for a in arms))

    print("\n=== paired per session against base ===")
    pairs = {a: f14.paired(sess["base"], sess[a], f"{a} - base") for a in arms if a != "base"}
    print(f"\nclause 6 yardstick: F-19 measured ${NOISE:.0f}/day of spread in this very book "
          f"from a ~1% change in the panel's rows. Every paired effect above is stated against it.")
    for a, d in pairs.items():
        eff = d.get("d_net", float("nan"))
        print(f"  {a:<14} paired {eff:>+8,.0f}/day  ->  "
              f"{'INSIDE construction noise' if abs(eff) < NOISE else 'larger than the noise'}")

    print("\n=== clause 8: abstention and the paired effect ON ACTIVE SESSIONS ONLY ===")
    yrs = pd.to_datetime(sess["base"]["day"]).dt.year.to_numpy()
    active = {}
    for arm in arms:
        key = ARMS[arm][0]
        if key is None:
            continue
        act = np.array([bool(admit[key].get(str(y), [])) for y in yrs])
        d = sess[arm]["net"].to_numpy() - sess["base"]["net"].to_numpy()
        empty_y = sum(1 for y in sorted(set(yrs)) if not admit[key].get(str(y), []))
        t_act = f1.tstat(d[act]) if act.sum() > 2 else float("nan")
        active[arm] = {"n_active": int(act.sum()), "empty_years": int(empty_y),
                       "d_active": float(d[act].mean()) if act.sum() else 0.0, "t_active": t_act}
        print(f"  {arm:<14} abstains in {empty_y}/{len(set(yrs))} windows; active on "
              f"{act.sum():>4}/{len(act)} sessions ({100 * act.mean():.0f}%); paired on ACTIVE "
              f"{active[arm]['d_active']:>+8,.0f}/day (t {t_act:+.2f})")

    print("\n=== regimes: terciles of SPY trailing 20-session realised vol ===")
    print(f"{'cell':<16}" + "".join(f"{k:>12}" for k in ("low", "mid", "high")))
    for arm in arms:
        s = sess[arm].copy()
        s["reg"] = s["day"].astype(str).map(reg)
        m = s.groupby("reg")["net"].mean()
        print(f"{arm:<16}" + "".join(f"{m.get(k, float('nan')):>12,.0f}"
                                     for k in ("low", "mid", "high")))

    exposure(admit)
    stab = {k: f17.report_admitted(admit[k], k) for k in admit}
    compare_gate(admit)

    r = lut.get("session/flow_only", b)
    n_pos = int((yr["flow_only"] > 0).sum()) if "flow_only" in yr else 0
    dp = pairs.get("flow_only", {})
    ok = (r["t"] > 2.0) and (n_pos >= 5) and (dp.get("d_net_t", -9) > 2.0)
    print("\n=== clause 5: the pre-registered pass rule (flow_only arm) ===")
    print(f"  net t > 2.0                    : {r['t']:+.3f}   {'PASS' if r['t'] > 2 else 'FAIL'}")
    print(f"  >= 5 of {len(yr)} years positive       : {n_pos}/{len(yr)}      "
          f"{'PASS' if n_pos >= 5 else 'FAIL'}")
    print(f"  paired flow_only-base t > 2.0  : {dp.get('d_net_t', float('nan')):+.3f}   "
          f"{'PASS' if dp.get('d_net_t', -9) > 2 else 'FAIL'}")
    print(f"\nDECISION: {'ACCEPT' if ok else 'REFUSE'}  "
          f"(base t {b['t']:+.3f} -> flow_only t {r['t']:+.3f})")

    pd.DataFrame(rows).to_csv(CELLS, index=False)
    if record_rows:
        for x in rows:
            arm = x["label"].split("/")[1]
            key = ARMS[arm][0]
            record(f"F-20 {x['label']}: F-17's causal pool gate re-run on the CLEAN panel with the "
                   f"flow store rebuilt through the patched loader (AUD-07 trim, 56 names pinned)",
                   x, sess[arm],
                   {"arm": arm, "label": LABEL, "decile": DECILE, "learner": "mid",
                    "pool": len(f17.PARENTS), "floor_q": f17.FLOOR_Q, "flow_store": "rebuilt"},
                   {"Admitted": json.dumps(stab.get(key or "", {}).get("per_year", {})),
                    "Abstention": json.dumps(active.get(arm, {})),
                    "Paired vs base": json.dumps(pairs.get(arm, {}))})
        print(f"\nrecorded {len(rows)} DIAGNOSTIC rows -> {LEDGER}")
    print(f"cells -> {CELLS}")


def exposure(admit: dict) -> None:
    """Clause 8 / F-19 rule (b): every admitted column next to its own changed-row share."""
    if not DIFF.exists():
        print("\nclause 8 exposure: run --diff first")
        return
    dd = pd.read_csv(DIFF).set_index("col")
    print("\n=== clause 8 (F-19 rule b): each admitted column's exposure to the removed defect ===")
    seen = {}
    for which in ("flow", "auction", "pooled"):
        for y, cols in sorted(admit[which].items()):
            for c in cols:
                if c in f17.PARENTS:
                    seen.setdefault(c, []).append(f"{which[:4]}/{y}")
    if not seen:
        print("  nothing was admitted in any window under any restriction - no exposure to report")
        return
    for c, where in sorted(seen.items()):
        pct = dd["pct"].get(c, float("nan"))
        print(f"  {c:<14} admitted {len(where):>2}x ({', '.join(where)})   changed rows "
              f"{pct if pct == pct else float('nan'):.4f}% of the shared store")


def install() -> None:
    """Clause 9: the rebuilt store replaces the dirty one, which is kept beside it."""
    if not FLOW_NEW.exists():
        raise SystemExit("nothing to install - run --build first")
    bak = FLOW_OLD.with_suffix(".dirty.parquet")
    if FLOW_OLD.exists() and not bak.exists():
        shutil.copy2(FLOW_OLD, bak)
        print(f"  kept the dirty store as {bak.name}")
    shutil.copy2(FLOW_NEW, FLOW_OLD)
    print(f"  installed {FLOW_NEW.name} -> {FLOW_OLD.name}")
    meta = OUT / "f14_flow.meta.json"
    fp = f1.panel_fingerprint()
    import hashlib
    import inspect
    src = "\n".join(inspect.getsource(fn) for fn in
                    (f14.flow_one, f14._roll_within_day, f14.decision_minutes, f14.build_flow,
                     ic.load_bars, ic.calendar_trim))
    meta = {"store": FLOW_OLD.name,
            "code": hashlib.sha256((src + repr(f14.FLOW_FEATS)).encode()).hexdigest()[:16],
            "store_dir": fp["store_dir"], "store_files": fp["store_files"],
            "store_newest": fp["store_newest"], "symbols": len(pin()[0]),
            "stamped": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    (OUT / "f14_flow.meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(f"  stamped f14_flow.meta.json: code {meta['code']}, {meta['symbols']} symbols, "
          f"store {meta['store_files']} files (F-19 rule a, extended to the flow store)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--diff", action="store_true")
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--fit", action="store_true")
    ap.add_argument("--arms", default=None, help="comma-separated subset for --fit")
    ap.add_argument("--books", action="store_true")
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--install", action="store_true")
    a = ap.parse_args()
    if a.build:
        build()
    if a.diff:
        diff()
    if a.gate:
        gate()
    if a.fit:
        fit(only=a.arms.split(",") if a.arms else None)
    if a.books:
        books(record_rows=a.record)
    if a.install:
        install()
    if not any((a.build, a.diff, a.gate, a.fit, a.books, a.install)):
        ap.print_help()


if __name__ == "__main__":
    main()
