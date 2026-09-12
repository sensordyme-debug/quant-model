#!/usr/bin/env python
"""The completion gate. Run this before you claim a change is done.

    python scripts/qb_check.py                 # blocking gate: lint + tests
    python scripts/qb_check.py --advisory      # also report the legacy debt (never fails)
    python scripts/qb_check.py --changed       # lint only what git says you touched
    python scripts/qb_check.py --quiet         # one line per stage, for hooks

WHY A SCRIPT AND NOT JUST `ruff && pytest`
-------------------------------------------
`research/audit_2026-09-12.md` found 25 defects, nine of them P0 - able to place wrong
orders or liquidate the book. The reason that many accumulated is not that anyone was
careless; it is that the full path from "an agent edits intraday_trader.py" to "that code
trades a real account at 09:25 tomorrow" contained no syntax check, no lint, no type check
and no mandatory test run. Every one of those was a written instruction in AGENTS.md that an
unattended agent under rate-limit pressure could simply not perform, with nothing noticing.

This makes the gate a thing you can run and a thing a hook can enforce.

THE TWO-TIER DESIGN, AND WHY IT IS NOT A CHEAT
-----------------------------------------------
Measured 2026-09-12: the strict ruleset reports 1,428 findings across scripts/ and
algorithms/ - 32k lines written in five days by six concurrent tracks - and a handful across
quant_brain/ and tests/. A gate that is red on day one is a gate that gets bypassed by
Friday, so:

    BLOCKING   quant_brain/, tests/, and anything you changed. Green today, stays green.
    ADVISORY   the whole repository, reported by rule with counts, never fails the run.

The advisory tier is how the legacy debt stays visible instead of being deleted from the
config and forgotten. It shrinks by moving rules out of `per-file-ignores` in ruff.toml, one
family per commit, each with the suite run after.

WHAT THIS DOES NOT DO
---------------------
It does not run the replay preflight or `compare_orders.py`. Those need IB Gateway and a
stored session, take minutes rather than seconds, and already gate the 09:25 launch through
`scripts/intraday_launch.py`. This gate is the fast one - under 15 seconds - so that running
it is never the reason someone skips it.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: Enforced strictly. New code and the shared core must stay clean.
BLOCKING_PATHS = ("quant_brain", "tests")

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def _supports_colour() -> bool:
    return sys.stdout.isatty()


def _paint(text: str, colour: str) -> str:
    return f"{colour}{text}{RESET}" if _supports_colour() else text


def _run(cmd: list[str], *, cwd: Path = REPO) -> tuple[int, str]:
    """Run a command, returning (exit code, combined output). Never raises."""
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=900)
    except FileNotFoundError:
        return 127, f"not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, f"timed out: {' '.join(cmd)}"
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, f"failed to run {' '.join(cmd)}: {exc}"
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def changed_python_files() -> list[str]:
    """Python files git reports as modified or untracked, that still exist.

    Staged, unstaged and untracked all count: an agent that has written a file but not staged
    it is exactly the case the gate is for. Deleted paths are filtered out so a removal does
    not make the linter fail on a missing file.
    """
    code, out = _run(["git", "status", "--porcelain"])
    if code != 0:
        return []
    files = []
    for line in out.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip().strip('"')
        if " -> " in path:                      # a rename: lint the destination
            path = path.split(" -> ", 1)[1]
        if path.endswith(".py") and (REPO / path).exists():
            files.append(path)
    return files


class Stage:
    """One gate stage and its result, so the summary can be printed in one place."""

    def __init__(self, name: str, blocking: bool = True):
        self.name, self.blocking = name, blocking
        self.code, self.output, self.seconds = 0, "", 0.0

    @property
    def ok(self) -> bool:
        return self.code == 0

    def line(self) -> str:
        if self.ok:
            mark, colour = "PASS", GREEN
        elif self.blocking:
            mark, colour = "FAIL", RED
        else:
            mark, colour = "WARN", YELLOW
        return f"  {_paint(mark, colour):<6} {self.name:<34} {self.seconds:5.1f}s"


def stage_lint(paths: list[str], *, name: str) -> Stage:
    st = Stage(name)
    if not paths:
        st.output = "nothing to lint"
        return st
    t0 = time.time()
    st.code, st.output = _run([sys.executable, "-m", "ruff", "check", "--output-format=concise",
                               *paths])
    st.seconds = time.time() - t0
    if st.code == 127:
        # Ruff missing is a real gap in the gate, not a pass. Say so loudly.
        st.output = ("ruff is not installed for this interpreter. "
                     "Install it with: py -3.14 -m pip install --no-deps ruff")
    return st


def stage_types() -> Stage:
    """Pyright over quant_brain/ and tests/, per pyrightconfig.json.

    Non-blocking when pyright is absent rather than when it fails: a missing checker is an
    environment gap the operator should see once, not a reason to block every commit on a
    machine that has not installed it. A checker that IS present and reports errors blocks.
    """
    st = Stage("pyright")
    t0 = time.time()
    # `shutil.which` is required, not defensive: npm installs pyright on Windows as a .cmd
    # shim, and subprocess raises FileNotFoundError on the bare name. Without this the gate
    # reports "pyright not installed" on a machine where it is installed and working - a
    # check that silently downgrades itself to a warning is worse than no check.
    exe = shutil.which("pyright")
    st.code, st.output = _run([exe, "--outputjson"]) if exe else (127, "")
    st.seconds = time.time() - t0
    if st.code == 127:
        st.blocking = False
        st.output = ("pyright not installed; install with: npm install -g pyright  "
                     "(npm, not pip - keeps it out of the interpreter the live tasks use)")
        st.code = 1
        return st
    # pyright exits non-zero when it reports errors; summarise rather than dumping the JSON.
    try:
        import json as _json
        summary = _json.loads(st.output).get("summary", {})
        errors = int(summary.get("errorCount", 0))
        warnings = int(summary.get("warningCount", 0))
        st.output = f"{errors} error(s), {warnings} warning(s) over {summary.get('filesAnalyzed')} files"
        st.code = 1 if errors else 0
    except (ValueError, TypeError, KeyError):
        pass                                   # keep the raw output; the exit code stands
    return st


def stage_tests() -> Stage:
    st = Stage("pytest")
    t0 = time.time()
    st.code, st.output = _run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                               "--tb=short"])
    st.seconds = time.time() - t0
    if st.code == 127 or "No module named pytest" in st.output:
        st.code = 1
        st.output = "pytest is not importable by this interpreter - the gate cannot vouch for anything"
    return st


def stage_advisory() -> Stage:
    """Full-repo lint with every suppression lifted. Reports; never fails."""
    st = Stage("legacy debt (advisory)", blocking=False)
    t0 = time.time()
    # `--isolated` is load-bearing: without it ruff still applies ruff.toml's
    # `per-file-ignores`, so a CLI `--select` reports nothing and the advisory tier
    # silently measures zero. That is exactly the kind of gate that looks green and checks
    # nothing, so it is called out here rather than left as a flag.
    st.code, st.output = _run([
        sys.executable, "-m", "ruff", "check", "--isolated", "--statistics", "--no-cache",
        "--target-version", "py311", "--line-length", "100",
        "--select", "E,F,I,UP,B,DTZ,PD,NPY", "--ignore", "UP042",
        "scripts", "algorithms",
    ])
    st.seconds = time.time() - t0
    # A non-zero exit here means findings exist, which is expected and is the point.
    st.code = 0 if st.output else st.code
    return st


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--advisory", action="store_true",
                    help="also report the full-repo legacy debt (never fails the run)")
    ap.add_argument("--changed", action="store_true",
                    help="lint the files git reports as changed, instead of the core paths")
    ap.add_argument("--no-tests", action="store_true", help="skip pytest (lint only)")
    ap.add_argument("--no-types", action="store_true", help="skip pyright")
    ap.add_argument("--quiet", action="store_true", help="summary lines only")
    args = ap.parse_args(argv)

    stages: list[Stage] = []

    if args.changed:
        files = changed_python_files()
        stages.append(stage_lint(files, name=f"ruff ({len(files)} changed file(s))"))
    else:
        stages.append(stage_lint(list(BLOCKING_PATHS), name="ruff (core + tests)"))
        extra = [f for f in changed_python_files()
                 if not f.startswith(("quant_brain/", "tests/"))]
        if extra:
            stages.append(stage_lint(extra, name=f"ruff ({len(extra)} changed elsewhere)"))

    if not args.no_types:
        stages.append(stage_types())

    if not args.no_tests:
        stages.append(stage_tests())

    if args.advisory:
        stages.append(stage_advisory())

    failed = [s for s in stages if not s.ok and s.blocking]

    print()
    print(_paint("  quant-brain completion gate", DIM))
    for st in stages:
        print(st.line())
    print()

    if not args.quiet:
        for st in stages:
            if st.output and (not st.ok or not st.blocking):
                header = f"--- {st.name} ---"
                print(_paint(header, DIM))
                print(st.output.rstrip()[:6000])
                print()

    if failed:
        names = ", ".join(s.name for s in failed)
        print(_paint(f"  GATE FAILED: {names}", RED))
        print(_paint("  Fix these before claiming the change is done.", DIM))
        return 1

    print(_paint("  GATE PASSED", GREEN))
    if any(not s.ok for s in stages):
        print(_paint("  (advisory findings above are informational, not blocking)", DIM))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
