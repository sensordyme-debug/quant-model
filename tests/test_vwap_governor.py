"""GOLDEN: the V1.0.0_Frozen governor, the cost model, the accounting and NQ/MNQ equivalence.

The governor is tested twice over: as a unit, where every boundary the brief names can be hit
exactly, and through the engine, where the same rule has to fire from real bars with a real
position open. A limit that passes the first and not the second is a limit nobody enforces.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from conftest_vwap import (  # noqa: E402
    LEVEL,
    QUIET_VOLUME,
    Scenario,
    et_at,
    flat_bar,
    long_scenario,
)

from quant_brain.strategies.vwap_pullback.engine import (  # noqa: E402
    EXIT_KILLSWITCH,
    EXIT_STOP,
    EXIT_TARGET,
    Engine,
    State,
)
from quant_brain.strategies.vwap_pullback.governor import (  # noqa: E402
    COOLDOWN,
    HALTED,
    PROFIT_CAP,
    TRADE_CAP,
    Governor,
)
from quant_brain.strategies.vwap_pullback.indicators import Bar  # noqa: E402
from quant_brain.strategies.vwap_pullback.spec import (  # noqa: E402
    AMBIGUITIES,
    CONFLICTS,
    FROZEN,
    FROZEN_MNQ,
    VERSION,
    FrozenSpec,
)

DAY = dt.date(2026, 1, 6)
NOON = et_at(DAY, "12:00")
PV = FROZEN.point_value            # 20.0
TICK = FROZEN.tick                 # 0.25


def gov(**kw) -> Governor:
    g = Governor(spec=FROZEN, **kw)
    g.day = DAY
    return g


# =====================================================================================
# THE FROZEN CONSTANTS ARE WHAT THE OWNER WROTE  (brief §31)
# =====================================================================================

def test_every_frozen_parameter_is_the_owners_number():
    """Asserted against literals here, so an edit to spec.py fails rather than redefines."""
    s = FROZEN
    assert s.version == "V1.0.0_Frozen"
    assert s.session_anchor == (18, 0)
    assert s.monitor_start == (9, 45)
    assert s.last_entry == (15, 30)
    assert s.hard_flatten == (15, 45)
    assert s.context_max_distance == 6.0
    assert s.long_zone == (-8.0, 2.0)
    assert s.short_zone == (-2.0, 8.0)
    assert s.invalidation_distance == 15.0
    assert s.atr_period == 14
    assert s.atr_minimum == 8.0
    assert s.volume_sma_period == 10
    assert s.volume_multiple == 1.2
    assert s.stop_points == 15.0
    assert s.target_points == 30.0
    assert s.breakeven_trigger == 15.0
    assert s.breakeven_offset == 0.25
    assert s.stall_mfe == 25.0
    assert s.stall_window == 3
    assert s.stall_target == 20.0
    assert s.daily_loss_killswitch == -800.0
    assert s.daily_profit_cap == 1200.0
    assert s.max_trades_per_day == 4
    assert s.consecutive_losses_for_cooldown == 2
    assert s.cooldown_minutes == 45
    assert s.instrument == "NQ" and s.contracts == 1
    assert s.commission_round_turn == 4.50
    assert s.slippage_ticks_entry == 1.0 and s.slippage_ticks_stop == 1.0


def test_the_mnq_override_is_ten_contracts_at_the_same_exposure():
    assert FROZEN_MNQ.instrument == "MNQ" and FROZEN_MNQ.contracts == 10
    assert FROZEN_MNQ.point_value == pytest.approx(20.0)
    assert FROZEN.point_value == pytest.approx(20.0)


# =====================================================================================
# CONTRACT MATH  (brief §13, §25)
# =====================================================================================

@pytest.mark.parametrize("points,dollars", [(1.0, 20.0), (15.0, 300.0), (30.0, 600.0),
                                            (25.0, 500.0), (0.25, 5.0)])
def test_the_nq_point_and_tick_arithmetic_is_the_frozen_one(points, dollars):
    assert points * FROZEN.point_value == pytest.approx(dollars)


@pytest.mark.parametrize("points,dollars", [(1.0, 20.0), (15.0, 300.0), (30.0, 600.0),
                                            (25.0, 500.0), (0.25, 5.0)])
def test_ten_micros_give_exactly_the_same_dollars_as_one_mini(points, dollars):
    assert points * FROZEN_MNQ.point_value == pytest.approx(dollars)


def test_one_tick_is_five_dollars_on_both_instruments():
    assert FROZEN.tick_value == pytest.approx(5.0)
    assert FROZEN_MNQ.tick_value == pytest.approx(5.0)
    assert FROZEN.tick == FROZEN_MNQ.tick == 0.25


def test_the_frozen_commission_differs_from_the_repositorys_cited_rate_on_purpose():
    """CONFLICT C8, pinned. The frozen $4.50 is used; the repository's $3.78 is not."""
    from quant_brain.markets.futures_cme import instruments as inst
    assert inst.get("NQ").commission_round_turn == pytest.approx(3.78)
    assert FROZEN.commission_round_turn == pytest.approx(4.50)
    assert FROZEN.commission_round_turn > inst.get("NQ").commission_round_turn


