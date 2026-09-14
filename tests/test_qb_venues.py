"""Venues: a capability is declared or it does not exist, and fit is compliant fit only.

Adversarial by design. The module's claims are structural, so the tests attack the structure:

1. Every `Capability` is gated. A venue declaring nothing refuses all twenty, by name; a venue
   declaring everything reaches its own code for all twenty. A member added to the enum
   without a gate breaks the walk.
2. A declaration cannot lie in either direction: declared-without-code is refused at
   construction, and a dry-run `submit` is not ORDER_SUBMIT.
3. The registry refuses a declaration the documentation contradicts - ProjectX claiming
   FLATTEN_ALL against API_UNKNOWNS.md U5 - and the test reads the document to prove the
   quoted finding is really there.
4. `best_fit` raises on a capability gap, excludes every rule violator, refuses to rank on a
   score it cannot compute, and shows its weights on every verdict.
"""
from __future__ import annotations

import datetime as dt
import random
from pathlib import Path
from typing import Any

import pytest

from quant_brain.brokers.ibkr import IBKRAdapter
from quant_brain.brokers.projectx import ConnectionState, Credentials, ProjectXAdapter
from quant_brain.core.calendar import Session, SessionCalendar
from quant_brain.core.execution import OrderIntent, OrderType, Side
from quant_brain.core.mode import Authority, Mode, NotPermitted
from quant_brain.core.risk import RiskChain, RiskDecision, RiskEngine
from quant_brain.markets.futures_cme import instruments as fut
from quant_brain.markets.futures_cme import twin as tw
from quant_brain.markets.futures_cme.profiles import EOD_TRAILING_50K, INTRADAY_TRAILING_50K
from quant_brain.markets.futures_cme.propfirm import (
    PropFirmProfile,
    PropFirmRiskEngine,
    TrailingMode,
)
from quant_brain.venues import (
    DOCUMENTED_ABSENCES,
    CannotRank,
    Capability,
    ContradictsDocumentation,
    IBKRVenue,
    NoEligibleVenue,
    ProfileObjective,
    ProfileRules,
    ProjectXVenue,
    Scoring,
    SimulatedVenue,
    StrategyProfile,
    TopstepRules,
    TwinObjective,
    Unsupported,
    Venue,
    VenueRegistry,
    default_registry,
    hooks,
)
from quant_brain.venues.propfirm import windows_overlap

C = Capability
REPO = Path(__file__).resolve().parents[1]
UNKNOWNS = REPO / "docs" / "topstep" / "API_UNKNOWNS.md"
#: For calls whose arguments must never be touched because the gate fires first.
NA: Any = None
T0 = dt.datetime(2026, 1, 5, tzinfo=dt.UTC)
T1 = dt.datetime(2026, 1, 6, tzinfo=dt.UTC)

SPECS = {"MES": fut.get("MES").spec, "ES": fut.get("ES").spec}


def _buy(sym: str = "MES", qty: float = 1, **kw) -> OrderIntent:
    return OrderIntent(symbol=sym, side=Side.BUY, quantity=qty, **kw)


class Cap(RiskEngine):
    name = "cap"

    def __init__(self, n: float):
        self.n = n

    def evaluate(self, intent):
        if intent.quantity <= self.n:
            return RiskDecision.allow(intent.quantity)
        return RiskDecision.reduce(self.n, f"capped at {self.n:g}", "cap")


class Ban(RiskEngine):
    name = "ban"

    def evaluate(self, intent):
        return RiskDecision.deny("banned", "ban")


def _sim(**kw) -> SimulatedVenue:
    kw.setdefault("specs", SPECS)
    return SimulatedVenue(**kw)


def _routed(venue: Venue, *engines: RiskEngine):
    return venue.route(RiskChain(list(engines)), authority=Authority.backtest())


# ======================================================================================
# EVERY CAPABILITY IS GATED
# ======================================================================================

SAMPLE_ARGS: dict[Capability, tuple[tuple, dict]] = {
    C.AUTH: ((), {}),
    C.ACCOUNTS: ((), {}),
    C.BALANCES: ((), {}),
    C.POSITIONS: ((), {}),
    C.OPEN_ORDERS: ((), {}),
    C.HISTORICAL_DATA: (("MES", T0, T1), {}),
    C.REALTIME_DATA: ((["MES"], lambda s, p: None), {}),
    C.INSTRUMENTS: ((), {}),
    C.ORDER_SUBMIT: ((RiskChain(),), {"authority": Authority.backtest()}),
    C.ORDER_MODIFY: ((NA, "sim-1"), {}),
    C.ORDER_CANCEL: ((), {}),
    C.FILLS: ((), {}),
    C.EXECUTION_REPORTS: ((), {}),
    C.TRADING_HOURS: ((dt.date(2026, 1, 5),), {}),
    C.CONTRACT_SPECS: (("MES",), {}),
    C.FEES: (("MES",), {}),
    C.MARGIN: (("MES",), {}),
    C.RECONCILIATION: (({},), {}),
    C.FLATTEN_ALL: ((), {}),
    C.BRACKET_ORDERS: ((NA, _buy()), {"stop_price": 1.0, "target_price": 2.0}),
}


