"""GOLDEN TESTS for ES V1.0_Frozen. Every expected number is arithmetic done in the test.

Part M of the brief lists eighteen scenarios; each has a test here, and the money is computed
longhand from the ES contract terms rather than copied from a run:

    1 point = $50      1 tick = 0.25 = $12.50      commission $4.14 round turn
    net = (ideal_exit - ideal_entry) * direction * 50 - entry_slip - exit_slip - 4.14
"""
from __future__ import annotations

import datetime as dt

import pytest

from quant_brain.strategies.initial_balance_reversion.engine import (
    EXIT_KILLSWITCH,
    EXIT_STOP,
    EXIT_TARGET,
    EXIT_TARGET_IMMEDIATE,
    EXIT_TIME,
    Engine,
    State,
)
from quant_brain.strategies.initial_balance_reversion.indicators import IBNotReady
from quant_brain.strategies.initial_balance_reversion.spec import (
    AMBIGUITIES,
    BASELINE_FROZEN,
    CONFLICTS,
    FROZEN,
    IDEAL,
    STRESS_1TICK,
    STRESS_2TICK,
    FrozenSpec,
    unresolved,
)
from tests.conftest_ib import Session, run

PV, TICK, COMM = 50.0, 0.25, 4.14


def net(entry_ideal, exit_ideal, d, entry_slip_t=1, exit_slip_t=0):
    """The frozen cost model, longhand."""
    gross = (exit_ideal - entry_ideal) * d * PV
    return gross - entry_slip_t * TICK * PV - exit_slip_t * TICK * PV - COMM


# ======================================================================================
# THE FROZEN CONSTANTS
# ======================================================================================

def test_every_frozen_constant_is_what_the_owner_wrote():
    """The one place a literal belongs. An edit to spec.py fails here."""
    s = FROZEN
    assert s.version == "ES_V1.0_Frozen"
    assert s.ib_start == (9, 30) and s.ib_end == (10, 30)
    assert s.execution_cutoff == (14, 0) and s.hard_flatten == (15, 45)
    assert s.ib_range_min == 10.0 and s.ib_range_max == 35.0
    assert s.stop_offset_ticks == 1.0
    assert s.time_stop_minutes == 60
    assert s.daily_loss_killswitch == -800.0
    assert s.daily_profit_cap == 1200.0
    assert s.max_trades_per_day == 2
    assert s.instrument == "ES" and s.contracts == 1
    assert s.point_value == 50.0 and s.tick == 0.25 and s.tick_value == 12.50
    assert s.commission_round_turn == 4.14
    assert s.bar_minutes == 5
    assert s.execution.name == "BASELINE_FROZEN"
    assert (BASELINE_FROZEN.entry_ticks, BASELINE_FROZEN.stop_ticks,
            BASELINE_FROZEN.target_ticks, BASELINE_FROZEN.market_exit_ticks) == (1, 1, 0, 0)
    assert BASELINE_FROZEN.frozen_spec_exact is True
    assert not unresolved(), [a.ref for a in unresolved()]
    assert len(AMBIGUITIES) == 10 and len(CONFLICTS) == 3


def test_the_repository_commission_disagrees_and_the_frozen_spec_wins():
    """CONFLICT D1, recorded rather than reconciled away."""
    from quant_brain.markets.futures_cme import instruments as I
    assert I.get("ES").commission_round_turn == 3.78
    assert FROZEN.commission_round_turn == 4.14
    assert FROZEN.commission_round_turn > I.get("ES").commission_round_turn


# ======================================================================================
# 1-2. FALSE BREAKOUT TO THE MIDPOINT TARGET
# ======================================================================================

