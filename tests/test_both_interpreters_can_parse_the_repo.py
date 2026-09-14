"""Every Python file in this repository must parse on both interpreters.

WHY
---
This repo runs on two Pythons and that is not going to change: the harness is 3.14.7 with
pandas 3.0.5 and pyarrow, and LEAN's embedded interpreter is 3.11.9 with pandas 2.2.3 and no
pyarrow. `scripts/env.ps1` sets up the second; `CLAUDE.md` says so in its first command block.

Syntax added after 3.11 therefore breaks a file for one half of the system while looking fine
in the other, and it does it at import time rather than at a call, so nothing catches it until
something tries to load the module. `scripts/ml_f21.py` carried one for an unknown length of
time:

    print(f"  -> {'the widening beats its own scramble' if a > s else 'THE SCRAMBLE WINS - the '
          'widening is arithmetic, not information'}")

A line break inside an f-string replacement field is 3.12+. On 3.11 that is
`SyntaxError: unterminated string literal`, and `ruff check` reported it repo-wide as
`invalid-syntax` while the file ran perfectly under 3.14. It was found only because a
repo-wide lint was run for an unrelated reason.

WHAT THIS CHECKS
----------------
Parsing, not importing. Importing every module would execute top-level code, need every
dependency present on both interpreters, and be a far larger and more fragile test. Parsing
catches the whole class of syntax-version problems and nothing else, which is exactly the
class that is invisible from inside one interpreter.

The 3.11 half runs as a subprocess because this process is 3.14 and cannot answer the
question. It takes about 2.7 seconds over 285 files.
"""
from __future__ import annotations

import ast
import pathlib
import shutil
import subprocess
import sys
import textwrap

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]

#: The Obsidian vault is user data with its own contents and is not part of this codebase.
#: `.git` and caches are not either.
SKIP_PARTS = ("__pycache__", ".git", "Quant Brain", ".venv", "node_modules")


def _python_files() -> list[pathlib.Path]:
    return [p for p in sorted(REPO.rglob("*.py"))
            if not any(part in SKIP_PARTS for part in p.parts)]


def test_the_repository_has_python_files_to_check():
    """Guard on the guard: a skip pattern that swallowed everything would make the tests
    below pass over an empty list."""
    files = _python_files()
    assert len(files) > 200, f"only found {len(files)} python files; the skip list is wrong"


def test_every_file_parses_on_the_harness_interpreter():
    """3.14, the interpreter running this test."""
    bad = []
    for p in _python_files():
        try:
            ast.parse(p.read_text(encoding="utf-8", errors="replace"), str(p))
        except SyntaxError as exc:
            bad.append(f"{p.relative_to(REPO)}:{exc.lineno} {exc.msg}")
    assert not bad, "files that do not parse on this interpreter:\n  " + "\n  ".join(bad)


@pytest.mark.skipif(shutil.which("py") is None,
                    reason="the py launcher is how 3.11 is reached on this machine")
def test_every_file_parses_on_leans_interpreter():
    """3.11, LEAN's embedded interpreter, as a subprocess.

    A failure here means the file is broken for every LEAN backtest, whether or not it is
    imported today, and the message names the file and line so it is a one-line fix rather
    than a hunt.
    """
    probe = textwrap.dedent("""
        import ast, pathlib, sys
        skip = ("__pycache__", ".git", "Quant Brain", ".venv", "node_modules")
        root = pathlib.Path(sys.argv[1])
        bad = []
        n = 0
        for p in sorted(root.rglob("*.py")):
            if any(part in skip for part in p.parts):
                continue
            n += 1
            try:
                ast.parse(p.read_text(encoding="utf-8", errors="replace"), str(p))
            except SyntaxError as exc:
                bad.append("%s:%s %s" % (p.relative_to(root), exc.lineno, exc.msg))
        print("PARSED", n)
        for b in bad:
            print("BAD", b)
    """)
    res = subprocess.run(["py", "-3.11", "-c", probe, str(REPO)],
                         capture_output=True, text=True, timeout=180)
    if res.returncode != 0:
        pytest.skip(f"3.11 is not available here: {res.stderr.strip()[:200]}")

    lines = res.stdout.splitlines()
    parsed = next((int(x.split()[1]) for x in lines if x.startswith("PARSED")), 0)
    assert parsed > 200, f"3.11 only saw {parsed} files; the probe did not run properly"

    bad = [x[4:] for x in lines if x.startswith("BAD ")]
    assert not bad, (
        "these files parse on 3.14 and NOT on LEAN's 3.11, so they are broken for every "
        "backtest:\n  " + "\n  ".join(bad))


def test_the_two_interpreters_are_the_ones_this_test_claims():
    """If the machine's toolchain moves, the reasoning above stops applying and this should
    be read again rather than silently protecting a different pair of versions."""
    assert sys.version_info[:2] >= (3, 12), (
        f"the harness is {sys.version_info.major}.{sys.version_info.minor}; this test exists "
        f"because the harness is NEWER than LEAN's 3.11 and can therefore accept syntax LEAN "
        f"cannot")