def test_the_enum_is_exactly_the_twenty_capabilities_the_directive_names():
    assert {c.name for c in Capability} == {
        "AUTH", "ACCOUNTS", "BALANCES", "POSITIONS", "OPEN_ORDERS", "HISTORICAL_DATA",
        "REALTIME_DATA", "INSTRUMENTS", "ORDER_SUBMIT", "ORDER_MODIFY", "ORDER_CANCEL", "FILLS",
        "EXECUTION_REPORTS", "TRADING_HOURS", "CONTRACT_SPECS", "FEES", "MARGIN",
        "RECONCILIATION", "FLATTEN_ALL", "BRACKET_ORDERS"}


def test_every_capability_has_exactly_one_public_gate_and_one_hook():
    table = hooks()
    assert set(table) == set(Capability), "a Capability with no gate can never be refused"
    assert set(SAMPLE_ARGS) == set(Capability), "this test must know how to call every gate"
    for cap, (public, hook) in table.items():
        assert callable(getattr(Venue, public)), (cap, public)
        assert callable(getattr(Venue, hook)), (cap, hook)
    assert len({p for p, _ in table.values()}) == len(table), "two capabilities share a gate"


class Nothing(Venue):
    name = "nothing"


def test_a_venue_declaring_nothing_refuses_every_capability_by_name():
    v = Nothing(SimulatedVenue().ledger, declares={})
    for cap, (public, _) in hooks().items():
        args, kw = SAMPLE_ARGS[cap]
        with pytest.raises(Unsupported) as e:
            getattr(v, public)(*args, **kw)
        assert e.value.venue == "nothing" and e.value.capability is cap
        assert "nothing" in str(e.value) and cap.name in str(e.value)
        assert "not emulated" in str(e.value)


class Everything(Venue):
    """Implements every hook with a sentinel, so the gate can be shown to DELEGATE."""

    name = "everything"
    SENTINEL = object()

    def __init__(self):
        super().__init__(SimulatedVenue().ledger,
                         declares={c: f"test sentinel for {c.name}" for c in Capability})

    def _sentinel(self, *a, **k):
        return self.SENTINEL

    for _cap, (_public, _hook) in hooks().items():
        locals()[_hook] = _sentinel
    del _cap, _public, _hook


def test_a_venue_declaring_everything_reaches_its_own_code_for_every_capability():
    v = Everything()
    assert v.capabilities == frozenset(Capability)
    for cap, (public, _) in hooks().items():
        args, kw = SAMPLE_ARGS[cap]
        assert getattr(v, public)(*args, **kw) is Everything.SENTINEL, cap


# ======================================================================================
# A DECLARATION CANNOT LIE
# ======================================================================================

def test_declaring_a_capability_without_implementing_it_is_refused_at_construction():
    class Promises(Venue):
        name = "promises"

    with pytest.raises(ValueError) as e:
        Promises(SimulatedVenue().ledger, declares={C.POSITIONS: "trust me"})
    assert "POSITIONS" in str(e.value) and "_positions" in str(e.value)


def test_a_declaration_with_no_evidence_is_refused():
    class Bare(Venue):
        name = "bare"

        def _positions(self):
            return {}

    with pytest.raises(ValueError) as e:
        Bare(SimulatedVenue().ledger, declares={C.POSITIONS: "   "})
    assert "no evidence" in str(e.value)


def test_a_capability_cannot_be_both_declared_and_documented_only():
    class Both(Venue):
        name = "both"

        def _positions(self):
            return {}

    with pytest.raises(ValueError) as e:
        Both(SimulatedVenue().ledger, declares={C.POSITIONS: "code"},
             documented_only={C.POSITIONS: "doc"})
    assert "both declared and listed as documented-only" in str(e.value)


def test_a_venue_without_a_name_is_refused():
    class Anon(Venue):
        pass

    with pytest.raises(ValueError):
        Anon(SimulatedVenue().ledger, declares={})


def test_declares_must_be_keyed_by_capability_not_by_string():
    with pytest.raises(TypeError):
        Nothing(SimulatedVenue().ledger, declares={"positions": "x"})  # type: ignore[dict-item]


def test_there_is_no_raw_submit_on_a_venue():
    """A venue.submit(intent) would be a second path to the adapter around the risk chain."""
    assert not hasattr(Venue, "submit")
    assert not hasattr(SimulatedVenue, "submit")


# ======================================================================================
# SIMULATED: EVERYTHING IT DECLARES IS TRUE IN MEMORY
# ======================================================================================

