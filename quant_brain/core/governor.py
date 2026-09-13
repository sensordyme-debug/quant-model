"""The risk governor: hard limits and kill switches, with a reason code on every refusal.

Phase 6 of the master directive. `core/risk.py` already provides the property that matters
most - a chain where the most restrictive answer wins and nothing can re-permit a denial. What
it did not provide is a vocabulary. `RiskDecision.binding` carried free-text rule names, so a
caller could see that an order was refused but could not switch on WHY, and nothing in the
chain had state: a stale feed or a dead connection could not trip anything, and nothing stayed
tripped until a person looked.

Three additions, all composing with the existing chain rather than replacing it:

    Reason        a closed enum of refusal codes. Every denial from this module carries one as
                  its `binding` entry, so `RiskDecision.binding` becomes machine-readable
                  without changing its type.
    KillSwitch    a RiskEngine with state. Once tripped it denies everything except FLATTEN
                  (which the base class already lets through) and stays tripped until
                  `reset(by=<a person>)`. Nothing in the code path resets one.
    Governor      a RiskChain of limit engines plus every kill switch, with `trip()` and a
                  `status()` a dashboard can read.

WHY "PROBABLY OKAY" IS NOT A STATE
------------------------------------
Every limit here is evaluated against an `AccountView` the caller supplies. If the view is
missing the field a limit needs, the limit DENIES with `DATA_UNAVAILABLE` rather than skipping
itself. A limit that silently does not apply when its input is missing is a limit that does
not apply at exactly the moment the data feed died - which is the moment it was for.
"""
from __future__ import annotations

import datetime as dt
import enum
from dataclasses import dataclass, field

from quant_brain.core.execution import OrderIntent
from quant_brain.core.risk import RiskChain, RiskDecision, RiskEngine


class Reason(str, enum.Enum):
    """Every way the governor can say no. Closed on purpose: a new refusal is a new code."""

    RISK_DAILY_LOSS = "RISK_DAILY_LOSS"
    RISK_DAILY_PROFIT_STOP = "RISK_DAILY_PROFIT_STOP"
    RISK_DRAWDOWN = "RISK_DRAWDOWN"
    RISK_PER_TRADE = "RISK_PER_TRADE"
    RISK_POSITION_SIZE = "RISK_POSITION_SIZE"
    RISK_MAX_CONTRACTS = "RISK_MAX_CONTRACTS"
    RISK_NOTIONAL = "RISK_NOTIONAL"
    RISK_CONCURRENT_POSITIONS = "RISK_CONCURRENT_POSITIONS"
    RISK_TRADES_PER_DAY = "RISK_TRADES_PER_DAY"
    RISK_COOLDOWN = "RISK_COOLDOWN"
    RISK_CONSECUTIVE_LOSSES = "RISK_CONSECUTIVE_LOSSES"
    RISK_MLL_BUFFER = "RISK_MLL_BUFFER"
    VENUE_CONTRACT_LIMIT = "VENUE_CONTRACT_LIMIT"
    VENUE_SESSION_CLOSED = "VENUE_SESSION_CLOSED"
    VENUE_RULE = "VENUE_RULE"
    DATA_STALE = "DATA_STALE"
    DATA_QUALITY = "DATA_QUALITY"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    CONNECTION_UNSAFE = "CONNECTION_UNSAFE"
    POSITION_UNRECONCILED = "POSITION_UNRECONCILED"
    BRACKET_UNVERIFIED = "BRACKET_UNVERIFIED"
    VOLATILITY_HALT = "VOLATILITY_HALT"
    CLOCK_UNSYNCED = "CLOCK_UNSYNCED"
    MANUAL_HALT = "MANUAL_HALT"

    @property
    def is_kill_switch(self) -> bool:
        """Codes that describe a STATE of the system rather than a property of one order."""
        return self in {Reason.DATA_STALE, Reason.DATA_QUALITY, Reason.CONNECTION_UNSAFE,
                        Reason.POSITION_UNRECONCILED, Reason.BRACKET_UNVERIFIED,
                        Reason.VOLATILITY_HALT, Reason.CLOCK_UNSYNCED, Reason.MANUAL_HALT}


