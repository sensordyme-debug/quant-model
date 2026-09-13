"""The research engine: experiments, trial accounting, and the promotion ladder.

This package exists to make Quant Brain harder to fool, which is a different goal from making
it able to run more backtests. The single most important thing in here is that the number of
trials is READ FROM THE LEDGER rather than passed in by the caller. A candidate discovered
after 500 experiments cannot be evaluated as though it were the first, because nobody is
asked how many there were.
"""
from quant_brain.research.registry import (
    Candidate,
    Experiment,
    Ledger,
    Stage,
    Verdict,
)

__all__ = ["Candidate", "Experiment", "Ledger", "Stage", "Verdict"]
