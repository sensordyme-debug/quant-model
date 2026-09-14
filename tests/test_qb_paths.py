"""Tests for Monte Carlo path generation and failure testing.

Two properties carry most of the weight. A resampler must preserve the serial structure it
claims to preserve, because clustered losses are what breach a trailing limit. And a stress
scenario must still be present in the paths the twin actually sees - an ordering scenario
that the bootstrap shuffles away measures nothing, and measured *better* than the base case
before the prefix pinning was added.
"""
from __future__ import annotations

import numpy as np
import pytest

from quant_brain.markets.futures_cme import paths as pa
from quant_brain.markets.futures_cme import twin as tw


def _days(pnl, adverse=1.4):
    return tw.days_from_pnl(list(pnl), path_fn=tw.u_shaped_path(adverse))


def _twin(**kw):
    kw.setdefault("profit_target", 3_000.0)
    kw.setdefault("payout_policy", tw.PayoutPolicy(fraction=0.5))
    return tw.TopstepTwin(50_000, **kw)


@pytest.fixture
def series():
    rng = np.random.default_rng(11)
    return _days(rng.normal(55, 350, size=150))


# ======================================================================================
# RESAMPLERS
# ======================================================================================

def test_every_resampler_returns_the_requested_shape(series):
    for maker in (lambda: pa.moving_block(series, block=10, reps=7),
                  lambda: pa.stationary_bootstrap(series, mean_block=10, reps=7),
                  lambda: pa.iid(series, reps=7)):
        out = maker()
        assert len(out) == 7
        assert all(len(p) == len(series) for p in out)


def test_resampled_days_are_drawn_from_the_original_sessions(series):
    original = {round(d.pnl, 9) for d in series}
    for p in pa.moving_block(series, block=10, reps=5):
        assert {round(d.pnl, 9) for d in p} <= original


def test_resamplers_are_deterministic_under_a_seed(series):
    a = pa.moving_block(series, block=10, reps=3, seed=4)
    b = pa.moving_block(series, block=10, reps=3, seed=4)
    c = pa.moving_block(series, block=10, reps=3, seed=5)
    assert [d.pnl for d in a[0]] == [d.pnl for d in b[0]]
    assert [d.pnl for d in a[0]] != [d.pnl for d in c[0]]


def test_the_block_bootstrap_preserves_autocorrelation_and_iid_destroys_it():
    """The property the whole module rests on, measured rather than assumed."""
    rng = np.random.default_rng(3)
    # A strongly autocorrelated series: losses genuinely cluster.
    x = np.zeros(400)
    for i in range(1, 400):
        x[i] = 0.85 * x[i - 1] + rng.normal(0, 100)
    days = _days(x + 40)

    def lag1(p):
        a = np.array([d.pnl for d in p])
        return float(np.corrcoef(a[:-1], a[1:])[0, 1])

    original = lag1(days)
    block = float(np.mean([lag1(p) for p in pa.moving_block(days, block=25, reps=40)]))
    flat = float(np.mean([lag1(p) for p in pa.iid(days, reps=40)]))
    assert original > 0.6
    assert block > 0.4, f"blocks should retain most of the dependence, got {block:.2f}"
    assert abs(flat) < 0.15, f"iid should destroy it, got {flat:.2f}"


def test_a_longer_block_retains_more_dependence():
    rng = np.random.default_rng(5)
    x = np.zeros(400)
    for i in range(1, 400):
        x[i] = 0.9 * x[i - 1] + rng.normal(0, 100)
    days = _days(x + 40)

    def lag1(p):
        a = np.array([d.pnl for d in p])
        return float(np.corrcoef(a[:-1], a[1:])[0, 1])

    short = np.mean([lag1(p) for p in pa.moving_block(days, block=2, reps=30)])
    long = np.mean([lag1(p) for p in pa.moving_block(days, block=50, reps=30)])
    assert long > short


