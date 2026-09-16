"""PHASE 2 certification of the 18:00-anchored historical data path. DATA ONLY.

No strategy is run here. Nothing in this file calls `Engine`, `Governor`, `OrderBook` or
`run_strategy.py`; no fill is simulated, no P&L is computed and no performance statistic
appears. What IS exercised, because the brief requires it, is the INDICATOR side of the data
contract - `SessionVwap` and `FiveMinuteAggregator` - since "the only VWAP reset is 18:00 ET"
and "a 5-minute bucket must not be visible before its last minute closed" are statements about
data construction that can only be proved by feeding data through them.

WHY SO MUCH OF THIS IS SYNTHETIC
---------------------------------
The store on disk is fifteen months of one venue and contains exactly one shape of defect
(end-truncated holiday sessions) plus two near-miss anchors. It cannot demonstrate a fall-back
DST session, a mid-session roll, a duplicate timestamp or an impossible bar, because none of
those are in it. Every one of those is therefore CONSTRUCTED, written to a parquet in the
store's own layout, and read back through the same adapter the real store uses - so the test
exercises the production path rather than a mock of it.

THE TWO DST SESSIONS THAT DO NOT EXIST
----------------------------------------
US DST changes at 02:00 on a Sunday, and the week's first anchored session opens at 18:00 that
same Sunday evening, so no REAL anchored session ever contains a transition. That makes the
DST handling untestable on real data and permanently so. The tests therefore use the
hypothetical Saturday-anchored sessions - 18:00 Sat -> 15:45 Sun - which DO span both
transitions, and assert the derived bar count moves to 1,246 and 1,366. Those sessions never
trade; the arithmetic that produces their length is the same arithmetic that produces every
real session's length, and this is the only way to show it is arithmetic and not the constant
1,306 with a comment.
"""
from __future__ import annotations

import ast
import datetime as dt
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from quant_brain.data import loader as L
from quant_brain.data.adapters import AdapterError
from quant_brain.data.quality import DataQualityError
from quant_brain.research import session_source as SS
from quant_brain.strategies.vwap_pullback import data as D
from quant_brain.strategies.vwap_pullback.indicators import (
    Bar,
    FiveMinuteAggregator,
    SessionVwap,
    VolumeSma,
    trading_day,
)
from quant_brain.strategies.vwap_pullback.spec import FROZEN, TIMEZONE

REPO = Path(__file__).resolve().parents[1]
STORE = REPO / "data" / "futures"
ANCHOR = FROZEN.anchor_minute()
FLAT = FROZEN.minute_of("hard_flatten")

needs_store = pytest.mark.skipif(not (STORE / "ES.parquet").exists(),
                                 reason="the futures store is not present")


# ======================================================================================
# SYNTHETIC STORES - the store's own layout, read through the store's own adapter
# ======================================================================================

def _rows(minutes, contract: str, base: float, volume: float) -> list[dict]:
    """One row per minute, in the IBKR store layout, with a valid OHLC by construction."""
    out = []
    for i, t in enumerate(minutes):
        c = base + (i % 7) * 0.25
        out.append({"t": t, "o": c, "h": c + 0.5, "l": c - 0.5, "c": c, "v": volume,
                    "contract": contract})
    return out


def write_store(path: Path, rows: list[dict]) -> Path:
    """Write rows as a parquet the `ibkr_futures` adapter will read."""
    df = pd.DataFrame(rows)
    df["t"] = pd.to_datetime(df["t"], utc=True)
    df.to_parquet(path, index=False)
    return path


def synth_session(day: dt.date, *, contract: str = "ESU5", base: float = 6000.0,
                  volume: float = 500.0, drop: tuple[int, ...] = (),
                  keep: int | None = None) -> list[dict]:
    """A complete anchored session for `day`, optionally with bars removed.

    `drop` removes bars by POSITION in the expected sequence; `keep` truncates to the first
    n bars. Both exist so a defect can be placed exactly where a test wants it.
    """
    mins = D.expected_minutes(day)
    if keep is not None:
        mins = mins[:keep]
    mins = [m for i, m in enumerate(mins) if i not in set(drop)]
    return _rows(mins, contract, base, volume)


@pytest.fixture
def store(tmp_path):
    """A factory: rows -> a loaded `AnchoredDataset`, through the real adapter."""
    def build(rows: list[dict], *, instrument: str = "ES",
              require_quality: bool = False) -> D.AnchoredDataset:
        p = write_store(tmp_path / f"{instrument}.parquet", rows)
        return D.load_anchored(p, instrument, require_quality=require_quality)
    return build


#: Loading a whole store is ~6 seconds and cutting RTH sessions from it is slower still.
#: The mutation harness runs this suite once per data mutation, so the loads are cached.
#: Nothing here is mutated - `AnchoredDataset` and `SessionSet` are both frozen.
_ANCHORED: dict[str, D.AnchoredDataset] = {}
_CANONICAL: dict[str, L.ResearchDataset] = {}
_RTH: dict[str, SS.SessionSet] = {}


def loaded(symbol: str) -> D.AnchoredDataset:
    if symbol not in _ANCHORED:
        _ANCHORED[symbol] = D.load_anchored(STORE / f"{symbol}.parquet", symbol)
    return _ANCHORED[symbol]


def canonical(symbol: str) -> L.ResearchDataset:
    if symbol not in _CANONICAL:
        _CANONICAL[symbol] = L.load("ibkr_futures", STORE / f"{symbol}.parquet",
                                    instrument=symbol)
    return _CANONICAL[symbol]


def rth(symbol: str) -> SS.SessionSet:
    """The existing loader's view of the same file: 09:30-16:00, complete sessions only."""
    if symbol not in _RTH:
        _RTH[symbol] = SS.from_dataset(canonical(symbol), SS.SessionWindow("09:30", "16:00"))
    return _RTH[symbol]


@pytest.fixture(scope="session")
def es() -> D.AnchoredDataset:
    return loaded("ES")


DATA_MODULE = REPO / "quant_brain" / "strategies" / "vwap_pullback" / "data.py"


def _hm(when: dt.datetime) -> int:
    """Minutes past midnight on the venue clock."""
    local = when.astimezone(TIMEZONE)
    return local.hour * 60 + local.minute


def _code_only(path: Path) -> str:
    """The module's CODE, with every comment and docstring removed.

    The structural tests below search for forbidden constructs. Searching the raw source
    would match the prose that explains why those constructs are absent - the module says
    "no bar is interpolated" and a naive scan for "interpolate" would fail on its own
    documentation. `ast.unparse` of the stripped tree is the honest thing to search.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)) and ast.get_docstring(node) is not None:
            node.body = node.body[1:] or [ast.Pass()]
    return ast.unparse(tree)


# ======================================================================================
# A. SESSION CONSTRUCTION
# ======================================================================================

def test_an_ordinary_anchored_session_is_1306_minutes_inclusive():
    """18:00 to 15:45 the next day, both endpoints included. The repo's inclusive convention.

    The number is asserted against a literal here and DERIVED in the module, which is the
    only arrangement where a change to the derivation fails a test.
    """
    assert D.expected_bar_count(dt.date(2026, 6, 10)) == 1306
    assert (24 * 60 - ANCHOR) + FLAT + 1 == 1306


def test_the_expected_count_is_derived_from_the_clock_and_not_a_constant():
    """The two sessions that span a DST transition. 1,306 is wrong for both.

    No real anchored session crosses a transition, so this uses the hypothetical
    Saturday-anchored session that does. If the derivation were the constant 1,306 - or naive
    wall-clock subtraction - both of these would return 1,306 and the test would fail.
    """
    spring = D.expected_bar_count(dt.date(2026, 3, 8))     # anchored Sat 7 Mar 18:00 EST
    fall = D.expected_bar_count(dt.date(2026, 11, 1))      # anchored Sat 31 Oct 18:00 EDT
    assert spring == 1306 - 60, "an hour vanishes at the spring transition"
    assert fall == 1306 + 60, "an hour repeats at the fall transition"


def test_the_expected_minutes_run_from_the_anchor_to_the_flatten_inclusive():
    m = D.expected_minutes(dt.date(2026, 6, 10))
    first, last = m[0].astimezone(TIMEZONE), m[-1].astimezone(TIMEZONE)
    assert (first.hour, first.minute) == FROZEN.session_anchor
    assert first.date() == dt.date(2026, 6, 9), "the anchor is the PREVIOUS calendar day"
    assert (last.hour, last.minute) == FROZEN.hard_flatten
    assert last.date() == dt.date(2026, 6, 10)


def test_every_expected_minute_is_exactly_sixty_seconds_after_the_last():
    m = D.expected_minutes(dt.date(2026, 11, 1))           # the long, fall-back session
    gaps = {(b - a).total_seconds() for a, b in zip(m, m[1:], strict=False)}
    assert gaps == {60.0}


def test_a_session_that_would_run_into_the_next_ones_anchor_is_refused():
    """The real invariant. A session ending at 19:00 would overlap the next 18:00 anchor and
    two consecutive sessions would claim the same bars."""
    bad = FROZEN.__class__(hard_flatten=(19, 0))
    with pytest.raises(ValueError, match="next session's anchor"):
        D.expected_minutes(dt.date(2026, 6, 10), bad)
    with pytest.raises(ValueError, match="does not precede the anchor"):
        D.expected_bar_count(dt.date(2026, 6, 10), bad)


def test_one_anchored_session_is_not_split_at_midnight(store):
    """THE REQUIREMENT: 18:00->midnight and midnight->09:30 must not become two sessions."""
    d = store(synth_session(dt.date(2026, 6, 10)))
    assert len(d.sessions) == 1
    s = d.sessions[0]
    dates = {b.timestamp.astimezone(TIMEZONE).date() for b in s.bars}
    assert dates == {dt.date(2026, 6, 9), dt.date(2026, 6, 10)}, \
        "one session, two calendar dates - which is exactly the point"
    assert s.trading_day == dt.date(2026, 6, 10)
    assert len(s.bars) == 1306


def test_the_loader_and_the_engine_agree_about_which_day_a_bar_is_in(store):
    """A silent disagreement here would be invisible: both would look internally consistent."""
    d = store(synth_session(dt.date(2026, 6, 10)))
    s = d.sessions[0]
    assert all(trading_day(b.timestamp, ANCHOR) == s.trading_day for b in s.bars)


def test_the_bars_are_ascending_and_unique(store):
    d = store(synth_session(dt.date(2026, 6, 10)))
    ts = [b.timestamp for b in d.sessions[0].bars]
    assert ts == sorted(ts)
    assert len(set(ts)) == len(ts)


def test_a_usable_session_starts_at_the_anchor_and_ends_at_the_flatten(store):
    d = store(synth_session(dt.date(2026, 6, 10)))
    s = d.sessions[0]
    assert s.usable
    first, last = (b.timestamp.astimezone(TIMEZONE) for b in (s.bars[0], s.bars[-1]))
    assert (first.hour, first.minute) == (18, 0)
    assert (last.hour, last.minute) == (15, 45)


def test_out_of_order_input_is_sorted_rather_than_trusted(store):
    rows = synth_session(dt.date(2026, 6, 10))
    shuffled = rows[900:] + rows[:900]
    d = store(shuffled)
    s = d.sessions[0]
    assert s.usable and len(s.bars) == 1306
    assert [b.timestamp for b in s.bars] == sorted(b.timestamp for b in s.bars)


def test_the_overnight_and_rth_halves_add_up(store):
    d = store(synth_session(dt.date(2026, 6, 10)))
    s = d.sessions[0]
    assert s.overnight_bars == 930, "18:00 to 09:29 inclusive"
    assert s.rth_bars == 376, "09:30 to 15:45 inclusive"
    assert s.overnight_bars + s.rth_bars == 1306


def test_the_bars_handed_out_are_the_engines_own_bar_type(store):
    """The data contract. `Bar.__post_init__` is what refuses a naive stamp or an
    impossible OHLC, so handing out anything else would move the validation out of the
    engine's reach."""
    d = store(synth_session(dt.date(2026, 6, 10)))
    bars = d.sessions[0].bars
    assert isinstance(bars, tuple) and all(type(b) is Bar for b in bars)
    assert all(b.timestamp.tzinfo is not None for b in bars)


