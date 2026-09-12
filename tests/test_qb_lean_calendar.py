"""LEAN's market-hours database as a SessionCalendar.

The audit question was: does LEAN already provide the CME calendar, so we do not build one?
It does. 552 entries, all nine target futures roots present, with the 17:00-18:00 daily
maintenance break encoded as the gap between the market and postmarket segments.

The cross-check tests are the point of this file. My hand-typed NYSE table and LEAN's were
built completely independently - mine from the published NYSE schedule, LEAN's by
QuantConnect - and they agree on every probe including the two days of mourning that are not
rule-derivable. Two independent tables agreeing is worth more than either alone, so the
hand-typed one is kept as a cross-check rather than deleted.

Every test skips rather than fails when LEAN is not beside the repository: it is a separate
checkout (`..\\Lean`) and a fresh clone should not report a false failure.
"""
from __future__ import annotations

import datetime as dt

import pytest

from quant_brain.core.calendar import CalendarCoverageError
from quant_brain.markets.lean_calendar import (
    DEFAULT_DB,
    LeanMarketHoursCalendar,
    _parse_lean_date,
    _parse_lean_time,
    cme_future,
    equity_usa,
)

D = dt.date
pytestmark = pytest.mark.skipif(not DEFAULT_DB.exists(),
                                reason="LEAN not checked out beside the repo")


# ------------------------------------------------------------------ parsing LEAN's format

def test_lean_dates_parse():
    assert _parse_lean_date("1/15/2018") == D(2018, 1, 15)
    assert _parse_lean_date("12/25/2026") == D(2026, 12, 25)
    assert _parse_lean_date("nonsense") is None


def test_the_day_rolling_timespan_is_midnight_at_the_END_of_the_day():
    """LEAN writes '1.00:00:00' for end-of-day. Reading it as 00:00 would make a Globex
    session measure as zero minutes long."""
    t, rolls = _parse_lean_time("1.00:00:00")
    assert t == dt.time(0, 0) and rolls is True
    t2, rolls2 = _parse_lean_time("17:00:00")
    assert t2 == dt.time(17, 0) and rolls2 is False


# ------------------------------------------------------------------ futures: the whole point

@pytest.mark.parametrize("root,expected_key", [
    ("ES", "Future-cme-ES"), ("MES", "Future-cme-MES"), ("NQ", "Future-cme-NQ"),
    ("MNQ", "Future-cme-MNQ"), ("RTY", "Future-cme-RTY"), ("M2K", "Future-cme-M2K"),
    ("CL", "Future-nymex-CL"), ("GC", "Future-comex-GC"), ("YM", "Future-cbot-YM"),
])
def test_every_target_contract_has_a_lean_calendar(root, expected_key):
    """The CME calendar was the futures branch's blocking gap. It is not missing."""
    c = cme_future(root)
    assert c.key == expected_key
    assert c.is_trading_day(D(2026, 9, 11))


def test_the_maintenance_break_is_a_gap_between_segments():
    """17:00-18:00 daily. It is why segments are read rather than just an open and a close."""
    segs = cme_future("ES").segments(D(2026, 9, 14))       # a Monday
    states = [s[2] for s in segs]
    assert "market" in states and "postmarket" in states
    market_end = next(b for _a, b, st in segs if st == "market")
    post_start = next(a for a, _b, st in segs if st == "postmarket")
    assert market_end == dt.time(17, 0)
    assert post_start == dt.time(18, 0), "the hour between them is the maintenance break"


def test_is_open_at_returns_false_inside_the_maintenance_break():
    es = cme_future("ES")
    assert es.is_open_at(dt.datetime(2026, 9, 14, 15, 0))     # market
    assert not es.is_open_at(dt.datetime(2026, 9, 14, 17, 30))  # the break
    assert es.is_open_at(dt.datetime(2026, 9, 14, 19, 0))     # Globex evening


def test_friday_has_no_evening_reopen():
    """Friday closes at 17:00 and does not reopen until Sunday - a real session difference."""
    fri = cme_future("ES").segments(D(2026, 9, 11))
    assert "postmarket" not in [s[2] for s in fri]
    sess = cme_future("ES").session(D(2026, 9, 11))
    assert sess is not None and sess.minutes == 1020    # 00:00 -> 17:00


def test_rth_mode_narrows_a_future_to_the_regular_session():
    """A futures strategy trades Globex; an equity-style question wants 09:30-16:00-ish."""
    full = cme_future("ES", rth=False).session(D(2026, 9, 11))
    rth = cme_future("ES", rth=True).session(D(2026, 9, 11))
    assert full is not None and rth is not None
    assert rth.minutes < full.minutes
    assert rth.open_t == dt.time(9, 30)


def test_futures_carry_early_closes_and_late_opens():
    es = cme_future("ES")
    assert len(es._early) > 100, "LEAN records 169 early closes for ES"
    assert len(es._late) > 50


def test_an_unknown_root_names_the_exchanges_it_tried():
    with pytest.raises(KeyError, match="cme"):
        cme_future("NOTAREALCONTRACT")


# ------------------------------------------------- cross-check against the hand-typed table

@pytest.mark.parametrize("day", [
    D(2026, 11, 26),   # Thanksgiving
    D(2025, 1, 9),     # day of mourning, Carter - not rule-derivable
    D(2018, 12, 5),    # day of mourning, G.H.W. Bush - not rule-derivable
    D(2026, 7, 3),     # observed July 4
    D(2026, 11, 27),   # the next early close, 210 minutes
    D(2026, 12, 24),   # early close
    D(2026, 9, 11),    # an ordinary session, 390 minutes
    D(2024, 7, 3),     # early close
    D(2026, 1, 1),     # New Year
])
def test_lean_and_the_hand_typed_table_agree(day):
    """Two independently-built tables. Disagreement means one of them is wrong and the
    trading decision that rests on it is unsafe."""
    from quant_brain.markets.equity_us import CALENDAR as hand
    lean = equity_usa()
    assert hand.is_trading_day(day) == lean.is_trading_day(day), f"open/closed differs on {day}"
    assert hand.session_minutes(day) == lean.session_minutes(day), f"length differs on {day}"


def test_lean_has_strictly_more_history_than_the_hand_typed_table():
    """Which is why LEAN is the better source once it is proven to agree."""
    from quant_brain.markets.equity_us import CALENDAR as hand
    lean = equity_usa()
    assert len(lean._holidays) > len(hand.holidays())
    assert len(lean._early) > len(hand.early_closes())


def test_the_equity_calendar_reports_a_regular_session_as_390_minutes():
    assert equity_usa().session_minutes(D(2026, 9, 11)) == 390


def test_the_next_early_close_is_210_minutes_in_leans_table_too():
    """AUD-07's date, confirmed by a second independent source."""
    assert equity_usa().session_minutes(D(2026, 11, 27)) == 210


# ------------------------------------------------------------------ housekeeping

def test_available_lists_keys_rather_than_making_a_caller_guess():
    keys = LeanMarketHoursCalendar.available(prefix="Future-cme-")
    assert len(keys) > 20 and "Future-cme-ES" in keys


def test_coverage_end_is_honest_about_the_tables_limit():
    """Past the furthest special date the calendar refuses rather than guessing."""
    lean = equity_usa()
    assert lean.coverage_end.year >= 2026
    with pytest.raises(CalendarCoverageError):
        lean.session(D(2099, 1, 4))


def test_a_missing_database_raises_a_message_that_says_where_to_look():
    with pytest.raises(FileNotFoundError, match="market-hours"):
        LeanMarketHoursCalendar("Equity-usa-[*]", db_path="/nonexistent/mhdb.json")
