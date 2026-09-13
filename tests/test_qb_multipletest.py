"""Tests for the multiple-testing controls.

Three kinds of test, in this order:

1. KNOWN ANSWERS. Every p-value adjustment is checked against a value computed by hand (and
   cross-checked against R's `p.adjust`, which is the reference implementation everyone else
   is checked against too). An adjustment that is merely self-consistent is worthless; these
   pin the arithmetic to numbers that exist outside this file.

2. PROPERTIES THE METHODS ARE CHOSEN FOR. Holm dominating Bonferroni, BH controlling FDR on
   simulated nulls, the DSR falling as the search widens, PBO sitting at 0.5 on noise and
   near 0 on a persistent edge, SPA being immune to padding a search with hopeless variants.
   These are simulations with fixed seeds, so they are reproducible, and with tolerances
   wide enough to be about the property rather than about the seed.

3. EVERY GUARD FIRES. `test_every_guard_in_the_module_has_a_test` counts the refusal sites in
   the source and fails if one is added without a test here. A guard nobody has fired is a
   guard nobody knows works, and this module's whole claim is that it refuses rather than
   invents.
"""
from __future__ import annotations

import inspect
import math
import re
from pathlib import Path

import numpy as np
import pytest

from quant_brain.core import multipletest as mt
from quant_brain.core import stats

ALPHA = 0.05

#: The worked example used for every known-answer check. Chosen because R's p.adjust gives
#: three different, hand-verifiable answers on it and because it straddles the boundary:
#: Bonferroni and Holm reject exactly one, BH rejects all five, BY rejects none.
P5 = [0.01, 0.02, 0.03, 0.04, 0.05]


def _panel(rng, t=400, k=20, sd=0.01):
    return rng.normal(0.0, sd, size=(t, k))


def _p(r: mt.BootstrapTestResult) -> float:
    """The p-value of a result that must be available. Asserts rather than assumes."""
    assert r.pvalue is not None, f"expected an available result, got: {r.describe()}"
    return r.pvalue


def _v(d: mt.DeflatedSharpe) -> float:
    """The value of a DSR that must be available."""
    assert d.value is not None, f"expected an available DSR, got: {d.describe()}"
    return d.value


def _dsr(n_trials: int, *, sharpe: float = 0.12, n_obs: int = 500,
         var_trials: float = 0.0025, skew: float = -0.5,
         kurtosis: float = 6.0) -> mt.DeflatedSharpe:
    """A daily Sharpe of 0.12 (about 1.9 annualised) over 500 observations, mildly fat-tailed
    and negatively skewed - the profile of a candidate this repository would promote."""
    return mt.deflated_sharpe(sharpe=sharpe, n_obs=n_obs, n_trials=n_trials,
                              var_trials=var_trials, skew=skew, kurtosis=kurtosis)


# ======================================================================================
# KNOWN ANSWERS
# ======================================================================================

def test_bonferroni_known_answer():
    r = mt.bonferroni(P5, ALPHA)
    assert r.adjusted == pytest.approx([0.05, 0.10, 0.15, 0.20, 0.25])
    assert list(r.rejected) == [True, False, False, False, False]
    assert r.n_tests == 5 and r.n_rejected == 1
    assert list(r.survivors) == [0]


def test_holm_known_answer():
    """R: p.adjust(c(.01,.02,.03,.04,.05), "holm") -> 0.05 0.08 0.09 0.09 0.09.

    Hand-computed: the running maximum of (n-i+1)*p_(i) is 5*.01=.05, 4*.02=.08, 3*.03=.09,
    max(.09, 2*.04)=.09, max(.09, 1*.05)=.09. The last two are held up by the third, which is
    the step-down rule made visible: once testing stops, nothing below it can be rejected.
    """
    r = mt.holm(P5, ALPHA)
    assert r.adjusted == pytest.approx([0.05, 0.08, 0.09, 0.09, 0.09])
    assert list(r.rejected) == [True, False, False, False, False]
    assert r.dependence == "arbitrary" and r.controls == "FWER"


def test_benjamini_hochberg_known_answer():
    """R: p.adjust(..., "BH") -> 0.05 five times, so all five survive at alpha=0.05.

    (n/i)*p_(i) is 0.05 for every i in this vector, which is what makes it a good example:
    the same five p-values that give Bonferroni one rejection give BH five.
    """
    r = mt.benjamini_hochberg(P5, ALPHA)
    assert r.adjusted == pytest.approx([0.05] * 5)
    assert list(r.rejected) == [True] * 5
    assert r.controls == "FDR" and r.dependence == "positive"


def test_benjamini_yekutieli_known_answer():
    """R: p.adjust(..., "BY") -> 0.1141667 five times. That is BH times c(5) = 2.2833."""
    r = mt.benjamini_yekutieli(P5, ALPHA)
    assert r.adjusted == pytest.approx([0.1141667] * 5, abs=1e-6)
    assert not r.rejected.any(), "BY's harmonic penalty must cost all five rejections here"
    assert r.dependence == "arbitrary"


