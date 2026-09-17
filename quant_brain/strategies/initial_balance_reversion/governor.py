"""The daily risk governor. Authoritative, and stricter than the strategy's own rules.

THREE RULES, AND THEY DO DIFFERENT THINGS
-------------------------------------------
    killswitch   realized + unrealized <= -$800   ->  flatten NOW, cancel, halt the day
    profit cap   realized >= +$1,200              ->  no NEW entries; the open trade runs on
    trade cap    2 trades taken                   ->  no new entries

The middle one is the one most easily got wrong. The specification is explicit that reaching
the realized cap must NOT flatten the position that is open - it stops the day from starting
anything else and lets the existing trade finish under its own OCO and time stop. A governor
that liquidated on the cap would book a different trade from the one the strategy placed.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from quant_brain.strategies.initial_balance_reversion.spec import FROZEN, FrozenSpec

#: Why an entry was refused. Strings because they are read by a human in the ledger.
BEFORE_IB_COMPLETE = "the Initial Balance has not closed"
OUT_OF_REGIME = "the IB range is outside 10.00-35.00"
AFTER_CUTOFF = "at or past the 14:00 execution cutoff"
HALTED = "the day is halted"
TRADE_CAP = "the daily trade cap of 2 is reached"
PROFIT_CAP = "the daily realized profit cap is reached"
IN_POSITION = "a position is already open"


@dataclass(frozen=True)
class EntryVerdict:
    allowed: bool
    reasons: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return self.allowed


@dataclass
class Governor:
    """Per-day risk state. Rolls at the session start, never across sessions."""

    spec: FrozenSpec = FROZEN
    realized: float = 0.0
    trades_today: int = 0
    halted: bool = False
    halt_reason: str = ""
    day: dt.date | None = None
    events: list[str] = field(default_factory=list)

    def reset(self, day: dt.date) -> None:
        self.realized = 0.0
        self.trades_today = 0
        self.halted = False
        self.halt_reason = ""
        self.day = day
        self.events.append(f"DAY RESET -> {day}")

    # -- the three rules --------------------------------------------------------------------

    def killswitch_breached(self, unrealized: float) -> bool:
        """Realized plus unrealized, where unrealized is marked at the ADVERSE intrabar
        extreme (AMBIGUITY B6) so a bucket's close cannot hide the excursion that tripped it.
        """
        return (self.realized + unrealized) <= self.spec.daily_loss_killswitch

    def profit_cap_reached(self) -> bool:
        return self.realized >= self.spec.daily_profit_cap

    def trade_cap_reached(self) -> bool:
        return self.trades_today >= self.spec.max_trades_per_day

    # -- the gate ---------------------------------------------------------------------------

    def may_enter(self, when: dt.datetime, *, ib_complete: bool, in_regime: bool,
                  position_open: bool, minute_of_day: int) -> EntryVerdict:
        why: list[str] = []
        if not ib_complete:
            why.append(BEFORE_IB_COMPLETE)
        if ib_complete and not in_regime:
            why.append(OUT_OF_REGIME)
        if minute_of_day >= self.spec.minute_of("execution_cutoff"):
            why.append(AFTER_CUTOFF)
        if self.halted:
            why.append(HALTED)
        if self.trade_cap_reached():
            why.append(TRADE_CAP)
        if self.profit_cap_reached():
            why.append(PROFIT_CAP)
        if position_open:
            why.append(IN_POSITION)
        _ = when
        return EntryVerdict(not why, tuple(why))

    # -- bookkeeping ---------------------------------------------------------------------------

    def halt(self, when: dt.datetime, reason: str) -> None:
        self.halted = True
        self.halt_reason = reason
        self.events.append(f"HALT {when.isoformat()} {reason}")

    def record_entry(self, when: dt.datetime) -> None:
        self.trades_today += 1
        self.events.append(f"ENTRY #{self.trades_today} {when.isoformat()}")

    def record_exit(self, *, net_pnl: float, when: dt.datetime) -> None:
        self.realized += net_pnl
        self.events.append(f"EXIT net {net_pnl:+.2f} realized {self.realized:+.2f}")
        #: the cap halts the day only once the account is FLAT, which is the state this
        #: method is called in - the trade that reached it has just closed.
        if self.profit_cap_reached() and not self.halted:
            self.halt(when, "daily realized profit cap reached and flat")


__all__ = ["AFTER_CUTOFF", "BEFORE_IB_COMPLETE", "EntryVerdict", "Governor", "HALTED",
           "IN_POSITION", "OUT_OF_REGIME", "PROFIT_CAP", "TRADE_CAP"]
