"""Hand-checkable arithmetic for path reconstruction. Every number here is computed by hand.

WHY THIS FILE EXISTS
--------------------
An audit found a synthetic worst mark of about -$900 arriving at the twin as a resampled
path of about -$51,947. It reproduced. `paths._rebuild` used to lay a resampled P&L onto an
unrelated template session's intraday shape and rescale it by `new_pnl / template_pnl` - an
UNBOUNDED ratio. A template session closing near flat is a divide-by-almost-zero, and it also
flips sign when the ratio is negative, so a real -$900 trough could come back as a +$90,000
peak with the day reported as having had no drawdown at all. On a 60-session fixture whose
worst mark anywhere was -$900 the median resampled path reached -$476,410.

Pass probability is the mission's objective function and it is computed on these paths, so
the reconstruction is tested against arithmetic rather than against recorded output. Nothing
below asserts a number that was read off a previous run; every expected value is written out
with the sum that produces it.
"""
from __future__ import annotations

import datetime as dt

import pytest

from quant_brain.markets.futures_cme import paths as pa
from quant_brain.markets.futures_cme import twin as tw

MONDAY = dt.date(2026, 1, 5)


# ======================================================================================
# FIXTURES - exactly representable, with a closed form for every statistic
# ======================================================================================

def _path(pnl: float) -> tuple[float, float, float]:
    """Three marks: half the close, a trough of -(|close| + 100), then the close.

    Chosen so `worst_mark` has a closed form - exactly `-(abs(pnl) + 100)` - and so every
    value is a binary-exact double, which lets the sums below be asserted with `==`.
    """
    return (0.5 * pnl, -abs(pnl) - 100.0, pnl)


def _sessions(pnls, start: dt.date = MONDAY) -> list[tw.TwinDay]:
    out, day = [], start
    for p in pnls:
        while day.weekday() >= 5:
            day += dt.timedelta(days=1)
        out.append(tw.TwinDay(day=day, pnl=float(p), path=_path(float(p))))
        day += dt.timedelta(days=1)
    return out


def _scaled_sessions(pnls, k: float, start: dt.date = MONDAY) -> list[tw.TwinDay]:
    """The same sessions with every dollar figure - close AND every mark - multiplied."""
    return [tw.TwinDay(day=d.day, pnl=d.pnl * k, path=tuple(m * k for m in d.path))
            for d in _sessions(pnls, start)]


def _equity_curve(days) -> list[float]:
    """Every intraday mark of a multi-day path, as equity relative to the opening balance.

    `TwinDay.path` is measured from the day's OPEN, so reconstructing the account curve means
    rebasing each day onto the running total. Getting this wrong in either direction - not
    rebasing, or rebasing and then adding the close again - is one of the ways a path
    reconstruction goes wrong, so it is written here once and asserted against.
    """
    curve: list[float] = []
    running = 0.0
    for d in days:
        curve.extend(running + m for m in d.path)
        running += d.pnl
    return curve


def _opening_equity(days) -> list[float]:
    out, running = [], 0.0
    for d in days:
        out.append(running)
        running += d.pnl
    return out


def _max_drawdown(curve) -> float:
    """Peak-to-trough on the reconstructed curve, with the peak starting at the opening
    balance - which is what a trailing MLL actually does from day one."""
    peak = worst = 0.0
    for x in curve:
        peak = max(peak, x)
        worst = max(worst, peak - x)
    return worst


UNIQUE = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0, 110.0, 120.0]
MIXED = [100.0, -250.0, 375.0, 0.0, -50.0, 625.0, -800.0, 25.0]


# ======================================================================================
# ORDER AND SIGN
# ======================================================================================

def test_a_block_is_consecutive_original_days_in_their_original_order():
    """A block bootstrap must emit `block` CONSECUTIVE days, not `block` copies of one."""
    days = _sessions(UNIQUE)
    for p in pa.moving_block(days, block=4, reps=25, seed=0):
        assert len(p) == 12
        for c in range(0, 12, 4):
            chunk = [d.pnl for d in p[c:c + 4]]
            i = UNIQUE.index(chunk[0])
            assert chunk == UNIQUE[i:i + 4], (
                f"block at {c} is {chunk}, not four consecutive original sessions")
            assert len(set(chunk)) == 4, "a block of copies is not a block"


