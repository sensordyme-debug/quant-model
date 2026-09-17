"""The Topstep account profile. Rules we are subject to, not parameters we may tune.

WHERE THE NUMBERS COME FROM
---------------------------
All of them come from the upstream engine, via ``rules.params.combine_params``. This
package does not restate the profit target or the trailing-loss buffer in its own constants,
because a second copy is a second thing to drift. What this module adds is:

  * a VERSIONED IDENTITY, so a result can name the rule set it was judged under;
  * a written statement of the one place upstream and this repository disagree.

THE DISAGREEMENT, STATED PLAINLY
--------------------------------
Passing is not "make $3,000". Upstream requires all three of

    ending balance  >= starting balance + profit target      ($53,000)
    total profit    >  0
    best single day <= consistency_pct * total profit

(``rules/kernel.py``, the ``Verdict.PASSED`` branch). ``combine_params`` hardcodes
``consistency_pct = 0.50``. This repository's own cited rulebook -
``quant_brain/markets/futures_cme/topstep.py``, ``CONSISTENCY_READINGS``, retrieved
2026-09-13 - records the DOCUMENTED reading as 0.55 and lists 0.50 only as a strict
variant.

The two disagree. We do not patch upstream and we do not quietly substitute our own number.
We default to upstream's 0.50, for a reason that can be stated: at a given profit, a lower
percentage caps the best day LOWER, so 0.50 is the HARDER test. Defaulting to it means the
divergence cannot flatter a result. The 0.55 reading is available as a named, non-default
profile so the sensitivity can be measured rather than argued about, and any result produced
under it says so in its manifest.

Concretely, at exactly the $3,000 target: 0.50 caps the best day at $1,500 and 0.55 at
$1,650. A strategy whose best day is $1,600 passes under the repository reading and fails
under upstream's. That gap is a reportable number, not a rounding detail.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from topstep_backtester.upstream import AccountSize, CombineParams, combine_params

#: Bumped when the MEANING of a profile changes, so old results stay identifiable.
PROFILE_SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True)
class AccountProfile:
    """A named, versioned prop-firm rule set, resolvable to upstream ``CombineParams``."""

    profile_id: str
    description: str
    size: AccountSize
    dll_enabled: bool
    #: ``None`` means "whatever upstream's ``combine_params`` says", which is the default
    #: and the only value that needs no justification. A number here is a deliberate
    #: departure and must be explained in ``consistency_basis``.
    consistency_pct_override: Decimal | None
    consistency_basis: str

    def params(self) -> CombineParams:
        """Resolve to the upstream rule object the engine actually enforces."""
        base = combine_params(self.size, dll_enabled=self.dll_enabled)
        if self.consistency_pct_override is None:
            return base
        #: ``msgspec.structs.replace`` on upstream's own frozen struct. This is upstream's
        #: configuration surface being used as intended - not a patch, not a subclass, and
        #: not a recalculation. The kernel still enforces the rule; we only state the rate.
        import msgspec

        return msgspec.structs.replace(base, consistency_pct=self.consistency_pct_override)

    @property
    def consistency_pct(self) -> Decimal:
        return self.params().consistency_pct

    def best_day_cap(self, total_profit: Decimal) -> Decimal:
        """The largest single day that still passes, at a given total profit.

        Provided because "what does the consistency rule actually cost me" is the question
        every sizing decision turns on, and computing it by hand each time invites error.
        """
        return self.consistency_pct * total_profit

    def minimum_profit_for_best_day(self, best_day: Decimal) -> Decimal:
        """The total profit needed before a day this large is permitted.

        The inverse of :meth:`best_day_cap`, and the more useful direction: one $3,100 day
        does not pass a $3,000 target, because it would have to be at most 50% of the total.
        """
        if self.consistency_pct <= 0:  # pragma: no cover - guarded by construction
            raise ValueError("consistency_pct must be positive")
        return best_day / self.consistency_pct

    def as_dict(self) -> dict[str, object]:
        resolved = self.params()
        return {
            "profile_id": self.profile_id,
            "schema_version": PROFILE_SCHEMA_VERSION,
            "description": self.description,
            "size": str(resolved.size),
            "starting_balance": str(resolved.starting_balance),
            "profit_target": str(resolved.profit_target),
            "mll_buffer": str(resolved.mll_buffer),
            "dll": None if resolved.dll is None else str(resolved.dll),
            "max_cap_micro_units": resolved.max_cap_micro_units,
            "consistency_pct": str(resolved.consistency_pct),
            "consistency_basis": self.consistency_basis,
        }


#: THE DEFAULT. Upstream's own reading, unmodified, and the stricter of the two.
TOPSTEP_50K_COMBINE = AccountProfile(
    profile_id="TOPSTEP_50K_COMBINE/v1",
    description=(
        "Topstep $50,000 Combine as the upstream engine enforces it: $3,000 target, "
        "$2,000 trailing MLL that stops trailing once the account is funded-eligible, "
        "no Personal Daily Loss Limit, 5 minis / 50 micros position cap."
    ),
    size=AccountSize.S50K,
    dll_enabled=False,
    consistency_pct_override=None,
    consistency_basis=(
        "upstream rules/params.py hardcodes 0.50; this repository's cited rulebook reads "
        "0.55 (CONSISTENCY_READINGS, retrieved 2026-09-13). 0.50 is the harder test, so "
        "the divergence cannot flatter a result. See UPSTREAM_FINDINGS.md FINDING 1."
    ),
)

#: The repository's documented reading, for measuring the sensitivity. NOT the default.
TOPSTEP_50K_COMBINE_DOC_CONSISTENCY = AccountProfile(
    profile_id="TOPSTEP_50K_COMBINE_DOC55/v1",
    description=(
        "Identical to TOPSTEP_50K_COMBINE except the consistency rate is this repository's "
        "documented 0.55 reading. Exists so the gap between the two readings is a measured "
        "number rather than an argument."
    ),
    size=AccountSize.S50K,
    dll_enabled=False,
    consistency_pct_override=Decimal("0.55"),
    consistency_basis=(
        "quant_brain/markets/futures_cme/topstep.py CONSISTENCY_READINGS doc_calc, basis "
        "total, retrieved 2026-09-13. Looser than upstream's 0.50; any result quoted from "
        "this profile must say so."
    ),
)

#: The only profiles a run may name. A profile not in here has not been reviewed.
PROFILES: dict[str, AccountProfile] = {
    p.profile_id: p for p in (TOPSTEP_50K_COMBINE, TOPSTEP_50K_COMBINE_DOC_CONSISTENCY)
}


def get_profile(profile_id: str) -> AccountProfile:
    if profile_id not in PROFILES:
        raise KeyError(
            f"unknown account profile {profile_id!r}; known profiles are {sorted(PROFILES)}"
        )
    return PROFILES[profile_id]


__all__ = [
    "PROFILES",
    "PROFILE_SCHEMA_VERSION",
    "TOPSTEP_50K_COMBINE",
    "TOPSTEP_50K_COMBINE_DOC_CONSISTENCY",
    "AccountProfile",
    "get_profile",
]
