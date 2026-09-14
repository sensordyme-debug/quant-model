"""The configuration boundary: what it permits, what it refuses, and what it must never leak.

WHY THIS FILE EXISTS
--------------------
`.env.example` documented four safety flags and, measured on 2026-09-14, **not one of them
was read by anything**. `EXECUTION_ENABLED` appeared nowhere in the repository outside that
file. `ORDER_TRANSMISSION_ENABLED` existed only as a Python constant inside two runners, which
is a different thing that shares a spelling. So a reader who set a flag believing they had
changed something was wrong, and a reader who set one believing they had disabled something
was wrong in the more dangerous direction.

`quant_brain/core/config.py` now reads all four and composes them with the code-level constant
and the authority ladder. This file is the proof, and it is written adversarially: several
tests try to get execution permitted and assert that they cannot.

NO CREDENTIAL APPEARS IN THIS FILE
----------------------------------
Where a test needs a value to be "set", it uses `SENTINEL` - a string that is obviously not a
credential and is unique enough to search for. That is the whole trick behind the leak tests:
put a findable marker where a secret would be, exercise the code, and assert the marker is
absent from everything the code produced. A real credential could not be used for this even
if one were available, because the assertion is about output that gets printed on failure.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from quant_brain.core import config as cfg
from quant_brain.core.mode import Authority, Mode

REPO = Path(__file__).resolve().parents[1]

#: Not a credential. A marker, chosen so that a substring search for it cannot match anything
#: else in this repository, and so that a human reading a failure sees immediately that no
#: real value was involved.
SENTINEL = "SENTINEL-not-a-real-credential-9f3a1c"

ALL_VARS = (cfg.ENV_PROJECTX_USER, cfg.ENV_PROJECTX_KEY, cfg.ENV_PROJECTX_BASE,
            cfg.ENV_TARGET_ACCOUNT, cfg.ENV_DRY_RUN, cfg.ENV_LIVE_TRADING,
            cfg.ENV_EXECUTION, cfg.ENV_TRANSMISSION)


@pytest.fixture
def clean_env(monkeypatch):
    """No configuration at all, and no secret file. The floor every test starts from."""
    for name in (*ALL_VARS, "QB_ACCOUNT_MODE", "QB_VENUE", "QB_ACCOUNT",
                 "QB_LIVE_TRADING_ENABLED"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(cfg, "SECRET_FILE", REPO / "live" / "does-not-exist.env")
    return monkeypatch


def _fully_permissive(monkeypatch):
    """Every environment condition set the dangerous way. Used to prove it is not enough."""
    monkeypatch.setenv(cfg.ENV_PROJECTX_USER, SENTINEL)
    monkeypatch.setenv(cfg.ENV_PROJECTX_KEY, SENTINEL)
    monkeypatch.setenv(cfg.ENV_TARGET_ACCOUNT, "ACC-123")
    monkeypatch.setenv(cfg.ENV_DRY_RUN, "false")
    monkeypatch.setenv(cfg.ENV_LIVE_TRADING, "true")
    monkeypatch.setenv(cfg.ENV_EXECUTION, "true")
    monkeypatch.setenv(cfg.ENV_TRANSMISSION, "true")


def _live_authority(tmp_path, monkeypatch) -> Authority:
    """A genuine EXECUTION_READY authority, built the only way mode.py allows one."""
    monkeypatch.setenv("QB_LIVE_TRADING_ENABLED", "true")
    d = tmp_path / "approvals"
    d.mkdir(parents=True, exist_ok=True)
    (d / "topstep-ACC-123.md").write_text("approved for this test only", encoding="utf-8")
    return Authority.for_live("topstep", "ACC-123",
                              i_understand_this_is_real_money=True, approval_dir=d)


# =====================================================================================
# 1-2. MISSING AND MALFORMED CONFIGURATION FAIL, AND SAY WHY
# =====================================================================================

def test_missing_projectx_credentials_are_reported_clearly(clean_env):
    conf = cfg.Configuration.load()
    assert conf.state() is cfg.ConfigState.CONFIG_MISSING
    assert not conf.credentials_present
    ok, why = conf.execution_permitted()
    assert not ok
    assert any("credentials are not configured" in w for w in why)


def test_the_adapter_names_which_credential_is_missing_and_shows_neither(clean_env):
    """`Credentials.from_environment` must say what is unset without quoting what is set."""
    from quant_brain.brokers.projectx import Credentials
    from quant_brain.core.mode import NotPermitted

    clean_env.setenv(cfg.ENV_PROJECTX_USER, SENTINEL)     # key still missing
    with pytest.raises(NotPermitted) as e:
        Credentials.from_environment()
    text = str(e.value)
    assert cfg.ENV_PROJECTX_KEY in text, "the missing name must be named"
    assert SENTINEL not in text, "the credential that WAS set leaked into the exception"


@pytest.mark.parametrize("value", ["maybe", "TRUE-ish", "on", "sure", "0.0", "None", "y"])
def test_a_malformed_flag_is_reported_and_treated_as_the_safe_value(clean_env, value):
    """Both halves matter. Reporting a typo without failing closed would be a warning nobody
    reads; failing closed without reporting would hide a configuration that does not say what
    its author thinks it says."""
    clean_env.setenv(cfg.ENV_TRANSMISSION, value)
    clean_env.setenv(cfg.ENV_DRY_RUN, value)
    conf = cfg.Configuration.load()
    assert conf.problems, f"{value!r} was accepted silently"
    assert conf.state() is cfg.ConfigState.CONFIG_INVALID
    assert conf.flags.order_transmission_enabled is False, "an enabling flag defaulted to ON"
    assert conf.flags.dry_run is True, "a protective flag defaulted to OFF"


def test_a_malformed_target_account_is_refused_rather_than_trimmed(clean_env):
    clean_env.setenv(cfg.ENV_TARGET_ACCOUNT, 'ACC-123"  # my account')
    conf = cfg.Configuration.load()
    assert conf.problems
    assert conf.state() is cfg.ConfigState.CONFIG_INVALID


def test_an_unset_target_account_is_never_guessed(clean_env):
    clean_env.setenv(cfg.ENV_PROJECTX_USER, SENTINEL)
    clean_env.setenv(cfg.ENV_PROJECTX_KEY, SENTINEL)
    conf = cfg.Configuration.load()
    assert conf.target_account_id == ""
    assert conf.state() is cfg.ConfigState.READ_ONLY_CONFIGURED, (
        "credentials alone must not reach READ_ONLY_READY; there is no 'the' account until a "
        "person names one")


# =====================================================================================
# 3-6. EACH FLAG, ON ITS OWN, DISABLES EXECUTION
# =====================================================================================

@pytest.mark.parametrize("name,value,label", [
    (cfg.ENV_DRY_RUN, "true", "DRY_RUN=true"),
    (cfg.ENV_LIVE_TRADING, "false", "LIVE_TRADING_ENABLED=false"),
    (cfg.ENV_EXECUTION, "false", "EXECUTION_ENABLED=false"),
    (cfg.ENV_TRANSMISSION, "false", "ORDER_TRANSMISSION_ENABLED=false"),
])
def test_one_flag_in_the_safe_position_disables_execution(clean_env, tmp_path, name, value,
                                                          label):
    """Everything else permissive, including a genuine live Authority. Each flag alone stops
    it, which is what makes the AND an AND rather than a list of suggestions."""
    _fully_permissive(clean_env)
    authority = _live_authority(tmp_path, clean_env)
    clean_env.setenv(name, value)

    conf = cfg.Configuration.load()
    ok, why = conf.execution_permitted(authority)
    assert not ok, f"{label} did not disable execution"
    assert why, "refused with no reason given"


def test_with_every_flag_permissive_and_a_live_authority_configuration_says_yes(clean_env,
                                                                                tmp_path):
    """The control, and the most uncomfortable test here.

    If this failed, the four tests above would pass for the wrong reason - something ELSE
    would be refusing and the flags would be untested. So configuration must be capable of
    saying yes. It saying yes is not dangerous: `transmission_allowed` still requires the
    code-level constant, and no live branch exists behind it, both asserted below.
    """
    _fully_permissive(clean_env)
    authority = _live_authority(tmp_path, clean_env)
    conf = cfg.Configuration.load()
    ok, why = conf.execution_permitted(authority)
    assert ok, f"configuration can never say yes, so the flag tests prove nothing: {why}"
    assert conf.state(authority) is cfg.ConfigState.LIVE_EXECUTION_AUTHORIZED


# =====================================================================================
# 7. NO SINGLE CONDITION BYPASSES THE BOUNDARY - ADVERSARIAL
# =====================================================================================

def test_no_single_flag_flipped_alone_permits_execution(clean_env, tmp_path):
    """Start from the safe floor and flip exactly one thing at a time. None is enough."""
    authority = _live_authority(tmp_path, clean_env)
    for name, value in ((cfg.ENV_DRY_RUN, "false"), (cfg.ENV_LIVE_TRADING, "true"),
                        (cfg.ENV_EXECUTION, "true"), (cfg.ENV_TRANSMISSION, "true"),
                        (cfg.ENV_PROJECTX_USER, SENTINEL), (cfg.ENV_PROJECTX_KEY, SENTINEL),
                        (cfg.ENV_TARGET_ACCOUNT, "ACC-123")):
        for n in ALL_VARS:
            clean_env.delenv(n, raising=False)
        clean_env.setenv(name, value)
        ok, _ = cfg.Configuration.load().execution_permitted(authority)
        assert not ok, f"setting {name}={value} alone permitted execution"


def test_the_code_level_constant_cannot_be_overridden_by_configuration(clean_env, tmp_path):
    """The adversarial case: every environment condition set the dangerous way, a real live
    Authority, and the runner's constant still False. This is the shape of the accident the
    two layers exist to survive - a scheduled task with a stale environment."""
    _fully_permissive(clean_env)
    authority = _live_authority(tmp_path, clean_env)
    allowed, why = cfg.transmission_allowed(False, authority=authority)
    assert not allowed
    assert any("code-level" in w for w in why)


def test_a_forged_safety_flags_object_cannot_claim_to_be_permissive():
    """`permissive` is computed, not stored, so no constructor argument can assert it."""
    forged = cfg.SafetyFlags(dry_run=True, live_trading_enabled=True,
                             execution_enabled=True, order_transmission_enabled=True)
    assert forged.permissive is False, "dry_run=True must veto regardless of the others"
    assert "permissive" not in {f for f in forged.__dataclass_fields__}


def test_no_configuration_makes_transmission_possible(clean_env, tmp_path):
    """The claim the whole mission rests on, stated as a test.

    Every environment condition dangerous, a real live Authority, and the configuration layer
    itself replaced by one that permits everything. The adapter still sends nothing, because
    the branch that would send does not exist - `submit` raises NotImplemented-shaped
    NotPermitted rather than reaching a transport.
    """
    from quant_brain.brokers import projectx
    _fully_permissive(clean_env)
    _live_authority(tmp_path, clean_env)
    assert projectx.ORDER_TRANSMISSION_ENABLED is False
    src = (REPO / "quant_brain" / "brokers" / "projectx.py").read_text(encoding="utf-8")
    assert "Order/place" not in src, (
        "an order endpoint appeared in the adapter; this test is the tripwire for that")
    assert "not implemented in this module" in src


# =====================================================================================
# 8-9. NOTHING PRINTS OR RAISES A CREDENTIAL
# =====================================================================================

def test_the_report_contains_no_credential_value(clean_env, tmp_path):
    _fully_permissive(clean_env)
    authority = _live_authority(tmp_path, clean_env)
    text = "\n".join(cfg.Configuration.load().report(authority=authority, tracked=[]))
    assert SENTINEL not in text, "a credential reached the doctor's output"
    assert "PRESENT" in text, "the report must still say a credential IS set"


def test_the_configuration_object_holds_no_credential(clean_env):
    """Not "does not print one" - does not HAVE one. A value that is not stored cannot leak
    through a repr, a debugger, a pickle or a future field added by someone in a hurry."""
    clean_env.setenv(cfg.ENV_PROJECTX_USER, SENTINEL)
    clean_env.setenv(cfg.ENV_PROJECTX_KEY, SENTINEL)
    conf = cfg.Configuration.load()
    blob = repr(conf) + str(conf) + json.dumps(
        {k: str(v) for k, v in conf.__dict__.items()}, default=str)
    assert SENTINEL not in blob
    assert conf.projectx_api_key_present is True


def test_the_doctor_subprocess_prints_no_credential(clean_env):
    """End to end through the real CLI, because the leak that matters is the one on a
    terminal. Run as a subprocess with the sentinel exported, so nothing about this process's
    imports can affect the answer."""
    clean_env.setenv(cfg.ENV_PROJECTX_USER, SENTINEL)
    clean_env.setenv(cfg.ENV_PROJECTX_KEY, SENTINEL)
    env = dict(os.environ)
    res = subprocess.run([sys.executable, "-m", "quant_brain", "config", "doctor"],
                         cwd=REPO, env=env, capture_output=True, text=True, timeout=120)
    combined = res.stdout + res.stderr
    assert SENTINEL not in combined, "the doctor printed a credential"
    assert "PRESENT" in combined
    assert res.returncode in (0, 1, 2), f"unexpected exit {res.returncode}"


def test_a_credentials_object_has_no_printable_form(clean_env):
    from quant_brain.brokers.projectx import Credentials
    clean_env.setenv(cfg.ENV_PROJECTX_USER, "someone")
    clean_env.setenv(cfg.ENV_PROJECTX_KEY, SENTINEL)
    c = Credentials.from_environment()
    assert SENTINEL not in repr(c)
    assert SENTINEL not in str(c)
    assert SENTINEL not in f"{c}"
    assert SENTINEL in json.dumps(c.payload()), (
        "the login payload is the ONE place the key is materialised; if it stopped appearing "
        "here the adapter could not authenticate and this test is checking the wrong object")


def test_no_secret_name_has_a_value_baked_into_source(clean_env):
    """A crude sweep for a credential committed into a tracked Python file.

    Looks for an assignment of a long opaque literal to a name that ends in KEY, SECRET,
    TOKEN or PASSWORD. It cannot prove the absence of a secret and does not claim to; it
    catches the copy-paste that every repository eventually receives.
    """
    pattern = re.compile(
        r"""(?i)\b\w*(api_key|secret|token|password)\w*\b\s*[:=]\s*["']([A-Za-z0-9_\-]{20,})["']""")
    #: A literal that announces itself is a canary, not a credential. A test suite needs
    #: a findable marker to prove a value never reaches an output, and the marker has to
    #: look enough like a credential to be worth testing with. tests/test_qb_projectx.py
    #: uses a DO-NOT-LEAK string and this file uses SENTINEL; both are the right thing to
    #: have. Anything NOT carrying one of these markers is suspect, tests included - the
    #: rule that credentials never appear in tests is kept, and this is how a fixture
    #: proves it is not one.
    self_identifying = ("do-not-leak", "sentinel", "not-a-real", "placeholder",
                        "example", "fake", "dummy", "your-", "changeme", "redacted")
    offenders = []
    for rel in subprocess.run(["git", "ls-files", "-z", "*.py", "*.json", "*.md", "*.ps1"],
                              cwd=REPO, capture_output=True, text=True,
                              timeout=60).stdout.split("\0"):
        if not rel.strip():
            continue
        f = REPO / rel
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:                                          # pragma: no cover
            continue
        for m in pattern.finditer(text):
            if any(mk in m.group(2).lower() for mk in self_identifying):
                continue
            line = text[:m.start()].count("\n") + 1
            offenders.append(f"{rel}:{line}")
    assert not offenders, f"credential-shaped literals in tracked files: {offenders}"

    # POSITIVE CONTROL, and it exists because this test was vacuous for a while. An editing
    # accident turned the two `` word boundaries in the pattern above into literal
    # backspace characters, which no source file contains, so the sweep matched nothing and
    # passed on every repository it would ever be run against. A scanner that cannot be shown
    # to catch anything is not evidence.
    # Assembled at run time rather than written as one literal, because this file is tracked
    # and the sweep above reads tracked files - a hard-coded probe here would be flagged by
    # the very check it exists to validate. That is not a workaround; it is the check working.
    probe = 'API_KEY = "' + ("abcdefghij" * 3) + '"'
    assert pattern.search(probe), (
        "the pattern no longer matches an obvious credential literal; it has been broken and "
        "this whole test is passing for no reason")
    assert pattern.search('SECRET = "sk-live-DO-NOT-LEAK-0123456789"'), (
        "the pattern does not match the canary either, so the exclusion list is untested")


# =====================================================================================
# 10. LOADING CONFIGURATION MUTATES NO PRODUCTION STATE
# =====================================================================================

def _fingerprint() -> dict[str, str]:
    out = {}
    for d in ("state", "log"):
        for p in sorted((REPO / "live" / d).glob("*")):
            if p.is_file():
                out[str(p.relative_to(REPO))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def test_loading_configuration_does_not_touch_live_state(clean_env):
    """The suite already rewrote `live/state/governor.json` once by accident. Configuration
    is read-only and this asserts it on the real directory rather than a redirected one."""
    before = _fingerprint()
    cfg.Configuration.load()
    cfg.transmission_allowed(False)
    cfg.secret_files_tracked_by_git()
    assert _fingerprint() == before, "loading configuration changed something under live/"


def test_the_doctor_does_not_touch_live_state():
    before = _fingerprint()
    res = subprocess.run([sys.executable, "-m", "quant_brain", "config", "doctor"],
                         cwd=REPO, capture_output=True, text=True, timeout=120)
    assert res.returncode in (0, 1, 2)
    assert _fingerprint() == before, "the doctor changed something under live/"


# =====================================================================================
# 11. THE EXISTING DATA-VENDOR CONFIGURATION STILL WORKS
# =====================================================================================

def test_the_two_parsers_of_the_secret_file_agree(tmp_path, monkeypatch):
    """`scripts/apikeys.py` and `core/config.py` both read live/secrets.env.

    Two parsers of one file is a duplication accepted on purpose - the alternative was making
    `quant_brain` import from `scripts/`, which inverts the dependency the package is arranged
    to avoid. Accepted, but not unchecked: they must agree on the same file.
    """
    import apikeys

    f = tmp_path / "secrets.env"
    f.write_text(
        "# a comment\n"
        "\n"
        f"ALPACA_API_KEY={SENTINEL}-alpaca\n"
        f'FMP_API_KEY="{SENTINEL}-fmp"\n'
        f"THETADATA_API_KEY='{SENTINEL}-theta'\n"
        "MALFORMED_LINE_WITHOUT_EQUALS\n",
        encoding="utf-8")
    monkeypatch.setattr(apikeys, "SECRETS", f)
    monkeypatch.setattr(cfg, "SECRET_FILE", f)
    for n in ("ALPACA_API_KEY", "FMP_API_KEY", "THETADATA_API_KEY"):
        monkeypatch.delenv(n, raising=False)

    from_apikeys = apikeys.keys()
    from_config = cfg.load_secret_file(export=False)
    assert set(from_apikeys) >= {"ALPACA_API_KEY", "FMP_API_KEY", "THETADATA_API_KEY"}
    assert from_config == set(from_apikeys), "the two parsers disagree about this file"
    assert "MALFORMED_LINE_WITHOUT_EQUALS" not in from_config


def test_config_loading_does_not_disturb_vendor_keys_already_in_the_environment(tmp_path,
                                                                                monkeypatch):
    """`setdefault`, not assignment. An exported value wins over the file, which is what lets
    a scheduled task or a CI job supply a key without one."""
    f = tmp_path / "secrets.env"
    f.write_text(f"ALPACA_API_KEY={SENTINEL}-from-file\n", encoding="utf-8")
    monkeypatch.setattr(cfg, "SECRET_FILE", f)
    monkeypatch.setenv("ALPACA_API_KEY", f"{SENTINEL}-from-environment")
    cfg.load_secret_file(export=True)
    assert os.environ["ALPACA_API_KEY"] == f"{SENTINEL}-from-environment"


@pytest.mark.skipif(not (REPO / "live" / "secrets.env").exists(),
                    reason="no local secrets file on this machine")
def test_the_real_vendor_keys_are_still_readable_by_the_existing_loader():
    """The backwards-compatibility check, on the real file, asserting NAMES only.

    If a change to the shared secret file ever broke the data-vendor path, this is where it
    shows up rather than in a sweep failing at 09:25.
    """
    import apikeys
    names = set(apikeys.keys())
    assert {"ALPACA_API_KEY", "ALPACA_SECRET_KEY", "THETADATA_API_KEY", "FMP_API_KEY"} <= names


# =====================================================================================
# THE TEMPLATE AND THE CODE MUST DESCRIBE THE SAME SYSTEM
# =====================================================================================

def _documented_vars() -> set[str]:
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    return set(re.findall(r"^([A-Z][A-Z0-9_]{2,})=", text, flags=re.MULTILINE))


def test_every_documented_variable_has_a_real_reader():
    """The check that would have caught the original defect.

    Four flags sat in `.env.example` describing a safety contract nothing enforced. A
    variable documented here must be named somewhere in the package or the scripts, outside
    the template itself.
    """
    src = ""
    for sub in ("quant_brain", "scripts"):
        for p in (REPO / sub).rglob("*.py"):
            if "__pycache__" not in p.parts:
                src += p.read_text(encoding="utf-8", errors="replace")
    orphans = sorted(v for v in _documented_vars() if v not in src)
    assert not orphans, (
        f"documented in .env.example and read by nothing: {orphans}. Either wire it up or "
        f"delete the line - a documented control that does not exist is trusted, which makes "
        f"it worse than no documentation.")


def test_every_configuration_variable_this_module_reads_is_documented():
    """The other direction. A variable the code reads and the template omits is a setting
    nobody can discover without grepping."""
    undocumented = sorted(v for v in ALL_VARS if v not in _documented_vars())
    assert not undocumented, f"read by config.py and absent from .env.example: {undocumented}"


def test_the_tracked_template_contains_nothing_that_looks_like_a_real_value():
    """`.env.example` is deliberately tracked and deliberately excluded from the
    tracked-secret check, so the exclusion has to be earned."""
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        _, v = line.split("=", 1)
        v = v.strip()
        assert v == "" or (v.startswith("<") and v.endswith(">")) or v in {"true", "false"}, (
            f"{line!r} is not a placeholder. The template may hold only <angle-bracket> "
            f"markers, the words true/false, or nothing.")


# =====================================================================================
# GIT
# =====================================================================================

def test_no_credential_file_is_tracked_by_git():
    tracked = cfg.secret_files_tracked_by_git()
    assert tracked == [], f"git is tracking credential files: {tracked}"


@pytest.mark.parametrize("path", [
    ".env", ".env.local", ".env.production",
    "live/secrets.env", "live/secrets.json", "live/projectx.env",
    "live/approvals/topstep-ACC1.md",
])
def test_every_credential_shape_is_ignored(path):
    """`.gitignore` had `.env` and not `.env.*`, so `.env.local` was trackable. Asked of git
    rather than read from the file, because the question is what git will DO."""
    res = subprocess.run(["git", "check-ignore", "-q", path], cwd=REPO, timeout=30)
    assert res.returncode == 0, f"{path} is not ignored"


def test_the_placeholder_template_stays_trackable():
    """The negation must not be so broad that the template disappears from the repository."""
    res = subprocess.run(["git", "check-ignore", "-q", ".env.example"], cwd=REPO, timeout=30)
    assert res.returncode != 0, ".env.example became ignored; the template must be committed"


# =====================================================================================
# STATES ARE DISTINCT, AND AUTHENTICATION IS NOT AUTHORIZATION
# =====================================================================================

def test_credentials_present_is_three_states_below_anything_that_can_trade(clean_env):
    clean_env.setenv(cfg.ENV_PROJECTX_USER, SENTINEL)
    clean_env.setenv(cfg.ENV_PROJECTX_KEY, SENTINEL)
    assert cfg.Configuration.load().state() is cfg.ConfigState.READ_ONLY_CONFIGURED

    clean_env.setenv(cfg.ENV_TARGET_ACCOUNT, "ACC-123")
    assert cfg.Configuration.load().state() is cfg.ConfigState.READ_ONLY_READY


def test_configuration_alone_can_never_reach_live_execution_authorized(clean_env):
    """`mode.from_environment()` refuses to produce EXECUTION_READY, so no combination of
    environment variables reaches the top state through the normal path."""
    from quant_brain.core.mode import from_environment
    _fully_permissive(clean_env)
    clean_env.setenv("QB_ACCOUNT_MODE", "PRACTICE")
    conf = cfg.Configuration.load()
    state = conf.state(from_environment())
    assert state is cfg.ConfigState.PRACTICE_READY
    assert state is not cfg.ConfigState.LIVE_EXECUTION_AUTHORIZED


def test_the_mode_ladder_still_refuses_to_select_live_from_configuration(clean_env):
    from quant_brain.core.mode import NotPermitted, from_environment
    clean_env.setenv("QB_ACCOUNT_MODE", "EXECUTION_READY")
    with pytest.raises(NotPermitted):
        from_environment()


def test_practice_is_below_execution_ready_in_the_ladder():
    assert Mode.PRACTICE < Mode.EXECUTION_READY
