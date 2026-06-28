"""SCOS Stage 3.5 — Learning Knowledge Index builder (LearningKnowledgeIndex).

Scans the 4 existing learning artifacts (replay_report.json, learning_audit.json,
feedback_log.json, style_history.json) and builds one read-only, deterministic
KnowledgeIndex. Never mutates a source file or any certified module's state.
Never learns, scores, or repairs corrupted data — only indexes and reports.

Failure policy: a missing source file is not an error (indexing continues with
the other 3). An unreadable/malformed source file is a validation issue for
that source only — the other sources still index. A single corrupted record
inside an otherwise-valid source is isolated (skipped + reported); it never
aborts the rest of that source or any other source.

Build order matches the user-specified pipeline: Replay -> Audit -> Feedback ->
Style History -> Knowledge Index. Replay is parsed first so its run_id/session_id
map is available to backfill session_id/replay_id onto audit and feedback events.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from knowledge_models import (  # noqa: E402
    INDEX_VERSION, SCHEMA_VERSION,
    SOURCE_FEEDBACK_LOG, SOURCE_LEARNING_AUDIT, SOURCE_STYLE_HISTORY, SOURCE_REPLAY_REPORT,
    EVENT_FEEDBACK_RECORDED, EVENT_LEARNING_DECISION, EVENT_STYLE_VERSION_CREATED,
    EVENT_REPLAY_RECORD, DECISION_ROLLBACK,
    KnowledgeIndex, LearningEvent, ValidationIssue,
)
from timeline import build_timeline  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_FEEDBACK_LOG = _REPO_ROOT / "scos" / "work" / "analytics" / "feedback_log.json"
_DEFAULT_LEARNING_AUDIT = _REPO_ROOT / "scos" / "work" / "learning" / "learning_audit.json"
_DEFAULT_STYLE_HISTORY = _REPO_ROOT / "scos" / "work" / "learning" / "style_history.json"
_DEFAULT_REPLAY_REPORT = _REPO_ROOT / "scos" / "work" / "replay" / "replay_report.json"

_FEEDBACK_SCORE_KEYS = ("retention_score", "engagement_score", "style_match_score", "quality_score")


def _read_json(path: Path):
    """Returns (data, error_or_None, existed_bool). Never raises."""
    if not path.exists():
        return None, None, False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data, None, True
    except (OSError, ValueError) as exc:
        return None, str(exc), True


def _count_by_source(issues: list) -> dict:
    out: dict = {}
    for i in issues:
        out[i.source] = out.get(i.source, 0) + 1
    return out


class LearningKnowledgeIndex:
    """Builder: scan -> validate -> build. Stateless across calls (re-reads sources
    every time); the only side effect of build() is handing the result to an
    IndexStore for persistence (caller-supplied, see query.py)."""

    def __init__(
        self,
        feedback_log_path: Path | str = _DEFAULT_FEEDBACK_LOG,
        learning_audit_path: Path | str = _DEFAULT_LEARNING_AUDIT,
        style_history_path: Path | str = _DEFAULT_STYLE_HISTORY,
        replay_report_path: Path | str = _DEFAULT_REPLAY_REPORT,
    ) -> None:
        self.feedback_log_path = Path(feedback_log_path)
        self.learning_audit_path = Path(learning_audit_path)
        self.style_history_path = Path(style_history_path)
        self.replay_report_path = Path(replay_report_path)

    def build(self, now_fn=time.time) -> KnowledgeIndex:
        issues: list[ValidationIssue] = []
        sources_missing: list[str] = []
        sources_hashed: list[str] = []
        hash_parts: list[bytes] = []
        total_records_seen = 0

        # ----------------------------------------------------------------- #
        # 1. replay_report.json — parsed first so run_id -> session_id is
        #    available to every later source.
        # ----------------------------------------------------------------- #
        replay_data, replay_err, replay_existed = _read_json(self.replay_report_path)
        if replay_existed:
            sources_hashed.append(SOURCE_REPLAY_REPORT)
            hash_parts.append(self.replay_report_path.read_bytes())
        else:
            sources_missing.append(SOURCE_REPLAY_REPORT)
        if replay_err:
            issues.append(ValidationIssue(SOURCE_REPLAY_REPORT, f"unreadable: {replay_err}", None))
            replay_data = None

        replay_map: dict = {}
        asset_map: dict = {}
        replay_events: list[LearningEvent] = []
        if isinstance(replay_data, dict):
            top_session = replay_data.get("session_id")
            results = replay_data.get("results")
            if isinstance(results, list):
                for i, r in enumerate(results):
                    total_records_seen += 1
                    if not isinstance(r, dict) or not r.get("run_id"):
                        issues.append(ValidationIssue(
                            SOURCE_REPLAY_REPORT, "result missing run_id", f"index {i}"))
                        continue
                    run_id = r["run_id"]
                    session_id = r.get("session_id") or top_session
                    replay_map[run_id] = {
                        "session_id": session_id,
                        "record_id": r.get("record_id"),
                        "decision": r.get("decision"),
                        "quality_score": r.get("quality_score"),
                        "timestamp": r.get("timestamp"),
                    }
                    if r.get("asset_hash"):
                        asset_map[run_id] = r["asset_hash"]
                    replay_events.append(LearningEvent(
                        run_id=run_id, session_id=session_id, replay_id=session_id,
                        timestamp=r.get("timestamp"), style_version=None,
                        event_type=EVENT_REPLAY_RECORD, source=SOURCE_REPLAY_REPORT,
                        metrics={"quality_score": r.get("quality_score")},
                        decision=r.get("decision"), rollback=False, confidence=None,
                        metadata={"record_id": r.get("record_id"), "error": r.get("error"),
                                 "asset_hash": r.get("asset_hash")},
                    ))
            elif results is not None:
                issues.append(ValidationIssue(SOURCE_REPLAY_REPORT, "results is not a list", None))
        elif replay_data is not None:
            issues.append(ValidationIssue(SOURCE_REPLAY_REPORT, "report is not an object", None))

        # ----------------------------------------------------------------- #
        # 2. learning_audit.json
        # ----------------------------------------------------------------- #
        audit_data, audit_err, audit_existed = _read_json(self.learning_audit_path)
        if audit_existed:
            sources_hashed.append(SOURCE_LEARNING_AUDIT)
            hash_parts.append(self.learning_audit_path.read_bytes())
        else:
            sources_missing.append(SOURCE_LEARNING_AUDIT)
        if audit_err:
            issues.append(ValidationIssue(SOURCE_LEARNING_AUDIT, f"unreadable: {audit_err}", None))
            audit_data = None

        audit_events: list[LearningEvent] = []
        audit_id_to_event: dict = {}
        audit_id_to_style: dict = {}
        run_id_to_timestamp: dict = {}
        seen_audit_ids: set = set()
        decision_counts: dict = {}
        if isinstance(audit_data, list):
            for i, entry in enumerate(audit_data):
                total_records_seen += 1
                if not isinstance(entry, dict):
                    issues.append(ValidationIssue(
                        SOURCE_LEARNING_AUDIT, "entry is not an object", f"index {i}"))
                    continue
                audit_id = entry.get("audit_id")
                decision = entry.get("decision")
                ts = entry.get("timestamp")
                if not audit_id or not decision or not isinstance(ts, (int, float)):
                    issues.append(ValidationIssue(
                        SOURCE_LEARNING_AUDIT, "missing required field(s)", audit_id))
                    continue
                if audit_id in seen_audit_ids:
                    issues.append(ValidationIssue(
                        SOURCE_LEARNING_AUDIT, "duplicate audit_id", audit_id))
                    continue
                seen_audit_ids.add(audit_id)
                decision_counts[decision] = decision_counts.get(decision, 0) + 1

                style_id = (entry.get("style_after") or entry.get("style_before") or {}).get("style_id")
                feedback_summary = entry.get("feedback_summary") or {}
                run_id = feedback_summary.get("run_id")
                replay_meta = replay_map.get(run_id) if run_id else None
                session_id = replay_meta["session_id"] if replay_meta else None
                if run_id:
                    run_id_to_timestamp[run_id] = ts

                metrics = {k: feedback_summary.get(k) for k in _FEEDBACK_SCORE_KEYS}
                event = LearningEvent(
                    run_id=run_id, session_id=session_id, replay_id=session_id,
                    timestamp=ts, style_version=None,
                    event_type=EVENT_LEARNING_DECISION, source=SOURCE_LEARNING_AUDIT,
                    metrics=metrics, decision=decision, rollback=(decision == DECISION_ROLLBACK),
                    confidence=None,
                    metadata={"reason": entry.get("reason"), "style_id": style_id},
                )
                audit_events.append(event)
                audit_id_to_event[audit_id] = event
                if style_id:
                    audit_id_to_style[audit_id] = style_id
        elif audit_data is not None:
            issues.append(ValidationIssue(SOURCE_LEARNING_AUDIT, "audit log is not a list", None))

        # ----------------------------------------------------------------- #
        # 3. feedback_log.json
        # ----------------------------------------------------------------- #
        feedback_data, feedback_err, feedback_existed = _read_json(self.feedback_log_path)
        if feedback_existed:
            sources_hashed.append(SOURCE_FEEDBACK_LOG)
            hash_parts.append(self.feedback_log_path.read_bytes())
        else:
            sources_missing.append(SOURCE_FEEDBACK_LOG)
        if feedback_err:
            issues.append(ValidationIssue(SOURCE_FEEDBACK_LOG, f"unreadable: {feedback_err}", None))
            feedback_data = None

        feedback_events: list[LearningEvent] = []
        seen_feedback_run_ids: set = set()
        if isinstance(feedback_data, list):
            for i, entry in enumerate(feedback_data):
                total_records_seen += 1
                if not isinstance(entry, dict) or not entry.get("run_id"):
                    issues.append(ValidationIssue(
                        SOURCE_FEEDBACK_LOG, "entry missing run_id", f"index {i}"))
                    continue
                run_id = entry["run_id"]
                if run_id in seen_feedback_run_ids:
                    issues.append(ValidationIssue(SOURCE_FEEDBACK_LOG, "duplicate run_id", run_id))
                    continue
                seen_feedback_run_ids.add(run_id)

                replay_meta = replay_map.get(run_id)
                session_id = replay_meta["session_id"] if replay_meta else None
                ts = run_id_to_timestamp.get(run_id)
                metrics = {k: entry.get(k) for k in _FEEDBACK_SCORE_KEYS}
                derived = entry.get("derived_style_updates") or {}
                feedback_events.append(LearningEvent(
                    run_id=run_id, session_id=session_id, replay_id=session_id,
                    timestamp=ts, style_version=None,
                    event_type=EVENT_FEEDBACK_RECORDED, source=SOURCE_FEEDBACK_LOG,
                    metrics=metrics, decision=None, rollback=False, confidence=None,
                    metadata={"content_type": derived.get("content_type")},
                ))
        elif feedback_data is not None:
            issues.append(ValidationIssue(SOURCE_FEEDBACK_LOG, "feedback log is not a list", None))

        # ----------------------------------------------------------------- #
        # 4. style_history.json
        # ----------------------------------------------------------------- #
        history_data, history_err, history_existed = _read_json(self.style_history_path)
        if history_existed:
            sources_hashed.append(SOURCE_STYLE_HISTORY)
            hash_parts.append(self.style_history_path.read_bytes())
        else:
            sources_missing.append(SOURCE_STYLE_HISTORY)
        if history_err:
            issues.append(ValidationIssue(SOURCE_STYLE_HISTORY, f"unreadable: {history_err}", None))
            history_data = None

        style_events: dict = {}
        style_versions_raw: dict = {}
        if isinstance(history_data, dict):
            for style_id, snaps in history_data.items():
                if not isinstance(snaps, list):
                    total_records_seen += 1
                    issues.append(ValidationIssue(
                        SOURCE_STYLE_HISTORY, "version list is not a list", style_id))
                    continue
                seen_versions: set = set()
                clean_snaps = []
                for snap in snaps:
                    total_records_seen += 1
                    if not isinstance(snap, dict) or "version" not in snap or "audit_id" not in snap:
                        issues.append(ValidationIssue(
                            SOURCE_STYLE_HISTORY, "snapshot missing required field(s)", style_id))
                        continue
                    version = snap["version"]
                    if version in seen_versions:
                        issues.append(ValidationIssue(
                            SOURCE_STYLE_HISTORY, "duplicate version", f"{style_id} v{version}"))
                        continue
                    seen_versions.add(version)
                    clean_snaps.append(snap)

                    audit_id = snap.get("audit_id")
                    is_seed = audit_id == "seed"
                    linked = None if is_seed else audit_id_to_event.get(audit_id)
                    if audit_id and not is_seed and linked is None:
                        issues.append(ValidationIssue(
                            SOURCE_STYLE_HISTORY, "audit_id does not resolve", audit_id))

                    style_events.setdefault(style_id, []).append(LearningEvent(
                        run_id=linked.run_id if linked else None,
                        session_id=linked.session_id if linked else None,
                        replay_id=linked.replay_id if linked else None,
                        timestamp=snap.get("timestamp"), style_version=version,
                        event_type=EVENT_STYLE_VERSION_CREATED, source=SOURCE_STYLE_HISTORY,
                        metrics={}, decision=(linked.decision if linked else None),
                        rollback=False, confidence=None,
                        metadata={"audit_id": audit_id, "seed": is_seed,
                                 "resolved": is_seed or linked is not None},
                    ))
                style_versions_raw[style_id] = clean_snaps
        elif history_data is not None:
            issues.append(ValidationIssue(SOURCE_STYLE_HISTORY, "style history is not an object", None))

        # ----------------------------------------------------------------- #
        # assemble timelines (per style_id, sorted for determinism)
        # ----------------------------------------------------------------- #
        events_by_style: dict = {}
        for aid, e in audit_id_to_event.items():
            sid = audit_id_to_style.get(aid)
            if sid:
                events_by_style.setdefault(sid, []).append(e)
        audit_run_id_to_style = {
            e.run_id: audit_id_to_style[aid]
            for aid, e in audit_id_to_event.items()
            if e.run_id and aid in audit_id_to_style
        }
        for e in feedback_events:
            sid = audit_run_id_to_style.get(e.run_id)
            if sid:
                events_by_style.setdefault(sid, []).append(e)

        all_style_ids = set(style_versions_raw) | set(audit_id_to_style.values())
        timelines = {}
        for style_id in sorted(all_style_ids):
            combined = list(style_events.get(style_id, [])) + list(events_by_style.get(style_id, []))
            timelines[style_id] = build_timeline(
                style_id, style_versions_raw.get(style_id, []), combined)

        # ----------------------------------------------------------------- #
        # flat, fully-ordered event list (never relies on dict/JSON order)
        # ----------------------------------------------------------------- #
        all_events = list(audit_events) + list(feedback_events) + list(replay_events)
        for evs in style_events.values():
            all_events.extend(evs)
        all_events.sort(key=lambda e: (
            e.timestamp if e.timestamp is not None else -1,
            e.source, e.run_id or "", e.event_type,
        ))

        # ----------------------------------------------------------------- #
        # statistics
        # ----------------------------------------------------------------- #
        total_events = len(all_events)
        linked_events = sum(
            1 for e in all_events
            if e.session_id or e.replay_id
            or (e.source == SOURCE_STYLE_HISTORY and e.metadata.get("resolved") is True)
        )
        broken_refs = sum(1 for i in issues if "does not resolve" in i.message)
        orphan = sum(
            1 for e in all_events
            if e.source in (SOURCE_LEARNING_AUDIT, SOURCE_FEEDBACK_LOG)
            and not e.session_id and not e.replay_id
        )
        style_count_events = sum(len(v) for v in style_events.values())
        depths = [len(tl.versions) for tl in timelines.values()]
        rollback_count = decision_counts.get(DECISION_ROLLBACK, 0)
        total_decisions = sum(decision_counts.values())

        statistics = {
            "counts": {
                "events_total": total_events,
                "by_source": {
                    SOURCE_LEARNING_AUDIT: len(audit_events),
                    SOURCE_FEEDBACK_LOG: len(feedback_events),
                    SOURCE_REPLAY_REPORT: len(replay_events),
                    SOURCE_STYLE_HISTORY: style_count_events,
                },
                "by_decision": decision_counts,
                "sources_missing": sorted(sources_missing),
            },
            "errors": {
                "validation_issue_count": len(issues),
                "by_source": _count_by_source(issues),
            },
            "coverage": round(linked_events / total_events, 6) if total_events else 0.0,
            "consistency": (
                round(1.0 - (len(issues) / total_records_seen), 6) if total_records_seen else 1.0
            ),
            "orphan_rate": round(orphan / total_events, 6) if total_events else 0.0,
            "broken_reference_rate": (
                round(broken_refs / total_records_seen, 6) if total_records_seen else 0.0
            ),
            "timeline_depth": {
                "average": round(sum(depths) / len(depths), 6) if depths else 0.0,
                "max": max(depths) if depths else 0,
            },
            "rollback_frequency": {
                "count": rollback_count,
                "fraction": round(rollback_count / total_decisions, 6) if total_decisions else 0.0,
            },
            "style_evolution_count": sum(1 for d in depths if d >= 2),
        }

        # ----------------------------------------------------------------- #
        # metadata (decision #8: travels with the index, independent of clock)
        # ----------------------------------------------------------------- #
        source_hash = hashlib.sha256(b"".join(hash_parts)).hexdigest()
        metadata = {
            "index_version": INDEX_VERSION,
            "schema_version": SCHEMA_VERSION,
            "generated_at": int(now_fn()),
            "source_hash": source_hash,
            "build_id": f"kidx_{source_hash[:16]}",
            "sources_hashed": sorted(sources_hashed),
        }

        return KnowledgeIndex(
            timeline=timelines, events=tuple(all_events),
            replay_map=replay_map, asset_map=asset_map,
            statistics=statistics, metadata=metadata,
            validation_issues=tuple(issues),
        )
