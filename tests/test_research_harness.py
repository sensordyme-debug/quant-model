"""The research harness: the code that decides what a result is.

Part 7. `scripts/intraday_backtest.py` produces every `intraday/*` row in the ledger and,
through them, every promotion decision on that sleeve - and it had no tests. The audit found
three inference defects in the ML track alone (AUD-18 overlapping labels, AUD-19 selecting on
the test window, AUD-20 shifting by row on an irregular grid) and one in the harness itself
(AUD-21, "harness biases, all in its own favour"). That is what untested measurement code
produces.

These tests exercise the arithmetic directly on synthetic books and equity curves rather than
on real bars, so they pin the FORMULAS - a Sharpe that silently loses its annualisation, a
drawdown that forgets the opening equity, a cost that is charged once instead of twice - and
do not drift when the data store grows.
"""
from __future__ import annotations

import datetime as dt
import math

import intraday_backtest as ib
import numpy as np
import pandas as pd
import pytest
from intraday_common import COMMISSION_MIN, COMMISSION_PER_SHARE, SLIPPAGE_BPS

D = dt.date
EQ = 1_000_000.0


def daily_rows(pnls, equity0=EQ):
    """Sessions with the equity curve implied by a list of daily P&L."""
    rows, eq = [], equity0
    for i, pnl in enumerate(pnls):
        prev = eq
        eq += pnl
        rows.append({"day": D(2026, 1, 5) + dt.timedelta(days=i), "pnl": pnl,
                     "ret": eq / prev - 1.0, "equity": eq, "trades": 2, "stopped": False,
                     "stop_minute": None})
    return rows


def book_with(trades=0, costs=0.0):
    b = ib.Book(EQ)
    for i in range(trades):
        b.trades.append({"t": pd.Timestamp(2026, 1, 5, 10, i % 50), "sym": "NVDA",
                         "qty": 10, "px": 100.0, "cost": 1.0, "why": ""})
    b.costs = costs
    return b


# ============================================================== metrics: the formulas

def test_drawdown_includes_the_opening_equity_as_the_first_peak():
    """A curve that only ever falls still has a drawdown - the peak is where it started."""
    s = ib.summarize(daily_rows([-10_000, -10_000]), book_with(), EQ, 0.0)
    assert s["max_drawdown_pct"] == pytest.approx(2.0, abs=1e-6)


def test_drawdown_is_measured_from_the_running_peak_not_the_start():
    """Up 100k then down 50k is a 4.55% drawdown from the peak, not a gain."""
    s = ib.summarize(daily_rows([100_000, -50_000]), book_with(), EQ, 0.0)
    assert s["max_drawdown_pct"] == pytest.approx(50_000 / 1_100_000 * 100, abs=1e-6)


def test_a_monotonically_rising_curve_has_zero_drawdown():
    s = ib.summarize(daily_rows([1000, 1000, 1000]), book_with(), EQ, 0.0)
    assert s["max_drawdown_pct"] == pytest.approx(0.0, abs=1e-9)


def test_sharpe_is_annualised_by_root_252():
    rows = daily_rows([1000, -500, 1500, -250, 800])
    s = ib.summarize(rows, book_with(), EQ, 0.0)
    rets = np.array([r["ret"] for r in rows])
    assert s["sharpe"] == pytest.approx(
        rets.mean() / rets.std(ddof=1) * math.sqrt(252), rel=1e-9)


def test_sharpe_is_nan_rather_than_infinite_on_a_constant_curve():
    """Zero variance must not produce a division that reads as a spectacular strategy."""
    s = ib.summarize(daily_rows([0.0, 0.0, 0.0]), book_with(), EQ, 0.0)
    assert math.isnan(s["sharpe"])


def test_a_single_session_does_not_fabricate_a_sharpe():
    s = ib.summarize(daily_rows([1000]), book_with(), EQ, 0.0)
    assert math.isnan(s["sharpe"])


def test_cagr_annualises_on_session_count_not_calendar_days():
    rows = daily_rows([1000] * 10)
    s = ib.summarize(rows, book_with(), EQ, 0.0)
    total = rows[-1]["equity"] / EQ - 1.0
    assert s["cagr_pct"] == pytest.approx(((1 + total) ** (252 / 10) - 1) * 100, rel=1e-9)


