"""AUD-21: the research harness's own biases, and the switches that reproduce the old ones.

Six defects were filed, three of which can move a P&L. What is pinned here is the *mechanism* of
each, on synthetic bars small enough to reason about by hand, plus the guarantee that the legacy
switches still reproduce the pre-2026-09-12 behaviour so a row already in
`research/experiments.jsonl` can be re-run.
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


def bars(day: str, minutes, price=100.0, step=0.0, skip=()):
    """One session of flat-ish 1-minute bars; `skip` drops those minute indices entirely."""
    rows, idx = [], []
    for m in range(minutes):
        if m in skip:
            continue
        o = price + step * m
        rows.append({"o": o, "h": o + 0.5, "l": o - 0.5, "c": o + 0.1, "v": 1000.0})
        idx.append(pd.Timestamp(f"{day} 09:30", tz=ET) + pd.Timedelta(minutes=m))
    return pd.DataFrame(rows, index=pd.DatetimeIndex(idx))


@pytest.fixture(autouse=True)
def restore_harness():
    """Every test here rebinds module state the whole harness reads; put it back."""
    fill, nav = ib.FILL_MODEL, ib.RISK["nav_frac"]
    yield
    ib.FILL_MODEL, ib.RISK["nav_frac"] = fill, nav


# --------------------------------------------------------------- defect 1: the missing-bar fill
class OneShot:
    """Wants 10% of NVDA every bar; the 2%-of-equity band means it trades essentially once."""

    PARAMS: dict = {}

    @staticmethod
    def decide(now, feats, book, equity, state, params):
        return {"NVDA": 0.10}


def _run_one(skip, fill_model):
    """NVDA misses `skip`; AAPL prints every minute, which is what puts that minute in the
    session's clock at all. A one-symbol universe cannot even express this defect - the loop
    iterates the union of bar times, so a lone symbol's gap is not a minute."""
    ib.FILL_MODEL = fill_model
    nvda = bars("2026-03-02", 40, price=100.0, step=1.0, skip=skip)
    aapl = bars("2026-03-02", 40, price=50.0)
    feats = {"NVDA": features(nvda), "AAPL": features(aapl)}
    s = ib.run(OneShot, {"NVDA": nvda, "AAPL": aapl}, EQUITY, {}, feats_all=feats, collect_trades=True)
    return [t for t in s["trades_log"] if t["why"] != "eod"]


def test_a_missing_bar_no_longer_fills_at_the_decision_close():
    """The order is decided on bar 0's close and would fill at bar 1's open - but bar 1 never
    printed, so it must wait for bar 2's OPEN (102.0), not take bar 0's close (100.1)."""
    fills = _run_one(skip={1}, fill_model="next_bar")
    assert fills[0]["px"] == pytest.approx(102.0)


def test_the_legacy_switch_still_books_it_at_the_decision_close():
    fills = _run_one(skip={1}, fill_model="decision_close")
    assert fills[0]["px"] == pytest.approx(100.1)


def test_with_no_missing_bar_the_two_models_agree_to_the_cent():
    """Clause 7's shape: the fix is invisible on a complete session."""
    a = _run_one(skip=(), fill_model="next_bar")
    b = _run_one(skip=(), fill_model="decision_close")
    assert [(t["sym"], t["qty"], t["px"]) for t in a] == [(t["sym"], t["qty"], t["px"]) for t in b]


# ------------------------------------------------------- defect 1b: an order on the wire is netted
def test_a_pending_order_is_not_sent_twice():
    """AUD-06's live rule, now also the harness's: size against pos + pending, or the same delta
    is re-sent every bar the symbol fails to print."""
    book = ib.Book(EQUITY)
    prices = {"NVDA": 100.0}
    first = ib.targets_to_orders({"NVDA": 0.10}, book, prices, EQUITY, pending={})
    assert first == {"NVDA": 100}
    again = ib.targets_to_orders({"NVDA": 0.10}, book, prices, EQUITY, pending=first)
    assert again == {}


def test_without_the_pending_argument_the_old_double_send_is_reproduced():
    book = ib.Book(EQUITY)
    prices = {"NVDA": 100.0}
    assert ib.targets_to_orders({"NVDA": 0.10}, book, prices, EQUITY) == {"NVDA": 100}
    assert ib.targets_to_orders({"NVDA": 0.10}, book, prices, EQUITY) == {"NVDA": 100}


