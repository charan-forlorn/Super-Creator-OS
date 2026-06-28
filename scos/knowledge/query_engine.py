"""SCOS Stage 3.6 — Knowledge Query Engine.

A deterministic, read-only navigation layer over a *certified* Stage 3.5
KnowledgeIndex. Think "git log / git blame / git show" for SCOS learning
history: it explains what already happened, but never creates, scores, ranks,
predicts, persists, or mutates knowledge.

Boundary (frozen, certifiable by grep — zero hits expected):
no json, no open(), no IndexStore, no filesystem, no network, no global state,
no wall-clock, no random, no caching, no mutation of the index. The engine reads
ONLY the in-memory KnowledgeIndex passed to its constructor, plus the frozen
model classes. It deliberately does NOT import the Stage 3.5 query.py (that
module imports IndexStore) — the few pure scans needed are re-expressed here
directly over index.events.

Determinism: identical KnowledgeIndex in -> identical results out, every call.
Every returned list is sorted by a single stable key (`_sort_key`), never by
dict / JSON / set iteration order.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from knowledge_models import (  # noqa: E402
    KnowledgeIndex,
    SOURCE_LEARNING_AUDIT, SOURCE_FEEDBACK_LOG, SOURCE_STYLE_HISTORY, SOURCE_REPLAY_REPORT,
    EVENT_LEARNING_DECISION, EVENT_FEEDBACK_RECORDED, EVENT_STYLE_VERSION_CREATED,
    EVENT_REPLAY_RECORD, DECISION_ROLLBACK,
)
from query_models import (  # noqa: E402
    StyleSummary, ExplainStyleResult, FieldChange, CompareVersionsResult,
    RunTraceResult, StyleChangeExplanation, RollbackHistory, RelatedEvents,
    LearningChain, StyleNotFound, RunNotFound, VersionNotFound, BrokenReference,
    InvalidComparison,
)

_QUALITY_KEY = "quality_score"
_RETENTION_KEY = "retention_score"


def _sort_key(e):
    """The single stable ordering for every event-bearing result. Never depends
    on dict / JSON / set ordering — only on the event's own recorded fields."""
    return (
        e.timestamp if e.timestamp is not None else -1,
        e.source,
        e.event_type,
        e.run_id or "",
        e.style_version if e.style_version is not None else -1,
    )


