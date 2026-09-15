"""Turn a frozen spec and a set of sessions into ONE canonical ledger.

This is the only place in the engine that simulates a fill. `run_strategy.py` calls it, the
account layer reads what it produced, and the tests drive it directly rather than through the
command line - so the thing under test is the thing that ships.

WHAT IS AND IS NOT DECIDED HERE
---------------------------------
Decided here: when a signal becomes a position, what the exit simulator does with it, what
each leg costs, and which intraday marks the chosen path mode produces.

NOT decided here: anything about the strategy. The signal is called once per session and its
output is used as given. There is no filter, no threshold, no re-entry rule and no place to
add one - a spec that loses money produces a ledger that loses money.

THE COST CONVENTION
-------------------
A round turn is split in half and charged at the bar each leg trades. The terminal P&L is the
same as charging it all at the exit, but the twin reads the intraday path, and cost not yet
charged is equity the account does not have. Getting this wrong makes an account look like it
had buffer it had already spent.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from quant_brain.markets.futures_cme import execution_sim as ex
from quant_brain.markets.futures_cme import instruments as inst
from quant_brain.research import exits as X
from quant_brain.research.canonical_ledger import (
    CanonicalLedger,
    ExecutionPathMode,
    LedgerTrade,
    build_session_ledger,
)
from quant_brain.research.strategy_spec import StrategySpec


def session_atr(g: pd.DataFrame) -> float:
    h = g["h"].to_numpy(dtype=float)
    low = g["l"].to_numpy(dtype=float)
    c = g["c"].to_numpy(dtype=float)
    prev = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - low, np.maximum(np.abs(h - prev), np.abs(low - prev)))
    return float(np.mean(tr))


def cost_for(spec: StrategySpec, slip_ticks: float, *,
             include_spread: bool | None = None) -> tuple[float, float, float]:
    """(total round-turn cost, commission+spread component, slippage component).

    The spread is part of the BASE cost, not of slippage: crossing it is what a market order
    does on every round turn, and calling it slippage would let a zero-slippage scenario
    report a fill at a price no one could get.
    """
    sym = spec.instrument
    ct = spec.sizing.contracts
    c = inst.get(sym)
    tick_value = c.spec.tick_value
    if spec.cost.commission_round_turn is not None:
        commission = spec.cost.commission_round_turn * ct
        spread = 0.0
    else:
        sim = ex.ExecutionSimulator(cost=ex.CostModel.for_contract(sym), symbol=sym)
        full = sim.round_turn_cost(ct)
        commission = c.commission_round_turn * ct
        spread = full - commission
    # The MODE decides whether the spread is charged, because crossing it is an execution
    # fact rather than a property of the strategy. `None` defers to the spec, which is what
    # a caller outside the mode ladder gets.
    charge_spread = spec.cost.include_spread if include_spread is None else include_spread
    if not charge_spread:
        spread = 0.0
    slip = (spec.cost.slippage_ticks + slip_ticks) * tick_value * ct
    return commission + spread + slip, commission + spread, slip


def build_ledger(spec: StrategySpec, sessions, feats, *, slip_ticks: float,
                 scenario: str, mode: ExecutionPathMode,
                 include_spread: bool | None = None) -> CanonicalLedger:
    """Simulate every session once and return the ledger everything downstream reads.

    `mode` changes only the intraday marks. The fills, the prices and the settled P&L are
    identical across all three modes - `test_canonical_pipeline.py` asserts that rather than
    leaving it as a comment, because it is the property that makes a mode a reporting choice
    instead of a different backtest.
    """
    contract = inst.get(spec.instrument)
    mult = contract.spec.multiplier
    ct = spec.sizing.contracts
    total_cost, base_cost, slip_cost = cost_for(spec, slip_ticks,
                                                include_spread=include_spread)
    arch = X.ExitArchitecture(
        "spec", stop_atr=spec.exit.stop_atr, target_r=spec.exit.target_r,
        structural_stop=spec.exit.structural_stop, trail_atr=spec.exit.trail_atr,
        breakeven_at_r=spec.exit.breakeven_at_r,
        time_stop_bars=spec.exit.time_stop_bars,
        use_invalidation=spec.exit.use_invalidation)

    out = []
    trade_id = 0
    for g, Xf in zip(sessions, feats, strict=True):
        pos = np.nan_to_num(np.asarray(spec.signal(Xf), dtype=float), nan=0.0)
        c = g["c"].to_numpy(dtype=float)
        h = g["h"].to_numpy(dtype=float)
        low = g["l"].to_numpy(dtype=float)
        times = g["t"].tolist()
        atr = session_atr(g)
        day = g["day"].iloc[0]
        n = len(c)
        last_entry = (spec.session.last_entry_bar
                      if spec.session.last_entry_bar is not None else n - 2)
        busy_until = spec.session.warmup_bars - 1
        prev = 0.0
        trades: list[LedgerTrade] = []
        for i, p in enumerate(pos):
            if p != 0 and p != prev and i > busy_until and i <= last_entry:
                r = X.simulate_trade(c, h, low, pos, i, int(np.sign(p)), atr, arch)
                busy_until = r.exit_bar
                gross = r.points * mult * ct
                trade_id += 1
                trades.append(LedgerTrade(
                    trade_id=trade_id, session=day, direction=r.direction, quantity=ct,
                    entry_bar=r.entry_bar, exit_bar=r.exit_bar,
                    entry_time=times[r.entry_bar], exit_time=times[r.exit_bar],
                    entry_price=r.entry_price, exit_price=r.exit_price,
                    gross_pnl=gross, commission_and_spread=base_cost,
                    slippage=slip_cost, net_pnl=gross - total_cost,
                    mae=r.mae_points * mult * ct, mfe=r.mfe_points * mult * ct,
                    r_multiple=r.r_multiple, exit_reason=r.reason,
                    holding_minutes=r.bars_held, ambiguous_bar=r.ambiguous))
            prev = p
        out.append(build_session_ledger(
            day, times, c, h, low, trades, mode=mode, multiplier=mult, contracts=ct,
            base_cost=base_cost, slip_cost=slip_cost))

    return CanonicalLedger(
        spec_hash=spec.spec_hash, strategy=spec.name, instrument=spec.instrument,
        multiplier=mult, tick_value=contract.spec.tick_value, contracts=ct,
        mode=mode, slippage_ticks=slip_ticks, scenario=scenario,
        round_turn_cost=total_cost, sessions=tuple(out))


def build_from_profile(spec: StrategySpec, sessions, feats,
                       profile) -> CanonicalLedger:
    """Build the ledger for one declared execution profile.

    The single call the runner makes per mode, so a mode's slippage, spread setting and path
    mode can never be applied in three separate places and drift apart.
    """
    return build_ledger(spec, sessions, feats, slip_ticks=profile.slippage_ticks,
                        scenario=profile.name, mode=profile.path_mode,
                        include_spread=profile.include_spread)


__all__ = ["build_from_profile", "build_ledger", "cost_for", "session_atr"]
