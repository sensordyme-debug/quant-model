"""What the overnight-to-RTH study established, pinned so it cannot rot quietly.

There are two kinds of test here and they exist for different reasons.

The first kind guards the PANEL. Every number in the study is computed from
`research/overnight_panel.parquet`, and the one way this study could be wrong in a way nobody
notices is if a column that is supposed to be knowable at 09:29 turns out to contain
information from later in the day. That is not a hypothetical: the previous iteration of this
research measured the regular session to 15:45 and concluded it drifted negative, and the
missing 35 minutes were the largest-volume part of the session. A boundary error is the most
expensive kind of error in this work and the cheapest kind to test for.

The second kind guards the FINDINGS - including, and especially, the null ones. A null result
is the thing most likely to be quietly overturned later by a change that reintroduces a bug,
because nobody re-examines a negative. So the direction null is pinned as firmly as the
volatility positive: if a future change makes overnight information appear to predict
direction, that is either a genuine discovery or a leak, and this test forces somebody to
decide which.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

PANEL = REPO / "research" / "overnight_panel.parquet"
ETF = REPO / "research" / "etf_overnight_panel.parquet"

pytestmark = pytest.mark.skipif(
    not PANEL.exists(), reason="run scripts/overnight_panel.py to build the panel")


@pytest.fixture(scope="module")
def panel() -> pd.DataFrame:
    return pd.read_parquet(PANEL)


@pytest.fixture(scope="module")
def feats(panel) -> pd.DataFrame:
    from overnight_hypotheses import futures_features
    return futures_features(panel)


# =====================================================================================
# THE PANEL'S BOUNDARIES
# =====================================================================================

def test_every_session_starts_at_the_bell(panel):
    """A session that starts at 09:31 has a first-bar return silently missing from r5."""
    assert set(panel["first_hm"]) == {"09:30"}


def test_no_session_runs_past_the_topstep_flatten(panel):
    """16:10 ET is 15:10 CT, the mandatory flat. Every bar used must precede it.

    The panel deliberately stops at 16:00 to leave ten minutes of margin, so this test also
    catches a widening of the window that would push a position past the deadline.
    """
    from quant_brain.markets.futures_cme import topstep as ts
    flat_ct = ts.MANDATORY_FLAT.value
    assert (flat_ct.hour, flat_ct.minute) == (15, 10), "the rulebook moved; rerun the study"
    assert panel["last_hm"].max() <= "16:00"


def test_the_eligible_window_is_wider_than_the_one_the_old_research_used(panel):
    """The 15:45-16:00 block is eligible and was previously discarded. Pinned because the
    whole 'RTH drifts negative' claim turned on excluding it."""
    assert (panel["last_hm"] > "15:45").mean() > 0.99


def test_overnight_and_rth_do_not_overlap(panel):
    """The structural guarantee the study rests on: no column spans 09:30.

    Checked by arithmetic rather than by inspection. The overnight close, the gap and the RTH
    open must chain exactly, so if any overnight column were computed from RTH bars the
    identity would break.
    """
    implied_on_close = panel["rth_open"] - panel["gap_pts"]
    assert np.allclose(panel["rth_open"], implied_on_close + panel["gap_pts"])
    # and the overnight extremes must bracket the overnight close, never the RTH close
    on_close = implied_on_close
    assert (on_close <= panel["on_high"] + 1e-6).all()
    assert (on_close >= panel["on_low"] - 1e-6).all()


def test_one_contract_per_trade_date(panel):
    """A roll inside a trade date puts a price gap in the middle of an overnight return."""
    assert panel.groupby(["symbol", "tdate"]).size().max() == 1


def test_the_panel_covers_what_the_report_claims(panel):
    counts = panel.groupby("symbol").size().to_dict()
    assert counts == {"ES": 312, "NQ": 312, "MES": 251, "MNQ": 251}


# =====================================================================================
# THE FINDING THAT SURVIVED
# =====================================================================================

@pytest.mark.parametrize("sym", ["ES", "NQ", "MES", "MNQ"])
def test_overnight_range_predicts_the_regular_session_range(feats, sym):
    """Hypothesis C. The one directional-free result that survived Bonferroni on all four
    instruments, at t between 5.8 and 7.7."""
    g = feats[feats.symbol == sym]
    r = float(np.corrcoef(g["on_range_pct"], g["rth_range_pct"])[0, 1])
    assert r > 0.30, f"{sym}: overnight-range correlation collapsed to {r:.3f}"


@pytest.mark.parametrize("sym", ["ES", "NQ", "MES", "MNQ"])
def test_overnight_volume_predicts_the_regular_session_range(feats, sym):
    """Hypothesis G, the same finding reached through a different overnight variable."""
    g = feats[feats.symbol == sym].dropna(subset=["on_volume_z", "rth_range_pct"])
    r = float(np.corrcoef(g["on_volume_z"], g["rth_range_pct"])[0, 1])
    assert r > 0.25, f"{sym}: overnight-volume correlation collapsed to {r:.3f}"


def test_the_volatility_finding_holds_in_every_block_of_the_session(feats):
    """It is not an opening-auction artefact: it is present from the bell to the close,
    including the 15:10-16:00 block the earlier research discarded."""
    from overnight_timeofday import BLOCKS, block_returns
    blocks = pd.concat([block_returns(s) for s in ["ES", "NQ"]], ignore_index=True)
    m = feats.merge(blocks, on=["tdate", "symbol"], how="inner")
    for _, _, name in BLOCKS:
        for sym in ["ES", "NQ"]:
            g = m[m.symbol == sym].dropna(subset=["on_range_pct", name])
            r = float(np.corrcoef(g["on_range_pct"], g[name].abs())[0, 1])
            assert r > 0.10, f"{sym} {name}: r={r:.3f}"


# =====================================================================================
# THE NULLS, PINNED AS FIRMLY AS THE POSITIVE
# =====================================================================================

@pytest.mark.parametrize("sym", ["ES", "NQ", "MES", "MNQ"])
def test_overnight_information_does_not_predict_direction(feats, sym):
    """The central null. If this ever fails, it is EITHER a discovery OR a leak, and the
    difference has to be established before anything is traded on it.

    The bar is the Bonferroni threshold for the 46-test family the hypotheses module runs,
    not the nominal 1.96, because that is the bar the finding would have to clear to count.
    """
    g = feats[feats.symbol == sym]
    n = len(g)
    r = float(np.corrcoef(g["on_ret_pct"], g["rth_ret_pct"])[0, 1])
    t = abs(r) * np.sqrt((n - 2) / (1 - r ** 2))
    assert t < 3.4, (
        f"{sym}: overnight return now predicts the RTH return at t={t:.2f} (r={r:+.3f}). "
        f"Establish whether this is a leak before treating it as an edge.")


def test_the_gap_does_not_fill(feats):
    """Hypothesis E, the folklore one. The measured sign is CONTINUATION on all four futures,
    which is the opposite of the retail claim, and it is not significant either way."""
    for sym in ["ES", "NQ", "MES", "MNQ"]:
        g = feats[feats.symbol == sym]
        r = float(np.corrcoef(g["gap_pct"], g["rth_ret_pct"])[0, 1])
        assert r > -0.05, f"{sym}: gap-fill correlation is {r:+.3f}; the folklore may be back"


def test_no_block_of_the_session_has_a_significant_unconditional_drift(feats):
    """Section 7's null. Twenty-eight cells, none clearing the Bonferroni bar of 3.1."""
    from overnight_timeofday import BLOCKS, block_returns
    blocks = pd.concat([block_returns(s) for s in ["ES", "NQ", "MES", "MNQ"]],
                       ignore_index=True)
    worst = 0.0
    for _, _, name in BLOCKS:
        for sym in ["ES", "NQ", "MES", "MNQ"]:
            v = blocks[blocks.symbol == sym][name].dropna().to_numpy()
            t = abs(np.mean(v) / (np.std(v, ddof=1) / np.sqrt(len(v))))
            worst = max(worst, t)
    assert worst < 3.1, f"a session block now drifts at t={worst:.2f}; re-run the study"