# ======================================================================================
# THE SESSION BOUNDARIES, TO THE SECOND
# ======================================================================================

#: Every boundary the frozen specification names, probed one second either side. Bars are
#: 1-minute and START-stamped, so 17:59:59 belongs to the 17:59 bar and 18:00:01 belongs to
#: the 18:00 bar - the second never selects a bar of its own, and the table says so rather
#: than leaving it to be re-derived at each call site.
BOUNDARIES: tuple[tuple[str, str, bool, str], ...] = (
    # instant (ET)              the bar it falls in   inside the session?   trading day
    ("2026-06-09 17:59:59",     "17:59",  False, "2026-06-09"),
    ("2026-06-09 18:00:00",     "18:00",  True,  "2026-06-10"),
    ("2026-06-09 18:00:01",     "18:00",  True,  "2026-06-10"),
    ("2026-06-10 09:44:59",     "09:44",  True,  "2026-06-10"),
    ("2026-06-10 09:45:00",     "09:45",  True,  "2026-06-10"),
    ("2026-06-10 15:29:59",     "15:29",  True,  "2026-06-10"),
    ("2026-06-10 15:30:00",     "15:30",  True,  "2026-06-10"),
    ("2026-06-10 15:30:01",     "15:30",  True,  "2026-06-10"),
    ("2026-06-10 15:44:59",     "15:44",  True,  "2026-06-10"),
    ("2026-06-10 15:45:00",     "15:45",  True,  "2026-06-10"),
    ("2026-06-10 15:45:01",     "15:45",  True,  "2026-06-10"),
    ("2026-06-10 15:46:00",     "15:46",  False, "2026-06-10"),
    ("2026-06-10 17:59:59",     "17:59",  False, "2026-06-10"),
    ("2026-06-10 18:00:00",     "18:00",  True,  "2026-06-11"),
)


@pytest.mark.parametrize("instant,bar_hm,inside,day", BOUNDARIES)
def test_the_session_boundaries_to_the_second(instant, bar_hm, inside, day):
    when = dt.datetime.fromisoformat(instant).replace(tzinfo=TIMEZONE)
    minute = when.replace(second=0, microsecond=0)
    assert minute.strftime("%H:%M") == bar_hm, "the bar a second falls in"

    m = _hm(minute)
    assert ((m >= ANCHOR) or (m <= FLAT)) is inside
    assert trading_day(minute, ANCHOR) == dt.date.fromisoformat(day)


def test_the_boundary_minutes_are_exactly_the_ones_the_spec_names():
    assert _hm(dt.datetime(2026, 6, 9, 18, 0, tzinfo=TIMEZONE)) == FROZEN.anchor_minute()
    assert _hm(dt.datetime(2026, 6, 10, 9, 45, tzinfo=TIMEZONE)) == \
        FROZEN.minute_of("monitor_start")
    assert _hm(dt.datetime(2026, 6, 10, 15, 30, tzinfo=TIMEZONE)) == \
        FROZEN.minute_of("last_entry")
    assert _hm(dt.datetime(2026, 6, 10, 15, 45, tzinfo=TIMEZONE)) == FLAT


def test_each_named_boundary_bar_is_present_in_a_complete_session(store):
    """The four wall-clock instants the strategy acts on all exist as bars, once each."""
    d = store(synth_session(dt.date(2026, 6, 10)))
    minutes = [_hm(b.timestamp) for b in d.sessions[0].bars]
    for named in ("session_anchor", "monitor_start", "last_entry", "hard_flatten"):
        assert minutes.count(FROZEN.minute_of(named)) == 1, named
    assert minutes[0] == FROZEN.anchor_minute() and minutes[-1] == FLAT


# ======================================================================================
# B. GOLDEN SESSIONS FROM THE REAL STORE
# ======================================================================================

@needs_store
def test_golden_the_census_of_the_es_store(es):
    """The exact shape of the ES store as certified. A change here is a data change."""
    assert len(es.sessions) == 327
    assert es.by_status() == {"COMPLETE": 313, "TRUNCATED_END": 14}
    assert len(es.usable()) == 313


@needs_store
def test_golden_a_complete_es_session(es):
    s = next(x for x in es.sessions if x.trading_day == dt.date(2026, 3, 9))
    assert s.usable and len(s.bars) == 1306 == s.quality.expected_bars
    assert s.quality.first_et == "2026-03-08 18:00"
    assert s.quality.last_et == "2026-03-09 15:45"
    assert s.contract == "ESH6"
    assert s.quality.missing_count == 0 and s.quality.duplicate_timestamps == 0


@needs_store
def test_golden_the_fourteen_truncated_es_sessions_are_all_end_truncations(es):
    """Every short session on this store is a venue early close, not an interior outage.

    The distinguishing property is measured, not assumed: the absent minutes form one run
    reaching the session's final minute, and the 18:00 anchor is present in all fourteen.
    """
    short = [s for s in es.sessions if s.quality.status is D.SessionStatus.TRUNCATED_END]
    assert len(short) == 14
    for s in short:
        assert s.quality.has_anchor and not s.quality.has_flatten
        assert not s.usable
        assert s.quality.first_et.endswith("18:00")
    ends = {s.quality.last_et[-5:] for s in short}
    assert ends == {"12:59", "13:14", "09:14"}, \
        "13:00, 13:15 and 09:15 closes - the published CME equity-index holiday schedule"


@needs_store
def test_golden_good_friday_has_no_rth_at_all(es):
    s = next(x for x in es.sessions if x.trading_day == dt.date(2026, 4, 3))
    assert s.quality.status is D.SessionStatus.TRUNCATED_END
    assert s.quality.actual_bars == 915 and s.quality.missing_count == 391
    assert s.quality.last_et == "2026-04-03 09:14"


@needs_store
def test_golden_a_session_missing_only_its_anchor_bar_is_still_refused():
    """1,305 of 1,306 is 99.92% complete and completely unusable.

    NQ 2025-06-10 has every minute except 18:00. A count-based or percentage-based
    completeness rule accepts it; the VWAP then anchors at 18:01 and every band, zone test
    and regime decision for that whole day is computed against an undefined series.
    """
    nq = loaded("NQ")
    s = next(x for x in nq.sessions if x.trading_day == dt.date(2025, 6, 10))
    assert s.quality.actual_bars == 1305 and s.quality.expected_bars == 1306
    assert s.quality.missing_minutes == ("18:00",)
    assert s.quality.status is D.SessionStatus.NO_ANCHOR
    assert not s.usable
    assert s.bars == (), "a refused session carries no bars at all"


@needs_store
def test_no_usable_session_anywhere_spans_two_contracts():
    for sym in ("ES", "NQ", "MES", "MNQ"):
        d = loaded(sym)
        for s in d.usable():
            assert len(s.quality.contracts) == 1, f"{sym} {s.trading_day}"


@needs_store
def test_a_usable_session_is_bit_for_bit_reproducible(es):
    again = D.load_anchored(STORE / "ES.parquet", "ES")
    a = {s.trading_day: s.content_hash() for s in es.usable()}
    b = {s.trading_day: s.content_hash() for s in again.usable()}
    assert a == b


# ======================================================================================
# C. TIMEZONE AND DAYLIGHT SAVING
# ======================================================================================

def test_the_module_hard_codes_no_utc_offset():
    """Structural. A hard-coded -04:00 or -05:00 is right for half the year and silent."""
    body = _code_only(DATA_MODULE)
    for bad in (r"utc-4", r"utc-5", r"\bEST\b", r"\bEDT\b", r"timedelta\(hours=-?[45]\)",
                r"[\"\-]0[45]:00\""):
        assert not re.search(bad, body, re.IGNORECASE), f"hard-coded offset {bad!r}"
    assert "tz_localize" not in body, "localising is how a naive frame acquires a wrong clock"
    assert "TIMEZONE" in body, "the venue clock comes from the frozen spec, not a literal"


@needs_store
def test_the_spring_transition_session_on_real_data(es):
    """2026-03-08 02:00 EST -> 03:00 EDT. The session anchored that evening is NORMAL.

    This is the honest result and it is worth pinning: the transition happens sixteen hours
    before the anchor, so the session is 1,306 bars and entirely on EDT. A loader that
    "handled DST" by adjusting this session would be wrong.
    """
    s = next(x for x in es.sessions if x.trading_day == dt.date(2026, 3, 9))
    assert len(s.bars) == 1306
    offsets = {b.timestamp.astimezone(TIMEZONE).utcoffset() for b in s.bars}
    assert offsets == {dt.timedelta(hours=-4)}, "the whole session is on EDT"


@needs_store
def test_no_real_anchored_session_contains_a_transition(es):
    """Measured, not asserted from the calendar: every session has ONE UTC offset."""
    for s in es.usable():
        offs = {b.timestamp.astimezone(TIMEZONE).utcoffset() for b in s.bars}
        assert len(offs) == 1, f"{s.trading_day} spans a DST transition"


def test_a_session_spanning_the_spring_forward_loses_an_hour(store):
    """The hypothetical Saturday-anchored session, built and loaded end to end.

    02:00-02:59 ET does not exist on 2026-03-08, and the session is 1,246 bars. Both facts
    fall out of the UTC walk; neither is special-cased anywhere.
    """
    day = dt.date(2026, 3, 8)
    d = store(synth_session(day))
    s = d.sessions[0]
    assert s.usable, s.quality.reasons
    assert len(s.bars) == 1246 == D.expected_bar_count(day)
    labels = {b.timestamp.astimezone(TIMEZONE).strftime("%H:%M") for b in s.bars}
    assert "01:59" in labels and "03:00" in labels
    assert not any(x.startswith("02:") for x in labels), "02:00-02:59 EST never happened"
    assert {b.timestamp.astimezone(TIMEZONE).utcoffset() for b in s.bars} == {
        dt.timedelta(hours=-5), dt.timedelta(hours=-4)}


