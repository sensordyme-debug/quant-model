"""Tests for purged/embargoed cross-validation and the write-once holdout.

The property being defended is negative and therefore easy to get wrong silently: no
training row's label window may reach the fold it is scored against. A splitter that stops
purging at some boundary produces plausible, publishable, wrong numbers, so most of these
tests check the property directly rather than the arithmetic that is meant to produce it.
"""
from __future__ import annotations

import json

import numpy as np
import pytest

from quant_brain.core import validation as v

# ======================================================================================
# THE PURGE
# ======================================================================================

def test_no_training_label_window_reaches_the_test_fold():
    """Swept across geometries, because a purge that fails does so at a boundary.

    Some combinations are legitimately infeasible - n=200 with h=60 and 3 folds leaves the
    first fold nothing to train on - and the constructor refuses them by design. Those are
    skipped rather than treated as failures, but at least one geometry must survive per
    horizon or the sweep would be vacuously green.
    """
    for horizon in (0, 1, 5, 21, 60):
        checked = 0
        for folds in (2, 3, 5, 8):
            for n in (200, 1000, 1237):
                try:
                    splits = v.purged_walk_forward(n, horizon=horizon, folds=folds)
                except ValueError:
                    continue                      # geometry refused; nothing to check
                for split in splits:
                    v.assert_no_leakage(split, horizon=horizon)
                    checked += 1
        assert checked > 0, f"no feasible geometry was actually checked at h={horizon}"


def test_the_purge_removes_exactly_the_horizon():
    splits = v.purged_walk_forward(1000, horizon=21, folds=5)
    assert [s.purged for s in splits] == [21] * 5


def test_a_zero_horizon_purges_nothing():
    splits = v.purged_walk_forward(1000, horizon=0, folds=5)
    assert all(s.purged == 0 for s in splits)


def test_every_split_is_strictly_walk_forward():
    for s in v.purged_walk_forward(500, horizon=10, folds=4):
        assert s.train.max() < s.test.min(), "training data must precede the test fold"


def test_test_folds_tile_the_tail_without_overlapping():
    splits = v.purged_walk_forward(1000, horizon=5, folds=5)
    covered = np.concatenate([s.test for s in splits])
    assert covered.size == np.unique(covered).size, "test folds overlap"
    assert covered.max() == 999, "the last fold must reach the end of the sample"


def test_the_horizon_is_required_and_not_defaulted():
    with pytest.raises(TypeError):
        v.purged_walk_forward(100)          # type: ignore[call-arg]


def test_a_leaky_split_is_caught_by_the_assertion():
    """The detector must actually detect; build a bad split by hand and check it fires."""
    bad = v.Split(fold=0, train=np.arange(0, 100), test=np.arange(100, 200),
                  purged=0, embargoed=0)
    v.assert_no_leakage(bad, horizon=0)                    # h=0 is fine
    with pytest.raises(v.LeakageError) as e:
        v.assert_no_leakage(bad, horizon=5)
    assert "label windows reaching" in str(e.value)
    assert "index 95" in str(e.value), "the error should name the first offending row"


def test_a_non_walk_forward_split_is_caught():
    # Training strictly after the test fold and not overlapping it: the purge check passes
    # and only the ordering check can catch this one.
    bad = v.Split(fold=0, train=np.arange(250, 300), test=np.arange(100, 200),
                  purged=0, embargoed=0)
    with pytest.raises(v.LeakageError) as e:
        v.assert_no_leakage(bad, horizon=0)
    assert "not walk-forward" in str(e.value)
    # The same split is legitimate under k-fold, where the checker must not object.
    v.assert_no_leakage(bad, horizon=0, walk_forward=False)


def test_rolling_windows_are_shorter_than_expanding_ones():
    exp = v.purged_walk_forward(1000, horizon=5, folds=5, expanding=True)
    roll = v.purged_walk_forward(1000, horizon=5, folds=5, expanding=False)
    assert exp[-1].train_size > roll[-1].train_size
    for s in roll:
        v.assert_no_leakage(s, horizon=5)


