#!/usr/bin/env python
"""S-41: ensemble the crisis switch instead of choosing it.

    python scripts/sweep_s41.py --workers 10      # the whole thing, ~6 min
    python scripts/sweep_s41.py --no-record       # do not append to the ledger

WHY THIS ITEM. S-40 proved that no real-time selector can find the shipped
`regime_threshold=1.50 / regime_vol_window=20` cell: a walk-forward argmax over the same 36
cells picks it in 0 of 11 years under either a CAR or a Sharpe objective, lands 1.389 (CAR
objective) / 1.688 (Sharpe objective) CAR points BELOW the grid mean, and carries the worst
drawdown of any book S-40 tested (38.185%). The shipped cell's distance above the grid mean
is hindsight in full. Yet S-40's last row was the one that needed no selection at all - the
equal-weight mean of all 36 cells - and it carried the best Sharpe (1.173) and the lowest
drawdown (23.389%) of every book in the table, beating even the hindsight-shipped cell on
FULL (23.389 vs 23.860) and OOS (23.407 vs 23.855).

That row is an upper bound, not a book. S-40 averaged the 36 cells' RETURNS, which is 36
separate accounts each paying its own commission and each rebalancing to its own targets.
The implementable object is the average of their target WEIGHTS - one account, one order
list, netting across the 36 opinions before anything trades. Averaging weights is not
averaging returns, and the difference is not a rounding error in either direction:

  - it can only HELP costs: 36 cells that disagree about one name net to a smaller trade
    than 36 accounts that each trade it, so the weight-blend's turnover is bounded above by
    the return-blend's and is strictly below it whenever the cells disagree;
  - it can HURT the risk-off boundary: the return-blend gets a clean k/36 of the crisis
    exposure because each account really is flat; the weight-blend has to HOLD a fractional
    position, which must clear the 0.01x no-trade band to exist at all, and below it the
    book silently rounds the ensemble's opinion to zero.

Both effects are measured here rather than argued. The prize is explicitly NOT return - S-40
put the blend ~0.42 bps/day behind the shipped cell on FULL at t -0.98, and the sign of that
gap flips by window - it is that the sleeve's single most fragile decision stops having to be
made at all.

PRE-REGISTERED before the first simulation, seven clauses
--------------------------------------------------------
(1a) IDENTITY. At the shipped `Params()` this harness reproduces the deployed cell to the
     digit: CAR 22.192150170492255%, 5,052 orders, 2012-2026 at zero cost - the figure S-25
     through S-40 each quote independently. If it misses, nothing below may be read.
(1b) WEIGHT-PATH IDENTITY, and this one is the licence for the whole item. The shipped
     cell's target weights are extracted day by day and fed BACK through the same simulator
     via `legs_simulate(weights_fn=...)`. The resulting book must match (1a) to the digit on
     CAR *and* on order count. That is what proves the extraction is the same object the
     in-loop call produces - same slice, same state chain, same sizing at close[i-1] - so a
     blend built out of 36 such extractions is executed through exactly the deployed
     rebalance and not through a second, friendlier one. If 1b misses, nothing below may be
     read.
(2) PURITY, inherited from S-40 clause 2b and re-asserted, not assumed: `dd_halve > 1.0 and
    dd_flat > 1.0`, so `drawdown_multiplier`'s `dd = 1 - last/peak` (bounded by 1.0) can
    never reach either threshold and the overlay returns 1.0 on every session. Target weights
    are then a pure function of (prices, params) and a cell's weight path does not depend on
    the equity curve of the book that executes it - which is what makes a 36-cell blend
    well-defined at all. Arithmetic, not a simulation.
(3) THE BLEND. `w_blend[t] = mean over the 36 cells of w_cell[t]`, each cell's path carrying
    its own hysteresis state (S-11's `held`/`held_age`), executed in the deployed `mode=both`
    convention on IS 2012-2019 / FULL 2012-2026 / OOS 2020-2026, zero cost, against: the
    shipped cell, the `off` cell, and - where S-40's cache is present - S-40's own
    RETURN-average, which is the upper bound this book is trying to approach.
(4) EXECUTABILITY, which is the question that decides whether this is a book or a table.
    Reported: names held per session, the fractional risk-off boundary (sessions where
    1..35 of the 36 cells are risk-off, i.e. where the blend holds a partial book no single
    cell would hold), the share of blended target weight that falls below the 0.01x no-trade
    band and is therefore rounded to nothing, and the realized gross against the target
    gross. Pre-registered bar: if more than 10% of target weight is lost to the band at
    $100k, the blend is not executable at the deployed size and that is the finding.
(4b) ROBUSTNESS AGAINST THE OBVIOUS ATTACK. The 36-cell grid was pre-registered by S-40, but
     the shipped cell is inside it, so a critic may say the blend inherits the shipped cell's
     hindsight. The blend is therefore re-run over the 35 cells with the shipped cell
     REMOVED. If the two are within 0.05 Sharpe the result is a property of the ensemble;
     if removing one cell of 36 moves it materially, the blend is the shipped cell in a
     costume and must be reported as such.
(5) COST. Every headline book re-run in S-22's honest historical cell C (2 bp one-way spread
    plus IBKR Pro financing on the historical effective fed funds rate) on FULL and OOS, with
    the paired daily return difference against the shipped cell and its t.
(6) TURNOVER, which is where weight-blending is supposed to win: orders/yr, turnover/yr and
    fees for the blend against the shipped cell, and against 36x the mean single cell, which
    is what the return-average would actually have paid.
(7) THE DECISION, pre-registered so it cannot be moved afterwards. The blend is a PROMOTION
    CANDIDATE only if, fully charged, on BOTH FULL and OOS: Sharpe >= shipped, MaxDD <=
    shipped, CAR >= shipped - 1.0 points, and clause 4's band test passes. Anything else is
    reported and filed, never shipped from here. EXPECTATION, stated first: the Sharpe and
    drawdown conditions pass (S-40's return-average cleared them with room) and the CAR
    condition is the one at risk, because weight-blending gives up the return-average's free
    diversification across 36 independent rebalances. Note for whoever reads this later: even
    a clean pass is NOT a promotion, because no single `Params()` can express a 36-cell blend
    - shipping it needs a signal-level change to `algorithms/s1_momo/signals.py` and its own
    LEAN run through `scripts/backtest.py`, which is a separate item.

DIAGNOSTIC. No shipped or runner-loaded file is touched: the shipped `Params()` defaults,
`live/*`, `champion.json` and all scheduled tasks are untouched, so no deploy gate and no
`--replay` is owed. `target_vol`, `target_exposure`, `margin_budget` and the drawdown cap are
the owner's and are READ here, never changed. The one shared-code change is the default-inert
`weights_fn` argument on the RESEARCH harness `sweep_s25.legs_simulate` (S-26/S-28/S-30/S-32
precedent); clause 1a re-proves every earlier row is bit-identical.
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
from sweep_s19 import MIN_ORDER_VALUE, START_EQUITY, paired, tstat   # noqa: E402
from sweep_s25 import legs_simulate                            # noqa: E402
from sweep_s31 import describe                                 # noqa: E402
from sweep_s40 import (OFF_THRESHOLD, S25_DEPLOYED_CAR, S25_DEPLOYED_ORDERS,  # noqa: E402
                       SHIPPED_CELL, SPREAD_BPS, THRESHOLDS, VOL_WINDOWS, WINDOWS)

LEDGER = REPO / "research" / "experiments.jsonl"
CACHE_PATH = REPO / "results" / "s41_cache.pkl"
S40_CACHE = REPO / "results" / "s40_cache.pkl"
OUT_PATH = REPO / "results" / "s41_full.txt"

#: clause 4 - the pre-registered executability bar
BAND_LOSS_BAR = 10.0
#: clause 4b - the pre-registered robustness bar
SHARPE_TIE = 0.05
#: clause 7 - the pre-registered promotion-candidate bars
CAR_GIVEAWAY = 1.0


def grid_cells() -> list[dict]:
    return [{"regime_threshold": t, "regime_vol_window": w}
            for t in THRESHOLDS for w in VOL_WINDOWS]


def make_params(over: dict) -> sig.Params:
    return dataclasses.replace(sig.Params(), **over) if over else sig.Params()


def cell_name(over: dict) -> str:
    if not over:
        return "shipped"
    if over.get("regime_threshold") == OFF_THRESHOLD:
        return "off (switch never fires)"
    return f"thr={over['regime_threshold']:.2f} win={over['regime_vol_window']}"


def is_shipped(over: dict) -> bool:
    return (over.get("regime_threshold"), over.get("regime_vol_window")) == SHIPPED_CELL


# ------------------------------------------------------------------- clause 3: weight paths

_FRAMES: dict | None = None
_FIN: dict | None = None


def _init_worker() -> None:
    global _FRAMES, _FIN
    _FRAMES = load_ohlcv(sig.traded_universe(sig.Params()))
    _FIN = {"rates": rates.load(), "spread": 0.0}


def _bounds(index: pd.Index, params, start: str, end: str) -> tuple[int, int]:
    """`legs_simulate`'s own loop bounds at `lag=0`, so a path lines up session for session."""
    i0 = max(index.searchsorted(pd.Timestamp(start)) + 1, params.history_bars)
    i1 = min(index.searchsorted(pd.Timestamp(end), side="right"), len(index))
    return i0, i1


