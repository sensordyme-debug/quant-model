"""Provider adapters. The ONLY layer allowed to know a vendor's column names.

THE RULE
--------
Everything upstream of an adapter is a provider's problem: `t` versus `date` versus
`timestamp`, a symbol in a column versus a symbol in the filename, volume as int64 versus
float64, one contract per file versus five spliced into one. Everything downstream sees the
canonical schema and nothing else.

`tests/test_canonical_data.py::test_no_provider_column_name_escapes_the_adapter_layer`
enforces it by grepping the rest of the layer for the provider spellings.

WHAT AN ADAPTER MUST DO
-------------------------
1. read the source, however the provider shaped it
2. produce a canonical frame through `schema.build_frame`, never by hand
3. produce a `DatasetManifest` that DECLARES the representation - and the adapter must know
   what it is declaring, from the fetch parameters, not from the filename

An adapter that cannot determine the data form REFUSES. It does not guess, and it does not
default to the least alarming option.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from quant_brain.data import contracts as C
from quant_brain.data.manifest import (
    DatasetManifest,
    RollSpec,
    hash_file,
    utc_now_iso,
)
from quant_brain.data.schema import AdjustmentMethod, DataForm, RollMethod, build_frame

#: The session clock the US equity-index complex is researched on. Declared per dataset, not
#: assumed globally - `docs/DATA_FLOW_FORENSICS.md` FINDING 1 is a boundary that moved
#: underneath an assumed clock.
US_EQUITY_INDEX_TZ = "America/New_York"

#: This repository's own futures store: how it was actually built. Sourced from
#: `scripts/futures_fetch_multi.py`, which is the script that wrote the files.
IBKR_FUTURES_ROLL_DAYS = 8
IBKR_FUTURES_CHAINS: dict[str, tuple[str, ...]] = {
    "ES": ("ESU5", "ESZ5", "ESH6", "ESM6", "ESU6"),
    "NQ": ("NQU5", "NQZ5", "NQH6", "NQM6", "NQU6"),
    "MES": ("MESZ5", "MESH6", "MESM6", "MESU6"),
    "MNQ": ("MNQZ5", "MNQH6", "MNQM6", "MNQU6"),
}


class AdapterError(ValueError):
    """A source this adapter cannot read into the canonical schema without guessing."""


def _session_date_from_trade_day(ts_utc: pd.Series, tz: str) -> pd.Series:
    """The calendar date of the session a bar belongs to, on the venue clock.

    Deliberately the LOCAL CALENDAR DATE and not a futures trade date. A trade date shifts
    the evening session onto the next day and is the right convention for overnight work,
    but it is a research decision with real content - `overnight_panel` makes it explicitly
    and says why. Baking it in here would apply it to callers who never asked for it.
    """
    return ts_utc.dt.tz_convert(tz).dt.date


# ======================================================================================
# IBKR FUTURES - data/futures/{ES,NQ,MES,MNQ}.parquet
# ======================================================================================

def ibkr_futures(path: Path, *, instrument: str, tz: str = US_EQUITY_INDEX_TZ,
                 dataset_id: str | None = None) -> tuple[pd.DataFrame, DatasetManifest]:
    """The store this repository already has: contracts spliced, unadjusted.

    The representation is NOT inferred from the file. It is declared here because
    `scripts/futures_fetch_multi.py` is the script that wrote it and its behaviour is known:
    it fetches each contract separately over a window that ends `ROLL_DAYS = 8` days before
    that contract's last trade date, then concatenates them with **no price adjustment**.
    The `contract` column is preserved per bar, so the raw legs are recoverable and the
    series is `reconstructible`.

    Measured consequence, in the file right now: roll gaps of +0.71% to +1.03% on ES and up
    to +1.03% on NQ. Any return computed across one is fiction, which is why the form is
    CONTINUOUS_UNADJUSTED and not something quieter.
    """
    path = Path(path)
    if not path.exists():
        raise AdapterError(f"no such file: {path}. The adapter fails closed rather than "
                           f"substituting a proxy instrument.")
    raw = pd.read_parquet(path)

    expected = {"t", "o", "h", "l", "c", "v", "contract"}
    missing = expected - set(raw.columns)
    if missing:
        raise AdapterError(
            f"{path.name}: missing {sorted(missing)}. This adapter reads the IBKR futures "
            f"layout (t,o,h,l,c,v,contract). A file without `contract` cannot state which "
            f"physical contract a bar belongs to, and every roll and session guarantee in "
            f"this layer rests on that column.")

    raw = raw.sort_values("t").reset_index(drop=True)
    ts = pd.to_datetime(raw["t"], utc=True)
    symbols = raw["contract"].astype(str)

    families = {C.family_of(s) for s in symbols.unique()}
    if len(families) != 1:
        raise AdapterError(
            f"{path.name}: contracts resolve to {sorted(families)} - more than one root in "
            f"one file. A canonical frame is one instrument.")
    family = families.pop()
    if family != instrument:
        raise AdapterError(
            f"{path.name}: caller says instrument={instrument!r} but the contracts are "
            f"{family!r} ({sorted(symbols.unique())[:3]}...). Refusing rather than trusting "
            f"one over the other.")

    frame = build_frame(
        instrument=instrument, contract_symbol=symbols, contract_family=family,
        timestamp=ts, session_date=_session_date_from_trade_day(ts, tz),
        bar_interval="1min", open_=raw["o"], high=raw["h"], low=raw["l"], close=raw["c"],
        volume=raw["v"], name=path.name)

    present = list(dict.fromkeys(symbols))            # order of appearance
    declared = IBKR_FUTURES_CHAINS.get(instrument)
    notes: list[str] = []
    if declared is not None and tuple(present) != declared:
        notes.append(f"chain in file {present} differs from the fetch script's declared "
                     f"chain {list(declared)}")
    contiguous, why = C.is_contiguous_chain(present)
    if not contiguous:
        notes.append(f"chain is not contiguous: {why}")

    changes = frame["contract_symbol"].astype(str)
    roll_ts = tuple(str(t) for t in
                    frame.loc[changes.ne(changes.shift()) & (frame.index > 0),
                              "timestamp"])

    manifest = DatasetManifest(
        dataset_id=dataset_id or f"ibkr-{instrument}-1min",
        provider="IBKR", instrument=instrument, contract_family=family,
        data_form=DataForm.CONTINUOUS_UNADJUSTED,
        roll=RollSpec(
            method=RollMethod.CALENDAR_DAYS_BEFORE_EXPIRY,
            adjustment=AdjustmentMethod.NONE,
            days_before_expiry=IBKR_FUTURES_ROLL_DAYS,
            contracts=tuple(present), roll_timestamps=roll_ts,
            volume_handling="carried: each contract keeps its own volume; nothing is summed "
                            "across the splice",
            open_interest_handling="absent: IBKR historical bars carry no open interest, so "
                                   "an OI-triggered roll cannot be reproduced from this store",
            reconstructible=True),
        bar_interval="1min", timezone="UTC", session_timezone=tz,
        coverage_start=str(frame["timestamp"].iloc[0]),
        coverage_end=str(frame["timestamp"].iloc[-1]),
        bars=len(frame), sessions=int(frame["session_date"].nunique()),
        source_files=(str(path),), source_hashes=(hash_file(path),),
        canonicalized_at=utc_now_iso(), adapter="ibkr_futures",
        adapter_params={"roll_days": IBKR_FUTURES_ROLL_DAYS, "session_timezone": tz},
        notes=tuple(notes))
    return frame, manifest


def ibkr_futures_single_contract(path: Path, *, instrument: str, contract_symbol: str,
                                 tz: str = US_EQUITY_INDEX_TZ
                                 ) -> tuple[pd.DataFrame, DatasetManifest]:
    """One contract out of the spliced store, as a first-class RAW dataset.

    This is what "raw contracts are first-class" means in practice: the store holds them, so
    they can be extracted and used as `DataForm.RAW` - a series with no roll in it anywhere,
    which is the only form where price continuity needs no argument at all.
    """
    frame, base = ibkr_futures(path, instrument=instrument, tz=tz)
    sub = frame[frame["contract_symbol"].astype(str) == contract_symbol]
    if sub.empty:
        have = sorted(frame["contract_symbol"].astype(str).unique())
        raise AdapterError(f"{contract_symbol!r} is not in {Path(path).name}; it holds {have}")
    sub = sub.reset_index(drop=True)
    code = C.parse(contract_symbol)

    manifest = DatasetManifest(
        dataset_id=f"ibkr-{contract_symbol}-1min",
        provider="IBKR", instrument=instrument, contract_family=code.root,
        data_form=DataForm.RAW, roll=RollSpec.none(),
        bar_interval="1min", timezone="UTC", session_timezone=tz,
        coverage_start=str(sub["timestamp"].iloc[0]),
        coverage_end=str(sub["timestamp"].iloc[-1]),
        bars=len(sub), sessions=int(sub["session_date"].nunique()),
        source_files=base.source_files, source_hashes=base.source_hashes,
        canonicalized_at=utc_now_iso(), adapter="ibkr_futures_single_contract",
        adapter_params={"contract_symbol": contract_symbol, "session_timezone": tz},
        notes=(f"extracted from the spliced store {Path(path).name}; this is the {code.year}-"
               f"{code.month:02d} contract only and contains no roll",))
    return sub, manifest


# ======================================================================================
# ALPACA EQUITY MINUTE - data/minute_alpaca/<SYMBOL>.parquet
# ======================================================================================

def alpaca_equity_minute(path: Path, *, symbol: str | None = None,
                         tz: str = US_EQUITY_INDEX_TZ
                         ) -> tuple[pd.DataFrame, DatasetManifest]:
    """The equity store: a DatetimeIndex named `date`, columns o/h/l/c/v, symbol in the
    FILENAME.

    The filename-as-symbol is why `symbol` is an argument. It defaults to the file stem
    because that is what the store means, but a caller who knows better can say so, and the
    manifest records which of the two was used - a symbol carried by a filesystem path is a
    symbol that a copy or a rename silently changes.

    An equity series has no contract, so `contract_symbol` is empty and the form is RAW:
    there is no roll and nothing was adjusted. NOTE that this says nothing about corporate
    actions - see the manifest note.
    """
    path = Path(path)
    if not path.exists():
        raise AdapterError(f"no such file: {path}")
    raw = pd.read_parquet(path)
    sym = symbol or path.stem
    if not sym:
        raise AdapterError(f"cannot determine a symbol for {path}")

    if isinstance(raw.index, pd.DatetimeIndex):
        ts = pd.to_datetime(raw.index.to_series(), utc=True).reset_index(drop=True)
        raw = raw.reset_index(drop=True)
    elif "date" in raw.columns:
        ts = pd.to_datetime(raw["date"], utc=True)
    elif "t" in raw.columns:
        ts = pd.to_datetime(raw["t"], utc=True)
    else:
        raise AdapterError(
            f"{path.name}: no DatetimeIndex and no `date`/`t` column. This adapter will not "
            f"guess which column is time.")

    missing = {"o", "h", "l", "c", "v"} - set(raw.columns)
    if missing:
        raise AdapterError(f"{path.name}: missing {sorted(missing)}")

    frame = build_frame(
        instrument=sym, contract_symbol="", contract_family=sym,
        timestamp=ts, session_date=_session_date_from_trade_day(ts, tz),
        bar_interval="1min", open_=raw["o"], high=raw["h"], low=raw["l"], close=raw["c"],
        volume=raw["v"], name=path.name)

    manifest = DatasetManifest(
        dataset_id=f"alpaca-{sym}-1min", provider="Alpaca", instrument=sym,
        contract_family=sym, data_form=DataForm.RAW, roll=RollSpec.none(),
        bar_interval="1min", timezone="UTC", session_timezone=tz,
        coverage_start=str(frame["timestamp"].iloc[0]),
        coverage_end=str(frame["timestamp"].iloc[-1]),
        bars=len(frame), sessions=int(frame["session_date"].nunique()),
        source_files=(str(path),), source_hashes=(hash_file(path),),
        canonicalized_at=utc_now_iso(), adapter="alpaca_equity_minute",
        adapter_params={"symbol_source": "argument" if symbol else "filename",
                        "session_timezone": tz},
        notes=("RAW here means no futures roll and no roll adjustment. It does NOT assert "
               "anything about corporate actions: whether this series is split- and "
               "dividend-adjusted is a property of the Alpaca feed that this adapter cannot "
               "verify from the file, and a strategy sensitive to absolute price levels "
               "must establish it separately.",))
    return frame, manifest


# ======================================================================================
# GENERIC - anything, provided the caller declares what it is
# ======================================================================================

def generic_table(path: Path, *, instrument: str, data_form: DataForm,
                  roll: RollSpec, session_timezone: str, bar_interval: str,
                  columns: dict[str, str], provider: str = "unknown",
                  contract_family: str | None = None,
                  data_form_description: str = "",
                  dataset_id: str | None = None) -> tuple[pd.DataFrame, DatasetManifest]:
    """A CSV or parquet from anywhere, with the caller declaring every ambiguous thing.

    `columns` maps CANONICAL name -> the provider's spelling, e.g.
    `{"timestamp": "ts", "open": "Open", ...}`. Every required field must be mapped or
    supplied; nothing is matched by fuzzy name, because a fuzzy match between `close` and
    `adj_close` is exactly how an adjusted series becomes an execution source.

    There is no default `data_form`. That is the point of the whole module.
    """
    path = Path(path)
    if not path.exists():
        raise AdapterError(f"no such file: {path}")
    if not isinstance(data_form, DataForm):
        raise AdapterError(
            "generic_table requires an explicit DataForm. A dataset whose representation "
            "nobody will state cannot enter research; that is the rule this layer exists "
            "to enforce.")
    raw = (pd.read_csv(path) if path.suffix.lower() == ".csv" else pd.read_parquet(path))

    need = ("timestamp", "open", "high", "low", "close", "volume")
    unmapped = [k for k in need if k not in columns]
    if unmapped:
        raise AdapterError(
            f"{path.name}: no column mapping for {unmapped}. Map every one explicitly - "
            f"guessing between `close` and `adj_close` is how an adjusted series becomes "
            f"an execution price.")
    absent = [v for v in columns.values() if v not in raw.columns]
    if absent:
        raise AdapterError(f"{path.name}: mapped columns {absent} are not in the file "
                           f"(it has {list(raw.columns)})")

    ts = pd.to_datetime(raw[columns["timestamp"]], utc=True)
    csym = raw[columns["contract_symbol"]].astype(str) if "contract_symbol" in columns else ""
    fam = contract_family or instrument

    optional = {}
    for key in ("open_interest", "bid", "ask", "bid_size", "ask_size"):
        if key in columns:
            optional[key] = raw[columns[key]]

    frame = build_frame(
        instrument=instrument, contract_symbol=csym, contract_family=fam,
        timestamp=ts, session_date=_session_date_from_trade_day(ts, session_timezone),
        bar_interval=bar_interval, open_=raw[columns["open"]], high=raw[columns["high"]],
        low=raw[columns["low"]], close=raw[columns["close"]],
        volume=raw[columns["volume"]], name=path.name, **optional)

    manifest = DatasetManifest(
        dataset_id=dataset_id or f"{provider}-{instrument}-{bar_interval}",
        provider=provider, instrument=instrument, contract_family=fam,
        data_form=data_form, roll=roll, bar_interval=bar_interval, timezone="UTC",
        session_timezone=session_timezone,
        coverage_start=str(frame["timestamp"].iloc[0]),
        coverage_end=str(frame["timestamp"].iloc[-1]),
        bars=len(frame), sessions=int(frame["session_date"].nunique()),
        source_files=(str(path),), source_hashes=(hash_file(path),),
        canonicalized_at=utc_now_iso(), adapter="generic_table",
        adapter_params={"columns": dict(columns), "session_timezone": session_timezone},
        data_form_description=data_form_description)
    return frame, manifest


#: Every adapter, by name. `loader.py` dispatches through this so a caller never imports a
#: provider module directly and the set of supported providers is enumerable.
ADAPTERS = {
    "ibkr_futures": ibkr_futures,
    "ibkr_futures_single_contract": ibkr_futures_single_contract,
    "alpaca_equity_minute": alpaca_equity_minute,
    "generic_table": generic_table,
}


def available() -> list[str]:
    return sorted(ADAPTERS)


__all__ = ["ADAPTERS", "IBKR_FUTURES_CHAINS", "IBKR_FUTURES_ROLL_DAYS",
           "US_EQUITY_INDEX_TZ", "AdapterError", "alpaca_equity_minute", "available",
           "generic_table", "ibkr_futures", "ibkr_futures_single_contract"]
