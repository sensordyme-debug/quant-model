"""The orchestration: canonical frame in, engine result plus manifest and reconciliation out.

This is the only place the pieces are wired together, and it is deliberately linear so the
order of operations is readable in one pass:

    assert the posture        research only, certified engine version
    adapt                     canonical frame -> upstream bars, refusing anything inexact
    validate                  upstream's own validator, on the bars it will actually consume
    run                       the upstream engine, with the profiles supplied
    reconcile                 recompute the money independently from the fills
    manifest                  hash the inputs and the assumptions

No number is computed here. Every figure in a ``RunResult`` came either from the engine or
from ``reference.arithmetic``, and the two are kept separate precisely so their agreement
means something.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pandas as pd

from quant_brain.data.schema import DataForm
from topstep_backtester.adapters.bars import BarAdapterReport, to_upstream_bars
from topstep_backtester.archive import assert_active
from topstep_backtester.manifests.manifest import RunManifest, build_manifest
from topstep_backtester.profiles.account import TOPSTEP_50K_COMBINE, AccountProfile
from topstep_backtester.profiles.execution import BASELINE, ExecutionProfile
from topstep_backtester.reference.arithmetic import (
    Reconciliation,
    ReferenceFill,
    ReferenceLedger,
    reference_ledger,
)
from topstep_backtester.safety import assert_research_only
from topstep_backtester.strategies.spec import FrozenStrategySpec
from topstep_backtester.upstream import (
    Backtest,
    assert_certified_version,
    spec_for_symbol,
    validate_bars,
)


class DataRefused(ValueError):
    """The bars did not pass upstream validation. The run does not start."""


@dataclass(frozen=True)
class RunResult:
    """Everything one backtest produced, with its provenance attached."""

    manifest: RunManifest
    bar_report: BarAdapterReport
    validation_issues: tuple[tuple[str, str], ...]
    #: The upstream ``BacktestResult``. Not copied, not reshaped - the authority.
    result: Any
    #: The upstream ``SummaryStats``.
    stats: Any
    reference: ReferenceLedger
    reconciliation: Reconciliation
    account_profile: AccountProfile
    execution_profile: ExecutionProfile
    spec: FrozenStrategySpec

    @property
    def run_id(self) -> str:
        return self.manifest.run_id

    @property
    def reconciled(self) -> bool:
        return self.reconciliation.agrees


def _reference_fills(replay: Any) -> tuple[ReferenceFill, ...]:
    """Project the engine's fill events onto the four facts the reference arithmetic needs."""
    out: list[ReferenceFill] = []
    for event in replay.fill_events:
        if getattr(event, "voided", False):
            #: A voided fill was reversed by the engine; including it would double-count.
            continue
        out.append(
            ReferenceFill(
                side=str(event.side),
                size=int(event.size),
                price=Decimal(str(event.price)),
                costs=Decimal(str(event.costs)),
            )
        )
    return tuple(out)


def run_backtest(
    frame: pd.DataFrame,
    strategy_factory: Callable[[str], Any],
    *,
    spec: FrozenStrategySpec,
    data_form: DataForm = DataForm.RAW,
    account_profile: AccountProfile = TOPSTEP_50K_COMBINE,
    execution_profile: ExecutionProfile = BASELINE,
    contract_id_override: str | None = None,
    operator: str = "",
    dataset_manifest_id: str = "",
    notes: Sequence[str] = (),
    allow_archived: bool = False,
) -> RunResult:
    """Run one frozen strategy over one canonical frame under one set of assumptions.

    ``strategy_factory`` receives the resolved contract id and returns a strategy INSTANCE.
    It is a factory rather than an instance because a strategy carries per-run state, and
    reusing one across profiles would let the first run's state leak into the second.
    """
    #: This engine is FROZEN. LEAN is the authoritative backtester; see archive.py.
    assert_active(allow_archived=allow_archived)
    assert_research_only()
    assert_certified_version()
    spec.assert_runnable()

    if spec.instrument != "" and spec.instrument not in frame["instrument"].astype(str).unique():
        raise ValueError(
            f"the spec is frozen for {spec.instrument!r} but the frame carries "
            f"{sorted(frame['instrument'].astype(str).unique())}. Running a strategy on an "
            f"instrument it was not frozen for is switching instruments after the fact."
        )

    bars, bar_report = to_upstream_bars(
        frame,
        instrument=spec.instrument,
        bar_interval=spec.bar_interval,
        data_form=data_form,
        contract_id_override=contract_id_override,
    )

    report = validate_bars(bars, spec_for_symbol(spec.instrument))
    issues = tuple((issue.code, issue.message) for issue in report.issues)
    if not report.ok:
        errors = [f"[{code}] {message}" for code, message in issues]
        raise DataRefused(
            f"{spec.instrument} {spec.bar_interval}: upstream validation failed with "
            f"{len(errors)} error(s). The run does not start on data the engine considers "
            f"malformed:\n  " + "\n  ".join(errors[:20])
        )

    contract_id = contract_id_override or bar_report.contract_ids[0]
    engine_report = Backtest(
        bars,
        strategy_factory(contract_id),
        account=account_profile.size,
        dll_enabled=account_profile.dll_enabled,
        fill_config=execution_profile.bar_fill_config(),
        broker_config=execution_profile.broker_config(),
        fee_model=execution_profile.fee_model(),
        record=True,
    ).run()

    result = engine_report.result
    instrument_spec = spec_for_symbol(spec.instrument)
    ledger = reference_ledger(
        _reference_fills(engine_report.replay),
        tick_size=instrument_spec.tick_size,
        tick_value=instrument_spec.tick_value,
    )

    engine_gross = sum((rt.gross_pnl for rt in result.round_trips), Decimal(0))
    engine_costs = sum((rt.costs for rt in result.round_trips), Decimal(0))
    reconciliation = Reconciliation(
        engine_gross=engine_gross,
        engine_costs=engine_costs,
        engine_net=engine_gross - engine_costs,
        reference_gross=ledger.gross_pnl,
        reference_costs=ledger.costs,
        reference_net=ledger.net_pnl,
        scaled_positions_seen=ledger.scaled_positions_seen,
        unclosed_qty=ledger.unclosed_qty,
    )

    manifest = build_manifest(
        bars=bars,
        bar_report=bar_report,
        spec=spec,
        account_profile=account_profile,
        execution_profile=execution_profile,
        operator=operator,
        dataset_manifest_id=dataset_manifest_id,
        notes=notes,
    )

    return RunResult(
        manifest=manifest,
        bar_report=bar_report,
        validation_issues=issues,
        result=result,
        stats=engine_report.stats,
        reference=ledger,
        reconciliation=reconciliation,
        account_profile=account_profile,
        execution_profile=execution_profile,
        spec=spec,
    )


def run_ladder(
    frame: pd.DataFrame,
    strategy_factory: Callable[[str], Any],
    *,
    spec: FrozenStrategySpec,
    ladder: Sequence[ExecutionProfile],
    **kwargs: Any,
) -> dict[str, RunResult]:
    """The same strategy at every rung, keyed by execution profile id.

    Returns all of them. A caller that wants one rung still gets the others, because the
    whole purpose of the ladder is that the flattering rung cannot be reported alone.
    """
    return {
        profile.profile_id: run_backtest(
            frame, strategy_factory, spec=spec, execution_profile=profile, **kwargs
        )
        for profile in ladder
    }


__all__ = ["DataRefused", "RunResult", "run_backtest", "run_ladder"]
