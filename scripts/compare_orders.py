#!/usr/bin/env python
"""I-1 pre-deploy gate: does the paper runner place the same orders as the backtest?

The signal itself cannot diverge - `algorithms/s1_momo/signals.py` is imported by both
`algorithms/s1_momo/main.py` (LEAN) and `scripts/paper_trade.py` (IBKR). What *can*
diverge is everything after it: the arithmetic that turns target weights into integer
share deltas, and the no-trade band that decides which of those deltas are worth
sending. Those are two separate implementations of the same rule -
`main.py:submit_targets` and `paper_trade.py:plan_orders` - and nothing until now
compared them.

This script does. It walks LEAN's own daily bars with the shipped signal, maintaining a
share-level book the way `submit_targets` does, and at every decision date it hands
*identical* inputs (targets, positions, prices, equity) to both implementations and
diffs the resulting order lists. Because the inputs are identical by construction, any
disagreement is purely an execution-layer divergence - it cannot be a data or signal
artifact.

`plan_orders` is imported from `scripts/paper_trade.py` itself, not copied, so this
tests the code that will actually trade.

    py -3.11 scripts/compare_orders.py                      # full period
    py -3.11 scripts/compare_orders.py --start 2024-01-01   # recent slice
    py -3.11 scripts/compare_orders.py --verbose            # show the first differences

Exit code is 0 when the two agree on every date and 1 otherwise, so the paper-deploy
checklist can gate on it.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "algorithms" / "s1_momo"))
sys.path.insert(0, str(REPO / "scripts"))

import signals as sig                     # noqa: E402
from lean_prices import load_frames       # noqa: E402
import paper_trade as pt                  # noqa: E402

#: The band `main.py` ships (`self.min_order_value`). Kept here as the reference value
#: the runner is checked against; override with --min-order-value to explore.
LEAN_MIN_ORDER_VALUE = 0.01


def lean_deltas(targets, positions, prices, equity, min_order_value, tickers):
    """Reproduce `main.py:submit_targets` exactly: integer shares, band as a fraction of equity.

    Iterates the whole traded universe rather than just the target names, because a name
    that has dropped out of the book still needs its position sold down to zero.
    """
    out = {}
    for ticker in tickers:
        px = float(prices.get(ticker, 0.0) or 0.0)
        held = int(positions.get(ticker, 0))
        target = 0 if px <= 0 else int(targets.get(ticker, 0.0) * equity / px)
        if abs(target - held) * max(px, 0.01) >= min_order_value * equity:
            out[ticker] = target - held
    return out


def runner_deltas(targets, positions, prices, equity):
    """Whatever `paper_trade.plan_orders` would send, as {ticker: delta}."""
    plan = pt.plan_orders(targets, positions, prices, equity)
    return {sym: delta for sym, delta, _px, _tgt, _cur in plan if delta}


def walk(prices, params, start, end, min_order_value, verbose=0):
    """Step the champion signal through history and diff the two order lists each day.

    The book is advanced using LEAN's rule, since LEAN is the reference the champion's
    `OrderListHash` was measured on; the runner is scored against that same state.
    """
    tickers = sig.traded_universe(params)
    index = prices.index
    i0 = index.searchsorted(pd.Timestamp(start))
    i1 = len(index) - 1 if end is None else min(index.searchsorted(pd.Timestamp(end)), len(index) - 1)

    equity_curve = [100_000.0]
    positions: dict[str, int] = {}
    state: dict = {}
    dates = disagreements = 0
    lean_orders = run_orders = 0
    shown = 0
    causes: dict[str, int] = {}

    for i in range(i0, i1):
        lo = max(0, i - params.history_bars + 1)
        window = prices.iloc[lo:i + 1]
        bar = prices.iloc[i]
        equity = equity_curve[-1]

        targets, diag = sig.target_weights(window, equity_curve, params, state)
        state = diag.get("state", {})
        px = {t: float(bar[t]) for t in tickers if t in bar.index and pd.notna(bar[t])}

        a = lean_deltas(targets, positions, px, equity, min_order_value, tickers)
        b = runner_deltas(targets, positions, px, equity)

        dates += 1
        lean_orders += len(a)
        run_orders += len(b)
        if a != b:
            disagreements += 1
            for t in sorted(set(a) | set(b)):
                if a.get(t, 0) == b.get(t, 0):
                    continue
                if t not in a:
                    causes["runner sends an order LEAN bands out"] = causes.get(
                        "runner sends an order LEAN bands out", 0) + 1
                elif t not in b:
                    causes["LEAN sends an order the runner bands out"] = causes.get(
                        "LEAN sends an order the runner bands out", 0) + 1
                else:
                    causes["different share count"] = causes.get("different share count", 0) + 1
            if verbose and shown < verbose:
                shown += 1
                print(f"\n  {index[i].date()}  equity {equity:,.0f}")
                for t in sorted(set(a) | set(b)):
                    if a.get(t, 0) != b.get(t, 0):
                        note = f"notional {abs(b.get(t, a.get(t, 0))) * px.get(t, 0):,.0f}"
                        print(f"    {t:<6} LEAN {a.get(t, 0):>+8}   runner {b.get(t, 0):>+8}   {note}")

        # Advance the book on LEAN's rule, marking to the next close.
        for t, d in a.items():
            positions[t] = positions.get(t, 0) + d
        nxt = prices.iloc[i + 1]
        cash = equity - sum(positions.get(t, 0) * px.get(t, 0.0) for t in positions)
        value = cash + sum(n * float(nxt[t]) for t, n in positions.items()
                           if t in nxt.index and pd.notna(nxt[t]))
        equity_curve.append(value)

    return {
        "dates": dates,
        "disagreements": disagreements,
        "lean_orders": lean_orders,
        "runner_orders": run_orders,
        "causes": causes,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2012-01-03")
    ap.add_argument("--end", default=None)
    ap.add_argument("--min-order-value", type=float, default=LEAN_MIN_ORDER_VALUE,
                    help="the band main.py uses; the runner is checked against it")
    ap.add_argument("--verbose", type=int, default=0, metavar="N",
                    help="print the first N disagreeing dates in full")
    args = ap.parse_args()

    params = sig.Params()
    prices, _volumes = load_frames(sig.traded_universe(params))
    print(f"comparing algorithms/s1_momo/main.py:submit_targets (band "
          f"{args.min_order_value:g} x equity)")
    print(f"     with scripts/paper_trade.py:plan_orders   (band "
          f"{pt.MIN_NOTIONAL:,.0f} flat + {getattr(pt, 'MIN_ORDER_VALUE', 0.0):g} x equity)")

    r = walk(prices, params, args.start, args.end, args.min_order_value, args.verbose)

    agree = r["dates"] - r["disagreements"]
    print(f"\ndecision dates      {r['dates']}")
    print(f"dates in agreement  {agree}  ({agree / max(1, r['dates']):.1%})")
    print(f"orders: LEAN {r['lean_orders']:,}   runner {r['runner_orders']:,}   "
          f"({r['runner_orders'] - r['lean_orders']:+,})")
    if r["causes"]:
        print("\ndisagreements by cause:")
        for k, v in sorted(r["causes"].items(), key=lambda kv: -kv[1]):
            print(f"  {v:>7,}  {k}")
        print("\nFAIL: the paper runner would not reproduce the backtest's order list.")
        return 1
    print("\nPASS: the runner reproduces the backtest's order list on every date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
