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
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quant_brain.core.validation import LeakageError  # noqa: E402
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
#: THE SESSION WINDOW IS NOT SET BY DEFAULT, AND THAT IS DELIBERATE.
#:
#: This module used to default to 09:30-15:45. That is WRONG for anything Topstep-related:
#: the mandatory flat is 15:10 CT = 16:10 ET, so 15:45-16:00 ET is eligible trading time -
#: and measured on this store it is the heaviest quarter-hour of the day, 10.58% of RTH
#: volume. Five research phases had to override the constant by hand, and a caller who forgot
#: silently got a truncated session and a flatten 25 minutes early.
#:
#: A dangerous implicit default is not fixed by documenting it. `load` and `session_frames`
#: now REFUSE to run until a caller states the window through `use_session`, which also
#: recomputes SESSION_BARS - the second half of the old footgun, because setting CLOSE_ET
#: without SESSION_BARS silently dropped every session.
OPEN_ET: str | None = None
CLOSE_ET: str | None = None
SESSION_BARS: int | None = None

#: The window every Topstep-compatible backtest should use: 09:30-16:00 ET, ten minutes
#: inside the 16:10 ET flatten. Named so callers can state it rather than retype it.
TOPSTEP_SESSION = ("09:30", "16:00")
#: The legacy window, kept ONLY so the golden fixtures can ask for it by name.
LEGACY_1545_SESSION = ("09:30", "15:45")


