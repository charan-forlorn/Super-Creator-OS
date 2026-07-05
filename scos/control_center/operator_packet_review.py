"""SCOS Stage 5.5 Operator Packet Review logic.

Pure validation and deterministic decision orchestration for Stage 5.4
prompt/result packets. This module never dispatches a packet, executes a
command, touches a clipboard, opens an app/browser, calls a network API, or
uses clock/random/uuid state.
"""

from __future__ import annotations

from typing import Any

try:
    from .manual_handoff_package import create_manual_handoff_package
    from .operator_packet_review_models import (
        ALLOWED_OPERATOR_DECIDED_BY,
        ALLOWED_OPERATOR_PACKET_DECISIONS,
        ALLOWED_REVIEW_AGENT_NAMES,
        OPERATOR_PACKET_REVIEW_SCHEMA_VERSION,
        OperatorPacketDecision,
        OperatorPacketReviewError,
        OperatorPacketReviewResult,
        PacketReviewCheck,
    )
    from .runtime_registry import get_runtime
except ImportError:  # direct-module execution (tests insert the package dir)
    from manual_handoff_package import create_manual_handoff_package
    from operator_packet_review_models import (
        ALLOWED_OPERATOR_DECIDED_BY,
        ALLOWED_OPERATOR_PACKET_DECISIONS,
        ALLOWED_REVIEW_AGENT_NAMES,
        OPERATOR_PACKET_REVIEW_SCHEMA_VERSION,
        OperatorPacketDecision,
        OperatorPacketReviewError,
        OperatorPacketReviewResult,
        PacketReviewCheck,
    )
    from runtime_registry import get_runtime

OPERATOR_PACKET_REVIEW_LOGIC_SCHEMA_VERSION = 1

_FORBIDDEN_METADATA_KEY_MARKERS = (
    "api_key",
    "token",
    "secret",
    "password",
    "private_key",
)
_URL_PREFIXES = ("http://", "https://")


def _check(
    name: str,
    status: str,
    severity: str,
    *,
    packet_id: str | None = None,
    error_kind: str | None = None,
    error_detail: str | None = None,
    metadata=None,
) -> PacketReviewCheck:
    return PacketReviewCheck.of(
        name,
        status,
        severity,
        packet_id=packet_id,
        error_kind=error_kind,
        error_detail=error_detail,
        metadata=metadata,
    )


def _fail(
    error_kind: str,
    error_detail: str,
    failed_step: str,
    *,
    checks=(),
    metadata=None,
) -> OperatorPacketReviewError:
    try:
        return OperatorPacketReviewError.of(
            error_kind,
            error_detail,
            failed_step,
            checks=checks,
            metadata=metadata,
        )
    except ValueError:
        return OperatorPacketReviewError.of(
            error_kind,
            error_detail,
            failed_step,
            checks=checks,
            metadata={"unsafe_metadata_rejected": "true"},
        )


def _has_url(value: Any) -> bool:
    lowered = str(value).lower()
    return any(marker in lowered for marker in _URL_PREFIXES)


def _packet_primary_id(packet: Any) -> str | None:
    return getattr(packet, "packet_id", None) or getattr(packet, "prompt_packet_id", None)


def _packet_result_id(packet: Any) -> str | None:
    return getattr(packet, "result_packet_id", None)


def _routing_id(routing_decision: Any) -> str | None:
    if routing_decision is None:
        return None
    return getattr(routing_decision, "decision_id", None)


def _routing_target_agent(routing_decision: Any) -> str | None:
    if routing_decision is None:
        return None
    return getattr(routing_decision, "next_agent", None)


def _metadata_pairs(value: Any) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    if hasattr(value, "items"):
        items = value.items()
    else:
        items = value
    pairs: list[tuple[str, str]] = []
    for item in items:
        pair = tuple(item)
        if len(pair) != 2:
            raise ValueError(f"metadata entries must be (key, value), got {item!r}")
        pairs.append((str(pair[0]), str(pair[1])))
    return tuple(pairs)


def _metadata_secret_errors(metadata: Any) -> tuple[str, ...]:
    errors: list[str] = []
    try:
        pairs = _metadata_pairs(metadata)
    except ValueError as exc:
        return (str(exc),)
    for key, value in pairs:
        lowered_key = key.lower()
        for marker in _FORBIDDEN_METADATA_KEY_MARKERS:
            if marker in lowered_key:
                errors.append(f"secret-like metadata key {key!r}")
        if _has_url(value):
            errors.append(f"URL-like metadata value for key {key!r}")
    return tuple(errors)


