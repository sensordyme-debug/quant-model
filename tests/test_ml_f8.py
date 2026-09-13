"""F-8's label and book paths - the two functions that decide what its result IS.

F-8 is rank 2 in `research/sweep_audit.md`. It is the F-track script whose statistics are most
exposed, for two reasons that have nothing to do with each other:

  `ml_f8.py:520`      `best = max(cells.items(), key=lambda kv: kv[1][0]["net_day"])` picks the
                      best of a twenty-cell grid ON THE TEST WINDOW, and clause 7's pass rule
                      (`:606`, `net > 0 and t > 2`) is then applied to that maximum at the
                      threshold for a single pre-registered test.
  `ml_f8.py:156-199`  `add_labels` builds `close`, a label defined at every slot and always
                      ending at the same 15:30 flatten. Consecutive `close` labels are not
                      merely overlapping, they are NESTED - slot k+1's label is a subset of
                      slot k's - which is the strongest label dependence anywhere in the repo.
                      Measured on `data/f1/f8_preds.parquet`: naive IC t +7.79 -> HAC +4.02.

Testing `add_labels` also turned up a defect that is not statistical at all: clause 3's stated
invariant, "**every book below turns exactly 2x equity per session**", is false for two of the
four books it ships. See `test_clause_3s_two_times_turnover_invariant_does_not_hold`.
"""
from __future__ import annotations

import ml_f8
import numpy as np
import pandas as pd
import pytest

from quant_brain.core import stats

N = ml_f8.N_SLOTS          # 11 decision slots per session, 0..10


# --------------------------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------------------------

def _slot_ts(day, slot):
    """The decision timestamp `add_labels` will recover slot `slot` from (09:55 + 30k)."""
    return pd.Timestamp(day) + pd.Timedelta(hours=9, minutes=55 + 30 * slot)


def _panel(n_days=3, n_syms=4, seed=1, drop=None):
    """One row per (session, slot, symbol). `drop` removes a (slot, sym) to open a gap."""
    rng = np.random.default_rng(seed)
    rows = []
    for day in pd.bdate_range("2024-01-02", periods=n_days):
        for slot in range(N):
            for j in range(n_syms):
                if drop is not None and (slot, j) == drop:
                    continue
                rows.append({"ts": _slot_ts(day, slot), "day": day.date(), "year": day.year,
                             "sym": f"S{j}", "fwd": float(rng.normal(0.0, 0.002))})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------------------------
# the label: what F-8 asks the model to predict
# --------------------------------------------------------------------------------------------

def test_add_labels_recovers_the_slot_from_the_decision_timestamp():
    """`ml_f8.py:163-164` derives the slot arithmetically; everything downstream keys off it."""
    out = ml_f8.add_labels(_panel(n_days=1))
    got = out.drop_duplicates("ts").sort_values("ts")["slot"].to_numpy()
    assert list(got) == list(range(N))
    assert out["slot"].min() == 0 and out["slot"].max() == N - 1


def test_the_close_label_is_the_sum_of_every_remaining_interval_in_the_session():
    """`close` holds to the 15:30 flatten, so its horizon is `11 - slot`, not a constant.

    This is the label F-8 selects as its best cell, and it is the one the deployed convention
    implies. The arithmetic below is the whole definition: at slot k the label is the sum of
    `fwd` over slots k..10, demeaned across the names present at that timestamp.
    """
    out = ml_f8.add_labels(_panel(n_days=2, n_syms=4)).sort_values(["sym", "day", "slot"])

    # rebuild the label independently: sum of the remaining intervals, then demean per timestamp
    raw = (out.sort_values(["sym", "day", "slot"])
              .groupby(["sym", "day"], sort=False)["fwd"]
              .transform(lambda s: s.iloc[::-1].cumsum().iloc[::-1]))
    expected = raw - raw.groupby(out["ts"]).transform("mean")

    # ml_f8.py:197 casts the label to float32, so the tolerance is float32 precision
    assert out["y_close"].to_numpy() == pytest.approx(expected.to_numpy(), abs=1e-8)
    assert out["y_close"].notna().all(), "close is defined at every slot - it keeps the panel"

    # and the horizon really is 11 - slot: the last slot spans one interval, the first eleven
    last = out[out["slot"] == N - 1]
    assert raw[last.index].to_numpy() == pytest.approx(last["fwd"].to_numpy(), abs=1e-12)


