"""Minute aggregation, swing memory and the divergence detector. PART 9 to PART 13.

THE CAUSALITY RULES, AND WHY EACH IS A SEPARATE GUARD
-----------------------------------------------------
This is where a divergence strategy leaks the future if it is going to. Three distinct
mistakes, each cheap to make and each fatal:

1. THE LOOKBACK MUST EXCLUDE BAR T. PART 10 is explicit: the window is
   Low[T-15]..Low[T-1]. Including bar T makes "Low[T] <= min(window)" trivially true of
   every bar that happens to be the lowest of sixteen, and the signal stops meaning
   anything. ``_window`` slices the closed bars only and never sees the bar being judged.

2. SWING MEMORY MUST NOT BE CONFIRMED BY LATER BARS. The usual way to find swing lows is
   to wait for price to turn back up and then mark the low - which requires bars that come
   AFTER the low. PART 11 instead defines a swing as a bar that is the extreme of its own
   trailing window, decided at that bar's close with the CVD of that same close. No later
   bar is consulted, ever. That is why ``observe`` is called once per completed bar, in
   order, and takes no future argument: it structurally cannot look forward.

3. CVD MUST BE SAMPLED AT THE EXACT BAR CLOSE. PART 9. The CVD stored with a swing is the
   value after the last trade of that bar and before the first trade of the next. The
   aggregator therefore seals a bar and captures CVD in the same operation, rather than
   letting a caller read CVD later and pair it with an earlier bar.

The ordering inside ``observe`` is the part worth reading twice: the signal is evaluated
against the swing memory as it stood BEFORE this bar, and only then is the memory updated.
Updating first would compare bar T against a swing established by bar T itself, and
condition 2 (Low[T] < Prev_Low_Price) would be unsatisfiable rather than merely rare.
"""
from __future__ import annotations

import datetime as dt
from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal

from topstep_backtester.strategies.cvd_absorption_harvester.spec import LOOKBACK_BARS


@dataclass(frozen=True)
class MinuteBar:
    """A completed 1-minute bar with CVD sampled at its exact close."""

    start: dt.datetime
    end: dt.datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    cvd_at_close: int
    trades: int


@dataclass
class MinuteAggregator:
    """Builds 1-minute bars from classified trades, sealing CVD at each close.

    Bars are emitted only when a trade arrives in a LATER minute, so a bar is never handed
    out before the minute that contains it is over. A partially formed minute is not a bar
    and is never shown to the detector.
    """

    _open: Decimal | None = None
    _high: Decimal | None = None
    _low: Decimal | None = None
    _close: Decimal | None = None
    _volume: int = 0
    _trades: int = 0
    _minute: dt.datetime | None = None
    #: CVD as of the most recent trade folded in. When the minute seals this is the value at
    #: its exact close (PART 9) rather than a value read after the boundary had passed.
    _pending_cvd: int = 0

    def _floor(self, when: dt.datetime) -> dt.datetime:
        return when.replace(second=0, microsecond=0)

    def add(self, *, when: dt.datetime, price: Decimal, volume: int, cvd: int
            ) -> MinuteBar | None:
        """Fold one trade in. Returns the PREVIOUS bar if this trade closed it."""
        minute = self._floor(when)
        completed: MinuteBar | None = None

        if self._minute is not None and minute != self._minute:
            completed = self._seal(cvd_at_close=self._pending_cvd)
        if self._minute is None or completed is not None:
            self._minute = minute
            self._open = self._high = self._low = self._close = price
            self._volume = 0
            self._trades = 0

        assert self._high is not None and self._low is not None
        self._high = max(self._high, price)
        self._low = min(self._low, price)
        self._close = price
        self._volume += volume
        self._trades += 1
        #: CVD as of THIS trade. When the minute later seals, this is the value at its exact
        #: close - the last trade inside the bar - and not a value read after the boundary.
        self._pending_cvd = cvd
        return completed

    def _seal(self, *, cvd_at_close: int) -> MinuteBar:
        assert self._minute is not None
        assert self._open is not None and self._high is not None
        assert self._low is not None and self._close is not None
        bar = MinuteBar(
            start=self._minute,
            end=self._minute + dt.timedelta(minutes=1),
            open=self._open,
            high=self._high,
            low=self._low,
            close=self._close,
            volume=self._volume,
            cvd_at_close=cvd_at_close,
            trades=self._trades,
        )
        return bar

    def flush(self) -> MinuteBar | None:
        """Seal whatever minute is open. For end-of-session only."""
        if self._minute is None:
            return None
        bar = self._seal(cvd_at_close=self._pending_cvd)
        self._minute = None
        return bar


