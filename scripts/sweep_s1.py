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
import universe as uni                    # noqa: E402
from lean_prices import load_frames       # noqa: E402

COST_BPS = 2.0          # round-trip cost per unit of turnover; IBKR on liquid ETFs
IS_END = "2019-12-31"
OOS_START = "2020-01-01"


def simulate(prices: pd.DataFrame, params: sig.Params, start="2012-01-03", end=None,
             volumes: pd.DataFrame | None = None):
    """Daily walk-forward. Weights decided on bar i are earned over bar i+1."""
    index = prices.index
    i0 = index.searchsorted(pd.Timestamp(start))
    i1 = len(index) - 1 if end is None else min(index.searchsorted(pd.Timestamp(end)), len(index) - 1)
    equity, dates = [100_000.0], []
    state, prev = {}, {}
    exposures, turnovers, invested = [], [], 0
    members = []

    for i in range(i0, i1):
        lo = max(0, i - params.history_bars + 1)
        window = prices.iloc[lo:i + 1]
        vol_window = None if volumes is None else volumes.iloc[lo:i + 1]
        weights, diag = sig.target_weights(window, equity, params, state, volumes=vol_window)
        state = diag.get("state", {})
        if diag.get("universe_members"):
            members.append(set(diag["universe_members"]))
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
    extra = {
        "invested_share": invested / max(1, len(turnovers)),
        "mean_exposure": float(np.mean(exposures)) if exposures else 0.0,
        "daily_turnover": float(np.mean(turnovers)),
        "rebalances": len(turnovers),
    }
    if members:
        # How much did the point-in-time sleeve actually move? A membership that never
        # changes is the S-7 fixed list wearing a different hat.
        churn = [len(b - a) for a, b in zip(members, members[1:])]
        extra["universe_churn"] = float(np.mean(churn)) if churn else 0.0
        extra["universe_names"] = len(set().union(*members))
    return curve, extra


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
    line = (f"{label:<40} CAR {m['CAR']:8.1%}  Sharpe {m['Sharpe']:6.2f}  MaxDD {m['MaxDD']:7.1%}  "
            f"Vol {m['Vol']:6.1%}  inv {m.get('invested_share', 0):5.1%}  "
            f"exp {m.get('mean_exposure', 0):4.2f}x  turn {m.get('daily_turnover', 0):.2f}")
    if "universe_churn" in m:
        line += f"  churn {m['universe_churn']:.3f}/day  names {m['universe_names']}"
    print(line)


