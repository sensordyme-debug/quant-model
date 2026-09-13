"""Startup and periodic reconciliation: compare what we believe with what the venue says, and
halt on any difference.

Phase 8 of the master directive. `brokers/projectx.reconcile()` already refuses to return an
empty position set when it cannot ask the venue; that is the right refusal but it is only a
refusal. This is the engine: two `Snapshot`s in, a `ReconcileResult` out, and the result
either clears the reconciliation preconditions in `lifecycle.Readiness` or trips the
governor's `POSITION_UNRECONCILED` switch and says exactly what differed.

WHICH SIDE IS THE TRUTH
-----------------------
Neither, and that is the point of comparing. The venue is the truth about what EXISTS - a
position the broker holds is real whether or not the process remembers opening it. Local
state is the truth about what was INTENDED - an order the process never sent cannot be
explained by anything the process did. So every difference is reported in both directions:

    position the broker holds that local does not  -> unexplained position (someone or
                                                      something else traded this account)
    position local holds that the broker does not  -> phantom position (a fill was assumed)
    quantity differs                                -> partial fill or duplicate that was missed
    working order at the broker not in local        -> unexplained order
    working order in local not at the broker        -> missing order; if it was a stop the
                                                      position is naked (protection.py)
    equity differs beyond tolerance                 -> P&L accounting is wrong somewhere
    either snapshot older than `max_age`            -> stale; cannot conclude anything

None of these is auto-corrected. "Adopt the broker's view" sounds reasonable until the
broker's view includes a position a bug opened; "adopt local" is worse. A person decides,
after reading the discrepancy list, and until then nothing new opens. Flatten still works -
the governor never blocks it.
"""
from __future__ import annotations

import datetime as dt
import enum
from collections.abc import Mapping
from dataclasses import dataclass, field

from quant_brain.core.governor import Governor, Reason


class DiscrepancyKind(str, enum.Enum):
    UNEXPLAINED_POSITION = "unexplained_position"    # broker has it, local does not
    PHANTOM_POSITION = "phantom_position"            # local has it, broker does not
    QUANTITY_MISMATCH = "quantity_mismatch"
    UNEXPLAINED_ORDER = "unexplained_order"          # broker has it, local does not
    MISSING_ORDER = "missing_order"                  # local has it, broker does not
    ORDER_MISMATCH = "order_mismatch"                # same id, different content
    EQUITY_MISMATCH = "equity_mismatch"
    STALE = "stale"
    UNAVAILABLE = "unavailable"                      # one side could not report at all


@dataclass(frozen=True)
class OrderRef:
    """The parts of a working order that reconciliation compares. Venue-neutral."""

    symbol: str
    side: str
    quantity: float
    kind: str = ""          # "stop" | "limit" | ... - matters for the protection consequence


@dataclass(frozen=True)
class Snapshot:
    """One side's belief at one instant. Positions are signed contracts."""

    positions: Mapping[str, float]
    working: Mapping[str, OrderRef]
    as_of: dt.datetime
    equity: float | None = None
    source: str = ""

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None:
            raise ValueError("Snapshot.as_of must be timezone-aware")


@dataclass(frozen=True)
class Discrepancy:
    kind: DiscrepancyKind
    key: str
    local: object
    broker: object
    detail: str

    def describe(self) -> str:
        return (f"{self.kind.value} {self.key}: local={self.local!r} broker={self.broker!r} "
                f"- {self.detail}")


@dataclass(frozen=True)
class ReconcileResult:
    ok: bool
    discrepancies: tuple[Discrepancy, ...] = ()
    checked_at: dt.datetime | None = None

    @property
    def unexplained_orders(self) -> bool:
        return any(d.kind in (DiscrepancyKind.UNEXPLAINED_ORDER, DiscrepancyKind.MISSING_ORDER,
                              DiscrepancyKind.ORDER_MISMATCH) for d in self.discrepancies)

    @property
    def unexplained_positions(self) -> bool:
        return any(d.kind in (DiscrepancyKind.UNEXPLAINED_POSITION,
                              DiscrepancyKind.PHANTOM_POSITION,
                              DiscrepancyKind.QUANTITY_MISMATCH) for d in self.discrepancies)

    @property
    def missing_stops(self) -> list[Discrepancy]:
        """Local believed a stop was working and the broker does not have it. Naked."""
        return [d for d in self.discrepancies
                if d.kind is DiscrepancyKind.MISSING_ORDER
                and isinstance(d.local, OrderRef) and d.local.kind in ("stop", "stop_limit")]

    def readiness_fields(self) -> dict[str, bool]:
        """The four `lifecycle.Readiness` fields this result is allowed to assert."""
        return {
            "local_state_reconciled": self.ok,
            "broker_state_reconciled": self.ok,
            "no_unexplained_orders": not self.unexplained_orders,
            "no_unexplained_positions": not self.unexplained_positions,
        }

    def describe(self) -> str:
        if self.ok:
            return "reconciled: local and broker agree"
        return "NOT reconciled:\n  " + "\n  ".join(d.describe() for d in self.discrepancies)


