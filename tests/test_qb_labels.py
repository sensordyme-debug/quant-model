"""Forward labels that know rows from time (AUD-20).

`.shift(-k)` moves k ROWS. `sweep_f1` guarded the day boundary but not within-day gaps,
because the IBKR store has none. Measured on the store AGENTS.md recommends for statistical
power:

    data/minute         20,399 rows / 263 sessions   : 0 within-day gaps, 0 labels dropped
    data/minute_alpaca 209,184 rows / 2,686 sessions : 73 gaps of 10-45 min, 173 of 190,394
                        labels dropped (0.091%), worst window spanning 2h10m while labelled
                        a 30-minute return

Small, real, and free to remove. These tests pin the guard on synthetic grids where the right
answer is known by construction.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_brain.core.labels import forward_return, forward_span_mask, grid_report, overlap

ET = "America/New_York"


def grid(day="2026-09-11", n=78, freq="5min", start="09:30"):
    return pd.date_range(f"{day} {start}", periods=n, freq=freq, tz=ET)


# ------------------------------------------------------------------ a clean grid is untouched

def test_a_gapless_grid_accepts_every_window():
    idx = grid(n=40)
    ok = forward_span_mask(idx, 7, 35)
    assert ok.iloc[:-7].all()
    assert not ok.iloc[-7:].any(), "windows running off the end do not exist"


def test_the_expected_span_can_be_given_as_minutes_or_a_timedelta():
    idx = grid(n=20)
    a = forward_span_mask(idx, 7, 35)
    b = forward_span_mask(idx, 7, pd.Timedelta(minutes=35))
    pd.testing.assert_series_equal(a, b)


# ------------------------------------------------------------------ a gap is caught

def test_a_within_day_gap_invalidates_the_windows_that_span_it():
    """The defect: this window passes the same-day test and still spans the wrong time."""
    idx = grid(n=40).delete(list(range(10, 14)))          # 20 minutes missing mid-session
    ok = forward_span_mask(idx, 7, 35)
    assert not ok.all()
    bad = (~ok).sum()
    assert bad > 7, "the gap should invalidate several overlapping windows, not just one"


def test_the_day_guard_alone_would_have_missed_it():
    """Proves the guard adds something: same-day is True exactly where span is False."""
    idx = grid(n=40).delete(list(range(10, 14)))
    day = idx.to_series().dt.date
    same_day = day.shift(-7) == day
    span_ok = forward_span_mask(idx, 7, 35)
    missed = same_day.fillna(False) & ~span_ok
    assert missed.any(), "there must be windows the day check accepts and the span check rejects"


def test_an_overnight_window_is_rejected_by_default():
    idx = grid("2026-09-10", n=10).append(grid("2026-09-11", n=10))
    ok = forward_span_mask(idx, 7, 35)
    assert not ok.iloc[3:10].any()


def test_same_day_can_be_switched_off_for_a_deliberately_overnight_label():
    """An overnight-holding label legitimately crosses the boundary; the guard must not
    silently forbid a design it was not written for."""
    idx = pd.date_range("2026-09-10 09:30", periods=20, freq="1D", tz=ET)
    assert forward_span_mask(idx, 5, pd.Timedelta(days=5), same_day=False).iloc[:-5].all()


# ------------------------------------------------------------------ the label itself

def test_forward_return_matches_the_row_shift_on_a_clean_grid():
    """No shipped number may move where the data is gapless - that is why IBKR drops zero."""
    idx = grid(n=40)
    px = pd.Series(np.linspace(100, 120, len(idx)), index=idx)
    naive = np.log(px.shift(-7) / px.shift(-1))
    guarded = forward_return(px, entry_offset=1, hold=6, bar_minutes=5)
    pd.testing.assert_series_equal(naive[guarded.notna()], guarded.dropna(),
                                   check_names=False)


def test_forward_return_drops_only_the_windows_that_span_a_gap():
    idx = grid(n=40).delete(list(range(10, 14)))
    px = pd.Series(np.linspace(100, 120, len(idx)), index=idx)
    naive = np.log(px.shift(-7) / px.shift(-1))
    guarded = forward_return(px, entry_offset=1, hold=6, bar_minutes=5)
    assert guarded.notna().sum() < naive.notna().sum()
    # and every surviving value is identical to the naive one
    keep = guarded.notna()
    assert np.allclose(guarded[keep], naive[keep])


# ------------------------------------------------------------------ overlap arithmetic

@pytest.mark.parametrize("horizon,step,expected", [
    (6, 6, 0),      # sweep_f1: holds 6 bars, decides every 6 -> no overlap, naive t is fine
    (5, 1, 4),      # sweep_f3 h=5, daily decisions -> 4 days of shared return
    (21, 1, 20),    # sweep_f3 h=21
    (1, 1, 0),
    (3, 5, 0),      # sampling slower than the horizon cannot overlap
])
def test_overlap(horizon, step, expected):
    assert overlap(horizon, step) == expected


def test_f1_does_not_overlap_and_f3_does():
    """The distinction that decides whether a naive t-stat is defensible."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import sweep_f1 as f1
    assert overlap(f1.HOLD, f1.STEP) == 0


# ------------------------------------------------------------------ the grid diagnostic

def test_grid_report_counts_gaps():
    idx = grid(n=40).delete(list(range(10, 14)))
    rep = grid_report(idx, bar_minutes=5)
    assert rep["rows"] == 36 and rep["sessions"] == 1
    assert rep["within_day_gaps"] == 1 and rep["gap_minutes"] == [25]


def test_grid_report_on_a_clean_grid_finds_nothing():
    rep = grid_report(grid(n=40), bar_minutes=5)
    assert rep["within_day_gaps"] == 0 and rep["gap_minutes"] == []


def test_grid_report_tolerates_a_degenerate_index():
    assert grid_report(pd.DatetimeIndex([]), bar_minutes=5)["rows"] == 0


# ------------------------------------------------------------------ against the real stores

def test_the_ibkr_store_is_gapless_so_the_guard_is_a_no_op():
    """If this ever fails, a shipped F-1 number has moved and the change must be re-measured."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import intraday_common as ic
    import sweep_f1 as f1
    if not (Path(ic.DATA_DIR) / "NVDA.parquet").exists():
        pytest.skip("IBKR minute store not on disk (gitignored)")
    d5 = f1.to_5min(ic.load_bars("NVDA"))
    assert grid_report(d5.index, bar_minutes=f1.BAR)["within_day_gaps"] == 0
