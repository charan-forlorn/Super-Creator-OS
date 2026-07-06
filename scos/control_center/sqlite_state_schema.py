"""SCOS Stage 6.3 SQLite WAL schema for durable Control Center state.

Defines the table/index/PRAGMA statements and path-safety checks used by
``sqlite_state_store.SQLiteStateStore``. This module never opens a database
connection itself -- it only returns SQL text and validates paths.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid,
no network, no server.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

try:
    from .state_models import DurableStateError
except ImportError:  # direct-module execution (tests insert the package dir)
    from state_models import DurableStateError

SQLITE_STATE_SCHEMA_VERSION = 1

DEFAULT_STATE_DB_RELATIVE_PATH = "scos/work/control_center/state/control_center.sqlite3"

_URL_PREFIXES = ("http://", "https://", "ftp://", "ws://", "wss://")
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
# ``pathlib.Path`` collapses "://" to a single separator (e.g.
# "https://example.com" -> "https:\example.com" on Windows), so a caller who
# already wrapped a URL in ``Path`` before calling this function loses the
# double slash. Detect that collapsed form too, restricted to known URL
# scheme names (never a single drive letter like "C:\") so real Windows
# absolute paths are never misidentified as URLs.
_KNOWN_URL_SCHEMES = ("http", "https", "ftp", "ws", "wss")
_COLLAPSED_SCHEME_RE = re.compile(
    r"^(" + "|".join(_KNOWN_URL_SCHEMES) + r"):[\\/]", re.IGNORECASE
)


def get_pragmas() -> tuple[str, ...]:
    return (
        "PRAGMA journal_mode=WAL",
        "PRAGMA synchronous=NORMAL",
        "PRAGMA foreign_keys=ON",
        "PRAGMA busy_timeout=5000",
    )


def get_schema_statements() -> tuple[str, ...]:
    return (
        """
        CREATE TABLE IF NOT EXISTS state_schema (
            schema_name TEXT PRIMARY KEY,
            schema_version INTEGER NOT NULL,
            applied_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS commands (
            command_id TEXT PRIMARY KEY,
            command_type TEXT NOT NULL,
            status TEXT NOT NULL,
            request_id TEXT,
            session_id TEXT,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            metadata_json TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            task_id TEXT,
            agent_id TEXT,
            runtime_id TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            metadata_json TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            source TEXT NOT NULL,
            subject_type TEXT NOT NULL,
            subject_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS approvals (
            approval_id TEXT PRIMARY KEY,
            approval_type TEXT NOT NULL,
            subject_type TEXT NOT NULL,
            subject_id TEXT NOT NULL,
            decision TEXT NOT NULL,
            decided_by TEXT NOT NULL,
            decided_at TEXT NOT NULL,
            reason TEXT,
            metadata_json TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS results (
            result_id TEXT PRIMARY KEY,
            result_type TEXT NOT NULL,
            subject_type TEXT NOT NULL,
            subject_id TEXT NOT NULL,
            verdict TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
        """,
    )


def get_index_statements() -> tuple[str, ...]:
    return (
        "CREATE INDEX IF NOT EXISTS ix_events_subject_sequence "
        "ON events(subject_type, subject_id, sequence)",
        "CREATE INDEX IF NOT EXISTS ix_events_created_at ON events(created_at)",
        "CREATE INDEX IF NOT EXISTS ix_commands_status ON commands(status)",
        "CREATE INDEX IF NOT EXISTS ix_commands_session_id ON commands(session_id)",
        "CREATE INDEX IF NOT EXISTS ix_sessions_status ON sessions(status)",
        "CREATE INDEX IF NOT EXISTS ix_approvals_subject "
        "ON approvals(subject_type, subject_id)",
        "CREATE INDEX IF NOT EXISTS ix_approvals_decision ON approvals(decision)",
        "CREATE INDEX IF NOT EXISTS ix_results_subject "
        "ON results(subject_type, subject_id)",
        "CREATE INDEX IF NOT EXISTS ix_results_verdict ON results(verdict)",
    )


def stable_json_dumps(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _looks_like_url(text: str) -> bool:
    stripped = text.strip()
    lowered = stripped.lower()
    if lowered.startswith(_URL_PREFIXES):
        return True
    if _SCHEME_RE.match(stripped):
        return True
    return bool(_COLLAPSED_SCHEME_RE.match(stripped))


def validate_database_path(repo_root: Path, db_path: Path) -> DurableStateError | None:
    """Return a ``DurableStateError`` if ``db_path`` is unsafe, else ``None``.

    Rejects URL-like paths and any path that would escape ``repo_root`` once
    resolved. Does not touch the filesystem beyond path resolution.
    """

    raw_text = str(db_path)
    if _looks_like_url(raw_text):
        return DurableStateError.of(
            "invalid_path",
            f"db_path must be a local filesystem path, got {raw_text!r}",
        )

    try:
        resolved_root = Path(repo_root).resolve()
        resolved_db = (resolved_root / db_path).resolve() if not db_path.is_absolute() else db_path.resolve()
    except (OSError, ValueError) as exc:
        return DurableStateError.of(
            "invalid_path", f"db_path could not be resolved: {exc}"
        )

    try:
        resolved_db.relative_to(resolved_root)
    except ValueError:
        return DurableStateError.of(
            "invalid_path",
            f"db_path must resolve inside repo_root, got {resolved_db}",
        )

    return None
