"""SCOS Stage 4.9 commercial launch certification pack models.

Immutable, local-first models for packaging final launch evidence into a
deterministic certification bundle. These models store only commercial-owned
primitive data, reuse the Stage 4.1 ``FrozenMap`` implementation, and serialize
with explicit key order.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from .report_models import FrozenMap, _freeze_value
except ImportError:  # pragma: no cover - supports this repo's plain-script tests
    from report_models import FrozenMap, _freeze_value

COMMERCIAL_LAUNCH_CERTIFICATION_SCHEMA_VERSION = 1

LAUNCH_CERTIFICATION_CHECK_STATUSES = ("success", "failure", "skipped")
LAUNCH_CERTIFICATION_SEVERITIES = ("info", "warning", "error", "critical")
LAUNCH_CERTIFICATION_STATUSES = ("PASS", "CONDITIONAL_PASS", "FAIL")


@dataclass(frozen=True)
class LaunchCertificationCheck:
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
        if self.status not in LAUNCH_CERTIFICATION_CHECK_STATUSES:
            raise ValueError(f"invalid launch certification check status: {self.status!r}")
        if self.severity not in LAUNCH_CERTIFICATION_SEVERITIES:
            raise ValueError(f"invalid launch certification check severity: {self.severity!r}")
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
    ) -> "LaunchCertificationCheck":
        return LaunchCertificationCheck(
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
class LaunchCertificationBlocker:
    blocker_id: str
    category: str
    severity: str
    title: str
    detail: str
    recommended_action: str
    source_check: str
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "blocker_id", str(self.blocker_id))
        object.__setattr__(self, "category", str(self.category))
        object.__setattr__(self, "severity", str(self.severity))
        if self.severity not in ("warning", "error", "critical"):
            raise ValueError(f"invalid launch certification blocker severity: {self.severity!r}")
        object.__setattr__(self, "title", str(self.title))
        object.__setattr__(self, "detail", str(self.detail))
        object.__setattr__(self, "recommended_action", str(self.recommended_action))
        object.__setattr__(self, "source_check", str(self.source_check))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    @staticmethod
    def of(
        blocker_id: str,
        category: str,
        severity: str,
        title: str,
        detail: str,
        recommended_action: str,
        source_check: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> "LaunchCertificationBlocker":
        return LaunchCertificationBlocker(
            blocker_id=str(blocker_id),
            category=str(category),
            severity=str(severity),
            title=str(title),
            detail=str(detail),
            recommended_action=str(recommended_action),
            source_check=str(source_check),
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
            "source_check": self.source_check,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class LaunchCertificationArtifact:
    artifact_name: str
    artifact_path: str
    artifact_type: str
    required: bool
    exists: bool
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_name", str(self.artifact_name))
        object.__setattr__(self, "artifact_path", str(self.artifact_path))
        object.__setattr__(self, "artifact_type", str(self.artifact_type))
        object.__setattr__(self, "required", bool(self.required))
        object.__setattr__(self, "exists", bool(self.exists))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    @staticmethod
    def of(
        artifact_name: str,
        artifact_path: str,
        artifact_type: str,
        *,
        required: bool,
        exists: bool,
        metadata: dict[str, Any] | None = None,
    ) -> "LaunchCertificationArtifact":
        return LaunchCertificationArtifact(
            artifact_name=str(artifact_name),
            artifact_path=str(artifact_path),
            artifact_type=str(artifact_type),
            required=bool(required),
            exists=bool(exists),
            metadata=FrozenMap.from_mapping(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_name": self.artifact_name,
            "artifact_path": self.artifact_path,
            "artifact_type": self.artifact_type,
            "required": self.required,
            "exists": self.exists,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class LaunchCertificationResult:
    ok: bool
    schema_version: int
    certification_status: str
    launch_certification_id: str
    checked_at: str
    dry_run_report_path: str
    output_dir: str
    launch_certification_report_path: str
    launch_certification_summary_path: str
    launch_readiness_checklist_path: str
    launch_blockers_path: str
    operator_next_steps_path: str
    readiness_score: int
    readiness_max_score: int
    go_no_go: str
    checks: tuple[LaunchCertificationCheck, ...]
    blockers: tuple[LaunchCertificationBlocker, ...]
    artifacts: tuple[LaunchCertificationArtifact, ...]
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "certification_status", str(self.certification_status))
        if self.certification_status not in LAUNCH_CERTIFICATION_STATUSES:
            raise ValueError(f"invalid launch certification status: {self.certification_status!r}")
        object.__setattr__(self, "launch_certification_id", str(self.launch_certification_id))
        object.__setattr__(self, "checked_at", str(self.checked_at))
        object.__setattr__(self, "dry_run_report_path", str(self.dry_run_report_path))
        object.__setattr__(self, "output_dir", str(self.output_dir))
        object.__setattr__(self, "launch_certification_report_path", str(self.launch_certification_report_path))
        object.__setattr__(self, "launch_certification_summary_path", str(self.launch_certification_summary_path))
        object.__setattr__(self, "launch_readiness_checklist_path", str(self.launch_readiness_checklist_path))
        object.__setattr__(self, "launch_blockers_path", str(self.launch_blockers_path))
        object.__setattr__(self, "operator_next_steps_path", str(self.operator_next_steps_path))
        object.__setattr__(self, "readiness_score", int(self.readiness_score))
        object.__setattr__(self, "readiness_max_score", int(self.readiness_max_score))
        object.__setattr__(self, "go_no_go", str(self.go_no_go))
        object.__setattr__(self, "checks", tuple(self.checks))
        object.__setattr__(self, "blockers", tuple(self.blockers))
        object.__setattr__(self, "artifacts", tuple(self.artifacts))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "certification_status": self.certification_status,
            "launch_certification_id": self.launch_certification_id,
            "checked_at": self.checked_at,
            "dry_run_report_path": self.dry_run_report_path,
            "output_dir": self.output_dir,
            "launch_certification_report_path": self.launch_certification_report_path,
            "launch_certification_summary_path": self.launch_certification_summary_path,
            "launch_readiness_checklist_path": self.launch_readiness_checklist_path,
            "launch_blockers_path": self.launch_blockers_path,
            "operator_next_steps_path": self.operator_next_steps_path,
            "readiness_score": self.readiness_score,
            "readiness_max_score": self.readiness_max_score,
            "go_no_go": self.go_no_go,
            "checks": [check.to_dict() for check in self.checks],
            "blockers": [blocker.to_dict() for blocker in self.blockers],
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class LaunchCertificationError:
    ok: bool
    schema_version: int
    error_kind: str
    error_detail: str
    failed_check: str
    checks: tuple[LaunchCertificationCheck, ...]
    blockers: tuple[LaunchCertificationBlocker, ...]
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
        checks: tuple[LaunchCertificationCheck, ...] = (),
        blockers: tuple[LaunchCertificationBlocker, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> "LaunchCertificationError":
        base = {"schema_version": COMMERCIAL_LAUNCH_CERTIFICATION_SCHEMA_VERSION}
        base.update(metadata or {})
        return LaunchCertificationError(
            ok=False,
            schema_version=COMMERCIAL_LAUNCH_CERTIFICATION_SCHEMA_VERSION,
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
    "COMMERCIAL_LAUNCH_CERTIFICATION_SCHEMA_VERSION",
    "LaunchCertificationCheck",
    "LaunchCertificationBlocker",
    "LaunchCertificationArtifact",
    "LaunchCertificationResult",
    "LaunchCertificationError",
)
