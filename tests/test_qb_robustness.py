"""Tests for regime labelling and concentration metrics.

Three properties carry most of the weight here.

A REGIME LABEL MUST NOT READ THE FUTURE. The two leaks that matter are tested with working
reproductions rather than described: the whole-sample `pd.qcut`, which every notebook writes,
and a leak confined to a warm-up window, which is the shape `features._opening_range_pos`
had. The second one is why `assert_causal_labels` sweeps early probe points instead of
testing one late index, and the test proves the late probe misses it.

CONCENTRATION MUST BE READABLE ON DEGENERATE INPUT. Every share has a denominator that can be
zero or negative, and a metric that returns a plausible-looking number on a losing sample is
worse than one that returns NaN. The all-losers, one-winner and perfectly-even samples are all
exercised for that reason.

AND THE ARITHMETIC MUST ADD UP. Intraday attribution summing to the session's own P&L, and
regime shares summing to one, are the invariants that catch an attribution assigning money to
a bucket it did not come from.
"""
from __future__ import annotations

import datetime as dt
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_brain.markets.futures_cme.twin import TwinDay
from quant_brain.research import robustness as rb

REPO = Path(__file__).resolve().parents[1]
ES_STORE = REPO / "data" / "futures" / "ES.parquet"


# ======================================================================================
# FIXTURES
# ======================================================================================

def _bars(closes, *, start: str = "2025-06-09 18:00", tz: str = "America/New_York",
          volumes=None) -> pd.DataFrame:
    """A minute frame in the store's shape: UTC `t`, OHLCV."""
    n = len(closes)
    idx = pd.date_range(pd.Timestamp(start, tz=tz), periods=n, freq="1min")
    c = np.asarray(closes, dtype=float)
    return pd.DataFrame({
        "t": idx.tz_convert("UTC"),
        "o": c, "h": c, "l": c, "c": c,
        "v": np.asarray(volumes, dtype=float) if volumes is not None else np.ones(n),
    })


def _table(n: int = 260, seed: int = 0) -> pd.DataFrame:
    """A session table of the shape `session_table` emits, without the parquet."""
    rng = np.random.default_rng(seed)
    idx = pd.Index([dt.date(2025, 1, 1) + dt.timedelta(days=i) for i in range(n)],
                   name="session", dtype=object)
    return pd.DataFrame({
        "bars": np.full(n, 1380),
        "ret": rng.normal(0.0, 0.008, n),
        "rvol": np.abs(rng.normal(3e-4, 1e-4, n)),
        "volume": rng.lognormal(12.0, 0.4, n),
        "range_frac": np.abs(rng.normal(0.011, 0.004, n)),
        "efficiency": np.abs(rng.normal(0.033, 0.02, n)),
        "trend_strength": np.abs(rng.normal(1.2, 0.6, n)),
    }, index=idx)


def _days(pnl, *, start=dt.date(2026, 1, 5), path=True) -> list[TwinDay]:
    out, day = [], start
    for x in pnl:
        while day.weekday() >= 5:
            day += dt.timedelta(days=1)
        marks = tuple(np.linspace(float(x) / 390.0, float(x), 390)) if path else ()
        out.append(TwinDay(day=day, pnl=float(x), path=marks))
        day += dt.timedelta(days=1)
    return out


def _walks(n_sessions: int, bars_per: int, rng, start: dt.date) -> pd.DataFrame:
    """`n_sessions` independent random walks, one per trade date, in one frame."""
    frames, day = [], start
    for _ in range(n_sessions):
        steps = rng.normal(0.0, 0.001, bars_per)
        frames.append(_bars(100.0 * np.exp(np.cumsum(steps)),
                            start=f"{day.isoformat()} 18:00"))
        day += dt.timedelta(days=1)
    return pd.concat(frames, ignore_index=True)


@pytest.fixture
def table() -> pd.DataFrame:
    return _table()


# ======================================================================================
# SESSION TABLE
# ======================================================================================

def test_a_globex_session_is_ordered_by_timestamp_not_by_clock_minute():
    """The bug this caught on the real ES store, kept as a test.

    A CME trade date runs 18:00 to 17:00, so sorting its bars by minute-of-day puts midnight
    first and the previous evening last. Measured on the real ES store with the buggy sort:
    mean |session return| 9.0e-5 against the correct 6.0e-3, and mean efficiency 4.6e-4
    against 3.3e-2. Two orders of magnitude, and nothing raised.
    """
    closes = np.linspace(100.0, 110.0, 1380)          # 18:00 -> 16:59, one way up
    out = rb.session_table(_bars(closes))
    assert len(out) == 1
    assert out["ret"].iloc[0] == pytest.approx(0.10, rel=1e-6)
    assert out["efficiency"].iloc[0] == pytest.approx(1.0, rel=1e-6)


