#!/usr/bin/env python
"""S-44: the daily sweeps' commission replica is not LEAN's fee model - fix it and price it.

D-7 settled the engine side from source and then from data: LEAN's `InteractiveBrokersFeeModel`
charges US equities `feePerShare 0.005, minimumFee 1, maximumFeeRate 0.005`
(`InteractiveBrokersFeeModel.cs:150`), and `sweep_d7.lean_ib_fee` reproduces all 5,128 champion
fills to $0.0000. Only the S-track's own replica is wrong, and it is wrong in two ways, not one:

    sweep_s19.commission (pre-S-44)   min(max(1.00, 0.005*q), 0.01 * q * price)
    InteractiveBrokersFeeModel.cs     fee = 0.005*q
                                      if   fee < 1.00                 -> 1.00
                                      elif fee > 0.005 * q * price    -> 0.005 * q * price

(a) the cap RATE is 0.01 against the engine's 0.005 - the constant AUD-17/S-44 names; and
(b) the shape is a CLAMP against the engine's if/ELSE-if, so the replica lets the 0.5%-of-value
cap pull an order BELOW the $1 minimum, which LEAN never does. (b) was not in the item's text
and is found here by transcribing rather than by patching the one constant.

`sweep_s19.commission` is shared code - it is `simulate`'s fee function, and S-22/S-23/S-24/S-31
and `verify_s31` reach it through `simulate` while S-25 and S-39 import it by name - so the
change has to be proven inert on the shipped cell before it lands, and the legacy form has to
stay callable so any row written before today can be reproduced.

Nine clauses, pre-registered here before the first simulation:

 1. TRANSCRIPTION. The new `commission` equals `sweep_d7.lean_ib_fee` at every point of a
    (quantity x price) grid spanning both branches, and reproduces the champion's LEAN-reported
    `Total Fees` from its 5,128 order events to the cent.
 2. THE DIFFERENCE, PREDICTED THEN ENUMERATED. Legacy and engine can differ only where
    `price < $1.00` (the cap band) or `q < 200 and q*price < $200` (the floor-vs-cap band).
    Enumerate the same grid and check no third region exists; report the worst ratio. Predicted
    sign: the legacy replica OVERCHARGES in the cap band (up to exactly 2x) and UNDERCHARGES in
    the floor band.
 3. THE SHIPPED CELL. On the champion's own 5,128 fills the two forms must agree, because the
    champion ranks 9 ETFs whose adjusted prices never approach $1. Pre-registered expectation:
    delta exactly $0.00. If it is not, the fix is promotion-gated and stops here.
 4. BIT-IDENTITY OF THE HARNESS. Re-run S-19's four conventions under both forms. Expectation:
    CAR delta 0.00e+00 and order delta 0 in every cell. This is the licence to change shared code.
 5. REACHABILITY. Per symbol over the daily store, sessions whose ADJUSTED close is under $1.00
    and under $0.50, on the S-19 window. The defect is inert only where the book cannot reach.
 6. PRICE IT WHERE IT BINDS. `LEVERED_PROXY_3X` (S-6/S-18's 3x book, the one shipped-adjacent
    configuration that holds TQQQ) under both fee forms: fees, CAR, drawdown, paired bps/day.
 7. THE FLOOR BRANCH. `MIN_ORDER_VALUE = 0.01 * equity` means an order under $200 of value needs
    equity under $20,000. Report the book's minimum equity: if it is above that, branch (b) is
    unreachable by construction in this harness and is a guard, not a correction.
 8. THE NEIGHBOUR. `sweep_s21.commission` says "the same model `scripts/sweep_s19.py` uses" and
    is a different model on all three constants (0.0035 / $0.35 / 1%, IBKR's TIERED schedule
    rather than the fixed one LEAN charges). Price the gap on the champion's fills, re-cost
    S-21's walk under both, re-accrue the financing drag, and check whether the corrected walk
    reproduces `sweep_s19.simulate(..., fill="open")` - which S-21's own docstring claims it is.
    Pre-registered bar: S-21's conclusion is "unchanged" if the drag moves under 0.05 CAR points.
 9. VERDICT RULE. Ship the transcription iff clause 1 passes and clause 4 is exactly zero.
    Clause 6's correction is reported as DIAGNOSTIC and is called a changed conclusion only if
    its CAR delta exceeds 0.10 points.

    py -3.11 scripts/sweep_s44.py                # all nine clauses
    py -3.11 scripts/sweep_s44.py --no-record    # do not append to the ledger

Nothing here is a promotion candidate: every row is the same strategy under two arithmetics for
the same broker, so the only question is which arithmetic is the engine's.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "algorithms" / "s1_momo"))
sys.path.insert(0, str(REPO / "scripts"))

import signals as sig                                              # noqa: E402
import fetch_data as fd                                            # noqa: E402
import sweep_s19 as s19                                            # noqa: E402
import sweep_s21 as s21                                            # noqa: E402
from sweep_d7 import lean_ib_fee                                   # noqa: E402
from lean_prices import load_ohlcv                                 # noqa: E402

LEDGER = REPO / "research" / "experiments.jsonl"
CHAMPION_RUN = REPO / "results" / "s1_momo" / "20260911T145705Z"
CHAMPION_FEES = 27199.76          # champion.json stats["Total Fees"], LEAN's own number


# --------------------------------------------------------------------------- clause 1 & 2

#: Spans both branches on purpose: q from 1 share to 50,000, price from a penny to $1,000.
GRID_Q = [1, 2, 5, 10, 50, 100, 150, 199, 200, 201, 500, 1_000, 5_000, 50_000]
GRID_PX = [0.01, 0.05, 0.1, 0.2, 0.3, 0.4, 0.49, 0.5, 0.51, 0.75, 0.99, 1.0, 1.01,
           2.0, 5.0, 9.5, 50.0, 97.16, 500.0, 1_000.0]


def clause1_transcription() -> dict:
    """The new form against D-7's independently-written replica, then against LEAN itself."""
    worst = 0.0
    for q in GRID_Q:
        for px in GRID_PX:
            worst = max(worst, abs(s19.commission(q, px) - lean_ib_fee(q, px)))
            worst = max(worst, abs(s19.commission(-q, px) - lean_ib_fee(-q, px)))
    fills = champion_fills()
    total = sum(s19.commission(f["q"], f["px"]) for f in fills)
    return {"grid_points": 2 * len(GRID_Q) * len(GRID_PX),
            "max_abs_diff_vs_d7": worst,
            "champion_fills": len(fills),
            "replica_total_fees": total,
            "lean_total_fees": CHAMPION_FEES,
            "fee_error": total - CHAMPION_FEES,
            "pass": worst == 0.0 and abs(total - CHAMPION_FEES) < 0.005}