def _path_job(args: tuple) -> tuple:
    """One cell's target-weight path over one window, on exactly `legs_simulate`'s sessions.

    The equity curve handed to `target_weights` is flat rather than the executing book's.
    Clause 2 licenses that (the overlay returns 1.0 on every session, so the curve cannot
    reach the weights) and clause 1b PROVES it end to end for the shipped cell, which is the
    only cell whose in-loop book exists to compare against.
    """
    over, window = args
    params = make_params(over)
    start, end = WINDOWS[window]
    closes = _FRAMES["close"]
    i0, i1 = _bounds(closes.index, params, start, end)
    state: dict = {}
    curve = [float(START_EQUITY)]
    path: dict = {}
    off_days = 0
    for i in range(i0, i1):
        lo = max(0, i - params.history_bars)
        targets, diag = sig.target_weights(closes.iloc[lo:i], curve, params, state)
        state = diag.get("state", {})
        curve.append(float(START_EQUITY))
        path[closes.index[i]] = {t: float(v) for t, v in targets.items() if v}
        off_days += int(diag.get("reason") == "risk-off")
    return (tuple(sorted(over.items())), window), path, off_days


def _sim_job(args: tuple) -> tuple:
    """One book. `path` None runs the shipped signal in-loop; otherwise it is executed."""
    key, over, window, costed, path = args
    start, end = WINDOWS[window]
    fn = None if path is None else (lambda d, _p=path: _p.get(d, {}))
    book = legs_simulate(_FRAMES, make_params(over), "both", start, end,
                         SPREAD_BPS if costed else 0.0, _FIN if costed else None,
                         weights_fn=fn)
    d = describe(book, key[0])
    d.update(window=window, start=start, end=end, cell=key[0], costed=costed)
    keep = [c for c in ("date", "ret", "gross_x", "orders", "turnover", "prev") if c in book]
    return key + (window, costed), d, book[keep].to_dict("records")


