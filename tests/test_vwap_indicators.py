"""GOLDEN: the indicator layer of V1.0.0_Frozen. Every expected value computed by hand.

The rule this file obeys, from the brief: an expected value is NEVER read out of the thing
under test. Where arithmetic is long enough to be worth checking (VWAP, the volume-weighted
standard deviation, Wilder's ATR) the test carries its own deliberately-simple reference
implementation and the two are compared; where it is short enough to do on paper, the number
is written in the comment beside the assertion.
"""
from __future__ import annotations

import datetime as dt
import math
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from quant_brain.strategies.vwap_pullback.indicators import (  # noqa: E402
    Atr,
    Bar,
    FiveMinuteAggregator,
    FiveMinuteBar,
    SessionVwap,
    VolumeSma,
    minute_of_day,
    trading_day,
)
from quant_brain.strategies.vwap_pullback.spec import FROZEN, TIMEZONE  # noqa: E402

ET = ZoneInfo("America/New_York")
ANCHOR = FROZEN.anchor_minute()          # 18:00 -> 1080


def bar(when: dt.datetime, *, h: float, low: float, c: float, v: float,
        o: float | None = None) -> Bar:
    return Bar(timestamp=when, open=c if o is None else o, high=h, low=low, close=c,
               volume=v)


def at(day: str, hhmm: str) -> dt.datetime:
    h, m = hhmm.split(":")
    y, mo, d = (int(x) for x in day.split("-"))
    return dt.datetime(y, mo, d, int(h), int(m), tzinfo=ET)


# =====================================================================================
# REFERENCE IMPLEMENTATIONS - deliberately simple, deliberately slow
# =====================================================================================

def ref_vwap(bars: list[Bar]) -> float:
    """sum(TP_i V_i) / sum(V_i). Written the long way on purpose."""
    num = sum(((b.high + b.low + b.close) / 3.0) * b.volume for b in bars)
    den = sum(b.volume for b in bars)
    return num / den


def ref_sigma(bars: list[Bar]) -> float:
    """sqrt( sum(V_i (TP_i - VWAP)^2) / sum(V_i) ), the frozen formula, literally."""
    v = ref_vwap(bars)
    num = sum(b.volume * (((b.high + b.low + b.close) / 3.0) - v) ** 2 for b in bars)
    den = sum(b.volume for b in bars)
    return math.sqrt(num / den)


def ref_true_ranges(bars: list) -> list[float]:
    out = []
    prev_close = None
    for b in bars:
        out.append(b.high - b.low if prev_close is None
                   else max(b.high - b.low, abs(b.high - prev_close),
                            abs(b.low - prev_close)))
        prev_close = b.close
    return out


def ref_atr_wilder(bars: list, period: int) -> float:
    trs = ref_true_ranges(bars)
    if len(trs) < period:
        return float("nan")
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


def ref_atr_sma(bars: list, period: int) -> float:
    trs = ref_true_ranges(bars)
    return sum(trs[-period:]) / period if len(trs) >= period else float("nan")


# =====================================================================================
# VWAP
# =====================================================================================

def test_the_briefs_two_bar_vwap_is_exactly_101_point_5():
    """The worked example from the specification, computed on paper.

        TP1 = (101 + 99 + 100)/3 = 100      V1 = 100
        TP2 = (103 + 101 + 102)/3 = 102     V2 = 300
        VWAP = (100*100 + 102*300) / 400 = 40,600 / 400 = 101.5
    """
    v = SessionVwap(anchor_minute=ANCHOR)
    v.update(bar(at("2026-01-05", "19:00"), h=101, low=99, c=100, v=100))
    assert v.value == pytest.approx(100.0)          # one bar: VWAP is its own TP
    v.update(bar(at("2026-01-05", "19:01"), h=103, low=101, c=102, v=300))
    assert v.value == pytest.approx(101.5)


