"""scripts/intraday_common.py: the cost model, split scaling, and the universe invariant.

The commission function is the one piece of code whose bugs are invisible in a backtest and
expensive live, because it is charged on every one of the sleeve's ~$5.5M/day of turnover.
A-5 part 2 fitted SEC and TAF rates against IBKR's own commissionReport on 2026-09-10 and
reproduced all five sells to the cent; these tests pin that model so a refactor cannot quietly
revert to the pre-2026-09-10 version that undercharged a round trip by ~0.21 bps of the sell leg.
"""
from __future__ import annotations

import datetime as dt

import intraday_common as ic
import pandas as pd
import pytest


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
    """A store with no table must cost exactly as it did before the table existed.

    (Not "the live store is unadjusted" - D-5 proved it is adjusted and wrote its table. What
    keeps this inert for the LIVE trader is that every store's most recent segment is 1.0 and
    live code only asks about today; see the A-16 block at the end of this file.)
    """
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


# ------------------------------------------------------ A-16: who applies share_scale, and who must not
#
# The trader has two executors and they are on opposite sides of this question, for a reason
# that is about DATA and not about preference:
#
#   SimExecutor  (--replay) fills off `data/minute`, whose prices are split-ADJUSTED (D-5). The
#                share count it derives from a dollar size is therefore the adjusted one, and a
#                per-share commission on it is wrong by the whole cumulative factor - 200x on
#                SOXS before its 2026-03-05 reverse split. It MUST divide by share_scale().
#   LiveExecutor fills off IBKR's raw tape at `commissionReport` prices. That share count is
#                already real. It MUST NOT divide by anything.
#
# A-16 is the day the first of those was made true. These tests are what stops a tidy-minded
# refactor from making both executors "consistent" and reintroducing the defect on one side or
# creating a new one on the other.

def _sim_fill(symbol, qty, price, day, splits, monkeypatch):
    """Drive the REAL SimExecutor through one fill and return the cost it books."""
    import intraday_trader as itr

    monkeypatch.setattr(ic, "_SPLITS", splits)
    ts = pd.Timestamp(f"{day} 10:00", tz=ic.ET)
    bars = {symbol: pd.DataFrame({"o": [price]}, index=[ts])}
    ex = itr.SimExecutor(bars)
    ex.submit({symbol: qty}, ts)
    fills = ex.settle(ts)
    assert len(fills) == 1
    return fills[0][3]


def test_replay_charges_the_real_share_count_on_an_adjusted_store(monkeypatch):
    """SOXS pre-2026-03-05: the store shows 1 share where 200 traded, so the per-share
    commission is 200x what the unscaled model charged. This is A-16's whole content."""
    splits = {"SOXS": [["2025-08-26", 0.005], ["2026-03-05", 0.1], ["2026-07-15", 1.0]]}
    got = _sim_fill("SOXS", 30, 1000.0, "2026-01-05", splits, monkeypatch)
    want = ic.commission(30, 1000.0, 0.005) + ic.slippage(30, 1000.0)
    assert got == pytest.approx(want)
    unscaled = ic.commission(30, 1000.0) + ic.slippage(30, 1000.0)
    assert got > unscaled * 5, "a revert to commission(q, px) would land here"


def test_replay_and_the_research_harness_now_price_a_fill_identically(monkeypatch):
    """The point of the fix is one convention, two implementations. `intraday_backtest.py`
    charges `commission(delta, px, share_scale(sym, day)) + slippage(delta, px)`; so must the
    replay, on every symbol and on both sides."""
    splits = {"SOXS": [["2025-08-26", 0.005], ["2026-03-05", 0.1], ["2026-07-15", 1.0]],
              "NFLX": [["2025-08-26", 10.0], ["2025-11-17", 1.0]],
              "NVDA": [["2025-08-26", 1.0]]}
    for sym, qty, px, day in (("SOXS", 30, 1000.0, "2026-01-05"), ("SOXS", -30, 1000.0, "2026-01-05"),
                              ("SOXS", 12, 95.0, "2026-04-01"), ("NFLX", -140, 85.0, "2025-09-15"),
                              ("NFLX", 14, 850.0, "2026-01-05"), ("NVDA", -55, 180.0, "2026-01-05")):
        got = _sim_fill(sym, qty, px, day, splits, monkeypatch)
        want = (ic.commission(qty, px, ic.share_scale(sym, day))
                + ic.slippage(qty, px))
        assert got == pytest.approx(want), f"{sym} {qty} @ {px} on {day}"


def test_a_store_on_the_current_basis_is_untouched_by_the_fix(monkeypatch):
    """Every store's most recent segment is 1.0 by construction, and that - not the absence of
    a table - is why the deployed 09:25 replay is byte-identical before and after A-16."""
    splits = {"SOXS": [["2025-08-26", 0.005], ["2026-07-15", 1.0]]}
    got = _sim_fill("SOXS", 30, 5.0, "2026-09-11", splits, monkeypatch)
    assert got == pytest.approx(ic.commission(30, 5.0) + ic.slippage(30, 5.0))


def test_the_live_executor_must_never_scale_its_commission():
    """AST, not behaviour: `LiveExecutor` needs a live `ib` connection, and the property under
    test is a property of the SOURCE - which executor passes a third argument to commission().
    Live fills come from IBKR's own report at raw prices; scaling them would undercharge the
    real book by the same factor the replay was undercharging by."""
    import ast
    import inspect

    import intraday_trader as itr

    tree = ast.parse(inspect.getsource(itr))
    nargs = {}
    for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
        for fn in (n for n in ast.walk(cls) if isinstance(n, ast.FunctionDef)):
            for call in (n for n in ast.walk(fn) if isinstance(n, ast.Call)):
                if isinstance(call.func, ast.Name) and call.func.id == "commission":
                    nargs.setdefault(cls.name, set()).add(len(call.args))
    assert nargs["SimExecutor"] == {3}, "the replay executor must pass share_scale"
    assert nargs["LiveExecutor"] == {2}, "the live executor must not scale a raw-tape fill"