def test_the_trade_date_rolls_at_18_00():
    out = rb.session_table(_bars(np.full(120, 100.0), start="2025-06-09 17:30"))
    # 17:30-17:59 belongs to the 9th; 18:00 onward is already the 10th's session.
    assert list(out.index) == [dt.date(2025, 6, 9), dt.date(2025, 6, 10)]
    assert out["bars"].tolist() == [30, 90]


def test_rollover_none_uses_the_calendar_date():
    out = rb.session_table(_bars(np.full(120, 100.0), start="2025-06-09 17:30"),
                           rollover=None, buckets=rb.DEFAULT_BUCKETS)
    assert list(out.index) == [dt.date(2025, 6, 9)]


def test_a_timezone_naive_timestamp_column_is_refused():
    frame = _bars(np.full(10, 100.0))
    frame["t"] = frame["t"].dt.tz_localize(None)
    with pytest.raises(ValueError, match="timezone-naive"):
        rb.session_table(frame)


def test_a_missing_time_column_is_named_rather_than_guessed():
    with pytest.raises(ValueError, match="needs a 't' column"):
        rb.session_table(_bars(np.full(10, 100.0)).drop(columns=["t"]))


def test_realised_volatility_does_not_straddle_the_session_boundary():
    """A diff across an overnight gap is a gap, not a bar return.

    Two identical sessions separated by a 10% jump. If the boundary leaked, the second
    session's realised volatility would be dominated by the gap and differ from the first's.
    """
    rng = np.random.default_rng(5)
    walk = 100.0 * np.exp(np.cumsum(rng.normal(0, 1e-4, 1380)))
    frame = pd.concat([_bars(walk, start="2025-06-09 18:00"),
                       _bars(walk * 1.10, start="2025-06-10 18:00")], ignore_index=True)
    out = rb.session_table(frame)
    assert len(out) == 2
    assert out["rvol"].iloc[0] == pytest.approx(out["rvol"].iloc[1], rel=1e-9)


def test_efficiency_separates_a_one_way_session_from_a_round_trip():
    one_way = rb.session_table(_bars(np.linspace(100.0, 101.0, 1380)))
    there_and_back = rb.session_table(_bars(
        np.r_[np.linspace(100.0, 101.0, 690), np.linspace(101.0, 100.0, 690)]))
    assert one_way["efficiency"].iloc[0] == pytest.approx(1.0, rel=1e-6)
    assert there_and_back["efficiency"].iloc[0] < 1e-9


def test_trend_strength_is_the_efficiency_ratio_with_the_length_divided_out():
    out = rb.session_table(_bars(np.linspace(100.0, 101.0, 1380)))
    assert out["trend_strength"].iloc[0] == pytest.approx(
        out["efficiency"].iloc[0] * math.sqrt(1380))


def test_trend_strength_removes_the_bar_count_dependence():
    """The raw Kaufman ratio falls as 1/sqrt(bars), so a half-day would read as trending.

    Both sets of sessions are random walks with the same per-bar volatility; only the length
    differs. `efficiency` must differ by roughly sqrt(2) - a pure artefact of the bar count -
    and `trend_strength` must not.
    """
    rng = np.random.default_rng(11)
    long_ = rb.session_table(_walks(120, 1380, rng, dt.date(2025, 1, 6)))
    short = rb.session_table(_walks(120, 690, rng, dt.date(2026, 1, 6)))
    raw_gap = short["efficiency"].mean() / long_["efficiency"].mean()
    fixed_gap = short["trend_strength"].mean() / long_["trend_strength"].mean()
    assert raw_gap > 1.2                            # the length artefact is real
    assert abs(fixed_gap - 1.0) < abs(raw_gap - 1.0)


def test_coverage_reports_a_store_that_cannot_distinguish_overnight_from_rth():
    """An RTH-only store must say so rather than have an overnight computed for it."""
    out = rb.session_table(_bars(np.full(390, 100.0), start="2025-06-10 09:30"))
    assert rb.coverage(out, "overnight") == 0.0
    assert rb.coverage(out, "open") == 1.0
    assert rb.coverage(out, "midday") == 1.0


