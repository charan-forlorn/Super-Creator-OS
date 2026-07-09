"""Stage 7.7 immutable adapter activation preflight models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ADAPTER_ACTIVATION_PREFLIGHT_SCHEMA_VERSION = 1

PREFLIGHT_TARGET_ADAPTERS = ("chatgpt", "claude_code", "codex", "hermes", "all")
PREFLIGHT_ACTIVATION_MODES = (
    "preflight_only",
    "do_not_activate",
    "simulator_only",
    "manual_handoff_only",
)
PREFLIGHT_REJECTED_ACTIVATION_MODES = (
    "real_dispatch",
    "live_adapter",
    "api_dispatch",
    "cloud_dispatch",
    "browser_automation",
    "gui_automation",
    "clipboard_automation",
)
PREFLIGHT_STATUSES = ("pass", "warning", "blocker", "missing", "not_required")
PREFLIGHT_GO_NO_GO = ("GO", "NO_GO", "BLOCKED")


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
class AdapterActivationPreflightCheck:
    check_id: str
    check_name: str
    status: str
    summary: str
    required: bool
    source_stage: str
    references: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "check_id", str(self.check_id))
        object.__setattr__(self, "check_name", str(self.check_name))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "summary", str(self.summary))
        object.__setattr__(self, "required", bool(self.required))
        object.__setattr__(self, "source_stage", str(self.source_stage))
        object.__setattr__(self, "references", _strings(self.references))
        object.__setattr__(self, "metadata", _pairs(self.metadata))
        _require_allowed("status", self.status, PREFLIGHT_STATUSES)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "check_name": self.check_name,
            "status": self.status,
            "summary": self.summary,
            "required": self.required,
            "source_stage": self.source_stage,
            "references": list(self.references),
            "metadata": [[key, value] for key, value in self.metadata],
        }


@dataclass(frozen=True)
class AdapterActivationArtifact:
    artifact_id: str
    artifact_type: str
    path: str
    required: bool
    exists: bool
    readable: bool
    digest: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_id", str(self.artifact_id))
        object.__setattr__(self, "artifact_type", str(self.artifact_type))
        object.__setattr__(self, "path", str(self.path))
        object.__setattr__(self, "required", bool(self.required))
        object.__setattr__(self, "exists", bool(self.exists))
        object.__setattr__(self, "readable", bool(self.readable))
        object.__setattr__(self, "digest", None if self.digest is None else str(self.digest))

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "path": self.path,
            "required": self.required,
            "exists": self.exists,
            "readable": self.readable,
            "digest": self.digest,
        }


@dataclass(frozen=True)
class AdapterActivationPreflightResult:
    gate_id: str
    gate_name: str
    checked_at: str
    target_adapter: str | None
    requested_activation_mode: str
    go_no_go: str
    readiness_score: int
    accepted: bool
    can_activate_now: bool
    activation_allowed_later: bool
    dispatch_blocked: bool
    approval_evidence_status: str
    audit_evidence_status: str
    secret_handling_status: str
    simulator_fallback_status: str
    manual_fallback_status: str
    rollback_status: str
    security_review_status: str
    transport_boundary_status: str
    adapter_contract_status: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    checks: tuple[AdapterActivationPreflightCheck, ...]
    inspected_artifacts: tuple[AdapterActivationArtifact, ...]
    forbidden_behavior_findings: tuple[str, ...]
    next_manual_actions: tuple[str, ...]
    report_path: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "gate_id", str(self.gate_id))
        object.__setattr__(self, "gate_name", str(self.gate_name))
        object.__setattr__(self, "checked_at", str(self.checked_at))
        object.__setattr__(
            self,
            "target_adapter",
            None if self.target_adapter is None else str(self.target_adapter),
        )
        object.__setattr__(self, "requested_activation_mode", str(self.requested_activation_mode))
        object.__setattr__(self, "go_no_go", str(self.go_no_go))
        object.__setattr__(self, "readiness_score", int(self.readiness_score))
        object.__setattr__(self, "accepted", bool(self.accepted))
        object.__setattr__(self, "can_activate_now", bool(self.can_activate_now))
        object.__setattr__(self, "activation_allowed_later", bool(self.activation_allowed_later))
        object.__setattr__(self, "dispatch_blocked", bool(self.dispatch_blocked))
        for field_name in (
            "approval_evidence_status",
            "audit_evidence_status",
            "secret_handling_status",
            "simulator_fallback_status",
            "manual_fallback_status",
            "rollback_status",
            "security_review_status",
            "transport_boundary_status",
            "adapter_contract_status",
        ):
            object.__setattr__(self, field_name, str(getattr(self, field_name)))
            _require_allowed(field_name, getattr(self, field_name), PREFLIGHT_STATUSES)
        object.__setattr__(self, "blockers", _strings(self.blockers))
        object.__setattr__(self, "warnings", _strings(self.warnings))
        object.__setattr__(
            self,
            "checks",
            tuple(sorted(self.checks, key=lambda item: item.check_id)),
        )
        object.__setattr__(
            self,
            "inspected_artifacts",
            tuple(sorted(self.inspected_artifacts, key=lambda item: item.artifact_id)),
        )
        object.__setattr__(
            self,
            "forbidden_behavior_findings",
            _strings(self.forbidden_behavior_findings),
        )
        object.__setattr__(self, "next_manual_actions", _strings(self.next_manual_actions))
        object.__setattr__(self, "report_path", None if self.report_path is None else str(self.report_path))
        _require_allowed("go_no_go", self.go_no_go, PREFLIGHT_GO_NO_GO)
        _require_allowed("requested_activation_mode", self.requested_activation_mode, PREFLIGHT_ACTIVATION_MODES)
        if self.target_adapter is not None:
            _require_allowed("target_adapter", self.target_adapter, PREFLIGHT_TARGET_ADAPTERS)

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "gate_name": self.gate_name,
            "checked_at": self.checked_at,
            "target_adapter": self.target_adapter,
            "requested_activation_mode": self.requested_activation_mode,
            "go_no_go": self.go_no_go,
            "readiness_score": self.readiness_score,
            "accepted": self.accepted,
            "can_activate_now": self.can_activate_now,
            "activation_allowed_later": self.activation_allowed_later,
            "dispatch_blocked": self.dispatch_blocked,
            "approval_evidence_status": self.approval_evidence_status,
            "audit_evidence_status": self.audit_evidence_status,
            "secret_handling_status": self.secret_handling_status,
            "simulator_fallback_status": self.simulator_fallback_status,
            "manual_fallback_status": self.manual_fallback_status,
            "rollback_status": self.rollback_status,
            "security_review_status": self.security_review_status,
            "transport_boundary_status": self.transport_boundary_status,
            "adapter_contract_status": self.adapter_contract_status,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "checks": [check.to_dict() for check in self.checks],
            "inspected_artifacts": [artifact.to_dict() for artifact in self.inspected_artifacts],
            "forbidden_behavior_findings": list(self.forbidden_behavior_findings),
            "next_manual_actions": list(self.next_manual_actions),
            "report_path": self.report_path,
        }


@dataclass(frozen=True)
class AdapterActivationPreflightError:
    error_code: str
    message: str
    checked_at: str
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "error_code", str(self.error_code))
        object.__setattr__(self, "message", str(self.message))
        object.__setattr__(self, "checked_at", str(self.checked_at))
        object.__setattr__(self, "blockers", _strings(self.blockers))

    @staticmethod
    def of(
        error_code: str,
        message: str,
        *,
        checked_at: str,
        blockers: tuple[str, ...] = (),
    ) -> "AdapterActivationPreflightError":
        return AdapterActivationPreflightError(
            error_code=error_code,
            message=message,
            checked_at=checked_at,
            blockers=blockers or (message,),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "checked_at": self.checked_at,
            "blockers": list(self.blockers),
        }


__all__ = sorted(
    (
        "ADAPTER_ACTIVATION_PREFLIGHT_SCHEMA_VERSION",
        "PREFLIGHT_ACTIVATION_MODES",
        "PREFLIGHT_GO_NO_GO",
        "PREFLIGHT_REJECTED_ACTIVATION_MODES",
        "PREFLIGHT_STATUSES",
        "PREFLIGHT_TARGET_ADAPTERS",
        "AdapterActivationArtifact",
        "AdapterActivationPreflightCheck",
        "AdapterActivationPreflightError",
        "AdapterActivationPreflightResult",
    )
)
