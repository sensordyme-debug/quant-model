"""Store validation before research or trading consumes the bars.

Part 17's rule is the one under test: "NEVER interpret missing market data as a legitimate
zero price. Missing data must have an explicit state." That is not abstract here - AUD-05 was
this exact confusion in the live runner, where `prices.get(s, 0.0)` marked a $30k position at
zero on one dropped bar and flattened the book.

Two of these run against the real stores, because a validator that has only ever seen
synthetic frames proves nothing about the data the system actually trades.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from quant_brain.core.dataquality import (
    DataQualityError,
    Severity,
    check_frame,
    gaps,
    require_usable,
    validate_store,
)
from quant_brain.markets.equity_us import CALENDAR

ET = "America/New_York"


def frame(day="2026-09-11", n=390, start="09:30", **over):
    idx = pd.date_range(f"{day} {start}", periods=n, freq="1min", tz=ET)
    df = pd.DataFrame({"o": 100.0, "h": 100.5, "l": 99.5, "c": 100.0, "v": 1000.0}, index=idx)
    for k, v in over.items():
        df[k] = v
    return df


def codes(rep, severity=None):
    return {f.check for f in rep.findings if severity is None or f.severity is severity}


# --------------------------------------------------------------- a zero is absent, not cheap

def test_a_zero_price_is_a_failure_not_a_cheap_bar():
    df = frame()
    df.iloc[5, df.columns.get_loc("c")] = 0.0
    rep = check_frame("NVDA", df)
    assert rep.failed
    assert "zero_price" in codes(rep, Severity.FAIL)


def test_a_nan_price_is_a_failure():
    df = frame()
    df.iloc[7, df.columns.get_loc("c")] = float("nan")
    assert "nan_price" in codes(check_frame("NVDA", df), Severity.FAIL)


def test_a_negative_price_is_a_failure():
    df = frame()
    df.iloc[3, df.columns.get_loc("o")] = -1.0
    assert "negative_price" in codes(check_frame("NVDA", df), Severity.FAIL)


# --------------------------------------------------------------- structural impossibilities

def test_high_below_low_is_a_failure():
    df = frame()
    df.iloc[2, df.columns.get_loc("h")] = 98.0
    assert "impossible_bar" in codes(check_frame("NVDA", df), Severity.FAIL)


def test_a_close_outside_the_bar_range_is_a_failure():
    df = frame()
    df.iloc[4, df.columns.get_loc("c")] = 200.0
    assert "impossible_bar" in codes(check_frame("NVDA", df), Severity.FAIL)


def test_duplicate_timestamps_are_a_failure():
    df = frame(n=10)
    df = pd.concat([df, df.iloc[[3]]]).sort_index()
    assert "duplicates" in codes(check_frame("NVDA", df), Severity.FAIL)


def test_an_unsorted_index_is_a_failure():
    df = frame(n=10).iloc[::-1]
    assert "ordering" in codes(check_frame("NVDA", df), Severity.FAIL)


def test_a_tz_naive_index_is_a_failure():
    """DST is undefined on a naive index, and this system's whole clock rests on ET."""
    df = frame(n=10)
    df.index = pd.DatetimeIndex(df.index).tz_localize(None)
    assert "timezone" in codes(check_frame("NVDA", df), Severity.FAIL)


def test_an_empty_frame_is_a_failure_not_an_empty_pass():
    assert check_frame("NVDA", pd.DataFrame()).failed


def test_a_negative_volume_is_a_failure():
    df = frame(n=10)
    df.iloc[1, df.columns.get_loc("v")] = -5.0
    assert "negative_volume" in codes(check_frame("NVDA", df), Severity.FAIL)


# --------------------------------------------------------------- warnings, not failures

def test_zero_volume_warns_rather_than_fails():
    """Legitimate in a thin minute, suspicious in bulk - the caller decides."""
    df = frame(n=10)
    df.iloc[1, df.columns.get_loc("v")] = 0.0
    rep = check_frame("NVDA", df)
    assert not rep.failed and "zero_volume" in codes(rep, Severity.WARN)