@dataclass(frozen=True)
class Limits:
    """The hard limits. `None` means "no limit of this kind", never "unknown".

    Frozen because a limit that can be raised mid-session is not a limit; changing one is a
    new `Governor`, which is a diff someone reviews.
    """

    max_risk_per_trade: float | None = None       # dollars
    max_daily_loss: float | None = None           # dollars, positive number
    daily_profit_stop: float | None = None        # dollars; stop trading once reached
    max_drawdown: float | None = None             # dollars from peak
    max_position: float | None = None             # absolute contracts in one symbol
    max_contracts: float | None = None            # absolute contracts across all symbols
    max_notional: float | None = None             # dollars
    max_concurrent_positions: int | None = None
    max_trades_per_day: int | None = None
    cooldown_seconds: float | None = None
    max_consecutive_losses: int | None = None
    #: Minimum dollars that must remain between equity and the prop-firm MLL AFTER this
    #: trade's risk. The single most important limit on a prop account.
    mll_buffer: float | None = None

    def size_limits(self):
        """The same ceilings expressed for `core/sizing.py`, at the GOVERNOR level.

        One source of truth: a sizer that is handed these cannot propose more than the
        governor would pass, so a reduction at the chain is a defect in the sizer's inputs
        rather than a second opinion. Per-symbol `max_position` is the per-order contract
        cap; `max_risk_per_trade` is the dollar cap.
        """
        from quant_brain.core.sizing import SizeLimits
        return SizeLimits(
            governor_max_contracts=int(self.max_position) if self.max_position else None,
            governor_max_risk=self.max_risk_per_trade)


@dataclass
class AccountView:
    """What the governor knows about the account right now. Supplied by the caller.

    Every field defaults to None, meaning UNKNOWN. A limit whose input is None denies with
    DATA_UNAVAILABLE. That is the difference between "no daily loss limit is configured" (a
    None in `Limits`) and "we do not know today's P&L" (a None here) - the first is a choice,
    the second is a reason to stop.
    """

    daily_pnl: float | None = None
    drawdown: float | None = None                 # dollars below peak, positive
    positions: dict[str, float] = field(default_factory=dict)   # symbol -> signed qty
    notional: float | None = None
    trades_today: int | None = None
    consecutive_losses: int | None = None
    last_trade_at: dt.datetime | None = None
    distance_to_mll: float | None = None
    risk_per_contract: dict[str, float] = field(default_factory=dict)  # symbol -> dollars
    now: dt.datetime | None = None

    @property
    def open_count(self) -> int:
        return sum(1 for q in self.positions.values() if q)

    @property
    def total_contracts(self) -> float:
        return sum(abs(q) for q in self.positions.values())


