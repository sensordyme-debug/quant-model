"""Deterministic state machines for a trading session and for each order.

Phase 7 of the master directive. Two machines, one rule each way:

    SessionMachine   a connection may only transition along `SESSION_TRANSITIONS`, and it may
                     only reach READY when EVERY precondition in `Readiness` is true.
    OrderMachine     an order may only transition along `ORDER_TRANSITIONS`, and every
                     transition is recorded with a timestamp and a note.

AUTHENTICATED IS NOT READY
--------------------------
The directive states it and the ProjectX adapter already enforces it at the connection level;
this module makes it a property of the whole session. Between AUTHENTICATED and READY sits
RECONCILING, and READY requires thirteen things to be simultaneously true - connection
verified, account identified, market data healthy, clock synchronised, session valid, venue
rules loaded, local state reconciled, broker state reconciled, no unexplained orders, no
unexplained positions, risk budget computed, protection verified, and an explicit enable. A
`Readiness` with any of them False cannot produce READY; the machine raises and names what is
missing.

WHY AN ILLEGAL TRANSITION RAISES
--------------------------------
A state machine that logs an illegal transition and proceeds is a diagram, not a machine. The
transitions that matter most are the ones that must NOT happen - SUBMITTED without APPROVED,
PROTECTED without FILLED, READY without RECONCILING - and the only way to make them not happen
is to make them impossible.
"""
from __future__ import annotations

import datetime as dt
import enum
from dataclasses import dataclass, field


class IllegalTransition(RuntimeError):
    """The machine was asked to do something its table does not permit."""


# =====================================================================================
# SESSION
# =====================================================================================

class SessionState(str, enum.Enum):
    DISCONNECTED = "disconnected"
    AUTHENTICATING = "authenticating"
    AUTHENTICATED = "authenticated"
    RECONCILING = "reconciling"
    READY = "ready"
    HALTED = "halted"

    @property
    def may_trade(self) -> bool:
        """Exactly one state. Not AUTHENTICATED, not RECONCILING."""
        return self is SessionState.READY


SESSION_TRANSITIONS: dict[SessionState, frozenset[SessionState]] = {
    SessionState.DISCONNECTED: frozenset({SessionState.AUTHENTICATING}),
    SessionState.AUTHENTICATING: frozenset({SessionState.AUTHENTICATED, SessionState.HALTED,
                                            SessionState.DISCONNECTED}),
    SessionState.AUTHENTICATED: frozenset({SessionState.RECONCILING, SessionState.HALTED,
                                           SessionState.DISCONNECTED}),
    SessionState.RECONCILING: frozenset({SessionState.READY, SessionState.HALTED,
                                         SessionState.AUTHENTICATED}),
    SessionState.READY: frozenset({SessionState.RECONCILING, SessionState.HALTED,
                                   SessionState.DISCONNECTED}),
    # HALTED is terminal for the process. A person restarts it.
    SessionState.HALTED: frozenset(),
}


@dataclass(frozen=True)
class Readiness:
    """The thirteen things that must all be true before trading is legal.

    Every field defaults to False. A caller has to assert each one, and the machine refuses
    READY while any is missing - so forgetting to check something is the same as it having
    failed, which is the correct default for a precondition.
    """

    connection_verified: bool = False
    account_identified: bool = False
    market_data_healthy: bool = False
    clock_synchronized: bool = False
    session_valid: bool = False
    venue_rules_loaded: bool = False
    local_state_reconciled: bool = False
    broker_state_reconciled: bool = False
    no_unexplained_orders: bool = False
    no_unexplained_positions: bool = False
    risk_budget_computed: bool = False
    protection_verified: bool = False
    explicitly_enabled: bool = False

    def missing(self) -> list[str]:
        return [k for k, v in self.__dict__.items() if not v]

    @property
    def complete(self) -> bool:
        return not self.missing()


@dataclass
class SessionMachine:
    """A trading session's state, with the full transition history."""

    state: SessionState = SessionState.DISCONNECTED
    history: list[tuple[dt.datetime, SessionState, str]] = field(default_factory=list)
    halt_reason: str = ""

    def transition(self, to: SessionState, *, note: str = "",
                   readiness: Readiness | None = None) -> SessionState:
        if to not in SESSION_TRANSITIONS[self.state]:
            raise IllegalTransition(
                f"session {self.state.value} -> {to.value} is not permitted; allowed: "
                f"{sorted(s.value for s in SESSION_TRANSITIONS[self.state])}")
        if to is SessionState.READY:
            if readiness is None:
                raise IllegalTransition(
                    "READY requires a Readiness; it cannot be entered on assertion")
            if not readiness.complete:
                raise IllegalTransition(
                    f"READY refused; missing: {', '.join(readiness.missing())}")
        if to is SessionState.HALTED:
            self.halt_reason = note or "halted"
        self.history.append((dt.datetime.now(dt.UTC), to, note))
        self.state = to
        return self.state

    def halt(self, reason: str) -> SessionState:
        """Always legal from any non-terminal state; the one transition that never refuses."""
        if self.state is SessionState.HALTED:
            return self.state
        self.halt_reason = reason
        self.history.append((dt.datetime.now(dt.UTC), SessionState.HALTED, reason))
        self.state = SessionState.HALTED
        return self.state

    @property
    def may_trade(self) -> bool:
        return self.state.may_trade


