"""Configuration: what is a secret, what is a setting, what is a policy, and what is a target.

WHY THIS MODULE EXISTS
----------------------
`.env.example` documented four safety flags:

    DRY_RUN=true
    LIVE_TRADING_ENABLED=false
    EXECUTION_ENABLED=false
    ORDER_TRANSMISSION_ENABLED=false

Measured 2026-09-14: **not one of them was read by anything.** `EXECUTION_ENABLED` appeared
nowhere in the repository outside that file. `ORDER_TRANSMISSION_ENABLED` existed only as a
Python constant of the same name inside two runners, which is a different thing that happens
to share a spelling. `DRY_RUN` and `LIVE_TRADING_ENABLED` matched only an enum member and a
substring of `QB_LIVE_TRADING_ENABLED`.

Four lines of a safety contract that nothing enforced. A reader setting
`ORDER_TRANSMISSION_ENABLED=true` in their shell would have changed nothing, and a reader
setting it to `false` and believing they had disabled something would have been equally
wrong. Documentation that describes a control which does not exist is worse than no
documentation, because it is trusted.

THE FOUR KINDS OF CONFIGURATION, KEPT APART
-------------------------------------------
    SECRET          PROJECTX_USERNAME, PROJECTX_API_KEY, and the data-vendor keys.
                    Never committed, never printed, never in an exception, never in a log.
                    This module handles them by PRESENCE ONLY: it will tell you whether a
                    credential is set and it has no method that returns one.

    RUNTIME         PROJECTX_BASE_URL, QB_VENUE. Non-secret, environment-dependent.

    SAFETY POLICY   the four flags above. What this process may attempt.

    TARGET          TOPSTEP_TARGET_ACCOUNT_ID. Which account. Never inferred, never
                    defaulted, never guessed - an unset target is an error, not "the first
                    one we find".

Keeping them apart matters because they have different failure modes. A missing secret is a
setup problem. A wrong target is a catastrophe. A permissive safety flag is a catastrophe
that looks like a setup problem.

NO SINGLE FLAG IS SUFFICIENT
----------------------------
`execution_permitted()` is an AND over five independent conditions, and it returns the FULL
list of reasons it said no rather than short-circuiting, so a reader fixing one never
discovers the next one at run time:

    1. DRY_RUN is false
    2. LIVE_TRADING_ENABLED is true
    3. EXECUTION_ENABLED is true
    4. ORDER_TRANSMISSION_ENABLED is true
    5. an `Authority` reaching `Mode.EXECUTION_READY`, which `mode.py` will only produce
       from `Authority.for_live()` and its own three conditions: a typed
       `i_understand_this_is_real_money=True`, the `QB_LIVE_TRADING_ENABLED` environment
       variable, and a non-empty human-written approval file for that exact venue+account.

So eight conditions in total, in four different places: a shell, a file, a typed argument,
and this module. And even all eight together do not currently transmit anything - see
`test_no_configuration_makes_transmission_possible`. The adapter has no live branch to reach
and both runners carry a literal code-level constant. Configuration is the outermost of
several layers, not the only one.

FAIL CLOSED, AND ASYMMETRICALLY
-------------------------------
The three ENABLING flags are true only for an explicit `1`, `true` or `yes`. Anything else,
including unset, empty, misspelled or `TRUE-ish` nonsense, is false.

`DRY_RUN` is PROTECTIVE, so it inverts: it is true unless explicitly `0`, `false` or `no`.
Unset means dry run. A typo means dry run.

Both rules point the same way: an unreadable configuration is a safe configuration. That is
why an unrecognised value is reported as `CONFIG_INVALID` *and* treated as the safe value,
rather than one or the other. Refusing to run on a typo is right; refusing while also
guessing the dangerous interpretation would not be.
"""
from __future__ import annotations

import enum
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from quant_brain.core.mode import Authority, Mode

REPO = Path(__file__).resolve().parents[2]

#: The one gitignored file that holds real credentials. It already existed for the data
#: vendors and is parsed by `scripts/apikeys.py`; ProjectX credentials go in the same file in
#: the same `KEY=value` format rather than a second file with a second set of mistakes
#: available. `.gitignore` covers it, and `secret_files_tracked_by_git()` checks rather than
#: assumes.
SECRET_FILE = REPO / "live" / "secrets.env"

