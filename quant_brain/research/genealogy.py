"""Hypothesis preregistration and lineage: what we believed, when, and what changed our mind.

WHY THIS EXISTS
---------------
`registry.Ledger` already records experiments and applies a multiplicity correction over a
family. That is necessary and it is not sufficient, because it cannot see the shape of a
research programme over time.

Consider a real sequence from this repository. A tournament tests thirty mechanisms. One
family looks marginally better than the rest. A researcher writes a variant conditioned on
what the first pass showed, tests it, and it looks better still. Each individual experiment is
correctly recorded and correctly corrected. The programme as a whole has nevertheless been
fitted to the data, one honest step at a time, and nothing in a flat ledger can tell you that
happened.

The distinguishing fact is not the count of experiments. It is **whether a hypothesis was
written before or after seeing the result it was designed to explain**. This module records
that, per hypothesis, as a field that cannot be filled in retrospectively without leaving a
trace.

THE FIELD THAT MATTERS
----------------------
`result_driven`. True when this hypothesis exists because of something we saw in our own data.
That is not a sin - it is how research works, and Part 6 of the brief explicitly asks for
second-generation hypotheses from failure analysis. But a result-driven hypothesis tested on
the same data that inspired it is circular, and the only defence is to know which ones they
are and hold them to a different standard: a fresh split, or a wider multiplicity bar, or
both.

`effective_trials()` implements that. A lineage of result-driven descendants counts as more
trials than its members, because each generation was chosen by looking at the last.

WHAT THIS DELIBERATELY DOES NOT DO
----------------------------------
It does not stop anybody. A researcher can preregister anything and run anything. The point is
that the record makes an evolutionary search visible in the shape of the tree, so that a
reader six months later can see whether a survivor was predicted or discovered.
"""
from __future__ import annotations

import datetime as dt
import enum
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_PATH = REPO / "research" / "hypotheses.jsonl"


class Stage(str, enum.Enum):
    """The budget ladder. A hypothesis climbs it one rung at a time and never skips.

    Part 9 of the brief: a defined discovery test, then validation, then robustness, then out
    of sample, then the final holdout. Each rung is more expensive than the last in the only
    currency that matters here, which is how much of the remaining unseen data it spends.
    """

    PROPOSED = "PROPOSED"
    DISCOVERY = "DISCOVERY"
    VALIDATION = "VALIDATION"
    ROBUSTNESS = "ROBUSTNESS"
    OUT_OF_SAMPLE = "OUT_OF_SAMPLE"
    FINAL_HOLDOUT = "FINAL_HOLDOUT"
    REJECTED = "REJECTED"
    #: Refused before any data was spent, by the economic feasibility gate.
    REFUSED_INFEASIBLE = "REFUSED_INFEASIBLE"

    @property
    def rung(self) -> int:
        order = [Stage.PROPOSED, Stage.DISCOVERY, Stage.VALIDATION, Stage.ROBUSTNESS,
                 Stage.OUT_OF_SAMPLE, Stage.FINAL_HOLDOUT]
        return order.index(self) if self in order else -1


@dataclass
class Hypothesis:
    """One preregistered claim, with its ancestry and the reason it exists.

    `prediction` is the load-bearing field and it must be written before the test. "This
    mechanism will make money" is not a prediction; "fading a 95th-percentile opening-range
    extension on the Nasdaq complex will produce a positive mean per session with fewer than
    three round turns per session" is. The difference is whether a result could contradict it.
    """

    id: str
    title: str
    mechanism_id: str
    #: The falsifiable claim, written BEFORE the experiment.
    prediction: str
    #: What outcome would kill it. Written before, too.
    falsified_if: str
    instruments: tuple[str, ...] = ()
    #: Lineage. Empty parent means a first-generation hypothesis from a mechanism.
    parent: str | None = None
    #: Why this differs from its parent. Required when there is a parent.
    modification_reason: str = ""
    #: TRUE when this hypothesis exists because of something seen in OUR data. The single
    #: most important field in the record; see the module docstring.
    result_driven: bool = False
    #: What we had already seen when this was written. Free text, but write it.
    prior_evidence: str = ""
    stage: Stage = Stage.PROPOSED
    preregistered_at: str = ""
    feasibility: dict = field(default_factory=dict)
    results: list[dict] = field(default_factory=list)
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.preregistered_at:
            self.preregistered_at = dt.datetime.now(dt.UTC).isoformat()
        if self.parent and not self.modification_reason:
            raise ValueError(
                f"{self.id}: a hypothesis with a parent must say why it differs. A variant "
                f"with no stated reason is indistinguishable from a parameter sweep.")

    @property
    def fingerprint(self) -> str:
        """Stable over the claim, not over the results. Two hypotheses with the same
        prediction on the same instruments are the same trial however they are named."""
        blob = json.dumps({"m": self.mechanism_id, "p": self.prediction,
                           "i": sorted(self.instruments)}, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]

    def to_json(self) -> dict:
        d = asdict(self)
        d["stage"] = self.stage.value
        d["fingerprint"] = self.fingerprint
        return d


