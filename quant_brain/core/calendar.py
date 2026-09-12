"""When a market is open, and what "the close" means on any given day.

WHY THIS EXISTS
---------------
`research/audit_2026-09-12.md` AUD-07: "No exchange calendar anywhere". The consequences it
documents are all live, not hypothetical:

  * `intraday_common.FLATTEN_MINUTE = 368` is the 368th minute after 09:30, i.e. 15:38. On a
    13:00 early close there is no 368th bar - the RTH feed stops at 210. `step()` returns on
    `t <= last_t`, no flatten is ever sent, and the position is carried into the 15:45 daily
    rebalance as a "foreign" holding.
  * The research harness silently closes at the 12:59 price with zero latency, so the
    backtest disagrees with the live path on exactly the days the live path breaks.
  * All 21 early closes 2016-2025 in the Alpaca store carry 13:00-15:59 after-hours bars, so
    `late_momo` opens into the post-market tape and the flatten fills against it.
  * On a holiday both scheduled tasks fire and the daily runner queues MKT orders on a stale
    signal.

The next early close is **2026-11-27**. This module is the fix, and it is deliberately the
same piece of work as the multi-market seam: `SessionCalendar` is the abstraction a futures
branch needs anyway (CME trades a 23-hour session, not 09:30-16:00), so fixing the equity
defect behind an ABC gets the futures calendar for free instead of hard-coding a holiday
list that would have to be rewritten.

WHY A HARD-CODED TABLE RATHER THAN `pandas_market_calendars`
------------------------------------------------------------
AUD-07 offered both. A table wins here for three reasons: it adds no dependency to an
environment that already has two Pythons with different pandas majors (F-01); it is
auditable by eye against the NYSE published schedule; and it is importable by the LEAN-side
Python 3.11, which has no pandas_market_calendars and cannot get one without touching the
environment the live tasks run in. The cost is that it must be extended - `coverage_end`
exists so that expiry is an exception rather than a silent wrong answer.
"""
from __future__ import annotations

import abc
import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class Session:
    """One trading session, in exchange-local wall clock.

    `open_t`/`close_t` are `datetime.time` in the calendar's own timezone. A session that
    spans midnight (CME's Sunday 18:00 open) sets `spans_midnight`, so a caller comparing
    times knows not to treat `open_t > close_t` as a bug.
    """

    day: dt.date
    open_t: dt.time
    close_t: dt.time
    is_early_close: bool = False
    spans_midnight: bool = False

    @property
    def minutes(self) -> int:
        """Length of the session in minutes.

        This is the number the intraday framework's bar offsets are relative to. A regular
        US equity session is 390; a 13:00 early close is 210. Any constant that assumes 390
        is a bug on 21 days of the last decade.
        """
        o = self.open_t.hour * 60 + self.open_t.minute
        c = self.close_t.hour * 60 + self.close_t.minute
        if self.spans_midnight or c <= o:
            c += 24 * 60
        return c - o


class SessionCalendar(abc.ABC):
    """What a market branch must be able to answer about the clock.

    Deliberately small. Everything the runners and the harness actually need is here, and
    nothing else - a calendar that also knew about settlement or expiry would be a futures
    calendar wearing a core interface.
    """

    name: str = "abstract"
    tz: ZoneInfo = ET
    #: Last date the underlying table is known-good. Past this the calendar refuses rather
    #: than guessing, because a guessed holiday is indistinguishable from a real one until
    #: money is on the line. See `check_covered`.
    coverage_end: dt.date = dt.date(1970, 1, 1)

    @abc.abstractmethod
    def is_trading_day(self, day: dt.date) -> bool:
        """True if the market trades at all on `day`."""

    @abc.abstractmethod
    def session(self, day: dt.date) -> Session | None:
        """The session for `day`, or None if the market is closed."""

    def check_covered(self, day: dt.date) -> None:
        """Raise if `day` is past the table's verified range.

        Part 18's operating principle: UNKNOWN STATE = DO NOT TRADE. A calendar asked about
        a date it has no data for must not answer "regular session" - that is precisely how
        a runner ends up trading a holiday. The launcher catches this and refuses to start,
        which is a loud, fixable failure instead of a silent wrong one.
        """
        if day > self.coverage_end:
            raise CalendarCoverageError(
                f"{self.name} calendar is verified only through {self.coverage_end}; "
                f"asked about {day}. Extend the table in "
                f"quant_brain/markets/<branch>/calendar.py before trading this date."
            )

    def is_early_close(self, day: dt.date) -> bool:
        s = self.session(day)
        return bool(s and s.is_early_close)

    def session_minutes(self, day: dt.date) -> int | None:
        """Length of `day`'s session in minutes, or None when closed.

        The replacement for every hard-coded 390. A framework constant expressed as
        "close minus 22 minutes" is correct on both a regular day and an early close;
        the literal 368 is correct only on one of them.
        """
        s = self.session(day)
        return s.minutes if s else None

    def minutes_before_close(self, day: dt.date, minutes: int) -> int | None:
        """Bar offset from the open that sits `minutes` before the close.

        This is the shape AUD-07 asks for: the flatten is defined relative to the close, so
        it lands at 15:38 on a regular day and 12:38 on a 13:00 close, with no branch in the
        caller. Returns None when the market is shut, and clamps at 0 rather than returning
        a negative offset on a session shorter than `minutes`.
        """
        total = self.session_minutes(day)
        if total is None:
            return None
        return max(0, total - minutes)

    def next_trading_day(self, day: dt.date, *, skip: int = 1) -> dt.date:
        """The `skip`-th trading day strictly after `day`."""
        cur, left = day, skip
        # 40 calendar days is comfortably past the longest closed run any of these markets
        # has (a 3-day weekend plus a holiday). Bounded so a bad table cannot spin forever.
        for _ in range(40 * max(1, skip)):
            cur += dt.timedelta(days=1)
            if self.is_trading_day(cur):
                left -= 1
                if left == 0:
                    return cur
        raise CalendarCoverageError(f"{self.name}: no trading day found within 40 days of {day}")

    def trading_days(self, start: dt.date, end: dt.date) -> list[dt.date]:
        """Every trading day in [start, end], inclusive."""
        out, cur = [], start
        while cur <= end:
            if self.is_trading_day(cur):
                out.append(cur)
            cur += dt.timedelta(days=1)
        return out


class CalendarCoverageError(RuntimeError):
    """Asked about a date the calendar cannot vouch for. Never trade through this."""


def easter(year: int) -> dt.date:
    """Western Easter Sunday, by the anonymous Gregorian algorithm.

    Present only because Good Friday is a US market holiday and is the one closure that
    cannot be written as an nth-weekday rule. Verified against the known Good Fridays in the
    equity table (2016-03-25 ... 2027-03-26) by `tests/test_qb_calendar.py`.
    """
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ll = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ll) // 451
    month, day = divmod(h + ll - 7 * m + 114, 31)
    return dt.date(year, month, day + 1)


def good_friday(year: int) -> dt.date:
    return easter(year) - dt.timedelta(days=2)
