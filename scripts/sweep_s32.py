#!/usr/bin/env python
"""S-32: the execution no-trade band, re-priced on the book the owner actually owns.

    python scripts/sweep_s32.py --stage a     # clauses 1-2: identity and the premise
    python scripts/sweep_s32.py --stage b     # clauses 3-7: the grid, the halves, the placebo
    python scripts/sweep_s32.py --no-record   # do not append to the ledger

WHY THIS IS NOT A LEVER AND NOT A CANDIDATE. The backlog's instruction since the 2026-09-12
review is to stop finding levers and say that the binding constraint on this repository is
the owner decisions in `BLOCKERS.md`; S-31 established the pattern for a day on which neither
standing measurement job can advance (both ran first today, Saturday, and neither has new
input) - RE-PRICE AN OPEN OWNER DECISION ON THE HONEST SCALE rather than open a new research
track. This iteration does that for the one remaining decision that is pure execution: the
no-trade band, open since 2026-09-09.

    "Decision needed: should `scripts/paper_trade.py` run a wider band (0.03 or 0.08) than
     the backtest's 0.01?"  -- BLOCKERS.md, 2026-09-09

Everything the owner has been shown about it is on a book that pays no financing and fills on
the backtest's clock:

    S-13   0.01 -> 0.08 walks CAR 24.40 / 24.35 / 24.54 / 24.34 / 23.92 / 24.47 with no
           trend while orders fall 4,735 -> 1,727, i.e. 63% of the champion's orders are
           return-neutral. LEAN, zero spread, zero financing, the backtest's clock, and on
           the RETIRED S-12 champion.
    S-18   on the current champion, band 0.03 is worth +0.064 CAR at 0 bp and +0.103 at 2 bp.
           Still LEAN, still no financing, still the backtest's clock.

That is the wrong scale for this particular question, and not for S-31's reason. A band is a
TURNOVER lever and nothing else: it buys back spread. Charging zero spread therefore prices
the one thing the band is for at zero, which is why S-13 could find "no trend" - and the
owner's own note says so in as many words ("in LEAN that is worth only the $6.1k of
commission ... live it is worth more than that, because LEAN charges commission but models no
spread at all"). S-32 charges it, on the deployed 15:45 convention, with the borrowing, and
at the execution cost the live account has actually measured.

PRE-REGISTERED before the first number, seven clauses
----------------------------------------------------
(1) IDENTITY. At the shipped band 0.01 this harness must reproduce the deployed cell to the
    digit - CAR 22.192150%, 5,052 orders at zero cost - and its fully-charged cell must land
    on the 19.640% that S-22, S-26, S-28, S-30 and S-31 all independently quote. If either
    misses, the band argument changed the book rather than filtered its orders.

(2) THE PREMISE, AND THE CLAUSE THIS ITERATION CAN FAIL ON. If a band buys back spread, its
    advantage over the shipped 0.01 must GROW with the spread charged. The grid is run at 0,
    1, 2 and 3.2 bps one way (the last is the live-measured execution cost, `daily_fills.py`,
    +3.2 bps against the auction the runner aims at). WRITTEN DOWN FIRST: if the band that
    wins the decision cell does not have a gain that is monotone non-decreasing across those
    four spreads, the premise is wrong, the result is reported as noise and no band is
    recommended whatever the CAR column says.

(3) THE GRID. Bands 0.000 / 0.005 / 0.010 (shipped) / 0.020 / 0.030 / 0.050 / 0.080 / 0.120,
    each in four cost cells: (A) the deployed convention at zero cost, S-19's scale; (B) the
    same charged 2 bp of one-way spread; (C) THE DECISION CELL - 2 bp plus IBKR Pro financing
    on the historical effective fed funds rate, which is S-22's honest historical book; and
    (D) the same at the live-measured 3.2 bps and today's 3.63% cost of money.

(4) THE RULE, which is `champion.json`'s own and not a new one. A band is RECOMMENDABLE only
    if, in cell C, it beats the shipped 0.01 on CAR, is at most 0.03 Sharpe below it, has a
    drawdown no more than 1.0 point worse and under the 35% absolute limit, AND wins in both
    halves (IS 2012-2019, OOS 2020-2026). Anything short of that is reported and 0.01 stands.
    Note what "recommendable" means here and nowhere else: this is an EXECUTION setting on
    `paper_trade.py`, so it is the owner's call by the 2026-09-09 decision, and the loop
    cannot take it - a wider band moves the live order list off `OrderListHash
    a6d6224ce9c70091e5bfa8e96f046bf3`, which is the baseline `compare_orders.py` gates on.

(5) THE PLACEBO, which decides whether a band is an idea or just less trading. At the winning
    band's own measured skip rate, candidate orders are dropped AT RANDOM with that
    probability (five seeds) while the shipped 0.01 band is left in place. That holds the
    NUMBER of skipped orders fixed and changes only WHICH ones. If random skipping earns as
    much in cell C, the gain is "trade less" and the band's shape is doing nothing.

(6) SIGNIFICANCE, stated rather than discovered. The paired daily return difference against
    the shipped band, full period and both halves, with its t. Nothing on this sleeve has
    reached |t| = 2 except S-31's arithmetic, and this will be said out loud whatever it is.

(7) THE LIVE CONSEQUENCE. What the band would do to the live runner - orders per year, the
    turnover it removes, and the dollar spread bill that turnover carries at the measured
    +3.2 bps - so the owner is answering with the size of the prize in hand.

DIAGNOSTIC. Nothing here is promotable, no shipped or runner-loaded file is touched (the two
new arguments are on the RESEARCH harness `sweep_s25.legs_simulate`, S-26/S-28/S-30's
precedent, and both are inert at their defaults), so no deploy gate and no replay is owed.
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

import signals as sig                                          # noqa: E402
import rates                                                   # noqa: E402
from lean_prices import load_ohlcv                             # noqa: E402
from sweep_s19 import MIN_ORDER_VALUE, paired                   # noqa: E402
from sweep_s25 import legs_simulate                            # noqa: E402
from sweep_s31 import describe                                 # noqa: E402

LEDGER = REPO / "research" / "experiments.jsonl"
START = "2012-01-03"
END = "2026-09-04"
HALVES = [("IS 2012-2019", START, "2019-12-31"), ("OOS 2020-2026", "2020-01-02", END)]

SHIPPED_BAND = MIN_ORDER_VALUE                       # 0.01, main.py's shipped value
BANDS = (0.000, 0.005, 0.010, 0.020, 0.030, 0.050, 0.080, 0.120)

#: clause 1 - the two cells five previous iterations agree on
S25_DEPLOYED_CAR = 22.192150170492255
DEPLOYED_COSTED_CAR = 19.640

#: clause 2 - the spreads the premise is tested across. 3.2 bp is measured, not assumed:
#: `scripts/daily_fills.py`, 10 paper fills over 3 sessions, +3.2 bps against the closing
#: auction the runner aims at (per-fill sd 14.1, se 4.5).
PREMISE_SPREADS = (0.0, 1.0, 2.0, 3.2)
LIVE_SPREAD_BPS = 3.2

#: clause 4 - champion.json's promotion criteria, quoted rather than re-invented
SHARPE_TOL = 0.03
DD_TOL_POINTS = 1.0
DD_ABSOLUTE = 35.0

PLACEBO_SEEDS = (1, 2, 3, 4, 5)


# --------------------------------------------------------------------------------- books

def deployed(frames: dict, band: float, *, spread: float = 0.0, fin: dict | None = None,
             skip: dict | None = None, start: str = START,
             end: str = END) -> pd.DataFrame:
    """The deployed 15:45 convention at a given execution no-trade band."""
    return legs_simulate(frames, sig.Params(), "both", start, end, spread, fin,
                         band=band, skip=skip)


def table(rows: list[dict]) -> None:
    hdr = (f"{'band':>7}{'sess':>6}{'CAR%':>9}{'Sharpe':>8}{'MaxDD%':>8}{'std':>7}"
           f"{'orders':>8}{'fees':>10}{'turn/yr':>9}{'skipped':>9}")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['band']:>7.3f}{r['sessions']:>6}{r['CAR']:>9.3f}{r['Sharpe']:>8.3f}"
              f"{r['MaxDD']:>8.3f}{r['std']:>7.3f}{r['orders']:>8,}{r['fees']:>10,.0f}"
              f"{r['turnover_x']:>9.1f}{r.get('skipped', float('nan')):>8.1f}%")


def skip_rate(rows: list[dict]) -> None:
    """Fill in the share of the shipped band's orders each wider band removes."""
    base = next(r for r in rows if abs(r["band"] - SHIPPED_BAND) < 1e-12)
    for r in rows:
        r["skipped"] = 100.0 * (1.0 - r["orders"] / base["orders"])


