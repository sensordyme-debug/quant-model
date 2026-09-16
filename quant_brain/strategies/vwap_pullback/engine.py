"""The frozen engine: one bar in, a state machine step out. Nothing here looks forward.

THE SHAPE OF THE LOOP, AND WHY THE ORDER IS THE SPECIFICATION
---------------------------------------------------------------
Per 1-minute bar, in this order and no other:

    1. DAY ROLL      at the 18:00 anchor: reset the VWAP, the counters and the halt
    2. INDICATORS    absorb the bar - VWAP, volume SMA, the 5-minute aggregate, ATR
    3. POSITION      manage an open position against the levels IN FORCE AT THE BAR'S START
    4. ENTRY         only if flat; context, then trigger, then fill at this bar's close
    5. AUDIT         the order book must be defensible after every single bar

Step 3 before step 4 is deliberate: a bar that stops a position out and also qualifies as a
new trigger does BOTH, in that order, which is what actually happens on a tape. Step 3 using
levels frozen at the bar's start is the conservative reading of an unknowable intrabar path -
see `BE_ARMS_AFTER_THE_BAR` below.

WHAT THIS ENGINE CANNOT DO, BY CONSTRUCTION
---------------------------------------------
It receives one bar at a time and holds no reference to any container of bars. There is no
`bars[i+1]` to write by accident; a forward-looking rule would have to be given the future
explicitly, and nothing in the signature offers it. The `+25` stall rule is the one place a
FORWARD WINDOW exists at all, and it is implemented as a countdown over bars already seen: at
t+1 and t+2 the engine records and decides nothing.

INTRABAR PRECEDENCE, WRITTEN DOWN ONCE
----------------------------------------
OHLCV cannot say whether the high or the low came first. When more than one thing could have
happened on a bar, resolution is by this table and nothing else:

    1. STOP                  a resting order at a known level
    2. TARGET                a resting order at a known level
    3. GOVERNOR KILLSWITCH   a decision taken at the bar's close
    4. HARD FLATTEN          a decision taken at the bar's close
    5. STALL MARKET CLOSE    a decision taken at the bar's close

Resting orders before discretionary ones, and STOP before TARGET. That is the same precedence
`research/bracket_reference.py` declares, reused deliberately: ambiguity is never resolved
toward profit, and a bar that could have been either is recorded as `ambiguous_bar`.
"""
from __future__ import annotations

import datetime as dt
import enum
from dataclasses import dataclass, field

import pandas as pd

from quant_brain.research.canonical_ledger import Fill, LedgerTrade
from quant_brain.strategies.vwap_pullback.governor import Governor
from quant_brain.strategies.vwap_pullback.indicators import (
    Atr,
    Bar,
    FiveMinuteAggregator,
    SessionVwap,
    VolumeSma,
    trading_day,
)
from quant_brain.strategies.vwap_pullback.orders import OrderBook
from quant_brain.strategies.vwap_pullback.spec import FROZEN, FrozenSpec

#: AMBIGUITY A15. The break-even modification arms at the END of the bar whose extreme
#: triggered it, so the ORIGINAL stop is in force for the whole of that bar.
#:
#: The alternative - arming mid-bar, then testing the bar's own low against the new stop -
#: resolves an ambiguous bar (one that touched both fill+15 and fill-15) in the strategy's
#: favour, turning a full stop-out into a one-tick win on nothing more than an assumption
#: about which tick came first. `research/bracket_reference.py` arms before the test because
#: the certified engine it mirrors does; this engine does not, and the difference is tested.
BE_ARMS_AFTER_THE_BAR = True

def _stamp(when: dt.datetime) -> pd.Timestamp:
    """A pandas Timestamp from an AWARE datetime.

    `pd.Timestamp(...)` is annotated as possibly returning `NaT`, which it cannot do for a
    real datetime - but the annotation is what every downstream signature has to satisfy, so
    the impossibility is asserted once, here, instead of being ignored at each use.
    """
    out = pd.Timestamp(when)
    if not isinstance(out, pd.Timestamp):                  # pragma: no cover
        raise ValueError(f"{when!r} did not convert to a timestamp")
    return out


