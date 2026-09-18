"""Reconstruction, DST and genealogy - certification questions 5, 9, 10, 11 and 14.

Each of these answers a challenge that a summary statistic cannot:

    DST          does an hour that does not exist, and an hour that happens twice, still
                 map to the right bar?
    trades       which trades made this number?
    months       was it one good month, or twelve?
    account      how close did the account come to liquidation on its worst day?
    genealogy    is this the first version of this idea, or the eleventh?
"""
from __future__ import annotations

import datetime as dt
import itertools
from decimal import Decimal

import pandas as pd
import pytest

from quant_brain.data.schema import DataForm, build_frame
from topstep_backtester.adapters.bars import to_upstream_bars
from topstep_backtester.reporting import ledger
from topstep_backtester.run import run_backtest
from topstep_backtester.strategies import probe as P
from topstep_backtester.strategies import registry
from topstep_backtester.strategies.spec import FrozenStrategySpec, SpecError


def make(**kwargs):
    return run_backtest(
        P.probe_series(),
        lambda cid: P.SyntheticProbe(cid, synthetic_series_id="SYNTH-probe"),
        spec=P.PROBE_SPEC,
        #: this engine is archived; these tests reproduce its recorded behaviour
        allow_archived=True,
        **kwargs,
    )


# ======================================================================================
# Q5 - DST
# ======================================================================================


def dst_frame(day: dt.date, *, n: int, first_utc: str) -> pd.DataFrame:
    stamps = pd.date_range(pd.Timestamp(first_utc, tz="UTC"), periods=n, freq="1min", tz="UTC")
    return build_frame(
        instrument="ES", contract_symbol="ESH5", contract_family="ES",
        timestamp=stamps, session_date=[day] * n, bar_interval="1min",
        open_=[5000.00] * n, high=[5000.50] * n, low=[4999.75] * n,
        close=[5000.25] * n, volume=[100] * n,
    )


@pytest.mark.parametrize(
    ("label", "day", "first_utc", "expected_et_hour", "expected_offset"),
    [
        #: the Friday before the spring-forward weekend - still EST, UTC-5
        ("EST before spring forward", dt.date(2025, 3, 7), "2025-03-07 14:30:00", 9, -5),
        #: the Monday after - now EDT, UTC-4, so the same 09:30 ET is 13:30 UTC
        ("EDT after spring forward", dt.date(2025, 3, 10), "2025-03-10 13:30:00", 9, -4),
        #: the Friday before the autumn fall-back - still EDT
        ("EDT before fall back", dt.date(2025, 10, 31), "2025-10-31 13:30:00", 9, -4),
        #: the Monday after - back to EST
        ("EST after fall back", dt.date(2025, 11, 3), "2025-11-03 14:30:00", 9, -5),
    ],
)
def test_the_same_venue_time_survives_both_dst_transitions(
    label: str, day: dt.date, first_utc: str, expected_et_hour: int, expected_offset: int
) -> None:
    """09:30 ET is a different UTC instant either side of a transition, and must stay 09:30 ET.

    The canonical layer stores UTC and the engine converts to the venue clock itself, so the
    only thing this can get wrong is the conversion to epoch nanoseconds. That is exactly the
    defect this pipeline already found once, which is why it is asserted on four dates rather
    than one.
    """
    frame = dst_frame(day, n=10, first_utc=first_utc)
    bars, _ = to_upstream_bars(
        frame, instrument="ES", bar_interval="1min", data_form=DataForm.RAW
    )
    from zoneinfo import ZoneInfo

    et = dt.datetime.fromtimestamp(bars[0].ts_event / 1e9, ZoneInfo("America/New_York"))
    assert et.hour == expected_et_hour and et.minute == 30, f"{label}: got {et}"
    assert et.utcoffset() == dt.timedelta(hours=expected_offset), f"{label}: wrong offset"
    assert et.date() == day


