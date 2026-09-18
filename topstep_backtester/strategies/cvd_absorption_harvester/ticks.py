"""Per-trade delta classification and cumulative volume delta. PART 7 and PART 8.

WHAT MAKES THIS CORRECT OR NOT
------------------------------
CVD is the running sum of signed trade sizes, where the sign says which side was the
aggressor. The whole edge the strategy hypothesises rests on that sign being right, and
there are exactly four ways to get it wrong:

    approximate it      sign the bar's volume by its candle direction. Forbidden by PART 2,
                        and the reason ``tick_schema`` gates every run.
    misalign the quote  compare a trade against a quote from after it. AMBIGUITY A2.
    guess a missing one classify a trade with no bid or ask. PART 7 forbids it, so such a
                        trade is recorded UNCLASSIFIABLE and contributes zero.
    leak state          carry yesterday's CVD, or yesterday's previous-delta, into today.

The last one is the subtle one. PART 8 resets CVD to zero at 09:30:00 ET, and this module
resets the previous trade price and previous delta with it - because a zero-tick on the
first trade of the session would otherwise inherit a sign from the previous session. That
inheritance is not a rounding detail; it is overnight information entering an intraday
signal. It is also why AMBIGUITY A6 is unresolved rather than quietly defaulted: after the
reset there IS no previous delta, and the specification does not say what the first
midpoint zero-tick should do.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from zoneinfo import ZoneInfo

from topstep_backtester.strategies.cvd_absorption_harvester.spec import (
    CVD_RESET_ET,
    TIMEZONE,
)

_ET = ZoneInfo(TIMEZONE)
_RESET_TIME = dt.time.fromisoformat(CVD_RESET_ET)


class Classification(str, Enum):
    """How a trade's delta was assigned. Recorded per trade so CVD is auditable."""

    AT_ASK = "AT_ASK"
    AT_BID = "AT_BID"
    INSIDE_UPTICK = "INSIDE_UPTICK"
    INSIDE_DOWNTICK = "INSIDE_DOWNTICK"
    INSIDE_ZEROTICK = "INSIDE_ZEROTICK"
    #: No bid, no ask, or a trade outside the quote. Zero delta, counted, never guessed.
    UNCLASSIFIABLE = "UNCLASSIFIABLE"
    #: A midpoint zero-tick with no previous delta to inherit. AMBIGUITY A6.
    UNDEFINED_FIRST_ZEROTICK = "UNDEFINED_FIRST_ZEROTICK"


class AmbiguousTick(RuntimeError):
    """A tick whose classification depends on an UNRESOLVED ambiguity.

    Raised rather than defaulted. The strategy cannot run until the owner rules on A3/A4
    (locked market) and A6 (first zero-tick), and silently picking a branch here is exactly
    the decision this register exists to prevent.
    """


@dataclass(frozen=True)
class Trade:
    """One trade print with the quote standing at its instant."""

    timestamp: dt.datetime
    price: Decimal
    volume: int
    bid: Decimal | None
    ask: Decimal | None


@dataclass(frozen=True)
class ClassifiedTrade:
    trade: Trade
    delta: int
    classification: Classification

    @property
    def timestamp(self) -> dt.datetime:
        return self.trade.timestamp


