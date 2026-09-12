"""Per-market worker allocation.

Part 6: `plan_workers` has to stop being a capability and become part of the orchestration,
with Futures leading, Options in parallel, and the inactive branches consuming nothing.

The property that matters most is the one-directional clamp. A helper that could RAISE a
worker count would be silently reshaping an experiment, and a helper researchers do not trust
gets deleted. It may only lower.
"""
from __future__ import annotations

import dataclasses

import pytest

from quant_brain.core.instruments import AssetClass
from quant_brain.core.resources import GB, ResourceSnapshot, plan_workers
from quant_brain.core.scheduler import (
    MARKETS,
    Allocation,
    Market,
    Priority,
    allocate,
    resolve_workers,
    workers_for,
)


def snap(*, avail=48 * GB, limit=72 * GB, committed=10 * GB, cpu=16):
    return ResourceSnapshot(total_phys=64 * GB, avail_phys=avail, commit_limit=limit,
                            commit_avail=limit - committed, cpu_count=cpu)


def budget(n_cpu=16, **kw):
    return plan_workers(600.0, snap=snap(cpu=n_cpu, **kw))


# ------------------------------------------------------------------ policy: who is active

def test_the_active_markets_are_futures_options_and_equity():
    active = {k for k, m in MARKETS.items() if m.active}
    assert active == {"futures", "options", "equity"}


def test_the_scaffold_markets_are_off_not_merely_deprioritised():
    for name in ("etf", "bitcoin", "crypto"):
        assert MARKETS[name].priority is Priority.OFF
        assert MARKETS[name].priority.value == 0


def test_futures_and_options_are_both_high():
    assert MARKETS["futures"].priority is Priority.HIGH
    assert MARKETS["options"].priority is Priority.HIGH


# ------------------------------------------------------------------ the split

def test_an_inactive_market_gets_exactly_zero():
    alloc = allocate(budget=budget())
    for name in ("etf", "bitcoin", "crypto"):
        assert alloc.for_market(name) == 0


def test_futures_is_never_allocated_less_than_options():
    """Futures is the capital-building engine; equal priority must not let Options exceed it."""
    for cpu in range(4, 33):
        alloc = allocate(budget=budget(n_cpu=cpu))
        assert alloc.for_market("futures") >= alloc.for_market("options"), cpu


def test_every_active_market_gets_at_least_one_worker_when_the_budget_allows():
    alloc = allocate(budget=budget())
    for name in ("futures", "options", "equity"):
        assert alloc.for_market(name) >= 1


def test_a_tiny_budget_goes_to_the_highest_priority_first():
    tiny = plan_workers(600.0, max_workers=2, snap=snap())
    alloc = allocate(budget=tiny)
    assert alloc.total == 2
    assert alloc.for_market("futures") == 1
    assert alloc.for_market("options") == 1
    assert alloc.for_market("equity") == 0        # NORMAL loses to two HIGHs


def test_the_split_never_exceeds_the_machine_budget():
    for cpu in range(2, 65):
        alloc = allocate(budget=budget(n_cpu=cpu))
        assert sum(alloc.per_market.values()) <= alloc.total


def test_no_worker_is_lost_to_rounding():
    for cpu in range(4, 40):
        alloc = allocate(budget=budget(n_cpu=cpu))
        assert sum(alloc.per_market.values()) == alloc.total, cpu


def test_the_split_is_deterministic():
    b = budget()
    assert allocate(budget=b).per_market == allocate(budget=b).per_market


def test_all_markets_off_allocates_nothing():
    off = {k: Market(k, AssetClass.EQUITY, Priority.OFF) for k in ("a", "b")}
    alloc = allocate(off, budget=budget())
    assert sum(alloc.per_market.values()) == 0


# ------------------------------------------------ policy cannot override the measurement

def test_commit_pressure_shrinks_every_market_including_futures():
    """The safety-critical property: policy divides the budget, it never raises it."""
    starved = plan_workers(900.0, snap=snap(avail=34 * GB, limit=83 * GB,
                                            committed=int(81.5 * GB)))
    assert starved.limited_by == "commit" and starved.workers == 1
    alloc = allocate(budget=starved)
    assert alloc.total == 1
    assert sum(alloc.per_market.values()) == 1
    assert alloc.for_market("futures") == 1       # the one worker goes to the priority branch


def test_the_budget_is_computed_against_the_heaviest_active_market():
    """Options workers are budgeted at 900 MB; using an average would under-reserve."""
    alloc = allocate()
    assert alloc.budget.detail  # the reason is always carried
    assert max(m.worker_mb for m in MARKETS.values() if m.active) == 900.0


# ------------------------------------------------------------------ the clamp

def test_resolve_workers_lowers_an_oversized_request():
    assert resolve_workers(1000, "futures", verbose=False) <= workers_for("futures")


def test_resolve_workers_respects_a_smaller_request(monkeypatch):
    """Ask for 2 and get 2 - the helper must not reshape an experiment upward.

    The budget is pinned to `snap()` instead of the live machine. Read off the machine this
    assertion is a coin flip: `resolve_workers` clamps to `workers_for("futures")`, which on
    2026-09-12 was **1** at 81% commit charge, so "ask for 2 and get 2" is false whenever
    another track is sweeping - and this suite gates the 09:25 launch (E-8).
    """
    import quant_brain.core.scheduler as sched
    monkeypatch.setattr(sched, "plan_workers",
                        lambda *a, **k: plan_workers(600.0, snap=snap()))
    assert resolve_workers(2, "futures", verbose=False) == 2


def test_resolve_workers_never_raises_a_request_on_the_live_machine():
    """The one-directional clamp against whatever this box actually has free right now.

    This is the half of the property that survives contact with a loaded machine, so it is
    the half allowed to look at one.
    """
    for want in (1, 2, 4, 8):
        assert 1 <= resolve_workers(want, "futures", verbose=False) <= want


def test_resolve_workers_never_returns_zero_for_an_active_market():
    assert resolve_workers(0, "futures", verbose=False) >= 1
    assert resolve_workers(None, "futures", verbose=False) >= 1


def test_resolve_workers_returns_zero_for_an_inactive_market():
    for name in ("etf", "bitcoin", "crypto"):
        assert resolve_workers(8, name, verbose=False) == 0


def test_resolve_workers_is_monotonic():
    prev = 0
    for want in (1, 2, 3, 4, 5, 6, 100):
        got = resolve_workers(want, "futures", verbose=False)
        assert got >= prev
        prev = got


def test_workers_for_rejects_an_unknown_market():
    with pytest.raises(KeyError, match="known:"):
        workers_for("dogecoin")


def test_allocation_describe_names_the_limiting_resource_and_the_off_markets():
    text = allocate(budget=budget()).describe()
    assert "limited by" in text
    assert "off:" in text and "crypto" in text


def test_allocation_is_a_frozen_record():
    """FrozenInstanceError specifically: `Exception` would also pass on a typo'd attribute."""
    alloc = allocate(budget=budget())
    assert isinstance(alloc, Allocation)
    with pytest.raises(dataclasses.FrozenInstanceError):
        alloc.total = 99            # type: ignore[misc]
