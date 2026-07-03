"""SCOS Stage 4.8 first paid customer dry-run models.

Immutable, local-first models for rehearsing one first paid customer delivery
from explicit local inputs. These models carry only commercial-owned primitive
data, reuse the Stage 4.1 ``FrozenMap`` implementation, and serialize
deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from .report_models import FrozenMap, _freeze_value
except ImportError:  # pragma: no cover - supports this repo's plain-script tests
    from report_models import FrozenMap, _freeze_value

FIRST_PAID_CUSTOMER_DRY_RUN_SCHEMA_VERSION = 1

DRY_RUN_STEP_STATUSES = ("success", "failure", "skipped")
DRY_RUN_BLOCKER_SEVERITIES = ("warning", "error", "critical")


def _thaw(value: Any) -> Any:
    if isinstance(value, FrozenMap):
        return value.to_dict()
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True)
class SyntheticCustomerCase:
    customer_id: str
    business_name: str
    business_type: str
    target_offer: str
    target_price: str
    intake_summary: str
    expected_deliverables: tuple[str, ...]
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "customer_id", str(self.customer_id))
        object.__setattr__(self, "business_name", str(self.business_name))
        object.__setattr__(self, "business_type", str(self.business_type))
        object.__setattr__(self, "target_offer", str(self.target_offer))
        object.__setattr__(self, "target_price", str(self.target_price))
        object.__setattr__(self, "intake_summary", str(self.intake_summary))
        object.__setattr__(self, "expected_deliverables", tuple(str(v) for v in self.expected_deliverables))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    @staticmethod
    def of(
        *,
        customer_id: str,
        business_name: str,
        business_type: str,
        target_offer: str,
        target_price: str,
        intake_summary: str,
        expected_deliverables: tuple[str, ...] | list[str],
        metadata: dict[str, Any] | None = None,
    ) -> "SyntheticCustomerCase":
        return SyntheticCustomerCase(
            customer_id=str(customer_id),
            business_name=str(business_name),
            business_type=str(business_type),
            target_offer=str(target_offer),
            target_price=str(target_price),
            intake_summary=str(intake_summary),
            expected_deliverables=tuple(str(v) for v in expected_deliverables),
            metadata=FrozenMap.from_mapping(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "customer_id": self.customer_id,
            "business_name": self.business_name,
            "business_type": self.business_type,
            "target_offer": self.target_offer,
            "target_price": self.target_price,
            "intake_summary": self.intake_summary,
            "expected_deliverables": list(self.expected_deliverables),
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class DryRunStep:
    step_name: str
    status: str
    artifact_path: str | None
    error_kind: str | None
    error_detail: str | None
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "step_name", str(self.step_name))
        object.__setattr__(self, "status", str(self.status))
        if self.status not in DRY_RUN_STEP_STATUSES:
            raise ValueError(f"invalid dry-run step status: {self.status!r}")
        if self.artifact_path is not None:
            object.__setattr__(self, "artifact_path", str(self.artifact_path))
        if self.error_kind is not None:
            object.__setattr__(self, "error_kind", str(self.error_kind))
        if self.error_detail is not None:
            object.__setattr__(self, "error_detail", str(self.error_detail))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    @staticmethod
    def of(
        step_name: str,
        status: str,
        *,
        artifact_path: str | None = None,
        error_kind: str | None = None,
        error_detail: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "DryRunStep":
        return DryRunStep(
            step_name=str(step_name),
            status=str(status),
            artifact_path=None if artifact_path is None else str(artifact_path),
            error_kind=None if error_kind is None else str(error_kind),
            error_detail=None if error_detail is None else str(error_detail),
            metadata=FrozenMap.from_mapping(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_name": self.step_name,
            "status": self.status,
            "artifact_path": self.artifact_path,
            "error_kind": self.error_kind,
            "error_detail": self.error_detail,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class DryRunBlocker:
    blocker_id: str
    category: str
    severity: str
    title: str
    detail: str
    recommended_action: str
    source_step: str
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "blocker_id", str(self.blocker_id))
        object.__setattr__(self, "category", str(self.category))
        object.__setattr__(self, "severity", str(self.severity))
        if self.severity not in DRY_RUN_BLOCKER_SEVERITIES:
            raise ValueError(f"invalid dry-run blocker severity: {self.severity!r}")
        object.__setattr__(self, "title", str(self.title))
        object.__setattr__(self, "detail", str(self.detail))
        object.__setattr__(self, "recommended_action", str(self.recommended_action))
        object.__setattr__(self, "source_step", str(self.source_step))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    @staticmethod
    def of(
        blocker_id: str,
        category: str,
        severity: str,
        title: str,
        detail: str,
        recommended_action: str,
        source_step: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> "DryRunBlocker":
        return DryRunBlocker(
            blocker_id=str(blocker_id),
            category=str(category),
            severity=str(severity),
            title=str(title),
            detail=str(detail),
            recommended_action=str(recommended_action),
            source_step=str(source_step),
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
            "source_step": self.source_step,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class FirstPaidCustomerDryRunResult:
    ok: bool
    schema_version: int
    passed: bool
    dry_run_id: str
    checked_at: str
    customer_case: SyntheticCustomerCase
    go_no_go: str
    readiness_level: str
    readiness_score: int
    readiness_max_score: int
    commercial_run_manifest_path: str | None
    acceptance_report_path: str | None
    operating_kit_path: str | None
    monetization_readiness_report_path: str | None
    dry_run_report_path: str | None
    steps: tuple[DryRunStep, ...]
    blockers: tuple[DryRunBlocker, ...]
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "passed", bool(self.passed))
        object.__setattr__(self, "dry_run_id", str(self.dry_run_id))
        object.__setattr__(self, "checked_at", str(self.checked_at))
        object.__setattr__(self, "go_no_go", str(self.go_no_go))
        object.__setattr__(self, "readiness_level", str(self.readiness_level))
        object.__setattr__(self, "readiness_score", int(self.readiness_score))
        object.__setattr__(self, "readiness_max_score", int(self.readiness_max_score))
        for field_name in (
            "commercial_run_manifest_path",
            "acceptance_report_path",
            "operating_kit_path",
            "monetization_readiness_report_path",
            "dry_run_report_path",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, str(value))
        object.__setattr__(self, "steps", tuple(self.steps))
        object.__setattr__(self, "blockers", tuple(self.blockers))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "passed": self.passed,
            "dry_run_id": self.dry_run_id,
            "checked_at": self.checked_at,
            "customer_case": self.customer_case.to_dict(),
            "go_no_go": self.go_no_go,
            "readiness_level": self.readiness_level,
            "readiness_score": self.readiness_score,
            "readiness_max_score": self.readiness_max_score,
            "commercial_run_manifest_path": self.commercial_run_manifest_path,
            "acceptance_report_path": self.acceptance_report_path,
            "operating_kit_path": self.operating_kit_path,
            "monetization_readiness_report_path": self.monetization_readiness_report_path,
            "dry_run_report_path": self.dry_run_report_path,
            "steps": [step.to_dict() for step in self.steps],
            "blockers": [blocker.to_dict() for blocker in self.blockers],
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class FirstPaidCustomerDryRunError:
    ok: bool
    schema_version: int
    error_kind: str
    error_detail: str
    failed_step: str
    steps: tuple[DryRunStep, ...]
    blockers: tuple[DryRunBlocker, ...]
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", False)
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "error_kind", str(self.error_kind))
        object.__setattr__(self, "error_detail", str(self.error_detail))
        object.__setattr__(self, "failed_step", str(self.failed_step))
        object.__setattr__(self, "steps", tuple(self.steps))
        object.__setattr__(self, "blockers", tuple(self.blockers))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    @staticmethod
    def of(
        error_kind: str,
        error_detail: str,
        failed_step: str,
        steps: tuple[DryRunStep, ...] = (),
        blockers: tuple[DryRunBlocker, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> "FirstPaidCustomerDryRunError":
        base = {"schema_version": FIRST_PAID_CUSTOMER_DRY_RUN_SCHEMA_VERSION}
        base.update(metadata or {})
        return FirstPaidCustomerDryRunError(
            ok=False,
            schema_version=FIRST_PAID_CUSTOMER_DRY_RUN_SCHEMA_VERSION,
            error_kind=str(error_kind),
            error_detail=str(error_detail),
            failed_step=str(failed_step),
            steps=tuple(steps),
            blockers=tuple(blockers),
            metadata=FrozenMap.from_mapping(base),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "error_kind": self.error_kind,
            "error_detail": self.error_detail,
            "failed_step": self.failed_step,
            "steps": [step.to_dict() for step in self.steps],
            "blockers": [blocker.to_dict() for blocker in self.blockers],
            "metadata": self.metadata.to_dict(),
        }


__all__ = (
    "FIRST_PAID_CUSTOMER_DRY_RUN_SCHEMA_VERSION",
    "SyntheticCustomerCase",
    "DryRunStep",
    "DryRunBlocker",
    "FirstPaidCustomerDryRunResult",
    "FirstPaidCustomerDryRunError",
)