# =====================================================================================
# GOLDEN ACCOUNTING  (brief §24)
# =====================================================================================

def test_the_briefs_hand_worked_bracket_arithmetic():
    """NQ long, 15-point stop and 30-point target, before any friction.

        stop   -15 x $20 = -$300
        target +30 x $20 = +$600
    """
    assert -FROZEN.stop_points * PV == pytest.approx(-300.0)
    assert FROZEN.target_points * PV == pytest.approx(600.0)


def test_a_stop_out_books_the_hand_computed_dollars():
    """Entry 20,001.75 (close 20,001.50 + one tick). Stop 19,986.75, filled a tick worse.

        gross     (19,986.75 - 20,001.50) x 20 = -14.75 x 20 = -$295.00
        slippage  (0.25 entry + 0.25 stop) x 20                = -$ 10.00
        commission                                              = -$  4.50
        net                                                     = -$309.50
    """
    sc = long_scenario()
    e = Engine()
    e.run(sc.bars)
    f = e.position.fill_price
    e.run([sc.then(minutes_after=1, high=f, low=f - 20.0, close=f - 18.0)])
    t = e.trades[0]
    assert t.exit_reason == EXIT_STOP
    assert t.entry_price == pytest.approx(20_001.75)
    assert t.exit_price == pytest.approx(19_986.50)
    assert t.gross_pnl == pytest.approx(-295.00)
    assert t.slippage == pytest.approx(10.00)
    assert t.commission_and_spread == pytest.approx(4.50)
    assert t.net_pnl == pytest.approx(-309.50)


def test_a_target_fill_books_the_hand_computed_dollars():
    """Target 20,031.75, a limit fill with no slippage.

        gross     (20,031.75 - 20,001.50) x 20 = 30.25 x 20 = +$605.00
        slippage  0.25 entry only                            = -$  5.00
        commission                                           = -$  4.50
        net                                                  = +$595.50
    """
    sc = long_scenario()
    e = Engine()
    e.run(sc.bars)
    f = e.position.fill_price
    e.run([sc.then(minutes_after=1, high=f + 31.0, low=f + 1.0, close=f + 30.0)])
    t = e.trades[0]
    assert t.exit_reason == EXIT_TARGET
    assert t.exit_price == pytest.approx(20_031.75)
    assert t.gross_pnl == pytest.approx(605.00)
    assert t.slippage == pytest.approx(5.00)
    assert t.net_pnl == pytest.approx(595.50)


def test_the_accounting_identity_holds_on_every_trade():
    """net == gross - slippage - commission, AND net == fill-to-fill less commission.

    Two independent routes to the same number. If slippage were double-counted - once inside
    the fill and once as a line - the two would disagree by exactly the slippage.
    """
    for offset, label in ((-20.0, "stop"), (+31.0, "target")):
        sc = long_scenario()
        e = Engine()
        e.run(sc.bars)
        f = e.position.fill_price
        if offset < 0:
            e.run([sc.then(minutes_after=1, high=f, low=f + offset, close=f + offset + 2)])
        else:
            e.run([sc.then(minutes_after=1, high=f + offset, low=f + 1.0,
                           close=f + offset - 1)])
        t = e.trades[0]
        assert t.net_pnl == pytest.approx(
            t.gross_pnl - t.slippage - t.commission_and_spread), label
        from_fills = ((t.exit_price - t.entry_price) * t.direction * PV
                      - FROZEN.commission_round_turn)
        assert t.net_pnl == pytest.approx(from_fills), label


