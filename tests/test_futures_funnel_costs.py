"""What the futures discovery funnel actually charges a hypothesis to trade.

THE DEFECT THIS FILE PINS
-------------------------
`scripts/futures_discover.py` counted a session's round turns as

    turns = int(np.abs(np.diff(pos, prepend=0.0)).sum() / 2)

`prepend=0.0` supplies the opening leg. Nothing supplies the closing one. A session is
entered flat and must end flat (the funnel's own 15:45 ET window, and Topstep's 3:10 PM CT
flat rule), so the exit is always traded and was never counted. For any rule that holds a
position into the bell the leg total is odd, and `int(odd/2)` truncates it down.

The consequence is not a rounding error. A rule that is simply long all session trades
exactly one round turn and was charged **zero**:

    always long, 390 bars       charged 0   actual 1
    in for the last half only   charged 0   actual 1
    flip long->short, still on  charged 1   actual 2

Measured against the funnel's own output, `research/experiments_futures.jsonl`:
**624 of the 816 scored hypotheses (76%) recorded `trades: 0` and `costs: 0.0`** - evaluated
on a gross P&L with no transaction cost at all. Worse, `trades < MIN_TRADES` (40) is an early
return, so all 624 were then discarded as "not a strategy" before the Topstep survival gate
and the walk-forward gate ever ran. The funnel was structurally unable to evaluate any
hypothesis that trades once or twice a session - which is most of the plausible ones.

The second defect here is timing. The cost used to be spread linearly across the session
with `np.linspace(0, cost, len(pnl_path))`. The terminal P&L is the same either way, but the
path is what `TwinDay(path=...)` hands to the Topstep twin, whose trailing maximum loss limit
tracks peak equity intraday. Cost that has not been charged yet is equity the twin thinks the
account has. Charging each leg at the bar it trades is both more accurate and less flattering.

These tests are the guard. If `session_accounting` ever stops counting the bell flatten, or
starts smearing cost again, they fail.
"""
from __future__ import annotations

import numpy as np
import pytest

from quant_brain.markets.futures_cme import execution_sim as ex
from quant_brain.markets.futures_cme import instruments as inst

fd = pytest.importorskip("futures_discover")

SYMBOL = "MES"
MULT = inst.get(SYMBOL).spec.multiplier
RT = ex.ExecutionSimulator(cost=ex.CostModel.for_contract(SYMBOL),
                           symbol=SYMBOL).round_turn_cost(1)


def _flat_close(n: int) -> np.ndarray:
    """A flat price series, so gross P&L is exactly zero and cost is the whole story."""
    return np.full(n, 5000.0)


def _ramp_close(n: int, step: float = 0.25) -> np.ndarray:
    return 5000.0 + step * np.arange(n, dtype=float)


# ---------------------------------------------------------------------------------------
# The leg count
# ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("name,pos,expected", [
    ("long all session", [1.0] * 60, 1.0),
    ("short all session", [-1.0] * 60, 1.0),
    ("in for the last half only", [0.0] * 30 + [1.0] * 30, 1.0),
    ("one in-and-out mid-session", [0.0] * 10 + [1.0] * 20 + [0.0] * 30, 1.0),
    ("flip long to short at the bell", [1.0] * 30 + [-1.0] * 30, 2.0),
    ("six on/off cycles, flat at the bell", ([1.0] * 5 + [0.0] * 5) * 6, 6.0),
    ("never in the market", [0.0] * 60, 0.0),
])
def test_every_leg_is_counted_including_the_flatten_at_the_bell(name, pos, expected):
    _, turns, _ = fd.session_accounting(
        np.array(pos), _flat_close(len(pos)),
        multiplier=MULT, contracts=1, round_turn_cost=RT)
    assert turns == expected, f"{name}: counted {turns} round turns, should be {expected}"


def test_a_rule_that_holds_into_the_bell_is_charged_a_full_round_turn():
    """The headline case. This is what 624 of 816 ledger rows were charged nothing for."""
    net, turns, gross = fd.session_accounting(
        np.ones(390), _flat_close(390), multiplier=MULT, contracts=1, round_turn_cost=RT)
    assert turns == 1.0
    assert gross == pytest.approx(0.0)
    assert net[-1] == pytest.approx(-RT), (
        "a flat market, one round turn: the session must end down exactly the round-turn cost")


def test_cost_scales_with_contracts_through_the_simulator_not_by_hand():
    rt3 = ex.ExecutionSimulator(cost=ex.CostModel.for_contract(SYMBOL),
                                symbol=SYMBOL).round_turn_cost(3)
    net, turns, _ = fd.session_accounting(
        np.ones(60), _flat_close(60), multiplier=MULT, contracts=3, round_turn_cost=rt3)
    assert turns == 1.0
    assert net[-1] == pytest.approx(-rt3)


# ---------------------------------------------------------------------------------------
# When the cost lands
# ---------------------------------------------------------------------------------------

def test_cost_is_charged_at_the_bar_that_trades_not_smeared_across_the_session():
    """Enter at bar 0, exit at the bell, flat market.

    Charged correctly, the equity path is a step: down half a round turn from the first
    point and flat until the closing leg. Smeared linearly it would be a diagonal, which
    hands the Topstep twin equity the account does not have.
    """
    n = 100
    net, turns, _ = fd.session_accounting(
        np.ones(n), _flat_close(n), multiplier=MULT, contracts=1, round_turn_cost=RT)
    assert turns == 1.0
    assert net[0] == pytest.approx(-RT / 2), "the entry leg is paid at the entry bar"
    mid = net[1:-1]
    assert np.allclose(mid, -RT / 2), (
        "a flat market with no trading in between must hold a flat equity line; a linear "
        f"ramp means the cost is being smeared. saw {mid.min():.4f}..{mid.max():.4f}")
    assert net[-1] == pytest.approx(-RT), "the exit leg is paid at the bell"


