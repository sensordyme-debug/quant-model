"""The strategy, wired to the upstream engine. PART 14, 15 and 16.

HOW THIS MAPS ONTO A BAR ENGINE
-------------------------------
Upstream is bar-sequenced, and it accepts TICK-unit bars at arbitrary sub-second spacing
(verified). So one trade print becomes one Bar with open = high = low = close = the trade
price and volume = the trade size. The strategy then gets ``on_bar`` per TRADE, which is
what PART 16 and PART 18 require: break-even management and the killswitch are evaluated
per trade, not per minute, and no tick-level behaviour is downgraded to bar-close
behaviour.

THE ONE THING THE ENGINE CANNOT CARRY
-------------------------------------
``Bar`` has fields for OHLCV and nothing else - there is no bid or ask on it. Order-flow
classification needs the quote standing at each trade, so the quote CANNOT travel through
the engine's feed. It is supplied to the strategy as a side channel: a ``QuoteBook`` built
from the same source, aligned by timestamp.

That is a Layer B design, not a modification of upstream: the engine still owns every fill,
every dollar and every prop-firm decision, and the quote book only feeds signal
computation. But it is a real integration constraint and it has a consequence worth stating
plainly - the alignment rule between a trade and "its" quote is ours to choose, and choosing
it wrongly silently flips classifications. Which is why ``QuoteBook`` refuses to guess: the
alignment policy is AMBIGUITY A2 and must be supplied explicitly.

WHY THE BRACKET IS PLACED IN on_fill AND NOT AFTER buy()
--------------------------------------------------------
PART 15 requires the bracket to be anchored to the ACTUAL fill price, and the fill price is
not known when the order is submitted - upstream fills a market order at the next record's
open, slipped adverse (AMBIGUITY A12). Anchoring to the signal bar's close would put the
stop and target at prices derived from a fill that never happened. Upstream already computes
its bracket children from the real fill when ``stop_loss_ticks``/``take_profit_ticks`` are
passed to ``buy``/``sell``, so that is what is used, and ``on_fill`` records the actual fill
for the ledger rather than recomputing anything.
"""
from __future__ import annotations

import datetime as dt
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from zoneinfo import ZoneInfo

from topstep_backtester.strategies.base import ResearchStrategy
from topstep_backtester.strategies.cvd_absorption_harvester import spec as S
from topstep_backtester.strategies.cvd_absorption_harvester.governor import Governor, State
from topstep_backtester.strategies.cvd_absorption_harvester.signal import (
    DivergenceDetector,
    MinuteAggregator,
    Signal,
)
from topstep_backtester.strategies.cvd_absorption_harvester.ticks import (
    TickDataHandler,
    Trade,
)

_ET = ZoneInfo(S.TIMEZONE)
_WINDOW_OPEN = dt.time.fromisoformat(S.ENTRY_WINDOW_OPEN_ET)
_WINDOW_CLOSE = dt.time.fromisoformat(S.ENTRY_WINDOW_CLOSE_ET)


class QuoteAlignment(str, Enum):
    """Which quote is "prevailing" for a trade. AMBIGUITY A2 - no default is provided."""

    #: The last quote stamped strictly before the trade.
    STRICTLY_BEFORE = "STRICTLY_BEFORE"
    #: The last quote stamped at or before the trade.
    AT_OR_BEFORE = "AT_OR_BEFORE"


class QuoteBook:
    """Timestamp-indexed quotes, with an explicit alignment policy.

    Takes parallel sorted arrays rather than a frame so the lookup is a bisect and the
    strategy does not carry a pandas dependency into its hot path.
    """

    def __init__(self, stamps_ns: list[int], bids: list[Decimal], asks: list[Decimal],
                 *, alignment: QuoteAlignment) -> None:
        if not (len(stamps_ns) == len(bids) == len(asks)):
            raise ValueError("quote arrays must be the same length")
        if any(earlier > later for earlier, later
               in zip(stamps_ns, stamps_ns[1:], strict=False)):
            raise ValueError("quote timestamps must be sorted ascending")
        self._stamps = stamps_ns
        self._bids = bids
        self._asks = asks
        self.alignment = alignment
        self.misses = 0

    def at(self, ts_ns: int) -> tuple[Decimal | None, Decimal | None]:
        """The prevailing quote for a trade at ``ts_ns``, or (None, None) if there is none.

        A miss returns None rather than the nearest quote. PART 7 forbids inventing a
        classification for a missing bid or ask, and the nearest LATER quote is future
        information.
        """
        if self.alignment is QuoteAlignment.STRICTLY_BEFORE:
            index = bisect_left(self._stamps, ts_ns) - 1
        else:
            index = bisect_right(self._stamps, ts_ns) - 1
        if index < 0:
            self.misses += 1
            return None, None
        return self._bids[index], self._asks[index]


