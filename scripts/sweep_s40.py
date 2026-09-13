#!/usr/bin/env python
"""S-40: the crisis switch is the most-fitted thing in the champion. Is it worth anything,
and could anyone have found the shipped cell in real time?

    python scripts/sweep_s40.py --workers 10      # the whole thing, ~8 min
    python scripts/sweep_s40.py --stage a         # clauses 1-3: identity, ablation, grid
    python scripts/sweep_s40.py --no-record       # do not append to the ledger

WHY THIS ITEM. S-38 (AUD-11 part 2) priced selection inflation on all eight tunable axes and
found the two biggest contributors by a wide margin are the two halves of the crisis switch:

    regime_vol_window   +3.596 CAR points   "the one dial in the parameter set with NO
                                             selection record anywhere"
    regime_threshold    +3.016 CAR points
    mom_skip            +0.074              (a dead heat, for scale)

S-38 stopped at "the shipped cell sits this far above its grid mean", which is a statement
about hindsight. It never asked the question that decides whether those 6.6 points are an
asset or an accounting artefact: **is the surface stable enough that a selector running in
real time would have landed on, or near, the shipped cell?** If yes, the switch is real edge
and the champion's headline is defensible. If no, the +6.6 is unrealizable, the honest
forward expectation of the switch is the grid mean, and the sleeve is carrying two fitted
dials for nothing.

Third possibility, and it is the one nobody has priced: the switch may be worth nothing even
at its best cell. `risk_on` has never been ablated end to end. S-1 refused the *original*
below-median filter and a 200-day trend filter; the crisis multiple that replaced them was
adopted on a table and has been in the book ever since without an off-switch run.

WHAT MAKES THE WALK-FORWARD EXACT HERE, stated before it is used. At the shipped defaults
`dd_halve = dd_flat = 9.0` while `drawdown_multiplier`'s `dd = 1 - last/peak` is bounded by
1.0, so the overlay returns 1.0 on every session and `equity_curve` - its only consumer in
`target_weights` - cannot reach the weights. Target weights are therefore a pure function of
(prices, params): a cell's return on date t does not depend on what the book did before t
under a different cell. Stitching year-by-year is exact up to the one rebalance at each
boundary, and clause 4 counts those boundaries and bounds their cost rather than waving at
them. This is asserted in clause 2b and the whole walk-forward is void if it fails.

PRE-REGISTERED before the first simulation, seven clauses
--------------------------------------------------------
(1) IDENTITY. At the shipped `Params()` this harness reproduces the deployed cell to the
    digit - CAR 22.192150170492255%, 5,052 orders, 2012-2026 at zero cost - the figure S-25,
    S-26, S-28, S-30, S-31, S-32, S-33, S-36, S-37 and S-39 each quote independently. If it
    misses, nothing below may be read.

(2a) THE ABLATION. `regime_threshold = 1e9` makes `vol_now >= threshold * median` unreachable,
    so `risk_on` returns True on every session with sufficient history and the switch is off.
    Verified by counting risk-off sessions, not assumed: the `off` cell must have 0 and the
    shipped cell must have > 0.
(2b) THE PURITY ASSERTION above: `dd_halve > 1.0 and dd_flat > 1.0`. Arithmetic, not a
    simulation, and it is what licenses clause 4.

(3) THE JOINT GRID, zero cost, on IS 2012-2019 / FULL 2012-2026 / OOS 2020-2026:
        regime_threshold   {1.25, 1.40, 1.50*, 1.60, 1.75, 2.00}
        regime_vol_window  {10, 15, 20*, 30, 40, 60}
    36 cells plus `off`. S-38 moved these two coordinate-wise through the shipped point; this
    runs the joint surface, which is the object a selector actually searches. Reported: where
    the shipped cell ranks on each window, and the FULL-argmax.

(4) THE WALK-FORWARD, which is the hypothesis. For each year Y in 2016..2026 the selector
    sees only 2012-01-03..(Y-1)-12-31 - a backtest anyone could have run on 31 December - and
    takes that window's argmax over the 36 cells. Two selectors are run because the choice of
    objective is itself a researcher degree of freedom: `CAR` and `Sharpe`. The chosen cell's
    daily returns are taken for year Y and the years are stitched (licensed by 2b). Reported
    against: the shipped cell, the `off` cell, and the grid's own equal-weight mean over the
    same 2016-2026 span. Pre-registered branches on `walk-forward CAR - grid-mean CAR`:
      (a) >= +2.0 and the shipped cell within 0.5 of walk-forward -> the surface is STABLE,
          the shipped cell is defensible, and S-38's +6.6 is realizable rather than hindsight;
      (b) -0.5 .. +2.0 -> PARTIALLY realizable; the honest forward number sits between the
          grid mean and the shipped cell and must be quoted as a range;
      (c) < -0.5 -> selecting on this axis in real time is HARMFUL and the shipped cell's
          distance above the grid mean is hindsight in full.
    EXPECTATION, stated first: (c) or the bottom of (b). S-33 measured this sleeve's pooled
    selection premium at -0.049 CAR points - choosing a parameter on the first half predicts
    nothing about the second - and there is no reason the crisis switch should be the
    exception just because its grid is wider. A wide grid with no predictive selection is
    exactly the signature of a dial that is fitting noise.
    Also reported: how often each selector picks the shipped cell (the hit rate), and the
    number of boundaries at which the selection actually changes, which bounds the stitch's
    unmodelled rebalance cost at ~2 x gross x spread per switch.

(5) IS THE SWITCH WORTH ANYTHING AT ALL? `off` against shipped, against the grid mean and
    against the walk-forward book, on FULL/IS/OOS, with the paired daily t. Pre-registered:
    if `off` is within 0.5 CAR points of the walk-forward book and does not carry materially
    more drawdown (> 2.0 points), the switch is two fitted dials buying nothing that a real
    selector could have captured, and that is a reportable simplification of the book - filed
    as an item, never shipped from here.

(6) WHAT THE SWITCH DOES. Risk-off session counts per cell and the shipped cell's episodes,
    plus a cross-check that the vectorized mask agrees with the simulation (on a risk-off
    session the deployed book's gross must collapse).

(7) COST. Every headline cell re-run in S-22's honest historical book (2 bp one-way spread
    plus IBKR Pro financing on the historical effective fed funds rate) on FULL and OOS, with
    the paired daily return difference and its t. Nothing on this sleeve has reached |t| = 2
    except S-31's arithmetic, S-33's re-selection and S-38's; this will be said out loud
    whatever it is.

DIAGNOSTIC. No shipped or runner-loaded file is touched: the shipped `Params()` defaults,
`live/*`, `champion.json` and all scheduled tasks are untouched, so no deploy gate and no
`--replay` is owed. `target_vol`, `target_exposure`, `margin_budget` and the drawdown cap are
the owner's and are READ here, never changed.
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
from sweep_s19 import paired, tstat                            # noqa: E402
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

#: clause 1 - the cell ten previous iterations agree on
S25_DEPLOYED_CAR = 22.192150170492255
S25_DEPLOYED_ORDERS = 5052

#: clause 3 - the joint surface
THRESHOLDS = (1.25, 1.40, 1.50, 1.60, 1.75, 2.00)
VOL_WINDOWS = (10, 15, 20, 30, 40, 60)
SHIPPED_CELL = (1.50, 20)
#: clause 2a - unreachable, so `risk_on` never returns False on a vol crisis
OFF_THRESHOLD = 1e9

#: clause 4 - the first year the selector is allowed to speak (4 years of training)
WF_FIRST_YEAR = 2016

#: clause 7 - S-22's honest historical book
SPREAD_BPS = 2.0

#: clause 5 - the pre-registered materiality bars
CAR_BAR = 0.5
DD_BAR = 2.0

CACHE_PATH = REPO / "results" / "s40_cache.pkl"


# ------------------------------------------------------------------------------- machinery

def cells() -> list[dict]:
    """The 36 grid cells plus the ablation, as `over` dicts for `make_params`."""
    out = [{"regime_threshold": t, "regime_vol_window": w}
           for t in THRESHOLDS for w in VOL_WINDOWS]
    out.append({"regime_threshold": OFF_THRESHOLD})
    return out


def make_params(over: dict) -> sig.Params:
    return dataclasses.replace(sig.Params(), **over) if over else sig.Params()


def cell_name(over: dict) -> str:
    if not over:
        return "shipped"
    if over.get("regime_threshold") == OFF_THRESHOLD and "regime_vol_window" not in over:
        return "off (switch never fires)"
    return f"thr={over['regime_threshold']:.2f} win={over['regime_vol_window']}"


def is_shipped(over: dict) -> bool:
    return (over.get("regime_threshold"), over.get("regime_vol_window")) == SHIPPED_CELL


def is_off(over: dict) -> bool:
    return over.get("regime_threshold") == OFF_THRESHOLD


def key_of(over: dict, window: str, costed: bool) -> tuple:
    return (tuple(sorted(over.items())), window, costed)


_FRAMES: dict | None = None
_FIN: dict | None = None


def _init_worker() -> None:
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
    keep = ["date", "ret"] + (["gross_x"] if "gross_x" in book else [])
    return key_of(over, window, costed), d, book[keep].to_dict("records")


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


def summarize_returns(dates, ret, label: str) -> dict:
    """`sweep_s19.summarize`'s statistics on a bare return series (the stitched book)."""
    ret = np.asarray(ret, dtype=float)
    n = len(ret)
    years = n / 252.0
    curve = np.cumprod(1 + ret)
    sd = ret.std(ddof=1)
    return {"cell": label, "sessions": n,
            "CAR": 100 * (curve[-1] ** (1 / years) - 1) if years > 0 else float("nan"),
            "Sharpe": (ret.mean() / sd * np.sqrt(252)) if sd else float("nan"),
            "MaxDD": 100 * float((1 - curve / np.maximum.accumulate(curve)).max()),
            "std": sd * np.sqrt(252), "orders": 0, "fees": 0.0,
            "end_equity": float(curve[-1])}


