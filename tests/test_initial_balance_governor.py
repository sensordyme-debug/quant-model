"""The daily governor: killswitch, profit cap, trade cap, cutoff, flatten.

The governor is the safety layer and it is authoritative, so each rule is tested at its own
boundary rather than only in the middle of its range.
"""
from __future__ import annotations

import datetime as dt

import pytest

from quant_brain.strategies.initial_balance_reversion.governor import (
    AFTER_CUTOFF,
    BEFORE_IB_COMPLETE,
    HALTED,
    IN_POSITION,
    OUT_OF_REGIME,
    PROFIT_CAP,
    TRADE_CAP,
    Governor,
)
from quant_brain.strategies.initial_balance_reversion.spec import FROZEN

WHEN = dt.datetime(2026, 6, 10, 11, 0, tzinfo=dt.UTC)


def fresh() -> Governor:
    g = Governor(spec=FROZEN)
    g.reset(dt.date(2026, 6, 10))
    return g


def ok(g, **kw):
    base = dict(ib_complete=True, in_regime=True, position_open=False, minute_of_day=660)
    base.update(kw)
    return g.may_enter(WHEN, **base)


# ---- the killswitch boundary ------------------------------------------------------------

@pytest.mark.parametrize("realized,unrealized,breached", [
    (0.0, -799.99, False),
    (0.0, -800.00, True),
    (0.0, -800.01, True),
    (-400.0, -399.99, False),
    (-400.0, -400.00, True),
    (500.0, -1299.99, False),
    (500.0, -1300.00, True),
])
def test_the_killswitch_boundary_is_at_exactly_minus_800(realized, unrealized, breached):
    g = fresh()
    g.realized = realized
    assert g.killswitch_breached(unrealized) is breached


# ---- the profit cap boundary -------------------------------------------------------------

@pytest.mark.parametrize("realized,reached", [
    (1199.99, False), (1200.00, True), (1200.01, True), (0.0, False), (-50.0, False),
])
def test_the_profit_cap_boundary_is_at_exactly_plus_1200(realized, reached):
    g = fresh()
    g.realized = realized
    assert g.profit_cap_reached() is reached


def test_the_profit_cap_blocks_entries_but_does_not_itself_flatten():
    g = fresh()
    g.realized = 1250.0
    v = ok(g)
    assert not v and PROFIT_CAP in v.reasons
    #: nothing in the governor closes a position; that is the engine's job and the
    #: specification is explicit that the cap must not do it
    assert not hasattr(g, "flatten")


def test_the_cap_halts_the_day_only_once_flat():
    g = fresh()
    g.record_exit(net_pnl=1200.0, when=WHEN)
    assert g.halted and "flat" in g.halt_reason


# ---- the trade cap ------------------------------------------------------------------------

def test_the_trade_cap_is_two():
    g = fresh()
    assert ok(g)
    g.record_entry(WHEN)
    assert not g.trade_cap_reached()
    g.record_entry(WHEN)
    assert g.trade_cap_reached()
    v = ok(g)
    assert not v and TRADE_CAP in v.reasons


# ---- the 14:00 cutoff ----------------------------------------------------------------------

@pytest.mark.parametrize("minute,allowed", [
    (13 * 60 + 55, True), (14 * 60 - 1, True), (14 * 60, False), (14 * 60 + 5, False),
])
def test_entries_stop_at_1400_exactly(minute, allowed):
    g = fresh()
    v = ok(g, minute_of_day=minute)
    assert bool(v) is allowed
    if not allowed:
        assert AFTER_CUTOFF in v.reasons


# ---- the other gates -----------------------------------------------------------------------

def test_every_refusal_states_its_reason():
    g = fresh()
    assert BEFORE_IB_COMPLETE in ok(g, ib_complete=False).reasons
    assert OUT_OF_REGIME in ok(g, in_regime=False).reasons
    assert IN_POSITION in ok(g, position_open=True).reasons
    g.halt(WHEN, "manual")
    assert HALTED in ok(g).reasons


def test_an_incomplete_ib_is_reported_without_also_claiming_the_regime_failed():
    g = fresh()
    v = ok(g, ib_complete=False, in_regime=False)
    assert BEFORE_IB_COMPLETE in v.reasons
    assert OUT_OF_REGIME not in v.reasons, "the regime is unknowable before the IB closes"


def test_a_reset_clears_everything_the_previous_day_left():
    g = fresh()
    g.realized = -500.0
    g.record_entry(WHEN)
    g.halt(WHEN, "whatever")
    g.reset(dt.date(2026, 6, 11))
    assert g.realized == 0.0 and g.trades_today == 0
    assert not g.halted and g.halt_reason == ""
    assert g.day == dt.date(2026, 6, 11)
    assert ok(g)


def test_realized_accumulates_across_trades_within_a_day():
    g = fresh()
    g.record_exit(net_pnl=-300.0, when=WHEN)
    g.record_exit(net_pnl=120.0, when=WHEN)
    assert g.realized == pytest.approx(-180.0)
    assert not g.halted
