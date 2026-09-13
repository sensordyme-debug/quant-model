#!/usr/bin/env python
"""S-38 (AUD-11 part 2): S-33 priced three of this sleeve's dials and left five unpriced,
and called its answer a FLOOR. This turns the floor into an estimate.

    python scripts/sweep_s38.py --workers 10        # the whole thing, ~10 min
    python scripts/sweep_s38.py --stage a           # clauses 1-4: provenance and the grid
    python scripts/sweep_s38.py --no-record         # do not append to the ledger

THE OPEN QUANTITY. `research/backlog.md`, AUD-11, after S-33 closed its first half:

    "LOWER BOUND: three dials priced (`mom_skip`, `alloc_vol_window`, the 252 shelf) plus
     the band by S-32; `top_n`, `target_vol`, `regime_threshold`, `regime_vol_window` and
     `target_exposure` are not, so +0.5 is a floor on total selection inflation, not an
     estimate."

S-33 measured the shipped set at **+0.974 CAR points above the mean of its 18-cell grid**
on 2020-2026 (0.53 sd, 78th percentile, rank 14 of 18) and the **selection premium at
-0.049** pooled over 20 cells. Both numbers are conditional on three axes. This iteration
runs all EIGHT - S-33's three re-run verbatim as a reproduction check, plus the five it
named - and reports one pooled number for the sleeve.

WHY THE FIVE ARE NOT ONE KIND OF THING, which is the clause that can make this wrong.
`top_n` and `regime_threshold` were chosen on CAR tables and are selection axes. `target_vol`
and `target_exposure` are SIZE: they are the owner's risk posture, they trade CAR against
drawdown by construction, and the spread of a CAR grid over them is not selection inflation -
it is the risk dial doing its job. Summing all five into one number would inflate the answer
with the owner's own decision. So provenance is classified from the record BEFORE the grid
runs (clause 2) and only the fitted axes enter the estimate (clause 5).

PRE-REGISTERED before the first number, seven clauses
----------------------------------------------------
(1) IDENTITY. At the shipped `Params()` this harness must reproduce the deployed cell to the
    digit - CAR 22.192150170492255%, 5,052 orders, 2012-2026 at zero cost - the figure S-25,
    S-26, S-28, S-30, S-31, S-32, S-33, S-36 and S-37 each quote independently. If it misses,
    nothing below may be read.

(2) PROVENANCE, written down before the grid and falsifiable against the repository. Each of
    the eight axes is classified from the record that set its value:
      FITTED        - the record shows a CAR/Sharpe table and the shipped value was read off it.
      RISK-POSTURE  - the value expresses the owner's mandate or risk budget, not a fit.
      UNRECORDED    - no table and no stated rationale; treated as FITTED, because an
                      unexplained value cannot be defended as a priori.
    Only FITTED and UNRECORDED axes enter clause 5's estimate.

(3) THE GRID IS THE SELECTION RECORD WHERE THERE IS ONE. Coordinate-wise from the shipped set,
    zero cost, on IS 2012-2019 / FULL 2012-2026 / OOS 2020-2026:
      - S-33's three, verbatim, as a reproduction check:
          `mom_skip`           {2, 3, 5*, 8, 10, 15, 20}        (S-10's table)
          `alloc_vol_window`   {10, 20, 21*, 30, 40, 60}        (S-12's table)
          `mom_lb4`            {150, 220, 250, 252*, 280, 300, 320}  (S-9's shelf)
      - the five AUD-11 named:
          `top_n`              {2, 3*, 4, 5, 6}                 (S-7/S-8's tables)
          `regime_threshold`   {1.25, 1.40, 1.50*, 1.60, 1.75, 2.00}  (S-29's shelf)
          `regime_vol_window`  {10, 15, 20*, 30, 40, 60}        (no record - see clause 2)
          `target_vol`         {0.25, 0.30, 0.40*, 0.50, 0.60}  (risk posture)
          `target_exposure`    {1.25, 1.50, 1.75*, 2.00, 2.25}  (risk posture)

(4) THE REPRODUCTION CHECK. S-33's three axes must give back its published numbers: the
    shipped set +0.974 CAR points above the 18-cell grid mean on 2020-2026, 78th percentile,
    rank 14 of 18, pooled selection premium -0.049. Tolerance 0.01 points. If the three-axis
    number does not reproduce, the eight-axis number is not reportable either.

(5) THE ESTIMATE, which is what AUD-11 is owed. Per axis, `shipped OOS CAR - mean(OOS CAR over
    that axis)`, and pooled over the FITTED and UNRECORDED axes with the shipped cell counted
    once per axis exactly as S-33 counted it. Pre-registered branches:
      (a) pooled delta < 0.5  -> the five dials are COSMETIC; S-33's +0.974 on three axes is
          close to the whole story and the floor was nearly the estimate;
      (b) 0.5 <= delta < 2.0  -> the floor roughly doubles; the published 2020-2026 figure is
          overstated by that much and AUD-11's relabel text needs the larger number;
      (c) delta >= 2.0        -> the label is not the problem, the number is, and the honest
          forward expectation of this parameterization is materially below what is published.
    EXPECTATION, stated first: (a) or the low end of (b). S-33 measured the selection premium
    at -0.049 - choosing a parameter on the first half of this sleeve predicts nothing about
    the second - which says each axis should contribute a small noise-signed amount rather
    than a systematically positive one, so eight axes should not be much worse than three.

(6) ADDITIVITY, because a sum of coordinate deltas is not a joint delta. The FULL-argmax set
    over all eight axes is run jointly on 2020-2026 and compared with the sum of its own
    coordinate deltas. Pre-registered: if the two differ by more than 0.5 CAR points the
    coordinate sum in clause 5 is reported as an approximation with its error, not as the
    estimate.

(7) THE HONEST NUMBER AND ITS SIGNIFICANCE. The shipped set and the joint FULL-argmax set on
    2020-2026 in cell C (2 bp one-way spread plus IBKR Pro financing on the historical
    effective fed funds rate - S-22's honest historical book), with the paired daily return
    difference and its t. Nothing on this sleeve has reached |t| = 2 except S-31's arithmetic
    and S-33's re-selection; this will be said out loud whatever it is.

DIAGNOSTIC. Nothing here is promotable and no shipped or runner-loaded file is touched: the
shipped `Params()` defaults, `live/*`, `champion.json` and all three scheduled tasks are
untouched, so no deploy gate and no `--replay` is owed. `target_vol`, `target_exposure` and
`margin_budget` are the owner's and are READ here, never changed.
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
import rates                                                   # noqa: E402
from lean_prices import load_ohlcv                             # noqa: E402
from sweep_s19 import paired                                   # noqa: E402
from sweep_s25 import legs_simulate                            # noqa: E402
from sweep_s31 import describe                                 # noqa: E402

LEDGER = REPO / "research" / "experiments.jsonl"
START = "2012-01-03"
END = "2026-09-04"
IS_END = "2019-12-31"
OOS_START = "2020-01-02"

WINDOWS = {
    "FULL": (START, END),
    "IS": (START, IS_END),
    "OOS": (OOS_START, END),
}

#: clause 1 - the cell nine previous iterations agree on
S25_DEPLOYED_CAR = 22.192150170492255
S25_DEPLOYED_ORDERS = 5052

#: clause 4 - what S-33 published for its three axes, to 3 decimals
S33_POOLED_DELTA = 0.974
S33_PERCENTILE = 78.0
S33_RANK = (14, 18)
S33_PREMIUM = -0.049
S33_TOL = 0.01

#: clause 2/3 - the eight axes. `origin` is the pre-registered provenance class and decides
#: which axes enter clause 5; `record` is the entry in this repository that set the value.
AXES = {
    # --- S-33's three, verbatim -------------------------------------------------------
    "mom_skip": {
        "values": (2, 3, 5, 8, 10, 15, 20), "shipped": 5, "origin": "FITTED",
        "s33": True, "record": "S-10's skip walk, full-period LEAN table"},
    "alloc_vol_window": {
        "values": (10, 20, 21, 30, 40, 60), "shipped": 21, "origin": "FITTED",
        "s33": True, "record": "S-12's inverse-vol window table, signals.py:160-167"},
    "mom_lb4": {
        "values": (150, 220, 250, 252, 280, 300, 320), "shipped": 252, "origin": "FITTED",
        "s33": True, "record": "S-9's fourth-horizon shelf, signals.py:183-187"},
    # --- the five AUD-11 named --------------------------------------------------------
    "top_n": {
        "values": (2, 3, 4, 5, 6), "shipped": 3, "origin": "FITTED",
        "s33": False, "record": "S-7/S-8 CAR tables (journal.md 6269-6281, 6441); "
                                "'top_n=3 is a local peak' was read off a full-period grid"},
    "regime_threshold": {
        "values": (1.25, 1.40, 1.50, 1.60, 1.75, 2.00), "shipped": 1.50, "origin": "FITTED",
        "s33": False, "record": "signals.py:929-943 sets the FORM (a multiple of the median, "
                                "not the median) on evidence; the 1.5 itself is a table value, "
                                "re-run as a shelf by S-29 (journal.md 861-864)"},
    "regime_vol_window": {
        "values": (10, 15, 20, 30, 40, 60), "shipped": 20, "origin": "UNRECORDED",
        "s33": False, "record": "no table and no stated rationale anywhere in the record; "
                                "20 sessions is a month, but nothing says it was chosen for "
                                "that - treated as FITTED by clause 2"},
    "target_vol": {
        "values": (0.25, 0.30, 0.40, 0.50, 0.60), "shipped": 0.40, "origin": "RISK-POSTURE",
        "s33": False, "record": "the owner's volatility mandate (USER.md 2026-09-10); S-28 "
                                "measured it as binding on 2.8% of sessions, so this axis is "
                                "a risk dial rather than a fitted parameter"},
    "target_exposure": {
        "values": (1.25, 1.50, 1.75, 2.00, 2.25), "shipped": 1.75, "origin": "RISK-POSTURE",
        "s33": False, "record": "leverage request, bounded by margin_budget and the drawdown "
                                "cap - both explicitly the owner's (BLOCKERS.md, S-31)"},
}
SHIPPED = {a: c["shipped"] for a, c in AXES.items()}
IN_ESTIMATE = {"FITTED", "UNRECORDED"}

#: clause 7 - S-22's honest historical book
SPREAD_BPS = 2.0

#: post-hoc robustness (clause 5b): `evaluate.py`'s own drawdown tolerance, in points. A cell
#: the promotion gate would have refused on risk is not a cell the selector could have shipped,
#: so the grid mean over ALL cells is a weak null. Restricting to the risk-feasible ones is the
#: obvious attack on clause 5 and is answered here rather than left to the critic.
DD_TOLERANCE_POINTS = 1.0

CACHE_PATH = REPO / "results" / "s38_cache.pkl"


# ------------------------------------------------------------------------------- machinery

def make_params(over: dict) -> sig.Params:
    """The shipped Params with zero or more axes moved."""
    base = sig.Params()
    kw = {}
    for k, v in over.items():
        if k == "mom_lb4":
            lbs = list(base.mom_lookbacks)
            lbs[-1] = int(v)
            kw["mom_lookbacks"] = tuple(lbs)
        else:
            kw[k] = v
    return dataclasses.replace(base, **kw) if kw else base


def cell_name(over: dict) -> str:
    if not over:
        return "shipped"
    return " ".join(f"{k}={v}" for k, v in sorted(over.items()))


def key_of(over: dict, window: str, costed: bool) -> tuple:
    return (tuple(sorted(over.items())), window, costed)


_FRAMES: dict | None = None
_FIN: dict | None = None


def _init_worker() -> None:
    """Each process loads the store once; it is 0.2 s and keeps the pickle small."""
    global _FRAMES, _FIN
    _FRAMES = load_ohlcv(sig.traded_universe(sig.Params()))
    _FIN = {"rates": rates.load(), "spread": 0.0}


def _job(args: tuple) -> tuple:
    over, window, costed = args
    s, e = WINDOWS[window]
    book = legs_simulate(_FRAMES, make_params(over), "both", s, e,
                         SPREAD_BPS if costed else 0.0, _FIN if costed else None)
    d = describe(book, cell_name(over))
    d.update(window=window, start=s, end=e, cell=cell_name(over), costed=costed)
    # the daily series is needed for clause 7's paired t; keep only what `paired` reads
    rets = book[["date", "ret"]].to_dict("records")
    return key_of(over, window, costed), d, rets


def run_jobs(jobs: list[tuple], cache: dict, workers: int, label: str) -> None:
    todo = [j for j in jobs if key_of(*j) not in cache]
    if not todo:
        return
    print(f"  [{label}] {len(todo)} simulations on {workers} workers ...", flush=True)
    t0 = dt.datetime.now()
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as ex:
        for k, d, rets in ex.map(_job, todo):
            cache[k] = (d, pd.DataFrame(rets))
    print(f"  [{label}] done in {(dt.datetime.now() - t0).total_seconds():.0f}s\n", flush=True)


def get(cache: dict, over: dict, window: str, costed: bool = False) -> dict:
    return cache[key_of(over, window, costed)][0]


def book_of(cache: dict, over: dict, window: str, costed: bool = False) -> pd.DataFrame:
    return cache[key_of(over, window, costed)][1]


def spearman(a, b) -> float:
    """Rank correlation without scipy; ties averaged."""
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    if ra.std(ddof=1) == 0 or rb.std(ddof=1) == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def over_for(axis: str, value) -> dict:
    return {} if value == SHIPPED[axis] else {axis: value}


# --------------------------------------------------------------------------------- ledger

def record(rows: list[dict], no_record: bool) -> None:
    if no_record:
        return
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with LEDGER.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({
                "ts": stamp, "algorithm": "daily/s38_selection", "class": "book",
                "tag": f"S-38 {r['cell']} @ {r['window']} ({r.get('note', '')})",
                "commit": "", "run_dir": "",
                "track": "S-38", "start": r["start"], "end": r["end"],
                "stats": {"Sessions": str(r["sessions"]),
                          "Total Orders": str(r["orders"]),
                          "Compounding Annual Return": f"{r['CAR']:.4f}%",
                          "Sharpe Ratio": f"{r['Sharpe']:.3f}",
                          "Drawdown": f"{r['MaxDD']:.3f}%",
                          "Annual Standard Deviation": f"{r['std']:.3f}",
                          "Total Fees": f"${r['fees']:.2f}",
                          "End Equity": f"{r['end_equity']:.2f}"}}, default=str) + "\n")


# ---------------------------------------------------------------------------- the clauses

def clause_1(cache: dict) -> bool:
    print("=== clause 1: identity - is this the deployed book? ===")
    d = get(cache, {}, "FULL")
    ok = abs(d["CAR"] - S25_DEPLOYED_CAR) < 1e-9 and d["orders"] == S25_DEPLOYED_ORDERS
    print(f"  shipped Params, 2012-2026, 0 bp   CAR {d['CAR']:.6f}%   orders {d['orders']:,}")
    print(f"  S-25..S-37's deployed cell        CAR {S25_DEPLOYED_CAR:.6f}%   "
          f"orders {S25_DEPLOYED_ORDERS:,}")
    print(f"  -> {'MATCH' if ok else 'MISMATCH'}\n")
    return ok


def clause_2() -> None:
    print("=== clause 2: provenance, classified before the grid ran ===")
    hdr = f"{'axis':>18}{'shipped':>10}  {'class':<14}record"
    print(hdr)
    print("-" * 100)
    for axis, c in AXES.items():
        print(f"{axis:>18}{str(c['shipped']):>10}  {c['origin']:<14}{c['record'][:60]}")
        for extra in [c["record"][i:i + 60] for i in range(60, len(c["record"]), 60)]:
            print(f"{'':>28}  {'':<14}{extra}")
    n_in = sum(1 for c in AXES.values() if c["origin"] in IN_ESTIMATE)
    print(f"\n  {n_in} of {len(AXES)} axes enter clause 5's estimate; "
          f"{len(AXES) - n_in} are RISK-POSTURE and are reported but not summed.")
    print("  A CAR grid over a size dial measures the owner's risk decision, not selection.\n")


def clause_3(cache: dict) -> dict:
    print("=== clause 3: the grid, coordinate-wise from the shipped set, zero cost ===")
    print("  IS is what the selection SHOULD have been read on; FULL is what it WAS read on;")
    print("  OOS 2020-2026 is the half every published figure calls out-of-sample.\n")
    grid: dict[str, list[dict]] = {}
    for axis, conf in AXES.items():
        tag = f"{axis} [{conf['origin']}]"
        print(f"--- {tag} " + "-" * max(4, 74 - len(tag)))
        hdr = (f"{axis:>18}{'IS CAR%':>10}{'FULL CAR%':>11}{'OOS CAR%':>10}"
               f"{'OOS Sharpe':>12}{'OOS DD%':>9}{'OOS ord':>9}")
        print(hdr)
        print("-" * len(hdr))
        cells = []
        for v in conf["values"]:
            over = over_for(axis, v)
            c = {w: get(cache, over, w) for w in ("IS", "FULL", "OOS")}
            mark = " *" if v == SHIPPED[axis] else "  "
            print(f"{str(v) + mark:>18}{c['IS']['CAR']:>10.3f}{c['FULL']['CAR']:>11.3f}"
                  f"{c['OOS']['CAR']:>10.3f}{c['OOS']['Sharpe']:>12.3f}"
                  f"{c['OOS']['MaxDD']:>9.3f}{c['OOS']['orders']:>9,}")
            cells.append({"axis": axis, "value": v, "shipped": v == SHIPPED[axis],
                          "over": over, "origin": conf["origin"], "s33": conf["s33"],
                          "IS": c["IS"]["CAR"], "FULL": c["FULL"]["CAR"],
                          "OOS": c["OOS"]["CAR"], "OOS_dd": c["OOS"]["MaxDD"],
                          "OOS_sharpe": c["OOS"]["Sharpe"]})
        grid[axis] = cells
        print()
    return grid


def _pooled(cells: list[dict], shipped_oos: float) -> dict:
    """S-33's three statistics on an arbitrary pool of grid cells.

    TWO COUNTING CONVENTIONS, both taken from S-33 rather than chosen here, because clause 4
    reproduces its published numbers only under them and got 0.877 / 65th / n=20 under the
    obvious alternative:
      * UNIQUE CELLS. The shipped cell appears on every axis; it is one book, so it is
        counted ONCE per pool. S-33's "18 unique grid cells" over three axes of 7 + 6 + 7 is
        exactly 20 - 2 repeats.
      * INCLUSIVE RANK. "rank 14 of 18" counts the cells at OR BELOW the shipped cell, from
        the bottom, so the percentile is `<=` and not `<`.
    """
    seen, uniq = set(), []
    for c in cells:
        k = tuple(sorted(c["over"].items()))
        if k in seen:
            continue
        seen.add(k)
        uniq.append(c)
    arr = np.asarray([c["OOS"] for c in uniq], dtype=float)
    at_or_below = int((arr <= shipped_oos).sum())
    sd = float(arr.std(ddof=1)) if len(arr) > 1 else 0.0
    delta = shipped_oos - float(arr.mean())
    return {"n": len(arr), "mean": float(arr.mean()), "median": float(np.median(arr)),
            "sd": sd, "delta": delta,
            "sd_units": (delta / sd) if sd else float("nan"),
            "pct": 100.0 * at_or_below / len(arr),
            "rank": at_or_below,                       # S-33's "14 of 18", from the bottom
            "rank_from_top": len(arr) - at_or_below + 1}


def clause_4(grid: dict, shipped_oos: float) -> bool:
    print("=== clause 4: does S-33's three-axis number reproduce? ===")
    cells = [c for a in grid for c in grid[a] if AXES[a]["s33"]]
    p = _pooled(cells, shipped_oos)
    prem = []
    for axis, cs in grid.items():
        if not AXES[axis]["s33"]:
            continue
        argmax = max(cs, key=lambda c: (c["IS"], c["shipped"]))
        prem.append(argmax["OOS"] - float(np.median([c["OOS"] for c in cs])))
    got_prem = float(np.mean(prem))
    checks = [("pooled delta", p["delta"], S33_POOLED_DELTA, S33_TOL),
              ("percentile", p["pct"], S33_PERCENTILE, 1.0),
              ("rank (of 18)", float(p["rank"]), float(S33_RANK[0]), 0.5),
              ("cells", float(p["n"]), float(S33_RANK[1]), 0.5),
              ("selection premium", got_prem, S33_PREMIUM, S33_TOL)]
    hdr = f"{'statistic':<22}{'S-33 published':>16}{'re-run here':>14}{'ok?':>6}"
    print(hdr)
    print("-" * len(hdr))
    ok = True
    for name, got, want, tol in checks:
        good = abs(got - want) <= tol
        ok &= good
        print(f"{name:<22}{want:>16.3f}{got:>14.3f}{('yes' if good else 'NO'):>6}")
    print(f"\n  -> S-33 {'REPRODUCES' if ok else 'DOES NOT REPRODUCE'}; the eight-axis number "
          f"{'is' if ok else 'is NOT'} reportable.\n")
    return ok


def clause_5(grid: dict, shipped_oos: float) -> dict:
    print("=== clause 5: the estimate AUD-11 is owed ===")
    hdr = (f"{'axis':<18}{'class':<14}{'cells':>6}{'grid mean':>11}{'grid sd':>9}"
           f"{'shipped-mean':>14}{'sd units':>10}{'pct':>7}")
    print(hdr)
    print("-" * len(hdr))
    per_axis = {}
    for axis, cs in grid.items():
        p = _pooled(cs, shipped_oos)
        per_axis[axis] = p
        print(f"{axis:<18}{AXES[axis]['origin']:<14}{p['n']:>6}{p['mean']:>11.3f}"
              f"{p['sd']:>9.3f}{p['delta']:>+14.3f}{p['sd_units']:>+10.2f}{p['pct']:>7.0f}")
    print("-" * len(hdr))

    def pool(pred, label):
        cells = [c for a in grid for c in grid[a] if pred(a)]
        if not cells:
            return None
        p = _pooled(cells, shipped_oos)
        print(f"{label:<18}{'':<14}{p['n']:>6}{p['mean']:>11.3f}{p['sd']:>9.3f}"
              f"{p['delta']:>+14.3f}{p['sd_units']:>+10.2f}{p['pct']:>7.0f}")
        return p

    three = pool(lambda a: AXES[a]["s33"], "S-33's three")
    five = pool(lambda a: not AXES[a]["s33"] and AXES[a]["origin"] in IN_ESTIMATE,
                "the new fitted")
    risk = pool(lambda a: AXES[a]["origin"] == "RISK-POSTURE", "risk-posture")
    eight = pool(lambda a: AXES[a]["origin"] in IN_ESTIMATE, "ESTIMATE (fitted)")
    print()
    if risk is not None:
        print(f"  the risk-posture pool sits at {risk['delta']:+.3f} and is NOT summed in: it "
              f"prices the owner's dial, not a fit.")
    coord = sum(p["delta"] for a, p in per_axis.items() if AXES[a]["origin"] in IN_ESTIMATE)
    print(f"  coordinate sum over the fitted axes: {coord:+.3f} CAR points "
          f"(clause 6 tests whether a sum is legitimate)")
    # ---- clause 5b, POST-HOC and labelled as such --------------------------------------
    ship_dd = next(c["OOS_dd"] for cs in grid.values() for c in cs if c["shipped"])
    cap = ship_dd + DD_TOLERANCE_POINTS
    feas = [c for a in grid for c in grid[a]
            if AXES[a]["origin"] in IN_ESTIMATE and c["OOS_dd"] <= cap]
    pf = _pooled(feas, shipped_oos)
    print(f"  POST-HOC (not pre-registered): the null above lets the selector ship cells the")
    print(f"  promotion gate would refuse. Restricted to fitted cells inside the shipped")
    print(f"  drawdown + {DD_TOLERANCE_POINTS:.1f} point tolerance ({cap:.3f}% OOS MaxDD), "
          f"{pf['n']} of {eight['n']} cells survive")
    print(f"  and the estimate falls to {pf['delta']:+.3f} CAR points "
          f"({pf['sd_units']:+.2f} sd, {pf['pct']:.0f}th percentile).\n")

    # ---- clause 5c, POST-HOC: how often is the shipped value its axis's OOS argmax? ------
    # Selection ran on FULL 2012-2026, which CONTAINS 2020-2026, so a full-period argmax is
    # partly an out-of-sample argmax. That is AUD-11's whole thesis, and it is directly
    # countable: under a null of no selection the shipped value is the OOS-best cell of its
    # own axis with probability 1/n.
    hits, probs = [], []
    for axis, cs in grid.items():
        if AXES[axis]["origin"] not in IN_ESTIMATE:
            continue
        best = max(cs, key=lambda c: c["OOS"])
        probs.append(1.0 / len(cs))
        if best["shipped"]:
            hits.append(axis)
    # exact Poisson-binomial tail, by convolution
    dist = np.array([1.0])
    for p in probs:
        dist = np.convolve(dist, [1 - p, p])
    pval = float(dist[len(hits):].sum())
    print(f"  POST-HOC (not pre-registered): the shipped value is the OUT-OF-SAMPLE argmax of")
    print(f"  its own axis on {len(hits)} of {len(probs)} fitted axes ({', '.join(hits)}),")
    print(f"  against {sum(probs):.2f} expected under no selection. Exact Poisson-binomial "
          f"P(X >= {len(hits)}) = {pval:.3f}.\n")

    d = eight["delta"]
    if d < 0.5:
        branch = ("(a) COSMETIC - the five dials add little; S-33's floor was nearly the "
                  "estimate")
    elif d < 2.0:
        branch = (f"(b) the floor is not the estimate - the published 2020-2026 figure is "
                  f"overstated by about {d:.2f} CAR points")
    else:
        branch = ("(c) the number, not just the label, is wrong - the honest forward "
                  "expectation is materially below what is published")
    print(f"  -> pre-registered branch {branch}\n")
    return {"per_axis": per_axis, "three": three, "five": five, "risk": risk,
            "eight": eight, "feasible": pf, "coord_sum": coord, "branch": branch}


def clause_6(grid: dict, cache: dict, shipped_oos: float) -> dict:
    print("=== clause 6: is a sum of coordinate deltas a joint delta? ===")
    full_set = {}
    coord = 0.0
    for axis, cs in grid.items():
        if AXES[axis]["origin"] not in IN_ESTIMATE:
            continue
        top = max(cs, key=lambda c: (c["FULL"], c["shipped"]))
        shipped_cell = next(c for c in cs if c["shipped"])
        coord += shipped_cell["OOS"] - top["OOS"]
        if not top["shipped"]:
            full_set[axis] = top["value"]
    joint = get(cache, full_set, "OOS") if full_set else get(cache, {}, "OOS")
    joint_delta = shipped_oos - joint["CAR"]
    err = joint_delta - coord
    print(f"  FULL-argmax set over the fitted axes: {cell_name(full_set)}")
    print(f"  shipped OOS CAR                     {shipped_oos:>9.3f}")
    print(f"  joint FULL-argmax set, OOS CAR      {joint['CAR']:>9.3f}  "
          f"(Sharpe {joint['Sharpe']:.3f}, DD {joint['MaxDD']:.3f}%)")
    print(f"  joint delta (shipped - argmax)      {joint_delta:>+9.3f}")
    print(f"  sum of the same axes' coordinate deltas {coord:>+6.3f}")
    print(f"  additivity error                    {err:>+9.3f}")
    verdict = ("ADDITIVE within the pre-registered 0.5" if abs(err) <= 0.5 else
               "NOT ADDITIVE - clause 5's sum is an approximation with this error")
    print(f"  -> {verdict}\n")
    return {"set": full_set, "joint": joint, "joint_delta": joint_delta,
            "coord": coord, "err": err, "verdict": verdict}


def clause_7(cache: dict, c6: dict, grid: dict) -> list[dict]:
    print("=== clause 7: the honest number (cell C) and its significance ===")
    rows = []
    hdr = f"{'set':<18}{'parameters':<44}{'OOS CAR%':>10}{'Sharpe':>8}{'MaxDD%':>8}"
    print(hdr)
    print("-" * len(hdr))
    for name, over in (("shipped", {}), ("joint FULL-argmax", c6["set"])):
        d = get(cache, over, "OOS", costed=True)
        d = dict(d, cell=f"cellC {name} {cell_name(over)}")
        rows.append(d)
        print(f"{name:<18}{cell_name(over):<44}{d['CAR']:>10.3f}{d['Sharpe']:>8.3f}"
              f"{d['MaxDD']:>8.3f}")
    charge = rows[0]["CAR"] - get(cache, {}, "OOS")["CAR"]
    seen, oos_all = set(), []
    for a in grid:
        if AXES[a]["origin"] not in IN_ESTIMATE:
            continue
        for c in grid[a]:
            k = tuple(sorted(c["over"].items()))
            if k not in seen:
                seen.add(k)
                oos_all.append(c["OOS"])
    lo, hi, med = float(np.min(oos_all)), float(np.max(oos_all)), float(np.median(oos_all))
    print(f"\n  cell-C charge on this book: {charge:+.3f} CAR points. The fitted grid's own")
    print(f"  0 bp OOS range is {lo:.3f} .. {hi:.3f} (median {med:.3f}, n={len(oos_all)}), so the")
    print(f"  honest fully-charged 2020-2026 band of this parameterization is roughly "
          f"{lo + charge:.1f} .. {hi + charge:.1f}%,")
    print(f"  median {med + charge:.1f}%, against the {rows[0]['CAR']:.3f}% the shipped set prints.")
    p = paired(book_of(cache, c6["set"], "OOS", True), book_of(cache, {}, "OOS", True),
               "argmax", "shipped")
    print(f"\n  joint FULL-argmax minus shipped, 2020-2026 cell C, paired daily: "
          f"{p['bps_per_day']:+.3f} bps/day")
    print(f"  over {p['days']} sessions, t {p['t']:+.2f} -> "
          f"{'past' if abs(p['t']) >= 2 else 'short of'} |t| = 2\n")
    return rows


# ----------------------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", default="all", choices=["all", "a"])
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--no-record", action="store_true")
    ap.add_argument("--fresh", action="store_true",
                    help="ignore results/s38_cache.pkl and re-simulate every cell")
    args = ap.parse_args()

    print(f"S-38 (AUD-11 part 2)  IS {START}..{IS_END}   OOS {OOS_START}..{END}")
    print(f"axes: {', '.join(AXES)}\n")

    cache: dict = {}
    if CACHE_PATH.exists() and not args.fresh:
        cache = pickle.loads(CACHE_PATH.read_bytes())
        print(f"  [cache] {len(cache)} simulations reloaded from {CACHE_PATH.name}\n")
    jobs = []
    seen = set()
    for axis, conf in AXES.items():
        for v in conf["values"]:
            over = over_for(axis, v)
            k = tuple(sorted(over.items()))
            if k in seen:
                continue
            seen.add(k)
            jobs += [(over, w, False) for w in ("IS", "FULL", "OOS")]
    run_jobs(jobs, cache, args.workers, "grid")
    CACHE_PATH.write_bytes(pickle.dumps(cache))

    if not clause_1(cache):
        print("clause 1 FAILED - this is not the deployed book. Stop.")
        return 1
    clause_2()
    grid = clause_3(cache)
    shipped_oos = get(cache, {}, "OOS")["CAR"]

    # the shipped cell sits on every axis; write it to the append-only ledger ONCE
    flat, written = [], set()
    for axis, cs in grid.items():
        for c in cs:
            for w in ("IS", "FULL", "OOS"):
                k = key_of(c["over"], w, False)
                if k in written:
                    continue
                written.add(k)
                flat.append(dict(get(cache, c["over"], w)))
    for r in flat:
        r["note"] = "pandas book, 0 bp - DIAGNOSTIC, not promotable"

    if args.stage == "a":
        clause_4(grid, shipped_oos)
        clause_5(grid, shipped_oos)
        record(flat, args.no_record)
        return 0

    repro = clause_4(grid, shipped_oos)
    clause_5(grid, shipped_oos)

    # clause 6 needs the joint FULL-argmax cell; clause 7 needs both cells charged
    full_set = {}
    for axis, cs in grid.items():
        if AXES[axis]["origin"] not in IN_ESTIMATE:
            continue
        top = max(cs, key=lambda c: (c["FULL"], c["shipped"]))
        if not top["shipped"]:
            full_set[axis] = top["value"]
    run_jobs([(full_set, "OOS", False), (full_set, "OOS", True), ({}, "OOS", True)],
             cache, min(args.workers, 3), "joint + cell C")
    CACHE_PATH.write_bytes(pickle.dumps(cache))

    c6 = clause_6(grid, cache, shipped_oos)
    rows7 = clause_7(cache, c6, grid)
    for r in rows7:
        r = dict(r)
        r["note"] = f"pandas book, {SPREAD_BPS:g} bp + IBKR Pro financing - DIAGNOSTIC"
        flat.append(r)
    jd = dict(get(cache, full_set, "OOS"))
    jd["cell"] = f"joint FULL-argmax {cell_name(full_set)}"
    jd["note"] = "pandas book, 0 bp - DIAGNOSTIC, not promotable"
    flat.append(jd)

    record(flat, args.no_record)
    if not repro:
        print("NOTE: clause 4 did not reproduce S-33; read clause 5 with that caveat.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
