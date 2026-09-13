"""Tests for the futures feature library and the bounded discovery funnel.

Two properties carry the weight. A feature must be refused when the store cannot support it,
rather than approximated from something else - that is the difference between a
microstructure feature and a noisier copy of the return wearing its name. And every gate in
the funnel must be able to reject, because a gate that never fires is decoration and a loop
made of decoration promotes noise.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_brain.markets.futures_cme import features as fe
from quant_brain.research import Ledger
from quant_brain.research.registry import Stage
from quant_brain.research.search import (
    Funnel,
    Hypothesis,
    Limits,
    search,
    threshold_hypotheses,
)


@pytest.fixture
def bars():
    rng = np.random.default_rng(4)
    n = 400
    close = 6000 + np.cumsum(rng.normal(0, 0.5, n))
    return pd.DataFrame({
        "o": close, "h": close + 0.5, "l": close - 0.5, "c": close,
        "v": rng.integers(1, 500, n).astype(float),
    })


@pytest.fixture
def quoted(bars):
    df = bars.copy()
    df["bid"] = df["c"] - 0.25
    df["ask"] = df["c"] + 0.25
    df["bid_size"] = 100.0
    df["ask_size"] = 120.0
    return df


# ======================================================================================
# THE LIBRARY REFUSES WHAT IT CANNOT SUPPORT
# ======================================================================================

def test_microstructure_is_absent_on_an_ohlcv_store(bars):
    """The rule the library exists to enforce: never fabricate microstructure from OHLCV."""
    lib = fe.library()
    missing = lib.missing(set(bars.columns))
    assert set(missing) == {"spread_bps", "quote_imbalance"}
    X, skipped = lib.build(bars, strict=False)
    assert "spread_bps" not in X.columns
    assert "quote_imbalance" not in X.columns
    assert set(skipped) == set(missing)


def test_microstructure_appears_once_the_store_carries_quotes(quoted):
    lib = fe.library()
    assert lib.missing(set(quoted.columns)) == {}
    X, skipped = lib.build(quoted)
    assert skipped == {}
    assert "spread_bps" in X.columns
    assert X["spread_bps"].iloc[10] == pytest.approx(0.5 / quoted["c"].iloc[10] * 10_000)


def test_a_strict_build_refuses_rather_than_silently_narrowing(bars):
    """A narrower matrix than the caller asked for is what the model actually sees."""
    with pytest.raises(ValueError) as e:
        fe.library().build(bars)
    msg = str(e.value)
    assert "cannot support 2 feature(s)" in msg
    assert "narrower matrix is what your model will actually see" in msg


def test_the_missing_report_names_the_columns_each_feature_wanted(bars):
    missing = fe.library().missing(set(bars.columns))
    assert set(missing["spread_bps"]) == {"bid", "ask"}
    assert set(missing["quote_imbalance"]) == {"bid_size", "ask_size"}


def test_duplicate_feature_names_are_refused():
    fs = fe.FeatureSet()
    f = fe.Feature("x", "fam", lambda d: d["c"])
    fs.add(f)
    with pytest.raises(ValueError) as e:
        fs.add(fe.Feature("x", "other", lambda d: d["c"]))
    assert "silent overwrite" in str(e.value)


def test_every_family_named_in_the_brief_is_present():
    fams = fe.library().families()
    for expected in ("momentum", "meanrev", "volatility", "volume", "session",
                     "microstructure"):
        assert expected in fams, f"family {expected} missing from the library"


# ======================================================================================
# CAUSALITY IS VERIFIED, NOT ASSERTED
# ======================================================================================

def test_no_feature_in_the_library_reads_the_future(quoted):
    assert fe.audit_causality(fe.library(), quoted) == {}


def test_the_causality_check_actually_catches_a_leak(bars):
    """A guard that cannot fail is not a guard."""
    leaky = fe.Feature("peek", "bad", lambda d: d["c"].shift(-5), ("c",), 0)
    with pytest.raises(AssertionError) as e:
        fe.assert_causal(leaky, bars)
    assert "not causal" in str(e.value)


def test_a_centred_window_is_caught(bars):
    """The realistic version of the bug: review passes, the test does not."""
    centred = fe.Feature("centred", "bad",
                         lambda d: d["c"].rolling(21, center=True).mean(), ("c",), 21)
    with pytest.raises(AssertionError):
        fe.assert_causal(centred, bars)


def test_audit_reports_every_leak_rather_than_the_first(bars):
    fs = fe.FeatureSet()
    fs.add(fe.Feature("a", "bad", lambda d: d["c"].shift(-3), ("c",)))
    fs.add(fe.Feature("b", "bad", lambda d: d["c"].shift(-7), ("c",)))
    fs.add(fe.Feature("ok", "good", lambda d: d["c"].shift(3), ("c",)))
    fails = fe.audit_causality(fs, bars)
    assert set(fails) == {"a", "b"}


def test_a_feature_the_store_cannot_build_is_skipped_by_the_audit(bars):
    fs = fe.FeatureSet()
    fs.add(fe.Feature("needs_quotes", "micro", lambda d: d["bid"], ("bid",)))
    assert fe.audit_causality(fs, bars) == {}


# ======================================================================================
# THE FUNNEL: EVERY GATE CAN REJECT
# ======================================================================================

def _hyp(n=0, family="test.family"):
    return Hypothesis(name=f"h{n}", family=family, params={"i": n}, signal=lambda X: 0.0)


def _result(**kw):
    base = {"pnl": list(np.random.default_rng(0).normal(5.0, 1.0, 200)), "sessions": 200}
    base.update(kw)
    return base


def test_each_gate_rejects_and_is_counted(tmp_path):
    """One hypothesis per gate, each rigged to die at exactly that gate."""
    ledger = Ledger(tmp_path / "l.jsonl")
    rng = np.random.default_rng(1)
    strong = list(rng.normal(5.0, 1.0, 200))
    weak = list(rng.normal(0.0, 1.0, 200))

    plan = {
        "h0": _result(pnl=weak),                                     # statistical
        "h1": _result(pnl=strong, cost_ok=False),                    # cost
        "h2": _result(pnl=strong, topstep_ok=False),                 # topstep
        "h3": _result(pnl=strong, walkforward_ok=False),             # walk-forward
        "h4": _result(pnl=strong),                                   # survives
        "h5": _result(pnl=strong[:10], sessions=10),                 # too short
    }
    fun = search([_hyp(i) for i in range(6)], ledger=ledger,
                 evaluate=lambda h: plan[h.name],
                 limits=Limits(min_sessions=100))

    assert fun.rejected_statistical == 1
    assert fun.rejected_cost == 1
    assert fun.rejected_topstep == 1
    assert fun.rejected_walkforward == 1
    assert fun.too_short == 1
    assert fun.survived == ["h4"]


def test_the_statistical_gate_runs_first(tmp_path):
    """Otherwise the survivors are selected by filters the correction cannot see."""
    ledger = Ledger(tmp_path / "l.jsonl")
    weak = list(np.random.default_rng(2).normal(0.0, 1.0, 200))
    fun = search([_hyp(0)], ledger=ledger,
                 evaluate=lambda h: _result(pnl=weak, cost_ok=False, topstep_ok=False),
                 limits=Limits(min_sessions=100))
    assert fun.rejected_statistical == 1
    assert fun.rejected_cost == 0, "a statistically dead hypothesis reached the cost gate"


def test_every_hypothesis_is_recorded_including_the_rejections(tmp_path):
    """The rejections are the denominator of the correction applied to the survivors."""
    ledger = Ledger(tmp_path / "l.jsonl")
    weak = list(np.random.default_rng(3).normal(0.0, 1.0, 200))
    search([_hyp(i) for i in range(25)], ledger=ledger,
           evaluate=lambda h: _result(pnl=weak), limits=Limits(min_sessions=100))
    assert ledger.trials("test.family") == 25
    assert all(e.stage is Stage.REJECTED for e in ledger.family("test.family"))


def test_the_threshold_rises_across_one_search(tmp_path):
    """The hundredth candidate in a family faces a harder bar than the first."""
    ledger = Ledger(tmp_path / "l.jsonl")
    seen = []
    weak = list(np.random.default_rng(5).normal(0.0, 1.0, 200))
    search([_hyp(i) for i in range(30)], ledger=ledger,
           evaluate=lambda h: _result(pnl=weak), limits=Limits(min_sessions=100))
    seen = [e.verdict.threshold for e in ledger.family("test.family") if e.verdict]
    assert max(seen) > min(seen), "the bar did not move across the search"


def test_a_survivor_reaches_validation_not_champion(tmp_path):
    ledger = Ledger(tmp_path / "l.jsonl")
    strong = list(np.random.default_rng(6).normal(5.0, 1.0, 200))
    search([_hyp(0)], ledger=ledger, evaluate=lambda h: _result(pnl=strong),
           limits=Limits(min_sessions=100))
    e = ledger.family("test.family")[0]
    assert e.stage is Stage.VALIDATION, "surviving the funnel is not promotion"


# ======================================================================================
# THE LOOP IS BOUNDED AND RESUMABLE
# ======================================================================================

def test_the_experiment_budget_stops_the_loop(tmp_path):
    ledger = Ledger(tmp_path / "l.jsonl")
    weak = list(np.random.default_rng(7).normal(0.0, 1.0, 200))
    fun = search([_hyp(i) for i in range(100)], ledger=ledger,
                 evaluate=lambda h: _result(pnl=weak),
                 limits=Limits(max_experiments=10, min_sessions=100))
    assert fun.tested <= 10
    assert "experiment budget" in fun.stopped_because


def test_the_time_budget_stops_the_loop(tmp_path):
    import time
    ledger = Ledger(tmp_path / "l.jsonl")
    weak = list(np.random.default_rng(8).normal(0.0, 1.0, 200))

    def slow(h):
        time.sleep(0.05)
        return _result(pnl=weak)

    fun = search([_hyp(i) for i in range(100)], ledger=ledger, evaluate=slow,
                 limits=Limits(max_seconds=0.2, min_sessions=100))
    assert "time budget" in fun.stopped_because


def test_a_resumed_search_skips_what_is_already_in_the_ledger(tmp_path):
    ledger = Ledger(tmp_path / "l.jsonl")
    weak = list(np.random.default_rng(9).normal(0.0, 1.0, 200))
    hyps = [_hyp(i) for i in range(20)]
    first = search(hyps, ledger=ledger, evaluate=lambda h: _result(pnl=weak),
                   limits=Limits(min_sessions=100))
    second = search(hyps, ledger=ledger, evaluate=lambda h: _result(pnl=weak),
                    limits=Limits(min_sessions=100))
    assert first.duplicate == 0
    assert second.duplicate == 20
    assert second.tested == 0
    assert ledger.trials("test.family") == 20, "a resume must not inflate the trial count"


def test_a_duplicate_is_not_re_evaluated(tmp_path):
    ledger = Ledger(tmp_path / "l.jsonl")
    calls = []
    weak = list(np.random.default_rng(10).normal(0.0, 1.0, 200))

    def counting(h):
        calls.append(h.name)
        return _result(pnl=weak)

    search([_hyp(0)], ledger=ledger, evaluate=counting, limits=Limits(min_sessions=100))
    search([_hyp(0)], ledger=ledger, evaluate=counting, limits=Limits(min_sessions=100))
    assert calls == ["h0"], "a duplicate was re-evaluated, which is the expensive half"


def test_the_callback_sees_every_outcome(tmp_path):
    ledger = Ledger(tmp_path / "l.jsonl")
    seen = []
    rng = np.random.default_rng(11)
    plan = {"h0": _result(pnl=list(rng.normal(0.0, 1.0, 200))),
            "h1": _result(pnl=list(rng.normal(5.0, 1.0, 200)))}
    search([_hyp(0), _hyp(1)], ledger=ledger, evaluate=lambda h: plan[h.name],
           limits=Limits(min_sessions=100),
           on_result=lambda h, r, outcome: seen.append(outcome))
    assert set(seen) == {"statistical", "survived"}


# ======================================================================================
# HYPOTHESIS GENERATION
# ======================================================================================

def test_the_grid_size_is_the_product_of_its_axes():
    hyps = threshold_hypotheses(["a", "b", "c"], family="f",
                                thresholds=(-1.0, 1.0), directions=(1, -1))
    assert len(hyps) == 3 * 2 * 2
    assert len({h.name for h in hyps}) == len(hyps), "grid produced duplicate names"


def test_every_generated_hypothesis_carries_its_parameters():
    for h in threshold_hypotheses(["z_60"], family="f"):
        assert set(h.params) == {"feature", "threshold", "direction"}
        assert h.family == "f"


def test_a_generated_signal_is_bounded_and_uses_only_its_own_feature():
    X = pd.DataFrame({"a": np.linspace(-3, 3, 50), "b": np.zeros(50)})
    h = threshold_hypotheses(["a"], family="f", thresholds=(0.5,), directions=(1,))[0]
    sig = np.asarray(h.signal(X), dtype=float)
    assert set(np.unique(sig)) <= {-1.0, 1.0}
    assert len(sig) == len(X)


def test_the_funnel_table_renders_every_stage():
    text = Funnel(generated=10, rejected_statistical=7, rejected_cost=2,
                  survived=["x"], stopped_because="budget").table()
    for probe in ("generated", "statistical", "cost", "Topstep", "walk-forward",
                  "SURVIVED", "stopped"):
        assert probe in text


# ======================================================================================
# THE LOOKAHEAD THAT PRODUCED THE ONLY SURVIVOR
#
# opening_range_pos took the high and low of the first 30 bars and divided EVERY bar by that
# range, including the first 30 - so at bar 5 it already knew the extremes of bars 6..29. The
# causality check missed it because it probed a single index at 80% through the series, where
# a leak confined to the opening window cannot show.
#
# It was the only hypothesis to survive the funnel across 272 candidates on two contracts:
# t = +6.25 against a 3.56 multiplicity bar, 5/5 walk-forward folds, $140.75 a session on one
# MNQ. With the feature made causal, the same grid promotes nothing.
# ======================================================================================

def test_the_opening_range_feature_is_causal_inside_its_own_window(bars):
    """The specific failure: perturbing a bar inside the opening range moved earlier bars."""
    feat = next(f for f in fe.library().features if f.name == "opening_range_pos")
    base = np.asarray(feat.fn(bars), dtype=float)
    bumped = bars.copy()
    for col in ("c", "h", "l", "o"):
        bumped.iloc[20:, bumped.columns.get_loc(col)] *= 1.05
    after = np.asarray(feat.fn(bumped), dtype=float)
    assert np.allclose(base[:20], after[:20], equal_nan=True), (
        "perturbing bar 20 changed a bar before it; the opening range is reading forward")


def test_the_opening_range_freezes_after_its_window(bars):
    """It must still be the OPENING range: fixed once the first 30 bars are done."""
    feat = next(f for f in fe.library().features if f.name == "opening_range_pos")
    base = np.asarray(feat.fn(bars), dtype=float)
    bumped = bars.copy()
    # A new session high at bar 100 must not redefine the opening range.
    bumped.iloc[100, bumped.columns.get_loc("h")] *= 2.0
    after = np.asarray(feat.fn(bumped), dtype=float)
    assert np.allclose(base[:100], after[:100], equal_nan=True)


def test_the_causality_check_probes_early_bars_not_just_late_ones():
    """A single late probe is what let the leak through; assert the sweep exists."""
    import inspect
    src = inspect.getsource(fe.assert_causal)
    assert "points" in src, "assert_causal no longer sweeps multiple perturbation points"


def test_a_leak_confined_to_the_opening_window_is_caught(bars):
    """The exact shape of the shipped bug, rebuilt, must now fail."""
    leaky = fe.Feature(
        "orp_old", "session",
        lambda d: (d["c"] - d["l"].iloc[:30].min())
        / (d["h"].iloc[:30].max() - d["l"].iloc[:30].min()),
        ("h", "l", "c"), 0)
    with pytest.raises(AssertionError) as e:
        fe.assert_causal(leaky, bars)
    assert "not causal" in str(e.value)


def test_a_late_only_probe_would_still_miss_it(bars):
    """Documents WHY the sweep is necessary rather than merely asserting that it is."""
    leaky = fe.Feature(
        "orp_old", "session",
        lambda d: (d["c"] - d["l"].iloc[:30].min())
        / (d["h"].iloc[:30].max() - d["l"].iloc[:30].min()),
        ("h", "l", "c"), 0)
    fe.assert_causal(leaky, bars, at=int(len(bars) * 0.8))     # passes, and that was the bug
