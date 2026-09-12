"""Shared fixtures for the runner test suite.

Two jobs:

1. Put `scripts/` on `sys.path` so the runners import as top-level modules, exactly the way
   they import each other at run time (`intraday_trader` does `sys.path.insert` on its own
   directory, so anything else would test a different import graph than the one that runs).

2. **Make it impossible for a test to touch the live account's state.** The runners write
   `live/state/intraday_book.json` (the file the deployed 09:25 trader reads at start-up and
   flattens from), append to `live/log/*.jsonl`, and push chat alerts through the OpenClaw CLI.
   A test that ran the real functions would corrupt the sleeve's book or spam the owner's
   phone, so the `isolate_live` autouse fixture redirects the book to `tmp_path` and replaces
   every logging and alerting entry point with a recorder. Tests that want to see what was
   logged read `log_records` / `alerts`.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
for p in (str(SCRIPTS), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)


@pytest.fixture(autouse=True)
def isolate_live(tmp_path, monkeypatch):
    """Redirect every side effect the runners have on `live/` into the test's tmp dir.

    Returns an object with `.log` (list of (module, kind, fields)) and `.alerts` (list of str)
    so a test can assert on what the runner *would* have recorded.
    """
    import intraday_common
    import intraday_trader
    import paper_trade

    class Sink:
        def __init__(self):
            self.log: list[tuple[str, str, dict]] = []
            self.alerts: list[str] = []

        def kinds(self, module: str | None = None) -> list[str]:
            return [k for m, k, _ in self.log if module is None or m == module]

        def fields(self, kind: str) -> list[dict]:
            return [f for _, k, f in self.log if k == kind]

    sink = Sink()

    def fake_common_log(name, kind, **fields):
        sink.log.append((f"common:{name}", kind, fields))

    def fake_intraday_log(kind, **fields):
        sink.log.append(("intraday", kind, fields))

    def fake_paper_log(kind, **fields):
        sink.log.append(("paper", kind, fields))

    def fake_notify(text, *_a, **_k):
        sink.alerts.append(text)

    # intraday_trader imported log_event/notify into its own namespace; patch there AND at the
    # source, so neither import style leaks a real write.
    monkeypatch.setattr(intraday_common, "log_event", fake_common_log)
    monkeypatch.setattr(intraday_common, "notify", fake_notify)
    monkeypatch.setattr(intraday_trader, "log_event", fake_common_log)
    monkeypatch.setattr(intraday_trader, "log", fake_intraday_log)
    monkeypatch.setattr(intraday_trader, "notify", fake_notify)
    monkeypatch.setattr(intraday_trader, "_notify", fake_notify)
    monkeypatch.setattr(paper_trade, "log_event", fake_paper_log)
    monkeypatch.setattr(paper_trade, "notify", fake_notify)
    monkeypatch.setattr(paper_trade, "record_alert", lambda *a, **k: None)

    # The live book, the halt files and the approval file all move into tmp_path. Nothing
    # under live/ is read or written by a test.
    book = tmp_path / "state" / "intraday_book.json"
    monkeypatch.setattr(intraday_trader, "BOOK_FILE", book)
    monkeypatch.setattr(intraday_trader, "HALT_FILES", [tmp_path / "HALT", tmp_path / "HALT_INTRADAY"])
    monkeypatch.setattr(intraday_trader, "APPROVAL", tmp_path / "APPROVED_PAPER.md")
    monkeypatch.setattr(paper_trade, "APPROVAL", tmp_path / "APPROVED_PAPER.md")
    monkeypatch.setattr(paper_trade, "HALT", tmp_path / "HALT")
    monkeypatch.setattr(paper_trade, "LOG_DIR", tmp_path / "log")
    monkeypatch.setattr(paper_trade, "STATE_DIR", tmp_path / "state")

    yield sink

    # Belt and braces: the real live/ book must be untouched by anything the test did.
    assert not (REPO / "live" / "state" / "intraday_book.json.test").exists()


@pytest.fixture
def sink(isolate_live):
    """Alias so a test can ask for the recorder by name."""
    return isolate_live
