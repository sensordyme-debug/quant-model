"""Order intent, and the adapter boundary that keeps strategies off broker APIs.

Part 8: "Do not allow strategy code to directly depend on a specific broker API." Today
`paper_trade.py` and `intraday_trader.py` both build `ib_async` objects inline, which is why
neither can be pointed at a prop firm without an edit to the trading loop.

The split this module draws:

    strategy  ->  OrderIntent        what I want to happen, in instrument terms
    risk      ->  OrderIntent'       possibly reduced or rejected, deterministically
    adapter   ->  broker call        the only code that knows what "IBKR" means

`OrderIntent` is the contract. It carries no broker ids, no connection, no account - a
strategy that produced one can be replayed against a simulator, an IBKR adapter or a prop
firm adapter without knowing which.
"""
from __future__ import annotations

import datetime as dt
import enum
from dataclasses import dataclass

from quant_brain.core.instruments import InstrumentSpec


class Side(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"

    @property
    def sign(self) -> int:
        """+1 for a buy, -1 for a sell. Lets position maths avoid an if."""
        return 1 if self is Side.BUY else -1

    @classmethod
    def of(cls, quantity: float) -> Side:
        """The side that a signed quantity implies."""
        return cls.BUY if quantity >= 0 else cls.SELL


class OrderType(str, enum.Enum):
    MARKET = "market"
    LIMIT = "limit"
    #: Flatten-to-zero. Distinguished from MARKET because the risk layer must never reduce or
    #: reject a flatten - AUD-06 and AUD-08 are both cases where a risk or sizing rule
    #: silently suppressed the order that would have closed a position.
    FLATTEN = "flatten"


@dataclass(frozen=True)
class OrderIntent:
    """One thing a strategy wants done, before any venue knows about it.

    Quantity is unsigned and the direction lives in `side`, because a signed quantity plus a
    side is two sources of truth and they drift. `signed_quantity` derives the one number
    position maths wants.
    """

    symbol: str
    side: Side
    quantity: float
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    #: Free-form provenance: which strategy, which sleeve, which experiment. Ends up on the
    #: broker's orderRef so a fill can be attributed back (the intraday sleeve already does
    #: this with orderRef=INTRADAY; this generalises it).
    tag: str = ""
    ts: dt.datetime | None = None

    def __post_init__(self) -> None:
        if self.quantity < 0:
            raise ValueError(
                f"{self.symbol}: OrderIntent.quantity is unsigned ({self.quantity}); "
                f"use side={Side.SELL.value!r} for a sale"
            )
        if self.order_type is OrderType.LIMIT and self.limit_price is None:
            raise ValueError(f"{self.symbol}: LIMIT order without a limit_price")

    @property
    def signed_quantity(self) -> float:
        return self.quantity * self.side.sign

    @property
    def is_flatten(self) -> bool:
        return self.order_type is OrderType.FLATTEN

    def with_quantity(self, quantity: float) -> OrderIntent:
        """A copy at a new size. How the risk layer reduces an order without mutating it.

        Frozen dataclass plus explicit copy means a risk engine cannot accidentally change an
        intent another engine in the chain already inspected.
        """
        return OrderIntent(symbol=self.symbol, side=self.side, quantity=quantity,
                           order_type=self.order_type, limit_price=self.limit_price,
                           tag=self.tag, ts=self.ts)


@dataclass(frozen=True)
class Fill:
    """What actually happened. The simulator and any live adapter both emit these."""

    symbol: str
    side: Side
    quantity: float
    price: float
    commission: float = 0.0
    slippage: float = 0.0
    ts: dt.datetime | None = None
    tag: str = ""

    @property
    def signed_quantity(self) -> float:
        return self.quantity * self.side.sign

    def cost(self) -> float:
        """Total frictional cost of this fill in dollars. Always positive."""
        return abs(self.commission) + abs(self.slippage)


@dataclass
class Position:
    """A running position with average cost, for realized/unrealized attribution.

    Average-cost rather than FIFO lots: prop-firm rules are all stated against account
    equity and daily P&L, none against per-lot tax basis, so lots would be precision nobody
    consumes. Documented because it is a real modelling choice, not an oversight.
    """

    spec: InstrumentSpec
    quantity: float = 0.0          # signed: negative is short
    avg_price: float = 0.0
    realized: float = 0.0

    def apply(self, fill: Fill) -> float:
        """Book a fill. Returns the realized P&L this fill produced (net of its own cost)."""
        q = fill.signed_quantity
        realized = 0.0
        if self.quantity == 0 or (self.quantity > 0) == (q > 0):
            # Opening or adding: weighted-average the cost basis.
            total = self.quantity + q
            if total != 0:
                self.avg_price = (self.avg_price * self.quantity + fill.price * q) / total
            self.quantity = total
        else:
            # Reducing, closing or flipping.
            closing = min(abs(q), abs(self.quantity))
            direction = 1.0 if self.quantity > 0 else -1.0
            realized = (fill.price - self.avg_price) * closing * direction * self.spec.multiplier
            remaining = self.quantity + q
            if (remaining > 0) != (self.quantity > 0) and remaining != 0:
                # Flipped through zero: the residual opens at the fill price.
                self.avg_price = fill.price
            self.quantity = remaining
            if self.quantity == 0:
                self.avg_price = 0.0
        realized -= fill.cost()
        self.realized += realized
        return realized

    def unrealized(self, mark: float) -> float:
        """Mark-to-market P&L at `mark`.

        AUD-05 is the reason this takes an explicit mark and has no default: `Book.pnl` used
        `prices.get(s, 0.0)`, so one missing bar marked a $30k long as a $30k loss and
        flattened the whole book. A caller with no price must decide what that means; it
        must not be able to get a silent zero from here.
        """
        if self.quantity == 0:
            return 0.0
        return (mark - self.avg_price) * self.quantity * self.spec.multiplier
