"""scripts/intraday_common.py: the cost model, split scaling, and the universe invariant.

The commission function is the one piece of code whose bugs are invisible in a backtest and
expensive live, because it is charged on every one of the sleeve's ~$5.5M/day of turnover.
A-5 part 2 fitted SEC and TAF rates against IBKR's own commissionReport on 2026-09-10 and
reproduced all five sells to the cent; these tests pin that model so a refactor cannot quietly
revert to the pre-2026-09-10 version that undercharged a round trip by ~0.21 bps of the sell leg.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

import intraday_common as ic


# --------------------------------------------------------------------------- commission
def test_buy_pays_commission_only():
    assert ic.commission(100, 100.0) == pytest.approx(1.0)      # $0.005 * 100 = $0.50, floored at $1


def test_sell_pays_sec_and_taf_on_top():
    expected = 1.0 + 100 * 100.0 * ic.SEC_FEE_RATE + 100 * ic.TAF_PER_SHARE
    assert ic.commission(-100, 100.0) == pytest.approx(expected)
    assert ic.commission(-100, 100.0) > ic.commission(100, 100.0)


def test_sign_is_load_bearing():
    """Passing abs(shares) reverts to the model that undercharged every sale. If this ever
    passes, someone dropped the sign at a call site and the backtest got quietly cheaper."""
    assert ic.commission(-1000, 50.0) != pytest.approx(ic.commission(1000, 50.0))


def test_dollar_minimum_binds_on_a_small_order():
    assert ic.commission(50, 20.0) == pytest.approx(ic.COMMISSION_MIN)


def test_one_percent_cap_binds_on_a_cheap_stock():
    """100 shares at $0.50: per-share floor says $1.00, but 1% of the $50 notional is $0.50."""
    assert ic.commission(100, 0.50) == pytest.approx(0.50)


def test_taf_is_capped_per_order():
    shares, price = 1_000_000, 1.0
    c = ic.commission(-shares, price)
    per_share = min(max(ic.COMMISSION_MIN, shares * ic.COMMISSION_PER_SHARE), 0.01 * shares * price)
    assert c == pytest.approx(per_share + shares * price * ic.SEC_FEE_RATE + ic.TAF_CAP)
    assert ic.TAF_CAP == 8.30


def test_share_scale_makes_a_split_adjusted_store_charge_the_real_share_count():
    """data/minute_alpaca prices a 2016 NVDA share at ~1/40th, so dollar sizing buys ~40x the
    shares really bought and a per-SHARE commission reads 40x too high. `scale` fixes the
    per-share term while leaving the notional-based SEC fee alone."""
    unscaled = ic.commission(-100, 100.0)                  # 100 real shares at $100
    scaled = ic.commission(-400, 25.0, scale=4.0)          # same $10k, store shows 4x the shares
    assert scaled == pytest.approx(unscaled)


def test_share_scale_defaults_to_one_and_survives_a_zero():
    assert ic.commission(100, 100.0, scale=1.0) == ic.commission(100, 100.0)
    assert ic.commission(100, 100.0, scale=0.0) == ic.commission(100, 100.0)


def test_slippage_is_flat_basis_points_of_notional_both_ways():
    assert ic.slippage(100, 100.0) == pytest.approx(100 * 100.0 * ic.SLIPPAGE_BPS / 1e4)
    assert ic.slippage(-100, 100.0) == ic.slippage(100, 100.0)
    assert ic.SLIPPAGE_BPS == 1.5


def test_round_trip_cost_in_basis_points_is_where_research_thinks_it_is():
    """A $100k round trip on a $100 stock: ~3.0 bps of slippage plus commission and fees.
    If a change moves this, every turnover-vs-edge conclusion in the ledger moves with it."""
    notional = 100_000.0
    shares = 1000
    total = (ic.commission(shares, 100.0) + ic.slippage(shares, 100.0)
             + ic.commission(-shares, 100.0) + ic.slippage(-shares, 100.0))
    assert total / notional * 1e4 == pytest.approx(4.23, abs=0.02)   # 3.00 slippage + 1.23 fees


# --------------------------------------------------------------------------- split factors
def test_share_scale_is_one_when_the_store_has_no_split_file(monkeypatch):
    """The live IBKR store is unadjusted, so this must be a no-op for the live trader."""
    monkeypatch.setattr(ic, "_SPLITS", {})
    assert ic.share_scale("NVDA", "2016-01-04") == 1.0


def test_share_scale_steps_at_each_split_date(monkeypatch):
    monkeypatch.setattr(ic, "_SPLITS", {"NVDA": [["2016-01-04", 40.0], ["2021-07-20", 10.0], ["2024-06-10", 1.0]]})
    assert ic.share_scale("nvda", "2016-06-01") == 40.0    # case-insensitive
    assert ic.share_scale("NVDA", "2021-07-20") == 10.0    # inclusive on the date itself
    assert ic.share_scale("NVDA", "2021-07-19") == 40.0
    assert ic.share_scale("NVDA", "2026-01-01") == 1.0
    assert ic.share_scale("NVDA", "2010-01-01") == 40.0    # before the first segment: earliest factor
    assert ic.share_scale("AAPL", "2026-01-01") == 1.0     # unknown symbol


# --------------------------------------------------------------------------- causal volume cap
def test_volume_limits_never_see_their_own_session():
    """A participation cap built on today's own volume is look-ahead. The denominator for day D
    must be the median of sessions strictly before D."""
    idx, vols = [], []
    for i, day in enumerate(pd.date_range("2026-01-05", periods=8, freq="B")):
        for minute in (0, 1):
            idx.append(pd.Timestamp(day) + pd.Timedelta(hours=9, minutes=30 + minute))
            vols.append(100.0 * (i + 1) + minute)
    df = pd.DataFrame({"v": vols}, index=pd.DatetimeIndex(idx))
    lim = ic.volume_limits(df, lookback=20, min_sessions=5)

    days = sorted({d.date() for d in df.index})
    assert lim.loc[days[:5], 0].isna().all(), "fewer than min_sessions of history means no cap"
    # Day index 5 (the 6th session) sees sessions 0..4 -> volumes 100..500 -> median 300.
    assert lim.loc[days[5], 0] == pytest.approx(300.0)
    assert lim.loc[days[5], 1] == pytest.approx(301.0)
    # And never its own 600.
    assert lim.loc[days[5], 0] < 600.0


def test_volume_limits_on_an_empty_frame_is_empty_not_an_error():
    assert ic.volume_limits(pd.DataFrame(columns=["v"])).empty


# --------------------------------------------------------------------------- sleeve invariants
def test_the_two_sleeves_never_share_a_symbol():
    """The whole safety argument for two runners on one account is that each can flatten its own
    book without touching the other's. That holds only while the universes are disjoint."""
    assert not set(ic.UNIVERSE) & ic.DAILY_SLEEVE_UNIVERSE
    assert len(set(ic.UNIVERSE)) == len(ic.UNIVERSE), "a duplicate would double a name's cap"


def test_only_the_deployable_leveraged_names_are_offered_to_this_sleeve():
    assert set(ic.LEVERAGED_DEPLOYABLE) <= set(ic.LEVERAGED_UNIVERSE)
    assert not set(ic.LEVERAGED_DEPLOYABLE) & ic.DAILY_SLEEVE_UNIVERSE


def test_session_bounds_match_the_bar_stamping_convention():
    """Bars are stamped at their START, so 15:59 is the last regular bar and 16:00 is excluded."""
    assert (ic.SESSION_OPEN, ic.SESSION_CLOSE) == (dt.time(9, 30), dt.time(16, 0))
