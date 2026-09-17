"""Canonical frames in, upstream ``Bar`` objects out. The most dangerous file in Layer B.

WHY DANGEROUS
-------------
Everything the engine reports is a function of the bars it was given. A translation defect
here does not announce itself as an error; it announces itself as a plausible equity curve.
Three specific ways that happens, and what this module does about each:

1. THE STAMP. The canonical store is START-stamped: a bar labelled 09:30 covers 09:30:00 to
   09:30:59. The engine, by contrast, advances its clock to ``ts_init`` and only then shows
   the strategy the bar (``engine/backtest.py`` line 181), so ``ts_init`` is the bar's
   COMPLETION instant and the earliest moment a decision on it can act. Mapping the
   canonical stamp to ``ts_init`` instead of ``ts_event`` would hand every strategy one bar
   of hindsight. Upstream calls this "the classic off-by-one look-ahead stamp bug" and
   rejects ``ts_event >= ts_init`` outright; this module is the reason that check never
   fires, not the thing it protects against.

2. THE PRICE. Canonical prices are float64; the engine works in ``Decimal`` on the tick
   grid and refuses anything off it. The temptation is to round. Rounding invents a price
   nobody quoted, so a fill at it is fiction - this module converts exactly, via the
   shortest round-tripping decimal string, and REFUSES off-grid input naming the bar.

3. THE SERIES. A back- or forward-adjusted continuous series contains prices that were
   never quoted anywhere. It is a return series wearing price clothing, and filling against
   one produces a P&L that could not have been earned. ``DataForm.execution_valid`` already
   encodes this in the canonical layer; this module enforces it at the boundary.

WHAT THIS MODULE WILL NOT DO
----------------------------
Fill gaps, forward-fill a missing bar, drop a duplicate, sort a shuffled frame, coerce a
fractional volume, or repair OHLC. Every one of those is a decision about what the market
did, and this is a translator. It reports and refuses.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from decimal import Decimal
from typing import cast

import numpy as np
import pandas as pd

from quant_brain.data.schema import DataForm, validate_frame
from topstep_backtester.adapters.contracts import contract_id_from_floor_code
from topstep_backtester.upstream import (
    SPECS,
    AggregateBarUnit,
    Bar,
    BarType,
    spec_for_symbol,
)

#: Canonical ``bar_interval`` strings this pipeline understands, and the upstream bar unit
#: each maps to. Deliberately a small explicit table: an interval the engine has no fixed
#: nanosecond step for (DAY and above) cannot be translated at all, and a silent fallback
#: would be worse than a refusal.
INTERVALS: dict[str, tuple[AggregateBarUnit, int]] = {
    "1s": (AggregateBarUnit.SECOND, 1),
    "1min": (AggregateBarUnit.MINUTE, 1),
    "2min": (AggregateBarUnit.MINUTE, 2),
    "3min": (AggregateBarUnit.MINUTE, 3),
    "5min": (AggregateBarUnit.MINUTE, 5),
    "10min": (AggregateBarUnit.MINUTE, 10),
    "15min": (AggregateBarUnit.MINUTE, 15),
    "30min": (AggregateBarUnit.MINUTE, 30),
    "60min": (AggregateBarUnit.MINUTE, 60),
    "1h": (AggregateBarUnit.HOUR, 1),
}

#: Nanoseconds in one unit of each upstream bar unit.
_UNIT_NS: dict[AggregateBarUnit, int] = {
    AggregateBarUnit.SECOND: 1_000_000_000,
    AggregateBarUnit.MINUTE: 60_000_000_000,
    AggregateBarUnit.HOUR: 3_600_000_000_000,
}


class BarAdapterError(ValueError):
    """A canonical frame that cannot be translated exactly. Never downgraded to a warning."""


@dataclass(frozen=True)
class BarAdapterReport:
    """What the translation did, in enough detail to audit it without rerunning it."""

    rows_in: int
    bars_out: int
    instrument: str
    bar_interval: str
    unit: str
    unit_number: int
    step_ns: int
    contract_ids: tuple[str, ...]
    first_ts_event_utc: str
    last_ts_event_utc: str
    last_ts_init_utc: str
    data_form: str
    stamp_convention: str
    notes: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, object]:
        return {
            "rows_in": self.rows_in,
            "bars_out": self.bars_out,
            "instrument": self.instrument,
            "bar_interval": self.bar_interval,
            "unit": self.unit,
            "unit_number": self.unit_number,
            "step_ns": self.step_ns,
            "contract_ids": list(self.contract_ids),
            "first_ts_event_utc": self.first_ts_event_utc,
            "last_ts_event_utc": self.last_ts_event_utc,
            "last_ts_init_utc": self.last_ts_init_utc,
            "data_form": self.data_form,
            "stamp_convention": self.stamp_convention,
            "notes": list(self.notes),
        }


def step_for(bar_interval: str) -> tuple[AggregateBarUnit, int, int]:
    """``("5min")`` -> ``(MINUTE, 5, 300_000_000_000)``."""
    if bar_interval not in INTERVALS:
        raise BarAdapterError(
            f"bar_interval {bar_interval!r} is not translatable; this pipeline maps "
            f"{sorted(INTERVALS)}. Daily and above have no fixed nanosecond step on a "
            f"23-hour Globex day, which is why the engine refuses them too."
        )
    unit, number = INTERVALS[bar_interval]
    return unit, number, _UNIT_NS[unit] * number


def _price(value: float, *, tick: Decimal, column: str, when: str) -> Decimal:
    """float64 -> exact tick-grid ``Decimal``, or a refusal that names the bar."""
    if value is None or math.isnan(value):
        raise BarAdapterError(
            f"{when}: `{column}` is missing. A bar with no price is not a bar; the gap is a "
            f"fact about the data and filling it here would hide it."
        )
    as_decimal = Decimal(str(value))
    quotient = as_decimal / tick
    if quotient != quotient.to_integral_value():
        raise BarAdapterError(
            f"{when}: `{column}` = {as_decimal} is not a multiple of the {tick} tick. This "
            f"adapter will not round it - a price nudged onto the grid was never quoted, and "
            f"a fill at it would be fiction. Either the frame is an adjusted continuous "
            f"series (which is not execution-valid) or the source is wrong."
        )
    return as_decimal


def _epoch_ns(stamps: pd.Series, *, when: str) -> np.ndarray:
    """UTC nanoseconds since the epoch, whatever resolution the column happens to hold.

    THIS FUNCTION EXISTS BECAUSE THE OBVIOUS SPELLING IS WRONG.
    ``stamps.astype("int64")`` returns the column's underlying integers in ITS OWN unit, and
    pandas 3.0 builds ``datetime64[us]`` by default where pandas 2.x built ``[ns]``. On a
    microsecond column the obvious spelling therefore returns microseconds, the engine reads
    them as nanoseconds, and every bar lands in January 1970 - ordered, self-consistent, and
    off by fifty-five years. Nothing downstream notices: the bars are still monotonic, the
    step between them is still computed separately and still correct, and the upstream
    validator sees a well-formed weekday sequence.

    So the conversion is explicit, and then it is CHECKED by converting back. The assertion
    costs one vectorised comparison and removes an entire class of silent time-base defect.
    """
    as_ns = stamps.dt.as_unit("ns")
    epoch = as_ns.astype("int64").to_numpy()
    restored = pd.to_datetime(epoch, unit="ns", utc=True)
    if not restored.equals(pd.DatetimeIndex(as_ns.to_numpy(), tz="UTC")):
        raise BarAdapterError(
            f"{when}: timestamps did not survive conversion to epoch nanoseconds. The "
            f"canonical column is {stamps.dtype}; something about its resolution or timezone "
            f"is not what this adapter assumes, and guessing would misdate every bar."
        )
    return epoch


def _volume(value: float, *, when: str) -> int:
    if value is None or math.isnan(value):
        raise BarAdapterError(f"{when}: `volume` is missing")
    as_float = float(value)
    if as_float < 0:
        raise BarAdapterError(f"{when}: `volume` is negative ({as_float})")
    if as_float != int(as_float):
        raise BarAdapterError(
            f"{when}: `volume` = {as_float} is fractional. Contracts are integral; a "
            f"fractional count means the frame has been resampled with a mean rather than a "
            f"sum, and truncating it here would hide that."
        )
    return int(as_float)


def to_upstream_bars(
    frame: pd.DataFrame,
    *,
    instrument: str,
    bar_interval: str,
    data_form: DataForm,
    contract_id_override: str | None = None,
) -> tuple[tuple[Bar, ...], BarAdapterReport]:
    """Translate a canonical frame into the engine's bar sequence.

    ``contract_id_override`` exists for ``CONTINUOUS_UNADJUSTED`` frames, where every price
    was really quoted but no single physical contract spans the series. The engine needs one
    identity to look up the tick value; supplying it is a declaration, recorded in the
    report, not an inference. Adjusted forms are refused outright regardless.
    """
    validate_frame(frame, name=f"{instrument} {bar_interval}")
    if instrument not in SPECS:
        raise BarAdapterError(
            f"instrument {instrument!r} has no upstream spec; the engine covers "
            f"{sorted(SPECS)}"
        )
    if data_form.is_adjusted:
        raise BarAdapterError(
            f"{data_form.value} contains prices that were never quoted - the adjustment "
            f"shifts history so one end of the series is synthetic. Returns from it are "
            f"meaningful; FILLS from it are not, and this pipeline exists to produce fills. "
            f"Use RAW, or CONTINUOUS_UNADJUSTED with an explicit contract_id_override."
        )

    spec = spec_for_symbol(instrument)
    tick = spec.tick_size
    unit, number, step = step_for(bar_interval)

    declared = set(frame["bar_interval"].astype(str).unique())
    if declared != {bar_interval}:
        raise BarAdapterError(
            f"the frame declares bar_interval {sorted(declared)} but the caller asked for "
            f"{bar_interval!r}. A mismatch here silently changes every bar boundary."
        )

    notes: list[str] = []
    if contract_id_override is not None:
        if data_form is DataForm.RAW:
            raise BarAdapterError(
                "contract_id_override is for continuous series; a RAW frame already carries "
                "its physical contract in `contract_symbol` and overriding it would discard "
                "the real identity."
            )
        notes.append(
            f"contract identity declared as {contract_id_override} for a "
            f"{data_form.value} series; the series spans rolls and no single physical "
            f"contract covers it"
        )

    ordered = frame.reset_index(drop=True)
    #: cast, not a runtime conversion: DataFrame.__getitem__ is typed loosely enough
    #: that a checker cannot tell a column from a sub-frame, and the schema check
    #: above has already established this is the timestamp column.
    stamps = cast("pd.Series", ordered["timestamp"])
    if not stamps.is_monotonic_increasing:
        raise BarAdapterError(
            f"{instrument} {bar_interval}: the canonical frame is not in timestamp order. "
            f"This adapter will not sort it. A frame that arrived shuffled has been through "
            f"a concat or a merge that lost its ordering, and quietly sorting it here would "
            f"conceal whichever step did that."
        )
    if stamps.duplicated().any():
        first_dupe = cast("pd.Series", stamps[stamps.duplicated()]).iloc[0]
        raise BarAdapterError(
            f"duplicate timestamp {first_dupe} in the canonical frame. Two bars claiming the "
            f"same minute is a data defect; dropping one here would pick a winner silently. "
            f"Resolve it in the canonical layer where the provenance is."
        )

    epoch_ns = _epoch_ns(stamps, when=f"{instrument} {bar_interval}")
    opens = ordered["open"].to_numpy()
    highs = ordered["high"].to_numpy()
    lows = ordered["low"].to_numpy()
    closes = ordered["close"].to_numpy()
    volumes = ordered["volume"].to_numpy()
    symbols = ordered["contract_symbol"].astype(str).to_numpy()
    session_dates = ordered["session_date"].to_numpy()

    cache: dict[str, BarType] = {}
    bars: list[Bar] = []
    seen_ids: list[str] = []

    for i in range(len(ordered)):
        ts_event = int(epoch_ns[i])
        when = f"{instrument} bar at {stamps.iloc[i].isoformat()}"

        if contract_id_override is not None:
            cid = contract_id_override
        else:
            code = symbols[i]
            if not code:
                raise BarAdapterError(
                    f"{when}: `contract_symbol` is empty and no contract_id_override was "
                    f"given. The engine derives tick size and tick value from the contract "
                    f"id, so it cannot price a bar with no identity."
                )
            reference = session_dates[i]
            if isinstance(reference, pd.Timestamp):
                reference = reference.date()
            elif isinstance(reference, str):
                reference = dt.date.fromisoformat(reference)
            cid = contract_id_from_floor_code(code, instrument=instrument, reference=reference)

        bar_type = cache.get(cid)
        if bar_type is None:
            bar_type = BarType(contract_id=cid, unit=unit, unit_number=number)
            cache[cid] = bar_type
            seen_ids.append(cid)

        o = _price(float(opens[i]), tick=tick, column="open", when=when)
        h = _price(float(highs[i]), tick=tick, column="high", when=when)
        low = _price(float(lows[i]), tick=tick, column="low", when=when)
        c = _price(float(closes[i]), tick=tick, column="close", when=when)
        if h < max(o, c) or low > min(o, c):
            raise BarAdapterError(
                f"{when}: OHLC is impossible (o={o} h={h} l={low} c={c}). The engine rejects "
                f"this too; it is surfaced here so the offending bar is named."
            )

        bars.append(
            Bar(
                bar_type=bar_type,
                ts_event=ts_event,
                #: START-stamped in, so the completion instant is stamp + one interval. This
                #: single line is what keeps the strategy from seeing a bar before it closed.
                ts_init=ts_event + step,
                open=o,
                high=h,
                low=low,
                close=c,
                volume=_volume(float(volumes[i]), when=when),
            )
        )

    if not bars:
        raise BarAdapterError(
            f"{instrument} {bar_interval}: the canonical frame has no rows. An empty "
            f"backtest is not a result."
        )

    report = BarAdapterReport(
        rows_in=len(frame),
        bars_out=len(bars),
        instrument=instrument,
        bar_interval=bar_interval,
        unit=unit.name,
        unit_number=number,
        step_ns=step,
        contract_ids=tuple(seen_ids),
        first_ts_event_utc=stamps.iloc[0].isoformat(),
        last_ts_event_utc=stamps.iloc[-1].isoformat(),
        last_ts_init_utc=(stamps.iloc[-1] + pd.Timedelta(step, unit="ns")).isoformat(),
        data_form=data_form.value,
        stamp_convention="canonical timestamp is the bar START -> ts_event; ts_init = +1 bar",
        notes=tuple(notes),
    )
    return tuple(bars), report


__all__ = [
    "INTERVALS",
    "BarAdapterError",
    "BarAdapterReport",
    "step_for",
    "to_upstream_bars",
]