@dataclass
class TickDataHandler:
    """Classifies trades and maintains CVD, resetting at 09:30:00 ET.

    ``strict`` is the honest default. With it True, a tick that can only be classified by
    resolving an unresolved ambiguity raises instead of picking a branch. Setting it False
    does NOT invent a classification - it records UNCLASSIFIABLE or
    UNDEFINED_FIRST_ZEROTICK and contributes zero delta - and exists so data-quality
    surveys can count how often each case occurs without the run aborting on the first one.
    """

    strict: bool = True

    cvd: int = 0
    previous_trade_price: Decimal | None = None
    previous_delta: int | None = None
    session_date: dt.date | None = None

    trades_seen: int = 0
    unclassifiable: int = 0
    locked_market_ticks: int = 0
    first_zerotick_events: int = 0
    resets: int = 0
    events: list[str] = field(default_factory=list)

    # -- session handling ------------------------------------------------------------------

    def session_of(self, when: dt.datetime) -> dt.date:
        """The date whose 09:30 reset governs this trade.

        Converted to the venue clock with a real timezone, never a fixed offset, so the
        reset lands at 09:30 local on both sides of a DST transition. A trade before 09:30
        belongs to the PREVIOUS reset epoch - CVD has not restarted yet - which matters for
        the overnight session that precedes the morning window.
        """
        if when.tzinfo is None:
            raise ValueError(
                f"trade timestamp {when!r} is timezone-naive. A naive stamp is an unstated "
                f"assumption about the venue clock, and the 09:30 reset is exactly what it "
                f"gets wrong across DST."
            )
        local = when.astimezone(_ET)
        if local.time() >= _RESET_TIME:
            return local.date()
        return local.date() - dt.timedelta(days=1)

    def reset(self, session: dt.date) -> None:
        """Zero CVD *and* the per-trade state it depends on."""
        self.cvd = 0
        #: Reset with CVD, not separately. A zero-tick on the session's first trade would
        #: otherwise inherit a sign computed from yesterday's flow.
        self.previous_trade_price = None
        self.previous_delta = None
        self.session_date = session
        self.resets += 1
        self.events.append(f"CVD RESET -> 0 for session {session} at {CVD_RESET_ET} ET")

    # -- classification --------------------------------------------------------------------

    def classify(self, trade: Trade) -> ClassifiedTrade:
        """Assign a delta to one trade. PART 7, in the order the specification lists."""
        bid, ask, price = trade.bid, trade.ask, trade.price

        if trade.volume <= 0:
            #: PART 22 lists zero and negative volume as validation items. A print with no
            #: size is not a trade; giving it a sign would add a classification event to CVD
            #: while contributing nothing, which is worse than recording it as bad data.
            return self._unclassifiable(trade, f"non-positive volume {trade.volume}")
        if bid is None or ask is None:
            return self._unclassifiable(trade, "missing bid or ask")
        if bid > ask:
            return self._unclassifiable(trade, f"crossed quote bid {bid} > ask {ask}")

        if bid == ask:
            #: AMBIGUITIES A3 and A4. A trade at a locked market satisfies CASE 1 and CASE 2
            #: at once, and the specification does not order the cases.
            self.locked_market_ticks += 1
            if self.strict:
                raise AmbiguousTick(
                    f"trade at {trade.timestamp.isoformat()} priced {price} on a LOCKED "
                    f"market (bid == ask == {bid}) satisfies PART 7 CASE 1 (at ask, "
                    f"+{trade.volume}) and CASE 2 (at bid, -{trade.volume}) simultaneously. "
                    f"AMBIGUITIES A3/A4 are unresolved; the sign of this delta is the "
                    f"owner's call, not this module's."
                )
            return self._record(trade, 0, Classification.UNCLASSIFIABLE)

        if price == ask:
            return self._record(trade, +trade.volume, Classification.AT_ASK)
        if price == bid:
            return self._record(trade, -trade.volume, Classification.AT_BID)

        if not (bid < price < ask):
            #: Outside the quote. PART 22 forbids forcing it into a classification.
            return self._unclassifiable(
                trade, f"price {price} outside quote [{bid}, {ask}]"
            )

        #: PART 7 CASE 3. Inside the quote, so the tick rule decides, against the PREVIOUS
        #: trade price - which is state from earlier in this session only.
        previous = self.previous_trade_price
        if previous is None:
            #: Nothing to compare against: this is the session's first inside trade.
            return self._first_zerotick(trade)
        if price > previous:
            return self._record(trade, +trade.volume, Classification.INSIDE_UPTICK)
        if price < previous:
            return self._record(trade, -trade.volume, Classification.INSIDE_DOWNTICK)

        #: Zero-tick: inherit the previous delta's SIGN, applied to this trade's size.
        if self.previous_delta is None:
            return self._first_zerotick(trade)
        sign = 1 if self.previous_delta > 0 else -1
        return self._record(trade, sign * trade.volume, Classification.INSIDE_ZEROTICK)

    def _first_zerotick(self, trade: Trade) -> ClassifiedTrade:
        """A midpoint trade with no previous trade price to compare against. AMBIGUITY A6."""
        self.first_zerotick_events += 1
        if self.strict:
            raise AmbiguousTick(
                f"trade at {trade.timestamp.isoformat()} priced {trade.price} is inside the "
                f"quote with no previous trade price in this session, so PART 7 CASE 3 has "
                f"nothing to compare against and 'delta = previous_delta' is undefined. "
                f"AMBIGUITY A6 is unresolved."
            )
        return self._record(trade, 0, Classification.UNDEFINED_FIRST_ZEROTICK)

    def _unclassifiable(self, trade: Trade, why: str) -> ClassifiedTrade:
        self.unclassifiable += 1
        self.events.append(f"UNCLASSIFIABLE {trade.timestamp.isoformat()}: {why}")
        return self._record(trade, 0, Classification.UNCLASSIFIABLE)

    def _record(
        self, trade: Trade, delta: int, classification: Classification
    ) -> ClassifiedTrade:
        return ClassifiedTrade(trade=trade, delta=delta, classification=classification)

    # -- the public entry point --------------------------------------------------------------

    def on_trade(self, trade: Trade) -> ClassifiedTrade:
        """Classify, accumulate, and advance the per-trade state. Call once per trade, in order."""
        session = self.session_of(trade.timestamp)
        if session != self.session_date:
            self.reset(session)

        classified = self.classify(trade)
        self.trades_seen += 1
        self.cvd += classified.delta

        #: The previous trade price advances on EVERY trade, including an unclassifiable one:
        #: a trade happened at that price whether or not its aggressor could be determined.
        self.previous_trade_price = trade.price
        #: The previous DELTA advances only when a sign was actually assigned. Letting a
        #: zero from an unclassifiable tick become the inherited delta would silently turn
        #: the next zero-tick into a zero too.
        if classified.classification not in (
            Classification.UNCLASSIFIABLE,
            Classification.UNDEFINED_FIRST_ZEROTICK,
        ):
            self.previous_delta = classified.delta
        return classified

    def quality(self) -> dict[str, int | float]:
        """Counters a data-quality report needs. PART 22."""
        seen = self.trades_seen or 1
        return {
            "trades_seen": self.trades_seen,
            "unclassifiable": self.unclassifiable,
            "unclassifiable_pct": round(100.0 * self.unclassifiable / seen, 4),
            "locked_market_ticks": self.locked_market_ticks,
            "first_zerotick_events": self.first_zerotick_events,
            "resets": self.resets,
            "cvd": self.cvd,
        }


__all__ = [
    "AmbiguousTick",
    "Classification",
    "ClassifiedTrade",
    "TickDataHandler",
    "Trade",
]
