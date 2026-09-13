"""Tests for the Topstep digital twin, the payout decision, and the risk budget.

The twin exists to make two things visible that a pass/fail simulator hides: that the
Express Funded Account is a second, harder barrier than the Combine, and that a payout is a
risk decision rather than a cash transfer. Most of these tests are built around one of
those two facts.
"""
from __future__ import annotations

import datetime as dt

import pytest

from quant_brain.markets.futures_cme import topstep as ts
from quant_brain.markets.futures_cme import twin as tw


def _days(pnl, *, path=True, adverse=1.5):
    fn = tw.u_shaped_path(adverse) if path else None
    return tw.days_from_pnl(list(pnl), path_fn=fn)


def _twin(**kw):
    kw.setdefault("profit_target", 3_000.0)
    return tw.TopstepTwin(50_000, **kw)


# ======================================================================================
# THE MISSING INTRADAY PATH IS A REFUSAL, NOT A DEFAULT
# ======================================================================================

def test_sessions_without_an_intraday_path_are_refused():
    t = _twin()
    with pytest.raises(ValueError) as e:
        t.run(_days([100.0, 200.0], path=False))
    msg = str(e.value)
    assert "intraday" in msg and "upper bound" in msg, (
        "the refusal must explain that the alternative is an optimistic estimate")


def test_the_refusal_can_be_waived_and_the_result_says_so():
    t = _twin(strict_path=False)
    r = t.run(_days([100.0, 200.0], path=False))
    assert r.path_supplied is False


def test_a_partial_path_still_trips_the_refusal():
    t = _twin()
    days = _days([100.0, 200.0])
    days[1] = tw.TwinDay(day=days[1].day, pnl=200.0)      # path stripped
    with pytest.raises(ValueError):
        t.run(days)


# ======================================================================================
# THE LIFECYCLE - passing is not the payoff
# ======================================================================================

def test_passing_the_combine_resets_the_balance_to_zero_with_the_same_limit():
    """The whole reason the twin exists. A comfortable pass buys a harder account."""
    t = _twin(payout_policy=tw.NEVER)
    r = t.run(_days([800.0, 700.0, 900.0, 700.0] + [0.0] * 5, adverse=1.0))
    stages = [s for _, s in r.transitions]
    assert ts.TopstepStage.COMBINE_PASSED in stages
    assert ts.TopstepStage.EXPRESS_FUNDED in stages
    assert r.combine_days == 4
    # After the roll, the account is at $0 profit again with the identical $2,000 of room.
    assert r.final_balance == pytest.approx(0.0)
    assert t.xfa_profile.starting_balance == 0.0
    assert t.xfa_profile.max_drawdown == t.combine_profile.max_drawdown


def test_the_pass_rate_and_the_paid_rate_are_different_numbers():
    """If they were equal the second barrier would be free, and it is not."""
    t = _twin(payout_policy=tw.IMMEDIATE)
    # Passes the Combine on day 4, then loses the XFA before five winning days accumulate.
    paths = [_days([800.0, 700.0, 900.0, 700.0, -700.0, -700.0, -700.0], adverse=1.0)]
    ev = tw.evaluate_twin(t, paths)
    assert ev.p_pass_combine == 1.0
    assert ev.p_first_payout == 0.0
    assert ev.p_liquidated == 1.0


def test_a_combine_breach_ends_the_path_when_only_one_attempt_is_allowed():
    t = _twin(max_combine_attempts=1)
    r = t.run(_days([-2_500.0] + [100.0] * 10, adverse=1.0))
    assert r.terminal is ts.TopstepStage.LIQUIDATED
    assert r.combine_attempts == 1
    assert r.breach_day == dt.date(2026, 1, 5)
    assert r.combine_days is None


def test_more_attempts_buy_another_combine_and_another_fee():
    t = _twin(max_combine_attempts=3, combine_fee=100.0)
    r = t.run(_days([-2_500.0, -2_500.0, 100.0, 100.0], adverse=1.0))
    assert r.combine_attempts == 3
    assert r.fees_paid == 300.0
    assert r.terminal is not ts.TopstepStage.LIQUIDATED, "the third attempt is still alive"


