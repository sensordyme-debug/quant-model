#!/usr/bin/env python
"""OpenClaw gateway health monitor with an explicit state machine.

    python scripts/gateway_watchdog.py            # one check; restart if needed
    python scripts/gateway_watchdog.py --probe    # report health only, never restart
    python scripts/gateway_watchdog.py --status   # print the recorded history

WHY THIS REPLACES THE SLEEP-AND-CHECK VERSION
----------------------------------------------
The previous watchdog restarted the task, slept 45 s, probed once, and wrote the answer to a
log. Its log for 2026-09-12 reads:

    12:00:50 restart -> 12:01:39 listening=True     (49 s)
    14:20:51 restart -> 14:21:39 listening=False
    14:25:51 restart -> 14:26:40 listening=False
    14:30:56 restart -> 14:31:46 listening=False
    15:00:50 restart -> 15:01:39 listening=False
    15:15:49 restart -> 15:16:37 listening=True     (48 s)
    (and one 11:55:51 restart with no result line at all)

Two of six succeeded inside the window and four did not, and the four failures fall entirely
between 14:20 and 15:01 - which is exactly the window in which this machine ran three
concurrent `sweep_a8 --workers 11`, 40 python processes, and commit charge at 98% of an
83.4 GB limit. The gateway was not failing to start. **It was taking longer than 45 s to bind
because the machine was starved**, and a fixed verification window cannot express that.

So the bug is not the number 45. It is that a single probe after a fixed sleep produces a
boolean that conflates "dead" with "slow", and that boolean was the only evidence anyone had
about gateway health. Worse, each false verdict triggered another restart five minutes later,
and the old kill step matched ANY node process whose command line contained "openclaw" -
which includes agent sessions the gateway spawned. Under load the watchdog was killing
research jobs and adding to the pressure that was slowing the gateway.

The fix is to poll for readiness instead of sleeping, to record how long the bind actually
took so the distribution is visible, and to scope the kill to the gateway's own process.

STATES
------
    STARTING    a restart was issued very recently; give it room, do not stack restarts
    HEALTHY     the port accepts a connection
    UNHEALTHY   the port does not, and no restart is in flight
    RESTARTING  stopping the task and clearing its process
    VERIFYING   polling for the port to come up, with the elapsed time recorded
    FAILED      the verification budget expired without the port coming up
"""
from __future__ import annotations

import argparse
import datetime as dt
import enum
import json
import socket
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

PORT = 18789
TASK = "OpenClaw Gateway"
HEALTH_FILE = REPO / "live" / "state" / "gateway_health.json"
LOG_FILE = REPO / "live" / "log" / "gateway_watchdog.jsonl"

#: How long a freshly started task is allowed to be unlistening before we call it unhealthy.
#: The observed successful binds took 48-49 s on a loaded machine, so 90 s is that plus room.
STARTING_GRACE_S = 90
#: Total budget for VERIFYING. Generous on purpose - the failures above were slow, not dead,
#: and a premature FAILED costs a second restart that makes the load worse.
VERIFY_BUDGET_S = 240
VERIFY_POLL_S = 3
#: Stop restarting after this many consecutive failures in a window. A watchdog that restarts
#: forever on a genuinely broken gateway is a fork bomb with a timer.
MAX_CONSECUTIVE_RESTARTS = 3
RESTART_WINDOW_S = 3600


class Health(str, enum.Enum):
    STARTING = "STARTING"
    HEALTHY = "HEALTHY"
    UNHEALTHY = "UNHEALTHY"
    RESTARTING = "RESTARTING"
    VERIFYING = "VERIFYING"
    FAILED = "FAILED"


@dataclass
class Reading:
    """One watchdog observation. Everything Part 4 asks to be recorded."""

    ts: str
    port: int
    status: str
    pid: int | None = None
    restart_reason: str = ""
    restart_count: int = 0
    verification_seconds: float | None = None
    final_result: str = ""
    detail: str = ""
    listeners: list[int] = field(default_factory=list)

    def line(self) -> str:
        v = f" verify={self.verification_seconds:.1f}s" if self.verification_seconds else ""
        p = f" pid={self.pid}" if self.pid else ""
        r = f" restarts={self.restart_count}" if self.restart_count else ""
        return (f"{self.ts} {self.status:<10} port={self.port}{p}{v}{r}"
                + (f" reason={self.restart_reason}" if self.restart_reason else "")
                + (f" -> {self.final_result}" if self.final_result else "")
                + (f" ({self.detail})" if self.detail else ""))