ENV_PROJECTX_USER = "PROJECTX_USERNAME"
ENV_PROJECTX_KEY = "PROJECTX_API_KEY"
ENV_PROJECTX_BASE = "PROJECTX_BASE_URL"
ENV_TARGET_ACCOUNT = "TOPSTEP_TARGET_ACCOUNT_ID"

ENV_DRY_RUN = "DRY_RUN"
ENV_LIVE_TRADING = "LIVE_TRADING_ENABLED"
ENV_EXECUTION = "EXECUTION_ENABLED"
ENV_TRANSMISSION = "ORDER_TRANSMISSION_ENABLED"

#: Every name this module treats as a credential. Used to decide what may be reported as
#: PRESENT/MISSING and, more importantly, what must never be returned.
SECRET_NAMES = frozenset({
    ENV_PROJECTX_USER, ENV_PROJECTX_KEY,
    "ALPACA_API_KEY", "ALPACA_SECRET_KEY", "THETADATA_API_KEY", "FMP_API_KEY",
    "POLYGON_API_KEY", "FINNHUB_API_KEY", "NASDAQ_DATA_LINK_API_KEY", "TELEGRAM_BOT_TOKEN",
})

_TRUE = frozenset({"1", "true", "yes"})
_FALSE = frozenset({"0", "false", "no"})


class ConfigError(ValueError):
    """A configuration value is malformed.

    A subclass of ValueError rather than of anything in `mode.py`, because a bad config is a
    setup mistake and a refused authority is a policy decision, and conflating them makes
    both harder to read in a traceback.
    """


class ConfigState(str, enum.Enum):
    """What the configuration permits. Ordered, and ordered deliberately.

    AUTHENTICATION IS NOT AUTHORIZATION. Having a working username and API key puts you at
    `READ_ONLY_CONFIGURED`, three states below anything that can act on an account and four
    below anything that could trade. The gap is the point: every prop-firm accident starts
    with a process that could log in.
    """

    #: A required input is absent. Nothing can be attempted.
    CONFIG_MISSING = "CONFIG_MISSING"
    #: Inputs are present and at least one is malformed. Treated as strictly worse than
    #: missing: a missing value is honest, a malformed one means somebody believed they had
    #: configured something.
    CONFIG_INVALID = "CONFIG_INVALID"
    #: Credentials present, no target account. Enough to authenticate and to LIST accounts.
    #: Not enough to read one, because there is no "the" account until a person names it.
    READ_ONLY_CONFIGURED = "READ_ONLY_CONFIGURED"
    #: Credentials and an explicit target account. Read-only work against that account.
    READ_ONLY_READY = "READ_ONLY_READY"
    #: The above, plus every safety flag in its permissive position, plus an authority
    #: reaching PRACTICE. Would permit practice-account order flow if a transmission path
    #: existed. None does.
    PRACTICE_READY = "PRACTICE_READY"
    #: The above, plus an authority reaching EXECUTION_READY. Unreachable from configuration
    #: alone by construction: `mode.from_environment()` refuses to produce it.
    LIVE_EXECUTION_AUTHORIZED = "LIVE_EXECUTION_AUTHORIZED"


def _flag(name: str, *, protective: bool, problems: list[str]) -> bool:
    """One flag, fail-closed, with a malformed value recorded rather than swallowed."""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return True if protective else False
    v = raw.strip().lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    problems.append(
        f"{name} is set to an unrecognised value. Accepted: {sorted(_TRUE)} or "
        f"{sorted(_FALSE)}, case-insensitive. Treated as "
        f"{'true (dry run stays on)' if protective else 'false (stays disabled)'}."
    )
    return True if protective else False


