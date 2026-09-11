#!/usr/bin/env python
"""S-22: the three instrument corrections charged together, and what the deployed daily
book should honestly be expected to earn.

S-17, S-19 and S-21 each audited the harness rather than the strategy, and each priced ONE
defect against a clean control: no spread on any fill, a runner acting on a signal one
session later than the backtest, and a margin loan that has never been charged interest.
Each was reported alone. Nobody has charged them at once, and the owner has never been
given a single number for the deployed book.

Three reasons the composite is not the sum of the parts:
  (a) a staler signal changes WHICH trades fire, so it moves the spread bill;
  (b) financing is charged on a cash path that the other two corrections both move;
  (c) CAR is geometric, so points do not add.

Two halves, because LEAN can express two of the three corrections exactly and not the third:

  --report  reads the ledger and prints the 2^3 factorial of {spread, financing, clock
            bound} as LEAN ran it, against the multiplicative null of the three singles.
            The residual is the interaction, and the pre-registered test in
            scripts/_s22_runs.sh is whether it exceeds 0.5 CAR points.

  --book    runs the S-19 pandas book, which fills wherever it is told, with the S-22
            financing hook switched on. That is the only harness that can price the
            deployed 15:45 convention (decide on close[i-1], fill at close[i]), which LEAN
            cannot express on daily bars. It is only readable if it reproduces LEAN's own
            financing drag at the backtest convention, which is printed first.

Nothing here is a candidate. Every cell charges a cost the control does not, so every cell
must lose; `evaluate.py` is not the judge and already refuses S1_FINANCING=on runs as not
comparable. The output belongs in champion.json and BLOCKERS.md as a recorded expectation.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "algorithms" / "s1_momo"))
sys.path.insert(0, str(REPO / "scripts"))

import signals as sig                                   # noqa: E402
import rates                                            # noqa: E402
from lean_prices import load_ohlcv                      # noqa: E402
from sweep_s19 import simulate, summarize, paired, tstat  # noqa: E402

LEDGER = REPO / "research" / "experiments.jsonl"
START, END = "2012-01-03", "2026-09-04"

#: the three corrections, in the order they are printed
AXES = ("spread", "financing", "clock")
#: env keys a cell may carry and still be one of the 2^3 full-period factorial cells
ALLOWED = {"S1_NOOP", "S1_SLIPPAGE_BPS", "S1_FINANCING", "S1_SIGNAL_LAG"}


def pct(s) -> float:
    return float(str(s).replace("%", "").replace("$", "").replace(",", ""))


# --------------------------------------------------------------------------- the ledger

def cell_key(env: dict) -> tuple | None:
    """(spread_bps, financing, lag) for a full-period cell, or None if it is not one."""
    if set(env) - ALLOWED:
        return None
    return (float(env.get("S1_SLIPPAGE_BPS", 0.0)),
            env.get("S1_FINANCING", "off").lower() == "on",
            int(env.get("S1_SIGNAL_LAG", 0)))


def load_cells() -> dict:
    """Most recent s1_momo run per factorial cell, plus the named S-22 extras."""
    cells, extras = {}, {}
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("algorithm") != "s1_momo" or not r.get("stats"):
            continue
        env, tag = r.get("env", {}) or {}, r.get("tag", "")
        key = cell_key(env)
        if key is not None:
            cells[key] = r
        if tag.startswith("S-22") and ("forward" in tag or " IS " in tag or " OOS " in tag
                                       or tag.endswith("IS 2012-2019")
                                       or tag.endswith("OOS 2020-2026")):
            extras[tag] = r
    return cells, extras


def row(r: dict) -> dict:
    s = r["stats"]
    return {"ts": r["ts"], "orders": int(s["Total Orders"]),
            "CAR": pct(s["Compounding Annual Return"]),
            "Sharpe": float(s["Sharpe Ratio"]), "DD": pct(s["Drawdown"]),
            "std": float(s["Annual Standard Deviation"]),
            "fees": pct(s["Total Fees"])}


def report() -> dict:
    cells, extras = load_cells()
    base_key = (0.0, False, 0)
    if base_key not in cells:
        print("no control cell in the ledger - run scripts/_s22_runs.sh first")
        return {}
    base = row(cells[base_key])

    order = [(0.0, False, 0), (2.0, False, 0), (0.0, True, 0), (0.0, False, 1),
             (2.0, True, 0), (2.0, False, 1), (0.0, True, 1), (2.0, True, 1)]
    names = {(0.0, False, 0): "control (as promoted)",
             (2.0, False, 0): "spread 2 bp            (S-17/S-18)",
             (0.0, True, 0): "financing              (S-21)",
             (0.0, False, 1): "clock bound  lag1      (S-19)",
             (2.0, True, 0): "spread + financing",
             (2.0, False, 1): "spread + clock",
             (0.0, True, 1): "financing + clock",
             (2.0, True, 1): "ALL THREE"}

    print(f"{'cell':<38}{'CAR%':>9}{'drag':>8}{'Sharpe':>8}{'MaxDD%':>8}{'std':>7}"
          f"{'orders':>8}{'fees $':>10}   run")
    print("-" * 112)
    got = {}
    for k in order:
        if k not in cells:
            print(f"{names[k]:<38}{'(missing)':>9}")
            continue
        v = row(cells[k])
        got[k] = v
        print(f"{names[k]:<38}{v['CAR']:>9.3f}{v['CAR'] - base['CAR']:>+8.3f}"
              f"{v['Sharpe']:>8.3f}{v['DD']:>8.2f}{v['std']:>7.3f}{v['orders']:>8,}"
              f"{v['fees']:>10,.0f}   {v['ts']}")

    # --- the pre-registered test: are the three corrections independent?
    print("\ncomposition test (pre-registered in scripts/_s22_runs.sh):")
    singles = [(2.0, False, 0), (0.0, True, 0), (0.0, False, 1)]
    if all(k in got for k in singles) and (2.0, True, 1) in got:
        f = [(1 + got[k]["CAR"] / 100) / (1 + base["CAR"] / 100) for k in singles]
        mult = 100 * ((1 + base["CAR"] / 100) * np.prod(f) - 1)
        add = base["CAR"] + sum(got[k]["CAR"] - base["CAR"] for k in singles)
        meas = got[(2.0, True, 1)]["CAR"]
        print(f"  multiplicative null (the three singles composed)   {mult:8.3f}%")
        print(f"  additive null       (the three drags summed)       {add:8.3f}%")
        print(f"  MEASURED triple                                    {meas:8.3f}%")
        print(f"  interaction, measured - multiplicative             {meas - mult:+8.3f} points"
              f"   -> {'INDEPENDENT' if abs(meas - mult) <= 0.5 else 'INTERACTION'}"
              f" (rule: |x| <= 0.5)")
        for k in [(2.0, True, 0), (2.0, False, 1), (0.0, True, 1)]:
            if k not in got:
                continue
            a, b = ([(2.0, False, 0), (0.0, True, 0)] if k == (2.0, True, 0) else
                    [(2.0, False, 0), (0.0, False, 1)] if k == (2.0, False, 1) else
                    [(0.0, True, 0), (0.0, False, 1)])
            fm = 100 * ((1 + base["CAR"] / 100)
                        * (1 + got[a]["CAR"] / 100) / (1 + base["CAR"] / 100)
                        * (1 + got[b]["CAR"] / 100) / (1 + base["CAR"] / 100) - 1)
            print(f"  pair {names[k]:<34}{got[k]['CAR']:8.3f}%  null {fm:7.3f}%"
                  f"  interaction {got[k]['CAR'] - fm:+7.3f}")
    if extras:
        print("\nnamed S-22 cells (halves and the forward-rate scenario):")
        for tag, r in extras.items():
            v = row(r)
            print(f"  {tag:<62}{v['CAR']:>8.3f}%  Sharpe {v['Sharpe']:>6.3f}  "
                  f"DD {v['DD']:>6.2f}%  {v['ts']}")
    return {"base": base, "cells": got, "extras": extras}


# ----------------------------------------------------------------------------- the book

CONVENTIONS = [("backtest / pre-open fix", 0, "open"),
               ("deployed 15:45 runner", 0, "close"),
               ("lag1 (LEAN's bound)", 1, "open")]


def book_table(rows: list[dict]) -> None:
    hdr = (f"{'cell':<46}{'sess':>6}{'CAR%':>9}{'Sharpe':>8}{'MaxDD%':>8}{'std':>7}"
           f"{'orders':>8}{'fees $':>10}{'interest $':>12}")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['cell']:<46}{r['sessions']:>6}{r['CAR']:>9.3f}{r['Sharpe']:>8.3f}"
              f"{r['MaxDD']:>8.3f}{r['std']:>7.3f}{r['orders']:>8,}{r['fees']:>10,.0f}"
              f"{r.get('interest', 0.0):>12,.0f}")


def run_book(spread: float, fin: dict, args) -> dict:
    params = sig.Params()
    frames = load_ohlcv(sig.traded_universe(params))
    print(f"store: {frames['close'].index[0].date()} .. {frames['close'].index[-1].date()}"
          f"   window {args.start} .. {args.end}\n")

    books, rows = {}, []
    for label, lag, fill in CONVENTIONS:
        for tag, sl, fn in [("clean", 0.0, None),
                            ("+ financing", 0.0, fin),
                            (f"+ financing + {spread:g} bp", spread, fin)]:
            b = simulate(frames, params, lag, fill, args.start, args.end, sl, fn)
            name = f"{label:<26} {tag}"
            books[name] = b
            s = summarize(b, name)
            s["interest"] = float(b["interest"].sum())
            rows.append(s)
    book_table(rows)

    car = {r["cell"]: r["CAR"] for r in rows}
    clean = {lbl: car[f"{lbl:<26} clean"] for lbl, _l, _f in CONVENTIONS}
    full = {lbl: car[f"{lbl:<26} + financing + {spread:g} bp"] for lbl, _l, _f in CONVENTIONS}
    bt = CONVENTIONS[0][0]

    print("\ncross-harness check, the only thing that makes the deployed row readable:")
    fin_only = car[f"{bt:<26} + financing"]
    print(f"  this book, backtest convention: financing costs "
          f"{fin_only - clean[bt]:+.3f} CAR points ({clean[bt]:.3f} -> {fin_only:.3f})")
    print("  LEAN, same cell (S-21):         financing costs   -1.316 CAR points "
          "(24.403 -> 23.087)")

    print("\nthe number this script exists to produce:")
    for lbl, _l, _f in CONVENTIONS:
        print(f"  {lbl:<26} clean {clean[lbl]:7.3f}%   fully charged {full[lbl]:7.3f}%"
              f"   drag {full[lbl] - clean[lbl]:+7.3f}")

    print(f"\npaired daily return difference against '{bt} clean' (bps/day):")
    for lbl, _l, _f in CONVENTIONS:
        p = paired(books[f"{lbl:<26} + financing + {spread:g} bp"],
                   books[f"{bt:<26} clean"], lbl, bt)
        print(f"  {lbl:<26} fully charged  {p['bps_per_day']:>+8.3f}  t {p['t']:>+6.2f}"
              f"  ({p['days']} days)")

    return {"rows": rows, "books": books, "clean": clean, "full": full}


def record(rows: list[dict], spread: float, rate_src: str = "usd_benchmark") -> None:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with LEDGER.open("a", encoding="utf-8") as f:
        for r in rows:
            rec = {"ts": stamp, "algorithm": "daily/s22_composite", "class": "book",
                   "tag": f"S-22 {r['cell'].strip()} (pandas book, shared signals.py, "
                          f"IBKR Pro financing on {rate_src}, {spread:g} bp spread)",
                   "commit": "", "run_dir": "", "track": "S-22",
                   "stats": {"Sessions": str(r["sessions"]),
                             "Total Orders": str(r["orders"]),
                             "Compounding Annual Return": f"{r['CAR']:.3f}%",
                             "Sharpe Ratio": f"{r['Sharpe']:.3f}",
                             "Drawdown": f"{r['MaxDD']:.3f}%",
                             "Annual Standard Deviation": f"{r['std']:.3f}",
                             "Total Fees": f"${r['fees']:.2f}",
                             "Financing": f"${r.get('interest', 0.0):.2f}",
                             "End Equity": f"{r['end_equity']:.2f}"}}
            f.write(json.dumps(rec, default=str) + "\n")
    print(f"\n{len(rows)} rows appended to {LEDGER.relative_to(REPO)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", action="store_true", help="the LEAN 2^3 factorial")
    ap.add_argument("--book", action="store_true", help="the pandas book, deployed clock")
    ap.add_argument("--start", default=START)
    ap.add_argument("--end", default=END)
    ap.add_argument("--spread-bps", type=float, default=2.0)
    ap.add_argument("--fin-spread", type=float, default=0.0)
    ap.add_argument("--fin-rates", default="data/rates/usd_benchmark.csv")
    ap.add_argument("--no-record", action="store_true")
    args = ap.parse_args()
    if not (args.report or args.book):
        args.report = args.book = True

    if args.report:
        report()
    if args.book:
        path = Path(args.fin_rates)
        if not path.is_absolute():
            path = REPO / path
        fin = {"rates": rates.load(path), "spread": args.fin_spread}
        print(f"\n\nthe pandas book (S-19's, with the S-22 financing hook): "
              f"{len(fin['rates']):,} benchmark days, spread shift {args.fin_spread:+.2f}pp\n")
        out = run_book(args.spread_bps, fin, args)
        if not args.no_record:
            record(out["rows"], args.spread_bps, path.stem)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