def test_bucket_statistics_are_computed_only_from_that_bucket():
    closes = np.full(1380, 100.0)
    closes[930:990] = 105.0                          # 09:30-10:29 only, the open bucket
    out = rb.session_table(_bars(closes)).iloc[0]
    assert out["open_ret"] == pytest.approx(0.0)     # flat at 105 within the bucket
    assert out["open_range_frac"] == pytest.approx(0.0)
    assert out["midday_range_frac"] == pytest.approx(0.0)
    assert out["range_frac"] == pytest.approx(0.05, rel=1e-6)


def test_a_duplicate_bucket_name_is_refused():
    dupes = (rb.Bucket("open", dt.time(9, 30), dt.time(10, 0)),
             rb.Bucket("open", dt.time(10, 0), dt.time(11, 0)))
    with pytest.raises(ValueError, match="duplicate bucket"):
        rb.session_table(_bars(np.full(60, 100.0)), buckets=dupes)


# ======================================================================================
# REGIME LABELS - CAUSALITY IS THE POINT
# ======================================================================================

def test_the_standard_labellers_are_causal(table):
    assert rb.audit_label_causality(rb.labellers(), table) == {}


def test_labels_are_unchanged_by_appending_future_sessions(table):
    """Prefix invariance: an independent check on the same property.

    The perturbation test asks "does changing the future move the past?". This asks "does
    the past exist before the future does?". A rolling window with the wrong `min_periods`
    can pass one and fail the other.
    """
    for lab in rb.labellers():
        full = list(lab.label(table))
        head = list(lab.label(table.iloc[:150]))
        assert full[:150] == head


def test_a_whole_sample_qcut_labeller_is_caught(table):
    """The one line everybody writes. Its cut points are a statistic of the whole sample."""
    def qcut_by_hand(t: pd.DataFrame) -> pd.Series:
        # What `pd.qcut(t["rvol"], 3)` computes, written out: the cut points are a statistic
        # of the WHOLE column, so January is labelled using December's volatility.
        x = np.asarray(t["rvol"], dtype=float)
        lo, hi = np.quantile(x, [1 / 3, 2 / 3])
        return pd.Series(np.where(x <= lo, "low", np.where(x <= hi, "mid", "high")),
                         index=t.index, dtype=object)

    leaky = rb.RegimeLabeller("qcut_vol", "volatility", qcut_by_hand, ("rvol",), 0,
                              "the textbook lookahead")
    with pytest.raises(AssertionError, match="not causal"):
        rb.assert_causal_labels(leaky, table)


def test_a_leak_confined_to_the_warmup_survives_a_single_late_probe(table):
    """The `opening_range_pos` shape, reproduced.

    The first forty sessions are labelled from the median of those same forty - so a
    perturbation late in the sample cannot reveal it, and a single probe at 80% through
    passes a labeller that is reading its own future. Only the early sweep points catch it,
    which is exactly why `assert_causal_labels` has them.
    """
    def leaky(t: pd.DataFrame) -> pd.Series:
        base = rb._binary(t, "rvol", short=5, long=60, high="high_vol", low="low_vol")
        out = np.array(base, dtype=object)
        k = min(40, len(t))
        x = t["rvol"].astype(float).to_numpy()[:k]
        out[:k] = np.where(x > np.median(x), "high_vol", "low_vol")
        return pd.Series(out, index=t.index, dtype=object)

    lab = rb.RegimeLabeller("opening_leak", "volatility", leaky, ("rvol",), 65, "")
    # The probe the original `assert_causal` used, and it passes.
    rb.assert_causal_labels(lab, table, at=int(len(table) * 0.8))
    with pytest.raises(AssertionError, match="session [0-9]+"):
        rb.assert_causal_labels(lab, table)


def test_the_causality_sweep_refuses_a_table_too_short_to_probe():
    with pytest.raises(ValueError, match="too short"):
        rb.assert_causal_labels(rb.labellers()[0], _table(2))


def test_warmup_sessions_are_labelled_rather_than_dropped(table):
    labels = rb.label_table(table)
    for lab in rb.labellers():
        col = labels[lab.name]
        assert len(col) == len(table)
        assert (col == rb.WARMUP).sum() == lab.warmup - 1
        assert col.iloc[0] == rb.WARMUP
        assert col.iloc[-1] != rb.WARMUP


def test_label_table_refuses_a_table_it_cannot_support(table):
    thin = table.drop(columns=["volume", "trend_strength"])
    with pytest.raises(ValueError, match="cannot support 2 labeller"):
        rb.label_table(thin)
    kept = rb.label_table(thin, strict=False)
    assert set(kept.columns) == {"vol_regime", "vol_tercile"}