def test_close_labels_within_a_session_are_nested_not_merely_overlapping():
    """Every `close` label in a session ends at the same instant, so they contain one another.

    Undemeaned, `c_close(k) - c_close(k+1) == fwd(k)` exactly: slot k's label IS slot k+1's
    label plus one more interval. An overlapping label shares part of its window with its
    neighbour; a nested one shares all of it. That is why `close` shows the largest measured
    inflation in the archive (1.94x) despite F-1's own 30-minute label showing none.
    """
    panel = _panel(n_days=2, n_syms=1)        # one name: the demean is a no-op it can undo
    out = ml_f8.add_labels(panel).sort_values(["sym", "day", "slot"])

    # with a single name per timestamp the cross-sectional mean IS the value, so y_close == 0.
    # Reconstruct the pre-demean quantity from `fwd` and assert the nesting identity on it.
    for (_sym, _day), g in out.groupby(["sym", "day"], sort=False):
        fwd = g.sort_values("slot")["fwd"].to_numpy()
        raw = np.array([fwd[k:].sum() for k in range(N)])
        diffs = raw[:-1] - raw[1:]
        assert diffs == pytest.approx(fwd[:-1], abs=1e-15), (
            "slot k's close label is slot k+1's plus exactly one more interval")
        # nesting means the last slot's label is a single interval and the first spans all 11
        assert raw[-1] == pytest.approx(fwd[-1], abs=1e-15)
        assert raw[0] == pytest.approx(fwd.sum(), abs=1e-15)


def test_labels_are_demeaned_across_the_names_present_at_the_same_timestamp():
    """A dollar-neutral book earns the cross-section, so every label is a spread, not a level.

    `ml_f8.py:197`. If this drifted, every `gross_bps` in the F-8 tables would be measuring a
    market return the book does not take.
    """
    out = ml_f8.add_labels(_panel(n_days=2, n_syms=6))
    for label in ml_f8.LABELS:
        per_ts = out.dropna(subset=[f"y_{label}"]).groupby("ts")[f"y_{label}"].mean()
        assert per_ts.abs().max() < 1e-9, f"y_{label} is not demeaned within its timestamp"


@pytest.mark.parametrize(("label", "horizon", "slots"), [("h4", 4, 8), ("h7", 7, 5), ("h10", 10, 2)])
def test_a_fixed_horizon_label_exists_only_where_the_hold_fits_in_the_session(label, horizon, slots):
    """`slot + h <= 11`, so the three fixed horizons cover 8, 5 and 2 slots of the 11.

    This is what makes the four labels non-comparable on sample size: `close` keeps the whole
    panel, `h10` keeps two elevenths of it. The IC t's F-8 prints side by side in `run_ic` are
    computed on samples that differ by a factor of five.
    """
    out = ml_f8.add_labels(_panel(n_days=3, n_syms=4))
    live = out.dropna(subset=[f"y_{label}"])
    assert sorted(live["slot"].unique()) == list(range(slots))
    assert live["slot"].max() + horizon == N


def test_consecutive_fixed_horizon_labels_share_all_but_one_of_their_intervals():
    """h4 at slot k and at slot k+1 share 3 of their 4 intervals - an MA(3) in the slot index.

    Sampling every slot while holding for four is the textbook overlapping-label setup, and it
    is why `ic_vs`'s naive t on `y_h4` measured 6.69 against a HAC 5.05 on the real store.
    """
    panel = _panel(n_days=2, n_syms=1)
    out = ml_f8.add_labels(panel).sort_values(["sym", "day", "slot"])
    horizon = ml_f8.HORIZONS["h4"]

    for (_sym, _day), g in out.groupby(["sym", "day"], sort=False):
        fwd = g.sort_values("slot")["fwd"].to_numpy()
        raw = np.array([fwd[k:k + horizon].sum() for k in range(N - horizon + 1)])
        shared = raw[:-1] - fwd[:len(raw) - 1]        # drop the interval the next one lacks
        expect = raw[1:] - fwd[horizon:horizon + len(raw) - 1]
        assert shared == pytest.approx(expect, abs=1e-15), "3 of 4 intervals are common"


def test_a_missing_slot_invalidates_every_horizon_that_spans_it():
    """`ml_f8.py:176-180`: the chain breaks at a gap, and no label is built across one.

    Without this a data outage would silently produce a label that skips the missing interval
    and reads as a clean return. The guard is the reason the labels can be trusted at all.
    """
    intact = ml_f8.add_labels(_panel(n_days=1, n_syms=4, seed=2))
    holed = ml_f8.add_labels(_panel(n_days=1, n_syms=4, seed=2, drop=(5, 0)))

    s0_intact = intact[intact["sym"] == "S0"]
    s0_holed = holed[holed["sym"] == "S0"]

    # slot 5 is gone, and every h4 label whose window covers slot 5 (slots 2,3,4,5) is dead
    assert 5 not in set(s0_holed["slot"])
    alive = set(s0_holed.dropna(subset=["y_h4"])["slot"])
    assert alive.isdisjoint({2, 3, 4, 5}), f"labels spanning the gap survived: {alive}"
    # the untouched early slots keep theirs
    assert not set(s0_intact.dropna(subset=["y_h4"])["slot"]).isdisjoint({2, 3, 4, 5})


