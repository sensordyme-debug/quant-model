"""Tests for the multi-instrument / quote futures fetcher.

WHAT IS WORTH TESTING HERE, AND WHAT IS NOT
--------------------------------------------
The fetch itself is IBKR's behaviour and cannot be asserted on: it is slow, it needs a
gateway, and re-running it would issue hours of historical-data requests from the test
suite. **No test in this file connects to anything.** That is not a convenience - this repo
runs `pytest` at 09:25 as the live sleeve's launch gate (see `conftest.RUNNER_TESTS`), and a
test that opened an IB connection at that moment would be competing with the trader for the
gateway. The one live check is behind `IB_LIVE_TESTS=1` and stays skipped by default.

What IS worth testing is everything between the wire and the disk, because that is where a
futures store gets silently wrong:

  1. THE ROLL CONVENTION IS THE SAME ONE ES WAS BUILT WITH. The new stores are meant to be
     usable alongside `data/futures/ES.parquet` in a single backtest. If this script rolled
     on a different day, or gave the first contract a different lead-in, the two stores
     would disagree about which instrument a given minute belongs to and every cross-
     instrument result would be an artefact of the mismatch. So `windows()` is pinned
     against `futures_data._windows` directly, not against a hard-coded expectation - a
     copy that is only checked against itself is not checked.

  2. THE `BID_ASK` FIELD MAPPING. IBKR packs four different quantities into one bar's OHLC
     (avg bid / max ask / min bid / avg ask). Get that mapping wrong and the store still
     looks perfectly plausible - prices in the right range, no validation failure - while
     every measured spread is nonsense and the cost model that was supposed to stop
     assuming is now assuming something worse. It is asserted field by field.

  3. THE REFUSAL ACTUALLY REFUSES. `validate_and_write` is the only thing standing between a
     bad fetch and a store the research reads for months. "Futures store was written
     unvalidated" is a *resolved* blocker; a refusal nobody tests is how it un-resolves.
     Every test of it asserts the file is absent afterwards, not merely that the function
     returned False.
"""
from __future__ import annotations

import datetime as dt
import os
import socket
import sys

import futures_data
import futures_fetch_multi as fm
import pandas as pd
import pytest

from quant_brain.markets.futures_cme.dataquality import Severity, check_futures_frame


class _Bar:
    """The three fields of an `ib_async.BarData` the row builders read."""

    def __init__(self, date, o, h, low, c, v=-1.0):
        self.date, self.open, self.high, self.low, self.close, self.volume = (
            date, o, h, low, c, v)


def _codes(rep):
    return {f.check for f in rep.findings}


# ======================================================================================
# 1. THE ROLL CONVENTION MATCHES THE STORE ALREADY ON DISK
# ======================================================================================

def test_roll_constant_matches_the_script_that_built_the_es_store():
    """A different roll day makes the two stores disagree about the same minute."""
    assert fm.ROLL_DAYS == futures_data.ROLL_DAYS


def test_the_es_chain_is_the_same_five_expiries_futures_data_uses():
    assert fm.CHAINS["ES"] == futures_data.ES_CHAIN


def test_windows_reproduces_futures_data_window_arithmetic_exactly():
    """Pinned against the original function, not against a transcribed expectation.

    `windows` is a deliberate copy (the module docstring says why). The only way a copy
    stays honest is a test that runs both.
    """
    for chain in (futures_data.ES_CHAIN, futures_data.MES_CHAIN, fm.CHAINS["NQ"]):
        assert fm.windows(chain) == futures_data._windows(chain)


def test_the_es_windows_reproduce_the_deployed_store_span():
    """The strongest available check on the convention: the real ES store's own edges.

    `ES.parquet` was built by `futures_data.fetch` with these windows. If this module's
    first window starts on a different date, or its last ends on one, the copy has drifted
    from the thing it is supposed to match - and the drift is measured against 447,600 real
    bars rather than against another line of code.
    """
    path = fm.STORE / "ES.parquet"
    if not path.exists():
        pytest.skip("data/futures/ES.parquet not present")
    es = pd.read_parquet(path, columns=["t"])
    ts = pd.to_datetime(es["t"], utc=True)
    win = fm.windows(fm.CHAINS["ES"])
    assert ts.min().date() >= win[0][1]
    assert ts.max().date() <= win[-1][2]
    # and it really does reach the edges - a window far wider than the data would pass the
    # bounds above while telling us nothing.
    assert (ts.min().date() - win[0][1]).days <= 3
    assert (ts.max().date() - win[-1][2]).days == 0


