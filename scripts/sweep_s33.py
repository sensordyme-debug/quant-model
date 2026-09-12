#!/usr/bin/env python
"""S-33 (AUD-11): the champion's "OOS 2020-2026" is a sub-period of a full-period fit.
How much of it is selection?

    python scripts/sweep_s33.py --stage a     # clauses 1-2: identity and the grid
    python scripts/sweep_s33.py --stage b     # clauses 3-7: re-selection, premium, honest number
    python scripts/sweep_s33.py --no-record   # do not append to the ledger

THE FINDING BEING PRICED. `research/audit_2026-09-12.md`, AUD-11:

    "Every shipped parameter (`mom_skip`, `alloc_vol_window`, the 252 shelf, the band) was
     chosen on full-period tables; the 2020-2026 'OOS' is a sub-period check of the chosen
     set. The honest ~20% CAR is fully in-sample, and the 33% PSR says the same. Every
     OOS-weighted claim (S-18, S-22, S-26, S-28) inherits it. Fix: re-select on 2012-2019
     and report 2020-2026 once, or relabel and treat paper trading as the only
     out-of-sample evidence."

The finding is correct as a matter of record - the three tables quoted in `signals.py`'s own
docstrings (S-9's fourth-horizon shelf, S-10's skip walk, S-12's inverse-vol window) are all
full-period LEAN numbers, and 2020-2026 was read afterwards. What the audit does NOT say is
what the contamination is WORTH, and that is the only form of the question the loop can act
on: a label that overstates by 0.1 CAR points is a documentation fix, a label that overstates
by 5 is a different strategy than the one in `champion.json`.

This iteration measures it the only way it can be measured - by re-doing the selection with
2020-2026 genuinely withheld and reading the withheld half once.

PRE-REGISTERED before the first number, seven clauses
----------------------------------------------------
(1) IDENTITY. At the shipped `Params()` this harness must reproduce the deployed cell to the
    digit - CAR 22.192150%, 5,052 orders at zero cost over 2012-2026 - the figure S-25, S-26,
    S-28, S-30, S-31 and S-32 each quote independently. If it misses, the grid below is
    measuring a different book and nothing in it may be read.

(2) THE GRID IS THE SELECTION RECORD, NOT A NEW SEARCH. Three axes, each taken verbatim from
    the docstring in `signals.py` that records how the shipped value was chosen, so this is a
    re-run of the actual selection rather than a fresh hunt:
      - `mom_skip` in {2, 3, 5*, 8, 10, 15, 20}            (S-10's table, * = shipped)
      - `alloc_vol_window` in {10, 20, 21*, 30, 40, 60}    (S-12's table)
      - the fourth `mom_lookbacks` horizon in {150, 220, 250, 252*, 280, 300, 320}  (S-9's shelf)
    Coordinate-wise from the shipped set, which is how the record shows the three were chosen
    (one iteration each: S-9, S-10, S-12). Cost cell: ZERO SPREAD, because that is the cell
    all three tables were read in; re-costing comes in clause 6 and changes no selection.

(3) THE SELECTION RULE, written down before the numbers. Argmax CAR on the selection window,
    per axis, ties to the shipped value. Two windows are selected on: FULL 2012-2026 (what
    was actually done) and IS 2012-2019 (what should have been done). Each window's winner
    is then read ONCE on 2020-2026.

(4) THE CLAUSE THIS CAN FAIL ON. Pre-registered consequence for each branch, so the result
    can be wrong rather than merely reported:
      (a) if IS re-selection lands on the shipped values on all three axes, the audit's
          finding is COSMETIC - the label is wrong, the number is not, and the fix is to
          relabel;
      (b) if IS re-selection moves and its 2020-2026 CAR is WORSE than the shipped set's,
          the published OOS is contaminated by exactly that difference, and that difference
          is the correction owed to `champion.json`;
      (c) if IS re-selection moves and its 2020-2026 CAR is BETTER, the full-period fit is
          not even a good fit - it bought in-sample CAR at the cost of the withheld half.
    EXPECTATION, stated first: (b), by 1-3 CAR points. If it is under 0.5 the finding is
    cosmetic whatever branch it lands in.

(5) THE SELECTION PREMIUM, which is the deliverable this file is actually for. Branch (a)/(b)
    tells you about one draw. The durable quantity is whether choosing a parameter on this
    sleeve's first half predicts anything about its second: the Spearman rank correlation
    between IS CAR and OOS CAR across the whole grid, per axis and pooled, and the OOS CAR of
    the IS-argmax against the OOS CAR of the grid's MEDIAN cell. If the argmax is no better
    out of sample than the median cell, parameter selection here has NO out-of-sample content
    and the honest forward expectation of any fitted cell is the grid's central tendency -
    which is a statement about every S-item in this repository, not just this one.

(6) THE HONEST NUMBER. The shipped set and the IS-selected set, both on 2020-2026, in cell C
    (2 bp of one-way spread plus IBKR Pro financing on the historical effective fed funds
    rate - S-22's honest historical book, the cell `champion.json`'s
    `deployed_expectation_note` is quoted in). Plus the grid's OOS spread in that same cell,
    so the sentence "the champion's forward expectation is X" carries its selection error.

(7) SIGNIFICANCE, stated rather than discovered. The paired daily return difference of the
    IS-selected set against the shipped set over 2020-2026 with its t. Nothing on this sleeve
    has reached |t| = 2 except S-31's arithmetic, and this will be said out loud whatever it is.

DIAGNOSTIC. Nothing here is promotable and no shipped or runner-loaded file is touched: the
shipped `Params()` defaults, `live/*`, `champion.json`'s stats and all three scheduled tasks
are untouched, so no deploy gate and no `--replay` is owed. The one write this iteration may
earn is a LABEL correction, which is AUD-11's own second option.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import sys
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

#: clause 1 - the cell six previous iterations agree on
S25_DEPLOYED_CAR = 22.192150170492255
S25_DEPLOYED_ORDERS = 5052

#: clause 2 - the three axes, each grid copied from the signals.py docstring that records
#: how the shipped value was chosen. `None` marks the shipped value on each axis.
AXES = {
    "mom_skip": (2, 3, 5, 8, 10, 15, 20),
    "alloc_vol_window": (10, 20, 21, 30, 40, 60),
    "mom_lb4": (150, 220, 250, 252, 280, 300, 320),
}
SHIPPED = {"mom_skip": 5, "alloc_vol_window": 21, "mom_lb4": 252}

#: clause 6 - S-22's honest historical book
SPREAD_BPS = 2.0


def make_params(**over) -> sig.Params:
    """The shipped Params with one or more of the three axes moved."""
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


def run(frames: dict, over: dict, window: str, *, spread: float = 0.0,
        fin: dict | None = None) -> pd.DataFrame:
    s, e = WINDOWS[window]
    return legs_simulate(frames, make_params(**over), "both", s, e, spread, fin)


def spearman(a, b) -> float:
    """Rank correlation without scipy; ties averaged."""
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    if ra.std(ddof=1) == 0 or rb.std(ddof=1) == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


# --------------------------------------------------------------------------------- ledger

def record(rows: list[dict], no_record: bool) -> None:
    if no_record:
        return
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with LEDGER.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({
                "ts": stamp, "algorithm": "daily/s33_oos", "class": "book",
                "tag": f"S-33 {r['cell']} @ {r['window']} ({r.get('note', '')})",
                "commit": "", "run_dir": "",
                "track": "S-33", "start": r["start"], "end": r["end"],
                "stats": {"Sessions": str(r["sessions"]),
                          "Total Orders": str(r["orders"]),
                          "Compounding Annual Return": f"{r['CAR']:.4f}%",
                          "Sharpe Ratio": f"{r['Sharpe']:.3f}",
                          "Drawdown": f"{r['MaxDD']:.3f}%",
                          "Annual Standard Deviation": f"{r['std']:.3f}",
                          "Total Fees": f"${r['fees']:.2f}",
                          "End Equity": f"{r['end_equity']:.2f}"}}, default=str) + "\n")


# ---------------------------------------------------------------------------- the clauses

def clause_1(frames: dict) -> tuple[bool, list[dict]]:
    print("=== clause 1: identity - is this the deployed book? ===")
    d = describe(run(frames, {}, "FULL"), "shipped @ FULL")
    ok = (abs(d["CAR"] - S25_DEPLOYED_CAR) < 1e-9
          and d["orders"] == S25_DEPLOYED_ORDERS)
    print(f"  shipped Params, 2012-2026, 0 bp   CAR {d['CAR']:.6f}%   orders {d['orders']:,}")
    print(f"  S-25..S-32's deployed cell        CAR {S25_DEPLOYED_CAR:.6f}%   "
          f"orders {S25_DEPLOYED_ORDERS:,}")
    print(f"  -> {'MATCH' if ok else 'MISMATCH'}\n")
    d.update(window="FULL", start=START, end=END, cell="shipped")
    return ok, [d]


def clause_2(frames: dict) -> tuple[dict, list[dict]]:
    """The coordinate grid on all three windows. This is the expensive part."""
    print("=== clause 2: the selection record re-run, per axis, zero cost ===")
    print("  IS CAR is what the selection SHOULD have been read on; FULL CAR is what it WAS")
    print("  read on; OOS CAR is the withheld half, read once.\n")
    grid: dict[str, list[dict]] = {}
    rows: list[dict] = []
    cache: dict[tuple, dict] = {}

    for axis, values in AXES.items():
        print(f"--- {axis} " + "-" * (68 - len(axis)))
        hdr = (f"{axis:>18}{'IS CAR%':>10}{'FULL CAR%':>11}{'OOS CAR%':>10}"
               f"{'OOS Sharpe':>12}{'OOS DD%':>9}{'OOS ord':>9}")
        print(hdr)
        print("-" * len(hdr))
        cells = []
        for v in values:
            over = {} if v == SHIPPED[axis] else {axis: v}
            key = tuple(sorted(over.items()))
            if key not in cache:
                c = {}
                for w in ("IS", "FULL", "OOS"):
                    d = describe(run(frames, over, w), cell_name(over))
                    s, e = WINDOWS[w]
                    d.update(window=w, start=s, end=e, cell=cell_name(over))
                    c[w] = d
                    rows.append(d)
                cache[key] = c
            c = cache[key]
            mark = " *" if v == SHIPPED[axis] else "  "
            print(f"{str(v) + mark:>18}{c['IS']['CAR']:>10.3f}{c['FULL']['CAR']:>11.3f}"
                  f"{c['OOS']['CAR']:>10.3f}{c['OOS']['Sharpe']:>12.3f}"
                  f"{c['OOS']['MaxDD']:>9.3f}{c['OOS']['orders']:>9,}")
            cells.append({"axis": axis, "value": v, "shipped": v == SHIPPED[axis],
                          "over": over,
                          "IS": c["IS"]["CAR"], "FULL": c["FULL"]["CAR"],
                          "OOS": c["OOS"]["CAR"], "OOS_sharpe": c["OOS"]["Sharpe"],
                          "OOS_dd": c["OOS"]["MaxDD"]})
        grid[axis] = cells
        print()
    return grid, rows


def clause_3(grid: dict) -> dict:
    """Argmax CAR per axis on each selection window; ties to the shipped value."""
    print("=== clause 3: what each selection window picks ===")
    hdr = f"{'axis':>18}{'shipped':>10}{'FULL picks':>13}{'IS picks':>11}{'moved?':>9}"
    print(hdr)
    print("-" * len(hdr))
    picks = {}
    for axis, cells in grid.items():
        best = {}
        for w in ("FULL", "IS"):
            top = max(cells, key=lambda c: (c[w], c["shipped"]))
            best[w] = top["value"]
        picks[axis] = best
        print(f"{axis:>18}{SHIPPED[axis]:>10}{best['FULL']:>13}{best['IS']:>11}"
              f"{('YES' if best['IS'] != SHIPPED[axis] else 'no'):>9}")
    print()
    return picks


def clause_4(frames: dict, grid: dict, picks: dict) -> dict:
    """Read the IS-selected set on the withheld half, once."""
    print("=== clause 4: the withheld half, read once ===")
    is_set = {a: picks[a]["IS"] for a in AXES if picks[a]["IS"] != SHIPPED[a]}
    full_set = {a: picks[a]["FULL"] for a in AXES if picks[a]["FULL"] != SHIPPED[a]}
    out = {"is_set": is_set, "full_set": full_set, "rows": []}

    books = {}
    for name, over in (("shipped", {}), ("IS-selected", is_set), ("FULL-selected", full_set)):
        key = tuple(sorted(over.items()))
        if key in books:
            books[name] = books[key]
            continue
        b = run(frames, over, "OOS")
        books[name] = books[key] = b

    hdr = (f"{'set':<16}{'parameters':<40}{'OOS CAR%':>10}{'Sharpe':>8}"
           f"{'MaxDD%':>8}{'orders':>8}")
    print(hdr)
    print("-" * len(hdr))
    base = None
    for name, over in (("shipped", {}), ("IS-selected", is_set), ("FULL-selected", full_set)):
        d = describe(books[name], f"{name} @ OOS")
        d.update(window="OOS", start=OOS_START, end=END, cell=f"{name} {cell_name(over)}")
        if name == "shipped":
            base = d
        out["rows"].append(d)
        out[name] = d
        print(f"{name:<16}{cell_name(over):<40}{d['CAR']:>10.3f}{d['Sharpe']:>8.3f}"
              f"{d['MaxDD']:>8.3f}{d['orders']:>8,}")

    gap = out["IS-selected"]["CAR"] - base["CAR"]
    print(f"\n  IS-selected minus shipped on the withheld half: {gap:+.3f} CAR points")
    if not is_set:
        branch = ("(a) COSMETIC - IS re-selection lands on the shipped values on every axis; "
                  "the label is wrong, the number is not")
    elif gap < -0.5:
        branch = (f"(b) CONTAMINATED by {-gap:.3f} CAR points - the published OOS is better "
                  "than an honestly-selected set achieves on the same half")
    elif gap > 0.5:
        branch = ("(c) the full-period fit is not even a good fit - an honestly-selected set "
                  "does BETTER on the withheld half")
    else:
        branch = (f"COSMETIC by the pre-registered 0.5 threshold ({gap:+.3f}) - the set moved "
                  "but the number did not")
    print(f"  -> pre-registered branch {branch}\n")
    out["branch"] = branch
    out["gap"] = gap
    out["books"] = books
    return out


def clause_5(grid: dict) -> None:
    """The selection premium: does IS rank predict OOS at all?"""
    print("=== clause 5: the selection premium - does choosing on the first half help? ===")
    hdr = (f"{'axis':>18}{'cells':>7}{'rho(IS,OOS)':>13}{'OOS of IS-argmax':>18}"
           f"{'OOS median cell':>17}{'premium':>10}")
    print(hdr)
    print("-" * len(hdr))
    pooled_is, pooled_oos, premia = [], [], []
    for axis, cells in grid.items():
        iss = [c["IS"] for c in cells]
        oos = [c["OOS"] for c in cells]
        rho = spearman(iss, oos)
        argmax = max(cells, key=lambda c: (c["IS"], c["shipped"]))
        med = float(np.median(oos))
        prem = argmax["OOS"] - med
        premia.append(prem)
        pooled_is += iss
        pooled_oos += oos
        print(f"{axis:>18}{len(cells):>7}{rho:>+13.3f}{argmax['OOS']:>18.3f}"
              f"{med:>17.3f}{prem:>+10.3f}")
    rho_p = spearman(pooled_is, pooled_oos)
    print("-" * len(hdr))
    print(f"{'pooled':>18}{len(pooled_is):>7}{rho_p:>+13.3f}"
          f"{'':>18}{'':>17}{np.mean(premia):>+10.3f}")
    print()
    print("  rho is the Spearman rank correlation between a cell's 2012-2019 CAR and its")
    print("  2020-2026 CAR across that axis. 'premium' is what picking the first half's best")
    print("  cell buys on the second half against picking the axis's MEDIAN cell. A premium")
    print("  near zero means parameter selection on this sleeve carries no out-of-sample")
    print("  content and the honest forward expectation of ANY fitted cell is the median.\n")


def clause_6(frames: dict, out: dict, grid: dict, fin: dict) -> list[dict]:
    """The honest number: the withheld half in S-22's fully-charged cell C."""
    print("=== clause 6: the honest number - the withheld half, fully charged (cell C) ===")
    rows = []
    hdr = (f"{'set':<16}{'parameters':<40}{'OOS CAR%':>10}{'Sharpe':>8}{'MaxDD%':>8}")
    print(hdr)
    print("-" * len(hdr))
    for name, over in (("shipped", {}), ("IS-selected", out["is_set"])):
        d = describe(run(frames, over, "OOS", spread=SPREAD_BPS, fin=fin),
                     f"{name} @ OOS costed")
        d.update(window="OOS", start=OOS_START, end=END,
                 cell=f"cellC {name} {cell_name(over)}")
        rows.append(d)
        print(f"{name:<16}{cell_name(over):<40}{d['CAR']:>10.3f}{d['Sharpe']:>8.3f}"
              f"{d['MaxDD']:>8.3f}")
    oos_all = [c["OOS"] for cells in grid.values() for c in cells]
    charge = rows[0]["CAR"] - out["shipped"]["CAR"]          # the cell-C haircut, in points
    lo, hi = float(np.min(oos_all)), float(np.max(oos_all))
    print(f"\n  the grid's own OOS range at 0 bp is {lo:.3f} .. {hi:.3f} CAR "
          f"(n={len(oos_all)} cells, median {np.median(oos_all):.3f}); the cell-C charge is "
          f"{charge:+.3f} points,")
    print(f"  so the honest fully-charged OOS band of this parameterization is roughly "
          f"{lo + charge:.1f} .. {hi + charge:.1f}%, median {np.median(oos_all) + charge:.1f}%.\n")
    return rows