def test_resamplers_refuse_a_series_too_short_to_resample():
    one = _days([100.0])
    for call in (lambda: pa.moving_block(one, block=1),
                 lambda: pa.stationary_bootstrap(one, mean_block=1),
                 lambda: pa.iid(one)):
        with pytest.raises(ValueError):
            call()


def test_resamplers_refuse_nonsense_parameters(series):
    with pytest.raises(ValueError):
        pa.moving_block(series, block=0)
    with pytest.raises(ValueError):
        pa.stationary_bootstrap(series, mean_block=0.5)


def test_a_longer_requested_path_extends_the_calendar_with_usable_days(series):
    """Padding days must carry an intraday path, or the twin refuses the whole path."""
    out = pa.moving_block(series, block=10, reps=2, length=200)
    assert len(out[0]) == 200
    assert all(d.path for d in out[0]), "a padded day without a path is unrunnable"
    days = [d.day for d in out[0]]
    assert days == sorted(days) and all(d.weekday() < 5 for d in days)
    _twin().run(out[0])          # must not raise


def test_the_rebuilt_intraday_path_moves_with_the_day_by_hand():
    """A path that belonged to a +$400 day is not the path of a -$400 day.

    `_rebuild` re-closes a session ADDITIVELY: the change accrues linearly across the marks,
    so the last one moves the whole way and the path still ends at the close. It used to
    rescale by `new / old`, an unbounded ratio that blew a -$900 trough up to -$476,410 on a
    near-flat template day. Every number below is hand arithmetic.
    """
    d = _days([400.0])[0]
    assert d.path == pytest.approx((-280.0, -560.0, 400.0))    # u_shaped_path(1.4) on +400

    rebuilt = pa._rebuild([d], [-400.0])[0]
    assert rebuilt.pnl == -400.0
    # delta = -400 - 400 = -800, accrued at 1/3, 2/3, 3/3 of the session.
    assert rebuilt.path == pytest.approx((-280.0 - 800 / 3, -560.0 - 1600 / 3, -400.0))
    assert rebuilt.path[-1] == pytest.approx(rebuilt.pnl), "the path must end at the close"
    # Bounded: the trough can move by at most the size of the change, and no more.
    assert min(rebuilt.path) >= min(d.path) - 800.0


# ======================================================================================
# SCENARIOS
# ======================================================================================

def test_scale_losses_touches_only_losing_days():
    days = _days([100.0, -200.0, 300.0, -50.0])
    out = pa.ScaleLosses(name="x", describe="", factor=2.0).apply(days)
    assert [d.pnl for d in out] == [100.0, -400.0, 300.0, -100.0]


def test_add_cost_touches_every_day():
    days = _days([100.0, -200.0])
    out = pa.AddCost(name="x", describe="", per_day=25.0).apply(days)
    assert [d.pnl for d in out] == [75.0, -225.0]


def test_worst_run_first_moves_the_worst_window_to_the_front():
    days = _days([100.0] * 10 + [-300.0] * 5 + [100.0] * 10)
    out = pa.WorstRunFirst(name="x", describe="", window=5).apply(days)
    assert [d.pnl for d in out[:5]] == [-300.0] * 5
    assert sorted(d.pnl for d in out) == sorted(d.pnl for d in days), (
        "reordering must not change the multiset of sessions")


def test_a_shock_inserts_one_session_and_lengthens_the_series():
    days = _days([100.0] * 10)
    out = pa.Shock(name="x", describe="", size=-900.0, at=0).apply(days)
    assert len(out) == 11
    assert out[0].pnl == -900.0
    assert all(d.path for d in out), "an inserted day must be runnable"


def test_decay_shrinks_the_edge_and_keeps_the_noise():
    rng = np.random.default_rng(1)
    raw = rng.normal(80, 300, size=200)
    days = _days(raw)
    out = pa.Decay(name="x", describe="", end_fraction=0.0).apply(days)
    a = np.array([d.pnl for d in out])
    assert a.mean() < raw.mean() / 2, "the edge should be roughly halved on average"
    assert a.std() == pytest.approx(raw.std(), rel=0.2), "the noise should survive"


