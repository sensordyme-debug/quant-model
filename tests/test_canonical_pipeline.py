"""Adversarial tests for the integrated pipeline: one ledger, two consumers, four modes.

WHAT THIS FILE DEFENDS
----------------------
The runner now produces a single canonical ledger and reads the P&L layer, the Topstep
account layer and the monthly/payout layer off it. That removes the failure mode where a
profit number and an account verdict were computed from two different walks over the same
day - but it creates new ones, and this file is about those:

    * a mode changing a P&L it must not change
    * an adverse excursion rescuing an account instead of endangering it
    * the account layer disagreeing with the independent reference once it is fed real fills
    * an event on the boundary - exactly at the limit, both rules on one bar - resolving the
      flattering way

Every session below is built bar by bar with prices chosen so the arithmetic is checkable by
hand, and the signal is handed in directly rather than derived from features. That keeps the
test about the PIPELINE rather than about the feature library.

THE STRATEGY IS NEVER TOUCHED
-----------------------------
Nothing here tunes, filters or reshapes a signal to produce an outcome. Where a scenario
needs the account to breach, the PRICES are built to breach it; the rule stays as written.
"""
from __future__ import annotations

import dataclasses
import datetime as dt

import numpy as np
import pandas as pd
import pytest

from quant_brain.markets.futures_cme import instruments as inst
from quant_brain.markets.futures_cme import topstep as ts
from quant_brain.markets.futures_cme import twin as tw
from quant_brain.research import execution_modes as em
from quant_brain.research import exits as X
from quant_brain.research import topstep_reference as tr
from quant_brain.research.account_result import PayoutRuleSet, build_account_result
from quant_brain.research.canonical_ledger import ExecutionPathMode as M
from quant_brain.research.ledger_builder import build_ledger, cost_for
from quant_brain.research.strategy_spec import (
    CostSpec,
    ExitSpec,
    SessionSpec,
    SizingSpec,
    StrategySpec,
)

MONDAY = dt.date(2026, 1, 5)

#: Zero commission and no spread wherever a scenario is about the ACCOUNT rather than about
#: costs, so a hand-computed balance is not off by a few dollars of fees. Scenarios that are
#: about cost say so and use the published model.
FREE = CostSpec(commission_round_turn=0.0, include_spread=False, slippage_ticks=0.0)


def signal_from(X):
    """The spec's signal for every test here: the position array, handed in directly."""
    return np.asarray(X["pos"], dtype=float)


def make_spec(instrument: str = "ES", *, contracts: int = 1, exit_spec=None,
              cost=FREE, warmup: int = 0, last_entry: int | None = None) -> StrategySpec:
    return StrategySpec(
        name="pipeline_probe", instrument=instrument, timeframe="1min",
        signal=signal_from,
        exit=exit_spec if exit_spec is not None else ExitSpec(use_invalidation=True),
        sizing=SizingSpec(contracts=contracts),
        session=SessionSpec(open_et="09:30", close_et="16:00", warmup_bars=warmup,
                            last_entry_bar=last_entry),
        cost=cost,
        rationale="engine probe; not a strategy and never recommended")


def session(day: dt.date, closes, highs=None, lows=None):
    """One synthetic session. Highs/lows default to the closes: no intrabar excursion."""
    c = np.asarray(closes, dtype=float)
    h = c if highs is None else np.asarray(highs, dtype=float)
    lo = c if lows is None else np.asarray(lows, dtype=float)
    t = pd.date_range(pd.Timestamp(f"{day} 14:30", tz="UTC"), periods=len(c), freq="1min")
    return pd.DataFrame({"t": t, "o": c, "h": h, "l": lo, "c": c, "v": 1.0,
                         "day": [day] * len(c)})


def weekdays(n: int, start: dt.date = MONDAY) -> list[dt.date]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def ledger(spec, sessions, positions, *, mode=M.CLOSE_ONLY, slip=0.0, spread=None):
    feats = [{"pos": p} for p in positions]
    return build_ledger(spec, sessions, feats, slip_ticks=slip, scenario="TEST",
                        mode=mode, include_spread=spread)


def account(led, **kw):
    kw.setdefault("payout_fraction", 1.0)
    kw.setdefault("reps", 60)
    return build_account_result(led, **kw)


# ======================================================================================
# THE STRUCTURAL GUARANTEE: ONE LEDGER
# ======================================================================================

def test_the_account_layer_consumes_the_ledgers_own_marks_and_nothing_else():
    """The whole point of the refactor, asserted directly.

    `twin_days()` must hand the account simulator the SAME tuples the P&L layer summed. If
    it rebuilt them, this comparison would be of two objects that merely happen to agree,
    and the day they stopped agreeing nothing would notice.
    """
    days = weekdays(3)
    spec = make_spec()
    sess = [session(d, [4000.0, 4001.0, 4002.0, 4001.0, 4000.0]) for d in days]
    pos = [np.array([1.0, 1.0, 1.0, 0.0, 0.0])] * 3
    led = ledger(spec, sess, pos)
    twin_days = led.twin_days()
    assert len(twin_days) == len(led.sessions)
    for td, s in zip(twin_days, led.sessions, strict=True):
        assert td.path is s.marks            # identity, not equality
        assert td.pnl == s.realized_net
        assert td.path[-1] == td.pnl


def test_the_pnl_layer_recomputes_nothing():
    """Every view is a projection of the same fills."""
    days = weekdays(4)
    spec = make_spec()
    sess = [session(d, [4000.0, 4003.0, 4002.0, 4005.0]) for d in days]
    pos = [np.array([1.0, 1.0, 0.0, 0.0])] * 4
    led = ledger(spec, sess, pos)
    trades = led.trade_frame()
    assert float(trades["net_pnl"].sum()) == pytest.approx(float(led.daily().sum()))
    assert float(led.equity_curve()[-1]) == pytest.approx(float(led.daily().sum()))
    # two fills per trade, and their signed quantities cancel
    fills = led.fill_frame()
    assert len(fills) == 2 * len(trades)
    assert float(fills["signed_quantity"].sum()) == pytest.approx(0.0)


# ======================================================================================
# 1-11: ACCOUNT-LEVEL ADVERSARIAL SCENARIOS
# ======================================================================================

def test_01_the_target_is_reached_and_then_given_back():
    """Three sessions of +$3,000 worth of points, then a loss. The pass is not undone.

    ES at 50x: 20 points is $1,000. Sessions of +20, +20, +20 make exactly $3,000 with a
    best day of one third, inside the 55% consistency limit, so the Combine passes on the
    third. The fourth session loses 20 points - on a FUNDED account that opens at $0, so it
    is a $1,000 loss against $2,000 of room, not a reversal of the pass.
    """
    days = weekdays(4)
    spec = make_spec("ES")
    sess = ([session(d, [4000.0, 4020.0]) for d in days[:3]]
            + [session(days[3], [4000.0, 3980.0])])
    pos = [np.array([1.0, 0.0])] * 4
    a = account(ledger(spec, sess, pos))
    assert a.target_reached is True
    assert a.combine_sessions == 3
    assert a.terminal_stage == "express_funded"
    assert a.liquidated is False
    assert a.ending_balance == pytest.approx(-1_000.0)     # the XFA, not the Combine


