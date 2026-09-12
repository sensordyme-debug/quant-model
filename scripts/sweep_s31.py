#!/usr/bin/env python
"""S-31: the margin-budget frontier, re-priced on the book the owner actually owns.

    python scripts/sweep_s31.py --stage a     # clauses 1-2: identity and the LEAN calibration
    python scripts/sweep_s31.py --stage b     # clauses 3-5: the frontier, the halves, the gains
    python scripts/sweep_s31.py --stage c     # clauses 6-7: the inverse solve and the ceiling
    python scripts/sweep_s31.py --no-record   # do not append to the ledger

WHY THIS IS NOT A LEVER AND NOT A CANDIDATE. The backlog's own instruction as of the
2026-09-12 review is to stop finding levers and say that the binding constraint on this
repository is the six owner decisions in `BLOCKERS.md`. This iteration does not add a
seventh. It re-prices the LARGEST of the six - the `margin_budget` size question, open since
2026-09-10 as options (a)/(b)/(c)/(d+) - on the scale S-22 established and every table in
`BLOCKERS.md` predates.

Every number the owner has ever been shown for that decision is on a book that pays none of
the three costs S-17/S-19/S-21 measured:

    S-16's table   0.75 / 0.78 / 0.80 / 0.82 -> 24.403 / 25.307 / 25.903 / 26.474
                   LEAN, zero spread, zero financing, the backtest's clock.
    S-21's table   0.75 / 0.80 / 0.82        -> 23.087 / 24.296 / 24.742
                   financing charged, still zero spread and still the backtest's clock.
    S-22's finding the deployed book charged all three earns 19.640%, not 24.403%.
                   The headline is about 18% high, and `champion.json` says so.

So the owner is being asked to spend a Reg-T buffer against a gain quoted on a book that does
not exist. The correction cannot be a parallel shift, either, which is the whole reason this
is worth a run rather than an assertion: the financing drag is proportional to the DEBIT
BALANCE and the spread bill is proportional to TURNOVER, and a larger budget raises both. A
gain of +1.50 CAR points quoted with the borrowing free is mechanically smaller once the
borrowing is charged - S-21 already saw +1.500 -> +1.209 at 0.80 with one of the three costs
on - and the Sharpe argument, which is the strongest single sentence in the case for (d+),
thins faster than the return does.

PRE-REGISTERED before the first number, seven clauses
----------------------------------------------------
(1) IDENTITY. At the shipped `margin_budget` 0.75 this harness must reproduce the deployed
    cell to the digit - CAR 22.192150%, 5,052 orders at zero cost - and its fully-charged
    cell must land on the 19.640% that S-22, S-26, S-28 and S-30 all independently quote. If
    either misses, the budget dial changed the book rather than sized it and nothing below
    may be read.

(2) CALIBRATION, AND IT IS THE CLAUSE THIS ITERATION CAN FAIL ON. The decision being priced
    is selected on DRAWDOWN, and this is a pandas harness, so its drawdown must be scored
    against LEAN's own before it is allowed to answer a drawdown question. `sweep_s1.py` is
    on record understating drawdown by +2 points at champion size and by +8 to +10 at 2x
    exposure. The backtest-convention cell of THIS harness (`sweep_s19.simulate`, fill at the
    open, lag 0) is run at budget 0.75 and 0.80 and compared with the two LEAN rows already
    on file: 0.75 -> 24.403% / 0.994 / DD 23.700% (the champion's own run) and 0.80 ->
    25.903% / 1.008 / DD 25.1% (S-16). WRITTEN DOWN FIRST: if the harness's drawdown error
    exceeds 2.0 points at EITHER budget, or if the error GROWS with the budget by more than
    1.0 point between them, the frontier is reported as a ranking only and no budget is
    solved for under a drawdown - because an understated drawdown that worsens with size is
    exactly the bias that would make a too-large budget look safe.

(3) THE FRONTIER. Budgets 0.70 / 0.75 / 0.78 / 0.80 / 0.82 / 0.85 / 0.90 / 1.00, each run in
    four cost cells: (A) the backtest convention at zero cost, which is the scale S-16's
    table is on; (B) the deployed 15:45 convention at zero cost, S-19's scale; (C) the
    deployed convention charged 2 bp of one-way spread and IBKR Pro financing on the historic
    effective fed funds rate, which is the honest historical book; and (D) the same at today's
    3.63% flat benchmark, which is the forward-looking book. 1.00 is the Reg-T corner - an
    unlevered basket at a full budget wants exactly the shipped 2.0x `max_gross_weight` - so
    the frontier is run to its own end rather than to a chosen stopping point.

(4) THE DECOMPOSITION IS THE POINT. For every budget, the gain over 0.75 is quoted in all
    four cells side by side, so the owner reads "what you were shown" against "what you would
    get" on one line. EXPECTATION, WRITTEN DOWN SO IT CAN BE WRONG: the gain survives in sign
    and ordering and shrinks by a quarter to a half, most of the shrinkage being financing
    (proportional to the debit, which rises with the budget) and the rest spread (proportional
    to turnover, which also rises). If the ordering instead REVERSES anywhere on the frontier,
    that is a finding about the decision and not about the harness, and it is reported as the
    headline.

(5) HALVES, on cell (C) only. A budget whose advantage is carried by one half of the sample is
    reported as such. Nothing here is expected to reach |t| = 2 - S-21's own frontier did not -
    and the paired statistic against 0.75 is printed with every row so that is visible rather
    than implied.

(6) THE INVERSE, WHICH IS OPTION (c) ANSWERED IN ADVANCE. `BLOCKERS.md` offers the owner
    "name a drawdown you are willing to carry and let the loop solve for the budget under it".
    That is currently an IOU. Solve it for 25% / 30% / 35% on cell (C), on the drawdown the
    harness actually measures plus the calibration error clause 2 finds, and state the answer
    as a range rather than a point. The 35% row is not a preference: it is the one hard limit
    in `champion.json`'s `criteria`.

(7) NOTHING IS PROMOTED AND NOTHING IS SHIPPED. `margin_budget` stays 0.75, no default moves,
    no shipped or runner-loaded file is touched, so no deploy gate is owed. Every ledger row
    is tagged DIAGNOSTIC and not promotable. The deliverable is a table appended to the
    existing size question in `BLOCKERS.md`, because a size decision is the owner's under
    AGENTS.md and this iteration's whole purpose is to make it answerable on the right
    numbers, not to answer it.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "algorithms" / "s1_momo"))
sys.path.insert(0, str(REPO / "scripts"))

import signals as sig                                          # noqa: E402
import rates                                                   # noqa: E402
from lean_prices import load_ohlcv                             # noqa: E402
from sweep_s19 import START_EQUITY, paired, simulate, summarize, tstat   # noqa: E402
from sweep_s25 import legs_simulate                            # noqa: E402

LEDGER = REPO / "research" / "experiments.jsonl"
START = "2012-01-03"
END = "2026-09-04"
HALVES = [("IS 2012-2019", START, "2019-12-31"), ("OOS 2020-2026", "2020-01-02", END)]

SHIPPED_BUDGET = 0.75
BUDGETS = (0.70, 0.75, 0.78, 0.80, 0.82, 0.85, 0.90, 1.00)

#: clause 1 - the two cells four previous iterations agree on
S25_DEPLOYED_CAR = 22.192150170492255
DEPLOYED_COSTED_CAR = 19.640

#: clause 2 - the LEAN rows already on file, zero spread, zero financing, backtest clock
LEAN_REF = {0.75: {"CAR": 24.403, "Sharpe": 0.994, "MaxDD": 23.700, "src": "champion run"},
            0.80: {"CAR": 25.903, "Sharpe": 1.008, "MaxDD": 25.100, "src": "S-16"}}
CAL_TOL_POINTS = 2.0        # clause 2: max permitted drawdown error at either budget
CAL_DRIFT_POINTS = 1.0      # clause 2: max permitted growth of that error with the budget

REG_T_GROSS = 2.0
DD_TARGETS = (25.0, 30.0, 35.0)


# --------------------------------------------------------------------------------- books

def deployed(frames: dict, budget: float, *, spread: float = 0.0, fin: dict | None = None,
             start: str = START, end: str = END) -> pd.DataFrame:
    """The deployed 15:45 convention at a given margin budget."""
    p = replace(sig.Params(), margin_budget=budget)
    return legs_simulate(frames, p, "both", start, end, spread, fin)


def backtest_conv(frames: dict, budget: float, *, spread: float = 0.0,
                  fin: dict | None = None, start: str = START, end: str = END) -> pd.DataFrame:
    """The backtest's own convention - decide on close[i-1], fill at open[i]."""
    p = replace(sig.Params(), margin_budget=budget)
    return simulate(frames, p, 0, "open", start, end, spread, fin)


