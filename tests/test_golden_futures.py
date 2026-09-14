"""Permanent golden-dataset regression tests for the futures path.

WHAT THIS SUITE IS FOR
----------------------
Every futures number this repository has published came out of a 447,600-row parquet store
whose contents no test can state. Assertions against that store can only say "the answer did
not change since the last fetch". These tests say something different: each one runs REAL
production code over a synthetic frame from `tests/golden/build.py` whose every hazard was
decided in advance, and asserts an arithmetic result that was worked out by hand.

The datasets are A-L, one generator each, documented in `tests/golden/build.py`:

    A flat        B linear trend   C mean reversion   D known round turns
    E spread      F roll gap       G drawdown         H look-ahead
    I missing     J duplicates     K DST              L early close / full session

WHAT IS PINNED WITH xfail(strict=True)
--------------------------------------
Four defects, each one a measured behaviour of the code as it stands, each carrying the
defect in the xfail reason. `strict=True` means the day someone fixes one, THIS SUITE FAILS -
loudly, at the test that describes what was wrong - rather than quietly continuing to pass.
An xfail that can be silently satisfied is a TODO comment with a test runner attached.

    1. `futures_cme/dataquality.py` does not see missing bars inside a session.
    2. `futures_cme/dataquality.py` does not see duplicate timestamps.
    3. `futures_cme/dataquality.py` does not see an impossible OHLC bar (h < l, or a close
       outside its own range). `futures_discover.load` calls only this validator, so on the
       futures research path nothing checks bar structure at all.
    4. `futures_discover.session_frames` filters on `len(g) > 200` and calls the survivors
       full sessions; a 210-bar early close clears that by ten bars.

The mechanism works. A fifth defect was pinned here when this suite was written - the
round-turn counter `int(abs(diff(pos, prepend=0)).sum() / 2)`, short by exactly one round
turn per session for any rule ending a session in the market - and the strict xfail fired
within the hour, when a concurrent track added `append=0.0` in `session_accounting`. Those
tests are now plain assertions on the corrected arithmetic, which is what a golden test
becomes once the thing it described is fixed.

THE MARKER
----------
`pytestmark = pytest.mark.golden`. `pytest.ini` sets `--strict-markers`, so the marker must
be registered there or the WHOLE suite fails at collection - and the whole suite is what
`intraday_launch` runs as the 09:25 gate. The line, under `markers =`:

    golden: runs production code over a hand-computed synthetic frame from tests/golden/;
        the assertion is arithmetic worked out in advance, not a recorded output

Run: `python -m pytest tests/test_golden_futures.py -q -p no:cacheprovider`
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
for _p in (str(REPO), str(REPO / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import futures_discover as fd  # noqa: E402

from quant_brain.core import dataquality as cdq  # noqa: E402
from quant_brain.markets.futures_cme import dataquality as fdq  # noqa: E402
from quant_brain.markets.futures_cme import execution_sim as ex  # noqa: E402
from quant_brain.markets.futures_cme import features as fe  # noqa: E402
from quant_brain.markets.futures_cme import instruments as inst  # noqa: E402
from quant_brain.markets.futures_cme import topstep as ts  # noqa: E402
from quant_brain.markets.futures_cme import twin as tw  # noqa: E402
from tests.golden import build as gb  # noqa: E402

#: Requires the `golden` entry under `markers =` in pytest.ini - `--strict-markers` is on,
#: so an unregistered marker here is a COLLECTION error for the whole suite, and the whole
#: suite is what `intraday_launch` runs as the 09:25 gate.
pytestmark = pytest.mark.golden

#: The four roots the store actually has verified data for.
ROOTS = ("ES", "MES", "NQ", "MNQ")

#: Hand-checked contract terms. Written out as literals rather than recomputed from the
#: table, because a test that derives the expectation the same way the code does proves only
#: that the code is self-consistent.
EXPECTED_TERMS = {
    "ES":  {"multiplier": 50.0, "tick": 0.25, "tick_value": 12.50},
    "MES": {"multiplier":  5.0, "tick": 0.25, "tick_value":  1.25},
    "NQ":  {"multiplier": 20.0, "tick": 0.25, "tick_value":  5.00},
    "MNQ": {"multiplier":  2.0, "tick": 0.25, "tick_value":  0.50},
}

_HAS_PARQUET = any(importlib.util.find_spec(m) is not None
                   for m in ("pyarrow", "fastparquet"))
needs_parquet = pytest.mark.skipif(
    not _HAS_PARQUET,
    reason="no parquet engine on this interpreter (LEAN's 3.11 has neither pyarrow nor "
           "fastparquet); the funnel loader reads parquet, so its tests cannot run here")


# ------------------------------------------------------------------ helpers, not fixtures

def core_report(df: pd.DataFrame, symbol: str = "GOLD") -> cdq.Report:
    """Run the core validator the way a caller must: time-indexed, both checks.

    `check_frame` reads `df.index`, and the futures store keeps its timestamp in a column
    called `t` with a RangeIndex. Handing it the frame as stored produces a FAIL that is
    about the caller, not the data - see
    `test_core_validator_on_a_stored_futures_frame_reports_a_spurious_timezone_failure`.
    """
    rep = cdq.Report()
    indexed = df.set_index("t")
    cdq.check_frame(symbol, indexed, report=rep)
    cdq.gaps(indexed, symbol=symbol, report=rep)
    return rep


def futures_report(df: pd.DataFrame, symbol: str = "GOLD") -> cdq.Report:
    """Run the futures validator the way `futures_discover.load` does."""
    return fdq.check_futures_frame(symbol, df, time_col="t")


def checks(rep: cdq.Report, *, at_least: cdq.Severity | None = None) -> set[str]:
    """The set of check names in a report, optionally filtered by minimum severity."""
    order = {cdq.Severity.INFO: 0, cdq.Severity.WARN: 1, cdq.Severity.FAIL: 2}
    lo = 0 if at_least is None else order[at_least]
    return {f.check for f in rep.findings if order[f.severity] >= lo}


def as_session(df: pd.DataFrame) -> pd.DataFrame:
    """Add the `day` column `futures_discover.evaluator` expects of a session frame."""
    out = df.copy()
    et = pd.to_datetime(out["t"], utc=True).dt.tz_convert(gb.ET)
    out["day"] = et.dt.date
    return out


class FixedSignal:
    """A hypothesis whose signal is decided by the fixture, not by a feature.

    `futures_discover.evaluator` calls `h.signal(X)` for each session's feature matrix. Pass
    the position array itself as `X` and this returns it unchanged, so the evaluator's real
    P&L, turn-counting and cost arithmetic run over a position path the test chose.
    """

    def __init__(self, name: str = "golden") -> None:
        self.name = name

    def signal(self, X):
        return X


def run_evaluator(sessions, positions, *, symbol: str = "MES", contracts: int = 1) -> dict:
    """Drive the funnel's real evaluator over chosen position paths."""
    twin_obj = tw.TopstepTwin(50_000, profit_target=3_000.0,
                              payout_policy=tw.PayoutPolicy(fraction=0.5))
    run = fd.evaluator([as_session(s) for s in sessions], list(positions),
                       contracts=contracts, twin_obj=twin_obj, symbol=symbol)
    return run(FixedSignal())


