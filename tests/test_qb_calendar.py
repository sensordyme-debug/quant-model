"""The calendar that closes AUD-07.

The defect these tests exist to prevent: `intraday_common.FLATTEN_MINUTE = 368` is the
368th minute after 09:30 and there is no such bar on a 13:00 early close, so the live
sleeve never flattens and carries the position into the 15:45 daily rebalance.

Two things are therefore pinned hard: that early closes are 210 minutes rather than 390,
and that a close-relative offset lands on a real bar on both kinds of day. Everything else
here guards the table itself, because a hand-typed holiday list is only as good as the
checks on it.
"""
from __future__ import annotations

import datetime as dt

import pytest

from quant_brain.core.calendar import CalendarCoverageError, Session, easter, good_friday
from quant_brain.markets.equity_us import CALENDAR

D = dt.date


# --------------------------------------------------------------------------- the AUD-07 bug

def test_regular_session_is_390_minutes():
    assert CALENDAR.session_minutes(D(2026, 9, 11)) == 390


def test_early_close_is_210_minutes_not_390():
    """The whole defect in one assertion: 2026-11-27 has no 368th bar."""
    assert CALENDAR.session_minutes(D(2026, 11, 27)) == 210
    assert 368 > 210, "if this ever fails the constant stopped being out of range"


def test_flatten_offset_lands_inside_the_session_on_both_day_types():
    """`minutes_before_close(22)` is the shape AUD-07 asks for: 15:38 / 12:38."""
    regular = CALENDAR.minutes_before_close(D(2026, 9, 11), 22)
    early = CALENDAR.minutes_before_close(D(2026, 11, 27), 22)
    total_early = CALENDAR.session_minutes(D(2026, 11, 27))
    # Both accessors return None on a closed day. Asserting they are not None before
    # comparing is the point rather than noise: an unguarded `early < total_early` raises
    # TypeError instead of failing, which is how an Optional turns a red test into a crash.
    assert regular is not None and early is not None and total_early is not None
    assert regular == 368                      # unchanged behaviour on a normal day
    assert early == 188                        # 210 - 22, i.e. 12:38 ET
    assert early < total_early


def test_minutes_before_close_clamps_rather_than_going_negative():
    """A session shorter than the offset must yield 0, never a negative bar index."""
    assert CALENDAR.minutes_before_close(D(2026, 11, 27), 500) == 0


def test_closed_day_returns_none_everywhere():
    thanksgiving = D(2026, 11, 26)
    assert CALENDAR.is_trading_day(thanksgiving) is False
    assert CALENDAR.session(thanksgiving) is None
    assert CALENDAR.session_minutes(thanksgiving) is None
    assert CALENDAR.minutes_before_close(thanksgiving, 22) is None


# --------------------------------------------------------------------------- the table

def test_next_early_close_is_the_one_the_audit_named():
    """research/audit_2026-09-12.md AUD-07: 'Next early close is 2026-11-27.'"""
    after_audit = sorted(d for d in CALENDAR.early_closes() if d > D(2026, 9, 12))
    assert after_audit[0] == D(2026, 11, 27)


def test_good_fridays_match_an_independent_computation():
    """Checks a whole holiday family against the Easter algorithm, not against itself."""
    missing = CALENDAR.expected_good_fridays() - CALENDAR.holidays()
    assert not missing, f"Good Fridays absent from the holiday table: {sorted(missing)}"


def test_easter_algorithm_on_known_years():
    assert easter(2024) == D(2024, 3, 31)
    assert easter(2026) == D(2026, 4, 5)
    assert good_friday(2026) == D(2026, 4, 3)


def test_no_date_is_both_a_holiday_and_an_early_close():
    assert not (CALENDAR.holidays() & CALENDAR.early_closes())


def test_no_weekend_appears_in_either_table():
    for d in CALENDAR.holidays() | CALENDAR.early_closes():
        assert d.weekday() < 5, f"{d} is a weekend and does not belong in the table"


def test_every_early_close_is_a_trading_day():
    for d in CALENDAR.early_closes():
        assert CALENDAR.is_trading_day(d), f"{d} is flagged early-close but is not open"


def test_days_of_mourning_are_closed():
    """Not rule-derivable; they look like data gaps in any bar store (AUD-24)."""
    assert not CALENDAR.is_trading_day(D(2018, 12, 5))   # G. H. W. Bush
    assert not CALENDAR.is_trading_day(D(2025, 1, 9))    # Carter


@pytest.mark.parametrize("year,count", [(2024, 10), (2025, 11), (2026, 10)])
def test_holiday_counts_per_year(year, count):
    """A typo that drops or duplicates a date changes the count for that year."""
    got = sum(1 for d in CALENDAR.holidays() if d.year == year)
    assert got == count


def test_trading_day_count_for_a_full_year_is_plausible():
    """2024 had 252 US equity sessions. A table error moves this."""
    days = CALENDAR.trading_days(D(2024, 1, 1), D(2024, 12, 31))
    assert len(days) == 252


def test_weekends_are_never_trading_days():
    assert not CALENDAR.is_trading_day(D(2026, 9, 12))   # Saturday
    assert not CALENDAR.is_trading_day(D(2026, 9, 13))   # Sunday


# --------------------------------------------------------------------------- safety

def test_beyond_coverage_raises_rather_than_guessing():
    """Part 18: UNKNOWN STATE = DO NOT TRADE. A guessed session is worse than an error."""
    with pytest.raises(CalendarCoverageError):
        CALENDAR.session(D(2031, 3, 4))


def test_is_trading_day_does_not_raise_beyond_coverage():
    """Deliberate asymmetry: cheap weekday screening stays usable, but anything that could
    put an order on the wire (`session`) refuses. Documented so it is not read as a hole."""
    assert CALENDAR.is_trading_day(D(2031, 3, 4)) is True


def test_next_trading_day_skips_the_thanksgiving_weekend():
    assert CALENDAR.next_trading_day(D(2026, 11, 25)) == D(2026, 11, 27)
    assert CALENDAR.next_trading_day(D(2026, 11, 27)) == D(2026, 11, 30)


def test_session_spanning_midnight_measures_correctly():
    """Guards the CME-shaped case before the futures calendar depends on it."""
    s = Session(day=D(2026, 9, 10), open_t=dt.time(18, 0), close_t=dt.time(17, 0),
                spans_midnight=True)
    assert s.minutes == 23 * 60
