"""SCOS Stage 4.1 commercial report models.

The commercial contract is an immutable, local-first projection over Stage 3.9
KnowledgeService view models. It stores only commercial-owned primitives and
tuple-backed structures, never lower-layer result objects or mutable payloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

COMMERCIAL_REPORT_SCHEMA_VERSION = 1


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


@dataclass(frozen=True)
class ReportEvidence:
    evidence_id: str
    evidence_type: str
    source: str
    value: Any

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", str(self.evidence_id))
        object.__setattr__(self, "evidence_type", str(self.evidence_type))
        object.__setattr__(self, "source", str(self.source))
        object.__setattr__(self, "value", _freeze_value(self.value))

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "evidence_type": self.evidence_type,
            "source": self.source,
            "value": _thaw_value(self.value),
        }


@dataclass(frozen=True)
class ReportRisk:
    risk_id: str
    risk_type: str
    source: str
    detail: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "risk_id", str(self.risk_id))
        object.__setattr__(self, "risk_type", str(self.risk_type))
        object.__setattr__(self, "source", str(self.source))
        object.__setattr__(self, "detail", str(self.detail))

    def to_dict(self) -> dict[str, str]:
        return {
            "risk_id": self.risk_id,
            "risk_type": self.risk_type,
            "source": self.source,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class CommercialReport:
    report_id: str
    schema_version: int
    report_type: str
    created_at: str
    source_run_id: str
    style_id: str | None
    qa_status: str
    summary: str
    evidence: tuple[ReportEvidence, ...]
    recommendations: tuple[Any, ...]
    risks: tuple[ReportRisk, ...]
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "report_id", str(self.report_id))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "report_type", str(self.report_type))
        object.__setattr__(self, "created_at", str(self.created_at))
        object.__setattr__(self, "source_run_id", str(self.source_run_id))
        if self.style_id is not None:
            object.__setattr__(self, "style_id", str(self.style_id))
        object.__setattr__(self, "qa_status", str(self.qa_status))
        object.__setattr__(self, "summary", str(self.summary))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "recommendations", tuple(_freeze_value(item) for item in self.recommendations))
        object.__setattr__(self, "risks", tuple(self.risks))
        object.__setattr__(self, "metadata", _freeze_value(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "schema_version": self.schema_version,
            "report_type": self.report_type,
            "created_at": self.created_at,
            "source_run_id": self.source_run_id,
            "style_id": self.style_id,
            "qa_status": self.qa_status,
            "summary": self.summary,
            "evidence": [item.to_dict() for item in self.evidence],
            "recommendations": [_thaw_value(item) for item in self.recommendations],
            "risks": [item.to_dict() for item in self.risks],
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class CommercialReportError:
    error: str
    target: str
    reason: str
    metadata: FrozenMap

    @staticmethod
    def of(error: str, target: str, reason: str, metadata: dict[str, Any] | None = None) -> "CommercialReportError":
        return CommercialReportError(
            error=str(error),
            target=str(target),
            reason=str(reason),
            metadata=FrozenMap.from_mapping(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.error,
            "target": self.target,
            "reason": self.reason,
            "metadata": self.metadata.to_dict(),
        }
