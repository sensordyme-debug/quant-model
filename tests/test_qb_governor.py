"""The governor: every limit bites, every refusal carries a code, no switch resets itself.

Adversarial by design. Each test is a way the governor could have been wrong and quietly
let an order through; the assertions are the ways it must fail instead.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
from typing import Any

import pytest

from quant_brain.core.execution import (
    OrderIntent,
    OrderType,
    RoutedExecutor,
    Side,
    SimulatedAdapter,
)
from quant_brain.core.governor import AccountView, Governor, KillSwitch, LimitEngine, Limits, Reason
from quant_brain.core.mode import Authority

UTC = dt.UTC


def buy(qty=1.0, symbol="MES"):
    return OrderIntent(symbol=symbol, side=Side.BUY, quantity=qty)


def flat(qty=1.0, symbol="MES"):
    return OrderIntent(symbol=symbol, side=Side.SELL, quantity=qty, order_type=OrderType.FLATTEN)


def healthy(**over: Any):
    base: dict[str, Any] = dict(daily_pnl=0.0, drawdown=0.0, positions={}, notional=0.0, trades_today=0,
                consecutive_losses=0, last_trade_at=None, distance_to_mll=2000.0,
                risk_per_contract={"MES": 50.0}, now=dt.datetime(2026, 9, 14, 14, 0, tzinfo=UTC))
    base.update(over)
    return AccountView(**base)


# ---------------------------------------------------------------------------------------
# Reason codes are machine-readable and closed
# ---------------------------------------------------------------------------------------

def test_every_reason_is_a_string_and_kill_switch_flag_partitions_them():
    codes = {r.value for r in Reason}
    assert len(codes) == len(list(Reason))
    ks = {r for r in Reason if r.is_kill_switch}
    assert Reason.DATA_STALE in ks and Reason.CONNECTION_UNSAFE in ks
    assert Reason.RISK_DAILY_LOSS not in ks and Reason.RISK_PER_TRADE not in ks


def test_denial_binding_is_a_reason_code_not_free_text():
    eng = LimitEngine(Limits(max_daily_loss=500), healthy(daily_pnl=-500))
    d = eng(buy())
    assert not d.allowed
    assert d.binding == (Reason.RISK_DAILY_LOSS.value,)
    Reason(d.binding[0])  # parses back into the enum


# ---------------------------------------------------------------------------------------
# State limits deny; size limits reduce
# ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("limits,view,code", [
    (Limits(max_daily_loss=500), healthy(daily_pnl=-500.01), Reason.RISK_DAILY_LOSS),
    (Limits(daily_profit_stop=800), healthy(daily_pnl=800), Reason.RISK_DAILY_PROFIT_STOP),
    (Limits(max_drawdown=1000), healthy(drawdown=1000), Reason.RISK_DRAWDOWN),
    (Limits(max_trades_per_day=3), healthy(trades_today=3), Reason.RISK_TRADES_PER_DAY),
    (Limits(max_consecutive_losses=2), healthy(consecutive_losses=2),
     Reason.RISK_CONSECUTIVE_LOSSES),
    (Limits(max_concurrent_positions=1), healthy(positions={"MNQ": 1}),
     Reason.RISK_CONCURRENT_POSITIONS),
    (Limits(max_notional=10_000), healthy(notional=10_000), Reason.RISK_NOTIONAL),
    (Limits(mll_buffer=500), healthy(distance_to_mll=500), Reason.RISK_MLL_BUFFER),
])
def test_state_limits_deny_at_the_boundary(limits, view, code):
    d = LimitEngine(limits, view)(buy())
    assert not d.allowed, d
    assert code.value in d.binding


def test_one_dollar_inside_the_daily_loss_is_still_allowed():
    d = LimitEngine(Limits(max_daily_loss=500), healthy(daily_pnl=-499))(buy())
    assert d.allowed and d.quantity == 1.0


def test_cooldown_denies_then_clears():
    now = dt.datetime(2026, 9, 14, 14, 0, tzinfo=UTC)
    L = Limits(cooldown_seconds=60)
    d = LimitEngine(L, healthy(now=now, last_trade_at=now - dt.timedelta(seconds=30)))(buy())
    assert not d.allowed and Reason.RISK_COOLDOWN.value in d.binding
    d = LimitEngine(L, healthy(now=now, last_trade_at=now - dt.timedelta(seconds=61)))(buy())
    assert d.allowed


def test_concurrent_positions_limit_does_not_block_adding_to_an_open_symbol():
    d = LimitEngine(Limits(max_concurrent_positions=1), healthy(positions={"MES": 1}))(buy())
    assert d.allowed


@pytest.mark.parametrize("limits,view,want,code", [
    (Limits(max_position=3), healthy(positions={"MES": 2}), 1, Reason.RISK_POSITION_SIZE),
    (Limits(max_contracts=5), healthy(positions={"MES": 2, "MNQ": -2}), 1,
     Reason.RISK_MAX_CONTRACTS),
    (Limits(max_risk_per_trade=125), healthy(), 2, Reason.RISK_PER_TRADE),      # 125/50 = 2.5
    (Limits(mll_buffer=500), healthy(distance_to_mll=650), 3, Reason.RISK_MLL_BUFFER),  # 150/50
])
def test_size_limits_reduce_to_the_room_left(limits, view, want, code):
    d = LimitEngine(limits, view)(buy(10))
    assert d.allowed and d.quantity == want, d
    assert code.value in d.binding


def test_size_limit_with_no_room_is_a_denial_not_a_zero_order():
    d = LimitEngine(Limits(max_position=2), healthy(positions={"MES": 2}))(buy(1))
    assert not d.allowed and d.quantity == 0


def test_tightest_size_limit_wins_and_every_binding_rule_is_named():
    L = Limits(max_position=5, max_contracts=4, max_risk_per_trade=150)   # room 5, 4, 3
    d = LimitEngine(L, healthy())(buy(10))
    assert d.allowed and d.quantity == 3
    assert set(d.binding) == {Reason.RISK_POSITION_SIZE.value, Reason.RISK_MAX_CONTRACTS.value,
                              Reason.RISK_PER_TRADE.value}


# ---------------------------------------------------------------------------------------
# Unknown is not okay
# ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("limits,missing", [
    (Limits(max_daily_loss=500), "daily_pnl"),
    (Limits(max_drawdown=500), "drawdown"),
    (Limits(max_trades_per_day=5), "trades_today"),
    (Limits(max_consecutive_losses=3), "consecutive_losses"),
    (Limits(mll_buffer=100), "distance_to_mll"),
])
def test_configured_limit_with_unknown_input_denies_with_data_unavailable(limits, missing):
    d = LimitEngine(limits, healthy(**{missing: None}))(buy())
    assert not d.allowed
    assert d.binding == (Reason.DATA_UNAVAILABLE.value,)


def test_per_trade_risk_with_unknown_stop_distance_denies():
    d = LimitEngine(Limits(max_risk_per_trade=100), healthy(risk_per_contract={}))(buy())
    assert not d.allowed and Reason.DATA_UNAVAILABLE.value in d.binding


def test_per_trade_risk_with_zero_stop_distance_is_a_data_quality_denial():
    d = LimitEngine(Limits(max_risk_per_trade=100),
                    healthy(risk_per_contract={"MES": 0.0}))(buy())
    assert not d.allowed and Reason.DATA_QUALITY.value in d.binding


def test_no_limits_configured_and_no_data_is_allowed_because_nothing_was_asked():
    # The contract: a None in Limits is a choice, a None in the view is only a problem when
    # some limit needs it. With nothing configured the empty view must not deny.
    d = LimitEngine(Limits(), AccountView())(buy(3))
    assert d.allowed and d.quantity == 3


# ---------------------------------------------------------------------------------------
# Kill switches
# ---------------------------------------------------------------------------------------

def test_tripped_switch_denies_with_its_code_and_stays_tripped():
    s = KillSwitch(Reason.DATA_STALE)
    assert s(buy()).allowed
    s.trip("last bar 91s old")
    d = s(buy())
    assert not d.allowed and d.binding == (Reason.DATA_STALE.value,)
    assert "91s" in d.reasons[0]
    assert not s(buy()).allowed          # no auto-reset on the next evaluation
    assert s.tripped_at is not None


def test_switch_reset_requires_a_named_person():
    s = KillSwitch(Reason.CONNECTION_UNSAFE)
    s.trip("hub disconnected")
    with pytest.raises(ValueError):
        s.reset(by="")
    with pytest.raises(ValueError):
        s.reset(by="   ")
    assert s.tripped
    s.reset(by="operator")
    assert not s.tripped and s.reset_by == "operator"


def test_tripped_switch_still_lets_a_flatten_through():
    s = KillSwitch(Reason.POSITION_UNRECONCILED)
    s.trip("broker shows 2, local shows 1")
    d = s(flat(2))
    assert d.allowed and d.quantity == 2


# ---------------------------------------------------------------------------------------
# Governor composes the lot
# ---------------------------------------------------------------------------------------

def test_governor_has_one_switch_per_kill_switch_reason_and_none_for_limits():
    g = Governor(Limits(), healthy())
    assert set(g.switches) == {r for r in Reason if r.is_kill_switch}
    with pytest.raises(ValueError):
        g.trip(Reason.RISK_DAILY_LOSS, "not a switch")


def test_governor_switch_short_circuits_before_limits():
    g = Governor(Limits(max_position=1), healthy(positions={"MES": 1}))
    g.trip(Reason.DATA_STALE, "feed dead")
    d = g(buy())
    assert not d.allowed
    assert d.binding == (Reason.DATA_STALE.value,)     # the cause, not the limit


def test_governor_halted_and_status_reflect_trips():
    g = Governor(Limits(max_daily_loss=500), healthy())
    assert not g.halted and g.status()["tripped"] == []
    g.trip(Reason.BRACKET_UNVERIFIED, "MES long 2, no stop")
    assert g.halted
    st = g.status()
    assert st["halted"] and st["tripped"][0]["reason"] == "BRACKET_UNVERIFIED"
    assert st["limits"] == {"max_daily_loss": 500}
    g.reset(Reason.BRACKET_UNVERIFIED, by="operator")
    assert not g.halted


def test_governor_status_never_contains_secret_looking_keys():
    st = Governor(Limits(), healthy()).status()
    flat_keys = set()

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                flat_keys.add(k.lower())
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(st)
    assert not {k for k in flat_keys if any(w in k for w in ("key", "token", "secret", "password"))}


def test_governor_in_routed_executor_refuses_and_records_reason_code():
    g = Governor(Limits(max_daily_loss=500), healthy(daily_pnl=-600))
    ex = RoutedExecutor(g, SimulatedAdapter(), authority=Authority.backtest())
    acks = ex.submit([buy(2)])
    assert acks == []
    (_, decision), = ex.refused
    assert decision.binding == (Reason.RISK_DAILY_LOSS.value,)


def test_governor_in_routed_executor_flatten_survives_every_trip():
    g = Governor(Limits(max_daily_loss=1), healthy(daily_pnl=-999))
    for r in Reason:
        if r.is_kill_switch:
            g.trip(r, "everything is on fire")
    adapter = SimulatedAdapter()
    ex = RoutedExecutor(g, adapter, authority=Authority.backtest())
    acks = ex.flatten({"MES": 3, "MNQ": -2})
    assert len(acks) == 2 and all(a.accepted for a in acks)


def test_limits_are_frozen():
    L = Limits(max_daily_loss=500)
    with pytest.raises(dataclasses.FrozenInstanceError):
        L.max_daily_loss = 5000  # type: ignore[misc]


def test_limits_project_onto_sizing_at_the_governor_level():
    from quant_brain.core.sizing import Binding
    sl = Limits(max_position=3.0, max_risk_per_trade=150.0).size_limits()
    levels = {b: (c, r) for b, c, r in sl.levels()}
    assert levels[Binding.GOVERNOR] == (3, 150.0)
    assert levels[Binding.VENUE] == (None, None)
    assert Limits().size_limits().levels().__next__()[1:] == (None, None)
