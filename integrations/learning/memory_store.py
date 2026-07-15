"""Compatibility adapter for canonical and runtime memory layers.

Default reads are canonical-only to preserve existing behavior. Runtime records
are included only when explicitly requested. Writes are delegated to the owning
safe writer for each layer:

- canonical -> memory_writer.safe_append()
- runtime   -> runtime_journal.append_runtime_record()
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import memory_writer as _canonical_writer
import runtime_journal as _runtime_journal

CANONICAL_ONLY = "canonical"
RUNTIME_ONLY = "runtime"
COMBINED = "combined"

DEFAULT_CANONICAL_DB = _canonical_writer.DEFAULT_DB
DEFAULT_RUNTIME_JOURNAL = _runtime_journal.DEFAULT_RUNTIME_JOURNAL


def _resolve(path: str | os.PathLike | None, default: Path) -> Path:
    return Path(path) if path is not None else default


def _load_canonical(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"canonical memory root is not a JSON array: {path}")
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(data):
        if not isinstance(row, dict):
            raise ValueError(f"canonical memory record {index} is not an object")
        rows.append(row)
    return rows


def _source_copy(record: dict[str, Any], source_layer: str) -> dict[str, Any]:
    out = dict(record)
    out["source_layer"] = source_layer
    return out


def _identity_keys(record: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    runtime_id = str(record.get("runtime_record_id") or "").strip()
    if runtime_id:
        keys.add(f"runtime_record_id:{runtime_id}")

    provenance = record.get("provenance")
    if isinstance(provenance, dict):
        loop_run_id = str(provenance.get("loop_run_id") or "").strip()
        if loop_run_id:
            keys.add(f"loop_run_id:{loop_run_id}")

    project_name = str(record.get("project_name") or "").strip()
    if project_name:
        keys.add(f"project_name:{project_name}")
        created_at = str(record.get("created_at") or "").strip()
        if created_at:
            keys.add(f"project_name_created_at:{project_name}|{created_at}")

    return keys


def read_records(
    *,
    mode: str = CANONICAL_ONLY,
    canonical_path: str | os.PathLike | None = None,
    runtime_path: str | os.PathLike | None = None,
) -> list[dict[str, Any]]:
    """Read records from the requested layer.

    Modes:
    - canonical: default, reads only tracked canonical memory.
    - runtime: explicit runtime-only read.
    - combined: explicit canonical + runtime read. Canonical records win when
      identity keys collide, and every returned record carries source_layer.

    Read operations never create files or directories.
    """
    canonical = _resolve(canonical_path, DEFAULT_CANONICAL_DB)
    runtime = _resolve(runtime_path, DEFAULT_RUNTIME_JOURNAL)

    if mode == CANONICAL_ONLY:
        return list(_load_canonical(canonical))

    if mode == RUNTIME_ONLY:
        return [_source_copy(row, "runtime") for row in _runtime_journal.load_runtime_records(runtime)]

    if mode != COMBINED:
        raise ValueError(f"unknown memory read mode: {mode}")

    canonical_rows = _load_canonical(canonical)
    runtime_rows = _runtime_journal.load_runtime_records(runtime)

    canonical_keys: set[str] = set()
    combined: list[dict[str, Any]] = []
    for row in canonical_rows:
        canonical_keys.update(_identity_keys(row))
        combined.append(_source_copy(row, "canonical"))

    for row in runtime_rows:
        keys = _identity_keys(row)
        if keys and keys & canonical_keys:
            continue
        combined.append(_source_copy(row, "runtime"))

    return combined


def append_canonical_record(
    record: dict[str, Any],
    *,
    canonical_path: str | os.PathLike | None = None,
) -> tuple[bool, str]:
    """Delegate canonical writes to the existing canonical safe path."""
    return _canonical_writer.safe_append(record, _resolve(canonical_path, DEFAULT_CANONICAL_DB))


def append_runtime_record(
    record: dict[str, Any],
    *,
    runtime_path: str | os.PathLike | None = None,
) -> tuple[bool, str]:
    """Delegate runtime writes to the runtime journal safe path."""
    return _runtime_journal.append_runtime_record(record, _resolve(runtime_path, DEFAULT_RUNTIME_JOURNAL))


def append_record(
    record: dict[str, Any],
    *,
    layer: str = CANONICAL_ONLY,
    canonical_path: str | os.PathLike | None = None,
    runtime_path: str | os.PathLike | None = None,
) -> tuple[bool, str]:
    """Append through the writer that owns the selected layer."""
    if layer == CANONICAL_ONLY:
        return append_canonical_record(record, canonical_path=canonical_path)
    if layer == RUNTIME_ONLY:
        return append_runtime_record(record, runtime_path=runtime_path)
    raise ValueError(f"unknown memory write layer: {layer}")