def clause2_difference() -> dict:
    """Enumerate where legacy and engine part, and check the two predicted bands are all of it."""
    rows, unexplained = [], 0
    over = under = 0
    worst_ratio = 1.0
    for q in GRID_Q:
        for px in GRID_PX:
            a, b = s19.commission(q, px), s19.commission_legacy(q, px)
            if abs(a - b) < 1e-12:
                continue
            in_cap = px < 1.0
            in_floor = (0.005 * q < 1.0) and (q * px < 200.0)
            if not (in_cap or in_floor):
                unexplained += 1
            if b > a:
                over += 1
            else:
                under += 1
            worst_ratio = max(worst_ratio, b / a if a else float("inf"))
            band = "+".join([n for n, f in (("cap", in_cap), ("floor", in_floor)) if f]) or "?"
            rows.append({"q": q, "px": px, "engine": a, "legacy": b, "band": band})
    return {"differing_points": len(rows), "unexplained": unexplained,
            "legacy_overcharges": over, "legacy_undercharges": under,
            "worst_legacy_over_engine_ratio": worst_ratio,
            "worst_engine_over_legacy_ratio": max(
                (r["engine"] / r["legacy"] for r in rows if r["legacy"] > 0), default=1.0),
            "sample": [r for r in rows if r["band"] == "cap"][:4]
                      + [r for r in rows if r["band"] == "cap+floor"][:4],
            "pass": unexplained == 0}


# ------------------------------------------------------------------------------- clause 3

def champion_fills() -> list[dict]:
    path = CHAMPION_RUN / "S1MomentumRotationAlgorithm-order-events.json"
    out = []
    for e in json.loads(path.read_text(encoding="utf-8")):
        if e.get("status") == "filled":
            out.append({"sym": e["symbolValue"], "q": float(e["fillQuantity"]),
                        "px": float(e["fillPrice"])})
    return out


