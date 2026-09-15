"""Adversarial forensics on the backtest engine. These tests exist to FIND bugs, not confirm.

The organising principle is that a test which calls the same code path the engine calls cannot
catch an error in what that path was supposed to mean. So wherever practical the expected
value here is either computed by hand and written into the test as a literal, or produced by
`quant_brain.research.reference_ledger`, which shares no code with the engine.

The suite is grouped by the attack it mounts:

    LEAKAGE       corrupt the future and assert the past does not move
    FILLS         demand a price the bar never traded and assert refusal
    CONTRACT MATH hand-computed tick and point values per instrument
    ACCOUNTING    the ledger, the equity curve and the cost total must be the same money
    SESSION       the flatten must happen, must cost, and must appear in the ledger
    ADVERSARIAL   degenerate and malformed input

A test that passes here is not proof the engine is right. A test that fails is proof it is
wrong, which is the more useful direction.
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

import futures_discover as fd  # noqa: E402

from quant_brain.research import exits as X  # noqa: E402
from quant_brain.research import strategy_lab as lab  # noqa: E402
from quant_brain.research.reference_ledger import (  # noqa: E402
    reference_drawdown,
    reference_pnl_one_trade,
    run_reference,
)


def _sa(pos, closes, mult=2.0, ct=1, rt=1.72):
    return fd.session_accounting(np.asarray(pos, dtype=float),
                                 np.asarray(closes, dtype=float),
                                 multiplier=mult, contracts=ct, round_turn_cost=rt)


# =====================================================================================
# INDEPENDENT RECONCILIATION  (Phase 22)
# =====================================================================================

CASES = [
    ("flat", [0, 0, 0, 0, 0], [100, 101, 102, 103, 104]),
    ("long all session", [1, 1, 1, 1, 1], [100, 101, 102, 103, 104]),
    ("short all session", [-1, -1, -1, -1, -1], [100, 101, 102, 103, 104]),
    ("exit mid", [1, 1, 0, 0, 0], [100, 102, 104, 103, 101]),
    ("direct reversal", [1, 1, -1, -1, 0], [100, 102, 104, 102, 100]),
    ("in-out-in", [1, 0, 1, 0, 1], [100, 101, 102, 103, 104]),
    ("losing long", [1, 1, 1, 0, 0], [100, 99, 98, 97, 96]),
    ("open at bell", [0, 0, 1, 1, 1], [100, 101, 102, 103, 110]),
]


#: `session_accounting` accounts whatever position series it is handed and has NO entry
#: policy - the "no new position on the final bar" rule lives in the runner and in the
#: reference. Reconciling the two therefore requires disabling the reference's cutoff, and
#: saying so here rather than letting a future reader think the low-level function enforces it.
NO_CUTOFF = 10**9


@pytest.mark.parametrize("name,pos,closes", CASES)
def test_engine_reconciles_with_an_independent_loop_implementation(name, pos, closes):
    """The vectorised engine against a plain-Python ledger that shares none of its code."""
    path, turns, gross = _sa(pos, closes)
    ref = run_reference(list(pos), list(closes), multiplier=2.0, contracts=1,
                        round_turn_cost=1.72, last_entry_bar=NO_CUTOFF)
    assert float(path[-1]) == pytest.approx(ref.net_pnl, abs=1e-9), name
    assert turns == pytest.approx(ref.round_turns, abs=1e-9), name
    assert gross == pytest.approx(ref.gross_pnl, abs=1e-9), name


@pytest.mark.parametrize("mult,ct,rt", [(2.0, 1, 1.72), (50.0, 1, 16.28),
                                        (5.0, 10, 24.70), (20.0, 3, 41.34)])
def test_reconciliation_holds_at_every_multiplier_and_size(mult, ct, rt):
    pos = [1, 1, -1, -1, 0, 1, 1]
    closes = [100, 103, 101, 99, 104, 102, 106]
    path, turns, gross = _sa(pos, closes, mult=mult, ct=ct, rt=rt)
    ref = run_reference(pos, closes, multiplier=mult, contracts=ct, round_turn_cost=rt,
                        last_entry_bar=NO_CUTOFF)
    assert float(path[-1]) == pytest.approx(ref.net_pnl, abs=1e-7)
    assert gross == pytest.approx(ref.gross_pnl, abs=1e-7)


# =====================================================================================
# LEAKAGE  (Phase 2)
# =====================================================================================

def test_corrupting_the_future_does_not_move_the_past():
    """The single most important test in the suite.

    Run the engine, then rewrite every bar after index k to an absurd value and run again.
    The equity path up to and including k must be byte-identical. Anything that moves is
    reading forward.
    """
    rng = np.random.default_rng(3)
    n = 200
    closes = 100 + np.cumsum(rng.normal(0, 0.5, n))
    pos = np.sign(rng.normal(0, 1, n))
    k = 120
    base, _, _ = _sa(pos, closes, mult=2.0, ct=1, rt=1.72)
    poisoned = closes.copy()
    poisoned[k + 1:] = 1e6                       # absurd, and profitable if leaked
    after, _, _ = _sa(pos, poisoned, mult=2.0, ct=1, rt=1.72)
    # path index j holds P&L through bar j+1, so bars up to k are represented up to index k-1
    assert np.allclose(base[:k - 1], after[:k - 1]), (
        "the equity path before the corruption changed; the engine reads forward")


def test_a_wildly_profitable_future_cannot_make_an_earlier_bar_profitable():
    """Synthetic dataset where the future is absurdly good. A strategy that cannot see it
    must not benefit from it."""
    closes = np.concatenate([np.full(50, 100.0), np.full(50, 100000.0)])
    pos = np.concatenate([np.ones(49), np.zeros(51)])   # flat before the jump
    path, turns, gross = _sa(pos, closes, mult=1.0, ct=1, rt=0.0)
    assert gross == pytest.approx(0.0, abs=1e-9), (
        f"a flat-before-the-jump position earned {gross}; the jump leaked backwards")


def test_the_one_bar_lag_is_real():
    """Position at bar i must earn bar i+1's move, never bar i's own.

    Constructed so the two conventions give different answers: the position turns on exactly
    at the bar that already moved.
    """
    closes = [100.0, 110.0, 110.0, 110.0]
    pos = [0.0, 1.0, 1.0, 0.0]        # long from bar 1, after the +10 already happened
    _, _, gross = _sa(pos, closes, mult=1.0, ct=1, rt=0.0)
    assert gross == pytest.approx(0.0, abs=1e-9), (
        f"earned {gross} on a move that happened before the position existed")


def test_the_exit_simulator_cannot_see_past_its_own_exit_bar():
    c = np.array([100.0, 101.0, 102.0, 103.0, 104.0, 105.0])
    h = c + 0.5
    low = c - 0.5
    sig = np.ones(6)
    arch = X.ExitArchitecture("t2", time_stop_bars=2, use_invalidation=False)
    r1 = X.simulate_trade(c, h, low, sig, 0, 1, atr=99.0, arch=arch)
    c2, h2, l2 = c.copy(), h.copy(), low.copy()
    c2[3:] = 1e6
    h2[3:] = 1e6
    l2[3:] = 1e6
    r2 = X.simulate_trade(c2, h2, l2, sig, 0, 1, atr=99.0, arch=arch)
    assert r1.exit_bar == r2.exit_bar == 2
    assert r1.points == pytest.approx(r2.points)


# =====================================================================================
# FILLS  (Phase 4)
# =====================================================================================

def test_a_target_the_bar_never_reached_does_not_fill():
    """A buy target above the bar's high must not fill merely because the close is high."""
    c = np.array([100.0, 100.0, 100.0])
    h = np.array([100.0, 100.5, 100.5])          # never reaches 110
    low = np.array([100.0, 99.5, 99.5])
    arch = X.ExitArchitecture("far", stop_atr=100.0, target_r=1.0, use_invalidation=False)
    r = X.simulate_trade(c, h, low, np.ones(3), 0, 1, atr=10.0, arch=arch)
    assert r.reason != X.TARGET, "filled a target price the bar never traded through"


