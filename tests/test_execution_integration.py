"""End-to-end integration of the risk and execution chain against a fake broker.

WHAT THIS DRIVES
----------------
Production code, all of it, with only the venue faked:

    core/execution.py    OrderIntent, RoutedExecutor, Position, Fill, ExecutionAdapter
    core/risk.py         RiskChain, RiskDecision
    core/governor.py     Governor, Limits, AccountView, KillSwitch, Reason
    core/idempotency.py  intent_id, IntentJournal, IntentState
    core/reconcile.py    reconcile, Reconciler, Snapshot, Discrepancy
    core/protection.py   verify, ProtectionMonitor, ProtectionState
    core/config.py       transmission_allowed

The venue is `tests/fakes/broker.FakeBroker`, which rejects, half-fills, echoes a fill,
loses a fill and holds positions the local book never opened. Nothing here opens a socket
and nothing writes under `live/` - the journal goes to `tmp_path`, and `conftest.isolate_live`
fails the test if a byte of real live state moves.

WHAT IT FOUND
-------------
Every finding is a test. The ones pinned with `xfail(strict=True)` are defects in production
code that this suite is not allowed to fix (other tracks own those files); the marker carries
the evidence, and the day the defect is fixed the strict marker turns the XPASS into a
failure so the pin has to be deleted. In summary:

  1. Deduplication works, and no production caller turns it on. `RoutedExecutor` dedupes only
     when a `journal=` is supplied; all three production construction sites omit it and
     neither runner sets `intent_id`, so the duplicate-order defect is live in the runners.
  2. Nothing carries a fill into a position book. `RoutedExecutor` has no book, no fill
     callback and no way to learn that an order filled; `Position.apply` is correct and has
     one caller in the whole tree (`venues/registry.py`).
  7. The adapter boundary cannot report positions, so no production code can rebuild state
     from the broker after a restart. `ExecutionAdapter` declares `submit`, `working` and
     `cancel_all` and nothing else.
  6. The journal cannot represent a fill. ACKED is terminal, so a dropped fill after an ack
     is invisible to `recover()`; reconciliation is the only mechanism that catches one.
  8. A protective stop cannot be expressed at all: `OrderType` has no STOP or STOP_LIMIT, so
     `core.protection` - which verifies stops the venue reports - can never see one that this
     system placed.
  9. The governor's contract caps are direction-blind and therefore block the EXIT: at the
     cap a closing order is denied, and below it a closing order is silently reduced.

Everything else holds. Reconciliation and bracket verification both work correctly and are
usable exactly as written - their problem is that nothing calls them, which
`tests/test_production_reachability.py` already pins.

Run: `python -m pytest tests/test_execution_integration.py -q -p no:cacheprovider`
"""
from __future__ import annotations

import ast
import dataclasses
import datetime as dt
import pathlib

import pytest

from quant_brain.core import config as qb_config
from quant_brain.core.execution import (
    Ack,
    ExecutionAdapter,
    Fill,
    OrderIntent,
    OrderType,
    Position,
    RoutedExecutor,
    Side,
)
from quant_brain.core.governor import AccountView, Governor, Limits, Reason
from quant_brain.core.idempotency import IntentJournal, IntentState, intent_id
from quant_brain.core.instruments import AssetClass, InstrumentSpec
from quant_brain.core.mode import Authority
from quant_brain.core.protection import ProtectionMonitor, ProtectionState, verify
from quant_brain.core.reconcile import (
    DiscrepancyKind,
    OrderRef,
    Reconciler,
    Snapshot,
    reconcile,
)
from quant_brain.core.risk import RiskChain
from tests.fakes.broker import EPOCH, DisconnectedBroker, FakeBroker, local_snapshot

REPO = pathlib.Path(__file__).resolve().parents[1]

MES = InstrumentSpec(symbol="MES", asset_class=AssetClass.FUTURE, multiplier=5.0, tick=0.25)
MNQ = InstrumentSpec(symbol="MNQ", asset_class=AssetClass.FUTURE, multiplier=2.0, tick=0.25)
SPECS = {"MES": MES, "MNQ": MNQ}


# =====================================================================================
# The client side of the boundary.
# =====================================================================================

class LocalBook:
    """The process's own position book, built ONLY out of `core.execution` primitives.

    It has to live in the test because production has no such thing: `RoutedExecutor` owns
    no positions, `ExecutionAdapter` reports no positions, and `Position.apply` - which is
    the correct, tested booking primitive - is called from exactly one place in the whole
    tree (`quant_brain/venues/registry.py`, the in-memory research ledger). See
    `test_the_executor_learns_that_an_order_filled`, which pins that gap.

    Deliberately dumb: it applies fill MESSAGES and nothing else. That is what makes the
    dropped-fill test meaningful - a book that reconciled itself against the venue behind
    the scenes would hide the exact failure being measured.
    """

    def __init__(self, specs=SPECS):
        self.specs = dict(specs)
        self.positions: dict[str, Position] = {}
        self.applied: list[Fill] = []

    def apply(self, fill: Fill) -> float:
        pos = self.positions.setdefault(fill.symbol, Position(spec=self.specs[fill.symbol]))
        self.applied.append(fill)
        return pos.apply(fill)

    def adopt(self, symbol: str, quantity: float, avg_price: float) -> None:
        """Set a position outright, as a restart rebuilt from the broker would."""
        self.positions[symbol] = Position(spec=self.specs[symbol], quantity=quantity,
                                          avg_price=avg_price)

    def qty(self, symbol: str) -> float:
        p = self.positions.get(symbol)
        return p.quantity if p else 0.0

    def avg(self, symbol: str) -> float:
        p = self.positions.get(symbol)
        return p.avg_price if p else 0.0

    def signed(self) -> dict[str, float]:
        return {s: p.quantity for s, p in self.positions.items() if p.quantity}

    def snapshot(self, working: dict[str, OrderRef] | None = None, *,
                 as_of: dt.datetime | None = None) -> Snapshot:
        return local_snapshot(self.signed(), working, as_of=as_of)


def executor(broker: ExecutionAdapter, *, risk=None, journal: IntentJournal | None = None,
             book: LocalBook | None = None) -> RoutedExecutor:
    """A `RoutedExecutor` wired the way a runner wires one, plus an optional journal.

    `Authority.backtest()` is the lowest authority that may reach an in-memory adapter, so
    this cannot be pointed at anything real even by accident.
    """
    ex = RoutedExecutor(risk if risk is not None else RiskChain(), broker,
                        authority=Authority.backtest(), journal=journal)
    if book is not None and isinstance(broker, FakeBroker):
        broker.on_fill(book.apply)
    return ex


