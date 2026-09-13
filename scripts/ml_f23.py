"""F-23 + F-24: print the two statistics the decisions were actually made on, then re-read the
decisions. One sitting, because F-21's amendment to F-23 says they are the same defect at two
levels and the lower one is the larger hole.

F-20 (d) found that a bit-identical flow store changed 6 of 8 gate decisions, and that four of
them turned on a **0.0014 |IC| gap between `dvol30` and `amihud30`, two columns correlated at
0.88**. Nothing F-16 or F-17 printed showed that, so F-17 reported a coin flip as a finding and
nobody could see it. F-21 (5)(6) found the same defect one level up: a **+24.6% pooled rank IC**
arriving with a **-6.3% book gross** on the same rows and the same target, because rank IC scores
every ordering in the cross-section while a decile book is paid for two tails at one slot.

Neither is an experiment. Both are prints that already existed inside a function and were never
lifted out, and the question this run asks is not "what happens if we measure differently" but
**"how many of this track's frozen conclusions read differently once the statistic they were
decided on is on the page"**. No model is fitted. No data is pulled. Every number below comes from
prediction files this track has already frozen and from `panel.parquet`.

    INTRADAY_DATA_DIR=data/minute_alpaca python scripts/ml_f23.py --spread   # F-24
    INTRADAY_DATA_DIR=data/minute_alpaca python scripts/ml_f23.py --gate     # F-23

--------------------------------------------------------------------------------------------
PRE-REGISTERED - written in full before any F-23/F-24 number was read
--------------------------------------------------------------------------------------------

0. THE PRIOR.  F-21 measured ONE dissociation between the IC and the book, on one pair of arms.
   One instance is an anecdote. I expect the retro-read to find the IC and the slot-0 decile
   spread agreeing on MOST of this track's frozen arm comparisons - they are both monotone in the
   same forecast - and I expect the disagreements to cluster where the arms differ in the WIDTH of
   the cross-section rather than in the quality of the forecast (F-21's 62-name panel; F-17's
   flow arm, whose coverage is partial). If the spread agrees with the money no better than the IC
   does, F-24 is a print worth keeping and NOT a change of lead statistic, and saying so is the
   deliverable. For F-23 I expect 0-2 admissions per window and I expect a MINORITY of them to be
   UNRESOLVED, because F-20's 0.0014 gap was found in the flow pool, where eleven candidates are
   one signal at three widths; the auction pool's six columns are six measurements and should
   separate.

1. NO REFIT, AND THE ROWS ARE PINNED.  Every arm is read from its own frozen prediction file
   (`f8_preds`, `preds_test_ext`, `f17_preds`, `f19_preds`, `f20_preds`, `f21_preds`). Within a
   run, all arms are restricted to the (ts, sym) rows ALL of that run's arms carry, so the IC and
   the spread are computed on identical rows and any difference between two arms is the model and
   nothing else. Across runs nothing is compared: F-17's predictions predate F-19's panel rebuild
   and their row sets are not the same object.

2. THE TARGET IS THE CLEAN PANEL'S `y_close`, for every arm, whatever panel the arm was fitted on.
   F-21's `ic_like_for_like` set that convention and it is the only one that makes a 62-name arm
   and a 56-name arm comparable. Arms fitted on a wider universe are therefore scored on the
   incumbent cross-section they share with the base, which is also the cross-section the book
   trades.

3. THE THREE STATISTICS, all on those rows: (i) mean per-timestamp rank IC over the full
   cross-section - what every F-run since F-8 has led with; (ii) the SLOT-0 DECILE SPREAD in bps -
   mean top-decile `y_close` minus bottom-decile at the 09:55 decision, which is exactly what
   `ml_f8.simulate(kind="session")` earns before costs; (iii) the all-slot decile spread, which is
   what the `cohort_*` books earn. `ml_f8.decile_spread` computes all three and is the lift of
   `ml_f21.tails()` that F-24 asks for.

4. THE MONEY COLUMN is each run's own frozen `session/<arm>` gross bps per dollar turned, taken
   from `data/f1/f*_arms.csv` and, for F-8's label ladder, from the DIAGNOSTIC rows that run wrote
   to `research/experiments.jsonl`. It is gross, not net, deliberately: cost is a property of the
   turnover schedule and is equal across arms by construction (F-17 clause 7), so gross bps is the
   pure forecast-to-book conversion and the only column the forecast statistic can be held to.

5. F-24'S DECISION RULE, pre-registered.  Over every arm-minus-base comparison with
   |delta gross bps| > 0.001 (smaller is a tie and is excluded, not counted as an agreement), count
   how often sign(delta IC) equals sign(delta gross bps) and how often sign(delta slot-0 spread)
   does. The spread REPLACES the IC as the statistic every F-table leads with if and only if it
   agrees strictly more often. Equal or worse and the IC stays, F-21's dissociation is recorded as
   one instance rather than a class, and F-24 closes as a print that is kept because it is free.

6. F-23'S DECISION RULE, the one F-23 wrote and this run uses for the first time.  For each
   admitted parent the gate prints (i) the |IC| of the highest-scoring candidate clause 4c dropped
   against it, (ii) that pair's median per-timestamp |Spearman|, (iii) the admitted column's margin
   over the floor. An admission whose |IC| margin over its displaced rival is SMALLER than the
   candidate's own IC standard error is reported as **UNRESOLVED**, not as an admission: the gate
   cannot tell the two columns apart and the arm built on it is one draw from a coin flip. An
   admission that displaced nothing is UNCONTESTED - it has no rival and the rule does not apply.

7. WHAT THIS RUN MAY AND MAY NOT CONCLUDE.  It may say that a past verdict was decided on an
   unreadable margin. It may NOT overturn one: reversing a refusal needs a book, and every arm
   here was already refused on net. Nothing is promoted, `champion.json` is not touched, and no
   shipped or runner-loaded file changes, so no deploy gate and no `--replay` is owed.
"""

