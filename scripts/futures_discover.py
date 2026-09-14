"""Run the bounded discovery loop on real ES data, and report where every hypothesis died.

Part 8/9/29. This is the funnel end to end: a grid of deliberately simple hypotheses built
from the futures feature library, each one backtested on real minute bars with real costs,
then put through four gates in increasing order of expense - statistics, cost, Topstep
survival, walk-forward.

READ THE ATTRITION, NOT THE SURVIVORS
---------------------------------------
The output that matters is the funnel table. A run that promotes something is not better than
a run that promotes nothing; a run where the gates do not discriminate is the only bad
outcome, because that means the gates are decoration.

Every hypothesis is written to the ledger whether it survives or not, which is what makes the
multiplicity correction real: the hundredth candidate in a family faces a threshold sized by
the ninety-nine before it, and there is no argument available to the caller about that.

WHAT THIS IS NOT
----------------
Not a claim that a threshold rule on a single feature is a sensible strategy. It is not. The
grid exists to exercise and measure the funnel on real data; the model progression Part 9
asks for starts after the funnel is trusted, not before.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant_brain.markets.futures_cme import dataquality as fdq  # noqa: E402
from quant_brain.markets.futures_cme import execution_sim as ex  # noqa: E402
from quant_brain.markets.futures_cme import features as fe  # noqa: E402
from quant_brain.markets.futures_cme import instruments as inst  # noqa: E402
from quant_brain.markets.futures_cme import paths as pa  # noqa: E402
from quant_brain.markets.futures_cme import twin as tw  # noqa: E402
from quant_brain.research import Ledger  # noqa: E402
from quant_brain.research.search import Limits, search, threshold_hypotheses  # noqa: E402

LEDGER = Path("research/experiments_futures.jsonl")

#: Price source -> the instrument actually traded. A $50K account with a $2,000 limit cannot
#: carry an ES point ($50) or an NQ point ($20), so the grid is priced on the parent series
#: and sized in the micro. The micro is also what the account is permitted at entry.
TRADED = {"ES": "MES", "NQ": "MNQ", "MES": "MES", "MNQ": "MNQ"}
OPEN_ET, CLOSE_ET = "09:30", "15:45"

#: Gate thresholds. Named and documented rather than tuned: a gate whose level was chosen
#: after seeing the results is not a gate.
MIN_TRADES = 40          # below this a per-session series is not a strategy, it is a few days
MAX_COST_SHARE = 0.60    # costs above 60% of gross edge: execution eats the result
MIN_PASS_RATE = 0.10     # Topstep survival floor
MIN_WF_FOLDS = 3         # walk-forward folds that must be positive out of 5


def load(store: Path, symbol: str) -> pd.DataFrame:
    df = pd.read_parquet(store)
    fdq.require_usable(symbol, df, time_col="t")
    df["t"] = pd.to_datetime(df["t"], utc=True)
    et = df["t"].dt.tz_convert("America/New_York")
    df["day"] = et.dt.date
    df["hm"] = et.dt.strftime("%H:%M")
    rth = df[(df["hm"] >= OPEN_ET) & (df["hm"] <= CLOSE_ET)].copy()
    # One contract per session: a session built from two instruments is not one session.
    good = rth.groupby("day")["contract"].nunique()
    return rth[rth["day"].isin(good[good == 1].index)].reset_index(drop=True)


def session_frames(df: pd.DataFrame) -> list[pd.DataFrame]:
    return [g.reset_index(drop=True) for _, g in df.groupby("day", sort=True)
            if len(g) > 200]


def build_features(sessions: list[pd.DataFrame], lib: fe.FeatureSet):
    """Features per session, so no window ever reaches across a session boundary."""
    out = []
    for g in sessions:
        X, _ = lib.build(g, strict=False)
        out.append(X)
    return out


def session_accounting(pos, close, *, multiplier: float, contracts: int,
                       round_turn_cost: float):
    """One session's net equity path, its round-turn count and its gross P&L.

    COUNTING THE LEGS
    -----------------
    A session starts flat and must end flat: the funnel trades a 09:30-15:45 ET window and
    Topstep requires a flat book at 3:10 PM CT. So the exit is always traded. The previous
    count was `int(abs(diff(pos, prepend=0)).sum() / 2)`, which supplies the opening leg and
    never the closing one, then truncates the odd total downwards. A rule that is simply long
    all session therefore reported ZERO round turns and was charged ZERO cost. Measured on
    the funnel's own ledger, 624 of the 816 scored hypotheses (76%) recorded `trades: 0` and
    `costs: 0.0`, and were then discarded by the 40-trade floor as "not a strategy" before the
    Topstep and walk-forward gates ever ran. `append=0.0` closes the book.

    WHEN THE COST LANDS
    -------------------
    Cost used to be spread across the session with `linspace(0, cost, n)`. The terminal P&L
    is identical either way, but this path is what `TwinDay(path=...)` hands to the Topstep
    twin, and the trailing maximum loss limit tracks peak equity intraday. Cost not yet
    charged is equity the twin believes the account has. Each leg is now paid at the bar it
    trades: half a round turn on the way in, half on the way out.

    THE ONE-BAR LAG
    ---------------
    Position decided on bar i earns bar i+1's move. That is what separates a backtest from a
    look-ahead and it is unchanged here.
    """
    pos = np.nan_to_num(np.asarray(pos, dtype=float), nan=0.0)
    close = np.asarray(close, dtype=float)
    n = len(pos)
    if n < 2:
        return np.zeros(1), 0.0, 0.0

    step = np.diff(close, prepend=close[0]) * multiplier * contracts
    gross_path = np.cumsum(pos[:-1] * step[1:])

    #: Contracts traded at each boundary, including the entry (prepend) and the flatten at
    #: the bell (append). Length n+1; index k is the trade that happens at bar k.
    legs = np.abs(np.diff(pos, prepend=0.0, append=0.0))
    turns = float(legs.sum()) / 2.0

    #: Cumulative cost through bar k, at half a round turn per leg.
    paid = np.cumsum(legs) * (round_turn_cost / 2.0)
    #: gross_path[j] is the P&L after bar j+1's move, so it carries the cost through bar j+1.
    incurred = paid[1:n].copy()
    incurred[-1] = paid[-1]          # the closing flatten settles on the last point
    return gross_path - incurred, turns, float(gross_path[-1])


def evaluator(sessions, feats, *, contracts: int, twin_obj, symbol: str):
    """Backtest one hypothesis and run every gate that does not need the survivors."""
    spec = inst.get(symbol).spec
    sim = ex.ExecutionSimulator(cost=ex.CostModel.for_contract(symbol), symbol=symbol)
    tick_cost = sim.round_turn_cost(contracts)

    def run(h):
        pnls, paths, trades, gross, costs = [], [], 0.0, 0.0, 0.0
        for g, X in zip(sessions, feats, strict=True):
            net_path, turns, session_gross = session_accounting(
                h.signal(X), g["c"].to_numpy(dtype=float),
                multiplier=spec.multiplier, contracts=contracts, round_turn_cost=tick_cost)
            trades += turns
            gross += session_gross
            costs += turns * tick_cost
            pnls.append(float(net_path[-1]) if len(net_path) else 0.0)
            paths.append(tuple(float(x) for x in net_path))

        out: dict = {"pnl": pnls, "sessions": len(pnls), "trades": int(round(trades)),
                     "gross": gross, "costs": costs,
                     "mean_per_session": float(np.mean(pnls)) if pnls else 0.0}

        if trades < MIN_TRADES:
            out["cost_ok"] = False
            out["cost_reason"] = f"only {trades} round turns; not a strategy"
            return out
        share = costs / abs(gross) if gross else float("inf")
        out["cost_share"] = share
        if share > MAX_COST_SHARE:
            out["cost_ok"] = False
            out["cost_reason"] = (f"costs are {share:.0%} of gross edge, above "
                                  f"{MAX_COST_SHARE:.0%}")
            return out

        days = [tw.TwinDay(day=g["day"].iloc[0], pnl=p, path=path or (p,))
                for g, p, path in zip(sessions, pnls, paths, strict=True)]
        ev = tw.evaluate_twin(twin_obj, pa.moving_block(days, block=10, reps=150, seed=0))
        out["p_pass_combine"] = ev.p_pass_combine
        out["p_first_payout"] = ev.p_first_payout
        if ev.p_pass_combine < MIN_PASS_RATE:
            out["topstep_ok"] = False
            out["topstep_reason"] = (f"passes {ev.p_pass_combine:.1%} of resampled paths, "
                                     f"below {MIN_PASS_RATE:.0%}")
            return out

        arr = np.array(pnls)
        folds = np.array_split(arr, 5)
        positive = sum(1 for f in folds if f.mean() > 0)
        out["wf_positive_folds"] = positive
        if positive < MIN_WF_FOLDS:
            out["walkforward_ok"] = False
            out["walkforward_reason"] = f"only {positive}/5 walk-forward folds positive"
        return out

    return run


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--price-source", default="ES", choices=sorted(TRADED),
                    help="which stored contract's bars to build the grid on")
    ap.add_argument("--contracts", type=int, default=1)
    ap.add_argument("--max-experiments", type=int, default=200)
    ap.add_argument("--max-seconds", type=float, default=900.0)
    ap.add_argument("--profit-target", type=float, default=3_000.0)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    source = args.price_source
    symbol = TRADED[source]
    store = Path(f"data/futures/{source}.parquet")
    family = f"futures.{source.lower()}.threshold_grid.v2"
    if not store.exists():
        print(f"no futures store at {store}")
        return 1

    df = load(store, source)
    sessions = session_frames(df)
    lib = fe.library()
    feats = build_features(sessions, lib)
    supported = [c for c in feats[0].columns]
    refused = lib.missing(set(df.columns))

    print(f"{source} store: {len(df):,} RTH bars -> {len(sessions)} sessions, sized in {symbol}")
    print(f"features: {len(supported)} built, {len(refused)} REFUSED "
          f"({', '.join(refused) or 'none'})")
    print(f"  families: {ties(lib.families())}\n")

    hyps = threshold_hypotheses(supported, family=family)
    twin_obj = tw.TopstepTwin(50_000, profit_target=args.profit_target,
                              payout_policy=tw.PayoutPolicy(fraction=0.5))
    ledger = Ledger(LEDGER)
    before = ledger.trials(family)

    fun = search(hyps, ledger=ledger,
                 evaluate=evaluator(sessions, feats, contracts=args.contracts,
                                    twin_obj=twin_obj, symbol=symbol),
                 limits=Limits(max_experiments=args.max_experiments,
                               max_seconds=args.max_seconds, min_sessions=100))

    print(f"FUNNEL  ({len(hyps)} hypotheses in the grid)")
    print(fun.table())
    print(f"\n  ledger: {ledger.summary(family)}")
    print(f"  trials in {family}: {before} -> {ledger.trials(family)}")
    if fun.survived:
        print("\n  SURVIVED to the holdout:")
        for name in fun.survived:
            print(f"    {name}")
    else:
        print("\n  Nothing survived. That is a result, not a failure of the loop.")

    args.out = args.out or Path(f"research/futures_discovery_{source.lower()}.json")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({
        "grid": len(hyps), "funnel": fun.__dict__, "family": family,
        "price_source": source, "traded": symbol,
        "features_built": supported, "features_refused": {k: list(v) for k, v in
                                                          refused.items()},
        "trials_before": before, "trials_after": ledger.trials(family),
    }, indent=2, default=str), encoding="utf-8")
    print(f"\nwritten to {args.out}")
    return 0


def ties(families: dict) -> str:
    return ", ".join(f"{k}={len(v)}" for k, v in sorted(families.items()))


if __name__ == "__main__":
    raise SystemExit(main())
