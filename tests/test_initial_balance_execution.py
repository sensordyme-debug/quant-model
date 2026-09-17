"""Phase 1/E-F-G for the ES strategy: fills, costs, and an INDEPENDENT reconciliation.

The money is checked three ways: against arithmetic typed into the test, against
`quant_brain.research.reference_ledger` (which shares no code with this engine), and against
the identity `gross - entry_slip - exit_slip - commission == net` on every trade.
"""
from __future__ import annotations

import datetime as dt
import itertools

import pytest

from quant_brain.research.reference_ledger import reference_pnl_one_trade
from quant_brain.strategies.initial_balance_reversion.engine import (
    EXIT_STOP,
    EXIT_TARGET,
    EXIT_TIME,
)
from quant_brain.strategies.initial_balance_reversion.orders import Bracket
from quant_brain.strategies.initial_balance_reversion.spec import (
    BASELINE_FROZEN,
    FROZEN,
    IDEAL,
    STRESS_1TICK,
    STRESS_2TICK,
    FrozenSpec,
)
from tests.conftest_ib import Session, run

PV, TICK, COMM = 50.0, 0.25, 4.14


# ======================================================================================
# F. TWENTY-FIVE HAND-CALCULATED CONTRACT-MATH SCENARIOS
# ======================================================================================

HAND = [
    # (entry, exit, direction, entry_ticks, exit_ticks, expected_net)
    (5000.00, 5010.00,  1, 0, 0,  500.00 - COMM),
    (5000.00, 5010.00,  1, 1, 0,  500.00 - 12.50 - COMM),
    (5000.00, 5010.00,  1, 1, 1,  500.00 - 25.00 - COMM),
    (5000.00, 5010.00, -1, 0, 0, -500.00 - COMM),
    (5010.00, 5000.00, -1, 1, 0,  500.00 - 12.50 - COMM),
    (5010.00, 5000.00, -1, 1, 1,  500.00 - 25.00 - COMM),
    (5000.00, 5000.25,  1, 0, 0,   12.50 - COMM),
    (5000.00, 4999.75,  1, 0, 0,  -12.50 - COMM),
    (5000.00, 5000.00,  1, 1, 0,    0.00 - 12.50 - COMM),
    (5000.00, 5000.00, -1, 1, 1,    0.00 - 25.00 - COMM),
    (5000.00, 5007.75,  1, 1, 0,  387.50 - 12.50 - COMM),
    (5000.00, 4992.25,  1, 1, 1, -387.50 - 25.00 - COMM),
    (5000.00, 5002.50, -1, 1, 0, -125.00 - 12.50 - COMM),
    (4998.75, 5010.25,  1, 1, 0,  575.00 - 12.50 - COMM),
    (5023.25, 5010.00, -1, 1, 0,  662.50 - 12.50 - COMM),
    (5000.00, 5035.00,  1, 0, 0, 1750.00 - COMM),
    (5000.00, 4965.00,  1, 0, 0, -1750.00 - COMM),
    (6000.00, 6016.00, -1, 1, 2, -800.00 - 37.50 - COMM),
    (6000.00, 5984.00,  1, 1, 3, -800.00 - 50.00 - COMM),
    (5555.25, 5555.50,  1, 0, 0,   12.50 - COMM),
    (5555.25, 5555.00,  1, 0, 0,  -12.50 - COMM),
    (4321.00, 4331.00, -1, 2, 0, -500.00 - 25.00 - COMM),
    (4321.00, 4311.00, -1, 2, 2,  500.00 - 50.00 - COMM),
    (5100.00, 5100.75,  1, 1, 0,   37.50 - 12.50 - COMM),
    (5100.00, 5099.25, -1, 1, 0,   37.50 - 12.50 - COMM),
]


@pytest.mark.parametrize("entry,exit_,d,et,xt,expected", HAND,
                         ids=[f"case{i}" for i in range(len(HAND))])
def test_hand_calculated_es_contract_math(entry, exit_, d, et, xt, expected):
    """Longhand, then confirmed by code that shares nothing with the engine."""
    gross = (exit_ - entry) * d * PV
    net = gross - et * TICK * PV - xt * TICK * PV - COMM
    assert net == pytest.approx(expected, abs=1e-9)

    ref_gross, ref_comm, _ = reference_pnl_one_trade(entry, exit_, d, 1, PV, COMM)
    assert ref_gross == pytest.approx(gross, abs=1e-9)
    assert ref_comm == pytest.approx(COMM, abs=1e-9)


def test_the_tick_and_point_values_are_the_frozen_ones():
    assert FROZEN.point_value == 50.0
    assert FROZEN.tick == 0.25
    assert FROZEN.tick_value == 12.50
    assert FROZEN.tick_value == FROZEN.tick * FROZEN.point_value


