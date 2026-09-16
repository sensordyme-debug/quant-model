"""GOLDEN: the V1.0.0_Frozen state machine, triggers, brackets, break-even and stall rule.

The two tests this file exists for are `test_a_break_even_fires_on_the_bars_high_even_when_it
_closes_back_below` and `test_a_break_on_t_plus_3_prevents_the_stall_modification`. Both are
written so that an implementation reading the wrong thing - the close instead of the high, a
two-bar window instead of three - fails rather than merely reports something different.
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
    assert_vwap_is_pinned,
    et_at,
    flat_bar,
    long_scenario,
    short_scenario,
)

from quant_brain.strategies.vwap_pullback.engine import (  # noqa: E402
    EXIT_HARD_FLATTEN,
    EXIT_STALL,
    EXIT_STOP,
    EXIT_TARGET,
    TRANSITIONS,
    Engine,
    IllegalTransition,
    State,
)
from quant_brain.strategies.vwap_pullback.indicators import Bar  # noqa: E402
from quant_brain.strategies.vwap_pullback.orders import (  # noqa: E402
    BracketError,
    OrderStatus,
)
from quant_brain.strategies.vwap_pullback.spec import FROZEN  # noqa: E402

TICK = FROZEN.tick               # 0.25
PV = FROZEN.point_value          # 20.0


def run_long(extra=None) -> tuple[Engine, Scenario]:
    sc = long_scenario()
    e = Engine()
    e.run(sc.bars)
    if extra:
        e.run(extra(sc, e))
    return e, sc


# =====================================================================================
# THE WARM-UP ITSELF IS SOUND
# =====================================================================================

def test_the_scenario_pins_the_vwap_and_opens_a_long_at_the_expected_prices():
    e, sc = run_long()
    assert_vwap_is_pinned(e)
    assert e.state is State.IN_POSITION
    p = e.position
    # trigger close 20,001.50 + one tick of adverse slippage
    assert p.fill_price == pytest.approx(LEVEL + 1.75)
    assert p.direction == 1
    assert p.stop_price == pytest.approx(p.fill_price - FROZEN.stop_points)
    assert p.target_price == pytest.approx(p.fill_price + FROZEN.target_points)


def test_the_mirror_scenario_opens_a_short_at_the_mirrored_prices():
    sc = short_scenario()
    e = Engine()
    e.run(sc.bars)
    p = e.position
    assert p.direction == -1
    assert p.fill_price == pytest.approx(LEVEL - 1.75)
    assert p.stop_price == pytest.approx(p.fill_price + FROZEN.stop_points)
    assert p.target_price == pytest.approx(p.fill_price - FROZEN.target_points)


# =====================================================================================
# FILL-PRICE ANCHORING  (brief §9, the "CRITICAL" one)
# =====================================================================================

def test_the_bracket_is_anchored_to_the_FILL_and_never_to_the_signal_bar_close():
    """The fill is one tick away from the close, so the two anchors give different levels.

    If the stop were computed from the signal bar's close it would sit at 19,986.50; from the
    fill it sits at 19,986.75. A quarter point is one tick and $5, and the difference is the
    whole reason the brief calls this critical.
    """
    e, sc = run_long()
    trigger_close = LEVEL + 1.5
    fill = e.position.fill_price
    assert fill != pytest.approx(trigger_close), "no slippage was applied to the fill"
    assert e.position.stop_price == pytest.approx(fill - 15.0)
    assert e.position.stop_price != pytest.approx(trigger_close - 15.0)
    assert e.position.target_price == pytest.approx(fill + 30.0)
    assert e.position.target_price != pytest.approx(trigger_close + 30.0)


def test_entry_slippage_is_always_adverse_on_both_sides():
    long_e, _ = run_long()
    short_e = Engine()
    short_e.run(short_scenario().bars)
    assert long_e.position.fill_price > LEVEL + 1.5, "a long paid less than the close"
    assert short_e.position.fill_price < LEVEL - 1.5, "a short received more than the close"


def test_the_order_layer_cannot_see_the_signal_bar_at_all():
    """Structural: `attach_bracket` takes the entry ORDER, whose only price is the fill."""
    import inspect

    from quant_brain.strategies.vwap_pullback.orders import OrderBook
    params = set(inspect.signature(OrderBook.attach_bracket).parameters)
    assert params == {"self", "entry", "stop_points", "target_points", "token"}


# =====================================================================================
# OCO  (brief §10)
# =====================================================================================

def test_the_entry_produces_one_linked_bracket_with_the_right_side_and_quantity():
    e, _ = run_long()
    b = e.book.bracket
    assert b.stop.oco_group == b.target.oco_group == b.group
    assert b.stop.side is b.target.side, "the two exits are on different sides"
    assert b.stop.side.value == "sell", "a long's exits must sell"
    assert b.stop.quantity == b.target.quantity == FROZEN.contracts
    assert b.stop.price == pytest.approx(b.fill_price - 15.0)
    assert b.target.price == pytest.approx(b.fill_price + 30.0)
    assert e.book.audit() == ()


def test_a_short_brackets_on_the_buy_side():
    e = Engine()
    e.run(short_scenario().bars)
    b = e.book.bracket
    assert b.stop.side.value == "buy"
    assert b.stop.price == pytest.approx(b.fill_price + 15.0)


def test_the_filled_leg_cancels_the_other_one():
    def stop_out(sc, e):
        f = e.position.fill_price
        return [sc.then(minutes_after=1, high=f, low=f - 20, close=f - 18)]

    e, _ = run_long(stop_out)
    b = e.book.bracket if e.book.bracket else None
    assert b is None, "the bracket was not released after the position closed"
    stops = [o for o in e.book.orders.values() if o.order_id.startswith("STOP")]
    targets = [o for o in e.book.orders.values() if o.order_id.startswith("TARGET")]
    assert stops[0].status is OrderStatus.FILLED
    assert targets[0].status is OrderStatus.CANCELLED
    assert "OCO" in targets[0].reason


def test_no_bracket_can_survive_the_position_it_protected():
    def stop_out(sc, e):
        f = e.position.fill_price
        return [sc.then(minutes_after=1, high=f, low=f - 20, close=f - 18)]

    e, _ = run_long(stop_out)
    assert e.position is None
    assert not [o for o in e.book.orders.values() if o.working], "an order outlived the trade"
    assert e.book.audit() == ()


def test_a_second_bracket_on_one_position_is_refused():
    e, _ = run_long()
    with pytest.raises(BracketError, match="already protects"):
        e.book.attach_bracket(entry=e.book.bracket.entry, stop_points=15.0,
                              target_points=30.0, token="a-different-token")


def test_a_rejected_entry_leaves_no_bracket_and_no_position():
    from quant_brain.strategies.vwap_pullback.orders import OrderBook
    book = OrderBook()
    rejected = book.reject_entry(token="t1", reason="risk refused")
    assert book.position == 0 and book.bracket is None
    with pytest.raises(BracketError, match="unfilled entry"):
        book.attach_bracket(entry=rejected, stop_points=15.0, target_points=30.0,
                            token="t2")
    assert book.audit() == ()


def test_a_second_entry_while_positioned_is_refused_by_the_book_as_well_as_the_fsm():
    e, _ = run_long()
    with pytest.raises(BracketError, match="second entry"):
        e.book.submit_entry(direction=1, quantity=1, fill_price=LEVEL, token="another")


def test_releasing_a_bracket_is_refused_while_a_position_is_open():
    e, _ = run_long()
    with pytest.raises(BracketError, match="refusing to release"):
        e.book.release()


def test_releasing_a_bracket_with_a_working_leg_is_refused_even_when_flat():
    """The orphan case proper: the book is flat but a leg was never cancelled."""
    from quant_brain.strategies.vwap_pullback.orders import OrderBook
    book = OrderBook()
    entry = book.submit_entry(direction=1, quantity=1, fill_price=100.0, token="e")
    book.attach_bracket(entry=entry, stop_points=15.0, target_points=30.0, token="b")
    book.position = 0                      # flatten behind the book's back
    with pytest.raises(BracketError, match="still working"):
        book.release()
    assert "ORPHAN" in book.audit()[0]


# =====================================================================================
# IDEMPOTENCY  (brief §27)
# =====================================================================================

def test_every_mutating_order_action_is_idempotent():
    from quant_brain.strategies.vwap_pullback.orders import OrderBook
    book = OrderBook()
    a = book.submit_entry(direction=1, quantity=1, fill_price=100.0, token="e1")
    b = book.submit_entry(direction=1, quantity=1, fill_price=100.0, token="e1")
    assert a is b and book.position == 1

    br1 = book.attach_bracket(entry=a, stop_points=15.0, target_points=30.0, token="b1")
    br2 = book.attach_bracket(entry=a, stop_points=15.0, target_points=30.0, token="b1")
    assert br1 is br2
    assert len([o for o in book.orders.values() if o.order_id.startswith("STOP")]) == 1

    book.modify_stop(price=100.25, token="m1", reason="be")
    book.modify_stop(price=999.0, token="m1", reason="be")
    assert book.bracket.stop.price == pytest.approx(100.25), "a repeat modify took effect"

    book.modify_target(price=120.0, token="t1", reason="stall")
    book.modify_target(price=999.0, token="t1", reason="stall")
    assert book.bracket.target.price == pytest.approx(120.0)

    x1 = book.fill_exit(which="stop", price=100.25, token="x1")
    x2 = book.fill_exit(which="stop", price=999.0, token="x1")
    assert x1 is x2 and book.position == 0


def test_a_repeated_market_data_event_cannot_produce_a_second_entry():
    """The bar arrives twice. One entry, and the duplicate is named as such."""
    sc = long_scenario()
    e = Engine()
    e.run(sc.bars)
    assert len(e.trades) == 0 and e.position is not None
    before = e.book.position
    out = e.on_bar(sc.bars[-1])
    assert out.ignored == "duplicate bar"
    assert e.book.position == before
    assert len([o for o in e.book.orders.values() if o.order_id.startswith("ENTRY")]) == 1


def test_an_out_of_order_bar_is_refused_rather_than_absorbed():
    sc = long_scenario()
    e = Engine()
    e.run(sc.bars)
    stale = flat_bar(sc.trigger_time - dt.timedelta(minutes=5), level=LEVEL, width=0.25,
                     volume=QUIET_VOLUME)
    out = e.on_bar(stale)
    assert out.ignored == "out-of-order bar"


def test_cancel_working_is_idempotent():
    e, _ = run_long()
    n1 = e.book.cancel_working(token="c1")
    n2 = e.book.cancel_working(token="c1")
    assert n1 == 2 and n2 == 0            # the stop and the target, then nothing


# =====================================================================================
# BREAK-EVEN  (brief §11 - intrabar, not close-based)
# =====================================================================================

def test_a_break_even_fires_on_the_bars_high_even_when_it_closes_back_below():
    """THE TEST A CLOSE-ONLY IMPLEMENTATION MUST FAIL.

    The brief's own example, in the scenario's prices: entry 20,001.75, a bar whose HIGH
    reaches +16 but whose CLOSE is only +5. A rule reading the close sees +5, well under the
    15-point trigger, and does nothing.
    """
    def wick(sc, e):
        f = e.position.fill_price
        return [sc.then(minutes_after=1, high=f + 16.0, low=f - 1.0, close=f + 5.0)]

    e, _ = run_long(wick)
    assert e.outcomes[-1].breakeven, "the high was ignored; this is a close-only break-even"
    assert e.position.stop_price == pytest.approx(e.position.fill_price + 0.25)
    assert e.book.bracket.stop.price == pytest.approx(e.position.fill_price + 0.25)


@pytest.mark.parametrize("excursion,expected", [(14.99, False), (15.0, True), (15.01, True)])
def test_the_break_even_trigger_is_a_closed_boundary_at_fifteen_points(excursion, expected):
    def wick(sc, e):
        f = e.position.fill_price
        return [sc.then(minutes_after=1, high=f + excursion, low=f - 1.0, close=f + 1.0)]

    e, _ = run_long(wick)
    assert e.outcomes[-1].breakeven is expected
    want = (e.position.fill_price + 0.25) if expected else (e.position.fill_price - 15.0)
    assert e.position.stop_price == pytest.approx(want)


def test_the_short_break_even_mirrors_on_the_low():
    sc = short_scenario()
    e = Engine()
    e.run(sc.bars)
    f = e.position.fill_price
    e.run([sc.then(minutes_after=1, high=f + 1.0, low=f - 16.0, close=f - 5.0)])
    assert e.outcomes[-1].breakeven
    assert e.position.stop_price == pytest.approx(f - 0.25)


def test_the_break_even_arms_only_once():
    def twice(sc, e):
        f = e.position.fill_price
        return [sc.then(minutes_after=1, high=f + 16.0, low=f + 1.0, close=f + 5.0),
                sc.then(minutes_after=2, high=f + 17.0, low=f + 1.0, close=f + 6.0)]

    e, _ = run_long(twice)
    assert e.outcomes[-2].breakeven and not e.outcomes[-1].breakeven
    modifies = [ev for ev in e.book.events if ev.startswith("MODIFY STOP")]
    assert len(modifies) == 1, f"the stop was modified {len(modifies)} times"


def test_the_break_even_does_not_rescue_a_bar_that_also_touched_the_original_stop():
    """AMBIGUITY A15, and the conservative reading, made visible.

    One bar reaches fill+15 AND fill-15. OHLCV cannot say which came first. Arming the
    break-even before testing the bar's own low would turn a full 15-point loss into a
    one-tick win on an assumption. The original stop is in force for the whole of the bar it
    arms on.
    """
    def both(sc, e):
        f = e.position.fill_price
        return [sc.then(minutes_after=1, high=f + 16.0, low=f - 16.0, close=f - 10.0)]

    e, _ = run_long(both)
    assert e.trades, "the bar touched the stop and nothing closed"
    t = e.trades[0]
    assert t.exit_reason == EXIT_STOP
    # the ORIGINAL stop, minus a tick of slippage - not fill + 0.25
    assert t.exit_price == pytest.approx(LEVEL + 1.75 - 15.0 - 0.25)


# =====================================================================================
# THE +25 STALL RULE  (brief §12)
# =====================================================================================

def _stall_bars(sc, e, t3_close_offset: float, *, mfe_high: float = 26.0):
    """MFE bar reaching +`mfe_high`, then three bars whose closes the test controls."""
    f = e.position.fill_price
    return [
        sc.then(minutes_after=1, high=f + mfe_high, low=f + 10.0, close=f + 20.0),
        sc.then(minutes_after=2, high=f + 21.0, low=f + 15.0, close=f + 21.0),
        sc.then(minutes_after=3, high=f + 20.0, low=f + 14.0, close=f + 19.0),
        sc.then(minutes_after=4, high=f + max(20.0, t3_close_offset),
                low=f + min(14.0, t3_close_offset - 1.0), close=f + t3_close_offset),
    ]


def test_a_stall_after_three_failed_closes_modifies_the_target_to_plus_twenty():
    e, sc = run_long()
    e.run(_stall_bars(sc, e, t3_close_offset=18.0))
    f = e.position.fill_price
    assert e.outcomes[-1].stall_modified, "the stall did not fire"
    assert e.position.target_price == pytest.approx(f + 20.0)
    assert e.book.bracket.target.price == pytest.approx(f + 20.0)


def test_a_break_on_t_plus_3_prevents_the_stall_modification():
    """THE LOOKAHEAD TEST THE BRIEF CALLS ABSOLUTELY CRITICAL.

    t+1 and t+2 both fail to break the MFE bar's high; t+3 breaks it. An implementation that
    decided at t+2 - or that peeked forward - would already have modified the target. The
    identical sequence with t+3 NOT breaking is the control below.
    """
    e, sc = run_long()
    f = e.position.fill_price
    e.run(_stall_bars(sc, e, t3_close_offset=27.0))     # 27 > the 26-point MFE high
    assert not any(o.stall_modified for o in e.outcomes), (
        "the target was modified even though t+3 broke the MFE bar's high")
    assert e.position is not None
    assert e.position.target_price == pytest.approx(f + 30.0), "the original target moved"


def test_the_control_sequence_differing_only_at_t_plus_3_does_stall():
    """Identical bars except the last close. One stalls, one does not."""
    a, sc_a = run_long()
    a.run(_stall_bars(sc_a, a, t3_close_offset=27.0))
    b, sc_b = run_long()
    b.run(_stall_bars(sc_b, b, t3_close_offset=18.0))
    assert not any(o.stall_modified for o in a.outcomes)
    assert any(o.stall_modified for o in b.outcomes)


def test_a_break_at_t_plus_1_also_prevents_the_modification():
    e, sc = run_long()
    f = e.position.fill_price
    e.run([
        sc.then(minutes_after=1, high=f + 26.0, low=f + 10.0, close=f + 20.0),
        sc.then(minutes_after=2, high=f + 28.0, low=f + 20.0, close=f + 27.0),   # breaks
        sc.then(minutes_after=3, high=f + 20.0, low=f + 14.0, close=f + 19.0),
        sc.then(minutes_after=4, high=f + 20.0, low=f + 14.0, close=f + 18.0),
    ])
    assert not any(o.stall_modified for o in e.outcomes)


@pytest.mark.parametrize("mfe,fires", [(24.99, False), (25.0, True), (25.01, True)])
def test_the_stall_mfe_threshold_is_a_closed_boundary_at_twenty_five(mfe, fires):
    e, sc = run_long()
    f = e.position.fill_price
    e.run([
        sc.then(minutes_after=1, high=f + mfe, low=f + 10.0, close=f + 20.0),
        sc.then(minutes_after=2, high=f + 21.0, low=f + 15.0, close=f + 19.0),
        sc.then(minutes_after=3, high=f + 20.0, low=f + 14.0, close=f + 18.0),
        sc.then(minutes_after=4, high=f + 20.0, low=f + 14.0, close=f + 17.0),
    ])
    assert any(o.stall_modified for o in e.outcomes) is fires


def test_the_window_is_three_bars_and_not_two():
    """A two-bar implementation would fire one bar early; here t+3 breaks the high."""
    e, sc = run_long()
    outs = e.run(_stall_bars(sc, e, t3_close_offset=27.0))
    assert not outs[1].stall_modified, "the rule decided at t+2"
    assert not outs[2].stall_modified, "the rule decided at t+3's predecessor"
    assert not any(o.stall_modified for o in outs)


def test_the_mfe_bar_is_the_FIRST_bar_to_reach_plus_twenty_five():
    """A later, higher bar must not move the reference the three closes are measured against."""
    e, sc = run_long()
    f = e.position.fill_price
    e.run([
        sc.then(minutes_after=1, high=f + 26.0, low=f + 10.0, close=f + 20.0),   # MFE bar
        sc.then(minutes_after=2, high=f + 28.0, low=f + 20.0, close=f + 25.0),
        sc.then(minutes_after=3, high=f + 20.0, low=f + 14.0, close=f + 19.0),
        sc.then(minutes_after=4, high=f + 20.0, low=f + 14.0, close=f + 18.0),
    ])
    # t+1 closed at +25, BELOW the MFE bar's +26 high, so no break; t+2 and t+3 also fail.
    assert any(o.stall_modified for o in e.outcomes)
    assert e.position.mfe_bar_extreme == pytest.approx(f + 26.0)


def test_the_target_is_modified_only_once():
    e, sc = run_long()
    f = e.position.fill_price
    e.run(_stall_bars(sc, e, t3_close_offset=18.0))
    e.run([sc.then(minutes_after=5, high=f + 19.0, low=f + 14.0, close=f + 17.0),
           sc.then(minutes_after=6, high=f + 19.0, low=f + 14.0, close=f + 16.0)])
    mods = [ev for ev in e.book.events if ev.startswith("MODIFY TARGET")]
    assert len(mods) == 1, f"the target was modified {len(mods)} times"


def test_a_stall_whose_new_target_is_already_through_closes_at_market():
    """AMBIGUITY A10: at the modification bar the close is already past fill+20."""
    e, sc = run_long()
    f = e.position.fill_price
    e.run([
        sc.then(minutes_after=1, high=f + 26.0, low=f + 10.0, close=f + 20.0),
        sc.then(minutes_after=2, high=f + 25.0, low=f + 15.0, close=f + 22.0),
        sc.then(minutes_after=3, high=f + 25.0, low=f + 20.0, close=f + 23.0),
        sc.then(minutes_after=4, high=f + 25.0, low=f + 20.0, close=f + 24.0),
    ])
    assert e.position is None, "the position should have been closed at market"
    assert e.trades[-1].exit_reason == EXIT_STALL
    assert e.trades[-1].exit_price == pytest.approx(f + 24.0)


def test_the_short_side_stall_mirrors_exactly():
    sc = short_scenario()
    e = Engine()
    e.run(sc.bars)
    f = e.position.fill_price
    e.run([
        sc.then(minutes_after=1, high=f - 10.0, low=f - 26.0, close=f - 20.0),
        sc.then(minutes_after=2, high=f - 15.0, low=f - 21.0, close=f - 19.0),
        sc.then(minutes_after=3, high=f - 14.0, low=f - 20.0, close=f - 18.0),
        sc.then(minutes_after=4, high=f - 14.0, low=f - 20.0, close=f - 17.0),
    ])
    assert any(o.stall_modified for o in e.outcomes)
    assert e.position.target_price == pytest.approx(f - 20.0)


def test_a_position_that_exits_before_t_plus_3_never_stalls():
    e, sc = run_long()
    f = e.position.fill_price
    e.run([
        sc.then(minutes_after=1, high=f + 26.0, low=f + 10.0, close=f + 20.0),
        sc.then(minutes_after=2, high=f + 31.0, low=f + 20.0, close=f + 30.0),   # target
        sc.then(minutes_after=3, high=f + 20.0, low=f + 14.0, close=f + 18.0),
    ])
    assert e.trades[-1].exit_reason == EXIT_TARGET
    assert not any(o.stall_modified for o in e.outcomes)


def test_the_break_even_and_the_stall_can_both_be_active():
    e, sc = run_long()
    f = e.position.fill_price
    e.run(_stall_bars(sc, e, t3_close_offset=18.0))
    assert e.position.breakeven_done, "a +26 excursion should have armed break-even"
    assert e.position.stop_price == pytest.approx(f + 0.25)
    assert e.position.target_price == pytest.approx(f + 20.0)


# =====================================================================================
# CAUSALITY  (brief §22)
# =====================================================================================

def test_decisions_before_a_mutation_point_are_identical_however_the_future_changes():
    """Run twice; replace every bar after the decision point with something violent.

    Every outcome up to the mutation point must be byte-identical, including the states, the
    entries, the modifications and the trades booked so far.
    """
    def snapshot(e, upto):
        return [(o.timestamp, o.state, o.entered, o.exited, o.breakeven, o.stall_modified,
                 round(o.vwap, 9)) for o in e.outcomes[:upto]]

    sc = long_scenario()
    e1 = Engine()
    e1.run(sc.bars)
    f = e1.position.fill_price
    tail_a = _stall_bars(sc, e1, t3_close_offset=18.0)
    e1.run(tail_a)
    cut = len(sc.bars) + 2                    # partway through the stall window

    sc2 = long_scenario()
    e2 = Engine()
    e2.run(sc2.bars)
    tail_b = list(_stall_bars(sc2, e2, t3_close_offset=18.0))
    # mutate everything from the cut onward into a violent, unrelated future
    for i in range(2, len(tail_b)):
        b = tail_b[i]
        tail_b[i] = Bar(timestamp=b.timestamp, open=f, high=f + 900.0, low=f - 900.0,
                        close=f - 800.0, volume=999_999.0)
    e2.run(tail_b)

    assert snapshot(e1, cut) == snapshot(e2, cut), (
        "a decision before the mutation point changed when the future changed")


def test_the_engine_is_never_handed_a_container_of_bars():
    """Structural causality: `on_bar` takes ONE bar, so there is no `bars[i+1]` to read."""
    import inspect
    sig = inspect.signature(Engine.on_bar)
    assert list(sig.parameters) == ["self", "bar"]
    assert sig.parameters["bar"].annotation == "Bar"


def test_every_indicator_takes_one_bar_at_a_time_and_never_a_series():
    """Online accumulators. `update` takes a single bar, so no window can reach forward."""
    import inspect

    from quant_brain.strategies.vwap_pullback.indicators import (
        Atr,
        FiveMinuteAggregator,
        SessionVwap,
        VolumeSma,
    )
    for cls in (SessionVwap, VolumeSma, Atr, FiveMinuteAggregator):
        params = [n for n in inspect.signature(cls.update).parameters if n != "self"]
        assert params[0] == "bar", f"{cls.__name__}.update does not take a single bar"
        assert len(params) <= 2, f"{cls.__name__}.update takes more than one bar"


def test_a_trigger_decision_does_not_depend_on_the_bar_after_it():
    """The same trigger bar, two different following bars: the entry must be identical."""
    outs = []
    for follow_close in (LEVEL + 50.0, LEVEL - 50.0):
        sc = long_scenario()
        e = Engine()
        e.run(sc.bars)
        entry = (e.position.fill_price, e.position.stop_price, e.position.target_price)
        e.run([sc.then(minutes_after=1, high=follow_close + 1, low=follow_close - 1,
                       close=follow_close)])
        outs.append(entry)
    assert outs[0] == outs[1]


# =====================================================================================
# EXECUTION AMBIGUITY  (brief §23)
# =====================================================================================

def test_a_bar_touching_both_stop_and_target_resolves_as_the_stop_and_is_flagged():
    """The repository's declared precedence: STOP before TARGET, ambiguity recorded."""
    def both(sc, e):
        f = e.position.fill_price
        return [sc.then(minutes_after=1, high=f + 31.0, low=f - 16.0, close=f)]

    e, _ = run_long(both)
    t = e.trades[0]
    assert t.exit_reason == EXIT_STOP
    assert t.ambiguous_bar is True


