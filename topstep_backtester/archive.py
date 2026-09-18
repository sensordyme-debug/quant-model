"""Archival status for this package. It is FROZEN and is no longer a backtesting engine.

    STATUS: FROZEN / ARCHIVED
    ACTIVE_BACKTEST_ENGINE: NO

WHY IT WAS FROZEN
-----------------
The CVD_ABSORPTION_HARVESTER specification requires genuine tick-level trade and quote
information to reconstruct cumulative volume delta: each trade classified against the bid
and ask standing at that trade. The data reachable through this path does not provide
Time & Sales or order-flow information - a survey of all 2,779 parquet files in the store
found a minimum inter-record gap of 60 seconds and zero simultaneous prints, which is a
resampled grid rather than a trade sequence.

Two roads led out of that. Approximate the missing inputs, or keep expanding a custom engine
until it had a tick pipeline of its own. The project took neither: it migrated to
QuantConnect LEAN, which natively supports futures tick, trade and quote data, and which is
now the sole authoritative backtesting engine in this repository.

WHAT FREEZING DOES AND DOES NOT MEAN
------------------------------------
It does NOT mean deletion. Every module, test, manifest and result stays exactly where it
is, because results already reported under this engine have to remain reproducible - a
frozen engine that cannot be re-run is a set of numbers nobody can check.

It DOES mean the engine will not start a new strategy backtest by accident.
``run_backtest`` refuses unless the caller passes ``allow_archived=True``, which is a thing
you have to type on purpose and which reads, at the call site, as what it is: reproducing an
archived result rather than doing new research.

WHAT MUST NOT HAPPEN TO THIS PACKAGE
------------------------------------
No behaviour changes. Not the fill model, not the data handling, not the remaining
specification ambiguities, not the tick-data problem. Changing a frozen engine invalidates
every result recorded under it while leaving those results looking current, which is worse
than either keeping it or deleting it. If it needs to change, it is not archived any more
and that is a decision with a date on it.
"""
from __future__ import annotations

#: The two flags PART 2 of the migration brief asks for, as constants a test can read.
STATUS = "FROZEN / ARCHIVED"
ACTIVE_BACKTEST_ENGINE = False

#: When, and what replaced it.
ARCHIVED_ON = "2026-09-18"
SUPERSEDED_BY = "QuantConnect LEAN (sole authoritative backtesting engine)"

#: The engine this package wrapped. Recorded so the archive says what it was, not just that
#: it is closed.
WRAPPED_ENGINE = "topstep-backtest 0.4.0 (pip, site-packages, never modified)"

ARCHIVED_REASON = (
    "The strategy requires genuine tick-level trade and quote information for CVD "
    "reconstruction. The data available to this path does not provide sufficient "
    "Time & Sales / order-flow information. Rather than approximating the required inputs "
    "or continuing to expand a custom engine, the project has migrated to QuantConnect "
    "LEAN, which natively supports futures tick, trade and quote data."
)


class EngineArchived(RuntimeError):
    """An attempt to run new strategy research through the frozen engine."""


def assert_active(*, allow_archived: bool = False) -> None:
    """Gate every backtest entry point in this package.

    ``allow_archived=True`` is the documented escape for reproducing a result that was
    originally produced here. It is deliberately not a config value or an environment
    variable: it has to appear at the call site, where a reader can see that this particular
    call is archival rather than new research.
    """
    if ACTIVE_BACKTEST_ENGINE or allow_archived:
        return
    raise EngineArchived(
        f"topstep_backtester is {STATUS} as of {ARCHIVED_ON} and is no longer an active "
        f"backtesting engine.\n\n{ARCHIVED_REASON}\n\n"
        f"Superseded by: {SUPERSEDED_BY}. New strategy backtests go through "
        f"scripts/backtest.py and algorithms/<name>/main.py.\n"
        f"To reproduce a result originally produced by this engine, pass "
        f"allow_archived=True at the call site."
    )


def status() -> dict[str, object]:
    return {
        "package": "topstep_backtester",
        "status": STATUS,
        "active_backtest_engine": ACTIVE_BACKTEST_ENGINE,
        "archived_on": ARCHIVED_ON,
        "superseded_by": SUPERSEDED_BY,
        "wrapped_engine": WRAPPED_ENGINE,
        "reason": ARCHIVED_REASON,
        "code_retained": True,
        "results_retained": True,
        "behaviour_frozen": True,
    }


__all__ = [
    "ACTIVE_BACKTEST_ENGINE",
    "ARCHIVED_ON",
    "ARCHIVED_REASON",
    "STATUS",
    "SUPERSEDED_BY",
    "WRAPPED_ENGINE",
    "EngineArchived",
    "assert_active",
    "status",
]