def run_pool(jobs: list, fn, cache: dict, workers: int, label: str, key_of) -> None:
    todo = [j for j in jobs if key_of(j) not in cache]
    if not todo:
        return
    print(f"  [{label}] {len(todo)} jobs on {workers} workers ...", flush=True)
    t0 = dt.datetime.now()
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as ex:
        for out in ex.map(fn, todo):
            cache[out[0]] = out[1:]
    print(f"  [{label}] done in {(dt.datetime.now() - t0).total_seconds():.0f}s\n", flush=True)


# ------------------------------------------------------------------------------- the blend

def blend(paths: dict, cells: list[dict], window: str) -> dict:
    """Equal-weight mean of the cells' target weights, session by session.

    A cell that is risk-off contributes an empty dict, i.e. zero to every name - which is
    exactly the fractional boundary clause 4 counts. The denominator is the number of CELLS,
    never the number of cells with an opinion, or a unanimous risk-off day would be
    indistinguishable from a day nobody held anything.
    """
    n = float(len(cells))
    keys = [(tuple(sorted(c.items())), window) for c in cells]
    dates = paths[keys[0]][0].keys()
    out: dict = {}
    for d in dates:
        agg: dict = {}
        for k in keys:
            for t, v in paths[k][0].get(d, {}).items():
                agg[t] = agg.get(t, 0.0) + v
        out[d] = {t: v / n for t, v in agg.items() if v}
    return out


def disagreement(paths: dict, cells: list[dict], window: str) -> dict:
    """Clause 4: how many of the cells are flat on each session, and how many names the
    blend ends up holding."""
    keys = [(tuple(sorted(c.items())), window) for c in cells]
    dates = sorted(paths[keys[0]][0].keys())
    flat, names = [], []
    for d in dates:
        f = sum(1 for k in keys if not paths[k][0].get(d))
        held = set()
        for k in keys:
            held |= set(paths[k][0].get(d, {}))
        flat.append(f)
        names.append(len(held))
    return {"dates": dates, "flat": np.array(flat), "names": np.array(names)}


def band_loss(bl: dict, equity: float) -> dict:
    """Clause 4: the share of blended target weight that cannot clear the no-trade band.

    An honest upper bound on the damage, and deliberately the PESSIMISTIC reading: it treats
    every target below the band as unreachable from flat, which is what it is on the first
    session a name appears. Once a position exists the band applies to the DELTA, so an
    established holding below the band survives; the simulation books that correctly and this
    column exists only to say how much of the ensemble's opinion is at risk of never starting.
    """
    tot = lost = 0.0
    days_any = 0
    for d, w in bl.items():
        small = sum(abs(v) for v in w.values() if abs(v) < MIN_ORDER_VALUE)
        tot += sum(abs(v) for v in w.values())
        lost += small
        days_any += int(small > 0)
    return {"pct_weight_lost": 100.0 * lost / tot if tot else float("nan"),
            "days_any_small": 100.0 * days_any / max(len(bl), 1),
            "equity": equity}