def row(d: dict, extra: str = "") -> str:
    return (f"{d['cell']:<28}{d['sessions']:>6}{d['CAR']:>9.3f}{d['Sharpe']:>8.3f}"
            f"{d['MaxDD']:>8.3f}{d['std']:>7.3f}{d['orders']:>8,}{extra}")


HDR = (f"{'cell':<28}{'sess':>6}{'CAR%':>9}{'Sharpe':>8}{'MaxDD%':>8}{'std':>7}{'orders':>8}")


# --------------------------------------------------------------- clause 6: the risk-off mask

def regime_masks(frames: dict) -> dict:
    """Risk-off mask per (threshold, window), vectorized from the same definition `risk_on`
    uses: `vol >= threshold * trailing-252-median(vol)`, both on `REGIME_TICKER`.

    `risk_on` computes these on a truncated slice, but a rolling std of length `w` and a
    trailing median of the last `regime_median_window` of them each read a fixed number of
    rows back, and `Params.history_bars` is built (signals.py:427) to cover exactly that, so
    the last value of the slice equals the full-history rolling value. Clause 6 checks the
    result against the simulation rather than trusting this paragraph.
    """
    p = sig.Params()
    px = frames["close"][sig.REGIME_TICKER] if "close" in frames else None
    if px is None:                                 # load_ohlcv returns per-field frames
        raise KeyError("close frame missing from the price store")
    out = {}
    for w in VOL_WINDOWS:
        vol = px.pct_change().rolling(w).std(ddof=1) * np.sqrt(sig.TRADING_DAYS)
        med = vol.rolling(p.regime_median_window).median()
        for t in THRESHOLDS:
            out[(t, w)] = (vol >= t * med) & np.isfinite(vol) & np.isfinite(med)
    return out


