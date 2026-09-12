#!/usr/bin/env python
"""S-30: the overnight-only book as a DELTA book - can the equity route pay the equity spread?

    python scripts/sweep_s30.py --stage a        # clauses 1-4: the identity and the arithmetic
    python scripts/sweep_s30.py --stage b        # clause 5: the costed grid (only if a clears)
    python scripts/sweep_s30.py --stage c        # clauses 6-7: placebo and granularity
    python scripts/sweep_s30.py --no-record      # do not append to the ledger

Every result of 2026-09-12 points at one lever and nobody has pulled it. S-25 measured that
94% of the deployed daily book's return and all of its measurable alpha is OVERNIGHT
(+8.103 bps/day at t +6.80 against +0.738 intraday at t +0.47; same-gross selection excess
+3.087 at t +4.20 against -0.314 at t -0.37), while 61% of its variance is the intraday leg
that pays nothing. S-26 tried to remove that leg with a futures overlay - vol-matched h=0.50
earned 20.837% / Sharpe 1.100 against the deployed 19.640 / 1.047 and was REFUSED on
drawdown (26.02 against 24.04 + 1.0), needing owner consent to hold futures in any case.
S-28 tried to re-measure it and was refused by 0.027 CAR points.

The untried route is to shed the intraday leg in the EQUITY book: sell a fraction of the
carried position at the open, hold nothing of it through the session, and let the deployed
close rebalance buy it back. S-25 priced the h=1 corner of that family and refused it hard -
1,248x equity of annual turnover, negative before a cent of cost - but it priced it as a
FULL ROUND TRIP ON EVERY NAME EVERY SESSION (`mode="overnight"` liquidates unconditionally
at the open and reloads the whole target at the close) and its printed turnover was not
growth-normalized, a defect S-26 found and corrected. This iteration prices the same family
the cheap way, through the deployed rebalance, so the close-side buy-back NETS against the
day's rotation and the turnover figure is the one a runner would actually pay.

Read the construction honestly, because the backlog item's wording invites a misreading: a
book that holds NOTHING through the session has no "delta" at the OPEN - the whole carried
position must go, there is nothing to net it against. The only netting available is at the
CLOSE, where one trade re-establishes the day's target instead of a liquidation followed by
a reload. So the "delta book" saving is bounded above by the deployed book's own rebalance
turnover, which is ~0.39x of equity one way. Clause 4 measures exactly what it is worth, and
if it is small the backlog item's premise is wrong and that is written down as wrong.

PRE-REGISTERED before the first number, seven clauses
----------------------------------------------------
(1) IDENTITY, two ways. `flat_frac=0.0` must reproduce S-25's deployed cell to the digit
    (CAR 22.192150%, 5,052 orders) and the leg+cost residual must stay at ~1e-16 of equity.
    Separately, `flat_frac=1.0` must reproduce `mode="overnight"`'s RETURN to within the
    netting it is designed to save - same positions held overnight, same legs - so its
    `ret_on` series must match S-25's overnight book session by session to 1e-12 at zero
    cost. If either fails, the new argument changed the book rather than routing it and
    nothing below may be read.

(2) THE TURNOVER ARITHMETIC COMES FIRST, AND IT IS ALLOWED TO REFUSE THE IDEA ON ITS OWN.
    Before any costed or judged book is run, measure for h = 0.25 / 0.50 / 0.75 / 1.00: the
    gross edge over the deployed book at ZERO cost (paired, bps/day), the realized volatility
    that sets the relever, and the EXTRA turnover per session growth-normalized (S-26's
    correction: divide each session's notional by that session's own equity, never by
    START_EQUITY). The breakeven one-way cost is
        c* = gross edge in bps/day / extra turnover per session in x of equity
    and a costed book is run only if c* > 2.0 bp at some h, which is the spread every other
    daily row in this repository is charged at. THE EXPECTATION, WRITTEN DOWN FIRST SO THE
    RESULT CAN BE WRONG RATHER THAN MERELY REPORTED: refused, and by roughly 1.5x rather than
    by a factor. At h=1 the open flatten trades the book's whole 1.25x gross and the close
    netting can absorb at most the day's ~0.39x rebalance, so extra turnover should land
    near 2.1-2.5x of equity a session; vol-matching an overnight leg of 0.115 annualized to
    the deployed 0.188 permits ~1.6x of relever, which buys perhaps 4-5 bps/day of gross.
    That is c* ~= 1.3-1.5 bp - under the spread, and by a margin narrow enough to be worth
    measuring rather than asserting. If it instead clears 2 bp, this is the only construction
    on file that could deliver S-26's risk reduction with no futures, no owner consent and
    no Reg-T decision, i.e. it would move a refused-on-risk result into the loop's authority.

(3) SAY WHAT IS SOLD BEFORE PRICING WHAT IS BOUGHT (S-26 clause 3, transplanted). The book's
    own intraday leg is +0.738 bps/day at t +0.47 - a return indistinguishable from zero - so
    the construction sells a drift it cannot measure and buys a variance reduction it can.
    Both sides are reported as measurements: the leg means with their t-statistics, and the
    realized annualized volatility of every h book, before any relever is applied.

(4) THE NETTING IS THE WHOLE PREMISE, SO IT IS MEASURED, NOT ASSUMED. `flat_frac=1.0` and
    `mode="overnight"` are the same book reached two ways; the difference in their turnover
    IS the "delta book" saving the backlog item is built on. It is quoted in x equity/yr and
    as a percentage. If it is under 10% of the gross figure, the item's premise is refuted and
    S-25's refusal stands unamended except for the growth-normalization.

(5) ONLY IF (2) CLEARS: the costed grid at 2 bp of one-way equity spread plus IBKR Pro
    financing on the settled balance (S-21's hook), at scale 1 and vol-matched on the real
    machinery to the deployed book's own realized volatility. Promotable only on
    `evaluate.py`'s criteria transplanted here - beat the deployed 19.640% CAR, Sharpe within
    0.03, drawdown no more than 1.0 point worse, never above the 35% absolute limit - in the
    full period AND both halves, with gross inside Reg-T's 2.0x.

(6) PLACEBO, and it is what decides what a pass would mean. The mirror construction - flat
    OVERNIGHT, holding the session - must be materially worse at the same relever, or nothing
    here is about the leg split and the result is a statement about leverage. S-25 already
    priced it unlevered (-3.032% at 0 bp); it is re-priced here vol-matched so the comparison
    is the same comparison the primary gets.

(7) NOTHING HERE IS SHIPPABLE BY THE LOOP EVEN IF IT PASSES, and for a different reason than
    S-26's. This book trades TWICE a session, at 09:30 and at 15:45 ET, so it needs a second
    scheduled execution window and a second preflight - a change to the deployed runner's
    execution, which AGENTS.md puts behind the owner. A pass is evidence for that decision,
    not a deployment. Every row is tagged DIAGNOSTIC and no default moves.
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

import signals as sig                                         # noqa: E402
import rates                                                  # noqa: E402
from lean_prices import load_ohlcv                            # noqa: E402
from sweep_s19 import START_EQUITY, paired, summarize, tstat   # noqa: E402
from sweep_s25 import legs_simulate, identity_check            # noqa: E402

LEDGER = REPO / "research" / "experiments.jsonl"
START = "2012-01-03"
END = "2026-09-04"
HALVES = [("IS 2012-2019", START, "2019-12-31"), ("OOS 2020-2026", "2020-01-02", END)]
S25_DEPLOYED_CAR = 22.192150170492255       # clause 1: S-25's own printed figure
DEPLOYED_COSTED = {"CAR": 19.640, "Sharpe": 1.047, "MaxDD": 24.037}   # S-22/S-26/S-28's cell
REG_T = 2.0
RATIOS = (0.25, 0.50, 0.75, 1.00)
S25_OVERNIGHT_EXCESS = 3.087                # bps/day, same-gross selection excess


# ------------------------------------------------------------------------------- the books

def run(frames: dict, params, *, flat_frac: float = 0.0, mode: str = "both",
        scale: float = 1.0, spread: float = 0.0, fin: dict | None = None,
        start: str = START, end: str = END) -> pd.DataFrame:
    return legs_simulate(frames, params, mode, start, end, spread, fin,
                         scale=scale, flat_frac=flat_frac)


def describe(book: pd.DataFrame, label: str) -> dict:
    """S-19's summary plus the two exposure columns this iteration decides on."""
    s = summarize(book, label)
    s["gross_x"] = float(book["gross_x"].mean())
    s["gross_max"] = float(book["gross_x"].max())
    # S-26's correction: a turnover figure used in a breakeven must be growth-normalized,
    # i.e. each session's notional divided by that session's own equity.
    per_session = (book["turnover"] / book["prev"])
    s["turn_day_x"] = float(per_session.mean())
    s["turnover_x"] = float(per_session.mean() * 252)
    s["on_bps"] = float(1e4 * book["ret_on"].mean())
    s["id_bps"] = float(1e4 * book["ret_id"].mean())
    return s


