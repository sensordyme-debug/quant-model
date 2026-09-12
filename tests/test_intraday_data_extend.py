"""D-4 / AUD-16: pin the two decisions the IBKR minute fetcher makes without a network.

`scripts/intraday_data.py` never asks IBKR a question it has not already answered locally:

    WHEN may a request end?          `snap_after_close` / `last_safe_end`
    WHICH windows are worth asking?  `sessions_needed` / `fetch_symbol`'s skip

Both were wrong in the same direction - they trusted the wall clock and a bar count - and the
two defects hid each other: the fetcher wrote a truncated session, then counted it as present
and refused to fetch the month again, so the store froze at a half day and stayed there.

Every test here runs against the REAL US equity calendar, because the off-by-ones that matter
are calendar facts: an early close is a complete 210-minute session and must never be
re-requested, a holiday has no session to truncate, and "today" is only safe once it is over.
"""
from __future__ import annotations

import datetime as dt

import pytest

pytest.importorskip("pyarrow", reason="the minute store is parquet; 3.11 has no engine")

import intraday_data as idata  # noqa: E402
import pandas as pd  # noqa: E402
import store_health as sh  # noqa: E402
from intraday_common import ET  # noqa: E402

from quant_brain.markets.equity_us import CALENDAR  # noqa: E402

REGULAR = dt.date(2026, 9, 11)        # ordinary 390-minute Friday
EARLY = dt.date(2026, 11, 27)         # day after Thanksgiving, 13:00 close, 210 minutes
HOLIDAY = dt.date(2026, 11, 26)       # Thanksgiving


def at(day: dt.date, hh: int, mm: int = 0) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(hh, mm), tzinfo=ET)


def inside_session(when: dt.datetime) -> bool:
    sess = CALENDAR.session(when.date())
    return bool(sess and sess.open_t <= when.time() < sess.close_t)


# ------------------------------------------------------------------ when may a request end?

