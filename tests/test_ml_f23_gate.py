"""F-23's resolution rule: when is a gate admission a finding, and when is it a coin flip?

F-20 (d) found a bit-identical flow store changing 6 of 8 gate decisions, four of them on a
**0.0014 |IC| gap between `dvol30` and `amihud30`, two columns correlated at 0.88**. F-17 printed
neither number, so its flow verdict was reported as a property of `dvol30` when the window could
not tell `dvol30` from `amihud30` at all. F-23's rule says an admission whose |IC| margin over the
rival it displaced is smaller than the winner's own IC standard error is UNRESOLVED.

These test the rule and the standard error it is measured against, not the gate's screening legs -
those are F-16's and F-17's and are unchanged.
"""
from __future__ import annotations

import numpy as np
import pytest

import ml_f17


# --------------------------------------------------------------------------------------------
# the standard error, backed out of the t the gate already computed
# --------------------------------------------------------------------------------------------

def test_ic_standard_error_is_recovered_from_the_mean_and_its_own_t():
    """`f16._ic` returns (mean, t) with t = mean / se, so no second pass over the window."""
    assert ml_f17.ic_se({"ic": 0.0200, "ic_t": 8.0}) == pytest.approx(0.0025)


def test_the_standard_error_is_a_magnitude_and_does_not_care_which_way_the_ic_points():
    """Every flow column the gate admits carries a NEGATIVE IC; the screen reads |IC|."""
    assert (ml_f17.ic_se({"ic": -0.0200, "ic_t": -8.0})
            == ml_f17.ic_se({"ic": 0.0200, "ic_t": 8.0}))


@pytest.mark.parametrize("row", [{"ic": 0.01, "ic_t": 0.0},
                                 {"ic": np.nan, "ic_t": 4.0},
                                 {"ic": 0.01, "ic_t": np.nan},
                                 {}])
def test_an_unusable_t_gives_no_standard_error_rather_than_a_wrong_one(row):
    assert not np.isfinite(ml_f17.ic_se(row))


# --------------------------------------------------------------------------------------------
# the rule
# --------------------------------------------------------------------------------------------

def _admitted(ic=0.02325, ic_t=-7.8):
    return {"admitted_pooled": True, "ic": ic, "ic_t": ic_t}


def test_f20s_own_dvol30_case_is_the_coin_flip_the_rule_exists_to_catch():
    """|IC| 0.02325 (se 0.00298) admitted over amihud30 at 0.02187 - a gap of 0.46 se."""
    r = _admitted()
    d = {"rival": "amihud30", "rival_ic": -0.02187, "pair_rho": 0.876, "gap": 0.00138}
    assert ml_f17.resolution(r, d) == "UNRESOLVED"
    assert abs(d["gap"]) < ml_f17.ic_se(r)


def test_a_margin_wider_than_the_winners_own_standard_error_resolves():
    r = _admitted()
    assert ml_f17.resolution(r, {"rival": "x", "rival_ic": 0.01, "pair_rho": 0.9,
                                 "gap": 0.01}) == "RESOLVED"


def test_the_rule_reads_the_size_of_the_gap_not_its_sign():
    """Clause 4c is greedy on |IC|, so the gap is never negative - but the rule must not depend
    on that, or a future ordering change would silently turn coin flips into findings."""
    r = _admitted()
    assert ml_f17.resolution(r, {"gap": -0.00138, "rival": "amihud30", "rival_ic": -0.02187,
                                 "pair_rho": 0.876}) == "UNRESOLVED"
    assert ml_f17.resolution(r, {"gap": -0.01, "rival": "x", "rival_ic": 0.01,
                                 "pair_rho": 0.9}) == "RESOLVED"


def test_an_admission_that_displaced_nothing_is_uncontested_not_resolved():
    """The rule compares a winner with a rival. With no rival it has nothing to say, and saying
    RESOLVED there would launder F-23's silence into a verdict."""
    assert ml_f17.resolution(_admitted(), None) == "UNCONTESTED"


def test_a_candidate_the_gate_rejected_carries_no_verdict_at_all():
    assert ml_f17.resolution({"admitted_pooled": False, "ic": 0.02, "ic_t": 8.0}, None) == ""


def test_an_unmeasurable_margin_is_unresolved_rather_than_admitted():
    """Fail toward the weaker claim: a gap or a standard error that is not finite means the
    window could not tell the two columns apart, which is exactly UNRESOLVED."""
    assert ml_f17.resolution(_admitted(ic_t=0.0), {"gap": 0.01}) == "UNRESOLVED"
    assert ml_f17.resolution(_admitted(), {"gap": np.nan}) == "UNRESOLVED"


# --------------------------------------------------------------------------------------------
# the print
# --------------------------------------------------------------------------------------------

def test_the_admission_line_names_the_rival_the_gap_and_the_verdict():
    line = ml_f17.describe_admission(
        {"feature": "dvol30", **_admitted()},
        {"rival": "amihud30", "rival_ic": -0.02187, "pair_rho": 0.876, "gap": 0.00138},
        floor=0.01518)
    for piece in ("dvol30", "amihud30", "0.876", "UNRESOLVED", "+0.00807"):
        assert piece in line, f"{piece!r} missing from {line!r}"


def test_an_uncontested_admission_says_so_instead_of_printing_an_empty_rival():
    line = ml_f17.describe_admission({"feature": "ofi_sess", **_admitted()}, None, floor=0.009)
    assert "UNCONTESTED" in line and "displaced nothing" in line
