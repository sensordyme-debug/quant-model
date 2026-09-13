"""Tests for the futures execution simulator.

The two things worth defending: the modelled cost must reconcile with the cost this
repository has actually measured, and a flatten must never be refusable. Everything else is
arithmetic that a mutation test would catch.
"""
from __future__ import annotations

import datetime as dt

import pytest

from quant_brain.core.execution import OrderIntent, OrderType, Side
from quant_brain.markets.futures_cme import execution_sim as ex
from quant_brain.markets.futures_cme import instruments as inst

#: F-2a measured the realised ES round-trip cost at this, in basis points of notional.
MEASURED_ES_BPS = 0.488


def _sim(symbol="ES", **kw):
    return ex.ExecutionSimulator(cost=ex.CostModel.for_contract(symbol), symbol=symbol, **kw)


def _q(bid=5799.75, ask=5800.00, **kw):
    return ex.Quote(bid=bid, ask=ask, **kw)


def _buy(qty=1.0, **kw):
    return OrderIntent(symbol="ES", side=Side.BUY, quantity=qty, **kw)


def _fill(result):
    """The fill, insisting there is one. Narrows the Optional and names the refusal."""
    assert result.fill is not None, f"expected a fill, got: {result}"
    return result.fill


# ======================================================================================
# THE COST RECONCILES WITH WHAT WAS MEASURED
# ======================================================================================

def test_the_modelled_es_round_turn_matches_the_measured_cost_and_is_conservative():
    """The single most important number in this module.

    A cost model that disagrees with the repository's own measurement is not a model, it is a
    guess. F-2a measured 0.488 bps on ES; this charges one tick of spread plus $4 round-turn
    commission, which comes to 0.569 bps at 5800 - 17% above measured, i.e. conservative. If
    this ever drifts below the measured figure the model has become optimistic and every
    result downstream of it is flattered.
    """
    sim = _sim("ES")
    bps = sim.cost_per_dollar_exposure(5_800.0) * 10_000
    assert bps == pytest.approx(0.569, abs=0.01)
    assert bps > MEASURED_ES_BPS, "the model must not be cheaper than the measured cost"
    assert bps < MEASURED_ES_BPS * 1.5, f"{bps:.3f} bps is implausibly far above measured"


def test_the_round_turn_is_commission_plus_one_tick():
    sim = _sim("ES")
    assert sim.round_turn_cost(1.0) == pytest.approx(2 * 2.0 + 12.50)
    assert sim.round_turn_cost(3.0) == pytest.approx(3 * (2 * 2.0 + 12.50))


def test_micros_cost_more_per_dollar_of_exposure_than_their_parent():
    """The granularity premium, which is the whole mini-versus-micro decision."""
    out = ex.compare_granularity("ES", 5_800.0)
    assert out["MES/ES"] == pytest.approx(1.364, abs=0.01)
    assert out["MES"] > out["ES"]


@pytest.mark.parametrize("parent", ["ES", "NQ", "CL", "GC"])
def test_every_micro_is_more_expensive_per_dollar_than_its_parent(parent):
    out = ex.compare_granularity(parent, 100.0)
    for micro in inst.micros_of(parent):
        assert out[f"{micro}/{parent}"] > 1.0, (
            f"{micro} is not more expensive than {parent} per dollar; check the metadata")


def test_a_contract_without_a_recorded_commission_is_refused():
    """A futures cost model with no commission is wrong, not conservative."""
    import dataclasses
    real = inst.get("ES")
    patched = dataclasses.replace(real, commission_round_turn=0.0)
    original = inst.get
    inst.get = lambda s: patched if s == "ES" else original(s)   # type: ignore[assignment]
    try:
        with pytest.raises(ValueError) as e:
            ex.CostModel.for_contract("ES")
        assert "commission" in str(e.value)
        assert "broker statement" in str(e.value)
    finally:
        inst.get = original                                       # type: ignore[assignment]


def test_zero_notional_is_refused_rather_than_dividing_by_zero():
    with pytest.raises(ValueError):
        _sim().cost_per_dollar_exposure(0.0)


# ======================================================================================
# PRICING
# ======================================================================================

def test_a_market_buy_crosses_to_the_ask_and_a_sell_to_the_bid():
    sim = _sim()
    q = _q()
    buy = sim.execute(_buy(), q)
    sell = sim.execute(OrderIntent(symbol="ES", side=Side.SELL, quantity=1.0), q)
    assert _fill(buy).price == 5_800.00
    assert _fill(sell).price == 5_799.75


