"""D-10: the daily sleeve's guard on a target it cannot express as whole shares.

`signals.unsizable_targets` is the one definition of the boundary. Three callers reach it -
`algorithms/s1_momo/main.py:submit_targets` (LEAN), `scripts/sweep_s19.py:simulate` (the offline
book every S-row is priced in) and `scripts/paper_trade.py:plan_orders` (the deployed runner,
which receives it from the loaded signal module rather than transcribing it, because a fourth
transcription is exactly the defect S-45 is open about).

Not `runner`-marked: nothing here is executed by the 09:25 intraday launch.

What a future edit could break, in descending order of cost:

1. **Inertness.** The champion is deployed. The guard reads, it does not size, and any edit that
   lets it reach an order changes a book the owner approved at `OrderListHash
   a6d6224ce9c70091e5bfa8e96f046bf3`. The purity tests below are the cheap standing proof of
   that; the expensive one is the LEAN control `sweep_d10.py` clause 6 reads.
2. **The boundary itself.** One whole share, from the `int()`/`floor()` truncation the three
   sizing rules share. Off-by-one at 1.0 exactly is the mistake to pin: 1.0 shares IS sizable.
3. **The second reason.** `no_price` is not the same defect as `under_one_share` and D-10's item
   text names only the first. It is the one with an asymmetric consequence - an unpriced name
   that is already HELD keeps its position, because the no-trade band prices the liquidation at
   a cent a share - so a refactor that collapses the two reasons loses the worse of them.
4. **The band is not a reason.** Banding a small rebalancing delta is S-13/S-32 working as
   designed. A guard that fires on it would cry wolf on ~3,000 of the champion's orders.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "algorithms" / "s1_momo"))
sys.path.insert(0, str(REPO / "scripts"))

import signals as sig  # noqa: E402

unsizable = sig.unsizable_targets


# --------------------------------------------------------------------------- the boundary
def test_a_sizable_target_produces_no_hit():
    """The normal case, and the one that must stay silent: 500 shares of a $100 name."""
    assert unsizable({"SPY": 0.5}, {"SPY": 100.0}, 100_000.0) == []


def test_exactly_one_share_is_sizable():
    """1.0 is the boundary and it is on the sizable side - `int(1.0)` is 1, a real position."""
    assert unsizable({"SPY": 0.001}, {"SPY": 100.0}, 100_000.0) == []


def test_just_under_one_share_is_a_hit():
    """$99.99 of a $100 name buys nothing, and before D-10 nothing said so."""
    hits = unsizable({"SPY": 0.0009999}, {"SPY": 100.0}, 100_000.0)
    assert [h["reason"] for h in hits] == ["under_one_share"]
    assert hits[0]["ticker"] == "SPY"
    assert hits[0]["shares"] == pytest.approx(0.9999)
    assert hits[0]["notional"] == pytest.approx(99.99)


def test_the_hit_carries_what_a_reader_needs_to_act():
    """Weight, price, allocation, shares and the position that is stuck - not just a name."""
    hit, = unsizable({"LLY": 0.01}, {"LLY": 2_000.0}, 100_000.0, {"LLY": 3})
    assert hit == {"ticker": "LLY", "reason": "under_one_share", "weight": 0.01,
                   "price": 2_000.0, "notional": 1_000.0, "shares": 0.5, "held": 3.0}


def test_a_shorts_weight_is_measured_on_its_magnitude():
    """`plan_orders` sizes a negative weight with copysign, so the boundary is |w|."""
    assert unsizable({"SPY": -0.5}, {"SPY": 100.0}, 100_000.0) == []
    assert [h["reason"] for h in unsizable({"SPY": -0.0001}, {"SPY": 100.0}, 100_000.0)] \
        == ["under_one_share"]


# --------------------------------------------------------------------------- the second reason
@pytest.mark.parametrize("price", [0.0, -1.0, float("nan"), float("inf")])
def test_an_unusable_price_is_no_price_not_under_one_share(price):
    """Distinct reason, because its consequence is distinct: a HELD position is kept, not closed.

    `submit_targets` forces the target to zero and the band then scores the liquidation at
    `max(price, 0.01)`, so closing N shares would need `0.01 * N >= 0.01 * equity`, i.e. a share
    count at least as large as the account's dollar equity. The stale position is carried.
    """
    hit, = unsizable({"SPY": 0.5}, {"SPY": price}, 100_000.0, {"SPY": 500})
    assert hit["reason"] == "no_price"
    assert hit["held"] == 500.0


def test_a_missing_price_is_the_same_as_an_unusable_one():
    """A ranked name absent from the price dict is the live shape of this: no bar arrived."""
    assert [h["reason"] for h in unsizable({"SPY": 0.5}, {}, 100_000.0)] == ["no_price"]


def test_an_unpriced_name_with_no_weight_is_not_a_hit():
    """Only names the signal actually ranked. A zero weight is the sleeve declining to hold."""
    assert unsizable({"SPY": 0.0, "TLT": 0.5}, {"TLT": 100.0}, 100_000.0) == []


# --------------------------------------------------------------------------- not the band
def test_a_banded_rebalancing_delta_is_not_a_hit():
    """S-13/S-32. ~3,000 of the champion's orders are drift the band drops; none is a defect.

    The target here is 5,000 shares against 4,995 held - a $500 delta the 1%-of-equity band
    refuses. The guard must stay silent: the position exists and the signal is expressed.
    """
    assert unsizable({"SPY": 0.5}, {"SPY": 100.0}, 100_000.0) == []


# --------------------------------------------------------------------------- inertness
def test_the_guard_allocates_nothing_and_mutates_nothing():
    """Purity, checked on the inputs a caller would be horrified to have modified."""
    targets = {"SPY": 0.5, "LLY": 0.01}
    prices = {"SPY": 100.0, "LLY": 2_000.0}
    held = {"SPY": 500}
    unsizable(targets, prices, 100_000.0, held)
    assert targets == {"SPY": 0.5, "LLY": 0.01}
    assert prices == {"SPY": 100.0, "LLY": 2_000.0}
    assert held == {"SPY": 500}


def test_hits_are_ordered_by_ticker_so_a_log_diff_is_stable():
    hits = unsizable({"ZZZ": 0.01, "AAA": 0.01}, {"ZZZ": 2_000.0, "AAA": 2_000.0}, 100_000.0)
    assert [h["ticker"] for h in hits] == ["AAA", "ZZZ"]


def test_main_py_only_logs_the_guard_and_never_sizes_from_it():
    """The inertness claim, read off the deployed source.

    `submit_targets` must call the guard AFTER `deltas` is complete and must not assign to
    `deltas` anywhere in the loop that consumes the result. This is the standing version of the
    LEAN control: `sweep_d10.py` clause 6 proves the hash, this proves the shape in a second.
    """
    src = (REPO / "algorithms" / "s1_momo" / "main.py").read_text(encoding="utf-8")
    body = src.split("def submit_targets", 1)[1].split("\n    def ", 1)[0]
    call = body.index("sig.unsizable_targets(")
    assert body.rindex("deltas[symbol] =") < call, \
        "the guard must run after the order plan is fixed"
    # Between the guard and the send there may be reads of `deltas` (the SIZING log line) but
    # no write of any kind, which is what makes the block provably unable to move an order.
    between = body[call:body.index("for symbol in sorted(deltas")]
    assert "deltas[" not in between and "deltas =" not in between, \
        "nothing between the guard and the send may write the order plan"


# --------------------------------------------------------------------------- the three callers
def test_the_offline_book_takes_the_guard_as_an_out_parameter():
    """`sweep_s19.simulate` must default it off, so every pre-D-10 row stays reproducible."""
    import inspect

    sweep_s19 = pytest.importorskip("sweep_s19")
    sig_ = inspect.signature(sweep_s19.simulate)
    assert sig_.parameters["unsizable"].default is None


def test_the_runner_receives_the_predicate_rather_than_transcribing_it():
    """S-45's lesson. `paper_trade` is generic over signals, so it must not own a second copy."""
    import inspect

    pt = pytest.importorskip("paper_trade")
    src = inspect.getsource(pt.plan_orders)
    assert "unsizable_fn(" in src, "the predicate comes from the caller"
    assert "< 1" not in src and "MIN_WHOLE_SHARES" not in src, \
        "plan_orders must not reimplement the boundary"
    assert inspect.signature(pt.plan_orders).parameters["unsizable"].default is None


def test_the_runner_collects_nothing_when_the_signal_does_not_export_the_predicate():
    """A non-s1 signal module must not crash the deployed runner."""
    pt = pytest.importorskip("paper_trade")
    out = []
    plan = pt.plan_orders({"SPY": 0.5}, {}, {"SPY": 100.0}, 100_000.0,
                          unsizable=out, unsizable_fn=None)
    assert out == []
    assert plan == [("SPY", 500, 100.0, 500, 0)]


def test_the_runner_plan_is_bit_identical_with_and_without_the_collector():
    """The I-1 equivalence gate must not be able to tell the guard is there."""
    pt = pytest.importorskip("paper_trade")
    args = ({"SPY": 0.5, "LLY": 0.01}, {"SPY": 200}, {"SPY": 100.0, "LLY": 2_000.0}, 100_000.0)
    out = []
    assert pt.plan_orders(*args) == pt.plan_orders(*args, unsizable=out,
                                                   unsizable_fn=unsizable)
    assert [h["ticker"] for h in out] == ["LLY"]
