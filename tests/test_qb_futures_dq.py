"""Tests for futures-specific data validation.

A validator nobody can make fail is decoration, so every check here is exercised against a
store built to break it. The real ES store is then run through the whole set as an
integration check, because a validator that only ever sees synthetic frames tends to
discover that real data has a shape it did not anticipate.
"""
from __future__ import annotations

import pandas as pd
import pytest

from quant_brain.core.dataquality import DataQualityError, Severity
from quant_brain.markets.futures_cme import dataquality as fdq

STORE = "data/futures/ES.parquet"


def _frame(closes, contracts=None, volumes=None, start="2025-06-10 09:30",
           **extra) -> pd.DataFrame:
    n = len(closes)
    t = pd.date_range(pd.Timestamp(start, tz="America/New_York"), periods=n, freq="1min")
    return pd.DataFrame({
        "t": t.tz_convert("UTC"),
        "o": closes, "h": closes, "l": closes, "c": closes,
        "v": volumes if volumes is not None else [10.0] * n,
        "contract": contracts if contracts is not None else ["ESU5"] * n,
        **extra,
    })


def _codes(rep):
    return {f.check for f in rep.findings}


def _sev(rep, check):
    return next(f.severity for f in rep.findings if f.check == check)


# ======================================================================================
# EACH CHECK FIRES ON A STORE BUILT TO BREAK IT
# ======================================================================================

def test_a_frame_without_contract_identity_is_refused():
    """A roll error is invisible in price, so identity is not optional."""
    df = _frame([100.0] * 10).drop(columns=["contract"])
    rep = fdq.check_futures_frame("ES", df, time_col="t")
    assert rep.failed
    assert "contract_identity" in _codes(rep)


def test_an_empty_frame_is_refused():
    rep = fdq.check_futures_frame("ES", pd.DataFrame(), time_col="t")
    assert rep.failed and "empty" in _codes(rep)


def test_a_roll_gap_is_reported():
    closes = [100.0] * 20 + [105.0] * 20            # 5% jump at the roll
    df = _frame(closes, ["ESU5"] * 20 + ["ESZ5"] * 20)
    rep = fdq.check_futures_frame("ES", df, time_col="t")
    assert "roll_gap" in _codes(rep)
    assert _sev(rep, "roll_gap") is Severity.WARN
    assert not rep.failed, "a roll gap is normal; only an unknown one is the hazard"


def test_a_small_roll_gap_is_recorded_but_not_warned():
    closes = [100.0] * 20 + [100.1] * 20            # 0.1%, under the 0.5% threshold
    rep = fdq.check_futures_frame("ES", _frame(closes, ["ESU5"] * 20 + ["ESZ5"] * 20),
                                  time_col="t")
    assert "rolls" in _codes(rep)
    assert "roll_gap" not in _codes(rep)


def test_a_single_contract_series_reports_no_roll():
    rep = fdq.check_futures_frame("ES", _frame([100.0] * 30), time_col="t")
    assert "rolls" in _codes(rep)
    assert "single contract" in next(f.detail for f in rep.findings if f.check == "rolls")


def test_two_contracts_on_one_date_is_flagged():
    df = _frame([100.0] * 40, ["ESU5"] * 20 + ["ESZ5"] * 20)
    rep = fdq.check_futures_frame("ES", df, time_col="t")
    assert "roll_overlap" in _codes(rep)


def test_a_contract_that_reappears_is_a_failure():
    """Revisiting an expired contract means the stitching is not chronological."""
    df = _frame([100.0] * 30, ["ESU5"] * 10 + ["ESZ5"] * 10 + ["ESU5"] * 10)
    rep = fdq.check_futures_frame("ES", df, time_col="t")
    assert rep.failed and "roll_backwards" in _codes(rep)


def test_an_impossible_move_inside_one_contract_is_a_failure():
    closes = [100.0] * 10 + [500.0] + [100.0] * 10
    rep = fdq.check_futures_frame("ES", _frame(closes), time_col="t")
    assert rep.failed and "impossible_move" in _codes(rep)


def test_a_roll_is_not_mistaken_for_an_impossible_move():
    """Comparing across a roll would flag every roll, which is how a check gets turned off."""
    closes = [100.0] * 20 + [300.0] * 20            # a 200% "move" that is just the roll
    rep = fdq.check_futures_frame("ES", _frame(closes, ["ESU5"] * 20 + ["ESZ5"] * 20),
                                  time_col="t")
    assert "impossible_move" not in _codes(rep)
    assert not rep.failed


def test_timestamps_going_backwards_are_a_failure():
    df = _frame([100.0] * 10)
    df.loc[5, "t"] = df.loc[0, "t"] - pd.Timedelta(days=1)
    rep = fdq.check_futures_frame("ES", df, time_col="t")
    assert rep.failed and "time_order" in _codes(rep)


# ======================================================================================
# THE STALE CHECK DISCRIMINATES
# ======================================================================================

