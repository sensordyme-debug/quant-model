"""The four open P0s in the deployed intraday runner (AUD-05, 06, 08, 09).

Each of these can place a wrong order, leave risk open, or liquidate the book. They are
written failing-first: every test in this file failed against the runner as it stood before
the fix commit, and the docstring on each says what the observed defect was.

    AUD-05  a missing bar marks an open position at $0, so one dropped minute reads as a
            total loss, breaches the 2.5% daily limit and flattens the whole book
    AUD-06  in-flight orders are invisible to sizing and to the flatten, so the same delta
            is resent every minute until it books
    AUD-08  start-up and --flatten sell what the BOOK says, not what the ACCOUNT holds
    AUD-09  a NaN price passes the price guard and raises inside math.floor, skipping the
            whole step including the flatten; and notify() runs before the loss-limit submit
"""
from __future__ import annotations

import math
from types import SimpleNamespace

import intraday_trader as it
import pandas as pd
import pytest
from intraday_common import DAILY_LOSS_LIMIT

NAV = 1_000_000.0


class FakeExecutor:
    """Records submissions and can hold orders in flight, the way a real one does.

    `pending` is the part the old FakeExecutor did not model at all, which is why AUD-06
    was invisible to the suite: every fake order settled instantly, so the runner never saw
    its own outstanding quantity.
    """

    def __init__(self):
        self.submitted: list[dict] = []
        self.to_settle: list[tuple] = []
        self._pending: dict[str, int] = {}

    def submit(self, orders, when, flatten=False):
        self.submitted.append(dict(orders))
        for s, q in orders.items():
            self._pending[s] = self._pending.get(s, 0) + q

    def settle(self, t):
        out, self.to_settle = self.to_settle, []
        for s, q, _px, _c in out:
            left = self._pending.get(s, 0) - q
            if left:
                self._pending[s] = left
            else:
                self._pending.pop(s, None)
        return out

    def pending_qty(self) -> dict[str, int]:
        return dict(self._pending)


class FakeStrategy:
    def __init__(self, targets=None):
        self.targets = targets or {}

    def decide(self, t, feats, pos, equity, state, params):
        return dict(self.targets)


def make(strategy=None, pos=None, cost=None, closed=0.0, dry_run=False, mode="test"):
    ex = FakeExecutor()
    book = it.Book()
    book.pos.update(pos or {})
    book.cost.update(cost or {})
    book._closed = closed
    t = it.Trader(strategy or FakeStrategy(), {}, 1.0, book, ex, dry_run, mode)
    return t, ex


def bar(hh, mm):
    return pd.Timestamp(2026, 9, 11, hh, mm)


# ============================================================== AUD-05: the missing bar

def test_a_missing_price_does_not_mark_the_position_to_zero(sink):
    """The defect: Yahoo drops SMCI for one minute, a $30k long reads as a $30k loss.

    Two bars. The first carries a price, the second does not. The sleeve P&L on the second
    bar must be unchanged, not -30,000.
    """
    t, _ex = make(pos={"SMCI": 300}, cost={"SMCI": -30_000.0})
    pnl_first = t.step(bar(10, 0), {}, {"SMCI": 100.0}, NAV)
    pnl_gap = t.step(bar(10, 1), {}, {}, NAV)          # feed dropped the symbol
    assert pnl_first == pytest.approx(0.0)
    assert pnl_gap == pytest.approx(0.0), "a dropped bar must not book a loss"


def test_a_missing_price_does_not_trip_the_daily_loss_limit(sink):
    """The consequence the audit describes: the whole book gets flattened for the day.

    The strategy is asked to KEEP the position, so any sale here could only come from the
    risk gate. `stopped` is the flag that ends the session - that is the thing that must not
    fire on a data gap.
    """
    hold = FakeStrategy({"SMCI": 0.03})
    t, ex = make(hold, pos={"SMCI": 300}, cost={"SMCI": -30_000.0})
    t.step(bar(10, 0), {}, {"SMCI": 100.0}, NAV)
    t.step(bar(10, 1), {}, {}, NAV)
    assert not t.stopped, "an unmarked symbol must not trip the loss limit"
    assert "loss_limit" not in sink.kinds()
    assert not any(o.get("SMCI", 0) < 0 for o in ex.submitted), ex.submitted


def test_an_unmarked_position_is_alerted_not_swallowed(sink):
    t, _ = make(pos={"SMCI": 300}, cost={"SMCI": -30_000.0})
    t.step(bar(10, 0), {}, {}, NAV)                     # never had a price
    assert "unmarked" in " ".join(sink.kinds()).lower() or any(
        "unmark" in a.lower() or "mark" in a.lower() for a in sink.alerts), sink.log


