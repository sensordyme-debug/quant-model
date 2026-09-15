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


def bar_at(g: pd.DataFrame, hhmm: str | None, *, default: int) -> int:
    """The index of the bar stamped `hhmm` in this session, or `default` when unstated.

    Resolved from the session's own `hm` column rather than computed from the window, so a
    session that is structurally complete but stamped differently than expected raises here
    instead of silently shifting every rule by a bar.
    """
    if hhmm is None:
        return default
    hits = np.flatnonzero(g["hm"].to_numpy() == hhmm)
    if not len(hits):
        raise ValueError(
            f"session {g['day'].iloc[0]} has no bar stamped {hhmm}. The spec states a "
            f"wall-clock rule the data cannot locate; the engine will not approximate it "
            f"with the nearest bar.")
    return int(hits[0])


def entry_cutoff(g: pd.DataFrame, spec: StrategySpec, flat_bar: int, n: int) -> int:
    """The last bar index at which a NEW position may open.

    Three sources, in the spec's own order of precedence, and never more than one of them is
    set (`SessionSpec` refuses both spellings at construction). Whatever it resolves to, it is
    capped at `flat_bar - 1`: an entry on the forced-flat bar could not be held for a single
    bar and could only lose a round turn.
    """
    if spec.session.last_entry_et is not None:
        cutoff = bar_at(g, spec.session.last_entry_et, default=n - 2)
    elif spec.session.last_entry_bar is not None:
        cutoff = spec.session.last_entry_bar
    else:
        cutoff = n - 2
    return min(cutoff, flat_bar - 1)


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
        "spec", stop_atr=spec.exit.stop_atr, stop_points=spec.exit.stop_points,
        target_r=spec.exit.target_r, target_points=spec.exit.target_points,
        structural_stop=spec.exit.structural_stop, trail_atr=spec.exit.trail_atr,
        trail_points=spec.exit.trail_points,
        breakeven_at_r=spec.exit.breakeven_at_r,
        time_stop_bars=spec.exit.time_stop_bars,
        use_invalidation=spec.exit.use_invalidation)
    cooldown = spec.risk.cooldown_bars
    cap = spec.risk.max_trades_per_session

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
        flat_bar = bar_at(g, spec.session.flat_by_et, default=n - 1)
        last_entry = entry_cutoff(g, spec, flat_bar, n)
        #: The first bar at which a NEW position may open. `warmup_bars` is a count of bars
        #: that must elapse, so bar index `warmup_bars` is the first permitted one.
        next_entry_at = spec.session.warmup_bars
        prev = 0.0
        taken = 0
        trades: list[LedgerTrade] = []
        for i, p in enumerate(pos):
            if (p != 0 and p != prev and i >= next_entry_at and i <= last_entry
                    and (cap is None or taken < cap)):
                r = X.simulate_trade(c, h, low, pos, i, int(np.sign(p)), atr, arch,
                                     last_bar=flat_bar)
                # THE REVERSAL RULE. `>=` rather than `>` is load-bearing.
                #
                # When a signal flips +1 -> -1 at bar i, `use_invalidation` closes the long
                # AT bar i and the short wants to open AT bar i - one reversal, two legs, one
                # price. The previous `i > exit_bar` test refused that entry, and because
                # `prev` then advanced past the flip, the run of -1 that followed never
                # produced another edge either: the short leg was dropped for the rest of the
                # run, silently. Measured on an alternating +1/-1 signal, the engine returned
                # four trades, ALL LONG. A spec that says "long above, short below" was being
                # tested as "long above, flat below" under its own hash.
                #
                # Re-entry at the exit bar cannot loop: `simulate_trade` scans from
                # `entry_bar + 1`, so every trade advances the bar index by at least one, and
                # `last_entry <= flat_bar - 1` keeps the final bar entry-free.
                next_entry_at = r.exit_bar + cooldown
                taken += 1
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


__all__ = ["bar_at", "build_from_profile", "build_ledger", "cost_for",
           "entry_cutoff", "session_atr"]
