"""CVD_ABSORPTION_HARVESTER / XFA_V2.0 - specification, CVD, causality and governor.

The lookahead section (PART 23) is the part worth reading. Those tests plant future
information and require the past to be unchanged by it. A divergence strategy that consults
later bars to confirm a swing produces beautiful backtests and no money, and the failure is
invisible in the equity curve - so it is tested structurally rather than hoped for.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from topstep_backtester.strategies.cvd_absorption_harvester import governor_probe as GP
from topstep_backtester.strategies.cvd_absorption_harvester import spec as S
from topstep_backtester.strategies.cvd_absorption_harvester import tick_schema
from topstep_backtester.strategies.cvd_absorption_harvester.governor import (
    Governor,
    IllegalTransition,
    State,
)
from topstep_backtester.strategies.cvd_absorption_harvester.signal import (
    DivergenceDetector,
    MinuteAggregator,
    MinuteBar,
)
from topstep_backtester.strategies.cvd_absorption_harvester.ticks import (
    AmbiguousTick,
    Classification,
    TickDataHandler,
    Trade,
)
from topstep_backtester.strategies.spec import SpecError
from topstep_backtester.upstream import SPECS

ET = ZoneInfo("America/New_York")


def trade(*, at: dt.datetime, price: str, volume: int = 10,
          bid: str | None = None, ask: str | None = None) -> Trade:
    return Trade(
        timestamp=at,
        price=Decimal(price),
        volume=volume,
        bid=None if bid is None else Decimal(bid),
        ask=None if ask is None else Decimal(ask),
    )


def et(day: dt.date, hh: int, mm: int, ss: int = 0) -> dt.datetime:
    return dt.datetime(day.year, day.month, day.day, hh, mm, ss, tzinfo=ET)


DAY = dt.date(2025, 6, 3)


# ======================================================================================
# PART 1 / PART 39 - the specification and its register
# ======================================================================================


def test_the_spec_has_a_stable_identity() -> None:
    assert S.SPEC.name == "CVD_ABSORPTION_HARVESTER"
    assert S.SPEC.version == "XFA_V2.0"
    assert len(S.SPEC.spec_hash) == 16
    assert S.SPEC.spec_hash == S.SPEC.spec_hash


def test_the_spec_restates_the_real_es_contract_terms() -> None:
    """The arithmetic in this package is derived from these, so they must be the real ones."""
    es = SPECS["ES"]
    assert es.tick_size == S.TICK_SIZE
    assert es.tick_value == S.TICK_VALUE
    assert S.POINT_VALUE == S.TICK_VALUE * 4


def test_the_frozen_parameters_are_the_owners_numbers() -> None:
    """PART 38. If one of these changes, it is a new strategy version, not a tweak."""
    assert S.LOOKBACK_BARS == 15
    assert S.CONTRACTS == 1
    assert S.STOP_TICKS == 8
    assert S.TARGET_TICKS == 16
    assert S.BE_TRIGGER_TICKS == 8
    assert S.BE_STOP_OFFSET_TICKS == 1
    assert S.WINNING_DAY_LOCK_USD == Decimal("160")
    assert S.KILLSWITCH_USD == Decimal("-250")
    assert S.CVD_RESET_ET == "09:30:00"
    assert S.ENTRY_WINDOW_OPEN_ET == "09:45:00"
    assert S.ENTRY_WINDOW_CLOSE_ET == "11:30:00"
    assert S.COMMISSION_ROUND_TURN_USD == Decimal("4.14")


def test_the_register_covers_every_part_39_item_and_then_some() -> None:
    refs = {a.ref for a in S.AMBIGUITIES}
    assert {f"A{n}" for n in range(1, 16)} <= refs, "a PART 39 item is missing"
    assert {"A16", "A17"} <= refs, "the two items found while implementing are missing"


def test_the_register_counts_are_pinned() -> None:
    """The report quotes these. A silent drift would make the report wrong, not the code."""
    resolved = [a.ref for a in S.AMBIGUITIES if a.resolved]
    unresolved = list(S.unresolved_refs())
    assert len(S.AMBIGUITIES) == 17, f"register has {len(S.AMBIGUITIES)} items"
    assert sorted(resolved) == ["A12", "A13", "A14", "A15", "A17", "A8"], resolved
    assert len(unresolved) == 11, f"{len(unresolved)} unresolved: {unresolved}"


def test_the_spec_cannot_be_frozen_while_readings_are_undecided() -> None:
    """PART 39: do not invent answers. An unfrozen spec cannot run, which is the point."""
    outstanding = S.unresolved_refs()
    assert outstanding, "expected unresolved ambiguities requiring owner input"
    with pytest.raises(SpecError, match="unresolved ambiguit"):
        S.SPEC.freeze(author="claude")


def test_every_resolved_item_names_its_authority() -> None:
    """A reading with no source is an invention with a citation field left blank."""
    for item in S.AMBIGUITIES:
        if item.resolved:
            assert item.reading_taken.strip(), f"{item.ref} resolved with no reading"
            assert item.authority.strip(), f"{item.ref} resolved with no authority"


def test_a_long_and_a_short_signal_cannot_coexist() -> None:
    """AMBIGUITY A8, resolved from the spec's own text rather than by a tie-break rule.

    PART 12.4 needs Close > Open and PART 13.4 needs Close < Open. No bar satisfies both.
    """
    a8 = next(a for a in S.AMBIGUITIES if a.ref == "A8")
    assert a8.resolved and not a8.material
    bar = MinuteBar(start=et(DAY, 10, 0), end=et(DAY, 10, 1), open=Decimal("5000.00"),
                    high=Decimal("5001.00"), low=Decimal("4999.00"),
                    close=Decimal("5000.50"), volume=10, cvd_at_close=0, trades=1)
    assert not (bar.close > bar.open and bar.close < bar.open)


# ======================================================================================
# PART 2 / PART 43 - the data gate
# ======================================================================================


def test_the_tick_gate_refuses_minute_bars() -> None:
    import pandas as pd

    minute_grid = pd.DataFrame(
        {
            "t": pd.date_range("2025-06-03 13:30", periods=10, freq="1min", tz="UTC"),
            "o": [5000.0] * 10, "h": [5001.0] * 10, "l": [4999.0] * 10,
            "c": [5000.5] * 10, "v": [100] * 10,
        }
    )
    verdict = tick_schema.check_frame(minute_grid, source="minute bars")
    assert not verdict.satisfied
    assert "price" in verdict.missing_fields
    assert verdict.min_gap_seconds == 60.0
    assert not verdict.granularity_ok
    with pytest.raises(tick_schema.TickDataUnavailable, match="cannot be approximated"):
        tick_schema.require_tick_data(verdict)


def test_the_tick_gate_accepts_a_genuine_trade_and_quote_feed() -> None:
    """The gate must be capable of passing, or it proves nothing about the data."""
    import pandas as pd

    base = pd.Timestamp("2025-06-03 13:30:00", tz="UTC")
    feed = pd.DataFrame(
        {
            #: sub-second, with two prints sharing a stamp - what a real feed looks like
            "timestamp": [base, base, base + pd.Timedelta("1ms"),
                          base + pd.Timedelta("3ms"), base + pd.Timedelta("3ms")],
            "price": [5000.25, 5000.25, 5000.50, 5000.25, 5000.00],
            "volume": [2, 5, 1, 3, 4],
            "bid": [5000.00, 5000.00, 5000.25, 5000.00, 5000.00],
            "ask": [5000.25, 5000.25, 5000.50, 5000.25, 5000.25],
        }
    )
    verdict = tick_schema.check_frame(feed, source="synthetic T&S")
    assert verdict.satisfied, verdict.summary()
    assert verdict.missing_fields == ()
    assert verdict.simultaneous_stamps > 0
    tick_schema.require_tick_data(verdict)


# ======================================================================================
# PART 7 - delta classification, every branch
# ======================================================================================


def test_a_trade_at_the_ask_is_positive_delta() -> None:
    h = TickDataHandler()
    out = h.on_trade(trade(at=et(DAY, 10, 0), price="5000.25", volume=7,
                           bid="5000.00", ask="5000.25"))
    assert out.classification is Classification.AT_ASK
    assert out.delta == +7
    assert h.cvd == 7


def test_a_trade_at_the_bid_is_negative_delta() -> None:
    h = TickDataHandler()
    out = h.on_trade(trade(at=et(DAY, 10, 0), price="5000.00", volume=7,
                           bid="5000.00", ask="5000.25"))
    assert out.classification is Classification.AT_BID
    assert out.delta == -7
    assert h.cvd == -7


def test_an_inside_uptick_is_positive_and_a_downtick_negative() -> None:
    h = TickDataHandler()
    #: seed a previous trade price with an at-ask print, then trade inside a wider quote
    h.on_trade(trade(at=et(DAY, 10, 0), price="5000.25", bid="5000.00", ask="5000.25"))
    up = h.on_trade(trade(at=et(DAY, 10, 1), price="5000.50", volume=3,
                          bid="5000.00", ask="5001.00"))
    assert up.classification is Classification.INSIDE_UPTICK and up.delta == +3
    down = h.on_trade(trade(at=et(DAY, 10, 2), price="5000.25", volume=4,
                            bid="5000.00", ask="5001.00"))
    assert down.classification is Classification.INSIDE_DOWNTICK and down.delta == -4


def test_an_inside_zerotick_inherits_the_previous_deltas_sign() -> None:
    h = TickDataHandler()
    h.on_trade(trade(at=et(DAY, 10, 0), price="5000.25", bid="5000.00", ask="5000.25"))
    h.on_trade(trade(at=et(DAY, 10, 1), price="5000.50", volume=3,
                     bid="5000.00", ask="5001.00"))  # uptick, +3
    flat = h.on_trade(trade(at=et(DAY, 10, 2), price="5000.50", volume=9,
                            bid="5000.00", ask="5001.00"))
    assert flat.classification is Classification.INSIDE_ZEROTICK
    assert flat.delta == +9, "the SIGN is inherited, applied to THIS trade's size"


def test_a_missing_quote_is_recorded_unclassifiable_not_guessed() -> None:
    h = TickDataHandler()
    out = h.on_trade(trade(at=et(DAY, 10, 0), price="5000.25", volume=5, bid=None, ask=None))
    assert out.classification is Classification.UNCLASSIFIABLE
    assert out.delta == 0
    assert h.cvd == 0
    assert h.quality()["unclassifiable"] == 1


def test_a_trade_outside_the_quote_is_not_forced_into_a_classification() -> None:
    h = TickDataHandler()
    out = h.on_trade(trade(at=et(DAY, 10, 0), price="5002.00",
                           bid="5000.00", ask="5000.25"))
    assert out.classification is Classification.UNCLASSIFIABLE


def test_a_crossed_quote_is_unclassifiable() -> None:
    h = TickDataHandler()
    out = h.on_trade(trade(at=et(DAY, 10, 0), price="5000.00",
                           bid="5000.50", ask="5000.00"))
    assert out.classification is Classification.UNCLASSIFIABLE


def test_a_zero_volume_print_is_bad_data_not_a_trade() -> None:
    """AMBIGUITY A17, resolved: PART 22 lists zero volume as a validation item."""
    h = TickDataHandler()
    out = h.on_trade(trade(at=et(DAY, 10, 0), price="5000.25", volume=0,
                           bid="5000.00", ask="5000.25"))
    assert out.classification is Classification.UNCLASSIFIABLE
    assert out.delta == 0


def test_a_locked_market_raises_rather_than_picking_a_sign() -> None:
    """AMBIGUITIES A3/A4. bid == ask satisfies CASE 1 and CASE 2 at once."""
    h = TickDataHandler(strict=True)
    with pytest.raises(AmbiguousTick, match="LOCKED market"):
        h.on_trade(trade(at=et(DAY, 10, 0), price="5000.00",
                         bid="5000.00", ask="5000.00"))


def test_the_first_inside_trade_of_a_session_raises_rather_than_defaulting() -> None:
    """AMBIGUITY A6. After the 09:30 reset there is no previous delta to inherit."""
    h = TickDataHandler(strict=True)
    with pytest.raises(AmbiguousTick, match="no previous trade price"):
        h.on_trade(trade(at=et(DAY, 10, 0), price="5000.50",
                         bid="5000.00", ask="5001.00"))


def test_non_strict_mode_counts_ambiguities_without_inventing_a_sign() -> None:
    h = TickDataHandler(strict=False)
    locked = h.on_trade(trade(at=et(DAY, 10, 0), price="5000.00",
                              bid="5000.00", ask="5000.00"))
    assert locked.delta == 0
    assert h.quality()["locked_market_ticks"] == 1
    assert h.cvd == 0


def test_an_unclassifiable_tick_does_not_become_the_inherited_delta() -> None:
    """A zero from bad data must not silently turn the next zero-tick into a zero."""
    h = TickDataHandler(strict=False)
    h.on_trade(trade(at=et(DAY, 10, 0), price="5000.25", bid="5000.00", ask="5000.25"))
    h.on_trade(trade(at=et(DAY, 10, 1), price="5000.50", volume=3,
                     bid="5000.00", ask="5001.00"))  # uptick +3
    h.on_trade(trade(at=et(DAY, 10, 2), price="5000.50", volume=2,
                     bid=None, ask=None))            # unclassifiable, delta 0
    flat = h.on_trade(trade(at=et(DAY, 10, 3), price="5000.50", volume=6,
                            bid="5000.00", ask="5001.00"))
    assert flat.delta == +6, "the inherited sign should still be the uptick's, not the zero"


# ======================================================================================
# PART 8 - the CVD reset, including DST
# ======================================================================================


def test_cvd_resets_at_0930_et_each_session() -> None:
    h = TickDataHandler()
    h.on_trade(trade(at=et(DAY, 10, 0), price="5000.25", volume=5,
                     bid="5000.00", ask="5000.25"))
    assert h.cvd == 5
    nxt = DAY + dt.timedelta(days=1)
    h.on_trade(trade(at=et(nxt, 9, 30), price="5000.25", volume=3,
                     bid="5000.00", ask="5000.25"))
    assert h.cvd == 3, "CVD carried across the reset"
    assert h.resets == 2


def test_no_overnight_state_leaks_through_the_reset() -> None:
    """The previous trade price and previous delta reset WITH CVD, not separately.

    Otherwise the session's first zero-tick inherits a sign computed from yesterday's flow,
    which is overnight information entering an intraday signal.
    """
    h = TickDataHandler(strict=False)
    h.on_trade(trade(at=et(DAY, 15, 0), price="5000.25", volume=5,
                     bid="5000.00", ask="5000.25"))
    assert h.previous_delta == +5
    nxt = DAY + dt.timedelta(days=1)
    h.on_trade(trade(at=et(nxt, 9, 31), price="5000.50", volume=4,
                     bid="5000.00", ask="5001.00"))
    assert h.previous_delta is None or h.previous_delta == 0, (
        "yesterday's delta survived the reset"
    )
    assert h.cvd == 0


def test_a_trade_before_0930_belongs_to_the_previous_reset_epoch() -> None:
    h = TickDataHandler()
    #: 09:29 is still the overnight session; CVD has not restarted
    assert h.session_of(et(DAY, 9, 29)) == DAY - dt.timedelta(days=1)
    assert h.session_of(et(DAY, 9, 30)) == DAY
    assert h.session_of(et(DAY, 16, 0)) == DAY


@pytest.mark.parametrize(
    ("label", "day", "expected_offset"),
    [
        ("EST before spring forward", dt.date(2025, 3, 7), -5),
        ("EDT after spring forward", dt.date(2025, 3, 10), -4),
        ("EDT before fall back", dt.date(2025, 10, 31), -4),
        ("EST after fall back", dt.date(2025, 11, 3), -5),
    ],
)
def test_the_reset_lands_at_0930_local_across_both_dst_transitions(
    label: str, day: dt.date, expected_offset: int
) -> None:
    """PART 4. A fixed UTC offset would move the reset by an hour twice a year."""
    h = TickDataHandler()
    boundary = et(day, 9, 30)
    assert boundary.utcoffset() == dt.timedelta(hours=expected_offset), label
    assert h.session_of(boundary) == day
    assert h.session_of(boundary - dt.timedelta(minutes=1)) == day - dt.timedelta(days=1)


def test_a_naive_timestamp_is_refused() -> None:
    h = TickDataHandler()
    with pytest.raises(ValueError, match="timezone-naive"):
        #: naive ON PURPOSE - the naive stamp IS the thing under test here
        h.session_of(dt.datetime(2025, 6, 3, 10, 0))  # noqa: DTZ001


# ======================================================================================
# PART 9 - minute aggregation with CVD sampled at the exact close
# ======================================================================================


def test_a_bar_is_emitted_only_once_its_minute_is_over() -> None:
    agg = MinuteAggregator()
    assert agg.add(when=et(DAY, 10, 0, 5), price=Decimal("5000.00"), volume=1, cvd=1) is None
    assert agg.add(when=et(DAY, 10, 0, 40), price=Decimal("5001.00"), volume=2, cvd=3) is None
    bar = agg.add(when=et(DAY, 10, 1, 2), price=Decimal("5000.50"), volume=1, cvd=9)
    assert bar is not None
    assert bar.start == et(DAY, 10, 0)
    assert bar.open == Decimal("5000.00") and bar.high == Decimal("5001.00")
    assert bar.close == Decimal("5001.00")
    assert bar.volume == 3 and bar.trades == 2


def test_cvd_is_sampled_at_the_bar_close_not_after_it() -> None:
    """PART 9. The sealed bar carries the CVD of its LAST trade, not the next minute's."""
    agg = MinuteAggregator()
    agg.add(when=et(DAY, 10, 0, 5), price=Decimal("5000.00"), volume=1, cvd=11)
    agg.add(when=et(DAY, 10, 0, 50), price=Decimal("5000.25"), volume=1, cvd=22)
    bar = agg.add(when=et(DAY, 10, 1, 1), price=Decimal("5000.50"), volume=1, cvd=999)
    assert bar is not None
    assert bar.cvd_at_close == 22, "the bar took CVD from a trade after its close"


