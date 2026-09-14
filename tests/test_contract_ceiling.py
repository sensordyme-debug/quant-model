"""The contract ceiling, in the unit the caller is trading. Pins the 2026-09-14 fix.

THE DEFECT THIS FILE EXISTS TO KEEP CLOSED
------------------------------------------
`TopstepAccount.contracts_allowed` is the account-wide allowance in MICRO-EQUIVALENTS: 50 on
a $50K Combine, which the published table (help.topstep.com/en/articles/8284197) states as
"5 minis OR 50 micros", one allowance in two units. Two consumers read that 50 as raw
contracts of whatever was being sized - `core.sizing.enforce` and `twin.max_contracts` - so
a fresh $50K Combine sized in ES came out at:

    2.0-point stop   5 contracts     (a coincidence: the MLL room binds there)
    1.0-point stop  10 contracts
    0.5-point stop  20 contracts
    0.25 (one tick) 40 contracts

against a published ceiling of five, with the binding reported as `strategy_signal` every
time because the prop-firm cap never bound at all. Five ES is $250 a point; forty is $2,000
a point against $2,000 of room, so two ticks against the position is the whole account.

THE FIX, AND WHY IT IS SHAPED THIS WAY
--------------------------------------
`core` may not import `markets`. The mini/micro equivalence is a fact about a firm's product
table, which lives in `markets`, so it cannot travel to the sizer as data. It travels as an
answer instead: `MllAccount` gained `max_contracts_for(symbol) -> int | None`, implemented on
`PropFirmProfile` where the table is and on `TopstepAccount` where the open book is, and
`enforce` asks it using `ctx.spec.symbol`. `contracts_allowed` is untouched and still
reports micro-equivalents, because the CLI and the twin display the allowance the way
Topstep publishes it.

WHAT IS AND IS NOT HARD-CODED HERE
----------------------------------
The published numbers (5 minis / 50 micros at $50K) are hard-coded once, in `PUBLISHED_50K`,
because they are a citation. The 10:1 relationship between them is NOT hard-coded a second
time: `test_the_mini_and_micro_ceilings_hold_the_published_ratio` derives it from the
contract multipliers in `instruments.CONTRACTS`, so a ceiling that stopped matching the
contract it is a ceiling on would fail rather than agree with itself.
"""
from __future__ import annotations

import inspect
import math

import pytest

from quant_brain.core import sizing as sz
from quant_brain.core.instruments import AssetClass, InstrumentSpec
from quant_brain.markets.futures_cme import instruments as finst
from quant_brain.markets.futures_cme import topstep as ts
from quant_brain.markets.futures_cme import twin as tw
from quant_brain.markets.futures_cme.propfirm import PropFirmProfile

SIZE = 50_000
TARGET = 3_000.0

#: help.topstep.com/en/articles/8284197, retrieved 2026-09-13: "| $50K | 5 | 50 |".
#: (minis, micros). The one place these two numbers appear in this file.
PUBLISHED_50K = (5, 50)

MINIS = ("ES", "NQ")
MICROS = ("MES", "MNQ")

#: Every stop a caller could plausibly pass, plus two that are pathological. One ES tick is
#: 0.25 points; 0.01 is a sub-tick stop, which no venue would fill but a bad feature might
#: compute, and it is exactly the input that turned the old cap into a four-figure size.
STOPS = (10.0, 4.0, 2.0, 1.0, 0.5, 0.25, 0.05, 0.01)

#: The stops at which `PropFirmSizer`'s default quarter-of-the-room budget asks for MORE ES
#: than the five-contract ceiling, so the ceiling is what strictly binds. 0.25 x $2,000 is
#: $500 and one ES point is $50, so the ask is 10 / stop: above five below a two-point stop.
CEILING_BINDS = (1.0, 0.5, 0.25, 0.05, 0.01)
#: And the stops at which the budget asks for fewer than five, so the budget binds instead.
BUDGET_BINDS = (10.0, 4.0)


def account(profit: float = 0.0) -> ts.TopstepAccount:
    acct = ts.TopstepAccount(profile=ts.combine(SIZE, profit_target=TARGET))
    if profit:
        acct.settle_day(profit)
    return acct


