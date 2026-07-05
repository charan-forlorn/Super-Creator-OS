"""SCOS Stage 4.17 first customer conversion handoff models.

Immutable, local-first models for a read-only *manual close preparation* layer
built over a Stage 4.16 ``first_prospect_outcome_review.json``. These models
describe the deterministic conversion handoff package a human operator uses to
confirm scope, offer, pricing, next steps, and close readiness with a prospect
before any manual outreach.

This layer reuses the Stage 4.1 ``FrozenMap`` implementation and serializes with
explicit key order. It never sends anything, never contacts external services,
never keeps a customer database, never touches money-collection, commercial
document, or customer-relationship systems, and never mutates the Stage 4.16
outcome-review artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from .report_models import FrozenMap, _freeze_value
except ImportError:  # pragma: no cover - supports this repo's plain-script tests
    from report_models import FrozenMap, _freeze_value

FIRST_CUSTOMER_CONVERSION_HANDOFF_SCHEMA_VERSION = 1

CONVERSION_HANDOFF_CHECK_STATUSES = ("success", "failure", "skipped")
CONVERSION_HANDOFF_CHECK_SEVERITIES = ("info", "warning", "error")
CONVERSION_HANDOFF_BLOCKER_SEVERITIES = ("warning", "error", "critical")

CONVERSION_HANDOFF_ARTIFACT_TYPES = (
    "manifest",
    "scope_confirmation",
    "offer_summary",
    "pricing_confirmation",
    "manual_close_checklist",
    "next_step_script",
    "operator_review",
    "evidence_summary",
)


@dataclass(frozen=True)
class ConversionHandoffCheck:
    check_name: str
    status: str
    severity: str
    artifact_path: str | None
    error_kind: str | None
    error_detail: str | None
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "check_name", str(self.check_name))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "severity", str(self.severity))
        if self.status not in CONVERSION_HANDOFF_CHECK_STATUSES:
            raise ValueError(f"invalid conversion handoff check status: {self.status!r}")
        if self.severity not in CONVERSION_HANDOFF_CHECK_SEVERITIES:
            raise ValueError(f"invalid conversion handoff check severity: {self.severity!r}")
        if self.artifact_path is not None:
            object.__setattr__(self, "artifact_path", str(self.artifact_path))
        if self.error_kind is not None:
            object.__setattr__(self, "error_kind", str(self.error_kind))
        if self.error_detail is not None:
            object.__setattr__(self, "error_detail", str(self.error_detail))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    @staticmethod
    def of(
        check_name: str,
        status: str,
        severity: str,
        *,
        artifact_path: str | None = None,
        error_kind: str | None = None,
        error_detail: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "ConversionHandoffCheck":
        return ConversionHandoffCheck(
            check_name=str(check_name),
            status=str(status),
            severity=str(severity),
            artifact_path=None if artifact_path is None else str(artifact_path),
            error_kind=None if error_kind is None else str(error_kind),
            error_detail=None if error_detail is None else str(error_detail),
            metadata=FrozenMap.from_mapping(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_name": self.check_name,
            "status": self.status,
            "severity": self.severity,
            "artifact_path": self.artifact_path,
            "error_kind": self.error_kind,
            "error_detail": self.error_detail,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class ConversionHandoffArtifact:
    artifact_name: str
    artifact_type: str
    path: str
    required: bool
    description: str
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_name", str(self.artifact_name))
        object.__setattr__(self, "artifact_type", str(self.artifact_type))
        if self.artifact_type not in CONVERSION_HANDOFF_ARTIFACT_TYPES:
            raise ValueError(f"invalid conversion handoff artifact type: {self.artifact_type!r}")
        object.__setattr__(self, "path", str(self.path))
        object.__setattr__(self, "required", bool(self.required))
        object.__setattr__(self, "description", str(self.description))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    @staticmethod
    def of(
        artifact_name: str,
        artifact_type: str,
        path: str,
        *,
        required: bool = True,
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> "ConversionHandoffArtifact":
        return ConversionHandoffArtifact(
            artifact_name=str(artifact_name),
            artifact_type=str(artifact_type),
            path=str(path),
            required=bool(required),
            description=str(description),
            metadata=FrozenMap.from_mapping(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_name": self.artifact_name,
            "artifact_type": self.artifact_type,
            "path": self.path,
            "required": self.required,
            "description": self.description,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class ConversionHandoffBlocker:
    blocker_id: str
    category: str
    severity: str
    title: str
    detail: str
    recommended_action: str
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "blocker_id", str(self.blocker_id))
        object.__setattr__(self, "category", str(self.category))
        object.__setattr__(self, "severity", str(self.severity))
        if self.severity not in CONVERSION_HANDOFF_BLOCKER_SEVERITIES:
            raise ValueError(f"invalid conversion handoff blocker severity: {self.severity!r}")
        object.__setattr__(self, "title", str(self.title))
        object.__setattr__(self, "detail", str(self.detail))
        object.__setattr__(self, "recommended_action", str(self.recommended_action))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    @staticmethod
    def of(
        blocker_id: str,
        category: str,
        severity: str,
        title: str,
        detail: str,
        recommended_action: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> "ConversionHandoffBlocker":
        return ConversionHandoffBlocker(
            blocker_id=str(blocker_id),
            category=str(category),
            severity=str(severity),
            title=str(title),
            detail=str(detail),
            recommended_action=str(recommended_action),
            metadata=FrozenMap.from_mapping(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "blocker_id": self.blocker_id,
            "category": self.category,
            "severity": self.severity,
            "title": self.title,
            "detail": self.detail,
            "recommended_action": self.recommended_action,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class FirstCustomerConversionHandoffResult:
    ok: bool
    schema_version: int
    accepted: bool
    handoff_id: str
    outcome_review_id: str
    prospect_id: str
    checked_at: str
    source_outcome_review_path: str
    handoff_dir: str
    manifest_path: str
    artifacts: tuple[ConversionHandoffArtifact, ...]
    checks: tuple[ConversionHandoffCheck, ...]
    blockers: tuple[ConversionHandoffBlocker, ...]
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "accepted", bool(self.accepted))
        object.__setattr__(self, "handoff_id", str(self.handoff_id))
        object.__setattr__(self, "outcome_review_id", str(self.outcome_review_id))
        object.__setattr__(self, "prospect_id", str(self.prospect_id))
        object.__setattr__(self, "checked_at", str(self.checked_at))
        object.__setattr__(self, "source_outcome_review_path", str(self.source_outcome_review_path))
        object.__setattr__(self, "handoff_dir", str(self.handoff_dir))
        object.__setattr__(self, "manifest_path", str(self.manifest_path))
        object.__setattr__(self, "artifacts", tuple(self.artifacts))
        object.__setattr__(self, "checks", tuple(self.checks))
        object.__setattr__(self, "blockers", tuple(self.blockers))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "accepted": self.accepted,
            "handoff_id": self.handoff_id,
            "outcome_review_id": self.outcome_review_id,
            "prospect_id": self.prospect_id,
            "checked_at": self.checked_at,
            "source_outcome_review_path": self.source_outcome_review_path,
            "handoff_dir": self.handoff_dir,
            "manifest_path": self.manifest_path,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "checks": [check.to_dict() for check in self.checks],
            "blockers": [blocker.to_dict() for blocker in self.blockers],
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class FirstCustomerConversionHandoffError:
    ok: bool
    schema_version: int
    error_kind: str
    error_detail: str
    failed_check: str
    checks: tuple[ConversionHandoffCheck, ...]
    blockers: tuple[ConversionHandoffBlocker, ...]
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", False)
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "error_kind", str(self.error_kind))
        object.__setattr__(self, "error_detail", str(self.error_detail))
        object.__setattr__(self, "failed_check", str(self.failed_check))
        object.__setattr__(self, "checks", tuple(self.checks))
        object.__setattr__(self, "blockers", tuple(self.blockers))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    @staticmethod
    def of(
        error_kind: str,
        error_detail: str,
        failed_check: str,
        checks: tuple[ConversionHandoffCheck, ...] = (),
        blockers: tuple[ConversionHandoffBlocker, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> "FirstCustomerConversionHandoffError":
        base = {"schema_version": FIRST_CUSTOMER_CONVERSION_HANDOFF_SCHEMA_VERSION}
        base.update(metadata or {})
        return FirstCustomerConversionHandoffError(
            ok=False,
            schema_version=FIRST_CUSTOMER_CONVERSION_HANDOFF_SCHEMA_VERSION,
            error_kind=str(error_kind),
            error_detail=str(error_detail),
            failed_check=str(failed_check),
            checks=tuple(checks),
            blockers=tuple(blockers),
            metadata=FrozenMap.from_mapping(base),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "error_kind": self.error_kind,
            "error_detail": self.error_detail,
            "failed_check": self.failed_check,
            "checks": [check.to_dict() for check in self.checks],
            "blockers": [blocker.to_dict() for blocker in self.blockers],
            "metadata": self.metadata.to_dict(),
        }


__all__ = (
    "FIRST_CUSTOMER_CONVERSION_HANDOFF_SCHEMA_VERSION",
    "CONVERSION_HANDOFF_CHECK_STATUSES",
    "CONVERSION_HANDOFF_CHECK_SEVERITIES",
    "CONVERSION_HANDOFF_BLOCKER_SEVERITIES",
    "CONVERSION_HANDOFF_ARTIFACT_TYPES",
    "ConversionHandoffCheck",
    "ConversionHandoffArtifact",
    "ConversionHandoffBlocker",
    "FirstCustomerConversionHandoffResult",
    "FirstCustomerConversionHandoffError",
)
