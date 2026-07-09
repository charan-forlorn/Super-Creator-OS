"""Stage 7.6 immutable operator command view models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

OPERATOR_COMMAND_VIEW_SCHEMA_VERSION = 1

APPROVAL_STATES = (
    "pending",
    "approved",
    "denied",
    "missing_approval",
    "tampered",
    "executed",
    "blocked",
    "unknown",
)
EXECUTION_STATES = (
    "not_executed",
    "executed",
    "blocked_missing_approval",
    "blocked_denied",
    "blocked_tampered_approval",
    "blocked_not_allowlisted",
    "blocked_validation_failed",
    "unknown",
)
AUDIT_STATES = ("audited", "missing", "tampered", "unknown")
EVENT_STATES = ("present", "missing", "unknown")
GO_NO_GO_VALUES = ("GO", "NO_GO")


def _require_allowed(field_name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ValueError(f"{field_name} must be one of {list(allowed)}, got {value!r}")


def _strings(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    return tuple(sorted(str(value) for value in values))


def _pairs(values: Any) -> tuple[tuple[str, str], ...]:
    if values is None:
        return ()
    pairs: list[tuple[str, str]] = []
    for item in values:
        pair = tuple(item)
        if len(pair) != 2:
            raise ValueError(f"metadata entries must be pairs, got {item!r}")
        pairs.append((str(pair[0]), str(pair[1])))
    return tuple(sorted(pairs, key=lambda pair: pair[0]))


@dataclass(frozen=True)
class OperatorCommandEvidenceReference:
    reference_id: str
    reference_type: str
    source_stage: str
    path: str
    exists: bool
    readable: bool
    digest: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "reference_id", str(self.reference_id))
        object.__setattr__(self, "reference_type", str(self.reference_type))
        object.__setattr__(self, "source_stage", str(self.source_stage))
        object.__setattr__(self, "path", str(self.path))
        object.__setattr__(self, "exists", bool(self.exists))
        object.__setattr__(self, "readable", bool(self.readable))
        object.__setattr__(self, "digest", None if self.digest is None else str(self.digest))

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference_id": self.reference_id,
            "reference_type": self.reference_type,
            "source_stage": self.source_stage,
            "path": self.path,
            "exists": self.exists,
            "readable": self.readable,
            "digest": self.digest,
        }


@dataclass(frozen=True)
class OperatorCommandApprovalState:
    command_id: str
    approval_state: str
    terminal: bool
    human_readable_status: str
    required_operator_action: str
    evidence_references: tuple[OperatorCommandEvidenceReference, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", str(self.command_id))
        object.__setattr__(self, "approval_state", str(self.approval_state))
        object.__setattr__(self, "terminal", bool(self.terminal))
        object.__setattr__(self, "human_readable_status", str(self.human_readable_status))
        object.__setattr__(self, "required_operator_action", str(self.required_operator_action))
        for reference in self.evidence_references:
            if not isinstance(reference, OperatorCommandEvidenceReference):
                raise ValueError("evidence_references must contain OperatorCommandEvidenceReference values")
        object.__setattr__(
            self,
            "evidence_references",
            tuple(sorted(self.evidence_references, key=lambda item: item.reference_id)),
        )
        _require_allowed("approval_state", self.approval_state, APPROVAL_STATES)

    def to_dict(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "approval_state": self.approval_state,
            "terminal": self.terminal,
            "human_readable_status": self.human_readable_status,
            "required_operator_action": self.required_operator_action,
            "evidence_references": [reference.to_dict() for reference in self.evidence_references],
        }


@dataclass(frozen=True)
class ExecutionEvidenceRecord:
    evidence_id: str
    command_id: str
    execution_state: str
    approval_state: str
    audit_state: str
    event_state: str
    summary: str
    references: tuple[OperatorCommandEvidenceReference, ...]
    metadata: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", str(self.evidence_id))
        object.__setattr__(self, "command_id", str(self.command_id))
        object.__setattr__(self, "execution_state", str(self.execution_state))
        object.__setattr__(self, "approval_state", str(self.approval_state))
        object.__setattr__(self, "audit_state", str(self.audit_state))
        object.__setattr__(self, "event_state", str(self.event_state))
        object.__setattr__(self, "summary", str(self.summary))
        for reference in self.references:
            if not isinstance(reference, OperatorCommandEvidenceReference):
                raise ValueError("references must contain OperatorCommandEvidenceReference values")
        object.__setattr__(self, "references", tuple(sorted(self.references, key=lambda item: item.reference_id)))
        object.__setattr__(self, "metadata", _pairs(self.metadata))
        _require_allowed("execution_state", self.execution_state, EXECUTION_STATES)
        _require_allowed("approval_state", self.approval_state, APPROVAL_STATES)
        _require_allowed("audit_state", self.audit_state, AUDIT_STATES)
        _require_allowed("event_state", self.event_state, EVENT_STATES)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "command_id": self.command_id,
            "execution_state": self.execution_state,
            "approval_state": self.approval_state,
            "audit_state": self.audit_state,
            "event_state": self.event_state,
            "summary": self.summary,
            "references": [reference.to_dict() for reference in self.references],
            "metadata": [[key, value] for key, value in self.metadata],
        }


@dataclass(frozen=True)
class OperatorCommandView:
    view_id: str
    checked_at: str
    command_id: str
    command_type: str
    approval: OperatorCommandApprovalState
    execution: ExecutionEvidenceRecord
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    next_manual_action: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "view_id", str(self.view_id))
        object.__setattr__(self, "checked_at", str(self.checked_at))
        object.__setattr__(self, "command_id", str(self.command_id))
        object.__setattr__(self, "command_type", str(self.command_type))
        if not isinstance(self.approval, OperatorCommandApprovalState):
            raise ValueError("approval must be OperatorCommandApprovalState")
        if not isinstance(self.execution, ExecutionEvidenceRecord):
            raise ValueError("execution must be ExecutionEvidenceRecord")
        object.__setattr__(self, "warnings", _strings(self.warnings))
        object.__setattr__(self, "blockers", _strings(self.blockers))
        object.__setattr__(self, "next_manual_action", str(self.next_manual_action))

    def to_dict(self) -> dict[str, Any]:
        return {
            "view_id": self.view_id,
            "checked_at": self.checked_at,
            "command_id": self.command_id,
            "command_type": self.command_type,
            "approval": self.approval.to_dict(),
            "execution": self.execution.to_dict(),
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "next_manual_action": self.next_manual_action,
        }


@dataclass(frozen=True)
class OperatorCommandViewTotals:
    pending: int
    approved: int
    denied: int
    missing_approval: int
    executed: int
    blocked: int
    audited: int

    def __post_init__(self) -> None:
        for field_name in (
            "pending",
            "approved",
            "denied",
            "missing_approval",
            "executed",
            "blocked",
            "audited",
        ):
            value = int(getattr(self, field_name))
            if value < 0:
                raise ValueError(f"{field_name} must be >= 0")
            object.__setattr__(self, field_name, value)

    def to_dict(self) -> dict[str, int]:
        return {
            "pending": self.pending,
            "approved": self.approved,
            "denied": self.denied,
            "missing_approval": self.missing_approval,
            "executed": self.executed,
            "blocked": self.blocked,
            "audited": self.audited,
        }


@dataclass(frozen=True)
class OperatorCommandViewSnapshot:
    snapshot_id: str
    checked_at: str
    views: tuple[OperatorCommandView, ...]
    totals: OperatorCommandViewTotals
    warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    readiness_score: int
    go_no_go: str
    accepted: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "snapshot_id", str(self.snapshot_id))
        object.__setattr__(self, "checked_at", str(self.checked_at))
        for view in self.views:
            if not isinstance(view, OperatorCommandView):
                raise ValueError("views must contain OperatorCommandView values")
        object.__setattr__(self, "views", tuple(sorted(self.views, key=lambda item: item.command_id)))
        if not isinstance(self.totals, OperatorCommandViewTotals):
            raise ValueError("totals must be OperatorCommandViewTotals")
        object.__setattr__(self, "warnings", _strings(self.warnings))
        object.__setattr__(self, "blockers", _strings(self.blockers))
        object.__setattr__(self, "readiness_score", int(self.readiness_score))
        object.__setattr__(self, "go_no_go", str(self.go_no_go))
        object.__setattr__(self, "accepted", bool(self.accepted))
        _require_allowed("go_no_go", self.go_no_go, GO_NO_GO_VALUES)

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "checked_at": self.checked_at,
            "views": [view.to_dict() for view in self.views],
            "totals": self.totals.to_dict(),
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "readiness_score": self.readiness_score,
            "go_no_go": self.go_no_go,
            "accepted": self.accepted,
        }


__all__ = sorted(
    (
        "APPROVAL_STATES",
        "AUDIT_STATES",
        "EVENT_STATES",
        "EXECUTION_STATES",
        "GO_NO_GO_VALUES",
        "OPERATOR_COMMAND_VIEW_SCHEMA_VERSION",
        "ExecutionEvidenceRecord",
        "OperatorCommandApprovalState",
        "OperatorCommandEvidenceReference",
        "OperatorCommandView",
        "OperatorCommandViewSnapshot",
        "OperatorCommandViewTotals",
    )
)
