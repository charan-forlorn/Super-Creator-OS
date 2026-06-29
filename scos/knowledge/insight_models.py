"""SCOS Stage 3.8 — Knowledge Insight Engine output + error models.

Pure, immutable shapes returned by KnowledgeInsightEngine (see insight_engine.py).
Every public engine method returns exactly one of these — an `Insight` or an
error-result model. Errors are deterministic result objects, never raised.

An Insight is an aggregation of facts *already returned by the Explain Engine* —
it creates no knowledge, infers nothing, predicts nothing, scores nothing. All
numeric fields in InsightStatistics are direct counts of certified facts.

No business logic, no I/O, no scos.* imports, no json/open/IndexStore, no clock,
no randomness. All models are frozen dataclasses; `to_dict()` is a pure transform.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Insight output-contract version — independent of the Explain layer's
# EXPLANATION_SCHEMA_VERSION so the two layers version separately over time.
INSIGHT_SCHEMA_VERSION = 1

# insight_type discriminators — fixed, machine-routable.
INSIGHT_STYLE = "style"
INSIGHT_RUN = "run"
INSIGHT_LEARNING = "learning"
INSIGHT_ROLLBACK = "rollback"
INSIGHT_PORTFOLIO = "portfolio"  # replaces the spec's "system" — see engine docstring


@dataclass(frozen=True)
class InsightStatistics:
    """Aggregated facts only — every field is a direct count of certified data
    returned by the Explain Engine. No estimates, no scores, no predictions."""

    version_count: int = 0
    rollback_count: int = 0
    learning_count: int = 0
    feedback_count: int = 0
    quality_samples: int = 0
    retention_samples: int = 0
    style_count: int = 0
    decision_counts: dict = field(default_factory=dict)

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
class Insight:
    """An immutable, deterministic aggregation of already-certified facts.

    `confidence` reuses the Stage 3.7 Confidence model exactly (evidence
    completeness only). `schema_version` is engine-stamped from
    INSIGHT_SCHEMA_VERSION. `insight_id`/`generated_from` aid Stage 4 reference,
    caching, and audit — they are provenance, never new knowledge."""

    schema_version: int
    insight_id: str
    insight_type: str
    title: str
    summary: str
    statistics: InsightStatistics
    references: tuple
    confidence: object
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


# --------------------------------------------------------------------------- #
# error result models — returned, never raised (Stage 3.7 philosophy)
# --------------------------------------------------------------------------- #


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
class MissingEvidence:
    target: str
    missing: tuple

    def to_dict(self) -> dict:
        return {"error": "MissingEvidence", "target": self.target, "missing": list(self.missing)}


@dataclass(frozen=True)
class BrokenReference:
    reference: str
    detail: str

    def to_dict(self) -> dict:
        return {"error": "BrokenReference", "reference": self.reference, "detail": self.detail}


@dataclass(frozen=True)
class InsightUnavailable:
    target: str
    reason: str

    def to_dict(self) -> dict:
        return {"error": "InsightUnavailable", "target": self.target, "reason": self.reason}