def test_the_short_side_ambiguous_bar_also_resolves_as_the_stop():
    sc = short_scenario()
    e = Engine()
    e.run(sc.bars)
    f = e.position.fill_price
    e.run([sc.then(minutes_after=1, high=f + 16.0, low=f - 31.0, close=f)])
    assert e.trades[0].exit_reason == EXIT_STOP
    assert e.trades[0].ambiguous_bar is True


def test_a_gap_straight_through_the_stop_fills_at_the_stop_level():
    """The declared modelling choice, reused from `research/bracket_reference`."""
    def gap(sc, e):
        f = e.position.fill_price
        return [sc.then(minutes_after=1, high=f - 40.0, low=f - 60.0, close=f - 50.0)]

    e, _ = run_long(gap)
    t = e.trades[0]
    # the stop level less one tick of slippage - NOT the -50 the bar traded
    assert t.exit_price == pytest.approx(LEVEL + 1.75 - 15.0 - 0.25)


def test_a_gap_straight_through_the_target_fills_at_the_target_level():
    def gap(sc, e):
        f = e.position.fill_price
        return [sc.then(minutes_after=1, high=f + 60.0, low=f + 40.0, close=f + 50.0)]

    e, _ = run_long(gap)
    assert e.trades[0].exit_price == pytest.approx(LEVEL + 1.75 + 30.0)


