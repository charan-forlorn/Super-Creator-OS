"""SCOS Stage 4.12 first prospect execution log models.

Immutable, local-first models that record a single manual first-prospect
outreach attempt as deterministic evidence. These models reuse the Stage 4.1
``FrozenMap`` implementation and serialize with explicit key order.

This layer is manual evidence logging only. It does not send messages, gather
leads, enrich records, or call external services.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from .report_models import FrozenMap, _freeze_value
except ImportError:  # pragma: no cover - supports this repo's plain-script tests
    from report_models import FrozenMap, _freeze_value

FIRST_PROSPECT_EXECUTION_LOG_SCHEMA_VERSION = 1

PROSPECT_ACTION_TYPES = (
    "manual_dm",
    "manual_walk_in",
    "manual_call_note",
    "manual_follow_up",
    "manual_observation",
    "manual_mini_audit_offer",
)

PROSPECT_RESPONSE_STATUSES = (
    "not_contacted",
    "contacted",
    "interested",
    "not_interested",
    "no_response",
    "follow_up_needed",
    "mini_audit_requested",
    "blocked",
)

PROSPECT_CHECK_STATUSES = ("success", "failure", "skipped")
PROSPECT_CHECK_SEVERITIES = ("info", "warning", "error")


@dataclass(frozen=True)
class ProspectProfile:
    prospect_id: str
    display_name: str
    business_type: str
    channel: str
    source: str
    manual_context: str
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "prospect_id", str(self.prospect_id))
        object.__setattr__(self, "display_name", str(self.display_name))
        object.__setattr__(self, "business_type", str(self.business_type))
        object.__setattr__(self, "channel", str(self.channel))
        object.__setattr__(self, "source", str(self.source))
        object.__setattr__(self, "manual_context", str(self.manual_context))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    @staticmethod
    def of(
        *,
        prospect_id: str,
        display_name: str,
        business_type: str,
        channel: str,
        source: str,
        manual_context: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> "ProspectProfile":
        return ProspectProfile(
            prospect_id=str(prospect_id),
            display_name=str(display_name),
            business_type=str(business_type),
            channel=str(channel),
            source=str(source),
            manual_context=str(manual_context),
            metadata=FrozenMap.from_mapping(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "prospect_id": self.prospect_id,
            "display_name": self.display_name,
            "business_type": self.business_type,
            "channel": self.channel,
            "source": self.source,
            "manual_context": self.manual_context,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class ProspectOutreachAction:
    action_id: str
    action_type: str
    outreach_asset_id: str | None
    offered_mini_audit: bool
    message_summary: str
    performed_at: str
    performed_by: str
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "action_id", str(self.action_id))
        # action_type is caller-supplied; membership is enforced by the record
        # function (validate_outreach_action) so it can return a typed error.
        object.__setattr__(self, "action_type", str(self.action_type))
        if self.outreach_asset_id is not None:
            object.__setattr__(self, "outreach_asset_id", str(self.outreach_asset_id))
        object.__setattr__(self, "offered_mini_audit", bool(self.offered_mini_audit))
        object.__setattr__(self, "message_summary", str(self.message_summary))
        object.__setattr__(self, "performed_at", str(self.performed_at))
        object.__setattr__(self, "performed_by", str(self.performed_by))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    @staticmethod
    def of(
        *,
        action_id: str,
        action_type: str,
        message_summary: str,
        performed_at: str,
        performed_by: str,
        outreach_asset_id: str | None = None,
        offered_mini_audit: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> "ProspectOutreachAction":
        return ProspectOutreachAction(
            action_id=str(action_id),
            action_type=str(action_type),
            outreach_asset_id=None if outreach_asset_id is None else str(outreach_asset_id),
            offered_mini_audit=bool(offered_mini_audit),
            message_summary=str(message_summary),
            performed_at=str(performed_at),
            performed_by=str(performed_by),
            metadata=FrozenMap.from_mapping(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "outreach_asset_id": self.outreach_asset_id,
            "offered_mini_audit": self.offered_mini_audit,
            "message_summary": self.message_summary,
            "performed_at": self.performed_at,
            "performed_by": self.performed_by,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class ProspectResponseStatus:
    status: str
    response_summary: str
    next_action: str
    follow_up_due: str | None
    blocker_summary: str | None
    metadata: FrozenMap

    def __post_init__(self) -> None:
        # status is caller-supplied; membership is enforced by the record function
        # (validate_response_status) so it can return a typed error.
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "response_summary", str(self.response_summary))
        object.__setattr__(self, "next_action", str(self.next_action))
        if self.follow_up_due is not None:
            object.__setattr__(self, "follow_up_due", str(self.follow_up_due))
        if self.blocker_summary is not None:
            object.__setattr__(self, "blocker_summary", str(self.blocker_summary))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    @staticmethod
    def of(
        *,
        status: str,
        response_summary: str = "",
        next_action: str = "",
        follow_up_due: str | None = None,
        blocker_summary: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "ProspectResponseStatus":
        return ProspectResponseStatus(
            status=str(status),
            response_summary=str(response_summary),
            next_action=str(next_action),
            follow_up_due=None if follow_up_due is None else str(follow_up_due),
            blocker_summary=None if blocker_summary is None else str(blocker_summary),
            metadata=FrozenMap.from_mapping(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "response_summary": self.response_summary,
            "next_action": self.next_action,
            "follow_up_due": self.follow_up_due,
            "blocker_summary": self.blocker_summary,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class ProspectExecutionCheck:
    check_name: str
    status: str
    severity: str
    error_kind: str | None
    error_detail: str | None
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "check_name", str(self.check_name))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "severity", str(self.severity))
        if self.status not in PROSPECT_CHECK_STATUSES:
            raise ValueError(f"invalid prospect check status: {self.status!r}")
        if self.severity not in PROSPECT_CHECK_SEVERITIES:
            raise ValueError(f"invalid prospect check severity: {self.severity!r}")
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
        error_kind: str | None = None,
        error_detail: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "ProspectExecutionCheck":
        return ProspectExecutionCheck(
            check_name=str(check_name),
            status=str(status),
            severity=str(severity),
            error_kind=None if error_kind is None else str(error_kind),
            error_detail=None if error_detail is None else str(error_detail),
            metadata=FrozenMap.from_mapping(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_name": self.check_name,
            "status": self.status,
            "severity": self.severity,
            "error_kind": self.error_kind,
            "error_detail": self.error_detail,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class FirstProspectExecutionLogResult:
    ok: bool
    schema_version: int
    logged: bool
    execution_log_id: str
    checked_at: str
    prospect: ProspectProfile
    outreach_action: ProspectOutreachAction
    response_status: ProspectResponseStatus
    outreach_launch_kit_path: str | None
    execution_log_path: str | None
    checks: tuple[ProspectExecutionCheck, ...]
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "logged", bool(self.logged))
        object.__setattr__(self, "execution_log_id", str(self.execution_log_id))
        object.__setattr__(self, "checked_at", str(self.checked_at))
        if self.outreach_launch_kit_path is not None:
            object.__setattr__(self, "outreach_launch_kit_path", str(self.outreach_launch_kit_path))
        if self.execution_log_path is not None:
            object.__setattr__(self, "execution_log_path", str(self.execution_log_path))
        object.__setattr__(self, "checks", tuple(self.checks))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "logged": self.logged,
            "execution_log_id": self.execution_log_id,
            "checked_at": self.checked_at,
            "prospect": self.prospect.to_dict(),
            "outreach_action": self.outreach_action.to_dict(),
            "response_status": self.response_status.to_dict(),
            "outreach_launch_kit_path": self.outreach_launch_kit_path,
            "execution_log_path": self.execution_log_path,
            "checks": [check.to_dict() for check in self.checks],
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class FirstProspectExecutionLogError:
    ok: bool
    schema_version: int
    error_kind: str
    error_detail: str
    failed_check: str
    checks: tuple[ProspectExecutionCheck, ...]
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", False)
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "error_kind", str(self.error_kind))
        object.__setattr__(self, "error_detail", str(self.error_detail))
        object.__setattr__(self, "failed_check", str(self.failed_check))
        object.__setattr__(self, "checks", tuple(self.checks))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    @staticmethod
    def of(
        error_kind: str,
        error_detail: str,
        failed_check: str,
        checks: tuple[ProspectExecutionCheck, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> "FirstProspectExecutionLogError":
        base = {"schema_version": FIRST_PROSPECT_EXECUTION_LOG_SCHEMA_VERSION}
        base.update(metadata or {})
        return FirstProspectExecutionLogError(
            ok=False,
            schema_version=FIRST_PROSPECT_EXECUTION_LOG_SCHEMA_VERSION,
            error_kind=str(error_kind),
            error_detail=str(error_detail),
            failed_check=str(failed_check),
            checks=tuple(checks),
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
            "metadata": self.metadata.to_dict(),
        }


__all__ = (
    "FIRST_PROSPECT_EXECUTION_LOG_SCHEMA_VERSION",
    "PROSPECT_ACTION_TYPES",
    "PROSPECT_RESPONSE_STATUSES",
    "PROSPECT_CHECK_STATUSES",
    "PROSPECT_CHECK_SEVERITIES",
    "ProspectProfile",
    "ProspectOutreachAction",
    "ProspectResponseStatus",
    "ProspectExecutionCheck",
    "FirstProspectExecutionLogResult",
    "FirstProspectExecutionLogError",
)