# ======================================================================================
# THE COST IDENTITY, ON EVERY TRADE THE ENGINE PRODUCES
# ======================================================================================

def _scenarios() -> list[Session]:
    return [
        (Session().ib(high=5020.0, low=5000.0).quiet("10:30", "10:40", 5010.0)
         .block("10:40", 5002.0, 5002.0, 4995.0, 5002.0)
         .block("10:45", 5002.0, 5012.0, 5002.0, 5011.0).quiet("10:50", "15:45", 5011.0)),
        (Session().ib(high=5020.0, low=5000.0).quiet("10:30", "10:40", 5010.0)
         .block("10:40", 5018.0, 5025.0, 5018.0, 5018.0)
         .block("10:45", 5018.0, 5018.0, 5008.0, 5009.0).quiet("10:50", "15:45", 5009.0)),
        (Session().ib(high=5020.0, low=5000.0)
         .block("10:30", 5000.0, 5000.0, 4998.0, 4998.0)
         .block("10:35", 4998.0, 5001.0, 4998.0, 5001.0)
         .block("10:40", 5001.0, 5001.0, 4990.0, 4990.0).quiet("10:45", "15:45", 4990.0)),
        (Session().ib(high=5020.0, low=5000.0)
         .block("10:30", 5000.0, 5000.0, 4999.0, 4999.0)
         .block("10:35", 4999.0, 5001.0, 4999.0, 5001.0).quiet("10:40", "15:45", 5001.0)),
    ]


@pytest.mark.parametrize("scenario,profile",
                         list(itertools.product(range(4),
                                                (IDEAL, BASELINE_FROZEN, STRESS_1TICK,
                                                 STRESS_2TICK))))
def test_gross_minus_costs_equals_net_on_every_trade(scenario, profile):
    eng = run(_scenarios()[scenario], spec=FrozenSpec(execution=profile))
    assert eng.trades
    for t in eng.trades:
        assert t.net_pnl == pytest.approx(
            t.gross_pnl - t.entry_slippage - t.exit_slippage - t.commission, abs=1e-9)
        assert t.commission == COMM, "charged once, as a round turn"
        assert t.entry_slippage == profile.entry_ticks * TICK * PV


def test_slippage_is_never_double_counted_as_a_spread():
    """The only cost lines are commission and the declared tick slippage."""
    eng = run(_scenarios()[0])
    t = eng.trades[0]
    assert t.exit_reason == EXIT_TARGET
    assert t.exit_slippage == 0.0, "a limit target is never charged"
    assert t.entry_slippage == 12.50
    assert t.commission == 4.14
    assert t.net_pnl == pytest.approx(t.gross_pnl - 16.64, abs=1e-9)


@pytest.mark.parametrize("profile,expected_exit_slip", [
    (IDEAL, 0.0), (BASELINE_FROZEN, 0.0), (STRESS_1TICK, 12.50), (STRESS_2TICK, 25.00),
])
def test_market_exit_slippage_is_reported_separately_and_is_zero_in_the_baseline(
        profile, expected_exit_slip):
    """AMBIGUITY B9: the specification does not price the time stop, so the baseline does
    not invent a number - and the stress profiles measure what that omission is worth."""
    eng = run(_scenarios()[3], spec=FrozenSpec(execution=profile))
    t = eng.trades[0]
    assert t.exit_reason == EXIT_TIME
    assert t.exit_slippage == expected_exit_slip


# ======================================================================================
# E. AMBIGUOUS BARS AND GAPS
# ======================================================================================

def test_the_bracket_reports_an_ambiguous_bar():
    b = Bracket(direction=1, quantity=1, stop_price=4990.0, target_price=5010.0,
                deadline=dt.datetime(2026, 6, 10, 12, 0, tzinfo=dt.UTC))
    assert b.stop_touched(high=5000.0, low=4989.0)
    assert b.target_touched(high=5011.0, low=5000.0)
    assert b.ambiguous(high=5011.0, low=4989.0)
    assert not b.ambiguous(high=5000.0, low=4989.0)


def test_a_gap_through_the_target_still_fills_at_the_target():
    s = (Session().ib(high=5020.0, low=5000.0)
         .block("10:30", 5000.0, 5000.0, 4998.0, 4998.0)
         .block("10:35", 4998.0, 5001.0, 4998.0, 5001.0)
         .block("10:40", 5060.0, 5065.0, 5060.0, 5062.0)     # opens far above the 5010 target
         .quiet("10:45", "15:45", 5062.0))
    eng = run(s)
    t = eng.trades[0]
    assert t.exit_reason == EXIT_TARGET
    assert t.exit_price == 5010.0, "at the level, not at the gap - declared, optimistic"


