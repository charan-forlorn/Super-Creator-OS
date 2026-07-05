"""SCOS Stage 5.4 Unified Prompt & Result Packet models.

Immutable dataclasses that model a deterministic envelope for passing a
prompt from one agent to another (``PromptPacket``) and passing a result
back (``ResultPacket``), plus a non-executing routing recommendation
(``PacketRoutingDecision``). This module NEVER executes AI, calls an API,
automates a desktop app, opens a browser, or touches a clipboard — it only
models state so the Control Center (and, later, real integrations) has a
single deterministic shape to agree on.

There is no ``FrozenMap`` class in this package (one exists in
``scos.commercial.report_models``, but ``scos.control_center`` never imports
``scos.commercial`` in-process). Every "map-like" field in this module is a
``tuple[tuple[str, str], ...]`` of (key, value) string pairs, mirroring the
convention already established in ``work_session_models.py`` and
``agent_adapter_models.py`` — this satisfies the same "immutable map field"
intent without a dedicated class.

All collection fields are tuples, so no mutable dict/list is ever exposed
from a model instance. ``to_dict()`` uses explicit key order and serializes
tuples as lists.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PROMPT_RESULT_PACKET_SCHEMA_VERSION = 1

ALLOWED_PACKET_CONTEXT_REF_TYPES = (
    "session",
    "stage_plan",
    "implementation_report",
    "review_report",
    "audit_report",
    "file_path",
    "git_commit",
    "test_result",
    "operator_note",
    "specification",
    "certification",
    "handoff",
)

ALLOWED_PACKET_TYPES = (
    "planning_prompt",
    "implementation_prompt",
    "review_prompt",
    "audit_prompt",
    "status_update_prompt",
    "result_summary_prompt",
    "release_gate_prompt",
    "manual_handoff_prompt",
)

ALLOWED_PACKET_AGENT_NAMES = (
    "chatgpt",
    "claude_code",
    "codex",
    "hermes",
    "operator",
)

ALLOWED_PROMPT_PACKET_STATUSES = (
    "drafted",
    "ready_for_operator_review",
    "approved_for_handoff",
    "sent_to_agent",
    "result_expected",
    "cancelled",
    "blocked",
)

ALLOWED_RESULT_ARTIFACT_TYPES = (
    "text_result",
    "implementation_report",
    "review_report",
    "audit_report",
    "test_output",
    "changed_files",
    "diff_summary",
    "blocker_list",
    "decision",
    "next_action",
    "certification_report",
)

# Named distinctly from agent_adapter_models.ALLOWED_RESULT_TYPES (a
# different, Stage 5.3 enum) to avoid any export-name collision.
ALLOWED_RESULT_TYPES_PACKET = (
    "planning_result",
    "implementation_result",
    "review_result",
    "audit_result",
    "status_update_result",
    "result_summary",
    "release_gate_result",
    "manual_handoff_result",
)

ALLOWED_RESULT_VERDICTS = (
    "PASS",
    "PASS_WITH_WARNINGS",
    "NEEDS_FIX",
    "BLOCKED",
    "FAIL",
    "INFO",
)

ALLOWED_RESULT_PACKET_STATUSES = (
    "received",
    "validated",
    "review_required",
    "next_prompt_ready",
    "archived",
    "blocked",
)

ALLOWED_ROUTING_PRIORITIES = (
    "low",
    "normal",
    "high",
    "urgent",
)

ALLOWED_PACKET_ERROR_KINDS = (
    "invalid_agent",
    "invalid_packet_type",
    "invalid_result_type",
    "invalid_verdict",
    "invalid_ref_type",
    "invalid_artifact_type",
    "invalid_priority",
    "missing_required_field",
    "empty_required_field",
    "unsafe_path",
    "unsafe_metadata",
    "invalid_collection_type",
    "contract_violation",
)

_FORBIDDEN_URL_MARKERS = ("http://", "https://")
_FORBIDDEN_METADATA_KEY_MARKERS = (
    "api_key",
    "token",
    "secret",
    "password",
    "private_key",
)


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


def _require_nonempty(field_name: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


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


def _reject_secret_metadata(
    field_name: str, pairs: tuple[tuple[str, str], ...]
) -> None:
    for key, _value in pairs:
        lowered_key = key.lower()
        for marker in _FORBIDDEN_METADATA_KEY_MARKERS:
            if marker in lowered_key:
                raise ValueError(
                    f"{field_name} must not contain secret-bearing keys "
                    f"(found key {key!r} matching {marker!r})"
                )


def _check_metadata_safety(field_name: str, pairs: tuple[tuple[str, str], ...]) -> None:
    for _key, value in pairs:
        _reject_url(field_name, value)
    _reject_secret_metadata(field_name, pairs)


@dataclass(frozen=True)
class PacketContextReference:
    """A pointer to one piece of evidence/context attached to a PromptPacket.

    ``path`` may be ``None`` (not every reference is a local file); when
    present it is rejected if it looks like a URL. ``sha256`` may be
    ``None`` in Stage 5.4 (no content-hash verification is performed here).
    """

    ref_id: str
    ref_type: str
    title: str
    path: str | None
    summary: str
    required: bool
    sha256: str | None
    metadata: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "ref_id", str(self.ref_id))
        object.__setattr__(self, "ref_type", str(self.ref_type))
        object.__setattr__(self, "title", str(self.title))
        object.__setattr__(self, "path", _optional_str(self.path))
        object.__setattr__(self, "summary", str(self.summary))
        object.__setattr__(self, "required", bool(self.required))
        object.__setattr__(self, "sha256", _optional_str(self.sha256))
        object.__setattr__(self, "metadata", _string_pairs("metadata", self.metadata))
        _require_allowed("ref_type", self.ref_type, ALLOWED_PACKET_CONTEXT_REF_TYPES)
        _require_nonempty("ref_id", self.ref_id)
        _require_nonempty("title", self.title)
        _require_nonempty("summary", self.summary)
        _reject_url("path", self.path)
        _check_metadata_safety("metadata", self.metadata)

    @staticmethod
    def of(
        ref_id: str,
        ref_type: str,
        title: str,
        summary: str,
        *,
        path: str | None = None,
        required: bool = False,
        sha256: str | None = None,
        metadata: Any = (),
    ) -> "PacketContextReference":
        return PacketContextReference(
            ref_id=ref_id,
            ref_type=ref_type,
            title=title,
            path=path,
            summary=summary,
            required=required,
            sha256=sha256,
            metadata=_string_pairs("metadata", metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref_id": self.ref_id,
            "ref_type": self.ref_type,
            "title": self.title,
            "path": self.path,
            "summary": self.summary,
            "required": self.required,
            "sha256": self.sha256,
            "metadata": _pairs_to_lists(self.metadata),
        }


@dataclass(frozen=True)
class PromptPacket:
    """A deterministic, caller-authored prompt handed from one agent to another.

    ``created_at`` must be supplied explicitly (no clock is read).
    ``packet_id`` must be a caller-supplied, content-derived string — this
    model never hashes anything itself (see
    ``prompt_result_packet_builder.py`` for deterministic id derivation).
    """

    ok: bool
    schema_version: int
    packet_id: str
    packet_type: str
    session_id: str
    task_id: str
    source_agent: str
    target_agent: str
    target_runtime_id: str
    title: str
    objective: str
    prompt_body: str
    context_refs: tuple[PacketContextReference, ...]
    constraints: tuple[str, ...]
    expected_result_format: str
    expected_artifacts: tuple[str, ...]
    created_at: str
    status: str
    metadata: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "packet_id", str(self.packet_id))
        object.__setattr__(self, "packet_type", str(self.packet_type))
        object.__setattr__(self, "session_id", str(self.session_id))
        object.__setattr__(self, "task_id", str(self.task_id))
        object.__setattr__(self, "source_agent", str(self.source_agent))
        object.__setattr__(self, "target_agent", str(self.target_agent))
        object.__setattr__(self, "target_runtime_id", str(self.target_runtime_id))
        object.__setattr__(self, "title", str(self.title))
        object.__setattr__(self, "objective", str(self.objective))
        object.__setattr__(self, "prompt_body", str(self.prompt_body))
        context_refs = tuple(self.context_refs or ())
        for ref in context_refs:
            if not isinstance(ref, PacketContextReference):
                raise ValueError(
                    "context_refs entries must be PacketContextReference instances"
                )
        object.__setattr__(self, "context_refs", context_refs)
        object.__setattr__(
            self, "constraints", _string_tuple("constraints", self.constraints)
        )
        object.__setattr__(
            self, "expected_result_format", str(self.expected_result_format)
        )
        object.__setattr__(
            self,
            "expected_artifacts",
            _string_tuple("expected_artifacts", self.expected_artifacts),
        )
        object.__setattr__(self, "created_at", str(self.created_at))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "metadata", _string_pairs("metadata", self.metadata))

        _require_allowed("packet_type", self.packet_type, ALLOWED_PACKET_TYPES)
        _require_allowed("source_agent", self.source_agent, ALLOWED_PACKET_AGENT_NAMES)
        _require_allowed("target_agent", self.target_agent, ALLOWED_PACKET_AGENT_NAMES)
        _require_allowed("status", self.status, ALLOWED_PROMPT_PACKET_STATUSES)
        _require_nonempty("prompt_body", self.prompt_body)
        _require_nonempty("objective", self.objective)
        _require_nonempty("target_agent", self.target_agent)
        _reject_url("prompt_body", self.prompt_body)
        _check_metadata_safety("metadata", self.metadata)

    @staticmethod
    def of(
        packet_id: str,
        packet_type: str,
        session_id: str,
        task_id: str,
        source_agent: str,
        target_agent: str,
        target_runtime_id: str,
        title: str,
        objective: str,
        prompt_body: str,
        created_at: str,
        status: str,
        *,
        ok: bool = True,
        schema_version: int = PROMPT_RESULT_PACKET_SCHEMA_VERSION,
        context_refs: Any = (),
        constraints: Any = (),
        expected_result_format: str = "structured_report",
        expected_artifacts: Any = (),
        metadata: Any = (),
    ) -> "PromptPacket":
        return PromptPacket(
            ok=ok,
            schema_version=schema_version,
            packet_id=packet_id,
            packet_type=packet_type,
            session_id=session_id,
            task_id=task_id,
            source_agent=source_agent,
            target_agent=target_agent,
            target_runtime_id=target_runtime_id,
            title=title,
            objective=objective,
            prompt_body=prompt_body,
            context_refs=tuple(context_refs or ()),
            constraints=_string_tuple("constraints", constraints),
            expected_result_format=expected_result_format,
            expected_artifacts=_string_tuple("expected_artifacts", expected_artifacts),
            created_at=created_at,
            status=status,
            metadata=_string_pairs("metadata", metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "packet_id": self.packet_id,
            "packet_type": self.packet_type,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "source_agent": self.source_agent,
            "target_agent": self.target_agent,
            "target_runtime_id": self.target_runtime_id,
            "title": self.title,
            "objective": self.objective,
            "prompt_body": self.prompt_body,
            "context_refs": [ref.to_dict() for ref in self.context_refs],
            "constraints": list(self.constraints),
            "expected_result_format": self.expected_result_format,
            "expected_artifacts": list(self.expected_artifacts),
            "created_at": self.created_at,
            "status": self.status,
            "metadata": _pairs_to_lists(self.metadata),
        }


@dataclass(frozen=True)
class ResultArtifactReference:
    """A pointer to one piece of evidence/output attached to a ResultPacket."""

    artifact_id: str
    artifact_type: str
    path: str | None
    summary: str
    sha256: str | None
    required: bool
    metadata: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_id", str(self.artifact_id))
        object.__setattr__(self, "artifact_type", str(self.artifact_type))
        object.__setattr__(self, "path", _optional_str(self.path))
        object.__setattr__(self, "summary", str(self.summary))
        object.__setattr__(self, "sha256", _optional_str(self.sha256))
        object.__setattr__(self, "required", bool(self.required))
        object.__setattr__(self, "metadata", _string_pairs("metadata", self.metadata))
        _require_allowed(
            "artifact_type", self.artifact_type, ALLOWED_RESULT_ARTIFACT_TYPES
        )
        _require_nonempty("artifact_id", self.artifact_id)
        _require_nonempty("summary", self.summary)
        _reject_url("path", self.path)
        _check_metadata_safety("metadata", self.metadata)

    @staticmethod
    def of(
        artifact_id: str,
        artifact_type: str,
        summary: str,
        *,
        path: str | None = None,
        sha256: str | None = None,
        required: bool = False,
        metadata: Any = (),
    ) -> "ResultArtifactReference":
        return ResultArtifactReference(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            path=path,
            summary=summary,
            sha256=sha256,
            required=required,
            metadata=_string_pairs("metadata", metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "path": self.path,
            "summary": self.summary,
            "sha256": self.sha256,
            "required": self.required,
            "metadata": _pairs_to_lists(self.metadata),
        }


@dataclass(frozen=True)
class ResultPacket:
    """A deterministic, caller-authored result handed back for a PromptPacket.

    ``created_at`` must be supplied explicitly (no clock is read).
    ``result_packet_id`` must be a caller-supplied, content-derived string —
    this model never hashes anything itself.
    """

    ok: bool
    schema_version: int
    result_packet_id: str
    prompt_packet_id: str
    session_id: str
    task_id: str
    source_agent: str
    target_agent: str
    result_type: str
    verdict: str
    summary: str
    artifacts: tuple[ResultArtifactReference, ...]
    blockers: tuple[str, ...]
    next_action: str | None
    recommended_next_agent: str | None
    created_at: str
    status: str
    metadata: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "result_packet_id", str(self.result_packet_id))
        object.__setattr__(self, "prompt_packet_id", str(self.prompt_packet_id))
        object.__setattr__(self, "session_id", str(self.session_id))
        object.__setattr__(self, "task_id", str(self.task_id))
        object.__setattr__(self, "source_agent", str(self.source_agent))
        object.__setattr__(self, "target_agent", str(self.target_agent))
        object.__setattr__(self, "result_type", str(self.result_type))
        object.__setattr__(self, "verdict", str(self.verdict))
        object.__setattr__(self, "summary", str(self.summary))
        artifacts = tuple(self.artifacts or ())
        for artifact in artifacts:
            if not isinstance(artifact, ResultArtifactReference):
                raise ValueError(
                    "artifacts entries must be ResultArtifactReference instances"
                )
        object.__setattr__(self, "artifacts", artifacts)
        object.__setattr__(self, "blockers", _string_tuple("blockers", self.blockers))
        object.__setattr__(self, "next_action", _optional_str(self.next_action))
        object.__setattr__(
            self, "recommended_next_agent", _optional_str(self.recommended_next_agent)
        )
        object.__setattr__(self, "created_at", str(self.created_at))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "metadata", _string_pairs("metadata", self.metadata))

        _require_allowed("source_agent", self.source_agent, ALLOWED_PACKET_AGENT_NAMES)
        _require_allowed("target_agent", self.target_agent, ALLOWED_PACKET_AGENT_NAMES)
        _require_allowed("result_type", self.result_type, ALLOWED_RESULT_TYPES_PACKET)
        _require_allowed("verdict", self.verdict, ALLOWED_RESULT_VERDICTS)
        _require_allowed("status", self.status, ALLOWED_RESULT_PACKET_STATUSES)
        if self.recommended_next_agent is not None:
            _require_allowed(
                "recommended_next_agent",
                self.recommended_next_agent,
                ALLOWED_PACKET_AGENT_NAMES,
            )
        _require_nonempty("summary", self.summary)
        _check_metadata_safety("metadata", self.metadata)

    @staticmethod
    def of(
        result_packet_id: str,
        prompt_packet_id: str,
        session_id: str,
        task_id: str,
        source_agent: str,
        target_agent: str,
        result_type: str,
        verdict: str,
        summary: str,
        created_at: str,
        status: str,
        *,
        ok: bool = True,
        schema_version: int = PROMPT_RESULT_PACKET_SCHEMA_VERSION,
        artifacts: Any = (),
        blockers: Any = (),
        next_action: str | None = None,
        recommended_next_agent: str | None = None,
        metadata: Any = (),
    ) -> "ResultPacket":
        return ResultPacket(
            ok=ok,
            schema_version=schema_version,
            result_packet_id=result_packet_id,
            prompt_packet_id=prompt_packet_id,
            session_id=session_id,
            task_id=task_id,
            source_agent=source_agent,
            target_agent=target_agent,
            result_type=result_type,
            verdict=verdict,
            summary=summary,
            artifacts=tuple(artifacts or ()),
            blockers=_string_tuple("blockers", blockers),
            next_action=next_action,
            recommended_next_agent=recommended_next_agent,
            created_at=created_at,
            status=status,
            metadata=_string_pairs("metadata", metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "result_packet_id": self.result_packet_id,
            "prompt_packet_id": self.prompt_packet_id,
            "session_id": self.session_id,
            "task_id": self.task_id,
            "source_agent": self.source_agent,
            "target_agent": self.target_agent,
            "result_type": self.result_type,
            "verdict": self.verdict,
            "summary": self.summary,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "blockers": list(self.blockers),
            "next_action": self.next_action,
            "recommended_next_agent": self.recommended_next_agent,
            "created_at": self.created_at,
            "status": self.status,
            "metadata": _pairs_to_lists(self.metadata),
        }


@dataclass(frozen=True)
class PacketRoutingDecision:
    """A deterministic, non-executing recommendation for what happens next.

    Creating a ``PacketRoutingDecision`` never sends anything anywhere and
    never builds the next ``PromptPacket`` automatically — it only records a
    recommendation for a human (or a later stage) to act on.
    """

    decision_id: str
    source_result_packet_id: str
    next_agent: str
    next_packet_type: str
    reason: str
    priority: str
    requires_operator_approval: bool
    metadata: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_id", str(self.decision_id))
        object.__setattr__(
            self, "source_result_packet_id", str(self.source_result_packet_id)
        )
        object.__setattr__(self, "next_agent", str(self.next_agent))
        object.__setattr__(self, "next_packet_type", str(self.next_packet_type))
        object.__setattr__(self, "reason", str(self.reason))
        object.__setattr__(self, "priority", str(self.priority))
        object.__setattr__(
            self, "requires_operator_approval", bool(self.requires_operator_approval)
        )
        object.__setattr__(self, "metadata", _string_pairs("metadata", self.metadata))
        _require_allowed("next_agent", self.next_agent, ALLOWED_PACKET_AGENT_NAMES)
        _require_allowed("next_packet_type", self.next_packet_type, ALLOWED_PACKET_TYPES)
        _require_allowed("priority", self.priority, ALLOWED_ROUTING_PRIORITIES)
        _require_nonempty("reason", self.reason)
        _check_metadata_safety("metadata", self.metadata)

    @staticmethod
    def of(
        decision_id: str,
        source_result_packet_id: str,
        next_agent: str,
        next_packet_type: str,
        reason: str,
        *,
        priority: str = "normal",
        requires_operator_approval: bool = True,
        metadata: Any = (),
    ) -> "PacketRoutingDecision":
        return PacketRoutingDecision(
            decision_id=decision_id,
            source_result_packet_id=source_result_packet_id,
            next_agent=next_agent,
            next_packet_type=next_packet_type,
            reason=reason,
            priority=priority,
            requires_operator_approval=requires_operator_approval,
            metadata=_string_pairs("metadata", metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "source_result_packet_id": self.source_result_packet_id,
            "next_agent": self.next_agent,
            "next_packet_type": self.next_packet_type,
            "reason": self.reason,
            "priority": self.priority,
            "requires_operator_approval": self.requires_operator_approval,
            "metadata": _pairs_to_lists(self.metadata),
        }


@dataclass(frozen=True)
class PromptResultPacketError:
    """A deterministic, structured rejection for an invalid packet operation."""

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
        _require_allowed("error_kind", self.error_kind, ALLOWED_PACKET_ERROR_KINDS)

    @staticmethod
    def of(
        error_kind: str,
        error_detail: str,
        failed_step: str,
        *,
        ok: bool = False,
        schema_version: int = PROMPT_RESULT_PACKET_SCHEMA_VERSION,
        metadata: Any = (),
    ) -> "PromptResultPacketError":
        return PromptResultPacketError(
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
