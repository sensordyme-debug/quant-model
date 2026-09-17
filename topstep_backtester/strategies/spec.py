"""Frozen strategy specifications: what was tested, fixed before it was tested.

WHAT A FROZEN SPEC IS FOR
-------------------------
It makes one specific lie impossible: changing the strategy after seeing the results and
reporting the new version against the old evidence. A spec carries a content hash over its
rules and parameters. Move a threshold and the hash moves, so a result that names a hash no
longer matching any spec in the tree is detectably stale, and a spec that quietly grew a
parameter cannot pass itself off as the one that was tested.

WHAT IS AND IS NOT IN THE HASH
------------------------------
The hash covers the SEMANTIC content - the rules, every parameter, the instrument, the
timeframe, the session window. It deliberately excludes provenance: who froze it, when, and
the free-text hypothesis and notes.

That split is the useful one. Two specs with the same hash are the same experiment even if
one was frozen a month later under a different author, which is exactly what you want when
asking "have we already tested this". Including the timestamp would make every re-freeze
look like a new strategy and make the hash worthless for that question. The excluded fields
are still recorded, still reported, and still committed - they just do not define identity.
The Phase E manifest bug was the same mistake in the other direction: a path in the identity
hash made the same dataset hash differently on two machines.

THE AMBIGUITY REGISTER
----------------------
A written rule almost always admits more than one reading, and the readings differ in P&L.
A spec that does not say which reading it took has not been frozen, it has merely been
written down. Each ambiguity records the question, the reading taken, the authority for it,
and whether it is material. ``unresolved()`` must be empty before a spec may run - the test
suite asserts it, and ``freeze()`` refuses otherwise.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

#: Bumped when the meaning of a spec field changes.
SPEC_SCHEMA_VERSION = "1.0.0"


class SpecError(ValueError):
    """A specification that is not fit to be tested against."""


@dataclass(frozen=True)
class Ambiguity:
    """One place the written rules admitted more than one reading."""

    ref: str
    question: str
    reading_taken: str
    authority: str
    material: bool
    resolved: bool = True

    def as_dict(self) -> dict[str, object]:
        return {
            "ref": self.ref,
            "question": self.question,
            "reading_taken": self.reading_taken,
            "authority": self.authority,
            "material": self.material,
            "resolved": self.resolved,
        }


def _canonical(value: Any) -> Any:
    """Reduce a value to something JSON can serialise deterministically."""
    if isinstance(value, Mapping):
        return {str(k): _canonical(value[k]) for k in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, float):
        #: repr, not str: the shortest round-tripping form, so 0.1 hashes as "0.1" on every
        #: platform rather than as a 17-digit expansion that differs between them.
        return repr(value)
    return str(value)


@dataclass(frozen=True)
class FrozenStrategySpec:
    """An immutable, content-addressed description of one strategy.

    Construct it, then call :meth:`freeze`. An unfrozen spec has no hash and may not be run.
    """

    name: str
    version: str
    instrument: str
    bar_interval: str
    #: Prose, one rule per entry. These are hashed: reword a rule and the identity changes,
    #: which is correct - the rules ARE the strategy.
    entry_rules: tuple[str, ...]
    exit_rules: tuple[str, ...]
    risk_rules: tuple[str, ...]
    #: Every number the strategy uses. Hashed. Nothing here may be searched over.
    parameters: Mapping[str, Any]
    #: Venue-clock window the strategy is allowed to act in, as "HH:MM-HH:MM ET".
    session_window: str
    ambiguities: tuple[Ambiguity, ...] = ()

    #: GENEALOGY. The spec_hash of the version this one was derived from, empty for an
    #: original. Hashed, deliberately: a strategy that is "v2 of the one that lost" is a
    #: different experiment from one invented independently, and the difference is exactly
    #: what multiple-testing corrections need to know. Recording the parent also makes a
    #: family of near-identical variants visible as a family rather than as N fresh ideas.
    derived_from: str = ""
    #: Why it was derived. Free text, but required whenever derived_from is set - a lineage
    #: with no stated reason is the shape a quiet re-tune takes.
    derivation_reason: str = ""

    # ---- provenance: recorded, reported, NOT hashed -------------------------------------
    hypothesis: str = ""
    author: str = ""
    frozen_at: str = ""
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))
        if not self.name or not self.version:
            raise SpecError("a spec needs a name and a version")
        if not self.entry_rules:
            raise SpecError(
                f"{self.name}: no entry rules. A strategy that cannot say when it enters "
                f"cannot be frozen, and cannot be falsified either."
            )
        if not self.exit_rules:
            raise SpecError(
                f"{self.name}: no exit rules. An entry with no stated exit is not a "
                f"strategy; the exit is where the P&L actually comes from."
            )
        if self.derived_from and not self.derivation_reason:
            raise SpecError(
                f"{self.name}: derived_from={self.derived_from} with no derivation_reason. "
                f"A variant that cannot say why it differs from its parent is a re-tune "
                f"wearing a new name, and the whole point of tracking genealogy is that a "
                f"family of variants is countable."
            )
        if self.derivation_reason and not self.derived_from:
            raise SpecError(
                f"{self.name}: derivation_reason given with no derived_from. Name the "
                f"parent spec hash."
            )

    # ---- identity -----------------------------------------------------------------------

    def semantic_content(self) -> dict[str, Any]:
        """Exactly what the hash covers. Public so a reader can check it themselves."""
        return {
            "schema_version": SPEC_SCHEMA_VERSION,
            "name": self.name,
            "version": self.version,
            "instrument": self.instrument,
            "bar_interval": self.bar_interval,
            "session_window": self.session_window,
            "entry_rules": list(self.entry_rules),
            "exit_rules": list(self.exit_rules),
            "risk_rules": list(self.risk_rules),
            "parameters": _canonical(self.parameters),
            "derived_from": self.derived_from,
            "ambiguities": [
                {"ref": a.ref, "reading_taken": a.reading_taken, "material": a.material}
                for a in sorted(self.ambiguities, key=lambda a: a.ref)
            ],
        }

    @property
    def spec_hash(self) -> str:
        blob = json.dumps(self.semantic_content(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

    @property
    def spec_id(self) -> str:
        return f"{self.name}/{self.version}@{self.spec_hash}"

    # ---- the ambiguity register ----------------------------------------------------------

    def unresolved(self) -> tuple[Ambiguity, ...]:
        return tuple(a for a in self.ambiguities if not a.resolved)

    def material_ambiguities(self) -> tuple[Ambiguity, ...]:
        return tuple(a for a in self.ambiguities if a.material)

    # ---- the gate -------------------------------------------------------------------------

    def freeze(self, *, author: str, at: dt.datetime | None = None) -> FrozenStrategySpec:
        """Stamp provenance and assert the spec is fit to run. Returns a new spec.

        The hash is unchanged by freezing - provenance is outside it - so freezing an
        already-frozen spec is idempotent in identity, which is what lets a spec be
        re-stamped without looking like a different experiment.
        """
        outstanding = self.unresolved()
        if outstanding:
            raise SpecError(
                f"{self.name}: {len(outstanding)} unresolved ambiguit"
                f"{'y' if len(outstanding) == 1 else 'ies'} "
                f"({', '.join(a.ref for a in outstanding)}). Every reading must be decided, "
                f"with its authority named, BEFORE the strategy meets data - deciding "
                f"afterwards is choosing the reading that won."
            )
        stamped = at or dt.datetime.now(dt.UTC)
        return FrozenStrategySpec(
            name=self.name,
            version=self.version,
            instrument=self.instrument,
            bar_interval=self.bar_interval,
            entry_rules=self.entry_rules,
            exit_rules=self.exit_rules,
            risk_rules=self.risk_rules,
            parameters=dict(self.parameters),
            session_window=self.session_window,
            ambiguities=self.ambiguities,
            derived_from=self.derived_from,
            derivation_reason=self.derivation_reason,
            hypothesis=self.hypothesis,
            author=author,
            frozen_at=stamped.isoformat(),
            notes=self.notes,
        )

    @property
    def generation(self) -> int:
        """0 for an original. Only ever 1 here - the full chain needs the registry."""
        return 1 if self.derived_from else 0

    @property
    def is_frozen(self) -> bool:
        return bool(self.frozen_at and self.author)

    def assert_runnable(self) -> None:
        if not self.is_frozen:
            raise SpecError(
                f"{self.name}: not frozen. Call freeze(author=...) before running it, so the "
                f"record says the rules were fixed before the result existed."
            )
        if self.unresolved():  # pragma: no cover - freeze() already refuses
            raise SpecError(f"{self.name}: unresolved ambiguities remain")

    def as_dict(self) -> dict[str, object]:
        return {
            **self.semantic_content(),
            "spec_hash": self.spec_hash,
            "spec_id": self.spec_id,
            "derivation_reason": self.derivation_reason,
            "hypothesis": self.hypothesis,
            "author": self.author,
            "frozen_at": self.frozen_at,
            "notes": list(self.notes),
            "ambiguity_register": [a.as_dict() for a in self.ambiguities],
        }


__all__ = [
    "SPEC_SCHEMA_VERSION",
    "Ambiguity",
    "FrozenStrategySpec",
    "SpecError",
]