def test_widen_intraday_deepens_the_trough_and_leaves_the_close():
    days = _days([400.0])
    out = pa.WidenIntraday(name="x", describe="", factor=2.0).apply(days)
    assert out[0].pnl == 400.0
    assert min(out[0].path) == pytest.approx(min(days[0].path) * 2)


def test_every_default_scenario_has_a_name_and_a_description():
    for s in pa.DEFAULT_SCENARIOS:
        assert s.name and s.describe
        assert s.name != s.describe


def test_scenarios_carry_no_probability():
    """Deliberate: a probability invites averaging, which defeats stress testing."""
    for s in pa.DEFAULT_SCENARIOS:
        assert not hasattr(s, "probability")


# ======================================================================================
# THE PREFIX PIN - the bug that inverted a result
# ======================================================================================

def test_ordering_scenarios_declare_a_prefix_to_pin():
    by_name = {s.name: s for s in pa.DEFAULT_SCENARIOS}
    assert by_name["worst 10d first"].pin_prefix == 10
    assert by_name["-$1,000 shock on day 1"].pin_prefix == 1
    assert by_name["cost +$25/day"].pin_prefix == 0, (
        "a per-day transformation is order-independent and needs no pin")


def test_a_pinned_prefix_survives_the_resample():
    # A varied tail, so "the tail was resampled" is actually observable - an all-constant
    # tail resamples to itself and would make the check vacuous.
    days = _days([-300.0] * 5 + list(np.arange(40) * 10.0 + 50.0))
    out = pa.resample_with_prefix(days, pin=5, block=10, reps=20, seed=0)
    for p in out:
        assert [d.pnl for d in p[:5]] == [-300.0] * 5, "the pinned head was resampled"
    assert len({tuple(d.pnl for d in p[5:]) for p in out}) > 1, "the tail was not resampled"


def test_no_pin_resamples_everything():
    days = _days([-300.0] * 5 + list(np.arange(40) * 10.0 + 50.0))
    out = pa.resample_with_prefix(days, pin=0, block=10, reps=20, seed=0)
    heads = {tuple(d.pnl for d in p[:5]) for p in out}
    assert len(heads) > 1


def test_the_prefix_pin_changes_the_answer_on_an_ordering_scenario():
    """Without it, "worst run first" measured as safer than the base case.

    That was not a small loss of power - the reordering that moves the worst stretch to the
    front also breaks up whatever run the base ordering contained, so a bootstrap that
    reshuffles both ends up comparing two arbitrary orderings and can favour the stressed one.
    """
    rng = np.random.default_rng(11)
    days = _days(rng.normal(55, 350, size=150))
    t = _twin()
    stressed = pa.WorstRunFirst(name="w", describe="", window=10, pin_prefix=10).apply(days)

    unpinned = pa.resample_with_prefix(stressed, pin=0, block=10, reps=200, seed=0)
    pinned = pa.resample_with_prefix(stressed, pin=10, block=10, reps=200, seed=0)
    base = pa.resample_with_prefix(days, pin=0, block=10, reps=200, seed=0)

    p_base = tw.evaluate_twin(t, base).p_pass_combine
    p_unpinned = tw.evaluate_twin(t, unpinned).p_pass_combine
    p_pinned = tw.evaluate_twin(t, pinned).p_pass_combine

    assert p_pinned < p_base, "pinned, the worst-run-first scenario must hurt"
    assert p_pinned < p_unpinned, "pinning must bite harder than not pinning"


# ======================================================================================
# THE STRESS REPORT
# ======================================================================================

def test_stress_reports_a_base_case_and_every_scenario(series):
    r = pa.stress(_twin(), series, reps=60)
    assert set(r.scenarios) == {s.name for s in pa.DEFAULT_SCENARIOS}
    for row in (r.base, *r.scenarios.values()):
        for k in ("p_pass_combine", "p_first_payout", "p_liquidated", "mean_gross"):
            assert 0 <= row[k] if k.startswith("p_") else row[k] >= 0