@pytest.mark.parametrize("depth,exits", [(15.0, True), (14.99, False)])
def test_an_exact_touch_fills_and_a_one_tick_miss_does_not(depth, exits):
    def probe(sc, e):
        f = e.position.fill_price
        return [sc.then(minutes_after=1, high=f + 1.0, low=f - depth, close=f - 1.0)]

    e, _ = run_long(probe)
    assert bool(e.trades) is exits


def test_the_entry_bar_cannot_stop_the_position_out_that_same_bar():
    """A position filled at a bar's close cannot be hit by that bar's low; it already happened.

    The trigger bar's low is 3.75 points under the fill - well inside a 15-point stop - but it
    is also in the past by the time the fill exists.
    """
    e, sc = run_long()
    assert e.position is not None and not e.trades
    assert e.position.entry_bar == len(sc.bars) - 1


# =====================================================================================
# THE STATE MACHINE  (brief §8, §26)
# =====================================================================================

def test_the_declared_transition_table_covers_every_state():
    assert set(TRANSITIONS) == set(State)


@pytest.mark.parametrize("src,dst", [
    (State.FLAT_MONITORING, State.ARMED_LONG),
    (State.FLAT_MONITORING, State.ARMED_SHORT),
    (State.FLAT_MONITORING, State.HALTED_DAY),
    (State.FLAT_MONITORING, State.COOLDOWN),
    (State.ARMED_LONG, State.IN_POSITION),
    (State.ARMED_SHORT, State.IN_POSITION),
    (State.ARMED_LONG, State.FLAT_MONITORING),
    (State.ARMED_SHORT, State.FLAT_MONITORING),
    (State.ARMED_LONG, State.HALTED_DAY),
    (State.ARMED_SHORT, State.HALTED_DAY),
    (State.IN_POSITION, State.FLAT_MONITORING),
    (State.IN_POSITION, State.COOLDOWN),
    (State.IN_POSITION, State.HALTED_DAY),
    (State.COOLDOWN, State.FLAT_MONITORING),
    (State.COOLDOWN, State.HALTED_DAY),
])
def test_every_legal_transition_is_permitted(src, dst):
    e = Engine()
    e.state = src
    e._to(dst, et_at(dt.date(2026, 1, 6), "10:00"))
    assert e.state is dst


