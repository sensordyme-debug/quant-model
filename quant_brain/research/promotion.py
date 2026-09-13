"""The champion/challenger promotion gate: the rungs between a good number and real money.

Parts 11 and 14. `registry.py` builds the ladder and refuses illegal transitions; `search.py`
runs the funnel that gets a candidate as far as `Stage.VALIDATION`. Neither of them decides
anything. This module is the decision, and it is deliberately the least accommodating file in
the package.

WHY A GATE AND NOT A RANKING
-----------------------------
The failure mode this exists to prevent is not "a bad strategy scored well". It is "a
strategy became champion because it was the best of the batch". A ranking always has a
winner. Ranking 500 hypotheses and promoting the top one is a procedure that returns a
champion when handed pure noise, and it returns one with a confident-looking score, because
the maximum of 500 noise draws is large by construction. So nothing here compares a candidate
to its peers. Every condition is absolute, every one of them must hold, and the answer to
"which was best?" is not an input.

That is also why `decide()` returns a `Decision` and not a bool. A bool invites the reading
"it failed, but only just" without ever putting the failing condition on the record. The
decision object names every condition, says which held, and survives into the journal - so a
promotion six weeks old can still be argued with.

WHAT THE CONDITIONS ARE, AND WHAT EACH ONE PREVENTS
----------------------------------------------------
    ladder          the transition is one the ladder permits. Prevents a candidate appearing
                    as CHAMPION without having been a CHALLENGER and a PAPER run first, which
                    is the shape every "we were in a hurry" promotion takes.
    statistical     the ledger's verdict passed, AND it was taken at the trial count the
                    ledger holds NOW. The second half is the one that bites: a candidate that
                    cleared |t| > 1.96 as experiment 3 of a search that eventually ran 500 was
                    never judged against its own multiplicity, and its recorded verdict says
                    PASS forever. AUD-19's arithmetic: at 55 trials, ~2.75 spurious
                    "significant" results are expected from noise alone.
    costs           costs are below a stated share of GROSS profit. Net-of-cost P&L hides the
                    case where the edge is real and the broker keeps most of it - a strategy
                    that grosses 100k and pays 80k in costs is a fee-generation machine with a
                    thin positive residual, and it degrades to negative on any slippage
                    surprise.
    topstep         the prop-firm pass rate over resampled paths clears a floor. Part 6's
                    point: the account has a trailing drawdown rule, so a strategy's expected
                    P&L is almost irrelevant next to the probability that its path kills the
                    account before the profit target is reached.
    walk_forward    most folds positive AND the mean positive. Either alone is foolable: a
                    positive mean can be one enormous fold on top of four losers, and a
                    majority of tiny wins can sit under one catastrophic loss.
    holdout         the write-once holdout was spent EXACTLY ONCE, on THIS candidate, and it
                    passed. See below.
    beats_champion  strictly better than the incumbent. Passing is not beating.

    reproducible    ADVISORY, not blocking, and this is a calibration rather than an
                    aspiration - the same trade ruff.toml makes. Almost every experiment in
                    this repository runs from a dirty tree, because the sweep script that
                    produced it is usually untracked at the time it runs. Making that blocking
                    would mean the gate never passes, and a gate that never passes is a gate
                    that gets bypassed. It is reported on every decision so the cost of that
                    concession stays visible.

WHY THE HOLDOUT CHECK IS ABOUT COUNTING, NOT SCORING
------------------------------------------------------
`core.validation.Holdout` makes a second look raise. That protects the holdout from being
re-read; it does not protect the promotion from being made on a holdout that was read twice
under `force=True`, or on a holdout that was spent evaluating a DIFFERENT candidate. Both
happen: the second is the more common and the less obvious - candidate A spends the holdout,
candidate B is a small variation of A, and B gets promoted quoting A's out-of-sample number.
The holdout was still spent once, and B has no out-of-sample evidence at all.

So the gate reads the holdout's own ledger and requires exactly one look, stamped with this
candidate's id. `spend_holdout()` does the stamping and takes no `force` parameter, so the
supported path cannot produce an unusable record.

WHY A CROSS-ENVIRONMENT COMPARISON RAISES INSTEAD OF FAILING A CHECK
----------------------------------------------------------------------
`core.provenance` documents the drift: this repository runs pandas 2.2 on Python 3.11 and
pandas 3.0 on 3.14, both writing to the same ledger, and copy-on-write, string dtype and
resample semantics all moved between those versions. A challenger measured under one and a
champion measured under the other differ by an unknown amount that has nothing to do with the
strategy.

That is not a condition that can be weighed against the others. "Nine of ten conditions
passed" is a sentence someone will act on; "the comparison is meaningless" is not a score at
all. So `refuse_cross_environment` raises `EnvironmentMismatch` before any condition is
evaluated, and no `Decision` is produced to quote. It also refuses an UNRECORDED environment:
not knowing whether two numbers are comparable is the same position as knowing they are not.
"""
from __future__ import annotations

