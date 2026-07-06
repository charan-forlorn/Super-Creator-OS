"""SCOS Stage 6.3 SQLite WAL-backed durable Control Center state store.

Wraps ``sqlite3`` (stdlib only, no ORM) to persist and read back durable
command/session/event/approval/result records for the Control Center. WAL
mode is enabled on every connection. All queries are parameterized; no
caller-supplied value is ever concatenated into SQL text.

This module never starts a server, opens a network port, dispatches real AI
work, or executes arbitrary commands -- it only reads/writes rows in a local
SQLite file.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid,
no network, no server.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

try:
    from .state_models import (
        ALLOWED_COMMAND_STATUSES,
        ALLOWED_SESSION_STATUSES,
        DurableCommandRecord,
        DurableEventRecord,
        DurableApprovalRecord,
        DurableResultRecord,
        DurableSessionRecord,
        DurableStateError,
    )
    from .sqlite_state_schema import (
        DEFAULT_STATE_DB_RELATIVE_PATH,
        SQLITE_STATE_SCHEMA_VERSION,
        get_index_statements,
        get_pragmas,
        get_schema_statements,
        stable_json_dumps,
        validate_database_path,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from state_models import (
        ALLOWED_COMMAND_STATUSES,
        ALLOWED_SESSION_STATUSES,
        DurableCommandRecord,
        DurableEventRecord,
        DurableApprovalRecord,
        DurableResultRecord,
        DurableSessionRecord,
        DurableStateError,
    )
    from sqlite_state_schema import (
        DEFAULT_STATE_DB_RELATIVE_PATH,
        SQLITE_STATE_SCHEMA_VERSION,
        get_index_statements,
        get_pragmas,
        get_schema_statements,
        stable_json_dumps,
        validate_database_path,
    )

_STATE_SCHEMA_NAME = "control_center_state"


def _row_to_command(row: sqlite3.Row) -> DurableCommandRecord:
    return DurableCommandRecord.of(
        row["command_id"],
        row["command_type"],
        row["status"],
        row["created_at"],
        request_id=row["request_id"],
        session_id=row["session_id"],
        payload_json=row["payload_json"],
        updated_at=row["updated_at"],
        metadata=_load_metadata(row["metadata_json"]),
    )


def _row_to_session(row: sqlite3.Row) -> DurableSessionRecord:
    return DurableSessionRecord.of(
        row["session_id"],
        row["status"],
        row["created_at"],
        task_id=row["task_id"],
        agent_id=row["agent_id"],
        runtime_id=row["runtime_id"],
        updated_at=row["updated_at"],
        metadata=_load_metadata(row["metadata_json"]),
    )


def _row_to_event(row: sqlite3.Row) -> DurableEventRecord:
    return DurableEventRecord.of(
        row["event_id"],
        row["event_type"],
        row["source"],
        row["subject_type"],
        row["subject_id"],
        row["created_at"],
        row["sequence"],
        payload_json=row["payload_json"],
        metadata=_load_metadata(row["metadata_json"]),
    )


def _row_to_approval(row: sqlite3.Row) -> DurableApprovalRecord:
    return DurableApprovalRecord.of(
        row["approval_id"],
        row["approval_type"],
        row["subject_type"],
        row["subject_id"],
        row["decision"],
        row["decided_by"],
        row["decided_at"],
        reason=row["reason"],
        metadata=_load_metadata(row["metadata_json"]),
    )


def _row_to_result(row: sqlite3.Row) -> DurableResultRecord:
    return DurableResultRecord.of(
        row["result_id"],
        row["result_type"],
        row["subject_type"],
        row["subject_id"],
        row["verdict"],
        row["created_at"],
        payload_json=row["payload_json"],
        metadata=_load_metadata(row["metadata_json"]),
    )


def _load_metadata(metadata_json: str) -> dict[str, str]:
    import json

    if not metadata_json:
        return {}
    try:
        parsed = json.loads(metadata_json)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


class SQLiteStateStore:
    """SQLite WAL-backed durable state store rooted at ``repo_root``.

    ``db_path`` may be relative (resolved against ``repo_root``) or absolute,
    but must always resolve inside ``repo_root``. The database file and its
    parent directory are created lazily by :meth:`initialize`.
    """

    def __init__(self, *, repo_root: Path, db_path: Path | None = None) -> None:
        self._repo_root = Path(repo_root)
        self._db_path = Path(db_path) if db_path is not None else Path(
            DEFAULT_STATE_DB_RELATIVE_PATH
        )
        path_error = validate_database_path(self._repo_root, self._db_path)
        if path_error is not None:
            raise ValueError(
                f"{path_error.error_kind}: {path_error.error_detail}"
            )
        self._resolved_db_path = (
            self._db_path
            if self._db_path.is_absolute()
            else (self._repo_root / self._db_path)
        )

    @property
    def db_path(self) -> Path:
        return self._resolved_db_path

    def _connect(self) -> sqlite3.Connection:
        self._resolved_db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self._resolved_db_path))
        connection.row_factory = sqlite3.Row
        for pragma in get_pragmas():
            connection.execute(pragma)
        return connection

    def initialize(
        self, *, applied_at: str, metadata: dict | None = None
    ) -> DurableStateError | None:
        try:
            connection = self._connect()
        except sqlite3.Error as exc:
            return DurableStateError.of("storage_unavailable", str(exc))

        try:
            with connection:
                for statement in get_schema_statements():
                    connection.execute(statement)
                for statement in get_index_statements():
                    connection.execute(statement)
                connection.execute(
                    """
                    INSERT INTO state_schema
                        (schema_name, schema_version, applied_at, metadata_json)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(schema_name) DO UPDATE SET
                        schema_version = excluded.schema_version,
                        applied_at = excluded.applied_at,
                        metadata_json = excluded.metadata_json
                    """,
                    (
                        _STATE_SCHEMA_NAME,
                        SQLITE_STATE_SCHEMA_VERSION,
                        applied_at,
                        stable_json_dumps(metadata or {}),
                    ),
                )
        except sqlite3.Error as exc:
            return DurableStateError.of("storage_unavailable", str(exc))
        finally:
            connection.close()
        return None

    def health_snapshot(self, *, checked_at: str) -> dict:
        try:
            connection = self._connect()
        except sqlite3.Error as exc:
            return {
                "ok": False,
                "checked_at": checked_at,
                "db_mode": "unavailable",
                "wal_enabled": False,
                "error_detail": str(exc),
            }

        try:
            journal_mode_row = connection.execute("PRAGMA journal_mode").fetchone()
            journal_mode = str(journal_mode_row[0]) if journal_mode_row else "unknown"
            schema_row = connection.execute(
                "SELECT schema_version, applied_at FROM state_schema "
                "WHERE schema_name = ?",
                (_STATE_SCHEMA_NAME,),
            ).fetchone()
            return {
                "ok": True,
                "checked_at": checked_at,
                "db_mode": journal_mode,
                "wal_enabled": journal_mode.lower() == "wal",
                "schema_version": schema_row["schema_version"] if schema_row else None,
                "schema_applied_at": schema_row["applied_at"] if schema_row else None,
                "db_path": str(self._resolved_db_path),
            }
        except sqlite3.Error as exc:
            return {
                "ok": False,
                "checked_at": checked_at,
                "db_mode": "unavailable",
                "wal_enabled": False,
                "error_detail": str(exc),
            }
        finally:
            connection.close()

    # ---- commands ------------------------------------------------------

    def insert_command(
        self, record: DurableCommandRecord
    ) -> DurableCommandRecord | DurableStateError:
        if not isinstance(record, DurableCommandRecord):
            return DurableStateError.of(
                "invalid_payload", "record must be a DurableCommandRecord"
            )
        if record.status not in ALLOWED_COMMAND_STATUSES:
            return DurableStateError.of(
                "invalid_status", f"invalid command status: {record.status!r}"
            )
        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO commands
                        (command_id, command_type, status, request_id,
                         session_id, payload_json, created_at, updated_at,
                         metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.command_id,
                        record.command_type,
                        record.status,
                        record.request_id,
                        record.session_id,
                        record.payload_json,
                        record.created_at,
                        record.updated_at,
                        stable_json_dumps(dict(record.metadata)),
                    ),
                )
        except sqlite3.IntegrityError:
            return DurableStateError.of(
                "duplicate_id", f"command_id already exists: {record.command_id!r}"
            )
        except sqlite3.Error as exc:
            return DurableStateError.of("storage_unavailable", str(exc))
        finally:
            connection.close()
        return record

    def get_command(self, command_id: str) -> DurableCommandRecord | DurableStateError:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM commands WHERE command_id = ?", (command_id,)
            ).fetchone()
        except sqlite3.Error as exc:
            return DurableStateError.of("storage_unavailable", str(exc))
        finally:
            connection.close()
        if row is None:
            return DurableStateError.of(
                "not_found", f"command not found: {command_id!r}"
            )
        return _row_to_command(row)

    def list_commands(
        self, status: str | None = None
    ) -> tuple[DurableCommandRecord, ...]:
        connection = self._connect()
        try:
            if status is None:
                rows = connection.execute(
                    "SELECT * FROM commands ORDER BY created_at ASC, command_id ASC"
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM commands WHERE status = ? "
                    "ORDER BY created_at ASC, command_id ASC",
                    (status,),
                ).fetchall()
        finally:
            connection.close()
        return tuple(_row_to_command(row) for row in rows)

    # ---- sessions --------------------------------------------------------

    def insert_session(
        self, record: DurableSessionRecord
    ) -> DurableSessionRecord | DurableStateError:
        if not isinstance(record, DurableSessionRecord):
            return DurableStateError.of(
                "invalid_payload", "record must be a DurableSessionRecord"
            )
        if record.status not in ALLOWED_SESSION_STATUSES:
            return DurableStateError.of(
                "invalid_status", f"invalid session status: {record.status!r}"
            )
        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO sessions
                        (session_id, task_id, agent_id, runtime_id, status,
                         created_at, updated_at, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.session_id,
                        record.task_id,
                        record.agent_id,
                        record.runtime_id,
                        record.status,
                        record.created_at,
                        record.updated_at,
                        stable_json_dumps(dict(record.metadata)),
                    ),
                )
        except sqlite3.IntegrityError:
            return DurableStateError.of(
                "duplicate_id", f"session_id already exists: {record.session_id!r}"
            )
        except sqlite3.Error as exc:
            return DurableStateError.of("storage_unavailable", str(exc))
        finally:
            connection.close()
        return record

    def get_session(self, session_id: str) -> DurableSessionRecord | DurableStateError:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        except sqlite3.Error as exc:
            return DurableStateError.of("storage_unavailable", str(exc))
        finally:
            connection.close()
        if row is None:
            return DurableStateError.of(
                "not_found", f"session not found: {session_id!r}"
            )
        return _row_to_session(row)

    def list_sessions(
        self, status: str | None = None
    ) -> tuple[DurableSessionRecord, ...]:
        connection = self._connect()
        try:
            if status is None:
                rows = connection.execute(
                    "SELECT * FROM sessions ORDER BY created_at ASC, session_id ASC"
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM sessions WHERE status = ? "
                    "ORDER BY created_at ASC, session_id ASC",
                    (status,),
                ).fetchall()
        finally:
            connection.close()
        return tuple(_row_to_session(row) for row in rows)

    # ---- events ------------------------------------------------------

    def append_event(
        self, record: DurableEventRecord
    ) -> DurableEventRecord | DurableStateError:
        if not isinstance(record, DurableEventRecord):
            return DurableStateError.of(
                "invalid_payload", "record must be a DurableEventRecord"
            )
        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO events
                        (event_id, event_type, source, subject_type, subject_id,
                         payload_json, created_at, sequence, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.event_id,
                        record.event_type,
                        record.source,
                        record.subject_type,
                        record.subject_id,
                        record.payload_json,
                        record.created_at,
                        record.sequence,
                        stable_json_dumps(dict(record.metadata)),
                    ),
                )
        except sqlite3.IntegrityError:
            return DurableStateError.of(
                "duplicate_id", f"event_id already exists: {record.event_id!r}"
            )
        except sqlite3.Error as exc:
            return DurableStateError.of("storage_unavailable", str(exc))
        finally:
            connection.close()
        return record

    def list_events(
        self,
        subject_type: str | None = None,
        subject_id: str | None = None,
    ) -> tuple[DurableEventRecord, ...]:
        connection = self._connect()
        try:
            if subject_type is None and subject_id is None:
                rows = connection.execute(
                    "SELECT * FROM events ORDER BY sequence ASC, event_id ASC"
                ).fetchall()
            elif subject_type is not None and subject_id is not None:
                rows = connection.execute(
                    "SELECT * FROM events WHERE subject_type = ? AND subject_id = ? "
                    "ORDER BY sequence ASC, event_id ASC",
                    (subject_type, subject_id),
                ).fetchall()
            elif subject_type is not None:
                rows = connection.execute(
                    "SELECT * FROM events WHERE subject_type = ? "
                    "ORDER BY sequence ASC, event_id ASC",
                    (subject_type,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM events WHERE subject_id = ? "
                    "ORDER BY sequence ASC, event_id ASC",
                    (subject_id,),
                ).fetchall()
        finally:
            connection.close()
        return tuple(_row_to_event(row) for row in rows)

    # ---- approvals -----------------------------------------------------

    def insert_approval(
        self, record: DurableApprovalRecord
    ) -> DurableApprovalRecord | DurableStateError:
        if not isinstance(record, DurableApprovalRecord):
            return DurableStateError.of(
                "invalid_payload", "record must be a DurableApprovalRecord"
            )
        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO approvals
                        (approval_id, approval_type, subject_type, subject_id,
                         decision, decided_by, decided_at, reason, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.approval_id,
                        record.approval_type,
                        record.subject_type,
                        record.subject_id,
                        record.decision,
                        record.decided_by,
                        record.decided_at,
                        record.reason,
                        stable_json_dumps(dict(record.metadata)),
                    ),
                )
        except sqlite3.IntegrityError:
            return DurableStateError.of(
                "duplicate_id",
                f"approval_id already exists: {record.approval_id!r}",
            )
        except sqlite3.Error as exc:
            return DurableStateError.of("storage_unavailable", str(exc))
        finally:
            connection.close()
        return record

    def list_approvals(
        self,
        subject_type: str | None = None,
        subject_id: str | None = None,
    ) -> tuple[DurableApprovalRecord, ...]:
        connection = self._connect()
        try:
            if subject_type is None and subject_id is None:
                rows = connection.execute(
                    "SELECT * FROM approvals ORDER BY decided_at ASC, approval_id ASC"
                ).fetchall()
            elif subject_type is not None and subject_id is not None:
                rows = connection.execute(
                    "SELECT * FROM approvals WHERE subject_type = ? "
                    "AND subject_id = ? ORDER BY decided_at ASC, approval_id ASC",
                    (subject_type, subject_id),
                ).fetchall()
            elif subject_type is not None:
                rows = connection.execute(
                    "SELECT * FROM approvals WHERE subject_type = ? "
                    "ORDER BY decided_at ASC, approval_id ASC",
                    (subject_type,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM approvals WHERE subject_id = ? "
                    "ORDER BY decided_at ASC, approval_id ASC",
                    (subject_id,),
                ).fetchall()
        finally:
            connection.close()
        return tuple(_row_to_approval(row) for row in rows)

    # ---- results -------------------------------------------------------

    def insert_result(
        self, record: DurableResultRecord
    ) -> DurableResultRecord | DurableStateError:
        if not isinstance(record, DurableResultRecord):
            return DurableStateError.of(
                "invalid_payload", "record must be a DurableResultRecord"
            )
        connection = self._connect()
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO results
                        (result_id, result_type, subject_type, subject_id,
                         verdict, payload_json, created_at, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.result_id,
                        record.result_type,
                        record.subject_type,
                        record.subject_id,
                        record.verdict,
                        record.payload_json,
                        record.created_at,
                        stable_json_dumps(dict(record.metadata)),
                    ),
                )
        except sqlite3.IntegrityError:
            return DurableStateError.of(
                "duplicate_id", f"result_id already exists: {record.result_id!r}"
            )
        except sqlite3.Error as exc:
            return DurableStateError.of("storage_unavailable", str(exc))
        finally:
            connection.close()
        return record

    def list_results(
        self,
        subject_type: str | None = None,
        subject_id: str | None = None,
    ) -> tuple[DurableResultRecord, ...]:
        connection = self._connect()
        try:
            if subject_type is None and subject_id is None:
                rows = connection.execute(
                    "SELECT * FROM results ORDER BY created_at ASC, result_id ASC"
                ).fetchall()
            elif subject_type is not None and subject_id is not None:
                rows = connection.execute(
                    "SELECT * FROM results WHERE subject_type = ? "
                    "AND subject_id = ? ORDER BY created_at ASC, result_id ASC",
                    (subject_type, subject_id),
                ).fetchall()
            elif subject_type is not None:
                rows = connection.execute(
                    "SELECT * FROM results WHERE subject_type = ? "
                    "ORDER BY created_at ASC, result_id ASC",
                    (subject_type,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM results WHERE subject_id = ? "
                    "ORDER BY created_at ASC, result_id ASC",
                    (subject_id,),
                ).fetchall()
        finally:
            connection.close()
        return tuple(_row_to_result(row) for row in rows)