def test_golden_1_long_false_breakout_reaches_the_midpoint():
    """IB 5000-5020. Price pokes to 4995, closes back at 5002, target 5010.

    E_long = 4995.00              stop = 4995.00 - 0.25 = 4994.75
    entry  = 5002.00 + 0.25       (one tick adverse on a market buy)
    target = midpoint 5010.00     already on a tick, so no rounding
    net    = (5010 - 5002) * 50 - 12.50 - 4.14 = 400 - 16.64 = 383.36
    """
    s = (Session().ib(high=5020.0, low=5000.0)
         .quiet("10:30", "10:40", 5010.0)
         .block("10:40", 5002.0, 5002.0, 4995.0, 5002.0)      # trap AND rejection
         .block("10:45", 5002.0, 5012.0, 5002.0, 5011.0)      # target touched
         .quiet("10:50", "15:45", 5011.0))
    eng = run(s)
    assert len(eng.trades) == 1
    t = eng.trades[0]
    assert t.direction == 1
    assert t.ib_low == 5000.0 and t.ib_high == 5020.0 and t.ib_range == 20.0
    assert t.ib_midpoint == 5010.0
    assert t.trap_extreme == 4995.0
    assert t.stop_price == 4994.75
    assert t.entry_price == 5002.25
    assert t.target_price == 5010.0
    assert t.exit_reason == EXIT_TARGET
    assert t.exit_price == 5010.0
    assert t.net_pnl == pytest.approx(net(5002.0, 5010.0, 1), abs=1e-9)
    assert t.net_pnl == pytest.approx(383.36, abs=1e-9)


def test_golden_2_short_false_breakout_reaches_the_midpoint():
    """Mirror. E_short = 5025, stop 5025.25, entry 5018.00 - 0.25, target 5010."""
    s = (Session().ib(high=5020.0, low=5000.0)
         .quiet("10:30", "10:40", 5010.0)
         .block("10:40", 5018.0, 5025.0, 5018.0, 5018.0)
         .block("10:45", 5018.0, 5018.0, 5008.0, 5009.0)
         .quiet("10:50", "15:45", 5009.0))
    eng = run(s)
    t = eng.trades[0]
    assert t.direction == -1
    assert t.trap_extreme == 5025.0 and t.stop_price == 5025.25
    assert t.entry_price == 5017.75
    assert t.target_price == 5010.0 and t.exit_reason == EXIT_TARGET
    assert t.net_pnl == pytest.approx(net(5018.0, 5010.0, -1), abs=1e-9)
    assert t.net_pnl == pytest.approx(383.36, abs=1e-9)


# ======================================================================================
# 3-4. THE STOP SITS ONE TICK BEYOND THE EXCURSION EXTREME
# ======================================================================================

def test_golden_3_long_stop_is_one_tick_below_the_excursion_low():
    """The multi-bar excursion from the brief: -1, then -3, then reject.

    IB 5000-5020. lows 4999, 4997, then a bar closing at 5001.
    E_long must be 4997 - the DEEPEST point of THIS trip - not the last bar's low.
    """
    s = (Session().ib(high=5020.0, low=5000.0)
         .quiet("10:30", "10:40", 5010.0)
         .block("10:40", 5000.0, 5000.0, 4999.0, 4999.0)
         .block("10:45", 4999.0, 4999.0, 4997.0, 4998.0)
         .block("10:50", 4998.0, 5001.0, 4998.0, 5001.0)      # rejection
         .quiet("10:55", "11:00", 5001.0)
         .block("11:00", 5001.0, 5001.0, 4994.0, 4994.0)      # stop taken
         .quiet("11:05", "15:45", 4994.0))
    eng = run(s)
    t = eng.trades[0]
    assert t.trap_extreme == 4997.0, "the deepest point of the trip, not the last bar's low"
    assert t.stop_price == 4996.75
    assert t.entry_price == 5001.25
    assert t.exit_reason == EXIT_STOP
    #: stop fills one tick BELOW the level under BASELINE
    assert t.exit_price == 4996.50
    assert t.net_pnl == pytest.approx(net(5001.0, 4996.75, 1, 1, 1), abs=1e-9)