def test_the_two_bar_standard_deviation_is_exactly_sqrt_three_quarters():
    """sum(V (TP - VWAP)^2)/sum(V) = (100*1.5^2 + 300*0.5^2)/400 = 300/400 = 0.75."""
    v = SessionVwap(anchor_minute=ANCHOR)
    bars = [bar(at("2026-01-05", "19:00"), h=101, low=99, c=100, v=100),
            bar(at("2026-01-05", "19:01"), h=103, low=101, c=102, v=300)]
    for b in bars:
        v.update(b)
    assert v.variance == pytest.approx(0.75)
    assert v.sigma == pytest.approx(math.sqrt(0.75))
    assert v.sigma == pytest.approx(0.8660254037844386)
    # and the bands
    assert v.band(1.0) == pytest.approx(101.5 + math.sqrt(0.75))
    assert v.band(-1.0) == pytest.approx(101.5 - math.sqrt(0.75))
    # against the literal reference
    assert v.value == pytest.approx(ref_vwap(bars))
    assert v.sigma == pytest.approx(ref_sigma(bars))


def test_the_typical_price_is_the_three_way_average_and_not_the_close():
    """(H + L + C) / 3. An ASYMMETRIC bar is what separates the two readings.

    Every other fixture in this file uses bars centred on their close, where TP and close
    happen to coincide - convenient for hand arithmetic, and blind to a VWAP that weights the
    wrong number. Mutation testing found exactly that hole.
    """
    b = bar(at("2026-01-05", "19:00"), h=110, low=100, c=101, v=1)
    assert b.typical_price == pytest.approx((110 + 100 + 101) / 3.0)
    assert b.typical_price == pytest.approx(103.66666666666667)
    assert b.typical_price != pytest.approx(b.close)


def test_the_vwap_weights_typical_prices_and_not_closes():
    """The same bars under both readings give different numbers; the frozen one is TP."""
    bars = [bar(at("2026-01-05", "19:00"), h=110, low=100, c=101, v=100),
            bar(at("2026-01-05", "19:01"), h=120, low=104, c=119, v=300)]
    v = SessionVwap(anchor_minute=ANCHOR)
    for b in bars:
        v.update(b)
    # TP1 = 103.6666..., TP2 = 114.3333...
    assert v.value == pytest.approx((103.66666666666667 * 100 + 114.33333333333333 * 300)
                                    / 400)
    assert v.value == pytest.approx(ref_vwap(bars))
    close_weighted = sum(b.close * b.volume for b in bars) / sum(b.volume for b in bars)
    assert v.value != pytest.approx(close_weighted), (
        "the VWAP agreed with a close-weighted one; the fixture cannot tell them apart")


def test_the_sigma_is_measured_around_typical_prices_too():
    bars = [bar(at("2026-01-05", "19:00"), h=110, low=100, c=101, v=100),
            bar(at("2026-01-05", "19:01"), h=120, low=104, c=119, v=300)]
    v = SessionVwap(anchor_minute=ANCHOR)
    for b in bars:
        v.update(b)
    assert v.sigma == pytest.approx(ref_sigma(bars))
    assert v.sigma > 0.0


def test_the_first_bar_has_a_vwap_and_zero_dispersion():
    v = SessionVwap(anchor_minute=ANCHOR)
    v.update(bar(at("2026-01-05", "19:00"), h=102, low=98, c=100, v=50))
    assert v.value == pytest.approx(100.0)          # TP = (102+98+100)/3 = 100
    assert v.sigma == pytest.approx(0.0)


def test_before_any_volume_the_vwap_is_NaN_and_never_a_silent_zero():
    v = SessionVwap(anchor_minute=ANCHOR)
    assert not v.ready
    assert v.value != v.value
    assert v.sigma != v.sigma


