"""ProjectX / TopstepX adapter: the connection state machine, and why it cannot trade.

ProjectX is the gateway Topstep exposes as TopstepX. This module implements the connection
lifecycle, credential handling and order translation for it, and is deliberately incapable of
sending a live order in its default configuration.

WHAT IS VERIFIED, AND WHAT IS NOT
-----------------------------------
Verified against https://gateway.docs.projectx.com/docs/getting-started/authenticate/
authenticate-api-key/, retrieved 2026-09-13:

    POST https://api.topstepx.com/api/Auth/loginKey
    body    {"userName": ..., "apiKey": ...}
    returns {"token": ..., "success": bool, "errorCode": int, "errorMessage": str | null}
    "valid for 24 hours from the time it is issued. After that, requests fail with HTTP 401"
    a Validate Session endpoint exists to refresh before expiry

Everything else - the order, position, contract and history endpoints, the SignalR hub event
names, the rate limits - is recorded in `docs/topstep/API.md` and anything the documentation
does not settle is listed in `docs/topstep/API_UNKNOWNS.md` as a question rather than guessed
at here. §45 of the brief: "Do not guess endpoint behavior. If documentation is ambiguous:
mark it UNKNOWN." An endpoint invented in code is indistinguishable from a verified one three
months later, which is why they live in a table with sources instead.

THE SEPARATION THAT MATTERS
-----------------------------
`AUTHENTICATED` does not mean "may trade". It means a token exists. The brief states this
directly and it is the failure this class is shaped around: every prop-firm integration that
has ever fired an unintended order did so because logging in and being permitted to trade
were the same state.

So there are two axes, and they are independent:

    ConnectionState   what the SOCKET can do    DISCONNECTED .. AUTHENTICATED .. HALTED
    Authority         what the PROCESS may do   RESEARCH .. PRACTICE .. EXECUTION_READY

`submit()` consults both. A fully authenticated session under a RESEARCH authority sends
nothing, and a fully approved authority with an expired token sends nothing.

DRY RUN IS THE DEFAULT AND IT IS NOT A FLAG ON THE REQUEST
-------------------------------------------------------------
In dry run the transport is never called at all. There is no code path where a request object
is built and then not sent - the request is not built. A "send=False" parameter threaded
through a live code path is one boolean away from being wrong; not having the code path is
not.
"""
from __future__ import annotations

import datetime as dt
import enum
import os
from dataclasses import dataclass, field

from quant_brain.core.execution import Ack, ExecutionAdapter, OrderIntent, OrderType, Side
from quant_brain.core.mode import Authority, Mode, NotPermitted

#: Verified. The one endpoint this module hard-codes, because it is the one it has read.
AUTH_PATH = "/api/Auth/loginKey"

#: Documented token lifetime. Refreshed early by `REFRESH_MARGIN` so a long-running session
#: never discovers expiry by having an order rejected.
TOKEN_LIFETIME = dt.timedelta(hours=24)
REFRESH_MARGIN = dt.timedelta(minutes=30)

#: Credentials come from the environment, never from an argument, a file in the repo, or a
#: config object that might get logged. Named here so a reader can find them without grep.
ENV_USER = "PROJECTX_USERNAME"
ENV_KEY = "PROJECTX_API_KEY"
ENV_BASE = "PROJECTX_BASE_URL"

DEFAULT_BASE = "https://api.topstepx.com"


class ConnectionState(str, enum.Enum):
    """What the connection can do. Orthogonal to what the process is permitted to do."""

    DISCONNECTED = "disconnected"
    AUTHENTICATING = "authenticating"
    #: A token exists. This state grants NOTHING beyond the ability to make read calls.
    AUTHENTICATED = "authenticated"
    #: Authenticated against a practice account, which has been confirmed as such.
    PRACTICE_READY = "practice_ready"
    #: Orders are translated and recorded but the transport is never invoked.
    DRY_RUN = "dry_run"
    #: Orders would reach the venue. Requires an EXECUTION_READY authority as well.
    EXECUTION_READY = "execution_ready"
    #: Something is wrong. Terminal until a human intervenes; never auto-recovers.
    HALTED = "halted"

    @property
    def can_read(self) -> bool:
        return self in (ConnectionState.AUTHENTICATED, ConnectionState.PRACTICE_READY,
                        ConnectionState.DRY_RUN, ConnectionState.EXECUTION_READY)

    @property
    def can_send(self) -> bool:
        """Only one state can. Note that AUTHENTICATED is not it."""
        return self is ConnectionState.EXECUTION_READY


