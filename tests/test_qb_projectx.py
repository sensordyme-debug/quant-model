"""Tests for the ProjectX / TopstepX adapter.

Three properties, in descending order of how much damage their absence would do:

1. It cannot place a live order. §44 of the brief is absolute about this, and the strongest
   evidence is a test that tries every route and fails on each.
2. A credential never appears in any printable form - repr, str, f-string, exception,
   event payload. §20 lists the places; the test enumerates them.
3. AUTHENTICATED does not imply permission to trade. That conflation is how prop-firm
   integrations fire unintended orders, so it gets its own section.
"""
from __future__ import annotations

import datetime as dt

import pytest

from quant_brain.brokers.projectx import (
    AUTH_PATH,
    ENV_KEY,
    ENV_USER,
    REFRESH_MARGIN,
    TOKEN_LIFETIME,
    ConnectionState,
    Credentials,
    Halted,
    ProjectXAdapter,
    Session,
)
from quant_brain.core.execution import OrderIntent, Side
from quant_brain.core.mode import Authority, Mode, NotPermitted

SECRET = "sk-live-DO-NOT-LEAK-0123456789"


class FakeTransport:
    """Records calls. Never touches a network - there is no network code in these tests."""

    def __init__(self, response=None, raises=None):
        self.calls: list[tuple[str, dict]] = []
        self.response = response if response is not None else {
            "token": "TOKEN-VALUE", "success": True, "errorCode": 0, "errorMessage": None}
        self.raises = raises

    def post(self, url, json=None, **kw):
        self.calls.append((url, json or {}))
        if self.raises:
            raise self.raises
        return self.response


@pytest.fixture
def creds():
    return Credentials(username="someone", _api_key=SECRET)


def _authed(dry_run=True, **kw):
    t = FakeTransport()
    a = ProjectXAdapter(transport=t, dry_run=dry_run, account_id="ACC1", **kw)
    a.authenticate(Credentials(username="u", _api_key=SECRET))
    return a, t


# ======================================================================================
# IT CANNOT PLACE A LIVE ORDER
# ======================================================================================

def test_the_default_construction_has_no_transport_at_all():
    """Not "does not send" - cannot. There is nothing to call."""
    a = ProjectXAdapter()
    assert a.transport is None
    assert a.dry_run is True
    with pytest.raises(NotPermitted) as e:
        a.authenticate(Credentials(username="u", _api_key=SECRET))
    assert "no transport" in str(e.value)


def test_a_dry_run_records_the_order_and_never_reaches_the_transport():
    a, t = _authed(dry_run=True)
    before = len(t.calls)
    ack = a.submit(OrderIntent(symbol="CON.F.US.MNQ.Z25", side=Side.BUY, quantity=2))
    assert not ack.accepted
    assert "dry run" in ack.reason
    assert len(t.calls) == before, "the transport was called during a dry run"
    assert a.would_send[-1]["size"] == 2


def test_live_submission_is_not_implemented_rather_than_gated(monkeypatch):
    """An implementation present but gated is one edit from an accident.

    STRENGTHENED when the configuration gate landed. `submit` now also consults
    `config.transmission_allowed`, so a forced-open connection alone routes into the dry-run
    branch and this test would have passed for the wrong reason - proving the config gate
    works rather than proving there is no live code. So the gate is forced open too, by
    replacing it wholesale with a function that says yes.

    That makes this the most adversarial test in the file: connection state forced to
    EXECUTION_READY, `dry_run` forced False, and the entire configuration layer replaced by a
    stub that permits everything. There is still nothing to send, because the branch that
    would send does not exist.

    The gate is stubbed rather than driven with environment variables on purpose - no string
    resembling a credential is set anywhere in this suite.
    """
    from quant_brain.core import config as qb_config
    monkeypatch.setattr(qb_config, "transmission_allowed", lambda *a, **k: (True, []))

    a, _ = _authed(dry_run=False)
    a.arm(Authority.practice("topstep", "ACC1"), confirmed_practice=True)
    # Forced past every gate by hand - the hardest possible case for the claim below.
    a.state = ConnectionState.EXECUTION_READY
    a.dry_run = False
    with pytest.raises(NotPermitted) as e:
        a.submit(OrderIntent(symbol="X", side=Side.BUY, quantity=1))
    assert "not implemented" in str(e.value)