def spec(symbol: str) -> InstrumentSpec:
    return finst.get(symbol).spec


def decide(symbol: str, acct: ts.TopstepAccount, stop: float, *,
           sizer: sz.Sizer | None = None,
           requested: float = 1_000_000.0) -> sz.SizeDecision:
    """Push a deliberately enormous ask through the funnel on `symbol`."""
    ctx = sz.SizeContext(spec=spec(symbol), prop_account=acct, stop_distance=stop,
                         price=6_000.0, equity=10_000_000.0, requested=requested)
    return (sizer or sz.PropFirmSizer()).size(ctx)


# ======================================================================================
# THE CEILING ITSELF
# ======================================================================================

@pytest.mark.parametrize("symbol", MINIS)
@pytest.mark.parametrize("stop", STOPS)
def test_a_mini_never_exceeds_five_at_any_stop_distance(symbol, stop):
    """Five minis is the published ceiling and no stop distance may buy a sixth.

    Parametrised over the stop because the stop is what the old defect scaled with: the cap
    was constant at 50 while the budget-implied size grew as the stop shrank, so the cap only
    ever bound by accident and stopped binding entirely below two points.
    """
    minis, _ = PUBLISHED_50K
    d = decide(symbol, account(), stop)
    assert d.available
    assert d.contracts <= minis, (
        f"{d.contracts} {symbol} at a {stop}-point stop against a {minis}-contract ceiling")


@pytest.mark.parametrize("symbol", MICROS)
@pytest.mark.parametrize("stop", STOPS)
def test_a_micro_never_exceeds_fifty_at_any_stop_distance(symbol, stop):
    """The control case, which was already correct: in micros the two units coincide."""
    _, micros = PUBLISHED_50K
    d = decide(symbol, account(), stop)
    assert d.available and d.contracts <= micros


@pytest.mark.parametrize("symbol,expected", [
    ("ES", PUBLISHED_50K[0]), ("NQ", PUBLISHED_50K[0]),
    ("MES", PUBLISHED_50K[1]), ("MNQ", PUBLISHED_50K[1]),
])
def test_the_account_states_its_ceiling_in_contracts_of_the_symbol(symbol, expected):
    assert account().max_contracts_for(symbol) == expected


def test_the_reproduction_from_the_defect_report_now_returns_five_every_time():
    """The exact four measurements in the bug report, all of which must now be five.

    Recorded as a table rather than a loop so the before/after is readable in a diff:
    5 / 10 / 20 / 40 became 5 / 5 / 5 / 5, and the binding became `prop_firm` at each one
    instead of `strategy_signal` - which is the half of the defect that mattered most,
    because a decision that names the wrong binding cannot be audited from its log line.
    """
    acct = account()
    got = {stop: decide("ES", acct, stop) for stop in (2.0, 1.0, 0.5, 0.25)}
    assert {stop: d.contracts for stop, d in got.items()} == {2.0: 5, 1.0: 5, 0.5: 5, 0.25: 5}
    assert all(d.binding is sz.Binding.PROP_FIRM for d in got.values())


def test_the_ceiling_scales_with_the_account_size_in_both_units():
    """$100K is 10 minis / 100 micros and $150K is 15 / 150, in the same 10:1 ratio."""
    for size, (minis, micros) in ((100_000, (10, 100)), (150_000, (15, 150))):
        acct = ts.TopstepAccount(profile=ts.combine(size, profit_target=TARGET))
        assert acct.max_contracts_for("ES") == minis
        assert acct.max_contracts_for("MES") == micros


# ======================================================================================
# THE 10:1 RATIO, DERIVED RATHER THAN RESTATED
# ======================================================================================