def _collect_packet_metadata(packet: Any) -> tuple[tuple[str, Any], ...]:
    collected: list[tuple[str, Any]] = [("packet.metadata", getattr(packet, "metadata", None))]
    for index, ref in enumerate(tuple(getattr(packet, "context_refs", ()) or ())):
        collected.append((f"context_refs[{index}].metadata", getattr(ref, "metadata", None)))
    for index, artifact in enumerate(tuple(getattr(packet, "artifacts", ()) or ())):
        collected.append((f"artifacts[{index}].metadata", getattr(artifact, "metadata", None)))
    return tuple(collected)


def _collect_path_errors(packet: Any) -> tuple[str, ...]:
    errors: list[str] = []
    for index, ref in enumerate(tuple(getattr(packet, "context_refs", ()) or ())):
        path = getattr(ref, "path", None)
        if path is not None and _has_url(path):
            errors.append(f"context_refs[{index}].path is URL-like")
    for index, artifact in enumerate(tuple(getattr(packet, "artifacts", ()) or ())):
        path = getattr(artifact, "path", None)
        if path is not None and _has_url(path):
            errors.append(f"artifacts[{index}].path is URL-like")
    return tuple(errors)


def _runtime_check(target_runtime_id: str | None) -> PacketReviewCheck:
    if not target_runtime_id:
        return _check(
            "target_runtime_present",
            "skipped",
            "info",
            error_kind=None,
            error_detail="No runtime id supplied for this decision",
        )
    runtime = get_runtime(target_runtime_id)
    if runtime is not None:
        return _check(
            "target_runtime_known",
            "success",
            "info",
            metadata={"runtime_id": target_runtime_id},
        )
    return _check(
        "target_runtime_known",
        "skipped",
        "warning",
        error_kind="runtime_not_in_local_registry",
        error_detail=(
            "Runtime id is not in the local registry; treating as warning "
            "because Stage 5.4 packets may carry runtime type ids."
        ),
        metadata={"runtime_id": target_runtime_id},
    )


def _checks_blocking(checks: tuple[PacketReviewCheck, ...]) -> bool:
    return any(
        check.status == "failure" and check.severity in ("error", "critical")
        for check in checks
    )


def _has_critical_failure(checks: tuple[PacketReviewCheck, ...]) -> bool:
    return any(check.status == "failure" and check.severity == "critical" for check in checks)


def _resolve_target_agent(
    *, packet: Any, routing_decision: Any, target_agent: str | None
) -> str | None:
    return (
        target_agent
        or _routing_target_agent(routing_decision)
        or getattr(packet, "target_agent", None)
        or getattr(packet, "recommended_next_agent", None)
    )


def _resolve_target_runtime_id(
    *, packet: Any, target_runtime_id: str | None
) -> str | None:
    return target_runtime_id or getattr(packet, "target_runtime_id", None)


