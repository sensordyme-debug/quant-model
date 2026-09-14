"""A ProjectX / TopstepX client that is structurally incapable of placing an order.

WHY A SEPARATE MODULE
---------------------
`projectx.py` is the execution adapter. It deliberately has no HTTP dependency and no live
submit branch, and that should stay true. This module is the read-only half: it makes real
network calls, and it is built so that the set of things it can reach is a closed list.

THE CONTROL THAT MATTERS
------------------------
`ReadOnlyTransport` holds an explicit allow-list of endpoint paths. A request to anything
outside it raises before a socket is opened. `/api/Order/place` is not on the list, and there
is additionally a specific refusal that names it, so a future edit that widens the list still
has to delete a line that says out loud what it is deleting.

This is a different kind of control from a flag. A flag says "not now". A closed allow-list
says "there is no code path from here to there", and it keeps saying it when somebody is
tired at 3am and reaching for the fastest way to test something.

WHAT IT DOES NOT DO
-------------------
It does not authorise anything. Authentication is not authorization: a token from this module
grants reads and nothing else, which is the same position `ConnectionState.AUTHENTICATED`
takes in the adapter. Sizing, risk and the Topstep rulebook are all somewhere else.

It also does not retry a failed authentication. A wrong credential retried in a loop is how
an account gets locked, and a lockout during a Combine is worse than a failed script.

SECRETS
-------
The API key is materialised in exactly one place, the login body, and that body is never put
in an exception, a log line or a return value. `urllib` errors are caught and re-raised as a
type that carries only the status code and the endpoint path.
"""
from __future__ import annotations

import datetime as dt
import json as _json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

DEFAULT_BASE = "https://api.topstepx.com"

#: Every endpoint this module may reach. Read-only by inspection, and closed by construction.
#: Paths come from `docs/topstep/API.md`. Adding one is a deliberate act; adding a writing one
#: should not happen at all.
READ_ONLY_PATHS: frozenset[str] = frozenset({
    "/api/Auth/loginKey",
    "/api/Auth/validate",
    "/api/Account/search",
    "/api/Contract/search",
    "/api/Contract/available",
    "/api/Contract/searchById",
    "/api/History/retrieveBars",
    "/api/Position/searchOpen",
    "/api/Order/searchOpen",
    "/api/Order/search",
    "/api/Trade/search",
})

#: Named separately so that the refusal message can say what was attempted. Anything here is
#: refused even if somebody adds it to the allow-list above by mistake.
FORBIDDEN_FRAGMENTS = ("order/place", "order/modify", "order/cancel", "position/close",
                       "position/partialclose")


class ReadOnlyViolation(RuntimeError):
    """An attempt to reach an endpoint this module is not permitted to reach."""


class TransportError(RuntimeError):
    """A network or protocol failure. Carries a status and a path, never a request body."""


@dataclass
class ReadOnlyTransport:
    """POST JSON to an allow-listed ProjectX endpoint. Nothing else.

    `timeout` is per request. `min_interval` is a floor between requests, because the
    documented rate limits are per-endpoint and a research script that paginates history will
    otherwise walk straight into them; a small sleep is cheaper than a ban.
    """

    base_url: str = DEFAULT_BASE
    timeout: float = 30.0
    min_interval: float = 0.25
    _last_call: float = field(default=0.0, repr=False)
    #: Every path reached, for the report. Paths only - no bodies, no tokens.
    calls: list[str] = field(default_factory=list)

    def _check(self, path: str) -> None:
        low = path.lower()
        for frag in FORBIDDEN_FRAGMENTS:
            if frag in low:
                raise ReadOnlyViolation(
                    f"refusing to reach {path}: this transport is read-only and {frag!r} "
                    f"writes to the account. There is no flag that changes this; the check "
                    f"is here so that reaching a writing endpoint requires deleting a line "
                    f"of code that says what it is for.")
        if path not in READ_ONLY_PATHS:
            raise ReadOnlyViolation(
                f"refusing to reach {path}: not in the read-only allow-list. Add it to "
                f"READ_ONLY_PATHS only after confirming from docs/topstep/API.md that it "
                f"does not modify orders, positions or the account.")

    def post(self, url_or_path: str, *, json: dict | None = None,
             token: str | None = None) -> dict[str, Any]:
        """POST and return the decoded body.

        Accepts a full URL so the object satisfies the `transport.post(url, json=...)` shape
        `ProjectXAdapter.authenticate` expects, and a bare path for this module's own calls.
        """
        path = url_or_path[len(self.base_url):] if url_or_path.startswith(self.base_url) \
            else url_or_path
        self._check(path)

        wait = self.min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

        return self._send(path, json or {}, token)

    def _send(self, path: str, body: dict, token: str | None) -> dict[str, Any]:
        data = _json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(self.base_url + path, data=data, headers=headers,
                                     method="POST")
        self.calls.append(path)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            # The body of the FAILED request is not included. On /api/Auth/loginKey that body
            # is the API key, and an HTTPError repr is exactly the thing that ends up in a log.
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:300]
            except Exception:                                          # noqa: BLE001
                pass
            raise TransportError(f"{path} returned HTTP {exc.code}: {detail}") from None
        except urllib.error.URLError as exc:
            raise TransportError(f"{path} could not be reached: {exc.reason}") from None
        try:
            return _json.loads(raw)
        except Exception:                                              # noqa: BLE001
            raise TransportError(f"{path} returned a body that is not JSON "
                                 f"({len(raw)} bytes)") from None


