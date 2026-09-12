"""scripts/paper_trade.py: order sizing, the no-trade band, the margin ceiling and the clock gate.

The point of these is the I-1 equivalence claim: `plan_orders` must produce the same order list
`algorithms/s1_momo/main.py:submit_targets` produces from the same targets, holdings and prices,
because that equivalence is what makes the backtest's 24.4% a statement about the deployed path.
`scripts/compare_orders.py` checks it on the champion's real sample; these check the arithmetic
that makes it true, in a second and without LEAN.
"""
from __future__ import annotations

import datetime as dt

import paper_trade as pt
import pytest


# --------------------------------------------------------------------------- the no-trade band
def test_band_is_a_fraction_of_equity_not_a_constant():
    """The 2026-09-09 defect: a flat $200 band sent 9,196 orders against the backtest's 4,653."""
    assert pt.MIN_ORDER_VALUE == 0.01, "band must track s1_momo's min_order_value (1% of equity)"
    plan = pt.plan_orders({"SPY": 0.5}, {"SPY": 495}, {"SPY": 100.0}, 100_000.0)
    assert plan == [], "a $500 drift is below the $1,000 band on a $100k account"


def test_band_floor_only_binds_on_a_small_account():
    """MIN_NOTIONAL is a floor under the fraction, so it must not change a $100k decision."""
    # $100k account: 1% = $1,000 dominates the $200 floor.
    assert pt.plan_orders({"SPY": 0.5}, {"SPY": 493}, {"SPY": 100.0}, 100_000.0) == []
    # $10k account: 1% = $100, so the $200 floor binds and a $700 order still goes.
    plan = pt.plan_orders({"SPY": 0.5}, {"SPY": 43}, {"SPY": 100.0}, 10_000.0)
    assert [(s, d) for s, d, *_ in plan] == [("SPY", 7)]
    # ...but a $100 order does not.
    assert pt.plan_orders({"SPY": 0.5}, {"SPY": 49}, {"SPY": 100.0}, 10_000.0) == []


def test_order_crossing_the_band_is_sent_whole_not_trimmed():
    plan = pt.plan_orders({"SPY": 0.5}, {}, {"SPY": 100.0}, 100_000.0)
    assert [(s, d, tgt, cur) for s, d, _, tgt, cur in plan] == [("SPY", 500, 500, 0)]


# --------------------------------------------------------------------------- share arithmetic
@pytest.mark.parametrize("weight, price, expected", [
    (0.5, 100.0, 500),      # exact
    (0.5, 300.0, 166),      # floors down, never up: 166.67 -> 166
    (-0.5, 300.0, -166),    # a short floors toward zero too, not away from it
    (0.0, 100.0, 0),
    (1.0, 100_000.0, 1),
    (0.000001, 100.0, 0),   # a weight too small to buy one share is not an order
])
def test_target_shares_truncate_toward_zero(weight, price, expected):
    """`int(w*equity/px)` in LEAN truncates toward zero; the runner's copysign(floor(abs))
    must agree on the short side, or the two order lists diverge on every short."""
    plan = pt.plan_orders({"SPY": weight}, {}, {"SPY": price}, 100_000.0)
    got = plan[0][3] if plan else 0
    assert got == expected
    lean = 0.0 if price <= 0 else int(weight * 100_000.0 / price)
    assert got == lean, "runner and s1_momo must agree share-for-share"


def test_no_price_is_reported_not_silently_dropped():
    plan = pt.plan_orders({"SPY": 0.5}, {"XYZ": 10}, {"SPY": 100.0}, 100_000.0)
    stuck = [p for p in plan if p[1] is None]
    assert [(s, cur) for s, _, _, _, cur in stuck] == [("XYZ", 10)]


def test_zero_or_negative_price_is_never_sized():
    plan = pt.plan_orders({"SPY": 0.5}, {}, {"SPY": 0.0}, 100_000.0)
    assert plan == [("SPY", None, 0.0, None, 0)]


