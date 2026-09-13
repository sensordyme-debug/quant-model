"""C-7: does the command Task Scheduler actually runs still start?

The suite has always proved the runners through a path the scheduler does not have.
`tests/conftest.py` puts both `scripts/` and the repo root on `sys.path` before any test
imports anything, so `import paper_trade` succeeds in here no matter what the file's own
import block does. The scheduled task gives no such help: it registers

    C:\\...\\python.exe  "C:\\...\\quant-model\\scripts\\paper_trade.py"   (cwd = the repo)

which makes `sys.path[0]` the *scripts* directory and leaves the repo root unimportable
unless the script arranges it. C-6 is what that costs: on 2026-09-13 commit `c1fc9b1` put
`from quant_brain...` above the `sys.path` guard that was already in `paper_trade.py`, the
deployed 15:45 command could not import for 83 minutes across two commits, and `pytest tests/`
stayed green at 1,221 tests for every minute of it. A critic found it; the gate could not.

Reproduced on the real file before this test was written, by moving that one guard back below
the import it protects and running both paths:

    subprocess, scheduler's recipe   rc=1  ModuleNotFoundError: No module named 'quant_brain'
    in-process, conftest's sys.path  rc=0  import OK

So the assertion has to be on a subprocess. An in-process import inherits the already-fixed
`sys.path` and would pass while the deployed command was broken - which is the defect, not a
test of it.

Gating (`conftest.RUNNER_TESTS`). A trading entry point that cannot start is not a fact about
this machine, it is a fact about the code in the repository, which is E-8's standard for the
power to stop the sleeve. The dashboard is registered as a scheduled task too, but it cannot
make the book wrong and must not be able to stop the open, so it is checked in
`test_dashboard_entrypoint.py`, which does not gate.

`--help` is the probe because it runs the whole module-level import graph and then exits 0
before `main()` - no IB connection, no order, nothing written under `live/`. Cost: ~1.4 s for
all three, against a gate that E-11 left at 21 s.
"""
from __future__ import annotations

import re

import pytest
from conftest import REPO, run_as_scheduler

# The entry points on the trading path, named as the scheduler names them. The first two are
# registered by `scripts/install_*.ps1`; `intraday_trader.py` is not registered directly but is
# spawned by the launcher with the same recipe (`intraday_launch.py`: `[PY, str(TRADER), ...]`),
# so it starts with the same `sys.path` and is exposed to the same defect.
TRADING_ENTRYPOINTS = ("paper_trade", "intraday_launch", "intraday_trader")

# Registered as a scheduled task, deliberately NOT gating - see the module docstring.
NON_TRADING_ENTRYPOINTS = ("dashboard",)


@pytest.mark.parametrize("name", TRADING_ENTRYPOINTS)
def test_the_deployed_command_starts_without_the_suite_s_path_help(name):
    """The exact class of outage C-6 hit: import-time breakage invisible to an in-process test."""
    res = run_as_scheduler(REPO / "scripts" / f"{name}.py", "--help")
    assert res.returncode == 0, (
        f"scripts/{name}.py cannot start the way the scheduler starts it "
        f"(rc={res.returncode}). This is the deployed command, not a test harness:\n"
        f"{res.stderr.strip() or res.stdout.strip()}")
    assert f"usage: {name}.py" in res.stdout, (
        f"scripts/{name}.py exited 0 but never reached argparse; stdout:\n{res.stdout[:500]}")


def test_the_recipe_really_has_no_repo_root_on_sys_path(tmp_path):
    """Falsifiability control, and the only thing standing between this file and vacuity.

    Every assertion above is worth nothing if the subprocess gets the repo root by some route
    the recipe does not control - a `.pth` in site-packages, an editable install, a
    `PYTHONPATH` exported into the agent's shell. A script that imports `quant_brain` with no
    guard of its own MUST fail. If this test ever goes green-by-accident, the parametrized
    tests above are measuring nothing and this is the one that says so.
    """
    script = tmp_path / "no_guard.py"
    script.write_text("import quant_brain\nprint('imported')\n", encoding="utf-8")

    res = run_as_scheduler(script)

    assert res.returncode != 0, (
        "a script with no sys.path guard imported quant_brain anyway, so the repo root is "
        "reaching subprocesses by some route this recipe does not strip - every other "
        "assertion in this file is now vacuous")
    assert "No module named 'quant_brain'" in res.stderr


def test_the_recipe_admits_a_script_that_carries_its_own_guard(tmp_path):
    """The other half of the control: the failure above is about the path, not about the package.

    Without this, a `quant_brain` that was broken outright would satisfy the test above and the
    two would agree while describing nothing. Same recipe, same import, one added line - the
    line `paper_trade.py` carries and C-6 moved.
    """
    script = tmp_path / "with_guard.py"
    script.write_text(
        f"import sys\nsys.path.insert(0, r'{REPO}')\nimport quant_brain\nprint('imported')\n",
        encoding="utf-8")

    res = run_as_scheduler(script)

    assert res.returncode == 0, res.stderr.strip()
    assert "imported" in res.stdout


def test_every_python_script_an_installer_registers_is_classified():
    """A sixth scheduled task must not arrive with nothing checking that its command starts.

    Reads the installers, not Task Scheduler: the registered state is a property of this
    machine, and E-8 is explicit that a gating test may not have one of those for a verdict.
    """
    registered = set()
    for installer in sorted((REPO / "scripts").glob("install_*.ps1")):
        src = installer.read_text(encoding="utf-8")
        registered.update(re.findall(r"scripts\\(\w+)\.py", src))

    assert registered, "no installer registers a python script - has the pattern changed?"
    unclassified = registered - set(TRADING_ENTRYPOINTS) - set(NON_TRADING_ENTRYPOINTS)
    assert not unclassified, (
        f"{sorted(unclassified)} are registered as scheduled tasks but are in neither "
        "TRADING_ENTRYPOINTS nor NON_TRADING_ENTRYPOINTS - decide whether a failure to start "
        "may stop the 09:25 sleeve, then add it to one of them")


def test_the_table_names_only_scripts_that_exist():
    """A renamed runner must not silently drop out of this check."""
    for name in TRADING_ENTRYPOINTS + NON_TRADING_ENTRYPOINTS:
        assert (REPO / "scripts" / f"{name}.py").exists(), f"{name}.py is listed but has no file"
