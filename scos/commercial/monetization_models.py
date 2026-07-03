"""SCOS Stage 4.7 monetization readiness review models.

Immutable, local-first models for the Stage 4.7 monetization readiness review.
They store only commercial-owned primitives and tuple-backed structures, reuse
the Stage 4.1 ``FrozenMap`` (never a duplicate implementation), and serialize
deterministically: tuples render as lists, ``FrozenMap`` renders as a plain
dict, explicit key order is fixed, and callers apply
``json.dumps(..., sort_keys=True, indent=2)``. No real clock, no random, no
UUID is ever consulted.

Stage 4.7 is a *review* layer only: these models describe the outcome of
inspecting artifacts that already exist on disk (an accepted Stage 4.5
acceptance report and a Stage 4.6 operating kit). They never rebuild, mutate,
or delete any inspected artifact.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from .report_models import FrozenMap, _freeze_value
except ImportError:  # pragma: no cover - supports this repo's plain-script tests
    from report_models import FrozenMap, _freeze_value

MONETIZATION_READINESS_SCHEMA_VERSION = 1

READINESS_CHECK_STATUSES = ("success", "failure", "skipped")
READINESS_CHECK_SEVERITIES = ("info", "warning", "error", "critical")


@dataclass(frozen=True)
class MonetizationReadinessCheck:
    """One recorded readiness check with its category, outcome, and score."""

    check_name: str
    category: str
    status: str
    severity: str
    score: int
    max_score: int
    artifact_path: str | None
    error_kind: str | None
    error_detail: str | None
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "check_name", str(self.check_name))
        object.__setattr__(self, "category", str(self.category))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "severity", str(self.severity))
        object.__setattr__(self, "score", int(self.score))
        object.__setattr__(self, "max_score", int(self.max_score))
        if self.status not in READINESS_CHECK_STATUSES:
            raise ValueError(f"invalid readiness check status: {self.status!r}")
        if self.severity not in READINESS_CHECK_SEVERITIES:
            raise ValueError(f"invalid readiness check severity: {self.severity!r}")
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
        category: str,
        status: str,
        severity: str,
        score: int,
        max_score: int,
        *,
        artifact_path: str | None = None,
        error_kind: str | None = None,
        error_detail: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "MonetizationReadinessCheck":
        return MonetizationReadinessCheck(
            check_name=str(check_name),
            category=str(category),
            status=str(status),
            severity=str(severity),
            score=int(score),
            max_score=int(max_score),
            artifact_path=None if artifact_path is None else str(artifact_path),
            error_kind=None if error_kind is None else str(error_kind),
            error_detail=None if error_detail is None else str(error_detail),
            metadata=FrozenMap.from_mapping(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_name": self.check_name,
            "category": self.category,
            "status": self.status,
            "severity": self.severity,
            "score": self.score,
            "max_score": self.max_score,
            "artifact_path": self.artifact_path,
            "error_kind": self.error_kind,
            "error_detail": self.error_detail,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class MonetizationGap:
    """One identified monetization readiness gap and its recommended action."""

    gap_id: str
    category: str
    severity: str
    title: str
    detail: str
    recommended_action: str
    blocking: bool
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "gap_id", str(self.gap_id))
        object.__setattr__(self, "category", str(self.category))
        object.__setattr__(self, "severity", str(self.severity))
        object.__setattr__(self, "title", str(self.title))
        object.__setattr__(self, "detail", str(self.detail))
        object.__setattr__(self, "recommended_action", str(self.recommended_action))
        object.__setattr__(self, "blocking", bool(self.blocking))
        if self.severity not in READINESS_CHECK_SEVERITIES:
            raise ValueError(f"invalid gap severity: {self.severity!r}")
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    @staticmethod
    def of(
        gap_id: str,
        category: str,
        severity: str,
        title: str,
        detail: str,
        recommended_action: str,
        blocking: bool,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> "MonetizationGap":
        return MonetizationGap(
            gap_id=str(gap_id),
            category=str(category),
            severity=str(severity),
            title=str(title),
            detail=str(detail),
            recommended_action=str(recommended_action),
            blocking=bool(blocking),
            metadata=FrozenMap.from_mapping(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "gap_id": self.gap_id,
            "category": self.category,
            "severity": self.severity,
            "title": self.title,
            "detail": self.detail,
            "recommended_action": self.recommended_action,
            "blocking": self.blocking,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class MonetizationReadinessResult:
    """Deterministic monetization readiness result with score and decision."""

    ok: bool
    schema_version: int
    ready: bool
    readiness_id: str
    checked_at: str
    score: int
    max_score: int
    readiness_level: str
    go_no_go: str
    acceptance_report_path: str | None
    operating_kit_path: str | None
    checks: tuple[MonetizationReadinessCheck, ...]
    gaps: tuple[MonetizationGap, ...]
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "ready", bool(self.ready))
        object.__setattr__(self, "readiness_id", str(self.readiness_id))
        object.__setattr__(self, "checked_at", str(self.checked_at))
        object.__setattr__(self, "score", int(self.score))
        object.__setattr__(self, "max_score", int(self.max_score))
        object.__setattr__(self, "readiness_level", str(self.readiness_level))
        object.__setattr__(self, "go_no_go", str(self.go_no_go))
        if self.acceptance_report_path is not None:
            object.__setattr__(self, "acceptance_report_path", str(self.acceptance_report_path))
        if self.operating_kit_path is not None:
            object.__setattr__(self, "operating_kit_path", str(self.operating_kit_path))
        object.__setattr__(self, "checks", tuple(self.checks))
        object.__setattr__(self, "gaps", tuple(self.gaps))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "ready": self.ready,
            "readiness_id": self.readiness_id,
            "checked_at": self.checked_at,
            "score": self.score,
            "max_score": self.max_score,
            "readiness_level": self.readiness_level,
            "go_no_go": self.go_no_go,
            "acceptance_report_path": self.acceptance_report_path,
            "operating_kit_path": self.operating_kit_path,
            "checks": [chk.to_dict() for chk in self.checks],
            "gaps": [gap.to_dict() for gap in self.gaps],
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class MonetizationReadinessError:
    """Deterministic failure object for an aborted readiness review."""

    ok: bool
    schema_version: int
    error_kind: str
    error_detail: str
    failed_check: str
    checks: tuple[MonetizationReadinessCheck, ...]
    gaps: tuple[MonetizationGap, ...]
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", False)
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "error_kind", str(self.error_kind))
        object.__setattr__(self, "error_detail", str(self.error_detail))
        object.__setattr__(self, "failed_check", str(self.failed_check))
        object.__setattr__(self, "checks", tuple(self.checks))
        object.__setattr__(self, "gaps", tuple(self.gaps))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    @staticmethod
    def of(
        error_kind: str,
        error_detail: str,
        failed_check: str,
        checks: tuple["MonetizationReadinessCheck", ...] = (),
        gaps: tuple["MonetizationGap", ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> "MonetizationReadinessError":
        base = {"schema_version": MONETIZATION_READINESS_SCHEMA_VERSION}
        base.update(metadata or {})
        return MonetizationReadinessError(
            ok=False,
            schema_version=MONETIZATION_READINESS_SCHEMA_VERSION,
            error_kind=str(error_kind),
            error_detail=str(error_detail),
            failed_check=str(failed_check),
            checks=tuple(checks),
            gaps=tuple(gaps),
            metadata=FrozenMap.from_mapping(base),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "error_kind": self.error_kind,
            "error_detail": self.error_detail,
            "failed_check": self.failed_check,
            "checks": [chk.to_dict() for chk in self.checks],
            "gaps": [gap.to_dict() for gap in self.gaps],
            "metadata": self.metadata.to_dict(),
        }


__all__ = (
    "MONETIZATION_READINESS_SCHEMA_VERSION",
    "READINESS_CHECK_STATUSES",
    "READINESS_CHECK_SEVERITIES",
    "MonetizationReadinessCheck",
    "MonetizationGap",
    "MonetizationReadinessResult",
    "MonetizationReadinessError",
)