# =====================================================================================
# ORDER
# =====================================================================================

class OrderState(str, enum.Enum):
    INTENT_CREATED = "intent_created"
    RISK_CHECK = "risk_check"
    APPROVED = "approved"
    REJECTED = "rejected"                # by risk, before submission
    SUBMITTED = "submitted"              # sent to the venue; NOT yet acknowledged
    ACKNOWLEDGED = "acknowledged"        # the venue has it
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    #: A filled position with a VERIFIED protective order. Not "a stop was sent".
    PROTECTED = "protected"
    #: A filled position with no verified protection. The dangerous state, made explicit.
    UNPROTECTED = "unprotected"
    CLOSING = "closing"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    ERROR = "error"

    @property
    def is_terminal(self) -> bool:
        return self in {OrderState.REJECTED, OrderState.CLOSED, OrderState.CANCELLED,
                        OrderState.ERROR}

    @property
    def has_exposure(self) -> bool:
        return self in {OrderState.PARTIALLY_FILLED, OrderState.FILLED, OrderState.PROTECTED,
                        OrderState.UNPROTECTED, OrderState.CLOSING}


ORDER_TRANSITIONS: dict[OrderState, frozenset[OrderState]] = {
    OrderState.INTENT_CREATED: frozenset({OrderState.RISK_CHECK}),
    OrderState.RISK_CHECK: frozenset({OrderState.APPROVED, OrderState.REJECTED}),
    OrderState.APPROVED: frozenset({OrderState.SUBMITTED, OrderState.CANCELLED}),
    OrderState.SUBMITTED: frozenset({OrderState.ACKNOWLEDGED, OrderState.ERROR,
                                     OrderState.CANCELLED,
                                     # a venue can fill before it acknowledges
                                     OrderState.PARTIALLY_FILLED, OrderState.FILLED}),
    OrderState.ACKNOWLEDGED: frozenset({OrderState.PARTIALLY_FILLED, OrderState.FILLED,
                                        OrderState.CANCELLED, OrderState.ERROR}),
    OrderState.PARTIALLY_FILLED: frozenset({OrderState.FILLED, OrderState.PROTECTED,
                                            OrderState.UNPROTECTED, OrderState.CLOSING,
                                            OrderState.CANCELLED, OrderState.ERROR}),
    OrderState.FILLED: frozenset({OrderState.PROTECTED, OrderState.UNPROTECTED,
                                  OrderState.CLOSING, OrderState.ERROR}),
    OrderState.PROTECTED: frozenset({OrderState.UNPROTECTED, OrderState.CLOSING,
                                     OrderState.CLOSED, OrderState.ERROR}),
    OrderState.UNPROTECTED: frozenset({OrderState.PROTECTED, OrderState.CLOSING,
                                       OrderState.ERROR}),
    OrderState.CLOSING: frozenset({OrderState.CLOSED, OrderState.ERROR}),
    OrderState.REJECTED: frozenset(),
    OrderState.CLOSED: frozenset(),
    OrderState.CANCELLED: frozenset(),
    OrderState.ERROR: frozenset(),
}


@dataclass
class OrderMachine:
    """One order's life, with every step recorded.

    `intent_id` is the deterministic identity from `core/idempotency.py`; it is required so
    that a machine can be recovered after a restart and matched to what the venue reports.
    """

    intent_id: str
    state: OrderState = OrderState.INTENT_CREATED
    history: list[tuple[dt.datetime, OrderState, str]] = field(default_factory=list)
    filled_qty: float = 0.0
    requested_qty: float = 0.0

    def __post_init__(self) -> None:
        if not self.intent_id:
            raise ValueError("an order needs a deterministic intent_id; see core/idempotency")
        if not self.history:
            self.history.append((dt.datetime.now(dt.UTC), self.state, "created"))

    def transition(self, to: OrderState, *, note: str = "") -> OrderState:
        if to not in ORDER_TRANSITIONS[self.state]:
            raise IllegalTransition(
                f"order {self.intent_id}: {self.state.value} -> {to.value} is not permitted; "
                f"allowed: {sorted(s.value for s in ORDER_TRANSITIONS[self.state])}")
        self.history.append((dt.datetime.now(dt.UTC), to, note))
        self.state = to
        return self.state

    def fill(self, qty: float, *, note: str = "") -> OrderState:
        """Record a fill and move to PARTIALLY_FILLED or FILLED as the arithmetic says."""
        if qty <= 0:
            raise ValueError(f"a fill of {qty} is not a fill")
        self.filled_qty += qty
        if self.requested_qty and self.filled_qty > self.requested_qty + 1e-9:
            # More filled than asked for is a venue-side fault, not something to absorb.
            return self.transition(OrderState.ERROR, note=(
                f"overfill: {self.filled_qty:g} filled against {self.requested_qty:g} "
                f"requested {note}".strip()))
        complete = self.requested_qty and self.filled_qty >= self.requested_qty - 1e-9
        return self.transition(OrderState.FILLED if complete else OrderState.PARTIALLY_FILLED,
                               note=note or f"filled {qty:g}")

    @property
    def remaining(self) -> float:
        return max(0.0, self.requested_qty - self.filled_qty)

    def describe(self) -> str:
        return (f"{self.intent_id} {self.state.value} "
                f"{self.filled_qty:g}/{self.requested_qty:g} "
                f"({len(self.history)} transitions)")
