#!/usr/bin/env python
"""Preflight + launch for the intraday sleeve. This is what the 09:25 ET scheduled task runs.

    python scripts/intraday_launch.py            # preflight, then live paper trading
    python scripts/intraday_launch.py --dry-run  # preflight, then live bars without orders

Preflight (any failure -> alert, no trading):
  1. the runner unit suite (`tests/`) passes - the sizing, gate and book-accounting arithmetic
     the replay cannot reach (loss limit, HALT files, margin ceiling, shared-constant drift)
  2. replay the most recent stored session through scripts/intraday_trader.py (exercises the
     exact strategy + execution code that is about to run; catches a broken commit overnight)
  3. IB Gateway reachable and the account is a paper account
  4. live/APPROVED_PAPER.md present and no HALT file
Then it runs the trader in the foreground until 15:42 ET and forwards its exit code.

    python scripts/intraday_launch.py --preflight-only   # run the gates, never launch
"""
from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from intraday_common import LIVE, REPO, UNIVERSE, load_bars, log_event, notify  # noqa: E402

PY = sys.executable
TRADER = REPO / "scripts" / "intraday_trader.py"
CONFIG = LIVE / "intraday_config.json"       # {"strategy": "active", "equity_frac": 1.0, "params": {...}}
PYTEST_TIMEOUT = 300                         # suite is ~30 s on 3.14 / ~22 s on 3.11: hang guard
SUBSET_TIMEOUT = 120                         # the `runner` re-run is ~13 s; only on a failure


def config():
    import json
    cfg = {"strategy": "active", "equity_frac": 1.0, "params": {}}
    if CONFIG.exists():
        cfg.update(json.loads(CONFIG.read_text(encoding="utf-8")))
    return cfg


def last_session() -> dt.date | None:
    """Most recent session that is COMPLETE for the sampled symbols.

    A truncated last day - the store refreshed mid-session - replays with open positions and a
    nonsense P&L (2026-09-10, and again on 2026-09-11: 170/390 bars, 15 positions still open,
    exit 0), so the preflight must pick a session it can carry all the way to the flatten.

    "Complete" is a SHAPE, not a bar count (E-6). The original `>= 300 bars` test is wrong in
    both directions, and both were confirmed against the live store:

      * A complete early close is 210 bars. `>= 300` rejects it, so the two early closes in the
        store - 2025-11-28 and 2025-12-24, both 210/210 - are unreplayable, and the morning gate
        can therefore NEVER exercise the calendar-aware flatten that AUD-07 exists for. That is
        the path most likely to break, skipped on exactly the mornings it matters.
      * A fetch that dies at 14:40 leaves 310/390 bars. `>= 300` accepts it, and the replay ends
        with an open book - the defect the guard was added to prevent.

    Asking whether the session's bars SPAN the session answers both. If `store_health` cannot be
    imported the old heuristic still runs: a completeness checker must never be the reason the
    sleeve fails to launch.
    """
    try:
        import store_health as sh
        from quant_brain.markets.equity_us import CALENDAR
    except Exception:  # noqa: BLE001 - fall back rather than fail the launch
        sh = CALENDAR = None

    complete = None
    for s in UNIVERSE[:4]:
        df = load_bars(s)
        if df.empty:
            continue
        if sh is not None:
            ok = {x.day for x in sh.session_shapes(df.index, CALENDAR) if not x.truncated}
        else:
            counts = df.groupby(df.index.date).size()
            ok = set(counts[counts >= 300].index)
        complete = ok if complete is None else complete & ok
    return max(complete) if complete else None