def test_every_default_scenario_actually_hurts(series):
    """A scenario that never changes the answer is decoration."""
    r = pa.stress(_twin(), series, reps=200)
    base = r.base["p_first_payout"]
    for name, row in r.scenarios.items():
        assert row["p_first_payout"] < base, f"{name} did not hurt at all"


def test_the_default_shock_is_survivable_rather_than_arithmetic():
    """A shock beyond the MLL kills a fresh account with certainty and tests the rulebook.

    The binding constraint is the intraday TROUGH, not the close: a shock day is rebuilt with
    the template's path shape, so under u_shaped_path(k) a close of -X troughs at -kX. The
    default must satisfy k * |size| < MLL, and this asserts the arithmetic rather than
    trusting the comment that states it.
    """
    shock = next(s for s in pa.DEFAULT_SCENARIOS if isinstance(s, pa.Shock))
    mll = 2_000.0
    # A series with real losing days, so the shock borrows a LOSING session's shape - which
    # is the case the default was sized against.
    days = _days([100.0] * 15 + [-500.0] * 5)
    stressed = shock.apply(days)
    assert stressed[0].pnl == shock.size
    # Donor is the -$500 day, path (-350, -700, -500); k = -1000 / -500 = 2.
    assert stressed[0].path == pytest.approx((-700.0, -1400.0, -1000.0))
    trough = min(stressed[0].path)
    assert trough == pytest.approx(shock.size * 1.4)
    assert trough > -mll, (
        f"the shock day troughs at {trough:,.0f}, past the {mll:,.0f} MLL, so the scenario "
        "is fatal by arithmetic and measures the rulebook rather than the strategy")
    r = _twin().run(stressed)
    assert r.days > 1, "the account must survive the shock day itself"


def test_the_table_renders_and_names_the_worst(series):
    r = pa.stress(_twin(), series, reps=60)
    text = r.table()
    assert "scenario" in text and "base" in text
    for s in pa.DEFAULT_SCENARIOS:
        assert s.name in text
    name, row = r.worst()
    assert name in r.scenarios
    assert row["p_first_payout"] == min(v["p_first_payout"] for v in r.scenarios.values())


def test_worst_of_an_empty_report_is_the_base_case():
    r = pa.StressReport(base={"p_first_payout": 0.5}, scenarios={})
    assert r.worst()[0] == "base"


# ======================================================================================
# BREAK-EVEN AND THE CLUSTERING PREMIUM
# ======================================================================================

def test_the_break_even_shock_is_the_point_the_rate_crosses(series):
    t = _twin()
    x = pa.break_even_shock(t, series, target_paid_rate=0.5, reps=120, hi=200.0, tol=4.0)
    assert 0 < x < 200

    def paid(extra):
        d = pa._rebuild(series, [s.pnl - extra for s in series])
        return tw.evaluate_twin(t, pa.moving_block(d, block=10, reps=120, seed=0)
                                ).p_first_payout

    assert paid(x - 8) >= 0.5 > paid(x + 8), "the returned point does not bracket the crossing"


def test_a_strategy_that_never_reaches_the_target_returns_the_floor(series):
    t = _twin()
    dead = pa._rebuild(series, [-abs(s.pnl) - 500 for s in series])
    assert pa.break_even_shock(t, dead, target_paid_rate=0.5, reps=40, lo=0.0, hi=50.0) == 0.0


def test_a_robust_strategy_returns_the_ceiling(series):
    t = _twin()
    assert pa.break_even_shock(t, series, target_paid_rate=0.0, reps=40,
                               lo=0.0, hi=50.0) == 50.0


