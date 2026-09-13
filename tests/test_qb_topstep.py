"""Tests for the Topstep rulebook, the hybrid MLL, and the account state machine.

Three things are being defended here, in descending order of how much money they are worth:

1. The MLL is EOD-trailing with an intraday breach test, and that is genuinely different
   from both of the modes that existed before. Several tests construct paths where EOD and
   INTRADAY give *opposite* answers and pin the hybrid to the documented one.
2. Nothing unverified becomes a number without the caller saying so out loud.
3. The consistency reading is configurable and the readings actually differ, so the
   ambiguity in Topstep's own page is measurable rather than buried.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import replace

import pytest

from quant_brain.markets.futures_cme import topstep as ts
from quant_brain.markets.futures_cme.propfirm import (
    Outcome,
    PropFirmProfile,
    PropFirmSimulator,
    SessionPnL,
    TrailingMode,
)

# ======================================================================================
# PROVENANCE - every rule must carry its evidence
# ======================================================================================

def _all_rules() -> dict[str, ts.Rule]:
    out: dict[str, ts.Rule] = {}
    for name in dir(ts):
        obj = getattr(ts, name)
        if isinstance(obj, ts.Rule):
            out[name] = obj
        elif isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, ts.Rule):
                    out[f"{name}[{k}]"] = v
    return out


def test_every_rule_carries_a_source_and_a_date():
    rules = _all_rules()
    assert len(rules) > 30, "the rulebook should be substantial, not a handful of constants"
    for name, rule in rules.items():
        assert rule.source, f"{name} has no source"
        assert rule.quote, f"{name} has no quote"
        assert isinstance(rule.retrieved, dt.date), f"{name} has no retrieval date"


def test_every_documented_rule_cites_a_topstep_url():
    for name, rule in _all_rules().items():
        if rule.confidence is ts.Confidence.DOC:
            assert rule.source.startswith("https://help.topstep.com/"), (
                f"{name} claims DOC confidence but does not cite a help-centre page")


def test_retrieval_date_is_the_date_the_pages_were_fetched():
    assert ts.RETRIEVED == dt.date(2026, 9, 12)
    for name, rule in _all_rules().items():
        assert rule.retrieved <= dt.date.today(), f"{name} claims a future retrieval date"


def test_cite_renders_quote_source_and_date():
    text = ts.MLL[50_000].cite()
    assert "$50K $2,000" in text
    assert "help.topstep.com" in text
    assert "2026-09-12" in text
    assert "DOC" in text


def test_confidence_is_ordered_so_it_can_gate():
    assert ts.Confidence.OWNER < ts.Confidence.SEARCH < ts.Confidence.DOC


def test_unresolved_lists_exactly_the_rules_below_doc():
    unresolved = ts.unresolved()
    for name, rule in unresolved.items():
        assert rule.confidence < ts.Confidence.DOC, f"{name} is resolved, should not be listed"
    # The three things the owner genuinely has to supply.
    assert any("profit_target" in k for k in unresolved)
    assert "xfa_scaling_plan" in unresolved
    assert "combine_min_trading_days" in unresolved


def test_rulebook_renders_every_rule_with_its_citation():
    text = ts.rulebook()
    assert "TOPSTEP RULEBOOK - retrieved 2026-09-12" in text
    for probe in ("$50K $2,000", "Best Day Profit / Total Profit",
                  "Each Express Funded Account starts with a $0 balance",
                  "20% available to trade immediately"):
        assert probe in text, f"rulebook omits {probe!r}"


# ======================================================================================
# FAIL CLOSED - the unverified profit target
# ======================================================================================

def test_combine_refuses_to_invent_a_profit_target():
    with pytest.raises(ts.UnverifiedRule) as e:
        ts.combine(50_000)
    assert "profit target" in str(e.value).lower()
    assert "dashboard" in str(e.value).lower(), "the error must say how to resolve it"


def test_combine_accepts_an_owner_supplied_target():
    p = ts.combine(50_000, profit_target=3_000.0)
    assert p.profit_target == 3_000.0


def test_combine_accepts_the_search_tier_target_only_when_asked():
    p = ts.combine(50_000, allow_unverified_target=True)
    assert p.profit_target == 3_000.0
    assert ts.COMBINE_PROFIT_TARGET[50_000].confidence is ts.Confidence.SEARCH


def test_require_below_the_bar_names_the_source_and_the_tier():
    with pytest.raises(ts.UnverifiedRule) as e:
        ts.XFA_SCALING.require(what="scaling plan")
    msg = str(e.value)
    assert "scaling plan" in msg and "OWNER" in msg and "help.topstep.com" in msg


def test_unknown_account_size_is_refused():
    for bad in (25_000, 250_000, 0):
        with pytest.raises(KeyError):
            ts.combine(bad, profit_target=1_000.0)
        with pytest.raises(KeyError):
            ts.express_funded(bad)


# ======================================================================================
# THE RULEBOOK'S NUMBERS
# ======================================================================================

@pytest.mark.parametrize("size,minis,micros", [(50_000, 5, 50), (100_000, 10, 100),
                                               (150_000, 15, 150)])
def test_contract_caps_match_the_published_table(size, minis, micros):
    p = ts.combine(size, profit_target=1_000.0)
    assert p.max_total_contracts == micros
    assert p.max_contracts_per_symbol["ES"] == minis
    assert p.max_contracts_per_symbol["MES"] == micros


@pytest.mark.parametrize("size,mll", [(50_000, 2_000.0), (100_000, 3_000.0),
                                      (150_000, 4_500.0)])
def test_mll_matches_the_published_table(size, mll):
    assert ts.combine(size, profit_target=1_000.0).max_drawdown == mll
    assert ts.express_funded(size).max_drawdown == mll


@pytest.mark.parametrize("size,dll", [(50_000, 1_000.0), (100_000, 2_000.0),
                                      (150_000, 3_000.0)])
def test_daily_loss_limit_is_off_unless_asked_for(size, dll):
    assert ts.combine(size, profit_target=1_000.0).daily_loss_limit is None
    on = ts.combine(size, profit_target=1_000.0, daily_loss_limit=ts.DLL_OPTIONAL[size].value)
    assert on.daily_loss_limit == dll


def test_a_daily_loss_hit_never_ends_the_account():
    # 8284207: "Triggering it is not a rule violation."
    p = ts.combine(50_000, profit_target=3_000.0, daily_loss_limit=1_000.0)
    assert p.daily_loss_ends_account is False


def test_live_funded_daily_loss_differs_from_the_combine():
    # The LFA's automatic DLL is NOT the Combine's optional one; conflating them would
    # under-report risk on the funded account by a factor of two at 50K.
    for size in ts.SIZES:
        assert ts.LFA_DLL[size].value != ts.DLL_OPTIONAL[size].value


def test_profit_split_is_ninety_ten():
    assert ts.combine(50_000, profit_target=3_000.0).profit_split == 0.90


def test_overnight_and_weekend_are_both_refused():
    p = ts.combine(50_000, profit_target=3_000.0)
    assert p.allow_overnight is False and p.allow_weekend is False


# ======================================================================================
# THE HYBRID MLL - the rule that did not fit
# ======================================================================================

def test_topstep_uses_the_hybrid_trailing_mode():
    assert ts.combine(50_000, profit_target=3_000.0).trailing_mode is (
        TrailingMode.EOD_TRAIL_INTRADAY_BREACH)
    assert ts.express_funded(50_000).trailing_mode is (
        TrailingMode.EOD_TRAIL_INTRADAY_BREACH)


def test_the_mll_does_not_advance_on_an_unrealized_high():
    """An intraday spike that gives it all back must not raise the floor.

    This is the half of the hybrid that differs from INTRADAY. Under INTRADAY a +$800 mark
    would ratchet the floor up $800; under Topstep's rule it does nothing at all.
    """
    a = ts.TopstepAccount(profile=ts.combine(50_000, profit_target=3_000.0))
    floor_before = a.mll
    a.mark(800.0)
    assert a.mll == floor_before, "unrealized profit moved the MLL; Topstep's does not"
    a.mark(0.0)
    a.settle_day(0.0)
    assert a.mll == floor_before


def test_settling_discards_the_mark_and_trails_the_balance():
    """A stale unrealized mark must not leak into the end-of-day peak.

    `settle_day` currently syncs equity to balance before advancing the peak, which makes
    "trail the balance" and "trail the equity" the same expression there - a mutation between
    them survives. That equivalence is load-bearing rather than incidental, so pin it: an
    open +$3,000 mark that is not part of the realized day must leave the floor where the
    realized balance puts it.
    """
    a = ts.TopstepAccount(profile=ts.combine(50_000, profit_target=3_000.0))
    a.mark(3_000.0)
    assert a.equity == 53_000.0
    a.settle_day(200.0)
    assert a.equity == a.balance == 50_200.0, "the mark must not survive the settle"
    assert a.mll == 48_200.0, "the floor followed the mark, not the realized balance"


def test_the_mll_does_advance_on_the_end_of_day_balance():
    """The other half: a realized gain that survives to the close does move it."""
    a = ts.TopstepAccount(profile=ts.combine(50_000, profit_target=3_000.0))
    assert a.mll == 48_000.0
    a.settle_day(500.0)
    assert a.mll == 48_500.0


def test_the_breach_is_tested_intraday_on_unrealized_pnl():
    """Equity touching the floor mid-session is a breach even if the day would close green."""
    a = ts.TopstepAccount(profile=ts.combine(50_000, profit_target=3_000.0))
    a.mark(-1_999.0)
    assert not a.breached()
    a.mark(-2_000.0)
    assert a.breached(), "unrealized loss reaching the MLL must breach"
    assert a.advance() is ts.TopstepStage.LIQUIDATED


def test_liquidation_is_absorbing():
    a = ts.TopstepAccount(profile=ts.combine(50_000, profit_target=3_000.0))
    a.mark(-2_500.0)
    assert a.advance() is ts.TopstepStage.LIQUIDATED
    a.mark(0.0)
    a.settle_day(5_000.0)
    assert a.advance() is ts.TopstepStage.LIQUIDATED, "a dead account cannot recover"


def test_the_mll_locks_at_the_starting_balance_and_never_moves_again():
    a = ts.TopstepAccount(profile=ts.combine(50_000, profit_target=3_000.0))
    a.settle_day(1_500.0)
    assert not a.mll_locked and a.mll == 49_500.0
    a.settle_day(500.0)                       # peak 52,000 -> floor would be 50,000
    assert a.mll_locked and a.mll == 50_000.0
    a.settle_day(3_000.0)                     # peak 55,000
    assert a.mll == 50_000.0, "a locked MLL must not keep trailing"


def test_the_xfa_mll_locks_at_zero_once_the_balance_reaches_the_limit():
    # 8284204: "Once your balance reaches $2,000, the MLL locks at $0 permanently."
    a = ts.TopstepAccount(profile=ts.express_funded(50_000),
                          stage=ts.TopstepStage.EXPRESS_FUNDED)
    assert a.balance == 0.0 and a.mll == -2_000.0
    a.settle_day(1_999.0)
    assert not a.mll_locked
    a.settle_day(1.0)                          # balance 2,000
    assert a.mll_locked and a.mll == 0.0
    a.settle_day(5_000.0)
    assert a.mll == 0.0


@pytest.mark.parametrize("size", ts.SIZES)
def test_the_xfa_lock_point_is_the_size_specific_mll_without_a_lock_constant(size):
    a = ts.TopstepAccount(profile=ts.express_funded(size),
                          stage=ts.TopstepStage.EXPRESS_FUNDED)
    limit = ts.MLL[size].value
    a.settle_day(limit - 1.0)
    assert not a.mll_locked
    a.settle_day(1.0)
    assert a.mll_locked and a.mll == 0.0


def _outcome(mode: TrailingMode, sessions: list[SessionPnL]) -> Outcome:
    base = ts.combine(50_000, profit_target=3_000.0)
    return PropFirmSimulator(replace(base, trailing_mode=mode)).run(sessions).outcome


def test_the_hybrid_is_not_intraday_the_unrealized_high_must_not_ratchet():
    """A +$1,500 mark given back, then a -$1,600 day. INTRADAY kills it; Topstep does not.

    Under INTRADAY the first session's unrealized high lifts the floor to 49,500, so the
    next day's 48,400 is a breach. Under Topstep's rule the floor never left 48,000 - the
    balance never closed higher - so 48,400 survives. Same path, opposite answers.
    """
    sessions = [
        SessionPnL(day=dt.date(2026, 1, 5), pnl=0.0, intraday_equity=[1_500.0, 0.0]),
        SessionPnL(day=dt.date(2026, 1, 6), pnl=-1_600.0, intraday_equity=[-1_600.0]),
    ]
    assert _outcome(TrailingMode.INTRADAY, sessions) is Outcome.FAILED_TRAILING
    assert _outcome(TrailingMode.EOD_TRAIL_INTRADAY_BREACH, sessions) is not (
        Outcome.FAILED_TRAILING)


def test_the_real_combine_profile_breaches_on_an_intraday_dip():
    """No mode override: the profile `combine()` actually builds must fail this path.

    The two tests around this one pass an explicit TrailingMode, which means neither would
    notice if `MLL_TRAILS` were changed to plain EOD - a mutation that silently stops the
    simulator walking the intraday path and understates breach risk on every Topstep
    estimate. This test is the one that ties the shipped profile to the behaviour.
    """
    p = ts.combine(50_000, profit_target=3_000.0)
    sessions = [SessionPnL(day=dt.date(2026, 1, 5), pnl=400.0,
                           intraday_equity=[-500.0, -2_100.0, 400.0])]
    assert PropFirmSimulator(p).run(sessions).outcome is Outcome.FAILED_TRAILING


def test_the_real_xfa_profile_breaches_on_an_intraday_dip():
    p = ts.express_funded(50_000)
    sessions = [SessionPnL(day=dt.date(2026, 1, 5), pnl=100.0,
                           intraday_equity=[-500.0, -2_000.0, 100.0])]
    assert PropFirmSimulator(p).run(sessions).outcome is Outcome.FAILED_TRAILING


def test_the_hybrid_is_not_eod_the_intraday_dip_must_be_tested():
    """The other direction: a day that closes green after dipping past the floor.

    EOD never looks at the path and passes it. Topstep liquidates intraday, on unrealized
    P&L. The two errors point opposite ways, which is why neither mode could stand in.
    """
    sessions = [SessionPnL(day=dt.date(2026, 1, 5), pnl=400.0,
                           intraday_equity=[-500.0, -2_100.0, 400.0])]
    assert _outcome(TrailingMode.EOD, sessions) is not Outcome.FAILED_TRAILING
    assert _outcome(TrailingMode.EOD_TRAIL_INTRADAY_BREACH, sessions) is (
        Outcome.FAILED_TRAILING)


def test_simulator_survives_the_same_day_without_the_intraday_dip():
    p = ts.combine(50_000, profit_target=3_000.0)
    sessions = [SessionPnL(day=dt.date(2026, 1, 5), pnl=400.0,
                           intraday_equity=[-500.0, -100.0, 400.0])]
    result = PropFirmSimulator(p).run(sessions)
    assert result.outcome is not Outcome.FAILED_TRAILING


# ======================================================================================
# THE STARTING-BALANCE AMBIGUITY IS IMMATERIAL
# ======================================================================================

@pytest.mark.parametrize("start", [0.0, 50_000.0, 1_234.5])
def test_outcomes_are_invariant_to_the_unpublished_starting_balance(start):
    """Topstep calls 50K 'buying power', not a balance, and never states the opening figure.

    Everything that decides an outcome is relative to the start, so the level cannot matter.
    Asserting that is honest; asserting a balance the documentation never gave would not be.
    """
    p = ts.combine(50_000, profit_target=3_000.0, starting_balance=start)
    a = ts.TopstepAccount(profile=p)
    assert a.distance_to_mll == 2_000.0
    for pnl in (900.0, -400.0, 1_200.0, 1_400.0):
        a.settle_day(pnl)
    assert a.total_profit == 3_100.0
    # Peak balance is start+3,100, so the floor has locked at the start itself and the whole
    # 3,100 of profit is the buffer - the same three numbers at every starting level.
    assert a.mll_locked
    assert a.mll == start
    assert a.distance_to_mll == 3_100.0
    assert a.best_day == 1_400.0
    assert a.consistency_pct == pytest.approx(1_400.0 / 3_100.0)
    assert a.combine_passed()[0] is True


def test_relative_quantities_match_across_two_starting_balances():
    a = ts.TopstepAccount(profile=ts.combine(50_000, profit_target=3_000.0,
                                             starting_balance=0.0))
    b = ts.TopstepAccount(profile=ts.combine(50_000, profit_target=3_000.0,
                                             starting_balance=50_000.0))
    for pnl in (700.0, -250.0, 1_100.0, 900.0, 800.0):
        a.settle_day(pnl)
        b.settle_day(pnl)
    assert a.total_profit == b.total_profit
    assert a.distance_to_mll == b.distance_to_mll
    assert a.mll_locked == b.mll_locked
    assert a.combine_passed() == b.combine_passed()


# ======================================================================================
# CONSISTENCY - the contradiction, made measurable
# ======================================================================================

def test_the_default_reading_is_the_strict_one():
    assert ts.DEFAULT_READING == "strict"
    assert ts.CONSISTENCY_READINGS["strict"] == (0.50, "total")


def test_both_documented_readings_are_recorded_verbatim():
    assert ts.COMBINE_CONSISTENCY_DOC.value == 0.55
    assert "55% of your Profit Target" in ts.COMBINE_CONSISTENCY_DOC.quote
    assert ts.COMBINE_CONSISTENCY_DENOMINATOR.value == "total"
    assert "Best Day Profit / Total Profit" in ts.COMBINE_CONSISTENCY_DENOMINATOR.quote
    assert ts.COMBINE_CONSISTENCY_OWNER.value == 0.50
    assert ts.COMBINE_CONSISTENCY_OWNER.confidence is ts.Confidence.OWNER


def test_an_unknown_reading_is_refused():
    with pytest.raises(KeyError):
        ts.combine(50_000, profit_target=3_000.0, reading="whatever")
    with pytest.raises(KeyError):
        ts.TopstepAccount(profile=ts.combine(50_000, profit_target=3_000.0),
                          reading="whatever")


def test_the_readings_actually_differ_on_one_path():
    """One equity path, four readings, and they do not all agree - which is the point."""
    days = [1_600.0, 600.0, 500.0, 400.0]      # best day 1,600 of 3,100 total
    verdicts = {}
    for name in ts.CONSISTENCY_READINGS:
        a = ts.TopstepAccount(
            profile=ts.combine(50_000, profit_target=3_000.0, reading=name), reading=name)
        for d in days:
            a.settle_day(d)
        verdicts[name] = a.combine_passed()[0]
    assert len(set(verdicts.values())) > 1, (
        f"every reading agreed ({verdicts}); the ambiguity would then be immaterial and "
        "this module's configurability unnecessary")


def test_strict_reading_blocks_a_lopsided_pass():
    a = ts.TopstepAccount(profile=ts.combine(50_000, profit_target=3_000.0))
    a.settle_day(2_000.0)
    a.settle_day(1_100.0)                      # 3,100 total, best day 65%
    ok, why = a.combine_passed()
    assert not ok
    assert "consistency" in why.lower() or "best day" in why.lower()


def test_exceeding_consistency_raises_the_target_rather_than_failing():
    """8284208: "If it exceeds that, your Profit Target increases." Not a failure."""
    a = ts.TopstepAccount(profile=ts.combine(50_000, profit_target=3_000.0))
    a.settle_day(2_000.0)
    a.settle_day(1_100.0)
    assert a.stage is ts.TopstepStage.TRADING_COMBINE
    assert a.advance() is ts.TopstepStage.TRADING_COMBINE, "must not be marked failed"
    assert a.effective_profit_target == pytest.approx(4_000.0)   # 2,000 / 0.50
    assert a.profit_target_remaining == pytest.approx(900.0)


def test_trading_on_past_the_raised_target_eventually_passes():
    a = ts.TopstepAccount(profile=ts.combine(50_000, profit_target=3_000.0))
    a.settle_day(2_000.0)
    a.settle_day(1_100.0)
    assert not a.combine_passed()[0]
    a.settle_day(900.0)                        # 4,000 total, best day exactly 50%
    ok, why = a.combine_passed()
    assert ok, why


def test_consistency_is_none_not_zero_before_any_profit():
    a = ts.TopstepAccount(profile=ts.combine(50_000, profit_target=3_000.0))
    assert a.consistency_pct is None
    a.settle_day(-500.0)
    assert a.consistency_pct is None, "a loss-making account has no meaningful percentage"


def test_target_reading_uses_the_target_as_the_denominator():
    a = ts.TopstepAccount(profile=ts.combine(50_000, profit_target=3_000.0,
                                             reading="doc_text"), reading="doc_text")
    a.settle_day(1_650.0)                      # 55% of the 3,000 target exactly
    assert a.consistency_pct == pytest.approx(0.55)
    assert a.consistency_ok


def test_the_engine_is_not_given_a_share_under_the_target_reading():
    """Otherwise the engine's total-profit test and the account's target test both apply."""
    p = ts.combine(50_000, profit_target=3_000.0, reading="doc_text")
    assert p.max_single_day_profit_share is None
    q = ts.combine(50_000, profit_target=3_000.0, reading="doc_calc")
    assert q.max_single_day_profit_share == 0.55


def test_with_reading_switches_a_built_profile():
    p = ts.combine(50_000, profit_target=3_000.0)
    assert ts.with_reading(p, "doc_calc").max_single_day_profit_share == 0.55
    assert ts.with_reading(p, "doc_text").max_single_day_profit_share is None
    assert "doc_calc" in ts.with_reading(p, "doc_calc").name


# ======================================================================================
# THE STATE MACHINE
# ======================================================================================

def test_the_happy_path_runs_combine_to_payout():
    a = ts.TopstepAccount(profile=ts.combine(50_000, profit_target=3_000.0))
    for d in (800.0, 700.0, 900.0, 700.0):     # 3,100 total, best day 29%
        a.settle_day(d)
    assert a.advance() is ts.TopstepStage.COMBINE_PASSED
    assert a.advance() is ts.TopstepStage.EXPRESS_FUNDED

    x = ts.TopstepAccount(profile=ts.express_funded(50_000),
                          stage=ts.TopstepStage.EXPRESS_FUNDED)
    for d in (300.0, 250.0, 400.0, 200.0):
        x.settle_day(d)
    assert x.advance() is ts.TopstepStage.EXPRESS_FUNDED, "four winning days is not five"
    x.settle_day(350.0)
    assert x.advance() is ts.TopstepStage.PAYOUT_ELIGIBLE


def test_a_day_under_a_hundred_and_fifty_is_not_a_winning_day():
    x = ts.TopstepAccount(profile=ts.express_funded(50_000),
                          stage=ts.TopstepStage.EXPRESS_FUNDED)
    for d in (149.99, 149.0, 100.0, 1.0, 149.5):
        x.settle_day(d)
    assert x.winning_days == 0
    assert not x.payout_eligible
    x.settle_day(150.0)
    assert x.winning_days == 1, "exactly $150 counts - 'at least $150'"


def test_the_consistency_route_needs_three_days_and_forty_percent():
    x = ts.TopstepAccount(profile=ts.express_funded(50_000, consistency_route=True),
                          stage=ts.TopstepStage.EXPRESS_FUNDED, consistency_route=True)
    x.settle_day(1_000.0)
    x.settle_day(1_000.0)
    assert not x.payout_eligible, "two days is not three"
    x.settle_day(1_000.0)
    assert x.payout_eligible                    # best day 33% of 3,000
    y = ts.TopstepAccount(profile=ts.express_funded(50_000, consistency_route=True),
                          stage=ts.TopstepStage.EXPRESS_FUNDED, consistency_route=True)
    for d in (2_000.0, 500.0, 500.0):
        y.settle_day(d)
    assert not y.payout_eligible, "best day 67% of total must block the consistency route"


def test_a_payout_is_capped_at_half_the_balance_and_the_route_ceiling():
    x = ts.TopstepAccount(profile=ts.express_funded(50_000),
                          stage=ts.TopstepStage.EXPRESS_FUNDED)
    for _ in range(5):
        x.settle_day(400.0)                     # balance 2,000
    assert x.payout_cap == 1_000.0
    x2 = ts.TopstepAccount(profile=ts.express_funded(50_000),
                           stage=ts.TopstepStage.EXPRESS_FUNDED)
    for _ in range(5):
        x2.settle_day(4_000.0)                  # balance 20,000; half is 10,000
    assert x2.payout_cap == 5_000.0, "the standard route caps at $5,000"
    x3 = ts.TopstepAccount(profile=ts.express_funded(50_000, consistency_route=True),
                           stage=ts.TopstepStage.EXPRESS_FUNDED, consistency_route=True)
    for _ in range(5):
        x3.settle_day(4_000.0)
    assert x3.payout_cap == 6_000.0, "the consistency route caps at $6,000"


def test_a_payout_resets_the_winning_day_count_and_the_daily_series():
    x = ts.TopstepAccount(profile=ts.express_funded(50_000),
                          stage=ts.TopstepStage.EXPRESS_FUNDED)
    for _ in range(5):
        x.settle_day(400.0)
    x.advance()
    paid = x.take_payout()
    assert paid == 1_000.0
    assert x.winning_days == 0 and x.daily_pnl == []
    assert x.payouts_taken == 1 and x.total_paid_out == 1_000.0
    assert x.stage is ts.TopstepStage.EXPRESS_FUNDED
    assert not x.payout_eligible


def test_a_payout_shrinks_the_buffer_because_the_mll_does_not_follow_it_down():
    """The reason a payout is a risk decision, not a cash transfer."""
    x = ts.TopstepAccount(profile=ts.express_funded(50_000),
                          stage=ts.TopstepStage.EXPRESS_FUNDED)
    for _ in range(5):
        x.settle_day(400.0)                     # balance 2,000, MLL locked at 0
    before = x.distance_to_mll
    x.advance()
    x.take_payout()
    assert x.distance_to_mll == before - 1_000.0
    assert x.mll == 0.0, "withdrawing must not lower the floor"


def test_an_ineligible_payout_pays_nothing_and_changes_nothing():
    x = ts.TopstepAccount(profile=ts.express_funded(50_000),
                          stage=ts.TopstepStage.EXPRESS_FUNDED)
    x.settle_day(400.0)
    assert x.take_payout() == 0.0
    assert x.payouts_taken == 0 and x.balance == 400.0


def test_partial_payouts_are_honoured_and_capped():
    x = ts.TopstepAccount(profile=ts.express_funded(50_000),
                          stage=ts.TopstepStage.EXPRESS_FUNDED)
    for _ in range(5):
        x.settle_day(400.0)
    x.advance()
    assert x.take_payout(250.0) == 250.0
    assert x.balance == 1_750.0


def test_payout_eligibility_is_lost_and_regained():
    x = ts.TopstepAccount(profile=ts.express_funded(50_000),
                          stage=ts.TopstepStage.EXPRESS_FUNDED)
    for _ in range(5):
        x.settle_day(400.0)
    assert x.advance() is ts.TopstepStage.PAYOUT_ELIGIBLE
    x.take_payout()
    assert x.advance() is ts.TopstepStage.EXPRESS_FUNDED
    for _ in range(5):
        x.settle_day(400.0)
    assert x.advance() is ts.TopstepStage.PAYOUT_ELIGIBLE


def test_going_live_is_an_external_decision_never_a_threshold():
    x = ts.TopstepAccount(profile=ts.express_funded(50_000),
                          stage=ts.TopstepStage.EXPRESS_FUNDED)
    for _ in range(40):
        x.settle_day(1_000.0)
    for _ in range(5):
        assert x.advance() is not ts.TopstepStage.LIVE_FUNDED, (
            "no amount of profit may promote an account to live")
    assert x.promote_to_live() is ts.TopstepStage.LIVE_FUNDED


def test_a_combine_account_cannot_be_promoted_to_live():
    a = ts.TopstepAccount(profile=ts.combine(50_000, profit_target=3_000.0))
    with pytest.raises(ValueError):
        a.promote_to_live()


def test_stage_predicates():
    assert ts.TopstepStage.LIQUIDATED.is_terminal
    assert ts.TopstepStage.FAILED.is_terminal
    assert not ts.TopstepStage.EXPRESS_FUNDED.is_terminal
    assert ts.TopstepStage.EXPRESS_FUNDED.is_funded
    assert ts.TopstepStage.PAYOUT_ELIGIBLE.is_funded
    assert ts.TopstepStage.LIVE_FUNDED.is_funded
    assert not ts.TopstepStage.TRADING_COMBINE.is_funded


def test_a_combine_account_is_never_payout_eligible():
    a = ts.TopstepAccount(profile=ts.combine(50_000, profit_target=3_000.0))
    for _ in range(10):
        a.settle_day(500.0)
    assert not a.payout_eligible, "an evaluation does not pay out"


# ======================================================================================
# SIZING AND THE SCALING GAP
# ======================================================================================

def test_the_scaling_plan_is_recorded_as_a_gap_not_assumed_away():
    assert ts.XFA_SCALING.confidence is ts.Confidence.OWNER
    assert ts.express_funded(50_000).scaling == ()
    assert "rungs were not published" in ts.XFA_SCALING.note


def test_a_supplied_scaling_ladder_is_honoured():
    ladder = ((0.0, 2), (500.0, 5), (1_500.0, 10))
    p = ts.express_funded(50_000, scaling=ladder)
    x = ts.TopstepAccount(profile=p, stage=ts.TopstepStage.EXPRESS_FUNDED)
    assert x.contracts_allowed == 2
    x.settle_day(600.0)
    assert x.contracts_allowed == 5
    x.settle_day(1_000.0)
    assert x.contracts_allowed == 10


def test_without_a_ladder_the_flat_cap_applies():
    a = ts.TopstepAccount(profile=ts.combine(50_000, profit_target=3_000.0))
    assert a.contracts_allowed == 50


# ======================================================================================
# THE READY-MADE PROFILES
# ======================================================================================

def test_profiles_covers_every_size_and_route():
    p = ts.profiles()
    assert len(p) == len(ts.SIZES) * 3
    for size in ts.SIZES:
        k = size // 1000
        assert p[f"combine_{k}k"].max_drawdown == ts.MLL[size].value
        assert p[f"xfa_{k}k"].starting_balance == 0.0
        assert p[f"xfa_{k}k_consistency"].max_single_day_profit_share == 0.40


def test_profiles_refuses_the_unverified_target_when_told_to():
    with pytest.raises(ts.UnverifiedRule):
        ts.profiles(allow_unverified_target=False)


def test_every_profile_round_trips_through_json():
    for name, p in ts.profiles().items():
        back = PropFirmProfile.from_dict(json.loads(p.to_json()))
        assert back == p, f"{name} did not survive a round trip"


def test_describe_is_readable_and_shows_the_lock():
    a = ts.TopstepAccount(profile=ts.combine(50_000, profit_target=3_000.0))
    assert "trading_combine" in a.describe()
    a.settle_day(2_500.0)
    assert a.mll_locked and "L" in a.describe()