def test_a_resampled_session_keeps_its_own_intraday_path():
    """The whole session travels. Nothing is rescaled onto another day's shape."""
    days = _sessions(MIXED)
    known = {d.pnl: d.path for d in days}
    for p in pa.moving_block(days, block=3, reps=30, seed=1):
        for d in p:
            assert d.pnl in known
            assert d.path == known[d.pnl], "the day arrived wearing another day's path"
            assert d.path == _path(d.pnl)


def test_signs_are_preserved():
    days = _sessions(MIXED)
    sign = {d.pnl: (d.pnl > 0) - (d.pnl < 0) for d in days}
    for maker in (lambda: pa.moving_block(days, block=3, reps=20, seed=2),
                  lambda: pa.stationary_bootstrap(days, mean_block=3, reps=20, seed=2),
                  lambda: pa.iid(days, reps=20, seed=2)):
        for p in maker():
            for d in p:
                assert (d.pnl > 0) - (d.pnl < 0) == sign[d.pnl]
                assert d.path[-1] == d.pnl, "the path must close where the day closed"


def test_dates_come_out_ordered_and_on_weekdays():
    days = _sessions(UNIQUE)
    for p in pa.moving_block(days, block=5, reps=10, seed=3, length=31):
        dates = [d.day for d in p]
        assert dates == sorted(dates) and len(set(dates)) == len(dates)
        assert all(d.weekday() < 5 for d in dates)


# ======================================================================================
# CUMULATIVE EQUITY
# ======================================================================================

def test_terminal_equity_is_exactly_the_sum_of_the_resampled_days():
    """No double counting: the close is in the path, and the path is rebased once."""
    days = _sessions(MIXED)
    for p in pa.moving_block(days, block=3, reps=40, seed=4):
        curve = _equity_curve(p)
        assert curve[-1] == sum(d.pnl for d in p)
        # And the same total reached the other way, mark by mark from the running open.
        assert curve[-1] == _opening_equity(p)[-1] + p[-1].pnl


def test_each_day_opens_where_the_previous_day_closed():
    days = _sessions(MIXED)
    for p in pa.moving_block(days, block=4, reps=20, seed=5):
        curve, opens = _equity_curve(p), _opening_equity(p)
        for i, o in enumerate(opens):
            assert curve[i * 3 + 2] == o + p[i].pnl
            if i:
                assert o == curve[(i - 1) * 3 + 2], "a day was not rebased onto the running total"


def test_a_hand_written_three_day_path_reconstructs_to_numbers_written_down_here():
    """The whole reconstruction on a fixture small enough to check on paper.

        day A  close +100  marks  +40,  -60, +100
        day B  close -300  marks  -50, -420, -300
        day C  close +200  marks  -30, +150, +200

        opens:   A 0,  B +100,  C -200
        curve:  +40, -60, +100 | +50, -320, -200 | -230, -50, 0
        peak:   +40, +40, +100 | +100, +100, +100 | +100, +100, +100
        dd:       0, 100,    0 |   50,  420,  300 |  330,  150, 100

        terminal equity  =  100 - 300 + 200  =  0
        worst mark       =  100 - 420        =  -320
        max drawdown     =  100 - (-320)     =  420
    """
    d = [tw.TwinDay(day=MONDAY, pnl=100.0, path=(40.0, -60.0, 100.0)),
         tw.TwinDay(day=MONDAY + dt.timedelta(days=1), pnl=-300.0,
                    path=(-50.0, -420.0, -300.0)),
         tw.TwinDay(day=MONDAY + dt.timedelta(days=2), pnl=200.0,
                    path=(-30.0, 150.0, 200.0))]
    curve = _equity_curve(d)
    assert curve == [40.0, -60.0, 100.0, 50.0, -320.0, -200.0, -230.0, -50.0, 0.0]
    assert curve[-1] == 0.0
    assert min(curve) == -320.0
    assert _max_drawdown(curve) == 420.0

    # block == n leaves the bootstrap exactly one draw, so the resample IS the fixture and
    # the same three numbers must survive the round trip through `moving_block`.
    for p in pa.moving_block(d, block=3, reps=5, seed=0):
        again = _equity_curve(p)
        assert again == curve
        assert _max_drawdown(again) == 420.0