@dataclass
class ReadOnlyClient:
    """Authenticate once, then read. Every method is a documented read endpoint.

    Holds the session token in a private field with no printable form, the same way
    `projectx.Session` does, so it cannot reach a log through a repr.
    """

    transport: ReadOnlyTransport
    _token: str = field(default="", repr=False)
    issued: dt.datetime | None = None
    username: str = ""

    # -- session -------------------------------------------------------------------------

    def authenticate(self, username: str, api_key: str) -> None:
        """One attempt. No retry, deliberately: a wrong key retried locks the account."""
        body = self.transport.post("/api/Auth/loginKey",
                                   json={"userName": username, "apiKey": api_key})
        if not body.get("success"):
            raise TransportError(
                f"authentication rejected, errorCode={body.get('errorCode')}, "
                f"errorMessage={body.get('errorMessage')!r}")
        token = body.get("token") or ""
        if not token:
            raise TransportError("authentication reported success with no token")
        self._token, self.issued, self.username = token, dt.datetime.now(dt.UTC), username

    def validate(self) -> dict:
        return self.transport.post("/api/Auth/validate", token=self._token)

    @property
    def authenticated(self) -> bool:
        return bool(self._token)

    def __repr__(self) -> str:
        return (f"ReadOnlyClient(user={self.username!r}, token=<redacted>, "
                f"authenticated={self.authenticated})")

    __str__ = __repr__

    # -- discovery -----------------------------------------------------------------------

    def accounts(self, *, only_active: bool = True) -> list[dict]:
        b = self.transport.post("/api/Account/search",
                                json={"onlyActiveAccounts": only_active}, token=self._token)
        return list(b.get("accounts") or [])

    def contracts(self, search_text: str, *, live: bool = False) -> list[dict]:
        b = self.transport.post("/api/Contract/search",
                                json={"searchText": search_text, "live": live},
                                token=self._token)
        return list(b.get("contracts") or [])

    def available_contracts(self, *, live: bool = False) -> list[dict]:
        b = self.transport.post("/api/Contract/available", json={"live": live},
                                token=self._token)
        return list(b.get("contracts") or [])

    def contract_by_id(self, contract_id: str) -> dict:
        b = self.transport.post("/api/Contract/searchById",
                                json={"contractId": contract_id}, token=self._token)
        return dict(b.get("contract") or {})

    # -- market data ---------------------------------------------------------------------

    def bars(self, contract_id: str, *, unit: int, unit_number: int,
             start: dt.datetime, end: dt.datetime, limit: int = 20000,
             live: bool = False, partial: bool = False) -> list[dict]:
        """One page of bars.

        `unit` follows the API's enumeration: 1 second, 2 minute, 3 hour, 4 day, 5 week,
        6 month. `partial` defaults False so an unfinished bar is never returned - a partial
        bar in a research dataset is a look-ahead with a timestamp.
        """
        b = self.transport.post("/api/History/retrieveBars", token=self._token, json={
            "contractId": contract_id,
            "live": live,
            "startTime": _iso(start),
            "endTime": _iso(end),
            "unit": unit,
            "unitNumber": unit_number,
            "limit": limit,
            "includePartialBar": partial,
        })
        if not b.get("success", True):
            raise TransportError(f"retrieveBars failed, errorCode={b.get('errorCode')}, "
                                 f"errorMessage={b.get('errorMessage')!r}")
        return list(b.get("bars") or [])

    # -- account state ---------------------------------------------------------------------

    def open_positions(self, account_id: int) -> list[dict]:
        b = self.transport.post("/api/Position/searchOpen",
                                json={"accountId": account_id}, token=self._token)
        return list(b.get("positions") or [])

    def open_orders(self, account_id: int) -> list[dict]:
        b = self.transport.post("/api/Order/searchOpen",
                                json={"accountId": account_id}, token=self._token)
        return list(b.get("orders") or [])

    def orders(self, account_id: int, *, start: dt.datetime,
               end: dt.datetime | None = None) -> list[dict]:
        payload = {"accountId": account_id, "startTimestamp": _iso(start)}
        if end is not None:
            payload["endTimestamp"] = _iso(end)
        b = self.transport.post("/api/Order/search", json=payload, token=self._token)
        return list(b.get("orders") or [])

    def trades(self, account_id: int, *, start: dt.datetime,
               end: dt.datetime | None = None) -> list[dict]:
        payload = {"accountId": account_id, "startTimestamp": _iso(start)}
        if end is not None:
            payload["endTimestamp"] = _iso(end)
        b = self.transport.post("/api/Trade/search", json=payload, token=self._token)
        return list(b.get("trades") or [])