@dataclass(frozen=True)
class SafetyFlags:
    """The four flags, as booleans, after fail-closed parsing.

    `permissive` is the AND that matters. It is a property rather than a stored field so that
    no code path can construct a `SafetyFlags` claiming to be permissive while holding flags
    that are not.
    """

    dry_run: bool = True
    live_trading_enabled: bool = False
    execution_enabled: bool = False
    order_transmission_enabled: bool = False

    @classmethod
    def from_environment(cls, problems: list[str] | None = None) -> SafetyFlags:
        p = problems if problems is not None else []
        return cls(
            dry_run=_flag(ENV_DRY_RUN, protective=True, problems=p),
            live_trading_enabled=_flag(ENV_LIVE_TRADING, protective=False, problems=p),
            execution_enabled=_flag(ENV_EXECUTION, protective=False, problems=p),
            order_transmission_enabled=_flag(ENV_TRANSMISSION, protective=False, problems=p),
        )

    @property
    def permissive(self) -> bool:
        """True only when all four say yes. Never call this expecting a single flag to win."""
        return (not self.dry_run and self.live_trading_enabled
                and self.execution_enabled and self.order_transmission_enabled)

    def blocking(self) -> list[str]:
        """Every flag standing in the way, not just the first.

        Returning all of them is deliberate. A caller who fixes one and re-runs would
        otherwise discover the next one at the next attempt, which teaches that the boundary
        is a sequence of small obstacles rather than a wall.
        """
        out = []
        if self.dry_run:
            out.append(f"{ENV_DRY_RUN} is true")
        if not self.live_trading_enabled:
            out.append(f"{ENV_LIVE_TRADING} is not true")
        if not self.execution_enabled:
            out.append(f"{ENV_EXECUTION} is not true")
        if not self.order_transmission_enabled:
            out.append(f"{ENV_TRANSMISSION} is not true")
        return out


def load_secret_file(path: Path | None = None, *, export: bool = True) -> frozenset[str]:
    """Load `live/secrets.env` into the environment. Returns the NAMES found, never a value.

    Same format and same precedence as `scripts/apikeys.py`, which has parsed this file since
    before this module existed and still does: `KEY=value`, `#` comments, optional surrounding
    quotes, and `setdefault` so an already-exported environment variable wins over the file.
    Two parsers of one file is a duplication worth accepting, because the alternative was
    making `quant_brain` import from `scripts/`, which inverts the dependency the whole
    package is arranged to avoid.

    An existing environment variable winning is the right precedence for this repository: it
    lets a scheduled task or a CI job supply a credential without a file, and it lets a shell
    override the file for one command without editing it.
    """
    p = path or SECRET_FILE
    found: set[str] = set()
    if not p.exists():
        return frozenset()
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        if not k:
            continue
        found.add(k)
        if export:
            os.environ.setdefault(k, v.strip().strip('"').strip("'"))
    return frozenset(found)


def _present(name: str) -> bool:
    return bool(os.environ.get(name, "").strip())


def secret_files_tracked_by_git(repo: Path | None = None) -> list[str]:
    """Which known-credential paths git is tracking. Empty is the only acceptable answer.

    Asks git rather than reading `.gitignore`, because those are different questions: a file
    added before a rule was written stays tracked forever and `.gitignore` will not say so.
    That is exactly how a secret gets committed by somebody who checked the ignore file.

    Returns an empty list when git is unavailable, which is a limitation and not a pass; the
    doctor reports the difference.
    """
    root = repo or REPO
    if shutil.which("git") is None:
        return []
    candidates = ("live/secrets.env", "live/secrets.json", ".env")
    try:
        res = subprocess.run(["git", "ls-files", "-z", "--", *candidates,
                              ".env.*", "live/*.env", "live/*secret*"],
                             cwd=root, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):       # pragma: no cover
        return []
    if res.returncode != 0:                             # pragma: no cover
        return []
    hits = [x for x in res.stdout.split(chr(0)) if x.strip()]
    # `.env.example` and anything else ending `.example`, `.template` or `.sample` is a
    # placeholder that is SUPPOSED to be tracked - that is the whole point of it. Excluded
    # by suffix rather than by name, so a future `live/projectx.env.example` is covered
    # too. That those files carry no real value is tested, not assumed: see
    # test_the_tracked_template_contains_nothing_that_looks_like_a_real_value.
    return sorted(h for h in hits
                  if not h.endswith((".example", ".template", ".sample")))


