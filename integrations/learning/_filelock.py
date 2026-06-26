"""_filelock.py — minimal cross-platform advisory file lock (stdlib only).

Closes the lost-update race documented in memory_concurrency_audit.md (scenario
3.1): it serializes the read -> validate -> modify -> write -> integrity-marker
critical section of the JSON memory stores so two concurrent writers can no longer
both read the same array and have the last os.replace() silently drop a record.

Design (matches the audit's Option A "stdlib platform shim" recommendation):
  - Windows -> msvcrt.locking  (LK_NBLCK poll loop + timeout)
  - POSIX   -> fcntl.flock     (LOCK_EX | LOCK_NB poll loop + timeout)
  - NO third-party dependency, so the stdlib-only learning spine invariant holds.

The lock is taken on a DEDICATED sidecar file (e.g. ".database.json.lock"), never
on the data file itself, so os.replace() on the data file is unaffected by the held
lock handle (important on Windows, where replacing an open file can fail).

Advisory, not mandatory: this only excludes writers that also acquire the lock.
Every in-repo writer (memory_writer.safe_append, telemetry.append_telemetry,
anchor_library.record_project_anchors) now routes through it, which covers all of
them. On both platforms the OS drops the lock when the handle closes — including on
process death — so a crash does not leave a permanently stale lock.
"""

from __future__ import annotations

import contextlib
import os
import time
from pathlib import Path

_POLL_S = 0.05  # how often to retry a contended lock


class LockTimeout(TimeoutError):
    """Raised internally when the lock can't be acquired within the timeout.

    Writers catch this and convert it to their normal (ok=False, info) return so
    the existing API contract ('never raises on a normal outcome') is preserved.
    """


def lock_path_for(target: str | os.PathLike) -> Path:
    """Sidecar lock path for a data file: memory/db.json -> memory/.db.json.lock."""
    target = Path(target)
    return target.parent / f".{target.name}.lock"


def atomic_replace(src: str | os.PathLike, dst: str | os.PathLike,
                   attempts: int = 25, delay: float = 0.02) -> None:
    """os.replace(src, dst) with a bounded retry on transient Windows failures.

    On Windows, MoveFileEx can briefly return ERROR_ACCESS_DENIED / ERROR_SHARING_
    VIOLATION when an antivirus scanner, the search indexer, or a just-closed handle
    momentarily holds the destination — even when our own file lock guarantees no
    logical concurrent writer. This is a transient OS condition, not a correctness
    problem, so a short retry (default ~0.5s budget) absorbs it. On POSIX, os.replace
    is atomic and effectively never hits this path, so the first attempt succeeds.
    """
    last: OSError | None = None
    for _ in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError as e:        # WinError 5 (access) / 32 (sharing)
            last = e
            time.sleep(delay)
    raise last if last is not None else RuntimeError("atomic_replace failed")


if os.name == "nt":
    import msvcrt

    def _try_acquire(fh) -> bool:
        try:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)  # non-blocking, 1 byte
            return True
        except OSError:
            return False

    def _release(fh) -> None:
        try:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
else:
    import fcntl

    def _try_acquire(fh) -> bool:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def _release(fh) -> None:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass


@contextlib.contextmanager
def file_lock(target: str | os.PathLike, timeout: float = 10.0):
    """Exclusive advisory lock guarding the data file `target`.

    Polls until acquired or `timeout` seconds elapse, then raises LockTimeout.
    Held on a sibling ".<name>.lock" file for the duration of the with-block.
    """
    lp = lock_path_for(target)
    lp.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lp, "a+")                       # create + keep open for the lock's life
    try:
        start = time.monotonic()
        while not _try_acquire(fh):
            if time.monotonic() - start >= timeout:
                raise LockTimeout(
                    f"could not acquire lock {lp.name} within {timeout}s (writer busy)")
            time.sleep(_POLL_S)
        try:
            yield
        finally:
            _release(fh)
    finally:
        fh.close()