def test_a_stop_the_bar_never_reached_does_not_fill():
    c = np.array([100.0, 100.0, 100.0])
    h = np.array([100.5, 100.5, 100.5])
    low = np.array([99.5, 99.5, 99.5])           # never reaches 90
    arch = X.ExitArchitecture("far", stop_atr=1.0, target_r=100.0, use_invalidation=False)
    r = X.simulate_trade(c, h, low, np.ones(3), 0, 1, atr=10.0, arch=arch)
    assert r.reason != X.STOP


def test_an_ambiguous_bar_resolves_pessimistically_and_says_so():
    """Both levels inside one bar. The engine must take the stop AND flag the ambiguity -
    never silently choose the profitable side."""
    c = np.array([100.0, 100.0])
    h = np.array([100.0, 130.0])
    low = np.array([100.0, 70.0])
    arch = X.ExitArchitecture("amb", stop_atr=1.0, target_r=1.0, use_invalidation=False)
    r = X.simulate_trade(c, h, low, np.ones(2), 0, 1, atr=10.0, arch=arch)
    assert r.reason == X.STOP
    assert r.ambiguous is True
    assert r.points < 0


def test_a_target_fills_AT_the_target_price_and_never_better():
    """Caught by mutation testing: nothing defended the fill PRICE of a target.

    A bar can run far past the target and close beyond it. The fill is the target, not the
    close - crediting the close is the single most common optimistic-fill bug, and it is
    invisible in aggregate statistics because it only inflates the winners.
    """
    c = np.array([100.0, 128.0])
    h = np.array([100.0, 130.0])
    low = np.array([100.0, 99.0])
    arch = X.ExitArchitecture("t", stop_atr=1.0, target_r=2.0, use_invalidation=False)
    r = X.simulate_trade(c, h, low, np.ones(2), 0, 1, atr=5.0, arch=arch)
    assert r.reason == X.TARGET
    assert r.exit_price == pytest.approx(110.0), (
        f"target filled at {r.exit_price}, not the 110.0 target price")
    assert r.points == pytest.approx(10.0), "credited more than the target was worth"