def test_ten_micros_and_one_mini_book_the_same_gross_on_the_same_path():
    """brief §25. Same prices, same gross, same slippage; only the commission differs."""
    out = {}
    for spec in (FROZEN, FROZEN_MNQ):
        sc = long_scenario()
        e = Engine(spec=spec)
        e.run(sc.bars)
        f = e.position.fill_price
        e.run([sc.then(minutes_after=1, high=f + 31.0, low=f + 1.0, close=f + 30.0)])
        out[spec.instrument] = e.trades[0]
    nq, mnq = out["NQ"], out["MNQ"]
    assert nq.entry_price == pytest.approx(mnq.entry_price)
    assert nq.exit_price == pytest.approx(mnq.exit_price)
    assert nq.gross_pnl == pytest.approx(mnq.gross_pnl) == pytest.approx(605.00)
    assert nq.slippage == pytest.approx(mnq.slippage) == pytest.approx(5.00)
    assert mnq.quantity == 10 and nq.quantity == 1
    # the ONLY difference, and it is the one the frozen spec leaves unstated (AMBIGUITY A11)
    assert mnq.net_pnl == pytest.approx(nq.net_pnl - (12.20 - 4.50))


def test_the_excursions_are_recorded_in_dollars_from_the_fill():
    """MFE/MAE are BAR-DERIVED, so they are upper bounds on what the trade experienced.

    The exit filled at the +30 target, but the bar's high reached +31 and that is what MFE
    records: $620, not $600. This is the same basis `strategy_report.MAE_BASIS` declares for
    the certified engine - a trade entered part-way through a bar did not see all of that
    bar's range - and it is asserted here so the convention cannot drift between the two.
    """
    sc = long_scenario()
    e = Engine()
    e.run(sc.bars)
    f = e.position.fill_price
    e.run([sc.then(minutes_after=1, high=f + 10.0, low=f - 4.0, close=f + 5.0),
           sc.then(minutes_after=2, high=f + 31.0, low=f + 1.0, close=f + 30.0)])
    t = e.trades[0]
    assert t.mfe == pytest.approx(31.0 * PV)     # the bar's HIGH, not the fill
    assert t.mae == pytest.approx(-4.0 * PV)
    assert t.mfe > (t.exit_price - t.entry_price) * PV, "MFE is not an upper bound"


# =====================================================================================
# THE KILLSWITCH  (brief §14)
# =====================================================================================

@pytest.mark.parametrize("realized,unrealized,fires", [
    (-799.99, 0.0, False),
    (-800.00, 0.0, True),
    (-800.01, 0.0, True),
    (-500.0, -300.0, True),        # the brief's own example: the halves add up
    (-799.0, 0.0, False),
    (0.0, -800.0, True),           # unrealised alone
    (0.0, -799.99, False),
    (-400.0, -399.99, False),
    (+200.0, -1000.0, True),
])
def test_the_killswitch_is_mark_to_market_and_closed_at_minus_eight_hundred(
        realized, unrealized, fires):
    g = gov()
    g.realized = realized
    assert g.killswitch_breached(unrealized) is fires


def test_a_realized_only_killswitch_would_miss_the_open_half():
    """The defect the MTM requirement exists to prevent, demonstrated.

    Realized -$500 with -$300 open is -$800 of damage. A limit reading only the booked half
    sees -$500 and does nothing.
    """
    g = gov()
    g.realized = -500.0
    assert g.killswitch_breached(-300.0) is True
    assert g.killswitch_breached(0.0) is False