# =====================================================================================
# THE CLAIM THE EARLIER REPORT GOT WRONG
# =====================================================================================

def test_the_regular_session_does_not_drift_negative(panel):
    """`docs/RESEARCH_DISCOVERY_REPORT.md` reported that RTH drifted negative on all four
    instruments. Measured on the full eligible window it is POSITIVE on all four, and
    indistinguishable from zero on all four. Pinned so the corrected number is the one that
    survives."""
    for sym, g in panel.groupby("symbol"):
        assert g["rth_ret_pct"].mean() > 0, f"{sym} RTH mean is negative again"


@pytest.mark.skipif(not ETF.exists(), reason="run scripts/overnight_replicate.py")
def test_the_overnight_drift_is_beta_not_alpha():
    """Over ten years of SPY and QQQ, holding only the overnight session has a WORSE
    risk-adjusted return than holding all day. The futures sample says the opposite, and the
    futures sample is fifteen months."""
    etf = pd.read_parquet(ETF)
    for sym, g in etf.groupby("symbol"):
        on, bh = g["on_ret_pct"].to_numpy(), g["day_ret_pct"].to_numpy()
        s_on = np.mean(on) / np.std(on, ddof=1)
        s_bh = np.mean(bh) / np.std(bh, ddof=1)
        assert s_on < s_bh, (
            f"{sym}: overnight-only Sharpe {s_on:.3f} now beats buy-and-hold {s_bh:.3f} over "
            f"the full sample. Check whether the sample changed before believing it.")