def test_a_labeller_names_the_column_it_wanted(table):
    lab = rb.labellers()[0]
    with pytest.raises(ValueError, match="needs \\('rvol',\\)"):
        lab.label(table.drop(columns=["rvol"]))


def test_terciles_split_the_sample_into_three_roughly_even_parts(table):
    counts = rb.label_table(table)["vol_tercile"].value_counts()
    live = {k: v for k, v in counts.items() if k != rb.WARMUP}
    assert set(live) == {"vol_low", "vol_mid", "vol_high"}
    assert min(live.values()) > 0.5 * max(live.values())


# ======================================================================================
# PERFORMANCE PER REGIME
# ======================================================================================

def test_regime_shares_sum_to_one_and_sessions_account_for_the_sample(table):
    rng = np.random.default_rng(2)
    pnl = rng.normal(60.0, 300.0, len(table))
    labels = rb.label_table(table)["vol_regime"]
    rows = rb.regime_performance(pnl, labels)
    assert sum(r.sessions_share for r in rows) == pytest.approx(1.0)
    assert sum(r.share_of_net for r in rows) == pytest.approx(1.0)
    assert sum(r.n for r in rows) == int((labels != rb.WARMUP).sum())


def test_carry_identifies_the_regime_that_holds_the_strategy_up():
    labels = ["high_vol"] * 20 + ["low_vol"] * 180
    pnl = [500.0] * 20 + [0.0] * 180
    rows = rb.regime_performance(pnl, labels)
    top = rb.carried_by(rows)
    assert top is not None
    assert top.regime == "high_vol"
    assert top.share_of_net == pytest.approx(1.0)
    assert top.carry == pytest.approx(10.0)          # 10% of sessions, 100% of the profit


def test_a_fair_regime_carries_one():
    labels = ["a"] * 100 + ["b"] * 100
    rows = rb.regime_performance([10.0] * 200, labels)
    assert all(r.carry == pytest.approx(1.0) for r in rows)


def test_warmup_sessions_are_excluded_from_regime_performance_by_default():
    labels = [rb.WARMUP] * 50 + ["a"] * 50
    pnl = [1000.0] * 50 + [1.0] * 50
    assert [r.regime for r in rb.regime_performance(pnl, labels)] == ["a"]
    kept = rb.regime_performance(pnl, labels, drop_warmup=False)
    assert {r.regime for r in kept} == {rb.WARMUP, "a"}


def test_misaligned_labels_are_refused_rather_than_zipped_short():
    with pytest.raises(ValueError, match="aligning"):
        rb.regime_performance([1.0, 2.0, 3.0], ["a", "b"])


def test_align_sessions_drops_days_the_table_does_not_cover(table):
    days = _days(np.ones(400), start=dt.date(2025, 1, 1))
    pnl, aligned = rb.align_sessions(days, table)
    assert len(pnl) == len(aligned)
    assert len(aligned) < len(days)
    assert set(aligned.index) <= set(table.index)


def test_align_sessions_says_so_when_nothing_matches(table):
    days = _days([1.0, 2.0], start=dt.date(2030, 1, 1))
    with pytest.raises(ValueError, match="trade-date convention"):
        rb.align_sessions(days, table)


# ======================================================================================
# INTRADAY ATTRIBUTION
# ======================================================================================

def test_bucket_spans_tile_the_declared_session():
    spans = rb.bucket_spans(rb.GLOBEX_BUCKETS, session_start=rb.GLOBEX_ROLLOVER,
                            session_end=dt.time(17, 0))
    assert [n for n, _, _ in spans] == ["overnight", "open", "midday", "close", "post"]
    assert spans[0][1] == 0.0
    assert spans[-1][2] == pytest.approx(1.0)
    for (_, _, end), (_, start, _) in zip(spans[:-1], spans[1:], strict=True):
        assert end == pytest.approx(start)


def test_a_bucket_outside_the_declared_session_is_refused():
    outside = (rb.Bucket("premarket", dt.time(4, 0), dt.time(9, 0)),)
    with pytest.raises(ValueError, match="does not lie inside"):
        rb.bucket_spans(outside, session_start=rb.RTH_OPEN, session_end=rb.RTH_CLOSE)


def test_attribution_sums_to_the_strategy_total():
    rng = np.random.default_rng(7)
    pnl = rng.normal(50, 400, 40)
    days = _days(pnl)
    out = rb.intraday_attribution(days)
    assert sum(out.values()) == pytest.approx(float(np.sum(pnl)), rel=1e-9)