# ----------------------------------------------------------------------------- the clauses

def row(d: dict, extra: str = "") -> str:
    return (f"{d['cell']:<30}{d['sessions']:>6}{d['CAR']:>9.3f}{d['Sharpe']:>8.3f}"
            f"{d['MaxDD']:>8.3f}{d['std']:>7.3f}{d['orders']:>8,}{d['fees']:>10,.0f}"
            f"{d['gross_x']:>7.2f}{d['turnover_x']:>9.1f}{extra}")


HDR = (f"{'book':<30}{'sess':>6}{'CAR%':>9}{'Sharpe':>8}{'MaxDD%':>8}{'std':>7}"
       f"{'orders':>8}{'fees':>10}{'gross':>7}{'turn/yr':>9}")


def h(title: str) -> None:
    print(f"\n{'=' * 100}\n{title}\n{'=' * 100}")


def clause_1(cache: dict) -> bool:
    h("CLAUSE 1 - identity, and the licence for everything below")
    dep = cache[("shipped", "FULL", False)][0]
    fed = cache[("shipped (fed its own weights)", "FULL", False)][0]
    ok = True
    for label, d, want_car, want_ord in (
            ("1a in-loop      ", dep, S25_DEPLOYED_CAR, S25_DEPLOYED_ORDERS),
            ("1b weights fed back", fed, S25_DEPLOYED_CAR, S25_DEPLOYED_ORDERS)):
        dc, do = abs(d["CAR"] - want_car), d["orders"] - want_ord
        good = dc < 1e-9 and do == 0
        ok &= good
        print(f"  {label}  CAR {d['CAR']:.12f}%  orders {d['orders']:,}   "
              f"delta {dc:.2e} / {do:+d}   {'OK' if good else 'MISMATCH'}")
    print("\n  1b is the one that matters: the extraction reproduces the in-loop book to the\n"
          "  digit, so a blend of 36 extractions is executed through the deployed rebalance.")
    return ok


def clause_2() -> bool:
    h("CLAUSE 2 - purity (arithmetic, not a simulation)")
    p = sig.Params()
    ok = p.dd_halve > 1.0 and p.dd_flat > 1.0
    print(f"  dd_halve {p.dd_halve}  dd_flat {p.dd_flat}   dd = 1 - last/peak <= 1.0")
    print(f"  overlay is constant 1.0 on every session -> weights are f(prices, params): "
          f"{'OK' if ok else 'VIOLATED'}")
    return ok


def clause_3(cache: dict, s40: dict | None) -> dict:
    h("CLAUSE 3 - the weight blend against the cell that was chosen, zero cost")
    print(HDR)
    print("-" * len(HDR))
    out = {}
    for window in ("FULL", "IS", "OOS"):
        for name in ("shipped", "off (switch never fires)", "blend36", "blend35 (no shipped)"):
            k = (name, window, False)
            if k in cache:
                d = cache[k][0]
                out[(name, window)] = d
                print(row(d))
        if s40 is not None:
            d = s40.get(window)
            if d:
                out[("S-40 return-average", window)] = d
                print(f"  {d['cell']:<28}{d['sessions']:>6}{d['CAR']:>9.3f}{d['Sharpe']:>8.3f}"
                      f"{d['MaxDD']:>8.3f}{d['std']:>7.3f}{'n/a':>8}{'n/a':>10}"
                      f"{'n/a':>7}{'n/a':>9}   (upper bound, 36 accounts)")
        print("-" * len(HDR))
    return out


#: S-40 clause 4's walk-forward span - the span its headline blend row is actually measured on
WF_SPAN_START = "2016-01-01"