EXIT_STOP = "stop"
EXIT_TARGET = "target"
EXIT_KILLSWITCH = "governor_killswitch"
EXIT_HARD_FLATTEN = "hard_flatten"
EXIT_STALL = "stall_market_close"


class State(str, enum.Enum):
    FLAT_MONITORING = "FLAT_MONITORING"
    ARMED_LONG = "ARMED_LONG"
    ARMED_SHORT = "ARMED_SHORT"
    IN_POSITION = "IN_POSITION"
    COOLDOWN = "COOLDOWN"
    HALTED_DAY = "HALTED_DAY"


#: Every transition the machine may make. Anything absent is refused, loudly.
TRANSITIONS: dict[State, frozenset[State]] = {
    State.FLAT_MONITORING: frozenset({State.ARMED_LONG, State.ARMED_SHORT,
                                      State.COOLDOWN, State.HALTED_DAY,
                                      State.FLAT_MONITORING}),
    State.ARMED_LONG: frozenset({State.IN_POSITION, State.FLAT_MONITORING,
                                 State.ARMED_SHORT, State.COOLDOWN, State.HALTED_DAY,
                                 State.ARMED_LONG}),
    State.ARMED_SHORT: frozenset({State.IN_POSITION, State.FLAT_MONITORING,
                                  State.ARMED_LONG, State.COOLDOWN, State.HALTED_DAY,
                                  State.ARMED_SHORT}),
    State.IN_POSITION: frozenset({State.FLAT_MONITORING, State.COOLDOWN,
                                  State.HALTED_DAY, State.IN_POSITION}),
    State.COOLDOWN: frozenset({State.FLAT_MONITORING, State.HALTED_DAY, State.COOLDOWN}),
    #: The halt releases at the 18:00 day roll and at no other moment.
    State.HALTED_DAY: frozenset({State.HALTED_DAY}),
}


class IllegalTransition(RuntimeError):
    """A state change the machine does not permit."""


@dataclass
class Position:
    """An open position and everything the exit rules need to remember about it."""

    direction: int
    quantity: int
    fill_price: float
    entry_time: dt.datetime
    entry_bar: int
    stop_price: float
    target_price: float
    #: Running excursions in POINTS, measured from the fill.
    mfe_points: float = 0.0
    mae_points: float = 0.0
    breakeven_done: bool = False
    #: Stall state. `mfe_bar_extreme` is the high (long) or low (short) of the bar on which
    #: +25 was FIRST achieved; the window then counts three bars and decides once.
    mfe_bar_index: int | None = None
    mfe_bar_extreme: float | None = None
    stall_bars_seen: int = 0
    stall_broken: bool = False
    stall_done: bool = False
    entry_slippage_points: float = 0.0


@dataclass
class BarOutcome:
    """What one bar did. Returned by `on_bar` so a test can assert on a single step."""

    timestamp: dt.datetime
    state: State
    ignored: str = ""
    entered: bool = False
    exited: str = ""
    breakeven: bool = False
    stall_modified: bool = False
    halted: bool = False
    vwap: float = float("nan")
    sigma: float = float("nan")
    atr: float = float("nan")
    notes: tuple[str, ...] = ()


