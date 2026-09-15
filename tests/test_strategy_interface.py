"""The frozen-strategy interface, and the two defects the reconciliation found.

The interface promises that a spec is immutable input: the engine runs it, does not tune it,
and records enough provenance that a result can be traced to the exact code that produced it.
These tests pin that promise, and pin the two bugs the independent reconciliation surfaced
while the interface was being built.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from quant_brain.research.reference_ledger import run_reference  # noqa: E402
from quant_brain.research.strategy_spec import (  # noqa: E402
    CostSpec,
    ExitSpec,
    SessionSpec,
    SizingSpec,
    StrategySpec,
)


def _sig(X):
    return np.zeros(len(X))


def _spec(**kw) -> StrategySpec:
    base = {"name": "t", "instrument": "MNQ", "timeframe": "1min", "signal": _sig}
    base.update(kw)
    return StrategySpec(**base)


# =====================================================================================
# THE SPEC IS IMMUTABLE AND HASHED
# =====================================================================================

def test_the_spec_is_frozen():
    import dataclasses
    s = _spec()
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.name = "changed"


def test_the_hash_covers_the_signal_BODY_not_just_its_name():
    """Two strategies with the same name and different logic must not share a hash."""
    def a(X):
        return np.zeros(len(X))

    def b(X):
        return np.ones(len(X))
    assert _spec(signal=a).spec_hash != _spec(signal=b).spec_hash


def test_the_hash_changes_when_any_execution_assumption_changes():
    base = _spec()
    assert base.spec_hash != _spec(sizing=SizingSpec(contracts=5)).spec_hash
    assert base.spec_hash != _spec(
        exit=ExitSpec(stop_atr=1.0, use_invalidation=False)).spec_hash
    assert base.spec_hash != _spec(cost=CostSpec(slippage_ticks=1.0)).spec_hash
    assert base.spec_hash != _spec(session=SessionSpec(warmup_bars=30)).spec_hash


def test_the_same_spec_hashes_identically_twice():
    assert _spec().spec_hash == _spec().spec_hash


# =====================================================================================
# THE SPEC REFUSES AMBIGUITY RATHER THAN CHOOSING
# =====================================================================================

def test_two_conflicting_stops_are_refused_not_silently_prioritised():
    """Any two of the three stop forms, in any combination. The message names which ones.

    The wording moved from "two different stops" to "N different stops" when `stop_points`
    made three forms possible; the pin is on the refusal and on the conflict being named,
    not on the number word.
    """
    with pytest.raises(ValueError, match="different stops"):
        ExitSpec(stop_atr=1.0, structural_stop=True, use_invalidation=False)
    with pytest.raises(ValueError, match="different stops"):
        ExitSpec(stop_atr=1.0, stop_points=10.0, use_invalidation=False)
    with pytest.raises(ValueError, match="different stops"):
        ExitSpec(stop_points=10.0, structural_stop=True, use_invalidation=False)


def test_an_exit_with_no_way_out_must_say_so_explicitly():
    with pytest.raises(ValueError, match="no way to close"):
        ExitSpec(use_invalidation=False)


def test_a_session_past_the_mandatory_flat_is_refused():
    with pytest.raises(ValueError, match="mandatory flat"):
        SessionSpec(close_et="16:30")


def test_an_unsupported_timeframe_is_refused_rather_than_resampled():
    with pytest.raises(ValueError, match="not supported"):
        _spec(timeframe="5min")


def test_nonsense_exit_parameters_are_refused():
    with pytest.raises(ValueError):
        ExitSpec(target_r=-1.0)
    with pytest.raises(ValueError):
        ExitSpec(stop_atr=0.0, target_r=1.0, use_invalidation=False)
    with pytest.raises(ValueError):
        ExitSpec(time_stop_bars=0, use_invalidation=False)


def test_sizing_above_its_own_ceiling_is_refused():
    with pytest.raises(ValueError, match="exceeds max_contracts"):
        SizingSpec(contracts=10, max_contracts=5)


# =====================================================================================
# THE TWO DEFECTS THE RECONCILIATION FOUND
# =====================================================================================

def test_no_position_may_be_opened_on_the_final_bar():
    """Found by the independent reference.

    A position opened on the last bar cannot be held - the session ends flat - so it is
    entered and closed at the same price and can only lose a round turn. The runner always
    refused those entries; the reference did not, and the two disagreed by exactly one round
    turn on every session whose signal fired on the final bar. That was a HIDDEN ASSUMPTION,
    not an arithmetic error, and it is now a named parameter on both sides.
    """
    closes = [100.0, 100.0, 100.0, 100.0]
    pos = [0.0, 0.0, 0.0, 1.0]            # fires on the final bar only
    ref = run_reference(pos, closes, multiplier=1.0, contracts=1, round_turn_cost=10.0)
    assert ref.round_turns == 0.0, "a last-bar entry was taken; it cannot be held"
    assert ref.net_pnl == pytest.approx(0.0)
    assert not ref.trades


def test_an_existing_position_may_still_CLOSE_on_the_final_bar():
    """The cutoff blocks new entries. It must not block the mandatory flatten."""
    closes = [100.0, 101.0, 102.0, 103.0]
    pos = [1.0, 1.0, 1.0, 1.0]
    ref = run_reference(pos, closes, multiplier=1.0, contracts=1, round_turn_cost=2.0)
    assert ref.final_position == 0
    assert ref.round_turns == pytest.approx(1.0)
    assert ref.gross_pnl == pytest.approx(3.0)


def test_session_accounting_has_no_entry_policy_and_that_split_is_deliberate():
    """`session_accounting` accounts whatever position series it is handed; the entry policy
    lives in the runner and the reference. Recording the split stops a future reader assuming
    the low-level function enforces it."""
    import futures_discover as fd
    closes = [100.0] * 6
    pos = [0.0, 0.0, 0.0, 0.0, 0.0, 1.0]
    _, turns, _ = fd.session_accounting(np.asarray(pos), np.asarray(closes),
                                        multiplier=1.0, contracts=1, round_turn_cost=4.0)
    ref = run_reference(pos, closes, multiplier=1.0, contracts=1, round_turn_cost=4.0)
    assert ref.round_turns == 0.0, "the reference must apply the cutoff"
    assert turns == pytest.approx(1.0), "session_accounting deliberately has no entry policy"


def test_two_cost_assumptions_must_not_be_compared_across():
    """The second defect: the runner validated its REALISTIC (0.5 tick) result against a
    ZERO-slippage reference and reported INVALID with a gap of exactly one scenario's
    slippage - 27 trades x $0.25 = $6.75. The reconciliation was right; the caller was
    comparing two different things."""
    closes = [100.0, 101.0, 101.0]
    pos = [1.0, 1.0, 0.0]
    cheap = run_reference(pos, closes, multiplier=1.0, contracts=1, round_turn_cost=1.0)
    dear = run_reference(pos, closes, multiplier=1.0, contracts=1, round_turn_cost=2.0)
    assert cheap.net_pnl - dear.net_pnl == pytest.approx(1.0)


# =====================================================================================
# END TO END
# =====================================================================================

def test_the_example_spec_produced_a_validated_package():
    runs = REPO / "research" / "strategy_runs"
    hits = sorted(runs.glob("example_failed_reversal_*_result.json"))
    if not hits:
        pytest.skip("run scripts/run_strategy.py --spec examples.example_strategy:SPEC")
    r = json.loads(hits[-1].read_text(encoding="utf-8"))
    assert r["validation"]["status"] == "VALIDATED", r["validation"]["failures"]
    for k in ("ledger_reconciles", "equity_reconciles", "independent_reconciles"):
        assert r["validation"][k], k
    assert r["provenance"]["spec_hash"] == r["spec_hash"]
    assert r["provenance"]["data_hash"]
    assert r["provenance"]["git_sha"]
    assert r["provenance"]["sessions"] > 0