def test_a_full_year_of_sessions_leaves_cagr_equal_to_total_return():
    rows = daily_rows([100.0] * 252)
    s = ib.summarize(rows, book_with(), EQ, 0.0)
    assert s["cagr_pct"] == pytest.approx(s["net_profit_pct"], rel=1e-6)


def test_net_profit_is_taken_from_the_final_equity():
    s = ib.summarize(daily_rows([5000, -2000, 1000]), book_with(), EQ, 0.0)
    assert s["net_profit_pct"] == pytest.approx(4000 / EQ * 100, rel=1e-9)


def test_worst_and_best_day_are_the_extremes_not_the_mean():
    s = ib.summarize(daily_rows([500, -9000, 2000]), book_with(), EQ, 0.0)
    assert s["worst_day"] == -9000 and s["best_day"] == 2000


def test_win_day_percentage_counts_strictly_positive_days():
    s = ib.summarize(daily_rows([100, 0, -100, 200]), book_with(), EQ, 0.0)
    assert s["win_days_pct"] == pytest.approx(50.0)


def test_trade_count_is_the_book_not_the_daily_column():
    """`trades` on a daily row is per-session; the headline must be the book's own total."""
    s = ib.summarize(daily_rows([100, 100]), book_with(trades=37), EQ, 0.0)
    assert s["trades"] == 37


def test_costs_per_day_divides_by_sessions():
    s = ib.summarize(daily_rows([100] * 4), book_with(costs=800.0), EQ, 0.0)
    assert s["costs_total"] == 800.0
    assert s["costs_per_day"] == pytest.approx(200.0)


def test_stopped_days_are_counted():
    rows = daily_rows([100, -100, 100])
    rows[1]["stopped"] = True
    assert ib.summarize(rows, book_with(), EQ, 0.0)["stopped_days"] == 1


def test_no_sessions_is_an_error_not_a_zero_result():
    """An empty run must not read as a flat, riskless strategy."""
    assert "error" in ib.summarize([], book_with(), EQ, 0.0)


# ============================================================== transaction costs

def test_a_fill_charges_both_commission_and_slippage():
    b = ib.Book(EQ)
    b.fill(pd.Timestamp(2026, 1, 5, 10, 0), "NVDA", 100, 50.0)
    expected = max(COMMISSION_MIN, 100 * COMMISSION_PER_SHARE) + 100 * 50.0 * SLIPPAGE_BPS / 1e4
    assert b.costs == pytest.approx(expected, rel=1e-9)


def test_cost_is_charged_on_a_sale_as_well_as_a_purchase():
    b = ib.Book(EQ)
    b.fill(pd.Timestamp(2026, 1, 5, 10, 0), "NVDA", -100, 50.0)
    assert b.costs > 0


def test_a_round_trip_costs_more_than_twice_the_buy_because_selling_is_dearer():
    """The sell leg is deliberately more expensive, and a symmetric assumption is wrong.

    SEC fee (20.60e-6 of notional) and TAF (0.000198/share, capped) are charged on SALES
    only. On 100 shares at $50 that is 5,000 * 20.60e-6 + 100 * 0.000198 = $0.1228 on top of
    the buy leg's cost. A backtest that modelled the round trip as 2x the buy would
    understate turnover cost by that much on every close - which for a sleeve doing ~35
    trades a day is the difference between an edge and a rounding error.
    """
    from intraday_common import SEC_FEE_RATE, TAF_PER_SHARE
    b = ib.Book(EQ)
    b.fill(pd.Timestamp(2026, 1, 5, 10, 0), "NVDA", 100, 50.0)
    buy_leg = b.costs
    b.fill(pd.Timestamp(2026, 1, 5, 10, 1), "NVDA", -100, 50.0)
    sell_extra = 100 * 50.0 * SEC_FEE_RATE + 100 * TAF_PER_SHARE
    assert b.costs == pytest.approx(2 * buy_leg + sell_extra, rel=1e-6)
    assert b.costs > 2 * buy_leg


def test_the_sell_only_fees_are_not_charged_on_a_purchase():
    b_buy, b_sell = ib.Book(EQ), ib.Book(EQ)
    b_buy.fill(pd.Timestamp(2026, 1, 5, 10, 0), "NVDA", 100, 50.0)
    b_sell.fill(pd.Timestamp(2026, 1, 5, 10, 0), "NVDA", -100, 50.0)
    assert b_sell.costs > b_buy.costs