def test_a_zero_volume_bar_contributes_no_weight_but_is_still_counted():
    """It must not shift the VWAP, and it must not be invisible either."""
    v = SessionVwap(anchor_minute=ANCHOR)
    v.update(bar(at("2026-01-05", "19:00"), h=101, low=99, c=100, v=100))
    before = v.value
    v.update(bar(at("2026-01-05", "19:01"), h=900, low=880, c=890, v=0))
    assert v.value == pytest.approx(before), "a zero-volume bar moved the VWAP"
    assert v.bars_in_session == 2, "the bar vanished from the count"


def test_the_vwap_resets_at_exactly_eighteen_hundred_and_not_a_minute_either_side():
    v = SessionVwap(anchor_minute=ANCHOR)
    v.update(bar(at("2026-01-05", "17:58"), h=101, low=99, c=100, v=100))
    v.update(bar(at("2026-01-05", "17:59"), h=101, low=99, c=100, v=100))
    assert v.resets == 0
    assert v.bars_in_session == 2
    v.update(bar(at("2026-01-05", "18:00"), h=203, low=201, c=202, v=300))
    assert v.resets == 1, "18:00 did not open a new session"
    assert v.bars_in_session == 1, "the new session kept the old bars"
    assert v.value == pytest.approx(202.0)          # TP = (203+201+202)/3 = 202


def test_bars_either_side_of_the_anchor_belong_to_different_trading_days():
    assert trading_day(at("2026-01-05", "17:59"), ANCHOR) == dt.date(2026, 1, 5)
    assert trading_day(at("2026-01-05", "18:00"), ANCHOR) == dt.date(2026, 1, 6)
    assert trading_day(at("2026-01-06", "09:45"), ANCHOR) == dt.date(2026, 1, 6)
    assert trading_day(at("2026-01-06", "15:45"), ANCHOR) == dt.date(2026, 1, 6)


def test_there_is_one_continuous_vwap_across_the_overnight_into_the_rth_session():
    """The 09:45 VWAP must carry the overnight bars, not restart at the cash open."""
    v = SessionVwap(anchor_minute=ANCHOR)
    overnight = [bar(at("2026-01-05", "18:00") + dt.timedelta(minutes=i),
                     h=101, low=99, c=100, v=100) for i in range(60)]
    for b in overnight:
        v.update(b)
    morning = bar(at("2026-01-06", "09:45"), h=121, low=119, c=120, v=100)
    v.update(morning)
    assert v.resets == 0, "the VWAP reset somewhere it should not have"
    assert v.bars_in_session == 61
    assert v.value == pytest.approx(ref_vwap([*overnight, morning]))
    # 60 bars at TP 100 and one at TP 120, equal volume -> (60*100 + 120)/61
    assert v.value == pytest.approx((60 * 100.0 + 120.0) / 61)


def test_the_incremental_vwap_matches_the_literal_formula_over_a_full_session():
    """Numerical precision (brief §20): NQ-scale prices over a whole session.

    The textbook O(1) shortcut `E[TP^2] - VWAP^2` subtracts two numbers near 4e8 here and
    loses most of its significant digits; volume-weighted Welford does not. 1e-9 on prices
    near 20,000 is roughly fourteen significant figures.
    """
    import random
    rng = random.Random(7)
    v = SessionVwap(anchor_minute=ANCHOR)
    bars = []
    px = 20_000.0
    for i in range(1_380):
        px += rng.uniform(-3, 3)
        b = bar(at("2026-01-05", "18:00") + dt.timedelta(minutes=i),
                h=px + 1.0, low=px - 1.0, c=px, v=rng.uniform(50, 5_000))
        bars.append(b)
        v.update(b)
    assert v.value == pytest.approx(ref_vwap(bars), abs=1e-9)
    assert v.sigma == pytest.approx(ref_sigma(bars), abs=1e-9)