def test_attribution_puts_the_money_in_the_bucket_that_made_it():
    """Flat until 15:00, then +100. Only the close bucket may be credited."""
    flat_then_up = tuple(np.r_[np.zeros(330), np.linspace(100.0 / 60, 100.0, 60)])
    day = TwinDay(day=dt.date(2026, 1, 5), pnl=100.0, path=flat_then_up)
    out = rb.intraday_attribution([day])
    assert out["open"] == pytest.approx(0.0)
    assert out["midday"] == pytest.approx(0.0)
    assert out["close"] == pytest.approx(100.0)


def test_attribution_refuses_a_session_with_no_path():
    day = TwinDay(day=dt.date(2026, 1, 5), pnl=100.0)
    with pytest.raises(ValueError, match="no intraday path"):
        rb.intraday_attribution([day])


def test_attribution_refuses_a_path_too_coarse_for_the_buckets():
    """`u_shaped_path` is a three-point caricature; it cannot be split five ways."""
    day = TwinDay(day=dt.date(2026, 1, 5), pnl=100.0, path=(-70.0, -140.0, 100.0))
    with pytest.raises(ValueError, match="buckets were requested"):
        rb.intraday_attribution([day], buckets=rb.GLOBEX_BUCKETS,
                                session_start=rb.GLOBEX_ROLLOVER,
                                session_end=dt.time(17, 0))


def test_a_path_that_does_not_end_at_the_close_is_completed():
    """The final mark is the session's realised P&L whether or not the path says so."""
    day = TwinDay(day=dt.date(2026, 1, 5), pnl=10.0,
                  path=tuple(np.linspace(1.0, 5.0, 390)))
    out = rb.intraday_attribution([day])
    assert sum(out.values()) == pytest.approx(10.0)


# ======================================================================================
# CONCENTRATION
# ======================================================================================

def test_one_lucky_day_reads_as_one_lucky_day():
    pnl = [-1.0] * 99 + [1000.0]
    rep = rb.concentration(pnl)
    assert rep.effective_sessions == pytest.approx(1.0)
    assert rep.days_to_zero == 1
    assert rep.best_day_share_gross == pytest.approx(1.0)
    assert rep.best_day_share > 1.0                  # the rest of the sample loses money
    assert rep.without_best[1] == pytest.approx(-99.0)


def test_a_perfectly_even_series_reads_as_even():
    rep = rb.concentration([10.0] * 200)
    assert rep.herfindahl == pytest.approx(1 / 200)
    assert rep.effective_sessions == pytest.approx(200.0)
    assert rep.gini == pytest.approx(0.0, abs=1e-12)
    assert rep.gini_floor == pytest.approx(0.0)
    assert rep.best_day_share == pytest.approx(1 / 200)
    assert rep.longest_losing_streak == 0
    assert rep.underwater_fraction == 0.0


def test_shares_against_a_non_positive_total_are_nan_rather_than_negative():
    rep = rb.concentration([10.0, -50.0, 5.0, -20.0])
    assert rep.net_positive is False
    assert math.isnan(rep.best_day_share)
    assert all(math.isnan(v) for v in rep.top_share.values())
    # The gross variants stay readable: something was made, even if less was kept.
    assert rep.best_day_share_gross == pytest.approx(10.0 / 15.0)
    assert rep.days_to_zero == 0


def test_the_gini_cannot_fall_below_the_floor_its_loss_rate_imposes():
    rng = np.random.default_rng(19)
    for seed in range(20):
        x = rng.normal(5.0, 100.0, 300) + seed
        rep = rb.concentration(x)
        assert rep.gini >= rep.gini_floor - 1e-9


def test_effective_sessions_never_exceeds_the_number_of_winners():
    rng = np.random.default_rng(23)
    rep = rb.concentration(rng.normal(20.0, 200.0, 400))
    assert rep.effective_sessions <= rep.n_winners + 1e-9


def test_removing_the_best_days_matches_the_hand_computation():
    pnl = [100.0, 50.0, 25.0, -10.0, -5.0]
    rep = rb.concentration(pnl, drop=(1, 2))
    assert rep.total == pytest.approx(160.0)
    assert rep.without_best[1] == pytest.approx(60.0)
    assert rep.without_best[2] == pytest.approx(10.0)
    assert rep.days_to_zero == 3