def test_a_session_spanning_the_fall_back_gains_an_hour(store):
    """1,366 bars, and 01:00-01:59 ET happens TWICE with distinct UTC instants."""
    day = dt.date(2026, 11, 1)
    d = store(synth_session(day))
    s = d.sessions[0]
    assert s.usable, s.quality.reasons
    assert len(s.bars) == 1366 == D.expected_bar_count(day)
    ones = [b for b in s.bars
            if b.timestamp.astimezone(TIMEZONE).strftime("%H:%M") == "01:30"]
    assert len(ones) == 2, "the repeated hour"
    assert ones[0].timestamp != ones[1].timestamp, "distinct instants, same wall clock"
    assert (ones[1].timestamp - ones[0].timestamp) == dt.timedelta(hours=1)
    assert {b.timestamp.astimezone(TIMEZONE).utcoffset() for b in s.bars} == {
        dt.timedelta(hours=-4), dt.timedelta(hours=-5)}


def test_a_hole_in_the_repeated_hour_is_still_found_by_position(store):
    """Label arithmetic would confuse the two 01:30s. The classifier is positional."""
    day = dt.date(2026, 11, 1)
    mins = D.expected_minutes(day)
    first_one_thirty = next(i for i, m in enumerate(mins)
                            if m.astimezone(TIMEZONE).strftime("%H:%M") == "01:30")
    d = store(synth_session(day, drop=(first_one_thirty,)))
    s = d.sessions[0]
    assert s.quality.status is D.SessionStatus.HOLED
    assert s.quality.missing_minutes == ("01:30",)
    assert s.quality.actual_bars == 1365


def test_a_naive_timestamp_cannot_reach_a_bar():
    with pytest.raises(ValueError, match="timezone-naive"):
        Bar(timestamp=dt.datetime(2026, 6, 10, 9, 45), open=1.0, high=1.0, low=1.0,
            close=1.0, volume=1.0)


def test_the_venue_clock_is_the_repositorys_one_timezone_object():
    assert TIMEZONE.key == "America/New_York"
    assert TIMEZONE is not ZoneInfo("UTC")


# ======================================================================================
# D. ROLLS - preserved, never adjusted
# ======================================================================================

@needs_store
def test_golden_the_es_rolls_and_their_measured_gaps(es):
    assert [(r.previous_contract, r.new_contract) for r in es.rolls] == [
        ("ESU5", "ESZ5"), ("ESZ5", "ESH6"), ("ESH6", "ESM6"), ("ESM6", "ESU6")]
    for r in es.rolls:
        assert abs(r.price_difference) > 10.0, "these are real, large discontinuities"
        assert 0.5 < abs(r.price_difference_pct) < 2.0


@needs_store
def test_the_roll_discontinuity_is_preserved_and_not_normalised(es):
    """THE POLICY: a roll gap is a fact about the series, not an error to be smoothed.

    Read straight out of the canonical frame, the bar before each roll and the bar after it
    differ by the full contract spread. If anything in this path back-adjusted, spliced with
    an offset or normalised, these differences would be near zero.
    """
    ds = canonical("ES")
    f = ds.frame.reset_index(drop=True)
    sym = f["contract_symbol"].astype(str)
    at = f.index[sym.ne(sym.shift()) & (f.index > 0)]
    for i in at:
        measured = float(f.loc[i, "open"]) - float(f.loc[i - 1, "close"])
        assert abs(measured) > 10.0
        matching = [r for r in es.rolls if r.at_utc == str(f.loc[i, "timestamp"])]
        assert matching and matching[0].price_difference == pytest.approx(measured)
    assert ds.manifest.roll.adjustment.value == "NONE"
    assert ds.manifest.data_form.value == "CONTINUOUS_UNADJUSTED"


@needs_store
def test_the_measured_rolls_match_the_manifests_declared_roll_timestamps(es):
    declared = set(es.source_manifest.roll.roll_timestamps)
    assert {r.at_utc for r in es.rolls} == declared


@needs_store
def test_a_roll_at_the_anchor_is_reported_as_opening_a_session_not_polluting_one(es):
    """A three-valued field, because a boolean here says the opposite of what is true.

    A roll AT 18:00 is the first bar of a NEW session, so that session is entirely the new
    contract and nothing is mixed. Recording it as "inside an anchored session" is true of
    the bar and would read, correctly on its face and wrongly in substance, as three
    contaminated sessions on a store whose contaminated-session count is zero.
    """
    positions = [r.position for r in es.rolls]
    assert positions == ["AT_THE_ANCHOR", "BETWEEN_SESSIONS",
                         "AT_THE_ANCHOR", "AT_THE_ANCHOR"]
    assert "INSIDE_A_SESSION" not in positions
    assert not [s for s in es.sessions
                if s.quality.status is D.SessionStatus.MULTI_CONTRACT]

    #: and the session each anchor-roll opens is single-contract, on the NEW contract
    for r in es.rolls:
        if r.position != "AT_THE_ANCHOR":
            continue
        opened = next(s for s in es.sessions
                      if str(s.trading_day) == r.trading_day)
        assert opened.quality.contracts == (r.new_contract,)

    assert {row["position"] for row in es.manifest()["rolls"]} == {
        "AT_THE_ANCHOR", "BETWEEN_SESSIONS"}


def test_a_roll_genuinely_inside_a_session_is_labelled_as_such(store):
    """The constructed case the real store cannot supply, so the label is not vacuous."""
    day = dt.date(2026, 6, 10)
    rows = synth_session(day, contract="ESM6")
    for r in rows[700:]:
        r["contract"] = "ESU6"
        r["o"] = r["h"] = r["l"] = r["c"] = r["c"] + 55.0
    d = store(rows)
    assert [r.position for r in d.rolls] == ["INSIDE_A_SESSION"]
    assert d.sessions[0].quality.status is D.SessionStatus.MULTI_CONTRACT


@needs_store
def test_the_real_rolls_land_on_a_session_boundary_and_never_inside_one(es):
    """Measured. Three of the four ES rolls land exactly on an 18:00 anchor and the fourth
    lands in the 15:45-18:00 dead zone, which is why no session is MULTI_CONTRACT."""
    for r in es.rolls:
        minute = dt.datetime.fromisoformat(r.at_utc).astimezone(TIMEZONE)
        m = minute.hour * 60 + minute.minute
        assert m == ANCHOR or FLAT < m < ANCHOR, f"roll at {r.at_et} sits inside a session"
    assert not [s for s in es.sessions if s.quality.status is D.SessionStatus.MULTI_CONTRACT]


def test_a_roll_inside_a_session_is_refused(store):
    """Constructed, because the real store has none. A session priced across two contracts
    turns a roll gap into a return."""
    day = dt.date(2026, 6, 10)
    rows = synth_session(day, contract="ESM6")
    for r in rows[700:]:
        r["contract"] = "ESU6"
        r["o"] = r["h"] = r["l"] = r["c"] = r["c"] + 55.0
    d = store(rows)
    s = d.sessions[0]
    assert s.quality.status is D.SessionStatus.MULTI_CONTRACT
    assert not s.usable and s.bars == ()
    assert s.quality.contracts == ("ESM6", "ESU6")


def test_the_loader_selects_no_contract_and_says_so():
    """Structural. Contract choice happened at fetch time under a calendar rule; a loader
    that re-chose could choose using information the day did not have."""
    body = _code_only(DATA_MODULE)
    for forbidden in ("idxmax", "nlargest", "most_liquid", "argmax", "rolling",
                      "open_interest >", "open_interest.", "shift(-"):
        assert forbidden not in body, f"{forbidden!r} would be a data-derived roll choice"
    #: The one `shift` in the module is `sym.shift()` - the PREVIOUS row, used to notice that
    #: the contract column changed. A negative period there would be reading the next bar.
    assert "shift()" in body
    assert "chosen at FETCH time by a calendar rule" in DATA_MODULE.read_text(
        encoding="utf-8"), "the manifest must SAY where the contract came from"


def test_a_later_contract_change_cannot_alter_an_earlier_session(store):
    """Behavioural companion to the structural test: the future is not consulted."""
    a = synth_session(dt.date(2026, 6, 10), contract="ESM6", base=6000.0)
    b = synth_session(dt.date(2026, 6, 11), contract="ESM6", base=6000.0)
    b2 = synth_session(dt.date(2026, 6, 11), contract="ESU6", base=6055.0)
    first = store(a + b).sessions[0]
    second = store(a + b2).sessions[0]
    assert first.content_hash() == second.content_hash()
    assert first.contract == second.contract == "ESM6"


# ======================================================================================
# E. CORRUPTION - found, reported, never repaired
# ======================================================================================

def test_an_interior_hole_is_reported_and_the_session_refused(store):
    d = store(synth_session(dt.date(2026, 6, 10), drop=(500, 501, 502)))
    s = d.sessions[0]
    assert s.quality.status is D.SessionStatus.HOLED
    assert s.quality.missing_count == 3 and s.quality.actual_bars == 1303
    assert not s.usable
    assert "volume-weighted" in s.quality.reasons[0]


def test_an_end_truncation_is_distinguished_from_an_interior_hole(store):
    early = store(synth_session(dt.date(2026, 6, 10), keep=1140)).sessions[0]
    holed = store(synth_session(dt.date(2026, 6, 10), drop=(1200,))).sessions[0]
    assert early.quality.status is D.SessionStatus.TRUNCATED_END
    assert holed.quality.status is D.SessionStatus.HOLED
    assert not early.usable and not holed.usable


def test_a_missing_anchor_outranks_a_missing_tail(store):
    """Both defects at once. The anchor is the one that makes the VWAP undefined."""
    rows = synth_session(dt.date(2026, 6, 10), drop=(0,), keep=1140)
    s = store(rows).sessions[0]
    assert s.quality.status is D.SessionStatus.NO_ANCHOR


def test_a_duplicate_timestamp_is_caught(store):
    rows = synth_session(dt.date(2026, 6, 10))
    rows.insert(400, dict(rows[400]))
    s = store(rows).sessions[0]
    assert s.quality.status is D.SessionStatus.CORRUPT
    assert s.quality.duplicate_timestamps == 1
    assert not s.usable


