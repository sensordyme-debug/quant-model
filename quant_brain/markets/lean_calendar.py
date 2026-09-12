"""A SessionCalendar backed by LEAN's own market-hours database.

WHY THIS REPLACES HAND-TYPED TABLES
------------------------------------
`markets/equity_us/calendar.py` carries 108 NYSE closures and 23 early closes that I typed by
hand. LEAN ships `Data/market-hours/market-hours-database.json` - 3.5 MB, 552 entries - and it
already contains all of it, deeper:

    Equity-usa-[*]     293 holidays, 65 early closes
    hand-typed table   108 holidays, 23 early closes   (2016-2027 only)

Cross-checked before trusting it. LEAN independently agrees on every date the hand-typed table
asserts, including the two that are not rule-derivable and the one the whole AUD-07 fix turns
on:

    2018-12-05  day of mourning, G.H.W. Bush   holiday in both
    2025-01-09  day of mourning, Carter        holiday in both
    2026-07-03  observed July 4                holiday in both
    2026-11-27  the next early close           13:00 in both

Two independently-built tables agreeing on every probe is worth more than either alone, so the
hand-typed one is kept as a cross-check (see `tests/test_qb_lean_calendar.py`) rather than
deleted.

AND IT GIVES FUTURES ITS CALENDAR FOR FREE
-------------------------------------------
The CME calendar was the futures branch's single blocking gap. LEAN has it:

    Future-cme-ES      Sunday 18:00 open, Mon-Fri 00:00-09:30 pre / 09:30-17:00 market /
                       18:00-24:00 post, 169 early closes, 119 late opens
    Future-cbot-YM, Future-comex-GC, Future-nymex-CL   all present

The 17:00-18:00 daily maintenance break is encoded as the GAP between the market and
postmarket segments, which is why segments are read rather than just an open and a close.

`rth=True` gives the regular session (what an equity strategy means by "the session");
`rth=False` gives the full Globex span a futures strategy trades. That distinction is the
reason this class exists rather than a dict of open/close times.
"""
from __future__ import annotations

import datetime as dt
import json
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from quant_brain.core.calendar import Session, SessionCalendar

#: LEAN lives beside this repository, per AGENTS.md ("LEAN engine source and build: ..\\Lean").
DEFAULT_DB = (Path(__file__).resolve().parents[3] / "Lean" / "Data"
              / "market-hours" / "market-hours-database.json")

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def _parse_lean_date(s: str) -> dt.date | None:
    """LEAN writes dates as M/D/YYYY. Returns None on anything unexpected."""
    try:
        m, d, y = s.split("/")
        return dt.date(int(y[:4]), int(m), int(d))
    except (ValueError, AttributeError):
        return None


def _parse_lean_time(s: str) -> tuple[dt.time, bool]:
    """LEAN writes 'HH:MM:SS', and '1.00:00:00' for midnight at the end of the day.

    Returns (time, rolls_past_midnight). The `1.` prefix is a .NET TimeSpan with a day
    component; treating it as 24:00 rather than 00:00 is what keeps a Globex session from
    measuring as zero minutes long.
    """
    rolls = False
    if "." in s and s.count(":") == 2 and s.split(".")[0].isdigit():
        days, s = s.split(".", 1)
        rolls = int(days) >= 1
    h, m, sec = (int(x) for x in s.split(":"))
    if h >= 24:
        h, rolls = h - 24, True
    return dt.time(h, m, sec), rolls


@lru_cache(maxsize=4)
def _load(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"LEAN market-hours database not found at {p}. It ships with the engine at "
            f"Data/market-hours/market-hours-database.json.")
    return json.loads(p.read_text(encoding="utf-8"))


