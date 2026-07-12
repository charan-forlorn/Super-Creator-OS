"""Append-only Stage 8E revised-delivery release ledger and read helpers.

This store is SEPARATE from the Stage 8D reconciliation ledger
(``hvs_rerender_result_store.reconciliation_audit_path``), the Stage 8C
dispatch ledger, and the Stage 8B revision audit ledger. Stage 8E owns its own
append-only ledger under ``scos/work/hvs_revised_delivery_release.jsonl``.

Conventions mirror ``hvs_rerender_result_store``:
  * append-only; duplicate id with identical payload returns the existing event
  * duplicate id with conflicting payload raises (never silently overwrites)
  * path traversal / null-byte / URL paths are rejected
  * no secrets, no media, no network, no subprocess
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .hvs_local_delivery_service import _runtime_root
from .hvs_revised_delivery_release_models import (
    RELEASE_EVENT_SCHEMA_VERSION,
    ReleaseAuditEvent,
)


def release_audit_path(repo_root: Any) -> Path:
    return _runtime_root(Path(repo_root)) / "hvs_revised_delivery_release.jsonl"


def read_release_events(*, audit_log_path: Any) -> tuple[ReleaseAuditEvent, ...]:
    path = Path(audit_log_path)
    if ".." in path.parts or "://" in str(path) or "\x00" in str(path):
        raise ValueError("unsafe release store path")
    if not path.is_file():
        return ()
    seen: set[str] = set()
    result: list[ReleaseAuditEvent] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = ReleaseAuditEvent(**json.loads(line))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"malformed release event at line {n}") from exc
        if event.event_id in seen:
            raise ValueError("conflicting duplicate release event id")
        seen.add(event.event_id)
        result.append(event)
    return tuple(result)


def append_release_event(
    *, audit_log_path: Any, event: ReleaseAuditEvent
) -> ReleaseAuditEvent:
    existing = read_release_events(audit_log_path=audit_log_path)
    for seen in existing:
        if seen.event_id == event.event_id:
            if seen.to_dict() == event.to_dict():
                return seen
            raise ValueError("conflicting duplicate release event id")
    path = Path(audit_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(
            json.dumps(event.to_dict(), sort_keys=True, separators=(",", ":")) + "\n"
        )
    return event


def make_release_event(
    *,
    event_type: str,
    subject_id: str,
    operator_id: str,
    recorded_at: str,
    record: dict[str, Any],
) -> ReleaseAuditEvent:
    """Build a deterministic, schema-validated Stage 8E audit event.

    The event id is derived from the event type + subject id + record payload
    (no timestamp), so identical semantic events are idempotent and conflicting
    events under the same id are rejected.
    """
    event_id = _release_event_id(
        event_type=event_type, subject_id=subject_id, record=record
    )
    return ReleaseAuditEvent(
        schema_version=RELEASE_EVENT_SCHEMA_VERSION,
        event_id=event_id,
        event_type=event_type,
        subject_id=subject_id,
        operator_id=operator_id,
        recorded_at=recorded_at,
        record=record,
    )


def _release_event_id(
    *, event_type: str, subject_id: str, record: dict[str, Any]
) -> str:
    canonical = json.dumps(
        {"event_type": event_type, "subject_id": subject_id, "record": record},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"scos-hvs-release-evt-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"