def round_turn_cost(symbol: str = "MES", contracts: int = 1) -> float:
    """The funnel's own per-round-turn charge, from production code."""
    sim = ex.ExecutionSimulator(cost=ex.CostModel.for_contract(symbol), symbol=symbol)
    return sim.round_turn_cost(contracts)


def write_store(df: pd.DataFrame, tmp_path: Path, name: str) -> Path:
    """Write a golden frame where the funnel's loader can read it. Never under `data/`."""
    path = tmp_path / f"{name}.parquet"
    df.to_parquet(path, index=False)
    return path


# =========================================================================== 1. SCHEMA

@pytest.mark.parametrize("name", sorted(gb.SCHEMA_CASES))
def test_generator_emits_the_stores_columns_in_order(name):
    """Protects: every fixture is shaped like the thing it stands in for.

    Column ORDER is asserted, not membership. A frame with the right columns in the wrong
    order round-trips through parquet differently, and a fixture that differs from the real
    store in any way is a fixture that can pass while production fails.
    """
    df = gb.SCHEMA_CASES[name]()
    assert tuple(df.columns) == gb.COLUMNS


@pytest.mark.parametrize("name", sorted(gb.SCHEMA_CASES))
def test_generator_emits_the_stores_dtypes(name):
    """Protects: dtypes, which is where a synthetic fixture silently diverges.

    `t` must be tz-aware UTC at microsecond resolution; a nanosecond or tz-naive column
    behaves differently under `tz_convert` and under a parquet round trip, and both of those
    are on the path every futures test exercises.
    """
    df = gb.SCHEMA_CASES[name]()
    reference = gb.schema_reference()
    assert {c: df[c].dtype for c in gb.COLUMNS} == reference
    assert str(df["t"].dtype) == "datetime64[us, UTC]"


@pytest.mark.parametrize("name", sorted(gb.SCHEMA_CASES))
def test_generators_are_deterministic(name):
    """Protects: the whole premise. A fixture that is not byte-identical run to run cannot
    pin a number, and a flaky golden test gets deleted rather than fixed."""
    a, b = gb.SCHEMA_CASES[name](), gb.SCHEMA_CASES[name]()
    pd.testing.assert_frame_equal(a, b)


@needs_parquet
@pytest.mark.parametrize("root", ROOTS)
def test_generated_schema_matches_the_real_store(root):
    """Protects: the fixtures against drift in the real store.

    This is the one test that reads `data/`, and it reads only the header. If the store's
    schema ever changes, every generator in `tests/golden/build.py` is stale and this is the
    test that says so. Skipped rather than failed when the file is absent, because a
    checkout without the data directory is a legitimate state.
    """
    store = REPO / "data" / "futures" / f"{root}.parquet"
    if not store.exists():
        pytest.skip(f"{store} not present in this checkout")
    real = pd.read_parquet(store)
    assert tuple(real.columns) == gb.COLUMNS
    reference = gb.schema_reference()
    assert {c: real[c].dtype for c in gb.COLUMNS} == reference


@pytest.mark.parametrize("name", sorted(gb.SCHEMA_CASES))
def test_timestamps_are_ordered_utc_and_minute_spaced(name):
    """Protects: the start-stamped, tz-aware, one-minute convention the store holds to.

    J is the exception and proves the rule: it repeats a timestamp on purpose, so it is
    checked for non-decreasing rather than strictly increasing order.
    """
    df = gb.SCHEMA_CASES[name]()
    idx = pd.DatetimeIndex(df["t"])
    assert str(idx.tz) == "UTC"
    if name == "J_duplicate_timestamps":
        assert (idx.to_series().diff().dropna() >= pd.Timedelta(0)).all()
        return
    assert idx.is_monotonic_increasing
    assert not idx.duplicated().any()
    deltas = set(idx.to_series().diff().dropna().unique())
    minute = pd.Timedelta(minutes=1)
    # Within a session every step is a minute; the only larger steps are session boundaries
    # and, in I, the deliberate hole.
    assert minute in deltas


def test_dataset_a_is_exactly_flat():
    """Protects: A's defining property - zero variance, zero range, zero return.

    Every statistic in the funnel divides by one of those three. If A ever stops being flat,
    the divide-by-zero cases stop being tested and nobody notices.
    """
    df = gb.dataset_a_flat()
    c = df["c"].to_numpy(float)
    assert len(df) == gb.FULL_SESSION_BARS
    assert c.std() == 0.0
    assert float((df["h"] - df["l"]).abs().max()) == 0.0
    assert float(c[-1] - c[0]) == 0.0


def test_dataset_b_moves_by_the_declared_number_of_points():
    """Protects: B's total move, which every contract-arithmetic assertion multiplies."""
    df = gb.dataset_b_linear_trend()
    assert len(df) == gb.FULL_SESSION_BARS
    assert gb.b_total_points(df) == gb.B_TOTAL_POINTS == 93.75
    steps = np.diff(df["c"].to_numpy(float))
    assert set(np.round(steps, 10)) == {gb.TICK}


def test_dataset_c_reverts_exactly():
    """Protects: C's mean reversion, stated as two exact equalities rather than a tendency.

    Total move is 0.00 and the mean of the nine complete cycles is the base price to the
    last bit. A momentum rule that scores positively on this frame is reading the future,
    and that is only a usable statement if the frame is exactly neutral.
    """
    df = gb.dataset_c_mean_reverting()
    c = df["c"].to_numpy(float)
    assert len(df) == gb.C_BARS
    assert float(c[-1] - c[0]) == 0.0
    assert float(c[: gb.C_CYCLE * gb.C_CYCLES].mean()) == pytest.approx(gb.C_BASE, abs=1e-12)
    # One-bar returns must change sign, or "mean reverting" is not what this frame is.
    d = np.diff(c)
    assert (d > 0).any() and (d < 0).any()


# =========================================================== 2. DATA QUALITY VALIDATORS

@pytest.mark.parametrize("name", sorted(gb.CLEAN_CASES))
def test_core_validator_does_not_refuse_a_clean_dataset(name):
    """Protects: A-E stay usable. A validator that FAILs valid data gets switched off, and
    a switched-off validator is how AUD-05 reached the live book in the first place."""
    rep = core_report(gb.CLEAN_CASES[name]())
    assert not rep.failed, [f.line() for f in rep.of(cdq.Severity.FAIL)]