def wired(tmp_path, **kw) -> tuple[FakeBroker, RoutedExecutor, LocalBook, IntentJournal]:
    """The whole chain: fake venue, real executor, a local book fed by fill messages."""
    broker = FakeBroker(**kw)
    book = LocalBook()
    journal = IntentJournal(tmp_path / "intents.jsonl")
    return broker, executor(broker, journal=journal, book=book), book, journal


def an_id(sequence: int = 0, *, symbol: str = "MES", side: str = "buy") -> str:
    return intent_id(strategy="integration", account="fake-50k", symbol=symbol,
                     session="2026-09-14", signal_ts=EPOCH, side=side, sequence=sequence)


def buy(qty: float = 1.0, *, symbol: str = "MES", iid: str = "", **kw) -> OrderIntent:
    return OrderIntent(symbol=symbol, side=Side.BUY, quantity=qty, tag="integration",
                       intent_id=iid, **kw)


def sell(qty: float = 1.0, *, symbol: str = "MES", iid: str = "", **kw) -> OrderIntent:
    return OrderIntent(symbol=symbol, side=Side.SELL, quantity=qty, tag="integration",
                       intent_id=iid, **kw)


def a_governor(limits: Limits | None = None, view: AccountView | None = None) -> Governor:
    return Governor(limits or Limits(), view or AccountView())


# =====================================================================================
# The fake is a credible venue, not a stub that agrees. Prove that first.
# =====================================================================================

def test_the_fake_reports_remaining_quantity_not_submitted_quantity():
    """The `ExecutionAdapter.working()` contract, which AUD-06 is about.

    `SimulatedAdapter` in production reports its own outbox forever - it never fills, so
    submitted and remaining coincide there and the distinction is untested. A fake that
    inherited that behaviour could not detect a netting bug at all.
    """
    broker = FakeBroker()
    ex = executor(broker)
    ex.submit([buy(4)])
    assert broker.working() == {"MES": 4.0}
    broker.fill(price=5000.0, quantity=1)
    assert broker.working() == {"MES": 3.0}
    broker.fill(price=5000.0)
    assert broker.working() == {}


def test_the_fake_records_rejected_orders_as_received():
    """A rejection is still an order that reached the venue. Counting only fills would let a
    duplicate-order regression hide behind a venue refusal."""
    broker = FakeBroker(reject={"MES"})
    ex = executor(broker)
    (ack,) = ex.submit([buy(1)])
    assert ack.accepted is False
    assert len(broker.orders) == 1
    assert broker.working() == {} and broker.open_positions() == {}


def test_the_fake_can_lose_a_fill_and_can_echo_one():
    broker = FakeBroker()
    book = LocalBook()
    broker.on_fill(book.apply)
    ex = executor(broker)
    ex.submit([buy(1), buy(1, symbol="MNQ")])
    broker.fill("fake-1", price=5000.0, drop=True)
    broker.fill("fake-2", price=20000.0, echo=True)
    assert len(broker.fills) == 2, "the venue booked both"
    assert [f.symbol for f in broker.dropped] == ["MES"]
    assert [f.symbol for f in broker.delivered] == ["MNQ", "MNQ"], "echoed once"
    assert broker.open_positions() == {"MES": 1.0, "MNQ": 1.0}


# =====================================================================================
# INVARIANT 1 - one intent produces exactly one order
# =====================================================================================

def test_one_intent_id_driven_twice_produces_exactly_one_order(tmp_path):
    """THE duplicate-order defect, asserted at the venue.

    The same decision, submitted twice - a retry, a restart, a scheduler that fired twice -
    must put one order on the wire. `RoutedExecutor` consults the journal BEFORE the risk
    chain, so the second attempt is refused whatever the chain would have said.
    """
    broker, ex, book, journal = wired(tmp_path)
    intent = buy(2, iid=an_id())

    first = ex.submit([intent])
    second = ex.submit([intent])

    assert len(first) == 1 and first[0].accepted
    assert second == [], "the replay must not reach the venue"
    assert len(broker.orders) == 1, (
        f"the venue received {len(broker.orders)} orders for one intent: "
        f"{[o.broker_id for o in broker.orders]}")
    assert broker.working() == {"MES": 2.0}, "one order's worth on the wire, not two"

    (_, denial) = ex.refused[-1]
    assert denial.binding == ("IDEMPOTENCY_DUPLICATE",)
    assert journal.seen(an_id()).state is IntentState.ACKED

    broker.fill(price=5000.0)
    assert book.qty("MES") == 2.0, "and the one order fills for the intended size, not double"


def test_a_replay_after_a_restart_still_produces_no_second_order(tmp_path):
    """A fresh process with a fresh executor reads the same journal off disk."""
    broker = FakeBroker()
    journal = IntentJournal(tmp_path / "intents.jsonl")
    intent = buy(1, iid=an_id())
    executor(broker, journal=journal).submit([intent])

    restarted = executor(broker, journal=IntentJournal(tmp_path / "intents.jsonl"))
    assert restarted.submit([intent]) == []
    assert len(broker.orders) == 1


def test_an_intent_with_no_id_is_refused_before_the_venue_sees_it(tmp_path):
    """Deduplication that only covers labelled orders is not deduplication."""
    broker, ex, _book, journal = wired(tmp_path)
    assert ex.submit([buy(1)]) == []
    assert broker.orders == []
    assert ex.refused[-1][1].binding == ("IDEMPOTENCY_NO_ID",)
    assert journal.entries() == {}


def test_without_a_journal_the_same_intent_reaches_the_venue_twice():
    """The configuration the runners actually use. This is the live defect, demonstrated.

    `RoutedExecutor(risk, adapter, authority=...)` with no `journal=` sets `self.journal =
    None`, and `_claim` then returns None for every intent. Nothing else in the chain has any
    notion of intent identity, so the same decision goes out as many times as it is offered.
    """
    broker = FakeBroker()
    ex = executor(broker)                      # exactly how intraday_trader.py builds one
    intent = buy(3)
    ex.submit([intent])
    ex.submit([intent])
    assert len(broker.orders) == 2
    assert broker.working() == {"MES": 6.0}, "6 contracts on the wire for a 3-contract decision"


def _routed_executor_call_sites() -> list[tuple[str, int, set[str]]]:
    """Every `RoutedExecutor(...)` construction in production code, with its keywords."""
    out: list[tuple[str, int, set[str]]] = []
    for rel in ("scripts/intraday_trader.py", "scripts/paper_trade.py"):
        tree = ast.parse((REPO / rel).read_text(encoding="utf-8"), rel)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "RoutedExecutor"):
                out.append((rel, node.lineno, {k.arg for k in node.keywords if k.arg}))
    return out


