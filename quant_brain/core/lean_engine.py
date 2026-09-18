"""Identify the LEAN engine a backtest actually ran on.

WHY THIS EXISTS
---------------
LEAN is now the sole authoritative backtesting engine in this repository. That makes its
exact version part of every result: an engine upgrade changes fill behaviour, brokerage
models, consolidators and statistics, so two numbers produced by different LEAN builds are
not comparable even when the algorithm and the data are byte-identical. Before this module
the experiment record captured the repository's commit and said nothing about the engine's,
which meant a LEAN rebuild could move every result with no trace in the record.

WHAT IS AND IS NOT PINNED HERE
------------------------------
Recorded: the LEAN source commit, its ``git describe`` build number, the compiled launcher's
size and content hash, the .NET and Python runtimes, the OS, and whether Docker is present.

The launcher hash matters more than it looks. The source commit says which code was checked
out; the launcher hash says which code was actually COMPILED and executed. Those diverge the
moment somebody edits the tree without rebuilding, and it is the binary that produced the
number.

Not pinned: the data. Data has its own manifest and its own hash, because the engine and the
dataset move for different reasons and conflating them makes both untraceable.

THE DOCKER FIELD IS A FINDING, NOT A CONFIGURATION
--------------------------------------------------
The official LEAN CLI workflow (``lean backtest``) runs the engine inside Docker. This
machine has no virtualisation available, so the repository drives the compiled launcher
directly instead. That is not a workaround around LEAN - it is the same engine, run without
the container - but it IS a difference from the documented path and belongs in the record of
every run rather than in a README nobody reads.
"""
from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

#: Where the LEAN checkout lives. Overridable so a second checkout can be pinned explicitly.
DEFAULT_LEAN_ROOT = Path(os.environ.get("LEAN_ROOT", Path(__file__).resolve().parents[3] / "Lean"))


def _run(args: list[str], cwd: Path | None = None) -> str:
    try:
        return subprocess.check_output(
            args, cwd=cwd, text=True, stderr=subprocess.DEVNULL, timeout=30
        ).strip()
    except Exception:
        return ""


def _hash_file(path: Path) -> str:
    if not path.exists():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


@dataclass(frozen=True)
class LeanEngine:
    """Everything needed to say which engine produced a result."""

    lean_root: str
    lean_commit: str
    lean_describe: str
    lean_remote: str
    launcher_path: str
    launcher_exists: bool
    launcher_bytes: int
    launcher_sha256_16: str
    launcher_mtime: str
    dotnet_version: str
    python_version: str
    lean_python_home: str
    os_platform: str
    docker_available: bool
    docker_version: str
    lean_cli_version: str
    data_dir: str
    data_dir_exists: bool

    @property
    def pinned(self) -> bool:
        """True when the engine is identifiable to a specific compiled binary."""
        return bool(self.lean_commit and self.launcher_sha256_16)

    def as_dict(self) -> dict[str, object]:
        return {
            "lean_root": self.lean_root,
            "lean_commit": self.lean_commit,
            "lean_describe": self.lean_describe,
            "lean_remote": self.lean_remote,
            "launcher_path": self.launcher_path,
            "launcher_exists": self.launcher_exists,
            "launcher_bytes": self.launcher_bytes,
            "launcher_sha256_16": self.launcher_sha256_16,
            "launcher_mtime": self.launcher_mtime,
            "dotnet_version": self.dotnet_version,
            "python_version": self.python_version,
            "lean_python_home": self.lean_python_home,
            "os_platform": self.os_platform,
            "docker_available": self.docker_available,
            "docker_version": self.docker_version,
            "lean_cli_version": self.lean_cli_version,
            "data_dir": self.data_dir,
            "data_dir_exists": self.data_dir_exists,
            "pinned": self.pinned,
            #: Stated explicitly so a reader never has to infer it from docker_available.
            "execution_path": (
                "native compiled launcher (no Docker)" if not self.docker_available
                else "native compiled launcher (Docker present but unused)"
            ),
        }


def describe(lean_root: Path | None = None) -> LeanEngine:
    """Interrogate the installed engine. Cheap enough to call on every run."""
    root = Path(lean_root or DEFAULT_LEAN_ROOT)
    default_launcher = root / "Launcher" / "bin" / "Release" / "QuantConnect.Lean.Launcher.exe"
    launcher = Path(os.environ.get("LEAN_LAUNCHER", default_launcher))
    data_dir = Path(os.environ.get("LEAN_DATA", root / "Data"))

    docker_path = shutil.which("docker")
    dotnet_root = Path(os.environ.get("DOTNET_ROOT", ""))
    dotnet_exe = dotnet_root / "dotnet.exe" if dotnet_root.name else Path("dotnet")

    stat = launcher.stat() if launcher.exists() else None

    return LeanEngine(
        lean_root=str(root),
        lean_commit=_run(["git", "rev-parse", "HEAD"], cwd=root),
        lean_describe=_run(["git", "describe", "--tags"], cwd=root),
        lean_remote=_run(["git", "config", "--get", "remote.origin.url"], cwd=root),
        launcher_path=str(launcher),
        launcher_exists=launcher.exists(),
        launcher_bytes=stat.st_size if stat else 0,
        launcher_sha256_16=_hash_file(launcher),
        launcher_mtime=(
            __import__("datetime").datetime.fromtimestamp(
                stat.st_mtime, __import__("datetime").UTC
            ).isoformat()
            if stat
            else ""
        ),
        dotnet_version=_run([str(dotnet_exe), "--version"]),
        python_version=(
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        ),
        lean_python_home=os.environ.get("LEAN_PYTHON_HOME", ""),
        os_platform=platform.platform(),
        docker_available=docker_path is not None,
        docker_version=_run(["docker", "--version"]) if docker_path else "",
        lean_cli_version=_run(["lean", "--version"]) if shutil.which("lean") else "",
        data_dir=str(data_dir),
        data_dir_exists=data_dir.exists(),
    )


class EngineNotPinned(RuntimeError):
    """The engine could not be identified to a specific compiled binary."""


def assert_pinned(engine: LeanEngine | None = None) -> LeanEngine:
    """Refuse to treat a result as reproducible on an unidentifiable engine."""
    resolved = engine or describe()
    if not resolved.launcher_exists:
        raise EngineNotPinned(
            f"no compiled LEAN launcher at {resolved.launcher_path}. Build it first:\n"
            f"  dotnet build {resolved.lean_root}/Launcher/QuantConnect.Lean.Launcher.csproj "
            f"-c Release"
        )
    if not resolved.lean_commit:
        raise EngineNotPinned(
            f"{resolved.lean_root} is not a git checkout, so the engine version cannot be "
            f"recorded. A result from an unidentifiable engine is not reproducible."
        )
    return resolved


__all__ = [
    "DEFAULT_LEAN_ROOT",
    "EngineNotPinned",
    "LeanEngine",
    "assert_pinned",
    "describe",
]