# --------------------------------------------------------------------------------- ledger

def record(rows: list[dict], no_record: bool) -> None:
    if no_record:
        return
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with LEDGER.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({
                "ts": stamp, "algorithm": "daily/s32_band", "class": "book",
                "tag": f"S-32 {r['cell'].strip()} ({r.get('note', '')})",
                "commit": "", "run_dir": "",
                "track": "S-32", "start": r.get("start", START), "end": r.get("end", END),
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
    print("=== clause 1: does the band argument filter orders, or change the book? ===")
    b0 = deployed(frames, SHIPPED_BAND)
    d0 = describe(b0, "band 0.010 @ 0bp")
    d0["band"] = SHIPPED_BAND
    ok_gross = abs(d0["CAR"] - S25_DEPLOYED_CAR) < 1e-9 and d0["orders"] == 5052
    print(f"  shipped band, zero cost        CAR {d0['CAR']:.6f}%   orders {d0['orders']:,}")
    print(f"  S-25..S-31's deployed cell     CAR {S25_DEPLOYED_CAR:.6f}%   orders 5,052")
    print(f"  -> {'MATCH' if ok_gross else 'MISMATCH'}")

    dc = describe(deployed(frames, SHIPPED_BAND, spread=spread, fin=fin_hist),
                  "band 0.010 costed")
    dc["band"] = SHIPPED_BAND
    ok_costed = abs(dc["CAR"] - DEPLOYED_COSTED_CAR) < 0.01
    print(f"  shipped band, fully charged    CAR {dc['CAR']:.6f}%   "
          f"Sharpe {dc['Sharpe']:.3f}   DD {dc['MaxDD']:.3f}%")
    print(f"  S-22's independent figure      CAR {DEPLOYED_COSTED_CAR:.3f}%")
    print(f"  -> {'MATCH' if ok_costed else 'MISMATCH'}\n")
    return (ok_gross and ok_costed), [d0, dc]


def clause_2(frames: dict, bands=BANDS) -> tuple[dict, list[dict]]:
    """The premise: a band buys back spread, so its gain must grow with the spread charged.

    Run with NO financing so the only thing moving across a row is the execution cost - the
    financed debit also moves with the band (a skipped buy leaves cash) and mixing the two
    would make a monotone claim untestable.
    """
    print("=== clause 2: does the band's advantage grow with the spread charged? ===")
    print("  deployed convention, no financing, so the only thing moving is execution cost\n")
    grid: dict[float, list[dict]] = {}
    rows_out = []
    for s in PREMISE_SPREADS:
        rows = []
        for b in bands:
            d = describe(deployed(frames, b, spread=s), f"premise {s:.1f}bp band {b:.3f}")
            d["band"], d["spread"] = b, s
            rows.append(d)
        skip_rate(rows)
        grid[s] = rows
        rows_out.extend(rows)

    hdr = f"{'band':>7}{'skipped':>9}" + "".join(f"{f'{s:g}bp gain':>12}" for s in PREMISE_SPREADS)
    print(hdr)
    print("-" * len(hdr))
    for b in bands:
        cells = {s: next(r for r in grid[s] if r["band"] == b) for s in PREMISE_SPREADS}
        base = {s: next(r for r in grid[s] if abs(r["band"] - SHIPPED_BAND) < 1e-12)
                for s in PREMISE_SPREADS}
        line = f"{b:>7.3f}{cells[PREMISE_SPREADS[0]]['skipped']:>8.1f}%"
        line += "".join(f"{cells[s]['CAR'] - base[s]['CAR']:>+12.3f}" for s in PREMISE_SPREADS)
        print(line)
    print("\n  gain = CAR at that band minus CAR at the shipped 0.01, same spread column.")
    print("  The premise predicts every row rises left to right. The clause is decided on")
    print("  the band that wins the decision cell, which is chosen in clause 3.\n")
    return grid, rows_out


def premise_holds(grid: dict, band: float) -> tuple[bool, list[float]]:
    gains = []
    for s in PREMISE_SPREADS:
        rows = grid[s]
        base = next(r for r in rows if abs(r["band"] - SHIPPED_BAND) < 1e-12)
        gains.append(next(r for r in rows if r["band"] == band)["CAR"] - base["CAR"])
    ok = all(gains[i + 1] >= gains[i] - 1e-9 for i in range(len(gains) - 1))
    return ok, gains


def clause_3(frames: dict, fin_hist: dict, fin_today: dict, spread: float,
             grid: dict, bands=BANDS) -> dict:
    """Cells A and B are the 0 bp and `spread` columns clause 2 already ran, reused rather
    than recomputed - identical arguments, so identical books."""
    print("=== clause 3: the band in four cost cells ===")
    cells = {
        "A deployed, 0bp": lambda b: deployed(frames, b),
        "B deployed, 2bp": lambda b: deployed(frames, b, spread=spread),
        "C deployed, 2bp+fin": lambda b: deployed(frames, b, spread=spread, fin=fin_hist),
        "D deployed, live+today": lambda b: deployed(frames, b, spread=LIVE_SPREAD_BPS,
                                                     fin=fin_today),
    }
    reuse = {"A deployed, 0bp": 0.0, "B deployed, 2bp": spread}
    out: dict = {}
    for name, fn in cells.items():
        print(f"--- cell {name} " + "-" * (56 - len(name)))
        rows = []
        src = grid.get(reuse.get(name, -1.0))
        for b in bands:
            if src is not None:
                d = dict(next(r for r in src if r["band"] == b))
                d["cell"] = f"{name.split()[0]} band {b:.3f}"
            else:
                bk = fn(b)
                d = describe(bk, f"{name.split()[0]} band {b:.3f}")
                d["book"] = bk
            d["band"] = b
            rows.append(d)
        skip_rate(rows)
        table(rows)
        print()
        out[name] = rows
    return out


def clause_4(front: dict, bands=BANDS) -> tuple[float, dict]:
    """The decision cell, judged on champion.json's own criteria."""
    print("=== clause 4: the decision cell C, against champion.json's criteria ===")
    rows = front["C deployed, 2bp+fin"]
    base = next(r for r in rows if abs(r["band"] - SHIPPED_BAND) < 1e-12)
    hdr = (f"{'band':>7}{'CAR%':>9}{'gain':>9}{'Sharpe':>8}{'dSharpe':>9}{'MaxDD%':>8}"
           f"{'dDD':>7}{'orders':>8}{'verdict':>28}")
    print(hdr)
    print("-" * len(hdr))
    passing = []
    for r in rows:
        d_car = r["CAR"] - base["CAR"]
        d_sh = r["Sharpe"] - base["Sharpe"]
        d_dd = r["MaxDD"] - base["MaxDD"]
        why = []
        if r["band"] == SHIPPED_BAND:
            why = ["shipped"]
        else:
            if d_car <= 0:
                why.append("CAR")
            if d_sh < -SHARPE_TOL:
                why.append("Sharpe")
            if d_dd > DD_TOL_POINTS:
                why.append("drawdown")
            if r["MaxDD"] > DD_ABSOLUTE:
                why.append("35% limit")
            if not why:
                passing.append(r)
        verdict = "PASSES full period" if not why else "fails: " + ", ".join(why)
        print(f"{r['band']:>7.3f}{r['CAR']:>9.3f}{d_car:>+9.3f}{r['Sharpe']:>8.3f}"
              f"{d_sh:>+9.3f}{r['MaxDD']:>8.3f}{d_dd:>+7.3f}{r['orders']:>8,}"
              f"{verdict:>28}")
    print()
    if not passing:
        print("  NO band passes the full period. The shipped 0.01 stands.\n")
        return float("nan"), base
    win = max(passing, key=lambda r: r["CAR"])
    print(f"  best passing band in the decision cell: {win['band']:.3f} "
          f"({win['CAR'] - base['CAR']:+.3f} CAR, {win['skipped']:.1f}% of orders removed)\n")
    return win["band"], base


def clause_5(frames: dict, fin_hist: dict, spread: float, bands=BANDS) -> None:
    """The halves, paired against the shipped band - clauses 4 (both halves) and 6 (t)."""
    print("=== clauses 4+6: the decision cell by half, paired against the shipped 0.01 ===")
    for label, s, e in HALVES:
        print(f"--- {label} " + "-" * (60 - len(label)))
        base = deployed(frames, SHIPPED_BAND, spread=spread, fin=fin_hist, start=s, end=e)
        d_base = describe(base, "base")
        hdr = (f"{'band':>7}{'CAR%':>9}{'gain':>9}{'Sharpe':>8}{'MaxDD%':>8}"
               f"{'vs 0.01 bps/day':>17}{'t':>7}")
        print(hdr)
        print("-" * len(hdr))
        for b in bands:
            bk = (base if abs(b - SHIPPED_BAND) < 1e-12
                  else deployed(frames, b, spread=spread, fin=fin_hist, start=s, end=e))
            d = describe(bk, f"C half band {b:.3f}")
            p = paired(bk, base, "cand", "base")
            print(f"{b:>7.3f}{d['CAR']:>9.3f}{d['CAR'] - d_base['CAR']:>+9.3f}"
                  f"{d['Sharpe']:>8.3f}{d['MaxDD']:>8.3f}"
                  f"{p['bps_per_day']:>+17.3f}{p['t']:>+7.2f}")
        print()


def clause_6_full(front: dict, bands=BANDS) -> None:
    print("=== clause 6: the full-period paired difference in the decision cell ===")
    rows = front["C deployed, 2bp+fin"]
    base = next(r for r in rows if abs(r["band"] - SHIPPED_BAND) < 1e-12)
    hdr = f"{'band':>7}{'bps/day vs 0.01':>18}{'t':>8}"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        if r["band"] == SHIPPED_BAND:
            continue
        p = paired(r["book"], base["book"], "cand", "base")
        print(f"{r['band']:>7.3f}{p['bps_per_day']:>+18.3f}{p['t']:>+8.2f}")
    print()


def clause_5_placebo(frames: dict, fin_hist: dict, spread: float, front: dict,
                     band: float) -> list[dict]:
    """Random skipping at the winning band's own rate, with the shipped band left in place."""
    print("=== clause 5: the placebo - the same orders removed, chosen at random ===")
    rows = front["C deployed, 2bp+fin"]
    base = next(r for r in rows if abs(r["band"] - SHIPPED_BAND) < 1e-12)
    if not np.isfinite(band):
        band = max((r for r in rows if r["band"] > SHIPPED_BAND),
                   key=lambda r: r["CAR"])["band"]
        print(f"  no band passed clause 4, so the placebo is run at the best wider band "
              f"({band:.3f}) anyway - the question 'shape or volume?' is worth answering "
              f"either way.")
    win = next(r for r in rows if r["band"] == band)
    p = 1.0 - win["orders"] / base["orders"]
    print(f"  band {band:.3f} removes {100 * p:.1f}% of the shipped band's orders "
          f"({base['orders']:,} -> {win['orders']:,}); the placebo removes the same share "
          f"at random\n")
    out = []
    for seed in PLACEBO_SEEDS:
        bk = deployed(frames, SHIPPED_BAND, spread=spread, fin=fin_hist,
                      skip={"p": p, "seed": seed})
        d = describe(bk, f"placebo seed {seed}")
        d["band"], d["seed"] = SHIPPED_BAND, seed
        d["pair"] = paired(bk, base["book"], "cand", "base")
        out.append(d)
    hdr = (f"{'cell':>18}{'CAR%':>9}{'gain':>9}{'Sharpe':>8}{'MaxDD%':>8}{'orders':>8}"
           f"{'bps/day':>10}{'t':>7}")
    print(hdr)
    print("-" * len(hdr))
    print(f"{'band ' + f'{band:.3f}':>18}{win['CAR']:>9.3f}"
          f"{win['CAR'] - base['CAR']:>+9.3f}{win['Sharpe']:>8.3f}{win['MaxDD']:>8.3f}"
          f"{win['orders']:>8,}"
          f"{paired(win['book'], base['book'], 'a', 'b')['bps_per_day']:>+10.3f}"
          f"{paired(win['book'], base['book'], 'a', 'b')['t']:>+7.2f}")
    for d in out:
        print(f"{'random seed ' + str(d['seed']):>18}{d['CAR']:>9.3f}"
              f"{d['CAR'] - base['CAR']:>+9.3f}{d['Sharpe']:>8.3f}{d['MaxDD']:>8.3f}"
              f"{d['orders']:>8,}{d['pair']['bps_per_day']:>+10.3f}{d['pair']['t']:>+7.2f}")
    mean_gain = float(np.mean([d["CAR"] - base["CAR"] for d in out]))
    print(f"\n  random mean gain {mean_gain:+.3f} CAR against the band's "
          f"{win['CAR'] - base['CAR']:+.3f}.")
    print("  If the two are the same, the band's SHAPE is doing nothing and the gain is")
    print("  simply less trading; if the band is clearly better, it is selecting.\n")
    for d in out:
        d.pop("pair", None)
    return out


def clause_7(front: dict, bands=BANDS) -> None:
    """What the band would do to the live runner, in orders and in dollars."""
    print("=== clause 7: the live consequence, at the measured +3.2 bps ===")
    rows = front["C deployed, 2bp+fin"]
    base = next(r for r in rows if abs(r["band"] - SHIPPED_BAND) < 1e-12)
    years = base["sessions"] / 252.0
    hdr = (f"{'band':>7}{'orders/yr':>11}{'removed':>9}{'turn/yr':>9}"
           f"{'turnover removed':>18}{'spread bill saved':>19}")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        d_turn = base["turnover_x"] - r["turnover_x"]
        print(f"{r['band']:>7.3f}{r['orders'] / years:>11.0f}{r['skipped']:>8.1f}%"
              f"{r['turnover_x']:>9.1f}{d_turn:>+18.1f}"
              f"{100 * d_turn * LIVE_SPREAD_BPS / 1e4:>18.3f}%")
    print("\n  'turn/yr' is traded notional as a multiple of equity per year; 'spread bill")
    print("  saved' is that difference charged the live-measured 3.2 bps one way, as a")
    print("  percentage of equity a year. It is the arithmetic upper bound on the prize -")
    print("  the CAR columns above are what survives the tracking error the band introduces.\n")


# ----------------------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default=START)
    ap.add_argument("--end", default=END)
    ap.add_argument("--spread-bps", type=float, default=2.0)
    ap.add_argument("--stage", default="a", choices=["all", "a", "b"])
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
    print(f"window {args.start} .. {args.end}   shipped band {SHIPPED_BAND:g} x equity   "
          f"bands {', '.join(f'{b:.3f}' for b in BANDS)}\n")

    GROSS = f"pandas book, {args.start}..{args.end}, 0 bp - DIAGNOSTIC, not promotable"
    COSTED = (f"pandas book, {args.start}..{args.end}, {args.spread_bps:g} bp + IBKR Pro "
              f"financing - DIAGNOSTIC, not promotable")

    ok1, rows1 = clause_1(frames, fin_hist, args.spread_bps)
    if not ok1:
        print("clause 1 FAILED - the band argument does not reproduce the deployed book. Stop.")
        return 1

    grid, rows2 = clause_2(frames)
    if args.stage == "a":
        for r in rows1 + rows2:
            r["note"] = GROSS
        record(rows1 + rows2, args.no_record)
        return 0

    front = clause_3(frames, fin_hist, fin_today, args.spread_bps, grid)
    # cells A and B ARE the 0 bp and 2 bp premise columns, so those rows are not written twice
    rows2 = [r for r in rows2 if r["spread"] not in (0.0, args.spread_bps)]
    win, base = clause_4(front)
    ok2, gains = premise_holds(grid, win if np.isfinite(win) else 0.03)
    print("=== clause 2, decided ===")
    print(f"  band {(win if np.isfinite(win) else 0.03):.3f} gains "
          + " / ".join(f"{g:+.3f}" for g in gains)
          + f" at {' / '.join(f'{s:g}' for s in PREMISE_SPREADS)} bp")
    print(f"  -> the premise {'HOLDS' if ok2 else 'FAILS'}: the band's advantage "
          f"{'grows' if ok2 else 'does NOT grow'} with the spread charged")
    if not ok2:
        print("  PRE-REGISTERED CONSEQUENCE: the result below is reported as noise and no")
        print("  band is recommended whatever the CAR column says.\n")
    else:
        print()

    clause_6_full(front)
    clause_5(frames, fin_hist, args.spread_bps)
    placebo = clause_5_placebo(frames, fin_hist, args.spread_bps, front, win)
    clause_7(front)

    flat = []
    for name, rows in front.items():
        for r in rows:
            r = dict(r)
            r.pop("book", None)
            r["note"] = COSTED if name.startswith(("C", "D")) else GROSS
            flat.append(r)
    for r in placebo:
        r["note"] = COSTED
    for r in rows1 + rows2:
        r["note"] = GROSS
    record(rows1 + rows2 + flat + placebo, args.no_record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
