"""Prop-firm rules: the gate a model may not argue with, and the absorbing barrier.

Part 5 requires that "the ML model must NEVER be able to override hard risk constraints".
That is a structural claim, so it is tested structurally: there is no argument, field or
call ordering that turns a denial into an approval.

Part 6 requires that the simulator model the barrier faithfully. The tests that matter most
are the ones showing the three trailing conventions give *different* answers on the *same*
equity path - if they did not, the profile field would be decoration.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import replace

import pytest

from quant_brain.core.execution import OrderIntent, OrderType, Side
from quant_brain.core.risk import RiskChain, RiskDecision, RiskEngine
from quant_brain.markets.futures_cme import instruments as fut
from quant_brain.markets.futures_cme.profiles import (
    EOD_TRAILING_50K,
    INTRADAY_TRAILING_50K,
    STATIC_DRAWDOWN_100K,
    get,
)
from quant_brain.markets.futures_cme.propfirm import (
    AccountState,
    Outcome,
    PropFirmProfile,
    PropFirmRiskEngine,
    PropFirmSimulator,
    SessionPnL,
    TrailingMode,
    evaluate,
)

D = dt.date


def buy(sym="MES", qty=1):
    return OrderIntent(symbol=sym, side=Side.BUY, quantity=qty)


def flatten(sym="MES", qty=1):
    return OrderIntent(symbol=sym, side=Side.SELL, quantity=qty, order_type=OrderType.FLATTEN)


def state(profile=EOD_TRAILING_50K, **kw):
    s = AccountState(profile=profile)
    for k, v in kw.items():
        setattr(s, k, v)
    return s


# ---------------------------------------------------------------- the non-negotiable gate

def test_denies_when_daily_loss_limit_is_hit():
    s = state(balance=50_000 - 1_100)
    s.day_start_balance = 50_000.0
    d = PropFirmRiskEngine(s)(buy())
    assert not d.allowed and "daily_loss_limit" in d.binding


def test_denies_when_equity_is_at_the_trailing_floor():
    s = state(balance=48_000.0, peak=50_000.0)     # floor = 50,000 - 2,000
    s.day_start_balance = 48_000.0
    d = PropFirmRiskEngine(s)(buy())
    assert not d.allowed and "trailing_drawdown" in d.binding


def test_reduces_to_the_room_left_under_a_symbol_cap():
    s = state(contracts={"ES": 3})
    d = PropFirmRiskEngine(s)(OrderIntent("ES", Side.BUY, 5))
    assert d.allowed and d.quantity == 2          # cap 5, holding 3
    assert "max_contracts_per_symbol" in d.binding


def test_denies_when_a_cap_leaves_no_room_at_all():
    s = state(contracts={"ES": 5})
    d = PropFirmRiskEngine(s)(OrderIntent("ES", Side.BUY, 1))
    assert not d.allowed


def test_total_contract_cap_counts_across_symbols():
    s = state(contracts={"ES": 3, "NQ": 2})       # total cap is 5
    d = PropFirmRiskEngine(s)(OrderIntent("NQ", Side.BUY, 2))
    assert not d.allowed or d.quantity == 0


def test_a_dead_account_cannot_open_anything():
    s = state()
    s.outcome = Outcome.FAILED_TRAILING
    assert not PropFirmRiskEngine(s)(buy()).allowed


# ------------------------------------------------- the exit is never blocked (AUD-06/08)

def test_flatten_passes_every_gate_even_on_a_dead_account():
    """A risk layer that can block the exit is not a risk layer."""
    s = state(balance=10.0, peak=50_000.0, contracts={"MES": 50})
    s.outcome = Outcome.FAILED_TRAILING
    s.day_start_balance = 50_000.0
    d = PropFirmRiskEngine(s)(flatten(qty=50))
    assert d.allowed and d.quantity == 50


def test_flatten_bypasses_a_chain_containing_a_denier():
    class DenyAll(RiskEngine):
        name = "deny"

        def evaluate(self, intent):
            return RiskDecision.deny("no", "deny_all")

    chain = RiskChain([DenyAll(), PropFirmRiskEngine(state())])
    assert not chain(buy()).allowed
    assert chain(flatten()).allowed


# ---------------------------------------------------------- no override path exists

def test_a_denial_carries_no_usable_quantity():
    """Structural: a caller cannot lift a size off a rejected decision."""
    d = RiskDecision.deny("nope", "rule")
    assert d.allowed is False and d.quantity == 0.0


def test_merge_is_order_independent_and_always_takes_the_tighter_answer():
    a = RiskDecision.allow(10)
    b = RiskDecision.reduce(3, "cap", "r")
    c = RiskDecision.deny("dead", "r2")
    assert a.merge(b).quantity == b.merge(a).quantity == 3
    assert not a.merge(c).allowed
    assert not c.merge(a).allowed          # a later permissive engine cannot re-permit


def test_reduce_to_zero_is_a_denial_not_a_zero_size_order():
    assert not RiskDecision.reduce(0, "no room", "cap").allowed


def test_chain_short_circuits_on_the_first_denial():
    class Boom(RiskEngine):
        name = "boom"

        def evaluate(self, intent):
            raise AssertionError("must not be reached after a denial")

    chain = RiskChain([PropFirmRiskEngine(state(contracts={"ES": 5})), Boom()])
    assert not chain(OrderIntent("ES", Side.BUY, 1)).allowed


# ------------------------------------------------------------- session and news rules

def test_blackout_window_covers_the_0830_release():
    eng = PropFirmRiskEngine(state())
    assert eng.in_blackout(dt.time(8, 30))
    assert eng.in_blackout(dt.time(14, 0))
    assert not eng.in_blackout(dt.time(10, 15))


def test_flat_deadline_is_relative_to_the_close_so_early_closes_work():
    """The AUD-07 lesson applied here: minutes-to-close, never a bar index."""
    eng = PropFirmRiskEngine(state())
    assert eng.must_be_flat(minutes_to_close=10)
    assert not eng.must_be_flat(minutes_to_close=45)


def test_overnight_permitted_profile_never_forces_flat():
    p = PropFirmProfile(name="swing", starting_balance=50_000, allow_overnight=True)
    assert not PropFirmRiskEngine(state(p)).must_be_flat(minutes_to_close=1)


# ------------------------------------------------------ trailing conventions differ

def _path(pnls):
    return [SessionPnL(day=D(2026, 1, 5) + dt.timedelta(days=i), pnl=v)
            for i, v in enumerate(pnls)]


# These two isolate the trailing mechanic by switching the daily cap off. With it on, a
# -2,100 day is truncated to -1,100 and never reaches the floor at all - which is itself
# worth knowing, and is pinned by `test_daily_loss_that_does_not_end_the_account_caps_the_day`.
_UNCAPPED = replace(EOD_TRAILING_50K, name="uncapped", daily_loss_limit=None)


def test_trailing_floor_can_fail_an_account_that_is_still_in_profit():
    """The property that makes prop-firm trading a different game from investing.

    +3,000 then -2,500 leaves the account up 500 on the month and dead: the peak dragged the
    floor to 51,000 and the balance is 50,500. No Sharpe or CAR figure sees this.
    """
    unlocked = replace(_UNCAPPED, name="unlocked", trailing_locks_at=None)
    r = PropFirmSimulator(unlocked).run(_path([3_000, -2_500]))
    assert r.outcome is Outcome.FAILED_TRAILING
    assert r.final_balance > unlocked.starting_balance      # profitable, and still failed


def test_the_lock_saves_the_same_path_the_unlocked_profile_kills():
    """`trailing_locks_at` is the single highest-value field in a profile."""
    unlocked = replace(_UNCAPPED, name="unlocked", trailing_locks_at=None)
    path = _path([3_000, -2_500])
    assert PropFirmSimulator(_UNCAPPED).run(path).outcome is Outcome.IN_PROGRESS
    assert PropFirmSimulator(unlocked).run(path).outcome is Outcome.FAILED_TRAILING


def test_intraday_trailing_kills_a_path_that_eod_survives():
    """Same realized P&L, different convention, different outcome."""
    day = SessionPnL(day=D(2026, 1, 5), pnl=100.0,
                     # went +2,600 then gave it all back to +100
                     intraday_equity=[0, 1_200, 2_600, 400, 100])
    eod = PropFirmProfile(**{**INTRADAY_TRAILING_50K.__dict__, "name": "eod",
                             "trailing_mode": TrailingMode.EOD})
    assert PropFirmSimulator(eod).run([day]).outcome is Outcome.IN_PROGRESS
    assert PropFirmSimulator(INTRADAY_TRAILING_50K).run([day]).outcome is Outcome.FAILED_TRAILING


def test_static_floor_ignores_the_peak_entirely():
    sim = PropFirmSimulator(STATIC_DRAWDOWN_100K)
    r = sim.run(_path([5_000, -1_000, -1_000, -1_000]))   # peak 105k, still above 97k floor
    assert r.outcome is Outcome.IN_PROGRESS
    r2 = sim.run(_path([-1_500, -1_500]))                  # 97,000 floor reached
    assert r2.outcome is Outcome.FAILED_MAX_DRAWDOWN


# ----------------------------------------------------------------------- passing

def test_profit_target_passes_once_min_days_are_met():
    r = PropFirmSimulator(EOD_TRAILING_50K).run(_path([700] * 5))
    assert r.outcome is Outcome.PASSED and r.days == 5


def test_target_reached_too_early_keeps_trading_until_min_days():
    """3,000 on day one must not pass a profile that requires five trading days."""
    r = PropFirmSimulator(EOD_TRAILING_50K).run(_path([3_200]))
    assert r.outcome is Outcome.IN_PROGRESS


def test_consistency_rule_fails_a_one_lucky_day_account():
    # Five days, but one contributes far more than 40% of the profit.
    r = PropFirmSimulator(EOD_TRAILING_50K).run(_path([100, 100, 2_800, 100, 100]))
    assert r.outcome is Outcome.FAILED_CONSISTENCY


def test_daily_loss_that_does_not_end_the_account_caps_the_day():
    r = PropFirmSimulator(EOD_TRAILING_50K).run(_path([-5_000, 200]))
    assert r.daily_pnl[0] == -1_100.0          # capped, not -5,000
    assert r.outcome is Outcome.IN_PROGRESS


def test_daily_loss_ends_the_account_when_the_profile_says_so():
    p = PropFirmProfile(**{**EOD_TRAILING_50K.__dict__, "name": "harsh",
                           "daily_loss_ends_account": True})
    assert PropFirmSimulator(p).run(_path([-5_000])).outcome is Outcome.FAILED_DAILY_LOSS


# --------------------------------------------------------------------- the distribution

def test_evaluate_reports_a_distribution_not_a_single_number():
    good = [_path([700] * 5) for _ in range(6)]
    dead = [_path([-1_200, -1_200]) for _ in range(4)]
    ev = evaluate(EOD_TRAILING_50K, good + dead)
    assert ev.paths == 10
    assert ev.pass_rate == pytest.approx(0.6)
    assert sum(ev.failure_rates.values()) == pytest.approx(0.4)
    assert "pass 60.0%" in ev.summary()


def test_expected_capital_is_net_of_the_evaluation_fee():
    """A pass rate that ignores the fee is not an objective, it is a vanity metric."""
    all_fail = [_path([-1_200, -1_200]) for _ in range(5)]
    ev = evaluate(EOD_TRAILING_50K, all_fail)
    assert ev.expected_capital == pytest.approx(-EOD_TRAILING_50K.evaluation_fee)


# ------------------------------------------------------------------------ profile I/O

def test_profile_round_trips_through_json():
    back = PropFirmProfile.from_dict(
        __import__("json").loads(EOD_TRAILING_50K.to_json()))
    assert back == EOD_TRAILING_50K


def test_unknown_rule_key_is_refused_rather_than_ignored():
    """A typo'd rule silently disabling a limit is the failure this module prevents."""
    d = __import__("json").loads(EOD_TRAILING_50K.to_json())
    d["max_daily_loss"] = 500          # plausible-looking, not a real field
    with pytest.raises(ValueError, match="unknown rule"):
        PropFirmProfile.from_dict(d)


