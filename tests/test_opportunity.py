"""What the conditional-opportunity study established, pinned so it cannot rot quietly.

Three kinds of test live here, and the middle kind is the one that matters most.

CAUSALITY. The opportunity forecast is the only result in this research programme that
anybody would act on, so the claim that it uses no future information is load-bearing. It is
tested by PERTURBATION rather than by reading the code: change the future and assert the
forecast does not move. A causality argument that depends on a human noticing a `shift(1)` is
not an argument.

THE POSITIVE. The forecast predicts realised volatility out of sample. Pinned with a floor,
because a regression in the feature pipeline would show up here as a collapse rather than as
a subtly worse number nobody checks.

THE NULLS, which is the middle kind and the important one. This study produced far more
negative results than positive ones, and a negative result is exactly what gets quietly
overturned later by a bug that reintroduces a leak - because nobody re-examines a null. So
the direction nulls are pinned as hard as the volatility positive. If a future change makes
overnight information appear to predict direction, or makes the opportunity model appear to
predict displacement, this suite fails and somebody has to decide whether it is a discovery
or a defect.
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

from quant_brain.research import opportunity as opp  # noqa: E402

PANEL = REPO / "research" / "opportunity_panel.parquet"
ETF = REPO / "research" / "etf_overnight_panel.parquet"

pytestmark = pytest.mark.skipif(
    not PANEL.exists(), reason="run scripts/opportunity_panel.py to build the panel")


@pytest.fixture(scope="module")
def panel() -> pd.DataFrame:
    return pd.read_parquet(PANEL)


@pytest.fixture(scope="module")
def forecasts(panel) -> dict[str, pd.DataFrame]:
    out = {}
    for sym, g in panel.groupby("symbol"):
        g = g.sort_values("tdate").reset_index(drop=True).copy()
        g["fc"] = opp.forecast_frame(g, "rth_rv_pct")
        g["bench"] = opp.forecast_frame(g, "rth_rv_pct",
                                        features=opp.BENCHMARK_FEATURES)
        g["mean"] = opp.expanding_mean(g["rth_rv_pct"].to_numpy(dtype=float))
        out[sym] = g
    return out


# =====================================================================================
# CAUSALITY, TESTED BY PERTURBATION
# =====================================================================================

def test_the_forecast_cannot_see_the_day_it_is_forecasting(panel):
    """Change every future target value and assert no earlier forecast moves.

    This is the test the whole study rests on. `walk_forward` fits day k on days 0..k-1, so
    rewriting day k onward must leave forecasts 0..k untouched. If it does not, the window is
    off by one somewhere and every out-of-sample number in the report is wrong.
    """
    g = panel[panel.symbol == "ES"].sort_values("tdate").reset_index(drop=True)
    x = g[list(opp.FEATURES)].to_numpy(dtype=float)
    y = g["rth_rv_pct"].to_numpy(dtype=float)
    base = opp.walk_forward(x, y)

    cut = 150
    y2 = y.copy()
    y2[cut:] = y2[cut:] * 7.5 + 1000.0          # obliterate the future
    poisoned = opp.walk_forward(x, y2)

    a, b = base[:cut + 1], poisoned[:cut + 1]
    m = np.isfinite(a) & np.isfinite(b)
    assert m.sum() > 50, "not enough forecasts before the cut to make the test meaningful"
    assert np.allclose(a[m], b[m]), (
        "forecasts before the cut moved when the future was rewritten; the walk-forward "
        "window is leaking")


def test_perturbing_a_future_FEATURE_also_cannot_move_an_earlier_forecast(panel):
    """The same argument for the regressor side, which is the easier one to get wrong."""
    g = panel[panel.symbol == "NQ"].sort_values("tdate").reset_index(drop=True)
    x = g[list(opp.FEATURES)].to_numpy(dtype=float)
    y = g["rth_rv_pct"].to_numpy(dtype=float)
    base = opp.walk_forward(x, y)
    cut = 150
    x2 = x.copy()
    x2[cut:] = x2[cut:] * -3.0
    poisoned = opp.walk_forward(x2, y)
    a, b = base[:cut], poisoned[:cut]
    m = np.isfinite(a) & np.isfinite(b)
    assert np.allclose(a[m], b[m])


def test_every_predictor_in_the_panel_is_knowable_before_the_open(panel):
    """The prior-day columns must genuinely lag: today's RTH range must never equal today's
    `prev_rth_range_pct`, and must equal YESTERDAY's."""
    for _, g in panel.groupby("symbol"):
        g = g.sort_values("tdate").reset_index(drop=True)
        shifted = g["rth_range_pct"].shift(1)
        m = shifted.notna() & g["prev_rth_range_pct"].notna()
        assert np.allclose(g.loc[m, "prev_rth_range_pct"], shifted[m]), (
            "prev_rth_range_pct is not yesterday's value")


