"""THE ANCHORED LOADER: 18:00 ET -> 15:45 ET sessions, complete or refused.

    RAW STORE          data/futures/<SYM>.parquet   (t,o,h,l,c,v,contract)
         |  quant_brain.data.adapters.ibkr_futures   <- the ONLY place vendor names appear
    CANONICAL FRAME    12 required columns, UTC-stored, tz declared, manifest + quality gate
         |  this module
    ANCHORED SESSION   one trading day, 18:00 ET (prev cal. day) -> 15:45 ET, ONE contract
         |
    1-MINUTE Bar[]     the engine's only input type
         |  FiveMinuteAggregator, inside the engine
    5-MINUTE BARS      derived causally; a bucket exists only once its last minute closed
         |
    STRATEGY ENGINE

WHY THIS IS NOT `research/session_source`
------------------------------------------
That module cuts RTH windows (09:30-16:00) and is certified for it. Its three filters do not
describe this session at all: the anchored window CROSSES MIDNIGHT, its expected bar count
changes with daylight saving, and its completeness turns on two specific bars - the 18:00
anchor and the 15:45 flatten - rather than on a count. Adding a second mode to a certified
module would put the RTH equivalence guarantee at risk to save a dataclass, so the shared
pieces (`SessionSet`-shaped provenance, the canonical load, the quality gate) are REUSED and
only the cutting is new. `tests/test_vwap_data.py` proves the two agree bar-for-bar on the
window where they overlap.

THE COMPLETENESS RULE, AND WHY IT IS STRICT
---------------------------------------------
A session is usable only if it is COMPLETE: the 18:00 bar is present, the 15:45 bar is
present, every minute between them is present exactly once, and every bar carries the same
contract. Anything else is kept in the dataset with a reason and excluded from the strategy
feed.

That is stricter than it may look, and deliberately:

  - a missing 18:00 anchor means the VWAP starts somewhere else, and every band, every zone
    test and every regime decision for the whole day is then computed against a number the
    specification did not define.
  - a missing 15:45 bar means the engine's forced flat never fires. A position would survive
    to the 18:00 roll, which the engine treats as an invariant violation and refuses. On this
    store that is not hypothetical: fourteen ES sessions have no 15:45 bar, their last bar
    falling at 12:59, 13:14 or 09:14 ET. WHY those bars are absent is not determined here -
    see `SessionStatus.TRUNCATED_END`.
  - an interior hole removes volume from a VOLUME-WEIGHTED average. The VWAP that results is
    not the frozen VWAP with a small error in it; it is a different statistic.

NOTHING IS REPAIRED. No bar is interpolated, no price is carried forward, no gap is bridged,
no roll is adjusted. `docs/CANONICAL_DATA_LAYER.md` is the doctrine and this module inherits
it: a dataset that cannot be described is refused rather than tidied.

WHAT THIS LOADER DOES NOT DECIDE
----------------------------------
It does not choose a contract. The `contract` column was written at fetch time by
`scripts/futures_fetch_multi.py` under a CALENDAR rule - eight days before each contract's
last trade date - and this module READS it. There is no volume crossover, no open-interest
test and no look at what later turned out to be liquid, because that information did not
exist on the day and the store carries none of it anyway.
"""
from __future__ import annotations

import datetime as dt
import enum
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd

from quant_brain.data import loader as L
from quant_brain.data.manifest import DatasetManifest
from quant_brain.strategies.vwap_pullback.indicators import Bar
from quant_brain.strategies.vwap_pullback.spec import FROZEN, TIMEZONE, FrozenSpec

#: Bumped whenever the cutting rules or the manifest shape change, so a result produced under
#: an older loader is identifiable as such rather than silently comparable.
LOADER_VERSION = "vwap-anchored-1.0.0"
SCHEMA_VERSION = "1.0.0"