def test_the_micro_chains_start_a_quarter_late_because_ibkr_dropped_those_expiries():
    """Measured on 2026-09-13: MESU5 / MNQU5 return error 200 by symbol and by month.

    Pinned so that a later run which quietly re-adds them has to justify it. The shorter
    chain is a fact about IBKR retention; it is also the reason MES/MNQ cannot be compared
    with ES over the full 1.25 years, which any user of these stores has to know.
    """
    assert fm.CHAINS["MES"][0][0] == "MESZ5"
    assert fm.CHAINS["MNQ"][0][0] == "MNQZ5"
    assert fm.CHAINS["ES"][0][0] == "ESU5"
    assert fm.CHAINS["NQ"][0][0] == "NQU5"
    assert len(fm.CHAINS["MES"]) == len(fm.CHAINS["ES"]) - 1


def test_every_chain_is_chronological_and_uses_quarterly_expiries():
    """A chain out of order stitches a series that revisits an expired contract."""
    for sym, chain in fm.CHAINS.items():
        months = [exp for _ls, exp in chain]
        assert months == sorted(months), sym
        for exp in months:
            d = dt.datetime.strptime(exp, "%Y%m%d").date()
            assert d.month in (3, 6, 9, 12), f"{sym} {exp} is not a quarterly expiry"


# ======================================================================================
# 2. PAGING
# ======================================================================================

def test_pages_walk_backwards_a_month_at_a_time_and_cover_the_window():
    start, end = dt.date(2026, 3, 12), dt.date(2026, 6, 10)
    stamps = fm._pages(start, end)
    assert stamps[0] == "20260610-21:00:00"
    dates = [dt.datetime.strptime(s[:8], "%Y%m%d").date() for s in stamps]
    assert dates == sorted(dates, reverse=True)
    # the last page ends at or before the window start, so a one-month duration reaches it
    assert dates[-1] > start
    assert (dates[-1] - start).days <= 30


def test_every_page_boundary_lands_outside_a_cme_session():
    """21:00 is after the CME close and before the next open, so no page splits a session."""
    for _ls, start, end in fm.windows(fm.CHAINS["ES"]):
        for stamp in fm._pages(start, end):
            assert stamp.endswith("-21:00:00")


def test_a_zero_length_window_requests_nothing():
    assert fm._pages(dt.date(2026, 1, 1), dt.date(2026, 1, 1)) == []


# ======================================================================================
# 3. THE BID_ASK FIELD MAPPING  (see the module docstring: this is the silent one)
# ======================================================================================

def test_trades_rows_carry_ohlcv_and_contract_identity():
    t = pd.Timestamp("2026-06-10 14:30", tz="UTC")
    rows = fm._rows([_Bar(t, 5000.0, 5002.0, 4999.0, 5001.0, v=123.0)], "TRADES", "ESM6")
    assert rows == [{"t": t, "o": 5000.0, "h": 5002.0, "l": 4999.0, "c": 5001.0,
                     "v": 123.0, "contract": "ESM6"}]


def test_quote_rows_unpack_ibkrs_four_quantities_into_named_columns():
    """open=avg bid, close=avg ask, low=min bid, high=max ask. Asserted field by field.

    Deliberately uses four distinct values so a transposition cannot pass: if `bid` were
    read from `low` the assertion below would see 4999.5, not 5000.0.
    """
    t = pd.Timestamp("2026-06-10 14:30", tz="UTC")
    row = fm._rows([_Bar(t, 5000.00, 5002.50, 4999.50, 5000.25)], "BID_ASK", "ESM6")[0]
    assert row["bid"] == 5000.00       # open  = time-average bid
    assert row["ask"] == 5000.25       # close = time-average ask
    assert row["bid_low"] == 4999.50   # low   = minimum bid
    assert row["ask_high"] == 5002.50  # high  = maximum ask
    assert row["spread"] == pytest.approx(0.25)
    assert row["c"] == pytest.approx(5000.125)   # mid, so the validator has a price column
    assert row["contract"] == "ESM6"


