"""SCOS Stage 5.4 Unified Prompt & Result Packet builder.

Pure, side-effect-free functions that construct ``PromptPacket``,
``ResultPacket``, and ``PacketRoutingDecision`` instances with deterministic,
content-derived ids. This module NEVER executes AI, calls an API, automates
a desktop app, opens a browser, touches a clipboard, or auto-dispatches a
routing recommendation — ``recommend_routing``/``create_routing_decision``
only ever produce data for a human (or a later stage) to act on.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid.
"""

from __future__ import annotations

import hashlib

try:
    from .prompt_result_packet_models import (
        ALLOWED_PACKET_AGENT_NAMES,
        ALLOWED_PACKET_TYPES,
        ALLOWED_RESULT_TYPES_PACKET,
        ALLOWED_RESULT_VERDICTS,
        ALLOWED_ROUTING_PRIORITIES,
        PacketContextReference,
        PacketRoutingDecision,
        PROMPT_RESULT_PACKET_SCHEMA_VERSION,
        PromptPacket,
        PromptResultPacketError,
        ResultArtifactReference,
        ResultPacket,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from prompt_result_packet_models import (
        ALLOWED_PACKET_AGENT_NAMES,
        ALLOWED_PACKET_TYPES,
        ALLOWED_RESULT_TYPES_PACKET,
        ALLOWED_RESULT_VERDICTS,
        ALLOWED_ROUTING_PRIORITIES,
        PacketContextReference,
        PacketRoutingDecision,
        PROMPT_RESULT_PACKET_SCHEMA_VERSION,
        PromptPacket,
        PromptResultPacketError,
        ResultArtifactReference,
        ResultPacket,
    )

PROMPT_RESULT_PACKET_BUILDER_SCHEMA_VERSION = 1

_ID_DIGEST_LENGTH = 16


def _fail(
    error_kind: str, error_detail: str, failed_step: str, metadata=()
) -> PromptResultPacketError:
    return PromptResultPacketError.of(
        error_kind, error_detail, failed_step, metadata=metadata
    )


def _check_agent(field_name: str, value) -> PromptResultPacketError | None:
    if value not in ALLOWED_PACKET_AGENT_NAMES:
        return _fail(
            "invalid_agent",
            f"{field_name}={value!r} is not a recognized agent",
            field_name,
        )
    return None


def _check_packet_type(value) -> PromptResultPacketError | None:
    if value not in ALLOWED_PACKET_TYPES:
        return _fail(
            "invalid_packet_type", f"packet_type={value!r} is not recognized", "packet_type"
        )
    return None


def _check_result_type(value) -> PromptResultPacketError | None:
    if value not in ALLOWED_RESULT_TYPES_PACKET:
        return _fail(
            "invalid_result_type", f"result_type={value!r} is not recognized", "result_type"
        )
    return None


def _check_verdict(value) -> PromptResultPacketError | None:
    if value not in ALLOWED_RESULT_VERDICTS:
        return _fail("invalid_verdict", f"verdict={value!r} is not recognized", "verdict")
    return None


def _check_priority(value) -> PromptResultPacketError | None:
    if value not in ALLOWED_ROUTING_PRIORITIES:
        return _fail("invalid_priority", f"priority={value!r} is not recognized", "priority")
    return None


def _check_nonempty(field_name: str, value) -> PromptResultPacketError | None:
    if value is None or not str(value).strip():
        return _fail(
            "empty_required_field", f"{field_name} must not be empty", field_name
        )
    return None


def _check_collection(field_name: str, value) -> PromptResultPacketError | None:
    if value is not None and not isinstance(value, (tuple, list)):
        return _fail(
            "invalid_collection_type",
            f"{field_name} must be a tuple or list",
            field_name,
        )
    return None


def _derive_packet_id(
    *, session_id, task_id, packet_type, source_agent, target_agent, title, created_at
) -> str:
    digest = hashlib.sha256(
        "|".join(
            (session_id, task_id, packet_type, source_agent, target_agent, title, created_at)
        ).encode("utf-8")
    ).hexdigest()[:_ID_DIGEST_LENGTH]
    return f"pp-{digest}"


def _derive_result_packet_id(
    *, prompt_packet_id, source_agent, target_agent, result_type, verdict, created_at
) -> str:
    digest = hashlib.sha256(
        "|".join(
            (prompt_packet_id, source_agent, target_agent, result_type, verdict, created_at)
        ).encode("utf-8")
    ).hexdigest()[:_ID_DIGEST_LENGTH]
    return f"rp-{digest}"


def _derive_decision_id(
    *, source_result_packet_id, next_agent, next_packet_type, reason, priority
) -> str:
    digest = hashlib.sha256(
        "|".join(
            (source_result_packet_id, next_agent, next_packet_type, reason, priority)
        ).encode("utf-8")
    ).hexdigest()[:_ID_DIGEST_LENGTH]
    return f"rd-{digest}"


def create_prompt_packet(
    *,
    session_id: str,
    task_id: str,
    packet_type: str,
    source_agent: str,
    target_agent: str,
    target_runtime_id: str,
    title: str,
    objective: str,
    prompt_body: str,
    created_at: str,
    context_refs=None,
    constraints=None,
    expected_result_format: str = "structured_report",
    expected_artifacts=None,
    metadata=None,
) -> PromptPacket | PromptResultPacketError:
    for check in (
        _check_agent("source_agent", source_agent),
        _check_agent("target_agent", target_agent),
        _check_packet_type(packet_type),
        _check_nonempty("objective", objective),
        _check_nonempty("prompt_body", prompt_body),
        _check_nonempty("target_agent", target_agent),
        _check_nonempty("created_at", created_at),
        _check_collection("context_refs", context_refs),
        _check_collection("constraints", constraints),
        _check_collection("expected_artifacts", expected_artifacts),
    ):
        if check is not None:
            return check

    resolved_refs = tuple(context_refs or ())
    for ref in resolved_refs:
        if not isinstance(ref, PacketContextReference):
            return _fail(
                "invalid_ref_type",
                "context_refs entries must be PacketContextReference instances",
                "context_refs",
            )

    packet_id = _derive_packet_id(
        session_id=session_id,
        task_id=task_id,
        packet_type=packet_type,
        source_agent=source_agent,
        target_agent=target_agent,
        title=title,
        created_at=created_at,
    )
    try:
        return PromptPacket.of(
            packet_id,
            packet_type,
            session_id,
            task_id,
            source_agent,
            target_agent,
            target_runtime_id,
            title,
            objective,
            prompt_body,
            created_at,
            "drafted",
            context_refs=resolved_refs,
            constraints=constraints or (),
            expected_result_format=expected_result_format,
            expected_artifacts=expected_artifacts or (),
            metadata=metadata or (),
        )
    except ValueError as exc:
        return _fail("contract_violation", str(exc), "PromptPacket.of")


def create_result_packet(
    *,
    prompt_packet: PromptPacket,
    result_type: str,
    verdict: str,
    summary: str,
    created_at: str,
    artifacts=None,
    blockers=None,
    next_action: str | None = None,
    recommended_next_agent: str | None = None,
    metadata=None,
) -> ResultPacket | PromptResultPacketError:
    if not isinstance(prompt_packet, PromptPacket):
        return _fail(
            "contract_violation", "prompt_packet must be a PromptPacket", "prompt_packet"
        )
    for check in (
        _check_result_type(result_type),
        _check_verdict(verdict),
        _check_nonempty("summary", summary),
        _check_nonempty("created_at", created_at),
        _check_collection("artifacts", artifacts),
        _check_collection("blockers", blockers),
    ):
        if check is not None:
            return check
    if recommended_next_agent is not None:
        agent_check = _check_agent("recommended_next_agent", recommended_next_agent)
        if agent_check is not None:
            return agent_check

    resolved_artifacts = tuple(artifacts or ())
    for artifact in resolved_artifacts:
        if not isinstance(artifact, ResultArtifactReference):
            return _fail(
                "invalid_artifact_type",
                "artifacts entries must be ResultArtifactReference instances",
                "artifacts",
            )

    result_packet_id = _derive_result_packet_id(
        prompt_packet_id=prompt_packet.packet_id,
        source_agent=prompt_packet.target_agent,
        target_agent=prompt_packet.source_agent,
        result_type=result_type,
        verdict=verdict,
        created_at=created_at,
    )
    try:
        return ResultPacket.of(
            result_packet_id,
            prompt_packet.packet_id,
            prompt_packet.session_id,
            prompt_packet.task_id,
            prompt_packet.target_agent,
            prompt_packet.source_agent,
            result_type,
            verdict,
            summary,
            created_at,
            "received",
            artifacts=resolved_artifacts,
            blockers=blockers or (),
            next_action=next_action,
            recommended_next_agent=recommended_next_agent,
            metadata=metadata or (),
        )
    except ValueError as exc:
        return _fail("contract_violation", str(exc), "ResultPacket.of")


def create_routing_decision(
    *,
    result_packet: ResultPacket,
    next_agent: str,
    next_packet_type: str,
    reason: str,
    priority: str = "normal",
    requires_operator_approval: bool = True,
    metadata=None,
) -> PacketRoutingDecision | PromptResultPacketError:
    if not isinstance(result_packet, ResultPacket):
        return _fail(
            "contract_violation", "result_packet must be a ResultPacket", "result_packet"
        )
    for check in (
        _check_agent("next_agent", next_agent),
        _check_packet_type(next_packet_type),
        _check_priority(priority),
        _check_nonempty("reason", reason),
    ):
        if check is not None:
            return check

    decision_id = _derive_decision_id(
        source_result_packet_id=result_packet.result_packet_id,
        next_agent=next_agent,
        next_packet_type=next_packet_type,
        reason=reason,
        priority=priority,
    )
    try:
        return PacketRoutingDecision.of(
            decision_id,
            result_packet.result_packet_id,
            next_agent,
            next_packet_type,
            reason,
            priority=priority,
            requires_operator_approval=requires_operator_approval,
            metadata=metadata or (),
        )
    except ValueError as exc:
        return _fail("contract_violation", str(exc), "PacketRoutingDecision.of")


def create_followup_prompt_from_result(
    *,
    result_packet: ResultPacket,
    target_agent: str,
    target_runtime_id: str,
    packet_type: str,
    title: str,
    objective: str,
    prompt_body: str,
    created_at: str,
    constraints=None,
    expected_result_format: str = "structured_report",
    expected_artifacts=None,
    metadata=None,
) -> PromptPacket | PromptResultPacketError:
    if not isinstance(result_packet, ResultPacket):
        return _fail(
            "contract_violation", "result_packet must be a ResultPacket", "result_packet"
        )
    return create_prompt_packet(
        session_id=result_packet.session_id,
        task_id=result_packet.task_id,
        packet_type=packet_type,
        source_agent=result_packet.target_agent,
        target_agent=target_agent,
        target_runtime_id=target_runtime_id,
        title=title,
        objective=objective,
        prompt_body=prompt_body,
        created_at=created_at,
        context_refs=None,
        constraints=constraints,
        expected_result_format=expected_result_format,
        expected_artifacts=expected_artifacts,
        metadata=metadata,
    )


# (result_type, verdict) -> (next_agent, next_packet_type)
# "any FAIL" / "any BLOCKED" are handled as a universal escalation check
# (see recommend_routing), not as individual dict entries per result_type.
_ROUTING_RECOMMENDATIONS: dict[tuple[str, str], tuple[str, str]] = {
    ("planning_result", "PASS"): ("claude_code", "implementation_prompt"),
    ("implementation_result", "PASS"): ("codex", "review_prompt"),
    ("implementation_result", "NEEDS_FIX"): ("claude_code", "implementation_prompt"),
    ("review_result", "PASS"): ("hermes", "audit_prompt"),
    ("review_result", "NEEDS_FIX"): ("claude_code", "implementation_prompt"),
    ("audit_result", "PASS"): ("chatgpt", "status_update_prompt"),
    ("audit_result", "BLOCKED"): ("operator", "manual_handoff_prompt"),
}

# Alternate recommendation for review_result PASS, per spec ("... -> hermes
# audit_prompt or chatgpt status_update_prompt"): the primary above keeps the
# audit stage in the loop by default; this alternate offers the lighter
# path via recommend_routing(..., alternate=True).
_ALTERNATE_ROUTING_RECOMMENDATIONS: dict[tuple[str, str], tuple[str, str]] = {
    ("review_result", "PASS"): ("chatgpt", "status_update_prompt"),
}

_UNIVERSAL_ESCALATION_VERDICTS = ("FAIL", "BLOCKED")
_ESCALATION_TARGET: tuple[str, str] = ("operator", "manual_handoff_prompt")


def recommend_routing(
    *, result_type: str, verdict: str, alternate: bool = False
) -> tuple[str, str] | None:
    """Return (next_agent, next_packet_type), or None if no recommendation.

    This is a pure lookup — it never creates a PacketRoutingDecision and
    never dispatches anything. Any FAIL or BLOCKED verdict always escalates
    to operator/manual_handoff_prompt regardless of result_type, taking
    precedence over any result_type-specific entry.
    """
    if verdict in _UNIVERSAL_ESCALATION_VERDICTS:
        return _ESCALATION_TARGET
    if alternate and (result_type, verdict) in _ALTERNATE_ROUTING_RECOMMENDATIONS:
        return _ALTERNATE_ROUTING_RECOMMENDATIONS[(result_type, verdict)]
    return _ROUTING_RECOMMENDATIONS.get((result_type, verdict))