def test_a_flat_round_trip_at_the_same_price_loses_exactly_the_costs():
    """The single most important cost assertion: no free lunch on a zero-move round trip."""
    b = ib.Book(EQ)
    b.fill(pd.Timestamp(2026, 1, 5, 10, 0), "NVDA", 100, 50.0)
    b.fill(pd.Timestamp(2026, 1, 5, 10, 1), "NVDA", -100, 50.0)
    assert b.pos == {}
    assert b.value({}) == pytest.approx(EQ - b.costs, rel=1e-9)


def test_a_zero_delta_fill_is_ignored():
    b = ib.Book(EQ)
    b.fill(pd.Timestamp(2026, 1, 5, 10, 0), "NVDA", 0, 50.0)
    assert b.trades == [] and b.costs == 0.0


def test_a_closed_position_leaves_no_residue():
    b = ib.Book(EQ)
    b.fill(pd.Timestamp(2026, 1, 5, 10, 0), "NVDA", 100, 50.0)
    b.fill(pd.Timestamp(2026, 1, 5, 10, 1), "NVDA", -100, 50.0)
    assert "NVDA" not in b.pos


# ============================================================== sizing rules

def test_sizing_floors_to_whole_shares():
    b = ib.Book(EQ)
    orders = ib.targets_to_orders({"NVDA": 0.10}, b, {"NVDA": 333.0}, EQ)
    assert orders["NVDA"] == math.floor(0.10 * EQ / 333.0)
    assert isinstance(orders["NVDA"], int)


def test_the_per_symbol_cap_binds():
    b = ib.Book(EQ)
    big = ib.RISK["per_symbol_hard_cap"] * 5
    orders = ib.targets_to_orders({"NVDA": big}, b, {"NVDA": 100.0}, EQ)
    assert orders["NVDA"] <= math.floor(ib.RISK["per_symbol_hard_cap"] * EQ / 100.0)


def test_the_gross_cap_scales_every_target_down_together():
    b = ib.Book(EQ)
    n = 20
    targets = {f"S{i}": 0.15 for i in range(n)}          # gross 3.0 vs a 1.6 cap
    prices = {f"S{i}": 100.0 for i in range(n)}
    orders = ib.targets_to_orders(targets, b, prices, EQ)
    gross = sum(abs(q) * 100.0 for q in orders.values())
    assert gross <= ib.RISK["gross_hard_cap"] * EQ * 1.01


def test_the_no_trade_band_suppresses_a_small_drift_but_never_a_close():
    b = ib.Book(EQ)
    b.pos["NVDA"] = 1000
    tiny = ib.targets_to_orders({"NVDA": 1000 * 100.0 / EQ + 0.0001}, b,
                                {"NVDA": 100.0}, EQ)
    assert "NVDA" not in tiny                     # below min_change
    close = ib.targets_to_orders({}, b, {"NVDA": 100.0}, EQ)
    assert close["NVDA"] == -1000                 # a close is always allowed through


def test_a_missing_or_non_positive_price_is_skipped():
    b = ib.Book(EQ)
    assert ib.targets_to_orders({"NVDA": 0.1}, b, {}, EQ) == {}
    assert ib.targets_to_orders({"NVDA": 0.1}, b, {"NVDA": 0.0}, EQ) == {}
    assert ib.targets_to_orders({"NVDA": 0.1}, b, {"NVDA": -5.0}, EQ) == {}


def test_the_harness_and_the_live_trader_apply_the_same_caps():
    """AUD's 'trader/common drift' class: the two sizers must read the same constants."""
    import intraday_trader as it
    from intraday_common import GROSS_HARD_CAP, MIN_CHANGE, PER_SYMBOL_HARD_CAP
    assert ib.SHIPPED_RISK["per_symbol_hard_cap"] == PER_SYMBOL_HARD_CAP
    assert ib.SHIPPED_RISK["gross_hard_cap"] == GROSS_HARD_CAP
    assert ib.SHIPPED_RISK["min_change"] == MIN_CHANGE
    assert it.PER_SYMBOL_HARD_CAP == PER_SYMBOL_HARD_CAP


# ============================================================== OOS boundary

def test_the_in_sample_and_out_of_sample_windows_do_not_overlap():
    """`--split X` runs IS to X-1day inclusive and OOS from X inclusive. A session on X must
    appear in exactly one of them - an overlap inflates OOS with data the parameters saw."""
    split = D(2026, 8, 17)
    is_end = split - dt.timedelta(days=1)
    oos_start = split
    assert is_end < oos_start
    for day in (D(2026, 8, 14), D(2026, 8, 16), split, D(2026, 8, 18)):
        in_is = day <= is_end
        in_oos = day >= oos_start
        assert in_is != in_oos, f"{day} is in both or neither"