def test_a_failing_quality_report_stops_the_load_before_a_session_is_even_cut(tmp_path):
    """The canonical gate runs first and fails closed. The tests above deliberately pass
    `require_quality=False` so they can inspect a broken dataset; the DEFAULT does not."""
    rows = synth_session(dt.date(2026, 6, 10))
    rows.insert(400, dict(rows[400]))
    p = write_store(tmp_path / "ES.parquet", rows)
    with pytest.raises(DataQualityError, match="must not enter research"):
        D.load_anchored(p, "ES")


def test_a_clean_synthetic_session_passes_the_canonical_gate_outright(tmp_path):
    """The companion. If every synthetic frame merely WARNed, the test above would prove
    nothing about duplicates in particular."""
    p = write_store(tmp_path / "ES.parquet", synth_session(dt.date(2026, 6, 10)))
    d = D.load_anchored(p, "ES")
    assert d.source_manifest.quality.status == "PASS"
    assert d.sessions[0].usable


def test_a_collision_two_different_bars_at_one_timestamp_is_caught(store):
    rows = synth_session(dt.date(2026, 6, 10))
    twin = dict(rows[400])
    twin["c"] = twin["o"] = twin["h"] = twin["l"] = 6100.0
    rows.insert(401, twin)
    s = store(rows).sessions[0]
    assert s.quality.status is D.SessionStatus.CORRUPT
    assert s.quality.duplicate_timestamps == 1


def test_an_impossible_bar_is_caught(store):
    rows = synth_session(dt.date(2026, 6, 10))
    rows[600]["h"], rows[600]["l"] = 5990.0, 6010.0          # high below low
    s = store(rows).sessions[0]
    assert s.quality.status is D.SessionStatus.CORRUPT
    assert s.quality.invalid_bars == 1
    assert not s.usable


def test_a_close_outside_the_bar_range_is_caught(store):
    rows = synth_session(dt.date(2026, 6, 10))
    rows[600]["c"] = rows[600]["h"] + 5.0
    s = store(rows).sessions[0]
    assert s.quality.status is D.SessionStatus.CORRUPT
    assert s.quality.invalid_bars == 1


def test_negative_volume_is_caught(store):
    rows = synth_session(dt.date(2026, 6, 10))
    rows[600]["v"] = -1.0
    s = store(rows).sessions[0]
    assert s.quality.status is D.SessionStatus.CORRUPT
    assert s.quality.invalid_bars == 1


def test_zero_volume_is_counted_and_kept(store):
    """A zero-volume minute is a real market state, not a defect. It is NOT dropped - it
    contributes no VWAP weight and the count travels with the session so a thin session is
    visible as thin."""
    rows = synth_session(dt.date(2026, 6, 10))
    for r in rows[600:610]:
        r["v"] = 0.0
    s = store(rows).sessions[0]
    assert s.usable
    assert s.quality.zero_volume_bars == 10
    assert len(s.bars) == 1306
    assert any("zero volume" in r for r in s.quality.reasons)


def test_a_contract_from_the_wrong_family_is_refused_by_the_adapter(tmp_path):
    rows = synth_session(dt.date(2026, 6, 10), contract="ESM6")
    rows[900]["contract"] = "NQM6"
    p = write_store(tmp_path / "ES.parquet", rows)
    with pytest.raises(AdapterError, match="more than one root"):
        D.load_anchored(p, "ES", require_quality=False)


def test_an_instrument_that_disagrees_with_the_file_is_refused(tmp_path):
    p = write_store(tmp_path / "ES.parquet", synth_session(dt.date(2026, 6, 10)))
    with pytest.raises(AdapterError, match="Refusing rather than trusting"):
        D.load_anchored(p, "NQ", require_quality=False)


def test_a_missing_store_fails_closed(tmp_path):
    with pytest.raises(FileNotFoundError, match="fails closed"):
        D.load_anchored(tmp_path / "nothing.parquet", "ES")


def test_a_store_with_no_anchored_session_is_refused_rather_than_returned(tmp_path):
    """An EMPTY dataset is the most dangerous possible return value.

    A backtest that scores zero sessions reports no loss, no drawdown and no trades, and
    reads exactly like a strategy that never triggered. This repository has already been bitten
    by that shape once - `flatten_leg_dropped__the_original_2026_defect` - so the loader
    raises instead.

    The bars here are all in the 15:46-17:59 dead zone, which belongs to no anchored session.
    """
    day = dt.date(2026, 6, 10)
    dead = [dt.datetime(day.year, day.month, day.day, 16, m, tzinfo=TIMEZONE)
            .astimezone(dt.UTC) for m in range(0, 60)]
    p = write_store(tmp_path / "ES.parquet", _rows(dead, "ESM6", 6000.0, 500.0))
    with pytest.raises(ValueError, match="not one of them falls in an 18:00-anchored"):
        D.load_anchored(p, "ES", require_quality=False)


def test_an_adjusted_series_is_refused_as_an_execution_source(tmp_path):
    """Back-adjusted prices are a valid research input and an invalid fill price.

    Their levels are arithmetic rather than quotes - a roll gap has been spread backwards
    through the history - so a 15-point stop would be tested against a price no venue showed.
    The canonical layer refuses an adjusted execution source on the other path; this one
    refuses it here rather than inheriting the assumption.
    """
    from quant_brain.data.manifest import AdjustmentMethod, DataForm, RollMethod, RollSpec

    rows = synth_session(dt.date(2026, 6, 10), contract="ESM6")
    frame = pd.DataFrame(rows).rename(columns={"t": "ts", "o": "Open", "h": "High",
                                               "l": "Low", "c": "Close", "v": "Vol"})
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    p = tmp_path / "adjusted.parquet"
    frame.to_parquet(p, index=False)

    with pytest.raises(ValueError, match="must not run on them"):
        D.load_anchored(
            p, "ES", adapter="generic_table", require_quality=False,
            data_form=DataForm.CONTINUOUS_BACK_ADJUSTED, session_timezone="America/New_York",
            bar_interval="1min", provider="somebody-else",
            roll=RollSpec(method=RollMethod.CALENDAR_DAYS_BEFORE_EXPIRY,
                          adjustment=AdjustmentMethod.RATIO, days_before_expiry=8,
                          non_reconstructible_reason="a fixture, not a real series"),
            columns={"timestamp": "ts", "open": "Open", "high": "High", "low": "Low",
                     "close": "Close", "volume": "Vol", "contract_symbol": "contract"})


def test_the_same_session_loads_from_a_completely_different_source_shape(tmp_path):
    """DATA-SOURCE AGNOSTICISM, demonstrated rather than asserted.

    Same bars, different file: different column names, a different provider, a different
    declared roll, and `generic_table` instead of `ibkr_futures`. The loader knows none of
    that - `adapter` names the reader and `**adapter_kwargs` reaches it unchanged - so the
    sessions that come out are bar-for-bar the ones the IBKR path produces.
    """
    from quant_brain.data.manifest import AdjustmentMethod, DataForm, RollMethod, RollSpec

    rows = synth_session(dt.date(2026, 6, 10), contract="ESM6")
    native = D.load_anchored(write_store(tmp_path / "ES.parquet", rows), "ES",
                             require_quality=False)

    frame = pd.DataFrame(rows).rename(columns={"t": "epoch_utc", "o": "OPEN", "h": "HIGH",
                                               "l": "LOW", "c": "LAST", "v": "qty",
                                               "contract": "sym"})
    frame["epoch_utc"] = pd.to_datetime(frame["epoch_utc"], utc=True)
    foreign_path = tmp_path / "somebody_elses_export.parquet"
    frame.to_parquet(foreign_path, index=False)

    foreign = D.load_anchored(
        foreign_path, "ES", adapter="generic_table", require_quality=False,
        data_form=DataForm.CONTINUOUS_UNADJUSTED, session_timezone="America/New_York",
        bar_interval="1min", provider="somebody-else",
        roll=RollSpec(method=RollMethod.VOLUME_CROSSOVER, adjustment=AdjustmentMethod.NONE,
                      non_reconstructible_reason="the export states no roll trigger"),
        columns={"timestamp": "epoch_utc", "open": "OPEN", "high": "HIGH", "low": "LOW",
                 "close": "LAST", "volume": "qty", "contract_symbol": "sym"})

    assert [s.trading_day for s in foreign.usable()] == [s.trading_day
                                                         for s in native.usable()]
    assert foreign.usable()[0].content_hash() == native.usable()[0].content_hash()
    assert foreign.usable()[0].bars == native.usable()[0].bars

    #: The provenance differs, and must: same bars, a different statement about where they
    #: came from and how the contract was chosen.
    assert foreign.manifest()["source"]["provider"] == "somebody-else"
    assert foreign.manifest()["roll_method"] == "VOLUME_CROSSOVER"
    assert foreign.manifest()["manifest_id"] != native.manifest()["manifest_id"]


def test_the_loader_names_no_vendor_column():
    """Structural. `t/o/h/l/c/v` are IBKR's spellings and live only in the adapter."""
    #: `ast.unparse` normalises every string literal to single quotes, so the probes are
    #: written that way; searching for double-quoted forms would pass vacuously.
    body = _code_only(DATA_MODULE)
    for vendor in ("'t'", "'o'", "'h'", "'l'", "'v'", "'contract'"):
        assert vendor not in body, f"{vendor} is a provider column spelling"
    assert "'ibkr_futures'" in body, "it is the default"
    assert body.count("ibkr") == 1, "and ONLY the default - it appears exactly once"


def test_nothing_in_this_path_repairs_data():
    """Structural, and the most important test in the file.

    Silent repair is the failure mode that produces a beautiful backtest on data that never
    existed. There is no interpolation, no forward fill, no reindex-and-fill and no gap
    bridging anywhere in the module.
    """
    body = _code_only(DATA_MODULE)
    for bad in ("interpolate", "fillna", "ffill", "bfill", "dropna", "drop_duplicates",
                "reindex", "asfreq", "resample", "combine_first", "replace("):
        assert bad not in body, f"{bad!r} repairs data"


@needs_store
def test_every_gap_in_the_store_is_accounted_for_by_the_session_definition(es):
    """The canonical layer WARNs `unexplained_gaps` on all four stores. This explains them.

    Counted straight off the raw series: 326 places where consecutive bars are more than a
    minute apart. Every one of them either begins at the session close - the 15:45-18:00
    maintenance break, extended over weekends - or begins BEFORE 15:45, which is an early
    close. There is no third kind, and the count of the second kind is exactly the count of
    sessions the anchored loader refuses.

    That is the strongest statement available about interior holes: not "none were found"
    but "every absence in the file is attributed, and none of them is inside a session the
    strategy would be fed".
    """
    f = canonical("ES").frame
    et = f["timestamp"].dt.tz_convert(TIMEZONE)
    minutes_apart = f["timestamp"].diff().dt.total_seconds().div(60).fillna(1)

    dead_zone = early_close = 0
    for i in minutes_apart[minutes_apart > 1].index:
        opened_at = _hm(et.iloc[i - 1].to_pydatetime())
        if opened_at >= FLAT:
            dead_zone += 1            # the 15:45-18:00 break, or a weekend on top of it
        else:
            early_close += 1
    total = int((minutes_apart > 1).sum())

    assert total == 326
    assert dead_zone == 312
    assert early_close == 14
    assert dead_zone + early_close == total, "there is no third kind of gap"

    refused = [s for s in es.sessions
               if s.quality.status is D.SessionStatus.TRUNCATED_END]
    assert len(refused) == early_close == 14
    assert not [s for s in es.sessions if s.quality.status is D.SessionStatus.HOLED]
    assert es.manifest()["totals"]["missing_bars_all_sessions"] == sum(
        s.quality.missing_count for s in refused)


