"""What the selection lab guarantees, pinned.

The lab's whole value is that every strategy is measured the same way. So most of these tests
are about the MEASUREMENT rather than about any result: trade extraction against hand-computed
arithmetic, cost accounting that cannot drift, and the verdict ladder behaving mechanically
rather than tracking net profit.

The Monte Carlo precondition gets its own section. The brief forbids relying on the path
machinery unless it is independently verified, so the properties that verification established
are asserted here rather than left in a scratch file - in particular the additive re-lay, which
replaced a ratio version that could scale a near-flat session's excursion by an arbitrary
factor.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from quant_brain.research import strategy_lab as lab  # noqa: E402

CHEAP = lab.CostModel(round_turn_commission=2.0, tick_value=0.5, slippage_ticks=0.0)


def _times(n: int) -> pd.Series:
    base = dt.datetime(2026, 1, 5, 9, 30)
    return pd.Series([base + dt.timedelta(minutes=i) for i in range(n)])


# =====================================================================================
# TRADE EXTRACTION, AGAINST ARITHMETIC DONE BY HAND
# =====================================================================================

def test_a_single_long_earns_the_move_minus_one_round_turn():
    """Prices 100 -> 104 at multiplier 2 is $8 gross; one round turn at $2 leaves $6."""
    closes = np.array([100.0, 101.0, 102.0, 103.0, 104.0])
    pos = np.array([1.0, 1.0, 1.0, 1.0, 0.0])
    trades, eq = lab.extract_trades(
        pos, closes, _times(5), strategy="s", symbol="MNQ", session=dt.date(2026, 1, 5),
        multiplier=2.0, contracts=1, cost=CHEAP, atr_dollars=10.0)
    assert len(trades) == 1
    t = trades[0]
    assert t.direction == 1
    assert t.gross_pnl == pytest.approx(8.0)
    assert t.net_pnl == pytest.approx(6.0)
    assert t.exit_reason == lab.EXIT_SIGNAL_FLAT
    assert eq[-1] == pytest.approx(6.0)


def test_a_short_earns_the_fall():
    closes = np.array([100.0, 99.0, 98.0, 97.0])
    pos = np.array([-1.0, -1.0, -1.0, 0.0])
    trades, _ = lab.extract_trades(
        pos, closes, _times(4), strategy="s", symbol="MNQ", session=dt.date(2026, 1, 5),
        multiplier=2.0, contracts=1, cost=CHEAP, atr_dollars=10.0)
    assert trades[0].direction == -1
    assert trades[0].gross_pnl == pytest.approx(6.0)


def test_a_direct_reversal_is_two_trades_and_two_round_turns():
    """Long to short with no flat in between is two positions, so two round turns.

    Charging one would understate cost by half on any mechanism that flips rather than
    stands down, which is most of this library.
    """
    closes = np.array([100.0, 102.0, 104.0, 102.0, 100.0])
    pos = np.array([1.0, 1.0, -1.0, -1.0, 0.0])
    trades, eq = lab.extract_trades(
        pos, closes, _times(5), strategy="s", symbol="MNQ", session=dt.date(2026, 1, 5),
        multiplier=1.0, contracts=1, cost=CHEAP, atr_dollars=10.0)
    assert len(trades) == 2
    assert trades[0].exit_reason == lab.EXIT_SIGNAL_FLIP
    assert eq[-1] == pytest.approx(sum(t.gross_pnl for t in trades) - 2 * 2.0)


def test_a_position_open_at_the_bell_is_a_forced_flatten():
    closes = np.array([100.0, 101.0, 102.0])
    pos = np.array([1.0, 1.0, 1.0])
    trades, _ = lab.extract_trades(
        pos, closes, _times(3), strategy="s", symbol="MNQ", session=dt.date(2026, 1, 5),
        multiplier=1.0, contracts=1, cost=CHEAP, atr_dollars=10.0)
    assert len(trades) == 1
    assert trades[0].exit_reason == lab.EXIT_FORCED_FLATTEN


def test_mae_and_mfe_bracket_the_trades_outcome():
    """A trade that goes against you before working must record it."""
    closes = np.array([100.0, 97.0, 96.0, 103.0, 105.0])
    pos = np.array([1.0, 1.0, 1.0, 1.0, 0.0])
    trades, _ = lab.extract_trades(
        pos, closes, _times(5), strategy="s", symbol="MNQ", session=dt.date(2026, 1, 5),
        multiplier=1.0, contracts=1, cost=CHEAP, atr_dollars=10.0)
    t = trades[0]
    assert t.mae < 0 < t.mfe
    assert t.mae <= t.gross_pnl <= t.mfe


def test_a_flat_signal_produces_no_trades_and_no_costs():
    closes = np.linspace(100, 110, 20)
    trades, eq = lab.extract_trades(
        np.zeros(20), closes, _times(20), strategy="s", symbol="MNQ",
        session=dt.date(2026, 1, 5), multiplier=1.0, contracts=1, cost=CHEAP,
        atr_dollars=10.0)
    assert trades == []
    assert eq[-1] == pytest.approx(0.0)


def test_contracts_scale_gross_but_costs_scale_too():
    closes = np.array([100.0, 105.0, 105.0])
    pos = np.array([1.0, 0.0, 0.0])
    one, _ = lab.extract_trades(pos, closes, _times(3), strategy="s", symbol="MNQ",
                                session=dt.date(2026, 1, 5), multiplier=1.0, contracts=1,
                                cost=CHEAP, atr_dollars=10.0)
    ten, _ = lab.extract_trades(pos, closes, _times(3), strategy="s", symbol="MNQ",
                                session=dt.date(2026, 1, 5), multiplier=1.0, contracts=10,
                                cost=CHEAP, atr_dollars=10.0)
    assert ten[0].gross_pnl == pytest.approx(one[0].gross_pnl * 10)
    assert ten[0].net_pnl == pytest.approx(one[0].net_pnl * 10)


def test_slippage_is_charged_once_per_round_turn_not_once_per_leg():
    """The commonest arithmetic slip in a harness like this."""
    c = lab.CostModel(round_turn_commission=0.0, tick_value=10.0, slippage_ticks=1.0)
    closes = np.array([100.0, 100.0, 100.0])
    pos = np.array([1.0, 0.0, 0.0])
    trades, _ = lab.extract_trades(pos, closes, _times(3), strategy="s", symbol="MNQ",
                                   session=dt.date(2026, 1, 5), multiplier=1.0,
                                   contracts=1, cost=c, atr_dollars=10.0)
    assert trades[0].net_pnl == pytest.approx(-10.0)


# =====================================================================================
# PORTFOLIO METRICS
# =====================================================================================

def test_profit_factor_with_no_losses_is_a_sentinel_not_a_flattering_number():
    """An undefined profit factor printed as a large finite number corrupts a ranking."""
    tr = [lab.Trade("s", "MNQ", _times(2)[0], _times(2)[1], 0, 1, 1, 1, 1.0, 2.0,
                    5.0, 0.0, 0.0, 5.0, 0.0, 5.0, 1.0, "x", 1, dt.date(2026, 1, 5))]
    sr = [lab.SessionResult(dt.date(2026, 1, 5), "MNQ", "s", 1, 5.0, 0.0, 5.0,
                            0.0, 5.0, 0.0, 0, False, 0.5, (5.0,))]
    p = lab.summarise_portfolio(tr, sr, strategy="s", symbol="MNQ")
    assert not np.isfinite(p.profit_factor)


def test_drawdown_is_measured_on_the_cumulative_curve():
    sr = [lab.SessionResult(dt.date(2026, 1, d), "MNQ", "s", 1, v, 0.0, v, 0.0, 0.0, 0.0,
                            0, False, 0.5, (v,))
          for d, v in zip(range(5, 10), [100.0, -300.0, -200.0, 50.0, 400.0],
                          strict=True)]
    p = lab.summarise_portfolio([], sr, strategy="s", symbol="MNQ")
    assert p.max_drawdown == pytest.approx(-500.0)
    assert p.consec_losing_days == 2
    assert p.net_pnl == pytest.approx(50.0)


def test_an_empty_run_does_not_crash_or_invent_numbers():
    p = lab.summarise_portfolio([], [], strategy="s", symbol="MNQ")
    assert p.n_sessions == 0 and p.net_pnl == 0.0 and p.sharpe == 0.0


# =====================================================================================
# THE MONTE CARLO PRECONDITION
# =====================================================================================

def _day(i: int, pnl: float, dip: float):
    from quant_brain.markets.futures_cme.twin import TwinDay
    path = np.concatenate([np.linspace(0, dip, 25), np.linspace(dip, pnl, 25)])
    return TwinDay(day=dt.date(2025, 1, 6) + dt.timedelta(days=i), pnl=float(pnl),
                   path=tuple(float(x) for x in path), traded=True)


def test_the_re_lay_is_additive_and_lands_exactly_on_target():
    from quant_brain.markets.futures_cme import paths as P
    d = _day(0, 100.0, -400.0)
    for target in (0.0, 500.0, -250.0):
        s = P._shifted(d, target)
        assert s.pnl == pytest.approx(target)
        moved = max(abs(a - b) for a, b in zip(s.path, d.path, strict=True))
        assert moved <= abs(target - d.pnl) + 1e-9


def test_a_near_flat_session_cannot_have_its_excursion_scaled():
    """The specific defect the brief warns about: a ratio re-lay on a ~0 close explodes."""
    from quant_brain.markets.futures_cme import paths as P
    from quant_brain.markets.futures_cme.twin import TwinDay
    flat = TwinDay(day=dt.date(2025, 1, 6), pnl=0.01,
                   path=tuple(np.linspace(0, -500, 40)) + (0.01,), traded=True)
    s = P._shifted(flat, 1000.0)
    assert min(s.path) > -600.0, "the excursion was scaled, not shifted"


def test_resampling_carries_whole_sessions_untouched():
    from quant_brain.markets.futures_cme import paths as P
    days = [_day(i, 10.0 * i, -50.0 * (i + 1)) for i in range(6)]
    laid = P._lay_out(days, [3, 3, 0], [dt.date(2026, 2, d) for d in (2, 3, 4)])
    assert [x.pnl for x in laid] == [days[3].pnl, days[3].pnl, days[0].pnl]
    assert laid[0].path == days[3].path


def test_resampling_preserves_the_pnl_distribution():
    from quant_brain.markets.futures_cme import paths as P
    rng = np.random.default_rng(4)
    days = [_day(i, float(rng.normal(0, 200)), -float(abs(rng.normal(300, 100))))
            for i in range(80)]
    out = P.iid(days, reps=200, seed=1)
    src = np.array([d.pnl for d in days])
    got = np.array([d.pnl for p in out for d in p])
    assert abs(got.mean() - src.mean()) < 0.1 * src.std()
    assert set(np.round(got, 6)) <= set(np.round(src, 6))


# =====================================================================================
# THE LAB'S FINDINGS
# =====================================================================================

SCORES = REPO / "research" / "lab_scorecards.csv"
pytestmark_data = pytest.mark.skipif(
    not SCORES.exists(), reason="run scripts/strategy_lab_run.py then _report.py")


@pytestmark_data
def test_the_verdict_is_not_a_function_of_net_pnl():
    """The ladder must be able to reject a profitable cell and not-reject an unprofitable one,
    or it is a P&L ranking wearing a verdict's name."""
    d = pd.read_csv(SCORES)
    rejected_profitable = d[(d.verdict == "REJECT") & (d.net_pnl > 0)]
    assert len(rejected_profitable) > 0, (
        "no profitable cell was rejected; the verdict may have collapsed to net P&L")


@pytestmark_data
def test_almost_nothing_clears_the_topstep_barrier():
    d = pd.read_csv(SCORES)
    assert (d.dd_over_mll < 1).sum() <= 20, (
        "many more cells now fit inside the $2,000 MLL than when the lab ran; re-check the "
        "cost model and the contract scaling before believing it")


@pytestmark_data
def test_no_cell_reached_paper_or_combine_candidate():
    """If this ever fails it is good news and must be investigated, not celebrated."""
    d = pd.read_csv(SCORES)
    n = int(d.verdict.isin(["PAPER CANDIDATE", "COMBINE CANDIDATE"]).sum())
    assert n == 0, (
        f"{n} cells now reach paper/Combine candidate. Verify the cost model, the barrier "
        f"test and the multiplicity accounting before acting on it.")
