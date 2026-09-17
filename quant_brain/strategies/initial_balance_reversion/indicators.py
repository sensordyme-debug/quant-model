"""The Initial Balance, and the excursion tracker that finds the stop.

TWO OBJECTS, BOTH ONLINE ACCUMULATORS
---------------------------------------
`InitialBalance` is fed completed 5-minute buckets and refuses to answer until the window has
closed. `Excursion` is fed buckets and remembers the extreme of the CURRENT continuous trip
outside the IB. Neither can look forward, because neither holds anything it has not been fed -
causality is a property of the data structure rather than something a test goes looking for.

WHY THE EXCURSION IS NOT "THE DAY'S LOW"
------------------------------------------
The specification is explicit and the distinction decides every stop:

    bar 1   low = Low_IB - 1        excursion opens, extreme = Low_IB - 1
    bar 2   low = Low_IB - 3        extreme = Low_IB - 3
    bar 3   low = Low_IB - 2, close > Low_IB    rejection; E_long = Low_IB - 3

The day may well have traded lower at 09:45 or at 15:00. Neither is E_long. Only the trip that
this rejection ends counts, and it is sealed at the moment of rejection so nothing later can
revise it.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from quant_brain.strategies.vwap_pullback.indicators import Bar, FiveMinuteBar


class IBNotReady(RuntimeError):
    """The Initial Balance was read before its window closed. Raised, never defaulted."""


@dataclass
class InitialBalance:
    """High, low, range and midpoint of 09:30-10:30, sealed when the window ends.

    `complete` flips exactly once, when a bucket starting at or after `end_minute` arrives.
    Until then every accessor raises: a partial IB is not a small error in the midpoint, it is
    a different number, and returning it would put the whole day's target and regime filter on
    data the strategy was not entitled to.
    """

    start_minute: int
    end_minute: int
    high: float = float("-inf")
    low: float = float("inf")
    buckets: int = 0
    complete: bool = False
    _sealed_high: float = float("nan")
    _sealed_low: float = float("nan")

    def update(self, five: FiveMinuteBar, minute_of_start: int) -> None:
        """Absorb one COMPLETED 5-minute bucket, identified by its START minute."""
        if self.complete:
            return
        if minute_of_start >= self.end_minute:
            self.seal()
            return
        if minute_of_start < self.start_minute:
            return                      # pre-open bucket; not part of the IB
        self.high = max(self.high, five.high)
        self.low = min(self.low, five.low)
        self.buckets += 1

    def seal(self) -> None:
        """Freeze the window. Idempotent, and the only way `complete` becomes True.

        Refuses to seal an EMPTY window. A driver that feeds the engine bars from outside
        09:30-10:30 - the anchored session starts at 18:00, and a minute-of-day filter with
        no upper bound keeps those evening bars - would otherwise seal an IB of
        [inf, -inf], compute a range of -inf, fail the regime filter and halt every single
        day. That is a silent zero-trade backtest, which is the failure this repository has
        been bitten by before, so it raises instead.
        """
        if self.complete:
            return
        if self.buckets == 0:
            raise IBNotReady(
                "the Initial Balance window closed having seen no bars at all. The engine "
                "was fed nothing between 09:30 and 10:30 - check the driver's session "
                "filter, which on an 18:00-anchored session must bound the minute of day at "
                "BOTH ends.")
        self._sealed_high, self._sealed_low = self.high, self.low
        self.complete = True

    def _check(self) -> None:
        if not self.complete:
            raise IBNotReady(
                "the Initial Balance was read before 10:30. It is not a partial estimate of "
                "the final value; it is a different number, and every target and regime "
                "decision built on it would be wrong.")

    @property
    def ib_high(self) -> float:
        self._check()
        return self._sealed_high

    @property
    def ib_low(self) -> float:
        self._check()
        return self._sealed_low

    @property
    def ib_range(self) -> float:
        self._check()
        return self._sealed_high - self._sealed_low

    @property
    def midpoint(self) -> float:
        self._check()
        return (self._sealed_high + self._sealed_low) / 2.0

    def in_regime(self, lo: float, hi: float) -> bool:
        """Inclusive on both ends, exactly as written."""
        return lo <= self.ib_range <= hi


#: Which side of the IB the current trip is on. `NONE` means price is inside.
BELOW, NONE, ABOVE = -1, 0, 1


@dataclass
class Excursion:
    """The CURRENT continuous trip outside the Initial Balance, and its extreme.

    A trip opens the first time a bucket trades outside the IB, deepens while it stays out,
    and is CONSUMED by the rejection that ends it. `consumed` is what stops one breakout from
    producing two entries: the tracker will not offer the same trip twice, and a new entry
    needs price to leave the IB again.
    """

    side: int = NONE
    extreme: float = float("nan")
    buckets: int = 0
    consumed: bool = False

    def update(self, five: FiveMinuteBar, ib_high: float, ib_low: float) -> None:
        """Absorb one completed bucket and update the trip.

        Order matters and follows the specification: the trip is extended by what the bucket
        TRADED (its high/low), and ended by where it CLOSED. A bucket can therefore both open
        a trip and reject it - AMBIGUITY B3 - which the literal reading permits.
        """
        went_below = five.low < ib_low
        went_above = five.high > ib_high

        if self.side == NONE:
            if went_below and went_above:
                #: an outside bar that traded beyond BOTH edges. The specification names no
                #: precedence, so neither side is claimed and the trip does not open.
                return
            if went_below:
                self.side, self.extreme, self.buckets, self.consumed = BELOW, five.low, 1, False
                return
            if went_above:
                self.side, self.extreme, self.buckets, self.consumed = ABOVE, five.high, 1, False
                return
            return

        if self.side == BELOW:
            if went_below:
                self.extreme = min(self.extreme, five.low)
                self.buckets += 1
            if five.close > ib_low:
                #: closed back inside: the trip is over. It stays readable for exactly this
                #: bucket so the engine can act on it, then resets on the next one.
                return
            return

        if went_above:
            self.extreme = max(self.extreme, five.high)
            self.buckets += 1
        return

    def rejected(self, five: FiveMinuteBar, ib_high: float, ib_low: float) -> bool:
        """True when THIS bucket closes back inside and the trip has not been traded."""
        if self.side == NONE or self.consumed:
            return False
        if self.side == BELOW:
            return five.close > ib_low
        return five.close < ib_high

    def close_trip(self) -> None:
        """Reset after a bucket that closed back inside, traded or not."""
        self.side, self.extreme, self.buckets, self.consumed = NONE, float("nan"), 0, False

    def consume(self) -> None:
        """Mark the trip as traded. A second entry needs a NEW trip (AMBIGUITY B7)."""
        self.consumed = True


def bucket_start_minute(five: FiveMinuteBar, tz) -> int:
    """Minutes past midnight on the venue clock, of the bucket's FIRST minute."""
    local = five.start.astimezone(tz)
    return local.hour * 60 + local.minute


def bucket_close_time(five: FiveMinuteBar, bar_minutes: int) -> dt.datetime:
    """The instant the bucket completes: its last minute's start, plus one minute.

    `FiveMinuteBar.end` is the START stamp of the final one-minute bar in the bucket, so the
    bucket is complete sixty seconds later. Every decision this strategy takes is stamped
    here, and it is the clock the 60-minute time stop counts from.
    """
    _ = bar_minutes
    return five.end + dt.timedelta(minutes=1)


__all__ = ["ABOVE", "BELOW", "Bar", "Excursion", "IBNotReady", "InitialBalance", "NONE",
           "bucket_close_time", "bucket_start_minute"]