def test_archetype_lookup_error_names_the_alternatives():
    with pytest.raises(KeyError, match="known:"):
        get("topstep_50k")


# --------------------------------------------------------- contract terms feed sizing

def test_micro_sizing_gives_ten_times_the_granularity_under_a_contract_cap():
    """Why micros matter under a 3-contract limit: 3 ES = 30 MES of exposure, in 30 steps."""
    es, mes = fut.get("ES"), fut.get("MES")
    assert es.spec.multiplier / mes.spec.multiplier == 10.0
    assert fut.micros_of("ES") == ["MES"]


# ================================================ weekend and scaling rules (audit Phase 6)

def test_a_weekday_overnight_hold_can_be_allowed_while_the_weekend_is_not():
    """Several firms permit an overnight hold and still require flat into the weekend, because
    a Friday-to-Sunday gap is the one move no intraday stop can protect against."""
    p = replace(EOD_TRAILING_50K, name="wk", allow_overnight=True, allow_weekend=False)
    eng = PropFirmRiskEngine(state(p))
    assert not eng.must_be_flat(5, is_last_session_of_week=False)   # Tuesday: hold
    assert eng.must_be_flat(5, is_last_session_of_week=True)        # Friday: flatten


def test_a_firm_that_allows_the_weekend_does_not_force_a_friday_flatten():
    p = replace(EOD_TRAILING_50K, name="wk", allow_overnight=True, allow_weekend=True)
    assert not PropFirmRiskEngine(state(p)).must_be_flat(5, is_last_session_of_week=True)