class LeanMarketHoursCalendar(SessionCalendar):
    """Any market LEAN knows about, addressed by its database key.

    Keys look like `Equity-usa-[*]`, `Future-cme-ES`, `Future-nymex-CL`. `available()` lists
    them rather than making a caller guess.
    """

    def __init__(self, key: str, *, db_path: str | Path | None = None, rth: bool = True):
        self.key = key
        self._db_path = str(db_path or DEFAULT_DB)
        self.rth = rth
        db = _load(self._db_path)
        try:
            self._e = db["entries"][key]
        except KeyError:
            raise KeyError(
                f"{key!r} is not in LEAN's market-hours database. "
                f"Try one of: "
                f"{', '.join(sorted(k for k in db['entries'] if key.split('-')[0] in k)[:8])}"
            ) from None
        self.name = key
        self.tz = ZoneInfo(self._e.get("exchangeTimeZone", "America/New_York"))
        self._holidays = {d for d in (_parse_lean_date(x)
                                      for x in self._e.get("holidays", [])) if d}
        self._early = {}
        for k, v in (self._e.get("earlyCloses") or {}).items():
            d = _parse_lean_date(k)
            if d:
                self._early[d] = _parse_lean_time(v)[0]
        self._late = {}
        for k, v in (self._e.get("lateOpens") or {}).items():
            d = _parse_lean_date(k)
            if d:
                self._late[d] = _parse_lean_time(v)[0]
        # LEAN's tables are maintained forward; coverage is whatever the file states plus the
        # rule-based weekday segments, which have no end. Take the furthest special date as
        # the honest limit rather than claiming the calendar is good forever.
        specials = self._holidays | set(self._early) | set(self._late)
        self.coverage_end = max(specials) if specials else dt.date(1970, 1, 1)

    # -- SessionCalendar ---------------------------------------------------------------

    def is_trading_day(self, day: dt.date) -> bool:
        if day in self._holidays:
            return False
        return bool(self._segments(day))

    def session(self, day: dt.date) -> Session | None:
        self.check_covered(day)
        if not self.is_trading_day(day):
            return None
        segs = self._segments(day)
        if not segs:
            return None
        open_t = self._late.get(day) or segs[0][0]
        close_t = segs[-1][1]
        early = self._early.get(day)
        if early is not None:
            close_t = early
        spans = segs[-1][2] and early is None
        return Session(day=day, open_t=open_t, close_t=close_t,
                       is_early_close=early is not None, spans_midnight=spans)

    # -- extras a futures branch needs --------------------------------------------------

    def segments(self, day: dt.date) -> list[tuple[dt.time, dt.time, str]]:
        """Every tradable block on `day`, as (start, end, state).

        The daily maintenance break is the gap BETWEEN blocks, so a caller that needs to know
        whether an instant is tradable must look at segments rather than at open/close.
        """
        if not self.is_trading_day(day):
            return []
        return [(a, b, st) for a, b, _r, st in self._raw_segments(day)]

    def is_open_at(self, when: dt.datetime) -> bool:
        """True if `when` (exchange-local) falls inside a tradable block."""
        t = when.time()
        return any(a <= t < b or (b <= a and (t >= a or t < b))
                   for a, b, _st in self.segments(when.date()))

    @staticmethod
    def available(db_path: str | Path | None = None, prefix: str = "") -> list[str]:
        db = _load(str(db_path or DEFAULT_DB))
        return sorted(k for k in db["entries"] if k.startswith(prefix))

    # -- internals ---------------------------------------------------------------------

    def _raw_segments(self, day: dt.date) -> list[tuple[dt.time, dt.time, bool, str]]:
        out = []
        for seg in self._e.get(_WEEKDAYS[day.weekday()], []):
            start, _ = _parse_lean_time(seg["start"])
            end, rolls = _parse_lean_time(seg["end"])
            out.append((start, end, rolls, seg.get("state", "market")))
        return out

    def _segments(self, day: dt.date):
        segs = self._raw_segments(day)
        if self.rth:
            segs = [s for s in segs if s[3] == "market"]
        return segs


def equity_usa(**kw) -> LeanMarketHoursCalendar:
    """US equities, regular hours. LEAN's own table, 293 holidays and 65 early closes."""
    return LeanMarketHoursCalendar("Equity-usa-[*]", rth=True, **kw)


def cme_future(root: str, *, rth: bool = False, **kw) -> LeanMarketHoursCalendar:
    """A CME-complex future by root symbol, resolving the exchange automatically.

    `rth=False` by default: a futures strategy trades the Globex span, and defaulting to the
    09:30-17:00 window would silently discard most of the session.
    """
    exchanges = ("cme", "cbot", "comex", "nymex", "cfe")
    for exch in exchanges:
        key = f"Future-{exch}-{root.upper()}"
        try:
            return LeanMarketHoursCalendar(key, rth=rth, **kw)
        except KeyError:
            continue
    raise KeyError(f"no LEAN market-hours entry for future {root!r} on any of {exchanges}")
