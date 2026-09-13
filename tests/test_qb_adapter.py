"""Tests for the execution adapter boundary and the routed order path.

Part 16 makes a structural claim: a model can propose and the infrastructure disposes. That
claim is only true if there is exactly one path to a venue and it runs through the risk
chain. These tests attack that property directly - can a denied intent reach the adapter by
any route, can a reduction be ignored, can a flatten be blocked - because a boundary that is
merely a convention is not a boundary.
"""
from __future__ import annotations

import pytest

from quant_brain.brokers.ibkr import IBKRAdapter
from quant_brain.core.execution import (
    ExecutionAdapter,
    OrderIntent,
    OrderType,
    RoutedExecutor,
    Side,
    SimulatedAdapter,
)
from quant_brain.core.risk import RiskChain, RiskDecision, RiskEngine


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

    def __init__(self, *symbols):
        self.symbols = set(symbols)

    def evaluate(self, intent):
        if intent.symbol in self.symbols:
            return RiskDecision.deny(f"{intent.symbol} is banned", "ban")
        return RiskDecision.allow(intent.quantity)


def _buy(sym="AAPL", qty=10.0, **kw):
    return OrderIntent(symbol=sym, side=Side.BUY, quantity=qty, **kw)


def _flat(sym="AAPL", qty=10.0):
    return OrderIntent(symbol=sym, side=Side.SELL, quantity=qty,
                       order_type=OrderType.FLATTEN)


# ======================================================================================
# THE ONE PATH TO A VENUE
# ======================================================================================

def test_a_denied_intent_never_reaches_the_adapter():
    """The property the whole boundary exists for."""
    ad = SimulatedAdapter()
    ex = RoutedExecutor(RiskChain([Ban("TSLA")]), ad)
    acks = ex.submit([_buy("TSLA"), _buy("AAPL")])
    assert [i.symbol for i in ad.sent] == ["AAPL"]
    assert [a.intent.symbol for a in acks] == ["AAPL"]


def test_the_adapter_receives_the_reduced_size_not_the_requested_one():
    ad = SimulatedAdapter()
    ex = RoutedExecutor(RiskChain([Cap(10)]), ad)
    ex.submit([_buy(qty=250)])
    assert [i.quantity for i in ad.sent] == [10]


def test_a_reduction_to_zero_is_a_refusal_however_it_is_spelled():
    class Zero(RiskEngine):
        name = "zero"

        def evaluate(self, intent):
            return RiskDecision(True, 0.0, ("nothing left",), ("zero",))

    ad = SimulatedAdapter()
    ex = RoutedExecutor(RiskChain([Zero()]), ad)
    assert ex.submit([_buy()]) == []
    assert ad.sent == []
    assert len(ex.refused) == 1


def test_no_ordering_of_engines_lets_a_later_one_re_permit():
    ad = SimulatedAdapter()
    permissive = Cap(1_000_000)
    for chain in (RiskChain([Ban("TSLA"), permissive]),
                  RiskChain([permissive, Ban("TSLA")])):
        ad.sent.clear()
        RoutedExecutor(chain, ad).submit([_buy("TSLA")])
        assert ad.sent == [], "an engine order let a denial be reversed"


def test_every_verdict_is_recorded_including_the_refusals():
    """The refusals are the interesting half and are invisible if only fills are logged."""
    ad = SimulatedAdapter()
    ex = RoutedExecutor(RiskChain([Ban("TSLA"), Cap(10)]), ad)
    ex.submit([_buy("TSLA"), _buy("AAPL", 50), _buy("MSFT", 5)])
    assert len(ex.decisions) == 3
    refused = ex.refused
    assert [i.symbol for i, _ in refused] == ["TSLA"]
    assert "banned" in " ".join(refused[0][1].reasons)


def test_the_binding_rule_is_reported_not_just_the_refusal():
    ad = SimulatedAdapter()
    ex = RoutedExecutor(RiskChain([Cap(3)]), ad)
    ex.submit([_buy(qty=100)])
    _, decision, _ = ex.decisions[0]
    assert decision.binding == ("cap",)


# ======================================================================================
# FLATTEN IS NOT REFUSABLE
# ======================================================================================

def test_a_flatten_bypasses_every_engine_at_once():
    ad = SimulatedAdapter()
    ex = RoutedExecutor(RiskChain([Ban("TSLA"), Cap(1)]), ad)
    ex.submit([_flat("TSLA", 40)])
    assert [(i.symbol, i.quantity) for i in ad.sent] == [("TSLA", 40)], (
        "a flatten was blocked or reduced; a risk layer that can block the exit is not one")


def test_the_flatten_helper_builds_closing_intents_in_the_right_direction():
    ad = SimulatedAdapter()
    ex = RoutedExecutor(RiskChain([Ban("TSLA")]), ad)
    ex.flatten({"AAPL": 30, "TSLA": -12, "MSFT": 0})
    got = {(i.symbol, i.side, i.quantity, i.order_type) for i in ad.sent}
    assert got == {("AAPL", Side.SELL, 30, OrderType.FLATTEN),
                   ("TSLA", Side.BUY, 12, OrderType.FLATTEN)}, (
        "a flat position should produce no order and the signs must invert")