@pytest.mark.parametrize("day", [REGULAR, EARLY, HOLIDAY])
def test_snap_never_lands_inside_a_session(day):
    """The whole point of the function, checked minute by minute over a full day.

    IBKR truncates the session `endDateTime` lands in, so one end inside a session is one
    silently half-stored day - and the module's own store held sixteen of them."""
    for minute in range(24 * 60):
        now = at(day, minute // 60, minute % 60)
        assert not inside_session(idata.snap_after_close(now, now=now))


def test_legacy_snap_reproduces_the_defect():
    """The comparison flag must actually reproduce the bug, or D-4's control cell is a fiction."""
    midday = at(REGULAR, 12, 35)
    assert idata.snap_after_close(midday, now=midday, legacy=True) == midday
    assert inside_session(idata.snap_after_close(midday, now=midday, legacy=True))


def test_after_the_close_today_is_fetchable():
    """A post-close run must still reach today, or the store can never include the last session."""
    evening = at(REGULAR, 17, 0)
    end = idata.snap_after_close(evening, now=evening)
    assert end.date() == REGULAR and end.time() >= dt.time(16, 15)
    assert idata.last_closed_session(evening) == REGULAR


def test_during_the_session_the_boundary_steps_back_a_day():
    midday = at(REGULAR, 12, 35)
    end = idata.snap_after_close(midday, now=midday)
    assert end == at(REGULAR - dt.timedelta(days=1), 20, 0)
    assert idata.last_closed_session(midday) == dt.date(2026, 9, 10)


def test_last_closed_session_walks_back_over_a_weekend():
    """Saturday's "last closed session" is Friday, not Saturday - the calendar decides, not the
    clock. Run on the Saturday the D-4 repair was made."""
    assert idata.last_closed_session(at(dt.date(2026, 9, 12), 17, 39)) == REGULAR


def test_the_settle_margin_follows_the_early_close_not_the_clock():
    """AUD-07's rule applied to the fetcher: the margin is added to the CALENDAR's close, so an
    early close is fetchable from 13:15 and a hard-coded 16:15 would have lost three hours of
    the only window in which a half day can be stored complete."""
    assert not inside_session(idata.snap_after_close(at(EARLY, 13, 5), now=at(EARLY, 13, 5)))
    assert idata.last_closed_session(at(EARLY, 13, 5)) < EARLY        # 10 minutes early
    assert idata.last_closed_session(at(EARLY, 13, 20)) == EARLY      # settled
    assert idata.last_closed_session(at(REGULAR, 13, 20)) < REGULAR   # regular day: still open


# ------------------------------------------------------------------ which windows are needed?

def store(tmp_path, monkeypatch, symbol: str, days_and_bars: dict[dt.date, int | None]):
    """Write a synthetic store: `None` bars means the session is absent altogether."""
    idx = []
    for day, bars in days_and_bars.items():
        if bars is None:
            continue
        sess = CALENDAR.session(day)
        assert sess is not None, f"{day} is not a trading session - fix the fixture's dates"
        idx += list(pd.date_range(pd.Timestamp(f"{day} {sess.open_t}", tz=ET),
                                  periods=bars, freq="1min", tz=ET))
    path = tmp_path / f"{symbol}.parquet"
    df = pd.DataFrame({"o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0, "v": 100},
                      index=pd.DatetimeIndex(idx).tz_convert("UTC"))
    df.index.name = "date"
    df.to_parquet(path)
    monkeypatch.setattr(idata, "parquet_path", lambda s, _p=path: _p)
    return path


def week(end: dt.date, n: int) -> list[dt.date]:
    days, cur = [], end
    while len(days) < n:
        if CALENDAR.is_trading_day(cur):
            days.append(cur)
        cur -= dt.timedelta(days=1)
    return sorted(days)


def test_complete_store_needs_nothing(tmp_path, monkeypatch):
    """Identity, and the withdrawal condition of the whole patch: a fetcher that re-requests a
    complete store burns the pacing budget the repair needs."""
    days = week(REGULAR, 20)
    store(tmp_path, monkeypatch, "TEST", {d: CALENDAR.session_minutes(d) for d in days})
    now = at(dt.date(2026, 9, 12), 17, 0)
    assert idata.sessions_needed("TEST", days[0], REGULAR, now=now) == []
    assert idata.incomplete_sessions("TEST", now=now) == []


def test_truncated_last_session_is_needed(tmp_path, monkeypatch):
    """The defect exactly as it stood in the live store: 175 of 390 bars on the last day."""
    days = week(REGULAR, 20)
    bars = {d: CALENDAR.session_minutes(d) for d in days}
    bars[REGULAR] = 175
    store(tmp_path, monkeypatch, "TEST", bars)
    now = at(dt.date(2026, 9, 12), 17, 0)
    assert idata.sessions_needed("TEST", days[0], REGULAR, now=now) == [REGULAR]


def test_missing_session_is_needed_which_the_old_repair_could_not_see(tmp_path, monkeypatch):
    """`--repair` used to iterate the days ON DISK, so a day that was never fetched at all was
    invisible to it. A store cannot extend itself if absence is unrepresentable."""
    days = week(REGULAR, 20)
    bars = {d: CALENDAR.session_minutes(d) for d in days}
    bars[REGULAR] = None
    store(tmp_path, monkeypatch, "TEST", bars)
    now = at(dt.date(2026, 9, 12), 17, 0)
    assert idata.sessions_needed("TEST", days[0], REGULAR, now=now) == [REGULAR]
    assert idata.incomplete_sessions("TEST", now=now) == [REGULAR]


def test_a_complete_early_close_is_not_re_requested(tmp_path, monkeypatch):
    """210 bars is a whole session. The pre-D-4 rule got this right by hard-coding 210 and wrong
    for every other session length; the calendar gets it right for both."""
    days = week(EARLY, 5)
    store(tmp_path, monkeypatch, "TEST", {d: CALENDAR.session_minutes(d) for d in days})
    now = at(EARLY + dt.timedelta(days=3), 17, 0)
    assert idata.sessions_needed("TEST", days[0], EARLY, now=now) == []


def test_a_sparse_session_is_not_called_truncated(tmp_path, monkeypatch):
    """E-6's line, imported not redrawn: bars scattered but SPANNING the session are benign.
    The pre-D-4 bar-count rule (`n < 390 and n != 210`) refetched every one of them."""
    days = week(REGULAR, 5)
    full = pd.date_range(pd.Timestamp(f"{REGULAR} 09:30", tz=ET), periods=390, freq="1min", tz=ET)
    keep = sorted(set(range(390)) - set(range(100, 130)))   # a hole in the middle, both ends kept
    idx = list(full[keep])
    for d in days[:-1]:
        sess = CALENDAR.session(d)
        assert sess is not None, f"{d} is not a trading session - fix the fixture's dates"
        idx += list(pd.date_range(pd.Timestamp(f"{d} {sess.open_t}", tz=ET),
                                  periods=sess.minutes, freq="1min", tz=ET))
    path = tmp_path / "TEST.parquet"
    df = pd.DataFrame({"o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0, "v": 100},
                      index=pd.DatetimeIndex(sorted(idx)).tz_convert("UTC"))
    df.index.name = "date"
    df.to_parquet(path)
    monkeypatch.setattr(idata, "parquet_path", lambda s, _p=path: _p)
    now = at(dt.date(2026, 9, 12), 17, 0)
    assert idata.sessions_needed("TEST", days[0], REGULAR, now=now) == []


def test_a_session_that_has_not_closed_is_never_needed(tmp_path, monkeypatch):
    """An incomplete live session is not a defect, and requesting it is how one is created."""
    days = week(REGULAR, 20)
    bars = {d: CALENDAR.session_minutes(d) for d in days}
    bars[REGULAR] = 120
    store(tmp_path, monkeypatch, "TEST", bars)
    midday = at(REGULAR, 12, 35)
    assert idata.sessions_needed("TEST", days[0], REGULAR, now=midday) == []


def test_the_count_based_skip_is_blind_where_the_new_rule_is_not(tmp_path, monkeypatch):
    """AUD-16's core claim, as an assertion rather than a sentence: with 20 complete sessions on
    disk the OLD rule's "15 or more present" is satisfied whatever the state of the last day, so
    the window is skipped and the store can never advance past its own truncation."""
    days = week(REGULAR, 20)
    bars = {d: CALENDAR.session_minutes(d) for d in days}
    bars[REGULAR] = 175
    store(tmp_path, monkeypatch, "TEST", bars)
    now = at(dt.date(2026, 9, 12), 17, 0)
    shapes = idata.store_shapes("TEST")
    counted = sum(1 for d in shapes if days[0] <= d <= REGULAR)
    assert counted >= 15                                              # old rule: skip
    assert idata.sessions_needed("TEST", days[0], REGULAR, now=now)   # new rule: fetch


def test_fetcher_and_store_health_agree_on_every_session(tmp_path, monkeypatch):
    """Clause 4. Two modules that disagree about what "complete" means give an operator two
    answers and no way to choose, which is how the 2026-09-10 defect survived a `--repair`."""
    days = week(REGULAR, 20)
    bars = {d: CALENDAR.session_minutes(d) for d in days}
    bars[REGULAR] = 175
    bars[days[5]] = None
    path = store(tmp_path, monkeypatch, "TEST", bars)
    now = at(dt.date(2026, 9, 12), 17, 0)
    shapes = {s.day: s for s in sh.session_shapes(sh.rth_index(path), CALENDAR)}
    e6 = {d for d, s in shapes.items() if s.truncated} | {d for d in days if d not in shapes}
    assert set(idata.incomplete_sessions("TEST", now=now)) == e6


def test_month_ends_are_all_safe_boundaries():
    """Every window end a `--months N` run produces, not just the newest one."""
    midday = at(REGULAR, 11, 48)
    ends = idata.month_ends(12, now=midday)
    assert len(ends) == 12
    assert not any(inside_session(e) for e in ends)
    assert any(inside_session(e) for e in idata.month_ends(12, now=midday, legacy=True))