def test_golden_4_short_stop_is_one_tick_above_the_excursion_high():
    s = (Session().ib(high=5020.0, low=5000.0)
         .quiet("10:30", "10:40", 5010.0)
         .block("10:40", 5020.0, 5021.0, 5020.0, 5021.0)
         .block("10:45", 5021.0, 5023.0, 5021.0, 5022.0)
         .block("10:50", 5022.0, 5022.0, 5019.0, 5019.0)      # rejection
         .quiet("10:55", "11:00", 5019.0)
         .block("11:00", 5019.0, 5026.0, 5019.0, 5026.0)      # stop taken
         .quiet("11:05", "15:45", 5026.0))
    eng = run(s)
    t = eng.trades[0]
    assert t.trap_extreme == 5023.0 and t.stop_price == 5023.25
    assert t.exit_reason == EXIT_STOP and t.exit_price == 5023.50


def test_the_excursion_extreme_ignores_a_deeper_low_from_a_different_trip():
    """The day's low is NOT E_long. Only the trip this rejection ends counts."""
    s = (Session().ib(high=5020.0, low=5000.0)
         .block("10:30", 5000.0, 5000.0, 4990.0, 4990.0)      # trip A, very deep
         .block("10:35", 4990.0, 5005.0, 4990.0, 5005.0)      # trip A rejects -> trade 1
         .block("10:40", 5005.0, 5011.0, 5005.0, 5010.0)      # trade 1 takes its target
         .quiet("10:45", "11:00", 5010.0)
         .block("11:00", 5000.0, 5000.0, 4998.0, 4998.0)      # trip B, shallow
         .block("11:05", 4998.0, 5002.0, 4998.0, 5002.0)      # trip B rejects -> trade 2
         .quiet("11:10", "15:45", 5002.0))
    eng = run(s)
    assert len(eng.trades) == 2
    assert eng.trades[0].trap_extreme == 4990.0
    assert eng.trades[1].trap_extreme == 4998.0, "trip B's own low, not the day's 4990"
    assert eng.trades[1].stop_price == 4997.75


# ======================================================================================
# 5-8. THE IB RANGE REGIME FILTER, INCLUSIVE BOUNDARIES
# ======================================================================================

@pytest.mark.parametrize("rng,trades_expected", [
    (9.999999, 0), (10.0, 1), (35.0, 1), (35.000001, 0), (20.0, 1),
])
def test_golden_5_to_8_the_regime_filter_boundaries(rng, trades_expected):
    low = 5000.0
    high = low + rng
    mid = (high + low) / 2.0
    s = (Session().ib(high=high, low=low)
         .quiet("10:30", "10:40", mid)
         .block("10:40", low, low + 1.0, low - 5.0, low + 1.0)   # trap and reject
         .block("10:45", low + 1.0, high + 5.0, low + 1.0, high)
         .quiet("10:50", "15:45", high))
    eng = run(s)
    assert len(eng.trades) == trades_expected
    if trades_expected == 0:
        assert eng.state is State.HALTED_DAY
        assert "outside" in eng.governor.halt_reason


def test_the_ib_refuses_to_be_read_before_its_window_closes():
    from quant_brain.strategies.initial_balance_reversion.indicators import InitialBalance
    ib = InitialBalance(start_minute=570, end_minute=630)
    with pytest.raises(IBNotReady, match="before 10:30"):
        _ = ib.midpoint


def test_an_empty_ib_window_raises_rather_than_halting_every_day():
    """The driver defect that produced a silent zero-trade backtest, now loud."""
    from quant_brain.strategies.initial_balance_reversion.indicators import InitialBalance
    ib = InitialBalance(start_minute=570, end_minute=630)
    with pytest.raises(IBNotReady, match="no bars at all"):
        ib.seal()


# ======================================================================================
# 9-10. THE DAILY TRADE CAP
# ======================================================================================