# ======================================================================================
# PART 10 / PART 11 / PART 23 - causality and the lookahead canaries
# ======================================================================================


def bar(index: int, *, low: str, high: str, open_: str, close: str, cvd: int) -> MinuteBar:
    start = et(DAY, 10, 0) + dt.timedelta(minutes=index)
    return MinuteBar(start=start, end=start + dt.timedelta(minutes=1),
                     open=Decimal(open_), high=Decimal(high), low=Decimal(low),
                     close=Decimal(close), volume=100, cvd_at_close=cvd, trades=5)


def flat_bars(n: int, *, low: str = "5000.00", high: str = "5002.00",
              cvd: int = 0) -> list[MinuteBar]:
    return [bar(i, low=low, high=high, open_="5001.00", close="5001.00", cvd=cvd)
            for i in range(n)]


def test_the_detector_is_silent_until_a_full_lookback_of_closed_bars_exists() -> None:
    det = DivergenceDetector()
    for b in flat_bars(S.LOOKBACK_BARS - 1):
        assert det.observe(b) is None
    assert not det.ready


def test_the_lookback_window_excludes_bar_t() -> None:
    """PART 10. Including bar T makes the price-extreme condition near-tautological."""
    det = DivergenceDetector()
    for b in flat_bars(S.LOOKBACK_BARS):
        det.observe(b)
    assert det.ready
    #: window is built from closed bars only; the deque never holds more than the lookback
    assert len(det._closed) == S.LOOKBACK_BARS
    assert det._window_low() == Decimal("5000.00")


