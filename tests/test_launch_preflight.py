"""E-5: the launcher's unit-suite preflight gate.

`intraday_launch.unit_tests_ok` decides whether the 09:25 ET scheduled task is allowed to start
the live paper trader. It is the only piece of the platform that can *stop the sleeve trading*,
so its failure mapping is the thing under test here, not its happy path:

    a real test failure (pytest exit 1)   -> refuse, no trading
    anything else                        -> trade, with a warning

That asymmetry exists because a missing dev dependency, an empty tests directory or a hung
collection says nothing about whether the book arithmetic is correct, and an outage caused by
the safety check would be worse than the risk it was added to cover. Every "anything else"
branch below is therefore a test that the sleeve *still trades*.

Each case builds a throwaway repo in tmp_path with its own pytest.ini and points the gate at it,
so nothing here depends on - or re-runs - the real suite except `test_the_real_suite_passes`.
"""
from __future__ import annotations

import subprocess

import intraday_launch
import pytest


def make_repo(root, body: str, name: str = "test_sample.py"):
    """A minimal pytest project at `root` containing one test file."""
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n", encoding="utf-8")
    (root / "tests" / name).write_text(body, encoding="utf-8")
    return root


# --- the refusal, which is the only way this gate can stop trading -----------------------

def test_a_failing_test_refuses_to_trade(tmp_path):
    make_repo(tmp_path, "def test_boom():\n    assert 1 == 2\n")
    ok, outcome, detail = intraday_launch.unit_tests_ok(root=tmp_path)
    assert ok is False
    assert outcome == "failed"
    assert "test_boom" in detail          # the detail must name the test, it goes to the alert


@pytest.mark.parametrize("code, expected", [
    (0, (True, "passed")),
    (1, (False, "failed")),      # the only refusal
    (2, (True, "warn")),         # interrupted / collection error
    (3, (True, "warn")),         # internal error
    (4, (True, "warn")),         # usage error
    (5, (True, "warn")),         # nothing collected
    (9, (True, "warn")),         # unknown future code: must still let the sleeve trade
])
def test_the_exit_code_mapping_is_total(tmp_path, monkeypatch, code, expected):
    """The mapping, exhaustively and cheaply. The real-pytest tests below prove which codes
    pytest actually emits; this proves no code can fall through to an unintended refusal."""
    make_repo(tmp_path, "def test_ok():\n    assert True\n")
    monkeypatch.setattr(
        intraday_launch.subprocess, "run",
        lambda cmd, *a, **k: subprocess.CompletedProcess(cmd, code, "summary line", ""))
    ok, outcome, _ = intraday_launch.unit_tests_ok(root=tmp_path)
    assert (ok, outcome) == expected


# --- everything else must let the sleeve trade -------------------------------------------

def test_a_passing_suite_trades(tmp_path):
    make_repo(tmp_path, "def test_ok():\n    assert True\n")
    ok, outcome, detail = intraday_launch.unit_tests_ok(root=tmp_path)
    assert (ok, outcome) == (True, "passed")
    assert "1 passed" in detail


def test_pytest_not_importable_trades_with_a_warning(tmp_path):
    """The E-5 requirement: a missing dev dependency can never stop the sleeve."""
    make_repo(tmp_path, "def test_ok():\n    assert True\n")
    missing = tmp_path / "no-such-python.exe"       # probe raises OSError, not a return code
    ok, outcome, detail = intraday_launch.unit_tests_ok(root=tmp_path, python=str(missing))
    assert ok is True
    assert outcome == "skipped"
    assert "probe" in detail or "not importable" in detail


def test_probe_failure_is_detected_without_running_the_suite(tmp_path, monkeypatch):
    """If the probe says pytest is absent, the gate must not then run `-m pytest` anyway -
    that call would exit 1 (module not found) and be misread as a failing suite."""
    make_repo(tmp_path, "def test_boom():\n    assert False\n")
    calls = []
    real = subprocess.run

    def spy(cmd, *a, **k):
        calls.append(list(cmd))
        if "-c" in cmd:                              # the probe: pretend pytest is missing
            return subprocess.CompletedProcess(cmd, 1, "", "No module named pytest")
        return real(cmd, *a, **k)

    monkeypatch.setattr(intraday_launch.subprocess, "run", spy)
    # a python that is not this interpreter, so the probe is actually performed
    ok, outcome, _ = intraday_launch.unit_tests_ok(root=tmp_path, python="other-python")
    assert (ok, outcome) == (True, "skipped")
    assert len(calls) == 1, "the suite must not be run after the probe fails"