def test_the_stop_is_taken_when_both_legs_are_touched():
    s = (Session().ib(high=5020.0, low=5000.0)
         .block("10:30", 5000.0, 5000.0, 4998.0, 4998.0)
         .block("10:35", 4998.0, 5001.0, 4998.0, 5001.0)
         .block("10:40", 5001.0, 5015.0, 4990.0, 5000.0)
         .quiet("10:45", "15:45", 5000.0))
    eng = run(s)
    assert eng.trades[0].exit_reason == EXIT_STOP
    assert eng.trades[0].ambiguous_bar


# ======================================================================================
# G. LEDGER RECONCILIATION AGAINST THE INDEPENDENT REFERENCE
# ======================================================================================

def test_every_trade_reconciles_with_the_independent_reference():
    mismatches = []
    for i in range(4):
        for profile in (IDEAL, BASELINE_FROZEN, STRESS_1TICK, STRESS_2TICK):
            eng = run(_scenarios()[i], spec=FrozenSpec(execution=profile))
            for t in eng.trades:
                d = t.direction
                ideal_entry = t.entry_price - (t.entry_slippage / PV) * d
                ideal_exit = t.exit_price + (t.exit_slippage / PV) * d
                gross, comm, _ = reference_pnl_one_trade(ideal_entry, ideal_exit, d, 1,
                                                         PV, COMM)
                net = gross - t.entry_slippage - t.exit_slippage - comm
                if abs(gross - t.gross_pnl) > 1e-9 or abs(net - t.net_pnl) > 1e-9:
                    mismatches.append((i, profile.name, t.trade_id, t.gross_pnl, gross,
                                       t.net_pnl, net))
    assert not mismatches, mismatches


def test_a_trade_is_fully_reconstructible_from_its_ledger_row():
    """Every field the brief requires is present and internally consistent."""
    eng = run(_scenarios()[0])
    t = eng.trades[0]
    for field in ("trade_id", "session", "direction", "quantity", "entry_time", "exit_time",
                  "entry_price", "exit_price", "ib_high", "ib_low", "ib_range",
                  "ib_midpoint", "trap_extreme", "stop_price", "target_price", "gross_pnl",
                  "commission", "entry_slippage", "exit_slippage", "net_pnl", "exit_reason",
                  "holding_minutes", "mae", "mfe", "ambiguous_bar", "realized_before",
                  "realized_after"):
        assert hasattr(t, field), field
    assert t.ib_range == t.ib_high - t.ib_low
    assert t.ib_midpoint == (t.ib_high + t.ib_low) / 2.0
    assert t.stop_price == t.trap_extreme - FROZEN.tick * t.direction
    assert t.holding_minutes == int((t.exit_time - t.entry_time).total_seconds() // 60)
    assert t.realized_after == pytest.approx(t.realized_before + t.net_pnl, abs=1e-9)


def test_running_the_same_session_twice_is_identical():
    a, b = run(_scenarios()[0]), run(_scenarios()[0])
    assert [vars(t) for t in a.trades] == [vars(t) for t in b.trades]


# ======================================================================================
# D. BAR SEMANTICS - every timestamp reconstructible
# ======================================================================================

def test_the_decision_and_execution_instants_are_the_bucket_close():
    eng = run(_scenarios()[0])
    t = eng.trades[0]
    #: the rejection bucket starts 10:40 and covers 10:40:00-10:44:59, so it completes at
    #: 10:45:00 - which is the decision instant AND the execution instant.
    assert t.entry_time.strftime("%H:%M:%S") == "10:45:00"
    assert t.entry_time.minute % 5 == 0
    #: and the fill is that bucket's close, moved one tick adverse
    assert t.entry_price == 5002.0 + FROZEN.tick


def test_every_exit_lands_on_a_bucket_boundary():
    for i in range(4):
        eng = run(_scenarios()[i])
        for t in eng.trades:
            assert t.exit_time.second == 0
            assert t.exit_time.minute % 5 == 0
            assert t.exit_time >= t.entry_time


def test_no_fill_price_is_off_tick():
    for i in range(4):
        for profile in (IDEAL, BASELINE_FROZEN, STRESS_1TICK, STRESS_2TICK):
            eng = run(_scenarios()[i], spec=FrozenSpec(execution=profile))
            for t in eng.trades:
                for price in (t.entry_price, t.exit_price, t.stop_price, t.target_price):
                    assert abs((price / FROZEN.tick) - round(price / FROZEN.tick)) < 1e-9, (
                        f"{price} is not a placeable ES price")