def clause_3b(cache: dict) -> None:
    """The correction S-41's own premise needed.

    S-41 was opened on the sentence "the equal-weight blend carried the best Sharpe (1.173)
    and the lowest drawdown (23.389%) of every book in S-40's table, beating even the
    hindsight-shipped cell's drawdown on FULL (23.389 vs 23.860)". Those two numbers are not
    from the same row as the cells they are compared against: S-40's blend row is
    `grid equal-weight (same span)`, 2,684 sessions, i.e. the 2016-2026 WALK-FORWARD span,
    while `shipped` at 23.860 is 3,689 sessions of FULL. The drawdown survives the mix-up by
    luck - the blend's worst drawdown is the 2020 crash, which lies inside both spans, so
    23.389 is the same number either way - but the Sharpe does not, and 1.173 was never
    comparable to a FULL-span 1.159. This clause puts every book on S-40's own span.
    """
    h("CLAUSE 3b - S-40's headline blend row, on the span it was actually measured on")
    cut = pd.Timestamp(WF_SPAN_START)
    print(HDR)
    print("-" * len(HDR))
    for costed in (False, True):
        for name in ("shipped", "off (switch never fires)", "blend36"):
            k = (name, "FULL", costed)
            if k not in cache:
                continue
            b = cache[k][1]
            d = summarize_span(b[b["date"] >= cut], f"{name} [{'cost' if costed else 'zero'}]")
            print(f"{d['cell']:<30}{d['sessions']:>6}{d['CAR']:>9.3f}{d['Sharpe']:>8.3f}"
                  f"{d['MaxDD']:>8.3f}{d['std']:>7.3f}")
        print("-" * len(HDR))
    print("  S-40 printed 2,684 sessions / CAR 22.916 / Sharpe 1.173 / MaxDD 23.389 for the\n"
          "  RETURN-average on this span; the row above is the implementable WEIGHT-blend on\n"
          "  the same sessions. The comparison the item was opened on - 1.173 against a\n"
          "  FULL-span 1.159 - compares two different spans and is withdrawn here.")


def summarize_span(book: pd.DataFrame, label: str) -> dict:
    ret = book["ret"].to_numpy()
    curve = np.cumprod(1 + ret)
    sd = ret.std(ddof=1)
    return {"cell": label, "sessions": len(ret),
            "CAR": 100 * (curve[-1] ** (252.0 / len(ret)) - 1),
            "Sharpe": ret.mean() / sd * np.sqrt(252),
            "MaxDD": 100 * float((1 - curve / np.maximum.accumulate(curve)).max()),
            "std": sd * np.sqrt(252)}


def composition(paths: dict, cells: list[dict], bl: dict, window: str) -> dict:
    """Clause 4: does the blend disagree with the shipped cell about WHICH names, or only
    about HOW MUCH? The book holds three names, so this decides what the ensemble is doing."""
    k = (tuple(sorted(next(c for c in cells if is_shipped(c)).items())), window)
    ship = paths[k][0]
    same = diff = ship_on_blend_off = 0
    for d, w in bl.items():
        sw = ship.get(d, {})
        if not sw and not w:
            continue
        if set(sw) == set(w):
            same += 1
        elif sw and not w:
            ship_on_blend_off += 1
        else:
            diff += 1
    tot = max(same + diff + ship_on_blend_off, 1)
    return {"same_names": 100.0 * same / tot, "diff_names": 100.0 * diff / tot,
            "ship_only": 100.0 * ship_on_blend_off / tot, "n": tot}


def clause_4(bl: dict, dis: dict, window: str, comp: dict | None = None) -> dict:
    h(f"CLAUSE 4 - is it executable? ({window})")
    flat, names = dis["flat"], dis["names"]
    n = len(flat)
    print(f"  sessions {n:,}")
    print(f"  all 36 cells risk-off (a unanimous crisis)        "
          f"{100.0 * (flat == 36).mean():>7.2f}% of sessions")
    print(f"  all 36 cells risk-ON  (nobody disagrees)          "
          f"{100.0 * (flat == 0).mean():>7.2f}%")
    print(f"  FRACTIONAL boundary, 1..35 cells flat             "
          f"{100.0 * ((flat > 0) & (flat < 36)).mean():>7.2f}%   "
          f"<- where the blend holds a book no cell holds")
    print(f"  names in the blended target: mean {names.mean():.2f}  "
          f"median {np.median(names):.0f}  max {names.max()}")
    if comp:
        print(f"\n  against the shipped cell, on sessions where either holds something "
              f"(n {comp['n']:,}):")
        print(f"    identical name set, differing only in size   {comp['same_names']:>7.2f}%")
        print(f"    a different name set                         {comp['diff_names']:>7.2f}%")
        print(f"    shipped holds, the blend is flat             {comp['ship_only']:>7.2f}%")
        print("    -> the ensemble is a vote on GROSS, not on which names to own.")
    for eq in (START_EQUITY, 1_000_000.0):
        b = band_loss(bl, eq)
        print(f"\n  no-trade band {MIN_ORDER_VALUE:.3f}x equity, at ${eq:,.0f}")
        print(f"    share of blended target weight below the band   "
              f"{b['pct_weight_lost']:>7.3f}%  (bar {BAND_LOSS_BAR}%)")
        print(f"    sessions with at least one sub-band target      "
              f"{b['days_any_small']:>7.2f}%")
    b = band_loss(bl, START_EQUITY)
    ok = b["pct_weight_lost"] <= BAND_LOSS_BAR
    print(f"\n  clause 4 band test: {'PASS' if ok else 'FAIL'}")
    print("  Note the band is a fraction of equity, so it does not soften with account size;\n"
          "  the two rows above differ only in the dollars, never in the verdict.")
    return {"ok": ok, **b}


