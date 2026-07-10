"""Stage 8.4 immutable secret-safe adapter activation preflight models."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

SECRET_SAFE_ADAPTER_PREFLIGHT_SCHEMA_VERSION = 1

SECRET_SAFE_ADAPTER_IDS = ("chatgpt", "claude_code", "codex", "hermes")
SECRET_SAFE_ADAPTER_RUNTIMES = ("manual", "simulator")
SECRET_SAFE_ACTIVATION_MODES = ("preflight_only", "simulator_only", "manual_handoff_only")
SECRET_SAFE_REJECTED_ACTIVATION_MODES = (
    "activate_now",
    "auto_activate",
    "real_dispatch",
    "auto_dispatch",
    "api_dispatch",
    "live_adapter",
)
SECRET_SAFE_TRANSPORTS = ("FILE_SNAPSHOT_REFRESH", "NO_TRANSPORT")
SECRET_SAFE_REJECTED_TRANSPORTS = ("WEBSOCKET", "SSE_EVENTSOURCE", "POLLING", "LOCAL_HTTP")
SECRET_SAFE_VERDICTS = ("READY_FOR_OPERATOR_DECISION", "NO_GO", "BLOCKED")
SECRET_SAFE_CHECK_STATUSES = ("pass", "warning", "blocker", "missing")
SECRET_SAFE_CHECK_SEVERITIES = ("info", "warning", "error", "critical")
SECRET_SAFE_CREDENTIAL_CATEGORIES = (
    "API_KEY",
    "TOKEN",
    "PASSWORD",
    "COOKIE",
    "AUTHORIZATION_HEADER",
    "PRIVATE_KEY",
    "GENERIC_SECRET",
    "UNKNOWN",
)
SECRET_SAFE_SENSITIVITY = ("PUBLIC", "INTERNAL", "SENSITIVE", "SECRET")


def _require_allowed(field_name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ValueError(f"{field_name} must be one of {list(allowed)}, got {value!r}")


def _strings(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    return tuple(sorted(str(value) for value in values))


def _freeze_value(value: Any) -> Any:
    if isinstance(value, FrozenEvidenceMap):
        return value
    if isinstance(value, MappingProxyType):
        value = dict(value)
    if isinstance(value, dict):
        return FrozenEvidenceMap.from_mapping(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    return value


def _thaw_value(value: Any) -> Any:
    if isinstance(value, FrozenEvidenceMap):
        return value.to_dict()
    if isinstance(value, tuple):
        return [_thaw_value(item) for item in value]
    return value


@dataclass(frozen=True)
class FrozenEvidenceMap:
    items: tuple[tuple[str, Any], ...]

    @staticmethod
    def from_mapping(mapping: dict[str, Any] | None) -> "FrozenEvidenceMap":
        source = mapping or {}
        return FrozenEvidenceMap(tuple((str(key), _freeze_value(source[key])) for key in sorted(source)))

    def to_dict(self) -> dict[str, Any]:
        return {key: _thaw_value(value) for key, value in self.items}


@dataclass(frozen=True)
class SafeCredentialReference:
    reference_id: str
    credential_category: str
    sensitivity: str
    source_kind: str
    policy_status: str
    redaction_status: str
    material_present: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "reference_id", str(self.reference_id))
        object.__setattr__(self, "credential_category", str(self.credential_category))
        object.__setattr__(self, "sensitivity", str(self.sensitivity))
        object.__setattr__(self, "source_kind", str(self.source_kind))
        object.__setattr__(self, "policy_status", str(self.policy_status))
        object.__setattr__(self, "redaction_status", str(self.redaction_status))
        object.__setattr__(self, "material_present", bool(self.material_present))
        _require_allowed("credential_category", self.credential_category, SECRET_SAFE_CREDENTIAL_CATEGORIES)
        _require_allowed("sensitivity", self.sensitivity, SECRET_SAFE_SENSITIVITY)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference_id": self.reference_id,
            "credential_category": self.credential_category,
            "sensitivity": self.sensitivity,
            "source_kind": self.source_kind,
            "policy_status": self.policy_status,
            "redaction_status": self.redaction_status,
            "material_present": self.material_present,
        }


@dataclass(frozen=True)
class SecretSafeAdapterPreflightRequest:
    schema_version: int
    request_id: str
    adapter_id: str
    adapter_runtime: str
    activation_mode: str
    requested_transport: str
    checked_at: str
    generic_preflight_evidence: FrozenEvidenceMap
    transport_decision_evidence: FrozenEvidenceMap
    file_snapshot_boundary_evidence: FrozenEvidenceMap
    credential_policy_evidence: FrozenEvidenceMap
    operator_approval_evidence: FrozenEvidenceMap
    audit_readiness_evidence: FrozenEvidenceMap
    rollback_evidence: FrozenEvidenceMap
    simulator_fallback_evidence: FrozenEvidenceMap
    manual_fallback_evidence: FrozenEvidenceMap
    safe_credential_references: tuple[SafeCredentialReference, ...]
    metadata: FrozenEvidenceMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", int(self.schema_version))
        for field_name in ("request_id", "adapter_id", "adapter_runtime", "activation_mode", "requested_transport", "checked_at"):
            object.__setattr__(self, field_name, str(getattr(self, field_name)))
        for field_name in (
            "generic_preflight_evidence",
            "transport_decision_evidence",
            "file_snapshot_boundary_evidence",
            "credential_policy_evidence",
            "operator_approval_evidence",
            "audit_readiness_evidence",
            "rollback_evidence",
            "simulator_fallback_evidence",
            "manual_fallback_evidence",
            "metadata",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, FrozenEvidenceMap):
                object.__setattr__(self, field_name, FrozenEvidenceMap.from_mapping(dict(value or {})))
        object.__setattr__(
            self,
            "safe_credential_references",
            tuple(sorted(self.safe_credential_references, key=lambda item: item.reference_id)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "adapter_id": self.adapter_id,
            "adapter_runtime": self.adapter_runtime,
            "activation_mode": self.activation_mode,
            "requested_transport": self.requested_transport,
            "checked_at": self.checked_at,
            "generic_preflight_evidence": self.generic_preflight_evidence.to_dict(),
            "transport_decision_evidence": self.transport_decision_evidence.to_dict(),
            "file_snapshot_boundary_evidence": self.file_snapshot_boundary_evidence.to_dict(),
            "credential_policy_evidence": self.credential_policy_evidence.to_dict(),
            "operator_approval_evidence": self.operator_approval_evidence.to_dict(),
            "audit_readiness_evidence": self.audit_readiness_evidence.to_dict(),
            "rollback_evidence": self.rollback_evidence.to_dict(),
            "simulator_fallback_evidence": self.simulator_fallback_evidence.to_dict(),
            "manual_fallback_evidence": self.manual_fallback_evidence.to_dict(),
            "safe_credential_references": [item.to_dict() for item in self.safe_credential_references],
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class PreflightCheck:
    check_id: str
    category: str
    status: str
    severity: str
    summary: str
    evidence_refs: tuple[str, ...]
    blocker_code: str | None
    warning_code: str | None

    def __post_init__(self) -> None:
        for field_name in ("check_id", "category", "status", "severity", "summary"):
            object.__setattr__(self, field_name, str(getattr(self, field_name)))
        object.__setattr__(self, "evidence_refs", _strings(self.evidence_refs))
        object.__setattr__(self, "blocker_code", None if self.blocker_code is None else str(self.blocker_code))
        object.__setattr__(self, "warning_code", None if self.warning_code is None else str(self.warning_code))
        _require_allowed("status", self.status, SECRET_SAFE_CHECK_STATUSES)
        _require_allowed("severity", self.severity, SECRET_SAFE_CHECK_SEVERITIES)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "category": self.category,
            "status": self.status,
            "severity": self.severity,
            "summary": self.summary,
            "evidence_refs": list(self.evidence_refs),
            "blocker_code": self.blocker_code,
            "warning_code": self.warning_code,
        }


@dataclass(frozen=True)
class PreflightValidationResult:
    accepted: bool
    checked_at: str
    request: SecretSafeAdapterPreflightRequest | None
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "accepted", bool(self.accepted))
        object.__setattr__(self, "checked_at", str(self.checked_at))
        object.__setattr__(self, "warnings", _strings(self.warnings))
        object.__setattr__(self, "blockers", _strings(self.blockers))

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "checked_at": self.checked_at,
            "request": self.request.to_dict() if self.request else None,
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
        }


@dataclass(frozen=True)
class SecretSafeAdapterPreflightResult:
    schema_version: int
    result_id: str
    checked_at: str
    adapter_id: str
    verdict: str
    readiness_score: int
    accepted: bool
    ready_for_operator_decision: bool
    can_activate_now: bool
    activation_authorized: bool
    real_dispatch_blocked: bool
    external_calls_blocked: bool
    credentials_materialized: bool
    runtime_mutated: bool
    checks: tuple[PreflightCheck, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    required_next_action: str
    evidence_digest: str
    report_path: str | None
    metadata: FrozenEvidenceMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", int(self.schema_version))
        for field_name in ("result_id", "checked_at", "adapter_id", "verdict", "required_next_action", "evidence_digest"):
            object.__setattr__(self, field_name, str(getattr(self, field_name)))
        object.__setattr__(self, "readiness_score", int(self.readiness_score))
        for field_name in (
            "accepted",
            "ready_for_operator_decision",
            "can_activate_now",
            "activation_authorized",
            "real_dispatch_blocked",
            "external_calls_blocked",
            "credentials_materialized",
            "runtime_mutated",
        ):
            object.__setattr__(self, field_name, bool(getattr(self, field_name)))
        object.__setattr__(self, "checks", tuple(sorted(self.checks, key=lambda item: item.check_id)))
        object.__setattr__(self, "blockers", _strings(self.blockers))
        object.__setattr__(self, "warnings", _strings(self.warnings))
        object.__setattr__(self, "report_path", None if self.report_path is None else str(self.report_path))
        if not isinstance(self.metadata, FrozenEvidenceMap):
            object.__setattr__(self, "metadata", FrozenEvidenceMap.from_mapping(dict(self.metadata or {})))
        _require_allowed("verdict", self.verdict, SECRET_SAFE_VERDICTS)
        if self.can_activate_now or self.activation_authorized or self.credentials_materialized or self.runtime_mutated:
            raise ValueError("Stage 8.4 result invariants must keep runtime inactive and unmutated")
        if not self.real_dispatch_blocked or not self.external_calls_blocked:
            raise ValueError("Stage 8.4 result invariants must keep dispatch and external calls blocked")
        if self.accepted and self.verdict != "READY_FOR_OPERATOR_DECISION":
            raise ValueError("accepted Stage 8.4 result requires READY_FOR_OPERATOR_DECISION")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "result_id": self.result_id,
            "checked_at": self.checked_at,
            "adapter_id": self.adapter_id,
            "verdict": self.verdict,
            "readiness_score": self.readiness_score,
            "accepted": self.accepted,
            "ready_for_operator_decision": self.ready_for_operator_decision,
            "can_activate_now": self.can_activate_now,
            "activation_authorized": self.activation_authorized,
            "real_dispatch_blocked": self.real_dispatch_blocked,
            "external_calls_blocked": self.external_calls_blocked,
            "credentials_materialized": self.credentials_materialized,
            "runtime_mutated": self.runtime_mutated,
            "checks": [check.to_dict() for check in self.checks],
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "required_next_action": self.required_next_action,
            "evidence_digest": self.evidence_digest,
            "report_path": self.report_path,
            "metadata": self.metadata.to_dict(),
        }


__all__ = sorted(
    (
        "SECRET_SAFE_ACTIVATION_MODES",
        "SECRET_SAFE_ADAPTER_IDS",
        "SECRET_SAFE_ADAPTER_PREFLIGHT_SCHEMA_VERSION",
        "SECRET_SAFE_ADAPTER_RUNTIMES",
        "SECRET_SAFE_CHECK_SEVERITIES",
        "SECRET_SAFE_CHECK_STATUSES",
        "SECRET_SAFE_REJECTED_ACTIVATION_MODES",
        "SECRET_SAFE_REJECTED_TRANSPORTS",
        "SECRET_SAFE_TRANSPORTS",
        "SECRET_SAFE_VERDICTS",
        "FrozenEvidenceMap",
        "PreflightCheck",
        "PreflightValidationResult",
        "SafeCredentialReference",
        "SecretSafeAdapterPreflightRequest",
        "SecretSafeAdapterPreflightResult",
    )
)
