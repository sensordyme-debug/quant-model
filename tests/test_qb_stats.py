"""Significance testing under overlapping observations (AUD-18).

The defect: `sweep_f1.tstat` and its duplicate in `sweep_f3.py` are the iid t-statistic, used
at 60 call sites. F-3's labels are `log(open[t+1+h]/open[t+1])` with h = 5 or 21 sessions,
formed every trading day, so consecutive observations share h-1 days of the same returns.

Measured on F-3's own exported scores against its own panel, reproducing the ledger's
IC 0.01133 exactly:

    h=5    naive t +2.17  ->  HAC t +1.31  (1.66x), block bootstrap p = 0.196
    h=21   naive t +2.41  ->  HAC t +0.79  (3.05x), block bootstrap p = 0.436

Both "significant" results become insignificant. These tests pin the estimator that produced
those numbers, including the synthetic cases where the true answer is known.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from quant_brain.core.stats import (
    TStat,
    block_bootstrap_t,
    inflation,
    lag_for_overlap,
    newey_west_lag,
    summarize,
    tstat_hac,
    tstat_iid,
)


def overlapping(n, h, seed=0, mu=0.0):
    """A series of h-period overlapping sums of iid noise: an MA(h-1) by construction.

    This is exactly F-3's label structure, so the true variance inflation is known and the
    estimator can be checked against it rather than against itself.
    """
    rng = np.random.default_rng(seed)
    e = rng.standard_normal(n + h)
    return np.array([e[i:i + h].sum() for i in range(n)]) + mu


# ------------------------------------------------------- the naive statistic, as a baseline

def test_iid_tstat_matches_the_textbook_formula():
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    got = tstat_iid(x)
    assert got.t == pytest.approx(x.mean() / (x.std(ddof=1) / np.sqrt(len(x))))
    assert got.method == "iid" and got.n == 5


def test_iid_on_independent_noise_is_correctly_sized():
    """On genuinely iid data the naive t is right, and HAC must not disagree much."""
    rng = np.random.default_rng(3)
    x = rng.standard_normal(4000)
    assert abs(tstat_iid(x).t) < 3
    assert inflation(x, horizon=1) == pytest.approx(1.0, abs=0.05)


def test_degenerate_inputs_return_nan_rather_than_a_number():
    for bad in ([], [1.0], [np.nan, np.nan]):
        assert not np.isfinite(tstat_iid(bad).t)
        assert not np.isfinite(tstat_hac(bad).t)


def test_zero_variance_does_not_divide_by_zero():
    assert not np.isfinite(tstat_iid([2.0] * 50).t)
    assert not np.isfinite(tstat_hac([2.0] * 50, horizon=5).t)


# ------------------------------------------------------- the correction does what it claims

def test_hac_deflates_the_t_on_overlapping_data():
    x = overlapping(3000, h=5, seed=1, mu=0.06)
    iid, hac = tstat_iid(x), tstat_hac(x, horizon=5)
    assert abs(hac.t) < abs(iid.t)
    assert hac.lag == 4


def test_the_inflation_approaches_root_h_on_a_pure_overlap():
    """Theory: a perfect h-period overlap inflates the naive t by about sqrt(h)."""
    for h in (5, 10, 21):
        x = overlapping(6000, h=h, seed=h, mu=0.03)
        got = inflation(x, horizon=h)
        assert got == pytest.approx(math.sqrt(h), rel=0.30), (h, got)


def test_hac_and_iid_agree_when_there_is_no_overlap():
    rng = np.random.default_rng(11)
    x = rng.standard_normal(3000) + 0.05
    assert inflation(x, horizon=1) == pytest.approx(1.0, abs=0.1)


def test_a_longer_horizon_needs_a_bigger_correction():
    a = inflation(overlapping(6000, h=5, seed=5, mu=0.03), horizon=5)
    b = inflation(overlapping(6000, h=21, seed=5, mu=0.03), horizon=21)
    assert b > a


# ------------------------------------------------------- the lag is not negotiable

def test_the_lag_is_derived_from_the_horizon():
    assert lag_for_overlap(5) == 4
    assert lag_for_overlap(21) == 20
    assert lag_for_overlap(1) == 0


def test_a_short_sample_caps_the_lag_rather_than_estimating_noise():
    assert lag_for_overlap(21, n=40) == 10


def test_a_lag_below_the_horizon_is_refused_not_silently_accepted():
    """A truncated lag leaves the overlap partly uncorrected and still reports an inflated t,
    which is worse than no correction because it looks like one."""
    x = overlapping(500, h=21, seed=2)
    with pytest.raises(ValueError, match="below the"):
        tstat_hac(x, lag=3, horizon=21)


def test_the_automatic_bandwidth_is_the_newey_west_rule():
    for n in (100, 1000, 5000):
        assert newey_west_lag(n) == int(math.floor(4.0 * (n / 100.0) ** (2.0 / 9.0)))


def test_hac_variance_is_never_negative():
    """Bartlett weights guarantee this in theory; the clamp guards floating-point drift."""
    rng = np.random.default_rng(4)
    for _ in range(20):
        x = rng.standard_normal(200)
        got = tstat_hac(x, lag=30)
        assert got.se >= 0


# ------------------------------------------------------- the independent check

def test_the_block_bootstrap_agrees_with_hac_on_a_null_series():
    x = overlapping(2000, h=21, seed=8, mu=0.0)      # true mean is zero
    p, _se = block_bootstrap_t(x, block=21, reps=400, seed=1)
    assert p > 0.05
    assert not tstat_hac(x, horizon=21).significant


def test_the_block_bootstrap_finds_a_genuine_effect():
    x = overlapping(2000, h=5, seed=9, mu=1.5)       # a large true mean
    p, _se = block_bootstrap_t(x, block=5, reps=400, seed=1)
    assert p < 0.05
    assert tstat_hac(x, horizon=5).significant


def test_the_bootstrap_is_deterministic_under_a_seed():
    x = overlapping(500, h=5, seed=3, mu=0.2)
    assert block_bootstrap_t(x, block=5, reps=200, seed=42) == \
           block_bootstrap_t(x, block=5, reps=200, seed=42)


# ------------------------------------------------------- reporting

def test_significant_uses_the_conventional_threshold():
    assert TStat(0.0, 2.10, 1.0, 100, 0, "iid").significant
    assert not TStat(0.0, 1.90, 1.0, 100, 0, "iid").significant
    assert not TStat(0.0, float("nan"), 1.0, 100, 0, "iid").significant


def test_summarize_reports_both_statistics_and_the_inflation():
    text = summarize(overlapping(1000, h=5, seed=1, mu=0.05), horizon=5, label="F-3 IC")
    for token in ("F-3 IC", "naive t", "HAC t", "inflation", "h=5", "L=4"):
        assert token in text, text


def test_summarize_without_a_horizon_reports_only_the_naive_statistic():
    assert "HAC" not in summarize([1.0, 2.0, 3.0, 4.0])


# ------------------------------------------------------- the F-3 result, as a regression

def test_the_f3_correction_is_reproducible_from_the_saved_artifacts():
    """Guards the headline finding: F-3's IC t of 2.17 does not survive its own overlap.

    Skips rather than fails if the artifacts are absent - they are gitignored research
    output, and a fresh clone should not report a false failure.
    """
    from pathlib import Path

    import pandas as pd

    repo = Path(__file__).resolve().parents[1]
    scores_p, panel_p = repo / "data/f3/ml_scores.csv", repo / "data/f3/panel.parquet"
    if not (scores_p.exists() and panel_p.exists()):
        pytest.skip("F-3 artifacts not on disk (gitignored research output)")

    scores = pd.read_csv(scores_p, parse_dates=["date"])
    panel = pd.read_parquet(panel_p)
    panel["date"] = pd.to_datetime(panel["date"])
    long = scores.melt(id_vars="date", var_name="sym", value_name="score").dropna()
    # `.loc` with an explicit DataFrame annotation: chained boolean-then-column indexing
    # is typed as Series | DataFrame, which merge() will not accept as `right`.
    test: pd.DataFrame = panel.loc[panel["date"] >= "2012-01-01",
                                   ["date", "sym", "y_5"]]
    m = long.merge(test, on=["date", "sym"], how="inner").dropna(subset=["y_5"])
    # np.asarray + astype rather than the chained .to_numpy(): groupby.apply is typed as
    # Series | DataFrame | Any, so the array's dtype is unknown to the checker downstream.
    ic_series = (m.groupby("date")
                   .apply(lambda g: g["score"].corr(g["y_5"], method="spearman")
                          if len(g) > 5 else np.nan, include_groups=False)
                   .dropna())
    ic = np.asarray(ic_series, dtype=float)

    assert float(np.mean(ic)) == pytest.approx(0.01133, abs=5e-5), "not F-3's own IC series"
    assert tstat_iid(ic).t == pytest.approx(2.17, abs=0.05)      # what the ledger reports
    hac = tstat_hac(ic, horizon=5)
    assert hac.t == pytest.approx(1.31, abs=0.10)                # what it is worth
    assert not hac.significant, "the whole point of AUD-18"


# ------------------------------------------------------- multiplicity (AUD-19)

def test_the_threshold_rises_with_the_number_of_trials():
    from quant_brain.core.stats import bonferroni_threshold
    assert bonferroni_threshold(1) == pytest.approx(1.96, abs=0.01)
    assert bonferroni_threshold(24) == pytest.approx(3.08, abs=0.02)
    assert bonferroni_threshold(55) == pytest.approx(3.32, abs=0.02)
    # monotone: more trials can only make the bar higher
    ts = [bonferroni_threshold(n) for n in (1, 5, 20, 55, 200)]
    assert ts == sorted(ts)


def test_f3_survives_neither_correction():
    """The worked example. ml_f7 alone runs 24 constructions; the ledger holds 55 distinct
    F-track specifications; nothing in the ML track corrects for any of it."""
    from quant_brain.core.stats import deflated
    for t in (2.17, 1.31):                      # naive, then HAC
        survives, thr = deflated(t, 55)
        assert not survives and thr > 3.0


def test_a_genuinely_strong_result_still_survives_55_trials():
    """The correction must not be so blunt that nothing can ever pass it."""
    from quant_brain.core.stats import deflated
    survives, _ = deflated(4.74, 55)            # F-1's reported t
    assert survives


def test_verdict_reports_both_corrections_together():
    from quant_brain.core.stats import verdict
    x = overlapping(2000, h=5, seed=4, mu=0.03)
    text = verdict(x, horizon=5, n_trials=55, label="F-3 IC")
    for token in ("F-3 IC", "threshold", "55 trial", "naive t was"):
        assert token in text, text


def test_deflated_handles_a_nan_t():
    from quant_brain.core.stats import deflated
    survives, _ = deflated(float("nan"), 10)
    assert not survives
