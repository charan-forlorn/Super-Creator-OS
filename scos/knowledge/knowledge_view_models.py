"""SCOS Stage 3.9 — Knowledge Access Layer view models.

Pure, immutable read-model shapes returned by KnowledgeService (see
knowledge_service.py). Each public service method returns exactly one of these —
a composite view or a service-owned error model. Errors are deterministic result
objects, never raised.

A view *composes and projects* facts the certified Insight/Query layers already
return — it creates no knowledge, makes no decision, scores nothing. These models
are owned by the Access layer: they import no lower-layer type, so no Insight/
Query/Explain type leaks through the service boundary.

No business logic, no I/O, no scos.* imports, no json/open/IndexStore, no clock,
no randomness. All models are frozen dataclasses; `to_dict()` is a pure transform.
"""

from __future__ import annotations

from dataclasses import dataclass

KNOWLEDGE_VIEW_SCHEMA_VERSION = 1

SUBJECT_STYLE = "style"
SUBJECT_RUN = "run"
SUBJECT_PORTFOLIO = "portfolio"
SUBJECT_SYSTEM = "system"

# Reference Ordering Contract (Access-layer-owned copy — a stable cross-layer
# convention, intentionally not imported from a lower layer).
REF_CATEGORY_ORDER = ("run", "style", "version", "audit", "session")

CONFIDENCE_COMPLETE = "complete"
CONFIDENCE_PARTIAL = "partial"
CONFIDENCE_NONE = "none"


def _freeze_value(value):
    if isinstance(value, FrozenPayload):
        return value
    if isinstance(value, dict):
        return FrozenPayload.from_mapping(value)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(v) for v in value)
    return value


def _thaw_value(value):
    if isinstance(value, FrozenPayload):
        return value.to_dict()
    if isinstance(value, tuple):
        return [_thaw_value(v) for v in value]
    return value


@dataclass(frozen=True)
class FrozenPayload:
    """Immutable, access-owned copy of an arbitrary lower-layer mapping."""

    items: tuple

    @staticmethod
    def from_mapping(mapping) -> "FrozenPayload":
        return FrozenPayload(tuple((k, _freeze_value(mapping[k])) for k in sorted(mapping)))

    def to_dict(self) -> dict:
        return {k: _thaw_value(v) for k, v in self.items}


@dataclass(frozen=True)
class ViewConfidence:
    """Access-layer evidence-completeness over the sections a view composed.
    Same semantics as the lower layers (level + present/expected/missing); never
    a probability. Owned here so the view never exposes a lower-layer type."""

    level: str
    present: int
    expected: int
    missing: tuple

    def to_dict(self) -> dict:
        return {"level": self.level, "present": self.present,
                "expected": self.expected, "missing": list(self.missing)}

    @staticmethod
    def of(present_names, expected_names) -> "ViewConfidence":
        present_set = tuple(present_names)
        expected_set = tuple(expected_names)
        present = len(present_set)
        expected = len(expected_set)
        if expected > 0 and present == expected:
            level = CONFIDENCE_COMPLETE
        elif present == 0:
            level = CONFIDENCE_NONE
        else:
            level = CONFIDENCE_PARTIAL
        missing = tuple(n for n in expected_set if n not in present_set)
        return ViewConfidence(level=level, present=present, expected=expected, missing=missing)


@dataclass(frozen=True)
class ViewStatistics:
    """Access-layer-owned projection of InsightStatistics."""

    version_count: int
    rollback_count: int
    learning_count: int
    feedback_count: int
    quality_samples: int
    retention_samples: int
    style_count: int
    decision_counts: tuple

    def to_dict(self) -> dict:
        return {
            "version_count": self.version_count,
            "rollback_count": self.rollback_count,
            "learning_count": self.learning_count,
            "feedback_count": self.feedback_count,
            "quality_samples": self.quality_samples,
            "retention_samples": self.retention_samples,
            "style_count": self.style_count,
            "decision_counts": dict(self.decision_counts),
        }


@dataclass(frozen=True)
class ViewInsight:
    """Access-layer-owned projection of a lower-layer Insight."""

    schema_version: int
    insight_id: str
    insight_type: str
    title: str
    summary: str
    statistics: ViewStatistics
    references: tuple
    confidence: ViewConfidence
    generated_from: tuple

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "insight_id": self.insight_id,
            "insight_type": self.insight_type,
            "title": self.title,
            "summary": self.summary,
            "statistics": self.statistics.to_dict(),
            "references": list(self.references),
            "confidence": self.confidence.to_dict(),
            "generated_from": list(self.generated_from),
        }


@dataclass(frozen=True)
class ViewError:
    """Access-layer-owned section error detail."""

    error: str
    target: str
    detail: str

    def to_dict(self) -> dict:
        return {"error": self.error, "target": self.target, "detail": self.detail}


