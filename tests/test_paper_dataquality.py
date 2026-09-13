"""AUD-13 / S-37: the paper runner's data-completeness gate.

The defect these exist to prevent is not "bad data reaches the signal". It is that the signal
treats bad data as *information*: `target_weights` drops an all-NaN column before it does
anything else, so a failed download is a smaller universe, and a missing `REGIME_TICKER` makes
`risk_on` return `"SPY missing"`, which liquidates the whole account under a reason that reads
like a risk decision. Each of the three shapes below therefore produces a different wrong book
with nothing in the log to tell it apart from a decision, which is why the gate is a refusal
rather than a warning.

The asymmetry that makes refusing the right answer was measured, not assumed - see clause 5 in
`scripts/sweep_s37.py` and `research/journal_daily.md`.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import paper_trade as pt
import pytest

UNIVERSE = ["SPY", "QQQ", "XLK"]


@pytest.fixture()
def good() -> pd.DataFrame:
    idx = pd.bdate_range("2026-08-03", periods=40)
    return pd.DataFrame({t: np.linspace(100.0, 110.0, 40) for t in UNIVERSE}, index=idx)


# ------------------------------------------------------------------ the three defect shapes
def test_a_healthy_frame_raises_nothing(good):
    assert pt.data_faults(good, UNIVERSE, good.index[-1], good.index[-2].date()) == []


def test_a_missing_column_is_a_fault_not_a_warning(good):
    """`risk_on` returns `regime_reason "SPY missing"` for this frame and the book goes flat."""
    faults = pt.data_faults(good.drop(columns=["SPY"]), UNIVERSE, good.index[-1],
                            good.index[-2].date())
    assert len(faults) == 1 and "SPY" in faults[0] and "no column" in faults[0]


def test_an_all_nan_column_is_a_fault(good):
    """`target_weights` runs dropna(axis=1, how="all") first, so this is a silent rotation."""
    faults = pt.data_faults(good.assign(XLK=np.nan), UNIVERSE, good.index[-1],
                            good.index[-2].date())
    assert len(faults) == 1 and "XLK" in faults[0] and "entirely NaN" in faults[0]


def test_a_nan_in_the_last_row_is_a_fault(good):
    """ffill would carry yesterday's close forward and `plan_orders` would size shares at it."""
    frame = good.copy()
    frame.iloc[-1, frame.columns.get_loc("QQQ")] = np.nan
    faults = pt.data_faults(frame, UNIVERSE, frame.index[-1], frame.index[-2].date())
    assert len(faults) == 1 and "QQQ" in faults[0] and "last row" in faults[0]


def test_an_as_of_older_than_the_previous_session_is_a_fault(good):
    """The whole frame stale at once: no per-column check can see this one."""
    short = good.iloc[:-1]
    faults = pt.data_faults(short, UNIVERSE, short.index[-1], good.index[-1].date())
    assert len(faults) == 1 and "older than the previous session" in faults[0]


def test_an_empty_frame_is_a_fault():
    empty = pd.DataFrame(columns=UNIVERSE, index=pd.DatetimeIndex([]))
    faults = pt.data_faults(empty, UNIVERSE, None, None)
    assert any("empty" in f for f in faults)


def test_every_fault_is_reported_not_just_the_first(good):
    """One alert has to carry the whole diagnosis: a partial outage is usually several
    symptoms of one failure, and fixing the first one blind restarts the same run."""
    frame = good.drop(columns=["SPY"]).assign(XLK=np.nan).iloc[:-1]
    faults = pt.data_faults(frame, UNIVERSE, frame.index[-1], good.index[-1].date())
    assert len(faults) == 3, faults