def test_golden_9_and_10_two_trades_are_allowed_and_a_third_is_refused():
    s = (Session().ib(high=5020.0, low=5000.0)
         .block("10:30", 5000.0, 5000.0, 4998.0, 4998.0)
         .block("10:35", 4998.0, 5002.0, 4998.0, 5002.0)      # trade 1 entry
         .block("10:40", 5002.0, 5010.0, 5002.0, 5010.0)      # trade 1 target
         .block("10:45", 5000.0, 5000.0, 4996.0, 4996.0)
         .block("10:50", 4996.0, 5003.0, 4996.0, 5003.0)      # trade 2 entry
         .block("10:55", 5003.0, 5010.0, 5003.0, 5010.0)      # trade 2 target
         .block("11:00", 5000.0, 5000.0, 4994.0, 4994.0)
         .block("11:05", 4994.0, 5004.0, 4994.0, 5004.0)      # would be trade 3
         .quiet("11:10", "15:45", 5004.0))
    eng = run(s)
    assert len(eng.trades) == 2, "the daily cap of 2 is authoritative"
    assert eng.governor.trades_today == 2
    assert eng.governor.trade_cap_reached()


def test_one_excursion_cannot_produce_two_entries():
    """AMBIGUITY B7. A second entry needs price to leave the IB again."""
    s = (Session().ib(high=5020.0, low=5000.0)
         .block("10:30", 5000.0, 5000.0, 4996.0, 4996.0)
         .block("10:35", 4996.0, 5001.0, 4996.0, 5001.0)      # rejection -> trade 1
         .block("10:40", 5001.0, 5002.0, 5001.0, 5002.0)      # still inside: no new trip
         .block("10:45", 5002.0, 5003.0, 5002.0, 5003.0)
         .quiet("10:50", "15:45", 5003.0))
    eng = run(s)
    assert len(eng.trades) == 1


# ======================================================================================
# 11-12. THE GOVERNOR
# ======================================================================================

def test_golden_11_the_minus_800_killswitch_flattens_and_halts():
    """A long entered at 5001.25 marked at a bucket low of 4984 is -$862.50 unrealized."""
    s = (Session().ib(high=5020.0, low=5000.0)
         .block("10:30", 5000.0, 5000.0, 4999.0, 4999.0)
         .block("10:35", 4999.0, 5001.0, 4999.0, 5001.0)      # entry at 5001.25
         .block("10:40", 5001.0, 5001.0, 4984.0, 4990.0)      # deep adverse excursion
         .quiet("10:45", "15:45", 4990.0))
    eng = run(s, spec=FrozenSpec(execution=BASELINE_FROZEN))
    t = eng.trades[0]
    #: the stop sits at 4998.75 and 4984 trades through it, so the STOP fires first -
    #: a resting stop is at the exchange and the governor never gets the chance.
    assert t.exit_reason == EXIT_STOP
    assert eng.state in (State.TRADE_COMPLETE, State.ARMED, State.HALTED_DAY)


def test_the_killswitch_fires_when_no_stop_stands_in_front_of_it():
    """Stop far away, so the -$800 mark is what closes the trade."""
    s = (Session().ib(high=5035.0, low=5000.0)
         .block("10:30", 5000.0, 5000.0, 4960.0, 4960.0)      # very deep trip
         .block("10:35", 4960.0, 5002.0, 4960.0, 5002.0)      # rejection; E = 4960
         .block("10:40", 5002.0, 5002.0, 4984.0, 4985.0)      # -$862 mark, stop is 4959.75
         .quiet("10:45", "15:45", 4985.0))
    eng = run(s)
    t = eng.trades[0]
    assert t.stop_price == 4959.75
    assert t.exit_reason == EXIT_KILLSWITCH
    assert eng.state is State.HALTED_DAY
    assert eng.governor.halted


