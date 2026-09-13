"""Adversarial tests for the champion/challenger promotion gate.

The gate is the last thing between a plausible backtest and a funded account, so these tests
are written as attacks rather than as demonstrations. Each one is something a person under
deadline pressure - or an unattended agent optimising for "made progress" - would genuinely
try: promote on the score, skip a rung, quote a stale verdict from before the search grew,
look at the holdout twice, ride on another candidate's holdout look, compare a py311 number
against a py314 one, tie with the champion and call it a win, hand in a pass rate as a
percentage so it clears every floor.

Every attempt below is asserted to fail. The two tests that assert something PASSES exist to
keep the rest honest: a fixture that failed for an unrelated reason would make thirty
refusals pass while proving nothing.

Nothing here touches `research/experiments.jsonl` or the real holdout ledger; every ledger is
carved out of `tmp_path`.
"""
from __future__ import annotations

import dataclasses
import inspect

import numpy as np
import pytest

from quant_brain.core.provenance import Provenance
from quant_brain.core.validation import LeakageError, make_holdout
from quant_brain.research.promotion import (
    ADVISORY_CHECKS,
    CHECKS_BY_RUNG,
    CORE_CHECKS,
    Check,
    Decision,
    EnvironmentMismatch,
    Evidence,
    PromotionGate,
    PromotionRefused,
    Rules,
    refuse_cross_environment,
)
from quant_brain.research.registry import Candidate, Experiment, Ledger, Stage

FAMILY = "futures.momentum"


# ------------------------------------------------------------------------------ fixtures

def prov(*, py: str = "3.11.9", pandas: str = "2.2.3", numpy_v: str = "2.4.6",
         commit: str = "0" * 40, dirty: bool = False) -> Provenance:
    return Provenance(python_version=py, git_commit=commit, git_dirty=dirty,
                      dependencies={"pandas": pandas, "numpy": numpy_v})


@pytest.fixture
def ledger(tmp_path):
    return Ledger(tmp_path / "experiments.jsonl")


@pytest.fixture
def gate(ledger):
    return PromotionGate(ledger)


@pytest.fixture
def holdout(tmp_path):
    data = np.linspace(-1.0, 1.0, 500)
    return make_holdout(data, fraction=0.2, ledger_path=tmp_path / "holdout.jsonl",
                        label="ES-2016-2026")


def seeded_experiment(ledger: Ledger, *, others: int = 20) -> Experiment:
    """A survivor of a 21-experiment family, with a verdict taken at the full trial count."""
    for i in range(others):
        ledger.record(Experiment(hypothesis=f"rejected idea {i}", family=FAMILY,
                                 params={"i": i}))
    exp = Experiment(hypothesis="the survivor", family=FAMILY, params={"w": 3})
    ledger.record(exp)
    series = np.random.default_rng(0).normal(0.30, 1.0, size=400)
    exp.verdict = ledger.verdict(exp, series, horizon=1)
    return exp


@pytest.fixture
def ev(ledger, gate, holdout):
    """A candidate at PAPER with every condition satisfied, holdout already spent once."""
    exp = seeded_experiment(ledger)
    cand = Candidate(candidate_id="C-1", experiment_id=exp.experiment_id, stage=Stage.PAPER)
    champ = Candidate(candidate_id="CHAMP-0", experiment_id="old", stage=Stage.CHAMPION)
    e = Evidence(
        candidate=cand, experiment=exp, provenance=prov(),
        fold_scores=[0.020, 0.010, -0.005, 0.030, 0.015],
        topstep_pass_rate=0.52, gross_profit=100_000.0, costs=25_000.0,
        holdout=holdout, score=1.25,
        champion=champ, champion_provenance=prov(), champion_score=1.00,
    )
    gate.spend_holdout(e, result={"passed": True, "t": 3.4},
                       note="final holdout for C-1 before the champion seat")
    return e


# ============================================================================
# THE BASELINE. If these two disagree the other thirty prove nothing.
# ============================================================================