def table(rows: list[dict]) -> None:
    hdr = (f"{'cell':<28}{'sess':>6}{'CAR%':>9}{'Sharpe':>8}{'MaxDD%':>8}{'std':>7}"
           f"{'gross':>7}{'on bps':>8}{'id bps':>8}{'turn/day':>9}{'turn x/yr':>11}")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['cell']:<28}{r['sessions']:>6}{r['CAR']:>9.3f}{r['Sharpe']:>8.3f}"
              f"{r['MaxDD']:>8.3f}{r['std']:>7.3f}{r['gross_x']:>7.2f}{r['on_bps']:>+8.3f}"
              f"{r['id_bps']:>+8.3f}{r['turn_day_x']:>9.3f}{r['turnover_x']:>11.1f}")


def vol_match(frames: dict, params, target_std: float, *, tol: float = 0.002,
              max_iter: int = 4, **kw) -> tuple[pd.DataFrame, float, list[str]]:
    """Scale the book on the real machinery until its realized vol matches `target_std`."""
    trace = []
    bk = run(frames, params, scale=1.0, **kw)
    s0 = summarize(bk, "x")["std"]
    trace.append(f"scale 1.000 -> std {s0:.4f}")
    k = target_std / s0
    for _ in range(max_iter):
        bk = run(frames, params, scale=k, **kw)
        s = summarize(bk, "x")["std"]
        trace.append(f"scale {k:.3f} -> std {s:.4f}")
        if abs(s - target_std) <= tol * target_std:
            break
        k *= target_std / s
    return bk, k, trace