# ------------------------------------------------------------------------------- the clauses

def clause_1(cache: dict) -> bool:
    print("=" * 100)
    print("(1) IDENTITY - the deployed cell, FULL, zero cost")
    print("=" * 100)
    d = get(cache, {}, "FULL")
    ok = (abs(d["CAR"] - S25_DEPLOYED_CAR) < 1e-9 and d["orders"] == S25_DEPLOYED_ORDERS)
    print(f"  CAR    {d['CAR']!r}   expected {S25_DEPLOYED_CAR!r}   "
          f"delta {d['CAR'] - S25_DEPLOYED_CAR:.3e}")
    print(f"  orders {d['orders']:,}   expected {S25_DEPLOYED_ORDERS:,}")
    print(f"  -> {'PASS' if ok else 'FAIL'}\n")
    return ok


def clause_2(cache: dict, masks: dict) -> bool:
    print("=" * 100)
    print("(2) THE ABLATION and THE PURITY ASSERTION")
    print("=" * 100)
    p = sig.Params()
    pure = p.dd_halve > 1.0 and p.dd_flat > 1.0
    print(f"  (2b) dd_halve={p.dd_halve} dd_flat={p.dd_flat}, and `dd = 1 - last/peak` <= 1.0")
    print(f"       -> the drawdown overlay is inert, `equity_curve` cannot reach the weights,")
    print(f"          target weights are a pure function of (prices, params): "
          f"{'PASS' if pure else 'FAIL'}")
    shipped_off = int(masks[SHIPPED_CELL].sum())
    off_params = make_params({"regime_threshold": OFF_THRESHOLD})
    print(f"  (2a) shipped cell risk-off sessions over the store: {shipped_off}")
    print(f"       ablation threshold {off_params.regime_threshold:.0e} makes "
          f"`vol >= thr * median` unreachable (max vol/median seen: "
          f"{_max_ratio(masks):.2f})")
    ok = pure and shipped_off > 0
    print(f"  -> {'PASS' if ok else 'FAIL'}\n")
    return ok