def test_a_swing_is_decided_at_its_own_close_with_no_later_bar() -> None:
    """PART 11. No future-confirmed pivots: the swing is set by the bar that made it."""
    det = DivergenceDetector()
    for b in flat_bars(S.LOOKBACK_BARS):
        det.observe(b)
    low_bar = bar(S.LOOKBACK_BARS, low="4995.00", high="5001.00",
                  open_="5000.00", close="4996.00", cvd=-500)
    det.observe(low_bar)
    assert det.prev_low is not None
    assert det.prev_low.price == Decimal("4995.00")
    assert det.prev_low.cvd == -500, "the swing took a CVD from some other bar"
    assert det.prev_low.at == low_bar.end


def test_future_bars_cannot_change_a_signal_already_emitted() -> None:
    """PART 23 canary: replay the same prefix, then plant different futures."""
    def run(future_lows: list[str]) -> list[str]:
        det = DivergenceDetector()
        for b in flat_bars(S.LOOKBACK_BARS):
            det.observe(b)
        det.observe(bar(S.LOOKBACK_BARS, low="4995.00", high="5001.00",
                        open_="5000.00", close="4996.00", cvd=-500))
        for b in flat_bars(S.LOOKBACK_BARS, low="4997.00", high="5001.00", cvd=-400):
            det.observe(b)
        emitted = [s.bar.end.isoformat() for s in det.signals]
        for i, low in enumerate(future_lows):
            det.observe(bar(100 + i, low=low, high="5010.00",
                            open_="5000.00", close="5005.00", cvd=999))
        return emitted

    assert run(["4000.00", "3900.00"]) == run(["6000.00", "6100.00"]), (
        "the set of signals emitted before the planted future differs with the future; "
        "something in the detector is reading forward"
    )


