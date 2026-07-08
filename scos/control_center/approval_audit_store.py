"""SCOS Stage 6.6 operator approval persistence & audit trail store.

Durable, append-only, tamper-evident ledger for operator approve/deny
decisions, built on top of the Stage 6.3 SQLite WAL infrastructure
(``sqlite_state_schema`` helpers + ``DEFAULT_STATE_DB_RELATIVE_PATH``).

The unified ledger is a single ``audit_ledger`` table. Every entry records a
complete decision (denormalized) AND is a link in a SHA-256 hash chain (see
``approval_audit_models``): each entry commits to its predecessor via
``prev_hash`` and to its own canonical payload via ``entry_hash``.
``verify_chain`` replays the persisted rows and detects any tampering.

Append-only by design: no UPDATE/DELETE is ever issued against
``audit_ledger``. A status change is expressed by appending a new decision,
never by mutating an old one. Decisions and the audit trail therefore survive
a process restart because they live in the SQLite WAL file.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid,
no network, no server, no socket, no API route, no real AI dispatch.

Reuses the Stage 6.3 connection/parameterized-query discipline. The store
never opens a port or starts a server.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

try:
    from .approval_audit_models import (
        GENESIS_PREV_HASH,
        ApprovalDecision,
        AuditEntry,
    )
    from .operator_packet_review_models import FrozenMap
    from .sqlite_state_schema import (
        DEFAULT_STATE_DB_RELATIVE_PATH,
        get_index_statements,
        get_pragmas,
        get_schema_statements,
        stable_json_dumps,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from approval_audit_models import (
        GENESIS_PREV_HASH,
        ApprovalDecision,
        AuditEntry,
    )
    from operator_packet_review_models import FrozenMap
    from sqlite_state_schema import (
        DEFAULT_STATE_DB_RELATIVE_PATH,
        get_index_statements,
        get_pragmas,
        get_schema_statements,
        stable_json_dumps,
    )

_STATE_SCHEMA_NAME = "control_center_state"


def _connect(repo_root: Path, db_path: Path) -> sqlite3.Connection:
    resolved_db = (
        db_path
        if db_path.is_absolute()
        else (Path(repo_root) / db_path)
    )
    resolved_db.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(resolved_db))
    connection.row_factory = sqlite3.Row
    for pragma in get_pragmas():
        connection.execute(pragma)
    # Ensure the schema (incl. audit_ledger) exists.
    for statement in get_schema_statements():
        connection.execute(statement)
    for statement in get_index_statements():
        connection.execute(statement)
    return connection


def _load_metadata(metadata_json: str) -> FrozenMap:
    if not metadata_json:
        return FrozenMap.of({})
    try:
        parsed = json.loads(metadata_json)
    except ValueError:
        return FrozenMap.of({})
    return FrozenMap.of(parsed if isinstance(parsed, dict) else {})


def _row_to_audit_entry(row: sqlite3.Row) -> AuditEntry:
    return AuditEntry(
        entry_id=row["entry_id"],
        sequence=int(row["sequence"]),
        prev_hash=row["prev_hash"],
        entry_hash=row["entry_hash"],
        decision_id=row["decision_id"],
        subject_type=row["subject_type"],
        subject_id=row["subject_id"],
        decision=row["decision"],
        decided_by=row["decided_by"],
        decided_at=row["decided_at"],
        reason=row["reason"],
        metadata_json=row["metadata_json"],
    )


def _row_to_decision(row: sqlite3.Row) -> ApprovalDecision:
    return ApprovalDecision(
        decision_id=row["decision_id"],
        subject_type=row["subject_type"],
        subject_id=row["subject_id"],
        decision=row["decision"],
        decided_by=row["decided_by"],
        decided_at=row["decided_at"],
        reason=row["reason"],
        metadata=_load_metadata(row["metadata_json"]),
    )


def append_audit_entry(
    *,
    decision: ApprovalDecision,
    repo_root: Path,
    db_path=None,
) -> AuditEntry:
    """Append a single audit entry for an already-built decision.

    The chain link (``prev_hash``) is derived from the current highest
    sequence in the ledger: genesis links to the sentinel, all others link
    to the prior entry's ``entry_hash``. Returns the persisted ``AuditEntry``.
    """
    if not isinstance(decision, ApprovalDecision):
        raise ValueError("decision must be an ApprovalDecision")
    resolved_db = (
        Path(db_path)
        if db_path is not None
        else Path(DEFAULT_STATE_DB_RELATIVE_PATH)
    )
    connection = _connect(repo_root, resolved_db)
    try:
        with connection:
            prev = connection.execute(
                "SELECT sequence, entry_hash FROM audit_ledger "
                "ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            if prev is None:
                sequence = 1
                prev_hash = GENESIS_PREV_HASH
            else:
                sequence = int(prev["sequence"]) + 1
                prev_hash = prev["entry_hash"]
            entry = AuditEntry.of(
                sequence=sequence, prev_hash=prev_hash, decision=decision
            )
            connection.execute(
                """
                INSERT INTO audit_ledger
                    (entry_id, sequence, prev_hash, entry_hash, decision_id,
                     subject_type, subject_id, decision, decided_by,
                     decided_at, reason, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.entry_id,
                    entry.sequence,
                    entry.prev_hash,
                    entry.entry_hash,
                    entry.decision_id,
                    entry.subject_type,
                    entry.subject_id,
                    entry.decision,
                    entry.decided_by,
                    entry.decided_at,
                    entry.reason,
                    entry.metadata_json,
                ),
            )
    finally:
        connection.close()
    return entry


