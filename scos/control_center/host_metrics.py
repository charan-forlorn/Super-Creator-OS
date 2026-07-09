"""Local artifact metrics for Stage 6.9 backend observability.

This module reads local files only. It does not inspect live CPU, memory,
processes, sockets, or any OS runtime telemetry.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

HOST_METRICS_SCHEMA_VERSION = 1

_URL_PREFIXES = ("http://", "https://", "ftp://", "ws://", "wss://")
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")


@dataclass(frozen=True)
class ArtifactMetric:
    artifact_id: str
    path: str
    exists: bool
    is_file: bool
    is_dir: bool
    readable: bool
    size_bytes: int
    error_kind: str | None = None
    error_detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "path": self.path,
            "exists": self.exists,
            "is_file": self.is_file,
            "is_dir": self.is_dir,
            "readable": self.readable,
            "size_bytes": self.size_bytes,
            "error_kind": self.error_kind,
            "error_detail": self.error_detail,
        }


@dataclass(frozen=True)
class JsonlMetric:
    artifact: ArtifactMetric
    record_count: int
    malformed_line_count: int
    last_record: dict[str, Any] | None
    records: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact": self.artifact.to_dict(),
            "record_count": self.record_count,
            "malformed_line_count": self.malformed_line_count,
            "last_record": self.last_record,
            "records": list(self.records),
        }


@dataclass(frozen=True)
class SQLiteMetric:
    artifact: ArtifactMetric
    readable: bool
    wal_enabled: bool
    journal_mode: str | None
    table_counts: tuple[tuple[str, int], ...]
    error_kind: str | None = None
    error_detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact": self.artifact.to_dict(),
            "readable": self.readable,
            "wal_enabled": self.wal_enabled,
            "journal_mode": self.journal_mode,
            "table_counts": [[name, count] for name, count in self.table_counts],
            "error_kind": self.error_kind,
            "error_detail": self.error_detail,
        }


def resolve_local_artifact_path(repo_root: Path, artifact_path: Any, label: str) -> Path:
    """Resolve an artifact path inside ``repo_root`` without touching it."""
    raw = str(artifact_path).strip()
    lowered = raw.lower()
    if lowered.startswith(_URL_PREFIXES) or _SCHEME_RE.match(raw):
        raise ValueError(f"URL_PATH_REJECTED: {label} must be a local path")
    root = Path(repo_root).resolve()
    candidate = Path(artifact_path)
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise ValueError(f"PATH_ESCAPE_REJECTED: {label} must resolve inside repo_root") from None
    return resolved


def collect_artifact_metric(repo_root: Path, artifact_path: Any, artifact_id: str) -> ArtifactMetric:
    try:
        resolved = resolve_local_artifact_path(repo_root, artifact_path, artifact_id)
    except ValueError as exc:
        return ArtifactMetric(
            artifact_id=artifact_id,
            path=str(artifact_path),
            exists=False,
            is_file=False,
            is_dir=False,
            readable=False,
            size_bytes=0,
            error_kind=str(exc).split(":", 1)[0],
            error_detail=str(exc),
        )
    exists = resolved.exists()
    is_file = resolved.is_file()
    is_dir = resolved.is_dir()
    size_bytes = 0
    readable = False
    error_kind = None
    error_detail = None
    if exists:
        try:
            stat = resolved.stat()
            size_bytes = int(stat.st_size) if is_file else 0
            if is_file:
                with open(resolved, "rb") as handle:
                    handle.read(0)
            readable = True
        except OSError as exc:
            error_kind = "unreadable_artifact"
            error_detail = type(exc).__name__
    return ArtifactMetric(
        artifact_id=artifact_id,
        path=str(resolved),
        exists=exists,
        is_file=is_file,
        is_dir=is_dir,
        readable=readable,
        size_bytes=size_bytes,
        error_kind=error_kind,
        error_detail=error_detail,
    )


def collect_directory_artifact_count(repo_root: Path, directory_path: Any, artifact_id: str) -> ArtifactMetric:
    metric = collect_artifact_metric(repo_root, directory_path, artifact_id)
    if not metric.exists or not metric.is_dir or not metric.readable:
        return metric
    try:
        count = sum(1 for child in Path(metric.path).rglob("*") if child.is_file())
    except OSError as exc:
        return ArtifactMetric(
            artifact_id=metric.artifact_id,
            path=metric.path,
            exists=metric.exists,
            is_file=metric.is_file,
            is_dir=metric.is_dir,
            readable=False,
            size_bytes=0,
            error_kind="unreadable_artifact",
            error_detail=type(exc).__name__,
        )
    return ArtifactMetric(
        artifact_id=metric.artifact_id,
        path=metric.path,
        exists=metric.exists,
        is_file=metric.is_file,
        is_dir=metric.is_dir,
        readable=metric.readable,
        size_bytes=count,
        error_kind=metric.error_kind,
        error_detail=metric.error_detail,
    )


def collect_jsonl_metric(repo_root: Path, jsonl_path: Any, artifact_id: str) -> JsonlMetric:
    artifact = collect_artifact_metric(repo_root, jsonl_path, artifact_id)
    if not artifact.exists or not artifact.is_file or not artifact.readable:
        return JsonlMetric(artifact=artifact, record_count=0, malformed_line_count=0,
                           last_record=None, records=())
    records: list[dict[str, Any]] = []
    malformed = 0
    try:
        text = Path(artifact.path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        broken = ArtifactMetric(
            artifact_id=artifact.artifact_id,
            path=artifact.path,
            exists=artifact.exists,
            is_file=artifact.is_file,
            is_dir=artifact.is_dir,
            readable=False,
            size_bytes=artifact.size_bytes,
            error_kind="unreadable_artifact",
            error_detail=type(exc).__name__,
        )
        return JsonlMetric(artifact=broken, record_count=0, malformed_line_count=0,
                           last_record=None, records=())
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if isinstance(value, dict):
            records.append(value)
        else:
            malformed += 1
    return JsonlMetric(
        artifact=artifact,
        record_count=len(records),
        malformed_line_count=malformed,
        last_record=records[-1] if records else None,
        records=tuple(records),
    )


def collect_sqlite_metric(
    repo_root: Path,
    db_path: Any,
    artifact_id: str,
    *,
    expected_tables: tuple[str, ...] = (),
) -> SQLiteMetric:
    artifact = collect_artifact_metric(repo_root, db_path, artifact_id)
    if not artifact.exists or not artifact.is_file or not artifact.readable:
        return SQLiteMetric(
            artifact=artifact,
            readable=False,
            wal_enabled=False,
            journal_mode=None,
            table_counts=(),
            error_kind=artifact.error_kind,
            error_detail=artifact.error_detail,
        )
    uri = Path(artifact.path).as_uri() + "?mode=ro"
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(uri, uri=True)
        journal_row = connection.execute("PRAGMA journal_mode").fetchone()
        journal_mode = str(journal_row[0]) if journal_row else "unknown"
        counts: list[tuple[str, int]] = []
        for table in sorted(expected_tables):
            exists = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if exists is None:
                continue
            count_row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            counts.append((table, int(count_row[0]) if count_row else 0))
        return SQLiteMetric(
            artifact=artifact,
            readable=True,
            wal_enabled=journal_mode.lower() == "wal",
            journal_mode=journal_mode,
            table_counts=tuple(counts),
        )
    except sqlite3.Error as exc:
        return SQLiteMetric(
            artifact=artifact,
            readable=False,
            wal_enabled=False,
            journal_mode=None,
            table_counts=(),
            error_kind="sqlite_unreadable",
            error_detail=type(exc).__name__,
        )
    finally:
        if connection is not None:
            connection.close()