def run(prices, params, label, start="2012-01-03", end=None, volumes=None):
    curve, extra = simulate(prices, params, start, end, volumes)
    m = metrics(curve, extra)
    row(label, m)
    return m


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", default="ablation",
                    choices=["ablation", "grid", "sensitivity", "splits", "regimes", "margin",
                             "s7", "s7bias", "d3", "s8", "s8vol", "s9"])
    ap.add_argument("--section", type=int, default=0,
                    help="run one numbered section of the sweep (0 = all). A full-period "
                         "simulation costs ~22s, so a long sweep is split to stay inside a "
                         "single shell timeout.")
    args = ap.parse_args()

    tickers = sig.TRADED_UNIVERSE
    if args.mode in ("s7", "s7bias", "d3"):
        tickers = sorted(set(tickers) | set(sig.MEGACAP_SLEEVE))
    prices, volumes = load_frames(tickers, start="2009-06-01")
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

    elif args.mode == "s7":
        # S-7: beat buy-and-hold on absolute return. Three levers, each judged in and out
        # of sample separately, because a return increase is exactly what a bull-market
        # half of the sample hands out for free.
        ETF = tuple(sig.RANK_UNIVERSE)
        WIDE = ETF + tuple(sig.MEGACAP_SLEEVE)
        print("=== 1. weighting scheme (universe and top_n at default) ===")
        for mode in ["equal", "rank", "momentum"]:
            params = replace(P, weight_mode=mode)
            print(f"\n--- weight_mode={mode} ---")
            run(prices, params, "  IS  2012-2019", start="2012-01-03", end=IS_END)
            run(prices, params, "  OOS 2020-2026", start=OOS_START)
            run(prices, params, "  full 2012-2026")

        print("\n=== 2. top_n on the ETF sleeve ===")
        for top_n in [2, 3, 4, 5, 6]:
            params = replace(P, top_n=top_n)
            print(f"\n--- top_n={top_n} ---")
            run(prices, params, "  IS  2012-2019", start="2012-01-03", end=IS_END)
            run(prices, params, "  OOS 2020-2026", start=OOS_START)
            run(prices, params, "  full 2012-2026")

        print("\n=== 3. ranking sleeve (megacap names are 2026's list: selection bias) ===")
        for name, universe_, top_n in [("etf-9", ETF, 3), ("etf+megacap-59", WIDE, 3),
                                       ("etf+megacap-59", WIDE, 5),
                                       ("etf+megacap-59", WIDE, 8),
                                       ("megacap-50", tuple(sig.MEGACAP_SLEEVE), 5)]:
            params = replace(P, rank_universe=universe_, top_n=top_n)
            print(f"\n--- {name}, top_n={top_n} ---")
            run(prices, params, "  IS  2012-2019", start="2012-01-03", end=IS_END)
            run(prices, params, "  OOS 2020-2026", start=OOS_START)
            run(prices, params, "  full 2012-2026")

        print("\n=== benchmarks ===")
        for ticker in ["SPY", "QQQ"]:
            row(f"  {ticker} IS  2012-2019", metrics(prices[ticker].loc["2012-01-03":IS_END]))
            row(f"  {ticker} OOS 2020-2026", metrics(prices[ticker].loc[OOS_START:]))
            row(f"  {ticker} full 2012-2026", metrics(prices[ticker].loc["2012-01-03":]))

    elif args.mode == "s8":
        # S-8: reach the volatility mandate without breaching the 35% drawdown limit.
        # The champion runs at 16.5% vol because a constant margin budget binds every day;
        # simply raising it to 1.0 buys 2.07x exposure and a 35.4% drawdown, which fails.
        # So size has to be *paid for* with a better drawdown profile. Four levers, each
        # judged in and out of sample, then the survivors combined - a drawdown improvement
        # is exactly the thing that shows up for free on whichever half had no crisis.
        def both(params, label):
            print(f"\n--- {label} ---")
            run(prices, params, "  IS  2012-2019", start="2012-01-03", end=IS_END)
            run(prices, params, "  OOS 2020-2026", start=OOS_START)
            return run(prices, params, "  full 2012-2026")

        print("=== 0. baselines: the champion, and what raw size costs ===")
        both(P, "champion (budget=0.75, top_n=3)")
        both(replace(P, margin_budget=1.0), "budget=1.0, nothing paid for it")

        print("\n=== 1. top_n: S-7 measured 5-6 as cheaper in drawdown at equal return ===")
        for top_n in [3, 5, 6]:
            both(replace(P, top_n=top_n, margin_budget=1.0), f"top_n={top_n} budget=1.0")

        print("\n=== 2. an earlier, cheaper breaker (dd_halve / dd_flat / taper) ===")
        for halve, flat, mode in [(0.15, 0.25, "step"), (0.10, 0.25, "step"),
                                  (0.08, 0.20, "step"), (0.15, 0.25, "taper"),
                                  (0.10, 0.25, "taper"), (0.10, 0.20, "taper")]:
            both(replace(P, margin_budget=1.0, dd_halve=halve, dd_flat=flat, dd_mode=mode),
                 f"dd {halve}/{flat} {mode} budget=1.0")

        print("\n=== 3. per-holding trailing stop ===")
        for stop, window in [(0.10, 60), (0.15, 60), (0.20, 60), (0.15, 120), (0.25, 120)]:
            both(replace(P, margin_budget=1.0, trail_stop=stop, trail_window=window),
                 f"trail {stop:.0%}/{window}d budget=1.0")

        print("\n=== 4. elastic budget: spend the vol target's ask, clipped ===")
        for floor, cap in [(0.3, 1.0), (0.3, 1.25), (0.4, 1.5), (0.2, 1.5), (0.3, 2.0)]:
            both(replace(P, scale_cap=6.0, margin_budget_floor=floor, margin_budget_cap=cap),
                 f"elastic budget [{floor}, {cap}] scale_cap=6")

        print("\n--- benchmarks ---")
        for ticker in ["SPY", "QQQ"]:
            row(f"  {ticker} IS  2012-2019", metrics(prices[ticker].loc["2012-01-03":IS_END]))
            row(f"  {ticker} OOS 2020-2026", metrics(prices[ticker].loc[OOS_START:]))
            row(f"  {ticker} full 2012-2026", metrics(prices[ticker].loc["2012-01-03":]))

    elif args.mode == "s8vol":
        # S-8, second pass. The elastic budget in --mode s8 barely moved anything, and the
        # reason is in the numbers: the book realizes ~24% vol against a 40% target, so
        # `target_vol / sigma` is above every ceiling on essentially every day. The vol
        # target is *saturated*, which means the strategy has never actually vol-targeted -
        # it carries a constant margin and takes the whole of a crisis at full size.
        # Lowering the target to something the book can reach is what turns the elastic
        # budget from a no-op into a risk control.
        def both(params, label):
            print(f"\n--- {label} ---")
            run(prices, params, "  IS  2012-2019", start="2012-01-03", end=IS_END)
            run(prices, params, "  OOS 2020-2026", start=OOS_START)
            return run(prices, params, "  full 2012-2026")

        print("=== elastic budget with a reachable vol target ===")
        for tv in [0.18, 0.22, 0.26, 0.30]:
            for cap in [1.25, 1.75]:
                both(replace(P, scale_cap=6.0, target_vol=tv, margin_budget_floor=0.2,
                             margin_budget_cap=cap, max_gross_weight=3.0),
                     f"target_vol={tv:.0%} elastic [0.2, {cap}] gross<=3")

        print("\n=== control: the same reachable target under the flat budget ===")
        for tv in [0.22, 0.26]:
            both(replace(P, target_vol=tv, margin_budget=1.0), f"target_vol={tv:.0%} flat 1.0")

        # Reg-T is the real ceiling: initial margin of 1.0 already means 2.0x gross on an
        # ordinary ETF, so a budget above 1.0 is only reachable under portfolio margin and
        # is not something the I-1 paper account can execute. These are the shippable ones.
        print("\n=== executable: budget capped at Reg-T, gross at the champion's 2.0 ===")
        for tv in [0.24, 0.26, 0.28, 0.32]:
            both(replace(P, scale_cap=6.0, target_vol=tv, margin_budget_floor=0.2,
                         margin_budget_cap=1.0),
                 f"target_vol={tv:.0%} elastic [0.2, 1.0] gross<=2")

    elif args.mode == "s9":
        # S-9: a different *signal* on the honest ETF-9 sleeve. Everything since S-6 has
        # changed size or universe and none of it moved the champion, so this changes what
        # gets ranked and what qualifies. Four levers, each judged in and out of sample,
        # then the survivors combined. Turnover is printed because S-3 measured a 2.1bps
        # commission floor per unit of turnover at this account size: a cell that wins on
        # gross return while doubling turnover is not a win.
        def both(params, label):
            print(f"\n--- {label} ---")
            run(prices, params, "  IS  2012-2019", start="2012-01-03", end=IS_END)
            run(prices, params, "  OOS 2020-2026", start=OOS_START)
            return run(prices, params, "  full 2012-2026")

        def section(n):
            return args.section in (0, n)

        if section(1):
            print("=== 0. baseline: the champion signal ===")
            base = both(P, "champion (blend, absolute floor, top_n=3)")
            print("\n=== 1. scoring scheme: equalize the horizons, or risk-adjust them ===")
            for mode in ["zscore", "riskadj"]:
                both(replace(P, mom_score=mode), f"mom_score={mode}")
            print(f"\nchampion full-period bar to beat: CAR {base['CAR']:.1%} "
                  f"Sharpe {base['Sharpe']:.2f} MaxDD {base['MaxDD']:.1%} "
                  f"turn {base['daily_turnover']:.2f}")

        if section(2):
            print("\n=== 2. risk-adjusted momentum, vol window; horizon agreement ===")
            for window in [20, 120]:
                both(replace(P, mom_score="riskadj", mom_vol_window=window),
                     f"mom_score=riskadj vol_window={window}")
            both(replace(P, mom_confirm=True), "mom_confirm on (blend)")

        if section(3):
            print("\n=== 3. cross-sectional entry gate vs the absolute floor ===")
            for rel in [0.0, 0.03, 0.08]:
                both(replace(P, entry_mode="median", min_rel_momentum=rel),
                     f"entry=median +{rel:.0%} (blend)")

        if section(4):
            print("\n=== 4. a second momentum horizon set ===")
            for lookbacks in [(10, 40, 120), (20, 60, 120, 250), (60, 120, 250)]:
                both(replace(P, mom_lookbacks=lookbacks), f"lookbacks={lookbacks}")

        if section(5):
            # `riskadj` is monotone in its vol window (20 > 60 > 120) and only the 20-day
            # end beats the champion, so the shortest window is at the *edge* of the tested
            # grid. Either the edge is a plateau, in which case the lever is real and the
            # exact window does not matter, or it is a spike, in which case section 2 found
            # one lucky cell. This is the question, not a search for a better number.
            print("\n=== 5. is the riskadj vol window a plateau or a spike? ===")
            for window in [5, 10, 15, 30, 40]:
                both(replace(P, mom_score="riskadj", mom_vol_window=window),
                     f"mom_score=riskadj vol_window={window}")

        if section(6):
            # Adding a 250-day horizon beat the champion on both halves *and* cut turnover.
            # Before believing it, separate the two things it could be: a genuine 12-month
            # momentum horizon, or just a fourth vote diluting the noisy 20-day one. If the
            # effect is the horizon, sets built around 250 win without needing four members
            # and the exact length does not matter much; if it is dilution, only the
            # four-member set wins.
            print("\n=== 6. is it the 12-month horizon, or just a fourth vote? ===")
            for lookbacks in [(250,), (120, 250), (20, 250), (20, 60, 120, 200),
                              (20, 60, 120, 300)]:
                both(replace(P, mom_lookbacks=lookbacks), f"lookbacks={lookbacks}")

        if section(8):
            # Section 6 left the (20,60,120,250) win looking like a *spike*: shift the
            # fourth horizon to 200 and 3.6 points of CAR vanish, and 300 could not be
            # tested at all because `history_bars=300` silently starves any lookback past
            # 298 - `target_weights` returns "only N bars" and the book sits in cash for
            # the whole sample. So the scan is re-run with the history raised, one horizon
            # at a time, full period only. A single peak surrounded by ordinary neighbours
            # is a fitted parameter; a broad shelf is a real effect.
            print("\n=== 8. fourth-horizon scan with history_bars raised to 400 ===")
            long_p = replace(P, history_bars=400)
            run(prices, long_p, "control: champion horizons, history=400")
            for fourth in [150, 180, 200, 220, 240, 250, 260, 280, 300, 320]:
                run(prices, replace(long_p, mom_lookbacks=(20, 60, 120, fourth)),
                    f"lookbacks=(20,60,120,{fourth})")

        if section(7):
            # 252 sessions = one trading year, not the scan's argmax (250 was, marginally).
            # The shelf in section 8 runs 220-300, so the a-priori choice sits inside it and
            # nothing is being tuned to the last basis point.
            print("\n=== 7. the long-horizon blend against the levers it must survive ===")
            L = (20, 60, 120, 252)
            both(replace(P, mom_lookbacks=L), f"lookbacks={L} (the candidate)")
            both(replace(P, mom_lookbacks=L, mom_score="riskadj", mom_vol_window=20),
                 f"lookbacks={L} + riskadj-20")
            for top_n in [2, 4]:
                both(replace(P, mom_lookbacks=L, top_n=top_n), f"lookbacks={L} top_n={top_n}")
            both(replace(P, mom_lookbacks=L, regime_threshold=99.0),
                 f"lookbacks={L} no crisis-vol filter")

        print("--- benchmarks ---")
        for ticker in ["SPY", "QQQ"]:
            row(f"  {ticker} full 2012-2026", metrics(prices[ticker].loc["2012-01-03":]))

    elif args.mode == "d3":
        # D-3: does deciding membership from trailing dollar volume, on the rebalance date,
        # survive the control that killed S-7's wide sleeve? Three questions, in order:
        #   1. how much does the selected sleeve actually move (if it is static, nothing
        #      has been fixed);
        #   2. what does the *passively held* point-in-time sleeve earn (that is the bar
        #      the signal has to clear, not SPY);
        #   3. does the signal on that sleeve beat the champion out of sample.
        POOL = tuple(sig.RANK_UNIVERSE) + tuple(sig.MEGACAP_SLEEVE)
        pool = [t for t in POOL if t in prices.columns]

        print("=== 1. membership churn, top-N by 60-day median dollar volume ===")
        for size in [10, 20, 30]:
            hist = uni.membership_history(prices, volumes, pool, size, start="2012-01-03")
            ever = int(hist.any().sum())
            prev = hist.shift().astype(object).fillna(hist.iloc[0]).astype(bool)
            changes = int((hist != prev).sum(axis=1).sum() / 2)
            first, last = hist.iloc[0], hist.iloc[-1]
            overlap = int((first & last).sum())
            print(f"  size={size:<3} names ever selected {ever:<3} "
                  f"entries+exits {changes:<5} "
                  f"2012 vs 2026 overlap {overlap}/{size} "
                  f"({overlap / size:.0%} of the sleeve never changed)")
            if size == 20:
                print(f"    2012-01-03: {', '.join(sorted(hist.columns[first]))}")
                print(f"    2026-09-04: {', '.join(sorted(hist.columns[last]))}")

        print("\n=== 2. passive controls, 2012-2026, daily equal weight ===")

        def basket(mask_or_cols, label):
            window = prices.loc["2012-01-03":]
            if isinstance(mask_or_cols, pd.DataFrame):
                mask = mask_or_cols.reindex(window.index).ffill().fillna(False)
                r = window[mask.columns].pct_change().where(mask)
            else:
                r = window[list(mask_or_cols)].pct_change()
            eq = (1 + r.mean(axis=1).fillna(0.0)).cumprod() * 100_000
            m = metrics(eq)
            row(label, m)
            return m

        pit20 = uni.membership_history(prices, volumes, pool, 20, start="2012-01-03")
        pit_bench = basket(pit20, "  EW top-20 point-in-time (D-3)")
        fixed_bench = basket([t for t in sig.MEGACAP_SLEEVE if t in prices.columns],
                             "  EW 50 megacaps, 2026 list (S-7 control)")
        for ticker in ["SPY", "QQQ"]:
            row(f"  {ticker} buy & hold", metrics(prices[ticker].loc["2012-01-03":]))
        print(f"  point-in-time selection costs the passive basket "
              f"{pit_bench['CAR'] - fixed_bench['CAR']:+.1%} CAR - that gap is the part of "
              f"S-7's headline that was hindsight.")

        print("\n=== 3. the signal on a point-in-time sleeve, in and out of sample ===")
        for size, top_n in [(20, 3), (20, 5), (30, 5), (10, 3), (30, 3)]:
            params = replace(P, rank_universe=tuple(pool), universe_size=size, top_n=top_n)
            print(f"\n--- universe_size={size} top_n={top_n} ---")
            run(prices, params, "  IS  2012-2019", start="2012-01-03", end=IS_END,
                volumes=volumes)
            run(prices, params, "  OOS 2020-2026", start=OOS_START, volumes=volumes)
            m = run(prices, params, "  full 2012-2026", volumes=volumes)
            print(f"{'':<40} excess over the EW point-in-time basket: "
                  f"{m['CAR'] - pit_bench['CAR']:+.1%} CAR at "
                  f"{m['Vol'] / pit_bench['Vol']:.2f}x its vol")

        print("\n=== champion (fixed ETF-9 sleeve), same harness ===")
        run(prices, P, "  IS  2012-2019", start="2012-01-03", end=IS_END)
        run(prices, P, "  OOS 2020-2026", start=OOS_START)
        run(prices, P, "  full 2012-2026")

    elif args.mode == "s7bias":
        # How much of the wide-sleeve result is signal and how much is knowing, in 2012,
        # which 50 companies would be megacaps in 2026? An IS/OOS split cannot answer this:
        # the bias is in universe *construction*, so it is spread evenly over both halves.
        # The honest control is the same universe held passively - if momentum's edge over
        # its own basket is small, the headline number is the basket, not the strategy.
        mega = [t for t in sig.MEGACAP_SLEEVE if t in prices.columns]
        window = prices.loc["2012-01-03":]
        rets = window[mega].pct_change()

        def basket(cols, label):
            r = window[cols].pct_change()
            eq = (1 + r.mean(axis=1).fillna(0.0)).cumprod() * 100_000
            row(label, metrics(eq))
            return metrics(eq)

        print("=== passive controls, 2012-2026, daily equal weight ===")
        bench = basket(mega, f"  EW {len(mega)} megacaps (2026 list)")
        listed = [t for t in mega if pd.notna(window[t].iloc[0])]
        basket(listed, f"  EW {len(listed)} of them already listed 2012-01-03")
        late = [t for t in mega if t not in listed]
        if late:
            basket(late, f"  EW {len(late)} that listed later ({', '.join(late)})")
        for ticker in ["SPY", "QQQ"]:
            row(f"  {ticker} buy & hold", metrics(window[ticker]))

        print("\n=== the signal on that same sleeve, vs the sleeve held passively ===")
        for label, universe_ in [("megacap-50 (2026 list)", tuple(mega)),
                                 ("megacap listed-2012 only", tuple(listed))]:
            m = run(prices, replace(P, rank_universe=universe_, top_n=5),
                    f"  momentum top_n=5 on {label}")
            print(f"{'':<40} excess over its own EW basket: "
                  f"{m['CAR'] - bench['CAR']:+.1%} CAR at {m['Vol'] / bench['Vol']:.2f}x its vol")

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