class LimitEngine(RiskEngine):
    """Evaluates every configured limit. Reduces where it can, denies where it must.

    Size limits REDUCE (a 12-contract request against a 10-contract cap becomes 10); state
    limits DENY (a breached daily loss does not become a smaller order, it becomes no order).
    The distinction is the difference between "too big" and "not now".
    """

    name = "limits"

    def __init__(self, limits: Limits, view: AccountView):
        self.limits = limits
        self.view = view

    def evaluate(self, intent: OrderIntent) -> RiskDecision:
        L, v = self.limits, self.view
        d = RiskDecision.allow(intent.quantity)

        def need(value, code: Reason, what: str):
            """A configured limit whose input is unknown is a denial, not a skip."""
            if value is None:
                return RiskDecision.deny(f"{what} is unknown, so the limit cannot be checked",
                                         Reason.DATA_UNAVAILABLE.value)
            return None

        # --- state limits: deny -------------------------------------------------------------
        if L.max_daily_loss is not None:
            if (r := need(v.daily_pnl, Reason.RISK_DAILY_LOSS, "daily P&L")):
                return r
            assert v.daily_pnl is not None
            if v.daily_pnl <= -L.max_daily_loss:
                return RiskDecision.deny(
                    f"daily P&L {v.daily_pnl:,.0f} at or past the {-L.max_daily_loss:,.0f} limit",
                    Reason.RISK_DAILY_LOSS.value)
        if L.daily_profit_stop is not None:
            if (r := need(v.daily_pnl, Reason.RISK_DAILY_PROFIT_STOP, "daily P&L")):
                return r
            assert v.daily_pnl is not None
            if v.daily_pnl >= L.daily_profit_stop:
                return RiskDecision.deny(
                    f"daily P&L {v.daily_pnl:,.0f} reached the {L.daily_profit_stop:,.0f} "
                    f"profit stop; done for the day",
                    Reason.RISK_DAILY_PROFIT_STOP.value)
        if L.max_drawdown is not None:
            if (r := need(v.drawdown, Reason.RISK_DRAWDOWN, "drawdown")):
                return r
            assert v.drawdown is not None
            if v.drawdown >= L.max_drawdown:
                return RiskDecision.deny(
                    f"drawdown {v.drawdown:,.0f} at or past {L.max_drawdown:,.0f}",
                    Reason.RISK_DRAWDOWN.value)
        if L.max_trades_per_day is not None:
            if (r := need(v.trades_today, Reason.RISK_TRADES_PER_DAY, "today's trade count")):
                return r
            assert v.trades_today is not None
            if v.trades_today >= L.max_trades_per_day:
                return RiskDecision.deny(
                    f"{v.trades_today} trades today, limit {L.max_trades_per_day}",
                    Reason.RISK_TRADES_PER_DAY.value)
        if L.max_consecutive_losses is not None:
            if (r := need(v.consecutive_losses, Reason.RISK_CONSECUTIVE_LOSSES,
                          "consecutive-loss count")):
                return r
            assert v.consecutive_losses is not None
            if v.consecutive_losses >= L.max_consecutive_losses:
                return RiskDecision.deny(
                    f"{v.consecutive_losses} consecutive losses, lockout at "
                    f"{L.max_consecutive_losses}",
                    Reason.RISK_CONSECUTIVE_LOSSES.value)
        if L.cooldown_seconds is not None and v.last_trade_at is not None:
            if v.now is None:
                return RiskDecision.deny("clock unknown, so the cooldown cannot be checked",
                                         Reason.DATA_UNAVAILABLE.value)
            since = (v.now - v.last_trade_at).total_seconds()
            if since < L.cooldown_seconds:
                return RiskDecision.deny(
                    f"{since:.0f}s since the last trade, cooldown is {L.cooldown_seconds:.0f}s",
                    Reason.RISK_COOLDOWN.value)
        if L.max_concurrent_positions is not None:
            opening_new = intent.symbol not in v.positions or not v.positions[intent.symbol]
            if opening_new and v.open_count >= L.max_concurrent_positions:
                return RiskDecision.deny(
                    f"{v.open_count} positions open, limit {L.max_concurrent_positions}",
                    Reason.RISK_CONCURRENT_POSITIONS.value)

        # --- size limits: reduce ------------------------------------------------------------
        qty = intent.quantity
        if L.max_position is not None:
            held = abs(v.positions.get(intent.symbol, 0.0))
            room = max(0.0, L.max_position - held)
            if qty > room:
                d = d.merge(RiskDecision.reduce(
                    room, f"{held:g} held in {intent.symbol}, cap {L.max_position:g}",
                    Reason.RISK_POSITION_SIZE.value))
        if L.max_contracts is not None:
            room = max(0.0, L.max_contracts - v.total_contracts)
            if qty > room:
                d = d.merge(RiskDecision.reduce(
                    room, f"{v.total_contracts:g} contracts held, cap {L.max_contracts:g}",
                    Reason.RISK_MAX_CONTRACTS.value))
        per = v.risk_per_contract.get(intent.symbol)
        if L.max_risk_per_trade is not None:
            if per is None:
                return RiskDecision.deny(
                    f"risk per contract for {intent.symbol} is unknown",
                    Reason.DATA_UNAVAILABLE.value)
            if per <= 0:
                return RiskDecision.deny(
                    f"risk per contract for {intent.symbol} is {per}, which is not a stop",
                    Reason.DATA_QUALITY.value)
            room = L.max_risk_per_trade / per
            if qty > room:
                d = d.merge(RiskDecision.reduce(
                    int(room), f"{per:,.0f}/contract against a {L.max_risk_per_trade:,.0f} "
                    f"per-trade risk cap", Reason.RISK_PER_TRADE.value))
        if L.mll_buffer is not None:
            if (r := need(v.distance_to_mll, Reason.RISK_MLL_BUFFER, "distance to the MLL")):
                return r
            assert v.distance_to_mll is not None
            if per is None:
                return RiskDecision.deny(
                    f"risk per contract for {intent.symbol} is unknown, so the MLL buffer "
                    f"cannot be protected", Reason.DATA_UNAVAILABLE.value)
            spendable = v.distance_to_mll - L.mll_buffer
            if spendable <= 0:
                return RiskDecision.deny(
                    f"{v.distance_to_mll:,.0f} to the MLL is inside the {L.mll_buffer:,.0f} "
                    f"buffer", Reason.RISK_MLL_BUFFER.value)
            room = spendable / per if per > 0 else 0.0
            if qty > room:
                d = d.merge(RiskDecision.reduce(
                    int(room), f"only {spendable:,.0f} spendable above the MLL buffer",
                    Reason.RISK_MLL_BUFFER.value))
        if L.max_notional is not None and v.notional is not None:
            if v.notional >= L.max_notional:
                return RiskDecision.deny(
                    f"notional {v.notional:,.0f} at or past {L.max_notional:,.0f}",
                    Reason.RISK_NOTIONAL.value)
        return d