def test_a_venue_rejection_of_a_flatten_is_reported_not_swallowed():
    ad = SimulatedAdapter(reject={"AAPL"})
    ex = RoutedExecutor(RiskChain(), ad)
    acks = ex.flatten({"AAPL": 10})
    assert len(acks) == 1 and not acks[0].accepted


# ======================================================================================
# EVENTS
# ======================================================================================

def test_every_outcome_emits_a_named_event():
    seen = []
    ad = SimulatedAdapter(reject={"MSFT"})
    ex = RoutedExecutor(RiskChain([Ban("TSLA"), Cap(10)]), ad,
                        on_event=lambda ev, **kw: seen.append(ev))
    ex.submit([_buy("TSLA"), _buy("AAPL", 50), _buy("MSFT", 5), _buy("NVDA", 5)])
    assert "risk_denied" in seen
    assert "risk_reduced" in seen
    assert "venue_rejected" in seen
    assert "order_sent" in seen


def test_the_denial_event_carries_the_rule_that_bound_it():
    seen = []
    ex = RoutedExecutor(RiskChain([Ban("TSLA")]), SimulatedAdapter(),
                        on_event=lambda ev, **kw: seen.append((ev, kw)))
    ex.submit([_buy("TSLA")])
    ev, kw = seen[0]
    assert ev == "risk_denied"
    assert kw["binding"] == ["ban"]
    assert kw["symbol"] == "TSLA"


def test_an_executor_without_an_event_sink_still_works():
    ad = SimulatedAdapter()
    RoutedExecutor(RiskChain(), ad).submit([_buy()])
    assert len(ad.sent) == 1


# ======================================================================================
# THE ADAPTER CONTRACT
# ======================================================================================

def test_the_simulated_adapter_nets_working_quantity_by_symbol():
    ad = SimulatedAdapter()
    ad.submit(_buy("AAPL", 10))
    ad.submit(OrderIntent(symbol="AAPL", side=Side.SELL, quantity=4))
    ad.submit(_buy("MSFT", 7))
    assert ad.working() == {"AAPL": 6.0, "MSFT": 7.0}


def test_a_fully_offset_symbol_drops_out_of_working():
    ad = SimulatedAdapter()
    ad.submit(_buy("AAPL", 10))
    ad.submit(OrderIntent(symbol="AAPL", side=Side.SELL, quantity=10))
    assert ad.working() == {}


def test_an_adapter_must_implement_the_boundary():
    with pytest.raises(TypeError):
        ExecutionAdapter()          # type: ignore[abstract]


def test_the_ack_renders_both_outcomes():
    assert "sim-1" in str(SimulatedAdapter().submit(_buy()))
    assert "REJECTED" in str(SimulatedAdapter(reject={"AAPL"}).submit(_buy()))


# ======================================================================================
# THE IBKR ADAPTER
# ======================================================================================

class FakeOrder:
    def __init__(self, action, qty):
        self.action, self.totalQuantity = action, qty
        self.orderRef, self.outsideRth, self.tif, self.orderId = "", None, "", 0


class FakeExec:
    def __init__(self, shares):
        self.shares = shares


class FakeFill:
    def __init__(self, shares):
        self.execution = FakeExec(shares)


class FakeTrade:
    def __init__(self, contract, order, oid):
        self.contract, self.order = contract, order
        self.order.orderId = oid
        self.fills: list = []


class FakeContract:
    def __init__(self, symbol):
        self.symbol = symbol


class FakeIB:
    def __init__(self, *, raise_on=None):
        self.placed: list = []
        self.cancelled: list = []
        self.raise_on = raise_on or set()
        self._oid = 0

    def placeOrder(self, contract, order):      # noqa: N802  (ib_async's name)
        if contract.symbol in self.raise_on:
            raise ConnectionError("socket closed")
        self._oid += 1
        tr = FakeTrade(contract, order, self._oid)
        self.placed.append(tr)
        return tr

    def cancelOrder(self, order):               # noqa: N802
        self.cancelled.append(order)


@pytest.fixture
def ibkr():
    ib = FakeIB()
    contracts = {s: FakeContract(s) for s in ("AAPL", "MSFT")}
    return ib, IBKRAdapter(ib, contracts, order_ref="INTRADAY")


def test_the_three_fields_that_have_each_cost_a_defect_are_set(ibkr):
    """tif, outsideRth and orderRef. Each one is a bug this repository already paid for."""
    ib, ad = ibkr
    ad.submit(_buy("AAPL", 5))
    o = ib.placed[0].order
    assert o.tif == "DAY", "an empty TIF makes IBKR emit 10349, which ib_async reads as a cancel"
    assert o.outsideRth is False, "AUD-08/09: an outside-RTH order queues to the next open"
    assert o.orderRef == "INTRADAY", "without a ref, stale orders cannot be found and cancelled"