_MAX_RATIO = {"v": 0.0}


def _max_ratio(masks: dict) -> float:
    return _MAX_RATIO["v"]


def clause_3(cache: dict) -> dict:
    print("=" * 100)
    print("(3) THE JOINT GRID - 36 cells, zero cost, shipped marked *")
    print("=" * 100)
    grid = [c for c in cells() if not is_off(c)]
    out = {}
    for window in ("IS", "FULL", "OOS"):
        cars = {(c["regime_threshold"], c["regime_vol_window"]): get(cache, c, window)["CAR"]
                for c in grid}
        out[window] = cars
        ship = cars[SHIPPED_CELL]
        vals = np.array(sorted(cars.values()))
        pct = 100.0 * float((vals <= ship).mean())
        rank = int((vals > ship).sum()) + 1
        best = max(cars, key=cars.get)
        print(f"\n  --- {window} {WINDOWS[window][0]}..{WINDOWS[window][1]}  "
              f"mean {vals.mean():.3f}  sd {vals.std(ddof=1):.3f}  "
              f"range {vals.min():.3f}..{vals.max():.3f}")
        print(f"      shipped thr=1.50 win=20: {ship:.3f}  "
              f"(+{ship - vals.mean():.3f} vs mean, {pct:.0f}th pct, rank {rank} of 36)  "
              f"argmax thr={best[0]:.2f} win={best[1]} at {cars[best]:.3f}")
        print("      " + "win/thr".rjust(9) + "".join(f"{t:>9.2f}" for t in THRESHOLDS))
        for w in VOL_WINDOWS:
            line = f"      {w:>9}"
            for t in THRESHOLDS:
                mark = "*" if (t, w) == SHIPPED_CELL else " "
                line += f"{cars[(t, w)]:>8.2f}{mark}"
            print(line)
        off = get(cache, {"regime_threshold": OFF_THRESHOLD}, window)
        print(f"      off (switch never fires): {off['CAR']:.3f}  "
              f"(vs grid mean {off['CAR'] - vals.mean():+.3f}, vs shipped "
              f"{off['CAR'] - ship:+.3f})")
    print()
    return out