def test_a_quote_row_carries_no_volume_column():
    """IBKR sends volume=-1 on a quote bar. A store that wrote it would be inventing trades.

    `check_futures_frame`'s stale-quote check grades a frozen price by whether volume
    printed during it; -1 would make every quiet overnight run look like a stuck feed with
    negative turnover. Absent is the honest representation, not zero and not -1.
    """
    row = fm._rows([_Bar(pd.Timestamp("2026-06-10", tz="UTC"), 1.0, 2.0, 0.5, 1.5, v=-1.0)],
                   "BID_ASK", "ESM6")[0]
    assert "v" not in row


def test_a_quote_store_satisfies_the_validators_bid_ask_check():
    """The point of the quote store: `_check_quotes` stops saying the spread is assumed.

    That check emits its "the spread is ASSUMED by the cost model" INFO only when the frame
    has no bid/ask columns, so the evidence the store landed is the *absence* of that
    finding - and, on an OHLCV frame of the same prices, its presence. Both directions are
    asserted, because "no finding" is also what a check that silently stopped running looks
    like.
    """
    t = pd.date_range(pd.Timestamp("2026-06-10 09:30", tz="America/New_York"),
                      periods=30, freq="1min").tz_convert("UTC")
    bars = [_Bar(ts, 5000.0, 5000.5, 4999.75, 5000.25) for ts in t]
    quoted = pd.DataFrame(fm._rows(bars, "BID_ASK", "ESM6"))
    rep = check_futures_frame("ES_quotes", quoted, time_col="t")
    assert not rep.failed, [f.line() for f in rep.findings]
    assert "quotes" not in _codes(rep)
    assert not {"crossed_book", "quote_nonpositive"} & _codes(rep)

    ohlcv = pd.DataFrame(fm._rows(bars, "TRADES", "ESM6"))
    assumed = next(f for f in check_futures_frame("ES", ohlcv, time_col="t").findings
                   if f.check == "quotes")
    assert assumed.severity is Severity.INFO and "ASSUMED" in assumed.detail


# ======================================================================================
# 4. STITCHING: ONE CONTRACT OWNS EACH MINUTE
# ======================================================================================

def _minutes(day: str, contract: str, price: float, n: int = 3) -> pd.DataFrame:
    t = pd.date_range(pd.Timestamp(f"{day} 10:00", tz="UTC"), periods=n, freq="1min")
    return pd.DataFrame({"t": t, "o": price, "h": price, "l": price, "c": price,
                         "v": 10.0, "contract": contract})


@pytest.fixture()
def two_contract_chain(monkeypatch):
    """A synthetic chain whose roll falls on 2025-12-11, so the seam is easy to point at."""
    chain = [("TTZ5", "20251219"), ("TTH6", "20260320")]
    monkeypatch.setitem(fm.CHAINS, "TT", chain)
    return chain


def test_stitch_gives_each_minute_to_the_contract_whose_quarter_owns_it(two_contract_chain):
    """The seam: the back month's bars before the roll and the front month's after it.

    Both contracts quote all four days here, which is what really happens - the roll is a
    choice about which quote to believe, and the whole hazard is making that choice
    implicitly. 2025-12-11 is the roll, and the rule is that the outgoing contract owns the
    roll day itself.
    """
    frames = [_minutes(d, "TTZ5", 100.0) for d in ("2025-12-09", "2025-12-10",
                                                   "2025-12-11", "2025-12-12")]
    frames += [_minutes(d, "TTH6", 105.0) for d in ("2025-12-09", "2025-12-10",
                                                    "2025-12-11", "2025-12-12")]
    out = fm.stitch("TT", frames, "TRADES")
    owner = {str(k): v for k, v in
             out.set_index(out["t"].dt.date)["contract"].groupby(level=0).first().items()}
    assert owner["2025-12-09"] == "TTZ5"
    assert owner["2025-12-10"] == "TTZ5"
    assert owner["2025-12-11"] == "TTZ5"     # roll day belongs to the outgoing contract
    assert owner["2025-12-12"] == "TTH6"


