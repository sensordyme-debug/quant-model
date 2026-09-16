"""The OCO bracket: one entry, two linked exits, and no way to end up with one of them.

WHAT THIS IS AND IS NOT
-------------------------
This is a SIMULATED order book. It has no network, no credentials and no broker adapter, and
`test_the_order_layer_has_no_transmission_surface` asserts that by inspecting the source. It
exists so the frozen strategy's order semantics can be tested at all - the certified research
path models exits as a scan over bars and never materialises an order object, so there was
nothing to test "the stop and the target are linked" against.

THE THREE FAILURE MODES IT IS BUILT AGAINST
---------------------------------------------
    ORPHAN      a bracket that survives its position. A stop resting under a flat book is an
                order that will one day open a position nobody asked for.
    NAKED       a position whose protective order was never created, or was cancelled and not
                replaced. `core.protection` calls this UNPROTECTED and so does this.
    DUPLICATE   two entries, or two brackets, from one decision - the shape a retry or a
                repeated market-data event takes.

Every mutating call is IDEMPOTENT: calling it twice with the same arguments is the same as
calling it once, and returns the same object. That is not a convenience. A bar that arrives
twice, a callback that fires twice, a restart that replays the last event - all three are
ordinary, and all three are how duplicates get created.

FILL PRICE IS THE ANCHOR
--------------------------
`attach_bracket` takes the fill price and nothing else. It cannot see the signal bar's close,
so it cannot accidentally anchor to it. That is CONFLICT C4 made structural rather than
remembered.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field

from quant_brain.core.execution import Side


class OrderKind(str, enum.Enum):
    MARKET = "market"
    STOP = "stop"
    LIMIT = "limit"


class OrderStatus(str, enum.Enum):
    WORKING = "working"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

    @property
    def is_terminal(self) -> bool:
        return self is not OrderStatus.WORKING


class BracketError(RuntimeError):
    """An order action that would leave the book in a state nobody could defend."""


@dataclass
class Order:
    """One order. `price` is None for a market order and required for a stop or a limit."""

    order_id: str
    kind: OrderKind
    side: Side
    quantity: int
    price: float | None
    status: OrderStatus = OrderStatus.WORKING
    #: The OCO group this order belongs to. Two orders sharing a group cancel each other.
    oco_group: str | None = None
    fill_price: float | None = None
    reason: str = ""

    @property
    def working(self) -> bool:
        return self.status is OrderStatus.WORKING

    def resting_price(self) -> float:
        """The level this order rests at. Raises on a market order, which has none.

        `price` is Optional because a MARKET order genuinely has no price. Every caller that
        reads a stop's or a target's level goes through here, so "the bracket leg had no
        price" becomes a refusal at the moment it is read rather than a `None` flowing into
        the arithmetic that sets the next stop.
        """
        if self.price is None:
            raise BracketError(
                f"{self.order_id} is a {self.kind.value} order and has no resting price")
        return float(self.price)


@dataclass
class Bracket:
    """An entry and its two linked exits. The stop and the target share an OCO group."""

    group: str
    entry: Order
    stop: Order
    target: Order
    fill_price: float
    direction: int
    quantity: int

    @property
    def live(self) -> bool:
        return self.stop.working or self.target.working

    @property
    def protected(self) -> bool:
        """A position is protected only while its STOP is working. A target is not protection."""
        return self.stop.working


@dataclass
class OrderBook:
    """The simulated book. One position at a time, by construction.

    `position` is signed contracts. The book refuses to open a second position while one is
    open, which is the structural half of "no simultaneous long and short" - the FSM refuses
    it too, and both are tested, because a rule enforced in one place is a rule one edit away
    from being enforced nowhere.
    """

    orders: dict[str, Order] = field(default_factory=dict)
    bracket: Bracket | None = None
    position: int = 0
    avg_price: float | None = None
    _seq: int = 0
    #: Every action already applied, keyed by its idempotency token.
    _applied: dict[str, str] = field(default_factory=dict)
    events: list[str] = field(default_factory=list)

    # -- helpers ---------------------------------------------------------------------------

    def _next_id(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}-{self._seq:04d}"

    def _log(self, what: str) -> None:
        self.events.append(what)

    def _once(self, token: str) -> str | None:
        """Idempotency. Returns the id of the earlier application, or None if this is new."""
        return self._applied.get(token)

    # -- entry -----------------------------------------------------------------------------

    def submit_entry(self, *, direction: int, quantity: int, fill_price: float,
                     token: str, reason: str = "signal") -> Order:
        """A market entry that fills immediately at `fill_price`. Idempotent on `token`.

        The caller has already applied slippage to `fill_price`; this layer does not know what
        a signal bar is and must not, or the bracket could be anchored to the wrong number.
        """
        seen = self._once(token)
        if seen is not None:
            return self.orders[seen]
        if self.position != 0:
            raise BracketError(
                f"refusing a second entry while {self.position:+d} is open. One position at a "
                f"time is a property of this engine, not a preference.")
        if direction not in (1, -1):
            raise BracketError(f"direction must be +1 or -1, got {direction}")
        if quantity < 1:
            raise BracketError(f"quantity must be positive, got {quantity}")

        o = Order(order_id=self._next_id("ENTRY"), kind=OrderKind.MARKET,
                  side=Side.BUY if direction > 0 else Side.SELL, quantity=quantity,
                  price=None, status=OrderStatus.FILLED, fill_price=fill_price,
                  reason=reason)
        self.orders[o.order_id] = o
        self._applied[token] = o.order_id
        self.position = direction * quantity
        self.avg_price = fill_price
        self._log(f"ENTRY {o.order_id} {direction:+d}x{quantity} @ {fill_price}")
        return o

    def reject_entry(self, *, token: str, reason: str) -> Order:
        """A rejected entry. Leaves NO position and therefore must leave no bracket."""
        seen = self._once(token)
        if seen is not None:
            return self.orders[seen]
        o = Order(order_id=self._next_id("ENTRY"), kind=OrderKind.MARKET, side=Side.BUY,
                  quantity=0, price=None, status=OrderStatus.REJECTED, reason=reason)
        self.orders[o.order_id] = o
        self._applied[token] = o.order_id
        self._log(f"REJECT {o.order_id} {reason}")
        return o

    # -- bracket ---------------------------------------------------------------------------

    def attach_bracket(self, *, entry: Order, stop_points: float, target_points: float,
                       token: str) -> Bracket:
        """Create the linked STOP and TARGET from the ENTRY'S FILL PRICE. Idempotent.

        Refuses when there is no position: a bracket with nothing to protect is the orphan
        this class exists to prevent.
        """
        if self._once(token) is not None and self.bracket is not None:
            return self.bracket
        if entry.status is not OrderStatus.FILLED or entry.fill_price is None:
            raise BracketError(
                f"cannot bracket {entry.order_id}: status {entry.status.value}. A bracket on "
                f"an unfilled entry is an orphan waiting for a position that never came.")
        if self.position == 0:
            raise BracketError("cannot bracket a flat book")
        if self.bracket is not None and self.bracket.live:
            raise BracketError(
                f"a live bracket {self.bracket.group} already protects this position. A "
                f"second one would double the exit quantity.")

        fill = float(entry.fill_price)
        direction = 1 if entry.side is Side.BUY else -1
        exit_side = Side.SELL if direction > 0 else Side.BUY
        group = self._next_id("OCO")
        stop_px = fill - stop_points * direction
        target_px = fill + target_points * direction

        stop = Order(order_id=self._next_id("STOP"), kind=OrderKind.STOP, side=exit_side,
                     quantity=entry.quantity, price=stop_px, oco_group=group,
                     reason="initial stop")
        target = Order(order_id=self._next_id("TARGET"), kind=OrderKind.LIMIT,
                       side=exit_side, quantity=entry.quantity, price=target_px,
                       oco_group=group, reason="initial target")
        self.orders[stop.order_id] = stop
        self.orders[target.order_id] = target
        self.bracket = Bracket(group=group, entry=entry, stop=stop, target=target,
                               fill_price=fill, direction=direction,
                               quantity=entry.quantity)
        self._applied[token] = group
        self._log(f"BRACKET {group} stop {stop_px} target {target_px} from fill {fill}")
        return self.bracket

    def modify_stop(self, *, price: float, token: str, reason: str) -> Order:
        """Move the stop. Idempotent on `token`, so a repeated break-even cannot double-apply."""
        if self.bracket is None or not self.bracket.stop.working:
            raise BracketError("no working stop to modify")
        if self._once(token) is not None:
            return self.bracket.stop
        self.bracket.stop.price = price
        self.bracket.stop.reason = reason
        self._applied[token] = self.bracket.stop.order_id
        self._log(f"MODIFY STOP {self.bracket.stop.order_id} -> {price} ({reason})")
        return self.bracket.stop

    def modify_target(self, *, price: float, token: str, reason: str) -> Order:
        if self.bracket is None or not self.bracket.target.working:
            raise BracketError("no working target to modify")
        if self._once(token) is not None:
            return self.bracket.target
        self.bracket.target.price = price
        self.bracket.target.reason = reason
        self._applied[token] = self.bracket.target.order_id
        self._log(f"MODIFY TARGET {self.bracket.target.order_id} -> {price} ({reason})")
        return self.bracket.target

    # -- exits -----------------------------------------------------------------------------

    def fill_exit(self, *, which: str, price: float, token: str,
                  reason: str | None = None) -> Order:
        """Fill one leg and CANCEL THE OTHER. That cancellation is what makes it an OCO.

        `which` is "stop", "target" or "flatten". A flatten fills at `price` and cancels both
        resting legs.
        """
        seen = self._once(token)
        if seen is not None:
            return self.orders[seen]
        if self.bracket is None:
            raise BracketError("no bracket to exit")
        b = self.bracket
        if which == "flatten":
            o = Order(order_id=self._next_id("FLAT"), kind=OrderKind.MARKET,
                      side=Side.SELL if b.direction > 0 else Side.BUY,
                      quantity=b.quantity, price=None, status=OrderStatus.FILLED,
                      fill_price=price, oco_group=b.group,
                      reason=reason or "forced flatten")
            self.orders[o.order_id] = o
            self._cancel_leg(b.stop, "cancelled by flatten")
            self._cancel_leg(b.target, "cancelled by flatten")
        else:
            o = b.stop if which == "stop" else b.target
            other = b.target if which == "stop" else b.stop
            if not o.working:
                raise BracketError(f"the {which} is already {o.status.value}")
            o.status = OrderStatus.FILLED
            o.fill_price = price
            if reason:
                o.reason = reason
            self._cancel_leg(other, f"cancelled by the {which} (OCO)")
        self._applied[token] = o.order_id
        self.position = 0
        self.avg_price = None
        self._log(f"EXIT {which} {o.order_id} @ {price}")
        return o

    def _cancel_leg(self, leg: Order, why: str) -> None:
        if leg.working:
            leg.status = OrderStatus.CANCELLED
            leg.reason = why

    def cancel_working(self, *, token: str, reason: str = "cancelled") -> int:
        """Cancel every working order. Idempotent; returns how many were cancelled."""
        if self._once(token) is not None:
            return 0
        n = 0
        for o in self.orders.values():
            if o.working:
                o.status = OrderStatus.CANCELLED
                o.reason = reason
                n += 1
        self._applied[token] = f"cancelled-{n}"
        self._log(f"CANCEL {n} working orders ({reason})")
        return n

    def release(self) -> None:
        """Forget the closed bracket. Refuses while anything is still working or open."""
        if self.position != 0:
            raise BracketError(f"refusing to release a bracket with {self.position:+d} open")
        if self.bracket is not None and self.bracket.live:
            raise BracketError(
                f"refusing to release bracket {self.bracket.group}: a leg is still working. "
                f"That leg is the orphan.")
        self.bracket = None

    # -- invariants -------------------------------------------------------------------------

    def audit(self) -> tuple[str, ...]:
        """Every way the book is currently indefensible. Empty means safe.

        Checked after EVERY bar by the engine, so a violation is caught at the bar that caused
        it rather than at the end of the day when the cause is gone.
        """
        bad: list[str] = []
        working = [o for o in self.orders.values() if o.working]
        if self.position == 0 and working:
            bad.append(f"ORPHAN: flat but {len(working)} orders still working "
                       f"({[o.order_id for o in working]})")
        if self.position != 0:
            if self.bracket is None:
                bad.append("NAKED: open position with no bracket at all")
            elif not self.bracket.protected:
                bad.append(f"NAKED: {self.position:+d} open with no working stop")
        if self.bracket is not None and self.bracket.stop.working \
                and self.bracket.target.working \
                and self.bracket.stop.oco_group != self.bracket.target.oco_group:
            bad.append("UNLINKED: the stop and the target are not in one OCO group")
        if self.bracket is not None and self.position != 0 \
                and abs(self.position) != self.bracket.quantity:
            bad.append(f"QUANTITY: position {self.position:+d} against a bracket for "
                       f"{self.bracket.quantity}")
        return tuple(bad)


__all__ = ["Bracket", "BracketError", "Order", "OrderBook", "OrderKind", "OrderStatus",
           "Side"]
