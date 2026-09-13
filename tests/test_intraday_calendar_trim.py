"""AUD-07 / D-6: the bar loader trims each session at its own calendar close.

`scripts/alpaca_data.py` filtered incoming bars on a literal 09:30-16:00 window, so all 21 early
closes 2016-2025 in `data/minute_alpaca` were stored with their 13:00-15:59 POST-MARKET prints
wearing an RTH timestamp - 22,081 rows over the sleeve universe, of which only ~31% of the
possible minutes print at all and which carry a median 14.3% of the volume the same clock window
carries on the five regular sessions before them.

Two halves are pinned here. `calendar_trim` must remove exactly those rows and nothing else (a
trim that eats a real RTH bar is worse than a store with extra ones), and the harness must COUNT
the forced end-of-day fill - the one fill in a session that is not worked, and therefore the one
that would land in that post-market tape if a flatten ever failed. It was reported only when
A-11's participation cap was on, so the harness could close a book against a post-market print and
say nothing.
"""
from __future__ import annotations

import datetime as dt

import intraday_common as ic
import pandas as pd
import pytest

ET = ic.ET

REGULAR = dt.date(2025, 11, 26)      # Wednesday before Thanksgiving, a full session
HOLIDAY = dt.date(2025, 11, 27)      # Thanksgiving
EARLY = dt.date(2025, 11, 28)        # 13:00 close
EARLY_2 = dt.date(2024, 7, 3)        # July 3, a different early-close family


def _session(day: dt.date, first=dt.time(9, 30), last=dt.time(15, 59)) -> pd.DatetimeIndex:
    a = first.hour * 60 + first.minute
    b = last.hour * 60 + last.minute
    return pd.DatetimeIndex([pd.Timestamp(dt.datetime.combine(day, dt.time(m // 60, m % 60)), tz=ET)
                             for m in range(a, b + 1)])


def _frame(days) -> pd.DataFrame:
    idx = pd.DatetimeIndex([]).tz_localize(ET)
    for d in days:
        idx = idx.append(_session(d))
    return pd.DataFrame({"o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5,
                         "v": range(len(idx))}, index=idx)


# ------------------------------------------------------------------------ what the trim removes

def test_an_early_close_loses_everything_from_1300_and_keeps_210_bars():
    out = ic.calendar_trim(_frame([EARLY]))
    assert len(out) == 210
    assert max(t.time() for t in out.index) == dt.time(12, 59)


def test_a_regular_session_is_untouched():
    f = _frame([REGULAR])
    out = ic.calendar_trim(f)
    assert len(out) == 390
    assert out.equals(f)


def test_a_full_day_closure_leaves_no_rows_at_all():
    """A holiday with bars is not a data gap to be tolerated: it is a row that cannot exist."""
    assert ic.calendar_trim(_frame([HOLIDAY])).empty


def test_a_mixed_frame_keeps_the_regular_day_whole_and_cuts_only_the_early_one():
    out = ic.calendar_trim(_frame([REGULAR, HOLIDAY, EARLY]))
    by_day = out.groupby(pd.Index(out.index.date)).size().to_dict()
    assert by_day == {REGULAR: 390, EARLY: 210}


def test_july_3_is_trimmed_the_same_way_as_the_thanksgiving_family():
    out = ic.calendar_trim(_frame([EARLY_2]))
    assert len(out) == 210


# --------------------------------------------------------------------- what the trim must never do

def test_the_trim_is_a_pure_subset_values_and_all():
    f = _frame([REGULAR, EARLY])
    out = ic.calendar_trim(f)
    assert out.index.isin(f.index).all()
    assert out.equals(f.loc[out.index])          # nothing filled, shifted or re-typed


def test_a_frame_with_no_affected_day_is_returned_unchanged_and_cheaply():
    f = _frame([REGULAR])
    assert ic.calendar_trim(f) is f              # the fast path, so load_bars pays nothing


def test_the_trim_is_idempotent():
    once = ic.calendar_trim(_frame([REGULAR, HOLIDAY, EARLY]))
    assert ic.calendar_trim(once).equals(once)


def test_an_empty_frame_survives():
    f = _frame([]).astype({"v": float})
    assert ic.calendar_trim(f).empty


def test_a_calendar_that_cannot_be_imported_degrades_to_the_old_behaviour(monkeypatch):
    """A loader sits on the live path. A broken calendar import must not stop the sleeve."""
    import builtins
    real = builtins.__import__

    def boom(name, *a, **k):
        if name.startswith("quant_brain.markets.equity_us"):
            raise ImportError("no calendar")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", boom)
    f = _frame([EARLY])
    assert len(ic.calendar_trim(f)) == 390


# ------------------------------------------------------------------------------ the loader switch

def test_load_bars_honours_the_switch(tmp_path, monkeypatch):
    f = _frame([REGULAR, EARLY])
    monkeypatch.setattr(ic, "DATA_DIR", tmp_path)
    f.tz_convert("UTC").to_parquet(tmp_path / "ZZZ.parquet")

    monkeypatch.setattr(ic, "CALENDAR_TRIM", True)
    assert len(ic.load_bars("ZZZ")) == 600
    monkeypatch.setattr(ic, "CALENDAR_TRIM", False)
    assert len(ic.load_bars("ZZZ")) == 780       # the pre-2026-09-13 store view, for reproduction


# ---------------------------------------------------------- the harness counts the unworked fill

def _bars_one_day(day: dt.date, n: int = 60) -> pd.DataFrame:
    last = 9 * 60 + 30 + n - 1
    idx = _session(day, dt.time(9, 30), dt.time(last // 60, last % 60))
    return pd.DataFrame({"o": 100.0, "h": 100.0, "l": 100.0, "c": 100.0, "v": 1000},
                        index=idx)


class _AlwaysLong:
    """Holds one name for the whole session, so the framework flatten never gets a chance."""

    PARAMS: dict = {}

    @staticmethod
    def decide(now, feats, book, equity, state, params):
        return {"ZZZ": 0.10}


def test_a_position_dumped_into_the_last_bar_is_reported_without_the_participation_cap():
    """Before AUD-07 these two keys existed only when RISK['part_cap'] was non-zero."""
    import intraday_backtest as ib

    day = dt.date(2026, 3, 10)
    bars = {"ZZZ": _bars_one_day(day)}
    s = ib.run(_AlwaysLong, bars, 1_000_000.0, {}, day, day, False)
    assert s["forced_eod_orders"] == 1
    assert s["forced_eod_notional"] == pytest.approx(1000 * 100.0)
    assert s["forced_eod_days"] == [str(day)]


def test_a_book_that_flattens_itself_reports_zero():
    import intraday_backtest as ib

    day = dt.date(2026, 3, 10)
    bars = {"ZZZ": _bars_one_day(day)}

    class _Flat:
        PARAMS: dict = {}

        @staticmethod
        def decide(now, feats, book, equity, state, params):
            return {}

    s = ib.run(_Flat, bars, 1_000_000.0, {}, day, day, False)
    assert s["forced_eod_orders"] == 0
    assert s["forced_eod_days"] == []