@dataclass
class Engine:
    """The frozen strategy. Fed bars; produces canonical trades, fills and a state trail."""

    spec: FrozenSpec = FROZEN
    state: State = State.FLAT_MONITORING
    governor: Governor = None            # type: ignore[assignment]
    book: OrderBook = field(default_factory=OrderBook)
    vwap: SessionVwap = None             # type: ignore[assignment]
    volume_sma: VolumeSma = None         # type: ignore[assignment]
    five_min: FiveMinuteAggregator = field(default_factory=FiveMinuteAggregator)
    atr: Atr = None                      # type: ignore[assignment]

    position: Position | None = None
    trades: list[LedgerTrade] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    outcomes: list[BarOutcome] = field(default_factory=list)
    transitions: list[tuple[dt.datetime, State, State]] = field(default_factory=list)

    _bar_index: int = -1
    _last_ts: dt.datetime | None = None
    _trade_id: int = 0
    #: The bars already seen, so `_previous_bar` cannot reach past the current one. Appended
    #: by `on_bar` and NOT by the caller: a driver that forgot to append would silently give
    #: the trigger a stale previous bar.
    _history: list[Bar] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.governor is None:
            self.governor = Governor(spec=self.spec)
        if self.vwap is None:
            self.vwap = SessionVwap(anchor_minute=self.spec.anchor_minute())
        if self.volume_sma is None:
            self.volume_sma = VolumeSma(period=self.spec.volume_sma_period)
        if self.atr is None:
            self.atr = Atr(period=self.spec.atr_period, method=self.spec.atr_method)

    # =================================================================================
    # THE STATE MACHINE
    # =================================================================================

    def _to(self, target: State, when: dt.datetime, why: str = "") -> None:
        if target not in TRANSITIONS[self.state]:
            raise IllegalTransition(
                f"{self.state.value} -> {target.value} is not a permitted transition"
                + (f" ({why})" if why else "")
                + ". The machine refuses rather than repairing itself into a state nobody "
                  "declared.")
        if target is not self.state:
            self.transitions.append((when, self.state, target))
        self.state = target

    def _release_halt(self, when: dt.datetime) -> None:
        """The ONLY way out of HALTED_DAY: the 18:00 roll, applied by the governor."""
        self.state = State.FLAT_MONITORING
        self.transitions.append((when, State.HALTED_DAY, State.FLAT_MONITORING))

    # =================================================================================
    # THE BAR LOOP
    # =================================================================================

    def on_bar(self, bar: Bar) -> BarOutcome:
        """Absorb one 1-minute bar and take at most one action of each kind."""
        # --- duplicate and out-of-order events fail closed ------------------------------
        if self._last_ts is not None and bar.timestamp <= self._last_ts:
            out = BarOutcome(timestamp=bar.timestamp, state=self.state,
                             ignored=("duplicate bar" if bar.timestamp == self._last_ts
                                      else "out-of-order bar"))
            self.outcomes.append(out)
            return out
        self._last_ts = bar.timestamp
        self._bar_index += 1
        self._history.append(bar)
        notes: list[str] = []

        # --- 1. the day roll --------------------------------------------------------------
        if self.governor.observe(bar.timestamp):
            if self.position is not None:
                raise RuntimeError(
                    f"{bar.timestamp}: a position survived to the 18:00 roll. The 15:45 hard "
                    f"flatten is supposed to make that impossible.")
            was_halted = self.state is State.HALTED_DAY
            self.five_min.reset()
            if was_halted:
                self._release_halt(bar.timestamp)
            else:
                self._to(State.FLAT_MONITORING, bar.timestamp, "day roll")
            notes.append("day roll")

        # --- 2. indicators ----------------------------------------------------------------
        self.vwap.update(bar)
        self.volume_sma.update(bar)
        finished = self.five_min.update(bar, self.vwap.value)
        if finished is not None:
            self.atr.update(finished)

        out = BarOutcome(timestamp=bar.timestamp, state=self.state, vwap=self.vwap.value,
                         sigma=self.vwap.sigma, atr=self.atr.value)

        # --- 3. an open position ----------------------------------------------------------
        if self.position is not None:
            # Passed explicitly rather than re-read inside: the invariant "there is a
            # position" is established HERE, and a method that re-reads `self.position` is one
            # refactor away from being called when there is not one.
            self._manage(bar, self.position, out, notes)

        # --- 4. an entry ------------------------------------------------------------------
        if self.position is None:
            self._seek_entry(bar, out, notes)

        # --- 5. the book must be defensible -----------------------------------------------
        bad = self.book.audit()
        if bad:
            raise RuntimeError(f"{bar.timestamp}: order book is indefensible - "
                               + "; ".join(bad))

        out.state = self.state
        out.notes = tuple(notes)
        self.outcomes.append(out)
        return out

    # =================================================================================
    # POSITION MANAGEMENT
    # =================================================================================

    def _manage(self, bar: Bar, p: Position, out: BarOutcome, notes: list[str]) -> None:
        d = p.direction
        pv = self.spec.point_value

        # Excursions first: they are measurements of the bar, not decisions about it.
        favourable = (bar.high - p.fill_price) if d > 0 else (p.fill_price - bar.low)
        adverse = (bar.low - p.fill_price) if d > 0 else (p.fill_price - bar.high)
        p.mfe_points = max(p.mfe_points, favourable)
        p.mae_points = min(p.mae_points, adverse)

        # The levels IN FORCE for this bar, frozen before anything is modified.
        stop_px, target_px = p.stop_price, p.target_price

        # --- the resting orders ------------------------------------------------------------
        stop_hit = (bar.low <= stop_px) if d > 0 else (bar.high >= stop_px)
        target_hit = (bar.high >= target_px) if d > 0 else (bar.low <= target_px)
        ambiguous = bool(stop_hit and target_hit)

        if stop_hit:
            slip = self.spec.slippage_ticks_stop * self.spec.tick
            self._close(bar, p, price=stop_px - slip * d, reason=EXIT_STOP,
                        exit_slippage_points=slip, ambiguous=ambiguous, out=out)
            return
        if target_hit:
            slip = self.spec.slippage_ticks_target * self.spec.tick
            self._close(bar, p, price=target_px - slip * d, reason=EXIT_TARGET,
                        exit_slippage_points=slip, ambiguous=ambiguous, out=out)
            return

        # --- the discretionary actions, decided at this bar's close -------------------------
        unrealized = self._unrealized(bar, p)
        if self.governor.killswitch_breached(unrealized):
            self._close(bar, p, price=bar.close, reason=EXIT_KILLSWITCH,
                        exit_slippage_points=self.spec.slippage_ticks_flatten *
                        self.spec.tick, ambiguous=False, out=out)
            self.governor.halt(bar.timestamp,
                               f"MTM {self.governor.realized + unrealized:+,.2f} at or below "
                               f"{self.spec.daily_loss_killswitch:+,.2f}")
            self._to(State.HALTED_DAY, bar.timestamp, "killswitch")
            out.halted = True
            notes.append("killswitch")
            return

        if self.governor.must_hard_flatten(bar.timestamp):
            self._close(bar, p, price=bar.close, reason=EXIT_HARD_FLATTEN,
                        exit_slippage_points=self.spec.slippage_ticks_flatten *
                        self.spec.tick, ambiguous=False, out=out)
            notes.append("hard flatten")
            return

        # --- the stall rule ----------------------------------------------------------------
        if self._stall_step(bar, p, out, notes):
            return

        # --- break-even, armed AFTER the bar it triggered on -------------------------------
        if not p.breakeven_done and p.mfe_points >= self.spec.breakeven_trigger:
            new_stop = p.fill_price + self.spec.breakeven_offset * d
            self.book.modify_stop(price=new_stop,
                                  token=f"be-{p.entry_bar}", reason="break-even")
            p.stop_price = new_stop
            p.breakeven_done = True
            out.breakeven = True
            notes.append(f"break-even -> {new_stop}")
        _ = pv

    def _unrealized(self, bar: Bar, p: Position) -> float:
        """Open P&L in dollars, on the basis the frozen spec declares (AMBIGUITY A2)."""
        d = p.direction
        mark = (bar.low if d > 0 else bar.high) \
            if self.spec.governor_mtm_basis == "intrabar" else bar.close
        return (mark - p.fill_price) * d * self.spec.point_value

    def _stall_step(self, bar: Bar, p: Position, out: BarOutcome,
                    notes: list[str]) -> bool:
        """The +25 MFE stall rule. Returns True when it closed the position.

        THE CAUSALITY THIS ENCODES. `mfe_bar_index` is set on the bar that first reaches +25.
        Each later bar increments a counter and records only whether ITS OWN close broke the
        MFE bar's extreme. The decision is taken when the counter reaches `stall_window`, and
        never before - so a break on t+3 prevents the modification, and no information from
        t+3 can reach the engine at t+1 because at t+1 the counter is 1.
        """
        d = p.direction
        if p.stall_done:
            return False

        if p.mfe_bar_index is None:
            if p.mfe_points >= self.spec.stall_mfe:
                p.mfe_bar_index = self._bar_index
                p.mfe_bar_extreme = bar.high if d > 0 else bar.low
                notes.append(f"MFE bar at {bar.timestamp:%H:%M} extreme {p.mfe_bar_extreme}")
            return False

        # A later bar inside the window.
        p.stall_bars_seen += 1
        if p.mfe_bar_extreme is None:                     # pragma: no cover
            raise RuntimeError("a stall window opened with no MFE bar extreme recorded")
        extreme = p.mfe_bar_extreme
        broke = (bar.close > extreme) if d > 0 else (bar.close < extreme)
        if broke:
            p.stall_broken = True
        if p.stall_bars_seen < self.spec.stall_window:
            return False

        # The window is complete: decide exactly once.
        p.stall_done = True
        if p.stall_broken:
            notes.append("stall window closed: a close broke the MFE bar extreme")
            return False

        new_target = p.fill_price + self.spec.stall_target * d
        already = (bar.close >= new_target) if d > 0 else (bar.close <= new_target)
        if already:
            # AMBIGUITY A10: the modified target is already marketable, so it is not a
            # resting order any more - it is an immediate close.
            self.book.modify_target(price=new_target, token=f"stall-{p.entry_bar}",
                                    reason="stall")
            p.target_price = new_target
            out.stall_modified = True
            self._close(bar, p, price=bar.close, reason=EXIT_STALL,
                        exit_slippage_points=self.spec.slippage_ticks_flatten *
                        self.spec.tick, ambiguous=False, out=out)
            notes.append(f"stall: target -> {new_target}, already through it, market close")
            return True

        self.book.modify_target(price=new_target, token=f"stall-{p.entry_bar}",
                                reason="stall")
        p.target_price = new_target
        out.stall_modified = True
        notes.append(f"stall: target -> {new_target}")
        return False

    def _close(self, bar: Bar, p: Position, *, price: float, reason: str,
               exit_slippage_points: float, ambiguous: bool, out: BarOutcome) -> None:
        """Book the exit, emit the canonical trade, and hand the result to the governor."""
        d, pv = p.direction, self.spec.point_value
        which = {EXIT_STOP: "stop", EXIT_TARGET: "target"}.get(reason, "flatten")
        order = self.book.fill_exit(which=which, price=price,
                                    token=f"exit-{p.entry_bar}", reason=reason)
        self.book.release()

        # GROSS is measured at the IDEAL prices - the levels before slippage moved the fills -
        # so that `gross - slippage - commission == net` holds the way it does everywhere else
        # in this repository, and slippage is visible as its own line rather than hidden
        # inside the fill.
        ideal_entry = p.fill_price - p.entry_slippage_points * d
        ideal_exit = price + exit_slippage_points * d
        gross = (ideal_exit - ideal_entry) * d * pv
        slippage = (p.entry_slippage_points + exit_slippage_points) * pv
        commission = self.spec.commission_round_turn
        net = gross - slippage - commission

        self._trade_id += 1
        day = trading_day(p.entry_time, self.spec.anchor_minute())
        # `pd.Timestamp` of an aware datetime is never NaT; the annotation says otherwise, so
        # the narrowing is done once here rather than at each of the two use sites.
        entry_ts = _stamp(p.entry_time)
        exit_ts = _stamp(bar.timestamp)
        self.fills.append(Fill(session=day, bar=self._bar_index, timestamp=exit_ts,
                               kind="EXIT", signed_quantity=float(-d * p.quantity),
                               price=price, reason=reason, cost=commission / 2.0))
        self.trades.append(LedgerTrade(
            trade_id=self._trade_id, session=day, direction=d, quantity=p.quantity,
            entry_bar=p.entry_bar, exit_bar=self._bar_index,
            entry_time=entry_ts, exit_time=exit_ts,
            entry_price=p.fill_price, exit_price=price,
            gross_pnl=gross, commission_and_spread=commission, slippage=slippage,
            net_pnl=net, mae=p.mae_points * pv, mfe=p.mfe_points * pv,
            r_multiple=((price - p.fill_price) * d) / self.spec.stop_points,
            exit_reason=reason, holding_minutes=self._bar_index - p.entry_bar,
            ambiguous_bar=ambiguous))

        self.position = None
        out.exited = reason
        _ = order

        self.governor.record_exit(net_pnl=net, when=bar.timestamp)
        if self.state is not State.HALTED_DAY:
            if self.governor.in_cooldown(bar.timestamp):
                self._to(State.COOLDOWN, bar.timestamp, "consecutive losses")
            else:
                self._to(State.FLAT_MONITORING, bar.timestamp, "position closed")
        # A realized loss alone can breach the killswitch once the position is gone.
        if not self.governor.halted and self.governor.killswitch_breached(0.0):
            self.governor.halt(bar.timestamp,
                               f"realized {self.governor.realized:+,.2f} at or below "
                               f"{self.spec.daily_loss_killswitch:+,.2f}")
            self._to(State.HALTED_DAY, bar.timestamp, "killswitch on realized")
            out.halted = True

    # =================================================================================
    # ENTRY
    # =================================================================================

    def _seek_entry(self, bar: Bar, out: BarOutcome, notes: list[str]) -> None:
        when = bar.timestamp

        if self.governor.halted:
            if self.state is not State.HALTED_DAY:
                self._to(State.HALTED_DAY, when, "governor halted")
            return
        if self.governor.must_hard_flatten(when):
            self.book.cancel_working(token=f"flat-{self._bar_index}",
                                     reason="hard flatten window")
            if self.state is not State.FLAT_MONITORING:
                self._to(State.FLAT_MONITORING, when, "hard flatten window")
            return
        if self.governor.in_cooldown(when):
            if self.state is not State.COOLDOWN:
                self._to(State.COOLDOWN, when, "cooldown")
            return
        if self.state is State.COOLDOWN:
            self._to(State.FLAT_MONITORING, when, "cooldown expired")

        verdict = self.governor.may_enter(when, position_open=False)
        if not verdict.allowed:
            if self.state in (State.ARMED_LONG, State.ARMED_SHORT):
                self._to(State.FLAT_MONITORING, when, "entry no longer permitted")
            return

        regime = self._context()
        vwap = self.vwap.value
        if regime is None or vwap != vwap:
            if self.state in (State.ARMED_LONG, State.ARMED_SHORT):
                self._to(State.FLAT_MONITORING, when, "context lost")
            return

        # --- invalidation, checked before arming or triggering ---------------------------
        if regime > 0 and bar.close < vwap - self.spec.invalidation_distance:
            self._to(State.FLAT_MONITORING, when, "long setup invalidated")
            notes.append("long invalidated")
            return
        if regime < 0 and bar.close > vwap + self.spec.invalidation_distance:
            self._to(State.FLAT_MONITORING, when, "short setup invalidated")
            notes.append("short invalidated")
            return

        self._to(State.ARMED_LONG if regime > 0 else State.ARMED_SHORT, when, "context")

        if self._trigger(bar, regime, vwap):
            self._enter(bar, regime, out, notes)

    def _context(self) -> int | None:
        """The 5-minute regime: +1 long, -1 short, None for neither.

        Reads the LAST COMPLETED 5-minute bar and the VWAP value recorded at its close - the
        same series the 1-minute trigger reads, by construction.
        """
        five = self.five_min.last_completed
        if five is None or not self.atr.ready:
            return None
        if self.atr.value < self.spec.atr_minimum:
            return None
        v = five.vwap_at_close
        if v != v:
            return None
        # AMBIGUITY A7: a 5m bar entirely on the right side of VWAP gives a NEGATIVE distance,
        # which passes `<= 6.0`. Implemented literally, as written.
        if five.close > v and (v - five.low) <= self.spec.context_max_distance:
            return 1
        if five.close < v and (five.high - v) <= self.spec.context_max_distance:
            return -1
        return None

    def _trigger(self, bar: Bar, regime: int, vwap: float) -> bool:
        """The 1-minute trigger bar. Four conditions, all on data available at its close."""
        if not self.volume_sma.ready:
            return False
        if bar.volume < self.spec.volume_multiple * self.volume_sma.value:
            return False

        if regime > 0:
            lo, hi = self.spec.long_zone
            if not (vwap + lo <= bar.close <= vwap + hi):     # AMBIGUITY A5: the close
                return False
            if bar.low > vwap:                                # AMBIGUITY A4: touch/penetrate
                return False
            if bar.close <= bar.open:                         # must close green
                return False
            prev = self._previous_bar()
            return prev is not None and bar.close > prev.high

        lo, hi = self.spec.short_zone
        if not (vwap + lo <= bar.close <= vwap + hi):
            return False
        if bar.high < vwap:
            return False
        if bar.close >= bar.open:                             # must close red
            return False
        prev = self._previous_bar()
        return prev is not None and bar.close < prev.low

    def _previous_bar(self) -> Bar | None:
        return self._history[-2] if len(self._history) >= 2 else None

    def _enter(self, bar: Bar, regime: int, out: BarOutcome, notes: list[str]) -> None:
        d = regime
        slip = self.spec.slippage_ticks_entry * self.spec.tick
        fill = bar.close + slip * d                    # adverse, by construction
        entry = self.book.submit_entry(direction=d, quantity=self.spec.contracts,
                                       fill_price=fill,
                                       token=f"entry-{self._bar_index}")
        bracket = self.book.attach_bracket(entry=entry, stop_points=self.spec.stop_points,
                                           target_points=self.spec.target_points,
                                           token=f"bracket-{self._bar_index}")
        self.position = Position(
            direction=d, quantity=self.spec.contracts, fill_price=fill,
            entry_time=bar.timestamp, entry_bar=self._bar_index,
            stop_price=bracket.stop.resting_price(),
            target_price=bracket.target.resting_price(),
            entry_slippage_points=slip)
        self.fills.append(Fill(
            session=trading_day(bar.timestamp, self.spec.anchor_minute()),
            bar=self._bar_index, timestamp=_stamp(bar.timestamp), kind="ENTRY",
            signed_quantity=float(d * self.spec.contracts), price=fill, reason="signal",
            cost=self.spec.commission_round_turn / 2.0))
        self.governor.record_entry(bar.timestamp)
        self._to(State.IN_POSITION, bar.timestamp, "trigger")
        out.entered = True
        notes.append(f"entry {d:+d} @ {fill}")

    # =================================================================================
    # DRIVING
    # =================================================================================

    def run(self, bars) -> list[BarOutcome]:
        """Feed a sequence of bars. The only way the engine ever sees more than one."""
        return [self.on_bar(b) for b in bars]

    @property
    def realized(self) -> float:
        return self.governor.realized

    def summary(self) -> str:
        wins = sum(1 for t in self.trades if t.net_pnl > 0)
        return (f"{len(self.trades)} trades, {wins} winners, "
                f"realized ${self.governor.realized:+,.2f}, state {self.state.value}")


__all__ = ["BE_ARMS_AFTER_THE_BAR", "BarOutcome", "EXIT_HARD_FLATTEN", "EXIT_KILLSWITCH",
           "EXIT_STALL", "EXIT_STOP", "EXIT_TARGET", "Engine", "IllegalTransition",
           "Position", "State", "TRANSITIONS"]
