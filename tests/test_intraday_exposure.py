"""A-20: the harness records what the book actually HOLDS, not only what it traded.

A-18 measured a +$41-69/day channel it could only attribute by inference, because `summarize()`
reported turnover and never exposure. The reading was that whole-share `floor()` makes a
size-scaled book carry systematically less than k x its target - half a share is a larger fraction
of a smaller position. These tests pin the three things that reading needs to be a measurement:

  * `intended_gross` is the sizing step's ASK, with the same two clamps `targets_to_orders`
    applies and in the same order (gross cap, then per-symbol cap);
  * realized gross is the book's own marks, reconstructible from the fills and the prices;
  * the shortfall between them GROWS as the book is scaled down, which is the mechanism itself.

Inertness of the accumulation is pinned next door: `tests/test_intraday_size_schedule.py` fixes
exact share counts and an exact `daily` frame on the same toy books, and those are the numbers a
change to the bar loop would move.
"""
from __future__ import annotations

import datetime as dt
import math
import sys
from pathlib import Path

import intraday_backtest as ib
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "algorithms" / "intraday"))
from base import features  # noqa: E402

ET = "America/New_York"
EQUITY = 100_000.0
DAY = "2026-03-02"


def bars(day: str, minutes: int, price: float = 300.0):
    rows, idx = [], []
    for m in range(minutes):
        rows.append({"o": price, "h": price + 0.5, "l": price - 0.5, "c": price + 0.1, "v": 1000.0})
        idx.append(pd.Timestamp(f"{day} 09:30", tz=ET) + pd.Timedelta(minutes=m))
    return pd.DataFrame(rows, index=pd.DatetimeIndex(idx))


class Long10:
    """Wants 10% of NVDA every bar; the no-trade band means it trades essentially once."""

    PARAMS: dict = {}

    @staticmethod
    def decide(now, feats, book, equity, state, params):
        return {"NVDA": 0.10}


class Flat:
    PARAMS: dict = {}

    @staticmethod
    def decide(now, feats, book, equity, state, params):
        return {}


#: `run` drops any session with fewer than 30 bars, so every toy book here is at least that.
MINUTES = 32


def _run(strategy=Long10, sched=None, minutes=MINUTES, price=300.0, equity=EQUITY, day=DAY):
    px = bars(day, minutes, price=price)
    return ib.run(strategy, {"NVDA": px}, equity, {}, feats_all={"NVDA": features(px)},
                  collect_trades=True, size_schedule=sched)


def test_intended_gross_applies_the_gross_cap_then_the_per_symbol_cap():
    """The ASK, with exactly the clamps `targets_to_orders` uses. Order matters: scaling for the
    gross cap first can pull a name back under the per-symbol cap, and clamping first cannot."""
    cap = ib.RISK["per_symbol_hard_cap"]
    gross_cap = ib.RISK["gross_hard_cap"]
    assert ib.intended_gross({}) == 0.0
    assert ib.intended_gross({"A": 0.0, "B": 0.0}) == 0.0
    # under both caps: the ask is the ask, and the sign does not matter
    assert ib.intended_gross({"A": 0.01, "B": -0.02}) == pytest.approx(0.03)
    # one name over the per-symbol cap, book under the gross cap
    assert ib.intended_gross({"A": cap * 3}) == pytest.approx(min(cap, gross_cap))
    # book over the gross cap: every weight is scaled, and the total is the gross cap
    over = {f"S{i}": gross_cap for i in range(4)}
    assert ib.intended_gross(over) == pytest.approx(min(gross_cap, 4 * cap))


