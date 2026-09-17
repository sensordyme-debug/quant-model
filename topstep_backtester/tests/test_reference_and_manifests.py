"""The independent arithmetic, and the hashes that tie a number to its inputs.

THE MOST IMPORTANT TEST IN THIS FILE
------------------------------------
``test_the_reconciliation_detects_a_disagreement``. Every other reconciliation test asserts
that two calculations agreed - which a reconciliation that always returns True would also
satisfy. This one feeds it a deliberate error and requires it to notice. Without it the
whole independent-check apparatus is decorative.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from pathlib import Path

import pytest

from topstep_backtester.manifests.manifest import (
    RunManifest,
    hash_bars,
    hash_layer_b_source,
)
from topstep_backtester.reference.arithmetic import (
    Reconciliation,
    ReferenceFill,
    reference_ledger,
)
from topstep_backtester.upstream import AggregateBarUnit, Bar, BarType

TICK = Decimal("0.25")
VALUE = Decimal("12.50")


def fills(*rows: tuple[str, int, str, str]) -> list[ReferenceFill]:
    return [
        ReferenceFill(side=side, size=size, price=Decimal(price), costs=Decimal(cost))
        for side, size, price, cost in rows
    ]


# ======================================================================================
# the arithmetic itself
# ======================================================================================


def test_a_winning_long_is_priced_from_the_tick_table() -> None:
    ledger = reference_ledger(
        fills(("BUY", 1, "5000.00", "1.90"), ("SELL", 1, "5002.00", "1.90")),
        tick_size=TICK, tick_value=VALUE,
    )
    #: 2.00 points / 0.25 = 8 ticks; 8 * $12.50 = $100.00
    assert ledger.gross_pnl == Decimal("100.00")
    assert ledger.costs == Decimal("3.80")
    assert ledger.net_pnl == Decimal("96.20")
    assert ledger.unclosed_qty == 0


def test_a_losing_long_is_negative() -> None:
    ledger = reference_ledger(
        fills(("BUY", 1, "5000.00", "1.90"), ("SELL", 1, "4998.00", "1.90")),
        tick_size=TICK, tick_value=VALUE,
    )
    assert ledger.gross_pnl == Decimal("-100.00")
    assert ledger.net_pnl == Decimal("-103.80")


def test_a_winning_short_is_positive() -> None:
    """The sign convention is where an independent reimplementation usually goes wrong."""
    ledger = reference_ledger(
        fills(("SELL", 1, "5002.00", "1.90"), ("BUY", 1, "5000.00", "1.90")),
        tick_size=TICK, tick_value=VALUE,
    )
    assert ledger.gross_pnl == Decimal("100.00")


def test_size_scales_the_result() -> None:
    ledger = reference_ledger(
        fills(("BUY", 3, "5000.00", "5.70"), ("SELL", 3, "5002.00", "5.70")),
        tick_size=TICK, tick_value=VALUE,
    )
    assert ledger.gross_pnl == Decimal("300.00")


def test_an_unclosed_position_is_reported_rather_than_assumed_flat() -> None:
    ledger = reference_ledger(
        fills(("BUY", 2, "5000.00", "3.80"), ("SELL", 1, "5002.00", "1.90")),
        tick_size=TICK, tick_value=VALUE,
    )
    assert ledger.unclosed_qty == 1
    #: one of the two contracts closed, 8 ticks, $12.50 each
    assert ledger.gross_pnl == Decimal("100.00")


def test_a_scaled_position_is_flagged_because_averaging_and_fifo_can_diverge() -> None:
    ledger = reference_ledger(
        fills(
            ("BUY", 1, "5000.00", "1.90"),
            ("BUY", 1, "5002.00", "1.90"),
            ("SELL", 2, "5004.00", "3.80"),
        ),
        tick_size=TICK, tick_value=VALUE,
    )
    assert ledger.scaled_positions_seen is True
    #: average entry 5001.00, exit 5004.00 -> 3.00 points on 2 contracts
    assert ledger.gross_pnl == Decimal("300.00")


def test_zero_tick_terms_are_refused() -> None:
    with pytest.raises(ValueError, match="must both be positive"):
        reference_ledger(fills(("BUY", 1, "5000.00", "0")), tick_size=Decimal(0),
                         tick_value=VALUE)


def test_an_unknown_side_is_refused_rather_than_guessed() -> None:
    with pytest.raises(ValueError, match="unknown fill side"):
        reference_ledger(
            [ReferenceFill(side="HOLD", size=1, price=Decimal("1"), costs=Decimal("0"))],
            tick_size=TICK, tick_value=VALUE,
        )


# ======================================================================================
# the reconciliation must be capable of failing
# ======================================================================================


def test_the_reconciliation_detects_a_disagreement() -> None:
    """Feed it an error and require it to notice. Otherwise every green tick means nothing."""
    wrong = Reconciliation(
        engine_gross=Decimal("100.00"), engine_costs=Decimal("3.80"),
        engine_net=Decimal("96.20"),
        reference_gross=Decimal("150.00"), reference_costs=Decimal("3.80"),
        reference_net=Decimal("146.20"),
        scaled_positions_seen=False, unclosed_qty=0,
    )
    assert wrong.agrees is False
    assert wrong.gross_delta == Decimal("-50.00")
    assert wrong.net_delta == Decimal("-50.00")


def test_a_single_cent_of_disagreement_is_a_disagreement() -> None:
    """No tolerance. Both sides work in Decimal on a tick grid, so there is no float error
    to absorb - a tolerance would hide exactly the bug worth finding."""
    off_by_a_penny = Reconciliation(
        engine_gross=Decimal("100.00"), engine_costs=Decimal("3.80"),
        engine_net=Decimal("96.20"),
        reference_gross=Decimal("100.01"), reference_costs=Decimal("3.80"),
        reference_net=Decimal("96.21"),
        scaled_positions_seen=False, unclosed_qty=0,
    )
    assert off_by_a_penny.agrees is False


def test_agreement_is_reported_when_it_is_real() -> None:
    same = Reconciliation(
        engine_gross=Decimal("100.00"), engine_costs=Decimal("3.80"),
        engine_net=Decimal("96.20"),
        reference_gross=Decimal("100.00"), reference_costs=Decimal("3.80"),
        reference_net=Decimal("96.20"),
        scaled_positions_seen=False, unclosed_qty=0,
    )
    assert same.agrees is True


def test_the_reference_module_shares_no_code_with_the_engine() -> None:
    """Agreement is only evidence if the two calculations are genuinely independent.

    Checked by parsing the imports rather than by searching the text: the docstring
    discusses the engine at length, and a substring match would flag its own explanation.
    """
    import ast

    path = Path(__file__).resolve().parent.parent / "reference" / "arithmetic.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    borrowed = sorted(
        name for name in imported
        if name.startswith("topstep_backtest") or name.startswith("topstep_backtester")
    )
    assert borrowed == [], (
        f"reference/arithmetic.py imports {borrowed}. It must reach neither the engine nor "
        f"the seam that re-exports it, or its agreement with the engine is a tautology."
    )
    assert imported <= {"__future__", "collections.abc", "dataclasses", "decimal"}, (
        f"unexpected dependency: {sorted(imported)}"
    )


# ======================================================================================
# manifests
# ======================================================================================


def bar(ts: int) -> Bar:
    return Bar(
        bar_type=BarType(contract_id="CON.F.US.ES.Z25", unit=AggregateBarUnit.MINUTE,
                         unit_number=1),
        ts_event=ts, ts_init=ts + 60_000_000_000,
        open=Decimal("5000.00"), high=Decimal("5000.50"),
        low=Decimal("4999.75"), close=Decimal("5000.25"), volume=100,
    )


def test_the_bar_hash_moves_when_a_bar_moves() -> None:
    base = [bar(1_700_000_000_000_000_000)]
    later = [bar(1_700_000_060_000_000_000)]
    assert hash_bars(base) != hash_bars(later)


def test_the_bar_hash_is_stable_for_identical_bars() -> None:
    ts = 1_700_000_000_000_000_000
    assert hash_bars([bar(ts)]) == hash_bars([bar(ts)])


def test_the_source_hash_is_stable_within_a_run() -> None:
    assert hash_layer_b_source() == hash_layer_b_source()


def manifest(**overrides) -> RunManifest:
    base = {
        "bars_hash": "aaaa", "bar_count": 10, "instrument": "ES", "bar_interval": "1min",
        "first_ts_event_utc": "2025-01-01T14:30:00+00:00",
        "last_ts_init_utc": "2025-01-01T14:40:00+00:00",
        "data_form": "RAW", "contract_ids": ("CON.F.US.ES.H25",),
        "spec_id": "x/1.0.0@bbbb", "spec_hash": "bbbb",
        "account_profile": {"profile_id": "A"}, "execution_profile": {"profile_id": "B"},
        "upstream_api_fingerprint": "cccc", "upstream_version": "0.4.0",
        "code_hash": "dddd",
    }
    return RunManifest(**{**base, **overrides})


def test_provenance_is_outside_the_identity_hash() -> None:
    """The Phase E defect, inverted: a path in the identity hash made the same data hash
    differently on two machines. Provenance is recorded beside identity, never inside it."""
    a = manifest(operator="alice", created_at="2026-01-01T00:00:00+00:00",
                 platform_name="Windows", notes=("one",))
    b = manifest(operator="bob", created_at="2026-06-01T00:00:00+00:00",
                 platform_name="Linux", notes=("two",))
    assert a.run_id == b.run_id


@pytest.mark.parametrize(
    "field",
    ["bars_hash", "spec_hash", "code_hash", "upstream_api_fingerprint", "upstream_version"],
)
def test_every_input_and_assumption_is_inside_the_identity_hash(field: str) -> None:
    base = manifest()
    moved = manifest(**{field: "zzzz"})
    assert base.run_id != moved.run_id, f"{field} does not affect the run id"


def test_changing_a_profile_changes_the_identity() -> None:
    base = manifest()
    moved = manifest(execution_profile={"profile_id": "STRESS"})
    assert base.run_id != moved.run_id


def test_the_manifest_round_trips_to_json() -> None:
    import json

    payload = json.loads(manifest(created_at=dt.datetime.now(dt.UTC).isoformat()).to_json())
    assert payload["run_id"]
    assert payload["identity"]["instrument"] == "ES"
    assert "operator" in payload["provenance"]
