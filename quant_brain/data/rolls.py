"""Roll detection and price adjustment. The two are kept apart on purpose.

DETECTION is a measurement: where did the contract change, and how big was the gap. It reads
the data and asserts nothing.

ADJUSTMENT is a transformation that produces prices **that were never quoted**. Every function
below that does one says so, records exactly what it did, and stamps the result so it cannot
be done twice.

WHY DIFFERENCE AND RATIO ARE NOT INTERCHANGEABLE
--------------------------------------------------
Both remove the roll gap. They preserve different things, and which one a backtest used
changes results that have nothing to do with the roll:

    DIFFERENCE   p' = p + offset
                 point moves preserved EXACTLY. h-l is unchanged, so ATR in points is
                 unchanged, so a stop at "entry - 1 ATR" is the same stop.
                 percentage returns distorted: a 10-point move on a shifted-down 5000 is a
                 different percentage than on the 5055 that traded.
                 CAN GO NEGATIVE on a long enough history of upward rolls.

    RATIO        p' = p * factor
                 percentage returns preserved EXACTLY.
                 point moves distorted: h-l scales, so ATR in points scales, so a stop at
                 "entry - 1 ATR" is a DIFFERENT NUMBER OF POINTS than the one that would
                 have been placed at the time - and P&L is in points times a multiplier.
                 breaks the tick grid: an adjusted price is generally not a multiple of
                 0.25, so a stop "at 3990" is at a price no order could rest on.

A strategy whose rules are in points is distorted by RATIO. A strategy whose rules are in
percent is distorted by DIFFERENCE. There is no adjustment that distorts neither, which is
why `DataForm.execution_valid` refuses both for fills.

`docs/ROLL_ADJUSTMENT_FORENSICS.md` measures every one of those distortions on this
repository's own store.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from quant_brain.data.schema import PRICE_COLUMNS, AdjustmentMethod, DataForm, validate_frame

#: Price-bearing columns an adjustment must touch. Quotes are prices too: adjusting the
#: trade prices and leaving the bid/ask alone manufactures a spread that grows with the
#: cumulative offset, which is a cost model built out of an accounting error.
ADJUSTABLE_COLUMNS: tuple[str, ...] = (*PRICE_COLUMNS, "bid", "ask")


class RollError(ValueError):
    """A roll operation that would produce a series nobody could interpret."""


@dataclass(frozen=True)
class RollEvent:
    """One observed contract change. Measured from the bars, not from a rule."""

    index: int                     # row index of the FIRST bar of the new contract
    timestamp: pd.Timestamp
    from_contract: str
    to_contract: str
    last_close: float
    first_open: float
    #: The gap the splice put in the series: the new contract's first OPEN against the old
    #: contract's last CLOSE. Opens rather than closes on the new side, because that is the
    #: first price the new contract actually printed.
    gap_points: float
    gap_pct: float
    #: Bars between the old contract's last bar and the new one's first. A splice with no
    #: overlap and no hole has exactly one interval here.
    bars_between: int

    def as_row(self) -> dict:
        return {"index": self.index, "timestamp": self.timestamp,
                "from_contract": self.from_contract, "to_contract": self.to_contract,
                "last_close": self.last_close, "first_open": self.first_open,
                "gap_points": self.gap_points, "gap_pct": self.gap_pct,
                "bars_between": self.bars_between}


def detect_rolls(df: pd.DataFrame) -> list[RollEvent]:
    """Every point in a canonical frame where `contract_symbol` changes.

    Measured, never assumed from a calendar rule. If the rule and the data disagree - a
    provider rolled a day early, a chain skipped an expiry - this reports what the DATA did,
    which is the thing the backtest actually consumed.
    """
    validate_frame(df, name="roll detection")
    if df.empty:
        return []
    sym = df["contract_symbol"].astype(str).to_numpy()
    ts = df["timestamp"].to_numpy()
    close = df["close"].to_numpy(dtype=float)
    open_ = df["open"].to_numpy(dtype=float)

    out: list[RollEvent] = []
    changes = np.flatnonzero(sym[1:] != sym[:-1]) + 1
    for i in changes:
        last_c, first_o = float(close[i - 1]), float(open_[i])
        step = pd.Timestamp(ts[i]) - pd.Timestamp(ts[i - 1])
        out.append(RollEvent(
            index=int(i), timestamp=pd.Timestamp(ts[i]),
            from_contract=sym[i - 1], to_contract=sym[i],
            last_close=last_c, first_open=first_o,
            gap_points=first_o - last_c,
            gap_pct=(first_o / last_c - 1.0) * 100.0 if last_c else float("nan"),
            bars_between=int(step / pd.Timedelta(minutes=1)) if step else 0))
    return out


def roll_table(df: pd.DataFrame) -> pd.DataFrame:
    """`detect_rolls` as a frame, for a report or a manifest."""
    events = detect_rolls(df)
    return pd.DataFrame([e.as_row() for e in events]) if events else pd.DataFrame(
        columns=["index", "timestamp", "from_contract", "to_contract", "last_close",
                 "first_open", "gap_points", "gap_pct", "bars_between"])


def contract_spans(df: pd.DataFrame) -> pd.DataFrame:
    """First and last bar of every contract present, in order of appearance.

    Used to detect the thing a `groupby` would hide: a contract that appears, disappears and
    comes back. That is not a chain, it is interleaved data, and a roll ordering computed
    over it is meaningless.
    """
    validate_frame(df, name="contract spans")
    sym = df["contract_symbol"].astype(str)
    block = (sym != sym.shift()).cumsum()
    g = df.assign(_b=block).groupby("_b", sort=True)
    rows = []
    for _, sub in g:
        rows.append({"contract_symbol": str(sub["contract_symbol"].iloc[0]),
                     "start": sub["timestamp"].iloc[0], "end": sub["timestamp"].iloc[-1],
                     "bars": len(sub)})
    out = pd.DataFrame(rows)
    if not out.empty:
        counts = out["contract_symbol"].value_counts()
        out["appears_n_times"] = out["contract_symbol"].map(counts)
    return out


# ======================================================================================
# ADJUSTMENT
# ======================================================================================

@dataclass(frozen=True)
class AdjustmentResult:
    """An adjusted frame and the complete record of what was done to it.

    The offsets ARE the audit trail. Given the original and this table, the adjustment is
    reversible and reproducible; without it, an adjusted series is a set of numbers with no
    provenance.
    """

    frame: pd.DataFrame
    method: AdjustmentMethod
    data_form: DataForm
    #: One entry per contract span, in order: the additive offset or multiplicative factor
    #: applied to every bar of that span.
    offsets: pd.DataFrame
    #: The roll events measured BEFORE adjustment.
    rolls: list[RollEvent]
    #: True when at least one adjusted price fell at or below zero. A back-adjusted series
    #: on a long enough history of upward rolls WILL do this, and a negative futures price
    #: breaks every percentage, every log return and every ratio downstream.
    produced_non_positive: bool
    #: How far the adjusted prices sit off the instrument's tick grid. Zero for a difference
    #: adjustment whose gaps are whole ticks; generally non-zero for a ratio adjustment.
    max_tick_grid_error: float


def _apply(values: np.ndarray, spans: list[tuple[int, int]], factors: np.ndarray,
           method: AdjustmentMethod) -> np.ndarray:
    out = values.astype(float).copy()
    for (lo, hi), f in zip(spans, factors, strict=True):
        if method is AdjustmentMethod.DIFFERENCE:
            out[lo:hi] += f
        else:
            out[lo:hi] *= f
    return out


def adjust(df: pd.DataFrame, *, method: AdjustmentMethod, direction: str = "back",
           tick_size: float | None = None,
           source_form: DataForm = DataForm.CONTINUOUS_UNADJUSTED) -> AdjustmentResult:
    """Remove the roll gaps, and record exactly how.

    `direction` "back" leaves the LAST contract's prices untouched and shifts history;
    "forward" leaves the FIRST contract's prices untouched and shifts everything after it.

    REFUSES to adjust anything that is not `CONTINUOUS_UNADJUSTED`. That single guard is the
    whole defence against double adjustment: an already-adjusted frame has gaps of zero, so
    re-running this would silently be a no-op and a *stored* offset table applied twice
    would not. Making the source form an argument that must be declared means the second
    application has to lie about what it is holding.
    """
    if direction not in ("back", "forward"):
        raise RollError(f"direction must be 'back' or 'forward', got {direction!r}")
    if method is AdjustmentMethod.NONE:
        raise RollError("AdjustmentMethod.NONE is not an adjustment; do not call adjust()")
    if method is AdjustmentMethod.UNKNOWN:
        raise RollError(
            "AdjustmentMethod.UNKNOWN cannot be APPLIED - it is a statement that somebody "
            "else adjusted a series and did not say how.")
    if source_form is not DataForm.CONTINUOUS_UNADJUSTED:
        raise RollError(
            f"refusing to adjust a {source_form.value} series. Adjustment is only defined "
            f"on CONTINUOUS_UNADJUSTED input: a RAW single contract has no roll to remove, "
            f"and an already-adjusted series would be DOUBLE ADJUSTED - which is invisible "
            f"afterwards, because the second pass measures gaps of zero and changes "
            f"nothing while a stored offset table would shift it twice.")

    validate_frame(df, name="adjustment input")
    rolls = detect_rolls(df)
    spans_df = contract_spans(df)
    if not spans_df.empty and (spans_df["appears_n_times"] > 1).any():
        repeated = sorted(spans_df.loc[spans_df["appears_n_times"] > 1,
                                       "contract_symbol"].unique())
        raise RollError(
            f"contracts {repeated} appear in more than one block, so this is interleaved "
            f"data rather than a chain. Adjusting it would apply one contract two different "
            f"offsets.")

    n = len(df)
    sym = df["contract_symbol"].astype(str).to_numpy()
    bounds = [0, *[e.index for e in rolls], n]
    spans = [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]

    # The per-roll gap, as an offset (difference) or a factor (ratio).
    if method is AdjustmentMethod.DIFFERENCE:
        step = np.array([e.gap_points for e in rolls], dtype=float)
        identity = 0.0
    else:
        step = np.array([(e.first_open / e.last_close) if e.last_close else np.nan
                         for e in rolls], dtype=float)
        identity = 1.0

    factors = np.full(len(spans), identity, dtype=float)
    if rolls:
        if direction == "back":
            # span k must be lifted by every gap that happens AFTER it, so the LAST span
            # gets the identity and earlier spans accumulate backwards.
            for k in range(len(spans) - 2, -1, -1):
                factors[k] = (factors[k + 1] + step[k]
                              if method is AdjustmentMethod.DIFFERENCE
                              else factors[k + 1] * step[k])
        else:
            # the FIRST span keeps the identity; each later span is pushed back by the gaps
            # that happened before it.
            for k in range(1, len(spans)):
                factors[k] = (factors[k - 1] - step[k - 1]
                              if method is AdjustmentMethod.DIFFERENCE
                              else factors[k - 1] / step[k - 1])

    out = df.copy()
    for col in ADJUSTABLE_COLUMNS:
        if col in out.columns:
            out[col] = _apply(out[col].to_numpy(dtype=float), spans, factors, method)

    prices = out[list(PRICE_COLUMNS)].to_numpy(dtype=float)
    non_positive = bool(np.nanmin(prices) <= 0) if prices.size else False

    grid_error = 0.0
    if tick_size:
        rem = np.abs(np.remainder(prices, tick_size))
        grid_error = float(np.nanmax(np.minimum(rem, tick_size - rem))) if rem.size else 0.0

    form = (DataForm.CONTINUOUS_BACK_ADJUSTED if direction == "back"
            else DataForm.CONTINUOUS_FORWARD_ADJUSTED)
    offsets = pd.DataFrame({
        "contract_symbol": [sym[lo] for lo, _ in spans],
        "start_index": [lo for lo, _ in spans],
        "end_index": [hi for _, hi in spans],
        "bars": [hi - lo for lo, hi in spans],
        ("offset" if method is AdjustmentMethod.DIFFERENCE else "factor"): factors,
    })
    return AdjustmentResult(frame=out, method=method, data_form=form, offsets=offsets,
                            rolls=rolls, produced_non_positive=non_positive,
                            max_tick_grid_error=grid_error)


def residual_gaps(df: pd.DataFrame) -> pd.DataFrame:
    """The roll gaps that remain after an adjustment. Should be ~0; reported, not assumed."""
    return roll_table(df)


def gap_free(df: pd.DataFrame, *, tolerance: float = 1e-9) -> tuple[bool, float]:
    """Is every roll gap within tolerance of zero? Returns (verdict, worst absolute gap)."""
    events = detect_rolls(df)
    if not events:
        return True, 0.0
    worst = max(abs(e.gap_points) for e in events)
    return worst <= tolerance, worst


__all__ = ["ADJUSTABLE_COLUMNS", "AdjustmentResult", "RollError", "RollEvent", "adjust",
           "contract_spans", "detect_rolls", "gap_free", "residual_gaps", "roll_table"]