def test_simulated_fills_at_the_supplied_mark_and_books_the_position_with_the_multiplier():
    v = _sim(marks={"MES": 5000.0}, cash=1_000.0)
    ex = _routed(v)
    (ack,) = ex.submit([_buy("MES", 2)])
    assert ack.accepted
    assert v.positions() == {"MES": 2.0}
    assert len(v.fills()) == 1 and v.fills()[0].price == 5000.0
    v.mark("MES", 5001.0)                       # +1.00 x 2 contracts x $5 multiplier
    assert v.balances()["unrealized"] == pytest.approx(10.0)
    assert v.balances()["equity"] == pytest.approx(1_010.0)


def test_simulated_rejects_a_symbol_with_no_spec_rather_than_guessing_a_multiplier():
    v = _sim(marks={"ZB": 120.0})
    (ack,) = _routed(v).submit([_buy("ZB", 1)])
    assert not ack.accepted and "no InstrumentSpec" in ack.reason
    assert v.positions() == {}


def test_simulated_rests_an_order_with_no_mark_and_fills_when_one_arrives():
    """AUD-05: no price means no fill, never a fill at zero."""
    v = _sim()
    _routed(v).submit([_buy("MES", 3)])
    assert v.positions() == {} and v.open_orders() == {"MES": 3.0}
    v.mark("MES", 4990.0)
    assert v.positions() == {"MES": 3.0} and v.open_orders() == {}


def test_simulated_limit_orders_fill_only_when_the_mark_crosses():
    v = _sim(marks={"MES": 5000.0})
    ex = _routed(v)
    ex.submit([_buy("MES", 1, order_type=OrderType.LIMIT, limit_price=4990.0)])
    assert v.open_orders() == {"MES": 1.0}
    v.mark("MES", 4995.0)
    assert v.open_orders() == {"MES": 1.0}, "4995 does not cross a 4990 buy limit"
    v.mark("MES", 4989.0)
    assert v.positions() == {"MES": 1.0}


def test_simulated_balances_refuse_to_mark_an_open_position_at_zero():
    v = _sim(marks={"MES": 5000.0})
    _routed(v).submit([_buy("MES", 1)])
    v.ledger.marks.pop("MES")
    with pytest.raises(LookupError) as e:
        v.balances()
    assert "AUD-05" in str(e.value)


def test_simulated_flatten_all_cancels_working_and_closes_every_position():
    v = _sim(marks={"MES": 5000.0, "ES": 5000.0})
    ex = _routed(v)
    ex.submit([_buy("MES", 2), OrderIntent("ES", Side.SELL, 1),
               _buy("ES", 7, order_type=OrderType.LIMIT, limit_price=4000.0)])   # rests
    assert v.positions() == {"MES": 2.0, "ES": -1.0} and v.open_orders() == {"ES": 7.0}
    acks = v.flatten_all()
    assert v.open_orders() == {}, "the resting buy must be cancelled, not left to fill later"
    assert v.positions() == {}
    assert {a.intent.symbol for a in acks} == {"MES", "ES"}
    assert all(a.intent.order_type is OrderType.FLATTEN for a in acks)
    assert [a.intent.side for a in acks if a.intent.symbol == "ES"] == [Side.BUY]


def test_simulated_flatten_all_with_no_mark_rests_the_exit_rather_than_inventing_a_price():
    v = _sim(marks={"MES": 5000.0})
    _routed(v).submit([_buy("MES", 2)])
    v.ledger.marks.pop("MES")
    (ack,) = v.flatten_all()
    assert ack.accepted and v.positions() == {"MES": 2.0}
    assert v.open_orders() == {"MES": -2.0}, "the FLATTEN is on the wire, waiting for a price"
    v.mark("MES", 4999.0)
    assert v.positions() == {} and v.open_orders() == {}


def test_simulated_reconcile_reports_and_does_not_repair():
    v = _sim(marks={"MES": 5000.0})
    _routed(v).submit([_buy("MES", 2)])
    r = v.reconcile({"MES": 3.0, "ES": -1.0})
    assert not r.agrees
    assert r.diffs == {"MES": (3.0, 2.0), "ES": (-1.0, 0.0)}
    assert v.positions() == {"MES": 2.0}, "reconcile must not have touched the book"
    assert v.reconcile({"MES": 2.0}).agrees


def test_simulated_modify_goes_through_the_risk_chain():
    v = _sim()                                   # no mark: orders rest and can be modified
    ex = _routed(v, Cap(5))
    (ack,) = ex.submit([_buy("MES", 3)])
    grown = v.modify(ex, ack.broker_id, quantity=10)
    assert grown.accepted and grown.intent.quantity == 5, "the chain capped the modify"
    assert v.open_orders() == {"MES": 5.0}, "the old order is gone, the capped one rests"
    banned = v.modify(_routed(v, Ban()), grown.broker_id, quantity=4)
    assert not banned.accepted and "refused by the risk chain" in banned.reason
    assert v.open_orders() == {}
    with pytest.raises(KeyError):
        v.modify(ex, "sim-999")
    with pytest.raises(ValueError):
        v.modify(_routed(_sim()), "sim-1")       # an executor routed to a different venue