class AccountBindingError(RuntimeError):
    """The target account could not be identified UNAMBIGUOUSLY. Never a fallback."""


def bind_account(accounts: list[dict], target: str) -> dict:
    """Find the one account matching `target`. Refuse on zero, refuse on more than one.

    THE RULE THIS ENFORCES
    Never silently choose the first account the API returns. A Combine, an Express Funded
    account and a practice account can all be live on one login, and picking the wrong one is
    not an error that shows up as an error - it shows up as a passed Combine on the wrong
    account, or a real loss on a funded one.

    `target` is matched against the account's `name` and, if it is all digits, its `id`. The
    configured value in this repository is a NAME - measured 2026-09-14, the configured
    `TOPSTEP_TARGET_ACCOUNT_ID` is `50KTC-...`-shaped, while the API's `id` field is an
    integer. Both are accepted so a future reconfiguration to the numeric id keeps working.

    Matching is exact. Not a prefix, not case-insensitive, not "contains": every relaxation
    of this is a way to match two accounts and then pick one.
    """
    if not target:
        raise AccountBindingError(
            "no target account configured. Set TOPSTEP_TARGET_ACCOUNT_ID to the account you "
            "intend to trade. It is never inferred - there is no 'the' account until a "
            "person names one.")
    hits = [a for a in accounts
            if str(a.get("name", "")) == target
            or (target.isdigit() and str(a.get("id", "")) == target)]
    if not hits:
        names = sorted(str(a.get("name", "?")) for a in accounts)
        raise AccountBindingError(
            f"target account {target!r} is not among the {len(accounts)} account(s) this "
            f"login can see: {names}. Nothing is selected.")
    if len(hits) > 1:
        raise AccountBindingError(
            f"target account {target!r} matched {len(hits)} accounts. Refusing to guess "
            f"which; make the identifier unique.")
    return hits[0]


def _iso(t: dt.datetime) -> str:
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.UTC)
    return t.astimezone(dt.UTC).isoformat().replace("+00:00", "Z")


def from_environment(base_url: str | None = None, **kw) -> ReadOnlyClient:
    """Build an authenticated client from the environment. Credentials are read here and
    nowhere else, and are not stored on the returned object."""
    import os

    from quant_brain.core import config as cfg

    cfg.load_secret_file()
    user = os.environ.get(cfg.ENV_PROJECTX_USER, "").strip()
    key = os.environ.get(cfg.ENV_PROJECTX_KEY, "").strip()
    if not user or not key:
        missing = [n for n, v in ((cfg.ENV_PROJECTX_USER, user),
                                  (cfg.ENV_PROJECTX_KEY, key)) if not v]
        raise TransportError(f"ProjectX credentials are not configured: {', '.join(missing)}")
    base = base_url or os.environ.get(cfg.ENV_PROJECTX_BASE) or DEFAULT_BASE
    client = ReadOnlyClient(transport=ReadOnlyTransport(base_url=base.rstrip("/"), **kw))
    client.authenticate(user, key)
    return client


__all__ = ["AccountBindingError", "DEFAULT_BASE", "READ_ONLY_PATHS",
           "ReadOnlyClient", "ReadOnlyTransport", "ReadOnlyViolation",
           "TransportError", "bind_account", "from_environment"]