def test_the_killswitch_fires_from_the_engine_with_a_position_open():
    """Two stop-outs, a cooldown, then a third position whose OPEN loss tips it over.

        two stops   2 x -$309.50  = -$619.00 realized
        open loss   -10 points    = -$200.00 unrealised
        total                       -$819.00  <=  -$800
    """
    sc = Scenario().warmup().arm_long(trigger_at="10:00")
    e = Engine()
    e.run(sc.bars)
    f = e.position.fill_price
    e.run([sc.then(minutes_after=1, high=f, low=f - 20.0, close=f - 18.0)])

    sc.again_long(trigger_at="10:20")
    e.run(sc.bars[len(e.outcomes):])
    f2 = e.position.fill_price
    e.run([sc.then(minutes_after=1, high=f2, low=f2 - 20.0, close=f2 - 18.0)])
    assert e.governor.realized == pytest.approx(-619.00)
    assert e.state is State.COOLDOWN

    # past the 45-minute cooldown, take a third position and let it sit 10 points offside
    sc.again_long(trigger_at="11:20")
    e.run(sc.bars[len(e.outcomes):])
    assert e.position is not None, "the third entry was refused"
    f3 = e.position.fill_price
    e.run([sc.then(minutes_after=1, high=f3, low=f3 - 10.0, close=f3 - 9.0)])

    assert e.trades[-1].exit_reason == EXIT_KILLSWITCH
    assert e.state is State.HALTED_DAY
    assert e.governor.halted


def test_a_halt_flattens_cancels_and_blocks_everything_until_eighteen_hundred():
    e = Engine()
    sc = Scenario().warmup().pad_until("09:44")
    e.run(sc.bars)
    e.governor.halt(et_at(DAY, "10:00"), "test halt")
    e.state = State.HALTED_DAY
    verdict = e.governor.may_enter(et_at(DAY, "11:00"), position_open=False)
    assert not verdict and HALTED in verdict.reasons
    # still halted at 17:59, released at 18:00
    e.on_bar(flat_bar(et_at(DAY, "17:59"), level=LEVEL, volume=QUIET_VOLUME))
    assert e.state is State.HALTED_DAY
    e.on_bar(flat_bar(et_at(DAY, "18:00"), level=LEVEL, volume=QUIET_VOLUME))
    assert e.state is State.FLAT_MONITORING and not e.governor.halted


def test_the_two_mtm_readings_are_both_implemented_and_genuinely_differ():
    """AMBIGUITY A2: a bar whose LOW breaches but whose CLOSE does not."""
    intrabar = Engine(spec=FrozenSpec(governor_mtm_basis="intrabar"))
    on_close = Engine(spec=FrozenSpec(governor_mtm_basis="close"))
    outs = []
    for e in (intrabar, on_close):
        sc = long_scenario()
        e.run(sc.bars)
        e.governor.realized = -700.0
        f = e.position.fill_price
        # low is -10 points (-$200 -> -$900 total); close is -1 point (-$720 total)
        e.run([sc.then(minutes_after=1, high=f, low=f - 10.0, close=f - 1.0)])
        outs.append(e.governor.halted)
    assert outs == [True, False], (
        "the two mark-to-market readings did not differ on a bar built to separate them")


# =====================================================================================
# THE PROFIT CAP  (brief §15)
# =====================================================================================

@pytest.mark.parametrize("realized,allowed", [(1199.99, True), (1200.00, False),
                                              (1200.01, False)])
def test_the_profit_cap_boundary(realized, allowed):
    g = gov()
    g.realized = realized
    v = g.may_enter(NOON, position_open=False)
    assert v.allowed is allowed
    if not allowed:
        assert PROFIT_CAP in v.reasons


def test_the_profit_cap_blocks_entries_and_does_not_flatten_an_open_position():
    """The cap is an entry gate. An open trade keeps its stop, its target and its rules."""
    sc = long_scenario()
    e = Engine()
    e.run(sc.bars)
    e.governor.realized = 5_000.0                       # far past the cap
    f = e.position.fill_price
    e.run([sc.then(minutes_after=1, high=f + 16.0, low=f - 1.0, close=f + 5.0)])
    assert e.position is not None, "the profit cap flattened an open position"
    assert e.outcomes[-1].breakeven, "break-even stopped working past the cap"
    e.run([sc.then(minutes_after=2, high=f + 31.0, low=f + 1.0, close=f + 30.0)])
    assert e.trades[-1].exit_reason == EXIT_TARGET, "the target stopped working past the cap"


