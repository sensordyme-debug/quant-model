"""The gateway watchdog's state machine.

The defect this replaces: the old watchdog restarted the task, slept 45 s, probed once, and
wrote a boolean. On 2026-09-12 it logged four failures in a row - all of them between 14:20
and 15:01, which is exactly the window when this machine ran three concurrent
`sweep_a8 --workers 11` with commit charge at 98%. The gateway was not dead, it was slow, and
a single probe after a fixed sleep cannot tell those apart. Two other restarts the same day,
outside that window, succeeded in 48 and 49 seconds.

So what is under test is that the watchdog distinguishes STARTING from UNHEALTHY, records how
long a bind actually took rather than asserting a boolean, and refuses to restart forever.
"""
from __future__ import annotations

import json
import socket

import gateway_watchdog as gw
import pytest

# --------------------------------------------------------------- the classification rule

@pytest.mark.parametrize("listening,since,expected", [
    (True, None, gw.Health.HEALTHY),
    (True, 5.0, gw.Health.HEALTHY),          # listening wins over everything
    (True, 9999.0, gw.Health.HEALTHY),
    (False, 5.0, gw.Health.STARTING),        # just restarted: give it room
    (False, 44.0, gw.Health.STARTING),
    (False, 89.0, gw.Health.STARTING),
    (False, 91.0, gw.Health.UNHEALTHY),      # past the grace and still nothing
    (False, None, gw.Health.UNHEALTHY),      # never started, or unknown
    (False, 9999.0, gw.Health.UNHEALTHY),
])
def test_classify(listening, since, expected):
    assert gw.classify(listening=listening, seconds_since_restart=since) is expected


def test_the_grace_covers_the_observed_bind_times():
    """The two successful restarts on 2026-09-12 took 48 s and 49 s. A grace shorter than
    that is what produced the false failures."""
    for observed in (48.0, 49.0):
        assert gw.classify(listening=False, seconds_since_restart=observed) is gw.Health.STARTING
    assert gw.STARTING_GRACE_S > 49


def test_the_verify_budget_is_far_longer_than_the_old_fixed_sleep():
    """45 s was the number that misreported four healthy restarts as failures."""
    assert gw.VERIFY_BUDGET_S >= 180


# ------------------------------------------------------------------ the circuit breaker

def test_restarts_are_counted_inside_the_window():
    import datetime as dt
    now = dt.datetime.now()
    doc = {"restarts": [
        {"ts": (now - dt.timedelta(minutes=5)).isoformat()},
        {"ts": (now - dt.timedelta(minutes=30)).isoformat()},
        {"ts": (now - dt.timedelta(minutes=200)).isoformat()},   # outside the hour
    ]}
    assert gw.recent_restarts(doc, now.timestamp()) == 2


def test_malformed_restart_entries_do_not_break_the_count():
    assert gw.recent_restarts({"restarts": [{}, {"ts": "nonsense"}, {"ts": None}]},
                              now=1_000_000.0) == 0


def test_a_missing_history_counts_as_no_restarts():
    assert gw.recent_restarts({}, now=1_000_000.0) == 0


def test_the_breaker_refuses_a_fourth_restart(tmp_path, monkeypatch):
    """A watchdog that restarts forever on a genuinely broken gateway is a fork bomb."""
    import datetime as dt
    now = dt.datetime.now()
    health = tmp_path / "gateway_health.json"
    health.write_text(json.dumps({"restarts": [
        {"ts": (now - dt.timedelta(minutes=i)).isoformat()} for i in (5, 10, 15)]}),
        encoding="utf-8")
    monkeypatch.setattr(gw, "HEALTH_FILE", health)
    monkeypatch.setattr(gw, "LOG_FILE", tmp_path / "wd.jsonl")
    monkeypatch.setattr(gw, "port_open", lambda *a, **k: False)
    monkeypatch.setattr(gw, "task_last_run_seconds", lambda: 9999.0)
    called = []
    monkeypatch.setattr(gw, "_run", lambda *a, **k: called.append(a) or (0, ""))

    assert gw.check() == 2
    assert not called, "the breaker must not issue a restart"
    last = json.loads(health.read_text(encoding="utf-8"))["last"]
    assert last["status"] == "FAILED" and "giving up" in last["final_result"]


# ------------------------------------------------------------------ probe-only never acts

def test_probe_only_reports_but_never_restarts(tmp_path, monkeypatch):
    monkeypatch.setattr(gw, "HEALTH_FILE", tmp_path / "h.json")
    monkeypatch.setattr(gw, "LOG_FILE", tmp_path / "wd.jsonl")
    monkeypatch.setattr(gw, "port_open", lambda *a, **k: False)
    monkeypatch.setattr(gw, "task_last_run_seconds", lambda: 9999.0)
    called = []
    monkeypatch.setattr(gw, "_run", lambda *a, **k: called.append(a) or (0, ""))
    assert gw.check(probe_only=True) == 1
    assert not called