def test_a_fully_evidenced_challenger_takes_the_champion_seat(gate, ev):
    d = gate.decide(ev, to=Stage.CHAMPION)
    assert d.promoted, d.describe()
    assert {c.name for c in d.checks if c.required} == set(CHECKS_BY_RUNG[Stage.CHAMPION])


def test_the_fixture_is_discriminating(gate, ev):
    """One condition broken must be enough. Otherwise the gate is decorative."""
    weakened = dataclasses.replace(ev, topstep_pass_rate=0.05)
    assert not gate.decide(weakened, to=Stage.CHAMPION).promoted


# ============================================================================
# PROMOTION ON THE SCORE ALONE
# ============================================================================

def test_the_best_score_in_the_world_does_not_promote_a_failing_candidate(gate, ev):
    """The attack the module exists for: a huge margin over the champion, nothing else."""
    broken = dataclasses.replace(ev, score=99.0, topstep_pass_rate=0.01,
                                 fold_scores=[-1.0, -1.0, -1.0, 2.0, -1.0],
                                 gross_profit=10.0, costs=9.0)
    d = gate.decide(broken, to=Stage.CHAMPION)
    assert not d.promoted
    assert {c.name for c in d.failures} == {"topstep", "walk_forward", "costs"}
    beat = next(c for c in d.checks if c.name == "beats_champion")
    assert beat.passed, "the challenger really does out-score the champion; that is not enough"


def test_there_is_no_keyword_that_forces_a_promotion(gate):
    forbidden = {"force", "override", "skip", "ignore", "score", "best", "rank"}
    for fn in (PromotionGate.decide, PromotionGate.apply, PromotionGate.spend_holdout):
        leaked = forbidden & set(inspect.signature(fn).parameters)
        assert not leaked, f"{fn.__qualname__} exposes {leaked}"


def test_the_gate_never_answers_with_a_bare_boolean(gate, ev):
    d = gate.decide(ev, to=Stage.CHAMPION)
    assert isinstance(d, Decision)
    assert len(d.checks) >= len(CORE_CHECKS) + 2
    assert all(isinstance(c, Check) and c.detail.strip() for c in d.checks)
    assert "PROMOTE" in d.describe() and "ladder" in d.describe()


def test_a_decision_cannot_be_edited_into_a_promotion(gate, ev):
    d = gate.decide(dataclasses.replace(ev, topstep_pass_rate=0.0), to=Stage.CHAMPION)
    assert not d.promoted
    with pytest.raises(dataclasses.FrozenInstanceError):
        d.checks = ()                                                   # type: ignore[misc]
    with pytest.raises(AttributeError):
        d.promoted = True                                               # type: ignore[misc]
    with pytest.raises(AttributeError):
        d.checks.append(Check("invented", True, "looks fine to me"))    # type: ignore[attr-defined]


# ============================================================================
# SKIPPING A RUNG
# ============================================================================

def test_a_validation_candidate_cannot_jump_to_champion(gate, ev):
    ev.candidate.stage = Stage.VALIDATION
    d = gate.decide(ev, to=Stage.CHAMPION)
    assert not d.promoted
    assert [c.name for c in d.failures] == ["ladder"]
    assert "skips a rung" in d.failures[0].detail


def test_apply_refuses_a_failing_decision(gate, ev):
    ev.candidate.stage = Stage.VALIDATION
    d = gate.decide(ev, to=Stage.CHAMPION)
    with pytest.raises(PromotionRefused):
        gate.apply(ev, d)
    assert ev.candidate.stage is Stage.VALIDATION


def test_one_decision_cannot_be_applied_twice(gate, ev):
    d = gate.decide(ev, to=Stage.CHAMPION)
    gate.apply(ev, d)
    assert ev.candidate.stage is Stage.CHAMPION
    with pytest.raises(PromotionRefused, match="stale decision"):
        gate.apply(ev, d)