def test_harmonic_is_the_harmonic_number():
    assert mt.harmonic(1) == pytest.approx(1.0)
    assert mt.harmonic(5) == pytest.approx(1 + 1 / 2 + 1 / 3 + 1 / 4 + 1 / 5)
    assert mt.harmonic(100) == pytest.approx(5.187, abs=1e-3)
    # The BY penalty IS this number, so the two must agree exactly.
    by = mt.benjamini_yekutieli(P5, ALPHA)
    bh = mt.benjamini_hochberg(P5, ALPHA)
    assert by.adjusted == pytest.approx(bh.adjusted * mt.harmonic(5))


def test_pvalues_from_t_known_answers():
    two = mt.pvalues_from_t([0.0, 1.959963985, 2.575829304])
    assert two == pytest.approx([1.0, 0.05, 0.01], abs=1e-8)
    one = mt.pvalues_from_t([0.0, 1.644853627, -1.644853627], two_sided=False)
    assert one == pytest.approx([0.5, 0.05, 0.95], abs=1e-8)


def test_the_p_value_form_of_bonferroni_agrees_with_the_t_form_in_stats():
    """Not a reimplementation: the same rule on two scales must reject the same set.

    `stats.bonferroni_threshold` is what `Ledger.verdict` already applies. If this module's
    p-value form disagreed with it, the repository would have two Bonferronis.
    """
    ts = np.array([1.2, 2.4, 3.1, 3.9, 0.3, 4.6])
    n = ts.size
    thr = stats.bonferroni_threshold(n, ALPHA)
    p_form = mt.bonferroni(mt.pvalues_from_t(ts), ALPHA).rejected
    t_form = np.abs(ts) > thr
    assert list(p_form) == list(t_form)


def test_expected_max_sharpe_hand_computed():
    """SR0 at N=2 collapses to sqrt(V) * gamma * Z^-1(1 - 1/(2e)), since Z^-1(1/2) = 0."""
    from statistics import NormalDist
    v = 0.04
    hand = math.sqrt(v) * mt.EULER_MASCHERONI * NormalDist().inv_cdf(1 - 1 / (2 * math.e))
    assert mt.expected_max_sharpe(2, v) == pytest.approx(hand)
    assert mt.expected_max_sharpe(2, v) == pytest.approx(0.103951, abs=1e-6)


def test_expected_max_sharpe_grows_with_the_search_and_only_slowly():
    """sqrt(2 V log N): a hundredfold wider search barely doubles the bar. Both halves of
    that sentence are the point, so both are asserted."""
    v = 0.01
    values = [mt.expected_max_sharpe(n, v) for n in (2, 10, 100, 1000, 10000)]
    assert all(a < b for a, b in zip(values, values[1:], strict=False))
    assert values[2] / values[1] < 2.0, "10 -> 100 trials must not even double the bar"
    # The sqrt(2 V log N) asymptote is approached from below; at N=10,000 it is still 10%
    # above the exact expression, which is why the exact one is what the module computes.
    asymptote = math.sqrt(2 * v * math.log(10000))
    assert values[-1] < asymptote
    assert values[-1] == pytest.approx(asymptote, rel=0.15)


def test_sharpe_moments_on_a_gaussian_sample():
    r = np.random.default_rng(4).normal(0.05, 1.0, size=20000)
    sr, n, skew, kurt = mt.sharpe_moments(r)
    assert n == 20000
    assert sr == pytest.approx(0.05, abs=0.02)
    assert skew == pytest.approx(0.0, abs=0.05)
    assert kurt == pytest.approx(3.0, abs=0.10), "NON-excess kurtosis: 3, not 0"


# ======================================================================================
# HOLM DOMINATES BONFERRONI - THE REASON IT IS HERE
# ======================================================================================

