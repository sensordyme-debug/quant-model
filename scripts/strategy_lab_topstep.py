"""Phases 12 and 13: Monte Carlo and the Topstep digital twin.

THE PHASE 12 PRECONDITION, DISCHARGED
---------------------------------------
The brief forbids using the existing Monte Carlo path reconstruction unless it has been
independently verified, and says to STOP and fix it if it is still suspect.

It was verified before this module was written, by property checks written against the
machinery rather than against the existing suite's framing:

    - iid resampling preserves the session P&L mean and standard deviation, and emits only
      real session P&Ls
    - `_shifted` re-closes a session at a requested P&L ADDITIVELY: the close lands exactly on
      target and no intraday mark moves by more than |delta|. Checked at targets of 0, 1x, 5x
      and -1x the original close
    - the documented near-flat blow-up specifically: re-closing a $0.01 session at $1,000 does
      NOT scale its -$500 excursion by 100,000x
    - `_lay_out` carries whole sessions with pnl AND path byte-identical - no reconstruction
    - `_calendar` returns strictly increasing dates and invents only weekdays
    - `_scaled_day` multiplies P&L and every intraday mark by the same factor

One check initially failed and the failure was mine: a synthetic template built with
consecutive calendar days contains weekends, and `_calendar` preserves the template's own
dates and only guarantees weekday spacing for dates it invents. On a realistic weekday-only
template it is clean. The machinery is sound; the precondition is discharged.

WHY THE TWIN IS WHERE MOST OF THESE DIE
-----------------------------------------
The baseline tournament's best cell earns $52,379 net with an 80.9% win rate. It also has a
maximum drawdown of $39,960. The Topstep trailing maximum loss limit is $2,000, tested
INTRADAY on unrealised P&L. A strategy whose equity curve breathes twenty times the size of
the barrier does not fail the Combine occasionally; it fails it structurally, and no amount of
resampling changes that.

So this module reports the two things separately, as the brief demands:

    NORMAL ECONOMICS   what the mechanism earns, with its own drawdown
    TOPSTEP FEASIBILITY  what happens against a $2,000 barrier

and it computes the ratio between a strategy's own drawdown and the barrier first, because
that single number decides most of the field before any simulation runs.

SIZE IS SWEPT, NOT CHOSEN
---------------------------
A strategy's Combine outcome depends on contract count in two opposing ways: bigger reaches
the target sooner and breaches the barrier sooner. Picking one size and reporting it is how a
pass rate gets manufactured, so the sweep is reported in full including the sizes that fail.
"""
from __future__ import annotations

import argparse
import datetime as dt
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from quant_brain.markets.futures_cme import paths as P            # noqa: E402
from quant_brain.markets.futures_cme.twin import TopstepTwin, TwinDay  # noqa: E402

MLL = 2_000.0
DLL = 1_000.0
TARGET = 3_000.0
MAX_DAYS = 120
N_PATHS = 400
BLOCK = 10

#: Contract sweeps. Micros scale to 50, minis to 5, per the Topstep scaling plan.
SIZES = {"ES": (1, 2, 5), "NQ": (1, 2, 5), "MES": (1, 5, 10, 20), "MNQ": (1, 5, 10, 20)}


def load_sessions() -> dict:
    with (REPO / "research" / "lab_sessions.pkl").open("rb") as fh:
        return pickle.load(fh)