def test_held_name_dropped_from_the_universe_gets_a_zero_target():
    """S-18 retired the 3x proxies and left 3,227 TQQQ in the account. The caller now feeds a
    zero target for held-but-untargeted names; plan_orders must turn that into a full sale."""
    plan = pt.plan_orders({"SPY": 1.0}, {"TQQQ": 3227}, {"SPY": 100.0, "TQQQ": 80.0}, 100_000.0)
    assert ("TQQQ", -3227) in [(s, d) for s, d, *_ in plan]


def test_a_small_leftover_below_the_band_is_deliberately_not_sold():
    """Documents a real asymmetry with the intraday sleeve, which always allows an exit.

    The daily runner has no `or target == 0` escape because `s1_momo.submit_targets` has none
    either: adding one here would make the runner place orders LEAN never places and break the
    compare_orders equivalence. If this test ever fails, the backtest changed too."""
    plan = pt.plan_orders({}, {"SPY": 5}, {"SPY": 100.0}, 100_000.0)
    assert plan == [], "$500 leftover stays; matching LEAN beats tidiness"


def test_sells_and_buys_are_both_planned_and_prices_carried_through():
    plan = pt.plan_orders({"SPY": 0.3, "TLT": 0.2}, {"SPY": 600, "GLD": 100},
                          {"SPY": 100.0, "TLT": 50.0, "GLD": 200.0}, 100_000.0)
    by_sym = {s: (d, px, tgt, cur) for s, d, px, tgt, cur in plan}
    assert by_sym["SPY"] == (-300, 100.0, 300, 600)
    assert by_sym["TLT"] == (400, 50.0, 400, 0)
    # A held name absent from the target dict is sized to zero, not ignored: the union of
    # targets and positions is what gets iterated. This is the S-18/TQQQ fix generalised.
    assert by_sym["GLD"] == (-100, 200.0, 0, 100)


# --------------------------------------------------------------------------- margin ceiling
class _SigWithTable:
    MARGIN_REQ = {"UPRO": 0.75, "TMF": 0.75}
    BASE_MARGIN_REQ = 0.5


class _SigNoTable:
    pass


def test_margin_uses_the_signals_own_table():
    used = pt.margin_used({"UPRO": 0.5, "SPY": 0.5}, _SigWithTable)
    assert used == pytest.approx(0.5 * 0.75 + 0.5 * 0.5)


def test_margin_falls_back_to_100_percent_when_nothing_is_known():
    """The unsafe direction is *under*-stating margin, so no table means Reg-T is not assumed."""
    assert pt.margin_used({"SPY": 0.5, "QQQ": 0.5}, _SigNoTable) == pytest.approx(1.0)


def test_margin_counts_shorts_gross():
    assert pt.margin_used({"SPY": 0.5, "SH": -0.5}, _SigWithTable) == pytest.approx(0.5)


def test_print_plan_aborts_above_the_margin_ceiling(capsys):
    with pytest.raises(SystemExit) as e:
        pt.print_plan([], 100_000.0, {"SPY": 1.5, "QQQ": 1.5}, _SigNoTable)
    assert "No orders sent" in str(e.value)


def test_print_plan_allows_a_book_at_the_ceiling():
    pt.print_plan([], 100_000.0, {"SPY": 0.5, "QQQ": 0.5}, _SigNoTable)   # exactly 1.0x, no raise
    assert pt.MAX_MARGIN_USED == 1.0