def describe(book: pd.DataFrame, label: str) -> dict:
    """S-19's summary plus the exposure and borrowing columns a size decision needs."""
    s = summarize(book, label)
    s["gross_x"] = float(book["gross_x"].mean()) if "gross_x" in book else float("nan")
    s["gross_max"] = float(book["gross_x"].max()) if "gross_x" in book else float("nan")
    if "cash" in book and "prev" in book:
        debit = np.minimum(book["cash"].to_numpy(), 0.0) / book["prev"].to_numpy()
        s["debit_x"] = float(-debit.mean())
        s["debit_days"] = float(100.0 * (debit < 0).mean())
    else:
        s["debit_x"] = s["debit_days"] = float("nan")
    if "turnover" in book and "prev" in book:
        s["turnover_x"] = float((book["turnover"] / book["prev"]).mean() * 252)
    else:
        s["turnover_x"] = float("nan")
    return s


def table(rows: list[dict], *, exposure: bool = True) -> None:
    hdr = (f"{'cell':<26}{'sess':>6}{'CAR%':>9}{'Sharpe':>8}{'MaxDD%':>8}{'std':>7}"
           f"{'orders':>8}{'fees':>10}")
    if exposure:
        hdr += f"{'gross':>7}{'maxgr':>7}{'debit':>7}{'turn/yr':>9}"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        line = (f"{r['cell']:<26}{r['sessions']:>6}{r['CAR']:>9.3f}{r['Sharpe']:>8.3f}"
                f"{r['MaxDD']:>8.3f}{r['std']:>7.3f}{r['orders']:>8,}{r['fees']:>10,.0f}")
        if exposure:
            line += (f"{r['gross_x']:>7.2f}{r['gross_max']:>7.2f}{r['debit_x']:>7.2f}"
                     f"{r['turnover_x']:>9.1f}")
        print(line)