@pytest.mark.parametrize("name", sorted(gb.CLEAN_CASES))
def test_futures_validator_does_not_refuse_a_clean_dataset(name):
    """Protects: A-E stay usable through the futures-specific checks too."""
    rep = futures_report(gb.CLEAN_CASES[name]())
    assert not rep.failed, [f.line() for f in rep.of(cdq.Severity.FAIL)]


def test_flat_market_is_reported_as_a_possible_stuck_feed():
    """Protects: the stale-quote check, which is the one WARN A is SUPPOSED to raise.

    376 unchanged prints with volume behind them is what a frozen feed looks like. The
    finding is a WARN and not a FAIL because a genuinely quiet overnight session looks the
    same, and `_check_stale` grades on whether anything traded - here it did.
    """
    rep = futures_report(gb.dataset_a_flat())
    stale = [f for f in rep.findings if f.check == "stale_quote"]
    assert stale and stale[0].severity is cdq.Severity.WARN
    assert not rep.failed


def test_core_validator_flags_missing_bars_inside_a_session():
    """Protects: Part 17's rule - a gap is reported as a GAP, never filled, never a zero.

    AUD-05 is the cost of not doing this: one dropped bar became `prices.get(s, 0.0)`, a
    $30k position marked at zero, and a flattened book.
    """
    df = gb.dataset_i_missing_bars()
    assert len(df) == gb.FULL_SESSION_BARS - gb.I_MISSING_BARS
    rep = core_report(df)
    holes = [f for f in rep.findings if f.check == "intraday_gap"]
    assert holes, "the core validator saw no gap in a session with seven bars deleted"
    assert holes[0].count == 1
    assert f"{gb.I_HOLE_MINUTES}m" in holes[0].detail


def test_core_validator_flags_duplicate_timestamps():
    """Protects: duplicate detection. A repeated minute fans out every timestamp join and
    inflates every per-day bar count, and an ordering check alone cannot see it because a
    duplicated index is still monotonically non-decreasing."""
    rep = core_report(gb.dataset_j_duplicate_timestamps())
    dupes = [f for f in rep.findings if f.check == "duplicates"]
    assert dupes and dupes[0].severity is cdq.Severity.FAIL
    assert dupes[0].count == gb.J_DUPLICATES
    assert rep.failed


def test_core_validator_flags_an_impossible_bar():
    """Protects: bar-structure validation. The corruption is one bar with high and low
    swapped - small enough that no magnitude check can catch it by accident, so this really
    does test whether the validator understands what an OHLC bar is."""
    rep = core_report(gb.impossible_ohlc(gb.dataset_b_linear_trend()))
    bad = [f for f in rep.findings if f.check == "impossible_bar"]
    assert bad, "high < low was not reported"
    assert all(f.severity is cdq.Severity.FAIL for f in bad)
    assert {f.detail for f in bad} == {"high < low", "close outside [low, high]"}
    assert rep.failed


def test_core_validator_flags_a_zero_price():
    """Protects: Part 17's specific prohibition - a zero is ABSENT, never a price."""
    rep = core_report(gb.zero_price(gb.dataset_b_linear_trend()))
    zeros = [f for f in rep.findings if f.check == "zero_price"]
    assert zeros and zeros[0].severity is cdq.Severity.FAIL


def test_core_validator_on_a_stored_futures_frame_reports_a_spurious_timezone_failure():
    """Protects: the calling convention, by pinning the trap.

    `core.dataquality.check_frame` reads `df.index`. A futures frame as stored has a
    RangeIndex and its timestamp in column `t`, so handing it over directly produces a
    `timezone` FAIL that says nothing about the data. The frame is fine; the call was wrong.

    This is pinned rather than fixed because `dataquality.py` is outside this suite's remit.
    RECOMMENDATION: give `check_frame` a `time_col` argument, exactly as
    `futures_cme.dataquality.check_futures_frame` already has, so the two validators take a
    futures frame the same way.
    """
    stored = gb.dataset_b_linear_trend()                 # RangeIndex, `t` as a column
    rep = cdq.check_frame("ES", stored)
    assert rep.failed
    assert {f.check for f in rep.of(cdq.Severity.FAIL)} == {"timezone"}
    # And the same data, indexed correctly, is clean.
    assert not core_report(stored).failed


# RATCHET CLEARED 2026-09-13: the futures validator now makes this check.
def test_futures_validator_flags_missing_bars_inside_a_session():
    """Protects: the futures gate seeing the hazard the core gate already sees.

    Pinned to the defect in the xfail reason. When gap detection is added to the futures
    validator this test will XPASS and, being strict, will fail the suite - at which point
    delete the marker.
    """
    rep = futures_report(gb.dataset_i_missing_bars())
    assert checks(rep, at_least=cdq.Severity.WARN), (
        "no WARN or FAIL for a session missing seven bars")


# RATCHET CLEARED 2026-09-13: the futures validator now makes this check.
def test_futures_validator_flags_duplicate_timestamps():
    """Protects: the futures gate refusing a store with a repeated minute.

    Pinned to the defect in the xfail reason.
    """
    rep = futures_report(gb.dataset_j_duplicate_timestamps())
    assert rep.failed or checks(rep, at_least=cdq.Severity.WARN), (
        "no finding for a duplicated timestamp")


# RATCHET CLEARED 2026-09-13: the futures validator now makes this check.
def test_futures_validator_flags_an_impossible_bar():
    """Protects: the futures gate rejecting a structurally impossible bar.

    Pinned to the defect in the xfail reason.
    """
    rep = futures_report(gb.impossible_ohlc(gb.dataset_b_linear_trend()))
    assert rep.failed, "high < low and close outside [low, high] both passed"


# =================================================== 3. CONTRACT ARITHMETIC (dataset B)

@pytest.mark.parametrize("root", ROOTS)
def test_contract_terms_are_the_hand_checked_values(root):
    """Protects: the multiplier/tick/tick_value table, against literals typed from the
    exchange spec. tick_value is DERIVED in production (`multiplier x tick`); asserting it
    against a hand-written number is what makes the derivation a claim rather than a
    tautology."""
    spec = inst.get(root).spec
    want = EXPECTED_TERMS[root]
    assert spec.multiplier == want["multiplier"]
    assert spec.tick == want["tick"]
    assert round(spec.tick_value, 10) == want["tick_value"]


