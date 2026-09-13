"""The sweep archive's statistics, pinned as executable facts (research/sweep_audit.md).

WHY THIS EXISTS
---------------
`quant_brain/core/stats.py` was written to fix three things: overlapping labels (AUD-18),
multiplicity (AUD-19), and the habit of reading |t| > 1.96 off a search. It is correct, it is
tested by `tests/test_qb_stats.py`, and as of this audit **not one** of the 59 `sweep_*` /
`ml_*` scripts imports it. Every significance claim in the research archive is computed by a
hand-rolled copy of the iid t-statistic.

This file does not try to fix that - the sweeps belong to other tracks and are the executable
record of results already in the ledger. It pins the *audit* instead, so that
`research/sweep_audit.md` cannot quietly go stale:

  1. the shared t-statistics really are the naive iid form (byte-for-byte in behaviour with
     `stats.tstat_iid`), so the audit's "naive t" label is a measurement, not an adjective;
  2. the grid sizes the ranked table quotes really are the grid sizes in the code;
  3. the three dependence structures the audit prices - label overlap, same-day cross-sectional
     pooling, and episode clustering - inflate a naive t by the amounts the audit claims.

If a track retrofits `tstat_hac` into one of these modules, a test here fails. That failure
means **the audit entry is out of date**, not that the code is broken - fix the row in
`research/sweep_audit.md` and the expectation here together.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from quant_brain.core import stats

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"

#: A fixed, unremarkable sample. Nothing about the assertions depends on these values beyond
#: their being finite, non-constant and long enough for ddof=1 to mean something.
SAMPLE = np.array([0.4, -1.2, 0.9, 2.1, -0.3, 0.7, -1.8, 1.4, 0.2, -0.6,
                   1.1, 0.05, -0.9, 1.7, -0.4, 0.8, 0.3, -1.1, 0.6, 0.15])


# --------------------------------------------------------------------------------------------
# 1. the hand-rolled t-statistics ARE the naive iid form
# --------------------------------------------------------------------------------------------

#: (module, attribute, adapter) for every distinct copy of the t-statistic in the archive.
#: These are the functions that decide, across the whole repository, whether a result is a
#: result. Six independent copies, zero shared code, zero corrections.
TSTAT_SITES = [
    ("sweep_f1", "tstat", lambda f, x: f(x)),          # the hub: 7 ml_* modules call this one
    ("sweep_f3", "tstat", lambda f, x: f(x)),
    ("sweep_f2", "tstat", lambda f, x: f(x)),
    ("sweep_s19", "tstat", lambda f, x: f(x)),         # imported by s22/s25/s26/s27/s30/s31
    ("sweep_s2", "tstat", lambda f, x: f(x)),
    ("sweep_o1", "tstat", lambda f, x: f(x)[2]),       # returns (mean, se, t)
    ("sweep_a14", "tstat", lambda f, x: f(x)[2]),
    ("sweep_a15", "tstat", lambda f, x: f(x)[2]),
    ("sweep_x1", "_cluster_t", lambda f, x: f(x)[1]),  # (mean, t, n); reused by f4 and f6
]


@pytest.mark.parametrize(("module", "attr", "call"), TSTAT_SITES,
                         ids=[f"{m}.{a}" for m, a, _ in TSTAT_SITES])
def test_every_archive_tstat_is_the_naive_iid_form(module, attr, call):
    """Each copy reproduces `stats.tstat_iid` exactly - no HAC, no clustering, no correction.

    This is the audit's central claim stated as arithmetic. `tstat_iid` is
    `mean / (sd / sqrt(n))` with ddof=1; if any of these sites agrees with it to 12 decimal
    places on an arbitrary sample, it is that formula and nothing else.
    """
    import importlib

    fn = getattr(importlib.import_module(module), attr)
    # `_cluster_t` and s20's copy take a pandas Series; the rest take an array. Both accept
    # an ndarray, so one call shape covers all nine.
    got = float(call(fn, SAMPLE))
    assert got == pytest.approx(stats.tstat_iid(SAMPLE).t, abs=1e-12), (
        f"{module}.{attr} is no longer the naive iid t - update research/sweep_audit.md")


@pytest.mark.parametrize(("module", "attr", "call"), TSTAT_SITES,
                         ids=[f"{m}.{a}" for m, a, _ in TSTAT_SITES])
def test_no_archive_tstat_corrects_for_serial_dependence(module, attr, call):
    """On a strongly autocorrelated series every copy still returns the uncorrected number.

    The sample below is an AR(1)-ish ramp: consecutive values are nearly identical, so the
    honest standard error is far larger than the iid one. A function that corrected for that
    would disagree with `tstat_iid` here. None does.
    """
    import importlib

    rng = np.random.default_rng(11)
    innov = rng.normal(0.02, 1.0, 600)
    series = np.empty(600)
    acc = 0.0
    for i, e in enumerate(innov):          # phi = 0.9: heavy positive serial correlation
        acc = 0.9 * acc + e
        series[i] = acc
    fn = getattr(importlib.import_module(module), attr)
    naive = float(call(fn, series))
    hac = stats.tstat_hac(series, lag=stats.newey_west_lag(len(series)))

    assert naive == pytest.approx(stats.tstat_iid(series).t, abs=1e-10)
    # and the correction it declines to make is material, not cosmetic
    assert abs(naive) > 1.5 * abs(hac.t), (
        f"{module}.{attr}: HAC would change this t materially, so the omission is not benign")


def test_not_one_sweep_or_ml_script_imports_the_repos_stats_module():
    """The measurement that opened this audit, kept honest.

    `quant_brain.core.stats` carries HAC, horizon-derived lags and Bonferroni. If this test
    starts failing, a track has begun retrofitting it and the ranked table needs re-reading.
    """
    scripts = sorted(SCRIPTS.glob("sweep_*.py")) + sorted(SCRIPTS.glob("ml_*.py"))
    assert len(scripts) >= 59, "the archive shrank; re-run the audit"

    importers = [p.name for p in scripts
                 if "core.stats" in p.read_text(encoding="utf-8")
                 or "core import stats" in p.read_text(encoding="utf-8")]
    assert importers == [], (
        f"{importers} now import the corrections - research/sweep_audit.md is stale")


# --------------------------------------------------------------------------------------------
# 2. the grid sizes the ranked table quotes
# --------------------------------------------------------------------------------------------

def test_f3_selection_searches_ten_cells_and_publishes_a_two_point_one_seven():
    """F-3 argmaxes over (model x horizon) and reports the winner at the 1.96 threshold.

    Ten cells is small as grids go - which is the point of ranking by grid x severity rather
    than by grid alone. F-3 ranks first because its *label* is wrong, not because its grid is
    big: the Bonferroni threshold for ten trials already exceeds the t it published.
    """
    import sweep_f3

    assert len(sweep_f3.GRID) == 5
    assert sweep_f3.HORIZONS == (5, 21)
    cells = len(sweep_f3.GRID) * len(sweep_f3.HORIZONS)
    assert cells == 10

    published = 2.17                      # ledger: pooled out-of-sample IC t, h = 5
    assert stats.bonferroni_threshold(cells) == pytest.approx(2.807, abs=0.005)
    assert published < stats.bonferroni_threshold(cells), (
        "F-3's headline t does not clear the threshold for its own selection, before any "
        "overlap correction is applied at all")


def test_f8_applies_a_pre_registered_pass_rule_to_the_argmax_of_twenty_cells():
    """ml_f8:520 chooses the best of BOOKS x labels on the test window, then gates it at t > 2.

    Clause 7's `t > 2` is the threshold for one pre-registered test. It is applied to the
    maximum of a twenty-cell search over the same window the cells were scored on.
    """
    import ml_f8

    labels = [ml_f8.BENCH] + ml_f8.LABELS       # h1 benchmark + h4/h7/h10/close
    cells = len(ml_f8.BOOKS) * len(labels)
    assert len(ml_f8.BOOKS) == 4
    assert cells == 20
    assert stats.bonferroni_threshold(cells) == pytest.approx(3.023, abs=0.005)
    assert stats.bonferroni_threshold(cells) > 2.0


@pytest.mark.parametrize(("module", "expected", "note"), [
    ("sweep_f6", 168, "ENTRIES 7 x EXITS 2 x BOOKS 2 x SELECTIONS 2 x LOOKBACKS 3"),
    ("sweep_x1", 16, "LOOKBACKS 4 x HORIZONS 2 x DECILES 2"),
    ("sweep_l1", 16, "ZS 4 x HORIZONS 4"),
    ("sweep_o4", 60, "TARGETS 5 x WIDTHS 3 x ENTRIES 2 x STRUCTURES 2"),
])
def test_the_ranked_tables_grid_sizes_are_the_codes_grid_sizes(module, expected, note):
    """The denominators in research/sweep_audit.md come from the modules, not from prose."""
    import importlib

    m = importlib.import_module(module)
    sizes = {
        "sweep_f6": lambda: (len(m.ENTRIES) * len(m.EXITS) * len(m.BOOKS)
                             * len(m.SELECTIONS) * len(m.LOOKBACKS)),
        "sweep_x1": lambda: len(m.LOOKBACKS) * len(m.HORIZONS) * len(m.DECILES),
        "sweep_l1": lambda: len(m.ZS) * len(m.HORIZONS),
        "sweep_o4": lambda: len(m.TARGETS) * len(m.WIDTHS) * len(m.ENTRIES) * len(m.STRUCTURES),
    }
    assert sizes[module]() == expected, note


@pytest.mark.parametrize(("trials", "threshold"), [
    (1, 1.960), (6, 2.638), (10, 2.807), (20, 3.023),
    (24, 3.078), (55, 3.317), (168, 3.617), (336, 3.793),
])
def test_the_bonferroni_thresholds_quoted_in_the_audit(trials, threshold):
    """Every |t| bar the ranked table cites, pinned.

    A reader checking the table should not have to trust arithmetic done in prose. Note how
    flat this is: going from 20 trials to 336 moves the bar only from 3.02 to 3.84, which is
    why "the grid is enormous" is a weaker objection than "the label is overlapping".
    """
    assert stats.bonferroni_threshold(trials) == pytest.approx(threshold, abs=0.005)


# --------------------------------------------------------------------------------------------
# 3. the three dependence structures the audit prices
# --------------------------------------------------------------------------------------------

def _overlapping_label(rng, n, horizon):
    """`sum of the next h iid daily returns`, formed every day - F-3's label shape exactly."""
    daily = rng.normal(0.0004, 0.01, n + horizon)
    return np.array([daily[i:i + horizon].sum() for i in range(n)])


