"""Append-only local persistence for Stage 8J commercial acceptance evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .hvs_commercial_acceptance_models import (
    COMMERCIAL_ACCEPTANCE_EVENT_SCHEMA_VERSION,
    EVT_COMMERCIAL_ACCEPTANCE_VERIFIED,
    EVT_CUSTOMER_DECISION_RECORDED,
    EVT_PROPOSAL_PRESENTATION_RECORDED,
    CommercialAcceptanceEvent,
)
from .hvs_commercial_proposal_models import _safe_text, stable_id
from .hvs_customer_outcome_models import validate_calendar_date
from .hvs_local_delivery_service import _runtime_root


_ALLOWED_EVENT_TYPES = frozenset((
    EVT_PROPOSAL_PRESENTATION_RECORDED,
    EVT_CUSTOMER_DECISION_RECORDED,
    EVT_COMMERCIAL_ACCEPTANCE_VERIFIED,
))


def commercial_acceptance_path(repo_root: Any) -> Path:
    return _runtime_root(Path(repo_root)) / "hvs_commercial_acceptance.jsonl"


def _validate_path(path: Any) -> Path:
    value = Path(path)
    text = str(value)
    if ".." in value.parts or "://" in text or "\x00" in text:
        raise ValueError("unsafe commercial acceptance store path")
    return value


def _validate_event(event: CommercialAcceptanceEvent) -> None:
    if event.schema_version != COMMERCIAL_ACCEPTANCE_EVENT_SCHEMA_VERSION:
        raise ValueError("commercial acceptance event schema version mismatch")
    if event.event_type not in _ALLOWED_EVENT_TYPES:
        raise ValueError("unsupported commercial acceptance event type")
    for field in ("event_id", "subject_id", "operator_id"):
        _safe_text(field, getattr(event, field))
    validate_calendar_date("recorded_at", event.recorded_at)
    if not isinstance(event.record, dict):
        raise ValueError("commercial acceptance event record must be a dict")


def read_commercial_acceptance_events(*, audit_log_path: Any) -> tuple[CommercialAcceptanceEvent, ...]:
    path = _validate_path(audit_log_path)
    if not path.is_file():
        return ()
    events: list[CommercialAcceptanceEvent] = []
    seen: set[str] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = CommercialAcceptanceEvent(**json.loads(line))
            _validate_event(event)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"malformed commercial acceptance event at line {number}") from exc
        if event.event_id in seen:
            raise ValueError("conflicting commercial acceptance event")
        seen.add(event.event_id)
        events.append(event)
    return tuple(events)


def append_commercial_acceptance_event(
    *,
    audit_log_path: Any,
    event_type: str,
    subject_id: str,
    operator_id: str,
    recorded_at: str,
    record: dict[str, Any],
) -> CommercialAcceptanceEvent:
    event = CommercialAcceptanceEvent(
        COMMERCIAL_ACCEPTANCE_EVENT_SCHEMA_VERSION,
        stable_id("scos-hvs-commercial-acceptance-event", {"event_type": event_type, "subject_id": subject_id, "record": record}),
        event_type,
        subject_id,
        operator_id,
        recorded_at,
        record,
    )
    _validate_event(event)
    for existing in read_commercial_acceptance_events(audit_log_path=audit_log_path):
        if existing.event_id == event.event_id:
            if existing.to_dict() == event.to_dict():
                return existing
            raise ValueError("conflicting commercial acceptance event")
    path = _validate_path(audit_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    return event