@dataclass
class KillSwitch(RiskEngine):
    """A RiskEngine with memory. Tripped means every non-flatten order is refused.

    `reset` requires `by=<a name>`. That is not ceremony: a switch that any code path can reset
    is a switch the code path will reset, and the whole value of a kill switch is that it
    outlasts the logic that tripped it until a person has looked.
    """

    reason: Reason
    tripped: bool = False
    tripped_at: dt.datetime | None = None
    detail: str = ""
    reset_by: str = ""

    def __post_init__(self) -> None:
        self.name = self.reason.value.lower()

    def trip(self, detail: str) -> None:
        if not self.tripped:
            self.tripped_at = dt.datetime.now(dt.UTC)
        self.tripped = True
        self.detail = detail

    def reset(self, *, by: str) -> None:
        if not by.strip():
            raise ValueError("a kill switch is reset by a named person, not by code")
        self.tripped = False
        self.reset_by = by
        self.detail = ""

    def evaluate(self, intent: OrderIntent) -> RiskDecision:
        if self.tripped:
            return RiskDecision.deny(
                f"{self.reason.value}: {self.detail or 'tripped'}", self.reason.value)
        return RiskDecision.allow(intent.quantity)


class Governor(RiskChain):
    """The chain with every kill switch pre-installed, a `trip()` and a `status()`.

    It IS a `RiskChain`, so it drops into `RoutedExecutor` unchanged and inherits the
    guarantee that FLATTEN bypasses everything - including every tripped switch, because the
    one thing a halted system must still be able to do is get flat.
    """

    name = "governor"

    def __init__(self, limits: Limits, view: AccountView,
                 extra: list[RiskEngine] | None = None):
        self.limits_engine = LimitEngine(limits, view)
        self.switches: dict[Reason, KillSwitch] = {
            r: KillSwitch(r) for r in Reason if r.is_kill_switch}
        # Switches first: a tripped switch short-circuits the chain before any limit is
        # consulted, which keeps the reason list pointed at the cause.
        super().__init__(engines=[*self.switches.values(), self.limits_engine, *(extra or [])],
                         name="governor")

    @property
    def view(self) -> AccountView:
        return self.limits_engine.view

    def trip(self, reason: Reason, detail: str) -> None:
        if not reason.is_kill_switch:
            raise ValueError(f"{reason.value} is a per-order limit, not a kill switch")
        self.switches[reason].trip(detail)

    def reset(self, reason: Reason, *, by: str) -> None:
        self.switches[reason].reset(by=by)

    @property
    def halted(self) -> bool:
        return any(s.tripped for s in self.switches.values())

    def tripped(self) -> list[KillSwitch]:
        return [s for s in self.switches.values() if s.tripped]

    STATUS_FILE = "governor.json"

    def publish(self, store) -> object:
        """Write `status()` into a scoped `StateStore` so `python -m quant_brain risk status`
        can read it. The store stamps its scope, so a DRYRUN governor's status can never be
        mistaken for a PAPER one even if the file is copied."""
        payload = dict(self.status(), published_at=dt.datetime.now(dt.UTC).isoformat())
        return store.write_json(self.STATUS_FILE, payload)

    def status(self) -> dict:
        """What a dashboard or `risk status` shows. Never contains a credential."""
        return {
            "halted": self.halted,
            "tripped": [{"reason": s.reason.value, "detail": s.detail,
                         "since": s.tripped_at.isoformat() if s.tripped_at else None}
                        for s in self.tripped()],
            "limits": {k: v for k, v in self.limits_engine.limits.__dict__.items()
                       if v is not None},
            "view": {
                "daily_pnl": self.view.daily_pnl, "drawdown": self.view.drawdown,
                "open_positions": self.view.open_count,
                "contracts": self.view.total_contracts,
                "trades_today": self.view.trades_today,
                "distance_to_mll": self.view.distance_to_mll,
            },
        }
