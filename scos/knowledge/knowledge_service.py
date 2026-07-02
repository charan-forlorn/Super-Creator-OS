"""SCOS Stage 3.9 — Knowledge Access Layer (KnowledgeService).

The unified, read-only consumer boundary over the Knowledge subsystem:

    KnowledgeIndex -> Query -> Explain -> ExplainFacade -> Insight -> KnowledgeService

KnowledgeService is the single entrypoint a consumer (a future Stage 4 Decision
engine, a CLI, a dashboard) depends on. It *composes and projects* the public
outputs of the certified Insight and Query engines into coherent, frozen view
read-models — it creates no knowledge, makes no decision, scores/ranks/predicts
nothing, and mutates nothing.

Boundary (frozen, certifiable by grep — zero hits expected): no json, no open(),
no IndexStore, no filesystem, no network, no random, no datetime/time/clock, no
persistence, no mutation. Lower-layer error types are translated into the
Access-layer error vocabulary (knowledge_view_models) — none leak into the view
models. (query_models / insight_models are imported here ONLY for isinstance
dispatch; the view models themselves import no lower-layer type.)

Determinism: identical KnowledgeIndex in -> identical view JSON out, every call.
"""

from __future__ import annotations

from insight_engine import KnowledgeInsightEngine
from query_engine import KnowledgeQueryEngine
import insight_models as im  # isinstance dispatch only
import query_models as qm  # isinstance dispatch only
import knowledge_view_models as vm