def reconcile(local: Snapshot, broker: Snapshot, *, now: dt.datetime,
              max_age: dt.timedelta = dt.timedelta(seconds=30),
              equity_tolerance: float = 0.0, qty_tolerance: float = 0.0) -> ReconcileResult:
    """Compare. Every difference is a discrepancy; any discrepancy is a failure.

    `equity_tolerance` exists because two sides can legitimately mark a position at prices
    a tick apart; it defaults to zero so that a caller has to decide what slack is honest.
    """
    out: list[Discrepancy] = []

    for name, snap in (("local", local), ("broker", broker)):
        age = now - snap.as_of
        if age > max_age:
            out.append(Discrepancy(DiscrepancyKind.STALE, name, local.as_of.isoformat(),
                                   broker.as_of.isoformat(),
                                   f"{name} snapshot is {age.total_seconds():.0f}s old, "
                                   f"limit {max_age.total_seconds():.0f}s"))
    if out:
        # Cannot compare stale state; a match would not mean anything and a mismatch would
        # send someone chasing a difference that may have already resolved.
        return ReconcileResult(False, tuple(out), now)

    # --- positions --------------------------------------------------------------------
    lp = {k: v for k, v in local.positions.items() if v}
    bp = {k: v for k, v in broker.positions.items() if v}
    for sym in sorted(set(lp) | set(bp)):
        lq, bq = lp.get(sym, 0.0), bp.get(sym, 0.0)
        if abs(lq - bq) <= qty_tolerance:
            continue
        if not lq:
            out.append(Discrepancy(DiscrepancyKind.UNEXPLAINED_POSITION, sym, 0.0, bq,
                                   "the broker holds a position this process did not open"))
        elif not bq:
            out.append(Discrepancy(DiscrepancyKind.PHANTOM_POSITION, sym, lq, 0.0,
                                   "this process believes it holds a position the broker "
                                   "does not have"))
        else:
            out.append(Discrepancy(DiscrepancyKind.QUANTITY_MISMATCH, sym, lq, bq,
                                   "same symbol, different size; a missed partial fill or a "
                                   "duplicate"))

    # --- working orders ---------------------------------------------------------------
    for oid in sorted(set(local.working) | set(broker.working)):
        lo, bo = local.working.get(oid), broker.working.get(oid)
        if lo is None:
            assert bo is not None
            out.append(Discrepancy(DiscrepancyKind.UNEXPLAINED_ORDER, oid, None, bo,
                                   "the broker has a working order this process did not send"))
        elif bo is None:
            what = "a protective stop" if lo.kind in ("stop", "stop_limit") else "an order"
            out.append(Discrepancy(DiscrepancyKind.MISSING_ORDER, oid, lo, None,
                                   f"this process believes {what} is working; the broker has "
                                   f"no such order"))
        elif (lo.symbol, lo.side, lo.kind) != (bo.symbol, bo.side, bo.kind) or \
                abs(lo.quantity - bo.quantity) > qty_tolerance:
            out.append(Discrepancy(DiscrepancyKind.ORDER_MISMATCH, oid, lo, bo,
                                   "same order id, different content"))

    # --- equity -----------------------------------------------------------------------
    if local.equity is None or broker.equity is None:
        if local.equity is not None or broker.equity is not None:
            out.append(Discrepancy(DiscrepancyKind.UNAVAILABLE, "equity", local.equity,
                                   broker.equity, "one side cannot report equity"))
    elif abs(local.equity - broker.equity) > equity_tolerance:
        out.append(Discrepancy(DiscrepancyKind.EQUITY_MISMATCH, "equity", local.equity,
                               broker.equity,
                               f"differ by {abs(local.equity - broker.equity):,.2f}, tolerance "
                               f"{equity_tolerance:,.2f}"))

    return ReconcileResult(not out, tuple(out), now)


@dataclass
class Reconciler:
    """Runs `reconcile` and applies the consequence to a `Governor`.

    A failure trips `POSITION_UNRECONCILED`; a missing stop additionally trips
    `BRACKET_UNVERIFIED`, because that discrepancy is not an accounting question, it is
    open exposure. A pass does NOT reset either switch - a switch that a later clean
    reconciliation resets is a switch that a transient agreement can clear before a person
    has looked at why it tripped.
    """

    governor: Governor
    max_age: dt.timedelta = dt.timedelta(seconds=30)
    equity_tolerance: float = 0.0
    history: list[ReconcileResult] = field(default_factory=list)

    def run(self, local: Snapshot, broker: Snapshot, *, now: dt.datetime) -> ReconcileResult:
        r = reconcile(local, broker, now=now, max_age=self.max_age,
                      equity_tolerance=self.equity_tolerance)
        self.history.append(r)
        if not r.ok:
            self.governor.trip(Reason.POSITION_UNRECONCILED, r.describe())
            if r.missing_stops:
                self.governor.trip(Reason.BRACKET_UNVERIFIED,
                                   "; ".join(d.describe() for d in r.missing_stops))
        return r

    @property
    def last(self) -> ReconcileResult | None:
        return self.history[-1] if self.history else None