def test_no_session_falls_between_the_two_windows():
    """The other failure: a gap silently drops sessions from both halves."""
    split = D(2026, 8, 17)
    is_end, oos_start = split - dt.timedelta(days=1), split
    assert (oos_start - is_end).days == 1          # adjacent, no hole


@pytest.mark.parametrize("split", [D(2026, 8, 17), D(2026, 1, 2), D(2026, 12, 31)])
def test_the_boundary_holds_for_any_split_date(split):
    is_end, oos_start = split - dt.timedelta(days=1), split
    assert is_end < oos_start and (oos_start - is_end).days == 1


# ============================================================== registration

def test_a_recorded_row_carries_the_fields_the_gate_reads(tmp_path, monkeypatch):
    ledger = tmp_path / "experiments.jsonl"
    monkeypatch.setattr(ib, "EXPERIMENTS", ledger)
    s = ib.summarize(daily_rows([1000] * 40), book_with(trades=80, costs=400.0), EQ, 1.0)
    ib.record("orb", "unit test", s, {"k": 1}, D(2026, 1, 5), D(2026, 3, 1))
    import json
    row = json.loads(ledger.read_text(encoding="utf-8").strip())
    assert row["algorithm"] == "intraday/orb"
    for k in ("Total Orders", "Compounding Annual Return", "Sharpe Ratio", "Drawdown"):
        assert k in row["stats"], k
    assert row["env_key"].startswith("py")          # provenance is stamped
    assert "reproducible" in row


def test_an_errored_run_is_never_recorded(tmp_path, monkeypatch):
    """A failed run must not leave a row that a later comparison could pick up."""
    ledger = tmp_path / "experiments.jsonl"
    monkeypatch.setattr(ib, "EXPERIMENTS", ledger)
    ib.record("orb", "broken", {"error": "no sessions"}, {}, D(2026, 1, 5), D(2026, 3, 1))
    assert not ledger.exists()


def test_non_shipped_risk_overrides_are_flagged_on_the_row(tmp_path, monkeypatch):
    """A run under relaxed limits must be labelled, or it is comparable to nothing."""
    ledger = tmp_path / "experiments.jsonl"
    monkeypatch.setattr(ib, "EXPERIMENTS", ledger)
    monkeypatch.setitem(ib.RISK, "gross_hard_cap", 99.0)
    s = ib.summarize(daily_rows([100] * 40), book_with(trades=40), EQ, 1.0)
    ib.record("orb", "relaxed", s, {}, D(2026, 1, 5), D(2026, 3, 1))
    import json
    row = json.loads(ledger.read_text(encoding="utf-8").strip())
    assert row["risk"]["gross_hard_cap"] == 99.0


# ============================================ AUD-07: the harness must agree with the runner

def test_the_harness_flatten_minute_matches_the_live_trader_on_a_regular_day():
    import intraday_trader as it
    day = D(2026, 9, 11)
    assert ib.flatten_minute_for(day) == it.flatten_minute_for(day) == 368


def test_the_harness_flatten_minute_matches_the_live_trader_on_an_early_close():
    """The whole point of AUD-07: on 2026-11-27 the session is 210 minutes, so a harness
    still using 368 would model a flatten that the live path cannot perform - and the two
    would disagree on exactly the days the live path used to break."""
    import intraday_trader as it
    day = D(2026, 11, 27)
    assert ib.flatten_minute_for(day) == it.flatten_minute_for(day) == 188


def test_a_deliberate_risk_override_is_not_silently_moved_by_the_calendar(monkeypatch):
    """An override is a stated experiment. The calendar may correct the SHIPPED value only."""
    monkeypatch.setitem(ib.RISK, "flatten_minute", 300)
    assert ib.flatten_minute_for(D(2026, 11, 27)) == 300
    assert ib.flatten_minute_for(D(2026, 9, 11)) == 300


def test_the_shipped_flatten_minute_is_unchanged_on_a_normal_session():
    """Behaviour on a regular day must be byte-identical to before the change."""
    assert ib.flatten_minute_for(D(2026, 9, 11)) == ib.SHIPPED_RISK["flatten_minute"]
