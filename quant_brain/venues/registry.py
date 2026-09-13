"""The venues this platform knows, and the one question asked of them: which fits?

Two things live here. The concrete venues - the existing adapters wrapped with HONEST
capability declarations, each with the evidence for every claim - and the registry that
holds them and answers `best_fit(strategy)`.

THE DECLARATIONS ARE THE POINT
------------------------------
Each venue below declares the smallest set its adapter has actually been shown to do:

    simulated   everything an in-memory ledger can do honestly: it fills at a mark it was
                given, books positions with the multiplier it was given, and refuses to
                fill what it has no price or spec for. Not AUTH, not data, not margin.
    ibkr        ORDER_SUBMIT, OPEN_ORDERS, ORDER_CANCEL. That is the whole of
                `quant_brain/brokers/ibkr.py`. The connection and contract qualification
                are the caller's; positions and fills are never queried by the adapter.
    projectx    AUTH. One endpoint, the one the adapter implements and the one its docstring
                calls verified. Everything else the API documents is recorded as
                `documented_only` so the fit report can say "documented, not implemented"
                - and FLATTEN_ALL is recorded as documented ABSENT, per API_UNKNOWNS.md U5.

`DOCUMENTED_ABSENCES` is the registry's own knowledge: capabilities the documentation says
a venue does NOT have. `register()` refuses a venue that declares one. A declaration is a
claim, and a claim the documentation contradicts is not a claim the platform should rank on.

WHAT best_fit WILL NOT DO
-------------------------
It will not rank when nothing fits. A strategy that requires FLATTEN_ALL against a registry
with no venue declaring it gets `NoEligibleVenue` naming the gap, not a "closest match" that
would be acted on. It will not rank a venue whose rules the strategy violates - excluded,
with the rule named. And it will not rank on an objective it cannot compute: a Topstep venue
with no fee supplied raises `CannotRank` rather than sorting on None. Legitimate, compliant
fit only; everything else is a refusal with a reason.
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType

from quant_brain.brokers.ibkr import IBKRAdapter
from quant_brain.brokers.projectx import ProjectXAdapter
from quant_brain.core.calendar import Session, SessionCalendar
from quant_brain.core.execution import (
    Ack,
    ExecutionAdapter,
    Fill,
    OrderIntent,
    OrderType,
    Position,
    RoutedExecutor,
    Side,
    SimulatedAdapter,
)
from quant_brain.core.idempotency import IntentJournal
from quant_brain.core.instruments import InstrumentSpec
from quant_brain.core.mode import Authority, Mode
from quant_brain.core.risk import RiskEngine
from quant_brain.venues.base import (
    Account,
    Capability,
    Reconciliation,
    StrategyProfile,
    Venue,
    reconcile_positions,
)
from quant_brain.venues.propfirm import ObjectiveResult, Paths, PropFirmRules, TopstepRules

C = Capability


# =====================================================================================
# SIMULATED
# =====================================================================================

class LedgerAdapter(SimulatedAdapter):
    """`SimulatedAdapter` plus a fill model honest enough to answer POSITIONS and FILLS.

    The base simulator accepts everything and fills nothing, which is exactly right for
    testing the routing and exactly wrong for a venue that declares POSITIONS. This keeps the
    base's acks and ids and adds the minimum that makes the other capabilities true:

      * an order fills at the mark the caller supplied for its symbol, immediately if one is
        known and the order crosses it, otherwise when `mark()` next moves the price;
      * a fill is booked into a `Position` with the `InstrumentSpec` the caller supplied, so
        the multiplier is the instrument's and not an assumed 1.0;
      * a symbol with no spec is REJECTED at submit rather than booked at a guessed
        multiplier, and a symbol with no mark RESTS rather than filling at zero (AUD-05).

    No fill is ever invented. If a research run wants a cost model, `execution_sim.py` has
    the measured one; this ledger charges only the flat `fee_per_unit` it was told.
    """

    def __init__(self, *, specs: Mapping[str, InstrumentSpec] | None = None,
                 marks: Mapping[str, float] | None = None, fee_per_unit: float = 0.0,
                 reject: set[str] | None = None):
        super().__init__(reject=reject)
        self.specs: dict[str, InstrumentSpec] = dict(specs or {})
        self.marks: dict[str, float] = dict(marks or {})
        self.fee_per_unit = fee_per_unit
        self.positions: dict[str, Position] = {}
        self.fills: list[Fill] = []
        self.acks: list[Ack] = []
        #: broker_id -> intent still on the wire. The source of `working()`.
        self.resting: dict[str, OrderIntent] = {}

    def submit(self, intent: OrderIntent) -> Ack:
        if intent.symbol not in self.specs:
            ack = Ack(intent=intent, accepted=False,
                      reason=f"simulated venue has no InstrumentSpec for {intent.symbol}; "
                             f"a fill cannot be booked without a multiplier")
            self.acks.append(ack)
            return ack
        ack = super().submit(intent)
        self.acks.append(ack)
        if ack.accepted:
            self.resting[ack.broker_id] = intent
            self._try_fill(ack.broker_id)
        return ack

    @staticmethod
    def _crosses(intent: OrderIntent, mark: float) -> bool:
        if intent.order_type is OrderType.LIMIT:
            limit = intent.limit_price
            if limit is None:          # OrderIntent refuses this at construction
                return False
            return mark <= limit if intent.side is Side.BUY else mark >= limit
        return True                    # MARKET, FLATTEN and the auction types fill at the mark

    def _try_fill(self, broker_id: str) -> None:
        intent = self.resting[broker_id]
        mark = self.marks.get(intent.symbol)
        if mark is None or not self._crosses(intent, mark):
            return
        fill = Fill(symbol=intent.symbol, side=intent.side, quantity=intent.quantity,
                    price=mark, commission=self.fee_per_unit * intent.quantity, tag=intent.tag)
        pos = self.positions.setdefault(intent.symbol, Position(spec=self.specs[intent.symbol]))
        pos.apply(fill)
        self.fills.append(fill)
        del self.resting[broker_id]

    def mark(self, symbol: str, price: float) -> None:
        """Move a price; resting orders on that symbol fill if they now cross."""
        self.marks[symbol] = price
        for bid in [b for b, i in self.resting.items() if i.symbol == symbol]:
            self._try_fill(bid)

    def working(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for i in self.resting.values():
            out[i.symbol] = out.get(i.symbol, 0.0) + i.signed_quantity
        return {k: v for k, v in out.items() if v}

    def cancel(self, broker_id: str) -> bool:
        return self.resting.pop(broker_id, None) is not None

    def cancel_all(self) -> int:
        n = len(self.resting)
        self.resting.clear()
        return n

    def signed_positions(self) -> dict[str, float]:
        return {s: p.quantity for s, p in self.positions.items() if p.quantity}


class SimulatedVenue(Venue):
    """An in-memory venue. Declares what the ledger can do and, honestly, nothing else.

    Capabilities that depend on something the caller may not have supplied are declared
    only when it was: CONTRACT_SPECS and INSTRUMENTS need specs, TRADING_HOURS needs a
    calendar, FEES needs a fee. Declaring TRADING_HOURS on a venue with no calendar would be
    the AUD-07 defect in a new coat - a session length answered from nothing.

    Never AUTH, HISTORICAL_DATA, REALTIME_DATA, MARGIN or BRACKET_ORDERS: there is nothing
    to authenticate against, no store, no feed, no margin model, and a bracket whose stop
    can only trigger on marks the test itself supplies would be a bracket that tests the
    test.
    """

    name = "simulated"

    def __init__(self, *, specs: Mapping[str, InstrumentSpec] | None = None,
                 marks: Mapping[str, float] | None = None, cash: float = 0.0,
                 calendar: SessionCalendar | None = None, fee_per_unit: float | None = None,
                 rules: PropFirmRules | None = None, reject: set[str] | None = None,
                 name: str | None = None):
        if name:
            # Several simulated venues in one registry (different rulebooks) need
            # different names; the class attribute is the default, not a constraint.
            self.name = name
        self.ledger = LedgerAdapter(specs=specs, marks=marks,
                                    fee_per_unit=fee_per_unit or 0.0, reject=reject)
        self.cash = cash
        self.calendar = calendar
        self._fee = fee_per_unit
        ledger = "in-memory LedgerAdapter (quant_brain/venues/registry.py)"
        declares: dict[Capability, str] = {
            C.ACCOUNTS: f"{ledger}: one simulated account",
            C.BALANCES: f"{ledger}: cash plus realized, unrealized at supplied marks only",
            C.POSITIONS: f"{ledger}: Position.apply over booked fills",
            C.OPEN_ORDERS: f"{ledger}: resting orders, remaining size",
            C.ORDER_SUBMIT: f"{ledger}: SimulatedAdapter.submit, fills at the supplied mark",
            C.ORDER_MODIFY: f"{ledger}: cancel and resubmit through the RoutedExecutor",
            C.ORDER_CANCEL: f"{ledger}: resting orders dropped",
            C.FILLS: f"{ledger}: every booked Fill",
            C.EXECUTION_REPORTS: f"{ledger}: every Ack issued",
            C.RECONCILIATION: f"{ledger}: reconcile_positions against the booked positions",
            C.FLATTEN_ALL: f"{ledger}: cancel_all then a FLATTEN per open position",
        }
        if specs:
            declares[C.CONTRACT_SPECS] = "InstrumentSpecs supplied at construction"
            declares[C.INSTRUMENTS] = "the symbols with a supplied InstrumentSpec"
        if calendar is not None:
            declares[C.TRADING_HOURS] = f"SessionCalendar {calendar.name!r} supplied"
        if fee_per_unit is not None:
            declares[C.FEES] = f"flat fee_per_unit={fee_per_unit} supplied at construction"
        super().__init__(self.ledger, declares=declares, rules=rules)

    # -- convenience for tests and research ------------------------------------------------

    def mark(self, symbol: str, price: float) -> None:
        self.ledger.mark(symbol, price)

    # -- hooks -----------------------------------------------------------------------------------

    def _accounts(self) -> Sequence[Account]:
        return (Account(id="SIM", name=self.name, can_trade=True, simulated=True),)

    def _balances(self) -> Mapping[str, float]:
        realized = sum(p.realized for p in self.ledger.positions.values())
        unrealized = 0.0
        for sym, pos in self.ledger.positions.items():
            if pos.quantity == 0:
                continue
            mark = self.ledger.marks.get(sym)
            if mark is None:
                raise LookupError(f"{self.name}: no mark for the open {sym} position; a balance "
                                  f"that marked it at zero would be AUD-05")
            unrealized += pos.unrealized(mark)
        cash = self.cash + realized
        return {"cash": cash, "realized": realized, "unrealized": unrealized,
                "equity": cash + unrealized}

    def _positions(self) -> Mapping[str, float]:
        return self.ledger.signed_positions()

    def _open_orders(self) -> Mapping[str, float]:
        return self.ledger.working()

    def _instruments(self) -> Sequence[str]:
        return sorted(self.ledger.specs)

    def _route(self, risk: RiskEngine, *, authority: Authority,
               on_event: Callable[..., None] | None,
               journal: IntentJournal | None = None) -> RoutedExecutor:
        return RoutedExecutor(risk, self.ledger, authority=authority, on_event=on_event,
                              journal=journal)

    def _modify(self, executor: RoutedExecutor, broker_id: str, *,
                quantity: float | None, limit_price: float | None) -> Ack:
        if executor.adapter is not self.ledger:
            raise ValueError(f"{self.name}: the executor routes to {executor.adapter.name!r}, "
                             f"not to this venue")
        old = self.ledger.resting.get(broker_id)
        if old is None:
            raise KeyError(f"{self.name}: {broker_id!r} is not resting (filled, cancelled or "
                           f"never accepted); a modify of a done order is not a modify")
        new = OrderIntent(symbol=old.symbol, side=old.side,
                          quantity=old.quantity if quantity is None else quantity,
                          order_type=old.order_type,
                          limit_price=old.limit_price if limit_price is None else limit_price,
                          tag=old.tag, ts=old.ts)
        self.ledger.cancel(broker_id)
        acks = executor.submit([new])
        if acks:
            return acks[0]
        # Refused by the chain: the old order is gone and the new one never reached the
        # venue. Reported as a rejection carrying the chain's reasons, not swallowed.
        _, decision = executor.refused[-1]
        return Ack(intent=new, accepted=False,
                   reason="modify refused by the risk chain: " + "; ".join(decision.reasons))

    def _cancel_all(self) -> int:
        return self.ledger.cancel_all()

    def _fills(self) -> Sequence[Fill]:
        return tuple(self.ledger.fills)

    def _execution_reports(self) -> Sequence[Ack]:
        return tuple(self.ledger.acks)

    def _trading_hours(self, day: dt.date) -> Session | None:
        assert self.calendar is not None      # declared only when supplied
        return self.calendar.session(day)

    def _contract_spec(self, symbol: str) -> InstrumentSpec:
        return self.ledger.specs[symbol]

    def _fees(self, symbol: str) -> float:
        assert self._fee is not None          # declared only when supplied
        return self._fee

    def _reconcile(self, local_positions: Mapping[str, float]) -> Reconciliation:
        return reconcile_positions(local_positions, self.ledger.signed_positions())

    def _flatten_all(self, tag: str) -> Sequence[Ack]:
        self.ledger.cancel_all()
        acks = []
        for sym, q in self.ledger.signed_positions().items():
            intent = OrderIntent(symbol=sym, side=Side.of(-q), quantity=abs(q),
                                 order_type=OrderType.FLATTEN, tag=tag)
            acks.append(self.ledger.submit(intent))
        return tuple(acks)


# =====================================================================================
# IBKR
# =====================================================================================

class IBKRVenue(Venue):
    """Interactive Brokers, through `IBKRAdapter`. Three capabilities, because that is the code.

    What the adapter does NOT do, and why each absence is honest rather than lazy:

        AUTH            it takes an already-connected `ib`; connecting is the runner's job
        INSTRUMENTS     `contracts` is a caller-qualified map; the adapter resolves nothing
        POSITIONS       never queried. `RoutedExecutor.flatten` takes positions from the
                        caller precisely because the adapter has no view of them
        FILLS           `working()` reads `trade.fills` for SIZE only, and the test fakes
                        carry no price or side; turning those into `Fill` records would be
                        this wrapper reaching past the adapter into ib_async
        FLATTEN_ALL     no positions view, so no account-level flatten
        BRACKET_ORDERS  `build_ib_order` produces MKT, LMT, MOC and MOO. No children.

    Declaring any of those would make a strategy fit IBKR on paper and fail at 09:31.
    """

    name = "ibkr"

    def __init__(self, adapter: IBKRAdapter, *, rules: PropFirmRules | None = None):
        self.ibkr = adapter
        src = "quant_brain/brokers/ibkr.py"
        super().__init__(adapter, rules=rules, declares={
            C.ORDER_SUBMIT: f"IBKRAdapter.submit -> ib.placeOrder via build_ib_order ({src}); "
                            f"tif, outsideRth and orderRef set explicitly (2026-09-10 defect)",
            C.OPEN_ORDERS: f"IBKRAdapter.working: remaining size from executions, keyed by "
                           f"the caller's symbol (AUD-06) ({src})",
            C.ORDER_CANCEL: f"IBKRAdapter.cancel_all -> ib.cancelOrder for every unfilled "
                            f"trade this adapter placed ({src})",
        })

    def _route(self, risk: RiskEngine, *, authority: Authority,
               on_event: Callable[..., None] | None,
               journal: IntentJournal | None = None) -> RoutedExecutor:
        return RoutedExecutor(risk, self.ibkr, authority=authority, on_event=on_event,
                              journal=journal)

    def _open_orders(self) -> Mapping[str, float]:
        return self.ibkr.working()

    def _cancel_all(self) -> int:
        return self.ibkr.cancel_all()


# =====================================================================================
# PROJECTX / TOPSTEPX
# =====================================================================================

#: API.md sections that document an endpoint the adapter has NOT implemented. Recorded so
#: the fit report distinguishes "a week of verified work away" from "impossible", and so
#: nobody re-reads the docs to find out. None of these is a capability.
_PROJECTX_DOCUMENTED: dict[Capability, str] = {
    C.ACCOUNTS: "API.md 8.1 POST /api/Account/search; `simulated` is the practice flag",
    C.BALANCES: "API.md 8.1 TradingAccountModel.balance; cash vs net-liq semantics UNKNOWN (U15)",
    C.INSTRUMENTS: "API.md 8.2-8.4 Contract/search, searchById, available; ids are opaque",
    C.CONTRACT_SPECS: "API.md 8.3 ContractModel: tickSize and tickValue only, no multiplier, "
                      "no expiry (U15)",
    C.HISTORICAL_DATA: "API.md 8.5 POST /api/History/retrieveBars, 50 requests per 30 s, "
                       "newest-first, alignment UNKNOWN (U7)",
    C.ORDER_SUBMIT: "API.md 8.6 POST /api/Order/place; adapter.submit is a dry-run recorder "
                    "and raises NotPermitted on any live path by design",
    C.ORDER_MODIFY: "API.md 8.7 POST /api/Order/modify; no maximum-trail-distance guard",
    C.ORDER_CANCEL: "API.md 8.8 POST /api/Order/cancel; 'Only simulated accounts ... can "
                    "cancel orders through this endpoint' (U1)",
    C.OPEN_ORDERS: "API.md 8.10 POST /api/Order/searchOpen; omits Suspended bracket "
                   "children (U2)",
    C.POSITIONS: "API.md 8.13 POST /api/Position/searchOpen; adapter.working refuses until "
                 "verified",
    C.FILLS: "API.md 8.16 POST /api/Trade/search, half-turn rows; profitAndLoss null on an "
             "opening fill",
    C.EXECUTION_REPORTS: "API.md 10.2 GatewayUserOrder on the user hub; SignalR contract "
                         "UNKNOWN (U10)",
    C.REALTIME_DATA: "API.md 10.3 market hub GatewayQuote/Trade/Depth; book semantics "
                     "UNKNOWN (U9)",
    C.BRACKET_ORDERS: "API.md 8.6 stopLossBracket/takeProfitBracket; account must be in Auto "
                      "OCO mode, child linkage UNKNOWN (U3)",
    C.RECONCILIATION: "composite of API.md 8.10 and 8.13 with U2/U4 caveats; "
                      "adapter.reconcile refuses rather than stub an empty book",
}


class ProjectXVenue(Venue):
    """ProjectX / TopstepX, through `ProjectXAdapter`. One capability: AUTH.

    The adapter implements one endpoint, `POST /api/Auth/loginKey`, and its own module
    docstring is careful to say that is the only thing verified. So that is the only thing
    declared. The dry-run `submit` is deliberately NOT ORDER_SUBMIT: a recorder that never
    reaches a transport is a test fixture, and a venue that declared it as submission would
    let a strategy "fit" a venue that cannot send an order.

    The rulebook attached is Topstep's, because Topstep is the firm whose accounts this
    gateway reaches. The venue is still named after the adapter, since the same ProjectX
    protocol fronts other firms (API.md section 3) and the rules are what differ.
    """

    name = "projectx"

    def __init__(self, adapter: ProjectXAdapter | None = None, *,
                 rules: PropFirmRules | None = None):
        self.projectx = adapter or ProjectXAdapter.for_dry_run()
        super().__init__(self.projectx, rules=rules, documented_only=_PROJECTX_DOCUMENTED,
                         declares={
            C.AUTH: "ProjectXAdapter.authenticate -> POST /api/Auth/loginKey "
                    "(quant_brain/brokers/projectx.py AUTH_PATH), verified against "
                    "gateway.docs.projectx.com authenticate-api-key, retrieved 2026-09-13 "
                    "(docs/topstep/API.md 5.1). Grants read access and nothing else.",
        })

    def _authenticate(self, credentials: object | None) -> object:
        # The adapter's own type is Credentials | None; the venue passes through whatever
        # it was handed and lets the adapter be the one that refuses a wrong shape.
        return self.projectx.authenticate(credentials)  # type: ignore[arg-type]


# =====================================================================================
# WHAT THE DOCUMENTATION SAYS A VENUE DOES NOT HAVE
# =====================================================================================

#: Venue name -> capabilities the documentation says are ABSENT, with the finding quoted.
#: `register()` refuses any declaration that intersects this. Keyed by the canonical venue
#: name AND checked against the adapter's type, so renaming a wrapper does not slip past it.
DOCUMENTED_ABSENCES: Mapping[str, Mapping[Capability, str]] = MappingProxyType({
    "projectx": MappingProxyType({
        C.FLATTEN_ALL: (
            "docs/topstep/API_UNKNOWNS.md U5 (retrieved 2026-09-13): 'There is no "
            "Order/cancelAll, no Position/closeAll, and no account-level flatten in S1 or in "
            "S2's complete path list (21 operations, all enumerated in API.md section 7).' "
            "Flattening is documented only as iterating searchOpen + cancel and then "
            "positions + closeContract, which U5 notes is racy against new fills: an "
            "emulation, not a capability."),
        C.TRADING_HOURS: (
            "docs/topstep/API_UNKNOWNS.md U15: ContractModel has 'no trading-hours/session "
            "calendar'; API.md section 12: no S1 page for symbol/session calendars."),
        C.MARGIN: (
            "docs/topstep/API_UNKNOWNS.md U15: TradingAccountModel has 'no currency, no "
            "equity/margin fields'; no API surface for account risk rules exists in S2's "
            "21 operations."),
    }),
})

#: Adapter type -> the canonical venue name whose documented absences apply to it.
_CANONICAL: tuple[tuple[type[ExecutionAdapter], str], ...] = (
    (ProjectXAdapter, "projectx"),
    (IBKRAdapter, "ibkr"),
)


class ContradictsDocumentation(ValueError):
    """A venue declared a capability the documentation says it does not have."""

    def __init__(self, venue: str, contradicted: Mapping[Capability, str]):
        self.venue = venue
        self.contradicted = dict(contradicted)
        lines = [f"venue {venue!r} declares {', '.join(c.name for c in contradicted)}, which "
                 f"the documentation records as ABSENT. A declaration the documentation "
                 f"contradicts is refused; update the documentation with a source first."]
        lines.extend(f"  {c.name}: {why}" for c, why in contradicted.items())
        super().__init__("\n".join(lines))


class NoEligibleVenue(LookupError):
    """No registered venue can legitimately run this strategy. Never answered with a guess."""


class CannotRank(RuntimeError):
    """Eligible venues exist but the ranking basis cannot be computed for one of them."""


# =====================================================================================
# THE FIT REPORT
# =====================================================================================

@dataclass(frozen=True)
class Verdict:
    """One venue's answer to one strategy. Fits, or does not, and exactly why."""

    venue: str
    requires: Mode
    missing: tuple[Capability, ...] = ()
    violations: tuple[str, ...] = ()
    blocked: str = ""
    notes: tuple[str, ...] = ()
    objective: ObjectiveResult | None = None

    @property
    def fits(self) -> bool:
        return not self.missing and not self.violations and not self.blocked

    def reasons(self) -> list[str]:
        out = [f"{self.venue}: lacks {c.name}" for c in self.missing]
        out.extend(f"{self.venue}: {v}" for v in self.violations)
        if self.blocked:
            out.append(f"{self.venue}: {self.blocked}")
        out.extend(f"{self.venue}: {n}" for n in self.notes)
        return out


