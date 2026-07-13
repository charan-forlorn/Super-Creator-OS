"""Append-only local persistence for Stage 8K engagement activation evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .hvs_commercial_proposal_models import _safe_text, stable_id
from .hvs_customer_outcome_models import validate_calendar_date
from .hvs_engagement_activation_models import (
    ENGAGEMENT_ACTIVATION_EVENT_SCHEMA_VERSION,
    EVT_CUSTOMER_INPUT_CONFIRMED,
    EVT_CUSTOMER_INPUT_REQUIREMENT_ADDED,
    EVT_ENGAGEMENT_ACTIVATION_CREATED,
    EVT_ENGAGEMENT_APPROVED,
    EVT_ENGAGEMENT_CANCELLED,
    EVT_ENGAGEMENT_REJECTED,
    EVT_PAYMENT_READINESS_CONFIRMED,
    EVT_PAYMENT_REQUIREMENT_RECORDED,
    EVT_PRODUCTION_KICKOFF_AUTHORIZATION_CREATED,
    EVT_PRODUCTION_REVIEW_REQUESTED,
    EngagementActivationEvent,
)
from .hvs_local_delivery_service import _runtime_root


_ALLOWED_EVENT_TYPES = frozenset((
    EVT_ENGAGEMENT_ACTIVATION_CREATED,
    EVT_PAYMENT_REQUIREMENT_RECORDED,
    EVT_PAYMENT_READINESS_CONFIRMED,
    EVT_CUSTOMER_INPUT_REQUIREMENT_ADDED,
    EVT_CUSTOMER_INPUT_CONFIRMED,
    EVT_PRODUCTION_REVIEW_REQUESTED,
    EVT_ENGAGEMENT_APPROVED,
    EVT_ENGAGEMENT_REJECTED,
    EVT_ENGAGEMENT_CANCELLED,
    EVT_PRODUCTION_KICKOFF_AUTHORIZATION_CREATED,
))


def engagement_activation_path(repo_root: Any) -> Path:
    return _runtime_root(Path(repo_root)) / "hvs_engagement_activation.jsonl"


def _validate_path(path: Any) -> Path:
    value = Path(path)
    text = str(value)
    if ".." in value.parts or "://" in text or "\x00" in text:
        raise ValueError("unsafe engagement activation store path")
    return value


def _validate_event(event: EngagementActivationEvent) -> None:
    if event.schema_version != ENGAGEMENT_ACTIVATION_EVENT_SCHEMA_VERSION:
        raise ValueError("engagement activation event schema version mismatch")
    if event.event_type not in _ALLOWED_EVENT_TYPES:
        raise ValueError("unsupported engagement activation event type")
    for field in ("event_id", "subject_id", "operator_id"):
        _safe_text(field, getattr(event, field))
    validate_calendar_date("recorded_at", event.recorded_at)
    if not isinstance(event.record, dict):
        raise ValueError("engagement activation event record must be a dict")


def read_engagement_activation_events(*, audit_log_path: Any) -> tuple[EngagementActivationEvent, ...]:
    path = _validate_path(audit_log_path)
    if not path.is_file():
        return ()
    events: list[EngagementActivationEvent] = []
    seen: set[str] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = EngagementActivationEvent(**json.loads(line))
            _validate_event(event)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"malformed engagement activation event at line {number}") from exc
        if event.event_id in seen:
            raise ValueError("conflicting engagement activation event")
        seen.add(event.event_id)
        events.append(event)
    return tuple(events)


def append_engagement_activation_event(
    *,
    audit_log_path: Any,
    event_type: str,
    subject_id: str,
    operator_id: str,
    recorded_at: str,
    record: dict[str, Any],
) -> EngagementActivationEvent:
    event = EngagementActivationEvent(
        ENGAGEMENT_ACTIVATION_EVENT_SCHEMA_VERSION,
        stable_id("scos-hvs-engagement-activation-event", {"event_type": event_type, "subject_id": subject_id, "record": record}),
        event_type,
        subject_id,
        operator_id,
        recorded_at,
        record,
    )
    _validate_event(event)
    for existing in read_engagement_activation_events(audit_log_path=audit_log_path):
        if existing.event_id == event.event_id:
            if existing.to_dict() == event.to_dict():
                return existing
            raise ValueError("conflicting engagement activation event")
    path = _validate_path(audit_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    return event