import dataclasses
import math
from collections.abc import Sequence
from dataclasses import dataclass

from quant_brain.core.provenance import Provenance
from quant_brain.core.validation import Holdout
from quant_brain.research.registry import ALLOWED, Candidate, Experiment, Ledger, Stage


class PromotionRefused(RuntimeError):
    """The gate declined to produce or act on a decision. Distinct from "did not promote".

    A candidate that fails a condition is answered with a `Decision`, because that is
    information. A refusal means the question itself was malformed - comparing across
    interpreters, applying a decision to the wrong candidate, acting on a stale one - and
    answering it at all would manufacture a number that means nothing.
    """


class EnvironmentMismatch(PromotionRefused):
    """Two results were about to be compared that were produced by different software."""


# --------------------------------------------------------------------------------------
# The conditions, and which rung requires which.
#
# Cumulative by construction: each rung requires everything the rung below it did, plus one
# more. Written as data rather than as branches so the cumulativeness is checkable - a test
# asserts that no rung drops a condition an earlier rung required, which is the shape a
# well-meaning refactor breaks first.
# --------------------------------------------------------------------------------------

#: Conditions every promotion must satisfy, at every rung.
CORE_CHECKS: tuple[str, ...] = ("ladder", "statistical", "costs", "topstep", "walk_forward")

#: Reported on every decision, blocking on none. See the module docstring.
ADVISORY_CHECKS: tuple[str, ...] = ("reproducible",)

CHECKS_BY_RUNG: dict[Stage, tuple[str, ...]] = {
    # RESEARCH -> VALIDATION is the funnel's own output (search.py runs these four gates), so
    # the gate here re-checks them rather than trusting the funnel's booleans.
    Stage.VALIDATION: CORE_CHECKS,
    # VALIDATION -> CHALLENGER is where the holdout is spent. Part 29's funnel: "1 survives
    # walk-forward -> 1 reaches the holdout -> 1 becomes a Challenger".
    Stage.CHALLENGER: (*CORE_CHECKS, "holdout"),
    # CHALLENGER -> PAPER re-checks everything: paper trading costs real time on a real
    # account and the evidence must still hold on the day, not on the day it was gathered.
    Stage.PAPER: (*CORE_CHECKS, "holdout"),
    # PAPER -> CHAMPION adds the only comparative condition in the module.
    Stage.CHAMPION: (*CORE_CHECKS, "holdout", "beats_champion"),
}


