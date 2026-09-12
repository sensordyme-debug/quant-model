#!/usr/bin/env python
"""S-34 (AUD-10): price the promotion defect in `scripts/evaluate.py`, then prove the fix.

    py -3.11 scripts/sweep_s34.py            # all clauses
    py -3.11 scripts/sweep_s34.py --report   # same, table only

THE DEFECT. `evaluate.py --promote` wrote `stats`, `run_dir`, `commit` and `tag` into
`research/champion.json` and never touched `stats_by_spread`. `champion_stats()` prefers that
dict, so the first candidate judged after a promotion was compared against the numbers of the
book that had just been retired. It has never bitten because the file was hand-edited after
each of the two promotions this repository has had, which is a habit and not a gate.

WHAT THIS SCRIPT IS. Not a backtest: no LEAN run, no new ledger row, no strategy parameter
touched. It is a measurement of a tooling defect against the only record that can price it -
the real ledger and the real promotion that happened on 2026-09-11 (S-12 -> S-18) - plus the
verification that the patched `evaluate.py` closes it without changing a single existing
verdict. The reason it is an S-item rather than a silent patch is that the quantity that
decides whether AUD-10 is cosmetic or material is a number (how much slack a stale column
hands a candidate), and this track does not ship a fix whose size it has not measured.

CLAUSES, PRE-REGISTERED BEFORE THE FIRST NUMBER (run 2026-09-12):

  1. IDENTITY. The champion file as it stands today is self-consistent: exactly one numeric
     column of `stats_by_spread` carries `run_dir == champion["run_dir"]`, and that column
     agrees with `champion["stats"]` on every key the two share. If this FAILS the file is
     already stale and the item is urgent rather than preventive.

  2. THE DEFECT REPRODUCES. Promoting a real ledger run through the OLD code path (reproduced
     inline below, five lines) leaves a champion whose `champion_stats()` returns a book other
     than the promoted one. Confirmed if the returned CAR differs from the promoted run's by
     more than 0.001 points.

  3. BLAST RADIUS, THE NUMBER. On the real S-12 -> S-18 promotion, per cost column: the CAR,
     Sharpe and drawdown gap between the stale column and the true one, read as the slack a
     later candidate is handed. MATERIAL if the drawdown slack in any column exceeds
     `criteria.drawdown_tolerance_points` (1.0), because that tolerance is the whole width of
     the risk rule the slack would be added to. Otherwise cosmetic and the fix is hygiene.

  4. IT FLIPS REAL VERDICTS. Replay every `s1_momo` row in the ledger through `verdict()`
     against (a) the true post-S-18 columns and (b) the stale columns the old code path would
     have left, and count rows whose verdict flips. DEMONSTRATED if at least one row flips
     from "does not beat" to "beats", i.e. the defect promotes something the true champion
     would have refused. A flip count of zero would make clause 3 arithmetic only.

  5. BACKWARD COMPATIBILITY, THE FIX'S OWN IDENTITY. With the patch in place, every `s1_momo`
     verdict against today's `champion.json` is unchanged from the pre-patch baseline captured
     in `results/_aud10_baseline_table.txt`. Any single changed verdict WITHDRAWS the fix:
     `evaluate.py` is shared code and a promotion gate that moves an existing judgment is a
     worse defect than the one being repaired.

  6. THE FIX CLOSES IT. The same simulated promotion through `promoted_columns()` leaves
     (a) exactly one numeric column, keyed at the promoted run's own spread, whose `run_dir`
     is the promoted run's and whose stats equal it, (b) every `*_note` key byte-identical,
     and (c) a later candidate at a spread with no column REFUSED as not comparable rather
     than judged against anything.

  7. THE GUARD CATCHES A HAND-EDIT. A champion whose columns point only at a foreign run is
     refused by `stale_note()` with a message naming AUD-10, and every verdict built on it
     carries that refusal. This is the half of the fix that does not depend on the writer:
     clause 6 makes `--promote` correct, clause 7 makes an incorrect file detectable however
     it got that way.

WITHDRAWAL CONDITION. Clause 5 failing, or clause 1 failing in a way that means the shipped
champion has been judged against the wrong column (which would put every S-item since S-18
in question rather than this patch).
"""
import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import evaluate as ev  # noqa: E402

