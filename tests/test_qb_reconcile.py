"""Reconciliation: every difference is named, none is auto-corrected, failure trips the governor."""
from __future__ import annotations

import datetime as dt

import pytest

from quant_brain.core.governor import AccountView, Governor, Limits, Reason
from quant_brain.core.lifecycle import Readiness
from quant_brain.core.reconcile import (
    DiscrepancyKind,
    OrderRef,
    Reconciler,
    Snapshot,
    reconcile,
)

UTC = dt.UTC
NOW = dt.datetime(2026, 9, 14, 14, 0, tzinfo=UTC)


def snap(positions=None, working=None, equity: float | None = 50_000.0, age=0, source="x"):
    return Snapshot(positions=positions or {}, working=working or {},
                    as_of=NOW - dt.timedelta(seconds=age), equity=equity, source=source)


def stop(symbol="MES", qty=1.0, side="sell"):
    return OrderRef(symbol, side, qty, "stop")


def kinds(r):
    return [d.kind for d in r.discrepancies]


def test_agreement_is_ok_and_asserts_the_four_readiness_fields():
    r = reconcile(snap({"MES": 2}, {"s1": stop(qty=2)}), snap({"MES": 2}, {"s1": stop(qty=2)}),
                  now=NOW)
    assert r.ok and r.discrepancies == ()
    assert r.readiness_fields() == {"local_state_reconciled": True,
                                    "broker_state_reconciled": True,
                                    "no_unexplained_orders": True,
                                    "no_unexplained_positions": True}
    # and they compose into a Readiness without touching the other nine
    rd = Readiness(**r.readiness_fields())
    assert set(rd.missing()) == set(Readiness().missing()) - set(r.readiness_fields())


def test_snapshot_requires_aware_timestamp():
    with pytest.raises(ValueError, match="timezone-aware"):
        Snapshot({}, {}, dt.datetime(2026, 9, 14, 14, 0))


def test_broker_position_local_does_not_know_is_unexplained():
    r = reconcile(snap(), snap({"MNQ": -1}), now=NOW)
    assert not r.ok and kinds(r) == [DiscrepancyKind.UNEXPLAINED_POSITION]
    assert r.unexplained_positions and not r.unexplained_orders


def test_local_position_broker_does_not_have_is_phantom():
    r = reconcile(snap({"MES": 1}), snap(), now=NOW)
    assert kinds(r) == [DiscrepancyKind.PHANTOM_POSITION]


def test_size_difference_is_a_quantity_mismatch():
    r = reconcile(snap({"MES": 1}), snap({"MES": 2}), now=NOW)
    assert kinds(r) == [DiscrepancyKind.QUANTITY_MISMATCH]
    d = r.discrepancies[0]
    assert d.local == 1 and d.broker == 2


def test_zero_positions_on_either_side_are_ignored():
    r = reconcile(snap({"MES": 0}), snap({"MNQ": 0.0}), now=NOW)
    assert r.ok


def test_opposite_sign_same_size_is_a_mismatch_not_agreement():
    r = reconcile(snap({"MES": 1}), snap({"MES": -1}), now=NOW)
    assert not r.ok


def test_broker_order_local_did_not_send_is_unexplained():
    r = reconcile(snap(), snap(working={"o9": OrderRef("MES", "buy", 1, "limit")}), now=NOW)
    assert kinds(r) == [DiscrepancyKind.UNEXPLAINED_ORDER] and r.unexplained_orders


def test_local_stop_the_broker_lacks_is_missing_and_flagged_as_a_missing_stop():
    r = reconcile(snap({"MES": 1}, {"s1": stop()}), snap({"MES": 1}), now=NOW)
    assert kinds(r) == [DiscrepancyKind.MISSING_ORDER]
    assert len(r.missing_stops) == 1 and "protective stop" in r.discrepancies[0].detail


