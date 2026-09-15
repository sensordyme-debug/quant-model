"""The frozen rule and its falsification, pinned.

Two jobs. First, the rule must stay frozen: a hash and a behavioural equivalence check against
the live tournament implementation, so an edit there cannot silently change what "the failed
reversal effect" refers to. Second, the falsification must stay findable - the QQQ inversion is
the whole result, and if it ever disappears somebody has to look at why.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from failed_reversal_spec import (  # noqa: E402
    SPEC,
    failed_reversal,
    rule_hash,
    verify_against_library,
)

SPEC_JSON = REPO / "research" / "failed_reversal_spec.json"
INST = REPO / "research" / "fr_replication_instruments.csv"
ERA = REPO / "research" / "fr_replication_eras.csv"
FRICTION = REPO / "research" / "fr_replication_friction.csv"


# =====================================================================================
# THE RULE STAYS FROZEN
# =====================================================================================

def test_the_frozen_rule_still_matches_the_live_implementation():
    ok, msg = verify_against_library()
    assert ok, msg


def test_the_rule_hash_is_unchanged():
    """If this fails, every result carrying the old hash refers to a different rule."""
    assert rule_hash() == "8ed5bb73283cb506"


def test_the_spec_records_no_stop_and_no_target():
    assert SPEC["stop"] == "NONE"
    assert SPEC["target"] == "NONE"
    assert SPEC["warmup_minutes"] == 45
    assert SPEC["upper_quantile"] == 0.95
    assert SPEC["lower_quantile"] == 0.05


# =====================================================================================
# THE RULE'S MECHANICS, ON HAND-BUILT INPUT
# =====================================================================================

def test_a_long_fires_only_when_the_previous_bar_was_above_the_threshold():
    orp = np.array([0.0, 2.0, 1.0, 1.0])
    mins = np.array([50.0, 51.0, 52.0, 53.0])
    pos = failed_reversal(orp, mins, hi=1.5, lo=-1.5)
    assert list(pos) == [0.0, 0.0, 1.0, 0.0], "long must fire on the crossing bar only"


def test_a_short_mirrors_the_long_on_the_downside():
    orp = np.array([0.0, -2.0, -1.0, -1.0])
    mins = np.array([50.0, 51.0, 52.0, 53.0])
    pos = failed_reversal(orp, mins, hi=1.5, lo=-1.5)
    assert list(pos) == [0.0, 0.0, -1.0, 0.0]


def test_the_direction_is_WITH_the_original_breakout():
    """The correction to the previous phase's prose. An upside extension that pulls back
    produces a LONG, not a short: the bet is that the retracement fails."""
    orp = np.array([0.0, 3.0, 1.0])
    pos = failed_reversal(orp, np.array([50.0, 51.0, 52.0]), hi=1.5, lo=-1.5)
    assert pos[2] == 1.0, "an upside failed reversal must be LONG"


def test_the_45_minute_warmup_suppresses_early_signals():
    orp = np.array([0.0, 2.0, 1.0])
    early = failed_reversal(orp, np.array([10.0, 20.0, 30.0]), hi=1.5, lo=-1.5)
    late = failed_reversal(orp, np.array([50.0, 51.0, 52.0]), hi=1.5, lo=-1.5)
    assert not early.any()
    assert late.any()


def test_the_hardcoded_first_prev_cannot_fire_a_signal():
    """`prev` is 0.0 at bar 0. With a positive hi and negative lo that can never trigger,
    and the warm-up excludes bar 0 anyway - but pin it so a threshold change is caught."""
    pos = failed_reversal(np.array([1.0, 1.0]), np.array([99.0, 99.0]), hi=1.5, lo=-1.5)
    assert pos[0] == 0.0


# =====================================================================================
# THE FALSIFICATION
# =====================================================================================

@pytest.mark.skipif(not INST.exists(), reason="run failed_reversal_replication.py")
def test_qqq_inverts_the_effect_on_the_same_index_as_mnq():
    """The result the whole study turns on. QQQ tracks the Nasdaq-100, as MNQ does."""
    d = pd.read_csv(INST).set_index(["panel", "symbol"])
    mnq = d.loc[("futures", "MNQ")]
    qqq = d.loc[("etf", "QQQ")]
    assert mnq["mean_1"] > 0 and qqq["mean_1"] < 0, (
        "QQQ no longer inverts MNQ's sign; the falsification has changed and must be "
        "re-examined")
    assert qqq["ctrl_pctile_1"] < 0.10, (
        f"QQQ now sits at percentile {qqq['ctrl_pctile_1']:.1%} against its matched control; "
        f"it was 0.5%")
    assert qqq["entries"] > 10 * mnq["entries"] / 2, "QQQ should carry far more entries"


@pytest.mark.skipif(not ERA.exists(), reason="run failed_reversal_periods.py")
def test_the_inversion_holds_over_the_exact_futures_dates():
    """Rules out a period explanation: same index, same calendar window, opposite sign."""
    e = pd.read_csv(ERA)
    era = "2025-06..2026-09 (futures era)"
    q = e[(e.symbol == "QQQ") & (e.period == era)]
    m = e[(e.symbol == "MNQ") & (e.period == era)]
    assert len(q) and len(m)
    assert float(m.mean_1.iloc[0]) > 0 > float(q.mean_1.iloc[0]), (
        "QQQ and MNQ now agree in sign over the same dates; the period explanation is back "
        "on the table and the verdict needs revisiting")


@pytest.mark.skipif(not FRICTION.exists(), reason="run failed_reversal_friction.py")
def test_almost_everything_is_negative_after_costs():
    f = pd.read_csv(FRICTION)
    n_neg = int((f["net_1.0t"] <= 0).sum())
    assert n_neg >= 6, (
        f"only {n_neg} of {len(f)} instruments are negative at one tick; it was 7 of 8")


@pytest.mark.skipif(not SPEC_JSON.exists(), reason="run failed_reversal_spec.py")
def test_the_stored_spec_carries_the_same_hash():
    stored = json.loads(SPEC_JSON.read_text(encoding="utf-8"))
    assert stored["rule_hash"] == rule_hash()
    assert stored["matches_live_implementation"] is True