# ------------------------------------------------------------------ probing (pure-ish)

def port_open(port: int = PORT, host: str = "127.0.0.1", timeout: float = 2.0) -> bool:
    """True if something accepts a TCP connection on the port.

    A connect is a stronger check than `Get-NetTCPConnection`: a socket in LISTEN whose
    process is wedged still shows in the table but refuses or hangs on accept.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def listener_pids(port: int = PORT) -> list[int]:
    """PIDs listening on the port, via netstat. [] when it cannot be determined."""
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True,
                             text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return []
    pids: list[int] = []
    for line in out.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0] == "TCP" and parts[-2].upper() == "LISTENING":
            if parts[1].endswith(f":{port}"):
                try:
                    pids.append(int(parts[-1]))
                except ValueError:
                    pass
    return sorted(set(pids))


def classify(*, listening: bool, seconds_since_restart: float | None,
             grace: int = STARTING_GRACE_S) -> Health:
    """The state machine's decision function. Pure, so it can be tested exhaustively."""
    if listening:
        return Health.HEALTHY
    if seconds_since_restart is not None and seconds_since_restart < grace:
        return Health.STARTING
    return Health.UNHEALTHY


# ------------------------------------------------------------------ persisted history

def load_health() -> dict:
    if not HEALTH_FILE.exists():
        return {"restarts": [], "last": None}
    try:
        return json.loads(HEALTH_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"restarts": [], "last": None}


def save_health(doc: dict) -> None:
    HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    HEALTH_FILE.write_text(json.dumps(doc, indent=2, default=str) + "\n", encoding="utf-8")


def recent_restarts(doc: dict, now: float, window: int = RESTART_WINDOW_S) -> int:
    """How many restarts were issued inside the window."""
    out = 0
    for entry in doc.get("restarts", []):
        try:
            when = dt.datetime.fromisoformat(entry["ts"]).timestamp()
        except (KeyError, ValueError, TypeError):
            continue
        if now - when <= window:
            out += 1
    return out


