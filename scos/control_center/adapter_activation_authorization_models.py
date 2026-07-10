"""Stage 8.5 immutable explicit adapter activation authorization models."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

try:
    from .secret_safe_adapter_preflight_models import FrozenEvidenceMap
except ImportError:  # direct-module execution
    from secret_safe_adapter_preflight_models import FrozenEvidenceMap

ADAPTER_ACTIVATION_AUTHORIZATION_SCHEMA_VERSION = 1

ADAPTER_ACTIVATION_AUTHORIZATION_DECISIONS = (
    "AUTHORIZED_IN_PRINCIPLE",
    "DENIED",
    "BLOCKED",
    "EXPIRED",
)
EXPLICIT_OPERATOR_AUTHORIZATION_DECISIONS = ("APPROVE", "DENY")
AUTHORIZATION_CHECK_SEVERITIES = ("info", "warning", "error", "critical")


def _require_allowed(field_name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ValueError(f"{field_name} must be one of {list(allowed)}, got {value!r}")


def _strings(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    return tuple(sorted(str(value) for value in values))


def _plain(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, MappingProxyType):
        value = dict(value)
    if isinstance(value, dict):
        return {str(key): _plain(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _frozen_map(value: Any) -> FrozenEvidenceMap:
    plain = _plain(value)
    return FrozenEvidenceMap.from_mapping(plain if isinstance(plain, dict) else {"value": plain})


@dataclass(frozen=True)
class OperatorIdentity:
    operator_id: str
    display_name: str
    role: str
    authentication_evidence_ref: str
    human_confirmed: bool

    def __post_init__(self) -> None:
        for field_name in ("operator_id", "display_name", "role", "authentication_evidence_ref"):
            object.__setattr__(self, field_name, str(getattr(self, field_name)))
        object.__setattr__(self, "human_confirmed", bool(self.human_confirmed))

    def to_dict(self) -> dict[str, Any]:
        return {
            "operator_id": self.operator_id,
            "display_name": self.display_name,
            "role": self.role,
            "authentication_evidence_ref": self.authentication_evidence_ref,
            "human_confirmed": self.human_confirmed,
        }


@dataclass(frozen=True)
class AdapterActivationScope:
    adapter_id: str
    adapter_kind: str
    runtime_target: str
    allowed_operations: tuple[str, ...]
    transport_mode: str
    credential_reference_ids: tuple[str, ...]
    expires_at: str

    def __post_init__(self) -> None:
        for field_name in ("adapter_id", "adapter_kind", "runtime_target", "transport_mode", "expires_at"):
            object.__setattr__(self, field_name, str(getattr(self, field_name)))
        object.__setattr__(self, "allowed_operations", _strings(self.allowed_operations))
        object.__setattr__(self, "credential_reference_ids", _strings(self.credential_reference_ids))

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "adapter_kind": self.adapter_kind,
            "runtime_target": self.runtime_target,
            "allowed_operations": list(self.allowed_operations),
            "transport_mode": self.transport_mode,
            "credential_reference_ids": list(self.credential_reference_ids),
            "expires_at": self.expires_at,
        }


@dataclass(frozen=True)
class AdapterActivationAuthorizationRequest:
    request_id: str
    checked_at: str
    preflight_result: FrozenEvidenceMap
    operator: OperatorIdentity
    scope: AdapterActivationScope
    explicit_decision: str
    decision_reason: str
    approval_evidence: FrozenEvidenceMap
    audit_readiness: FrozenEvidenceMap
    rollback_acknowledged: bool
    fallback_acknowledged: bool
    schema_version: int = ADAPTER_ACTIVATION_AUTHORIZATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", int(self.schema_version))
        for field_name in ("request_id", "checked_at", "explicit_decision", "decision_reason"):
            object.__setattr__(self, field_name, str(getattr(self, field_name)))
        if not isinstance(self.operator, OperatorIdentity):
            object.__setattr__(self, "operator", OperatorIdentity(**_plain(self.operator)))
        if not isinstance(self.scope, AdapterActivationScope):
            object.__setattr__(self, "scope", AdapterActivationScope(**_plain(self.scope)))
        if not isinstance(self.preflight_result, FrozenEvidenceMap):
            object.__setattr__(self, "preflight_result", _frozen_map(self.preflight_result))
        if not isinstance(self.approval_evidence, FrozenEvidenceMap):
            object.__setattr__(self, "approval_evidence", _frozen_map(self.approval_evidence))
        if not isinstance(self.audit_readiness, FrozenEvidenceMap):
            object.__setattr__(self, "audit_readiness", _frozen_map(self.audit_readiness))
        object.__setattr__(self, "rollback_acknowledged", bool(self.rollback_acknowledged))
        object.__setattr__(self, "fallback_acknowledged", bool(self.fallback_acknowledged))
        _require_allowed("explicit_decision", self.explicit_decision, EXPLICIT_OPERATOR_AUTHORIZATION_DECISIONS)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "checked_at": self.checked_at,
            "preflight_result": self.preflight_result.to_dict(),
            "operator": self.operator.to_dict(),
            "scope": self.scope.to_dict(),
            "explicit_decision": self.explicit_decision,
            "decision_reason": self.decision_reason,
            "approval_evidence": self.approval_evidence.to_dict(),
            "audit_readiness": self.audit_readiness.to_dict(),
            "rollback_acknowledged": self.rollback_acknowledged,
            "fallback_acknowledged": self.fallback_acknowledged,
        }


@dataclass(frozen=True)
class AuthorizationCheck:
    check_id: str
    code: str
    passed: bool
    severity: str
    message: str
    evidence: FrozenEvidenceMap

    def __post_init__(self) -> None:
        for field_name in ("check_id", "code", "severity", "message"):
            object.__setattr__(self, field_name, str(getattr(self, field_name)))
        object.__setattr__(self, "passed", bool(self.passed))
        if not isinstance(self.evidence, FrozenEvidenceMap):
            object.__setattr__(self, "evidence", _frozen_map(self.evidence))
        _require_allowed("severity", self.severity, AUTHORIZATION_CHECK_SEVERITIES)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "code": self.code,
            "passed": self.passed,
            "severity": self.severity,
            "message": self.message,
            "evidence": self.evidence.to_dict(),
        }


@dataclass(frozen=True)
class AdapterActivationAuthorizationResult:
    schema_version: int
    authorization_id: str
    checked_at: str
    decision: str
    authorized_in_principle: bool
    can_activate_now: bool
    activation_executed: bool
    credentials_materialized: bool
    external_calls_made: bool
    runtime_mutated: bool
    checks: tuple[AuthorizationCheck, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    evidence: FrozenEvidenceMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", int(self.schema_version))
        for field_name in ("authorization_id", "checked_at", "decision"):
            object.__setattr__(self, field_name, str(getattr(self, field_name)))
        for field_name in (
            "authorized_in_principle",
            "can_activate_now",
            "activation_executed",
            "credentials_materialized",
            "external_calls_made",
            "runtime_mutated",
        ):
            object.__setattr__(self, field_name, bool(getattr(self, field_name)))
        object.__setattr__(self, "checks", tuple(sorted(self.checks, key=lambda item: item.check_id)))
        object.__setattr__(self, "blockers", _strings(self.blockers))
        object.__setattr__(self, "warnings", _strings(self.warnings))
        if not isinstance(self.evidence, FrozenEvidenceMap):
            object.__setattr__(self, "evidence", _frozen_map(self.evidence))
        _require_allowed("decision", self.decision, ADAPTER_ACTIVATION_AUTHORIZATION_DECISIONS)
        if self.can_activate_now or self.activation_executed or self.credentials_materialized:
            raise ValueError("Stage 8.5 authorization must not activate adapters or materialize credentials")
        if self.external_calls_made or self.runtime_mutated:
            raise ValueError("Stage 8.5 authorization must not make external calls or mutate runtime")
        if self.authorized_in_principle and self.decision != "AUTHORIZED_IN_PRINCIPLE":
            raise ValueError("authorized_in_principle requires AUTHORIZED_IN_PRINCIPLE decision")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "authorization_id": self.authorization_id,
            "checked_at": self.checked_at,
            "decision": self.decision,
            "authorized_in_principle": self.authorized_in_principle,
            "can_activate_now": self.can_activate_now,
            "activation_executed": self.activation_executed,
            "credentials_materialized": self.credentials_materialized,
            "external_calls_made": self.external_calls_made,
            "runtime_mutated": self.runtime_mutated,
            "checks": [check.to_dict() for check in self.checks],
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "evidence": self.evidence.to_dict(),
        }


__all__ = sorted(
    (
        "ADAPTER_ACTIVATION_AUTHORIZATION_DECISIONS",
        "ADAPTER_ACTIVATION_AUTHORIZATION_SCHEMA_VERSION",
        "AUTHORIZATION_CHECK_SEVERITIES",
        "EXPLICIT_OPERATOR_AUTHORIZATION_DECISIONS",
        "AdapterActivationAuthorizationRequest",
        "AdapterActivationAuthorizationResult",
        "AdapterActivationScope",
        "AuthorizationCheck",
        "OperatorIdentity",
    )
)