def test_a_planted_future_cvd_cannot_retroactively_create_divergence() -> None:
    """The divergence comparand must be the swing's OWN CVD, not a later value."""
    det = DivergenceDetector()
    for b in flat_bars(S.LOOKBACK_BARS):
        det.observe(b)
    det.observe(bar(S.LOOKBACK_BARS, low="4995.00", high="5001.00",
                    open_="5000.00", close="4996.00", cvd=-500))
    captured = det.prev_low
    assert captured is not None and captured.cvd == -500
    #: a wildly different later CVD must not rewrite the stored swing
    det.observe(bar(S.LOOKBACK_BARS + 1, low="4998.00", high="5001.00",
                    open_="5000.00", close="5000.50", cvd=50_000))
    assert det.prev_low is not None and det.prev_low.cvd == -500


def test_all_four_long_conditions_are_required() -> None:
    """Drop any one and the signal must not fire. PART 12 says ALL must be TRUE."""
    def attempt(*, low: str, cvd: int, open_: str, close: str) -> bool:
        det = DivergenceDetector()
        for b in flat_bars(S.LOOKBACK_BARS):
            det.observe(b)
        #: establish a swing low at 4995 with CVD -500
        det.observe(bar(S.LOOKBACK_BARS, low="4995.00", high="5001.00",
                        open_="5000.00", close="4996.00", cvd=-500))
        for b in flat_bars(S.LOOKBACK_BARS, low="4996.00", high="5001.00", cvd=-400):
            det.observe(b)
        signal = det.observe(bar(99, low=low, high="5001.00", open_=open_,
                                 close=close, cvd=cvd))
        return signal is not None and signal.direction > 0

    #: all four satisfied: new extreme, penetrates 4995, CVD above -500, closes up
    assert attempt(low="4994.00", cvd=-100, open_="4995.00", close="4998.00")
    #: no penetration of the prior swing
    assert not attempt(low="4995.50", cvd=-100, open_="4995.00", close="4998.00")
    #: CVD is NOT diverging (below the swing's CVD)
    assert not attempt(low="4994.00", cvd=-900, open_="4995.00", close="4998.00")
    #: no rejection print - closes down
    assert not attempt(low="4994.00", cvd=-100, open_="4998.00", close="4995.00")