def test_a_funded_account_is_never_re_entered_within_a_path():
    t = _twin(max_combine_attempts=5, payout_policy=tw.NEVER)
    r = t.run(_days([800.0, 700.0, 900.0, 700.0, -2_500.0, 500.0, 500.0], adverse=1.0))
    assert r.terminal is ts.TopstepStage.LIQUIDATED
    assert r.combine_attempts == 1, "losing the XFA must not silently buy a new Combine"


# ======================================================================================
# THE PAYOUT DECISION
# ======================================================================================

def _funded_path(n_winning=6, win=400.0):
    return _days([800.0, 700.0, 900.0, 700.0] + [win] * n_winning, adverse=1.0)


def test_the_never_policy_withdraws_nothing():
    r = _twin(payout_policy=tw.NEVER).run(_funded_path())
    assert r.payouts == [] and r.total_paid == 0.0


def test_the_immediate_policy_withdraws_at_the_first_opportunity():
    r = _twin(payout_policy=tw.IMMEDIATE).run(_funded_path())
    assert len(r.payouts) == 1
    _, amount = r.payouts[0]
    assert amount == pytest.approx(1_000.0)     # balance 2,000 after 5 x 400, half of it


def test_a_payout_shrinks_the_funded_buffer_by_exactly_what_it_takes():
    taken = _twin(payout_policy=tw.IMMEDIATE).run(_funded_path())
    kept = _twin(payout_policy=tw.NEVER).run(_funded_path())
    assert taken.min_buffer_funded == pytest.approx(kept.min_buffer_funded - 1_000.0)


def test_the_buffer_floor_caps_the_withdrawal():
    r = _twin(payout_policy=tw.PayoutPolicy(min_buffer_after=1_600.0)).run(_funded_path())
    assert len(r.payouts) == 1
    assert r.payouts[0][1] == pytest.approx(400.0)   # 2,000 of room less the 1,600 floor


def test_a_buffer_floor_above_the_balance_blocks_the_payout_entirely():
    r = _twin(payout_policy=tw.PayoutPolicy(min_buffer_after=5_000.0)).run(_funded_path())
    assert r.payouts == []


def test_the_fraction_takes_part_of_the_eligible_cap():
    r = _twin(payout_policy=tw.PayoutPolicy(fraction=0.25)).run(_funded_path())
    assert r.payouts[0][1] == pytest.approx(250.0)


def test_wait_days_delays_the_withdrawal():
    early = _twin(payout_policy=tw.IMMEDIATE).run(_funded_path(n_winning=8))
    late = _twin(payout_policy=tw.PayoutPolicy(wait_days=3)).run(_funded_path(n_winning=8))
    assert late.payouts[0][0] > early.payouts[0][0]


def test_stop_after_caps_lifetime_withdrawals():
    long_path = _funded_path(n_winning=40)
    uncapped = _twin(payout_policy=tw.IMMEDIATE).run(long_path)
    capped = _twin(payout_policy=tw.PayoutPolicy(stop_after=1_500.0)).run(long_path)
    assert uncapped.total_paid > capped.total_paid
    assert capped.total_paid <= 1_500.0 + capped.payouts[-1][1]


def test_taking_less_can_earn_more_because_the_account_survives():
    """The twin's headline result, pinned so a refactor cannot quietly reverse it.

    A path that grinds up and then takes a run of losses: withdrawing everything at the
    first opportunity strips the buffer that would have absorbed the losing run, and the
    account dies before the second payout it would otherwise have earned.
    """
    path = _days([800.0, 700.0, 900.0, 700.0]        # pass the Combine
                 + [400.0] * 5                        # five winning days -> eligible
                 + [-300.0] * 3                       # a losing run
                 + [400.0] * 5, adverse=1.0)          # and a second run of winners
    greedy = _twin(payout_policy=tw.IMMEDIATE).run(path)
    patient = _twin(payout_policy=tw.PayoutPolicy(fraction=0.5)).run(path)
    assert greedy.terminal is ts.TopstepStage.LIQUIDATED
    assert patient.terminal is not ts.TopstepStage.LIQUIDATED
    assert patient.total_paid > greedy.total_paid