@pytest.mark.parametrize("horizon", [5, 21])
def test_an_h_day_label_formed_daily_inflates_the_naive_t_toward_sqrt_h(horizon):
    """The AUD-18 mechanism, on a series whose dependence is known by construction.

    A label spanning h days and sampled every day is exactly MA(h-1). The naive t divides by
    a standard error that ignores h-1 lags of positive autocovariance, so it is too large.
    sqrt(h) is the asymptotic ceiling; the realised factor is below it on a finite sample,
    which is why the audit reports *measured* factors (F-3: 1.66x at h=5, 3.05x at h=21) and
    not sqrt(h) itself.
    """
    rng = np.random.default_rng(7)
    x = _overlapping_label(rng, 3000, horizon)

    naive = stats.tstat_iid(x)
    hac = stats.tstat_hac(x, horizon=horizon)
    factor = abs(naive.t) / abs(hac.t)

    assert hac.lag == horizon - 1, "the lag must cover the whole overlap"
    assert factor > 1.3, "an overlapping label must inflate the naive t"
    assert factor < math.sqrt(horizon) * 1.35, "and sqrt(h) is the scale of the effect"


def test_the_overlap_is_confined_to_the_labels_own_horizon():
    """Autocorrelation dies at lag h - the signature that identifies the defect in real data.

    This is the fingerprint the audit used to confirm F-3's panel: y_5's autocorrelation is
    +0.755 at lag 1 and ~0 by lag 5; y_21's is +0.934 at lag 1 and ~0 by lag 21. Anything
    else would mean the dependence is not overlap and a horizon-derived lag is the wrong fix.
    """
    rng = np.random.default_rng(3)
    x = _overlapping_label(rng, 20_000, 5)
    ac = [float(np.corrcoef(x[:-k], x[k:])[0, 1]) for k in (1, 2, 4, 5, 6)]

    assert ac[0] > 0.7 and ac[1] > 0.5           # inside the window: strongly dependent
    assert abs(ac[3]) < 0.05 and abs(ac[4]) < 0.05  # at and beyond h: gone