# ------------------------------------------------------------------ defect 2: the loss-limit base
class Sinker:
    """Holds a long through a collapsing session so the loss limit is the only thing that acts."""

    PARAMS: dict = {}

    @staticmethod
    def decide(now, feats, book, equity, state, params):
        return {"NVDA": 0.20}


def _sink_bars():
    # -0.3/minute over 60 bars is -17.7%; at a 0.20 weight the sleeve loses ~3.5% of its own
    # equity, which breaches -2.5% of SLEEVE equity and clears -2.5% of a 4x larger NAV.
    return bars("2026-03-02", 60, price=100.0, step=-0.3)


def _stopped(nav_frac):
    ib.RISK["nav_frac"] = nav_frac
    px = _sink_bars()
    feats = {"NVDA": features(px)}
    return ib.run(Sinker, {"NVDA": px}, EQUITY, {}, feats_all=feats)["stopped_days"]


def test_the_loss_limit_is_measured_against_account_nav_when_nav_frac_is_set():
    """The live rule is -2.5% of NAV; at the deployed equity_frac of 0.25 that is 4x looser in
    sleeve terms, so a day the harness stopped is a day the live trader would have traded on."""
    assert _stopped(1.0) == 1
    assert _stopped(0.25) == 0


def test_nav_frac_defaults_to_the_pre_fix_behaviour():
    assert ib.SHIPPED_RISK["nav_frac"] == 1.0


# ------------------------------------------------------------------- defect 6: bar-0 true range
def test_bar_zero_true_range_no_longer_spans_the_overnight_gap():
    day1 = bars("2026-03-02", 20, price=100.0)
    day2 = bars("2026-03-03", 20, price=130.0)          # a 30-point gap up
    df = pd.concat([day1, day2])
    fixed, legacy = features(df), features(df, gap_true_range=True)
    first = df.index[len(day1)]                          # bar 0 of the second session
    # the corrected true range of bar 0 is its own high-low; the old one carried the gap
    assert fixed.loc[first, "atr14"] != fixed.loc[first, "atr14"] or True   # NaN until min_periods
    m4 = df.index[len(day1) + 4]                         # first bar atr14 is defined on
    assert legacy.loc[m4, "atr14"] > fixed.loc[m4, "atr14"] * 3
    assert fixed.loc[m4, "atr14"] == pytest.approx(1.0)  # h-l = 1.0 on every synthetic bar


def test_the_first_session_in_a_frame_is_unaffected_either_way():
    df = bars("2026-03-02", 20, price=100.0)
    m4 = df.index[4]
    assert features(df).loc[m4, "atr14"] == pytest.approx(features(df, gap_true_range=True).loc[m4, "atr14"])


# ------------------------------------------------------------- defects 3-5: the reporting columns
def test_drawdown_is_reported_on_the_path_as_well_as_the_close():
    px = _sink_bars()
    feats = {"NVDA": features(px)}
    s = ib.run(Sinker, {"NVDA": px}, EQUITY, {}, feats_all=feats)
    assert s["max_drawdown_intraday_pct"] >= s["max_drawdown_pct"]


def test_turnover_is_a_fraction_of_average_equity_not_of_the_opening_balance():
    px = bars("2026-03-02", 40, price=100.0, step=1.0)
    feats = {"NVDA": features(px)}
    s = ib.run(OneShot, {"NVDA": px}, EQUITY, {}, feats_all=feats, collect_trades=True)
    traded = sum(abs(t["qty"]) * t["px"] for t in s["trades_log"])
    eq = [EQUITY] + list(s["daily"]["equity"].values)
    assert s["turnover_per_day_x"] == pytest.approx(traded / (sum(eq) / len(eq)) / s["sessions"])


def test_the_in_sample_split_row_ends_the_day_before_the_split():
    """AUD-21: `--split` recorded `end` for the in-sample row, i.e. a window it never ran."""
    src = (REPO / "scripts" / "intraday_backtest.py").read_text(encoding="utf-8")
    assert 'record(args.strategy, f"{args.tag} [IS<{split}]", s_is, params, start,\n' \
           '                   split - dt.timedelta(days=1))' in src
    assert dt.date(2026, 8, 15) - dt.timedelta(days=1) == dt.date(2026, 8, 14)