def clause3_shipped_cell() -> dict:
    fills = champion_fills()
    eng = sum(s19.commission(f["q"], f["px"]) for f in fills)
    leg = sum(s19.commission_legacy(f["q"], f["px"]) for f in fills)
    n_diff = sum(1 for f in fills
                 if abs(s19.commission(f["q"], f["px"])
                        - s19.commission_legacy(f["q"], f["px"])) > 1e-9)
    px = sorted(abs(f["px"]) for f in fills)
    val = sorted(abs(f["px"] * f["q"]) for f in fills)
    q = sorted(abs(f["q"]) for f in fills)
    return {"fills": len(fills), "engine": eng, "legacy": leg, "delta": eng - leg,
            "fills_that_differ": n_diff,
            "min_fill_price": px[0], "min_fill_value": val[0], "min_fill_qty": q[0],
            "fills_at_the_1_dollar_floor": sum(1 for x in q if 0.005 * x < 1.0),
            "pass": n_diff == 0 and abs(eng - leg) < 1e-9}


# ------------------------------------------------------------------------------- clause 4

def run_conventions(frames, params, start: str, end: str, legacy: bool) -> dict:
    """S-19's four conventions under one fee arithmetic, by swapping the module's function."""
    keep = s19.commission
    if legacy:
        s19.commission = s19.commission_legacy
    try:
        out = {}
        for label, lag, fill in s19.CONVENTIONS:
            book = s19.simulate(frames, params, lag, fill, start, end)
            out[label] = (book, s19.summarize(book, label))
        return out
    finally:
        s19.commission = keep


def clause4_bit_identity(frames, params, start: str, end: str) -> dict:
    eng = run_conventions(frames, params, start, end, legacy=False)
    leg = run_conventions(frames, params, start, end, legacy=True)
    rows = []
    worst_car = worst_fee = 0.0
    worst_orders = 0
    for label, (_b, se) in eng.items():
        sl = leg[label][1]
        rows.append({"cell": label, "CAR_engine": se["CAR"], "CAR_legacy": sl["CAR"],
                     "d_CAR": se["CAR"] - sl["CAR"], "fees_engine": se["fees"],
                     "fees_legacy": sl["fees"], "d_fees": se["fees"] - sl["fees"],
                     "orders_engine": se["orders"], "d_orders": se["orders"] - sl["orders"]})
        worst_car = max(worst_car, abs(se["CAR"] - sl["CAR"]))
        worst_fee = max(worst_fee, abs(se["fees"] - sl["fees"]))
        worst_orders = max(worst_orders, abs(se["orders"] - sl["orders"]))
    return {"rows": rows, "max_abs_d_CAR": worst_car, "max_abs_d_fees": worst_fee,
            "max_abs_d_orders": worst_orders,
            "pass": worst_car == 0.0 and worst_fee == 0.0 and worst_orders == 0,
            "books": eng}


# ------------------------------------------------------------------------------- clause 5

def clause5_reachability(start: str, end: str) -> dict:
    ok = []
    for t in fd.ETFS + fd.MEGACAPS:
        try:
            load_ohlcv([t])
            ok.append(t)
        except Exception:
            continue
    closes = load_ohlcv(ok)["close"].loc[start:end]
    per = {}
    for t in closes.columns:
        s = closes[t].dropna()
        if s.empty:
            continue
        n1, nh = int((s < 1.0).sum()), int((s < 0.5).sum())
        if n1:
            per[t] = {"sessions": int(len(s)), "min_adj_close": float(s.min()),
                      "sessions_below_1": n1, "sessions_below_0_50": nh,
                      "share_below_1": n1 / len(s)}
    return {"symbols_loaded": len(ok), "missing": sorted(set(fd.ETFS + fd.MEGACAPS) - set(ok)),
            "symbols_reaching_the_cap": per,
            "champion_universe_min": float(
                closes[[t for t in sig.traded_universe() if t in closes.columns]].min().min())}


# ------------------------------------------------------------------------------- clause 6

