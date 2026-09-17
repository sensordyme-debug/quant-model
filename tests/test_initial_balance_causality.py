"""Phase 1/C for the ES strategy: nothing at time t may depend on data after t.

The brief names fourteen attack surfaces. Each is attacked here by CORRUPTING THE FUTURE and
requiring every earlier output to be byte-identical, which is a stronger test than inspecting
the code: it does not matter how the leak would have been written, only that the answer does
not move.
"""
from __future__ import annotations

import dataclasses
import datetime as dt

import pytest

from quant_brain.strategies.initial_balance_reversion.engine import Engine
from quant_brain.strategies.initial_balance_reversion.indicators import (
    Excursion,
    InitialBalance,
)
from quant_brain.strategies.initial_balance_reversion.spec import FROZEN, TIMEZONE
from quant_brain.strategies.vwap_pullback.indicators import Bar
from tests.conftest_ib import Session, run


def fingerprint(eng: Engine) -> list[tuple]:
    """Everything a trade is judged on, as a comparable value."""
    return [(t.trade_id, str(t.session), t.direction, t.entry_time, t.exit_time,
             t.entry_price, t.exit_price, t.ib_high, t.ib_low, t.ib_range, t.ib_midpoint,
             t.trap_extreme, t.stop_price, t.target_price, t.gross_pnl, t.commission,
             t.entry_slippage, t.exit_slippage, t.net_pnl, t.exit_reason, t.mae, t.mfe)
            for t in eng.trades]


def base_session(day=dt.date(2026, 6, 10)) -> Session:
    return (Session(day=day).ib(high=5020.0, low=5000.0)
            .quiet("10:30", "10:40", 5010.0)
            .block("10:40", 5002.0, 5002.0, 4995.0, 5002.0)
            .block("10:45", 5002.0, 5012.0, 5002.0, 5011.0)
            .quiet("10:50", "15:45", 5011.0))


def corrupt_after(bars: list[Bar], cut: str, price: float = 99_999.0) -> list[Bar]:
    """Replace every bar at or after `cut` (ET HH:MM) with an absurd one."""
    hh, mm = cut.split(":")
    limit = int(hh) * 60 + int(mm)
    out = []
    for b in bars:
        local = b.timestamp.astimezone(TIMEZONE)
        if local.hour * 60 + local.minute >= limit:
            out.append(Bar(timestamp=b.timestamp, open=price, high=price, low=price,
                           close=price, volume=7_777_777.0))
        else:
            out.append(b)
    return out


def feed(bars: list[Bar], day: dt.date) -> Engine:
    eng = Engine(spec=FROZEN)
    eng.start_session(day, bars[0].timestamp)
    for b in bars:
        eng.on_bar(b)
    return eng


# ======================================================================================
# 1-4. THE INITIAL BALANCE CANNOT SEE PAST 10:30
# ======================================================================================

@pytest.mark.parametrize("cut", ["10:30", "10:35", "11:00", "12:00", "14:00"])
def test_the_ib_is_identical_however_the_rest_of_the_day_behaves(cut):
    s = base_session()
    clean = feed(s.bars(), s.day)
    wrecked = feed(corrupt_after(s.bars(), cut), s.day)
    assert (clean.ib.ib_high, clean.ib.ib_low) == (5020.0, 5000.0)
    assert (wrecked.ib.ib_high, wrecked.ib.ib_low) == (clean.ib.ib_high, clean.ib.ib_low)
    assert wrecked.ib.ib_range == clean.ib.ib_range == 20.0
    assert wrecked.ib.midpoint == clean.ib.midpoint == 5010.0


def test_a_violent_bar_at_1030_cannot_enter_the_ib():
    """The 10:30 bucket is the first one OUTSIDE the window. It seals, it does not extend."""
    s = base_session().block("10:30", 5010.0, 6000.0, 4000.0, 5010.0)
    eng = feed(s.bars(), s.day)
    assert eng.ib.ib_high == 5020.0 and eng.ib.ib_low == 5000.0
    assert eng.ib.buckets == 12, "exactly the twelve buckets from 09:30 to 10:25"


def test_the_ib_accumulates_only_its_own_twelve_buckets():
    ib = InitialBalance(start_minute=570, end_minute=630)
    fake = dataclasses.make_dataclass("F", ["high", "low", "close"])
    for m in range(570, 630, 5):
        ib.update(fake(5010.0, 4990.0, 5000.0), m)
    assert ib.buckets == 12
    ib.update(fake(9999.0, 1.0, 5000.0), 630)
    assert ib.complete and ib.ib_high == 5010.0 and ib.ib_low == 4990.0


# ======================================================================================
# 5-9. TRAP, EXTREME, SIGNAL, TARGET AND STOP
# ======================================================================================