def clause_4b(c3: dict) -> bool:
    h("CLAUSE 4b - does the blend survive deleting the shipped cell from the grid?")
    ok = True
    for window in ("FULL", "IS", "OOS"):
        a, b = c3.get(("blend36", window)), c3.get(("blend35 (no shipped)", window))
        if not (a and b):
            continue
        ds, dd, dc = b["Sharpe"] - a["Sharpe"], b["MaxDD"] - a["MaxDD"], b["CAR"] - a["CAR"]
        good = abs(ds) <= SHARPE_TIE
        ok &= good
        print(f"  {window:<5} 35-cell minus 36-cell   Sharpe {ds:+.4f}   MaxDD {dd:+.3f}   "
              f"CAR {dc:+.3f}   {'tie' if good else 'MOVES'}")
    verdict = ("the blend is a property of the ensemble, not of the shipped cell" if ok
               else "removing one cell of 36 moves the result - the blend leans on it")
    print(f"\n  clause 4b: {verdict}")
    return ok


def clause_5(cache: dict) -> dict:
    h("CLAUSE 5 - fully charged, S-22 cell C (2 bp one-way spread + IBKR Pro financing)")
    print(HDR)
    print("-" * len(HDR))
    out = {}
    for window in ("FULL", "OOS"):
        for name in ("shipped", "off (switch never fires)", "blend36", "blend35 (no shipped)"):
            k = (name, window, True)
            if k in cache:
                d = cache[k][0]
                out[(name, window)] = d
                print(row(d))
        print("-" * len(HDR))
    print("\n  paired daily return difference against the shipped cell, same sessions:")
    for window in ("FULL", "OOS"):
        base = cache[("shipped", window, True)][1]
        for name in ("blend36", "blend35 (no shipped)", "off (switch never fires)"):
            k = (name, window, True)
            if k not in cache:
                continue
            pr = paired(cache[k][1], base, name, "shipped")
            print(f"    {window:<5} {pr['pair']:<42} {pr['bps_per_day']:+8.3f} bps/day  "
                  f"t {pr['t']:+6.2f}  n {pr['days']:,}")
    return out


def clause_6(cache: dict, c5: dict) -> None:
    h("CLAUSE 6 - turnover: what netting 36 opinions into one order list actually saves")
    print(f"  {'book':<30}{'orders':>9}{'ord/yr':>9}{'turn/yr':>10}{'fees':>12}")
    print("  " + "-" * 68)
    for window in ("FULL",):
        for name in ("shipped", "blend36", "blend35 (no shipped)"):
            d = c5.get((name, window))
            if not d:
                continue
            yrs = d["sessions"] / 252.0
            print(f"  {name:<30}{d['orders']:>9,}{d['orders'] / yrs:>9.0f}"
                  f"{d['turnover_x']:>10.1f}{d['fees']:>12,.0f}")
    shipped = c5.get(("shipped", "FULL"))
    bl = c5.get(("blend36", "FULL"))
    if shipped and bl:
        print(f"\n  the return-average would have paid 36 separate rebalances; the weight-blend\n"
              f"  pays one. Against the single shipped account the blend trades "
              f"{bl['orders'] / shipped['orders']:.2f}x the orders\n"
              f"  and {bl['turnover_x'] / shipped['turnover_x']:.2f}x the turnover, "
              f"for {bl['fees'] / shipped['fees']:.2f}x the fees.")


def clause_7(c5: dict, band_ok: bool) -> None:
    h("CLAUSE 7 - the pre-registered decision")
    verdicts = []
    for window in ("FULL", "OOS"):
        a, s = c5.get(("blend36", window)), c5.get(("shipped", window))
        if not (a and s):
            continue
        sh = a["Sharpe"] >= s["Sharpe"]
        dd = a["MaxDD"] <= s["MaxDD"]
        car = a["CAR"] >= s["CAR"] - CAR_GIVEAWAY
        verdicts.append(sh and dd and car)
        print(f"  {window:<5} Sharpe {a['Sharpe']:.3f} vs {s['Sharpe']:.3f} "
              f"{'PASS' if sh else 'FAIL':<5}   "
              f"MaxDD {a['MaxDD']:.3f} vs {s['MaxDD']:.3f} {'PASS' if dd else 'FAIL':<5}   "
              f"CAR {a['CAR']:.3f} vs {s['CAR']:.3f} (-{CAR_GIVEAWAY:.1f} allowed) "
              f"{'PASS' if car else 'FAIL'}")
    print(f"  band test {'PASS' if band_ok else 'FAIL'}")
    ok = all(verdicts) and band_ok and verdicts
    print(f"\n  VERDICT: {'PROMOTION CANDIDATE' if ok else 'NOT a promotion candidate'}")
    print("  Either way nothing ships from here: a 36-cell blend is not expressible in one\n"
          "  `Params()`, so the book would need a signal-level change and its own LEAN run.")


