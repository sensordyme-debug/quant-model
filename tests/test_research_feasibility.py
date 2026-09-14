"""The gate that runs before the laboratory, and the record that runs alongside it.

These two modules exist because of a measured failure. A 240-trial tournament on this
repository's own data produced no survivor, and most of those 240 backtests were answerable
in advance with arithmetic: a mechanism predicting a two-tick move traded twenty times a
session cannot clear $2.10 a round turn, and no parameter search changes that. Running it
anyway spends a backtest and raises the multiplicity bar for everything tested afterwards.

So the tests here are mostly about **refusing**, and about refusing for the right reason. The
distinction the whole design rests on is between a hypothesis that can never pay (a property
of the fee schedule, which more data will not fix) and one that pays but is too small to see
in this sample (a property of the sample, which more data will fix). Conflating those two is
how a research programme wastes a year.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from quant_brain.research import feasibility as fz
from quant_brain.research.genealogy import Hypothesis, Registry, Stage

# =====================================================================================
# THE ECONOMIC GATE
# =====================================================================================

def test_a_two_tick_scalp_traded_all_day_is_refused_before_any_backtest():
    """The case the module was written for. Half a point on MNQ is $1.00 gross at full
    capture and $0.50 at the honest default; the round turn costs $1.72."""
    a = fz.assess(instrument="MNQ", expected_magnitude_points=0.5,
                  expected_trades_per_session=20)
    assert a.verdict is fz.Verdict.INFEASIBLE_COST
    assert a.edge_ratio < 1.0
    assert a.net_per_session < 0
    assert "No parameter search fixes this" in " ".join(a.reasons)


def test_paying_for_itself_but_invisible_is_a_different_verdict():
    """Not the same failure, and the remedy is the opposite: get more data rather than stop."""
    a = fz.assess(instrument="MNQ", expected_magnitude_points=3.0,
                  expected_trades_per_session=1.0)
    assert a.verdict is fz.Verdict.UNTESTABLE_HERE
    assert a.pays_for_itself
    assert a.sessions_needed_corrected > a.sessions_available
    assert "More data fixes this" in " ".join(a.reasons)


def test_a_large_edge_at_low_turnover_is_feasible():
    """The gate must be able to say yes, or the refusals prove nothing."""
    a = fz.assess(instrument="MNQ", expected_magnitude_points=40.0,
                  expected_trades_per_session=1.0, time_in_market=0.1)
    assert a.verdict is fz.Verdict.FEASIBLE
    assert a.sessions_needed_corrected <= a.sessions_available


def test_missing_inputs_produce_UNKNOWN_and_not_a_verdict_about_the_market():
    a = fz.assess(instrument="MNQ", expected_magnitude_points=None,
                  expected_trades_per_session=1.0)
    assert a.verdict is fz.Verdict.UNKNOWN
    assert "gap in the hypothesis, not a finding about the market" in " ".join(a.reasons)


def test_the_default_capture_is_pessimistic_and_matters():
    """Assuming a published effect is captured in full is the commonest way a feasibility
    estimate flatters a hypothesis. The default must be the cautious one."""
    half = fz.assess(instrument="MNQ", expected_magnitude_points=3.0,
                     expected_trades_per_session=1.0)
    full = fz.assess(instrument="MNQ", expected_magnitude_points=3.0,
                     expected_trades_per_session=1.0, capture=1.0)
    assert full.gross_per_round_turn == pytest.approx(2 * half.gross_per_round_turn)
    assert half.gross_per_round_turn < full.gross_per_round_turn


def test_more_trials_make_the_bar_harder_never_easier():
    one = fz.assess(instrument="MNQ", expected_magnitude_points=40.0,
                    expected_trades_per_session=1.0, time_in_market=0.1, trials=1)
    many = fz.assess(instrument="MNQ", expected_magnitude_points=40.0,
                     expected_trades_per_session=1.0, time_in_market=0.1, trials=500)
    assert many.sessions_needed_corrected > one.sessions_needed_corrected


def test_feasibility_is_a_property_of_the_pair_not_of_the_idea():
    """The same mechanism can be comfortable on one contract and hopeless on another, because
    the cost and the point value move independently."""
    out = fz.assess_all(expected_magnitude_points=1.2, expected_trades_per_session=2.0)
    verdicts = {k: v.verdict for k, v in out.items()}
    assert len(set(verdicts.values())) > 1, (
        f"every instrument returned the same verdict {verdicts}; the per-instrument "
        f"arithmetic is not being applied")


@pytest.mark.parametrize("sym,lo,hi", [("MES", 0.9, 1.1), ("MNQ", 1.6, 1.8),
                                       ("ES", 0.6, 0.7), ("NQ", 1.3, 1.5)])
def test_the_break_even_move_matches_the_measured_cost_schedule(sym, lo, hi):
    """The number a researcher should hold in their head. Pinned so a cost change is visible
    here rather than discovered halfway through a study."""
    assert lo <= fz.break_even_magnitude(sym) <= hi


def test_required_accuracy_is_just_above_a_coin_flip():
    """The result that reframed the programme. On MNQ at a 30-minute horizon the bar is a
    51.4% hit rate - so the barrier is not the fee schedule, it is finding any signal at all
    a point or two above chance."""
    p = fz.required_accuracy("MNQ", 62.01)
    assert 0.51 < p < 0.52
    assert fz.required_accuracy("MES", 28.52) > p, (
        "MES needs a higher hit rate than MNQ at the same horizon, because its cost is "
        "larger relative to its typical move")


def test_required_accuracy_falls_as_the_move_grows():
    a = fz.required_accuracy("MNQ", 10.0)
    b = fz.required_accuracy("MNQ", 100.0)
    assert a > b > 0.5


def test_a_zero_move_needs_impossible_accuracy_rather_than_dividing_by_zero():
    assert fz.required_accuracy("MNQ", 0.0) == float("inf")


# =====================================================================================
# CAN WE EVEN SEE A PASSING EDGE?
# =====================================================================================

def test_a_combine_sized_edge_is_visible_on_the_micros_and_not_on_NQ():
    """The instrument-selection result, pinned. It is derived from measured per-session noise
    and the $3,000 target, with no strategy and no backtest involved, so it cannot be a
    selection artefact.

    NQ failing here is the useful half: a strategy good enough to pass the Combine on NQ
    would still be indistinguishable from noise in this sample, so a null result on NQ is not
    evidence of absence. On MES and MNQ it is.
    """
    assert fz.combine_requirement("MES").a_passing_edge_would_be_visible
    assert fz.combine_requirement("MNQ").a_passing_edge_would_be_visible
    assert not fz.combine_requirement("NQ").a_passing_edge_would_be_visible


def test_a_longer_runway_lowers_the_economic_bar_and_not_the_epistemic_one():
    fast = fz.combine_requirement("MNQ", sessions_to_target=30)
    slow = fz.combine_requirement("MNQ", sessions_to_target=120)
    assert fast.target_per_session > slow.target_per_session
    assert fast.detectable_per_session == pytest.approx(slow.detectable_per_session), (
        "how long you take to pass cannot change how much data we hold")


def test_more_participation_means_more_noise_to_see_through():
    quiet = fz.combine_requirement("MNQ", time_in_market=0.05)
    busy = fz.combine_requirement("MNQ", time_in_market=1.00)
    assert busy.detectable_per_session > quiet.detectable_per_session


# =====================================================================================
# PREREGISTRATION AND LINEAGE
# =====================================================================================

@pytest.fixture
def registry():
    return Registry(Path(tempfile.mkdtemp()) / "h.jsonl")


def _h(hid: str, **kw) -> Hypothesis:
    base = dict(id=hid, title="t", mechanism_id="M-1", prediction=f"claim {hid}",
                falsified_if="mean per session <= 0 on validation", instruments=("MNQ",))
    base.update(kw)
    return Hypothesis(**base)


def test_the_same_claim_cannot_be_registered_twice(registry):
    """Re-running a claim does not make it more true, and counting it twice inflates the
    denominator against everything else in the programme."""
    registry.preregister(_h("H001"))
    with pytest.raises(ValueError, match="same claim"):
        registry.preregister(_h("H002", prediction="claim H001"))


def test_a_variant_must_say_why_it_differs_from_its_parent():
    """A variant with no stated reason is indistinguishable from a parameter sweep."""
    with pytest.raises(ValueError, match="why it differs"):
        _h("H001-A", parent="H001")


def test_the_budget_ladder_cannot_be_skipped(registry):
    """Each rung spends a little more of the unseen data than the last, so skipping one
    spends the expensive data first."""
    registry.preregister(_h("H001"))
    with pytest.raises(ValueError, match="cannot jump"):
        registry.record("H001", stage=Stage.FINAL_HOLDOUT, result={})
    registry.record("H001", stage=Stage.DISCOVERY, result={"net": 1.0})
    assert registry.get("H001").stage is Stage.DISCOVERY


def test_a_result_driven_lineage_costs_more_trials(registry):
    """The whole point of the module. Each generation chosen by looking at the last is
    another look at the data, and the multiplicity bar has to know."""
    registry.preregister(_h("H001"))
    registry.preregister(_h("H001-A", prediction="claim A", parent="H001",
                            modification_reason="H001 was positive only in high vol",
                            result_driven=True))
    registry.preregister(_h("H001-A2", prediction="claim A2", parent="H001-A",
                            modification_reason="A held only on Nasdaq",
                            result_driven=True))
    assert registry.effective_trials("H001") == 1
    assert registry.effective_trials("H001-A") == 2
    assert registry.effective_trials("H001-A2") == 3


def test_a_predicted_lineage_costs_no_extra_trials(registry):
    """A variant written from theory rather than from a result is not a second look at the
    data, and must not be penalised as though it were."""
    registry.preregister(_h("H001"))
    registry.preregister(_h("H001-B", prediction="claim B", parent="H001",
                            modification_reason="the source paper predicts a vol dependence",
                            result_driven=False))
    assert registry.effective_trials("H001-B") == 1


def test_lineage_and_descendants_agree(registry):
    registry.preregister(_h("H001"))
    registry.preregister(_h("H001-A", prediction="a", parent="H001",
                            modification_reason="r"))
    registry.preregister(_h("H001-A2", prediction="b", parent="H001-A",
                            modification_reason="r"))
    assert [h.id for h in registry.lineage("H001-A2")] == ["H001", "H001-A", "H001-A2"]
    assert {h.id for h in registry.descendants("H001")} == {"H001-A", "H001-A2"}


def test_the_record_survives_a_reload(registry):
    """Append-only, because a prediction that can be edited after the result is not a
    preregistration."""
    registry.preregister(_h("H001"))
    registry.record("H001", stage=Stage.DISCOVERY, result={"net": -100.0})
    again = Registry(registry.path)
    assert again.get("H001").stage is Stage.DISCOVERY
    assert again.get("H001").results[-1]["net"] == -100.0


def test_the_fingerprint_ignores_the_name_and_not_the_claim():
    """Identity is the claim, not the label. Renaming a hypothesis must not let it be
    registered a second time, and changing the instrument must."""
    a = _h("H001", prediction="fading extension pays")
    b = _h("H999", prediction="fading extension pays")
    assert a.fingerprint == b.fingerprint, "the same claim under two names is one trial"
    assert _h("H001", prediction="fading extension pays",
              instruments=("MES",)).fingerprint != a.fingerprint
    assert _h("H001", prediction="something else").fingerprint != a.fingerprint