def test_simulated_conditional_capabilities_are_declared_only_when_supplied():
    bare = SimulatedVenue()
    for cap in (C.CONTRACT_SPECS, C.INSTRUMENTS, C.TRADING_HOURS, C.FEES):
        assert not bare.supports(cap)
    with pytest.raises(Unsupported):
        bare.trading_hours(dt.date(2026, 1, 5))

    class Always(SessionCalendar):
        name = "always"
        coverage_end = dt.date(2030, 1, 1)

        def is_trading_day(self, day):
            return True

        def session(self, day):
            return Session(day, dt.time(9, 30), dt.time(16, 0))

    full = _sim(calendar=Always(), fee_per_unit=0.62)
    assert full.trading_hours(dt.date(2026, 1, 5)) is not None
    assert full.fees("MES") == 0.62
    assert full.instruments() == ["ES", "MES"]
    assert full.contract_spec("ES").multiplier == 50.0
    assert not full.supports(C.AUTH) and not full.supports(C.MARGIN)
    assert not full.supports(C.HISTORICAL_DATA) and not full.supports(C.BRACKET_ORDERS)


def test_simulated_route_keeps_the_mode_ladder():
    v = _sim()
    with pytest.raises(NotPermitted):
        v.route(RiskChain(), authority=Authority.research())


def test_simulated_route_keeps_the_risk_chain_in_front_of_the_ledger():
    v = _sim(marks={"MES": 5000.0})
    _routed(v, Ban()).submit([_buy("MES", 1)])
    assert v.positions() == {} and v.execution_reports() == ()


# ======================================================================================
# IBKR: THREE CAPABILITIES, BECAUSE THAT IS THE CODE
# ======================================================================================

class FakeTrade:
    def __init__(self, contract, order, oid):
        self.contract, self.order = contract, order
        self.order.orderId = oid
        self.fills: list = []


class FakeIB:
    def __init__(self):
        self.placed: list = []
        self.cancelled: list = []
        self._oid = 0

    def placeOrder(self, contract, order):
        self._oid += 1
        t = FakeTrade(contract, order, self._oid)
        self.placed.append(t)
        return t

    def cancelOrder(self, order):
        self.cancelled.append(order)


def _ibkr():
    ib = FakeIB()
    return ib, IBKRVenue(IBKRAdapter(ib, {"MES": object()}, order_ref="TEST"))


def test_ibkr_declares_exactly_what_the_adapter_implements():
    _, v = _ibkr()
    assert v.capabilities == {C.ORDER_SUBMIT, C.OPEN_ORDERS, C.ORDER_CANCEL}
    assert v.requires is Mode.PAPER
    for cap in v.capabilities:
        assert "quant_brain/brokers/ibkr.py" in v.evidence[cap]


def test_ibkr_declared_capabilities_reach_the_adapter():
    ib, v = _ibkr()
    ex = v.route(RiskChain(), authority=Authority.paper("ibkr"))
    (ack,) = ex.submit([_buy("MES", 2)])
    assert ack.accepted and len(ib.placed) == 1
    assert v.open_orders() == {"MES": 2.0}
    assert v.cancel_all() == 1 and len(ib.cancelled) == 1


@pytest.mark.parametrize("cap", [C.AUTH, C.POSITIONS, C.FILLS, C.FLATTEN_ALL, C.INSTRUMENTS,
                                 C.BRACKET_ORDERS, C.RECONCILIATION])
def test_ibkr_refuses_what_the_adapter_never_implemented(cap):
    _, v = _ibkr()
    args, kw = SAMPLE_ARGS[cap]
    with pytest.raises(Unsupported) as e:
        getattr(v, hooks()[cap][0])(*args, **kw)
    assert e.value.venue == "ibkr" and e.value.capability is cap


# ======================================================================================
# PROJECTX: AUTH, AND A DRY RUN IS NOT ORDER SUBMISSION
# ======================================================================================

class FakeTransport:
    def __init__(self):
        self.calls: list = []

    def post(self, url, json=None, **kw):
        self.calls.append((url, json))
        return {"token": "TOKEN", "success": True, "errorCode": 0, "errorMessage": None}


def test_projectx_declares_only_auth():
    v = ProjectXVenue()
    assert v.capabilities == {C.AUTH}
    assert "loginKey" in v.evidence[C.AUTH] and "2026-09-13" in v.evidence[C.AUTH]
    assert v.requires is Mode.PRACTICE


def test_projectx_auth_reaches_the_adapter_and_grants_nothing_else():
    t = FakeTransport()
    v = ProjectXVenue(ProjectXAdapter(transport=t, dry_run=True))
    state = v.authenticate(Credentials(username="u", _api_key="k"))
    assert state is ConnectionState.AUTHENTICATED and t.calls
    for cap in (C.ORDER_SUBMIT, C.POSITIONS, C.FLATTEN_ALL, C.RECONCILIATION):
        args, kw = SAMPLE_ARGS[cap]
        with pytest.raises(Unsupported) as e:
            getattr(v, hooks()[cap][0])(*args, **kw)
        assert e.value.capability is cap