def test_02_an_intrabar_breach_on_a_session_that_closes_safely():
    """The scenario close-only accounting cannot see.

    One session: the close path goes 4000 -> 4000 (flat, $0). The bar's LOW is 3958, which
    is 42 points below the entry: 42 x $50 = $2,100 against $2,000 of room.

        CLOSE_ONLY               worst mark $0        survives
        INTRABAR_CONSERVATIVE    worst mark -$2,100   liquidated

    Same fills, same settled P&L, opposite account verdict. This is the 2.6% of real ES
    sessions measured in docs/TOPSTEP_TWIN_AUDIT.md, reproduced exactly.
    """
    spec = make_spec("ES")
    sess = [session(MONDAY, [4000.0, 4000.0], highs=[4000.0, 4000.0],
                    lows=[4000.0, 3958.0])]
    pos = [np.array([1.0, 0.0])]

    shallow = account(ledger(spec, sess, pos, mode=M.CLOSE_ONLY))
    deep = account(ledger(spec, sess, pos, mode=M.INTRABAR_CONSERVATIVE))

    assert shallow.liquidated is False
    assert deep.liquidated is True
    assert "intraday" in deep.liquidation_reason
    # the P&L is untouched by the mode
    assert shallow.returns.net_pnl == deep.returns.net_pnl == 0.0


def test_03_the_daily_loss_limit_fires_intraday():
    """A 30-point adverse excursion with the $1,000 DLL armed.

    30 x $50 = $1,500. The DLL level sits at 50,000 - 1,000 = 49,000 and the MLL at 48,000,
    so equity 48,500 crosses the higher level first: the session is capped at -$1,000 and
    the account survives at $49,000 rather than settling at -$1,500.
    """
    spec = make_spec("ES")
    sess = [session(MONDAY, [4000.0, 4000.0], lows=[4000.0, 3970.0])]
    pos = [np.array([1.0, 0.0])]
    a = account(ledger(spec, sess, pos, mode=M.INTRABAR_CONSERVATIVE),
                daily_loss_limit=1_000.0)
    assert a.dll_capped_sessions == 1
    assert a.liquidated is False
    assert a.ending_balance == pytest.approx(49_000.0)
    assert a.min_dll_buffer is not None


def test_04_equity_landing_exactly_on_the_limit_is_a_breach():
    """40 points down is exactly $2,000: equity 48,000, the limit 48,000.

    The rule is "at or below", so the boundary belongs to the firm. Landing one tick
    shallower must survive, which the next test pins.
    """
    spec = make_spec("ES")
    sess = [session(MONDAY, [4000.0, 3960.0])]
    a = account(ledger(spec, sess, [np.array([1.0, 0.0])]))
    assert a.liquidated is True
    assert "48,000" in a.liquidation_reason


def test_04b_one_tick_shallower_survives():
    """3960.25 is $1,987.50 down. The boundary is bracketed from both sides."""
    spec = make_spec("ES")
    sess = [session(MONDAY, [4000.0, 3960.25])]
    a = account(ledger(spec, sess, [np.array([1.0, 0.0])]))
    assert a.liquidated is False
    assert a.ending_balance == pytest.approx(50_000.0 - 1_987.50)


def test_05_equity_landing_exactly_on_the_daily_limit_caps_the_session():
    """Exactly $1,000 down with the DLL armed: 49,000 <= 49,000, so the cap fires.

    It settles at the same -$1,000 either way, which is what makes this boundary safe to
    get wrong in P&L terms and dangerous to get wrong in ACCOUNT terms: the capped session
    also ends the trading day.
    """
    spec = make_spec("ES")
    sess = [session(MONDAY, [4000.0, 3980.0])]
    a = account(ledger(spec, sess, [np.array([1.0, 0.0])], mode=M.INTRABAR_CONSERVATIVE),
                daily_loss_limit=1_000.0)
    assert a.dll_capped_sessions == 1
    assert a.ending_balance == pytest.approx(49_000.0)


def test_06_profit_landing_exactly_on_the_target_passes():
    """Exactly $3,000 over three equal sessions. 3,000 >= 3,000, so the target is met."""
    days = weekdays(3)
    spec = make_spec("ES")
    sess = [session(d, [4000.0, 4020.0]) for d in days]
    a = account(ledger(spec, sess, [np.array([1.0, 0.0])] * 3))
    assert a.target_reached is True
    assert a.combine_sessions == 3


def test_06b_one_tick_short_of_the_target_does_not_pass():
    """$2,987.50. The other side of the same boundary."""
    days = weekdays(3)
    spec = make_spec("ES")
    sess = ([session(d, [4000.0, 4020.0]) for d in days[:2]]
            + [session(days[2], [4000.0, 4019.75])])
    a = account(ledger(spec, sess, [np.array([1.0, 0.0])] * 3))
    assert a.target_reached is False
    assert a.terminal_stage == "trading_combine"


def test_07_the_target_and_the_limit_on_the_same_session():
    """A session that would pass the Combine at its close but touches the limit first.

    Two prior sessions bank $2,000. The third rises 20 points to complete the $3,000 - but
    its LOW is 4000 - 40.5 = 3959.5 first, which against a limit that has trailed to
    50,000 is a breach at 49,959.5... so the account is dead before the target is scored.

    Liquidation is absorbing. A twin that scored the target off the close would report a
    funded account that had already been liquidated.
    """
    days = weekdays(3)
    spec = make_spec("ES")
    sess = [session(days[0], [4000.0, 4020.0]),
            session(days[1], [4000.0, 4020.0]),
            session(days[2], [4000.0, 4020.0], highs=[4000.0, 4020.0],
                    lows=[4000.0, 3959.5])]
    pos = [np.array([1.0, 0.0])] * 3
    a = account(ledger(spec, sess, pos, mode=M.INTRABAR_CONSERVATIVE))
    assert a.liquidated is True
    assert a.liquidation_session == days[2]
    assert a.target_reached is False


