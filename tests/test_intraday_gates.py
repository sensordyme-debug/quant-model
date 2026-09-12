"""scripts/intraday_trader.py: Trader.step - the risk gates, in the order they fire.

Every one of these is a path that only runs when something has already gone wrong, which is
exactly why none of them is exercised by a normal replay. They are asserted here against a fake
executor so a refactor of the loop cannot silently disarm one.
"""
from __future__ import annotations

import intraday_trader as it
import pandas as pd
import pytest
from intraday_common import DAILY_LOSS_LIMIT, FLATTEN_MINUTE

NAV = 1_000_000.0


class FakeExecutor:
    """Records submissions; settles whatever the test queues into `to_settle`."""

    def __init__(self):
        self.submitted: list[dict] = []
        self.to_settle: list[tuple] = []

    def submit(self, orders, when):
        self.submitted.append(dict(orders))

    def settle(self, t):
        out, self.to_settle = self.to_settle, []
        return out


class FakeStrategy:
    def __init__(self, targets=None, raises=False):
        self.targets, self.raises, self.calls = targets or {}, raises, 0

    def decide(self, t, feats, pos, equity, state, params):
        self.calls += 1
        if self.raises:
            raise RuntimeError("signal blew up")
        return dict(self.targets)


def make(strategy=None, pos=None, cost=None, closed=0.0, dry_run=False, mode="test", equity_frac=1.0):
    ex = FakeExecutor()
    book = it.Book()
    book.pos.update(pos or {})
    book.cost.update(cost or {})
    book._closed = closed
    t = it.Trader(strategy or FakeStrategy(), {}, equity_frac, book, ex, dry_run, mode)
    return t, ex


def bar(hh, mm):
    return pd.Timestamp(2026, 9, 11, hh, mm)


# --------------------------------------------------------------------------- happy path
def test_a_normal_minute_asks_the_strategy_and_submits():
    strat = FakeStrategy({"NVDA": 0.10})
    t, ex = make(strat)
    t.step(bar(10, 0), {}, {"NVDA": 100.0}, NAV)
    assert strat.calls == 1
    assert ex.submitted == [{"NVDA": 1000}]        # 0.10 * 1,000,000 / 100


def test_dry_run_decides_but_never_submits():
    strat = FakeStrategy({"NVDA": 0.10})
    t, ex = make(strat, dry_run=True)
    t.step(bar(10, 0), {}, {"NVDA": 100.0}, NAV)
    assert strat.calls == 1 and ex.submitted == []


def test_fills_are_settled_before_the_new_decision_is_sized():
    """Order of operations matters: a fill that arrived last minute must be in the book before
    this minute's delta is computed, or the trader doubles up on its own order."""
    strat = FakeStrategy({"NVDA": 0.10})
    t, ex = make(strat)
    ex.to_settle = [("NVDA", 1000, 100.0, 5.0)]
    t.step(bar(10, 0), {}, {"NVDA": 100.0}, NAV)
    assert t.book.pos == {"NVDA": 1000}
    assert ex.submitted == [], "the target is already held; no second order"


def test_the_same_bar_twice_does_not_decide_twice():
    """The live feed can return the same last bar on consecutive polls (Yahoo lags ~1 min)."""
    strat = FakeStrategy({"NVDA": 0.10})
    t, ex = make(strat)
    t.step(bar(10, 0), {}, {"NVDA": 100.0}, NAV)
    t.step(bar(10, 0), {}, {"NVDA": 100.0}, NAV)
    t.step(bar(9, 59), {}, {"NVDA": 100.0}, NAV)     # an older bar is also ignored
    assert strat.calls == 1 and len(ex.submitted) == 1


def test_nav_open_is_latched_on_the_first_bar_of_the_session():
    t, _ = make()
    t.step(bar(9, 31), {}, {}, NAV)
    t.step(bar(9, 32), {}, {}, NAV * 0.5)
    assert t.nav_open == NAV, "the loss limit must be measured against start-of-day NAV"


# --------------------------------------------------------------------------- daily loss limit
def _losing_book(loss):
    """A book holding 1,000 shares bought at $100 whose mark produces exactly `-loss`."""
    return {"NVDA": 1000}, {"NVDA": -100_000.0}, (100_000.0 - loss) / 1000.0


def test_loss_limit_flattens_and_stops_for_the_day(sink):
    pos, cost, px = _losing_book(DAILY_LOSS_LIMIT * NAV + 1_000)     # -$26,000 against a -$25,000 limit
    strat = FakeStrategy({"NVDA": 0.10})
    t, ex = make(strat, pos=pos, cost=cost)
    t.step(bar(10, 0), {}, {"NVDA": px}, NAV)
    assert t.stopped is True
    assert ex.submitted == [{"NVDA": -1000}], "the whole book is sent flat"
    assert "loss_limit" in sink.kinds()
    assert any("loss limit" in a for a in sink.alerts)


def test_loss_limit_stays_stopped_on_later_bars(sink):
    pos, cost, px = _losing_book(DAILY_LOSS_LIMIT * NAV + 1_000)
    strat = FakeStrategy({"NVDA": 0.10})
    t, ex = make(strat, pos=pos, cost=cost)
    t.step(bar(10, 0), {}, {"NVDA": px}, NAV)
    ex.to_settle = [("NVDA", -1000, px, 5.0)]
    t.step(bar(10, 1), {}, {"NVDA": px}, NAV)
    t.step(bar(10, 2), {}, {"NVDA": px}, NAV)
    assert strat.calls == 0, "a stopped sleeve never asks the strategy again"
    assert ex.submitted == [{"NVDA": -1000}], "and never re-enters"
    assert sink.kinds().count("loss_limit") == 1, "the limit is reported once, not every minute"