@dataclass(frozen=True)
class Rules:
    """The numeric floors. Frozen, and every default carries its reasoning.

    Exposed as a dataclass so a track can state a stricter rule for its own family, and
    deliberately NOT read from a config file: a threshold that lives in a file gets edited
    the evening a candidate misses it, and nothing in the git history says why.
    """

    #: Fewer folds than this and "most folds positive" is a coin-flip statement. Four is the
    #: smallest count where a 3/4 majority is not simply 2-of-3.
    min_folds: int = 4
    #: Share of folds that must be positive. 0.6 of five folds is three, which is the weakest
    #: majority worth calling one.
    min_fold_win_rate: float = 0.6
    #: Prop-firm pass rate over resampled paths. A third is not a good business; it is the
    #: level below which the evaluation fee dominates the expected capital, which is the
    #: number `propfirm.evaluate` actually reports.
    min_topstep_pass_rate: float = 0.35
    #: Costs as a share of GROSS profit. Above a third, an unmodelled slippage regime of the
    #: size this repository routinely measures turns the strategy negative.
    max_cost_share: float = 0.35
    #: How much better than the incumbent a challenger must be. Zero means "strictly better";
    #: it is a floor on the margin, not a tolerance that lets a tie through.
    min_beat_margin: float = 0.0


@dataclass(frozen=True)
class Check:
    """One condition and its answer. `detail` is written to be read months later.

    `required` is what makes the advisory tier possible without weakening the gate: a check
    that is not required is reported in full and excluded from `Decision.promoted`, and the
    set of non-required names is a module constant rather than a per-call argument.
    """

    name: str
    passed: bool
    detail: str
    required: bool = True

    def describe(self) -> str:
        mark = "PASS" if self.passed else ("FAIL" if self.required else "warn")
        return f"  [{mark}] {self.name}: {self.detail}"


@dataclass(frozen=True)
class Decision:
    """What the gate concluded, condition by condition. Immutable on purpose.

    Frozen because a decision that can be edited after the fact is a decision nobody has to
    argue with. `checks` is a tuple for the same reason: appending a passing check to a
    failed decision is exactly the shortcut a tired agent would take at 03:00.
    """

    candidate_id: str
    from_stage: Stage
    to_stage: Stage
    checks: tuple[Check, ...]
    env_key: str = ""

    @property
    def promoted(self) -> bool:
        """True only when every REQUIRED condition held. Advisories cannot block."""
        return all(c.passed for c in self.checks if c.required)

    @property
    def failures(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if c.required and not c.passed)

    @property
    def warnings(self) -> tuple[Check, ...]:
        return tuple(c for c in self.checks if not c.required and not c.passed)

    def reason(self) -> str:
        """One line, suitable for `Candidate.advance(why=...)` and for a journal entry."""
        move = f"{self.from_stage.value}->{self.to_stage.value}"
        if not self.promoted:
            return f"{move} REFUSED: " + "; ".join(
                f"{c.name} - {c.detail}" for c in self.failures)
        names = [c.name for c in self.checks if c.required]
        warned = [c.name for c in self.warnings]
        tail = f"; advisory: {', '.join(warned)}" if warned else ""
        return f"{move} on {len(names)} condition(s) [{', '.join(names)}]{tail}"

    def describe(self) -> str:
        head = "PROMOTE" if self.promoted else "HOLD"
        return "\n".join([
            f"{head}  {self.candidate_id}  {self.from_stage.value} -> {self.to_stage.value}"
            f"  env={self.env_key or '?'}",
            *[c.describe() for c in self.checks],
        ])

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "from_stage": self.from_stage.value,
            "to_stage": self.to_stage.value,
            "env_key": self.env_key,
            "promoted": self.promoted,
            "checks": [dataclasses.asdict(c) for c in self.checks],
            "reason": self.reason(),
        }


