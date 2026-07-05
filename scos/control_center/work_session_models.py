"""SCOS Stage 5.2 AI Work Session Manager models.

Immutable dataclasses that model deterministic AI work session state:
task -> runtime assignment -> status transitions -> result. This module
NEVER executes AI, calls an API, automates a desktop app, or opens a
browser — it only models state so the Control Center (and, later, real
integrations) has a single deterministic shape to agree on.

All collection fields are tuples (``supported_task_types`` / ``metadata``
are tuples of strings or ``(key, value)`` string pairs), so no mutable
dict/list is ever exposed from a model instance. ``to_dict()`` uses
explicit key order and serializes tuples as lists.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

AI_WORK_SESSION_SCHEMA_VERSION = 1

ALLOWED_AGENT_NAMES = (
    "chatgpt",
    "claude_code",
    "codex",
    "hermes",
)

ALLOWED_RUNTIME_TYPES = (
    "chatgpt_app",
    "chatgpt_web",
    "manual_clipboard",
    "claude_code_cli",
    "claude_code_vscode",
    "codex_cli",
    "codex_app",
    "hermes_cli",
)

ALLOWED_TASK_TYPES = (
    "planning",
    "implementation",
    "review",
    "audit",
    "status_update",
    "prompt_build",
    "result_summary",
    "release_gate",
    "manual_handoff",
)

ALLOWED_PRIORITIES = (
    "low",
    "normal",
    "high",
    "urgent",
)

ALLOWED_SESSION_STATUSES = (
    "draft",
    "queued",
    "assigned",
    "waiting_for_operator",
    "sent_to_agent",
    "agent_working",
    "result_ready",
    "review_required",
    "needs_fix",
    "approved",
    "blocked",
    "cancelled",
    "done",
)

MANUAL_CLIPBOARD_RUNTIME_ID = "manual_clipboard"


def _require_allowed(field_name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ValueError(
            f"{field_name} must be one of {list(allowed)}, got {value!r}"
        )


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _string_tuple(field_name: str, value: Any) -> tuple[str, ...]:
    """Normalize ``value`` into an immutable tuple of strings, order preserved."""
    if value is None:
        return ()
    return tuple(str(item) for item in value)


def _string_pairs(field_name: str, value: Any) -> tuple[tuple[str, str], ...]:
    """Normalize ``value`` into an immutable tuple of (str, str) pairs.

    Accepts a mapping or an iterable of two-item pairs; the resulting order is
    the input order (deterministic for tuples/lists; mappings preserve their
    own insertion order).
    """
    if value is None:
        return ()
    if isinstance(value, dict):
        items = value.items()
    else:
        items = value
    pairs: list[tuple[str, str]] = []
    for item in items:
        pair = tuple(item)
        if len(pair) != 2:
            raise ValueError(
                f"{field_name} entries must be (key, value) pairs, got {item!r}"
            )
        pairs.append((str(pair[0]), str(pair[1])))
    return tuple(pairs)


def _pairs_to_lists(pairs: tuple[tuple[str, str], ...]) -> list[list[str]]:
    return [[key, value] for key, value in pairs]


@dataclass(frozen=True)
class AgentRuntime:
    """A declared, statically-registered AI agent runtime surface.

    This is a description only — nothing here launches, calls, or drives the
    named runtime. ``runtime_type`` is intentionally NOT cross-checked
    against ``agent_name`` here (the registry owns that pairing); this model
    only enforces each field's own allowed-value set.
    """

    runtime_id: str
    agent_name: str
    runtime_type: str
    display_name: str
    supported_task_types: tuple[str, ...]
    enabled: bool
    metadata: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "runtime_id", str(self.runtime_id))
        object.__setattr__(self, "agent_name", str(self.agent_name))
        object.__setattr__(self, "runtime_type", str(self.runtime_type))
        object.__setattr__(self, "display_name", str(self.display_name))
        object.__setattr__(
            self,
            "supported_task_types",
            _string_tuple("supported_task_types", self.supported_task_types),
        )
        object.__setattr__(self, "enabled", bool(self.enabled))
        object.__setattr__(self, "metadata", _string_pairs("metadata", self.metadata))
        _require_allowed("agent_name", self.agent_name, ALLOWED_AGENT_NAMES)
        _require_allowed("runtime_type", self.runtime_type, ALLOWED_RUNTIME_TYPES)
        for task_type in self.supported_task_types:
            _require_allowed("supported_task_types", task_type, ALLOWED_TASK_TYPES)

    @staticmethod
    def of(
        runtime_id: str,
        agent_name: str,
        runtime_type: str,
        display_name: str,
        *,
        supported_task_types: Any = (),
        enabled: bool = True,
        metadata: Any = (),
    ) -> "AgentRuntime":
        return AgentRuntime(
            runtime_id=runtime_id,
            agent_name=agent_name,
            runtime_type=runtime_type,
            display_name=display_name,
            supported_task_types=_string_tuple(
                "supported_task_types", supported_task_types
            ),
            enabled=enabled,
            metadata=_string_pairs("metadata", metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_id": self.runtime_id,
            "agent_name": self.agent_name,
            "runtime_type": self.runtime_type,
            "display_name": self.display_name,
            "supported_task_types": list(self.supported_task_types),
            "enabled": self.enabled,
            "metadata": _pairs_to_lists(self.metadata),
        }


@dataclass(frozen=True)
class AIWorkTask:
    """An operator-authored unit of AI work, not yet assigned to any runtime.

    ``task_type`` and ``priority`` are enforced here: tasks are always
    engine-constructed from an explicit operator action (unlike Stage 5.1
    command drafts, there is no separate validation-layer pass for tasks).
    """

    task_id: str
    title: str
    task_type: str
    objective: str
    input_summary: str
    source_stage: str
    priority: str
    metadata: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", str(self.task_id))
        object.__setattr__(self, "title", str(self.title))
        object.__setattr__(self, "task_type", str(self.task_type))
        object.__setattr__(self, "objective", str(self.objective))
        object.__setattr__(self, "input_summary", str(self.input_summary))
        object.__setattr__(self, "source_stage", str(self.source_stage))
        object.__setattr__(self, "priority", str(self.priority))
        object.__setattr__(self, "metadata", _string_pairs("metadata", self.metadata))
        _require_allowed("task_type", self.task_type, ALLOWED_TASK_TYPES)
        _require_allowed("priority", self.priority, ALLOWED_PRIORITIES)

    @staticmethod
    def of(
        task_id: str,
        title: str,
        task_type: str,
        objective: str,
        input_summary: str,
        source_stage: str,
        *,
        priority: str = "normal",
        metadata: Any = (),
    ) -> "AIWorkTask":
        return AIWorkTask(
            task_id=task_id,
            title=title,
            task_type=task_type,
            objective=objective,
            input_summary=input_summary,
            source_stage=source_stage,
            priority=priority,
            metadata=_string_pairs("metadata", metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "task_type": self.task_type,
            "objective": self.objective,
            "input_summary": self.input_summary,
            "source_stage": self.source_stage,
            "priority": self.priority,
            "metadata": _pairs_to_lists(self.metadata),
        }


@dataclass(frozen=True)
class AgentAssignment:
    """A binding of one task to one agent + runtime, with an explicit reason.

    ``assigned_at`` must be supplied explicitly (no clock is read).
    """

    assignment_id: str
    task_id: str
    agent_name: str
    runtime_id: str
    reason: str
    assigned_at: str
    metadata: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "assignment_id", str(self.assignment_id))
        object.__setattr__(self, "task_id", str(self.task_id))
        object.__setattr__(self, "agent_name", str(self.agent_name))
        object.__setattr__(self, "runtime_id", str(self.runtime_id))
        object.__setattr__(self, "reason", str(self.reason))
        object.__setattr__(self, "assigned_at", str(self.assigned_at))
        object.__setattr__(self, "metadata", _string_pairs("metadata", self.metadata))
        _require_allowed("agent_name", self.agent_name, ALLOWED_AGENT_NAMES)

    @staticmethod
    def of(
        assignment_id: str,
        task_id: str,
        agent_name: str,
        runtime_id: str,
        reason: str,
        assigned_at: str,
        *,
        metadata: Any = (),
    ) -> "AgentAssignment":
        return AgentAssignment(
            assignment_id=assignment_id,
            task_id=task_id,
            agent_name=agent_name,
            runtime_id=runtime_id,
            reason=reason,
            assigned_at=assigned_at,
            metadata=_string_pairs("metadata", metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "assignment_id": self.assignment_id,
            "task_id": self.task_id,
            "agent_name": self.agent_name,
            "runtime_id": self.runtime_id,
            "reason": self.reason,
            "assigned_at": self.assigned_at,
            "metadata": _pairs_to_lists(self.metadata),
        }


@dataclass(frozen=True)
class AIWorkSession:
    """The full deterministic lifecycle record for one unit of AI work.

    ``assignment`` is ``None`` until the manager assigns a runtime.
    ``status`` is engine-enforced (only ``ALLOWED_SESSION_STATUSES`` values
    may exist); the manager is the only allowed writer of transitions.
    """

    session_id: str
    schema_version: int
    task: AIWorkTask
    assignment: AgentAssignment | None
    status: str
    created_at: str
    updated_at: str
    result_summary: str | None
    next_action: str | None
    metadata: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_id", str(self.session_id))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "created_at", str(self.created_at))
        object.__setattr__(self, "updated_at", str(self.updated_at))
        object.__setattr__(self, "result_summary", _optional_str(self.result_summary))
        object.__setattr__(self, "next_action", _optional_str(self.next_action))
        object.__setattr__(self, "metadata", _string_pairs("metadata", self.metadata))
        if not isinstance(self.task, AIWorkTask):
            raise ValueError("task must be an AIWorkTask instance")
        if self.assignment is not None and not isinstance(
            self.assignment, AgentAssignment
        ):
            raise ValueError("assignment must be an AgentAssignment instance or None")
        _require_allowed("status", self.status, ALLOWED_SESSION_STATUSES)

    @staticmethod
    def of(
        session_id: str,
        task: AIWorkTask,
        status: str,
        created_at: str,
        updated_at: str,
        *,
        schema_version: int = AI_WORK_SESSION_SCHEMA_VERSION,
        assignment: AgentAssignment | None = None,
        result_summary: str | None = None,
        next_action: str | None = None,
        metadata: Any = (),
    ) -> "AIWorkSession":
        return AIWorkSession(
            session_id=session_id,
            schema_version=schema_version,
            task=task,
            assignment=assignment,
            status=status,
            created_at=created_at,
            updated_at=updated_at,
            result_summary=result_summary,
            next_action=next_action,
            metadata=_string_pairs("metadata", metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "schema_version": self.schema_version,
            "task": self.task.to_dict(),
            "assignment": self.assignment.to_dict() if self.assignment else None,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "result_summary": self.result_summary,
            "next_action": self.next_action,
            "metadata": _pairs_to_lists(self.metadata),
        }


@dataclass(frozen=True)
class AIWorkSessionError:
    """A deterministic, structured rejection for an invalid manager operation."""

    ok: bool
    schema_version: int
    error_kind: str
    error_detail: str
    failed_step: str
    metadata: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "error_kind", str(self.error_kind))
        object.__setattr__(self, "error_detail", str(self.error_detail))
        object.__setattr__(self, "failed_step", str(self.failed_step))
        object.__setattr__(self, "metadata", _string_pairs("metadata", self.metadata))

    @staticmethod
    def of(
        error_kind: str,
        error_detail: str,
        failed_step: str,
        *,
        ok: bool = False,
        schema_version: int = AI_WORK_SESSION_SCHEMA_VERSION,
        metadata: Any = (),
    ) -> "AIWorkSessionError":
        return AIWorkSessionError(
            ok=ok,
            schema_version=schema_version,
            error_kind=error_kind,
            error_detail=error_detail,
            failed_step=failed_step,
            metadata=_string_pairs("metadata", metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "error_kind": self.error_kind,
            "error_detail": self.error_detail,
            "failed_step": self.failed_step,
            "metadata": _pairs_to_lists(self.metadata),
        }