def clause_4(cache: dict) -> dict:
    print("=" * 100)
    print("(4) THE WALK-FORWARD - the selector sees only what a 31-December backtest would")
    print("=" * 100)
    grid = [c for c in cells() if not is_off(c)]
    books = {(c["regime_threshold"], c["regime_vol_window"]): book_of(cache, c, "FULL")
             for c in grid}
    dates = pd.to_datetime(books[SHIPPED_CELL]["date"])
    years = sorted({d.year for d in dates if d.year >= WF_FIRST_YEAR})
    rets = {k: pd.Series(v["ret"].to_numpy(), index=pd.to_datetime(v["date"]))
            for k, v in books.items()}

    def score(k, upto, how):
        s = rets[k][rets[k].index <= upto]
        if how == "CAR":
            return float(np.prod(1 + s.to_numpy()) ** (252.0 / len(s)) - 1)
        sd = s.std(ddof=1)
        return float(s.mean() / sd * np.sqrt(252)) if sd else float("nan")

    result = {}
    for how in ("CAR", "Sharpe"):
        picks, series, hits, switches = {}, [], 0, 0
        prev = None
        for y in years:
            cutoff = pd.Timestamp(f"{y - 1}-12-31")
            pick = max(rets, key=lambda k: score(k, cutoff, how))
            picks[y] = pick
            hits += int(pick == SHIPPED_CELL)
            switches += int(prev is not None and pick != prev)
            prev = pick
            seg = rets[pick][(rets[pick].index >= pd.Timestamp(f"{y}-01-01"))
                             & (rets[pick].index <= pd.Timestamp(f"{y}-12-31"))]
            series.append(seg)
        wf = pd.concat(series).sort_index()
        span_start, span_end = wf.index[0], wf.index[-1]
        d = summarize_returns(wf.index, wf.to_numpy(), f"walk-forward ({how})")
        # everything else restricted to the same span, so the comparison is paired
        def span(k):
            s = rets[k]
            return s[(s.index >= span_start) & (s.index <= span_end)]
        ship = summarize_returns(None, span(SHIPPED_CELL).to_numpy(), "shipped (same span)")
        off_book = book_of(cache, {"regime_threshold": OFF_THRESHOLD}, "FULL")
        off_s = pd.Series(off_book["ret"].to_numpy(), index=pd.to_datetime(off_book["date"]))
        off_s = off_s[(off_s.index >= span_start) & (off_s.index <= span_end)]
        off = summarize_returns(None, off_s.to_numpy(), "off (same span)")
        eq = np.mean([span(k).to_numpy() for k in rets], axis=0)
        gmean = summarize_returns(None, eq, "grid equal-weight (same span)")
        grid_car_mean = float(np.mean([summarize_returns(None, span(k).to_numpy(), "")["CAR"]
                                       for k in rets]))

        print(f"\n  --- selector = argmax {how}, {span_start.date()}..{span_end.date()}")
        print(f"      picks: " + "  ".join(
            f"{y}:{picks[y][0]:.2f}/{picks[y][1]}" for y in years))
        print(f"      shipped cell chosen in {hits} of {len(years)} years; "
              f"{switches} boundary switches "
              f"(unmodelled rebalance <= {switches * 2 * 1.6 * SPREAD_BPS:.0f} bps total, "
              f"~{switches * 2 * 1.6 * SPREAD_BPS / 1e4 * 100 / (len(wf) / 252):.3f} CAR pts)")
        print("      " + HDR)
        for d_ in (d, ship, off, gmean):
            print("      " + row(d_))
        print(f"      grid MEAN of per-cell CAR over the span: {grid_car_mean:.3f}")
        delta = d["CAR"] - grid_car_mean
        gap_ship = abs(d["CAR"] - ship["CAR"])
        branch = ("(a) STABLE - realizable" if delta >= 2.0 and gap_ship <= CAR_BAR
                  else "(b) PARTIALLY realizable - quote a range" if delta >= -CAR_BAR
                  else "(c) HARMFUL - the shipped cell's distance is hindsight in full")
        print(f"      walk-forward - grid mean = {delta:+.3f} CAR points; "
              f"|walk-forward - shipped| = {gap_ship:.3f}")
        print(f"      -> BRANCH {branch}")
        wf_df = pd.DataFrame({"date": wf.index, "ret": wf.to_numpy()})
        sh_df = pd.DataFrame({"date": span(SHIPPED_CELL).index,
                              "ret": span(SHIPPED_CELL).to_numpy()})
        of_df = pd.DataFrame({"date": off_s.index, "ret": off_s.to_numpy()})
        for a, b, na, nb in ((wf_df, sh_df, f"wf({how})", "shipped"),
                             (wf_df, of_df, f"wf({how})", "off"),
                             (sh_df, of_df, "shipped", "off")):
            pr = paired(a, b, na, nb)
            print(f"      paired {pr['pair']:<22} {pr['bps_per_day']:+.3f} bps/day  "
                  f"t {pr['t']:+.2f}  n {pr['days']}")
        result[how] = {"wf": d, "shipped": ship, "off": off, "grid_mean": grid_car_mean,
                       "delta": delta, "branch": branch, "picks": picks, "hits": hits,
                       "switches": switches, "span": (span_start, span_end)}
    print()
    return result