@needs_store
def test_the_long_stale_price_run_carries_no_vwap_weight(es):
    """The `stale_price` WARN is 645 bars with an unchanged close. All 645 print ZERO volume.

    That matters precisely because the VWAP is volume-weighted: a zero-volume bar adds no
    weight, so a run of them cannot drag the average anywhere. `SessionVwap` counts them in
    `bars_in_session` and gives them no weight, which is why the run is a thin market rather
    than a distorted statistic.

    It is the Thanksgiving overnight, and its session is one of the fourteen the loader
    refuses anyway - but the reasoning must not depend on that, because the same shape on a
    complete session would be accepted.
    """
    f = canonical("ES").frame
    unchanged = f["close"].diff() == 0
    run = unchanged.groupby((~unchanged).cumsum()).cumsum()
    end = int(run.idxmax())
    length = int(run.max())
    assert length == 645

    window = f.iloc[end - length:end + 1]
    assert (window["volume"] <= 0).sum() >= length, "the whole run is zero-volume"
    assert float(window["close"].nunique()) == 1.0

    et_start = f["timestamp"].dt.tz_convert(TIMEZONE).iloc[end - length]
    assert et_start.strftime("%Y-%m-%d %H:%M") == "2025-11-27 21:44"

    #: Fed through the real accumulator: the run moves neither the VWAP nor its sigma.
    v = SessionVwap(anchor_minute=ANCHOR)
    v.update(Bar(timestamp=dt.datetime(2026, 6, 9, 18, 0, tzinfo=TIMEZONE),
                 open=20_000.0, high=20_001.0, low=19_999.0, close=20_000.0, volume=500.0))
    before = (v.value, v.sigma, v.bars_in_session)
    anchor = dt.datetime(2026, 6, 9, 18, 0, tzinfo=TIMEZONE)
    for m in range(1, 101):
        v.update(Bar(timestamp=anchor + dt.timedelta(minutes=m),
                     open=20_500.0, high=20_500.0, low=20_500.0, close=20_500.0, volume=0.0))
    assert (v.value, v.sigma) == before[:2], "zero volume moved a volume-weighted average"
    assert v.bars_in_session == before[2] + 100, "but the bars are still counted"


@needs_store
def test_the_mixed_contract_sessions_are_an_rth_artefact_not_an_anchored_one(es):
    """The canonical layer WARNs that 4 ES sessions hold two contracts. None is anchored.

    It counts sessions by `session_date`, the trade day, so a roll AT 18:00 lands inside a
    session under that convention. Under the anchored convention 18:00 is the boundary, so
    the same roll lands between two sessions and neither is mixed. Same file, same rolls,
    two different and both-correct answers - which is why the anchored loader measures
    contract identity itself rather than inheriting the verdict.
    """
    assert canonical("ES").manifest.quality.warn_reasons.count("mixed_contract_session") == 1
    assert len(es.rolls) == 4
    assert not [s for s in es.sessions
                if s.quality.status is D.SessionStatus.MULTI_CONTRACT]
    assert all(len(s.quality.contracts) == 1 for s in es.sessions)


@needs_store
def test_the_upstream_quality_verdict_travels_with_the_dataset(es):
    """Stale prices, unexplained gaps and mixed-contract sessions are the canonical layer's
    job and it does report them. This asserts the anchored loader CARRIES that verdict
    rather than discarding it - a WARN that does not reach the result is a WARN nobody sees.
    """
    m = es.manifest()
    assert m["source"]["quality_status"] == "WARN"
    assert m["source"]["quality_report_hash"]
    assert es.source_manifest.quality.warn_reasons, "WARN with no stated reason is useless"


# ======================================================================================
# F. LOOKAHEAD IN DATA CONSTRUCTION
# ======================================================================================

def test_no_bar_in_a_session_is_stamped_after_the_session_end(store):
    d = store(synth_session(dt.date(2026, 6, 10)))
    end = D.expected_minutes(dt.date(2026, 6, 10))[-1]
    assert all(b.timestamp <= end for b in d.sessions[0].bars)


def test_sessions_do_not_overlap_in_time(store):
    d = store(synth_session(dt.date(2026, 6, 10)) + synth_session(dt.date(2026, 6, 11)))
    a, b = d.sessions
    assert a.bars[-1].timestamp < b.bars[0].timestamp


@needs_store
def test_no_real_session_overlaps_the_next(es):
    u = es.usable()
    for a, b in zip(u, u[1:], strict=False):
        assert a.bars[-1].timestamp < b.bars[0].timestamp


def test_the_vwap_resets_at_the_anchor_and_nowhere_else(store):
    """REQUIREMENT 7, proved by feeding the real accumulator two consecutive sessions.

    Not a strategy run: `SessionVwap` is an indicator, it produces no signal and no fill. The
    assertion is about WHERE the series restarts - exactly once per session, at 18:00, and
    never at midnight, 09:30, 09:45 or the calendar date change.
    """
    d = store(synth_session(dt.date(2026, 6, 10)) + synth_session(dt.date(2026, 6, 11)))
    v = SessionVwap(anchor_minute=ANCHOR)
    reset_at: list[str] = []
    for s in d.sessions:
        for b in s.bars:
            before = v.resets
            v.update(b)
            if v.resets != before:
                reset_at.append(b.timestamp.astimezone(TIMEZONE).strftime("%H:%M"))
    assert reset_at == ["18:00"], "one reset, at the anchor, for the second session"
    assert v.bars_in_session == 1306


def test_the_vwap_does_not_reset_at_midnight_or_at_the_cash_open(store):
    d = store(synth_session(dt.date(2026, 6, 10)))
    v = SessionVwap(anchor_minute=ANCHOR)
    marks: dict[str, float] = {}
    for b in d.sessions[0].bars:
        v.update(b)
        hm = b.timestamp.astimezone(TIMEZONE).strftime("%H:%M")
        if hm in ("23:59", "00:00", "09:29", "09:30", "09:44", "09:45"):
            marks[hm] = v.bars_in_session
    assert v.resets == 0, "a single session must never reset mid-way"
    assert marks["00:00"] == marks["23:59"] + 1, "the count runs straight through midnight"
    assert marks["09:30"] == marks["09:29"] + 1, "and straight through the cash open"
    assert marks["09:45"] == marks["09:44"] + 1, "and through the monitor start"
    assert marks["09:45"] == 946


def test_the_vwap_at_any_bar_depends_only_on_bars_up_to_it(store):
    """Truncation test. If the loader or the accumulator could see forward, a prefix and a
    full session would disagree at the same bar."""
    d = store(synth_session(dt.date(2026, 6, 10)))
    bars = d.sessions[0].bars
    for k in (1, 50, 930, 1200):
        a = SessionVwap(anchor_minute=ANCHOR)
        for b in bars[:k]:
            a.update(b)
        full = SessionVwap(anchor_minute=ANCHOR)
        seen = None
        for i, b in enumerate(bars):
            full.update(b)
            if i == k - 1:
                seen = (full.value, full.sigma)
                break
        assert (a.value, a.sigma) == seen


def test_a_five_minute_bucket_is_invisible_until_its_last_minute_has_closed(store):
    """REQUIREMENT 8. A partial bucket must never masquerade as a completed bar."""
    d = store(synth_session(dt.date(2026, 6, 10)))
    agg = FiveMinuteAggregator()
    v = SessionVwap(anchor_minute=ANCHOR)
    completions: list[str] = []
    for b in d.sessions[0].bars:
        v.update(b)
        done = agg.update(b, v.value)
        hm = b.timestamp.astimezone(TIMEZONE).strftime("%H:%M")
        if done is not None:
            completions.append(hm)
            end = done.end.astimezone(TIMEZONE)
            assert end < b.timestamp.astimezone(TIMEZONE), \
                "a completed bucket ends strictly before the bar that revealed it"
            assert (end.hour * 60 + end.minute) % 5 == 4, "buckets close on :x4 and :x9"
    assert completions[0] == "18:05"
    assert all(int(c[-2:]) % 5 == 0 for c in completions), "revealed on the next :x0/:x5"
    assert len(completions) == 261, "1306 minutes = 261 completed buckets + one forming"


def test_five_minute_buckets_align_to_the_venue_clock_across_midnight(store):
    d = store(synth_session(dt.date(2026, 6, 10)))
    agg, v = FiveMinuteAggregator(), SessionVwap(anchor_minute=ANCHOR)
    for b in d.sessions[0].bars:
        v.update(b)
        agg.update(b, v.value)
    starts = [x.start.astimezone(TIMEZONE) for x in agg.completed]
    assert all((s.hour * 60 + s.minute) % 5 == 0 for s in starts)
    assert all(x.volume == 5 * 500.0 for x in agg.completed), "five minutes of volume each"
    midnight = [s for s in starts if (s.hour, s.minute) == (0, 0)]
    assert len(midnight) == 1, "midnight opens a bucket like any other five-minute mark"


def test_five_minute_buckets_survive_the_spring_transition(store):
    """The hour that does not exist must not merge two buckets or produce a ten-minute bar."""
    d = store(synth_session(dt.date(2026, 3, 8)))
    agg, v = FiveMinuteAggregator(), SessionVwap(anchor_minute=ANCHOR)
    for b in d.sessions[0].bars:
        v.update(b)
        agg.update(b, v.value)
    assert {x.volume for x in agg.completed} == {5 * 500.0}
    spans = {(x.end - x.start).total_seconds() for x in agg.completed}
    assert spans == {240.0}, "start-stamped: four minutes from first stamp to last"


def test_the_manifest_never_reads_ahead_of_its_own_session(store):
    """The per-session record describes only that session's bars."""
    d = store(synth_session(dt.date(2026, 6, 10)) + synth_session(dt.date(2026, 6, 11),
                                                                  drop=(700,)))
    rows = {r["trading_day"]: r for r in d.manifest()["sessions"]}
    assert rows["2026-06-10"]["status"] == "COMPLETE"
    assert rows["2026-06-10"]["missing"] == 0, "the NEXT session's hole is not counted here"
    assert rows["2026-06-11"]["missing"] == 1


# ======================================================================================
# G. EQUIVALENCE WITH THE EXISTING LOADER
# ======================================================================================

