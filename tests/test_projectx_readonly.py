"""The read-only ProjectX client: what it may reach, and what it refuses to guess.

Two properties are worth a test file of their own.

**The order endpoint is unreachable by construction, not by a flag.** `ReadOnlyTransport`
holds a closed allow-list and refuses before a socket opens. A flag says "not now"; a closed
list says there is no path from here to there, and it keeps saying it at 3am.

**The target account is never guessed.** A Combine, an Express Funded account and a practice
account can all be live on one login. Picking the wrong one does not surface as an error - it
surfaces as a passed Combine on the wrong account, or a real loss on a funded one.

Nothing here makes a network call. The transport is exercised through its own guard, which
runs before any I/O, and everything else uses a fake.
"""
from __future__ import annotations

import pytest

from quant_brain.brokers import projectx_readonly as px

# =====================================================================================
# THE ALLOW-LIST
# =====================================================================================

@pytest.mark.parametrize("path", [
    "/api/Order/place", "/api/Order/modify", "/api/Order/cancel",
    "/api/Position/closeContract", "/api/Position/partialCloseContract",
])
def test_every_writing_endpoint_is_refused(path):
    """Refused by the fragment check, which fires even if the allow-list were widened."""
    with pytest.raises(px.ReadOnlyViolation) as e:
        px.ReadOnlyTransport().post(path, json={})
    assert "read-only" in str(e.value)


def test_the_order_endpoint_is_not_in_the_allow_list_either():
    assert "/api/Order/place" not in px.READ_ONLY_PATHS
    assert not any("place" in p.lower() for p in px.READ_ONLY_PATHS)


def test_an_unknown_endpoint_is_refused_rather_than_attempted():
    with pytest.raises(px.ReadOnlyViolation) as e:
        px.ReadOnlyTransport().post("/api/Something/new", json={})
    assert "allow-list" in str(e.value)


def test_the_allow_list_is_closed_and_small():
    """A list that grows without anybody noticing is not a control. Eleven endpoints, all
    documented in docs/topstep/API.md, all reads."""
    assert len(px.READ_ONLY_PATHS) == 11
    for p in px.READ_ONLY_PATHS:
        assert p.startswith("/api/")
        assert not any(f in p.lower() for f in px.FORBIDDEN_FRAGMENTS)


def test_a_full_url_is_reduced_to_its_path_before_the_check():
    """The adapter contract passes a full URL. The guard must not be bypassable by prefixing
    the base URL onto a forbidden path."""
    t = px.ReadOnlyTransport()
    with pytest.raises(px.ReadOnlyViolation):
        t.post(t.base_url + "/api/Order/place", json={})


def test_nothing_was_sent_when_a_path_is_refused():
    """The refusal happens before the socket, so the call is not even recorded."""
    t = px.ReadOnlyTransport()
    with pytest.raises(px.ReadOnlyViolation):
        t.post("/api/Order/place", json={})
    assert t.calls == []


# =====================================================================================
# ACCOUNT BINDING
# =====================================================================================

ACCOUNTS = [
    {"id": 1, "name": "PRACTICEJUL0824", "balance": 50_000, "canTrade": True},
    {"id": 2, "name": "50KTC-SKU-V2-DLL-679574-19137660", "balance": 50_000,
     "canTrade": True},
    {"id": 3, "name": "XFA-000111", "balance": 0, "canTrade": True},
]


def test_the_configured_account_binds_to_exactly_one():
    a = px.bind_account(ACCOUNTS, "50KTC-SKU-V2-DLL-679574-19137660")
    assert a["id"] == 2


def test_an_unset_target_refuses_rather_than_choosing_the_first():
    """The failure this exists to prevent. The first account here is a PRACTICE account, so
    a silent fallback would look harmless right up until the day the order is real."""
    with pytest.raises(px.AccountBindingError) as e:
        px.bind_account(ACCOUNTS, "")
    assert "never inferred" in str(e.value)


def test_a_target_that_matches_nothing_refuses_and_lists_what_it_saw():
    with pytest.raises(px.AccountBindingError) as e:
        px.bind_account(ACCOUNTS, "50KTC-WRONG")
    msg = str(e.value)
    assert "not among" in msg
    assert "PRACTICEJUL0824" in msg, "the operator needs to see the real options"