class SessionStatus(str, enum.Enum):
    """Why a session is or is not fed to the strategy. Ordered worst-last for reporting."""

    COMPLETE = "COMPLETE"
    #: Every minute from the anchor to some point before 15:45, then nothing. The overnight
    #: is whole; the afternoon simply is not there.
    #:
    #: THE NAME DESCRIBES THE SHAPE AND CLAIMS NOTHING ABOUT THE CAUSE. A scheduled venue
    #: close and a vendor outage that ended at the session close produce the same shape, and
    #: telling them apart needs a verified CME calendar, which this repository does not have
    #: (`markets/equity_us/calendar.py` is hand-verified against the NYSE schedule and is a
    #: different venue: it cannot describe CME's 09:15 Good Friday close). Both are refused,
    #: so nothing reaches the strategy on the strength of a guess, and the rejection code is
    #: INCOMPLETE_SESSION for both.
    TRUNCATED_END = "TRUNCATED_END"
    #: A hole somewhere inside the session. Removes volume from a volume-weighted average.
    HOLED = "HOLED"
    #: The session never reached 18:00 - the VWAP would anchor somewhere undefined.
    NO_ANCHOR = "NO_ANCHOR"
    #: Two physical contracts in one session: a roll gap would be priced as a return.
    MULTI_CONTRACT = "MULTI_CONTRACT"
    #: Duplicate timestamps, impossible OHLC, negative volume. Refused by the schema.
    CORRUPT = "CORRUPT"

    @property
    def usable(self) -> bool:
        return self is SessionStatus.COMPLETE