def test_pooling_same_day_names_as_independent_inflates_t_by_the_design_effect():
    """The a8/a9/a12 defect: thousands of (symbol, session) trips, ~3.8 independent units/day.

    `sweep_a9.py:170`, `sweep_a12.py:197` and `sweep_a8.py:198` compute a t over per-trip P&L
    pooled across names. Same-day names share a market factor, so the effective sample is
    smaller than the row count by Kish's design effect 1 + (m-1)*rho. Measured on the real
    F-1 store: m = 56 names, rho = 0.250, deff = 14.8, i.e. a 3.84x inflation - the largest
    single distortion found anywhere in the archive, and larger than any overlap effect.
    """
    rng = np.random.default_rng(5)
    days, m, rho = 400, 56, 0.25
    common = rng.normal(0.0, math.sqrt(rho), days)[:, None]
    idio = rng.normal(0.0, math.sqrt(1.0 - rho), (days, m))
    panel = common + idio                         # corr between two names on a day == rho

    pooled = stats.tstat_iid(panel.ravel())       # what the per-trip tables do
    clustered = stats.tstat_iid(panel.mean(axis=1))  # one number per session

    deff = 1.0 + (m - 1) * rho
    assert abs(pooled.t) / abs(clustered.t) == pytest.approx(math.sqrt(deff), rel=0.15)
    assert math.sqrt(deff) > 3.5, "the design effect this audit measured on the real store"


