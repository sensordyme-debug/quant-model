"""The canonical entry point. One way in, and it separates FEATURE data from EXECUTION data.

THE SEPARATION, AND WHY IT IS THE POINT OF THE WHOLE LAYER
------------------------------------------------------------
An adjusted continuous series is a legitimate thing to compute features on. Returns are
continuous across the roll, so a momentum measure or a volatility estimate reads sensibly.

It is NOT a legitimate thing to fill orders at. A back-adjusted price of 5,043.17 is a number
no venue ever quoted; a stop resting there could not have existed, and a fill reported at it
is a fill at a fiction. The distortion is not small and it is not uniform - see
`docs/ROLL_ADJUSTMENT_FORENSICS.md`, where the same rule produces different stop distances,
different R multiples and different P&L depending only on which adjustment was applied.

So `ResearchInputs` carries both, states whether they are the same series, and refuses an
execution source whose `data_form` is not execution-valid. A run that wants features from an
adjusted series and fills from the unadjusted one says so, and the report says so too.

NOTHING GETS A DEFAULT
----------------------
No default data form, no default timezone, no default session window, no default adapter. The
15:45 session default was removed for exactly this reason and the same doctrine applies here:
an assumption nobody had to type is an assumption nobody checked.
"""
from __future__ import annotations

import inspect
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from quant_brain.data import adapters as _adapters
from quant_brain.data import quality as _quality
from quant_brain.data.manifest import DatasetManifest, ManifestError, QualitySummary
from quant_brain.data.schema import frame_fingerprint, validate_frame


class LoaderError(ValueError):
    """A load that would require guessing. Always raised, never warned around."""


@dataclass
class ResearchDataset:
    """A validated canonical frame, its manifest, and the quality report it passed under."""

    frame: pd.DataFrame
    manifest: DatasetManifest
    report: _quality.QualityReport

    @property
    def fingerprint(self) -> str:
        """A hash of the BARS, distinct from the manifest id and the source hash.

        Three different questions, three different hashes: the source hash says the file is
        the same, the manifest id says the interpretation is the same, and this says the
        rows that actually reached research are the same. A filter or an adjustment between
        the file and the frame moves only this one.
        """
        return frame_fingerprint(self.frame)

    @property
    def execution_valid(self) -> bool:
        return self.manifest.execution_valid

    def sessions(self) -> Iterator[tuple[object, pd.DataFrame]]:
        """Iterate session by session without materialising a list of every session.

        `futures_discover.session_frames` builds a list of ~326 frames and holds them all.
        That is fine at 447,600 bars and is not fine at ten years of minutes, so the
        canonical path streams. A caller who genuinely needs them all can still `list()` it
        and pay the memory deliberately.
        """
        yield from self.frame.groupby("session_date", sort=True)

    def session_count(self) -> int:
        return int(self.frame["session_date"].nunique())

    def between(self, start=None, end=None) -> ResearchDataset:
        """A time-sliced copy. The manifest's coverage is updated; its id is NOT.

        The id stays fixed on purpose: slicing does not change what the series IS. The
        fingerprint moves, which is the hash that answers "did the bars change".
        """
        import dataclasses
        f = self.frame
        if start is not None:
            f = f[f["timestamp"] >= pd.Timestamp(start, tz="UTC")]
        if end is not None:
            f = f[f["timestamp"] <= pd.Timestamp(end, tz="UTC")]
        f = f.reset_index(drop=True)
        if f.empty:
            raise LoaderError(f"{self.manifest.dataset_id}: no bars in [{start}, {end}]")
        man = dataclasses.replace(
            self.manifest, coverage_start=str(f["timestamp"].iloc[0]),
            coverage_end=str(f["timestamp"].iloc[-1]), bars=len(f),
            sessions=int(f["session_date"].nunique()))
        return ResearchDataset(frame=f, manifest=man, report=self.report)

    def summary(self) -> str:
        return f"{self.manifest.summary()} | frame {self.fingerprint}"


def load(adapter: str, path: Path | str, *, require_quality: bool = True,
         session_timezone: str | None = None, **adapter_kwargs) -> ResearchDataset:
    """Read a source through a named adapter, gate it, and return a research dataset.

    `require_quality=False` still RUNS the gate and still attaches the report - it only
    declines to raise on FAIL. It exists so the adversarial tests can inspect a broken
    dataset, and every caller that uses it is expected to be one of them.

    `session_timezone` names the venue clock the QUALITY GATE reads sessions on. Some
    adapters need the same value to build the frame - `generic_table` requires it - and
    because this function declares a parameter of that name, Python binds the caller's
    keyword here and it never reaches `**adapter_kwargs`. The result was that
    `generic_table` could not be invoked through this function AT ALL: every call site in
    the repository reached past the loader and called the adapter directly, so the
    "source-agnostic" property of this layer had never actually been exercised end to end.
    It is forwarded below when, and only when, the adapter declares a parameter of that
    name - so no existing call changes behaviour. Found by
    `tests/test_vwap_data.py::test_the_same_session_loads_from_a_completely_different_source_shape`.
    """
    if adapter not in _adapters.ADAPTERS:
        raise LoaderError(
            f"unknown adapter {adapter!r}. Available: {_adapters.available()}. A provider "
            f"with no adapter is not loaded by guessing at its columns; write one.")

    read = _adapters.ADAPTERS[adapter]
    if session_timezone is not None \
            and "session_timezone" in inspect.signature(read).parameters:
        adapter_kwargs.setdefault("session_timezone", session_timezone)
    frame, manifest = read(Path(path), **adapter_kwargs)
    validate_frame(frame, name=manifest.dataset_id)

    tz = session_timezone or manifest.session_timezone
    if not tz:
        raise LoaderError(
            f"{manifest.dataset_id}: no session timezone. A session boundary with no clock "
            f"is the defect docs/DATA_FLOW_FORENSICS.md records as FINDING 1.")

    report = _quality.check(frame, dataset_id=manifest.dataset_id, session_timezone=tz)
    manifest = manifest.with_quality(QualitySummary(
        status=report.status.value, checks_run=len(report.findings),
        warn_reasons=tuple(f.check for f in report.of(_quality.Level.WARN)),
        fail_reasons=tuple(f.check for f in report.of(_quality.Level.FAIL)),
        report_hash=report.report_hash))

    if require_quality and report.failed:
        lines = "\n".join("  " + f.line() for f in report.of(_quality.Level.FAIL))
        raise _quality.DataQualityError(
            f"{manifest.dataset_id}: FAIL - this dataset must not enter research.\n{lines}")
    return ResearchDataset(frame=frame, manifest=manifest, report=report)


