"""THE ADAPTER: canonical market data -> the session frames the strategy backtester consumes.

    CANONICAL DATA  (quant_brain.data: adapter -> schema -> quality gate -> manifest)
          |
          |   this module, and nothing else
          v
    STRATEGY BACKTESTER  (ledger_builder -> canonical_ledger -> account_result)

WHY AN ADAPTER AND NOT A REWRITE
----------------------------------
`scripts/futures_discover.py` reads `data/futures/*.parquet` directly. It applies a session
window, a one-contract-per-session filter and a completeness filter, and it does all three on
provider column names (`t,o,h,l,c,v,contract`) with no statement anywhere of what the price
series IS. That path produced every published futures number in this repository, so it is not
being deleted and it is not being edited: it is being made ONE OF TWO, with this module as the
other, and an equivalence run (`scripts/canonical_equivalence.py`) standing between them.

What changes when a run goes through here: the bars arrive having passed the canonical schema
check and the canonical quality gate, carrying a manifest that states the data form, the roll
method, the adjustment method and the venue clock - and the run refuses outright if the series
is not execution-valid. What does NOT change: the bars themselves, their order, their dtypes,
or a single downstream line of arithmetic. The frames this module hands out are comparable
column by column with the ones `futures_discover` hands out, which is the property the
equivalence run asserts.

THE THREE FILTERS, STATED ONCE
--------------------------------
Both paths apply the same three, in the same order. They are restated here rather than
imported from `futures_discover` because importing them would make "the two paths agree" a
tautology instead of a measurement. The equivalence run is what keeps them honest.

  1. WINDOW           keep bars whose venue-clock time is within [open_et, close_et].
  2. ONE CONTRACT     drop any session whose bars span more than one physical contract. A
                      session built from two contracts prices a roll gap as a return.
  3. COMPLETENESS     keep a session only if it opens on the window's first minute, closes on
                      its last, and holds exactly one bar for every minute between. Structural,
                      because this repository has no verified CME holiday table; the cost is
                      that a legitimate early close is dropped rather than scaled.

NOTHING HERE IS A DEFAULT
---------------------------
The window is required. There is no fallback instrument, no fallback adapter and no fallback
session. A missing store raises; an unreadable one raises; an execution-invalid data form
raises. `docs/CANONICAL_DATA_LAYER.md` is why: an assumption nobody had to type is an
assumption nobody checked.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from quant_brain.data import loader as L
from quant_brain.data.manifest import DatasetManifest
from quant_brain.markets.futures_cme import dataquality as fdq

#: The column contract the backtester downstream of this module reads. `ledger_builder` takes
#: `c/h/l/t/day`, the feature library takes `o/h/l/c/v`, and `hm` is the window filter's own
#: working column, kept because the legacy frames carry it and equivalence is asserted on the
#: whole frame rather than on a chosen subset.
BACKTESTER_COLUMNS: tuple[str, ...] = ("t", "o", "h", "l", "c", "v", "contract", "day", "hm")

#: Canonical name -> backtester name. The ONLY place the two vocabularies meet.
_RENAME: dict[str, str] = {
    "timestamp": "t", "open": "o", "high": "h", "low": "l", "close": "c",
    "volume": "v", "contract_symbol": "contract",
}

CANONICAL = "canonical"
LEGACY = "legacy"


class SessionSourceError(ValueError):
    """A load that would require guessing. Raised, never warned around."""


def _minutes(hhmm: str) -> int:
    """Minutes past midnight, on the venue's wall clock.

    Wall-clock arithmetic, deliberately not `datetime` arithmetic: the window is a pair of
    LOCAL clock readings and the same two readings describe a 391-bar session on both sides of
    a DST change. Constructing a datetime here would attach a date, and a date is what makes
    an hour appear or vanish twice a year.
    """
    try:
        h, _, m = hhmm.partition(":")
        hours, mins = int(h), int(m)
    except ValueError as exc:
        raise SessionSourceError(f"{hhmm!r} is not a HH:MM wall-clock time") from exc
    if not (0 <= hours <= 23 and 0 <= mins <= 59) or len(hhmm) != 5:
        raise SessionSourceError(f"{hhmm!r} is not a HH:MM wall-clock time")
    return hours * 60 + mins


@dataclass(frozen=True)
class SessionWindow:
    """The venue-clock trading window, with its bar count derived rather than assumed.

    `futures_discover` carries these as module globals and had to grow `use_session` because
    setting the close without recomputing the bar count silently discarded every session. Here
    they are one immutable value, so the two cannot be set apart.
    """

    open_et: str
    close_et: str
    timezone: str = "America/New_York"

    def __post_init__(self) -> None:
        if _minutes(self.close_et) <= _minutes(self.open_et):
            raise SessionSourceError(
                f"close {self.close_et} is not after open {self.open_et}")

    @property
    def bars(self) -> int:
        """Inclusive minute count: 09:30..16:00 is 391 bars, not 390."""
        return _minutes(self.close_et) - _minutes(self.open_et) + 1

    @classmethod
    def from_spec(cls, spec) -> SessionWindow:
        """Read the window off a frozen `StrategySpec`. The spec is the authority."""
        return cls(open_et=spec.session.open_et, close_et=spec.session.close_et)

    def as_dict(self) -> dict:
        return {"open_et": self.open_et, "close_et": self.close_et,
                "timezone": self.timezone, "bars": self.bars}


@dataclass(frozen=True)
class Attrition:
    """Where every bar and every session went. Reported, not summarised away.

    A backtest that silently drops a fifth of its sessions is a different experiment from the
    one the author thinks they ran, so the count of each refusal travels with the data.
    """

    bars_in_file: int
    bars_in_window: int
    sessions_in_window: int
    sessions_dropped_multi_contract: int
    sessions_dropped_incomplete: int
    sessions_kept: int
    multi_contract_days: tuple[str, ...] = ()
    incomplete_days: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "bars_in_file": self.bars_in_file,
            "bars_in_window": self.bars_in_window,
            "sessions_in_window": self.sessions_in_window,
            "sessions_dropped_multi_contract": self.sessions_dropped_multi_contract,
            "sessions_dropped_incomplete": self.sessions_dropped_incomplete,
            "sessions_kept": self.sessions_kept,
            "multi_contract_days": list(self.multi_contract_days),
            "incomplete_days": list(self.incomplete_days),
        }

    def line(self) -> str:
        multi = ("unknown" if self.sessions_dropped_multi_contract < 0
                 else str(self.sessions_dropped_multi_contract))
        return (f"{self.bars_in_file:,} bars in file -> {self.bars_in_window:,} in window -> "
                f"{self.sessions_in_window} sessions -> dropped {multi} multi-contract, "
                f"{self.sessions_dropped_incomplete} incomplete -> "
                f"{self.sessions_kept} kept")


@dataclass(frozen=True)
class SessionSet:
    """The backtester's input: complete sessions, the window they were cut on, and provenance.

    `provenance` is the block that goes in the result JSON. On the canonical path it is
    `ResearchInputs.provenance()` - data form, roll method, adjustment method, manifest id,
    frame fingerprint, quality status - and on the legacy path it is an explicit record that
    NONE of those were declared, which is the honest description of what that path knows.
    """

    sessions: tuple[pd.DataFrame, ...]
    window: SessionWindow
    path: str
    instrument: str
    source_file: str
    provenance: dict
    attrition: Attrition
    manifest: DatasetManifest | None = None
    inputs: L.ResearchInputs | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __len__(self) -> int:
        return len(self.sessions)

    @property
    def frames(self) -> list[pd.DataFrame]:
        """The list the backtester iterates. A list, not the tuple, to match the old call."""
        return list(self.sessions)

    @property
    def first_day(self):
        return self.sessions[0]["day"].iloc[0]

    @property
    def last_day(self):
        return self.sessions[-1]["day"].iloc[0]

    def describe(self) -> str:
        head = (f"DATA PATH: {self.path.upper()}   {self.instrument}   "
                f"{self.window.open_et}-{self.window.close_et} "
                f"{self.window.timezone}   {len(self.sessions)} sessions   "
                f"{self.first_day} .. {self.last_day}")
        body = self.provenance.get("describe", "")
        return f"{head}\n  {self.attrition.line()}" + (f"\n  {body}" if body else "")


# ======================================================================================
# THE THREE FILTERS
# ======================================================================================

def _apply_window(frame: pd.DataFrame, window: SessionWindow) -> pd.DataFrame:
    """Filter 1. Venue-clock wall time, inclusive at both ends, plus `day` and `hm`."""
    et = frame["t"].dt.tz_convert(window.timezone)
    out = frame.copy()
    out["day"] = et.dt.date
    out["hm"] = et.dt.strftime("%H:%M")
    keep = (out["hm"] >= window.open_et) & (out["hm"] <= window.close_et)
    return out[keep].reset_index(drop=True)


def _drop_multi_contract(frame: pd.DataFrame) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """Filter 2. A session spanning two physical contracts prices a roll gap as a return."""
    per = frame.groupby("day")["contract"].nunique()
    bad = tuple(str(d) for d in per[per != 1].index)
    kept = frame[frame["day"].isin(per[per == 1].index)].reset_index(drop=True)
    return kept, bad


def _complete_sessions(frame: pd.DataFrame,
                       window: SessionWindow) -> tuple[list[pd.DataFrame], tuple[str, ...]]:
    """Filter 3. Structural completeness: first minute, last minute, exact bar count.

    Those three together admit no interior hole - `window.bars` distinct minutes cannot fit in
    a `window.bars`-minute span with a gap in it - and duplicate timestamps, which are the one
    way to defeat that counting argument, are a FAIL in both quality gates upstream.
    """
    out: list[pd.DataFrame] = []
    dropped: list[str] = []
    for day, g in frame.groupby("day", sort=True):
        hm = g["hm"]
        if (len(g) != window.bars or hm.iloc[0] != window.open_et
                or hm.iloc[-1] != window.close_et):
            dropped.append(str(day))
            continue
        out.append(g.reset_index(drop=True))
    return out, tuple(dropped)


def _cut(frame: pd.DataFrame, window: SessionWindow,
         bars_in_file: int) -> tuple[list[pd.DataFrame], Attrition]:
    """The three filters in order, with every refusal counted."""
    windowed = _apply_window(frame, window)
    sessions_in_window = int(windowed["day"].nunique()) if len(windowed) else 0
    single, multi = _drop_multi_contract(windowed)
    complete, incomplete = _complete_sessions(single, window)
    return complete, Attrition(
        bars_in_file=bars_in_file, bars_in_window=len(windowed),
        sessions_in_window=sessions_in_window,
        sessions_dropped_multi_contract=len(multi),
        sessions_dropped_incomplete=len(incomplete),
        sessions_kept=len(complete),
        multi_contract_days=multi, incomplete_days=incomplete)


# ======================================================================================
# THE CANONICAL PATH
# ======================================================================================

def from_dataset(ds: L.ResearchDataset, window: SessionWindow) -> SessionSet:
    """Cut sessions from an already-loaded canonical dataset. The core of the adapter.

    THE FOUR THINGS THIS DOES THAT THE LEGACY PATH CANNOT
      - the frame arrived having passed `schema.validate_frame`: UTC-stored, tz-declared, one
        instrument, one bar interval, numeric prices.
      - it arrived having passed `quality.check`: duplicates, gaps, impossible bars, stale
        prices, mixed-contract sessions - PASS/WARN/FAIL, hashed onto the manifest.
      - the series DECLARES its form. `ResearchInputs` refuses an execution source whose data
        form is adjusted, so a fill can never be simulated at a price no venue quoted.
      - the result carries the manifest id and the frame fingerprint, so two runs on two
        representations of the same file cannot be mistaken for each other.

    The futures validator that the legacy path runs (`futures_cme.dataquality.require_usable`)
    is run here TOO, on the renamed frame. Running both is deliberate: the canonical path must
    not be weaker than the path it replaces on any check, and the two gates do not test the
    same things.

    Taking a dataset rather than a path is what lets a caller hand in a SLICE - a training
    window, a holdout - without this module having to own the idea of a split.
    """
    instrument = ds.manifest.instrument
    inputs = L.same_for_both(ds)                 # refuses a non-execution-valid form
    frame = ds.frame.rename(columns=_RENAME)
    frame["contract"] = frame["contract"].astype(str)
    fdq.require_usable(instrument, frame, time_col="t")   # the legacy gate, also run here

    sessions, attrition = _cut(frame, window, bars_in_file=len(ds.frame))
    if not sessions:
        raise SessionSourceError(
            f"{instrument}: zero complete sessions on {window.open_et}-{window.close_et}. "
            f"Refusing to run on partial sessions. {attrition.line()}")

    prov = inputs.provenance()
    prov["data_path"] = CANONICAL
    prov["describe"] = inputs.describe()
    prov["window"] = window.as_dict()
    prov["attrition"] = attrition.as_dict()
    prov["gates_run"] = ["schema.validate_frame", "data.quality.check",
                         "futures_cme.dataquality.require_usable"]
    return SessionSet(
        sessions=tuple(s[list(BACKTESTER_COLUMNS)] for s in sessions), window=window,
        path=CANONICAL, instrument=instrument,
        source_file=", ".join(ds.manifest.source_files),
        provenance=prov, attrition=attrition, manifest=ds.manifest, inputs=inputs,
        notes=tuple(ds.manifest.notes))


def from_canonical(store: Path | str, instrument: str, window: SessionWindow, *,
                   adapter: str = "ibkr_futures", dataset_id: str | None = None,
                   **adapter_kwargs) -> SessionSet:
    """Read a file through a NAMED canonical adapter, then cut sessions.

    The convenience wrapper over `from_dataset`. `adapter` is named rather than inferred from
    the filename: a provider with no adapter is not read by guessing at its columns, and a
    fuzzy match between `close` and `adj_close` is how an adjusted series becomes an execution
    price.
    """
    store = Path(store)
    if not store.exists():
        raise SessionSourceError(
            f"no bars for {instrument} at {store}. The engine fails closed rather than "
            f"substituting a proxy instrument.")
    ds = L.load(adapter, store, instrument=instrument, dataset_id=dataset_id,
                **adapter_kwargs)
    return from_dataset(ds, window)


# ======================================================================================
# THE LEGACY PATH - kept runnable so the two can be compared, never as the default
# ======================================================================================

def from_legacy(store: Path | str, instrument: str, window: SessionWindow) -> SessionSet:
    """Load through `futures_discover`, unmodified. Present ONLY for the equivalence run.

    This calls the original module, including its global `use_session` state, so what is
    compared is the code that produced the published numbers rather than a reimplementation
    of it. The provenance block records what this path does NOT know, because that absence is
    the finding: no data form, no roll method, no adjustment method, no manifest, no
    fingerprint, and no statement that the prices are execution-valid.
    """
    import sys
    repo = Path(__file__).resolve().parents[2]
    if str(repo / "scripts") not in sys.path:
        sys.path.insert(0, str(repo / "scripts"))
    import futures_discover as fd

    store = Path(store)
    if not store.exists():
        raise SessionSourceError(f"no bars for {instrument} at {store}")

    fd.use_session(window.open_et, window.close_et)
    raw_bars = len(pd.read_parquet(store))
    df = fd.load(store, instrument)
    sessions = fd.session_frames(df)
    if not sessions:
        raise SessionSourceError(
            f"{instrument}: zero complete sessions on {window.open_et}-{window.close_et}")

    kept_days = {str(s["day"].iloc[0]) for s in sessions}
    attrition = Attrition(
        bars_in_file=raw_bars, bars_in_window=len(df),
        sessions_in_window=int(df["day"].nunique()) if len(df) else 0,
        # `fd.load` has already dropped the multi-contract days, so they are not countable
        # here without re-reading the file. Stated as unknown rather than guessed at.
        sessions_dropped_multi_contract=-1,
        sessions_dropped_incomplete=int(df["day"].nunique()) - len(sessions),
        sessions_kept=len(sessions),
        incomplete_days=tuple(sorted(
            {str(d) for d in df["day"].unique()} - kept_days)) if len(df) else ())
    prov = {
        "data_path": LEGACY,
        "describe": ("LEGACY PATH: bars read straight from the provider file. No data form, "
                     "no roll method, no adjustment method, no manifest id and no frame "
                     "fingerprint were declared, because this path has nowhere to put them."),
        "features_identical_to_execution": True,
        "feature_data": {"dataset_id": f"{store.stem}.parquet", "manifest_id": None,
                         "frame_fingerprint": None, "data_form": None,
                         "roll_method": None, "adjustment_method": None,
                         "provider": None, "quality_status": None},
        "execution_data": {"dataset_id": f"{store.stem}.parquet", "manifest_id": None,
                           "frame_fingerprint": None, "data_form": None,
                           "execution_valid": None},
        "window": window.as_dict(),
        "attrition": attrition.as_dict(),
        "gates_run": ["futures_cme.dataquality.require_usable"],
    }
    return SessionSet(
        sessions=tuple(sessions), window=window, path=LEGACY, instrument=instrument,
        source_file=str(store), provenance=prov, attrition=attrition)


# ======================================================================================
# THE ONE ENTRY POINT THE RUNNER CALLS
# ======================================================================================

def build(spec, *, data_path: str = CANONICAL, root: Path | None = None) -> SessionSet:
    """Sessions for a frozen spec. `canonical` is the default; `legacy` must be asked for."""
    repo = Path(__file__).resolve().parents[2] if root is None else Path(root)
    store = repo / "data" / "futures" / f"{spec.instrument}.parquet"
    window = SessionWindow.from_spec(spec)
    if data_path == CANONICAL:
        return from_canonical(store, spec.instrument, window)
    if data_path == LEGACY:
        return from_legacy(store, spec.instrument, window)
    raise SessionSourceError(
        f"unknown data path {data_path!r}. Use {CANONICAL!r} (the authoritative input) or "
        f"{LEGACY!r} (the pre-canonical reader, kept for the equivalence run only).")


__all__ = ["Attrition", "BACKTESTER_COLUMNS", "CANONICAL", "LEGACY", "SessionSet",
           "SessionSourceError", "SessionWindow", "build", "from_canonical", "from_dataset",
           "from_legacy"]
