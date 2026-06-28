"""SCOS Stage 3.5 — Learning Knowledge Index data models.

Pure, immutable data shapes for the read-only knowledge layer built over SCOS's
existing learning artifacts (feedback_log.json, learning_audit.json,
style_history.json, replay_report.json). No business logic, no I/O, no scos.*
imports — see knowledge_index.py (build) and index_store.py (persistence).

All models are frozen dataclasses: once constructed, a LearningEvent/Timeline/
KnowledgeIndex never changes. This module never raises into a partial build —
it only defines shapes.
"""

from __future__ import annotations

from dataclasses import dataclass

INDEX_VERSION = 1
SCHEMA_VERSION = 1

SOURCE_FEEDBACK_LOG = "feedback_log"
SOURCE_LEARNING_AUDIT = "learning_audit"
SOURCE_STYLE_HISTORY = "style_history"
SOURCE_REPLAY_REPORT = "replay_report"

EVENT_FEEDBACK_RECORDED = "FEEDBACK_RECORDED"
EVENT_LEARNING_DECISION = "LEARNING_DECISION"
EVENT_STYLE_VERSION_CREATED = "STYLE_VERSION_CREATED"
EVENT_REPLAY_RECORD = "REPLAY_RECORD"

DECISION_ROLLBACK = "ROLLBACK"
DECISION_APPLY = "APPLY"
DECISION_CLAMP = "CLAMP"
DECISION_REJECT = "REJECT"
DECISION_FAIL = "FAIL"


@dataclass(frozen=True)
class LearningEvent:
    """One indexed event from exactly one source artifact.

    `confidence` is always None for events built from the 4 permitted sources —
    none of them carry a per-event confidence value (only the separate, non-input
    learning_state.json does). This is a documented limitation, not a bug.
    """

    run_id: str | None
    session_id: str | None
    replay_id: str | None
    timestamp: int | float | None
    style_version: int | None
    event_type: str
    source: str
    metrics: dict
    decision: str | None
    rollback: bool
    confidence: float | None
    metadata: dict

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "session_id": self.session_id,
            "replay_id": self.replay_id,
            "timestamp": self.timestamp,
            "style_version": self.style_version,
            "event_type": self.event_type,
            "source": self.source,
            "metrics": self.metrics,
            "decision": self.decision,
            "rollback": self.rollback,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }

    @staticmethod
    def from_dict(d: dict) -> "LearningEvent":
        return LearningEvent(**d)


@dataclass(frozen=True)
class LearningTimeline:
    """One style_id's version history plus every event that touched it."""

    style_id: str
    versions: tuple
    events: tuple
    current_version: int | None

    def to_dict(self) -> dict:
        return {
            "style_id": self.style_id,
            "versions": [dict(v) for v in self.versions],
            "events": [e.to_dict() for e in self.events],
            "current_version": self.current_version,
        }

    @staticmethod
    def from_dict(d: dict) -> "LearningTimeline":
        return LearningTimeline(
            style_id=d["style_id"],
            versions=tuple(d["versions"]),
            events=tuple(LearningEvent.from_dict(e) for e in d["events"]),
            current_version=d["current_version"],
        )


@dataclass(frozen=True)
class ValidationIssue:
    """One deterministic validation finding. Reporting only — never auto-repaired."""

    source: str
    message: str
    record_ref: str | None

    def to_dict(self) -> dict:
        return {"source": self.source, "message": self.message, "record_ref": self.record_ref}

    @staticmethod
    def from_dict(d: dict) -> "ValidationIssue":
        return ValidationIssue(**d)


@dataclass(frozen=True)
class KnowledgeIndex:
    """The complete, immutable result of one build() — the runtime object that
    IndexStore persists/restores. Never constructed directly by query.py."""

    timeline: dict
    events: tuple
    replay_map: dict
    asset_map: dict
    statistics: dict
    metadata: dict
    validation_issues: tuple

    def to_dict(self) -> dict:
        return {
            "timeline": {sid: tl.to_dict() for sid, tl in self.timeline.items()},
            "events": [e.to_dict() for e in self.events],
            "replay_map": self.replay_map,
            "asset_map": self.asset_map,
            "statistics": self.statistics,
            "metadata": self.metadata,
            "validation_issues": [i.to_dict() for i in self.validation_issues],
        }

    @staticmethod
    def from_dict(d: dict) -> "KnowledgeIndex":
        return KnowledgeIndex(
            timeline={sid: LearningTimeline.from_dict(tl) for sid, tl in d["timeline"].items()},
            events=tuple(LearningEvent.from_dict(e) for e in d["events"]),
            replay_map=d["replay_map"],
            asset_map=d["asset_map"],
            statistics=d["statistics"],
            metadata=d["metadata"],
            validation_issues=tuple(ValidationIssue.from_dict(i) for i in d["validation_issues"]),
        )
