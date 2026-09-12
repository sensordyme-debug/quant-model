"""State scoping: a simulation must not be able to write the live account's files.

THE DEFECT THIS EXISTS TO MAKE IMPOSSIBLE
------------------------------------------
`research/audit_2026-09-12.md` AUD-04, still open at the time of writing, and visible in the
deployed file:

    live/state/last_run.json
      "equity": 100000.0, "equity_high": 100000.0,
      "equity_curve": [100000.0, 100000.0, 100000.0, 100000.0],
      "held_age": {"XLE": 15, "XLK": 15, "IWM": 6},
      "dry_run": true

Those 100,000s are `paper_trade.MockAccount.net_liq`, not the IBKR account. `--mock` and
`--dry-run` call the same `save_state()` the real run does, so seven simulated runs on one
signal date wrote themselves into the live equity curve and pushed `held_age` to 15. The
audit's assessment holds: it is harmless *only* because the champion ships with the drawdown
breaker off. Turn the breaker on and it reads a ~90% drawdown against a fabricated
`equity_high` and liquidates a real book.

Part 19 asks for this to be "enforced architecturally, not merely by naming files
differently". The distinction matters, because a naming convention is what already failed
here - `save_state` knew the run was a dry run (it writes `"dry_run": true` into the file it
is corrupting) and wrote to the live path anyway.

HOW IT IS ENFORCED
------------------
A caller does not choose a path. It chooses a `StateScope`, gets a `StateStore`, and the
store is the only way to name a file. Every resolved path is checked to be inside that
scope's root, so `store.path("../../live/state/last_run.json")` raises rather than escaping.
A store built for a simulation has no method that reaches the live directory - not a
discouraged one, none.

`StateScope.for_run()` is the second half: it derives the scope from the runner's own flags
in one place, so a new flag combination cannot silently resolve to LIVE.
"""
from __future__ import annotations

import enum
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]


class StateScopeError(RuntimeError):
    """A write was attempted outside the store's scope. Never catch this to continue."""


class StateScope(str, enum.Enum):
    """Who owns a piece of state, and therefore where it may live.

    LIVE and PAPER share a directory on purpose: this system's "live" IS an IBKR paper
    account, and splitting them would create a second real-money path to keep in sync for no
    benefit today. They are separate enum members so that when a funded account appears, the
    split is a one-line change to `root_for` rather than an audit of every caller.
    """

    LIVE = "live"
    PAPER = "paper"
    DRYRUN = "dryrun"
    BACKTEST = "backtest"
    RESEARCH = "research"

    @property
    def is_real(self) -> bool:
        """True when this state describes an actual broker account.

        The single predicate every guard in this module is written against.
        """
        return self in (StateScope.LIVE, StateScope.PAPER)

    @classmethod
    def for_run(cls, *, mock: bool = False, dry_run: bool = False,
                backtest: bool = False, research: bool = False) -> StateScope:
        """Derive the scope from a runner's flags, in one place.

        Ordered most-simulated first so that any combination of flags resolves to the LEAST
        privileged scope. `--mock --dry-run` is MOCK, not LIVE; an unrecognised future flag
        combination that forgets to set one of these still cannot reach PAPER unless every
        simulation flag is false. Getting this backwards is precisely AUD-04.
        """
        if mock:
            return cls.RESEARCH
        if backtest:
            return cls.BACKTEST
        if research:
            return cls.RESEARCH
        if dry_run:
            return cls.DRYRUN
        return cls.PAPER


def root_for(scope: StateScope, *, base: Path | None = None) -> Path:
    """The only directory a store of `scope` may touch.

    Simulated scopes nest under the live directory rather than living elsewhere so that
    `live/state/` remains the one place an operator looks, and so the existing `.gitignore`
    entry for `live/state/` keeps covering them. Nesting is safe because containment is
    checked against the *scope's own* root, not against `live/`.
    """
    base = base or (REPO / "live" / "state")
    if scope.is_real:
        return base
    return base / scope.value