@pytest.mark.xfail(strict=True, reason=(
    "FINDING 1: no production RoutedExecutor is given a journal, so nothing in the live "
    "path deduplicates. intraday_trader.py:352, paper_trade.py:717 and paper_trade.py:867 "
    "all construct RoutedExecutor(risk, adapter, authority=..., on_event=...) with journal "
    "omitted; RoutedExecutor.__init__ then sets self.journal=None and _claim() returns None "
    "for every intent. Neither runner sets intent_id either (paper_trade.intent_for() and "
    "intraday_trader.py:394 build OrderIntent without one), so even attaching a journal "
    "would refuse every order with IDEMPOTENCY_NO_ID until the intents are given ids. Fix: "
    "mint core.idempotency.intent_id at the decision site and pass journal=IntentJournal(...) "
    "at all three construction sites."))
def test_every_production_routed_executor_is_given_an_intent_journal():
    sites = _routed_executor_call_sites()
    assert sites, "no RoutedExecutor construction found in the runners; update this test"
    missing = [(f, ln) for f, ln, kw in sites if "journal" not in kw]
    assert not missing, f"RoutedExecutor built without a journal at {missing}"


# =====================================================================================
# INVARIANT 2 - a fill updates the position book deterministically
# =====================================================================================

@pytest.mark.parametrize("side,qty,expected", [(Side.BUY, 2.0, 2.0), (Side.SELL, 2.0, -2.0)])
def test_a_fill_moves_the_book_to_exactly_the_filled_quantity_signed(side, qty, expected):
    """The "position stayed at zero while orders went out" defect, asserted directly.

    After one full fill the local position is the filled quantity, signed by the side of the
    order, and the average price is the fill price. Not approximately, and not zero.
    """
    broker = FakeBroker()
    book = LocalBook()
    broker.on_fill(book.apply)
    ex = executor(broker)
    intent = OrderIntent(symbol="MES", side=side, quantity=qty, tag="integration")
    ex.submit([intent])

    assert book.qty("MES") == 0.0, "an ack is not a fill; the book must not move on acceptance"

    broker.fill(price=5000.0)

    assert book.qty("MES") == expected
    assert book.avg("MES") == 5000.0
    assert book.signed() == {"MES": expected}
    assert broker.open_positions() == {"MES": expected}, "and it agrees with the venue"
    assert broker.working() == {}


def test_a_flip_through_zero_reopens_at_the_new_price_and_realizes_the_old_leg():
    """Booking is deterministic through a sign change, which is where average cost goes wrong."""
    broker = FakeBroker()
    book = LocalBook()
    broker.on_fill(book.apply)
    ex = executor(broker)

    ex.submit([buy(2)])
    broker.fill(price=5000.0)
    ex.submit([sell(5)])
    broker.fill(price=5010.0)

    assert book.qty("MES") == -3.0
    assert book.avg("MES") == 5010.0, "the residual short opens at the fill price"
    realized = book.positions["MES"].realized
    assert realized == pytest.approx((5010.0 - 5000.0) * 2 * MES.multiplier), "2 x 10pt x $5"
    assert broker.open_positions() == {"MES": -3.0}


def test_an_echoed_fill_message_double_counts_a_book_built_from_messages():
    """A venue that reports the same fill twice must not be able to double the book.

    Booking every message that arrives is the naive client, and this is what it costs: the
    book says 2 while the venue says 1. Nothing in `core/` currently deduplicates a fill -
    `Fill` carries no id and `IntentState` has no FILLED state - so a real client has to key
    off broker state, not off messages. Recorded here as the hazard it is.
    """
    broker = FakeBroker()
    book = LocalBook()
    broker.on_fill(book.apply)
    executor(broker).submit([buy(1)])

    broker.fill(price=5000.0, echo=True)

    assert broker.open_positions() == {"MES": 1.0}, "the venue booked it once"
    assert book.qty("MES") == 2.0, "the message-driven book booked it twice"
    assert book.qty("MES") != broker.open_positions()["MES"]
    assert not {f.name for f in dataclasses.fields(Fill)} & {"fill_id", "exec_id", "broker_id"}, (
        "core.execution.Fill carries no venue identity, so no consumer can tell a repeated "
        "fill message from a second fill; a client must key off broker state, not messages")


@pytest.mark.xfail(strict=True, reason=(
    "FINDING 2: nothing connects a fill to a position book. RoutedExecutor exposes "
    "`decisions`, `refused`, `journal`, `risk` and `adapter` and has no positions, no fills "
    "and no fill callback; ExecutionAdapter declares only submit/working/cancel_all, so an "
    "adapter has no way to report a fill upwards either. core.execution.Position.apply is "
    "the correct booking primitive and has exactly one caller in the tree "
    "(quant_brain/venues/registry.py:139, the in-memory research ledger) - no production "
    "runner books through it. This is the structural form of the 'position book stayed at "
    "zero while orders went out' defect. Fix: give the executor (or a component it owns) a "
    "fill stream and a Position book, and have the adapters emit Fills."))
def test_the_executor_learns_that_an_order_filled():
    broker = FakeBroker()
    ex = executor(broker)
    ex.submit([buy(2)])
    broker.fill(price=5000.0)
    surface = {n for n in dir(ex) if not n.startswith("_")}
    assert surface & {"positions", "book", "fills", "on_fill"}, (
        f"RoutedExecutor has no fill or position surface; it exposes {sorted(surface)}")


# =====================================================================================
# INVARIANT 3 - partial fills accumulate, and the remainder is right
# =====================================================================================

def test_partial_fills_accumulate_and_the_remaining_working_quantity_is_right():
    broker = FakeBroker()
    book = LocalBook()
    broker.on_fill(book.apply)
    executor(broker).submit([buy(5)])

    broker.fill(price=5000.0, quantity=2)
    assert book.qty("MES") == 2.0
    assert broker.working() == {"MES": 3.0}, "three still on the wire"

    broker.fill(price=5006.0, quantity=1)
    assert book.qty("MES") == 3.0
    assert book.avg("MES") == pytest.approx((2 * 5000.0 + 1 * 5006.0) / 3)
    assert broker.working() == {"MES": 2.0}

    broker.fill(price=5012.0)
    assert book.qty("MES") == 5.0
    assert broker.working() == {}
    assert broker.open_positions() == {"MES": 5.0}
    assert book.signed() == broker.open_positions()