def test_a_healthy_gateway_needs_no_action(tmp_path, monkeypatch):
    monkeypatch.setattr(gw, "HEALTH_FILE", tmp_path / "h.json")
    monkeypatch.setattr(gw, "LOG_FILE", tmp_path / "wd.jsonl")
    monkeypatch.setattr(gw, "port_open", lambda *a, **k: True)
    monkeypatch.setattr(gw, "listener_pids", lambda *a, **k: [4242])
    monkeypatch.setattr(gw, "task_last_run_seconds", lambda: 10.0)
    called = []
    monkeypatch.setattr(gw, "_run", lambda *a, **k: called.append(a) or (0, ""))
    assert gw.check() == 0
    assert not called
    last = json.loads((tmp_path / "h.json").read_text(encoding="utf-8"))["last"]
    assert last["status"] == "HEALTHY" and last["pid"] == 4242


def test_a_recently_restarted_gateway_is_left_alone(tmp_path, monkeypatch):
    """The stacking bug: firing every 5 minutes while the last restart is still binding."""
    monkeypatch.setattr(gw, "HEALTH_FILE", tmp_path / "h.json")
    monkeypatch.setattr(gw, "LOG_FILE", tmp_path / "wd.jsonl")
    monkeypatch.setattr(gw, "port_open", lambda *a, **k: False)
    monkeypatch.setattr(gw, "task_last_run_seconds", lambda: 20.0)
    called = []
    monkeypatch.setattr(gw, "_run", lambda *a, **k: called.append(a) or (0, ""))
    assert gw.check() == 0
    assert not called
    last = json.loads((tmp_path / "h.json").read_text(encoding="utf-8"))["last"]
    assert last["status"] == "STARTING"


# ------------------------------------------------------------------ verification records

def test_verify_returns_immediately_when_the_port_is_already_up(monkeypatch):
    monkeypatch.setattr(gw, "port_open", lambda *a, **k: True)
    ok, elapsed = gw.verify(budget=10, poll=1)
    assert ok and elapsed < 1.0


def test_verify_reports_the_elapsed_time_when_it_gives_up(monkeypatch):
    monkeypatch.setattr(gw, "port_open", lambda *a, **k: False)
    ok, elapsed = gw.verify(budget=2, poll=1)
    assert not ok and elapsed >= 2.0


def test_verify_succeeds_on_a_slow_bind(monkeypatch):
    """The 2026-09-12 case: slow, not dead. The old fixed sleep called this a failure."""
    calls = {"n": 0}

    def slow(*_a, **_k):
        calls["n"] += 1
        return calls["n"] >= 3

    monkeypatch.setattr(gw, "port_open", slow)
    ok, elapsed = gw.verify(budget=30, poll=0.01)
    assert ok and calls["n"] == 3 and elapsed >= 0


# ------------------------------------------------------------------ the record itself

def test_every_field_part_4_asks_for_is_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(gw, "LOG_FILE", tmp_path / "wd.jsonl")
    r = gw.Reading(ts="2026-09-12T15:00:00", port=18789, status="HEALTHY", pid=123,
                   restart_reason="port not accepting", restart_count=2,
                   verification_seconds=48.3, final_result="bound")
    gw.record(r)
    rec = json.loads((tmp_path / "wd.jsonl").read_text(encoding="utf-8").strip())
    for field in ("ts", "pid", "port", "status", "restart_reason", "restart_count",
                  "verification_seconds", "final_result"):
        assert field in rec, field
    assert "48.3s" in r.line() and "HEALTHY" in r.line()


def test_history_is_jsonl_so_a_series_can_be_read(tmp_path, monkeypatch):
    monkeypatch.setattr(gw, "LOG_FILE", tmp_path / "wd.jsonl")
    for i in range(3):
        gw.record(gw.Reading(ts=f"t{i}", port=18789, status="HEALTHY"))
    lines = (tmp_path / "wd.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    assert [json.loads(x)["ts"] for x in lines] == ["t0", "t1", "t2"]


def test_a_corrupt_health_file_does_not_stop_the_watchdog(tmp_path, monkeypatch):
    bad = tmp_path / "h.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(gw, "HEALTH_FILE", bad)
    assert gw.load_health() == {"restarts": [], "last": None}


# ------------------------------------------------------------------ the probe is real

def test_port_open_is_a_real_connect_not_a_table_lookup():
    """A socket in LISTEN whose process is wedged still shows in netstat but refuses accept."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
        assert gw.port_open(port=port, timeout=1.0)
    assert not gw.port_open(port=port, timeout=0.5)      # closed again