def test_the_configuration_gate_diverts_a_live_looking_submit_into_a_dry_run():
    """The layer below the missing implementation, on its own.

    Connection forced to EXECUTION_READY and `dry_run` False, but configuration untouched and
    therefore refusing. The order is recorded rather than sent, and the reason it was blocked
    travels with the event so an operator can see WHICH condition stopped it.
    """
    a, t = _authed(dry_run=False)
    a.arm(Authority.practice("topstep", "ACC1"), confirmed_practice=True)
    a.state = ConnectionState.EXECUTION_READY
    a.dry_run = False
    before = len(t.calls)
    ack = a.submit(OrderIntent(symbol="CON.F.US.MNQ.Z25", side=Side.BUY, quantity=1))
    assert not ack.accepted
    assert len(t.calls) == before, "the transport was reached despite the configuration gate"
    assert a.would_send, "the translated body must still be recorded"


def test_reconciliation_refuses_rather_than_returning_an_empty_position_set():
    """An empty stub would look like agreement with ANY local state."""
    a, _ = _authed(dry_run=True)
    a.arm(Authority.practice("topstep", "ACC1"))
    with pytest.raises(NotPermitted) as e:
        a.reconcile({"MNQ": 3.0})
    assert "most dangerous possible stub" in str(e.value)


def test_the_adapter_requires_the_top_rung_unless_it_is_a_dry_run():
    assert ProjectXAdapter(dry_run=False).requires is Mode.EXECUTION_READY
    assert ProjectXAdapter(dry_run=True).requires is Mode.PRACTICE


def test_a_research_authority_cannot_route_to_it():
    from quant_brain.core.execution import RoutedExecutor
    from quant_brain.core.risk import RiskChain
    with pytest.raises(NotPermitted):
        RoutedExecutor(RiskChain(), ProjectXAdapter.for_dry_run(),
                       authority=Authority.backtest())


# ======================================================================================
# AUTHENTICATED IS NOT PERMISSION
# ======================================================================================

def test_authenticating_does_not_make_the_connection_able_to_send():
    a, _ = _authed()
    assert a.state is ConnectionState.AUTHENTICATED
    assert a.state.can_read
    assert not a.state.can_send, "AUTHENTICATED must not imply the ability to trade"


def test_only_execution_ready_can_send():
    sendable = [s for s in ConnectionState if s.can_send]
    assert sendable == [ConnectionState.EXECUTION_READY]


def test_arming_a_non_dry_run_requires_evidence_about_the_account():
    a, _ = _authed(dry_run=False)
    with pytest.raises(NotPermitted) as e:
        a.arm(Authority.practice("topstep", "ACC1"))
    assert "confirmed_practice" in str(e.value)
    assert "belief" in str(e.value)


def test_a_practice_authority_cannot_arm_a_funded_account():
    a, _ = _authed(dry_run=False)
    with pytest.raises(NotPermitted):
        a.arm(Authority.practice("topstep", "ACC1"), confirmed_practice=False)


def test_a_practice_account_arms_to_practice_ready_not_execution_ready():
    a, _ = _authed(dry_run=False)
    state = a.arm(Authority.practice("topstep", "ACC1"), confirmed_practice=True)
    assert state is ConnectionState.PRACTICE_READY
    assert not state.can_send


def test_arming_before_authenticating_is_refused():
    a = ProjectXAdapter(transport=FakeTransport())
    with pytest.raises(Halted):
        a.arm(Authority.practice("topstep", "ACC1"))


# ======================================================================================
# SECRETS DO NOT APPEAR ANYWHERE
# ======================================================================================

