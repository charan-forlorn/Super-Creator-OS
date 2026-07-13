"""Append-only local persistence for Stage 8H evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .hvs_customer_outcome_models import CUSTOMER_SUCCESS_EVENT_SCHEMA_VERSION, stable_id
from .hvs_local_delivery_service import _runtime_root
from .hvs_rerender_dispatch_models import _safe_id


@dataclass(frozen=True)
class CustomerSuccessEvent:
    schema_version: str
    event_id: str
    event_type: str
    subject_id: str
    operator_id: str
    recorded_at: str
    record: dict[str, Any]

    def __post_init__(self) -> None:
        if self.schema_version != CUSTOMER_SUCCESS_EVENT_SCHEMA_VERSION:
            raise ValueError("customer-success event schema version mismatch")
        for field in ("event_id", "subject_id", "operator_id"):
            _safe_id(field, getattr(self, field))
        _safe_id("event_type", self.event_type)
        if not isinstance(self.record, dict):
            raise ValueError("customer-success event record must be a dict")

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def customer_success_path(repo_root: Any) -> Path:
    return _runtime_root(Path(repo_root)) / "hvs_customer_success.jsonl"


def read_customer_success_events(*, audit_log_path: Any) -> tuple[CustomerSuccessEvent, ...]:
    path = Path(audit_log_path)
    if ".." in path.parts or "://" in str(path) or "\x00" in str(path):
        raise ValueError("unsafe customer-success store path")
    if not path.is_file():
        return ()
    result: list[CustomerSuccessEvent] = []
    ids: set[str] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = CustomerSuccessEvent(**json.loads(line))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"malformed customer-success event at line {number}") from exc
        if event.event_id in ids:
            raise ValueError("conflicting duplicate customer-success event id")
        ids.add(event.event_id)
        result.append(event)
    return tuple(result)


def make_customer_success_event(*, event_type: str, subject_id: str, operator_id: str, recorded_at: str, record: dict[str, Any]) -> CustomerSuccessEvent:
    event_id = stable_id("scos-hvs-customer-success-event", {"event_type": event_type, "subject_id": subject_id, "record": record})
    return CustomerSuccessEvent(CUSTOMER_SUCCESS_EVENT_SCHEMA_VERSION, event_id, event_type, subject_id, operator_id, recorded_at, record)


def append_customer_success_event(*, audit_log_path: Any, event: CustomerSuccessEvent) -> CustomerSuccessEvent:
    for existing in read_customer_success_events(audit_log_path=audit_log_path):
        if existing.event_id == event.event_id:
            if existing.to_dict() == event.to_dict():
                return existing
            raise ValueError("conflicting duplicate customer-success event id")
    path = Path(audit_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event.to_dict(), sort_keys=True, separators=(",", ":")) + "\n")
    return event