def test_the_expanding_mean_benchmark_is_also_causal(panel):
    y = (panel[panel.symbol == "ES"].sort_values("tdate")["rth_rv_pct"]
         .to_numpy(dtype=float))
    base = opp.expanding_mean(y)
    y2 = y.copy()
    y2[200:] = 999.0
    assert np.allclose(base[:200][np.isfinite(base[:200])],
                       opp.expanding_mean(y2)[:200][np.isfinite(base[:200])])


# =====================================================================================
# THE FINDING THAT SURVIVED
# =====================================================================================

@pytest.mark.parametrize("sym", ["ES", "NQ", "MES", "MNQ"])
def test_the_opportunity_forecast_beats_the_historical_mean(forecasts, sym):
    """Out-of-sample R-squared near 0.45-0.51 on every instrument. Floored well below the
    measured value so that noise does not fail the suite but a collapse does."""
    g = forecasts[sym]
    r2, n = opp.oos_r2(g["rth_rv_pct"].to_numpy(dtype=float),
                       g["fc"].to_numpy(dtype=float), g["mean"].to_numpy(dtype=float))
    assert n > 100
    assert r2 > 0.30, f"{sym}: forecast skill collapsed to R2={r2:.3f}"


@pytest.mark.parametrize("sym", ["ES", "NQ", "MES", "MNQ"])
def test_the_overnight_session_adds_to_yesterday(forecasts, sym):
    """The incremental claim. Measured at +0.077 to +0.192; a positive floor is the claim."""
    g = forecasts[sym]
    r2, _ = opp.oos_r2(g["rth_rv_pct"].to_numpy(dtype=float),
                       g["fc"].to_numpy(dtype=float), g["bench"].to_numpy(dtype=float))
    assert r2 > 0.0, (
        f"{sym}: the overnight session no longer improves on a yesterday-only model "
        f"(incremental R2={r2:.3f})")


def test_three_predictors_beat_fifteen(panel):
    """Pinned because it is counter-intuitive and because a future contributor adding
    'just one more feature' should see this fail rather than silently degrade the forecast."""
    from opportunity_panel import PREDICTORS
    g = panel[panel.symbol == "ES"].sort_values("tdate").reset_index(drop=True)
    y = g["rth_rv_pct"].to_numpy(dtype=float)
    mean = opp.expanding_mean(y)
    small, _ = opp.oos_r2(y, opp.forecast_frame(g, "rth_rv_pct"), mean)
    big, _ = opp.oos_r2(y, opp.forecast_frame(g, "rth_rv_pct", features=PREDICTORS), mean)
    assert small > big, f"three predictors {small:.3f} no longer beat fifteen {big:.3f}"


# =====================================================================================
# THE NULLS, PINNED AS HARD AS THE POSITIVE
# =====================================================================================

@pytest.mark.parametrize("sym", ["ES", "NQ", "MES", "MNQ"])
def test_the_opportunity_model_predicts_PATH_and_not_DISPLACEMENT(panel, sym):
    """The central mechanistic fact, and the reason no gate in this study made money.

    Realised volatility is forecast at R2 near 0.5. The absolute net move - which is what a
    directional trade is actually paid for - is forecast at under 0.15 everywhere and under
    0.10 almost everywhere. If displacement ever becomes as predictable as path, that is a
    genuine discovery and this test should fail loudly so somebody looks at it.
    """
    g = panel[panel.symbol == sym].sort_values("tdate").reset_index(drop=True)
    y = g["rth_absret_pts"].to_numpy(dtype=float)
    r2, _ = opp.oos_r2(y, opp.forecast_frame(g, "rth_absret_pts"), opp.expanding_mean(y))
    assert r2 < 0.20, (
        f"{sym}: displacement is now forecast at R2={r2:.3f}. Establish whether this is a "
        f"leak before treating it as an edge.")


