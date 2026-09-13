#!/usr/bin/env python
"""S-43: a rank VOTE instead of a weight AVERAGE - does truncation separate the gain from the loss?

    python scripts/sweep_s43.py --workers 10      # the whole thing
    python scripts/sweep_s43.py --no-record       # do not append to the ledger

WHY THIS ITEM. S-42 priced the 36-cell weight-blend on the SIGNAL axes and refused it: fully
charged it earns 17.482 / 0.986 / 23.397 (CAR / Sharpe / MaxDD) against the shipped cell's
19.640 / 1.047 / 24.037, a paired -0.784 bps/day at t -2.08. But S-42 also showed the verdict
has two halves with different causes:

  the GAIN is real but small - 0.64 drawdown points in both windows (only rank 17 of 36 among
  the cells the blend averages), plus 0.69x the turnover for 0.87x the fees, which is the first
  netting saving ever demonstrated on this book and the only distinctive part of the gain;

  the LOSS is DILUTION, not cost - the blend holds 4.88 names against the shipped 2.47 at the
  same 1.25x gross, so it funds names the momentum score ranked 4th to 9th of nine. Averaging a
  concentrated ranking IS widening it.

If that diagnosis is right, the two halves are separable by construction. Blend the 36 cells'
target weights exactly as S-42 does, then TRUNCATE to the shipped `top_n` by blended weight and
renormalize to the same gross before executing: an ensemble vote on WHICH THREE, with the
concentration the book was built on restored. This item is a test of the MECHANISM, not a search
for a book - the ladder `keep in {2, 3, 4, 5, all}` is run so the dilution claim is a
dose-response rather than one cell.

THE TRUNCATION RULE, pre-registered in full before the first simulation
----------------------------------------------------------------------
Given the blended target `w[t]` (S-42's object, unchanged: the equal-weight mean over all 36
cells, denominator always 36 and never "the cells with an opinion"):

  1. `gross[t] = sum |w[t][s]|` over every name s.
  2. If `gross[t] == 0`, the truncated target is EMPTY - the book is flat, never synthesised.
  3. Order the names by `(-|w|, symbol)`. The symbol tiebreak is alphabetical, deterministic,
     and uses no information the session does not already have. How often it is actually
     BINDING (an exact |w| tie at the K boundary) is reported, so the arbitrary part of the
     rule is priced rather than assumed harmless.
  4. Keep the first K. If fewer than K names carry non-zero weight, keep all of them - the rule
     never invents a name to reach K.
  5. If K covers every name with weight, return the blend UNCHANGED (bit-identical, not
     re-scaled): this is what makes `K = all` an exact identity against S-42's blend36 and
     therefore a licence for the plumbing.
  6. Otherwise scale the kept weights by `gross[t] / sum |kept|`, so the truncated book carries
     the IDENTICAL gross as the untruncated blend on EVERY session. Holding exposure fixed is
     not a detail: it is the whole reason this is a width experiment and not a sizing one, and
     sizing-versus-width is precisely the confound S-42 corrected S-41 on.

PRE-REGISTERED CLAUSES
----------------------
(1) THE LICENCE. 1a the shipped in-loop book reproduces the deployed cell to the digit (CAR
    22.192150170492255%, 5,052 orders, 2012-2026 zero cost). 1b the shipped cell fed its own
    weights matches 1a to the digit. 1c `K = all` reproduces S-42's blend36 to the digit on CAR
    *and* order count - a PLUMBING identity, labelled as such, whose job is to prove that every
    difference in the ladder below is the truncation and nothing else. 1d the 36 cells share one
    date set on each window (S-42 clause 1c, re-asserted because this item re-derives the paths).
    If 1 fails, nothing below may be read.
(2) PURITY. `dd_halve > 1.0 and dd_flat > 1.0`, so the drawdown overlay is constant 1.0 and the
    target weights are a pure function of (prices, params). Inherited from S-40/S-41/S-42.
(3) THE RULE'S OWN ASSERTIONS, arithmetic rather than hope: on every session and every K,
    `|gross_trunc - gross_blend| < 1e-12`, and the name count is `min(K, names with weight)`.
    Plus the binding-tie count from step 3 above.
(4) THE LADDER, zero cost, on IS 2012-2019 / FULL 2012-2026 / OOS 2020-2026, K in
    {2, 3, 4, 5, all}, against the shipped cell. PRE-REGISTERED READING: S-42 attributes the
    blend's CAR loss to dilution. If that is right, CAR must RISE as K falls toward 3 and the
    drawdown gain must survive. If CAR is flat in K, the loss is not width, the diagnosis was
    wrong, and the ensemble is closed on this axis too.
(4b) WIDTH AND MEMBERSHIP per K: names held, the share of sessions whose name set is IDENTICAL
     to the shipped cell's (S-42 measured 1.90% for blend36 - the membership disagreement that
     made this grid worth ensembling at all), and the no-trade band loss. Band bar unchanged
     from S-41/S-42: more than 10% of target weight below 0.01x equity at $100k and the book is
     not executable at the deployed size.
(4c) THE ALTERNATIVE SPECIFICATION, and the control that stops this item proving the wrong
     thing. `trunc3` widens then narrows; a blend over only the 9 cells with `top_n = 3` never
     widens at all. If the narrow-grid blend matches `trunc3`, then truncation is just a slow
     way of restricting the grid and the "vote on which three" framing adds nothing; if
     `trunc3` beats it, the votes of the wide cells carry information about membership that the
     narrow cells do not have. Run at zero cost and fully charged, same windows.
(5) COST. Every headline book re-run in S-22's honest historical cell C (2 bp one-way spread
    plus IBKR Pro financing on the historical effective fed funds rate) on FULL and OOS, with
    the paired daily return difference against the shipped cell and its t. S-42's headline to
    beat: -0.784 bps/day at t -2.08.
(6) TURNOVER. Orders/yr, turnover/yr and fees per K against the shipped cell. S-42 measured
    0.69x turnover and 0.87x fees for blend36. PRE-REGISTERED EXPECTATION: truncation RAISES
    turnover, because a name drifting across the K boundary becomes a full entry and exit
    instead of a small weight change. If the 0.69x survives at K = 3, the netting lives in the
    averaging rather than in the width, and that is the finding worth having.
(7) THE PROMOTION DECISION, S-41/S-42's bars verbatim so all three items are comparable. A K is
    a PROMOTION CANDIDATE only if, fully charged, on BOTH FULL and OOS: Sharpe >= shipped,
    MaxDD <= shipped, CAR >= shipped - 1.0 points, and clause 4b's band test passes.
(8) THE RANK BAR, which is the clause the promotion bar is the wrong instrument for. C-8's
    result, applied by S-42 clause 8b and re-applied here: a margin over a walk-forward selector
    is a statement about the selector, so each K's case must be its RANK among the 36 cells it
    averages, on the same 2016+ span at zero cost, plus the count of fixed cells that DOMINATE
    it on CAR, Sharpe and MaxDD together. S-42 measured blend36 at rank 17 of 36 on MaxDD. The
    walk-forward selectors are shown alongside for continuity, not as a bar.
(9) THE VERDICT, pre-registered both ways. If truncation recovers the CAR while keeping the
    drawdown and turnover gains, the ensemble was only ever mis-specified and the item becomes a
    signal-level change plus its own LEAN run. If it does not, weight-ensembling is CLOSED on
    this sleeve on both kinds of axis and is recorded as such.

POST HOC, and labelled so in the output rather than smuggled into the list above: clause 4d
splits the K = 3 paired daily difference on whether the vote's name set matches the shipped
cell's that session. It exists because clause 4b turned up a number this item could not have
predicted (77.80% identical sets at K = 3, against 1.90% at every other rung, which is mostly a
count mismatch), and it is the only clause that separates "the ensemble picks worse names" from
"the ensemble sizes the same names worse". It changes no bar and no verdict.

DIAGNOSTIC. No shipped or runner-loaded file is touched: the shipped `Params()` defaults,
`live/*`, `champion.json`, `margin_budget`, `target_vol`, `target_exposure`, the drawdown cap
and every scheduled task are untouched, so no deploy gate and no `--replay` is owed. No shared
code changes - S-41's `weights_fn` is already in place and clause 1 re-proves it. S-42's weight
paths are read from `results/s42_cache.pkl` under clause 1c/1d's licence and are never written
back; this item's own books live in `results/s43_cache.pkl`. Every ledger row is tagged
DIAGNOSTIC.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "algorithms" / "s1_momo"))
sys.path.insert(0, str(REPO / "scripts"))

import signals as sig                                            # noqa: E402
import sweep_s41 as s41                                          # noqa: E402
import sweep_s42 as s42                                          # noqa: E402
from sweep_s19 import MIN_ORDER_VALUE, START_EQUITY, paired      # noqa: E402
from sweep_s40 import (S25_DEPLOYED_CAR, S25_DEPLOYED_ORDERS,    # noqa: E402
                       END, WINDOWS, WF_FIRST_YEAR)
from sweep_s41 import (BAND_LOSS_BAR, CAR_GIVEAWAY, HDR,         # noqa: E402
                       band_loss, row, summarize_span)

LEDGER = REPO / "research" / "experiments.jsonl"
S42_CACHE = REPO / "results" / "s42_cache.pkl"
CACHE_PATH = REPO / "results" / "s43_cache.pkl"

#: the pre-registered ladder. `ALL` is the identity end and is S-42's blend36 exactly.
ALL = 10 ** 9
LADDER = (2, 3, 4, 5, ALL)
SHIPPED_TOP_N = 3
WF_SPAN_START = f"{WF_FIRST_YEAR}-01-01"

#: S-42's measured headline, quoted so every comparison below is pre-registered
S42_SAME_NAMES_FULL = 1.90
S42_BLEND_TURNOVER_X = 0.69
S42_BLEND_FEES_X = 0.87


def kname(k: int) -> str:
    return "all" if k >= ALL else str(k)


def label_of(k: int) -> str:
    return f"trunc{kname(k)}"


# ------------------------------------------------------------------- the truncation rule

def truncate(bl: dict, keep: int) -> tuple[dict, dict]:
    """The pre-registered rule. Returns (path, stats) - see the module docstring, steps 1-6."""
    out: dict = {}
    ties = 0
    gross_err = 0.0
    counts = []
    for d, w in bl.items():
        gross = sum(abs(v) for v in w.values())
        if not w or gross <= 0.0:
            out[d] = {}
            counts.append(0)
            continue
        order = sorted(w.items(), key=lambda kv: (-abs(kv[1]), kv[0]))
        if keep >= len(order):
            out[d] = dict(w)                      # step 5: bit-identical, never re-scaled
            counts.append(len(w))
            continue
        kept = order[:keep]
        if abs(kept[-1][1]) == abs(order[keep][1]):
            ties += 1                             # step 3: the tiebreak is binding here
        s = sum(abs(v) for _, v in kept)
        scale = gross / s
        out[d] = {t: v * scale for t, v in kept}
        counts.append(len(kept))
        gross_err = max(gross_err, abs(sum(abs(v) for v in out[d].values()) - gross))
    return out, {"ties": ties, "gross_err": gross_err,
                 "names": float(np.mean(counts)) if counts else float("nan"),
                 "sessions": len(bl)}


# ---------------------------------------------------------------------------- the clauses

h = s42.h


def book_of(cache: dict, label: str, window: str, costed: bool):
    start, end = WINDOWS[window] if window in WINDOWS else (WF_SPAN_START, END)
    return cache.get((label, start, end, costed))


def clause_1(cache: dict, paths: dict, cells: list[dict]) -> bool:
    h("CLAUSE 1 - the licence: identity, the weight path, and truncation's inert end")
    ok = True
    for lab, key in (("1a in-loop         ", "shipped (in-loop)"),
                     ("1b weights fed back", "shipped (fed its own weights)")):
        d = book_of(cache, key, "FULL", False)[0]
        dc, do = abs(d["CAR"] - S25_DEPLOYED_CAR), d["orders"] - S25_DEPLOYED_ORDERS
        good = dc < 1e-9 and do == 0
        ok &= good
        print(f"  {lab}  CAR {d['CAR']:.12f}%  orders {d['orders']:,}   "
              f"delta {dc:.2e} / {do:+d}   {'OK' if good else 'MISMATCH'}")

    a = book_of(cache, "blend36", "FULL", False)[0]
    b = book_of(cache, label_of(ALL), "FULL", False)[0]
    dc, do = abs(a["CAR"] - b["CAR"]), b["orders"] - a["orders"]
    good = dc < 1e-12 and do == 0
    ok &= good
    print(f"\n  1c K=all vs S-42 blend36 (PLUMBING identity, not a result):")
    print(f"      blend36  CAR {a['CAR']:.12f}%  orders {a['orders']:,}")
    print(f"      trunc-all CAR {b['CAR']:.12f}%  orders {b['orders']:,}   "
          f"delta {dc:.2e} / {do:+d}   {'OK' if good else 'MISMATCH'}")
    print("      -> every difference in the ladder below is the truncation and nothing else.")

    print("\n  1d session-set invariance over the 36 cells (S-42 clause 1c, re-asserted):")
    for window in ("FULL", "OOS"):
        sets = {frozenset(paths[s42.path_key(c, window)][0]) for c in cells}
        n = len(next(iter(sets)))
        good = len(sets) == 1
        ok &= good
        print(f"      {window:<5} {len(sets)} distinct date set(s), {n:,} sessions each   "
              f"{'OK' if good else 'MISMATCH'}")
    return ok


def clause_3(stats: dict) -> bool:
    h("CLAUSE 3 - the rule's own assertions (arithmetic, before any book is read)")
    print(f"  {'K':>5}{'sessions':>10}{'mean names':>12}{'max |gross err|':>18}"
          f"{'binding ties':>14}")
    print("  " + "-" * 59)
    ok = True
    for k in LADDER:
        s = stats[k]
        good = s["gross_err"] < 1e-12
        ok &= good
        print(f"  {kname(k):>5}{s['sessions']:>10,}{s['names']:>12.2f}"
              f"{s['gross_err']:>18.2e}{s['ties']:>14,}")
    print(f"\n  gross preserved to < 1e-12 on every session and every K: "
          f"{'OK' if ok else 'VIOLATED'}")
    print("  -> the ladder moves WIDTH at constant exposure, which is the only way the\n"
          "     dilution claim can be tested without re-running S-41's sizing confound.")
    tot = sum(stats[k]["ties"] for k in LADDER)
    print(f"  the alphabetical tiebreak is binding on {tot} boundary decisions in total"
          f"{' - it is inert' if tot == 0 else ''}.")
    return ok


def clause_4(cache: dict) -> dict:
    h("CLAUSE 4 - the ladder, zero cost: is the blend's CAR loss a dose-response in width?")
    out = {}
    print(HDR)
    print("-" * len(HDR))
    for window in ("FULL", "IS", "OOS"):
        for lab in ["shipped (in-loop)"] + [label_of(k) for k in LADDER]:
            d = book_of(cache, lab, window, False)
            if not d:
                continue
            out[(lab, window)] = d[0]
            tag = "   <- S-42's blend36" if lab == label_of(ALL) else ""
            print(row(d[0], tag))
        print("-" * len(HDR))
    print("\n  the dose-response the item was opened to measure (FULL, zero cost):")
    s = out[("shipped (in-loop)", "FULL")]
    print(f"  {'K':>5}{'CAR%':>10}{'vs shipped':>13}{'Sharpe':>9}{'MaxDD%':>10}"
          f"{'vs shipped':>13}")
    print("  " + "-" * 60)
    for k in LADDER:
        d = out[(label_of(k), "FULL")]
        print(f"  {kname(k):>5}{d['CAR']:>10.3f}{d['CAR'] - s['CAR']:>+13.3f}"
              f"{d['Sharpe']:>9.3f}{d['MaxDD']:>10.3f}{d['MaxDD'] - s['MaxDD']:>+13.3f}")
    cars = [out[(label_of(k), "FULL")]["CAR"] for k in LADDER]
    mono = all(cars[i] >= cars[i + 1] - 1e-9 for i in range(len(cars) - 1))
    print(f"\n  CAR monotonically decreasing in K (the dilution prediction): "
          f"{'YES' if mono else 'NO'}")
    print(f"  spread across the ladder: {max(cars) - min(cars):.3f} CAR points")
    return out


def clause_4b(paths: dict, cells: list[dict], blends: dict, window: str) -> dict:
    h(f"CLAUSE 4b - width, membership and the no-trade band, per K ({window})")
    print(f"  {'K':>5}{'mean names':>12}{'median':>9}{'same name set':>16}"
          f"{'band loss %':>14}{'sess w/ small':>15}")
    print("  " + "-" * 71)
    out = {}
    for k in LADDER:
        bl = blends[(k, window)]
        comp = s42.composition(paths, cells, bl, window)
        b = band_loss(bl, START_EQUITY)
        names = np.array([len(w) for w in bl.values()])
        out[k] = {"ok": b["pct_weight_lost"] <= BAND_LOSS_BAR, **b, **comp}
        print(f"  {kname(k):>5}{names.mean():>12.2f}{np.median(names):>9.0f}"
              f"{comp['same_names']:>15.2f}%{b['pct_weight_lost']:>14.3f}"
              f"{b['days_any_small']:>14.2f}%")
    ship = paths[s42.path_key(next(c for c in cells if s42.is_shipped(c)), window)][0]
    sn = np.array([len(ship.get(d, {})) for d in blends[(LADDER[0], window)]])
    print(f"\n  the shipped cell on the same sessions: mean {sn.mean():.2f} names, "
          f"median {np.median(sn):.0f}")
    print(f"  S-42 measured blend36 at 1.90% identical name sets and "
          f"{S42_SAME_NAMES_FULL}% is the membership disagreement this grid was ensembled for.")
    print(f"  band bar {BAND_LOSS_BAR}% of target weight at ${START_EQUITY:,.0f}: "
          f"{'all K PASS' if all(v['ok'] for v in out.values()) else 'SOME K FAIL'}")
    return out


def clause_4d(cache: dict, paths: dict, cells: list[dict], blends: dict) -> None:
    """Post hoc, and labelled as such: WHERE does the K = 3 book lose its CAR?

    Clause 4b turns up the one number this item could not have predicted: at K = 3 the vote's
    name set is IDENTICAL to the shipped cell's on 77.80% of sessions (the 1.90% at the other
    rungs is mostly a COUNT mismatch, since the shipped cell holds 2.47 names on average and a
    set of 4 can never equal a set of 3). So at K = 3 the ensemble agrees with the incumbent
    about WHICH NAMES four sessions in five, and the whole disagreement lives in the fifth.
    Splitting the paired daily difference on that boundary says whether the ensemble loses by
    picking worse names or by sizing the same names differently - two different verdicts on the
    mechanism, and the promotion table cannot tell them apart.

    The target dated d is built from closes through d-1 (`_path_job`), so it is the position
    held on d and pairs with d's return without an offset.
    """
    h("CLAUSE 4d (post hoc) - where the K=3 vote loses: different names, or different sizes?")
    ship_path = paths[s42.path_key(next(c for c in cells if s42.is_shipped(c)), "FULL")][0]
    bl = blends[(3, "FULL")]
    agree = {d for d, w in bl.items() if set(w) == set(ship_path.get(d, {}))}
    a = book_of(cache, "trunc3", "FULL", True)[1]
    b = book_of(cache, "shipped (in-loop)", "FULL", True)[1]
    m = a[["date", "ret"]].merge(b[["date", "ret"]], on="date", suffixes=("_a", "_b"))
    m["diff"] = 1e4 * (m["ret_a"] - m["ret_b"])
    m["agree"] = m["date"].isin(agree)
    print(f"  {'sessions':<34}{'n':>7}{'share':>9}{'bps/day':>11}{'t':>8}"
          f"{'total bps':>12}")
    print("  " + "-" * 81)
    tot = m["diff"].sum()
    for lab, sub in (("same three names as shipped", m[m["agree"]]),
                     ("a different name set", m[~m["agree"]]),
                     ("all", m)):
        d = sub["diff"].to_numpy()
        t = d.mean() / (d.std(ddof=1) / np.sqrt(len(d))) if len(d) > 1 else float("nan")
        print(f"  {lab:<34}{len(d):>7,}{100.0 * len(d) / len(m):>8.1f}%{d.mean():>11.3f}"
              f"{t:>8.2f}{d.sum():>12,.0f}")
    share = 100.0 * m[~m["agree"]]["diff"].sum() / tot if tot else float("nan")
    print(f"\n  the {100.0 * (~m['agree']).mean():.1f}% of sessions where the vote picks a "
          f"DIFFERENT set carry {share:.1f}% of the\n  total shortfall against the shipped "
          f"cell. If that is far above their session share, the\n  ensemble loses by choosing "
          f"names, not by sizing them - and width was never the mechanism.")


def clause_4c(cache: dict, c5: dict) -> None:
    h("CLAUSE 4c - the control: does truncation beat simply restricting the grid to top_n=3?")
    print(HDR)
    print("-" * len(HDR))
    for costed in (False, True):
        for window in (("FULL", "IS", "OOS") if not costed else ("FULL", "OOS")):
            for lab in ("trunc3", "blend9 (top_n=3 only)", "shipped (in-loop)"):
                d = book_of(cache, lab, window, costed)
                if d:
                    print(row(d[0], f"   [{'cost' if costed else 'zero'} {window}]"))
            print("-" * len(HDR))
    a, b = c5.get(("trunc3", "FULL")), c5.get(("blend9 (top_n=3 only)", "FULL"))
    if a and b:
        print(f"\n  fully charged, FULL: trunc3 - blend9   CAR {a['CAR'] - b['CAR']:+.3f}   "
              f"Sharpe {a['Sharpe'] - b['Sharpe']:+.3f}   MaxDD {a['MaxDD'] - b['MaxDD']:+.3f}")
        print("  -> a positive CAR here means the WIDE cells' votes carry membership information\n"
              "     the narrow grid does not have; a tie means truncation is grid restriction.")


def clause_5(cache: dict) -> dict:
    h("CLAUSE 5 - fully charged, S-22 cell C (2 bp one-way spread + IBKR Pro financing)")
    print(HDR)
    print("-" * len(HDR))
    out = {}
    labels = ["shipped (in-loop)"] + [label_of(k) for k in LADDER] + ["blend9 (top_n=3 only)"]
    for window in ("FULL", "OOS"):
        for lab in labels:
            d = book_of(cache, lab, window, True)
            if d:
                out[(lab, window)] = d[0]
                print(row(d[0]))
        print("-" * len(HDR))
    print("\n  paired daily return difference against the shipped cell, same sessions:")
    print(f"  (S-42's blend36 headline: FULL -0.784 bps/day at t -2.08)")
    for window in ("FULL", "OOS"):
        base = book_of(cache, "shipped (in-loop)", window, True)[1]
        for lab in [label_of(k) for k in LADDER] + ["blend9 (top_n=3 only)"]:
            d = book_of(cache, lab, window, True)
            if not d:
                continue
            pr = paired(d[1], base, lab, "shipped")
            print(f"    {window:<5} {pr['pair']:<42} {pr['bps_per_day']:+8.3f} bps/day  "
                  f"t {pr['t']:+6.2f}  n {pr['days']:,}")
    return out


def clause_6(c5: dict) -> None:
    h("CLAUSE 6 - turnover: does the netting saving survive the truncation?")
    print(f"  {'book':<30}{'orders':>9}{'ord/yr':>9}{'turn/yr':>10}{'fees':>12}"
          f"{'turn x':>9}{'fees x':>9}")
    print("  " + "-" * 88)
    s = c5.get(("shipped (in-loop)", "FULL"))
    for lab in ["shipped (in-loop)"] + [label_of(k) for k in LADDER] + \
               ["blend9 (top_n=3 only)"]:
        d = c5.get((lab, "FULL"))
        if not d:
            continue
        yrs = d["sessions"] / 252.0
        print(f"  {lab:<30}{d['orders']:>9,}{d['orders'] / yrs:>9.0f}"
              f"{d['turnover_x']:>10.1f}{d['fees']:>12,.0f}"
              f"{d['turnover_x'] / s['turnover_x']:>9.2f}{d['fees'] / s['fees']:>9.2f}")
    print(f"\n  S-42 measured blend36 at {S42_BLEND_TURNOVER_X}x turnover and "
          f"{S42_BLEND_FEES_X}x fees - the first netting saving shown on this book.")
    print("  PRE-REGISTERED EXPECTATION: truncation RAISES turnover, because a name drifting\n"
          "  across the K boundary becomes a full entry and exit instead of a weight change.")


def clause_7(c5: dict, band: dict) -> dict:
    h("CLAUSE 7 - the pre-registered promotion decision (S-41/S-42's bars, verbatim)")
    out = {}
    for k in LADDER:
        lab = label_of(k)
        verdicts = []
        lines = []
        for window in ("FULL", "OOS"):
            a, s = c5.get((lab, window)), c5.get(("shipped (in-loop)", window))
            if not (a and s):
                continue
            sh, dd = a["Sharpe"] >= s["Sharpe"], a["MaxDD"] <= s["MaxDD"]
            car = a["CAR"] >= s["CAR"] - CAR_GIVEAWAY
            verdicts.append(sh and dd and car)
            lines.append(f"      {window:<5} Sharpe {a['Sharpe']:.3f} vs {s['Sharpe']:.3f} "
                         f"{'PASS' if sh else 'FAIL':<5}  MaxDD {a['MaxDD']:.3f} vs "
                         f"{s['MaxDD']:.3f} {'PASS' if dd else 'FAIL':<5}  CAR {a['CAR']:.3f} "
                         f"vs {s['CAR']:.3f} {'PASS' if car else 'FAIL'}")
        bok = band.get(k, {}).get("ok", False)
        ok = bool(verdicts) and all(verdicts) and bok
        out[k] = ok
        print(f"  K = {kname(k)}   band {'PASS' if bok else 'FAIL'}   -> "
              f"{'PROMOTION CANDIDATE' if ok else 'NOT a promotion candidate'}")
        for ln in lines:
            print(ln)
    print("\n  Nothing ships from here either way: a 36-cell blend plus a truncation is not\n"
          "  expressible in one `Params()`, so a winner would owe a signal-level change and\n"
          "  its own LEAN run before `champion.json` could be touched.")
    return out


def clause_8(cache: dict, cells: list[dict]) -> None:
    h("CLAUSE 8 - C-8's rank bar: how does each K rank among the 36 cells it averages?")
    cut = pd.Timestamp(WF_SPAN_START)

    def span(label, costed=False):
        d = book_of(cache, label, "FULL", costed)
        return summarize_span(d[1][d[1]["date"] >= cut], label) if d else None

    fixed = [(c, span(s42.cell_name(c))) for c in cells]
    fixed = [(c, d) for c, d in fixed if d]

    def dominates(a, b):
        return a["CAR"] > b["CAR"] and a["Sharpe"] > b["Sharpe"] and a["MaxDD"] < b["MaxDD"]

    refs = {lab: span(lab) for lab in
            ["shipped (in-loop)"] + [label_of(k) for k in LADDER] +
            ["blend9 (top_n=3 only)", "wf-CAR", "wf-Sharpe"]}
    print(f"  on the {refs['shipped (in-loop)']['sessions']:,}-session 2016+ span, zero cost - "
          f"the cell every one of the 36 was run in\n")
    print(f"  {'book':<26}{'CAR%':>9}{'rank':>8}{'Sharpe':>9}{'rank':>8}{'MaxDD%':>9}"
          f"{'rank':>8}{'dominated by':>14}")
    print("  " + "-" * 91)
    for lab, d in refs.items():
        if not d:
            continue
        parts = []
        for metric, better in (("CAR", "high"), ("Sharpe", "high"), ("MaxDD", "low")):
            vals = np.array([x[metric] for _, x in fixed])
            v = d[metric]
            r = int((vals > v).sum()) + 1 if better == "high" else int((vals < v).sum()) + 1
            parts.append((v, r))
        nd = sum(1 for _, x in fixed if dominates(x, d))
        print(f"  {lab:<26}{parts[0][0]:>9.3f}{parts[0][1]:>6} /36{parts[1][0]:>9.3f}"
              f"{parts[1][1]:>6} /36{parts[2][0]:>9.3f}{parts[2][1]:>6} /36{nd:>11} /36")
    print("\n  S-42 measured blend36 at rank 17 of 36 on MaxDD - the number that shrank its\n"
          "  gain. A truncated blend earns the mechanism claim only by ranking better than the\n"
          "  cells it is built from; a margin over `wf-*` is a statement about the selector.")


# --------------------------------------------------------------------------------- ledger

def record(rows: list[dict], skip: bool) -> None:
    if skip:
        print(f"\n  --no-record: {len(rows)} rows NOT written\n")
        return
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with LEDGER.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({
                "ts": stamp, "algorithm": "daily/s43_trunc", "class": "book",
                "tag": f"S-43 {r['cell']} @ {r['start']}..{r['end']} "
                       f"({'cell C cost' if r['costed'] else 'zero cost'}, DIAGNOSTIC)",
                "commit": "", "run_dir": "",
                "track": "S-43", "start": r["start"], "end": r["end"],
                "stats": {"Sessions": str(r["sessions"]),
                          "Total Orders": str(r["orders"]),
                          "Compounding Annual Return": f"{r['CAR']:.4f}%",
                          "Sharpe Ratio": f"{r['Sharpe']:.3f}",
                          "Drawdown": f"{r['MaxDD']:.3f}%",
                          "Annual Standard Deviation": f"{r['std']:.3f}",
                          "Total Fees": f"${r['fees']:.2f}",
                          "End Equity": f"{r['end_equity']:.2f}"}}, default=str) + "\n")
    print(f"\n  recorded {len(rows)} DIAGNOSTIC rows in {LEDGER.name}\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--no-record", action="store_true")
    ap.add_argument("--fresh", action="store_true")
    a = ap.parse_args()

    if not S42_CACHE.exists():
        print(f"S-42's cache is missing ({S42_CACHE}). Run scripts/sweep_s42.py first.")
        return 1
    s42_cache = pickle.loads(S42_CACHE.read_bytes())
    print(f"S-42 cache: {len(s42_cache)} entries (read-only)")

    cache: dict = dict(s42_cache)
    seeded = set(cache)
    if CACHE_PATH.exists() and not a.fresh:
        own = pickle.loads(CACHE_PATH.read_bytes())
        cache.update(own)
        print(f"S-43 cache: {len(own)} entries")

    cells = s42.grid_cells()
    assert len(cells) == 36, len(cells)
    paths = {k: cache[k] for k in cache if len(k) == 2 and isinstance(k[0], tuple)}
    assert len(paths) == 72, f"expected 36 cells x 2 windows of weight paths, got {len(paths)}"
    for c in cells:
        ki = s42.path_key(c, "IS")
        if ki not in paths:
            cut = pd.Timestamp(WINDOWS["IS"][1])
            kf = s42.path_key(c, "FULL")
            paths[ki] = ({d: w for d, w in paths[kf][0].items() if d <= cut}, paths[kf][1])

    # ---- the blends and the ladder
    narrow = [c for c in cells if c["top_n"] == SHIPPED_TOP_N]
    assert len(narrow) == 9, len(narrow)
    blends, stats = {}, {}
    for w in ("FULL", "IS", "OOS"):
        base = s42._blend(paths, cells, w)
        for k in LADDER:
            blends[(k, w)], st = truncate(base, k)
            if w == "FULL":
                stats[k] = st
        blends[("narrow", w)] = s42._blend(paths, narrow, w)

    jobs = [("shipped (in-loop)", *WINDOWS["FULL"], False, None)]
    for w in ("FULL", "IS", "OOS"):
        for k in LADDER:
            jobs.append((label_of(k), *WINDOWS[w], False, blends[(k, w)]))
        jobs.append(("blend9 (top_n=3 only)", *WINDOWS[w], False, blends[("narrow", w)]))
    for w in ("FULL", "OOS"):
        for k in LADDER:
            jobs.append((label_of(k), *WINDOWS[w], True, blends[(k, w)]))
        jobs.append(("blend9 (top_n=3 only)", *WINDOWS[w], True, blends[("narrow", w)]))
    s42.run_pool(jobs, s42._sim_job, cache, a.workers, "books",
                 key_of=lambda j: (j[0], j[1], j[2], j[3]))
    CACHE_PATH.write_bytes(pickle.dumps({k: v for k, v in cache.items() if k not in seeded}))
    for k in list(cache):
        if len(k) == 4 and isinstance(cache[k][1], list):
            cache[k] = (cache[k][0], pd.DataFrame(cache[k][1]))

    ok = clause_1(cache, paths, cells)
    ok &= s42.clause_2()
    ok &= clause_3(stats)
    if not ok:
        print("\nPRE-REGISTERED STOP: clause 1, 2 or 3 failed, nothing below is readable.")
        return 1

    clause_4(cache)
    band = clause_4b(paths, cells, blends, "FULL")
    clause_4b(paths, cells, blends, "OOS")
    c5 = clause_5(cache)
    clause_4c(cache, c5)
    clause_4d(cache, paths, cells, blends)
    clause_6(c5)
    clause_7(c5, band)
    clause_8(cache, cells)

    rows = [cache[k][0] for k in cache
            if k not in seeded and len(k) == 4 and "CAR" in cache[k][0]]
    record(rows, a.no_record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
