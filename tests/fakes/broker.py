"""A fake broker: an in-process venue that can be made to behave badly on purpose.

WHY A FAKE AND NOT A STUB
-------------------------
Order transmission is frozen (`ORDER_TRANSMISSION_ENABLED = False` in both runners and in
`quant_brain/brokers/projectx.py`), so the execution path cannot be exercised against a real
venue and must not be. The alternative that teaches nothing is a stub that accepts every
order and reports whatever the caller already believes: it turns every invariant into a
tautology. `quant_brain.core.execution.SimulatedAdapter` is close to that by design - it
accepts everything, never fills, and reports its own outbox as `working()`.

This fake is the opposite. Everything that a real venue does badly is a method:

    submit()                 records EVERY order it receives, with a monotonically
                             increasing broker id, including the ones it rejects
    fill()                   fills on demand, fully or partially, at a price the test picks
    fill(drop=True)          books the fill at the venue and NEVER tells the client - the
                             state that makes a restart dangerous
    fill(echo=True)          delivers the same fill message twice, booking it once
    reject                   a venue refusal, returned as an Ack rather than raised
    set_position()           the broker holds something the local book never opened, so
                             reconciliation has a real disagreement to catch
    place_out_of_band()      an order that appeared at the venue without passing through
                             the executor (a manual stop in the platform, a bracket leg),
                             which is what `core.protection` is written to verify against

THE TWO LEDGERS ARE KEPT APART
------------------------------
`fills` is what the BROKER booked. `delivered` is what the CLIENT was told. A dropped fill
is in the first and not the second, and that gap is the whole subject of the restart and
reconciliation tests - a fake with one list cannot express it.

`positions` is the broker's own truth and is never derived from anything the client says.
That is what lets `snapshot()` be handed to `core.reconcile.reconcile` as the broker side of
a genuine comparison.

Standard library only, no network, no clock of its own beyond an injectable one.
"""
from __future__ import annotations

import datetime as dt
import enum
import itertools
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from quant_brain.core.execution import (
    Ack,
    ExecutionAdapter,
    Fill,
    OrderIntent,
    OrderType,
    Side,
)
from quant_brain.core.mode import Mode
from quant_brain.core.protection import WorkingOrder
from quant_brain.core.reconcile import OrderRef, Snapshot

#: A fixed, timezone-aware instant so a test that does not care about time need not invent
#: one. `Snapshot.as_of` refuses a naive datetime, which is the correct refusal and is why
#: this constant is aware.
EPOCH = dt.datetime(2026, 9, 14, 14, 30, tzinfo=dt.UTC)


class OrderStatus(str, enum.Enum):
    WORKING = "working"
    PARTIAL = "partial"
    FILLED = "filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"

    @property
    def open(self) -> bool:
        """Is this order still capable of filling? The definition `working()` depends on."""
        return self in (OrderStatus.WORKING, OrderStatus.PARTIAL)


@dataclass
class BrokerOrder:
    """One order as the VENUE sees it. Not an intent: an intent has no id and no fill state."""

    broker_id: str
    intent: OrderIntent
    status: OrderStatus = OrderStatus.WORKING
    filled: float = 0.0
    avg_price: float = 0.0
    #: "market" | "limit" | "stop" | "stop_limit". Derived from the intent for anything the
    #: executor can express, and set explicitly by `place_out_of_band` for anything it
    #: cannot - which today includes every protective stop, since `OrderType` has no STOP.
    kind: str = "market"
    stop_price: float | None = None
    acknowledged: bool = True
    reason: str = ""

    @property
    def remaining(self) -> float:
        """Unsigned quantity still on the wire. Zero once filled, rejected or cancelled."""
        if not self.status.open:
            return 0.0
        return max(0.0, self.intent.quantity - self.filled)

    @property
    def signed_remaining(self) -> float:
        return self.remaining * self.intent.side.sign

    def as_order_ref(self) -> OrderRef:
        """The venue-neutral shape `core.reconcile` compares."""
        return OrderRef(symbol=self.intent.symbol, side=self.intent.side.value,
                        quantity=self.remaining, kind=self.kind)

    def as_working_order(self) -> WorkingOrder:
        """The shape `core.protection.verify` consumes. Built from the VENUE's record."""
        return WorkingOrder(order_id=self.broker_id, symbol=self.intent.symbol,
                            side=self.intent.side, quantity=self.remaining, kind=self.kind,
                            stop_price=self.stop_price,
                            limit_price=self.intent.limit_price,
                            acknowledged=self.acknowledged)