@dataclass
class TradeRecord:
    """Everything PART 24 requires for one trade, recorded as it happens."""

    trade_id: int
    signal_at: str
    direction: int
    signal_close: Decimal
    cvd_at_signal: int
    prev_swing_price: Decimal
    prev_swing_cvd: int
    entry_price: Decimal | None = None
    entry_at: str = ""
    stop_price: Decimal | None = None
    target_price: Decimal | None = None
    be_triggered_at: str = ""
    be_mfe_ticks: int | None = None
    be_stop_from: Decimal | None = None
    be_stop_to: Decimal | None = None
    mae_ticks: int = 0
    mfe_ticks: int = 0
    conditions: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, object]:
        return {
            "trade_id": self.trade_id,
            "signal_at": self.signal_at,
            "direction": "long" if self.direction > 0 else "short",
            "signal_close": str(self.signal_close),
            "cvd_at_signal": self.cvd_at_signal,
            "prev_swing_price": str(self.prev_swing_price),
            "prev_swing_cvd": self.prev_swing_cvd,
            "entry_price": None if self.entry_price is None else str(self.entry_price),
            "entry_at": self.entry_at,
            "stop_price": None if self.stop_price is None else str(self.stop_price),
            "target_price": None if self.target_price is None else str(self.target_price),
            "be_triggered_at": self.be_triggered_at,
            "be_mfe_ticks": self.be_mfe_ticks,
            "be_stop_from": None if self.be_stop_from is None else str(self.be_stop_from),
            "be_stop_to": None if self.be_stop_to is None else str(self.be_stop_to),
            "mae_ticks": self.mae_ticks,
            "mfe_ticks": self.mfe_ticks,
            "conditions": list(self.conditions),
        }