class KnowledgeService:
    """Deterministic, side-effect-free unified read interface over one
    KnowledgeIndex, composing the Insight and Query public contracts."""

    def __init__(self, index) -> None:
        self._insight = KnowledgeInsightEngine(index)
        self._query = KnowledgeQueryEngine(index)

    # ------------------------------------------------------------------ #
    # private helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _order_refs(labels):
        """Reference Ordering Contract over 'category:id' labels: dedupe, group by
        REF_CATEGORY_ORDER, sort by id within a category."""
        order = {c: i for i, c in enumerate(vm.REF_CATEGORY_ORDER)}
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
    def _scope_key(style_ids):
        """Deterministic, length-prefixed portfolio identity for an explicit scope."""
        return "|".join(f"{len(sid)}:{sid}" for sid in sorted(frozenset(style_ids)))

    @staticmethod
    def _view_confidence(conf):
        """Wrap a lower-layer confidence (ConfidenceFact) into the Access-layer
        ViewConfidence — no lower-layer type leaks out."""
        return vm.ViewConfidence(level=conf.level, present=conf.present,
                                 expected=conf.expected, missing=tuple(conf.missing))

    @classmethod
    def _view_statistics(cls, stats):
        return vm.ViewStatistics(
            version_count=stats.version_count,
            rollback_count=stats.rollback_count,
            learning_count=stats.learning_count,
            feedback_count=stats.feedback_count,
            quality_samples=stats.quality_samples,
            retention_samples=stats.retention_samples,
            style_count=stats.style_count,
            decision_counts=tuple(sorted(stats.decision_counts.items())),
        )

    @classmethod
    def _view_insight(cls, insight):
        return vm.ViewInsight(
            schema_version=insight.schema_version,
            insight_id=insight.insight_id,
            insight_type=insight.insight_type,
            title=insight.title,
            summary=insight.summary,
            statistics=cls._view_statistics(insight.statistics),
            references=tuple(insight.references),
            confidence=cls._view_confidence(insight.confidence),
            generated_from=tuple(insight.generated_from),
        )

    @staticmethod
    def _payload(mapping):
        return vm.FrozenPayload.from_mapping(mapping) if mapping is not None else None

    @classmethod
    def _run_provenance(cls, trace):
        return vm.RunProvenance(
            run_id=trace.run_id,
            session_id=trace.session_id,
            asset_hash=trace.asset_hash,
            style_id=trace.style_id,
            current_version=trace.current_version,
            decision=trace.decision,
            replay=cls._payload(trace.replay),
            feedback=cls._payload(trace.feedback),
            audit=cls._payload(trace.audit),
            style_version=cls._payload(trace.style_version),
            timeline_ref=cls._payload(trace.timeline_ref),
        )

    @staticmethod
    def _error_detail(result):
        if isinstance(result, im.MissingEvidence):
            return "missing_evidence", vm.ViewError(
                "MissingEvidence", result.target, ",".join(result.missing))
        if isinstance(result, im.BrokenReference):
            return "broken_reference", vm.ViewError(
                "BrokenReference", result.reference, result.detail)
        if isinstance(result, im.InsightUnavailable):
            return "unavailable", vm.ViewError(
                "InsightUnavailable", result.target, result.reason)
        return "unavailable", vm.ViewError(
            type(result).__name__, "unknown", "unrecognized insight result")

    @classmethod
    def _section(cls, kind, result):
        if isinstance(result, im.Insight):
            return vm.ViewSection(kind=kind, status="ok",
                                  insight=cls._view_insight(result))
        status, error = cls._error_detail(result)
        return vm.ViewSection(kind=kind, status=status, error=error)

    @staticmethod
    def _resolve_scope(scope):
        """Mirror the Insight scope contract → (style_ids, error_reason, requested)."""
        if scope is None:
            return (), "no scope provided", 0
        if isinstance(scope, dict):
            if scope.get("type") == "explicit":
                raw_ids = scope.get("style_ids") or ()
                if isinstance(raw_ids, str) or not isinstance(raw_ids, (list, tuple)):
                    return (), "explicit scope style_ids must be a list or tuple", 0
                ids = tuple(raw_ids)
                if any(not isinstance(sid, str) for sid in ids):
                    return (), "scope style_ids must be strings", 0
                return ids, None, len(frozenset(ids))
            return (), f"unsupported scope type: {scope.get('type')!r}", 0
        if isinstance(scope, str) or not isinstance(scope, (list, tuple)):
            return (), "scope must be a list, tuple, or explicit scope object", 0
        ids = tuple(scope)
        if any(not isinstance(sid, str) for sid in ids):
            return (), "scope style_ids must be strings", 0
        return ids, None, len(frozenset(ids))

    # ------------------------------------------------------------------ #
    # public API (exactly four)
    # ------------------------------------------------------------------ #

    def knowledge_view(self, style_id):
        si = self._insight.style_insight(style_id)
        if isinstance(si, im.StyleNotFound):
            return vm.StyleNotFound(style_id)
        # si is an Insight (style exists). learning/rollback may be MissingEvidence.
        li = self._insight.learning_insight(style_id)
        rb = self._insight.rollback_insight(style_id)

        sections = (self._section("style", si),
                    self._section("learning", li),
                    self._section("rollback", rb))
        present = [s.kind for s in sections if s.status == "ok"]

        labels = list(si.references)
        for r in (li, rb):
            if isinstance(r, im.Insight):
                labels.extend(r.references)

        return vm.KnowledgeView(
            schema_version=vm.KNOWLEDGE_VIEW_SCHEMA_VERSION,
            view_id=f"style:{style_id}", subject_type=vm.SUBJECT_STYLE, style_id=style_id,
            sections=sections, references=self._order_refs(labels),
            confidence=vm.ViewConfidence.of(present, ("style", "learning", "rollback")),
            generated_from=("KnowledgeInsightEngine.style_insight",
                            "KnowledgeInsightEngine.learning_insight",
                            "KnowledgeInsightEngine.rollback_insight"))

    def run_view(self, run_id):
        ri = self._insight.run_insight(run_id)
        if isinstance(ri, im.RunNotFound):
            return vm.RunNotFound(run_id)
        if isinstance(ri, im.BrokenReference):
            return vm.ViewUnavailable(run_id, f"broken reference: {ri.reference}")
        if isinstance(ri, im.MissingEvidence):
            return vm.ViewUnavailable(run_id, "missing evidence for run")

        # ri is an Insight — compose provenance from the Query layer's trace.
        trace = self._query.trace_run(run_id)
        if isinstance(trace, qm.BrokenReference):
            return vm.ViewUnavailable(run_id, f"broken reference: {trace.reference}")
        provenance = self._run_provenance(trace) if isinstance(trace, qm.RunTraceResult) else None

        return vm.RunView(
            schema_version=vm.KNOWLEDGE_VIEW_SCHEMA_VERSION,
            view_id=f"run:{run_id}", subject_type=vm.SUBJECT_RUN, run_id=run_id,
            run_insight=self._view_insight(ri), provenance=provenance,
            references=self._order_refs(list(ri.references)),
            confidence=self._view_confidence(ri.confidence),
            generated_from=("KnowledgeInsightEngine.run_insight",
                            "KnowledgeQueryEngine.trace_run"))

    def portfolio_view(self, scope):
        ids, error_reason, _requested = self._resolve_scope(scope)
        if error_reason is not None:
            if error_reason != "no scope provided":
                return vm.ViewUnavailable("portfolio", error_reason)
            return vm.EmptyScope(error_reason)
        if not ids:
            return vm.EmptyScope("empty scope")

        pi = self._insight.portfolio_summary(scope)
        if isinstance(pi, im.InsightUnavailable):
            return vm.EmptyScope(pi.reason)

        # per-style sections (resolved styles only), deterministic order
        sections = []
        for sid in sorted(frozenset(ids)):
            s = self._insight.style_insight(sid)
            if isinstance(s, im.Insight):
                sections.append(vm.ViewSection(kind="style", status="ok",
                                               insight=self._view_insight(s)))
            else:
                status, error = self._error_detail(s)
                if isinstance(s, im.StyleNotFound):
                    status = "not_found"
                    error = vm.ViewError("StyleNotFound", sid, "style not found")
                sections.append(vm.ViewSection(kind="style", status=status,
                                               error=error, style_id=sid))

        return vm.PortfolioView(
            schema_version=vm.KNOWLEDGE_VIEW_SCHEMA_VERSION,
            view_id=f"portfolio:{self._scope_key(ids)}", subject_type=vm.SUBJECT_PORTFOLIO,
            style_count=pi.statistics.style_count, sections=tuple(sections),
            aggregate_statistics=self._view_statistics(pi.statistics),
            references=self._order_refs(list(pi.references)),
            confidence=self._view_confidence(pi.confidence),
            generated_from=("KnowledgeInsightEngine.portfolio_summary",
                            "KnowledgeInsightEngine.style_insight"))

    def overview(self, scope):
        ids, error_reason, requested = self._resolve_scope(scope)
        if error_reason is not None:
            if error_reason != "no scope provided":
                return vm.ViewUnavailable("system", error_reason)
            return vm.EmptyScope(error_reason)
        if not ids:
            return vm.EmptyScope("empty scope")

        pi = self._insight.portfolio_summary(scope)
        if isinstance(pi, im.InsightUnavailable):
            return vm.EmptyScope(pi.reason)

        return vm.SystemOverview(
            schema_version=vm.KNOWLEDGE_VIEW_SCHEMA_VERSION,
            view_id=f"system:{requested}", subject_type=vm.SUBJECT_SYSTEM,
            scope_size=requested, totals=self._view_statistics(pi.statistics),
            references=self._order_refs(list(pi.references)),
            generated_from=("KnowledgeInsightEngine.portfolio_summary",))
