"""The dataset manifest: what a dataset IS, declared, hashed, and travelling with results.

WHY A MANIFEST AND NOT A DOCSTRING
------------------------------------
The roll rule for this repository's futures store was, until this module existed, the integer
`ROLL_DAYS = 8` inside the script that fetched it. Re-fetch with a 5 and every downstream
result changes, with no signal anywhere - not in the parquet, not in the backtest output, not
in the git history of the results. A reader six months later cannot tell which store a number
came from.

A manifest fixes that by being a *required input* rather than documentation. The loader will
not produce a canonical frame without one, the manifest will not construct without a declared
`DataForm`, and its identifier is a hash of its own contents - so two datasets that differ in
representation cannot collide in a provenance record even if they came from the same bytes.

WHAT IS HASHED, AND WHY THERE ARE TWO HASHES
----------------------------------------------
    source_hashes    sha256 of each source FILE, as bytes on disk. Answers "is this the
                     same file I ran on before".
    manifest_id      sha256 over the declared metadata. Answers "is this the same
                     INTERPRETATION of that file". A back-adjusted and an unadjusted reading
                     of one parquet share a source hash and must never share an id.

The frame fingerprint - "did the bars that actually reached research change" - is a third
question and lives in `schema.frame_fingerprint`, because an adapter, a filter or an
adjustment can sit between the file and the bars.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from quant_brain.data.schema import SCHEMA_VERSION, AdjustmentMethod, DataForm, RollMethod

#: Bumped when the manifest's own field set changes, so an old manifest is identifiable
#: rather than silently reinterpreted under new semantics.
MANIFEST_VERSION = "1.0.0"


class ManifestError(ValueError):
    """A dataset that has not declared enough about itself to be used. Never defaulted."""


@dataclass(frozen=True)
class RollSpec:
    """How a continuous series was assembled. Required whenever the form is continuous.

    `reconstructible` is not a boast. It is the honest answer to "could someone rebuild this
    series from the raw contracts", and it is False whenever the method is PROVIDER_DEFINED
    or UNKNOWN, or whenever the trigger needs data the store does not hold - an
    open-interest crossover cannot be reproduced from a store with no open interest, and
    this repository's store has none.
    """

    method: RollMethod
    adjustment: AdjustmentMethod
    #: For CALENDAR_DAYS_BEFORE_EXPIRY. None for every other method.
    days_before_expiry: int | None = None
    #: The contracts that were spliced, in chronological order.
    contracts: tuple[str, ...] = ()
    #: The instants the series changed contract, as ISO strings. Measured from the data
    #: where possible rather than recomputed from the rule, so a rule/data disagreement is
    #: visible instead of assumed away.
    roll_timestamps: tuple[str, ...] = ()
    #: What happens to volume across a roll. "carried" = each contract's own volume, which
    #: is the only honest answer for a splice; "summed" would invent liquidity.
    volume_handling: str = "carried"
    open_interest_handling: str = "absent"
    reconstructible: bool = False
    non_reconstructible_reason: str = ""

    def __post_init__(self) -> None:
        if self.method is RollMethod.CALENDAR_DAYS_BEFORE_EXPIRY \
                and self.days_before_expiry is None:
            raise ManifestError(
                "RollMethod.CALENDAR_DAYS_BEFORE_EXPIRY needs `days_before_expiry`. The "
                "rule without its parameter is not a rule.")
        if self.days_before_expiry is not None \
                and self.method is not RollMethod.CALENDAR_DAYS_BEFORE_EXPIRY:
            raise ManifestError(
                f"`days_before_expiry` is meaningless for {self.method.value}")
        if not self.reconstructible and not self.non_reconstructible_reason:
            raise ManifestError(
                "a roll marked NON_RECONSTRUCTIBLE must say why. 'Cannot be rebuilt' with "
                "no reason is indistinguishable from 'nobody checked'.")
        if self.reconstructible and not self.method.reconstructible:
            raise ManifestError(
                f"{self.method.value} cannot be reconstructible: the method itself does not "
                f"define the roll well enough to rebuild it.")

    @classmethod
    def none(cls) -> RollSpec:
        """For a RAW single-contract dataset, or anything that is not a futures series."""
        return cls(method=RollMethod.NONE, adjustment=AdjustmentMethod.NONE,
                   reconstructible=True)


@dataclass(frozen=True)
class QualitySummary:
    """The gate's verdict, frozen onto the manifest so a result carries the report it ran
    under rather than whatever the gate says today."""

    status: str = "NOT_RUN"          # PASS | WARN | FAIL | NOT_RUN
    checks_run: int = 0
    warn_reasons: tuple[str, ...] = ()
    fail_reasons: tuple[str, ...] = ()
    report_hash: str = ""


@dataclass(frozen=True)
class DatasetManifest:
    """Everything a result needs to say about the data it ran on.

    Constructed by an adapter, never by research code. Frozen, because a manifest that can
    be edited after a run is not provenance.
    """

    # -- identity ----------------------------------------------------------------------
    dataset_id: str
    provider: str
    instrument: str
    contract_family: str

    # -- representation. NO DEFAULTS. --------------------------------------------------
    data_form: DataForm
    roll: RollSpec

    # -- shape -------------------------------------------------------------------------
    bar_interval: str
    timezone: str                     # the tz the CANONICAL frame stores (always UTC)
    session_timezone: str             # the venue clock sessions are defined in
    coverage_start: str
    coverage_end: str
    bars: int
    sessions: int

    # -- provenance --------------------------------------------------------------------
    source_files: tuple[str, ...] = ()
    source_hashes: tuple[str, ...] = ()
    schema_version: str = SCHEMA_VERSION
    manifest_version: str = MANIFEST_VERSION
    canonicalized_at: str = ""
    adapter: str = ""
    adapter_params: dict = field(default_factory=dict)

    # -- what it may be used for -------------------------------------------------------
    data_form_description: str = ""
    quality: QualitySummary = field(default_factory=QualitySummary)
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.data_form, DataForm):
            raise ManifestError(
                f"data_form must be a DataForm, got {self.data_form!r}. There is no default "
                f"and no inference from the filename: state what the series is.")
        if self.data_form is DataForm.OTHER and not self.data_form_description.strip():
            raise ManifestError(
                "DataForm.OTHER requires `data_form_description`. 'Other' with no "
                "description is a dataset nobody can reason about.")
        if self.data_form is DataForm.RAW and self.roll.method is not RollMethod.NONE:
            raise ManifestError(
                f"a RAW dataset is one contract and cannot have roll method "
                f"{self.roll.method.value}")
        if self.data_form.is_continuous and self.roll.method is RollMethod.NONE:
            raise ManifestError(
                f"{self.data_form.value} is a spliced series, so it HAS a roll. "
                f"RollMethod.NONE contradicts it; use UNKNOWN if the method is genuinely "
                f"not known - that is a different and more honest statement.")
        if self.data_form.is_adjusted and self.roll.adjustment is AdjustmentMethod.NONE:
            raise ManifestError(
                f"{self.data_form.value} says the prices were adjusted and "
                f"AdjustmentMethod.NONE says they were not. One of the two is wrong.")
        if not self.data_form.is_adjusted \
                and self.roll.adjustment in (AdjustmentMethod.RATIO,
                                             AdjustmentMethod.DIFFERENCE):
            raise ManifestError(
                f"{self.data_form.value} is an UNadjusted form but the roll declares a "
                f"{self.roll.adjustment.value} adjustment.")
        if self.timezone != "UTC":
            raise ManifestError(
                f"canonical storage is UTC; this manifest says {self.timezone!r}. The venue "
                f"clock belongs in `session_timezone`.")
        if not self.session_timezone:
            raise ManifestError(
                "`session_timezone` is required. A session boundary without a clock is the "
                "defect docs/DATA_FLOW_FORENSICS.md records as FINDING 1: a roll boundary "
                "fixed in UTC lands at 18:00 ET in summer and 16:00 ET in winter.")

    # -- identity ------------------------------------------------------------------------

    @property
    def manifest_id(self) -> str:
        """A hash over the DECLARED representation, not over the bytes.

        Deliberately excludes `quality` and `canonicalized_at`: re-running the gate or
        re-canonicalising the same file at a different time is the same dataset, whereas
        reading the same file as back-adjusted instead of unadjusted is not.
        """
        payload = {
            "provider": self.provider, "instrument": self.instrument,
            "contract_family": self.contract_family,
            "data_form": self.data_form.value,
            "data_form_description": self.data_form_description,
            "roll": {"method": self.roll.method.value,
                     "adjustment": self.roll.adjustment.value,
                     "days_before_expiry": self.roll.days_before_expiry,
                     "contracts": list(self.roll.contracts),
                     "roll_timestamps": list(self.roll.roll_timestamps),
                     "volume_handling": self.roll.volume_handling,
                     "open_interest_handling": self.roll.open_interest_handling,
                     "reconstructible": self.roll.reconstructible},
            "bar_interval": self.bar_interval, "timezone": self.timezone,
            "session_timezone": self.session_timezone,
            "coverage": [self.coverage_start, self.coverage_end],
            "bars": self.bars, "sessions": self.sessions,
            "source_hashes": list(self.source_hashes),
            "schema_version": self.schema_version,
            "manifest_version": self.manifest_version,
            "adapter": self.adapter, "adapter_params": self.adapter_params,
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    @property
    def execution_valid(self) -> bool:
        """May the execution simulator fill orders at these prices? See `DataForm`."""
        return self.data_form.execution_valid

    def refuse_if_not_execution_valid(self) -> None:
        if self.execution_valid:
            return
        raise ManifestError(
            f"{self.dataset_id}: {self.data_form.value} prices were never quoted by any "
            f"venue, so a fill simulated at one is a fill at a number that did not exist. "
            f"This series may be used as FEATURE data; it may not be the EXECUTION source. "
            f"Supply an execution dataset whose data_form is RAW or "
            f"CONTINUOUS_UNADJUSTED, or state explicitly that features and execution "
            f"differ. See docs/DATA_FLOW_FORENSICS.md and the loader's `ResearchDataset`.")

    # -- serialisation ---------------------------------------------------------------------

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["data_form"] = self.data_form.value
        d["roll"]["method"] = self.roll.method.value
        d["roll"]["adjustment"] = self.roll.adjustment.value
        d["manifest_id"] = self.manifest_id
        d["execution_valid"] = self.execution_valid
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=1, sort_keys=True, default=str)

    def write(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
        return path

    @classmethod
    def from_dict(cls, d: dict) -> DatasetManifest:
        d = dict(d)
        d.pop("manifest_id", None)
        d.pop("execution_valid", None)
        r = dict(d.pop("roll"))
        r["method"] = RollMethod(r["method"])
        r["adjustment"] = AdjustmentMethod(r["adjustment"])
        for key in ("contracts", "roll_timestamps"):
            r[key] = tuple(r.get(key) or ())
        q = d.pop("quality", None) or {}
        q = QualitySummary(status=q.get("status", "NOT_RUN"),
                           checks_run=int(q.get("checks_run", 0)),
                           warn_reasons=tuple(q.get("warn_reasons") or ()),
                           fail_reasons=tuple(q.get("fail_reasons") or ()),
                           report_hash=q.get("report_hash", ""))
        for key in ("source_files", "source_hashes", "notes"):
            d[key] = tuple(d.get(key) or ())
        d["data_form"] = DataForm(d["data_form"])
        return cls(roll=RollSpec(**r), quality=q, **d)

    @classmethod
    def read(cls, path: Path) -> DatasetManifest:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def with_quality(self, q: QualitySummary) -> DatasetManifest:
        """A copy carrying the gate's verdict. The manifest id is unchanged by design."""
        return dataclasses.replace(self, quality=q)

    def summary(self) -> str:
        adj = self.roll.adjustment.value
        rec = "reconstructible" if self.roll.reconstructible else "NON_RECONSTRUCTIBLE"
        return (f"{self.dataset_id} [{self.manifest_id}] {self.provider} {self.instrument} "
                f"{self.bar_interval} | {self.data_form.value} | roll "
                f"{self.roll.method.value} adj {adj} ({rec}) | "
                f"{self.coverage_start[:10]}..{self.coverage_end[:10]} | "
                f"{self.bars:,} bars, {self.sessions} sessions | quality "
                f"{self.quality.status} | execution "
                f"{'VALID' if self.execution_valid else 'REFUSED'}")


def hash_file(path: Path, *, chunk: int = 1 << 20) -> str:
    """sha256 of a file's bytes, streamed. Never loads the whole file to hash it."""
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def utc_now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


__all__ = ["MANIFEST_VERSION", "DatasetManifest", "ManifestError", "QualitySummary",
           "RollSpec", "hash_file", "utc_now_iso"]
