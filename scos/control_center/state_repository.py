"""SCOS Stage 6.3 Control Center durable state repository.

A higher-level API over ``SQLiteStateStore`` intended for the Stage 6.2
backend/API layer (and future Stage 6.4 event stream) to record durable
state without touching SQL directly. This module builds deterministic
record IDs from sha256 of stable caller-supplied inputs; it never reads the
clock, generates a UUID, or calls ``random``.

This module writes records only -- it never executes a command, enqueues
real work, starts a server, or dispatches to a real AI adapter.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid,
no network, no server.
"""

from __future__ import annotations

import hashlib
from typing import Any

try:
    from .sqlite_state_store import SQLiteStateStore
    from .state_models import (
        DurableApprovalRecord,
        DurableCommandRecord,
        DurableEventRecord,
        DurableResultRecord,
        DurableSessionRecord,
        DurableStateError,
    )
    from .sqlite_state_schema import stable_json_dumps
except ImportError:  # direct-module execution (tests insert the package dir)
    from sqlite_state_store import SQLiteStateStore
    from state_models import (
        DurableApprovalRecord,
        DurableCommandRecord,
        DurableEventRecord,
        DurableResultRecord,
        DurableSessionRecord,
        DurableStateError,
    )
    from sqlite_state_schema import stable_json_dumps

CONTROL_CENTER_STATE_REPOSITORY_SCHEMA_VERSION = 1


def _sha256_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:32]}"


class ControlCenterStateRepository:
    """Higher-level durable state writer/reader over ``SQLiteStateStore``."""

    def __init__(self, store: SQLiteStateStore) -> None:
        self._store = store

    @property
    def store(self) -> SQLiteStateStore:
        return self._store

    def initialize_state(self, applied_at: str) -> dict | DurableStateError:
        error = self._store.initialize(applied_at=applied_at)
        if error is not None:
            return error
        return self._store.health_snapshot(checked_at=applied_at)

    def record_backend_request(
        self,
        *,
        request_id: str,
        request_type: str,
        session_id: str | None,
        payload_json: str,
        created_at: str,
        metadata: Any = None,
    ) -> DurableCommandRecord | DurableStateError:
        command_id = _sha256_id("cmd", "backend_request", request_id, request_type)
        record = DurableCommandRecord.of(
            command_id,
            request_type,
            "draft",
            created_at,
            request_id=request_id,
            session_id=session_id,
            payload_json=payload_json,
            metadata=metadata,
        )
        return self._store.insert_command(record)

    def record_backend_response(
        self,
        *,
        request_id: str,
        request_type: str,
        status: str,
        session_id: str | None,
        payload_json: str,
        created_at: str,
        metadata: Any = None,
    ) -> DurableCommandRecord | DurableStateError:
        command_id = _sha256_id("cmd", "backend_response", request_id, request_type)
        record = DurableCommandRecord.of(
            command_id,
            request_type,
            status,
            created_at,
            request_id=request_id,
            session_id=session_id,
            payload_json=payload_json,
            metadata=metadata,
        )
        return self._store.insert_command(record)

    def record_command_state(
        self,
        *,
        command_key: str,
        command_type: str,
        status: str,
        created_at: str,
        request_id: str | None = None,
        session_id: str | None = None,
        payload_json: str = "{}",
        metadata: Any = None,
    ) -> DurableCommandRecord | DurableStateError:
        command_id = _sha256_id("cmd", "command_state", command_key, command_type)
        record = DurableCommandRecord.of(
            command_id,
            command_type,
            status,
            created_at,
            request_id=request_id,
            session_id=session_id,
            payload_json=payload_json,
            metadata=metadata,
        )
        return self._store.insert_command(record)

    def record_session_state(
        self,
        *,
        session_key: str,
        status: str,
        created_at: str,
        task_id: str | None = None,
        agent_id: str | None = None,
        runtime_id: str | None = None,
        metadata: Any = None,
    ) -> DurableSessionRecord | DurableStateError:
        session_id = _sha256_id("session", "session_state", session_key)
        record = DurableSessionRecord.of(
            session_id,
            status,
            created_at,
            task_id=task_id,
            agent_id=agent_id,
            runtime_id=runtime_id,
            metadata=metadata,
        )
        return self._store.insert_session(record)

    def record_operator_approval(
        self,
        *,
        approval_key: str,
        approval_type: str,
        subject_type: str,
        subject_id: str,
        decision: str,
        decided_by: str,
        decided_at: str,
        reason: str | None = None,
        metadata: Any = None,
    ) -> DurableApprovalRecord | DurableStateError:
        approval_id = _sha256_id(
            "approval", "operator_approval", approval_key, subject_type, subject_id
        )
        record = DurableApprovalRecord.of(
            approval_id,
            approval_type,
            subject_type,
            subject_id,
            decision,
            decided_by,
            decided_at,
            reason=reason,
            metadata=metadata,
        )
        return self._store.insert_approval(record)

    def record_agent_result(
        self,
        *,
        result_key: str,
        result_type: str,
        subject_type: str,
        subject_id: str,
        verdict: str,
        created_at: str,
        payload_json: str = "{}",
        metadata: Any = None,
    ) -> DurableResultRecord | DurableStateError:
        result_id = _sha256_id(
            "result", "agent_result", result_key, subject_type, subject_id
        )
        record = DurableResultRecord.of(
            result_id,
            result_type,
            subject_type,
            subject_id,
            verdict,
            created_at,
            payload_json=payload_json,
            metadata=metadata,
        )
        return self._store.insert_result(record)

    def append_control_center_event(
        self,
        *,
        event_key: str,
        event_type: str,
        source: str,
        subject_type: str,
        subject_id: str,
        sequence: int,
        created_at: str,
        payload_json: str = "{}",
        metadata: Any = None,
    ) -> DurableEventRecord | DurableStateError:
        event_id = _sha256_id(
            "event", "control_center_event", event_key, subject_type, subject_id
        )
        record = DurableEventRecord.of(
            event_id,
            event_type,
            source,
            subject_type,
            subject_id,
            created_at,
            sequence,
            payload_json=payload_json,
            metadata=metadata,
        )
        return self._store.append_event(record)

    def get_current_state_snapshot(self, checked_at: str) -> dict | DurableStateError:
        try:
            from .state_snapshot import build_state_snapshot
        except ImportError:
            from state_snapshot import build_state_snapshot
        return build_state_snapshot(self._store, checked_at=checked_at)
