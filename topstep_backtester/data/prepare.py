"""Load through the canonical layer, then apply the conditions the ENGINE additionally needs.

THE DIVISION OF LABOUR
----------------------
``quant_brain.data.loader.load`` reads a source through a named adapter, validates the
schema, runs the three-valued quality gate and refuses a FAIL. None of that is repeated
here. What this module adds is the short list of things that are fine for research in
general but not for THIS engine:

    execution validity   an adjusted continuous series has prices that were never quoted.
                         Fine for computing returns; not fine for computing fills.
    instrument coverage  the engine prices fifteen products. A dataset for anything else
                         cannot be backtested here at all.
    interval support     the engine needs a fixed nanosecond bar step, which rules out
                         daily and above on a 23-hour Globex day.

WARNINGS ARE CARRIED, NOT SWALLOWED
-----------------------------------
A WARN from the quality gate does not stop a run - the canonical layer already decided that,
and it requires every WARN to state why research may proceed. But a warning that is not
carried into the report is a warning that was not issued, so every one of them travels with
the prepared data and lands in the run manifest.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from quant_brain.data import loader as canonical_loader
from quant_brain.data.schema import DataForm
from topstep_backtester.adapters.bars import INTERVALS
from topstep_backtester.upstream import SPECS


class DataNotUsable(ValueError):
    """Canonical data that the engine specifically cannot consume."""


@dataclass(frozen=True)
class PreparedData:
    """A frame the engine can consume, plus everything known about where it came from."""

    frame: pd.DataFrame
    instrument: str
    bar_interval: str
    data_form: DataForm
    dataset_id: str
    manifest_id: str
    bars_fingerprint: str
    quality_status: str
    quality_warnings: tuple[str, ...]
    session_count: int
    coverage_start: str
    coverage_end: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "manifest_id": self.manifest_id,
            "bars_fingerprint": self.bars_fingerprint,
            "instrument": self.instrument,
            "bar_interval": self.bar_interval,
            "data_form": self.data_form.value,
            "quality_status": self.quality_status,
            "quality_warnings": list(self.quality_warnings),
            "session_count": self.session_count,
            "coverage_start": self.coverage_start,
            "coverage_end": self.coverage_end,
            "rows": len(self.frame),
        }


def _check_engine_preconditions(instrument: str, bar_interval: str,
                                data_form: DataForm, dataset_id: str) -> None:
    if instrument not in SPECS:
        raise DataNotUsable(
            f"{dataset_id}: instrument {instrument!r} has no upstream spec. The engine "
            f"prices {sorted(SPECS)}; without a tick size and tick value it cannot compute "
            f"a single dollar of P&L for this product."
        )
    if bar_interval not in INTERVALS:
        raise DataNotUsable(
            f"{dataset_id}: bar interval {bar_interval!r} has no fixed nanosecond step. "
            f"Supported: {sorted(INTERVALS)}."
        )
    if data_form.is_adjusted:
        raise DataNotUsable(
            f"{dataset_id}: {data_form.value} carries prices that were never quoted, "
            f"because the adjustment shifts one end of the history. Returns from it are "
            f"meaningful; FILLS from it are not, and a backtest is a claim about fills."
        )


def prepare(
    adapter: str,
    path: Path | str,
    *,
    session_timezone: str | None = None,
    require_quality: bool = True,
    **adapter_kwargs: Any,
) -> PreparedData:
    """Load a dataset and confirm the engine can actually consume it.

    ``require_quality`` is forwarded to the canonical loader unchanged. Passing False still
    runs the gate and still attaches its report; it only declines to raise on FAIL, and the
    resulting ``quality_status`` travels into the manifest so a run on known-bad data cannot
    be mistaken for a clean one.
    """
    dataset = canonical_loader.load(
        adapter,
        path,
        require_quality=require_quality,
        session_timezone=session_timezone,
        **adapter_kwargs,
    )
    manifest = dataset.manifest
    _check_engine_preconditions(
        manifest.instrument, manifest.bar_interval, manifest.data_form, manifest.dataset_id
    )

    return PreparedData(
        frame=dataset.frame,
        instrument=manifest.instrument,
        bar_interval=manifest.bar_interval,
        data_form=manifest.data_form,
        dataset_id=manifest.dataset_id,
        manifest_id=getattr(manifest, "manifest_id", ""),
        bars_fingerprint=dataset.fingerprint,
        quality_status=dataset.report.status.value,
        quality_warnings=tuple(
            finding.line() for finding in dataset.report.findings
            if finding.level.value == "WARN"
        ),
        session_count=dataset.session_count(),
        coverage_start=manifest.coverage_start,
        coverage_end=manifest.coverage_end,
    )


__all__ = ["DataNotUsable", "PreparedData", "prepare"]