def test_impossible_geometry_is_refused_rather_than_returning_empty_folds():
    with pytest.raises(ValueError):
        v.purged_walk_forward(3, horizon=1, folds=5)
    with pytest.raises(ValueError):
        v.purged_walk_forward(0, horizon=5, folds=3)
    with pytest.raises(ValueError):
        v.purged_walk_forward(100, horizon=5, folds=1)
    with pytest.raises(ValueError):
        v.purged_walk_forward(100, horizon=-1, folds=3)
    with pytest.raises(ValueError):
        v.purged_walk_forward(100, horizon=5, folds=3, embargo=-5)


def test_a_horizon_that_eats_the_sample_is_refused_with_an_explanation():
    with pytest.raises(ValueError) as e:
        v.purged_walk_forward(120, horizon=100, folds=5, min_train=10)
    msg = str(e.value)
    assert "eaten the sample" in msg
    assert "shorter horizon" in msg, "the error must say what to do about it"


# ======================================================================================
# THE EMBARGO - vacuous in walk-forward, load-bearing in k-fold
# ======================================================================================

def test_the_embargo_removes_nothing_under_walk_forward_at_any_width():
    """The module's headline claim, asserted rather than argued.

    An embargo protects a test fold from training rows that follow it. Walk-forward has
    none, so no width can remove a row. If this ever fails, either the fold layout stopped
    being walk-forward or the embargo started removing rows it should not.
    """
    for embargo in (1, 10, 100, 0.01, 0.25):
        splits = v.purged_walk_forward(1000, horizon=21, folds=5, embargo=embargo)
        assert all(s.embargoed == 0 for s in splits), f"embargo={embargo} removed rows"


def test_the_embargo_does_remove_rows_under_kfold():
    """The contrast that makes the claim above meaningful rather than a broken feature."""
    splits = v.purged_kfold(1000, horizon=21, folds=5, embargo=10)
    assert sum(s.embargoed for s in splits) > 0
    # Every fold but the last has training data on its right-hand side to embargo.
    assert [s.embargoed for s in splits[:-1]] == [10, 10, 10, 10]
    assert splits[-1].embargoed == 0, "the final fold ends the sample; nothing follows it"


def test_kfold_purges_on_the_left_and_embargoes_on_the_right():
    for s in v.purged_kfold(1000, horizon=21, folds=5, embargo=10):
        v.assert_no_leakage(s, horizon=21, embargo=10, walk_forward=False)


def test_kfold_trains_on_both_sides_which_walk_forward_never_does():
    kf = v.purged_kfold(1000, horizon=5, folds=5, embargo=0)
    interior = kf[2]
    assert interior.train.min() < interior.test.min()
    assert interior.train.max() > interior.test.max(), (
        "the whole point of k-fold here is training data after the test block")


def test_an_embargo_violation_is_caught_by_the_assertion():
    bad = v.Split(fold=0, train=np.array([50, 205, 210]), test=np.arange(100, 200),
                  purged=0, embargoed=0)
    with pytest.raises(v.LeakageError) as e:
        v.assert_no_leakage(bad, horizon=0, embargo=20)
    assert "embargo" in str(e.value)


def test_a_fractional_embargo_is_read_as_a_fraction_of_n():
    splits = v.purged_kfold(1000, horizon=0, folds=5, embargo=0.02)
    assert splits[0].embargoed == 20


def test_kfold_refuses_impossible_geometry():
    with pytest.raises(ValueError):
        v.purged_kfold(0, horizon=5, folds=3)
    with pytest.raises(ValueError):
        v.purged_kfold(100, horizon=5, folds=1)
    with pytest.raises(ValueError):
        v.purged_kfold(100, horizon=-1, folds=3)
    with pytest.raises(ValueError):
        v.purged_kfold(100, horizon=5, folds=3, embargo=-1)


# ======================================================================================
# COVERAGE - what the correction cost
# ======================================================================================