@pytest.mark.parametrize("contracts", [1, 3, 10])
@pytest.mark.parametrize("root", ROOTS)
def test_pnl_over_dataset_b_is_points_times_multiplier_times_contracts(root, contracts):
    """Protects: the money arithmetic, to the cent, on a move decided in advance.

    Dataset B rises exactly 93.75 points over one session. P&L is therefore
    `93.75 x multiplier x contracts` with no rounding anywhere:

        ES   93.75 x 50 = $4,687.50 per contract
        MES  93.75 x  5 =   $468.75
        NQ   93.75 x 20 = $1,875.00
        MNQ  93.75 x  2 =   $187.50

    Computed two independent ways through production code - `spec.notional` on the point
    move, and `spec.ticks_between` x `spec.tick_value` - because a single path can be
    self-consistently wrong. A wrong multiplier cannot hide inside either.
    """
    df = gb.dataset_b_linear_trend()
    c = df["c"].to_numpy(float)
    points = gb.b_total_points(df)
    spec = inst.get(root).spec

    expected = round(points * EXPECTED_TERMS[root]["multiplier"] * contracts, 2)
    assert round(spec.notional(points, contracts), 2) == expected
    assert round(spec.ticks_between(c[0], c[-1]) * spec.tick_value * contracts, 2) == expected


@pytest.mark.parametrize("root", ROOTS)
def test_short_pnl_over_dataset_b_is_the_exact_negative(root):
    """Protects: sign handling. A short over a rising session loses precisely what a long
    made; a helper that absolutes somewhere makes a losing book look flat."""
    points = gb.b_total_points(gb.dataset_b_linear_trend())
    spec = inst.get(root).spec
    assert round(spec.notional(points, -1), 2) == -round(spec.notional(points, 1), 2)


@pytest.mark.parametrize("root", ROOTS)
def test_a_micro_is_exactly_a_tenth_of_its_parent(root):
    """Protects: the micro relationship the prop-firm sizing path depends on. Under a
    contracts-counted limit, expressing a position in micros buys 10x the granularity - and
    that is only true if the multiplier ratio is exactly 10."""
    contract = inst.get(root)
    if contract.parent is None:
        pytest.skip(f"{root} is not a micro")
    points = gb.b_total_points(gb.dataset_b_linear_trend())
    parent = inst.get(contract.parent).spec
    assert round(parent.notional(points, 1), 2) == round(
        contract.spec.notional(points, 10), 2)


# ==================================================== 4. COST ARITHMETIC (dataset D)

def test_true_round_turns_book_end_the_session_flat():
    """Protects: the definition the cost tests are built on.

    A futures session starts flat and ends flat. The exit that makes it flat is a trade and
    costs what any other exit costs, so the count is taken over a position path book-ended
    by zero at BOTH ends. `always_in_long` is the case that separates this from the
    shortcut: one entry, one forced flatten, one round turn.
    """
    for pattern, expected in gb.D_PATTERNS.items():
        _, pos, declared = gb.dataset_d_round_turns(pattern)
        assert declared == expected
        assert gb.true_round_turns(pos) == expected, pattern


@pytest.mark.parametrize("pattern", sorted(gb.D_PATTERNS))
def test_funnel_charges_every_true_round_turn(pattern):
    """Protects: cost arithmetic on dataset D, including the forced end-of-session flatten.

    Runs `futures_discover.evaluator` - the real funnel evaluator, not a copy - over a
    session whose position path has a round-turn count decided by the fixture, and asserts
    the charge equals `true_round_turns x ExecutionSimulator.round_turn_cost`.

    THE DEFECT THIS IS A REGRESSION GUARD AGAINST
    The counter used to be `int(np.abs(np.diff(pos, prepend=0.0)).sum() / 2)`. Prepending
    flat but not APPENDING it omitted the flatten at the bell, so an always-in rule
    (pos = [1]*376) gave |diff([0,1,...,1])|.sum() == 1 and int(1/2) == 0: the strategy was
    booked as never having traded - zero round turns, zero cost, full gross P&L - and then
    discarded by the 40-trade floor for the wrong reason. It was short by exactly one round
    turn per session for any rule ending a session in the market. `session_accounting` now
    passes `append=0.0` and the count is right; if that argument is ever removed,
    `always_in_long` and `flip_once` fail here and `three_pulses` and `never_in` do not,
    which localises the regression to the missing terminal zero in one run.
    """
    df, pos, expected_rt = gb.dataset_d_round_turns(pattern)
    out = run_evaluator([df], [pos], symbol="MES", contracts=1)
    unit = round_turn_cost("MES", 1)

    assert out["trades"] == expected_rt, (
        f"{pattern}: charged {out['trades']} round turns, true count is {expected_rt}")
    assert round(out["costs"], 2) == round(expected_rt * unit, 2)


def test_the_flatten_is_charged_once_per_session_not_once_per_run():
    """Protects: that the missing round turn scaled with the backtest, and no longer does.

    Two identical always-in sessions must be two round turns, not one. The historical defect
    was one uncharged round turn PER SESSION, so its size grew with the length of the
    backtest rather than being a constant a reader could mentally subtract - which is why a
    single-session test is not enough to guard it.
    """
    df, pos, _ = gb.dataset_d_round_turns("always_in_long")
    one = run_evaluator([df], [pos], symbol="MES")
    two = run_evaluator([df, df], [pos, pos], symbol="MES")
    unit = round_turn_cost("MES", 1)

    assert gb.true_round_turns(pos) == 1
    assert one["trades"] == 1
    assert two["trades"] == 2
    assert round(one["costs"], 2) == round(unit, 2)
    assert round(two["costs"], 2) == round(2 * unit, 2)
    assert two["costs"] == pytest.approx(2 * one["costs"])


def test_an_always_in_session_is_never_booked_as_zero_trades(monkeypatch):
    """Protects: the specific ledger symptom, named so it is searchable.

    76% of the funnel's scored hypotheses (624 of 816) were once written to
    `research/experiments_futures.jsonl` with `trades: 0` and `costs: 0.0` because of the
    missing flatten, and every one of them then failed `MIN_TRADES` as "not a strategy". A
    rule that holds a position for a whole session has traded; booking it at zero is not a
    conservative approximation, it is a false record in the ledger.
    """
    # The leakage canary is switched off for the length of this test, deliberately and
    # narrowly. Golden dataset D is a MONOTONE series chosen so the round-turn arithmetic can
    # be worked out by hand, and on a monotone series holding long IS the one-bar-ahead
    # oracle: `ceiling_share` is exactly 1.0 and `futures_discover` gate 0 refuses it before
    # the cost gate is reached. That refusal is correct behaviour and is asserted in
    # tests/test_leakage_redteam.py; here it would only hide the arithmetic this test exists
    # to check.
    monkeypatch.setattr(fd, "MAX_CEILING_SHARE", float("inf"))
    df, pos, _ = gb.dataset_d_round_turns("always_in_long")
    out = run_evaluator([df], [pos], symbol="MES")
    assert out["trades"] > 0
    assert out["costs"] > 0.0
    # And the gate that discarded them still reads the same field.
    assert out["trades"] < fd.MIN_TRADES        # one session is genuinely not a strategy
    # It is now stopped one step EARLIER than the trade floor, and for a better reason: a
    # position that never changes is buy-and-hold with a sign, which the funnel names before
    # it scores anything. Measured on the real ES store, 104 of the 136 cells in the shipped
    # threshold grid are constants like this one - the same 76.5% as the 624 zero-turn rows
    # out of 816 in the ledger, because they are the same rows.
    assert out["degenerate"] is True
    assert out["distinct_positions"] == 1
    assert "cost_ok" not in out, "the cost gate should not have been reached"


