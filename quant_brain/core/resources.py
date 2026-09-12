"""Machine resources, and how many research workers may safely run.

WHY THIS EXISTS, AND THE MEASUREMENT THAT SHAPED IT
---------------------------------------------------
Two observations a day apart on the same machine:

    2026-09-12 11:2x   sweeps running `--workers 1`.  41.79 GB free, 16 threads idle.
    2026-09-12 later   three concurrent `sweep_a8.py --workers 11`, 40 python processes.
                       Free RAM 35.4 GB - still comfortable - but **commit charge 66.33 GB
                       against a 72.25 GB limit (92%)**, and CPU pinned at 100%.

Nothing arbitrated either state. The second is the dangerous one and it is invisible to the
obvious check: a budget that reads free physical RAM sees 35 GB and happily authorises more
workers, while the machine is in fact five gigabytes from allocation failures. Windows will
fail a commit long before physical memory runs out, because commit accounts for reserved
address space the process has not touched yet.

So the rule this module enforces is that a worker budget is the **minimum** of what physical
memory allows and what the commit limit allows, with headroom on both. Part 20's framing:
the goal is not 100% RAM usage, it is maximum useful utilisation while staying stable.

Deliberately stdlib-only. `psutil` is not installed and adding it would touch the shared
environment two live trading tasks run out of (F-01), for information Windows already
exposes through `GlobalMemoryStatusEx`.
"""
from __future__ import annotations

import ctypes
import dataclasses
import datetime as dt
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

MB = 1024 * 1024
GB = 1024 * MB


class _MemoryStatusEx(ctypes.Structure):
    """Windows MEMORYSTATUSEX. `ullTotalPageFile` is the commit LIMIT, not a pagefile size."""

    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


@dataclass(frozen=True)
class ResourceSnapshot:
    """What the machine looks like right now. All byte counts."""

    total_phys: int
    avail_phys: int
    commit_limit: int
    commit_avail: int
    cpu_count: int
    ts: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))

    @property
    def used_phys(self) -> int:
        return self.total_phys - self.avail_phys

    @property
    def committed(self) -> int:
        return self.commit_limit - self.commit_avail

    @property
    def phys_pct(self) -> float:
        return 100.0 * self.used_phys / self.total_phys if self.total_phys else 0.0

    @property
    def commit_pct(self) -> float:
        """The number that was at 92% while free RAM looked fine. Watch this one."""
        return 100.0 * self.committed / self.commit_limit if self.commit_limit else 0.0

    @property
    def pressure(self) -> str:
        """One word for the dashboard and the launcher log."""
        worst = max(self.phys_pct, self.commit_pct)
        if worst >= 90:
            return "critical"
        if worst >= 80:
            return "high"
        if worst >= 60:
            return "moderate"
        return "low"

    def describe(self) -> str:
        return (
            f"RAM {self.used_phys/GB:.1f}/{self.total_phys/GB:.1f} GB ({self.phys_pct:.0f}%)  "
            f"commit {self.committed/GB:.1f}/{self.commit_limit/GB:.1f} GB "
            f"({self.commit_pct:.0f}%)  cpu {self.cpu_count}  pressure={self.pressure}"
        )


def snapshot() -> ResourceSnapshot:
    """Read the machine's current memory and CPU state.

    Windows goes through GlobalMemoryStatusEx. Elsewhere it falls back to `os.sysconf`, which
    has no commit concept, so commit is reported equal to physical - conservative, since the
    budget takes a minimum and an equal value simply stops the commit leg from binding.
    """
    cpu = os.cpu_count() or 1
    if sys.platform == "win32":
        stat = _MemoryStatusEx()
        stat.dwLength = ctypes.sizeof(_MemoryStatusEx)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            raise OSError("GlobalMemoryStatusEx failed")
        return ResourceSnapshot(
            total_phys=stat.ullTotalPhys, avail_phys=stat.ullAvailPhys,
            commit_limit=stat.ullTotalPageFile, commit_avail=stat.ullAvailPageFile,
            cpu_count=cpu,
        )
    try:
        total = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
        avail = os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError, AttributeError):
        total = avail = 0
    return ResourceSnapshot(total_phys=total, avail_phys=avail, commit_limit=total,
                            commit_avail=avail, cpu_count=cpu)


@dataclass(frozen=True)
class WorkerBudget:
    """How many workers may start, and the honest reason for the number."""

    workers: int
    limited_by: str
    detail: str
    snapshot: ResourceSnapshot

    def __int__(self) -> int:
        return self.workers

    def describe(self) -> str:
        return f"{self.workers} worker(s), limited by {self.limited_by}: {self.detail}"


#: Leave this much physical RAM for the OS, IB Gateway, the dashboard and the two trading
#: runners. Measured baseline for that set was ~4.5 GB (see the audit's RAM strategy); 8 GB
#: is that plus room for a LEAN backtest and an agent session to start while a sweep runs.
DEFAULT_RESERVE_BYTES = 8 * GB
#: Never let a research fan-out push commit past this. 85% leaves the same ~5 GB of commit
#: headroom that the 92% observation had already eaten into.
COMMIT_CEILING_PCT = 85.0
#: Leave cores for the live runners and the agent sessions. On 16 threads this yields 14.
DEFAULT_CPU_RESERVE = 2