def test_bar_spacing_is_unaffected_by_a_dst_transition() -> None:
    """A wall-clock day is 23 or 25 hours across a transition; a one-minute bar is always
    sixty seconds. Mixing those up is the classic spring-forward bug."""
    frame = dst_frame(dt.date(2025, 3, 10), n=10, first_utc="2025-03-10 13:30:00")
    bars, _ = to_upstream_bars(
        frame, instrument="ES", bar_interval="1min", data_form=DataForm.RAW
    )
    gaps = {b.ts_event - a.ts_event for a, b in itertools.pairwise(bars)}
    assert gaps == {60_000_000_000}


# ======================================================================================
# Q9 - every trade reconstructible
# ======================================================================================


def test_every_trade_can_be_reconstructed_from_the_ledger() -> None:
    run = make()
    rows = ledger.trade_ledger(run.result)
    assert len(rows) == len(run.result.round_trips) == 1
    row = rows[0]
    assert row.side == "long"
    assert row.qty == 1
    assert row.gross_pnl == Decimal("100.00")
    assert row.net_pnl == row.gross_pnl - row.costs
    assert row.duration_seconds > 0
    assert row.contract_id.startswith("CON.F.US.ES.")


def test_the_ledger_totals_equal_the_headline_number() -> None:
    """A ledger that does not add up to the reported P&L is not a reconstruction."""
    run = make()
    rows = ledger.trade_ledger(run.result)
    total = sum((row.net_pnl for row in rows), Decimal(0))
    assert total == run.result.ending_balance - run.result.starting_balance


def test_the_trade_table_renders() -> None:
    text = ledger.markdown_trades(ledger.trade_ledger(make().result))
    assert "gross" in text and "$100.00" in text


# ======================================================================================
# Q10 - monthly P&L reconstructible
# ======================================================================================


def test_monthly_pnl_reconstructs_and_reconciles() -> None:
    run = make()
    rows = ledger.monthly(run.result)
    assert len(rows) == 1
    assert rows[0].month == "2025-06"
    assert rows[0].days_with_a_trade == 1
    agrees, delta = ledger.reconcile_monthly(run.result, rows)
    assert agrees, f"monthly totals are off by {delta}"


def test_the_monthly_reconciliation_can_fail() -> None:
    """Otherwise the check above proves nothing."""
    run = make()
    rows = list(ledger.monthly(run.result))
    import dataclasses

    tampered = [dataclasses.replace(rows[0], net_pnl=rows[0].net_pnl + Decimal("1.00"))]
    agrees, delta = ledger.reconcile_monthly(run.result, tampered)
    assert agrees is False
    assert delta == Decimal("1.00")


def test_the_monthly_table_renders() -> None:
    assert "net P&L" in ledger.markdown_monthly(ledger.monthly(make().result))


# ======================================================================================
# Q11 - the Topstep account path
# ======================================================================================


def test_the_account_path_carries_the_trailing_floor_beside_the_balance() -> None:
    run = make()
    path = ledger.account_path(run.result)
    assert len(path) == 1
    day = path[0]
    assert day.day == dt.date(2025, 6, 3)
    assert day.eod_balance == run.result.ending_balance

    #: THE FLOOR TRAILED. It starts $2,000 below the $50,000 balance, at $48,000, and the
    #: $96.20 the probe made pulled it up with the account to $48,096.20. That is the
    #: trailing maximum loss limit doing its job: profit raises the liquidation level, so
    #: giving the gain back breaches even though the balance is still above where it began.
    #: A static $48,000 floor here would mean the trailing rule was not being applied.
    assert day.floor_after == Decimal("48096.20")
    assert day.floor_after == day.eod_balance - Decimal("2000"), (
        "the floor should sit exactly the MLL buffer below the high-water balance"
    )
    assert day.headroom == Decimal("2000")


def test_the_worst_day_is_identifiable_even_on_a_winning_run() -> None:
    """"Ended up" and "was nearly liquidated in week one" are both true of one curve."""
    path = ledger.account_path(make().result)
    worst = ledger.worst_headroom(path)
    assert worst is not None
    assert worst.headroom == min(day.headroom for day in path)


