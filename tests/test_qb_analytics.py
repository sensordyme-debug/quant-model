"""Tests for the trade analytics module.

Four properties carry the weight.

KNOWN ANSWERS. A hand-built list of ten trades whose expectancy, profit factor, payoff
ratio, median, drawdowns and streaks can be checked on paper, so a regression in any of them
is a wrong number rather than a changed one. Sharpe, Sortino and Calmar are re-derived in the
test from the annualisation the report itself states.

REFUSALS ARE REFUSALS. MAE/MFE without a path, R without a stop, Sharpe under thirty trades,
the daily clock without a session count, the profit factor with no losers: each must come
back as `Unavailable` with the documented reason, never as NaN, inf, None or zero.

NO BARE NaN, ANYWHERE. A battery of degenerate trade lists - empty, one trade, all winners,
all losers, all flat, zero variance, zero span - is walked recursively and every float must be
finite. The walk is written here independently of the module's own serialiser, so the test
does not trust the code it is testing.

AND THE DICT ROUND-TRIPS. `report()` through `json.dumps` / `json.loads` must come back equal,
with every refusal spelled `{"unavailable": reason}`.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import math
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from quant_brain.research import analytics as an
from quant_brain.research import robustness as rb
from quant_brain.research.analytics import Direction, Trade, Unavailable

ET = ZoneInfo("America/New_York")
#: Monday 5 January 2026, 10:00 ET.
T0 = dt.datetime(2026, 1, 5, 10, 0, tzinfo=ET)


# ======================================================================================
# FIXTURES
# ======================================================================================

def _trade(pnl: float, i: int = 0, *, direction: Direction = Direction.LONG,
           size: float = 1.0, hold_minutes: int = 60, **kw) -> Trade:
    """A trade on day `i` whose GROSS P&L is exactly `pnl`, built from prices."""
    entry = T0 + dt.timedelta(days=i)
    return Trade(entry_time=entry, exit_time=entry + dt.timedelta(minutes=hold_minutes),
                 entry_price=100.0, exit_price=100.0 + direction.sign * pnl / size,
                 direction=direction, size=size, **kw)


#: Ten trades: expectancy 60, profit factor 3, win rate 0.6, payoff 2, median 75.
TEN = [100.0, 200.0, -50.0, 150.0, -100.0, 50.0, -50.0, 300.0, -100.0, 100.0]


def _ten() -> list[Trade]:
    return [_trade(p, i) for i, p in enumerate(TEN)]


def _num(v: object) -> float:
    """A real number out of a Metric, failing loudly on a refusal."""
    assert isinstance(v, int | float) and not isinstance(v, bool), f"not a number: {v!r}"
    return float(v)


def _walk(obj: object, path: str = "$") -> None:
    """Independent no-NaN walker over a JSON-shaped tree."""
    if isinstance(obj, float):
        assert math.isfinite(obj), f"{path} is {obj!r}"
    elif isinstance(obj, dict):
        for k, v in obj.items():
            assert isinstance(k, str), f"{path} has a non-string key {k!r}"
            _walk(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _walk(v, f"{path}[{i}]")
    else:
        assert obj is None or isinstance(obj, str | int | bool), f"{path} is {type(obj)}"


# ======================================================================================
# THE SENTINEL
# ======================================================================================

def test_unavailable_has_no_arithmetic_and_needs_a_reason():
    u = Unavailable("because")
    with pytest.raises(TypeError):
        _ = u * 2  # type: ignore[operator]
    with pytest.raises(TypeError):
        _ = u + 1.0  # type: ignore[operator]
    with pytest.raises(ValueError):
        Unavailable("")
    assert u.to_json() == {"unavailable": "because"}
    assert Unavailable.from_json({"unavailable": "because"}) == u
    assert Unavailable.from_json({"unavailable": "x", "extra": 1}) is None
    assert Unavailable.from_json(1.0) is None
    assert not an.available(u) and an.available(0.0)


# ======================================================================================
# PER-TRADE
# ======================================================================================

def test_pnl_is_derived_from_prices_and_costs_follow_fill_convention():
    t = _trade(100.0, size=2.0, commission=4.0, slippage=-6.0)      # sign of slippage ignored
    assert t.gross_pnl == pytest.approx(100.0)
    assert t.cost == pytest.approx(10.0)
    assert t.net_pnl == pytest.approx(90.0)
    s = _trade(-40.0, direction=Direction.SHORT, size=4.0, multiplier=5.0)
    # exit = 100 - (-40)/4 = 110 on a short: (110-100) * -1 * 4 * 5 = -200
    assert s.gross_pnl == pytest.approx(-200.0)
    assert s.holding_seconds == 3600.0
    assert s.day_of_week == "Mon"


def test_mae_mfe_known_answer_with_a_path():
    long = Trade(entry_time=T0, exit_time=T0 + dt.timedelta(minutes=5), entry_price=100.0,
                 exit_price=102.0, direction=Direction.LONG, size=2.0, path=(99.0, 103.0, 101.0))
    assert _num(long.mae) == pytest.approx(2.0)      # 99 on 2 lots
    assert _num(long.mfe) == pytest.approx(6.0)      # 103 on 2 lots
    short = Trade(entry_time=T0, exit_time=T0 + dt.timedelta(minutes=5), entry_price=100.0,
                  exit_price=98.0, direction=Direction.SHORT, size=1.0, path=(99.0, 103.0))
    assert _num(short.mae) == pytest.approx(3.0)
    assert _num(short.mfe) == pytest.approx(2.0)
    # Costs are not path-dependent: MAE/MFE are gross.
    costly = Trade(entry_time=T0, exit_time=T0 + dt.timedelta(minutes=5), entry_price=100.0,
                   exit_price=102.0, direction=Direction.LONG, size=2.0, path=(99.0,),
                   commission=50.0)
    assert _num(costly.mae) == pytest.approx(2.0)
    assert costly.net_pnl == pytest.approx(-46.0)


def test_mae_mfe_unavailable_without_a_path_even_when_prices_would_tempt_an_estimate():
    t = _trade(-80.0)                                  # a loser: the exit IS adverse
    assert t.mae == Unavailable(an.NO_PATH)
    assert t.mfe == Unavailable(an.NO_PATH)
    assert t.excursions == Unavailable("no intraday path recorded")
    rep = an.aggregate([t, _trade(50.0, 1)])
    assert isinstance(rep.mae, Unavailable) and an.NO_PATH in rep.mae.reason
    assert isinstance(rep.mfe, Unavailable)
    assert rep.path_coverage == 0.0


def test_r_multiple_needs_a_recorded_stop():
    with_stop = _trade(20.0, size=2.0, stop_distance=5.0)      # risk = 5 * 2 = 10
    assert _num(with_stop.initial_risk) == pytest.approx(10.0)
    assert _num(with_stop.r_multiple) == pytest.approx(2.0)
    without = _trade(20.0)
    assert without.r_multiple == Unavailable(an.NO_STOP)
    assert without.initial_risk == Unavailable(an.NO_STOP)
    with pytest.raises(ValueError):
        _trade(20.0, stop_distance=0.0)
    with pytest.raises(ValueError):
        _trade(20.0, stop_distance=-1.0)


def test_expectancy_r_refuses_partial_stop_coverage_but_distribution_covers_the_subset():
    trades = [_trade(20.0, 0, stop_distance=10.0), _trade(-10.0, 1, stop_distance=10.0),
              _trade(30.0, 2)]
    rep = an.aggregate(trades)
    assert rep.stop_coverage == pytest.approx(2 / 3)
    assert isinstance(rep.expectancy_r, Unavailable)
    assert "1 of 3 trades" in rep.expectancy_r.reason
    assert isinstance(rep.r_multiple, an.Distribution) and rep.r_multiple.n == 2
    assert rep.r_multiple.mean == pytest.approx(0.5)
    full = an.aggregate(trades[:2])
    assert _num(full.expectancy_r) == pytest.approx(0.5)


def test_trade_record_validation():
    naive = dt.datetime(2026, 1, 5, 10, 0)
    with pytest.raises(ValueError, match="timezone-naive"):
        Trade(entry_time=naive, exit_time=naive, entry_price=1.0, exit_price=1.0,
              direction=Direction.LONG, size=1.0)
    with pytest.raises(ValueError, match="precedes"):
        Trade(entry_time=T0, exit_time=T0 - dt.timedelta(seconds=1), entry_price=1.0,
              exit_price=1.0, direction=Direction.LONG, size=1.0)
    with pytest.raises(ValueError, match="size"):
        Trade(entry_time=T0, exit_time=T0, entry_price=1.0, exit_price=1.0,
              direction=Direction.LONG, size=0.0)
    with pytest.raises(ValueError, match="multiplier"):
        _trade(1.0, multiplier=0.0)
    with pytest.raises(ValueError, match="non-finite"):
        _trade(float("nan"))
    with pytest.raises(ValueError, match="path"):
        _trade(1.0, path=(1.0, float("inf")))
    # A string direction is coerced, as the JSON side of the world will hand one over.
    t = Trade(entry_time=T0, exit_time=T0, entry_price=1.0, exit_price=1.0,
              direction="short", size=1.0)  # type: ignore[arg-type]
    assert t.direction is Direction.SHORT
    assert Direction.of(-3) is Direction.SHORT and Direction.of(2) is Direction.LONG
    with pytest.raises(ValueError):
        Direction.of(0)


def test_session_of_uses_the_fixed_clock():
    assert an.session_of(dt.datetime(2026, 1, 5, 9, 45, tzinfo=ET)) == "open"
    assert an.session_of(dt.datetime(2026, 1, 5, 12, 0, tzinfo=ET)) == "midday"
    assert an.session_of(dt.datetime(2026, 1, 5, 15, 30, tzinfo=ET)) == "close"
    assert an.session_of(dt.datetime(2026, 1, 5, 18, 0, tzinfo=ET)) == "other"
    # A UTC stamp is converted, not read as local.
    assert an.session_of(dt.datetime(2026, 1, 5, 14, 45, tzinfo=dt.UTC)) == "open"


def test_trade_records_are_json_ready():
    rows = an.trade_records([_trade(10.0, stop_distance=2.0), _trade(-5.0, 1, path=(99.0,))])
    text = json.dumps(rows, allow_nan=False)
    back = json.loads(text)
    assert back == rows
    assert back[0]["mae"] == {"unavailable": an.NO_PATH}
    assert back[0]["r_multiple"] == 5.0
    assert back[1]["r_multiple"] == {"unavailable": an.NO_STOP}
    # Exit 95 with a mark at 99: the exit itself is the adverse extreme, so MAE is 5, MFE 0.
    assert back[1]["mae"] == 5.0 and back[1]["mfe"] == 0.0
    assert back[0]["entry_time"].startswith("2026-01-05T10:00:00")
    _walk(back)


# ======================================================================================
# AGGREGATE - KNOWN ANSWERS
# ======================================================================================

def test_ten_trade_known_answers():
    rep = an.aggregate(_ten())
    assert (rep.n, rep.n_winners, rep.n_losers, rep.n_flat) == (10, 6, 4, 0)
    assert _num(rep.win_rate) == pytest.approx(0.6)
    assert _num(rep.loss_rate) == pytest.approx(0.4)
    assert _num(rep.expectancy) == pytest.approx(60.0)
    assert _num(rep.median_trade) == pytest.approx(75.0)
    assert _num(rep.average_winner) == pytest.approx(150.0)
    assert _num(rep.average_loser) == pytest.approx(-75.0)
    assert _num(rep.largest_winner) == 300.0 and _num(rep.largest_loser) == -100.0
    assert rep.gross_profit == pytest.approx(900.0)
    assert rep.gross_loss == pytest.approx(300.0)
    assert rep.total_net == pytest.approx(600.0)
    assert rep.total_gross == pytest.approx(600.0) and rep.total_costs == 0.0
    assert _num(rep.profit_factor) == pytest.approx(3.0)
    assert _num(rep.payoff_ratio) == pytest.approx(2.0)
    assert _num(rep.breakeven_win_rate) == pytest.approx(1.0 / 3.0)
    assert rep.longest_win_streak == 2 and rep.longest_loss_streak == 1
    # Equity 100,300,250,400,300,350,300,600,500,600: episodes of depth 50, 100, 100.
    assert _num(rep.max_drawdown) == pytest.approx(100.0)
    assert rep.n_drawdowns == 3
    assert _num(rep.average_drawdown) == pytest.approx(250.0 / 3.0)
    # The deepest (first on ties) troughs at trade 4 and regains the peak at trade 7.
    assert _num(rep.recovery_trades) == 3.0
    assert _num(rep.recovery_seconds) == pytest.approx(3 * 86400.0)
    assert _num(rep.longest_underwater_trades) == 3.0
    assert _num(rep.underwater_fraction) == pytest.approx(0.5)
    prof = rb.drawdown_profile(TEN)
    assert _num(rep.max_drawdown) == prof["max_drawdown"]
    assert rep.longest_loss_streak == prof["longest_losing_streak"]
    # Ten trades: below the ratio minimum, and the 5% tail needs twenty.
    assert isinstance(rep.sharpe, Unavailable) and "30-trade minimum" in rep.sharpe.reason
    assert isinstance(rep.sortino, Unavailable) and isinstance(rep.calmar, Unavailable)
    assert isinstance(rep.cvar, Unavailable) and rep.cvar_trades == 0
    assert _num(rep.volatility) == pytest.approx(float(np.std(TEN, ddof=1)))
    assert isinstance(rep.holding_time, an.Distribution)
    assert rep.holding_time.median == 3600.0 and rep.holding_time.n == 10
    assert _num(rep.expectancy_t) == pytest.approx(rb.stats.tstat_hac(TEN).t)


def test_skew_and_kurtosis_match_the_bias_corrected_sample_estimators():
    x = [3.0, -1.0, 4.0, 1.0, -5.0, 9.0, 2.0, -6.0, 5.0, 3.0, -5.0]
    rep = an.aggregate([_trade(p, i) for i, p in enumerate(x)])
    assert _num(rep.skew) == pytest.approx(pd.Series(x).skew())
    assert _num(rep.kurtosis) == pytest.approx(pd.Series(x).kurt())
    symmetric = an.aggregate([_trade(p, i) for i, p in enumerate([-2.0, -1.0, 0.0, 1.0, 2.0])])
    assert _num(symmetric.skew) == pytest.approx(0.0, abs=1e-12)


def test_cvar_is_the_mean_of_the_worst_tail_and_states_how_thin_it_is():
    pnls = [float(v) for v in range(-20, 20)]                       # 40 trades, -20..19
    rep = an.aggregate([_trade(p, i) for i, p in enumerate(pnls)], cvar_quantile=0.05)
    assert rep.cvar_trades == 2                                     # ceil(0.05 * 40)
    assert _num(rep.cvar) == pytest.approx(-19.5)
    tenth = an.aggregate([_trade(p, i) for i, p in enumerate(pnls)], cvar_quantile=0.10)
    assert tenth.cvar_trades == 4 and _num(tenth.cvar) == pytest.approx(-18.5)
    thin = an.aggregate([_trade(p, i) for i, p in enumerate(pnls[:19])], cvar_quantile=0.05)
    assert isinstance(thin.cvar, Unavailable) and "at least 20" in thin.cvar.reason


# ======================================================================================
# ANNUALISED RATIOS - REFUSED UNDER THIRTY, RE-DERIVED AT THIRTY
# ======================================================================================

def _thirty(n: int = 30) -> list[Trade]:
    return [_trade(100.0 if i % 3 else -80.0, i) for i in range(n)]


def test_sharpe_unavailable_under_thirty_trades():
    rep = an.aggregate(_thirty(29))
    for name in ("sharpe", "sortino", "calmar", "sharpe_daily", "sortino_daily"):
        v = getattr(rep, name)
        assert isinstance(v, Unavailable), name
        assert "29 trade(s) is below the 30-trade minimum" in v.reason, name
    loose = an.aggregate(_thirty(29), min_trades_for_ratios=10)
    assert isinstance(loose.sharpe, float)


def test_trade_clock_ratios_match_the_stated_annualisation():
    trades = _thirty()
    rep = an.aggregate(trades)
    x = np.array([t.net_pnl for t in trades])
    span = (max(t.exit_time for t in trades) - min(t.entry_time for t in trades))
    span_days = span.total_seconds() / 86400.0
    tpy = 30 / (span_days / 365.25)
    assert _num(rep.annualisation.span_days) == pytest.approx(span_days)
    assert _num(rep.annualisation.trades_per_year) == pytest.approx(tpy)
    assert "trades_per_year" in rep.annualisation.trade_clock
    assert _num(rep.sharpe) == pytest.approx(x.mean() / x.std(ddof=1) * math.sqrt(tpy))
    downside = math.sqrt(np.mean(np.minimum(x, 0.0) ** 2))
    assert _num(rep.sortino) == pytest.approx(x.mean() / downside * math.sqrt(tpy))
    annual = x.sum() * 365.25 / span_days
    assert _num(rep.calmar) == pytest.approx(annual / _num(rep.max_drawdown))
    # Daily clock is refused without the session count, and derived with it.
    assert rep.sharpe_daily == Unavailable(an.NO_TRADING_DAYS)
    assert rep.sortino_daily == Unavailable(an.NO_TRADING_DAYS)
    same = an.aggregate(trades, trading_days=30)                    # one trade per session
    assert _num(same.sharpe_daily) == pytest.approx(x.mean() / x.std(ddof=1) * math.sqrt(252))
    padded = an.aggregate(trades, trading_days=60)                  # thirty flat sessions
    d = np.concatenate([x, np.zeros(30)])
    assert _num(padded.sharpe_daily) == pytest.approx(d.mean() / d.std(ddof=1) * math.sqrt(252))
    dd = math.sqrt(np.mean(np.minimum(d, 0.0) ** 2))
    assert _num(padded.sortino_daily) == pytest.approx(d.mean() / dd * math.sqrt(252))
    with pytest.raises(ValueError, match="fewer than the 30 distinct exit dates"):
        an.aggregate(trades, trading_days=29)


def test_ratios_refuse_degenerate_denominators_instead_of_returning_inf():
    winners = an.aggregate([_trade(10.0, i) for i in range(30)])
    assert isinstance(winners.profit_factor, Unavailable)
    assert isinstance(winners.payoff_ratio, Unavailable)
    assert isinstance(winners.breakeven_win_rate, Unavailable)
    assert isinstance(winners.sortino, Unavailable) and "downside" in winners.sortino.reason
    assert isinstance(winners.calmar, Unavailable) and "zero drawdown" in winners.calmar.reason
    assert _num(winners.max_drawdown) == 0.0 and winners.n_drawdowns == 0
    assert isinstance(winners.average_drawdown, Unavailable)
    assert isinstance(winners.recovery_trades, Unavailable)
    assert isinstance(winners.sharpe, Unavailable) and "zero variance" in winners.sharpe.reason
    losers = an.aggregate([_trade(-10.0, i) for i in range(30)])
    assert isinstance(losers.average_winner, Unavailable)
    assert isinstance(losers.recovery_trades, Unavailable)
    assert "had not recovered" in losers.recovery_trades.reason
    assert losers.by_direction["long"].share_of_net == Unavailable(
        "whole-sample net is not positive; a share against it is not a share")
    instant = an.aggregate([_trade(float(i % 5) - 2.0, 0, hold_minutes=0) for i in range(30)])
    assert isinstance(instant.sharpe, Unavailable) and "spans no time" in instant.sharpe.reason


# ======================================================================================
# SPLITS
# ======================================================================================

def test_thin_regime_buckets_are_marked_unreliable_not_dropped():
    trades = [_trade(10.0 if i % 2 else -4.0, i, regime="calm") for i in range(25)]
    trades += [_trade(50.0, 25 + i, regime="storm") for i in range(3)]
    trades += [_trade(1.0, 40)]                                     # no label at all
    rep = an.aggregate(trades, min_bucket_trades=20)
    assert set(rep.by_regime) == {"calm", "storm", an.UNLABELLED}
    calm, storm, none = rep.by_regime["calm"], rep.by_regime["storm"], rep.by_regime["unlabelled"]
    assert calm.reliable and calm.note == ""
    assert not storm.reliable and storm.note == "UNRELIABLE: 3 trade(s), below the 20-trade minimum"
    assert not none.reliable
    assert storm.n == 3 and storm.total_net == 150.0 and storm.win_rate == 1.0
    assert isinstance(storm.profit_factor, Unavailable)
    assert sum(b.share_of_trades for b in rep.by_regime.values()) == pytest.approx(1.0)
    assert sum(b.total_net for b in rep.by_regime.values()) == pytest.approx(rep.total_net)
    assert sum(_num(b.share_of_net) for b in rep.by_regime.values()) == pytest.approx(1.0)
    # The same buckets read as solid once the minimum is lowered: the flag is the judgement.
    assert an.aggregate(trades, min_bucket_trades=3).by_regime["storm"].reliable


def test_direction_session_and_weekday_splits():
    trades = [_trade(10.0, 0, session="open"), _trade(-5.0, 1, direction=Direction.SHORT,
                                                        session="close"),
              _trade(7.0, 2, session="open")]
    rep = an.aggregate(trades, min_bucket_trades=1)
    assert list(rep.by_direction) == ["long", "short"]
    assert rep.by_direction["short"].n == 1 and rep.by_direction["short"].total_net == -5.0
    assert rep.by_session["open"].n == 2 and rep.by_session["close"].expectancy == -5.0
    assert list(rep.by_weekday) == ["Mon", "Tue", "Wed"]
    only_long = an.aggregate(trades[:1], min_bucket_trades=1)
    assert list(only_long.by_direction) == ["long"]


# ======================================================================================
# INVARIANTS: NO BARE NaN, DETERMINISM, JSON ROUND TRIP, DOCS
# ======================================================================================

def _battery() -> dict[str, tuple[list[Trade], dict[str, object]]]:
    return {
        "empty": ([], {}),
        "one": ([_trade(5.0)], {}),
        "one_flat": ([_trade(0.0)], {}),
        "two_identical": ([_trade(5.0, 0), _trade(5.0, 1)], {}),
        "all_winners": ([_trade(10.0, i) for i in range(35)], {}),
        "all_losers": ([_trade(-10.0, i) for i in range(35)], {}),
        "all_flat": ([_trade(0.0, i) for i in range(35)], {}),
        "zero_span": ([_trade(float(i % 7) - 3.0, 0, hold_minutes=0) for i in range(35)], {}),
        "mixed_no_paths": (_ten(), {}),
        "mixed_with_paths_and_stops": (
            [_trade(p, i, path=(99.0, 101.0), stop_distance=3.0) for i, p in enumerate(TEN)],
            {}),
        "partial_coverage": (
            [_trade(p, i, path=(99.5,) if i % 2 else (), stop_distance=3.0 if i % 3 else None)
             for i, p in enumerate(TEN)], {}),
        "thirty_with_days": (_thirty(), {"trading_days": 45}),
        "thirty_one_session": ([_trade(float(i % 4) - 1.5, 0) for i in range(30)],
                               {"trading_days": 1}),
        "labelled": ([_trade(p, i, regime="a" if i % 2 else None, session="open")
                      for i, p in enumerate(TEN)], {"min_bucket_trades": 3}),
    }


@pytest.mark.parametrize("name", sorted(_battery()))
def test_no_aggregate_field_is_ever_a_bare_nan(name: str):
    trades, kw = _battery()[name]
    rep = an.report(trades, **kw)  # type: ignore[arg-type]
    _walk(rep)
    # json's own guard is a second, independent witness.
    json.dumps(rep, allow_nan=False)
    # And the typed object carries no NaN either, before serialisation.
    for r in an.readings(an.aggregate(trades, **kw)):  # type: ignore[arg-type]
        if isinstance(r.value, float):
            assert math.isfinite(r.value), r.metric


def test_empty_list_is_all_refusals_and_zero_counts():
    rep = an.aggregate([])
    assert rep.n == 0 and rep.total_net == 0.0 and rep.n_drawdowns == 0
    for name in ("win_rate", "expectancy", "median_trade", "profit_factor", "max_drawdown",
                 "sharpe", "volatility", "skew", "cvar", "holding_time", "mae",
                 "path_coverage", "expectancy_r"):
        v = getattr(rep, name)
        assert isinstance(v, Unavailable), name
    assert rep.win_rate == Unavailable(an.NO_TRADES)
    assert rep.by_direction == {} and rep.by_regime == {}
    assert rep.annualisation.trades_per_year == Unavailable(an.NO_TRADES)


def test_report_round_trips_through_json_with_unavailable_spelled_out():
    trades = [_trade(p, i, path=(99.0, 101.0) if i % 2 else (), regime="r")
              for i, p in enumerate(TEN)]
    rep = an.report(trades)
    text = json.dumps(rep, allow_nan=False, sort_keys=True)
    back = json.loads(text)
    assert back == rep
    assert back["sharpe"] == {"unavailable": "10 trade(s) is below the 30-trade minimum for an "
                                             "annualised ratio"}
    assert back["expectancy"] == 60.0
    assert back["path_coverage"] == 0.5
    assert back["mae"]["n"] == 5
    assert back["by_regime"]["r"]["note"].startswith("UNRELIABLE")
    assert back["annualisation"]["trading_days"] is None
    assert back["config"]["min_trades_for_ratios"] == 30
    assert Unavailable.from_json(back["sharpe_daily"]) == Unavailable(
        "10 trade(s) is below the 30-trade minimum for an annualised ratio")
    # to_jsonable refuses a NaN outright rather than emitting one.
    with pytest.raises(ValueError, match="non-finite"):
        an.to_jsonable({"x": float("nan")})
    with pytest.raises(ValueError, match="non-finite"):
        an.to_jsonable(float("inf"))


def test_deterministic_and_order_independent():
    trades = _thirty()
    a = an.report(trades, trading_days=40)
    b = an.report(list(reversed(trades)), trading_days=40)
    c = an.report(trades, trading_days=40)
    assert a == b == c
    assert an.aggregate(trades) == an.aggregate(trades)


def test_every_reported_metric_is_documented_with_a_basis():
    assert an.undocumented() == set()
    rep = an.aggregate(_ten())
    names = {r.metric for r in an.readings(rep)}
    assert names == {f.name for f in dataclasses.fields(an.TradeReport)} - {"cvar_quantile",
                                                                    "annualisation", "config"}
    for doc in an.METRIC_DOCS.values():
        assert doc.basis in ("arithmetic", "judgement")
        assert doc.interpretation
    judged = set(an.judgements())
    assert {"sharpe", "sortino", "calmar", "profit_factor", "by_regime", "bucket.reliable",
            "n"} <= judged
    assert {"expectancy", "win_rate", "max_drawdown", "mae", "cvar", "skew"}.isdisjoint(judged)
    # The MetricDoc in use is robustness's, not a look-alike.
    assert all(isinstance(d, rb.MetricDoc) for d in an.METRIC_DOCS.values())


def test_config_validation():
    with pytest.raises(ValueError, match="cvar_quantile"):
        an.aggregate(_ten(), cvar_quantile=0.0)
    with pytest.raises(ValueError, match="cvar_quantile"):
        an.aggregate(_ten(), cvar_quantile=1.0)
    with pytest.raises(ValueError, match="min_bucket_trades"):
        an.aggregate(_ten(), min_bucket_trades=0)
    with pytest.raises(ValueError, match="min_trades_for_ratios"):
        an.aggregate(_ten(), min_trades_for_ratios=1)
    with pytest.raises(ValueError, match="trading_days"):
        an.aggregate(_ten(), trading_days=0)