class Halted(RuntimeError):
    """The adapter has halted. Never caught internally; a halt requires a person."""


@dataclass
class Credentials:
    """Read from the environment, and structurally difficult to leak.

    `__repr__` and `__str__` are overridden because the default dataclass repr would print
    the key, and a dataclass ends up inside an exception, a log line or a debugger sooner or
    later. §20 of the brief lists every place a secret must not appear; the cheapest way to
    satisfy all of them at once is for the object to have no printable form.
    """

    username: str
    _api_key: str = field(repr=False, default="")

    @classmethod
    def from_environment(cls) -> Credentials:
        user = os.environ.get(ENV_USER, "").strip()
        key = os.environ.get(ENV_KEY, "").strip()
        if not user or not key:
            missing = [n for n, v in ((ENV_USER, user), (ENV_KEY, key)) if not v]
            raise NotPermitted(
                f"ProjectX credentials are not in the environment: {', '.join(missing)} "
                f"unset or empty. They are read from the environment only - never from an "
                f"argument, a repository file, or a config object that might be logged.")
        return cls(username=user, _api_key=key)

    def payload(self) -> dict:
        """The login body. The only place the key is materialised."""
        return {"userName": self.username, "apiKey": self._api_key}

    def __repr__(self) -> str:
        return f"Credentials(username={self.username!r}, api_key=<redacted>)"

    __str__ = __repr__


@dataclass
class Session:
    """A token and its expiry. The token is never logged and never returned."""

    _token: str = field(repr=False, default="")
    issued: dt.datetime | None = None

    @property
    def expires(self) -> dt.datetime | None:
        return None if self.issued is None else self.issued + TOKEN_LIFETIME

    @property
    def valid(self) -> bool:
        if not self._token or self.issued is None:
            return False
        return dt.datetime.now(dt.UTC) < (self.issued + TOKEN_LIFETIME)

    @property
    def needs_refresh(self) -> bool:
        """True inside the margin before expiry, so refresh happens before a 401, not after."""
        if not self._token or self.issued is None:
            return True
        return dt.datetime.now(dt.UTC) >= (self.issued + TOKEN_LIFETIME - REFRESH_MARGIN)

    def header(self) -> dict:
        if not self._token:
            raise Halted("no session token; authenticate first")
        return {"Authorization": f"Bearer {self._token}"}

    def __repr__(self) -> str:
        state = "valid" if self.valid else "invalid"
        return f"Session(token=<redacted>, {state}, expires={self.expires})"

    __str__ = __repr__