def plan_workers(
    per_worker_mb: float,
    *,
    max_workers: int | None = None,
    reserve_bytes: int = DEFAULT_RESERVE_BYTES,
    commit_ceiling_pct: float = COMMIT_CEILING_PCT,
    cpu_reserve: int = DEFAULT_CPU_RESERVE,
    snap: ResourceSnapshot | None = None,
) -> WorkerBudget:
    """The safe worker count for a fan-out whose workers cost `per_worker_mb` each.

    Takes the minimum of three independent limits and names which one bound, because
    "8 workers" without a reason is un-actionable: if CPU is the binding constraint the fix
    is a different machine, and if commit is, the fix is closing Cursor.

    Always returns at least 1. A budget of zero would mean "do no research", which is never
    the right answer to memory pressure - the right answer is one worker and a warning.

    Measured input for the caller: a `sweep_a8` multiprocessing child was observed at
    ~590 MB peak, so `per_worker_mb=600` is the calibrated default for this repository's
    sweeps rather than a guess.
    """
    snap = snap or snapshot()
    per_worker = max(1.0, per_worker_mb) * MB

    # 1) physical memory, after the reserve
    spare_phys = max(0, snap.avail_phys - reserve_bytes)
    by_phys = int(spare_phys // per_worker)

    # 2) commit charge - the leg that the 92% observation showed is the one that actually
    #    binds first on this machine under a heavy fan-out.
    ceiling = snap.commit_limit * (commit_ceiling_pct / 100.0)
    spare_commit = max(0, int(ceiling - snap.committed))
    by_commit = int(spare_commit // per_worker)

    # 3) cores
    by_cpu = max(1, snap.cpu_count - cpu_reserve)

    limits = {"memory": by_phys, "commit": by_commit, "cpu": by_cpu}
    if max_workers is not None:
        limits["requested"] = max_workers
    limited_by = min(limits, key=lambda k: limits[k])
    workers = max(1, min(limits.values()))

    detail = ", ".join(f"{k}={v}" for k, v in limits.items()) + f"; {snap.describe()}"
    return WorkerBudget(workers=workers, limited_by=limited_by, detail=detail, snapshot=snap)


@dataclass
class WorkerRecord:
    """One research worker, as Part 20 asks it to be tracked."""

    worker_id: str
    experiment_id: str
    purpose: str
    pid: int
    started: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    rss_mb: float = 0.0
    cpu_pct: float = 0.0

    @property
    def age_s(self) -> float:
        return (dt.datetime.now(dt.timezone.utc) - self.started).total_seconds()

    def alive(self) -> bool:
        """Whether the PID still exists.

        Part 16's lesson applied to workers: "a scheduled task being Running must not be
        considered proof that the underlying process is healthy". A registry that never
        checks is a list of ghosts.
        """
        if self.pid <= 0:
            return False
        try:
            os.kill(self.pid, 0)          # signal 0 probes without touching the process
        except ProcessLookupError:
            return False
        except PermissionError:
            return True                   # exists, owned by someone else
        except OSError:
            return False
        return True


class ResourceRegistry:
    """A JSON-file registry of live research workers, shared across processes.

    Deliberately a file rather than a daemon. The six research tracks are separate processes
    started by an external scheduler; a daemon would be another thing that can die silently,
    which is the failure mode Part 16 is already trying to fix. A file that every process
    appends to and prunes is enough to answer "what is running and what is it for".

    Not concurrency-perfect: two simultaneous registrations can race. That is acceptable for
    an advisory budget and is documented rather than hidden - a lost record makes the budget
    more conservative, never less.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _read(self) -> list[WorkerRecord]:
        if not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []                     # a corrupt registry must not stop research
        out = []
        for d in raw:
            d = dict(d)
            d["started"] = dt.datetime.fromisoformat(d["started"])
            out.append(WorkerRecord(**d))
        return out

    def _write(self, records: list[WorkerRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = []
        for r in records:
            d = dataclasses.asdict(r)
            d["started"] = r.started.isoformat()
            payload.append(d)
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def register(self, record: WorkerRecord) -> None:
        records = [r for r in self._read() if r.worker_id != record.worker_id]
        records.append(record)
        self._write(records)

    def release(self, worker_id: str) -> None:
        self._write([r for r in self._read() if r.worker_id != worker_id])

    def active(self) -> list[WorkerRecord]:
        """Live workers, after pruning dead PIDs from the file."""
        alive = [r for r in self._read() if r.alive()]
        if len(alive) != len(self._read()):
            self._write(alive)
        return alive

    def orphans(self) -> list[WorkerRecord]:
        """Registered records whose process is gone. Part 20's orphan detection."""
        return [r for r in self._read() if not r.alive()]


def _main(argv: list[str] | None = None) -> int:
    """`python -m quant_brain.core.resources [--per-worker-mb 600]`

    Prints the current snapshot and the budget it implies. Safe to run any time; reads only.
    """
    import argparse

    ap = argparse.ArgumentParser(description="Machine resources and safe worker budget.")
    ap.add_argument("--per-worker-mb", type=float, default=600.0,
                    help="peak RSS per worker (default 600, the measured sweep_a8 child)")
    ap.add_argument("--max-workers", type=int, default=None)
    ap.add_argument("--registry", default=None, help="path to a worker registry JSON")
    args = ap.parse_args(argv)

    snap = snapshot()
    print(snap.describe())
    budget = plan_workers(args.per_worker_mb, max_workers=args.max_workers, snap=snap)
    print(budget.describe())
    if snap.pressure in ("high", "critical"):
        print(f"WARNING: memory pressure is {snap.pressure}; "
              f"commit is the leg to watch, not free RAM.")
    if args.registry:
        reg = ResourceRegistry(args.registry)
        for r in reg.active():
            print(f"  worker {r.worker_id} pid={r.pid} exp={r.experiment_id} "
                  f"{r.purpose} age={r.age_s:.0f}s")
        for r in reg.orphans():
            print(f"  ORPHAN {r.worker_id} pid={r.pid} (process gone)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