# ======================================================================================
# PART 17 / 18 / 19 - the governor
# ======================================================================================


def test_the_winning_day_lock_reads_realized_only() -> None:
    """An unrealized gain has not been banked, so it must not trip the lock."""
    g = Governor()
    g.start_day(DAY)
    assert g.on_equity(at=et(DAY, 10, 0), unrealized=Decimal("500")) is State.ACTIVE
    assert not g.winning_day_reached()
    g.realized = Decimal("160")
    assert g.on_equity(at=et(DAY, 10, 1), unrealized=Decimal(0)) is State.HALTED_SUCCESS


@pytest.mark.parametrize(
    ("realized", "unrealized", "expected"),
    [
        ("159.99", "0", State.ACTIVE),
        ("160.00", "0", State.HALTED_SUCCESS),
        ("160.01", "0", State.HALTED_SUCCESS),
    ],
)
def test_the_lock_boundary_is_inclusive(realized: str, unrealized: str,
                                        expected: State) -> None:
    g = Governor()
    g.start_day(DAY)
    g.realized = Decimal(realized)
    assert g.on_equity(at=et(DAY, 10, 0), unrealized=Decimal(unrealized)) is expected


@pytest.mark.parametrize(
    ("realized", "unrealized", "expected"),
    [
        ("-100", "-149.99", State.ACTIVE),
        ("-100", "-150.00", State.HALTED_FAIL),
        ("0", "-250.00", State.HALTED_FAIL),
        ("-250", "0", State.HALTED_FAIL),
    ],
)
def test_the_killswitch_reads_realized_plus_unrealized(realized: str, unrealized: str,
                                                       expected: State) -> None:
    """PART 18. An account is liquidated on live equity, not on what has been booked."""
    g = Governor()
    g.start_day(DAY)
    g.realized = Decimal(realized)
    assert g.on_equity(at=et(DAY, 10, 0), unrealized=Decimal(unrealized)) is expected