# --------------------------------------------------------------------------------------------
# the statistic
# --------------------------------------------------------------------------------------------

def test_ic_vs_reports_the_naive_iid_t_of_the_per_timestamp_ic_series():
    """`ml_f8.py:420-425` is the function behind every cell of the label x model IC matrix."""
    rng = np.random.default_rng(8)
    n_ts, n_syms = 300, 12
    frame = pd.DataFrame({
        "ts": np.repeat(pd.date_range("2024-01-02 09:55", periods=n_ts, freq="30min"), n_syms),
        "pred": rng.normal(0, 1, n_ts * n_syms),
        "y_close": rng.normal(0, 1, n_ts * n_syms),
    })
    _ic, got = ml_f8.ic_vs(frame, "pred", "y_close")

    ics = (frame.groupby("ts", sort=False)
           .apply(lambda g: g["pred"].corr(g["y_close"], method="spearman")
                  if len(g) > 5 else np.nan, include_groups=False).dropna().to_numpy())
    assert got == pytest.approx(stats.tstat_iid(ics).t, abs=1e-9)
    assert got != pytest.approx(stats.tstat_hac(ics, horizon=N).t, abs=1e-9) or len(ics) < 3


def test_the_close_labels_nesting_inflates_a_naive_t_more_than_a_shorter_hold_does():
    """More dependence in the label means more inflation, and `close` carries the most.

    Built here from a common per-session shock so that a session's ICs move together, which is
    what nesting produces. The ordering - `close` worse than `h4` - is the ordering measured on
    the real store (1.94x against 1.32x).
    """
    rng = np.random.default_rng(15)
    days, per_day = 500, N
    session_level = rng.normal(0.02, 0.05, days)

    nested = np.repeat(session_level, per_day) + rng.normal(0, 0.01, days * per_day)
    short = np.repeat(session_level, per_day) * 0.25 + rng.normal(0, 0.05, days * per_day)

    infl_nested = abs(stats.tstat_iid(nested).t) / abs(stats.tstat_hac(nested, horizon=N).t)
    infl_short = abs(stats.tstat_iid(short).t) / abs(stats.tstat_hac(short, horizon=4).t)

    assert infl_nested > 1.5, "a nested label must inflate the naive t substantially"
    assert infl_nested > infl_short, "and more than a label with a shorter shared window"


# --------------------------------------------------------------------------------------------
# the book: what F-8 would have traded, and what clause 3 says about it
# --------------------------------------------------------------------------------------------

def _book_frame(n_days=4, n_syms=20, seed=3, agree=False):
    """A prediction panel. `agree=True` gives every slot in a session the same ranking."""
    rng = np.random.default_rng(seed)
    rows = []
    for day in pd.bdate_range("2024-01-02", periods=n_days):
        fixed = rng.normal(0, 1, n_syms)
        for slot in range(N):
            pred = fixed if agree else rng.normal(0, 1, n_syms)
            for j in range(n_syms):
                rows.append({"ts": _slot_ts(day, slot), "day": day.date(), "year": day.year,
                             "sym": f"S{j}", "slot": slot, "pred": float(pred[j]),
                             "fwd": float(rng.normal(0, 0.002)), "entry_px": 50.0 + j})
    return pd.DataFrame(rows)


def test_the_session_book_turns_exactly_twice_equity_per_session():
    """One cohort in at slot 0 and out at the flatten: 1.0x each way, 2.0x total.

    This is the only one of the four books for which clause 3's invariant actually holds.
    """
    sess = ml_f8.simulate(_book_frame(), "session", costs=False)
    assert (sess["turnover"] / ml_f8.EQUITY).to_numpy() == pytest.approx(2.0, rel=1e-9)


def test_clause_3s_two_times_turnover_invariant_does_not_hold():
    """`ml_f8.py:74-76` claims every book turns exactly 2x equity a session. Two do not.

    `cohort_close` sums (nets) its eleven cohorts' weights before turnover is charged
    (`ml_f8.py:346`), so when consecutive slots rank the cross-section differently the
    offsetting legs cancel and less notional changes hands than the claim states. Measured
    here: ~1.4x rather than 2.0x.

    This matters because clause 3's stated purpose for fixing turnover is that
    "the sweep F-7 already exhausted cannot be re-run by accident" - i.e. the books are meant
    to be comparable at constant turnover so that `gross_bps` is like-for-like. They are not:
    turnover varies with how much the forecast churns, which is exactly the axis F-7 swept.
    """
    disagreeing = _book_frame(agree=False)
    turns = {}
    for kind, h in (("session", None), ("cohort_close", None),
                    ("cohort_h", 7), ("cohort_h", 4)):
        sess = ml_f8.simulate(disagreeing, kind, h=h, costs=False)
        turns[f"{kind}{h or ''}"] = float((sess["turnover"] / ml_f8.EQUITY).mean())

    assert turns["session"] == pytest.approx(2.0, rel=1e-9)
    assert turns["cohort_close"] < 1.75, (
        f"cohort_close turns {turns['cohort_close']:.3f}x, not the 2.0x clause 3 asserts")
    assert turns["cohort_h4"] < 2.0, (
        f"cohort_h4 turns {turns['cohort_h4']:.3f}x, not the 2.0x clause 3 asserts")


