"""A venue is what a place you can trade at DECLARES it can do - and nothing more.

`quant_brain.core.execution.ExecutionAdapter` is the order boundary: submit, working,
cancel_all. That is enough to route an intent and it is deliberately all the boundary says.
But a strategy, a reconciler and a HALT path need to ask other questions of a venue - what
positions does it hold, can it flatten everything, does it know the session calendar - and
today each of those questions is answered by whichever runner happens to be asking, with an
`if isinstance(adapter, ...)` or a try/except around a method that may not exist.

That is the failure this module prevents. Three of the audit findings in
`research/audit_2026-09-12.md` are the same defect wearing different clothes: code that
ASSUMED a capability the venue did not have, and got a silent default instead of a refusal.
AUD-05 marked a $30k long at $0 because a price lookup defaulted; AUD-06 double-sized because
"working" was assumed to mean "submitted"; the ProjectX adapter's own docstring calls an
empty position stub "the single most dangerous possible stub", because it looks like
agreement with any local state.

THE RULE
--------
A venue declares, at construction, the exact set of `Capability` members it supports, with a
sentence of evidence for each. Calling anything it did not declare raises `Unsupported`,
naming the venue and the capability. Nothing is emulated, approximated or defaulted. The
declaration is checked in BOTH directions when the venue is built:

    declared but not implemented  ->  refused at construction (a promise with no code behind it)
    implemented but not declared  ->  unreachable (code that exists is not the same as a
                                      capability the venue stands behind - ProjectX has a
                                      dry-run `submit` and it is NOT order submission)

WHY DECLARED RATHER THAN DISCOVERED
-----------------------------------
`hasattr(adapter, "positions")` would be the easy version and it is wrong in the way that
matters: it reports what code exists, not what the code has been verified to do. ProjectX
has a `reconcile` method; it raises. IBKR has `cancel_all`; it works. An attribute probe
cannot tell those apart, and a registry that ranks venues on attribute probes would rank on
the wrong thing. A declaration is a human-made claim with evidence attached, and the
registry can refuse one that contradicts the documentation (`registry.DOCUMENTED_ABSENCES`).

WHAT A VENUE IS NOT
-------------------
It is not permission. `Authority` (mode.py) decides whether this PROCESS may reach a venue;
`Capability` decides what the VENUE can do once reached. Keeping them apart is what stops
"we can authenticate" from sliding into "therefore we may trade" - `AUTH` is a capability
here precisely so it can be declared without implying anything about `ORDER_SUBMIT`.

It is also not a second path to the venue. `ORDER_SUBMIT` does not expose a raw `submit`;
it exposes `route()`, which builds the `RoutedExecutor` that every non-flatten order must
pass through. A venue abstraction that let a strategy call `venue.submit(intent)` would
reintroduce the exact bypass Part 16 forbids.
"""
from __future__ import annotations

import datetime as dt
import enum
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING

from quant_brain.core.calendar import Session
from quant_brain.core.execution import Ack, ExecutionAdapter, Fill, OrderIntent, RoutedExecutor
from quant_brain.core.idempotency import IntentJournal
from quant_brain.core.instruments import InstrumentSpec
from quant_brain.core.mode import Authority, Mode

if TYPE_CHECKING:  # pragma: no cover
    # Import-time circular: propfirm.py needs StrategyProfile from here, and a Venue carries
    # an optional rulebook from there. Type-only, the same shape execution.py uses for risk.
    from quant_brain.core.risk import RiskEngine
    from quant_brain.venues.propfirm import PropFirmRules


