"""Append-only local persistence for Stage 8I proposal evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .hvs_commercial_proposal_models import (
    CommercialProposalEvent,
    COMMERCIAL_PROPOSAL_EVENT_SCHEMA_VERSION,
    EVT_MANUAL_HANDOFF_CREATED,
    EVT_PROPOSAL_APPROVED,
    EVT_PROPOSAL_CANCELLED,
    EVT_PROPOSAL_PREPARED,
    EVT_PROPOSAL_REJECTED,
    EVT_PROPOSAL_SUBMITTED,
    _safe_text,
    stable_id,
)
from .hvs_customer_outcome_models import validate_calendar_date
from .hvs_local_delivery_service import _runtime_root


_ALLOWED_EVENT_TYPES = frozenset((
    EVT_PROPOSAL_PREPARED,
    EVT_PROPOSAL_SUBMITTED,
    EVT_PROPOSAL_APPROVED,
    EVT_PROPOSAL_REJECTED,
    EVT_PROPOSAL_CANCELLED,
    EVT_MANUAL_HANDOFF_CREATED,
))


def _validate_event(event: CommercialProposalEvent) -> None:
    if event.schema_version != COMMERCIAL_PROPOSAL_EVENT_SCHEMA_VERSION:
        raise ValueError("commercial proposal event schema version mismatch")
    if event.event_type not in _ALLOWED_EVENT_TYPES:
        raise ValueError("unsupported commercial proposal event type")
    for field in ("event_id", "subject_id", "operator_id"):
        _safe_text(field, getattr(event, field))
    validate_calendar_date("recorded_at", event.recorded_at)
    if not isinstance(event.record, dict):
        raise ValueError("commercial proposal event record must be a dict")


def commercial_proposal_path(repo_root: Any) -> Path:
    return _runtime_root(Path(repo_root)) / "hvs_commercial_proposals.jsonl"


def read_commercial_proposal_events(*, audit_log_path: Any) -> tuple[CommercialProposalEvent, ...]:
    path = Path(audit_log_path)
    if ".." in path.parts or "://" in str(path) or "\x00" in str(path):
        raise ValueError("unsafe commercial proposal store path")
    if not path.is_file():
        return ()
    events, seen = [], set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = CommercialProposalEvent(**json.loads(line))
            _validate_event(event)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"malformed commercial proposal event at line {number}") from exc
        if event.schema_version != COMMERCIAL_PROPOSAL_EVENT_SCHEMA_VERSION or event.event_id in seen:
            raise ValueError("conflicting commercial proposal event")
        seen.add(event.event_id); events.append(event)
    return tuple(events)


def append_commercial_proposal_event(*, audit_log_path: Any, event_type: str, subject_id: str, operator_id: str, recorded_at: str, record: dict[str, Any]) -> CommercialProposalEvent:
    event = CommercialProposalEvent(COMMERCIAL_PROPOSAL_EVENT_SCHEMA_VERSION, stable_id("scos-hvs-commercial-proposal-event", {"event_type": event_type, "subject_id": subject_id, "record": record}), event_type, subject_id, operator_id, recorded_at, record)
    _validate_event(event)
    for existing in read_commercial_proposal_events(audit_log_path=audit_log_path):
        if existing.event_id == event.event_id:
            if existing.to_dict() == event.to_dict(): return existing
            raise ValueError("conflicting commercial proposal event")
    path = Path(audit_log_path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    return event