@pytest.mark.parametrize("src,dst", [
    (State.HALTED_DAY, State.FLAT_MONITORING),
    (State.HALTED_DAY, State.ARMED_LONG),
    (State.HALTED_DAY, State.IN_POSITION),
    (State.HALTED_DAY, State.COOLDOWN),
    (State.FLAT_MONITORING, State.IN_POSITION),
    (State.COOLDOWN, State.ARMED_LONG),
    (State.COOLDOWN, State.ARMED_SHORT),
    (State.COOLDOWN, State.IN_POSITION),
])
def test_every_illegal_transition_is_refused(src, dst):
    e = Engine()
    e.state = src
    with pytest.raises(IllegalTransition):
        e._to(dst, et_at(dt.date(2026, 1, 6), "10:00"))


def test_a_halted_day_can_only_be_left_at_the_eighteen_hundred_roll():
    """Not by a timeout, not by a flat book, not by a new signal. Only by the day rolling."""
    sc = Scenario().warmup().pad_until("09:44")
    e = Engine()
    e.run(sc.bars)
    e.governor.halt(sc.bars[-1].timestamp, "test")
    e.state = State.HALTED_DAY
    # bars through the rest of the day change nothing
    t = et_at(sc.day, "10:00")
    while t < et_at(sc.day, "17:59"):
        e.on_bar(flat_bar(t, level=LEVEL, width=0.25, volume=QUIET_VOLUME))
        assert e.state is State.HALTED_DAY
        t += dt.timedelta(minutes=30)
    e.on_bar(flat_bar(et_at(sc.day, "18:00"), level=LEVEL, width=0.25,
                      volume=QUIET_VOLUME))
    assert e.state is State.FLAT_MONITORING
    assert not e.governor.halted