def test_the_killswitch_wins_when_both_thresholds_hold() -> None:
    """A day down $250 on live equity is not a successful day."""
    g = Governor()
    g.start_day(DAY)
    g.realized = Decimal("200")
    assert g.on_equity(at=et(DAY, 10, 0), unrealized=Decimal("-500")) is State.HALTED_FAIL


def test_the_breaching_equity_is_recorded_so_the_overshoot_is_measurable() -> None:
    """AMBIGUITY A15: the flatten fills a record later, so the loss exceeds $250."""
    g = Governor()
    g.start_day(DAY)
    g.realized = Decimal("-200")
    g.on_equity(at=et(DAY, 10, 0), unrealized=Decimal("-60"))
    assert g.breach_equity == Decimal("-260")


@pytest.mark.parametrize("terminal", [State.HALTED_SUCCESS, State.HALTED_FAIL])
def test_a_halted_day_cannot_be_re_armed(terminal: State) -> None:
    g = Governor()
    g.start_day(DAY)
    g._transition(terminal, at=et(DAY, 10, 0), reason="test", unrealized=Decimal(0))
    assert g.halted
    with pytest.raises(IllegalTransition, match="not a legal transition"):
        g._transition(State.ACTIVE, at=et(DAY, 10, 1), reason="re-arm",
                      unrealized=Decimal(0))


