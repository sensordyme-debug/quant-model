"""The translation layer, including the two defects the certification audit actually found.

``test_the_epoch_conversion_survives_a_microsecond_column`` and
``test_a_subclass_cannot_shadow_the_instrument_spec`` are not hypothetical. Both were real
bugs in the first draft of this package, both were silent, and both would have corrupted
every number downstream. They are pinned here so they cannot come back.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pandas as pd
import pytest

from quant_brain.data.schema import DataForm, build_frame
from topstep_backtester.adapters import contracts
from topstep_backtester.adapters.bars import (
    BarAdapterError,
    step_for,
    to_upstream_bars,
)
from topstep_backtester.strategies.base import ResearchStrategy, StrategyContractError
from topstep_backtester.strategies.probe import PROBE_SPEC
from topstep_backtester.upstream import spec_for_symbol, validate_bars

DAY = dt.date(2025, 12, 1)


def frame(
    *,
    n: int = 6,
    instrument: str = "ES",
    contract_symbol: str = "ESZ5",
    interval: str = "1min",
    opens: list[float] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    closes: list[float] | None = None,
    volumes: list[float] | None = None,
) -> pd.DataFrame:
    stamps = pd.date_range(f"{DAY.isoformat()} 14:30", periods=n, freq="1min", tz="UTC")
    return build_frame(
        instrument=instrument,
        contract_symbol=contract_symbol,
        contract_family=instrument,
        timestamp=stamps,
        session_date=[DAY] * n,
        bar_interval=interval,
        open_=opens or [5000.00] * n,
        high=highs or [5000.50] * n,
        low=lows or [4999.75] * n,
        close=closes or [5000.25] * n,
        volume=volumes or [100] * n,
    )


# ======================================================================================
# the timestamp base - the defect that misdated every bar by fifty-five years
# ======================================================================================


def test_the_epoch_conversion_survives_a_microsecond_column() -> None:
    """pandas 3.0 builds datetime64[us]; astype("int64") then yields MICROseconds.

    The engine reads that integer as nanoseconds, so every bar lands in January 1970 -
    ordered, self-consistent, passing upstream validation, and completely wrong.
    """
    source = frame()
    assert getattr(source["timestamp"].dtype, "unit", None) == "us", (
        "fixture no longer exercises the bug - the canonical column is no longer "
        "microsecond-resolution, so this test would pass vacuously"
    )

    bars, _ = to_upstream_bars(
        source, instrument="ES", bar_interval="1min", data_form=DataForm.RAW
    )
    restored = pd.Timestamp(bars[0].ts_event, unit="ns", tz="UTC")
    assert restored == source["timestamp"].iloc[0]
    assert restored.year == 2025, "bars were misdated - the epoch base is wrong again"


def test_microsecond_and_nanosecond_columns_give_identical_bars() -> None:
    micros = frame()
    nanos = micros.assign(timestamp=micros["timestamp"].dt.as_unit("ns"))
    a, _ = to_upstream_bars(micros, instrument="ES", bar_interval="1min",
                            data_form=DataForm.RAW)
    b, _ = to_upstream_bars(nanos, instrument="ES", bar_interval="1min",
                            data_form=DataForm.RAW)
    assert [x.ts_event for x in a] == [x.ts_event for x in b]
    assert [x.ts_init for x in a] == [x.ts_init for x in b]


def test_the_canonical_stamp_becomes_the_bar_start_not_its_completion() -> None:
    """The one-bar-of-hindsight bug, pinned.

    The engine advances its clock to ``ts_init`` before showing the strategy a bar, so
    ``ts_init`` must be the bar's END. Mapping the canonical start stamp there would let
    every strategy act on a bar one interval before it finished.
    """
    source = frame()
    bars, report = to_upstream_bars(
        source, instrument="ES", bar_interval="1min", data_form=DataForm.RAW
    )
    first = source["timestamp"].iloc[0]
    assert pd.Timestamp(bars[0].ts_event, unit="ns", tz="UTC") == first
    assert pd.Timestamp(bars[0].ts_init, unit="ns", tz="UTC") == first + pd.Timedelta(minutes=1)
    assert bars[0].ts_init > bars[0].ts_event
    assert report.step_ns == 60_000_000_000


@pytest.mark.parametrize(
    ("interval", "expected_ns"),
    [("1min", 60_000_000_000), ("5min", 300_000_000_000), ("1h", 3_600_000_000_000)],
)
def test_the_step_matches_the_interval(interval: str, expected_ns: int) -> None:
    _, _, step = step_for(interval)
    assert step == expected_ns


def test_an_untranslatable_interval_is_refused() -> None:
    with pytest.raises(BarAdapterError, match="not translatable"):
        step_for("1day")


# ======================================================================================
# refusals - the adapter reports and refuses, it never repairs
# ======================================================================================


def test_an_off_grid_price_is_refused_rather_than_rounded() -> None:
    bad = frame(closes=[5000.10] + [5000.25] * 5)
    with pytest.raises(BarAdapterError, match="not a multiple of the 0.25 tick"):
        to_upstream_bars(bad, instrument="ES", bar_interval="1min", data_form=DataForm.RAW)


def test_a_fractional_volume_is_refused() -> None:
    bad = frame(volumes=[100.5] + [100.0] * 5)
    with pytest.raises(BarAdapterError, match="fractional"):
        to_upstream_bars(bad, instrument="ES", bar_interval="1min", data_form=DataForm.RAW)


def test_a_shuffled_frame_is_refused_rather_than_sorted() -> None:
    shuffled = frame().iloc[[3, 0, 1, 2, 4, 5]]
    with pytest.raises(BarAdapterError, match="not in timestamp order"):
        to_upstream_bars(shuffled, instrument="ES", bar_interval="1min",
                         data_form=DataForm.RAW)


def test_a_duplicate_timestamp_is_refused_rather_than_deduplicated() -> None:
    source = frame()
    duplicated = pd.concat([source, source.iloc[[2]]]).sort_values("timestamp")
    with pytest.raises(BarAdapterError, match="duplicate timestamp"):
        to_upstream_bars(duplicated, instrument="ES", bar_interval="1min",
                         data_form=DataForm.RAW)


def test_impossible_ohlc_is_refused() -> None:
    bad = frame(highs=[4999.00] * 6)
    with pytest.raises(BarAdapterError, match="OHLC is impossible"):
        to_upstream_bars(bad, instrument="ES", bar_interval="1min", data_form=DataForm.RAW)


def test_a_missing_price_is_refused_rather_than_filled() -> None:
    bad = frame(closes=[float("nan")] + [5000.25] * 5)
    with pytest.raises(BarAdapterError, match="is missing"):
        to_upstream_bars(bad, instrument="ES", bar_interval="1min", data_form=DataForm.RAW)


@pytest.mark.parametrize(
    "form", [DataForm.CONTINUOUS_BACK_ADJUSTED, DataForm.CONTINUOUS_FORWARD_ADJUSTED]
)
def test_an_adjusted_series_is_refused_because_its_prices_were_never_quoted(
    form: DataForm,
) -> None:
    with pytest.raises(BarAdapterError, match="never quoted"):
        to_upstream_bars(frame(), instrument="ES", bar_interval="1min", data_form=form)


def test_a_declared_interval_mismatch_is_refused() -> None:
    with pytest.raises(BarAdapterError, match="declares bar_interval"):
        to_upstream_bars(frame(), instrument="ES", bar_interval="5min",
                         data_form=DataForm.RAW)


def test_an_unknown_instrument_is_refused() -> None:
    with pytest.raises(BarAdapterError, match="no upstream spec"):
        to_upstream_bars(
            frame(instrument="ZZZZ", contract_symbol="ZZZZZ5"),
            instrument="ZZZZ", bar_interval="1min", data_form=DataForm.RAW,
        )


def test_an_override_on_a_raw_frame_is_refused() -> None:
    """RAW data already knows its contract; overriding would discard the real identity."""
    with pytest.raises(BarAdapterError, match="already carries its physical contract"):
        to_upstream_bars(frame(), instrument="ES", bar_interval="1min",
                         data_form=DataForm.RAW,
                         contract_id_override="CON.F.US.ES.Z25")


# ======================================================================================
# what the adapter produces passes the engine's own validator
# ======================================================================================


def test_adapted_bars_pass_upstream_validation() -> None:
    bars, _ = to_upstream_bars(frame(), instrument="ES", bar_interval="1min",
                               data_form=DataForm.RAW)
    report = validate_bars(bars, spec_for_symbol("ES"))
    assert report.ok, [(i.code, i.message) for i in report.issues]


def test_prices_arrive_as_exact_decimals_not_floats() -> None:
    bars, _ = to_upstream_bars(frame(), instrument="ES", bar_interval="1min",
                               data_form=DataForm.RAW)
    assert isinstance(bars[0].close, Decimal)
    assert bars[0].close == Decimal("5000.25")
    assert isinstance(bars[0].volume, int)


# ======================================================================================
# contract identity
# ======================================================================================


def test_a_floor_code_becomes_the_contract_id_the_engine_expects() -> None:
    cid = contracts.contract_id_from_floor_code("ESZ5", instrument="ES", reference=DAY)
    assert cid == "CON.F.US.ES.Z25"
    contracts.assert_resolves(cid, expect="ES")


def test_a_two_digit_year_needs_no_reference_date() -> None:
    assert contracts.parse_floor_code("ESZ25") == ("ES", 2025, 12)


def test_a_single_digit_year_without_a_reference_is_refused_rather_than_guessed() -> None:
    with pytest.raises(contracts.ContractIdError, match="single year digit"):
        contracts.parse_floor_code("ESU5")


def test_a_single_digit_year_resolves_to_the_nearest_year() -> None:
    assert contracts.parse_floor_code("ESU5", reference=dt.date(2025, 6, 1))[1] == 2025
    assert contracts.parse_floor_code("ESU5", reference=dt.date(2034, 6, 1))[1] == 2035


def test_a_root_that_disagrees_with_the_frame_is_refused() -> None:
    with pytest.raises(contracts.ContractIdError, match="has root"):
        contracts.contract_id_from_floor_code("NQZ5", instrument="ES", reference=DAY)


def test_the_engine_reads_our_contract_ids_the_way_we_intended() -> None:
    for symbol in ("ES", "NQ", "MNQ", "MES"):
        cid = contracts.contract_id(symbol, year=2026, month=3)
        contracts.assert_resolves(cid, expect=symbol)


# ======================================================================================
# the strategy base class guards
# ======================================================================================


def test_a_non_async_on_bar_is_refused_at_class_definition() -> None:
    with pytest.raises(StrategyContractError, match="must be `async def`"):

        class Broken(ResearchStrategy):
            def on_bar(self, bar: object) -> None:  # type: ignore[override]
                pass


def test_a_subclass_cannot_shadow_the_instrument_spec() -> None:
    """``SymbolStrategy.spec`` is the tick size and tick value. Shadowing it moves the money.

    The first draft of ``ResearchStrategy`` assigned ``self.spec`` and was caught only
    because upstream happens to expose it as a read-only property. Nothing protects the
    other thirty-odd public names, so the guard covers all of them.
    """
    with pytest.raises(StrategyContractError, match="already uses"):

        class Shadowing(ResearchStrategy):
            spec = PROBE_SPEC  # type: ignore[assignment]

            async def on_bar(self, bar: object) -> None:
                pass


def test_overriding_a_real_callback_is_still_allowed() -> None:
    class Fine(ResearchStrategy):
        async def on_bar(self, bar: object) -> None:
            pass

        async def on_start(self) -> None:
            pass

    assert issubclass(Fine, ResearchStrategy)
