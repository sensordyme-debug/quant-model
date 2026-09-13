"""A futures execution simulator: what a fill actually costs, and when it does not happen.

Part 24. Everything above this module - the twin, the Monte Carlo, the stress scenarios -
consumes session P&L and is only as honest as that number. This is where the number stops
being a backtest's `close - entry` and starts including the four things that separate a
research P&L from a brokerage statement:

    SPREAD      a market order crosses it. On ES that is one tick, $12.50 round turn, and
                F-2a measured the realised cost at 0.488 bps, which is the anchor used here.
    COMMISSION  per side, per contract, and on a micro it is a far larger share of the move.
    SLIPPAGE    beyond the spread, growing with size relative to what rests at the touch.
    REJECTION   the order that does not happen at all - past the flatten time, through a
                position limit, or inside a blackout.

WHY THE MICRO CONTRACTS ARE THE POINT
--------------------------------------
A prop account's survival depends on granularity: under a 5-contract ES limit you have five
sizing steps, under 50 MES you have fifty. But a micro is one tenth the notional at roughly
the same commission per contract, so the cost per dollar of exposure is far higher. That
trade is exactly the kind of thing a Sharpe-based backtest hides and a pass-probability
objective surfaces, and `cost_per_dollar_exposure` exists to make it visible.

WHAT THIS DELIBERATELY IS NOT
-----------------------------
Not a matching engine. There is no order book here, and simulating one from bar data would be
false precision dressed as rigour - the repository has no tick data (the capability audit
measured 30 seconds as the floor), so a book reconstruction would be interpolation with a
confident face. What this does is charge a defensible, measured cost and refuse the orders a
real venue or a real rulebook would refuse.
"""
from __future__ import annotations

import datetime as dt
import enum
import math
from dataclasses import dataclass, field

from quant_brain.core.execution import Fill, OrderIntent, OrderType, Side
from quant_brain.markets.futures_cme import instruments as inst


class RejectReason(str, enum.Enum):
    """Why an order did not become a fill. Every one of these happens in production."""

    NONE = "none"
    FLAT_BEFORE_CLOSE = "flat_before_close"
    BLACKOUT = "blackout"
    POSITION_LIMIT = "position_limit"
    MARKET_CLOSED = "market_closed"
    LIMIT_NOT_MARKETABLE = "limit_not_marketable"
    ZERO_QUANTITY = "zero_quantity"
    NO_PRICE = "no_price"


@dataclass(frozen=True)
class Quote:
    """The top of book at a moment. `bid`/`ask` are prices, `size` is what rests there."""

    bid: float
    ask: float
    bid_size: int = 100
    ask_size: int = 100
    ts: dt.datetime | None = None

    def __post_init__(self) -> None:
        if self.bid > self.ask:
            raise ValueError(f"crossed quote: bid {self.bid} above ask {self.ask}")
        if self.bid <= 0 or self.ask <= 0:
            raise ValueError(f"non-positive quote: {self.bid}/{self.ask}")

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    def touch(self, side: Side) -> float:
        """The price a market order of that side crosses to."""
        return self.ask if side is Side.BUY else self.bid

    def resting(self, side: Side) -> int:
        return self.ask_size if side is Side.BUY else self.bid_size


@dataclass(frozen=True)
class CostModel:
    """Commission and slippage, per contract.

    Defaults are deliberately absent for commission: brokers differ by a factor of three on
    futures, and a wrong commission on a micro-contract strategy is not a rounding error - it
    can be most of the edge. `for_contract` reads the rate off the instrument metadata, which
    is where a measured number belongs.
    """

    commission_per_side: float
    #: Extra slippage in TICKS once an order is large relative to what rests at the touch.
    #: Zero means the order is assumed to fill entirely at the touch, which is only credible
    #: for sizes small against the book.
    impact_ticks_per_book: float = 1.0
    #: The quoted spread, in ticks. One tick is the default because it is the minimum the
    #: venue permits, but it is an ASSUMPTION until a quote store exists - use
    #: `measure_spread_ticks` to replace it with the tape.
    spread_ticks: float = 1.0

    @classmethod
    def for_contract(cls, symbol: str, **kw) -> CostModel:
        c = inst.get(symbol)
        if not c.commission_round_turn:
            raise ValueError(
                f"{symbol} has no commission recorded in the instrument metadata. A futures "
                "cost model without a commission is not conservative, it is wrong - on a "
                "micro contract the commission can exceed the edge. Record the rate from "
                "your own broker statement.")
        return cls(commission_per_side=c.commission_round_turn / 2, **kw)