@dataclass(frozen=True)
class ViewSection:
    kind: str
    status: str
    insight: ViewInsight | None = None
    error: ViewError | None = None
    style_id: str | None = None

    def to_dict(self) -> dict:
        data = {
            "kind": self.kind,
            "status": self.status,
            "insight": self.insight.to_dict() if self.insight is not None else None,
        }
        if self.error is not None:
            data["error"] = self.error.to_dict()
        if self.style_id is not None:
            data["style_id"] = self.style_id
        return data


@dataclass(frozen=True)
class RunProvenance:
    run_id: str
    session_id: str | None
    asset_hash: str | None
    style_id: str | None
    current_version: int | None
    decision: str | None
    replay: FrozenPayload | None
    feedback: FrozenPayload | None
    audit: FrozenPayload | None
    style_version: FrozenPayload | None
    timeline_ref: FrozenPayload | None

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "session_id": self.session_id,
            "asset_hash": self.asset_hash,
            "style_id": self.style_id,
            "current_version": self.current_version,
            "decision": self.decision,
            "replay": self.replay.to_dict() if self.replay is not None else None,
            "feedback": self.feedback.to_dict() if self.feedback is not None else None,
            "audit": self.audit.to_dict() if self.audit is not None else None,
            "style_version": self.style_version.to_dict() if self.style_version is not None else None,
            "timeline_ref": self.timeline_ref.to_dict() if self.timeline_ref is not None else None,
        }


@dataclass(frozen=True)
class KnowledgeView:
    """Complete per-style read model: the style's insight composed with its
    learning-chain and rollback insights into one coherent object."""

    schema_version: int
    view_id: str
    subject_type: str
    style_id: str
    sections: tuple
    references: tuple
    confidence: ViewConfidence
    generated_from: tuple

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "view_id": self.view_id,
            "subject_type": self.subject_type,
            "style_id": self.style_id,
            "sections": [s.to_dict() for s in self.sections],
            "references": list(self.references),
            "confidence": self.confidence.to_dict(),
            "generated_from": list(self.generated_from),
        }


@dataclass(frozen=True)
class RunView:
    """Per-run read model: the run's insight composed with its provenance/trace."""

    schema_version: int
    view_id: str
    subject_type: str
    run_id: str
    run_insight: ViewInsight
    provenance: RunProvenance | None
    references: tuple
    confidence: ViewConfidence
    generated_from: tuple

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "view_id": self.view_id,
            "subject_type": self.subject_type,
            "run_id": self.run_id,
            "run_insight": self.run_insight.to_dict(),
            "provenance": self.provenance.to_dict() if self.provenance is not None else None,
            "references": list(self.references),
            "confidence": self.confidence.to_dict(),
            "generated_from": list(self.generated_from),
        }


@dataclass(frozen=True)
class PortfolioView:
    """Multi-style composite over an explicit scope."""

    schema_version: int
    view_id: str
    subject_type: str
    style_count: int
    sections: tuple
    aggregate_statistics: ViewStatistics
    references: tuple
    confidence: ViewConfidence
    generated_from: tuple

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "view_id": self.view_id,
            "subject_type": self.subject_type,
            "style_count": self.style_count,
            "sections": [s.to_dict() for s in self.sections],
            "aggregate_statistics": self.aggregate_statistics.to_dict(),
            "references": list(self.references),
            "confidence": self.confidence.to_dict(),
            "generated_from": list(self.generated_from),
        }


@dataclass(frozen=True)
class SystemOverview:
    """Top-level aggregated counts/coverage across a scope — facts only."""

    schema_version: int
    view_id: str
    subject_type: str
    scope_size: int
    totals: ViewStatistics
    references: tuple
    generated_from: tuple

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "view_id": self.view_id,
            "subject_type": self.subject_type,
            "scope_size": self.scope_size,
            "totals": self.totals.to_dict(),
            "references": list(self.references),
            "generated_from": list(self.generated_from),
        }


# --------------------------------------------------------------------------- #
# error result models — returned, never raised
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ViewUnavailable:
    target: str
    reason: str

    def to_dict(self) -> dict:
        return {"error": "ViewUnavailable", "target": self.target, "reason": self.reason}


@dataclass(frozen=True)
class StyleNotFound:
    style_id: str

    def to_dict(self) -> dict:
        return {"error": "StyleNotFound", "style_id": self.style_id}


@dataclass(frozen=True)
class RunNotFound:
    run_id: str

    def to_dict(self) -> dict:
        return {"error": "RunNotFound", "run_id": self.run_id}


@dataclass(frozen=True)
class EmptyScope:
    reason: str

    def to_dict(self) -> dict:
        return {"error": "EmptyScope", "reason": self.reason}