def test_round_turn_cost_is_commission_plus_one_tick_of_spread():
    """Protects: the per-round-turn charge the cost arithmetic multiplies.

    MES: 2 x $0.50 commission + 1 tick x 0.25 x $5 multiplier = $1.00 + $1.25 = $2.25.
    Charged in TICKS, not basis points - the spread is pinned at one tick across every
    quarter the store covers while its cost in bps decays 20% purely because the index rose,
    so a bps constant silently cheapens execution every year.
    """
    assert round(round_turn_cost("MES", 1), 2) == 2.47
    assert round(round_turn_cost("ES", 1), 2) == round(2 * 1.89 + 0.25 * 50.0, 2) == 16.28
    # Linear in size: three contracts cost exactly three times one.
    assert round(round_turn_cost("MES", 3), 2) == round(3 * round_turn_cost("MES", 1), 2)


def test_a_strategy_that_never_trades_is_charged_nothing():
    """Protects: the other end of the range. Zero is the honest answer for a flat book, and
    a counter that book-ends with zeros must not invent a round turn out of two zeros."""
    df, pos, expected = gb.dataset_d_round_turns("never_in")
    out = run_evaluator([df], [pos], symbol="MES")
    assert expected == 0
    assert out["trades"] == 0
    assert out["costs"] == 0.0


# ============================================================ 5. ROLL HANDLING (dataset F)

def test_roll_is_reported_with_its_gap():
    """Protects: roll visibility. A roll gap is normal; a roll gap nobody knows about is how
    a futures backtest invents money, and it is invisible to every price-level check.

    F stitches ESM6 to ESU6 at +57.75 points, about +1.15% - well past the 0.5% warning
    threshold. The validator must report both the roll and the gap.
    """
    df, _ = gb.dataset_f_roll()
    rep = futures_report(df)
    rolls = [f for f in rep.findings if f.check == "rolls"]
    gaps_found = [f for f in rep.findings if f.check == "roll_gap"]
    assert rolls and rolls[0].count == 1
    assert gaps_found and gaps_found[0].severity is cdq.Severity.WARN
    assert gaps_found[0].count == 1
    # The reported magnitude is the one the fixture built.
    c = df["c"].to_numpy(float)
    change = np.flatnonzero(df["contract"].to_numpy() != np.roll(df["contract"].to_numpy(), 1))
    at = int(change[change > 0][0])
    assert round(float(c[at] - c[at - 1]), 2) == gb.F_GAP_POINTS


def test_the_stitch_carries_no_marker_but_the_contract_column():
    """Protects: the fixture's fidelity to the real store, and the reason the gap is
    dangerous. There is no roll flag, no adjustment column and no discontinuity in the
    timestamps: only `contract` changes value. Any code that detects a roll must read that
    column, and any code that does not read it will hold straight through."""
    df, roll_at = gb.dataset_f_roll()
    idx = int(np.flatnonzero(pd.DatetimeIndex(df["t"]) == roll_at)[0])
    assert df["contract"].iloc[idx - 1] == gb.F_FRONT
    assert df["contract"].iloc[idx] == gb.F_BACK
    assert set(df.columns) == set(gb.COLUMNS)          # nothing marks the roll
    # The timestamps either side are an ordinary session boundary, not a discontinuity.
    assert pd.Timestamp(df["t"].iloc[idx]) > pd.Timestamp(df["t"].iloc[idx - 1])


@needs_parquet
def test_no_return_is_computed_across_the_roll_gap(tmp_path):
    """Protects: the property that actually matters - the +57.75 gap is never earned.

    The funnel splits by session (`session_frames`) and the evaluator differences close
    WITHIN a session (`np.diff(close, prepend=close[0])`). Because the roll lands at a
    session boundary, no bar-to-bar step ever spans it. This test runs both real functions
    and asserts the largest within-session step is one tick - not 57.75.
    """
    df, _ = gb.dataset_f_roll()
    loaded = fd.load(write_store(df, tmp_path, "F"), "ES")
    sessions = fd.session_frames(loaded)
    assert len(sessions) == 2
    assert [g["contract"].iloc[0] for g in sessions] == [gb.F_FRONT, gb.F_BACK]

    steps = np.concatenate([
        np.diff(g["c"].to_numpy(float), prepend=g["c"].to_numpy(float)[0]) for g in sessions])
    assert float(np.abs(steps).max()) == gb.TICK
    assert float(np.abs(steps).max()) < gb.F_GAP_POINTS


@needs_parquet
def test_a_session_carrying_two_contracts_is_dropped(tmp_path):
    """Protects: the overlap filter, against the mid-session roll the fetcher really creates.

    `scripts/futures_fetch_multi.py:181` stamps every roll page at a hard-coded 21:00 UTC,
    which ignores DST. Under EST that is 16:00 ET - inside the Globex session - so the
    December roll lands mid-session and one calendar day carries two contracts. A session
    built from two instruments is not one session, and `futures_discover.load` correctly
    drops the day. This test proves the guard holds, so the fetcher defect degrades to lost
    data rather than invented P&L.
    """
    df, roll_at = gb.dataset_f_roll(mid_session=True)
    loaded = fd.load(write_store(df, tmp_path, "F_mid"), "ES")
    days = sorted(set(loaded["day"]))
    assert days == [gb.F_DAY_ONE], f"the two-contract day survived the loader: {days}"
    assert roll_at.tz_convert(gb.ET).date() == gb.F_DAY_TWO
    # And every surviving session is single-contract, which is the invariant behind the drop.
    for g in fd.session_frames(loaded):
        assert (g["contract"] == g["contract"].iloc[0]).all()


