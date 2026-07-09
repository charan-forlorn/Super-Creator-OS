"""Stage 8.3 immutable credential policy and redaction models."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

STAGE83_CREDENTIAL_POLICY_SCHEMA_VERSION = 1

CREDENTIAL_CATEGORIES = (
    "API_KEY",
    "TOKEN",
    "PASSWORD",
    "COOKIE",
    "AUTHORIZATION_HEADER",
    "PRIVATE_KEY",
    "GENERIC_SECRET",
    "UNKNOWN",
)
SENSITIVITY_LEVELS = ("PUBLIC", "INTERNAL", "SENSITIVE", "SECRET")
POLICY_SURFACES = (
    "LOG",
    "EVENT",
    "SNAPSHOT",
    "APPROVAL_EVIDENCE",
    "CERTIFICATION_EVIDENCE",
    "UNKNOWN",
)
APPROVAL_BOUNDARY_STATUSES = (
    "NOT_REQUESTED",
    "PENDING",
    "APPROVED_EXPLICIT_LATER_STAGE",
    "DENIED",
    "BLANKET_APPROVAL_REJECTED",
    "AMBIGUOUS",
)
POLICY_GO_NO_GO = ("GO", "NO_GO", "BLOCKED")

REDACTION_MARKER = "[REDACTED:SECRET]"
DEFAULT_SECRET_FIELD_MARKERS = (
    "api_key",
    "token",
    "secret",
    "password",
    "credential",
    "cookie",
    "authorization",
    "bearer",
)
DEFAULT_FORBIDDEN_OUTPUT_SURFACES = (
    "LOG",
    "EVENT",
    "SNAPSHOT",
    "APPROVAL_EVIDENCE",
    "CERTIFICATION_EVIDENCE",
)
DEFAULT_ALLOWED_LOCAL_EVIDENCE_LOCATIONS = (
    "docs/specification/STAGE8_CREDENTIAL_SECRET_POLICY.md",
    "docs/certification/Stage-8.3-plan.md",
)


def _require_allowed(field_name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ValueError(f"{field_name} must be one of {list(allowed)}, got {value!r}")


def _strings(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    return tuple(sorted(str(value) for value in values))


def _freeze_value(value: Any) -> Any:
    if isinstance(value, FrozenPolicyMap):
        return value
    if isinstance(value, MappingProxyType):
        value = dict(value)
    if isinstance(value, dict):
        return FrozenPolicyMap.from_mapping(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    return value


def _thaw_value(value: Any) -> Any:
    if isinstance(value, FrozenPolicyMap):
        return value.to_dict()
    if isinstance(value, tuple):
        return [_thaw_value(item) for item in value]
    return value


@dataclass(frozen=True)
class FrozenPolicyMap:
    """Tuple-backed immutable mapping with stable serialization."""

    items: tuple[tuple[str, Any], ...]

    @staticmethod
    def from_mapping(mapping: dict[str, Any] | None) -> "FrozenPolicyMap":
        source = mapping or {}
        return FrozenPolicyMap(tuple((str(key), _freeze_value(source[key])) for key in sorted(source)))

    def to_dict(self) -> dict[str, Any]:
        return {key: _thaw_value(value) for key, value in self.items}


@dataclass(frozen=True)
class CredentialPolicy:
    schema_version: int
    policy_id: str
    redaction_marker: str
    secret_field_markers: tuple[str, ...]
    forbidden_output_surfaces: tuple[str, ...]
    allowed_local_evidence_locations: tuple[str, ...]
    require_explicit_later_stage_approval: bool
    metadata: FrozenPolicyMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "policy_id", str(self.policy_id))
        object.__setattr__(self, "redaction_marker", str(self.redaction_marker))
        object.__setattr__(self, "secret_field_markers", _strings(self.secret_field_markers))
        object.__setattr__(self, "forbidden_output_surfaces", _strings(self.forbidden_output_surfaces))
        for surface in self.forbidden_output_surfaces:
            _require_allowed("forbidden_output_surfaces", surface, POLICY_SURFACES)
        object.__setattr__(
            self,
            "allowed_local_evidence_locations",
            _strings(self.allowed_local_evidence_locations),
        )
        object.__setattr__(
            self,
            "require_explicit_later_stage_approval",
            bool(self.require_explicit_later_stage_approval),
        )
        if not isinstance(self.metadata, FrozenPolicyMap):
            object.__setattr__(self, "metadata", FrozenPolicyMap.from_mapping(dict(self.metadata or {})))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "redaction_marker": self.redaction_marker,
            "secret_field_markers": list(self.secret_field_markers),
            "forbidden_output_surfaces": list(self.forbidden_output_surfaces),
            "allowed_local_evidence_locations": list(self.allowed_local_evidence_locations),
            "require_explicit_later_stage_approval": self.require_explicit_later_stage_approval,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class CredentialPolicyViolation:
    violation_id: str
    surface: str
    path: str
    category: str
    severity: str
    message: str
    evidence: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "violation_id", str(self.violation_id))
        object.__setattr__(self, "surface", str(self.surface))
        object.__setattr__(self, "path", str(self.path))
        object.__setattr__(self, "category", str(self.category))
        object.__setattr__(self, "severity", str(self.severity))
        object.__setattr__(self, "message", str(self.message))
        object.__setattr__(self, "evidence", str(self.evidence))
        _require_allowed("surface", self.surface, POLICY_SURFACES)
        _require_allowed("category", self.category, CREDENTIAL_CATEGORIES)
        _require_allowed("severity", self.severity, SENSITIVITY_LEVELS)

    def to_dict(self) -> dict[str, Any]:
        return {
            "violation_id": self.violation_id,
            "surface": self.surface,
            "path": self.path,
            "category": self.category,
            "severity": self.severity,
            "message": self.message,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class RedactionFinding:
    finding_id: str
    path: str
    category: str
    reason: str
    redacted: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "finding_id", str(self.finding_id))
        object.__setattr__(self, "path", str(self.path))
        object.__setattr__(self, "category", str(self.category))
        object.__setattr__(self, "reason", str(self.reason))
        object.__setattr__(self, "redacted", bool(self.redacted))
        _require_allowed("category", self.category, CREDENTIAL_CATEGORIES)

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "path": self.path,
            "category": self.category,
            "reason": self.reason,
            "redacted": self.redacted,
        }


@dataclass(frozen=True)
class RedactionResult:
    accepted: bool
    redacted_payload: Any
    findings: tuple[RedactionFinding, ...]
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "accepted", bool(self.accepted))
        object.__setattr__(self, "redacted_payload", _freeze_value(self.redacted_payload))
        object.__setattr__(
            self,
            "findings",
            tuple(sorted(self.findings, key=lambda item: (item.path, item.finding_id))),
        )
        object.__setattr__(self, "warnings", _strings(self.warnings))
        object.__setattr__(self, "blockers", _strings(self.blockers))

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "redacted_payload": _thaw_value(self.redacted_payload),
            "findings": [finding.to_dict() for finding in self.findings],
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
        }


@dataclass(frozen=True)
class PolicyValidationResult:
    accepted: bool
    go_no_go: str
    readiness_score: int
    checked_at: str
    policy_id: str
    surface: str
    approval_boundary_status: str
    violations: tuple[CredentialPolicyViolation, ...]
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    metadata: FrozenPolicyMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "accepted", bool(self.accepted))
        object.__setattr__(self, "go_no_go", str(self.go_no_go))
        object.__setattr__(self, "readiness_score", int(self.readiness_score))
        object.__setattr__(self, "checked_at", str(self.checked_at))
        object.__setattr__(self, "policy_id", str(self.policy_id))
        object.__setattr__(self, "surface", str(self.surface))
        object.__setattr__(self, "approval_boundary_status", str(self.approval_boundary_status))
        object.__setattr__(
            self,
            "violations",
            tuple(sorted(self.violations, key=lambda item: item.violation_id)),
        )
        object.__setattr__(self, "warnings", _strings(self.warnings))
        object.__setattr__(self, "blockers", _strings(self.blockers))
        if not isinstance(self.metadata, FrozenPolicyMap):
            object.__setattr__(self, "metadata", FrozenPolicyMap.from_mapping(dict(self.metadata or {})))
        _require_allowed("go_no_go", self.go_no_go, POLICY_GO_NO_GO)
        _require_allowed("surface", self.surface, POLICY_SURFACES)
        _require_allowed("approval_boundary_status", self.approval_boundary_status, APPROVAL_BOUNDARY_STATUSES)

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "go_no_go": self.go_no_go,
            "readiness_score": self.readiness_score,
            "checked_at": self.checked_at,
            "policy_id": self.policy_id,
            "surface": self.surface,
            "approval_boundary_status": self.approval_boundary_status,
            "violations": [violation.to_dict() for violation in self.violations],
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "metadata": self.metadata.to_dict(),
        }


def create_default_credential_policy(metadata: dict[str, Any] | None = None) -> CredentialPolicy:
    return CredentialPolicy(
        schema_version=STAGE83_CREDENTIAL_POLICY_SCHEMA_VERSION,
        policy_id="stage8.3-local-credential-policy",
        redaction_marker=REDACTION_MARKER,
        secret_field_markers=DEFAULT_SECRET_FIELD_MARKERS,
        forbidden_output_surfaces=DEFAULT_FORBIDDEN_OUTPUT_SURFACES,
        allowed_local_evidence_locations=DEFAULT_ALLOWED_LOCAL_EVIDENCE_LOCATIONS,
        require_explicit_later_stage_approval=True,
        metadata=FrozenPolicyMap.from_mapping(metadata or {"stage": "8.3"}),
    )


__all__ = sorted(
    (
        "APPROVAL_BOUNDARY_STATUSES",
        "CREDENTIAL_CATEGORIES",
        "DEFAULT_ALLOWED_LOCAL_EVIDENCE_LOCATIONS",
        "DEFAULT_FORBIDDEN_OUTPUT_SURFACES",
        "DEFAULT_SECRET_FIELD_MARKERS",
        "POLICY_GO_NO_GO",
        "POLICY_SURFACES",
        "REDACTION_MARKER",
        "SENSITIVITY_LEVELS",
        "STAGE83_CREDENTIAL_POLICY_SCHEMA_VERSION",
        "CredentialPolicy",
        "CredentialPolicyViolation",
        "FrozenPolicyMap",
        "PolicyValidationResult",
        "RedactionFinding",
        "RedactionResult",
        "create_default_credential_policy",
    )
)