def test_a_decision_cannot_be_applied_to_a_different_candidate(gate, ev):
    d = gate.decide(ev, to=Stage.CHAMPION)
    other = dataclasses.replace(
        ev, candidate=Candidate(candidate_id="C-2", experiment_id=ev.experiment.experiment_id,
                                stage=Stage.PAPER))
    with pytest.raises(PromotionRefused, match="C-1"):
        gate.apply(other, d)


def test_the_rungs_are_cumulative():
    """A refactor that drops a condition from a higher rung is the shape of the next defect."""
    order = [Stage.VALIDATION, Stage.CHALLENGER, Stage.PAPER, Stage.CHAMPION]
    for lower, higher in zip(order, order[1:], strict=False):
        assert set(CHECKS_BY_RUNG[lower]) <= set(CHECKS_BY_RUNG[higher]), (
            f"{higher.value} requires less than {lower.value}")
    for rung, names in CHECKS_BY_RUNG.items():
        assert set(CORE_CHECKS) <= set(names), rung
        assert not set(ADVISORY_CHECKS) & set(names), "an advisory must never block"


def test_rejection_is_not_the_gates_business(gate, ev):
    with pytest.raises(ValueError, match="advance"):
        gate.decide(ev, to=Stage.REJECTED)
    with pytest.raises(ValueError):
        gate.decide(ev, to=Stage.RESEARCH)


# ============================================================================
# THE STATISTICAL CONDITION AND ITS TRIAL COUNT
# ============================================================================

def test_a_verdict_taken_before_the_search_grew_is_refused(gate, ledger, ev):
    """The ordinary way a search launders its multiplicity: promote on the early PASS."""
    for i in range(200, 400):
        ledger.record(Experiment(hypothesis=f"later idea {i}", family=FAMILY, params={"i": i}))
    d = gate.decide(ev, to=Stage.CHAMPION)
    stat = next(c for c in d.checks if c.name == "statistical")
    assert not stat.passed and not d.promoted
    assert "now holds 221" in stat.detail


def test_a_failed_verdict_cannot_be_promoted(gate, ledger, ev):
    noise = np.random.default_rng(7).normal(0.0, 1.0, size=400)
    ev.experiment.verdict = ledger.verdict(ev.experiment, noise, horizon=1)
    assert not ev.experiment.verdict.passed
    d = gate.decide(ev, to=Stage.CHAMPION)
    assert not d.promoted and [c.name for c in d.failures] == ["statistical"]


def test_a_candidate_with_no_verdict_at_all_is_refused(gate, ev):
    ev.experiment.verdict = None
    d = gate.decide(ev, to=Stage.CHAMPION)
    assert not d.promoted
    assert "has not been tested" in next(c for c in d.failures if c.name == "statistical").detail


# ============================================================================
# THE WRITE-ONCE HOLDOUT
# ============================================================================

def test_the_holdout_refuses_a_second_look(gate, ev):
    with pytest.raises(LeakageError):
        gate.spend_holdout(ev, result={"passed": True}, note="just one more")


def test_spend_holdout_offers_no_way_to_force_a_second_look():
    """`Holdout.spend` has force for a human decision; the promotion path must not."""
    assert "force" not in inspect.signature(PromotionGate.spend_holdout).parameters


def test_a_forced_second_look_burns_the_holdout_for_promotion(gate, ev):
    """Going around the gate to `Holdout.spend(force=True)` is detected, not rewarded."""
    assert ev.holdout is not None
    ev.holdout.spend(result={"passed": True, "candidate_id": "C-1"},
                     note="second look, this time it worked", force=True)
    d = gate.decide(ev, to=Stage.CHAMPION)
    hold = next(c for c in d.checks if c.name == "holdout")
    assert not hold.passed and not d.promoted
    assert "evaluated 2 times" in hold.detail


