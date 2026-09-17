"""A thin, honest pass-through to the engine's Monte Carlo. No resampling happens here.

WHY NOT WRITE OUR OWN
---------------------
Upstream block-bootstraps whole TRADING DAYS, in blocks, which preserves two things a naive
per-trade shuffle destroys: the clustering of losses within a day, and the day-level
sequence the trailing drawdown rule actually operates on. A per-trade IID resample would
report a much better pass probability for the same strategy, and it would be wrong in a
direction that flatters. Reimplementing it here would just be a second chance to get that
wrong.

THE SEED IS NOT A PARAMETER
---------------------------
``DEFAULT_SEED`` is fixed and is not to be varied in search of a better number. Running
several seeds and reporting the best is the cleanest possible way to manufacture a pass
probability, so :func:`pass_probability_curve` runs one seed across several HORIZONS - which
answers a real question - rather than several seeds at one horizon, which answers none.

TWO FLAGS THAT TRAVEL WITH EVERY RESULT
---------------------------------------
``provisional`` means upstream judged the source sample too small for the output to be
load-bearing. ``source_truncated`` means the source run did not reach a terminal verdict.
Both are surfaced by :func:`describe`; neither may be dropped when quoting a probability,
because a pass probability from eleven days is a number about eleven days.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from topstep_backtester.upstream import monte_carlo

#: Fixed. See the module docstring - this is not a knob.
DEFAULT_SEED = 0
DEFAULT_PATHS = 2000
DEFAULT_BLOCK_LENGTH = 5

#: Horizons worth asking about for a Combine, in trading days. One week, two, a month, and
#: the open-ended case.
DEFAULT_HORIZONS: tuple[int | None, ...] = (5, 10, 20, 30, None)


@dataclass(frozen=True)
class HorizonRow:
    horizon_days: int | None
    pass_probability: Any
    mll_breach_probability: Any
    consistency_blocked_probability: Any
    target_not_reached_probability: Any
    provisional: bool
    source_truncated: bool

    @property
    def label(self) -> str:
        return "no limit" if self.horizon_days is None else f"{self.horizon_days} days"


def run(result: Any, *, params: Any, horizon_days: int | None = None,
        paths: int = DEFAULT_PATHS, block_length: int = DEFAULT_BLOCK_LENGTH,
        seed: int = DEFAULT_SEED) -> Any:
    """One upstream Monte Carlo, with this pipeline's fixed defaults."""
    return monte_carlo(
        result,
        params=params,
        paths=paths,
        horizon_days=horizon_days,
        block_length=block_length,
        seed=seed,
    )


def pass_probability_curve(
    result: Any, *, params: Any, horizons: Sequence[int | None] = DEFAULT_HORIZONS,
    paths: int = DEFAULT_PATHS, block_length: int = DEFAULT_BLOCK_LENGTH,
    seed: int = DEFAULT_SEED,
) -> tuple[HorizonRow, ...]:
    """P(pass) as a function of how long you are allowed to take.

    This is the shape that answers "can it pass in a week", and it answers it honestly:
    the same seed and the same source days at every horizon, so the only thing varying is
    the question.
    """
    rows: list[HorizonRow] = []
    for horizon in horizons:
        outcome = run(
            result, params=params, horizon_days=horizon, paths=paths,
            block_length=block_length, seed=seed,
        )
        rows.append(
            HorizonRow(
                horizon_days=horizon,
                pass_probability=outcome.pass_probability,
                mll_breach_probability=outcome.mll_breach_probability,
                consistency_blocked_probability=outcome.consistency_blocked_probability,
                target_not_reached_probability=outcome.target_not_reached_probability,
                provisional=bool(outcome.provisional),
                source_truncated=bool(outcome.source_truncated),
            )
        )
    return tuple(rows)


def describe(outcome: Any) -> dict[str, Any]:
    """Every field upstream reported, with the two caveat flags kept alongside."""
    return {
        "paths": outcome.paths,
        "horizon_days": outcome.horizon_days,
        "block_length": outcome.block_length,
        "seed": outcome.seed,
        "source_days": outcome.source_days,
        "provisional": bool(outcome.provisional),
        "source_truncated": bool(outcome.source_truncated),
        "pass_probability": str(outcome.pass_probability),
        "mll_breach_probability": str(outcome.mll_breach_probability),
        "consistency_blocked_probability": str(outcome.consistency_blocked_probability),
        "target_not_reached_probability": str(outcome.target_not_reached_probability),
        "dll_lock_rate": str(outcome.dll_lock_rate),
        "expected_days_to_pass": (
            None if outcome.expected_days_to_pass is None
            else str(outcome.expected_days_to_pass)
        ),
        "median_days_to_pass": (
            None if outcome.median_days_to_pass is None
            else str(outcome.median_days_to_pass)
        ),
        "p05_ending_balance": str(outcome.p05_ending_balance),
        "median_ending_balance": str(outcome.median_ending_balance),
        "p95_ending_balance": str(outcome.p95_ending_balance),
    }


def caveat(outcome: Any) -> str:
    """The sentence that must accompany any quoted probability from this outcome."""
    notes: list[str] = []
    if getattr(outcome, "provisional", False):
        notes.append(
            f"PROVISIONAL: upstream judged {outcome.source_days} source day(s) too few for "
            f"these statistics to be load-bearing"
        )
    if getattr(outcome, "source_truncated", False):
        notes.append(
            "SOURCE TRUNCATED: the underlying backtest did not reach a terminal verdict, so "
            "the resampled days describe an unfinished attempt"
        )
    if not notes:
        return (
            f"resampled from {outcome.source_days} source days, {outcome.paths} paths, "
            f"block length {outcome.block_length}, seed {outcome.seed}"
        )
    return " | ".join(notes)


__all__ = [
    "DEFAULT_BLOCK_LENGTH",
    "DEFAULT_HORIZONS",
    "DEFAULT_PATHS",
    "DEFAULT_SEED",
    "HorizonRow",
    "caveat",
    "describe",
    "pass_probability_curve",
    "run",
]