def test_a_flat_market_has_zero_dispersion_and_not_a_negative_variance():
    """The cancellation case the shortcut formula gets wrong."""
    v = SessionVwap(anchor_minute=ANCHOR)
    for i in range(500):
        v.update(bar(at("2026-01-05", "18:00") + dt.timedelta(minutes=i),
                     h=20_000.0, low=20_000.0, c=20_000.0, v=1_000.0))
    assert v.variance >= 0.0
    assert v.sigma == pytest.approx(0.0, abs=1e-9)


# =====================================================================================
# TIMEZONE AND DST
# =====================================================================================

def test_the_strategy_clock_is_the_repositorys_authoritative_one():
    from quant_brain.core.calendar import ET as REPO_ET
    assert TIMEZONE is REPO_ET
    assert TIMEZONE.key == "America/New_York"


def test_a_naive_timestamp_is_refused_rather_than_assumed_to_be_local():
    with pytest.raises(ValueError, match="timezone-naive"):
        Bar(timestamp=dt.datetime(2026, 1, 5, 10, 0), open=1, high=1, low=1, close=1,
            volume=1)


@pytest.mark.parametrize("day", ["2026-03-07", "2026-03-08", "2026-03-09",
                                 "2026-10-31", "2026-11-01", "2026-11-02"])
@pytest.mark.parametrize("hhmm,expected", [("09:45", 585), ("15:30", 930), ("15:45", 945),
                                           ("18:00", 1080)])
def test_the_wall_clock_rules_hold_their_time_across_both_dst_transitions(day, hhmm,
                                                                         expected):
    """09:45 stays 09:45, 18:00 stays 18:00 - on the transition days themselves.

    The UTC offset moves underneath; the strategy's minute-of-day must not.
    """
    when = at(day, hhmm)
    assert minute_of_day(when) == expected


def test_the_same_wall_clock_time_is_a_different_utc_hour_across_the_transition():
    """If this ever stops being true, something has hard-coded an offset."""
    winter = at("2026-01-15", "09:45").astimezone(dt.UTC)
    summer = at("2026-07-15", "09:45").astimezone(dt.UTC)
    assert winter.hour == 14 and summer.hour == 13
    # and both still read 09:45 on the venue clock
    assert minute_of_day(winter) == minute_of_day(summer) == 585


def test_a_utc_timestamp_is_mapped_to_et_before_any_rule_is_applied():
    """Data arrives in UTC; the rules are wall-clock. The conversion is the whole point."""
    utc = dt.datetime(2026, 7, 15, 22, 0, tzinfo=dt.UTC)     # 18:00 ET in summer
    assert minute_of_day(utc) == 1080
    assert trading_day(utc, ANCHOR) == dt.date(2026, 7, 16)


def test_the_vwap_anchor_survives_a_dst_transition_day():
    """Spring forward: 02:00 does not exist. The 18:00 anchor is still one reset per day."""
    v = SessionVwap(anchor_minute=ANCHOR)
    when = at("2026-03-07", "18:00")
    end = at("2026-03-09", "18:00")
    n = 0
    while when < end:
        v.update(bar(when, h=101, low=99, c=100, v=10))
        when += dt.timedelta(minutes=30)
        n += 1
    assert v.resets == 1, f"expected exactly one 18:00 reset over two days, got {v.resets}"


# =====================================================================================
# VOLUME SMA
# =====================================================================================

def test_the_volume_sma_is_unavailable_until_its_window_is_full():
    s = VolumeSma(period=10)
    for i in range(9):
        s.update(bar(at("2026-01-05", "19:00") + dt.timedelta(minutes=i),
                     h=1, low=1, c=1, v=100))
        assert not s.ready
        assert s.value != s.value, "a partial window reported an average"
    s.update(bar(at("2026-01-05", "19:09"), h=1, low=1, c=1, v=100))
    assert s.ready and s.value == pytest.approx(100.0)