def test_coverage_reports_the_cost_of_the_correction():
    cov = v.coverage(v.purged_walk_forward(1000, horizon=21, folds=5), 1000)
    assert 0 < cov["train"] < 1
    assert cov["test"] == pytest.approx(0.834, abs=0.01)
    assert cov["purged"] == pytest.approx(105 / 1000)
    assert cov["embargoed"] == 0.0


def test_a_longer_horizon_costs_more_data():
    short = v.coverage(v.purged_walk_forward(1000, horizon=5, folds=5), 1000)
    long = v.coverage(v.purged_walk_forward(1000, horizon=60, folds=5), 1000)
    assert long["purged"] > short["purged"]
    assert long["train"] < short["train"]


def test_coverage_of_no_splits_is_zero_not_a_crash():
    assert v.coverage([], 100)["train"] == 0.0


# ======================================================================================
# CROSS-VALIDATION
# ======================================================================================

def test_cross_validate_passes_disjoint_purged_indices_to_the_scorer():
    seen = []

    def score(train, test):
        seen.append((train.copy(), test.copy()))
        assert train.max() + 21 < test.min()
        return float(test.size)

    r = v.cross_validate(score, 1000, horizon=21, folds=5)
    assert len(seen) == 5
    assert len(r.scores) == 5
    assert r.horizon == 21


def test_cross_validate_checks_for_leakage_by_default():
    """The check must be on unless switched off, since its cost is a boolean mask."""
    calls = []
    original = v.assert_no_leakage

    def spy(split, **kw):
        calls.append(split.fold)
        return original(split, **kw)

    v.assert_no_leakage = spy                       # type: ignore[assignment]
    try:
        v.cross_validate(lambda a, b: 0.0, 500, horizon=5, folds=4)
        assert calls == [0, 1, 2, 3]
        calls.clear()
        v.cross_validate(lambda a, b: 0.0, 500, horizon=5, folds=4, check=False)
        assert calls == []
    finally:
        v.assert_no_leakage = original              # type: ignore[assignment]


def test_the_result_summary_states_the_horizon_and_what_was_dropped():
    r = v.cross_validate(lambda a, b: 0.5, 1000, horizon=21, folds=5, embargo=10)
    text = r.summary()
    assert "h=21" in text and "embargo=10" in text
    assert "purged" in text and "%" in text
    assert r.mean == pytest.approx(0.5)


def test_a_single_fold_score_has_no_standard_deviation_rather_than_zero():
    r = v.CVResult(scores=[0.3], splits=[], coverage={})
    assert np.isnan(r.std), "one fold cannot estimate dispersion; 0.0 would be a lie"


def test_iter_splits_yields_index_pairs():
    pairs = list(v.iter_splits(500, horizon=5, folds=3))
    assert len(pairs) == 3
    for train, test in pairs:
        assert train.max() + 5 < test.min()


# ======================================================================================
# THE WRITE-ONCE HOLDOUT
# ======================================================================================

@pytest.fixture
def series():
    rng = np.random.default_rng(0)
    return rng.normal(size=500)


def test_a_holdout_is_the_tail_of_the_sample(series, tmp_path):
    h = v.make_holdout(series, fraction=0.2, ledger_path=tmp_path / "ledger.jsonl")
    assert h.size == 100
    assert h.start == 400
    assert h.test_index[0] == 400 and h.test_index[-1] == 499
    assert h.train_index[-1] == 399


def test_the_holdout_training_index_is_purged_too(series, tmp_path):
    h = v.make_holdout(series, fraction=0.2, ledger_path=tmp_path / "l.jsonl")
    idx = h.purged_train_index(horizon=21)
    assert idx[-1] == 378, "the last 21 rows before the holdout carry labels inside it"
    assert idx.size == h.train_index.size - 21


def test_the_first_look_is_recorded(series, tmp_path):
    ledger = tmp_path / "l.jsonl"
    h = v.make_holdout(series, fraction=0.2, ledger_path=ledger, label="F-13")
    rec = h.spend(result={"sharpe": 1.2}, note="first evaluation of the meta-model")
    assert rec["look"] == 1 and rec["forced"] is False
    assert ledger.exists()
    written = json.loads(ledger.read_text(encoding="utf-8").strip())
    assert written["result"] == {"sharpe": 1.2}
    assert written["label"] == "F-13"


