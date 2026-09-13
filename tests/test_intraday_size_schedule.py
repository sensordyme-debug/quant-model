"""A-18: the harness's per-session size multiplier (`--size-schedule`).

Every A-15/A-17 sizing conclusion on this sleeve was scored by multiplying a persisted daily P&L
series by k_t. This option is what re-scores such a claim THROUGH the harness, so the two
properties that make it usable are pinned here:

  * absent, and present-at-k=1.0, are the shipped path EXACTLY - not approximately. A sizing study
    that cannot reproduce its own unscaled base has measured nothing;
  * k is applied to the strategy's WEIGHTS, before the per-symbol and gross caps, and changes no
    decision the strategy makes.

The nonlinearity the option exists to expose - whole-share rounding - is pinned too, because it is
the thing the linear scoring cannot see and therefore the thing a future refactor must not
silently smooth away.
"""
from __future__ import annotations

import datetime as dt
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


def bars(day: str, minutes: int, price: float = 100.0, step: float = 0.0):
    rows, idx = [], []
    for m in range(minutes):
        o = price + step * m
        rows.append({"o": o, "h": o + 0.5, "l": o - 0.5, "c": o + 0.1, "v": 1000.0})
        idx.append(pd.Timestamp(f"{day} 09:30", tz=ET) + pd.Timedelta(minutes=m))
    return pd.DataFrame(rows, index=pd.DatetimeIndex(idx))


class Long10:
    """Wants 10% of NVDA every bar; the no-trade band means it trades essentially once."""

    PARAMS: dict = {}
    seen: list = []

    @staticmethod
    def decide(now, feats, book, equity, state, params):
        Long10.seen.append(equity)
        return {"NVDA": 0.10}


def _run(sched, default=1.0, price=100.0):
    Long10.seen = []
    px = bars(DAY, 40, price=price, step=1.0)
    feats = {"NVDA": features(px)}
    return ib.run(Long10, {"NVDA": px}, EQUITY, {}, feats_all=feats, collect_trades=True,
                  size_schedule=sched, size_default=default)


def test_absent_and_k_one_are_the_same_run():
    """The identity every sizing study rests on: k = 1.0 must be the shipped path, exactly."""
    base = _run(None)
    one = _run({dt.date(2026, 3, 2): 1.0})
    assert one["daily"].equals(base["daily"])
    for key in ("net_profit_pct", "trades", "costs_total", "max_drawdown_pct"):
        assert one[key] == base[key]
    assert [t["qty"] for t in one["trades_log"]] == [t["qty"] for t in base["trades_log"]]


def test_a_half_size_schedule_halves_the_position():
    """k scales the WEIGHT. Sizing happens on the decision bar's CLOSE (100.1), so 10% of
    $100,000 is floor(99.90) = 99 shares and half of it is floor(49.95) = 49 - which is 49 and
    not 49.5, and that half-share is the whole reason this item exists."""
    full = _run(None)
    half = _run({dt.date(2026, 3, 2): 0.5})
    assert full["trades_log"][0]["qty"] == 99
    assert half["trades_log"][0]["qty"] == 49


def test_the_share_floor_is_the_nonlinearity_the_linear_scoring_cannot_see():
    """A-18's whole point. At $300 a share, 10% of $100,000 is 33.33 shares -> 33. Two thirds of
    that is 22.22 -> 22, but two thirds of 33 is 22.0 only by luck; at k = 0.7 the linear scoring
    predicts 23.1 shares and the harness holds 23, and at k = 0.5 it predicts 16.5 and holds 16.
    The floor is applied AFTER k, never to a scaled share count, so the error does not compound.
    """
    full = _run(None, price=300.0)
    assert full["trades_log"][0]["qty"] == 33
    for k, want in ((0.7, 23), (0.5, 16)):
        got = _run({dt.date(2026, 3, 2): k}, price=300.0)["trades_log"][0]["qty"]
        assert got == want, f"k={k}: harness held {got}, expected floor(0.10*{k}*100000/300)"


def test_the_strategy_sees_the_unscaled_book():
    """k must not leak into the strategy's own view, or it stops being a pure size overlay and
    every decision becomes a function of the schedule."""
    _run({dt.date(2026, 3, 2): 0.4})
    scaled_first = Long10.seen[0]
    _run(None)
    assert scaled_first == Long10.seen[0] == EQUITY


def test_an_uncovered_session_runs_at_the_default_and_is_counted():
    s = _run({dt.date(2020, 1, 2): 0.5})          # a day that is not in this run at all
    assert s["size_sessions_scaled"] == 0
    assert s["size_sessions_uncovered"] == 1
    assert s["daily"].equals(_run(None)["daily"])  # default 1.0 = untouched


def test_the_loader_rejects_an_ambiguous_or_broken_csv(tmp_path):
    good = tmp_path / "s.csv"
    good.write_text("day,k\n2026-03-02,0.5\n", encoding="utf-8")
    assert ib.load_size_schedule(str(good)) == {dt.date(2026, 3, 2): 0.5}
    assert ib.load_size_schedule(None) is None

    two = tmp_path / "two.csv"
    two.write_text("day,a,b\n2026-03-02,0.5,0.6\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        ib.load_size_schedule(str(two))
    assert ib.load_size_schedule(str(two), "b") == {dt.date(2026, 3, 2): 0.6}

    bad = tmp_path / "bad.csv"
    bad.write_text("day,k\n2026-03-02,-1.0\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        ib.load_size_schedule(str(bad))

    nokey = tmp_path / "nokey.csv"
    nokey.write_text("date,k\n2026-03-02,0.5\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        ib.load_size_schedule(str(nokey))
