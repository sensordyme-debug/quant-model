#!/usr/bin/env python
"""Fast walk-forward sweeps of the S-1 signal, outside the LEAN engine.

Calls `algorithms/s1_momo/signals.target_weights` day by day on LEAN's own bars, so a
sweep tests the code that ships rather than a re-implementation of it. Fees are a flat
per-unit-turnover charge, which is deliberately cruder than LEAN's fee model: use this
to *choose* parameters, then confirm the chosen set with scripts/backtest.py.

    python scripts/sweep_s1.py --mode ablation     # what each component contributes
    python scripts/sweep_s1.py --mode grid         # parameter grid, full period
    python scripts/sweep_s1.py --mode sensitivity  # +/-25% shocks around the default
    python scripts/sweep_s1.py --mode splits       # in-sample vs out-of-sample
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "algorithms" / "s1_momo"))
sys.path.insert(0, str(REPO / "scripts"))

import signals as sig                     # noqa: E402
from lean_prices import load_closes       # noqa: E402

COST_BPS = 2.0          # round-trip cost per unit of turnover; IBKR on liquid ETFs
IS_END = "2019-12-31"
OOS_START = "2020-01-01"


def simulate(prices: pd.DataFrame, params: sig.Params, start="2012-01-03", end=None):
    """Daily walk-forward. Weights decided on bar i are earned over bar i+1."""
    index = prices.index
    i0 = index.searchsorted(pd.Timestamp(start))
    i1 = len(index) - 1 if end is None else min(index.searchsorted(pd.Timestamp(end)), len(index) - 1)
    equity, dates = [100_000.0], []
    state, prev = {}, {}
    exposures, turnovers, invested = [], [], 0

    for i in range(i0, i1):
        window = prices.iloc[max(0, i - params.history_bars + 1):i + 1]
        weights, diag = sig.target_weights(window, equity, params, state)
        state = diag.get("state", {})
        if weights:
            invested += 1
            exposures.append(diag.get("effective_exposure", 0.0))

        turnover = sum(abs(weights.get(t, 0.0) - prev.get(t, 0.0))
                       for t in set(weights) | set(prev))
        turnovers.append(turnover)
        step = prices.iloc[i + 1] / prices.iloc[i] - 1.0
        gain = sum(w * step[t] for t, w in weights.items() if np.isfinite(step[t]))
        equity.append(equity[-1] * (1.0 + gain) - equity[-1] * turnover * COST_BPS / 1e4)
        dates.append(index[i + 1])
        prev = weights

    curve = pd.Series(equity[1:], index=dates)
    return curve, {
        "invested_share": invested / max(1, len(turnovers)),
        "mean_exposure": float(np.mean(exposures)) if exposures else 0.0,
        "daily_turnover": float(np.mean(turnovers)),
        "rebalances": len(turnovers),
    }


def metrics(curve: pd.Series, extra: dict | None = None) -> dict:
    rets = curve.pct_change().dropna()
    years = (curve.index[-1] - curve.index[0]).days / 365.25
    vol = rets.std() * np.sqrt(sig.TRADING_DAYS)
    out = {
        "CAR": (curve.iloc[-1] / curve.iloc[0]) ** (1 / years) - 1 if years > 0 else float("nan"),
        "Sharpe": rets.mean() / rets.std() * np.sqrt(sig.TRADING_DAYS) if rets.std() > 0 else float("nan"),
        "MaxDD": (1 - curve / curve.cummax()).max(),
        "Vol": vol,
    }
    out.update(extra or {})
    return out


def row(label: str, m: dict):
    print(f"{label:<40} CAR {m['CAR']:8.1%}  Sharpe {m['Sharpe']:6.2f}  MaxDD {m['MaxDD']:7.1%}  "
          f"Vol {m['Vol']:6.1%}  inv {m.get('invested_share', 0):5.1%}  "
          f"exp {m.get('mean_exposure', 0):4.2f}x  turn {m.get('daily_turnover', 0):.2f}")


def run(prices, params, label, start="2012-01-03", end=None):
    curve, extra = simulate(prices, params, start, end)
    m = metrics(curve, extra)
    row(label, m)
    return m


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", default="ablation",
                    choices=["ablation", "grid", "sensitivity", "splits", "regimes", "margin"])
    args = ap.parse_args()

    prices = load_closes(sig.TRADED_UNIVERSE, start="2009-06-01")
    print(f"data: {prices.shape[0]} bars {prices.index[0].date()} .. {prices.index[-1].date()}, "
          f"{prices.shape[1]} tickers\n")
    P = sig.DEFAULTS

    if args.mode == "ablation":
        print("=== component ablation, 2012-2026 ===")
        run(prices, P, "S-1 default")
        run(prices, replace(P, trend_window=0), "no trend filter")
        run(prices, replace(P, regime_threshold=99.0), "no crisis-vol filter")
        run(prices, replace(P, trend_window=0, regime_threshold=99.0), "no regime filter at all")
        run(prices, replace(P, dd_halve=9.0, dd_flat=9.0), "no drawdown overlay")
        run(prices, replace(P, target_vol=99.0), "no vol target (exposure fixed)")
        run(prices, replace(P, target_exposure=1.0, max_gross_weight=1.0), "unlevered, cash only")
        run(prices, replace(P, regime_threshold=1.0), "spec's original vol<median filter")
        print("\n=== benchmarks ===")
        for ticker in ["SPY", "QQQ", "TQQQ"]:
            series = prices[ticker].loc["2012-01-03":]
            row(f"{ticker} buy & hold", metrics(series))

    elif args.mode == "grid":
        print("=== parameter grid, 2012-2026 ===")
        for gross in [0.95, 1.0, 1.15, 1.3]:
            for tv in [0.40, 0.55, 0.75]:
                for cap in [2.0, 3.0]:
                    run(prices, replace(P, max_gross_weight=gross, target_vol=tv,
                                        scale_cap=cap),
                        f"gross={gross} tv={tv:.0%} cap={cap}")

    elif args.mode == "sensitivity":
        print("=== +/-25% shocks around the default (full period) ===")
        run(prices, P, "default")
        for factor in (0.75, 1.25):
            run(prices, P.scaled(factor), f"lookbacks & vol threshold x{factor}")
            run(prices, replace(P, mom_lookbacks=tuple(max(2, int(round(lb * factor)))
                                                       for lb in P.mom_lookbacks)),
                f"lookbacks x{factor}")
            run(prices, replace(P, regime_threshold=P.regime_threshold * factor),
                f"vol threshold x{factor}")
            run(prices, replace(P, target_vol=P.target_vol * factor), f"target_vol x{factor}")
            run(prices, replace(P, trend_window=int(P.trend_window * factor)),
                f"trend_window x{factor}")
            run(prices, replace(P, target_exposure=P.target_exposure * factor),
                f"target_exposure x{factor}")
        for top_n in (2, 4):
            run(prices, replace(P, top_n=top_n), f"top_n={top_n}")

    elif args.mode == "margin":
        # S-6: how much size does the margin budget buy, and where does drawdown break?
        # Judged in and out of sample separately, because a size increase is exactly the
        # kind of change that looks free on the half of the sample that only went up.
        print("=== S-6 margin budget, target_exposure held at the default ===")
        for budget in [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]:
            run(prices, replace(P, margin_budget=budget), f"margin_budget={budget}")
        print("\n=== budget x target_exposure (the budget only binds if size is asked for) ===")
        for budget in [1.0, 1.5, 2.0]:
            for te in [1.75, 2.5, 3.5]:
                run(prices, replace(P, margin_budget=budget, target_exposure=te),
                    f"budget={budget} target_exposure={te}")
        print("\n=== chosen budgets, in vs out of sample ===")
        for budget in [1.0, 1.5, 2.0]:
            params = replace(P, margin_budget=budget)
            print(f"\n--- margin_budget={budget} ---")
            run(prices, params, "  IS  2012-2019", start="2012-01-03", end=IS_END)
            run(prices, params, "  OOS 2020-2026", start=OOS_START)
            run(prices, params, "  full 2012-2026")
        print("\n--- benchmarks ---")
        for ticker in ["SPY", "QQQ"]:
            row(f"  {ticker} full 2012-2026", metrics(prices[ticker].loc["2012-01-03":]))

    elif args.mode == "regimes":
        print("=== regime filter choice, judged separately in and out of sample ===")
        variants = {
            "trend200 + crisis vol": P,
            "crisis vol only": replace(P, trend_window=0),
            "trend200 only": replace(P, regime_threshold=99.0),
            "no regime filter": replace(P, trend_window=0, regime_threshold=99.0),
        }
        for name, params in variants.items():
            print(f"\n--- {name} ---")
            run(prices, params, "  IS  2012-2019", start="2012-01-03", end=IS_END)
            run(prices, params, "  OOS 2020-2026", start=OOS_START)
            run(prices, params, "  full 2012-2026")
        print("\n--- benchmarks ---")
        for ticker in ["SPY", "QQQ"]:
            row(f"  {ticker} IS  2012-2019", metrics(prices[ticker].loc["2012-01-03":IS_END]))
            row(f"  {ticker} OOS 2020-2026", metrics(prices[ticker].loc[OOS_START:]))

    elif args.mode == "splits":
        print("=== in-sample / out-of-sample ===")
        run(prices, P, "IS  2012-2019", start="2012-01-03", end=IS_END)
        run(prices, P, "OOS 2020-2026", start=OOS_START)
        run(prices, P, "full 2012-2026")
        print()
        for ticker in ["SPY", "QQQ"]:
            row(f"{ticker} IS  2012-2019", metrics(prices[ticker].loc["2012-01-03":IS_END]))
            row(f"{ticker} OOS 2020-2026", metrics(prices[ticker].loc[OOS_START:]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