def test_the_secret_is_absent_from_every_printable_form(creds):
    for rendered in (repr(creds), str(creds), f"{creds}", f"{creds!r}", format(creds)):
        assert SECRET not in rendered
        assert "<redacted>" in rendered


def test_the_secret_is_absent_from_a_session(creds):
    s = Session(_token=SECRET, issued=dt.datetime.now(dt.UTC))
    for rendered in (repr(s), str(s), f"{s}"):
        assert SECRET not in rendered


def test_the_secret_is_absent_from_the_adapters_description():
    a, _ = _authed()
    assert SECRET not in a.describe()
    assert "TOKEN-VALUE" not in a.describe()


def test_a_transport_failure_does_not_re_raise_the_request_body():
    """A transport error can carry the request, and the request carries the API key."""
    t = FakeTransport(raises=RuntimeError(f"connection refused sending {SECRET}"))
    a = ProjectXAdapter(transport=t)
    with pytest.raises(Halted) as e:
        a.authenticate(Credentials(username="u", _api_key=SECRET))
    text = str(e.value) + repr(e.value)
    assert SECRET not in text
    assert e.value.__cause__ is None, "the cause chain would carry the original message"


def test_events_never_carry_the_secret():
    seen: list[tuple[str, dict]] = []
    t = FakeTransport()
    a = ProjectXAdapter(transport=t, on_event=lambda ev, **kw: seen.append((ev, kw)))
    a.authenticate(Credentials(username="u", _api_key=SECRET))
    blob = repr(seen)
    assert SECRET not in blob
    assert "TOKEN-VALUE" not in blob


def test_credentials_come_from_the_environment_and_say_so_when_absent(monkeypatch):
    monkeypatch.delenv(ENV_USER, raising=False)
    monkeypatch.delenv(ENV_KEY, raising=False)
    with pytest.raises(NotPermitted) as e:
        Credentials.from_environment()
    assert ENV_USER in str(e.value) and ENV_KEY in str(e.value)


def test_the_environment_path_works_when_set(monkeypatch):
    monkeypatch.setenv(ENV_USER, "someone")
    monkeypatch.setenv(ENV_KEY, SECRET)
    c = Credentials.from_environment()
    assert c.username == "someone"
    assert c.payload()["apiKey"] == SECRET       # materialised only here
    assert SECRET not in repr(c)


def test_no_credential_appears_in_the_source_of_this_package():
    """A standing check that nothing real was ever pasted in while debugging."""
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "quant_brain"
    # Shapes that look like real secrets rather than placeholders.
    patterns = [re.compile(p) for p in (
        r"sk-[A-Za-z0-9]{16,}", r"eyJ[A-Za-z0-9_-]{20,}", r"Bearer\s+[A-Za-z0-9._-]{20,}")]
    offenders = []
    for f in root.rglob("*.py"):
        text = f.read_text(encoding="utf-8", errors="replace")
        for pat in patterns:
            for m in pat.finditer(text):
                offenders.append(f"{f.relative_to(root)}: {m.group()[:12]}...")
    assert offenders == [], f"possible secret in source: {offenders}"


# ======================================================================================
# THE TOKEN
# ======================================================================================

def test_the_documented_lifetime_is_twenty_four_hours():
    assert TOKEN_LIFETIME == dt.timedelta(hours=24)


def test_a_fresh_session_is_valid_and_does_not_need_refresh():
    s = Session(_token="t", issued=dt.datetime.now(dt.UTC))
    assert s.valid and not s.needs_refresh


def test_a_session_inside_the_margin_wants_refreshing_before_it_expires():
    """Refresh before a 401, not after one."""
    issued = dt.datetime.now(dt.UTC) - (TOKEN_LIFETIME - REFRESH_MARGIN + dt.timedelta(minutes=1))
    s = Session(_token="t", issued=issued)
    assert s.valid, "still valid..."
    assert s.needs_refresh, "...but should already be refreshing"


def test_an_expired_session_is_invalid():
    s = Session(_token="t", issued=dt.datetime.now(dt.UTC) - TOKEN_LIFETIME
                - dt.timedelta(minutes=1))
    assert not s.valid