def test_08_a_stop_and_a_target_reachable_on_one_bar_resolve_as_the_stop():
    """The ambiguity rule, carried through the ledger to the trade record.

    Entry at 4000 with a 1-ATR stop and a 2R target. The next bar spans both. The engine
    resolves it as a STOP and flags `ambiguous_bar`; the flag reaches the trade frame so a
    reader can count how much of a result rests on the assumption.
    """
    # A STRUCTURAL stop takes its risk from the entry bar's own range, so the levels are
    # readable off two numbers instead of a session-wide average: entry 4000, entry-bar low
    # 3990, so risk is 10 points, the stop sits at 3990 and the 2R target at 4020.
    spec = make_spec("ES", exit_spec=ExitSpec(structural_stop=True, target_r=2.0,
                                              use_invalidation=False))
    sess = [session(MONDAY, [4000.0, 4000.0, 4000.0],
                    highs=[4010.0, 4001.0, 4025.0], lows=[3990.0, 3999.0, 3985.0])]
    pos = [np.array([1.0, 0.0, 0.0])]
    led = ledger(spec, sess, pos)
    tf = led.trade_frame()
    assert len(tf) == 1
    assert tf["exit_reason"].iloc[0] == "stop"
    assert bool(tf["ambiguous_bar"].iloc[0]) is True


def test_09_a_position_still_open_at_the_bell_is_flattened_and_recorded():
    """No position survives the session. The exit reason says the bell closed it."""
    spec = make_spec("ES")
    sess = [session(MONDAY, [4000.0, 4001.0, 4002.0, 4003.0])]
    pos = [np.array([1.0, 1.0, 1.0, 1.0])]     # never turns off
    led = ledger(spec, sess, pos)
    tf = led.trade_frame()
    assert len(tf) == 1
    assert tf["exit_reason"].iloc[0] == X.FLATTEN == "forced_flatten"
    assert bool(tf["forced_flatten"].iloc[0]) is True
    assert led.sessions[0].ends_flat is True
    assert led.sessions[0].forced_flatten is True
    a = account(led)
    assert a.forced_flatten_sessions == 1
    assert a.forced_flatten_pnl == pytest.approx(150.0)     # 3 points x $50


def test_10_a_forced_flatten_during_an_adverse_excursion_is_still_marked():
    """The bell closes the position at the close, but the account was marked at the low.

    The path must show the excursion even though the trade settles at the close - otherwise
    a session that came within a tick of the limit reads as uneventful.
    """
    spec = make_spec("ES")
    sess = [session(MONDAY, [4000.0, 4000.0, 4000.0],
                    highs=[4000.0, 4000.0, 4000.0], lows=[4000.0, 3970.0, 3990.0])]
    pos = [np.array([1.0, 1.0, 1.0])]
    led = ledger(spec, sess, pos, mode=M.INTRABAR_CONSERVATIVE)
    s = led.sessions[0]
    assert s.realized_net == pytest.approx(0.0)
    assert min(s.marks) == pytest.approx(-1_500.0)       # 30 points x $50
    assert s.marks[-1] == pytest.approx(0.0)


def test_11_a_profitable_signal_after_liquidation_earns_the_account_nothing():
    """Liquidation is absorbing. The strategy keeps trading; the account does not.

    Session 1 loses $2,000 and kills the Combine. Sessions 2 and 3 make $1,000 each. The
    STRATEGY ends up flat overall; the ACCOUNT ended on session 1 and the later profit is
    not credited to it. Reporting the strategy total as the account outcome would be the
    single largest overstatement this engine could make.
    """
    days = weekdays(3)
    spec = make_spec("ES")
    sess = [session(days[0], [4000.0, 3960.0]),
            session(days[1], [4000.0, 4020.0]),
            session(days[2], [4000.0, 4020.0])]
    pos = [np.array([1.0, 0.0])] * 3
    led = ledger(spec, sess, pos)
    a = account(led)
    assert float(led.daily().sum()) == pytest.approx(0.0)     # strategy: flat
    assert a.liquidated is True
    assert a.days_survived == 1                                # account: over on day one
    assert a.liquidation_session == days[0]
    assert a.returns.pnl_under_account_constraints == pytest.approx(-2_000.0)


# ======================================================================================
# 12-20: FILL-LEVEL ADVERSARIAL SCENARIOS
# ======================================================================================

def test_12_a_position_reversal_is_two_trades_not_one():
    """Long then short in the same session. Four fills, two round turns, both charged."""
    spec = make_spec("ES", exit_spec=ExitSpec(use_invalidation=True))
    sess = [session(MONDAY, [4000.0, 4002.0, 4004.0, 4003.0, 4001.0])]
    # Flat at bar 2 closes the long by invalidation; the short at bar 3 is then a NEW
    # entry. Going straight from +1 to -1 exits on bar 2 and leaves bar 3 looking
    # unchanged, so no second position opens - which is correct, and not what this
    # test is about.
    pos = [np.array([1.0, 1.0, 0.0, -1.0, 0.0])]
    led = ledger(spec, sess, pos)
    tf = led.trade_frame()
    assert len(tf) == 2
    assert list(tf["direction"]) == [1, -1]
    assert len(led.sessions[0].fills) == 4
    assert float(led.fill_frame()["signed_quantity"].sum()) == pytest.approx(0.0)


def test_13_a_trade_that_exits_on_the_very_next_bar_is_a_real_trade():
    """The shortest possible round trip: entered at bar 0, out at bar 1.

    `holding_minutes` is 1, not 0 - a zero would make it look like a fill that never
    happened, and per-trade statistics would divide by a phantom.
    """
    spec = make_spec("ES")
    sess = [session(MONDAY, [4000.0, 4001.0, 4001.0])]
    pos = [np.array([1.0, 0.0, 0.0])]
    tf = ledger(spec, sess, pos).trade_frame()
    assert len(tf) == 1
    assert tf["holding_minutes"].iloc[0] == 1
    assert tf["entry_bar"].iloc[0] == 0 and tf["exit_bar"].iloc[0] == 1


def test_14_partial_fills_are_declared_not_modelled_in_every_mode():
    """The honest answer, stated in the result rather than discovered later.

    One-minute OHLCV carries no size, so there is nothing to model a partial against. Every
    mode says so in the same words, and the words travel into the saved scenario table.
    """
    for profile in em.LADDER:
        assert "NOT MODELLED" in profile.partial_fills
        assert profile.as_row()["partial_fill_model"] == profile.partial_fills
    assert "NOT MODELLED" in em.assumptions_table()