@dataclass
class Evidence:
    """Everything the gate is allowed to look at. Nothing is fetched behind the caller's back.

    The gate takes numbers rather than a backtester, for the reason `search.py` and
    `propfirm.evaluate` both give: how a strategy is simulated and how its sessions are
    resampled are research decisions with real content, and a gate that computed them would
    quietly override the track that owns them.

    Every optional field defaults to None rather than to a permissive value. A missing number
    FAILS its condition; it does not skip it. That asymmetry is the entire design - the common
    way a gate stops working is that a caller stops populating a field and the check silently
    starts passing.
    """

    candidate: Candidate
    experiment: Experiment
    provenance: Provenance

    #: Per-fold walk-forward scores, in fold order.
    fold_scores: Sequence[float] = ()
    #: `propfirm.Evaluation.pass_rate`: a fraction in [0, 1], not a percentage.
    topstep_pass_rate: float | None = None
    #: Gross profit BEFORE costs, and the costs themselves, in the same currency.
    gross_profit: float | None = None
    costs: float | None = None
    #: The write-once holdout this candidate's out-of-sample claim rests on.
    holdout: Holdout | None = None

    #: The scalar the champion comparison is made on. Only read at PAPER -> CHAMPION.
    score: float | None = None
    champion: Candidate | None = None
    champion_provenance: Provenance | None = None
    champion_score: float | None = None


def refuse_cross_environment(challenger: Provenance | None,
                             champion: Provenance | None,
                             *, what: str = "this comparison") -> str:
    """Raise unless both results came from the same recorded software environment.

    Returns the shared `env_key` so a caller can stamp it on whatever it produces.

    Separate from the gate and public, because the same refusal belongs anywhere two numbers
    from this repository's ledger meet - `scripts/evaluate.py` already refuses to compare
    across cost models and backtest windows (S-18, F-3) and this is the same principle on the
    axis `provenance.py` was written to expose. It raises rather than returning a flag for the
    reason in the module docstring: a meaningless comparison is not a low score.
    """
    if challenger is None:
        raise EnvironmentMismatch(
            f"{what}: no provenance on the challenger. An unrecorded environment is not the "
            f"same as a matching one - it is the case where nobody can tell.")
    mine = challenger.env_key
    if not challenger.python_version:
        raise EnvironmentMismatch(
            f"{what}: the challenger's provenance records no interpreter version, so its "
            f"env_key is {mine!r}. Capture provenance at the top of the run "
            f"(`Provenance.capture`); a blank key would match every other blank key and the "
            f"refusal would never fire.")
    if champion is None:
        return mine
    theirs = champion.env_key
    if theirs != mine:
        raise EnvironmentMismatch(
            f"{what}: challenger measured under {mine}, incumbent under {theirs}. These are "
            f"different interpreters and/or different numeric stacks - this repository runs "
            f"pandas 2.2 on 3.11 and pandas 3.0 on 3.14, which disagree on copy-on-write, "
            f"string dtype and resample semantics. The difference between the two numbers "
            f"contains an unknown amount of software. Re-measure one of them in the other's "
            f"environment; there is no flag that makes this comparison valid.")
    return mine


