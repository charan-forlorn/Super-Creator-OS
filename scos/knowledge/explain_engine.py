"""SCOS Stage 3.7 — Knowledge Explain Engine.

A deterministic, read-only explanation layer over the certified Knowledge stack:

    KnowledgeIndex -> KnowledgeQueryEngine -> KnowledgeExplainEngine

It converts relationships *already present* in the index into immutable,
human-readable Explanation objects built from fixed string templates filled with
verified facts. It explains — it never predicts, learns, infers missing facts,
repairs broken references, or uses AI/LLM/NLG. It mutates nothing.

Boundary (frozen, certifiable by grep — zero hits expected): no json, no open(),
no IndexStore, no filesystem, no network, no random, no wall-clock, no
persistence, no mutation. The engine answers only by calling its internal
KnowledgeQueryEngine and reading the frozen models. The Query Engine never
depends on this module (no circular dependency).

Determinism: identical KnowledgeIndex in -> identical Explanation JSON out, every
call. All ordering is stable (query-layer order for events; the Reference
Ordering Contract for references).
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from query_engine import KnowledgeQueryEngine  # noqa: E402
import query_models as qm  # noqa: E402
import explain_models as em  # noqa: E402


class KnowledgeExplainEngine:
    """Deterministic, side-effect-free explanation interface over one KnowledgeIndex."""

    def __init__(self, index) -> None:
        self._q = KnowledgeQueryEngine(index)

    # ------------------------------------------------------------------ #
    # private helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _refs(pairs):
        """Dedupe + order references per the Reference Ordering Contract:
        category order run -> style -> version -> audit -> session, id-sorted
        within each category. `pairs` is an iterable of (category, id) with
        id never None."""
        order = {c: i for i, c in enumerate(em.REF_CATEGORY_ORDER)}
        seen = set()
        cleaned = []
        for category, ident in pairs:
            if ident is None or category not in order:
                continue
            ref = f"{category}:{ident}"
            if ref not in seen:
                seen.add(ref)
                cleaned.append((order[category], str(ident), ref))
        cleaned.sort(key=lambda t: (t[0], t[1]))
        return tuple(t[2] for t in cleaned)

    @staticmethod
    def _explanation(explanation_type, title, summary, supporting_events, references,
                     present_names, expected_names):
        return em.Explanation(
            schema_version=em.EXPLANATION_SCHEMA_VERSION,
            explanation_type=explanation_type,
            title=title,
            summary=summary,
            supporting_events=tuple(supporting_events),
            references=references,
            confidence=em.Confidence.of(present_names, expected_names),
        )

    @staticmethod
    def _parse_version_id(version_id):
        """`"{style_id}:{version}"` -> (style_id, version:int) or None. Splits on
        the LAST colon; version must be an integer."""
        if not isinstance(version_id, str) or ":" not in version_id:
            return None
        style_id, _, raw = version_id.rpartition(":")
        if not style_id:
            return None
        try:
            return style_id, int(raw)
        except ValueError:
            return None

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #

    def explain_run(self, run_id):
        res = self._q.trace_run(run_id)
        if isinstance(res, qm.RunNotFound):
            return em.RunNotFound(run_id)
        if isinstance(res, qm.BrokenReference):
            return em.BrokenReference(res.reference, res.detail)

        links = {"replay": res.replay, "feedback": res.feedback,
                 "audit": res.audit, "style_version": res.style_version}
        present = [k for k, v in links.items() if v is not None]
        if not present:
            return em.MissingEvidence(run_id, ("replay", "feedback", "audit", "style_version"))

        supporting = [links[k] for k in ("replay", "feedback", "audit", "style_version")
                      if links[k] is not None]
        refs = self._refs([
            ("run", res.run_id), ("style", res.style_id), ("session", res.session_id),
            ("audit", res.audit.get("metadata", {}).get("audit_id") if res.audit else None),
        ])
        summary = (
            f"Run {run_id} on style {res.style_id or 'unknown'} "
            f"recorded decision {res.decision or 'none'} "
            f"(session {res.session_id or 'none'}, asset {res.asset_hash or 'none'}). "
            f"Evidence present: {', '.join(present)}."
        )
        return self._explanation(
            em.EXPLANATION_RUN, f"Run {run_id}", summary, supporting, refs,
            present, ("replay", "feedback", "audit", "style_version"))

    def explain_style(self, style_id):
        res = self._q.explain_style(style_id)
        if isinstance(res, qm.StyleNotFound):
            return em.StyleNotFound(style_id)

        present = []
        if res.versions:
            present.append("versions")
        if res.events:
            present.append("events")
        if res.decisions:
            present.append("decisions")
        refs = self._refs(
            [("style", style_id)]
            + [("version", f"{style_id}:{v.get('version')}") for v in res.versions]
        )
        summary = (
            f"Style {style_id} has {res.version_count} version(s), "
            f"currently at version {res.current_version}. "
            f"Decisions observed: {', '.join(res.decisions) if res.decisions else 'none'}. "
            f"First seen {res.first_seen}, last updated {res.last_updated}."
        )
        return self._explanation(
            em.EXPLANATION_STYLE, f"Style {style_id}", summary,
            [e.to_dict() for e in res.events], refs,
            present, ("versions", "events", "decisions"))

    def explain_version(self, version_id):
        parsed = self._parse_version_id(version_id)
        if parsed is None:
            return em.ExplanationUnavailable(str(version_id), "malformed version_id (expected 'style:version')")
        style_id, version = parsed

        res = self._q.why_was_style_changed(style_id, version)
        if isinstance(res, qm.StyleNotFound):
            return em.StyleNotFound(style_id)
        if isinstance(res, qm.VersionNotFound):
            return em.ExplanationUnavailable(version_id, f"version {version} not found for style {style_id}")
        if isinstance(res, qm.BrokenReference):
            return em.BrokenReference(res.reference, res.detail)

        present = []
        if res.audit_reason is not None:
            present.append("audit_reason")
        if res.feedback_summary:
            present.append("feedback_summary")
        if res.metrics:
            present.append("metrics")
        refs = self._refs([("style", style_id), ("version", f"{style_id}:{version}")])
        summary = (
            f"Style {style_id} reached version {version} "
            f"(previous {res.previous_version}, current {res.current_version}); "
            f"reason: {res.audit_reason or 'no recorded reason'}."
        )
        return self._explanation(
            em.EXPLANATION_VERSION, f"Version {version_id}", summary, [], refs,
            present, ("audit_reason", "feedback_summary", "metrics"))

    def explain_learning_chain(self, style_id):
        res = self._q.explain_style(style_id)
        if isinstance(res, qm.StyleNotFound):
            return em.StyleNotFound(style_id)

        version_events = [e for e in res.events
                          if e.event_type == "STYLE_VERSION_CREATED" and e.run_id]
        if not version_events:
            return em.MissingEvidence(style_id, ("learning_chain",))

        supporting = []
        ref_pairs = [("style", style_id)]
        present_total = 0
        expected_total = 0
        for ev in version_events:
            chain = self._q.find_learning_chain(ev.run_id)
            if isinstance(chain, qm.RunNotFound):
                continue
            links = {"replay": chain.replay, "feedback": chain.feedback,
                     "audit": chain.audit, "version": chain.version}
            for k in ("replay", "feedback", "audit", "version"):
                expected_total += 1
                if links[k] is not None:
                    present_total += 1
                    supporting.append(links[k])
            ref_pairs.append(("run", ev.run_id))
            if ev.style_version is not None:
                ref_pairs.append(("version", f"{style_id}:{ev.style_version}"))

        if not supporting:
            return em.MissingEvidence(style_id, ("learning_chain",))

        refs = self._refs(ref_pairs)
        summary = (
            f"Style {style_id} learning chain spans {len(version_events)} version transition(s); "
            f"{present_total} of {expected_total} chain link(s) present across replay/feedback/audit/version."
        )
        # confidence over aggregate link completeness across the whole chain
        present_names = tuple(f"link_{i}" for i in range(present_total))
        expected_names = tuple(f"link_{i}" for i in range(expected_total))
        return self._explanation(
            em.EXPLANATION_LEARNING_CHAIN, f"Learning chain for {style_id}", summary,
            supporting, refs, present_names, expected_names)

    def explain_rollback(self, version_id):
        parsed = self._parse_version_id(version_id)
        if parsed is None:
            return em.ExplanationUnavailable(str(version_id), "malformed version_id (expected 'style:version')")
        style_id, _version = parsed

        style_res = self._q.explain_style(style_id)
        if isinstance(style_res, qm.StyleNotFound):
            return em.StyleNotFound(style_id)

        rb = self._q.list_rollbacks(style_id)
        if not rb.rollbacks:
            return em.MissingEvidence(version_id, ("rollback",))

        # reasons come from the ROLLBACK audit events on the style's timeline
        reasons = []
        ref_pairs = [("style", style_id), ("version", version_id)]
        for entry in rb.rollbacks:
            ref_pairs.append(("run", entry.get("run_id")))
        for e in style_res.events:
            if e.decision == "ROLLBACK":
                reasons.append(e.metadata.get("reason"))
        present = ["rollback_event"]
        if any(r for r in reasons):
            present.append("reason")
        refs = self._refs(ref_pairs)
        reason_text = next((r for r in reasons if r), "no recorded reason")
        summary = (
            f"Style {style_id} has {len(rb.rollbacks)} recorded rollback(s); "
            f"reason: {reason_text}."
        )
        return self._explanation(
            em.EXPLANATION_ROLLBACK, f"Rollback for {version_id}", summary,
            [dict(r) for r in rb.rollbacks], refs,
            present, ("rollback_event", "reason"))

    def summarize_learning(self, style_id):
        res = self._q.summarize_style_history(style_id)
        if isinstance(res, qm.StyleNotFound):
            return em.StyleNotFound(style_id)

        present = []
        if res.decision_distribution:
            present.append("decisions")
        if res.quality_trend or res.retention_trend:
            present.append("trends")
        dist = ", ".join(f"{k}={v}" for k, v in sorted(res.decision_distribution.items())) or "none"
        refs = self._refs([("style", style_id)])
        summary = (
            f"Style {style_id}: {res.version_count} version(s), "
            f"timeline depth {res.timeline_depth}, {res.rollback_count} rollback(s). "
            f"Decisions: {dist}. "
            f"Quality points: {len(res.quality_trend)}, retention points: {len(res.retention_trend)}."
        )
        return self._explanation(
            em.EXPLANATION_SUMMARY, f"Learning summary for {style_id}", summary, [], refs,
            present, ("decisions", "trends"))