from __future__ import annotations

import argparse
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
import sweep_f1 as f1  # noqa: E402
import ml_f8 as f8  # noqa: E402

OUT = REPO / "data" / "f1"
LEDGER = REPO / "research" / "experiments.jsonl"
SPREAD_CSV = OUT / "f23_spread.csv"
GATE_CSV = OUT / "f23_gate.csv"

#: clause 1: one entry per frozen run - (preds file, arm column, base arm, arms CSV, arm -> csv label)
RUNS = {
    "F-17": {"preds": "f17_preds.parquet", "col": "arm", "base": "base",
             "arms": "f17_arms.csv",
             "order": ["base", "pooled", "flow_only", "auction_only", "pooled_scrambled"]},
    "F-19": {"preds": "f19_preds.parquet", "col": "arm", "base": "base",
             "arms": "f19_arms.csv",
             "order": ["base", "causal", "causal_scrambled"]},
    "F-20": {"preds": "f20_preds.parquet", "col": "arm", "base": "base",
             "arms": "f20_arms.csv",
             "order": ["base", "flow_only", "flow_scram", "auction_only"]},
    "F-21": {"preds": "f21_preds.parquet", "col": "panel", "base": "base56",
             "arms": "f21_arms.csv", "extra_base": ("f20_preds.parquet", "arm", "base"),
             "order": ["base56", "wide", "scram"],
             "csv": {"base56": "base56", "wide": "wide62_feat", "scram": "wide62_scram"}},
    "F-8": {"preds": "f8_preds.parquet", "col": "label", "base": "h1",
            "arms": None, "extra_base": ("preds_test_ext.parquet", None, "h1"),
            "order": ["h1", "h4", "h7", "h10", "close"]},
}

#: clause 2 note: `wide62_etfonly` books a DIFFERENT universe, so it has no like-for-like row set
#: with the base and is excluded by construction rather than by choice. Same for `wide62_traded`,
#: which F-21 itself labelled DIAGNOSTIC ONLY.
EXCLUDED = {"wide62_etfonly", "wide62_traded"}

TIE = 0.001                        # clause 5: below this a gross-bps difference is a tie


# ------------------------------------------------------------------------------ F-24: the spread


def clean_target() -> pd.DataFrame:
    """Clause 2: the clean panel's `y_close`, the target every arm is scored against."""
    p = pd.read_parquet(f1.PANEL, columns=["ts", "day", "year", "sym", "fwd"])
    p = f8.add_labels(p)
    p = p[(p["year"] >= f8.FIRST_TEST_YEAR) & p["y_close"].notna()]
    return p[["ts", "sym", "slot", "y_close"]].reset_index(drop=True)


def gross_bps_table() -> dict[str, dict[str, float]]:
    """Clause 4: each run's own frozen session-book gross bps, per arm."""
    out: dict[str, dict[str, float]] = {}
    for run, cfg in RUNS.items():
        cells = {}
        if cfg["arms"]:
            a = pd.read_csv(OUT / cfg["arms"])
            for _, r in a.iterrows():
                if str(r["label"]).startswith("session/"):
                    cells[str(r["label"]).split("/", 1)[1]] = float(r["gross_bps"])
        out[run] = cells
    led = {}
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        if '"intraday/f8_label"' not in line:
            continue
        r = json.loads(line)
        if r["params"].get("book") == "session" and not r["stats"].get("Control"):
            led[r["params"]["label"]] = float(r["stats"]["Gross Bps Per Turnover"])
    out["F-8"] = led
    return out


