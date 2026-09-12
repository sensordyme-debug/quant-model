"""Everything needed to reproduce an experiment, captured automatically.

WHY: THE LEDGER CANNOT CURRENTLY TELL TWO ENVIRONMENTS APART
-------------------------------------------------------------
This repository runs two Python interpreters with different major versions of pandas:

    py -3.11   pandas 2.2.3, numpy 2.4.6   - pythonnet host for LEAN, no pyarrow
    py -3.14   pandas 3.0.5, numpy 2.5.3   - the scientific stack, runs BOTH live tasks

Observed on 2026-09-12: `sweep_s32.py --stage b` running on 3.11 and `sweep_a8.py` running
on 3.14, **both appending rows to `research/experiments.jsonl`**. A grep for `version_info`,
`pandas.__version__` or any equivalent guard across scripts/, algorithms/ and tests/ returns
nothing. pandas 3.0 changed copy-on-write, string dtype and resample semantics relative to
2.2, so two rows produced under different interpreters are not necessarily comparable - and
nothing in the ledger records which produced which.

Part 11 asks for exactly this metadata. The important field is `env_key`: a short stable
digest of interpreter and numeric-stack versions, so a comparison across environments is
*detectable* rather than merely discouraged. That mirrors how `evaluate.py` already refuses
to compare across cost models and backtest windows (S-18, F-3) - the same principle, applied
to the environment.

WHAT THIS DOES NOT DO
---------------------
It records; it does not enforce. Refusing a cross-environment comparison belongs in the
promotion gate, which is where the other two axis-mismatch refusals already live.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import os
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

#: Packages whose version can change a numeric result. Deliberately short: recording every
#: installed package makes the fingerprint change on unrelated tooling upgrades, which
#: trains people to ignore it.
NUMERIC_STACK = ("pandas", "numpy", "scipy", "scikit-learn", "pyarrow")


def _module_version(name: str) -> str | None:
    """Version of an installed package without importing it.

    `importlib.metadata` reads the distribution metadata, so asking about pandas does not pay
    pandas' import cost - this runs at the top of every experiment.
    """
    try:
        from importlib.metadata import PackageNotFoundError, version
    except ImportError:                                  # pragma: no cover
        return None
    try:
        return version(name)
    except PackageNotFoundError:
        return None
    except Exception:                                    # pragma: no cover
        return None


def _git(*args: str, repo: Path | None = None) -> str:
    """A git command's stdout, or "" if git is unavailable or the call fails.

    Never raises. Provenance capture must not be able to break an experiment - a run with a
    blank commit is worth more than a crashed run.
    """
    try:
        out = subprocess.run(["git", *args], cwd=str(repo) if repo else None,
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def config_hash(config: object) -> str:
    """Stable 12-hex digest of any JSON-serialisable configuration.

    `sort_keys` so a dict whose insertion order changed does not read as a different
    configuration; `default=str` so dates and Paths do not break the hash.
    """
    blob = json.dumps(config, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:12]


@dataclass(frozen=True)
class Provenance:
    """The reproducibility record for one experiment.

    Every field is optional except the ones that can be captured automatically, so adopting
    this costs a caller one line. Fields the caller alone knows - dataset version, feature
    version, seed - default to empty and should be filled in where they exist.
    """

    # -- captured automatically ------------------------------------------------------------
    experiment_id: str = ""
    ts: str = ""
    git_commit: str = ""
    git_dirty: bool = False
    git_branch: str = ""
    python_version: str = ""
    python_executable: str = ""
    platform: str = ""
    dependencies: dict[str, str] = field(default_factory=dict)

    # -- supplied by the caller --------------------------------------------------------------
    dataset_version: str = ""
    data_timestamp: str = ""
    feature_version: str = ""
    model_version: str = ""
    strategy_version: str = ""
    configuration_hash: str = ""
    random_seed: int | None = None
    notes: str = ""

    @property
    def env_key(self) -> str:
        """Short digest of the things that can change a number.

        Interpreter major.minor plus the numeric stack. Two ledger rows with different
        `env_key` values were produced by different software and should not be compared
        without saying so. Human-readable prefix so it is legible in a table:

            py311-a1b2c3   py314-d4e5f6
        """
        py = ".".join(self.python_version.split(".")[:2]) if self.python_version else "?"
        stack = json.dumps({k: self.dependencies.get(k, "") for k in NUMERIC_STACK},
                           sort_keys=True)
        digest = hashlib.sha256(stack.encode("utf-8")).hexdigest()[:6]
        return f"py{py.replace('.', '')}-{digest}"

    @property
    def reproducible(self) -> bool:
        """Whether this run could actually be reproduced from what was recorded.

        A dirty tree means the code that ran is not the code at that commit, so the honest
        answer is no. Reporting it is the point - `evaluate.py` can then treat a dirty-tree
        candidate as diagnostic rather than promotable, the way it already treats a moved
        backtest window.
        """
        return bool(self.git_commit) and not self.git_dirty

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["env_key"] = self.env_key
        d["reproducible"] = self.reproducible
        return d

    def describe(self) -> str:
        dirty = " (DIRTY TREE)" if self.git_dirty else ""
        return (f"{self.experiment_id or 'run'} @ {self.git_commit[:8] or '????????'}{dirty} "
                f"env={self.env_key} py={self.python_version}")

    @classmethod
    def capture(
        cls,
        *,
        experiment_id: str = "",
        repo: Path | None = None,
        config: object = None,
        dataset_version: str = "",
        data_timestamp: str = "",
        feature_version: str = "",
        model_version: str = "",
        strategy_version: str = "",
        random_seed: int | None = None,
        notes: str = "",
    ) -> Provenance:
        """Gather everything obtainable from the running process. Never raises."""
        repo = repo or Path(__file__).resolve().parents[2]
        commit = _git("rev-parse", "HEAD", repo=repo)
        status = _git("status", "--porcelain", repo=repo)
        branch = _git("rev-parse", "--abbrev-ref", "HEAD", repo=repo)
        deps = {name: v for name in NUMERIC_STACK if (v := _module_version(name))}
        return cls(
            experiment_id=experiment_id,
            ts=dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ"),
            git_commit=commit,
            # Untracked-only changes still count: a sweep script that exists but is not
            # committed is exactly the state most of this repository's experiments run in,
            # and the run genuinely cannot be reproduced from the commit alone.
            git_dirty=bool(status),
            git_branch=branch,
            python_version=platform.python_version(),
            python_executable=sys.executable,
            platform=f"{platform.system()} {platform.release()}",
            dependencies=deps,
            dataset_version=dataset_version,
            data_timestamp=data_timestamp,
            feature_version=feature_version,
            model_version=model_version,
            strategy_version=strategy_version,
            configuration_hash=config_hash(config) if config is not None else "",
            random_seed=random_seed,
            notes=notes,
        )


def env_key_now() -> str:
    """The current interpreter's `env_key`, without a full capture.

    Cheap enough to call from a sweep's argument parser to print which environment a run is
    about to happen in - the one-line version of the F-01 fix.
    """
    deps = {name: (_module_version(name) or "") for name in NUMERIC_STACK}
    py = ".".join(platform.python_version().split(".")[:2])
    digest = hashlib.sha256(json.dumps(deps, sort_keys=True).encode("utf-8")).hexdigest()[:6]
    return f"py{py.replace('.', '')}-{digest}"


def require_interpreter(major: int, minor: int, *, why: str = "") -> None:
    """Refuse to continue on the wrong interpreter.

    The enforcement half of F-01, for entry points that genuinely only work on one: anything
    reading parquet needs 3.14 (3.11 has no pyarrow), and anything hosted by pythonnet needs
    3.11. `AGENTS.md` and two memory files already say this in prose; this makes it fail at
    the top of the script instead of somewhere in the middle with an ImportError.
    """
    got = sys.version_info[:2]
    if got != (major, minor):
        raise RuntimeError(
            f"this entry point requires Python {major}.{minor}, got {got[0]}.{got[1]} "
            f"({sys.executable}){'. ' + why if why else ''}"
        )


def _main(argv: list[str] | None = None) -> int:
    """`python -m quant_brain.core.provenance` - print this environment's record."""
    p = Provenance.capture(experiment_id=os.environ.get("QB_EXPERIMENT_ID", ""))
    print(json.dumps(p.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
