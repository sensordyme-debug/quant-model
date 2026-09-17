"""The register of things this pipeline cannot compute, and why.

WHY THIS FILE EXISTS
--------------------
The research brief asks for a full account journey: Combine, funded account, Express Funded
Account, first payout, and the distribution of time to that payout. The upstream engine
models the Combine. It does not model the rest - ``metrics/economics.py`` says so in its own
header ("Funded is parked; see docs/ROADMAP.md") and ships a single user-supplied
``pass_value`` scalar in place of a funded simulation.

That leaves two options. Build a funded-account model in Layer B, or report the gap. Building
it would mean inventing payout timing, buffer rules and withdrawal mechanics that nobody in
this pipeline has a source for, and the output would be indistinguishable in a report from
the figures that ARE grounded. So: report the gap, in a form that is hard to ignore and
impossible to confuse with a computed number.

Each entry names what was asked for, why it cannot be answered, and what WOULD be needed to
answer it. That last field matters - it turns "we did not do this" into a scope statement
someone can act on.
"""
from __future__ import annotations

from dataclasses import dataclass

#: The literal that appears in every report field with no number behind it.
UNMODELED = "UNMODELED"


@dataclass(frozen=True)
class UnmodeledItem:
    ref: str
    topic: str
    reason: str
    what_would_be_needed: str

    def as_dict(self) -> dict[str, str]:
        return {
            "ref": self.ref,
            "topic": self.topic,
            "status": UNMODELED,
            "reason": self.reason,
            "what_would_be_needed": self.what_would_be_needed,
        }


REGISTER: tuple[UnmodeledItem, ...] = (
    UnmodeledItem(
        ref="U1",
        topic="Funded account simulation (post-Combine trading)",
        reason=(
            "The upstream engine models the Combine only. metrics/economics.py states "
            "'Funded is parked; see docs/ROADMAP.md' and exposes no funded-account rule set, "
            "buffer or drawdown mode. Layer B will not invent one."
        ),
        what_would_be_needed=(
            "An upstream funded-account rule kernel, or a cited funded rulebook with the "
            "same standard of sourcing as quant_brain/markets/futures_cme/topstep.py."
        ),
    ),
    UnmodeledItem(
        ref="U2",
        topic="Express Funded Account (XFA) mechanics",
        reason=(
            "No XFA rules, fees or eligibility logic exist anywhere in the upstream package; "
            "grep finds no reference to it."
        ),
        what_would_be_needed="A cited XFA rulebook and an upstream implementation of it.",
    ),
    UnmodeledItem(
        ref="U3",
        topic="First payout timing and its distribution",
        reason=(
            "Payout requires the funded model that does not exist (U1). EvalEconomics takes "
            "`pass_value` as a scalar the CALLER supplies for what passing is worth - it is "
            "an input, not a simulated payout, and reporting it as one would be circular."
        ),
        what_would_be_needed=(
            "U1 and U2, plus payout minimums, consistency requirements at payout, and the "
            "withdrawal schedule."
        ),
    ),
    UnmodeledItem(
        ref="U4",
        topic="Complete account journey (signup to first withdrawal)",
        reason="Composed entirely of U1-U3; nothing downstream of the Combine is modelled.",
        what_would_be_needed="U1, U2 and U3.",
    ),
    UnmodeledItem(
        ref="U5",
        topic="Exchange holidays and early closes",
        reason=(
            "The upstream package deliberately ships no holiday calendar (data/validator.py: "
            "'There is deliberately no exchange-holiday check'), so a bar on a holiday is "
            "indistinguishable from any other weekday bar. This repository reached the same "
            "conclusion independently and forbids inventing a holiday rule."
        ),
        what_would_be_needed=(
            "A sourced CME holiday and early-close calendar, applied in the canonical data "
            "layer rather than guessed at from bar counts."
        ),
    ),
)


def as_dicts() -> list[dict[str, str]]:
    return [item.as_dict() for item in REGISTER]


def markdown_table() -> str:
    lines = [
        "| ref | topic | status | why | what would be needed |",
        "|---|---|---|---|---|",
    ]
    for item in REGISTER:
        lines.append(
            f"| {item.ref} | {item.topic} | **{UNMODELED}** | {item.reason} | "
            f"{item.what_would_be_needed} |"
        )
    return "\n".join(lines)


__all__ = ["REGISTER", "UNMODELED", "UnmodeledItem", "as_dicts", "markdown_table"]