def clause6_levered(start: str, end: str) -> dict:
    """The 3x book under both fee forms. Restores `signals.LEVERED_PROXY` on the way out."""
    keep_map = sig.LEVERED_PROXY
    sig.LEVERED_PROXY = dict(sig.LEVERED_PROXY_3X)
    try:
        params = sig.Params()
        tickers = [t for t in sig.traded_universe(params)]
        frames = load_ohlcv(tickers)
        label, lag, fill = s19.CONVENTIONS[0]
        keep_fn = s19.commission
        books = {}
        for name, fn in (("engine", s19.commission), ("legacy", s19.commission_legacy)):
            s19.commission = fn
            try:
                books[name] = s19.simulate(frames, params, lag, fill, start, end)
            finally:
                s19.commission = keep_fn
        se = s19.summarize(books["engine"], "3x engine")
        sl = s19.summarize(books["legacy"], "3x legacy")
        p = s19.paired(books["engine"], books["legacy"], "engine", "legacy")
        return {"universe": tickers, "engine": se, "legacy": sl,
                "d_CAR": se["CAR"] - sl["CAR"], "d_fees": se["fees"] - sl["fees"],
                "d_MaxDD": se["MaxDD"] - sl["MaxDD"],
                "fee_share": (sl["fees"] - se["fees"]) / sl["fees"] if sl["fees"] else 0.0,
                "paired": p,
                "min_equity": float(books["engine"]["equity"].min())}
    finally:
        sig.LEVERED_PROXY = keep_map


# ------------------------------------------------------------------------------- clause 7

def clause7_floor(books: dict) -> dict:
    """Is the floor-vs-cap branch reachable given the band? Needs equity under $20,000."""
    threshold = s19.FEE_MIN / (s19.FEE_MAX_FRAC * 1.0)          # order value at which the
    equity_needed = threshold / s19.MIN_ORDER_VALUE             # cap would pull below the floor
    mins = {label: float(b["equity"].min()) for label, (b, _s) in books.items()}
    return {"order_value_below_which_cap_beats_floor": threshold,
            "equity_that_would_require": equity_needed,
            "min_equity_by_cell": mins,
            "reachable": any(v < equity_needed for v in mins.values())}


# ------------------------------------------------------------------------------- clause 8

def clause8_neighbour(start: str, end: str) -> dict:
    """`sweep_s21`'s own fee function against the engine's, on fills and then on conclusions.

    Two questions, and the second is the one that decides whether anything already claimed on
    this track moves: (a) how far apart are the two arithmetics on the champion's fills, and
    (b) does S-21's financing drag - the number quoted to the owner - change when the walk is
    re-costed? (b) is run by swapping the function under `s21.walk` and re-accruing through
    `s21.probe`, which is a cheap re-read of the same cash path.
    """
    old = s21.commission_tiered_legacy
    fills = champion_fills()
    eng = sum(s19.commission(f["q"], f["px"]) for f in fills)
    nb = sum(old(f["q"], f["px"]) for f in fills)
    n_diff = sum(1 for f in fills
                 if abs(s19.commission(f["q"], f["px"]) - old(f["q"], f["px"])) > 1e-9)

    params = sig.Params()
    walks, drags = {}, {}
    keep_fn = s21.commission
    for name, fn in (("engine", s19.commission), ("tiered_legacy", old)):
        s21.commission = fn
        try:
            walks[name] = s21.walk(params, start, end)
        finally:
            s21.commission = keep_fn
    keep_cached = s21.cached_walk
    for name, book in walks.items():
        s21.cached_walk = lambda _b=book: _b
        try:
            pr = s21.probe(0.0)
            drags[name] = {"interest": float(pr["interest"].sum()),
                           "drag_bps_per_day": float(pr["drag_bps"].mean()),
                           "simple_CAR_points": float(pr["drag_bps"].mean() * 252 / 100),
                           "end_equity": float(book["equity"].iloc[-1]),
                           "mean_cash": float(book["cash"].mean()),
                           "share_in_credit": float((book["cash"] > 0).mean())}
        finally:
            s21.cached_walk = keep_cached

    # The identity the corrected fee model buys: S-21's walk is documented as the S-19
    # convention, so under one arithmetic the two books must be the same book.
    frames = load_ohlcv(sig.traded_universe(params))
    label, lag, fill = s19.CONVENTIONS[0]
    ref = s19.simulate(frames, params, lag, fill, start, end)
    ident = {}
    for name, book in walks.items():
        d = np.abs(book["equity"].to_numpy() - ref["equity"].to_numpy())
        ident[name] = {"max_abs_session_gap": float(d.max()),
                       "end_gap": float(book["equity"].iloc[-1] - ref["equity"].iloc[-1])}
    return {"engine": eng, "sweep_s21_tiered": nb, "delta": nb - eng,
            "share_of_engine": (nb - eng) / eng if eng else 0.0,
            "fills_that_differ": n_diff, "fills": len(fills),
            "constants_s21_tiered": {"per_share": 0.0035, "min": 0.35, "cap_frac": 0.01},
            "constants_engine": {"per_share": s19.FEE_PER_SHARE, "min": s19.FEE_MIN,
                                 "cap_frac": s19.FEE_MAX_FRAC},
            "financing": drags,
            "d_simple_CAR_points": (drags["engine"]["simple_CAR_points"]
                                    - drags["tiered_legacy"]["simple_CAR_points"]),
            "identity_vs_s19_backtest_cell": ident,
            "s19_end_equity": float(ref["equity"].iloc[-1])}