def test_no_new_entry_is_taken_once_the_cap_is_reached():
    sc = Scenario().warmup().arm_long(trigger_at="10:00")
    e = Engine()
    e.run(sc.bars)
    f = e.position.fill_price
    e.run([sc.then(minutes_after=1, high=f + 31.0, low=f + 1.0, close=f + 30.0)])
    e.governor.realized = FROZEN.daily_profit_cap        # exactly at the cap
    sc.again_long(trigger_at="10:30")
    e.run(sc.bars[len(e.outcomes):])
    assert e.position is None, "an entry was taken at the profit cap"


# =====================================================================================
# THE TRADE CAP  (brief §16)
# =====================================================================================

@pytest.mark.parametrize("taken,allowed", [(0, True), (1, True), (2, True), (3, True),
                                           (4, False), (5, False)])
def test_the_daily_trade_cap_boundary(taken, allowed):
    g = gov()
    g.trades_today = taken
    v = g.may_enter(NOON, position_open=False)
    assert v.allowed is allowed
    if not allowed:
        assert TRADE_CAP in v.reasons


def test_a_trade_is_counted_once_at_entry_and_not_again_at_exit():
    """A round turn is ONE trade. Counting the exit too would halve the daily allowance."""
    sc = long_scenario()
    e = Engine()
    e.run(sc.bars)
    assert e.governor.trades_today == 1
    f = e.position.fill_price
    e.run([sc.then(minutes_after=1, high=f + 31.0, low=f + 1.0, close=f + 30.0)])
    assert e.governor.trades_today == 1, "the exit was counted as a second trade"
    assert len(e.trades) == 1


def test_the_engine_refuses_a_perfect_trigger_once_the_cap_is_reached():
    sc = Scenario().warmup().arm_long(trigger_at="10:00")
    e = Engine()
    e.run(sc.bars)
    f = e.position.fill_price
    e.run([sc.then(minutes_after=1, high=f + 31.0, low=f + 1.0, close=f + 30.0)])
    e.governor.trades_today = FROZEN.max_trades_per_day
    sc.again_long(trigger_at="10:30")
    e.run(sc.bars[len(e.outcomes):])
    assert len(e.trades) == 1 and e.position is None


# =====================================================================================
# THE CONSECUTIVE-LOSS BREAKER  (brief §17)
# =====================================================================================

def test_one_loss_does_not_start_a_cooldown_and_two_do():
    g = gov()
    g.record_exit(net_pnl=-100.0, when=NOON)
    assert g.cooldown_until is None
    assert g.may_enter(NOON, position_open=False).allowed
    g.record_exit(net_pnl=-100.0, when=NOON)
    assert g.cooldown_until == NOON + dt.timedelta(minutes=45)
    assert COOLDOWN in g.may_enter(NOON, position_open=False).reasons


@pytest.mark.parametrize("seconds,blocked", [(44 * 60 + 59, True), (45 * 60, False),
                                             (45 * 60 + 1, False)])
def test_the_cooldown_expires_at_exactly_forty_five_minutes(seconds, blocked):
    g = gov()
    g.record_exit(net_pnl=-100.0, when=NOON)
    g.record_exit(net_pnl=-100.0, when=NOON)
    when = NOON + dt.timedelta(seconds=seconds)
    assert (COOLDOWN in g.may_enter(when, position_open=False).reasons) is blocked


def test_a_winning_trade_resets_the_consecutive_loss_count():
    g = gov()
    g.record_exit(net_pnl=-100.0, when=NOON)
    g.record_exit(net_pnl=+50.0, when=NOON)
    assert g.consecutive_losses == 0
    g.record_exit(net_pnl=-100.0, when=NOON)
    assert g.cooldown_until is None, "the streak survived a winning trade"


