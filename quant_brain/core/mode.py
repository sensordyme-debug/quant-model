"""What this process is allowed to do, and why it is almost never "trade real money".

This is the safety spine. `RoutedExecutor` already guarantees that every order passes the
risk chain; that answers "is this order permitted?" It does not answer the prior question,
"is this PROCESS permitted to reach a venue at all?" - and that is the question a research
loop, a backtest and a scheduled job all get wrong in the same way, by being one
misconfiguration away from a real order.

THE LADDER
----------
    RESEARCH          in-memory only. No adapter may be reached, not even a simulated one
                      that talks to a network.
    BACKTEST          simulated adapters only.
    VALIDATED         simulated only; the label records that a promotion gate has passed.
    PAPER             a broker's paper endpoint. Real API, fake money.
    PRACTICE          a prop firm's practice account. Real API, fake money, real rules.
    HUMAN_APPROVAL    a person has reviewed and signed off, and the signature is on disk.
    EXECUTION_READY   real money.

A mode is not a preference. `Authority.permits()` is consulted before an adapter is handed
an intent, and an adapter declares the minimum mode it requires. A simulated adapter needs
BACKTEST; the IBKR adapter pointed at a paper port needs PAPER; a prop-firm adapter pointed
at a funded account needs EXECUTION_READY.

WHY EXECUTION_READY CANNOT BE REACHED BY CONFIGURATION ALONE
--------------------------------------------------------------
Three independent things must be true at once, and no single edit can supply all three:

  1. the process asked for it explicitly (an argument, not a default)
  2. an environment variable set outside the code says live trading is enabled
  3. an approval FILE exists on disk, created by a person, naming what was approved

Any one of those alone is an accident waiting to happen. A default is an accident. An
environment variable alone is an accident - the wrong shell, a copied service definition. A
file alone is an accident - a stale artefact from a month ago. Requiring all three means the
accident has to happen three times, in three different places, in the same direction.

The repository already applies exactly this pattern to the equity sleeve, where live trading
requires a human-created `live/APPROVED_PAPER.md`. This generalises it rather than inventing
it: `CLAUDE.md` records that convention, and it has held.

WHAT THIS MODULE DELIBERATELY DOES NOT DO
-------------------------------------------
It does not authenticate, connect, or know what a broker is. Authority is about permission,
not capability. Keeping them apart is what stops "we managed to log in" from sliding into
"therefore we may trade", which is the single most common way a paper integration becomes a
live one.
"""
from __future__ import annotations

import datetime as dt
import enum
import os
from dataclasses import dataclass
from pathlib import Path

#: The environment variable that must say so before real money is reachable. Named with the
#: verb in it so that reading a process listing or a service file makes the intent obvious.
LIVE_ENV = "QB_LIVE_TRADING_ENABLED"

#: Where a human records that they approved something. One file per venue+account, so an
#: approval for a practice account cannot be silently reused for a funded one.
APPROVAL_DIR = Path("live/approvals")


class Mode(enum.IntEnum):
    """Ordered, so `>=` is the permission test. Higher means closer to real money."""

    RESEARCH = 0
    BACKTEST = 1
    VALIDATED = 2
    PAPER = 3
    PRACTICE = 4
    HUMAN_APPROVAL = 5
    EXECUTION_READY = 6

    @property
    def touches_a_venue(self) -> bool:
        """Does this mode involve a real API call to somebody else's server?"""
        return self >= Mode.PAPER

    @property
    def risks_real_money(self) -> bool:
        return self is Mode.EXECUTION_READY


class NotPermitted(PermissionError):
    """The process is not allowed to do this. Always fatal; never caught and downgraded."""


