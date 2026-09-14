"""Tests for the end-to-end Topstep baseline script.

The script is the integration proof, so what needs defending is not the strategy - which is
deliberately trivial - but that the sessions it hands the twin are correct: real intraday
paths, costs actually charged, and no session silently dropped or double-counted.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import futures_topstep_baseline as base  # noqa: E402

from quant_brain.markets.futures_cme import execution_sim as ex  # noqa: E402
from quant_brain.markets.futures_cme import instruments as inst  # noqa: E402


def _bars(day: dt.date, closes: list[float], contract: str = "ESU5") -> pd.DataFrame:
    """One synthetic RTH session, one bar a minute from 09:30 ET."""
    start = pd.Timestamp(f"{day} 09:30", tz="America/New_York")
    t = pd.date_range(start, periods=len(closes), freq="1min")
    return pd.DataFrame({
        "t": t.tz_convert("UTC"), "o": closes, "h": closes, "l": closes, "c": closes,
        "v": [10.0] * len(closes), "contract": [contract] * len(closes),
    })


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    """The column derivation `load` does, without needing the real parquet on disk."""
    df = df.sort_values("t").reset_index(drop=True)
    et = df["t"].dt.tz_convert("America/New_York")
    df["et"] = et
    df["day"] = et.dt.date
    df["hm"] = et.dt.strftime("%H:%M")
    rth = df[(df["hm"] >= base.OPEN_ET) & (df["hm"] <= "16:00")].copy()
    assert isinstance(rth, pd.DataFrame)
    return rth


def _session(closes: list[float], day=dt.date(2025, 6, 10), **kw):
    return base.sessions(_prepare(_bars(day, closes)), **kw)


def _rising(n: int = 380, step: float = 0.25) -> list[float]:
    return [6000.0 + i * step for i in range(n)]


# ======================================================================================
# THE SESSIONS HANDED TO THE TWIN
# ======================================================================================

def test_a_session_carries_a_real_intraday_path_not_a_synthetic_one():
    """The point of the whole exercise: Topstep's MLL is tested against this path."""
    out = _session(_rising())
    assert len(out) == 1
    d = out[0]
    assert len(d.path) > 300, "the path should be one point a minute, not a three-point shape"
    assert d.path[-1] == pytest.approx(d.pnl), "the path must end at the session's P&L"


def test_the_direction_is_the_first_thirty_minutes():
    up = _session(_rising())[0]
    down = _session([6000.0 - i * 0.25 for i in range(380)])[0]
    # A monotone market: the strategy is right in both directions, so both make money.
    assert up.pnl > 0 and down.pnl > 0


def test_a_reversal_after_the_signal_loses_money():
    closes = [6000.0 + i * 0.25 for i in range(31)]            # up in the first 30 min
    closes += [closes[-1] - i * 0.25 for i in range(349)]      # then straight back down
    assert _session(closes)[0].pnl < 0


def test_the_round_turn_cost_is_actually_charged():
    """A flat session must lose exactly the modelled cost, not zero."""
    flat = _session([6000.0] * 380)[0]
    sim = ex.ExecutionSimulator(cost=ex.CostModel.for_contract(base.SYMBOL),
                                symbol=base.SYMBOL)
    assert flat.pnl == pytest.approx(-sim.round_turn_cost(1.0))
    assert flat.pnl == pytest.approx(-2.47), "MES: $1 commission round turn plus one tick"


def test_cost_scales_with_contracts():
    one = _session([6000.0] * 380, contracts=1)[0]
    four = _session([6000.0] * 380, contracts=4)[0]
    assert four.pnl == pytest.approx(4 * one.pnl)


def test_pnl_uses_the_micro_multiplier():
    """Sizing this in ES would put a 40-point day past a $2,000 MLL on its own."""
    out = _session(_rising(step=1.0))[0]
    mult = inst.get(base.SYMBOL).spec.multiplier
    assert mult == 5.0
    # Entry at 10:00 (bar 30), exit at 15:45 (bar 375): 345 points at $5.
    assert out.pnl == pytest.approx(345 * 1.0 * 5.0 - 2.47, abs=0.01)


def test_a_roll_day_is_excluded_rather_than_traded_across():
    """Two instruments in one session is not one session."""
    day = dt.date(2025, 6, 10)
    a = _bars(day, _rising(200), contract="ESU5")
    b = _bars(day, _rising(200), contract="ESZ5")
    b["t"] = b["t"] + pd.Timedelta(minutes=200)
    assert base.sessions(_prepare(pd.concat([a, b]))) == []


def test_a_short_session_is_skipped_not_patched():
    assert _session([6000.0] * 40) == []          # 10 bars after the signal, under the floor


def test_a_session_missing_its_signal_bar_is_skipped():
    closes = _rising()
    df = _prepare(_bars(dt.date(2025, 6, 10), closes))
    df = df[df["hm"] != base.SIGNAL_ET]
    assert base.sessions(df) == []


def test_each_session_appears_once():
    df = _prepare(pd.concat([_bars(dt.date(2025, 6, 10), _rising()),
                             _bars(dt.date(2025, 6, 11), _rising())]))
    out = base.sessions(df)
    assert len(out) == 2
    assert len({d.day for d in out}) == 2


def test_the_exit_is_before_the_close():
    """Topstep requires flat into the close; the specification must respect it."""
    assert base.EXIT_ET < "16:00"
    out = _session(_rising())[0]
    # 09:30 open, 10:00 signal, 15:45 exit -> 346 marks inclusive.
    assert len(out.path) == 346


# ======================================================================================
# THE REAL STORE, WHEN IT IS PRESENT
# ======================================================================================

@pytest.mark.skipif(not base.STORE.exists(), reason="no futures store on this machine")
def test_the_real_store_produces_usable_sessions():
    days = base.sessions(base.load())
    assert len(days) > 300, f"only {len(days)} sessions from the real store"
    assert all(d.path for d in days), "every session must carry an intraday path"
    assert all(len(d.path) > 100 for d in days), "a path of a few points is not a real one"


@pytest.mark.skipif(not base.STORE.exists(), reason="no futures store on this machine")
def test_the_real_sessions_run_through_the_twin_without_being_refused():
    """The strict-path guard is the integration test: it refuses anything not real."""
    from quant_brain.markets.futures_cme import twin as tw
    days = base.sessions(base.load())
    t = tw.TopstepTwin(50_000, profit_target=3_000.0)
    r = t.run(days)
    assert r.days > 0
    assert r.path_supplied is True