def test_15_a_gap_straight_through_the_stop_still_fills_at_the_stop():
    """The declared assumption, made visible rather than left implicit.

    The bar opens far below the stop. The engine fills AT the stop price, so the modelled
    loss is smaller than a real gap would produce. That is optimistic, it is what
    `stop_execution` says in every mode, and a scenario asserting it means the assumption
    cannot change without a test failing.
    """
    spec = make_spec("ES", exit_spec=ExitSpec(structural_stop=True,
                                              use_invalidation=False))
    sess = [session(MONDAY, [4000.0, 4000.0, 3900.0],
                    highs=[4010.0, 4001.0, 3905.0], lows=[3990.0, 3999.0, 3895.0])]
    led = ledger(spec, sess, [np.array([1.0, 0.0, 0.0])])
    tf = led.trade_frame()
    assert tf["exit_reason"].iloc[0] == "stop"
    # Risk is 10 points off the entry bar, so the stop sits at 3990 - a hundred points
    # above where the gap bar actually traded. The modelled loss is $500; a fill at the
    # 3895 low would have been $5,250.
    assert tf["exit_price"].iloc[0] == pytest.approx(3990.0)
    assert tf["net_pnl"].iloc[0] == pytest.approx(-500.0)
    assert "no gap-through penalty" in em.CONSERVATIVE.stop_execution


def test_16_a_gap_straight_through_the_target_still_fills_at_the_target():
    """The mirror image, and the reason it is not free: the same rule caps the winner."""
    spec = make_spec("ES", exit_spec=ExitSpec(structural_stop=True, target_r=2.0,
                                              use_invalidation=False))
    sess = [session(MONDAY, [4000.0, 4000.0, 4100.0],
                    highs=[4010.0, 4001.0, 4105.0], lows=[3990.0, 3999.0, 4095.0])]
    tf = ledger(spec, sess, [np.array([1.0, 0.0, 0.0])]).trade_frame()
    assert tf["exit_reason"].iloc[0] == "target"
    assert tf["exit_price"].iloc[0] == pytest.approx(4020.0)   # 4000 + 2 x 10 points
    assert tf["net_pnl"].iloc[0] == pytest.approx(1_000.0)     # not the $5,000 gap


def test_17_two_entry_signals_on_one_bar_cannot_open_two_positions():
    """A signal that flips and flips back while a position is open is ignored until it exits.

    Without the `busy_until` guard the engine would open overlapping positions and charge
    one round turn for two, which inflates trade count and understates cost simultaneously.
    """
    # `use_invalidation=False` with no stop is REFUSED by the spec - a position with no way
    # out is a real error, not a test fixture - so this carries a structural stop the rising
    # prices never reach.
    spec = make_spec("ES", exit_spec=ExitSpec(structural_stop=True,
                                              use_invalidation=False))
    sess = [session(MONDAY, [4000.0, 4001.0, 4002.0, 4003.0, 4004.0],
                    highs=[4001.0, 4002.0, 4003.0, 4004.0, 4005.0],
                    lows=[3999.0, 4000.0, 4001.0, 4002.0, 4003.0])]
    pos = [np.array([1.0, 0.0, 1.0, 0.0, 1.0])]
    led = ledger(spec, sess, pos)
    tf = led.trade_frame()
    # invalidation is off and the stop is never reached, so the first entry runs to the
    # bell and the later signals cannot open a second overlapping position
    assert len(tf) == 1
    assert tf["exit_reason"].iloc[0] == X.FLATTEN
    assert tf["exit_bar"].iloc[0] == 4
    assert len(led.sessions[0].fills) == 2


def test_18_the_short_side_mirrors_the_long_side_exactly():
    """A mirrored price path must produce a mirrored ledger, marks included."""
    spec = make_spec("ES")
    up = [session(MONDAY, [4000.0, 4010.0], highs=[4000.0, 4012.0],
                  lows=[3994.0, 4008.0])]
    down = [session(MONDAY, [4000.0, 3990.0], highs=[4006.0, 3992.0],
                    lows=[4000.0, 3988.0])]
    a = ledger(spec, up, [np.array([1.0, 0.0])], mode=M.INTRABAR_CONSERVATIVE)
    b = ledger(spec, down, [np.array([-1.0, 0.0])], mode=M.INTRABAR_CONSERVATIVE)
    assert a.sessions[0].realized_net == pytest.approx(b.sessions[0].realized_net)
    assert list(a.sessions[0].marks) == pytest.approx(list(b.sessions[0].marks))


def test_19_one_contract_against_the_maximum_the_account_allows():
    """Five ES is the ceiling on a $50K account; six is not, and the result says so.

    P&L scales exactly with size and so does the risk, which is the whole reason the
    ceiling exists: the same session that costs $2,000 at five lots costs $400 at one.
    """
    spec1 = make_spec("ES", contracts=1)
    spec5 = make_spec("ES", contracts=5)
    spec6 = make_spec("ES", contracts=6)
    sess = [session(MONDAY, [4000.0, 3992.0])]
    pos = [np.array([1.0, 0.0])]

    a1 = account(ledger(spec1, sess, pos))
    a5 = account(ledger(spec5, sess, pos))
    a6 = account(ledger(spec6, sess, pos))

    assert a1.returns.net_pnl == pytest.approx(-400.0)
    assert a5.returns.net_pnl == pytest.approx(-2_000.0)
    assert a1.contract_limit_ok is True and a5.contract_limit_ok is True
    assert a6.contract_limit_ok is False
    assert "exceeds the 5 permitted" in a6.contract_limit_detail
    # five lots is exactly the $2,000 of room; one lot is a fifth of it
    assert a5.liquidated is True
    assert a1.liquidated is False


def test_20_micros_and_minis_are_the_same_points_and_different_money():
    """MES is a tenth of ES. The same bars must produce a tenth of the P&L, exactly."""
    sess = [session(MONDAY, [4000.0, 4010.0])]
    pos = [np.array([1.0, 0.0])]
    big = ledger(make_spec("ES"), sess, pos)
    small = ledger(make_spec("MES"), sess, pos)
    assert inst.get("ES").spec.multiplier == 10 * inst.get("MES").spec.multiplier
    assert float(big.daily().sum()) == pytest.approx(10 * float(small.daily().sum()))
    assert account(big).contract_limit_detail.endswith("ES permitted")
    assert account(small).contract_limit_detail.endswith("MES permitted")


# ======================================================================================
# 21-25: ACCOUNT CONFIGURATION AND THE SECOND OPINION
# ======================================================================================

def test_21_and_22_the_daily_loss_limit_is_a_configuration_that_changes_the_outcome():
    """The same sessions, armed and unarmed. One survives; one does not.

    35 points is $1,750, inside the $2,000 limit but outside the $1,000 daily one. Two of
    them in a row kill an unarmed account (-$3,500 against $2,000 of room) and leave an
    armed one at -$2,000... which is also dead, so the third session is the discriminator:
    armed, the account is at 48,000 - dead. Take one session instead.
    """
    spec = make_spec("ES")
    sess = [session(MONDAY, [4000.0, 3965.0])]
    pos = [np.array([1.0, 0.0])]
    led_c = ledger(spec, sess, pos, mode=M.INTRABAR_CONSERVATIVE)

    unarmed = account(led_c, daily_loss_limit=None)
    armed = account(led_c, daily_loss_limit=1_000.0)

    assert unarmed.liquidated is False
    assert unarmed.ending_balance == pytest.approx(48_250.0)
    assert armed.liquidated is False
    assert armed.ending_balance == pytest.approx(49_000.0)   # capped at -$1,000
    assert armed.dll_capped_sessions == 1
    assert unarmed.dll_capped_sessions == 0
    assert unarmed.min_dll_buffer is None
    assert armed.min_dll_buffer is not None


