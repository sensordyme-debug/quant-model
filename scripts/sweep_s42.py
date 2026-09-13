#!/usr/bin/env python
"""S-42: the ensemble trick on the SIGNAL axes, where a CAR grid is a fair instrument.

    python scripts/sweep_s42.py --workers 10      # the whole thing
    python scripts/sweep_s42.py --no-record       # do not append to the ledger

WHY THIS ITEM. S-41 built the equal-weight WEIGHT-blend of the 36-cell crisis-switch grid and
it failed the promotion bar on return while winning on drawdown. That comparison is confounded
and S-41 said so: the crisis switch is a RISK dial, so every column in it is contaminated by
the drawdown-for-return trade S-40 corrected S-38 on, and "lower CAR, lower MaxDD" is not a
verdict on an ensemble - it is a verdict on how much risk the ensemble happens to carry.

The clean version of the experiment lives on the axes S-38 labelled FITTED that are NOT risk
dials, where higher CAR at equal drawdown is unambiguously better and an ensemble has nothing
to hide behind. S-41 also handed this item a second, sharper reason to run: clause 4 found the
36 crisis-switch cells hold the IDENTICAL name set on 86.83% of sessions, so that ensemble was
"a vote on GROSS, not on which names to own" - which is the one shape where weight-blending has
almost nothing to net and is therefore nearly indistinguishable from return-averaging. The
signal axes are the opposite shape by construction: `mom_skip`, the fourth momentum horizon and
`top_n` change WHICH names are ranked into the book, so the 36 cells disagree about membership
rather than about size, and netting 36 opinions into one order list is a real operation rather
than an arithmetic identity. If weight-blending is ever worth its complexity on this sleeve,
it is here; if it is not worth it here, it is not worth it anywhere on this book.

THE GRID, pre-registered before the first simulation
----------------------------------------------------
Three axes, every value taken from S-38's own pre-registered value list for that axis, the
shipped point inside each, and 3 x 3 x 4 = 36 cells so the cell count matches S-41 exactly and
the fractional-boundary arithmetic stays comparable:

    mom_skip        {2, 5*, 10}             S-38 list (2,3,5,8,10,15,20); S-10's skip walk
    mom_lookbacks4  {220, 252*, 300}        S-38 list (150,...,320); S-9's shelf is 220-300
    top_n           {2, 3*, 4, 5}           S-38 list (2,3,4,5,6); S-7/S-8's CAR tables

WHY `rank_persist` AND `entry_mode`/`min_momentum` ARE EXCLUDED, stated so it is a decision and
not an omission. Both are OFF in the shipped book (`rank_persist=0`, `entry_mode="absolute"`,
`min_momentum=0.0`) and neither appears in S-38's eight axes. A grid over an off-by-default
feature is an ON/OFF ABLATION, not a selection surface: the "shipped cell" would sit on the
boundary rather than inside, half the cells would carry a mechanism the book has never adopted,
and an ensemble's result would mix "should the feature exist" with "at what level" - two
questions with different answers and different owners. They are ablation items, not ensemble
items, and S-42 does not pretend otherwise.

`target_vol`, `target_exposure`, `margin_budget`, `max_gross_weight` and the drawdown cap do
not appear on any axis: they are the owner's and are READ here, never moved. The crisis switch
sits at its shipped cell in all 36, so nothing here re-opens S-40 or S-41.

PRE-REGISTERED, eight clauses
-----------------------------
(1a) IDENTITY. At the shipped `Params()` this harness reproduces the deployed cell to the
     digit: CAR 22.192150170492255%, 5,052 orders, 2012-2026 at zero cost - the figure S-25
     through S-41 each quote. If it misses, nothing below may be read.
(1b) WEIGHT-PATH IDENTITY, re-proved rather than inherited. The shipped cell's target weights
     are extracted day by day and fed BACK through `legs_simulate(weights_fn=...)`; the
     resulting book must match (1a) to the digit on CAR *and* order count. S-41 proved this
     for its grid, but the extraction here runs under different `history_bars`, so the licence
     is re-earned. If 1b misses, nothing below may be read.
(1c) SESSION-SET INVARIANCE, and this clause exists only because S-42's axes have a property
     S-41's did not: they MOVE `Params.history_bars` (307 to 360 across the 36 cells, against
     a constant 307 in S-41's grid). Two assertions, both arithmetic rather than hope. First,
     every cell's weight path must cover the IDENTICAL set of dates, which holds iff the
     window's own start index dominates `history_bars` - 2012-01-03 sits at index 3,524 of a
     7,213-bar store, so it does, but it is ASSERTED not assumed. Second, every path-fed book
     is executed with the SHIPPED `Params()`, which is exact because `legs_simulate` reads
     `params` only for `i0` and the traded universe once `weights_fn` is supplied (verified in
     `sweep_s25.py:203-246`); so all 36 cells and every blend run through one identical
     rebalance and differ in nothing but their weights. Without both, S-41's clause 3b
     discipline - every row on the same session count - cannot be met on this grid.
(2) PURITY, inherited from S-40 clause 2b / S-41 clause 2 and re-asserted: `dd_halve > 1.0 and
    dd_flat > 1.0`, so `drawdown_multiplier`'s `dd = 1 - last/peak` (bounded by 1.0) can never
    fire and the overlay returns 1.0 on every session. Target weights are then a pure function
    of (prices, params), which is what makes both a 36-cell blend and a year-stitched selector
    well defined at all.
(3) THE GRID, zero cost, on IS 2012-2019 / FULL 2012-2026 / OOS 2020-2026. Where the shipped
    cell ranks among the 36 on each window, and the argmax of each window. This is S-40 clause
    3's diagnostic applied to the signal axes, and it is the AUD-11 question for them: S-40
    found the shipped crisis-switch cell is rank 1 of 36 on the half labelled OOS and rank 24
    of 36 on the half labelled IS. Whatever this table says will be said out loud.
(4) THE BLEND. `w_blend[t] = mean over the 36 cells of w_cell[t]`, each cell's path carrying
    its own hysteresis state, executed in the deployed `mode=both` convention, against the
    shipped cell and the grid's own FULL-argmax.
(4b) THE MECHANISM, and the pre-registered contrast with S-41. Reported: names held, the share
     of sessions on which the blend's name set is IDENTICAL to the shipped cell's, and the
     share of blended target weight below the 0.01x no-trade band. S-41 measured 86.83%
     identical name sets and a 0.002% band loss. PRE-REGISTERED READING: if the identical-name
     share here is materially below S-41's, the ensemble is voting on MEMBERSHIP rather than on
     GROSS and weight-blending is doing real netting; if it is not, the signal axes turn out to
     be gross dials in disguise and that is the finding. Band bar unchanged from S-41: more
     than 10% of target weight lost at $100k and the blend is not executable at the deployed
     size.
(4c) ROBUSTNESS. The blend is re-run over the 35 cells with the SHIPPED cell removed. Within
     0.05 Sharpe and the result is a property of the ensemble; otherwise the blend is the
     incumbent in a costume and must be reported as such. S-41's bar, verbatim.
(5) COST. Every headline book re-run in S-22's honest historical cell C (2 bp one-way spread
    plus IBKR Pro financing on the historical effective fed funds rate) on FULL and OOS, with
    the paired daily return difference against the shipped cell and its t.
(6) TURNOVER. Orders/yr, turnover/yr and fees for the blend against the shipped cell. S-41
    measured 1.26x orders at 0.99x turnover - more orders, the same turnover - because its
    ensemble only ever voted on gross. PRE-REGISTERED EXPECTATION HERE: turnover RISES, because
    36 cells that disagree about membership hand the book a target that drifts between name
    sets instead of jumping between them, and a drifting target is traded more than a stepping
    one. If turnover falls, the netting story is real and it is the first evidence of it.
(7) THE PROMOTION DECISION, identical bars to S-41 so the two items are comparable. The blend
    is a PROMOTION CANDIDATE only if, fully charged, on BOTH FULL and OOS: Sharpe >= shipped,
    MaxDD <= shipped, CAR >= shipped - 1.0 points, and clause 4b's band test passes.
(8) THE DECISION BAR, which is the one clause 7 is the wrong instrument for. S-41 clause 7b's
    framing: the shipped cell is the PROMOTION bar, a real-time selector is the DECISION bar,
    because the shipped cell is only on the menu with hindsight. S-40's walk-forward existed
    for the crisis switch; there is none for these axes, so it is built here. For each year Y
    from 2016 the selector sees only 2012-01-03..(Y-1)-12-31 and takes that window's argmax,
    under a CAR objective and a Sharpe objective. ONE IMPROVEMENT ON S-40's CONSTRUCTION, and
    it removes an approximation rather than adding an assumption: S-40 stitched the chosen
    cells' RETURNS year by year and had to bound the unmodelled rebalance at each boundary.
    Here the selection is expressed as a WEIGHTS path - `wf[t] = w_of(cell chosen for year(t))`
    - and executed through `weights_fn`, so the boundary rebalance is a real trade at a real
    spread and there is nothing left to bound. Reported: the hit rate on the shipped cell, the
    number of boundary switches, and the blend against both selectors on the identical span.

DIAGNOSTIC. No shipped or runner-loaded file is touched: the shipped `Params()` defaults,
`live/*`, `champion.json` and all scheduled tasks are untouched, so no deploy gate and no
`--replay` is owed. No new shared-code argument is added either - S-41's `weights_fn` is
already in place and clause 1b re-proves it - so this item changes no file any other track
reads. Every ledger row is tagged DIAGNOSTIC.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import pickle
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "algorithms" / "s1_momo"))
sys.path.insert(0, str(REPO / "scripts"))

import signals as sig                                          # noqa: E402
import sweep_s41 as s41                                        # noqa: E402
from sweep_s19 import MIN_ORDER_VALUE, START_EQUITY, paired    # noqa: E402
from sweep_s25 import legs_simulate                            # noqa: E402
from sweep_s31 import describe                                 # noqa: E402
from sweep_s40 import (S25_DEPLOYED_CAR, S25_DEPLOYED_ORDERS,  # noqa: E402
                       SPREAD_BPS, END, WINDOWS, WF_FIRST_YEAR)
from sweep_s41 import (BAND_LOSS_BAR, CAR_GIVEAWAY, SHARPE_TIE, HDR,  # noqa: E402
                       band_loss, row, summarize_span)

LEDGER = REPO / "research" / "experiments.jsonl"
CACHE_PATH = REPO / "results" / "s42_cache.pkl"
OUT_PATH = REPO / "results" / "s42_full.txt"

#: the pre-registered grid - every value from S-38's own list for that axis
MOM_SKIPS = (2, 5, 10)
MOM_LB4 = (220, 252, 300)
TOP_NS = (2, 3, 4, 5)
BASE_LOOKBACKS = (20, 60, 120)
SHIPPED_CELL = (5, 252, 3)                 # (mom_skip, mom_lookbacks[-1], top_n)

#: clause 8 - the walk-forward span, S-40's own first speaking year
WF_SPAN_START = f"{WF_FIRST_YEAR}-01-01"

#: clause 4b - S-41's measured contrast, quoted so the comparison is pre-registered
S41_SAME_NAMES_FULL = 86.83
S41_BAND_LOSS_FULL = 0.002


# ------------------------------------------------------------------------------- the grid

def grid_cells() -> list[dict]:
    return [{"mom_skip": s, "mom_lookbacks": BASE_LOOKBACKS + (lb,), "top_n": n}
            for s in MOM_SKIPS for lb in MOM_LB4 for n in TOP_NS]


def cell_key(over: dict) -> tuple:
    return (over["mom_skip"], over["mom_lookbacks"][-1], over["top_n"])


def cell_name(over: dict) -> str:
    s, lb, n = cell_key(over)
    return f"skip={s} lb4={lb} n={n}"


def is_shipped(over: dict) -> bool:
    return cell_key(over) == SHIPPED_CELL


def path_key(over: dict, window: str) -> tuple:
    return (cell_key(over), window)


# ------------------------------------------------------------------- workers (clause 1c)

def _path_job(args: tuple) -> tuple:
    """One cell's target-weight path over one window, on `legs_simulate`'s own sessions.

    Identical in construction to `sweep_s41._path_job`; re-implemented here only because the
    cache key is this item's `(mom_skip, lb4, top_n)` triple rather than S-41's regime pair.
    """
    over, window = args
    params = dataclasses.replace(sig.Params(), **over)
    start, end = WINDOWS[window]
    closes = s41._FRAMES["close"]
    i0, i1 = s41._bounds(closes.index, params, start, end)
    state: dict = {}
    curve = [float(START_EQUITY)]
    path: dict = {}
    for i in range(i0, i1):
        lo = max(0, i - params.history_bars)
        targets, diag = sig.target_weights(closes.iloc[lo:i], curve, params, state)
        state = diag.get("state", {})
        curve.append(float(START_EQUITY))
        path[closes.index[i]] = {t: float(v) for t, v in targets.items() if v}
    return (cell_key(over), window), path, int(params.history_bars)


def _sim_job(args: tuple) -> tuple:
    """One book. `path` None runs the shipped signal in-loop; otherwise it is executed.

    Clause 1c: the executing `Params()` is ALWAYS the shipped one when a path is supplied, so
    every row in this item runs through one identical rebalance.
    """
    label, start, end, costed, path = args
    fn = None if path is None else (lambda d, _p=path: _p.get(d, {}))
    book = legs_simulate(s41._FRAMES, sig.Params(), "both", start, end,
                         SPREAD_BPS if costed else 0.0, s41._FIN if costed else None,
                         weights_fn=fn)
    d = describe(book, label)
    d.update(window=start + ".." + end, start=start, end=end, cell=label, costed=costed)
    keep = [c for c in ("date", "ret", "gross_x", "orders", "turnover", "prev") if c in book]
    return (label, start, end, costed), d, book[keep].to_dict("records")


def run_pool(jobs: list, fn, cache: dict, workers: int, label: str, key_of) -> None:
    todo = [j for j in jobs if key_of(j) not in cache]
    if not todo:
        return
    print(f"  [{label}] {len(todo)} jobs on {workers} workers ...", flush=True)
    t0 = dt.datetime.now()
    with ProcessPoolExecutor(max_workers=workers, initializer=s41._init_worker) as ex:
        for out in ex.map(fn, todo):
            cache[out[0]] = out[1:]
    print(f"  [{label}] done in {(dt.datetime.now() - t0).total_seconds():.0f}s\n", flush=True)


# ---------------------------------------------------------------------------- the clauses

def h(title: str) -> None:
    print(f"\n{'=' * 100}\n{title}\n{'=' * 100}")


def book_of(cache: dict, label: str, window: str, costed: bool):
    start, end = WINDOWS[window] if window in WINDOWS else (WF_SPAN_START, END)
    return cache.get((label, start, end, costed))


def clause_1(cache: dict, paths: dict, cells: list[dict]) -> bool:
    h("CLAUSE 1 - identity, the weight-path licence, and session-set invariance")
    ok = True
    for label, key in (("1a in-loop         ", "shipped (in-loop)"),
                       ("1b weights fed back", "shipped (fed its own weights)")):
        d = book_of(cache, key, "FULL", False)[0]
        dc, do = abs(d["CAR"] - S25_DEPLOYED_CAR), d["orders"] - S25_DEPLOYED_ORDERS
        good = dc < 1e-9 and do == 0
        ok &= good
        print(f"  {label}  CAR {d['CAR']:.12f}%  orders {d['orders']:,}   "
              f"delta {dc:.2e} / {do:+d}   {'OK' if good else 'MISMATCH'}")

    print("\n  1c session-set invariance (the clause S-41 did not need):")
    hbs = sorted({paths[path_key(c, 'FULL')][1] for c in cells})
    print(f"    history_bars across the 36 cells: {hbs[0]} .. {hbs[-1]}  "
          f"({len(hbs)} distinct values; S-41's grid had 1)")
    for window in ("FULL", "OOS"):
        sets = {frozenset(paths[path_key(c, window)][0]) for c in cells}
        n = len(next(iter(sets)))
        good = len(sets) == 1
        ok &= good
        print(f"    {window:<5} {len(sets)} distinct date set(s) over 36 cells, "
              f"{n:,} sessions each   {'OK' if good else 'MISMATCH'}")
    print("    -> the window start index dominates history_bars, so every cell, every blend\n"
          "       and every selector below is measured on one identical session set.")
    return ok


def clause_2() -> bool:
    h("CLAUSE 2 - purity (arithmetic, not a simulation)")
    p = sig.Params()
    ok = p.dd_halve > 1.0 and p.dd_flat > 1.0
    print(f"  dd_halve {p.dd_halve}  dd_flat {p.dd_flat}   dd = 1 - last/peak <= 1.0")
    print(f"  overlay is constant 1.0 on every session -> weights are f(prices, params): "
          f"{'OK' if ok else 'VIOLATED'}")
    return ok


def clause_3(cache: dict, cells: list[dict]) -> dict:
    h("CLAUSE 3 - the 36-cell signal grid, zero cost: where the shipped cell actually sits")
    out: dict = {}
    for window in ("IS", "FULL", "OOS"):
        rows = []
        for c in cells:
            d = book_of(cache, cell_name(c), window, False)
            if d:
                rows.append((c, d[0]))
        out[window] = rows
    print(f"  {'window':<6}{'shipped CAR':>13}{'grid mean':>11}{'vs mean':>10}"
          f"{'pct':>7}{'rank':>10}{'argmax cell':>22}{'argmax CAR':>12}")
    print("  " + "-" * 92)
    for window in ("IS", "FULL", "OOS"):
        rows = out[window]
        cars = np.array([d["CAR"] for _, d in rows])
        ship = next(d["CAR"] for c, d in rows if is_shipped(c))
        rank = int((cars > ship).sum()) + 1
        pct = 100.0 * (cars <= ship).mean()
        best = max(rows, key=lambda r: r[1]["CAR"])
        print(f"  {window:<6}{ship:>13.3f}{cars.mean():>11.3f}{ship - cars.mean():>+10.3f}"
              f"{pct:>6.0f}th{rank:>6} of 36{cell_name(best[0]):>22}{best[1]['CAR']:>12.3f}")
    print("\n  For scale, S-40's crisis-switch grid on the identical windows: shipped ranked\n"
          "  24 of 36 on IS, 14 of 36 on FULL and 1 of 36 on OOS - the shape that located\n"
          "  AUD-11. The row above is the same diagnostic on the axes that pick names.")
    print(f"\n  full-period spread of the 36 cells: min {min(d['CAR'] for _, d in out['FULL']):.3f}"
          f"  max {max(d['CAR'] for _, d in out['FULL']):.3f}  "
          f"sd {np.std([d['CAR'] for _, d in out['FULL']], ddof=1):.3f} CAR points")
    return out


def clause_3b(grid: dict) -> None:
    """Is this surface STABLE? S-40's own diagnostic on the crisis switch, re-run here.

    Not pre-registered as a clause - it is the obvious reading of clause 3's table and it is
    labelled post hoc for that reason - but it is the quantity that separates "the shipped
    cell ranks high in both halves" from "the shipped cell ranks high in both halves by
    accident". S-40 measured IS-to-OOS Spearman +0.208 across the 36 crisis-switch cells and
    called it the mechanism behind a selector that never beats its own grid mean.
    """
    h("CLAUSE 3b (post hoc) - is the signal surface stable across the two halves?")
    keys = [cell_key(c) for c, _ in grid["IS"]]
    lut = {w: {cell_key(c): d for c, d in grid[w]} for w in ("IS", "OOS", "FULL")}
    a = np.array([lut["IS"][k]["CAR"] for k in keys])
    b = np.array([lut["OOS"][k]["CAR"] for k in keys])
    ra, rb = pd.Series(a).rank().to_numpy(), pd.Series(b).rank().to_numpy()
    sp = float(np.corrcoef(ra, rb)[0, 1])
    pe = float(np.corrcoef(a, b)[0, 1])
    print(f"  IS -> OOS across the 36 cells:  Spearman {sp:+.3f}   Pearson {pe:+.3f}")
    print(f"  S-40's crisis-switch grid, same windows:  Spearman +0.208   Pearson +0.330")
    top3 = [k for k in keys if ra[keys.index(k)] >= 34]
    print(f"\n  the IS top-3 cells {[f'skip={k[0]} lb4={k[1]} n={k[2]}' for k in top3]}")
    print(f"    their OOS ranks: {[int(rb[keys.index(k)]) for k in top3]} of 36")
    ship = SHIPPED_CELL
    print(f"  the shipped cell skip={ship[0]} lb4={ship[1]} n={ship[2]}: "
          f"IS rank {37 - int(ra[keys.index(ship)])}, OOS rank {37 - int(rb[keys.index(ship)])}")
    both = [k for k in keys
            if lut["IS"][k]["CAR"] > lut["IS"][ship]["CAR"]
            and lut["OOS"][k]["CAR"] > lut["OOS"][ship]["CAR"]]
    print(f"\n  cells that beat the shipped cell on CAR in BOTH halves: {len(both)} of 36")
    for k in both:
        print(f"    skip={k[0]} lb4={k[1]} n={k[2]:<3}  IS {lut['IS'][k]['CAR']:6.3f} "
              f"(shipped {lut['IS'][ship]['CAR']:.3f})   OOS {lut['OOS'][k]['CAR']:6.3f} "
              f"(shipped {lut['OOS'][ship]['CAR']:.3f})   FULL MaxDD "
              f"{lut['FULL'][k]['MaxDD']:6.3f} (shipped {lut['FULL'][ship]['MaxDD']:.3f})")


def clause_4(cache: dict, grid: dict) -> dict:
    h("CLAUSE 4 - the weight blend against the cell that shipped, zero cost")
    print(HDR)
    print("-" * len(HDR))
    out = {}
    for window in ("FULL", "IS", "OOS"):
        best = max(grid[window], key=lambda r: r[1]["CAR"])
        for label in ("shipped (in-loop)", "blend36", "blend35 (no shipped)"):
            d = book_of(cache, label, window, False)
            if d:
                out[(label, window)] = d[0]
                print(row(d[0]))
        print(row(best[1], f"   <- FULL-window argmax ({cell_name(best[0])}), HINDSIGHT"))
        print("-" * len(HDR))
    return out


def composition(paths: dict, cells: list[dict], bl: dict, window: str) -> dict:
    """Clause 4b: does the blend disagree with the shipped cell about WHICH names?"""
    ship = paths[path_key(next(c for c in cells if is_shipped(c)), window)][0]
    same = diff = ship_only = 0
    extra = []
    for d, w in bl.items():
        sw = ship.get(d, {})
        if not sw and not w:
            continue
        if set(sw) == set(w):
            same += 1
        elif sw and not w:
            ship_only += 1
        else:
            diff += 1
        extra.append(len(set(w) - set(sw)))
    tot = max(same + diff + ship_only, 1)
    return {"same_names": 100.0 * same / tot, "diff_names": 100.0 * diff / tot,
            "ship_only": 100.0 * ship_only / tot, "n": tot,
            "extra_names": float(np.mean(extra)) if extra else float("nan")}


def clause_4b(paths: dict, cells: list[dict], bl: dict, window: str) -> dict:
    h(f"CLAUSE 4b - what is the ensemble actually voting on? ({window})")
    comp = composition(paths, cells, bl, window)
    names = np.array([len(w) for w in bl.values()])
    ship = paths[path_key(next(c for c in cells if is_shipped(c)), window)][0]
    sn = np.array([len(ship.get(d, {})) for d in bl])
    print(f"  sessions {len(bl):,}")
    print(f"  names in the blended target: mean {names.mean():.2f}  "
          f"median {np.median(names):.0f}  max {names.max()}")
    print(f"  names in the shipped target: mean {sn.mean():.2f}  "
          f"median {np.median(sn):.0f}  max {sn.max()}")
    print(f"\n  against the shipped cell, on sessions where either holds something "
          f"(n {comp['n']:,}):")
    print(f"    identical name set, differing only in size   {comp['same_names']:>7.2f}%   "
          f"(S-41 measured {S41_SAME_NAMES_FULL}%)")
    print(f"    a different name set                         {comp['diff_names']:>7.2f}%")
    print(f"    shipped holds, the blend is flat             {comp['ship_only']:>7.2f}%")
    print(f"    names the blend holds that shipped does not  {comp['extra_names']:>7.2f} per session")
    verdict = ("MEMBERSHIP - the ensemble owns names the incumbent does not, so weight-blending\n"
               "       has real netting to do and is NOT the return-average in disguise"
               if comp["same_names"] < S41_SAME_NAMES_FULL - 10
               else "GROSS - same shape as S-41; the signal axes behave like size dials here")
    print(f"\n    -> the ensemble is a vote on {verdict}")
    b = band_loss(bl, START_EQUITY)
    print(f"\n  no-trade band {MIN_ORDER_VALUE:.3f}x equity, at ${START_EQUITY:,.0f}")
    print(f"    share of blended target weight below the band   "
          f"{b['pct_weight_lost']:>7.3f}%  (bar {BAND_LOSS_BAR}%, S-41 measured "
          f"{S41_BAND_LOSS_FULL}%)")
    print(f"    sessions with at least one sub-band target      {b['days_any_small']:>7.2f}%")
    ok = b["pct_weight_lost"] <= BAND_LOSS_BAR
    print(f"\n  clause 4b band test: {'PASS' if ok else 'FAIL'}")
    return {"ok": ok, **b, **comp}


def clause_4c(c4: dict) -> bool:
    h("CLAUSE 4c - does the blend survive deleting the shipped cell from the grid?")
    ok = True
    for window in ("FULL", "IS", "OOS"):
        a, b = c4.get(("blend36", window)), c4.get(("blend35 (no shipped)", window))
        if not (a and b):
            continue
        ds = b["Sharpe"] - a["Sharpe"]
        good = abs(ds) <= SHARPE_TIE
        ok &= good
        print(f"  {window:<5} 35-cell minus 36-cell   Sharpe {ds:+.4f}   "
              f"MaxDD {b['MaxDD'] - a['MaxDD']:+.3f}   CAR {b['CAR'] - a['CAR']:+.3f}   "
              f"{'tie' if good else 'MOVES'}")
    print(f"\n  clause 4c: "
          f"{'a property of the ensemble' if ok else 'the blend leans on the shipped cell'}")
    return ok


def clause_5(cache: dict, grid: dict) -> dict:
    h("CLAUSE 5 - fully charged, S-22 cell C (2 bp one-way spread + IBKR Pro financing)")
    print(HDR)
    print("-" * len(HDR))
    out = {}
    labels = ["shipped (in-loop)", "blend36", "blend35 (no shipped)"]
    for window in ("FULL", "OOS"):
        best = cell_name(max(grid[window], key=lambda r: r[1]["CAR"])[0])
        for label in labels + [best]:
            d = book_of(cache, label, window, True)
            if d:
                out[(label, window)] = d[0]
                tag = "   <- window argmax, HINDSIGHT" if label == best else ""
                print(row(d[0], tag))
        print("-" * len(HDR))
    print("\n  paired daily return difference against the shipped cell, same sessions:")
    for window in ("FULL", "OOS"):
        base = book_of(cache, "shipped (in-loop)", window, True)[1]
        for label in ("blend36", "blend35 (no shipped)"):
            d = book_of(cache, label, window, True)
            if not d:
                continue
            pr = paired(d[1], base, label, "shipped")
            print(f"    {window:<5} {pr['pair']:<42} {pr['bps_per_day']:+8.3f} bps/day  "
                  f"t {pr['t']:+6.2f}  n {pr['days']:,}")
    return out


def clause_6(c5: dict) -> None:
    h("CLAUSE 6 - turnover: what netting 36 opinions into one order list actually costs")
    print(f"  {'book':<30}{'orders':>9}{'ord/yr':>9}{'turn/yr':>10}{'fees':>12}")
    print("  " + "-" * 70)
    for label in ("shipped (in-loop)", "blend36", "blend35 (no shipped)"):
        d = c5.get((label, "FULL"))
        if not d:
            continue
        yrs = d["sessions"] / 252.0
        print(f"  {label:<30}{d['orders']:>9,}{d['orders'] / yrs:>9.0f}"
              f"{d['turnover_x']:>10.1f}{d['fees']:>12,.0f}")
    s, b = c5.get(("shipped (in-loop)", "FULL")), c5.get(("blend36", "FULL"))
    if s and b:
        print(f"\n  against the single shipped account the blend trades "
              f"{b['orders'] / s['orders']:.2f}x the orders and\n"
              f"  {b['turnover_x'] / s['turnover_x']:.2f}x the turnover, for "
              f"{b['fees'] / s['fees']:.2f}x the fees.  S-41 measured 1.26x / 0.99x / 1.01x\n"
              f"  on the crisis-switch grid, where the cells only ever disagreed about size.")


def clause_7(c5: dict, band_ok: bool) -> bool:
    h("CLAUSE 7 - the pre-registered promotion decision (S-41's bars, verbatim)")
    verdicts = []
    for window in ("FULL", "OOS"):
        a, s = c5.get(("blend36", window)), c5.get(("shipped (in-loop)", window))
        if not (a and s):
            continue
        sh, dd = a["Sharpe"] >= s["Sharpe"], a["MaxDD"] <= s["MaxDD"]
        car = a["CAR"] >= s["CAR"] - CAR_GIVEAWAY
        verdicts.append(sh and dd and car)
        print(f"  {window:<5} Sharpe {a['Sharpe']:.3f} vs {s['Sharpe']:.3f} "
              f"{'PASS' if sh else 'FAIL':<5}   "
              f"MaxDD {a['MaxDD']:.3f} vs {s['MaxDD']:.3f} {'PASS' if dd else 'FAIL':<5}   "
              f"CAR {a['CAR']:.3f} vs {s['CAR']:.3f} (-{CAR_GIVEAWAY:.1f} allowed) "
              f"{'PASS' if car else 'FAIL'}")
    print(f"  band test {'PASS' if band_ok else 'FAIL'}")
    ok = bool(verdicts) and all(verdicts) and band_ok
    print(f"\n  VERDICT: {'PROMOTION CANDIDATE' if ok else 'NOT a promotion candidate'}")
    print("  Either way nothing ships from here: a 36-cell blend is not expressible in one\n"
          "  `Params()`, so the book would need a signal-level change and its own LEAN run.")
    return ok


# ------------------------------------------------------------------ clause 8: walk-forward

def select(grid_full: list, objective: str, upto: pd.Timestamp) -> dict:
    """The argmax cell over 2012-01-03..`upto`, measured on the cells' own daily returns."""
    best, best_v = None, -np.inf
    for c, _ in grid_full:
        b = _RET[cell_key(c)]
        r = b[b["date"] <= upto]["ret"].to_numpy()
        if len(r) < 252:
            continue
        v = summarize_span(pd.DataFrame({"ret": r}), "")[objective]
        if v > best_v:
            best, best_v = c, v
    return best


