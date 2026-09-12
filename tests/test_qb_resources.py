"""Worker budgeting, and the commit-charge leg that free RAM hides.

The observation these tests encode: on 2026-09-12 this machine showed 34.7 GB of free
physical RAM (55% used, which reads as "plenty") while commit charge sat at 98% of an
83.4 GB limit. A budget that reads free RAM authorises 35 more workers there. The machine
was about two gigabytes from allocation failures.

So the property under test is not "the arithmetic is right" but "the commit leg can bind
while the memory leg is relaxed, and when it does the budget collapses".
"""
from __future__ import annotations

import datetime as dt
import os

from quant_brain.core.resources import (
    GB,
    MB,
    ResourceRegistry,
    ResourceSnapshot,
    WorkerRecord,
    plan_workers,
    snapshot,
)


def snap(*, total=64 * GB, avail=32 * GB, limit=72 * GB, committed=20 * GB, cpu=16):
    return ResourceSnapshot(total_phys=total, avail_phys=avail, commit_limit=limit,
                            commit_avail=limit - committed, cpu_count=cpu)


# ------------------------------------------------------- the failure mode that motivated it

def test_commit_pressure_collapses_the_budget_while_free_ram_looks_healthy():
    """The 2026-09-12 state, reproduced: 55% RAM used, 98% commit."""
    s = snap(total=63 * GB, avail=34 * GB, limit=83 * GB, committed=int(81.5 * GB))
    b = plan_workers(600, snap=s)
    assert b.limited_by == "commit"
    assert b.workers == 1
    assert s.pressure == "critical"


def test_a_free_ram_only_view_would_have_been_badly_wrong():
    """Documents the size of the error the commit leg prevents."""
    s = snap(total=63 * GB, avail=34 * GB, limit=83 * GB, committed=int(81.5 * GB))
    naive = int((s.avail_phys - 8 * GB) // (600 * MB))
    assert naive > 30                       # what free RAM alone would have authorised
    assert plan_workers(600, snap=s).workers == 1


def test_healthy_machine_scales_out_and_says_cpu_is_the_limit():
    """The other half: when nothing is under pressure, fan out to the cores."""
    b = plan_workers(600, snap=snap(avail=48 * GB, committed=10 * GB))
    assert b.workers == 14                  # 16 threads - 2 reserved
    assert b.limited_by == "cpu"


def test_memory_binds_when_workers_are_fat():
    b = plan_workers(4096, snap=snap(avail=20 * GB, committed=10 * GB))
    assert b.limited_by == "memory"
    assert b.workers == 3                   # (20 - 8) GB / 4 GB


def test_explicit_request_is_honoured_as_a_ceiling_not_a_floor():
    b = plan_workers(600, max_workers=4, snap=snap(avail=48 * GB, committed=10 * GB))
    assert b.workers == 4 and b.limited_by == "requested"
    tight = plan_workers(600, max_workers=99,
                         snap=snap(avail=63 * GB, limit=72 * GB, committed=int(71 * GB)))
    assert tight.workers == 1               # asking for 99 does not raise the ceiling


def test_budget_never_returns_zero():
    """Zero would mean 'do no research', which is never the right answer to pressure."""
    b = plan_workers(600, snap=snap(avail=0, limit=72 * GB, committed=72 * GB))
    assert b.workers == 1


def test_reason_is_always_reported_because_a_bare_number_is_unactionable():
    b = plan_workers(600, snap=snap())
    assert b.limited_by in {"memory", "commit", "cpu", "requested"}
    assert "commit=" in b.detail and "cpu=" in b.detail


def test_int_conversion_gives_the_worker_count():
    assert int(plan_workers(600, snap=snap())) >= 1


# ------------------------------------------------------------------------ pressure bands

def test_pressure_bands():
    assert snap(avail=60 * GB, committed=5 * GB).pressure == "low"
    assert snap(total=64 * GB, avail=20 * GB, committed=5 * GB).pressure == "moderate"
    assert snap(total=64 * GB, avail=10 * GB, committed=5 * GB).pressure == "high"
    assert snap(total=64 * GB, avail=2 * GB, committed=5 * GB).pressure == "critical"


def test_pressure_takes_the_worse_of_the_two_legs():
    """Relaxed memory must not mask a critical commit."""
    s = snap(total=64 * GB, avail=60 * GB, limit=72 * GB, committed=int(70 * GB))
    assert s.phys_pct < 10 and s.commit_pct > 95
    assert s.pressure == "critical"


# ----------------------------------------------------------------------- real machine

def test_snapshot_reads_this_machine_without_psutil():
    s = snapshot()
    assert s.total_phys > 0 and s.cpu_count >= 1
    assert 0 <= s.phys_pct <= 100
    assert 0 <= s.commit_pct <= 100
    assert "pressure=" in s.describe()


# --------------------------------------------------------------------------- registry

def test_registry_round_trip(tmp_path):
    reg = ResourceRegistry(tmp_path / "workers.json")
    rec = WorkerRecord(worker_id="w1", experiment_id="F-9", purpose="sweep", pid=os.getpid())
    reg.register(rec)
    active = reg.active()
    assert len(active) == 1 and active[0].experiment_id == "F-9"
    reg.release("w1")
    assert reg.active() == []


def test_registry_detects_orphans(tmp_path):
    """Part 16's lesson: a record is not proof the process is alive."""
    reg = ResourceRegistry(tmp_path / "workers.json")
    reg.register(WorkerRecord(worker_id="ghost", experiment_id="x", purpose="dead",
                              pid=999_999_000))
    assert [r.worker_id for r in reg.orphans()] == ["ghost"]
    assert reg.active() == []               # active() prunes


def test_registering_the_same_id_twice_replaces_rather_than_duplicates(tmp_path):
    reg = ResourceRegistry(tmp_path / "workers.json")
    for purpose in ("first", "second"):
        reg.register(WorkerRecord(worker_id="w", experiment_id="e", purpose=purpose,
                                  pid=os.getpid()))
    assert [r.purpose for r in reg.active()] == ["second"]


def test_corrupt_registry_does_not_stop_research(tmp_path):
    p = tmp_path / "workers.json"
    p.write_text("{not json", encoding="utf-8")
    assert ResourceRegistry(p).active() == []


def test_worker_age_is_measured(tmp_path):
    rec = WorkerRecord(worker_id="w", experiment_id="e", purpose="p", pid=os.getpid(),
                       started=dt.datetime.now(dt.UTC) - dt.timedelta(seconds=30))
    assert 29 <= rec.age_s <= 60