def test_compare_policies_does_not_mutate_the_original_twin():
    t = _twin(payout_policy=tw.IMMEDIATE)
    tw.compare_policies(t, [_funded_path()], {"never": tw.NEVER, "half":
                                              tw.PayoutPolicy(fraction=0.5)})
    assert t.policy is tw.IMMEDIATE


def test_compare_policies_returns_one_evaluation_per_policy():
    out = tw.compare_policies(_twin(), [_funded_path()],
                              {"a": tw.NEVER, "b": tw.IMMEDIATE})
    assert set(out) == {"a", "b"}
    assert out["a"].mean_gross == 0.0
    assert out["b"].mean_gross > 0.0


# ======================================================================================
# THE ECONOMICS FAIL CLOSED
# ======================================================================================

def test_net_capital_is_none_when_the_fee_is_unknown():
    r = _twin(payout_policy=tw.IMMEDIATE).run(_funded_path())
    assert r.fees_paid is None
    assert r.net_capital is None
    assert r.gross_capital > 0
    assert "fee unknown" in r.summary()


def test_the_evaluation_refuses_to_call_gross_a_profit():
    ev = tw.evaluate_twin(_twin(), [_funded_path()])
    assert ev.fee_known is False
    assert ev.mean_net is None
    assert "FEE UNKNOWN" in ev.summary()
    assert "not a profit figure" in ev.summary()


def test_a_supplied_fee_produces_a_net_figure():
    r = _twin(payout_policy=tw.IMMEDIATE, combine_fee=165.0).run(_funded_path())
    assert r.fees_paid == 165.0
    assert r.net_capital == pytest.approx(r.gross_capital - 165.0)
    ev = tw.evaluate_twin(_twin(payout_policy=tw.IMMEDIATE, combine_fee=165.0),
                          [_funded_path()])
    assert ev.fee_known and ev.mean_net is not None
    assert "FEE UNKNOWN" not in ev.summary()


def test_the_twin_uses_the_verified_profit_target_without_being_told():
    """It used to raise here. The target is DOC-tier as of 2026-09-13."""
    assert tw.TopstepTwin(50_000).combine_profile.profit_target == 3_000.0


# ======================================================================================
# THE DAILY LOSS LIMIT
# ======================================================================================

def test_the_daily_loss_limit_caps_the_day_without_ending_the_account():
    t = _twin(daily_loss_limit=1_000.0)
    r = t.run(_days([-5_000.0, 200.0, 200.0], adverse=1.0))
    assert r.terminal is not ts.TopstepStage.LIQUIDATED, (
        "8284207: triggering the DLL is not a rule violation")
    assert r.days == 3


def test_without_the_daily_loss_limit_the_same_day_is_fatal():
    r = _twin().run(_days([-5_000.0, 200.0, 200.0], adverse=1.0))
    assert r.terminal is ts.TopstepStage.LIQUIDATED


def test_an_armed_daily_loss_limit_above_the_mll_prevents_liquidation():
    """Both limits are levels the day falls through; the higher one fires first.

    A fresh Combine sits at 50,000 with the MLL at 48,000. An armed $1,000 DLL puts a
    flatten at 49,000 - above the MLL - so a session that would have run to -$2,100 is
    stopped at -$1,000 and the account cannot reach the floor at all. Arming the DLL is
    therefore a genuine reduction in liquidation risk, paid for in days ended early.
    """
    days = [tw.TwinDay(day=dt.date(2026, 1, 5), pnl=-500.0,
                       path=(-100.0, -2_100.0, -500.0))]
    unarmed = _twin().run(days)
    assert unarmed.terminal is ts.TopstepStage.LIQUIDATED
    assert "intraday" in unarmed.breach_reason

    armed = _twin(daily_loss_limit=1_000.0).run(days)
    assert armed.terminal is not ts.TopstepStage.LIQUIDATED
    assert armed.final_balance == pytest.approx(49_000.0), "the day is capped at -$1,000"