_RET: dict = {}


def wf_path(paths: dict, cells: list[dict], grid_full: list,
            objective: str) -> tuple[dict, list]:
    """Clause 8: the selection as a WEIGHTS path, so the boundary rebalance is a real trade."""
    picks = []
    out: dict = {}
    ship_path = paths[path_key(cells[0], "FULL")][0]
    dates = [d for d in sorted(ship_path) if d >= pd.Timestamp(WF_SPAN_START)]
    for year in sorted({d.year for d in dates}):
        cell = select(grid_full, objective, pd.Timestamp(f"{year - 1}-12-31"))
        picks.append((year, cell))
        p = paths[path_key(cell, "FULL")][0]
        for d in dates:
            if d.year == year:
                out[d] = p.get(d, {})
    return out, picks


def clause_8(cache: dict, picks: dict) -> None:
    h("CLAUSE 8 - against what a real-time selector actually gets (S-41 clause 7b's framing)")
    cut = pd.Timestamp(WF_SPAN_START)
    rows = []
    for label in ("shipped (in-loop)", "blend36", "wf-CAR", "wf-Sharpe"):
        for costed in (False, True):
            d = book_of(cache, label, "FULL", costed)
            if not d:
                continue
            b = d[1]
            rows.append(summarize_span(b[b["date"] >= cut],
                                       f"{label} [{'cost' if costed else 'zero'}]"))
    print(f"  {'book':<40}{'sess':>6}{'CAR%':>9}{'Sharpe':>8}{'MaxDD%':>9}{'std':>7}")
    print("  " + "-" * 79)
    for r in rows:
        print(f"  {r['cell']:<40}{r['sessions']:>6}{r['CAR']:>9.3f}{r['Sharpe']:>8.3f}"
              f"{r['MaxDD']:>9.3f}{r['std']:>7.3f}")
    print("\n  what the selector picked, and how often it found the cell that shipped:")
    for obj, ps in picks.items():
        hits = sum(1 for _, c in ps if is_shipped(c))
        switches = sum(1 for i in range(1, len(ps))
                       if cell_key(ps[i][1]) != cell_key(ps[i - 1][1]))
        print(f"    {obj:<8} shipped cell chosen in {hits} of {len(ps)} years, "
              f"{switches} boundary switches")
        print(f"             {' -> '.join(cell_name(c) for _, c in ps)}")
    for obj in picks:
        a = next((r for r in rows if r["cell"].startswith("blend36 [cost")), None)
        s = next((r for r in rows if r["cell"].startswith(f"wf-{obj} [cost")), None)
        if a and s:
            print(f"\n  blend36 - wf-{obj} (both fully charged): CAR {a['CAR'] - s['CAR']:+.3f}"
                  f"   Sharpe {a['Sharpe'] - s['Sharpe']:+.3f}"
                  f"   MaxDD {a['MaxDD'] - s['MaxDD']:+.3f}")