def test_slippage_is_measured_from_the_mid_and_is_a_cost_on_both_sides():
    sim = _sim()
    q = _q()
    buy = sim.execute(_buy(), q)
    sell = sim.execute(OrderIntent(symbol="ES", side=Side.SELL, quantity=1.0), q)
    # Half a tick from the mid each way: 0.125 * 50 = $6.25.
    assert _fill(buy).slippage == pytest.approx(6.25)
    assert _fill(sell).slippage == pytest.approx(6.25)
    assert sim.total_slippage == pytest.approx(12.50), "a round turn pays the full spread"


def test_a_large_order_walks_the_book():
    sim = _sim()
    small = sim.execute(_buy(1.0), _q(ask_size=10))
    large = sim.execute(_buy(50.0), _q(ask_size=10))
    assert _fill(large).price > _fill(small).price
    # (50 - 10) / 10 = 4 books deep, 1 tick each.
    assert _fill(large).price == pytest.approx(5_800.00 + 4 * 0.25)


def test_an_order_inside_the_resting_size_pays_no_impact():
    sim = _sim()
    r = sim.execute(_buy(5.0), _q(ask_size=100))
    assert _fill(r).price == 5_800.00


def test_fills_are_rounded_against_the_trader():
    sim = _sim()
    # A price landing between ticks must round up for a buy and down for a sell.
    assert sim.round_to_tick(5_800.10, Side.BUY) == pytest.approx(5_800.25)
    assert sim.round_to_tick(5_800.10, Side.SELL) == pytest.approx(5_800.00)
    assert sim.round_to_tick(5_800.00, Side.BUY) == pytest.approx(5_800.00)


def test_commission_scales_with_quantity():
    sim = _sim()
    r = sim.execute(_buy(7.0), _q())
    assert _fill(r).commission == pytest.approx(7 * 2.0)


def test_a_passive_limit_behind_the_touch_is_refused_not_filled():
    """The most consequential modelling choice here, and the one most often got wrong.

    Assuming a resting bid gets filled lets a backtest collect the spread on every trade and
    ignore adverse selection - your bid trades precisely when the market is about to go
    lower. Estimating passive fills honestly needs queue position and trade prints, which
    this repository does not have, so they are refused rather than modelled.
    """
    sim = _sim()
    r = sim.execute(_buy(order_type=OrderType.LIMIT, limit_price=5_799.50), _q())
    assert not r.filled
    assert r.reason is ex.RejectReason.LIMIT_NOT_MARKETABLE
    assert "passive fills are not modelled" in r.detail


def test_a_marketable_limit_fills_at_the_touch():
    sim = _sim()
    r = sim.execute(_buy(order_type=OrderType.LIMIT, limit_price=5_800.00), _q())
    assert r.filled and _fill(r).price == pytest.approx(5_800.00)


def test_a_limit_never_fills_worse_than_its_price_even_walking_the_book():
    sim = _sim()
    r = sim.execute(_buy(50.0, order_type=OrderType.LIMIT, limit_price=5_800.25),
                    _q(ask_size=10))
    assert r.filled
    assert _fill(r).price <= 5_800.25, "the walk went through the limit"


def test_a_sell_limit_above_the_market_does_not_fill():
    sim = _sim()
    r = sim.execute(OrderIntent(symbol="ES", side=Side.SELL, quantity=1.0,
                                order_type=OrderType.LIMIT, limit_price=5_900.00), _q())
    assert not r.filled
    assert r.reason is ex.RejectReason.LIMIT_NOT_MARKETABLE


def test_a_sell_limit_the_market_has_come_up_to_does_fill():
    sim = _sim()
    r = sim.execute(OrderIntent(symbol="ES", side=Side.SELL, quantity=1.0,
                                order_type=OrderType.LIMIT, limit_price=5_799.75), _q())
    assert r.filled and _fill(r).price == pytest.approx(5_799.75)


def test_a_limit_order_without_a_price_is_refused():
    sim = _sim()
    with pytest.raises(ValueError):
        sim.fill_price(_buy(order_type=OrderType.LIMIT), _q())


# ======================================================================================
# QUOTES
# ======================================================================================

def test_a_crossed_or_impossible_quote_is_refused_at_construction():
    with pytest.raises(ValueError):
        ex.Quote(bid=5_801.0, ask=5_800.0)
    with pytest.raises(ValueError):
        ex.Quote(bid=0.0, ask=5_800.0)
    with pytest.raises(ValueError):
        ex.Quote(bid=-1.0, ask=-0.5)