def test_a_candidate_cannot_ride_on_another_candidates_holdout_look(gate, ledger, holdout):
    """A small variation of the candidate that spent the holdout has no evidence of its own."""
    exp = seeded_experiment(ledger)
    first = Evidence(candidate=Candidate(candidate_id="C-1", experiment_id=exp.experiment_id,
                                         stage=Stage.VALIDATION),
                     experiment=exp, provenance=prov(), holdout=holdout,
                     fold_scores=[0.02, 0.01, 0.03, 0.01, 0.02], topstep_pass_rate=0.5,
                     gross_profit=100_000.0, costs=20_000.0)
    gate.spend_holdout(first, result={"passed": True}, note="final look for C-1")

    twin = dataclasses.replace(
        first, candidate=Candidate(candidate_id="C-1b", experiment_id=exp.experiment_id,
                                   stage=Stage.VALIDATION))
    d = gate.decide(twin, to=Stage.CHALLENGER)
    hold = next(c for c in d.checks if c.name == "holdout")
    assert not hold.passed and "'C-1'" in hold.detail
    assert gate.decide(first, to=Stage.CHALLENGER).promoted, "the owner still passes"


def test_an_unspent_holdout_cannot_reach_challenger(gate, ledger, holdout):
    exp = seeded_experiment(ledger)
    e = Evidence(candidate=Candidate(candidate_id="C-9", experiment_id=exp.experiment_id,
                                     stage=Stage.VALIDATION),
                 experiment=exp, provenance=prov(), holdout=holdout,
                 fold_scores=[0.02, 0.01, 0.03, 0.01, 0.02], topstep_pass_rate=0.5,
                 gross_profit=100_000.0, costs=20_000.0)
    d = gate.decide(e, to=Stage.CHALLENGER)
    assert not d.promoted
    assert "never been evaluated" in next(c for c in d.failures if c.name == "holdout").detail


def test_a_missing_holdout_fails_the_condition_rather_than_skipping_it(gate, ev):
    d = gate.decide(dataclasses.replace(ev, holdout=None), to=Stage.CHAMPION)
    assert not d.promoted and "holdout" in {c.name for c in d.failures}
    with pytest.raises(PromotionRefused):
        gate.spend_holdout(dataclasses.replace(ev, holdout=None), result={"passed": True},
                           note="nowhere to put it")


def test_a_holdout_look_that_failed_cannot_be_read_as_evidence(gate, ledger, holdout):
    exp = seeded_experiment(ledger)
    e = Evidence(candidate=Candidate(candidate_id="C-3", experiment_id=exp.experiment_id,
                                     stage=Stage.VALIDATION),
                 experiment=exp, provenance=prov(), holdout=holdout,
                 fold_scores=[0.02, 0.01, 0.03, 0.01, 0.02], topstep_pass_rate=0.5,
                 gross_profit=100_000.0, costs=20_000.0)
    gate.spend_holdout(e, result={"passed": False, "reason": "t=0.4 out of sample"},
                       note="final look for C-3")
    d = gate.decide(e, to=Stage.CHALLENGER)
    assert not d.promoted
    assert "t=0.4" in next(c for c in d.failures if c.name == "holdout").detail


def test_a_holdout_record_with_no_verdict_field_is_refused(gate, ledger, holdout):
    exp = seeded_experiment(ledger)
    cand = Candidate(candidate_id="C-4", experiment_id=exp.experiment_id,
                     stage=Stage.VALIDATION)
    holdout.spend(result={"candidate_id": "C-4", "sharpe": 1.4}, note="hand-written record")
    e = Evidence(candidate=cand, experiment=exp, provenance=prov(), holdout=holdout,
                 fold_scores=[0.02, 0.01, 0.03, 0.01, 0.02], topstep_pass_rate=0.5,
                 gross_profit=100_000.0, costs=20_000.0)
    d = gate.decide(e, to=Stage.CHALLENGER)
    assert not d.promoted
    assert "no `passed` field" in next(c for c in d.failures if c.name == "holdout").detail