def test_stitch_keeps_each_timestamp_exactly_once(two_contract_chain):
    frames = [_minutes("2025-12-11", "TTZ5", 100.0), _minutes("2025-12-11", "TTH6", 105.0)]
    out = fm.stitch("TT", frames, "TRADES")
    assert out["t"].is_unique
    assert len(out) == 3


def test_stitch_drops_bars_from_outside_a_contracts_own_quarter(two_contract_chain):
    """A back-month bar fetched by an over-wide page must not reach the store.

    Without this the store would carry the illiquid far month's prints, which are a
    different instrument's price and quietly wrong rather than obviously missing.
    """
    frames = [_minutes("2025-09-01", "TTZ5", 100.0),   # before TTZ5's own window opens
              _minutes("2025-12-10", "TTZ5", 100.0),
              _minutes("2025-10-01", "TTH6", 105.0)]   # far month, months early
    out = fm.stitch("TT", frames, "TRADES")
    assert set(out["contract"]) == {"TTZ5"}
    assert out["t"].dt.date.unique().tolist() == [dt.date(2025, 12, 10)]


def test_stitch_returns_a_frame_the_validator_accepts(two_contract_chain):
    """End to end on the shape that actually gets written: sorted, unique, single-owner."""
    frames = [_minutes(d, "TTZ5", 100.0) for d in ("2025-12-09", "2025-12-10")]
    frames += [_minutes(d, "TTH6", 100.5) for d in ("2025-12-12", "2025-12-15")]
    out = fm.stitch("TT", frames, "TRADES")
    rep = check_futures_frame("TT", out, time_col="t")
    assert not rep.failed, [f.line() for f in rep.findings]
    assert out["t"].is_monotonic_increasing


# ======================================================================================
# 5. THE REFUSAL
# ======================================================================================

def test_a_clean_store_is_written(tmp_path):
    df = _minutes("2025-12-10", "TTZ5", 100.0, n=200)
    path = tmp_path / "TT.parquet"
    assert fm.validate_and_write("TT", df, path) is True
    assert path.exists()
    assert len(pd.read_parquet(path)) == 200


def test_a_crossed_book_is_refused_and_nothing_reaches_disk(tmp_path):
    """Bid above ask cannot be true, so the quote store must not exist at all afterwards.

    Asserting on the file rather than on the return value is the point: a caller that
    ignored the boolean would still be unable to research on a broken store.
    """
    n = 10
    t = pd.date_range(pd.Timestamp("2026-06-10 14:30", tz="UTC"), periods=n, freq="1min")
    df = pd.DataFrame({"t": t, "bid": 5000.0, "ask": 5000.25, "bid_low": 4999.5,
                       "ask_high": 5000.5, "spread": 0.25, "c": 5000.125,
                       "contract": "ESM6"})
    df.loc[4, "ask"] = 4999.0          # one crossed minute is enough
    path = tmp_path / "ES_quotes.parquet"
    assert fm.validate_and_write("ES_quotes", df, path) is False
    assert not path.exists()


def test_the_validator_imports_before_the_first_request_not_after_the_last(tmp_path):
    """Regression: the write path's imports must be paid for up front, not at the end.

    This one has already happened. `python scripts/futures_fetch_multi.py` puts `scripts/`
    on `sys.path` and NOT the repo root, so `import quant_brain` raised - but because the
    validator was imported lazily inside `validate_and_write`, the failure surfaced only
    after all fifteen MES pages had been fetched. 27 minutes of IBKR history, discarded, and
    no store written.

    `preflight()` is the fix and it is only worth anything if it actually resolves the
    import, so this calls it directly. The subprocess check below covers the path half.
    """
    fm.preflight()


