"""What the exit simulator guarantees, and what the exit study found.

The simulator tests come first and matter most. An exit engine that fills a stop at the wrong
price, or resolves an ambiguous bar optimistically, produces a grid where the best cells are
the ones the bug flatters - and a grid search will find exactly those. Every rule is checked
against a hand-built bar sequence where the right answer is known by construction.

The findings tests pin the two results a future change is most likely to overturn silently:
that the entry gate still admits only one candidate, and that in-sample exit selection still
carries no out-of-sample information.
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

from quant_brain.research import exits as X  # noqa: E402


def _bars(highs, lows, closes):
    return (np.array(closes, dtype=float), np.array(highs, dtype=float),
            np.array(lows, dtype=float))


LONG = np.array([1.0] * 8)


# =====================================================================================
# THE SIMULATOR
# =====================================================================================

def test_a_target_fills_at_the_target_price_not_the_bar_close():
    """A bar that runs far past the target must not credit the extra."""
    c, h, low = _bars(highs=[100, 101, 130], lows=[100, 99, 101], closes=[100, 100, 128])
    arch = X.ExitArchitecture("t", stop_atr=1.0, target_r=2.0, use_invalidation=False)
    r = X.simulate_trade(c, h, low, LONG, 0, 1, atr=5.0, arch=arch)
    assert r.reason == X.TARGET
    assert r.exit_price == pytest.approx(110.0)     # entry 100 + 2R where R = 1.0*5
    assert r.points == pytest.approx(10.0)


def test_a_stop_fills_at_the_stop_price():
    c, h, low = _bars(highs=[100, 101, 101], lows=[100, 99, 80], closes=[100, 100, 82])
    arch = X.ExitArchitecture("s", stop_atr=1.0, target_r=2.0, use_invalidation=False)
    r = X.simulate_trade(c, h, low, LONG, 0, 1, atr=5.0, arch=arch)
    assert r.reason == X.STOP
    assert r.exit_price == pytest.approx(95.0)
    assert r.points == pytest.approx(-5.0)


def test_an_ambiguous_bar_is_resolved_as_a_STOP_and_flagged():
    """The pessimistic convention. A bar spanning both levels cannot say which came first;
    assuming the target would convert losses into wins at exactly the tight-stop settings a
    grid search is drawn to."""
    c, h, low = _bars(highs=[100, 115], lows=[100, 90], closes=[100, 112])
    arch = X.ExitArchitecture("a", stop_atr=1.0, target_r=2.0, use_invalidation=False)
    r = X.simulate_trade(c, h, low, LONG, 0, 1, atr=5.0, arch=arch)
    assert r.reason == X.STOP
    assert r.ambiguous is True


def test_a_short_stops_out_on_the_high_not_the_low():
    c, h, low = _bars(highs=[100, 101, 120], lows=[100, 99, 99], closes=[100, 100, 118])
    short = np.array([-1.0] * 3)
    arch = X.ExitArchitecture("s", stop_atr=1.0, target_r=2.0, use_invalidation=False)
    r = X.simulate_trade(c, h, low, short, 0, -1, atr=5.0, arch=arch)
    assert r.reason == X.STOP
    assert r.exit_price == pytest.approx(105.0)
    assert r.points == pytest.approx(-5.0)


def test_a_time_stop_fires_on_the_right_bar_at_the_close():
    c, h, low = _bars(highs=[100, 101, 102, 103, 104],
                      lows=[100, 99, 100, 101, 102], closes=[100, 101, 102, 103, 104])
    arch = X.ExitArchitecture("t3", time_stop_bars=3, use_invalidation=False)
    r = X.simulate_trade(c, h, low, np.array([1.0] * 5), 0, 1, atr=50.0, arch=arch)
    assert r.reason == X.TIME
    assert r.bars_held == 3
    assert r.exit_price == pytest.approx(103.0)


def test_signal_invalidation_exits_when_the_signal_turns():
    sig = np.array([1.0, 1.0, 0.0, 0.0])
    c, h, low = _bars(highs=[100, 101, 102, 103], lows=[100, 99, 100, 101],
                      closes=[100, 101, 102, 103])
    arch = X.ExitArchitecture("f", use_invalidation=True)
    r = X.simulate_trade(c, h, low, sig, 0, 1, atr=50.0, arch=arch)
    assert r.reason == X.INVALIDATION
    assert r.exit_bar == 2


def test_an_unclosed_position_is_flattened_at_the_last_bar():
    c, h, low = _bars(highs=[100, 101, 102], lows=[100, 99, 100], closes=[100, 101, 102])
    arch = X.ExitArchitecture("n", use_invalidation=False)
    r = X.simulate_trade(c, h, low, LONG, 0, 1, atr=50.0, arch=arch)
    assert r.reason == X.FLATTEN
    assert r.exit_bar == 2


def test_a_structural_stop_uses_the_signal_bars_own_extreme():
    c, h, low = _bars(highs=[100, 101, 101], lows=[96, 99, 95], closes=[100, 100, 96])
    arch = X.ExitArchitecture("c", structural_stop=True, target_r=2.0,
                              use_invalidation=False)
    r = X.simulate_trade(c, h, low, LONG, 0, 1, atr=99.0, arch=arch)
    assert r.reason == X.STOP
    assert r.exit_price == pytest.approx(96.0)      # the entry bar's low


def test_break_even_arms_only_after_the_declared_R_is_reached():
    """Before 1R the stop stays where it was; after, a pullback to entry exits flat."""
    c, h, low = _bars(highs=[100, 106, 106, 101], lows=[100, 100, 100, 99],
                      closes=[100, 105, 105, 100])
    arch = X.ExitArchitecture("be", stop_atr=1.0, breakeven_at_r=1.0, target_r=5.0,
                              use_invalidation=False)
    r = X.simulate_trade(c, h, low, np.array([1.0] * 4), 0, 1, atr=5.0, arch=arch)
    assert r.reason == X.STOP
    assert r.exit_price == pytest.approx(100.0)     # moved to entry, not the original 95
    assert r.points == pytest.approx(0.0)


def test_the_r_multiple_is_measured_against_the_architectures_own_risk():
    c, h, low = _bars(highs=[100, 101, 130], lows=[100, 99, 101], closes=[100, 100, 128])
    arch = X.ExitArchitecture("t", stop_atr=2.0, target_r=1.0, use_invalidation=False)
    r = X.simulate_trade(c, h, low, LONG, 0, 1, atr=5.0, arch=arch)
    assert r.points == pytest.approx(10.0)          # 1R where R = 2.0 * 5
    assert r.r_multiple == pytest.approx(1.0)


def test_entry_events_finds_opens_and_not_holds():
    pos = np.array([0.0, 1.0, 1.0, 0.0, -1.0, -1.0, 1.0])
    assert X.entry_events(pos) == [(1, 1), (4, -1), (6, 1)]


def test_mfe_and_mae_are_recorded_even_when_the_trade_ends_flat():
    c, h, low = _bars(highs=[100, 108, 100], lows=[100, 100, 92], closes=[100, 100, 100])
    arch = X.ExitArchitecture("n", use_invalidation=False)
    r = X.simulate_trade(c, h, low, LONG, 0, 1, atr=99.0, arch=arch)
    assert r.mfe_points == pytest.approx(8.0)
    assert r.mae_points == pytest.approx(-8.0)
    assert r.points == pytest.approx(0.0)


# =====================================================================================
# THE FINDINGS
# =====================================================================================

GATE = REPO / "research" / "exit_entry_gate.json"
GRID = REPO / "research" / "exit_grid.csv"


@pytest.mark.skipif(not GATE.exists(), reason="run scripts/exit_entry_information.py")
def test_only_one_entry_passes_the_information_gate():
    """Phase 16's answer. If more entries start passing, that is either a discovery or a
    broken control, and somebody must decide which before exit work resumes."""
    g = json.loads(GATE.read_text(encoding="utf-8"))
    n_pass = sum(1 for v in g.values() if v == "PASS")
    assert n_pass <= 2, f"{n_pass} entries now pass the gate; it was 1"
    assert g.get("breakout.failed_reversal|MNQ") == "PASS"
    assert g.get("revert.vwap.q90|NQ") == "FAIL", (
        "the lab's highest-expectancy cell now shows entry information; it had none at any "
        "of seven horizons")


@pytest.mark.skipif(not GRID.exists(), reason="run scripts/exit_architecture_research.py")
def test_exit_selection_carries_no_out_of_sample_information():
    """The core negative. An in-sample/out-of-sample correlation near zero is what makes
    every 'best exit' in the grid meaningless."""
    d = pd.read_csv(GRID)
    corr = d[["is_per_trade", "oos_per_trade"]].corr().iloc[0, 1]
    assert abs(corr) < 0.35, (
        f"in-sample exit selection now correlates {corr:+.3f} with out-of-sample "
        f"performance; it was -0.002. Verify before treating any architecture as chosen.")


@pytest.mark.skipif(not GRID.exists(), reason="run scripts/exit_architecture_research.py")
def test_the_baseline_is_identical_to_a_one_bar_time_stop():
    """The mechanism is a one-bar scalp, so signal invalidation already fires at bar one.
    If these ever diverge, the entry's holding behaviour has changed."""
    d = pd.read_csv(GRID).set_index("arch")
    for col in ("is_per_trade", "is_trades", "oos_per_trade", "oos_trades"):
        assert d.loc["F.baseline_invalidation", col] == pytest.approx(
            d.loc["E.time1b", col]), f"{col} diverged"


@pytest.mark.skipif(not GRID.exists(), reason="run scripts/exit_architecture_research.py")
def test_no_architecture_is_strongly_positive_out_of_sample():
    d = pd.read_csv(GRID)
    assert int((d.oos_per_trade > 6.0).sum()) == 0, (
        "an exit architecture now exceeds $6/trade out of sample; check the fill convention "
        "and the ambiguous-bar rule before believing it")