def test_holm_rejects_a_superset_of_bonferroni_on_every_random_family():
    """Uniform dominance, at the same FWER and the same (absent) dependence assumption."""
    rng = np.random.default_rng(0)
    strictly_more = 0
    for _ in range(500):
        n = int(rng.integers(2, 40))
        # A mixture, not pure uniforms: with all-null families neither method rejects and
        # the dominance claim would be vacuously true on 500 empty comparisons.
        z = rng.normal(0.0, 1.0, n)
        z[: max(1, n // 4)] += 3.5
        p = mt.pvalues_from_t(z, two_sided=False)
        b, h = mt.bonferroni(p, ALPHA), mt.holm(p, ALPHA)
        assert np.all(h.adjusted <= b.adjusted + 1e-15)
        assert np.all(b.rejected <= h.rejected), "Holm dropped a Bonferroni rejection"
        strictly_more += int(h.n_rejected > b.n_rejected)
    # Measured: 41 of 500. The gain is real but modest - Holm only pulls ahead when a second
    # p-value falls between alpha/n and alpha/(n-1), which is a narrow window. Worth taking,
    # since it costs nothing, and worth not overselling.
    assert strictly_more > 20, "if Holm rarely rejects more, the dominance claim is empty"


def test_holm_and_bonferroni_agree_on_the_smallest_p_value():
    """They must: Holm's first step IS the Bonferroni bar. The gain is only downstream.

    Hand-picked to sit in the gap: at n=3 the Bonferroni bar is 0.0167 and Holm's second
    step is 0.025, so p=0.02 is rejected by one method and not the other.
    """
    p = [0.01, 0.02, 0.50]
    assert mt.holm(p, ALPHA).rejected[0] == mt.bonferroni(p, ALPHA).rejected[0]
    assert mt.holm(p, ALPHA).n_rejected == 2
    assert mt.bonferroni(p, ALPHA).n_rejected == 1


def test_holm_controls_the_family_wise_error_rate_under_the_global_null():
    """2,000 families of 10 independent nulls: at most ~5% may produce ANY rejection."""
    rng = np.random.default_rng(1)
    any_rejection = sum(bool(mt.holm(rng.random(10), ALPHA).n_rejected) for _ in range(2000))
    fwer = any_rejection / 2000
    assert fwer <= ALPHA + 0.02, f"Holm's FWER came out {fwer:.4f}"


# ======================================================================================
# FDR CONTROL, MEASURED
# ======================================================================================

def _fdr_simulation(method, reps=400, n=200, n_alt=20, effect=3.5, seed=0):
    """(mean false discovery proportion, mean rejections) over `reps` simulated families.

    One-sided tests of independent statistics, `n_alt` of which have a real effect. One-sided
    is deliberate: it is the form under which correlated statistics satisfy BH's PRDS
    condition, and it is the form a strategy family is actually tested in.
    """
    rng = np.random.default_rng(seed)
    fdps, counts = [], []
    for _ in range(reps):
        z = rng.normal(0.0, 1.0, n)
        z[:n_alt] += effect
        r = method(mt.pvalues_from_t(z, two_sided=False), ALPHA)
        total = r.n_rejected
        false = int(np.count_nonzero(r.rejected[n_alt:]))
        fdps.append(false / total if total else 0.0)
        counts.append(total)
    return float(np.mean(fdps)), float(np.mean(counts))


def test_benjamini_hochberg_controls_fdr_on_simulated_nulls():
    """The guarantee is E[FDP] <= alpha * n0/n = 0.045 here. Measured: ~0.046."""
    fdp, rejections = _fdr_simulation(mt.benjamini_hochberg)
    assert fdp <= ALPHA + 0.01, f"BH's measured FDR was {fdp:.4f}"
    assert fdp > 0.02, ("BH came out far below its own bound, which means the simulation is "
                        "not exercising the correction rather than that BH is conservative")
    assert rejections > 10, "BH must still find most of the 20 real effects"


def test_benjamini_yekutieli_also_controls_fdr_and_is_strictly_more_conservative():
    fdp_by, rej_by = _fdr_simulation(mt.benjamini_yekutieli)
    fdp_bh, rej_bh = _fdr_simulation(mt.benjamini_hochberg)
    assert fdp_by <= ALPHA
    assert fdp_by < fdp_bh, "BY must buy its dependence-robustness with a lower FDP"
    assert rej_by < rej_bh, "and pay for it in rejections - that is the harmonic penalty"


def test_the_rejection_sets_nest_bonferroni_in_holm_in_bh():
    """The power ordering, on one family, in one line: FWER-strict to FDR-loose."""
    rng = np.random.default_rng(2)
    z = rng.normal(0.0, 1.0, 200)
    z[:20] += 3.5
    p = mt.pvalues_from_t(z, two_sided=False)
    b, h, by, bh = (mt.bonferroni(p), mt.holm(p), mt.benjamini_yekutieli(p),
                    mt.benjamini_hochberg(p))
    assert np.all(b.rejected <= h.rejected)
    assert np.all(by.rejected <= bh.rejected), "BY must be a subset of BH, always"
    assert b.n_rejected <= h.n_rejected <= by.n_rejected <= bh.n_rejected


def test_holm_controls_fdr_too_but_at_a_cost_in_discoveries():
    """FWER control implies FDR control. The reason to prefer BH is power, not validity."""
    fdp_holm, rej_holm = _fdr_simulation(mt.holm)
    _, rej_bh = _fdr_simulation(mt.benjamini_hochberg)
    assert fdp_holm < 0.02
    assert rej_bh > rej_holm * 1.2, "BH must find materially more of the real effects"


# ======================================================================================
# REACHING THE DEPENDENCE-APPROPRIATE VARIANT
# ======================================================================================

def test_control_fdr_defaults_to_the_variant_valid_under_arbitrary_dependence():
    """The default must be the safe one: strategies sharing a market are dependent."""
    default = mt.control_fdr(P5, ALPHA)
    assert default.method == "benjamini-yekutieli"
    assert default.dependence == "arbitrary"
    assert mt.control_fdr(P5, ALPHA, dependence="positive").method == "benjamini-hochberg"
    assert mt.control_fdr(P5, ALPHA, dependence="independent").method == "benjamini-hochberg"


def test_control_fwer_is_holm_whatever_the_caller_believes_about_dependence():
    for dep in mt.DEPENDENCE:
        r = mt.control_fwer(P5, ALPHA, dependence=dep)
        assert r.method == "holm-bonferroni"
        assert r.dependence == "arbitrary", "Holm's validity does not depend on the claim"
        assert dep in r.note, "but the claim must be recorded at the call site"


def test_an_unknown_dependence_claim_is_refused_rather_than_defaulted():
    for fn in (mt.control_fdr, mt.control_fwer):
        with pytest.raises(ValueError, match="dependence must be one of"):
            fn(P5, ALPHA, dependence="mild")


# ======================================================================================
# THE TRIAL COUNT IS STRUCTURAL, AS IN registry.py
# ======================================================================================

def test_no_correction_accepts_a_trial_count_argument():
    """`Ledger.verdict` refuses an n_trials keyword; nothing here may reintroduce one.

    The vector IS the trial count. Understating the search has to mean deleting entries from
    a list the caller can see, not typing a smaller integer.
    """
    forbidden = {"n_trials", "trials", "num_trials", "n", "count", "override", "force"}
    for fn in (mt.bonferroni, mt.holm, mt.benjamini_hochberg, mt.benjamini_yekutieli,
               mt.control_fwer, mt.control_fdr, mt.reality_check, mt.spa, mt.pbo,
               mt.deflated_sharpe_from_returns):
        params = set(inspect.signature(fn).parameters)
        assert not (forbidden & params), f"{fn.__name__} exposes {forbidden & params}"


def test_the_only_way_to_weaken_the_correction_is_to_withhold_trials():
    """And doing so is visible in the argument, which is the property registry.py protects."""
    p = list(np.linspace(0.001, 0.5, 40))
    full = mt.holm(p, ALPHA)
    hidden = mt.holm(p[:5], ALPHA)
    assert hidden.adjusted[0] < full.adjusted[0]
    assert hidden.n_tests == 5 and full.n_tests == 40


def test_the_deflated_sharpe_derives_its_trial_count_from_the_vector_of_trial_sharpes():
    rng = np.random.default_rng(5)
    returns = rng.normal(0.05, 1.0, size=500)
    sharpes = rng.normal(0.0, 0.05, size=64)
    out = mt.deflated_sharpe_from_returns(returns, trial_sharpes=sharpes)
    assert out.n_trials == 64, "N is len(trial_sharpes), not an argument"
    sr, n, skew, kurt = mt.sharpe_moments(returns)
    explicit = mt.deflated_sharpe(sharpe=sr, n_obs=n, n_trials=64,
                                  var_trials=float(sharpes.var(ddof=1)), skew=skew,
                                  kurtosis=kurt)
    assert out.value == pytest.approx(explicit.value)


# ======================================================================================
# WHITE'S REALITY CHECK AND HANSEN'S SPA
# ======================================================================================

def test_the_best_of_a_set_of_pure_noise_strategies_looks_significant_and_the_reality_check_says_no():
    """The demonstration the method exists for, measured over 30 independent searches.

    Each search is 15 zero-edge candidates over 250 periods. The naive one-sided t on the
    best of them clears 5% in 21 of the 30 searches; the reality check clears 5% in 2, which
    is its nominal size.
    """
    rng = np.random.default_rng(31337)
    naive_hits = rc_hits = spa_hits = 0
    for _ in range(30):
        m = _panel(rng, t=250, k=15)
        best_t = float((m.mean(0) / (m.std(0, ddof=1) / math.sqrt(250))).max())
        naive_hits += int(mt.pvalues_from_t([best_t], two_sided=False)[0] <= ALPHA)
        rc_hits += int(_p(mt.reality_check(m, block=4, reps=200, seed=5)) <= ALPHA)
        spa_hits += int(_p(mt.spa(m, block=4, reps=200, seed=5)) <= ALPHA)
    assert naive_hits >= 15, f"the naive best-of-K only fired {naive_hits}/30 times"
    assert rc_hits <= 6, f"the reality check fired {rc_hits}/30 times on pure noise"
    assert spa_hits <= 6, f"SPA fired {spa_hits}/30 times on pure noise"


def test_a_real_edge_survives_both_bootstrap_tests():
    rng = np.random.default_rng(7)
    m = _panel(rng)
    m[:, 3] += 0.0025
    rc = mt.reality_check(m, block=5, reps=1000, seed=1)
    sp = mt.spa(m, block=5, reps=1000, seed=1)
    assert _p(rc) < 0.01 and _p(sp) < 0.01
    assert rc.best == 3 and sp.best == 3


def test_padding_a_search_with_hopeless_variants_fools_the_reality_check_and_not_spa():
    """The reason SPA is the default here, measured rather than argued.

    Same marginal edge, then 80 deliberately terrible candidates are added. White's
    recentring leaves every one of them contributing to the bootstrap maximum, so the
    p-value of the good candidate rises from 0.03 to 0.13 and it stops being significant -
    a search made to look innocent by adding candidates nobody believed in. Hansen's
    consistent recentring drops them and the p-value does not move at all.
    """
    rng = np.random.default_rng(7)
    m = _panel(rng)
    m[:, 3] += 0.0015
    hopeless = rng.normal(-0.006, 0.01, size=(m.shape[0], 80))
    padded = np.column_stack([m, hopeless])

    rc = _p(mt.reality_check(m, block=5, reps=1000, seed=1))
    rc_pad = _p(mt.reality_check(padded, block=5, reps=1000, seed=1))
    sp = _p(mt.spa(m, block=5, reps=1000, seed=1))
    sp_pad = _p(mt.spa(padded, block=5, reps=1000, seed=1))

    assert rc <= ALPHA < rc_pad, f"padding moved the reality check from {rc} to {rc_pad}"
    assert rc_pad > 3 * rc
    assert sp_pad == pytest.approx(sp, abs=0.01)
    assert sp_pad <= ALPHA


def test_hansens_three_p_values_bracket_in_the_documented_order():
    rng = np.random.default_rng(9)
    m = _panel(rng)
    m[:, 0] += 0.0012
    m[:, 1] -= 0.004
    r = mt.spa(m, block=5, reps=1000, seed=2)
    lower, upper = r.pvalue_lower, r.pvalue_upper
    assert lower is not None and upper is not None
    assert lower <= _p(r) <= upper


def test_both_bootstrap_tests_are_deterministic_under_a_seed():
    rng = np.random.default_rng(3)
    m = _panel(rng, t=200, k=8)
    a = mt.reality_check(m, block=5, reps=200, seed=42)
    b = mt.reality_check(m, block=5, reps=200, seed=42)
    assert _p(a) == _p(b)
    assert a.statistic == b.statistic
    assert _p(mt.spa(m, block=5, reps=200, seed=42)) == _p(mt.spa(m, block=5, reps=200, seed=42))
    # A different seed may differ, but must still produce a number.
    assert 0.0 <= _p(mt.reality_check(m, block=5, reps=200, seed=43)) <= 1.0


def test_the_panel_helper_builds_the_orientation_the_tests_expect():
    cols = [np.arange(5.0), np.arange(5.0) * 2]
    p = mt.panel(cols)
    assert p.shape == (5, 2)
    assert list(p[:, 1]) == [0.0, 2.0, 4.0, 6.0, 8.0]


def test_a_short_history_returns_an_explicit_unavailable_rather_than_a_p_value():
    """No false precision: 20 periods cannot support a stationary bootstrap, and the honest
    output is a refusal with a reason, not a plausible decimal."""
    m = _panel(np.random.default_rng(6), t=20, k=5)
    for fn in (mt.reality_check, mt.spa):
        r = fn(m, block=3, reps=200, seed=0)
        assert r.pvalue is None and not r.available
        assert r.statistic is None
        assert "20 periods is below the 30" in r.reason
        assert "UNAVAILABLE" in r.describe()


def test_an_available_result_describes_itself_with_its_numbers():
    m = _panel(np.random.default_rng(6), t=120, k=5)
    text = mt.spa(m, block=4, reps=200, seed=0).describe()
    assert "hansen-spa" in text and "p=" in text and "lower" in text


# ======================================================================================
# DEFLATED SHARPE RATIO
# ======================================================================================

def test_the_deflated_sharpe_falls_as_the_number_of_trials_rises():
    """The whole point of the statistic. Measured: 0.978 at 2 trials, 0.179 at 1,000."""
    values = [_v(_dsr(n)) for n in (2, 10, 50, 100, 1000)]
    assert all(a > b for a, b in zip(values, values[1:], strict=False)), values
    assert values[0] == pytest.approx(0.9784, abs=1e-3)
    assert values[-1] == pytest.approx(0.1788, abs=1e-3)


def test_a_sharpe_that_passes_undeflated_fails_once_the_search_is_counted():
    """The narrative version, and the reason this is not the probabilistic Sharpe ratio."""
    few, many = _dsr(2), _dsr(100)
    assert few.survives and not many.survives
    sr0 = many.expected_max_sharpe
    assert sr0 is not None and sr0 > many.sharpe, (
        "at 100 trials the expected maximum from noise alone exceeds the observed Sharpe")


def test_negative_skew_and_fat_tails_pull_the_deflated_sharpe_toward_a_coin_flip():
    """Both directions, because the naive statement of this property is wrong.

    The moments widen the Sharpe's sampling distribution, so they move the DSR TOWARD 0.5.
    For a candidate above its expected maximum - the one anybody is looking at - that is a
    fall, which is why a Gaussian default flatters. For one already below it, the same
    inflation raises the number. This test pins both, and the second half is what caught the
    module docstring claiming the effect was one-directional.
    """
    passing_gauss = _v(_dsr(10, skew=0.0, kurtosis=3.0))
    passing_real = _v(_dsr(10))
    failing_gauss = _v(_dsr(1000, skew=0.0, kurtosis=3.0))
    failing_real = _v(_dsr(1000))
    assert passing_gauss > 0.5 and failing_gauss < 0.5
    assert passing_real < passing_gauss
    assert failing_real > failing_gauss


def test_a_wider_spread_of_trial_sharpes_deflates_harder():
    narrow = _v(_dsr(50, var_trials=0.0004))
    wide = _v(_dsr(50, var_trials=0.0100))
    assert wide < narrow, (
        "V is what makes a correlated search cheaper than an independent one")


def test_one_trial_is_unavailable_rather_than_an_undeflated_number():
    r = _dsr(1)
    assert r.value is None and not r.available and not r.survives
    assert "nothing to deflate" in r.reason
    assert "UNAVAILABLE" in r.describe()


def test_zero_variance_across_trials_is_unavailable_rather_than_a_silent_non_correction():
    r = _dsr(50, var_trials=0.0)
    assert r.value is None
    assert "UNDEFLATED" in r.reason


def test_too_few_observations_for_a_fourth_moment_is_unavailable():
    r = _dsr(50, n_obs=12)
    assert r.value is None
    assert "fourth moment from 12 points" in r.reason


def test_an_impossible_variance_term_is_unavailable_rather_than_a_nan():
    """1 - g3*SR + (g4-1)/4*SR^2 can go negative on inconsistent moment estimates. A NaN
    would propagate; an unavailable result says which assumption broke."""
    r = _dsr(50, sharpe=1.5, skew=1.2, kurtosis=1.0)
    assert r.value is None
    assert "not a variance" in r.reason


def test_deflated_sharpe_from_returns_matches_the_moments_of_the_series():
    rng = np.random.default_rng(8)
    returns = rng.normal(0.03, 1.0, size=800)
    trials = rng.normal(0.0, 0.04, size=40)
    r = mt.deflated_sharpe_from_returns(returns, trial_sharpes=trials)
    sr, n, skew, kurt = mt.sharpe_moments(returns)
    assert r.n_obs == n and r.sharpe == pytest.approx(sr)
    assert r.skew == pytest.approx(skew) and r.kurtosis == pytest.approx(kurt)


def test_a_single_trial_sharpe_is_unavailable_from_the_vector_form_too():
    returns = np.random.default_rng(8).normal(0.03, 1.0, size=800)
    r = mt.deflated_sharpe_from_returns(returns, trial_sharpes=[0.02])
    assert r.value is None and "nothing to deflate against" in r.reason


# ======================================================================================
# PROBABILITY OF BACKTEST OVERFITTING
# ======================================================================================

def test_pbo_is_about_one_half_when_every_configuration_is_noise():
    """The defining property: ranking noise is a coin flip.

    Averaged over 40 independent 20-configuration sweeps, because PBO on ONE sweep is very
    noisy - the 70 splits inside a sweep share the same realised data, so they are far from
    independent. Measured: mean 0.547, median 0.514, sd 0.20 across sweeps. A test that
    asserted 0.5 on a single sweep would be asserting a seed.
    """
    rng = np.random.default_rng(2026)
    values = [mt.pbo(rng.normal(0.0, 0.01, size=(600, 20)), n_splits=8).value
              for _ in range(40)]
    mean = float(np.mean(values))
    assert 0.40 <= mean <= 0.62, f"mean PBO on pure noise was {mean:.3f}"
    assert max(values) > 0.7 and min(values) < 0.3, (
        "the per-sweep spread should be wide; if it is not, the estimator is not sampling")


def test_pbo_is_low_when_one_configuration_has_a_persistent_edge():
    """Selection has real skill here, and CSCV must say so on every seed, not on average."""
    for seed in range(500, 508):
        rng = np.random.default_rng(seed)
        m = rng.normal(0.0, 0.01, size=(1200, 25))
        m[:, 7] += 0.0015
        r = mt.pbo(m, n_splits=10)
        assert r.value <= 0.05, f"seed {seed}: PBO {r.value:.3f} on a genuine edge"
        assert (r.selected == 7).mean() > 0.9, "the edge should win in sample nearly always"
        assert r.prob_oos_loss <= 0.05


def test_pbo_reports_the_shape_of_the_experiment_it_ran():
    m = np.random.default_rng(1).normal(0.0, 0.01, size=(600, 12))
    r = mt.pbo(m, n_splits=8)
    assert r.n_combinations == math.comb(8, 4) == 70
    assert r.logits.size == 70 and r.selected.size == 70
    assert r.n_configs == 12 and r.n_splits == 8
    assert 0.0 <= r.value <= 1.0 and np.all(np.isfinite(r.logits))
    assert "PBO" in r.describe() and "70 splits" in r.describe()


def test_pbo_is_deterministic():
    """CSCV enumerates its splits; there is no sampling, so there is nothing to seed."""
    m = np.random.default_rng(1).normal(0.0, 0.01, size=(600, 12))
    assert mt.pbo(m, n_splits=8).value == mt.pbo(m, n_splits=8).value


def test_pbo_accepts_a_custom_metric():
    m = np.random.default_rng(1).normal(0.0, 0.01, size=(600, 12))
    total = mt.pbo(m, n_splits=8, metric=lambda block: block.sum(axis=0))
    assert 0.0 <= total.value <= 1.0


def test_the_degradation_slope_is_negative_when_selection_is_overfitting():
    """The IS-best's out-of-sample score falls as its in-sample score rises: the visual
    signature of overfitting in the CSCV paper, reduced to one number."""
    m = np.random.default_rng(21).normal(0.0, 0.01, size=(600, 30))
    r = mt.pbo(m, n_splits=8)
    assert r.degradation_slope is not None and r.degradation_slope < 0.0


# ======================================================================================
# EVERY GUARD FIRES
# ======================================================================================

def test_alpha_outside_the_unit_interval_is_refused():
    for bad in (0.0, 1.0, -0.1, 1.5):
        with pytest.raises(ValueError, match="alpha must lie strictly"):
            mt.holm(P5, bad)


def test_an_empty_family_is_refused():
    with pytest.raises(ValueError, match="empty family"):
        mt.holm([], ALPHA)


def test_a_nan_p_value_is_refused_rather_than_dropped():
    """Dropping it would shrink the trial count, which is the number this module protects."""
    with pytest.raises(ValueError, match="failed to run"):
        mt.holm([0.01, float("nan"), 0.3], ALPHA)


def test_p_values_outside_zero_one_are_refused_with_the_likely_cause_named():
    with pytest.raises(ValueError, match="are these t-statistics"):
        mt.holm([0.01, 2.4, 0.3], ALPHA)


def test_pvalues_from_t_refuses_empty_and_non_finite_input():
    with pytest.raises(ValueError, match="no t-statistics"):
        mt.pvalues_from_t([])
    with pytest.raises(ValueError, match="not finite"):
        mt.pvalues_from_t([1.0, float("nan")])


def test_harmonic_refuses_a_non_positive_count():
    with pytest.raises(ValueError, match="n must be at least 1"):
        mt.harmonic(0)


def test_the_panel_helper_refuses_series_that_do_not_span_the_same_periods():
    with pytest.raises(ValueError, match="different numbers of periods"):
        mt.panel([np.zeros(10), np.zeros(11)])
    with pytest.raises(ValueError, match="no candidate series"):
        mt.panel([])
    with pytest.raises(ValueError, match="series are empty"):
        mt.panel([np.zeros(0), np.zeros(0)])


@pytest.mark.parametrize("fn", [mt.reality_check, mt.spa])
def test_the_bootstrap_tests_refuse_a_ragged_or_misshapen_panel(fn):
    with pytest.raises(ValueError, match="ragged"):
        fn([[1.0, 2.0], [1.0, 2.0, 3.0]], block=2, reps=100)
    with pytest.raises(ValueError, match="single series"):
        fn(np.zeros(50), block=2, reps=100)
    with pytest.raises(ValueError, match="2-D"):
        fn(np.zeros((10, 3, 2)), block=2, reps=100)
    with pytest.raises(ValueError, match="at least 2 candidates"):
        fn(np.zeros((50, 1)), block=2, reps=100)
    with pytest.raises(ValueError, match="at least 2 periods"):
        fn(np.zeros((1, 3)), block=1, reps=100)
    with pytest.raises(ValueError, match="not finite"):
        fn(np.full((50, 3), np.nan), block=2, reps=100)


def test_the_bootstrap_tests_refuse_a_mismatched_benchmark():
    m = _panel(np.random.default_rng(0), t=100, k=4)
    with pytest.raises(ValueError, match="the benchmark covers 50 periods"):
        mt.reality_check(m, block=4, reps=100, benchmark=np.zeros(50))
    with pytest.raises(ValueError, match="benchmark series contains non-finite"):
        mt.reality_check(m, block=4, reps=100, benchmark=np.full(100, np.nan))


def test_the_block_length_is_required_and_range_checked():
    """It is the serial-dependence assumption, so it cannot be defaulted silently."""
    m = _panel(np.random.default_rng(0), t=100, k=4)
    assert "block" in inspect.signature(mt.reality_check).parameters
    assert inspect.signature(mt.reality_check).parameters["block"].default is inspect.Parameter.empty
    for bad in (0, -1, 101):
        with pytest.raises(ValueError, match="mean block length"):
            mt.reality_check(m, block=bad, reps=100)


def test_too_few_bootstrap_reps_to_resolve_a_p_value_is_refused():
    m = _panel(np.random.default_rng(0), t=100, k=4)
    with pytest.raises(ValueError, match="cannot resolve a p-value"):
        mt.reality_check(m, block=4, reps=50)


def test_a_candidate_that_never_traded_is_refused():
    m = _panel(np.random.default_rng(0), t=100, k=4)
    m[:, 2] = 0.0
    with pytest.raises(ValueError, match="zero variance"):
        mt.spa(m, block=4, reps=100)


def test_the_expected_maximum_refuses_one_trial_and_a_degenerate_variance():
    with pytest.raises(ValueError, match="not defined"):
        mt.expected_max_sharpe(1, 0.01)
    with pytest.raises(ValueError, match="finite and positive"):
        mt.expected_max_sharpe(10, 0.0)


def test_excess_kurtosis_passed_as_kurtosis_is_refused_with_the_fix_named():
    """The standard implementation error, and it inflates the DSR. Caught, not absorbed."""
    with pytest.raises(ValueError, match="NON-EXCESS kurtosis"):
        mt.deflated_sharpe(sharpe=0.1, n_obs=500, n_trials=50, var_trials=0.0025,
                           skew=0.0, kurtosis=0.0)


def test_an_annualised_sharpe_passed_with_a_daily_observation_count_is_refused():
    with pytest.raises(ValueError, match="almost certainly an annualised figure"):
        mt.deflated_sharpe(sharpe=1.8, n_obs=500, n_trials=50, var_trials=0.0025,
                           skew=0.0, kurtosis=3.0, max_plausible_sharpe=1.0)


@pytest.mark.parametrize("field", ["sharpe", "skew", "kurtosis", "var_trials"])
def test_non_finite_deflated_sharpe_inputs_are_refused(field):
    nan = float("nan")
    args = dict(sharpe=0.1, var_trials=0.0025, skew=0.0, kurtosis=3.0)
    args[field] = nan
    with pytest.raises(ValueError, match="must be finite"):
        mt.deflated_sharpe(n_obs=500, n_trials=50, sharpe=args["sharpe"],
                           var_trials=args["var_trials"], skew=args["skew"],
                           kurtosis=args["kurtosis"])


def test_a_min_obs_below_a_fourth_moment_is_refused():
    with pytest.raises(ValueError, match="below the 4 observations"):
        mt.deflated_sharpe(sharpe=0.1, n_obs=500, n_trials=50, var_trials=0.0025, skew=0.0,
                           kurtosis=3.0, min_obs=3)


def test_sharpe_moments_refuses_a_tiny_or_flat_series():
    """The flat case is not hypothetical: fifty copies of 0.1 have a standard deviation of
    2.8e-17 rather than zero, and an absolute `sd <= 0` test reported a Sharpe of 3.6e15.
    That is what this assertion found, and why the guard is scale-relative."""
    with pytest.raises(ValueError, match="fourth moment"):
        mt.sharpe_moments([0.1, 0.2, 0.3])
    with pytest.raises(ValueError, match="floating-point dust"):
        mt.sharpe_moments([0.1] * 50)
    with pytest.raises(ValueError, match="no variance"):
        mt.sharpe_moments([0.0] * 50)


def test_the_vector_form_refuses_an_empty_or_broken_trial_set():
    returns = np.random.default_rng(0).normal(0.02, 1.0, size=200)
    with pytest.raises(ValueError, match="empty search did not produce it"):
        mt.deflated_sharpe_from_returns(returns, trial_sharpes=[])
    with pytest.raises(ValueError, match="still happened and still counts"):
        mt.deflated_sharpe_from_returns(returns, trial_sharpes=[0.1, float("nan")])


def test_pbo_refuses_an_odd_or_tiny_number_of_splits():
    m = np.random.default_rng(0).normal(0.0, 0.01, size=(600, 10))
    with pytest.raises(ValueError, match="must be even"):
        mt.pbo(m, n_splits=7)
    with pytest.raises(ValueError, match="at most 2 splits"):
        mt.pbo(m, n_splits=2)


def test_pbo_refuses_blocks_too_short_to_score():
    m = np.random.default_rng(0).normal(0.0, 0.01, size=(12, 10))
    with pytest.raises(ValueError, match="periods per block"):
        mt.pbo(m, n_splits=8)
    with pytest.raises(ValueError, match="below the 2 rows"):
        mt.pbo(m, n_splits=4, min_block=1)


def test_pbo_refuses_a_split_count_that_would_enumerate_too_many_combinations():
    m = np.random.default_rng(0).normal(0.0, 0.01, size=(600, 10))
    with pytest.raises(ValueError, match="above max_combinations"):
        mt.pbo(m, n_splits=20)


def test_pbo_refuses_a_metric_that_does_not_score_every_configuration():
    m = np.random.default_rng(0).normal(0.0, 0.01, size=(600, 10))
    with pytest.raises(ValueError, match="one score per column"):
        mt.pbo(m, n_splits=4, metric=lambda block: block.sum(axis=0)[:3])
    with pytest.raises(ValueError, match="non-finite scores"):
        mt.pbo(m, n_splits=4, metric=lambda block: np.full(block.shape[1], np.nan))


def test_pbo_refuses_a_single_configuration():
    with pytest.raises(ValueError, match="at least 2 candidates"):
        mt.pbo(np.random.default_rng(0).normal(0, 0.01, size=(600, 1)), n_splits=4)


def test_every_guard_in_the_module_has_a_test():
    """A refusal nobody has fired is a refusal nobody knows works.

    This counts the `raise ValueError` sites in the source and fails when one is added
    without a test above. If you are here because you added a guard: add the test, then
    update the number. If you are here because you removed one: same.
    """
    src = Path(mt.__file__).read_text(encoding="utf-8")
    guards = len(re.findall(r"raise ValueError\(", src))
    assert guards == 39, (
        f"the module now has {guards} refusal sites, not 39. Every one needs a test in the "
        f"section above before this number is changed.")


def test_the_unavailable_paths_never_return_a_number():
    """Section 40: an unavailable result must carry a reason and no plausible decimal."""
    short = mt.reality_check(_panel(np.random.default_rng(0), t=20, k=4), block=3, reps=100)
    one_trial = _dsr(1)
    for r in (short, one_trial):
        assert r.reason and len(r.reason) > 40, "a refusal must say why"
    assert short.pvalue is None and short.statistic is None
    assert one_trial.value is None and one_trial.expected_max_sharpe is None