def test_23_intrabar_conservative_versus_close_only_across_a_whole_run():
    """The mode ladder's first real step, on a run long enough to matter.

    Twenty sessions, each with a $500 adverse wick the closes never show. The settled P&L
    must be byte-identical and the account's worst buffer must be strictly worse.
    """
    days = weekdays(20)
    spec = make_spec("ES")
    # The wick has to sit on a bar the position is HELD through. Bar 0 is the entry bar and
    # the position opens at its close, so a low there is before the position existed and is
    # correctly not marked - putting the wick there would make this pass for no reason.
    sess = [session(d, [4000.0, 4002.0, 4002.0],
                    highs=[4000.0, 4002.0, 4002.0], lows=[4000.0, 3990.0, 4002.0])
            for d in days]
    pos = [np.array([1.0, 1.0, 0.0])] * 20
    shallow = ledger(spec, sess, pos, mode=M.CLOSE_ONLY)
    deep = ledger(spec, sess, pos, mode=M.INTRABAR_CONSERVATIVE)

    assert float(shallow.daily().sum()) == float(deep.daily().sum())
    assert shallow.trade_frame().drop(columns=["execution_path_mode"]).equals(
        deep.trade_frame().drop(columns=["execution_path_mode"]))
    a, b = account(shallow), account(deep)
    # `min_mll_buffer` is measured after settlement, and the wick never reaches the close -
    # so it is the INTRADAY buffer that moves. Asserting the wrong one of the two would
    # pass for the wrong reason on a session whose close happened to be its low.
    assert a.min_mll_buffer == pytest.approx(b.min_mll_buffer)
    assert b.min_mll_buffer_intraday < a.min_mll_buffer_intraday
    assert b.max_intraday_drawdown < a.max_intraday_drawdown


def test_24_stress_is_strictly_worse_than_baseline_and_only_in_the_path():
    """STRESS drops the protection a stop's fill price gives the exit bar.

    A stop exits at 3990 while the bar's low is 3970. INTRABAR_CONSERVATIVE floors the mark
    at the stop, because the position was closed there. STRESS assumes the flatten had not
    registered at the worst tick. Both settle the trade at 3990.
    """
    spec = make_spec("ES", exit_spec=ExitSpec(structural_stop=True,
                                              use_invalidation=False))
    sess = [session(MONDAY, [4000.0, 4000.0, 3985.0],
                    highs=[4010.0, 4001.0, 3995.0], lows=[3990.0, 3999.0, 3970.0])]
    pos = [np.array([1.0, 0.0, 0.0])]
    cons = ledger(spec, sess, pos, mode=M.INTRABAR_CONSERVATIVE)
    stress = ledger(spec, sess, pos, mode=M.STRESS)

    assert cons.sessions[0].realized_net == pytest.approx(stress.sessions[0].realized_net)
    assert cons.trade_frame()["exit_price"].iloc[0] == pytest.approx(3990.0)
    assert min(cons.sessions[0].marks) == pytest.approx(-500.0)     # the stop, 10 pts
    assert min(stress.sessions[0].marks) == pytest.approx(-1_500.0)  # the low, 30 pts


def test_25_the_account_layer_agrees_with_the_independent_reference():
    """Every canonical run cross-checks itself against `topstep_reference`.

    Not the twin against itself: a second implementation with no shared code, fed the ledger
    the production run produced.
    """
    days = weekdays(12)
    spec = make_spec("ES")
    rng = np.random.default_rng(4)
    sess, pos = [], []
    for d in days:
        c = 4000.0 + np.cumsum(rng.normal(0, 3.0, 6))
        sess.append(session(d, c, highs=c + 2.0, lows=c - 2.0))
        pos.append(np.array([1.0, 1.0, 0.0, -1.0, -1.0, 0.0]))
    for mode in (M.CLOSE_ONLY, M.INTRABAR_CONSERVATIVE, M.STRESS):
        a = account(ledger(spec, sess, pos, mode=mode), daily_loss_limit=1_000.0)
        assert a.cross_check.agrees, a.cross_check.mismatches
        assert a.cross_check.fields_compared >= 16


# ======================================================================================
# THE MONOTONIC SAFETY PROPERTY, AT THE INTEGRATED LEVEL
# ======================================================================================

def test_adverse_excursion_can_only_endanger_an_account_never_rescue_it():
    """The property that makes the mode ladder safe to enable, proved on whole runs.

    Random sessions, random wicks. Going CLOSE_ONLY -> INTRABAR_CONSERVATIVE -> STRESS adds
    valid adverse marks and nothing else, so at each step:

        * the settled P&L is UNCHANGED - it is a barrier model, not a fill model
        * a liquidated account stays liquidated
        * days survived never increases
        * the minimum buffer never improves while the account is alive
        * the resampled survival probability never increases

    Any one of those failing would mean an excursion had bought the account something,
    which is not a thing an adverse excursion can do.
    """
    rng = np.random.default_rng(20260914)
    spec = make_spec("ES")
    strictly_worse = 0
    for _ in range(120):
        days = weekdays(int(rng.integers(4, 14)))
        sess, pos = [], []
        for d in days:
            n = 8
            c = 4000.0 + np.cumsum(rng.normal(0, 4.0, n))
            wick = np.abs(rng.normal(0, 6.0, n))
            sess.append(session(d, c, highs=c + wick, lows=c - wick))
            pos.append(np.where(rng.random(n) > 0.5, 1.0, -1.0))
        results = []
        for mode in (M.CLOSE_ONLY, M.INTRABAR_CONSERVATIVE, M.STRESS):
            led = ledger(spec, sess, pos, mode=mode)
            results.append((led, account(led, reps=40)))

        base_pnl = float(results[0][0].daily().sum())
        for led, _ in results[1:]:
            assert float(led.daily().sum()) == pytest.approx(base_pnl)

        for (_, softer), (_, harder) in zip(results, results[1:], strict=False):
            assert not (softer.liquidated and not harder.liquidated), \
                "an adverse excursion rescued a liquidated account"
            assert harder.days_survived <= softer.days_survived
            assert harder.p_survive_period <= softer.p_survive_period + 1e-12
            assert harder.max_intraday_drawdown <= softer.max_intraday_drawdown + 1e-9
            if not softer.liquidated and not harder.liquidated:
                assert harder.min_mll_buffer <= softer.min_mll_buffer + 1e-9
            if harder.liquidated and not softer.liquidated:
                strictly_worse += 1
    assert strictly_worse > 0, "the fuzz never flipped an account; it proves nothing"


