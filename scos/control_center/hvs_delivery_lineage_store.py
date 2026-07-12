"""Append-only local storage for immutable delivery lineage events."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .hvs_delivery_lineage_models import DeliveryLineageEvent
from .hvs_local_delivery_service import _runtime_root


LINEAGE_AUDIT_FILENAME = "hvs_delivery_lineage.jsonl"


def lineage_audit_path(repo_root: Path) -> Path:
    return _runtime_root(Path(repo_root)) / LINEAGE_AUDIT_FILENAME


def _ensure_store_path(path: Any) -> Path:
    target = path if isinstance(path, Path) else Path(str(path))
    text = str(target)
    if "\x00" in text or "://" in text or ".." in target.parts:
        raise ValueError("lineage store path must be a safe local path")
    return target


def read_lineage_events(*, audit_log_path: Any) -> tuple[DeliveryLineageEvent, ...]:
    target = _ensure_store_path(audit_log_path)
    if not target.is_file():
        return ()
    events: list[DeliveryLineageEvent] = []
    ids: set[str] = set()
    for line_number, line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = DeliveryLineageEvent(**json.loads(line))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"malformed lineage event at line {line_number}") from exc
        if event.event_id in ids:
            raise ValueError("conflicting duplicate lineage event id")
        ids.add(event.event_id)
        events.append(event)
    return tuple(events)


def append_lineage_event(*, audit_log_path: Any, event: DeliveryLineageEvent) -> DeliveryLineageEvent:
    target = _ensure_store_path(audit_log_path)
    existing = read_lineage_events(audit_log_path=target)
    for seen in existing:
        if seen.event_id == event.event_id:
            if seen.to_dict() == event.to_dict():
                return seen
            raise ValueError("conflicting duplicate lineage event id")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event.to_dict(), ensure_ascii=False, separators=(",", ":"), sort_keys=True))
        handle.write("\n")
    return event