@dataclass(frozen=True)
class Swing:
    """A swing extreme, decided at its own bar's close."""

    price: Decimal
    cvd: int
    at: dt.datetime


@dataclass(frozen=True)
class Signal:
    """A divergence signal, with every comparand recorded for the trade ledger."""

    direction: int  # +1 long, -1 short
    bar: MinuteBar
    prev_swing_price: Decimal
    prev_swing_cvd: int
    #: Which of the four PART 12/13 conditions were satisfied. All four, or no signal.
    conditions: tuple[str, ...]

    @property
    def side(self) -> str:
        return "long" if self.direction > 0 else "short"


@dataclass
class DivergenceDetector:
    """Swing memory plus the four-condition entry test. One call per completed bar.

    The detector holds no clock and knows nothing about the entry window, the governor or
    positions. It answers exactly one question - did bar T produce a divergence - and the
    strategy decides whether it is allowed to act on it. Keeping those separate is what
    lets the window and governor logic be tested without synthesising divergences.
    """

    lookback: int = LOOKBACK_BARS

    prev_low: Swing | None = None
    prev_high: Swing | None = None
    _closed: deque[MinuteBar] = field(default_factory=deque)
    bars_seen: int = 0
    signals: list[Signal] = field(default_factory=list)

    def reset(self) -> None:
        """Clear swing memory and the bar window. Called at the session reset."""
        self.prev_low = None
        self.prev_high = None
        self._closed.clear()
        self.bars_seen = 0

    @property
    def ready(self) -> bool:
        """True once a full lookback of CLOSED bars exists, excluding the current one."""
        return len(self._closed) >= self.lookback

    def _window_low(self) -> Decimal:
        return min(bar.low for bar in self._closed)

    def _window_high(self) -> Decimal:
        return max(bar.high for bar in self._closed)

    def observe(self, bar: MinuteBar) -> Signal | None:
        """Evaluate bar T, then fold it into the memory. Order matters - see the docstring."""
        self.bars_seen += 1
        signal = self._evaluate(bar) if self.ready else None
        self._update_memory(bar)
        if signal is not None:
            self.signals.append(signal)
        return signal

    def _evaluate(self, bar: MinuteBar) -> Signal | None:
        #: Both windows are computed from CLOSED bars only. Bar T is not in `self._closed`
        #: yet, which is the structural guarantee behind PART 10.
        window_low = self._window_low()
        window_high = self._window_high()

        if self.prev_low is not None:
            extreme = bar.low <= window_low
            penetration = bar.low < self.prev_low.price
            divergence = bar.cvd_at_close > self.prev_low.cvd
            rejection = bar.close > bar.open
            if extreme and penetration and divergence and rejection:
                return Signal(
                    direction=+1,
                    bar=bar,
                    prev_swing_price=self.prev_low.price,
                    prev_swing_cvd=self.prev_low.cvd,
                    conditions=(
                        f"Low[T]={bar.low} <= window_low={window_low}",
                        f"Low[T]={bar.low} < Prev_Low_Price={self.prev_low.price}",
                        f"CVD[T]={bar.cvd_at_close} > Prev_Low_CVD={self.prev_low.cvd}",
                        f"Close[T]={bar.close} > Open[T]={bar.open}",
                    ),
                )

        if self.prev_high is not None:
            extreme = bar.high >= window_high
            penetration = bar.high > self.prev_high.price
            divergence = bar.cvd_at_close < self.prev_high.cvd
            rejection = bar.close < bar.open
            if extreme and penetration and divergence and rejection:
                return Signal(
                    direction=-1,
                    bar=bar,
                    prev_swing_price=self.prev_high.price,
                    prev_swing_cvd=self.prev_high.cvd,
                    conditions=(
                        f"High[T]={bar.high} >= window_high={window_high}",
                        f"High[T]={bar.high} > Prev_High_Price={self.prev_high.price}",
                        f"CVD[T]={bar.cvd_at_close} < Prev_High_CVD={self.prev_high.cvd}",
                        f"Close[T]={bar.close} < Open[T]={bar.open}",
                    ),
                )
        return None

    def _update_memory(self, bar: MinuteBar) -> None:
        """PART 11. A bar that is the extreme of its own trailing window IS the new swing."""
        if self.ready:
            if bar.low <= self._window_low():
                self.prev_low = Swing(price=bar.low, cvd=bar.cvd_at_close, at=bar.end)
            if bar.high >= self._window_high():
                self.prev_high = Swing(price=bar.high, cvd=bar.cvd_at_close, at=bar.end)

        self._closed.append(bar)
        while len(self._closed) > self.lookback:
            self._closed.popleft()


__all__ = [
    "DivergenceDetector",
    "MinuteAggregator",
    "MinuteBar",
    "Signal",
    "Swing",
]
