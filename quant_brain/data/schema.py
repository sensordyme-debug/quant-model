"""The canonical market-data schema. One representation, declared, never inferred.

WHY THIS EXISTS
---------------
`docs/DATA_FLOW_FORENSICS.md` mapped the state before this module: four parquet files each
holding four or five spliced futures contracts, with roll gaps of +0.7% to +1.0% sitting in
the price series, and **nothing anywhere on disk saying so**. The roll rule lived as an
integer in the script that happened to fetch the data. Three separate entry points each
normalised the same file their own way. A second equity store carried its symbol in the
filename.

None of that produced a wrong published number - the loaders filter defensively and the
overnight work uses a trade-date convention that happens to align with the roll. But
"happens to" is the problem. Every one of those protections is a filter downstream of an
assumption that was never written down, and a filter cannot defend an assumption it does not
know it is making.

So: a dataset entering research must SAY what it is. Not be guessed at from its filename, not
be inferred from its symbol, not be assumed from the directory it sits in.

THE TWO THINGS THAT ARE NOT THE SAME
--------------------------------------
    instrument        ES        the economic exposure. Owns the multiplier, the tick size,
                                the tick value and the trading calendar.
    contract_symbol   ESU5      a physical deliverable with an expiry and its own liquidity,
                                its own settlement, and a price that is NOT the instrument's
                                price - it differs by carry.

Conflating them is how a +0.85% roll gap becomes a return. Both are required on every bar.

WHY THE CONSTANTS ARE PER-BAR COLUMNS
---------------------------------------
`instrument`, `bar_interval` and `timestamp_timezone` do not vary within a dataset, so
carrying them per bar looks wasteful. They are columns anyway, as `category` dtype, for one
reason: a frame that has been sliced, concatenated or merged with another dataset must still
be able to answer "what is this bar" from the bar itself. Metadata that lives only on a
wrapper object is metadata that is lost the first time someone calls `pd.concat`. The
categorical dtype makes the cost a few bytes per distinct value, not per row - measured at
447,600 rows the four constant columns add under 1 MB.
"""
from __future__ import annotations

import enum

import numpy as np
import pandas as pd

#: Bumped whenever the column set or a dtype contract changes. Recorded in every manifest
#: and in every backtest's provenance, so a result produced under an older schema is
#: identifiable as such rather than silently comparable.
SCHEMA_VERSION = "1.0.0"


class DataForm(str, enum.Enum):
    """What economic series the prices actually are. There is NO default.

    The distinction that matters for execution: `RAW` and `CONTINUOUS_UNADJUSTED` contain
    prices that were really quoted, so a fill at one of them is a fill that could have
    happened. The adjusted forms contain prices that were never quoted anywhere - they are a
    return series wearing price clothing - and filling at one is filling at a number the
    market never printed.
    """

    #: One physical contract, start to finish. The only form with no roll in it at all.
    RAW = "RAW"
    #: Contracts spliced end to end with NO price adjustment. Every price was really quoted;
    #: the series contains a jump at each roll and any return computed across one is fiction.
    CONTINUOUS_UNADJUSTED = "CONTINUOUS_UNADJUSTED"
    #: History shifted so the CURRENT contract's prices are the real ones. Returns are
    #: continuous; historical absolute prices are not what traded, and with a ratio
    #: adjustment they drift further from reality the further back you look.
    CONTINUOUS_BACK_ADJUSTED = "CONTINUOUS_BACK_ADJUSTED"
    #: The mirror: the FIRST contract's prices are real and later history is shifted. The
    #: recent end is the fictional one, which is the worse half to falsify for execution.
    CONTINUOUS_FORWARD_ADJUSTED = "CONTINUOUS_FORWARD_ADJUSTED"
    #: Anything else. Requires `data_form_description`; refused without one.
    OTHER = "OTHER"

    @property
    def is_continuous(self) -> bool:
        return self is not DataForm.RAW

    @property
    def is_adjusted(self) -> bool:
        """True when at least some prices in the series were never quoted."""
        return self in (DataForm.CONTINUOUS_BACK_ADJUSTED,
                        DataForm.CONTINUOUS_FORWARD_ADJUSTED)

    @property
    def execution_valid(self) -> bool:
        """Whether a fill may be simulated at these prices.

        `OTHER` is refused because "we do not know what this is" cannot be the basis for
        assuming a trade happened at a price. See `docs/DATA_FLOW_FORENSICS.md` and the
        FEATURE vs EXECUTION separation in `loader.py`.
        """
        return self in (DataForm.RAW, DataForm.CONTINUOUS_UNADJUSTED)