class PromotionGate:
    """Decides whether one candidate may advance one rung. It cannot be argued with.

    Holds the ledger because the statistical condition needs the CURRENT trial count, not the
    one that was current when the verdict was written. That is the whole reason this is a
    class and not a function: the trial count has to be read at decision time, from the
    ledger, and not accepted from the caller - the same rule `Ledger.verdict` enforces one
    level down.
    """

    def __init__(self, ledger: Ledger, rules: Rules | None = None) -> None:
        self.ledger = ledger
        self.rules = rules or Rules()

    # -- the holdout ---------------------------------------------------------------------

    def spend_holdout(self, evidence: Evidence, *, result: dict, note: str) -> dict:
        """Spend the candidate's one look at the final holdout, stamped with its identity.

        There is no `force` parameter and adding one would defeat the module: `Holdout.spend`
        already offers force for the case where a human decides, out loud, to burn a holdout,
        and a promotion made on a burnt holdout is exactly what this gate exists to catch. The
        two facilities must not be the same function.

        The stamp is what stops candidate B being promoted on candidate A's look. `result`
        must carry `passed`; the gate reads it back from the holdout's own on-disk ledger
        rather than from memory, so a look taken in a previous session counts.
        """
        if evidence.holdout is None:
            raise PromotionRefused(
                f"{evidence.candidate.candidate_id} has no holdout to spend; carve one with "
                f"`validation.make_holdout` before the candidate reaches CHALLENGER")
        env = refuse_cross_environment(evidence.provenance, None,
                                       what=f"holdout for {evidence.candidate.candidate_id}")
        stamped = {**result,
                   "candidate_id": evidence.candidate.candidate_id,
                   "experiment_id": evidence.experiment.experiment_id,
                   "env_key": env}
        return evidence.holdout.spend(result=stamped, note=note)

    # -- the decision ----------------------------------------------------------------------

    def decide(self, evidence: Evidence, *, to: Stage) -> Decision:
        """Evaluate every condition required at `to` and return them all.

        There is no `force`, no `override` and no `score` shortcut, and there is a test that
        asserts none of those names ever appears in this signature. A candidate is promoted
        because every condition held, or it is not promoted.
        """
        if to is Stage.REJECTED:
            raise ValueError(
                "rejecting a candidate is `Candidate.advance(Stage.REJECTED, why=...)` and "
                "needs no evidence. A gate that could also reject would be a gate with a "
                "reason to be asked twice.")
        if to not in CHECKS_BY_RUNG:
            raise ValueError(f"{to.value} is not a rung this gate promotes to; "
                             f"expected one of {[s.value for s in CHECKS_BY_RUNG]}")

        # Before anything is measured. A refused comparison must not leave a partial decision
        # behind for someone to quote the passing half of.
        env = refuse_cross_environment(
            evidence.provenance, evidence.champion_provenance,
            what=f"{evidence.candidate.candidate_id} -> {to.value}")

        required = CHECKS_BY_RUNG[to]
        built = [self._ladder(evidence, to), self._statistical(evidence), self._costs(evidence),
                 self._topstep(evidence), self._walk_forward(evidence)]
        if "holdout" in required:
            built.append(self._holdout(evidence))
        if "beats_champion" in required:
            built.append(self._beats_champion(evidence))
        built.extend(self._advisories(evidence))

        checks = tuple(dataclasses.replace(c, required=c.name in required) for c in built)
        return Decision(candidate_id=evidence.candidate.candidate_id,
                        from_stage=evidence.candidate.stage, to_stage=to,
                        checks=checks, env_key=env)

    def apply(self, evidence: Evidence, decision: Decision) -> Candidate:
        """Move the candidate, but only on a decision that is passing, matching and fresh.

        The freshness check is the interesting one. Without it, `decide()` once and `apply()`
        twice would walk a candidate up two rungs on one piece of evidence, which is the
        rung-skipping the ladder exists to prevent wearing a different hat. A decision is
        valid for the stage it was taken at and no other.
        """
        cand = evidence.candidate
        if decision.candidate_id != cand.candidate_id:
            raise PromotionRefused(
                f"this decision was taken for {decision.candidate_id!r} and cannot be applied "
                f"to {cand.candidate_id!r}")
        if decision.from_stage is not cand.stage:
            raise PromotionRefused(
                f"stale decision: it was taken while {cand.candidate_id} was at "
                f"{decision.from_stage.value} and the candidate is now at {cand.stage.value}. "
                f"Re-decide; evidence does not carry across a rung.")
        if not decision.promoted:
            raise PromotionRefused(decision.reason())
        return cand.advance(decision.to_stage, why=decision.reason())

    # -- the conditions ----------------------------------------------------------------------

    def _ladder(self, ev: Evidence, to: Stage) -> Check:
        frm = ev.candidate.stage
        if to in ALLOWED[frm]:
            return Check("ladder", True, f"{frm.value} -> {to.value} is a permitted rung")
        return Check("ladder", False,
                     f"{frm.value} -> {to.value} skips a rung (permitted from {frm.value}: "
                     f"{sorted(s.value for s in ALLOWED[frm])})")

    def _statistical(self, ev: Evidence) -> Check:
        """The ledger's verdict, re-checked against the trial count the ledger holds NOW."""
        v = ev.experiment.verdict
        if v is None:
            return Check("statistical", False,
                         "no verdict on the experiment; a candidate with no recorded "
                         "statistical test has not been tested, whatever its metrics say")
        now = self.ledger.trials(ev.experiment.family)
        if v.trials < now:
            return Check("statistical", False,
                         f"the verdict was taken at {v.trials} trial(s) but family "
                         f"{ev.experiment.family!r} now holds {now}. It cleared "
                         f"{v.threshold:.2f}; the current bar is higher. Re-run "
                         f"`Ledger.verdict` before promoting - a stale PASS is the ordinary "
                         f"way a search launders its own multiplicity.")
        if not v.passed:
            return Check("statistical", False, v.describe())
        return Check("statistical", True, v.describe())

    def _costs(self, ev: Evidence) -> Check:
        if ev.gross_profit is None or ev.costs is None:
            return Check("costs", False,
                         "gross profit and costs were not both supplied; net P&L alone cannot "
                         "show how much of the edge the broker keeps")
        gross, costs = float(ev.gross_profit), float(ev.costs)
        if not (math.isfinite(gross) and math.isfinite(costs)):
            return Check("costs", False, f"gross={gross} costs={costs} are not both finite")
        if costs < 0:
            return Check("costs", False,
                         f"costs are {costs:+,.2f}. A negative cost is a modelling error - a "
                         f"rebate that nets to a credit - and it would make the share "
                         f"negative and pass this check without anyone reading it.")
        if gross <= 0:
            return Check("costs", False,
                         f"gross profit is {gross:+,.2f}, so there is no gross edge for costs "
                         f"to be a share of. Zero costs on zero gross must not read as 0%.")
        share = costs / gross
        cap = self.rules.max_cost_share
        ok = share <= cap
        return Check("costs", ok,
                     f"costs are {share:.1%} of gross ({costs:,.2f} of {gross:,.2f}) "
                     f"vs a {cap:.0%} ceiling")

    def _topstep(self, ev: Evidence) -> Check:
        rate = ev.topstep_pass_rate
        if rate is None:
            return Check("topstep", False,
                         "no prop-firm pass rate supplied; expected P&L says nothing about "
                         "whether the path survives a trailing drawdown rule")
        rate = float(rate)
        if not math.isfinite(rate) or not 0.0 <= rate <= 1.0:
            return Check("topstep", False,
                         f"pass rate {rate} is not a fraction in [0, 1]. This is almost always "
                         f"a percentage passed where a fraction was expected, and 45.0 would "
                         f"clear every floor this module could state.")
        floor = self.rules.min_topstep_pass_rate
        return Check("topstep", rate >= floor,
                     f"prop-firm pass rate {rate:.1%} vs a {floor:.0%} floor")

    def _walk_forward(self, ev: Evidence) -> Check:
        folds = [float(x) for x in ev.fold_scores]
        rules = self.rules
        if len(folds) < rules.min_folds:
            return Check("walk_forward", False,
                         f"{len(folds)} fold(s), below the {rules.min_folds} needed for "
                         f"'most folds positive' to mean anything")
        if not all(math.isfinite(x) for x in folds):
            return Check("walk_forward", False,
                         f"fold scores contain a non-finite value: {folds}. A NaN fold is a "
                         f"fold that did not run, and dropping it silently changes the "
                         f"denominator of the win rate.")
        wins = sum(1 for x in folds if x > 0)
        share = wins / len(folds)
        mean = sum(folds) / len(folds)
        ok = share >= rules.min_fold_win_rate and mean > 0
        return Check("walk_forward", ok,
                     f"{wins}/{len(folds)} folds positive ({share:.0%} vs "
                     f"{rules.min_fold_win_rate:.0%}), mean {mean:+.4f}"
                     + ("" if ok else "; a positive mean carried by one fold is a strategy "
                        "that worked once, and a majority of tiny wins under one large loss "
                        "is not an edge either"))

    def _holdout(self, ev: Evidence) -> Check:
        """Exactly one look, on this candidate, and it passed. Counting, then scoring."""
        if ev.holdout is None:
            return Check("holdout", False,
                         "no final holdout; the out-of-sample claim rests on nothing")
        looks = ev.holdout.looks()
        label = ev.holdout.label or ev.holdout.fingerprint[:12]
        if not looks:
            return Check("holdout", False,
                         f"holdout {label} has never been evaluated. A candidate cannot reach "
                         f"CHALLENGER on in-sample evidence, and the holdout is spent through "
                         f"`PromotionGate.spend_holdout`, deliberately, once.")
        if len(looks) > 1:
            when = ", ".join(str(r.get("when")) for r in looks)
            return Check("holdout", False,
                         f"holdout {label} has been evaluated {len(looks)} times ({when}). "
                         f"The second look is where the out-of-sample claim dies: the number "
                         f"quoted is now the best of {len(looks)}, selected with knowledge of "
                         f"the holdout. Carve a fresh holdout or promote nothing.")
        rec = looks[0]
        result = rec.get("result") or {}
        owner = result.get("candidate_id")
        if owner != ev.candidate.candidate_id:
            return Check("holdout", False,
                         f"holdout {label} was spent on {owner!r}, not on "
                         f"{ev.candidate.candidate_id!r}. One look means one candidate; a "
                         f"variation of the candidate that spent it has no out-of-sample "
                         f"evidence of its own, however small the variation.")
        if "passed" not in result:
            return Check("holdout", False,
                         f"the single look at {label} recorded no `passed` field, so what it "
                         f"decided cannot be read back: {sorted(result)}")
        if not result.get("passed"):
            return Check("holdout", False,
                         f"the single look at {label} did not pass: "
                         f"{result.get('reason') or result}")
        return Check("holdout", True,
                     f"holdout {label} spent exactly once, on this candidate, on "
                     f"{rec.get('when')} - {rec.get('note')!r}")

    def _beats_champion(self, ev: Evidence) -> Check:
        """Strictly better than the incumbent. Passing every other condition is not beating."""
        if ev.champion is None:
            return Check("beats_champion", True,
                         "no incumbent champion; this candidate is the first, and it earns "
                         "the seat on the other conditions rather than on a comparison")
        if ev.score is None or ev.champion_score is None:
            return Check("beats_champion", False,
                         f"incumbent {ev.champion.candidate_id} is present but the comparison "
                         f"score is missing (challenger={ev.score}, "
                         f"incumbent={ev.champion_score})")
        mine, theirs = float(ev.score), float(ev.champion_score)
        if not (math.isfinite(mine) and math.isfinite(theirs)):
            return Check("beats_champion", False,
                         f"scores are not both finite: {mine} vs {theirs}")
        margin = mine - theirs
        ok = margin > self.rules.min_beat_margin
        tie = " - a tie is not a win; the incumbent has live evidence the challenger does not"
        return Check("beats_champion", ok,
                     f"{mine:+.4f} vs incumbent {ev.champion.candidate_id} {theirs:+.4f} "
                     f"(margin {margin:+.4f} vs {self.rules.min_beat_margin:+.4f})"
                     + ("" if ok or margin < 0 else tie))

    def _advisories(self, ev: Evidence) -> list[Check]:
        p = ev.provenance
        if p.reproducible:
            return [Check("reproducible", True,
                          f"clean tree at {p.git_commit[:8]} under {p.env_key}")]
        why = "dirty working tree" if p.git_commit else "no commit recorded"
        return [Check("reproducible", False,
                      f"{why}; this run cannot be reproduced from git alone. Advisory, not "
                      f"blocking - see the module docstring on why making it blocking would "
                      f"turn the gate off rather than clean the tree.")]