def test_the_holdout_is_not_required_below_challenger(gate, ledger):
    """The funnel spends the holdout on the way to CHALLENGER, not before it."""
    exp = seeded_experiment(ledger)
    e = Evidence(candidate=Candidate(candidate_id="C-5", experiment_id=exp.experiment_id,
                                     stage=Stage.RESEARCH),
                 experiment=exp, provenance=prov(),
                 fold_scores=[0.02, 0.01, 0.03, 0.01, 0.02], topstep_pass_rate=0.5,
                 gross_profit=100_000.0, costs=20_000.0)
    assert gate.decide(e, to=Stage.VALIDATION).promoted
    assert not gate.decide(e, to=Stage.CHALLENGER).promoted


# ============================================================================
# CROSS-ENVIRONMENT COMPARISON
# ============================================================================

def test_comparing_a_py314_challenger_with_a_py311_champion_raises(gate, ev):
    crossed = dataclasses.replace(ev, provenance=prov(py="3.14.1", pandas="3.0.5",
                                                      numpy_v="2.5.3"))
    with pytest.raises(EnvironmentMismatch, match="py314"):
        gate.decide(crossed, to=Stage.CHAMPION)


def test_the_refusal_fires_even_when_every_other_condition_passes(gate, ev):
    """It is not a low score. There is no partial Decision left behind to quote."""
    crossed = dataclasses.replace(ev, champion_provenance=prov(py="3.14.1", pandas="3.0.5"))
    assert gate.decide(ev, to=Stage.CHAMPION).promoted
    with pytest.raises(EnvironmentMismatch):
        gate.decide(crossed, to=Stage.CHAMPION)


def test_a_same_interpreter_but_different_pandas_is_still_a_mismatch(gate, ev):
    """pandas 2.2 -> 3.0 moved copy-on-write and resample; the interpreter alone is not it."""
    crossed = dataclasses.replace(ev, champion_provenance=prov(pandas="3.0.5"))
    with pytest.raises(EnvironmentMismatch):
        gate.decide(crossed, to=Stage.CHAMPION)


def test_an_unrecorded_environment_is_refused_rather_than_assumed_to_match(gate, ev):
    blank = dataclasses.replace(ev, provenance=Provenance(git_commit="a" * 40))
    with pytest.raises(EnvironmentMismatch, match="no interpreter version"):
        gate.decide(blank, to=Stage.CHAMPION)


def test_two_blank_provenances_do_not_match_each_other(gate, ev):
    """The failure mode a naive equality check has: '' == '' and the refusal never fires."""
    blank = Provenance()
    crossed = dataclasses.replace(ev, provenance=blank, champion_provenance=blank)
    with pytest.raises(EnvironmentMismatch):
        gate.decide(crossed, to=Stage.CHAMPION)


def test_the_refusal_applies_at_every_rung_not_only_at_the_champion_seat(gate, ev):
    ev.candidate.stage = Stage.CHALLENGER
    crossed = dataclasses.replace(ev, champion_provenance=prov(py="3.14.1"))
    with pytest.raises(EnvironmentMismatch):
        gate.decide(crossed, to=Stage.PAPER)


def test_the_helper_returns_the_shared_key_when_the_environments_agree():
    key = refuse_cross_environment(prov(), prov(commit="b" * 40), what="unit")
    assert key.startswith("py311-") and key == prov().env_key


def test_the_helper_refuses_a_missing_challenger_provenance():
    with pytest.raises(EnvironmentMismatch, match="no provenance"):
        refuse_cross_environment(None, prov(), what="unit")


# ============================================================================
# BEATING THE CHAMPION, NOT MERELY PASSING
# ============================================================================

def test_a_tie_does_not_take_the_seat(gate, ev):
    d = gate.decide(dataclasses.replace(ev, score=1.00), to=Stage.CHAMPION)
    beat = next(c for c in d.checks if c.name == "beats_champion")
    assert not d.promoted and not beat.passed and "a tie is not a win" in beat.detail