def test_clustering_a_contiguous_episode_subset_shrinks_the_effective_sample():
    """The s20/s29 defect: a risk-off subset is 590 sessions but only 29 crisis episodes.

    Selecting a subset by a persistent regime flag does not give independent draws; it gives
    a handful of long runs. The nominal n overstates the information by roughly the mean
    episode length.
    """
    rng = np.random.default_rng(9)
    n_episodes, episode_len = 29, 20
    # each episode has its own level: within-episode returns are far from independent
    levels = rng.normal(0.0008, 0.004, n_episodes)
    x = np.concatenate([lv + rng.normal(0.0, 0.002, episode_len) for lv in levels])

    pooled = stats.tstat_iid(x)
    by_episode = stats.tstat_iid(x.reshape(n_episodes, episode_len).mean(axis=1))

    assert pooled.n == n_episodes * episode_len == 580
    assert by_episode.n == n_episodes
    assert abs(pooled.t) > 1.8 * abs(by_episode.t), (
        "counting sessions instead of episodes materially overstates the evidence")


# --------------------------------------------------------------------------------------------
# 4. the corrections compound - the number the ranked table is ordered by
# --------------------------------------------------------------------------------------------

def test_f3s_published_ic_survives_neither_correction_alone_nor_the_pair():
    """The audit's rank-1 finding, as arithmetic on the numbers the ledger carries.

    F-3 published IC +0.01133 at t +2.17 (h=5) and +0.01264 at t +2.41 (h=21), read against
    1.96. Measured on `data/f3/panel.parquet`, the overlap correction alone takes those to
    +1.31 and +0.79; the ten-cell selection alone raises the bar to 2.81. Either kills it.
    """
    for naive, corrected, inflation in ((2.17, 1.31, 1.66), (2.41, 0.79, 3.05)):
        assert naive / inflation == pytest.approx(corrected, abs=0.02), "measured inflation"
        assert corrected < 1.96, "overlap alone refutes it at the conventional threshold"
        assert naive < stats.bonferroni_threshold(10), "selection alone refutes it too"
        assert corrected < stats.bonferroni_threshold(10) / 2, "the pair is not close"
