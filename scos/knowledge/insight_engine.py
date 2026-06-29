"""SCOS Stage 3.8 — Knowledge Insight Engine.

The final read-only layer of the Knowledge subsystem:

    KnowledgeIndex -> KnowledgeQueryEngine -> KnowledgeExplainEngine
                   -> KnowledgeExplainFacade -> KnowledgeInsightEngine

KnowledgeInsightEngine depends ONLY on the KnowledgeExplainFacade's normalized
contract (ExplainFact / EventFact / Reference / ConfidenceFact). It reads no
upstream event-dict key, no upstream reference string format, and no
explain_models type — every such dependency lives behind the facade. It
aggregates the facade's facts into immutable Insight objects via deterministic
counting and fixed templates. It creates no knowledge, infers nothing, predicts
nothing, scores/ranks/recommends nothing, and mutates nothing.

Boundary (frozen, certifiable by grep — zero hits expected): no json, no open(),
no IndexStore, no filesystem, no network, no random, no datetime/time/clock, no
persistence, no mutation. Imports only the facade and its own insight_models.

Note on system_summary: the spec's no-arg `system_summary()` is intentionally NOT
implemented — the certified Explain Engine exposes no enumeration, and reading the
index to enumerate styles would break the explain-only contract. Per the approved
design it is replaced by `portfolio_summary(scope)` (explicit scope). A true
system-wide summary would require a future enumeration capability under its own
certification.

Determinism: identical KnowledgeIndex in -> identical Insight JSON out, every call.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from explain_facade import KnowledgeExplainFacade, ConfidenceFact, REF_CATEGORY_ORDER  # noqa: E402
import explain_facade as ef  # noqa: E402
import insight_models as im  # noqa: E402

_DECISION_ROLLBACK = "ROLLBACK"
_ET_FEEDBACK = "FEEDBACK_RECORDED"
_ET_LEARNING = "LEARNING_DECISION"
_STAT_CATEGORIES = ("versions", "decisions", "feedback", "learning")
_REF_VERSION = "version"


class KnowledgeInsightEngine:
    """Deterministic, side-effect-free insight interface over one KnowledgeIndex,
    accessed exclusively through the KnowledgeExplainFacade contract seam."""

    def __init__(self, index) -> None:
        self._explain = KnowledgeExplainFacade(index)

    # ------------------------------------------------------------------ #
    # private helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _to_insight_error(fact):
        """Map a facade error-kind (stable string) to this layer's error model.
        The Insight layer never sees explain_models types."""
        k, d = fact.error_kind, fact.error_detail
        if k == ef.ERROR_STYLE_NOT_FOUND:
            return im.StyleNotFound(d["style_id"])
        if k == ef.ERROR_RUN_NOT_FOUND:
            return im.RunNotFound(d["run_id"])
        if k == ef.ERROR_MISSING_EVIDENCE:
            return im.MissingEvidence(d["target"], tuple(d["missing"]))
        if k == ef.ERROR_BROKEN_REFERENCE:
            return im.BrokenReference(d["reference"], d["detail"])
        if k == ef.ERROR_EXPLANATION_UNAVAILABLE:
            return im.InsightUnavailable(d["target"], d["reason"])
        return im.InsightUnavailable("unknown", k or "unknown error")

    @staticmethod
    def _order_refs(labels):
        """Reference Ordering Contract over Insight-domain 'category:id' labels:
        dedupe, group by REF_CATEGORY_ORDER, sort by id within a category. (Labels
        are produced from facade Reference objects via _labels, so the only string
        parsing here is of Insight's own output format, not upstream's.)"""
        order = {c: i for i, c in enumerate(REF_CATEGORY_ORDER)}
        seen = set()
        items = []
        for label in labels:
            if label in seen:
                continue
            seen.add(label)
            category, _, ident = label.partition(":")
            items.append((order.get(category, len(order)), ident, label))
        items.sort(key=lambda t: (t[0], t[1]))
        return tuple(t[2] for t in items)

    @staticmethod
    def _labels(references):
        """facade Reference objects -> Insight-domain label strings."""
        return [r.label for r in references]

    @staticmethod
    def _aggregate_events(events):
        """Pure fact counts over facade EventFact objects (never raw dicts)."""
        decision_counts = {}
        feedback_count = learning_count = quality = retention = 0
        for e in events:
            if e.decision:
                decision_counts[e.decision] = decision_counts.get(e.decision, 0) + 1
            if e.event_type == _ET_FEEDBACK:
                feedback_count += 1
            elif e.event_type == _ET_LEARNING:
                learning_count += 1
            if e.has_quality:
                quality += 1
            if e.has_retention:
                retention += 1
        return decision_counts, feedback_count, learning_count, quality, retention

    @staticmethod
    def _stats_confidence(stats):
        """Evidence-completeness over which fact categories are populated — uses the
        facade's ConfidenceFact (Stage 3.7 semantics, facade-owned type). Never a
        probability."""
        present = []
        if stats.version_count:
            present.append("versions")
        if stats.decision_counts:
            present.append("decisions")
        if stats.feedback_count:
            present.append("feedback")
        if stats.learning_count:
            present.append("learning")
        return ConfidenceFact.of(present, _STAT_CATEGORIES)

    @staticmethod
    def _version_count(references):
        return sum(1 for r in references if r.category == _REF_VERSION)

    @staticmethod
    def _resolve_scope(scope):
        """Normalize portfolio scope to (style_ids, error_reason).

        Accepts (forward-compatible):
          - a list/tuple of style ids (explicit scope, the common case)
          - {"type": "explicit", "style_ids": [...]} (canonical scope object)
        error_reason is None on success, or a string for an unsupported scope
        (e.g. a future enumeration-based type not yet available)."""
        if scope is None:
            return (), "no scope provided"
        if isinstance(scope, dict):
            stype = scope.get("type")
            if stype == "explicit":
                return tuple(scope.get("style_ids") or ()), None
            return (), f"unsupported scope type: {stype!r}"
        return tuple(scope), None

    # ------------------------------------------------------------------ #
    # public API (exactly five)
    # ------------------------------------------------------------------ #

    def style_insight(self, style_id):
        fact = self._explain.explain_style(style_id)
        if not fact.ok:
            return self._to_insight_error(fact)

        decisions, feedback, learning, quality, retention = self._aggregate_events(fact.events)
        stats = im.InsightStatistics(
            version_count=self._version_count(fact.references),
            rollback_count=decisions.get(_DECISION_ROLLBACK, 0),
            learning_count=learning, feedback_count=feedback,
            quality_samples=quality, retention_samples=retention,
            style_count=1, decision_counts=decisions)
        summary = (
            f"Style {style_id} contains {stats.version_count} version(s) with "
            f"{stats.rollback_count} recorded rollback(s); "
            f"{stats.learning_count} learning decision(s), {stats.feedback_count} feedback record(s)."
        )
        return im.Insight(
            schema_version=im.INSIGHT_SCHEMA_VERSION, insight_id=f"style:{style_id}",
            insight_type=im.INSIGHT_STYLE, title=f"Style insight: {style_id}", summary=summary,
            statistics=stats, references=self._order_refs(self._labels(fact.references)),
            confidence=self._stats_confidence(stats),
            generated_from=("KnowledgeExplainFacade.explain_style",))

    def run_insight(self, run_id):
        fact = self._explain.explain_run(run_id)
        if not fact.ok:
            return self._to_insight_error(fact)

        decisions, feedback, learning, quality, retention = self._aggregate_events(fact.events)
        stats = im.InsightStatistics(
            learning_count=learning, feedback_count=feedback,
            quality_samples=quality, retention_samples=retention, decision_counts=decisions)
        summary = (
            f"Run {run_id} has {len(fact.events)} evidence record(s) "
            f"across {len(decisions)} decision type(s)."
        )
        return im.Insight(
            schema_version=im.INSIGHT_SCHEMA_VERSION, insight_id=f"run:{run_id}",
            insight_type=im.INSIGHT_RUN, title=f"Run insight: {run_id}", summary=summary,
            statistics=stats, references=self._order_refs(self._labels(fact.references)),
            confidence=fact.confidence,  # evidence completeness of the run's links
            generated_from=("KnowledgeExplainFacade.explain_run",))

    def learning_insight(self, style_id):
        fact = self._explain.explain_learning_chain(style_id)
        if not fact.ok:
            return self._to_insight_error(fact)

        decisions, feedback, learning, quality, retention = self._aggregate_events(fact.events)
        stats = im.InsightStatistics(
            version_count=self._version_count(fact.references),
            rollback_count=decisions.get(_DECISION_ROLLBACK, 0),
            learning_count=learning, feedback_count=feedback,
            quality_samples=quality, retention_samples=retention,
            style_count=1, decision_counts=decisions)
        summary = (
            f"Style {style_id} learning chain aggregates {len(fact.events)} chain link(s) "
            f"across {stats.version_count} version transition(s)."
        )
        return im.Insight(
            schema_version=im.INSIGHT_SCHEMA_VERSION, insight_id=f"learning:{style_id}",
            insight_type=im.INSIGHT_LEARNING, title=f"Learning insight: {style_id}", summary=summary,
            statistics=stats, references=self._order_refs(self._labels(fact.references)),
            confidence=fact.confidence,
            generated_from=("KnowledgeExplainFacade.explain_learning_chain",))

    def rollback_insight(self, style_id):
        # explain_rollback takes a version_id; list_rollbacks ignores the version
        # component, so a synthesized "style:0" deterministically scopes to the style.
        fact = self._explain.explain_rollback(f"{style_id}:0")
        if not fact.ok:
            return self._to_insight_error(fact)

        stats = im.InsightStatistics(
            rollback_count=len(fact.events), style_count=1,
            decision_counts=({_DECISION_ROLLBACK: len(fact.events)} if fact.events else {}))
        summary = f"Style {style_id} has {stats.rollback_count} recorded rollback(s)."
        return im.Insight(
            schema_version=im.INSIGHT_SCHEMA_VERSION, insight_id=f"rollback:{style_id}",
            insight_type=im.INSIGHT_ROLLBACK, title=f"Rollback insight: {style_id}", summary=summary,
            statistics=stats, references=self._order_refs(self._labels(fact.references)),
            confidence=fact.confidence,
            generated_from=("KnowledgeExplainFacade.explain_rollback",))

    def portfolio_summary(self, scope):
        ids, error_reason = self._resolve_scope(scope)
        if error_reason is not None:
            return im.InsightUnavailable("portfolio", error_reason)
        if not ids:
            return im.InsightUnavailable("portfolio", "empty scope")

        version = rollback = learning = feedback = quality = retention = 0
        decision_counts = {}
        all_labels = []
        resolved = 0
        requested = len(set(ids))
        for sid in sorted(set(ids)):
            si = self.style_insight(sid)
            if not isinstance(si, im.Insight):
                continue
            resolved += 1
            s = si.statistics
            version += s.version_count
            rollback += s.rollback_count
            learning += s.learning_count
            feedback += s.feedback_count
            quality += s.quality_samples
            retention += s.retention_samples
            for k, v in s.decision_counts.items():
                decision_counts[k] = decision_counts.get(k, 0) + v
            all_labels.extend(si.references)  # already Insight-domain label strings

        stats = im.InsightStatistics(
            version_count=version, rollback_count=rollback, learning_count=learning,
            feedback_count=feedback, quality_samples=quality, retention_samples=retention,
            style_count=resolved, decision_counts=decision_counts)
        summary = (
            f"Portfolio of {resolved} resolved style(s) (of {requested} requested) "
            f"contains {version} version(s) and {rollback} recorded rollback(s)."
        )
        return im.Insight(
            schema_version=im.INSIGHT_SCHEMA_VERSION, insight_id=f"portfolio:{resolved}",
            insight_type=im.INSIGHT_PORTFOLIO, title="Portfolio insight", summary=summary,
            statistics=stats, references=self._order_refs(all_labels),
            confidence=self._stats_confidence(stats),
            generated_from=("KnowledgeExplainFacade.explain_style",))