def test_a_midday_entry_pays_nothing_before_it_trades():
    n = 60
    pos = np.array([0.0] * 30 + [1.0] * 30)
    net, _, _ = fd.session_accounting(
        pos, _flat_close(n), multiplier=MULT, contracts=1, round_turn_cost=RT)
    assert np.allclose(net[:28], 0.0), "no position, no cost"
    assert net[-1] == pytest.approx(-RT)


# ---------------------------------------------------------------------------------------
# The accounting identity, and the one-bar lag it must not break
# ---------------------------------------------------------------------------------------

def test_terminal_net_is_gross_minus_the_round_turns_charged():
    rng = np.random.default_rng(0)
    for _ in range(25):
        n = int(rng.integers(20, 200))
        pos = rng.choice([-1.0, 0.0, 1.0], size=n)
        close = 5000.0 + np.cumsum(rng.normal(0, 0.25, n))
        net, turns, gross = fd.session_accounting(
            pos, close, multiplier=MULT, contracts=1, round_turn_cost=RT)
        assert net[-1] == pytest.approx(gross - turns * RT), (
            "net, gross and cost must reconcile exactly on every path")


def test_the_one_bar_lag_survives_the_change():
    """Position on bar i earns bar i+1's move. A rule long only on the last bar can never
    earn anything, because there is no bar after it."""
    n = 40
    pos = np.zeros(n)
    pos[-1] = 1.0
    _, turns, gross = fd.session_accounting(
        pos, _ramp_close(n), multiplier=MULT, contracts=1, round_turn_cost=RT)
    assert gross == pytest.approx(0.0), "a last-bar position must earn zero, not one bar of move"
    assert turns == 1.0, "it still traded in and out, so it still pays"


def test_a_position_held_one_bar_earns_exactly_one_bars_move():
    n = 40
    pos = np.zeros(n)
    pos[10] = 1.0
    _, _, gross = fd.session_accounting(
        pos, _ramp_close(n, step=0.25), multiplier=MULT, contracts=1, round_turn_cost=RT)
    assert gross == pytest.approx(0.25 * MULT)


# ---------------------------------------------------------------------------------------
# Through the production evaluator, on the family the funnel actually ran
# ---------------------------------------------------------------------------------------

def _sessions_and_feats(n_sessions: int, bars: int = 60):
    import pandas as pd
    sessions, feats = [], []
    for d in range(n_sessions):
        close = _flat_close(bars)
        sessions.append(pd.DataFrame({"c": close, "day": [f"2026-01-{d + 1:02d}"] * bars}))
        feats.append(pd.DataFrame({"f": np.zeros(bars)}))
    return sessions, feats


class _AlwaysLong:
    name, family, params = "always_long", "test", {}

    @staticmethod
    def signal(X):
        return np.ones(len(X))


def test_the_trade_floor_no_longer_discards_the_low_turnover_family():
    """60 sessions of a session-long rule: 60 round turns, above the 40-trade floor.

    Before the fix this reported `trades: 0`, `costs: 0.0` and returned early with
    `cost_ok=False, "only 0 round turns; not a strategy"` - the funnel discarding the
    hypothesis class it was least able to price. The market here is flat, so the rule has no
    gross edge and the COST gate rightly rejects it; the point is that it is now rejected for
    losing money rather than for a trade count that never existed.
    """
    from quant_brain.markets.futures_cme import twin as tw
    sessions, feats = _sessions_and_feats(60)
    run = fd.evaluator(sessions, feats, contracts=1,
                       twin_obj=tw.TopstepTwin(50_000, profit_target=3_000.0),
                       symbol=SYMBOL)
    out = run(_AlwaysLong())
    assert out["trades"] == 60, f"60 sessions, one round turn each; got {out['trades']}"
    assert out["costs"] == pytest.approx(60 * RT)
    assert out["mean_per_session"] == pytest.approx(-RT), (
        "flat market, one round turn a session: the funnel must see a loss, not zero")
    assert "round turns; not a strategy" not in (out.get("cost_reason") or ""), (
        "the trade floor is still swallowing a rule that trades every single session")


def test_the_low_turnover_family_now_reaches_the_topstep_and_walkforward_gates():
    """A session-long rule on a rising market clears the cost gate and is actually evaluated.

    This is the part the undercount made impossible. With `trades: 0` every low-turnover
    hypothesis hit the 40-trade early return, so `evaluate_twin` and the walk-forward split
    never ran on any of them. 624 of 816 ledger rows died there.
    """
    from quant_brain.markets.futures_cme import twin as tw
    sessions, feats = _sessions_and_feats(60)
    for g in sessions:
        g["c"] = _ramp_close(len(g), step=0.25)
    run = fd.evaluator(sessions, feats, contracts=1,
                       twin_obj=tw.TopstepTwin(50_000, profit_target=3_000.0),
                       symbol=SYMBOL)
    out = run(_AlwaysLong())
    assert out["trades"] == 60
    assert out.get("cost_ok") is not False, out.get("cost_reason")
    assert out["mean_per_session"] == pytest.approx(59 * 0.25 * MULT - RT), (
        "59 one-bar moves earned, one round turn paid")
    assert "p_pass_combine" in out, "the Topstep survival gate never ran"
    assert "wf_positive_folds" in out, "the walk-forward gate never ran"