def arm_frames(run: str, cfg: dict) -> dict[str, pd.DataFrame]:
    """Every arm of one run as (ts, sym, pred), including a base that lives in another file."""
    frames: dict[str, pd.DataFrame] = {}
    p = pd.read_parquet(OUT / cfg["preds"], columns=["ts", "sym", "pred", cfg["col"]])
    p["ts"] = pd.to_datetime(p["ts"])
    for arm, g in p.groupby(cfg["col"], sort=False):
        frames[str(arm)] = g[["ts", "sym", "pred"]]
    if "extra_base" in cfg:
        fn, col, arm = cfg["extra_base"]
        b = pd.read_parquet(OUT / fn, columns=["ts", "sym", "pred"] + ([col] if col else []))
        b["ts"] = pd.to_datetime(b["ts"])
        if col:
            b = b[b[col] == arm]
        frames[cfg["base"]] = b[["ts", "sym", "pred"]]
    return frames


def run_spread() -> None:
    print("F-24: the decile spread beside the rank IC, on every arm this track has frozen.\n"
          f"target: clean panel `y_close`, {f8.FIRST_TEST_YEAR}+ (clause 2); rows pinned per run "
          "to the intersection of that run's arms (clause 1).\n")
    y = clean_target()
    money = gross_bps_table()
    rows = []

    for run, cfg in RUNS.items():
        frames = arm_frames(run, cfg)
        order = [a for a in cfg["order"] if a in frames]
        if cfg["base"] not in order:
            print(f"{run}: base arm {cfg['base']} missing - skipped")
            continue

        keys = None                                            # clause 1: common rows only
        for a in order:
            k = pd.MultiIndex.from_frame(frames[a][["ts", "sym"]])
            keys = k if keys is None else keys.intersection(k)
        common = pd.DataFrame({"ts": keys.get_level_values(0), "sym": keys.get_level_values(1)})
        base = y.merge(common, on=["ts", "sym"], how="inner")

        print(f"=== {run}: {len(order)} arms on {len(base):,} shared rows "
              f"({base['sym'].nunique()} names, {base['ts'].dt.year.min()}-"
              f"{base['ts'].dt.year.max()}) ===")
        print(f"{'arm':<20}{'full IC':>11}{'slot0 spread':>14}{'t':>7}{'all-slot':>10}{'t':>7}"
              f"{'middle IC':>11}{'gross bps':>11}")
        cells = {}
        for a in order:
            m = base.merge(frames[a], on=["ts", "sym"], how="inner")
            icm, _ = f1.ic_stats(m.assign(y=m["y_close"]), m["pred"].to_numpy())
            s = f8.decile_spread(m, "pred", "y_close")
            csv_arm = cfg.get("csv", {}).get(a, a)
            g = money.get(run, {}).get(csv_arm, float("nan"))
            cells[a] = {"run": run, "arm": a, "csv_arm": csv_arm, "rows": len(m), "ic": icm,
                        "spread0_bps": s["spread0_bps"], "spread0_t": s["spread0_t"],
                        "spread_bps": s["spread_bps"], "spread_t": s["spread_t"],
                        "mid_ic": s["mid_ic"], "gross_bps": g, "slot0_n": s["spread0_n"]}
            print(f"{a:<20}{icm:>+11.5f}{s['spread0_bps']:>+14.3f}{s['spread0_t']:>+7.2f}"
                  f"{s['spread_bps']:>+10.3f}{s['spread_t']:>+7.2f}{s['mid_ic']:>+11.5f}"
                  f"{g:>11.3f}")
        rows += list(cells.values())

        b = cells[cfg["base"]]
        print(f"\n  arm minus base ({cfg['base']}), and what each statistic SAYS about the money:")
        print(f"  {'arm':<20}{'d IC':>12}{'d spread0':>12}{'d gross bps':>13}"
              f"{'IC agrees':>11}{'spread agrees':>15}")
        for a in order:
            if a == cfg["base"] or cells[a]["csv_arm"] in EXCLUDED:
                continue
            c = cells[a]
            dic, dsp, dg = c["ic"] - b["ic"], c["spread0_bps"] - b["spread0_bps"], \
                c["gross_bps"] - b["gross_bps"]
            tie = not np.isfinite(dg) or abs(dg) <= TIE
            ai = "tie" if tie else ("yes" if np.sign(dic) == np.sign(dg) else "NO")
            asp = "tie" if tie else ("yes" if np.sign(dsp) == np.sign(dg) else "NO")
            cells[a].update({"d_ic": dic, "d_spread0": dsp, "d_gross": dg,
                             "ic_agrees": ai, "spread_agrees": asp})
            print(f"  {a:<20}{dic:>+12.5f}{dsp:>+12.3f}{dg:>+13.3f}{ai:>11}{asp:>15}")
        print()

    df = pd.DataFrame(rows)
    SPREAD_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(SPREAD_CSV, index=False)

    # ---- clause 5: the pre-registered count
    cmp_ = df[df.get("ic_agrees").notna()] if "ic_agrees" in df.columns else df.iloc[:0]
    live = cmp_[cmp_["ic_agrees"] != "tie"]
    ties = cmp_[cmp_["ic_agrees"] == "tie"]
    n = len(live)
    ic_ok = int((live["ic_agrees"] == "yes").sum())
    sp_ok = int((live["spread_agrees"] == "yes").sum())
    print("=== clause 5: does the statistic the runs LED WITH point the way the money went? ===")
    print(f"  informative comparisons (|d gross| > {TIE}): {n}   (ties excluded: {len(ties)})")
    print(f"  sign(d rank IC)      agrees with sign(d gross bps) in {ic_ok}/{n}")
    print(f"  sign(d slot0 spread) agrees with sign(d gross bps) in {sp_ok}/{n}")
    if n:
        r_ic = live["d_ic"].corr(live["d_gross"], method="spearman")
        r_sp = live["d_spread0"].corr(live["d_gross"], method="spearman")
        print(f"  rank correlation with d gross bps:  IC {r_ic:+.3f}   slot0 spread {r_sp:+.3f}")
        for _, r in live.iterrows():
            if r["ic_agrees"] != r["spread_agrees"]:
                print(f"    DISAGREE  {r['run']} {r['arm']:<16} d IC {r['d_ic']:+.5f} "
                      f"({r['ic_agrees']})  d spread0 {r['d_spread0']:+.3f} "
                      f"({r['spread_agrees']})  d gross {r['d_gross']:+.3f}")
    verdict = ("ADOPT the slot-0 decile spread as the lead statistic"
               if sp_ok > ic_ok else
               "KEEP the rank IC as the lead statistic; the spread is printed, not promoted")
    print(f"\n  PRE-REGISTERED RULE (clause 5): spread leads iff it agrees strictly more often.")
    print(f"  {sp_ok} vs {ic_ok}  ->  {verdict}")
    print(f"\nwritten: {SPREAD_CSV}")