def test_the_volume_sma_includes_the_current_bar():
    """AMBIGUITY A6, pinned so the reading cannot drift.

    Nine bars of 100 and a tenth of 1,000: including the current bar gives 190; excluding it
    would give 100.
    """
    s = VolumeSma(period=10)
    for i in range(9):
        s.update(bar(at("2026-01-05", "19:00") + dt.timedelta(minutes=i),
                     h=1, low=1, c=1, v=100))
    s.update(bar(at("2026-01-05", "19:09"), h=1, low=1, c=1, v=1_000))
    assert s.value == pytest.approx((9 * 100 + 1_000) / 10)     # = 190.0
    assert s.value == pytest.approx(190.0)


def test_the_volume_threshold_arithmetic_is_one_point_two_times_the_mean():
    """The frozen gate: volume >= 1.2 * SMA(10). Mean 190 -> threshold 228."""
    assert FROZEN.volume_multiple * 190.0 == pytest.approx(228.0)


# =====================================================================================
# FIVE-MINUTE AGGREGATION
# =====================================================================================

def _minute_bars(start: dt.datetime, specs):
    return [bar(start + dt.timedelta(minutes=i), h=h, low=lo, c=c, v=v, o=o)
            for i, (o, h, lo, c, v) in enumerate(specs)]


def test_a_five_minute_bar_appears_only_once_its_final_minute_has_closed():
    """Causality. While the bucket is forming it must not be visible to anything."""
    agg = FiveMinuteAggregator()
    bars = _minute_bars(at("2026-01-06", "09:40"),
                        [(100, 102, 99, 101, 10), (101, 103, 100, 102, 20),
                         (102, 104, 101, 103, 30), (103, 105, 102, 104, 40),
                         (104, 106, 103, 105, 50), (105, 107, 104, 106, 60)])
    for b in bars[:5]:
        assert agg.update(b, 100.0) is None
        assert agg.last_completed is None, "an unfinished 5m bar became visible"
    done = agg.update(bars[5], 100.0)
    assert done is not None
    assert agg.last_completed is done


def test_the_completed_five_minute_bar_is_the_hand_aggregated_one():
    """09:40..09:44 -> open of the first, high of all, low of all, close of the last."""
    agg = FiveMinuteAggregator()
    bars = _minute_bars(at("2026-01-06", "09:40"),
                        [(100, 102, 99, 101, 10), (101, 103, 100, 102, 20),
                         (102, 104, 101, 103, 30), (103, 105, 102, 104, 40),
                         (104, 106, 103, 105, 50), (105, 107, 104, 106, 60)])
    for b in bars:
        agg.update(b, 100.0)
    five = agg.last_completed
    assert five.open == 100        # the 09:40 open
    assert five.high == 106        # max(102,103,104,105,106)
    assert five.low == 99          # min(99,100,101,102,103)
    assert five.close == 105       # the 09:44 close
    assert five.volume == 150      # 10+20+30+40+50
    assert five.start == at("2026-01-06", "09:40")
    assert five.end == at("2026-01-06", "09:44")


def test_buckets_are_aligned_to_the_venue_clock_and_not_to_the_first_bar_seen():
    """A stream starting at 09:42 must still close its bucket at 09:44."""
    agg = FiveMinuteAggregator()
    bars = _minute_bars(at("2026-01-06", "09:42"),
                        [(100, 101, 99, 100, 10)] * 5)
    done = [agg.update(b, 100.0) for b in bars]
    assert done[:3] == [None, None, None]
    assert done[3] is not None, "the bucket did not close on the 09:45 boundary"
    assert done[3].start == at("2026-01-06", "09:42")
    assert done[3].end == at("2026-01-06", "09:44")


def test_the_five_minute_bar_carries_the_vwap_value_from_its_own_close():
    """The 5m context reads a RECORDED 1m VWAP value, never one of its own."""
    agg = FiveMinuteAggregator()
    bars = _minute_bars(at("2026-01-06", "09:40"), [(100, 101, 99, 100, 10)] * 6)
    values = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0]
    done = None
    for b, v in zip(bars, values, strict=True):
        done = agg.update(b, v) or done
    assert done.vwap_at_close == 50.0, "the 5m bar did not take the VWAP at its last minute"