def test_a_partially_filled_order_leaves_its_remainder_working_across_symbols():
    """Netting has to be per symbol: a remainder on MES must not offset one on MNQ."""
    broker = FakeBroker()
    executor(broker).submit([buy(4), sell(3, symbol="MNQ")])
    broker.fill("fake-1", price=5000.0, quantity=1)
    broker.fill("fake-2", price=20000.0, quantity=1)
    assert broker.working() == {"MES": 3.0, "MNQ": -2.0}


def test_a_sizer_that_nets_working_quantity_does_not_double_up_on_a_slow_fill():
    """AUD-06 in one assertion: the second decision must see the first order's remainder.

    The 15:38 order half-fills; at 15:39 the strategy still wants 5 total. Netting what is
    working (3) against the target (5) leaves 2 to send. Reading only the booked position (2)
    would send 3 more and end up long 8.
    """
    broker = FakeBroker()
    book = LocalBook()
    broker.on_fill(book.apply)
    ex = executor(broker)

    ex.submit([buy(5)])
    broker.fill(price=5000.0, quantity=2)

    target = 5.0
    held = book.qty("MES")
    on_the_wire = broker.working().get("MES", 0.0)
    still_needed = target - held - on_the_wire
    assert (held, on_the_wire, still_needed) == (2.0, 3.0, 0.0)

    naive = target - held
    assert naive == 3.0, "the AUD-06 arithmetic, which would take the position to 8"


# =====================================================================================
# INVARIANT 4 - flatten closes exactly the open quantity, and sends nothing when flat
# =====================================================================================

def test_flatten_closes_exactly_the_open_quantity():
    broker = FakeBroker()
    book = LocalBook()
    broker.on_fill(book.apply)
    ex = executor(broker)
    ex.submit([buy(3)])
    broker.fill(price=5000.0)
    sent_before = len(broker.orders)

    acks = ex.flatten(book.signed(), tag="eod")

    assert len(acks) == 1 and acks[0].accepted
    closing = broker.orders[sent_before]
    assert closing.intent.side is Side.SELL
    assert closing.intent.quantity == 3.0
    assert closing.intent.order_type is OrderType.FLATTEN
    broker.fill(price=5010.0)
    assert book.qty("MES") == 0.0
    assert broker.open_positions() == {}


def test_flatten_of_a_short_buys_back_exactly_the_open_quantity():
    broker = FakeBroker()
    book = LocalBook()
    broker.on_fill(book.apply)
    ex = executor(broker)
    ex.submit([sell(2)])
    broker.fill(price=5000.0)
    assert book.qty("MES") == -2.0

    ex.flatten(book.signed())
    closing = broker.orders[-1]
    assert (closing.intent.side, closing.intent.quantity) == (Side.BUY, 2.0)
    broker.fill(price=4990.0)
    assert book.qty("MES") == 0.0


@pytest.mark.parametrize("positions", [{}, {"MES": 0.0}, {"MES": 0.0, "MNQ": 0.0}])
def test_a_flatten_with_no_position_sends_nothing(positions):
    broker = FakeBroker()
    ex = executor(broker)
    assert ex.flatten(positions) == []
    assert broker.orders == []


def test_flatten_reads_the_local_book_so_a_broker_only_position_is_left_open():
    """AUD-08, demonstrated: `flatten()` takes positions as an ARGUMENT.

    It closes what the caller believes, not what the venue holds. When the two disagree - a
    dropped fill, a position opened by another process, a manual trade in the platform - the
    emergency exit sends nothing and the exposure survives the flatten. The correct input to
    `flatten()` is a broker-sourced position map, and no production caller has one because
    `ExecutionAdapter` cannot report positions (see FINDING 7).
    """
    broker = FakeBroker()
    book = LocalBook()
    broker.on_fill(book.apply)
    ex = executor(broker)
    broker.set_position("MES", 2.0, avg_price=5000.0)      # nobody told the local book

    assert ex.flatten(book.signed()) == []
    assert broker.orders == []
    assert broker.open_positions() == {"MES": 2.0}, "still exposed after a flatten"


def test_a_flatten_is_never_reduced_or_refused_by_the_risk_chain():
    """A risk layer that can block the exit is not a risk layer (AUD-06 / AUD-08)."""
    view = AccountView(daily_pnl=-9_000.0, positions={"MES": 3.0}, trades_today=99)
    gov = a_governor(Limits(max_daily_loss=500.0, max_position=1.0, max_trades_per_day=1), view)
    gov.trip(Reason.MANUAL_HALT, "operator stopped trading")
    broker = FakeBroker()
    ex = executor(broker, risk=gov)

    assert ex.submit([buy(1)]) == [], "a new order is refused"
    acks = ex.flatten({"MES": 3.0})

    assert len(acks) == 1 and acks[0].accepted
    assert broker.orders[-1].intent.quantity == 3.0, "flatten is not reduced by max_position=1"


# =====================================================================================
# INVARIANT 5 - reconciliation halts on disagreement
# =====================================================================================

def test_a_broker_position_the_local_book_does_not_have_halts_trading():
    """Broker state is the truth about what EXISTS; the correct response is to stop."""
    broker = FakeBroker()
    book = LocalBook()
    broker.on_fill(book.apply)
    gov = a_governor()
    ex = executor(broker, risk=gov, book=book)
    broker.set_position("MES", 2.0, avg_price=5000.0)

    result = Reconciler(governor=gov).run(book.snapshot(), broker.snapshot(), now=EPOCH)

    assert result.ok is False
    (d,) = result.discrepancies
    assert d.kind is DiscrepancyKind.UNEXPLAINED_POSITION
    assert (d.key, d.local, d.broker) == ("MES", 0.0, 2.0), "the broker's number is reported"
    assert result.unexplained_positions is True
    assert result.readiness_fields() == {
        "local_state_reconciled": False, "broker_state_reconciled": False,
        "no_unexplained_orders": True, "no_unexplained_positions": False}

    assert gov.halted is True
    assert [s.reason for s in gov.tripped()] == [Reason.POSITION_UNRECONCILED]
    assert ex.submit([buy(1)]) == [], "nothing new opens while unreconciled"
    assert broker.orders == []
    assert ex.refused[-1][1].binding == (Reason.POSITION_UNRECONCILED.value,)