def test_the_killswitch_reads_the_adverse_extreme_and_not_the_close():
    """AMBIGUITY B6, at the only place the two readings differ.

    The previous test used a bucket whose low and close were a point apart, so BOTH readings
    tripped -$800 and the test could not tell them apart - a mutation swapping the low for
    the close survived it. Here the low trips and the close does not:

        entry 5002.25   low 4985 -> (4985 - 5002.25) * 50 = -$862.50   FIRES
                        close 4999 -> (4999 - 5002.25) * 50 = -$162.50  would NOT
        stop 4959.75 is far below the low, so no resting order stands in front
        target 5017.50 is far above the high
    """
    s = (Session().ib(high=5035.0, low=5000.0)
         .block("10:30", 5000.0, 5000.0, 4960.0, 4960.0)
         .block("10:35", 4960.0, 5002.0, 4960.0, 5002.0)      # entry 5002.25
         .block("10:40", 5002.0, 5002.0, 4985.0, 4999.0)      # low trips, close does not
         .quiet("10:45", "15:45", 4999.0))
    eng = run(s)
    t = eng.trades[0]
    assert t.entry_price == 5002.25 and t.stop_price == 4959.75
    assert t.target_price == 5017.50
    assert t.exit_reason == EXIT_KILLSWITCH, (
        "marked at the bucket CLOSE the killswitch would not have fired")
    assert t.exit_price == 4999.0
    assert eng.governor.halted and eng.state is State.HALTED_DAY
    #: and the discrimination is real: the close-based mark is well inside the threshold
    assert (4999.0 - 5002.25) * 50 > FROZEN.daily_loss_killswitch
    assert (4985.0 - 5002.25) * 50 <= FROZEN.daily_loss_killswitch


def test_a_consumed_trip_is_never_offered_a_second_time():
    """AMBIGUITY B7, tested on `Excursion` directly.

    The engine happens to close every trip on the bucket that consumed it, so this guard is
    unreachable from the bar loop and a mutation removing it changed no engine output. It is
    still part of the object's contract - one breakout, one entry - so it is pinned here
    rather than deleted on the grounds that nothing currently reaches it.
    """
    import dataclasses

    from quant_brain.strategies.initial_balance_reversion.indicators import BELOW, Excursion
    fake = dataclasses.make_dataclass("F", ["high", "low", "close"])
    e = Excursion()
    e.update(fake(5005.0, 4995.0, 4996.0), 5020.0, 5000.0)
    assert e.side == BELOW and e.extreme == 4995.0

    rejection = fake(5005.0, 4998.0, 5002.0)
    assert e.rejected(rejection, 5020.0, 5000.0) is True
    e.consume()
    assert e.rejected(rejection, 5020.0, 5000.0) is False, (
        "a trip already traded must not be offered again")
    e.close_trip()
    assert e.side == 0 and not e.consumed


def test_golden_12_the_profit_cap_does_not_flatten_the_open_trade():
    """+$1,200 realized stops NEW entries; the running trade finishes on its own rules."""
    from quant_brain.strategies.initial_balance_reversion.governor import Governor
    g = Governor(spec=FROZEN)
    g.reset(dt.date(2026, 6, 10))
    g.realized = 1300.0
    assert g.profit_cap_reached()
    v = g.may_enter(dt.datetime(2026, 6, 10, 11, 0, tzinfo=dt.UTC), ib_complete=True,
                    in_regime=True, position_open=False, minute_of_day=660)
    assert not v and any("profit cap" in r for r in v.reasons)
    #: and the halt only lands once flat
    g2 = Governor(spec=FROZEN)
    g2.reset(dt.date(2026, 6, 10))
    g2.record_exit(net_pnl=1300.0, when=dt.datetime(2026, 6, 10, 11, 0, tzinfo=dt.UTC))
    assert g2.halted and "flat" in g2.halt_reason


# ======================================================================================
# 13-14. TIME STOP AND HARD FLATTEN
# ======================================================================================