class RollMethod(str, enum.Enum):
    """How one contract hands over to the next. `UNKNOWN` is a legal value and a loud one."""

    #: No roll: the dataset is a single contract, or is not a futures series at all.
    NONE = "NONE"
    #: Roll a fixed number of calendar days before last trade date. What this repository's
    #: own store uses (`futures_fetch_multi.ROLL_DAYS = 8`).
    CALENDAR_DAYS_BEFORE_EXPIRY = "CALENDAR_DAYS_BEFORE_EXPIRY"
    #: Roll when the back month's volume first exceeds the front month's.
    VOLUME_CROSSOVER = "VOLUME_CROSSOVER"
    #: Roll when the back month's open interest first exceeds the front month's.
    OPEN_INTEREST_CROSSOVER = "OPEN_INTEREST_CROSSOVER"
    #: The provider rolled it and did not say how. Reconstruction is impossible.
    PROVIDER_DEFINED = "PROVIDER_DEFINED"
    #: Nobody knows. Distinct from PROVIDER_DEFINED: that one names a responsible party.
    UNKNOWN = "UNKNOWN"

    @property
    def reconstructible(self) -> bool:
        return self in (RollMethod.NONE, RollMethod.CALENDAR_DAYS_BEFORE_EXPIRY,
                        RollMethod.VOLUME_CROSSOVER, RollMethod.OPEN_INTEREST_CROSSOVER)


class AdjustmentMethod(str, enum.Enum):
    """How the roll gap was removed, if it was.

    DIFFERENCE and RATIO are not interchangeable and the difference is not cosmetic. A
    difference adjustment preserves POINT moves exactly and distorts percentage returns; a
    ratio adjustment preserves PERCENTAGE returns and distorts point moves. A stop placed at
    "entry minus 10 points" and a stop placed at "entry minus 0.15%" are the same stop on the
    day and different stops a year back, and which one the backtest actually used depends
    entirely on this field. `docs/ROLL_ADJUSTMENT_FORENSICS.md` measures both.
    """

    NONE = "NONE"
    #: p_adj = p + offset. Point moves preserved; returns distorted.
    DIFFERENCE = "DIFFERENCE"
    #: p_adj = p * factor. Returns preserved; point moves distorted.
    RATIO = "RATIO"
    UNKNOWN = "UNKNOWN"


# ======================================================================================
# THE COLUMN CONTRACT
# ======================================================================================

#: Required on every bar. A frame missing any one of these is not canonical and is refused.
REQUIRED_COLUMNS: tuple[str, ...] = (
    "instrument",            # ES        the economic exposure
    "contract_symbol",       # ESU5      the physical contract, "" when not applicable
    "contract_family",       # ES        the root whose terms price this bar
    "timestamp",             #           tz-aware, always stored in UTC
    "timestamp_timezone",    # UTC       stated, so a naive frame cannot masquerade
    "session_date",          #           the trading session this bar belongs to
    "bar_interval",          # 1min
    "open", "high", "low", "close", "volume",
)

#: Carried when the provider has them. Absent is a fact, not an error - but `open_interest`
#: absent means an OI-triggered roll cannot be reconstructed, and the manifest says so.
OPTIONAL_COLUMNS: tuple[str, ...] = (
    "open_interest", "bid", "ask", "bid_size", "ask_size",
)

ALL_COLUMNS: tuple[str, ...] = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

#: The constant-per-dataset columns, stored as `category` so the per-row cost is a pointer.
CATEGORICAL_COLUMNS: tuple[str, ...] = (
    "instrument", "contract_symbol", "contract_family", "timestamp_timezone",
    "bar_interval",
)

PRICE_COLUMNS: tuple[str, ...] = ("open", "high", "low", "close")


class SchemaError(ValueError):
    """A frame that is not canonical. Raised, never warned: this is a fail-closed layer."""


def validate_frame(df: pd.DataFrame, *, name: str = "dataset") -> None:
    """Refuse anything that is not a canonical frame. Structure only, not data quality.

    The split matters. THIS function answers "is this the right shape" and is cheap enough
    to run on every load. `quality.py` answers "is the content trustworthy" and is where
    duplicates, gaps and impossible bars are found. A frame can pass here and fail there;
    it cannot reach research without passing both.
    """
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise SchemaError(
            f"{name}: not a canonical frame - missing {missing}. Required columns are "
            f"{list(REQUIRED_COLUMNS)}. Build it through an adapter in "
            f"`quant_brain.data.adapters` rather than hand-assembling one; the adapter is "
            f"the only place a provider's column names are allowed to appear.")

    ts = df["timestamp"]
    if not pd.api.types.is_datetime64_any_dtype(ts):
        raise SchemaError(f"{name}: `timestamp` is {ts.dtype}, not a datetime")
    if getattr(ts.dtype, "tz", None) is None:
        raise SchemaError(
            f"{name}: `timestamp` is timezone-NAIVE. A naive timestamp is an unstated "
            f"assumption about the venue's clock, and the DST-mobile roll boundary in "
            f"docs/DATA_FLOW_FORENSICS.md is exactly what that assumption gets wrong. "
            f"Localise it in the adapter.")
    if str(ts.dtype.tz) != "UTC":
        raise SchemaError(
            f"{name}: `timestamp` is stored in {ts.dtype.tz}, not UTC. Canonical storage is "
            f"UTC and conversion to a venue clock happens at the point of use, so that one "
            f"frame cannot carry two clocks after a concat.")

    for col in PRICE_COLUMNS + ("volume",):
        if not pd.api.types.is_numeric_dtype(df[col]):
            raise SchemaError(f"{name}: `{col}` is {df[col].dtype}, not numeric")

    declared = set(df["timestamp_timezone"].astype(str).unique())
    if declared != {"UTC"}:
        raise SchemaError(
            f"{name}: `timestamp_timezone` says {sorted(declared)} but the column is stored "
            f"in UTC. The declaration and the dtype must agree - a frame that says one and "
            f"stores the other is the shape that survives review and fails in production.")

    for col in ("instrument", "bar_interval"):
        n = df[col].nunique(dropna=False)
        if n > 1:
            raise SchemaError(
                f"{name}: {n} distinct values of `{col}` in one frame "
                f"({sorted(map(str, df[col].unique()))[:5]}). A canonical frame is ONE "
                f"instrument at ONE bar interval. Concatenating two is how a multiplier "
                f"gets applied to the wrong prices.")