# --------------------------------------------------------------------------------- ledger

def record(rows: list[dict], note: str, no_record: bool) -> None:
    if no_record:
        return
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with LEDGER.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({
                "ts": stamp, "algorithm": "daily/s31_budget", "class": "book",
                "tag": f"S-31 {r['cell'].strip()} ({r.get('note', note)})",
                "commit": "", "run_dir": "",
                "track": "S-31", "start": r.get("start", START), "end": r.get("end", END),
                "stats": {"Sessions": str(r["sessions"]),
                          "Total Orders": str(r["orders"]),
                          "Compounding Annual Return": f"{r['CAR']:.3f}%",
                          "Sharpe Ratio": f"{r['Sharpe']:.3f}",
                          "Drawdown": f"{r['MaxDD']:.3f}%",
                          "Annual Standard Deviation": f"{r['std']:.3f}",
                          "Total Fees": f"${r['fees']:.2f}",
                          "End Equity": f"{r['end_equity']:.2f}"}}, default=str) + "\n")


# ---------------------------------------------------------------------------- the clauses

def clause_1(frames: dict, fin_hist: dict, spread: float) -> tuple[bool, list[dict]]:
    print("=== clause 1: does the budget dial size the deployed book, or change it? ===")
    b0 = deployed(frames, SHIPPED_BUDGET)
    d0 = describe(b0, "budget 0.75 @ 0bp")
    ok_gross = abs(d0["CAR"] - S25_DEPLOYED_CAR) < 1e-9 and d0["orders"] == 5052
    print(f"  shipped budget, zero cost      CAR {d0['CAR']:.6f}%   orders {d0['orders']:,}")
    print(f"  S-25/S-26/S-28/S-30's cell     CAR {S25_DEPLOYED_CAR:.6f}%   orders 5,052")
    print(f"  -> {'MATCH' if ok_gross else 'MISMATCH'}")

    bc = deployed(frames, SHIPPED_BUDGET, spread=spread, fin=fin_hist)
    dc = describe(bc, "budget 0.75 costed")
    ok_costed = abs(dc["CAR"] - DEPLOYED_COSTED_CAR) < 0.01
    print(f"  shipped budget, fully charged  CAR {dc['CAR']:.6f}%   "
          f"Sharpe {dc['Sharpe']:.3f}   DD {dc['MaxDD']:.3f}%")
    print(f"  S-22's independent figure      CAR {DEPLOYED_COSTED_CAR:.3f}%")
    print(f"  -> {'MATCH' if ok_costed else 'MISMATCH'}\n")
    return (ok_gross and ok_costed), [d0, dc]