def test_an_intraday_only_firm_still_flattens_every_day():
    p = replace(EOD_TRAILING_50K, name="flat", allow_overnight=False, allow_weekend=False)
    eng = PropFirmRiskEngine(state(p))
    assert eng.must_be_flat(5, is_last_session_of_week=False)
    assert eng.must_be_flat(5, is_last_session_of_week=True)


def test_no_ladder_means_the_flat_contract_cap_applies_at_every_balance():
    p = replace(EOD_TRAILING_50K, name="flat", max_total_contracts=5, scaling=())
    for profit in (-1000.0, 0.0, 5000.0):
        assert p.contracts_allowed_at(profit) == 5


def test_a_ladder_scales_permitted_size_with_the_accounts_own_profit():
    """A strategy sized for the funded ceiling is untradeable on day one; the ladder is how
    a rulebook says so."""
    p = replace(EOD_TRAILING_50K, name="ladder", max_total_contracts=10,
                scaling=((0.0, 2), (1_000.0, 5), (2_500.0, 10)))
    assert p.contracts_allowed_at(0.0) == 2
    assert p.contracts_allowed_at(999.0) == 2
    assert p.contracts_allowed_at(1_000.0) == 5
    assert p.contracts_allowed_at(3_000.0) == 10


def test_a_losing_account_keeps_the_first_rung_rather_than_zero():
    """A ladder that left a fresh or drawn-down account with no permitted size would be a
    misreading of every rulebook, not a conservative one."""
    p = replace(EOD_TRAILING_50K, name="ladder", scaling=((500.0, 3), (2_000.0, 6)))
    assert p.contracts_allowed_at(-800.0) == 3


