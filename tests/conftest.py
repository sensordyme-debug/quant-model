"""Shared fixtures for the runner test suite.

Three jobs:

1. Put `scripts/` on `sys.path` so the runners import as top-level modules, exactly the way
   they import each other at run time (`intraday_trader` does `sys.path.insert` on its own
   directory, so anything else would test a different import graph than the one that runs).

2. **Make it impossible for a test to touch the live account's state.** The runners write
   `live/state/intraday_book.json` (the file the deployed 09:25 trader reads at start-up and
   flattens from), append to `live/log/*.jsonl`, and push chat alerts through the OpenClaw CLI.
   A test that ran the real functions would corrupt the sleeve's book or spam the owner's
   phone, so the `isolate_live` autouse fixture redirects the book to `tmp_path` and replaces
   every logging and alerting entry point with a recorder. Tests that want to see what was
   logged read `log_records` / `alerts`.

3. **Mark the tests that are allowed to stop the sleeve trading** (E-8). `intraday_launch`
   runs this suite at 09:25 and E-5 made `pytest exit 1` its one refusal, on the reasoning
   that "a failing test means the sizing or book arithmetic the trader is about to use is
   provably wrong". That reasoning is true of the runner tests and false of everything else
   in here, and the difference is not cosmetic - three tests in this suite have a verdict
   that depends on the machine rather than on the code:

       test_qb_scheduler   `resolve_workers(2, "futures") == 2` reads live free memory, and
                           returns 1 whenever commit charge is high - which is routine on
                           this box, since several sweep tracks run concurrently
       test_qb_dataquality  runs the validator over the deployed IBKR store, so a dead
                           overnight fetch fails it (E-6 found exactly that on 2026-09-11)
       test_qb_stats / test_qb_labels  read parquet, which needs an engine 3.11 lacks

   None of those says anything about the book, and all of them would have stopped the paper
   sleeve for the day. So the refusal is scoped to `RUNNER_TESTS` below and everything else
   degrades to a warning. Default is *not* gating: a new test file has to opt in to the
   power to cause an outage, which is E-5's asymmetry applied one level up.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
for p in (str(SCRIPTS), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)


# Job 1 above is exactly why `run_as_scheduler` exists (C-7). The path help this file gives
# every test is help the Task Scheduler does not give the runners: it registers
# `<python> "<repo>\scripts\<name>.py"` with the repo as the working directory, so `sys.path[0]`
# is `scripts/` and the repo root is NOT importable unless the script says so itself. C-6 found
# `paper_trade.py` unable to import for 83 minutes while 1,221 tests stayed green, because every
# one of them imported it through the lines above. Anything asserting "the deployed command
# starts" has to leave this process.
#
# `sys.executable` is the right interpreter, not an approximation: `intraday_launch` runs the
# gate as `[sys.executable, "-m", "pytest", ...]`, and the launcher is itself started by the
# scheduled task, so inside the 09:25 gate this IS the interpreter Task Scheduler registered.
_SCHEDULER_STRIPS = ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP")


def run_as_scheduler(script, *args, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    """Run `script` the way Task Scheduler runs it: absolute path, repo as cwd, no path help.

    The environment is inherited minus the variables that could smuggle the repo root onto
    `sys.path` behind the script's back, which would make every assertion built on this
    vacuous. `tests/test_runner_entrypoints.py` proves that it does not.
    """
    env = {k: v for k, v in os.environ.items() if k not in _SCHEDULER_STRIPS}
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=str(REPO), env=env, capture_output=True, text=True, timeout=timeout, check=False,
    )


# The modules that exercise code the live trader actually executes: sizing, the book, the
# gates, the cost model it fills at, the state it reconciles, and the launch gate itself. A
# failure in one of these means the arithmetic of the deployed sleeve is wrong, which is the
# only thing worth refusing to trade over.
RUNNER_TESTS = frozenset({
    # the one that says no process here can reach a venue. It belongs in the gating set for
    # the obvious reason: if the transmission freeze has come off by accident, the 09:25 task
    # must not start. It caught a real hole - paper_trade.py's FLATTEN branch built an
    # IBKRAdapter and called RoutedExecutor.flatten ~130 lines before the file's own hard
    # disable, so `--flatten`, or the mere existence of live/HALT, transmitted orders.
    "test_no_order_can_be_transmitted",
    # the governor in the live path and the FLATTEN close-out; a failure here must stop the sleeve
    "test_intraday_governor",
    "test_costs",             # the cost model positions are sized and marked with
    "test_intraday_book",     # book accounting
    "test_intraday_gates",    # halt / approval / time gates
    "test_intraday_p0",       # the trader's day-zero path
    "test_intraday_sizing",   # position sizing
    "test_launch_preflight",  # this gate's own failure mapping
    "test_paper_dataquality", # the daily runner's data gate (AUD-13): every assertion is on
                              # pinned dates and a fabricated frame, so nothing here can fail
                              # for a reason outside the code - which is what makes it
                              # eligible to gate at all (C-3)
    "test_paper_sizing",      # the daily sleeve's runner
    "test_reconcile_state",   # the live book's state reconciliation
    "test_runner_entrypoints", # (C-7) that the deployed command STARTS, proved by subprocess:
                              # C-6 broke `paper_trade.py`'s import for 83 minutes while the
                              # whole suite stayed green, because the path help above hid it
})

# Files that import a runner module but only to *read data through it* (the store loaders) or
# to test research tooling built on top of it. Listed explicitly so that
# `test_every_runner_importer_is_classified` stays a real check: a new file that touches the
# trader is a deliberate decision in one of these two sets, never an accident.
NON_GATING_RUNNER_IMPORTERS = frozenset({
    "test_intraday_data_extend",    # the fetcher, not the trader
    "test_intraday_harness_bias",   # backtest harness correctness
    "test_gateway_watchdog",        # infrastructure; cannot make the book wrong
    "test_qb_dataquality",          # validates the deployed store: data finding, not code
    "test_qb_labels",               # ditto
    "test_research_harness",        # the research path, not the live path
    "test_store_health",            # store completeness: data finding, not code
})


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "runner: covers code the live trader executes; a failure here stops the 09:25 sleeve",
    )


def pytest_collection_modifyitems(items):
    """Apply `runner` by module name rather than a `pytestmark` line in each file.

    One list in one place beats eight copies of a marker, and it keeps the gating set
    reviewable: `RUNNER_TESTS` is the answer to "what can stop the sleeve?".
    """
    mark = pytest.mark.runner
    for item in items:
        if item.module is not None and item.module.__name__ in RUNNER_TESTS:
            item.add_marker(mark)


@pytest.fixture(autouse=True)
def isolate_live(tmp_path, monkeypatch):
    """Redirect every side effect the runners have on `live/` into the test's tmp dir.

    Returns an object with `.log` (list of (module, kind, fields)) and `.alerts` (list of str)
    so a test can assert on what the runner *would* have recorded.
    """
    import intraday_common
    import intraday_launch
    import intraday_trader
    import paper_trade

    class Sink:
        def __init__(self):
            self.log: list[tuple[str, str, dict]] = []
            self.alerts: list[str] = []

        def kinds(self, module: str | None = None) -> list[str]:
            return [k for m, k, _ in self.log if module is None or m == module]

        def fields(self, kind: str) -> list[dict]:
            return [f for _, k, f in self.log if k == kind]

    sink = Sink()

    def fake_common_log(name, kind, **fields):
        sink.log.append((f"common:{name}", kind, fields))

    def fake_intraday_log(kind, **fields):
        sink.log.append(("intraday", kind, fields))

    def fake_paper_log(kind, **fields):
        sink.log.append(("paper", kind, fields))

    def fake_notify(text, *_a, **_k):
        sink.alerts.append(text)

    # intraday_trader imported log_event/notify into its own namespace; patch there AND at the
    # source, so neither import style leaks a real write.
    monkeypatch.setattr(intraday_common, "log_event", fake_common_log)
    monkeypatch.setattr(intraday_common, "notify", fake_notify)
    # intraday_launch does the same import, and E-11 gave it a code path (the background
    # full-suite report) that logs and alerts from a test's own process.
    monkeypatch.setattr(intraday_launch, "log_event", fake_common_log)
    monkeypatch.setattr(intraday_launch, "notify", fake_notify)
    monkeypatch.setattr(intraday_trader, "log_event", fake_common_log)
    monkeypatch.setattr(intraday_trader, "log", fake_intraday_log)
    monkeypatch.setattr(intraday_trader, "notify", fake_notify)
    monkeypatch.setattr(intraday_trader, "_notify", fake_notify)
    monkeypatch.setattr(paper_trade, "log_event", fake_paper_log)
    monkeypatch.setattr(paper_trade, "notify", fake_notify)
    monkeypatch.setattr(paper_trade, "record_alert", lambda *a, **k: None)

    # The live book, the halt files and the approval file all move into tmp_path. Nothing
    # under live/ is read or written by a test.
    book = tmp_path / "state" / "intraday_book.json"
    monkeypatch.setattr(intraday_trader, "BOOK_FILE", book)
    monkeypatch.setattr(intraday_trader, "HALT_FILES", [tmp_path / "HALT", tmp_path / "HALT_INTRADAY"])
    monkeypatch.setattr(intraday_trader, "APPROVAL", tmp_path / "APPROVED_PAPER.md")
    monkeypatch.setattr(paper_trade, "APPROVAL", tmp_path / "APPROVED_PAPER.md")
    monkeypatch.setattr(paper_trade, "HALT", tmp_path / "HALT")
    monkeypatch.setattr(paper_trade, "LOG_DIR", tmp_path / "log")
    monkeypatch.setattr(paper_trade, "STATE_DIR", tmp_path / "state")

    # `quant_brain.core.state.root_for()` resolves the StateStore root from this module
    # constant, so a test that builds a Trader in "live" mode publishes the governor to the
    # REAL live/state/governor.json. Measured: running the suite (and `pytest -m runner`,
    # which is the 09:25 pre-trade gate, and the pre-commit hook) rewrote that file.
    # Redirecting REPO sends every StateStore under tmp_path instead.
    import quant_brain.core.state as _qb_state
    monkeypatch.setattr(_qb_state, "REPO", tmp_path)

    # Belt and braces, and this time it braces something: fingerprint the REAL live state
    # before the test runs and refuse to let the test end if it changed. The previous guard
    # asserted the absence of `intraday_book.json.test`, a filename nothing in the tree ever
    # creates, so it passed while the suite was rewriting live/state/governor.json.
    _live_real = REPO / "live"
    _before = {
        p: p.stat().st_mtime_ns
        for d in ("state", "log")
        for p in sorted((_live_real / d).glob("*"))
        if p.is_file()
    }

    yield sink

    _after = {
        p: p.stat().st_mtime_ns
        for d in ("state", "log")
        for p in sorted((_live_real / d).glob("*"))
        if p.is_file()
    }
    _changed = sorted(
        str(p.relative_to(REPO)) for p in set(_before) | set(_after)
        if _before.get(p) != _after.get(p)
    )
    assert not _changed, (
        "a test mutated real production state under live/: "
        + ", ".join(_changed)
        + ". Every live path must be redirected into tmp_path by this fixture."
    )


@pytest.fixture
def sink(isolate_live):
    """Alias so a test can ask for the recorder by name."""
    return isolate_live