def test_the_clustering_premium_is_near_zero_on_an_independent_series(series):
    """The diagnostic must not cry wolf on a series that genuinely has no clustering."""
    prem = pa.clustering_premium(_twin(), series, block=10, reps=200)
    assert abs(prem["pass_premium"]) < 0.10
    assert abs(prem["paid_premium"]) < 0.10


def test_the_clustering_premium_fires_when_the_series_is_dependent():
    """It must react to dependence - but the SIGN is not assumed, and here it is negative.

    Clustering raises the variance of cumulative P&L. Against the drawdown barrier that
    hurts; against a profit target only $3,000 away it helps, and on this AR(0.9) series the
    second effect wins - the block bootstrap passes MORE often than IID. That is why
    `clustering_premium` is documented as a sensitivity with no assumed direction: an earlier
    version of this test asserted a positive premium and was simply wrong about the finance.
    """
    rng = np.random.default_rng(2)
    x = np.zeros(300)
    for i in range(1, 300):
        x[i] = 0.9 * x[i - 1] + rng.normal(0, 120)
    days = _days(x + 70)
    prem = pa.clustering_premium(_twin(), days, block=30, reps=250)
    assert abs(prem["pass_premium"]) > 0.05, (
        f"dependence this strong must move the answer, got {prem['pass_premium']:+.3f}")
    assert prem["pass_premium"] < 0, (
        "on this series the clustered resample passes more often, not less - the finding "
        "the docstring records")


# ======================================================================================
# SIZE
# ======================================================================================

def test_the_size_sweep_optimum_is_interior_not_at_an_end():
    """Against an absorbing barrier, more size is not monotonically better or worse.

    Sharpe is scale-invariant and cannot find this optimum, which is the whole argument for
    optimising the prop-firm objective instead.
    """
    rng = np.random.default_rng(11)
    days = _days(rng.normal(55, 350, size=150))
    sweep = pa.size_sweep(_twin(), days, reps=200)
    best = pa.best_size(sweep)
    sizes = sorted(sweep)
    assert best not in (sizes[0], sizes[-1]), f"optimum at an endpoint ({best}); not interior"
    assert sweep[sizes[-1]]["p_liquidated"] > sweep[sizes[0]]["p_liquidated"], (
        "bigger size must raise liquidation risk")


def test_the_paid_optimum_and_the_gross_optimum_can_differ():
    """Which is why the objective has to be named rather than assumed.

    200 reps could not resolve this and the two optima collided on Monte Carlo noise alone
    (paid 0.650 at 0.75x against 0.640 at 0.5x - a 1-point gap on a 200-path estimate). The
    separation is real and stable from about 600 reps: maximising CASH WITHDRAWN wants more
    size than maximising the chance of withdrawing anything at all, because the extra size
    that raises the eventual payout also raises the chance of never reaching one.
    """
    rng = np.random.default_rng(11)
    days = _days(rng.normal(55, 350, size=150))
    sweep = pa.size_sweep(_twin(), days, reps=800)
    paid, gross = pa.best_size(sweep, "p_first_payout"), pa.best_size(sweep, "mean_gross")
    assert paid != gross
    assert paid < gross, (
        f"the payout-probability optimum ({paid}) should be the more cautious of the two, "
        f"not larger than the cash optimum ({gross})")


def test_best_size_breaks_ties_toward_the_smaller_size():
    sweep = {0.5: {"p_first_payout": 0.8}, 1.0: {"p_first_payout": 0.8}}
    assert pa.best_size(sweep) == 0.5


def test_scaling_multiplies_every_session():
    days = _days([100.0, -200.0])
    assert [d.pnl for d in pa.scaled(days, 2.0)] == [200.0, -400.0]
    with pytest.raises(ValueError):
        pa.scaled(days, 0.0)


def test_with_scenario_copies_a_twin_and_rejects_unknown_attributes():
    t = _twin()
    clone = pa.with_scenario(t, strict_path=False)
    assert clone.strict_path is False and t.strict_path is True
    with pytest.raises(AttributeError):
        pa.with_scenario(t, not_a_field=1)