def test_a_genuine_loss_still_trips_the_limit(sink):
    """The guard must not disarm the limit itself - that would be a worse defect."""
    t, _ex = make(pos={"NVDA": 1000}, cost={"NVDA": -100_000.0})
    t.step(bar(10, 0), {}, {"NVDA": 100.0}, NAV)
    loss_px = 100.0 - (DAILY_LOSS_LIMIT * NAV * 1.1) / 1000
    t.step(bar(10, 1), {}, {"NVDA": loss_px}, NAV)
    assert t.stopped, "a real, fully-marked loss must still stop the day"


def test_last_known_price_is_used_rather_than_zero(sink):
    """A stale mark is wrong by the size of the move; a zero mark is wrong by the notional."""
    t, _ = make(pos={"NVDA": 100}, cost={"NVDA": -10_000.0})
    t.step(bar(10, 0), {}, {"NVDA": 110.0}, NAV)
    pnl = t.step(bar(10, 1), {}, {}, NAV)
    assert pnl == pytest.approx(1_000.0)                # held at the last good mark


# ============================================================== AUD-06: in-flight orders

def test_the_same_delta_is_not_resent_while_an_order_is_in_flight(sink):
    """The defect: sizing reads book.pos only, so an unfilled buy is reordered every minute."""
    t, ex = make(FakeStrategy({"NVDA": 0.10}))
    t.step(bar(10, 0), {}, {"NVDA": 100.0}, NAV)
    assert ex.submitted and ex.submitted[0]["NVDA"] > 0
    first = dict(ex.submitted[0])
    t.step(bar(10, 1), {}, {"NVDA": 100.0}, NAV)        # nothing filled yet
    resent = ex.submitted[1] if len(ex.submitted) > 1 else {}
    assert not resent.get("NVDA"), f"resent {resent} on top of in-flight {first}"


def test_a_slow_fill_at_the_flatten_does_not_become_a_double_sell(sink):
    """15:38 sends the sell, 15:39 must not send it again and 15:40 must not buy it back."""
    t, ex = make(pos={"NVDA": 500}, cost={"NVDA": -50_000.0})
    t.step(bar(15, 38), {}, {"NVDA": 100.0}, NAV)
    assert ex.submitted[-1] == {"NVDA": -500}
    t.step(bar(15, 39), {}, {"NVDA": 100.0}, NAV)       # still unfilled
    assert not ex.submitted[-1].get("NVDA") or len(ex.submitted) == 1, ex.submitted