def test_reconciliation_adopts_neither_side_and_auto_corrects_nothing():
    """"Adopt the broker" is wrong when a bug opened the position; "adopt local" is worse."""
    broker = FakeBroker()
    book = LocalBook()
    book.adopt("MES", 1.0, 5000.0)
    broker.set_position("MES", 4.0, avg_price=5000.0)

    result = reconcile(book.snapshot(), broker.snapshot(), now=EPOCH)

    assert result.ok is False
    (d,) = result.discrepancies
    assert d.kind is DiscrepancyKind.QUANTITY_MISMATCH
    assert (d.local, d.broker) == (1.0, 4.0)
    assert book.qty("MES") == 1.0, "local untouched"
    assert broker.open_positions() == {"MES": 4.0}, "broker untouched"
    assert "quantity_mismatch MES" in result.describe()


def test_a_position_the_local_book_holds_and_the_broker_does_not_is_a_phantom():
    broker = FakeBroker()
    book = LocalBook()
    book.adopt("MES", 2.0, 5000.0)
    result = reconcile(book.snapshot(), broker.snapshot(), now=EPOCH)
    (d,) = result.discrepancies
    assert d.kind is DiscrepancyKind.PHANTOM_POSITION
    assert (d.local, d.broker) == (2.0, 0.0)


def test_a_working_order_the_process_never_sent_is_unexplained_and_halts():
    broker = FakeBroker()
    gov = a_governor()
    ex = executor(broker, risk=gov)
    broker.place_out_of_band(symbol="MES", side=Side.SELL, quantity=1.0, kind="limit",
                             limit_price=5100.0)

    result = Reconciler(governor=gov).run(local_snapshot(), broker.snapshot(), now=EPOCH)

    assert result.ok is False and result.unexplained_orders is True
    (d,) = result.discrepancies
    assert d.kind is DiscrepancyKind.UNEXPLAINED_ORDER
    assert gov.halted and ex.submit([buy(1)]) == []


def test_a_stop_the_process_believes_in_that_the_broker_lacks_trips_bracket_unverified():
    """A missing stop is not an accounting question; it is open exposure."""
    broker = FakeBroker()
    gov = a_governor()
    local = local_snapshot({"MES": 2.0},
                           {"stop-1": OrderRef("MES", "sell", 2.0, "stop")})
    broker.set_position("MES", 2.0, avg_price=5000.0)

    result = Reconciler(governor=gov).run(local, broker.snapshot(), now=EPOCH)

    assert result.ok is False
    assert [d.kind for d in result.discrepancies] == [DiscrepancyKind.MISSING_ORDER]
    assert len(result.missing_stops) == 1
    assert {s.reason for s in gov.tripped()} == {Reason.POSITION_UNRECONCILED,
                                                 Reason.BRACKET_UNVERIFIED}


def test_a_clean_reconciliation_does_not_reset_a_switch_that_already_tripped():
    """A transient agreement must not clear a halt before a person has looked."""
    broker = FakeBroker()
    gov = a_governor()
    rec = Reconciler(governor=gov)
    broker.set_position("MES", 1.0, avg_price=5000.0)
    rec.run(local_snapshot(), broker.snapshot(), now=EPOCH)
    assert gov.halted

    ok = rec.run(local_snapshot({"MES": 1.0}), broker.snapshot(), now=EPOCH)

    assert ok.ok is True
    assert gov.halted is True, "only a named person resets a switch"
    assert len(rec.history) == 2 and rec.last is ok


def test_a_flatten_still_reaches_the_venue_after_a_reconciliation_halt():
    broker = FakeBroker()
    gov = a_governor()
    ex = executor(broker, risk=gov)
    broker.set_position("MES", 2.0, avg_price=5000.0)
    Reconciler(governor=gov).run(local_snapshot(), broker.snapshot(), now=EPOCH)

    acks = ex.flatten(broker.open_positions())

    assert gov.halted and len(acks) == 1 and acks[0].accepted
    assert broker.orders[-1].intent.order_type is OrderType.FLATTEN


def test_stale_state_is_refused_before_any_comparison_is_made():
    """A match between two stale snapshots would not mean anything."""
    broker = FakeBroker()
    broker.set_position("MES", 1.0, avg_price=5000.0)
    result = reconcile(local_snapshot({"MES": 1.0}), broker.snapshot(),
                       now=EPOCH + dt.timedelta(minutes=5))
    assert result.ok is False
    assert {d.kind for d in result.discrepancies} == {DiscrepancyKind.STALE}


# =====================================================================================
# INVARIANT 6 - a dropped fill is detected, not assumed away
# =====================================================================================

def test_a_dropped_fill_leaves_the_book_wrong_and_reconciliation_catches_it():
    """The message never arrives. The book is not merely stale - it is wrong, and silent."""
    broker = FakeBroker()
    book = LocalBook()
    broker.on_fill(book.apply)
    gov = a_governor()
    ex = executor(broker, risk=gov)

    ex.submit([buy(2)])
    broker.fill(price=5000.0, drop=True)

    assert broker.delivered == [] and len(broker.dropped) == 1
    assert book.qty("MES") == 0.0, "the book does not invent the fill"
    assert broker.open_positions() == {"MES": 2.0}
    assert broker.working() == {}, "and the order is no longer working, so nothing looks pending"

    result = Reconciler(governor=gov).run(book.snapshot(), broker.snapshot(), now=EPOCH)

    assert result.ok is False
    assert [d.kind for d in result.discrepancies] == [DiscrepancyKind.UNEXPLAINED_POSITION]
    assert gov.halted, "detected, and the response is to stop"


def test_a_dropped_partial_fill_is_a_quantity_mismatch():
    broker = FakeBroker()
    book = LocalBook()
    broker.on_fill(book.apply)
    executor(broker).submit([buy(4)])
    broker.fill(price=5000.0, quantity=1)
    broker.fill(price=5000.0, quantity=2, drop=True)

    assert book.qty("MES") == 1.0 and broker.open_positions() == {"MES": 3.0}
    result = reconcile(book.snapshot(broker.order_refs()), broker.snapshot(), now=EPOCH)
    kinds = [d.kind for d in result.discrepancies]
    assert DiscrepancyKind.QUANTITY_MISMATCH in kinds


def test_an_order_lost_after_transmission_stays_submitted_for_recovery(tmp_path):
    """A connection that dies after the send is an UNKNOWN outcome, not a failure.

    The journal must leave the intent SUBMITTED so `recover()` finds it, and must still
    refuse the replay: "outcome unknown" is not permission to resend.
    """
    broker = DisconnectedBroker()
    journal = IntentJournal(tmp_path / "intents.jsonl")
    ex = executor(broker, journal=journal)
    intent = buy(1, iid=an_id())

    with pytest.raises(ConnectionError):
        ex.submit([intent])

    assert len(broker.orders) == 1, "the venue did receive it"
    assert journal.seen(an_id()).state is IntentState.SUBMITTED
    assert [e.intent_id for e in journal.recover()] == [an_id()]
    assert executor(broker, journal=IntentJournal(tmp_path / "intents.jsonl")
                    ).submit([intent]) == []
    assert len(broker.orders) == 1