def clause_2(frames: dict) -> tuple[bool, float, list[dict]]:
    """Score the harness's drawdown against LEAN's at two budgets."""
    print("=== clause 2: is this harness allowed to answer a DRAWDOWN question? ===")
    print("  the backtest-convention cell of this harness against the LEAN rows on file\n")
    rows, errs = [], {}
    for b, ref in LEAN_REF.items():
        d = describe(backtest_conv(frames, b), f"backtest conv @ {b:.2f}")
        err_dd = d["MaxDD"] - ref["MaxDD"]
        err_car = d["CAR"] - ref["CAR"]
        errs[b] = err_dd
        rows.append(d)
        print(f"  budget {b:.2f}  ({ref['src']})")
        print(f"    LEAN     CAR {ref['CAR']:>7.3f}%  Sharpe {ref['Sharpe']:.3f}  "
              f"DD {ref['MaxDD']:>6.3f}%")
        print(f"    harness  CAR {d['CAR']:>7.3f}%  Sharpe {d['Sharpe']:.3f}  "
              f"DD {d['MaxDD']:>6.3f}%")
        print(f"    error    CAR {err_car:>+7.3f}                    DD {err_dd:>+6.3f} points\n")
    worst = max(abs(v) for v in errs.values())
    drift = errs[0.80] - errs[0.75]
    ok = worst <= CAL_TOL_POINTS and abs(drift) <= CAL_DRIFT_POINTS
    print(f"  worst |drawdown error| {worst:.3f} points (limit {CAL_TOL_POINTS:.1f})")
    print(f"  error drift 0.75 -> 0.80 {drift:+.3f} points (limit {CAL_DRIFT_POINTS:+.1f})")
    print(f"  -> clause 2 {'PASSES: a budget may be solved for under a drawdown' if ok else 'FAILS: the frontier is a RANKING ONLY'}\n")
    return ok, errs.get(0.80, float("nan")), rows


def frontier(frames: dict, fin_hist: dict, fin_today: dict, spread: float,
             budgets=BUDGETS) -> dict:
    """Clause 3: every budget in four cost cells."""
    cells = {
        "A backtest, 0bp": lambda b: backtest_conv(frames, b),
        "B deployed, 0bp": lambda b: deployed(frames, b),
        "C deployed, costed": lambda b: deployed(frames, b, spread=spread, fin=fin_hist),
        "D deployed, today": lambda b: deployed(frames, b, spread=spread, fin=fin_today),
    }
    out: dict = {}
    for name, fn in cells.items():
        print(f"--- cell {name} " + "-" * (58 - len(name)))
        rows = []
        for b in budgets:
            bk = fn(b)
            d = describe(bk, f"{name.split()[0]} budget {b:.2f}")
            d["budget"] = b
            d["book"] = bk
            rows.append(d)
        table(rows)
        print()
        out[name] = rows
    return out


