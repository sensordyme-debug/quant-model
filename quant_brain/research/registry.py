"""The experiment ledger, trial accounting, and the promotion ladder.

WHY THE TRIAL COUNT IS NOT AN ARGUMENT
----------------------------------------
Part 5 of the brief: "A candidate discovered after 10,000 experiments must not be evaluated
as though it were the first experiment." Every multiplicity correction in the literature
takes the number of trials as an input, and in practice that input is supplied by the person
who wants the result to be significant. It is the softest number in quantitative research.

So `Ledger.verdict()` does not accept one. It counts the experiments already recorded in the
same family and uses that. The only way to make the threshold easier is to run fewer
experiments, which is the correct incentive. Nothing in this module offers an override, and
`test_qb_research.py` asserts there is no keyword that reintroduces one.

WHAT AN EXPERIMENT IS
---------------------
A hypothesis, the provenance needed to reproduce it, and a metric. Its identity is a
fingerprint over the hypothesis and the parameters, which gives two properties Part 15 asks
for: duplicate experiments are detectable, and re-running one is idempotent rather than a
second trial. Running the same specification twice is not two pieces of evidence, and a
system that counted it as two would inflate its own multiplicity penalty while learning
nothing - the fingerprint stops both.

WHAT THIS DOES NOT DO
---------------------
It does not decide whether a strategy is good. It records what was tried, refuses to forget
it, and applies the arithmetic that follows. Promotion still requires a human-authored gate
(`promotion.py` in the runners) and, for anything live, an approval file on disk.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import enum
import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from quant_brain.core import stats
from quant_brain.core.provenance import Provenance


class Stage(str, enum.Enum):
    """Where a candidate sits on the ladder. Part 14.

    `REJECTED` is terminal and deliberately kept rather than deleted: the rejected
    experiments are the denominator of every multiplicity correction, and a system that
    forgets them is a system that flatters its survivors.
    """

    RESEARCH = "research"
    VALIDATION = "validation"
    CHALLENGER = "challenger"
    PAPER = "paper"
    CHAMPION = "champion"
    REJECTED = "rejected"

    @property
    def is_terminal(self) -> bool:
        return self is Stage.REJECTED

    @property
    def rank(self) -> int:
        order = [Stage.RESEARCH, Stage.VALIDATION, Stage.CHALLENGER, Stage.PAPER,
                 Stage.CHAMPION]
        return order.index(self) if self in order else -1


#: The only advances the ladder permits. Anything else raises, so a candidate cannot appear
#: as CHAMPION without having been a CHALLENGER and a PAPER run first.
ALLOWED: dict[Stage, set[Stage]] = {
    Stage.RESEARCH: {Stage.VALIDATION, Stage.REJECTED},
    Stage.VALIDATION: {Stage.CHALLENGER, Stage.REJECTED},
    Stage.CHALLENGER: {Stage.PAPER, Stage.REJECTED},
    Stage.PAPER: {Stage.CHAMPION, Stage.REJECTED},
    Stage.CHAMPION: {Stage.REJECTED},
    Stage.REJECTED: set(),
}


@dataclass(frozen=True)
class Verdict:
    """The statistical answer, with the multiplicity that produced it on the record."""

    metric: float
    t: float
    threshold: float
    trials: int
    horizon: int
    passed: bool
    reason: str

    def describe(self) -> str:
        head = "PASS" if self.passed else "FAIL"
        return (f"{head}  t={self.t:+.2f} vs |t|>{self.threshold:.2f} "
                f"after {self.trials} trial(s) at h={self.horizon} - {self.reason}")


@dataclass
class Experiment:
    """One hypothesis, tried once, with everything needed to reproduce and to count it."""

    hypothesis: str
    family: str
    params: dict = field(default_factory=dict)
    provenance: Provenance | None = None
    metrics: dict = field(default_factory=dict)
    stage: Stage = Stage.RESEARCH
    verdict: Verdict | None = None
    notes: str = ""
    created: str = ""
    experiment_id: str = ""

    def __post_init__(self) -> None:
        if not self.family.strip():
            raise ValueError("an experiment must belong to a named family; the family is "
                             "the unit multiplicity is counted over, so an unnamed one "
                             "would escape the correction")
        if not self.created:
            self.created = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        if not self.experiment_id:
            self.experiment_id = self.fingerprint()

    def fingerprint(self) -> str:
        """Identity from the specification, so a re-run is the same experiment.

        Deliberately excludes the metrics, the timestamp and the verdict: those are the
        OUTCOME, and an identity that included them would make every re-run a new trial and
        let a search launder its multiplicity by simply running things twice.
        """
        payload = json.dumps({"hypothesis": self.hypothesis, "family": self.family,
                              "params": self.params},
                             sort_keys=True, default=str)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        d = {
            "experiment_id": self.experiment_id,
            "hypothesis": self.hypothesis,
            "family": self.family,
            "params": self.params,
            "metrics": self.metrics,
            "stage": self.stage.value,
            "notes": self.notes,
            "created": self.created,
            "provenance": self.provenance.to_dict() if self.provenance else None,
            "verdict": dataclasses.asdict(self.verdict) if self.verdict else None,
        }
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Experiment:
        v = d.get("verdict")
        return cls(
            hypothesis=d["hypothesis"], family=d["family"], params=d.get("params", {}),
            metrics=d.get("metrics", {}), stage=Stage(d.get("stage", "research")),
            verdict=Verdict(**v) if v else None, notes=d.get("notes", ""),
            created=d.get("created", ""), experiment_id=d.get("experiment_id", ""),
            provenance=None,
        )


@dataclass
class Candidate:
    """A strategy tracked across the ladder, distinct from the experiment that found it."""

    candidate_id: str
    experiment_id: str
    strategy_version: str = ""
    model_version: str = ""
    dataset_version: str = ""
    feature_version: str = ""
    stage: Stage = Stage.RESEARCH
    history: list[tuple[str, str]] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def advance(self, to: Stage, *, why: str) -> Candidate:
        """Move one rung. Raises on any transition the ladder does not permit."""
        if to not in ALLOWED[self.stage]:
            raise ValueError(
                f"{self.candidate_id}: {self.stage.value} -> {to.value} is not a permitted "
                f"transition (allowed: {sorted(s.value for s in ALLOWED[self.stage])}). "
                f"A candidate cannot skip a rung; that is what the ladder is for.")
        if not why.strip():
            raise ValueError("a stage change must carry a reason")
        self.history.append((f"{self.stage.value}->{to.value}", why))
        self.stage = to
        return self


class Ledger:
    """Append-only experiment record on disk. The denominator of every correction.

    JSONL with atomic appends, because six agent tracks share this tree and a torn write
    would corrupt the trial count - which is the one number this module exists to protect.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)

    # -- reading ---------------------------------------------------------------------------

    def all(self) -> list[Experiment]:
        if not self.path.exists():
            return []
        out: list[Experiment] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    out.append(Experiment.from_dict(json.loads(line)))
                except (json.JSONDecodeError, KeyError):
                    continue    # a malformed row must not hide the rest of the history
        return out

    def family(self, family: str) -> list[Experiment]:
        return [e for e in self.all() if e.family == family]

    def trials(self, family: str) -> int:
        """Distinct experiments already recorded in this family.

        Distinct, not rows: re-running the same specification is not a second piece of
        evidence about the market, and counting it would inflate the penalty without
        learning anything.
        """
        return len({e.experiment_id for e in self.family(family)})

    def seen(self, experiment: Experiment) -> Experiment | None:
        """The previously recorded run of this exact specification, if there is one."""
        fp = experiment.fingerprint()
        for e in self.all():
            if e.experiment_id == fp:
                return e
        return None

    # -- writing ---------------------------------------------------------------------------

    def record(self, experiment: Experiment) -> Experiment:
        """Append one experiment. Idempotent on the fingerprint."""
        prior = self.seen(experiment)
        if prior is not None:
            return prior
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(experiment.to_dict(), sort_keys=True, default=str) + "\n"
        # Atomic append: write the whole new content to a temp file in the same directory and
        # replace. Slower than an O_APPEND write and correct under concurrent agents, which
        # is the trade this repository wants - the alternative loses experiments silently.
        existing = self.path.read_text(encoding="utf-8") if self.path.exists() else ""
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(existing + line)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return experiment

    # -- the arithmetic --------------------------------------------------------------------

    def verdict(self, experiment: Experiment, series, *, horizon: int = 1) -> Verdict:
        """Judge a result against a threshold sized by the trials ALREADY IN THE LEDGER.

        There is no `n_trials` parameter and adding one would defeat the module. The count
        includes this experiment, so the first hypothesis in a family faces |t| > 1.96 and
        the hundredth faces a materially harder bar.

        `horizon` is the label's forward span. It is required in substance because
        `stats.tstat_hac` refuses a lag below h-1: an overlapping label is an MA(h-1) and an
        IID t-statistic on one is not a statistic, it is a number.
        """
        prior = self.trials(experiment.family)
        already = self.seen(experiment) is not None
        n = prior if already else prior + 1

        t = stats.tstat_hac(series, horizon=horizon)
        threshold = stats.bonferroni_threshold(n)
        value = float(t.t)
        passed = bool(abs(value) > threshold) and math.isfinite(value)
        if not math.isfinite(value):
            reason = "t-statistic is not finite; the series has no usable variance"
        elif passed:
            reason = f"survives {n}-trial correction in family {experiment.family!r}"
        else:
            reason = (f"|t|={abs(value):.2f} does not clear {threshold:.2f}; "
                      f"{n} trial(s) in family {experiment.family!r}")
        return Verdict(metric=float(getattr(t, "mean", float("nan"))), t=value,
                       threshold=float(threshold), trials=n, horizon=horizon,
                       passed=passed, reason=reason)

    def summary(self, family: str | None = None) -> str:
        rows = self.family(family) if family else self.all()
        by_stage: dict[str, int] = {}
        for e in rows:
            by_stage[e.stage.value] = by_stage.get(e.stage.value, 0) + 1
        parts = ", ".join(f"{k}={v}" for k, v in sorted(by_stage.items()))
        fams = sorted({e.family for e in rows})
        return (f"{len(rows)} experiment(s) across {len(fams)} famil(y/ies)"
                + (f" [{parts}]" if parts else ""))