def test_a_daily_loss_limit_below_the_mll_protects_nothing():
    """The other side of the ordering: near the floor, the MLL is the higher level.

    After grinding down to 48,900 the account has $900 of room but a $1,000 DLL, whose
    flatten sits at 47,900 - below the floor. The MLL is reached first and the DLL is
    decorative, which is exactly when a trader would most like to believe otherwise.
    """
    t = _twin(daily_loss_limit=1_000.0)
    days = _days([-550.0, -550.0], adverse=1.0)          # down to 48,900
    days.append(tw.TwinDay(day=dt.date(2026, 1, 7), pnl=-950.0,
                           path=(-200.0, -950.0)))
    r = t.run(days)
    assert r.terminal is ts.TopstepStage.LIQUIDATED
    assert "MLL" in r.breach_reason


def test_with_daily_loss_limit_helper_uses_the_documented_amount():
    p = tw.with_daily_loss_limit(ts.combine(50_000, profit_target=3_000.0), 50_000)
    assert p.daily_loss_limit == 1_000.0


# ======================================================================================
# THE RISK BUDGET
# ======================================================================================

def test_on_a_combine_the_balance_and_the_room_differ_by_an_order_of_magnitude():
    """Sizing off the balance would put on ~18x what the account can survive."""
    a = ts.TopstepAccount(profile=ts.combine(50_000, profit_target=3_000.0))
    for _ in range(6):
        a.settle_day(500.0)                        # balance 53,000, floor locked at 50,000
    assert a.balance == 53_000.0
    assert a.mll_locked and a.distance_to_mll == 3_000.0
    assert tw.risk_budget(a) == pytest.approx(750.0)
    assert a.balance / a.distance_to_mll > 17


def test_on_a_young_xfa_the_room_exceeds_the_balance():
    """The other direction: sizing off the balance would trade far too small."""
    x = ts.TopstepAccount(profile=ts.express_funded(50_000),
                          stage=ts.TopstepStage.EXPRESS_FUNDED)
    for _ in range(1):
        x.settle_day(500.0)
    assert x.balance == 500.0
    assert not x.mll_locked and x.distance_to_mll == 2_000.0
    assert tw.risk_budget(x) == pytest.approx(500.0)


def test_a_locked_xfa_is_the_one_case_where_balance_and_room_agree():
    """Documented as the coincidence that makes anchoring to balance look harmless."""
    x = ts.TopstepAccount(profile=ts.express_funded(50_000),
                          stage=ts.TopstepStage.EXPRESS_FUNDED)
    for _ in range(15):
        x.settle_day(400.0)
    assert x.mll_locked and x.balance == x.distance_to_mll == 6_000.0


def test_a_payout_halves_the_room_on_a_locked_xfa():
    flush = ts.TopstepAccount(profile=ts.express_funded(50_000),
                              stage=ts.TopstepStage.EXPRESS_FUNDED)
    for _ in range(15):
        flush.settle_day(400.0)
    before = tw.risk_budget(flush)
    flush.advance()
    paid = flush.take_payout()
    # $6,000 balance on a 50K XFA: half the balance is $3,000 but the ceiling is $2,000,
    # so the CEILING binds here, not the half-balance rule.
    assert paid == 2_000.0, "the 50K standard ceiling is $2,000, not the $150K row"
    assert tw.risk_budget(flush) == pytest.approx(before * 4 / 6)


def test_the_risk_budget_shrinks_the_moment_a_payout_is_taken():
    a = ts.TopstepAccount(profile=ts.express_funded(50_000),
                          stage=ts.TopstepStage.EXPRESS_FUNDED)
    for _ in range(10):
        a.settle_day(400.0)
    before = tw.risk_budget(a)
    a.advance()
    a.take_payout()
    assert tw.risk_budget(a) < before


def test_an_invalid_risk_fraction_is_refused():
    a = ts.TopstepAccount(profile=ts.combine(50_000, profit_target=3_000.0))
    for bad in (0.0, -0.1, 1.5):
        with pytest.raises(ValueError):
            tw.risk_budget(a, fraction=bad)


def test_max_contracts_clamps_to_the_firm_ceiling():
    a = ts.TopstepAccount(profile=ts.combine(50_000, profit_target=3_000.0))
    # 25% of $2,000 is $500; at $1 of risk per contract that is 500 contracts, but the
    # profile permits 50 micros.
    assert tw.max_contracts(a, 1.0) == 50