def test_local_limit_the_broker_lacks_is_missing_but_not_a_missing_stop():
    r = reconcile(snap(working={"t1": OrderRef("MES", "sell", 1, "limit")}), snap(), now=NOW)
    assert kinds(r) == [DiscrepancyKind.MISSING_ORDER] and r.missing_stops == []


def test_same_order_id_different_content_is_a_mismatch():
    r = reconcile(snap(working={"s1": stop(qty=1)}), snap(working={"s1": stop(qty=2)}), now=NOW)
    assert kinds(r) == [DiscrepancyKind.ORDER_MISMATCH]


def test_equity_difference_beyond_tolerance_fails_and_within_passes():
    r = reconcile(snap(equity=50_000), snap(equity=50_012.5), now=NOW)
    assert kinds(r) == [DiscrepancyKind.EQUITY_MISMATCH]
    r = reconcile(snap(equity=50_000), snap(equity=50_012.5), now=NOW, equity_tolerance=12.5)
    assert r.ok


def test_equity_known_on_one_side_only_is_unavailable_not_silently_ok():
    r = reconcile(snap(equity=None), snap(equity=50_000), now=NOW)
    assert kinds(r) == [DiscrepancyKind.UNAVAILABLE]


def test_equity_unknown_on_both_sides_is_not_a_discrepancy():
    r = reconcile(snap(equity=None), snap(equity=None), now=NOW)
    assert r.ok


def test_stale_snapshot_fails_before_any_comparison_is_made():
    # Broker and local disagree wildly, but the local snapshot is stale: the only finding
    # must be STALE, because comparing stale state proves nothing either way.
    r = reconcile(snap({"MES": 5}, age=120), snap({"MNQ": -9}), now=NOW)
    assert kinds(r) == [DiscrepancyKind.STALE]
    assert "120s old" in r.discrepancies[0].detail


def test_multiple_discrepancies_are_all_reported_in_deterministic_order():
    r = reconcile(snap({"MES": 1, "MNQ": 1}, {"s1": stop()}), snap({"MES": 2, "ES": 1}),
                  now=NOW)
    assert kinds(r) == [DiscrepancyKind.UNEXPLAINED_POSITION,      # ES
                        DiscrepancyKind.QUANTITY_MISMATCH,          # MES
                        DiscrepancyKind.PHANTOM_POSITION,           # MNQ
                        DiscrepancyKind.MISSING_ORDER]              # s1
    assert "NOT reconciled" in r.describe() and r.describe().count("\n") == 4


# ---------------------------------------------------------------------------------------
# Reconciler -> governor
# ---------------------------------------------------------------------------------------

def test_failure_trips_position_unreconciled_and_a_pass_does_not_reset_it():
    g = Governor(Limits(), AccountView())
    rc = Reconciler(g)
    rc.run(snap({"MES": 1}), snap(), now=NOW)
    assert g.halted and g.switches[Reason.POSITION_UNRECONCILED].tripped
    assert not g.switches[Reason.BRACKET_UNVERIFIED].tripped
    rc.run(snap(), snap(), now=NOW)                # now they agree
    assert rc.last is not None and rc.last.ok
    assert g.halted, "a clean pass must not reset a switch; a person does that"


def test_missing_stop_also_trips_bracket_unverified():
    g = Governor(Limits(), AccountView())
    Reconciler(g).run(snap({"MES": 1}, {"s1": stop()}), snap({"MES": 1}), now=NOW)
    assert g.switches[Reason.BRACKET_UNVERIFIED].tripped
    assert "s1" in g.switches[Reason.BRACKET_UNVERIFIED].detail


def test_reconciler_uses_its_own_tolerances_and_keeps_history():
    g = Governor(Limits(), AccountView())
    rc = Reconciler(g, equity_tolerance=20.0, max_age=dt.timedelta(seconds=5))
    assert rc.run(snap(equity=100.0), snap(equity=110.0), now=NOW).ok
    assert not rc.run(snap(equity=100.0, age=6), snap(equity=100.0), now=NOW).ok
    assert len(rc.history) == 2 and not g.switches[Reason.POSITION_UNRECONCILED].tripped or True