def test_the_mini_and_micro_ceilings_hold_the_published_ratio():
    """The ceiling ratio must equal the CONTRACT ratio, read off the instrument table.

    The published caps and the contract multipliers are two independent statements of the
    same fact - a micro is a tenth of its parent, so ten times as many of them fill the same
    allowance - and this asserts they agree. Hard-coding "10" here would let the two drift
    apart silently, which is how a table like this rots: the day somebody edits MES's
    multiplier or Topstep restates the micro column, exactly one of the two moves.
    """
    acct = account()
    for micro in MICROS:
        contract = finst.get(micro)
        parent = contract.parent
        assert parent is not None, f"{micro} must declare its parent to be sized as a micro"
        ratio = finst.get(parent).spec.multiplier / contract.spec.multiplier
        assert ratio == pytest.approx(10.0), (
            "the equity-index micros are a tenth of their parent; if that changed, the caps "
            "are the thing to re-derive, not this assertion")
        mini_cap = acct.max_contracts_for(parent)
        micro_cap = acct.max_contracts_for(micro)
        assert micro_cap == mini_cap * ratio, (
            f"{micro_cap} {micro} against {mini_cap} {parent} is not the {ratio:g}:1 that "
            f"the contract multipliers say it should be")


def test_the_two_ceilings_are_the_same_notional():
    """Five ES and fifty MES are one allowance, so they must buy the same exposure."""
    acct, price = account(), 6_000.0
    es = acct.max_contracts_for("ES") * spec("ES").multiplier * price
    mes = acct.max_contracts_for("MES") * spec("MES").multiplier * price
    assert es == pytest.approx(mes)


# ======================================================================================
# A MIXED BOOK CANNOT BUY THE ALLOWANCE TWICE
# ======================================================================================

def test_three_open_es_reduce_the_micro_headroom_to_twenty():
    """3 ES consume 30 of the 50 micro-equivalents; 20 MES is what is left, not 50.

    This is the whole reason the ceiling is netted against the open book. A per-symbol cap
    read in isolation hands the full micro column to every symbol in turn, so a book of
    3 ES + 50 MES reads as compliant at 80 micro-equivalents - 1.6x the permitted size, on
    the same $2,000 of room.
    """
    acct = account()
    acct.open_contracts = {"ES": 3}
    assert acct.open_equivalents == pytest.approx(30.0)
    assert acct.max_contracts_for("MES") == 20
    assert acct.max_contracts_for("ES") == 2
    # And the sizer honours it, not just the account.
    assert decide("MES", acct, 0.25).contracts == 20


def test_a_short_position_consumes_the_allowance_too():
    """Sign is irrelevant to a position limit; three short ES cost the same thirty units."""
    acct = account()
    acct.open_contracts = {"ES": -3}
    assert acct.max_contracts_for("MES") == 20


def test_a_full_book_leaves_no_headroom_for_anything():
    acct = account()
    acct.open_contracts = {"MES": 50}
    assert acct.max_contracts_for("MES") == 0
    assert acct.max_contracts_for("ES") == 0
    assert decide("ES", acct, 2.0).contracts == 0


def test_an_overfilled_book_does_not_produce_negative_headroom():
    """A book already past the ceiling (it should not happen) clamps at zero, not below."""
    acct = account()
    acct.open_contracts = {"ES": 20}          # 200 equivalents against an allowance of 50
    assert acct.max_contracts_for("MES") == 0
    assert acct.max_contracts_for("ES") == 0


def test_a_flat_account_is_the_default_and_costs_nothing():
    """`open_contracts` defaults to empty, so nothing that ignores it changes behaviour."""
    acct = account()
    assert acct.open_contracts == {}
    assert acct.open_equivalents == 0.0
    assert acct.max_contracts_for("ES") == PUBLISHED_50K[0]


# ======================================================================================
# FAIL CLOSED
# ======================================================================================

def test_an_unlisted_root_is_refused_rather_than_defaulted():
    """A root Topstep does not permit gets zero, never a permissive fallback.

    Zero and not None: `enforce` reads None as "this firm sets no ceiling", so a None here
    would be the most expensive possible way to say "I do not know this product".
    """
    acct = account()
    for unknown in ("BTC", "ZN", "6E", "", "NOT_A_ROOT"):
        assert acct.max_contracts_for(unknown) == 0, unknown
    assert acct.max_contracts_for("BTC") is not None