class Capability(str, enum.Enum):
    """Everything a venue might be able to do, as a closed list.

    Closed on purpose: a strategy's requirements and a venue's declaration must be drawn from
    the same vocabulary or the fit question cannot be asked. `str` mixin so a requirement
    round-trips through JSON as `"order_submit"` rather than an enum repr, matching the rest of
    the platform's serialised records.

    Several members look like they could be derived from others and deliberately are not:

      * FLATTEN_ALL is not ORDER_SUBMIT plus a loop. A loop over positions is racy against
        new fills (API_UNKNOWNS.md U5 says exactly this of ProjectX), and a HALT path that
        might leave a leg behind is not a HALT path.
      * FILLS is not EXECUTION_REPORTS. A fill is an execution; a report is the venue's
        statement about an order's state. Conflating them is AUD-06 at the boundary.
      * OPEN_ORDERS is remaining size, per `ExecutionAdapter.working`. Not submitted size.
      * AUTH implies nothing. ProjectX declares it and nothing else.
    """

    AUTH = "auth"
    ACCOUNTS = "accounts"
    BALANCES = "balances"
    POSITIONS = "positions"
    OPEN_ORDERS = "open_orders"
    HISTORICAL_DATA = "historical_data"
    REALTIME_DATA = "realtime_data"
    INSTRUMENTS = "instruments"
    ORDER_SUBMIT = "order_submit"
    ORDER_MODIFY = "order_modify"
    ORDER_CANCEL = "order_cancel"
    FILLS = "fills"
    EXECUTION_REPORTS = "execution_reports"
    TRADING_HOURS = "trading_hours"
    CONTRACT_SPECS = "contract_specs"
    FEES = "fees"
    MARGIN = "margin"
    RECONCILIATION = "reconciliation"
    FLATTEN_ALL = "flatten_all"
    BRACKET_ORDERS = "bracket_orders"


class Unsupported(RuntimeError):
    """The venue did not declare this capability. Never caught and worked around.

    Carries the venue and the capability as attributes so a caller that wants to choose a
    different venue can do so programmatically - but the message is written for the person
    reading a log at 09:31, because that is who usually meets it.
    """

    def __init__(self, venue: str, capability: Capability, *, note: str = ""):
        self.venue = venue
        self.capability = capability
        msg = (f"venue {venue!r} does not declare {capability.name}. An undeclared capability "
               f"is not emulated, approximated or defaulted: either choose a venue that "
               f"declares it, or extend this venue and change its declaration with evidence.")
        super().__init__(msg + (f" {note}" if note else ""))


@dataclass(frozen=True)
class Account:
    """One account at a venue, in the fields every venue can actually supply.

    `simulated` is carried because ProjectX makes it the only machine-readable distinction
    between a practice account and a funded one (API.md section 8.1), and `arm()` on that
    adapter refuses to proceed without it. A venue that cannot say is expected to leave the
    field None rather than guess - which is why it is Optional and not a bool.
    """

    id: str
    name: str = ""
    can_trade: bool | None = None
    simulated: bool | None = None


@dataclass(frozen=True)
class Reconciliation:
    """Local belief versus the venue's statement, symbol by symbol.

    Reports, never repairs. The ProjectX adapter's `reconcile` docstring has the reasoning:
    a difference means one side is wrong, and deleting the information that shows which is
    the worst available move. What to do about a disagreement is the caller's decision.
    """

    local: Mapping[str, float]
    venue: Mapping[str, float]
    diffs: Mapping[str, tuple[float, float]]

    @property
    def agrees(self) -> bool:
        return not self.diffs