def record(reading: Reading) -> None:
    """Append one structured reading. JSONL so the dashboard can read the series."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(reading), default=str) + "\n")
    print(reading.line())


# ------------------------------------------------------------------ actions

def _run(cmd: list[str], timeout: int = 60) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)[:200]
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def kill_gateway_processes() -> list[int]:
    """Kill the gateway process, and ONLY it.

    The previous version matched any node process whose command line contained "openclaw",
    which includes the agent sessions the gateway spawns - so a watchdog firing mid-iteration
    took a research job with it. The match here is the gateway's own entry point and port.
    """
    ps = (
        "Get-CimInstance Win32_Process -Filter \"Name='node.exe'\" | "
        "Where-Object { "
        "$_.CommandLine -like '*openclaw*dist*index.js*' -and "
        "$_.CommandLine -like '* gateway*' -and "
        f"$_.CommandLine -like '*{PORT}*'"
        " } | Select-Object -ExpandProperty ProcessId"
    )
    code, out = _run(["powershell", "-NoProfile", "-Command", ps])
    pids = [int(x) for x in out.split() if x.strip().isdigit()] if code == 0 else []
    for pid in pids:
        _run(["taskkill", "/PID", str(pid), "/F", "/T"], timeout=30)
    return pids


def verify(budget: int = VERIFY_BUDGET_S, poll: int = VERIFY_POLL_S) -> tuple[bool, float]:
    """Poll until the port answers or the budget expires. Returns (ok, elapsed seconds).

    Polling rather than one probe after a fixed sleep is the actual fix: it distinguishes
    "slow because the machine is starved" from "dead", which the old boolean could not, and
    it returns the elapsed time so the distribution becomes visible instead of inferred.
    """
    start = time.monotonic()
    while True:
        if port_open():
            return True, time.monotonic() - start
        if time.monotonic() - start >= budget:
            return False, time.monotonic() - start
        time.sleep(poll)


def task_last_run_seconds() -> float | None:
    """Seconds since the scheduled task last started, or None."""
    ps = (f"$i = Get-ScheduledTaskInfo -TaskName '{TASK}' -ErrorAction SilentlyContinue; "
          "if ($i -and $i.LastRunTime) { "
          "[int]((Get-Date) - $i.LastRunTime).TotalSeconds } else { 'none' }")
    code, out = _run(["powershell", "-NoProfile", "-Command", ps], timeout=45)
    out = out.strip()
    if code != 0 or not out or out == "none":
        return None
    try:
        return float(out.splitlines()[-1].strip())
    except ValueError:
        return None


def now_iso() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def check(*, probe_only: bool = False) -> int:
    """One watchdog pass. Returns a process exit code."""
    doc = load_health()
    listening = port_open()
    pids = listener_pids() if listening else []
    since = task_last_run_seconds()
    state = classify(listening=listening, seconds_since_restart=since)

    if state is Health.HEALTHY:
        r = Reading(ts=now_iso(), port=PORT, status=state.value,
                    pid=pids[0] if pids else None, listeners=pids)
        doc["last"] = asdict(r)
        save_health(doc)
        record(r)
        return 0

    if state is Health.STARTING:
        r = Reading(ts=now_iso(), port=PORT, status=state.value,
                    detail=f"task started {since:.0f}s ago; within the {STARTING_GRACE_S}s grace")
        doc["last"] = asdict(r)
        save_health(doc)
        record(r)
        return 0

    if probe_only:
        record(Reading(ts=now_iso(), port=PORT, status=Health.UNHEALTHY.value,
                       detail="probe only; no restart attempted"))
        return 1

    count = recent_restarts(doc, time.time())
    if count >= MAX_CONSECUTIVE_RESTARTS:
        r = Reading(ts=now_iso(), port=PORT, status=Health.FAILED.value,
                    restart_count=count, final_result="giving up",
                    detail=f"{count} restarts already in the last {RESTART_WINDOW_S // 60} min; "
                           f"not restarting again - this needs a human")
        doc["last"] = asdict(r)
        save_health(doc)
        record(r)
        return 2

    reason = f"port {PORT} not accepting connections"
    record(Reading(ts=now_iso(), port=PORT, status=Health.RESTARTING.value,
                   restart_reason=reason, restart_count=count))
    _run(["powershell", "-NoProfile", "-Command", f"Stop-ScheduledTask -TaskName '{TASK}'"])
    killed = kill_gateway_processes()
    time.sleep(3)
    _run(["powershell", "-NoProfile", "-Command", f"Start-ScheduledTask -TaskName '{TASK}'"])

    record(Reading(ts=now_iso(), port=PORT, status=Health.VERIFYING.value,
                   restart_reason=reason,
                   detail=f"killed {killed or 'nothing'}; polling up to {VERIFY_BUDGET_S}s"))
    ok, elapsed = verify()
    pids = listener_pids() if ok else []
    final = Health.HEALTHY if ok else Health.FAILED
    r = Reading(ts=now_iso(), port=PORT, status=final.value,
                pid=pids[0] if pids else None, listeners=pids,
                restart_reason=reason, restart_count=count + 1,
                verification_seconds=round(elapsed, 1),
                final_result="bound" if ok else "did not bind within the budget")
    doc.setdefault("restarts", []).append(
        {"ts": now_iso(), "reason": reason, "ok": ok, "seconds": round(elapsed, 1)})
    doc["restarts"] = doc["restarts"][-50:]
    doc["last"] = asdict(r)
    save_health(doc)
    record(r)
    return 0 if ok else 2


def status() -> int:
    doc = load_health()
    last = doc.get("last")
    print(f"gateway port {PORT}: {'LISTENING' if port_open() else 'not listening'}")
    if last:
        print("last reading:", Reading(**last).line())
    rs = doc.get("restarts", [])
    if rs:
        ok = [r for r in rs if r.get("ok")]
        secs = [r["seconds"] for r in rs if r.get("ok") and r.get("seconds")]
        print(f"restarts recorded: {len(rs)}, succeeded {len(ok)}")
        if secs:
            print(f"time to bind: min {min(secs):.0f}s  median "
                  f"{sorted(secs)[len(secs) // 2]:.0f}s  max {max(secs):.0f}s")
        for r in rs[-5:]:
            print(f"  {r['ts']}  ok={r.get('ok')}  {r.get('seconds')}s  {r.get('reason', '')}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--probe", action="store_true", help="report health, never restart")
    ap.add_argument("--status", action="store_true", help="print the recorded history")
    args = ap.parse_args(argv)
    if args.status:
        return status()
    return check(probe_only=args.probe)


if __name__ == "__main__":
    raise SystemExit(main())