# --------------------------------------------------------------------------- MOO clock gate
@pytest.mark.parametrize("when, ok", [
    (dt.datetime(2026, 9, 14, 4, 0), True),      # Monday, first accepted minute
    (dt.datetime(2026, 9, 14, 9, 28), True),     # last accepted minute
    (dt.datetime(2026, 9, 14, 9, 29), False),    # IBKR rejects tif=OPG from here
    (dt.datetime(2026, 9, 14, 3, 59), False),
    (dt.datetime(2026, 9, 14, 15, 45), False),   # the currently-scheduled slot
    (dt.datetime(2026, 9, 12, 5, 0), False),     # Saturday
    (dt.datetime(2026, 9, 13, 5, 0), False),     # Sunday
])
def test_moo_window(when, ok):
    assert pt.moo_window_ok(when) is ok


def test_moo_window_matches_the_documented_constant():
    assert pt.MOO_WINDOW_ET == (dt.time(4, 0), dt.time(9, 28))


# --------------------------------------------------------------------------- order construction
def test_build_order_maps_each_type_to_what_ibkr_expects():
    mkt = pt.build_order("MKT", "BUY", 10)
    assert (mkt.orderType, mkt.action, mkt.totalQuantity) == ("MKT", "BUY", 10)
    moc = pt.build_order("MOC", "SELL", 7)
    assert (moc.orderType, moc.tif, moc.action, moc.totalQuantity) == ("MOC", "DAY", "SELL", 7)
    moo = pt.build_order("MOO", "BUY", 3)
    # There is no "MOO" orderType at IBKR: an opening-auction order is MKT + tif OPG.
    assert (moo.orderType, moo.tif) == ("MKT", "OPG")


def test_build_order_refuses_an_unknown_type():
    with pytest.raises(ValueError):
        pt.build_order("LMT", "BUY", 1)


# --------------------------------------------------------------------------- signal adapter
def test_call_signal_passes_only_the_arguments_the_signal_declares():
    seen = {}

    def target_weights(closes, as_of=None, params=None, state=None):
        seen.update(as_of=as_of, params=params, state=state)
        return {"SPY": 1.0}

    sig = type("S", (), {"target_weights": staticmethod(target_weights), "PARAMS": {"k": 1}})
    state = {"signal_state": {"prev": 3}}
    w, _diag = pt.call_signal(sig, closes=None, as_of="2026-09-11", state=state)
    assert w == {"SPY": 1.0}
    assert seen == {"as_of": "2026-09-11", "params": {"k": 1}, "state": {"prev": 3}}


def test_call_signal_tolerates_a_bare_signature():
    sig = type("S", (), {"target_weights": staticmethod(lambda closes: {"SPY": 0.4})})
    w, _ = pt.call_signal(sig, closes=None, as_of="2026-09-11", state={})
    assert w == {"SPY": 0.4}


def test_call_signal_persists_returned_state_and_drops_zero_weights():
    def target_weights(closes, state=None):
        return {"SPY": 0.5, "QQQ": 0.0}, {"state": {"n": 2}, "reason": "risk on"}

    sig = type("S", (), {"target_weights": staticmethod(target_weights)})
    state = {}
    w, diag = pt.call_signal(sig, closes=None, as_of=None, state=state)
    assert w == {"SPY": 0.5}, "a zero weight is not a position and must not become an order"
    assert state["signal_state"] == {"n": 2}
    assert diag["reason"] == "risk on"


def test_demo_signal_is_loadable_and_buys_spy():
    sig = pt.load_signal("demo")
    assert sig.UNIVERSE == ["SPY"]
    assert sig.target_weights(None) == {"SPY": 1.0}


def test_equity_curve_appends_one_point_per_new_session():
    """Mirrors main()'s bookkeeping: one equity point per trading day, never two for a rerun."""
    state = {"equity_curve": [100.0], "as_of": "2026-09-10"}
    for as_of, expected in (("2026-09-10", 1), ("2026-09-11", 2), ("2026-09-11", 2)):
        curve = [float(x) for x in state.get("equity_curve", [])]
        if not curve or str(state.get("as_of")) != as_of:
            curve.append(101.0)
        state["equity_curve"], state["as_of"] = curve, as_of
        assert len(state["equity_curve"]) == expected