BASELINE = REPO / "results" / "_aud10_baseline_table.txt"

# The two runs behind today's champion columns, and the two behind the champion S-18 retired.
S18_0BP, S18_2BP = "20260911T145705Z", "20260911T150558Z"
S12_0BP, S12_2BP = "20260909T042431Z", "20260911T125421Z"


def old_promote(run, champion):
    """`evaluate.py --promote` exactly as it stood before this iteration (the defect)."""
    out = json.loads(json.dumps(champion))
    out.update({
        "algorithm": run["algorithm"], "class": run["class"], "run_dir": run["run_dir"],
        "stats": run["stats"], "commit": run.get("commit"), "tag": run.get("tag"),
    })
    return out


def new_promote(run, champion):
    """The patched path: the promoted run's column replaces the retired book's columns."""
    out = json.loads(json.dumps(champion))
    out.update({
        "algorithm": run["algorithm"], "class": run["class"], "run_dir": run["run_dir"],
        "stats": run["stats"], "commit": run.get("commit"), "tag": run.get("tag"),
        "stats_by_spread": ev.promoted_columns(run, out),
    })
    return out


def by_ts(runs):
    return {r["ts"]: r for r in runs}


def s12_champion(runs, champion):
    """The champion file as it stood the moment before S-18 was promoted."""
    out = json.loads(json.dumps(champion))
    r0, r2 = by_ts(runs)[S12_0BP], by_ts(runs)[S12_2BP]
    cols = {k: v for k, v in (champion.get("stats_by_spread") or {}).items()
            if not ev.COLUMN_KEY.match(k)}
    cols["0.0"] = dict(r0["stats"], run_dir=r0["run_dir"])
    cols["2.0"] = dict(r2["stats"], run_dir=r2["run_dir"])
    out.update({"run_dir": r0["run_dir"], "stats": r0["stats"], "commit": r0.get("commit"),
                "stats_by_spread": cols})
    return out