@needs_store
def test_the_anchored_and_rth_loaders_agree_bar_for_bar_where_they_overlap(es):
    """EXACT equality, not "close enough".

    `session_source` cuts 09:30-16:00 and the anchored loader cuts 18:00-15:45, so the
    overlap is 09:30-15:45. Every price, every volume and every contract must be identical
    there; the two paths read the same file through the same adapter and any difference is a
    defect in one of them.
    """
    cut = rth("ES")
    mine = {s.trading_day: s for s in es.usable()}

    compared = 0
    for frame in cut.sessions:
        day = pd.Timestamp(frame["day"].iloc[0]).date()
        if day not in mine:
            continue
        theirs = frame[frame["hm"] <= "15:45"]
        #: The RTH half of the anchored session. The upper bound matters as much as the
        #: lower one: without it the 18:00-23:59 overnight bars, whose minute-of-day is also
        #: past 09:30, would join the comparison and it would pass for the wrong reason.
        ours = [b for b in mine[day].bars
                if 9 * 60 + 30 <= _hm(b.timestamp) <= 15 * 60 + 45]
        assert len(ours) == len(theirs) == 376, f"{day}"
        cols = {c: theirs[c].tolist() for c in ("t", "o", "h", "l", "c", "v", "contract")}
        for i, b in enumerate(ours):
            assert b.timestamp == cols["t"][i].to_pydatetime()
            assert (b.open, b.high, b.low, b.close, b.volume) == (
                cols["o"][i], cols["h"][i], cols["l"][i], cols["c"][i], cols["v"][i])
            assert mine[day].contract == cols["contract"][i]
        compared += 1
    assert compared > 250, f"only {compared} sessions compared"


@needs_store
def test_the_overnight_half_matches_the_raw_parquet_read_directly(es):
    """The overnight bars have no second loader to be checked against, so check the FILE.

    `session_source` never sees 18:00-09:29, which is 71% of every anchored session, so the
    equivalence test above can say nothing about it. This reads the parquet with pandas
    alone - no adapter, no canonical frame, no schema, no quality gate, none of the code
    under test - and compares the raw rows in the session's UTC span against the bars the
    loader produced. A transformation anywhere in the canonical path would show up here and
    nowhere else.
    """
    raw = pd.read_parquet(STORE / "ES.parquet")
    raw["t"] = pd.to_datetime(raw["t"], utc=True)
    raw = raw.sort_values("t").reset_index(drop=True)

    checked = 0
    for s in es.usable()[::40] + es.usable()[-1:]:
        lo, hi = s.bars[0].timestamp, s.bars[-1].timestamp
        window = raw[(raw["t"] >= lo) & (raw["t"] <= hi)]
        assert len(window) == len(s.bars) == 1306, s.trading_day
        cols = {c: window[c].tolist() for c in ("t", "o", "h", "l", "c", "v", "contract")}
        for i, bar in enumerate(s.bars):
            assert bar.timestamp == cols["t"][i].to_pydatetime()
            assert (bar.open, bar.high, bar.low, bar.close, bar.volume) == (
                cols["o"][i], cols["h"][i], cols["l"][i], cols["c"][i], cols["v"][i])
            assert s.contract == cols["contract"][i]
        overnight = [b for b in s.bars if _hm(b.timestamp) >= ANCHOR
                     or _hm(b.timestamp) < 9 * 60 + 30]
        assert len(overnight) == 930
        checked += 1
    assert checked >= 8


@needs_store
def test_the_two_loaders_disagree_only_where_their_rules_differ(es):
    """The session counts are NOT equal and that is correct. Every difference is named.

    A session the RTH loader keeps but the anchored one refuses is a day whose RTH half is
    whole and whose overnight half is not - which is precisely the class of day this phase
    exists to catch.
    """
    ds, cut = canonical("ES"), rth("ES")
    theirs = {pd.Timestamp(f["day"].iloc[0]).date() for f in cut.sessions}
    ours = {s.trading_day for s in es.usable()}
    assert (len(theirs), len(ours)) == (310, 313)

    assert not theirs - ours, \
        "every day the RTH loader trusts, the anchored loader trusts too"

    only_anchored = sorted(ours - theirs)
    assert only_anchored == [dt.date(2025, 11, 11), dt.date(2025, 12, 11),
                             dt.date(2026, 2, 10)]

    #: Each of the three is the 15:45-vs-16:00 window difference and nothing else. Two are
    #: days whose 16:00 bar is absent - the RTH loader needs 391 bars and these have 390,
    #: while the anchored session ends at 15:45 and never wanted that bar. The third is the
    #: ESZ5 -> ESH6 roll, which lands AT 16:00: inside the RTH window, so that session is
    #: priced across two contracts and correctly dropped, and outside the anchored window,
    #: so the anchored session is one contract throughout.
    f = ds.frame
    et = f["timestamp"].dt.tz_convert(TIMEZONE)
    hm = et.dt.hour * 60 + et.dt.minute
    for day in (dt.date(2025, 11, 11), dt.date(2026, 2, 10)):
        assert not ((et.dt.date == day) & (hm == 16 * 60)).any(), "no 16:00 bar"
        assert next(x for x in es.sessions if x.trading_day == day).usable
    roll_day = f[(et.dt.date == dt.date(2025, 12, 11)) & (hm >= 15 * 60 + 45)]
    assert set(roll_day["contract_symbol"].astype(str)) == {"ESZ5", "ESH6"}
    assert next(x for x in es.sessions
                if x.trading_day == dt.date(2025, 12, 11)).contract == "ESZ5"
    assert cut.attrition.multi_contract_days == ("2025-12-11",)

    #: And the 14 the anchored loader refuses. Thirteen are also RTH-incomplete; the
    #: fourteenth is Good Friday, which has no RTH bars at all and so never became an RTH
    #: session in the first place.
    refused = {s.trading_day for s in es.rejected()}
    assert len(refused) == 14
    rth_incomplete = {dt.date.fromisoformat(d) for d in cut.attrition.incomplete_days}
    assert refused - rth_incomplete == {dt.date(2026, 4, 3)}


# ======================================================================================
# H. THE MANIFEST
# ======================================================================================

def test_the_manifest_is_deterministic(store):
    rows = synth_session(dt.date(2026, 6, 10))
    a, b = store(rows).manifest(), store(rows).manifest()
    for k in ("manifest_id", "content_hash"):
        assert a[k] == b[k]
    assert a == b


def test_the_manifest_id_does_not_depend_on_how_the_path_was_typed(tmp_path, monkeypatch):
    """Same bytes, two spellings of the same file, one id.

    The id answers "is this the same interpretation of the same data". A path answers "where
    did I find it", and the two were conflated: loading `data/futures/ES.parquet` and
    `C:\\...\\data\\futures\\ES.parquet` produced different manifest ids for byte-identical
    input, which downstream reads as a run on different data. The file's sha256 is hashed and
    settles identity; the path is recorded for a human and excluded from the hash.
    """
    p = write_store(tmp_path / "ES.parquet", synth_session(dt.date(2026, 6, 10)))
    absolute = D.load_anchored(p, "ES", require_quality=False).manifest()

    monkeypatch.chdir(tmp_path)
    relative = D.load_anchored(Path("ES.parquet"), "ES", require_quality=False).manifest()

    assert absolute["manifest_id"] == relative["manifest_id"]
    assert absolute["content_hash"] == relative["content_hash"]
    assert absolute["source"]["file_hashes"] == relative["source"]["file_hashes"]
    #: and each still records the path it was actually given
    assert absolute["source"]["files"] != relative["source"]["files"]
    assert relative["source"]["files"] == ["ES.parquet"]


def test_the_manifest_id_moves_when_a_single_price_moves(store):
    rows = synth_session(dt.date(2026, 6, 10))
    before = store(rows).manifest()
    rows[900]["c"] = rows[900]["c"] + 0.25
    rows[900]["h"] = max(rows[900]["h"], rows[900]["c"])
    after = store(rows).manifest()
    assert before["content_hash"] != after["content_hash"]
    assert before["manifest_id"] != after["manifest_id"]


def test_the_manifest_states_what_the_data_is_and_where_it_came_from(store):
    m = store(synth_session(dt.date(2026, 6, 10))).manifest()
    assert m["loader_version"] == D.LOADER_VERSION
    assert m["adjustment_mode"] == "CONTINUOUS_UNADJUSTED"
    assert m["roll_adjustment"] == "NONE"
    assert m["roll_method"] == "CALENDAR_DAYS_BEFORE_EXPIRY"
    assert m["session_definition"]["anchor_et"] == "18:00"
    assert m["session_definition"]["end_et"] == "15:45"
    assert m["session_definition"]["timezone"] == "America/New_York"
    assert m["source"]["file_hashes"] and m["source"]["manifest_id"]
    assert m["source"]["quality_status"] in ("PASS", "WARN", "FAIL")


def test_the_manifest_accounts_for_every_session_it_refused(store):
    d = store(synth_session(dt.date(2026, 6, 10))
              + synth_session(dt.date(2026, 6, 11), keep=1140)
              + synth_session(dt.date(2026, 6, 12), drop=(3,)))
    m = d.manifest()
    assert m["coverage"]["sessions_found"] == 3
    assert m["coverage"]["sessions_usable"] == 1
    assert m["coverage"]["by_status"] == {
        "COMPLETE": 1, "TRUNCATED_END": 1, "HOLED": 1}
    assert len(m["sessions"]) == 3
    assert all(r["reasons"] for r in m["sessions"] if r["status"] != "COMPLETE")


def test_a_dataset_cannot_exist_without_a_source_manifest():
    """An anonymous dataset must not be constructible. The field has no default."""
    with pytest.raises(TypeError):
        D.AnchoredDataset(instrument="ES", sessions=(), rolls=())      # type: ignore[call-arg]


@needs_store
def test_golden_the_es_manifest_identity(es):
    m = es.manifest()
    assert m["coverage"]["sessions_usable"] == 313
    assert m["totals"]["bars_usable"] == 313 * 1306 == 408_778
    assert m["totals"]["overnight_bars_usable"] == 313 * 930
    assert m["totals"]["rth_bars_usable"] == 313 * 376
    assert m["totals"]["duplicate_timestamps"] == 0
    assert m["totals"]["invalid_bars"] == 0
    assert len(m["rolls"]) == 4


# ======================================================================================
# I. PERFORMANCE
# ======================================================================================

@needs_store
def test_a_full_store_loads_in_seconds_not_minutes():
    t = time.perf_counter()
    d = D.load_anchored(STORE / "ES.parquet", "ES")
    elapsed = time.perf_counter() - t
    assert len(d.usable()) > 300
    assert elapsed < 60.0, f"{elapsed:.1f}s to cut 327 sessions"


# ======================================================================================
# THE PROHIBITION
# ======================================================================================