def use_session(open_et: str, close_et: str) -> None:
    """Set the session window and derive SESSION_BARS from it, atomically.

    Always use this rather than assigning the constants: assigning CLOSE_ET alone leaves
    SESSION_BARS stale, and `session_frames` filters on `len(g) != SESSION_BARS`, so every
    session is silently discarded and the run reports zero trades rather than an error.
    """
    global OPEN_ET, CLOSE_ET, SESSION_BARS
    o = dt.datetime.strptime(open_et, "%H:%M")
    c = dt.datetime.strptime(close_et, "%H:%M")
    if c <= o:
        raise ValueError(f"close {close_et} is not after open {open_et}")
    OPEN_ET, CLOSE_ET = open_et, close_et
    SESSION_BARS = int((c - o).total_seconds() // 60) + 1


def _require_session() -> None:
    if OPEN_ET is None or CLOSE_ET is None or SESSION_BARS is None:
        raise RuntimeError(
            "no session window has been set. Call "
            "futures_discover.use_session(*futures_discover.TOPSTEP_SESSION) for the "
            "Topstep-compatible 09:30-16:00 ET window, or pass your own. There is no "
            "default: the previous default of 09:30-15:45 flattened 25 minutes before the "
            "actual deadline and discarded the heaviest quarter-hour of the session.")

#: Gate thresholds. Named and documented rather than tuned: a gate whose level was chosen
#: after seeing the results is not a gate.
MIN_TRADES = 40          # below this a per-session series is not a strategy, it is a few days
MAX_COST_SHARE = 0.60    # costs above 60% of gross edge: execution eats the result
MIN_PASS_RATE = 0.10     # Topstep survival floor
MIN_WF_FOLDS = 3         # walk-forward folds that must be positive out of 5

#: Refuse any hypothesis whose GROSS P&L is this fraction of the one-bar-ahead profit
#: ceiling. The ceiling is what a perfect oracle earns: sum|close[i+1]-close[i]| times the
#: contract multiplier, i.e. every tick of every bar, always on the right side. No causal
#: rule comes near it.
#:
#: The level is not tuned, it is read off a measured gap. tests/test_leakage_redteam.py runs
#: thirteen planted cheats and several clean controls through THIS evaluator and reports each
#: one's share of the ceiling:
#:
#:      close oracle sign(c[i+1]-c[i])       100.0000%      cheat
#:      future high/low                       99.57%        cheat
#:      future volume                         94.68%        cheat
#:      whole-frame X.shift(-1)               44.90%        cheat, the weakest measured
#:      ---------------------------------------------------- the empty band, 11x wide
#:      best clean causal rule                 3.97%        honest
#:
#: 20% sits in the middle of that band on a log scale. Anything a genuine causal rule has
#: ever produced here is five times below it; the feeblest leak measured is more than twice
#: above it. Moving this number to admit a specific result is exactly the thing it exists to
#: prevent, so if it ever has to move, say why in the commit and re-run the red team.
#:
#: ONE-SIDED. A high share is strong evidence of a leak. A low share is evidence of nothing:
#: a rule that is in the market for a tenth of the session has a tenth of the opportunity and
#: earns a small share whether or not it is cheating. This canary catches the loud failures.
MAX_CEILING_SHARE = 0.20


def load(store: Path, symbol: str) -> pd.DataFrame:
    _require_session()
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
    """Only COMPLETE sessions, and "complete" is tested rather than approximated.

    THE DEFECT THIS REPLACES
    The filter was `len(g) > 200`. A 13:00 ET equity early close is 210 start-stamped RTH
    bars, 55.9% of a session, and cleared that threshold by ten. So `mean_per_session`, the
    walk-forward fold means and the `TwinDay` P&L the Topstep twin resamples were all
    averaging half days in with whole ones, and the resampled path distribution was built
    from days of two different lengths. The stores have early closes in them: three in ES and
    NQ, two in MES and MNQ.

    WHY THERE IS NO CALENDAR HERE
    The obvious fix is `SessionCalendar.session_minutes`, and it is wrong, because the repo
    has no CME futures calendar and the equity one does not describe this market. Measured
    read-only across all four stores, 1,174 session-days: on 2025-07-03, 2025-11-28 and
    2025-12-24 the store holds 225 bars where `USEquityCalendar` says 210. The cash market
    shuts at 13:00 ET on those days and CME equity-index futures run to 13:15, so 09:30-13:14
    inclusive is 225 minutes and the store is right. There are also ten days per equity-index
    store that the equity calendar calls non-trading and the futures store has RTH bars for.
    Building a holiday table from memory of the CME schedule would be a guess wearing the
    costume of a calendar, and this module's own doctrine is UNKNOWN STATE = DO NOT TRADE.

    So completeness is tested structurally instead: the day must open on the window's first
    minute, close on its last, and hold exactly one bar for every minute between. Those three
    together admit no interior hole, because SESSION_BARS distinct minutes cannot fit in a
    SESSION_BARS-minute span with a gap in it. Duplicate timestamps, which could defeat that
    counting argument, are a FAIL in the futures validator that `load` runs first.

    WHAT IT CANNOT DO
    It cannot tell a legitimate early close from an outage that truncated the day. Both are
    excluded, which is the safe direction: a short day is dropped from the sample rather than
    averaged into it as though it were whole. It also drops any day the venue genuinely closed
    early even when that day is perfectly good data - measured cost, 3 of 326 ES sessions.
    A real CME calendar would let those days be kept and scaled; that is the upgrade path,
    and it needs a verified holiday table this repo does not yet have.
    """
    _require_session()
    out = []
    for _, g in df.groupby("day", sort=True):
        if len(g) != SESSION_BARS:
            continue
        hm = g["hm"]
        if hm.iloc[0] != OPEN_ET or hm.iloc[-1] != CLOSE_ET:
            continue
        out.append(g.reset_index(drop=True))
    return out


def build_features(sessions: list[pd.DataFrame], lib: fe.FeatureSet):
    """Features per session, so no window ever reaches across a session boundary.

    The library is audited for causality first. `fe.audit_causality` perturbs the future of
    each input column and asserts no feature value before the perturbation moves; it lives
    two imports away and this funnel never called it. Measured consequence
    (tests/test_leakage_redteam.py): a feature holding the leaked target, and a feature built
    on `rolling(31, center=True)`, are both caught by that guard and were both admitted here
    without inspection.

    Three sessions, not one: a leak that only fires on a particular shape of session is still
    a leak, and the audit costs a fraction of a second per session against a search that runs
    for minutes. It refuses rather than warns, because a feature library that can see the
    future makes every number downstream of it meaningless.
    """
    probe = [sessions[i] for i in dict.fromkeys(
        (0, len(sessions) // 2, len(sessions) - 1)) if 0 <= i < len(sessions)]
    for g in probe:
        bad = fe.audit_causality(lib, g)
        if bad:
            named = "; ".join(f"{k}: {v}" for k, v in sorted(bad.items()))
            raise LeakageError(
                f"REFUSING TO SEARCH: the feature library failed its own causality audit on "
                f"session {g['day'].iloc[0]} -- {named}. Every result built on a feature that "
                f"can see the future is void. Fix the feature, do not skip this check."
            )
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

    #: What a perfect one-bar-ahead oracle would earn on this exact data. Computed once,
    #: outside `run`, because it depends only on the price series.
    ceiling = float(sum(
        np.abs(np.diff(g["c"].to_numpy(dtype=float))).sum() * spec.multiplier * contracts
        for g in sessions))

    def run(h):
        pnls, paths, trades, gross, costs = [], [], 0.0, 0.0, 0.0
        gross_next_open, opens_seen = 0.0, 0
        seen_positions: set[float] = set()
        for g, X in zip(sessions, feats, strict=True):
            pos = np.nan_to_num(np.asarray(h.signal(X), dtype=float), nan=0.0)
            seen_positions.update(np.unique(pos).tolist())
            net_path, turns, session_gross = session_accounting(
                pos, g["c"].to_numpy(dtype=float),
                multiplier=spec.multiplier, contracts=contracts, round_turn_cost=tick_cost)
            trades += turns
            gross += session_gross
            costs += turns * tick_cost
            pnls.append(float(net_path[-1]) if len(net_path) else 0.0)
            paths.append(tuple(float(x) for x in net_path))

            # The same rule filled at the NEXT BAR'S OPEN instead of the decision bar's
            # close. Decide on bar i's close, trade at bar i+1's open, earn to bar i+2's
            # open. The difference between the two is the fill subsidy, and on a book with
            # any bid-ask bounce it can BE the strategy: the red team measured a rule whose
            # entire $11,901.65 of a $11,923.05 gross - 99.8% - was the convention, at
            # +2.0003 ticks a leg over 4,760 legs. The audit measured the same mechanism at
            # +0.0551 ticks/leg over 68,388 real ES legs. Neither is a trading result.
            if "o" in g.columns:
                o = g["o"].to_numpy(dtype=float)
                if len(o) > 2:
                    gross_next_open += float(
                        (pos[:len(o) - 2] * np.diff(o[1:])).sum()) * spec.multiplier * contracts
                    opens_seen += 1

        #: Recorded on EVERY hypothesis, passing or failing, so the ledger carries it and a
        #: later reader can see the distribution rather than only the refusals.
        ceil_share = abs(gross) / ceiling if ceiling else 0.0
        priced_at_open = opens_seen == len(sessions) and opens_seen > 0

        out: dict = {"distinct_positions": len(seen_positions),
                     "pnl": pnls, "sessions": len(pnls), "trades": int(round(trades)),
                     "gross": gross, "costs": costs, "ceiling": ceiling,
                     "ceiling_share": ceil_share,
                     # Named, always, so no reader has to guess. BT-04: the engine used to
                     # return not one word about where the fill happened.
                     "fill_convention": "decision_bar_close",
                     "gross_next_open_fill": gross_next_open if priced_at_open else None,
                     "fill_subsidy": (gross - gross_next_open) if priced_at_open else None,
                     "mean_per_session": float(np.mean(pnls)) if pnls else 0.0}

        # --- not a hypothesis: the position never changes -------------------------------
        # `threshold_hypotheses` emits `np.where(x >= thr, 1, -1) * direction`, so a rule is
        # always in the market and a threshold the feature never crosses collapses the whole
        # thing to a constant. Measured on the real ES store: 104 of 136 cells are constants
        # and the 136 cells produce only 32 distinct position paths, two of which (52 cells
        # each) are plain always-long and always-short. Reporting that is the difference
        # between "817 hypotheses, 0 survivors" and "of 817 candidates, three quarters were
        # buy-and-hold with a sign".
        if len(seen_positions) <= 1:
            out["degenerate"] = True
            held = next(iter(seen_positions), 0.0)
            out["degenerate_reason"] = (
                f"the position is a constant {held:+.0f} for every bar of every session: the "
                f"threshold never binds on this data, so this is buy-and-hold with a sign, "
                f"not a hypothesis")
            return out

        # --- gate 0: leakage ----------------------------------------------------------
        # Absolute value, deliberately. A perfectly WRONG oracle is the same bug with the
        # sign flipped, and the funnel has already produced 40 PASS verdicts with negative t
        # (the worst at -11.92). Sign-flipping a leak is a one-character edit; the canary
        # would be trivially evadable if it only looked at profits.
        if ceil_share > MAX_CEILING_SHARE:
            out["leakage_ok"] = False
            out["leakage_reason"] = (
                f"gross is {ceil_share:.1%} of the one-bar-ahead profit ceiling "
                f"(${ceiling:,.0f}), above the {MAX_CEILING_SHARE:.0%} refusal level. "
                f"No causal rule earns this; look for a look-ahead in the feature, or for a "
                f"rule whose edge is the fill, before believing any statistic below.")
            return out

        if trades < MIN_TRADES:
            out["cost_ok"] = False
            out["cost_reason"] = f"only {trades} round turns; not a strategy"
            return out
        cost_share = costs / abs(gross) if gross else float("inf")
        out["cost_share"] = cost_share
        if cost_share > MAX_COST_SHARE:
            out["cost_ok"] = False
            out["cost_reason"] = (f"costs are {cost_share:.0%} of gross edge, above "
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
