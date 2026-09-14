"""The bounded discovery loop: many hypotheses in, almost nothing out.

Part 29 states the success condition, and it is a funnel rather than a search:

    500 hypotheses -> 450 rejected statistically -> 40 rejected on cost/execution
                   -> 8 fail Topstep survival -> 1 survives walk-forward
                   -> 1 reaches the holdout -> 1 becomes a Challenger

The point is the attrition. A loop that promotes its best candidate has learned nothing about
the market and everything about its own noise, so every stage here is a gate that can reject,
the stages run in increasing order of cost, and the statistical gate runs FIRST - it is the
cheapest and it removes the most.

WHY THE ORDER OF THE GATES IS NOT ARBITRARY
---------------------------------------------
Statistics first, then costs, then Topstep survival, then walk-forward. Two reasons, and the
second is the one that matters. The cheap reason is compute: a Monte Carlo over a hypothesis
that cannot clear its own t-statistic is wasted. The real reason is that the multiplicity
penalty must be paid on every hypothesis TRIED, not on the ones that reached the end. Running
the statistical gate last would mean the survivors were selected by cost and survival filters
whose selection is invisible to the correction, and the reported t would be a lie about a
much larger search.

WHAT BOUNDS IT (Part 15)
------------------------
An experiment budget, a wall-clock budget, and a resource check between candidates. The loop
stops when any binds and says which. Duplicate specifications are detected by fingerprint
before they are run, so a resumed search does not re-pay for work already in the ledger -
which is also what makes it resumable at all.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from quant_brain.research.registry import Experiment, Ledger, Stage


@dataclass(frozen=True)
class Hypothesis:
    """One testable specification. `signal` maps a feature frame to a position in [-1, 1]."""

    name: str
    family: str
    params: dict
    signal: Callable[..., object]

    def experiment(self, extra: dict | None = None) -> Experiment:
        return Experiment(hypothesis=self.name, family=self.family,
                          params={**self.params, **(extra or {})})


@dataclass
class Limits:
    """What stops the loop. Every one of these is reported when it binds."""

    max_experiments: int = 200
    max_seconds: float = 600.0
    #: Refuse to start another candidate when the machine is under pressure. Part 19: never
    #: sacrifice system stability to maximise utilisation.
    stop_above_pressure: str = "high"
    #: Minimum sessions a hypothesis must be evaluated on. Below this the t-statistic is
    #: noise and the multiplicity penalty is being paid for nothing.
    min_sessions: int = 100


@dataclass
class Funnel:
    """Where every hypothesis died. The attrition IS the result."""

    generated: int = 0
    duplicate: int = 0
    too_short: int = 0
    degenerate: int = 0
    rejected_leakage: int = 0
    rejected_statistical: int = 0
    rejected_cost: int = 0
    rejected_topstep: int = 0
    rejected_walkforward: int = 0
    survived: list[str] = field(default_factory=list)
    stopped_because: str = ""
    elapsed: float = 0.0

    @property
    def tested(self) -> int:
        return self.generated - self.duplicate - self.too_short

    def table(self) -> str:
        rows = [
            ("generated", self.generated),
            ("duplicate (already in ledger)", self.duplicate),
            ("too few sessions", self.too_short),
            ("degenerate (position never changes)", self.degenerate),
            ("rejected: leakage / look-ahead", self.rejected_leakage),
            ("rejected: statistical", self.rejected_statistical),
            ("rejected: cost / execution", self.rejected_cost),
            ("rejected: Topstep survival", self.rejected_topstep),
            ("rejected: walk-forward", self.rejected_walkforward),
            ("SURVIVED to holdout", len(self.survived)),
        ]
        width = max(len(r[0]) for r in rows)
        out = [f"  {k:<{width}}  {v:>5}" for k, v in rows]
        if self.stopped_because:
            out.append(f"  stopped: {self.stopped_because}")
        out.append(f"  elapsed: {self.elapsed:.1f}s")
        return "\n".join(out)


def _pressure_rank(name: str) -> int:
    return {"low": 0, "moderate": 1, "high": 2, "critical": 3}.get(str(name).lower(), 0)


def search(hypotheses: Iterable[Hypothesis],
           *,
           ledger: Ledger,
           evaluate: Callable[[Hypothesis], dict],
           limits: Limits | None = None,
           horizon: int = 1,
           on_result: Callable[[Hypothesis, dict, str], None] | None = None) -> Funnel:
    """Run hypotheses through the funnel, recording every one in the ledger.

    `evaluate` returns a dict for one hypothesis with at least:
        pnl       per-session P&L, net of costs   (sequence of float)
        sessions  how many sessions it traded     (int)
    and optionally:
        leakage_ok / cost_ok / topstep_ok / walkforward_ok  booleans from the gates, plus
        any metrics worth recording. `leakage_ok` is checked first and for good reason: a
        t-statistic computed on a look-ahead P&L is not weak evidence, it is no evidence.

    The caller supplies `evaluate` rather than this module owning a backtester, for the same
    reason `propfirm.evaluate` takes paths: how a strategy is simulated is a research decision
    with real content, and baking one in here would quietly override it.

    EVERY hypothesis is recorded, including the rejected ones. That is not bookkeeping - the
    rejections are the denominator of the multiplicity correction applied to the survivors.
    """
    lim = limits or Limits()
    fun = Funnel()
    started = time.monotonic()

    for h in hypotheses:
        fun.generated += 1

        if fun.tested >= lim.max_experiments:
            fun.stopped_because = f"experiment budget reached ({lim.max_experiments})"
            break
        elapsed = time.monotonic() - started
        if elapsed >= lim.max_seconds:
            fun.stopped_because = f"time budget reached ({lim.max_seconds:.0f}s)"
            break
        pressure = _current_pressure()
        if _pressure_rank(pressure) >= _pressure_rank(lim.stop_above_pressure):
            fun.stopped_because = f"machine pressure is {pressure}; refusing to start more"
            break

        exp = h.experiment()
        if ledger.seen(exp) is not None:
            # Not re-run and not re-counted. This is what makes a resumed search cheap and
            # what stops a loop inflating its own multiplicity by repeating itself.
            fun.duplicate += 1
            continue

        result = evaluate(h)
        pnl = list(result.get("pnl", []))
        sessions = int(result.get("sessions", len(pnl)))
        exp.metrics = {k: v for k, v in result.items() if k != "pnl"}

        if sessions < lim.min_sessions:
            fun.too_short += 1
            exp.stage = Stage.REJECTED
            exp.notes = f"only {sessions} sessions, below the {lim.min_sessions} floor"
            ledger.record(exp)
            _emit(on_result, h, result, "too_short")
            continue

        # --- not a hypothesis at all ------------------------------------------------
        # A candidate whose position never changes over the whole sample is buy-and-hold
        # wearing a rule's name. It is worth counting rather than scoring: measured on the
        # real ES store, 104 of the 136 cells in the shipped threshold grid are constants,
        # because the grid's thresholds are absolute numbers (-1.0, -0.5, +0.5, +1.0) and
        # most of the feature library is scaled in returns, so the comparison never flips.
        # 104/136 is 76.5%; the ledger's 624 zero-turn rows out of 816 are 76.5%. They are
        # the same rows. An attrition table that does not separate these is reporting a grid
        # that mostly did not run.
        if result.get("degenerate"):
            fun.degenerate += 1
            exp.stage = Stage.REJECTED
            exp.notes = str(result.get("degenerate_reason", "position never changes"))
            ledger.record(exp)
            _emit(on_result, h, result, "degenerate")
            continue

        # --- gate 0: leakage, before any statistic is computed ---------------------------
        # A statistic computed on leaked P&L is not a weak statistic, it is a meaningless
        # one, so this cannot sit after the t-test. Measured by the red-team suite
        # (tests/test_leakage_redteam.py): a one-bar close oracle run through this funnel
        # earns 100.0000% of the theoretical profit ceiling and clears EVERY later gate,
        # including 5/5 walk-forward folds and a Topstep pass rate of 1.0. Four separate
        # cheats did the same. There was no gate here at all.
        #
        # `evaluate` is what decides; this only records and stops. Keeping the judgement in
        # the evaluator is deliberate - what counts as a leak is a market-specific question
        # and baking one answer in here would quietly override it, the same reasoning that
        # keeps the backtester out of this module.
        if not result.get("leakage_ok", True):
            fun.rejected_leakage += 1
            exp.stage = Stage.REJECTED
            exp.notes = str(result.get("leakage_reason", "failed the leakage gate"))
            ledger.record(exp)
            _emit(on_result, h, result, "leakage")
            continue

        # --- gate 1: statistics, at the ledger's own trial count -------------------------
        verdict = ledger.verdict(exp, pnl, horizon=horizon)
        exp.verdict = verdict
        if not verdict.passed:
            fun.rejected_statistical += 1
            exp.stage = Stage.REJECTED
            exp.notes = verdict.reason
            ledger.record(exp)
            _emit(on_result, h, result, "statistical")
            continue

        # --- gate 2: costs and execution --------------------------------------------------
        if not result.get("cost_ok", True):
            fun.rejected_cost += 1
            exp.stage = Stage.REJECTED
            exp.notes = str(result.get("cost_reason", "failed the cost gate"))
            ledger.record(exp)
            _emit(on_result, h, result, "cost")
            continue

        # --- gate 3: Topstep survival ------------------------------------------------------
        if not result.get("topstep_ok", True):
            fun.rejected_topstep += 1
            exp.stage = Stage.REJECTED
            exp.notes = str(result.get("topstep_reason", "failed Topstep survival"))
            ledger.record(exp)
            _emit(on_result, h, result, "topstep")
            continue

        # --- gate 4: walk-forward ----------------------------------------------------------
        if not result.get("walkforward_ok", True):
            fun.rejected_walkforward += 1
            exp.stage = Stage.REJECTED
            exp.notes = str(result.get("walkforward_reason", "failed walk-forward"))
            ledger.record(exp)
            _emit(on_result, h, result, "walkforward")
            continue

        exp.stage = Stage.VALIDATION
        exp.notes = "survived every gate; eligible for the holdout"
        ledger.record(exp)
        fun.survived.append(h.name)
        _emit(on_result, h, result, "survived")

    fun.elapsed = time.monotonic() - started
    return fun


def _emit(cb, h, result, outcome) -> None:
    if cb is not None:
        cb(h, result, outcome)


def _current_pressure() -> str:
    try:
        from quant_brain.core.resources import snapshot
        return str(getattr(snapshot(), "pressure", "low"))
    except Exception:                                                   # noqa: BLE001
        return "low"


# =====================================================================================
# HYPOTHESIS GENERATION
# =====================================================================================

def threshold_hypotheses(feature_names: Sequence[str], *, family: str,
                         thresholds: Sequence[float] = (-1.0, -0.5, 0.5, 1.0),
                         directions: Sequence[int] = (1, -1)) -> list[Hypothesis]:
    """The simplest possible family: go long when a feature clears a threshold.

    Deliberately dumb. Part 9 says start simple, and the point of the first pass through the
    funnel is to measure the funnel, not to find an edge. A grid like this also makes the
    multiplicity concrete: len(features) x len(thresholds) x len(directions) hypotheses, each
    one paid for in the threshold every later candidate has to clear.
    """
    out: list[Hypothesis] = []
    for name in feature_names:
        for thr in thresholds:
            for direction in directions:
                params = {"feature": name, "threshold": float(thr), "direction": int(direction)}
                out.append(Hypothesis(
                    name=f"{name} {'>' if thr >= 0 else '<'} {thr:+.2f} dir {direction:+d}",
                    family=family, params=params,
                    signal=_threshold_signal(name, thr, direction)))
    return out


def _threshold_signal(name: str, thr: float, direction: int):
    def signal(features):
        import numpy as np
        x = features[name]
        raw = np.where(x >= thr, 1.0, -1.0) if thr >= 0 else np.where(x <= thr, -1.0, 1.0)
        return raw * direction
    return signal