def gains(front: dict, budgets=BUDGETS) -> None:
    """Clause 4: what you were shown against what you would get, on one line."""
    print("=== clause 4: the gain over the shipped 0.75, in every cost cell ===")
    base = {n: next(r for r in rows if r["budget"] == SHIPPED_BUDGET)
            for n, rows in front.items()}
    hdr = (f"{'budget':>7}" + "".join(f"{n.split(' ',1)[0]+' CAR':>14}" for n in front)
           + "".join(f"{n.split(' ',1)[0]+' gain':>14}" for n in front) + f"{'haircut':>9}")
    print(hdr)
    print("-" * len(hdr))
    for b in budgets:
        cells = {n: next(r for r in rows if r["budget"] == b) for n, rows in front.items()}
        gain = {n: cells[n]["CAR"] - base[n]["CAR"] for n in front}
        shown, got = gain["A backtest, 0bp"], gain["D deployed, today"]
        hair = (100.0 * (1 - got / shown)) if abs(shown) > 1e-9 else float("nan")
        print(f"{b:>7.2f}" + "".join(f"{cells[n]['CAR']:>14.3f}" for n in front)
              + "".join(f"{gain[n]:>+14.3f}" for n in front)
              + (f"{hair:>8.0f}%" if np.isfinite(hair) else f"{'-':>9}"))
    print("\n  'haircut' is how much of the gain the owner was shown (cell A, S-16's scale)")
    print("  survives once the deployed clock, 2 bp of spread and today's cost of money are")
    print("  all charged (cell D). It is the number this iteration exists to produce.\n")

    print("=== the Sharpe argument, which is what the case for (d+) rests on ===")
    hdr2 = f"{'budget':>7}" + "".join(f"{n.split(' ',1)[0]+' Sharpe':>16}" for n in front)
    print(hdr2)
    print("-" * len(hdr2))
    for b in budgets:
        cells = {n: next(r for r in rows if r["budget"] == b) for n, rows in front.items()}
        print(f"{b:>7.2f}" + "".join(f"{cells[n]['Sharpe']:>16.3f}" for n in front))
    print()


def halves(frames: dict, fin_hist: dict, spread: float, budgets=BUDGETS) -> None:
    """Clause 5: the fully-charged frontier in each half, paired against 0.75."""
    print("=== clause 5: the fully-charged frontier by half, paired against 0.75 ===")
    for label, s, e in HALVES:
        print(f"--- {label} " + "-" * (60 - len(label)))
        base = deployed(frames, SHIPPED_BUDGET, spread=spread, fin=fin_hist, start=s, end=e)
        rows = []
        for b in budgets:
            bk = (base if b == SHIPPED_BUDGET
                  else deployed(frames, b, spread=spread, fin=fin_hist, start=s, end=e))
            d = describe(bk, f"C budget {b:.2f}")
            d["budget"], d["start"], d["end"] = b, s, e
            p = paired(bk, base, "cand", "base")
            d["pair_bps"], d["pair_t"] = p["bps_per_day"], p["t"]
            rows.append(d)
        hdr = (f"{'budget':>7}{'CAR%':>9}{'Sharpe':>8}{'MaxDD%':>8}{'std':>7}"
               f"{'vs 0.75 bps/day':>17}{'t':>7}")
        print(hdr)
        print("-" * len(hdr))
        for r in rows:
            print(f"{r['budget']:>7.2f}{r['CAR']:>9.3f}{r['Sharpe']:>8.3f}{r['MaxDD']:>8.3f}"
                  f"{r['std']:>7.3f}{r['pair_bps']:>+17.3f}{r['pair_t']:>+7.2f}")
        print()


