"""The IBKR execution adapter: the one place that knows what `ib_async` is.

Everything this class does was previously inline in `scripts/intraday_trader.py`'s
`LiveExecutor.submit`. Moving it behind `ExecutionAdapter` is what makes a second venue
reachable, and the behaviour is deliberately preserved to the field: same `orderRef`, same
`outsideRth=False`, same explicit `tif`.

THREE DETAILS THAT LOOK LIKE NOISE AND ARE NOT
-----------------------------------------------
Each of these is a defect this repository has already paid for once.

`tif` is set explicitly. An empty TIF makes IBKR emit informational code 10349, which
`ib_async` mislabels as a cancellation - on 2026-09-10 that marked live orders Cancelled
while they filled normally seconds later.

`outsideRth=False` is set explicitly, and the caller is expected to refuse submissions
outside regular hours BEFORE reaching this adapter. With this flag an order sent outside RTH
is queued to the next open where nothing is tracking it (AUD-08/09).

`working()` reports what is REMAINING, computed from executions rather than from the status
flag. A half-filled order has half its size still on the wire, and a sizer that nets the
submitted amount doubles up (AUD-06). The status flag lied on 2026-09-10; `fills` did not.
"""
from __future__ import annotations

from quant_brain.core.execution import Ack, ExecutionAdapter, OrderIntent, OrderType, Side


class IBKRAdapter(ExecutionAdapter):
    """Places orders through a connected `ib_async` IB instance.

    `contracts` maps symbol -> a qualified contract object. Qualification is the caller's
    job because it is a connection-time concern and doing it per order would add a round
    trip to the hot path.
    """

    name = "ibkr"

    def __init__(self, ib, contracts: dict, *, order_ref: str = "",
                 outside_rth: bool = False, tif: str = "DAY"):
        self.ib = ib
        self.contracts = contracts
        self.order_ref = order_ref
        self.outside_rth = outside_rth
        self.tif = tif
        self.open: list = []

    # -- construction ---------------------------------------------------------------------

    def _order(self, intent: OrderIntent):
        return build_ib_order(intent, order_ref=self.order_ref,
                              outside_rth=self.outside_rth, tif=self.tif)

    # -- the boundary ---------------------------------------------------------------------

    def submit(self, intent: OrderIntent) -> Ack:
        contract = self.contracts.get(intent.symbol)
        if contract is None:
            # Not an exception: an unqualified symbol is an ordinary venue-level refusal and
            # the caller needs the other intents in the batch to still go.
            return Ack(intent=intent, accepted=False,
                       reason=f"no qualified contract for {intent.symbol}")
        try:
            trade = self.ib.placeOrder(contract, self._order(intent))
        except Exception as exc:                                        # noqa: BLE001
            return Ack(intent=intent, accepted=False,
                       reason=f"{type(exc).__name__}: {exc}")
        self.open.append(trade)
        return Ack(intent=intent, accepted=True,
                   broker_id=str(getattr(trade.order, "orderId", "")), handle=trade)

    def working(self) -> dict[str, float]:
        """Signed quantity still outstanding per symbol, from executions. AUD-06."""
        out: dict[str, float] = {}
        for tr in self.open:
            done = float(sum(f.execution.shares for f in tr.fills))
            left = float(tr.order.totalQuantity) - done
            if left <= 1e-9:
                continue
            sign = 1 if tr.order.action == "BUY" else -1
            sym = tr.contract.symbol
            out[sym] = out.get(sym, 0.0) + left * sign
        return {s: q for s, q in out.items() if q}

    def cancel_all(self) -> int:
        """Cancel every order this adapter placed that is still working."""
        n = 0
        for tr in self.open:
            done = float(sum(f.execution.shares for f in tr.fills))
            if done >= float(tr.order.totalQuantity) - 1e-9:
                continue
            try:
                self.ib.cancelOrder(tr.order)
                n += 1
            except Exception:                                           # noqa: BLE001, S110
                pass    # a cancel that fails is reported by the venue, not raised here
        return n


def build_ib_order(intent: OrderIntent, *, order_ref: str = "",
                   outside_rth: bool = False, tif: str = "DAY"):
    """Translate one `OrderIntent` into the `ib_async` order object IBKR expects.

    A module-level function rather than an adapter method because two callers need it: the
    adapter, and `scripts/paper_trade.py`'s `build_order` shim, whose tests pin the exact
    objects for MKT, MOC and MOO. Keeping one construction site means those tests certify
    the adapter's output too.

    The auction types carry their own TIF and it wins over the adapter default: IBKR has no
    "MOO" order type at all - an opening-auction order is a plain MKT with tif="OPG", and a
    closing-auction order is orderType="MOC" with an ordinary DAY tif.
    """
    from ib_async import LimitOrder, MarketOrder, Order

    action = "BUY" if intent.side is Side.BUY else "SELL"
    qty = abs(intent.quantity)
    own_tif = None

    if intent.order_type is OrderType.LIMIT:
        if intent.limit_price is None:
            raise ValueError(f"{intent.symbol}: LIMIT intent without a limit price")
        o = LimitOrder(action, qty, intent.limit_price)
    elif intent.order_type is OrderType.MARKET_ON_CLOSE:
        o = Order(action=action, totalQuantity=qty, orderType="MOC", tif="DAY")
        own_tif = "DAY"
    elif intent.order_type is OrderType.MARKET_ON_OPEN:
        o = Order(action=action, totalQuantity=qty, orderType="MKT", tif="OPG")
        own_tif = "OPG"
    else:
        # MARKET and FLATTEN. The venue has no concept of "flatten" and inventing one here
        # would be a second meaning for the same wire message; the distinction lives in the
        # risk layer, which must not reduce it.
        o = MarketOrder(action, qty)

    o.orderRef = intent.tag or order_ref
    o.outsideRth = outside_rth
    o.tif = own_tif or tif
    return o