def test_sizing_nets_pending_into_the_current_position(sink):
    """A half-filled buy must reduce the remaining delta, not be ignored."""
    t, ex = make(FakeStrategy({"NVDA": 0.10}))
    t.step(bar(10, 0), {}, {"NVDA": 100.0}, NAV)
    want = ex.submitted[0]["NVDA"]
    ex.to_settle = [("NVDA", want // 2, 100.0, 1.0)]    # half fills
    t.step(bar(10, 1), {}, {"NVDA": 100.0}, NAV)
    total = sum(o.get("NVDA", 0) for o in ex.submitted)
    assert total == pytest.approx(want, abs=2), f"over-ordered: {ex.submitted}"


def test_a_filled_order_frees_the_symbol_for_further_sizing(sink):
    """The netting must not permanently block a symbol once its order completes."""
    t, ex = make(FakeStrategy({"NVDA": 0.10}))
    t.step(bar(10, 0), {}, {"NVDA": 100.0}, NAV)
    q = ex.submitted[0]["NVDA"]
    ex.to_settle = [("NVDA", q, 100.0, 1.0)]
    t.step(bar(10, 1), {}, {"NVDA": 100.0}, NAV)
    t.strategy.targets = {"NVDA": 0.20}                  # ask for more
    t.step(bar(10, 2), {}, {"NVDA": 100.0}, NAV)
    assert ex.submitted[-1].get("NVDA", 0) > 0


# ============================================================== AUD-09: NaN and ordering

def test_a_nan_price_does_not_raise_and_does_not_skip_the_flatten(sink):
    """The defect: `if not px` passes NaN (`not nan` is False), then math.floor raises and
    the exception skips the WHOLE step, including the end-of-day flatten."""
    t, ex = make(pos={"NVDA": 500, "TSLA": 100}, cost={"NVDA": -50_000.0, "TSLA": -20_000.0})
    t.step(bar(15, 38), {}, {"NVDA": float("nan"), "TSLA": 200.0}, NAV)
    assert ex.submitted, "the flatten must still have been attempted"
    assert ex.submitted[-1].get("TSLA") == -100, "the markable symbol must still be flattened"


def test_a_nan_target_price_is_skipped_in_sizing(sink):
    t, ex = make(FakeStrategy({"NVDA": 0.10, "TSLA": 0.10}))
    t.step(bar(10, 0), {}, {"NVDA": float("nan"), "TSLA": 200.0}, NAV)
    sent = ex.submitted[0] if ex.submitted else {}
    assert "NVDA" not in sent
    assert sent.get("TSLA", 0) > 0


def test_infinite_price_is_rejected_too():
    t, ex = make(FakeStrategy({"NVDA": 0.10}))
    t.step(bar(10, 0), {}, {"NVDA": math.inf}, NAV)
    assert not (ex.submitted and ex.submitted[0].get("NVDA"))


def test_the_flatten_order_is_submitted_before_the_alert_is_sent(sink):
    """The defect: notify() can block up to 45 s and ran BEFORE the flatten submit, so the
    book stayed open across the alert. Order of effects is what is asserted."""
    t, ex = make(pos={"NVDA": 1000}, cost={"NVDA": -100_000.0})
    t.step(bar(10, 0), {}, {"NVDA": 100.0}, NAV)
    loss_px = 100.0 - (DAILY_LOSS_LIMIT * NAV * 1.2) / 1000
    t.step(bar(10, 1), {}, {"NVDA": loss_px}, NAV)
    assert t.stopped
    assert ex.submitted and ex.submitted[-1] == {"NVDA": -1000}
    assert t.submit_before_notify is True, "the flatten must be on the wire before notify()"


# ============================================================== AUD-08: book vs account

def test_reconcile_adopts_the_accounts_position_when_the_book_disagrees():
    """A position closed by any other path becomes an untracked short at the next open."""
    book = it.Book()
    book.pos.update({"NVDA": 500})
    book.cost.update({"NVDA": -50_000.0})
    changes = it.reconcile_book(book, account={"NVDA": 0}, universe=["NVDA"])
    assert book.pos.get("NVDA", 0) == 0
    assert changes and changes[0][0] == "NVDA"


def test_reconcile_adopts_a_position_the_book_never_knew_about():
    book = it.Book()
    changes = it.reconcile_book(book, account={"TSLA": -200}, universe=["NVDA", "TSLA"])
    assert book.pos.get("TSLA") == -200
    assert changes


def test_reconcile_ignores_symbols_outside_the_sleeve_universe():
    """The daily sleeve's holdings are foreign and must not be adopted or sold."""
    book = it.Book()
    changes = it.reconcile_book(book, account={"SPY": 1000}, universe=["NVDA", "TSLA"])
    assert "SPY" not in book.pos
    assert not changes


def test_reconcile_is_a_no_op_when_the_book_already_agrees():
    book = it.Book()
    book.pos.update({"NVDA": 500})
    assert it.reconcile_book(book, account={"NVDA": 500}, universe=["NVDA"]) == []


def test_reconcile_reports_every_discrepancy_for_the_log():
    book = it.Book()
    book.pos.update({"NVDA": 500, "TSLA": 100})
    changes = dict((s, (a, b)) for s, a, b in
                   it.reconcile_book(book, account={"NVDA": 400, "TSLA": 100, "AMD": 50},
                                     universe=["NVDA", "TSLA", "AMD"]))
    assert changes["NVDA"] == (500, 400)
    assert changes["AMD"] == (0, 50)
    assert "TSLA" not in changes



def test_live_executor_settle_keeps_adapter_orders_authoritative():
    """A submitted fill must be booked once and removed from the adapter's list."""
    trade = SimpleNamespace(
        orderStatus=SimpleNamespace(status="Filled"),
        order=SimpleNamespace(orderId=17, action="BUY", totalQuantity=10),
        contract=SimpleNamespace(symbol="NVDA"),
        fills=[SimpleNamespace(
            execution=SimpleNamespace(shares=10, price=100.0),
            commissionReport=SimpleNamespace(commission=1.0), time=None,
        )],
    )
    executor = object.__new__(it.LiveExecutor)
    executor.ib = SimpleNamespace(sleep=lambda _seconds: None)
    executor.adapter = SimpleNamespace(open=[trade])

    fills = executor.settle(None)

    assert fills == [("NVDA", 10, 100.0, 1.0)]
    assert executor.adapter.open == []


def test_live_executor_hard_refuses_transmission_during_remediation(sink):
    """No entry, flatten, stale approval, or environment can reach IBKR now."""
    executor = object.__new__(it.LiveExecutor)
    assert executor.submit({"NVDA": 10}, None) == []
    assert "order_transmission_refused" in sink.kinds()


def test_live_loop_exit_uses_wall_clock_not_unassigned_bar_timestamp():
    """The exit guard must work before any feed bar has assigned local `t`."""
    source = it.Path(it.__file__).read_text(encoding="utf-8")
    assert "exit_minute_for(now.date())" in source
    assert "exit_minute_for(t.date())" in source  # replay still correctly uses bar time

# ============================================ AUD-07 live wiring + AUD-09 crash/feed guards

def test_flatten_minute_is_the_constant_on_a_regular_session():
    """Behaviour on a normal day must be byte-identical to before the change."""
    import datetime as _dt

    from intraday_common import FLATTEN_MINUTE
    assert it.flatten_minute_for(_dt.date(2026, 9, 11)) == FLATTEN_MINUTE == 368


def test_flatten_minute_moves_in_on_an_early_close():
    """2026-11-27 is a 13:00 close: 210 minutes, so bar 368 never arrives."""
    import datetime as _dt
    assert it.flatten_minute_for(_dt.date(2026, 11, 27)) == 188      # 210 - 22


def test_exit_minute_moves_in_on_an_early_close():
    import datetime as _dt
    assert it.exit_minute_for(_dt.date(2026, 11, 27)) == 192         # 210 - 18


def test_flatten_minute_falls_back_rather_than_raising_on_a_closed_day():
    """A calendar that cannot answer must not become a trading outage."""
    import datetime as _dt

    from intraday_common import FLATTEN_MINUTE
    assert it.flatten_minute_for(_dt.date(2026, 11, 26)) == FLATTEN_MINUTE   # Thanksgiving


def test_expected_latest_bar_before_the_open_is_the_prior_session_close():
    """AUD-09: at the 09:25 launch the newest bar IS yesterday's 15:59, so comparing it to
    the wall clock reported ~1,046 minutes of delay and the IB feed was never selected."""
    from intraday_common import ET as _ET
    now = pd.Timestamp("2026-09-11 09:25", tz=_ET)
    ref = it.expected_latest_bar(now)
    assert ref is not None
    assert (ref.date(), ref.hour, ref.minute) == (pd.Timestamp("2026-09-10").date(), 15, 59)


def test_expected_latest_bar_during_the_session_is_the_previous_minute():
    from intraday_common import ET as _ET
    now = pd.Timestamp("2026-09-11 11:07", tz=_ET)
    assert it.expected_latest_bar(now) == pd.Timestamp("2026-09-11 11:06", tz=_ET)


def test_expected_latest_bar_respects_an_early_close():
    from intraday_common import ET as _ET
    now = pd.Timestamp("2026-11-27 15:30", tz=_ET)      # after the 13:00 close
    ref = it.expected_latest_bar(now)
    assert (ref.hour, ref.minute) == (12, 59)


def test_the_probe_delay_is_now_zero_pre_open_instead_of_a_thousand_minutes():
    """The arithmetic the fix changes, stated directly."""
    from intraday_common import ET as _ET
    now = pd.Timestamp("2026-09-11 09:25", tz=_ET)
    latest = pd.Timestamp("2026-09-10 15:59", tz=_ET)   # what IBKR legitimately returns
    old_delay = (now - latest).total_seconds() / 60.0 - 1.0
    new_delay = (it.expected_latest_bar(now) - latest).total_seconds() / 60.0
    assert old_delay > 1000            # the old comparison: always "stale", always Yahoo
    assert new_delay == 0.0            # the new one: the feed is current


def test_guarded_main_reports_a_crash_instead_of_dying_silently(monkeypatch, sink):
    """AUD-09: a yfinance KeyError killed the process with a position open and no alert."""
    def boom():
        raise KeyError("yfinance dropped a column")

    monkeypatch.setattr(it, "main", boom)
    assert it.guarded_main() == 4
    assert "crashed" in sink.kinds()
    assert any("CRASHED" in a for a in sink.alerts), sink.alerts


def test_guarded_main_passes_through_a_normal_exit(monkeypatch, sink):
    monkeypatch.setattr(it, "main", lambda: 0)
    assert it.guarded_main() == 0
    assert "crashed" not in sink.kinds()


def test_guarded_main_does_not_swallow_systemexit(monkeypatch):
    def bye():
        raise SystemExit(3)

    monkeypatch.setattr(it, "main", bye)
    with pytest.raises(SystemExit):
        it.guarded_main()