class Registry:
    """An append-only record of hypotheses and their lineage.

    Append-only on purpose. A hypothesis whose prediction can be edited after the result is
    not a preregistration, and the cheapest way to make that true is to never rewrite a line.
    """

    def __init__(self, path: Path | None = None):
        self.path = path or DEFAULT_PATH
        self._items: dict[str, Hypothesis] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                d = json.loads(line)
                d.pop("fingerprint", None)
                d["stage"] = Stage(d.get("stage", "PROPOSED"))
                d["instruments"] = tuple(d.get("instruments") or ())
                self._items[d["id"]] = Hypothesis(**d)

    def __len__(self) -> int:
        return len(self._items)

    def all(self) -> list[Hypothesis]:
        return list(self._items.values())

    def get(self, hid: str) -> Hypothesis | None:
        return self._items.get(hid)

    def preregister(self, h: Hypothesis) -> Hypothesis:
        """Record a hypothesis before it is tested. Refuses a duplicate claim."""
        if h.id in self._items:
            raise ValueError(f"{h.id} is already registered; use `record` to add a result")
        clash = [o for o in self._items.values() if o.fingerprint == h.fingerprint]
        if clash:
            raise ValueError(
                f"{h.id} makes the same claim as {clash[0].id} on the same instruments. "
                f"Re-running it does not make it more true, and counting it twice inflates "
                f"the multiplicity denominator against everything else.")
        if h.parent and h.parent not in self._items:
            raise ValueError(f"{h.id}: parent {h.parent} is not registered")
        self._items[h.id] = h
        self._append(h)
        return h

    def record(self, hid: str, *, stage: Stage, result: dict) -> Hypothesis:
        """Attach a result and move the hypothesis one rung. Refuses to skip a rung."""
        h = self._items[hid]
        if stage.rung >= 0 and h.stage.rung >= 0 and stage.rung > h.stage.rung + 1:
            raise ValueError(
                f"{hid} is at {h.stage.value} and cannot jump to {stage.value}. The ladder "
                f"exists so that each rung spends a little more of the unseen data than the "
                f"last, and skipping one spends the expensive data first.")
        h.results.append({"stage": stage.value, "at": dt.datetime.now(dt.UTC).isoformat(),
                          **result})
        h.stage = stage
        self._append(h)
        return h

    def lineage(self, hid: str) -> list[Hypothesis]:
        """Root to leaf."""
        out, cur = [], self._items.get(hid)
        while cur is not None:
            out.append(cur)
            cur = self._items.get(cur.parent) if cur.parent else None
        return list(reversed(out))

    def descendants(self, hid: str) -> list[Hypothesis]:
        out, frontier = [], [hid]
        while frontier:
            p = frontier.pop()
            kids = [h for h in self._items.values() if h.parent == p]
            out.extend(kids)
            frontier.extend(k.id for k in kids)
        return out

    def effective_trials(self, hid: str) -> int:
        """How many trials this hypothesis really costs the multiplicity denominator.

        A first-generation hypothesis from a mechanism costs one. A descendant that exists
        because of something we saw in our own data costs one for itself PLUS one for every
        result-driven ancestor, because each of those ancestors was a look at the data that
        shaped this claim.

        This is a deliberately crude model of an effect that has no exact accounting. It is
        crude in the conservative direction, which is the only defensible way to be crude
        about a multiplicity bar.
        """
        line = self.lineage(hid)
        return 1 + sum(1 for h in line if h.result_driven)

    def _append(self, h: Hypothesis) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(h.to_json(), default=str) + "\n")

    def summary(self) -> str:
        by_stage: dict[str, int] = {}
        for h in self._items.values():
            by_stage[h.stage.value] = by_stage.get(h.stage.value, 0) + 1
        rd = sum(1 for h in self._items.values() if h.result_driven)
        lines = [f"{len(self._items)} hypotheses, {rd} of them result-driven"]
        lines += [f"  {k:22} {v}" for k, v in sorted(by_stage.items())]
        return "\n".join(lines)


__all__ = ["DEFAULT_PATH", "Hypothesis", "Registry", "Stage"]
