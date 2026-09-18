"""The strategy governor and its state machine. PART 17, 18 and 19.

TWO THRESHOLDS THAT DO DIFFERENT THINGS
---------------------------------------
    winning-day lock   REALIZED >= +$160        -> cancel working orders, no new setups
    killswitch         REALIZED + UNREALIZED <= -$250 -> flatten NOW, then no new setups

The asymmetry is the whole design. The lock reads realized P&L only, so an open trade
running at +$200 unrealized does not trip it - the day is not won until the money is
banked. The killswitch reads realized plus unrealized, because an account is liquidated on
live equity, not on what has been booked.

Getting that backwards in either direction produces a plausible-looking governor that is
wrong: a lock on live equity would stop the day on a trade that later gave the profit back,
and a killswitch on realized only would let an open position run straight through the floor
without ever triggering.

THE KILLSWITCH IS A SOFT FLOOR, AND THE REPORT MUST SAY SO
----------------------------------------------------------
This class decides WHEN to flatten. It cannot decide at what price, because upstream fills
a market order on the record after the one that submitted it (AMBIGUITY A15). So the
realised loss on a killswitch exit will generally exceed $250. That is a property of any
bar-sequenced simulator and is reported rather than hidden; ``breach_equity`` records the
equity that tripped it so the overshoot is measurable rather than assumed.

WHAT "UNTIL 17:00 ET" MEANS HERE
--------------------------------
17:00 ET is the close of the Globex trading day upstream already enforces, so a lock to
17:00 and a lock to the day roll are the same instant (AMBIGUITY A14). The governor
therefore resets on a new trading day, and ``unlock_at`` is recorded for the ledger rather
than consulted as a separate clock - two clocks that must agree are a defect waiting to
happen.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from topstep_backtester.strategies.cvd_absorption_harvester.spec import (
    GOVERNOR_UNLOCK_ET,
    KILLSWITCH_USD,
    WINNING_DAY_LOCK_USD,
)


class State(str, Enum):
    """PART 19. Three states, and no others are needed."""

    ACTIVE = "ACTIVE"
    HALTED_SUCCESS = "HALTED_SUCCESS"
    HALTED_FAIL = "HALTED_FAIL"


#: The only legal transitions. Anything else raises rather than repairing itself, because a
#: governor that silently re-arms after a halt is the single most expensive bug available
#: here - it would trade a day the rules had already closed.
TRANSITIONS: dict[State, frozenset[State]] = {
    State.ACTIVE: frozenset({State.HALTED_SUCCESS, State.HALTED_FAIL}),
    State.HALTED_SUCCESS: frozenset(),
    State.HALTED_FAIL: frozenset(),
}


class IllegalTransition(RuntimeError):
    """An attempt to leave a terminal state, or to enter one twice."""


#: Why an entry was refused. Strings because a human reads them in the ledger.
OUTSIDE_WINDOW = "outside the 09:45-11:30 ET entry window"
HALTED = "the governor has halted the day"
POSITION_OPEN = "a position is already open"


@dataclass(frozen=True)
class EntryVerdict:
    allowed: bool
    reasons: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return self.allowed


@dataclass(frozen=True)
class Transition:
    at: dt.datetime
    frm: State
    to: State
    reason: str
    realized: Decimal
    unrealized: Decimal

    def as_dict(self) -> dict[str, object]:
        return {
            "at": self.at.isoformat(),
            "from": self.frm.value,
            "to": self.to.value,
            "reason": self.reason,
            "realized": str(self.realized),
            "unrealized": str(self.unrealized),
        }


@dataclass
class Governor:
    """Per-trading-day state. Rolls at the session boundary, never across it."""

    state: State = State.ACTIVE
    realized: Decimal = Decimal(0)
    day: dt.date | None = None
    unlock_at: str = GOVERNOR_UNLOCK_ET

    #: The equity that tripped the killswitch, for measuring the overshoot (A15).
    breach_equity: Decimal | None = None
    trades_today: int = 0
    transitions: list[Transition] = field(default_factory=list)

    # -- the day roll -----------------------------------------------------------------------

    def start_day(self, day: dt.date) -> None:
        self.state = State.ACTIVE
        self.realized = Decimal(0)
        self.day = day
        self.breach_equity = None
        self.trades_today = 0

    @property
    def halted(self) -> bool:
        return self.state is not State.ACTIVE

    # -- the two thresholds ------------------------------------------------------------------

    def winning_day_reached(self) -> bool:
        """REALIZED only. An unrealized gain has not been banked and does not count."""
        return self.realized >= WINNING_DAY_LOCK_USD

    def killswitch_breached(self, unrealized: Decimal) -> bool:
        """REALIZED + UNREALIZED. An account is liquidated on live equity."""
        return (self.realized + unrealized) <= KILLSWITCH_USD

    # -- the state machine -------------------------------------------------------------------

    def _transition(self, to: State, *, at: dt.datetime, reason: str,
                    unrealized: Decimal) -> None:
        if to not in TRANSITIONS[self.state]:
            raise IllegalTransition(
                f"{self.state.value} -> {to.value} is not a legal transition at "
                f"{at.isoformat()}. Legal from {self.state.value}: "
                f"{sorted(s.value for s in TRANSITIONS[self.state]) or 'none (terminal)'}. "
                f"A governor that leaves a terminal state would trade a day the rules had "
                f"already closed."
            )
        self.transitions.append(
            Transition(at=at, frm=self.state, to=to, reason=reason,
                       realized=self.realized, unrealized=unrealized)
        )
        self.state = to

    def on_equity(self, *, at: dt.datetime, unrealized: Decimal) -> State:
        """Evaluate both thresholds on live equity. Call once per record, in order.

        The killswitch is checked FIRST. If both conditions somehow hold on the same record
        the account is in trouble, and treating that as a successful day would be the wrong
        reading of a day that is down $250 on live equity.
        """
        if self.halted:
            return self.state

        if self.killswitch_breached(unrealized):
            self.breach_equity = self.realized + unrealized
            self._transition(
                State.HALTED_FAIL,
                at=at,
                reason=(
                    f"killswitch: realized {self.realized} + unrealized {unrealized} = "
                    f"{self.breach_equity} <= {KILLSWITCH_USD}"
                ),
                unrealized=unrealized,
            )
            return self.state

        if self.winning_day_reached():
            self._transition(
                State.HALTED_SUCCESS,
                at=at,
                reason=f"winning-day lock: realized {self.realized} >= {WINNING_DAY_LOCK_USD}",
                unrealized=unrealized,
            )
        return self.state

    # -- bookkeeping --------------------------------------------------------------------------

    def record_entry(self) -> None:
        self.trades_today += 1

    def record_exit(self, *, net_pnl: Decimal, at: dt.datetime) -> State:
        """Book a closed trade, then re-evaluate the lock now the account is flat."""
        self.realized += net_pnl
        #: Evaluated at zero unrealized because this call happens on the flat side of a
        #: close. The winning-day lock is realized-only, so this is where it normally fires.
        return self.on_equity(at=at, unrealized=Decimal(0))

    # -- the gate -----------------------------------------------------------------------------

    def may_enter(self, *, in_window: bool, position_open: bool) -> EntryVerdict:
        why: list[str] = []
        if not in_window:
            why.append(OUTSIDE_WINDOW)
        if self.halted:
            why.append(HALTED)
        if position_open:
            why.append(POSITION_OPEN)
        return EntryVerdict(not why, tuple(why))

    def summary(self) -> dict[str, object]:
        return {
            "day": None if self.day is None else self.day.isoformat(),
            "state": self.state.value,
            "realized": str(self.realized),
            "trades_today": self.trades_today,
            "breach_equity": None if self.breach_equity is None else str(self.breach_equity),
            "transitions": [t.as_dict() for t in self.transitions],
        }


__all__ = [
    "HALTED",
    "OUTSIDE_WINDOW",
    "POSITION_OPEN",
    "TRANSITIONS",
    "EntryVerdict",
    "Governor",
    "IllegalTransition",
    "State",
    "Transition",
]