def test_an_empty_session_cannot_produce_a_header():
    with pytest.raises(Halted):
        Session().header()


def test_ensure_session_reauthenticates_inside_the_margin():
    a, t = _authed()
    a.session = Session(_token="t", issued=dt.datetime.now(dt.UTC) - TOKEN_LIFETIME
                        + dt.timedelta(minutes=5))
    calls = len(t.calls)
    a.ensure_session()
    assert len(t.calls) == calls + 1


def test_the_login_path_is_the_verified_one():
    _, t = _authed()
    url, body = t.calls[0]
    assert url.endswith(AUTH_PATH)
    assert set(body) == {"userName", "apiKey"}


# ======================================================================================
# FAILURE IS TERMINAL
# ======================================================================================

def test_a_rejected_login_halts():
    t = FakeTransport(response={"token": None, "success": False, "errorCode": 3,
                                "errorMessage": "bad key"})
    a = ProjectXAdapter(transport=t)
    with pytest.raises(Halted):
        a.authenticate(Credentials(username="u", _api_key=SECRET))
    assert a.state is ConnectionState.HALTED


def test_success_with_no_token_halts():
    """A venue that says yes and sends nothing is a venue we do not understand."""
    t = FakeTransport(response={"token": "", "success": True, "errorCode": 0})
    a = ProjectXAdapter(transport=t)
    with pytest.raises(Halted):
        a.authenticate(Credentials(username="u", _api_key=SECRET))
    assert a.state is ConnectionState.HALTED


def test_a_halt_is_terminal_and_blocks_everything_after_it():
    a, _ = _authed()
    a.halt("something is wrong")
    for call in (lambda: a.ensure_session(),
                 lambda: a.arm(Authority.practice("topstep", "A")),
                 lambda: a.submit(OrderIntent(symbol="X", side=Side.BUY, quantity=1)),
                 lambda: a.reconcile({})):
        with pytest.raises(Halted):
            call()


def test_nothing_in_the_module_clears_a_halt():
    a, _ = _authed()
    a.halt("x")
    assert a.state is ConnectionState.HALTED
    with pytest.raises(Halted):
        a.authenticate(Credentials(username="u", _api_key=SECRET))
    assert a.state is ConnectionState.HALTED


# ======================================================================================
# TRANSLATION
# ======================================================================================

def test_a_buy_and_a_sell_translate_to_the_documented_side_encoding():
    a = ProjectXAdapter.for_dry_run(account_id="A")
    buy = a._translate(OrderIntent(symbol="C", side=Side.BUY, quantity=3))
    sell = a._translate(OrderIntent(symbol="C", side=Side.SELL, quantity=3))
    assert buy["side"] == 0 and sell["side"] == 1
    assert buy["size"] == 3


def test_quantity_reaches_the_venue_unsigned():
    a = ProjectXAdapter.for_dry_run(account_id="A")
    body = a._translate(OrderIntent(symbol="C", side=Side.SELL, quantity=5))
    assert body["size"] == 5


def test_a_flatten_translates_to_a_market_order():
    from quant_brain.core.execution import OrderType
    a = ProjectXAdapter.for_dry_run(account_id="A")
    body = a._translate(OrderIntent(symbol="C", side=Side.SELL, quantity=1,
                                    order_type=OrderType.FLATTEN))
    assert body["type"] == 2, "the venue has no flatten concept; it is a market order"


def test_a_limit_carries_its_price():
    from quant_brain.core.execution import OrderType
    a = ProjectXAdapter.for_dry_run(account_id="A")
    body = a._translate(OrderIntent(symbol="C", side=Side.BUY, quantity=1,
                                    order_type=OrderType.LIMIT, limit_price=21000.25))
    assert body["type"] == 1 and body["limitPrice"] == 21000.25


def test_working_is_empty_in_a_dry_run_rather_than_guessed():
    a = ProjectXAdapter.for_dry_run(account_id="A")
    assert a.working() == {}
