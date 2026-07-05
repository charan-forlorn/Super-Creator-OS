"""SCOS Stage 4.18 shared commercial domain models.

Shared immutable primitives reused across commercial stages: checks, blockers,
artifact references, and manual actions. These models consolidate the shapes
that Stage 4.1-4.17 modules re-declare per feature, so future stages (and the
Stage 4.19 release gate) can build on one vocabulary without refactoring the
existing stage contracts.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from .report_models import FrozenMap
except ImportError:  # direct-module execution (tests insert the package dir)
    from report_models import FrozenMap

COMMERCIAL_DOMAIN_SCHEMA_VERSION = 1

CHECK_STATUSES = ("success", "failure", "skipped")
CHECK_SEVERITIES = ("info", "warning", "error", "critical")
BLOCKER_SEVERITIES = ("warning", "error", "critical")
MANUAL_ACTION_PRIORITIES = ("low", "normal", "high", "urgent")


def _require_allowed(field_name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ValueError(
            f"{field_name} must be one of {list(allowed)}, got {value!r}"
        )


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


@dataclass(frozen=True)
class CommercialCheck:
    """One deterministic pass/fail/skip observation inside a commercial stage."""

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
        object.__setattr__(self, "artifact_path", _optional_str(self.artifact_path))
        object.__setattr__(self, "error_kind", _optional_str(self.error_kind))
        object.__setattr__(self, "error_detail", _optional_str(self.error_detail))
        if not isinstance(self.metadata, FrozenMap):
            object.__setattr__(self, "metadata", FrozenMap.from_mapping(dict(self.metadata)))
        _require_allowed("status", self.status, CHECK_STATUSES)
        _require_allowed("severity", self.severity, CHECK_SEVERITIES)

    @staticmethod
    def of(
        check_name: str,
        status: str,
        severity: str = "info",
        *,
        artifact_path: str | None = None,
        error_kind: str | None = None,
        error_detail: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "CommercialCheck":
        return CommercialCheck(
            check_name=check_name,
            status=status,
            severity=severity,
            artifact_path=artifact_path,
            error_kind=error_kind,
            error_detail=error_detail,
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
class CommercialBlocker:
    """A named condition that blocks a commercial stage from proceeding."""

    blocker_id: str
    category: str
    severity: str
    title: str
    detail: str
    recommended_action: str
    source: str
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "blocker_id", str(self.blocker_id))
        object.__setattr__(self, "category", str(self.category))
        object.__setattr__(self, "severity", str(self.severity))
        object.__setattr__(self, "title", str(self.title))
        object.__setattr__(self, "detail", str(self.detail))
        object.__setattr__(self, "recommended_action", str(self.recommended_action))
        object.__setattr__(self, "source", str(self.source))
        if not isinstance(self.metadata, FrozenMap):
            object.__setattr__(self, "metadata", FrozenMap.from_mapping(dict(self.metadata)))
        _require_allowed("severity", self.severity, BLOCKER_SEVERITIES)

    @staticmethod
    def of(
        blocker_id: str,
        category: str,
        severity: str,
        title: str,
        detail: str,
        recommended_action: str,
        source: str,
        metadata: dict[str, Any] | None = None,
    ) -> "CommercialBlocker":
        return CommercialBlocker(
            blocker_id=blocker_id,
            category=category,
            severity=severity,
            title=title,
            detail=detail,
            recommended_action=recommended_action,
            source=source,
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
            "source": self.source,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class CommercialArtifactReference:
    """A stable pointer to a local artifact, optionally checksummed."""

    artifact_id: str
    artifact_type: str
    path: str
    sha256: str | None
    required: bool
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_id", str(self.artifact_id))
        object.__setattr__(self, "artifact_type", str(self.artifact_type))
        object.__setattr__(self, "path", str(self.path))
        object.__setattr__(self, "sha256", _optional_str(self.sha256))
        object.__setattr__(self, "required", bool(self.required))
        if not isinstance(self.metadata, FrozenMap):
            object.__setattr__(self, "metadata", FrozenMap.from_mapping(dict(self.metadata)))

    @staticmethod
    def of(
        artifact_id: str,
        artifact_type: str,
        path: str,
        *,
        sha256: str | None = None,
        required: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> "CommercialArtifactReference":
        return CommercialArtifactReference(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            path=path,
            sha256=sha256,
            required=required,
            metadata=FrozenMap.from_mapping(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "path": self.path,
            "sha256": self.sha256,
            "required": self.required,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class CommercialManualAction:
    """A human-operator action the system may recommend but never executes."""

    action: str
    reason: str
    priority: str
    due_at: str | None
    requires_human_review: bool
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "action", str(self.action))
        object.__setattr__(self, "reason", str(self.reason))
        object.__setattr__(self, "priority", str(self.priority))
        object.__setattr__(self, "due_at", _optional_str(self.due_at))
        object.__setattr__(self, "requires_human_review", bool(self.requires_human_review))
        if not isinstance(self.metadata, FrozenMap):
            object.__setattr__(self, "metadata", FrozenMap.from_mapping(dict(self.metadata)))
        _require_allowed("priority", self.priority, MANUAL_ACTION_PRIORITIES)

    @staticmethod
    def of(
        action: str,
        reason: str,
        priority: str = "normal",
        *,
        due_at: str | None = None,
        requires_human_review: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> "CommercialManualAction":
        return CommercialManualAction(
            action=action,
            reason=reason,
            priority=priority,
            due_at=due_at,
            requires_human_review=requires_human_review,
            metadata=FrozenMap.from_mapping(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "priority": self.priority,
            "due_at": self.due_at,
            "requires_human_review": self.requires_human_review,
            "metadata": self.metadata.to_dict(),
        }