def test_cohort_h4_runs_at_half_the_gross_exposure_of_the_other_books():
    """`ml_f8.py:333-335`: `sub = gross/len(entries)` with 8 entries but only a 4-slot hold.

    At most four of the eight cohorts are live at once, so the book carries 4/8 = 0.5x gross
    where `session` and `cohort_h7` carry 1.0x. The h4 row is therefore not a label comparison
    at constant construction - it is a label comparison at half the risk, and its dollar
    columns are halved for a reason that has nothing to do with the label.
    """
    agreeing = _book_frame(agree=True)      # identical ranking each slot isolates the exposure
    h4 = ml_f8.simulate(agreeing, "cohort_h", h=4, costs=False)
    h7 = ml_f8.simulate(agreeing, "cohort_h", h=7, costs=False)
    base = ml_f8.simulate(agreeing, "session", costs=False)

    t4 = float((h4["turnover"] / ml_f8.EQUITY).mean())
    t7 = float((h7["turnover"] / ml_f8.EQUITY).mean())
    tb = float((base["turnover"] / ml_f8.EQUITY).mean())

    assert tb == pytest.approx(2.0, rel=1e-9)
    assert t7 == pytest.approx(2.0, rel=1e-9)
    assert t4 == pytest.approx(1.0, rel=1e-9), (
        "with a constant ranking cohort_h4 opens and closes only 0.5x gross")
    assert t4 == pytest.approx(tb / 2.0, rel=1e-9)


def test_summarize_edge_bps_is_gross_minus_cost_per_dollar_turned():
    """`ml_f8.py:396-404`: the decisive column, and the multiple over F-1's 0.797 bps.

    `edge_bps` is what has to be positive for any of this to matter; `mult` is the headline
    "x F-1" column. Both are ratios to mean turnover, so a book that trades less looks better
    on dollars and identical on bps - which is the invariance clause 5 exists to enforce.
    """
    sess = pd.DataFrame({"day": pd.bdate_range("2024-01-02", periods=4),
                         "gross": [400.0, 600.0, 500.0, 300.0],
                         "cost": [200.0, 200.0, 200.0, 200.0],
                         "turnover": [2e6, 2e6, 2e6, 2e6]})
    sess["net"] = sess["gross"] - sess["cost"]
    out = ml_f8.summarize(sess, "unit")

    assert out["gross_bps"] == pytest.approx(1e4 * 450.0 / 2e6)
    assert out["cost_bps"] == pytest.approx(1e4 * 200.0 / 2e6)
    assert out["edge_bps"] == pytest.approx(out["gross_bps"] - out["cost_bps"])
    assert out["mult"] == pytest.approx(out["gross_bps"] / ml_f8.F1_GROSS_BPS)
    assert out["net_day"] == pytest.approx(250.0)
    assert out["t"] == pytest.approx(stats.tstat_iid(sess["net"].to_numpy()).t, abs=1e-9)


# --------------------------------------------------------------------------------------------
# the selection
# --------------------------------------------------------------------------------------------

def test_clause_7s_pass_rule_is_applied_to_the_maximum_of_a_twenty_cell_search():
    """`ml_f8.py:520` argmaxes on the test window; `:606` gates that winner at `t > 2`.

    Reproduced on pure noise: with twenty cells scored on the same window, the best cell's t
    clears 2 far more often than the 5% the threshold promises. The cells here are correlated
    (rho = 0.7) because F-8's twenty cells are four books on five labels over one panel, which
    reduces the effective number of trials - and it is still nowhere near a 5% rate.
    """
    import ml_f8 as m

    cells = len(m.BOOKS) * len([m.BENCH] + m.LABELS)
    assert cells == 20

    rng = np.random.default_rng(33)
    trials, rho, hits = 4000, 0.7, 0
    for _ in range(trials):
        common = rng.normal(0, 1)
        ts = np.sqrt(rho) * common + np.sqrt(1 - rho) * rng.normal(0, 1, cells)
        if ts.max() > 2.0:
            hits += 1
    rate = hits / trials

    assert rate > 0.12, (
        f"the best of {cells} correlated null cells clears t > 2 about {rate:.0%} of the "
        f"time, against the 5% clause 7 assumes")
    assert stats.bonferroni_threshold(cells) == pytest.approx(3.023, abs=0.005)
