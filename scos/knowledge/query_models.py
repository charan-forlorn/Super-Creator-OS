"""SCOS Stage 3.6 — Knowledge Query Engine result models.

Pure, immutable result shapes returned by KnowledgeQueryEngine (see
query_engine.py). Every public engine method returns exactly one of these —
a success model or an *error result* model. Errors are deterministic result
objects, never raised exceptions, so a caller can branch on type without
try/except and get byte-identical results for an identical KnowledgeIndex.

No business logic, no I/O, no scos.* imports, no json/open/IndexStore. All
models are frozen dataclasses; `to_dict()` is a pure transform for inspection
and deterministic test assertions (there is no persistence in Stage 3.6).
"""

from __future__ import annotations

from dataclasses import dataclass

# --------------------------------------------------------------------------- #
# success models
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class StyleSummary:
    """Computed-only roll-up of one style's history. No inference, no AI —
    every field is counted or sequenced directly from the timeline's events."""

    style_id: str
    version_count: int
    current_version: int | None
    timeline_depth: int
    first_timestamp: int | float | None
    last_timestamp: int | float | None
    rollback_count: int
    decision_distribution: dict
    quality_trend: tuple
    retention_trend: tuple

    def to_dict(self) -> dict:
        return {
            "style_id": self.style_id,
            "version_count": self.version_count,
            "current_version": self.current_version,
            "timeline_depth": self.timeline_depth,
            "first_timestamp": self.first_timestamp,
            "last_timestamp": self.last_timestamp,
            "rollback_count": self.rollback_count,
            "decision_distribution": self.decision_distribution,
            "quality_trend": [list(t) for t in self.quality_trend],
            "retention_trend": [list(t) for t in self.retention_trend],
        }


@dataclass(frozen=True)
class ExplainStyleResult:
    """git-show for a style: its current version, every version snapshot, every
    decision, the full ordered event list, and the computed summary."""

    style_id: str
    current_version: int | None
    version_count: int
    first_seen: int | float | None
    last_updated: int | float | None
    versions: tuple
    decisions: tuple
    events: tuple
    summary: StyleSummary

    def to_dict(self) -> dict:
        return {
            "style_id": self.style_id,
            "current_version": self.current_version,
            "version_count": self.version_count,
            "first_seen": self.first_seen,
            "last_updated": self.last_updated,
            "versions": [dict(v) for v in self.versions],
            "decisions": list(self.decisions),
            "events": [e.to_dict() for e in self.events],
            "summary": self.summary.to_dict(),
        }


@dataclass(frozen=True)
class FieldChange:
    """One structural difference between two style profiles."""

    field: str
    change_type: str  # "added" | "removed" | "modified"
    from_value: object
    to_value: object

    def to_dict(self) -> dict:
        return {
            "field": self.field,
            "change_type": self.change_type,
            "from_value": self.from_value,
            "to_value": self.to_value,
        }


@dataclass(frozen=True)
class CompareVersionsResult:
    """git-diff between two versions of one style. Pure structural comparison
    of the two profile snapshots — no inference about why fields changed."""

    style_id: str
    from_version: int
    to_version: int
    changes: tuple
    audit_id: str | None
    decision: str | None
    timestamp: int | float | None

    def to_dict(self) -> dict:
        return {
            "style_id": self.style_id,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "changes": [c.to_dict() for c in self.changes],
            "audit_id": self.audit_id,
            "decision": self.decision,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class RunTraceResult:
    """git-blame for a run: complete provenance across the 4 artifacts. Each
    link is a small dict or None — None means the link is genuinely absent,
    never inferred."""

    run_id: str
    session_id: str | None
    asset_hash: str | None
    style_id: str | None
    current_version: int | None
    decision: str | None
    replay: dict | None
    feedback: dict | None
    audit: dict | None
    style_version: dict | None
    timeline_ref: dict | None

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "session_id": self.session_id,
            "asset_hash": self.asset_hash,
            "style_id": self.style_id,
            "current_version": self.current_version,
            "decision": self.decision,
            "replay": self.replay,
            "feedback": self.feedback,
            "audit": self.audit,
            "style_version": self.style_version,
            "timeline_ref": self.timeline_ref,
        }


@dataclass(frozen=True)
class StyleChangeExplanation:
    """why-was-this-changed for one version. Returns ONLY recorded facts:
    the audit reason, the feedback summary, the metrics, and the surrounding
    versions. audit_reason is None for seed/unresolved versions — never invented."""

    style_id: str
    version: int
    previous_version: int | None
    current_version: int | None
    audit_reason: str | None
    feedback_summary: dict
    metrics: dict

    def to_dict(self) -> dict:
        return {
            "style_id": self.style_id,
            "version": self.version,
            "previous_version": self.previous_version,
            "current_version": self.current_version,
            "audit_reason": self.audit_reason,
            "feedback_summary": self.feedback_summary,
            "metrics": self.metrics,
        }


@dataclass(frozen=True)
class RollbackHistory:
    """Every ROLLBACK decision, ordered by (timestamp, stable id). style_id is
    None when not filtered to a single style."""

    style_id: str | None
    rollbacks: tuple

    def to_dict(self) -> dict:
        return {
            "style_id": self.style_id,
            "rollbacks": [dict(r) for r in self.rollbacks],
        }


@dataclass(frozen=True)
class RelatedEvents:
    """Every event transitively related to a run (shared run/audit/style/
    session), deduplicated and ordered."""

    run_id: str
    events: tuple

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "events": [e.to_dict() for e in self.events],
        }


@dataclass(frozen=True)
class LearningChain:
    """The deterministic causal chain for a run:
    replay -> feedback -> audit -> version -> timeline -> current style.
    Any missing link is None — the chain is never completed by inference."""

    run_id: str
    replay: dict | None
    feedback: dict | None
    audit: dict | None
    version: dict | None
    timeline_ref: dict | None
    current_style: dict | None

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "replay": self.replay,
            "feedback": self.feedback,
            "audit": self.audit,
            "version": self.version,
            "timeline_ref": self.timeline_ref,
            "current_style": self.current_style,
        }


# --------------------------------------------------------------------------- #
# error result models — returned, never raised
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
class VersionNotFound:
    style_id: str
    version: int

    def to_dict(self) -> dict:
        return {"error": "VersionNotFound", "style_id": self.style_id, "version": self.version}


@dataclass(frozen=True)
class BrokenReference:
    """A referenced audit_id in a style snapshot did not resolve — the index
    recorded a 'does not resolve' validation issue for it."""

    reference: str
    detail: str

    def to_dict(self) -> dict:
        return {"error": "BrokenReference", "reference": self.reference, "detail": self.detail}


@dataclass(frozen=True)
class InvalidComparison:
    style_id: str
    from_version: int
    to_version: int
    reason: str

    def to_dict(self) -> dict:
        return {
            "error": "InvalidComparison",
            "style_id": self.style_id,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "reason": self.reason,
        }
