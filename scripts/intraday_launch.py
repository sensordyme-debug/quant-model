#!/usr/bin/env python
"""Preflight + launch for the intraday sleeve. This is what the 09:25 ET scheduled task runs.

    python scripts/intraday_launch.py            # preflight, then live paper trading
    python scripts/intraday_launch.py --dry-run  # preflight, then live bars without orders

Preflight (any failure -> alert, no trading):
  1. the `runner`-marked tests pass - the sizing, gate and book-accounting arithmetic the
     replay cannot reach (loss limit, HALT files, margin ceiling, shared-constant drift)
  2. replay the most recent stored session through scripts/intraday_trader.py (exercises the
     exact strategy + execution code that is about to run; catches a broken commit overnight)
  3. IB Gateway reachable and the account is a paper account
  4. live/APPROVED_PAPER.md present and no HALT file
Then it runs the trader in the foreground until 15:42 ET and forwards its exit code.

Two steps here *report* and can never gate (they are the E-9 shape, asserted by tests that
walk this file's AST): the deployed minute store, between 1 and 2 - see `store_warnings` - and
the rest of the test suite, which runs in a background thread alongside the trader rather than
in front of it - see `start_full_suite_report`.

    python scripts/intraday_launch.py --preflight-only   # run the gates, never launch
"""
from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from intraday_common import DATA_DIR, LIVE, REPO, UNIVERSE, load_bars, log_event, notify  # noqa: E402

PY = sys.executable
TRADER = REPO / "scripts" / "intraday_trader.py"
CONFIG = LIVE / "intraday_config.json"       # {"strategy": "active", "equity_frac": 1.0, "params": {...}}
GATE_TIMEOUT = 120                           # hang guard for the gate: `-m runner`, 223 tests,
                                             # 19 s measured 2026-09-13
PYTEST_TIMEOUT = 300                         # hang guard for the full-suite REPORT, which runs
                                             # beside the trader and decides nothing

#: How many closed sessions the replayed day may sit behind the last closed one before the
#: preflight says so. 1 is a fetcher that skipped a night; 2+ is a fetcher that is not running.
#: Matches `store_health.STALE_DAYS`, which draws the same line for the same reason.
REPLAY_LAG_WARN = 2


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


def replay_lag(day: dt.date, today: dt.date, calendar) -> int:
    """Closed sessions strictly between the replayed day and today.

    0 on a normal morning (yesterday's session replayed today), 1 if a single overnight fetch
    was skipped, and one more for every session the store has not caught up on since.
    """
    return sum(1 for d in calendar.trading_days(day, today) if day < d < today)


def store_warnings(day: dt.date | None, *, today: dt.date | None = None,
                   store: Path | None = None,
                   symbols: list[str] | None = None) -> tuple[str, list[str]]:
    """E-9: report on the minute store the replay just drew from. Never a refusal.

    Returns `(outcome, lines)` with outcome in `{"ok", "warn", "skipped"}`. The caller logs and
    alerts on it and **must not branch on it**, for the same reason `unit_tests_ok` refuses only
    on a real assertion failure: a data finding says the store is short, not that the sizing or
    book arithmetic the trader is about to use is wrong. Excluding a bad date is research's job;
    stopping the sleeve over one would be a self-inflicted outage. So every failure path in here
    - a missing module, an unreadable parquet, a calendar that does not cover the day - returns
    "skipped" rather than raising, and the launcher's exit code is untouched either way.

    Why it exists at all. E-6 gave `last_session()` a shape test so the preflight would stop
    replaying half-days, and that fix made the failure it guards against **silent**: the
    launcher now walks back to the newest session that spans the bell and reports "replay OK"
    with no hint of how old it was. Measured on a copy of the live store with every symbol's
    last three sessions cut at 12:19, `last_session()` returned 2026-09-08 instead of
    2026-09-11 and the morning was otherwise indistinguishable from a healthy one. Nothing
    else on the schedule looks at the stores, so a dead fetcher could degrade the sleeve's
    research data indefinitely without a word. `replay_lag` is the number that says it.

    Scoped to the deployed universe (16 symbols, ~2.5 s) rather than every store: the 63M-row
    Alpaca store takes 98 s to check and the 09:25 gate is not where that belongs.
    """
    try:
        import store_health as sh
        from quant_brain.core.dataquality import Severity
        from quant_brain.markets.equity_us import CALENDAR
    except Exception as exc:  # noqa: BLE001 - a reporter must never be why the sleeve stops
        return "skipped", [f"store health unavailable: {type(exc).__name__}: {exc}"[:160]]

    today = today or dt.date.today()
    lines: list[str] = []
    try:
        if day is not None:
            lag = replay_lag(day, today, CALENDAR)
            if lag >= REPLAY_LAG_WARN:
                lines.append(
                    f"  WARN  store    replay_lag             the newest COMPLETE session is "
                    f"{day}, {lag} closed session(s) behind {today} - the overnight fetch has "
                    f"not run or is dying mid-session; the replay is proving the code against "
                    f"stale bars")
        rep, _rows = sh.check_minute_store(store or DATA_DIR, CALENDAR, today=today,
                                           symbols=symbols or UNIVERSE)
        lines += [f.line() for f in rep.findings if f.severity is not Severity.INFO]
    except Exception as exc:  # noqa: BLE001
        return "skipped", [f"store health did not complete: {type(exc).__name__}: {exc}"[:160]]
    return ("warn" if lines else "ok"), lines


