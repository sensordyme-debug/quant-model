"""Phases 3 and 4: gate the existing mechanisms on the opportunity forecast, and control it.

THE PREDICTION, WRITTEN BEFORE THE TEST
-----------------------------------------
This is not an open-ended search for a gate that helps. The opportunity model has a specific,
measured property that makes a specific prediction, and the prediction is recorded here so
that the result can contradict it.

The model forecasts PATH, not DISPLACEMENT. Out of sample it explains 46-51% of realised
volatility and 3-6% of the absolute net move. Sorting sessions by the forecast, median range
grows 86% from the low tercile to the high on ES while median net move grows 31%, so
efficiency - displacement divided by path - FALLS from 0.467 to 0.409. High forecast
volatility means a choppier session, not a more directional one.

    PREDICTION 1  Gating a TREND or BREAKOUT mechanism to high-forecast-volatility sessions
                  makes its PER-TRADE expectancy WORSE, because those sessions convert path
                  into displacement less efficiently.
    PREDICTION 2  Gating a MEAN-REVERSION mechanism the same way makes its per-trade
                  expectancy BETTER, for the same reason read the other way.
    PREDICTION 3  Neither effect survives a regime-matched random control, because efficiency
                  differs by only about 0.06 across terciles and that is small against the
                  session-to-session noise.

Prediction 3 is deliberately the pessimistic one. If 1 and 2 hold but 3 also holds, the gate
is real but useless, which is a different and more interesting answer than "the gate does
nothing".

WHY PER-TRADE EXPECTANCY IS THE PRIMARY METRIC
------------------------------------------------
Net profit is the wrong yardstick for a gate and it is the mistake that produced the previous
study's false positive. Every mechanism in this library loses money, so switching any of them
off for most of the calendar "improves" net profit mechanically, by an amount proportional to
how much trading was removed. A gate that fires on a tenth of the sessions will look ten
times better than one that fires on all of them, whatever it knows.

Expectancy PER TRADE cannot be gamed that way. If the gate carries information, the trades it
allows are better trades and the per-trade number moves. If the gate is only reducing
exposure, per-trade expectancy is unchanged and only the totals move. So per-trade is
reported first, net is reported alongside it for completeness, and the random control is run
on both.

THE TWO-STAGE RULE THE BRIEF INSISTS ON
-----------------------------------------
"First establish whether the gate predicts an independently measured opportunity variable.
Then test whether that independently validated gate improves strategy economics."

Stage one is done and lives in `quant_brain/research/opportunity.py`: the forecast is
validated against realised volatility, a quantity measured with no reference to any strategy's
profit and loss. Only the forecast that passed that test is allowed to gate anything here. No
gate is fitted to P&L at any point in this module.

THE CONTROL, WHICH IS THE ACTUAL POINT
----------------------------------------
Every gate is scored against random gates matched on the four things the brief names: trade
frequency, session frequency, sample size, and regime distribution.

The last one was missing from the previous study. A random gate that ignores regime can
accidentally select calm sessions, and calm sessions are safer, so an unmatched control is
too easy a benchmark. Sampling the same number of sessions from within each trailing
volatility tercile removes that escape route.

THE EVALUABLE WINDOW
--------------------
The forecast needs 80 sessions of history before it emits anything, and the trailing
threshold that turns a forecast into a decision needs more on top. Comparing a gate defined
on the back half of the sample against a baseline measured over the whole of it would confuse
the gate with the calendar, so BOTH are restricted to the sessions where a gate decision
actually exists. That is what `evaluable` is for, and it is why the baseline column here does
not match the tournament's own numbers.

WINDOW
------
The shared loader defaults to a 09:30-15:45 session, which the previous study established is
wrong: Topstep's flatten is 15:10 CT = 16:10 ET, so 15:45-16:00 is eligible and it is the
heaviest quarter-hour of the day. The constant is overridden locally rather than edited
globally, because golden test fixtures pin 376 bars and rebuilding them is a separate job.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import futures_discover as fd  # noqa: E402

#: The corrected eligible window. Overridden before any load.
fd.use_session(*fd.TOPSTEP_SESSION)

from quant_brain.markets.futures_cme import execution_sim as ex   # noqa: E402
from quant_brain.markets.futures_cme import features as fe        # noqa: E402
from quant_brain.markets.futures_cme import instruments as inst   # noqa: E402
from quant_brain.research import opportunity as opp               # noqa: E402
from strategy_tournament import build_strategies, calibrate       # noqa: E402

#: Family letters, from the tournament's own naming.
FAMILY_KIND = {"A": "trend", "B": "breakout", "C": "reversion", "D": "session",
               "E": "volatility", "F": "volume", "G": "microstructure"}

#: Sessions of forecast history before the gate THRESHOLD is considered formed. Short on
#: purpose: the forecast underneath it already carries 80 sessions of its own warm-up, so a
#: long second warm-up spends the sample twice for one decision.
THRESHOLD_WARMUP = 20

N_CONTROLS = 40
MIN_TRADES = 20


@dataclass
class Econ:
    """The economics of one strategy over one set of sessions."""

    sessions: int
    traded_sessions: int
    trades: int
    gross: float
    costs: float
    net: float
    mean_per_session: float
    mean_per_trade: float
    mean_per_traded_session: float
    t_stat: float
    win_rate: float
    profit_factor: float
    max_drawdown: float
    max_consec_losses: int


def econ(pnl: list[float], trades: float, gross: float, costs: float) -> Econ:
    a = np.asarray(pnl, dtype=float)
    traded = int(np.sum(a != 0.0))
    sd = float(a.std(ddof=1)) if a.size > 1 else 0.0
    equity = np.cumsum(a)
    peak = np.maximum.accumulate(equity) if a.size else np.array([0.0])
    wins, losses = a[a > 0].sum(), -a[a < 0].sum()
    run = best = 0
    for v in a:
        run = run + 1 if v < 0 else 0
        best = max(best, run)
    return Econ(
        sessions=int(a.size), traded_sessions=traded, trades=int(round(trades)),
        gross=float(gross), costs=float(costs), net=float(a.sum()),
        mean_per_session=float(a.mean()) if a.size else 0.0,
        mean_per_trade=float(a.sum() / trades) if trades else 0.0,
        mean_per_traded_session=float(a.sum() / traded) if traded else 0.0,
        t_stat=float(a.mean() / (sd / np.sqrt(a.size))) if sd > 0 and a.size > 1 else 0.0,
        win_rate=float((a > 0).mean()) if a.size else 0.0,
        profit_factor=float(wins / losses) if losses > 0 else float("inf") if wins > 0 else 0.0,
        max_drawdown=float((equity - peak).min()) if a.size else 0.0,
        max_consec_losses=best)


def run_strategy(strategy, sessions, feats, symbol: str, contracts: int,
                 mask: np.ndarray) -> Econ:
    """Evaluate one strategy over the sessions where `mask` is true, flat elsewhere.

    The mask zeroes the POSITION rather than dropping the session, so a gated run and an
    ungated run cover the same calendar and their per-session series line up day by day.
    """
    spec = inst.get(symbol).spec
    sim = ex.ExecutionSimulator(cost=ex.CostModel.for_contract(symbol), symbol=symbol)
    tick_cost = sim.round_turn_cost(contracts)

    pnls, trades, gross, costs = [], 0.0, 0.0, 0.0
    for i, (g, X) in enumerate(zip(sessions, feats, strict=True)):
        if not mask[i]:
            continue
        pos = np.nan_to_num(np.asarray(strategy.signal(X), dtype=float), nan=0.0)
        net_path, turns, sg = fd.session_accounting(
            pos, g["c"].to_numpy(dtype=float), multiplier=spec.multiplier,
            contracts=contracts, round_turn_cost=tick_cost)
        trades += turns
        gross += sg
        costs += turns * tick_cost
        pnls.append(float(net_path[-1]) if len(net_path) else 0.0)
    return econ(pnls, trades, gross, costs)


def build_gate(panel: pd.DataFrame, symbol: str, dates: list, quantile: float):
    """The causal opportunity gate, aligned to the session list.

    Returns (evaluable, gate_high, regime). `evaluable` marks sessions where a decision could
    be made at all; the gate and its controls are both confined to it.
    """
    g = panel[panel.symbol == symbol].sort_values("tdate").reset_index(drop=True)
    fc = pd.Series(opp.forecast_frame(g))
    thr = fc.shift(1).expanding(THRESHOLD_WARMUP).quantile(quantile)
    ok = fc.notna() & thr.notna()
    gate = ok & (fc >= thr)

    tv = g["prev_rth_rv_pct"].rolling(20).mean()
    q1 = tv.shift(1).expanding(THRESHOLD_WARMUP).quantile(1 / 3)
    q2 = tv.shift(1).expanding(THRESHOLD_WARMUP).quantile(2 / 3)
    reg = pd.Series(np.where(tv <= q1, "L", np.where(tv >= q2, "H", "M")), index=g.index)
    reg[~np.isfinite(tv)] = "?"

    lut_ok = dict(zip(g["tdate"], ok))
    lut_gate = dict(zip(g["tdate"], gate))
    lut_reg = dict(zip(g["tdate"], reg))
    evaluable = np.array([bool(lut_ok.get(d, False)) for d in dates])
    gate_hi = np.array([bool(lut_gate.get(d, False)) for d in dates])
    regime = np.array([str(lut_reg.get(d, "?")) for d in dates])
    return evaluable, gate_hi, regime


def matched_random_gates(gate: np.ndarray, evaluable: np.ndarray, regime: np.ndarray,
                         n: int, rng: np.random.Generator) -> list[np.ndarray]:
    """Random gates matched on session count WITHIN each regime stratum, inside `evaluable`.

    This is the part the previous study got wrong. Matching only the total count lets a
    random gate drift toward calm regimes, and calm regimes are easier, so the control ends
    up weaker than the gate it is supposed to challenge.
    """
    out = []
    strata = {r: np.flatnonzero(evaluable & (regime == r)) for r in set(regime.tolist())}
    want = {r: int(gate[idx].sum()) for r, idx in strata.items()}
    for _ in range(n):
        m = np.zeros(len(gate), dtype=bool)
        for r, idx in strata.items():
            k = want[r]
            if k > 0 and len(idx) >= k:
                m[rng.choice(idx, size=k, replace=False)] = True
        out.append(m)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", nargs="+", default=["ES", "NQ", "MES", "MNQ"])
    ap.add_argument("--contracts", type=int, default=1)
    ap.add_argument("--quantile", type=float, default=0.5)
    ap.add_argument("--controls", type=int, default=N_CONTROLS)
    ap.add_argument("--out", type=Path,
                    default=REPO / "research" / "opportunity_gating.csv")
    args = ap.parse_args()

    panel = pd.read_parquet(REPO / "research" / "opportunity_panel.parquet")
    rng = np.random.default_rng(31337)
    rows = []

    print("=" * 110)
    print("PHASES 3 AND 4 - OPPORTUNITY GATING WITH REGIME-MATCHED RANDOM CONTROLS")
    print(f"window {fd.OPEN_ET}-{fd.CLOSE_ET} ({fd.SESSION_BARS} bars), "
          f"{args.contracts} contract(s), gate = forecast RV >= trailing q{args.quantile}")
    print(f"{args.controls} regime-matched random gates per mechanism. "
          f"PRIMARY METRIC IS $/TRADE.")
    print("=" * 110)

    for symbol in args.symbols:
        store = REPO / "data" / "futures" / f"{symbol}.parquet"
        if not store.exists():
            continue
        df = fd.load(store, symbol)
        sessions = fd.session_frames(df)
        if not sessions:
            continue
        feats = fd.build_features(sessions, fe.library())
        dates = [g["day"].iloc[0] for g in sessions]

        n_train = len(sessions) // 2
        cal = calibrate(feats[:n_train], symbol)
        strategies = build_strategies(cal)

        evaluable, gate_hi, regime = build_gate(panel, symbol, dates, args.quantile)
        gate_lo = evaluable & ~gate_hi

        print(f"\n{symbol}: {len(sessions)} sessions, {int(evaluable.sum())} evaluable, "
              f"gate ON {int(gate_hi.sum())} / OFF {int(gate_lo.sum())}   "
              f"regimes L/M/H = {int((regime[evaluable] == 'L').sum())}/"
              f"{int((regime[evaluable] == 'M').sum())}/"
              f"{int((regime[evaluable] == 'H').sum())}")
        print(f"  {'mechanism':32} {'kind':11} {'base $/tr':>10} {'gated $/tr':>11} "
              f"{'anti $/tr':>10} {'ctrl p50':>9} {'ctrl p95':>9} {'pctile':>7}")

        controls = matched_random_gates(gate_hi, evaluable, regime, args.controls, rng)

        for s in strategies:
            base = run_strategy(s, sessions, feats, symbol, args.contracts, evaluable)
            if base.trades < MIN_TRADES:
                continue
            hi = run_strategy(s, sessions, feats, symbol, args.contracts, gate_hi)
            lo = run_strategy(s, sessions, feats, symbol, args.contracts, gate_lo)
            if hi.trades < MIN_TRADES:
                continue
            cvals = np.array([
                run_strategy(s, sessions, feats, symbol, args.contracts, m).mean_per_trade
                for m in controls])
            cnet = np.array([
                run_strategy(s, sessions, feats, symbol, args.contracts, m).net
                for m in controls])
            pct = float((cvals < hi.mean_per_trade).mean())
            kind = FAMILY_KIND.get(s.family.split(".")[0], s.family)
            rows.append({
                "symbol": symbol, "strategy": s.name, "family": s.family, "kind": kind,
                "evaluable": int(evaluable.sum()), "gate_on": int(gate_hi.sum()),
                "base_trades": base.trades, "base_net": base.net,
                "base_per_trade": base.mean_per_trade,
                "base_per_session": base.mean_per_session, "base_t": base.t_stat,
                "base_win": base.win_rate, "base_pf": base.profit_factor,
                "base_mdd": base.max_drawdown, "base_consec": base.max_consec_losses,
                "gated_trades": hi.trades, "gated_net": hi.net,
                "gated_per_trade": hi.mean_per_trade,
                "gated_per_session": hi.mean_per_session, "gated_t": hi.t_stat,
                "gated_win": hi.win_rate, "gated_pf": hi.profit_factor,
                "gated_mdd": hi.max_drawdown, "gated_consec": hi.max_consec_losses,
                "anti_trades": lo.trades, "anti_net": lo.net,
                "anti_per_trade": lo.mean_per_trade,
                "ctrl_pt_p05": float(np.percentile(cvals, 5)),
                "ctrl_pt_p50": float(np.median(cvals)),
                "ctrl_pt_p95": float(np.percentile(cvals, 95)),
                "ctrl_pt_pctile": pct,
                "ctrl_net_p50": float(np.median(cnet)),
                "ctrl_net_pctile": float((cnet < hi.net).mean()),
            })
            print(f"  {s.name[:32]:32} {kind:11} {base.mean_per_trade:10.2f} "
                  f"{hi.mean_per_trade:11.2f} {lo.mean_per_trade:10.2f} "
                  f"{np.median(cvals):9.2f} {np.percentile(cvals, 95):9.2f} {pct:7.1%}")

    out = pd.DataFrame(rows)
    out.to_csv(args.out, index=False)

    print("\n" + "=" * 110)
    print("PREDICTION SCORECARD")
    print("=" * 110)
    if len(out):
        out["pt_delta"] = out["gated_per_trade"] - out["base_per_trade"]
        for kind in ("trend", "breakout", "reversion", "session", "volatility", "volume"):
            sub = out[out["kind"] == kind]
            if not len(sub):
                continue
            print(f"  {kind:12} n={len(sub):3d}  median $/trade delta {sub.pt_delta.median():+8.2f}"
                  f"   improved {int((sub.pt_delta > 0).sum()):3d}/{len(sub):3d}"
                  f"   beat control p95 {int((sub.ctrl_pt_pctile > 0.95).sum()):3d}")
        print(f"\n  PREDICTION 1 (gate HURTS trend/breakout per-trade): "
              f"median delta trend {out[out.kind == 'trend'].pt_delta.median():+.2f}, "
              f"breakout {out[out.kind == 'breakout'].pt_delta.median():+.2f}")
        print(f"  PREDICTION 2 (gate HELPS reversion per-trade):      "
              f"median delta {out[out.kind == 'reversion'].pt_delta.median():+.2f}")
        print(f"  PREDICTION 3 (nothing beats the matched control):   "
              f"{int((out.ctrl_pt_pctile > 0.95).sum())} of {len(out)} cells beat control p95 "
              f"(expected by chance {len(out) * 0.05:.1f})")
    print(f"\nwrote {args.out}  ({len(out)} cells)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
