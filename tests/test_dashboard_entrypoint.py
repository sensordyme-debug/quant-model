"""C-7, non-gating half: the dashboard is a scheduled task too, but it may not stop the open.

`scripts/dashboard.py` is registered by `install_dashboard_task.ps1` with the same recipe as
the trading runners, so it is exposed to the same import-time defect C-6 found, and it is worth
checking that its deployed command starts. It is deliberately NOT in `conftest.RUNNER_TESTS`:
a read-only monitor that will not launch says nothing about the book's arithmetic, and E-8
exists because a gating test whose verdict is not about the trading path is a self-inflicted
outage waiting for 09:25. Failure here is a warning in the launcher's log and a real bug to
fix; it is not a reason to leave the sleeve flat for the day.

The gating half, the controls that keep this recipe honest, and the table that catches a newly
registered task are in `tests/test_runner_entrypoints.py`.
"""
from __future__ import annotations

import pytest
from conftest import REPO, run_as_scheduler
from test_runner_entrypoints import NON_TRADING_ENTRYPOINTS


@pytest.mark.parametrize("name", NON_TRADING_ENTRYPOINTS)
def test_the_registered_dashboard_command_starts(name):
    res = run_as_scheduler(REPO / "scripts" / f"{name}.py", "--help")
    assert res.returncode == 0, (
        f"scripts/{name}.py cannot start the way its scheduled task starts it "
        f"(rc={res.returncode}):\n{res.stderr.strip() or res.stdout.strip()}")
    assert f"usage: {name}.py" in res.stdout
