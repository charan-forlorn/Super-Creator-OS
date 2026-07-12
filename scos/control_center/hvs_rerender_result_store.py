"""Append-only Stage 8D re-render result reconciliation ledger and read helpers.

This store is SEPARATE from the Stage 8C dispatch ledger
(``hvs_rerender_dispatch_store.rerender_dispatch_audit_path``) and from the
Stage 8B revision audit ledger
(``hvs_revision_store.revision_audit_path``). Stage 8B's ``_state`` reads the
revision audit ledger and reconstructs state from the LAST event for a given
revision_request_id; appending reconciliation events there would corrupt that
state reconstruction. Stage 8D therefore owns its own append-only ledger under
``scos/work/hvs_rerender_result_reconciliation.jsonl``.

Conventions mirror ``hvs_rerender_dispatch_store``:
  * append-only; duplicate id with identical payload returns the existing event
  * duplicate id with conflicting payload raises (never silently overwrites)
  * path traversal / null-byte / URL paths are rejected
  * no secrets, no media, no network, no subprocess
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .hvs_local_delivery_service import _runtime_root
from .hvs_rerender_result_models import (
    RERENDER_RESULT_EVENT_SCHEMA_VERSION,
    RerenderResultAuditEvent,
)


def reconciliation_audit_path(repo_root: Any) -> Path:
    return _runtime_root(Path(repo_root)) / "hvs_rerender_result_reconciliation.jsonl"


def read_reconciliation_events(*, audit_log_path: Any) -> tuple[RerenderResultAuditEvent, ...]:
    path = Path(audit_log_path)
    if ".." in path.parts or "://" in str(path) or "\x00" in str(path):
        raise ValueError("unsafe reconciliation store path")
    if not path.is_file():
        return ()
    seen: set[str] = set()
    result: list[RerenderResultAuditEvent] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = RerenderResultAuditEvent(**json.loads(line))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"malformed reconciliation event at line {n}") from exc
        if event.event_id in seen:
            raise ValueError("conflicting duplicate reconciliation event id")
        seen.add(event.event_id)
        result.append(event)
    return tuple(result)


def append_reconciliation_event(
    *, audit_log_path: Any, event: RerenderResultAuditEvent
) -> RerenderResultAuditEvent:
    existing = read_reconciliation_events(audit_log_path=audit_log_path)
    for seen in existing:
        if seen.event_id == event.event_id:
            if seen.to_dict() == event.to_dict():
                return seen
            raise ValueError("conflicting duplicate reconciliation event id")
    path = Path(audit_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(
            json.dumps(event.to_dict(), sort_keys=True, separators=(",", ":")) + "\n"
        )
    return event


def make_reconciliation_event(
    *,
    event_type: str,
    result_id: str,
    dispatch_id: str,
    operator_id: str,
    recorded_at: str,
    record: dict[str, Any],
) -> RerenderResultAuditEvent:
    """Build a deterministic, schema-validated reconciliation audit event."""
    event_id = _reconciliation_event_id(
        event_type=event_type, result_id=result_id, dispatch_id=dispatch_id, record=record
    )
    return RerenderResultAuditEvent(
        schema_version=RERENDER_RESULT_EVENT_SCHEMA_VERSION,
        event_id=event_id,
        event_type=event_type,
        result_id=result_id,
        dispatch_id=dispatch_id,
        operator_id=operator_id,
        recorded_at=recorded_at,
        record=record,
    )


def _reconciliation_event_id(
    *, event_type: str, result_id: str, dispatch_id: str, record: dict[str, Any]
) -> str:
    import hashlib

    canonical = json.dumps(
        {"event_type": event_type, "result_id": result_id, "dispatch_id": dispatch_id, "record": record},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"scos-hvs-rerender-recon-evt-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"
