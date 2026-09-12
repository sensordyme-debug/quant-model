"""scripts/intraday_trader.py: book accounting and the state file the live trader trusts.

Two live defects live in here as regressions:

* 2026-09-11: yesterday's closed P&L, costs and trade count survived into a new session, so the
  daily loss limit was measured against a stale number and would have tripped ~$6.8k early.
* the book file is the only thing standing between a replay's simulated positions and a live
  start-up that flattens them on the real account, so `mode` must gate the load.
"""
from __future__ import annotations

import datetime as dt
import json

import pytest

import intraday_trader as it


def _book(**pos):
    b = it.Book()
    b.pos.update(pos)
    return b


# --------------------------------------------------------------------------- P&L accounting
def test_a_winning_round_trip_books_exactly_the_spread_minus_costs():
    b = it.Book()
    it.book_fill(b, "NVDA", 100, 100.0, 1.5)      # buy 100 @ 100, $1.50 of costs
    assert b.pos == {"NVDA": 100}
    assert b.pnl({"NVDA": 100.0}) == pytest.approx(-1.5), "flat mark, so P&L is just the cost"
    assert b.pnl({"NVDA": 101.0}) == pytest.approx(98.5)

    it.book_fill(b, "NVDA", -100, 101.0, 1.5)     # sell out at 101
    assert b.pos == {}, "a flat symbol leaves the position map"
    assert b.pnl({}) == pytest.approx(97.0)       # 100 * 1.00 - 3.00 of costs
    assert (b.trades, b.costs) == (2, pytest.approx(3.0))


def test_a_losing_short_round_trip_books_the_loss():
    b = it.Book()
    it.book_fill(b, "TSLA", -50, 200.0, 2.0)      # short 50 @ 200
    assert b.pnl({"TSLA": 210.0}) == pytest.approx(-50 * 10.0 - 2.0)
    it.book_fill(b, "TSLA", 50, 210.0, 2.0)
    assert b.pnl({}) == pytest.approx(-504.0)


def test_scaling_in_and_out_keeps_cash_exact():
    b = it.Book()
    it.book_fill(b, "AMD", 100, 10.0, 0.0)
    it.book_fill(b, "AMD", 100, 12.0, 0.0)        # average 11
    assert b.pos["AMD"] == 200
    assert b.pnl({"AMD": 11.0}) == pytest.approx(0.0)
    it.book_fill(b, "AMD", -150, 13.0, 0.0)
    assert b.pos["AMD"] == 50
    assert b.pnl({"AMD": 13.0}) == pytest.approx(200 * 2.0)
    it.book_fill(b, "AMD", -50, 13.0, 0.0)
    assert b.pos == {} and b.pnl({}) == pytest.approx(400.0)


def test_flipping_through_flat_closes_the_old_position_first():
    b = it.Book()
    it.book_fill(b, "COIN", 10, 100.0, 0.0)
    it.book_fill(b, "COIN", -10, 110.0, 0.0)      # +100 realised
    it.book_fill(b, "COIN", -10, 110.0, 0.0)      # now short from 110
    assert b.pos == {"COIN": -10}
    assert b.pnl({"COIN": 110.0}) == pytest.approx(100.0)


def test_a_fresh_book_does_not_inherit_another_books_closed_pnl():
    """`Book._closed` is declared as a class attribute; `+=` rebinds it per instance, but a
    regression that mutated the class default would silently carry P&L between sessions."""
    first = it.Book()
    it.book_fill(first, "META", 10, 100.0, 0.0)
    it.book_fill(first, "META", -10, 150.0, 0.0)
    assert first.pnl({}) == pytest.approx(500.0)
    assert it.Book().pnl({}) == 0.0
    assert it.Book._closed == 0.0


def test_pnl_marks_a_missing_price_at_zero_and_says_so():
    """`pnl({})` is used deliberately at end of day, when the book is flat. With an open
    position and no price it marks to zero, which is why the caller must flatten first."""
    b = it.Book()
    it.book_fill(b, "SMCI", 10, 100.0, 0.0)
    assert b.pnl({}) == pytest.approx(-1000.0)