# ======================================================================================
# FEATURE vs EXECUTION
# ======================================================================================

@dataclass
class ResearchInputs:
    """The pair of series a run uses, with the difference between them made explicit.

    A backtest that reports one number and used two series without saying so is not
    reproducible by anyone who was not in the room. `describe()` is what goes in the report.
    """

    features: ResearchDataset
    execution: ResearchDataset
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        try:
            self.execution.manifest.refuse_if_not_execution_valid()
        except ManifestError as exc:
            raise LoaderError(str(exc)) from exc
        if self.features.manifest.instrument != self.execution.manifest.instrument:
            raise LoaderError(
                f"features are {self.features.manifest.instrument} and execution is "
                f"{self.execution.manifest.instrument}. Trading one instrument on another's "
                f"signal may be a real strategy, but it is not something this loader will "
                f"assemble by accident - build it deliberately from two named inputs.")
        if self.features.manifest.bar_interval != self.execution.manifest.bar_interval:
            raise LoaderError(
                f"bar intervals differ: features {self.features.manifest.bar_interval}, "
                f"execution {self.execution.manifest.bar_interval}")

    @property
    def identical(self) -> bool:
        """True when the same bars serve both purposes - the common and simplest case."""
        return (self.features.manifest.manifest_id == self.execution.manifest.manifest_id
                and self.features.fingerprint == self.execution.fingerprint)

    def describe(self) -> str:
        if self.identical:
            return (f"FEATURE DATA and EXECUTION DATA are the SAME series: "
                    f"{self.features.manifest.dataset_id} "
                    f"[{self.features.manifest.data_form.value}] "
                    f"manifest {self.features.manifest.manifest_id} "
                    f"frame {self.features.fingerprint}")
        return (
            "FEATURE DATA and EXECUTION DATA DIFFER.\n"
            f"  FEATURE   {self.features.manifest.dataset_id} "
            f"[{self.features.manifest.data_form.value}] "
            f"manifest {self.features.manifest.manifest_id} "
            f"frame {self.features.fingerprint}\n"
            f"  EXECUTION {self.execution.manifest.dataset_id} "
            f"[{self.execution.manifest.data_form.value}] "
            f"manifest {self.execution.manifest.manifest_id} "
            f"frame {self.execution.fingerprint}\n"
            "  Signals were computed on one price series and fills simulated on another. "
            "Every entry price, stop distance, target and R multiple in the result comes "
            "from the EXECUTION series.")

    def provenance(self) -> dict:
        """The block a result embeds. Two runs on different representations cannot match."""
        return {
            "features_identical_to_execution": self.identical,
            "feature_data": {
                "dataset_id": self.features.manifest.dataset_id,
                "manifest_id": self.features.manifest.manifest_id,
                "frame_fingerprint": self.features.fingerprint,
                "data_form": self.features.manifest.data_form.value,
                "roll_method": self.features.manifest.roll.method.value,
                "adjustment_method": self.features.manifest.roll.adjustment.value,
                "provider": self.features.manifest.provider,
                "source_hashes": list(self.features.manifest.source_hashes),
                "quality_status": self.features.manifest.quality.status,
                "quality_report_hash": self.features.manifest.quality.report_hash,
                "coverage": [self.features.manifest.coverage_start,
                             self.features.manifest.coverage_end],
                "session_timezone": self.features.manifest.session_timezone,
                "bar_interval": self.features.manifest.bar_interval,
                "schema_version": self.features.manifest.schema_version,
            },
            "execution_data": {
                "dataset_id": self.execution.manifest.dataset_id,
                "manifest_id": self.execution.manifest.manifest_id,
                "frame_fingerprint": self.execution.fingerprint,
                "data_form": self.execution.manifest.data_form.value,
                "roll_method": self.execution.manifest.roll.method.value,
                "adjustment_method": self.execution.manifest.roll.adjustment.value,
                "provider": self.execution.manifest.provider,
                "source_hashes": list(self.execution.manifest.source_hashes),
                "quality_status": self.execution.manifest.quality.status,
                "quality_report_hash": self.execution.manifest.quality.report_hash,
                "execution_valid": self.execution.manifest.execution_valid,
            },
            "notes": list(self.notes),
        }


def same_for_both(ds: ResearchDataset) -> ResearchInputs:
    """The ordinary case: one series does both jobs. Still refuses a non-execution form."""
    return ResearchInputs(features=ds, execution=ds,
                          notes=["one series serves both purposes"])


__all__ = ["LoaderError", "ResearchDataset", "ResearchInputs", "load", "same_for_both"]
