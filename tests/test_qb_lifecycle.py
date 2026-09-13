"""Session and order state machines: illegal transitions raise, READY needs everything."""
from __future__ import annotations

import dataclasses

import pytest

from quant_brain.core.lifecycle import (
    ORDER_TRANSITIONS,
    SESSION_TRANSITIONS,
    IllegalTransition,
    OrderMachine,
    OrderState,
    Readiness,
    SessionMachine,
    SessionState,
)

ALL_READY = Readiness(**{f.name: True for f in dataclasses.fields(Readiness)})


# ---------------------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------------------

def test_only_ready_may_trade():
    assert [s for s in SessionState if s.may_trade] == [SessionState.READY]


def test_authenticated_cannot_jump_to_ready():
    m = SessionMachine()
    m.transition(SessionState.AUTHENTICATING)
    m.transition(SessionState.AUTHENTICATED)
    with pytest.raises(IllegalTransition, match="authenticated -> ready"):
        m.transition(SessionState.READY, readiness=ALL_READY)
    assert m.state is SessionState.AUTHENTICATED and not m.may_trade


def test_ready_requires_a_complete_readiness_and_names_what_is_missing():
    m = SessionMachine()
    m.transition(SessionState.AUTHENTICATING)
    m.transition(SessionState.AUTHENTICATED)
    m.transition(SessionState.RECONCILING)
    with pytest.raises(IllegalTransition, match="requires a Readiness"):
        m.transition(SessionState.READY)
    partial = dataclasses.replace(ALL_READY, protection_verified=False, explicitly_enabled=False)
    with pytest.raises(IllegalTransition) as e:
        m.transition(SessionState.READY, readiness=partial)
    assert "protection_verified" in str(e.value) and "explicitly_enabled" in str(e.value)
    assert m.state is SessionState.RECONCILING
    m.transition(SessionState.READY, readiness=ALL_READY)
    assert m.may_trade


def test_every_readiness_field_defaults_false_so_forgetting_one_blocks():
    r = Readiness()
    assert not r.complete and len(r.missing()) == 13
    for f in dataclasses.fields(Readiness):
        one_off = dataclasses.replace(ALL_READY, **{f.name: False})
        assert one_off.missing() == [f.name]


def test_halt_is_always_legal_and_terminal():
    for start in SessionState:
        m = SessionMachine(state=start)
        m.halt("test")
        assert m.state is SessionState.HALTED
        assert SESSION_TRANSITIONS[SessionState.HALTED] == frozenset()
        with pytest.raises(IllegalTransition):
            m.transition(SessionState.AUTHENTICATING)


def test_session_history_records_every_step_with_note():
    m = SessionMachine()
    m.transition(SessionState.AUTHENTICATING, note="loginKey")
    m.halt("token refused")
    assert [s for _, s, _ in m.history] == [SessionState.AUTHENTICATING, SessionState.HALTED]
    assert m.halt_reason == "token refused"


def test_session_table_is_closed_over_the_enum():
    assert set(SESSION_TRANSITIONS) == set(SessionState)


# ---------------------------------------------------------------------------------------
# Order
# ---------------------------------------------------------------------------------------

def test_order_table_is_closed_and_terminals_have_no_exits():
    assert set(ORDER_TRANSITIONS) == set(OrderState)
    for s in OrderState:
        if s.is_terminal:
            assert ORDER_TRANSITIONS[s] == frozenset(), s


def test_order_needs_an_intent_id():
    with pytest.raises(ValueError, match="intent_id"):
        OrderMachine(intent_id="")


@pytest.mark.parametrize("path", [
    [OrderState.SUBMITTED],                                      # skip risk
    [OrderState.RISK_CHECK, OrderState.SUBMITTED],               # skip approval
    [OrderState.RISK_CHECK, OrderState.APPROVED, OrderState.PROTECTED],   # protected w/o fill
    [OrderState.RISK_CHECK, OrderState.APPROVED, OrderState.FILLED],      # filled w/o submit
    [OrderState.RISK_CHECK, OrderState.REJECTED, OrderState.APPROVED],    # resurrect a rejection
])
def test_forbidden_paths_raise_at_the_first_illegal_step(path):
    m = OrderMachine(intent_id="abc", requested_qty=1)
    with pytest.raises(IllegalTransition):
        for s in path:
            m.transition(s)


def test_the_happy_path_and_its_history():
    m = OrderMachine(intent_id="abc", requested_qty=2)
    for s in (OrderState.RISK_CHECK, OrderState.APPROVED, OrderState.SUBMITTED,
              OrderState.ACKNOWLEDGED):
        m.transition(s)
    assert m.fill(1) is OrderState.PARTIALLY_FILLED and m.remaining == 1
    assert m.fill(1) is OrderState.FILLED and m.remaining == 0
    m.transition(OrderState.PROTECTED, note="stop 12345 acked")
    m.transition(OrderState.CLOSING)
    m.transition(OrderState.CLOSED)
    assert m.state.is_terminal
    assert [s for _, s, _ in m.history][-3:] == [OrderState.PROTECTED, OrderState.CLOSING,
                                                  OrderState.CLOSED]


def test_overfill_is_an_error_not_a_bigger_position():
    m = OrderMachine(intent_id="abc", requested_qty=1)
    for s in (OrderState.RISK_CHECK, OrderState.APPROVED, OrderState.SUBMITTED):
        m.transition(s)
    assert m.fill(2) is OrderState.ERROR
    assert "overfill" in m.history[-1][2]


def test_fill_before_ack_is_legal_because_venues_do_that():
    m = OrderMachine(intent_id="abc", requested_qty=1)
    for s in (OrderState.RISK_CHECK, OrderState.APPROVED, OrderState.SUBMITTED):
        m.transition(s)
    assert m.fill(1) is OrderState.FILLED


def test_zero_or_negative_fill_is_refused():
    m = OrderMachine(intent_id="abc", requested_qty=1)
    for s in (OrderState.RISK_CHECK, OrderState.APPROVED, OrderState.SUBMITTED):
        m.transition(s)
    with pytest.raises(ValueError):
        m.fill(0)


def test_unprotected_can_become_protected_but_protected_can_lapse_too():
    m = OrderMachine(intent_id="abc", requested_qty=1)
    for s in (OrderState.RISK_CHECK, OrderState.APPROVED, OrderState.SUBMITTED):
        m.transition(s)
    m.fill(1)
    m.transition(OrderState.UNPROTECTED, note="no stop working")
    m.transition(OrderState.PROTECTED, note="stop acked")
    m.transition(OrderState.UNPROTECTED, note="stop cancelled by venue")
    assert m.state.has_exposure
