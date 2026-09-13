"""Bracket verification: only an acknowledged, correctly-sided, correctly-priced, fully-sized
stop counts. Everything else is a specific reason and UNPROTECTED."""
from __future__ import annotations

import pytest

from quant_brain.core.execution import Side
from quant_brain.core.governor import AccountView, Governor, Limits, Reason
from quant_brain.core.protection import (
    ProtectionMonitor,
    ProtectionState,
    WorkingOrder,
    verify,
)


def stop(qty=1.0, side=Side.SELL, price: float | None = 5000.0, acked=True, symbol="MES",
         oid="s1", kind="stop"):
    return WorkingOrder(order_id=oid, symbol=symbol, side=side, quantity=qty, kind=kind,
                        stop_price=price, acknowledged=acked)


def test_flat_is_flat_regardless_of_orders():
    v = verify(symbol="MES", position=0, avg_price=None, working=[stop()])
    assert v.state is ProtectionState.FLAT and v.safe


def test_long_with_acked_sell_stop_below_entry_is_protected():
    v = verify(symbol="MES", position=2, avg_price=5010.0, working=[stop(2, price=5000.0)])
    assert v.state is ProtectionState.PROTECTED and v.covering == ("s1",) and v.naked_qty == 0


def test_short_with_acked_buy_stop_above_entry_is_protected():
    v = verify(symbol="MES", position=-1, avg_price=5000.0,
               working=[stop(1, side=Side.BUY, price=5010.0)])
    assert v.state is ProtectionState.PROTECTED


def test_no_stop_at_all_is_unprotected_with_the_reason():
    v = verify(symbol="MES", position=1, avg_price=5000.0, working=[])
    assert v.state is ProtectionState.UNPROTECTED and not v.safe
    assert "no stop-type order" in v.reasons[0] and v.naked_qty == 1


def test_a_stop_the_process_sent_but_the_venue_has_not_acked_is_pending_not_protected():
    v = verify(symbol="MES", position=1, avg_price=5010.0, working=[stop(1, acked=False)])
    assert v.state is ProtectionState.PENDING and not v.safe
    assert "not acknowledged" in v.reasons[0]


def test_wrong_side_stop_does_not_count():
    # A BUY stop above a long is an add, not a stop.
    v = verify(symbol="MES", position=1, avg_price=5000.0,
               working=[stop(1, side=Side.BUY, price=5020.0)])
    assert v.state is ProtectionState.UNPROTECTED and "does not close a long" in v.reasons[0]


def test_stop_on_the_wrong_side_of_entry_does_not_count():
    v = verify(symbol="MES", position=1, avg_price=5000.0, working=[stop(1, price=5020.0)])
    assert v.state is ProtectionState.UNPROTECTED
    assert "not on the protective side" in v.reasons[0]
    v = verify(symbol="MES", position=-1, avg_price=5000.0,
               working=[stop(1, side=Side.BUY, price=4990.0)])
    assert v.state is ProtectionState.UNPROTECTED


def test_stop_at_entry_within_a_tick_does_not_count():
    v = verify(symbol="MES", position=1, avg_price=5000.0, working=[stop(1, price=5000.0)],
               tick=0.25)
    assert v.state is ProtectionState.UNPROTECTED


def test_undersized_stop_is_unprotected_for_the_uncovered_part():
    v = verify(symbol="MES", position=3, avg_price=5010.0, working=[stop(2, price=5000.0)])
    assert v.state is ProtectionState.UNPROTECTED
    assert v.covered_qty == 2 and v.naked_qty == 1
    assert any("1 is naked" in r for r in v.reasons)


def test_two_stops_summing_to_the_position_protect_it():
    v = verify(symbol="MES", position=3, avg_price=5010.0,
               working=[stop(2, price=5000.0, oid="a"), stop(1, price=4995.0, oid="b")])
    assert v.state is ProtectionState.PROTECTED and set(v.covering) == {"a", "b"}


