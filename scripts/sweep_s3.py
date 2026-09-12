#!/usr/bin/env python
"""Fast walk-forward sweeps of the S-3 reversal signal, outside the LEAN engine.

Calls `algorithms/s3_reversal/signals.target_weights` day by day on LEAN's own bars, so a
sweep tests shipped code rather than a re-implementation. Costs are a flat per-unit-turnover
charge and are *crude*: S-8 measured that this harness understates LEAN's drawdown by 2
points at the champion's size and by 8-10 at twice it, and S-3 turns the whole book over
daily, so the charge matters more here than anywhere else. Choose parameters here, confirm
in `scripts/backtest.py`.

    python scripts/sweep_s3.py --mode grid          # lookback x n_side x vol_adjust
    python scripts/sweep_s3.py --mode splits        # in-sample vs out-of-sample
    python scripts/sweep_s3.py --mode sensitivity   # +/-25% shocks around the chosen set
    python scripts/sweep_s3.py --mode corr          # correlation with the S-1 champion
    python scripts/sweep_s3.py --mode pools         # megacap pool vs the honest ETF pool
    python scripts/sweep_s3.py --mode costs         # break-even cost per unit of turnover
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "algorithms" / "s3_reversal"))
sys.path.insert(0, str(REPO / "scripts"))

import signals as sig                     # noqa: E402  (s3_reversal/signals.py)
from lean_prices import load_frames       # noqa: E402

#: Round-trip cost per unit of turnover. 5bps, not the 2bps `sweep_s1.py` charges for
#: liquid ETFs: this book holds single names, whose spread is wider, and it re-forms the
#: whole book every day, so the assumption is load-bearing rather than a rounding error.
COST_BPS = 5.0
IS_END = "2019-12-31"
OOS_START = "2020-01-01"
START = "2012-01-03"


def simulate(prices, volumes, params, signal=None, start=START, end=None, cost_bps=None,
             opens=None, step_mode="c2c"):
    """Daily walk-forward. Weights decided on bar i are earned over bar i+1.

    S-36 (AUD-25) adds two default-inert arguments - the S-26/S-30/S-32 precedent on the
    daily harnesses - so every row this script has ever published stays bit-identical while
    the convention it uses becomes selectable and, more to the point, measurable.

    `step_mode="c2c"` (the shipped default) earns `close[i] -> close[i+1]` on weights decided
    at the close of bar i. LEAN fills that decision at the NEXT OPEN, so the segment
    `close[i] -> open[i+1]` is credited to a position that did not yet exist.
    `step_mode="o2o"` (needs `opens`) earns `open[i+1] -> open[i+2]` instead, which is what a
    next-open fill actually holds, on exactly the same decisions.

    S-36 PRICED THE DIFFERENCE AND THE AUDIT'S SIGN IS WRONG. On this book, full period,
    zero cost: c2c 2.559% CAR / 0.268 Sharpe against o2o 5.851% / 0.516. The shipped
    convention does not FLATTER the S-3 book by crediting it the gap - it PENALISES it by
    3.291 CAR points, because a reversal signal is on the losing side of the overnight
    segment (the gap continues the move; the reversal is an intraday phenomenon) while the
    gap is 49.9% of the average close-to-close step on this universe.

    It does not revive S-3. At this harness's own 5 bps per unit of turnover both
    conventions are deeply negative - c2c -8.967% / -0.732, o2o -4.811% / -0.330 - so the
    refusal that stands in the journal stands for the reason it was given, which was cost.
    What changes is that the margin was never as wide as the published table said.
    """
    if step_mode not in ("c2c", "o2o"):
        raise ValueError(f"step_mode must be 'c2c' or 'o2o', got {step_mode!r}")
    if step_mode == "o2o" and opens is None:
        raise ValueError("step_mode='o2o' needs an `opens` frame to fill against")
    signal = signal or sig.target_weights
    cost_bps = COST_BPS if cost_bps is None else cost_bps
    index = prices.index
    i0 = index.searchsorted(pd.Timestamp(start))
    last = len(index) - (2 if step_mode == "o2o" else 1)   # o2o needs open[i+2]
    i1 = last if end is None else min(index.searchsorted(pd.Timestamp(end)), last)
    equity, dates = [100_000.0], []
    state, prev = {}, {}
    grosses, turnovers, invested = [], [], 0

    for i in range(i0, i1):
        lo = max(0, i - params.history_bars + 1)
        window = prices.iloc[lo:i + 1]
        vol_window = None if volumes is None else volumes.iloc[lo:i + 1]
        weights, diag = signal(window, equity, params, state, volumes=vol_window)
        state = diag.get("state", {})
        if weights:
            invested += 1
            grosses.append(sum(abs(w) for w in weights.values()))

        turnover = sum(abs(weights.get(t, 0.0) - prev.get(t, 0.0))
                       for t in set(weights) | set(prev))
        turnovers.append(turnover)
        step = (prices.iloc[i + 1] / prices.iloc[i] - 1.0 if step_mode == "c2c"
                else opens.iloc[i + 2] / opens.iloc[i + 1] - 1.0)
        gain = sum(w * step[t] for t, w in weights.items()
                   if t in step.index and np.isfinite(step[t]))
        equity.append(equity[-1] * (1.0 + gain) - equity[-1] * turnover * cost_bps / 1e4)
        dates.append(index[i + 1])
        prev = weights

    curve = pd.Series(equity[1:], index=dates)
    return curve, {
        "invested_share": invested / max(1, len(turnovers)),
        "mean_gross": float(np.mean(grosses)) if grosses else 0.0,
        "daily_turnover": float(np.mean(turnovers)),
        "rebalances": len(turnovers),
    }


def metrics(curve, extra=None):
    rets = curve.pct_change().dropna()
    years = (curve.index[-1] - curve.index[0]).days / 365.25
    out = {
        "CAR": (curve.iloc[-1] / curve.iloc[0]) ** (1 / years) - 1 if years > 0 else float("nan"),
        "Sharpe": rets.mean() / rets.std() * np.sqrt(sig.TRADING_DAYS) if rets.std() > 0 else float("nan"),
        "MaxDD": (1 - curve / curve.cummax()).max(),
        "Vol": rets.std() * np.sqrt(sig.TRADING_DAYS),
    }
    out.update(extra or {})
    return out


def row(label, m):
    print(f"{label:<42} CAR {m['CAR']:8.1%}  Sharpe {m['Sharpe']:6.2f}  MaxDD {m['MaxDD']:7.1%}  "
          f"Vol {m['Vol']:6.1%}  inv {m.get('invested_share', 0):5.1%}  "
          f"gross {m.get('mean_gross', 0):4.2f}  turn {m.get('daily_turnover', 0):.2f}")


def run(prices, volumes, params, label, **kw):
    curve, extra = simulate(prices, volumes, params, **kw)
    m = metrics(curve, extra)
    row(label, m)
    return m, curve


def s1_curve(prices, volumes, start=START, end=None):
    """The champion's equity curve in this same harness, for correlation work."""
    s1 = sig.s1
    return simulate(prices, volumes, s1.DEFAULTS, signal=s1.target_weights,
                    start=start, end=end, cost_bps=2.0)[0]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", default="grid",
                    choices=["grid", "splits", "sensitivity", "corr", "pools", "costs"])
    ap.add_argument("--cost", type=float, default=COST_BPS,
                    help="cost per unit of turnover, bps. --cost 0 isolates the raw signal "
                         "from the cost drag, which is the only way to tell a dead edge "
                         "from an edge that is merely too expensive.")
    args = ap.parse_args()
    globals()["COST_BPS"] = args.cost

    P = sig.DEFAULTS
    tickers = sorted(set(sig.traded_universe(P)) | set(sig.s1.TRADED_UNIVERSE)
                     | set(sig.POOLS["etf"]))
    prices, volumes = load_frames(tickers, start="2009-06-01")
    print(f"data: {prices.shape[0]} bars {prices.index[0].date()} .. {prices.index[-1].date()}, "
          f"{prices.shape[1]} tickers   cost {COST_BPS}bps/turnover\n")

    if args.mode == "grid":
        print("-- horizon and breadth (megacap pool, top-30 by liquidity) --")
        for vol_adjust in (True, False):
            for lookback in (1, 2, 3, 5, 10):
                for n_side in (3, 5, 10):
                    p = replace(P, lookback=lookback, n_side=n_side, vol_adjust=vol_adjust)
                    run(prices, volumes, p,
                        f"lb={lookback:<2} n={n_side:<2} vol_adj={int(vol_adjust)}")
            print()

    elif args.mode == "splits":
        # The shipped defaults are the grid's best zero-cost cell, so the honest question
        # is no longer "which parameters" but "is the sign stable, and does either sign
        # survive costs". Both directions, both halves, gross and net of the cost charge.
        for direction, name in ((1, "reversal (buy losers)"), (-1, "continuation (buy winners)")):
            p = replace(P, direction=direction)
            print(f"-- {name} --")
            for cost in (0.0, args.cost):
                run(prices, volumes, p, f"  IS 2012-2019  @{cost:>4.1f}bps", end=IS_END, cost_bps=cost)
                run(prices, volumes, p, f"  OOS 2020-2026 @{cost:>4.1f}bps", start=OOS_START, cost_bps=cost)
                run(prices, volumes, p, f"  full          @{cost:>4.1f}bps", cost_bps=cost)
            print()

    elif args.mode == "sensitivity":
        base, _ = run(prices, volumes, P, "base")
        for name, values in [("lookback", (2, 4)), ("n_side", (4, 6)), ("universe_size", (22, 38)),
                             ("vol_window", (15, 25)), ("target_vol", (0.15, 0.25)),
                             ("margin_budget", (0.56, 0.94)), ("dd_halve", (0.11, 0.19))]:
            for v in values:
                run(prices, volumes, replace(P, **{name: v}), f"{name}={v}")
        for f in (0.75, 1.25):
            run(prices, volumes, P.scaled(f), f"all horizons x{f}")
        print(f"\nbase Sharpe {base['Sharpe']:.2f}, CAR {base['CAR']:.1%}, MaxDD {base['MaxDD']:.1%}")

    elif args.mode == "corr":
        print("-- correlation with the S-1 champion (same harness, same days) --")
        champ = s1_curve(prices, volumes)
        for direction in (1, -1):
            p = replace(P, direction=direction)
            m, curve = run(prices, volumes, p, f"S-3 direction={direction:+d}")
            a = curve.pct_change().dropna()
            b = champ.pct_change().dropna()
            joined = pd.concat([a, b], axis=1, join="inner").dropna()
            rho = float(joined.corr().iloc[0, 1])
            # 50/50 blend of the two return streams, rebalanced daily.
            blend = (joined.iloc[:, 0] + joined.iloc[:, 1]) / 2.0
            bs = blend.mean() / blend.std() * np.sqrt(sig.TRADING_DAYS)
            bdd = (1 - (1 + blend).cumprod() / (1 + blend).cumprod().cummax()).max()
            print(f"    corr with champion {rho:+.3f}   50/50 blend Sharpe {bs:.2f} "
                  f"vol {blend.std() * np.sqrt(sig.TRADING_DAYS):.1%} MaxDD {bdd:.1%}")
        mc = metrics(champ)
        row("S-1 champion (this harness)", mc)

    elif args.mode == "pools":
        for pool, size in [("megacap", 30), ("megacap", 50), ("wide", 30), ("etf", 0)]:
            p = replace(P, pool=pool, universe_size=size,
                        n_side=3 if pool == "etf" else P.n_side)
            run(prices, volumes, p, f"pool={pool} size={size}")

    elif args.mode == "costs":
        print("-- break-even: what does the edge survive? --")
        for cost in (0.0, 2.0, 5.0, 10.0, 15.0, 20.0):
            run(prices, volumes, P, f"cost {cost:>4.1f} bps/turnover", cost_bps=cost)

    return 0


if __name__ == "__main__":
    sys.exit(main())
