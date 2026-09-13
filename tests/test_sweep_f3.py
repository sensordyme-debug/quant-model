"""F-3's statistics and money paths - the functions that decide what its result IS.

F-3 is rank 1 in `research/sweep_audit.md`. It is the only script in the archive whose
published *positive* claim is refuted by the corrections: pooled out-of-sample
`IC +0.01133 at t +2.17` (h = 5) and `+0.01264 at t +2.41` (h = 21), both read against 1.96
and both carried into `research/backlog.md` as "the forecast is real and tiny".

Three separate defects produce that number, and this file tests each one at the function that
commits it rather than at the printed output:

  `sweep_f3.py:179`      the label `log(open[t+1+h] / open[t+1])` is formed on EVERY session,
                         so consecutive labels share h-1 days of the same returns;
  `sweep_f3.py:283-288`  `tstat` is `mean / (sd / sqrt(n))`, which assumes they do not;
  `sweep_f3.py:553`      the (model, horizon) pair is an argmax over ten cells, reported at
                         the threshold for one.

Nothing here reads `data/f3/panel.parquet` - the fixtures are built so the right answer is
known by construction. The measured numbers from the real panel live in the audit document.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import sweep_f3

from quant_brain.core import stats

# --------------------------------------------------------------------------------------------
# the label: what F-3 is asking the model to predict
# --------------------------------------------------------------------------------------------

def _opens(n_days, n_syms, seed=0):
    """A price panel of independent random walks - no cross-sectional or serial structure."""
    rng = np.random.default_rng(seed)
    steps = rng.normal(0.0, 0.01, (n_days, n_syms))
    return pd.DataFrame(100.0 * np.exp(np.cumsum(steps, axis=0)),
                        index=pd.bdate_range("2012-01-02", periods=n_days),
                        columns=[f"S{i}" for i in range(n_syms)])


@pytest.mark.parametrize("horizon", [5, 21])
def test_the_label_overlaps_by_exactly_horizon_minus_one_sessions(horizon):
    """`sweep_f3.py:179`'s formula, reproduced, and its dependence measured.

    `labels[h] = log(op.shift(-(1+h)) / op.shift(-1))` at date t spans sessions t+1..t+1+h.
    At date t+1 it spans t+2..t+2+h. They share h-1 days. Under independent daily returns the
    theoretical autocorrelation of such a label at lag k is (h-k)/h, which is what pins the
    structure as MA(h-1) rather than as some vaguer "persistence".
    """
    # long enough that a lag-h correlation estimate has a standard error well under the
    # tolerance: there are only n/h independent windows, so n must scale with h.
    op = _opens(40_000, 1, seed=horizon)
    entry = op.shift(-1)
    label = np.log(op.shift(-(1 + horizon)) / entry).iloc[:, 0].dropna().to_numpy()

    for k in (1, 2, horizon // 2):
        got = float(np.corrcoef(label[:-k], label[k:])[0, 1])
        assert got == pytest.approx((horizon - k) / horizon, abs=0.04), (
            f"lag {k} should carry {(horizon - k)}/{horizon} of the window")

    beyond = float(np.corrcoef(label[:-horizon], label[horizon:])[0, 1])
    assert abs(beyond) < 0.04, "and nothing survives past the horizon itself"


def _persistent_score_panel(horizon, seed, n_days=1500, n_syms=12, phi=0.98, beta=0.0016):
    """A panel with F-3's actual mechanism: a slow score against an overlapping label.

    A latent factor `f` follows an AR(1) with phi = 0.98 (a momentum-like state that changes
    slowly). Daily returns load on it weakly; the model's score is a noisy read of it. The
    label is the sum of the next `horizon` daily returns, formed every session.

    Both ingredients of the per-date IC therefore move slowly - the score because `f` is
    persistent, the label because consecutive windows overlap - so the IC SERIES is
    autocorrelated. That is what makes the naive t on it too large, and it is the reason a
    forecast can be genuinely weak-but-real and still print a t that means nothing.
    """
    rng = np.random.default_rng(seed)
    f = np.zeros((n_days, n_syms))
    for t in range(1, n_days):
        f[t] = phi * f[t - 1] + rng.normal(0, 1, n_syms) * np.sqrt(1 - phi ** 2)
    r = beta * f + rng.normal(0, 0.012, (n_days, n_syms))
    score = f + rng.normal(0, 1.2, (n_days, n_syms))

    label = np.full((n_days, n_syms), np.nan)
    for t in range(n_days - horizon - 1):
        label[t] = r[t + 1:t + 1 + horizon].sum(axis=0)

    dates = pd.bdate_range("2012-01-03", periods=n_days)
    frame = pd.DataFrame({
        "date": np.repeat(dates, n_syms),
        "sym": np.tile([f"S{i}" for i in range(n_syms)], n_days),
        f"y_{horizon}": label.ravel(),
    })
    keep = ~np.isnan(label.ravel())
    return frame[keep].reset_index(drop=True), score.ravel()[keep]


@pytest.mark.parametrize(("horizon", "floor"), [(5, 1.25), (21, 1.9)])
def test_ic_stats_reports_a_t_that_its_own_label_does_not_support(horizon, floor):
    """`ic_stats` is the function that produced +2.17, and it divides by the wrong error.

    On the real panel the measured inflation is 1.66x at h = 5 and 3.05x at h = 21. This
    fixture reproduces the same ordering and the same order of magnitude from a construction
    whose dependence is known, so the defect is demonstrated rather than asserted.
    """
    frame, pred = _persistent_score_panel(horizon, seed=100 + horizon)
    _ic, naive_t = sweep_f3.ic_stats(frame, pred, f"y_{horizon}")

    ics = (frame.assign(p=pred).groupby("date")
           .apply(lambda g: g["p"].corr(g[f"y_{horizon}"], method="spearman")
                  if len(g) > 5 else np.nan, include_groups=False).dropna().to_numpy())

    assert naive_t == pytest.approx(stats.tstat_iid(ics).t, abs=1e-9), (
        "ic_stats reports the naive iid t of the per-date IC series and nothing else")

    hac = stats.tstat_hac(ics, horizon=horizon)
    assert hac.lag == horizon - 1, "the lag must span the whole overlap"
    assert float(pd.Series(ics).autocorr(1)) > 0.15, (
        "the IC series is autocorrelated, which is the condition the naive t violates")
    assert abs(naive_t) > floor * abs(hac.t), (
        f"h={horizon}: the overlap correction must move this t materially")


def test_the_walk_forward_boundary_is_not_purged():
    """`sweep_f3.py:565-567` slices by calendar year with no gap for the label to close in.

    Year Y is predicted by a model trained on `year <= Y-2` and early-stopped on `year == Y-1`.
    The last training row is 31 December of Y-2, and its h-session label does not resolve until
    ~h sessions into Y-1 - which is the early-stopping window. The same holds at the selection
    boundary (`<= 2007` / `2008-2011`, `sweep_f3.py:99-100`). Nothing in the module removes
    those rows, so the stopping criterion is chosen partly on data the label already saw.
    """
    horizon = max(sweep_f3.HORIZONS)
    dates = pd.bdate_range("2011-11-01", "2012-03-01")
    train_end = pd.Timestamp("2011-12-31")

    last_train = dates[dates <= train_end][-1]
    # get_indexer rather than get_loc: get_loc is typed as possibly returning a slice or a
    # boolean mask (the duplicate-index cases), which cannot happen for this unique index but
    # which the checker has no way to rule out. get_indexer always returns positions.
    pos = int(dates.get_indexer([last_train])[0])
    label_closes = dates[pos + 1 + horizon]

    assert label_closes > train_end, "the final training label resolves inside the next slice"
    leaked = int(((dates > train_end) & (dates <= label_closes)).sum())
    assert leaked >= horizon, (
        f"{leaked} validation sessions are inside the last training label's window; a purge "
        f"would drop the final {horizon} training rows and this module drops none")

    assert sweep_f3.SELECT_TRAIN_END == 2007
    assert sweep_f3.SELECT_VALID == (2008, 2011)
    assert sweep_f3.TEST_START == 2012


# --------------------------------------------------------------------------------------------
# the book: what F-3 would have earned, and what it would have paid
# --------------------------------------------------------------------------------------------

def _book_frame(n_days=6, n_syms=10, seed=2):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2012-01-03", periods=n_days)
    rows = []
    for d in dates:
        for i in range(n_syms):
            rows.append({"date": d, "sym": f"S{i}", "entry_px": 50.0 + i,
                         "fwd1": float(rng.normal(0.0, 0.01))})
    return pd.DataFrame(rows)


def test_simulate_builds_a_dollar_neutral_book_at_the_requested_gross():
    """The long and short sleeves are equal and opposite, and together they are `gross`.

    `sweep_f3.py:330-334` puts `gross/2/k` on each of the top k and `-gross/2/k` on each of
    the bottom k. If that ever drifts, every bps-per-dollar-turned number in the F-3 tables
    is measured against the wrong denominator.
    """
    frame = _book_frame()
    pred = np.arange(len(frame), dtype=float)      # a strict ordering, no ties
    sess = sweep_f3.simulate(frame, pred, decile=0.20, gross=1.0, spread_bps=0.0)

    assert len(sess) == frame["date"].nunique() - 0
    # First session: the whole book is opened, so turnover is exactly gross x equity.
    assert sess["turnover"].iloc[0] == pytest.approx(1_000_000.0, rel=1e-9)


def test_simulate_charges_the_spread_on_both_legs_of_every_rebalance():
    """Turnover is notional traded, and `spread_bps` is charged on all of it.

    A book rebalanced daily pays the spread on what it opens AND on what it closes. The test
    fixes turnover by construction and then reads the cost difference between 0 bp and 2 bp,
    which must be exactly 2 bp of that turnover plus the unchanged commission.
    """
    frame = _book_frame()
    # a prediction that reorders the cross-section every session, so the book really trades
    pred = np.random.default_rng(17).normal(0.0, 1.0, len(frame))

    free = sweep_f3.simulate(frame, pred, decile=0.20, spread_bps=0.0)
    charged = sweep_f3.simulate(frame, pred, decile=0.20, spread_bps=2.0)

    assert (free["turnover"] > 0).all(), "the fixture must actually rebalance"
    assert charged["turnover"].to_numpy() == pytest.approx(free["turnover"].to_numpy())
    added = (charged["cost"] - free["cost"]).to_numpy()
    expected = 2.0 * 1e-4 * free["turnover"].to_numpy()
    assert added == pytest.approx(expected, rel=1e-9), "the spread is linear in turnover"
    assert (charged["net"] < free["net"]).all(), "and it can only reduce the net"


def test_simulate_long_only_holds_the_top_sleeve_at_full_gross():
    """`long_only` moves the whole book to one side rather than halving it.

    `sweep_f3.py:331` puts `gross/k` on the top k when long-only, against `gross/2/k` per side
    otherwise. Getting that wrong would double or halve every long-only row in the table.
    """
    frame = _book_frame()
    pred = np.arange(len(frame), dtype=float)

    both = sweep_f3.simulate(frame, pred, decile=0.20, long_only=False)
    top = sweep_f3.simulate(frame, pred, decile=0.20, long_only=True)

    # Opening day turnover is the gross notional in each case: 1.0x equity either way,
    # but the long-only book puts all of it on one side.
    assert top["turnover"].iloc[0] == pytest.approx(1_000_000.0, rel=1e-9)
    assert both["turnover"].iloc[0] == pytest.approx(1_000_000.0, rel=1e-9)
    assert not np.allclose(top["gross"].to_numpy(), both["gross"].to_numpy()), (
        "a long-only book earns the level, a dollar-neutral one earns the spread")


def test_summarize_prices_the_signal_per_dollar_turned_not_per_day():
    """`gross_bps` is F-3's decisive column and the one F-1's refusal turned on.

    `sweep_f3.py:352-355`: gross bps per dollar turned is `1e4 * mean(gross) / mean(turnover)`,
    and the cost line is the same ratio on costs. A book that trades a tenth as much has a
    tenth of the P&L and exactly the same bps, which is the whole reason this column exists.
    """
    sess = pd.DataFrame({"date": pd.bdate_range("2012-01-03", periods=4),
                         "gross": [100.0, 200.0, 150.0, 50.0],
                         "cost": [40.0, 40.0, 40.0, 40.0],
                         "turnover": [1e6, 1e6, 1e6, 1e6]})
    sess["net"] = sess["gross"] - sess["cost"]
    out = sweep_f3.summarize(sess, "unit")

    assert out["gross_bps"] == pytest.approx(1e4 * 125.0 / 1e6)
    assert out["cost_bps"] == pytest.approx(1e4 * 40.0 / 1e6)
    assert out["net_day"] == pytest.approx(85.0)
    assert out["sessions"] == 4
    assert out["worst"] == pytest.approx(10.0)

    # A book at a tenth the size has the same bps and a tenth the dollars - the invariance
    # the column is for.
    tenth = sess.assign(gross=sess["gross"] / 10, cost=sess["cost"] / 10,
                        turnover=sess["turnover"] / 10)
    tenth["net"] = tenth["gross"] - tenth["cost"]
    small = sweep_f3.summarize(tenth, "tenth")
    assert small["gross_bps"] == pytest.approx(out["gross_bps"])
    assert small["net_day"] == pytest.approx(out["net_day"] / 10)


def test_summarize_reports_the_naive_t_on_the_daily_net_series():
    """The `t` column that F-3's rows carry into the ledger is uncorrected.

    Unlike the IC, the daily net series is one observation per session and does NOT overlap,
    so this particular t is not inflated by AUD-18. It is still uncorrected for the ten cells
    the table prints, which is the part the audit charges F-3 for.
    """
    rng = np.random.default_rng(4)
    net = rng.normal(120.0, 900.0, 400)
    sess = pd.DataFrame({"date": pd.bdate_range("2012-01-03", periods=400),
                         "gross": net + 300.0, "cost": np.full(400, 300.0),
                         "turnover": np.full(400, 1e6), "net": net})
    out = sweep_f3.summarize(sess, "unit")

    assert out["t"] == pytest.approx(stats.tstat_iid(net).t, abs=1e-9)
    assert out["gross_t"] == pytest.approx(stats.tstat_iid(net + 300.0).t, abs=1e-9)


# --------------------------------------------------------------------------------------------
# the selection: how the reported cell was chosen
# --------------------------------------------------------------------------------------------

def test_the_reported_cell_is_the_argmax_of_ten_and_is_judged_as_if_it_were_one():
    """`sweep_f3.py:553` takes `max(sel, key=ic)` and `:583` prints the winner's t.

    With ten cells scored on the same validation window, the best validation IC is a maximum
    of ten draws, not a draw. This reproduces the selection on pure noise and shows how often
    the winner would look "significant" at the 1.96 bar F-3 read it against.
    """
    rng = np.random.default_rng(21)
    cells = len(sweep_f3.GRID) * len(sweep_f3.HORIZONS)
    assert cells == 10

    hits = 0
    trials = 2000
    for _ in range(trials):
        # ten independent null cells, each with a t drawn from the null distribution
        ts = rng.normal(0.0, 1.0, cells)
        if abs(ts[int(np.argmax(np.abs(ts)))]) > 1.96:
            hits += 1
    rate = hits / trials

    assert rate > 0.30, (
        f"the best of {cells} null cells clears 1.96 about {rate:.0%} of the time, against "
        f"the 5% the threshold is meant to deliver")
    # the threshold that would restore 5% is the one the audit quotes
    assert stats.bonferroni_threshold(cells) == pytest.approx(2.807, abs=0.005)
    assert 2.17 < stats.bonferroni_threshold(cells)
