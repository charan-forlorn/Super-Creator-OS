"""SCOS Stage 5.3 AI Agent Adapter Contract Layer models.

Immutable dataclasses that model a deterministic AI agent adapter
request/result lifecycle: request -> validation -> adapter selection ->
prepared prompt -> simulated send -> simulated result -> lifecycle events.
This module NEVER executes AI, calls an API, automates a desktop app, opens
a browser, or touches a clipboard — it only models state so the Control
Center (and, later, real integrations) has a single deterministic shape to
agree on.

All collection fields are tuples (``task_types`` / ``metadata`` are tuples
of strings or ``(key, value)`` string pairs, mirroring the convention
established in ``work_session_models.py``), so no mutable dict/list is ever
exposed from a model instance. ``to_dict()`` uses explicit key order and
serializes tuples as lists.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

AI_AGENT_ADAPTER_SCHEMA_VERSION = 1

ALLOWED_ADAPTER_AGENT_NAMES = (
    "chatgpt",
    "claude_code",
    "codex",
    "hermes",
    "manual_clipboard",
)

ALLOWED_ADAPTER_RUNTIME_TYPES = (
    "chatgpt_app",
    "chatgpt_web",
    "openai_api",
    "claude_code_vscode",
    "claude_code_cli",
    "codex_app",
    "codex_cli",
    "hermes_cli",
    "manual_clipboard",
)

ALLOWED_ADAPTER_TASK_TYPES = (
    "planning",
    "implementation",
    "review",
    "audit",
    "status_update",
    "prompt_build",
    "result_summary",
    "release_gate",
    "git_review",
    "manual_handoff",
)

ALLOWED_DELIVERY_MODES = (
    "contract_only",
    "manual_clipboard",
    "simulated",
)

ALLOWED_RESULT_TYPES = (
    "plan",
    "implementation_report",
    "review_report",
    "audit_report",
    "status_update",
    "prompt_packet",
    "result_summary",
    "release_gate_report",
    "git_review_report",
    "manual_handoff_note",
)

ALLOWED_ADAPTER_STATUSES = (
    "accepted",
    "prepared",
    "simulated_sent",
    "waiting_for_operator",
    "result_ready",
    "failed",
    "blocked",
)

ALLOWED_ADAPTER_ERROR_KINDS = (
    "invalid_agent",
    "invalid_runtime",
    "invalid_task_type",
    "invalid_delivery_mode",
    "unsupported_capability",
    "unsafe_prompt",
    "network_forbidden",
    "missing_required_field",
    "contract_violation",
    "adapter_blocked",
)

ALLOWED_ADAPTER_EVENT_TYPES = (
    "request_created",
    "request_validated",
    "adapter_selected",
    "prompt_prepared",
    "manual_clipboard_ready",
    "simulated_sent",
    "result_simulated",
    "result_ready",
    "blocked",
)

_FORBIDDEN_PROMPT_MARKERS = ("http://", "https://")


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


def _reject_unsafe_prompt(field_name: str, value: str) -> None:
    lowered = value.lower()
    for marker in _FORBIDDEN_PROMPT_MARKERS:
        if marker in lowered:
            raise ValueError(
                f"{field_name} must not contain a URL/network target "
                f"(found {marker!r})"
            )


@dataclass(frozen=True)
class AgentAdapterCapability:
    """A declared, statically-described capability surface for one adapter.

    This is a description only — nothing here launches, calls, or drives the
    named runtime. It only enforces each field's own allowed-value set.
    """

    capability_id: str
    agent_name: str
    runtime_type: str
    task_types: tuple[str, ...]
    supports_prompt_delivery: bool
    supports_result_capture: bool
    supports_status_check: bool
    supports_manual_fallback: bool
    metadata: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "capability_id", str(self.capability_id))
        object.__setattr__(self, "agent_name", str(self.agent_name))
        object.__setattr__(self, "runtime_type", str(self.runtime_type))
        object.__setattr__(
            self, "task_types", _string_tuple("task_types", self.task_types)
        )
        object.__setattr__(
            self, "supports_prompt_delivery", bool(self.supports_prompt_delivery)
        )
        object.__setattr__(
            self, "supports_result_capture", bool(self.supports_result_capture)
        )
        object.__setattr__(
            self, "supports_status_check", bool(self.supports_status_check)
        )
        object.__setattr__(
            self, "supports_manual_fallback", bool(self.supports_manual_fallback)
        )
        object.__setattr__(self, "metadata", _string_pairs("metadata", self.metadata))
        _require_allowed("agent_name", self.agent_name, ALLOWED_ADAPTER_AGENT_NAMES)
        _require_allowed(
            "runtime_type", self.runtime_type, ALLOWED_ADAPTER_RUNTIME_TYPES
        )
        for task_type in self.task_types:
            _require_allowed("task_types", task_type, ALLOWED_ADAPTER_TASK_TYPES)

    @staticmethod
    def of(
        capability_id: str,
        agent_name: str,
        runtime_type: str,
        *,
        task_types: Any = (),
        supports_prompt_delivery: bool = True,
        supports_result_capture: bool = True,
        supports_status_check: bool = False,
        supports_manual_fallback: bool = False,
        metadata: Any = (),
    ) -> "AgentAdapterCapability":
        return AgentAdapterCapability(
            capability_id=capability_id,
            agent_name=agent_name,
            runtime_type=runtime_type,
            task_types=_string_tuple("task_types", task_types),
            supports_prompt_delivery=supports_prompt_delivery,
            supports_result_capture=supports_result_capture,
            supports_status_check=supports_status_check,
            supports_manual_fallback=supports_manual_fallback,
            metadata=_string_pairs("metadata", metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "agent_name": self.agent_name,
            "runtime_type": self.runtime_type,
            "task_types": list(self.task_types),
            "supports_prompt_delivery": self.supports_prompt_delivery,
            "supports_result_capture": self.supports_result_capture,
            "supports_status_check": self.supports_status_check,
            "supports_manual_fallback": self.supports_manual_fallback,
            "metadata": _pairs_to_lists(self.metadata),
        }


@dataclass(frozen=True)
class AgentAdapterRequest:
    """A caller-authored request to hand one task to one agent adapter.

    ``request_id`` and ``created_at`` must be supplied explicitly (no clock,
    no random, no uuid is ever read). ``prompt_text`` must be explicit,
    caller-authored text — it is rejected if it contains a URL/network
    target, since this stage must never produce a "prompt" that could be
    used to reach out over the network.
    """

    request_id: str
    session_id: str
    task_id: str
    agent_name: str
    runtime_id: str
    runtime_type: str
    task_type: str
    prompt_text: str
    input_summary: str
    created_at: str
    delivery_mode: str
    expected_result_type: str
    metadata: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", str(self.request_id))
        object.__setattr__(self, "session_id", str(self.session_id))
        object.__setattr__(self, "task_id", str(self.task_id))
        object.__setattr__(self, "agent_name", str(self.agent_name))
        object.__setattr__(self, "runtime_id", str(self.runtime_id))
        object.__setattr__(self, "runtime_type", str(self.runtime_type))
        object.__setattr__(self, "task_type", str(self.task_type))
        object.__setattr__(self, "prompt_text", str(self.prompt_text))
        object.__setattr__(self, "input_summary", str(self.input_summary))
        object.__setattr__(self, "created_at", str(self.created_at))
        object.__setattr__(self, "delivery_mode", str(self.delivery_mode))
        object.__setattr__(
            self, "expected_result_type", str(self.expected_result_type)
        )
        object.__setattr__(self, "metadata", _string_pairs("metadata", self.metadata))
        _require_allowed("agent_name", self.agent_name, ALLOWED_ADAPTER_AGENT_NAMES)
        _require_allowed(
            "runtime_type", self.runtime_type, ALLOWED_ADAPTER_RUNTIME_TYPES
        )
        _require_allowed("task_type", self.task_type, ALLOWED_ADAPTER_TASK_TYPES)
        _require_allowed(
            "delivery_mode", self.delivery_mode, ALLOWED_DELIVERY_MODES
        )
        _require_allowed(
            "expected_result_type", self.expected_result_type, ALLOWED_RESULT_TYPES
        )
        _reject_unsafe_prompt("prompt_text", self.prompt_text)

    @staticmethod
    def of(
        request_id: str,
        session_id: str,
        task_id: str,
        agent_name: str,
        runtime_id: str,
        runtime_type: str,
        task_type: str,
        prompt_text: str,
        input_summary: str,
        created_at: str,
        *,
        delivery_mode: str = "contract_only",
        expected_result_type: str = "result_summary",
        metadata: Any = (),
    ) -> "AgentAdapterRequest":
        return AgentAdapterRequest(
            request_id=request_id,
            session_id=session_id,
            task_id=task_id,
            agent_name=agent_name,
            runtime_id=runtime_id,
            runtime_type=runtime_type,
            task_type=task_type,
            prompt_text=prompt_text,
            input_summary=input_summary,
            created_at=created_at,
            delivery_mode=delivery_mode,
            expected_result_type=expected_result_type,
            metadata=_string_pairs("metadata", metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "agent_name": self.agent_name,
            "runtime_id": self.runtime_id,
            "runtime_type": self.runtime_type,
            "task_type": self.task_type,
            "prompt_text": self.prompt_text,
            "input_summary": self.input_summary,
            "created_at": self.created_at,
            "delivery_mode": self.delivery_mode,
            "expected_result_type": self.expected_result_type,
            "metadata": _pairs_to_lists(self.metadata),
        }


@dataclass(frozen=True)
class AgentAdapterResult:
    """A deterministic, adapter-produced (or simulated) result record."""

    result_id: str
    request_id: str
    session_id: str
    agent_name: str
    runtime_id: str
    status: str
    result_type: str
    result_summary: str
    output_text: str | None
    output_path: str | None
    created_at: str
    next_action: str | None
    metadata: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "result_id", str(self.result_id))
        object.__setattr__(self, "request_id", str(self.request_id))
        object.__setattr__(self, "session_id", str(self.session_id))
        object.__setattr__(self, "agent_name", str(self.agent_name))
        object.__setattr__(self, "runtime_id", str(self.runtime_id))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "result_type", str(self.result_type))
        object.__setattr__(self, "result_summary", str(self.result_summary))
        object.__setattr__(self, "output_text", _optional_str(self.output_text))
        object.__setattr__(self, "output_path", _optional_str(self.output_path))
        object.__setattr__(self, "created_at", str(self.created_at))
        object.__setattr__(self, "next_action", _optional_str(self.next_action))
        object.__setattr__(self, "metadata", _string_pairs("metadata", self.metadata))
        _require_allowed("agent_name", self.agent_name, ALLOWED_ADAPTER_AGENT_NAMES)
        _require_allowed("status", self.status, ALLOWED_ADAPTER_STATUSES)
        _require_allowed("result_type", self.result_type, ALLOWED_RESULT_TYPES)

    @staticmethod
    def of(
        result_id: str,
        request_id: str,
        session_id: str,
        agent_name: str,
        runtime_id: str,
        status: str,
        result_type: str,
        result_summary: str,
        created_at: str,
        *,
        output_text: str | None = None,
        output_path: str | None = None,
        next_action: str | None = None,
        metadata: Any = (),
    ) -> "AgentAdapterResult":
        return AgentAdapterResult(
            result_id=result_id,
            request_id=request_id,
            session_id=session_id,
            agent_name=agent_name,
            runtime_id=runtime_id,
            status=status,
            result_type=result_type,
            result_summary=result_summary,
            output_text=output_text,
            output_path=output_path,
            created_at=created_at,
            next_action=next_action,
            metadata=_string_pairs("metadata", metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "request_id": self.request_id,
            "session_id": self.session_id,
            "agent_name": self.agent_name,
            "runtime_id": self.runtime_id,
            "status": self.status,
            "result_type": self.result_type,
            "result_summary": self.result_summary,
            "output_text": self.output_text,
            "output_path": self.output_path,
            "created_at": self.created_at,
            "next_action": self.next_action,
            "metadata": _pairs_to_lists(self.metadata),
        }


@dataclass(frozen=True)
class AgentAdapterError:
    """A deterministic, structured rejection for an invalid adapter operation."""

    ok: bool
    schema_version: int
    error_kind: str
    error_detail: str
    failed_step: str
    request_id: str | None
    metadata: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "error_kind", str(self.error_kind))
        object.__setattr__(self, "error_detail", str(self.error_detail))
        object.__setattr__(self, "failed_step", str(self.failed_step))
        object.__setattr__(self, "request_id", _optional_str(self.request_id))
        object.__setattr__(self, "metadata", _string_pairs("metadata", self.metadata))
        _require_allowed(
            "error_kind", self.error_kind, ALLOWED_ADAPTER_ERROR_KINDS
        )

    @staticmethod
    def of(
        error_kind: str,
        error_detail: str,
        failed_step: str,
        *,
        ok: bool = False,
        schema_version: int = AI_AGENT_ADAPTER_SCHEMA_VERSION,
        request_id: str | None = None,
        metadata: Any = (),
    ) -> "AgentAdapterError":
        return AgentAdapterError(
            ok=ok,
            schema_version=schema_version,
            error_kind=error_kind,
            error_detail=error_detail,
            failed_step=failed_step,
            request_id=request_id,
            metadata=_string_pairs("metadata", metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "error_kind": self.error_kind,
            "error_detail": self.error_detail,
            "failed_step": self.failed_step,
            "request_id": self.request_id,
            "metadata": _pairs_to_lists(self.metadata),
        }


@dataclass(frozen=True)
class AgentAdapterSimulationEvent:
    """One deterministic step in a simulated adapter lifecycle."""

    event_id: str
    request_id: str
    session_id: str
    agent_name: str
    event_type: str
    status_after: str
    message: str
    created_at: str
    metadata: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", str(self.event_id))
        object.__setattr__(self, "request_id", str(self.request_id))
        object.__setattr__(self, "session_id", str(self.session_id))
        object.__setattr__(self, "agent_name", str(self.agent_name))
        object.__setattr__(self, "event_type", str(self.event_type))
        object.__setattr__(self, "status_after", str(self.status_after))
        object.__setattr__(self, "message", str(self.message))
        object.__setattr__(self, "created_at", str(self.created_at))
        object.__setattr__(self, "metadata", _string_pairs("metadata", self.metadata))
        _require_allowed(
            "event_type", self.event_type, ALLOWED_ADAPTER_EVENT_TYPES
        )
        _require_allowed(
            "status_after", self.status_after, ALLOWED_ADAPTER_STATUSES
        )

    @staticmethod
    def of(
        event_id: str,
        request_id: str,
        session_id: str,
        agent_name: str,
        event_type: str,
        status_after: str,
        message: str,
        created_at: str,
        *,
        metadata: Any = (),
    ) -> "AgentAdapterSimulationEvent":
        return AgentAdapterSimulationEvent(
            event_id=event_id,
            request_id=request_id,
            session_id=session_id,
            agent_name=agent_name,
            event_type=event_type,
            status_after=status_after,
            message=message,
            created_at=created_at,
            metadata=_string_pairs("metadata", metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "request_id": self.request_id,
            "session_id": self.session_id,
            "agent_name": self.agent_name,
            "event_type": self.event_type,
            "status_after": self.status_after,
            "message": self.message,
            "created_at": self.created_at,
            "metadata": _pairs_to_lists(self.metadata),
        }