@dataclass(frozen=True)
class Fit:
    """The registry's full answer: who fits in what order, who does not and why, on what basis.

    `basis` is a sentence, not an enum, because the reader of a fit report is a person
    deciding whether to buy an evaluation, and "ranked by expected value after fees over
    1,000 paths" and "no paths supplied; ranked by the lowest Mode that fits" should not be
    distinguishable only by someone who knows the code.
    """

    strategy: str
    ranked: tuple[Verdict, ...]
    excluded: tuple[Verdict, ...]
    basis: str
    reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def best(self) -> Verdict:
        if not self.ranked:                     # best_fit raises before this can happen
            raise NoEligibleVenue(f"{self.strategy}: nothing ranked")
        return self.ranked[0]

    def describe(self) -> str:
        lines = [f"{self.strategy}: {self.basis}"]
        for i, v in enumerate(self.ranked, 1):
            score = ""
            if v.objective is not None and v.objective.score is not None:
                score = f"  score {v.objective.score:,.0f}"
            lines.append(f"  {i}. {v.venue} ({v.requires.name}){score}")
        for v in self.excluded:
            lines.append(f"  x  {v.venue}: " + "; ".join(v.reasons()))
        return "\n".join(lines)


# =====================================================================================
# THE REGISTRY
# =====================================================================================