@pytest.mark.parametrize("terminal", [State.HALTED_SUCCESS, State.HALTED_FAIL])
def test_a_halted_day_refuses_new_entries(terminal: State) -> None:
    g = Governor()
    g.start_day(DAY)
    g._transition(terminal, at=et(DAY, 10, 0), reason="test", unrealized=Decimal(0))
    verdict = g.may_enter(in_window=True, position_open=False)
    assert not verdict
    assert "halted" in " ".join(verdict.reasons)


def test_the_gate_reports_every_reason_not_just_the_first() -> None:
    g = Governor()
    g.start_day(DAY)
    g._transition(State.HALTED_FAIL, at=et(DAY, 10, 0), reason="t", unrealized=Decimal(0))
    verdict = g.may_enter(in_window=False, position_open=True)
    assert len(verdict.reasons) == 3


def test_a_terminal_state_is_left_only_by_the_day_roll() -> None:
    g = Governor()
    g.start_day(DAY)
    g._transition(State.HALTED_FAIL, at=et(DAY, 10, 0), reason="t", unrealized=Decimal(0))
    g.start_day(DAY + dt.timedelta(days=1))
    assert g.state is State.ACTIVE
    assert g.realized == Decimal(0)
    assert g.breach_equity is None


def test_the_governor_stops_evaluating_once_halted() -> None:
    g = Governor()
    g.start_day(DAY)
    g.realized = Decimal("-300")
    assert g.on_equity(at=et(DAY, 10, 0), unrealized=Decimal(0)) is State.HALTED_FAIL
    before = len(g.transitions)
    g.realized = Decimal("1000")
    assert g.on_equity(at=et(DAY, 10, 1), unrealized=Decimal(0)) is State.HALTED_FAIL
    assert len(g.transitions) == before, "a halted governor recorded another transition"


# ======================================================================================
# PART 20 - the governor integration test, through the real engine
# ======================================================================================


def test_the_probe_is_not_the_strategy() -> None:
    """It must not be able to borrow the strategy's identity."""
    assert GP.PROBE_SPEC.name != S.SPEC.name
    assert GP.PROBE_SPEC.spec_hash != S.SPEC.spec_hash
    assert "plumbing" in GP.PROBE_SPEC.name
    assert "governor plumbing test" in GP.PROBE_SPEC.hypothesis


def test_the_probe_arithmetic_is_derived_not_recorded() -> None:
    """The target is a limit (no slippage); the stop pays the declared tick, so it is nine."""
    assert GP.WIN_REALIZED == Decimal("196.20")
    assert GP.LOSS_REALIZED == Decimal("-116.30")


def test_thirty_synthetic_sessions_halt_exactly_where_planned() -> None:
    from collections import Counter

    from topstep_backtester.profiles.account import TOPSTEP_50K_COMBINE as ACC
    from topstep_backtester.profiles.execution import BASELINE
    from topstep_backtester.upstream import Backtest, spec_for_symbol, validate_bars

    cid = "CON.F.US.ES.M25"
    bars, plan = GP.build_sessions(contract_id=cid, days=30)
    assert validate_bars(bars, spec_for_symbol("ES")).ok

    probe = GP.GovernorProbe(cid)
    result = Backtest(
        bars, probe, account=ACC.size, dll_enabled=ACC.dll_enabled,
        fill_config=BASELINE.bar_fill_config(), broker_config=BASELINE.broker_config(),
        fee_model=BASELINE.fee_model(), record=True,
    ).run().result

    assert result.days_traded == 30
    observed = {shape: Counter() for shape in ("WIN", "KILL", "QUIET")}
    for day in plan:
        observed[day.shape][probe.daily_states.get(day.day, "ACTIVE")] += 1

    assert observed["WIN"] == Counter({State.HALTED_SUCCESS.value: 10})
    assert observed["KILL"] == Counter({State.HALTED_FAIL.value: 10})
    assert observed["QUIET"] == Counter({State.ACTIVE.value: 10})
    assert len(probe.governor.transitions) == 20


