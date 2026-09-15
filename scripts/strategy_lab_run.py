"""Phases 3 and 4: the baseline tournament, every strategy through one interface.

WHAT "BASELINE" MEANS HERE
----------------------------
Canonical parameters, as implemented. No tuning, no filters bolted on, no bracket layer. The
brief is explicit that optimisation comes later and only for survivors, so this run exists to
answer a prior question: with the rules exactly as they are written, what does each mechanism
actually do?

Two cost regimes are run for every cell, because they answer different questions and mixing
them is how a backtest flatters itself:

    NORMAL ECONOMICS    published Topstep round-turn commission only. This is the regime in
                        which a mechanism's raw edge is visible, and it is deliberately
                        optimistic.
    STRESSED            the same plus one tick of round-turn slippage. On these contracts one
                        tick is $12.50 (ES), $5.00 (NQ), $1.25 (MES) and $0.50 (MNQ), so this
                        is not a rounding adjustment - it is frequently the whole result.

A mechanism that is positive under the first and negative under the second has not found an
edge; it has found the difference between a mid price and a real one.

THE TWO REPORTS THE BRIEF ASKS TO KEEP SEPARATE
-------------------------------------------------
Normal economics is a question about the market. Topstep feasibility is a question about a
barrier problem with a $2,000 trailing drawdown tested intraday. A strategy can be good at one
and hopeless at the other, and the commonest way to mislead is to report whichever is kinder.
Both are computed here; the Topstep half runs in `strategy_lab_topstep.py` off the session
paths this module saves.

SIZE
----
One contract everywhere. Sizing is a separate decision with its own risk consequences, and
running the baseline at one contract keeps every comparison on the same footing. The Topstep
phase sweeps size explicitly.
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

import futures_discover as fd  # noqa: E402

fd.use_session(*fd.TOPSTEP_SESSION)

from quant_brain.markets.futures_cme import execution_sim as ex   # noqa: E402
from quant_brain.markets.futures_cme import features as fe        # noqa: E402
from quant_brain.markets.futures_cme import instruments as inst   # noqa: E402
from quant_brain.research import strategy_lab as lab              # noqa: E402
from strategy_registry import family_added                        # noqa: E402
from strategy_tournament import build_strategies, calibrate       # noqa: E402

#: Cost regimes, declared. Slippage is the ROUND-TURN total, not per leg.
REGIMES = {"normal": 0.0, "stressed": 1.0}

#: The train split used for threshold calibration. Frozen before any evaluation, matching the
#: tournament's own convention so the two are comparable.
TRAIN_FRACTION = 0.50


def session_atr_dollars(g: pd.DataFrame, multiplier: float, contracts: int) -> float:
    """The risk unit the R multiple is measured against.

    No strategy here has a stop, so there is no stop distance to divide by. The session's own
    average true range is the least arbitrary substitute: it is the scale of a typical move in
    the instrument on that day, so an R of 1 means "made about one session's worth of typical
    movement". It is NOT a stop-based R and is never described as one.
    """
    h = g["h"].to_numpy(dtype=float)
    low = g["l"].to_numpy(dtype=float)
    c = g["c"].to_numpy(dtype=float)
    prev = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - low, np.maximum(np.abs(h - prev), np.abs(low - prev)))
    return float(np.mean(tr)) * multiplier * contracts


def run_symbol(symbol: str, contracts: int, regime: str) -> tuple[list, list, list]:
    store = REPO / "data" / "futures" / f"{symbol}.parquet"
    if not store.exists():
        return [], [], []
    df = fd.load(store, symbol)
    sessions = fd.session_frames(df)
    if not sessions:
        return [], [], []
    feats = fd.build_features(sessions, fe.library())
    n_train = int(len(sessions) * TRAIN_FRACTION)
    cal = calibrate(feats[:n_train], symbol)
    strategies = list(build_strategies(cal)) + list(family_added(cal))

    spec = inst.get(symbol).spec
    sim = ex.ExecutionSimulator(cost=ex.CostModel.for_contract(symbol), symbol=symbol)
    cost = lab.CostModel(round_turn_commission=sim.round_turn_cost(1),
                         tick_value=spec.tick_value,
                         slippage_ticks=REGIMES[regime])
    rt = cost.per_round_turn(contracts)

    all_trades, all_sessions, portfolios = [], [], []
    atrs = [session_atr_dollars(g, spec.multiplier, contracts) for g in sessions]
    for s in strategies:
        trades: list[lab.Trade] = []
        sess: list[lab.SessionResult] = []
        for i, (g, X) in enumerate(zip(sessions, feats, strict=True)):
            pos = np.nan_to_num(np.asarray(s.signal(X), dtype=float), nan=0.0)
            tr, eq = lab.extract_trades(
                pos, g["c"].to_numpy(dtype=float), g["t"],
                strategy=s.name, symbol=symbol, session=g["day"].iloc[0],
                multiplier=spec.multiplier, contracts=contracts, cost=cost,
                atr_dollars=atrs[i])
            trades.extend(tr)
            sess.append(lab.summarise_session(
                tr, eq, pos, session=g["day"].iloc[0], symbol=symbol,
                strategy=s.name, cost_per_rt=rt))
        port = lab.summarise_portfolio(trades, sess, strategy=s.name, symbol=symbol)
        all_trades.extend(trades)
        all_sessions.extend(sess)
        portfolios.append(port)
    return all_trades, all_sessions, portfolios


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", nargs="+", default=["ES", "NQ", "MES", "MNQ"])
    ap.add_argument("--contracts", type=int, default=1)
    args = ap.parse_args()

    rows, trade_rows = [], []
    session_store: dict = {}

    for regime in REGIMES:
        for symbol in args.symbols:
            trades, sessions, ports = run_symbol(symbol, args.contracts, regime)
            if not ports:
                continue
            for p in ports:
                r = p.as_row()
                r["regime"] = regime
                r["contracts"] = args.contracts
                rows.append(r)
            if regime == "normal":
                for t in trades:
                    trade_rows.append({
                        "strategy": t.strategy, "symbol": t.symbol,
                        "session": t.session, "entry_time": t.entry_time,
                        "exit_time": t.exit_time, "direction": t.direction,
                        "contracts": t.contracts, "entry_price": t.entry_price,
                        "exit_price": t.exit_price, "gross_pnl": t.gross_pnl,
                        "commission": t.commission, "slippage": t.slippage,
                        "net_pnl": t.net_pnl, "mae": t.mae, "mfe": t.mfe,
                        "r_multiple": t.r_multiple, "exit_reason": t.exit_reason,
                        "holding_minutes": t.holding_minutes})
                for s in sessions:
                    session_store.setdefault((s.strategy, s.symbol), []).append(
                        {"session": s.session, "net_pnl": s.net_pnl,
                         "n_trades": s.n_trades, "path": s.path,
                         "max_intraday_dd": s.max_intraday_dd,
                         "forced_flatten": s.forced_flatten,
                         "time_in_market": s.time_in_market})
            print(f"  {regime:9} {symbol:5} {len(ports):3d} strategies, "
                  f"{len(trades):7d} trades")

    port_df = pd.DataFrame(rows)
    port_df.to_csv(REPO / "research" / "lab_portfolio.csv", index=False)
    pd.DataFrame(trade_rows).to_parquet(REPO / "research" / "lab_trades.parquet",
                                        index=False)
    with (REPO / "research" / "lab_sessions.pkl").open("wb") as fh:
        pickle.dump(session_store, fh)

    print("\n" + "=" * 112)
    print("PHASE 4 - BASELINE TOURNAMENT")
    print(f"{len(port_df)} strategy-instrument-regime cells, {args.contracts} contract, "
          f"{fd.OPEN_ET}-{fd.CLOSE_ET} ET")
    print("=" * 112)

    for regime in REGIMES:
        sub = port_df[port_df.regime == regime]
        print(f"\n--- {regime.upper()} "
              f"({'commission only' if regime == 'normal' else 'plus 1 tick round-turn slippage'}) "
              + "-" * 40)
        print(f"  cells                              {len(sub)}")
        print(f"  net P&L > 0                        {int((sub.net_pnl > 0).sum())}")
        print(f"  expectancy per trade > 0           "
              f"{int((sub.expectancy_per_trade > 0).sum())}")
        print(f"  |t| > 1.96 on the daily series     {int((sub.t_stat.abs() > 1.96).sum())}")
        print(f"  t > 1.96 AND net > 0               "
              f"{int(((sub.t_stat > 1.96) & (sub.net_pnl > 0)).sum())}")
        best = sub.reindex(sub.net_pnl.sort_values(ascending=False).index).head(8)
        print(f"\n  {'strategy':30} {'sym':5} {'trades':>7} {'net $':>10} {'$/trade':>9} "
              f"{'PF':>6} {'win%':>6} {'maxDD $':>10} {'t':>6}")
        for _, r in best.iterrows():
            pf = r.profit_factor
            print(f"  {r.strategy[:30]:30} {r.symbol:5} {int(r.n_trades):7d} "
                  f"{r.net_pnl:10.0f} {r.expectancy_per_trade:9.2f} "
                  f"{pf if np.isfinite(pf) else float('nan'):6.2f} {r.win_rate:6.1%} "
                  f"{r.max_drawdown:10.0f} {r.t_stat:6.2f}")

    print("\n" + "=" * 112)
    print("SURVIVAL FROM NORMAL TO STRESSED")
    print("=" * 112)
    piv = port_df.pivot_table(index=["strategy", "symbol"], columns="regime",
                              values="expectancy_per_trade")
    if {"normal", "stressed"}.issubset(piv.columns):
        piv = piv.dropna()
        pos_n = int((piv["normal"] > 0).sum())
        pos_s = int((piv["stressed"] > 0).sum())
        both = int(((piv["normal"] > 0) & (piv["stressed"] > 0)).sum())
        print(f"  positive at commission only          {pos_n} of {len(piv)}")
        print(f"  positive with 1 tick slippage        {pos_s} of {len(piv)}")
        print(f"  positive in BOTH                     {both}")
        print(f"  one tick erases                      {pos_n - pos_s} cells")

    print("\n" + "=" * 112)
    print("EXIT-REASON MIX  (there are only three, because no strategy has a stop)")
    print("=" * 112)
    td = pd.DataFrame(trade_rows)
    if len(td):
        mix = td.exit_reason.value_counts(normalize=True)
        for k, v in mix.items():
            print(f"  {k:18} {v:6.1%}")
        print(f"\n  median holding time: {td.holding_minutes.median():.0f} minutes")
        print(f"  trades per session-strategy-instrument cell: "
              f"{len(td) / max(1, len(port_df[port_df.regime == 'normal'])):.0f}")
    print(f"\nwrote research/lab_portfolio.csv, lab_trades.parquet, lab_sessions.pkl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
