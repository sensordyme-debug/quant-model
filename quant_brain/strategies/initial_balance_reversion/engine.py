"""The frozen state machine. Fed 1-minute bars; decides only on completed 5-minute buckets.

THE BAR CONTRACT, WRITTEN OUT ONCE
------------------------------------
    a bucket stamped 09:30 covers 09:30:00 - 09:34:59
    it is COMPLETE at 09:35:00, which is when the engine sees it
    every decision is stamped at that completion instant
    a market entry fills at that bucket's CLOSE price, plus adverse slippage

So `signal_time == bar_end + 1min == decision_time == execution_time`, and
`execution_price = close +/- entry slippage`. Nothing is filled at a price or an instant that
was not knowable when the decision was taken.

EXIT PRECEDENCE INSIDE ONE BUCKET, AND WHY
--------------------------------------------
OHLCV cannot order two touches inside a bar, so the order below is declared rather than
inferred, and it is the repository's existing conservative convention (`bracket_reference`):

    1. STOP        if the bucket traded to the stop. Checked first: a resting stop is at the
                   exchange and executes before anything discretionary.
    2. TARGET      only if the stop was not touched in the same bucket.
    3. GOVERNOR    realized + unrealized at the bucket's ADVERSE extreme <= -$800.
    4. TIME STOP   the bucket closing at or after fill + 60 minutes.
    5. HARD FLAT   the 15:45 bucket.

Every bucket that touched BOTH stop and target is flagged `ambiguous_bar` and counted, because
the convention decides those trades and the reader is entitled to know how many there were.

A gap through the stop fills AT THE STOP, not at the gap price. That is the repository's
declared policy, it is optimistic, and it is inherited deliberately rather than re-argued.
"""
from __future__ import annotations

import datetime as dt
import enum
from dataclasses import dataclass, field

from quant_brain.strategies.initial_balance_reversion.governor import Governor
from quant_brain.strategies.initial_balance_reversion.indicators import (
    ABOVE,
    BELOW,
    NONE,
    Excursion,
    InitialBalance,
    bucket_close_time,
    bucket_start_minute,
)
from quant_brain.strategies.initial_balance_reversion.spec import (
    FROZEN,
    TIMEZONE,
    FrozenSpec,
)
from quant_brain.strategies.vwap_pullback.indicators import (
    Bar,
    FiveMinuteAggregator,
    FiveMinuteBar,
)

EXIT_STOP = "stop"
EXIT_TARGET = "target"
EXIT_TIME = "time_stop"
EXIT_FLATTEN = "hard_flatten"
EXIT_KILLSWITCH = "governor_killswitch"
EXIT_TARGET_IMMEDIATE = "target_immediate"


class State(str, enum.Enum):
    BUILDING_IB = "BUILDING_IB"
    ARMED = "ARMED"
    IN_POSITION = "IN_POSITION"
    TRADE_COMPLETE = "TRADE_COMPLETE"
    HALTED_DAY = "HALTED_DAY"


TRANSITIONS: dict[State, set[State]] = {
    State.BUILDING_IB: {State.BUILDING_IB, State.ARMED, State.HALTED_DAY},
    State.ARMED: {State.ARMED, State.IN_POSITION, State.HALTED_DAY, State.BUILDING_IB},
    State.IN_POSITION: {State.IN_POSITION, State.TRADE_COMPLETE, State.HALTED_DAY},
    State.TRADE_COMPLETE: {State.TRADE_COMPLETE, State.ARMED, State.HALTED_DAY,
                           State.BUILDING_IB},
    State.HALTED_DAY: {State.HALTED_DAY, State.BUILDING_IB},
}


class IllegalTransition(RuntimeError):
    """A state change nobody declared. Raised rather than repaired."""


@dataclass
class Position:
    direction: int
    quantity: int
    fill_price: float
    entry_time: dt.datetime
    stop_price: float
    target_price: float
    deadline: dt.datetime
    entry_slippage_points: float
    trap_extreme: float
    ib_high: float
    ib_low: float
    ib_range: float
    ib_midpoint: float
    mfe_points: float = 0.0
    mae_points: float = 0.0
    realized_before: float = 0.0


