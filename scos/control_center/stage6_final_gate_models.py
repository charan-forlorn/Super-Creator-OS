"""SCOS Stage 6.10 final Stage 6 integration gate models.

Immutable dataclasses for the Stage 6 final integration gate / release gate /
Stage 7 handoff: the per-check observation, the integration blocker, the Stage
7 handoff item, and the result / error envelopes.

This module never imports ``scos.commercial`` or ``scos.knowledge`` - ``FrozenMap``
is re-declared locally (following the Stage 5.10 ``stage5_certification_models``
pattern) so Stage 6.10 stays free of any cross-package import.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

STAGE6_FINAL_GATE_SCHEMA_VERSION = 1

CHECK_STATUSES = ("success", "failure", "skipped")
CHECK_SEVERITIES = ("info", "warning", "error", "critical")
CHECK_CATEGORIES = (
    "preflight",
    "source_contract",
    "stage6_coherence",
    "safety_boundary",
    "testing",
    "security",
    "stage7_handoff",
)
BLOCKER_SEVERITIES = ("warning", "error", "critical")
HANDOFF_PRIORITIES = ("low", "normal", "high", "urgent")
GO_NO_GO_VALUES = ("GO", "NO_GO")
READINESS_LEVELS = ("certified", "conditionally_ready", "blocked")

# Documented category examples (free-form by contract, not enforced):
# handoff -> read_surface, ui_projection, operator_health_panel,
#            sync_decision, adapter_activation, safety_boundary,
#            documentation


def _freeze_value(value: Any) -> Any:
    if isinstance(value, FrozenMap):
        return value
    if isinstance(value, MappingProxyType):
        value = dict(value)
    if isinstance(value, dict):
        return FrozenMap.from_mapping(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    return value


def _thaw_value(value: Any) -> Any:
    if isinstance(value, FrozenMap):
        return value.to_dict()
    if isinstance(value, tuple):
        return [_thaw_value(item) for item in value]
    return value


@dataclass(frozen=True)
class FrozenMap:
    """Tuple-backed immutable mapping with deterministic serialization."""

    items: tuple[tuple[str, Any], ...]

    @staticmethod
    def from_mapping(mapping: dict[str, Any]) -> "FrozenMap":
        return FrozenMap(
            tuple((str(key), _freeze_value(mapping[key])) for key in sorted(mapping))
        )

    def to_dict(self) -> dict[str, Any]:
        return {key: _thaw_value(value) for key, value in self.items}


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
class Stage6GateCheck:
    """One deterministic observation made by the Stage 6 final integration gate."""

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
        _require_allowed("category", self.category, CHECK_CATEGORIES)

    @staticmethod
    def of(
        check_name: str,
        status: str,
        severity: str = "info",
        *,
        category: str,
        artifact_path: str | None = None,
        error_kind: str | None = None,
        error_detail: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "Stage6GateCheck":
        return Stage6GateCheck(
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
class Stage6GateBlocker:
    """A named condition that blocks Stage 6 final integration / closure."""

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
        _require_allowed("category", self.category, CHECK_CATEGORIES)

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
    ) -> "Stage6GateBlocker":
        return Stage6GateBlocker(
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
class Stage6GateEvidence:
    """One read-only evidence record pointing at a verified Stage 6 artifact."""

    evidence_id: str
    stage: str
    kind: str
    artifact_path: str
    detail: str
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", str(self.evidence_id))
        object.__setattr__(self, "stage", str(self.stage))
        object.__setattr__(self, "kind", str(self.kind))
        object.__setattr__(self, "artifact_path", str(self.artifact_path))
        object.__setattr__(self, "detail", str(self.detail))
        _freeze_metadata(self)

    @staticmethod
    def of(
        evidence_id: str,
        stage: str,
        kind: str,
        artifact_path: str,
        detail: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> "Stage6GateEvidence":
        return Stage6GateEvidence(
            evidence_id=evidence_id,
            stage=stage,
            kind=kind,
            artifact_path=artifact_path,
            detail=detail,
            metadata=FrozenMap.from_mapping(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "stage": self.stage,
            "kind": self.kind,
            "artifact_path": self.artifact_path,
            "detail": self.detail,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class Stage7HandoffItem:
    """One deterministic work item handed off from Stage 6 to Stage 7."""

    item_id: str
    title: str
    category: str
    priority: str
    description: str
    stage7_owner: str
    source_stage6_evidence: str | None
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "item_id", str(self.item_id))
        object.__setattr__(self, "title", str(self.title))
        object.__setattr__(self, "category", str(self.category))
        object.__setattr__(self, "priority", str(self.priority))
        object.__setattr__(self, "description", str(self.description))
        object.__setattr__(self, "stage7_owner", str(self.stage7_owner))
        object.__setattr__(
            self, "source_stage6_evidence", _optional_str(self.source_stage6_evidence)
        )
        _freeze_metadata(self)
        _require_allowed("priority", self.priority, HANDOFF_PRIORITIES)

    @staticmethod
    def of(
        item_id: str,
        title: str,
        category: str,
        priority: str = "normal",
        *,
        description: str = "",
        stage7_owner: str = "stage7-operator",
        source_stage6_evidence: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "Stage7HandoffItem":
        return Stage7HandoffItem(
            item_id=item_id,
            title=title,
            category=category,
            priority=priority,
            description=description,
            stage7_owner=stage7_owner,
            source_stage6_evidence=source_stage6_evidence,
            metadata=FrozenMap.from_mapping(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "title": self.title,
            "category": self.category,
            "priority": self.priority,
            "description": self.description,
            "stage7_owner": self.stage7_owner,
            "source_stage6_evidence": self.source_stage6_evidence,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class Stage6FinalIntegrationResult:
    """Complete Stage 6 final integration outcome (GO / NO_GO)."""

    ok: bool
    schema_version: int
    accepted: bool
    gate_id: str
    checked_at: str
    stage: str
    stage_closed: bool
    go_no_go: str
    readiness_level: str
    readiness_score: int
    readiness_max_score: int
    checks: tuple[Stage6GateCheck, ...]
    evidence: tuple[Stage6GateEvidence, ...]
    blockers: tuple[Stage6GateBlocker, ...]
    stage7_handoff_items: tuple[Stage7HandoffItem, ...]
    output_path: str | None
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "accepted", bool(self.accepted))
        object.__setattr__(self, "gate_id", str(self.gate_id))
        object.__setattr__(self, "checked_at", str(self.checked_at))
        object.__setattr__(self, "stage", str(self.stage))
        object.__setattr__(self, "stage_closed", bool(self.stage_closed))
        object.__setattr__(self, "go_no_go", str(self.go_no_go))
        object.__setattr__(self, "readiness_level", str(self.readiness_level))
        object.__setattr__(self, "readiness_score", int(self.readiness_score))
        object.__setattr__(self, "readiness_max_score", int(self.readiness_max_score))
        object.__setattr__(self, "checks", tuple(self.checks))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "blockers", tuple(self.blockers))
        object.__setattr__(self, "stage7_handoff_items", tuple(self.stage7_handoff_items))
        object.__setattr__(self, "output_path", _optional_str(self.output_path))
        _freeze_metadata(self)
        _require_allowed("go_no_go", self.go_no_go, GO_NO_GO_VALUES)
        _require_allowed("readiness_level", self.readiness_level, READINESS_LEVELS)
        has_error_or_critical = any(
            blocker.severity in ("error", "critical") for blocker in self.blockers
        )
        if self.stage_closed and not (self.accepted and not has_error_or_critical):
            raise ValueError(
                "stage_closed=True requires accepted=True and zero error/critical blockers"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "accepted": self.accepted,
            "gate_id": self.gate_id,
            "checked_at": self.checked_at,
            "stage": self.stage,
            "stage_closed": self.stage_closed,
            "go_no_go": self.go_no_go,
            "readiness_level": self.readiness_level,
            "readiness_score": self.readiness_score,
            "readiness_max_score": self.readiness_max_score,
            "checks": [check.to_dict() for check in self.checks],
            "evidence": [evidence.to_dict() for evidence in self.evidence],
            "blockers": [blocker.to_dict() for blocker in self.blockers],
            "stage7_handoff_items": [
                item.to_dict() for item in self.stage7_handoff_items
            ],
            "output_path": self.output_path,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class Stage6FinalIntegrationError:
    """Deterministic expected-failure envelope for the Stage 6 final gate."""

    ok: bool
    schema_version: int
    error_kind: str
    error_detail: str
    failed_check: str
    checks: tuple[Stage6GateCheck, ...]
    blockers: tuple[Stage6GateBlocker, ...]
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
        checks: tuple[Stage6GateCheck, ...] = (),
        blockers: tuple[Stage6GateBlocker, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> "Stage6FinalIntegrationError":
        return Stage6FinalIntegrationError(
            ok=False,
            schema_version=STAGE6_FINAL_GATE_SCHEMA_VERSION,
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


__all__ = sorted(
    (
        "BLOCKER_SEVERITIES",
        "CHECK_CATEGORIES",
        "CHECK_SEVERITIES",
        "CHECK_STATUSES",
        "FrozenMap",
        "GO_NO_GO_VALUES",
        "HANDOFF_PRIORITIES",
        "READINESS_LEVELS",
        "STAGE6_FINAL_GATE_SCHEMA_VERSION",
        "Stage6FinalIntegrationError",
        "Stage6FinalIntegrationResult",
        "Stage6GateBlocker",
        "Stage6GateCheck",
        "Stage6GateEvidence",
        "Stage7HandoffItem",
    )
)