def inverse(front: dict, cal_err: float, cal_ok: bool) -> None:
    """Clause 6: the budget that fits under a named drawdown."""
    print("=== clause 6: option (c) answered in advance - the budget under a named drawdown ===")
    rows = sorted(front["C deployed, costed"], key=lambda r: r["budget"])
    if not cal_ok:
        print("  clause 2 FAILED, so this is a RANKING and not a solve. Printed for ordering only.")
    print(f"  the harness's own drawdown is adjusted by the clause-2 calibration error "
          f"({cal_err:+.3f} points at budget 0.80)\n")
    hdr = (f"{'budget':>7}{'CAR%':>9}{'Sharpe':>8}{'DD harness':>12}{'DD adjusted':>13}"
           f"{'max gross':>11}{'Reg-T':>8}")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        adj = r["MaxDD"] - cal_err        # cal_err is harness minus LEAN, so subtract it
        regt = "ok" if r["gross_max"] <= REG_T_GROSS + 1e-9 else "OVER"
        print(f"{r['budget']:>7.2f}{r['CAR']:>9.3f}{r['Sharpe']:>8.3f}{r['MaxDD']:>12.3f}"
              f"{adj:>13.3f}{r['gross_max']:>11.2f}{regt:>8}")
    print()
    for tgt in DD_TARGETS:
        fits = [r for r in rows if (r["MaxDD"] - cal_err) <= tgt
                and r["gross_max"] <= REG_T_GROSS + 1e-9]
        if not fits:
            print(f"  drawdown <= {tgt:.0f}%  ->  no budget on the frontier fits")
            continue
        best = max(fits, key=lambda r: r["budget"])
        base = next(r for r in rows if r["budget"] == SHIPPED_BUDGET)
        print(f"  drawdown <= {tgt:.0f}%  ->  budget {best['budget']:.2f}   "
              f"CAR {best['CAR']:.3f}% ({best['CAR'] - base['CAR']:+.3f} over the shipped 0.75)"
              f"   Sharpe {best['Sharpe']:.3f}   adjusted DD {best['MaxDD'] - cal_err:.2f}%")
    print()


# ----------------------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default=START)
    ap.add_argument("--end", default=END)
    ap.add_argument("--spread-bps", type=float, default=2.0)
    ap.add_argument("--stage", default="a", choices=["all", "a", "b", "c"])
    ap.add_argument("--no-record", action="store_true")
    args = ap.parse_args()

    params = sig.Params()
    tickers = sig.traded_universe(params)
    frames = load_ohlcv(tickers)
    fin_hist = {"rates": rates.load(), "spread": 0.0}
    fin_today = {"rates": rates.load(REPO / "data" / "rates" / "usd_flat_2026.csv"),
                 "spread": 0.0}
    print(f"store: {len(tickers)} tickers, {frames['close'].index[0].date()} .. "
          f"{frames['close'].index[-1].date()}")
    print(f"window {args.start} .. {args.end}   spread {args.spread_bps:g} bp one way   "
          f"budgets {', '.join(f'{b:.2f}' for b in BUDGETS)}\n")

    GROSS = f"pandas book, {args.start}..{args.end}, 0 bp - DIAGNOSTIC, not promotable"
    COSTED = (f"pandas book, {args.start}..{args.end}, {args.spread_bps:g} bp + IBKR Pro "
              f"financing - DIAGNOSTIC, not promotable")

    stage = args.stage
    ok1, rows1 = clause_1(frames, fin_hist, args.spread_bps)
    if not ok1:
        print("clause 1 FAILED - the budget dial does not reproduce the deployed book. Stop.")
        return 1
    cal_ok, cal_err, rows2 = clause_2(frames)
    if stage == "a":
        record(rows1 + rows2, GROSS, args.no_record)
        return 0

    front = frontier(frames, fin_hist, fin_today, args.spread_bps)
    gains(front)
    if stage in ("b", "all"):
        halves(frames, fin_hist, args.spread_bps)
    inverse(front, cal_err, cal_ok)

    flat = []
    for name, rows in front.items():
        for r in rows:
            r = dict(r)
            r.pop("book", None)
            r["note"] = COSTED if name.startswith(("C", "D")) else GROSS
            flat.append(r)
    record(rows1 + rows2 + flat, GROSS, args.no_record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