# -------------------------------------------------------------------------------- F-23: the gate


def run_gate() -> None:
    import ml_f17 as f17

    print("F-23: the gate's admissions, with the rival each one displaced and the margin it\n"
          "turned on. Same gate, same pool, same floor as F-17 clause 4 - only the print is new.\n")
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
        print(f"    ({time.time() - t0:.0f}s)", flush=True)

    df = pd.DataFrame(all_rows)
    GATE_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(GATE_CSV, index=False)

    adm = df[df["admitted_pooled"]].copy()
    print("\n=== clause 6: every POOLED admission the gate has ever made, and whether the margin "
          "it turned on is readable ===")
    print(f"{'year':<6}{'feature':<14}{'|IC|':>9}{'IC se':>9}{'floor':>9}{'margin':>9}"
          f"{'displaced':<14}{'rival |IC|':>11}{'|rho|':>7}{'gap':>10}  verdict")
    for _, r in adm.iterrows():
        rv = r["displaced"] or "-"
        rvic = abs(r["displaced_ic"]) if np.isfinite(r["displaced_ic"]) else float("nan")
        print(f"{int(r['year']):<6}{r['feature']:<14}{abs(r['ic']):>9.5f}{r['ic_se']:>9.5f}"
              f"{r['floor']:>9.5f}{r['floor_margin']:>+9.5f}  {rv:<12}{rvic:>11.5f}"
              f"{r['displaced_rho']:>7.3f}{r['displaced_gap']:>+10.5f}  {r['resolved']}")

    n = len(adm)
    unres = int((adm["resolved"] == "UNRESOLVED").sum())
    unc = int((adm["resolved"] == "UNCONTESTED").sum())
    res = int((adm["resolved"] == "RESOLVED").sum())
    print(f"\n  pooled admissions across {len(years)} windows: {n}"
          f"  ->  RESOLVED {res}, UNRESOLVED {unres}, UNCONTESTED {unc}")
    contested = res + unres
    if contested:
        print(f"  of the {contested} CONTESTED admissions, {unres} "
              f"({100 * unres / contested:.0f}%) turned on a margin smaller than the winning "
              f"candidate's own IC standard error.")
    yrs_un = sorted(set(adm.loc[adm["resolved"] == "UNRESOLVED", "year"].astype(int)))
    print(f"  windows carrying at least one UNRESOLVED admission: {yrs_un or 'none'} "
          f"of {years}")
    print(f"\nwritten: {GATE_CSV}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spread", action="store_true", help="F-24: the decile spread retro-read")
    ap.add_argument("--gate", action="store_true", help="F-23: the gate's displacement diagnostics")
    args = ap.parse_args()
    if args.spread:
        run_spread()
    if args.gate:
        run_gate()
    if not (args.spread or args.gate):
        ap.print_help()


if __name__ == "__main__":
    main()