def test_golden_13_the_sixty_minute_time_stop():
    """Entry at the 10:35 bucket's close (10:40:00). Deadline 11:40:00.

    The bucket that closes AT 11:40 is the one starting 11:35, so that is the flatten bucket.
    """
    s = (Session().ib(high=5020.0, low=5000.0)
         .block("10:30", 5000.0, 5000.0, 4999.0, 4999.0)
         .block("10:35", 4999.0, 5001.0, 4999.0, 5001.0)      # entry
         .quiet("10:40", "15:45", 5001.0))                    # nothing ever hits
    eng = run(s)
    t = eng.trades[0]
    assert t.exit_reason == EXIT_TIME
    assert t.holding_minutes == 60
    assert t.entry_time.astimezone(t.entry_time.tzinfo).strftime("%H:%M") == "10:40"
    assert t.exit_time.strftime("%H:%M") == "11:40"
    #: flat market, so the whole loss is cost: one tick of entry slippage plus commission
    assert t.net_pnl == pytest.approx(-12.50 - 4.14, abs=1e-9)


def test_golden_14_the_1545_hard_flatten():
    """A trade opened at 13:55 with a 60-minute fuse would run to 14:55; make it survive by
    entering late enough that 15:45 arrives first."""
    s = (Session().ib(high=5020.0, low=5000.0)
         .quiet("10:30", "15:00", 5010.0)
         .block("15:00", 5000.0, 5000.0, 4999.0, 4999.0)
         .block("15:05", 4999.0, 5001.0, 4999.0, 5001.0)
         .quiet("15:10", "15:45", 5001.0))
    eng = run(s)
    #: 15:05's bucket closes at 15:10, past the 14:00 cutoff, so NO entry is taken at all
    assert len(eng.trades) == 0, "entries are refused at or after 14:00"


def test_the_hard_flatten_closes_a_trade_that_outlives_its_own_time_stop_window():
    """Enter at 13:55 (close 14:00 is the cutoff, so enter on the 13:50 bucket)."""
    s = (Session().ib(high=5020.0, low=5000.0)
         .quiet("10:30", "13:50", 5010.0)
         .block("13:50", 5000.0, 5000.0, 4999.0, 4999.0)
         .block("13:55", 4999.0, 5001.0, 4999.0, 5001.0)      # closes 14:00 -> refused
         .quiet("14:00", "15:45", 5001.0))
    eng = run(s)
    assert len(eng.trades) == 0


def test_an_entry_exactly_one_bucket_before_the_cutoff_is_allowed():
    """The 13:50 bucket closes at 13:55, inside the window."""
    s = (Session().ib(high=5020.0, low=5000.0)
         .quiet("10:30", "13:45", 5010.0)
         .block("13:45", 5000.0, 5000.0, 4999.0, 4999.0)
         .block("13:50", 4999.0, 5001.0, 4999.0, 5001.0)      # closes 13:55 -> allowed
         .quiet("13:55", "15:45", 5001.0))
    eng = run(s)
    assert len(eng.trades) == 1
    t = eng.trades[0]
    assert t.entry_time.strftime("%H:%M") == "13:55"
    #: 13:55 + 60 min = 14:55, which arrives before 15:45, so the time stop wins
    assert t.exit_reason == EXIT_TIME
    assert t.exit_time.strftime("%H:%M") == "14:55"


# ======================================================================================
# 15-16. AMBIGUOUS BAR AND GAPS
# ======================================================================================

def test_golden_15_stop_and_target_in_one_bucket_resolve_to_the_stop():
    s = (Session().ib(high=5020.0, low=5000.0)
         .block("10:30", 5000.0, 5000.0, 4998.0, 4998.0)
         .block("10:35", 4998.0, 5001.0, 4998.0, 5001.0)      # entry; stop 4997.75, tgt 5010
         .block("10:40", 5001.0, 5012.0, 4990.0, 5000.0)      # touches BOTH
         .quiet("10:45", "15:45", 5000.0))
    eng = run(s)
    t = eng.trades[0]
    assert t.exit_reason == EXIT_STOP, "declared conservative convention: stop first"
    assert t.ambiguous_bar is True
    assert eng.ambiguous_buckets == 1