def validate_packet_for_operator_review(
    *,
    packet,
    routing_decision=None,
    metadata=None,
) -> tuple[PacketReviewCheck, ...]:
    packet_id = _packet_primary_id(packet)
    checks: list[PacketReviewCheck] = []
    if packet_id:
        checks.append(
            _check("packet_id_present", "success", "info", packet_id=packet_id)
        )
    else:
        checks.append(
            _check(
                "packet_id_present",
                "failure",
                "critical",
                error_kind="invalid_packet",
                error_detail="packet must expose packet_id or prompt_packet_id",
            )
        )

    for field_name, value in _collect_packet_metadata(packet):
        errors = _metadata_secret_errors(value)
        if errors:
            checks.append(
                _check(
                    "metadata_safe",
                    "failure",
                    "critical",
                    packet_id=packet_id,
                    error_kind="unsafe_metadata",
                    error_detail=f"{field_name}: {'; '.join(errors)}",
                )
            )
        else:
            checks.append(
                _check(
                    "metadata_safe",
                    "success",
                    "info",
                    packet_id=packet_id,
                    metadata={"field": field_name},
                )
            )

    path_errors = _collect_path_errors(packet)
    if path_errors:
        checks.append(
            _check(
                "packet_paths_local",
                "failure",
                "critical",
                packet_id=packet_id,
                error_kind="unsafe_path",
                error_detail="; ".join(path_errors),
            )
        )
    else:
        checks.append(
            _check("packet_paths_local", "success", "info", packet_id=packet_id)
        )

    routing_id = _routing_id(routing_decision)
    if routing_decision is None:
        checks.append(
            _check(
                "routing_decision_present",
                "skipped",
                "info",
                packet_id=packet_id,
                error_detail="No routing decision supplied",
            )
        )
    elif routing_id:
        checks.append(
            _check(
                "routing_decision_present",
                "success",
                "info",
                packet_id=packet_id,
                metadata={"routing_decision_id": routing_id},
            )
        )
    else:
        checks.append(
            _check(
                "routing_decision_present",
                "failure",
                "error",
                packet_id=packet_id,
                error_kind="invalid_routing_decision",
                error_detail="routing_decision must expose decision_id",
            )
        )

    metadata_errors = _metadata_secret_errors(metadata)
    if metadata_errors:
        checks.append(
            _check(
                "review_metadata_safe",
                "failure",
                "critical",
                packet_id=packet_id,
                error_kind="unsafe_metadata",
                error_detail="; ".join(metadata_errors),
            )
        )
    else:
        checks.append(
            _check("review_metadata_safe", "success", "info", packet_id=packet_id)
        )
    return tuple(checks)


def _review_packet(
    *,
    packet,
    routing_decision,
    decision: str,
    decided_by: str,
    decided_at: str,
    reason: str,
    target_agent: str | None,
    target_runtime_id: str | None,
    create_handoff: bool,
    handoff_output_dir,
    metadata,
) -> OperatorPacketReviewResult | OperatorPacketReviewError:
    packet_checks = validate_packet_for_operator_review(
        packet=packet,
        routing_decision=routing_decision,
        metadata=metadata,
    )
    checks = list(packet_checks)
    packet_id = _packet_primary_id(packet) or ""
    result_packet_id = _packet_result_id(packet)
    routing_decision_id = _routing_id(routing_decision)

    if not str(decision).strip():
        return _fail(
            "invalid_decision",
            "decision must not be empty",
            "decision",
            checks=checks,
            metadata=metadata,
        )
    if decision not in ALLOWED_OPERATOR_PACKET_DECISIONS:
        return _fail(
            "invalid_decision",
            f"decision={decision!r} is not recognized",
            "decision",
            checks=checks,
            metadata=metadata,
        )
    if decided_by not in ALLOWED_OPERATOR_DECIDED_BY:
        return _fail(
            "invalid_decided_by",
            f"decided_by={decided_by!r} is not recognized",
            "decided_by",
            checks=checks,
            metadata=metadata,
        )
    if not str(decided_at).strip():
        return _fail(
            "missing_required_field",
            "decided_at must be caller-supplied",
            "decided_at",
            checks=checks,
            metadata=metadata,
        )
    if not str(reason).strip():
        return _fail(
            "missing_required_field",
            "reason must not be empty",
            "reason",
            checks=checks,
            metadata=metadata,
        )

    resolved_agent = _resolve_target_agent(
        packet=packet, routing_decision=routing_decision, target_agent=target_agent
    )
    resolved_runtime_id = _resolve_target_runtime_id(
        packet=packet, target_runtime_id=target_runtime_id
    )
    if resolved_agent is not None and resolved_agent not in ALLOWED_REVIEW_AGENT_NAMES:
        return _fail(
            "unsupported_agent",
            f"target_agent={resolved_agent!r} is not recognized",
            "target_agent",
            checks=checks,
            metadata=metadata,
        )
    checks.append(_runtime_check(resolved_runtime_id))

    if decision == "approve" and _checks_blocking(tuple(checks)):
        return _fail(
            "validation_failed",
            "approve is valid only when packet checks pass",
            "approve",
            checks=checks,
            metadata=metadata,
        )
    if decision == "manual_handoff":
        if not resolved_agent:
            return _fail(
                "missing_required_field",
                "manual_handoff requires target_agent",
                "target_agent",
                checks=checks,
                metadata=metadata,
            )
        if not resolved_runtime_id:
            return _fail(
                "missing_required_field",
                "manual_handoff requires target_runtime_id",
                "target_runtime_id",
                checks=checks,
                metadata=metadata,
            )
        if not create_handoff:
            return _fail(
                "handoff_required",
                "manual_handoff requires create_handoff=True",
                "create_handoff",
                checks=checks,
                metadata=metadata,
            )
    if create_handoff and handoff_output_dir is None:
        return _fail(
            "missing_required_field",
            "create_handoff=True requires handoff_output_dir",
            "handoff_output_dir",
            checks=checks,
            metadata=metadata,
        )

    if decision == "blocked" and _has_critical_failure(tuple(checks)):
        checks.append(
            _check(
                "blocked_by_critical_check",
                "success",
                "info",
                packet_id=packet_id,
            )
        )

    handoff_package = None
    if create_handoff and decision in ("approve", "manual_handoff"):
        if not resolved_agent:
            return _fail(
                "missing_required_field",
                "handoff package requires target_agent",
                "target_agent",
                checks=checks,
                metadata=metadata,
            )
        if not resolved_runtime_id:
            return _fail(
                "missing_required_field",
                "handoff package requires target_runtime_id",
                "target_runtime_id",
                checks=checks,
                metadata=metadata,
            )
        handoff = create_manual_handoff_package(
            packet=packet,
            routing_decision=routing_decision,
            target_agent=resolved_agent,
            target_runtime_id=resolved_runtime_id,
            output_dir=handoff_output_dir,
            created_at=decided_at,
            metadata=metadata,
        )
        if isinstance(handoff, OperatorPacketReviewError):
            return _fail(
                "handoff_failed",
                handoff.error_detail,
                "create_manual_handoff_package",
                checks=tuple(checks) + handoff.checks,
                metadata=metadata,
            )
        handoff_package = handoff

    try:
        operator_decision = OperatorPacketDecision.of(
            packet_id=packet_id,
            routing_decision_id=routing_decision_id,
            decision=decision,
            decided_by=decided_by,
            decided_at=decided_at,
            reason=reason,
            target_agent=resolved_agent,
            target_runtime_id=resolved_runtime_id,
            requires_manual_handoff=decision == "manual_handoff",
            checks=tuple(checks),
            metadata=metadata,
        )
        return OperatorPacketReviewResult.of(
            packet_id=packet_id,
            result_packet_id=result_packet_id,
            routing_decision_id=routing_decision_id,
            reviewed_at=decided_at,
            decision=operator_decision,
            handoff_package=handoff_package,
            checks=tuple(checks),
            output_path=handoff_package.manifest_path if handoff_package else None,
            metadata=metadata,
        )
    except ValueError as exc:
        return _fail(
            "contract_violation",
            str(exc),
            "build_review_result",
            checks=checks,
            metadata=metadata,
        )