def test_an_armed_setup_returns_to_monitoring_when_it_is_invalidated():
    """Long invalidation: a close more than 15 points below the VWAP abandons the setup."""
    sc = Scenario().warmup().arm_only(at="09:44")
    e = Engine()
    e.run(sc.bars)
    e.on_bar(flat_bar(et_at(sc.day, "09:45"), level=LEVEL, width=0.25,
                      volume=QUIET_VOLUME))
    assert e.state is State.ARMED_LONG
    far_below = LEVEL - 20.0
    e.on_bar(Bar(timestamp=et_at(sc.day, "09:46"), open=LEVEL, high=LEVEL,
                 low=far_below - 1, close=far_below, volume=QUIET_VOLUME))
    assert e.state is State.FLAT_MONITORING
    assert "long invalidated" in e.outcomes[-1].notes


def test_a_position_exit_leaves_IN_POSITION_by_way_of_monitoring():
    """The exit transition is IN_POSITION -> FLAT_MONITORING.

    The machine may then re-arm on the SAME bar if the 5-minute context still holds - that is
    a new opinion formed from data already seen, not a leftover of the closed trade - so the
    assertion is on the transition rather than on the state at the end of the bar.
    """
    def target(sc, e):
        f = e.position.fill_price
        return [sc.then(minutes_after=1, high=f + 31.0, low=f + 1.0, close=f + 30.0)]

    e, _ = run_long(target)
    assert e.position is None
    assert e.trades[0].exit_reason == EXIT_TARGET
    assert (State.IN_POSITION, State.FLAT_MONITORING) in [
        (a, b) for _, a, b in e.transitions]
    assert e.state in (State.FLAT_MONITORING, State.ARMED_LONG, State.ARMED_SHORT)