def test_a_short_target_also_fills_at_the_target_and_never_better():
    c = np.array([100.0, 72.0])
    h = np.array([100.0, 101.0])
    low = np.array([100.0, 70.0])
    arch = X.ExitArchitecture("t", stop_atr=1.0, target_r=2.0, use_invalidation=False)
    r = X.simulate_trade(c, h, low, -np.ones(2), 0, -1, atr=5.0, arch=arch)
    assert r.reason == X.TARGET
    assert r.exit_price == pytest.approx(90.0)
    assert r.points == pytest.approx(10.0)


def test_a_stop_fills_AT_the_stop_and_never_better_on_a_gap():
    """A stop that gaps through must not be credited the close if the close recovered."""
    c = np.array([100.0, 99.0])
    h = np.array([100.0, 99.5])
    low = np.array([100.0, 80.0])          # gapped well through the stop
    arch = X.ExitArchitecture("s", stop_atr=1.0, target_r=99.0, use_invalidation=False)
    r = X.simulate_trade(c, h, low, np.ones(2), 0, 1, atr=5.0, arch=arch)
    assert r.reason == X.STOP
    assert r.exit_price == pytest.approx(95.0), (
        f"stop filled at {r.exit_price}; it must fill at the stop price, not the recovery")


def test_a_long_market_position_does_not_systematically_receive_the_bar_low():
    """The classic optimistic-fill signature. Over many random bars, a long entered at the
    close must average close-to-close, not low-to-close."""
    rng = np.random.default_rng(17)
    n = 400
    c = 100 + np.cumsum(rng.normal(0, 0.4, n))
    pos = np.ones(n)
    _, _, gross = _sa(pos, c, mult=1.0, ct=1, rt=0.0)
    expected = float(c[-1] - c[0])
    assert gross == pytest.approx(expected, abs=1e-6), (
        "a long held all session did not earn exactly close-to-close")


