"""A cross-process advisory file lock. The one primitive the append-only journals share.

Lifted out of `research/registry.py` when `core/idempotency.py` needed the same guarantee for
the same reason: six agent tracks write to one working tree, and a lost row in the research
ledger is a lost trial while a lost row in the intent journal is a duplicate order. Both are
worse than a ten-millisecond wait.

An exclusive lock FILE rather than a byte-range lock on the target, because readers open the
target separately and a range lock would have to be threaded through every read.
`O_CREAT | O_EXCL` is atomic on every filesystem this runs on, which is the only primitive
needed.

Measured on this machine, without it: eight concurrent records produced three rows with a
read-modify-write, and three rows again with a plain append - Python emulates O_APPEND on
Windows with a seek followed by a write, so the POSIX advice that a small append is atomic
does not transfer here.

A stale lock (an agent killed mid-write) is broken after `timeout` rather than deadlocking
every other track. Losing the lock is recoverable; losing a row is not, so the timeout is
generous.
"""
from __future__ import annotations

import contextlib
import os
import time
from pathlib import Path


@contextlib.contextmanager
def file_lock(path: Path, *, timeout: float = 10.0):
    lock = path.with_suffix(path.suffix + ".lock")
    started = time.monotonic()
    fd = None
    while True:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except (FileExistsError, PermissionError):
            # PermissionError, not just FileExistsError: on Windows a lock file that another
            # thread is in the middle of unlinking sits in a pending-delete state, and
            # O_CREAT|O_EXCL against it raises errno 13 rather than errno 17. Measured here,
            # not anticipated - the first version of this loop caught only FileExistsError
            # and threw under contention.
            waited = time.monotonic() - started
            if waited > timeout:
                # Break it. An agent died holding this, and blocking every other track
                # forever is a worse failure than one racy append.
                try:
                    os.unlink(str(lock))
                except OSError:
                    pass
                started = time.monotonic()
            time.sleep(0.01)
    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
        try:
            os.unlink(str(lock))
        except OSError:
            pass