def test_no_simultaneous_long_and_short_is_possible():
    """Enforced twice - the FSM has no ARMED->ARMED-with-position edge, and the book refuses."""
    e, _ = run_long()
    assert e.book.position == 1
    with pytest.raises(BracketError):
        e.book.submit_entry(direction=-1, quantity=1, fill_price=LEVEL, token="opposite")


# =====================================================================================
# ENTRY WINDOWS AND THE HARD FLATTEN  (brief §4, §18)
# =====================================================================================

@pytest.mark.parametrize("hhmm,enters", [("09:44", False), ("09:45", True),
                                         ("15:29", True), ("15:30", True),
                                         ("15:31", False)])
def test_the_entry_window_boundaries(hhmm, enters):
    """09:45 opens monitoring; 15:30 is the last bar an entry may be decided on (A3).

    An identical, fully-qualifying trigger bar is placed at each time; only the clock differs.
    """
    e = Engine()
    e.run(Scenario().warmup().arm_long(trigger_at=hhmm).bars)
    assert (e.position is not None) is enters, (
        f"entry at {hhmm} was {'refused' if e.position is None else 'taken'}")


def test_the_hard_flatten_closes_the_position_at_exactly_fifteen_forty_five():
    sc = long_scenario()
    e = Engine()
    e.run(sc.bars)
    f = e.position.fill_price
    # quiet bars up to 15:44 - normal operation
    t = et_at(sc.day, "09:46")
    while t <= et_at(sc.day, "15:44"):
        e.on_bar(Bar(timestamp=t, open=f, high=f + 1.0, low=f - 1.0, close=f,
                     volume=QUIET_VOLUME))
        t += dt.timedelta(minutes=1)
    assert e.position is not None, "the position closed before 15:45"
    e.on_bar(Bar(timestamp=et_at(sc.day, "15:45"), open=f, high=f + 1.0, low=f - 1.0,
                 close=f + 0.5, volume=QUIET_VOLUME))
    assert e.position is None
    assert e.trades[-1].exit_reason == EXIT_HARD_FLATTEN
    assert e.trades[-1].exit_price == pytest.approx(f + 0.5)   # the bar's close