# =====================================================================================
# CONTRACT MATH  (Phase 6) — expected values computed by hand in the test
# =====================================================================================

CONTRACTS = [
    # symbol, tick size, tick value, point value(multiplier)
    ("ES", 0.25, 12.50, 50.0),
    ("MES", 0.25, 1.25, 5.0),
    ("NQ", 0.25, 5.00, 20.0),
    ("MNQ", 0.25, 0.50, 2.0),
]


@pytest.mark.parametrize("sym,tick,tick_value,mult", CONTRACTS)
def test_instrument_metadata_matches_the_exchange_specification(sym, tick, tick_value, mult):
    """Hand-written from the CME contract specs, not read from the engine."""
    from quant_brain.markets.futures_cme import instruments as inst
    spec = inst.get(sym).spec
    assert spec.tick == pytest.approx(tick), f"{sym} tick size"
    assert spec.tick_value == pytest.approx(tick_value), f"{sym} tick value"
    assert spec.multiplier == pytest.approx(mult), f"{sym} point value"
    assert spec.tick * spec.multiplier == pytest.approx(spec.tick_value), (
        f"{sym}: tick x multiplier must equal tick value")


@pytest.mark.parametrize("sym,tick,tick_value,mult", CONTRACTS)
def test_one_tick_moves_exactly_one_tick_value(sym, tick, tick_value, mult):
    """+1 tick long and -1 tick long, computed by hand."""
    entry = 5000.0
    g_up, _, _ = reference_pnl_one_trade(entry, entry + tick, +1, 1, mult, 0.0)
    g_dn, _, _ = reference_pnl_one_trade(entry, entry - tick, +1, 1, mult, 0.0)
    assert g_up == pytest.approx(tick_value)
    assert g_dn == pytest.approx(-tick_value)
    # and through the engine
    _, _, gross = _sa([1, 1, 0], [entry, entry + tick, entry + tick], mult=mult, ct=1, rt=0.0)
    assert gross == pytest.approx(tick_value), f"{sym}: engine one-tick value"


@pytest.mark.parametrize("sym,tick,tick_value,mult", CONTRACTS)
def test_one_point_moves_exactly_the_multiplier(sym, tick, tick_value, mult):
    _, _, gross = _sa([1, 1, 0], [5000.0, 5001.0, 5001.0], mult=mult, ct=1, rt=0.0)
    assert gross == pytest.approx(mult), f"{sym}: one point should be ${mult}"


@pytest.mark.parametrize("sym,tick,tick_value,mult", CONTRACTS)
def test_a_short_earns_the_mirror_of_a_long(sym, tick, tick_value, mult):
    up = [5000.0, 5010.0, 5010.0]
    _, _, long_g = _sa([1, 1, 0], up, mult=mult, ct=1, rt=0.0)
    _, _, short_g = _sa([-1, -1, 0], up, mult=mult, ct=1, rt=0.0)
    assert long_g == pytest.approx(-short_g)
    assert long_g == pytest.approx(10.0 * mult)


def test_the_micro_is_exactly_one_tenth_of_the_mini():
    from quant_brain.markets.futures_cme import instruments as inst
    for mini, micro in (("ES", "MES"), ("NQ", "MNQ")):
        a, b = inst.get(mini).spec, inst.get(micro).spec
        assert a.multiplier == pytest.approx(b.multiplier * 10), f"{mini}/{micro} multiplier"
        assert a.tick_value == pytest.approx(b.tick_value * 10), f"{mini}/{micro} tick value"
        assert a.tick == pytest.approx(b.tick), f"{mini}/{micro} tick size must match"


@pytest.mark.parametrize("n", [1, 2, 5, 10, 50])
def test_pnl_scales_exactly_linearly_in_contract_count(n):
    one, _, g1 = _sa([1, 1, 0], [100.0, 105.0, 105.0], mult=2.0, ct=1, rt=1.72)
    many, _, gn = _sa([1, 1, 0], [100.0, 105.0, 105.0], mult=2.0, ct=n, rt=1.72 * n)
    assert gn == pytest.approx(g1 * n)
    assert float(many[-1]) == pytest.approx(float(one[-1]) * n)


