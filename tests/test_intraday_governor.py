"""The intraday runner's chain is no longer empty: the governor is armed on the first bar,
attached to the executor, told UNKNOWN on an unmarked bar, tripped by a HALT file - and the
in-loop close-out reaches the executor as a FLATTEN, which no engine may refuse.

Written failing-first against the runner as it stood: `Trader.step` called
`self.ex.submit(orders, t)` without `flatten=`, so every loss-limit and 15:38 close-out was a
MARKET intent. Harmless while the chain was empty; the first engine added would have been
able to refuse the order that closes the book.
"""
from __future__ import annotations

import intraday_trader as it
import pandas as pd
import pytest
from intraday_common import DAILY_LOSS_LIMIT

from quant_brain.core.execution import OrderIntent, OrderType, Side
from quant_brain.core.governor import Reason

NAV = 1_000_000.0


class FakeExecutor:
    def __init__(self):
        self.submitted: list[tuple[dict, bool]] = []
        self.to_settle: list[tuple] = []
        self._pending: dict[str, int] = {}
        self.attached = []

    def attach_governor(self, governor) -> bool:
        self.attached.append(governor)
        return True

    def submit(self, orders, when, flatten=False):
        self.submitted.append((dict(orders), flatten))
        for s, q in orders.items():
            self._pending[s] = self._pending.get(s, 0) + q

    def settle(self, t):
        out, self.to_settle = self.to_settle, []
        return out

    def pending_qty(self) -> dict[str, int]:
        return dict(self._pending)


class Hold:
    def __init__(self, targets=None):
        self.targets = targets or {}

    def decide(self, t, feats, pos, equity, state, params):
        return dict(self.targets)


def make(strategy=None, pos=None, cost=None):
    ex = FakeExecutor()
    book = it.Book()
    book.pos.update(pos or {})
    book.cost.update(cost or {})
    return it.Trader(strategy or Hold(), {}, 1.0, book, ex, False, "test"), ex


def bar(hh, mm):
    return pd.Timestamp(2026, 9, 11, hh, mm)


def buy(sym="SMCI"):
    return OrderIntent(sym, Side.BUY, 10)


def flat(sym="SMCI"):
    return OrderIntent(sym, Side.SELL, 300, order_type=OrderType.FLATTEN)


def test_governor_is_armed_on_the_first_bar_with_the_sleeves_dollar_limit(sink):
    t, ex = make(pos={"SMCI": 300}, cost={"SMCI": -30_000.0})
    assert t.governor is None
    t.step(bar(10, 0), {}, {"SMCI": 100.0}, NAV)
    assert t.governor is not None and ex.attached == [t.governor]
    assert t.governor.limits_engine.limits.max_daily_loss == pytest.approx(DAILY_LOSS_LIMIT * NAV)
    assert "governor_armed" in sink.kinds()
    assert t.view.daily_pnl == pytest.approx(0.0)
    assert t.governor(buy()).allowed


def test_an_unmarked_position_makes_the_governor_refuse_new_entries_but_not_the_flatten(sink):
    # A held symbol with NO price ever seen is unmarked (a dropped bar after a price is marked
    # at the last known level - AUD-05 - and is not this case).
    t, ex = make(Hold({"SMCI": 0.03}), pos={"SMCI": 300}, cost={"SMCI": -30_000.0})
    t.step(bar(10, 0), {}, {}, NAV)
    assert "unmarked_positions" in sink.kinds()
    assert t.view.daily_pnl is None
    d = t.governor(buy())
    assert not d.allowed and d.binding == (Reason.DATA_UNAVAILABLE.value,)
    assert t.governor(flat()).allowed
    assert not t.stopped, "AUD-05: a data gap must not end the session"
    assert not any(o.get("SMCI", 0) < 0 for o, _ in ex.submitted)
    t.step(bar(10, 1), {}, {"SMCI": 100.0}, NAV)          # a price arrives: known again
    assert t.view.daily_pnl == pytest.approx(0.0) and t.governor(buy()).allowed


def test_a_dropped_bar_after_a_price_is_marked_at_the_last_level_and_stays_known(sink):
    t, _ex = make(Hold({"SMCI": 0.03}), pos={"SMCI": 300}, cost={"SMCI": -30_000.0})
    t.step(bar(10, 0), {}, {"SMCI": 100.0}, NAV)
    t.step(bar(10, 1), {}, {}, NAV)                       # AUD-05: marked at 100, not zero
    assert t.view.daily_pnl == pytest.approx(0.0) and t.governor(buy()).allowed


def test_loss_limit_close_out_reaches_the_executor_as_a_flatten(sink):
    t, ex = make(Hold({"SMCI": 0.03}), pos={"SMCI": 300}, cost={"SMCI": -30_000.0})
    t.step(bar(10, 0), {}, {"SMCI": 100.0}, NAV)
    t.step(bar(10, 1), {}, {"SMCI": 10.0}, NAV)           # -27,000 on 1,000,000 = -2.7%
    assert t.stopped
    orders, flatten = ex.submitted[-1]
    assert orders == {"SMCI": -300} and flatten is True, ex.submitted
    d = t.governor(buy())
    assert not d.allowed and d.binding == (Reason.RISK_DAILY_LOSS.value,)
    assert t.governor(flat()).allowed


def test_a_bar_inside_the_limit_still_allows_entries(sink):
    t, _ex = make(Hold({"SMCI": 0.03}), pos={"SMCI": 300}, cost={"SMCI": -30_000.0})
    t.step(bar(10, 0), {}, {"SMCI": 100.0}, NAV)
    t.step(bar(10, 1), {}, {"SMCI": 20.0}, NAV)           # -24,000 = -2.4%, inside 2.5%
    assert not t.stopped
    assert t.governor(buy()).allowed


def test_halt_file_trips_manual_halt_once(sink, tmp_path, monkeypatch):
    halt = tmp_path / "HALT"
    monkeypatch.setattr(it, "HALT_FILES", [halt])
    t, ex = make(Hold({"SMCI": 0.03}), pos={"SMCI": 300}, cost={"SMCI": -30_000.0})
    t.step(bar(10, 0), {}, {"SMCI": 100.0}, NAV)
    assert not t.governor.halted
    halt.write_text("stop")
    t.step(bar(10, 1), {}, {"SMCI": 100.0}, NAV)
    sw = t.governor.switches[Reason.MANUAL_HALT]
    assert sw.tripped and "HALT file" in sw.detail
    since = sw.tripped_at
    t.step(bar(10, 2), {}, {"SMCI": 100.0}, NAV)
    assert sw.tripped_at == since, "a switch already tripped is not re-tripped every bar"
    d = t.governor(buy())
    assert not d.allowed and d.binding == (Reason.MANUAL_HALT.value,)
    assert ex.submitted[-1][1] is True, "the HALT close-out is a FLATTEN"


def test_no_publish_outside_a_persisting_run(sink, monkeypatch):
    calls = []
    monkeypatch.setattr(it.Trader, "_publish_governor", lambda self: calls.append(1))
    t, _ex = make(pos={"SMCI": 300}, cost={"SMCI": -30_000.0})
    t.step(bar(10, 0), {}, {"SMCI": 100.0}, NAV)
    assert calls == [] and not t.persist
    t.persist = True
    t.step(bar(10, 1), {}, {"SMCI": 100.0}, NAV)
    assert calls == [1]