def test_an_unlisted_root_is_refused_through_the_sizer_too():
    btc = InstrumentSpec("BTC", AssetClass.FUTURE, multiplier=5.0, tick=5.0, exchange="CME")
    ctx = sz.SizeContext(spec=btc, prop_account=account(), stop_distance=25.0,
                         price=90_000.0, requested=1_000_000.0)
    d = sz.PropFirmSizer().size(ctx)
    assert d.available and d.contracts == 0 and d.binding is sz.Binding.PROP_FIRM


def test_the_symbol_lookup_is_case_insensitive():
    """`ctx.spec.symbol` is whatever the caller wrote; a lowercase root is still an ES."""
    assert account().max_contracts_for("es") == PUBLISHED_50K[0]
    assert account().max_contracts_for("mes") == PUBLISHED_50K[1]


def test_an_equivalence_profile_refuses_a_symbol_missing_from_its_table():
    """Equivalence in force + no published ratio for the symbol = refuse, at the profile.

    Separate from the permitted-products check because the two fail for different reasons: a
    firm may publish an open universe (`permitted_products=()`) and still state the ratio for
    only part of it, and a contract whose share of the allowance is unknown cannot be sized
    at all. `contract_units` returns 1.0 there, which is the flattering direction.
    """
    p = PropFirmProfile(name="OPEN_UNIVERSE", starting_balance=50_000.0,
                        max_total_contracts=50,
                        max_contracts_per_symbol={"MES": 50, "ES": 5},
                        contract_equivalence=True)
    assert p.permits("CL"), "no product list, so the universe is open"
    assert p.contract_units("CL") == 1.0, "and contract_units still guesses 1.0"
    assert p.max_contracts_for("CL") == 0, "but the ceiling refuses rather than using it"
    assert p.max_contracts_for("ES") == 5


def test_a_profile_with_no_ceiling_at_all_reports_none():
    """None means "this firm sets no ceiling" and must stay reachable.

    Collapsing it into 0 would cap a firm that publishes no position limit at nothing, which
    is a different bug in the other direction.
    """
    p = PropFirmProfile(name="NO_CAP", starting_balance=50_000.0)
    assert p.max_contracts_for("ES") is None


def test_a_non_equivalence_profile_still_reads_its_per_symbol_column_as_contracts():
    """The default (`contract_equivalence=False`) is unchanged: caps are raw contracts.

    Every profile that has not opted in must behave exactly as it did, or this fix has
    quietly re-scaled some other firm's rulebook.
    """
    p = PropFirmProfile(name="RAW", starting_balance=50_000.0, max_total_contracts=10,
                        max_contracts_per_symbol={"ES": 3})
    assert p.max_contracts_for("ES") == 3
    assert p.max_contracts_for("CL") == 10, "no per-symbol entry, so the total cap applies"
    assert p.max_contracts_for("CL", held_equivalents=4.0) == 6


# ======================================================================================
# PATHOLOGICAL INPUTS
# ======================================================================================

def test_a_one_tick_stop_with_a_million_contract_request_is_clamped_to_five():
    """The worst case in the report: the smallest legal stop and an absurd ask."""
    tick = spec("ES").tick
    assert tick == 0.25
    d = decide("ES", account(), tick, sizer=sz.SignalSizer(), requested=1_000_000.0)
    assert d.available and d.contracts == 5 and d.binding is sz.Binding.PROP_FIRM
    assert d.signal == 1_000_000, "the ask is recorded in full; only the answer is clamped"


@pytest.mark.parametrize("bad", [0.0, -1.0, -0.25, math.nan, math.inf, -math.inf])
def test_a_nonsense_stop_is_refused_at_the_context_boundary(bad):
    """Zero, negative, NaN and infinite stops never reach a sizer: the context rejects them.

    Refusing at construction rather than inside `enforce` is what makes this safe - there is
    no path on which a NaN stop becomes `budget / nan` and then an integer nobody questions.
    """
    with pytest.raises(ValueError):
        sz.SizeContext(spec=spec("ES"), prop_account=account(), stop_distance=bad,
                       price=6_000.0, requested=10.0)


def test_a_negative_request_is_refused():
    with pytest.raises(ValueError):
        sz.SizeContext(spec=spec("ES"), prop_account=account(), stop_distance=1.0,
                       requested=-5.0)