# ------------------------------------------------------- what the gate must NOT fire on
def test_a_name_before_its_own_inception_does_not_stop_the_account(good):
    """Clause 6's narrowing. A universe name with no history yet is not a data failure; a
    gate that refuses over one would stop trading the day a new ETF is added."""
    frame = good.copy()
    frame["XLK"] = np.nan
    frame.loc[frame.index[:5], "XLK"] = np.nan     # never printed at all
    faults = pt.data_faults(frame, UNIVERSE, frame.index[-1], good.index[-2].date())
    assert len(faults) == 1 and "entirely NaN" in faults[0]
    # ...but once it HAS printed, a hole in the last row is a fault again.
    frame.loc[frame.index[10], "XLK"] = 50.0
    faults = pt.data_faults(frame, UNIVERSE, frame.index[-1], good.index[-2].date())
    assert any("last row" in f for f in faults)


def test_a_held_name_outside_the_universe_is_not_checked(good):
    """S-18 left 3,227 TQQQ in the account. Refusing to trade because the retired name has no
    column would block the sale this runner exists to make; `plan_orders` reports it stuck."""
    frame = good.copy()
    frame["TQQQ"] = np.nan
    assert pt.data_faults(frame, UNIVERSE, frame.index[-1], good.index[-2].date()) == []


def test_an_as_of_newer_than_the_previous_session_is_fine(good):
    """`--history ib` keeps today's in-progress bar (AUD-25b). That is a different defect and
    this gate must not double-report it as staleness."""
    assert pt.data_faults(good, UNIVERSE, good.index[-1], good.index[-3].date()) == []


def test_no_calendar_means_no_staleness_fault(good):
    """C-3's rule: a gate that decides whether the account trades must not fail on an input
    that has nothing to do with the data - here, the calendar's own coverage window."""
    assert pt.data_faults(good.iloc[:-5], UNIVERSE, good.index[-6], None) == []


# --------------------------------------------------------------- the previous-session clock
def test_a_timestamp_previous_session_does_not_raise(good):
    """The frame's index yields `Timestamp`, `previous_session` yields `date`, and comparing
    the two raises. A TypeError inside the gate would crash the runner in the one place whose
    job is to stop it trading safely, so both sides are normalized."""
    assert pt.data_faults(good.iloc[:-1], UNIVERSE, good.index[-2], good.index[-1]) == [
        f"as_of {good.index[-2].date()} is older than the previous session "
        f"{good.index[-1].date()}"]


def test_previous_session_is_the_calendar_not_yesterday():
    """2026-09-08 is the Tuesday after Labor Day: `today - 1` is the holiday, not a session."""
    assert pt.previous_session(dt.date(2026, 9, 8)) == dt.date(2026, 9, 4)


def test_previous_session_crosses_a_weekend():
    assert pt.previous_session(dt.date(2026, 9, 14)) == dt.date(2026, 9, 11)


def test_previous_session_on_a_non_trading_day_is_the_last_session_before_it():
    """The runner can be started by hand on a Saturday; the frame is still Friday's."""
    assert pt.previous_session(dt.date(2026, 9, 12)) == dt.date(2026, 9, 11)


def test_previous_session_never_raises_outside_calendar_coverage():
    """S-37 found that `CALENDAR.trading_days` keeps answering past `coverage_end` from the
    weekday rule instead of raising - only `check_covered` enforces the contract. Without the
    explicit check this returns an unverified date, and a holiday returned here would refuse
    the whole rebalance. Not None means the gate is trusting an extrapolation."""
    assert pt.previous_session(dt.date(2035, 1, 5)) is None


# ---------------------------------------------------- the gate sits before the signal call
def test_the_gate_is_called_before_the_signal_is():
    """Ordering is the whole safety property: a fault must be unable to become an order."""
    # `Module.__file__` is `str | None` (a namespace or frozen module has none), so the guard
    # is what lets the slice below be read as a string rather than a possible None.
    assert pt.__file__ is not None, "paper_trade must be loaded from source for this check"
    src = Path(pt.__file__).read_text(encoding="utf-8")
    body = src[src.index("    # ---- signal ---"):]
    assert body.index("data_faults(") < body.index("call_signal("), \
        "data_faults must run before call_signal, or a defective frame can produce orders"
    assert body.index("data_faults(") < body.index("plan_orders(")