class VenueRegistry:
    """name -> Venue, and the fit question. Holds declarations; never infers them."""

    def __init__(self) -> None:
        self._venues: dict[str, Venue] = {}

    # -- registration --------------------------------------------------------------------------

    @staticmethod
    def _absences_for(venue: Venue) -> dict[Capability, str]:
        out: dict[Capability, str] = dict(DOCUMENTED_ABSENCES.get(venue.name, {}))
        for cls, canonical in _CANONICAL:
            if isinstance(venue.adapter, cls):
                out.update(DOCUMENTED_ABSENCES.get(canonical, {}))
        return out

    def register(self, venue: Venue) -> Venue:
        """Add a venue. Refuses a duplicate name and a declaration the documentation denies."""
        if venue.name in self._venues:
            raise ValueError(f"a venue named {venue.name!r} is already registered; two venues "
                             f"with one name would make the approval files ambiguous")
        absent = self._absences_for(venue)
        contradicted = {c: absent[c] for c in sorted(venue.capabilities & set(absent),
                                                     key=lambda c: c.name)}
        if contradicted:
            raise ContradictsDocumentation(venue.name, contradicted)
        self._venues[venue.name] = venue
        return venue

    def get(self, name: str) -> Venue:
        try:
            return self._venues[name]
        except KeyError:
            raise KeyError(f"no venue named {name!r}; registered: "
                           f"{', '.join(self.names()) or '<none>'}") from None

    def names(self) -> list[str]:
        return list(self._venues)

    def __len__(self) -> int:
        return len(self._venues)

    def __contains__(self, name: object) -> bool:
        return name in self._venues

    def explain(self, name: str) -> str:
        """The declaration, its evidence, what is documented-only and what is documented absent."""
        v = self.get(name)
        lines = [v.describe()]
        lines.extend(f"  + {c.name:<18} {why}" for c, why in sorted(v.evidence.items(),
                                                                 key=lambda kv: kv[0].name))
        lines.extend(f"  ~ {c.name:<18} documented only: {why}"
                     for c, why in sorted(v.documented_only.items(), key=lambda kv: kv[0].name))
        lines.extend(f"  - {c.name:<18} documented ABSENT: {why}"
                     for c, why in sorted(self._absences_for(v).items(),
                                          key=lambda kv: kv[0].name))
        return "\n".join(lines)

    # -- the fit question ------------------------------------------------------------------------

    def fit(self, strategy: StrategyProfile, name: str, *, authority: Authority | None = None,
            paths: Paths | None = None) -> Verdict:
        """One venue's verdict on one strategy. No ranking, no refusal - just the answer."""
        return self._verdict(self.get(name), strategy, authority, paths)

    def _verdict(self, venue: Venue, strategy: StrategyProfile,
                 authority: Authority | None, paths: Paths | None) -> Verdict:
        missing = tuple(sorted(venue.missing(strategy.requires), key=lambda c: c.name))
        notes: list[str] = []
        absent = self._absences_for(venue)
        for cap in missing:
            if cap in venue.documented_only:
                notes.append(f"{cap.name} is documented but not implemented: "
                             f"{venue.documented_only[cap]}")
            if cap in absent:
                notes.append(f"{cap.name} is documented ABSENT: {absent[cap]}")
        blocked = ""
        if authority is not None and not authority.permits(venue.requires):
            blocked = (f"requires {venue.requires.name} and this process holds "
                       f"{authority.mode.name}")
        violations: list[str] = []
        if venue.rules is not None:
            violations.extend(venue.rules.check(strategy))
        objective: ObjectiveResult | None = None
        if (paths is not None and venue.rules is not None
                and not missing and not violations and not blocked):
            objective = venue.rules.objective().evaluate(paths)
            if not objective.acceptable:
                cap = objective.scoring.max_p_ruin
                violations.append(f"p_ruin {objective.p_ruin:.1%} exceeds the max_p_ruin "
                                  f"{cap:.1%} the scoring set")
        return Verdict(venue=venue.name, requires=venue.requires, missing=missing,
                       violations=tuple(violations), blocked=blocked, notes=tuple(notes),
                       objective=objective)

    def best_fit(self, strategy: StrategyProfile, *, authority: Authority | None = None,
                 paths: Paths | None = None) -> Fit:
        """Which registered venue legitimately fits this strategy, and in what order.

        Eligibility is decided from declarations and rules alone:

          1. the venue declares every capability the strategy requires - else it is
             excluded, and if NO venue passes this step the call raises `NoEligibleVenue`
             rather than ranking near-misses;
          2. if an `authority` is given, it permits the venue's required Mode;
          3. the venue's rulebook, if it has one, finds no violation in the strategy's
             declared shape - a violator is excluded and never ranked.

        Ranking among the eligible:

          * with `paths`: every eligible venue that has a rulebook is scored by its
            objective and ordered by `score` (see `Scoring`; the weights are on each
            verdict). A venue whose score cannot be computed - unknown fee, typically -
            raises `CannotRank`, because sorting None last would rank a venue on the very
            number it could not produce. Eligible venues WITHOUT a rulebook (a broker) have
            no evaluation to be paid on; they follow the scored ones, in registration order,
            and the basis says so.
          * without `paths`: ordered by the lowest Mode that fits, then registration order.
            The lowest rung of the ladder is the safest place to run the same strategy, and
            with no objective there is no other declared fact to prefer one venue by. The
            basis says this too, and says to pass `paths` for the prop-firm question.
        """
        if not self._venues:
            raise NoEligibleVenue(f"{strategy.name}: the registry is empty")
        order = {name: i for i, name in enumerate(self._venues)}
        verdicts = [self._verdict(v, strategy, authority, paths) for v in self._venues.values()]

        capable = [v for v in verdicts if not v.missing]
        if not capable:
            need = ", ".join(sorted(c.name for c in strategy.requires))
            detail = "\n".join("  " + r for v in verdicts for r in v.reasons())
            raise NoEligibleVenue(
                f"{strategy.name} requires [{need}] and no registered venue declares all of "
                f"them. Refusing to rank near-misses: a venue chosen for lacking the fewest "
                f"capabilities is still a venue that lacks one the strategy needs.\n{detail}")

        compliant = [v for v in verdicts if v.fits]
        excluded = tuple(v for v in verdicts if not v.fits)
        if not compliant:
            detail = "\n".join("  " + r for v in verdicts for r in v.reasons())
            raise NoEligibleVenue(
                f"{strategy.name}: every venue that declares the required capabilities is "
                f"excluded by its rules or by the process authority.\n{detail}")

        if paths is None:
            ranked = sorted(compliant, key=lambda v: (v.requires, order[v.venue]))
            basis = ("no paths supplied: ranked by the lowest execution Mode that fits, then "
                     "registration order; pass paths to rank prop-firm venues by objective")
            return Fit(strategy=strategy.name, ranked=tuple(ranked), excluded=excluded,
                       basis=basis, reasons=tuple(r for v in excluded for r in v.reasons()))

        scored: list[tuple[float, Verdict]] = []
        unscored: list[Verdict] = []
        for v in compliant:
            if v.objective is None:
                unscored.append(v)
                continue
            score = v.objective.score
            if score is None:
                raise CannotRank(
                    f"{strategy.name}: {v.venue} is eligible but its objective has no score: "
                    + "; ".join(v.objective.reasons))
            scored.append((score, v))
        scored.sort(key=lambda sv: (-sv[0], sv[1].objective.p_ruin if sv[1].objective else 0.0,
                                    order[sv[1].venue]))
        unscored.sort(key=lambda v: order[v.venue])
        n = len(list(paths))
        basis = (f"ranked by objective score over {n} paths (weights shown on each verdict's "
                 f"scoring)")
        if unscored:
            basis += (f"; {', '.join(v.venue for v in unscored)} fit but carry no rulebook, so "
                      f"they follow unscored in registration order")
        ranked = tuple(v for _, v in scored) + tuple(unscored)
        return Fit(strategy=strategy.name, ranked=ranked, excluded=excluded, basis=basis,
                   reasons=tuple(r for v in excluded for r in v.reasons()))