def test_projectx_dry_run_submit_is_not_order_submission():
    """The adapter HAS a submit; it records and never sends. The venue must not call it one."""
    v = ProjectXVenue()
    assert hasattr(v.adapter, "submit")
    assert not v.supports(C.ORDER_SUBMIT)
    with pytest.raises(Unsupported) as e:
        v.route(RiskChain(), authority=Authority.practice("topstep", "A"))
    assert "documented by projectx but not implemented" in str(e.value)
    assert "8.6" in str(e.value)
    assert v.projectx.would_send == [], "nothing may have been recorded as a dry run"


def test_projectx_documented_only_never_overlaps_a_documented_absence():
    v = ProjectXVenue()
    absent = set(DOCUMENTED_ABSENCES["projectx"])
    assert not (set(v.documented_only) & absent)
    assert C.FLATTEN_ALL in absent and C.FLATTEN_ALL not in v.documented_only


# ======================================================================================
# THE REGISTRY REFUSES A DECLARATION THE DOCUMENTATION CONTRADICTS
# ======================================================================================

def test_u5_is_really_in_the_unknowns_document_and_the_registry_quotes_it():
    text = UNKNOWNS.read_text(encoding="utf-8")
    assert "### U5. Is there any documented way to cancel all orders / flatten everything?" in text
    assert "There is no `Order/cancelAll`, no `Position/closeAll`, and no account-level flatten" in text
    why = DOCUMENTED_ABSENCES["projectx"][C.FLATTEN_ALL]
    assert "U5" in why and "Order/cancelAll" in why and "Position/closeAll" in why
    assert "21 operations" in why


def test_the_registry_refuses_projectx_claiming_flatten_all():
    class Liar(Venue):
        name = "projectx"

        def _flatten_all(self, tag):
            return ()

    reg = VenueRegistry()
    with pytest.raises(ContradictsDocumentation) as e:
        reg.register(Liar(ProjectXAdapter.for_dry_run(),
                          declares={C.FLATTEN_ALL: "iterate cancel then closeContract"}))
    msg = str(e.value)
    assert "FLATTEN_ALL" in msg and "U5" in msg and "cancelAll" in msg
    assert e.value.contradicted == {C.FLATTEN_ALL: DOCUMENTED_ABSENCES["projectx"][C.FLATTEN_ALL]}
    assert len(reg) == 0


def test_renaming_the_wrapper_does_not_get_past_the_documented_absence():
    """The check follows the adapter's type, not only the venue's name."""
    class Renamed(Venue):
        name = "topstep_gateway"

        def _flatten_all(self, tag):
            return ()

    with pytest.raises(ContradictsDocumentation):
        VenueRegistry().register(Renamed(ProjectXAdapter.for_dry_run(),
                                         declares={C.FLATTEN_ALL: "x"}))


def test_a_simulated_venue_named_projectx_is_held_to_the_same_documentation():
    reg = VenueRegistry()
    with pytest.raises(ContradictsDocumentation):
        reg.register(SimulatedVenue(name="projectx"))


def test_a_duplicate_name_is_refused():
    reg = VenueRegistry()
    reg.register(SimulatedVenue())
    with pytest.raises(ValueError):
        reg.register(SimulatedVenue())


def test_default_registry_is_offline_and_honest():
    reg = default_registry()
    assert set(reg.names()) == {"simulated", "projectx"}, "no ib, so no IBKR venue"
    assert reg.get("projectx").capabilities == {C.AUTH}
    rules = reg.get("projectx").rules
    assert rules is not None and rules.name == "TOPSTEP_COMBINE_50K"
    with pytest.raises(KeyError):
        reg.get("ibkr")
    text = reg.explain("projectx")
    assert "+ AUTH" in text and "~ ORDER_SUBMIT" in text and "- FLATTEN_ALL" in text


# ======================================================================================
# BEST FIT: COMPLIANT FIT ONLY
# ======================================================================================

def _strategy(requires=(C.ORDER_SUBMIT, C.OPEN_ORDERS), **kw) -> StrategyProfile:
    kw.setdefault("name", "S")
    kw.setdefault("symbols", ("MES",))
    kw.setdefault("max_contracts_per_symbol", {"MES": 2})
    kw.setdefault("flat_by_minutes_before_close", 20)
    kw.setdefault("opens_risk_in", ((dt.time(9, 35), dt.time(10, 30)),))
    return StrategyProfile(requires=frozenset(requires), **kw)


def _paths(*, seed: int, n: int = 12, days: int = 60, mu: float = 60.0,
           sigma: float = 250.0) -> list[list[tw.TwinDay]]:
    out = []
    for i in range(n):
        rng = random.Random(seed * 1000 + i)
        pnl = [rng.gauss(mu, sigma) for _ in range(days)]
        out.append(tw.days_from_pnl(pnl, path_fn=tw.u_shaped_path(1.4)))
    return out