# ---------------------------------------------------------------------------------- output

def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=REPO,
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return ""


def record(tag: str, params: dict, stats: dict, start: str, end: str) -> None:
    rec = {"ts": dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
           "algorithm": "daily/s44_feecap", "class": "diagnostic", "tag": tag,
           "commit": git_commit(), "run_dir": "", "track": "S-44",
           "params": params, "start": start, "end": end,
           "stats": {**{k: str(v) for k, v in stats.items()}, "Diagnostic": "true"}}
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default=s19.START)
    ap.add_argument("--end", default=s19.END)
    ap.add_argument("--no-record", action="store_true")
    args = ap.parse_args()

    print(f"S-44  window {args.start} .. {args.end}   commit {git_commit()}")
    print(f"engine constants in sweep_s19: per_share {s19.FEE_PER_SHARE} "
          f"min ${s19.FEE_MIN:.2f} cap {s19.FEE_MAX_FRAC:.4f}\n")

    c1 = clause1_transcription()
    print("clause 1  transcription")
    print(f"  grid points checked against sweep_d7.lean_ib_fee   {c1['grid_points']:,}")
    print(f"  max |difference|                                   {c1['max_abs_diff_vs_d7']:.3e}")
    print(f"  champion fills replayed                            {c1['champion_fills']:,}")
    print(f"  replica total fees ${c1['replica_total_fees']:,.2f}  LEAN reports "
          f"${c1['lean_total_fees']:,.2f}  error ${c1['fee_error']:+.4f}")
    print(f"  PASS {c1['pass']}\n")

    c2 = clause2_difference()
    print("clause 2  where the legacy clamp and the engine part")
    print(f"  grid points that differ   {c2['differing_points']}  outside the two predicted "
          f"bands  {c2['unexplained']}")
    print(f"  legacy overcharges at {c2['legacy_overcharges']} points, undercharges at "
          f"{c2['legacy_undercharges']}")
    print(f"  worst legacy/engine ratio  {c2['worst_legacy_over_engine_ratio']:.4f} "
          f"(the cap band)   worst engine/legacy "
          f"{c2['worst_engine_over_legacy_ratio']:,.0f} (the floor band)")
    for r in c2["sample"]:
        print(f"    q {r['q']:>6}  px {r['px']:>8.2f}  engine {r['engine']:>10.4f}  "
              f"legacy {r['legacy']:>10.4f}   band {r['band']}")
    print(f"  PASS {c2['pass']}\n")

    c3 = clause3_shipped_cell()
    print("clause 3  the shipped cell")
    print(f"  champion fills {c3['fills']:,}   fills where the two forms differ "
          f"{c3['fills_that_differ']}")
    print(f"  engine ${c3['engine']:,.2f}   legacy ${c3['legacy']:,.2f}   delta "
          f"${c3['delta']:+,.2f}")
    print(f"  min fill price ${c3['min_fill_price']:,.2f}   min fill value "
          f"${c3['min_fill_value']:,.2f}   min qty {c3['min_fill_qty']:,.0f} shares")
    print(f"  fills sitting on the $1 minimum  {c3['fills_at_the_1_dollar_floor']:,} "
          f"({100 * c3['fills_at_the_1_dollar_floor'] / c3['fills']:.1f}%)")
    print(f"  PASS {c3['pass']}\n")

    params = sig.Params()
    frames = load_ohlcv(sig.traded_universe(params))
    c4 = clause4_bit_identity(frames, params, args.start, args.end)
    print("clause 4  S-19's four conventions under both fee forms")
    hdr = (f"  {'cell':<28}{'CAR eng':>10}{'CAR leg':>10}{'dCAR':>11}{'fees eng':>11}"
           f"{'d fees':>9}{'orders':>8}{'d ord':>7}")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for r in c4["rows"]:
        print(f"  {r['cell']:<28}{r['CAR_engine']:>10.6f}{r['CAR_legacy']:>10.6f}"
              f"{r['d_CAR']:>11.2e}{r['fees_engine']:>11,.2f}{r['d_fees']:>9.2f}"
              f"{r['orders_engine']:>8,}{r['d_orders']:>7}")
    print(f"  max |dCAR| {c4['max_abs_d_CAR']:.2e}   max |dfees| {c4['max_abs_d_fees']:.2e}   "
          f"max |dorders| {c4['max_abs_d_orders']}")
    print(f"  PASS {c4['pass']}\n")

    c5 = clause5_reachability(args.start, args.end)
    print("clause 5  reachability - adjusted closes that put a fill inside the cap band")
    print(f"  store symbols loaded {c5['symbols_loaded']} (missing {c5['missing']})")
    print(f"  champion universe minimum adjusted close  ${c5['champion_universe_min']:,.2f}")
    print(f"  {'symbol':<8}{'min adj $':>11}{'sess<$1':>9}{'sess<$0.50':>12}{'share<$1':>10}")
    for t, d in sorted(c5["symbols_reaching_the_cap"].items(),
                       key=lambda kv: -kv[1]["sessions_below_1"]):
        print(f"  {t:<8}{d['min_adj_close']:>11.4f}{d['sessions_below_1']:>9,}"
              f"{d['sessions_below_0_50']:>12,}{100 * d['share_below_1']:>9.1f}%")
    print()

    c6 = clause6_levered(args.start, args.end)
    print("clause 6  the 3x book (LEVERED_PROXY_3X), backtest convention, both fee forms")
    print(f"  universe {c6['universe']}")
    for k in ("engine", "legacy"):
        s = c6[k]
        print(f"  {k:<8}CAR {s['CAR']:>9.4f}%  Sharpe {s['Sharpe']:>6.3f}  MaxDD "
              f"{s['MaxDD']:>7.3f}%  orders {s['orders']:>6,}  fees ${s['fees']:>11,.2f}")
    print(f"  delta (engine - legacy)  CAR {c6['d_CAR']:+.4f} points   fees "
          f"${c6['d_fees']:+,.2f} ({100 * c6['fee_share']:.2f}% of the legacy fee line)   "
          f"MaxDD {c6['d_MaxDD']:+.4f}")
    print(f"  paired {c6['paired']['bps_per_day']:+.4f} bps/day  t {c6['paired']['t']:+.2f} "
          f"({c6['paired']['days']} days)\n")

    c7 = clause7_floor(c4["books"])
    print("clause 7  the floor-vs-cap branch")
    print(f"  the cap undercuts the $1 minimum below an order value of "
          f"${c7['order_value_below_which_cap_beats_floor']:,.2f}")
    print(f"  with the {s19.MIN_ORDER_VALUE:g} x equity band that needs equity under "
          f"${c7['equity_that_would_require']:,.2f}")
    print(f"  minimum equity reached: " + "  ".join(
        f"{k.split('(')[0].strip()[:18]} ${v:,.0f}" for k, v in c7["min_equity_by_cell"].items()))
    print(f"  reachable in this harness: {c7['reachable']}\n")

    c8 = clause8_neighbour(args.start, args.end)
    print("clause 8  sweep_s21.commission, which its docstring called the same model")
    print(f"  tiered (pre-S-44) {c8['constants_s21_tiered']}")
    print(f"  engine            {c8['constants_engine']}")
    print(f"  on the champion's {c8['fills']:,} fills: engine ${c8['engine']:,.2f}, tiered "
          f"${c8['sweep_s21_tiered']:,.2f}, delta ${c8['delta']:+,.2f} "
          f"({100 * c8['share_of_engine']:+.2f}%), differing on "
          f"{c8['fills_that_differ']:,} of {c8['fills']:,} fills")
    print(f"  {'form':<16}{'interest $':>14}{'drag bps/day':>14}{'simple CAR pts':>16}"
          f"{'end equity':>14}{'in credit':>11}")
    for k in ("engine", "tiered_legacy"):
        d = c8["financing"][k]
        print(f"  {k:<16}{d['interest']:>14,.2f}{d['drag_bps_per_day']:>14.4f}"
              f"{d['simple_CAR_points']:>16.4f}{d['end_equity']:>14,.0f}"
              f"{100 * d['share_in_credit']:>10.1f}%")
    print(f"  S-21's conclusion moves by {c8['d_simple_CAR_points']:+.4f} CAR points")
    print(f"  identity against sweep_s19's backtest cell (end equity "
          f"${c8['s19_end_equity']:,.2f}):")
    for k, v in c8["identity_vs_s19_backtest_cell"].items():
        print(f"    {k:<16} max session gap {v['max_abs_session_gap']:.3e}   end gap "
              f"${v['end_gap']:+,.2f}")
    print()

    ship = c1["pass"] and c4["pass"]
    print("clause 9  verdict")
    print(f"  transcription passes: {c1['pass']}   harness bit-identical: {c4['pass']}")
    print(f"  SHIP THE TRANSCRIPTION: {ship}")
    print(f"  clause 6 CAR delta {c6['d_CAR']:+.4f} points -> "
          f"{'a changed conclusion' if abs(c6['d_CAR']) > 0.10 else 'below the 0.10 bar, reported not promoted'}")

    if not args.no_record:
        for r in c4["rows"]:
            record(f"S-44 identity/{r['cell']}: S-19 convention under the LEAN-exact fee model "
                   f"vs the pre-S-44 clamp (DIAGNOSTIC)",
                   {"fee_form": "engine", "cap_frac": s19.FEE_MAX_FRAC, "legacy_cap_frac": 0.01},
                   {"Compounding Annual Return": f"{r['CAR_engine']:.6f}%",
                    "Total Fees": f"${r['fees_engine']:.2f}",
                    "Total Orders": str(r["orders_engine"]),
                    "dCAR vs legacy": f"{r['d_CAR']:.2e}",
                    "dFees vs legacy": f"${r['d_fees']:.2f}"},
                   args.start, args.end)
        for k in ("engine", "legacy"):
            s = c6[k]
            record(f"S-44 levered/{k}: the LEVERED_PROXY_3X book priced with the "
                   f"{'LEAN-exact' if k == 'engine' else 'pre-S-44 clamp'} fee model (DIAGNOSTIC)",
                   {"fee_form": k, "levered": "LEVERED_PROXY_3X",
                    "cap_frac": s19.FEE_MAX_FRAC if k == "engine" else 0.01},
                   {"Compounding Annual Return": f"{s['CAR']:.6f}%",
                    "Sharpe Ratio": f"{s['Sharpe']:.3f}",
                    "Drawdown": f"{s['MaxDD']:.3f}%",
                    "Total Orders": str(s["orders"]),
                    "Total Fees": f"${s['fees']:.2f}",
                    "Paired vs legacy bps/day": f"{c6['paired']['bps_per_day']:.4f}",
                    "Paired t": f"{c6['paired']['t']:.2f}"},
                   args.start, args.end)
        for k in ("engine", "tiered_legacy"):
            d = c8["financing"][k]
            record(f"S-44 financing/{k}: S-21's cash walk re-costed with the "
                   f"{'LEAN-exact fixed' if k == 'engine' else 'pre-S-44 IBKR tiered'} fee "
                   f"schedule, drag re-accrued (DIAGNOSTIC)",
                   {"fee_form": k, "spread_shift": 0.0,
                    "per_share": 0.005 if k == "engine" else 0.0035,
                    "fee_min": 1.0 if k == "engine" else 0.35,
                    "cap_frac": 0.005 if k == "engine" else 0.01},
                   {"End Equity": f"{d['end_equity']:.2f}",
                    "Total Interest": f"${d['interest']:.2f}",
                    "Drag Bps Per Day": f"{d['drag_bps_per_day']:.4f}",
                    "Simple CAR Points": f"{d['simple_CAR_points']:.4f}",
                    "Sessions In Credit": f"{100 * d['share_in_credit']:.1f}%",
                    "Gap vs s19 backtest cell":
                        f"{c8['identity_vs_s19_backtest_cell'][k]['end_gap']:.2f}"},
                   args.start, args.end)
        print(f"\n{len(c4['rows']) + 4} rows appended to {LEDGER.relative_to(REPO)}")

    out = REPO / "results" / "s44_full.txt"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"clause1": c1, "clause2": c2, "clause3": c3,
                               "clause4": {k: v for k, v in c4.items() if k != "books"},
                               "clause5": c5,
                               "clause6": {k: v for k, v in c6.items()},
                               "clause7": c7, "clause8": c8, "ship": ship},
                              indent=1, default=str), encoding="utf-8")
    print(f"full detail -> {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
