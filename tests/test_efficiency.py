"""What the volatility x directional-efficiency study established, pinned.

The most valuable tests in this file are the two ARTEFACT tests. This study produced two
results that looked like the best findings in the whole research programme, replicated
out of sample on all four ETFs at |t| up to 20, and were both false:

    1. `open30_absret_pct` -> `eff_mfe`   an accounting identity. The predictor's window is
                                          INSIDE the target's window, so a large opening move
                                          is literally part of the maximum favourable
                                          excursion it is "predicting".

    2. `openW_vol_share` -> `restW_eff_*` a look-ahead. The share divides by the day's TOTAL
                                          volume, which is unknown at minute W, so the
                                          predictor encodes the rest of the session.

Both replicated perfectly out of sample, because a leak replicates - out-of-sample testing
protects against overfitting, not against a predictor that contains its own answer. Those two
tests exist so that if either construction is ever reintroduced, the suite says so before it
reaches a report.

The rest of the file pins the nulls and the one structural fact worth keeping (intraday
sessions displace LESS than a random walk).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

ETF = REPO / "research" / "efficiency_etf.parquet"
FUT = REPO / "research" / "efficiency_futures.parquet"

pytestmark = pytest.mark.skipif(
    not ETF.exists(), reason="run scripts/efficiency_panel.py to build the panels")


@pytest.fixture(scope="module")
def etf() -> pd.DataFrame:
    return pd.read_parquet(ETF)


def _spearman(a, b):
    from efficiency_volatility import spearman
    return spearman(np.asarray(a, dtype=float), np.asarray(b, dtype=float))


# =====================================================================================
# THE TWO ARTEFACTS
# =====================================================================================

@pytest.mark.parametrize("sym", ["SPY", "QQQ", "IWM", "DIA"])
def test_the_opening_move_predicts_whole_session_mfe_only_by_overlap(etf, sym):
    """Artefact 1, pinned from both sides.

    Against the WHOLE session the relationship is huge, because the opening move is part of
    the excursion being measured. Against the session AFTER the opening window it vanishes.
    Both halves are asserted, so the test fails if either the identity disappears (the panel
    changed) or the remainder version acquires signal (a real discovery, or a new leak).
    """
    g = etf[etf.symbol == sym]
    r_whole, t_whole, _ = _spearman(g["open30_absret_pct"], g["eff_mfe"])
    r_rest, t_rest, _ = _spearman(g["open30_absret_pct"], g["rest30_eff_mfe"])
    assert r_whole > 0.20, (
        f"{sym}: the whole-session overlap effect is gone (r={r_whole:.3f}); the panel's "
        f"window definitions may have changed")
    assert abs(t_rest) < 2.5, (
        f"{sym}: the opening move now predicts the REMAINDER's excursion efficiency at "
        f"t={t_rest:.2f}. Establish whether this is a discovery or a new leak.")


@pytest.mark.parametrize("sym", ["SPY", "QQQ", "IWM", "DIA"])
def test_opening_volume_share_is_a_leak_and_the_causal_version_is_null(etf, sym):
    """Artefact 2. `vol_share` divides by the day's total volume; `vol_rel` does not."""
    g = etf[etf.symbol == sym]
    _, t_leaky, _ = _spearman(g["open30_vol_share_LEAKY"], g["rest30_eff_vol"])
    _, t_causal, _ = _spearman(g["open30_vol_rel"], g["rest30_eff_vol"])
    assert abs(t_leaky) > 4.0, (
        f"{sym}: the leaky share no longer shows its artefact (t={t_leaky:.2f})")
    assert abs(t_causal) < 2.5, (
        f"{sym}: the CAUSAL opening-volume ratio now predicts remainder efficiency at "
        f"t={t_causal:.2f}. This would be a real finding - verify it before trading it.")


def test_the_leaky_share_encodes_the_rest_of_the_day(etf):
    """The mechanism of artefact 2, asserted directly rather than described."""
    g = etf[etf.symbol == "SPY"].dropna(
        subset=["open30_vol_share_LEAKY", "rth_volume", "open30_volume"])
    rest_vol = (g["rth_volume"] - g["open30_volume"]).to_numpy(dtype=float)
    _, t, _ = _spearman(g["open30_vol_share_LEAKY"], rest_vol)
    assert abs(t) > 8.0, (
        "the leaky share no longer correlates with rest-of-day volume; the leak it "
        "demonstrates may have been silently fixed in the panel")


def test_the_overlap_guard_rejects_a_mismatched_pair():
    """The guard that stops artefact 1 recurring, tested on its own terms."""
    from efficiency_search_clean import overlaps
    assert overlaps("open30_absret_pct", "eff_mfe")
    assert overlaps("open30_absret_pct", "rest15_eff_mfe")
    assert overlaps("fc_vol x open30_ret_pct", "eff_range")
    assert not overlaps("open30_absret_pct", "rest30_eff_mfe")
    assert not overlaps("prev_rv_pct", "eff_range")
    assert not overlaps("on_atr_pct", "eff_mfe")


# =====================================================================================
# PATH SHAPE, AND THE DEFECT THAT MADE IT DEGENERATE
# =====================================================================================