def clause_7b(cache: dict) -> None:
    """The comparison clause 7 is NOT allowed to make, and the one that matters.

    Clause 7 judges the blend against the shipped cell, which is the right bar for a
    promotion and the wrong bar for a decision, because S-40 proved the shipped cell is not
    a thing anyone could have chosen: a walk-forward argmax over the same grid picks it in 0
    of 11 years. The bar for a decision is what a selector ACTUALLY gets. Those rows are
    S-40's, quoted from `results/s40_full.txt` and not re-simulated here; the blend row is
    clause 3b's, on the identical 2,684 sessions, so the table is span-matched throughout.
    """
    h("CLAUSE 7b - against what a real-time selector actually achieves (S-40's own span)")
    cut = pd.Timestamp(WF_SPAN_START)
    b = cache[("blend36", "FULL", False)][1]
    bl = summarize_span(b[b["date"] >= cut], "weight-blend36 (this harness)")
    cited = [("shipped - HINDSIGHT, 0 of 11 yrs", 24.705, 1.228, 23.860),
             ("grid mean of per-cell CAR", 22.734, float("nan"), float("nan")),
             ("walk-forward, CAR selector", 21.345, 1.011, 38.185),
             ("walk-forward, Sharpe selector", 21.046, 1.000, 38.185),
             ("off (switch never fires)", 28.021, 1.169, 36.619)]
    print(f"  {'book':<36}{'CAR%':>9}{'Sharpe':>8}{'MaxDD%':>9}    source")
    print("  " + "-" * 74)
    print(f"  {bl['cell']:<36}{bl['CAR']:>9.3f}{bl['Sharpe']:>8.3f}{bl['MaxDD']:>9.3f}"
          f"    clause 3b")
    for n, c, s, d in cited:
        sh = f"{s:>8.3f}" if np.isfinite(s) else f"{'n/a':>8}"
        dd = f"{d:>9.3f}" if np.isfinite(d) else f"{'n/a':>9}"
        print(f"  {n:<36}{c:>9.3f}{sh}{dd}    S-40")
    for n, c, s, d in cited[2:4]:
        print(f"\n  blend - {n}:  CAR {bl['CAR'] - c:+.3f}   Sharpe {bl['Sharpe'] - s:+.3f}   "
              f"MaxDD {bl['MaxDD'] - d:+.3f}")
    print("\n  The blend is not a better cell than the one that shipped. It is a better book\n"
          "  than CHOOSING a cell - which is the only thing on offer to anyone deciding this\n"
          "  dial today without S-40's hindsight.")


# --------------------------------------------------------------------------------- ledger

def record(rows: list[dict], skip: bool) -> None:
    if skip:
        print(f"\n  --no-record: {len(rows)} rows NOT written\n")
        return
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with LEDGER.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({
                "ts": stamp, "algorithm": "daily/s41_blend", "class": "book",
                "tag": f"S-41 {r['cell']} @ {r['window']} "
                       f"({'cell C cost' if r['costed'] else 'zero cost'}, DIAGNOSTIC)",
                "commit": "", "run_dir": "",
                "track": "S-41", "start": r["start"], "end": r["end"],
                "stats": {"Sessions": str(r["sessions"]),
                          "Total Orders": str(r["orders"]),
                          "Compounding Annual Return": f"{r['CAR']:.4f}%",
                          "Sharpe Ratio": f"{r['Sharpe']:.3f}",
                          "Drawdown": f"{r['MaxDD']:.3f}%",
                          "Annual Standard Deviation": f"{r['std']:.3f}",
                          "Total Fees": f"${r['fees']:.2f}",
                          "End Equity": f"{r['end_equity']:.2f}"}}, default=str) + "\n")
    print(f"\n  recorded {len(rows)} DIAGNOSTIC rows in {LEDGER.name}\n")