class ProjectXAdapter(ExecutionAdapter):
    """Order translation and lifecycle for ProjectX / TopstepX.

    Construct with `transport=None` (the default) and the adapter cannot make a network call
    at all: there is nothing to call. A transport is injected by the caller, which keeps this
    module free of an HTTP dependency and makes every test offline by construction.
    """

    name = "projectx"
    #: The default is the top rung, so an adapter used carelessly is refused rather than
    #: permitted. `for_dry_run` and `for_practice` lower it deliberately.
    requires = Mode.EXECUTION_READY

    def __init__(self, *, transport=None, base_url: str | None = None,
                 dry_run: bool = True, account_id: str = "",
                 on_event=None):
        self.transport = transport
        self.base_url = (base_url or os.environ.get(ENV_BASE) or DEFAULT_BASE).rstrip("/")
        self.dry_run = dry_run
        self.account_id = account_id
        self.state = ConnectionState.DISCONNECTED
        self.session = Session()
        self.credentials: Credentials | None = None
        self.requires = Mode.PRACTICE if dry_run else Mode.EXECUTION_READY
        #: Everything a dry run would have sent. The deliverable of a dry run.
        self.would_send: list[dict] = []
        self.open: list[dict] = []
        self._symbol_by_order: dict[str, str] = {}
        self._on_event = on_event
        self._halt_reason = ""

    # -- constructors that say what they are -------------------------------------------------

    @classmethod
    def for_dry_run(cls, **kw) -> ProjectXAdapter:
        """Translate and record orders, never send them. The safe default made explicit."""
        kw["dry_run"] = True
        return cls(**kw)

    @classmethod
    def for_practice(cls, account_id: str, *, transport, **kw) -> ProjectXAdapter:
        """A practice account. Real API, fake money, real rules.

        Still refuses to send until `arm()` has confirmed the account is a practice account
        against the venue - the caller asserting it is not evidence.
        """
        return cls(transport=transport, account_id=account_id, dry_run=False, **kw)

    # -- events and halting --------------------------------------------------------------------

    def _emit(self, event: str, **fields) -> None:
        if self._on_event is not None:
            self._on_event(event, **fields)

    def halt(self, reason: str) -> None:
        """Terminal. Nothing in this module clears a halt; a person does, by restarting."""
        self.state = ConnectionState.HALTED
        self._halt_reason = reason
        self._emit("projectx_halted", reason=reason)

    def _check_live(self) -> None:
        if self.state is ConnectionState.HALTED:
            raise Halted(f"adapter is halted: {self._halt_reason}")

    # -- authentication --------------------------------------------------------------------------

    def authenticate(self, credentials: Credentials | None = None) -> ConnectionState:
        """Exchange credentials for a token. Grants read access and nothing else.

        Returns AUTHENTICATED on success. Note what that state does NOT permit: `can_send`
        is False for it, and remains False until `arm()` is called with a matching authority.
        """
        self._check_live()
        if self.transport is None:
            raise NotPermitted(
                "no transport is configured, so this adapter cannot make a network call. "
                "That is the default and it is deliberate: inject a transport explicitly "
                "when a real connection is intended.")
        self.credentials = credentials or Credentials.from_environment()
        self.state = ConnectionState.AUTHENTICATING
        self._emit("projectx_authenticating", base_url=self.base_url,
                   username=self.credentials.username)
        try:
            body = self.transport.post(self.base_url + AUTH_PATH,
                                       json=self.credentials.payload())
        except Exception as exc:                                        # noqa: BLE001
            # The exception is not re-raised with its context: a transport error can carry
            # the request body, and the request body is the API key.
            self.halt(f"authentication transport failed: {type(exc).__name__}")
            raise Halted("authentication failed; see the halt reason") from None

        if not isinstance(body, dict) or not body.get("success"):
            code = body.get("errorCode") if isinstance(body, dict) else "?"
            self.halt(f"authentication rejected by the venue, errorCode={code}")
            raise Halted(f"authentication rejected, errorCode={code}")
        token = body.get("token") or ""
        if not token:
            self.halt("authentication reported success with no token")
            raise Halted("authentication reported success with no token")

        self.session = Session(_token=token, issued=dt.datetime.now(dt.UTC))
        self.state = ConnectionState.AUTHENTICATED
        self._emit("projectx_authenticated", expires=str(self.session.expires))
        return self.state

    def ensure_session(self) -> None:
        """Re-authenticate before the token expires rather than after a 401."""
        self._check_live()
        if self.session.needs_refresh and self.state.can_read:
            self._emit("projectx_token_refresh", expires=str(self.session.expires))
            self.authenticate(self.credentials)

    # -- arming ------------------------------------------------------------------------------------

    def arm(self, authority: Authority, *, confirmed_practice: bool | None = None
            ) -> ConnectionState:
        """Move from "logged in" to "may act", which are different things.

        `confirmed_practice` must come from a venue query, not from the caller's belief. It
        is a required argument for a non-dry-run session precisely so that "I think this is
        the practice account" cannot be left implicit.
        """
        self._check_live()
        if self.state is not ConnectionState.AUTHENTICATED:
            raise Halted(f"cannot arm from {self.state.value}; authenticate first")

        if self.dry_run:
            authority.require(Mode.PRACTICE, what="arming a ProjectX dry run")
            self.state = ConnectionState.DRY_RUN
            self._emit("projectx_armed", state=self.state.value)
            return self.state

        if confirmed_practice is None:
            raise NotPermitted(
                "arming a non-dry-run session requires confirmed_practice to be True or "
                "False, established by querying the venue. The caller's belief about which "
                "account this is does not count as evidence.")
        if confirmed_practice:
            authority.require(Mode.PRACTICE, what="arming a ProjectX practice account")
            self.state = ConnectionState.PRACTICE_READY
        else:
            authority.require(Mode.EXECUTION_READY,
                              what="arming a ProjectX FUNDED account for real orders")
            self.state = ConnectionState.EXECUTION_READY
        self._emit("projectx_armed", state=self.state.value, practice=confirmed_practice)
        return self.state

    # -- the boundary ------------------------------------------------------------------

    def _translate(self, intent: OrderIntent) -> dict:
        """OrderIntent -> the request body shape.

        The field names here follow the documented order model in `docs/topstep/API.md`.
        Where that document records an UNKNOWN, the value is passed through under a name
        marked in the doc rather than invented - a wrong field name fails loudly at the
        venue, whereas a plausible invented one can be silently ignored.
        """
        side = 0 if intent.side is Side.BUY else 1
        type_map = {
            OrderType.MARKET: 2,
            OrderType.LIMIT: 1,
            OrderType.FLATTEN: 2,      # the venue has no flatten; it is a market order
        }
        body = {
            "accountId": self.account_id,
            "contractId": intent.symbol,
            "type": type_map.get(intent.order_type, 2),
            "side": side,
            "size": int(abs(intent.quantity)),
            "customTag": intent.tag or None,
        }
        if intent.order_type is OrderType.LIMIT:
            body["limitPrice"] = intent.limit_price
        return body

    def submit(self, intent: OrderIntent) -> Ack:
        """Translate, then send only if BOTH the connection and the process permit it."""
        self._check_live()
        body = self._translate(intent)

        if self.dry_run or not self.state.can_send:
            # No request is built and not sent - the transport is not reached at all. There
            # is no boolean here that could be flipped to make this send.
            self.would_send.append(body)
            self._emit("projectx_dry_run", symbol=intent.symbol,
                       side=intent.side.value, qty=intent.quantity, state=self.state.value)
            return Ack(intent=intent, accepted=False,
                       reason=f"dry run: recorded, not sent (state={self.state.value})",
                       handle=body)

        raise NotPermitted(
            "live order submission is not implemented in this module. The architecture is "
            "complete to this line deliberately: the brief that produced it forbids enabling "
            "live execution, and an implementation present but gated is one edit from an "
            "accident, whereas an implementation absent is not. Wiring it requires the "
            "order endpoint from docs/topstep/API.md to be verified first.")

    def working(self) -> dict[str, float]:
        """Outstanding quantity per symbol. Empty in a dry run - nothing is outstanding."""
        if self.dry_run or not self.state.can_send:
            return {}
        raise NotPermitted(
            "position queries require a verified endpoint; see "
            "docs/topstep/API_UNKNOWNS.md")

    # -- reconciliation ----------------------------------------------------------------

    def reconcile(self, local_positions: dict[str, float]) -> dict:
        """Compare local belief against the venue, and HALT on any disagreement.

        §23: local state is UNVERIFIED at startup. The correct response to a mismatch is to
        stop, not to "fix" it - a difference means one of the two is wrong, and deleting the
        information that reveals which is the worst available move.
        """
        self._check_live()
        if not self.state.can_read:
            raise Halted(f"cannot reconcile from {self.state.value}")
        raise NotPermitted(
            "reconciliation requires the position and order endpoints, which are recorded as "
            "UNKNOWN in docs/topstep/API_UNKNOWNS.md until verified against the official "
            "documentation. Returning an empty position set here would look like agreement "
            "with any local state, which is the single most dangerous possible stub.")

    def describe(self) -> str:
        account = self.account_id or "<unset>"
        session = "valid" if self.session.valid else "invalid"
        return (f"projectx {self.state.value} dry_run={self.dry_run} "
                f"account={account} session={session}")
