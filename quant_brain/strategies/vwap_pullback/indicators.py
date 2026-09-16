"""The indicator state: ONE VWAP array, a causal 5-minute aggregator, ATR(14), volume SMA.

EVERY OBJECT HERE IS AN ONLINE ACCUMULATOR, AND THAT IS THE POINT
------------------------------------------------------------------
A vectorised indicator computed over a whole frame can see the future by accident - a
`rolling(..., center=True)`, a `shift(-1)`, a session aggregate broadcast back over its own
bars. None of that is expressible here: each object is fed one bar at a time and can only
return what it has already been fed. Causality is a property of the data structure rather than
something a test has to go looking for.

THE ONE VWAP ARRAY
------------------
`SessionVwap` is the only VWAP in this package. The 5-minute context does not compute its own:
`FiveMinuteAggregator` records the VWAP value that `SessionVwap` held at the close of each
5-minute bar, so the 5-minute regime and the 1-minute trigger are reading the same series by
construction and not by coincidence. `test_the_5m_context_and_the_1m_trigger_read_one_vwap`
asserts it against the identity of the values.

NUMERICAL NOTE ON THE STANDARD DEVIATION
------------------------------------------
The frozen formula is `sqrt(sum(V_i (TP_i - VWAP_t)^2) / sum(V_i))` - the dispersion around the
CURRENT VWAP, so a naive incremental form would have to revisit every bar. The textbook O(1)
shortcut, `E[TP^2] - VWAP^2`, subtracts two numbers near 4e8 on NQ prices and loses most of its
significant digits when the dispersion is small. This uses volume-weighted WELFORD instead,
which is O(1), algebraically identical, and does not cancel.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field

from quant_brain.strategies.vwap_pullback.spec import TIMEZONE


def et(when: dt.datetime) -> dt.datetime:
    """The venue-clock reading of an instant. Refuses a naive timestamp.

    A naive datetime is an unstated assumption about which clock it is on, and the DST rules
    this strategy lives under are exactly what that assumption gets wrong twice a year.
    """
    if when.tzinfo is None or when.utcoffset() is None:
        raise ValueError(
            f"{when!r} is timezone-naive. Every timestamp reaching this strategy must be "
            f"tz-aware; convert at the data boundary, never here.")
    return when.astimezone(TIMEZONE)


def minute_of_day(when: dt.datetime) -> int:
    """Minutes past midnight on the VENUE clock, after the DST-aware conversion."""
    local = et(when)
    return local.hour * 60 + local.minute


def trading_day(when: dt.datetime, anchor_minute: int) -> dt.date:
    """The trading date a bar belongs to, where the day rolls at the anchor (18:00 ET).

    A bar at 19:30 on Monday belongs to Tuesday's trading day; a bar at 10:00 on Tuesday
    belongs to Tuesday's. AMBIGUITY A13 records why the counters roll here rather than at
    midnight: it is the boundary the VWAP anchor and the halt release already use.
    """
    local = et(when)
    if local.hour * 60 + local.minute >= anchor_minute:
        return (local + dt.timedelta(days=1)).date()
    return local.date()


@dataclass
class Bar:
    """One bar, start-stamped, on a tz-aware clock. The engine's only input type."""

    timestamp: dt.datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        et(self.timestamp)                       # refuses naive
        if self.high < self.low:
            raise ValueError(f"{self.timestamp}: high {self.high} below low {self.low}")
        if not (self.low <= self.open <= self.high):
            raise ValueError(f"{self.timestamp}: open {self.open} outside [{self.low}, "
                             f"{self.high}]")
        if not (self.low <= self.close <= self.high):
            raise ValueError(f"{self.timestamp}: close {self.close} outside [{self.low}, "
                             f"{self.high}]")
        if self.volume < 0:
            raise ValueError(f"{self.timestamp}: negative volume {self.volume}")

    @property
    def typical_price(self) -> float:
        """TP = (High + Low + Close) / 3, the frozen definition."""
        return (self.high + self.low + self.close) / 3.0