def breakeven(cand: pd.DataFrame, dep: pd.DataFrame) -> dict:
    """Clause 2: the one-way cost the construction can pay before it falls behind.

    Both books must be run at ZERO cost, so `edge` is gross. The candidate pays the spread
    on `extra` more notional per unit of equity per session than the deployed book does, so
    a one-way cost of `c` bps costs it `c * extra` bps of equity a day.
    """
    p = paired(cand, dep, "cand", "dep")
    extra = float((cand["turnover"] / cand["prev"]).mean()
                  - (dep["turnover"] / dep["prev"]).mean())
    return {"edge_bps": p["bps_per_day"], "t": p["t"], "days": p["days"],
            "extra_turn_day_x": extra, "extra_turn_x_yr": extra * 252,
            "breakeven_bps": (p["bps_per_day"] / extra) if extra > 0 else float("nan")}


# --------------------------------------------------------------------------------- ledger

def record(rows: list[dict], note: str, no_record: bool) -> None:
    if no_record:
        return
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with LEDGER.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({
                "ts": stamp, "algorithm": "daily/s30_delta", "class": "book",
                "tag": f"S-30 {r['cell'].strip()} ({r.get('note', note)})",
                "commit": "", "run_dir": "",
                "track": "S-30", "start": r.get("start", START), "end": r.get("end", END),
                "stats": {"Sessions": str(r["sessions"]),
                          "Total Orders": str(r["orders"]),
                          "Compounding Annual Return": f"{r['CAR']:.3f}%",
                          "Sharpe Ratio": f"{r['Sharpe']:.3f}",
                          "Drawdown": f"{r['MaxDD']:.3f}%",
                          "Annual Standard Deviation": f"{r['std']:.3f}",
                          "Total Fees": f"${r['fees']:.2f}",
                          "End Equity": f"{r['end_equity']:.2f}"}}, default=str) + "\n")


