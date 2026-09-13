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


# ======================================================================================
# CONCURRENCY AND PROVENANCE
#
# Both regressions below were found by an adversarial review of code written the same day,
# and both were confirmed by measurement before being fixed. They are the two ways the trial
# count - the denominator of every correction this module applies - could silently be wrong.
# ======================================================================================

def test_provenance_survives_the_round_trip(ledger):
    """It was written to disk and thrown away on read, so a loaded row had no environment.

    That is precisely the field a cross-environment refusal needs: two rows both reporting
    None would have compared equal and been called a match.
    """
    from quant_brain.core.provenance import Provenance
    e = Experiment(hypothesis="h", family="f", params={"a": 1},
                   provenance=Provenance.capture())
    ledger.record(e)
    back = ledger.all()[0].provenance
    assert back is not None, "provenance was dropped on read"
    assert back.env_key, "an experiment loaded from disk must know its environment"


def test_a_row_written_by_older_code_still_loads(ledger):
    """The ledger is append-only, so it holds rows from before fields existed."""
    ledger.path.parent.mkdir(parents=True, exist_ok=True)
    ledger.path.write_text(json.dumps({
        "experiment_id": "old1", "hypothesis": "h", "family": "f", "params": {},
        "metrics": {}, "stage": "research", "created": "2026-01-01T00:00:00",
        "provenance": {"git_commit": "abc", "a_field_that_no_longer_exists": 1},
    }) + "\n", encoding="utf-8")
    e = ledger.all()[0]
    assert e.provenance is not None and e.provenance.git_commit == "abc"


def test_concurrent_records_do_not_lose_experiments(tmp_path):
    """A lost row is a lost trial. Measured before the fix: 8 recorded, 3 on disk.

    Neither obvious design was correct on this machine. A read-modify-write around
    os.replace loses updates; a plain append-mode write is not atomic either, because Python
    emulates O_APPEND on Windows with a seek followed by a write.
    """
    import threading
    led = Ledger(tmp_path / "l.jsonl")
    n = 16
    barrier = threading.Barrier(n)
    errors: list[str] = []

    def record(i: int) -> None:
        try:
            barrier.wait()
            led.record(Experiment(hypothesis=f"h{i}", family="fam", params={"i": i}))
        except Exception as exc:                                        # noqa: BLE001
            errors.append(repr(exc))

    threads = [threading.Thread(target=record, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"recording raised under contention: {errors[:3]}"
    assert led.trials("fam") == n, f"{n} recorded, {led.trials('fam')} survived"


def test_concurrent_duplicates_still_count_as_one_trial(tmp_path):
    """The check and the append must be one operation, or both racers write."""
    import threading
    led = Ledger(tmp_path / "l.jsonl")
    barrier = threading.Barrier(12)

    def record(_: int) -> None:
        barrier.wait()
        led.record(Experiment(hypothesis="same", family="fam", params={"a": 1}))

    threads = [threading.Thread(target=record, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert led.trials("fam") == 1
    assert len(led.all()) == 1


def test_the_lock_file_is_not_left_behind(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    for i in range(5):
        led.record(_exp(i))
    assert list(tmp_path.glob("*.lock")) == []


def test_a_stale_lock_is_broken_rather_than_deadlocking(tmp_path):
    """An agent killed mid-write must not block every other track forever."""
    import time as _time
    led = Ledger(tmp_path / "l.jsonl")
    stale = led.path.with_suffix(led.path.suffix + ".lock")
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.touch()
    started = _time.monotonic()
    from quant_brain.research.registry import _file_lock
    with _file_lock(led.path, timeout=0.2):
        pass
    assert _time.monotonic() - started < 5.0, "a stale lock deadlocked the loop"


# ======================================================================================
# RETRACTION
#
# A research platform has to be able to say "this was wrong, and here is why" without
# erasing the record. The case this was built for: a hypothesis that survived the funnel at
# t = +6.25 and was later shown to be produced by a lookahead in the feature library.
# ======================================================================================

def test_a_retraction_withdraws_the_verdict_without_deleting_the_trial(ledger):
    """The original is still a trial and still belongs in every later denominator."""
    e = _exp(1)
    e.stage = Stage.VALIDATION
    ledger.record(e)
    assert ledger.trials("futures.momentum") == 1

    ledger.retract(e.experiment_id, why="the feature it used read the future")
    back = ledger.all()[0]
    assert back.stage is Stage.REJECTED
    assert "RETRACTED" in back.notes and "read the future" in back.notes
    assert ledger.trials("futures.momentum") == 1, "a retraction must not remove a trial"


def test_the_original_row_stays_byte_identical_on_disk(ledger):
    e = _exp(1)
    ledger.record(e)
    first_line = ledger.path.read_text(encoding="utf-8").splitlines()[0]
    ledger.retract(e.experiment_id, why="wrong")
    assert ledger.path.read_text(encoding="utf-8").splitlines()[0] == first_line


def test_a_retraction_must_say_why(ledger):
    e = _exp(1)
    ledger.record(e)
    for bad in ("", "   "):
        with pytest.raises(ValueError) as exc:
            ledger.retract(e.experiment_id, why=bad)
        assert "deletion with extra steps" in str(exc.value)


def test_retractions_are_listed_with_their_reasons(ledger):
    e = _exp(1)
    ledger.record(e)
    ledger.retract(e.experiment_id, why="lookahead in the opening range")
    assert ledger.retractions() == {e.experiment_id: "lookahead in the opening range"}


def test_a_retraction_survives_a_reopen(tmp_path):
    a = Ledger(tmp_path / "l.jsonl")
    e = _exp(1)
    e.stage = Stage.VALIDATION
    a.record(e)
    a.retract(e.experiment_id, why="wrong")
    assert Ledger(tmp_path / "l.jsonl").all()[0].stage is Stage.REJECTED


def test_retracting_one_experiment_leaves_the_others_alone(ledger):
    keep, drop = _exp(1), _exp(2)
    for x in (keep, drop):
        x.stage = Stage.VALIDATION
        ledger.record(x)
    ledger.retract(drop.experiment_id, why="wrong")
    by_id = {e.experiment_id: e for e in ledger.all()}
    assert by_id[keep.experiment_id].stage is Stage.VALIDATION
    assert by_id[drop.experiment_id].stage is Stage.REJECTED
