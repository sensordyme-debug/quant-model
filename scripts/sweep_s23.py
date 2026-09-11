#!/usr/bin/env python
"""S-23: the pre-open MOO path - what it is worth, and what would take it away.

BLOCKERS.md has been asking the owner to move the daily task from 15:45 ET to a pre-open
slot since S-17, and S-22 priced the move at +1.85 CAR points on an honestly-costed book.
Every one of those numbers assumes the opening auction fills at the same price as the
closing one. That assumption has never been charged, and it is the assumption a reasonable
person would push on: the closing auction is the deepest print of the US day and the
opening auction is not.

So this script asks the decision-shaped question instead of the return-shaped one:

    the move is worth +X CAR points; how much MORE than the closing auction would the
    opening auction have to cost before X goes to zero?

That is a breakeven, it has the same units as the thing the loop actually measures on live
fills (bps against the reference price), and it converts an unfalsifiable worry into a
number the next fifty fills can check. Both books are run through S-19's share-level
harness with S-22's financing hook, so both pay IBKR Pro interest on the debit balance they
carry, and the deployed book is charged the 2 bp column the ledger uses.

    python scripts/sweep_s23.py                # breakeven + halves, historical rates
    python scripts/sweep_s23.py --today        # also at today's 3.63% flat benchmark
    python scripts/sweep_s23.py --auction      # the minute-store liquidity read
    python scripts/sweep_s23.py --no-record

Nothing here is promotable: both rows are the same strategy at a different fill, so the
winner is known before the run and only its margin is in question. The output belongs in
BLOCKERS.md next to the request.
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

import signals as sig                                      # noqa: E402
import rates                                               # noqa: E402
from lean_prices import load_ohlcv                         # noqa: E402
from sweep_s19 import simulate, summarize, paired, START, END   # noqa: E402

LEDGER = REPO / "research" / "experiments.jsonl"
SPLIT = "2020-01-01"          # the halves S-12 and S-18 were both judged on


def car_of(book: pd.DataFrame) -> float:
    return summarize(book, "")["CAR"]


def breakeven(frames, params, fin, deployed_car: float, args) -> dict:
    """Extra spread on the OPENING auction that erases the pre-open move's advantage.

    The deployed book is fixed at `--spread-bps`; the pre-open book is charged the same
    plus a surcharge, and the surcharge is solved for. A monotone bisection is enough -
    CAR is strictly decreasing in the spread charged to a book whose order list does not
    depend on it (sizing uses the previous close either way, so the plan is unchanged and
    only the price paid moves).
    """
    def preopen_car(extra: float) -> float:
        b = simulate(frames, params, 0, "open", args.start, args.end,
                     args.spread_bps + extra, fin)
        return car_of(b)

    lo, hi = 0.0, 2.0
    grid = []
    while preopen_car(hi) > deployed_car and hi < 64.0:
        lo, hi = hi, hi * 2
    for _ in range(12):
        mid = 0.5 * (lo + hi)
        c = preopen_car(mid)
        grid.append((mid, c))
        if c > deployed_car:
            lo = mid
        else:
            hi = mid
    return {"extra_bps": 0.5 * (lo + hi), "probe": grid}


def auction_read(symbols) -> None:
    """What the minute store can say about opening vs closing auction liquidity.

    This is a proxy and is labelled as one. Alpaca SIP minute bars carry no quotes, so the
    spread itself is not observable here; what IS observable is how much of the day trades
    in the first minute against the last, and how wide those two minutes are in bps. A
    market order into a thinner, wider auction is the mechanism the breakeven is guarding
    against, so the direction and rough size of the asymmetry is worth having.
    """
    store = REPO / "data" / "minute_alpaca"
    print("\nopening vs closing minute, Alpaca SIP 1-minute TRADES bars "
          "(a proxy: no quotes in this store)")
    print(f"{'sym':<6}{'sessions':>9}{'open vol %':>12}{'close vol %':>12}"
          f"{'open rng bps':>14}{'close rng bps':>14}{'ratio':>8}")
    for s in symbols:
        p = store / f"{s}.parquet"
        if not p.exists():
            print(f"{s:<6}{'not in store':>9}")
            continue
        df = pd.read_parquet(p)                   # columns o,h,l,c,v on a UTC DatetimeIndex
        et = df.index.tz_convert("America/New_York")
        df = df.assign(_day=et.date, _t=et.time)
        df = df[(df["_t"] >= dt.time(9, 30)) & (df["_t"] < dt.time(16, 0))]
        g = df.groupby("_day")
        first, last = g.head(1).set_index("_day"), g.tail(1).set_index("_day")
        tot = g["v"].sum()
        rng = lambda f: 1e4 * (f["h"] - f["l"]) / f["c"]               # noqa: E731
        ov, cv = 100 * first["v"] / tot, 100 * last["v"] / tot
        orng, crng = rng(first), rng(last)
        print(f"{s:<6}{len(tot):>9,}{ov.mean():>12.2f}{cv.mean():>12.2f}"
              f"{orng.mean():>14.2f}{crng.mean():>14.2f}{orng.mean() / crng.mean():>8.2f}")


def record(rows: list[dict], spread: float, rate_src: str) -> None:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with LEDGER.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({
                "ts": stamp, "algorithm": "daily/s23_preopen", "class": "book",
                "tag": f"S-23 {r['cell'].strip()} (pandas book, shared signals.py, "
                       f"IBKR Pro financing on {rate_src}, {spread:g} bp base spread)",
                "commit": "", "run_dir": "", "track": "S-23",
                "stats": {"Sessions": str(r["sessions"]), "Total Orders": str(r["orders"]),
                          "Compounding Annual Return": f"{r['CAR']:.3f}%",
                          "Sharpe Ratio": f"{r['Sharpe']:.3f}",
                          "Drawdown": f"{r['MaxDD']:.3f}%",
                          "Annual Standard Deviation": f"{r['std']:.3f}",
                          "Total Fees": f"${r['fees']:.2f}",
                          "Financing": f"${r.get('interest', 0.0):.2f}",
                          "End Equity": f"{r['end_equity']:.2f}"}}, default=str) + "\n")
    print(f"\n{len(rows)} rows appended to {LEDGER.relative_to(REPO)}")


def run(fin: dict, rate_src: str, args) -> list[dict]:
    params = sig.Params()
    frames = load_ohlcv(sig.traded_universe(params))
    print(f"\n=== financing on {rate_src} ===")
    print(f"store: {frames['close'].index[0].date()} .. {frames['close'].index[-1].date()}"
          f"   window {args.start} .. {args.end}   base spread {args.spread_bps:g} bp\n")

    books, rows = {}, []
    for label, fill in [("pre-open MOO (backtest convention)", "open"),
                        ("deployed 15:45 MKT", "close")]:
        b = simulate(frames, params, 0, fill, args.start, args.end, args.spread_bps, fin)
        books[label] = b
        s = summarize(b, label)
        s["interest"] = float(b["interest"].sum())
        rows.append(s)

    hdr = (f"{'cell':<38}{'sess':>6}{'CAR%':>9}{'Sharpe':>8}{'MaxDD%':>8}{'std':>7}"
           f"{'orders':>8}{'fees $':>10}{'interest $':>12}")
    print(hdr)
    for r in rows:
        print(f"{r['cell']:<38}{r['sessions']:>6}{r['CAR']:>9.3f}{r['Sharpe']:>8.3f}"
              f"{r['MaxDD']:>8.3f}{r['std']:>7.3f}{r['orders']:>8,}{r['fees']:>10,.0f}"
              f"{r['interest']:>12,.0f}")

    pre, dep = rows[0]["CAR"], rows[1]["CAR"]
    p = paired(books["pre-open MOO (backtest convention)"], books["deployed 15:45 MKT"],
               "pre-open", "deployed")
    print(f"\nthe move is worth {pre - dep:+.3f} CAR points "
          f"({dep:.3f}% -> {pre:.3f}%), paired {p['bps_per_day']:+.3f} bps/day "
          f"at t {p['t']:+.2f} on {p['days']} sessions")

    print("\nhalves (CAR%, same two conventions, same charges):")
    print(f"{'half':<26}{'pre-open':>11}{'deployed':>11}{'move':>9}")
    for name, s, e in [(f"IS {args.start[:4]}-2019", args.start, "2019-12-31"),
                       (f"OOS 2020-{args.end[:4]}", SPLIT, args.end)]:
        a = car_of(simulate(frames, params, 0, "open", s, e, args.spread_bps, fin))
        b = car_of(simulate(frames, params, 0, "close", s, e, args.spread_bps, fin))
        print(f"{name:<26}{a:>11.3f}{b:>11.3f}{a - b:>+9.3f}")

    be = breakeven(frames, params, fin, dep, args)
    print(f"\nBREAKEVEN: the opening auction may cost up to "
          f"{be['extra_bps']:.2f} bps MORE than the closing auction "
          f"({args.spread_bps:g} -> {args.spread_bps + be['extra_bps']:.2f} bp all-in) "
          f"before the move stops paying.")
    print("  for scale: the measured execution cost of the deployed 15:45 market orders is")
    print("  +3.2 bps against the close they aim at (daily_fills.py, 10 fills, se 4.5), and")
    print("  a half-cent tick on this sleeve is 0.27 bps on XLK, 0.71 on TQQQ, 0.77 on XLE (S-17).")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default=START)
    ap.add_argument("--end", default=END)
    ap.add_argument("--spread-bps", type=float, default=2.0)
    ap.add_argument("--fin-spread", type=float, default=0.0)
    ap.add_argument("--today", action="store_true",
                    help="also run on data/rates/usd_flat_2026.csv (today's benchmark)")
    ap.add_argument("--auction", action="store_true", help="minute-store liquidity proxy")
    ap.add_argument("--auction-only", action="store_true",
                    help="only the liquidity proxy (needs the default python: py -3.11 has no pyarrow)")
    ap.add_argument("--no-record", action="store_true")
    args = ap.parse_args()

    if args.auction_only:
        auction_read(["SPY", "QQQ", "IWM", "TQQQ"])
        return 0

    sources = ["data/rates/usd_benchmark.csv"]
    if args.today:
        sources.append("data/rates/usd_flat_2026.csv")

    for src in sources:
        path = REPO / src
        fin = {"rates": rates.load(path), "spread": args.fin_spread}
        rows = run(fin, path.stem, args)
        if not args.no_record:
            record(rows, args.spread_bps, path.stem)

    if args.auction:
        auction_read(["SPY", "QQQ", "IWM", "TQQQ"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
