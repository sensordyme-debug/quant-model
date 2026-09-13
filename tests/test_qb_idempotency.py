"""Deterministic intent ids, and an executor that will not send the same one twice."""
from __future__ import annotations

import datetime as dt
import threading
from typing import Any

import pytest

from quant_brain.core.execution import (
    OrderIntent,
    OrderType,
    RoutedExecutor,
    Side,
    SimulatedAdapter,
)
from quant_brain.core.idempotency import (
    Duplicate,
    IntentJournal,
    IntentState,
    intent_id,
)
from quant_brain.core.mode import Authority
from quant_brain.core.risk import RiskChain

UTC = dt.UTC
TS = dt.datetime(2026, 9, 14, 13, 31, tzinfo=UTC)


def iid(**over: Any):
    kw: dict[str, Any] = dict(strategy="orb", account="acct1", symbol="MES", session="2026-09-14",
              signal_ts=TS, side="buy", sequence=0)
    kw.update(over)
    return intent_id(**kw)


def entry(j: IntentJournal, iid_: str):
    e = j.seen(iid_)
    assert e is not None, iid_
    return e


def sent(ex: RoutedExecutor) -> list:
    assert isinstance(ex.adapter, SimulatedAdapter)
    return ex.adapter.sent


# ---------------------------------------------------------------------------------------
# identity
# ---------------------------------------------------------------------------------------

def test_same_decision_same_id_every_time():
    assert iid() == iid()
    assert len(iid()) == 20


@pytest.mark.parametrize("field,value", [
    ("strategy", "orb2"), ("account", "acct2"), ("symbol", "MNQ"), ("session", "2026-09-15"),
    ("signal_ts", TS + dt.timedelta(seconds=1)), ("side", "sell"), ("sequence", 1),
])
def test_every_input_changes_the_id(field, value):
    assert iid(**{field: value}) != iid()


def test_naive_timestamp_is_refused():
    with pytest.raises(ValueError, match="timezone-aware"):
        iid(signal_ts=dt.datetime(2026, 9, 14, 13, 31))


def test_same_instant_in_another_zone_is_the_same_id():
    ny = TS.astimezone(dt.timezone(dt.timedelta(hours=-4)))
    assert iid(signal_ts=ny) == iid()


@pytest.mark.parametrize("field", ["strategy", "account", "symbol", "session", "side"])
def test_empty_input_is_refused(field):
    with pytest.raises(ValueError, match=field):
        iid(**{field: " "})


# ---------------------------------------------------------------------------------------
# journal
# ---------------------------------------------------------------------------------------

def test_claim_then_duplicate_claim_is_refused(tmp_path):
    j = IntentJournal(tmp_path / "intents.jsonl")
    j.claim("abc", note="MES buy 1")
    with pytest.raises(Duplicate, match="already pending"):
        j.claim("abc")
    assert entry(j, "abc").state is IntentState.PENDING


def test_advance_walks_forward_and_terminal_is_terminal(tmp_path):
    j = IntentJournal(tmp_path / "i.jsonl")
    j.claim("abc")
    j.advance("abc", IntentState.SUBMITTED)
    j.advance("abc", IntentState.ACKED, broker_id="42")
    e = entry(j, "abc")
    assert e.state is IntentState.ACKED and e.broker_id == "42"
    with pytest.raises(Duplicate, match="terminal"):
        j.advance("abc", IntentState.FAILED)
    with pytest.raises(Duplicate):
        j.claim("abc")


def test_advance_of_unclaimed_intent_is_refused(tmp_path):
    j = IntentJournal(tmp_path / "i.jsonl")
    with pytest.raises(KeyError):
        j.advance("never", IntentState.SUBMITTED)


def test_recover_returns_only_the_unresolved(tmp_path):
    j = IntentJournal(tmp_path / "i.jsonl")
    j.claim("pending")
    j.claim("sent")
    j.advance("sent", IntentState.SUBMITTED)
    j.claim("done")
    j.advance("done", IntentState.ACKED)
    j.claim("bad")
    j.advance("bad", IntentState.FAILED)
    assert sorted(e.intent_id for e in j.recover()) == ["pending", "sent"]


def test_a_torn_row_does_not_hide_the_rest(tmp_path):
    p = tmp_path / "i.jsonl"
    j = IntentJournal(p)
    j.claim("good")
    with p.open("a", encoding="utf-8") as fh:
        fh.write('{"intent_id": "torn", "sta')
    j2 = IntentJournal(p)
    assert j2.seen("good") is not None
    j2.claim("after")
    assert {e.intent_id for e in j2.recover()} == {"good", "after"}