def test_nothing_trades_after_the_hard_flatten():
    sc = long_scenario()
    e = Engine()
    e.run(sc.bars)
    f = e.position.fill_price
    e.on_bar(Bar(timestamp=et_at(sc.day, "15:45"), open=f, high=f, low=f, close=f,
                 volume=QUIET_VOLUME))
    assert e.position is None
    # a perfect trigger at 15:46 must do nothing
    late = Bar(timestamp=et_at(sc.day, "15:46"), open=LEVEL - 1.0, high=LEVEL + 1.5,
               low=LEVEL - 2.0, close=LEVEL + 1.5, volume=100_000.0)
    e.on_bar(late)
    assert e.position is None
    assert e.book.audit() == ()


# =====================================================================================
# C9 / C10 - THE PROXIMITY INEQUALITIES, IMPLEMENTED LITERALLY  (brief DECISION 4)
# =====================================================================================
# These are NOT implementation defects. `VWAP - 5m low <= 6.0` is satisfied by a candle lying
# entirely ABOVE the VWAP, because the left-hand side is then negative. The engine matches the
# frozen rule as written; the tests below prove the literal behaviour so that the rule cannot
# be quietly reinterpreted, and the register records it as a strategy-definition
# characteristic rather than a bug.

def test_c9_the_long_proximity_rule_is_satisfied_by_a_negative_distance():
    """The arithmetic, before any engine is involved.

        VWAP = 20,000, 5m low = 20,005  ->  20,000 - 20,005 = -5  ->  -5 <= 6  is TRUE
    """
    vwap, low = 20_000.0, 20_005.0
    assert (vwap - low) == -5.0
    assert (vwap - low) <= FROZEN.context_max_distance