def test_no_tests_directory_trades(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    ok, outcome, _ = intraday_launch.unit_tests_ok(root=tmp_path)
    assert (ok, outcome) == (True, "skipped")


def test_nothing_collected_trades(tmp_path):
    """Exit 5. An empty suite is not evidence of a broken book."""
    make_repo(tmp_path, "# no tests here\n")
    ok, outcome, detail = intraday_launch.unit_tests_ok(root=tmp_path)
    assert ok is True
    assert outcome == "warn"
    assert "exit 5" in detail


def test_a_collection_error_trades(tmp_path):
    """Exit 2. A test file that will not even import is a broken *test*, and the replay
    preflight is the check that guards the strategy path."""
    make_repo(tmp_path, "def test_x(:\n    pass\n")     # syntax error
    ok, outcome, detail = intraday_launch.unit_tests_ok(root=tmp_path)
    assert ok is True
    assert outcome == "warn"
    assert "exit 2" in detail


def test_a_hung_suite_trades(tmp_path):
    make_repo(tmp_path, "import time\n\ndef test_slow():\n    time.sleep(60)\n")
    ok, outcome, detail = intraday_launch.unit_tests_ok(root=tmp_path, timeout=1)
    assert ok is True
    assert outcome == "warn"
    assert "exceeded" in detail


def test_the_gate_never_raises(tmp_path, monkeypatch):
    """Whatever subprocess does, the launcher must get a verdict rather than a traceback:
    an exception here would crash the launcher before the replay and HALT gates ran."""
    make_repo(tmp_path, "def test_ok():\n    assert True\n")

    def explode(cmd, *a, **k):
        if "-c" in cmd:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        raise OSError("no fork for you")

    monkeypatch.setattr(intraday_launch.subprocess, "run", explode)
    ok, outcome, _ = intraday_launch.unit_tests_ok(root=tmp_path)
    assert (ok, outcome) == (True, "warn")


# --- E-8: which failure counts. Only the live trading path may stop the sleeve -----------

def make_marked_repo(root, *, runner_body: str, other_body: str):
    """A repo shaped like this one: a `runner`-marked file and an unmarked one.

    The real suite applies the marker from `tests/conftest.py` by module name; here a
    `pytestmark` line is equivalent and keeps the fixture readable.
    """
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "pytest.ini").write_text(
        "[pytest]\ntestpaths = tests\nmarkers =\n    runner: live trading path\n",
        encoding="utf-8")
    (root / "tests" / "test_runner_path.py").write_text(
        "import pytest\n\npytestmark = pytest.mark.runner\n\n" + runner_body, encoding="utf-8")
    (root / "tests" / "test_research_path.py").write_text(other_body, encoding="utf-8")
    return root


def test_a_failure_outside_the_trading_path_trades_with_a_warning(tmp_path):
    """The E-8 case: worker allocation reading live free memory, or a store validator reading
    a store whose overnight fetch died. Neither says the book arithmetic is wrong, and both
    would have cost the sleeve a full day of paper trading under E-5's mapping."""
    make_marked_repo(tmp_path,
                     runner_body="def test_sizing():\n    assert True\n",
                     other_body="def test_free_memory():\n    assert 1 == 2\n")
    ok, outcome, detail = intraday_launch.unit_tests_ok(root=tmp_path)
    assert ok is True
    assert outcome == "warn"
    assert "outside the live trading path" in detail
    assert "test_free_memory" in detail        # the warning still names what broke


def test_a_failure_on_the_trading_path_still_refuses(tmp_path):
    """The narrowing must not weaken the refusal it was carved out of."""
    make_marked_repo(tmp_path,
                     runner_body="def test_sizing():\n    assert 1 == 2\n",
                     other_body="def test_research():\n    assert True\n")
    ok, outcome, detail = intraday_launch.unit_tests_ok(root=tmp_path)
    assert (ok, outcome) == (False, "failed")
    assert "test_sizing" in detail


def test_both_failing_refuses(tmp_path):
    make_marked_repo(tmp_path,
                     runner_body="def test_sizing():\n    assert 1 == 2\n",
                     other_body="def test_research():\n    assert 1 == 2\n")
    ok, outcome, _ = intraday_launch.unit_tests_ok(root=tmp_path)
    assert (ok, outcome) == (False, "failed")


def test_an_unmarked_repo_refuses_exactly_as_before(tmp_path):
    """No `runner` marker anywhere -> the subset collects nothing -> the answer is unreadable
    -> keep E-5's refusal. The narrowing may only downgrade a failure it can *prove* is off
    the trading path; it must never turn a missing marker into permission to trade."""
    make_repo(tmp_path, "def test_boom():\n    assert 1 == 2\n")
    ok, outcome, _ = intraday_launch.unit_tests_ok(root=tmp_path)
    assert (ok, outcome) == (False, "failed")