@dataclass
class ExecutionResult:
    """One order's outcome: a fill, or a refusal with a reason."""

    intent: OrderIntent
    fill: Fill | None = None
    reason: RejectReason = RejectReason.NONE
    detail: str = ""

    @property
    def filled(self) -> bool:
        return self.fill is not None

    def __str__(self) -> str:
        if self.fill:
            return (f"{self.intent.side.value} {self.fill.quantity:g} {self.intent.symbol} "
                    f"@ {self.fill.price:.4f} cost ${self.fill.cost():.2f}")
        return f"REJECTED {self.intent.symbol}: {self.reason.value} {self.detail}".rstrip()


@dataclass
class ExecutionSimulator:
    """Turns intents into fills, charging measured costs and refusing what a venue would.

    Stateless with respect to positions on purpose: position tracking lives in
    `core.execution.Position`, and duplicating it here would let the two disagree. What this
    owns is the price a fill happens at, and whether it happens.
    """

    cost: CostModel
    symbol: str
    #: Minutes before the session close after which only flattening orders are accepted.
    flat_before_close: int = 15
    #: (start, end) local times in which new risk may not be opened. Flattening always may.
    blackouts: tuple[tuple[dt.time, dt.time], ...] = ()
    #: Hard cap on absolute position, enforced against the position passed to `execute`.
    max_position: int | None = None
    fills: list[Fill] = field(default_factory=list)
    rejects: list[ExecutionResult] = field(default_factory=list)

    @property
    def tick(self) -> float:
        return inst.get(self.symbol).spec.tick

    @property
    def multiplier(self) -> float:
        return inst.get(self.symbol).spec.multiplier

    # -- pricing ---------------------------------------------------------------------------

    def is_marketable(self, intent: OrderIntent, quote: Quote) -> bool:
        """Whether a limit order can trade against this quote at all.

        A limit only fills here if the market has come to it: the ask is at or below a bid's
        limit, or the bid at or above an offer's limit. A limit resting behind the touch is
        reported as not filled.

        That is deliberately pessimistic and it is the single most consequential modelling
        choice in this file. Assuming a resting limit gets filled is the classic way a
        backtest manufactures returns - it collects the spread on every trade and silently
        ignores that the fills it gets are the ones it did not want (adverse selection: your
        bid trades exactly when the market is about to go lower). Estimating a passive fill
        probability honestly needs queue position and trade prints, and this repository has
        neither - the capability audit measured 30 seconds as the data floor. So passive
        fills are refused rather than modelled, and a strategy that needs them cannot be
        evaluated here until that data exists. Refusing to answer is the correct behaviour;
        answering optimistically is not.
        """
        if intent.order_type is not OrderType.LIMIT or intent.limit_price is None:
            return True
        return (quote.ask <= intent.limit_price if intent.side is Side.BUY
                else quote.bid >= intent.limit_price)

    def fill_price(self, intent: OrderIntent, quote: Quote) -> float:
        """Where the order fills, including spread and size impact.

        A market order crosses the spread and then walks the book: `impact_ticks_per_book`
        ticks for every multiple of the resting size. The walk is linear in size, which is
        conservative for small orders and optimistic for very large ones - stated here rather
        than buried, because it is the assumption most likely to be wrong for someone trading
        size that matters.

        A marketable limit crosses the same way but can never fill worse than its own price.
        Where the walk would go through the limit, the remainder is modelled as filling AT the
        limit rather than not at all, which is optimistic for a large order in a thin book.
        """
        sign = intent.side.sign
        if intent.order_type is OrderType.LIMIT and intent.limit_price is None:
            raise ValueError("a limit order needs a limit price")

        price = quote.touch(intent.side)
        resting = max(1, quote.resting(intent.side))
        books = max(0.0, (intent.quantity - resting) / resting)
        walked = price + sign * self.cost.impact_ticks_per_book * books * self.tick
        if intent.order_type is OrderType.LIMIT and intent.limit_price is not None:
            return min(walked, intent.limit_price) if sign > 0 else max(
                walked, intent.limit_price)
        return walked

    def round_to_tick(self, price: float, side: Side) -> float:
        """Round AGAINST the trader, which is the direction a venue rounds in practice."""
        t = self.tick
        return (math.ceil(price / t) * t) if side is Side.BUY else (math.floor(price / t) * t)

    # -- the gate --------------------------------------------------------------------------

    def _refuse(self, intent: OrderIntent, reason: RejectReason,
                detail: str = "") -> ExecutionResult:
        r = ExecutionResult(intent=intent, reason=reason, detail=detail)
        self.rejects.append(r)
        return r

    def execute(self, intent: OrderIntent, quote: Quote | None, *,
                minutes_to_close: int | None = None,
                now: dt.time | None = None,
                position: float = 0.0) -> ExecutionResult:
        """Attempt one order.

        A FLATTEN intent bypasses the blackout, the flatten-time cutoff and the position cap,
        matching `core.risk.RiskEngine`: the book must always be closeable, and a simulator
        that could refuse a flatten would model a trap rather than a venue.
        """
        if intent.quantity <= 0:
            return self._refuse(intent, RejectReason.ZERO_QUANTITY)
        if quote is None:
            # Part 32: if market data is unavailable, do not invent prices.
            return self._refuse(intent, RejectReason.NO_PRICE,
                                "no quote available; a price was not invented")

        if not intent.is_flatten:
            if minutes_to_close is not None and minutes_to_close <= self.flat_before_close:
                return self._refuse(
                    intent, RejectReason.FLAT_BEFORE_CLOSE,
                    f"{minutes_to_close}min to close, cutoff {self.flat_before_close}")
            if now is not None and self.in_blackout(now):
                return self._refuse(intent, RejectReason.BLACKOUT, f"at {now}")
            if self.max_position is not None:
                after = abs(position + intent.signed_quantity)
                if after > self.max_position:
                    return self._refuse(
                        intent, RejectReason.POSITION_LIMIT,
                        f"{after:g} would exceed {self.max_position}")

        if not self.is_marketable(intent, quote):
            return self._refuse(
                intent, RejectReason.LIMIT_NOT_MARKETABLE,
                f"limit {intent.limit_price:.4f} rests behind {quote.bid:.4f}/"
                f"{quote.ask:.4f}; passive fills are not modelled")

        raw = self.fill_price(intent, quote)
        price = self.round_to_tick(raw, intent.side)
        if intent.order_type is OrderType.LIMIT and intent.limit_price is not None:
            # Rounding against the trader must not push the fill through the limit.
            price = (min(price, intent.limit_price) if intent.side is Side.BUY
                     else max(price, intent.limit_price))

        slip = (price - quote.mid) * intent.side.sign * self.multiplier * intent.quantity
        fill = Fill(symbol=intent.symbol, side=intent.side, quantity=intent.quantity,
                    price=price, commission=self.cost.commission_per_side * intent.quantity,
                    slippage=slip, ts=intent.ts, tag=intent.tag)
        self.fills.append(fill)
        return ExecutionResult(intent=intent, fill=fill)

    def in_blackout(self, when: dt.time) -> bool:
        for start, end in self.blackouts:
            if start <= end:
                if start <= when <= end:
                    return True
            elif when >= start or when <= end:      # a window wrapping midnight
                return True
        return False

    # -- what it all cost --------------------------------------------------------------------

    @property
    def total_commission(self) -> float:
        return sum(f.commission for f in self.fills)

    @property
    def total_slippage(self) -> float:
        return sum(f.slippage for f in self.fills)

    @property
    def total_cost(self) -> float:
        return self.total_commission + self.total_slippage

    def round_turn_cost(self, quantity: float = 1.0) -> float:
        """Modelled cost of entering and exiting `quantity` contracts.

        Now cross-checked against three independent numbers rather than asserted. On the ES
        quote store fetched 2026-09-13, the RTH spread is a median of exactly 1.00 tick with
        95.6% of bars at one tick, giving 0.480 bps of round turn at ES's median price of
        6,872. The model charges 0.480 bps. F-2a's independently measured realised cost was
        0.488 bps. Three numbers, agreeing to within 2%.

        WHY THE COST IS CHARGED IN TICKS AND NOT IN BASIS POINTS
        Measured on the ES quote store, RTH, by quarter:

            2025Q2  1.00 ticks  0.411 bps   median price 6,086
            2025Q3  1.00 ticks  0.389 bps                6,431
            2025Q4  1.00 ticks  0.366 bps                6,830
            2026Q1  1.00 ticks  0.363 bps                6,888
            2026Q2  1.00 ticks  0.337 bps                7,412
            2026Q3  1.00 ticks  0.327 bps                7,647

        The spread is pinned at exactly one tick in every quarter while its cost in basis
        points decays 20%, entirely because the index rose. A tick is a fixed 0.25 points;
        bps is not fixed at all. So a hard-coded bps constant silently cheapens execution
        every year the market goes up, and charging in ticks is right at every price.

        This figure is therefore PRICE-DEPENDENT and must only ever be compared against a
        measurement taken at the SAME price. The same model reads 0.569 bps at 5,800 and
        0.480 bps at 6,872 - and ES never traded below 5,971 anywhere in this sample, so
        5,800 is not merely a different price, it is one that did not occur. Two separate
        readings of this number have gone wrong that way: once appearing 17% conservative
        and once appearing to overcharge by 56%. Like-for-like at the same price, the model
        and the tape agree to 1.000x.
        """
        spread = self.cost.spread_ticks * self.tick * self.multiplier
        return 2 * self.cost.commission_per_side * quantity + spread * quantity

    def cost_per_dollar_exposure(self, price: float) -> float:
        """Round-turn cost as a fraction of one contract's notional.

        The number that decides whether micros are worth their granularity. A micro is a
        tenth of the notional at a similar commission, so this is several times larger for
        MES than for ES - and it is the reason a strategy that works on ES can be
        unprofitable on the micro that a small account is actually permitted to trade.
        """
        notional = price * self.multiplier
        if notional <= 0:
            raise ValueError(f"non-positive notional from price {price}")
        return self.round_turn_cost(1.0) / notional