def test_a_hundred_random_runs_reconcile_field_by_field_with_the_reference():
    """The cross-check the acceptance criteria name, at the sizes they name.

    One hundred randomly generated strategy paths, each turned into a canonical ledger, each
    run through BOTH the production twin and the independent reference, compared on every
    decision-relevant field. The DLL, the payout policy and the path mode all vary, because
    a cross-check that only ever exercised one configuration would prove one configuration.
    """
    rng = np.random.default_rng(777)
    spec_cache = {}
    checked = 0
    for trial in range(100):
        days = weekdays(int(rng.integers(3, 20)))
        contracts = int(rng.integers(1, 4))
        spec = spec_cache.setdefault(contracts, make_spec("ES", contracts=contracts))
        sess, pos = [], []
        for d in days:
            n = int(rng.integers(4, 10))
            c = 4000.0 + np.cumsum(rng.normal(0, float(rng.choice([2.0, 6.0, 12.0])), n))
            wick = np.abs(rng.normal(0, 5.0, n))
            sess.append(session(d, c, highs=c + wick, lows=c - wick))
            pos.append(np.where(rng.random(n) > 0.45, 1.0, -1.0))
        # index, not the member: `rng.choice` coerces an enum to a numpy string
        mode = (M.CLOSE_ONLY, M.INTRABAR_CONSERVATIVE,
                M.STRESS)[int(rng.integers(0, 3))]
        dll = float(rng.choice([0.0, 1_000.0])) or None
        frac = float(rng.choice([0.0, 0.5, 1.0]))
        led = ledger(spec, sess, pos, mode=mode)
        a = account(led, daily_loss_limit=dll, payout_fraction=frac, reps=20)
        assert a.cross_check.agrees, f"trial {trial} mode={mode} dll={dll}: " \
                                     f"{a.cross_check.mismatches}"
        # 16 fields always, plus a 17th only when the daily loss limit is armed.
        assert a.cross_check.fields_compared >= 16
        checked += a.cross_check.fields_compared
    assert checked >= 100 * 16


# ======================================================================================
# THE EXECUTION LADDER ITSELF
# ======================================================================================

def test_the_four_modes_are_distinct_and_ordered():
    """A ladder whose rungs coincide is one rung reported four times."""
    names = [p.name for p in em.LADDER]
    assert names == ["IDEAL", "BASELINE", "CONSERVATIVE", "STRESS"]
    slips = [p.slippage_ticks for p in em.LADDER]
    assert slips == sorted(slips) and len(set(slips)) == 4
    assert em.IDEAL.include_spread is False
    assert all(p.include_spread for p in em.LADDER[1:])
    assert [p.path_mode for p in em.LADDER] == [
        M.CLOSE_ONLY, M.CLOSE_ONLY, M.INTRABAR_CONSERVATIVE, M.STRESS]


def test_the_headline_is_never_the_ideal_mode():
    """The rule that stops the ladder becoming decoration."""
    assert em.HEADLINE == "CONSERVATIVE"
    assert em.HEADLINE != "IDEAL"
    assert em.get(em.HEADLINE).slippage_ticks > 0
    assert em.get(em.HEADLINE).include_spread is True


def test_every_mode_declares_every_assumption():
    """No field may be left for the reader to guess at."""
    required = {"execution_mode", "execution_path_mode", "slippage_ticks_round_turn",
                "spread_charged", "stop_execution", "target_execution",
                "flatten_execution", "partial_fill_model", "ambiguous_bar_model"}
    for p in em.LADDER:
        row = p.as_row()
        assert required <= set(row)
        assert all(row[k] not in (None, "") for k in required)


def test_the_execution_mode_is_stamped_on_every_ledger_record():
    """A result that omits the mode is not interpretable, so it cannot be produced."""
    spec = make_spec("ES")
    sess = [session(MONDAY, [4000.0, 4002.0])]
    for mode in (M.CLOSE_ONLY, M.INTRABAR_CONSERVATIVE, M.STRESS):
        led = ledger(spec, sess, [np.array([1.0, 0.0])], mode=mode)
        tf = led.trade_frame()
        assert (tf["execution_path_mode"] == mode.value).all()
        assert led.mode is mode
        assert account(led).execution_path_mode is mode


def test_ideal_costs_less_than_baseline_which_costs_less_than_stress():
    """The ladder has to bite. Identical fills, monotonically worse economics."""
    spec = make_spec("ES", cost=CostSpec())          # the published cost model
    sess = [session(MONDAY, [4000.0, 4002.0])]
    nets = []
    for p in em.LADDER:
        led = ledger(spec, sess, [np.array([1.0, 0.0])], mode=p.path_mode,
                     slip=p.slippage_ticks, spread=p.include_spread)
        nets.append(float(led.daily().sum()))
    assert nets == sorted(nets, reverse=True)
    assert len(set(nets)) == 4


# ======================================================================================
# THE PAYOUT LAYER, KEPT SEPARATE
# ======================================================================================

def test_payout_rules_are_versioned_and_carry_their_sources():
    """Configuration, not constants. A rule change must be visible in the result."""
    rules = PayoutRuleSet.as_documented(50_000)
    assert rules.version.startswith("topstep-50k-")
    assert rules.version.endswith(ts.RETRIEVED.isoformat())
    assert rules.account_size == 50_000
    for key in ("winning_days_required", "winning_day_minimum", "balance_share",
                "ceiling", "minimum", "profit_split", "mll_resets_on_payout"):
        assert key in rules.sources and "help.topstep.com" in rules.sources[key]
    # values come from the rulebook, not from literals repeated in the payout layer
    assert rules.winning_days_required == ts.XFA_WINNING_DAYS.value
    assert rules.ceiling == ts.XFA_STANDARD_CAP_BY_SIZE[50_000].value


def test_profitability_and_payout_eligibility_are_reported_separately():
    """A profitable account that has not earned a payout must say both things.

    Four sessions of +$400. The strategy is profitable and the account is healthy, but four
    winning days is one short of the five a payout needs - and the account is still in the
    Combine, where no payout exists at all.
    """
    days = weekdays(4)
    spec = make_spec("ES")
    sess = [session(d, [4000.0, 4008.0]) for d in days]
    a = account(ledger(spec, sess, [np.array([1.0, 0.0])] * 4))
    assert a.returns.net_pnl == pytest.approx(1_600.0)     # profitable
    assert a.liquidated is False                            # survives
    assert a.target_reached is False                        # no target
    assert a.payout.eligible_sessions == 0                  # no payout
    assert a.payout.total_paid == 0.0


