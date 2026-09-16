"""The intraday governor: the layer that decides whether the strategy may trade at all.

WHY THIS IS NOT THE TOPSTEP TWIN
----------------------------------
`markets.futures_cme.twin` enforces the PROP FIRM's rules on a settled sequence of sessions:
the trailing maximum loss limit, the optional daily limit, the profit target, the payout
clock. It consumes one number per day plus a path, and it answers "what happened to the
account".

This answers a different and earlier question - "may the strategy open a position right now" -
and it answers it INSIDE the session, bar by bar, against the owner's own limits, which are
stricter than Topstep's and are not the same rules:

    killswitch   realized + unrealised <= -$800  ->  flatten, cancel, halt until 18:00
    profit cap   realized >= +$1,200             ->  no NEW entries; the open one is managed
    trade cap    4 entries per trading day
    breaker      2 consecutive NET losses        ->  45 minutes of cooldown
    hard flat    15:45 ET, which is 25 minutes BEFORE Topstep's mandatory 16:10

The two layers are complementary and neither is derived from the other. CONFLICT C5.

THE KILLSWITCH IS MARK-TO-MARKET, AND THAT IS THE WHOLE POINT
---------------------------------------------------------------
A killswitch that only reads REALIZED P&L cannot fire while a position is open, which is the
only time it matters. Realized -$500 with -$300 of open loss is -$800 of account damage, and
the account does not care which half is booked. `AMBIGUITY A2` records the remaining choice -
whether the open half is read at the bar's close or at its adverse extreme - and both are
implemented, because a limit that only looks at closes misses the move that breaches between
them.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from quant_brain.strategies.vwap_pullback.indicators import minute_of_day, trading_day
from quant_brain.strategies.vwap_pullback.spec import FROZEN, FrozenSpec

#: Every reason an entry can be refused. Strings rather than an enum so a verdict can be read
#: in a test failure without a lookup, and so a new reason cannot silently collide with one of
#: the existing values.
BEFORE_WINDOW = "before the monitoring window opens"
AFTER_CUTOFF = "past the last-entry time"
AFTER_FLATTEN = "past the hard flatten"
HALTED = "the day is halted"
COOLDOWN = "in the consecutive-loss cooldown"
TRADE_CAP = "the daily trade cap is reached"
PROFIT_CAP = "the daily profit cap is reached"
IN_POSITION = "a position is already open"


@dataclass(frozen=True)
class EntryVerdict:
    """Whether an entry is permitted, and every reason it is not. Never a bare bool.

    All reasons are collected rather than short-circuited: a test that blocks on the trade cap
    should be able to see that the cooldown was also active, and a bool cannot say that.
    """

    allowed: bool
    reasons: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return self.allowed


@dataclass
class Governor:
    """Per-trading-day state. Rolls at the 18:00 anchor, never at midnight (AMBIGUITY A13)."""

    spec: FrozenSpec = FROZEN
    realized: float = 0.0
    trades_today: int = 0
    consecutive_losses: int = 0
    cooldown_until: dt.datetime | None = None
    halted: bool = False
    halt_reason: str = ""
    day: dt.date | None = None
    events: list[str] = field(default_factory=list)

    # -- the day ----------------------------------------------------------------------------

    def observe(self, when: dt.datetime) -> bool:
        """Note the time. Returns True when this bar opened a NEW trading day.

        The halt is released here and nowhere else, which is what makes "remain halted until
        18:00" true by construction rather than by a second check somewhere.
        """
        day = trading_day(when, self.spec.anchor_minute())
        if self.day is None:
            self.day = day
            return False
        if day == self.day:
            return False
        self.reset(day)
        return True

    def reset(self, day: dt.date | None = None) -> None:
        self.realized = 0.0
        self.trades_today = 0
        self.consecutive_losses = 0
        self.cooldown_until = None
        self.halted = False
        self.halt_reason = ""
        self.day = day
        self.events.append(f"DAY RESET -> {day}")

    # -- the windows ------------------------------------------------------------------------

    def in_entry_window(self, when: dt.datetime) -> tuple[bool, tuple[str, ...]]:
        """The 09:45 .. 15:30 window, on the venue clock, DST handled by the conversion."""
        m = minute_of_day(when)
        reasons: list[str] = []
        if m < self.spec.minute_of("monitor_start"):
            reasons.append(BEFORE_WINDOW)
        cutoff = self.spec.minute_of("last_entry")
        # AMBIGUITY A3: a bar stamped exactly at the cutoff is AT it, not after it.
        if (m > cutoff) if self.spec.last_entry_inclusive else (m >= cutoff):
            reasons.append(AFTER_CUTOFF)
        if m >= self.spec.minute_of("hard_flatten"):
            reasons.append(AFTER_FLATTEN)
        return not reasons, tuple(reasons)

    def must_hard_flatten(self, when: dt.datetime) -> bool:
        """True from the 15:45 bar onward. 15:44 is normal operation; 15:45 is not."""
        return minute_of_day(when) >= self.spec.minute_of("hard_flatten")

    # -- the limits -------------------------------------------------------------------------

    def killswitch_breached(self, unrealized: float) -> bool:
        """realized + unrealised at or below the frozen limit. `<=`, so -800.00 fires."""
        return (self.realized + unrealized) <= self.spec.daily_loss_killswitch

    def halt(self, when: dt.datetime, reason: str) -> None:
        self.halted = True
        self.halt_reason = reason
        self.events.append(f"HALT {when.isoformat()} {reason}")

    def may_enter(self, when: dt.datetime, *, position_open: bool) -> EntryVerdict:
        """Every gate, evaluated together."""
        ok, reasons = self.in_entry_window(when)
        out = list(reasons)
        if self.halted:
            out.append(HALTED)
        if position_open:
            out.append(IN_POSITION)
        if self.cooldown_until is not None and when < self.cooldown_until:
            out.append(COOLDOWN)
        if self.trades_today >= self.spec.max_trades_per_day:
            out.append(TRADE_CAP)
        # `>=`: at exactly +1,200 new entries stop. The OPEN position is not touched - the
        # profit cap is an entry gate, not a flatten instruction.
        if self.realized >= self.spec.daily_profit_cap:
            out.append(PROFIT_CAP)
        _ = ok
        return EntryVerdict(allowed=not out, reasons=tuple(out))

    # -- bookkeeping ------------------------------------------------------------------------

    def record_entry(self, when: dt.datetime) -> None:
        self.trades_today += 1
        self.events.append(f"ENTRY #{self.trades_today} {when.isoformat()}")

    def record_exit(self, *, net_pnl: float, when: dt.datetime) -> None:
        """Book a closed trade and update the consecutive-loss streak.

        A SCRATCH (net exactly zero) neither increments nor resets the streak. The frozen
        brief is explicit that the count must not be reset "merely because a position was
        closed for a non-loss/non-win state", and a scratch is exactly that state.
        """
        self.realized += net_pnl
        if net_pnl < 0:
            self.consecutive_losses += 1
        elif net_pnl > 0:
            self.consecutive_losses = 0
        if self.consecutive_losses >= self.spec.consecutive_losses_for_cooldown:
            # AMBIGUITY A9: measured from the EXIT of the losing trade.
            self.cooldown_until = when + dt.timedelta(minutes=self.spec.cooldown_minutes)
            self.consecutive_losses = 0
            self.events.append(
                f"COOLDOWN until {self.cooldown_until.isoformat()} after "
                f"{self.spec.consecutive_losses_for_cooldown} consecutive losses")
        self.events.append(f"EXIT net {net_pnl:+.2f} realized {self.realized:+.2f} "
                           f"streak {self.consecutive_losses}")

    def in_cooldown(self, when: dt.datetime) -> bool:
        return self.cooldown_until is not None and when < self.cooldown_until


__all__ = ["AFTER_CUTOFF", "AFTER_FLATTEN", "BEFORE_WINDOW", "COOLDOWN", "EntryVerdict",
           "Governor", "HALTED", "IN_POSITION", "PROFIT_CAP", "TRADE_CAP"]