# =====================================================================================
# COST AND ACCOUNTING  (Phases 5, 7, 13)
# =====================================================================================

def test_the_cost_total_equals_round_turns_times_the_round_turn_cost():
    """Money must not appear or vanish. Three independent routes to the same number."""
    pos = [1, 1, -1, -1, 0, 1, 0]
    closes = [100, 102, 101, 99, 103, 105, 104]
    rt = 1.72
    path, turns, gross = _sa(pos, closes, mult=2.0, ct=1, rt=rt)
    implied_cost = gross - float(path[-1])
    assert implied_cost == pytest.approx(turns * rt, abs=1e-9)
    ref = run_reference(pos, closes, multiplier=2.0, contracts=1, round_turn_cost=rt,
                        last_entry_bar=NO_CUTOFF)
    assert ref.fees_paid == pytest.approx(turns * rt, abs=1e-9)


def test_no_trade_escapes_a_cost():
    """Every round turn charged, including the one that only exists because of the flatten."""
    for pos in ([1, 1, 1], [0, 1, 1], [1, -1, 1], [1, 0, 1]):
        closes = [100.0, 101.0, 102.0]
        path, turns, gross = _sa(pos, closes, mult=1.0, ct=1, rt=10.0)
        assert turns > 0, f"{pos} recorded zero round turns"
        assert gross - float(path[-1]) == pytest.approx(turns * 10.0, abs=1e-9)


def test_cost_is_charged_at_the_LEG_not_deferred_to_the_close():
    """Caught by mutation testing. The terminal P&L is identical either way, which is exactly
    why the suite missed it - but the intraday PATH is what `TwinDay(path=...)` hands to the
    Topstep twin, and the trailing MLL tracks peak equity intraday. Cost not yet charged is
    equity the twin believes the account has.

    A long opened at bar 0 in a flat market must already be down half a round turn on the
    first marked bar, not level.
    """
    closes = [100.0] * 6
    pos = [1.0, 1.0, 1.0, 1.0, 1.0, 0.0]
    rt = 10.0
    path, turns, gross = _sa(pos, closes, mult=1.0, ct=1, rt=rt)
    assert gross == pytest.approx(0.0), "flat market should have zero gross"
    assert float(path[0]) == pytest.approx(-rt / 2.0, abs=1e-9), (
        f"first marked bar shows {path[0]}; the opening leg's cost was not charged when it "
        f"was incurred")
    assert float(path[-1]) == pytest.approx(-rt, abs=1e-9), "both legs must be paid by the end"


def test_the_intraday_path_never_shows_money_the_account_does_not_have():
    """Generalisation of the above: at every bar, equity must be at most gross-so-far minus
    the cost of the legs already traded."""
    closes = [100.0, 101.0, 102.0, 101.0, 100.0, 100.0]
    pos = [1.0, 1.0, -1.0, -1.0, 0.0, 0.0]
    rt = 4.0
    path, _, _ = _sa(pos, closes, mult=1.0, ct=1, rt=rt)
    legs_by_bar = np.abs(np.diff(np.asarray(pos, dtype=float), prepend=0.0, append=0.0))
    paid = np.cumsum(legs_by_bar) * (rt / 2.0)
    step = np.diff(np.asarray(closes, dtype=float), prepend=closes[0])
    gross_running = np.cumsum(np.asarray(pos[:-1], dtype=float) * step[1:])
    for j in range(len(path)):
        assert float(path[j]) <= gross_running[j] - paid[j + 1] + 1e-9, (
            f"bar {j}: equity {path[j]} exceeds gross minus cost already incurred")