def test_the_payout_policy_is_a_decision_and_the_rules_are_not():
    """Changing how much to withdraw must not look like changing what is allowed."""
    rules = PayoutRuleSet.as_documented(50_000)
    greedy = rules.to_policy(fraction=1.0)
    cautious = rules.to_policy(fraction=0.5, min_buffer_after=500.0)
    assert greedy.fraction != cautious.fraction
    assert cautious.min_buffer_after == 500.0
    assert rules.ceiling == PayoutRuleSet.as_documented(50_000).ceiling


def test_probabilities_are_labelled_as_scenario_estimates_not_forecasts():
    """Twenty-three and twenty-four on the field list, with their caveat attached."""
    days = weekdays(6)
    spec = make_spec("ES")
    sess = [session(d, [4000.0, 4004.0]) for d in days]
    a = account(ledger(spec, sess, [np.array([1.0, 0.0])] * 6), reps=50)
    assert 0.0 <= a.p_survive_period <= 1.0
    assert 0.0 <= a.p_target_before_violation <= 1.0
    assert 0.0 <= a.p_payout_eligible <= 1.0
    assert "PATH-MODEL SCENARIO ESTIMATE" in a.probability_note
    assert "Not a forecast" in a.probability_note
    assert a.resample_reps == 50


# ======================================================================================
# MONTHLY ANALYTICS, FROM THE SAME LEDGER
# ======================================================================================

def test_monthly_rows_sum_back_to_the_ledger():
    """The month table is a partition of the ledger, so it has to add up to it."""
    days = weekdays(45)
    spec = make_spec("ES")
    rng = np.random.default_rng(5)
    sess, pos = [], []
    for d in days:
        c = 4000.0 + np.cumsum(rng.normal(0, 2.0, 5))
        sess.append(session(d, c, highs=c + 1.0, lows=c - 1.0))
        pos.append(np.array([1.0, 1.0, 0.0, 0.0, 0.0]))
    led = ledger(spec, sess, pos)
    a = account(led, reps=30)
    assert len(a.monthly) >= 2
    assert sum(r.net_pnl for r in a.monthly) == pytest.approx(float(led.daily().sum()))
    assert sum(r.sessions for r in a.monthly) == len(led.sessions)
    assert sum(r.trades for r in a.monthly) == led.total_trades
    # equity is continuous across the month boundary
    for prev, nxt in zip(a.monthly, a.monthly[1:], strict=False):
        assert nxt.starting_equity == pytest.approx(prev.ending_equity)
    assert a.monthly[0].starting_equity == pytest.approx(0.0)


def test_the_four_return_bases_are_never_the_same_number_by_accident():
    """Conflating them is how a backtest reports an impossible percentage."""
    days = weekdays(3)
    spec = make_spec("ES", contracts=2)
    sess = [session(d, [4000.0, 4010.0]) for d in days]
    a = account(ledger(spec, sess, [np.array([1.0, 0.0])] * 3))
    r = a.returns
    assert r.net_pnl == pytest.approx(3_000.0)             # 10 pts x $50 x 2 x 3
    assert r.mean_notional == pytest.approx(4_000.0 * 50 * 2)
    assert r.return_on_notional_pct == pytest.approx(100 * 3_000.0 / 400_000.0)
    assert r.return_on_account_pct == pytest.approx(6.0)
    assert r.pnl_per_contract == pytest.approx(1_500.0)
    assert r.return_on_notional_pct != r.return_on_account_pct
    assert "what the ACCOUNT realised" in r.note


def test_account_constrained_pnl_diverges_from_strategy_pnl_when_the_account_dies():
    """The two numbers must be allowed to disagree, and the report must carry both."""
    days = weekdays(3)
    spec = make_spec("ES")
    sess = [session(days[0], [4000.0, 3958.0]),
            session(days[1], [4000.0, 4100.0]),
            session(days[2], [4000.0, 4100.0])]
    led = ledger(spec, sess, [np.array([1.0, 0.0])] * 3)
    a = account(led)
    assert float(led.daily().sum()) == pytest.approx(7_900.0)   # strategy looks great
    assert a.returns.net_pnl == pytest.approx(7_900.0)
    assert a.liquidated is True
    # The STRATEGY lost $2,100 on the session that killed the account. The ACCOUNT lost
    # exactly its $2,000 of room, because Topstep flattens AT the limit and there is no
    # further equity to lose. Reporting the strategy figure would overstate the damage,
    # and the $7,900 it went on to make is not the account's either.
    assert a.returns.pnl_under_account_constraints == pytest.approx(-2_000.0)


# ======================================================================================
# GOVERNORS
# ======================================================================================

def test_the_pipeline_imports_nothing_that_can_transmit_an_order():
    """Backtest is research-only. The separation is a test, not a convention."""
    import quant_brain.research.account_result as ar
    import quant_brain.research.canonical_ledger as cl
    import quant_brain.research.execution_modes as ex_m
    import quant_brain.research.ledger_builder as lb
    banned = ("requests", "httpx", "urllib3", "aiohttp", "websocket", "ib_async",
              "ib_insync", "projectx")
    for mod in (cl, lb, ar, ex_m):
        src = open(mod.__file__, encoding="utf-8").read()
        for name in banned:
            assert f"import {name}" not in src, f"{mod.__name__} imports {name}"
        assert "/api/Order" not in src
        assert "secrets.env" not in src


def test_a_spec_cannot_be_mutated_by_a_run():
    """The frozen strategy stays frozen. A run that edited its own spec is not a backtest."""
    spec = make_spec("ES")
    before = (spec.spec_hash, dataclasses.asdict(spec.exit),
              dataclasses.asdict(spec.sizing), dataclasses.asdict(spec.cost))
    sess = [session(MONDAY, [4000.0, 4002.0])]
    for mode in (M.CLOSE_ONLY, M.INTRABAR_CONSERVATIVE, M.STRESS):
        account(ledger(spec, sess, [np.array([1.0, 0.0])], mode=mode))
    after = (spec.spec_hash, dataclasses.asdict(spec.exit),
             dataclasses.asdict(spec.sizing), dataclasses.asdict(spec.cost))
    assert before == after


def test_a_run_is_deterministic():
    """Same spec, same bars, same mode, same everything - twice."""
    days = weekdays(8)
    spec = make_spec("ES")
    rng = np.random.default_rng(3)
    sess, pos = [], []
    for d in days:
        c = 4000.0 + np.cumsum(rng.normal(0, 3.0, 6))
        sess.append(session(d, c, highs=c + 2, lows=c - 2))
        pos.append(np.array([1.0, 1.0, 0.0, -1.0, 0.0, 0.0]))
    a = account(ledger(spec, sess, pos, mode=M.STRESS), reps=40)
    b = account(ledger(spec, sess, pos, mode=M.STRESS), reps=40)
    assert a.returns.net_pnl == b.returns.net_pnl
    assert a.terminal_stage == b.terminal_stage
    assert a.p_survive_period == b.p_survive_period
    assert a.min_mll_buffer == b.min_mll_buffer


