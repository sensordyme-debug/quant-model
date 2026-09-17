"""Does the same input still give the same number, and does a number still match its inputs?

TWO DIFFERENT QUESTIONS
-----------------------
DETERMINISM asks whether running the pipeline twice on the same bars produces the same
result. It is checked by actually running it twice and comparing the numbers, not by
inspecting the code for sources of nondeterminism - the latter is how you conclude that
dict ordering is fine right up until it is not.

STALENESS asks the opposite: given a result recorded earlier, are the things that produced
it still what they were? A stored result carries the hashes of its bars, its spec, its
profiles and the Layer B source. If any of them has moved, the result describes a pipeline
that no longer exists, and quoting it is quoting a version of the code nobody can run.

The second is the one that bites in practice. A backtest is run, a threshold is adjusted
three days later, and the number in the report is still the old one - not through dishonesty
but because nothing connected the two.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from topstep_backtester.manifests.manifest import RunManifest, hash_layer_b_source
from topstep_backtester.upstream import api_fingerprint_hash


class DeterminismError(AssertionError):
    """Two runs of the same thing disagreed."""


class StaleResultError(AssertionError):
    """A recorded result no longer matches what produced it."""


#: The fields compared between two runs. Chosen because between them they cover the whole
#: accounting surface: if these all agree, no trade moved and no dollar changed.
_COMPARED = (
    "ending_balance",
    "total_profit",
    "best_day",
    "days_traded",
    "trade_count",
)


@dataclass(frozen=True)
class DeterminismReport:
    run_id_a: str
    run_id_b: str
    matched_fields: tuple[str, ...]
    mismatches: tuple[tuple[str, str, str], ...]
    equity_curves_identical: bool
    round_trips_identical: bool

    @property
    def deterministic(self) -> bool:
        return (
            self.run_id_a == self.run_id_b
            and not self.mismatches
            and self.equity_curves_identical
            and self.round_trips_identical
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id_a": self.run_id_a,
            "run_id_b": self.run_id_b,
            "deterministic": self.deterministic,
            "matched_fields": list(self.matched_fields),
            "mismatches": [
                {"field": f, "first": a, "second": b} for f, a, b in self.mismatches
            ],
            "equity_curves_identical": self.equity_curves_identical,
            "round_trips_identical": self.round_trips_identical,
        }


def check_determinism(run_once: Callable[[], Any]) -> DeterminismReport:
    """Run the supplied backtest twice and compare everything that could move.

    ``run_once`` must construct a FRESH strategy each time. Reusing an instance would carry
    the first run's state into the second, and the comparison would then be testing whether
    the strategy is stateless rather than whether the pipeline is deterministic.
    """
    first = run_once()
    second = run_once()

    mismatches: list[tuple[str, str, str]] = []
    matched: list[str] = []
    for field in _COMPARED:
        a = getattr(first.result, field)
        b = getattr(second.result, field)
        if a != b:
            mismatches.append((field, str(a), str(b)))
        else:
            matched.append(field)

    equity_same = tuple(first.result.equity_curve) == tuple(second.result.equity_curve)
    trips_same = tuple(
        (rt.direction, rt.opened_ts_ns, rt.closed_ts_ns, rt.gross_pnl, rt.costs)
        for rt in first.result.round_trips
    ) == tuple(
        (rt.direction, rt.opened_ts_ns, rt.closed_ts_ns, rt.gross_pnl, rt.costs)
        for rt in second.result.round_trips
    )

    return DeterminismReport(
        run_id_a=first.run_id,
        run_id_b=second.run_id,
        matched_fields=tuple(matched),
        mismatches=tuple(mismatches),
        equity_curves_identical=equity_same,
        round_trips_identical=trips_same,
    )


def assert_deterministic(run_once: Callable[[], Any]) -> DeterminismReport:
    report = check_determinism(run_once)
    if not report.deterministic:
        raise DeterminismError(
            f"the same backtest produced different results on two runs:\n"
            f"  run_id {report.run_id_a} vs {report.run_id_b}\n"
            f"  field mismatches: {report.mismatches}\n"
            f"  equity curve identical: {report.equity_curves_identical}\n"
            f"  round trips identical: {report.round_trips_identical}\n"
            f"A nondeterministic backtest cannot be reproduced, reviewed or trusted."
        )
    return report


@dataclass(frozen=True)
class StalenessReport:
    run_id: str
    spec_hash_current: bool
    code_hash_current: bool
    upstream_api_current: bool
    details: tuple[str, ...]

    @property
    def current(self) -> bool:
        return self.spec_hash_current and self.code_hash_current and self.upstream_api_current


def check_staleness(manifest: RunManifest, *, spec: Any = None) -> StalenessReport:
    """Is a recorded result still a description of the pipeline as it stands now?"""
    details: list[str] = []

    spec_ok = True
    if spec is not None:
        spec_ok = spec.spec_hash == manifest.spec_hash
        if not spec_ok:
            details.append(
                f"spec hash moved: the result was produced under {manifest.spec_hash} but "
                f"the spec now hashes to {spec.spec_hash}. The strategy changed after the "
                f"result was recorded."
            )

    current_code = hash_layer_b_source()
    code_ok = current_code == manifest.code_hash
    if not code_ok:
        details.append(
            f"Layer B source moved: recorded {manifest.code_hash}, now {current_code}. The "
            f"adapter, profiles or runner changed since this number was produced."
        )

    current_api = api_fingerprint_hash()
    api_ok = current_api == manifest.upstream_api_fingerprint
    if not api_ok:
        details.append(
            f"upstream API moved: recorded {manifest.upstream_api_fingerprint}, now "
            f"{current_api}. The engine was upgraded or replaced; re-certify before "
            f"comparing anything to this result."
        )

    return StalenessReport(
        run_id=manifest.run_id,
        spec_hash_current=spec_ok,
        code_hash_current=code_ok,
        upstream_api_current=api_ok,
        details=tuple(details),
    )


def assert_current(manifest: RunManifest, *, spec: Any = None) -> None:
    report = check_staleness(manifest, spec=spec)
    if not report.current:
        raise StaleResultError(
            f"result {report.run_id} is stale:\n  " + "\n  ".join(report.details)
        )


def assert_reconciled(run: Any) -> None:
    """The engine and the independent arithmetic must agree exactly."""
    if not run.reconciled:
        recon = run.reconciliation
        raise AssertionError(
            f"run {run.run_id}: the engine and reference/arithmetic.py disagree.\n"
            f"  gross: engine {recon.engine_gross} vs reference {recon.reference_gross} "
            f"(delta {recon.gross_delta})\n"
            f"  net:   engine {recon.engine_net} vs reference {recon.reference_net} "
            f"(delta {recon.net_delta})\n"
            f"Two independent calculations of the same money do not agree; one of them is "
            f"wrong and neither may be quoted until it is known which."
        )


def assert_no_free_money(run: Any) -> None:
    """A sanity floor: costs must be non-negative and charged on every round trip.

    Cheap, and it catches the single most embarrassing category of backtest defect - a fee
    model silently not wired up, which turns every marginal strategy profitable.
    """
    if not run.result.round_trips:
        return
    uncharged = [rt for rt in run.result.round_trips if rt.costs <= Decimal(0)]
    if uncharged:
        raise AssertionError(
            f"run {run.run_id}: {len(uncharged)} of {len(run.result.round_trips)} round "
            f"trips were charged no costs. Either the fee model is not wired up or the "
            f"execution profile is not reaching the engine."
        )


__all__ = [
    "DeterminismError",
    "DeterminismReport",
    "StaleResultError",
    "StalenessReport",
    "assert_current",
    "assert_deterministic",
    "assert_no_free_money",
    "assert_reconciled",
    "check_determinism",
    "check_staleness",
]