def measure_spread_ticks(quotes, *, tick: float, column: str = "spread",
                        low: float = 0.0, high: float = 20.0) -> dict[str, float]:
    """Measure the quoted spread from a quote store, so the cost model stops assuming it.

    Returns median, mean and the share of bars at exactly one tick. The median is the number
    to feed `CostModel.spread_ticks`: the mean is dragged by halt and rollover artefacts that
    no strategy actually trades through, and the `low`/`high` bounds drop those outright.

    A store with no quotes cannot call this, which is the point - `dataquality` reports the
    absence explicitly rather than letting an assumed spread pass for a measured one.
    """
    import pandas as pd

    # Series-typed explicitly: pd.to_numeric's return union includes scalars, so neither the
    # comparisons nor the reductions below are statically elementwise without this.
    s = pd.Series(pd.to_numeric(pd.Series(quotes[column]), errors="coerce")).dropna()
    # Re-wrapped after the boolean mask: indexing a Series widens the inferred type again.
    s = pd.Series(s[(s > low) & (s < high)])
    if s.empty:
        raise ValueError("no usable spread observations after filtering; the quote store is "
                         "empty or every row was an artefact")
    ticks = pd.Series(s / tick)
    return {"median_ticks": float(ticks.median()), "mean_ticks": float(ticks.mean()),
            "p90_ticks": float(ticks.quantile(0.90)),
            "one_tick_share": float((ticks <= 1.001).mean()), "n": float(len(ticks))}


def compare_granularity(symbol: str, price: float, *, micro_price: float | None = None
                        ) -> dict[str, float]:
    """The mini/micro trade-off, in numbers rather than intuition.

    Returns cost per dollar of exposure for the parent and each of its micros, plus the ratio.
    A ratio well above one is the price of the sizing granularity a small account needs, and
    it should be compared against the edge before the micro is chosen for its flexibility.
    """
    out: dict[str, float] = {}
    parent = inst.get(symbol)
    base = ExecutionSimulator(cost=CostModel.for_contract(symbol), symbol=symbol)
    out[symbol] = base.cost_per_dollar_exposure(price)
    for micro in inst.micros_of(symbol):
        sim = ExecutionSimulator(cost=CostModel.for_contract(micro), symbol=micro)
        out[micro] = sim.cost_per_dollar_exposure(micro_price if micro_price else price)
        out[f"{micro}/{parent.symbol}"] = out[micro] / out[symbol]
    return out