def append_decision(
    *,
    subject_type: str,
    subject_id: str,
    decision: str,
    decided_by: str,
    decided_at: str,
    reason=None,
    metadata=None,
    repo_root: Path,
    db_path=None,
) -> tuple[ApprovalDecision, AuditEntry]:
    """Persist a decision and its audit entry atomically.

    Returns the frozen ``(ApprovalDecision, AuditEntry)``. Never reads a
    clock — ``decided_at`` is supplied by the caller. The decision and its
    audit entry are the same append operation: the ledger row carries the
    full decision and is the hash-chain link.
    """
    decision_model = ApprovalDecision.of(
        subject_type=subject_type,
        subject_id=subject_id,
        decision=decision,
        decided_by=decided_by,
        decided_at=decided_at,
        reason=reason,
        metadata=metadata,
    )
    entry = append_audit_entry(
        decision=decision_model, repo_root=repo_root, db_path=db_path
    )
    return decision_model, entry


def load_decisions(
    *,
    subject_type=None,
    subject_id=None,
    repo_root: Path,
    db_path=None,
) -> tuple[ApprovalDecision, ...]:
    """Return all persisted decisions, optionally filtered, in ledger order."""
    resolved_db = (
        Path(db_path)
        if db_path is not None
        else Path(DEFAULT_STATE_DB_RELATIVE_PATH)
    )
    connection = _connect(repo_root, resolved_db)
    try:
        sql = (
            "SELECT entry_id, sequence, prev_hash, entry_hash, decision_id, "
            "subject_type, subject_id, decision, decided_by, decided_at, "
            "reason, metadata_json FROM audit_ledger"
        )
        params: list = []
        where = []
        if subject_type is not None:
            where.append("subject_type = ?")
            params.append(subject_type)
        if subject_id is not None:
            where.append("subject_id = ?")
            params.append(subject_id)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY sequence ASC"
        rows = connection.execute(sql, params).fetchall()
    finally:
        connection.close()
    return tuple(_row_to_decision(row) for row in rows)


def latest_decision(
    *,
    subject_type: str,
    subject_id: str,
    repo_root: Path,
    db_path=None,
) -> ApprovalDecision | None:
    """Return the highest-sequence decision for a subject, or ``None``."""
    decisions = load_decisions(
        subject_type=subject_type, subject_id=subject_id,
        repo_root=repo_root, db_path=db_path,
    )
    return decisions[-1] if decisions else None


def is_execution_granted(
    *,
    subject_type: str,
    subject_id: str,
    repo_root: Path,
    db_path=None,
) -> bool:
    """Safety check: execution is granted only if the latest decision for the

    subject is ``approved``. ``pending`` and ``denied`` block execution.
    """
    latest = latest_decision(
        subject_type=subject_type, subject_id=subject_id,
        repo_root=repo_root, db_path=db_path,
    )
    return latest is not None and latest.decision == "approved"


def verify_chain(
    *,
    repo_root: Path,
    db_path=None,
) -> bool:
    """Replay the persisted audit ledger and confirm the hash chain is intact.

    Returns ``False`` if any entry's ``prev_hash`` does not link to the prior
    entry's ``entry_hash``, or any stored ``entry_hash`` does not match the
    recomputed hash of its own canonical payload.
    """
    resolved_db = (
        Path(db_path)
        if db_path is not None
        else Path(DEFAULT_STATE_DB_RELATIVE_PATH)
    )
    connection = _connect(repo_root, resolved_db)
    try:
        rows = connection.execute(
            "SELECT entry_id, sequence, prev_hash, entry_hash, decision_id, "
            "subject_type, subject_id, decision, decided_by, decided_at, "
            "reason, metadata_json FROM audit_ledger ORDER BY sequence ASC"
        ).fetchall()
    finally:
        connection.close()

    expected_prev = GENESIS_PREV_HASH
    for row in rows:
        entry = _row_to_audit_entry(row)
        if entry.sequence < 1:
            return False
        if entry.prev_hash != expected_prev:
            return False
        if entry.entry_hash != entry.recompute_entry_hash():
            return False
        expected_prev = entry.entry_hash
    return True