def test_best_fit_refuses_rather_than_ranks_on_a_capability_gap():
    reg = default_registry()
    with pytest.raises(NoEligibleVenue) as e:
        reg.best_fit(_strategy(requires=(C.ORDER_SUBMIT, C.HISTORICAL_DATA)))
    msg = str(e.value)
    assert "HISTORICAL_DATA" in msg and "near-misses" in msg
    assert "simulated: lacks HISTORICAL_DATA" in msg
    assert "projectx: lacks HISTORICAL_DATA" in msg and "documented but not implemented" in msg


def test_best_fit_refuses_on_an_empty_registry():
    with pytest.raises(NoEligibleVenue):
        VenueRegistry().best_fit(_strategy())


def test_best_fit_never_ranks_a_venue_whose_rules_the_strategy_violates():
    reg = VenueRegistry()
    reg.register(_sim(name="sim_eod", rules=ProfileRules(EOD_TRAILING_50K)))
    reg.register(_sim(name="sim_free"))
    overnight = _strategy(holds_overnight=True)
    fit = reg.best_fit(overnight)
    assert [v.venue for v in fit.ranked] == ["sim_free"]
    (ex,) = fit.excluded
    assert ex.venue == "sim_eod" and any("holds overnight" in r for r in ex.violations)
    assert any("sim_eod" in r and "overnight" in r for r in fit.reasons)


def test_best_fit_refuses_when_every_capable_venue_is_excluded_by_its_rules():
    reg = VenueRegistry()
    reg.register(_sim(name="sim_eod", rules=ProfileRules(EOD_TRAILING_50K)))
    with pytest.raises(NoEligibleVenue) as e:
        reg.best_fit(_strategy(holds_overnight=True))
    assert "excluded by its rules" in str(e.value) and "overnight" in str(e.value)


def test_best_fit_honours_the_process_authority():
    reg = VenueRegistry()
    _, ib = _ibkr()
    reg.register(ib)
    reg.register(_sim())
    fit = reg.best_fit(_strategy(), authority=Authority.backtest())
    assert [v.venue for v in fit.ranked] == ["simulated"]
    assert fit.excluded[0].venue == "ibkr" and "PAPER" in fit.excluded[0].blocked
    fit = reg.best_fit(_strategy(), authority=Authority.paper("ibkr"))
    assert {v.venue for v in fit.ranked} == {"ibkr", "simulated"}


def test_without_paths_the_lowest_mode_that_fits_ranks_first_and_the_basis_says_so():
    reg = VenueRegistry()
    _, ib = _ibkr()
    reg.register(ib)                              # PAPER, registered first
    reg.register(_sim())                          # BACKTEST
    fit = reg.best_fit(_strategy())
    assert [v.venue for v in fit.ranked] == ["simulated", "ibkr"]
    assert fit.best.venue == "simulated"
    assert "no paths supplied" in fit.basis and "lowest execution Mode" in fit.basis
    assert "simulated" in fit.describe()


def test_with_paths_venues_are_ranked_by_objective_and_the_weights_are_visible():
    reg = VenueRegistry()
    reg.register(_sim(name="sim_eod", rules=ProfileRules(EOD_TRAILING_50K)))
    priced = Scoring(ruin_penalty=10_000.0)
    reg.register(_sim(name="sim_intraday",
                      rules=ProfileRules(INTRADAY_TRAILING_50K, scoring=priced)))
    reg.register(_sim(name="sim_broker"))       # no rulebook: fits, follows unscored
    paths = _paths(seed=1)
    fit = reg.best_fit(_strategy(), paths=paths)

    scored = [v for v in fit.ranked if v.objective is not None]
    assert [v.venue for v in scored] and fit.ranked[-1].venue == "sim_broker"
    scores = []
    for v in scored:
        assert v.objective is not None and v.objective.score is not None
        scores.append(v.objective.score)
    assert scores == sorted(scores, reverse=True), "ranked by score, descending"
    assert "objective score" in fit.basis and "sim_broker" in fit.basis

    by_name = {v.venue: v for v in scored}
    eod, intraday = by_name["sim_eod"].objective, by_name["sim_intraday"].objective
    assert eod is not None and intraday is not None
    assert eod.scoring == Scoring() and intraday.scoring == priced
    assert intraday.scoring.ruin_penalty == 10_000.0
    ev = intraday.expected_value_after_fees
    assert ev is not None
    assert intraday.score == pytest.approx(ev - 10_000.0 * intraday.p_ruin)
    assert eod.score == pytest.approx(eod.expected_value_after_fees)
    assert "ruin_penalty" in intraday.summary()