# --------------------------------------------------------------------------- serialisation
def test_json_round_trip_preserves_every_field():
    b = it.Book()
    it.book_fill(b, "NVDA", 100, 100.0, 1.5)
    it.book_fill(b, "TSLA", -20, 200.0, 1.0)
    it.book_fill(b, "TSLA", 20, 199.0, 1.0)
    d = b.to_json()
    back = it.Book.from_json(d)
    assert (back.pos, back.costs, back.trades) == (b.pos, b.costs, b.trades)
    assert back.pnl({"NVDA": 100.0}) == pytest.approx(b.pnl({"NVDA": 100.0}))


def test_save_book_always_tags_the_file_live():
    """A replay book must never be readable as a live one; `to_json("live")` is hardcoded in
    save_book precisely so only the live path can produce a loadable file."""
    it.save_book(_book(NVDA=10))
    d = json.loads(it.BOOK_FILE.read_text(encoding="utf-8"))
    assert d["mode"] == "live" and d["pos"] == {"NVDA": 10}


def test_load_book_ignores_a_file_that_is_not_from_a_live_run(sink):
    it.BOOK_FILE.parent.mkdir(parents=True, exist_ok=True)
    it.BOOK_FILE.write_text(json.dumps({"mode": "replay", "date": str(dt.date.today()),
                                        "pos": {"NVDA": 999}}), encoding="utf-8")
    b = it.load_book()
    assert b.pos == {}, "a simulated position must never be flattened on the real account"
    assert "ignored_book_file" in sink.kinds()


def test_load_book_carries_positions_but_drops_yesterdays_pnl(sink):
    """The 2026-09-11 defect, verbatim: positions must carry (they need flattening), the P&L
    the loss limit reads must not."""
    it.BOOK_FILE.parent.mkdir(parents=True, exist_ok=True)
    it.BOOK_FILE.write_text(json.dumps({"mode": "live", "date": "2026-09-11", "pos": {"NVDA": 100},
                                        "cost": {"NVDA": -10000.0}, "closed": -6800.0,
                                        "costs": 120.0, "trades": 42}), encoding="utf-8")
    b = it.load_book()
    assert b.pos == {"NVDA": 100}
    assert (b._closed, b.costs, b.trades) == (0.0, 0.0, 0)
    assert "book_rollover" in sink.kinds()
    roll = sink.fields("book_rollover")[0]
    assert roll["dropped_closed"] == -6800.0 and roll["from_date"] == "2026-09-11"


def test_load_book_keeps_todays_pnl_on_a_mid_session_restart():
    it.BOOK_FILE.parent.mkdir(parents=True, exist_ok=True)
    it.BOOK_FILE.write_text(json.dumps({"mode": "live", "date": str(dt.date.today()),
                                        "pos": {"NVDA": 100}, "cost": {"NVDA": -10000.0},
                                        "closed": -500.0, "costs": 12.0, "trades": 4}), encoding="utf-8")
    b = it.load_book()
    assert (b.pos, b._closed, b.trades) == ({"NVDA": 100}, -500.0, 4)


def test_load_book_with_no_file_is_an_empty_book():
    assert it.load_book().pos == {}


# --------------------------------------------------------------------------- the session clock
@pytest.mark.parametrize("hhmm, expected", [((9, 30), 0), ((10, 0), 30), ((15, 38), 368), ((15, 42), 372), ((16, 0), 390)])
def test_minute_index(hhmm, expected):
    import pandas as pd
    assert it.minute_index(pd.Timestamp(2026, 9, 11, *hhmm)) == expected


def test_flatten_and_exit_minutes_are_the_documented_clock_times():
    """AGENTS.md promises the sleeve is flat by 15:38 ET so the 15:45 daily rebalance sees only
    its own book. These two integers are that promise."""
    import pandas as pd
    from intraday_common import EXIT_MINUTE, FLATTEN_MINUTE
    assert it.minute_index(pd.Timestamp(2026, 9, 11, 15, 38)) == FLATTEN_MINUTE
    assert it.minute_index(pd.Timestamp(2026, 9, 11, 15, 42)) == EXIT_MINUTE
    assert FLATTEN_MINUTE < EXIT_MINUTE, "the loop must outlive the flatten by some minutes"