# ----------------------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default=START)
    ap.add_argument("--end", default=END)
    ap.add_argument("--spread-bps", type=float, default=2.0)
    ap.add_argument("--stage", default="a", choices=["all", "a", "b", "c"],
                    help="a = clauses 1-4 (the arithmetic that may refuse it), "
                         "b = clause 5 (the costed grid), c = clauses 6-7")
    ap.add_argument("--force-stage-b", action="store_true",
                    help="run the costed grid even when clause 2 refuses, to quote the "
                         "refusal as a book rather than as an inequality")
    ap.add_argument("--no-record", action="store_true")
    args = ap.parse_args()

    params = sig.Params()
    tickers = sig.traded_universe(params)
    frames = load_ohlcv(tickers)
    fin = {"rates": rates.load(), "spread": 0.0}
    base_kw = dict(start=args.start, end=args.end)
    print(f"store: {len(tickers)} tickers, {frames['close'].index[0].date()} .. "
          f"{frames['close'].index[-1].date()}")
    print(f"window {args.start} .. {args.end}   spread charged in the costed grid "
          f"{args.spread_bps:g} bp one way\n")

    rows: list[dict] = []
    stage = args.stage
    GROSS = f"pandas book, {args.start}..{args.end}, 0 bp gross - DIAGNOSTIC, not promotable"
    COSTED = (f"pandas book, {args.start}..{args.end}, {args.spread_bps:g} bp + IBKR Pro "
              f"financing - DIAGNOSTIC, not promotable")

    # ------------------------------------------------------------- clause 1: the identity
    print("=== clause 1: does `flat_frac` route the deployed book, or change it? ===")
    dep0 = run(frames, params, flat_frac=0.0, **base_kw)
    d0 = describe(dep0, "deployed @ 0bp")
    idc = identity_check(dep0, 0.0)
    same = abs(d0["CAR"] - S25_DEPLOYED_CAR) < 1e-9 and d0["orders"] == 5052
    print(f"  flat_frac=0.0                  CAR {d0['CAR']:.6f}%  orders {d0['orders']:,}")
    print(f"  S-25's own printed cell        CAR {S25_DEPLOYED_CAR:.6f}%  orders 5,052")
    print(f"  leg+cost identity              max |residual| "
          f"{idc['max_resid_frac_of_equity']:.2e} of equity")
    full_window = (args.start, args.end) == (START, END)
    if full_window:
        print(f"  VERDICT: {'PASS' if same else 'FAIL'}"
              f"{'' if same else ' - READ NOTHING BELOW'}")
        if not same:
            return 1

    ovn0 = run(frames, params, mode="overnight", **base_kw)
    f1 = run(frames, params, flat_frac=1.0, **base_kw)
    m = f1[["date", "ret_on"]].merge(ovn0[["date", "ret_on"]], on="date",
                                     suffixes=("_f", "_o"))
    leg_gap = float((m["ret_on_f"] - m["ret_on_o"]).abs().max())
    print(f"  flat_frac=1.0 vs mode='overnight': overnight leg max |difference| "
          f"{leg_gap:.3e} of equity over {len(m)} sessions")
    print(f"  VERDICT: {'PASS' if leg_gap < 1e-12 else 'FAIL'} - the two routes hold the "
          f"same book overnight and differ only in how they get there\n")

    # ------------------------------------------------- clause 3: what is sold, what is bought
    print("=== clause 3: the drift the construction sells, before the variance it buys ===")
    on = 1e4 * dep0["ret_on"].to_numpy()
    idy = 1e4 * dep0["ret_id"].to_numpy()
    print(f"  deployed overnight leg  {on.mean():+7.3f} bps/day  t {tstat(on):+5.2f}")
    print(f"  deployed intraday leg   {idy.mean():+7.3f} bps/day  t {tstat(idy):+5.2f}"
          f"   <- this is what is given up")
    print(f"  leg volatility (annualized): overnight "
          f"{dep0['ret_on'].std(ddof=1) * np.sqrt(252):.3f}  intraday "
          f"{dep0['ret_id'].std(ddof=1) * np.sqrt(252):.3f}  total {d0['std']:.3f}")
    print(f"  same-gross overnight selection excess on record (S-25): "
          f"+{S25_OVERNIGHT_EXCESS:.3f} bps/day at t +4.20\n")

    # ------------------------------------------------- clause 4: what the netting is worth
    print("=== clause 4: is there a 'delta book' at all? ===")
    so, sf = describe(ovn0, "S-25 overnight (reload)"), describe(f1, "flat_frac=1.0 (delta)")
    table([so, sf])
    saving = so["turnover_x"] - sf["turnover_x"]
    pct = 100 * saving / so["turnover_x"] if so["turnover_x"] else float("nan")
    print(f"\n  the delta routing saves {saving:.1f}x equity/yr of turnover, "
          f"{pct:.1f}% of the reload book's {so['turnover_x']:.1f}x")
    print(f"  clause 4 PREMISE: {'SUPPORTED' if pct >= 10 else 'REFUTED'} "
          f"(threshold 10%, pre-registered)")
    print(f"  (and S-25's printed 1,248x was not growth-normalized; the same book, normalized,"
          f"\n   turns over {so['turnover_x']:.1f}x - S-26's correction, a factor of "
          f"{1248 / so['turnover_x']:.1f}x)\n")

    # ---------------------------------------------- clause 2: the arithmetic that decides
    print("=== clause 2: the breakeven arithmetic, at zero cost, before any judgement ===")
    rows += [dict(d0, start=args.start, end=args.end, note=GROSS)]
    gross_books = {0.0: dep0, 1.0: f1}
    for h in RATIOS:
        if h not in gross_books:
            gross_books[h] = run(frames, params, flat_frac=h, **base_kw)
    grid = [describe(gross_books[h], f"flat {h:.2f} @ 0bp") for h in (0.0,) + RATIOS]
    table(grid)
    rows += [dict(g, start=args.start, end=args.end, note=GROSS) for g in grid[1:]]

    print("\n  the relever the variance reduction permits, and what it costs in turnover:")
    hdr = (f"  {'h':>5}{'std':>8}{'relever':>9}{'edge bps/day':>14}{'t':>7}"
           f"{'extra turn/day':>16}{'breakeven bp':>14}{'vs 2 bp':>9}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    tgt_std = d0["std"]
    be_rows = []
    for h in RATIOS:
        bk = gross_books[h]
        s = describe(bk, f"h={h}")
        k = tgt_std / s["std"]
        be = breakeven(bk, dep0)
        # the levered book's gross edge and extra turnover both scale with k to first order;
        # the exact version is clause 5's vol-matched run. Quoted here as the pre-registered
        # arithmetic, which is what decides whether clause 5 runs at all.
        lev_edge = k * (s["on_bps"] + s["id_bps"]) - (d0["on_bps"] + d0["id_bps"])
        lev_extra = k * s["turn_day_x"] - d0["turn_day_x"]
        lev_be = lev_edge / lev_extra if lev_extra > 0 else float("nan")
        be_rows.append({"h": h, "k": k, "be_raw": be["breakeven_bps"], "be_lev": lev_be,
                        "edge": be["edge_bps"], "t": be["t"],
                        "extra": be["extra_turn_day_x"], "lev_edge": lev_edge,
                        "lev_extra": lev_extra, "std": s["std"]})
        print(f"  {h:>5.2f}{s['std']:>8.4f}{k:>9.3f}{be['edge_bps']:>+14.3f}{be['t']:>+7.2f}"
              f"{be['extra_turn_day_x']:>16.3f}{be['breakeven_bps']:>14.3f}"
              f"{'CLEARS' if be['breakeven_bps'] > 2.0 else 'under':>9}")
    print("\n  the same arithmetic AFTER the relever the vol reduction permits "
          "(first-order, exact in clause 5):")
    print(f"  {'h':>5}{'relever':>9}{'levered edge':>14}{'extra turn/day':>16}"
          f"{'breakeven bp':>14}{'vs 2 bp':>9}")
    for r in be_rows:
        print(f"  {r['h']:>5.2f}{r['k']:>9.3f}{r['lev_edge']:>+14.3f}{r['lev_extra']:>16.3f}"
              f"{r['be_lev']:>14.3f}"
              f"{'CLEARS' if r['be_lev'] > 2.0 else 'under':>9}")

    best = max(be_rows, key=lambda r: max(r["be_raw"], r["be_lev"]))
    clears = max(best["be_raw"], best["be_lev"]) > 2.0
    print(f"\n  best breakeven anywhere: {max(best['be_raw'], best['be_lev']):.3f} bps one way "
          f"at h={best['h']:.2f}, against the {args.spread_bps:g} bp every other daily row "
          f"here is charged")
    print(f"  CLAUSE 2 VERDICT: {'CLEARS - clause 5 runs' if clears else 'REFUSED ON THE SPOT'}")
    if not clears:
        print("  The construction pays the equity spread on its own flatten, which is exactly")
        print("  the cost S-26's futures route was invented to avoid: an ES round trip is")
        print("  0.488 bps of notional against 4 bps for a 2 bp equity round trip, ~8x.")

    # --------------------------------------------------------- clause 5: the costed grid
    if stage in ("all", "b") or args.force_stage_b:
        print(f"\n=== clause 5: the costed grid at {args.spread_bps:g} bp + IBKR Pro "
              f"financing ===")
        if not clears:
            print("  (clause 2 refused; this grid is run anyway so the refusal is quoted as a")
            print("   book rather than as an inequality - it cannot promote anything)")
        costed_kw = dict(base_kw, spread=args.spread_bps, fin=fin)
        cdep = run(frames, params, flat_frac=0.0, **costed_kw)
        costed = {h: run(frames, params, flat_frac=h, **costed_kw) for h in RATIOS}
        crows = [describe(cdep, "deployed (costed)")]
        crows += [describe(costed[h], f"flat {h:.2f} costed") for h in RATIOS]
        table(crows)
        print(f"\n  reference, the deployed costed cell on record (S-22/S-26/S-28): "
              f"CAR {DEPLOYED_COSTED['CAR']:.3f}%  Sharpe {DEPLOYED_COSTED['Sharpe']:.3f}  "
              f"DD {DEPLOYED_COSTED['MaxDD']:.3f}%")
        print("\n  paired daily difference against the costed deployed book (bps/day):")
        for h in RATIOS:
            p = paired(costed[h], cdep, f"flat {h:.2f}", "deployed")
            print(f"    {p['pair']:<34}{p['bps_per_day']:>+8.3f}  t {p['t']:>+6.2f}  "
                  f"({p['days']} days)")
        rows += [dict(c, start=args.start, end=args.end, note=COSTED) for c in crows[1:]]

        # the vol-matched column, on the real machinery
        print("\n  vol-matched to the deployed book's own realized volatility "
              f"({summarize(cdep, 'd')['std']:.4f}), on the real machinery:")
        tgt = summarize(cdep, "d")["std"]
        for h in (0.50, 1.00):
            bk, k, trace = vol_match(frames, params, tgt, flat_frac=h, **costed_kw)
            s = describe(bk, f"flat {h:.2f} vol-matched")
            print(f"    h={h:.2f}  scale {k:.3f}  ({'; '.join(trace)})")
            print(f"    CAR {s['CAR']:.3f}%  Sharpe {s['Sharpe']:.3f}  DD {s['MaxDD']:.3f}%  "
                  f"std {s['std']:.4f}  gross mean {s['gross_x']:.2f} max {s['gross_max']:.2f}"
                  f"  turn {s['turnover_x']:.1f}x/yr")
            ok = (s["CAR"] > DEPLOYED_COSTED["CAR"]
                  and s["Sharpe"] >= DEPLOYED_COSTED["Sharpe"] - 0.03
                  and s["MaxDD"] <= DEPLOYED_COSTED["MaxDD"] + 1.0
                  and s["MaxDD"] <= 35.0 and s["gross_max"] <= REG_T)
            print(f"    criteria: {'PASS' if ok else 'REFUSED'}  "
                  f"(CAR {'+' if s['CAR'] > DEPLOYED_COSTED['CAR'] else '-'}, "
                  f"Sharpe {'+' if s['Sharpe'] >= DEPLOYED_COSTED['Sharpe'] - 0.03 else '-'}, "
                  f"DD {'+' if s['MaxDD'] <= DEPLOYED_COSTED['MaxDD'] + 1.0 else '-'}, "
                  f"Reg-T {'+' if s['gross_max'] <= REG_T else '-'})")
            rows.append(dict(s, start=args.start, end=args.end, note=COSTED))

        print("\n  halves (CAR%, costed, scale 1) - clause 5 needs BOTH:")
        for name, lo, hi in HALVES:
            line = f"    {name:<16}"
            for h in (0.0, 0.50, 1.00):
                s = describe(run(frames, params, flat_frac=h, spread=args.spread_bps,
                                 fin=fin, start=lo, end=hi), f"h{h} {name}")
                line += f"  h={h:.2f} {s['CAR']:>7.3f} (DD {s['MaxDD']:>5.1f})"
            print(line)

    # ------------------------------------------------------------ clause 6: the placebo
    if stage in ("all", "c"):
        print("\n=== clause 6: the placebo - the same construction on the leg that PAYS ===")
        print("  flat OVERNIGHT, holding the session. If this helps too, nothing here is")
        print("  about the split and the result is about leverage.\n")
        costed_kw = dict(base_kw, spread=args.spread_bps, fin=fin)
        cdep = run(frames, params, flat_frac=0.0, **costed_kw)
        tgt = summarize(cdep, "d")["std"]
        for mode, label in (("intraday", "flat overnight (placebo)"),
                            ("overnight", "flat all session (S-25 reload)")):
            bk = run(frames, params, mode=mode, **costed_kw)
            s = describe(bk, label)
            p = paired(bk, cdep, label, "deployed")
            print(f"  {label:<32} CAR {s['CAR']:>8.3f}%  Sharpe {s['Sharpe']:>6.3f}  "
                  f"DD {s['MaxDD']:>6.3f}%  turn {s['turnover_x']:>6.1f}x/yr  "
                  f"paired {p['bps_per_day']:+7.3f} (t {p['t']:+5.2f})")
            rows.append(dict(s, start=args.start, end=args.end, note=COSTED))
        print(f"\n  (both are quoted against the deployed costed book, std {tgt:.4f}; neither")
        print("   is relevered because neither is within a factor of the deployed book)")

    record(rows, GROSS, args.no_record)



    print(f"\n{len(rows)} DIAGNOSTIC rows "
          f"{'recorded' if not args.no_record else 'NOT recorded'} under daily/s30_delta")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