class CvdAbsorptionHarvester(ResearchStrategy):
    """CVD_ABSORPTION_HARVESTER / XFA_V2.0.

    Cannot be constructed while the specification has unresolved ambiguities: the base
    class calls ``assert_runnable()``, and a spec that cannot say which reading it took is
    not a spec you can attribute a result to. That is the intended state today - eleven of
    the seventeen register items await the owner.
    """

    def __init__(self, contract_id: str, *, quotes: QuoteBook,
                 tick_size: Decimal = S.TICK_SIZE) -> None:
        super().__init__(contract_id, spec=S.SPEC, require_ready=False)
        self.quotes = quotes
        self.tick = tick_size

        self.ticks = TickDataHandler(strict=True)
        self.minutes = MinuteAggregator()
        self.detector = DivergenceDetector(lookback=S.LOOKBACK_BARS)
        self.governor = Governor()

        self._session: dt.date | None = None
        self._pending: Signal | None = None
        self._open_trade: TradeRecord | None = None
        self._entry_price: Decimal | None = None
        #: Costs arrive PER HALF-TURN, so the entry side is carried to the exit. Without
        #: this the governor is told a realised figure short of one side's commission, and
        #: the winning-day lock would fire a fraction early.
        self._entry_costs = Decimal(0)
        self._be_done = False
        self._next_id = 1
        self.records: list[TradeRecord] = []

    # -- helpers --------------------------------------------------------------------------

    def _et(self, ts_ns: int) -> dt.datetime:
        return dt.datetime.fromtimestamp(ts_ns / 1e9, _ET)

    def _in_window(self, when: dt.datetime) -> bool:
        """AMBIGUITY A1 is unresolved, so the closing boundary is not decided here.

        The half-open reading is used for the plumbing and the ambiguity is flagged; a
        historical run is blocked until the owner rules, so no result depends on it.
        """
        return _WINDOW_OPEN <= when.timetz().replace(tzinfo=None) < _WINDOW_CLOSE

    def _unrealized(self, price: Decimal) -> Decimal:
        if self._entry_price is None or self._open_trade is None:
            return Decimal(0)
        points = (price - self._entry_price) * self._open_trade.direction
        return points * S.POINT_VALUE

    # -- the per-trade loop ----------------------------------------------------------------

    async def on_bar(self, bar: object) -> None:
        """One TICK bar is one trade print."""
        ts_ns = int(bar.ts_init)  # type: ignore[attr-defined]
        price = Decimal(str(bar.close))  # type: ignore[attr-defined]
        volume = int(bar.volume)  # type: ignore[attr-defined]
        when = self._et(ts_ns)

        session = self.ticks.session_of(when)
        if session != self._session:
            self._session = session
            self.detector.reset()
            self.governor.start_day(session)

        bid, ask = self.quotes.at(ts_ns)
        self.ticks.on_trade(
            Trade(timestamp=when, price=price, volume=volume, bid=bid, ask=ask)
        )

        await self._manage_open_trade(price, when)

        state = self.governor.on_equity(at=when, unrealized=self._unrealized(price))
        if state is State.HALTED_FAIL:
            await self.cancel_working()
            if self._open_trade is not None:
                await self.close()
            return
        if state is State.HALTED_SUCCESS:
            await self.cancel_working()
            return

        completed = self.minutes.add(
            when=when, price=price, volume=volume, cvd=self.ticks.cvd
        )
        if completed is not None:
            signal = self.detector.observe(completed)
            if signal is not None:
                await self._maybe_enter(signal, when)

    async def _maybe_enter(self, signal: Signal, when: dt.datetime) -> None:
        verdict = self.governor.may_enter(
            in_window=self._in_window(signal.bar.end.astimezone(_ET)),
            position_open=self._open_trade is not None,
        )
        if not verdict:
            return

        record = TradeRecord(
            trade_id=self._next_id,
            signal_at=signal.bar.end.isoformat(),
            direction=signal.direction,
            signal_close=signal.bar.close,
            cvd_at_signal=signal.bar.cvd_at_close,
            prev_swing_price=signal.prev_swing_price,
            prev_swing_cvd=signal.prev_swing_cvd,
            conditions=signal.conditions,
        )
        self._next_id += 1
        self._open_trade = record
        self._be_done = False
        self.governor.record_entry()

        #: Upstream computes the OCO children from the ACTUAL fill, so the tick offsets are
        #: handed to it rather than prices computed from the signal close (AMBIGUITY A12/A15).
        place = self.buy if signal.direction > 0 else self.sell
        await place(
            S.CONTRACTS,
            stop_loss_ticks=S.STOP_TICKS,
            take_profit_ticks=S.TARGET_TICKS,
            custom_tag=f"cvd-{record.trade_id}-{signal.side}",
        )

    async def _manage_open_trade(self, price: Decimal, when: dt.datetime) -> None:
        """Track MAE/MFE per trade and move the stop to break-even. PART 16."""
        record = self._open_trade
        if record is None or self._entry_price is None:
            return

        excursion = (price - self._entry_price) * record.direction
        ticks = int(excursion / self.tick)
        record.mfe_ticks = max(record.mfe_ticks, ticks)
        record.mae_ticks = min(record.mae_ticks, ticks)

        if not self._be_done and record.mfe_ticks >= S.BE_TRIGGER_TICKS:
            offset = self.tick * S.BE_STOP_OFFSET_TICKS * record.direction
            new_stop = self._entry_price + offset
            record.be_triggered_at = when.isoformat()
            record.be_mfe_ticks = record.mfe_ticks
            record.be_stop_from = record.stop_price
            record.be_stop_to = new_stop
            self._be_done = True
            await self.move_stop(price=new_stop)

    # -- upstream callbacks ------------------------------------------------------------------

    async def on_fill(self, fill: object) -> None:
        """Record the ACTUAL fill. Never recompute a price the engine already decided."""
        record = self._open_trade
        if record is None:
            return

        price = Decimal(str(fill.price))  # type: ignore[attr-defined]
        #: profit_and_loss is None on the OPENING half-turn. That is upstream's own
        #: discriminator between an entry and an exit; inferring it from position state
        #: would go wrong the moment a position were scaled.
        pnl = getattr(fill, "profit_and_loss", None)
        stamp = getattr(fill, "creation_timestamp", None)

        fees = Decimal(str(getattr(fill, "fees", 0) or 0))
        commissions = Decimal(str(getattr(fill, "commissions", 0) or 0))

        if pnl is None:
            self._entry_costs = fees + commissions
            record.entry_price = price
            record.entry_at = "" if stamp is None else stamp.astimezone(_ET).isoformat()
            self._entry_price = price
            #: Recorded for the ledger only. The ORDERS were placed as tick offsets so that
            #: upstream anchors the real OCO children to the real fill (AMBIGUITY A12).
            record.stop_price = price - self.tick * S.STOP_TICKS * record.direction
            record.target_price = price + self.tick * S.TARGET_TICKS * record.direction
            return

        #: An exit fill. The engine owns the P&L; the governor is only TOLD the realised
        #: amount so its realized-only winning-day lock can be evaluated on the flat side.
        when = stamp if stamp is not None else dt.datetime.now(_ET)
        self.governor.record_exit(
            net_pnl=Decimal(str(pnl)) - (self._entry_costs + fees + commissions), at=when
        )
        self.records.append(record)
        self._open_trade = None
        self._entry_price = None
        self._entry_costs = Decimal(0)
        self._be_done = False

    def ledger(self) -> list[dict[str, object]]:
        return [r.as_dict() for r in self.records]


__all__ = [
    "CvdAbsorptionHarvester",
    "QuoteAlignment",
    "QuoteBook",
    "TradeRecord",
]
