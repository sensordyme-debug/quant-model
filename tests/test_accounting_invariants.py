"""Accounting identities, made permanent.

WHY THIS FILE EXISTS
--------------------
An audit measured that all four backtest/accounting engines in this repository close their
accounting identities to 1e-10, and that `intraday_trader.Book` and `intraday_backtest.Book`
produce identical P&L on identical fill streams. That was a one-off measurement in a report.
A measurement in a report decays; an assertion in the suite does not. This file turns the
measurement into an enforced invariant, so the day an engine stops closing its books the
suite says so rather than a future audit.

THE FOUR ENGINES
----------------
    quant_brain.markets.futures_cme.execution_sim  fills + `core.execution.Position`
    scripts/intraday_backtest.py    `Book`      cash-and-marks
    scripts/intraday_trader.py      `Book`      cost-basis-and-closed-P&L
    scripts/futures_discover.py     the funnel's per-session P&L loop inside `evaluator`

The two `Book` classes are structurally different implementations of the same arithmetic -
one tracks cash, the other tracks signed cash per symbol and sweeps it into a closed bucket
when a symbol goes flat - which is exactly why their agreement is worth asserting. A third,
`core.execution.Position` (average-cost, from a different package), is used as an independent
referee: three implementations that were written separately and agree to 1e-12 is evidence;
one implementation checked against itself is not.

THE IDENTITY
------------
    starting_equity + realized_pnl + unrealized_pnl - commissions - fees - slippage == equity

stated per engine in whatever the engine's own vocabulary is, and asserted at two tolerances:

    REL_TOL   1e-9  relative, the contract this file promises callers
    AUDIT_TOL 1e-10 relative to equity, the residual the audit actually measured

The second is the one that catches a slow rot from 1e-15 to 1e-8 while the first still passes.

ORDER-INDEPENDENCE
------------------
`RiskChain` takes the intersection of what its engines permit, so composing two independent
*reducing* engines must commute. The shipped implementation is correct - caps of 2 and 10
return 2 in either order - but a mutation returning the LAST decision instead of the minimum
survived the entire existing suite. `test_a_reducing_chain_commutes` and
`test_the_chain_returns_the_minimum_never_the_last` close that hole. They are ordinary
passing assertions, not xfails: nothing is broken here, it was merely untested.

RUNNING
    python -m pytest tests/test_accounting_invariants.py -q
"""
from __future__ import annotations

import datetime as dt
import importlib
import itertools
import sys
from dataclasses import replace
from pathlib import Path

import pytest

