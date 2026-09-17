"""Recompute the money from the fills, using nothing but the contract terms.

THE METHOD
----------
Walk the fill events in order, keeping a signed position and a running average entry price.
When a fill reduces the position, book the closed quantity at the difference between its
price and the average entry, converted to dollars through the tick table:

    points   = exit_price - entry_price          (signed by direction)
    ticks    = points / tick_size
    dollars  = ticks * tick_value * closed_qty

That is it. No Decimal helpers borrowed from upstream, no fee model, no position object, no
lot tracker - the costs are summed straight off the fills the engine reported charging.

WHY AVERAGE ENTRY AND NOT FIFO
------------------------------
Upstream tracks FIFO lots. This module averages. For any position opened and closed in one
lot - which every trade in a one-contract strategy is - the two give identical answers, and
where they differ the difference is itself informative: a mismatch on a scaled position
means the two layers disagree about lot accounting, which is exactly the kind of thing a
reconciliation is supposed to surface rather than paper over. The report says which case it
is instead of quietly matching.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ReferenceFill:
    """One fill, reduced to the four facts the arithmetic needs."""

    side: str
    size: int
    price: Decimal
    costs: Decimal

    @property
    def direction(self) -> int:
        if self.side.upper() == "BUY":
            return 1
        if self.side.upper() == "SELL":
            return -1
        raise ValueError(f"unknown fill side {self.side!r}")


@dataclass(frozen=True)
class ReferenceRoundTrip:
    direction: int
    qty: int
    entry_price: Decimal
    exit_price: Decimal
    gross_pnl: Decimal
    costs: Decimal

    @property
    def net_pnl(self) -> Decimal:
        return self.gross_pnl - self.costs


@dataclass(frozen=True)
class ReferenceLedger:
    """The independent answer, plus enough detail to locate a disagreement."""

    round_trips: tuple[ReferenceRoundTrip, ...]
    gross_pnl: Decimal
    costs: Decimal
    net_pnl: Decimal
    scaled_positions_seen: bool
    unclosed_qty: int

    def as_dict(self) -> dict[str, object]:
        return {
            "round_trips": len(self.round_trips),
            "gross_pnl": str(self.gross_pnl),
            "costs": str(self.costs),
            "net_pnl": str(self.net_pnl),
            "scaled_positions_seen": self.scaled_positions_seen,
            "unclosed_qty": self.unclosed_qty,
        }


def reference_ledger(
    fills: Sequence[ReferenceFill], *, tick_size: Decimal, tick_value: Decimal
) -> ReferenceLedger:
    """The whole independent calculation. Deliberately small enough to read in one sitting."""
    if tick_size <= 0 or tick_value <= 0:
        raise ValueError("tick_size and tick_value must both be positive")

    position = 0
    avg_entry = Decimal(0)
    trips: list[ReferenceRoundTrip] = []
    total_costs = Decimal(0)
    total_gross = Decimal(0)
    scaled = False

    for fill in fills:
        total_costs += fill.costs
        signed = fill.direction * fill.size

        if position == 0 or (position > 0) == (signed > 0):
            #: opening or adding. Weighted average, which is where a scaled position would
            #: start to diverge from FIFO.
            if position != 0:
                scaled = True
            new_position = position + signed
            avg_entry = (
                (avg_entry * abs(position) + fill.price * fill.size) / abs(new_position)
                if new_position != 0
                else Decimal(0)
            )
            position = new_position
            continue

        #: reducing. Book the overlap.
        closing = min(abs(position), fill.size)
        direction = 1 if position > 0 else -1
        points = (fill.price - avg_entry) * direction
        gross = (points / tick_size) * tick_value * closing
        total_gross += gross
        trips.append(
            ReferenceRoundTrip(
                direction=direction,
                qty=closing,
                entry_price=avg_entry,
                exit_price=fill.price,
                gross_pnl=gross,
                costs=Decimal(0),
            )
        )
        remainder = fill.size - closing
        position += direction * -closing
        if remainder:
            #: the fill flipped the position through flat
            scaled = True
            position = fill.direction * remainder
            avg_entry = fill.price
        elif position == 0:
            avg_entry = Decimal(0)

    return ReferenceLedger(
        round_trips=tuple(trips),
        gross_pnl=total_gross,
        costs=total_costs,
        net_pnl=total_gross - total_costs,
        scaled_positions_seen=scaled,
        unclosed_qty=position,
    )


@dataclass(frozen=True)
class Reconciliation:
    """What the two independent answers said, and whether they agreed."""

    engine_gross: Decimal
    engine_costs: Decimal
    engine_net: Decimal
    reference_gross: Decimal
    reference_costs: Decimal
    reference_net: Decimal
    scaled_positions_seen: bool
    unclosed_qty: int

    @property
    def gross_delta(self) -> Decimal:
        return self.engine_gross - self.reference_gross

    @property
    def net_delta(self) -> Decimal:
        return self.engine_net - self.reference_net

    @property
    def agrees(self) -> bool:
        #: Exact equality, not a tolerance. Both sides work in Decimal on a tick grid, so
        #: there is no float error to absorb - a penny of disagreement is a real disagreement
        #: about what happened, and a tolerance would hide exactly the bug worth finding.
        return self.gross_delta == 0 and self.net_delta == 0

    def as_dict(self) -> dict[str, object]:
        return {
            "engine_gross": str(self.engine_gross),
            "engine_costs": str(self.engine_costs),
            "engine_net": str(self.engine_net),
            "reference_gross": str(self.reference_gross),
            "reference_costs": str(self.reference_costs),
            "reference_net": str(self.reference_net),
            "gross_delta": str(self.gross_delta),
            "net_delta": str(self.net_delta),
            "agrees": self.agrees,
            "scaled_positions_seen": self.scaled_positions_seen,
            "unclosed_qty": self.unclosed_qty,
        }


__all__ = [
    "Reconciliation",
    "ReferenceFill",
    "ReferenceLedger",
    "ReferenceRoundTrip",
    "reference_ledger",
]