def test_a_huge_one_bar_move_warns_as_a_possible_unadjusted_split():
    df = frame(n=10)
    df.iloc[5, df.columns.get_loc("c")] = 300.0
    df.iloc[5, df.columns.get_loc("h")] = 300.0
    rep = check_frame("NVDA", df)
    assert "price_jump" in codes(rep, Severity.WARN)


def test_a_clean_frame_produces_no_findings_at_all():
    rep = check_frame("NVDA", frame())
    assert not rep.failed
    assert not codes(rep, Severity.WARN)


# --------------------------------------------------------------- gaps have an explicit state

def test_a_gap_is_reported_and_never_filled():
    df = frame(n=60)
    df = pd.concat([df.iloc[:20], df.iloc[40:]])       # 20 minutes missing
    rep = gaps(df, symbol="NVDA")
    assert "intraday_gap" in codes(rep, Severity.WARN)
    assert len(df) == 40, "the validator must not add rows"


def test_the_overnight_boundary_is_not_reported_as_a_gap():
    a = frame(day="2026-09-10", n=30)
    b = frame(day="2026-09-11", n=30)
    rep = gaps(pd.concat([a, b]), symbol="NVDA")
    assert "intraday_gap" not in codes(rep)


# --------------------------------------------------------------- calendar coverage

def test_bars_on_a_market_holiday_are_a_failure():
    df = frame(day="2026-11-26", n=30)                  # Thanksgiving
    rep = check_frame("NVDA", df, CALENDAR)
    assert "non_trading_day" in codes(rep, Severity.FAIL)


def test_after_hours_rows_on_an_early_close_are_flagged():
    """AUD-07: the Alpaca store carries 13:00-15:59 rows on every early close."""
    df = frame(day="2026-11-27", n=390)                 # 210-minute session
    rep = check_frame("NVDA", df, CALENDAR)
    assert "after_hours" in codes(rep, Severity.WARN)


def test_a_correctly_trimmed_early_close_is_not_flagged():
    df = frame(day="2026-11-27", n=210)
    rep = check_frame("NVDA", df, CALENDAR)
    assert "after_hours" not in codes(rep)
    assert "early_close" in codes(rep, Severity.INFO)


# --------------------------------------------------------------- the gate

def test_require_usable_raises_on_a_failure():
    df = frame(n=10)
    df.iloc[1, df.columns.get_loc("c")] = 0.0
    with pytest.raises(DataQualityError, match="not usable"):
        require_usable({"NVDA": df})


def test_require_usable_returns_the_report_when_only_warnings_are_present():
    df = frame(n=10)
    df.iloc[1, df.columns.get_loc("v")] = 0.0
    rep = require_usable({"NVDA": df})
    assert not rep.failed and rep.of(Severity.WARN)


def test_validate_store_aggregates_across_symbols():
    bad = frame(n=10)
    bad.iloc[1, bad.columns.get_loc("c")] = 0.0
    rep = validate_store({"NVDA": frame(n=10), "TSLA": bad})
    assert rep.symbols == 2 and rep.failed
    assert {f.symbol for f in rep.of(Severity.FAIL)} == {"TSLA"}


def test_the_report_never_rewrites_the_frame():
    """No repair, ever: a validator that fixes data destroys the evidence upstream is broken."""
    df = frame(n=10)
    before = df.copy()
    validate_store({"NVDA": df}, CALENDAR)
    pd.testing.assert_frame_equal(df, before)


# --------------------------------------------------------------- against the real store

@pytest.mark.parametrize("symbol", ["NVDA"])
def test_the_deployed_ibkr_minute_store_passes(symbol):
    """The store the live sleeve actually trades must be usable, or research on it is void."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import intraday_common as ic
    rep = check_frame(symbol, ic.load_bars(symbol), CALENDAR)
    fails = rep.of(Severity.FAIL)
    assert not fails, [f.line() for f in fails]


def test_the_calendar_recognises_early_closes_in_the_real_store():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import intraday_common as ic
    rep = check_frame("NVDA", ic.load_bars("NVDA"), CALENDAR)
    early = [f for f in rep.findings if f.check == "early_close"]
    assert early and early[0].count >= 1, "the store spans no early close - extend it"


def test_severity_ordering_is_explicit():
    assert Severity.FAIL.value == "fail" and Severity.WARN.value == "warn"
    assert dt.date(2026, 11, 27) in CALENDAR.early_closes()
