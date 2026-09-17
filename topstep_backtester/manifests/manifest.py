"""What produced a number, by content hash, so the claim can be checked instead of trusted.

THE IDENTITY RULE, LEARNED THE HARD WAY
---------------------------------------
A hash that is supposed to mean "the same inputs" must not move when something irrelevant
moves. An earlier dataset manifest in this repository included the source FILE PATHS in its
identity hash, so the same data checked out at a different path hashed differently and two
machines could never agree they had run the same thing.

So ``run_id`` covers inputs and assumptions only: the bars, the frozen spec, the account and
execution profiles, and the upstream API shape. Paths, wall-clock times, hostnames and the
operator's name are recorded as provenance beside it and excluded from it. Two runs with the
same ``run_id`` should produce identical numbers, and ``validation.integrity`` checks exactly
that.

WHY THE BARS ARE HASHED, NOT THE FILE
-------------------------------------
The bars are hashed after adaptation, in the exact form the engine consumed them. A hash of
the parquet on disk would prove the file had not changed while saying nothing about whether
the adapter turned it into the same bars - which is the half of the path where the
interesting defects live.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import platform
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from topstep_backtester.upstream import Bar, upstream_provenance

MANIFEST_SCHEMA_VERSION = "1.0.0"

#: Layer B source that materially affects a number. Hashed into ``code_hash`` so a silent
#: edit to the adapter cannot leave an old result looking current.
_HASHED_SOURCE = (
    "upstream.py",
    "safety.py",
    "adapters/bars.py",
    "adapters/contracts.py",
    "profiles/account.py",
    "profiles/execution.py",
    "strategies/spec.py",
    "strategies/base.py",
    "reference/arithmetic.py",
    "run.py",
)


def hash_bars(bars: Sequence[Bar]) -> str:
    """A digest of the bars exactly as the engine received them."""
    digest = hashlib.sha256()
    for bar in bars:
        digest.update(
            f"{bar.bar_type.contract_id}|{int(bar.bar_type.unit)}|{bar.bar_type.unit_number}"
            f"|{bar.ts_event}|{bar.ts_init}|{bar.open}|{bar.high}|{bar.low}|{bar.close}"
            f"|{bar.volume}\n".encode()
        )
    return digest.hexdigest()[:16]


def hash_layer_b_source(root: Path | None = None) -> str:
    """A digest of the Layer B modules that can change a result."""
    base = root or Path(__file__).resolve().parent.parent
    digest = hashlib.sha256()
    for relative in _HASHED_SOURCE:
        path = base / relative
        #: A missing file is hashed as absent rather than skipped: deleting a module is a
        #: change to the pipeline and must move the hash.
        payload = path.read_bytes() if path.exists() else b"<absent>"
        digest.update(relative.encode())
        digest.update(hashlib.sha256(payload).digest())
    return digest.hexdigest()[:16]


@dataclass(frozen=True)
class RunManifest:
    """Inputs and assumptions (hashed) plus provenance (recorded, not hashed)."""

    # ---- hashed into run_id --------------------------------------------------------------
    bars_hash: str
    bar_count: int
    instrument: str
    bar_interval: str
    first_ts_event_utc: str
    last_ts_init_utc: str
    data_form: str
    contract_ids: tuple[str, ...]
    spec_id: str
    spec_hash: str
    account_profile: dict[str, Any]
    execution_profile: dict[str, Any]
    upstream_api_fingerprint: str
    upstream_version: str
    code_hash: str

    # ---- provenance: recorded, NOT hashed ------------------------------------------------
    created_at: str = ""
    operator: str = ""
    python: str = ""
    platform_name: str = ""
    dataset_manifest_id: str = ""
    notes: tuple[str, ...] = field(default_factory=tuple)

    def identity(self) -> dict[str, Any]:
        """Exactly the fields ``run_id`` is computed from."""
        return {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "bars_hash": self.bars_hash,
            "bar_count": self.bar_count,
            "instrument": self.instrument,
            "bar_interval": self.bar_interval,
            "first_ts_event_utc": self.first_ts_event_utc,
            "last_ts_init_utc": self.last_ts_init_utc,
            "data_form": self.data_form,
            "contract_ids": list(self.contract_ids),
            "spec_hash": self.spec_hash,
            "account_profile": self.account_profile,
            "execution_profile": self.execution_profile,
            "upstream_api_fingerprint": self.upstream_api_fingerprint,
            "upstream_version": self.upstream_version,
            "code_hash": self.code_hash,
        }

    @property
    def run_id(self) -> str:
        blob = json.dumps(self.identity(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "identity": self.identity(),
            "provenance": {
                "created_at": self.created_at,
                "operator": self.operator,
                "python": self.python,
                "platform": self.platform_name,
                "dataset_manifest_id": self.dataset_manifest_id,
                "notes": list(self.notes),
            },
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.as_dict(), indent=indent, sort_keys=False)


def build_manifest(
    *,
    bars: Sequence[Bar],
    bar_report: Any,
    spec: Any,
    account_profile: Any,
    execution_profile: Any,
    operator: str = "",
    dataset_manifest_id: str = "",
    notes: Sequence[str] = (),
) -> RunManifest:
    """Assemble the manifest from the objects a run already has in hand."""
    provenance = upstream_provenance()
    return RunManifest(
        bars_hash=hash_bars(bars),
        bar_count=len(bars),
        instrument=bar_report.instrument,
        bar_interval=bar_report.bar_interval,
        first_ts_event_utc=bar_report.first_ts_event_utc,
        last_ts_init_utc=bar_report.last_ts_init_utc,
        data_form=bar_report.data_form,
        contract_ids=tuple(bar_report.contract_ids),
        spec_id=spec.spec_id,
        spec_hash=spec.spec_hash,
        account_profile=account_profile.as_dict(),
        execution_profile=execution_profile.as_dict(),
        upstream_api_fingerprint=provenance["api_fingerprint"],
        upstream_version=provenance["installed_version"],
        code_hash=hash_layer_b_source(),
        created_at=dt.datetime.now(dt.UTC).isoformat(),
        operator=operator,
        python=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        platform_name=platform.platform(),
        dataset_manifest_id=dataset_manifest_id,
        notes=tuple(notes),
    )


__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "RunManifest",
    "build_manifest",
    "hash_bars",
    "hash_layer_b_source",
]
