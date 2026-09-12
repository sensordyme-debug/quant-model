"""The US cash equity trading calendar (NYSE/Nasdaq), 2016-2027.

This is the concrete fix for AUD-07. Every date below is a full-day closure or a 13:00 ET
early close published by NYSE. The range starts at 2016 because that is where the Alpaca SIP
minute store starts (`AGENTS.md` / Data), and runs to 2027 so the table does not expire
mid-research.

Two closures in the table are not rule-derivable and are easy to mistake for errors, so they
are called out here:

  * **2018-12-05** - National Day of Mourning, George H. W. Bush. Markets closed.
  * **2025-01-09** - National Day of Mourning, Jimmy Carter. Markets closed.

Both appear as ordinary missing sessions in any bar store, which is exactly the failure mode
AUD-24 ("store hygiene") warns about: a missing day that looks like a data gap but is not.

The early-close list is the one AUD-07 says the code has never had. All 21 of the
2016-2025 entries the audit counted in the Alpaca store are here, plus the forward dates.
`2026-11-27` is the next one, as the audit states.
"""
from __future__ import annotations

import datetime as dt

from quant_brain.core.calendar import ET, Session, SessionCalendar, good_friday

D = dt.date

#: Full-day closures. Grouped by year so a reviewer can check one year against the NYSE
#: published schedule without reading the whole table.
_HOLIDAYS: frozenset[dt.date] = frozenset([
    # 2016
    D(2016, 1, 1), D(2016, 1, 18), D(2016, 2, 15), D(2016, 3, 25), D(2016, 5, 30),
    D(2016, 7, 4), D(2016, 9, 5), D(2016, 11, 24), D(2016, 12, 26),
    # 2017
    D(2017, 1, 2), D(2017, 1, 16), D(2017, 2, 20), D(2017, 4, 14), D(2017, 5, 29),
    D(2017, 7, 4), D(2017, 9, 4), D(2017, 11, 23), D(2017, 12, 25),
    # 2018  (12-05 = day of mourning, G.H.W. Bush)
    D(2018, 1, 1), D(2018, 1, 15), D(2018, 2, 19), D(2018, 3, 30), D(2018, 5, 28),
    D(2018, 7, 4), D(2018, 9, 3), D(2018, 11, 22), D(2018, 12, 5), D(2018, 12, 25),
    # 2019
    D(2019, 1, 1), D(2019, 1, 21), D(2019, 2, 18), D(2019, 4, 19), D(2019, 5, 27),
    D(2019, 7, 4), D(2019, 9, 2), D(2019, 11, 28), D(2019, 12, 25),
    # 2020  (07-03 observed for Jul 4 Saturday)
    D(2020, 1, 1), D(2020, 1, 20), D(2020, 2, 17), D(2020, 4, 10), D(2020, 5, 25),
    D(2020, 7, 3), D(2020, 9, 7), D(2020, 11, 26), D(2020, 12, 25),
    # 2021  (07-05 observed for Jul 4 Sunday; 12-24 observed for Christmas Saturday)
    D(2021, 1, 1), D(2021, 1, 18), D(2021, 2, 15), D(2021, 4, 2), D(2021, 5, 31),
    D(2021, 7, 5), D(2021, 9, 6), D(2021, 11, 25), D(2021, 12, 24),
    # 2022  (Juneteenth observed 06-20; 12-26 observed for Christmas Sunday)
    D(2022, 1, 17), D(2022, 2, 21), D(2022, 4, 15), D(2022, 5, 30), D(2022, 6, 20),
    D(2022, 7, 4), D(2022, 9, 5), D(2022, 11, 24), D(2022, 12, 26),
    # 2023
    D(2023, 1, 2), D(2023, 1, 16), D(2023, 2, 20), D(2023, 4, 7), D(2023, 5, 29),
    D(2023, 6, 19), D(2023, 7, 4), D(2023, 9, 4), D(2023, 11, 23), D(2023, 12, 25),
    # 2024
    D(2024, 1, 1), D(2024, 1, 15), D(2024, 2, 19), D(2024, 3, 29), D(2024, 5, 27),
    D(2024, 6, 19), D(2024, 7, 4), D(2024, 9, 2), D(2024, 11, 28), D(2024, 12, 25),
    # 2025  (01-09 = day of mourning, Carter)
    D(2025, 1, 1), D(2025, 1, 9), D(2025, 1, 20), D(2025, 2, 17), D(2025, 4, 18),
    D(2025, 5, 26), D(2025, 6, 19), D(2025, 7, 4), D(2025, 9, 1), D(2025, 11, 27),
    D(2025, 12, 25),
    # 2026  (07-03 observed for Jul 4 Saturday)
    D(2026, 1, 1), D(2026, 1, 19), D(2026, 2, 16), D(2026, 4, 3), D(2026, 5, 25),
    D(2026, 6, 19), D(2026, 7, 3), D(2026, 9, 7), D(2026, 11, 26), D(2026, 12, 25),
    # 2027  (06-18 observed for Juneteenth Saturday; 07-05 for Jul 4 Sunday;
    #        12-24 observed for Christmas Saturday)
    D(2027, 1, 1), D(2027, 1, 18), D(2027, 2, 15), D(2027, 3, 26), D(2027, 5, 31),
    D(2027, 6, 18), D(2027, 7, 5), D(2027, 9, 6), D(2027, 11, 25), D(2027, 12, 24),
])

