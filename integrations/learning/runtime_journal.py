"""Safe append-only JSONL journal for local runtime learning records.

This store is for mutable local runtime state, not reviewed canonical memory.
Canonical project records continue to use memory_writer.safe_append() against
memory/database.json. Runtime journal writes are explicit-path friendly for
tests and default to memory/runtime/practice-render.jsonl in production.

Identity formula:
  runtime_record_id = "rt_" + sha256(canonical JSON object containing:
      record_type, engine, project_name, run_id, job_id, project_id,
      platform_family, format_id, render_source_id, attempt_id
  )[:24]

created_at is intentionally excluded so reruns with the same immutable runtime
semantics are idempotent unless an explicit attempt_id changes.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from _filelock import LockTimeout, atomic_replace, file_lock

DEFAULT_RUNTIME_JOURNAL = Path(__file__).resolve().parents[2] / "memory" / "runtime" / "practice-render.jsonl"

IDENTITY_FIELDS = (
    "record_type",
    "engine",
    "project_name",
    "run_id",
    "job_id",
    "project_id",
    "platform_family",
    "format_id",
    "render_source_id",
    "attempt_id",
)

REQUIRED_FIELDS = ("runtime_record_id", "record_type", "engine", "created_at")


def _marker_for(journal_path: Path) -> Path:
    return journal_path.parent / f".{journal_path.name}.integrity.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def derive_runtime_record_id(record: dict[str, Any]) -> str:
    """Derive a deterministic runtime identity from immutable semantic fields.

    The formula deliberately ignores created_at. Repeated runs with identical
    semantics reject as duplicates; distinct retries should set attempt_id.
    """
    if not isinstance(record, dict):
        raise TypeError("record must be an object")

    parts = {field: str(record.get(field) or "").strip() for field in IDENTITY_FIELDS}
    raw = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "rt_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def ensure_runtime_record_id(record: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy with runtime_record_id populated when absent."""
    out = dict(record)
    out.setdefault("runtime_record_id", derive_runtime_record_id(out))
    return out


def validate_runtime_record(record: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    if not isinstance(record, dict):
        return ["record is not an object"]

    for field in REQUIRED_FIELDS:
        if not str(record.get(field) or "").strip():
            errs.append(f"missing/empty field: {field}")

    primary_fields = ("project_name", "run_id", "job_id", "project_id")
    if not any(str(record.get(field) or "").strip() for field in primary_fields):
        errs.append("one of project_name/run_id/job_id/project_id is required")

    if not str(record.get("platform_family") or "").strip():
        errs.append("missing/empty field: platform_family")
    if not str(record.get("format_id") or "").strip():
        errs.append("missing/empty field: format_id")

    expected_id = derive_runtime_record_id(record)
    if record.get("runtime_record_id") != expected_id:
        errs.append("runtime_record_id does not match deterministic identity")

    return errs


def _parse_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    rows: list[dict[str, Any]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"malformed runtime journal line {lineno}: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"malformed runtime journal line {lineno}: row is not an object")
        errs = validate_runtime_record(value)
        if errs:
            raise ValueError(f"malformed runtime journal line {lineno}: {'; '.join(errs)}")
        rows.append(value)
    return rows


def load_runtime_records(journal_path: str | os.PathLike | None = None) -> list[dict[str, Any]]:
    """Read all valid runtime records. Raises on malformed existing lines."""
    path = Path(journal_path) if journal_path else DEFAULT_RUNTIME_JOURNAL
    return _parse_jsonl(path)


def _write_marker(journal_path: Path, count: int) -> None:
    marker = _marker_for(journal_path)
    tmp = marker.with_name(f"{marker.name}.{os.getpid()}.tmp")
    payload = {
        "sha256": _sha256(journal_path),
        "count": count,
        "updated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "note": "managed by runtime_journal.append_runtime_record - do not edit by hand",
    }
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    atomic_replace(tmp, marker)


def verify_runtime_integrity(journal_path: str | os.PathLike | None = None) -> tuple[bool, str]:
    path = Path(journal_path) if journal_path else DEFAULT_RUNTIME_JOURNAL
    marker = _marker_for(path)
    if not marker.exists():
        return True, "no integrity marker yet (bootstrap-trusted)"
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except Exception:
        return False, f"runtime integrity marker unreadable: {marker.name}"
    current = _sha256(path)
    if current != payload.get("sha256"):
        return False, (
            f"runtime integrity guard: {path.name} changed outside append_runtime_record "
            f"(expected {str(payload.get('sha256', ''))[:12]}, found {current[:12]})"
        )
    return True, "ok"


def append_runtime_record(
    record: dict[str, Any],
    journal_path: str | os.PathLike | None = None,
) -> tuple[bool, str]:
    """Append one validated runtime record to JSONL.

    Returns (ok, info), never raises for expected rejections. Existing malformed
    lines fail closed and are never truncated or repaired.
    """
    path = Path(journal_path) if journal_path else DEFAULT_RUNTIME_JOURNAL
    if not isinstance(record, dict):
        return False, "runtime record invalid: record is not an object"
    prepared = ensure_runtime_record_id(record)

    errs = validate_runtime_record(prepared)
    if errs:
        return False, "runtime record invalid: " + "; ".join(errs)

    try:
        with file_lock(path):
            ok_integrity, integrity_info = verify_runtime_integrity(path)
            if not ok_integrity:
                return False, integrity_info

            try:
                existing = _parse_jsonl(path)
            except ValueError as exc:
                return False, str(exc)

            record_id = prepared["runtime_record_id"]
            if any(row.get("runtime_record_id") == record_id for row in existing):
                return False, f"duplicate runtime_record_id {record_id} - aborted"

            line = json.dumps(prepared, ensure_ascii=False, separators=(",", ":")) + "\n"
            with path.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(line)
                fh.flush()
                os.fsync(fh.fileno())

            _write_marker(path, len(existing) + 1)
            return True, f"appended runtime record #{len(existing) + 1} ({record_id})"
    except LockTimeout as exc:
        return False, f"lock busy: {exc}"