def unit_tests_ok(root: Path = REPO, python: str = PY,
                  timeout: int = GATE_TIMEOUT) -> tuple[bool, str, str]:
    """Run the `runner`-marked tests. Returns (may_trade, outcome, detail).

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
    sleeve for a day. E-10 then closed the way round that refusal, because a hang in the tests
    that may *not* decide was burning the timeout the ones that may were reached through.

    E-11 is the consequence both of those stopped one step short of. Once only the `runner`
    tests can move the verdict, running the other 996 *first* buys nothing: every reachable
    (suite, subset) pair maps to the verdict the subset alone gives, with one exception -
    suite failed + subset unreadable, which refused, i.e. the full suite's sole contribution
    to this gate was an outage of exactly the shape E-5 forbids. It cost 105 s of a 300 s
    pre-open window (measured 2026-09-13; 82 s the day before, a suite five tracks grow
    daily), against 19 s for the tests that decide. So the gate is now the subset, full stop,
    and the rest of the suite runs as a report beside the trader - `full_suite_report`.

    The mapping is unchanged in substance and is simply no longer reached through 105 s of
    someone else's tests:

        `runner` test fails (exit 1)  -> refuse, no trading
        anything else                 -> trade, with a warning

    One new warning matters: `-m runner` collecting nothing means the marker is gone and this
    gate is DISARMED. E-5 still applies - an unreadable answer is not evidence and must not
    cause an outage - so it trades, loudly. The alert is the defence, because a test cannot be
    the defence here: a broken marker deselects the test that would have caught it.
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
        # "223 passed, 1003 deselected in 18.72s" summary that is the point of the log record.
        res = subprocess.run([python, "-m", "pytest", "-m", "runner",
                              "-p", "no:cacheprovider", "--tb=line"],
                             cwd=str(root), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        # E-5: a hang is not evidence about the book. It is now also far harder to reach -
        # `-m runner` deselects every test this gate does not own, so a hang here is a hang in
        # the trading path's own tests rather than in whatever another track added last night.
        return True, "warn", f"the runner tests exceeded {timeout}s and were abandoned"
    except (OSError, subprocess.SubprocessError) as exc:
        return True, "warn", f"could not run the runner tests: {exc}"

    out = (res.stdout + res.stderr).strip()
    tail = out.splitlines()[-1] if out else f"exit {res.returncode}"
    if res.returncode == 0:
        return True, "passed", tail
    if res.returncode == 1:                     # the only refusal: real assertion failures
        return False, "failed", out[-1500:]
    if res.returncode == 5 or "no tests ran" in out:
        # The marker is not registered, so nothing was selected and this gate is not checking
        # anything. Trading is still the right call (E-5), but it must be said out loud: the
        # test that would catch a broken marker is itself deselected by the broken marker.
        return True, "warn", (f"GATE DISARMED: no `runner` tests were collected in {root} "
                              f"(pytest exit {res.returncode}); the sizing and book arithmetic "
                              f"was NOT checked this morning. {tail}")
    # 2 interrupted, 3 internal error, 4 usage error -> not a verdict
    return True, "warn", f"pytest exit {res.returncode}: {tail}"


def _low_priority() -> dict:
    """Keyword args that put a child process below the trader on the CPU, where available."""
    flag = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", None)
    return {"creationflags": flag} if flag else {}


def full_suite_report(root: Path = REPO, python: str = PY,
                      timeout: int = PYTEST_TIMEOUT) -> tuple[str, str]:
    """Run the whole suite for the record. Returns (outcome, detail) and gates nothing.

    E-11. This used to be the gate, and the measurement that ended that is simple: of the 1,226
    tests in the repo on 2026-09-13, 223 are allowed to stop the sleeve and 1,003 are not, yet
    the verdict of the 223 was reached *through* 105 s of running all 1,226 - 88% of a 119 s
    preflight, in a window that closes at the 09:30 open. The suite grew 82 s -> 105 s in a
    single day under five concurrent tracks, none of which owns this deadline.

    The other 1,003 tests are still worth running every morning: they are how a track finds out
    it broke something overnight. They are just not worth *waiting for*, so they run here, in a
    background thread, below the trader's priority, and report through the log and the alert
    file like `store_warnings` does. The outcome vocabulary is deliberately different from
    `unit_tests_ok`'s - there is no may_trade in it to misread.
    """
    try:
        res = subprocess.run([python, "-m", "pytest", "-p", "no:cacheprovider", "--tb=line"],
                             cwd=str(root), capture_output=True, text=True, timeout=timeout,
                             **_low_priority())
    except subprocess.TimeoutExpired:
        return "timeout", f"the full suite exceeded {timeout}s and was abandoned"
    except (OSError, subprocess.SubprocessError) as exc:
        return "skipped", f"could not run the full suite: {exc}"
    out = (res.stdout + res.stderr).strip()
    tail = out.splitlines()[-1] if out else f"exit {res.returncode}"
    if res.returncode == 0:
        return "passed", tail
    if res.returncode == 1:
        return "failed", out[-1500:]
    return "warn", f"pytest exit {res.returncode}: {tail}"


def start_full_suite_report(root: Path = REPO, python: str = PY) -> threading.Thread:
    """Kick off `full_suite_report` beside the trader. Never raises, never gates.

    A daemon thread, so it cannot hold the launcher open, and `main` does not join it except
    under `--preflight-only` where there is no trader to run and the report is the deliverable.
    """
    def run() -> None:
        t0 = time.time()
        try:
            outcome, detail = full_suite_report(root, python)
        except Exception as exc:  # noqa: BLE001 - a reporter may never take the launcher down
            outcome, detail = "skipped", f"{type(exc).__name__}: {exc}"
        secs = round(time.time() - t0, 1)
        log_event("intraday", "suite_report", outcome=outcome, seconds=secs,
                  detail=detail[-500:])
        print(f"full suite report: {outcome} in {secs}s")
        if outcome in ("failed", "timeout"):
            notify(f"INTRADAY suite report: the full suite {outcome} after {secs}s. The "
                   f"`runner` tests passed, so the sleeve is trading; this is off the trading "
                   f"path. {detail[-300:]}")

    th = threading.Thread(target=run, name="full-suite-report", daemon=True)
    th.start()
    return th


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

    # 1) the gate: the `runner` tests only, ~19 s, and they reach the guards the replay cannot
    report: threading.Thread | None = None
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
        # 1a) E-11: the other ~1,000 tests are a report, not a gate. Started here so it overlaps
        # the replay and then the trader instead of standing in front of the open. It cannot
        # change the exit code; `test_the_suite_report_cannot_change_the_exit_code` pins that.
        report = start_full_suite_report()

    # 2) replay preflight
    if not args.skip_replay:
        day = last_session()
        if day is None:
            msg = "INTRADAY preflight FAILED: no stored minute bars to replay"
            print(msg); notify(msg); log_event("intraday", "preflight_failed", reason="no_bars")
            return 2

        # 2a) E-9: say what the store looks like, BEFORE the replay runs on it. Report-only -
        # it cannot change the exit code, and it is placed here so that when the replay does
        # fail the reason is already in the log and the alert above it.
        outcome, lines = store_warnings(day)
        log_event("intraday", "preflight_store", outcome=outcome, replay_day=str(day),
                  detail="; ".join(x.strip() for x in lines)[:600])
        print(f"preflight store {outcome} (replaying {day})")
        for ln in lines:
            print(ln)
        if outcome == "warn":
            notify("INTRADAY preflight: minute store findings, trading anyway - "
                   + "; ".join(x.strip() for x in lines)[:300])

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
        # No trader to run beside, so wait for the report rather than killing it with the
        # process. Bounded, and the result is a print/log either way - never a return code.
        if report is not None:
            report.join(timeout=PYTEST_TIMEOUT + 30)
        return 0
    cmd = [PY, str(TRADER)] + common + (["--dry-run"] if args.dry_run else [])
    log_event("intraday", "launch", cmd=cmd)
    return subprocess.call(cmd)


if __name__ == "__main__":
    sys.exit(main())