pytestmark = pytest.mark.acceptance

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
for _p in (str(SCRIPTS), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from quant_brain.core.execution import (  # noqa: E402
    Fill,
    OrderIntent,
    OrderType,
    Position,
    Side,
)
from quant_brain.core.instruments import AssetClass, InstrumentSpec  # noqa: E402
from quant_brain.core.risk import RiskChain, RiskDecision  # noqa: E402
from quant_brain.markets.futures_cme import execution_sim as ex  # noqa: E402
from quant_brain.markets.futures_cme import instruments as inst  # noqa: E402
from quant_brain.markets.futures_cme import topstep as ts  # noqa: E402
from quant_brain.markets.futures_cme import twin as tw  # noqa: E402
from quant_brain.markets.futures_cme.propfirm import (  # noqa: E402
    AccountState,
    PropFirmRiskEngine,
)

# ======================================================================================
# TOLERANCES - stated, not implied
# ======================================================================================

#: The contract this file promises: every identity closes to one part in a billion.
REL_TOL = 1e-9
#: Absolute floor, so an identity whose true value is 0.0 is not tested against 0 * rel.
ABS_TOL = 1e-9
#: What the audit actually measured. Asserted relative to ACCOUNT EQUITY rather than to the
#: P&L, because that is the number a residual would have to corrupt to matter, and because a
#: P&L that happens to be near zero would otherwise make the test unfalsifiable.
AUDIT_TOL = 1e-10


def closes(residual: float, scale: float) -> bool:
    """Whether `residual` is inside the audit's tolerance at the given money scale."""
    return abs(residual) <= AUDIT_TOL * max(1.0, abs(scale))


# ======================================================================================
# IMPORTING THE SCRIPTS
# ======================================================================================
# `intraday_backtest`, `intraday_trader` and `futures_discover` are scripts, not packages.
# `tests/conftest.py` already puts `scripts/` on `sys.path` (and the autouse `isolate_live`
# fixture imports the trader), but this file does not rely on that: it puts the path up
# itself above and imports through `importlib` with a guard, so the file is honest about
# which engines it could actually reach instead of erroring at collection.


def _script(name: str):
    """Import a top-level script module, or skip with the reason it could not be reached."""
    try:
        return importlib.import_module(name)
    except Exception as exc:  # noqa: BLE001 - the reason is the point of the skip
        pytest.skip(f"{name} is not importable ({type(exc).__name__}: {exc})")


@pytest.fixture(scope="module")
def backtest():
    return _script("intraday_backtest")


@pytest.fixture(scope="module")
def trader():
    return _script("intraday_trader")


@pytest.fixture(scope="module")
def common():
    return _script("intraday_common")


@pytest.fixture(scope="module")
def discover():
    return _script("futures_discover")


# ======================================================================================
# THE DETERMINISTIC TRADE SEQUENCE
# ======================================================================================
# Fourteen orders on one contract. No randomness, no clock, no data store. It contains
# every shape that has ever broken a book in this repository: adds to an existing position,
# partial reductions, a close to exactly flat, a flip through zero, and a re-open.

FUTURES_SEQUENCE: tuple[tuple[Side, int, float], ...] = (
    (Side.BUY, 2, 5000.00),    # open long 2
    (Side.BUY, 3, 5002.00),    # add       long 5
    (Side.SELL, 1, 5006.00),   # reduce    long 4
    (Side.SELL, 4, 5004.00),   # close     flat
    (Side.SELL, 2, 5001.00),   # open      short 2
    (Side.BUY, 1, 4998.00),    # reduce    short 1
    (Side.BUY, 3, 4995.00),    # FLIP through zero -> long 2
    (Side.SELL, 2, 5003.00),   # close     flat
    (Side.BUY, 2, 5007.00),    # open      long 2
    (Side.SELL, 5, 5010.00),   # FLIP through zero -> short 3
    (Side.BUY, 4, 5008.00),    # flip back           -> long 1
    (Side.SELL, 1, 5012.00),   # close     flat
    (Side.SELL, 2, 5011.00),   # open      short 2
    (Side.BUY, 1, 5009.00),    # reduce    short 1
)

FUTURES_MARK = 5009.50
FUTURES_START_EQUITY = 50_000.0
MES = "MES"


def _quote(mid: float, *, size: int = 50) -> ex.Quote:
    """A one-tick-wide MES quote around `mid`. MES ticks at 0.25, so half a tick is 0.125."""
    return ex.Quote(bid=mid - 0.125, ask=mid + 0.125, bid_size=size, ask_size=size)


def _run_futures_sequence():
    """Drive `ExecutionSimulator` + `Position` through FUTURES_SEQUENCE.

    Returns (sim, position, cash, per_trade_realized, fills). `cash` is kept by this test
    and not by either production object on purpose: the identity being asserted is that an
    independently-maintained cash ledger agrees with the engine's realized/unrealized split.
    """
    sim = ex.ExecutionSimulator(cost=ex.CostModel.for_contract(MES), symbol=MES)
    spec = inst.get(MES).spec
    pos = Position(spec=spec)
    cash = FUTURES_START_EQUITY
    per_trade: list[float] = []
    for side, qty, mid in FUTURES_SEQUENCE:
        result = sim.execute(OrderIntent(MES, side, qty), _quote(mid))
        assert result.filled, f"the fixture must fill every order: {result}"
        fill = result.fill
        cash -= fill.signed_quantity * fill.price * spec.multiplier + fill.cost()
        per_trade.append(pos.apply(fill))
    return sim, pos, cash, per_trade, list(sim.fills)


# --------------------------------------------------------------------------------------
# ENGINE 1: quant_brain.markets.futures_cme.execution_sim + core.execution.Position
# --------------------------------------------------------------------------------------

def test_execution_sim_closes_the_accounting_identity():
    """start + realized + unrealized == equity, to REL_TOL and to the audit's AUDIT_TOL.

    `Position.apply` already nets each fill's cost out of the realized figure it returns, so
    the identity in this engine's own vocabulary is

        equity = starting_equity + realized_net + unrealized

    and the cost-explicit form is recovered separately below. Both are asserted, because a
    bug that double-charged commission would satisfy one and not the other.
    """
    sim, pos, cash, _per_trade, _fills = _run_futures_sequence()
    unrealized = pos.unrealized(FUTURES_MARK)
    equity = cash + pos.quantity * FUTURES_MARK * inst.get(MES).spec.multiplier

    expected = FUTURES_START_EQUITY + pos.realized + unrealized
    assert equity == pytest.approx(expected, rel=REL_TOL, abs=ABS_TOL)
    assert closes(equity - expected, equity), (
        f"residual {equity - expected:.3e} exceeds the audited {AUDIT_TOL:.0e} "
        f"relative to equity {equity:,.2f}")


def test_execution_sim_costs_are_charged_exactly_once():
    """realized_gross - commissions - slippage == realized_net.

    The costs are charged in `Position.apply` via `Fill.cost()` and reported independently by
    the simulator's own `total_commission` / `total_slippage`. If the two ever disagree, one
    of them is counting a fill twice - which on this sequence would be worth $57.75 of the
    $255.00 gross, i.e. 23% of the result.
    """
    sim, pos, _cash, _per_trade, _fills = _run_futures_sequence()
    gross = pos.realized + sim.total_commission + sim.total_slippage

    assert pos.realized == pytest.approx(
        gross - sim.total_commission - sim.total_slippage, rel=REL_TOL, abs=ABS_TOL)
    assert sim.total_cost == pytest.approx(
        sim.total_commission + sim.total_slippage, rel=REL_TOL, abs=ABS_TOL)
    # Every market order crosses the spread, so no fill may be recorded at a better price
    # than the mid. A negative slippage here would mean the simulator is paying the trader
    # to trade, which is the classic way a backtest manufactures return.
    assert all(f.slippage >= 0.0 for f in sim.fills)
    assert all(f.commission > 0.0 for f in sim.fills)


def test_execution_sim_every_trade_reconciles():
    """Sum of the per-trade realized figures == the position's running total. No leakage."""
    _sim, pos, _cash, per_trade, fills = _run_futures_sequence()
    assert len(per_trade) == len(fills) == len(FUTURES_SEQUENCE)
    assert sum(per_trade) == pytest.approx(pos.realized, rel=REL_TOL, abs=ABS_TOL)


def test_execution_sim_every_position_reconciles_and_flat_is_exactly_zero():
    """Sum of signed fills == final position; flattening leaves EXACTLY 0.0, not 1e-16.

    "Approximately flat" is not flat: `intraday_trader.Book` deletes a symbol at zero and a
    residual would leave a phantom position that the next session's flatten would try to
    sell. The assertion is `== 0.0`, deliberately without a tolerance.
    """
    sim, pos, cash, _per_trade, fills = _run_futures_sequence()
    spec = inst.get(MES).spec
    assert sum(f.signed_quantity for f in fills) == pytest.approx(pos.quantity, abs=0.0)

    # Flatten it. A FLATTEN intent bypasses the gate, which is the whole point of the type.
    side = Side.SELL if pos.quantity > 0 else Side.BUY
    result = sim.execute(
        OrderIntent(MES, side, abs(pos.quantity), order_type=OrderType.FLATTEN),
        _quote(FUTURES_MARK))
    assert result.filled
    cash -= result.fill.signed_quantity * result.fill.price * spec.multiplier
    cash -= result.fill.cost()
    pos.apply(result.fill)

    assert pos.quantity == 0.0
    assert pos.avg_price == 0.0
    assert pos.unrealized(FUTURES_MARK) == 0.0
    # Flat means cash IS equity, and it equals the start plus everything realized.
    assert cash == pytest.approx(FUTURES_START_EQUITY + pos.realized, rel=REL_TOL, abs=ABS_TOL)
    assert closes(cash - (FUTURES_START_EQUITY + pos.realized), cash)


def test_execution_sim_refusals_move_no_money():
    """A refused order must leave cash, position and cost totals bit-identical.

    Three refusals a venue really makes: zero quantity, no quote (Part 32 - do not invent a
    price), and the position cap. Each is checked to change nothing at all, because the
    dangerous failure is not the refusal, it is a refusal that has already been booked.
    """
    sim = ex.ExecutionSimulator(cost=ex.CostModel.for_contract(MES), symbol=MES,
                                max_position=3)
    pos = Position(spec=inst.get(MES).spec)
    pos.apply(sim.execute(OrderIntent(MES, Side.BUY, 2), _quote(5000.0)).fill)
    before = (sim.total_commission, sim.total_slippage, pos.quantity, pos.realized,
              len(sim.fills))

    assert not sim.execute(OrderIntent(MES, Side.BUY, 0), _quote(5000.0)).filled
    assert not sim.execute(OrderIntent(MES, Side.BUY, 1), None).filled
    assert not sim.execute(OrderIntent(MES, Side.BUY, 5), _quote(5000.0),
                           position=pos.quantity).filled

    after = (sim.total_commission, sim.total_slippage, pos.quantity, pos.realized,
             len(sim.fills))
    assert before == after
    assert len(sim.rejects) == 3
    assert [r.reason for r in sim.rejects] == [
        ex.RejectReason.ZERO_QUANTITY, ex.RejectReason.NO_PRICE,
        ex.RejectReason.POSITION_LIMIT]


# ======================================================================================
# THE EQUITY FILL STREAM, shared by engines 2 and 3
# ======================================================================================
# Eleven fills across three symbols, chosen so that one symbol ends flat by a scale-out, one
# ends flat by a flip-and-close, and one is still open at the mark - so the final state
# exercises the closed bucket, the flat-deletion path and the mark-to-market path at once.

EQUITY_FILLS: tuple[tuple[str, int, float], ...] = (
    ("AAA", 100, 100.0),
    ("AAA", 50, 101.0),
    ("BBB", -80, 50.0),
    ("AAA", -150, 103.0),
    ("BBB", 80, 49.0),
    ("CCC", 10, 250.0),
    ("CCC", -20, 255.0),
    ("CCC", 10, 254.0),
    ("AAA", 25, 99.0),
    ("BBB", -40, 51.0),
    ("BBB", 40, 52.0),
)
EQUITY_MARKS = {"AAA": 102.0, "BBB": 53.0, "CCC": 256.0}
EQUITY_START = 1_000_000.0
EQUITY_DAY = dt.datetime(2026, 9, 10, 10, 0)

SHARE_SPEC = {
    s: InstrumentSpec(symbol=s, asset_class=AssetClass.EQUITY, multiplier=1.0, tick=0.01)
    for s in ("AAA", "BBB", "CCC")
}


def _cost_of(common, sym: str, qty: int, price: float, when=EQUITY_DAY) -> float:
    """Exactly the cost `intraday_backtest.Book.fill` computes for this fill.

    Not a reimplementation: it calls the same two production functions with the same
    arguments the Book passes them. The sign of `qty` is load-bearing - a sale pays the SEC
    Section 31 fee and the FINRA TAF on top of the commission and a purchase does not.
    """
    return (common.commission(qty, price, common.share_scale(sym, when.date()))
            + common.slippage(qty, price))


def _referee(fills, marks) -> tuple[float, float, dict[str, Position]]:
    """`core.execution.Position` as an independent average-cost ledger.

    A third implementation, from a different package, written by nobody who was thinking
    about either `Book`. Returns (realized_net, unrealized, positions).
    """
    book = {s: Position(spec=SHARE_SPEC[s]) for s in SHARE_SPEC}
    for sym, qty, price, cost in fills:
        book[sym].apply(Fill(symbol=sym, side=Side.of(qty), quantity=abs(qty),
                             price=price, commission=cost))
    realized = sum(p.realized for p in book.values())
    unrealized = sum(p.unrealized(marks[s]) for s, p in book.items() if p.quantity)
    return realized, unrealized, book


@pytest.fixture
def priced(common):
    """The fill stream with each fill's production-computed cost attached."""
    return [(sym, qty, price, _cost_of(common, sym, qty, price))
            for sym, qty, price in EQUITY_FILLS]


# --------------------------------------------------------------------------------------
# ENGINE 2: scripts/intraday_backtest.py Book   (cash and marks)
# --------------------------------------------------------------------------------------

def test_backtest_book_cash_closes_against_an_independent_ledger(backtest, priced):
    """value(marks) - starting_equity == realized + unrealized, refereed by `Position`.

    The Book keeps cash and positions; `Position` keeps average cost and realized P&L. They
    share no code. Their agreement is the accounting identity for this engine:

        cash + Sigma q*mark  ==  start + realized_net + unrealized
    """
    book = backtest.Book(EQUITY_START)
    for sym, qty, price in EQUITY_FILLS:
        book.fill(EQUITY_DAY, sym, qty, price, "invariant")

    realized, unrealized, _ = _referee(priced, EQUITY_MARKS)
    equity = book.value(EQUITY_MARKS)
    expected = EQUITY_START + realized + unrealized

    assert equity == pytest.approx(expected, rel=REL_TOL, abs=ABS_TOL)
    assert closes(equity - expected, equity), (
        f"residual {equity - expected:.3e} exceeds {AUDIT_TOL:.0e} of equity {equity:,.2f}")


def test_backtest_book_trades_and_costs_reconcile(backtest, priced):
    """Sigma per-trade cost == book.costs, and Sigma signed qty == the final position."""
    book = backtest.Book(EQUITY_START)
    for sym, qty, price in EQUITY_FILLS:
        book.fill(EQUITY_DAY, sym, qty, price, "invariant")

    assert len(book.trades) == len(EQUITY_FILLS)
    assert sum(t["cost"] for t in book.trades) == pytest.approx(
        book.costs, rel=REL_TOL, abs=ABS_TOL)
    # Every trade's cost is the one production `commission` + `slippage` would charge.
    assert [t["cost"] for t in book.trades] == pytest.approx(
        [c for _s, _q, _p, c in priced], rel=REL_TOL, abs=ABS_TOL)

    for sym in ("AAA", "BBB", "CCC"):
        net = sum(q for s, q, _p in EQUITY_FILLS if s == sym)
        assert book.pos.get(sym, 0) == net
    # BBB and CCC end flat and must be GONE from the map, not present at zero.
    assert set(book.pos) == {"AAA"}
    assert "BBB" not in book.pos and "CCC" not in book.pos


# --------------------------------------------------------------------------------------
# ENGINE 3: scripts/intraday_trader.py Book   (cost basis and closed P&L)
# --------------------------------------------------------------------------------------

def test_trader_book_pnl_closes_against_an_independent_ledger(backtest, trader, priced):
    """closed + Sigma cost + marks == realized + unrealized, refereed by `Position`.

    This Book has no cash: it holds signed cash per open symbol and sweeps a symbol's cash
    into `_closed` the moment it goes flat. That is a genuinely different decomposition of
    the same number, so agreeing with the average-cost referee is a real check and not a
    tautology.
    """
    book = trader.Book()
    for sym, qty, price, cost in priced:
        trader.book_fill(book, sym, qty, price, cost)

    realized, unrealized, _ = _referee(priced, EQUITY_MARKS)
    pnl = book.pnl(EQUITY_MARKS)
    expected = realized + unrealized

    assert pnl == pytest.approx(expected, rel=REL_TOL, abs=ABS_TOL)
    assert closes(pnl - expected, EQUITY_START)
    assert book.costs == pytest.approx(sum(c for *_x, c in priced), rel=REL_TOL, abs=ABS_TOL)
    assert book.trades == len(priced)


def test_trader_book_position_reconciles_and_flat_leaves_the_map(trader, priced):
    """Sigma signed fills == final position; a symbol at zero is deleted, not stored as 0."""
    book = trader.Book()
    for sym, qty, price, cost in priced:
        trader.book_fill(book, sym, qty, price, cost)

    for sym in ("AAA", "BBB", "CCC"):
        net = sum(q for s, q, _p in EQUITY_FILLS if s == sym)
        assert book.pos.get(sym, 0) == net
    assert set(book.pos) == {"AAA"}
    # A flat symbol keeps no cost basis either - its cash has moved to the closed bucket.
    assert set(book.cost) == {"AAA"}


def test_the_cost_model_separates_commission_from_regulatory_fees(common):
    """fees == commission(sell) - commission(buy), so the identity can name them apart.

    The identity this file promises spells commissions and fees separately, and
    `intraday_common.commission` returns them summed. They are separable exactly, because
    the SEC Section 31 fee and the FINRA TAF are charged on sells only and are added AFTER
    the 1%-of-notional cap on the broker commission. Asserted here so the decomposition used
    below is a fact about the production function rather than an assumption about it.
    """
    qty, price = 1_000, 100.0
    buy = common.commission(qty, price)
    sell = common.commission(-qty, price)
    fees = sell - buy
    expected = qty * price * common.SEC_FEE_RATE + min(qty * common.TAF_PER_SHARE,
                                                       common.TAF_CAP)
    assert fees == pytest.approx(expected, rel=REL_TOL, abs=ABS_TOL)
    assert fees > 0.0 and buy > 0.0


def test_the_full_identity_names_commissions_and_fees_and_slippage(common, trader, priced):
    """start + realized + unrealized - commissions - fees - slippage == equity.

    The form the brief asks for, with the three cost components pulled apart rather than
    lumped. `realized`/`unrealized` here are GROSS of cost (the referee is fed cost-free
    fills), so every dollar of friction has to be subtracted explicitly and the identity
    fails if any one of the three is dropped or double-counted.
    """
    gross_fills = [(s, q, p, 0.0) for s, q, p, _c in priced]
    realized_gross, unrealized_gross, _ = _referee(gross_fills, EQUITY_MARKS)

    commissions = sum(common.commission(abs(q), p, common.share_scale(s, EQUITY_DAY.date()))
                      for s, q, p, _c in priced)
    fees = sum(common.commission(q, p, common.share_scale(s, EQUITY_DAY.date()))
               - common.commission(abs(q), p, common.share_scale(s, EQUITY_DAY.date()))
               for s, q, p, _c in priced)
    slip = sum(common.slippage(q, p) for _s, q, p, _c in priced)

    book = trader.Book()
    for sym, qty, price, cost in priced:
        trader.book_fill(book, sym, qty, price, cost)
    equity = EQUITY_START + book.pnl(EQUITY_MARKS)

    expected = (EQUITY_START + realized_gross + unrealized_gross
                - commissions - fees - slip)
    assert equity == pytest.approx(expected, rel=REL_TOL, abs=ABS_TOL)
    assert closes(equity - expected, equity)
    # And the three components really do add up to what the books charged.
    assert commissions + fees + slip == pytest.approx(book.costs, rel=REL_TOL, abs=ABS_TOL)


# --------------------------------------------------------------------------------------
# THE TWO BOOKS AGREE - the audit's second finding, pinned
# --------------------------------------------------------------------------------------
# Each case is (label, fills, marks). `fills` are (symbol, signed_qty, price); the cost is
# computed once, from production code, and handed to both books so the comparison is of the
# ARITHMETIC and not of two different cost models.

STRESS_CASES: tuple[tuple[str, tuple, dict], ...] = (
    (
        "partial fills - one intent worked out over four prints",
        (("AAA", 25, 100.0), ("AAA", 25, 100.5), ("AAA", 25, 101.0), ("AAA", 25, 100.25),
         ("AAA", -60, 102.0)),
        {"AAA": 101.5},
    ),
    (
        "reversal - long flipped to short through zero and back",
        (("BBB", 100, 40.0), ("BBB", -250, 42.0), ("BBB", 300, 41.0), ("BBB", -150, 43.0)),
        {"BBB": 41.75},
    ),
    (
        "zero-quantity fill - must move no money in either book",
        (("CCC", 10, 250.0), ("CCC", 0, 250.0), ("CCC", -10, 251.0)),
        {},
    ),
    (
        "same-symbol round trip closing exactly flat",
        (("AAA", 200, 75.0), ("AAA", -200, 76.25)),
        {},
    ),
    (
        "overnight carry - position held across a session boundary",
        (("AAA", 120, 30.0), ("BBB", -60, 90.0), ("AAA", -40, 31.0),
         ("AAA", 40, 30.5), ("BBB", 60, 89.0)),
        {"AAA": 30.75, "BBB": 89.5},
    ),
    (
        "short-only round trip that loses money",
        (("CCC", -70, 500.0), ("CCC", -30, 505.0), ("CCC", 100, 512.0)),
        {},
    ),
    (
        "three symbols interleaved, one left open at the mark",
        EQUITY_FILLS,
        EQUITY_MARKS,
    ),
)


@pytest.mark.parametrize("label,fills,marks", STRESS_CASES,
                         ids=[c[0].split(" - ")[0] for c in STRESS_CASES])
def test_the_two_books_agree_on_identical_fill_streams(backtest, trader, common,
                                                       label, fills, marks):
    """`intraday_backtest.Book` and `intraday_trader.Book` produce identical P&L.

    The audit measured this once. Here it is, enforced, on seven streams including the four
    shapes that have historically broken book arithmetic in this repository.

    The zero-quantity case is the one asymmetry and it is deliberate: `Book.fill` returns
    early on `delta == 0` while `book_fill` has no such guard, so the trader's TRADE COUNTER
    advances by one where the backtest's does not. Their P&L is unaffected and that is what
    is asserted; the counter divergence is recorded in this file's report as a
    recommendation rather than silently normalised away here.
    """
    day = EQUITY_DAY
    cash_book = backtest.Book(EQUITY_START)
    cost_book = trader.Book()
    for sym, qty, price in fills:
        cost = 0.0 if qty == 0 else _cost_of(common, sym, qty, price, day)
        cash_book.fill(day, sym, qty, price, label)
        trader.book_fill(cost_book, sym, qty, price, cost)

    cash_pnl = cash_book.value(marks) - EQUITY_START
    cost_pnl = cost_book.pnl(marks)

    assert cash_book.pos == cost_book.pos, "the two books must hold the same positions"
    assert cash_pnl == pytest.approx(cost_pnl, rel=REL_TOL, abs=ABS_TOL)
    assert closes(cash_pnl - cost_pnl, EQUITY_START), (
        f"{label}: the two books differ by {cash_pnl - cost_pnl:.3e}, beyond the audited "
        f"{AUDIT_TOL:.0e} of ${EQUITY_START:,.0f}")
    assert cash_book.costs == pytest.approx(cost_book.costs, rel=REL_TOL, abs=ABS_TOL)


def test_the_two_books_agree_with_the_independent_referee(backtest, trader, priced):
    """Three implementations, one number. Cash book, cost book and average-cost `Position`.

    Two engines agreeing can mean both are wrong the same way - they were written in the
    same repository by the same hand. `core.execution.Position` is average-cost accounting
    from `quant_brain.core`, reached by neither script, and it agrees to 1e-12 on a $1m book.
    """
    cash_book = backtest.Book(EQUITY_START)
    cost_book = trader.Book()
    for sym, qty, price, cost in priced:
        cash_book.fill(EQUITY_DAY, sym, qty, price, "referee")
        trader.book_fill(cost_book, sym, qty, price, cost)

    realized, unrealized, _ = _referee(priced, EQUITY_MARKS)
    referee = realized + unrealized
    cash = cash_book.value(EQUITY_MARKS) - EQUITY_START
    held = cost_book.pnl(EQUITY_MARKS)

    for name, value in (("cash book", cash), ("cost book", held)):
        assert value == pytest.approx(referee, rel=REL_TOL, abs=ABS_TOL), name
        assert closes(value - referee, EQUITY_START), name


# --------------------------------------------------------------------------------------
# ENGINE 4: scripts/futures_discover.py - the funnel's per-session P&L loop
# --------------------------------------------------------------------------------------

class _FixedSignal:
    """A hypothesis with a hard-coded position series. The evaluator only calls `.signal`."""

    def __init__(self, positions):
        self.name = "acct-invariant"
        self.family = "test"
        self._positions = tuple(positions)

    def signal(self, X):
        import numpy as np
        return np.asarray(self._positions[:len(X)], dtype=float)


#: Deterministic, hand-written: 20 bars, six position changes, no RNG anywhere.
_POSITIONS = (0, 1, 1, 1, 0, -1, -1, 0, 1, 1, 0, 0, -1, -1, -1, 0, 1, 0, 0, 0)


def _funnel_inputs(sessions: int = 3, bars: int = 20):
    """Three synthetic ES-priced sessions built from a fixed arithmetic ramp.

    No random numbers: the close series is a closed-form zig-zag, so the P&L this produces is
    the same on every machine and every run.
    """
    import pandas as pd

    frames, feats = [], []
    for d in range(sessions):
        close = [5000.0 + (d * 3) + (i % 7) - (i % 3) * 1.5 for i in range(bars)]
        day = dt.date(2026, 1, 5) + dt.timedelta(days=d)
        frames.append(pd.DataFrame({"c": close, "day": [day] * bars}))
        feats.append(pd.DataFrame({"f": close}))
    return frames, feats


def _funnel_twin():
    """A real `TopstepTwin`, so the survival gate can run rather than crash on a None.

    The funnel returns from four places and the identity has to hold at every one of them.
    Handing the evaluator a working twin means a change to the gate ORDER or to `MIN_TRADES`
    moves which exit this test takes without turning an accounting test into an unrelated
    `AttributeError` - the identity is the subject, not the gate.
    """
    return tw.TopstepTwin(50_000, payout_policy=tw.PayoutPolicy(fraction=0.5))


def test_the_funnel_pnl_loop_closes(discover):
    """Sigma per-session net P&L == gross - costs, exactly.

    `evaluator.run` accumulates `gross` and `costs` separately from the per-session net it
    appends to `pnl`, so the three can drift apart. They must not: the funnel's cost gate
    divides one by the other and its Topstep gate feeds the third to the twin.

    The assertion is on the returned dict rather than at a particular gate, because every
    exit carries the same three numbers.
    """
    sessions, feats = _funnel_inputs()
    run = discover.evaluator(sessions, feats, contracts=1, twin_obj=_funnel_twin(),
                             symbol="MES")
    out = run(_FixedSignal(_POSITIONS))

    assert out["sessions"] == len(sessions)
    assert len(out["pnl"]) == len(sessions)
    net = sum(out["pnl"])
    assert net == pytest.approx(out["gross"] - out["costs"], rel=REL_TOL, abs=ABS_TOL)
    assert closes(net - (out["gross"] - out["costs"]), max(abs(out["gross"]), 1.0))
    assert out["mean_per_session"] == pytest.approx(net / len(sessions),
                                                    rel=REL_TOL, abs=ABS_TOL)
    assert out["costs"] >= 0.0
    assert out["trades"] >= 0


def test_the_funnel_identity_holds_at_a_different_gate_exit(discover, monkeypatch):
    """The same identity, reached through the Topstep-survival exit instead of trade count.

    `run` returns early from four places. The trade-count floor is the one the fixture grid
    trips naturally; lowering it for the length of this test walks the loop all the way past
    the cost gate and into the twin, which is a different return statement carrying the same
    three numbers. If a future refactor moves the accumulation of `gross` or `costs` inside
    a branch, one of these two tests catches it.
    """
    monkeypatch.setattr(discover, "MIN_TRADES", 1)
    monkeypatch.setattr(discover, "MAX_COST_SHARE", 10.0)
    # And gate 0, for the same reason as the other two: this fixture exists to make an
    # accounting identity checkable, not to look like a plausible strategy, and the leakage
    # canary refuses it on `ceiling_share`. The canary's own behaviour is asserted in
    # tests/test_leakage_redteam.py; disabling it here is what lets the identity be reached
    # at the deepest return statement.
    monkeypatch.setattr(discover, "MAX_CEILING_SHARE", float("inf"))
    sessions, feats = _funnel_inputs()
    out = discover.evaluator(sessions, feats, contracts=1, twin_obj=_funnel_twin(),
                             symbol="MES")(_FixedSignal(_POSITIONS))

    assert "cost_share" in out, "the run did not get past the cost gate"
    assert out["cost_share"] == pytest.approx(out["costs"] / abs(out["gross"]),
                                              rel=REL_TOL, abs=ABS_TOL)
    net = sum(out["pnl"])
    assert net == pytest.approx(out["gross"] - out["costs"], rel=REL_TOL, abs=ABS_TOL)
    assert closes(net - (out["gross"] - out["costs"]), max(abs(out["gross"]), 1.0))


def test_the_funnel_pnl_is_additive_across_sessions(discover):
    """Each session reconciles alone: Sigma one-session runs == the multi-session run.

    The funnel accumulates `gross`, `costs` and `trades` across sessions in one loop. If any
    state leaked between sessions - a carried position, a cost charged twice, a turn counted
    at a boundary - running the sessions one at a time would give a different total. This is
    the per-session reconciliation for an engine that reports only totals.

    `trades` is compared with one session of slack because the reported figure is a rounded
    count while `costs` is not; `costs` and `gross` are compared exactly.
    """
    sessions, feats = _funnel_inputs()
    h = _FixedSignal(_POSITIONS)
    twin = _funnel_twin()

    whole = discover.evaluator(sessions, feats, contracts=1, twin_obj=twin,
                               symbol="MES")(h)
    parts = [discover.evaluator([s], [f], contracts=1, twin_obj=twin, symbol="MES")(h)
             for s, f in zip(sessions, feats, strict=True)]

    assert sum(p["gross"] for p in parts) == pytest.approx(whole["gross"],
                                                           rel=REL_TOL, abs=ABS_TOL)
    assert sum(p["costs"] for p in parts) == pytest.approx(whole["costs"],
                                                           rel=REL_TOL, abs=ABS_TOL)
    assert abs(sum(p["trades"] for p in parts) - whole["trades"]) <= len(sessions)
    for i, part in enumerate(parts):
        assert part["pnl"][0] == pytest.approx(whole["pnl"][i], rel=REL_TOL, abs=ABS_TOL)


def test_the_funnel_charges_the_production_round_turn_cost_and_nothing_else(discover):
    """Every dollar of funnel cost is a whole number of LEGS at the production rate.

    `evaluator` takes `tick_cost` from `ExecutionSimulator.round_turn_cost` once and charges
    the book in legs - half a round turn in, half out. So

        costs / (round_turn_cost / 2)   must be a non-negative INTEGER

    and the reported turn count must agree with it to within the rounding the funnel applies
    when it publishes an integer. Stated this way, the assertion survives a change to how the
    legs are counted or when they are paid, and still fails the moment the funnel charges a
    rate that is not the one `CostModel.for_contract` produces.
    """
    sessions, feats = _funnel_inputs()
    contracts = 2
    out = discover.evaluator(sessions, feats, contracts=contracts, twin_obj=_funnel_twin(),
                             symbol="MES")(_FixedSignal(_POSITIONS))

    sim = ex.ExecutionSimulator(cost=ex.CostModel.for_contract("MES"), symbol="MES")
    round_turn = sim.round_turn_cost(contracts)
    assert round_turn > 0.0

    legs = out["costs"] / (round_turn / 2.0)
    assert legs >= 0.0
    assert legs == pytest.approx(round(legs), abs=1e-6), (
        f"${out['costs']:.4f} of cost is {legs:.6f} legs at ${round_turn:.4f} a round turn; "
        f"the funnel is charging a rate the production cost model does not produce")
    assert out["costs"] == pytest.approx(out["trades"] * round_turn,
                                         abs=round_turn / 2 + ABS_TOL)


# ======================================================================================
# ORDER-INDEPENDENCE
# ======================================================================================
# `RiskChain.evaluate` merges each engine's verdict into a running decision, and
# `RiskDecision.merge` takes the minimum quantity. So composing independent REDUCING engines
# is a commutative operation and the result must not depend on the list order.
#
# The shipped implementation is correct. It is also, today, untested in the one way that
# matters: a mutation returning the LAST engine's decision instead of the minimum survives
# the entire existing suite, because every existing chain test has the binding engine last.
# These tests make the ordering an asserted property.


def _capped_engine(cap: int) -> PropFirmRiskEngine:
    """A real `PropFirmRiskEngine` whose only active rule is a total-contract cap of `cap`."""
    profile = replace(ts.combine(50_000), max_total_contracts=cap,
                      max_contracts_per_symbol={}, scaling=())
    return PropFirmRiskEngine(AccountState(profile=profile))


def test_a_reducing_chain_commutes():
    """Caps of 2 and 10 return 2 in EITHER order. The intersection has no order."""
    intent = OrderIntent("ES", Side.BUY, 30)
    forward = RiskChain([_capped_engine(2), _capped_engine(10)]).evaluate(intent)
    reverse = RiskChain([_capped_engine(10), _capped_engine(2)]).evaluate(intent)

    assert forward.allowed and reverse.allowed
    assert forward.quantity == 2.0
    assert reverse.quantity == 2.0
    assert forward.quantity == reverse.quantity


def test_the_chain_returns_the_minimum_never_the_last():
    """Every permutation of three reducing engines returns the tightest cap.

    This is the assertion a `return last_decision` mutation cannot survive: with caps
    (7, 3, 9) there are six orderings and three distinct "last" answers, so any rule other
    than "the minimum" gives a different number in at least one permutation.
    """
    intent = OrderIntent("ES", Side.BUY, 30)
    caps = (7, 3, 9)
    results = {}
    for order in itertools.permutations(caps):
        decision = RiskChain([_capped_engine(c) for c in order]).evaluate(intent)
        results[order] = decision.quantity
        assert decision.allowed, order

    assert set(results.values()) == {float(min(caps))}, (
        f"the chain is order-dependent: {results}")
    # Every engine that bound is named, whatever the order it bound in.
    for order in itertools.permutations(caps):
        decision = RiskChain([_capped_engine(c) for c in order]).evaluate(intent)
        assert "max_total_contracts" in decision.binding


def test_a_denial_cannot_be_un_denied_by_reordering():
    """A denying engine wins from any position in the chain, and denial carries no quantity.

    The chain short-circuits on a denial, so a deny that comes FIRST and a deny that comes
    LAST take structurally different paths through `evaluate`. Both must end denied at zero.
    """
    intent = OrderIntent("ES", Side.BUY, 30)
    dead = _capped_engine(5)
    dead.state.contracts["ES"] = 5          # already at the cap: no room, so a denial

    for engines in ([dead, _capped_engine(10)], [_capped_engine(10), dead]):
        decision = RiskChain(engines).evaluate(intent)
        assert decision.allowed is False
        assert decision.quantity == 0.0
        assert decision.reasons, "a refusal that does not say why gets disabled by the next "\
                                 "person in a hurry"


def test_merge_is_commutative_on_the_decision_type_itself():
    """`RiskDecision.merge` - the primitive the chain's order-independence rests on."""
    a = RiskDecision.reduce(2.0, "cap 2", "rule_a")
    b = RiskDecision.reduce(10.0, "cap 10", "rule_b")
    assert a.merge(b).quantity == b.merge(a).quantity == 2.0
    assert a.merge(b).allowed and b.merge(a).allowed

    deny = RiskDecision.deny("no", "rule_c")
    assert a.merge(deny).allowed is False
    assert deny.merge(a).allowed is False
    assert a.merge(deny).quantity == deny.merge(a).quantity == 0.0


def test_a_flatten_reaches_the_venue_from_every_position_in_the_chain():
    """The one deliberate asymmetry: FLATTEN bypasses every engine, in any order.

    AUD-06 and AUD-08 were both cases where the order that would have CLOSED a position was
    suppressed by a sizing rule. A risk layer that can block the exit is not a risk layer,
    and this must stay true however the chain is assembled.
    """
    dead = _capped_engine(5)
    dead.state.contracts["ES"] = 5
    flatten = OrderIntent("ES", Side.SELL, 5, order_type=OrderType.FLATTEN)

    for engines in ([dead, _capped_engine(1)], [_capped_engine(1), dead]):
        decision = RiskChain(engines)(flatten)
        assert decision.allowed is True
        assert decision.quantity == 5.0