_KIND_FOR = {
    OrderType.MARKET: "market",
    OrderType.MARKET_ON_CLOSE: "market",
    OrderType.MARKET_ON_OPEN: "market",
    OrderType.FLATTEN: "market",
    OrderType.LIMIT: "limit",
}


@dataclass(eq=False)
class FakeBroker(ExecutionAdapter):
    """An in-process venue with its own position book, its own order book, and no network.

    Subclasses `ExecutionAdapter` so it plugs into the real `RoutedExecutor` unchanged: the
    point of the exercise is to drive PRODUCTION routing, risk and journalling code, and a
    fake that needed an adapter shim would be testing the shim.
    """

    name: str = "fake"
    #: In-memory. BACKTEST is the honest floor - nothing leaves the process - and it is
    #: deliberately not RESEARCH, so a research-authority process still cannot build a path
    #: to this object. Matches `SimulatedAdapter`.
    requires: Mode = Mode.BACKTEST

    #: Symbols the venue refuses outright.
    reject: set[str] = field(default_factory=set)
    reject_reason: str = "fake venue rejection"
    equity: float | None = None

    #: Every order the venue received, in arrival order, rejections included.
    orders: list[BrokerOrder] = field(default_factory=list)
    by_id: dict[str, BrokerOrder] = field(default_factory=dict)
    #: Every fill the BROKER booked.
    fills: list[Fill] = field(default_factory=list)
    #: Every fill message the CLIENT was handed. A dropped fill is absent here.
    delivered: list[Fill] = field(default_factory=list)
    #: Booked but never delivered. The restart hazard, made countable.
    dropped: list[Fill] = field(default_factory=list)
    #: The venue's own position book. Never derived from anything the client asserts.
    positions: dict[str, float] = field(default_factory=dict)
    avg_price: dict[str, float] = field(default_factory=dict)

    _ids: itertools.count = field(default_factory=lambda: itertools.count(1), repr=False)
    _listeners: list[Callable[[Fill], None]] = field(default_factory=list, repr=False)

    # -- the ExecutionAdapter contract ---------------------------------------------------

    def submit(self, intent: OrderIntent) -> Ack:
        """Record the order, then accept or refuse it. Never raises for a venue refusal."""
        broker_id = f"fake-{next(self._ids)}"
        order = BrokerOrder(broker_id=broker_id, intent=intent,
                            kind=_KIND_FOR.get(intent.order_type, "market"))
        self.orders.append(order)
        self.by_id[broker_id] = order
        if intent.symbol in self.reject:
            order.status = OrderStatus.REJECTED
            order.reason = self.reject_reason
            return Ack(intent=intent, accepted=False, broker_id=broker_id,
                       reason=self.reject_reason, handle=order)
        return Ack(intent=intent, accepted=True, broker_id=broker_id, handle=order)

    def working(self) -> dict[str, float]:
        """Signed quantity still OUTSTANDING per symbol - remaining, not submitted.

        The distinction the `ExecutionAdapter` docstring insists on (AUD-06): a half-filled
        order has half its size still on the wire, and an adapter that reports the submitted
        amount makes a netting sizer double up.
        """
        out: dict[str, float] = {}
        for o in self.orders:
            if o.status.open:
                out[o.intent.symbol] = out.get(o.intent.symbol, 0.0) + o.signed_remaining
        return {k: v for k, v in out.items() if v}

    def cancel_all(self) -> int:
        n = 0
        for o in self.orders:
            if o.status.open:
                o.status = OrderStatus.CANCELLED
                n += 1
        return n

    def cancel(self, broker_id: str) -> bool:
        o = self.by_id.get(broker_id)
        if o is None or not o.status.open:
            return False
        o.status = OrderStatus.CANCELLED
        return True

    # -- fills ---------------------------------------------------------------------------

    def on_fill(self, callback: Callable[[Fill], None]) -> None:
        """Subscribe to fill MESSAGES. A dropped fill never reaches a subscriber."""
        self._listeners.append(callback)

    def fill(self, broker_id: str | None = None, *, quantity: float | None = None,
             price: float, commission: float = 0.0, drop: bool = False,
             echo: bool = False, ts: dt.datetime | None = None) -> Fill:
        """Fill an order, fully or partially, at `price`.

        `broker_id` defaults to the oldest open order, which is what a test that has sent
        exactly one order wants. `quantity` defaults to the whole remaining size.

        `drop=True` books the fill at the venue and delivers no message - the venue and the
        client now disagree and nothing has told the client so. `echo=True` delivers the
        same message twice while booking it once, which is the duplicate-fill case a client
        that keys off messages rather than off state gets wrong.
        """
        order = self._resolve(broker_id)
        qty = order.remaining if quantity is None else float(quantity)
        if qty <= 0:
            raise ValueError(f"{order.broker_id}: nothing left to fill")
        if qty > order.remaining + 1e-9:
            raise ValueError(f"{order.broker_id}: asked to fill {qty:g} of {order.remaining:g}")

        prior = order.filled
        order.filled = prior + qty
        order.avg_price = ((order.avg_price * prior + price * qty) / order.filled
                           if order.filled else price)
        order.status = (OrderStatus.FILLED
                        if order.remaining <= 1e-9 else OrderStatus.PARTIAL)

        fill = Fill(symbol=order.intent.symbol, side=order.intent.side, quantity=qty,
                    price=price, commission=commission, ts=ts or EPOCH,
                    tag=order.intent.tag)
        self._book(fill)
        self.fills.append(fill)
        if drop:
            self.dropped.append(fill)
        else:
            self._deliver(fill)
            if echo:
                self._deliver(fill)
        return fill

    def fill_all(self, *, price: float, **kw) -> list[Fill]:
        """Fill every open order completely. Returns the fills, in order."""
        return [self.fill(o.broker_id, price=price, **kw)
                for o in list(self.orders) if o.status.open]

    def _resolve(self, broker_id: str | None) -> BrokerOrder:
        if broker_id is not None:
            order = self.by_id.get(broker_id)
            if order is None:
                raise KeyError(f"no such order at the fake venue: {broker_id}")
            return order
        for o in self.orders:
            if o.status.open:
                return o
        raise LookupError("no open order to fill")

    def _deliver(self, fill: Fill) -> None:
        self.delivered.append(fill)
        for cb in self._listeners:
            cb(fill)

    def _book(self, fill: Fill) -> None:
        """Move the VENUE's own position. Average cost, matching `execution.Position`."""
        sym = fill.symbol
        q0 = self.positions.get(sym, 0.0)
        q = fill.signed_quantity
        if q0 == 0 or (q0 > 0) == (q > 0):
            total = q0 + q
            if total:
                self.avg_price[sym] = ((self.avg_price.get(sym, 0.0) * q0 + fill.price * q)
                                       / total)
            self.positions[sym] = total
        else:
            remaining = q0 + q
            if remaining and (remaining > 0) != (q0 > 0):
                self.avg_price[sym] = fill.price
            self.positions[sym] = remaining
            if remaining == 0:
                self.avg_price.pop(sym, None)

    # -- making the venue disagree -------------------------------------------------------

    def set_position(self, symbol: str, quantity: float, *,
                     avg_price: float | None = None) -> None:
        """Give the venue a position no order of ours created.

        Someone else traded the account, a bracket leg filled, a previous process left a
        position behind. `core.reconcile` calls this an UNEXPLAINED_POSITION, and the
        correct response to one is to stop - which is what the tests assert.
        """
        self.positions[symbol] = quantity
        if avg_price is not None:
            self.avg_price[symbol] = avg_price
        elif not quantity:
            self.avg_price.pop(symbol, None)

    def place_out_of_band(self, *, symbol: str, side: Side, quantity: float, kind: str,
                          stop_price: float | None = None, limit_price: float | None = None,
                          acknowledged: bool = True) -> BrokerOrder:
        """An order that exists at the venue without having passed through the executor.

        Needed because `OrderIntent` cannot express a stop: `core.execution.OrderType` has
        MARKET, LIMIT, MOC, MOO and FLATTEN and no stop of any kind, so a protective order
        cannot be routed through `RoutedExecutor` at all. `core.protection.verify` is
        written entirely in terms of stops the venue reports, so without this method the
        module could never be exercised against anything but an empty list.
        """
        broker_id = f"fake-{next(self._ids)}"
        intent = OrderIntent(symbol=symbol, side=side, quantity=quantity,
                             order_type=(OrderType.LIMIT if kind == "limit"
                                         else OrderType.MARKET),
                             limit_price=limit_price if kind == "limit" else None)
        order = BrokerOrder(broker_id=broker_id, intent=intent, kind=kind,
                            stop_price=stop_price, acknowledged=acknowledged)
        self.orders.append(order)
        self.by_id[broker_id] = order
        return order

    # -- what the venue reports ----------------------------------------------------------

    def open_orders(self) -> list[BrokerOrder]:
        return [o for o in self.orders if o.status.open]

    def open_positions(self) -> dict[str, float]:
        """Signed contracts the VENUE holds. The truth about what EXISTS."""
        return {s: q for s, q in self.positions.items() if q}

    def order_refs(self) -> dict[str, OrderRef]:
        """Open orders keyed by broker id, as `core.reconcile` wants them."""
        return {o.broker_id: o.as_order_ref() for o in self.open_orders()}

    def protection_orders(self, symbol: str | None = None) -> Sequence[WorkingOrder]:
        """Open orders as `core.protection.verify` wants them."""
        return [o.as_working_order() for o in self.open_orders()
                if symbol is None or o.intent.symbol == symbol]

    def snapshot(self, as_of: dt.datetime | None = None, *,
                 equity: float | None = None) -> Snapshot:
        """The broker side of a reconciliation, built only from the venue's own records."""
        return Snapshot(positions=self.open_positions(), working=self.order_refs(),
                        as_of=as_of or EPOCH,
                        equity=self.equity if equity is None else equity,
                        source=self.name)

    # -- convenience for assertions ------------------------------------------------------

    def symbols_ordered(self) -> list[str]:
        return [o.intent.symbol for o in self.orders]

    def quantities_ordered(self) -> list[float]:
        """Signed quantity of every order the venue received, in arrival order."""
        return [o.intent.signed_quantity for o in self.orders]

    def accepted(self) -> list[BrokerOrder]:
        return [o for o in self.orders if o.status is not OrderStatus.REJECTED]


class DisconnectedBroker(FakeBroker):
    """A venue that takes the order and then loses the connection before acknowledging.

    Distinct from a rejection: a rejection is a known outcome, this is an UNKNOWN one, and
    the two must not be journalled the same way. `IntentJournal` leaves the intent SUBMITTED
    for `recover()` to find, which is the behaviour under test.
    """

    def submit(self, intent: OrderIntent) -> Ack:
        super().submit(intent)          # the venue DID receive it - that is the whole point
        raise ConnectionError("connection lost after the order was sent")


def local_snapshot(positions: dict[str, float] | None = None,
                   working: dict[str, OrderRef] | None = None, *,
                   as_of: dt.datetime | None = None,
                   equity: float | None = None) -> Snapshot:
    """The local side of a reconciliation. A plain constructor, kept next to its counterpart."""
    return Snapshot(positions=dict(positions or {}), working=dict(working or {}),
                    as_of=as_of or EPOCH, equity=equity, source="local")


def symbols_of(orders: Iterable[BrokerOrder]) -> list[str]:
    return [o.intent.symbol for o in orders]