@pytest.mark.parametrize("sym", ["ES", "NQ", "MES", "MNQ"])
def test_the_opportunity_model_cannot_predict_signed_direction(panel, sym):
    """The control that must keep failing. A model built entirely from magnitude variables
    should have no signed skill; if it acquires some, something is leaking."""
    g = panel[panel.symbol == sym].sort_values("tdate").reset_index(drop=True)
    y = g["rth_ret_pct"].to_numpy(dtype=float)
    r2, _ = opp.oos_r2(y, opp.forecast_frame(g, "rth_ret_pct"), opp.expanding_mean(y))
    assert r2 < 0.05, f"{sym}: signed return is now forecast at R2={r2:.3f}"


def test_no_conditional_direction_cell_was_significant():
    """Phase 2's null: 110 conditional cells, not one clearing a nominal 1.96."""
    f = REPO / "research" / "conditional_direction.csv"
    if not f.exists():
        pytest.skip("run scripts/conditional_direction.py")
    d = pd.read_csv(f)
    worst = float(d["t"].abs().max())
    assert worst < 1.96, (
        f"a conditional-direction cell now reaches |t|={worst:.2f}; it was {len(d)} cells "
        f"with a maximum of 1.9 when the study ran")


def test_the_75_90_bucket_did_not_replicate():
    """The one pattern Phase 2 threw up, falsified on 2,600 independent ETF sessions.

    Pinned because a 20-of-20 sign agreement is exactly the kind of thing that gets
    rediscovered and believed by somebody who does not know it was already tested.
    """
    f = REPO / "research" / "etf_overnight_panel.parquet"
    if not f.exists():
        pytest.skip("run scripts/overnight_replicate.py")
    from conditional_direction import bucketise, cell_stats, trailing_pctile
    etf = pd.read_parquet(f).sort_values(["symbol", "tdate"])
    for sym, g in etf.groupby("symbol"):
        g = g.reset_index(drop=True)
        b = bucketise(trailing_pctile(g["on_ret_pct"].abs()))
        y = (np.sign(g["on_ret_pct"]) * g["rth_ret_pct"]).to_numpy(dtype=float)
        st = cell_stats(y[b == "75-90"])
        assert st["t"] < 1.96, (
            f"{sym}: the 75-90 continuation bucket now reaches t={st['t']:.2f}. It was "
            f"{st['t']:.2f} and negative when the confirmation test ran.")


def test_the_opening_transition_adds_nothing():
    """Phase 6's null: 23 of 24 cells had negative out-of-sample R-squared, and the
    interaction model was worse than the best single model nearly everywhere."""
    f = REPO / "research" / "opening_transition.csv"
    if not f.exists():
        pytest.skip("run scripts/opening_transition.py")
    d = pd.read_csv(f)
    assert (d["r2_both"] > 0).sum() <= 3, (
        f"{int((d['r2_both'] > 0).sum())} opening-transition cells now beat the mean out of "
        f"sample; it was 1 of 24")


def test_the_cross_market_directional_survivor_was_first_half_only():
    """Phase 5: one directional cell of 36 cleared Bonferroni, and it lived entirely in
    2016-2021. Pinned as a negative so it is not rediscovered as a positive."""
    f = REPO / "research" / "cross_market.csv"
    if not f.exists():
        pytest.skip("run scripts/cross_market.py")
    d = pd.read_csv(f)
    dirn = d[d.outcome.str.startswith("rth_ret_")]
    n_sig = int((dirn["t"].abs() > 3.54).sum())
    assert n_sig <= 2, (
        f"{n_sig} cross-market directional cells now clear the Bonferroni bar; it was 1, "
        f"and that one did not survive a split-half test")