# ======================================================================================
# THE DEFECT ITSELF - the worst mark cannot be a multiple of any real loss
# ======================================================================================

def test_the_worst_mark_is_a_real_days_worst_mark_sitting_on_the_running_equity():
    days = _sessions(MIXED)
    real = {d.worst_mark for d in days}
    for p in pa.moving_block(days, block=3, reps=50, seed=6):
        curve, opens = _equity_curve(p), _opening_equity(p)
        worst = min(curve)
        # A resample invents nothing: every reconstructed session's own worst mark has to be
        # the worst mark of one of the sessions that actually happened.
        assert {d.worst_mark for d in p} <= real
        # And the deepest point of the ACCOUNT is the deepest point of some one session,
        # measured from the equity that session opened with. Nothing else can produce it.
        assert worst == min(o + d.worst_mark for o, d in zip(opens, p, strict=True))
        assert worst >= min(d.worst_mark for d in p) + sum(min(0.0, d.pnl) for d in p)


def test_the_reconstructed_worst_mark_can_never_be_a_multiple_of_the_worst_session():
    """The audit's symptom, as a bound: a -$900 worst session cannot become -$51,947.

    Each day contributes its own excursion once, so the deepest the account can go is
    everything that could go wrong added together - the sum of the losing closes plus one
    session's excursion. That is a LINEAR bound in the number of sessions, and the ratio
    rescale broke it by a factor of hundreds on a single day.
    """
    days = _sessions(MIXED)
    deepest_session = min(d.worst_mark for d in days)          # -900.0: -(800 + 100)
    assert deepest_session == -900.0
    for p in pa.moving_block(days, block=3, reps=100, seed=7):
        worst = min(_equity_curve(p))
        bound = sum(min(0.0, d.pnl) for d in p) + deepest_session
        assert worst >= bound, f"worst {worst:,.0f} is past the arithmetic floor {bound:,.0f}"
        assert worst / deepest_session <= len(p), (
            "the worst mark scales with the number of losing sessions, never with a ratio")


def test_a_near_flat_session_cannot_explode_the_reconstruction():
    """The exact shape of the defect, isolated to one day.

    A real session that closed at +$1.00 having been -$900 down. Under the old ratio rescale,
    re-closing it at -$100 multiplied its path by -100: the -$900 trough became +$90,000 and
    the day reported no drawdown whatever. Both halves are asserted against here.
    """
    flat = tw.TwinDay(day=MONDAY, pnl=1.0, path=(-900.0, 1.0))
    out = pa._rebuild([flat], [-100.0])[0]
    assert out.pnl == -100.0
    # delta = -101, accrued at 1/2 and 2/2: (-900 - 50.5, 1 - 101).
    assert out.path == pytest.approx((-950.5, -100.0))
    assert out.worst_mark == pytest.approx(-950.5)
    assert min(out.path) < 0.0, "a session that was $900 down must still show a drawdown"
    assert abs(min(out.path)) < 10 * abs(min(flat.path)), (
        f"the trough moved from {min(flat.path):,.0f} to {min(out.path):,.0f} - "
        "that is a ratio blow-up, not a re-close")


def test_a_whole_series_of_near_flat_closes_stays_inside_its_own_worst_mark():
    """The audit's fixture in miniature: real -$900 excursions behind near-flat closes."""
    days = [tw.TwinDay(day=MONDAY + dt.timedelta(days=i), pnl=p, path=(-900.0, p))
            for i, p in enumerate([0.5, -1.0, 2.0, 0.25, -0.5, 1.0])]
    assert min(d.worst_mark for d in days) == -900.0
    worsts = [min(_equity_curve(p)) for p in pa.moving_block(days, block=2, reps=150, seed=0)]
    # Six sessions, none closing further than $2 from flat, so the account can never be more
    # than one session's excursion plus a couple of dollars under water.
    assert min(worsts) >= -900.0 - 4.0
    assert max(worsts) <= -900.0 + 4.0