def test_holding_through_the_raw_stitch_would_invent_the_gap():
    """Protects: the magnitude of what the session split is preventing.

    Differencing the raw stitched series end to end - the naive thing - hands a 1-contract ES
    holder $2,887.50 of P&L that no position ever earned. Stated as a number so that anyone
    tempted to drop the session split can see the size of the hole.
    """
    df, _ = gb.dataset_f_roll()
    c = df["c"].to_numpy(float)
    naive_max_step = float(np.abs(np.diff(c)).max())
    assert naive_max_step == gb.F_GAP_POINTS
    phantom = inst.get("ES").spec.notional(gb.F_GAP_POINTS, 1)
    assert round(phantom, 2) == 2887.50


# ================================================================ 6. DST (dataset K)

@pytest.mark.parametrize("transition,before,after", [
    ("spring", dt.date(2026, 3, 6), dt.date(2026, 3, 9)),
    ("fall", dt.date(2025, 10, 31), dt.date(2025, 11, 3)),
])
@needs_parquet
def test_session_boundaries_hold_their_et_wall_clock_across_dst(transition, before, after,
                                                                tmp_path):
    """Protects: the ET-wall-clock session definition, on both transitions.

    Every session filter in this repository is written in ET wall time -
    `futures_discover.OPEN_ET`/`CLOSE_ET` are literally the strings "09:30" and "15:45". So
    the first and last bar of a session must read 09:30 and 15:45 in ET on BOTH sides of a
    transition, and both sessions must hold the same 376 bars. A pipeline that filtered in
    UTC would be wrong for half the year, on a set of days nobody enumerates.
    """
    df = gb.dataset_k_dst(transition)
    loaded = fd.load(write_store(df, tmp_path, f"K_{transition}"), "ES")
    per_day = {day: g for day, g in loaded.groupby("day")}
    assert sorted(per_day) == [before, after]
    for day, g in per_day.items():
        et = pd.to_datetime(g["t"], utc=True).dt.tz_convert(gb.ET)
        assert len(g) == gb.FULL_SESSION_BARS, day
        assert et.dt.strftime("%H:%M").iloc[0] == "09:30", day
        assert et.dt.strftime("%H:%M").iloc[-1] == "15:45", day


@pytest.mark.parametrize("transition,utc_before,utc_after", [
    # EST -> EDT: the clocks go forward, so the same 09:30 ET is an hour EARLIER in UTC.
    ("spring", 14, 13),
    # EDT -> EST: the clocks go back, so it is an hour LATER in UTC.
    ("fall", 13, 14),
])
def test_the_same_et_open_is_a_different_utc_hour_across_dst(transition, utc_before,
                                                             utc_after):
    """Protects: the fact that makes a hard-coded UTC hour a bug.

    09:30 ET is 14:30 UTC in winter and 13:30 UTC in summer. Any constant UTC stamp is
    therefore correct for at most one half of the year - which is precisely the
    `futures_fetch_multi.py:181` defect, one level up.
    """
    df = gb.dataset_k_dst(transition)
    et = pd.to_datetime(df["t"], utc=True).dt.tz_convert(gb.ET)
    opens = df.loc[et.dt.strftime("%H:%M") == "09:30", "t"]
    hours = [pd.Timestamp(x).hour for x in opens]
    assert hours == [utc_before, utc_after]
    assert abs(hours[0] - hours[1]) == 1


def test_the_globex_open_is_not_a_fixed_utc_hour():
    """Protects: the roll-page timestamp, stated as the arithmetic that makes 21:00 wrong.

    The Globex open is 18:00 ET. That is 23:00 UTC under EST and 22:00 UTC under EDT - two
    different constants, which is one more than a hard-coded stamp can be.
    """
    est_sunday = gb.globex_open_utc(dt.date(2026, 3, 1))       # before spring forward
    edt_sunday = gb.globex_open_utc(gb.K_SPRING_FORWARD)       # after
    assert est_sunday.hour == 23
    assert edt_sunday.hour == 22
    assert gb.globex_open_utc(dt.date(2025, 10, 26)).hour == 22   # EDT, before fall back
    assert gb.globex_open_utc(gb.K_FALL_BACK).hour == 23          # EST, after
    assert gb.K_HARDCODED_PAGE_UTC_HOUR not in {22, 23}


def test_the_hard_coded_page_stamp_lands_mid_session_in_winter():
    """Protects: the exact consequence of `futures_fetch_multi.py:181`.

    21:00 UTC is 17:00 ET under EDT - the daily maintenance break, adjacent to the 18:00
    reopen, so the March, June and September rolls land close enough to a session boundary
    to be harmless. Under EST it is 16:00 ET, which is inside the Globex session, so the
    DECEMBER roll lands mid-session and produces a calendar day carrying two contracts.
    One line, wrong on one roll in four.

    RECOMMENDATION (not implemented - `scripts/` is outside this suite's remit): build the
    page stamp from 18:00 ET localised to America/New_York and converted, exactly as
    `tests/golden/build.py::globex_open_utc` does, instead of a literal 21:00 UTC.
    """
    summer = gb.hardcoded_page_stamp_et(dt.date(2025, 9, 12))     # EDT roll
    winter = gb.hardcoded_page_stamp_et(dt.date(2025, 12, 12))    # EST roll
    assert summer == dt.time(17, 0)
    assert winter == dt.time(16, 0)
    assert winter < gb.K_GLOBEX_OPEN_ET
    assert winter != summer


# ================================================= 7. EARLY CLOSE / FULL SESSION (dataset L)

def test_the_two_session_lengths_are_what_the_clock_says():
    """Protects: the bar counts the whole early-close argument rests on.

    09:30-12:59 inclusive is 210 start-stamped minutes (a 13:00 ET close).
    09:30-15:45 inclusive is 376. 210 is 55.9% of a session and clears a `> 200` filter by
    ten bars.
    """
    df = gb.dataset_l_sessions()
    et = pd.to_datetime(df["t"], utc=True).dt.tz_convert(gb.ET)
    counts = et.dt.date.value_counts().to_dict()
    assert counts[gb.L_EARLY_CLOSE_DAY] == gb.EARLY_CLOSE_BARS == 210
    assert counts[gb.L_FULL_DAY] == gb.FULL_SESSION_BARS == 376
    assert gb.early_close_last_bar_et() == dt.time(12, 59)
    assert gb.full_session_last_bar_et() == dt.time(15, 45)
    assert gb.EARLY_CLOSE_BARS > 200          # the reason the filter lets it through