@dataclass(frozen=True)
class Configuration:
    """A snapshot of configuration, holding no secret value.

    Every credential is reduced to a boolean at construction. There is no field, property or
    method on this object that returns a credential, so it cannot leak one into a log, a
    repr, an exception or a report - not by discipline but because the value is not here.
    """

    projectx_username_present: bool = False
    projectx_api_key_present: bool = False
    target_account_id: str = ""
    base_url: str = ""
    flags: SafetyFlags = field(default_factory=SafetyFlags)
    problems: tuple[str, ...] = ()
    secret_file_exists: bool = False
    secret_names_in_file: tuple[str, ...] = ()

    @classmethod
    def load(cls, *, secret_file: Path | None = None, export: bool = True) -> Configuration:
        problems: list[str] = []
        names = load_secret_file(secret_file, export=export)
        flags = SafetyFlags.from_environment(problems)

        target = os.environ.get(ENV_TARGET_ACCOUNT, "").strip()
        if target and not all(c.isalnum() or c in "-_" for c in target):
            problems.append(
                f"{ENV_TARGET_ACCOUNT} contains characters outside [A-Za-z0-9-_]. An account "
                f"identifier is pasted from a dashboard, and a stray quote or trailing "
                f"comment is the usual cause; it is refused rather than trimmed, because "
                f"silently trimming a target account is how the wrong account gets traded.")

        p = secret_file or SECRET_FILE
        return cls(
            projectx_username_present=_present(ENV_PROJECTX_USER),
            projectx_api_key_present=_present(ENV_PROJECTX_KEY),
            target_account_id=target,
            base_url=os.environ.get(ENV_PROJECTX_BASE, "").strip(),
            flags=flags,
            problems=tuple(problems),
            secret_file_exists=p.exists(),
            secret_names_in_file=tuple(sorted(names)),
        )

    # -- state -----------------------------------------------------------------------------

    @property
    def credentials_present(self) -> bool:
        return self.projectx_username_present and self.projectx_api_key_present

    def state(self, authority: Authority | None = None) -> ConfigState:
        """Where this configuration sits on the ladder.

        `authority` is optional and defaults to None rather than to
        `mode.from_environment()`, so that computing a state never has a side effect and
        never depends on process-wide state a caller did not pass in.
        """
        if self.problems:
            return ConfigState.CONFIG_INVALID
        if not self.credentials_present:
            return ConfigState.CONFIG_MISSING
        if not self.target_account_id:
            return ConfigState.READ_ONLY_CONFIGURED
        if not self.flags.permissive:
            return ConfigState.READ_ONLY_READY
        if authority is not None and authority.permits(Mode.EXECUTION_READY):
            return ConfigState.LIVE_EXECUTION_AUTHORIZED
        if authority is not None and authority.permits(Mode.PRACTICE):
            return ConfigState.PRACTICE_READY
        return ConfigState.READ_ONLY_READY

    def execution_permitted(self, authority: Authority | None = None) -> tuple[bool, list[str]]:
        """The AND. Returns (permitted, every reason it is not).

        Read the second element even when the first is False, and especially then: it lists
        all of the conditions that failed rather than the first, so nobody works through them
        one run at a time under the impression that the last one will be the last one.
        """
        why: list[str] = []
        why.extend(f"malformed configuration: {p}" for p in self.problems)
        if not self.credentials_present:
            why.append("ProjectX credentials are not configured")
        if not self.target_account_id:
            why.append(f"{ENV_TARGET_ACCOUNT} is not set; the target account is never guessed")
        why.extend(self.flags.blocking())
        if authority is None:
            why.append("no Authority was supplied; execution requires one at EXECUTION_READY")
        elif not authority.permits(Mode.EXECUTION_READY):
            why.append(f"authority is {authority.mode.name}, below EXECUTION_READY")
        return (not why), why

    # -- reporting -------------------------------------------------------------------------

    def report(self, *, authority: Authority | None = None,
               tracked: list[str] | None = None) -> list[str]:
        """The doctor's output, as lines. Contains no secret value by construction.

        There is no code path here that could print one: the object holds booleans, and the
        only strings it holds are the target account id, which is not a secret, and the base
        URL, which is a public endpoint.
        """
        t = secret_files_tracked_by_git() if tracked is None else tracked
        yes_no = {True: "PRESENT", False: "MISSING"}
        lines = [
            "ProjectX credentials",
            f"  {ENV_PROJECTX_USER:<28} {yes_no[self.projectx_username_present]}",
            f"  {ENV_PROJECTX_KEY:<28} {yes_no[self.projectx_api_key_present]}",
            "",
            "Trading target",
            f"  {ENV_TARGET_ACCOUNT:<28} "
            f"{self.target_account_id or 'MISSING (never guessed; you must set it)'}",
            "",
            "Runtime",
            f"  {ENV_PROJECTX_BASE:<28} {self.base_url or 'unset (adapter default applies)'}",
            f"  {'secret file':<28} "
            f"{SECRET_FILE if self.secret_file_exists else str(SECRET_FILE) + '  (absent)'}",
            f"  {'names in secret file':<28} "
            f"{', '.join(self.secret_names_in_file) or 'none'}",
            "",
            "Safety policy  (all four must be permissive, and that is still not sufficient)",
            f"  {ENV_DRY_RUN:<28} {str(self.flags.dry_run).upper()}",
            f"  {ENV_LIVE_TRADING:<28} {str(self.flags.live_trading_enabled).upper()}",
            f"  {ENV_EXECUTION:<28} {str(self.flags.execution_enabled).upper()}",
            f"  {ENV_TRANSMISSION:<28} {str(self.flags.order_transmission_enabled).upper()}",
            "",
            "Git",
            f"  {'SECRET_FILES_TRACKED_BY_GIT':<28} {'YES: ' + ', '.join(t) if t else 'NO'}",
            "",
            f"STATE: {self.state(authority).value}",
        ]
        if self.problems:
            lines += ["", "PROBLEMS"] + [f"  - {p}" for p in self.problems]
        ok, why = self.execution_permitted(authority)
        lines += ["", f"EXECUTION PERMITTED BY CONFIGURATION: {'YES' if ok else 'NO'}"]
        lines += [f"  - {w}" for w in why]
        lines += [
            "",
            "Even a YES above would not transmit an order. ProjectXAdapter.submit has no live",
            "branch to reach, and both runners carry a literal code-level constant. See",
            "docs/CONFIGURATION.md for what each state does and does not permit.",
        ]
        return lines


