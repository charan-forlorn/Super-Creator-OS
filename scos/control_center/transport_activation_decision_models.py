"""Stage 8.1 immutable local transport activation decision models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

LOCAL_TRANSPORT_ACTIVATION_DECISION_SCHEMA_VERSION = 1

TRANSPORT_ACTIVATION_OPTIONS = (
    "NO_TRANSPORT",
    "FILE_SNAPSHOT_REFRESH",
    "LOCAL_HTTP",
    "WEBSOCKET",
    "SSE_EVENTSOURCE",
    "POLLING",
)

TRANSPORT_ACTIVATION_DECISIONS = (
    "NO_TRANSPORT",
    "FILE_SNAPSHOT_REFRESH_ALLOWED_LATER",
    "LOCAL_HTTP_ALLOWED_LATER",
    "WEBSOCKET_ALLOWED_LATER",
    "SSE_EVENTSOURCE_ALLOWED_LATER",
    "POLLING_ALLOWED_LATER",
    "BLOCK_TRANSPORT_ACTIVATION",
)

TRANSPORT_ACTIVATION_GO_NO_GO = ("GO", "NO_GO", "BLOCKED")
TRANSPORT_ACTIVATION_REQUIREMENT_STATUSES = ("pass", "warning", "blocker")


def _require_allowed(field_name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ValueError(f"{field_name} must be one of {list(allowed)}, got {value!r}")


def _strings(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    return tuple(sorted(str(value) for value in values))


def _pairs(values: Any) -> tuple[tuple[str, str], ...]:
    if values is None:
        return ()
    pairs: list[tuple[str, str]] = []
    for value in values:
        pair = tuple(value)
        if len(pair) != 2:
            raise ValueError(f"metadata entries must be pairs, got {value!r}")
        pairs.append((str(pair[0]), str(pair[1])))
    return tuple(sorted(pairs, key=lambda pair: pair[0]))


@dataclass(frozen=True)
class TransportOptionAnalysis:
    option: str
    description: str
    security_risk: str
    operational_risk: str
    localhost_boundary: str
    approval_requirements: tuple[str, ...]
    audit_requirements: tuple[str, ...]
    rollback_requirements: tuple[str, ...]
    test_requirements: tuple[str, ...]
    forbidden_behaviors: tuple[str, ...]
    recommendation: str
    locality_boundary: str
    origin_csrf_local_exposure_risk: str
    stale_data_risk: str
    event_ordering_risk: str
    accidental_command_execution_risk: str
    adapter_dispatch_risk: str
    credential_exposure_risk: str
    rollback_kill_switch_requirement: str
    operator_approval_preservation: str
    deterministic_testability: str

    def __post_init__(self) -> None:
        for field_name in (
            "option",
            "description",
            "security_risk",
            "operational_risk",
            "localhost_boundary",
            "recommendation",
            "locality_boundary",
            "origin_csrf_local_exposure_risk",
            "stale_data_risk",
            "event_ordering_risk",
            "accidental_command_execution_risk",
            "adapter_dispatch_risk",
            "credential_exposure_risk",
            "rollback_kill_switch_requirement",
            "operator_approval_preservation",
            "deterministic_testability",
        ):
            object.__setattr__(self, field_name, str(getattr(self, field_name)))
        object.__setattr__(self, "approval_requirements", _strings(self.approval_requirements))
        object.__setattr__(self, "audit_requirements", _strings(self.audit_requirements))
        object.__setattr__(self, "rollback_requirements", _strings(self.rollback_requirements))
        object.__setattr__(self, "test_requirements", _strings(self.test_requirements))
        object.__setattr__(self, "forbidden_behaviors", _strings(self.forbidden_behaviors))
        _require_allowed("option", self.option, TRANSPORT_ACTIVATION_OPTIONS)

    def to_dict(self) -> dict[str, Any]:
        return {
            "option": self.option,
            "description": self.description,
            "security_risk": self.security_risk,
            "operational_risk": self.operational_risk,
            "localhost_boundary": self.localhost_boundary,
            "approval_requirements": list(self.approval_requirements),
            "audit_requirements": list(self.audit_requirements),
            "rollback_requirements": list(self.rollback_requirements),
            "test_requirements": list(self.test_requirements),
            "forbidden_behaviors": list(self.forbidden_behaviors),
            "recommendation": self.recommendation,
            "locality_boundary": self.locality_boundary,
            "origin_csrf_local_exposure_risk": self.origin_csrf_local_exposure_risk,
            "stale_data_risk": self.stale_data_risk,
            "event_ordering_risk": self.event_ordering_risk,
            "accidental_command_execution_risk": self.accidental_command_execution_risk,
            "adapter_dispatch_risk": self.adapter_dispatch_risk,
            "credential_exposure_risk": self.credential_exposure_risk,
            "rollback_kill_switch_requirement": self.rollback_kill_switch_requirement,
            "operator_approval_preservation": self.operator_approval_preservation,
            "deterministic_testability": self.deterministic_testability,
        }


@dataclass(frozen=True)
class TransportSafetyRequirement:
    requirement_id: str
    category: str
    requirement: str
    status: str
    applies_to: tuple[str, ...]
    evidence: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "requirement_id", str(self.requirement_id))
        object.__setattr__(self, "category", str(self.category))
        object.__setattr__(self, "requirement", str(self.requirement))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "applies_to", _strings(self.applies_to))
        object.__setattr__(self, "evidence", _strings(self.evidence))
        object.__setattr__(self, "metadata", _pairs(self.metadata))
        _require_allowed("status", self.status, TRANSPORT_ACTIVATION_REQUIREMENT_STATUSES)

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "category": self.category,
            "requirement": self.requirement,
            "status": self.status,
            "applies_to": list(self.applies_to),
            "evidence": list(self.evidence),
            "metadata": [[key, value] for key, value in self.metadata],
        }


@dataclass(frozen=True)
class TransportDecisionBlocker:
    blocker_id: str
    code: str
    severity: str
    message: str
    evidence: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "blocker_id", str(self.blocker_id))
        object.__setattr__(self, "code", str(self.code))
        object.__setattr__(self, "severity", str(self.severity))
        object.__setattr__(self, "message", str(self.message))
        object.__setattr__(self, "evidence", _strings(self.evidence))

    def to_dict(self) -> dict[str, Any]:
        return {
            "blocker_id": self.blocker_id,
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class TransportDecisionRecord:
    decision_id: str
    decision: str
    requested_decision: str
    decided_at: str
    allow_future_implementation: bool
    future_implementation_requires_later_stage: bool
    recommended_next_stage: str
    decision_summary: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_id", str(self.decision_id))
        object.__setattr__(self, "decision", str(self.decision))
        object.__setattr__(self, "requested_decision", str(self.requested_decision))
        object.__setattr__(self, "decided_at", str(self.decided_at))
        object.__setattr__(self, "allow_future_implementation", bool(self.allow_future_implementation))
        object.__setattr__(
            self,
            "future_implementation_requires_later_stage",
            bool(self.future_implementation_requires_later_stage),
        )
        object.__setattr__(self, "recommended_next_stage", str(self.recommended_next_stage))
        object.__setattr__(self, "decision_summary", str(self.decision_summary))
        _require_allowed("decision", self.decision, TRANSPORT_ACTIVATION_DECISIONS)
        _require_allowed("requested_decision", self.requested_decision, TRANSPORT_ACTIVATION_DECISIONS)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "decision": self.decision,
            "requested_decision": self.requested_decision,
            "decided_at": self.decided_at,
            "allow_future_implementation": self.allow_future_implementation,
            "future_implementation_requires_later_stage": self.future_implementation_requires_later_stage,
            "recommended_next_stage": self.recommended_next_stage,
            "decision_summary": self.decision_summary,
        }


@dataclass(frozen=True)
class LocalTransportActivationDecisionResult:
    gate_id: str
    gate_name: str
    decided_at: str
    go_no_go: str
    readiness_score: int
    accepted: bool
    can_implement_now: bool
    transport_implemented: bool
    dispatch_blocked: bool
    decision_record: TransportDecisionRecord
    option_analyses: tuple[TransportOptionAnalysis, ...]
    safety_requirements: tuple[TransportSafetyRequirement, ...]
    blockers: tuple[TransportDecisionBlocker, ...]
    warnings: tuple[str, ...]
    inspected_artifacts: tuple[str, ...]
    forbidden_behavior_findings: tuple[str, ...]
    report_path: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "gate_id", str(self.gate_id))
        object.__setattr__(self, "gate_name", str(self.gate_name))
        object.__setattr__(self, "decided_at", str(self.decided_at))
        object.__setattr__(self, "go_no_go", str(self.go_no_go))
        object.__setattr__(self, "readiness_score", int(self.readiness_score))
        object.__setattr__(self, "accepted", bool(self.accepted))
        object.__setattr__(self, "can_implement_now", bool(self.can_implement_now))
        object.__setattr__(self, "transport_implemented", bool(self.transport_implemented))
        object.__setattr__(self, "dispatch_blocked", bool(self.dispatch_blocked))
        object.__setattr__(
            self,
            "option_analyses",
            tuple(sorted(self.option_analyses, key=lambda item: item.option)),
        )
        object.__setattr__(
            self,
            "safety_requirements",
            tuple(sorted(self.safety_requirements, key=lambda item: item.requirement_id)),
        )
        object.__setattr__(
            self,
            "blockers",
            tuple(sorted(self.blockers, key=lambda item: item.blocker_id)),
        )
        object.__setattr__(self, "warnings", _strings(self.warnings))
        object.__setattr__(self, "inspected_artifacts", _strings(self.inspected_artifacts))
        object.__setattr__(self, "forbidden_behavior_findings", _strings(self.forbidden_behavior_findings))
        object.__setattr__(self, "report_path", None if self.report_path is None else str(self.report_path))
        _require_allowed("go_no_go", self.go_no_go, TRANSPORT_ACTIVATION_GO_NO_GO)
        if self.go_no_go == "GO" and self.readiness_score != 100:
            raise ValueError("GO requires readiness_score=100")
        if self.go_no_go == "NO_GO" and not 70 <= self.readiness_score <= 99:
            raise ValueError("NO_GO requires readiness_score between 70 and 99")
        if self.go_no_go == "BLOCKED" and not 0 <= self.readiness_score <= 69:
            raise ValueError("BLOCKED requires readiness_score between 0 and 69")
        if self.can_implement_now:
            raise ValueError("Stage 8.1 result cannot allow immediate implementation")
        if self.transport_implemented:
            raise ValueError("Stage 8.1 result cannot mark transport as implemented")
        if not self.dispatch_blocked:
            raise ValueError("Stage 8.1 result must keep dispatch blocked")

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "gate_name": self.gate_name,
            "decided_at": self.decided_at,
            "go_no_go": self.go_no_go,
            "readiness_score": self.readiness_score,
            "accepted": self.accepted,
            "can_implement_now": self.can_implement_now,
            "transport_implemented": self.transport_implemented,
            "dispatch_blocked": self.dispatch_blocked,
            "decision_record": self.decision_record.to_dict(),
            "option_analyses": [analysis.to_dict() for analysis in self.option_analyses],
            "safety_requirements": [requirement.to_dict() for requirement in self.safety_requirements],
            "blockers": [blocker.to_dict() for blocker in self.blockers],
            "warnings": list(self.warnings),
            "inspected_artifacts": list(self.inspected_artifacts),
            "forbidden_behavior_findings": list(self.forbidden_behavior_findings),
            "report_path": self.report_path,
        }


@dataclass(frozen=True)
class LocalTransportActivationDecisionError:
    error_code: str
    message: str
    decided_at: str
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "error_code", str(self.error_code))
        object.__setattr__(self, "message", str(self.message))
        object.__setattr__(self, "decided_at", str(self.decided_at))
        object.__setattr__(self, "blockers", _strings(self.blockers))

    @staticmethod
    def of(
        error_code: str,
        message: str,
        *,
        decided_at: str,
        blockers: tuple[str, ...] = (),
    ) -> "LocalTransportActivationDecisionError":
        return LocalTransportActivationDecisionError(
            error_code=error_code,
            message=message,
            decided_at=decided_at,
            blockers=blockers or (message,),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "decided_at": self.decided_at,
            "blockers": list(self.blockers),
        }


__all__ = sorted(
    (
        "LOCAL_TRANSPORT_ACTIVATION_DECISION_SCHEMA_VERSION",
        "TRANSPORT_ACTIVATION_DECISIONS",
        "TRANSPORT_ACTIVATION_GO_NO_GO",
        "TRANSPORT_ACTIVATION_OPTIONS",
        "TRANSPORT_ACTIVATION_REQUIREMENT_STATUSES",
        "LocalTransportActivationDecisionError",
        "LocalTransportActivationDecisionResult",
        "TransportDecisionBlocker",
        "TransportDecisionRecord",
        "TransportOptionAnalysis",
        "TransportSafetyRequirement",
    )
)
