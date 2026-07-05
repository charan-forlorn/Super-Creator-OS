"""SCOS Stage 4.19 final release gate models.

Immutable dataclasses for the Stage 4 final commercial release gate: the
per-check observation, the release blocker, the Stage 5 handoff item, and the
result / error envelopes. These reuse the Stage 4.18 shared vocabulary
(``FrozenMap`` and the allowed status / severity / priority tuples from
``domain_models``) instead of re-declaring them.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from .report_models import FrozenMap
    from .domain_models import (
        BLOCKER_SEVERITIES,
        CHECK_SEVERITIES,
        CHECK_STATUSES,
        MANUAL_ACTION_PRIORITIES,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from report_models import FrozenMap
    from domain_models import (
        BLOCKER_SEVERITIES,
        CHECK_SEVERITIES,
        CHECK_STATUSES,
        MANUAL_ACTION_PRIORITIES,
    )

STAGE4_FINAL_RELEASE_GATE_SCHEMA_VERSION = 1

GO_NO_GO_VALUES = ("GO", "CONDITIONAL_GO", "NO_GO")
READINESS_LEVELS = (
    "stage4_complete",
    "stage4_complete_with_warnings",
    "stage4_blocked",
)

# Documented category examples (free-form by contract, not enforced):
# checks   -> preflight, source_contract, commercial_pipeline,
#             hardening_foundation, testing, security, release_readiness,
#             stage5_handoff
# handoff  -> control_center_backend, command_api, event_stream,
#             operator_approval, security, customer_workflow,
#             commercial_execution, productization, monitoring


def _require_allowed(field_name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ValueError(f"{field_name} must be one of {list(allowed)}, got {value!r}")


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _freeze_metadata(instance: Any) -> None:
    if not isinstance(instance.metadata, FrozenMap):
        object.__setattr__(
            instance, "metadata", FrozenMap.from_mapping(dict(instance.metadata or {}))
        )


@dataclass(frozen=True)
class Stage4ReleaseCheck:
    """One deterministic observation made by the Stage 4 final release gate."""

    check_name: str
    status: str
    severity: str
    category: str
    artifact_path: str | None
    error_kind: str | None
    error_detail: str | None
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "check_name", str(self.check_name))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "severity", str(self.severity))
        object.__setattr__(self, "category", str(self.category))
        object.__setattr__(self, "artifact_path", _optional_str(self.artifact_path))
        object.__setattr__(self, "error_kind", _optional_str(self.error_kind))
        object.__setattr__(self, "error_detail", _optional_str(self.error_detail))
        _freeze_metadata(self)
        _require_allowed("status", self.status, CHECK_STATUSES)
        _require_allowed("severity", self.severity, CHECK_SEVERITIES)

    @staticmethod
    def of(
        check_name: str,
        status: str,
        severity: str = "info",
        *,
        category: str = "release_readiness",
        artifact_path: str | None = None,
        error_kind: str | None = None,
        error_detail: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "Stage4ReleaseCheck":
        return Stage4ReleaseCheck(
            check_name=check_name,
            status=status,
            severity=severity,
            category=category,
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
            "category": self.category,
            "artifact_path": self.artifact_path,
            "error_kind": self.error_kind,
            "error_detail": self.error_detail,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class Stage4ReleaseBlocker:
    """A named condition that blocks the Stage 4 final release."""

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
        object.__setattr__(self, "title", str(self.title))
        object.__setattr__(self, "detail", str(self.detail))
        object.__setattr__(self, "recommended_action", str(self.recommended_action))
        object.__setattr__(self, "source_check", str(self.source_check))
        _freeze_metadata(self)
        _require_allowed("severity", self.severity, BLOCKER_SEVERITIES)

    @staticmethod
    def of(
        blocker_id: str,
        category: str,
        severity: str,
        title: str,
        detail: str,
        recommended_action: str,
        source_check: str,
        metadata: dict[str, Any] | None = None,
    ) -> "Stage4ReleaseBlocker":
        return Stage4ReleaseBlocker(
            blocker_id=blocker_id,
            category=category,
            severity=severity,
            title=title,
            detail=detail,
            recommended_action=recommended_action,
            source_check=source_check,
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
class Stage5HandoffItem:
    """One deterministic work item handed off from Stage 4 to Stage 5."""

    item_id: str
    title: str
    category: str
    priority: str
    description: str
    stage5_owner: str
    source_stage4_evidence: str | None
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "item_id", str(self.item_id))
        object.__setattr__(self, "title", str(self.title))
        object.__setattr__(self, "category", str(self.category))
        object.__setattr__(self, "priority", str(self.priority))
        object.__setattr__(self, "description", str(self.description))
        object.__setattr__(self, "stage5_owner", str(self.stage5_owner))
        object.__setattr__(
            self, "source_stage4_evidence", _optional_str(self.source_stage4_evidence)
        )
        _freeze_metadata(self)
        _require_allowed("priority", self.priority, MANUAL_ACTION_PRIORITIES)

    @staticmethod
    def of(
        item_id: str,
        title: str,
        category: str,
        priority: str = "normal",
        *,
        description: str = "",
        stage5_owner: str = "stage5-operator",
        source_stage4_evidence: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "Stage5HandoffItem":
        return Stage5HandoffItem(
            item_id=item_id,
            title=title,
            category=category,
            priority=priority,
            description=description,
            stage5_owner=stage5_owner,
            source_stage4_evidence=source_stage4_evidence,
            metadata=FrozenMap.from_mapping(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "title": self.title,
            "category": self.category,
            "priority": self.priority,
            "description": self.description,
            "stage5_owner": self.stage5_owner,
            "source_stage4_evidence": self.source_stage4_evidence,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class Stage4FinalReleaseGateResult:
    """Complete Stage 4 final release gate outcome (GO / CONDITIONAL_GO / NO_GO)."""

    ok: bool
    schema_version: int
    accepted: bool
    release_gate_id: str
    checked_at: str
    stage: str
    stage_closed: bool
    go_no_go: str
    readiness_level: str
    readiness_score: int
    readiness_max_score: int
    checks: tuple[Stage4ReleaseCheck, ...]
    blockers: tuple[Stage4ReleaseBlocker, ...]
    stage5_handoff_items: tuple[Stage5HandoffItem, ...]
    output_path: str | None
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "accepted", bool(self.accepted))
        object.__setattr__(self, "release_gate_id", str(self.release_gate_id))
        object.__setattr__(self, "checked_at", str(self.checked_at))
        object.__setattr__(self, "stage", str(self.stage))
        object.__setattr__(self, "stage_closed", bool(self.stage_closed))
        object.__setattr__(self, "go_no_go", str(self.go_no_go))
        object.__setattr__(self, "readiness_level", str(self.readiness_level))
        object.__setattr__(self, "readiness_score", int(self.readiness_score))
        object.__setattr__(self, "readiness_max_score", int(self.readiness_max_score))
        object.__setattr__(self, "checks", tuple(self.checks))
        object.__setattr__(self, "blockers", tuple(self.blockers))
        object.__setattr__(self, "stage5_handoff_items", tuple(self.stage5_handoff_items))
        object.__setattr__(self, "output_path", _optional_str(self.output_path))
        _freeze_metadata(self)
        _require_allowed("go_no_go", self.go_no_go, GO_NO_GO_VALUES)
        _require_allowed("readiness_level", self.readiness_level, READINESS_LEVELS)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "accepted": self.accepted,
            "release_gate_id": self.release_gate_id,
            "checked_at": self.checked_at,
            "stage": self.stage,
            "stage_closed": self.stage_closed,
            "go_no_go": self.go_no_go,
            "readiness_level": self.readiness_level,
            "readiness_score": self.readiness_score,
            "readiness_max_score": self.readiness_max_score,
            "checks": [check.to_dict() for check in self.checks],
            "blockers": [blocker.to_dict() for blocker in self.blockers],
            "stage5_handoff_items": [item.to_dict() for item in self.stage5_handoff_items],
            "output_path": self.output_path,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class Stage4FinalReleaseGateError:
    """Deterministic expected-failure envelope for the Stage 4 final release gate."""

    ok: bool
    schema_version: int
    error_kind: str
    error_detail: str
    failed_check: str
    checks: tuple[Stage4ReleaseCheck, ...]
    blockers: tuple[Stage4ReleaseBlocker, ...]
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "error_kind", str(self.error_kind))
        object.__setattr__(self, "error_detail", str(self.error_detail))
        object.__setattr__(self, "failed_check", str(self.failed_check))
        object.__setattr__(self, "checks", tuple(self.checks))
        object.__setattr__(self, "blockers", tuple(self.blockers))
        _freeze_metadata(self)

    @staticmethod
    def of(
        error_kind: str,
        error_detail: str,
        failed_check: str,
        checks: tuple[Stage4ReleaseCheck, ...] = (),
        blockers: tuple[Stage4ReleaseBlocker, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> "Stage4FinalReleaseGateError":
        return Stage4FinalReleaseGateError(
            ok=False,
            schema_version=STAGE4_FINAL_RELEASE_GATE_SCHEMA_VERSION,
            error_kind=error_kind,
            error_detail=error_detail,
            failed_check=failed_check,
            checks=tuple(checks),
            blockers=tuple(blockers),
            metadata=FrozenMap.from_mapping(metadata or {}),
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