def test_best_fit_refuses_to_rank_on_a_score_it_cannot_compute():
    """Topstep with no fee: eligible, compliant, and unrankable. CannotRank, not None-last."""
    reg = VenueRegistry()
    reg.register(_sim(name="sim_topstep", rules=TopstepRules(50_000)))
    # 50 minutes, not the helper's default 20. Topstep's mandatory flat is 15:10 CT, which is
    # 50 minutes before a 16:00 CT close, and the static checker now enforces the same
    # deadline the runtime gate does. A 20-minute flatten is a real violation, so with the
    # default this strategy is EXCLUDED and the test can no longer reach the ranking question
    # it exists to ask.
    s = _strategy(opens_risk_in=(), flat_by_minutes_before_close=50)
    with pytest.raises(CannotRank) as e:
        reg.best_fit(s, paths=_paths(seed=2))
    assert "fee" in str(e.value).lower()
    reg2 = VenueRegistry()
    reg2.register(_sim(name="sim_topstep", rules=TopstepRules(50_000, combine_fee=49.0)))
    fit = reg2.best_fit(s, paths=_paths(seed=2))
    obj = fit.best.objective
    assert obj is not None and obj.expected_value_after_fees is not None


def test_a_ruin_constraint_in_the_scoring_excludes_rather_than_ranks():
    reg = VenueRegistry()
    strict = ProfileRules(EOD_TRAILING_50K, scoring=Scoring(max_p_ruin=0.0))
    reg.register(_sim(name="sim_strict", rules=strict))
    reg.register(_sim(name="sim_free"))
    losing = _paths(seed=3, mu=-150.0, sigma=300.0)
    fit = reg.best_fit(_strategy(), paths=losing)
    assert [v.venue for v in fit.ranked] == ["sim_free"]
    (ex,) = fit.excluded
    assert any("p_ruin" in v and "max_p_ruin" in v for v in ex.violations)


def test_fit_gives_one_venues_verdict_without_ranking():
    reg = default_registry()
    # 50 minutes for the same reason as above: this asks about CAPABILITIES, and a strategy
    # excluded on the flat deadline never gets far enough to report a missing capability.
    v = reg.fit(_strategy(requires=(C.AUTH,), flat_by_minutes_before_close=50), "projectx")
    assert v.fits and v.missing == ()
    v = reg.fit(_strategy(flat_by_minutes_before_close=50), "projectx")
    assert not v.fits and v.missing == (C.OPEN_ORDERS, C.ORDER_SUBMIT)


# ======================================================================================
# THE OBJECTIVE COMPOSES THE TWIN
# ======================================================================================

def test_twin_objective_agrees_with_evaluate_twin_and_shows_its_weights():
    twin = tw.TopstepTwin(50_000, combine_fee=49.0)
    paths = _paths(seed=4)
    ev = tw.evaluate_twin(twin, paths)
    res = TwinObjective(twin, scoring=Scoring(days_penalty=1.0)).evaluate(paths)
    assert res.paths == len(paths)
    assert res.p_pass == ev.p_pass_combine
    assert res.expected_payout == ev.mean_gross
    assert res.expected_value_after_fees == ev.mean_net
    assert 0.0 <= res.p_ruin <= res.p_violation <= 1.0, "ruin is a subset of violation"
    assert res.scoring.days_penalty == 1.0
    ev_net = res.expected_value_after_fees
    assert ev_net is not None
    if res.expected_days is None:
        assert res.score is None, "days_penalty with no resolved paths cannot be charged"
    else:
        assert res.score == pytest.approx(ev_net - res.expected_days)
    assert "value_weight" in res.summary()


def test_twin_objective_with_no_fee_has_no_value_after_fees_and_says_why():
    res = TwinObjective(tw.TopstepTwin(50_000)).evaluate(_paths(seed=5))
    assert res.expected_value_after_fees is None and res.score is None
    assert any("fee unknown" in r for r in res.reasons)


def test_profile_objective_treats_a_violation_as_ruin_and_reports_the_fee_basis():
    res = ProfileObjective(EOD_TRAILING_50K).evaluate(_paths(seed=6))
    assert res.p_ruin == res.p_violation
    assert res.expected_value_after_fees is not None
    assert res.expected_payout == pytest.approx(
        res.expected_value_after_fees + EOD_TRAILING_50K.evaluation_fee)
    assert any("single-evaluation" in r for r in res.reasons)


def test_profile_objective_flags_a_zero_fee_and_missing_intraday_paths():
    free = PropFirmProfile(name="FREE", starting_balance=50_000.0, max_drawdown=2_000.0,
                           trailing_mode=TrailingMode.INTRADAY, profit_target=3_000.0)
    bare = [[tw.TwinDay(d.day, d.pnl) for d in p] for p in _paths(seed=7)]
    res = ProfileObjective(free).evaluate(bare)
    assert any("evaluation_fee is 0" in r for r in res.reasons)
    assert any("no intraday path" in r for r in res.reasons)


def test_an_objective_over_no_paths_is_refused():
    with pytest.raises(ValueError):
        ProfileObjective(EOD_TRAILING_50K).evaluate([])
    with pytest.raises(ValueError):
        TwinObjective(tw.TopstepTwin(50_000)).evaluate([[]])


@pytest.mark.parametrize("kw", [{"value_weight": 0.0}, {"value_weight": -1.0},
                                {"ruin_penalty": -1.0}, {"days_penalty": -0.5},
                                {"max_p_ruin": 1.5}])
