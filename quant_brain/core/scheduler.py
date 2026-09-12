"""Who gets the machine, and how much of it.

Part 6 of the architecture brief: `plan_workers` must stop being a capability and become
part of the actual research orchestration, with per-market priority so Futures leads while
Options continues in parallel and the inactive branches consume essentially nothing.

WHY A SEPARATE MODULE FROM `resources`
---------------------------------------
`resources` answers a machine question - how many workers can this box carry right now
without pushing Windows into allocation failure. That answer is the same whoever is asking.
This module answers a policy question - given that budget, who gets it. Keeping them apart
means the measurement cannot be quietly bent by the policy, which matters because the
measurement is the safety-critical half: on 2026-09-12 the machine sat at 98% commit charge
with 34.7 GB of physical RAM still free, and a policy that could override the commit leg
would have authorised roughly 35 more workers into a box two gigabytes from failure.

THE ALLOCATION RULE
-------------------
Shares are proportional to priority weight among the ACTIVE markets only, with two floors
that matter more than the proportions:

  * every active market gets at least one worker, so a HIGH/HIGH split never starves one
    branch to zero just because the machine is small;
  * an OFF market gets exactly zero, and is not merely deprioritised - Part 24 is explicit
    that inactive branches must not consume research compute.

The remainder after integer division goes to the highest-priority market, so on an odd
budget Futures gets the extra worker rather than it being lost to rounding.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass

from quant_brain.core.instruments import AssetClass
from quant_brain.core.resources import WorkerBudget, plan_workers


class Priority(int, enum.Enum):
    """How much of the research machine a market may claim.

    An int mixin so weights compare and sum directly. OFF is zero rather than a small
    number: "a little bit of crypto research" is exactly the drift Part 27 warns about.
    """

    OFF = 0
    LOW = 1
    NORMAL = 2
    HIGH = 4

    @property
    def active(self) -> bool:
        return self is not Priority.OFF


@dataclass(frozen=True)
class Market:
    """A research branch and its claim on the machine."""

    name: str
    asset_class: AssetClass
    priority: Priority
    #: Peak RSS of one worker for this market, in MB. Measured, not guessed: a `sweep_a8`
    #: multiprocessing child was observed at ~590 MB. Options workers hold 0DTE chain
    #: parquet and run heavier, so they are budgeted higher until measured otherwise.
    worker_mb: float = 600.0

    @property
    def active(self) -> bool:
        return self.priority.active


#: The current policy, straight from Part 24's priority list. Futures is the capital-building
#: engine and leads; Options continues in parallel; the rest are architectural scaffolds and
#: get nothing. Changing a market's status is a one-line edit here, which is the point -
#: activating a branch should be a visible decision, not an emergent one.
MARKETS: dict[str, Market] = {
    "futures": Market("futures", AssetClass.FUTURE, Priority.HIGH, worker_mb=600.0),
    "options": Market("options", AssetClass.OPTION, Priority.HIGH, worker_mb=900.0),
    "equity":  Market("equity", AssetClass.EQUITY, Priority.NORMAL, worker_mb=600.0),
    "etf":     Market("etf", AssetClass.ETF, Priority.OFF),
    "bitcoin": Market("bitcoin", AssetClass.CRYPTO, Priority.OFF),
    "crypto":  Market("crypto", AssetClass.CRYPTO, Priority.OFF),
}


@dataclass(frozen=True)
class Allocation:
    """The machine budget, split by market."""

    total: int
    per_market: dict[str, int]
    budget: WorkerBudget

    def for_market(self, name: str) -> int:
        return self.per_market.get(name.lower(), 0)

    def describe(self) -> str:
        rows = ", ".join(f"{k}={v}" for k, v in sorted(self.per_market.items()) if v)
        off = ", ".join(sorted(k for k, v in self.per_market.items() if not v))
        return (f"{self.total} worker(s) limited by {self.budget.limited_by}"
                f" | {rows or 'none'}" + (f" | off: {off}" if off else ""))


def allocate(markets: dict[str, Market] | None = None, *,
             max_workers: int | None = None,
             budget: WorkerBudget | None = None) -> Allocation:
    """Split the machine's safe worker budget across the active markets.

    The budget comes from `resources.plan_workers`, which takes the minimum of what physical
    memory, Windows commit charge and CPU allow. Policy divides that number; it never raises
    it. `per_worker_mb` for the whole-machine budget is the heaviest active market's, so the
    ceiling is computed against the worst case rather than an average that under-reserves.
    """
    markets = markets or MARKETS
    active = {k: m for k, m in markets.items() if m.active}
    per_market = {k: 0 for k in markets}
    if not active:
        return Allocation(0, per_market,
                          budget or plan_workers(600.0, max_workers=max_workers))

    heaviest = max(m.worker_mb for m in active.values())
    budget = budget or plan_workers(heaviest, max_workers=max_workers)
    total = budget.workers

    # One worker each first: an active branch must never be starved to zero by rounding.
    if total <= len(active):
        for k in sorted(active, key=lambda k: (-active[k].priority.value, k))[:total]:
            per_market[k] = 1
        return Allocation(total, per_market, budget)

    for k in active:
        per_market[k] = 1
    left = total - len(active)
    weights = {k: m.priority.value for k, m in active.items()}
    denom = sum(weights.values()) or 1
    for k, w in weights.items():
        per_market[k] += (left * w) // denom
    # Remainder to the highest priority, tie-broken by name so the split is deterministic.
    spare = total - sum(per_market.values())
    order = sorted(active, key=lambda k: (-weights[k], k))
    for i in range(spare):
        per_market[order[i % len(order)]] += 1
    return Allocation(total, per_market, budget)


def workers_for(market: str, *, max_workers: int | None = None) -> int:
    """The worker count a research job for `market` should actually use.

    This is the one call a sweep needs. It replaces a hard-coded `--workers N`, and it is
    what turns the resource manager from a capability into part of the orchestration.

        workers = workers_for("futures")
        with Pool(workers) as pool: ...

    Returns at least 1 for an active market and exactly 0 for an inactive one, so a caller
    that ignores the zero is doing so visibly.
    """
    name = market.lower()
    m = MARKETS.get(name)
    if m is None:
        raise KeyError(f"unknown market {market!r}; known: {', '.join(sorted(MARKETS))}")
    if not m.active:
        return 0
    return allocate(max_workers=max_workers).for_market(name)


def resolve_workers(requested: int | None, market: str = "equity", *,
                    verbose: bool = True) -> int:
    """Clamp a requested worker count to what the machine can currently carry.

    The adoption path for the fifteen sweeps that hard-code `--workers` at 4, 6 or 8 and
    consult nothing:

        ap.add_argument("--workers", type=int, default=6)
        ...
        workers = resolve_workers(args.workers, "futures")

    It is deliberately one-directional: it can only LOWER a request, never raise one. A
    researcher who asks for 2 gets 2. That matters for trust - a helper that silently
    increases parallelism would be changing an experiment's shape, and a helper people do not
    trust gets removed. What it prevents is the other direction: on 2026-09-12 three
    concurrent `sweep_a8 --workers 11` put this machine at 98% commit charge with 34.7 GB of
    physical RAM still apparently free, roughly two gigabytes from allocation failures, and
    the gateway watchdog then misread the resulting slow gateway binds as failures and
    restarted it four times.

    An inactive market returns 0, and the caller should treat that as "do not run".
    """
    m = MARKETS.get(market.lower())
    if m is not None and not m.active:
        if verbose:
            print(f"[scheduler] {market} is OFF; refusing to allocate workers")
        return 0
    try:
        allowed = workers_for(market) if m is not None else int(plan_workers(600.0))
    except Exception:  # noqa: BLE001 - a scheduling hiccup must not stop research
        return max(1, int(requested or 1))
    want = int(requested) if requested else allowed
    out = max(1, min(want, allowed))
    if verbose and out < want:
        print(f"[scheduler] {market}: requested {want} worker(s), machine allows {allowed} "
              f"-> using {out}")
    return out


def _main(argv: list[str] | None = None) -> int:
    """`python -m quant_brain.core.scheduler` - the current split, on this machine."""
    import argparse

    ap = argparse.ArgumentParser(description="Per-market research worker allocation.")
    ap.add_argument("--max-workers", type=int, default=None)
    ap.add_argument("--market", default=None, help="print just this market's worker count")
    args = ap.parse_args(argv)

    if args.market:
        print(workers_for(args.market, max_workers=args.max_workers))
        return 0

    alloc = allocate(max_workers=args.max_workers)
    print(alloc.budget.snapshot.describe())
    print(alloc.describe())
    print()
    for name in sorted(MARKETS, key=lambda k: (-MARKETS[k].priority.value, k)):
        m = MARKETS[name]
        n = alloc.for_market(name)
        note = "" if m.active else "  (inactive - architectural scaffold only)"
        print(f"  {name:<9} {m.priority.name:<7} {n:>3} worker(s)"
              f"  ~{n * m.worker_mb / 1024:.1f} GB{note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