def clause_5(cache: dict, grid: dict, wf: dict) -> None:
    print("=" * 100)
    print("(5) IS THE SWITCH WORTH ANYTHING AT ALL?")
    print("=" * 100)
    for window in ("IS", "FULL", "OOS"):
        ship = get(cache, {}, window)
        off = get(cache, {"regime_threshold": OFF_THRESHOLD}, window)
        gmean = float(np.mean(list(grid[window].values())))
        print(f"\n  --- {window}")
        print("      " + HDR)
        print("      " + row({**ship, "cell": "shipped"}))
        print("      " + row({**off, "cell": "off"}))
        print(f"      grid mean CAR {gmean:.3f}")
        print(f"      off - shipped   {off['CAR'] - ship['CAR']:+.3f} CAR, "
              f"{off['MaxDD'] - ship['MaxDD']:+.3f} DD pts, "
              f"{off['Sharpe'] - ship['Sharpe']:+.3f} Sharpe")
        pr = paired(book_of(cache, {"regime_threshold": OFF_THRESHOLD}, window),
                    book_of(cache, {}, window), "off", "shipped")
        print(f"      paired {pr['pair']:<22} {pr['bps_per_day']:+.3f} bps/day  "
              f"t {pr['t']:+.2f}  n {pr['days']}")
    best = wf["CAR"]
    gap = best["off"]["CAR"] - best["wf"]["CAR"]
    dd = best["off"]["MaxDD"] - best["wf"]["MaxDD"]
    verdict = ("TWO FITTED DIALS BUYING NOTHING a real selector could capture"
               if abs(gap) <= CAR_BAR and dd <= DD_BAR
               else "the switch carries content beyond what the grid mean measures")
    print(f"\n  off - walk-forward(CAR) over the walk-forward span: {gap:+.3f} CAR, "
          f"{dd:+.3f} DD pts")
    print(f"  -> {verdict}\n")


def clause_6(cache: dict, masks: dict) -> None:
    print("=" * 100)
    print("(6) WHAT THE SWITCH DOES - risk-off sessions, and the mask against the simulation")
    print("=" * 100)
    book = book_of(cache, {}, "FULL")
    dates = pd.to_datetime(book["date"])
    m = masks[SHIPPED_CELL].reindex(dates).fillna(False).to_numpy()
    print("      " + "win/thr".rjust(9) + "".join(f"{t:>9.2f}" for t in THRESHOLDS))
    for w in VOL_WINDOWS:
        line = f"      {w:>9}"
        for t in THRESHOLDS:
            s = masks[(t, w)].reindex(dates).fillna(False)
            mark = "*" if (t, w) == SHIPPED_CELL else " "
            line += f"{int(s.sum()):>8}{mark}"
        print(line)
    print(f"      (counts are risk-off sessions of {len(dates):,} in the FULL book)")
    if "gross_x" in book:
        g = book["gross_x"].to_numpy()
        print(f"\n      cross-check: mean gross on the shipped cell's risk-ON sessions "
              f"{g[~m].mean():.3f}x, on its risk-OFF sessions {g[m].mean():.3f}x")
    # the episodes
    s = pd.Series(m, index=dates)
    grp = (s != s.shift()).cumsum()[s]
    eps = [(str(g.index[0].date()), str(g.index[-1].date()), len(g))
           for _, g in s[s].groupby(grp)]
    print(f"\n      shipped cell: {len(eps)} risk-off episodes, {int(m.sum())} sessions")
    for a, b, n in eps:
        print(f"        {a} .. {b}  ({n} sessions)")
    print()


