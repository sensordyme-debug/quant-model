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

import abc
import datetime as dt
import enum
from dataclasses import dataclass
from typing import TYPE_CHECKING

from quant_brain.core.instruments import InstrumentSpec

if TYPE_CHECKING:  # pragma: no cover
    # Import-time circular: risk.py imports OrderIntent from here. The dependency
    # only exists for the type checker, which is the honest shape - this module
    # defines the boundary and does not need the risk layer to run.
    from quant_brain.core.risk import RiskDecision, RiskEngine


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
    #: Auction orders. Real, venue-independent order types rather than IBKR spellings:
    #: every equity and futures venue has an opening and a closing auction, and a strategy
    #: that wants the close should be able to say so without knowing that IBKR encodes the
    #: opening auction as a plain MKT carrying tif="OPG".
    MARKET_ON_CLOSE = "moc"
    MARKET_ON_OPEN = "moo"
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


# =====================================================================================
# THE ADAPTER BOUNDARY
# =====================================================================================

@dataclass(frozen=True)
class Ack:
    """What a venue said about one intent. The only thing an adapter returns.

    Deliberately not a `Fill`: acceptance and execution are different events, and conflating
    them is how a runner comes to believe a queued order is a done trade. AUD-06 was exactly
    that confusion at the position level; this keeps the two nouns apart at the boundary.
    """

    intent: OrderIntent
    accepted: bool
    broker_id: str = ""
    reason: str = ""
    #: Whatever the adapter wants to hand back for reconciliation - an ib_async Trade, a
    #: simulator record. Opaque to everything above the adapter, which is the point.
    handle: object | None = None

    def __str__(self) -> str:
        head = f"{self.intent.side.value} {self.intent.quantity:g} {self.intent.symbol}"
        return (f"{head} -> {self.broker_id or 'accepted'}" if self.accepted
                else f"{head} -> REJECTED {self.reason}")


class ExecutionAdapter(abc.ABC):
    """The only place that knows what a specific broker is.

    Everything above this class speaks `OrderIntent` and `Ack`. That is what makes a second
    venue - a prop firm, a simulator, a different broker - reachable without editing a
    trading loop, which Part 8 asks for and which the runners did not have.

    An adapter is deliberately NOT allowed to make risk decisions. It reports what the venue
    did; it does not decide what should be sent. `RoutedExecutor` owns that, so there is one
    place where a refusal can happen and it is not inside broker-specific code.
    """

    name: str = "adapter"

    @abc.abstractmethod
    def submit(self, intent: OrderIntent) -> Ack:
        """Send one intent. Must not raise for an ordinary venue rejection - return an Ack."""

    @abc.abstractmethod
    def working(self) -> dict[str, float]:
        """Signed quantity still outstanding per symbol.

        Remaining, not submitted. A half-filled order has half its size still on the wire,
        and a sizer that nets the submitted amount will double up. AUD-06.
        """

    def cancel_all(self) -> int:
        """Cancel everything working. Returns how many cancels were sent."""
        return 0


class RoutedExecutor:
    """Signal -> OrderIntent -> RiskEngine -> adapter -> broker, with the arrows enforced.

    The structural claim Part 16 makes is that a model can propose and the infrastructure
    disposes. That is only true if there is exactly one path to the venue and it runs through
    the risk chain. This is that path:

      * `submit` is the only way to reach the adapter, and it consults the chain first.
      * A denied intent is never passed on. The adapter cannot see it, so no adapter bug or
        broker quirk can resurrect it.
      * A reduced intent reaches the adapter at the REDUCED size, never the requested one.
      * A FLATTEN bypasses the chain entirely and always reaches the adapter, because a risk
        layer that can block the exit is not a risk layer (AUD-06 / AUD-08).

    `decisions` keeps every verdict, allowed or not, so a session can be audited afterwards
    for what was refused and by which rule - the refusals are the interesting half and they
    are invisible if only fills are logged.
    """

    def __init__(self, risk: RiskEngine, adapter: ExecutionAdapter, *,
                 on_event=None):
        self.risk = risk
        self.adapter = adapter
        self.decisions: list[tuple[OrderIntent, RiskDecision, Ack | None]] = []
        self._on_event = on_event

    def _emit(self, event: str, **fields) -> None:
        if self._on_event is not None:
            self._on_event(event, **fields)

    def submit(self, intents) -> list[Ack]:
        """Route intents. Returns an Ack for each one that reached the venue."""
        acks: list[Ack] = []
        for intent in intents:
            decision = self.risk(intent)
            if not decision.allowed:
                self.decisions.append((intent, decision, None))
                self._emit("risk_denied", symbol=intent.symbol,
                           side=intent.side.value, qty=intent.quantity,
                           reasons=list(decision.reasons), binding=list(decision.binding))
                continue
            sized = (intent if decision.quantity == intent.quantity
                     else intent.with_quantity(decision.quantity))
            if sized.quantity <= 0:
                # A reduction to zero is a refusal however it was spelled.
                self.decisions.append((intent, decision, None))
                self._emit("risk_zeroed", symbol=intent.symbol,
                           reasons=list(decision.reasons))
                continue
            if sized.quantity != intent.quantity:
                self._emit("risk_reduced", symbol=intent.symbol,
                           requested=intent.quantity, allowed=sized.quantity,
                           reasons=list(decision.reasons), binding=list(decision.binding))
            ack = self.adapter.submit(sized)
            self.decisions.append((intent, decision, ack))
            acks.append(ack)
            self._emit("order_sent" if ack.accepted else "venue_rejected",
                       symbol=sized.symbol, side=sized.side.value, qty=sized.quantity,
                       broker_id=ack.broker_id, reason=ack.reason)
        return acks

    def flatten(self, positions: dict[str, float], *, tag: str = "flatten") -> list[Ack]:
        """Close everything. Builds FLATTEN intents, which the chain cannot touch."""
        intents = [
            OrderIntent(symbol=s, side=Side.of(-q), quantity=abs(q),
                        order_type=OrderType.FLATTEN, tag=tag)
            for s, q in positions.items() if q
        ]
        self._emit("flatten_requested", symbols=sorted(positions), count=len(intents))
        return self.submit(intents)

    @property
    def refused(self) -> list[tuple[OrderIntent, RiskDecision]]:
        """Every intent that never reached the venue, with the verdict that stopped it."""
        return [(i, d) for i, d, a in self.decisions if a is None]


class SimulatedAdapter(ExecutionAdapter):
    """An in-memory venue. Accepts everything and records it.

    Exists so the routing above can be tested without a broker, and so a research run can
    exercise the identical code path a live run uses. A separate "research mode" branch
    inside the runner would be a second path to the venue, which is the thing this whole
    module is trying to prevent.
    """

    name = "simulated"

    def __init__(self, *, reject: set[str] | None = None):
        self.sent: list[OrderIntent] = []
        self.reject = reject or set()
        self._n = 0

    def submit(self, intent: OrderIntent) -> Ack:
        if intent.symbol in self.reject:
            return Ack(intent=intent, accepted=False, reason="simulated venue rejection")
        self._n += 1
        self.sent.append(intent)
        return Ack(intent=intent, accepted=True, broker_id=f"sim-{self._n}")

    def working(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for i in self.sent:
            out[i.symbol] = out.get(i.symbol, 0.0) + i.signed_quantity
        return {k: v for k, v in out.items() if v}