@dataclass
class SessionVwap:
    """The ONE VWAP array, anchored at the session boundary and reset there exactly.

    Fed one bar at a time. `value` and `sigma` are what the series held after the most recent
    bar, which is all any decision at that bar is allowed to see.
    """

    anchor_minute: int
    #: Volume-weighted Welford state.
    _weight: float = 0.0
    _mean: float = 0.0
    _m2: float = 0.0
    _day: dt.date | None = None
    bars_in_session: int = 0
    resets: int = 0

    def update(self, bar: Bar) -> None:
        """Absorb one bar, resetting first if it opens a new anchored session."""
        day = trading_day(bar.timestamp, self.anchor_minute)
        if self._day is None:
            self._day = day
        elif day != self._day:
            self.reset(day)
        self._day = day

        tp = bar.typical_price
        w = float(bar.volume)
        self.bars_in_session += 1
        if w <= 0.0:
            # A zero-volume bar contributes no weight. It is NOT skipped silently: the bar
            # count still advances, so `bars_in_session` and the weight can disagree and a
            # caller can see that the series is thinner than it looks.
            return
        new_weight = self._weight + w
        delta = tp - self._mean
        self._mean += delta * w / new_weight
        self._m2 += w * delta * (tp - self._mean)
        self._weight = new_weight

    def reset(self, day: dt.date | None = None) -> None:
        self._weight = self._mean = self._m2 = 0.0
        self.bars_in_session = 0
        self._day = day
        self.resets += 1

    @property
    def ready(self) -> bool:
        return self._weight > 0.0

    @property
    def value(self) -> float:
        """VWAP, or NaN before any volume has been seen. Never a silent zero."""
        return self._mean if self.ready else float("nan")

    @property
    def variance(self) -> float:
        if not self.ready:
            return float("nan")
        # Welford's M2 is non-negative by construction; the max guards only against a
        # denormal appearing at exactly zero dispersion.
        return max(0.0, self._m2 / self._weight)

    @property
    def sigma(self) -> float:
        v = self.variance
        return math.sqrt(v) if v == v else float("nan")

    def band(self, sigmas: float) -> float:
        return self.value + sigmas * self.sigma


@dataclass
class VolumeSma:
    """SMA of volume over the last `period` bars, INCLUDING the current one (AMBIGUITY A6)."""

    period: int
    _window: list[float] = field(default_factory=list)

    def update(self, bar: Bar) -> None:
        self._window.append(float(bar.volume))
        if len(self._window) > self.period:
            self._window.pop(0)

    def reset(self) -> None:
        self._window.clear()

    @property
    def ready(self) -> bool:
        return len(self._window) == self.period

    @property
    def value(self) -> float:
        """The mean, or NaN until the window is full. A partial window is not an average."""
        return sum(self._window) / len(self._window) if self.ready else float("nan")


@dataclass
class FiveMinuteBar:
    """A COMPLETED 5-minute bar, plus the VWAP value at its close.

    `vwap_at_close` is recorded, not recomputed: it is the value the one-minute `SessionVwap`
    held when this bar's final minute closed. That is what makes the 5-minute context and the
    1-minute trigger the same series.
    """

    start: dt.datetime
    end: dt.datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap_at_close: float