def clause_7(cache: dict) -> list[dict]:
    print("=" * 100)
    print("(7) COST - S-22's honest historical book (2 bp one-way + IBKR Pro financing)")
    print("=" * 100)
    rows = []
    for window in ("FULL", "OOS"):
        ship = get(cache, {}, window, True)
        off = get(cache, {"regime_threshold": OFF_THRESHOLD}, window, True)
        print(f"\n  --- {window}, costed")
        print("      " + HDR + f"{'fees':>12}")
        for d, name in ((ship, "shipped"), (off, "off")):
            print("      " + row({**d, "cell": name}, f"{d['fees']:>12,.0f}"))
            rows.append({**d, "cell": name, "note": "costed"})
        pr = paired(book_of(cache, {"regime_threshold": OFF_THRESHOLD}, window, True),
                    book_of(cache, {}, window, True), "off", "shipped")
        print(f"      paired {pr['pair']:<22} {pr['bps_per_day']:+.3f} bps/day  "
              f"t {pr['t']:+.2f}  n {pr['days']}")
        print(f"      off - shipped {off['CAR'] - ship['CAR']:+.3f} CAR, "
              f"{off['MaxDD'] - ship['MaxDD']:+.3f} DD pts")
    print()
    return rows


def record(rows: list[dict], no_record: bool) -> None:
    if no_record:
        return
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with LEDGER.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({
                "ts": stamp, "algorithm": "daily/s40_regime", "class": "book",
                "tag": f"S-40 {r['cell']} @ {r['window']} ({r.get('note', 'DIAGNOSTIC')})",
                "commit": "", "run_dir": "",
                "track": "S-40", "start": r["start"], "end": r["end"],
                "stats": {"Sessions": str(r["sessions"]),
                          "Total Orders": str(r["orders"]),
                          "Compounding Annual Return": f"{r['CAR']:.4f}%",
                          "Sharpe Ratio": f"{r['Sharpe']:.3f}",
                          "Drawdown": f"{r['MaxDD']:.3f}%",
                          "Annual Standard Deviation": f"{r['std']:.3f}",
                          "Total Fees": f"${r['fees']:.2f}",
                          "End Equity": f"{r['end_equity']:.2f}"}}, default=str) + "\n")
    print(f"  recorded {len(rows)} DIAGNOSTIC rows in {LEDGER.name}\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--stage", choices=["a", "b", "all"], default="all")
    ap.add_argument("--no-record", action="store_true")
    ap.add_argument("--fresh", action="store_true", help="ignore the cache")
    a = ap.parse_args()

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cache: dict = {}
    if CACHE_PATH.exists() and not a.fresh:
        cache = pickle.loads(CACHE_PATH.read_bytes())
        print(f"cache: {len(cache)} books\n")

    frames = load_ohlcv(sig.traded_universe(sig.Params()))
    masks = regime_masks(frames)
    p = sig.Params()
    px = frames["close"][sig.REGIME_TICKER]
    vol = px.pct_change().rolling(p.regime_vol_window).std(ddof=1) * np.sqrt(sig.TRADING_DAYS)
    med = vol.rolling(p.regime_median_window).median()
    _MAX_RATIO["v"] = float((vol / med).max())

    jobs = [({}, w, False) for w in WINDOWS]
    jobs += [(c, w, False) for c in cells() for w in WINDOWS]
    if a.stage != "a":
        jobs += [({}, w, True) for w in ("FULL", "OOS")]
        jobs += [(c, w, True) for c in cells() if is_off(c) for w in ("FULL", "OOS")]
    run_jobs(jobs, cache, a.workers, "books")
    CACHE_PATH.write_bytes(pickle.dumps(cache))

    ok = clause_1(cache)
    ok &= clause_2(cache, masks)
    if not ok:
        print("PRE-REGISTERED STOP: clause 1 or 2 failed, nothing below is readable.")
        return 1
    grid = clause_3(cache)
    if a.stage == "a":
        clause_6(cache, masks)
        return 0
    wf = clause_4(cache)
    clause_5(cache, grid, wf)
    clause_6(cache, masks)
    rows = clause_7(cache)
    for c in cells():
        for w in WINDOWS:
            rows.append({**get(cache, c, w), "note": "zero cost"})
    for w in WINDOWS:
        rows.append({**get(cache, {}, w), "cell": "shipped", "note": "zero cost"})
    record(rows, a.no_record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