# RATCHET CLEARED 2026-09-13: session_frames now requires the day to open on the
# window's first minute, close on its last, and hold one bar for every minute between.
@needs_parquet
def test_an_early_close_is_not_treated_as_a_full_session(tmp_path):
    """Protects: the funnel's 'full session' filter meaning what it says.

    The correct expectation, encoded rather than weakened: every frame `session_frames`
    returns as a session is a complete session for its day. Pinned to the defect above.
    """
    df = gb.dataset_l_sessions()
    loaded = fd.load(write_store(df, tmp_path, "L"), "ES")
    sessions = fd.session_frames(loaded)
    lengths = sorted(len(g) for g in sessions)
    assert lengths == [gb.FULL_SESSION_BARS], (
        f"session_frames returned sessions of lengths {lengths}; a 210-bar early close is "
        f"not a {gb.FULL_SESSION_BARS}-bar session")


@needs_parquet
def test_the_early_close_is_dropped_rather_than_scaled(tmp_path):
    """Protects: the SHAPE of the fix, so a partial one cannot pass unnoticed.

    UPDATED when the filter learned to test completeness. This test used to assert the
    defect - that `session_frames` returned both the 210-bar early close and the 376-bar
    full day - and its docstring said it was expected to fail the day the filter changed.
    It did, so here is the new characterisation.

    The early close is DROPPED, not rescaled. That is a deliberate and slightly lossy choice:
    a genuine 13:00 close is good data, and a real CME calendar would let it be kept and
    normalised. The repo has no such calendar - the equity one is measurably wrong for this
    market, reporting 210 minutes for three days on which the futures store correctly holds
    225 - so the safe direction is to exclude a short day rather than average it in as though
    it were whole. Measured cost on the real store: 3 of 326 ES sessions.
    """
    df = gb.dataset_l_sessions()
    loaded = fd.load(write_store(df, tmp_path, "L_char"), "ES")
    lengths = sorted(len(g) for g in fd.session_frames(loaded))
    assert lengths == [gb.FULL_SESSION_BARS]
    assert gb.EARLY_CLOSE_BARS == 210
    assert gb.EARLY_CLOSE_BARS > 200, "the bar count that used to clear the old `> 200` filter"


def test_the_session_length_is_derived_from_the_window_not_written_down():
    """Protects: the one place the session length lives. 09:30-15:45 inclusive is 376."""
    assert fd.SESSION_BARS == gb.FULL_SESSION_BARS == 376
    assert fd.OPEN_ET == "09:30" and fd.CLOSE_ET == "15:45"


@needs_parquet
def test_a_session_that_stops_before_the_bell_is_dropped_even_at_full_length(tmp_path):
    """Protects: that the filter tests the CLOCK, not only the count.

    A day holding 376 bars that all sit in the wrong part of the session is not a session.
    Without the first-and-last-minute check a bare count would admit it.
    """
    import datetime as dt
    full = gb.dataset_b_linear_trend(day=dt.date(2025, 12, 16))
    shifted = gb.dataset_b_linear_trend(day=dt.date(2025, 12, 15))
    shifted = shifted.copy()
    shifted["t"] = pd.to_datetime(shifted["t"], utc=True) - pd.Timedelta(minutes=30)
    df = pd.concat([shifted, full], ignore_index=True)
    loaded = fd.load(write_store(df, tmp_path, "shifted"), "ES")
    kept = fd.session_frames(loaded)
    assert [len(g) for g in kept] == [gb.FULL_SESSION_BARS]
    assert kept[0]["hm"].iloc[0] == "09:30" and kept[0]["hm"].iloc[-1] == "15:45"


def test_a_session_below_the_threshold_is_dropped(tmp_path):
    """Protects: that the filter does something. A 150-bar stub is excluded, so the bug is
    the threshold's LEVEL, not its absence - which is what makes the one-line calendar fix
    sufficient."""
    stub = gb.dataset_b_linear_trend(day=dt.date(2025, 12, 15), bars=150)
    full = gb.dataset_b_linear_trend(day=dt.date(2025, 12, 16))
    df = pd.concat([stub, full], ignore_index=True)
    loaded = fd.load(write_store(df, tmp_path, "stub"), "ES")
    assert [len(g) for g in fd.session_frames(loaded)] == [gb.FULL_SESSION_BARS]


# ================================================================ LOOK-AHEAD (dataset H)

def test_dataset_h_really_embeds_the_future():
    """Protects: the fixture. If H stops containing future information, every test below it
    proves nothing - they would all be passing against a clean series."""
    df = gb.dataset_h_lookahead()
    embedded = df[gb.H_ORACLE_COL].to_numpy(float)
    recomputed = gb.oracle_next_return(df)
    np.testing.assert_allclose(embedded[:-1], recomputed[:-1], rtol=0, atol=0)
    assert np.isnan(embedded[-1])
    # It is genuinely future information: it correlates perfectly with the NEXT bar's move
    # and is not obtainable from the current one.
    c = df["c"].to_numpy(float)
    np.testing.assert_allclose(embedded[:-1] * c[:-1], np.diff(c), rtol=0, atol=1e-9)


def test_the_causality_detector_catches_the_embedded_oracle():
    """Protects: `features.assert_causal` itself.

    A look-ahead detector that has never been shown to catch a look-ahead is decoration. The
    oracle here is next bar's return expressed as a feature function, so perturbing a bar
    moves an EARLIER feature value - which is exactly what the detector sweeps for, and it
    reports the first leaking index rather than just failing.
    """
    df = gb.dataset_h_lookahead()
    oracle = fe.Feature(gb.H_ORACLE_COL, "lookahead",
                        lambda d: d["c"].shift(-1) / d["c"] - 1.0, ("c",), 0,
                        "next bar's return - the thing that must never ship")
    with pytest.raises(AssertionError, match="is not causal"):
        fe.assert_causal(oracle, df)


def test_the_shipped_feature_library_is_causal_on_the_adversarial_series():
    """Protects: every feature the funnel builds, against the series designed to expose a leak.

    H is 180 quiet bars followed by a hard 20-bar ramp, so any statistic computed over the
    whole series rather than a trailing window has a different value in the quiet stretch
    depending on whether the ramp exists. `opening_range_pos` once shipped with a leak
    confined to the first 30 bars; `audit_causality` sweeps early indices for that reason,
    and this asserts the whole library comes back clean.
    """
    failures = fe.audit_causality(fe.library(), gb.dataset_h_lookahead())
    assert failures == {}, failures


def test_the_funnel_never_builds_the_oracle_column():
    """Protects: the boundary between the fixture's poison and the funnel's inputs.

    `FeatureSet.build` must produce only its declared features. A frame carrying an extra
    column of future information must not have that column travel into the feature matrix.
    """
    df = gb.dataset_h_lookahead()
    X, skipped = fe.library().build(df, strict=False)
    assert gb.H_ORACLE_COL not in X.columns
    assert gb.H_ORACLE_COL not in set(skipped)
    assert len(X) == len(df)


# ================================================================ SLIPPAGE (dataset E)