def test_realized_gross_is_the_book_marked_at_each_bar():
    """Rebuilt from the fills and the prices, independently of the accumulator."""
    s = _run()
    d = s["daily"].iloc[0]
    fills = [t for t in s["trades_log"] if t["why"] != "eod"]
    assert len(fills) == 1 and fills[0]["qty"] == 33      # floor(0.10 * 100_000 / 300.1)
    q, close = fills[0]["qty"], 300.1
    cash = EQUITY - sum(t["qty"] * t["px"] + t["cost"] for t in fills)
    held = abs(q) * close / (cash + q * close)
    # bar 0 decides and holds nothing; every later bar holds the fill, marked at the bar close
    assert d["bars"] == MINUTES
    assert d["gross"] == pytest.approx(held * (MINUTES - 1) / MINUTES, rel=1e-9)
    # the ask of the last bar is never scored, because no bar follows it to fill on
    assert d["dec_bars"] == MINUTES - 1
    assert d["intent_dec"] == pytest.approx(0.10, rel=1e-12)
    # every scored decision bar is paired with a mark that already holds the position, so the
    # shortfall is the share floor alone and not the one-bar fill latency
    assert d["gross_dec"] == pytest.approx(held, rel=1e-9)
    assert s["gross_shortfall_pct"] == pytest.approx(100.0 * (1.0 - held / 0.10), rel=1e-9)
    assert 0 < s["gross_shortfall_pct"] < 1.5          # ~ half a $300 share on a $10,000 position
    assert s["gross_realized_x"] == pytest.approx(d["gross"], rel=1e-12)


def test_the_shortfall_grows_as_the_book_is_scaled_down():
    """A-20's mechanism, and the whole reason the column exists. At $300 a share the unscaled book
    holds 33 of an asked-for 33.32; the half-size book holds 16 of an asked-for 16.66. The missing
    half share is the same number of dollars and a twice-as-large fraction of a smaller position,
    so the scaled book is further below its own target than the unscaled one is below its."""
    day = dt.date(2026, 3, 2)
    full = _run()
    half = _run(sched={day: 0.5})
    assert full["gross_shortfall_pct"] > 0
    assert half["gross_shortfall_pct"] > full["gross_shortfall_pct"] + 1.0
    # and it is the holding that shrank faster than k, not the ask
    assert half["gross_intended_x"] == pytest.approx(0.5 * full["gross_intended_x"], rel=1e-9)
    assert half["gross_realized_decision_x"] < 0.5 * full["gross_realized_decision_x"]


def test_a_bigger_book_rounds_away_less_of_it():
    """The other side of the same statement: the shortfall is a share price over a position size,
    so it vanishes as the book grows. A 100x book at the same weights loses ~100x less to it."""
    small = _run()
    big = _run(equity=EQUITY * 100)
    assert big["gross_shortfall_pct"] < small["gross_shortfall_pct"] / 50.0
    assert big["gross_shortfall_pct"] < 0.05


def test_a_book_that_asks_for_nothing_holds_nothing_and_does_not_divide_by_zero():
    s = _run(strategy=Flat)
    assert s["gross_realized_x"] == 0.0
    assert s["gross_intended_x"] == 0.0
    assert math.isnan(s["gross_shortfall_pct"])


def test_the_pooled_figures_are_bar_weighted_not_an_average_of_averages():
    """Two sessions of unequal length must pool by bar count; a mean of the two session means
    would silently over-weight the short day."""
    a = bars("2026-03-02", 30)
    b = bars("2026-03-03", 90)
    px = pd.concat([a, b])
    s = ib.run(Long10, {"NVDA": px}, EQUITY, {}, feats_all={"NVDA": features(px)})
    d = s["daily"]
    assert len(d) == 2 and d["bars"].tolist() == [30, 90]
    want = (d["gross"] * d["bars"]).sum() / d["bars"].sum()
    assert s["gross_realized_x"] == pytest.approx(float(want), rel=1e-12)
    assert s["gross_realized_x"] != pytest.approx(float(d["gross"].mean()), 1e-6)
    intent = (d["intent_dec"] * d["dec_bars"]).sum() / d["dec_bars"].sum()
    assert s["gross_intended_x"] == pytest.approx(float(intent), rel=1e-12)
    assert s["gross_shortfall_pct"] == pytest.approx(
        100.0 * (1.0 - s["gross_realized_decision_x"] / s["gross_intended_x"]), rel=1e-9)
