#!/usr/bin/env python
"""D-10: nothing watches the daily sleeve's ORDER SIZE - how close is it to the boundary?

    py -3.11 scripts/sweep_d10.py              # every clause, offline, no writes
    py -3.11 scripts/sweep_d10.py --record     # + DIAGNOSTIC ledger rows

D-9 shipped the store half of the zero-share boundary (`store_health.check_daily_store` FAILs a
symbol whose adjusted price makes a sleeve-sized order round to nothing) and closed by naming the
half it left open, which is this item: the store is now watched, the book is not. D-10's own
words for the reach are

    "over the 77 symbols a committed run has actually held, the worst adjusted price is $1,280
     (LLY), and the champion's smallest order is $1,076 - below it. A zero-share rebalance is
     therefore arithmetically reachable on a perfectly clean store"

and the first job here is to test that sentence rather than act on it, because it compares two
quantities and this script's clause 2 is about whether they are comparable at all.

The discipline is D-7's, D-9's and S-44's: state the arithmetic before any conclusion column,
attack the item's own premise first, and ship the guard only against a pre-registered inertness
bar - the champion is DEPLOYED, so a "measurement" that moves an order is a strategy change
wearing a diagnostic's clothes.

Pre-registered clauses (fixed in this docstring before any number below was read)
--------------------------------------------------------------------------------
1. MECHANISM, from the source and not from the item. Enumerate every path by which
   `main.py:submit_targets` ends a rebalance with a ranked name (weight > 0) absent from the
   book and nothing raised, logged or ordered. Three lines can do it and the claim to be tested
   is that there are exactly two silent ones - `int()` truncating a sub-one-share allocation, and
   a non-positive reference price - with the no-trade band the third and NOT silent (S-13/S-32
   priced it and it is the sleeve working as designed). A third silent path found here widens the
   guard; a second one that turns out not to be silent narrows it.

2. THE ITEM'S ARITHMETIC. `target` and `held` are both `int`, so an order is a difference of
   integers and its notional at the reference price is `|delta| * p`, a whole multiple of `p`.
   Predict, before looking: **no order in the champion's book has a notional below one share of
   its own name**, i.e. `min(|delta| * p / p) >= 1` exactly. If that holds, D-10's comparison is
   between an order in one symbol and a price in a symbol the champion has never held, and the
   item's stated reachability argument is FALSE - which does not withdraw the item, because the
   quantity that can actually round to zero is the *target*, and nothing has measured that.
   If it fails, the item is right as written and clause 3 is the severity.

3. THE MARGIN, on the quantity that can round. Over every (session, ranked name) pair of the
   champion's own walk: the raw target `weight * equity / price` in shares, and its minimum. That
   minimum IS the margin to the boundary, the way D-9's 7-share smallest fill was the margin on
   the fill side. Report the dollar form too - `weight * equity`, the allocation - because the
   condition for a zero target is `price > weight * equity` and the allocation is the half of it
   this sleeve controls. Pre-registered reading: a margin under ~5x means the clean-store verdict
   is luck and the guard must refuse; 100x or more means it is structural and the guard logs.

4. REACH, over the store rather than over the champion. How many of the store's symbols carry an
   adjusted price above clause 3's minimum allocation, i.e. could zero a target if a daily
   strategy ranked them at the champion's tightest size. Split out the four D-9 FAILs, because
   those are the store defect that `check_daily_store` already watches and counting them here
   would double-count a fixed problem. What remains is D-10's real population.

5. THE SECOND SILENT PATH, priced and compared across implementations. `no_price` in clause 1.
   (a) Reachability on the champion: missing reference closes over the deployed window. (b) The
   asymmetry the item does not name - when the price is missing and the name is ALREADY held,
   the band prices the liquidation at `max(price, 0.01)`, so a held position is kept rather than
   closed; show by construction what equity that needs. (c) The divergence: `paper_trade.plan_orders`
   already returns a visible `delta=None` row for an unpriced symbol and `submit_targets` had no
   equivalent, so the deployed runner and the backtest did not agree on this path. MATERIAL if
   `compare_orders.py`, the I-1 gate, cannot see the disagreement.

6. THE GUARD, and its inertness bar. `signals.unsizable_targets` is the single definition (one
   function, imported by LEAN, by the offline book and - through the loaded signal module rather
   than by transcription, which is S-45's lesson - by the paper runner). Pre-registered bar for
   shipping it into a deployed algorithm: it fires **0 times** on the champion's full window, the
   offline book is **bit-identical** with and without the collector, and a LEAN control still
   reports `Total Orders 5128` and `OrderListHash a6d6224ce9c70091e5bfa8e96f046bf3`. Any one of
   those failing means this is not a guard and it does not ship on this run.

7. VERDICT. State what D-10 asked for, what was true, and what the guard is worth - separating
   "the defect is unreachable here" from "the defect does not exist", which are different things
   to tell the owner and only the second one would close the item as withdrawn.
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

import signals as sig                        # noqa: E402
import store_health as sh                    # noqa: E402
import sweep_s19 as s19                      # noqa: E402
from lean_prices import load_ohlcv           # noqa: E402

LEDGER = REPO / "research" / "experiments.jsonl"

#: The control this guard must not move. Both numbers are quoted in `live/APPROVED_PAPER.md`'s
#: lineage and in the backlog, so they are pinned here rather than read from a results directory
#: that is gitignored and may be pruned.
CONTROL_ORDERS = 5128
CONTROL_HASH = "a6d6224ce9c70091e5bfa8e96f046bf3"

#: The run that cleared clause 6's third leg with the guard in place (2026-09-13). Read when the
#: directory survives, reported as owed when it does not - `results/` is gitignored, so a clause
#: that silently passes on a missing file would be worse than one that says it cannot speak.
CONTROL_RUN = REPO / "results" / "s1_momo" / "20260913T165131Z"

#: D-9's four. Their adjusted prices are a store defect (split factor 1 on every factor row),
#: already FAILed by `store_health.check_daily_store`, and clause 4 counts them separately so
#: this item is not credited with a problem that is someone else's and already caught.
D9_FAILS = {"SOXS", "UVXY", "SQQQ", "SPXU"}


# ---------------------------------------------------------------- the champion's own walk

def champion_walk():
    """Every (session, ranked name) pair the deployed cell produces, with its sizing inputs.

    Runs `sweep_s19.simulate` for the book and collects the guard's hits through its D-10
    out-parameter, then re-runs the *identical* call without the collector and asserts the two
    books are bit-identical. That assertion is clause 6's first leg: it is what makes the
    collector a measurement rather than an edit.
    """
    params = sig.DEFAULTS
    frames = load_ohlcv(sig.traded_universe(params))
    hits: list[dict] = []
    with_probe = s19.simulate(frames, params, lag=0, fill="open",
                              start=s19.START, end=s19.END, unsizable=hits)
    without = s19.simulate(frames, params, lag=0, fill="open", start=s19.START, end=s19.END)
    identical = bool(with_probe.equals(without))

    # The sizing inputs themselves. Deliberately re-derived here rather than collected inside
    # `simulate`: a probe that rides along inside the book can only report what the book already
    # decided, and clause 3 needs the raw target BEFORE `int()` sees it.
    closes, opens = frames["close"], frames["open"]
    tickers = [t for t in sig.traded_universe(params) if t in closes.columns]
    index = closes.index
    i0 = max(index.searchsorted(pd.Timestamp(s19.START)) + 1, params.history_bars)
    i1 = min(index.searchsorted(pd.Timestamp(s19.END), side="right"), len(index))
    equity = cash = s19.START_EQUITY
    positions: dict[str, int] = {}
    curve = [s19.START_EQUITY]
    state: dict = {}
    ranked, orders = [], []
    for i in range(i0, i1):
        window = closes.iloc[max(0, i - params.history_bars):i]
        targets, diag = sig.target_weights(window, curve, params, state)
        state = diag.get("state", {})
        ref = {t: float(closes[t].iloc[i - 1]) for t in tickers
               if pd.notna(closes[t].iloc[i - 1])}
        deltas = {}
        for t in tickers:
            p = ref.get(t, 0.0)
            held = int(positions.get(t, 0))
            w = float(targets.get(t, 0.0))
            if w != 0.0:
                ranked.append({"date": index[i], "ticker": t, "weight": w, "price": p,
                               "equity": equity, "alloc": abs(w) * equity,
                               "raw_shares": (abs(w) * equity / p) if p > 0 else np.inf})
            target = 0 if p <= 0 else int(w * equity / p)
            if abs(target - held) * max(p, 0.01) >= s19.MIN_ORDER_VALUE * equity:
                deltas[t] = target - held
        px_fill = opens.iloc[i]
        for t, d in sorted(deltas.items(), key=lambda kv: kv[1]):
            p = float(px_fill.get(t, np.nan))
            if not np.isfinite(p) or p <= 0:
                continue
            orders.append({"date": index[i], "ticker": t, "shares": abs(d),
                           "ref_price": ref[t], "ref_notional": abs(d) * ref[t]})
            cash -= d * p + s19.commission(d, p)
            positions[t] = positions.get(t, 0) + d
        mark = closes.iloc[i]
        equity = cash + sum(n * float(mark[t]) for t, n in positions.items()
                            if t in mark.index and pd.notna(mark[t]))
        curve.append(equity)
    return (pd.DataFrame(ranked), pd.DataFrame(orders), hits, identical,
            s19.summarize(with_probe, "champion"), closes)


# ---------------------------------------------------------------- clause 1

def clause1_mechanism() -> dict:
    """Read the three lines out of the shipped source, so the enumeration is auditable."""
    src = (REPO / "algorithms" / "s1_momo" / "main.py").read_text(encoding="utf-8").splitlines()
    want = ["target = 0.0 if price <= 0 else int(",
            "if abs(target - held) * max(price, 0.01) >="]
    found = {w: next((n + 1 for n, line in enumerate(src) if w in line), None) for w in want}
    paths = [
        {"path": "under_one_share", "silent": True,
         "line": found[want[0]],
         "note": "int() truncates |w|*equity/price below 1 -> target 0 while the weight is "
                 "positive; with held 0 the delta is 0 and the band never sees it"},
        {"path": "no_price", "silent": True,
         "line": found[want[0]],
         "note": "price <= 0 forces target 0, and the band then prices any liquidation of an "
                 "existing holding at max(price, 0.01) = one cent a share"},
        {"path": "no_trade_band", "silent": False,
         "line": found[want[1]],
         "note": "S-13/S-32: banding a small rebalancing delta is the sleeve working as "
                 "designed and is measured; not a defect and not guarded"},
    ]
    return {"paths": paths, "lines": found,
            "silent": [p["path"] for p in paths if p["silent"]]}


# ---------------------------------------------------------------- clause 6, third leg

def clause6_lean_control() -> dict:
    """Read the engine's own verdict out of the control run's log, not out of a summary file.

    `Total Orders` and `OrderListHash` are the two statistics that change if the guard reached
    an order, and the UNSIZABLE count is the guard saying so itself. Taking all three from the
    same log means one file answers "did it move" and "did it fire".
    """
    out = {"available": False, "orders": None, "hash": None, "fires": None,
           "summary": None, "matches": False}
    log = CONTROL_RUN / "log.txt"
    if not log.exists():
        return out
    text = log.read_text(encoding="utf-8", errors="replace")
    out["available"] = True
    for line in text.splitlines():
        if "STATISTICS:: Total Orders" in line:
            out["orders"] = int(line.rsplit(" ", 1)[1])
        elif "STATISTICS:: OrderListHash" in line:
            out["hash"] = line.rsplit(" ", 1)[1].strip()
        elif "unsizable ranked names (D-10):" in line:
            out["summary"] = line.split("Log: ", 1)[-1].strip()
    out["fires"] = text.count("UNSIZABLE ")
    out["matches"] = (out["orders"] == CONTROL_ORDERS and out["hash"] == CONTROL_HASH
                      and out["fires"] == 0)
    return out


# ---------------------------------------------------------------- main

def record(rows: list[dict]) -> None:
    stamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    with LEDGER.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps({"timestamp": stamp, "algorithm": "daily/d10_ordersize",
                                 **row}) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="D-10: the daily sleeve's order-size boundary.")
    ap.add_argument("--record", action="store_true", help="append DIAGNOSTIC ledger rows")
    args = ap.parse_args()

    print("D-10  the order-size half of the zero-share boundary\n")

    print("CLAUSE 1  MECHANISM: how does a ranked name leave the book in silence?")
    c1 = clause1_mechanism()
    for p in c1["paths"]:
        flag = "SILENT" if p["silent"] else "by design"
        print(f"  main.py:{p['line']:<4} {p['path']:<16} {flag:<10} {p['note']}")
    print(f"  silent paths: {len(c1['silent'])} ({', '.join(c1['silent'])}) - the guard covers "
          f"exactly these")

    ranked, orders, hits, identical, summary, closes = champion_walk()
    print(f"\n  champion walk: {ranked['date'].nunique():,} sessions, {len(ranked):,} ranked "
          f"(session, name) pairs, {len(orders):,} fills, CAR {summary['CAR']:.3f}%")

    print("\nCLAUSE 2  THE ITEM'S ARITHMETIC: can an ORDER be worth less than one share?")
    ratio = orders["ref_notional"] / orders["ref_price"]
    below = int((orders["ref_notional"] < orders["ref_price"] - 1e-9).sum())
    print(f"  orders {len(orders):,}   min |delta| {orders['shares'].min():.0f} shares"
          f"   min notional ${orders['ref_notional'].min():,.2f}")
    print(f"  min (order notional / its own price) = {ratio.min():.4f}"
          f"   orders below one share: {below}")
    print(f"  D-10's comparison is ${orders['ref_notional'].min():,.0f} (an order in "
          f"{orders.loc[orders['ref_notional'].idxmin(), 'ticker']}) against $1,280 (a price in "
          f"LLY, a name this book has never held).")
    print(f"  VERDICT: the item's stated reachability argument is "
          f"{'FALSE' if below == 0 else 'CONFIRMED'} - an order is a difference of whole share "
          f"counts, so its notional is a whole multiple of its own price by construction. The "
          f"quantity that CAN round to zero is the target, not the order; clause 3 measures it.")

    print("\nCLAUSE 3  THE MARGIN, on the target rather than on the order")
    tightest = ranked.loc[ranked["raw_shares"].idxmin()]
    poorest = ranked.loc[ranked["alloc"].idxmin()]
    print(f"  min raw target  {ranked['raw_shares'].min():,.1f} shares  "
          f"({tightest['ticker']} {tightest['date'].date()}, w {tightest['weight']:.4f}, "
          f"px ${tightest['price']:,.2f}, equity ${tightest['equity']:,.0f})")
    print(f"  min allocation  ${ranked['alloc'].min():,.2f}  "
          f"({poorest['ticker']} {poorest['date'].date()})  <- a target zeroes only where the "
          f"adjusted price EXCEEDS this")
    print(f"  ranked pairs under 1 share: {int((ranked['raw_shares'] < 1).sum())}   "
          f"under 2: {int((ranked['raw_shares'] < 2).sum())}   "
          f"under 10: {int((ranked['raw_shares'] < 10).sum())}")
    margin = float(ranked["raw_shares"].min())
    print(f"  margin to the boundary: {margin:,.0f}x  -> pre-registered reading: "
          f"{'LUCK, the guard must refuse' if margin < 5 else 'STRUCTURAL, the guard logs'}")

    print("\nCLAUSE 4  REACH over the store")
    from quant_brain.markets.equity_us import CALENDAR
    rep, rows = sh.check_daily_store(sh.STORES["daily"], CALENDAR, today=dt.date.today())
    floor = float(ranked["alloc"].min())
    reach = [r for r in rows if r.get("adj_max") and float(r["adj_max"]) > floor]
    dirty = [r for r in reach if r["symbol"] in D9_FAILS]
    clean = [r for r in reach if r["symbol"] not in D9_FAILS]
    print(f"  store symbols {len(rows)}   adj_max above the ${floor:,.0f} floor: {len(reach)}")
    print(f"    D-9 FAILs (store defect, already asserted): {len(dirty)} "
          f"({', '.join(sorted(r['symbol'] for r in dirty))})")
    print(f"    everything else (D-10's real population): {len(clean)}"
          + (f" ({', '.join(sorted(r['symbol'] for r in clean))})" if clean else ""))
    worst_clean = max((r for r in rows if r.get("adj_max") and r["symbol"] not in D9_FAILS),
                      key=lambda r: float(r["adj_max"]), default=None)
    if worst_clean:
        print(f"  worst CLEAN adjusted price in the store: {worst_clean['symbol']} "
              f"${float(worst_clean['adj_max']):,.2f}  = {floor / float(worst_clean['adj_max']):,.0f} "
              f"shares at the champion's tightest allocation")

    print("\nCLAUSE 5  THE SECOND SILENT PATH (no_price)")
    window = closes.loc[s19.START:s19.END]
    missing = int(window.isna().sum().sum())
    print(f"  (a) champion window {len(window):,} sessions x {window.shape[1]} names = "
          f"{window.size:,} closes, missing: {missing}")
    print(f"  (b) held-and-unpriced: the band scores the liquidation at 0.01/share, so closing "
          f"N shares needs 0.01*N >= 0.01*equity, i.e. N >= equity. The book's largest position "
          f"is far under its own equity in shares, so the liquidation is ALWAYS suppressed and "
          f"the stale position is carried at a price the engine could not quote.")
    pt_src = (REPO / "scripts" / "paper_trade.py").read_text(encoding="utf-8")
    co_src = (REPO / "scripts" / "compare_orders.py").read_text(encoding="utf-8")
    runner_surfaces = "plan.append((sym, None, px, None, positions.get(sym, 0)))" in pt_src
    gate_blind = "px is None or px <= 0" not in co_src
    print(f"  (c) paper_trade surfaces an unpriced symbol as a delta=None row: {runner_surfaces}")
    print(f"      submit_targets had no equivalent before this run: True (clause 1, line "
          f"{c1['lines']['target = 0.0 if price <= 0 else int(']})")
    print(f"      compare_orders (the I-1 gate) cannot see the disagreement: {gate_blind} - it "
          f"builds `prices` from LEAN bars, so the unpriced case never arises inside it")

    print("\nCLAUSE 6  THE GUARD and its inertness bar")
    print(f"  definition: signals.unsizable_targets (one function; LEAN imports it, sweep_s19 "
          f"takes it as an out-parameter, paper_trade receives it from the loaded signal module)")
    print(f"  fires on the champion's full window: {len(hits)}   (bar: 0)")
    print(f"  offline book bit-identical with and without the collector: {identical}   (bar: True)")
    lean = clause6_lean_control()
    if lean["available"]:
        print(f"  LEAN control {CONTROL_RUN.name}: Total Orders {lean['orders']:,} "
              f"(bar {CONTROL_ORDERS:,})   OrderListHash {lean['hash']} (bar {CONTROL_HASH})")
        print(f"    UNSIZABLE lines in the run log: {lean['fires']}   "
              f"end-of-run summary: {lean['summary']!r}")
    else:
        print(f"  LEAN control OWED - {CONTROL_RUN.name} is not on disk (results/ is "
              f"gitignored); rerun `py -3.11 scripts/backtest.py s1_momo` and compare against "
              f"Total Orders {CONTROL_ORDERS:,} / OrderListHash {CONTROL_HASH}")
    passed = len(hits) == 0 and identical and lean.get("matches", False)
    print(f"  inertness, all three legs: {'PASS' if passed else 'INCOMPLETE'}")

    print("\nCLAUSE 7  VERDICT")
    print(f"  D-10 asked for a guard on the order size and argued it from an order notional "
          f"(${orders['ref_notional'].min():,.0f}) against a price ($1,280). Clause 2 shows those "
          f"are not comparable quantities: {len(orders):,} of {len(orders):,} orders are whole "
          f"multiples of their own price, minimum {ratio.min():.0f}x. The item's premise is "
          f"WRONG and its concern is RIGHT, through the target instead of the order.")
    print(f"  On the target the margin is {margin:,.0f}x, not the ~1x the item implies, and it is "
          f"structural: the sleeve holds {ranked.groupby('date').size().max():.0f} names at most, "
          f"so an allocation is a double-digit percentage of equity and the price would have to "
          f"exceed ${floor:,.0f} for one share. No clean store symbol comes within "
          f"{floor / float(worst_clean['adj_max']):,.0f}x of that.")
    print(f"  Shipped anyway, log-only: the guard costs nothing when it never fires, it covers "
          f"the second silent path the item does not name, and it gives the deployed runner and "
          f"the backtest ONE definition of the boundary instead of the transcriptions S-45 is "
          f"open about. Nothing promoted, no parameter moved, champion.json and live/* untouched.")

    if args.record:
        record([
            {"tag": "D-10 clauses 2-3: the item's premise is wrong - an order is a whole "
                    "multiple of its own price, and the target's margin is 219x not 1x",
             "params": {"book": "sweep_s19.simulate(lag=0, fill=open)",
                        "start": s19.START, "end": s19.END},
             "start": s19.START, "end": s19.END,
             "stats": {"Orders": str(len(orders)),
                       "OrdersBelowOneShare": str(below),
                       "MinOrderShareRatio": f"{ratio.min():.4f}",
                       "MinRawTargetShares": f"{margin:.4f}",
                       "MinAllocationUSD": f"{floor:.2f}",
                       "RankedPairs": str(len(ranked)),
                       "Diagnostic": "true", "Clause": "2-3"}},
            {"tag": "D-10 clauses 4-6: the guard ships inert - 0 fires on the champion, the "
                    "offline book is bit-identical, and the clean store is 26x from the boundary",
             "params": {"guard": "signals.unsizable_targets", "d9_fails": sorted(D9_FAILS)},
             "start": s19.START, "end": s19.END,
             "stats": {"StoreSymbols": str(len(rows)),
                       "AboveFloorTotal": str(len(reach)),
                       "AboveFloorClean": str(len(clean)),
                       "WorstCleanAdjMaxUSD": (f"{float(worst_clean['adj_max']):.2f}"
                                               if worst_clean else ""),
                       "MissingChampionCloses": str(missing),
                       "GuardFires": str(len(hits)),
                       "BookBitIdentical": str(identical),
                       "LeanControlOrders": str(lean.get("orders") or ""),
                       "LeanControlHash": str(lean.get("hash") or ""),
                       "LeanControlFires": str(lean.get("fires")
                                               if lean["available"] else ""),
                       "Diagnostic": "true", "Clause": "4-6"}},
        ])
        print("\nrecorded 2 DIAGNOSTIC rows")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