class KnowledgeQueryEngine:
    """Deterministic, side-effect-free query interface over one KnowledgeIndex."""

    def __init__(self, index: KnowledgeIndex) -> None:
        self._index = index

    # ------------------------------------------------------------------ #
    # private deterministic helpers (pure reads of the index)
    # ------------------------------------------------------------------ #

    def _events_for_run(self, run_id):
        return sorted((e for e in self._index.events if e.run_id == run_id), key=_sort_key)

    def _run_exists(self, run_id) -> bool:
        if run_id in self._index.replay_map:
            return True
        return any(e.run_id == run_id for e in self._index.events)

    def _timeline_for_run(self, run_id):
        """The (style_id, timeline) that owns this run, via the run's style-
        version event, else any timeline whose events reference the run."""
        for style_id, tl in sorted(self._index.timeline.items()):
            for e in tl.events:
                if e.run_id == run_id:
                    return style_id, tl
        return None, None

    @staticmethod
    def _pick(events, event_type):
        for e in events:  # `events` is already _sort_key-ordered
            if e.event_type == event_type:
                return e
        return None

    @staticmethod
    def _snapshot(tl, version):
        for snap in tl.versions:
            if snap.get("version") == version:
                return snap
        return None

    @staticmethod
    def _event_link(e):
        """A compact, deterministic dict view of one event for a chain/trace link."""
        if e is None:
            return None
        return e.to_dict()

    def _broken_audit_ids(self):
        """audit_ids the index flagged as unresolved ('does not resolve')."""
        return {
            i.record_ref for i in self._index.validation_issues
            if "does not resolve" in i.message and i.record_ref is not None
        }

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #

    def explain_style(self, style_id):
        tl = self._index.timeline.get(style_id)
        if tl is None:
            return StyleNotFound(style_id)

        events = sorted(tl.events, key=_sort_key)
        timestamps = [e.timestamp for e in events if e.timestamp is not None]
        decisions = []
        for e in events:
            if e.decision is not None and e.decision not in decisions:
                decisions.append(e.decision)

        return ExplainStyleResult(
            style_id=style_id,
            current_version=tl.current_version,
            version_count=len(tl.versions),
            first_seen=min(timestamps) if timestamps else None,
            last_updated=max(timestamps) if timestamps else None,
            versions=tuple(dict(v) for v in tl.versions),
            decisions=tuple(decisions),
            events=tuple(events),
            summary=self.summarize_style_history(style_id),
        )

    def compare_versions(self, style_id, from_version, to_version):
        tl = self._index.timeline.get(style_id)
        if tl is None:
            return StyleNotFound(style_id)
        from_snap = self._snapshot(tl, from_version)
        if from_snap is None:
            return VersionNotFound(style_id, from_version)
        to_snap = self._snapshot(tl, to_version)
        if to_snap is None:
            return VersionNotFound(style_id, to_version)
        if from_version == to_version:
            return InvalidComparison(style_id, from_version, to_version, "identical versions")

        from_profile = from_snap.get("profile") or {}
        to_profile = to_snap.get("profile") or {}
        changes = []
        for field in sorted(set(from_profile) | set(to_profile)):
            in_from, in_to = field in from_profile, field in to_profile
            fv, tv = from_profile.get(field), to_profile.get(field)
            if in_from and not in_to:
                changes.append(FieldChange(field, "removed", fv, None))
            elif in_to and not in_from:
                changes.append(FieldChange(field, "added", None, tv))
            elif fv != tv:
                changes.append(FieldChange(field, "modified", fv, tv))

        # decision for the to-version comes from its style-version event (if any)
        decision = None
        for e in tl.events:
            if e.event_type == EVENT_STYLE_VERSION_CREATED and e.style_version == to_version:
                decision = e.decision
                break

        return CompareVersionsResult(
            style_id=style_id,
            from_version=from_version,
            to_version=to_version,
            changes=tuple(changes),
            audit_id=to_snap.get("audit_id"),
            decision=decision,
            timestamp=to_snap.get("timestamp"),
        )

    def trace_run(self, run_id):
        if not self._run_exists(run_id):
            return RunNotFound(run_id)

        events = self._events_for_run(run_id)
        replay_ev = self._pick(events, EVENT_REPLAY_RECORD)
        feedback_ev = self._pick(events, EVENT_FEEDBACK_RECORDED)
        audit_ev = self._pick(events, EVENT_LEARNING_DECISION)
        version_ev = self._pick(events, EVENT_STYLE_VERSION_CREATED)

        # broken reference: this run's style-version snapshot points at an
        # audit_id the index could not resolve.
        if version_ev is not None:
            aid = version_ev.metadata.get("audit_id")
            if aid in self._broken_audit_ids():
                return BrokenReference(aid, f"audit_id does not resolve (run {run_id})")

        style_id, tl = self._timeline_for_run(run_id)
        replay_meta = self._index.replay_map.get(run_id)
        session_id = None
        for e in events:
            if e.session_id:
                session_id = e.session_id
                break
        if session_id is None and replay_meta:
            session_id = replay_meta.get("session_id")

        decision = None
        if audit_ev is not None:
            decision = audit_ev.decision
        elif replay_ev is not None:
            decision = replay_ev.decision

        return RunTraceResult(
            run_id=run_id,
            session_id=session_id,
            asset_hash=self._index.asset_map.get(run_id),
            style_id=style_id,
            current_version=tl.current_version if tl is not None else None,
            decision=decision,
            replay=self._event_link(replay_ev),
            feedback=self._event_link(feedback_ev),
            audit=self._event_link(audit_ev),
            style_version=self._event_link(version_ev),
            timeline_ref=({"style_id": style_id, "current_version": tl.current_version}
                          if tl is not None else None),
        )

    def why_was_style_changed(self, style_id, version):
        tl = self._index.timeline.get(style_id)
        if tl is None:
            return StyleNotFound(style_id)
        snap = self._snapshot(tl, version)
        if snap is None:
            return VersionNotFound(style_id, version)

        # A version whose recorded audit_id did not resolve is a broken
        # reference — distinct from a seed version that legitimately has none.
        snap_audit = snap.get("audit_id")
        if snap_audit and snap_audit != "seed" and snap_audit in self._broken_audit_ids():
            return BrokenReference(
                snap_audit, f"audit_id does not resolve ({style_id} v{version})")

        version_ev = None
        for e in tl.events:
            if e.event_type == EVENT_STYLE_VERSION_CREATED and e.style_version == version:
                version_ev = e
                break

        audit_reason = None
        metrics = {}
        feedback_summary = {}
        run_id = version_ev.run_id if version_ev is not None else None
        if run_id:
            run_events = self._events_for_run(run_id)
            audit_ev = self._pick(run_events, EVENT_LEARNING_DECISION)
            feedback_ev = self._pick(run_events, EVENT_FEEDBACK_RECORDED)
            if audit_ev is not None:
                audit_reason = audit_ev.metadata.get("reason")
                metrics = dict(audit_ev.metrics)
            if feedback_ev is not None:
                feedback_summary = dict(feedback_ev.metrics)

        prev_snap = self._snapshot(tl, version - 1)
        return StyleChangeExplanation(
            style_id=style_id,
            version=version,
            previous_version=(prev_snap.get("version") if prev_snap is not None else None),
            current_version=tl.current_version,
            audit_reason=audit_reason,
            feedback_summary=feedback_summary,
            metrics=metrics,
        )

    def list_rollbacks(self, style_id=None):
        if style_id is not None:
            tl = self._index.timeline.get(style_id)
            source_events = tl.events if tl is not None else ()
        else:
            source_events = self._index.events

        rollbacks = []
        for e in sorted(source_events, key=_sort_key):
            if e.decision == DECISION_ROLLBACK:
                sid = style_id if style_id is not None else e.metadata.get("style_id")
                rollbacks.append({
                    "timestamp": e.timestamp,
                    "run_id": e.run_id,
                    "style_id": sid,
                    "decision": e.decision,
                })
        return RollbackHistory(style_id=style_id, rollbacks=tuple(rollbacks))

    def find_related_events(self, run_id):
        if not self._run_exists(run_id):
            return RunNotFound(run_id)

        seed = self._events_for_run(run_id)
        run_ids = {run_id}
        audit_ids = set()
        style_ids = set()
        session_ids = set()
        for e in seed:
            if e.run_id:
                run_ids.add(e.run_id)
            aid = e.metadata.get("audit_id")
            if aid and aid != "seed":
                audit_ids.add(aid)
            if e.session_id:
                session_ids.add(e.session_id)
        # style ownership of the seed run
        sid_owner, _ = self._timeline_for_run(run_id)
        if sid_owner:
            style_ids.add(sid_owner)

        related = []
        seen = set()
        for e in self._index.events:
            owner_in_scope = any(
                e in tl.events for s, tl in self._index.timeline.items() if s in style_ids
            )
            shares = (
                (e.run_id in run_ids and e.run_id is not None)
                or (e.metadata.get("audit_id") in audit_ids)
                or (e.session_id in session_ids and e.session_id is not None)
                or owner_in_scope
            )
            if shares:
                key = _sort_key(e)
                if key not in seen:
                    seen.add(key)
                    related.append(e)
        related.sort(key=_sort_key)
        return RelatedEvents(run_id=run_id, events=tuple(related))

    def find_learning_chain(self, run_id):
        if not self._run_exists(run_id):
            return RunNotFound(run_id)

        events = self._events_for_run(run_id)
        replay_ev = self._pick(events, EVENT_REPLAY_RECORD)
        feedback_ev = self._pick(events, EVENT_FEEDBACK_RECORDED)
        audit_ev = self._pick(events, EVENT_LEARNING_DECISION)
        version_ev = self._pick(events, EVENT_STYLE_VERSION_CREATED)

        style_id, tl = self._timeline_for_run(run_id)
        timeline_ref = None
        current_style = None
        if tl is not None:
            timeline_ref = {"style_id": style_id, "current_version": tl.current_version}
            cur_snap = self._snapshot(tl, tl.current_version)
            if cur_snap is not None:
                current_style = dict(cur_snap)

        return LearningChain(
            run_id=run_id,
            replay=self._event_link(replay_ev),
            feedback=self._event_link(feedback_ev),
            audit=self._event_link(audit_ev),
            version=self._event_link(version_ev),
            timeline_ref=timeline_ref,
            current_style=current_style,
        )

    def summarize_style_history(self, style_id):
        tl = self._index.timeline.get(style_id)
        if tl is None:
            return StyleNotFound(style_id)

        events = sorted(tl.events, key=_sort_key)
        timestamps = [e.timestamp for e in events if e.timestamp is not None]
        decision_distribution = {}
        rollback_count = 0
        quality_trend = []
        retention_trend = []
        for e in events:
            if e.decision is not None:
                decision_distribution[e.decision] = decision_distribution.get(e.decision, 0) + 1
                if e.decision == DECISION_ROLLBACK:
                    rollback_count += 1
            q = e.metrics.get(_QUALITY_KEY)
            if q is not None:
                quality_trend.append((e.timestamp, q))
            r = e.metrics.get(_RETENTION_KEY)
            if r is not None:
                retention_trend.append((e.timestamp, r))

        return StyleSummary(
            style_id=style_id,
            version_count=len(tl.versions),
            current_version=tl.current_version,
            timeline_depth=len(tl.versions),
            first_timestamp=min(timestamps) if timestamps else None,
            last_timestamp=max(timestamps) if timestamps else None,
            rollback_count=rollback_count,
            decision_distribution=decision_distribution,
            quality_trend=tuple(quality_trend),
            retention_trend=tuple(retention_trend),
        )
