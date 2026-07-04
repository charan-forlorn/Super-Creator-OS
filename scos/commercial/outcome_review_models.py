"""SCOS Stage 4.16 first prospect outcome review models.

Immutable, local-first models for a read-only *decision/review* layer recorded
over a Stage 4.15 mini-audit delivery log. These models capture the outcome
review that a human operator uses to decide the next manual action toward a
first-customer conversion: whether the prospect is conversion-ready given the
delivery + response evidence, and which manual next action should happen.

This layer reuses the Stage 4.1 ``FrozenMap`` implementation and serializes with
explicit key order. It never sends anything, never contacts external services,
never keeps a customer database, never touches billing, and never mutates the
Stage 4.15 delivery-log artifacts or the Stage 4.14 handoff artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from .report_models import FrozenMap, _freeze_value
except ImportError:  # pragma: no cover - supports this repo's plain-script tests
    from report_models import FrozenMap, _freeze_value

FIRST_PROSPECT_OUTCOME_REVIEW_SCHEMA_VERSION = 1

OUTCOME_REVIEW_CHECK_STATUSES = ("success", "failure", "skipped")
OUTCOME_REVIEW_CHECK_SEVERITIES = ("info", "warning", "error")

OUTCOME_REVIEW_ACTIONS = (
    "WAIT_FOR_RESPONSE",
    "FOLLOW_UP_AFTER_MINI_AUDIT",
    "REQUEST_SCOPE_CONFIRMATION",
    "SEND_REVISED_MINI_AUDIT",
    "ESCALATE_TO_FIRST_CUSTOMER_CONVERSION",
    "CLOSE_NO_GO",
    "BLOCKED",
)

OUTCOME_REVIEW_ACTION_PRIORITIES = ("low", "normal", "high", "urgent")


@dataclass(frozen=True)
class OutcomeReviewCheck:
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
        if self.status not in OUTCOME_REVIEW_CHECK_STATUSES:
            raise ValueError(f"invalid outcome review check status: {self.status!r}")
        if self.severity not in OUTCOME_REVIEW_CHECK_SEVERITIES:
            raise ValueError(f"invalid outcome review check severity: {self.severity!r}")
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
    ) -> "OutcomeReviewCheck":
        return OutcomeReviewCheck(
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
class OutcomeReviewAction:
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
        if self.action not in OUTCOME_REVIEW_ACTIONS:
            raise ValueError(f"invalid outcome review action: {self.action!r}")
        if self.priority not in OUTCOME_REVIEW_ACTION_PRIORITIES:
            raise ValueError(f"invalid outcome review priority: {self.priority!r}")
        if self.due_at is not None:
            object.__setattr__(self, "due_at", str(self.due_at))
        object.__setattr__(self, "requires_human_review", bool(self.requires_human_review))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    @staticmethod
    def of(
        *,
        action: str,
        reason: str,
        priority: str = "normal",
        due_at: str | None = None,
        requires_human_review: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> "OutcomeReviewAction":
        return OutcomeReviewAction(
            action=str(action),
            reason=str(reason),
            priority=str(priority),
            due_at=None if due_at is None else str(due_at),
            requires_human_review=bool(requires_human_review),
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


@dataclass(frozen=True)
class FirstProspectOutcomeReviewResult:
    ok: bool
    schema_version: int
    accepted: bool
    review_id: str
    delivery_log_id: str
    handoff_id: str
    prospect_id: str
    decision_id: str
    execution_log_id: str
    checked_at: str
    conversion_ready: bool
    action: OutcomeReviewAction
    source_delivery_log_path: str
    output_path: str | None
    checks: tuple[OutcomeReviewCheck, ...]
    blockers: tuple[str, ...]
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "accepted", bool(self.accepted))
        object.__setattr__(self, "review_id", str(self.review_id))
        object.__setattr__(self, "delivery_log_id", str(self.delivery_log_id))
        object.__setattr__(self, "handoff_id", str(self.handoff_id))
        object.__setattr__(self, "prospect_id", str(self.prospect_id))
        object.__setattr__(self, "decision_id", str(self.decision_id))
        object.__setattr__(self, "execution_log_id", str(self.execution_log_id))
        object.__setattr__(self, "checked_at", str(self.checked_at))
        object.__setattr__(self, "conversion_ready", bool(self.conversion_ready))
        object.__setattr__(self, "source_delivery_log_path", str(self.source_delivery_log_path))
        if self.output_path is not None:
            object.__setattr__(self, "output_path", str(self.output_path))
        object.__setattr__(self, "checks", tuple(self.checks))
        object.__setattr__(self, "blockers", tuple(str(item) for item in self.blockers))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "accepted": self.accepted,
            "review_id": self.review_id,
            "delivery_log_id": self.delivery_log_id,
            "handoff_id": self.handoff_id,
            "prospect_id": self.prospect_id,
            "decision_id": self.decision_id,
            "execution_log_id": self.execution_log_id,
            "checked_at": self.checked_at,
            "conversion_ready": self.conversion_ready,
            "action": self.action.to_dict(),
            "source_delivery_log_path": self.source_delivery_log_path,
            "output_path": self.output_path,
            "checks": [check.to_dict() for check in self.checks],
            "blockers": list(self.blockers),
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class FirstProspectOutcomeReviewError:
    ok: bool
    schema_version: int
    error_kind: str
    error_detail: str
    failed_check: str
    checks: tuple[OutcomeReviewCheck, ...]
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
        checks: tuple[OutcomeReviewCheck, ...] = (),
        blockers: tuple[str, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> "FirstProspectOutcomeReviewError":
        base = {"schema_version": FIRST_PROSPECT_OUTCOME_REVIEW_SCHEMA_VERSION}
        base.update(metadata or {})
        return FirstProspectOutcomeReviewError(
            ok=False,
            schema_version=FIRST_PROSPECT_OUTCOME_REVIEW_SCHEMA_VERSION,
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
    "FIRST_PROSPECT_OUTCOME_REVIEW_SCHEMA_VERSION",
    "OUTCOME_REVIEW_CHECK_STATUSES",
    "OUTCOME_REVIEW_CHECK_SEVERITIES",
    "OUTCOME_REVIEW_ACTIONS",
    "OUTCOME_REVIEW_ACTION_PRIORITIES",
    "OutcomeReviewCheck",
    "OutcomeReviewAction",
    "FirstProspectOutcomeReviewResult",
    "FirstProspectOutcomeReviewError",
)
