"""SCOS Stage 3.7 — Knowledge Explain Engine output + error models.

Pure, immutable shapes returned by KnowledgeExplainEngine (see explain_engine.py).
Every public engine method returns exactly one of these — an `Explanation` or an
error-result model. Errors are deterministic result objects, never raised, so a
caller branches on type and gets byte-identical output for an identical
KnowledgeIndex.

No business logic, no I/O, no scos.* imports, no json/open/IndexStore, no clock,
no randomness. All models are frozen dataclasses; `to_dict()` is a pure transform
(there is no persistence in Stage 3.7).
"""

from __future__ import annotations

from dataclasses import dataclass

# Output-contract version. A future Stage 4/5 may emit Explanation v2; stamping
# this from day one gives that change a backward-compatibility discriminator.
EXPLANATION_SCHEMA_VERSION = 1

# explanation_type discriminators — a machine-routable tag so a UI / dashboard /
# JSON export never has to parse the human title.
EXPLANATION_RUN = "run"
EXPLANATION_STYLE = "style"
EXPLANATION_VERSION = "version"
EXPLANATION_ROLLBACK = "rollback"
EXPLANATION_LEARNING_CHAIN = "learning_chain"
EXPLANATION_SUMMARY = "summary"

# Confidence levels — evidence-completeness only, NOT probability.
CONFIDENCE_COMPLETE = "complete"
CONFIDENCE_PARTIAL = "partial"
CONFIDENCE_NONE = "none"

# Reference Ordering Contract: references group by category in this fixed order
# (not alphabetical), id-sorted within each category. Stable, readable JSON.
REF_CATEGORY_ORDER = ("run", "style", "version", "audit", "session")


@dataclass(frozen=True)
class Confidence:
    """Deterministic evidence-completeness of one explanation. `level` is derived
    purely from how many expected evidence links were actually present — it never
    estimates a probability."""

    level: str
    present: int
    expected: int
    missing: tuple

    @staticmethod
    def of(present_names, expected_names) -> "Confidence":
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
        return Confidence(level=level, present=present, expected=expected, missing=missing)

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "present": self.present,
            "expected": self.expected,
            "missing": list(self.missing),
        }


@dataclass(frozen=True)
class Explanation:
    """An immutable, deterministic explanation of a relationship already stored in
    the KnowledgeIndex. Contains only verified facts; no inference, no NLG."""

    schema_version: int
    explanation_type: str
    title: str
    summary: str
    supporting_events: tuple
    references: tuple
    confidence: Confidence

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "explanation_type": self.explanation_type,
            "title": self.title,
            "summary": self.summary,
            "supporting_events": [dict(e) for e in self.supporting_events],
            "references": list(self.references),
            "confidence": self.confidence.to_dict(),
        }


# --------------------------------------------------------------------------- #
# error result models — returned, never raised
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ExplanationUnavailable:
    """The request itself cannot be formed (e.g. malformed version_id, or the
    referenced version does not exist) — distinct from missing evidence."""

    target: str
    reason: str

    def to_dict(self) -> dict:
        return {"error": "ExplanationUnavailable", "target": self.target, "reason": self.reason}


@dataclass(frozen=True)
class MissingEvidence:
    """The target exists but carries no evidence to explain. Lists exactly what is
    missing — never repaired, never inferred."""

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
class StyleNotFound:
    style_id: str

    def to_dict(self) -> dict:
        return {"error": "StyleNotFound", "style_id": self.style_id}


@dataclass(frozen=True)
class RunNotFound:
    run_id: str

    def to_dict(self) -> dict:
        return {"error": "RunNotFound", "run_id": self.run_id}