#: 13:00 ET closes. Day after Thanksgiving every year; July 3 when July 4 falls Tue-Fri and
#: July 3 is itself a session; Christmas Eve when it is a weekday session.
_EARLY_CLOSES: frozenset[dt.date] = frozenset([
    D(2016, 11, 25),
    D(2017, 7, 3), D(2017, 11, 24),
    D(2018, 7, 3), D(2018, 11, 23), D(2018, 12, 24),
    D(2019, 7, 3), D(2019, 11, 29), D(2019, 12, 24),
    D(2020, 11, 27), D(2020, 12, 24),
    D(2021, 11, 26),
    D(2022, 11, 25),
    D(2023, 7, 3), D(2023, 11, 24),
    D(2024, 7, 3), D(2024, 11, 29), D(2024, 12, 24),
    D(2025, 7, 3), D(2025, 11, 28), D(2025, 12, 24),
    D(2026, 11, 27), D(2026, 12, 24),
    D(2027, 11, 26),
])

REGULAR_OPEN = dt.time(9, 30)
REGULAR_CLOSE = dt.time(16, 0)
EARLY_CLOSE = dt.time(13, 0)


class USEquityCalendar(SessionCalendar):
    """NYSE/Nasdaq regular trading hours.

    Covers only RTH. The Alpaca store's after-hours bars (13:00-15:59 on early closes) are a
    separate problem AUD-07 also raises; `session_minutes` here is what a loader should trim
    to, and `tests/test_qb_calendar.py` pins the 210-minute early-close length that the trim
    depends on.
    """

    name = "us_equity"
    tz = ET
    coverage_end = D(2027, 12, 31)

    def is_trading_day(self, day: dt.date) -> bool:
        if day.weekday() >= 5:          # Saturday, Sunday
            return False
        return day not in _HOLIDAYS

    def session(self, day: dt.date) -> Session | None:
        self.check_covered(day)
        if not self.is_trading_day(day):
            return None
        early = day in _EARLY_CLOSES
        return Session(
            day=day,
            open_t=REGULAR_OPEN,
            close_t=EARLY_CLOSE if early else REGULAR_CLOSE,
            is_early_close=early,
        )

    # -- consistency checks the table must satisfy, exercised by the test suite -------------

    @staticmethod
    def holidays() -> frozenset[dt.date]:
        return _HOLIDAYS

    @staticmethod
    def early_closes() -> frozenset[dt.date]:
        return _EARLY_CLOSES

    @staticmethod
    def expected_good_fridays(first: int = 2016, last: int = 2027) -> set[dt.date]:
        """Good Fridays the table must contain, derived independently of the table.

        A table checked only against itself proves nothing. This lets the suite verify one
        whole holiday family against an algorithm rather than against a copy of the same
        hand-typed list.
        """
        return {good_friday(y) for y in range(first, last + 1)}


#: Module-level singleton. Stateless and frozen, so one instance is correct and it keeps
#: callers from paying construction cost inside a per-bar loop.
CALENDAR = USEquityCalendar()
