"""SCOS Stage 4.10 operator practice lab models.

Immutable, local-first models for deterministic operator practice runs. These
models reuse the Stage 4.1 ``FrozenMap`` implementation and serialize with
explicit key order.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from .report_models import FrozenMap, _freeze_value
except ImportError:  # pragma: no cover - supports this repo's plain-script tests
    from report_models import FrozenMap, _freeze_value

OPERATOR_PRACTICE_SCHEMA_VERSION = 1

PRACTICE_STEP_STATUSES = ("success", "failure", "skipped")
PRACTICE_OBSERVATION_SEVERITIES = ("info", "warning", "error")
PRACTICE_STATUSES = ("PASS", "CONDITIONAL_PASS", "FAIL")


@dataclass(frozen=True)
class PracticeScenario:
    scenario_id: str
    title: str
    business_type: str
    target_offer: str
    target_price: str
    operator_goal: str
    expected_outcome: str
    customer_case_metadata: FrozenMap
    required_observations: tuple[str, ...]
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "scenario_id", str(self.scenario_id))
        object.__setattr__(self, "title", str(self.title))
        object.__setattr__(self, "business_type", str(self.business_type))
        object.__setattr__(self, "target_offer", str(self.target_offer))
        object.__setattr__(self, "target_price", str(self.target_price))
        object.__setattr__(self, "operator_goal", str(self.operator_goal))
        object.__setattr__(self, "expected_outcome", str(self.expected_outcome))
        object.__setattr__(self, "customer_case_metadata", _freeze_value(self.customer_case_metadata))
        object.__setattr__(self, "required_observations", tuple(str(v) for v in self.required_observations))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    @staticmethod
    def of(
        *,
        scenario_id: str,
        title: str,
        business_type: str,
        target_offer: str,
        target_price: str,
        operator_goal: str,
        expected_outcome: str,
        customer_case_metadata: dict[str, Any] | None = None,
        required_observations: tuple[str, ...] | list[str] = (),
        metadata: dict[str, Any] | None = None,
    ) -> "PracticeScenario":
        return PracticeScenario(
            scenario_id=str(scenario_id),
            title=str(title),
            business_type=str(business_type),
            target_offer=str(target_offer),
            target_price=str(target_price),
            operator_goal=str(operator_goal),
            expected_outcome=str(expected_outcome),
            customer_case_metadata=FrozenMap.from_mapping(customer_case_metadata or {}),
            required_observations=tuple(str(v) for v in required_observations),
            metadata=FrozenMap.from_mapping(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "title": self.title,
            "business_type": self.business_type,
            "target_offer": self.target_offer,
            "target_price": self.target_price,
            "operator_goal": self.operator_goal,
            "expected_outcome": self.expected_outcome,
            "customer_case_metadata": self.customer_case_metadata.to_dict(),
            "required_observations": list(self.required_observations),
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class PracticeStep:
    step_name: str
    status: str
    artifact_path: str | None
    error_kind: str | None
    error_detail: str | None
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "step_name", str(self.step_name))
        object.__setattr__(self, "status", str(self.status))
        if self.status not in PRACTICE_STEP_STATUSES:
            raise ValueError(f"invalid practice step status: {self.status!r}")
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
    ) -> "PracticeStep":
        return PracticeStep(
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
class PracticeObservation:
    observation_id: str
    category: str
    severity: str
    title: str
    detail: str
    recommended_action: str
    source_artifact: str | None
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "observation_id", str(self.observation_id))
        object.__setattr__(self, "category", str(self.category))
        object.__setattr__(self, "severity", str(self.severity))
        if self.severity not in PRACTICE_OBSERVATION_SEVERITIES:
            raise ValueError(f"invalid practice observation severity: {self.severity!r}")
        object.__setattr__(self, "title", str(self.title))
        object.__setattr__(self, "detail", str(self.detail))
        object.__setattr__(self, "recommended_action", str(self.recommended_action))
        if self.source_artifact is not None:
            object.__setattr__(self, "source_artifact", str(self.source_artifact))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    @staticmethod
    def of(
        observation_id: str,
        category: str,
        severity: str,
        title: str,
        detail: str,
        recommended_action: str,
        *,
        source_artifact: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "PracticeObservation":
        return PracticeObservation(
            observation_id=str(observation_id),
            category=str(category),
            severity=str(severity),
            title=str(title),
            detail=str(detail),
            recommended_action=str(recommended_action),
            source_artifact=None if source_artifact is None else str(source_artifact),
            metadata=FrozenMap.from_mapping(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "category": self.category,
            "severity": self.severity,
            "title": self.title,
            "detail": self.detail,
            "recommended_action": self.recommended_action,
            "source_artifact": self.source_artifact,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class OperatorPracticeResult:
    ok: bool
    schema_version: int
    practice_id: str
    scenario_id: str
    checked_at: str
    scenario: PracticeScenario
    practice_status: str
    dry_run_report_path: str | None
    launch_certification_report_path: str | None
    practice_summary_path: str | None
    practice_walkthrough_path: str | None
    customer_facing_files_path: str | None
    internal_evidence_files_path: str | None
    operator_observations_path: str | None
    steps: tuple[PracticeStep, ...]
    observations: tuple[PracticeObservation, ...]
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "practice_id", str(self.practice_id))
        object.__setattr__(self, "scenario_id", str(self.scenario_id))
        object.__setattr__(self, "checked_at", str(self.checked_at))
        object.__setattr__(self, "practice_status", str(self.practice_status))
        if self.practice_status not in PRACTICE_STATUSES:
            raise ValueError(f"invalid practice status: {self.practice_status!r}")
        for field_name in (
            "dry_run_report_path",
            "launch_certification_report_path",
            "practice_summary_path",
            "practice_walkthrough_path",
            "customer_facing_files_path",
            "internal_evidence_files_path",
            "operator_observations_path",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, str(value))
        object.__setattr__(self, "steps", tuple(self.steps))
        object.__setattr__(self, "observations", tuple(self.observations))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "practice_id": self.practice_id,
            "scenario_id": self.scenario_id,
            "checked_at": self.checked_at,
            "scenario": self.scenario.to_dict(),
            "practice_status": self.practice_status,
            "dry_run_report_path": self.dry_run_report_path,
            "launch_certification_report_path": self.launch_certification_report_path,
            "practice_summary_path": self.practice_summary_path,
            "practice_walkthrough_path": self.practice_walkthrough_path,
            "customer_facing_files_path": self.customer_facing_files_path,
            "internal_evidence_files_path": self.internal_evidence_files_path,
            "operator_observations_path": self.operator_observations_path,
            "steps": [step.to_dict() for step in self.steps],
            "observations": [observation.to_dict() for observation in self.observations],
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class OperatorPracticeError:
    ok: bool
    schema_version: int
    error_kind: str
    error_detail: str
    failed_step: str
    steps: tuple[PracticeStep, ...]
    observations: tuple[PracticeObservation, ...]
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", False)
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "error_kind", str(self.error_kind))
        object.__setattr__(self, "error_detail", str(self.error_detail))
        object.__setattr__(self, "failed_step", str(self.failed_step))
        object.__setattr__(self, "steps", tuple(self.steps))
        object.__setattr__(self, "observations", tuple(self.observations))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    @staticmethod
    def of(
        error_kind: str,
        error_detail: str,
        failed_step: str,
        steps: tuple[PracticeStep, ...] = (),
        observations: tuple[PracticeObservation, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> "OperatorPracticeError":
        base = {"schema_version": OPERATOR_PRACTICE_SCHEMA_VERSION}
        base.update(metadata or {})
        return OperatorPracticeError(
            ok=False,
            schema_version=OPERATOR_PRACTICE_SCHEMA_VERSION,
            error_kind=str(error_kind),
            error_detail=str(error_detail),
            failed_step=str(failed_step),
            steps=tuple(steps),
            observations=tuple(observations),
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
            "observations": [observation.to_dict() for observation in self.observations],
            "metadata": self.metadata.to_dict(),
        }


__all__ = (
    "OPERATOR_PRACTICE_SCHEMA_VERSION",
    "PracticeScenario",
    "PracticeStep",
    "PracticeObservation",
    "OperatorPracticeResult",
    "OperatorPracticeError",
)