def test_this_phase_runs_no_strategy():
    """Belt and braces on the brief: the data module must not import the engine.

    A loader that can reach the engine is a loader that can be made to run a backtest by
    accident, which this phase is explicitly forbidden from doing.
    """
    banned = {"engine", "governor", "orders"}

    def imported_modules(path: Path) -> set[str]:
        out: set[str] = set()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module:
                out.add(node.module)
                out.update(f"{node.module}.{a.name}" for a in node.names)
            elif isinstance(node, ast.Import):
                out.update(a.name for a in node.names)
        return out

    for path in (DATA_MODULE, Path(__file__)):
        reached = imported_modules(path)
        assert not {m for m in reached
                    if m.startswith("quant_brain.strategies.vwap_pullback.")
                    and m.rsplit(".", 1)[-1] in banned}, f"{path.name} can reach the engine"
        assert not any("run_strategy" in m for m in reached)


# ======================================================================================
# J. THE RELEASE GATE - policies the owner froze on 2026-09-16
# ======================================================================================

def test_no_rejection_ever_claims_a_calendar_reason(store):
    """A refused session says INCOMPLETE_SESSION. It never says HOLIDAY.

    Deciding between a scheduled venue close and a vendor outage needs a verified CME
    calendar. This repository has a hand-verified NYSE table (`markets/equity_us/calendar.py`)
    and nothing for CME - and the two genuinely differ, most visibly at Good Friday, where
    NYSE closes all day and CME equity-index trades to 09:15. Inferring one from the other
    would put calendar knowledge the day did not have into the record a backtest quotes.
    """
    d = store(synth_session(dt.date(2026, 6, 10))
              + synth_session(dt.date(2026, 6, 11), keep=1140)
              + synth_session(dt.date(2026, 6, 12), drop=(3,)))
    codes = {s.quality.rejection_code for s in d.sessions}
    assert codes == {"", "INCOMPLETE_SESSION"}
    assert all(s.quality.rejection_code == "INCOMPLETE_SESSION" for s in d.rejected())
    assert all(s.quality.rejection_code == "" for s in d.usable())

    banned = ("holiday", "thanksgiving", "juneteenth", "good friday", "christmas",
              "memorial", "labor day", "independence")
    for s in d.sessions:
        blob = " ".join(s.quality.reasons).lower()
        for word in banned:
            assert word not in blob, f"{s.trading_day} infers a calendar: {word!r}"


@needs_store
def test_the_real_refusals_name_no_calendar_either(es):
    banned = ("holiday", "early close", "half-day", "thanksgiving", "juneteenth",
              "good friday", "christmas")
    for s in es.rejected():
        assert s.quality.rejection_code == "INCOMPLETE_SESSION"
        blob = " ".join(s.quality.reasons).lower()
        for word in banned:
            assert word not in blob, f"{s.trading_day}: {word!r}"
        assert "not determined" in blob, "the reason must say the cause is undetermined"
    assert {r["rejection_code"] for r in es.manifest()["sessions"]} == {
        "", "INCOMPLETE_SESSION"}


def test_the_loader_source_classifies_no_session_by_calendar():
    """Structural. No date literal and no holiday name may drive a decision in the module."""
    body = _code_only(DATA_MODULE)
    for word in ("holiday", "HOLIDAY", "easter", "thanksgiving", "good_friday",
                 "EARLY_CLOSE", "is_trading_day", "calendar."):
        assert word not in body, f"{word!r} would be calendar knowledge in the data path"


def test_zero_volume_never_rejects_a_session_however_much_of_it(store):
    """The owner's ruling: no zero-volume threshold exists, so none is invented.

    A session that is ENTIRELY zero-volume is still complete by every objective test - every
    minute is present exactly once, one contract, valid OHLC - so it is fed. The VWAP on it
    is undefined for want of any weight at all, which `SessionVwap.value` reports as NaN
    rather than as a silent zero, and the count travels in the manifest.
    """
    rows = synth_session(dt.date(2026, 6, 10))
    for r in rows:
        r["v"] = 0.0
    s = store(rows).sessions[0]
    assert s.usable, "zero volume is a market state, not a completeness failure"
    assert s.quality.zero_volume_bars == 1306 == len(s.bars)
    assert s.quality.rejection_code == ""

    v = SessionVwap(anchor_minute=ANCHOR)
    for b in s.bars:
        v.update(b)
    assert not v.ready and v.value != v.value, "NaN, never a silent zero"
    assert v.bars_in_session == 1306, "the bars are counted even though none has weight"


def test_a_zero_volume_bar_contributes_exactly_nothing_and_is_not_substituted(store):
    """TP * 0 = 0. No price carried forward, no volume invented, no bar skipped.

    Fed to the accumulator directly rather than through a second load, because a store with
    those bars REMOVED is a holed session and the loader would rightly refuse it - the claim
    under test is about weighting, not about completeness.
    """
    bars = store(synth_session(dt.date(2026, 6, 10))).sessions[0].bars
    zeroed = tuple(
        Bar(timestamp=b.timestamp, open=b.open, high=b.high, low=b.low, close=b.close,
            volume=0.0) if 600 <= i < 700 else b
        for i, b in enumerate(bars))

    with_zeros = SessionVwap(anchor_minute=ANCHOR)
    for b in zeroed:
        with_zeros.update(b)

    without_them = SessionVwap(anchor_minute=ANCHOR)
    for i, b in enumerate(bars):
        if not 600 <= i < 700:
            without_them.update(b)

    assert with_zeros.value == pytest.approx(without_them.value, abs=1e-12)
    assert with_zeros.sigma == pytest.approx(without_them.sigma, abs=1e-12)
    assert with_zeros.bars_in_session == without_them.bars_in_session + 100,         "counted, but weightless"

    #: not a vacuous pass: those hundred bars carry real, varying prices that WOULD have
    #: moved the average had they carried any weight
    assert len({b.close for b in zeroed[600:700]}) > 1
    weighted = SessionVwap(anchor_minute=ANCHOR)
    for b in bars:
        weighted.update(b)
    assert weighted.value != pytest.approx(with_zeros.value, abs=1e-9)


@needs_store
def test_zero_volume_bars_are_visible_in_the_manifest(es):
    m = es.manifest()
    assert m["totals"]["zero_volume_bars"] == 1306
    per = {r["trading_day"]: r["zero_volume_bars"] for r in m["sessions"]}
    assert per["2025-06-10"] == 273
    assert sum(per.values()) == m["totals"]["zero_volume_bars"]
    assert "TP * 0 = 0" in m["session_definition"]["zero_volume_policy"]


# ---- DST: the calendar-day implementation --------------------------------------------

@pytest.mark.parametrize("day", [dt.date(2026, 3, 8), dt.date(2026, 11, 1)])
def test_the_engines_day_roll_is_calendar_arithmetic_across_a_transition(day):
    """`trading_day` adds a DAY to a DATE. Twenty-four ABSOLUTE hours is a different answer.

    The sweep starts the previous midnight, which matters: the three forms agree everywhere
    except 23:00-23:59 on the evening BEFORE a spring-forward, where absolute arithmetic
    lands past midnight into the following trading day. A window that began at the
    transition day itself would cover none of those minutes and the test would pass while
    defending nothing - which is exactly how the first version of this test let the
    corresponding mutation survive.

    Python's own arithmetic on an aware datetime is wall-clock, so
    `(local + timedelta(days=1)).date()` is identical to the form under test; both are
    asserted, and the absolute form is asserted to DIFFER, so the test cannot pass by the
    three having collapsed into one.
    """
    start = dt.datetime(day.year, day.month, day.day, 0, 0,
                        tzinfo=TIMEZONE) - dt.timedelta(days=1)
    diverged = 0
    for m in range(0, 60 * 50):
        when = (start.astimezone(dt.UTC) + dt.timedelta(minutes=m)).astimezone(TIMEZONE)
        got = trading_day(when, ANCHOR)
        expected = when.date() + dt.timedelta(days=1) if _hm(when) >= ANCHOR else when.date()
        assert got == expected

        wall_clock = (when + dt.timedelta(days=1)).date() if _hm(when) >= ANCHOR             else when.date()
        assert got == wall_clock, "Python's aware-datetime arithmetic must agree"

        absolute = (when.astimezone(dt.UTC) + dt.timedelta(days=1)).astimezone(
            TIMEZONE).date() if _hm(when) >= ANCHOR else when.date()
        diverged += int(absolute != got)

    if day == dt.date(2026, 3, 8):
        assert diverged == 60,             "23:00-23:59 the evening before the spring-forward, and nowhere else"
    else:
        assert diverged == 0, "the fall-back does not expose this one"


def test_no_absolute_day_arithmetic_survives_in_the_session_path():
    """Structural, over both modules that decide which day a bar belongs to."""
    indicators = REPO / "quant_brain" / "strategies" / "vwap_pullback" / "indicators.py"
    for module in (DATA_MODULE, indicators):
        body = _code_only(module)
        assert "to_timedelta" not in body, f"{module.name}: absolute day arithmetic"
        assert "Timedelta(" not in body, f"{module.name}: absolute day arithmetic"
    #: and the loader's day roll is the date-plus-date form
    assert "calendar_day + dt.timedelta(days=1)" in DATA_MODULE.read_text(encoding="utf-8")


@needs_store
def test_every_real_session_still_lands_on_one_trading_day(es):
    """The end-to-end DST regression: loader and engine agree for every bar in the store."""
    for s in es.usable()[::25]:
        assert {trading_day(b.timestamp, ANCHOR) for b in s.bars} == {s.trading_day}


# ---- 1m -> 5m causality ---------------------------------------------------------------

def _five_minute_bars(bars):
    """Every COMPLETED 5-minute bar the aggregator produces, with the VWAP it saw."""
    agg, v = FiveMinuteAggregator(), SessionVwap(anchor_minute=ANCHOR)
    for b in bars:
        v.update(b)
        agg.update(b, v.value)
    return [(x.start, x.end, x.open, x.high, x.low, x.close, x.volume, x.vwap_at_close)
            for x in agg.completed]