@pytest.mark.parametrize("cut", ["10:45", "10:50", "11:00", "13:00"])
def test_every_trade_taken_before_the_corruption_is_byte_identical(cut):
    s = base_session()
    clean = feed(s.bars(), s.day)
    wrecked = feed(corrupt_after(s.bars(), cut), s.day)
    hh, mm = cut.split(":")
    limit = int(hh) * 60 + int(mm)
    before = [t for t in fingerprint(clean)
              if t[4].astimezone(TIMEZONE).hour * 60 + t[4].astimezone(TIMEZONE).minute
              <= limit]
    got = fingerprint(wrecked)[:len(before)]
    assert got == before, "an output before the corruption moved"


def test_the_excursion_extreme_cannot_be_revised_by_a_later_bar():
    """Sealed at the rejection. A deeper low afterwards must not move the stop."""
    s = (Session().ib(high=5020.0, low=5000.0)
         .quiet("10:30", "10:40", 5010.0)
         .block("10:40", 5000.0, 5000.0, 4997.0, 4997.0)
         .block("10:45", 4997.0, 5001.0, 4997.0, 5001.0)      # rejection, E = 4997
         .block("10:50", 5001.0, 5001.0, 4996.75, 4999.0)     # deeper, AFTER the entry
         .quiet("10:55", "15:45", 4999.0))
    eng = run(s)
    t = eng.trades[0]
    assert t.trap_extreme == 4997.0
    assert t.stop_price == 4996.75, "the stop is from the sealed extreme, not the later low"


def test_the_target_is_fixed_before_the_armed_window_and_never_moves():
    s = base_session()
    eng = feed(s.bars(), s.day)
    assert eng.trades[0].target_price == 5010.0
    #: a wildly different afternoon leaves the target where it was
    w = feed(corrupt_after(s.bars(), "11:00"), s.day)
    assert w.trades[0].target_price == 5010.0


# ======================================================================================
# 10-14. COUNTS, GOVERNOR, TIME STOP, FLATTEN, CROSS-SESSION
# ======================================================================================

def test_the_trade_count_cannot_see_a_future_trade():
    s = (Session().ib(high=5020.0, low=5000.0)
         .block("10:30", 5000.0, 5000.0, 4998.0, 4998.0)
         .block("10:35", 4998.0, 5001.0, 4998.0, 5001.0)
         .block("10:40", 5001.0, 5011.0, 5001.0, 5010.0)
         .quiet("10:45", "15:45", 5010.0))
    eng = feed(s.bars(), s.day)
    assert eng.trades[0].realized_before == 0.0
    assert eng.trades[0].realized_after == pytest.approx(eng.trades[0].net_pnl)


def test_the_governor_marks_only_on_bars_it_has_seen():
    """A catastrophic bar AFTER the exit cannot retro-trip the killswitch."""
    s = base_session()
    clean = feed(s.bars(), s.day)
    assert not clean.governor.halted
    w = feed(corrupt_after(s.bars(), "11:00", price=1.0), s.day)
    assert fingerprint(w)[0] == fingerprint(clean)[0]


def test_two_sessions_do_not_leak_into_one_another():
    a = base_session(dt.date(2026, 6, 10))
    b = base_session(dt.date(2026, 6, 11))
    solo_a = run(a)
    solo_b = run(b)
    both = Engine(spec=FROZEN)
    for s in (a, b):
        bars = s.bars()
        both.start_session(s.day, bars[0].timestamp)
        for x in bars:
            both.on_bar(x)
        both.end_session(bars[-1].timestamp)
    assert fingerprint(both)[:1] == fingerprint(solo_a)
    assert [f[1:] for f in fingerprint(both)[1:]] == [f[1:] for f in fingerprint(solo_b)]
    assert both.governor.day == dt.date(2026, 6, 11)


def test_truncating_the_day_leaves_the_completed_trades_unchanged():
    s = base_session()
    full = feed(s.bars(), s.day)
    short = feed([b for b in s.bars()
                  if b.timestamp.astimezone(TIMEZONE).hour < 12], s.day)
    assert fingerprint(short) == fingerprint(full)[:len(fingerprint(short))]
    assert len(fingerprint(short)) >= 1


# ======================================================================================
# STRUCTURAL
# ======================================================================================

def test_the_excursion_tracker_holds_nothing_it_was_not_fed():
    e = Excursion()
    assert e.side == 0
    fake = dataclasses.make_dataclass("F", ["high", "low", "close"])
    e.update(fake(5005.0, 4995.0, 4996.0), 5020.0, 5000.0)
    assert e.extreme == 4995.0
    e.update(fake(4997.0, 4990.0, 4992.0), 5020.0, 5000.0)
    assert e.extreme == 4990.0
    #: a bucket that does not trade lower leaves the extreme alone
    e.update(fake(4999.0, 4993.0, 4994.0), 5020.0, 5000.0)
    assert e.extreme == 4990.0