def test_mae_is_actually_recorded_for_a_trade_that_went_against_you():
    """Caught by mutation testing: nothing in this suite asserted MAE was populated, so an
    engine reporting MAE=0 for every trade passed. MAE drives the risk half of every
    scorecard."""
    closes = np.array([100.0, 90.0, 85.0, 110.0, 110.0])
    pos = np.array([1.0, 1.0, 1.0, 1.0, 0.0])
    times = pd.Series([dt.datetime(2026, 1, 5, 9, 30) + dt.timedelta(minutes=i)
                       for i in range(5)])
    cost = lab.CostModel(round_turn_commission=0.0, tick_value=0.5)
    trades, _ = lab.extract_trades(pos, closes, times, strategy="s", symbol="MNQ",
                                   session=dt.date(2026, 1, 5), multiplier=1.0,
                                   contracts=1, cost=cost, atr_dollars=1.0)
    assert len(trades) == 1
    t0 = trades[0]
    assert t0.mae < -1.0, f"MAE recorded as {t0.mae}; the trade went 15 points against"
    assert t0.mfe > 0.0, f"MFE recorded as {t0.mfe}"
    assert t0.mae <= t0.gross_pnl <= t0.mfe


def test_a_reversal_costs_two_round_turns_not_one():
    _, turns, _ = _sa([1, -1, 0], [100.0, 101.0, 102.0], mult=1.0, ct=1, rt=1.0)
    assert turns == pytest.approx(2.0)


def test_the_equity_curve_is_reconstructible_from_the_trade_ledger():
    """Phase 13's hard requirement. If the ledger cannot rebuild the curve it is invalid."""
    rng = np.random.default_rng(5)
    n = 120
    closes = 100 + np.cumsum(rng.normal(0, 0.3, n))
    pos = np.where(rng.normal(0, 1, n) > 0.6, 1.0, 0.0)
    times = pd.Series([dt.datetime(2026, 1, 5, 9, 30) + dt.timedelta(minutes=i)
                       for i in range(n)])
    cost = lab.CostModel(round_turn_commission=1.22, tick_value=0.5, slippage_ticks=0.0)
    trades, eq = lab.extract_trades(pos, closes, times, strategy="s", symbol="MNQ",
                                    session=dt.date(2026, 1, 5), multiplier=2.0,
                                    contracts=1, cost=cost, atr_dollars=10.0)
    assert float(eq[-1]) == pytest.approx(sum(t.net_pnl for t in trades), abs=1e-9), (
        "the equity curve does not equal the sum of the trade ledger")


def test_drawdown_is_path_dependent_and_matches_an_independent_loop():
    eq = [0.0, 100.0, -50.0, 20.0, -200.0, 300.0]
    worst, _, _ = reference_drawdown(eq)
    a = np.asarray(eq)
    vec = float((a - np.maximum.accumulate(a)).min())
    assert worst == pytest.approx(vec)
    assert worst == pytest.approx(-300.0), "peak 100 to trough -200 is a 300 drawdown"


# =====================================================================================
# SESSION AND FORCED FLATTEN  (Phase 8)
# =====================================================================================

def test_a_position_open_at_the_last_bar_is_always_flattened_and_charged():
    pos = [0.0, 1.0, 1.0, 1.0]
    closes = [100.0, 101.0, 102.0, 103.0]
    _, turns, _ = _sa(pos, closes, mult=1.0, ct=1, rt=2.0)
    assert turns == pytest.approx(1.0), "the flatten leg was not counted"
    ref = run_reference(pos, closes, multiplier=1.0, contracts=1, round_turn_cost=2.0,
                        last_entry_bar=NO_CUTOFF)
    assert ref.final_position == 0
    assert any(t.reason == "flatten" for t in ref.trades)


def test_the_flatten_appears_in_the_ledger_as_a_real_trade():
    times = pd.Series([dt.datetime(2026, 1, 5, 9, 30) + dt.timedelta(minutes=i)
                       for i in range(4)])
    cost = lab.CostModel(round_turn_commission=1.0, tick_value=0.5)
    trades, _ = lab.extract_trades(np.array([1.0, 1.0, 1.0, 1.0]),
                                   np.array([100.0, 101.0, 102.0, 103.0]), times,
                                   strategy="s", symbol="MNQ", session=dt.date(2026, 1, 5),
                                   multiplier=1.0, contracts=1, cost=cost, atr_dollars=1.0)
    assert len(trades) == 1
    assert trades[0].exit_reason == lab.EXIT_FORCED_FLATTEN
    assert trades[0].commission > 0