def empty_frame() -> pd.DataFrame:
    """A canonical frame with no rows. Useful for a provider that returned nothing."""
    cols = {c: pd.Series(dtype="object") for c in CATEGORICAL_COLUMNS}
    cols["timestamp"] = pd.Series(dtype="datetime64[ns, UTC]")
    cols["session_date"] = pd.Series(dtype="object")
    for c in PRICE_COLUMNS + ("volume",):
        cols[c] = pd.Series(dtype="float64")
    return pd.DataFrame(cols)[list(REQUIRED_COLUMNS)]


def build_frame(*, instrument: str, contract_symbol, contract_family: str,
                timestamp, session_date, bar_interval: str,
                open_, high, low, close, volume,
                open_interest=None, bid=None, ask=None,
                bid_size=None, ask_size=None, name: str = "dataset") -> pd.DataFrame:
    """Assemble a canonical frame from column arrays, then validate it.

    The ONLY supported way to make one. Adapters call this; nothing else constructs the
    columns by hand, so there is a single place where the dtypes and the ordering are
    decided and a single place a mistake can be made.
    """
    ts = pd.to_datetime(pd.Series(timestamp), utc=True)
    n = len(ts)

    def const(v):
        return pd.Series([v] * n, dtype="category")

    def series(v):
        if v is None:
            return None
        s = pd.Series(v)
        return s.astype("category") if s.dtype == object else s

    data = {
        "instrument": const(instrument),
        "contract_symbol": (const(contract_symbol)
                            if isinstance(contract_symbol, str) else series(contract_symbol)),
        "contract_family": const(contract_family),
        "timestamp": ts.reset_index(drop=True),
        "timestamp_timezone": const("UTC"),
        "session_date": pd.Series(session_date).reset_index(drop=True),
        "bar_interval": const(bar_interval),
        "open": pd.Series(open_, dtype="float64").reset_index(drop=True),
        "high": pd.Series(high, dtype="float64").reset_index(drop=True),
        "low": pd.Series(low, dtype="float64").reset_index(drop=True),
        "close": pd.Series(close, dtype="float64").reset_index(drop=True),
        "volume": pd.Series(volume, dtype="float64").reset_index(drop=True),
    }
    for key, value in (("open_interest", open_interest), ("bid", bid), ("ask", ask),
                       ("bid_size", bid_size), ("ask_size", ask_size)):
        if value is not None:
            data[key] = pd.Series(value, dtype="float64").reset_index(drop=True)

    df = pd.DataFrame(data)
    ordered = [c for c in ALL_COLUMNS if c in df.columns]
    df = df[ordered]
    validate_frame(df, name=name)
    return df


def frame_fingerprint(df: pd.DataFrame) -> str:
    """A content hash over the canonical columns, stable across column reordering.

    Not a hash of the source FILE - that is recorded separately in the manifest. This one
    answers a different question: "did the bars that reached research change", which a file
    hash cannot answer once an adapter, a filter or an adjustment sits in between.
    """
    import hashlib

    h = hashlib.sha256()
    h.update(SCHEMA_VERSION.encode())
    for col in ALL_COLUMNS:
        if col not in df.columns:
            continue
        h.update(col.encode())
        s = df[col]
        if col == "timestamp":
            # `.view` was removed from Series; astype("int64") on a tz-aware column
            # gives the UTC nanoseconds, which is the representation-independent value.
            h.update(np.ascontiguousarray(
                s.astype("int64").to_numpy(dtype="int64")).tobytes())
        elif pd.api.types.is_numeric_dtype(s):
            h.update(np.ascontiguousarray(s.to_numpy(dtype="float64")).tobytes())
        else:
            h.update("\x1f".join(map(str, s.astype(str))).encode())
    return h.hexdigest()[:16]


__all__ = ["ALL_COLUMNS", "CATEGORICAL_COLUMNS", "OPTIONAL_COLUMNS", "PRICE_COLUMNS",
           "REQUIRED_COLUMNS", "SCHEMA_VERSION", "AdjustmentMethod", "DataForm",
           "RollMethod", "SchemaError", "build_frame", "empty_frame", "frame_fingerprint",
           "validate_frame"]