# ======================================================================================
# DETERMINISM AND SHAPE
# ======================================================================================

def test_a_seeded_ordering_is_identical_across_runs():
    days = _sessions(MIXED)
    for maker in (lambda s: pa.moving_block(days, block=3, reps=6, seed=s),
                  lambda s: pa.stationary_bootstrap(days, mean_block=3, reps=6, seed=s),
                  lambda s: pa.iid(days, reps=6, seed=s)):
        a, b, c = maker(9), maker(9), maker(10)
        assert [[d.pnl for d in p] for p in a] == [[d.pnl for d in p] for p in b]
        assert [[d.path for d in p] for p in a] == [[d.path for d in p] for p in b]
        assert [[d.pnl for d in p] for p in a] != [[d.pnl for d in p] for p in c]


def test_the_number_of_days_out_equals_the_number_requested():
    days = _sessions(UNIQUE)
    n = len(days)
    makers = (lambda ln: pa.moving_block(days, block=5, reps=3, seed=0, length=ln),
              lambda ln: pa.stationary_bootstrap(days, mean_block=5, reps=3, seed=0, length=ln),
              lambda ln: pa.iid(days, reps=3, seed=0, length=ln))
    for length in (None, 1, 5, 12, 13, 31, 60):
        want = n if length is None else length
        for maker in makers:
            out = maker(length)
            assert len(out) == 3
            assert all(len(p) == want for p in out), f"asked for {want} days"
            assert all(d.path for p in out for d in p), "a day with no path is unrunnable"


def test_resampling_with_replacement_does_not_multiply_the_length():
    """Drawing 12 blocks of 4 from 12 days must still return 12 days, not 48."""
    days = _sessions(UNIQUE)
    assert all(len(p) == 12 for p in pa.moving_block(days, block=4, reps=5, seed=0))


def test_a_pinned_prefix_keeps_its_own_paths_and_the_requested_length():
    days = _sessions(MIXED)
    head = [(d.pnl, d.path) for d in days[:3]]
    for p in pa.resample_with_prefix(days, pin=3, block=2, reps=20, seed=0):
        assert len(p) == len(days)
        assert [(d.pnl, d.path) for d in p[:3]] == head


# ======================================================================================
# THE SCALE TEST
# ======================================================================================

def test_multiplying_every_input_by_ten_multiplies_every_output_by_exactly_ten():
    """A unit conversion anywhere in the reconstruction fails this and little else does.

    Every reconstruction primitive is homogeneous of degree one: ten times the contracts is
    ten times the close, ten times every intraday mark, ten times the drawdown. The fixture
    values are binary-exact doubles so this is asserted with `==`, not a tolerance.
    """
    one = _sessions(MIXED)
    ten = _scaled_sessions(MIXED, 10.0)

    a = pa.moving_block(one, block=3, reps=15, seed=11)
    b = pa.moving_block(ten, block=3, reps=15, seed=11)
    assert len(a) == len(b)
    for pa_, pb in zip(a, b, strict=True):
        assert [d.pnl * 10.0 for d in pa_] == [d.pnl for d in pb]
        assert [tuple(m * 10.0 for m in d.path) for d in pa_] == [d.path for d in pb]
        ca, cb = _equity_curve(pa_), _equity_curve(pb)
        assert [x * 10.0 for x in ca] == cb
        assert min(ca) * 10.0 == min(cb)                       # worst mark
        assert ca[-1] * 10.0 == cb[-1]                         # terminal equity
        assert _max_drawdown(ca) * 10.0 == _max_drawdown(cb)   # max drawdown
        assert sum(d.pnl for d in pa_) * 10.0 == sum(d.pnl for d in pb)

    # The transforms too, since they reconstruct paths as well.
    assert [d.path for d in pa.scaled(one, 2.0)] == [
        tuple(m / 10.0 for m in d.path) for d in pa.scaled(ten, 2.0)]
    loss = pa.ScaleLosses(name="x", describe="", factor=1.5)
    assert [d.path for d in loss.apply(ten)] == [
        tuple(m * 10.0 for m in d.path) for d in loss.apply(one)]
    worst_first = pa.WorstRunFirst(name="x", describe="", window=3)
    assert [d.pnl for d in worst_first.apply(ten)] == [
        d.pnl * 10.0 for d in worst_first.apply(one)]
    # `_rebuild` is additive, so scaling the requested closes with the sessions scales it too.
    # Its linear accrual divides by the mark count, so this one is asserted to a tolerance:
    # 10*(m + d/3) and (10m + 10d/3) differ in the last bit. A unit error is a factor, not an
    # ULP, so 1e-12 is still far tighter than anything a conversion bug could hide in.
    big = [m for d in pa._rebuild(ten, [d.pnl * 10.0 - 2_500.0 for d in one]) for m in d.path]
    small = [m * 10.0 for d in pa._rebuild(one, [d.pnl - 250.0 for d in one]) for m in d.path]
    assert big == pytest.approx(small, rel=1e-12, abs=1e-9)


