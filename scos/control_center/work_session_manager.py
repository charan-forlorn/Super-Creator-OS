"""SCOS Stage 5.2 AI Work Session Manager.

Pure, deterministic state-machine functions over an explicit ``sessions``
dict supplied by the caller (mirrors the explicit ``queue_path`` /
``event_log_path`` style of the Stage 5.1 command bridge). No function here
executes AI, calls an API, opens a browser, drives a desktop app, or reads a
clock — every timestamp is caller-supplied and every id is caller-supplied
or content-derived.

Lifecycle modeled:

    create_work_session -> assign_runtime -> transition_status (N times)
    -> complete_session | cancel_session

Local-first, deterministic, stdlib-only. No clock, no random, no uuid,
no network, no process launch.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

try:
    from .runtime_registry import get_runtime
    from .work_session_models import (
        AgentAssignment,
        AIWorkSession,
        AIWorkSessionError,
        AIWorkTask,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from runtime_registry import get_runtime
    from work_session_models import (
        AgentAssignment,
        AIWorkSession,
        AIWorkSessionError,
        AIWorkTask,
    )

WORK_SESSION_MANAGER_SCHEMA_VERSION = 1

TERMINAL_STATUSES = ("cancelled", "done")

_ASSIGNABLE_STATUSES = ("draft", "queued", "blocked", "needs_fix")

# Fixed, explicit transition table. Every status not listed as a key has no
# outgoing transitions (i.e. it is terminal).
ALLOWED_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "draft": ("queued", "cancelled"),
    "queued": ("assigned", "blocked", "cancelled"),
    "assigned": ("waiting_for_operator", "sent_to_agent", "blocked", "cancelled"),
    "waiting_for_operator": ("sent_to_agent", "blocked", "cancelled"),
    "sent_to_agent": ("agent_working", "blocked", "cancelled"),
    "agent_working": ("result_ready", "blocked", "cancelled"),
    "result_ready": ("review_required", "cancelled"),
    "review_required": ("needs_fix", "approved", "cancelled"),
    "needs_fix": ("queued", "sent_to_agent", "blocked", "cancelled"),
    "approved": ("done", "cancelled"),
    "blocked": ("queued", "cancelled"),
    "cancelled": (),
    "done": (),
}


def validate_transition(current_status: str, new_status: str) -> tuple[bool, str | None]:
    """Return ``(True, None)`` when ``new_status`` is reachable from
    ``current_status``, else ``(False, <stable error message>)``.

    Pure lookup against ``ALLOWED_TRANSITIONS``; never mutates anything.
    """
    allowed = ALLOWED_TRANSITIONS.get(current_status)
    if allowed is None:
        return False, f"unknown current_status: {current_status!r}"
    if new_status not in allowed:
        return (
            False,
            f"invalid transition: {current_status!r} -> {new_status!r} "
            f"(allowed: {list(allowed)})",
        )
    return True, None


def create_work_session(
    *,
    sessions: dict[str, AIWorkSession],
    session_id: str,
    task: AIWorkTask,
    created_at: str,
    metadata: Any = (),
) -> AIWorkSession | AIWorkSessionError:
    """Create a new session in ``draft`` status and register it in ``sessions``.

    Rejects a duplicate ``session_id`` (never overwrites an existing entry)
    and rejects a ``task`` that is not an ``AIWorkTask`` instance.
    """
    if session_id in sessions:
        return AIWorkSessionError.of(
            "DUPLICATE_SESSION_ID",
            f"session_id already exists: {session_id!r}",
            "create_work_session",
        )
    if not isinstance(task, AIWorkTask):
        return AIWorkSessionError.of(
            "INVALID_TASK",
            "task must be an AIWorkTask instance",
            "create_work_session",
        )
    session = AIWorkSession.of(
        session_id=session_id,
        task=task,
        status="draft",
        created_at=created_at,
        updated_at=created_at,
        metadata=metadata,
    )
    sessions[session_id] = session
    return session


def assign_runtime(
    *,
    sessions: dict[str, AIWorkSession],
    session_id: str,
    runtime_id: str,
    assignment_id: str,
    reason: str,
    assigned_at: str,
    metadata: Any = (),
) -> AIWorkSession | AIWorkSessionError:
    """Bind a registered, enabled, task-type-compatible runtime to a session.

    Only valid from an assignable status (``draft``, ``queued``, ``blocked``,
    ``needs_fix``); the resulting session moves to ``assigned``.
    """
    session = sessions.get(session_id)
    if session is None:
        return AIWorkSessionError.of(
            "UNKNOWN_SESSION", f"no session with id {session_id!r}", "assign_runtime"
        )
    if session.status in TERMINAL_STATUSES:
        return AIWorkSessionError.of(
            "SESSION_ALREADY_COMPLETED",
            f"session {session_id!r} is in terminal status {session.status!r}",
            "assign_runtime",
        )
    if session.status not in _ASSIGNABLE_STATUSES:
        return AIWorkSessionError.of(
            "INVALID_STATUS_FOR_ASSIGNMENT",
            f"cannot assign runtime while status is {session.status!r} "
            f"(assignable from: {list(_ASSIGNABLE_STATUSES)})",
            "assign_runtime",
        )
    runtime = get_runtime(runtime_id)
    if runtime is None:
        return AIWorkSessionError.of(
            "UNKNOWN_RUNTIME", f"no runtime with id {runtime_id!r}", "assign_runtime"
        )
    if not runtime.enabled:
        return AIWorkSessionError.of(
            "RUNTIME_DISABLED", f"runtime {runtime_id!r} is disabled", "assign_runtime"
        )
    if session.task.task_type not in runtime.supported_task_types:
        return AIWorkSessionError.of(
            "UNSUPPORTED_TASK_TYPE",
            f"runtime {runtime_id!r} does not support task_type "
            f"{session.task.task_type!r}",
            "assign_runtime",
        )
    assignment = AgentAssignment.of(
        assignment_id,
        session.task.task_id,
        runtime.agent_name,
        runtime_id,
        reason,
        assigned_at,
        metadata=metadata,
    )
    updated = replace(
        session,
        assignment=assignment,
        status="assigned",
        updated_at=assigned_at,
    )
    sessions[session_id] = updated
    return updated


def transition_status(
    *,
    sessions: dict[str, AIWorkSession],
    session_id: str,
    new_status: str,
    updated_at: str,
    result_summary: str | None = None,
    next_action: str | None = None,
) -> AIWorkSession | AIWorkSessionError:
    """Move a session to ``new_status`` if the transition is allowed.

    Never mutates a session already in a terminal status
    (``cancelled`` / ``done``).
    """
    session = sessions.get(session_id)
    if session is None:
        return AIWorkSessionError.of(
            "UNKNOWN_SESSION",
            f"no session with id {session_id!r}",
            "transition_status",
        )
    if session.status in TERMINAL_STATUSES:
        return AIWorkSessionError.of(
            "SESSION_ALREADY_COMPLETED",
            f"session {session_id!r} is in terminal status {session.status!r}",
            "transition_status",
        )
    ok, error = validate_transition(session.status, new_status)
    if not ok:
        return AIWorkSessionError.of("INVALID_TRANSITION", error or "", "transition_status")
    updated = replace(
        session,
        status=new_status,
        updated_at=updated_at,
        result_summary=(
            result_summary if result_summary is not None else session.result_summary
        ),
        next_action=next_action if next_action is not None else session.next_action,
    )
    sessions[session_id] = updated
    return updated


def complete_session(
    *,
    sessions: dict[str, AIWorkSession],
    session_id: str,
    updated_at: str,
    result_summary: str,
) -> AIWorkSession | AIWorkSessionError:
    """Move an ``approved`` session to ``done`` with a final result summary."""
    session = sessions.get(session_id)
    if session is None:
        return AIWorkSessionError.of(
            "UNKNOWN_SESSION",
            f"no session with id {session_id!r}",
            "complete_session",
        )
    if session.status in TERMINAL_STATUSES:
        return AIWorkSessionError.of(
            "SESSION_ALREADY_COMPLETED",
            f"session {session_id!r} is in terminal status {session.status!r}",
            "complete_session",
        )
    if session.status != "approved":
        return AIWorkSessionError.of(
            "INVALID_TRANSITION",
            f"complete_session requires status 'approved', got {session.status!r}",
            "complete_session",
        )
    return transition_status(
        sessions=sessions,
        session_id=session_id,
        new_status="done",
        updated_at=updated_at,
        result_summary=result_summary,
        next_action=None,
    )


def cancel_session(
    *,
    sessions: dict[str, AIWorkSession],
    session_id: str,
    updated_at: str,
    reason: str,
) -> AIWorkSession | AIWorkSessionError:
    """Cancel a non-terminal session, recording ``reason`` as the result summary."""
    session = sessions.get(session_id)
    if session is None:
        return AIWorkSessionError.of(
            "UNKNOWN_SESSION", f"no session with id {session_id!r}", "cancel_session"
        )
    if session.status in TERMINAL_STATUSES:
        return AIWorkSessionError.of(
            "SESSION_ALREADY_COMPLETED",
            f"session {session_id!r} is in terminal status {session.status!r}",
            "cancel_session",
        )
    return transition_status(
        sessions=sessions,
        session_id=session_id,
        new_status="cancelled",
        updated_at=updated_at,
        result_summary=reason,
        next_action=None,
    )