@dataclass
class FiveMinuteAggregator:
    """Builds 5-minute bars from the 1-minute stream, causally.

    A 5-minute bar becomes visible only when its final minute has closed and the NEXT bucket
    has begun. Until then it does not exist as far as any decision is concerned - which is the
    difference between a 5-minute context and a peek at the bar being formed.
    """

    bucket_minutes: int = 5
    completed: list[FiveMinuteBar] = field(default_factory=list)
    _bucket: int | None = None
    _o: float = 0.0
    _h: float = 0.0
    _low: float = 0.0
    _c: float = 0.0
    _v: float = 0.0
    _start: dt.datetime | None = None
    _end: dt.datetime | None = None
    _vwap_at_close: float = float("nan")

    def _bucket_of(self, bar: Bar) -> int:
        """Clock-aligned buckets on the VENUE clock: 09:40, 09:45, 09:50 ..."""
        local = et(bar.timestamp)
        return (local.hour * 60 + local.minute) // self.bucket_minutes

    def update(self, bar: Bar, vwap_value: float) -> FiveMinuteBar | None:
        """Absorb a 1-minute bar. Returns the 5-minute bar that JUST completed, if any."""
        bucket = self._bucket_of(bar)
        finished: FiveMinuteBar | None = None
        if self._bucket is not None and bucket != self._bucket:
            finished = self._close_bucket()
        if self._bucket is None or finished is not None:
            self._bucket = bucket
            self._o, self._h, self._low = bar.open, bar.high, bar.low
            self._v = 0.0
            self._start = bar.timestamp
        else:
            self._h = max(self._h, bar.high)
            self._low = min(self._low, bar.low)
        self._c = bar.close
        self._v += float(bar.volume)
        self._end = bar.timestamp
        self._vwap_at_close = vwap_value
        return finished

    def _close_bucket(self) -> FiveMinuteBar:
        if self._start is None or self._end is None:          # pragma: no cover
            raise RuntimeError("closing a 5-minute bucket that was never opened")
        out = FiveMinuteBar(start=self._start, end=self._end, open=self._o, high=self._h,
                            low=self._low, close=self._c, volume=self._v,
                            vwap_at_close=self._vwap_at_close)
        self.completed.append(out)
        return out

    def reset(self) -> None:
        self.completed.clear()
        self._bucket = None

    @property
    def last_completed(self) -> FiveMinuteBar | None:
        """The most recent COMPLETED 5-minute bar, or None. Never the one being formed."""
        return self.completed[-1] if self.completed else None


@dataclass
class Atr:
    """Average true range over completed 5-minute bars.

    TR = max(H-L, |H - prev_close|, |L - prev_close|), the frozen definition. Two smoothings
    are implemented because "ATR(14)" is AMBIGUITY A1 and the reading materially changes
    whether the 8.0-point gate opens:

        wilder  the conventional ATR. Seeded with the simple mean of the first `period` true
                ranges, then ATR_t = (ATR_{t-1} (n-1) + TR_t) / n.
        sma     the simple mean of the last `period` true ranges.
    """

    period: int
    method: str = "wilder"
    _prev_close: float | None = None
    _seed: list[float] = field(default_factory=list)
    _window: list[float] = field(default_factory=list)
    _value: float = float("nan")

    def __post_init__(self) -> None:
        if self.method not in ("wilder", "sma"):
            raise ValueError(f"unknown ATR method {self.method!r}")

    def true_range(self, bar: FiveMinuteBar) -> float:
        if self._prev_close is None:
            return bar.high - bar.low
        pc = self._prev_close
        return max(bar.high - bar.low, abs(bar.high - pc), abs(bar.low - pc))

    def update(self, bar: FiveMinuteBar) -> None:
        tr = self.true_range(bar)
        self._prev_close = bar.close
        if self.method == "sma":
            self._window.append(tr)
            if len(self._window) > self.period:
                self._window.pop(0)
            self._value = (sum(self._window) / self.period
                           if len(self._window) == self.period else float("nan"))
            return
        if self._value != self._value:                    # not yet seeded
            self._seed.append(tr)
            if len(self._seed) == self.period:
                self._value = sum(self._seed) / self.period
            return
        self._value = (self._value * (self.period - 1) + tr) / self.period

    def reset(self) -> None:
        self._prev_close = None
        self._seed.clear()
        self._window.clear()
        self._value = float("nan")

    @property
    def ready(self) -> bool:
        return self._value == self._value

    @property
    def value(self) -> float:
        return self._value


__all__ = ["Atr", "Bar", "FiveMinuteAggregator", "FiveMinuteBar", "SessionVwap", "VolumeSma",
           "et", "minute_of_day", "trading_day"]