def test_cost_is_charged_at_the_bar_each_leg_trades():
    """Half a round turn in, half out. The twin reads this path, so timing is not cosmetic.

    A single trade at zero P&L with a $10 round turn must show -$5 the moment it opens and
    -$10 when it closes. Charging it all at the exit would show the account $5 of buffer it
    had already spent.
    """
    spec = make_spec("ES", cost=CostSpec(commission_round_turn=10.0, include_spread=False))
    sess = [session(MONDAY, [4000.0, 4000.0, 4000.0])]
    led = ledger(spec, sess, [np.array([1.0, 1.0, 0.0])])
    s = led.sessions[0]
    assert s.marks[0] == pytest.approx(-5.0)
    assert s.marks[-1] == pytest.approx(-10.0)
    assert [f.cost for f in s.fills] == [5.0, 5.0]
    total, base, slip = cost_for(spec, 0.0, include_spread=False)
    assert total == pytest.approx(10.0) and slip == 0.0


def test_a_path_that_does_not_settle_where_the_trades_do_is_refused():
    """Fail closed. A snap that quietly absorbed a real gap would hide a broken fill model."""
    from quant_brain.research.canonical_ledger import build_session_ledger

    trades = ledger(make_spec("ES"), [session(MONDAY, [4000.0, 4010.0])],
                    [np.array([1.0, 0.0])]).sessions[0].trades
    broken = (dataclasses.replace(trades[0], net_pnl=trades[0].net_pnl + 5_000.0),)
    t = pd.date_range(pd.Timestamp("2026-01-05 14:30", tz="UTC"), periods=2, freq="1min")
    with pytest.raises(AssertionError, match="Refusing to snap it away"):
        build_session_ledger(MONDAY, list(t), np.array([4000.0, 4010.0]),
                             np.array([4000.0, 4010.0]), np.array([4000.0, 4010.0]),
                             broken, mode=M.CLOSE_ONLY, multiplier=50.0, contracts=1,
                             base_cost=0.0, slip_cost=0.0)


def test_the_reference_refuses_an_account_size_it_was_not_written_for():
    """A reference that guessed at the $150K row would reconcile against nothing."""
    days = weekdays(3)
    spec = make_spec("ES")
    sess = [session(d, [4000.0, 4002.0]) for d in days]
    a = account(ledger(spec, sess, [np.array([1.0, 0.0])] * 3), account_size=150_000)
    assert a.cross_check.agrees is False
    assert "$50,000 path only" in a.cross_check.mismatches[0]
    assert tr.SIZE == 50_000


def test_the_twin_trace_records_the_levels_the_breach_test_used():
    """The MLL and DLL paths are a record, not a recomputation."""
    days = weekdays(3)
    spec = make_spec("ES")
    sess = [session(d, [4000.0, 4010.0]) for d in days]
    a = account(ledger(spec, sess, [np.array([1.0, 0.0])] * 3), daily_loss_limit=1_000.0)
    path = a.mll_path()
    assert len(path) == 3
    assert list(path.columns[:6]) == ["session", "phase", "opening_balance",
                                      "closing_balance", "mll", "dll"]
    # session 1 opens at 50,000 with the limit 2,000 below and the daily limit 1,000 below
    assert path["mll"].iloc[0] == pytest.approx(48_000.0)
    assert path["dll"].iloc[0] == pytest.approx(49_000.0)
    # +$500 a session, so the limit trails up by $500 each time
    assert path["mll"].iloc[1] == pytest.approx(48_500.0)
    assert path["mll"].iloc[2] == pytest.approx(49_000.0)
    assert all(isinstance(d, tw.DayState) for d in a.trace)


def test_the_resampled_probabilities_use_the_configured_account():
    """The probabilities must be run on the SAME account the deterministic result was.

    A resampler that quietly built a fresh twin without the daily loss limit would report
    survival odds for an account nobody is trading, and the deterministic verdict beside it
    would be right - which is exactly the kind of disagreement nobody reads twice.

    Twelve sessions: nine small wins and three losses of $1,800. That is the shape the
    daily limit exists for. Unarmed, the third big loss kills the account on session five
    and every resampled ordering dies too. Armed, each big loss is capped at $1,000, the
    account survives all twelve, and 83% of orderings survive with it.
    """
    days = weekdays(12)
    spec = make_spec("ES")
    moves = [-36.0 if i % 4 == 0 else 4.0 for i in range(12)]
    sess = [session(d, [4000.0, 4000.0 + m]) for d, m in zip(days, moves, strict=True)]
    led = ledger(spec, sess, [np.array([1.0, 0.0])] * 12,
                 mode=M.INTRABAR_CONSERVATIVE)

    unarmed = account(led, daily_loss_limit=None, reps=300)
    armed = account(led, daily_loss_limit=1_000.0, reps=300)

    assert unarmed.liquidated is True and unarmed.days_survived == 5
    assert armed.liquidated is False and armed.days_survived == 12
    assert armed.dll_capped_sessions == 3 and unarmed.dll_capped_sessions == 0
    # The resampled odds have to move with the account, not sit at the unarmed value.
    assert unarmed.p_survive_period == 0.0
    assert armed.p_survive_period > 0.5
    assert armed.resample_reps == unarmed.resample_reps == 300


def test_the_ideal_mode_really_does_not_pay_the_spread():
    """IDEAL is the frictionless bound, and "frictionless" has to mean something.

    A builder that ignored the mode's `include_spread` would leave the ladder looking
    ordered - IDEAL still has less slippage - while quietly charging IDEAL a spread it is
    defined not to pay. The cost components are checked directly rather than through the
    net, which is where that would hide.
    """
    spec = make_spec("ES", cost=CostSpec())          # the published cost model
    with_spread, base_ws, _ = cost_for(spec, 0.0, include_spread=True)
    without, base_no, _ = cost_for(spec, 0.0, include_spread=False)
    assert base_ws > base_no > 0, "the spread has to be a real part of the base cost"
    assert without == pytest.approx(inst.get("ES").commission_round_turn)

    sess = [session(MONDAY, [4000.0, 4002.0])]
    per_mode = {}
    for p in em.LADDER:
        led = ledger(spec, sess, [np.array([1.0, 0.0])], mode=p.path_mode,
                     slip=p.slippage_ticks, spread=p.include_spread)
        per_mode[p.name] = float(led.trade_frame()["commission_and_spread"].iloc[0])
    assert per_mode["IDEAL"] == pytest.approx(base_no)
    assert per_mode["BASELINE"] == pytest.approx(base_ws)
    assert per_mode["IDEAL"] < per_mode["BASELINE"]