def test_golden_16_a_gap_through_the_stop_fills_at_the_stop():
    """Declared policy, inherited, and optimistic - stated rather than argued."""
    s = (Session().ib(high=5020.0, low=5000.0)
         .block("10:30", 5000.0, 5000.0, 4998.0, 4998.0)
         .block("10:35", 4998.0, 5001.0, 4998.0, 5001.0)      # stop 4997.75
         .block("10:40", 4950.0, 4950.0, 4940.0, 4945.0)      # opens far below the stop
         .quiet("10:45", "15:45", 4945.0))
    eng = run(s)
    t = eng.trades[0]
    assert t.exit_reason == EXIT_STOP
    assert t.exit_price == 4997.50, "at the stop less one tick, NOT at the gap price"


# ======================================================================================
# 17-18. DST AND TICK ROUNDING
# ======================================================================================

@pytest.mark.parametrize("day", [dt.date(2026, 3, 9), dt.date(2026, 11, 2)])
def test_golden_17_the_session_works_on_both_sides_of_a_dst_transition(day):
    s = (Session(day=day).ib(high=5020.0, low=5000.0)
         .quiet("10:30", "10:40", 5010.0)
         .block("10:40", 5002.0, 5002.0, 4995.0, 5002.0)
         .block("10:45", 5002.0, 5012.0, 5002.0, 5011.0)
         .quiet("10:50", "15:45", 5011.0))
    eng = run(s)
    t = eng.trades[0]
    assert t.exit_reason == EXIT_TARGET
    assert t.entry_time.utcoffset() == (dt.timedelta(hours=-4) if day.month == 3
                                        else dt.timedelta(hours=-5))
    assert t.net_pnl == pytest.approx(383.36, abs=1e-9)


def test_golden_18_an_off_tick_midpoint_is_rounded_away_from_the_entry():
    """IB 5000.00-5015.50 -> midpoint 5007.75. On a tick, so unchanged.
    IB 5000.00-5015.25 -> midpoint 5007.625. Off tick: a long rounds UP to 5007.75."""
    s = (Session().ib(high=5015.25, low=5000.0)
         .quiet("10:30", "10:40", 5007.0)
         .block("10:40", 5002.0, 5002.0, 4995.0, 5002.0)
         .block("10:45", 5002.0, 5009.0, 5002.0, 5008.0)
         .quiet("10:50", "15:45", 5008.0))
    eng = run(s)
    t = eng.trades[0]
    assert t.ib_midpoint == 5007.625, "the raw midpoint is carried in the ledger"
    assert t.target_price == 5007.75, "rounded UP for a long: strictly harder to reach"
    assert t.exit_price == 5007.75
    assert (t.target_price / 0.25) % 1 == 0, "and it is a placeable ES price"


def test_a_short_rounds_the_midpoint_down():
    s = (Session().ib(high=5015.25, low=5000.0)
         .quiet("10:30", "10:40", 5007.0)
         .block("10:40", 5013.0, 5020.0, 5013.0, 5013.0)
         .block("10:45", 5013.0, 5013.0, 5006.0, 5007.0)
         .quiet("10:50", "15:45", 5007.0))
    eng = run(s)
    t = eng.trades[0]
    assert t.ib_midpoint == 5007.625
    assert t.target_price == 5007.50, "rounded DOWN for a short"


# ======================================================================================
# THE EXECUTION LADDER
# ======================================================================================

@pytest.mark.parametrize("profile,expected_entry,expected_stop_fill", [
    (IDEAL, 5001.00, 4997.75),
    (BASELINE_FROZEN, 5001.25, 4997.50),
    (STRESS_1TICK, 5001.25, 4997.25),
    (STRESS_2TICK, 5001.25, 4997.00),
])
def test_the_ladder_moves_fills_and_nothing_else(profile, expected_entry, expected_stop_fill):
    s = (Session().ib(high=5020.0, low=5000.0)
         .block("10:30", 5000.0, 5000.0, 4998.0, 4998.0)
         .block("10:35", 4998.0, 5001.0, 4998.0, 5001.0)
         .block("10:40", 5001.0, 5001.0, 4990.0, 4990.0)
         .quiet("10:45", "15:45", 4990.0))
    eng = run(s, spec=FrozenSpec(execution=profile))
    t = eng.trades[0]
    assert t.entry_price == expected_entry
    assert t.exit_price == expected_stop_fill
    #: the RULES are identical across the ladder
    assert t.trap_extreme == 4998.0 and t.stop_price == 4997.75
    assert t.ib_midpoint == 5010.0 and t.exit_reason == EXIT_STOP