def test_top_shares_are_monotone_in_the_fraction_taken():
    rng = np.random.default_rng(31)
    rep = rb.concentration(rng.normal(30.0, 200.0, 500))
    assert rep.top_share[0.01] <= rep.top_share[0.05] <= rep.top_share[0.10]


def test_the_rolling_window_share_is_at_least_the_calendar_week_share():
    """A calendar boundary can split the good run; a rolling window cannot."""
    rng = np.random.default_rng(37)
    pnl = rng.normal(40.0, 250.0, 260)
    dates = [dt.date(2025, 1, 1) + dt.timedelta(days=i) for i in range(260)]
    rep = rb.concentration(pnl, dates=dates)
    assert rep.best_window_share[5] >= rep.best_week_share - 1e-12
    assert rep.best_month_share >= rep.best_week_share - 1e-12


def test_a_nan_session_is_refused_rather_than_silently_dropped():
    with pytest.raises(ValueError, match="NaN or inf"):
        rb.concentration([1.0, float("nan"), 3.0])


def test_mismatched_dates_are_refused():
    with pytest.raises(ValueError, match="2 dates for 3 sessions"):
        rb.concentration([1.0, 2.0, 3.0], dates=[dt.date(2025, 1, 1), dt.date(2025, 1, 2)])


def test_drawdown_profile_on_a_hand_built_series():
    #        equity:  10   6   3   8  13
    pnl = [10.0, -4.0, -3.0, 5.0, 5.0]
    out = rb.drawdown_profile(pnl)
    assert out["longest_losing_streak"] == 2.0
    assert out["max_drawdown"] == pytest.approx(7.0)
    assert out["longest_underwater"] == 3.0          # sessions 2, 3, 4 are below the peak
    assert out["underwater_fraction"] == pytest.approx(0.6)


def test_a_flat_session_does_not_extend_a_losing_streak():
    assert rb.drawdown_profile([-1.0, -1.0, 0.0, -1.0])["longest_losing_streak"] == 2.0


def test_time_under_water_counts_from_a_zero_peak():
    """Losing on day one is under water on day one; the account holder knows this."""
    assert rb.drawdown_profile([-5.0, 1.0, 1.0])["underwater_fraction"] == pytest.approx(1.0)


def test_the_report_table_renders_without_exploding_on_a_losing_sample():
    text = rb.concentration([-1.0, -2.0, 3.0]).table()
    assert "best days to zero" in text
    assert "already <= 0" in text


# ======================================================================================
# NULLS - where a threshold would otherwise be invented
# ======================================================================================

def test_the_ordering_null_flags_a_clustered_losing_run():
    """Same sessions, two orderings: one with the losses in a block, one interleaved."""
    losses = [-100.0] * 12
    wins = [40.0] * 108
    clustered = losses + wins
    spread = [-100.0 if i % 10 == 0 else 40.0 for i in range(120)]
    p_clustered = rb.ordering_null(clustered, reps=400, seed=1)
    p_spread = rb.ordering_null(spread, reps=400, seed=1)
    assert p_clustered["p_longest_losing_streak"] < 0.01
    assert p_spread["p_longest_losing_streak"] > p_clustered["p_longest_losing_streak"]


def test_the_ordering_null_is_deterministic_under_a_seed():
    rng = np.random.default_rng(41)
    x = rng.normal(10.0, 100.0, 200)
    assert rb.ordering_null(x, reps=200, seed=3) == rb.ordering_null(x, reps=200, seed=3)
    assert rb.ordering_null(x, reps=200, seed=3) != rb.ordering_null(x, reps=200, seed=4)


def test_the_ordering_null_refuses_a_sample_too_short_to_shuffle():
    with pytest.raises(ValueError, match="at least 3 sessions"):
        rb.ordering_null([1.0, 2.0])


def test_the_tail_null_flags_a_fat_tail_against_its_gaussian_reference():
    rng = np.random.default_rng(43)
    ordinary = rng.normal(20.0, 100.0, 300)
    with_a_jackpot = ordinary.copy()
    with_a_jackpot[150] = 8000.0
    p_ordinary = rb.tail_null(ordinary, reps=300, seed=2)
    p_jackpot = rb.tail_null(with_a_jackpot, reps=300, seed=2)
    assert p_jackpot["p_best_day_share_gross"] < 0.05
    assert p_ordinary["p_best_day_share_gross"] > p_jackpot["p_best_day_share_gross"]


def test_every_null_returns_probabilities():
    rng = np.random.default_rng(47)
    x = rng.normal(15.0, 120.0, 150)
    for out in (rb.ordering_null(x, reps=100), rb.tail_null(x, reps=100)):
        assert all(0.0 <= v <= 1.0 for v in out.values())