@pytest.mark.xfail(strict=True, reason=(
    "FINDING 6: the journal cannot represent a fill. IntentState is PENDING -> SUBMITTED -> "
    "ACKED | FAILED, and core/idempotency.py treats ACKED as TERMINAL (advance() raises "
    "Duplicate on any move out of it). An ack is acceptance, not execution - execution.Ack's "
    "own docstring says so - so after a venue ack the journal reports a finished intent "
    "whether the order filled, half-filled, or filled and had its fill message dropped. "
    "recover() therefore returns nothing for a dropped fill, and reconciliation is the only "
    "mechanism that can catch one. Fix: add FILLED/PARTIALLY_FILLED states (or a separate "
    "fill ledger keyed by broker_id) so an acked-but-unfilled intent is recoverable."))
def test_the_journal_can_tell_an_acked_order_from_a_filled_one(tmp_path):
    broker, ex, book, journal = wired(tmp_path)
    ex.submit([buy(2, iid=an_id())])
    broker.fill(price=5000.0, drop=True)
    states = {s.value for s in IntentState}
    assert states & {"filled", "partially_filled"}, (
        f"IntentState cannot express a fill; it has {sorted(states)}")


# =====================================================================================
# INVARIANT 7 - restart recovery rebuilds from the broker, not from local memory
# =====================================================================================

def test_state_rebuilt_from_the_broker_matches_the_broker():
    """The safe restart: throw the local book away and take the venue's word for what exists."""
    broker = FakeBroker()
    book = LocalBook()
    broker.on_fill(book.apply)
    executor(broker).submit([buy(2)])
    broker.fill(price=5000.0, drop=True)
    broker.place_out_of_band(symbol="MES", side=Side.SELL, quantity=2.0, kind="stop",
                             stop_price=4980.0)

    rebuilt = LocalBook()
    for symbol, qty in broker.open_positions().items():
        rebuilt.adopt(symbol, qty, broker.avg_price[symbol])
    rebuilt_working = dict(broker.order_refs())

    assert rebuilt.signed() == broker.open_positions() == {"MES": 2.0}
    assert rebuilt.avg("MES") == 5000.0
    result = reconcile(rebuilt.snapshot(rebuilt_working), broker.snapshot(), now=EPOCH)
    assert result.ok is True, result.describe()


def test_state_rebuilt_from_local_memory_after_a_restart_disagrees_with_the_broker():
    """The dangerous restart, which is why the rebuild has to come from the venue."""
    broker = FakeBroker()
    book = LocalBook()
    broker.on_fill(book.apply)
    executor(broker).submit([buy(2)])
    broker.fill(price=5000.0, drop=True)

    from_memory = LocalBook()
    for symbol, qty in book.signed().items():                 # local memory: empty
        from_memory.adopt(symbol, qty, book.avg(symbol))

    assert from_memory.signed() == {}
    assert reconcile(from_memory.snapshot(), broker.snapshot(), now=EPOCH).ok is False


@pytest.mark.xfail(strict=True, reason=(
    "FINDING 7: the adapter boundary cannot report positions, so no production code can "
    "perform the rebuild the test above performs by reaching into the fake. "
    "core.execution.ExecutionAdapter declares submit(), working() and cancel_all() and "
    "nothing else - there is no positions(), no fills(), no account snapshot - so "
    "core.reconcile.reconcile() can never be handed a broker-side Snapshot by anything on "
    "the production path. The one adapter that could ask a real venue, "
    "brokers/projectx.ProjectXAdapter, raises NotPermitted from both working() and "
    "reconcile(). Fix: add an abstract positions() (and ideally a fills stream) to "
    "ExecutionAdapter and build the broker Snapshot from it."))
def test_the_adapter_boundary_can_report_positions_for_a_restart_rebuild():
    surface = {n for n in dir(ExecutionAdapter) if not n.startswith("_")}
    assert surface & {"positions", "open_positions", "snapshot", "account"}, (
        f"ExecutionAdapter exposes only {sorted(surface)}; a restart cannot rebuild from it")


# =====================================================================================
# INVARIANT 8 - an open position with no known stop is UNPROTECTED, and fails closed
# =====================================================================================

def test_an_open_position_with_no_stop_at_the_venue_is_unprotected():
    broker = FakeBroker()
    book = LocalBook()
    broker.on_fill(book.apply)
    executor(broker).submit([buy(2)])
    broker.fill(price=5000.0)

    verdict = verify(symbol="MES", position=book.qty("MES"), avg_price=book.avg("MES"),
                     working=broker.protection_orders("MES"))

    assert verdict.state is ProtectionState.UNPROTECTED
    assert verdict.safe is False
    assert verdict.naked_qty == 2.0
    assert "no stop-type order is working for this symbol" in verdict.reasons


def test_protection_is_verified_from_the_venue_not_inferred_from_intent():
    """The process sent something; the venue has nothing. Only the venue's list counts.

    `RoutedExecutor` acked a working order and the executor's own record shows it as sent -
    and the position is still naked, because the venue reports no stop. That gap is the
    entire content of `core/protection.py`.
    """
    broker = FakeBroker()
    book = LocalBook()
    broker.on_fill(book.apply)
    ex = executor(broker)
    ex.submit([buy(2)])
    broker.fill(price=5000.0)

    # As close to "a stop" as OrderIntent can express (see FINDING 8): a resting closing
    # limit. It is acked, it is working, and it protects nothing.
    ex.submit([sell(2, order_type=OrderType.LIMIT, limit_price=4980.0)])
    assert len(ex.decisions) == 2 and ex.decisions[-1][2].accepted

    verdict = verify(symbol="MES", position=2.0, avg_price=5000.0,
                     working=broker.protection_orders("MES"))
    assert verdict.state is ProtectionState.UNPROTECTED
    assert verdict.covering == ()


def test_a_submitted_but_unacknowledged_stop_is_pending_not_protected():
    broker = FakeBroker()
    broker.place_out_of_band(symbol="MES", side=Side.SELL, quantity=2.0, kind="stop",
                             stop_price=4980.0, acknowledged=False)
    verdict = verify(symbol="MES", position=2.0, avg_price=5000.0,
                     working=broker.protection_orders("MES"))
    assert verdict.state is ProtectionState.PENDING
    assert any("not acknowledged" in r for r in verdict.reasons)