def test_a_worse_challenger_that_passes_everything_else_still_loses(gate, ev):
    d = gate.decide(dataclasses.replace(ev, score=0.80), to=Stage.CHAMPION)
    assert not d.promoted and [c.name for c in d.failures] == ["beats_champion"]


def test_a_margin_floor_can_be_raised_without_touching_the_gate(gate, ledger, ev):
    strict = PromotionGate(ledger, Rules(min_beat_margin=0.50))
    assert gate.decide(ev, to=Stage.CHAMPION).promoted
    assert not strict.decide(ev, to=Stage.CHAMPION).promoted


def test_an_incumbent_with_no_comparable_score_blocks_rather_than_waves_through(gate, ev):
    d = gate.decide(dataclasses.replace(ev, champion_score=None), to=Stage.CHAMPION)
    assert not d.promoted and [c.name for c in d.failures] == ["beats_champion"]
    d = gate.decide(dataclasses.replace(ev, score=float("nan")), to=Stage.CHAMPION)
    assert not d.promoted


def test_the_first_champion_needs_no_comparison_but_needs_everything_else(gate, ev):
    first = dataclasses.replace(ev, champion=None, champion_provenance=None,
                                champion_score=None, score=None)
    assert gate.decide(first, to=Stage.CHAMPION).promoted
    weak = dataclasses.replace(first, costs=90_000.0)
    assert not gate.decide(weak, to=Stage.CHAMPION).promoted


def test_the_comparison_is_not_consulted_below_the_champion_seat(gate, ev):
    ev.candidate.stage = Stage.CHALLENGER
    d = gate.decide(dataclasses.replace(ev, score=0.01), to=Stage.PAPER)
    assert d.promoted and "beats_champion" not in {c.name for c in d.checks}


# ============================================================================
# COSTS, TOPSTEP SURVIVAL, WALK-FORWARD
# ============================================================================

def test_costs_above_the_share_of_gross_are_refused(gate, ev):
    d = gate.decide(dataclasses.replace(ev, costs=60_000.0), to=Stage.CHAMPION)
    assert not d.promoted
    assert "60.0% of gross" in next(c for c in d.failures if c.name == "costs").detail


def test_zero_gross_with_zero_costs_does_not_read_as_a_zero_percent_share(gate, ev):
    d = gate.decide(dataclasses.replace(ev, gross_profit=0.0, costs=0.0), to=Stage.CHAMPION)
    assert not d.promoted and "no gross edge" in next(
        c for c in d.failures if c.name == "costs").detail


def test_negative_costs_are_a_modelling_error_not_a_free_pass(gate, ev):
    d = gate.decide(dataclasses.replace(ev, costs=-5_000.0), to=Stage.CHAMPION)
    assert not d.promoted and "negative cost" in next(
        c for c in d.failures if c.name == "costs").detail


def test_missing_cost_numbers_fail_rather_than_skip(gate, ev):
    for kw in ({"costs": None}, {"gross_profit": None}, {"costs": None, "gross_profit": None}):
        d = gate.decide(dataclasses.replace(ev, **kw), to=Stage.CHAMPION)
        assert not d.promoted, kw
        assert "costs" in {c.name for c in d.failures}


def test_topstep_survival_below_the_floor_is_refused(gate, ev):
    d = gate.decide(dataclasses.replace(ev, topstep_pass_rate=0.20), to=Stage.CHAMPION)
    assert not d.promoted and "20.0%" in next(
        c for c in d.failures if c.name == "topstep").detail


def test_a_pass_rate_handed_in_as_a_percentage_is_caught_not_waved_through(gate, ev):
    """45.0 would clear a 0.35 floor by a factor of 128. This is a real unit slip."""
    d = gate.decide(dataclasses.replace(ev, topstep_pass_rate=45.0), to=Stage.CHAMPION)
    assert not d.promoted
    assert "not a fraction" in next(c for c in d.failures if c.name == "topstep").detail


def test_a_missing_pass_rate_fails(gate, ev):
    d = gate.decide(dataclasses.replace(ev, topstep_pass_rate=None), to=Stage.CHAMPION)
    assert not d.promoted and "topstep" in {c.name for c in d.failures}


