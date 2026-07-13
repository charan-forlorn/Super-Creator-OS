"""Append-only local persistence for Stage 8L initialization evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .hvs_commercial_proposal_models import _safe_text, stable_id
from .hvs_customer_outcome_models import validate_calendar_date
from .hvs_local_delivery_service import _runtime_root
from .hvs_project_initialization_models import (
    EVT_PROJECT_INITIALIZATION_CONFLICT,
    EVT_PROJECT_INITIALIZATION_PREPARED,
    EVT_PROJECT_INITIALIZATION_VERIFIED,
    HVSProjectInitializationEvent,
    PROJECT_INITIALIZATION_EVENT_SCHEMA_VERSION,
)


_ALLOWED_EVENT_TYPES = frozenset(
    (
        EVT_PROJECT_INITIALIZATION_PREPARED,
        EVT_PROJECT_INITIALIZATION_VERIFIED,
        EVT_PROJECT_INITIALIZATION_CONFLICT,
    )
)


def project_initialization_path(repo_root: Any) -> Path:
    return _runtime_root(Path(repo_root)) / "hvs_project_initialization.jsonl"


def project_initialization_contracts_dir(repo_root: Any) -> Path:
    return _runtime_root(Path(repo_root)) / "hvs_project_initialization_contracts"


def _validate_path(path: Any) -> Path:
    value = Path(path)
    text = str(value)
    if ".." in value.parts or "://" in text or "\x00" in text:
        raise ValueError("unsafe project initialization store path")
    return value


def _validate_event(event: HVSProjectInitializationEvent) -> None:
    if event.schema_version != PROJECT_INITIALIZATION_EVENT_SCHEMA_VERSION:
        raise ValueError("project initialization event schema version mismatch")
    if event.event_type not in _ALLOWED_EVENT_TYPES:
        raise ValueError("unsupported project initialization event type")
    for field in ("event_id", "subject_id", "operator_id"):
        _safe_text(field, getattr(event, field))
    validate_calendar_date("recorded_at", event.recorded_at)
    if not isinstance(event.record, dict):
        raise ValueError("project initialization event record must be a dict")


def read_project_initialization_events(*, audit_log_path: Any) -> tuple[HVSProjectInitializationEvent, ...]:
    path = _validate_path(audit_log_path)
    if not path.is_file():
        return ()
    events: list[HVSProjectInitializationEvent] = []
    seen: set[str] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = HVSProjectInitializationEvent(**json.loads(line))
            _validate_event(event)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"malformed project initialization event at line {number}") from exc
        if event.event_id in seen:
            raise ValueError("conflicting project initialization event")
        seen.add(event.event_id)
        events.append(event)
    return tuple(events)


def append_project_initialization_event(
    *,
    audit_log_path: Any,
    event_type: str,
    subject_id: str,
    operator_id: str,
    recorded_at: str,
    record: dict[str, Any],
) -> HVSProjectInitializationEvent:
    event = HVSProjectInitializationEvent(
        PROJECT_INITIALIZATION_EVENT_SCHEMA_VERSION,
        stable_id(
            "scos-hvs-project-initialization-event",
            {"event_type": event_type, "subject_id": subject_id, "record": record},
        ),
        event_type,
        subject_id,
        operator_id,
        recorded_at,
        record,
    )
    _validate_event(event)
    for existing in read_project_initialization_events(audit_log_path=audit_log_path):
        if existing.event_id == event.event_id:
            if existing.to_dict() == event.to_dict():
                return existing
            raise ValueError("conflicting project initialization event")
    path = _validate_path(audit_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    return event


def write_initialization_contract_file(
    *, repo_root: Any, contract_id: str, contract: dict[str, Any]
) -> Path:
    target_dir = project_initialization_contracts_dir(repo_root)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{contract_id}.json"
    body = json.dumps(contract, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != body:
        raise ValueError("conflicting project initialization contract file")
    if not path.exists():
        path.write_text(body, encoding="utf-8")
    return path