def test_measured_spread_matches_the_designed_profile():
    """Protects: `measure_spread_ticks`, against a profile decided in advance.

    E quotes 4 ticks for the first 20 bars and 1 tick for the remaining 100. Median 1.00,
    one-tick share exactly 100/120. The MEAN is 1.50 - and the median is the number the cost
    model must take, because using the mean here would overcharge every backtest by 50% on
    the strength of twenty opening bars no strategy has to trade.
    """
    df = gb.dataset_e_spread_profile()
    m = ex.measure_spread_ticks(df, tick=gb.TICK)
    assert m["median_ticks"] == gb.E_MEDIAN_SPREAD_TICKS == 1.0
    assert m["one_tick_share"] == pytest.approx(gb.E_ONE_TICK_SHARE)
    assert m["p90_ticks"] == float(gb.E_WIDE_TICKS)
    assert m["n"] == float(gb.E_BARS)
    assert m["mean_ticks"] == pytest.approx(1.5)
    assert m["mean_ticks"] > m["median_ticks"]


@pytest.mark.parametrize("bar,spread_ticks", [(0, gb.E_WIDE_TICKS),
                                              (gb.E_BARS - 1, gb.E_NARROW_TICKS)])
def test_a_market_order_crosses_exactly_the_quoted_spread(bar, spread_ticks):
    """Protects: fill price and slippage on a book whose width is known.

    A buy market order small against the touch fills at the ask, and the slippage booked is
    the distance from the mid: `spread/2 x multiplier x quantity`. On the wide bar that is
    4 ticks (0.50 wide, $1.25 of slippage on MES); on the narrow bar 1 tick ($0.3125).
    """
    from quant_brain.core.execution import OrderIntent, OrderType, Side

    df = gb.dataset_e_spread_profile()
    row = df.iloc[bar]
    quote = ex.Quote(bid=float(row["bid"]), ask=float(row["ask"]),
                     bid_size=100, ask_size=100)
    assert round(quote.spread, 10) == round(spread_ticks * gb.TICK, 10)

    sim = ex.ExecutionSimulator(cost=ex.CostModel.for_contract("MES"), symbol="MES")
    intent = OrderIntent(symbol="MES", side=Side.BUY, quantity=1,
                         order_type=OrderType.MARKET)
    res = sim.execute(intent, quote)
    assert res.filled
    assert res.fill.price == pytest.approx(quote.ask)
    expected_slip = (quote.spread / 2) * inst.get("MES").spec.multiplier * 1
    assert res.fill.slippage == pytest.approx(expected_slip)
    assert res.fill.commission == pytest.approx(0.61)


def test_size_beyond_the_touch_walks_the_book_by_a_known_amount():
    """Protects: the size-impact term, which is linear in books consumed.

    With 100 resting and 300 ordered, the order consumes (300-100)/100 = 2 books and pays
    `impact_ticks_per_book x 2 x tick` beyond the ask. Stated here because it is the
    modelling assumption most likely to be wrong for size that matters, and a silent change
    to it would move every large-size result.
    """
    from quant_brain.core.execution import OrderIntent, OrderType, Side

    df = gb.dataset_e_spread_profile()
    row = df.iloc[gb.E_BARS - 1]
    quote = ex.Quote(bid=float(row["bid"]), ask=float(row["ask"]),
                     bid_size=100, ask_size=100)
    sim = ex.ExecutionSimulator(cost=ex.CostModel.for_contract("MES"), symbol="MES")
    intent = OrderIntent(symbol="MES", side=Side.BUY, quantity=300,
                         order_type=OrderType.MARKET)
    res = sim.execute(intent, quote)
    assert res.filled
    books = (300 - 100) / 100
    expected = quote.ask + sim.cost.impact_ticks_per_book * books * gb.TICK
    assert res.fill.price == pytest.approx(expected)


def test_the_futures_validator_accepts_a_well_formed_book():
    """Protects: E as a clean case through `_check_quotes`. Bid never exceeds ask and both
    are positive, so the crossed-book FAIL must not fire - and the 'no quotes' INFO must
    not fire either, because this store has them."""
    rep = futures_report(gb.dataset_e_spread_profile())
    assert not rep.failed
    assert "crossed_book" not in checks(rep)
    assert "quote_nonpositive" not in checks(rep)
    assert "quotes" not in checks(rep)          # the "no bid/ask columns" INFO


# ================================================================ DRAWDOWN (dataset G)

def test_the_drawdown_path_breaches_the_mll_on_the_known_bar():
    """Protects: the liquidation boundary, to the bar.

    One long ES contract from 5000.00 falling a tick a bar loses $12.50 a bar. A $50K
    Topstep Combine's MLL is $2,000 below the starting balance, so equity reaches it at bar
    160 and at no earlier bar. `breached()` is `equity <= mll`, so bar 160 - exactly at the
    limit - is a breach; a `<` would let the account trade on while liquidated.
    """
    df, breach_bar = gb.dataset_g_drawdown()
    account = ts.TopstepAccount(profile=ts.combine(50_000, profit_target=3_000.0))
    assert account.mll == account.profile.starting_balance - 2_000.0

    first_breach = None
    for i in range(len(df)):
        account.mark(gb.g_unrealized(df, i))
        if account.breached():
            first_breach = i
            break
    assert first_breach == breach_bar == gb.G_BREACH_BAR
    assert gb.g_unrealized(df, breach_bar) == -gb.G_LOSS_AT_BREACH == -2_000.0


def test_the_bar_before_the_breach_is_clear_by_one_tick_of_value():
    """Protects: the off-by-one. Bar 159 is -$1,987.50, which is $12.50 - one ES tick -
    clear of the limit. A fixture that breached three bars early would let a wrong
    comparison pass."""
    df, breach_bar = gb.dataset_g_drawdown()
    account = ts.TopstepAccount(profile=ts.combine(50_000, profit_target=3_000.0))
    account.mark(gb.g_unrealized(df, breach_bar - 1))
    assert not account.breached()
    assert account.distance_to_mll == pytest.approx(inst.get("ES").spec.tick_value)


def test_the_mll_does_not_advance_on_an_intraday_mark():
    """Protects: Topstep's specific rule, which the drawdown fixture depends on.

    The MLL trails the END-OF-DAY balance and nothing else. If an intraday mark moved it,
    G's breach bar would depend on the path's high-water point rather than on its level, and
    the fixture's declared bar would be meaningless.
    """
    df, _ = gb.dataset_g_drawdown()
    account = ts.TopstepAccount(profile=ts.combine(50_000, profit_target=3_000.0))
    before = account.mll
    account.mark(+5_000.0)          # a big unrealised gain
    assert account.mll == before
    account.mark(gb.g_unrealized(df, 10))
    assert account.mll == before