def transmission_allowed(code_switch: bool, *, authority: Authority | None = None,
                         configuration: Configuration | None = None) -> tuple[bool, list[str]]:
    """The one function an execution path calls. Returns (allowed, every reason it is not).

    Composes the two layers that exist for different reasons and must not collapse into one:

        code_switch     a literal constant in the runner's own source, currently False.
                        Changing it requires a diff, a review and a commit. Configuration
                        cannot reach it.
        configuration   the four environment flags plus credentials plus an explicit target.
                        Changing them requires a shell or a gitignored file, and no commit.
        authority       `mode.Authority` at EXECUTION_READY, which needs a typed argument, a
                        separate environment variable, and a human-written approval file for
                        that exact venue and account.

    The split is the whole design. A constant alone would mean an operator cannot stop a
    running process without a deploy; configuration alone would mean a stray environment
    variable in a scheduled task is sufficient; an approval file alone goes stale. Requiring
    all three means an accident has to happen three times, in three media, in the same
    direction, by three different mechanisms.

    Called with `code_switch=False` this can never return True, whatever the configuration
    says, which is the property `tests/test_config_safety.py` is built around.
    """
    why: list[str] = []
    if not code_switch:
        why.append("the runner's code-level ORDER_TRANSMISSION_ENABLED constant is False; "
                   "configuration cannot override it")
    cfg = configuration if configuration is not None else Configuration.load(export=False)
    ok, reasons = cfg.execution_permitted(authority)
    if not ok:
        why.extend(reasons)
    return (not why), why


def load(**kw) -> Configuration:
    """Convenience wrapper so callers read `config.load()`."""
    return Configuration.load(**kw)