def test_scoring_refuses_weights_that_would_rank_on_nonsense(kw):
    with pytest.raises(ValueError):
        Scoring(**kw)


def test_scoring_default_is_expected_value_after_fees_and_nothing_else():
    s = Scoring()
    assert s.as_dict() == {"value_weight": 1.0, "ruin_penalty": 0.0, "days_penalty": 0.0,
                           "max_p_ruin": None}
    assert s.score(expected_value_after_fees=123.0, p_ruin=0.9, expected_days=400) == 123.0
    assert s.score(expected_value_after_fees=None, p_ruin=0.0, expected_days=1) is None


# ======================================================================================
# THE RULES CHECK: UNDECLARED IS NOT COMPLIANT
# ======================================================================================

def test_a_fully_declared_compliant_strategy_has_no_violations():
    assert ProfileRules(EOD_TRAILING_50K).check(_strategy()) == []


def test_each_rule_dimension_is_checked_against_the_declared_shape():
    rules = ProfileRules(EOD_TRAILING_50K)      # 5 total, ES 5, MES 50, blackouts, flat 15
    def v(**kw):
        return rules.check(_strategy(**kw))

    assert any("holds overnight" in x for x in v(holds_overnight=True))
    assert any("weekend" in x for x in v(holds_overnight=True, holds_weekend=True))
    assert any("cannot be shown" in x for x in v(flat_by_minutes_before_close=None))
    assert any("flat only 5 min" in x for x in v(flat_by_minutes_before_close=5))
    assert any("ES peak 6" in x for x in v(max_contracts_per_symbol={"ES": 6}))
    assert any("day-one cap of 5" in x for x in v(max_contracts_per_symbol={"MES": 4, "ES": 4}))
    assert any("does not declare when it opens risk" in x for x in v(opens_risk_in=()))
    assert any("overlaps the 08:28-08:33 blackout" in x
               for x in v(opens_risk_in=((dt.time(8, 0), dt.time(8, 30)),)))
    assert any("overlaps the 13:58-14:03 blackout" in x
               for x in v(opens_risk_in=((dt.time(14, 3), dt.time(15, 0)),))), "inclusive edge"


def test_undeclared_size_cannot_be_shown_compliant():
    out = ProfileRules(EOD_TRAILING_50K).check(_strategy(max_contracts_per_symbol={}))
    assert any("declares no peak size" in x for x in out)


def test_notional_and_ladder_rules_bind_on_day_one():
    ladder = PropFirmProfile(name="LADDER", starting_balance=50_000.0, max_notional=100_000.0,
                             scaling=((0.0, 2), (1_500.0, 5)), allow_overnight=True,
                             allow_weekend=True)
    rules = ProfileRules(ladder)
    s = _strategy(max_contracts_per_symbol={"MES": 3}, max_notional=None)
    out = rules.check(s)
    assert any("day-one cap of 2" in x for x in out)
    assert any("declares no max_notional" in x for x in out)
    assert rules.check(_strategy(max_contracts_per_symbol={"MES": 2},
                                 max_notional=50_000.0)) == []


def test_window_overlap_is_inclusive_and_midnight_aware():
    late = (dt.time(23, 50), dt.time(0, 10))
    assert windows_overlap(late, (dt.time(0, 5), dt.time(0, 20)))
    assert windows_overlap(late, (dt.time(23, 0), dt.time(23, 50)))
    assert not windows_overlap(late, (dt.time(0, 11), dt.time(1, 0)))
    assert windows_overlap((dt.time(8, 28), dt.time(8, 33)), (dt.time(8, 33), dt.time(9, 0)))


def test_topstep_rules_check_both_stages_and_expose_the_unresolved_rules():
    rules = TopstepRules(50_000)
    assert [p.name for p in rules.stages()] == ["TOPSTEP_COMBINE_50K", "TOPSTEP_XFA_50K"]
    assert rules.profile.name == "TOPSTEP_COMBINE_50K"
    out = rules.check(_strategy(holds_overnight=True, opens_risk_in=()))
    assert any("TOPSTEP_COMBINE_50K" in x for x in out)
    assert any("TOPSTEP_XFA_50K" in x for x in out)
    assert len(out) == len(set(out)), "one message per distinct violation"
    assert "xfa_scaling_plan" in rules.unresolved()
    assert isinstance(rules.risk_engine(), PropFirmRiskEngine)


def test_strategy_profile_refuses_shapes_that_cannot_be_checked():
    with pytest.raises(TypeError):
        StrategyProfile(name="s", requires=frozenset({"order_submit"}))  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        StrategyProfile(name="s", requires=frozenset(), holds_weekend=True)
    with pytest.raises(ValueError):
        StrategyProfile(name=" ", requires=frozenset())
    s = StrategyProfile(name="s", requires=frozenset(), max_contracts_per_symbol={"MES": 3, "ES": 1})
    assert s.peak_total_contracts == 4
    assert StrategyProfile(name="s", requires=frozenset()).peak_total_contracts is None