def test_a_second_look_is_refused(series, tmp_path):
    h = v.make_holdout(series, fraction=0.2, ledger_path=tmp_path / "l.jsonl")
    h.spend(result={"sharpe": 1.2}, note="first")
    with pytest.raises(v.LeakageError) as e:
        h.spend(result={"sharpe": 1.4}, note="second")
    msg = str(e.value)
    assert "already been evaluated" in msg
    assert "'first'" in msg, "the refusal should quote what the first look was for"
    assert "force=True" in msg


def test_a_forced_second_look_is_allowed_and_labelled(series, tmp_path):
    ledger = tmp_path / "l.jsonl"
    h = v.make_holdout(series, fraction=0.2, ledger_path=ledger)
    h.spend(result={}, note="first")
    rec = h.spend(result={}, note="deliberate second look after a model change", force=True)
    assert rec["look"] == 2 and rec["forced"] is True
    assert len(h.looks()) == 2


def test_the_refusal_survives_a_new_process(series, tmp_path):
    """The ledger is on disk and keyed by the data, so a fresh object still notices."""
    ledger = tmp_path / "l.jsonl"
    v.make_holdout(series, fraction=0.2, ledger_path=ledger).spend(result={}, note="first")
    again = v.make_holdout(series, fraction=0.2, ledger_path=ledger)
    assert len(again.looks()) == 1
    with pytest.raises(v.LeakageError):
        again.spend(result={}, note="second, from a different object")


def test_different_data_is_a_different_holdout(series, tmp_path):
    ledger = tmp_path / "l.jsonl"
    v.make_holdout(series, fraction=0.2, ledger_path=ledger).spend(result={}, note="a")
    other = v.make_holdout(series * 2, fraction=0.2, ledger_path=ledger)
    assert other.looks() == [], "a different series must not inherit another's ledger"
    other.spend(result={}, note="b")


def test_a_different_fraction_is_a_different_holdout(series, tmp_path):
    ledger = tmp_path / "l.jsonl"
    v.make_holdout(series, fraction=0.2, ledger_path=ledger).spend(result={}, note="a")
    v.make_holdout(series, fraction=0.3, ledger_path=ledger).spend(result={}, note="b")


def test_an_evaluation_without_a_note_is_refused(series, tmp_path):
    h = v.make_holdout(series, fraction=0.2, ledger_path=tmp_path / "l.jsonl")
    for bad in ("", "   ", "\n"):
        with pytest.raises(ValueError) as e:
            h.spend(result={}, note=bad)
        assert "worthless without it" in str(e.value)


def test_an_empty_or_impossible_holdout_is_refused(tmp_path):
    with pytest.raises(ValueError):
        v.make_holdout([], ledger_path=tmp_path / "l.jsonl")
    for bad in (0.0, 1.0, -0.1, 1.5):
        with pytest.raises(ValueError):
            v.make_holdout([1.0, 2.0, 3.0], fraction=bad, ledger_path=tmp_path / "l.jsonl")


def test_the_ledger_directory_is_created_on_demand(series, tmp_path):
    h = v.make_holdout(series, fraction=0.2,
                       ledger_path=tmp_path / "deep" / "nested" / "l.jsonl")
    h.spend(result={}, note="first")
    assert (tmp_path / "deep" / "nested" / "l.jsonl").exists()


def test_the_holdout_never_overlaps_the_cv_folds(series, tmp_path):
    """The two mechanisms must compose: CV on the training portion only."""
    h = v.make_holdout(series, fraction=0.2, ledger_path=tmp_path / "l.jsonl")
    train_n = h.purged_train_index(horizon=21).size
    for s in v.purged_walk_forward(train_n, horizon=21, folds=4):
        assert s.test.max() < h.start, "a CV fold reached into the holdout"