@pytest.mark.parametrize("sizer", [
    sz.SignalSizer(), sz.PropFirmSizer(), sz.PropFirmSizer(fraction=1.0),
    sz.FixedRiskSizer(risk_dollars=1_000_000.0), sz.ATRSizer(),
], ids=["signal", "prop_firm", "prop_firm_full", "fixed_risk", "atr"])
def test_no_sizer_can_get_past_the_ceiling(sizer):
    """The ceiling is enforced in `enforce`, so it must hold for every sizer, not one.

    A cap that lives in one sizer is a cap the next sizer does not have - which is the
    module's stated reason for `Sizer.size` being `@final`, applied to the newest limit.
    """
    ctx = sz.SizeContext(spec=spec("ES"), prop_account=account(), stop_distance=0.25,
                         price=6_000.0, equity=100_000_000.0, atr=0.5, volatility=0.01,
                         requested=1_000_000.0, confidence=1.0)
    d = sizer.size(ctx)
    assert d.available, d.reasons
    assert d.contracts <= 5, f"{sizer.name} produced {d.contracts} ES"


def test_a_huge_profit_does_not_lift_the_ceiling_above_the_published_table():
    """The Combine has no scaling ladder, so profit must not move the cap. It moves the room.

    Worth pinning because `max_contracts_for` reads `contracts_allowed_at(profit)`, and a
    ladder misconfigured against the equivalence unit would show up here first.
    """
    rich = account(profit=100_000.0)
    assert rich.distance_to_mll > 2_000.0
    assert rich.max_contracts_for("ES") == PUBLISHED_50K[0]
    assert decide("ES", rich, 0.25).contracts == PUBLISHED_50K[0]


# ======================================================================================
# TYPES, BINDINGS AND THE SURFACE THAT STAYED
# ======================================================================================

@pytest.mark.parametrize("symbol", MINIS + MICROS)
def test_the_answer_is_an_int_and_not_a_float_that_prints_like_one(symbol):
    """`contracts` is a count. A float count reaches an order router as a float.

    `type(...) is int` rather than `isinstance`, because `bool` and `numpy.int64` both pass
    an isinstance check and neither is what an order quantity should be - `numpy` is imported
    by the sizing module and a `np.floor` slipping into the funnel is a live risk.
    """
    acct = account()
    assert type(acct.max_contracts_for(symbol)) is int
    d = decide(symbol, acct, 0.25)
    assert type(d.contracts) is int
    assert type(d.signal) is int
    assert type(tw.max_contracts(acct, 12.5, symbol=symbol)) is int


@pytest.mark.parametrize("stop", CEILING_BINDS)
def test_the_binding_names_the_prop_firm_when_the_prop_firm_bound(stop):
    """A decision that under-reports its binding cannot be audited from its log line.

    Under the defect this said `strategy_signal` at every one of these stops - the sizer's
    own arithmetic landed below a cap that was ten times too large, so nothing above it ever
    registered as binding and the log said the strategy had chosen the size.

    Only the stops where the ceiling STRICTLY binds are listed. At a 10-point stop the
    quarter-of-the-room budget is two contracts and the strategy really is what bound; a
    test that demanded PROP_FIRM there would be demanding a false attribution in the other
    direction. `test_the_binding_names_the_budget_when_the_budget_bound` covers those.
    """
    d = decide("ES", account(), stop)
    assert d.binding is sz.Binding.PROP_FIRM
    assert "LIMIT_PROP_FIRM" in d.codes
    assert any("ES" in r for r in d.reasons), "the reason must name the unit it capped in"


@pytest.mark.parametrize("stop", BUDGET_BINDS)
def test_the_binding_names_the_budget_when_the_budget_bound(stop):
    """The other half: a wide stop is budget-bound below five, and must say so.

    0.25 x $2,000 is $500, which at a 10-point ES stop ($500 a contract) is one and at four
    points ($200) is two. Both are under the five-contract ceiling, so the ceiling did not
    bind and must not be credited.
    """
    d = decide("ES", account(), stop)
    assert d.contracts < PUBLISHED_50K[0]
    assert d.binding is sz.Binding.STRATEGY_SIGNAL
    assert "LIMIT_PROP_FIRM" not in d.codes