def test_the_turn_counter_actually_counts_turns():
    """It returned zero for every session in the store until the direction-tracking bug was
    fixed. Pinned on synthetic paths where the right answer is known by construction."""
    from efficiency_panel import _turns
    ramp = np.linspace(100, 110, 400)
    v = np.concatenate([np.linspace(100, 90, 200), np.linspace(90, 100, 200)])
    saw = np.concatenate([np.linspace(100, 105, 100), np.linspace(105, 100, 100),
                          np.linspace(100, 105, 100), np.linspace(105, 100, 100)])
    assert _turns(ramp, 10.0)["n_turns"] == 0
    assert _turns(ramp, 10.0)["max_run_pts"] == pytest.approx(10.0, abs=0.1)
    assert _turns(v, 10.0)["n_turns"] == 1
    assert _turns(saw, 5.0)["n_turns"] == 3


def test_path_shape_is_not_degenerate_on_real_data(etf):
    """The giveaway for the old bug was max_run collapsing to exactly |close - open|."""
    g = etf[etf.symbol == "SPY"].dropna(subset=["n_turns", "max_run_pts", "disp_pts"])
    assert g["n_turns"].median() > 2, "turn counts look degenerate again"
    assert (g["max_run_pts"] > g["disp_pts"] + 1e-9).mean() > 0.5, (
        "max_run equals net displacement on most sessions, which means no swings are "
        "being detected")


# =====================================================================================
# THE STRUCTURAL FACT WORTH KEEPING
# =====================================================================================

@pytest.mark.parametrize("sym", ["SPY", "QQQ", "IWM", "DIA"])
def test_sessions_displace_less_than_a_random_walk(etf, sym):
    """eff_vol is |net move| over the random-walk expectation. Median 0.64-0.74 across every
    instrument and both panels: intraday index futures and ETFs mean-revert. This is the
    structural reason a directional mechanism is hard here, and it is worth pinning."""
    med = float(etf[etf.symbol == sym]["eff_vol"].median())
    assert 0.5 < med < 0.9, f"{sym}: eff_vol median moved to {med:.3f}"


def test_the_efficiency_definitions_mostly_agree(etf):
    """eff_range, eff_path and eff_vol correlate above 0.94, so the choice among them is not
    a researcher degree of freedom. eff_mfe and cost_opp are genuinely different."""
    sub = etf[["eff_range", "eff_path", "eff_vol"]].dropna().rank()
    assert np.corrcoef(sub["eff_range"], sub["eff_path"])[0, 1] > 0.90
    assert np.corrcoef(sub["eff_path"], sub["eff_vol"])[0, 1] > 0.90


# =====================================================================================
# THE NULLS
# =====================================================================================

def test_no_second_variable_predicts_efficiency_out_of_sample():
    """The headline null: 0 of ~4,800 window-matched tests clear Bonferroni in the search
    window and replicate in the holdout."""
    f = REPO / "research" / "efficiency_search_clean.csv"
    if not f.exists():
        pytest.skip("run scripts/efficiency_search_clean.py")
    d = pd.read_csv(f)
    from efficiency_search import bonf
    bar = bonf(len(d))
    rep = ((np.sign(d.rho_hold) == np.sign(d.rho_search))
           & (d.t_hold.abs() > 1.96) & (d.t_search.abs() > bar))
    assert int(rep.sum()) <= 2, (
        f"{int(rep.sum())} predictors now replicate out of sample; it was 0. Check for an "
        f"overlap or look-ahead before believing it.")


def test_forecast_volatility_does_not_sort_efficiency():
    """Phase 2: the spread of efficiency is flat across forecast-volatility quintiles, so
    there is no mixture of trend days and chop days to separate."""
    f = REPO / "research" / "efficiency_spread.csv"
    if not f.exists():
        pytest.skip("run scripts/efficiency_volatility.py")
    d = pd.read_csv(f)
    for (_, _), g in d.groupby(["panel", "symbol"]):
        g = g.sort_values("quintile")
        if len(g) < 3:
            continue
        ratio = g.iloc[-1]["sd"] / g.iloc[0]["sd"]
        assert ratio < 1.25, (
            f"efficiency spread now widens by {ratio:.2f}x across forecast-volatility "
            f"quintiles; a mixture may have appeared")


def test_the_inverted_u_does_not_survive():
    """The non-monotone alternative: 0 of 24 cells kept a negative curvature that was
    significant in both halves with a stable peak and beat a line out of sample."""
    f = REPO / "research" / "efficiency_nonlinear.csv"
    if not f.exists():
        pytest.skip("run scripts/efficiency_nonlinear.py")
    d = pd.read_csv(f)
    both_neg_sig = ((d.b2_search < 0) & (d.b2_hold < 0)
                    & (d.t2_search.abs() > 1.96) & (d.t2_hold.abs() > 1.96))
    assert int(both_neg_sig.sum()) == 0, (
        f"{int(both_neg_sig.sum())} cells now show a stable inverted-U; it was 0")


def test_the_pipeline_can_detect_an_injected_signal(etf):
    """The positive control, as a test. A programme that only reports nulls must show it is
    capable of reporting something else."""
    g = etf[etf.symbol == "SPY"].dropna(subset=["eff_range"])
    y = g["eff_range"].to_numpy(dtype=float)
    yr = pd.Series(y).rank().to_numpy()
    rng = np.random.default_rng(5150)
    strong = yr + 3.0 * rng.normal(size=len(yr)) * yr.std()
    _, t, _ = _spearman(strong, y)
    assert abs(t) > 8.0, f"the pipeline failed to detect a strong injected signal (t={t:.2f})"
    weak = yr + 10.0 * rng.normal(size=len(yr)) * yr.std()
    _, tw, _ = _spearman(weak, y)
    assert abs(tw) > 2.5, f"the pipeline failed to detect a weak injected signal (t={tw:.2f})"
