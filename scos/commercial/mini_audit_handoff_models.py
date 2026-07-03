"""SCOS Stage 4.14 first prospect mini-audit handoff models.

Immutable, local-first models for a manual mini-audit handoff package generated
over a Stage 4.13 follow-up decision. These models reuse the Stage 4.1
``FrozenMap`` implementation and serialize with explicit key order.

This layer is a local package-generation layer only. It never sends anything,
never contacts external services, never keeps a customer database, never touches
billing, and never mutates the Stage 4.12 / Stage 4.13 source artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from .report_models import FrozenMap, _freeze_value
except ImportError:  # pragma: no cover - supports this repo's plain-script tests
    from report_models import FrozenMap, _freeze_value

FIRST_PROSPECT_MINI_AUDIT_HANDOFF_SCHEMA_VERSION = 1

HANDOFF_CHECK_STATUSES = ("success", "failure", "skipped")
HANDOFF_CHECK_SEVERITIES = ("info", "warning", "error")

HANDOFF_ARTIFACT_TYPES = (
    "manifest",
    "markdown",
    "json",
    "checklist",
    "evidence",
    "summary",
)


@dataclass(frozen=True)
class MiniAuditHandoffCheck:
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
        if self.status not in HANDOFF_CHECK_STATUSES:
            raise ValueError(f"invalid handoff check status: {self.status!r}")
        if self.severity not in HANDOFF_CHECK_SEVERITIES:
            raise ValueError(f"invalid handoff check severity: {self.severity!r}")
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
    ) -> "MiniAuditHandoffCheck":
        return MiniAuditHandoffCheck(
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
class MiniAuditHandoffArtifact:
    artifact_name: str
    artifact_type: str
    path: str
    required: bool
    description: str
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_name", str(self.artifact_name))
        # artifact_type membership is enforced by the generator so it can shape a
        # typed error rather than raising here.
        object.__setattr__(self, "artifact_type", str(self.artifact_type))
        object.__setattr__(self, "path", str(self.path))
        object.__setattr__(self, "required", bool(self.required))
        object.__setattr__(self, "description", str(self.description))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    @staticmethod
    def of(
        *,
        artifact_name: str,
        artifact_type: str,
        path: str,
        required: bool = True,
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> "MiniAuditHandoffArtifact":
        return MiniAuditHandoffArtifact(
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
class FirstProspectMiniAuditHandoffResult:
    ok: bool
    schema_version: int
    accepted: bool
    handoff_id: str
    prospect_id: str
    decision_id: str
    execution_log_id: str | None
    checked_at: str
    output_dir: str
    manifest_path: str
    artifacts: tuple[MiniAuditHandoffArtifact, ...]
    checks: tuple[MiniAuditHandoffCheck, ...]
    blockers: tuple[str, ...]
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "accepted", bool(self.accepted))
        object.__setattr__(self, "handoff_id", str(self.handoff_id))
        object.__setattr__(self, "prospect_id", str(self.prospect_id))
        object.__setattr__(self, "decision_id", str(self.decision_id))
        if self.execution_log_id is not None:
            object.__setattr__(self, "execution_log_id", str(self.execution_log_id))
        object.__setattr__(self, "checked_at", str(self.checked_at))
        object.__setattr__(self, "output_dir", str(self.output_dir))
        object.__setattr__(self, "manifest_path", str(self.manifest_path))
        object.__setattr__(self, "artifacts", tuple(self.artifacts))
        object.__setattr__(self, "checks", tuple(self.checks))
        object.__setattr__(self, "blockers", tuple(str(item) for item in self.blockers))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "accepted": self.accepted,
            "handoff_id": self.handoff_id,
            "prospect_id": self.prospect_id,
            "decision_id": self.decision_id,
            "execution_log_id": self.execution_log_id,
            "checked_at": self.checked_at,
            "output_dir": self.output_dir,
            "manifest_path": self.manifest_path,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "checks": [check.to_dict() for check in self.checks],
            "blockers": list(self.blockers),
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class FirstProspectMiniAuditHandoffError:
    ok: bool
    schema_version: int
    error_kind: str
    error_detail: str
    failed_check: str
    checks: tuple[MiniAuditHandoffCheck, ...]
    blockers: tuple[str, ...]
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", False)
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "error_kind", str(self.error_kind))
        object.__setattr__(self, "error_detail", str(self.error_detail))
        object.__setattr__(self, "failed_check", str(self.failed_check))
        object.__setattr__(self, "checks", tuple(self.checks))
        object.__setattr__(self, "blockers", tuple(str(item) for item in self.blockers))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    @staticmethod
    def of(
        error_kind: str,
        error_detail: str,
        failed_check: str,
        checks: tuple[MiniAuditHandoffCheck, ...] = (),
        blockers: tuple[str, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> "FirstProspectMiniAuditHandoffError":
        base = {"schema_version": FIRST_PROSPECT_MINI_AUDIT_HANDOFF_SCHEMA_VERSION}
        base.update(metadata or {})
        return FirstProspectMiniAuditHandoffError(
            ok=False,
            schema_version=FIRST_PROSPECT_MINI_AUDIT_HANDOFF_SCHEMA_VERSION,
            error_kind=str(error_kind),
            error_detail=str(error_detail),
            failed_check=str(failed_check),
            checks=tuple(checks),
            blockers=tuple(str(item) for item in blockers),
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
            "blockers": list(self.blockers),
            "metadata": self.metadata.to_dict(),
        }


__all__ = (
    "FIRST_PROSPECT_MINI_AUDIT_HANDOFF_SCHEMA_VERSION",
    "HANDOFF_CHECK_STATUSES",
    "HANDOFF_CHECK_SEVERITIES",
    "HANDOFF_ARTIFACT_TYPES",
    "MiniAuditHandoffCheck",
    "MiniAuditHandoffArtifact",
    "FirstProspectMiniAuditHandoffResult",
    "FirstProspectMiniAuditHandoffError",
)