def test_concurrent_claims_of_one_id_admit_exactly_one(tmp_path):
    j = IntentJournal(tmp_path / "i.jsonl")
    won, lost = [], []
    gate = threading.Barrier(8)

    def go():
        gate.wait()
        try:
            j.claim("race")
            won.append(1)
        except Duplicate:
            lost.append(1)
    ts = [threading.Thread(target=go) for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len(won) == 1 and len(lost) == 7


# ---------------------------------------------------------------------------------------
# executor integration
# ---------------------------------------------------------------------------------------

def make(tmp_path, adapter=None):
    j = IntentJournal(tmp_path / "i.jsonl")
    ex = RoutedExecutor(RiskChain(), adapter or SimulatedAdapter(),
                        authority=Authority.backtest(), journal=j)
    return ex, j


def test_executor_with_journal_refuses_an_intent_without_id(tmp_path):
    ex, j = make(tmp_path)
    acks = ex.submit([OrderIntent("MES", Side.BUY, 1)])
    assert acks == []
    (_, d), = ex.refused
    assert d.binding == ("IDEMPOTENCY_NO_ID",)
    assert j.entries() == {}


def test_executor_sends_once_and_refuses_the_replay(tmp_path):
    ex, j = make(tmp_path)
    intent = OrderIntent("MES", Side.BUY, 1, intent_id=iid())
    assert len(ex.submit([intent])) == 1
    assert entry(j, iid()).state is IntentState.ACKED
    assert ex.submit([intent]) == []
    (_, d), = ex.refused
    assert d.binding == ("IDEMPOTENCY_DUPLICATE",)
    assert len(sent(ex)) == 1


def test_replay_after_restart_is_refused_by_a_fresh_executor(tmp_path):
    ex1, _ = make(tmp_path)
    intent = OrderIntent("MES", Side.BUY, 1, intent_id=iid())
    ex1.submit([intent])
    ex2, _ = make(tmp_path)
    assert ex2.submit([intent]) == []
    assert len(sent(ex2)) == 0


def test_risk_denial_is_journaled_as_failed_so_it_cannot_be_retried_silently(tmp_path):
    from quant_brain.core.risk import RiskDecision, RiskEngine

    class Deny(RiskEngine):
        def evaluate(self, intent):
            return RiskDecision.deny("no", "TEST")
    j = IntentJournal(tmp_path / "i.jsonl")
    ex = RoutedExecutor(Deny(), SimulatedAdapter(), authority=Authority.backtest(), journal=j)
    intent = OrderIntent("MES", Side.BUY, 1, intent_id=iid())
    ex.submit([intent])
    assert entry(j, iid()).state is IntentState.FAILED
    ex.submit([intent])
    assert ex.refused[-1][1].binding == ("IDEMPOTENCY_DUPLICATE",)


def test_adapter_exception_leaves_intent_submitted_for_recovery(tmp_path):
    class Boom(SimulatedAdapter):
        def submit(self, intent):
            raise ConnectionError("timeout after send")
    ex, j = make(tmp_path, Boom())
    intent = OrderIntent("MES", Side.BUY, 1, intent_id=iid())
    with pytest.raises(ConnectionError):
        ex.submit([intent])
    assert entry(j, iid()).state is IntentState.SUBMITTED
    assert [e.intent_id for e in j.recover()] == [iid()]
    # and the replay is refused: outcome unknown is not permission to resend
    ex2, _ = make(tmp_path)
    assert ex2.submit([intent]) == []


def test_venue_rejection_is_journaled_failed(tmp_path):
    class Reject(SimulatedAdapter):
        def submit(self, intent):
            from quant_brain.core.execution import Ack
            return Ack(intent, False, reason="margin")
    ex, j = make(tmp_path, Reject())
    intent = OrderIntent("MES", Side.BUY, 1, intent_id=iid())
    ex.submit([intent])
    e = entry(j, iid())
    assert e.state is IntentState.FAILED and e.note == "margin"


def test_flatten_bypasses_the_journal_entirely(tmp_path):
    ex, j = make(tmp_path)
    ex.flatten({"MES": 2})
    ex.flatten({"MES": 2})
    assert len(sent(ex)) == 2 and j.entries() == {}


def test_with_quantity_preserves_intent_id():
    i = OrderIntent("MES", Side.BUY, 3, intent_id="abc", order_type=OrderType.MARKET)
    assert i.with_quantity(1).intent_id == "abc"


def test_executor_without_journal_is_unchanged(tmp_path):
    ex = RoutedExecutor(RiskChain(), SimulatedAdapter(), authority=Authority.backtest())
    intent = OrderIntent("MES", Side.BUY, 1)
    assert len(ex.submit([intent])) == 1 and len(ex.submit([intent])) == 1