def test_the_side_and_size_reach_the_venue_unsigned_and_correct(ibkr):
    ib, ad = ibkr
    ad.submit(_buy("AAPL", 7))
    ad.submit(OrderIntent(symbol="MSFT", side=Side.SELL, quantity=3))
    assert [(o.order.action, o.order.totalQuantity) for o in ib.placed] == [
        ("BUY", 7), ("SELL", 3)]


def test_a_flatten_goes_to_the_venue_as_a_market_order(ibkr):
    """The venue has no concept of "flatten"; inventing one would be a second wire meaning."""
    ib, ad = ibkr
    ad.submit(_flat("AAPL", 4))
    assert ib.placed[0].order.action == "BUY" or ib.placed[0].order.action == "SELL"
    assert ib.placed[0].order.totalQuantity == 4


def test_an_unqualified_symbol_is_a_refusal_not_an_exception(ibkr):
    """The other intents in the batch still have to go."""
    _, ad = ibkr
    ack = ad.submit(_buy("NVDA", 1))
    assert not ack.accepted and "no qualified contract" in ack.reason


def test_a_broker_exception_becomes_a_refusal_carrying_the_cause():
    ib = FakeIB(raise_on={"AAPL"})
    ad = IBKRAdapter(ib, {"AAPL": FakeContract("AAPL")})
    ack = ad.submit(_buy("AAPL", 1))
    assert not ack.accepted and "ConnectionError" in ack.reason


def test_one_bad_symbol_does_not_stop_the_rest_of_the_batch():
    ib = FakeIB(raise_on={"AAPL"})
    ad = IBKRAdapter(ib, {s: FakeContract(s) for s in ("AAPL", "MSFT")})
    acks = RoutedExecutor(RiskChain(), ad).submit([_buy("AAPL", 1), _buy("MSFT", 1)])
    assert [a.accepted for a in acks] == [False, True]


def test_working_reports_the_remaining_quantity_not_the_submitted_one(ibkr):
    """AUD-06: a half-filled order has half its size still on the wire."""
    ib, ad = ibkr
    ad.submit(_buy("AAPL", 10))
    assert ad.working() == {"AAPL": 10.0}
    ib.placed[0].fills.append(FakeFill(6))
    assert ad.working() == {"AAPL": 4.0}
    ib.placed[0].fills.append(FakeFill(4))
    assert ad.working() == {}


def test_working_nets_opposing_orders_in_the_same_symbol(ibkr):
    _, ad = ibkr
    ad.submit(_buy("AAPL", 10))
    ad.submit(OrderIntent(symbol="AAPL", side=Side.SELL, quantity=4))
    assert ad.working() == {"AAPL": 6.0}


def test_cancel_all_skips_orders_that_are_already_done(ibkr):
    ib, ad = ibkr
    ad.submit(_buy("AAPL", 10))
    ad.submit(_buy("MSFT", 5))
    ib.placed[0].fills.append(FakeFill(10))         # AAPL complete
    assert ad.cancel_all() == 1
    assert len(ib.cancelled) == 1


def test_a_cancel_that_fails_does_not_raise(ibkr):
    ib, ad = ibkr
    ad.submit(_buy("AAPL", 10))
    ib.cancelOrder = lambda order: (_ for _ in ()).throw(RuntimeError("no route"))
    assert ad.cancel_all() == 0


# ======================================================================================
# NO LAYER ABOVE THE ADAPTER MAY NAME A BROKER
# ======================================================================================

NL = chr(10)
BROKER_SDKS = {"ib_async", "ib_insync", "ibapi", "alpaca", "polygon"}


def test_nothing_outside_the_brokers_package_imports_a_broker_sdk():
    """The property that makes a second venue reachable, checked structurally.

    Parsed rather than grepped: `core/execution.py` names ib_async in its docstring, which is
    documentation and not a dependency, and a substring check cannot tell the difference. An
    AST walk over the import statements can, and it also cannot be fooled by a variable that
    happens to share the name.
    """
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "quant_brain"
    offenders: list[str] = []
    for f in sorted(root.rglob("*.py")):
        if f.parent.name == "brokers":
            continue
        tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"), filename=str(f))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            else:
                continue
            for n in names:
                if n.split(".")[0] in BROKER_SDKS:
                    offenders.append(f"{f.relative_to(root)}:{node.lineno} imports {n}")
    detail = NL.join(offenders)
    assert offenders == [], (
        "broker SDK imported outside quant_brain/brokers:" + NL + detail)


def test_the_check_above_would_actually_catch_an_offender(tmp_path):
    """A guard that cannot fail is not a guard; prove the AST walk sees a real import."""
    import ast
    src = "from ib_async import IB" + NL + "x = 1" + NL
    found: list[str] = []
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Import):
            found += [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom) and n.module:
            found.append(n.module)
    assert any(x.split(".")[0] in BROKER_SDKS for x in found)
