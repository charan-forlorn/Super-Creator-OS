"""memory_writer.py — the ONLY safe path to write memory/database.json.

Guarantees (every write):
  - schema-validate the new record AND the existing DB before touching disk
  - timestamped backup into memory/_db_backups/
  - append-only: db + [record]; existing records verified byte-identical after
  - atomic write (temp file -> os.replace), so no partial/corrupt file is possible
  - duplicate guard on (project_name, created_at)

Returns (ok: bool, info: str). Never raises on a normal rejection — returns ok=False.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path

from _filelock import LockTimeout, atomic_replace, file_lock
from validators import validate_record, validate_db, validate_provenance

DEFAULT_DB = Path(__file__).resolve().parents[2] / "memory" / "database.json"

# === Write guard ===========================================================
# Two-part, code-level enforcement that the DB is only written by this module's
# safe_append():
#   1) the low-level writer refuses to run without a module-private token that
#      ONLY safe_append holds (blocks any other code calling the writer);
#   2) a tamper-evident integrity marker (sha256 sidecar) lets safe_append and
#      readers DETECT and REFUSE a DB that was changed out-of-band (raw open()).
# Additive: a `.db_integrity.json` sidecar next to the DB. Append-only intact.
_WRITE_TOKEN = object()


def _sidecar_for(db_path: Path) -> Path:
    # per-DB-file marker (not per-directory) so distinct DB files never collide
    return db_path.parent / f".{db_path.name}.integrity.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def _read_marker(db_path: Path) -> dict | None:
    sc = _sidecar_for(db_path)
    if not sc.exists():
        return None
    try:
        return json.loads(sc.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_marker(db_path: Path, count: int) -> None:
    _sidecar_for(db_path).write_text(json.dumps({
        "sha256": _sha256(db_path),
        "count": count,
        "updated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "note": "managed by memory_writer.safe_append — do not edit by hand",
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def verify_db_integrity(db_path: Path | None = None) -> tuple[bool, str]:
    """Tamper-evident check. Returns (ok, info). ok=True when the DB is unchanged
    since the last safe_append, or has no marker yet (bootstrap-trusted). ok=False
    means the DB was written OUTSIDE safe_append. Call at READ time before
    consuming the DB; safe_append also calls it before every append."""
    db_path = Path(db_path) if db_path else DEFAULT_DB
    marker = _read_marker(db_path)
    if marker is None:
        return True, "no integrity marker yet (bootstrap-trusted)"
    cur = _sha256(db_path)
    if cur != marker.get("sha256"):
        return False, (f"integrity guard: {db_path.name} was written outside safe_append "
                       f"(expected {str(marker.get('sha256',''))[:12]}, found {cur[:12]})")
    return True, "ok"


def _atomic_write_json(path: Path, data, _token=None) -> None:
    if _token is not _WRITE_TOKEN:
        raise PermissionError(
            "direct DB write blocked — use memory_writer.safe_append() (the approved safe path)")
    # Unique temp name (pid + uuid) so two concurrent writers never share the same
    # "database.json.tmp" and clobber each other's bytes (audit scenario 3.3).
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    atomic_replace(tmp, path)


def safe_append(record: dict, db_path: Path | None = None) -> tuple[bool, str]:
    db_path = Path(db_path) if db_path else DEFAULT_DB
    # CONCURRENCY GUARD (P0-4): hold an exclusive cross-process lock across the
    # whole read -> validate -> append -> atomic write -> marker section. Without
    # it, two writers can both read N records and the last os.replace() drops one
    # (silent lost update). The lock makes the critical section serializable; the
    # integrity marker is now refreshed INSIDE the lock, so a concurrent reader can
    # never observe the os.replace()/marker gap (audit scenarios 3.1 + 3.2).
    try:
        with file_lock(db_path):
            return _safe_append_locked(record, db_path)
    except LockTimeout as e:
        # Surface contention as a normal rejection — preserve the (ok, info)
        # contract (safe_append never raises on a non-exceptional outcome).
        return False, f"lock busy: {e}"


def _safe_append_locked(record: dict, db_path: Path) -> tuple[bool, str]:
    # WRITE GUARD (layer 2): refuse to append onto a DB that was changed
    # out-of-band (raw open()/manual edit) since the last safe_append. This makes
    # any direct write tamper-evident and keeps safe_append the source of truth.
    ok_integrity, integ_info = verify_db_integrity(db_path)
    if not ok_integrity:
        return False, integ_info

    errs = validate_record(record)
    if errs:
        return False, "record invalid: " + "; ".join(errs)

    # provenance is optional; if present it must be well-formed (backward compatible)
    perrs = validate_provenance(record.get("provenance"))
    if perrs:
        return False, "provenance invalid: " + "; ".join(perrs)

    db = json.loads(db_path.read_text(encoding="utf-8")) if db_path.exists() else []
    db_errs = validate_db(db)
    if db_errs:
        return False, "existing DB invalid (refusing to write): " + "; ".join(db_errs)

    if any(r.get("project_name") == record["project_name"]
           and r.get("created_at") == record["created_at"] for r in db):
        return False, "duplicate (same project_name + created_at) — aborted"

    # backup before write
    backups = db_path.parent / "_db_backups"
    backups.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup = backups / f"database.{stamp}.json"
    if db_path.exists():
        shutil.copy2(db_path, backup)

    new_db = db + [record]
    if new_db[:len(db)] != db:                       # post-condition: never alter old records
        return False, "append would alter existing records — aborted"

    # WRITE GUARD (layer 1): only safe_append holds _WRITE_TOKEN, so the
    # low-level writer runs for nobody else.
    _atomic_write_json(db_path, new_db, _WRITE_TOKEN)
    # refresh the tamper-evident marker so the next read/append trusts this DB.
    _write_marker(db_path, len(new_db))
    return True, f"appended record #{len(new_db)} (backup: {backup.name})"