def test_the_script_can_import_the_validator_when_run_as_a_command(tmp_path):
    """The failing case exactly: run the script as a file, from a cwd that is not the repo.

    `--report` is the cheapest entry point that reaches the validator import, and it needs
    no gateway. Asserting on the absence of ModuleNotFoundError rather than on the exit code
    matters - `--report` legitimately exits non-zero when a store is missing, and a test
    that only checked the code would pass while the import was still broken.
    """
    import subprocess

    proc = subprocess.run(
        [sys.executable, str(fm.REPO / "scripts" / "futures_fetch_multi.py"), "--report"],
        cwd=tmp_path, capture_output=True, text=True, timeout=300, check=False)
    combined = proc.stdout + proc.stderr
    assert "ModuleNotFoundError" not in combined, combined[-2000:]
    assert "Traceback" not in combined, combined[-2000:]


def test_a_store_without_contract_identity_is_refused(tmp_path):
    """A roll error is invisible in price; without identity it cannot even be looked for."""
    df = _minutes("2025-12-10", "TTZ5", 100.0, n=20).drop(columns=["contract"])
    path = tmp_path / "TT.parquet"
    assert fm.validate_and_write("TT", df, path) is False
    assert not path.exists()


def test_an_impossible_intrabar_move_is_refused(tmp_path):
    """20% inside one minute in one contract is a bad print, not a market."""
    df = _minutes("2025-12-10", "TTZ5", 100.0, n=20)
    df.loc[10, "c"] = 400.0
    path = tmp_path / "TT.parquet"
    assert fm.validate_and_write("TT", df, path) is False
    assert not path.exists()


def test_an_empty_store_is_refused(tmp_path):
    path = tmp_path / "TT.parquet"
    assert fm.validate_and_write("TT", pd.DataFrame(), path) is False
    assert not path.exists()


def test_dry_run_validates_but_writes_nothing(tmp_path):
    df = _minutes("2025-12-10", "TTZ5", 100.0, n=20)
    path = tmp_path / "TT.parquet"
    assert fm.validate_and_write("TT", df, path, dry_run=True) is True
    assert not path.exists()


# ======================================================================================
# 6. THE CONTRACT-RESOLUTION TRAP, AND PACING
# ======================================================================================

class _FakeContract:
    def __init__(self, con_id):
        self.conId = con_id
        self.localSymbol = "MESU5"


class _FakeIB:
    def __init__(self, result):
        self._result = result

    def qualifyContracts(self, *_contracts):
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def test_an_unresolved_expiry_is_detected_by_conid_not_by_list_length():
    """ib_async 2.1.0 returns a non-empty list for a contract IBKR could not resolve.

    This is exactly how MESU5 comes back, and a `if not qualified:` guard (which is what
    `futures_data` has) sails past it and then dies inside `reqHistoricalData` with an
    unrelated AttributeError. Checking `conId` is the difference between "IBKR dropped this
    expiry" - a finding worth reporting - and a crash three contracts later.
    """
    assert fm._qualify(_FakeIB([_FakeContract(0)]), "MES", "MESU5") is None
    assert fm._qualify(_FakeIB([None]), "MES", "MESU5") is None
    assert fm._qualify(_FakeIB([]), "MES", "MESU5") is None


def test_a_resolved_expiry_is_returned():
    con = _FakeContract(511209103)
    assert fm._qualify(_FakeIB([con]), "MES", "MESU6") is con


def test_a_qualify_exception_is_a_finding_not_a_crash():
    assert fm._qualify(_FakeIB(RuntimeError("timeout")), "MES", "MESU5") is None


def test_the_pacer_sleeps_only_once_the_ibkr_limit_is_reached(monkeypatch):
    """60 requests / 10 min is IBKR's rule; exceeding it earns error 162 and a silent hole."""
    slept: list[float] = []
    monkeypatch.setattr(fm.time, "sleep", slept.append)
    pacer = fm.Pacer(limit=3, window=600)
    for _ in range(3):
        pacer.wait()
    assert slept == []
    pacer.wait()
    assert len(slept) == 1 and slept[0] > 0


def test_the_pacer_default_stays_under_ibkrs_published_limit():
    assert fm.MAX_REQUESTS < 60
    assert fm.WINDOW_SECONDS == 600


# ======================================================================================
# 7. THE SPREAD SUMMARY  (the deliverable of OWNER-3 step 1)
# ======================================================================================

