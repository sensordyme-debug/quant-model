"""The end-to-end wiring test: hand-computed arithmetic in, engine result out.

WHY THESE NUMBERS AND NOT A RECORDED BASELINE
---------------------------------------------
Every expected value here is derived from the contract terms by hand and written into
``strategies/probe.py`` as a constant. A golden captured from a previous run would only ever
prove the pipeline still does what it did last week - including, if it came to that, still
being wrong in the same way. These assert what the arithmetic says the answer must be.

    buy 1 ES at 5000.00, sell at 5002.00
    2.00 points / 0.25 tick = 8 ticks
    8 ticks * $12.50        = $100.00 gross
    less one round turn     = the net the engine must report
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from topstep_backtester.profiles.account import (
    TOPSTEP_50K_COMBINE,
    TOPSTEP_50K_COMBINE_DOC_CONSISTENCY,
)
from topstep_backtester.profiles.execution import (
    BASELINE,
    IDEAL,
    LADDER,
    QUOTED_RUNG,
    STRESS_2TICK,
)
from topstep_backtester.reporting.cards import card_from_run
from topstep_backtester.reporting.report import build_report
from topstep_backtester.run import run_backtest, run_ladder
from topstep_backtester.strategies import probe as P
from topstep_backtester.upstream import SPECS
from topstep_backtester.validation import integrity


def make(series=None, series_id: str = "SYNTH-probe", **kwargs):
    return run_backtest(
        P.probe_series() if series is None else series,
        lambda cid: P.SyntheticProbe(cid, synthetic_series_id=series_id),
        spec=P.PROBE_SPEC,
        **kwargs,
    )


# ======================================================================================
# the two hand-computed goldens
# ======================================================================================


def test_the_probe_constants_match_the_engines_own_instrument_table() -> None:
    """The probe derives its expected P&L from restated ES terms. They must be the real ones.

    If this fails, every other assertion in this file is comparing the engine against the
    wrong arithmetic, and would keep passing while doing so.
    """
    es = SPECS["ES"]
    assert es.tick_size == P.ES_TICK_SIZE
    assert es.tick_value == P.ES_TICK_VALUE


def test_a_target_that_is_straddled_fills_at_the_limit_price() -> None:
    run = make()
    assert run.result.trade_count == 2, "expected exactly one entry and one exit"
    trip = run.result.round_trips[0]
    assert trip.gross_pnl == P.EXPECTED_GROSS_PNL == Decimal("100.00")
    assert trip.net_pnl == P.EXPECTED_GROSS_PNL - BASELINE.round_turn_cost("ES")
    assert run.result.ending_balance == Decimal("50000") + trip.net_pnl


def test_a_target_the_bar_opens_through_fills_at_the_open() -> None:
    """A marketable limit fills better than its limit price, and the pipeline must show it."""
    run = make(P.probe_series_gap(), series_id="SYNTH-probe-gap")
    trip = run.result.round_trips[0]
    assert trip.gross_pnl == P.EXPECTED_GAP_GROSS_PNL == Decimal("150.00")
    assert trip.gross_pnl > P.EXPECTED_GROSS_PNL, (
        "the gap fixture must pay MORE than the straddle fixture; if these are equal the "
        "pipeline is capping winners at their limit price"
    )


def test_the_entry_fills_on_the_bar_after_the_signal() -> None:
    """Upstream defers an order to the next bar. A fill on the signal bar would be hindsight."""
    run = make()
    fills = [e for e in _replay(run).fill_events if not e.voided]
    assert str(fills[0].side) == "BUY"
    assert fills[0].frame == P.ENTRY_BAR_INDEX + 1
    assert Decimal(str(fills[0].price)) == P.ENTRY_PRICE


def test_the_bracket_cannot_fill_on_the_bar_the_entry_filled_on() -> None:
    """Within one bar the price path is unknown, so an exit there would assume an ordering."""
    run = make()
    fills = [e for e in _replay(run).fill_events if not e.voided]
    assert fills[1].frame > fills[0].frame, (
        "a protective order filled on the same bar as the entry; that requires intrabar "
        "path information the data does not contain"
    )


def _replay(run) -> Any:
    #: The RunResult keeps the engine's objects rather than copies; the replay hangs off the
    #: same backtest, so re-running is the honest way to reach it from a test.
    from quant_brain.data.schema import DataForm
    from topstep_backtester.adapters.bars import to_upstream_bars
    from topstep_backtester.upstream import Backtest

    bars, report = to_upstream_bars(
        P.probe_series(), instrument="ES", bar_interval="1min", data_form=DataForm.RAW
    )
    return Backtest(
        bars,
        P.SyntheticProbe(report.contract_ids[0], synthetic_series_id="SYNTH-probe"),
        account=run.account_profile.size,
        dll_enabled=run.account_profile.dll_enabled,
        fill_config=run.execution_profile.bar_fill_config(),
        broker_config=run.execution_profile.broker_config(),
        fee_model=run.execution_profile.fee_model(),
        record=True,
    ).run().replay


# ======================================================================================
# reconciliation against independent arithmetic
# ======================================================================================


def test_the_engine_agrees_with_independent_arithmetic_exactly() -> None:
    run = make()
    integrity.assert_reconciled(run)
    assert run.reconciliation.gross_delta == 0
    assert run.reconciliation.net_delta == 0
    assert run.reconciliation.unclosed_qty == 0


def test_the_reconciliation_is_not_vacuous() -> None:
    """A reconciliation that compares nothing to nothing would also report agreement."""
    run = make()
    assert run.reference.round_trips, "the reference ledger booked no trades"
    assert run.reference.gross_pnl == Decimal("100.00")
    assert run.reference.costs > 0


def test_costs_are_actually_charged() -> None:
    integrity.assert_no_free_money(make())


# ======================================================================================
# determinism and reproducibility
# ======================================================================================


def test_the_same_inputs_produce_the_same_result_twice() -> None:
    report = integrity.assert_deterministic(make)
    assert report.run_id_a == report.run_id_b
    assert report.equity_curves_identical
    assert report.round_trips_identical


def test_the_run_id_does_not_depend_on_wall_clock_or_operator() -> None:
    """Identity covers inputs and assumptions; provenance is recorded beside it, not in it.

    The Phase E dataset manifest made the opposite mistake - a source path inside the
    identity hash meant the same data hashed differently on two machines.
    """
    a = make(operator="alice", notes=("first",))
    b = make(operator="bob", notes=("second",))
    assert a.run_id == b.run_id
    assert a.manifest.created_at != "" and b.manifest.created_at != ""
    assert a.manifest.operator != b.manifest.operator


def test_changing_an_assumption_changes_the_run_id() -> None:
    quoted = make(execution_profile=BASELINE)
    stressed = make(execution_profile=STRESS_2TICK)
    assert quoted.run_id != stressed.run_id, (
        "two runs under different execution assumptions share an identity; results computed "
        "under different assumptions could then be compared as if they were the same"
    )


def test_a_fresh_result_is_not_stale() -> None:
    run = make()
    integrity.assert_current(run.manifest, spec=P.PROBE_SPEC)


def test_a_result_whose_spec_moved_is_detected_as_stale() -> None:
    run = make()
    import dataclasses

    moved = dataclasses.replace(
        P.PROBE_SPEC, parameters={**dict(P.PROBE_SPEC.parameters), "take_profit_ticks": 9}
    )
    assert moved.spec_hash != P.PROBE_SPEC.spec_hash
    with pytest.raises(integrity.StaleResultError, match="spec hash moved"):
        integrity.assert_current(run.manifest, spec=moved)


# ======================================================================================
# the execution ladder
# ======================================================================================


def test_every_rung_runs_and_reconciles() -> None:
    runs = run_ladder(
        P.probe_series(),
        lambda cid: P.SyntheticProbe(cid, synthetic_series_id="SYNTH-probe"),
        spec=P.PROBE_SPEC,
        ladder=LADDER,
    )
    assert set(runs) == {p.profile_id for p in LADDER}
    for run in runs.values():
        integrity.assert_reconciled(run)


def test_slippage_actually_moves_the_fill() -> None:
    """Proves the ladder is live rather than decorative.

    The gross P&L of this fixture is deliberately INSENSITIVE to entry slippage - upstream
    places bracket children at tick offsets from the actual entry fill, so a worse entry
    moves the target by the same amount. The ladder's effect therefore shows up in the fill
    PRICE, which is what this asserts. A test that only compared gross would pass on a
    pipeline where the execution profile was never wired up at all.
    """
    ideal = _entry_price(IDEAL)
    stressed = _entry_price(STRESS_2TICK)
    assert stressed > ideal, (
        f"entry filled at {stressed} under STRESS_2TICK and {ideal} under IDEAL; the "
        f"execution profile is not reaching the engine"
    )
    assert stressed - ideal == STRESS_2TICK.market_slippage_ticks * P.ES_TICK_SIZE


def _entry_price(profile) -> Decimal:
    from quant_brain.data.schema import DataForm
    from topstep_backtester.adapters.bars import to_upstream_bars
    from topstep_backtester.upstream import Backtest

    bars, report = to_upstream_bars(
        P.probe_series(), instrument="ES", bar_interval="1min", data_form=DataForm.RAW
    )
    replay: Any = Backtest(
        bars,
        P.SyntheticProbe(report.contract_ids[0], synthetic_series_id="SYNTH-probe"),
        fill_config=profile.bar_fill_config(),
        broker_config=profile.broker_config(),
        fee_model=profile.fee_model(),
        record=True,
    ).run().replay
    return Decimal(str([e for e in replay.fill_events if not e.voided][0].price))


# ======================================================================================
# the probe refuses to be pointed at anything real
# ======================================================================================


def test_the_probe_refuses_a_series_that_is_not_declared_synthetic() -> None:
    with pytest.raises(ValueError, match="refuses series"):
        P.SyntheticProbe("CON.F.US.ES.M25", synthetic_series_id="ES-1min-2024")


# ======================================================================================
# reporting
# ======================================================================================


def test_the_card_leads_with_disqualifiers_not_with_profit() -> None:
    card = card_from_run(make())
    labels = [label for label, _ in card.as_rows()]
    assert labels[0] == "verdict"
    assert labels.index("breached") < labels.index("net P&L")
    assert labels.index("reconciled vs independent arithmetic") < labels.index("net P&L")
    assert labels[-1] == "ending balance"


def test_a_one_day_probe_is_flagged_provisional() -> None:
    """The probe trades a single day. Upstream's floor is 30, so PROVISIONAL is correct.

    This is the flag propagating, not a defect: a pipeline that reported a clean banner for
    a one-day sample would be the failure. Breach and reconciliation must still be clear,
    so the banner names exactly one thing.
    """
    card = card_from_run(make())
    assert card.provisional is True
    assert card.banner() == "PROVISIONAL - SAMPLE TOO SMALL FOR THE STATISTICS"
    assert card.reconciled is True
    assert card.breached is False


def test_the_report_prints_every_rung_and_names_what_it_cannot_model() -> None:
    runs = run_ladder(
        P.probe_series(),
        lambda cid: P.SyntheticProbe(cid, synthetic_series_id="SYNTH-probe"),
        spec=P.PROBE_SPEC,
        ladder=LADDER,
    )
    text = build_report(runs, quoted_profile_id=QUOTED_RUNG.profile_id, title="probe")
    for profile in LADDER:
        assert profile.profile_id in text, f"{profile.profile_id} missing from the report"
    assert "UNMODELED" in text
    assert "Express Funded" in text
    assert "first payout" in text.lower()


def test_a_report_cannot_quote_a_rung_it_did_not_run() -> None:
    runs = run_ladder(
        P.probe_series(),
        lambda cid: P.SyntheticProbe(cid, synthetic_series_id="SYNTH-probe"),
        spec=P.PROBE_SPEC,
        ladder=(BASELINE,),
    )
    with pytest.raises(KeyError, match="cannot quote a rung it did not run"):
        build_report(runs, quoted_profile_id=STRESS_2TICK.profile_id)


# ======================================================================================
# the account profile is actually applied
# ======================================================================================


def test_the_account_profile_reaches_the_engine() -> None:
    run = make()
    params = run.account_profile.params()
    assert run.result.starting_balance == params.starting_balance == Decimal("50000")
    assert run.result.profit_target == params.profit_target == Decimal("3000")


def test_the_two_consistency_readings_produce_different_run_ids() -> None:
    strict = make(account_profile=TOPSTEP_50K_COMBINE)
    documented = make(account_profile=TOPSTEP_50K_COMBINE_DOC_CONSISTENCY)
    assert strict.run_id != documented.run_id
    assert strict.account_profile.consistency_pct == Decimal("0.5")
    assert documented.account_profile.consistency_pct == Decimal("0.55")