def test_a_minority_of_positive_folds_is_refused(gate, ev):
    d = gate.decide(dataclasses.replace(ev, fold_scores=[0.02, -0.01, -0.02, 0.01, -0.03]),
                    to=Stage.CHAMPION)
    assert not d.promoted
    assert "2/5 folds positive" in next(c for c in d.failures if c.name == "walk_forward").detail


def test_one_enormous_fold_cannot_carry_four_losers(gate, ev):
    """The mean is strongly positive and the strategy worked exactly once."""
    d = gate.decide(dataclasses.replace(ev, fold_scores=[-0.01, -0.01, -0.01, 5.0, -0.01]),
                    to=Stage.CHAMPION)
    assert not d.promoted and "walk_forward" in {c.name for c in d.failures}


def test_a_majority_of_tiny_wins_under_one_large_loss_is_not_an_edge(gate, ev):
    d = gate.decide(dataclasses.replace(ev, fold_scores=[0.001, 0.001, 0.001, 0.001, -1.0]),
                    to=Stage.CHAMPION)
    assert not d.promoted and "walk_forward" in {c.name for c in d.failures}


def test_too_few_folds_to_speak_of_a_majority(gate, ev):
    d = gate.decide(dataclasses.replace(ev, fold_scores=[0.05, 0.05]), to=Stage.CHAMPION)
    assert not d.promoted
    assert "below the 4" in next(c for c in d.failures if c.name == "walk_forward").detail


def test_a_nan_fold_is_a_fold_that_did_not_run(gate, ev):
    d = gate.decide(dataclasses.replace(ev, fold_scores=[0.02, float("nan"), 0.03, 0.01, 0.02]),
                    to=Stage.CHAMPION)
    assert not d.promoted
    assert "non-finite" in next(c for c in d.failures if c.name == "walk_forward").detail


# ============================================================================
# THE ADVISORY TIER
# ============================================================================

def test_a_dirty_tree_is_reported_on_every_decision_and_blocks_nothing(gate, ev):
    dirty = dataclasses.replace(ev, provenance=prov(dirty=True),
                                champion_provenance=prov(dirty=True))
    d = gate.decide(dirty, to=Stage.CHAMPION)
    assert d.promoted, "making reproducibility blocking would switch the gate off"
    assert [c.name for c in d.warnings] == ["reproducible"]
    assert "dirty working tree" in d.warnings[0].detail
    assert "advisory: reproducible" in d.reason()


def test_the_advisory_is_never_counted_among_the_required_conditions(gate, ev):
    d = gate.decide(ev, to=Stage.CHAMPION)
    advisory = next(c for c in d.checks if c.name in ADVISORY_CHECKS)
    assert not advisory.required
    assert advisory.name not in {c.name for c in d.failures}


# ============================================================================
# THE RECORD A PROMOTION LEAVES BEHIND
# ============================================================================

def test_a_promotion_writes_its_reasons_into_the_candidate_history(gate, ev):
    d = gate.decide(ev, to=Stage.CHAMPION)
    cand = gate.apply(ev, d)
    assert cand.stage is Stage.CHAMPION
    move, why = cand.history[-1]
    assert move == "paper->champion"
    for name in CHECKS_BY_RUNG[Stage.CHAMPION]:
        assert name in why


def test_a_refusal_serialises_with_every_condition_intact(gate, ev):
    d = gate.decide(dataclasses.replace(ev, costs=99_000.0), to=Stage.CHAMPION)
    blob = d.to_dict()
    assert blob["promoted"] is False and blob["to_stage"] == "champion"
    assert blob["env_key"].startswith("py311-")
    assert {c["name"] for c in blob["checks"]} == set(CHECKS_BY_RUNG[Stage.CHAMPION]) | set(
        ADVISORY_CHECKS)
    assert "REFUSED" in blob["reason"] and "costs" in blob["reason"]