def review_prompt_packet(
    *,
    prompt_packet,
    routing_decision=None,
    decision: str,
    decided_by: str = "operator",
    decided_at: str,
    reason: str,
    target_agent: str | None = None,
    target_runtime_id: str | None = None,
    create_handoff: bool = False,
    handoff_output_dir=None,
    metadata=None,
) -> OperatorPacketReviewResult | OperatorPacketReviewError:
    return _review_packet(
        packet=prompt_packet,
        routing_decision=routing_decision,
        decision=decision,
        decided_by=decided_by,
        decided_at=decided_at,
        reason=reason,
        target_agent=target_agent,
        target_runtime_id=target_runtime_id,
        create_handoff=create_handoff,
        handoff_output_dir=handoff_output_dir,
        metadata=metadata,
    )


def review_result_packet(
    *,
    result_packet,
    routing_decision=None,
    decision: str,
    decided_by: str = "operator",
    decided_at: str,
    reason: str,
    target_agent: str | None = None,
    target_runtime_id: str | None = None,
    create_handoff: bool = False,
    handoff_output_dir=None,
    metadata=None,
) -> OperatorPacketReviewResult | OperatorPacketReviewError:
    return _review_packet(
        packet=result_packet,
        routing_decision=routing_decision,
        decision=decision,
        decided_by=decided_by,
        decided_at=decided_at,
        reason=reason,
        target_agent=target_agent,
        target_runtime_id=target_runtime_id,
        create_handoff=create_handoff,
        handoff_output_dir=handoff_output_dir,
        metadata=metadata,
    )