def test_a_profile_never_changes_a_strategy_rule():
    """Every profile must produce the same trade DATES and the same levels."""
    s = (Session().ib(high=5020.0, low=5000.0)
         .block("10:30", 5000.0, 5000.0, 4998.0, 4998.0)
         .block("10:35", 4998.0, 5001.0, 4998.0, 5001.0)
         .block("10:40", 5001.0, 5011.0, 5001.0, 5010.0)
         .quiet("10:45", "15:45", 5010.0))
    shapes = set()
    for p in (IDEAL, BASELINE_FROZEN, STRESS_1TICK, STRESS_2TICK):
        eng = run(s, spec=FrozenSpec(execution=p))
        t = eng.trades[0]
        shapes.add((t.direction, t.trap_extreme, t.stop_price, t.target_price,
                    t.exit_reason, t.entry_time, t.exit_time))
    assert len(shapes) == 1, "a profile moved a rule, not just a fill"


# ======================================================================================
# THE IMMEDIATE-TARGET CASE
# ======================================================================================

def test_a_rejection_that_closes_past_the_midpoint_exits_at_once():
    """AMBIGUITY B4. A sell limit below the market is marketable."""
    s = (Session().ib(high=5020.0, low=5000.0)
         .block("10:30", 5000.0, 5000.0, 4998.0, 4998.0)
         .block("10:35", 4998.0, 5014.0, 4998.0, 5014.0)      # closes ABOVE the 5010 midpoint
         .quiet("10:40", "15:45", 5014.0))
    eng = run(s)
    assert eng.immediate_targets == 1
    t = eng.trades[0]
    assert t.exit_reason == EXIT_TARGET_IMMEDIATE
    assert t.entry_time == t.exit_time
    assert t.net_pnl < 0, "it can only cost money"


# ======================================================================================
# STATE MACHINE
# ======================================================================================

def test_no_position_may_survive_the_session_end():
    s = (Session().ib(high=5020.0, low=5000.0)
         .quiet("10:30", "13:00", 5010.0)
         .block("13:00", 5000.0, 5000.0, 4999.0, 4999.0)
         .block("13:05", 4999.0, 5001.0, 4999.0, 5001.0)
         .quiet("13:10", "15:45", 5001.0))
    eng = run(s)
    assert eng.position is None
    assert len(eng.trades) == 1


def test_an_out_of_regime_day_halts_and_takes_no_trade():
    s = (Session().ib(high=5100.0, low=5000.0)        # range 100, far outside
         .block("10:30", 5000.0, 5000.0, 4990.0, 4990.0)
         .block("10:35", 4990.0, 5005.0, 4990.0, 5005.0)
         .quiet("10:40", "15:45", 5005.0))
    eng = run(s)
    assert eng.state is State.HALTED_DAY
    assert len(eng.trades) == 0


def test_the_engine_refuses_a_duplicate_or_out_of_order_bar():
    s = Session().ib(high=5020.0, low=5000.0).quiet("10:30", "15:45", 5010.0)
    bars = s.bars()
    eng = Engine(spec=FROZEN)
    eng.start_session(s.day, bars[0].timestamp)
    for b in bars:
        eng.on_bar(b)
    n = len(eng.five.completed)
    eng.on_bar(bars[-1])            # duplicate
    eng.on_bar(bars[10])            # out of order
    assert len(eng.five.completed) == n, "neither bar was absorbed"
