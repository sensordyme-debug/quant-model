"""A worked example of the frozen-strategy interface.

This is NOT a recommendation and NOT a strategy the research supports - every mechanism in
this repository has been rejected. It exists so the engine has something concrete to run, and
so the shape of a spec is documented by a working example rather than by prose.

The signal is the repository's own `breakout.failed_reversal` rule, transcribed, with the
thresholds passed in as literals rather than recalibrated. That makes the example fully
reproducible: no hidden calibration step sits between the spec and the result.
"""
from __future__ import annotations

import numpy as np

from quant_brain.research.strategy_spec import (
    CostSpec,
    ExitSpec,
    SessionSpec,
    SizingSpec,
    StrategySpec,
)

HI, LO = 1.900, -1.435          # MNQ train-split quantiles, frozen as literals


def failed_reversal_signal(X):
    """Long when an upside extension retraces below the 95th-percentile level; mirrored."""
    orp = np.nan_to_num(np.asarray(X["opening_range_pos"], dtype=float), nan=0.0)
    mins = np.nan_to_num(np.asarray(X["minutes_from_open"], dtype=float), nan=0.0)
    live = mins > 45
    prev = np.concatenate(([0.0], orp[:-1]))
    pos = np.zeros(len(orp), dtype=float)
    pos[live & (prev > HI) & (orp < HI)] = 1.0
    pos[live & (prev < LO) & (orp > LO)] = -1.0
    return pos


SPEC = StrategySpec(
    name="example_failed_reversal",
    instrument="MNQ",
    timeframe="1min",
    signal=failed_reversal_signal,
    exit=ExitSpec(use_invalidation=True),
    sizing=SizingSpec(contracts=1),
    session=SessionSpec(open_et="09:30", close_et="16:00", warmup_bars=45),
    cost=CostSpec(),
    rationale=("Example only. The mechanism was REJECTED in "
               "docs/FAILED_REVERSAL_REPLICATION.md - QQQ inverts its sign on the same "
               "index. It is used here purely to exercise the engine."),
)