@dataclass(frozen=True)
class Authority:
    """What one process may do. Immutable, because a mutable one would get raised mid-run.

    Construct with `Authority.research()` and friends rather than by hand, so the checks in
    `for_live()` cannot be skipped by passing the enum directly.
    """

    mode: Mode
    #: Free text naming what was approved and by whom, carried for the audit trail.
    note: str = ""
    venue: str = ""
    account: str = ""

    # -- constructors -----------------------------------------------------------------------

    @classmethod
    def research(cls) -> Authority:
        return cls(Mode.RESEARCH, note="in-memory research")

    @classmethod
    def backtest(cls) -> Authority:
        return cls(Mode.BACKTEST, note="simulated adapters only")

    @classmethod
    def paper(cls, venue: str, account: str = "") -> Authority:
        return cls(Mode.PAPER, note="broker paper endpoint", venue=venue, account=account)

    @classmethod
    def practice(cls, venue: str, account: str = "") -> Authority:
        return cls(Mode.PRACTICE, note="prop-firm practice account", venue=venue,
                   account=account)

    @classmethod
    def for_live(cls, venue: str, account: str, *, i_understand_this_is_real_money: bool = False,
                 approval_dir: Path | None = None) -> Authority:
        """The only way to EXECUTION_READY, and it refuses unless all three conditions hold.

        The keyword is spelled out rather than `live=True` on purpose: it has to be typed,
        it cannot be passed accidentally by a `**kwargs` splat from a config file, and it
        reads as an assertion in the diff that introduces it.
        """
        if not i_understand_this_is_real_money:
            raise NotPermitted(
                "live execution requires i_understand_this_is_real_money=True. This is not a "
                "formality: it is the one condition that cannot be supplied by configuration, "
                "so it must appear in a diff that a person wrote.")
        env = os.environ.get(LIVE_ENV, "").strip().lower()
        if env not in {"1", "true", "yes"}:
            raise NotPermitted(
                f"{LIVE_ENV} is not set to a truthy value (found {env!r}). Live execution "
                f"requires it to be set OUTSIDE the code, so that a checkout of this "
                f"repository cannot trade by itself.")
        path = approval_for(venue, account, approval_dir)
        if not path.exists():
            raise NotPermitted(
                f"no approval file at {path}. A person must create it, naming what is being "
                f"approved. An environment variable alone is a stale-shell accident; a file "
                f"alone is a stale-artefact accident; both plus an explicit argument is three "
                f"accidents in three places in the same direction.")
        note = path.read_text(encoding="utf-8", errors="replace").strip()
        if not note:
            raise NotPermitted(f"{path} is empty; an approval with no statement of what was "
                               f"approved is not an approval")
        return cls(Mode.EXECUTION_READY, note=note, venue=venue, account=account)

    # -- the test ---------------------------------------------------------------------------

    def permits(self, required: Mode) -> bool:
        return self.mode >= required

    def require(self, required: Mode, *, what: str = "") -> None:
        """Raise unless this authority reaches `required`. The call sites are the boundary."""
        if not self.permits(required):
            raise NotPermitted(
                f"{what or 'this operation'} requires {required.name} but this process holds "
                f"{self.mode.name}. Modes are ordered and this one is lower; nothing in the "
                f"code can raise it, which is the point.")

    def describe(self) -> str:
        where = f" {self.venue}/{self.account}" if self.venue else ""
        return f"{self.mode.name}{where}" + (f" - {self.note}" if self.note else "")


def approval_for(venue: str, account: str, approval_dir: Path | None = None) -> Path:
    """Where the approval for one venue+account lives.

    Per account, deliberately. A single global approval file would let a signature for a
    practice account authorise a funded one, which is the exact substitution this whole
    ladder exists to prevent.
    """
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in f"{venue}-{account}")
    return (approval_dir or APPROVAL_DIR) / f"{safe}.md"


def from_environment(default: Mode = Mode.RESEARCH) -> Authority:
    """Read the mode from configuration, refusing to produce EXECUTION_READY.

    Configuration can select any mode up to PRACTICE. It cannot select live: that path runs
    through `for_live` and its three conditions. A config file that could grant live
    execution would make every deployment one typo away from trading.
    """
    raw = os.environ.get("QB_ACCOUNT_MODE", "").strip().upper()
    if not raw:
        return Authority(default, note="default; QB_ACCOUNT_MODE unset")
    try:
        mode = Mode[raw]
    except KeyError:
        raise NotPermitted(
            f"QB_ACCOUNT_MODE={raw!r} is not a mode. Valid: "
            f"{', '.join(m.name for m in Mode)}") from None
    if mode >= Mode.HUMAN_APPROVAL:
        raise NotPermitted(
            f"QB_ACCOUNT_MODE cannot select {mode.name}. Anything at or above "
            f"{Mode.HUMAN_APPROVAL.name} requires Authority.for_live(), which additionally "
            f"needs {LIVE_ENV} and an on-disk approval file.")
    return Authority(mode, note=f"QB_ACCOUNT_MODE={raw}",
                     venue=os.environ.get("QB_VENUE", ""),
                     account=os.environ.get("QB_ACCOUNT", ""))


def write_approval(venue: str, account: str, *, approved_by: str, statement: str,
                   approval_dir: Path | None = None) -> Path:
    """Helper for a HUMAN to record an approval. Never called by automation.

    Present so the file has a documented shape rather than being invented differently by
    each person, and so the audit trail records who and when. It does not grant anything by
    itself - `for_live` still needs the environment variable and the explicit argument.
    """
    if not approved_by.strip() or not statement.strip():
        raise ValueError("an approval must name who approved it and what they approved")
    path = approval_for(venue, account, approval_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    path.write_text(
        f"# Live execution approval\n\n"
        f"- venue: {venue}\n- account: {account}\n- approved_by: {approved_by}\n"
        f"- when: {stamp}\n\n{statement.strip()}\n",
        encoding="utf-8")
    return path