def test_an_acknowledged_correctly_sided_stop_protects_the_position():
    """The positive case, so UNPROTECTED is not simply what this module always answers."""
    broker = FakeBroker()
    broker.set_position("MES", 2.0, avg_price=5000.0)
    broker.place_out_of_band(symbol="MES", side=Side.SELL, quantity=2.0, kind="stop",
                             stop_price=4980.0)
    verdict = verify(symbol="MES", position=2.0, avg_price=5000.0,
                     working=broker.protection_orders("MES"))
    assert verdict.state is ProtectionState.PROTECTED
    assert verdict.safe and verdict.covered_qty == 2.0


def test_an_undersized_stop_leaves_the_uncovered_part_naked():
    broker = FakeBroker()
    broker.place_out_of_band(symbol="MES", side=Side.SELL, quantity=1.0, kind="stop",
                             stop_price=4980.0)
    verdict = verify(symbol="MES", position=3.0, avg_price=5000.0,
                     working=broker.protection_orders("MES"))
    assert verdict.state is ProtectionState.UNPROTECTED
    assert (verdict.covered_qty, verdict.naked_qty) == (1.0, 2.0)


def test_an_unprotected_position_fails_closed_flattens_and_stops_new_orders():
    """The fail-safe, end to end: trip the governor, flatten now, refuse everything after."""
    broker = FakeBroker()
    book = LocalBook()
    broker.on_fill(book.apply)
    gov = a_governor()
    ex = executor(broker, risk=gov)
    ex.submit([buy(2)])
    broker.fill(price=5000.0)

    def fail_safe(symbol: str, verdict) -> None:
        gov.trip(Reason.BRACKET_UNVERIFIED, f"{symbol}: {verdict.describe()}")
        ex.flatten({symbol: book.qty(symbol)}, tag="unprotected")

    monitor = ProtectionMonitor(on_unprotected=fail_safe)
    monitor.check("MES", verify(symbol="MES", position=book.qty("MES"),
                                avg_price=book.avg("MES"),
                                working=broker.protection_orders("MES")))

    assert monitor.fired == [("MES", ProtectionState.UNPROTECTED)]
    assert gov.halted and [s.reason for s in gov.tripped()] == [Reason.BRACKET_UNVERIFIED]
    assert broker.orders[-1].intent.order_type is OrderType.FLATTEN
    assert broker.orders[-1].intent.quantity == 2.0
    broker.fill(price=4995.0)
    assert book.qty("MES") == 0.0

    before = len(broker.orders)
    assert ex.submit([buy(1)]) == []
    assert len(broker.orders) == before
    assert ex.refused[-1][1].binding == (Reason.BRACKET_UNVERIFIED.value,)


@pytest.mark.xfail(strict=True, reason=(
    "FINDING 8: a protective stop cannot be expressed as an OrderIntent. "
    "core.execution.OrderType has MARKET, LIMIT, MARKET_ON_CLOSE, MARKET_ON_OPEN and FLATTEN "
    "- no STOP, no STOP_LIMIT - and OrderIntent has no stop_price field and no attached/OCO "
    "leg. core.protection.verify() counts an order only when w.kind in ('stop','stop_limit'), "
    "so a stop this system placed through RoutedExecutor can never appear in the venue's "
    "working list as a stop. That is the mechanical reason 'neither runner places a "
    "protective order' and why, by protection.py's own definition, every open position is "
    "UNPROTECTED for the whole session. Fix: add STOP and STOP_LIMIT to OrderType with a "
    "stop_price on OrderIntent, and teach the adapters to translate them."))
def test_a_protective_stop_can_be_expressed_as_an_order_intent():
    spellings = {t.value for t in OrderType}
    assert spellings & {"stop", "stop_limit"}, (
        f"OrderType cannot express a stop; it has {sorted(spellings)}")


# =====================================================================================
# INVARIANT 9 - the risk chain has final authority
# =====================================================================================

def test_an_intent_the_governor_refuses_never_reaches_the_venue():
    view = AccountView(daily_pnl=-600.0)
    gov = a_governor(Limits(max_daily_loss=500.0), view)
    broker = FakeBroker()
    ex = executor(broker, risk=gov)

    assert ex.submit([buy(1)]) == []
    assert broker.orders == [], "the adapter was never reached, so no adapter bug can revive it"
    (intent, decision) = ex.refused[-1]
    assert decision.allowed is False
    assert decision.binding == (Reason.RISK_DAILY_LOSS.value,)
    assert intent.quantity == 1.0, "the refused intent is recorded unmodified"


@pytest.mark.parametrize("reason", [Reason.MANUAL_HALT, Reason.DATA_STALE,
                                    Reason.CONNECTION_UNSAFE, Reason.CLOCK_UNSYNCED])
def test_every_kill_switch_stops_new_orders_at_the_boundary(reason):
    gov = a_governor()
    gov.trip(reason, "tripped by the test")
    broker = FakeBroker()
    ex = executor(broker, risk=gov)
    assert ex.submit([buy(1), sell(1, symbol="MNQ")]) == []
    assert broker.orders == []
    assert {d.binding[0] for _, d in ex.refused} == {reason.value}


def test_a_reduced_intent_reaches_the_venue_at_the_reduced_size_not_the_requested_one():
    gov = a_governor(Limits(max_position=2.0), AccountView(positions={}))
    broker = FakeBroker()
    ex = executor(broker, risk=gov)

    (ack,) = ex.submit([buy(5)])

    assert ack.accepted
    assert len(broker.orders) == 1
    assert broker.orders[0].intent.quantity == 2.0, "the venue must never see the 5"
    assert broker.working() == {"MES": 2.0}


@pytest.mark.xfail(strict=True, reason=(
    "FINDING 9: the governor's contract caps are direction-blind, so they block the EXIT. "
    "core/governor.py LimitEngine.evaluate computes `held = abs(v.positions.get(symbol))` and "
    "`room = max(0, L.max_position - held)` (and the same shape for max_contracts against "
    "v.total_contracts) without ever looking at intent.side. At the cap, room is 0 and a "
    "SELL that would close a long is denied with RISK_POSITION_SIZE; below the cap the "
    "closing order is silently REDUCED, so a sell of 2 against a long of 1 with cap 2 goes "
    "out as a sell of 1 and leaves a position the strategy believes it closed. Only "
    "OrderType.FLATTEN escapes, and neither runner spells an ordinary exit that way - "
    "paper_trade.intent_for() never emits FLATTEN and intraday_trader.py:394 emits it only "
    "on the flatten branch. This is AUD-06/AUD-08 reintroduced one layer up. Latent today "
    "only because intraday_trader.py:588 configures Limits(max_daily_loss=...) alone; it "
    "goes live the moment a Topstep contract cap is configured. Fix: compute the room "
    "against the RESULTING position (held + intent.signed_quantity), so an order that "
    "reduces |position| is never capped."))