def test_a_scratch_neither_increments_nor_resets_the_streak():
    """The brief is explicit: do not reset merely because a position closed flat."""
    g = gov()
    g.record_exit(net_pnl=-100.0, when=NOON)
    assert g.consecutive_losses == 1
    g.record_exit(net_pnl=0.0, when=NOON)
    assert g.consecutive_losses == 1, "a scratch reset the streak"
    assert g.cooldown_until is None, "a scratch counted as a loss"


def test_a_loss_is_measured_NET_of_costs():
    """AMBIGUITY A8. A trade that is gross-positive but net-negative cost money."""
    g = gov()
    g.record_exit(net_pnl=-0.01, when=NOON)
    assert g.consecutive_losses == 1


def test_the_engine_enters_cooldown_after_two_losses_and_leaves_it_on_time():
    sc = Scenario().warmup().arm_long(trigger_at="10:00")
    e = Engine()
    e.run(sc.bars)
    f = e.position.fill_price
    e.run([sc.then(minutes_after=1, high=f, low=f - 20.0, close=f - 18.0)])
    sc.again_long(trigger_at="10:20")
    e.run(sc.bars[len(e.outcomes):])
    f2 = e.position.fill_price
    e.run([sc.then(minutes_after=1, high=f2, low=f2 - 20.0, close=f2 - 18.0)])
    assert e.state is State.COOLDOWN
    assert e.governor.cooldown_until == et_at(DAY, "10:21") + dt.timedelta(minutes=45)

    # a perfect trigger inside the cooldown is refused
    sc.again_long(trigger_at="10:40")
    e.run(sc.bars[len(e.outcomes):])
    assert e.position is None and len(e.trades) == 2

    # and permitted after it
    sc.again_long(trigger_at="11:10")
    e.run(sc.bars[len(e.outcomes):])
    assert e.position is not None, "the cooldown never released"


# =====================================================================================
# THE DAY  (brief §4, §18)
# =====================================================================================

def test_the_daily_counters_roll_at_eighteen_hundred_and_not_at_midnight():
    g = Governor(spec=FROZEN)
    g.observe(et_at(DAY, "10:00"))
    g.realized, g.trades_today = -500.0, 3
    assert not g.observe(et_at(DAY, "17:59")), "the day rolled early"
    assert g.trades_today == 3
    assert g.observe(et_at(DAY, "18:00")), "the day did not roll at the anchor"
    assert g.realized == 0.0 and g.trades_today == 0 and not g.halted


@pytest.mark.parametrize("hhmm,allowed", [("09:44", False), ("09:45", True),
                                          ("12:00", True), ("15:29", True),
                                          ("15:30", True), ("15:31", False),
                                          ("15:45", False), ("16:30", False)])
def test_the_governor_entry_window_boundaries(hhmm, allowed):
    """AMBIGUITY A3 at the governor level, not only through the engine.

    The engine test covers the same boundary end to end; this one covers it where the rule
    actually lives, because a mutation to `in_entry_window` named the governor suite and
    survived - the suite had no direct test of it.
    """
    g = gov()
    assert g.may_enter(et_at(DAY, hhmm), position_open=False).allowed is allowed


def test_the_last_entry_bar_is_inclusive_and_the_next_minute_is_not():
    g = gov()
    ok_at_cutoff, reasons_at_cutoff = g.in_entry_window(et_at(DAY, "15:30"))
    ok_after, reasons_after = g.in_entry_window(et_at(DAY, "15:31"))
    assert ok_at_cutoff and not reasons_at_cutoff
    assert not ok_after and "past the last-entry time" in reasons_after


@pytest.mark.parametrize("hhmm,flatten", [("15:44", False), ("15:45", True),
                                          ("15:46", True)])
def test_the_hard_flatten_boundary(hhmm, flatten):
    g = gov()
    assert g.must_hard_flatten(et_at(DAY, hhmm)) is flatten


def test_the_frozen_flatten_precedes_topsteps_mandatory_flat():
    """CONFLICT C5: 15:45 is the owner's rule and is 25 minutes earlier than the venue's."""
    assert FROZEN.minute_of("hard_flatten") == 15 * 60 + 45
    assert FROZEN.minute_of("hard_flatten") < 16 * 60 + 10