def test_c10_the_short_proximity_rule_mirrors_it():
    """VWAP = 20,000, 5m high = 19,995  ->  19,995 - 20,000 = -5  ->  -5 <= 6  is TRUE."""
    vwap, high = 20_000.0, 19_995.0
    assert (high - vwap) == -5.0
    assert (high - vwap) <= FROZEN.context_max_distance


def test_c9_a_five_minute_bucket_entirely_above_the_vwap_still_arms_long():
    """The characteristic, end to end: a bucket that never approached the VWAP qualifies."""
    sc = Scenario().warmup().arm_long_entirely_above()
    e = Engine()
    e.run(sc.bars)
    five = e.five_min.last_completed
    assert five.low > e.vwap.value, (
        "the fixture did not actually place the bucket entirely above the VWAP")
    assert (e.vwap.value - five.low) < 0.0, "the proximity distance is not negative"
    assert e.position is not None, (
        "the literal rule admits this bucket; the engine refused it, which means the "
        "inequality has been reinterpreted")
    assert e.position.direction == 1


def test_c10_a_five_minute_bucket_entirely_below_the_vwap_still_arms_short():
    sc = Scenario().warmup().arm_short_entirely_below()
    e = Engine()
    e.run(sc.bars)
    five = e.five_min.last_completed
    assert five.high < e.vwap.value
    assert (five.high - e.vwap.value) < 0.0
    assert e.position is not None
    assert e.position.direction == -1


def test_the_proximity_rule_still_refuses_a_bucket_that_is_genuinely_too_far():
    """The characteristic is one-sided: the 6-point limit still binds on the OTHER side.

    A long bucket whose low is seven points BELOW the VWAP gives `VWAP - low = +7 > 6` and is
    refused. So the rule is not vacuous - it only fails to exclude candles on the far side.
    """
    sc = Scenario().warmup().arm_long_entirely_above(shift=-7.5)
    e = Engine()
    e.run(sc.bars)
    five = e.five_min.last_completed
    assert (e.vwap.value - five.low) > FROZEN.context_max_distance
    assert e.position is None, "a bucket seven points away was admitted"


def test_the_engine_uses_the_frozen_inequalities_verbatim():
    """Structural: the source contains the rule as written, not a rewritten one."""
    import inspect

    from quant_brain.strategies.vwap_pullback import engine as eng
    src = inspect.getsource(eng.Engine._context)
    assert "(v - five.low) <= self.spec.context_max_distance" in src
    assert "(five.high - v) <= self.spec.context_max_distance" in src
    assert "abs(" not in src, "an abs() would silently change the characteristic"