def s40_return_average() -> dict | None:
    """S-40's upper bound, read from its cache so it is not re-simulated here."""
    if not S40_CACHE.exists():
        return None
    c40 = pickle.loads(S40_CACHE.read_bytes())
    out = {}
    for window in ("FULL", "IS", "OOS"):
        books = []
        for cell in grid_cells():
            k = (tuple(sorted(cell.items())), window, False)
            if k in c40:
                books.append(c40[k][1][["date", "ret"]])
        if len(books) != 36:
            return None
        m = books[0].rename(columns={"ret": "r0"})
        for i, b in enumerate(books[1:], 1):
            m = m.merge(b.rename(columns={"ret": f"r{i}"}), on="date")
        ret = m[[c for c in m.columns if c.startswith("r")]].mean(axis=1).to_numpy()
        curve = np.cumprod(1 + ret)
        yrs = len(ret) / 252.0
        out[window] = {"cell": "S-40 return-average", "sessions": len(ret),
                       "CAR": 100 * (curve[-1] ** (1 / yrs) - 1),
                       "Sharpe": ret.mean() / ret.std(ddof=1) * np.sqrt(252),
                       "MaxDD": 100 * float((1 - curve / np.maximum.accumulate(curve)).max()),
                       "std": ret.std(ddof=1) * np.sqrt(252)}
    return out


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
    shipped = [c for c in cells if is_shipped(c)]
    assert len(shipped) == 1, "the shipped cell must be in the pre-registered grid"
    no_ship = [c for c in cells if not is_shipped(c)]

    # ---- the weight paths. IS is a prefix of FULL (same start, same i0, state from {}),
    #      so only FULL and OOS are walked.
    path_jobs = [(c, w) for c in cells for w in ("FULL", "OOS")]
    run_pool(path_jobs, _path_job, cache, a.workers, "weight paths",
             key_of=lambda j: (tuple(sorted(j[0].items())), j[1]))
    CACHE_PATH.write_bytes(pickle.dumps(cache))

    for c in cells:                                   # IS = the FULL path, truncated
        kf = (tuple(sorted(c.items())), "FULL")
        ki = (tuple(sorted(c.items())), "IS")
        if ki not in cache:
            cut = pd.Timestamp(WINDOWS["IS"][1])
            cache[ki] = ({d: w for d, w in cache[kf][0].items() if d <= cut}, cache[kf][1])

    blends = {}
    for w in ("FULL", "IS", "OOS"):
        blends[("blend36", w)] = blend(cache, cells, w)
        blends[("blend35 (no shipped)", w)] = blend(cache, no_ship, w)

    # ---- the books
    sim_jobs = [(("shipped",), {}, w, False, None) for w in ("FULL", "IS", "OOS")]
    sim_jobs += [(("shipped (fed its own weights)",), {}, "FULL", False,
                  cache[(tuple(sorted(shipped[0].items())), "FULL")][0])]
    sim_jobs += [(("off (switch never fires)",), {"regime_threshold": OFF_THRESHOLD}, w,
                  costed, None)
                 for w in ("FULL", "IS", "OOS") for costed in ((False, True)
                                                               if w != "IS" else (False,))]
    for (name, w), bl in blends.items():
        for costed in ((False, True) if w != "IS" else (False,)):
            sim_jobs.append(((name,), {}, w, costed, bl))
    sim_jobs += [(("shipped",), {}, w, True, None) for w in ("FULL", "OOS")]
    run_pool(sim_jobs, _sim_job, cache, a.workers, "books",
             key_of=lambda j: (j[0][0], j[2], j[3]))
    CACHE_PATH.write_bytes(pickle.dumps(cache))
    for k in list(cache):                     # books cached as (describe, records)
        if len(k) == 3 and isinstance(cache[k][1], list):
            cache[k] = (cache[k][0], pd.DataFrame(cache[k][1]))

    ok = clause_1(cache)
    ok &= clause_2()
    if not ok:
        print("\nPRE-REGISTERED STOP: clause 1 or 2 failed, nothing below is readable.")
        return 1
    c3 = clause_3(cache, s40_return_average())
    clause_3b(cache)
    band = clause_4(blends[("blend36", "FULL")], disagreement(cache, cells, "FULL"), "FULL",
                    composition(cache, cells, blends[("blend36", "FULL")], "FULL"))
    clause_4(blends[("blend36", "OOS")], disagreement(cache, cells, "OOS"), "OOS",
             composition(cache, cells, blends[("blend36", "OOS")], "OOS"))
    clause_4b(c3)
    c5 = clause_5(cache)
    clause_6(cache, c5)
    clause_7(c5, band["ok"])
    clause_7b(cache)

    rows = [cache[k][0] for k in cache if len(k) == 3 and "CAR" in cache[k][0]]
    record(rows, a.no_record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