# ======================================================================================
# PARAMETER SENSITIVITY
# ======================================================================================

def _grid_1d(fn) -> dict[tuple[float, ...], float]:
    return {(float(k),): float(fn(k)) for k in range(1, 11)}


def test_a_plateau_reads_near_one_and_a_cliff_reads_near_zero():
    plateau = _grid_1d(lambda k: 1.0 - abs(k - 5) * 0.01)
    cliff = _grid_1d(lambda k: 1.0 if k == 5 else -0.2)
    flat = rb.parameter_sensitivity(plateau)
    sharp = rb.parameter_sensitivity(cliff)
    assert flat.neighbour_ratio == pytest.approx(0.99, abs=0.01)
    assert sharp.neighbour_ratio == pytest.approx(-0.2, abs=1e-9)
    assert sharp.neighbour_sign_agreement == 0.0
    assert flat.positive_fraction == 1.0
    assert sharp.positive_fraction == pytest.approx(0.1)


def test_neighbours_are_one_step_along_exactly_one_axis():
    scores = {(a, b): 1.0 for a in (1.0, 2.0, 3.0) for b in (10.0, 20.0, 30.0)}
    scores[(2.0, 20.0)] = 5.0
    rep = rb.parameter_sensitivity(scores, axis_names=("lookback", "threshold"))
    assert rep.best_key == (2.0, 20.0)
    assert rep.n_neighbours == 4                     # not the 8 of a diagonal neighbourhood
    assert set(rep.per_axis_ratio) == {"lookback", "threshold"}


def test_an_asymmetric_decay_shows_up_in_the_worst_neighbour():
    scores = {(1.0,): 0.9, (2.0,): 1.0, (3.0,): -0.5}
    rep = rb.parameter_sensitivity(scores)
    assert rep.neighbour_ratio == pytest.approx(0.2)
    assert rep.worst_neighbour_ratio == pytest.approx(-0.5)


def test_ratios_are_nan_when_the_best_point_is_not_positive():
    """Dividing by a negative best flips the comparison and reports a cliff as a plateau."""
    rep = rb.parameter_sensitivity({(1.0,): -1.0, (2.0,): -0.5, (3.0,): -2.0})
    assert math.isnan(rep.neighbour_ratio)
    assert math.isnan(rep.plateau_fraction)
    assert rep.positive_fraction == 0.0


def test_the_shipped_point_can_be_scored_instead_of_the_grid_maximum():
    rep = rb.parameter_sensitivity(_grid_1d(lambda k: float(k) ** 2), best_key=(3.0,))
    assert rep.best_key == (3.0,)
    assert rep.best_score == pytest.approx(9.0)
    assert rep.neighbour_ratio > 1.0                 # the neighbours beat the shipped point


def test_a_point_outside_the_grid_is_refused():
    with pytest.raises(ValueError, match="not a point in the grid"):
        rb.parameter_sensitivity({(1.0,): 1.0}, best_key=(9.0,))


def test_a_partially_filled_grid_only_counts_points_that_exist():
    scores = {(1.0,): 0.5, (2.0,): 1.0}              # no (3.0,)
    rep = rb.parameter_sensitivity(scores)
    assert rep.n_neighbours == 1
    assert rep.n_points == 2


def test_a_ragged_grid_is_refused():
    with pytest.raises(ValueError, match="differing lengths"):
        rb.parameter_sensitivity({(1.0,): 1.0, (1.0, 2.0): 2.0})


def test_an_empty_grid_is_refused():
    with pytest.raises(ValueError, match="non-empty grid"):
        rb.parameter_sensitivity({})


def test_the_sensitivity_table_renders():
    assert "neighbour ratio" in rb.parameter_sensitivity(_grid_1d(lambda k: 1.0)).table()


# ======================================================================================
# INTERPRETATION: MEASUREMENT VERSUS JUDGEMENT
# ======================================================================================

def test_every_reported_metric_has_a_documented_interpretation():
    assert rb.undocumented() == set()


def test_every_doc_declares_whether_its_concern_level_is_a_judgement():
    for doc in rb.METRIC_DOCS.values():
        assert doc.basis in ("arithmetic", "judgement")
        assert doc.interpretation.strip() and doc.concern.strip()


def test_a_doc_cannot_claim_an_unrecognised_basis():
    with pytest.raises(ValueError, match="arithmetic or judgement"):
        rb.MetricDoc("x", "what it is", "what to worry about", "obviously bad")


