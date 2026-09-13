"""Tests for the experiment ledger, trial accounting and the promotion ladder.

Most of these are adversarial rather than functional. The module's whole purpose is to be
hard to fool, so the tests try to fool it: understate the trial count, launder multiplicity
by re-running, skip a rung of the ladder, quietly forget a rejection. Each of those is a
thing a person under deadline pressure would genuinely attempt.
"""
from __future__ import annotations

import inspect
import json

import numpy as np
import pytest

from quant_brain.research import Candidate, Experiment, Ledger, Stage
from quant_brain.research.registry import ALLOWED, Verdict


@pytest.fixture
def ledger(tmp_path):
    return Ledger(tmp_path / "experiments.jsonl")


@pytest.fixture
def strong():
    return np.random.default_rng(0).normal(0.30, 1.0, size=400)


def _exp(n=0, family="futures.momentum"):
    return Experiment(hypothesis=f"hypothesis {n}", family=family, params={"w": n})


# ======================================================================================
# THE TRIAL COUNT CANNOT BE UNDERSTATED
# ======================================================================================

def test_the_threshold_rises_with_the_number_of_experiments_already_run(ledger, strong):
    """The property the module exists for."""
    first = ledger.verdict(_exp(1), strong)
    ledger.record(_exp(1))
    for i in range(2, 202):
        ledger.record(_exp(i))
    later = ledger.verdict(_exp(999), strong)

    assert first.trials == 1 and later.trials == 202
    assert later.threshold > first.threshold
    assert first.threshold == pytest.approx(1.96, abs=0.01)
    assert later.threshold > 3.5
    assert first.t == later.t, "the same series must produce the same t; only the bar moves"


def test_there_is_no_way_to_pass_a_trial_count(ledger):
    """A keyword would be used, and by the person who wants the result to be significant."""
    sig = inspect.signature(Ledger.verdict)
    forbidden = {"n_trials", "trials", "num_trials", "alpha", "override", "force"}
    assert not (forbidden & set(sig.parameters)), (
        f"Ledger.verdict exposes {forbidden & set(sig.parameters)}, which reintroduces the "
        "softest number in quantitative research as an argument")


def test_a_result_that_clears_one_trial_can_fail_after_many(ledger):
    marginal = np.random.default_rng(3).normal(0.11, 1.0, size=400)
    assert ledger.verdict(_exp(0), marginal).passed
    for i in range(400):
        ledger.record(_exp(i))
    assert not ledger.verdict(_exp(9999), marginal).passed


def test_re_running_the_same_specification_does_not_add_a_trial(ledger):
    """Otherwise a search could launder its own multiplicity, or inflate it for nothing."""
    e = _exp(1)
    for _ in range(5):
        ledger.record(e)
    assert ledger.trials("futures.momentum") == 1
    assert len(ledger.all()) == 1


def test_a_re_run_is_judged_at_the_same_count_not_one_higher(ledger, strong):
    e = _exp(1)
    ledger.record(e)
    assert ledger.verdict(e, strong).trials == 1


def test_families_are_counted_separately(ledger, strong):
    for i in range(50):
        ledger.record(_exp(i, family="futures.momentum"))
    v = ledger.verdict(_exp(0, family="futures.meanrev"), strong)
    assert v.trials == 1, "a fresh family must not inherit another family's penalty"


def test_an_unnamed_family_is_refused():
    """The family is the unit multiplicity is counted over; an unnamed one escapes it."""
    for bad in ("", "   "):
        with pytest.raises(ValueError) as e:
            Experiment(hypothesis="h", family=bad)
        assert "family" in str(e.value)


def test_the_verdict_records_the_multiplicity_it_used(ledger, strong):
    for i in range(9):
        ledger.record(_exp(i))
    v = ledger.verdict(_exp(100), strong)
    assert v.trials == 10
    assert "10 trial" in v.describe()
    assert f"{v.threshold:.2f}" in v.describe()


# ======================================================================================
# THE STATISTIC IS HORIZON-AWARE
# ======================================================================================

def test_the_horizon_reaches_the_hac_statistic(ledger):
    """An overlapping label is an MA(h-1); an IID t on one is a number, not a statistic."""
    rng = np.random.default_rng(7)
    base = rng.normal(0.1, 1.0, size=600)
    overlapping = np.convolve(base, np.ones(21) / 21, mode="valid")   # h=21 overlap
    naive = ledger.verdict(_exp(1), overlapping, horizon=1)
    aware = ledger.verdict(_exp(1), overlapping, horizon=21)
    assert abs(aware.t) < abs(naive.t), (
        "the horizon-aware t must be smaller on an overlapping series; "
        f"got naive {naive.t:.2f} and aware {aware.t:.2f}")
    assert aware.horizon == 21


def test_a_degenerate_series_fails_rather_than_passing(ledger):
    v = ledger.verdict(_exp(1), np.zeros(200))
    assert not v.passed
    assert "not finite" in v.reason or "does not clear" in v.reason


# ======================================================================================
# THE LEDGER REMEMBERS
# ======================================================================================

def test_rejected_experiments_stay_in_the_denominator(ledger, strong):
    """A system that forgets its rejections flatters its survivors."""
    for i in range(30):
        e = _exp(i)
        e.stage = Stage.REJECTED
        ledger.record(e)
    assert ledger.trials("futures.momentum") == 30
    assert ledger.verdict(_exp(99), strong).trials == 31