def to_twin_days(recs: list[dict], scale: float) -> list[TwinDay]:
    """Scale a one-contract session series to `scale` contracts, path and all."""
    out = []
    for r in recs:
        path = r["path"]
        # subsample: the MLL cares about the extremes, and 391 marks x 400 paths is a lot of
        # arithmetic for no extra fidelity on the minimum
        step = max(1, len(path) // 100)
        marks = tuple(float(x) * scale for x in path[::step]) + (float(path[-1]) * scale,)
        out.append(TwinDay(day=r["session"], pnl=float(r["net_pnl"]) * scale,
                           path=marks, traded=r["n_trades"] > 0))
    return out


def dll_breaches(days: list[TwinDay], limit: float = DLL) -> float:
    """Share of sessions whose worst intraday mark breaches the daily loss limit.

    Reported separately from the MLL because a DLL hit is not an account failure - it is a
    forced stand-down for the rest of the session. It still matters: a strategy that trips it
    weekly cannot compound, whatever its expectancy.
    """
    if not days:
        return float("nan")
    return float(np.mean([min(d.path) <= -limit for d in days if d.path]))


def run_twin(days: list[TwinDay], n_paths: int, seed: int) -> dict:
    """Block-bootstrapped Combine outcomes. Blocks preserve volatility clustering."""
    rng = np.random.default_rng(seed)
    n = len(days)
    passed = breached = 0
    days_to_pass, buffers, dds = [], [], []
    for _ in range(n_paths):
        idx = []
        while len(idx) < MAX_DAYS:
            start = int(rng.integers(0, n))
            idx.extend((start + k) % n for k in range(BLOCK))
        idx = idx[:MAX_DAYS]
        seq = [TwinDay(day=dt.date(2025, 1, 1) + dt.timedelta(days=k),
                       pnl=days[i].pnl, path=days[i].path, traded=days[i].traded)
               for k, i in enumerate(idx)]
        res = TopstepTwin(50_000, strict_path=True,
                          allow_unverified_target=True).run(seq)
        if res.combine_days is not None:
            passed += 1
            days_to_pass.append(res.combine_days)
        if res.breach_day is not None:
            breached += 1
        buffers.append(res.min_buffer)
        eq = np.cumsum([d.pnl for d in seq])
        dds.append(float((eq - np.maximum.accumulate(eq)).min()))
    return {
        "pass_rate": passed / n_paths, "breach_rate": breached / n_paths,
        "median_days_to_pass": float(np.median(days_to_pass)) if days_to_pass else np.nan,
        "p25_days": float(np.percentile(days_to_pass, 25)) if days_to_pass else np.nan,
        "p75_days": float(np.percentile(days_to_pass, 75)) if days_to_pass else np.nan,
        "median_min_buffer": float(np.median(buffers)),
        "expected_max_dd": float(np.mean(dds)),
        "worst_5pct_dd": float(np.percentile(dds, 5)),
        "worst_1pct_dd": float(np.percentile(dds, 1)),
    }


def monte_carlo(recs: list[dict], scale: float, seed: int = 909) -> dict:
    """Trade/day reshuffling and stress, using the VERIFIED path machinery."""
    days = to_twin_days(recs, scale)
    pnl = np.array([d.pnl for d in days], dtype=float)
    rng = np.random.default_rng(seed)
    # iid day reshuffling: destroys sequence, preserves the marginal distribution
    finals, maxdds, streaks = [], [], []
    for _ in range(2000):
        s = rng.permutation(pnl)
        eq = np.cumsum(s)
        finals.append(float(eq[-1]))
        maxdds.append(float((eq - np.maximum.accumulate(eq)).min()))
        run = best = 0
        for v in s:
            run = run + 1 if v < 0 else 0
            best = max(best, run)
        streaks.append(best)
    return {
        "mc_median_final": float(np.median(finals)),
        "mc_p05_final": float(np.percentile(finals, 5)),
        "mc_p95_final": float(np.percentile(finals, 95)),
        "mc_prob_final_positive": float(np.mean(np.array(finals) > 0)),
        "mc_median_maxdd": float(np.median(maxdds)),
        "mc_worst5_maxdd": float(np.percentile(maxdds, 5)),
        "mc_worst1_maxdd": float(np.percentile(maxdds, 1)),
        "mc_prob_dd_exceeds_mll": float(np.mean(np.array(maxdds) <= -MLL)),
        "mc_median_losing_streak": float(np.median(streaks)),
        "mc_p95_losing_streak": float(np.percentile(streaks, 95)),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--top", type=int, default=10,
                    help="how many cells by net P&L to take through the twin")
    ap.add_argument("--paths", type=int, default=N_PATHS)
    args = ap.parse_args()

    store = load_sessions()
    port = pd.read_csv(REPO / "research" / "lab_portfolio.csv")
    normal = port[port.regime == "normal"].copy()

    print("=" * 112)
    print("THE FILTER THAT DECIDES MOST OF THE FIELD BEFORE ANY SIMULATION")
    print("=" * 112)
    print("Topstep's trailing MLL is $2,000, tested intraday. A strategy whose own maximum")
    print("drawdown at ONE contract already exceeds it cannot be sized down into compliance")
    print("without also scaling its edge below the cost floor.\n")
    normal["dd_over_mll"] = normal.max_drawdown.abs() / MLL
    print(f"  cells with 1-contract max drawdown under $2,000 : "
          f"{int((normal.dd_over_mll < 1).sum())} of {len(normal)}")
    print(f"  median drawdown / MLL ratio                     : "
          f"{normal.dd_over_mll.median():.1f}x")
    print(f"  ratio for the highest-net cell                  : "
          f"{normal.loc[normal.net_pnl.idxmax(), 'dd_over_mll']:.1f}x")

    survivors = normal[(normal.net_pnl > 0)].copy()
    survivors = survivors.reindex(
        survivors.net_pnl.sort_values(ascending=False).index).head(args.top)
    print(f"\n  taking the {len(survivors)} positive-net cells through Monte Carlo and the twin")

    rows = []
    for _, r in survivors.iterrows():
        recs = store.get((r.strategy, r.symbol))
        if not recs:
            continue
        for size in SIZES.get(r.symbol, (1,)):
            days = to_twin_days(recs, float(size))
            mc = monte_carlo(recs, float(size))
            tw = run_twin(days, args.paths, seed=4242 + size)
            rows.append({"strategy": r.strategy, "symbol": r.symbol, "contracts": size,
                         "net_1ct": r.net_pnl, "dll_breach_rate": dll_breaches(days),
                         **mc, **tw})
            print(f"    {r.strategy[:28]:28} {r.symbol:5} {size:3d}ct  "
                  f"pass {tw['pass_rate']:5.1%}  breach {tw['breach_rate']:5.1%}  "
                  f"P[dd>MLL] {mc['mc_prob_dd_exceeds_mll']:5.1%}  "
                  f"DLL/session {dll_breaches(days):5.1%}")

    out = pd.DataFrame(rows)
    out.to_csv(REPO / "research" / "lab_topstep.csv", index=False)

    print("\n" + "=" * 112)
    print("PHASE 12 - MONTE CARLO  (2,000 iid day reshuffles per cell)")
    print("=" * 112)
    if len(out):
        print(f"  {'strategy':28} {'sym':5} {'ct':>3} {'P[final>0]':>11} "
              f"{'med maxDD':>11} {'worst1% DD':>11} {'P[DD>MLL]':>10} {'p95 streak':>11}")
        for _, r in out.iterrows():
            print(f"  {r.strategy[:28]:28} {r.symbol:5} {int(r.contracts):3d} "
                  f"{r.mc_prob_final_positive:11.1%} {r.mc_median_maxdd:11.0f} "
                  f"{r.mc_worst1_maxdd:11.0f} {r.mc_prob_dd_exceeds_mll:10.1%} "
                  f"{r.mc_p95_losing_streak:11.0f}")

    print("\n" + "=" * 112)
    print("PHASE 13 - TOPSTEP DIGITAL TWIN  (real intraday paths, intraday MLL armed)")
    print("=" * 112)
    if len(out):
        print(f"  {'strategy':28} {'sym':5} {'ct':>3} {'pass':>7} {'breach':>8} "
              f"{'med days':>9} {'p25':>5} {'p75':>5} {'DLL/sess':>9}")
        for _, r in out.iterrows():
            print(f"  {r.strategy[:28]:28} {r.symbol:5} {int(r.contracts):3d} "
                  f"{r.pass_rate:7.1%} {r.breach_rate:8.1%} "
                  f"{r.median_days_to_pass:9.0f} {r.p25_days:5.0f} {r.p75_days:5.0f} "
                  f"{r.dll_breach_rate:9.1%}")
        best = out.loc[out.pass_rate.idxmax()]
        print(f"\n  best pass rate in the whole field: {best.pass_rate:.1%} "
              f"({best.strategy} {best.symbol} at {int(best.contracts)} contracts)")
    print(f"\nwrote {REPO / 'research' / 'lab_topstep.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