def test_the_judgement_calls_are_listed_so_a_reader_can_argue_with_them():
    named = rb.judgements()
    assert "best_day_share" in named
    assert "neighbour_ratio" in named
    # And the ones that are pure arithmetic must not be in it.
    assert "effective_sessions" not in named
    assert "days_to_zero" not in named


def test_readings_attach_the_documentation_to_both_report_types():
    conc = rb.readings(rb.concentration([1.0, 2.0, -1.0, 5.0]))
    sens = rb.readings(rb.parameter_sensitivity(_grid_1d(lambda k: float(k))))
    assert {r.metric for r in conc} >= {"days_to_zero", "effective_sessions", "gini"}
    assert {r.metric for r in sens} >= {"neighbour_ratio", "positive_fraction"}
    assert all(r.basis in ("arithmetic", "judgement") for r in conc + sens)


# ======================================================================================
# INTEGRATION: THE REAL ES STORE
# ======================================================================================

@pytest.mark.skipif(not ES_STORE.exists(), reason="data/futures/ES.parquet not present")
def test_the_real_es_store_runs_end_to_end_with_finite_metrics():
    """Every metric over the deployed store: finite, in range, and no value pinned.

    Deliberately asserts no specific number. The store is refetched nightly, so an assertion
    on a measured value would fail on a Tuesday for a reason that has nothing to do with the
    code. What is pinned is what CANNOT change: shares lie in their ranges, the labels are
    causal, and the attribution adds up.
    """
    try:
        bars = pd.read_parquet(ES_STORE)
    except ImportError as exc:                       # 3.11 has no parquet engine
        pytest.skip(f"no parquet engine: {exc}")

    out = rb.session_table(bars)
    assert len(out) > 100
    assert out.index.is_monotonic_increasing
    assert out["bars"].min() > 0
    assert np.isfinite(out[["ret", "rvol", "volume", "efficiency"]].to_numpy()).all()
    assert (out["efficiency"].between(0.0, 1.0)).all()

    # This store is 23-hour Globex, so overnight IS distinguishable from RTH here.
    assert rb.coverage(out, "overnight") > 0.9
    assert rb.coverage(out, "open") > 0.9

    labs = rb.labellers()
    assert rb.audit_label_causality(labs, out) == {}
    labels = rb.label_table(out, labs)
    assert set(labels.columns) == {lab.name for lab in labs}

    # A stand-in strategy so the metrics run over a P&L series with the real store's own
    # regime structure. It is not an edge and is not claimed to be, but it is at least
    # CAUSAL: the signal is the overnight move, complete at 09:30, and the return is the RTH
    # session that follows it. The RTH return is compounded from the three RTH buckets,
    # which tile 09:30-16:00 exactly - and using the whole-session `ret` here instead would
    # pay the strategy for the overnight move it used as its signal, which is the same
    # lookahead this module exists to catch, one level up.
    rth = np.ones(len(out))
    for name in ("open", "midday", "close"):
        rth *= 1.0 + np.nan_to_num(out[f"{name}_ret"].to_numpy(), nan=0.0)
    signal = np.sign(np.nan_to_num(out["overnight_ret"].to_numpy(), nan=0.0))
    pnl = signal * (rth - 1.0) * 50.0 * 6000.0

    rep = rb.concentration(pnl, dates=list(out.index))
    assert rep.n == len(out)
    assert 0.0 <= rep.underwater_fraction <= 1.0
    assert 0 <= rep.longest_losing_streak <= rep.n
    assert 0 <= rep.longest_underwater <= rep.n
    assert rep.max_drawdown >= 0.0
    assert rep.gini >= rep.gini_floor - 1e-9
    assert 0.0 <= rep.gini <= 1.0
    assert 0 <= rep.days_to_zero <= rep.n
    if rep.n_winners:
        assert 1.0 <= rep.effective_sessions <= rep.n_winners + 1e-9
    assert rep.table()

    rows = rb.regime_performance(pnl, labels["vol_tercile"])
    assert rows
    assert sum(r.n for r in rows) == int((labels["vol_tercile"] != rb.WARMUP).sum())
    assert sum(r.sessions_share for r in rows) == pytest.approx(1.0)
    assert all(math.isfinite(r.mean) and 0.0 <= r.win_rate <= 1.0 for r in rows)

    nulls = rb.ordering_null(pnl, reps=200, seed=0)
    assert all(0.0 <= v <= 1.0 for v in nulls.values())
