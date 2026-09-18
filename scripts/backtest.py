#!/usr/bin/env python
"""Run a LEAN backtest natively on Windows (no Docker) and record the result.

Usage:
    python scripts/backtest.py <algorithm>            # algorithms/<algorithm>/main.py
    python scripts/backtest.py <algorithm> --tag "v2 faster rebalance"
    python scripts/backtest.py path/to/file.py --class-name MyAlgo

Results land in results/<algorithm>/<timestamp>/ and a one-line JSON record is
appended to research/experiments.jsonl so the research loop can compare runs.
Exit code 0 means a summary file was produced; the engine's own exit code is
ignored because pythonnet raises a harmless GIL finalizer error on shutdown.
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOME = Path.home()
LEAN_ROOT = Path(os.environ.get("LEAN_ROOT", REPO.parent / "Lean"))
LAUNCHER_DIR = LEAN_ROOT / "Launcher" / "bin" / "Release"
LAUNCHER = LAUNCHER_DIR / "QuantConnect.Lean.Launcher.exe"
DATA_DIR = Path(os.environ.get("LEAN_DATA", LEAN_ROOT / "Data"))
PY_HOME = Path(os.environ.get("LEAN_PYTHON_HOME", HOME / "AppData/Local/Python/pythoncore-3.11-64"))
DOTNET_ROOT = Path(os.environ.get("DOTNET_ROOT", HOME / "AppData/Local/Microsoft/dotnet"))
EXPERIMENTS = REPO / "research" / "experiments.jsonl"

KEY_STATS = [
    "Total Orders", "Net Profit", "Compounding Annual Return", "Sharpe Ratio",
    "Sortino Ratio", "Drawdown", "Win Rate", "Profit-Loss Ratio", "Alpha", "Beta",
    "Annual Standard Deviation", "Information Ratio", "Total Fees", "Start Equity",
    "End Equity", "Probabilistic Sharpe Ratio",
]


def detect_class(main_py: Path) -> str:
    src = main_py.read_text(encoding="utf-8")
    m = re.search(r"^class\s+(\w+)\s*\(\s*QCAlgorithm\s*\)", src, re.M)
    if not m:
        sys.exit(f"could not find a QCAlgorithm subclass in {main_py}")
    return m.group(1)


def git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:
        return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("algorithm", help="directory name under algorithms/ or a path to a .py file")
    ap.add_argument("--class-name", help="QCAlgorithm subclass name (auto-detected by default)")
    ap.add_argument("--tag", default="", help="free-text label stored with the experiment record")
    ap.add_argument("--timeout", type=int, default=3600, help="seconds before the engine is killed")
    ap.add_argument("--quiet", action="store_true", help="hide engine output, print only the summary")
    args = ap.parse_args()

    if args.algorithm.endswith(".py"):
        main_py = Path(args.algorithm).resolve()
        name = main_py.parent.name if main_py.name == "main.py" else main_py.stem
    else:
        name = args.algorithm
        main_py = REPO / "algorithms" / name / "main.py"
    if not main_py.exists():
        sys.exit(f"algorithm file not found: {main_py}")
    for p, what in [(LAUNCHER, "LEAN launcher (build Lean/Launcher first)"), (DATA_DIR, "data folder"),
                    (PY_HOME / "python311.dll", "Python 3.11 DLL")]:
        if not p.exists():
            sys.exit(f"missing {what}: {p}")

    cls = args.class_name or detect_class(main_py)
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = REPO / "results" / name / ts
    run_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PYTHONNET_PYDLL"] = str(PY_HOME / "python311.dll")
    env["PYTHONHOME"] = str(PY_HOME)
    env["PYTHONPATH"] = str(main_py.parent) + os.pathsep + env.get("PYTHONPATH", "")
    env["DOTNET_ROOT"] = str(DOTNET_ROOT)
    env["PATH"] = str(DOTNET_ROOT) + os.pathsep + env.get("PATH", "")
    env["DOTNET_CLI_TELEMETRY_OPTOUT"] = "1"

    cmd = [
        str(LAUNCHER),
        "--algorithm-type-name", cls,
        "--algorithm-language", "Python",
        "--algorithm-location", str(main_py),
        "--data-folder", str(DATA_DIR),
        "--results-destination-folder", str(run_dir),
        "--close-automatically", "true",
    ]
    print(f"[backtest] {name}::{cls}  ->  {run_dir}", flush=True)
    engine_log = run_dir / "engine-output.txt"
    with engine_log.open("w", encoding="utf-8", errors="replace") as log:
        proc = subprocess.Popen(cmd, cwd=LAUNCHER_DIR, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, errors="replace")
        try:
            for line in proc.stdout:
                log.write(line)
                interesting = ("ERROR" in line or "Traceback" in line or "STATISTICS::" in line
                               or "Algorithm Id" in line or line.startswith("Error"))
                if not args.quiet and interesting:
                    print(line.rstrip(), flush=True)
            proc.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            print("[backtest] engine timed out", flush=True)

    summary = run_dir / f"{cls}-summary.json"
    if not summary.exists():
        print(f"[backtest] FAILED: no summary at {summary}. See {engine_log}", flush=True)
        tail = engine_log.read_text(encoding="utf-8", errors="replace").splitlines()[-25:]
        print("\n".join(tail))
        return 1

    stats = json.loads(summary.read_text(encoding="utf-8")).get("statistics", {})
    picked = {k: stats[k] for k in KEY_STATS if k in stats}
    # S-18: record the S1_* overrides the cell was run with. Until now the only description
    # of a cell was its free-text tag, which `evaluate.py` cannot read - and S-17 showed that
    # one of those overrides (`S1_SLIPPAGE_BPS`) decides whether two rows are comparable at
    # all, because a book charged a spread is not measurable against one that is not.
    overrides = {k: v for k, v in sorted(os.environ.items()) if k.startswith("S1_")}
    record = {
        "ts": ts, "algorithm": name, "class": cls, "tag": args.tag, "commit": git_commit(),
        "run_dir": str(run_dir.relative_to(REPO)), "env": overrides, "stats": picked,
    }
    # Provenance. Part 11 of the architecture brief, and the fix for the environment
    # ambiguity: this repository runs LEAN on Python 3.11 (pandas 2.2.3) while everything
    # touching parquet runs on 3.14 (pandas 3.0.5), and both append to THIS file. `env_key`
    # is a short digest of interpreter plus numeric stack - py311-689198 vs py314-5ba485 -
    # so a comparison across environments is detectable rather than merely discouraged.
    # `reproducible` is false on a dirty tree, because the code that ran is then not the
    # code at that commit. Never allowed to break a recorded run.
    try:
        sys.path.insert(0, str(REPO))
        from quant_brain.core.provenance import Provenance
        prov = Provenance.capture(experiment_id=f"{name}::{cls}@{ts}", repo=REPO,
                                  config=overrides, strategy_version=cls)
        record["provenance"] = prov.to_dict()
        record["env_key"] = prov.env_key
        record["reproducible"] = prov.reproducible
    except Exception as exc:  # noqa: BLE001
        record["provenance_error"] = f"{type(exc).__name__}: {exc}"[:200]

    # LEAN is now the sole authoritative backtesting engine, so WHICH LEAN produced a number
    # is part of the number. An engine upgrade moves fills, brokerage models, consolidators
    # and statistics, so two results from different LEAN builds are not comparable even when
    # the algorithm and the data are byte-identical - and until this block existed, a rebuild
    # could move every result with nothing in the record to show it. The launcher hash is the
    # load-bearing field: the commit says what was checked out, the hash says what was
    # actually compiled and run, and those diverge the moment somebody edits without
    # rebuilding. Never allowed to break a recorded run.
    try:
        sys.path.insert(0, str(REPO))
        from quant_brain.core.lean_engine import describe as describe_engine
        record["lean_engine"] = describe_engine().as_dict()
    except Exception as exc:  # noqa: BLE001
        record["lean_engine_error"] = f"{type(exc).__name__}: {exc}"[:200]

    EXPERIMENTS.parent.mkdir(parents=True, exist_ok=True)
    with EXPERIMENTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    width = max(len(k) for k in picked) if picked else 10
    print(f"[backtest] RESULT {name}::{cls} ({ts})")
    for k, v in picked.items():
        print(f"  {k:<{width}}  {v}")
    if record.get("env_key"):
        flag = "" if record.get("reproducible") else "  (DIRTY TREE - not reproducible)"
        print(f"[backtest] env {record['env_key']}{flag}")
    print(f"[backtest] record appended to {EXPERIMENTS.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