def test_the_subset_rerun_only_happens_on_a_failure(tmp_path):
    """A green morning must still cost exactly one pytest launch."""
    make_marked_repo(tmp_path,
                     runner_body="def test_sizing():\n    assert True\n",
                     other_body="def test_research():\n    assert True\n")
    calls = []
    real = intraday_launch.subprocess.run

    def counting(cmd, *a, **k):
        calls.append(cmd)
        return real(cmd, *a, **k)

    intraday_launch.subprocess.run = counting
    try:
        ok, outcome, _ = intraday_launch.unit_tests_ok(root=tmp_path)
    finally:
        intraday_launch.subprocess.run = real
    assert (ok, outcome) == (True, "passed")
    assert not any("-m" in c and "runner" in c for c in calls if isinstance(c, list))


def test_every_runner_importer_is_classified():
    """A new test file that imports the trader is a decision, never an accident.

    If it lands in neither set, this fails and whoever added it has to say whether a failure
    in it should be allowed to stop the live sleeve.
    """
    import conftest

    runner_modules = ("intraday_trader", "paper_trade", "intraday_launch", "reconcile_state")
    tests_dir = intraday_launch.REPO / "tests"
    classified = conftest.RUNNER_TESTS | conftest.NON_GATING_RUNNER_IMPORTERS
    unclassified = []
    for path in sorted(tests_dir.glob("test_*.py")):
        src = path.read_text(encoding="utf-8")
        if any(f"import {m}" in src for m in runner_modules) and path.stem not in classified:
            unclassified.append(path.name)
    assert not unclassified, (
        f"{unclassified} import a live runner but are in neither conftest.RUNNER_TESTS nor "
        "conftest.NON_GATING_RUNNER_IMPORTERS - decide whether they may stop the sleeve")


def test_the_gating_set_names_only_files_that_exist():
    """A renamed test file must not silently drop out of the gate."""
    import conftest

    tests_dir = intraday_launch.REPO / "tests"
    for name in conftest.RUNNER_TESTS | conftest.NON_GATING_RUNNER_IMPORTERS:
        assert (tests_dir / f"{name}.py").exists(), f"{name} is listed but has no file"


def test_the_real_suite_marks_the_trading_path():
    """The marker actually reaches items in this repo - a typo in the module names would
    otherwise leave the gate with an empty subset, which refuses on every failure."""
    import conftest

    assert "test_intraday_sizing" in conftest.RUNNER_TESTS
    res = subprocess.run(
        [intraday_launch.PY, "-m", "pytest", "-m", "runner", "--collect-only", "-q",
         "-p", "no:cacheprovider"],
        cwd=str(intraday_launch.REPO), capture_output=True, text=True, timeout=300)
    assert res.returncode == 0, res.stdout[-800:] + res.stderr[-400:]
    assert "no tests ran" not in res.stdout


# --- the gate is wired into the launcher, and only where it belongs ----------------------

def test_the_refusal_code_is_distinct_from_the_other_preflight_codes():
    """The task's exit code is how the owner tells these apart in the scheduler history:
    2 = replay/data, 3 = HALT, 4 = unit suite. Keep them distinct."""
    src = (intraday_launch.REPO / "scripts" / "intraday_launch.py").read_text(encoding="utf-8")
    assert "return 4" in src
    assert src.index("preflight_tests") < src.index("# 2) replay preflight"), \
        "the unit suite must run before the replay, so a broken constant is caught in 0.5 s"


def test_the_gate_can_be_skipped_but_is_on_by_default():
    src = (intraday_launch.REPO / "scripts" / "intraday_launch.py").read_text(encoding="utf-8")
    assert '"--skip-tests", action="store_true"' in src
    assert "if not args.skip_tests:" in src


def test_no_test_here_calls_the_gate_on_this_repo():
    """Guard rail for whoever extends this file. `unit_tests_ok()` with its default root runs
    `pytest -q` on THIS repo, which would re-enter this suite and recurse until the machine
    gives up. Point the gate at a tmp_path repo, always. The real-repo path is verified by
    running `python scripts/intraday_launch.py --preflight-only` by hand instead."""
    import ast
    path = intraday_launch.REPO / "tests" / "test_launch_preflight.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bare = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and getattr(node.func, "attr", getattr(node.func, "id", None)) == "unit_tests_ok"
        and not node.args and not node.keywords
    ]
    assert bare == [], f"lines {bare}: pass root=tmp_path, never the no-argument default"
