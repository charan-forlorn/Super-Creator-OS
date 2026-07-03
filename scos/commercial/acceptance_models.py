"""SCOS Stage 4.5 commercial acceptance gate models.

Immutable, local-first certification models for the Stage 4.5 commercial
acceptance gate. They store only commercial-owned primitives and tuple-backed
structures, reuse the Stage 4.1 ``FrozenMap`` (never a duplicate
implementation), and serialize deterministically: tuples render as lists,
``FrozenMap`` renders as a plain dict, and callers apply
``json.dumps(..., sort_keys=True, indent=2)``. No real clock, no random, no
UUID is ever consulted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from .report_models import FrozenMap, _freeze_value
except ImportError:  # pragma: no cover - supports this repo's plain-script tests
    from report_models import FrozenMap, _freeze_value

COMMERCIAL_ACCEPTANCE_SCHEMA_VERSION = 1

ACCEPTANCE_CHECK_STATUSES = ("PASS", "FAIL", "BLOCKED", "SKIPPED")
ACCEPTANCE_CHECK_SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")


@dataclass(frozen=True)
class AcceptanceCheck:
    """One recorded certification check with its evidence and outcome."""

    check_name: str
    status: str
    severity: str
    evidence: str | None
    error_kind: str | None
    error_detail: str | None
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "check_name", str(self.check_name))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "severity", str(self.severity))
        if self.status not in ACCEPTANCE_CHECK_STATUSES:
            raise ValueError(f"invalid acceptance check status: {self.status!r}")
        if self.severity not in ACCEPTANCE_CHECK_SEVERITIES:
            raise ValueError(f"invalid acceptance check severity: {self.severity!r}")
        if self.evidence is not None:
            object.__setattr__(self, "evidence", str(self.evidence))
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
        evidence: str | None = None,
        error_kind: str | None = None,
        error_detail: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "AcceptanceCheck":
        return AcceptanceCheck(
            check_name=str(check_name),
            status=str(status),
            severity=str(severity),
            evidence=None if evidence is None else str(evidence),
            error_kind=None if error_kind is None else str(error_kind),
            error_detail=None if error_detail is None else str(error_detail),
            metadata=FrozenMap.from_mapping(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_name": self.check_name,
            "status": self.status,
            "severity": self.severity,
            "evidence": self.evidence,
            "error_kind": self.error_kind,
            "error_detail": self.error_detail,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class CommercialAcceptanceReport:
    """Deterministic certification report for one commercial run evaluation."""

    ok: bool
    schema_version: int
    certification_id: str
    run_id: str
    delivery_id: str
    created_at: str
    overall_status: str
    readiness_score: int
    checks: tuple[AcceptanceCheck, ...]
    evidence_paths: tuple[str, ...]
    blocking_reasons: tuple[str, ...]
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "certification_id", str(self.certification_id))
        object.__setattr__(self, "run_id", str(self.run_id))
        object.__setattr__(self, "delivery_id", str(self.delivery_id))
        object.__setattr__(self, "created_at", str(self.created_at))
        object.__setattr__(self, "overall_status", str(self.overall_status))
        object.__setattr__(self, "readiness_score", int(self.readiness_score))
        object.__setattr__(self, "checks", tuple(self.checks))
        object.__setattr__(self, "evidence_paths", tuple(str(p) for p in self.evidence_paths))
        object.__setattr__(self, "blocking_reasons", tuple(str(r) for r in self.blocking_reasons))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "certification_id": self.certification_id,
            "run_id": self.run_id,
            "delivery_id": self.delivery_id,
            "created_at": self.created_at,
            "overall_status": self.overall_status,
            "readiness_score": self.readiness_score,
            "checks": [chk.to_dict() for chk in self.checks],
            "evidence_paths": list(self.evidence_paths),
            "blocking_reasons": list(self.blocking_reasons),
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class CommercialAcceptanceError:
    """Deterministic failure object for an aborted acceptance evaluation."""

    ok: bool
    schema_version: int
    error_kind: str
    error_detail: str
    failed_check: str
    checks: tuple[AcceptanceCheck, ...]
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
        checks: tuple["AcceptanceCheck", ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> "CommercialAcceptanceError":
        base = {"schema_version": COMMERCIAL_ACCEPTANCE_SCHEMA_VERSION}
        base.update(metadata or {})
        return CommercialAcceptanceError(
            ok=False,
            schema_version=COMMERCIAL_ACCEPTANCE_SCHEMA_VERSION,
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
            "checks": [chk.to_dict() for chk in self.checks],
            "metadata": self.metadata.to_dict(),
        }


__all__ = (
    "COMMERCIAL_ACCEPTANCE_SCHEMA_VERSION",
    "ACCEPTANCE_CHECK_STATUSES",
    "ACCEPTANCE_CHECK_SEVERITIES",
    "AcceptanceCheck",
    "CommercialAcceptanceReport",
    "CommercialAcceptanceError",
)
