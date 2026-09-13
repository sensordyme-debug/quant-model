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

import datetime as dt
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


# --- E-9: the store report. Runs every morning, and may never stop the sleeve -------------
#
# E-6 gave `last_session()` a shape test so the preflight would stop replaying half-days. That
# fix made the failure it guards against silent: the launcher walks back to the newest session
# that spans the bell and prints "replay OK" whether that session is yesterday's or last
# month's. `store_warnings` is the scheduled consumer the checker never had - and because a
# short store is a *data* finding, not wrong book arithmetic, every test below asserts that
# the launcher keeps going.

def _calendar():
    from quant_brain.markets.equity_us import CALENDAR
    return CALENDAR


@pytest.mark.parametrize("day, today, lag", [
    ("2026-09-11", "2026-09-14", 0),   # normal Monday: Friday's session, nothing in between
    ("2026-09-11", "2026-09-15", 1),   # one overnight fetch skipped
    ("2026-09-08", "2026-09-12", 3),   # the dead-fetcher case: 09, 10, 11 all unusable
    ("2026-09-11", "2026-09-11", 0),   # same day - a re-run, not a lag
    ("2026-09-04", "2026-09-08", 0),   # Labor Day 2026-09-07 is not a session and must not count
])
def test_replay_lag_counts_closed_sessions_not_days(day, today, lag):
    """Pinned dates against the real calendar: the count is a property of the trading calendar,
    never of wall-clock days, or a long weekend would raise an alert every Tuesday."""
    assert intraday_launch.replay_lag(
        dt.date.fromisoformat(day), dt.date.fromisoformat(today), _calendar()) == lag


def test_a_stale_replay_day_warns_but_lets_the_sleeve_trade(tmp_path):
    """The case E-6 made invisible. No store is needed to see it: the lag is computed from the
    day `last_session()` chose, which is exactly the thing the shape test silently moves."""
    outcome, lines = intraday_launch.store_warnings(
        dt.date(2026, 9, 8), today=dt.date(2026, 9, 12), store=tmp_path / "empty")
    assert outcome == "warn"
    assert any("replay_lag" in ln and "2026-09-08" in ln and "3 closed session" in ln
               for ln in lines), lines


def test_a_current_replay_day_is_quiet(tmp_path):
    """A healthy morning must not alert, or the alert stops being read. `tmp_path/store` does
    not exist, so the only finding available is the absent-store one - and that is a WARN, not
    the replay_lag line under test."""
    _, lines = intraday_launch.store_warnings(
        dt.date(2026, 9, 11), today=dt.date(2026, 9, 14), store=tmp_path / "store")
    assert not any("replay_lag" in ln for ln in lines), lines


def test_an_absent_store_warns_rather_than_raising(tmp_path):
    outcome, lines = intraday_launch.store_warnings(
        dt.date(2026, 9, 11), today=dt.date(2026, 9, 14), store=tmp_path / "nope")
    assert outcome == "warn"
    assert any("no such store" in ln for ln in lines), lines


def test_no_replay_day_still_reports_the_store(tmp_path):
    """`day=None` happens when nothing is replayable at all. The lag is unanswerable then, but
    the store findings are still the operator's best clue, so they must survive."""
    outcome, lines = intraday_launch.store_warnings(
        None, today=dt.date(2026, 9, 14), store=tmp_path / "nope")
    assert outcome == "warn"
    assert not any("replay_lag" in ln for ln in lines)
    assert any("no such store" in ln for ln in lines)


def test_a_broken_checker_is_skipped_not_fatal(monkeypatch, tmp_path):
    """The whole point of the asymmetry: if the health check itself breaks, the sleeve trades.
    A reporter that can crash the launcher is worse than no reporter at all."""
    import store_health

    def explode(*a, **k):
        raise RuntimeError("pyarrow went away")

    monkeypatch.setattr(store_health, "check_minute_store", explode)
    outcome, lines = intraday_launch.store_warnings(
        dt.date(2026, 9, 11), today=dt.date(2026, 9, 14), store=tmp_path)
    assert outcome == "skipped"
    assert "pyarrow went away" in lines[0]


def test_an_unimportable_checker_is_skipped(monkeypatch, tmp_path):
    """E-6 left `last_session()` a fallback for the same reason; the report needs one too."""
    import builtins
    real_import = builtins.__import__

    def no_store_health(name, *a, **k):
        if name == "store_health":
            raise ImportError("no module named store_health")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_store_health)
    outcome, lines = intraday_launch.store_warnings(
        dt.date(2026, 9, 11), today=dt.date(2026, 9, 14), store=tmp_path)
    assert outcome == "skipped"
    assert "unavailable" in lines[0]


def test_a_store_whose_last_session_died_midday_is_reported(tmp_path):
    """End to end on a real parquet store, because the finding that matters most - the fetch
    died at lunch - only exists once there are bars to measure. Built here rather than read
    from `data/minute`, so the verdict cannot depend on what the D-track fetched last night
    (E-8: a gating test must state a property of the code)."""
    pytest.importorskip("pyarrow")
    import pandas as pd

    store = tmp_path / "minute"
    store.mkdir()
    for sym in ("NVDA", "TSLA"):
        frames = []
        for day, last in ((dt.date(2026, 9, 10), "15:59"), (dt.date(2026, 9, 11), "12:19")):
            idx = pd.date_range(f"{day} 09:30", f"{day} {last}", freq="1min", tz="America/New_York")
            frames.append(pd.DataFrame({"o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0, "v": 1}, index=idx))
        pd.concat(frames).tz_convert("UTC").to_parquet(store / f"{sym}.parquet")

    outcome, lines = intraday_launch.store_warnings(
        dt.date(2026, 9, 10), today=dt.date(2026, 9, 11), store=store, symbols=["NVDA", "TSLA"])
    assert outcome == "warn"
    assert any("truncated_tail" in ln and "2026-09-11" in ln for ln in lines), lines


def test_the_store_report_cannot_change_the_exit_code():
    """The E-9 requirement, read off the launcher rather than trusted: `store_warnings` is
    called for its log and its alert, and nothing in the call site may branch to a return."""
    import ast
    src = (intraday_launch.REPO / "scripts" / "intraday_launch.py").read_text(encoding="utf-8")
    assert "preflight_store" in src, "the step must leave a record every morning"

    tree = ast.parse(src)
    main = next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == "main")
    call = next(n for n in ast.walk(main)
                if isinstance(n, ast.Call)
                and getattr(n.func, "id", None) == "store_warnings")
    # every statement that mentions the outcome must be free of `return` anywhere inside it
    guilty = [ast.dump(s) for s in ast.walk(main)
              if isinstance(s, ast.If)
              and "outcome" in ast.dump(s.test)
              and any(isinstance(x, ast.Return) for x in ast.walk(s))]
    assert not guilty, "the store report must never gate the launch"
    assert call is not None


def test_the_store_report_runs_before_the_replay():
    """So that a replay failure caused by bad data already has its explanation in the log
    above it, rather than needing a second run to find out."""
    src = (intraday_launch.REPO / "scripts" / "intraday_launch.py").read_text(encoding="utf-8")
    assert src.index("store_warnings(day)") < src.index('str(TRADER), "--replay"')