def test_a_loss_just_inside_the_limit_keeps_trading():
    pos, cost, px = _losing_book(DAILY_LOSS_LIMIT * NAV - 1_000)     # -$24,000
    strat = FakeStrategy({"NVDA": 0.10})
    t, _ = make(strat, pos=pos, cost=cost)
    t.step(bar(10, 0), {}, {"NVDA": px}, NAV)
    assert t.stopped is False and strat.calls == 1


def test_the_limit_scales_with_the_account_not_with_a_constant():
    small_nav = 100_000.0
    pos, cost, px = _losing_book(DAILY_LOSS_LIMIT * small_nav + 100)
    t, _ = make(pos=pos, cost=cost)
    t.step(bar(10, 0), {}, {"NVDA": px}, small_nav)
    assert t.stopped is True
    assert DAILY_LOSS_LIMIT == 0.025


# --------------------------------------------------------------------------- halt files
@pytest.mark.parametrize("which", [0, 1])
def test_a_halt_file_flattens_and_stops(which, sink, monkeypatch):
    it.HALT_FILES[which].write_text("stop", encoding="utf-8")
    strat = FakeStrategy({"NVDA": 0.10})
    t, ex = make(strat, pos={"NVDA": 500}, cost={"NVDA": -50_000.0})
    t.step(bar(10, 0), {}, {"NVDA": 100.0}, NAV)
    assert t.stopped is True
    assert ex.submitted == [{"NVDA": -500}]
    assert "halt" in sink.kinds()


def test_no_halt_file_means_no_halt():
    assert not any(p.exists() for p in it.HALT_FILES), "the fixture must have redirected these"
    strat = FakeStrategy({"NVDA": 0.10})
    t, _ = make(strat)
    t.step(bar(10, 0), {}, {"NVDA": 100.0}, NAV)
    assert t.stopped is False


# --------------------------------------------------------------------------- the 15:38 flatten
def test_at_the_flatten_minute_the_book_is_sent_flat_whatever_the_strategy_wants():
    strat = FakeStrategy({"NVDA": 0.20})
    t, ex = make(strat, pos={"NVDA": 500}, cost={"NVDA": -50_000.0})
    t.step(bar(15, 38), {}, {"NVDA": 100.0}, NAV)
    assert strat.calls == 0, "past the flatten minute the strategy is not even consulted"
    assert ex.submitted == [{"NVDA": -500}]


def test_one_minute_before_the_flatten_minute_still_trades():
    strat = FakeStrategy({"NVDA": 0.10})
    t, ex = make(strat)
    t.step(bar(15, 37), {}, {"NVDA": 100.0}, NAV)
    assert strat.calls == 1 and ex.submitted == [{"NVDA": 1000}]


def test_an_already_flat_book_at_the_flatten_minute_sends_nothing():
    t, ex = make(FakeStrategy({"NVDA": 0.20}))
    t.step(bar(15, 39), {}, {"NVDA": 100.0}, NAV)
    assert ex.submitted == []


def test_flatten_minute_matches_the_constant():
    assert it.minute_index(bar(15, 38)) == FLATTEN_MINUTE


# --------------------------------------------------------------------------- strategy failure
def test_a_strategy_exception_is_logged_and_treated_as_flat(sink):
    """A broken signal must not crash the loop mid-session, and it must not be read as "hold"
    either - an unparsed target set means no target set."""
    t, ex = make(FakeStrategy(raises=True))
    t.step(bar(10, 0), {}, {"NVDA": 100.0}, NAV)
    assert "decide_error" in sink.kinds()
    assert ex.submitted == []


def test_a_strategy_exception_while_holding_exits_the_position(sink):
    t, ex = make(FakeStrategy(raises=True), pos={"NVDA": 500}, cost={"NVDA": -50_000.0})
    t.step(bar(10, 0), {}, {"NVDA": 100.0}, NAV)
    assert ex.submitted == [{"NVDA": -500}], "no opinion means no position"


def test_a_strategy_returning_none_is_treated_as_flat():
    strat = FakeStrategy()
    # setattr rather than direct assignment: `decide` is defined on the class, and a type
    # checker reads an instance-attribute assignment as shadowing a method it cannot verify.
    setattr(strat, "decide", lambda *a, **k: None)  # noqa: B010
    t, ex = make(strat, pos={"NVDA": 500}, cost={"NVDA": -50_000.0})
    t.step(bar(10, 0), {}, {"NVDA": 100.0}, NAV)
    assert ex.submitted == [{"NVDA": -500}]


# --------------------------------------------------------------------------- persistence
def test_only_a_real_live_run_writes_the_book_file():
    for mode, dry_run, persist in (("live", False, True), ("live", True, False),
                                   ("replay", False, False), ("test", False, False)):
        t, _ = make(mode=mode, dry_run=dry_run)
        assert t.persist is persist, f"mode={mode} dry_run={dry_run}"


def test_a_replay_step_never_writes_the_live_book_file():
    t, _ = make(mode="replay")
    t.step(bar(10, 0), {}, {"NVDA": 100.0}, NAV)
    assert not it.BOOK_FILE.exists()


def test_a_live_step_does_write_the_book_file():
    t, _ = make(mode="live")
    t.step(bar(10, 0), {}, {"NVDA": 100.0}, NAV)
    assert it.BOOK_FILE.exists()


# --------------------------------------------------------------------------- reporting cadence
def test_a_snapshot_is_logged_at_most_every_thirty_minutes(sink):
    t, _ = make()
    for minute in range(0, 75, 5):
        t.step(bar(10, 0) + pd.Timedelta(minutes=minute), {}, {"NVDA": 100.0}, NAV)
    assert sink.kinds().count("snapshot") == 3       # t+0, t+30, t+60