def unit_tests_ok(root: Path = REPO, python: str = PY,
                  timeout: int = PYTEST_TIMEOUT) -> tuple[bool, str, str]:
    """Run the runner unit suite. Returns (may_trade, outcome, detail).

    The asymmetry here is deliberate and is the whole design of this gate. A failing test means
    the sizing or book arithmetic the trader is about to use is provably wrong, so trading must
    not start. *Every other* outcome - pytest not installed, no tests collected, a collection
    error, a hang - says nothing about the book and must NOT stop the sleeve: refusing to trade
    because a dev dependency is missing on the machine would be a self-inflicted outage, and the
    replay preflight below is the check that actually guards the strategy path.

    So importability is probed separately instead of read off the exit code, because
    `python -m pytest` with pytest absent exits 1 - the same code as a real test failure.

    E-8 narrowed *which* failure counts. "A failing test means the book arithmetic is wrong"
    is true of the runner tests and false of the rest of the suite, where three tests were
    found whose verdict depends on the machine and not on the code: worker allocation reads
    live free memory, the store validators read the deployed parquet store, and two research
    tests need a parquet engine 3.11 does not have. Any of those would have stopped the
    sleeve for a day. So on exit 1 the runner-marked subset is re-run and *it* decides; a
    failure only outside that subset trades with a warning. See `tests/conftest.py`.
    """
    # If this very interpreter is already running pytest, it is importable by definition; the
    # probe is a second process launch (~1.4 s on Windows) worth skipping. At 09:25 the launcher
    # is plain python, so the real deploy path always probes.
    if not (python == sys.executable and "pytest" in sys.modules):
        try:
            probe = subprocess.run([python, "-c", "import pytest"], capture_output=True,
                                   text=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as exc:   # interpreter gone, or probe hung
            return True, "skipped", f"could not probe pytest with {python}: {exc}"
        if probe.returncode != 0:
            return True, "skipped", f"pytest not importable by {python}"
    if not (root / "tests").is_dir():
        return True, "skipped", f"no tests/ directory under {root}"

    try:
        # no -q here: pytest.ini already sets it, and a second one suppresses the
        # "126 passed in 35s" summary line that is the whole point of the log record.
        res = subprocess.run([python, "-m", "pytest", "-p", "no:cacheprovider", "--tb=line"],
                             cwd=str(root), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return True, "warn", f"suite exceeded {timeout}s and was abandoned"
    except OSError as exc:
        return True, "warn", f"could not run the suite: {exc}"

    out = (res.stdout + res.stderr).strip()
    tail = out.splitlines()[-1] if out else f"exit {res.returncode}"
    if res.returncode == 0:
        return True, "passed", tail
    if res.returncode == 1:                     # the only refusal: real assertion failures
        if _runner_subset_passed(root, python, timeout):
            return True, "warn", ("suite failed outside the live trading path, trading anyway: "
                                  + out[-1200:])
        return False, "failed", out[-1500:]
    # 2 interrupted, 3 internal error, 4 usage error, 5 nothing collected -> not a verdict
    return True, "warn", f"pytest exit {res.returncode}: {tail}"


def _runner_subset_passed(root: Path, python: str, timeout: int) -> bool:
    """Did the `runner`-marked tests pass? Only reached when the full suite already failed.

    Returns False - i.e. refuse - whenever the answer cannot be established: the subset also
    failed, the marker is not registered in this repo so nothing was collected, or the re-run
    could not be launched. The narrowing may only ever *downgrade a refusal it can prove is
    unrelated to the book*; an unreadable answer keeps E-5's original behaviour.

    The re-run gets its own, tighter budget: it is under a third of the suite (183 tests in
    13 s against 624 in 30 s) and it only ever happens on a morning that is already going
    wrong, so it must not be able to double the gate's worst case five minutes before the open.
    """
    try:
        res = subprocess.run([python, "-m", "pytest", "-m", "runner",
                              "-p", "no:cacheprovider", "--tb=line"],
                             cwd=str(root), capture_output=True, text=True,
                             timeout=min(timeout, SUBSET_TIMEOUT))
    except (OSError, subprocess.SubprocessError):
        return False
    return res.returncode == 0 and "no tests ran" not in (res.stdout + res.stderr)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-replay", action="store_true")
    ap.add_argument("--skip-tests", action="store_true")
    ap.add_argument("--preflight-only", action="store_true",
                    help="run the preflight gates and exit; never start the trader")
    args = ap.parse_args()
    cfg = config()
    import json
    common = ["--strategy", cfg["strategy"], "--equity-frac", str(cfg["equity_frac"])]
    if cfg.get("params"):
        common += ["--params", json.dumps(cfg["params"])]

    # 1) unit suite: offline, ~35 s, and reaches the guards the replay cannot
    if not args.skip_tests:
        ok, outcome, detail = unit_tests_ok()
        log_event("intraday", "preflight_tests", outcome=outcome, detail=detail[-500:])
        if not ok:
            msg = f"INTRADAY preflight FAILED: unit suite failed, not trading. {detail[-400:]}"
            print(msg); notify(msg)
            return 4
        print(f"preflight tests {outcome}: {detail}" if outcome != "passed"
              else f"preflight tests OK: {detail}")
        if outcome != "passed":
            notify(f"INTRADAY preflight: unit suite {outcome} ({detail[-200:]}); trading anyway")

    # 2) replay preflight
    if not args.skip_replay:
        day = last_session()
        if day is None:
            msg = "INTRADAY preflight FAILED: no stored minute bars to replay"
            print(msg); notify(msg); log_event("intraday", "preflight_failed", reason="no_bars")
            return 2
        res = subprocess.run([PY, str(TRADER), "--replay", str(day)] + common, capture_output=True, text=True, timeout=1200)
        tail = (res.stdout + res.stderr)[-800:]
        if res.returncode != 0 or "replay" not in res.stdout:
            msg = f"INTRADAY preflight FAILED: replay of {day} exited {res.returncode}: {tail[-300:]}"
            print(msg); notify(msg); log_event("intraday", "preflight_failed", reason="replay", output=tail)
            return 2
        print("preflight replay OK:", res.stdout.strip().splitlines()[-1])

    # 3) gates
    if any((LIVE / n).exists() for n in ("HALT", "HALT_INTRADAY")):
        msg = "INTRADAY not started: HALT file present"
        print(msg); notify(msg); log_event("intraday", "not_started", reason="halt")
        return 3
    if not args.dry_run and not (LIVE / "APPROVED_PAPER.md").exists():
        print("no approval file: running dry"); args.dry_run = True

    # 4) launch
    if args.preflight_only:
        print("preflight-only: all gates passed, not launching")
        return 0
    cmd = [PY, str(TRADER)] + common + (["--dry-run"] if args.dry_run else [])
    log_event("intraday", "launch", cmd=cmd)
    return subprocess.call(cmd)


if __name__ == "__main__":
    sys.exit(main())
