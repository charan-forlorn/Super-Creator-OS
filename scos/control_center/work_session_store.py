"""SCOS Stage 5.2 local AI work session store (JSONL, append-only).

Sessions and lifecycle events are appended one JSON object per line to local
JSONL files (UTF-8, LF). The store is strictly append-only: this module
never deletes, truncates, or rewrites existing lines. Reading a session
means replaying its append history: the most recent line for a given
``session_id`` is authoritative.

No SQLite, no database, no server. Local files only.

Local-first, deterministic, stdlib-only. No clock, no random, no network.
"""

from __future__ import annotations

from typing import Any

try:
    from .command_queue import _append_jsonl_line, _read_jsonl_objects
    from .work_session_models import AgentAssignment, AIWorkSession, AIWorkTask
except ImportError:  # direct-module execution (tests insert the package dir)
    from command_queue import _append_jsonl_line, _read_jsonl_objects
    from work_session_models import AgentAssignment, AIWorkSession, AIWorkTask

WORK_SESSION_STORE_SCHEMA_VERSION = 1


def _pairs_from_lists(value: Any) -> tuple[tuple[str, str], ...]:
    return tuple((str(pair[0]), str(pair[1])) for pair in (value or ()))


def _task_from_dict(payload: dict) -> AIWorkTask:
    return AIWorkTask.of(
        payload.get("task_id", ""),
        payload.get("title", ""),
        payload.get("task_type", ""),
        payload.get("objective", ""),
        payload.get("input_summary", ""),
        payload.get("source_stage", ""),
        priority=payload.get("priority", "normal"),
        metadata=_pairs_from_lists(payload.get("metadata")),
    )


def _assignment_from_dict(payload: dict | None) -> AgentAssignment | None:
    if payload is None:
        return None
    return AgentAssignment.of(
        payload.get("assignment_id", ""),
        payload.get("task_id", ""),
        payload.get("agent_name", ""),
        payload.get("runtime_id", ""),
        payload.get("reason", ""),
        payload.get("assigned_at", ""),
        metadata=_pairs_from_lists(payload.get("metadata")),
    )


def _session_from_dict(payload: dict) -> AIWorkSession:
    return AIWorkSession.of(
        payload.get("session_id", ""),
        _task_from_dict(payload.get("task", {})),
        payload.get("status", "draft"),
        payload.get("created_at", ""),
        payload.get("updated_at", ""),
        schema_version=int(payload.get("schema_version", 1)),
        assignment=_assignment_from_dict(payload.get("assignment")),
        result_summary=payload.get("result_summary"),
        next_action=payload.get("next_action"),
        metadata=_pairs_from_lists(payload.get("metadata")),
    )


def append_session(*, sessions_path, session: AIWorkSession) -> str:
    """Append one session snapshot line; return the line's SHA-256 hex.

    Every call (creation or any later transition) appends a new full
    snapshot line — the store never rewrites or deletes prior lines, so the
    append history is itself a deterministic audit trail.
    """
    if not isinstance(session, AIWorkSession):
        raise ValueError(
            "NOT_AN_AI_WORK_SESSION: only AIWorkSession instances may be stored"
        )
    return _append_jsonl_line(sessions_path, "sessions_path", session.to_dict())


def append_event(*, events_path, event: dict[str, Any]) -> str:
    """Append one plain JSON-object event line; return the line's SHA-256 hex.

    Unlike Stage 5.1's ``CommandEvent``, Stage 5.2 events are plain
    dictionaries (the caller — e.g. the manager's transition call site —
    decides the event shape); this function only enforces JSON-object shape
    and deterministic key order (Python 3.7+ dict order is preserved as-is).
    """
    if not isinstance(event, dict):
        raise ValueError("NOT_A_DICT: only dict events may be logged")
    return _append_jsonl_line(events_path, "events_path", event)


def load_sessions(*, sessions_path) -> tuple[AIWorkSession, ...]:
    """Replay every appended line and return the latest snapshot per session_id.

    Result order is first-seen order of each ``session_id`` (not append
    order of every line), so callers see one entry per session.
    """
    payloads = _read_jsonl_objects(sessions_path, "sessions_path", "INVALID_SESSION_LINE")
    latest: dict[str, dict] = {}
    order: list[str] = []
    for payload in payloads:
        session_id = payload.get("session_id", "")
        if session_id not in latest:
            order.append(session_id)
        latest[session_id] = payload
    return tuple(_session_from_dict(latest[session_id]) for session_id in order)


def load_session(*, sessions_path, session_id: str) -> AIWorkSession | None:
    """Return the latest snapshot for one ``session_id``, or ``None``."""
    for session in load_sessions(sessions_path=sessions_path):
        if session.session_id == session_id:
            return session
    return None


def list_sessions(*, sessions_path) -> tuple[str, ...]:
    """Return every distinct ``session_id`` present in the store, first-seen order."""
    return tuple(session.session_id for session in load_sessions(sessions_path=sessions_path))