def default_registry(*, ib: object | None = None, ib_contracts: Mapping[str, object] | None = None,
                     projectx: ProjectXAdapter | None = None,
                     simulated: SimulatedVenue | None = None,
                     topstep_size: int = 50_000,
                     combine_fee: float | None = None) -> VenueRegistry:
    """The venues this repository can construct without a network.

    IBKR is included only when a connected `ib` is supplied, because `IBKRAdapter` takes
    one and there is no honest way to wrap an adapter that has nothing to place orders
    through. ProjectX defaults to a dry-run adapter with no transport, exactly as the
    adapter's own default, carrying Topstep's rulebook at `topstep_size`. The simulated
    venue, if not supplied, is a bare ledger with no specs - it will reject every order
    until specs are given, which is the honest state of a simulator nobody has configured.
    """
    reg = VenueRegistry()
    reg.register(simulated or SimulatedVenue())
    if ib is not None:
        reg.register(IBKRVenue(IBKRAdapter(ib, dict(ib_contracts or {}))))
    reg.register(ProjectXVenue(projectx, rules=TopstepRules(topstep_size,
                                                            combine_fee=combine_fee)))
    return reg


__all__ = [
    "DOCUMENTED_ABSENCES", "CannotRank", "ContradictsDocumentation", "Fit", "IBKRVenue",
    "LedgerAdapter", "NoEligibleVenue", "ProjectXVenue", "SimulatedVenue", "VenueRegistry",
    "Verdict", "default_registry",
]
