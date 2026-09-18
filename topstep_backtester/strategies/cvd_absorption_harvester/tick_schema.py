"""The tick-data contract this strategy requires, and a checker that proves it unmet.

WHY THIS IS A MODULE AND NOT A PARAGRAPH
----------------------------------------
"We do not have the data" is the most consequential claim in this whole report, and the
temptation when a dataset is *nearly* right is to bridge the gap with something reasonable.
For CVD the reasonable-looking bridge is: take the minute bar, look at whether it closed up
or down, and sign the minute's volume accordingly. That produces a number called CVD which
is not CVD - it is candle direction wearing an order-flow name - and every divergence signal
derived from it would be an artefact of the approximation rather than a fact about who was
lifting offers.

So the requirement is expressed as a machine-checkable schema. `check_dataset` reports
exactly which required fields are absent and at what granularity, and a strategy run is
gated on it. A refusal with a field list is much harder to talk yourself past than a
refusal in prose.

WHAT CVD ACTUALLY NEEDS, AND WHY EACH FIELD
-------------------------------------------
Classification is per TRADE, against the quote standing at the instant of that trade. Every
field below is load-bearing for that one sentence:

    trade timestamp   orders the trades and locates each one against a quote
    trade price       compared to bid and ask to assign the aggressor
    trade size        the magnitude of the delta; the sign is the classification
    prevailing bid    the lower comparand
    prevailing ask    the upper comparand

The previous trade price and previous delta are STATE, not columns - they are derived by
walking the trades in order, which is why a per-trade sequence is indispensable and a
per-minute aggregate cannot substitute. One bid and one ask per minute cannot tell you how
many of that minute's contracts traded at the offer, and no amount of care recovers it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

#: Fields required on EVERY trade record, with the role each plays in classification.
REQUIRED_TICK_FIELDS: dict[str, str] = {
    "timestamp": "orders the trade sequence and aligns each trade with the standing quote",
    "price": "the trade price, compared against bid and ask to assign the aggressor",
    "volume": "the traded size, which becomes the magnitude of the signed delta",
    "bid": "the prevailing bid at the instant of the trade (the lower comparand)",
    "ask": "the prevailing ask at the instant of the trade (the upper comparand)",
}

#: Derived per-trade STATE. Not columns, but impossible to maintain without a trade
#: sequence, so they are listed to make the dependency explicit.
REQUIRED_DERIVED_STATE: dict[str, str] = {
    "previous_trade_price": "needed for the inside/midpoint tick rule (PART 7 case 3)",
    "previous_delta": "needed for the zero-tick rule, where price did not change",
}

#: The coarsest granularity at which per-trade classification is still meaningful. A feed
#: whose minimum inter-record gap is larger than this is an aggregate, not a trade sequence.
#: One second is already generous - real ES prints arrive in bursts within a millisecond.
MAX_USABLE_GAP_SECONDS = 1.0


@dataclass(frozen=True)
class FieldFinding:
    field_name: str
    present: bool
    role: str
    note: str = ""


@dataclass(frozen=True)
class TickDataVerdict:
    """Whether a dataset can support CVD, and precisely why not when it cannot."""

    source: str
    rows: int
    columns: tuple[str, ...]
    fields: tuple[FieldFinding, ...]
    min_gap_seconds: float | None
    modal_gap_seconds: float | None
    simultaneous_stamps: int
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def missing_fields(self) -> tuple[str, ...]:
        return tuple(f.field_name for f in self.fields if not f.present)

    @property
    def granularity_ok(self) -> bool:
        if self.min_gap_seconds is None:
            return False
        return self.min_gap_seconds <= MAX_USABLE_GAP_SECONDS

    @property
    def satisfied(self) -> bool:
        return not self.missing_fields and self.granularity_ok

    def summary(self) -> str:
        if self.satisfied:
            return (
                f"{self.source}: TICK DATA REQUIREMENT SATISFIED - {self.rows:,} trade "
                f"records, minimum gap {self.min_gap_seconds}s"
            )
        parts = [f"{self.source}: TICK DATA REQUIREMENT NOT SATISFIED"]
        if self.missing_fields:
            parts.append(f"missing required fields: {list(self.missing_fields)}")
        if not self.granularity_ok:
            parts.append(
                f"granularity is an aggregate, not a trade sequence "
                f"(minimum gap {self.min_gap_seconds}s, modal gap "
                f"{self.modal_gap_seconds}s, simultaneous stamps "
                f"{self.simultaneous_stamps}); per-trade classification needs a minimum gap "
                f"of {MAX_USABLE_GAP_SECONDS}s or less and many simultaneous prints"
            )
        return " | ".join(parts)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "rows": self.rows,
            "columns": list(self.columns),
            "satisfied": self.satisfied,
            "missing_fields": list(self.missing_fields),
            "granularity_ok": self.granularity_ok,
            "min_gap_seconds": self.min_gap_seconds,
            "modal_gap_seconds": self.modal_gap_seconds,
            "simultaneous_stamps": self.simultaneous_stamps,
            "fields": [
                {"field": f.field_name, "present": f.present, "role": f.role, "note": f.note}
                for f in self.fields
            ],
            "notes": list(self.notes),
        }


#: Column spellings that count as each required field. Deliberately explicit: guessing that
#: an unfamiliar column is the bid is how a spread series gets classified as a quote.
_ALIASES: dict[str, tuple[str, ...]] = {
    "timestamp": ("timestamp", "t", "time", "ts", "datetime", "dt"),
    "price": ("price", "trade_price", "last", "last_price", "px"),
    "volume": ("volume", "size", "trade_size", "last_size", "qty", "quantity", "v"),
    "bid": ("bid", "bid_price", "bidprice", "bid_px"),
    "ask": ("ask", "ask_price", "askprice", "ask_px"),
}


def _resolve(columns: set[str], canonical: str) -> str | None:
    for alias in _ALIASES[canonical]:
        if alias in columns:
            return alias
    return None


def check_frame(frame: pd.DataFrame, *, source: str) -> TickDataVerdict:
    """Judge an in-memory frame against the tick contract."""
    lowered = {str(c).lower(): str(c) for c in frame.columns}
    available = set(lowered)

    findings: list[FieldFinding] = []
    notes: list[str] = []
    for canonical, role in REQUIRED_TICK_FIELDS.items():
        alias = _resolve(available, canonical)
        findings.append(
            FieldFinding(
                field_name=canonical,
                present=alias is not None,
                role=role,
                note=f"found as {alias!r}" if alias else "no column of any accepted spelling",
            )
        )

    min_gap = modal_gap = None
    simultaneous = 0
    stamp_alias = _resolve(available, "timestamp")
    if stamp_alias is not None:
        stamps = pd.to_datetime(frame[lowered[stamp_alias]], errors="coerce").dropna()
        if len(stamps) >= 3:
            #: as_unit("ns") FIRST - pandas 3.0 stores datetime64[us] and astype("int64")
            #: returns the column's own unit, which would make a 60-second grid read as a
            #: 0.06-second tick feed. See topstep_backtester/adapters/bars.py::_epoch_ns.
            ordered = stamps.sort_values().dt.as_unit("ns").astype("int64").to_numpy()
            gaps = (ordered[1:] - ordered[:-1]) / 1e9
            positive = gaps[gaps > 0]
            simultaneous = int((gaps == 0).sum())
            if positive.size:
                min_gap = float(positive.min())
                modal_gap = float(pd.Series(positive).mode().iloc[0])
        else:
            notes.append("fewer than three usable timestamps; granularity undetermined")

    if simultaneous == 0 and min_gap is not None and min_gap >= 1.0:
        notes.append(
            "no two records share a timestamp. A real ES trade feed has many simultaneous "
            "prints, so this is a resampled grid rather than a trade sequence."
        )

    return TickDataVerdict(
        source=source,
        rows=len(frame),
        columns=tuple(str(c) for c in frame.columns),
        fields=tuple(findings),
        min_gap_seconds=min_gap,
        modal_gap_seconds=modal_gap,
        simultaneous_stamps=simultaneous,
        notes=tuple(notes),
    )


def check_parquet(path: Path | str) -> TickDataVerdict:
    """Judge a parquet file on disk."""
    path = Path(path)
    return check_frame(pd.read_parquet(path), source=path.as_posix())


class TickDataUnavailable(RuntimeError):
    """The dataset cannot support CVD. Raised instead of approximating."""


def require_tick_data(verdict: TickDataVerdict) -> None:
    """Gate a historical run. Never downgraded to a warning."""
    if not verdict.satisfied:
        raise TickDataUnavailable(
            f"{verdict.summary()}\n"
            f"CVD cannot be approximated from this data. Signing a minute bar's volume by "
            f"its candle direction produces a series that looks like CVD and is not, and "
            f"every divergence signal from it would be an artefact of the approximation. "
            f"The historical backtest is BLOCKED until a genuine trade-and-quote feed is "
            f"supplied."
        )


__all__ = [
    "MAX_USABLE_GAP_SECONDS",
    "REQUIRED_DERIVED_STATE",
    "REQUIRED_TICK_FIELDS",
    "FieldFinding",
    "TickDataUnavailable",
    "TickDataVerdict",
    "check_frame",
    "check_parquet",
    "require_tick_data",
]