def clause_8b(cache: dict, cells: list[dict]) -> None:
    """C-8's attack on S-41 clause 7b, answered here on S-42's own grid before it is made.

    The `critic` track (C-8, 2026-09-13) showed that S-41's "the blend beats the walk-forward
    selector" margin is not evidence ABOUT THE ENSEMBLE, because 23 of 36 FIXED cells already
    dominate that same selector on all three metrics - a margin over the selector measures how
    bad the selector is, not how good the blend is. The right object is the blend's RANK among
    the cells it is built from, and whether any fixed cell DOMINATES it. Both are computed here
    on the same 2,684-session span, at ZERO cost, which is the only cell every one of the 36 was
    run in; the costed rows above are unaffected and the comparison is like for like.
    """
    h("CLAUSE 8b - C-8's test, applied to this grid before the critic has to")
    cut = pd.Timestamp(WF_SPAN_START)

    def span(label):
        d = book_of(cache, label, "FULL", False)
        return summarize_span(d[1][d[1]["date"] >= cut], label) if d else None

    ref = {n: span(n) for n in ("blend36", "shipped (in-loop)", "wf-CAR", "wf-Sharpe")}
    fixed = [(c, span(cell_name(c))) for c in cells]

    def dominates(a, b):
        return a["CAR"] > b["CAR"] and a["Sharpe"] > b["Sharpe"] and a["MaxDD"] < b["MaxDD"]

    for obj in ("wf-CAR", "wf-Sharpe"):
        n = sum(1 for _, d in fixed if dominates(d, ref[obj]))
        print(f"  fixed cells that DOMINATE {obj:<10} on all three metrics: "
              f"{n:>2} of 36   (C-8 measured 23 of 36 for S-41's selector)")
    print("  -> a margin over the selector is a statement about the selector. The blend's own\n"
          "     case has to be its rank among the cells it averages:")
    for metric, better in (("CAR", "high"), ("Sharpe", "high"), ("MaxDD", "low")):
        vals = np.array([d[metric] for _, d in fixed])
        b = ref["blend36"][metric]
        s = ref["shipped (in-loop)"][metric]
        rank_b = int((vals > b).sum()) + 1 if better == "high" else int((vals < b).sum()) + 1
        rank_s = int((vals > s).sum()) + 1 if better == "high" else int((vals < s).sum()) + 1
        print(f"    {metric:<7} blend36 {b:>8.3f} -> rank {rank_b:>2} of 36      "
              f"shipped {s:>8.3f} -> rank {rank_s:>2} of 36")
    dom_b = [c for c, d in fixed if dominates(d, ref["blend36"])]
    dom_s = [c for c, d in fixed if dominates(d, ref["shipped (in-loop)"])]
    print(f"\n  fixed cells that DOMINATE blend36 on all three:            {len(dom_b):>2} of 36")
    print(f"  fixed cells that DOMINATE the shipped cell on all three:   {len(dom_s):>2} of 36")
    if dom_b:
        print(f"    {', '.join(cell_name(c) for c in dom_b[:6])}"
              f"{' ...' if len(dom_b) > 6 else ''}")


