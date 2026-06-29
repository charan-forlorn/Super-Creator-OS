"""SCOS Stage 3.8 — Knowledge Explain Facade.

A real (not pass-through) contract seam between the certified Stage 3.7 Explain
Engine and the Stage 3.8 Insight Engine:

    KnowledgeExplainEngine  ->  KnowledgeExplainFacade  ->  KnowledgeInsightEngine

Why a *real* facade and not a pass-through: a pass-through that simply forwards
Explanation objects (or their inner dicts) gives false safety — upstream drift
still cascades into the consumer. This facade therefore normalizes the entire
payload the Insight layer depends on into facade-OWNED frozen shapes:

  * error envelope  -> ExplainFact.ok + stable error_kind string
  * each event      -> EventFact (only the fields Insight needs, by name)
  * each reference   -> Reference(category, ident)   (the upstream "cat:id" string
                        format is parsed HERE, exactly once, and nowhere else)
  * confidence      -> ConfidenceFact (facade-owned; not an explain_models object)

Consequence: the Insight layer reads no upstream dict key, no upstream string
format, and no explain_models type. Any Explain-layer drift is absorbed in
_to_fact / _event_fact / _reference below — the single quarantine point.

Production module: no json/open/IndexStore/filesystem/network/random/clock/
mutation. Wraps the Explain Engine; reads only its returned objects; modifies no
certified file.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from explain_engine import KnowledgeExplainEngine  # noqa: E402
import explain_models as _em  # noqa: E402

# Facade-owned contract constants (NOT re-exports of explain_models internals).
REF_CATEGORY_ORDER = ("run", "style", "version", "audit", "session")

CONFIDENCE_COMPLETE = "complete"
CONFIDENCE_PARTIAL = "partial"
CONFIDENCE_NONE = "none"

ERROR_STYLE_NOT_FOUND = "StyleNotFound"
ERROR_RUN_NOT_FOUND = "RunNotFound"
ERROR_MISSING_EVIDENCE = "MissingEvidence"
ERROR_BROKEN_REFERENCE = "BrokenReference"
ERROR_EXPLANATION_UNAVAILABLE = "ExplanationUnavailable"

# Upstream event-dict keys / decision literals — referenced ONLY here, so a rename
# upstream is fixed in this file alone.
_K_EVENT_TYPE = "event_type"
_K_DECISION = "decision"
_K_METRICS = "metrics"
_K_QUALITY = "quality_score"
_K_RETENTION = "retention_score"


@dataclass(frozen=True)
class ConfidenceFact:
    """Facade-owned evidence-completeness value. Mirrors the Stage 3.7 semantics
    (level + present/expected/missing) without exposing the explain_models type,
    so the Insight layer depends on the facade's contract, not upstream's class."""

    level: str
    present: int
    expected: int
    missing: tuple

    def to_dict(self) -> dict:
        return {"level": self.level, "present": self.present,
                "expected": self.expected, "missing": list(self.missing)}

    @staticmethod
    def of(present_names, expected_names) -> "ConfidenceFact":
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
        return ConfidenceFact(level=level, present=present, expected=expected, missing=missing)


@dataclass(frozen=True)
class EventFact:
    """The only event fields the Insight layer is allowed to depend on — extracted
    by name from the upstream event dict here, so Insight never touches that dict."""

    event_type: str | None
    decision: str | None
    has_quality: bool
    has_retention: bool

    def to_dict(self) -> dict:
        return {"event_type": self.event_type, "decision": self.decision,
                "has_quality": self.has_quality, "has_retention": self.has_retention}


@dataclass(frozen=True)
class Reference:
    """A structured reference. The upstream 'category:id' string is parsed into
    this once, in the facade; the Insight layer consumes category/ident, never the
    raw string format."""

    category: str
    ident: str

    @property
    def label(self) -> str:
        return f"{self.category}:{self.ident}"

    def to_dict(self) -> dict:
        return {"category": self.category, "ident": self.ident}


@dataclass(frozen=True)
class ExplainFact:
    """Normalized, immutable view of one Explain result — the frozen contract the
    Insight layer depends on, fully decoupled from the Explanation dataclass."""

    ok: bool
    error_kind: str | None
    error_detail: dict
    events: tuple          # tuple[EventFact]
    references: tuple      # tuple[Reference]
    confidence: object     # ConfidenceFact | None

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "error_kind": self.error_kind,
            "error_detail": dict(self.error_detail),
            "events": [e.to_dict() for e in self.events],
            "references": [r.to_dict() for r in self.references],
            "confidence": self.confidence.to_dict() if self.confidence is not None else None,
        }


class KnowledgeExplainFacade:
    """Frozen contract wrapper over KnowledgeExplainEngine. Exposes the five
    Explain APIs, each returning a fully-normalized ExplainFact."""

    def __init__(self, index) -> None:
        self._engine = KnowledgeExplainEngine(index)

    # ---- single drift quarantine: all upstream-shape knowledge lives here ---- #

    @staticmethod
    def _event_fact(event_dict) -> EventFact:
        metrics = event_dict.get(_K_METRICS) or {}
        return EventFact(
            event_type=event_dict.get(_K_EVENT_TYPE),
            decision=event_dict.get(_K_DECISION),
            has_quality=metrics.get(_K_QUALITY) is not None,
            has_retention=metrics.get(_K_RETENTION) is not None,
        )

    @staticmethod
    def _reference(ref_string) -> Reference:
        category, _, ident = ref_string.partition(":")
        return Reference(category=category, ident=ident)

    @staticmethod
    def _confidence(conf) -> "ConfidenceFact | None":
        if conf is None:
            return None
        return ConfidenceFact(level=conf.level, present=conf.present,
                              expected=conf.expected, missing=tuple(conf.missing))

    def _to_fact(self, result) -> ExplainFact:
        if isinstance(result, _em.StyleNotFound):
            return ExplainFact(False, ERROR_STYLE_NOT_FOUND, {"style_id": result.style_id}, (), (), None)
        if isinstance(result, _em.RunNotFound):
            return ExplainFact(False, ERROR_RUN_NOT_FOUND, {"run_id": result.run_id}, (), (), None)
        if isinstance(result, _em.MissingEvidence):
            return ExplainFact(False, ERROR_MISSING_EVIDENCE,
                               {"target": result.target, "missing": tuple(result.missing)}, (), (), None)
        if isinstance(result, _em.BrokenReference):
            return ExplainFact(False, ERROR_BROKEN_REFERENCE,
                               {"reference": result.reference, "detail": result.detail}, (), (), None)
        if isinstance(result, _em.ExplanationUnavailable):
            return ExplainFact(False, ERROR_EXPLANATION_UNAVAILABLE,
                               {"target": result.target, "reason": result.reason}, (), (), None)
        # otherwise an Explanation — normalize every payload piece into facade types
        return ExplainFact(
            True, None, {},
            tuple(self._event_fact(e) for e in result.supporting_events),
            tuple(self._reference(r) for r in result.references),
            self._confidence(result.confidence),
        )

    # -------------------------------- API ------------------------------------ #

    def explain_style(self, style_id) -> ExplainFact:
        return self._to_fact(self._engine.explain_style(style_id))

    def explain_run(self, run_id) -> ExplainFact:
        return self._to_fact(self._engine.explain_run(run_id))

    def explain_learning_chain(self, style_id) -> ExplainFact:
        return self._to_fact(self._engine.explain_learning_chain(style_id))

    def explain_rollback(self, version_id) -> ExplainFact:
        return self._to_fact(self._engine.explain_rollback(version_id))

    def summarize_learning(self, style_id) -> ExplainFact:
        return self._to_fact(self._engine.summarize_learning(style_id))
