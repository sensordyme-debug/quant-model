"""The strategy registry. It is empty, and keeping it empty is the point.

WHY EMPTY IS A FEATURE
----------------------
A research pipeline that starts with a dozen inherited candidates loaded is a pipeline that
will eventually report the best of them. That is selection, and selection across a drawer of
old ideas is indistinguishable from optimisation no matter how principled each individual
backtest was. So this pipeline starts at zero and the owner adds one, deliberately, by name.

There is no auto-discovery here. No ``pkgutil.walk_packages``, no glob over a strategies
directory, no "load everything in the registry and rank it". Those are the mechanisms by
which a drawer refills itself, and their absence is deliberate rather than unfinished.

THE NAMED EXCLUSIONS
--------------------
The repository contains earlier work - VWAP pullback, opening-range breakout, initial
balance reversion, failed-reversal studies, mechanism scorecards, and the candidates from
previous research phases. None of it may be registered here. Not because it was bad work,
but because its results are already known, and a strategy whose results you already know is
not something you can test - you can only confirm it. Two of those bodies of work reached a
documented negative conclusion and one reached YELLOW; carrying them forward into a fresh
pipeline would launder those conclusions into a new-looking result.

``FORBIDDEN_LINEAGES`` makes that refusal mechanical rather than a matter of remembering.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator

from topstep_backtester.strategies.spec import FrozenStrategySpec, SpecError

#: Substrings of a strategy name that identify prior work in this repository. Matching is
#: case-insensitive and on the normalised name, so "VWAP_Pullback" and "vwap-pullback" are
#: both caught.
FORBIDDEN_LINEAGES: tuple[str, ...] = (
    "vwap",
    "orb",
    "opening_range",
    "initial_balance",
    "ib_reversion",
    "failed_reversal",
    "mechanism",
    "scorecard",
    "champion",
    "optimi",
)

#: name -> (spec, factory). EMPTY BY DESIGN. See the module docstring before adding to it.
ACTIVE_STRATEGIES: dict[str, tuple[FrozenStrategySpec, Callable[..., object]]] = {}

#: Every spec ever registered in this process, by spec_hash, whether or not it is still
#: active. Unregistering removes a strategy from ACTIVE_STRATEGIES and NOT from here.
#:
#: WHY IT DOES NOT FORGET
#: A strategy that was tested and withdrawn was still tested. The count of distinct
#: hypotheses tried is what any multiple-testing correction needs, and a ledger that
#: shrinks when you remove a candidate would report a smaller family than was actually
#: examined - which is the direction that makes a marginal result look significant.
GENEALOGY: dict[str, dict[str, str]] = {}


class RegistryError(RuntimeError):
    """A strategy that may not be registered."""


def _normalise(name: str) -> str:
    return name.lower().replace("-", "_").replace(" ", "_")


def check_lineage(name: str) -> None:
    """Refuse a name that belongs to prior work in this repository."""
    normalised = _normalise(name)
    for excluded in FORBIDDEN_LINEAGES:
        if excluded in normalised:
            raise RegistryError(
                f"{name!r} matches the excluded lineage {excluded!r}. Previous research in "
                f"this repository already reached a documented conclusion about it, and "
                f"re-running a known result in a fresh pipeline reports confirmation as "
                f"discovery. If the owner genuinely intends to retest it, that is a "
                f"deliberate decision that belongs in the prompt, not a default."
            )


def register(
    spec: FrozenStrategySpec,
    factory: Callable[..., object],
    *,
    acknowledge_single_candidate: bool = False,
) -> None:
    """Add the owner's strategy. One at a time, frozen, with its lineage checked.

    ``acknowledge_single_candidate`` must be passed explicitly once a strategy is already
    registered. Holding two candidates at once is how a pipeline drifts into ranking them,
    so the second one requires the caller to say out loud that they mean it.
    """
    spec.assert_runnable()
    check_lineage(spec.name)
    if spec.name in ACTIVE_STRATEGIES:
        raise RegistryError(
            f"{spec.name!r} is already registered with hash "
            f"{ACTIVE_STRATEGIES[spec.name][0].spec_hash}. Re-registering under the same "
            f"name would make two different experiments share an identity."
        )
    if ACTIVE_STRATEGIES and not acknowledge_single_candidate:
        raise RegistryError(
            f"{sorted(ACTIVE_STRATEGIES)} already registered. This pipeline tests one "
            f"strategy at a time on purpose: a registry holding several invites a ranking, "
            f"and the best of N backtests is not an out-of-sample result. Pass "
            f"acknowledge_single_candidate=True if the owner has decided otherwise."
        )
    ACTIVE_STRATEGIES[spec.name] = (spec, factory)
    GENEALOGY[spec.spec_hash] = {
        "name": spec.name,
        "version": spec.version,
        "spec_id": spec.spec_id,
        "derived_from": spec.derived_from,
        "derivation_reason": spec.derivation_reason,
        "frozen_at": spec.frozen_at,
        "author": spec.author,
    }


def unregister(name: str) -> None:
    ACTIVE_STRATEGIES.pop(name, None)


def clear() -> None:
    """Empty the ACTIVE registry. The genealogy ledger is deliberately untouched.

    Use :func:`reset_genealogy` if you really mean to forget what was tried - which outside
    a test means claiming fewer hypotheses were examined than actually were.
    """
    ACTIVE_STRATEGIES.clear()


def reset_genealogy() -> None:
    """Forget every spec ever registered. For test isolation only."""
    GENEALOGY.clear()


def lineage(spec_hash: str) -> tuple[str, ...]:
    """The chain of ancestors of a spec, nearest parent first.

    Walks ``derived_from`` through the genealogy ledger. Stops at an unknown parent, so a
    chain whose ancestor was registered in another process is truncated rather than
    fabricated.
    """
    chain: list[str] = []
    seen: set[str] = {spec_hash}
    current = GENEALOGY.get(spec_hash, {}).get("derived_from", "")
    while current and current not in seen:
        chain.append(current)
        seen.add(current)
        current = GENEALOGY.get(current, {}).get("derived_from", "")
    return tuple(chain)


def family_size(spec_hash: str) -> int:
    """How many distinct specs share a root with this one, including itself.

    The number a multiple-testing correction needs: testing the eleventh variant of one idea
    is not the same as testing the first, and a p-value that ignores the other ten is not a
    p-value.
    """
    def root_of(candidate: str) -> str:
        chain = lineage(candidate)
        return chain[-1] if chain else candidate

    root = root_of(spec_hash)
    return sum(1 for known in GENEALOGY if root_of(known) == root) or 1


def hypotheses_examined() -> int:
    """Total distinct specs ever registered in this process."""
    return len(GENEALOGY)


def get(name: str) -> tuple[FrozenStrategySpec, Callable[..., object]]:
    if name not in ACTIVE_STRATEGIES:
        raise RegistryError(
            f"no strategy named {name!r} is registered. ACTIVE_STRATEGIES is "
            f"{sorted(ACTIVE_STRATEGIES)}; this pipeline does not auto-discover strategies, "
            f"so one must be registered explicitly before it can run."
        )
    return ACTIVE_STRATEGIES[name]


def count() -> int:
    return len(ACTIVE_STRATEGIES)


def iter_specs() -> Iterator[FrozenStrategySpec]:
    for spec, _ in ACTIVE_STRATEGIES.values():
        yield spec


def assert_empty() -> None:
    """The state this package ships in, asserted by the certification tests."""
    if ACTIVE_STRATEGIES:
        raise RegistryError(
            f"ACTIVE_STRATEGIES should be empty in the shipped pipeline but holds "
            f"{sorted(ACTIVE_STRATEGIES)}"
        )


__all__ = [
    "ACTIVE_STRATEGIES",
    "FORBIDDEN_LINEAGES",
    "GENEALOGY",
    "RegistryError",
    "SpecError",
    "assert_empty",
    "check_lineage",
    "clear",
    "count",
    "get",
    "family_size",
    "hypotheses_examined",
    "iter_specs",
    "lineage",
    "register",
    "reset_genealogy",
    "unregister",
]