def test_a_completed_five_minute_bar_cannot_be_changed_by_a_later_minute(store):
    """MUTATE THE FUTURE, AND EVERY EARLIER 5-MINUTE BAR MUST BE BYTE-IDENTICAL.

    The aggregator is an online accumulator, so this ought to be structurally impossible -
    which is exactly why it is worth proving rather than asserting. The check is on the tuple
    of every field of every completed bucket, not on a summary.
    """
    day = dt.date(2026, 6, 10)
    clean = synth_session(day)
    wrecked = [dict(r) for r in clean]
    cut = 900                                   # a decision point mid-session
    for r in wrecked[cut:]:
        r["o"] = r["h"] = r["l"] = r["c"] = 99_999.0
        r["v"] = 7_777_777.0

    a = _five_minute_bars(store(clean).sessions[0].bars)
    b = _five_minute_bars(store(wrecked).sessions[0].bars)

    #: buckets are 5 minutes, so the last bucket to complete strictly before bar `cut` is
    #: the last one both runs can be expected to share
    shared = (cut // 5) - 1
    assert shared > 100, "the test must compare a meaningful number of buckets"
    assert a[:shared] == b[:shared]
    assert a[shared + 1:] != b[shared + 1:], "the wrecked future must actually differ"


def test_only_completed_five_minute_bars_are_ever_visible(store):
    """A bucket appears only once its final minute has closed AND the next has opened."""
    bars = store(synth_session(dt.date(2026, 6, 10))).sessions[0].bars
    agg, v = FiveMinuteAggregator(), SessionVwap(anchor_minute=ANCHOR)
    for i, b in enumerate(bars):
        v.update(b)
        agg.update(b, v.value)
        last = agg.last_completed
        if last is not None:
            assert last.end < b.timestamp, "the bucket closed before the revealing bar"
            covered = [x for x in bars[:i] if x.timestamp <= last.end]
            assert last.high == max(x.high for x in covered[-5:])
            assert last.low == min(x.low for x in covered[-5:])
            assert last.volume == sum(x.volume for x in covered[-5:])


def test_the_forming_bucket_is_never_in_the_completed_list(store):
    """ATR(14) reads `FiveMinuteAggregator.completed`. The bar being built is not in it."""
    bars = store(synth_session(dt.date(2026, 6, 10))).sessions[0].bars
    agg, v = FiveMinuteAggregator(), SessionVwap(anchor_minute=ANCHOR)
    for b in bars:
        v.update(b)
        agg.update(b, v.value)
        for done in agg.completed:
            assert done.end < b.timestamp, "a completed bucket ends before the current bar"
        #: the minute just absorbed belongs to the bucket being FORMED, so no completed
        #: bucket may contain it
        assert not any(x.start <= b.timestamp <= x.end for x in agg.completed)
    assert len(agg.completed) == 261, "1,306 minutes = 261 closed buckets + one still open"


# ---- the adversarial prefix test ------------------------------------------------------

@pytest.mark.parametrize("cut_minute", [600, 930, 1200])
def test_nothing_available_at_T_changes_when_everything_after_T_changes(store, cut_minute):
    """THE ADVERSARIAL DATA-PATH TEST.

    Two datasets identical up to a decision time T and violently different after it: prices
    moved to 99,999, volume to seven million, the contract switched, a roll invented. Every
    quantity a decision at T could read must be bit-identical between them - session
    identity, the 1-minute bars, the completed 5-minute buckets, the VWAP and its sigma, the
    volume SMA, contract identity, and the per-session quality record.

    If any of them moved, the data path would be handing the strategy information the day did
    not have, and no amount of care in the engine could undo it.
    """
    day = dt.date(2026, 6, 10)
    clean = synth_session(day, contract="ESM6")
    wrecked = [dict(r) for r in clean]
    for r in wrecked[cut_minute:]:
        r["o"] = r["h"] = r["l"] = r["c"] = 99_999.0
        r["v"] = 7_777_777.0
        r["contract"] = "ESU6"

    a = store(clean).sessions[0]
    b = store(wrecked).sessions[0]

    #: the wrecked run is refused outright - two contracts - which is itself correct, so the
    #: comparison runs on the BARS the loader cut, taken from a single-contract variant too
    single = [dict(r) for r in clean]
    for r in single[cut_minute:]:
        r["o"] = r["h"] = r["l"] = r["c"] = 99_999.0
        r["v"] = 7_777_777.0
    c = store(single).sessions[0]

    assert b.quality.status is D.SessionStatus.MULTI_CONTRACT
    assert a.trading_day == c.trading_day
    assert a.contract == c.contract == "ESM6"
    assert a.bars[:cut_minute] == c.bars[:cut_minute], "the 1-minute prefix moved"

    va, vc = SessionVwap(anchor_minute=ANCHOR), SessionVwap(anchor_minute=ANCHOR)
    sa, sc = VolumeSma(period=10), VolumeSma(period=10)
    aa, ac = FiveMinuteAggregator(), FiveMinuteAggregator()
    for bar_a, bar_c in zip(a.bars[:cut_minute], c.bars[:cut_minute], strict=True):
        va.update(bar_a)
        sa.update(bar_a)
        aa.update(bar_a, va.value)
        vc.update(bar_c)
        sc.update(bar_c)
        ac.update(bar_c, vc.value)
    assert (va.value, va.sigma, va.band(2.0)) == (vc.value, vc.sigma, vc.band(2.0))
    assert sa.value == sc.value
    assert _five_minute_bars(a.bars[:cut_minute]) == _five_minute_bars(c.bars[:cut_minute])

    #: and the prefix's own provenance is unchanged: the same bars hash the same
    prefix_a = D.AnchoredSession(a.trading_day, a.bars[:cut_minute], a.quality)
    prefix_c = D.AnchoredSession(c.trading_day, c.bars[:cut_minute], c.quality)
    assert prefix_a.content_hash() == prefix_c.content_hash()

    #: the future really was wrecked, so none of the above passed vacuously
    assert a.bars[cut_minute:] != c.bars[cut_minute:]


def test_a_prefix_only_store_produces_the_same_bars_as_the_full_one(store):
    """The other direction: truncating the file after T must not change the prefix either."""
    day = dt.date(2026, 6, 10)
    full = synth_session(day)
    a = store(full).sessions[0]
    b = store(full[:1000], require_quality=False).sessions[0]
    assert b.quality.status is D.SessionStatus.TRUNCATED_END
    #: the refused session carries no bars, so the comparison is against the rows the
    #: truncated file held - the loader must have cut the same prefix from both
    assert a.bars[:1000] == _bars_from_rows(full[:1000])
    assert b.bars == ()


def _bars_from_rows(rows) -> tuple[Bar, ...]:
    """Rebuild bars straight from the fixture rows, bypassing the loader entirely."""
    return tuple(Bar(timestamp=r["t"], open=r["o"], high=r["h"], low=r["l"], close=r["c"],
                     volume=r["v"]) for r in rows)


# ======================================================================================
# K. THE RELEASE MANIFEST
# ======================================================================================

RELEASE_FILE = REPO / "release" / "V1.0.0_Frozen.json"


@pytest.fixture(scope="session")
def release() -> dict:
    if not RELEASE_FILE.exists():
        pytest.skip("no release manifest; run scripts/vwap_release.py --write")
    return json.loads(RELEASE_FILE.read_text(encoding="utf-8"))


def test_the_release_manifest_pins_every_frozen_value_to_a_literal(release):
    """THE ONE PLACE A LITERAL BELONGS.

    `scripts/vwap_release.py` derives every field from `spec.FROZEN` rather than copying it,
    which keeps one source of truth and means the released file cannot disagree with the
    code. That arrangement proves nothing on its own - both would move together. So the
    numbers are written out HERE, by hand, from the owner's release gate, and a parameter
    that drifts fails this test rather than quietly re-releasing itself.
    """
    assert release["release"] == "V1.0.0_Frozen"
    assert release["strategy"]["spec_hash_nq"] == "1fe36d12eb631c96"
    assert release["strategy"]["spec_hash_mnq"] == "08c19f55b6382d72"
    assert release["strategy"]["execution_profile"] == "BASELINE_FROZEN"
    assert release["strategy"]["execution_profile_is_the_frozen_spec"] is True
    assert release["strategy"]["unresolved_material_ambiguities"] == []

    clock = release["clock"]
    assert clock["timezone"] == "America/New_York"
    assert clock["vwap_anchor_et"] == "18:00"
    assert clock["entry_window_start_et"] == "09:45"
    assert clock["entry_cutoff_et"] == "15:30"
    assert clock["hard_flatten_et"] == "15:45"
    assert clock["data_session_et"] == "18:00 -> 15:45"
    assert clock["vwap_resets_only_at"] == "18:00"
    assert clock["data_session_is_continuous"] is True

    sig = release["signals"]
    assert (sig["atr_method"], sig["atr_period"], sig["atr_minimum"]) == ("wilder", 14, 8.0)
    assert sig["atr_timeframe"] == "5min, completed buckets only"

    gov = release["governor"]
    assert gov["mtm_mode"] == "CONSERVATIVE_INTRABAR_ADVERSE_EXTREME"
    assert gov["daily_loss_killswitch"] == -800.0
    assert gov["daily_profit_cap"] == 1200.0
    assert gov["max_trades_per_day"] == 4

    cost = release["sizing_and_cost"]
    assert cost["nq"]["contracts"] == 1
    assert cost["mnq"]["contracts"] == 10
    assert cost["nq"]["commission_round_turn"] == 4.50
    assert cost["entry_slippage_ticks"] == 1.0
    assert cost["stop_slippage_ticks"] == 1.0
    assert cost["target_slippage_ticks"] == 0.0
    assert cost["market_exit_slippage_ticks"] == 0.0


def test_the_release_manifest_states_the_data_policy(release):
    dp = release["data_pipeline"]
    assert dp["loader_version"] == D.LOADER_VERSION
    assert dp["adjustment_mode"] == "CONTINUOUS_UNADJUSTED"
    assert dp["price_adjustment"] == "NONE"
    assert dp["rejection_code"] == "INCOMPLETE_SESSION"
    assert "No verified CME calendar" in dp["calendar_inference"]
    assert "TP * 0 = 0" in dp["zero_volume_policy"]
    assert "never a reason to reject" in dp["zero_volume_policy"]
    assert dp["repair_policy"].startswith("none")
    assert "no strategy backtest has been run" in release["prohibitions_at_this_gate"]


@needs_store
def test_the_release_manifest_matches_the_datasets_on_disk(release, es):
    ds = release["datasets"]["ES"]
    live = es.manifest()
    assert ds["manifest_id"] == live["manifest_id"]
    assert ds["content_hash"] == live["content_hash"]
    assert ds["file_sha256"] == live["source"]["file_hashes"]
    assert ds["file_bytes"] == live["source"]["file_bytes"]
    assert ds["rows_in_file"] == live["source"]["rows_in_file"] == 447_600
    assert ds["sessions_found"] == 327
    assert ds["sessions_usable"] == 313
    assert ds["contract_coverage"] == ["ESU5", "ESZ5", "ESH6", "ESM6", "ESU6"]
    for sym in ("ES", "NQ", "MES", "MNQ"):
        assert release["datasets"][sym]["present"] is True


def test_the_release_manifest_is_verifiable_from_the_repository():
    """`--verify` rebuilds every field and refuses on the first disagreement."""
    r = subprocess.run([sys.executable, "scripts/vwap_release.py", "--verify"],
                       cwd=REPO, capture_output=True, text=True, timeout=900, check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "release manifest verified" in r.stdout
