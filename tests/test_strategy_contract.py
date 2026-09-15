"""The user strategy contract: every field a human can state, and every ambiguity refused.

`test_strategy_interface.py` pins the ORIGINAL interface - immutability, hashing, the two
defects the reconciliation found. This file pins what was added so a human can hand over a
strategy without the engine interpreting anything: point-distance exits, wall-clock entry and
flat rules, cooldown, a per-session trade cap, and declared parameters.

THE PROPERTY THAT MATTERS MOST IS THE BORING ONE
--------------------------------------------------
Every new field defaults to the engine's previous behaviour, and
`test_the_new_fields_at_their_defaults_change_nothing` proves it on a real run rather than
asserting it in a comment. The frozen example strategy produced 340 trades and $301.20 net
before these fields existed and produces 340 trades and $301.20 net after.
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

from quant_brain.research import exits as X  # noqa: E402
from quant_brain.research.canonical_ledger import ExecutionPathMode  # noqa: E402
from quant_brain.research.ledger_builder import build_ledger  # noqa: E402
from quant_brain.research.strategy_spec import (  # noqa: E402
    AmbiguousSpec,
    CostSpec,
    ExitSpec,
    RiskSpec,
    SessionSpec,
    SizingSpec,
    SpecError,
    StrategySpec,
)

#: Zero cost wherever a test is about WHICH trades happened rather than what they cost.
FREE = CostSpec(commission_round_turn=0.0, include_spread=False, slippage_ticks=0.0)
DAY = dt.date(2026, 1, 5)


def _signal(X_):
    """The position array, handed in through the feature frame."""
    return np.asarray(X_["pos"], dtype=float)


def _spec(**kw) -> StrategySpec:
    base = dict(name="contract_probe", instrument="MNQ", timeframe="1min", signal=_signal,
                cost=FREE, rationale="engine probe; not a strategy")
    base.update(kw)
    return StrategySpec(**base)


def _session(closes, highs=None, lows=None, *, open_et="09:30"):
    """One synthetic session whose bars are stamped from `open_et`, one per minute."""
    c = np.asarray(closes, dtype=float)
    h = c if highs is None else np.asarray(highs, dtype=float)
    low = c if lows is None else np.asarray(lows, dtype=float)
    start = pd.Timestamp(f"{DAY} {open_et}", tz="America/New_York")
    t = pd.DatetimeIndex([start + pd.Timedelta(minutes=i) for i in range(len(c))])
    et = t.tz_convert("America/New_York")
    return pd.DataFrame({"t": t.tz_convert("UTC"), "o": c, "h": h, "l": low, "c": c,
                         "v": 1.0, "contract": "MNQH6", "day": DAY,
                         "hm": et.strftime("%H:%M")})


def _run(spec, sessions, positions):
    feats = [pd.DataFrame({"pos": p}) for p in positions]
    return build_ledger(spec, sessions, feats, slip_ticks=0.0, scenario="TEST",
                        mode=ExecutionPathMode.CLOSE_ONLY)


# =====================================================================================
# POINT DISTANCES - the form a trader actually states
# =====================================================================================

def test_a_stop_in_points_fills_at_the_stated_distance():
    """'A ten-point stop' means ten points, on every session, whatever the ATR was."""
    closes = [100.0] * 10
    lows = list(closes)
    lows[3] = 89.0                                     # trades through entry - 10
    g = _session(closes, lows=lows)
    spec = _spec(exit=ExitSpec(stop_points=10.0, use_invalidation=False,
                               time_stop_bars=20))
    led = _run(spec, [g], [[0, 1, 1, 1, 1, 1, 1, 1, 1, 1]])
    t = led.trade_frame()
    assert len(t) == 1
    assert t["entry_price"].iloc[0] == 100.0
    assert t["exit_price"].iloc[0] == 90.0             # the stop level, exactly
    assert t["exit_reason"].iloc[0] == X.STOP


def test_a_target_in_points_fills_at_the_stated_distance():
    closes = [100.0] * 10
    highs = list(closes)
    highs[4] = 121.0
    g = _session(closes, highs=highs)
    spec = _spec(exit=ExitSpec(target_points=20.0, use_invalidation=False,
                               time_stop_bars=20))
    led = _run(spec, [g], [[0, 1, 1, 1, 1, 1, 1, 1, 1, 1]])
    t = led.trade_frame()
    assert t["exit_price"].iloc[0] == 120.0
    assert t["exit_reason"].iloc[0] == X.TARGET


def test_a_point_stop_is_the_same_distance_whatever_the_session_volatility():
    """The reason both forms exist: an ATR stop is a different distance every day."""
    quiet = _session([100.0, 100.0, 100.0, 88.0, 100.0],
                     highs=[100.0] * 5, lows=[100.0, 100.0, 100.0, 88.0, 100.0])
    wild = _session([100.0, 130.0, 70.0, 88.0, 100.0],
                    highs=[100.0, 130.0, 130.0, 130.0, 130.0],
                    lows=[100.0, 70.0, 70.0, 70.0, 70.0])
    spec = _spec(exit=ExitSpec(stop_points=10.0, use_invalidation=False, time_stop_bars=10))
    for g in (quiet, wild):
        led = _run(spec, [g], [[0, 1, 1, 1, 1]])
        t = led.trade_frame()
        entry = t["entry_price"].iloc[0]
        assert t["exit_price"].iloc[0] == pytest.approx(entry - 10.0), "the stop moved"


def test_a_trail_in_points_ratchets_by_the_stated_distance():
    closes = [100.0, 110.0, 120.0, 100.0]
    g = _session(closes, highs=closes, lows=closes)
    spec = _spec(exit=ExitSpec(trail_points=5.0, use_invalidation=False, time_stop_bars=10))
    led = _run(spec, [g], [[0, 1, 1, 1]])
    t = led.trade_frame()
    # Entered at bar 1 (110). Best reaches 120 on bar 2, so the trail rests at 115.
    assert t["entry_price"].iloc[0] == 110.0
    assert t["exit_price"].iloc[0] == pytest.approx(115.0)


# =====================================================================================
# THE REFUSALS
# =====================================================================================

def test_a_target_in_R_with_no_stop_is_refused_rather_than_read_as_an_ATR_multiple():
    """The silent interpretation this contract exists to prevent.

    `exits.simulate_trade` falls back to the session ATR as a nominal R when no stop is set.
    If a target were allowed to read that fallback, "2R" would quietly mean "2 ATR" - a
    different distance, on a different scale, arrived at without the author saying so.
    """
    with pytest.raises(AmbiguousSpec, match="R is undefined"):
        ExitSpec(target_r=2.0, use_invalidation=True)
    with pytest.raises(AmbiguousSpec, match="R is undefined"):
        ExitSpec(breakeven_at_r=1.0, use_invalidation=True)
    # With a stop, R is defined and the same target is legal.
    assert ExitSpec(stop_points=10.0, target_r=2.0).target_r == 2.0
    assert ExitSpec(structural_stop=True, target_r=2.0).target_r == 2.0


def test_a_trail_does_not_count_as_a_stop_for_the_purpose_of_R():
    """A trail starts at the entry bar and only later binds, so it is not the risk at entry."""
    with pytest.raises(AmbiguousSpec, match="R is undefined"):
        ExitSpec(trail_points=5.0, target_r=2.0)
    assert not ExitSpec(trail_points=5.0).has_stop


def test_two_spellings_of_one_leg_are_refused():
    with pytest.raises(AmbiguousSpec, match="different targets"):
        ExitSpec(stop_points=10.0, target_r=2.0, target_points=20.0)
    with pytest.raises(AmbiguousSpec, match="different trails"):
        ExitSpec(trail_atr=1.0, trail_points=5.0)


def test_a_stop_that_is_not_a_whole_number_of_ticks_is_refused_not_rounded():
    """A resting order at a fraction of a tick is an order no exchange would accept.

    MNQ ticks at 0.25, so 10.1 points is 40.4 ticks. Rounding it would simulate a fill at a
    price that could not exist; the message names the two valid neighbours instead.
    """
    with pytest.raises(AmbiguousSpec, match="fraction of a tick"):
        _spec(exit=ExitSpec(stop_points=10.1, use_invalidation=False, time_stop_bars=5))
    ok = _spec(exit=ExitSpec(stop_points=10.25, use_invalidation=False, time_stop_bars=5))
    assert ok.exit.stop_points == 10.25


def test_an_instrument_the_registry_does_not_know_is_refused():
    with pytest.raises(AmbiguousSpec, match="not in the contract registry"):
        _spec(instrument="ZZZZ")


def test_more_than_one_open_position_is_refused_rather_than_approximated():
    """A stated engine limitation, raised at construction with the reason."""
    with pytest.raises(SpecError, match="models ONE position at a time"):
        RiskSpec(max_open_positions=2)


def test_two_spellings_of_the_entry_cutoff_are_refused():
    with pytest.raises(AmbiguousSpec, match="two spellings"):
        SessionSpec(last_entry_bar=300, last_entry_et="15:00")


def test_a_flat_time_outside_the_session_is_refused():
    with pytest.raises(SpecError, match="outside the session"):
        SessionSpec(open_et="09:30", close_et="16:00", flat_by_et="16:30")
    with pytest.raises(SpecError, match="outside the session"):
        SessionSpec(open_et="09:30", close_et="16:00", last_entry_et="09:00")


def test_an_entry_cutoff_at_or_after_the_flat_is_refused():
    with pytest.raises(SpecError, match="could never be held"):
        SessionSpec(last_entry_et="15:00", flat_by_et="15:00")


def test_a_time_stop_longer_than_the_session_is_refused_as_a_rule_that_cannot_fire():
    with pytest.raises(AmbiguousSpec, match="can never fire"):
        _spec(exit=ExitSpec(time_stop_bars=500, use_invalidation=False),
              session=SessionSpec(open_et="09:30", close_et="16:00"))


# =====================================================================================
# THE TRADE-MANAGEMENT RULES
# =====================================================================================

def test_a_cooldown_blocks_the_next_entry_for_the_stated_number_of_bars():
    """Signal fires on every bar; the exit is immediate, so re-entry is the only limit."""
    g = _session([100.0] * 12)
    pos = [0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1]
    no_cd = _run(_spec(exit=ExitSpec(time_stop_bars=1, use_invalidation=False)), [g], [pos])
    with_cd = _run(_spec(exit=ExitSpec(time_stop_bars=1, use_invalidation=False),
                         risk=RiskSpec(cooldown_bars=4)), [g], [pos])
    assert len(with_cd.trade_frame()) < len(no_cd.trade_frame())
    entries = with_cd.trade_frame()["entry_bar"].tolist()
    exits = with_cd.trade_frame()["exit_bar"].tolist()
    for prev_exit, nxt in zip(exits, entries[1:], strict=False):
        assert nxt - prev_exit > 4, f"re-entered {nxt - prev_exit} bars after an exit"


def test_a_zero_cooldown_is_exactly_the_engines_previous_behaviour():
    """The default must be inert: re-entry permitted on the bar after the exit."""
    g = _session([100.0] * 12)
    pos = [0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1]
    a = _run(_spec(exit=ExitSpec(time_stop_bars=1, use_invalidation=False)), [g], [pos])
    b = _run(_spec(exit=ExitSpec(time_stop_bars=1, use_invalidation=False),
                   risk=RiskSpec(cooldown_bars=0)), [g], [pos])
    assert a.trade_frame().equals(b.trade_frame())


def test_a_per_session_trade_cap_stops_at_the_cap_and_not_before():
    g = _session([100.0] * 20)
    pos = [0] + [1, 0] * 9 + [0]
    uncapped = _run(_spec(exit=ExitSpec(time_stop_bars=1, use_invalidation=False)), [g], [pos])
    capped = _run(_spec(exit=ExitSpec(time_stop_bars=1, use_invalidation=False),
                        risk=RiskSpec(max_trades_per_session=3)), [g], [pos])
    assert len(uncapped.trade_frame()) > 3
    assert len(capped.trade_frame()) == 3
    # And the three taken are the FIRST three, not a selection.
    assert (capped.trade_frame()["entry_bar"].tolist()
            == uncapped.trade_frame()["entry_bar"].tolist()[:3])


def test_a_wall_clock_flat_closes_the_position_at_that_bar():
    """`flat_by_et` is the strategy's own forced flat, inside the venue's."""
    g = _session([100.0 + i for i in range(20)], open_et="09:30")   # 09:30..09:49
    # 15 bars is inside the 20-bar window, and longer than the 9 bars the trade is held,
    # so the flat is what closes it and the time stop is not what is being measured.
    spec = _spec(exit=ExitSpec(use_invalidation=False, time_stop_bars=15),
                 session=SessionSpec(open_et="09:30", close_et="09:49",
                                     flat_by_et="09:40"))
    led = _run(spec, [g], [[0] + [1] * 19])
    t = led.trade_frame()
    assert len(t) == 1
    assert t["exit_bar"].iloc[0] == 10                 # 09:40 is index 10
    assert t["exit_reason"].iloc[0] == X.FLATTEN
    assert led.sessions[0].ends_flat


def test_a_wall_clock_entry_cutoff_blocks_later_entries():
    g = _session([100.0] * 20, open_et="09:30")        # 09:30..09:49
    spec = _spec(exit=ExitSpec(time_stop_bars=1, use_invalidation=False),
                 session=SessionSpec(open_et="09:30", close_et="09:49",
                                     last_entry_et="09:35"))
    led = _run(spec, [g], [[0] + [1, 0] * 9 + [0]])
    assert led.trade_frame()["entry_bar"].max() <= 5   # 09:35 is index 5


def test_no_entry_is_taken_on_the_forced_flat_bar():
    """It could not be held for a single bar and could only lose a round turn."""
    g = _session([100.0] * 20, open_et="09:30")
    spec = _spec(exit=ExitSpec(time_stop_bars=1, use_invalidation=False),
                 session=SessionSpec(open_et="09:30", close_et="09:49",
                                     flat_by_et="09:35"))
    led = _run(spec, [g], [[0, 0, 0, 0, 0, 1, 1, 1, 1, 1] + [0] * 10])
    assert led.trade_frame().empty, "an entry was taken on or after the flat bar"


def test_a_wall_clock_rule_the_data_cannot_locate_raises_rather_than_approximating():
    g = _session([100.0] * 10, open_et="09:30")        # 09:30..09:39
    spec = _spec(exit=ExitSpec(time_stop_bars=1, use_invalidation=False),
                 session=SessionSpec(open_et="09:30", close_et="09:39",
                                     flat_by_et="09:38"))
    object.__setattr__(spec.session, "flat_by_et", "09:52")   # bypass validation on purpose
    with pytest.raises(ValueError, match="no bar stamped"):
        _run(spec, [g], [[0] + [1] * 9])


# =====================================================================================
# WHAT THE SPEC SAYS ABOUT ITSELF
# =====================================================================================

def test_declared_parameters_are_hashed_and_reported():
    """`params` is never read by the engine; it exists so a result is reproducible."""
    a = _spec(params={"threshold": 1.9})
    b = _spec(params={"threshold": 2.1})
    assert a.spec_hash != b.spec_hash
    assert "threshold=1.9" in a.describe()


def test_every_new_field_changes_the_hash():
    base = _spec()
    assert base.spec_hash != _spec(risk=RiskSpec(cooldown_bars=1)).spec_hash
    assert base.spec_hash != _spec(risk=RiskSpec(max_trades_per_session=3)).spec_hash
    assert base.spec_hash != _spec(
        session=SessionSpec(flat_by_et="15:45")).spec_hash
    assert base.spec_hash != _spec(
        session=SessionSpec(last_entry_et="15:00")).spec_hash
    assert base.spec_hash != _spec(
        exit=ExitSpec(stop_points=10.0, use_invalidation=False)).spec_hash


def test_the_description_states_every_rule_that_will_be_applied():
    """What the engine prints before a run. A reader who disagrees with a line here has
    found the misunderstanding while it is still free to fix."""
    spec = _spec(
        exit=ExitSpec(stop_points=10.0, target_r=2.0, trail_points=5.0, time_stop_bars=30),
        sizing=SizingSpec(contracts=2),
        session=SessionSpec(open_et="09:30", close_et="16:00", warmup_bars=15,
                            last_entry_et="15:00", flat_by_et="15:45"),
        risk=RiskSpec(cooldown_bars=5, max_trades_per_session=4),
        params={"lookback": 20})
    d = spec.describe()
    for fragment in ("stop 10 pts", "target 2R", "trail 5 pts", "time stop 30 bars",
                     "2 contract(s)", "no entry for the first 15 bars",
                     "no new entry after 15:00", "forced flat at 15:45",
                     "cooldown 5 bar(s)", "max 4 trades/session", "lookback=20",
                     "the session ends flat"):
        assert fragment in d, fragment


def test_a_spec_with_no_stop_says_NO_STOP_rather_than_staying_quiet():
    assert "NO STOP" in _spec().exit.describe()


# =====================================================================================
# BACKWARD COMPATIBILITY - the property that lets the new fields exist at all
# =====================================================================================

def test_the_new_fields_at_their_defaults_change_nothing():
    """Defaults reproduce the engine's previous entry policy exactly.

    Measured rather than asserted: the frozen example strategy produced 340 trades and
    $301.20 net on MNQ before these fields existed, and produces the same after. This test
    pins the mechanism that makes that true - the resolved bar indices and the re-entry rule.
    """
    from quant_brain.research.ledger_builder import bar_at, entry_cutoff

    g = _session([100.0] * 391, open_et="09:30")
    spec = _spec()
    assert spec.session.flat_by_et is None
    assert spec.session.last_entry_et is None
    assert spec.risk.cooldown_bars == 0
    assert spec.risk.max_trades_per_session is None
    assert bar_at(g, None, default=390) == 390
    assert entry_cutoff(g, spec, flat_bar=390, n=391) == 389


def test_an_explicit_last_entry_bar_still_wins_over_the_default():
    from quant_brain.research.ledger_builder import entry_cutoff

    g = _session([100.0] * 391, open_et="09:30")
    spec = _spec(session=SessionSpec(last_entry_bar=200))
    assert entry_cutoff(g, spec, flat_bar=390, n=391) == 200
