"""Frozen specs, the account rules, and the execution ladder.

The theme is that an assumption must be impossible to change without leaving a trace: a
parameter move changes the spec hash, a consistency-rate change changes the account profile
id, and a slippage change changes the execution profile id. Every one of those flows into
the run id.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
from decimal import Decimal

import pytest

from topstep_backtester.profiles import account, execution
from topstep_backtester.strategies.spec import Ambiguity, FrozenStrategySpec, SpecError

BASE = {
    "name": "example",
    "version": "1.0.0",
    "instrument": "ES",
    "bar_interval": "5min",
    "session_window": "09:30-16:00 ET",
    "entry_rules": ("enter on a thing",),
    "exit_rules": ("leave on another thing",),
    "risk_rules": ("one contract",),
    "parameters": {"threshold": 10.0, "cap": 2},
}


def spec(**overrides) -> FrozenStrategySpec:
    return FrozenStrategySpec(**{**BASE, **overrides})


# ======================================================================================
# identity
# ======================================================================================


def test_the_hash_covers_the_parameters() -> None:
    a = spec()
    b = spec(parameters={"threshold": 10.5, "cap": 2})
    assert a.spec_hash != b.spec_hash, (
        "moving a threshold left the identity unchanged; a tuned strategy could then be "
        "reported against the untuned one's evidence"
    )


def test_the_hash_covers_the_rules() -> None:
    assert spec().spec_hash != spec(entry_rules=("enter on a different thing",)).spec_hash


def test_the_hash_covers_the_instrument_and_timeframe() -> None:
    assert spec().spec_hash != spec(instrument="NQ").spec_hash
    assert spec().spec_hash != spec(bar_interval="1min").spec_hash


def test_the_hash_ignores_provenance() -> None:
    """Two identical experiments are the same experiment, whoever froze them and when.

    If the timestamp were in the hash, re-freezing would look like a new strategy and the
    hash would be useless for answering "have we already tested this".
    """
    when = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    a = spec().freeze(author="alice", at=when)
    b = spec().freeze(author="bob", at=when + dt.timedelta(days=30))
    assert a.spec_hash == b.spec_hash
    assert a.author != b.author and a.frozen_at != b.frozen_at


def test_the_hash_is_stable_across_parameter_ordering() -> None:
    a = spec(parameters={"threshold": 10.0, "cap": 2})
    b = spec(parameters={"cap": 2, "threshold": 10.0})
    assert a.spec_hash == b.spec_hash


def test_float_parameters_hash_reproducibly() -> None:
    """repr, not str, so 0.1 hashes the same way on every platform."""
    assert spec(parameters={"x": 0.1}).spec_hash == spec(parameters={"x": 0.1}).spec_hash


# ======================================================================================
# the gates
# ======================================================================================


def test_a_spec_with_no_entry_rule_is_refused() -> None:
    with pytest.raises(SpecError, match="no entry rules"):
        spec(entry_rules=())


def test_a_spec_with_no_exit_rule_is_refused() -> None:
    with pytest.raises(SpecError, match="no exit rules"):
        spec(exit_rules=())


def test_an_unfrozen_spec_cannot_run() -> None:
    with pytest.raises(SpecError, match="not frozen"):
        spec().assert_runnable()


def test_a_spec_with_an_unresolved_ambiguity_cannot_be_frozen() -> None:
    """Deciding a reading after seeing results is choosing the reading that won."""
    open_question = Ambiguity(
        ref="A1", question="which close?", reading_taken="", authority="",
        material=True, resolved=False,
    )
    with pytest.raises(SpecError, match="unresolved ambiguit"):
        spec(ambiguities=(open_question,)).freeze(author="someone")


def test_a_resolved_ambiguity_register_permits_freezing() -> None:
    resolved = Ambiguity(
        ref="A1", question="which close?", reading_taken="the bucket close",
        authority="the written spec, literally", material=True,
    )
    frozen = spec(ambiguities=(resolved,)).freeze(author="someone")
    assert frozen.is_frozen
    assert frozen.unresolved() == ()
    assert frozen.material_ambiguities() == (resolved,)


def test_the_reading_taken_is_part_of_the_identity() -> None:
    """Two runs that resolved the same ambiguity differently are different experiments."""
    one = spec(ambiguities=(Ambiguity("A1", "q", "reading one", "auth", True),))
    two = spec(ambiguities=(Ambiguity("A1", "q", "reading two", "auth", True),))
    assert one.spec_hash != two.spec_hash


def test_parameters_cannot_be_mutated_after_construction() -> None:
    frozen = spec()
    with pytest.raises(TypeError):
        frozen.parameters["threshold"] = 99  # type: ignore[index]


# ======================================================================================
# the account profile
# ======================================================================================


def test_the_default_profile_uses_upstreams_own_numbers() -> None:
    params = account.TOPSTEP_50K_COMBINE.params()
    assert params.starting_balance == Decimal("50000")
    assert params.profit_target == Decimal("3000")
    assert params.mll_buffer == Decimal("2000")
    assert params.dll is None


def test_the_default_consistency_reading_is_the_stricter_one() -> None:
    """Upstream says 0.50, this repository's rulebook says 0.55. We default to the harder.

    A lower percentage caps the best day LOWER at a given profit, so defaulting to 0.50
    means the divergence between the two sources cannot flatter a result.
    """
    strict = account.TOPSTEP_50K_COMBINE.consistency_pct
    documented = account.TOPSTEP_50K_COMBINE_DOC_CONSISTENCY.consistency_pct
    assert strict == Decimal("0.5")
    assert documented == Decimal("0.55")
    assert strict < documented
    profit = Decimal("3000")
    assert (
        account.TOPSTEP_50K_COMBINE.best_day_cap(profit)
        < account.TOPSTEP_50K_COMBINE_DOC_CONSISTENCY.best_day_cap(profit)
    )


def test_passing_is_not_merely_making_the_target() -> None:
    """One big day does not pass, and the profile can say how big is too big."""
    profile = account.TOPSTEP_50K_COMBINE
    assert profile.best_day_cap(Decimal("3000")) == Decimal("1500.0")
    #: a single $3,100 day would have to be at most half the total, so it needs $6,200
    assert profile.minimum_profit_for_best_day(Decimal("3100")) == Decimal("6200")


def test_the_override_goes_through_upstreams_own_configuration_surface() -> None:
    """Not a patch and not a recalculation - the kernel still enforces the rule."""
    params = account.TOPSTEP_50K_COMBINE_DOC_CONSISTENCY.params()
    assert params.consistency_pct == Decimal("0.55")
    assert params.starting_balance == Decimal("50000")
    assert params.profit_target == Decimal("3000")


def test_every_profile_states_the_basis_for_its_consistency_rate() -> None:
    for profile in account.PROFILES.values():
        assert profile.consistency_basis.strip(), f"{profile.profile_id} has no stated basis"


def test_an_unknown_account_profile_is_refused() -> None:
    with pytest.raises(KeyError, match="unknown account profile"):
        account.get_profile("TOPSTEP_5M_COMBINE/v9")


# ======================================================================================
# the execution ladder
# ======================================================================================


def test_the_ladder_is_monotonic_in_adversity() -> None:
    stops = [p.stop_slippage_ticks for p in execution.LADDER]
    markets = [p.market_slippage_ticks for p in execution.LADDER]
    assert stops == sorted(stops), "the ladder must get strictly harder, never easier"
    assert markets == sorted(markets)
    assert stops[0] == 0 and markets[0] == 0, "IDEAL must be the frictionless bound"


def test_limits_never_fill_on_a_touch_at_any_rung() -> None:
    """True would improve every backtest in this pipeline and justify none of them."""
    for profile in execution.LADDER:
        assert profile.fill_limit_on_touch is False, profile.profile_id


def test_the_quoted_rung_is_not_the_frictionless_one() -> None:
    assert execution.QUOTED_RUNG is execution.BASELINE
    assert execution.QUOTED_RUNG is not execution.IDEAL
    assert execution.QUOTED_RUNG.stop_slippage_ticks > 0


def test_every_rung_names_its_fee_source() -> None:
    for profile in execution.LADDER:
        assert profile.fee_source.strip(), f"{profile.profile_id} does not say where fees came from"


def test_the_fee_model_is_explicit_and_nonzero() -> None:
    """Three different ES round-turn costs are in reach; a profile must resolve to one."""
    cost = execution.BASELINE.round_turn_cost("ES")
    assert cost > 0
    assert cost == Decimal("3.80"), (
        "upstream's default ES round turn changed; this repository also carries $3.78 and "
        "an earlier frozen spec used $4.14, so the divergence must be re-examined rather "
        "than the expectation updated"
    )


def test_an_unknown_execution_profile_is_refused() -> None:
    with pytest.raises(KeyError, match="the ladder is"):
        execution.get_profile("GENEROUS/v1")


def test_profiles_serialise_everything_a_reader_needs() -> None:
    payload = execution.BASELINE.as_dict()
    assert payload["stop_slippage_ticks"] == 1
    assert payload["fill_limit_on_touch"] is False
    assert payload["fee_source"]
    account_payload = account.TOPSTEP_50K_COMBINE.as_dict()
    assert account_payload["consistency_pct"] == "0.5"
    assert account_payload["consistency_basis"]


def test_a_spec_can_be_replaced_for_testing_without_mutating_the_original() -> None:
    original = spec()
    moved = dataclasses.replace(original, parameters={"threshold": 11.0, "cap": 2})
    assert original.parameters["threshold"] == 10.0
    assert moved.spec_hash != original.spec_hash