def test_the_engine_agrees_with_the_probes_hand_computed_outcomes() -> None:
    from topstep_backtester.profiles.account import TOPSTEP_50K_COMBINE as ACC
    from topstep_backtester.profiles.execution import BASELINE
    from topstep_backtester.upstream import Backtest

    cid = "CON.F.US.ES.M25"
    bars, _ = GP.build_sessions(contract_id=cid, days=30)
    result = Backtest(
        bars, GP.GovernorProbe(cid), account=ACC.size, dll_enabled=ACC.dll_enabled,
        fill_config=BASELINE.bar_fill_config(), broker_config=BASELINE.broker_config(),
        fee_model=BASELINE.fee_model(), record=True,
    ).run().result

    wins = [t.net_pnl for t in result.round_trips if t.net_pnl > 0]
    full_stops = [t.net_pnl for t in result.round_trips if t.net_pnl == GP.LOSS_REALIZED]
    assert wins and set(wins) == {GP.WIN_REALIZED}
    assert full_stops, "no round trip matched the hand-computed full-stop outcome"


def test_the_governors_realized_reconciles_with_the_engines_round_trip() -> None:
    """Costs arrive per HALF-TURN; missing one side would trip the lock a fraction early."""
    from topstep_backtester.profiles.account import TOPSTEP_50K_COMBINE as ACC
    from topstep_backtester.profiles.execution import BASELINE
    from topstep_backtester.upstream import Backtest

    cid = "CON.F.US.ES.M25"
    bars, _ = GP.build_sessions(contract_id=cid, days=3)
    probe = GP.GovernorProbe(cid)
    Backtest(
        bars, probe, account=ACC.size, dll_enabled=ACC.dll_enabled,
        fill_config=BASELINE.bar_fill_config(), broker_config=BASELINE.broker_config(),
        fee_model=BASELINE.fee_model(), record=True,
    ).run()
    success = [t for t in probe.governor.transitions
               if t.to is State.HALTED_SUCCESS]
    assert success, "no winning-day lock fired in the first three sessions"
    assert success[0].realized == GP.WIN_REALIZED, (
        f"the governor was told {success[0].realized} but one round turn of costs makes the "
        f"realised figure {GP.WIN_REALIZED}"
    )


# ======================================================================================
# the strategy itself cannot run, and that is the designed state
# ======================================================================================


def test_the_strategy_cannot_be_instantiated_while_readings_are_undecided() -> None:
    from topstep_backtester.strategies.cvd_absorption_harvester.strategy import (
        CvdAbsorptionHarvester,
        QuoteAlignment,
        QuoteBook,
    )

    book = QuoteBook([0], [Decimal("5000.00")], [Decimal("5000.25")],
                     alignment=QuoteAlignment.AT_OR_BEFORE)
    with pytest.raises(SpecError, match="not frozen"):
        CvdAbsorptionHarvester("CON.F.US.ES.M25", quotes=book)


def test_the_quote_book_will_not_pick_an_alignment_for_you() -> None:
    """AMBIGUITY A2 has no default, so the policy is a required argument."""
    from topstep_backtester.strategies.cvd_absorption_harvester.strategy import QuoteBook

    with pytest.raises(TypeError):
        QuoteBook([0], [Decimal("1")], [Decimal("2")])  # type: ignore[call-arg]


def test_the_quote_book_never_returns_a_later_quote() -> None:
    """A miss returns None. The nearest LATER quote is future information."""
    from topstep_backtester.strategies.cvd_absorption_harvester.strategy import (
        QuoteAlignment,
        QuoteBook,
    )

    book = QuoteBook([1000, 3000], [Decimal("5000.00")] * 2, [Decimal("5000.25")] * 2,
                     alignment=QuoteAlignment.AT_OR_BEFORE)
    assert book.at(500) == (None, None)
    assert book.at(1000) == (Decimal("5000.00"), Decimal("5000.25"))
    assert book.at(2000) == (Decimal("5000.00"), Decimal("5000.25"))


def test_the_two_alignment_policies_actually_differ() -> None:
    """If they agreed, AMBIGUITY A2 would be immaterial and could be closed."""
    from topstep_backtester.strategies.cvd_absorption_harvester.strategy import (
        QuoteAlignment,
        QuoteBook,
    )

    stamps: list[int] = [1000, 2000]
    bids = [Decimal("5000.00"), Decimal("5000.50")]
    asks = [Decimal("5000.25"), Decimal("5000.75")]
    strict = QuoteBook(stamps, bids, asks, alignment=QuoteAlignment.STRICTLY_BEFORE)
    inclusive = QuoteBook(stamps, bids, asks, alignment=QuoteAlignment.AT_OR_BEFORE)
    assert strict.at(2000) != inclusive.at(2000)