def test_the_ledger_survives_a_reopen(tmp_path, strong):
    a = Ledger(tmp_path / "l.jsonl")
    for i in range(12):
        a.record(_exp(i))
    b = Ledger(tmp_path / "l.jsonl")
    assert b.trials("futures.momentum") == 12
    assert b.verdict(_exp(99), strong).trials == 13


def test_a_malformed_row_does_not_hide_the_rest_of_the_history(ledger):
    ledger.record(_exp(1))
    ledger.record(_exp(2))
    with ledger.path.open("a", encoding="utf-8") as fh:
        fh.write("{not json at all\n")
    assert ledger.trials("futures.momentum") == 2


def test_the_write_is_atomic_and_leaves_no_temp_files(ledger):
    for i in range(5):
        ledger.record(_exp(i))
    leftovers = list(ledger.path.parent.glob("*.tmp"))
    assert leftovers == [], f"atomic write left {leftovers} behind"


def test_each_row_is_valid_json_with_the_fields_a_reader_needs(ledger):
    e = _exp(1)
    e.metrics = {"sharpe": 1.2}
    ledger.record(e)
    row = json.loads(ledger.path.read_text(encoding="utf-8").strip())
    for k in ("experiment_id", "hypothesis", "family", "params", "metrics", "stage",
              "created"):
        assert k in row
    assert row["metrics"] == {"sharpe": 1.2}


def test_an_empty_ledger_is_zero_trials_not_a_crash(ledger, strong):
    assert ledger.all() == []
    assert ledger.trials("anything") == 0
    assert ledger.verdict(_exp(1), strong).trials == 1


def test_the_summary_counts_by_stage(ledger):
    for i in range(3):
        ledger.record(_exp(i))
    e = _exp(99)
    e.stage = Stage.REJECTED
    ledger.record(e)
    text = ledger.summary()
    assert "4 experiment" in text and "research=3" in text and "rejected=1" in text


# ======================================================================================
# THE FINGERPRINT
# ======================================================================================

def test_identity_comes_from_the_specification_not_the_outcome():
    """Otherwise every re-run is a new trial and a search can launder its multiplicity."""
    a = Experiment(hypothesis="h", family="f", params={"w": 5})
    b = Experiment(hypothesis="h", family="f", params={"w": 5})
    b.metrics = {"sharpe": 99.0}
    b.notes = "looks amazing"
    b.stage = Stage.CHAMPION
    assert a.fingerprint() == b.fingerprint()


def test_a_different_parameter_is_a_different_experiment():
    a = Experiment(hypothesis="h", family="f", params={"w": 5})
    b = Experiment(hypothesis="h", family="f", params={"w": 6})
    assert a.fingerprint() != b.fingerprint()


def test_parameter_ordering_does_not_change_identity():
    a = Experiment(hypothesis="h", family="f", params={"a": 1, "b": 2})
    b = Experiment(hypothesis="h", family="f", params={"b": 2, "a": 1})
    assert a.fingerprint() == b.fingerprint()


def test_seen_finds_a_prior_run(ledger):
    e = _exp(1)
    assert ledger.seen(e) is None
    ledger.record(e)
    assert ledger.seen(e) is not None
    assert ledger.seen(_exp(2)) is None


# ======================================================================================
# THE LADDER
# ======================================================================================

def _cand(stage=Stage.RESEARCH):
    return Candidate(candidate_id="c1", experiment_id="e1", stage=stage)


def test_the_happy_path_climbs_one_rung_at_a_time():
    c = _cand()
    for to in (Stage.VALIDATION, Stage.CHALLENGER, Stage.PAPER, Stage.CHAMPION):
        c.advance(to, why="met the gate")
    assert c.stage is Stage.CHAMPION
    assert len(c.history) == 4


def test_a_candidate_cannot_skip_a_rung():
    """Champion straight from research is the failure mode the ladder exists to prevent."""
    with pytest.raises(ValueError) as e:
        _cand().advance(Stage.CHAMPION, why="it had the best backtest")
    assert "not a permitted transition" in str(e.value)
    assert "cannot skip a rung" in str(e.value)


def test_every_stage_can_be_rejected_except_a_rejection():
    for s in (Stage.RESEARCH, Stage.VALIDATION, Stage.CHALLENGER, Stage.PAPER,
              Stage.CHAMPION):
        _cand(s).advance(Stage.REJECTED, why="failed")
    with pytest.raises(ValueError):
        _cand(Stage.REJECTED).advance(Stage.RESEARCH, why="second chance")


def test_rejection_is_terminal():
    assert Stage.REJECTED.is_terminal
    assert ALLOWED[Stage.REJECTED] == set()


def test_a_stage_change_must_carry_a_reason():
    for bad in ("", "  "):
        with pytest.raises(ValueError):
            _cand().advance(Stage.VALIDATION, why=bad)


def test_the_history_records_what_happened_and_why():
    c = _cand()
    c.advance(Stage.VALIDATION, why="cleared the 12-trial threshold")
    assert c.history == [("research->validation", "cleared the 12-trial threshold")]


def test_no_transition_lets_a_candidate_move_backwards_by_accident():
    c = _cand(Stage.PAPER)
    with pytest.raises(ValueError):
        c.advance(Stage.CHALLENGER, why="demote")
    assert c.stage is Stage.PAPER


def test_the_verdict_renders_both_outcomes():
    good = Verdict(metric=1.0, t=5.0, threshold=2.0, trials=3, horizon=1, passed=True,
                   reason="fine")
    bad = Verdict(metric=0.0, t=0.5, threshold=2.0, trials=3, horizon=1, passed=False,
                  reason="nope")
    assert good.describe().startswith("PASS")
    assert bad.describe().startswith("FAIL")