def clause_7(out: dict) -> None:
    print("=== clause 7: significance, stated rather than discovered ===")
    if not out["is_set"]:
        print("  IS re-selection did not move; there is no pair to test.\n")
        return
    p = paired(out["books"]["IS-selected"], out["books"]["shipped"], "IS-sel", "shipped")
    print(f"  IS-selected minus shipped, 2020-2026, paired daily: "
          f"{p['bps_per_day']:+.3f} bps/day over {p['days']} sessions, t {p['t']:+.2f}")
    print(f"  -> {'past' if abs(p['t']) >= 2 else 'short of'} |t| = 2\n")


# ----------------------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", default="all", choices=["all", "a", "b"])
    ap.add_argument("--no-record", action="store_true")
    args = ap.parse_args()

    params = sig.Params()
    tickers = sig.traded_universe(params)
    frames = load_ohlcv(tickers)
    fin = {"rates": rates.load(), "spread": 0.0}
    print(f"store: {len(tickers)} tickers, {frames['close'].index[0].date()} .. "
          f"{frames['close'].index[-1].date()}")
    print(f"IS {START}..{IS_END}   OOS {OOS_START}..{END}   "
          f"axes {', '.join(AXES)}\n")

    GROSS = "pandas book, 0 bp - DIAGNOSTIC, not promotable"
    COSTED = f"pandas book, {SPREAD_BPS:g} bp + IBKR Pro financing - DIAGNOSTIC, not promotable"

    ok, rows1 = clause_1(frames)
    if not ok:
        print("clause 1 FAILED - this is not the deployed book. Stop.")
        return 1

    grid, rows2 = clause_2(frames)
    if args.stage == "a":
        for r in rows1 + rows2:
            r["note"] = GROSS
        record(rows1 + rows2, args.no_record)
        return 0

    picks = clause_3(grid)
    out = clause_4(frames, grid, picks)
    clause_5(grid)
    rows6 = clause_6(frames, out, grid, fin)
    clause_7(out)

    flat = []
    for r in rows1 + rows2 + out["rows"]:
        r = {k: v for k, v in r.items() if k != "book"}
        r["note"] = GROSS
        flat.append(r)
    for r in rows6:
        r["note"] = COSTED
        flat.append(r)
    record(flat, args.no_record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