# =====================================================================================
# ATR
# =====================================================================================

def _five(h, low, c, i=0):
    t = at("2026-01-06", "09:40") + dt.timedelta(minutes=5 * i)
    return FiveMinuteBar(start=t, end=t + dt.timedelta(minutes=4), open=c, high=h, low=low,
                         close=c, volume=100.0, vwap_at_close=100.0)


def test_true_range_is_the_frozen_three_way_maximum():
    a = Atr(period=14)
    first = _five(110, 100, 105, 0)
    assert a.true_range(first) == 10.0          # no previous close: H - L
    a.update(first)                              # prev_close = 105
    # H-L = 8; |H - 105| = 7; |L - 105| = 1  -> 8
    assert a.true_range(_five(112, 104, 108, 1)) == pytest.approx(8.0)
    a2 = Atr(period=14)
    a2.update(_five(110, 100, 105, 0))
    # a gap up: H-L = 2; |H - 105| = 17; |L - 105| = 15  -> 17
    assert a2.true_range(_five(122, 120, 121, 1)) == pytest.approx(17.0)


def test_wilder_atr_matches_an_independent_reference():
    import random
    rng = random.Random(3)
    bars, px = [], 20_000.0
    for i in range(60):
        px += rng.uniform(-10, 10)
        bars.append(_five(px + rng.uniform(1, 12), px - rng.uniform(1, 12), px, i))
    a = Atr(period=14, method="wilder")
    for b in bars:
        a.update(b)
    assert a.value == pytest.approx(ref_atr_wilder(bars, 14), abs=1e-9)


def test_sma_atr_matches_an_independent_reference():
    import random
    rng = random.Random(4)
    bars, px = [], 20_000.0
    for i in range(60):
        px += rng.uniform(-10, 10)
        bars.append(_five(px + rng.uniform(1, 12), px - rng.uniform(1, 12), px, i))
    a = Atr(period=14, method="sma")
    for b in bars:
        a.update(b)
    assert a.value == pytest.approx(ref_atr_sma(bars, 14), abs=1e-9)


def test_the_two_atr_readings_genuinely_differ_so_the_ambiguity_is_real():
    """AMBIGUITY A1 is material, demonstrated rather than asserted."""
    bars = [_five(100 + (30 if i == 0 else 2), 100 - (30 if i == 0 else 2), 100, i)
            for i in range(20)]
    w, s = Atr(period=14, method="wilder"), Atr(period=14, method="sma")
    for b in bars:
        w.update(b)
        s.update(b)
    assert w.value != pytest.approx(s.value), (
        "the two ATR readings agreed on a series built to separate them; the ambiguity "
        "would be untestable")


def test_the_atr_is_unavailable_before_fourteen_bars():
    a = Atr(period=14)
    for i in range(13):
        a.update(_five(110, 100, 105, i))
        assert not a.ready
        assert a.value != a.value
    a.update(_five(110, 100, 105, 13))
    assert a.ready


@pytest.mark.parametrize("atr_value,accepted", [(7.999999, False), (8.0, True),
                                                (8.000001, True)])
def test_the_eight_point_atr_gate_is_a_closed_boundary(atr_value, accepted):
    """`>=` 8.0. The three values the brief names, tested against the frozen constant."""
    assert (atr_value >= FROZEN.atr_minimum) is accepted


def test_the_atr_is_built_from_five_minute_bars_and_not_from_one_minute_bars():
    """Structural: `Atr.update` takes a FiveMinuteBar, so a 1-minute bar cannot reach it."""
    import inspect
    sig = inspect.signature(Atr.update)
    assert sig.parameters["bar"].annotation == "FiveMinuteBar"
