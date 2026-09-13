"""D-7 / AUD-17: the LEAN daily store's share basis and what LEAN charges on it.

Not `runner`-marked: nothing here is executed by the 09:25 intraday launch, and a failure
must not stop the sleeve. These guard three things that a future data change could silently
break, in descending order of how expensive being wrong is:

1. The fee replica. Every dollar column in `sweep_d7` rests on `lean_ib_fee` being a faithful
   transcription of `InteractiveBrokersFeeModel.cs:161-172`, including the if/ELSE-if that
   exempts the $1 minimum from the 0.5% cap. Pinned against the champion's own recorded fees.
2. The adjustment arithmetic. `adjusted = raw / cum` and `q_adjusted = cum * q_raw`, with the
   factor file read LEAN's way (first row whose date >= the bar date). Get the direction wrong
   and a "correction" doubles the error instead of removing it - D-5's clause 2 in test form.
3. The premise itself. Every factor file this repo writes carries `split_factor == 1`. If that
   ever stops being true, `sweep_d7`'s verdict is stale and the sidecar must be re-derived.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

sweep_d7 = pytest.importorskip("sweep_d7")

lean_ib_fee = sweep_d7.lean_ib_fee
cum_series = sweep_d7.cum_series


# --------------------------------------------------------------- the fee replica

def test_fee_is_half_a_cent_per_share_in_the_ordinary_case():
    # 10,000 shares at $50: 0.005 * 10_000 = $50, and 0.5% of $500k is $2,500, so neither
    # the floor nor the cap binds.
    assert lean_ib_fee(10_000, 50.0) == pytest.approx(50.0)


def test_one_dollar_minimum_binds_below_two_hundred_shares():
    assert lean_ib_fee(100, 50.0) == pytest.approx(1.0)
    assert lean_ib_fee(199, 50.0) == pytest.approx(1.0)
    assert lean_ib_fee(201, 50.0) == pytest.approx(1.005)


def test_the_minimum_is_not_subject_to_the_half_percent_cap():
    """LEAN's `if (fee < min) ... else if (fee > cap)` is not a clamp, and the difference is
    the whole of D-7 clause 6: a near-zero ADJUSTED share count does not pay a near-zero fee,
    it pays the floor. One share at $1 is a $1 trade whose 0.5% cap is half a cent - and LEAN
    charges $1, two hundred times the cap."""
    assert lean_ib_fee(1, 1.0) == pytest.approx(1.0)
    assert lean_ib_fee(1, 1.0) > 0.005 * 1.0


def test_half_percent_cap_binds_on_sub_dollar_prices():
    # 100,000 shares at $0.05: per-share would be $500, the cap is 0.5% of $5,000 = $25.
    assert lean_ib_fee(100_000, 0.05) == pytest.approx(25.0)


def test_fee_is_sign_agnostic():
    assert lean_ib_fee(-10_000, 50.0) == pytest.approx(lean_ib_fee(10_000, 50.0))


def test_replica_reproduces_every_champion_fill_to_the_cent():
    """The strongest available check: 5,128 fees LEAN itself computed, none of them ours."""
    fills, _ = sweep_d7.champion_fills()
    assert len(fills) > 1_000
    worst = max(abs(lean_ib_fee(e["fillQuantity"], e["fillPrice"])
                    - float(e.get("orderFeeAmount", 0.0))) for e in fills)
    assert worst < 1e-9


# --------------------------------------------------------------- adjustment arithmetic

def test_forward_split_inflates_the_adjusted_share_count():
    """A 10:1 forward split: bars before the ex-date carry cum = 10, so the adjusted price is
    a tenth of the raw one and a fixed dollar order buys ten times as many shares as it really
    did - which is why the per-share fee is OVERstated for forward-split names."""
    idx = pd.DatetimeIndex(["2024-06-07", "2024-06-10", "2024-06-11"])
    cum = cum_series(idx, [("2024-06-10", 10.0)])
    assert list(cum) == [10.0, 1.0, 1.0]
    raw_price = 1_200.0
    assert raw_price / cum.iloc[0] == pytest.approx(120.0)


def test_reverse_split_deflates_it_and_that_is_the_direction_aud17_names():
    """A 1:20 reverse split is ratio 0.05: the adjusted price is 20x the raw one, a fixed
    dollar order buys a twentieth of the real share count, and the fee is UNDERstated 20x."""
    idx = pd.DatetimeIndex(["2026-03-04", "2026-03-05"])
    cum = cum_series(idx, [("2026-03-05", 0.05)])
    assert cum.iloc[0] == pytest.approx(0.05)
    assert 1.45 / cum.iloc[0] == pytest.approx(29.0)


def test_cumulative_factor_compounds_over_several_splits():
    idx = pd.DatetimeIndex(["2019-01-01", "2021-01-01", "2025-01-01"])
    cum = cum_series(idx, [("2020-01-01", 4.0), ("2024-01-01", 10.0)])
    assert list(cum) == [40.0, 10.0, 1.0]


def test_price_factor_lookup_takes_the_first_row_at_or_after_the_bar_date():
    """LEAN's convention, documented in fetch_data.py:141-152. Off by one row and every
    dividend-era fee column in sweep_d7 shifts."""
    rows = sweep_d7.load_factor_rows("gld")
    assert rows, "no factor file for GLD"
    assert rows[-1][0] == pd.Timestamp("2050-12-31"), "sentinel row missing"
    idx = pd.DatetimeIndex([rows[0][0], rows[-1][0]])
    got = sweep_d7.price_factor_series("gld", idx)
    assert got.iloc[0] == pytest.approx(rows[0][1] * rows[0][2])
    assert got.iloc[-1] == pytest.approx(1.0)


def test_gld_pays_no_dividend_and_never_split_so_its_fee_correction_is_exactly_zero():
    """The control in clause 5's table: the one champion symbol whose adjusted price IS its
    raw price. If this ever moves, the correction is picking up something that is not an
    adjustment."""
    rows = sweep_d7.load_factor_rows("gld")
    assert all(pf == 1.0 and sf == 1.0 for _, pf, sf in rows)


# --------------------------------------------------------------- the premise

def test_every_factor_file_this_repo_writes_still_claims_split_factor_one():
    """Clause 1. If this fails the store has been migrated and sweep_d7's verdict is stale."""
    result = sweep_d7.clause1_premise_a(sweep_d7.universe())
    assert result["files"] == 69
    assert result["missing"] == 0
    assert result["rows"] > 1_000
    assert result["offending_rows"] == 0, (
        f"split_factor != 1 now appears for {result['offending_symbols']}; "
        "re-run scripts/sweep_d7.py --net and revisit D-7")