@dataclass(frozen=True)
class SessionQuality:
    """Everything measured about one session. Every count, never a summary verdict alone."""

    trading_day: dt.date
    status: SessionStatus
    expected_bars: int
    actual_bars: int
    missing_minutes: tuple[str, ...]
    duplicate_timestamps: int
    zero_volume_bars: int
    invalid_bars: int
    contracts: tuple[str, ...]
    first_et: str
    last_et: str
    has_anchor: bool
    has_flatten: bool
    reasons: tuple[str, ...]

    @property
    def missing_count(self) -> int:
        return len(self.missing_minutes)

    @property
    def rejection_code(self) -> str:
        """`INCOMPLETE_SESSION` for anything refused, empty for a session that is fed.

        ONE code, deliberately. `status` records the measured SHAPE of the failure, which is
        useful for reading a census; the code records the only thing the strategy acts on,
        which is that the session did not meet the objective completeness requirements. It
        never says HOLIDAY, EARLY_CLOSE or OUTAGE, because deciding between those needs a
        verified venue calendar and this repository has none for CME. An inferred calendar
        in the rejection record is inferred calendar knowledge in the backtest.
        """
        return "" if self.status.usable else "INCOMPLETE_SESSION"

    def as_row(self) -> dict:
        return {
            "trading_day": str(self.trading_day), "status": self.status.value,
            "rejection_code": self.rejection_code,
            "expected_bars": self.expected_bars, "actual_bars": self.actual_bars,
            "missing": self.missing_count,
            #: capped so one pathological session cannot dominate a manifest, with the count
            #: kept above so nothing is hidden by the cap
            "missing_sample": list(self.missing_minutes[:12]),
            "duplicate_timestamps": self.duplicate_timestamps,
            "zero_volume_bars": self.zero_volume_bars,
            "invalid_bars": self.invalid_bars,
            "contracts": list(self.contracts),
            "first_et": self.first_et, "last_et": self.last_et,
            "has_anchor": self.has_anchor, "has_flatten": self.has_flatten,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class AnchoredSession:
    """One 18:00-anchored trading day and the bars the engine would receive."""

    trading_day: dt.date
    bars: tuple[Bar, ...]
    quality: SessionQuality

    @property
    def usable(self) -> bool:
        return self.quality.status.usable

    @property
    def contract(self) -> str:
        return self.quality.contracts[0] if self.quality.contracts else ""

    @property
    def overnight_bars(self) -> int:
        """Bars before the 09:30 cash open. The half `session_source` throws away."""
        return sum(1 for b in self.bars
                   if _minute(b.timestamp) >= 18 * 60 or _minute(b.timestamp) < 9 * 60 + 30)

    @property
    def rth_bars(self) -> int:
        return len(self.bars) - self.overnight_bars

    def content_hash(self) -> str:
        """A hash of the BARS, so two runs on the same session are provably the same bars."""
        h = hashlib.sha256()
        for b in self.bars:
            h.update(f"{b.timestamp.timestamp():.0f}|{b.open!r}|{b.high!r}|{b.low!r}|"
                     f"{b.close!r}|{b.volume!r}".encode())
        return h.hexdigest()[:16]


@dataclass(frozen=True)
class RollEvent:
    """One contract change in the underlying store, measured rather than assumed."""

    at_utc: str
    at_et: str
    previous_contract: str
    new_contract: str
    previous_close: float
    new_open: float
    price_difference: float
    price_difference_pct: float
    previous_volume: float
    new_volume: float
    open_interest: str
    #: Where the contract change sits relative to the session boundary. Three-valued
    #: on purpose: a roll AT the anchor is the first bar of a NEW session, so the session it
    #: belongs to is entirely the new contract and NOTHING is mixed. A plain "inside a
    #: session" boolean is true of that bar and conveys the opposite of the material fact -
    #: a reader would take it as three contaminated sessions on this store, when the count
    #: of contaminated sessions is zero.
    #:      AT_THE_ANCHOR     the 18:00 bar: opens a session, contaminates none
    #:      BETWEEN_SESSIONS  in the 15:46-17:59 break: belongs to no session at all
    #:      INSIDE_A_SESSION  the one that would price a roll gap as a return
    position: str
    trading_day: str

    def as_row(self) -> dict:
        return dict(self.__dict__)


@dataclass(frozen=True)
class AnchoredDataset:
    """Every anchored session found in one store, usable and not."""

    instrument: str
    sessions: tuple[AnchoredSession, ...]
    rolls: tuple[RollEvent, ...]
    source_manifest: DatasetManifest
    spec: FrozenSpec = FROZEN
    notes: tuple[str, ...] = field(default_factory=tuple)

    def usable(self) -> list[AnchoredSession]:
        """The only sessions a strategy run may consume."""
        return [s for s in self.sessions if s.usable]

    def rejected(self) -> list[AnchoredSession]:
        return [s for s in self.sessions if not s.usable]

    def by_status(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for s in self.sessions:
            out[s.quality.status.value] = out.get(s.quality.status.value, 0) + 1
        return out

    @property
    def file_bytes(self) -> tuple[int, ...]:
        """Size on disk of each source file, in the order the manifest lists them.

        Recorded beside the sha256 rather than instead of it. The hash settles identity; the
        size is what a human can check in a directory listing in one second, and a size that
        disagrees with a matching hash would mean something far stranger than a stale file.
        """
        return tuple(Path(f).stat().st_size if Path(f).exists() else -1
                     for f in self.source_manifest.source_files)

    # -- the manifest -------------------------------------------------------------------

    def manifest(self) -> dict:
        """A DETERMINISTIC record of what was loaded. Hashed, and traceable to the source.

        This is what makes a strategy result attributable. A run quoting a manifest id can be
        tied to a specific file, a specific interpretation of that file, and a specific set of
        bars; a run quoting nothing is a number nobody can reproduce.
        """
        usable = self.usable()
        body = {
            "loader_version": LOADER_VERSION,
            "schema_version": SCHEMA_VERSION,
            "instrument": self.instrument,
            "session_definition": {
                "anchor_et": f"{self.spec.session_anchor[0]:02d}:"
                             f"{self.spec.session_anchor[1]:02d}",
                "end_et": f"{self.spec.hard_flatten[0]:02d}:{self.spec.hard_flatten[1]:02d}",
                "timezone": TIMEZONE.key,
                "bar_interval": "1min",
                "bar_stamp": "start-of-bar",
                "continuous": True,
                #: Written out because "one continuous session" is the claim most likely to
                #: be broken by a well-meaning later edit, and a manifest that states the
                #: boundaries it does NOT have is checkable.
                "vwap_reset_et": f"{self.spec.session_anchor[0]:02d}:"
                                 f"{self.spec.session_anchor[1]:02d}",
                "no_reset_at": ["00:00", "09:30", "09:45", "15:30", "calendar_date_change"],
                "completeness": "anchor present, end present, every minute between present "
                                "exactly once, one contract, valid OHLC, non-negative "
                                "volume",
                "rejection_code": "INCOMPLETE_SESSION",
                "zero_volume_policy": "kept. A zero-volume bar contributes TP * 0 = 0 to the "
                                      "volume-weighted average, so it adds no weight and "
                                      "moves nothing. It is never dropped, never repaired, "
                                      "and never a reason to reject a session; the count is "
                                      "carried per session below.",
            },
            "adjustment_mode": self.source_manifest.data_form.value,
            "roll_method": self.source_manifest.roll.method.value,
            "roll_adjustment": self.source_manifest.roll.adjustment.value,
            "roll_days_before_expiry": self.source_manifest.roll.days_before_expiry,
            "source": {
                "dataset_id": self.source_manifest.dataset_id,
                "provider": self.source_manifest.provider,
                #: `files` is the only path-shaped field and the only one the identity hash
                #: excludes - see the note beside `manifest_id` below.
                "files": list(self.source_manifest.source_files),
                "file_hashes": list(self.source_manifest.source_hashes),
                "file_bytes": list(self.file_bytes),
                "rows_in_file": self.source_manifest.bars,
                "first_bar_utc": self.source_manifest.coverage_start,
                "last_bar_utc": self.source_manifest.coverage_end,
                "contract_coverage": list(self.source_manifest.roll.contracts),
                "bar_interval": self.source_manifest.bar_interval,
                "stored_timezone": self.source_manifest.timezone,
                "session_timezone": self.source_manifest.session_timezone,
                "manifest_id": self.source_manifest.manifest_id,
                "schema_version": self.source_manifest.schema_version,
                "quality_status": self.source_manifest.quality.status,
                "quality_report_hash": self.source_manifest.quality.report_hash,
                "quality_warn_reasons": list(self.source_manifest.quality.warn_reasons),
            },
            "coverage": {
                "first_trading_day": str(self.sessions[0].trading_day) if self.sessions
                                     else None,
                "last_trading_day": str(self.sessions[-1].trading_day) if self.sessions
                                    else None,
                "sessions_found": len(self.sessions),
                "sessions_usable": len(usable),
                "by_status": self.by_status(),
            },
            "totals": {
                "bars_usable": sum(len(s.bars) for s in usable),
                "overnight_bars_usable": sum(s.overnight_bars for s in usable),
                "rth_bars_usable": sum(s.rth_bars for s in usable),
                "missing_bars_all_sessions": sum(s.quality.missing_count
                                                 for s in self.sessions),
                "duplicate_timestamps": sum(s.quality.duplicate_timestamps
                                            for s in self.sessions),
                "invalid_bars": sum(s.quality.invalid_bars for s in self.sessions),
                "zero_volume_bars": sum(s.quality.zero_volume_bars for s in self.sessions),
            },
            "rolls": [r.as_row() for r in self.rolls],
            "sessions": [s.quality.as_row() for s in self.sessions],
            "notes": list(self.notes),
        }
        body["content_hash"] = _hash_obj(
            [s.content_hash() for s in self.sessions])

        #: The id hashes everything EXCEPT the source file path. A path is where the bytes
        #: were found, not what they are: `data/futures/ES.parquet` and
        #: `C:\...\data\futures\ES.parquet` are the same dataset, and hashing the spelling
        #: made the same run report two different ids depending only on whether the caller
        #: typed a relative or an absolute path - which would read downstream as "this ran on
        #: different data". The file's sha256 IS in the hashed body and answers the identity
        #: question exactly; the path stays in the emitted manifest for a human to follow.
        identity = {k: v for k, v in body.items() if k != "source"}
        identity["source"] = {k: v for k, v in body["source"].items() if k != "files"}
        body["manifest_id"] = _hash_obj(identity)
        return body

    def summary(self) -> str:
        m = self.manifest()
        c, t = m["coverage"], m["totals"]
        return (f"{self.instrument}  {c['first_trading_day']} .. {c['last_trading_day']}  "
                f"{c['sessions_usable']}/{c['sessions_found']} usable  "
                f"{t['bars_usable']:,} bars ({t['overnight_bars_usable']:,} overnight)  "
                f"manifest {m['manifest_id']}  by status {c['by_status']}")


# ======================================================================================
# THE CUT
# ======================================================================================

def _minute(when: dt.datetime) -> int:
    local = when.astimezone(TIMEZONE)
    return local.hour * 60 + local.minute


def _hash_obj(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def expected_minutes(trading_day: dt.date, spec: FrozenSpec = FROZEN) -> list[dt.datetime]:
    """Every minute an anchored session should contain, as UTC instants.

    DERIVED, never assumed. The walk is done in UTC between two ET wall-clock instants, so
    the count follows from the calendar rather than from a constant: a session containing a
    spring-forward loses an hour and one containing a fall-back gains one, automatically,
    because the UTC distance between 18:00 ET and 15:45 ET is what changed.

    On the CME equity-index schedule no anchored session actually spans a transition - the
    change lands at 02:00 on a Sunday and the week's first session opens at 18:00 that
    evening - but the arithmetic does not depend on that remaining true.
    """
    anchor_day = trading_day - dt.timedelta(days=1)
    start = dt.datetime(anchor_day.year, anchor_day.month, anchor_day.day,
                        spec.session_anchor[0], spec.session_anchor[1], tzinfo=TIMEZONE)
    end = dt.datetime(trading_day.year, trading_day.month, trading_day.day,
                      spec.hard_flatten[0], spec.hard_flatten[1], tzinfo=TIMEZONE)
    if spec.minute_of("hard_flatten") >= spec.anchor_minute():
        raise ValueError(
            f"a session ending at {spec.hard_flatten} and anchoring at "
            f"{spec.session_anchor} would run past the next session's anchor, so two "
            f"consecutive sessions would claim the same bars")
    t, e = start.astimezone(dt.UTC), end.astimezone(dt.UTC)
    out = []
    while t <= e:
        out.append(t)
        t += dt.timedelta(minutes=1)
    return out


def expected_bar_count(trading_day: dt.date, spec: FrozenSpec = FROZEN) -> int:
    """The count, derived from the same wall-clock arithmetic. O(1)."""
    anchor_day = trading_day - dt.timedelta(days=1)
    start = dt.datetime(anchor_day.year, anchor_day.month, anchor_day.day,
                        spec.session_anchor[0], spec.session_anchor[1], tzinfo=TIMEZONE)
    end = dt.datetime(trading_day.year, trading_day.month, trading_day.day,
                      spec.hard_flatten[0], spec.hard_flatten[1], tzinfo=TIMEZONE)
    if spec.minute_of("hard_flatten") >= spec.anchor_minute():
        raise ValueError(f"{spec.hard_flatten} does not precede the anchor "
                         f"{spec.session_anchor} on the clock")
    delta = end.astimezone(dt.UTC) - start.astimezone(dt.UTC)
    return int(delta.total_seconds() // 60) + 1          # inclusive of both endpoints


def _classify(day: dt.date, group: pd.DataFrame, spec: FrozenSpec) -> SessionQuality:
    """Measure one session and decide whether the engine may see it."""
    minutes = expected_minutes(day, spec)
    want = pd.DatetimeIndex(minutes)
    expected = len(minutes)
    et = group["_et"]
    stamps = group["timestamp"]

    #: Set arithmetic on a DatetimeIndex rather than on integers. The store stamps
    #: microseconds and other providers stamp nanoseconds or seconds; an epoch divisor
    #: written for one of those silently reports every minute as absent under another, which
    #: is exactly what the first run of this loader did.
    have = pd.DatetimeIndex(stamps.unique())
    absent_at = want.get_indexer(want.difference(have))
    absent_at.sort()
    missing = tuple(minutes[i].astimezone(TIMEZONE).strftime("%H:%M") for i in absent_at)
    duplicates = int(len(stamps) - stamps.nunique())
    contracts = tuple(dict.fromkeys(group["contract_symbol"].astype(str)))
    zero_vol = int((group["volume"] <= 0).sum())

    anchor_min = spec.minute_of("session_anchor")
    flat_min = spec.minute_of("hard_flatten")
    mins = group["_min"]
    has_anchor = bool((mins == anchor_min).any())
    has_flatten = bool((mins == flat_min).any())

    invalid = int((
        (group["high"] < group["low"])
        | (group["open"] > group["high"]) | (group["open"] < group["low"])
        | (group["close"] > group["high"]) | (group["close"] < group["low"])
        | (group["volume"] < 0)
        | ~group[["open", "high", "low", "close"]].notna().all(axis=1)
    ).sum())

    reasons: list[str] = []
    if invalid or duplicates:
        status = SessionStatus.CORRUPT
        if invalid:
            reasons.append(f"{invalid} bar(s) fail the OHLC/volume checks")
        if duplicates:
            reasons.append(f"{duplicates} duplicate timestamp(s)")
    elif len(contracts) > 1:
        status = SessionStatus.MULTI_CONTRACT
        reasons.append(f"two physical contracts in one session: {list(contracts)}. A roll "
                       f"gap inside a session is priced as a return.")
    elif not has_anchor:
        status = SessionStatus.NO_ANCHOR
        reasons.append(f"no bar at the {spec.session_anchor[0]:02d}:"
                       f"{spec.session_anchor[1]:02d} anchor, so the VWAP would start "
                       f"somewhere the specification does not define")
    elif not missing:
        status = SessionStatus.COMPLETE
    elif not has_flatten and _is_end_truncation(absent_at, expected):
        status = SessionStatus.TRUNCATED_END
        #: STATED AS MEASURED, AND NO FURTHER. An earlier draft added "consistent with a
        #: venue early close", which is an inference from a calendar this repository does
        #: not have. The owner's release gate is explicit: a rejection says
        #: INCOMPLETE_SESSION, not HOLIDAY, unless a verified source exists here - and none
        #: does for CME. Calling these holidays would put inferred calendar knowledge into
        #: the record a backtest quotes.
        reasons.append(f"present from the anchor through {et.iloc[-1]:%H:%M} ET and absent "
                       f"from there to the "
                       f"{spec.hard_flatten[0]:02d}:{spec.hard_flatten[1]:02d} endpoint "
                       f"({len(missing)} minutes, one contiguous run). The reason for the "
                       f"absence is NOT determined: no verified venue calendar exists in "
                       f"this repository. The session is refused because the "
                       f"{spec.hard_flatten[0]:02d}:{spec.hard_flatten[1]:02d} bar the "
                       f"forced flat needs is not there.")
    else:
        status = SessionStatus.HOLED
        reasons.append(f"{len(missing)} minute(s) absent from inside the session, which "
                       f"removes volume from a volume-weighted average")
    if zero_vol and status is SessionStatus.COMPLETE:
        reasons.append(f"{zero_vol} bar(s) print zero volume; they contribute no VWAP "
                       f"weight and are counted rather than dropped")

    return SessionQuality(
        trading_day=day, status=status, expected_bars=expected, actual_bars=len(group),
        missing_minutes=missing, duplicate_timestamps=duplicates,
        zero_volume_bars=zero_vol, invalid_bars=invalid, contracts=contracts,
        first_et=f"{et.iloc[0]:%Y-%m-%d %H:%M}", last_et=f"{et.iloc[-1]:%Y-%m-%d %H:%M}",
        has_anchor=has_anchor, has_flatten=has_flatten, reasons=tuple(reasons))


def _is_end_truncation(absent_at, expected: int) -> bool:
    """True when the absent minutes are exactly the END of the session and nothing else.

    This measures SHAPE and infers no cause. A contiguous run of absences reaching the
    session's final minute is a different shape from a hole in the middle, and the two get
    different `SessionStatus` values so a census is readable. Neither value is a claim about
    WHY the bars are absent: that would need a verified CME calendar, which this repository
    does not have. Both shapes are refused, and both carry the same rejection code.

    Positional, not label-based: a session spanning a fall-back would contain two bars
    labelled 01:30 and string comparison would confuse them.
    """
    n = len(absent_at)
    if not n:
        return False
    return bool(absent_at[-1] == expected - 1 and absent_at[0] == expected - n)


def _rolls(frame: pd.DataFrame, spec: FrozenSpec) -> tuple[RollEvent, ...]:
    """Every contract change in the store, with what it cost, measured from the bars."""
    sym = frame["contract_symbol"].astype(str)
    changed = sym.ne(sym.shift()) & (frame.index > frame.index[0])
    out = []
    for i in frame.index[changed]:
        prev = frame.loc[i - 1]
        cur = frame.loc[i]
        diff = float(cur["open"]) - float(prev["close"])
        et = cur["_et"]
        anchor, flat = spec.minute_of("session_anchor"), spec.minute_of("hard_flatten")
        m = int(cur["_min"])
        if m == anchor:
            position = "AT_THE_ANCHOR"
        elif flat < m < anchor:
            position = "BETWEEN_SESSIONS"
        else:
            position = "INSIDE_A_SESSION"
        out.append(RollEvent(
            at_utc=str(cur["timestamp"]), at_et=f"{et:%Y-%m-%d %H:%M}",
            previous_contract=str(prev["contract_symbol"]),
            new_contract=str(cur["contract_symbol"]),
            previous_close=float(prev["close"]), new_open=float(cur["open"]),
            price_difference=diff,
            price_difference_pct=100.0 * diff / float(prev["close"])
            if prev["close"] else float("nan"),
            previous_volume=float(prev["volume"]), new_volume=float(cur["volume"]),
            open_interest="ABSENT: IBKR historical bars carry none, so an OI-triggered "
                          "roll could not be reproduced from this store",
            position=position,
            trading_day=str(cur["_day"])))
    return tuple(out)


def load_anchored(store: Path | str, instrument: str, *, spec: FrozenSpec = FROZEN,
                  adapter: str = "ibkr_futures", require_quality: bool = True,
                  **adapter_kwargs) -> AnchoredDataset:
    """Read a store through the canonical layer and cut 18:00-anchored sessions.

    SOURCE-AGNOSTIC. Nothing here knows what IBKR's columns are called: `adapter` names an
    entry in `quant_brain.data.adapters` and `adapter_kwargs` reaches it unchanged, so a
    Databento, CSV or vendor file loads through `generic_table` with a column mapping and
    produces the same sessions. `ibkr_futures` is the DEFAULT because it is the store this
    repository has, not because the pipeline depends on it.

    Fails closed on a missing file and on a canonical-quality FAIL. Everything softer than
    that is reported per session rather than raised, because a store with two bad days should
    still yield the other three hundred.
    """
    store = Path(store)
    if not store.exists():
        raise FileNotFoundError(
            f"no bars for {instrument} at {store}. The loader fails closed rather than "
            f"substituting a proxy instrument.")

    ds = L.load(adapter, store, instrument=instrument, require_quality=require_quality,
                **adapter_kwargs)

    #: THE PRICES THIS PRODUCES ARE EXECUTION PRICES. A back- or forward-adjusted series is
    #: a valid research input and an invalid one to fill against: its levels are arithmetic,
    #: not quotes, so a stop at 20,000 would be tested against a price no venue ever showed.
    #: The canonical layer already refuses an adjusted execution source on the other path
    #: (`ResearchInputs`); this path refuses it here rather than inheriting the assumption.
    if ds.manifest.data_form.is_adjusted:
        raise ValueError(
            f"{ds.manifest.dataset_id} is {ds.manifest.data_form.value}: its prices were "
            f"adjusted by {ds.manifest.roll.adjustment.value}, so a roll gap has been "
            f"normalised away and the levels are not quotes. V1.0.0 fills against these "
            f"bars and must not run on them. Load the unadjusted series.")

    frame = ds.frame.reset_index(drop=True)
    et = frame["timestamp"].dt.tz_convert(TIMEZONE)
    mins = et.dt.hour * 60 + et.dt.minute
    anchor, flat = spec.minute_of("session_anchor"), spec.minute_of("hard_flatten")

    work = frame.assign(_et=et, _min=mins)
    #: The trading day a bar belongs to. The anchor rolls the day, so an 18:00 bar on Sunday
    #: belongs to Monday - the same convention `indicators.trading_day` uses, because the
    #: engine and the loader disagreeing about which day a bar is in would be undetectable.
    #:
    #: CALENDAR arithmetic on dates, NOT `+ pd.to_timedelta(1, "D")` on the timestamps. That
    #: form adds twenty-four ABSOLUTE hours, which is not one calendar day on either side of
    #: a DST transition: on a spring-forward session it moved every bar from 23:00 ET onward
    #: into the FOLLOWING trading day, splitting one anchored session in two and leaving both
    #: halves with the wrong VWAP anchor. Python's aware-datetime arithmetic - which
    #: `indicators.trading_day` uses - is wall-clock and does not have this property, so the
    #: two implementations disagreed only on two days a year. Found by
    #: `test_a_session_spanning_the_spring_forward_loses_an_hour`.
    calendar_day = et.dt.date.to_numpy()
    work["_day"] = np.where((mins >= anchor).to_numpy(),
                            calendar_day + dt.timedelta(days=1), calendar_day)

    rolls = _rolls(work, spec)

    inside = (mins >= anchor) | (mins <= flat)
    cut = work.loc[inside].sort_values(by=["timestamp"]).reset_index(drop=True)

    sessions: list[AnchoredSession] = []
    for key, group in cut.groupby("_day", sort=True):
        day = cast(dt.date, key)
        q = _classify(day, group, spec)
        bars = _to_bars(group) if q.status.usable else ()
        sessions.append(AnchoredSession(trading_day=day, bars=bars, quality=q))

    if not sessions:
        raise ValueError(
            f"{ds.manifest.dataset_id}: {len(frame):,} bars, and not one of them falls in an "
            f"{spec.session_anchor[0]:02d}:{spec.session_anchor[1]:02d}-anchored session. "
            f"An empty dataset is refused rather than returned: a backtest that silently "
            f"scores zero sessions reports no loss, no drawdown and no trades, and reads "
            f"exactly like a strategy that simply never triggered.")

    rule = ds.manifest.roll.method.value
    if ds.manifest.roll.days_before_expiry is not None:
        rule += f", {ds.manifest.roll.days_before_expiry} days before expiry"
    notes = [
        f"the contract on every bar was chosen at FETCH time by a calendar rule ({rule}). "
        "This loader reads that column and selects nothing.",
        f"prices are {ds.manifest.data_form.value} with adjustment "
        f"{ds.manifest.roll.adjustment.value}: no back-adjustment, no splice offset, no "
        "normalisation of roll gaps.",
        *ds.manifest.notes,
    ]
    return AnchoredDataset(instrument=instrument, sessions=tuple(sessions), rolls=rolls,
                           source_manifest=ds.manifest, spec=spec, notes=tuple(notes))


def _to_bars(group: pd.DataFrame) -> tuple[Bar, ...]:
    """Canonical rows -> the engine's `Bar`. The one place the two vocabularies meet."""
    return tuple(
        Bar(timestamp=t.to_pydatetime(), open=float(o), high=float(h), low=float(low),
            close=float(c), volume=float(v))
        for t, o, h, low, c, v in zip(
            group["timestamp"], group["open"], group["high"], group["low"],
            group["close"], group["volume"], strict=True))


__all__ = ["AnchoredDataset", "AnchoredSession", "LOADER_VERSION", "RollEvent",
           "SCHEMA_VERSION", "SessionQuality", "SessionStatus", "expected_bar_count",
           "expected_minutes", "load_anchored"]