def gap(stale, true_, metric):
    return ev.num(true_.get(metric)) - ev.num(stale.get(metric))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", action="store_true", help="tables only, no narration")
    args = ap.parse_args()

    runs = ev.load_runs()
    champion = ev.load_champion()
    s1 = [r for r in runs if r["algorithm"] == "s1_momo"]
    index = by_ts(runs)
    fails = []

    print("=" * 78)
    print("S-34 (AUD-10): the promotion gate leaves the retired champion's numbers in place")
    print("=" * 78)

    # ---- clause 1: identity -------------------------------------------------------------
    cols = ev.cost_columns(champion)
    own = [k for k, c in cols.items() if c.get("run_dir") == champion.get("run_dir")]
    agree = all(str(cols[own[0]][k]) == str(champion["stats"][k])
                for k in cols[own[0]] if k in champion.get("stats", {})) if own else False
    print(f"\n[1] IDENTITY  columns {sorted(cols)}  notes "
          f"{len((champion.get('stats_by_spread') or {})) - len(cols)}")
    print(f"    column carrying the champion's own run_dir: {own or 'NONE'}")
    print(f"    that column agrees with champion['stats']:   {agree}")
    print(f"    stale_note(): {ev.stale_note(champion) or 'none - file is self-consistent'}")
    if len(own) != 1 or not agree:
        fails.append("clause 1: today's champion.json is NOT self-consistent")

    # ---- clause 2: the defect reproduces ------------------------------------------------
    cand = index[S18_2BP]                      # a real run, charged 2 bp, promoted for the test
    broken = old_promote(cand, s12_champion(s1, champion))
    seen, note = ev.champion_stats(cand, broken)
    delta = abs(ev.num(seen.get("Compounding Annual Return"))
                - ev.num(cand["stats"]["Compounding Annual Return"]))
    print(f"\n[2] DEFECT  promote {S18_2BP} (CAR {cand['stats']['Compounding Annual Return']}, "
          f"2 bp) through the OLD path, then judge a 2 bp candidate:")
    print(f"    champion_stats() returns CAR {seen.get('Compounding Annual Return')} from run "
          f"{seen.get('run_dir')}")
    print(f"    that is the RETIRED book: |difference| {delta:.3f} CAR points (> 0.001 confirms)")
    if delta <= 0.001:
        fails.append("clause 2: the defect did not reproduce")

    # ---- clause 3: blast radius ---------------------------------------------------------
    true_cols = {"0.0": index[S18_0BP], "2.0": index[S18_2BP]}
    stale_cols = {"0.0": index[S12_0BP], "2.0": index[S12_2BP]}
    dd_tol = float(champion.get("criteria", {}).get("drawdown_tolerance_points", 1.0))
    print(f"\n[3] BLAST RADIUS  the real S-12 -> S-18 promotion, slack handed to the next "
          f"candidate")
    print(f"    {'col':>5}  {'stale CAR':>9} {'true CAR':>9} {'dCAR':>7}  "
          f"{'stale Shp':>9} {'true Shp':>9} {'dShp':>7}  "
          f"{'stale DD':>8} {'true DD':>8} {'dDD':>7}")
    worst_dd = 0.0
    for key in ("0.0", "2.0"):
        st, tr = stale_cols[key]["stats"], true_cols[key]["stats"]
        d_car = gap(st, tr, "Compounding Annual Return")
        d_shp = gap(st, tr, "Sharpe Ratio")
        d_dd = ev.num(st.get("Drawdown")) - ev.num(tr.get("Drawdown"))
        worst_dd = max(worst_dd, d_dd)
        print(f"    {key:>5}  {st['Compounding Annual Return']:>9} "
              f"{tr['Compounding Annual Return']:>9} {d_car:>+7.3f}  "
              f"{st['Sharpe Ratio']:>9} {tr['Sharpe Ratio']:>9} {d_shp:>+7.3f}  "
              f"{st['Drawdown']:>8} {tr['Drawdown']:>8} {d_dd:>+7.3f}")
    verdict3 = "MATERIAL" if worst_dd > dd_tol else "cosmetic"
    print(f"    worst drawdown slack {worst_dd:+.3f} points against the "
          f"{dd_tol} of drawdown_tolerance_points -> {verdict3}")

    # ---- clause 4: it flips real verdicts ------------------------------------------------
    true_champ = new_promote(index[S18_0BP], s12_champion(s1, champion))
    true_champ["stats_by_spread"]["2.0"] = dict(index[S18_2BP]["stats"],
                                                run_dir=index[S18_2BP]["run_dir"])
    stale_champ = old_promote(index[S18_0BP], s12_champion(s1, champion))
    # The stale arm must be judged with the OLD semantics, or it measures the patch instead of
    # the defect: `stale_note()` refuses `stale_champ` outright (that is clause 7), which would
    # turn every row into "no" and report flips that are the fix working rather than the bug
    # biting. Bypassing the guard for this arm alone reproduces `evaluate.py` as it shipped.
    guard = ev.stale_note
    ev.stale_note = lambda _c: None
    try:
        flips = []
        for r in s1:
            ok_stale, _ = ev.verdict(r, stale_champ)
            ok_true, _ = ev.verdict(r, true_champ)
            if ok_true != ok_stale:
                flips.append((r, ok_stale, ok_true))
    finally:
        ev.stale_note = guard
    promoted_wrongly = [f for f in flips if f[1] and not f[2]]
    print(f"\n[4] VERDICT FLIPS  {len(s1)} s1_momo rows replayed against the true and the stale "
          f"post-promotion champion (guard bypassed on the stale arm: old semantics)")
    print(f"    rows whose verdict flips: {len(flips)}  "
          f"(stale says BEATS where true says NO: {len(promoted_wrongly)})")
    for r, ok_stale, ok_true in flips[:10]:
        s = r["stats"]
        print(f"      {'PROMOTES' if ok_stale else 'buries  '} {r['ts']}  "
              f"CAR {s.get('Compounding Annual Return'):>8}  "
              f"Sharpe {s.get('Sharpe Ratio'):>5}  DD {s.get('Drawdown'):>8}  "
              f"{(r.get('tag') or '')[:40]}")
    if not promoted_wrongly:
        print("    none in the dangerous direction - the ledger holds no run that the stale "
              "column alone would promote, so clause 3 is a bound rather than a demonstrated "
              "escape")

    # ---- clause 5: backward compatibility ------------------------------------------------
    print("\n[5] BACKWARD COMPATIBILITY  every verdict against today's champion.json, patched "
          "vs the pre-patch baseline")
    if not BASELINE.exists():
        fails.append("clause 5: baseline table missing")
        print(f"    MISSING {BASELINE}")
    else:
        base = {}
        for line in BASELINE.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if parts and parts[0].endswith("Z") and len(parts[0]) == 16:
                base[parts[0]] = parts[-1]
        now = {r["ts"]: ("yes" if ev.verdict(r, champion)[0] else "no") for r in s1}
        shared = sorted(set(base) & set(now))
        changed = [ts for ts in shared if base[ts] != now[ts]]
        print(f"    {len(shared)} rows compared, {len(changed)} changed")
        if changed:
            fails.append(f"clause 5: {len(changed)} verdicts moved - WITHDRAW the fix")
            for ts in changed[:10]:
                print(f"      {ts}: {base[ts]} -> {now[ts]}")

    # ---- clause 6: the fix closes it ------------------------------------------------------
    fixed = new_promote(cand, s12_champion(s1, champion))
    fcols = ev.cost_columns(fixed)
    notes_before = {k: v for k, v in (champion.get("stats_by_spread") or {}).items()
                    if not ev.COLUMN_KEY.match(k)}
    notes_after = {k: v for k, v in fixed["stats_by_spread"].items()
                   if not ev.COLUMN_KEY.match(k)}
    single = list(fcols) == [ev.spread_bps(cand)]
    points_at = fcols.get(ev.spread_bps(cand), {}).get("run_dir") == cand["run_dir"]
    notes_kept = notes_before == notes_after
    other, other_note = ev.champion_stats(index[S18_0BP], fixed)   # a 0 bp candidate, no column
    print(f"\n[6] THE FIX  promote the same run through promoted_columns()")
    print(f"    exactly one cost column, at the run's own spread: {single} {sorted(fcols)}")
    print(f"    it points at the promoted run:                   {points_at}")
    print(f"    all {len(notes_before)} research notes preserved byte-identical: {notes_kept}")
    print(f"    a 0 bp candidate against this champion: "
          f"{'REFUSED - ' + other_note[:88] if other_note else 'JUDGED (wrong)'}")
    print(f"    stale_note(): {ev.stale_note(fixed) or 'none'}")
    if not (single and points_at and notes_kept and other_note and not ev.stale_note(fixed)):
        fails.append("clause 6: the fix does not close the defect")

    # ---- clause 7: the guard catches a hand-edit ------------------------------------------
    hand = old_promote(cand, s12_champion(s1, champion))
    guard = ev.stale_note(hand)
    ok7, reasons7 = ev.verdict(index[S18_0BP], hand)
    carried = any("AUD-10" in x for x in reasons7)
    print(f"\n[7] GUARD  the clause-2 champion, built by the old path, read by the patched code")
    print(f"    stale_note(): {guard[:110] if guard else 'NONE - guard failed'}")
    print(f"    the refusal reaches verdict(): {carried} (beats={ok7})")
    if not guard or not carried or ok7:
        fails.append("clause 7: the staleness guard did not fire")

    print("\n" + "=" * 78)
    if fails:
        print("FAIL")
        for f in fails:
            print(f"  - {f}")
    else:
        print(f"ALL CLAUSES PASS - AUD-10 is {verdict3}, the fix is backward compatible, "
              f"and a stale champion file is now refused rather than used.")
    print("=" * 78)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