def test_the_windows_hold_their_wall_clock_time_on_a_dst_transition_day():
    g = Governor(spec=FROZEN)
    for day in (dt.date(2026, 3, 8), dt.date(2026, 11, 1)):
        assert g.must_hard_flatten(et_at(day, "15:45"))
        assert not g.must_hard_flatten(et_at(day, "15:44"))
        ok, _ = g.in_entry_window(et_at(day, "09:45"))
        assert ok
        ok, _ = g.in_entry_window(et_at(day, "09:44"))
        assert not ok


# =====================================================================================
# PROVENANCE  (brief §32)
# =====================================================================================

def test_the_spec_is_hashed_and_a_changed_number_changes_the_hash():
    base = FROZEN.spec_hash
    assert len(base) == 16
    assert FrozenSpec().spec_hash == base, "the hash is not stable across construction"
    assert FrozenSpec(stop_points=14.99).spec_hash != base
    assert FrozenSpec(atr_method="sma").spec_hash != base
    assert FrozenSpec(governor_mtm_basis="close").spec_hash != base
    assert FROZEN_MNQ.spec_hash != base


def test_the_version_is_recorded_and_the_registers_are_populated():
    assert VERSION == "V1.0.0_Frozen"
    assert FROZEN.version == VERSION
    assert len(AMBIGUITIES) >= 13
    assert len(CONFLICTS) >= 9
    for a in AMBIGUITIES:
        assert a.ref and a.rule and a.question and a.reading
    for c in CONFLICTS:
        assert c.ref and c.component and c.disagreement and c.resolution


def test_the_material_ambiguities_are_the_ones_with_both_readings_implemented():
    from quant_brain.strategies.vwap_pullback.spec import unresolved
    material = {a.ref for a in unresolved()}
    assert {"A1", "A2"} <= material, "the ATR and MTM readings must be flagged as material"
    for ref in ("A1", "A2"):
        a = next(x for x in AMBIGUITIES if x.ref == ref)
        assert a.both_implemented, f"{ref} is material but only one reading exists"


def test_the_engine_is_deterministic_and_carries_no_randomness():
    outs = []
    for _ in range(2):
        sc = long_scenario()
        e = Engine()
        e.run(sc.bars)
        f = e.position.fill_price
        e.run([sc.then(minutes_after=1, high=f + 31.0, low=f + 1.0, close=f + 30.0)])
        outs.append([(t.entry_price, t.exit_price, t.net_pnl, t.exit_reason)
                     for t in e.trades])
    assert outs[0] == outs[1]


def test_no_module_in_the_package_imports_a_random_generator_or_a_broker():
    import quant_brain.strategies.vwap_pullback as pkg
    root = Path(pkg.__file__).parent
    for f in root.glob("*.py"):
        src = f.read_text(encoding="utf-8")
        for banned in ("import random", "np.random", "ib_async", "requests",
                       "placeOrder", "socket"):
            assert banned not in src, f"{f.name} contains {banned!r}"


def test_the_order_layer_has_no_transmission_surface():
    from quant_brain.strategies.vwap_pullback import orders
    src = Path(orders.__file__).read_text(encoding="utf-8")
    for banned in ("http", "connect", "send", "api", "token=os.environ"):
        assert banned not in src.lower().replace("idempotency token", ""), banned


# =====================================================================================
# THE BOOK STAYS DEFENSIBLE THROUGH A WHOLE DAY
# =====================================================================================

def test_a_full_day_of_bars_never_leaves_the_book_indefensible():
    """The audit runs after every bar inside the engine; this walks a whole session."""
    sc = Scenario().warmup().arm_long(trigger_at="10:00")
    e = Engine()
    e.run(sc.bars)
    f = e.position.fill_price
    t = et_at(DAY, "10:01")
    while t <= et_at(DAY, "16:30"):
        e.on_bar(Bar(timestamp=t, open=f, high=f + 2.0, low=f - 2.0, close=f,
                     volume=QUIET_VOLUME))
        assert e.book.audit() == ()
        t += dt.timedelta(minutes=1)
    assert e.position is None, "the hard flatten never fired"
    assert e.trades[-1].exit_reason == "hard_flatten"