def test_the_mandatory_flat_clock_is_1510_central_and_is_a_clock_not_an_offset():
    from quant_brain.markets.futures_cme import topstep as ts
    assert (ts.MANDATORY_FLAT.value.hour, ts.MANDATORY_FLAT.value.minute) == (15, 10)
    assert ts.CME_EQUITY_CLOSE == dt.time(16, 0)


@pytest.mark.parametrize("date_str,expected_offset", [
    ("2026-01-15", -6),    # CST
    ("2026-07-15", -5),    # CDT
])
def test_the_flatten_deadline_survives_daylight_saving(date_str, expected_offset):
    """15:10 America/Chicago is a different UTC instant in winter and summer. A model that
    stores a fixed UTC offset is wrong twice a year."""
    import zoneinfo
    chi = zoneinfo.ZoneInfo("America/Chicago")
    d = dt.date.fromisoformat(date_str)
    local = dt.datetime.combine(d, dt.time(15, 10), tzinfo=chi)
    assert local.utcoffset() == dt.timedelta(hours=expected_offset)
    ny = local.astimezone(zoneinfo.ZoneInfo("America/New_York"))
    assert (ny.hour, ny.minute) == (16, 10), "15:10 CT must be 16:10 ET in both DST states"


# =====================================================================================
# ADVERSARIAL AND DEGENERATE INPUT  (Phase 17)
# =====================================================================================

def test_an_empty_or_single_bar_session_does_not_crash_or_invent_pnl():
    for closes in ([], [100.0]):
        path, turns, gross = _sa([1.0] * len(closes), closes, mult=1.0, ct=1, rt=1.0)
        assert turns == 0.0 and gross == 0.0


def test_nan_positions_are_treated_as_flat_not_as_a_position():
    path, turns, gross = _sa([np.nan, np.nan, np.nan], [100.0, 200.0, 300.0],
                             mult=1.0, ct=1, rt=1.0)
    assert gross == pytest.approx(0.0)
    assert turns == pytest.approx(0.0)


def test_a_zero_cost_model_is_possible_but_never_the_default():
    """Zero cost must be reachable for gross reporting, and must never happen by accident."""
    from quant_brain.markets.futures_cme import execution_sim as ex
    with pytest.raises((KeyError, ValueError)):
        ex.CostModel.for_contract("NOT_A_REAL_SYMBOL")


def test_round_turn_cost_includes_spread_not_only_commission():
    """The mislabel this audit found. `round_turn_cost` is commission PLUS a spread crossing;
    calling it 'commission only' understates the modelled friction."""
    from quant_brain.markets.futures_cme import execution_sim as ex
    from quant_brain.markets.futures_cme import instruments as inst
    for sym in ("ES", "NQ", "MES", "MNQ"):
        c = inst.get(sym)
        sim = ex.ExecutionSimulator(cost=ex.CostModel.for_contract(sym), symbol=sym)
        rt = sim.round_turn_cost(1)
        assert rt > c.commission_round_turn, (
            f"{sym}: round_turn_cost {rt} does not exceed commission "
            f"{c.commission_round_turn}; the spread component has gone missing")
        spread_component = rt - c.commission_round_turn
        assert spread_component == pytest.approx(
            sim.cost.spread_ticks * c.spec.tick_value, rel=1e-9)


def test_extreme_prices_do_not_overflow_or_lose_precision():
    for px in (0.01, 1e6):
        _, _, gross = _sa([1, 1, 0], [px, px * 1.01, px * 1.01], mult=1.0, ct=1, rt=0.0)
        assert np.isfinite(gross)
        assert gross == pytest.approx(px * 0.01, rel=1e-9)


def test_a_position_larger_than_one_unit_is_accounted_proportionally():
    _, turns, gross = _sa([2.0, 2.0, 0.0], [100.0, 101.0, 101.0], mult=1.0, ct=1, rt=1.0)
    assert gross == pytest.approx(2.0)
    assert turns == pytest.approx(2.0), "2 units in and out is 2 round turns"