def _quote_frame(spread_by_hour: dict[int, float]) -> pd.DataFrame:
    rows = []
    for hour, spread in spread_by_hour.items():
        for minute in range(30):
            t = pd.Timestamp(f"2026-06-10 {hour:02d}:{minute:02d}", tz="America/New_York")
            rows.append({"t": t.tz_convert("UTC"), "bid": 5000.0, "ask": 5000.0 + spread,
                         "bid_low": 5000.0, "ask_high": 5000.0 + spread,
                         "spread": spread, "c": 5000.0 + spread / 2, "contract": "ESM6"})
    return pd.DataFrame(rows)


def _line(text: str, label: str) -> str:
    return next(ln for ln in text.splitlines() if ln.strip().startswith(label))


def test_the_spread_summary_separates_the_cash_session_from_overnight():
    """A sleeve that trades 09:30-16:00 must not be costed at 3am's book.

    Built so the two regimes cannot be confused: one tick inside RTH, four ticks outside.
    """
    text = fm.spread_summary(_quote_frame({10: 0.25, 3: 1.00}))
    assert "1.00 ticks" in _line(text, "RTH")
    assert "4.00 ticks" in _line(text, "overnight")


def test_the_summary_converts_to_basis_points_against_each_rows_own_mid():
    """bps is the only unit comparable across instruments and across index levels.

    A fixed 0.25-point tick is 0.500 bps at a 5,000 mid and 0.333 bps at 7,500 - so the
    conversion has to use the price, and using each row's own mid rather than one chosen
    level is what stops the figure being an artefact of the level someone picked. Both
    levels are checked, because a hard-coded divisor would pass the first alone.
    """
    at_5000 = fm.spread_summary(_quote_frame({10: 0.25}))
    assert "0.500 bps" in _line(at_5000, "all hours")
    high = _quote_frame({10: 0.25})
    high[["bid", "ask", "bid_low", "ask_high", "c"]] += 2500.0   # mid ~7500
    assert "0.333 bps" in _line(fm.spread_summary(high), "all hours")


def test_the_summary_reports_the_round_trip_cost_at_the_rth_quote():
    """F-2a's measured cost is a ROUND TRIP, so the comparable figure is the full spread.

    Crossing costs half the quoted spread per side, so a round trip is one whole spread.
    Reporting the half against a round-trip benchmark would understate the charge by 2x,
    which is the direction that invents an edge - so both numbers are printed and pinned.
    """
    line = _line(fm.spread_summary(_quote_frame({10: 0.25, 3: 1.00})), "round trip")
    assert "1.00 ticks = 0.500 bps" in line
    assert "half-spread per side 0.250 bps" in line


def test_an_unparsable_quote_does_not_shift_every_later_minute_into_the_wrong_session():
    """A NaN spread must drop out of the statistics without moving the RTH boundary.

    The bug this pins is a length mismatch: drop the NaNs from the spreads, then index the
    result with a mask built on the full frame, and every minute after the first bad quote
    is attributed to the wrong session - silently, and in the direction that makes the cash
    session look like whatever the overnight book was doing.
    """
    df = _quote_frame({10: 0.25, 3: 1.00})
    clean = fm.spread_summary(df)
    df.loc[0, "spread"] = float("nan")       # one unusable RTH minute
    holed = fm.spread_summary(df)
    assert "n=     29" in _line(holed, "RTH")        # 30 RTH minutes less the NaN
    assert "1.00 ticks" in _line(holed, "RTH")       # and the survivors keep their session
    assert _line(clean, "overnight") == _line(holed, "overnight")


def test_a_frame_with_no_parsable_quote_says_so_instead_of_raising():
    df = _quote_frame({10: 0.25})
    df["spread"] = float("nan")
    assert fm.spread_summary(df) == "spread: no parsable quotes"


def test_a_non_positive_mid_cannot_divide_the_bps_conversion_by_zero():
    df = _quote_frame({10: 0.25})
    df.loc[0, "c"] = 0.0
    assert "n=     29" in _line(fm.spread_summary(df), "RTH")


def test_the_summary_states_whether_the_assumed_one_tick_survives_measurement():
    """The whole reason the quote store exists, so it is stated in words, not left to eyes."""
    assert "is SUPPORTED" in fm.spread_summary(_quote_frame({10: 0.25}))
    assert "NOT supported" in fm.spread_summary(_quote_frame({10: 1.50}))