def test_a_locked_market_is_allowed():
    q = ex.Quote(bid=5_800.0, ask=5_800.0)
    assert q.spread == 0.0 and q.mid == 5_800.0


def test_quote_accessors():
    q = _q()
    assert q.touch(Side.BUY) == q.ask and q.touch(Side.SELL) == q.bid
    assert q.resting(Side.BUY) == q.ask_size and q.resting(Side.SELL) == q.bid_size


# ======================================================================================
# REFUSALS
# ======================================================================================

def test_no_quote_means_no_fill_and_no_invented_price():
    """Part 32: if market data is unavailable, do not invent prices."""
    sim = _sim()
    r = sim.execute(_buy(), None)
    assert not r.filled
    assert r.reason is ex.RejectReason.NO_PRICE
    assert "not invented" in r.detail


def test_a_zero_quantity_order_is_refused():
    sim = _sim()
    assert sim.execute(OrderIntent(symbol="ES", side=Side.BUY, quantity=0.0), _q()).reason is (
        ex.RejectReason.ZERO_QUANTITY)


def test_new_risk_is_refused_inside_the_flatten_window():
    sim = _sim(flat_before_close=15)
    assert sim.execute(_buy(), _q(), minutes_to_close=20).filled
    r = sim.execute(_buy(), _q(), minutes_to_close=10)
    assert not r.filled and r.reason is ex.RejectReason.FLAT_BEFORE_CLOSE
    assert "cutoff 15" in r.detail


def test_new_risk_is_refused_inside_a_blackout():
    sim = _sim(blackouts=((dt.time(8, 28), dt.time(8, 32)),))
    assert sim.execute(_buy(), _q(), now=dt.time(8, 20)).filled
    assert not sim.execute(_buy(), _q(), now=dt.time(8, 30)).filled


def test_a_blackout_window_can_wrap_midnight():
    sim = _sim(blackouts=((dt.time(23, 50), dt.time(0, 10)),))
    assert sim.in_blackout(dt.time(23, 55))
    assert sim.in_blackout(dt.time(0, 5))
    assert not sim.in_blackout(dt.time(12, 0))


def test_the_position_limit_is_enforced_against_the_resulting_position():
    sim = _sim(max_position=5)
    assert sim.execute(_buy(3.0), _q(), position=0.0).filled
    r = sim.execute(_buy(3.0), _q(), position=3.0)
    assert not r.filled and r.reason is ex.RejectReason.POSITION_LIMIT
    assert "exceed 5" in r.detail


def test_the_position_limit_counts_absolute_size_not_signed():
    sim = _sim(max_position=5)
    r = sim.execute(OrderIntent(symbol="ES", side=Side.SELL, quantity=3.0), _q(),
                    position=-3.0)
    assert not r.filled and r.reason is ex.RejectReason.POSITION_LIMIT


def test_reducing_a_position_toward_flat_is_allowed_at_the_limit():
    sim = _sim(max_position=5)
    assert sim.execute(OrderIntent(symbol="ES", side=Side.SELL, quantity=3.0), _q(),
                       position=5.0).filled


# ======================================================================================
# A FLATTEN IS NEVER REFUSABLE
# ======================================================================================

def _flatten(qty=3.0):
    return OrderIntent(symbol="ES", side=Side.SELL, quantity=qty,
                       order_type=OrderType.FLATTEN, tag="emergency")


def test_a_flatten_bypasses_every_gate_at_once():
    """The brief is explicit: FLATTEN must not be suppressible by ordinary logic.

    A simulator that could refuse a flatten models a trap, not a venue - and it would let a
    strategy be tested under a regime where the emergency exit is closed, which is the one
    condition under which every risk number above becomes meaningless.
    """
    sim = _sim(flat_before_close=15, blackouts=((dt.time(0, 0), dt.time(23, 59)),),
               max_position=1)
    intent = _flatten(10.0)
    assert intent.is_flatten, "the test's flatten intent is not recognised as one"
    r = sim.execute(intent, _q(), minutes_to_close=1, now=dt.time(12, 0), position=10.0)
    assert r.filled, f"a flatten was refused: {r.reason.value}"


def test_a_flatten_still_needs_a_price():
    """The one thing a flatten cannot bypass: inventing a fill price."""
    sim = _sim()
    r = sim.execute(_flatten(), None)
    assert not r.filled and r.reason is ex.RejectReason.NO_PRICE


# ======================================================================================
# BOOKKEEPING
# ======================================================================================

