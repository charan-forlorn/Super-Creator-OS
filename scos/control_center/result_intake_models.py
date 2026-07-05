"""SCOS Stage 5.7 AI Result Intake & ChatGPT Status Update Loop models.

Immutable dataclasses that model how a pasted/imported agent (or operator)
result becomes a normalized ``AIResultIntakeRecord``, how that record is
turned into a ``ChatGPTStatusUpdatePacket`` (a manual-handoff status update
body, never sent anywhere by this module), how it updates local
``ProjectStateUpdate`` bookkeeping, and how a conservative
``NextActionDecision`` is recommended for the operator to act on.

This module NEVER executes AI, calls an API, automates a desktop app/browser,
touches a clipboard, opens a network connection, or runs a background worker.
It only models state so the Control Center has one deterministic shape for
the Stage 5.7 result-intake loop.

``FrozenMap`` is reused from ``operator_packet_review_models`` (Stage 5.5) per
the existing project convention: one immutable string-keyed map class shared
across ``scos.control_center`` model modules rather than a new one per stage.

All collection fields are tuples, so no mutable dict/list is ever exposed
from a model instance. ``to_dict()`` uses explicit key order and serializes
tuples as lists and ``FrozenMap`` as a plain dict.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from .operator_packet_review_models import FrozenMap
except ImportError:  # direct-module execution (tests insert the package dir)
    from operator_packet_review_models import FrozenMap

AI_RESULT_INTAKE_SCHEMA_VERSION = 1

ALLOWED_ARTIFACT_TYPES = (
    "implementation_report",
    "review_report",
    "audit_report",
    "test_report",
    "changed_files",
    "command_output",
    "git_status",
    "build_result",
    "lint_result",
    "screenshot_note",
    "operator_note",
    "unknown",
)

# ``source_agent="operator"`` means a manual pasted/imported result source
# only, not an automated agent runtime.
ALLOWED_SOURCE_AGENTS = ("chatgpt", "claude_code", "codex", "hermes", "operator")

ALLOWED_VERDICTS = (
    "PASS",
    "FAIL",
    "BLOCKED",
    "NEEDS_FIX",
    "NEEDS_REVIEW",
    "PARTIAL",
    "UNKNOWN",
)

ALLOWED_CONFIDENCE_LEVELS = ("low", "medium", "high")

ALLOWED_INTAKE_STATUSES = (
    "drafted",
    "intake_recorded",
    "normalized",
    "review_required",
    "ready_for_chatgpt_update",
    "sent_to_chatgpt_packet_ready",
    "project_state_updated",
    "next_action_ready",
    "blocked",
)

# Requesting agent for a ChatGPTStatusUpdatePacket is always "chatgpt" — this
# is the only allowed value, kept as a tuple for symmetry with other
# allow-lists and for a uniform error message from ``_require_allowed``.
ALLOWED_CHATGPT_TARGET_AGENTS = ("chatgpt",)

ALLOWED_CHATGPT_ACTIONS = (
    "summarize_status",
    "decide_next_action",
    "update_stage_plan",
    "prepare_review_prompt",
    "prepare_fix_prompt",
    "prepare_commit_recommendation",
    "mark_blocked",
    "request_operator_decision",
)

ALLOWED_TASK_STATUSES = (
    "planning",
    "implementation_done",
    "review_required",
    "needs_fix",
    "blocked",
    "approved",
    "ready_for_commit",
    "done",
)

ALLOWED_STAGE_STATUSES = (
    "active",
    "blocked",
    "needs_review",
    "ready_for_next_stage",
    "complete",
)

ALLOWED_NEXT_ACTIONS = (
    "send_to_chatgpt_status_update",
    "send_to_claude_fix",
    "send_to_codex_review",
    "send_to_hermes_audit",
    "request_operator_review",
    "prepare_commit_gate",
    "mark_stage_complete",
    "hold_blocked",
    "no_action",
)

ALLOWED_NEXT_ACTION_PRIORITIES = ("low", "normal", "high", "urgent")

ALLOWED_INTAKE_ERROR_KINDS = (
    "invalid_source_agent",
    "invalid_artifact_type",
    "invalid_verdict",
    "invalid_confidence",
    "invalid_status",
    "invalid_target_agent",
    "invalid_chatgpt_action",
    "invalid_task_status",
    "invalid_stage_status",
    "invalid_recommended_action",
    "invalid_priority",
    "missing_required_field",
    "empty_required_field",
    "unsafe_path",
    "unsafe_metadata",
    "invalid_collection_type",
    "contract_violation",
)

_FORBIDDEN_URL_MARKERS = ("http://", "https://")


def _require_allowed(field_name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ValueError(f"{field_name} must be one of {list(allowed)}, got {value!r}")


def _require_nonempty(field_name: str, value: str | None) -> None:
    if value is None or not str(value).strip():
        raise ValueError(f"{field_name} must not be empty")


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _string_tuple(field_name: str, value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    return tuple(str(item) for item in value)


def _reject_url(field_name: str, value: str | None) -> None:
    if value is None:
        return
    lowered = value.lower()
    for marker in _FORBIDDEN_URL_MARKERS:
        if marker in lowered:
            raise ValueError(
                f"{field_name} must be a local path/value, not a URL "
                f"(found {marker!r})"
            )


def _frozen_map(value: Any = None) -> FrozenMap:
    return FrozenMap.of(value)


@dataclass(frozen=True)
class ResultIntakeArtifact:
    """A pointer to one piece of evidence attached to an intake record."""

    artifact_id: str
    artifact_type: str
    title: str
    path: str | None
    summary: str
    sha256: str | None
    required: bool
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_id", str(self.artifact_id))
        object.__setattr__(self, "artifact_type", str(self.artifact_type))
        object.__setattr__(self, "title", str(self.title))
        object.__setattr__(self, "path", _optional_str(self.path))
        object.__setattr__(self, "summary", str(self.summary))
        object.__setattr__(self, "sha256", _optional_str(self.sha256))
        object.__setattr__(self, "required", bool(self.required))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))
        _require_allowed("artifact_type", self.artifact_type, ALLOWED_ARTIFACT_TYPES)
        _require_nonempty("artifact_id", self.artifact_id)
        _require_nonempty("title", self.title)
        _require_nonempty("summary", self.summary)
        _reject_url("path", self.path)

    @staticmethod
    def of(
        artifact_id: str,
        artifact_type: str,
        title: str,
        summary: str,
        *,
        path: str | None = None,
        sha256: str | None = None,
        required: bool = False,
        metadata: Any = None,
    ) -> "ResultIntakeArtifact":
        return ResultIntakeArtifact(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            title=title,
            path=path,
            summary=summary,
            sha256=sha256,
            required=required,
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "title": self.title,
            "path": self.path,
            "summary": self.summary,
            "sha256": self.sha256,
            "required": self.required,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class AIResultIntakeRecord:
    """A deterministic, normalized record of one pasted/imported agent result."""

    ok: bool
    schema_version: int
    intake_id: str
    session_id: str
    task_id: str
    source_agent: str
    source_runtime_id: str
    source_packet_id: str | None
    source_result_packet_id: str | None
    title: str
    raw_result_summary: str
    normalized_summary: str
    verdict: str
    confidence: str
    artifacts: tuple[ResultIntakeArtifact, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    tests_summary: str
    changed_files_summary: str
    operator_review_required: bool
    created_at: str
    status: str
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "intake_id", str(self.intake_id))
        object.__setattr__(self, "session_id", str(self.session_id))
        object.__setattr__(self, "task_id", str(self.task_id))
        object.__setattr__(self, "source_agent", str(self.source_agent))
        object.__setattr__(self, "source_runtime_id", str(self.source_runtime_id))
        object.__setattr__(self, "source_packet_id", _optional_str(self.source_packet_id))
        object.__setattr__(
            self,
            "source_result_packet_id",
            _optional_str(self.source_result_packet_id),
        )
        object.__setattr__(self, "title", str(self.title))
        object.__setattr__(self, "raw_result_summary", str(self.raw_result_summary))
        object.__setattr__(self, "normalized_summary", str(self.normalized_summary))
        object.__setattr__(self, "verdict", str(self.verdict))
        object.__setattr__(self, "confidence", str(self.confidence))
        artifacts = tuple(self.artifacts or ())
        for artifact in artifacts:
            if not isinstance(artifact, ResultIntakeArtifact):
                raise ValueError(
                    "artifacts entries must be ResultIntakeArtifact instances"
                )
        object.__setattr__(self, "artifacts", artifacts)
        object.__setattr__(self, "blockers", _string_tuple("blockers", self.blockers))
        object.__setattr__(self, "warnings", _string_tuple("warnings", self.warnings))
        object.__setattr__(self, "tests_summary", str(self.tests_summary))
        object.__setattr__(
            self, "changed_files_summary", str(self.changed_files_summary)
        )
        object.__setattr__(
            self, "operator_review_required", bool(self.operator_review_required)
        )
        object.__setattr__(self, "created_at", str(self.created_at))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))

        _require_allowed("source_agent", self.source_agent, ALLOWED_SOURCE_AGENTS)
        _require_allowed("verdict", self.verdict, ALLOWED_VERDICTS)
        _require_allowed("confidence", self.confidence, ALLOWED_CONFIDENCE_LEVELS)
        _require_allowed("status", self.status, ALLOWED_INTAKE_STATUSES)
        _require_nonempty("intake_id", self.intake_id)
        _require_nonempty("session_id", self.session_id)
        _require_nonempty("task_id", self.task_id)
        _require_nonempty("title", self.title)
        _require_nonempty("normalized_summary", self.normalized_summary)
        _require_nonempty("created_at", self.created_at)

    @staticmethod
    def of(
        intake_id: str,
        session_id: str,
        task_id: str,
        source_agent: str,
        source_runtime_id: str,
        title: str,
        raw_result_summary: str,
        normalized_summary: str,
        verdict: str,
        confidence: str,
        created_at: str,
        status: str,
        *,
        ok: bool = True,
        schema_version: int = AI_RESULT_INTAKE_SCHEMA_VERSION,
        source_packet_id: str | None = None,
        source_result_packet_id: str | None = None,
        artifacts: Any = (),
        blockers: Any = (),
        warnings: Any = (),
        tests_summary: str = "",
        changed_files_summary: str = "",
        operator_review_required: bool = True,
        metadata: Any = None,
    ) -> "AIResultIntakeRecord":
        return AIResultIntakeRecord(
            ok=ok,
            schema_version=schema_version,
            intake_id=intake_id,
            session_id=session_id,
            task_id=task_id,
            source_agent=source_agent,
            source_runtime_id=source_runtime_id,
            source_packet_id=source_packet_id,
            source_result_packet_id=source_result_packet_id,
            title=title,
            raw_result_summary=raw_result_summary,
            normalized_summary=normalized_summary,
            verdict=verdict,
            confidence=confidence,
            artifacts=tuple(artifacts or ()),
            blockers=_string_tuple("blockers", blockers),
            warnings=_string_tuple("warnings", warnings),
            tests_summary=tests_summary,
            changed_files_summary=changed_files_summary,
            operator_review_required=operator_review_required,
            created_at=created_at,
            status=status,
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "intake_id": self.intake_id,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "source_agent": self.source_agent,
            "source_runtime_id": self.source_runtime_id,
            "source_packet_id": self.source_packet_id,
            "source_result_packet_id": self.source_result_packet_id,
            "title": self.title,
            "raw_result_summary": self.raw_result_summary,
            "normalized_summary": self.normalized_summary,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "tests_summary": self.tests_summary,
            "changed_files_summary": self.changed_files_summary,
            "operator_review_required": self.operator_review_required,
            "created_at": self.created_at,
            "status": self.status,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class ChatGPTStatusUpdatePacket:
    """A manual-handoff status update body prepared for ChatGPT.

    Creating this packet never sends anything to ChatGPT — it only builds a
    deterministic body of text for the operator to paste manually.
    """

    ok: bool
    schema_version: int
    update_packet_id: str
    intake_id: str
    session_id: str
    task_id: str
    target_agent: str
    target_runtime_id: str
    title: str
    status_update_body: str
    result_verdict: str
    result_summary: str
    evidence_refs: tuple[str, ...]
    requested_chatgpt_action: str
    created_at: str
    status: str
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "update_packet_id", str(self.update_packet_id))
        object.__setattr__(self, "intake_id", str(self.intake_id))
        object.__setattr__(self, "session_id", str(self.session_id))
        object.__setattr__(self, "task_id", str(self.task_id))
        object.__setattr__(self, "target_agent", str(self.target_agent))
        object.__setattr__(self, "target_runtime_id", str(self.target_runtime_id))
        object.__setattr__(self, "title", str(self.title))
        object.__setattr__(self, "status_update_body", str(self.status_update_body))
        object.__setattr__(self, "result_verdict", str(self.result_verdict))
        object.__setattr__(self, "result_summary", str(self.result_summary))
        object.__setattr__(
            self, "evidence_refs", _string_tuple("evidence_refs", self.evidence_refs)
        )
        object.__setattr__(
            self, "requested_chatgpt_action", str(self.requested_chatgpt_action)
        )
        object.__setattr__(self, "created_at", str(self.created_at))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))

        _require_allowed(
            "target_agent", self.target_agent, ALLOWED_CHATGPT_TARGET_AGENTS
        )
        _require_allowed("result_verdict", self.result_verdict, ALLOWED_VERDICTS)
        _require_allowed(
            "requested_chatgpt_action",
            self.requested_chatgpt_action,
            ALLOWED_CHATGPT_ACTIONS,
        )
        _require_allowed("status", self.status, ALLOWED_INTAKE_STATUSES)
        _require_nonempty("update_packet_id", self.update_packet_id)
        _require_nonempty("intake_id", self.intake_id)
        _require_nonempty("status_update_body", self.status_update_body)
        _require_nonempty("created_at", self.created_at)

    @staticmethod
    def of(
        update_packet_id: str,
        intake_id: str,
        session_id: str,
        task_id: str,
        target_runtime_id: str,
        title: str,
        status_update_body: str,
        result_verdict: str,
        result_summary: str,
        requested_chatgpt_action: str,
        created_at: str,
        status: str,
        *,
        ok: bool = True,
        schema_version: int = AI_RESULT_INTAKE_SCHEMA_VERSION,
        target_agent: str = "chatgpt",
        evidence_refs: Any = (),
        metadata: Any = None,
    ) -> "ChatGPTStatusUpdatePacket":
        return ChatGPTStatusUpdatePacket(
            ok=ok,
            schema_version=schema_version,
            update_packet_id=update_packet_id,
            intake_id=intake_id,
            session_id=session_id,
            task_id=task_id,
            target_agent=target_agent,
            target_runtime_id=target_runtime_id,
            title=title,
            status_update_body=status_update_body,
            result_verdict=result_verdict,
            result_summary=result_summary,
            evidence_refs=_string_tuple("evidence_refs", evidence_refs),
            requested_chatgpt_action=requested_chatgpt_action,
            created_at=created_at,
            status=status,
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "update_packet_id": self.update_packet_id,
            "intake_id": self.intake_id,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "target_agent": self.target_agent,
            "target_runtime_id": self.target_runtime_id,
            "title": self.title,
            "status_update_body": self.status_update_body,
            "result_verdict": self.result_verdict,
            "result_summary": self.result_summary,
            "evidence_refs": list(self.evidence_refs),
            "requested_chatgpt_action": self.requested_chatgpt_action,
            "created_at": self.created_at,
            "status": self.status,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class ProjectStateUpdate:
    """A deterministic snapshot of project/task/stage state after an intake."""

    ok: bool
    schema_version: int
    state_update_id: str
    intake_id: str
    session_id: str
    task_id: str
    previous_stage: str
    current_stage: str
    task_status: str
    stage_status: str
    latest_agent: str
    latest_verdict: str
    summary: str
    updated_at: str
    evidence_refs: tuple[str, ...]
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "state_update_id", str(self.state_update_id))
        object.__setattr__(self, "intake_id", str(self.intake_id))
        object.__setattr__(self, "session_id", str(self.session_id))
        object.__setattr__(self, "task_id", str(self.task_id))
        object.__setattr__(self, "previous_stage", str(self.previous_stage))
        object.__setattr__(self, "current_stage", str(self.current_stage))
        object.__setattr__(self, "task_status", str(self.task_status))
        object.__setattr__(self, "stage_status", str(self.stage_status))
        object.__setattr__(self, "latest_agent", str(self.latest_agent))
        object.__setattr__(self, "latest_verdict", str(self.latest_verdict))
        object.__setattr__(self, "summary", str(self.summary))
        object.__setattr__(self, "updated_at", str(self.updated_at))
        object.__setattr__(
            self, "evidence_refs", _string_tuple("evidence_refs", self.evidence_refs)
        )
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))

        _require_allowed("task_status", self.task_status, ALLOWED_TASK_STATUSES)
        _require_allowed("stage_status", self.stage_status, ALLOWED_STAGE_STATUSES)
        _require_allowed("latest_agent", self.latest_agent, ALLOWED_SOURCE_AGENTS)
        _require_allowed("latest_verdict", self.latest_verdict, ALLOWED_VERDICTS)
        _require_nonempty("state_update_id", self.state_update_id)
        _require_nonempty("intake_id", self.intake_id)
        _require_nonempty("current_stage", self.current_stage)
        _require_nonempty("summary", self.summary)
        _require_nonempty("updated_at", self.updated_at)

    @staticmethod
    def of(
        state_update_id: str,
        intake_id: str,
        session_id: str,
        task_id: str,
        previous_stage: str,
        current_stage: str,
        task_status: str,
        stage_status: str,
        latest_agent: str,
        latest_verdict: str,
        summary: str,
        updated_at: str,
        *,
        ok: bool = True,
        schema_version: int = AI_RESULT_INTAKE_SCHEMA_VERSION,
        evidence_refs: Any = (),
        metadata: Any = None,
    ) -> "ProjectStateUpdate":
        return ProjectStateUpdate(
            ok=ok,
            schema_version=schema_version,
            state_update_id=state_update_id,
            intake_id=intake_id,
            session_id=session_id,
            task_id=task_id,
            previous_stage=previous_stage,
            current_stage=current_stage,
            task_status=task_status,
            stage_status=stage_status,
            latest_agent=latest_agent,
            latest_verdict=latest_verdict,
            summary=summary,
            updated_at=updated_at,
            evidence_refs=_string_tuple("evidence_refs", evidence_refs),
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "state_update_id": self.state_update_id,
            "intake_id": self.intake_id,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "previous_stage": self.previous_stage,
            "current_stage": self.current_stage,
            "task_status": self.task_status,
            "stage_status": self.stage_status,
            "latest_agent": self.latest_agent,
            "latest_verdict": self.latest_verdict,
            "summary": self.summary,
            "updated_at": self.updated_at,
            "evidence_refs": list(self.evidence_refs),
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class NextActionDecision:
    """A conservative, non-executing recommendation for what to do next.

    Creating this decision never sends anything anywhere and never dispatches
    the recommended action automatically — it only records a recommendation
    for the operator to act on.
    """

    ok: bool
    schema_version: int
    next_action_id: str
    intake_id: str
    session_id: str
    task_id: str
    recommended_action: str
    target_agent: str | None
    target_runtime_id: str | None
    priority: str
    reason: str
    requires_operator_approval: bool
    created_at: str
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "next_action_id", str(self.next_action_id))
        object.__setattr__(self, "intake_id", str(self.intake_id))
        object.__setattr__(self, "session_id", str(self.session_id))
        object.__setattr__(self, "task_id", str(self.task_id))
        object.__setattr__(self, "recommended_action", str(self.recommended_action))
        object.__setattr__(self, "target_agent", _optional_str(self.target_agent))
        object.__setattr__(
            self, "target_runtime_id", _optional_str(self.target_runtime_id)
        )
        object.__setattr__(self, "priority", str(self.priority))
        object.__setattr__(self, "reason", str(self.reason))
        object.__setattr__(
            self,
            "requires_operator_approval",
            bool(self.requires_operator_approval),
        )
        object.__setattr__(self, "created_at", str(self.created_at))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))

        _require_allowed(
            "recommended_action", self.recommended_action, ALLOWED_NEXT_ACTIONS
        )
        _require_allowed("priority", self.priority, ALLOWED_NEXT_ACTION_PRIORITIES)
        if self.target_agent is not None:
            _require_allowed("target_agent", self.target_agent, ALLOWED_SOURCE_AGENTS)
        _require_nonempty("next_action_id", self.next_action_id)
        _require_nonempty("intake_id", self.intake_id)
        _require_nonempty("reason", self.reason)
        _require_nonempty("created_at", self.created_at)
        if self.recommended_action != "no_action" and not self.requires_operator_approval:
            raise ValueError(
                "requires_operator_approval must be true for every "
                "recommended_action except no_action"
            )

    @staticmethod
    def of(
        next_action_id: str,
        intake_id: str,
        session_id: str,
        task_id: str,
        recommended_action: str,
        priority: str,
        reason: str,
        created_at: str,
        *,
        ok: bool = True,
        schema_version: int = AI_RESULT_INTAKE_SCHEMA_VERSION,
        target_agent: str | None = None,
        target_runtime_id: str | None = None,
        requires_operator_approval: bool = True,
        metadata: Any = None,
    ) -> "NextActionDecision":
        return NextActionDecision(
            ok=ok,
            schema_version=schema_version,
            next_action_id=next_action_id,
            intake_id=intake_id,
            session_id=session_id,
            task_id=task_id,
            recommended_action=recommended_action,
            target_agent=target_agent,
            target_runtime_id=target_runtime_id,
            priority=priority,
            reason=reason,
            requires_operator_approval=requires_operator_approval,
            created_at=created_at,
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "next_action_id": self.next_action_id,
            "intake_id": self.intake_id,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "recommended_action": self.recommended_action,
            "target_agent": self.target_agent,
            "target_runtime_id": self.target_runtime_id,
            "priority": self.priority,
            "reason": self.reason,
            "requires_operator_approval": self.requires_operator_approval,
            "created_at": self.created_at,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class AIResultIntakeError:
    """A deterministic, structured rejection for an invalid intake operation."""

    ok: bool
    schema_version: int
    error_kind: str
    error_detail: str
    failed_step: str
    intake_id: str | None
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "error_kind", str(self.error_kind))
        object.__setattr__(self, "error_detail", str(self.error_detail))
        object.__setattr__(self, "failed_step", str(self.failed_step))
        object.__setattr__(self, "intake_id", _optional_str(self.intake_id))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))
        _require_allowed("error_kind", self.error_kind, ALLOWED_INTAKE_ERROR_KINDS)

    @staticmethod
    def of(
        error_kind: str,
        error_detail: str,
        failed_step: str,
        *,
        ok: bool = False,
        schema_version: int = AI_RESULT_INTAKE_SCHEMA_VERSION,
        intake_id: str | None = None,
        metadata: Any = None,
    ) -> "AIResultIntakeError":
        return AIResultIntakeError(
            ok=ok,
            schema_version=schema_version,
            error_kind=error_kind,
            error_detail=error_detail,
            failed_step=failed_step,
            intake_id=intake_id,
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "error_kind": self.error_kind,
            "error_detail": self.error_detail,
            "failed_step": self.failed_step,
            "intake_id": self.intake_id,
            "metadata": self.metadata.to_dict(),
        }
