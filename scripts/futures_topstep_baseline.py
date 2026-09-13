"""End-to-end proof that the Topstep branch is INTEGRATED, not merely built.

Every module in the futures branch has been unit-tested in isolation. That is not the same
claim as "the pipeline runs", and the brief is explicit about not confusing the two. This
script takes the one real futures dataset in the repository - 447,600 one-minute ES bars,
125,156 of them in regular hours across 326 sessions - and pushes it through the whole chain
in one pass:

    real bars -> ONE pre-specified strategy -> real costs (execution_sim)
              -> real intraday paths -> the Topstep twin -> Monte Carlo -> stress

WHAT THIS IS NOT
----------------
It is not an edge claim, and the numbers it prints must not be read as one. The strategy is
deliberately trivial and was fixed before it was run - first-thirty-minute momentum, one
specification, no parameter search - precisely so that whatever comes out is a statement
about the PIPELINE and not about the market. 325 usable sessions is about a sixth of the
~2,000 A-4 measured as necessary to resolve an intraday edge in this repository, so no result
here can be significant, and the script reports the HAC t-statistic and the sample-size gap
rather than letting a number stand on its own.

It ran. The baseline has no edge - HAC t = +0.23 on a mean of $2.39 a session - and the twin
answers accordingly: 2.5% of resampled paths pass the Combine, 0.2% ever reach a payout, and
100% are eventually liquidated. The size sweep is the tell that the objective is degenerate
without an edge: bigger size RAISES the pass rate (2.0% at x1 to 6.0% at x1.5) because with no
drift the only route to a profit target is variance, while liquidation stays at 100% at every
size. A pipeline that said anything more flattering about this strategy would be broken.

WHY IT MATTERS ANYWAY
---------------------
Two things this run supplies that no unit test can. First, REAL intraday paths: every twin
result above this point used `u_shaped_path`, a synthetic shape whose docstring warns it is a
stand-in. Topstep's MLL is tested intraday, so the path is not a detail - it is half the
rule. Here the path comes from the minute bars themselves. Second, it exercises the refusals:
the twin's strict-path guard, the cost model's commission requirement, and the rulebook's
unverified-profit-target refusal all sit on this route.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant_brain.core import stats  # noqa: E402
from quant_brain.markets.futures_cme import execution_sim as ex  # noqa: E402
from quant_brain.markets.futures_cme import instruments as inst  # noqa: E402
from quant_brain.markets.futures_cme import paths as pa  # noqa: E402
from quant_brain.markets.futures_cme import topstep as ts  # noqa: E402
from quant_brain.markets.futures_cme import twin as tw  # noqa: E402

STORE = Path("data/futures/ES.parquet")

# --- the specification, fixed before the run -------------------------------------------
# Written down here so it is visibly pre-registered rather than chosen after seeing results.
OPEN_ET = "09:30"
SIGNAL_ET = "10:00"      # measure the first 30 minutes
EXIT_ET = "15:45"        # flat before the close, comfortably inside Topstep's requirement
SYMBOL = "MES"           # the micro: an ES point is $50, which a $2,000 MLL cannot carry


def load(store: Path = STORE) -> pd.DataFrame:
    df = pd.read_parquet(store)
    df["t"] = pd.to_datetime(df["t"], utc=True)
    df = df.sort_values("t").reset_index(drop=True)
    et = df["t"].dt.tz_convert("America/New_York")
    df["et"] = et
    df["day"] = et.dt.date
    df["hm"] = et.dt.strftime("%H:%M")
    # Regular trading hours only. The overnight session has its own microstructure and a
    # strategy that straddles both is two strategies wearing one name.
    return df[(df["hm"] >= OPEN_ET) & (df["hm"] <= "16:00")].copy()


def sessions(df: pd.DataFrame, contracts: int = 1) -> list[tw.TwinDay]:
    """One TwinDay per session, with the REAL intraday equity path in dollars.

    P&L is marked minute by minute from the entry price, so `path` is the account's actual
    within-session excursion rather than a synthetic shape. That is what Topstep's MLL is
    tested against, so it is the input that decides whether the twin's answer means anything.
    """
    spec = inst.get(SYMBOL).spec
    sim = ex.ExecutionSimulator(cost=ex.CostModel.for_contract(SYMBOL), symbol=SYMBOL)
    # Entering and exiting `contracts` micros, charged once per session.
    cost = sim.round_turn_cost(contracts)

    out: list[tw.TwinDay] = []
    for day, g in df.groupby("day", sort=True):
        g = g.sort_values("t")
        if g["contract"].nunique() > 1:
            continue                      # a roll day: two instruments, not one session
        opens = g[g["hm"] == OPEN_ET]
        sig = g[g["hm"] == SIGNAL_ET]
        held = g[(g["hm"] >= SIGNAL_ET) & (g["hm"] <= EXIT_ET)]
        if opens.empty or sig.empty or len(held) < 30:
            continue                      # a short or broken session; skipped, not patched

        first = float(opens["o"].iloc[0])
        entry = float(sig["c"].iloc[0])
        direction = 1 if entry > first else -1        # the whole strategy, in one line

        marks = held["c"].to_numpy(dtype=float)
        pnl_path = direction * (marks - entry) * spec.multiplier * contracts - cost
        out.append(tw.TwinDay(day=day, pnl=float(pnl_path[-1]),
                              path=tuple(float(x) for x in pnl_path)))
    return out


def report(days: list[tw.TwinDay], *, target: float, fee: float | None,
           reps: int, block: int) -> dict:
    pnl = np.array([d.pnl for d in days])
    out: dict = {
        "sessions": len(days),
        "mean_per_session": float(pnl.mean()),
        "total": float(pnl.sum()),
        "win_rate": float((pnl > 0).mean()),
        "worst_session": float(pnl.min()),
        "best_session": float(pnl.max()),
        "worst_intraday": float(min(min(d.path) for d in days)),
    }
    t = stats.tstat_hac(pnl, horizon=1)
    out["t_hac"] = t.t
    out["t_threshold_1_trial"] = stats.bonferroni_threshold(1)

    twin = tw.TopstepTwin(50_000, profit_target=target, combine_fee=fee,
                          payout_policy=tw.PayoutPolicy(fraction=0.5))
    ev = tw.evaluate_twin(twin, pa.moving_block(days, block=block, reps=reps))
    out["twin"] = {
        "p_pass_combine": ev.p_pass_combine,
        "p_first_payout": ev.p_first_payout,
        "p_liquidated": ev.p_liquidated,
        "mean_gross": ev.mean_gross,
        "mean_net": ev.mean_net,
        "median_days_to_pass": ev.median_days_to_pass,
        "p05_min_buffer_funded": ev.p05_min_buffer_funded,
    }
    out["stress"] = pa.stress(twin, days, reps=max(100, reps // 2), block=block).scenarios
    out["size_sweep"] = pa.size_sweep(twin, days, reps=max(100, reps // 2), block=block)
    out["clustering"] = pa.clustering_premium(twin, days, block=block,
                                              reps=max(100, reps // 2))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--contracts", type=int, default=1, help="MES contracts per session")
    ap.add_argument("--reps", type=int, default=400)
    ap.add_argument("--block", type=int, default=10)
    ap.add_argument("--profit-target", type=float, default=None,
                    help="Combine profit target. Omit to use the SEARCH-tier figure, which "
                         "the rulebook refuses by default and this script accepts explicitly.")
    ap.add_argument("--fee", type=float, default=None,
                    help="Combine cost. Omitted by default because Topstep's pricing was not "
                         "on any page fetched; without it no net figure is reported.")
    ap.add_argument("--out", type=Path, default=Path("research/futures_topstep_baseline.json"))
    args = ap.parse_args()

    if not STORE.exists():
        print(f"no futures store at {STORE}")
        return 1

    target = args.profit_target
    if target is None:
        rule = ts.COMBINE_PROFIT_TARGET[50_000]
        target = rule.require(ts.Confidence.SEARCH, what="Combine profit target")
        print(f"profit target ${target:,.0f} accepted at {rule.confidence.name} confidence")
        print(f"  {rule.cite()}")
        print(f"  {rule.note}\n")

    df = load()
    days = sessions(df, contracts=args.contracts)
    print(f"{len(df):,} RTH bars -> {len(days)} usable sessions "
          f"({SYMBOL} x{args.contracts})\n")

    r = report(days, target=target, fee=args.fee, reps=args.reps, block=args.block)

    print("STRATEGY (pre-specified, not searched)")
    print(f"  mean ${r['mean_per_session']:+,.2f}/session   total ${r['total']:+,.0f}   "
          f"win {r['win_rate']:.1%}")
    print(f"  worst close ${r['worst_session']:,.0f}   "
          f"worst intraday ${r['worst_intraday']:,.0f}")
    print(f"  HAC t = {r['t_hac']:+.2f} against a |t| > {r['t_threshold_1_trial']:.2f} "
          f"threshold at one trial")
    print(f"  {r['sessions']} sessions against the ~2,000 A-4 measured as necessary "
          f"({r['sessions'] / 2000:.0%})\n")

    tv = r["twin"]
    money = (f"E[net] ${tv['mean_net']:,.0f}" if tv["mean_net"] is not None
             else f"E[gross] ${tv['mean_gross']:,.0f} (FEE UNKNOWN - not a profit figure)")
    print("TOPSTEP TWIN")
    print(f"  pass {tv['p_pass_combine']:.1%} -> paid {tv['p_first_payout']:.1%}   "
          f"liquidated {tv['p_liquidated']:.1%}   {money}")
    print(f"  5th-pct funded buffer ${tv['p05_min_buffer_funded']:,.0f}\n")

    print("STRESS")
    for name, row in r["stress"].items():
        print(f"  {name:<28} pass {row['p_pass_combine']:6.1%}  "
              f"paid {row['p_first_payout']:6.1%}  liq {row['p_liquidated']:6.1%}")

    print("\nSIZE")
    for f, row in r["size_sweep"].items():
        print(f"  x{f:<5} pass {row['p_pass_combine']:6.1%}  "
              f"paid {row['p_first_payout']:6.1%}  liq {row['p_liquidated']:6.1%}  "
              f"E[gross] {row['mean_gross']:9,.0f}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(r, indent=2, default=float), encoding="utf-8")
    print(f"\nwritten to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
