"""SCOS Stage 4.15 first prospect mini-audit delivery log models.

Immutable, local-first models for a read-only *evidence/logging* layer recorded
over a Stage 4.14 mini-audit handoff package. These models capture what happened
when a human operator manually handled the handoff: whether it was reviewed,
whether it was manually sent, whether the prospect responded, and what the next
manual action should be.

This layer reuses the Stage 4.1 ``FrozenMap`` implementation and serializes with
explicit key order. It never sends anything, never contacts external services,
never keeps a customer database, never touches billing, and never mutates the
Stage 4.14 handoff artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from .report_models import FrozenMap, _freeze_value
except ImportError:  # pragma: no cover - supports this repo's plain-script tests
    from report_models import FrozenMap, _freeze_value

FIRST_PROSPECT_MINI_AUDIT_DELIVERY_LOG_SCHEMA_VERSION = 1

DELIVERY_CHECK_STATUSES = ("success", "failure", "skipped")
DELIVERY_CHECK_SEVERITIES = ("info", "warning", "error")

OPERATOR_REVIEW_STATUSES = (
    "not_reviewed",
    "reviewed",
    "changes_requested",
    "approved_for_manual_send",
    "blocked",
)

MANUAL_SEND_STATUSES = (
    "not_sent",
    "sent_manually",
    "deferred",
    "blocked",
)

PROSPECT_RESPONSE_STATUSES = (
    "no_response_yet",
    "interested",
    "requested_more_info",
    "requested_call",
    "deferred",
    "not_interested",
    "blocked",
)

DELIVERY_NEXT_ACTIONS = (
    "REVIEW_HANDOFF",
    "SEND_MANUALLY",
    "FOLLOW_UP",
    "WAIT",
    "SCHEDULE_CALL",
    "CLOSE_NO_GO",
    "ESCALATE_TO_FIRST_CUSTOMER_FLOW",
    "BLOCKED",
)

DELIVERY_NEXT_ACTION_PRIORITIES = ("low", "normal", "high", "urgent")


@dataclass(frozen=True)
class MiniAuditDeliveryCheck:
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
        if self.status not in DELIVERY_CHECK_STATUSES:
            raise ValueError(f"invalid delivery check status: {self.status!r}")
        if self.severity not in DELIVERY_CHECK_SEVERITIES:
            raise ValueError(f"invalid delivery check severity: {self.severity!r}")
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
    ) -> "MiniAuditDeliveryCheck":
        return MiniAuditDeliveryCheck(
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
class MiniAuditDeliveryEvidence:
    operator_review_status: str
    manual_send_status: str
    prospect_response_status: str
    manual_channel: str | None
    sent_at: str | None
    response_received_at: str | None
    response_summary: str | None
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "operator_review_status", str(self.operator_review_status))
        object.__setattr__(self, "manual_send_status", str(self.manual_send_status))
        object.__setattr__(self, "prospect_response_status", str(self.prospect_response_status))
        for name in ("manual_channel", "sent_at", "response_received_at", "response_summary"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, str(value))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    @staticmethod
    def of(
        *,
        operator_review_status: str,
        manual_send_status: str,
        prospect_response_status: str,
        manual_channel: str | None = None,
        sent_at: str | None = None,
        response_received_at: str | None = None,
        response_summary: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "MiniAuditDeliveryEvidence":
        return MiniAuditDeliveryEvidence(
            operator_review_status=str(operator_review_status),
            manual_send_status=str(manual_send_status),
            prospect_response_status=str(prospect_response_status),
            manual_channel=None if manual_channel is None else str(manual_channel),
            sent_at=None if sent_at is None else str(sent_at),
            response_received_at=None if response_received_at is None else str(response_received_at),
            response_summary=None if response_summary is None else str(response_summary),
            metadata=FrozenMap.from_mapping(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "operator_review_status": self.operator_review_status,
            "manual_send_status": self.manual_send_status,
            "prospect_response_status": self.prospect_response_status,
            "manual_channel": self.manual_channel,
            "sent_at": self.sent_at,
            "response_received_at": self.response_received_at,
            "response_summary": self.response_summary,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class MiniAuditDeliveryNextAction:
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
    ) -> "MiniAuditDeliveryNextAction":
        return MiniAuditDeliveryNextAction(
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
class FirstProspectMiniAuditDeliveryLogResult:
    ok: bool
    schema_version: int
    accepted: bool
    delivery_log_id: str
    handoff_id: str
    decision_id: str | None
    execution_log_id: str | None
    prospect_id: str
    checked_at: str
    source_handoff_manifest_path: str
    output_path: str | None
    evidence: MiniAuditDeliveryEvidence
    next_action: MiniAuditDeliveryNextAction
    checks: tuple[MiniAuditDeliveryCheck, ...]
    blockers: tuple[str, ...]
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "accepted", bool(self.accepted))
        object.__setattr__(self, "delivery_log_id", str(self.delivery_log_id))
        object.__setattr__(self, "handoff_id", str(self.handoff_id))
        if self.decision_id is not None:
            object.__setattr__(self, "decision_id", str(self.decision_id))
        if self.execution_log_id is not None:
            object.__setattr__(self, "execution_log_id", str(self.execution_log_id))
        object.__setattr__(self, "prospect_id", str(self.prospect_id))
        object.__setattr__(self, "checked_at", str(self.checked_at))
        object.__setattr__(self, "source_handoff_manifest_path", str(self.source_handoff_manifest_path))
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
            "delivery_log_id": self.delivery_log_id,
            "handoff_id": self.handoff_id,
            "decision_id": self.decision_id,
            "execution_log_id": self.execution_log_id,
            "prospect_id": self.prospect_id,
            "checked_at": self.checked_at,
            "source_handoff_manifest_path": self.source_handoff_manifest_path,
            "output_path": self.output_path,
            "evidence": self.evidence.to_dict(),
            "next_action": self.next_action.to_dict(),
            "checks": [check.to_dict() for check in self.checks],
            "blockers": list(self.blockers),
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class FirstProspectMiniAuditDeliveryLogError:
    ok: bool
    schema_version: int
    error_kind: str
    error_detail: str
    failed_check: str
    checks: tuple[MiniAuditDeliveryCheck, ...]
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
        checks: tuple[MiniAuditDeliveryCheck, ...] = (),
        blockers: tuple[str, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> "FirstProspectMiniAuditDeliveryLogError":
        base = {"schema_version": FIRST_PROSPECT_MINI_AUDIT_DELIVERY_LOG_SCHEMA_VERSION}
        base.update(metadata or {})
        return FirstProspectMiniAuditDeliveryLogError(
            ok=False,
            schema_version=FIRST_PROSPECT_MINI_AUDIT_DELIVERY_LOG_SCHEMA_VERSION,
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
    "FIRST_PROSPECT_MINI_AUDIT_DELIVERY_LOG_SCHEMA_VERSION",
    "DELIVERY_CHECK_STATUSES",
    "DELIVERY_CHECK_SEVERITIES",
    "OPERATOR_REVIEW_STATUSES",
    "MANUAL_SEND_STATUSES",
    "PROSPECT_RESPONSE_STATUSES",
    "DELIVERY_NEXT_ACTIONS",
    "DELIVERY_NEXT_ACTION_PRIORITIES",
    "MiniAuditDeliveryCheck",
    "MiniAuditDeliveryEvidence",
    "MiniAuditDeliveryNextAction",
    "FirstProspectMiniAuditDeliveryLogResult",
    "FirstProspectMiniAuditDeliveryLogError",
)