def test_max_contracts_returns_zero_rather_than_rounding_up_to_one():
    a = ts.TopstepAccount(profile=ts.combine(50_000, profit_target=3_000.0))
    # 25% of $2,000 is $500; one contract risks $600.
    assert tw.max_contracts(a, 600.0) == 0


def test_max_contracts_scales_with_the_remaining_room():
    a = ts.TopstepAccount(profile=ts.combine(50_000, profit_target=3_000.0))
    full = tw.max_contracts(a, 50.0)
    a.mark(-1_500.0)
    assert tw.max_contracts(a, 50.0) < full


def test_a_nonsense_risk_per_contract_is_refused():
    a = ts.TopstepAccount(profile=ts.combine(50_000, profit_target=3_000.0))
    for bad in (0.0, -5.0):
        with pytest.raises(ValueError):
            tw.max_contracts(a, bad)


# ======================================================================================
# PATH CONSTRUCTION
# ======================================================================================

def test_days_from_pnl_skips_weekends():
    days = tw.days_from_pnl([1.0] * 7, start=dt.date(2026, 1, 8))   # a Thursday
    assert all(d.day.weekday() < 5 for d in days)
    assert len({d.day for d in days}) == 7


def test_days_from_pnl_leaves_the_path_empty_by_default():
    assert all(d.path == () for d in tw.days_from_pnl([1.0, 2.0]))


def test_the_u_shaped_path_dips_below_the_close_in_both_directions():
    build = tw.u_shaped_path(2.0)
    up = build(500.0)
    assert up[-1] == 500.0 and min(up) == -1_000.0
    down = build(-500.0)
    assert down[-1] == -500.0 and min(down) == -1_000.0


def test_an_adverse_factor_below_one_is_refused():
    with pytest.raises(ValueError) as e:
        tw.u_shaped_path(0.5)
    assert "decorative" in str(e.value)


def test_worst_mark_includes_the_close():
    d = tw.TwinDay(day=dt.date(2026, 1, 5), pnl=-900.0, path=(-100.0, -200.0))
    assert d.worst_mark == -900.0
    e = tw.TwinDay(day=dt.date(2026, 1, 5), pnl=100.0, path=(-100.0, -800.0))
    assert e.worst_mark == -800.0


# ======================================================================================
# THE EVALUATION
# ======================================================================================

def test_the_minimum_buffer_is_never_negative_on_a_surviving_measurement():
    """A dead account has no buffer; recording the overshoot would poison the percentile."""
    t = _twin(payout_policy=tw.IMMEDIATE)
    for r in (t.run(_days([-2_500.0] + [100.0] * 3, adverse=1.0)),
              t.run(_funded_path())):
        assert r.min_buffer >= 0.0
        assert r.min_buffer_funded >= 0.0


def test_never_funded_paths_report_no_funded_buffer():
    r = _twin().run(_days([-2_500.0], adverse=1.0))
    assert not r.reached_funding
    assert r.min_buffer_funded == 0.0


def test_the_evaluation_aggregates_over_paths():
    t = _twin(payout_policy=tw.IMMEDIATE, combine_fee=100.0)
    good = _funded_path()
    bad = _days([-2_500.0] + [100.0] * 3, adverse=1.0)
    ev = tw.evaluate_twin(t, [good, good, bad, bad])
    assert ev.paths == 4
    assert ev.p_pass_combine == 0.5
    assert ev.p_first_payout == 0.5
    assert ev.p_liquidated == 0.5
    assert ev.mean_net == pytest.approx((1_000.0 - 100.0 + 1_000.0 - 100.0
                                         - 100.0 - 100.0) / 4)


def test_the_evaluation_label_defaults_to_the_profile_name():
    ev = tw.evaluate_twin(_twin(), [_funded_path()])
    assert ev.label == "TOPSTEP_COMBINE_50K"


def test_an_empty_path_set_does_not_divide_by_zero():
    ev = tw.evaluate_twin(_twin(), [])
    assert ev.paths == 0 and ev.p_pass_combine == 0.0
    assert ev.median_days_to_pass is None