def test_an_order_that_reduces_a_position_is_not_blocked_by_the_contract_cap():
    broker = FakeBroker()
    at_the_cap = executor(broker, risk=a_governor(Limits(max_position=2.0),
                                                  AccountView(positions={"MES": 2.0})))
    assert len(at_the_cap.submit([sell(2)])) == 1, "the order that closes the long is refused"
    assert broker.orders and broker.orders[-1].intent.quantity == 2.0

    under_the_cap = executor(FakeBroker(), risk=a_governor(
        Limits(max_position=2.0), AccountView(positions={"MES": 1.0})))
    under_the_cap.submit([sell(2)])
    assert under_the_cap.adapter.orders[-1].intent.quantity == 2.0, (
        "a closing sell must not be shrunk into a partial exit")


def test_a_reduction_to_zero_is_a_refusal_however_it_was_spelled():
    gov = a_governor(Limits(max_position=2.0), AccountView(positions={"MES": 2.0}))
    broker = FakeBroker()
    ex = executor(broker, risk=gov)
    assert ex.submit([buy(3)]) == []
    assert broker.orders == []


def test_a_limit_whose_input_is_unknown_denies_rather_than_skipping_itself():
    """"Probably okay" is not a state: a configured limit with a missing input must deny."""
    gov = a_governor(Limits(max_daily_loss=500.0), AccountView(daily_pnl=None))
    broker = FakeBroker()
    ex = executor(broker, risk=gov)
    assert ex.submit([buy(1)]) == []
    assert broker.orders == []
    assert ex.refused[-1][1].binding == (Reason.DATA_UNAVAILABLE.value,)


def test_the_journal_is_consulted_before_the_risk_chain(tmp_path):
    """A duplicate is refused whatever the chain would have said, and vice versa: a risk
    denial is journalled FAILED so the same intent cannot be quietly retried."""
    broker = FakeBroker()
    journal = IntentJournal(tmp_path / "intents.jsonl")
    gov = a_governor()
    gov.trip(Reason.MANUAL_HALT, "halted")
    ex = executor(broker, risk=gov, journal=journal)
    intent = buy(1, iid=an_id())

    assert ex.submit([intent]) == []
    assert journal.seen(an_id()).state is IntentState.FAILED
    assert ex.refused[-1][1].binding == (Reason.MANUAL_HALT.value,)

    assert ex.submit([intent]) == []
    assert ex.refused[-1][1].binding == ("IDEMPOTENCY_DUPLICATE",)
    assert broker.orders == []


def test_a_venue_rejection_is_an_ack_not_an_exception_and_is_journalled_failed(tmp_path):
    broker = FakeBroker(reject={"MES"})
    journal = IntentJournal(tmp_path / "intents.jsonl")
    ex = executor(broker, journal=journal)

    (ack,) = ex.submit([buy(1, iid=an_id())])

    assert isinstance(ack, Ack) and ack.accepted is False
    assert journal.seen(an_id()).state is IntentState.FAILED
    assert broker.open_positions() == {} and broker.working() == {}


# =====================================================================================
# INVARIANT 10 - nothing reaches a venue while ORDER_TRANSMISSION_ENABLED is false
# =====================================================================================

def _frozen_configuration(tmp_path) -> qb_config.Configuration:
    """A configuration loaded with no secret file, so nothing under live/ is read."""
    return qb_config.Configuration.load(secret_file=tmp_path / "absent.env", export=False)


def test_the_runner_transmission_constants_are_false():
    import intraday_trader
    import paper_trade

    from quant_brain.brokers import projectx

    assert intraday_trader.ORDER_TRANSMISSION_ENABLED is False
    assert paper_trade.ORDER_TRANSMISSION_ENABLED is False
    assert projectx.ORDER_TRANSMISSION_ENABLED is False


def test_transmission_is_refused_and_says_the_code_switch_is_why(tmp_path):
    allowed, why = qb_config.transmission_allowed(
        False, configuration=_frozen_configuration(tmp_path))
    assert allowed is False
    assert any("ORDER_TRANSMISSION_ENABLED constant is False" in w for w in why)


def test_a_runner_shaped_gate_sends_nothing_to_the_venue(tmp_path):
    """The runner's own shape: consult `transmission_allowed` first, then submit.

    Both runners hold the constant at False, so the guarded branch is not entered and the
    adapter is never reached. Asserted at the venue rather than at the branch, because "the
    if was false" is a weaker claim than "the broker received nothing".
    """
    import intraday_trader

    broker = FakeBroker()
    ex = executor(broker)
    allowed, why = qb_config.transmission_allowed(
        intraday_trader.ORDER_TRANSMISSION_ENABLED,
        configuration=_frozen_configuration(tmp_path))

    if allowed:                                            # pragma: no cover - never taken
        ex.submit([buy(1)])

    assert allowed is False and why
    assert broker.orders == [], "the venue must see nothing while transmission is frozen"


def test_the_projectx_adapter_records_what_it_would_have_sent_and_sends_nothing(tmp_path):
    """The real prop-firm adapter, driven with no transport. It cannot reach a network.

    Constructed with `transport=None` there is literally nothing to call, and `submit()`
    routes to the dry-run branch, which returns a non-accepted Ack carrying the translated
    body. That body is the deliverable of a dry run and is worth asserting on: a wrong
    contract id or a wrong side would otherwise only be discovered live.
    """
    from quant_brain.brokers.projectx import ProjectXAdapter

    adapter = ProjectXAdapter.for_dry_run(account_id="PRACTICE-1")
    ex = RoutedExecutor(RiskChain(), adapter, authority=Authority.practice("projectx"))

    (ack,) = ex.submit([sell(2, symbol="MES")])

    assert ack.accepted is False and "dry run" in ack.reason
    assert adapter.transport is None
    assert adapter.would_send == [{"accountId": "PRACTICE-1", "contractId": "MES",
                                   "type": 2, "side": 1, "size": 2,
                                   "customTag": "integration"}]
    assert adapter.working() == {}