def test_a_fixed_dollar_cost_is_the_one_transform_that_must_not_scale():
    """The control for the test above: `AddCost` is denominated in dollars, not in size."""
    one, ten = _sessions(MIXED), _scaled_sessions(MIXED, 10.0)
    cost = pa.AddCost(name="x", describe="", per_day=25.0)
    assert [d.pnl for d in cost.apply(one)] == [d.pnl - 25.0 for d in one]
    assert [d.pnl for d in cost.apply(ten)] == [d.pnl - 25.0 for d in ten]


# ======================================================================================
# DEGENERATE CASE
# ======================================================================================

def test_an_all_zero_series_produces_zero_paths_zero_drawdown_and_no_breach():
    days = [tw.TwinDay(day=MONDAY + dt.timedelta(days=i), pnl=0.0, path=(0.0, 0.0, 0.0))
            for i in range(10)]
    twin = tw.TopstepTwin(50_000, profit_target=3_000.0)
    for maker in (lambda: pa.moving_block(days, block=3, reps=10, seed=0),
                  lambda: pa.stationary_bootstrap(days, mean_block=3, reps=10, seed=0),
                  lambda: pa.iid(days, reps=10, seed=0)):
        for p in maker():
            assert all(d.pnl == 0.0 for d in p)
            assert all(m == 0.0 for d in p for m in d.path)
            curve = _equity_curve(p)
            assert curve == [0.0] * (3 * len(p))
            assert _max_drawdown(curve) == 0.0
            r = twin.run(p)
            assert r.breach_day is None and r.breach_reason == ""
            assert r.final_balance == 50_000.0
            assert r.terminal is not tw.ts.TopstepStage.LIQUIDATED


def test_a_zero_close_with_a_real_excursion_still_shows_the_excursion():
    """The degenerate case that is NOT trivial: flat closes, violent intraday.

    This is the exact shape the old ratio rescale could not represent - it special-cased a
    zero close and lost the excursion entirely, or divided by it.
    """
    days = [tw.TwinDay(day=MONDAY + dt.timedelta(days=i), pnl=0.0, path=(-400.0, 0.0))
            for i in range(6)]
    for p in pa.moving_block(days, block=2, reps=20, seed=0):
        curve = _equity_curve(p)
        assert curve[-1] == 0.0
        assert min(curve) == -400.0
        assert _max_drawdown(curve) == 400.0
    shifted = pa._rebuild(days, [-100.0] * 6)
    assert all(d.pnl == -100.0 for d in shifted)
    assert shifted[0].path == pytest.approx((-450.0, -100.0))
    assert min(_equity_curve(shifted)) == pytest.approx(-950.0)   # -500 open, -450 mark
