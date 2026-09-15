"""What strategy quality is actually required to make the Topstep funnel pay?

WHY THIS IS THE RIGHT QUESTION TO ASK NOW
-------------------------------------------
Five research phases have rejected every mechanism in the library. The reflex is to keep
searching, but before spending another phase it is worth knowing precisely what the search is
for. "Find an edge" is not a specification. "Find an annualised Sharpe of 1.4 with per-session
volatility near $250" is.

That number is computable from the published rules, and nobody has computed it. This module
does, using the repository's own verified Topstep lifecycle model rather than a hand-rolled
barrier approximation.

THE FUNNEL, AS THE RULES ACTUALLY DEFINE IT
---------------------------------------------
    Combine        $50,000 notional, +$3,000 target, $2,000 trailing MLL tested intraday.
                   Costs $49/month (Standard, $50K).
    The lock       The MLL trails the high-water mark until equity reaches +$2,000, then
                   LOCKS at the starting balance permanently. This matters enormously and is
                   why the barrier is more survivable than a naive reading suggests.
    Express Funded The account that follows a pass. Starts at $0 with the same $2,000 MLL,
                   which is why a Combine pass is not a payout - the previous lab phase found
                   many paths passing the Combine and then dying in the XFA.
    Payout         Up to 50% of balance, capped at $2,000 for a $50K account ($3,000 on the
                   consistency route). 90% profit split.
    After a payout The MLL resets to $0 permanently and the day count restarts.

WHAT IS BEING MEASURED
------------------------
For a strategy characterised only by its per-session mean and standard deviation, the full
lifecycle is simulated and the answer is expressed in the units that matter to somebody paying
the monthly fee: expected cash, months to first payout, and the probability of never getting
one.

No strategy is being proposed here. This is the specification the next search has to hit, and
the honest statement of what happens if it is missed.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from quant_brain.markets.futures_cme.twin import PayoutPolicy, TopstepTwin, TwinDay  # noqa: E402

MONTHLY_FEE = 49.0
N_PATHS = 600
MAX_SESSIONS = 250
SESSIONS_PER_MONTH = 21


def synth_days(mean: float, sd: float, n: int, rng: np.random.Generator) -> list[TwinDay]:
    """Sessions with a plausible intraday path, so the intraday MLL test is real.

    The path is a Brownian bridge from 0 to the session's close, scaled so its excursion is
    proportional to the session's own volatility. Without a path the twin cannot test the
    intraday breach and every survival number would be optimistic.
    """
    out = []
    for i in range(n):
        close = float(rng.normal(mean, sd))
        k = 40
        steps = rng.normal(0.0, sd / np.sqrt(k), k)
        walk = np.cumsum(steps)
        bridge = walk - np.linspace(0, 1, k) * (walk[-1] - close)
        out.append(TwinDay(day=dt.date(2025, 1, 1) + dt.timedelta(days=i),
                           pnl=close, path=tuple(float(x) for x in bridge), traded=True))
    return out


def run(sharpe: float, sd: float, rng: np.random.Generator) -> dict:
    mean = sharpe / np.sqrt(252) * sd
    passed = payouts = breached = 0
    cash, months, first_payout_month = [], [], []
    for _ in range(N_PATHS):
        days = synth_days(mean, sd, MAX_SESSIONS, rng)
        twin = TopstepTwin(50_000, strict_path=True, allow_unverified_target=True,
                           payout_policy=PayoutPolicy(min_buffer_after=500.0))
        res = twin.run(days)
        n_months = max(1.0, res.days / SESSIONS_PER_MONTH)
        fee = MONTHLY_FEE * n_months
        gross = res.total_paid
        cash.append(gross - fee)
        months.append(n_months)
        passed += res.combine_days is not None
        payouts += len(res.payouts) > 0
        breached += res.breach_day is not None
        if res.payouts:
            first_payout_month.append(
                (res.payouts[0][0] - days[0].day).days / 30.4)
    return {
        "sharpe": sharpe, "sd": sd, "mean_per_session": mean,
        "pass_rate": passed / N_PATHS, "payout_rate": payouts / N_PATHS,
        "breach_rate": breached / N_PATHS,
        "mean_net_cash": float(np.mean(cash)),
        "median_net_cash": float(np.median(cash)),
        "p_lose_money": float(np.mean(np.array(cash) < 0)),
        "median_months": float(np.median(months)),
        "median_months_to_payout": (float(np.median(first_payout_month))
                                    if first_payout_month else np.nan),
    }


def main() -> int:
    rng = np.random.default_rng(9090)
    print("=" * 104)
    print("WHAT STRATEGY QUALITY MAKES THE TOPSTEP FUNNEL PAY?")
    print(f"$50K Combine, ${MONTHLY_FEE:.0f}/month, MLL locks at +$2,000, "
          f"XFA payout cap $2,000, 90% split")
    print(f"{N_PATHS} full-lifecycle paths per cell, real intraday paths, "
          f"intraday MLL armed")
    print("=" * 104)

    rows = []
    print(f"\n{'Sharpe':>7} {'sd/sess':>8} {'$/sess':>8} {'pass':>7} {'payout':>7} "
          f"{'breach':>7} {'mean net $':>11} {'median $':>9} {'P(lose)':>8} {'months':>7}")
    for sharpe in (0.0, 0.5, 1.0, 1.5, 2.0, 3.0):
        for sd in (250.0,):
            r = run(sharpe, sd, rng)
            rows.append(r)
            print(f"{r['sharpe']:7.1f} {r['sd']:8.0f} {r['mean_per_session']:8.1f} "
                  f"{r['pass_rate']:7.1%} {r['payout_rate']:7.1%} {r['breach_rate']:7.1%} "
                  f"{r['mean_net_cash']:11.0f} {r['median_net_cash']:9.0f} "
                  f"{r['p_lose_money']:8.1%} {r['median_months']:7.1f}")

    print(f"\n  the per-session volatility knob, at Sharpe 1.0:")
    print(f"  {'sd/sess':>8} {'$/sess':>8} {'pass':>7} {'payout':>7} {'mean net $':>11} "
          f"{'P(lose)':>8}")
    for sd in (100.0, 250.0, 500.0, 800.0):
        r = run(1.0, sd, rng)
        rows.append(r)
        print(f"  {r['sd']:8.0f} {r['mean_per_session']:8.1f} {r['pass_rate']:7.1%} "
              f"{r['payout_rate']:7.1%} {r['mean_net_cash']:11.0f} {r['p_lose_money']:8.1%}")

    df = pd.DataFrame(rows)
    df.to_csv(REPO / "research" / "combine_funnel_ev.csv", index=False)

    print("\n" + "=" * 104)
    print("THE SPECIFICATION THE NEXT SEARCH HAS TO HIT")
    print("=" * 104)
    main_rows = df[df.sd == 250.0].sort_values("sharpe")
    be = main_rows[main_rows.mean_net_cash > 0]
    if len(be):
        first = be.iloc[0]
        print(f"  break-even Sharpe (mean net cash > 0): approximately "
              f"{first.sharpe:.1f}")
    else:
        print("  no tested Sharpe produces positive mean net cash")
    print(f"\n  A Sharpe-0 strategy - random entries, correct sizing - loses "
          f"${abs(df[(df.sharpe == 0) & (df.sd == 250)].mean_net_cash.iloc[0]):.0f} "
          f"on average.")
    print("  That is the cost of the fee, and it is the number any real edge has to clear")
    print("  before it earns anything at all.")
    print(f"\nwrote {REPO / 'research' / 'combine_funnel_ev.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