# ======================================================================================
# 8. THE STORES ON DISK  (skips until the fetch has run)
# ======================================================================================

NEW_STORES = ["MES.parquet", "NQ.parquet", "MNQ.parquet",
              "ES_quotes.parquet", "MES_quotes.parquet",
              "NQ_quotes.parquet", "MNQ_quotes.parquet"]


@pytest.mark.parametrize("name", NEW_STORES)
def test_each_store_written_by_this_script_passes_validation(name):
    """Re-run the gate over what is actually on disk.

    `validate_and_write` refuses at write time, but a store can be replaced, truncated or
    half-copied afterwards, and the research reads the file rather than the moment it was
    written. Skips rather than fails when a store has not been fetched yet, so the suite is
    green before the multi-hour run and meaningful after it.
    """
    path = fm.STORE / name
    if not path.exists():
        pytest.skip(f"{name} not fetched yet")
    df = pd.read_parquet(path)
    rep = check_futures_frame(path.stem, df, time_col="t")
    fails = [f.line() for f in rep.findings if f.severity is Severity.FAIL]
    assert not fails, fails


@pytest.mark.parametrize("name", NEW_STORES)
def test_each_store_is_sorted_unique_and_timezone_aware(name):
    """The three properties every consumer assumes and none of them re-checks."""
    path = fm.STORE / name
    if not path.exists():
        pytest.skip(f"{name} not fetched yet")
    df = pd.read_parquet(path, columns=["t"])
    ts = pd.to_datetime(df["t"])
    assert ts.dt.tz is not None
    assert ts.is_monotonic_increasing
    assert ts.is_unique


@pytest.mark.parametrize("name", ["MES", "NQ", "MNQ"])
def test_a_trades_store_stays_inside_its_chains_windows(name):
    """The store must not reach outside the quarters its own chain claims to cover."""
    path = fm.STORE / f"{name}.parquet"
    if not path.exists():
        pytest.skip(f"{name} not fetched yet")
    df = pd.read_parquet(path, columns=["t", "contract"])
    ts = pd.to_datetime(df["t"], utc=True)
    for ls, start, end in fm.windows(fm.CHAINS[name]):
        sub = ts[df["contract"] == ls]
        if not len(sub):
            continue
        assert sub.min().date() >= start, ls
        assert sub.max().date() <= end, ls


def test_a_quote_store_is_never_crossed_and_carries_a_positive_spread():
    """Asserted on the real file because the validator's FAIL is the only thing that would
    have stopped it being written, and a store can be overwritten after that gate."""
    path = fm.STORE / "ES_quotes.parquet"
    if not path.exists():
        pytest.skip("ES_quotes.parquet not fetched yet")
    df = pd.read_parquet(path, columns=["bid", "ask", "spread"])
    assert (df["ask"] >= df["bid"]).all()
    assert (df["spread"] >= 0).all()
    assert df["spread"].median() > 0


# ======================================================================================
# 9. THE ONE LIVE CHECK, OFF BY DEFAULT
# ======================================================================================

def _gateway_up(host: str = "127.0.0.1", port: int = 4002) -> bool:
    with socket.socket() as s:
        s.settimeout(2)
        return s.connect_ex((host, port)) == 0


@pytest.mark.skipif(os.environ.get("IB_LIVE_TESTS") != "1",
                    reason="opt in with IB_LIVE_TESTS=1; the 09:25 launch gate runs this "
                           "suite and must not open a competing gateway connection")
def test_the_front_contract_still_resolves_against_a_live_gateway():
    """Not part of the normal suite. Uses clientId 78 - one past the fetcher's 77 - so that
    running it while a fetch is in flight cannot evict the fetch's connection."""
    if not _gateway_up():
        pytest.skip("IB Gateway is not listening on 127.0.0.1:4002")
    from ib_async import IB

    ib = IB()
    ib.connect("127.0.0.1", 4002, clientId=78, timeout=30)
    try:
        con = fm._qualify(ib, "ES", fm.CHAINS["ES"][-1][0])
        assert con is not None and con.conId
    finally:
        ib.disconnect()