def test_an_ambiguous_target_refuses_rather_than_taking_the_first_match():
    dupes = ACCOUNTS + [{"id": 9, "name": "50KTC-SKU-V2-DLL-679574-19137660", "balance": 1}]
    with pytest.raises(px.AccountBindingError) as e:
        px.bind_account(dupes, "50KTC-SKU-V2-DLL-679574-19137660")
    assert "matched 2" in str(e.value)


def test_a_numeric_target_binds_by_id():
    """The configured value today is a name; the API's own key is an integer. Both work so a
    later reconfiguration to the numeric id does not silently stop matching."""
    assert px.bind_account(ACCOUNTS, "3")["name"] == "XFA-000111"


@pytest.mark.parametrize("near", [
    "50ktc-sku-v2-dll-679574-19137660",       # case
    "50KTC-SKU-V2-DLL-679574-1913766",        # prefix
    " 50KTC-SKU-V2-DLL-679574-19137660",      # leading space
])
def test_matching_is_exact_because_every_relaxation_can_match_two(near):
    with pytest.raises(px.AccountBindingError):
        px.bind_account(ACCOUNTS, near)


def test_an_empty_account_list_refuses(monkeypatch):
    with pytest.raises(px.AccountBindingError):
        px.bind_account([], "50KTC-SKU-V2-DLL-679574-19137660")


# =====================================================================================
# SECRETS
# =====================================================================================

SENTINEL = "SENTINEL-not-a-real-credential-9f3a1c"


def test_the_client_has_no_printable_token():
    c = px.ReadOnlyClient(transport=px.ReadOnlyTransport(), _token=SENTINEL,
                          username="someone")
    assert SENTINEL not in repr(c)
    assert SENTINEL not in str(c)
    assert "redacted" in repr(c)
    assert c.authenticated is True


def test_a_missing_credential_names_the_variable_and_not_the_value(monkeypatch):
    from quant_brain.core import config as cfg
    monkeypatch.setattr(cfg, "SECRET_FILE", cfg.REPO / "live" / "does-not-exist.env")
    monkeypatch.delenv(cfg.ENV_PROJECTX_KEY, raising=False)
    monkeypatch.setenv(cfg.ENV_PROJECTX_USER, SENTINEL)
    with pytest.raises(px.TransportError) as e:
        px.from_environment()
    assert cfg.ENV_PROJECTX_KEY in str(e.value)
    assert SENTINEL not in str(e.value), "the credential that WAS set leaked"


def test_authentication_makes_exactly_one_attempt():
    """A wrong key retried in a loop is how an account gets locked, and a lockout during a
    Combine is worse than a failed script. There is no retry, and this asserts it."""
    calls = []

    class Rejecting(px.ReadOnlyTransport):
        def post(self, path, *, json=None, token=None):
            calls.append(path)
            return {"success": False, "errorCode": 3, "errorMessage": None}

    c = px.ReadOnlyClient(transport=Rejecting())
    with pytest.raises(px.TransportError) as e:
        c.authenticate("someone", SENTINEL)
    assert len(calls) == 1, f"authentication was attempted {len(calls)} times"
    assert "errorCode=3" in str(e.value)
    assert SENTINEL not in str(e.value)


def test_a_successful_login_stores_no_credential_only_a_token():
    class OK(px.ReadOnlyTransport):
        def post(self, path, *, json=None, token=None):
            return {"success": True, "errorCode": 0, "token": "tok-abc"}

    c = px.ReadOnlyClient(transport=OK())
    c.authenticate("someone", SENTINEL)
    blob = repr(c) + str(c.__dict__)
    assert SENTINEL not in blob, "the api key was retained on the client"
    assert c.authenticated


# =====================================================================================
# BARS
# =====================================================================================

def test_partial_bars_are_off_by_default():
    """An unfinished bar in a research dataset is a look-ahead with a timestamp on it."""
    sent = {}

    class Cap(px.ReadOnlyTransport):
        def post(self, path, *, json=None, token=None):
            sent.update(json or {})
            return {"success": True, "bars": []}

    import datetime as dt
    c = px.ReadOnlyClient(transport=Cap(), _token="t")
    c.bars("CON.F.US.MNQ.Z25", unit=2, unit_number=1,
           start=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
           end=dt.datetime(2026, 1, 2, tzinfo=dt.UTC))
    assert sent["includePartialBar"] is False
    assert sent["live"] is False
    assert sent["startTime"].endswith("Z"), "timestamps must be explicit UTC"