def test_the_flat_cap_still_bounds_the_ladder():
    p = replace(EOD_TRAILING_50K, name="ladder", max_total_contracts=4,
                scaling=((0.0, 2), (1_000.0, 20)))
    assert p.contracts_allowed_at(5_000.0) == 4


def test_the_risk_engine_enforces_the_ladder_from_live_account_state():
    """The cap moves with the balance, so it is read from state, not from the profile alone."""
    p = replace(EOD_TRAILING_50K, name="ladder", max_total_contracts=10,
                max_contracts_per_symbol={}, scaling=((0.0, 1), (5_000.0, 10)))
    poor = state(p, balance=50_000.0)                 # +0 profit -> 1 contract
    rich = state(p, balance=56_000.0)                 # +6,000    -> 10 contracts
    assert PropFirmRiskEngine(poor)(OrderIntent("MES", Side.BUY, 5)).quantity == 1
    assert PropFirmRiskEngine(rich)(OrderIntent("MES", Side.BUY, 5)).allowed


def test_the_ladder_round_trips_through_json():
    p = replace(EOD_TRAILING_50K, name="ladder", scaling=((0.0, 2), (1_000.0, 5)))
    back = PropFirmProfile.from_dict(__import__("json").loads(p.to_json()))
    assert back == p and back.scaling == ((0.0, 2), (1_000.0, 5))