def test_fills_and_rejects_are_both_recorded():
    sim = _sim(max_position=1)
    sim.execute(_buy(1.0), _q())
    sim.execute(_buy(5.0), _q(), position=1.0)
    assert len(sim.fills) == 1 and len(sim.rejects) == 1
    assert sim.rejects[0].reason is ex.RejectReason.POSITION_LIMIT


def test_totals_accumulate_across_fills():
    sim = _sim()
    for _ in range(4):
        sim.execute(_buy(2.0), _q())
    assert sim.total_commission == pytest.approx(4 * 2 * 2.0)
    assert sim.total_cost == pytest.approx(sim.total_commission + sim.total_slippage)


def test_the_result_renders_both_outcomes():
    sim = _sim(max_position=1)
    ok = str(sim.execute(_buy(1.0), _q()))
    bad = str(sim.execute(_buy(5.0), _q(), position=1.0))
    assert "ES" in ok and "@" in ok and "cost $" in ok
    assert bad.startswith("REJECTED") and "position_limit" in bad


# ======================================================================================
# THE SPREAD IS NOW MEASURED, NOT ASSUMED
#
# The model charged one tick because one tick is the venue minimum, which is a floor rather
# than a measurement. The ES quote store fetched 2026-09-13 settles it: median exactly 1.00
# tick in RTH, 95.6% of bars at one tick.
# ======================================================================================

QUOTES = "data/futures/ES_quotes.parquet"


def test_the_spread_is_a_parameter_not_a_hard_coded_tick():
    cheap = ex.CostModel(commission_per_side=2.0, spread_ticks=1.0)
    wide = ex.CostModel(commission_per_side=2.0, spread_ticks=2.0)
    a = ex.ExecutionSimulator(cost=cheap, symbol="ES").round_turn_cost(1.0)
    b = ex.ExecutionSimulator(cost=wide, symbol="ES").round_turn_cost(1.0)
    assert b - a == pytest.approx(12.50), "a second tick of spread costs one more tick value"


def test_measure_spread_reports_the_shape_of_the_distribution():
    import pandas as pd
    q = pd.DataFrame({"spread": [0.25] * 90 + [0.50] * 10})
    out = ex.measure_spread_ticks(q, tick=0.25)
    assert out["median_ticks"] == pytest.approx(1.0)
    assert out["one_tick_share"] == pytest.approx(0.90)
    assert out["n"] == 100


def test_measure_spread_drops_halt_and_rollover_artefacts():
    import pandas as pd
    q = pd.DataFrame({"spread": [0.25] * 99 + [500.0]})
    out = ex.measure_spread_ticks(q, tick=0.25)
    assert out["n"] == 99, "a 2000-tick spread is a halt, not something a strategy trades"


def test_measure_spread_refuses_an_empty_store():
    import pandas as pd
    with pytest.raises(ValueError) as e:
        ex.measure_spread_ticks(pd.DataFrame({"spread": []}), tick=0.25)
    assert "empty" in str(e.value) or "artefact" in str(e.value)


@pytest.mark.skipif(not __import__("pathlib").Path(QUOTES).exists(),
                    reason="no ES quote store on this machine")
def test_the_real_es_spread_confirms_the_one_tick_assumption():
    """Three independent numbers, agreeing to within 2%.

    This is the test the cost model has been waiting for since it was written: it charged a
    spread it had no way to verify. Now the tape answers, and it agrees both with the model
    and with F-2a's separately measured realised cost.
    """
    import pandas as pd
    q = pd.read_parquet(QUOTES)
    q["t"] = pd.to_datetime(q["t"], utc=True)
    hm = q["t"].dt.tz_convert("America/New_York").dt.strftime("%H:%M")
    rth = q[(hm >= "09:30") & (hm <= "16:00")]

    out = ex.measure_spread_ticks(rth, tick=0.25)
    assert out["median_ticks"] == pytest.approx(1.0), (
        f"the one-tick assumption is wrong: median is {out['median_ticks']:.2f} ticks")
    assert out["one_tick_share"] > 0.90

    price = float(pd.Series(pd.to_numeric(rth["c"])).median())
    modelled = _sim("ES").cost_per_dollar_exposure(price) * 10_000
    assert modelled == pytest.approx(0.480, abs=0.02)
    assert modelled == pytest.approx(MEASURED_ES_BPS, abs=0.03), (
        "the model and F-2a's realised measurement must agree at the SAME price; comparing "
        "across price levels is what once made the model look 17% conservative")