@dataclass
class Trade:
    """One round trip. Every field the result is reconstructed from."""

    trade_id: int
    session: dt.date
    direction: int
    quantity: int
    entry_time: dt.datetime
    exit_time: dt.datetime
    entry_price: float
    exit_price: float
    ib_high: float
    ib_low: float
    ib_range: float
    ib_midpoint: float
    trap_extreme: float
    stop_price: float
    target_price: float
    gross_pnl: float
    commission: float
    entry_slippage: float
    exit_slippage: float
    net_pnl: float
    exit_reason: str
    holding_minutes: int
    mae: float
    mfe: float
    ambiguous_bar: bool
    realized_before: float
    realized_after: float


@dataclass
class Engine:
    """The frozen strategy. One instance walks the whole history in order."""

    spec: FrozenSpec = FROZEN
    state: State = State.BUILDING_IB
    governor: Governor = None            # type: ignore[assignment]
    five: FiveMinuteAggregator = field(default_factory=FiveMinuteAggregator)
    ib: InitialBalance = None            # type: ignore[assignment]
    excursion: Excursion = field(default_factory=Excursion)

    position: Position | None = None
    trades: list[Trade] = field(default_factory=list)
    transitions: list[tuple[dt.datetime, State, State]] = field(default_factory=list)
    ambiguous_buckets: int = 0
    immediate_targets: int = 0
    same_bucket_traps: int = 0

    _day: dt.date | None = None
    _trade_id: int = 0
    _last_ts: dt.datetime | None = None

    def __post_init__(self) -> None:
        if self.governor is None:
            self.governor = Governor(spec=self.spec)
        if self.ib is None:
            self.ib = self._fresh_ib()

    def _fresh_ib(self) -> InitialBalance:
        return InitialBalance(start_minute=self.spec.minute_of("ib_start"),
                              end_minute=self.spec.minute_of("ib_end"))

    def _to(self, target: State, when: dt.datetime, why: str = "") -> None:
        if target not in TRANSITIONS[self.state]:
            raise IllegalTransition(
                f"{self.state.value} -> {target.value} is not permitted"
                + (f" ({why})" if why else ""))
        if target is not self.state:
            self.transitions.append((when, self.state, target))
        self.state = target

    # ===================================================================================
    # THE BAR LOOP
    # ===================================================================================

    def start_session(self, day: dt.date, when: dt.datetime) -> None:
        """Begin a new trading session. Called by the driver, once per session."""
        if self.position is not None:
            raise RuntimeError(
                f"{day}: a position survived to the session boundary. The 15:45 hard "
                f"flatten is supposed to make that impossible.")
        self._day = day
        self.governor.reset(day)
        self.five = FiveMinuteAggregator()
        self.ib = self._fresh_ib()
        self.excursion = Excursion()
        self.state = State.BUILDING_IB
        self.transitions.append((when, State.HALTED_DAY, State.BUILDING_IB))

    def on_bar(self, bar: Bar) -> None:
        """Absorb one 1-minute bar. Decisions happen only when a bucket completes."""
        if self._last_ts is not None and bar.timestamp <= self._last_ts:
            return                              # duplicate or out-of-order: refused
        self._last_ts = bar.timestamp
        done = self.five.update(bar, float("nan"))
        if done is not None:
            self._on_bucket(done)

    def _on_bucket(self, five: FiveMinuteBar) -> None:
        start_min = bucket_start_minute(five, TIMEZONE)
        close_at = bucket_close_time(five, self.spec.bar_minutes)
        close_min = close_at.astimezone(TIMEZONE).hour * 60 + close_at.astimezone(
            TIMEZONE).minute

        # --- 1. the Initial Balance ------------------------------------------------------
        if not self.ib.complete:
            self.ib.update(five, start_min)
            if not self.ib.complete:
                return
            #: the window just closed. Apply the regime filter once, here.
            if not self.ib.in_regime(self.spec.ib_range_min, self.spec.ib_range_max):
                self.governor.halt(close_at,
                                   f"IB range {self.ib.ib_range:.2f} outside "
                                   f"[{self.spec.ib_range_min:g}, "
                                   f"{self.spec.ib_range_max:g}]")
                self._to(State.HALTED_DAY, close_at, "IB regime filter")
                return
            self._to(State.ARMED, close_at, "IB complete and in regime")
            return

        # --- 2. an open position ----------------------------------------------------------
        held_through = self.position is not None
        if held_through:
            self._manage(five, close_at, close_min)

        # --- 3. the excursion tracker runs on EVERY bucket, position or not (B8) ----------
        #: It must, or a trip that opens while a trade is running would be invisible once the
        #: trade closed, and the next rejection would be measured from a trip the engine
        #: never saw. Entry is gated separately, below.
        was_side = self.excursion.side
        self.excursion.update(five, self.ib.ib_high, self.ib.ib_low)
        rejected = self.excursion.rejected(five, self.ib.ib_high, self.ib.ib_low)
        opened_here = was_side == NONE and self.excursion.side != NONE
        #: a bucket closing back inside ENDS the trip whether or not it was traded. Without
        #: this a consumed trip would never reset and no later breakout could ever open one.
        closed_inside = (
            self.excursion.side == BELOW and five.close > self.ib.ib_low
            or self.excursion.side == ABOVE and five.close < self.ib.ib_high)

        # --- 4. an entry, only when flat, armed, and before the flatten -------------------
        may_trade = (self.position is None and not held_through
                     and self.state is not State.HALTED_DAY
                     and close_min < self.spec.minute_of("hard_flatten"))
        if rejected and may_trade:
            if opened_here:
                self.same_bucket_traps += 1
            self._maybe_enter(five, close_at, close_min)

        if closed_inside:
            self.excursion.close_trip()

    # ===================================================================================
    # ENTRY
    # ===================================================================================

    def _maybe_enter(self, five: FiveMinuteBar, when: dt.datetime, minute: int) -> None:
        verdict = self.governor.may_enter(
            when, ib_complete=self.ib.complete,
            in_regime=self.ib.in_regime(self.spec.ib_range_min, self.spec.ib_range_max),
            position_open=self.position is not None, minute_of_day=minute)
        if not verdict:
            return

        d = 1 if self.excursion.side == BELOW else -1
        tick = self.spec.tick
        slip = self.spec.execution.entry_ticks * tick
        fill = self.spec.round_to_tick(five.close + slip * d)
        stop = self.spec.round_to_tick(
            self.excursion.extreme - self.spec.stop_offset_ticks * tick * d)
        #: AMBIGUITY B10 - the raw midpoint is off-tick about half the time and a limit
        #: cannot rest there. Moved to a placeable tick AWAY from the entry.
        target = self.spec.round_target_conservative(self.ib.midpoint, d)

        self.position = Position(
            direction=d, quantity=self.spec.contracts, fill_price=fill, entry_time=when,
            stop_price=stop, target_price=target,
            deadline=when + dt.timedelta(minutes=self.spec.time_stop_minutes),
            entry_slippage_points=slip, trap_extreme=self.excursion.extreme,
            ib_high=self.ib.ib_high, ib_low=self.ib.ib_low, ib_range=self.ib.ib_range,
            ib_midpoint=self.ib.midpoint, realized_before=self.governor.realized)
        self.governor.record_entry(when)
        self.excursion.consume()
        self._to(State.IN_POSITION, when, "rejection")

        #: AMBIGUITY B4 - the target may already be behind the fill. A limit on the wrong
        #: side of the market is marketable and executes at once.
        if (d > 0 and fill >= target) or (d < 0 and fill <= target):
            self.immediate_targets += 1
            self._close(five, when, price=target, reason=EXIT_TARGET_IMMEDIATE,
                        exit_slippage_points=0.0, ambiguous=False)

    # ===================================================================================
    # MANAGEMENT
    # ===================================================================================

    def _manage(self, five: FiveMinuteBar, when: dt.datetime, minute: int) -> None:
        p = self.position
        assert p is not None
        d, tick = p.direction, self.spec.tick

        excursion_up = (five.high - p.fill_price) * d
        excursion_dn = (five.low - p.fill_price) * d
        p.mfe_points = max(p.mfe_points, excursion_up if d > 0 else -excursion_dn)
        p.mae_points = min(p.mae_points, excursion_dn if d > 0 else -excursion_up)

        hit_stop = five.low <= p.stop_price if d > 0 else five.high >= p.stop_price
        hit_target = five.high >= p.target_price if d > 0 else five.low <= p.target_price
        ambiguous = bool(hit_stop and hit_target)
        if ambiguous:
            self.ambiguous_buckets += 1

        # 1. the stop, first and unconditionally
        if hit_stop:
            slip = self.spec.execution.stop_ticks * tick
            self._close(five, when,
                        price=self.spec.round_to_tick(p.stop_price - slip * d),
                        reason=EXIT_STOP, exit_slippage_points=slip, ambiguous=ambiguous)
            return
        # 2. the target, a limit, filled at its level
        if hit_target:
            self._close(five, when, price=p.target_price, reason=EXIT_TARGET,
                        exit_slippage_points=self.spec.execution.target_ticks * tick,
                        ambiguous=False)
            return
        # 3. the governor, marked at the bucket's ADVERSE extreme
        adverse = five.low if d > 0 else five.high
        unreal = (adverse - p.fill_price) * d * self.spec.point_value
        if self.governor.killswitch_breached(unreal):
            slip = self.spec.execution.market_exit_ticks * tick
            self._close(five, when,
                        price=self.spec.round_to_tick(five.close - slip * d),
                        reason=EXIT_KILLSWITCH, exit_slippage_points=slip, ambiguous=False)
            self.governor.halt(when, "daily mark-to-market killswitch")
            self._to(State.HALTED_DAY, when, "killswitch")
            return
        # 4. the 60-minute time stop, on wall-clock elapsed time
        if when >= p.deadline:
            slip = self.spec.execution.market_exit_ticks * tick
            self._close(five, when,
                        price=self.spec.round_to_tick(five.close - slip * d),
                        reason=EXIT_TIME, exit_slippage_points=slip, ambiguous=False)
            return
        # 5. the 15:45 hard flatten
        if minute >= self.spec.minute_of("hard_flatten"):
            slip = self.spec.execution.market_exit_ticks * tick
            self._close(five, when,
                        price=self.spec.round_to_tick(five.close - slip * d),
                        reason=EXIT_FLATTEN, exit_slippage_points=slip, ambiguous=False)
            return

    def _close(self, five: FiveMinuteBar, when: dt.datetime, *, price: float, reason: str,
               exit_slippage_points: float, ambiguous: bool) -> None:
        p = self.position
        assert p is not None
        d, pv = p.direction, self.spec.point_value

        #: GROSS is measured at the IDEAL prices - the levels before slippage moved the
        #: fills - so `gross - slippage - commission == net` holds and slippage is its own
        #: line rather than hidden inside a fill.
        ideal_entry = p.fill_price - p.entry_slippage_points * d
        ideal_exit = price + exit_slippage_points * d
        gross = (ideal_exit - ideal_entry) * d * pv
        entry_slip = p.entry_slippage_points * pv
        exit_slip = exit_slippage_points * pv
        commission = self.spec.commission_round_turn
        net = gross - entry_slip - exit_slip - commission

        self._trade_id += 1
        before = p.realized_before
        #: `_day` is set by `start_session`, which the driver must call before any bar. A
        #: position cannot exist without one, so the narrowing is done once here rather than
        #: annotating the field as optional and checking at every use.
        assert self._day is not None
        self.governor.record_exit(net_pnl=net, when=when)
        self.trades.append(Trade(
            trade_id=self._trade_id, session=self._day, direction=d, quantity=p.quantity,
            entry_time=p.entry_time, exit_time=when, entry_price=p.fill_price,
            exit_price=price, ib_high=p.ib_high, ib_low=p.ib_low, ib_range=p.ib_range,
            ib_midpoint=p.ib_midpoint, trap_extreme=p.trap_extreme,
            stop_price=p.stop_price, target_price=p.target_price,
            gross_pnl=gross, commission=commission, entry_slippage=entry_slip,
            exit_slippage=exit_slip, net_pnl=net, exit_reason=reason,
            holding_minutes=int((when - p.entry_time).total_seconds() // 60),
            mae=p.mae_points * pv, mfe=p.mfe_points * pv, ambiguous_bar=ambiguous,
            realized_before=before, realized_after=self.governor.realized))
        self.position = None
        _ = five
        if self.state is State.IN_POSITION:
            self._to(State.HALTED_DAY if self.governor.halted else State.TRADE_COMPLETE,
                     when, reason)
        if self.state is State.TRADE_COMPLETE and not self.governor.halted:
            self._to(State.ARMED, when, "flat again")

    def end_session(self, when: dt.datetime) -> None:
        """Assert the day ended flat. The 15:45 flatten is supposed to guarantee it."""
        if self.position is not None:
            raise RuntimeError(
                f"{self._day}: a position survived past {when}. The hard flatten failed.")


__all__ = ["EXIT_FLATTEN", "EXIT_KILLSWITCH", "EXIT_STOP", "EXIT_TARGET",
           "EXIT_TARGET_IMMEDIATE", "EXIT_TIME", "Engine", "IllegalTransition", "Position",
           "State", "TRANSITIONS", "Trade"]