def _sidecar() -> dict:
    """`data/` is gitignored, so on a fresh clone the sidecar is absent rather than wrong."""
    path = sweep_d7.SPLITS_PATH
    if not path.exists():
        pytest.skip(f"{path} absent; regenerate with `scripts/sweep_d7.py --net --write`")
    return json.loads(path.read_text())


def test_the_split_sidecar_is_present_and_well_formed():
    table = _sidecar()
    assert len(table) >= 50
    for sym, events in table.items():
        assert events, f"{sym} has an empty split list; it should have been omitted"
        for date, ratio in events:
            pd.Timestamp(date)
            assert ratio > 0, f"{sym} {date} ratio {ratio} is not positive"


@pytest.mark.parametrize("symbol,expected", [("NVDA", 480.0), ("AAPL", 112.0), ("AMZN", 240.0)])
def test_known_cumulative_factors(symbol, expected):
    """Three splits everyone can check by hand: NVDA 2x2x2x1.5x4x10, AAPL 2x2x7x4,
    AMZN 2x2x3x20 -> 240 over the store's 1998 start."""
    table = _sidecar()
    idx = pd.DatetimeIndex(["1998-01-02"])
    cum = cum_series(idx, [(d, float(r)) for d, r in table[symbol]])
    assert cum.iloc[0] == pytest.approx(expected, rel=1e-9)
