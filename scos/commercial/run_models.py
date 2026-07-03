"""SCOS Stage 4.4 local commercial run orchestrator models.

Immutable, local-first result/error/step models for the Stage 4.4 commercial run
orchestrator. They store only commercial-owned primitives and tuple-backed
structures, reuse the Stage 4.1 ``FrozenMap`` (never a duplicate implementation),
and serialize deterministically: tuples render as lists, ``FrozenMap`` renders as
a plain dict, and callers apply ``json.dumps(..., sort_keys=True, indent=2)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from .report_models import FrozenMap, _freeze_value
except ImportError:  # pragma: no cover - supports this repo's plain-script tests
    from report_models import FrozenMap, _freeze_value

COMMERCIAL_RUN_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class CommercialRunStep:
    """One recorded step of the commercial run flow (success or failure)."""

    step_name: str
    status: str
    output_path: str | None
    error_kind: str | None
    error_detail: str | None
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "step_name", str(self.step_name))
        object.__setattr__(self, "status", str(self.status))
        if self.output_path is not None:
            object.__setattr__(self, "output_path", str(self.output_path))
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
        output_path: str | None = None,
        error_kind: str | None = None,
        error_detail: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "CommercialRunStep":
        return CommercialRunStep(
            step_name=str(step_name),
            status=str(status),
            output_path=None if output_path is None else str(output_path),
            error_kind=None if error_kind is None else str(error_kind),
            error_detail=None if error_detail is None else str(error_detail),
            metadata=FrozenMap.from_mapping(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_name": self.step_name,
            "status": self.status,
            "output_path": self.output_path,
            "error_kind": self.error_kind,
            "error_detail": self.error_detail,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class CommercialRunResult:
    """Deterministic success object for a completed commercial run."""

    ok: bool
    schema_version: int
    run_id: str
    report_id: str
    delivery_id: str
    output_dir: str
    report_path: str
    package_path: str
    manifest_path: str
    created_at: str
    steps: tuple[CommercialRunStep, ...]
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", True)
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "run_id", str(self.run_id))
        object.__setattr__(self, "report_id", str(self.report_id))
        object.__setattr__(self, "delivery_id", str(self.delivery_id))
        object.__setattr__(self, "output_dir", str(self.output_dir))
        object.__setattr__(self, "report_path", str(self.report_path))
        object.__setattr__(self, "package_path", str(self.package_path))
        object.__setattr__(self, "manifest_path", str(self.manifest_path))
        object.__setattr__(self, "created_at", str(self.created_at))
        object.__setattr__(self, "steps", tuple(self.steps))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "report_id": self.report_id,
            "delivery_id": self.delivery_id,
            "output_dir": self.output_dir,
            "report_path": self.report_path,
            "package_path": self.package_path,
            "manifest_path": self.manifest_path,
            "created_at": self.created_at,
            "steps": [step.to_dict() for step in self.steps],
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class CommercialRunError:
    """Deterministic failure object for an aborted commercial run."""

    ok: bool
    schema_version: int
    error_kind: str
    error_detail: str
    failed_step: str
    steps: tuple[CommercialRunStep, ...]
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", False)
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "error_kind", str(self.error_kind))
        object.__setattr__(self, "error_detail", str(self.error_detail))
        object.__setattr__(self, "failed_step", str(self.failed_step))
        object.__setattr__(self, "steps", tuple(self.steps))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    @staticmethod
    def of(
        error_kind: str,
        error_detail: str,
        failed_step: str,
        steps: tuple["CommercialRunStep", ...],
        metadata: dict[str, Any] | None = None,
    ) -> "CommercialRunError":
        base = {"schema_version": COMMERCIAL_RUN_SCHEMA_VERSION}
        base.update(metadata or {})
        return CommercialRunError(
            ok=False,
            schema_version=COMMERCIAL_RUN_SCHEMA_VERSION,
            error_kind=str(error_kind),
            error_detail=str(error_detail),
            failed_step=str(failed_step),
            steps=tuple(steps),
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
            "metadata": self.metadata.to_dict(),
        }


__all__ = (
    "COMMERCIAL_RUN_SCHEMA_VERSION",
    "CommercialRunStep",
    "CommercialRunResult",
    "CommercialRunError",
)
