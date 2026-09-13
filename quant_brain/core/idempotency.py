"""Deterministic intent identity, and a journal that refuses to send the same intent twice.

Phase 10 of the master directive. The failure this prevents is the one that costs the most per
occurrence: a process restarts after submitting, or an API call times out after the venue
accepted it, and the same order goes out again. Neither the strategy nor the venue did
anything wrong; the process simply could not tell that it had already acted.

THE IDENTITY
------------
    intent_id = hash(strategy, account, symbol, session, signal_ts, side, sequence)

Every input is something the STRATEGY knows at the moment it decides - nothing from the venue,
nothing from the clock at submission time. So the same decision produces the same id on the
second run of the same process, on a different machine, and after a restart. That is what
makes "have I already done this?" answerable.

THE JOURNAL
-----------
Append-only JSONL under the same cross-process lock the research ledger uses, because the same
six agent tracks that race on the ledger would race here, and a lost journal row is a duplicate
order. Each intent moves PENDING -> SUBMITTED -> ACKED | FAILED. A restart calls `recover()`,
which returns every intent left in PENDING or SUBMITTED: those are the ones whose outcome is
unknown, and the correct response is to reconcile them against the venue before doing anything
else - not to resend, and not to assume they failed.

WHY THE EXECUTOR REFUSES AN INTENT WITH NO ID
-----------------------------------------------
When a journal is attached, an `OrderIntent` without an `intent_id` is refused. Deduplication
that only applies to orders which happened to be labelled is deduplication that fails on
exactly the code path someone forgot about.
"""
from __future__ import annotations

import datetime as dt
import enum
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from quant_brain.core.locking import file_lock


def intent_id(*, strategy: str, account: str, symbol: str, session: str,
              signal_ts: dt.datetime | str, side: str, sequence: int = 0) -> str:
    """The deterministic identity of one trading decision.

    `signal_ts` is the DECISION time as the strategy saw it, not the submission time. If it is
    a datetime it must be timezone-aware: a naive timestamp hashes differently depending on
    the machine's zone, which would make the same decision look new after a move.
    """
    if isinstance(signal_ts, dt.datetime):
        if signal_ts.tzinfo is None:
            raise ValueError("signal_ts must be timezone-aware; a naive timestamp produces a "
                             "different id on a machine in a different zone")
        ts = signal_ts.astimezone(dt.UTC).isoformat(timespec="seconds")
    else:
        ts = str(signal_ts)
    for name, value in (("strategy", strategy), ("account", account), ("symbol", symbol),
                        ("session", session), ("side", side)):
        if not str(value).strip():
            raise ValueError(f"intent_id needs a non-empty {name}")
    payload = "|".join([strategy, account, symbol, session, ts, side, str(int(sequence))])
    return hashlib.sha256(payload.encode()).hexdigest()[:20]


class IntentState(str, enum.Enum):
    PENDING = "pending"        # decided, not yet sent
    SUBMITTED = "submitted"    # sent; outcome unknown until ACKED or FAILED
    ACKED = "acked"            # the venue confirmed it
    FAILED = "failed"          # the venue refused it, or it was never sent

    @property
    def unresolved(self) -> bool:
        return self in (IntentState.PENDING, IntentState.SUBMITTED)


class Duplicate(RuntimeError):
    """This intent has already been acted on. The order must not go out again."""


@dataclass(frozen=True)
class JournalEntry:
    intent_id: str
    state: IntentState
    when: str
    note: str = ""
    broker_id: str = ""


class IntentJournal:
    """The record of every intent this process has ever acted on."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    # -- reading ---------------------------------------------------------------------------

    def entries(self) -> dict[str, JournalEntry]:
        """Latest entry per intent id. Later rows win, which is how state advances."""
        out: dict[str, JournalEntry] = {}
        if not self.path.exists():
            return out
        for raw in self.path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            try:
                d = json.loads(raw)
                out[d["intent_id"]] = JournalEntry(
                    intent_id=d["intent_id"], state=IntentState(d["state"]),
                    when=d.get("when", ""), note=d.get("note", ""),
                    broker_id=d.get("broker_id", ""))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue    # a torn row must not hide the rest
        return out

    def seen(self, intent_id: str) -> JournalEntry | None:
        return self.entries().get(intent_id)

    def recover(self) -> list[JournalEntry]:
        """Every intent whose outcome is unknown. Reconcile these; never resend them."""
        return [e for e in self.entries().values() if e.state.unresolved]

    # -- writing ---------------------------------------------------------------------------

    def _append(self, entry: JournalEntry) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"intent_id": entry.intent_id, "state": entry.state.value,
                           "when": entry.when, "note": entry.note,
                           "broker_id": entry.broker_id}, sort_keys=True) + "\n"
        with self.path.open("a", encoding="utf-8") as fh:
            if fh.tell() and not _ends_with_newline(self.path):
                # A torn row from a crash mid-write would otherwise swallow this one.
                fh.write("\n")
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())

    def claim(self, intent_id: str, *, note: str = "") -> JournalEntry:
        """Mark an intent PENDING, atomically refusing if it was ever acted on before.

        The check and the write are under one lock, so two processes claiming the same id
        at the same moment cannot both succeed. That is the whole guarantee.
        """
        with file_lock(self.path):
            prior = self.seen(intent_id)
            if prior is not None:
                raise Duplicate(
                    f"intent {intent_id} was already {prior.state.value} at {prior.when}"
                    + (f" ({prior.note})" if prior.note else "")
                    + ". It must not be sent again; if its outcome is unknown, reconcile it "
                      "against the venue.")
            entry = JournalEntry(intent_id, IntentState.PENDING, _now(), note)
            self._append(entry)
            return entry

    def advance(self, intent_id: str, state: IntentState, *, note: str = "",
                broker_id: str = "") -> JournalEntry:
        """Move an intent forward. Refuses to move one that was never claimed."""
        with file_lock(self.path):
            prior = self.seen(intent_id)
            if prior is None:
                raise KeyError(f"intent {intent_id} was never claimed; advance() cannot "
                               f"invent a history for it")
            if prior.state in (IntentState.ACKED, IntentState.FAILED):
                raise Duplicate(f"intent {intent_id} is already terminal "
                                f"({prior.state.value}); nothing may move it")
            entry = JournalEntry(intent_id, state, _now(), note, broker_id)
            self._append(entry)
            return entry


def _ends_with_newline(path: Path) -> bool:
    with path.open("rb") as fh:
        fh.seek(-1, os.SEEK_END)
        return fh.read(1) == b"\n"


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