def test_stop_on_another_symbol_does_not_protect_this_one():
    v = verify(symbol="MES", position=1, avg_price=5010.0,
               working=[stop(1, price=5000.0, symbol="MNQ")])
    assert v.state is ProtectionState.UNPROTECTED


def test_limit_order_is_not_a_stop():
    v = verify(symbol="MES", position=1, avg_price=5010.0,
               working=[stop(1, price=None, kind="limit")])
    assert v.state is ProtectionState.UNPROTECTED


def test_stop_limit_counts_as_a_stop():
    v = verify(symbol="MES", position=1, avg_price=5010.0,
               working=[stop(1, price=5000.0, kind="stop_limit")])
    assert v.state is ProtectionState.PROTECTED


def test_unknown_avg_price_still_checks_side_and_size_but_not_price():
    v = verify(symbol="MES", position=1, avg_price=None, working=[stop(1, price=9999.0)])
    assert v.state is ProtectionState.PROTECTED   # cannot judge the price; side+size+ack hold


def test_require_target_demands_an_acked_closing_limit_too():
    v = verify(symbol="MES", position=1, avg_price=5010.0, working=[stop(1, price=5000.0)],
               require_target=True)
    assert v.state is ProtectionState.UNPROTECTED and "target required" in v.reasons[-1]
    tgt = WorkingOrder("t1", "MES", Side.SELL, 1, "limit", limit_price=5030.0, acknowledged=True)
    v = verify(symbol="MES", position=1, avg_price=5010.0,
               working=[stop(1, price=5000.0), tgt], require_target=True)
    assert v.state is ProtectionState.PROTECTED


def test_partly_covered_partly_pending_is_pending_not_protected():
    v = verify(symbol="MES", position=2, avg_price=5010.0,
               working=[stop(1, price=5000.0, oid="a"), stop(1, price=5000.0, oid="b", acked=False)])
    assert v.state is ProtectionState.PENDING and v.covered_qty == 1


# ---------------------------------------------------------------------------------------
# Monitor -> fail-safe
# ---------------------------------------------------------------------------------------

def test_monitor_fires_on_first_unprotected_and_trips_the_governor():
    g = Governor(Limits(), AccountView())
    flattened: list[str] = []

    def fail_safe(symbol, verdict):
        flattened.append(symbol)
        g.trip(Reason.BRACKET_UNVERIFIED, f"{symbol}: {verdict.describe()}")

    mon = ProtectionMonitor(on_unprotected=fail_safe)
    v = verify(symbol="MES", position=1, avg_price=5000.0, working=[])
    mon.check("MES", v)
    assert flattened == ["MES"] and g.halted
    assert g.status()["tripped"][0]["reason"] == "BRACKET_UNVERIFIED"


def test_monitor_tolerates_pending_for_the_grace_then_escalates():
    fired: list[tuple[str, ProtectionState]] = []
    mon = ProtectionMonitor(on_unprotected=lambda s, v: fired.append((s, v.state)),
                            pending_grace=3)
    v = verify(symbol="MES", position=1, avg_price=5010.0, working=[stop(1, acked=False)])
    mon.check("MES", v)
    mon.check("MES", v)
    assert fired == []
    mon.check("MES", v)
    assert fired == [("MES", ProtectionState.PENDING)]


def test_monitor_pending_counter_resets_once_protected():
    fired: list = []
    mon = ProtectionMonitor(on_unprotected=lambda s, v: fired.append(s), pending_grace=2)
    pend = verify(symbol="MES", position=1, avg_price=5010.0, working=[stop(1, acked=False)])
    ok = verify(symbol="MES", position=1, avg_price=5010.0, working=[stop(1)])
    mon.check("MES", pend)
    mon.check("MES", ok)
    mon.check("MES", pend)
    assert fired == []


@pytest.mark.parametrize("position", [1, -1, 3, -7])
def test_verdict_describe_is_informative(position):
    v = verify(symbol="MES", position=position, avg_price=5000.0, working=[])
    assert "unprotected" in v.describe() and f"naked {abs(position)}" in v.describe()