def test_a_tie_between_the_budget_and_the_ceiling_credits_the_ceiling():
    """At a two-point ES stop both say five, and `enforce` credits the HIGHER level.

    Documented behaviour ("crediting upward on a tie is deliberate"), and worth a test of
    its own because it is the exact stop at which the original defect looked correct: 5 was
    the right number for the wrong reason, and the binding said `strategy_signal`.
    """
    d = decide("ES", account(), 2.0)
    assert d.contracts == PUBLISHED_50K[0]
    assert d.signal == PUBLISHED_50K[0]
    assert d.binding is sz.Binding.PROP_FIRM


def test_the_binding_still_names_a_lower_level_when_a_lower_level_bound():
    """The ceiling must not swallow the hierarchy: a tighter venue cap still reports VENUE."""
    ctx = sz.SizeContext(spec=spec("ES"), prop_account=account(), stop_distance=0.25,
                         price=6_000.0, requested=1_000_000.0,
                         limits=sz.SizeLimits(venue_max_contracts=2))
    d = sz.SignalSizer().size(ctx)
    assert d.contracts == 2 and d.binding is sz.Binding.VENUE


def test_contracts_allowed_is_untouched_and_still_says_micro_equivalents():
    """Backwards compatibility, deliberately: the CLI and the twin display this number.

    It is kept in the firm's own unit and its docstring has to keep saying so, because the
    whole defect was one caller reading it as something else.
    """
    acct = account()
    assert acct.contracts_allowed == PUBLISHED_50K[1]
    doc = (ts.TopstepAccount.contracts_allowed.__doc__ or "").upper()
    assert "MICRO-EQUIVALENT" in doc
    assert "NOT A POSITION SIZE" in doc


def test_the_twin_and_the_sizer_agree_once_both_are_told_the_symbol():
    """`twin.max_contracts` and `PropFirmSizer` are two implementations of one rule.

    They were pinned against each other before this change and must stay pinned after it, or
    the twin's liquidation estimates are computed at a size the sizer would never place.
    """
    acct = account()
    for symbol in MINIS + MICROS:
        mult = spec(symbol).multiplier
        for stop in STOPS:
            rpc = stop * mult
            assert decide(symbol, acct, stop).contracts == tw.max_contracts(
                acct, rpc, symbol=symbol), f"{symbol} at a {stop} stop"


def test_the_twin_without_a_symbol_still_answers_in_micro_equivalents():
    """The documented back-compatible path, pinned so it cannot quietly become per-symbol.

    `max_contracts(a, 1.0)` is "how many micro-equivalents of room", which is what the
    account reports about itself. It is not a safe default for a mini and the docstring says
    so; this test exists to make the two readings visibly different, not to bless one.
    """
    acct = account()
    assert tw.max_contracts(acct, 1.0) == PUBLISHED_50K[1]
    assert tw.max_contracts(acct, 1.0, symbol="ES") == PUBLISHED_50K[0]
    assert tw.max_contracts(acct, 1.0, symbol="BTC") == 0


def test_core_asks_for_the_ceiling_without_importing_markets():
    """The layering is the point of the design, so it is asserted rather than assumed.

    `MllAccount` must name `max_contracts_for`, or the contract between the two layers is
    folklore; and `core.sizing` must still not mention `quant_brain.markets`, or the
    equivalence has crossed the boundary as a table instead of as an answer.
    """
    assert "max_contracts_for" in sz.MllAccount.__annotations__ or hasattr(
        sz.MllAccount, "max_contracts_for")
    source = inspect.getsource(sz)
    assert "import quant_brain.markets" not in source
    assert "from quant_brain.markets" not in source


def test_a_topstep_account_satisfies_the_protocol_structurally():
    """Nothing declares the relationship, so the only thing keeping it true is a test."""
    acct = account()
    for member in ("distance_to_mll", "contracts_allowed", "max_contracts_for"):
        assert hasattr(acct, member), member
    assert callable(acct.max_contracts_for)