@dataclass(frozen=True)
class StateStore:
    """Scoped file access. The only way to name a state file.

    Frozen: a store's scope cannot be changed after construction, so code that received a
    DRYRUN store cannot promote itself to PAPER.
    """

    scope: StateScope
    root: Path

    @classmethod
    def open(cls, scope: StateScope, *, base: Path | None = None) -> StateStore:
        root = root_for(scope, base=base).resolve()
        root.mkdir(parents=True, exist_ok=True)
        return cls(scope=scope, root=root)

    @classmethod
    def for_run(cls, *, base: Path | None = None, **flags: bool) -> StateStore:
        """Convenience: derive the scope from runner flags and open it."""
        return cls.open(StateScope.for_run(**flags), base=base)

    def path(self, name: str) -> Path:
        """Resolve `name` inside this scope, or raise.

        The containment check is the enforcement. `resolve()` collapses `..` before the
        comparison, so a traversal is caught rather than normalised into a valid live path.
        Absolute paths are refused outright - a caller with an absolute path has already
        decided where to write, which is the decision this class exists to take away.
        """
        candidate = Path(name)
        if candidate.is_absolute():
            raise StateScopeError(
                f"{self.scope.value} store: absolute path {name!r} is not addressable; "
                f"pass a name relative to the scope root")
        resolved = (self.root / candidate).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError:
            raise StateScopeError(
                f"{self.scope.value} store: {name!r} resolves to {resolved}, which is "
                f"outside the scope root {self.root}") from None
        return resolved

    def write_json(self, name: str, payload: object) -> Path:
        """Write a JSON document into this scope.

        Stamps `_scope` into any dict payload. That is not decoration: it means a state file
        found on disk can be identified as simulated even if it has somehow been copied into
        the live directory, which is the failure mode the current `last_run.json` is in.
        """
        target = self.path(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, dict):
            payload = {**payload, "_scope": self.scope.value}
        target.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
        return target

    def read_json(self, name: str, default: Any = None) -> Any:
        """Read a JSON document from this scope, or `default` when it is absent or corrupt.

        Returns `Any` rather than `object`, matching `json.loads`. A JSON document's shape is
        genuinely dynamic, and typing it as `object` would force every caller to cast before
        subscripting - friction that buys no safety, since the cast is unchecked either way.
        """
        target = self.path(name)
        if not target.exists():
            return default
        try:
            return json.loads(target.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return default

    def append_jsonl(self, name: str, record: dict) -> Path:
        target = self.path(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({**record, "_scope": self.scope.value}, default=str) + "\n")
        return target

    def exists(self, name: str) -> bool:
        return self.path(name).exists()


def scope_of(payload: object) -> StateScope | None:
    """Read the `_scope` stamp off a loaded state document, if it has one.

    Returns None for documents written before stamping existed - which is how the current
    contaminated `last_run.json` reads, and why `is_contaminated` below treats a missing
    stamp plus a `dry_run` flag as the tell.
    """
    if isinstance(payload, dict):
        raw = payload.get("_scope")
        if isinstance(raw, str):
            try:
                return StateScope(raw)
            except ValueError:
                return None
    return None


def is_contaminated(payload: object) -> bool:
    """True when a document in a real-money location was produced by a simulation.

    Two tells, either sufficient:
      * a `_scope` stamp that is not a real scope;
      * the legacy `"dry_run": true` flag that `paper_trade.save_state` already writes -
        which is what makes the currently deployed file detectable without a migration.

    Intended as a pre-flight assertion for the daily runner: refuse to size against state a
    simulation wrote, rather than reading a fabricated equity_high and acting on it.
    """
    if not isinstance(payload, dict):
        return False
    stamped = scope_of(payload)
    if stamped is not None and not stamped.is_real:
        return True
    return bool(payload.get("dry_run"))