@dataclass(frozen=True)
class StrategyProfile:
    """What a strategy needs from a venue, declared in the venue's own vocabulary.

    The counterpart of a venue's declaration. A venue says what it CAN do; a strategy says
    what it MUST have, and what shape its trading takes, so that a rulebook can be checked
    against it before any account is bought. Every field a rule might read is here rather
    than inferred, and an undeclared field is treated by `PropFirmRules.check` as
    "compliance cannot be shown" - not as compliant. That asymmetry is the whole point: a
    strategy that has not said when it opens risk cannot be certified clear of a news
    blackout by anyone's silence.

    Attributes:
        requires:  capabilities the strategy cannot run without.
        symbols:   roots it trades, in the platform's own symbols (not a venue's ids).
        max_contracts_per_symbol:  peak size it will ever hold per symbol.
        max_total_contracts:  peak size across all symbols; derived from the per-symbol peaks
                   when omitted, because a sum of peaks is an upper bound on the true peak.
        max_notional:  peak gross notional in dollars, if the strategy bounds it.
        holds_overnight / holds_weekend:  separate, because rulebooks separate them.
        flat_by_minutes_before_close:  how many minutes before the close the book is flat.
                   None means undeclared. 0 is a legitimate declaration (a MOC strategy).
        opens_risk_in:  exchange-local windows in which NEW risk is opened, the same clock as
                   `PropFirmProfile.blackout_windows`. Empty means undeclared.
    """

    name: str
    requires: frozenset[Capability]
    symbols: tuple[str, ...] = ()
    max_contracts_per_symbol: Mapping[str, int] = field(default_factory=dict)
    max_total_contracts: int | None = None
    max_notional: float | None = None
    holds_overnight: bool = False
    holds_weekend: bool = False
    flat_by_minutes_before_close: int | None = None
    opens_risk_in: tuple[tuple[dt.time, dt.time], ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("a StrategyProfile must be named; an anonymous fit report is "
                             "not auditable")
        bad = [c for c in self.requires if not isinstance(c, Capability)]
        if bad:
            # A string that happens to spell a member would pass a set-membership test
            # against a set of strings and fail it against a set of enums, depending on which
            # side was built first. Refuse the ambiguity at the door.
            raise TypeError(f"{self.name}: requires must contain Capability members, got "
                            f"{bad!r}")
        object.__setattr__(self, "requires", frozenset(self.requires))
        object.__setattr__(self, "max_contracts_per_symbol",
                           MappingProxyType(dict(self.max_contracts_per_symbol)))
        for sym, n in self.max_contracts_per_symbol.items():
            if n < 0:
                raise ValueError(f"{self.name}: negative peak size for {sym}")
        if self.holds_weekend and not self.holds_overnight:
            raise ValueError(f"{self.name}: holds_weekend without holds_overnight is not a "
                             f"shape a book can have")

    @property
    def peak_total_contracts(self) -> int | None:
        """The declared total, else the sum of per-symbol peaks, else None (undeclared)."""
        if self.max_total_contracts is not None:
            return self.max_total_contracts
        if self.max_contracts_per_symbol:
            return sum(self.max_contracts_per_symbol.values())
        return None


# =====================================================================================
# THE VENUE
# =====================================================================================

#: Capability -> (public method, hook the subclass implements). One hook per capability,
#: so the construction-time check "declared implies implemented" has exactly one thing to
#: look for, and the test suite can walk the table to prove every member is gated.
_HOOKS: dict[Capability, tuple[str, str]] = {
    Capability.AUTH: ("authenticate", "_authenticate"),
    Capability.ACCOUNTS: ("accounts", "_accounts"),
    Capability.BALANCES: ("balances", "_balances"),
    Capability.POSITIONS: ("positions", "_positions"),
    Capability.OPEN_ORDERS: ("open_orders", "_open_orders"),
    Capability.HISTORICAL_DATA: ("historical_bars", "_historical_bars"),
    Capability.REALTIME_DATA: ("subscribe", "_subscribe"),
    Capability.INSTRUMENTS: ("instruments", "_instruments"),
    Capability.ORDER_SUBMIT: ("route", "_route"),
    Capability.ORDER_MODIFY: ("modify", "_modify"),
    Capability.ORDER_CANCEL: ("cancel_all", "_cancel_all"),
    Capability.FILLS: ("fills", "_fills"),
    Capability.EXECUTION_REPORTS: ("execution_reports", "_execution_reports"),
    Capability.TRADING_HOURS: ("trading_hours", "_trading_hours"),
    Capability.CONTRACT_SPECS: ("contract_spec", "_contract_spec"),
    Capability.FEES: ("fees", "_fees"),
    Capability.MARGIN: ("margin", "_margin"),
    Capability.RECONCILIATION: ("reconcile", "_reconcile"),
    Capability.FLATTEN_ALL: ("flatten_all", "_flatten_all"),
    Capability.BRACKET_ORDERS: ("bracket", "_bracket"),
}


def hooks() -> Mapping[Capability, tuple[str, str]]:
    """The capability -> (public, hook) table, read-only. For tests and tooling."""
    return MappingProxyType(_HOOKS)


class Venue:
    """A place you can trade at, behind an explicit declaration of what it can do.

    Subclass, set `name`, and pass `declares` - a mapping from each supported `Capability`
    to a sentence of evidence saying where that support was verified (a code path, a
    documentation section with a retrieval date). Then implement the hook for each declared
    capability. Construction refuses:

      * a declaration with no evidence (a capability nobody can say why they believe in)
      * a declared capability whose hook was not overridden (a promise with no code)
      * a capability listed both as declared and as documented-only (contradiction)

    Every public method checks the declaration before doing anything else, and the check is
    the same one line, so it cannot be forgotten on the fifteenth method. The hooks exist so
    a subclass never has to remember to gate - it cannot reach its own implementation except
    through the gate.

    `documented_only` is for a venue like ProjectX whose API reference documents an
    endpoint the adapter has not implemented. It is NOT a capability - calling it raises like
    any other undeclared one - but the registry's fit report can then say "documented in
    API.md section 8.6, not implemented" instead of merely "missing", which is the difference
    between a gap that is a week of work and one that is impossible.
    """

    name: str = ""

    def __init__(self, adapter: ExecutionAdapter, *, declares: Mapping[Capability, str],
                 rules: PropFirmRules | None = None,
                 documented_only: Mapping[Capability, str] | None = None) -> None:
        if not self.name.strip():
            raise ValueError(f"{type(self).__name__} must set a non-empty `name`; the name is "
                             f"what the registry, the approval files and the fit report key on")
        self.adapter = adapter
        self.rules = rules
        checked: dict[Capability, str] = {}
        for cap, evidence in declares.items():
            if not isinstance(cap, Capability):
                raise TypeError(f"{self.name}: declares must be keyed by Capability, got "
                                f"{cap!r}")
            text = str(evidence).strip()
            if not text:
                raise ValueError(f"{self.name}: {cap.name} is declared with no evidence. A "
                                 f"declaration is a claim; a claim with no source is a guess, "
                                 f"and the registry ranks on these.")
            hook = _HOOKS[cap][1]
            if getattr(type(self), hook) is getattr(Venue, hook):
                raise ValueError(f"{self.name}: declares {cap.name} but does not implement "
                                 f"{hook}(). A declared capability with no code behind it "
                                 f"would fail at the first call instead of at construction.")
            checked[cap] = text
        self._declared: Mapping[Capability, str] = MappingProxyType(checked)

        doc: dict[Capability, str] = {}
        for cap, evidence in (documented_only or {}).items():
            if not isinstance(cap, Capability):
                raise TypeError(f"{self.name}: documented_only must be keyed by Capability")
            if cap in checked:
                raise ValueError(f"{self.name}: {cap.name} is both declared and listed as "
                                 f"documented-only; it cannot be both")
            doc[cap] = str(evidence).strip()
        self._documented_only: Mapping[Capability, str] = MappingProxyType(doc)

    # -- the declaration ----------------------------------------------------------------------

    @property
    def capabilities(self) -> frozenset[Capability]:
        return frozenset(self._declared)

    @property
    def evidence(self) -> Mapping[Capability, str]:
        """Why each declared capability is believed. Read-only."""
        return self._declared

    @property
    def documented_only(self) -> Mapping[Capability, str]:
        """Documented by the venue's API reference, NOT implemented here. Not capabilities."""
        return self._documented_only

    @property
    def requires(self) -> Mode:
        """The lowest Mode at which this venue may be reached. The adapter's word, not ours."""
        return self.adapter.requires

    def supports(self, capability: Capability) -> bool:
        return capability in self._declared

    def missing(self, required: frozenset[Capability]) -> frozenset[Capability]:
        """The subset of `required` this venue does not declare."""
        return frozenset(required) - self.capabilities

    def require(self, capability: Capability) -> None:
        """Raise `Unsupported` unless declared. The one line every public method starts with."""
        if capability not in self._declared:
            note = ""
            if capability in self._documented_only:
                note = (f"(documented by {self.name} but not implemented: "
                        f"{self._documented_only[capability]})")
            raise Unsupported(self.name, capability, note=note)

    def describe(self) -> str:
        caps = ", ".join(sorted(c.name for c in self._declared)) or "<nothing>"
        doc = ", ".join(sorted(c.name for c in self._documented_only))
        rules = f" rules={self.rules.name}" if self.rules is not None else ""
        return (f"{self.name} requires={self.requires.name}{rules} declares[{caps}]"
                + (f" documented_only[{doc}]" if doc else ""))

    # -- gated operations ------------------------------------------------------------------------
    # Each one: check the declaration, then delegate to the hook. The docstrings say what the
    # capability MEANS, because the meaning is what a subclass is signing up to.

    def authenticate(self, credentials: object | None = None) -> object:
        """AUTH: obtain a session. Grants nothing beyond what the venue's read calls need.

        Returns the venue's own connection-state object. Deliberately not a bool: "logged in"
        is a state with structure (ProjectX has seven), and flattening it to True is how a
        caller comes to believe AUTHENTICATED means "may trade".
        """
        self.require(Capability.AUTH)
        return self._authenticate(credentials)

    def accounts(self) -> Sequence[Account]:
        """ACCOUNTS: the accounts this session can see."""
        self.require(Capability.ACCOUNTS)
        return self._accounts()

    def balances(self) -> Mapping[str, float]:
        """BALANCES: named money figures. Keys are the venue's; at least "cash" and "equity".

        A venue that cannot compute equity because an open position has no mark must raise,
        not omit the position - AUD-05 is a $30k long marked at zero by a default.
        """
        self.require(Capability.BALANCES)
        return self._balances()

    def positions(self) -> Mapping[str, float]:
        """POSITIONS: signed quantity per symbol, as the VENUE states it. Empty means flat."""
        self.require(Capability.POSITIONS)
        return self._positions()

    def open_orders(self) -> Mapping[str, float]:
        """OPEN_ORDERS: signed quantity still on the wire per symbol. Remaining, not submitted.

        The same contract as `ExecutionAdapter.working`, and for the same reason: a sizer
        that nets the submitted amount against a half-filled order doubles up (AUD-06).
        """
        self.require(Capability.OPEN_ORDERS)
        return self._open_orders()

    def historical_bars(self, symbol: str, start: dt.datetime,
                        end: dt.datetime) -> Sequence[object]:
        """HISTORICAL_DATA: bars for `symbol` in [start, end]. Shape is the venue's."""
        self.require(Capability.HISTORICAL_DATA)
        return self._historical_bars(symbol, start, end)

    def subscribe(self, symbols: Sequence[str],
                  on_update: Callable[[str, object], None]) -> object:
        """REALTIME_DATA: stream updates for `symbols` to `on_update(symbol, payload)`."""
        self.require(Capability.REALTIME_DATA)
        return self._subscribe(symbols, on_update)

    def instruments(self) -> Sequence[str]:
        """INSTRUMENTS: the symbols this venue can resolve and trade right now."""
        self.require(Capability.INSTRUMENTS)
        return self._instruments()

    def route(self, risk: RiskEngine, *, authority: Authority,
              on_event: Callable[..., None] | None = None,
              journal: IntentJournal | None = None) -> RoutedExecutor:
        """ORDER_SUBMIT: the ONE way to send non-flatten orders through this venue.

        Returns a `RoutedExecutor`, so every intent passes the risk chain and the authority
        check at construction, exactly as it would without the venue layer. There is no
        `venue.submit(intent)`: a raw submit here would be a second path to the adapter and
        the architecture's central claim (one path, through risk) would be false.
        """
        self.require(Capability.ORDER_SUBMIT)
        return self._route(risk, authority=authority, on_event=on_event, journal=journal)

    def modify(self, executor: RoutedExecutor, broker_id: str, *,
               quantity: float | None = None, limit_price: float | None = None) -> Ack:
        """ORDER_MODIFY: change a working order's size or price.

        Takes the `RoutedExecutor` because a modify that GROWS an order is new risk, and new
        risk must pass the chain. A venue that could resize an order behind the risk layer's
        back would be a hole in it.
        """
        self.require(Capability.ORDER_MODIFY)
        return self._modify(executor, broker_id, quantity=quantity, limit_price=limit_price)

    def cancel_all(self) -> int:
        """ORDER_CANCEL: cancel every working order this venue placed. Returns the count sent.

        Matches the adapter boundary, which defines `cancel_all` and no per-order cancel;
        the venue follows the boundary rather than widening it here.
        """
        self.require(Capability.ORDER_CANCEL)
        return self._cancel_all()

    def fills(self) -> Sequence[Fill]:
        """FILLS: executions, as `Fill` records. What actually happened."""
        self.require(Capability.FILLS)
        return self._fills()

    def execution_reports(self) -> Sequence[Ack]:
        """EXECUTION_REPORTS: the venue's statements about orders. Not the same as fills."""
        self.require(Capability.EXECUTION_REPORTS)
        return self._execution_reports()

    def trading_hours(self, day: dt.date) -> Session | None:
        """TRADING_HOURS: the session for `day`, or None when closed. AUD-07's question."""
        self.require(Capability.TRADING_HOURS)
        return self._trading_hours(day)

    def contract_spec(self, symbol: str) -> InstrumentSpec:
        """CONTRACT_SPECS: the contractual terms of one instrument, from the venue."""
        self.require(Capability.CONTRACT_SPECS)
        return self._contract_spec(symbol)

    def fees(self, symbol: str) -> float:
        """FEES: the venue's stated cost per unit for `symbol`. A schedule, not a fill's fee."""
        self.require(Capability.FEES)
        return self._fees(symbol)

    def margin(self, symbol: str) -> float:
        """MARGIN: dollars of margin per unit of `symbol`, as the venue states it."""
        self.require(Capability.MARGIN)
        return self._margin(symbol)

    def reconcile(self, local_positions: Mapping[str, float]) -> Reconciliation:
        """RECONCILIATION: local belief against the venue's positions. Reports, never fixes."""
        self.require(Capability.RECONCILIATION)
        return self._reconcile(local_positions)

    def flatten_all(self, *, tag: str = "flatten") -> Sequence[Ack]:
        """FLATTEN_ALL: cancel everything working and close every position. The HALT path.

        Goes to the adapter directly rather than through a `RoutedExecutor`, and that is the
        one deliberate exception to "one path": FLATTEN intents bypass the risk chain by
        design (AUD-06 / AUD-08 - a risk layer that can block the exit is not a risk layer),
        and a HALT that first needed an authority object constructed would be a HALT that
        can fail to fire.
        """
        self.require(Capability.FLATTEN_ALL)
        return self._flatten_all(tag)

    def bracket(self, executor: RoutedExecutor, intent: OrderIntent, *,
                stop_price: float, target_price: float) -> Sequence[Ack]:
        """BRACKET_ORDERS: an entry with a protective stop and a target, as ONE venue-side unit.

        The parent goes through `executor` so the entry is risk-checked; the venue attaches
        the children. A bracket assembled from three separate submits is not a bracket - if
        the process dies between the second and third, the position is unprotected.
        """
        self.require(Capability.BRACKET_ORDERS)
        return self._bracket(executor, intent, stop_price=stop_price, target_price=target_price)

    # -- hooks ------------------------------------------------------------------------------------
    # Unreachable unless declared (the gate fires first) and refused at construction when
    # declared without being overridden. The NotImplementedError bodies therefore never run
    # in a correctly built venue; they exist so the table above has a definite target.

    def _authenticate(self, credentials: object | None) -> object:
        raise NotImplementedError("_authenticate")

    def _accounts(self) -> Sequence[Account]:
        raise NotImplementedError("_accounts")

    def _balances(self) -> Mapping[str, float]:
        raise NotImplementedError("_balances")

    def _positions(self) -> Mapping[str, float]:
        raise NotImplementedError("_positions")

    def _open_orders(self) -> Mapping[str, float]:
        raise NotImplementedError("_open_orders")

    def _historical_bars(self, symbol: str, start: dt.datetime,
                         end: dt.datetime) -> Sequence[object]:
        raise NotImplementedError("_historical_bars")

    def _subscribe(self, symbols: Sequence[str],
                   on_update: Callable[[str, object], None]) -> object:
        raise NotImplementedError("_subscribe")

    def _instruments(self) -> Sequence[str]:
        raise NotImplementedError("_instruments")

    def _route(self, risk: RiskEngine, *, authority: Authority,
               on_event: Callable[..., None] | None,
               journal: IntentJournal | None = None) -> RoutedExecutor:
        raise NotImplementedError("_route")

    def _modify(self, executor: RoutedExecutor, broker_id: str, *,
                quantity: float | None, limit_price: float | None) -> Ack:
        raise NotImplementedError("_modify")

    def _cancel_all(self) -> int:
        raise NotImplementedError("_cancel_all")

    def _fills(self) -> Sequence[Fill]:
        raise NotImplementedError("_fills")

    def _execution_reports(self) -> Sequence[Ack]:
        raise NotImplementedError("_execution_reports")

    def _trading_hours(self, day: dt.date) -> Session | None:
        raise NotImplementedError("_trading_hours")

    def _contract_spec(self, symbol: str) -> InstrumentSpec:
        raise NotImplementedError("_contract_spec")

    def _fees(self, symbol: str) -> float:
        raise NotImplementedError("_fees")

    def _margin(self, symbol: str) -> float:
        raise NotImplementedError("_margin")

    def _reconcile(self, local_positions: Mapping[str, float]) -> Reconciliation:
        raise NotImplementedError("_reconcile")

    def _flatten_all(self, tag: str) -> Sequence[Ack]:
        raise NotImplementedError("_flatten_all")

    def _bracket(self, executor: RoutedExecutor, intent: OrderIntent, *,
                 stop_price: float, target_price: float) -> Sequence[Ack]:
        raise NotImplementedError("_bracket")


def reconcile_positions(local: Mapping[str, float], venue: Mapping[str, float], *,
                        tolerance: float = 1e-9) -> Reconciliation:
    """Compare two position maps symbol by symbol. Shared so every venue diffs the same way.

    A symbol present on one side and absent on the other is a difference against zero, not
    a key error: "the venue has 3 MES and I have no record" is precisely the case a
    reconciler exists to surface.
    """
    diffs: dict[str, tuple[float, float]] = {}
    for sym in sorted(set(local) | set(venue)):
        a, b = float(local.get(sym, 0.0)), float(venue.get(sym, 0.0))
        if abs(a - b) > tolerance:
            diffs[sym] = (a, b)
    return Reconciliation(local=MappingProxyType(dict(local)),
                          venue=MappingProxyType(dict(venue)),
                          diffs=MappingProxyType(diffs))
