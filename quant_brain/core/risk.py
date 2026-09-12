"""Deterministic risk gating: the layer a model is not allowed to argue with.

Part 5 states the hard requirement: "The ML model must NEVER be able to override hard risk
constraints." That is an architectural property, not a coding convention, and it is enforced
here by shape:

  * A `RiskEngine` consumes an `OrderIntent` and returns a `RiskDecision`. It has no channel
    through which a model can pass a confidence, an override flag or a priority.
  * `RiskChain` composes engines and takes the **most restrictive** answer, always. There is
    no engine ordering that lets a later one re-permit what an earlier one denied.
  * A denial is terminal. `RiskDecision.allowed` is False and no `quantity` is carried, so a
    caller cannot accidentally use a reduced size from a rejected decision.

The one asymmetry, and it is deliberate: a FLATTEN intent is never reduced and never denied.
AUD-06 and AUD-08 in `research/audit_2026-09-12.md` are both cases where the order that
would have closed a position was suppressed by a sizing or ownership rule, leaving risk open
with nothing tracking it. A risk layer that can block the exit is not a risk layer.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field

from quant_brain.core.execution import OrderIntent


@dataclass(frozen=True)
class RiskDecision:
    """The verdict on one intent.

    Three outcomes only: allowed unchanged, allowed smaller, denied. `reasons` always
    explains a reduction or denial, because a risk layer whose refusals are not legible
    gets disabled by the next person who is in a hurry.
    """

    allowed: bool
    quantity: float
    reasons: tuple[str, ...] = ()
    #: Names of the hard rules that bound this decision. Reported by the simulator so a
    #: research run can say *which* constraint is the binding one, which is the difference
    #: between "this strategy fails" and "this strategy needs a smaller size".
    binding: tuple[str, ...] = ()

    @classmethod
    def allow(cls, quantity: float) -> RiskDecision:
        return cls(True, quantity)

    @classmethod
    def reduce(cls, quantity: float, reason: str, rule: str) -> RiskDecision:
        if quantity <= 0:
            return cls.deny(reason, rule)
        return cls(True, quantity, (reason,), (rule,))

    @classmethod
    def deny(cls, reason: str, rule: str) -> RiskDecision:
        return cls(False, 0.0, (reason,), (rule,))

    def merge(self, other: RiskDecision) -> RiskDecision:
        """Combine two verdicts, taking the more restrictive of the pair.

        Denial wins over reduction; a smaller quantity wins over a larger one. Reasons
        accumulate so the caller sees every rule that bit, not only the tightest.
        """
        reasons = self.reasons + other.reasons
        binding = self.binding + other.binding
        if not self.allowed or not other.allowed:
            return RiskDecision(False, 0.0, reasons, binding)
        return RiskDecision(True, min(self.quantity, other.quantity), reasons, binding)


class RiskEngine(abc.ABC):
    """One family of constraints.

    Kept deliberately narrow: an engine sees the intent and whatever account state it was
    constructed with, and returns a verdict. It does not place orders, does not mutate the
    account, and cannot see the model's opinion.
    """

    name: str = "risk"

    @abc.abstractmethod
    def evaluate(self, intent: OrderIntent) -> RiskDecision:
        """Verdict on `intent`. Must be pure with respect to the intent."""

    def __call__(self, intent: OrderIntent) -> RiskDecision:
        # Flatten bypasses every engine. See the module docstring - AUD-06 / AUD-08.
        if intent.is_flatten:
            return RiskDecision.allow(intent.quantity)
        return self.evaluate(intent)


@dataclass
class RiskChain(RiskEngine):
    """Every engine must agree. The result is the intersection of what they permit."""

    engines: list[RiskEngine] = field(default_factory=list)
    name: str = "chain"

    def evaluate(self, intent: OrderIntent) -> RiskDecision:
        decision = RiskDecision.allow(intent.quantity)
        for engine in self.engines:
            decision = decision.merge(engine(intent))
            if not decision.allowed:
                # Short-circuit: a denial cannot be un-denied, so the remaining engines can
                # only add reasons. Stopping keeps the reason list pointed at the cause.
                break
        return decision

    def add(self, engine: RiskEngine) -> RiskChain:
        self.engines.append(engine)
        return self