def test_a_frozen_price_with_no_volume_is_information_not_a_warning():
    """What a closed exchange looks like. The real ES store's only run is Thanksgiving."""
    rep = fdq.check_futures_frame(
        "ES", _frame([100.0] * 200, volumes=[0.0] * 200), time_col="t")
    assert _sev(rep, "stale_quote") is Severity.INFO
    assert "not a feed fault" in next(f.detail for f in rep.findings
                                      if f.check == "stale_quote")


def test_a_frozen_price_with_real_volume_is_a_warning():
    """Trades printing at an unchanging price is what a stuck feed looks like."""
    rep = fdq.check_futures_frame(
        "ES", _frame([100.0] * 200, volumes=[50.0] * 200), time_col="t")
    assert _sev(rep, "stale_quote") is Severity.WARN
    assert "frozen price" in next(f.detail for f in rep.findings
                                  if f.check == "stale_quote")


def test_a_short_flat_stretch_is_not_reported_at_all():
    rep = fdq.check_futures_frame("ES", _frame([100.0] * 30), time_col="t")
    assert "stale_quote" not in _codes(rep)


def test_the_stale_threshold_is_configurable():
    df = _frame([100.0] * 50, volumes=[99.0] * 50)
    assert "stale_quote" not in _codes(fdq.check_futures_frame("ES", df, time_col="t"))
    assert "stale_quote" in _codes(
        fdq.check_futures_frame("ES", df, time_col="t", stale_bars=10))


# ======================================================================================
# QUOTES
# ======================================================================================

def test_a_store_without_quotes_says_the_spread_is_assumed():
    rep = fdq.check_futures_frame("ES", _frame([100.0] * 10), time_col="t")
    detail = next(f.detail for f in rep.findings if f.check == "quotes")
    assert "ASSUMED" in detail and "not measured" in detail


def test_a_crossed_book_is_a_failure():
    df = _frame([100.0] * 10, bid=[100.5] * 10, ask=[100.0] * 10)
    rep = fdq.check_futures_frame("ES", df, time_col="t")
    assert rep.failed and "crossed_book" in _codes(rep)


def test_a_non_positive_quote_is_a_failure():
    df = _frame([100.0] * 10, bid=[0.0] * 10, ask=[100.0] * 10)
    rep = fdq.check_futures_frame("ES", df, time_col="t")
    assert rep.failed and "quote_nonpositive" in _codes(rep)


def test_a_healthy_book_passes():
    df = _frame([100.0] * 10, bid=[99.75] * 10, ask=[100.25] * 10)
    rep = fdq.check_futures_frame("ES", df, time_col="t")
    assert not rep.failed
    assert "crossed_book" not in _codes(rep)


# ======================================================================================
# FAIL CLOSED
# ======================================================================================

def test_require_usable_raises_on_a_broken_store():
    df = _frame([100.0] * 30, ["ESU5"] * 10 + ["ESZ5"] * 10 + ["ESU5"] * 10)
    with pytest.raises(DataQualityError) as e:
        fdq.require_usable("ES", df, time_col="t")
    assert "not usable" in str(e.value)
    assert "roll_backwards" in str(e.value)


def test_require_usable_returns_the_report_on_a_good_store():
    rep = fdq.require_usable("ES", _frame([100.0] * 30), time_col="t")
    assert not rep.failed and rep.rows == 30


def test_a_warning_does_not_block():
    """A roll gap must be reported and must not stop research; only impossibilities fail."""
    df = _frame([100.0] * 20 + [110.0] * 20, ["ESU5"] * 20 + ["ESZ5"] * 20)
    rep = fdq.require_usable("ES", df, time_col="t")
    assert "roll_gap" in _codes(rep)


# ======================================================================================
# THE REAL STORE
# ======================================================================================

@pytest.mark.skipif(not __import__("pathlib").Path(STORE).exists(),
                    reason="no futures store on this machine")
def test_the_real_es_store_is_usable_and_its_findings_are_the_known_ones():
    """An integration check. Synthetic frames never have the shape real data has.

    The findings are pinned because they are known and explained: four rolls with a largest
    unadjusted gap under 1%, four overlap dates (the roll days the research path already
    excludes), one long flat run that is Thanksgiving night with six contracts of volume,
    and no quotes in the store at all.
    """
    rep = fdq.check_futures_frame("ES", pd.read_parquet(STORE), time_col="t")
    assert not rep.failed, rep.summary()
    codes = _codes(rep)
    assert {"rolls", "roll_overlap", "quotes"} <= codes
    assert "roll_backwards" not in codes
    assert "impossible_move" not in codes
    assert "time_order" not in codes
    assert _sev(rep, "stale_quote") is Severity.INFO, (
        "the only long flat run in this store is a holiday session, not a stuck feed")


@pytest.mark.skipif(not __import__("pathlib").Path(STORE).exists(),
                    reason="no futures store on this machine")
def test_the_real_store_roll_count_matches_its_contract_count():
    df = pd.read_parquet(STORE)
    rep = fdq.check_futures_frame("ES", df, time_col="t")
    rolls = next(f.count for f in rep.findings if f.check == "rolls")
    assert rolls == df["contract"].nunique() - 1, (
        "a stitched series should roll exactly once per contract transition")
