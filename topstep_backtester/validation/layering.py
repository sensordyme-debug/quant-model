"""Prove the layer rule and the safety posture by reading the source, not by trusting it.

WHY AST AND NOT GREP
--------------------
The obvious implementation greps for "topstep_backtest" and fails the moment a docstring
mentions the package by name - which every honest docstring in this tree does. A checker
that cries wolf gets an exclusion list, then a bigger one, and then it is not a checker any
more. So imports are found by parsing the module and walking ``Import`` and ``ImportFrom``
nodes: prose is invisible to it, and an import cannot hide from it.

WHAT IS ALLOWED TO IMPORT UPSTREAM
----------------------------------
``topstep_backtester.upstream`` and nothing else. That single exception is what makes the
claim "we did not patch, shadow or override the engine" auditable in one file rather than
across forty.

THE TRANSMISSION SCAN IS TEXTUAL, AND THAT IS DELIBERATE
--------------------------------------------------------
Order transmission and credential handling are checked as TEXT, because the risk is not only
a call - it is a URL in a string, a key name in a dict, a half-written helper. Two files
necessarily contain those tokens: ``safety.py``, which defines the list, and this module,
which consumes it. Both are excluded by name, and the exclusion is a two-entry constant
rather than a growing list, because a third file needing an exemption would itself be the
finding.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from topstep_backtester.safety import (
    FORBIDDEN_CALL_TOKENS,
    FORBIDDEN_MODULE_PREFIXES,
)

#: The upstream distribution, as it appears in an import statement.
UPSTREAM_ROOT = "topstep_backtest"

#: The one module permitted to import it.
SEAM_MODULE = "upstream.py"

#: Files that legitimately contain the forbidden tokens because they define or consume the
#: list itself. Deliberately tiny - a growth in this tuple is a finding, not a fix.
_TOKEN_SCAN_EXEMPT: frozenset[str] = frozenset({"safety.py", "validation/layering.py"})


@dataclass(frozen=True)
class Finding:
    module: str
    line: int
    detail: str

    def __str__(self) -> str:
        return f"{self.module}:{self.line}: {self.detail}"


def package_root() -> Path:
    return Path(__file__).resolve().parent.parent


def source_files(root: Path | None = None) -> list[Path]:
    """Every Python file in this package, tests included."""
    base = root or package_root()
    return sorted(
        path
        for path in base.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def _relative(path: Path, base: Path) -> str:
    return path.relative_to(base).as_posix()


def _imported_roots(tree: ast.AST) -> list[tuple[int, str]]:
    """Every top-level package name imported, with the line it was imported on."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((node.lineno, alias.name.split(".")[0]))
        elif isinstance(node, ast.ImportFrom):
            #: A relative import has no module root to check.
            if node.level == 0 and node.module:
                found.append((node.lineno, node.module.split(".")[0]))
    return found


def scan_upstream_imports(root: Path | None = None) -> list[Finding]:
    """Any module other than the seam that imports the engine directly."""
    base = root or package_root()
    findings: list[Finding] = []
    for path in source_files(base):
        relative = _relative(path, base)
        if relative == SEAM_MODULE:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:  # pragma: no cover - a syntax error fails the suite anyway
            findings.append(Finding(relative, exc.lineno or 0, f"could not parse: {exc.msg}"))
            continue
        for line, name in _imported_roots(tree):
            if name == UPSTREAM_ROOT:
                findings.append(
                    Finding(
                        relative,
                        line,
                        f"imports {UPSTREAM_ROOT} directly. Every upstream name must come "
                        f"through topstep_backtester.upstream, which is what makes the "
                        f"layer boundary checkable.",
                    )
                )
    return findings


def scan_forbidden_imports(root: Path | None = None) -> list[Finding]:
    """Any import of a live-trading or broker SDK."""
    base = root or package_root()
    findings: list[Finding] = []
    for path in source_files(base):
        relative = _relative(path, base)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:  # pragma: no cover
            continue
        for line, name in _imported_roots(tree):
            if name in FORBIDDEN_MODULE_PREFIXES:
                findings.append(
                    Finding(
                        relative,
                        line,
                        f"imports {name!r}, a live-path module. This pipeline is historical "
                        f"only and has no reason to reach a broker.",
                    )
                )
    return findings


def scan_for_transmission(root: Path | None = None) -> list[Finding]:
    """Any token that only appears in code that sends something to a venue."""
    base = root or package_root()
    findings: list[Finding] = []
    for path in source_files(base):
        relative = _relative(path, base)
        if relative in _TOKEN_SCAN_EXEMPT:
            continue
        for number, text in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            for token in FORBIDDEN_CALL_TOKENS:
                if token in text:
                    findings.append(
                        Finding(
                            relative,
                            number,
                            f"contains {token!r}. The research pipeline transmits nothing "
                            f"and holds no credentials.",
                        )
                    )
    return findings


def audit(root: Path | None = None) -> dict[str, list[Finding]]:
    """Every layering and safety check, in one call."""
    return {
        "upstream_imports_outside_seam": scan_upstream_imports(root),
        "forbidden_live_imports": scan_forbidden_imports(root),
        "transmission_tokens": scan_for_transmission(root),
    }


def assert_clean(root: Path | None = None) -> None:
    """Raise with every finding listed, or return silently."""
    results = audit(root)
    problems = {name: found for name, found in results.items() if found}
    if problems:
        lines = []
        for name, found in problems.items():
            lines.append(f"{name}:")
            lines.extend(f"    {finding}" for finding in found)
        raise AssertionError("layering audit failed\n" + "\n".join(lines))


__all__ = [
    "SEAM_MODULE",
    "UPSTREAM_ROOT",
    "Finding",
    "assert_clean",
    "audit",
    "package_root",
    "scan_for_transmission",
    "scan_forbidden_imports",
    "scan_upstream_imports",
    "source_files",
]
