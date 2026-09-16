"""Synthetic scenario builder for the V1.0.0_Frozen golden suite.

WHY THE WARM-UP LOOKS LIKE THIS
---------------------------------
The strategy cannot form an opinion until four independent pieces of state are ready: a VWAP
with enough volume behind it to be stable, a full 10-bar volume SMA, fourteen completed
5-minute bars for ATR(14), and a completed 5-minute bar that establishes a regime. Building
that by hand in every test would put the same forty lines in thirty places, so it is built
once, here, with the arithmetic chosen so the resulting VWAP is EXACTLY the level asked for:

    every filler bar has high = L + w, low = L - w, close = L
    so TP = (high + low + close) / 3 = L for every bar, whatever w and whatever the volume

A series whose typical price is constant has that constant as its VWAP, exactly, with no
floating-point residue.

THE TWO THINGS THE FILLER HAS TO DO AT ONCE
---------------------------------------------
The filler bars are WIDE (+/- 10 points) because ATR(14) is computed on the 5-minute
aggregate and a session of narrow bars decays Wilder's average below the frozen 8-point gate
within an hour - a scenario padded with quiet bars would fail the context for a reason that
has nothing to do with what it is testing.

But the CONTEXT bucket has to be narrow, because the frozen regime test requires the 5-minute
low to be within 6 points of the VWAP, and the bar before the trigger has to have a low high,
because the trigger must break it. So the layout is: wide filler everywhere, one narrow
5-minute bucket immediately before the trigger's own bucket, and narrow bars from there to the
trigger. One narrow bucket pulls Wilder's ATR from 20.0 to 18.7 - still clear of the gate.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from quant_brain.strategies.vwap_pullback.indicators import Bar

ET = ZoneInfo("America/New_York")

#: The price everything is built around. A realistic NQ level, so the tick grid and the dollar
#: arithmetic are the ones the strategy will actually meet.
LEVEL = 20_000.0
#: Volume on the overnight warm-up bars. Large, so later bars cannot move the VWAP much.
WARMUP_VOLUME = 10_000.0
#: Volume on the daytime bars, which sets the SMA(10) baseline the trigger must beat.
QUIET_VOLUME = 100.0
#: Half-range of a filler bar. 10 points gives every 5-minute bucket a true range of 20.
WIDE = 10.0
#: Half-range of a bar inside the context bucket. Must keep the bucket low within the frozen
#: 6-point context distance.
NARROW = 0.25


def et_at(day: dt.date, hhmm: str) -> dt.datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    return dt.datetime(day.year, day.month, day.day, h, m, tzinfo=ET)


def flat_bar(when: dt.datetime, *, level: float = LEVEL, width: float = WIDE,
             volume: float = WARMUP_VOLUME) -> Bar:
    """A bar whose typical price is exactly `level`, so it cannot move the VWAP."""
    return Bar(timestamp=when, open=level, high=level + width, low=level - width,
               close=level, volume=volume)


@dataclass
class Scenario:
    """A day of synthetic bars, warmed up and ready to be triggered."""

    day: dt.date = dt.date(2026, 1, 6)
    level: float = LEVEL
    bars: list[Bar] = field(default_factory=list)
    trigger_time: dt.datetime | None = None

    # -- construction ----------------------------------------------------------------------

    def warmup(self) -> Scenario:
        """18:00..19:59 the previous evening: volume for the VWAP, 24 wide 5-minute buckets.

        Every bucket has a true range of 20 points, so Wilder's ATR(14) settles at exactly
        20.0 and clears the frozen 8-point gate with room to spare.
        """
        prev = self.day - dt.timedelta(days=1)
        start = et_at(prev, "18:00")
        self.bars += [flat_bar(start + dt.timedelta(minutes=i), level=self.level)
                      for i in range(120)]
        return self

    def pad_until(self, hhmm: str, *, start: str = "09:30") -> Scenario:
        """Wide, low-volume filler from `start` up to and including `hhmm`."""
        t, end = et_at(self.day, start), et_at(self.day, hhmm)
        while t <= end:
            self.bars.append(flat_bar(t, level=self.level, volume=QUIET_VOLUME))
            t += dt.timedelta(minutes=1)
        return self

    def _context_bucket_start(self, trigger: dt.datetime) -> dt.datetime:
        """The 5-minute bucket immediately BEFORE the one the trigger sits in."""
        minute = trigger.hour * 60 + trigger.minute
        bucket_start = minute - (minute % 5)
        return et_at(self.day, f"{(bucket_start - 5) // 60:02d}:{(bucket_start - 5) % 60:02d}")

    def _build(self, trigger_at: str, *, long: bool,
               context_shift: float = 0.0) -> Scenario:
        trigger = et_at(self.day, trigger_at)
        ctx_start = self._context_bucket_start(trigger)

        # wide filler from wherever the scenario currently ends, up to the context bucket
        start = "09:30"
        if self.bars and self.bars[-1].timestamp.date() == self.day:
            start = (self.bars[-1].timestamp + dt.timedelta(minutes=1)).strftime("%H:%M")
        if et_at(self.day, start) <= ctx_start - dt.timedelta(minutes=1):
            self.pad_until((ctx_start - dt.timedelta(minutes=1)).strftime("%H:%M"),
                           start=start)

        # The context bucket: four narrow bars, then one that sets the regime.
        #
        # `context_shift` moves the WHOLE bucket away from the VWAP without touching any
        # rule. At +5 every bar of a long bucket sits above the VWAP, which is what C9 is
        # about: `VWAP - low` is then NEGATIVE and still satisfies `<= 6.0`.
        base = self.level + context_shift
        for i in range(4):
            self.bars.append(flat_bar(ctx_start + dt.timedelta(minutes=i), level=base,
                                      width=NARROW, volume=QUIET_VOLUME))
        last = ctx_start + dt.timedelta(minutes=4)
        if long:
            self.bars.append(Bar(timestamp=last, open=base, high=base + 1.0,
                                 low=base - NARROW, close=base + 1.0,
                                 volume=QUIET_VOLUME))
        else:
            self.bars.append(Bar(timestamp=last, open=base, high=base + NARROW,
                                 low=base - 1.0, close=base - 1.0,
                                 volume=QUIET_VOLUME))

        # narrow bars from the trigger's own bucket start up to the trigger
        t = last + dt.timedelta(minutes=1)
        while t < trigger:
            self.bars.append(flat_bar(t, level=self.level, width=NARROW,
                                      volume=QUIET_VOLUME))
            t += dt.timedelta(minutes=1)

        self.trigger_time = trigger
        self.bars.append(self.long_trigger(trigger) if long
                         else self.short_trigger(trigger))
        return self

    def arm_long(self, *, trigger_at: str = "09:45") -> Scenario:
        return self._build(trigger_at, long=True)

    def arm_short(self, *, trigger_at: str = "09:45") -> Scenario:
        return self._build(trigger_at, long=False)

    def arm_long_entirely_above(self, *, trigger_at: str = "09:46",
                                shift: float = 5.0) -> Scenario:
        """A long context bucket that never comes near the VWAP. Register entry C9.

        The trigger must sit at least a minute after the bucket so the bar it has to break is
        one of the narrow ones back at the VWAP - otherwise no bar could be both inside the
        entry zone and above a bucket high five points clear of it.
        """
        return self._build(trigger_at, long=True, context_shift=shift)

    def arm_short_entirely_below(self, *, trigger_at: str = "09:46",
                                 shift: float = -5.0) -> Scenario:
        """The mirror. Register entry C10."""
        return self._build(trigger_at, long=False, context_shift=shift)

    def again_long(self, *, trigger_at: str) -> Scenario:
        """Another long setup later the same day. Filler resumes where the last bar left off."""
        return self._build(trigger_at, long=True)

    def again_short(self, *, trigger_at: str) -> Scenario:
        return self._build(trigger_at, long=False)

    def arm_only(self, *, at: str = "09:44") -> Scenario:
        """Establish the LONG regime but emit no trigger bar. Leaves the engine ARMED_LONG."""
        ctx_start = self._context_bucket_start(et_at(self.day, at) +
                                               dt.timedelta(minutes=5))
        self.pad_until((ctx_start - dt.timedelta(minutes=1)).strftime("%H:%M"))
        for i in range(4):
            self.bars.append(flat_bar(ctx_start + dt.timedelta(minutes=i), level=self.level,
                                      width=NARROW, volume=QUIET_VOLUME))
        self.bars.append(Bar(timestamp=ctx_start + dt.timedelta(minutes=4),
                             open=self.level, high=self.level + 1.0,
                             low=self.level - NARROW, close=self.level + 1.0,
                             volume=QUIET_VOLUME))
        self.trigger_time = ctx_start + dt.timedelta(minutes=5)
        return self

    # -- the trigger bars, built to satisfy exactly the four frozen conditions ------------

    def long_trigger(self, when: dt.datetime, *, volume: float = 1_000.0) -> Bar:
        """close in [VWAP-8, VWAP+2]; low <= VWAP; green; breaks the previous bar's high."""
        return Bar(timestamp=when, open=self.level - 1.0, high=self.level + 1.5,
                   low=self.level - 2.0, close=self.level + 1.5, volume=volume)

    def short_trigger(self, when: dt.datetime, *, volume: float = 1_000.0) -> Bar:
        return Bar(timestamp=when, open=self.level + 1.0, high=self.level + 2.0,
                   low=self.level - 1.5, close=self.level - 1.5, volume=volume)

    # -- appending post-entry bars --------------------------------------------------------

    def then(self, *, minutes_after: int, high: float, low: float, close: float,
             open_: float | None = None, volume: float = QUIET_VOLUME) -> Bar:
        """A bar `minutes_after` the trigger, with absolute prices the test computes."""
        when = self.trigger_time + dt.timedelta(minutes=minutes_after)
        return Bar(timestamp=when, open=close if open_ is None else open_, high=high,
                   low=low, close=close, volume=volume)

    def quiet_from(self, *, minutes_after: int, until: str, price: float) -> list[Bar]:
        """Uneventful bars pinned at `price`, for walking a position toward a deadline."""
        out, t = [], self.trigger_time + dt.timedelta(minutes=minutes_after)
        end = et_at(self.day, until)
        while t <= end:
            out.append(Bar(timestamp=t, open=price, high=price + 1.0, low=price - 1.0,
                           close=price, volume=QUIET_VOLUME))
            t += dt.timedelta(minutes=1)
        return out


def long_scenario(**kw) -> Scenario:
    return Scenario(**kw).warmup().arm_long()


def short_scenario(**kw) -> Scenario:
    return Scenario(**kw).warmup().arm_short()


def assert_vwap_is_pinned(engine, level: float = LEVEL, tol: float = 0.01) -> None:
    """The warm-up is supposed to hold the VWAP at `level`. Verify rather than assume."""
    assert abs(engine.vwap.value - level) < tol, (
        f"the warm-up did not pin the VWAP: {engine.vwap.value} vs {level}")