# --------------------------------------------------------------------------------- ledger

def record(rows: list[dict], skip: bool) -> None:
    if skip:
        print(f"\n  --no-record: {len(rows)} rows NOT written\n")
        return
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with LEDGER.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({
                "ts": stamp, "algorithm": "daily/s42_blend", "class": "book",
                "tag": f"S-42 {r['cell']} @ {r['start']}..{r['end']} "
                       f"({'cell C cost' if r['costed'] else 'zero cost'}, DIAGNOSTIC)",
                "commit": "", "run_dir": "",
                "track": "S-42", "start": r["start"], "end": r["end"],
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

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cache: dict = {}
    if CACHE_PATH.exists() and not a.fresh:
        cache = pickle.loads(CACHE_PATH.read_bytes())
        print(f"cache: {len(cache)} entries\n")

    cells = grid_cells()
    assert len(cells) == 36, len(cells)
    assert sum(is_shipped(c) for c in cells) == 1, "the shipped cell must be in the grid"
    no_ship = [c for c in cells if not is_shipped(c)]
    shipped = next(c for c in cells if is_shipped(c))

    # ---- weight paths. IS is a prefix of FULL (same start, same i0, state from {}).
    run_pool([(c, w) for c in cells for w in ("FULL", "OOS")], _path_job, cache, a.workers,
             "weight paths", key_of=lambda j: path_key(j[0], j[1]))
    CACHE_PATH.write_bytes(pickle.dumps(cache))
    paths = {k: cache[k] for k in cache if len(k) == 2 and isinstance(k[0], tuple)}
    for c in cells:
        ki = path_key(c, "IS")
        if ki not in paths:
            cut = pd.Timestamp(WINDOWS["IS"][1])
            kf = path_key(c, "FULL")
            paths[ki] = ({d: w for d, w in paths[kf][0].items() if d <= cut}, paths[kf][1])

    blends = {}
    for w in ("FULL", "IS", "OOS"):
        blends[("blend36", w)] = _blend(paths, cells, w)
        blends[("blend35 (no shipped)", w)] = _blend(paths, no_ship, w)

    # ---- the books. Everything but 1a is path-fed and therefore cheap.
    jobs = [("shipped (in-loop)", *WINDOWS["FULL"], False, None),
            ("shipped (fed its own weights)", *WINDOWS["FULL"], False,
             paths[path_key(shipped, "FULL")][0])]
    for w in ("FULL", "IS", "OOS"):
        for c in cells:
            jobs.append((cell_name(c), *WINDOWS[w], False, paths[path_key(c, w)][0]))
        for (name, ww), bl in blends.items():
            if ww == w:
                jobs.append((name, *WINDOWS[w], False, bl))
    for w in ("IS", "OOS"):
        jobs.append(("shipped (in-loop)", *WINDOWS[w], False, None))
    for w in ("FULL", "OOS"):
        jobs.append(("shipped (in-loop)", *WINDOWS[w], True, None))
        for (name, ww), bl in blends.items():
            if ww == w:
                jobs.append((name, *WINDOWS[w], True, bl))
    run_pool(jobs, _sim_job, cache, a.workers, "books",
             key_of=lambda j: (j[0], j[1], j[2], j[3]))
    CACHE_PATH.write_bytes(pickle.dumps(cache))
    for k in list(cache):
        if len(k) == 4 and isinstance(cache[k][1], list):
            cache[k] = (cache[k][0], pd.DataFrame(cache[k][1]))

    ok = clause_1(cache, paths, cells)
    ok &= clause_2()
    if not ok:
        print("\nPRE-REGISTERED STOP: clause 1 or 2 failed, nothing below is readable.")
        return 1
    grid = clause_3(cache, cells)
    clause_3b(grid)

    # ---- clause 8 needs the cells' own daily returns and two more books
    global _RET
    _RET = {cell_key(c): book_of(cache, cell_name(c), "FULL", False)[1] for c in cells}
    picks = {}
    wf_jobs = []
    for obj in ("CAR", "Sharpe"):
        p, ps = wf_path(paths, cells, grid["FULL"], obj)
        picks[obj] = ps
        for costed in (False, True):
            wf_jobs.append((f"wf-{obj}", *WINDOWS["FULL"], costed, p))
    run_pool(wf_jobs, _sim_job, cache, a.workers, "walk-forward",
             key_of=lambda j: (j[0], j[1], j[2], j[3]))
    CACHE_PATH.write_bytes(pickle.dumps(cache))
    for k in list(cache):
        if len(k) == 4 and isinstance(cache[k][1], list):
            cache[k] = (cache[k][0], pd.DataFrame(cache[k][1]))

    c4 = clause_4(cache, grid)
    band = clause_4b(paths, cells, blends[("blend36", "FULL")], "FULL")
    clause_4b(paths, cells, blends[("blend36", "OOS")], "OOS")
    clause_4c(c4)
    c5 = clause_5(cache, grid)
    clause_6(c5)
    clause_7(c5, band["ok"])
    clause_8(cache, picks)
    clause_8b(cache, cells)

    rows = [cache[k][0] for k in cache if len(k) == 4 and "CAR" in cache[k][0]]
    record(rows, a.no_record)
    return 0


def _blend(paths: dict, cells: list[dict], window: str) -> dict:
    """Equal-weight mean of the cells' target weights, session by session.

    The denominator is the number of CELLS, never the number with an opinion - S-41's rule,
    kept so the two items' blends are the same object.
    """
    n = float(len(cells))
    keys = [path_key(c, window) for c in cells]
    out: dict = {}
    for d in paths[keys[0]][0]:
        agg: dict = {}
        for k in keys:
            for t, v in paths[k][0].get(d, {}).items():
                agg[t] = agg.get(t, 0.0) + v
        out[d] = {t: v / n for t, v in agg.items() if v}
    return out


if __name__ == "__main__":
    raise SystemExit(main())