def test_worst_headroom_of_an_empty_path_is_none_not_a_crash() -> None:
    assert ledger.worst_headroom([]) is None


def test_the_account_path_table_renders() -> None:
    text = ledger.markdown_account_path(ledger.account_path(make().result))
    assert "trailing floor" in text and "headroom" in text


# ======================================================================================
# Q14 - strategy genealogy
# ======================================================================================


BASE = {
    "name": "owner_idea", "version": "1.0.0", "instrument": "ES", "bar_interval": "5min",
    "session_window": "09:30-16:00 ET", "entry_rules": ("a",), "exit_rules": ("b",),
    "risk_rules": ("c",), "parameters": {"stop": 10},
}


@pytest.fixture(autouse=True)
def _clean_registry():
    registry.clear()
    registry.reset_genealogy()
    yield
    registry.clear()
    registry.reset_genealogy()


def test_a_variant_is_a_different_experiment_from_its_parent() -> None:
    parent = FrozenStrategySpec(**BASE)
    child = FrozenStrategySpec(
        **{**BASE, "parameters": {"stop": 12}},
        derived_from=parent.spec_hash,
        derivation_reason="widened the stop after the parent stopped out early",
    )
    assert child.spec_hash != parent.spec_hash
    assert parent.generation == 0 and child.generation == 1


def test_a_lineage_with_no_stated_reason_is_refused() -> None:
    with pytest.raises(SpecError, match="no derivation_reason"):
        FrozenStrategySpec(**BASE, derived_from="abcdef0123456789")


def test_a_reason_with_no_parent_is_refused() -> None:
    with pytest.raises(SpecError, match="Name the parent"):
        FrozenStrategySpec(**BASE, derivation_reason="tweaked it")


def test_the_genealogy_counts_the_whole_family() -> None:
    """Testing the third variant of one idea is not the same as testing the first."""
    parent = FrozenStrategySpec(**BASE).freeze(author="owner")
    registry.register(parent, lambda cid: None)

    previous = parent
    for n, stop in enumerate((12, 14), start=2):
        variant = FrozenStrategySpec(
            **{**BASE, "name": f"owner_idea_v{n}", "parameters": {"stop": stop}},
            derived_from=previous.spec_hash,
            derivation_reason=f"widened the stop to {stop}",
        ).freeze(author="owner")
        registry.register(variant, lambda cid: None, acknowledge_single_candidate=True)
        previous = variant

    assert registry.hypotheses_examined() == 3
    assert registry.lineage(previous.spec_hash) == (
        registry.GENEALOGY[previous.spec_hash]["derived_from"],
        parent.spec_hash,
    )
    assert registry.family_size(previous.spec_hash) == 3


def test_withdrawing_a_candidate_does_not_erase_that_it_was_tested() -> None:
    """A ledger that shrinks would report fewer hypotheses than were actually examined."""
    spec = FrozenStrategySpec(**BASE).freeze(author="owner")
    registry.register(spec, lambda cid: None)
    registry.unregister(spec.name)

    assert registry.count() == 0
    assert registry.hypotheses_examined() == 1, (
        "the withdrawn strategy vanished from the genealogy; a later multiple-testing "
        "correction would then understate how many ideas were tried"
    )


def test_a_second_candidate_needs_an_explicit_acknowledgement() -> None:
    first = FrozenStrategySpec(**BASE).freeze(author="owner")
    second = FrozenStrategySpec(**{**BASE, "name": "another_idea"}).freeze(author="owner")
    registry.register(first, lambda cid: None)
    with pytest.raises(registry.RegistryError, match="one strategy at a time"):
        registry.register(second, lambda cid: None)
    registry.register(second, lambda cid: None, acknowledge_single_candidate=True)
    assert registry.count() == 2


def test_an_unfrozen_spec_cannot_be_registered() -> None:
    with pytest.raises(SpecError, match="not frozen"):
        registry.register(FrozenStrategySpec(**BASE), lambda cid: None)
