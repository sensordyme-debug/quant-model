"""Bracket verification: a position is protected only when its stop is proven to exist.

Phase 9 of the master directive. The rule is simple and every execution system that has lost
money on it agrees on it afterwards:

    POSITION OPEN + STOP UNKNOWN  ->  UNPROTECTED  ->  the configured fail-safe, now

"Unknown" covers every case that is not a verified, acknowledged, correctly-sided,
correctly-sized, correctly-priced protective order. A stop that was SUBMITTED is unknown. A
stop the strategy BELIEVES it placed is unknown. A stop for the wrong quantity protects the
wrong position. A stop on the wrong side of the entry is not a stop.

WHY VERIFICATION IS A FUNCTION OF WORKING ORDERS, NOT OF INTENT
----------------------------------------------------------------
`verify()` takes what the VENUE reports as working - not what the process sent. The
difference is the entire content of this module. A process that checks its own outbox has
verified that it tried; only the venue's working-order list verifies that it succeeded, and the
gap between those two is where naked exposure lives.
"""
from __future__ import annotations

import enum
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from quant_brain.core.execution import Side


class ProtectionState(str, enum.Enum):
    FLAT = "flat"                  # no position; nothing to protect
    PROTECTED = "protected"        # a verified stop covers the whole position
    PENDING = "pending"            # a stop is submitted but not yet acknowledged
    UNPROTECTED = "unprotected"    # open exposure with no verified stop. Act now.


@dataclass(frozen=True)
class WorkingOrder:
    """An order the venue says is live. Built from the venue's report, never from intent."""

    order_id: str
    symbol: str
    side: Side
    quantity: float
    kind: str                      # "stop" | "limit" | "market" | "stop_limit"
    stop_price: float | None = None
    limit_price: float | None = None
    acknowledged: bool = False
    #: Optional linkage the venue may report (OCO group, parent id). Absent is fine; wrong
    #: is what `verify` catches through side/qty/price rather than trusting the link.
    linked_to: str | None = None


@dataclass(frozen=True)
class ProtectionVerdict:
    state: ProtectionState
    reasons: tuple[str, ...] = ()
    covering: tuple[str, ...] = ()       # order ids that count as protection
    covered_qty: float = 0.0
    naked_qty: float = 0.0

    @property
    def safe(self) -> bool:
        return self.state in (ProtectionState.FLAT, ProtectionState.PROTECTED)

    def describe(self) -> str:
        why = f" - {'; '.join(self.reasons)}" if self.reasons else ""
        return f"{self.state.value} covered {self.covered_qty:g} naked {self.naked_qty:g}{why}"


def verify(*, symbol: str, position: float, avg_price: float | None,
           working: Sequence[WorkingOrder], require_target: bool = False,
           tick: float = 0.0) -> ProtectionVerdict:
    """Is this position protected by what the venue reports as working?

    A stop counts only if ALL of these hold:
      * it is a stop-type order on the same symbol
      * it is ACKNOWLEDGED - submitted is not enough
      * its side closes the position (sell for a long, buy for a short)
      * its stop price is on the protective side of the average entry
        (below for a long, above for a short); a stop above a long is a buy-stop that adds
      * summed across such orders, the quantity covers the whole position

    Anything short of all of them is reported with the specific reason, because "unprotected"
    on its own sends an operator looking in the wrong place.
    """
    if not position:
        return ProtectionVerdict(ProtectionState.FLAT)

    closing_side = Side.SELL if position > 0 else Side.BUY
    need = abs(position)
    reasons: list[str] = []
    covering: list[str] = []
    covered = 0.0
    pending = 0.0

    same = [w for w in working if w.symbol == symbol]
    stops = [w for w in same if w.kind in ("stop", "stop_limit")]
    if not stops:
        reasons.append("no stop-type order is working for this symbol")

    for w in stops:
        if w.side is not closing_side:
            reasons.append(f"{w.order_id}: stop is on the {w.side.value} side, which does not "
                           f"close a {'long' if position > 0 else 'short'}")
            continue
        if w.stop_price is None:
            reasons.append(f"{w.order_id}: stop has no stop price")
            continue
        if avg_price is not None:
            bad = (position > 0 and w.stop_price >= avg_price - tick) or \
                  (position < 0 and w.stop_price <= avg_price + tick)
            if bad:
                reasons.append(
                    f"{w.order_id}: stop {w.stop_price} is not on the protective side of the "
                    f"{avg_price} entry for a {'long' if position > 0 else 'short'}")
                continue
        if not w.acknowledged:
            pending += w.quantity
            reasons.append(f"{w.order_id}: stop is submitted but not acknowledged")
            continue
        covering.append(w.order_id)
        covered += w.quantity

    if covered >= need - 1e-9:
        if require_target:
            targets = [w for w in same if w.kind == "limit" and w.side is closing_side
                       and w.acknowledged]
            if sum(t.quantity for t in targets) < need - 1e-9:
                reasons.append("target required but no acknowledged closing limit covers the "
                               "position")
                return ProtectionVerdict(ProtectionState.UNPROTECTED, tuple(reasons),
                                         tuple(covering), covered, 0.0)
        return ProtectionVerdict(ProtectionState.PROTECTED, tuple(reasons), tuple(covering),
                                 covered, 0.0)

    naked = need - covered
    if pending >= naked - 1e-9 and covered + pending >= need - 1e-9:
        return ProtectionVerdict(ProtectionState.PENDING, tuple(reasons), tuple(covering),
                                 covered, naked)
    if covered > 0:
        reasons.append(f"stops cover {covered:g} of {need:g}; {naked:g} is naked")
    return ProtectionVerdict(ProtectionState.UNPROTECTED, tuple(reasons), tuple(covering),
                             covered, naked)


@dataclass
class ProtectionMonitor:
    """Watches verdicts and invokes the fail-safe the moment one is UNPROTECTED.

    The fail-safe is injected. The default is to request a flatten through whatever callable
    the caller supplies, and to trip the governor's BRACKET_UNVERIFIED switch so nothing new
    opens until a person has looked. Both happen on the FIRST unprotected verdict; there is no
    grace period, because the grace period is the exposure.
    """

    on_unprotected: Callable[[str, ProtectionVerdict], None]
    on_pending_too_long: Callable[[str, ProtectionVerdict], None] | None = None
    pending_grace: int = 3                # consecutive PENDING checks before escalation
    _pending_counts: dict[str, int] = field(default_factory=dict)
    fired: list[tuple[str, ProtectionState]] = field(default_factory=list)

    def check(self, symbol: str, verdict: ProtectionVerdict) -> ProtectionVerdict:
        if verdict.state is ProtectionState.UNPROTECTED:
            self.fired.append((symbol, verdict.state))
            self.on_unprotected(symbol, verdict)
            self._pending_counts.pop(symbol, None)
        elif verdict.state is ProtectionState.PENDING:
            n = self._pending_counts.get(symbol, 0) + 1
            self._pending_counts[symbol] = n
            if n >= self.pending_grace:
                # A stop that stays unacknowledged is a stop that is not there.
                self.fired.append((symbol, verdict.state))
                (self.on_pending_too_long or self.on_unprotected)(symbol, verdict)
        else:
            self._pending_counts.pop(symbol, None)
        return verdict
