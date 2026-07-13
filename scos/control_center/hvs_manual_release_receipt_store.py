"""Append-only Stage 8F manual-release / receipt / post-delivery audit ledger
and read helpers.

This store is SEPARATE from the Stage 8D reconciliation ledger
(``hvs_rerender_result_store.reconciliation_audit_path``), the Stage 8E release
ledger (``hvs_revised_delivery_release_store.release_audit_path``), the Stage
8C dispatch ledger, and the Stage 8B revision audit ledger. Stage 8F owns its
own append-only ledger under ``scos/work/hvs_manual_release_receipt.jsonl``.

Conventions mirror ``hvs_revised_delivery_release_store`` and
``hvs_rerender_result_store``:
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
from .hvs_manual_release_receipt_models import (
    POST_DELIVERY_EVENT_SCHEMA_VERSION,
    PostDeliveryAuditEvent,
)


def post_delivery_audit_path(repo_root: Any) -> Path:
    return _runtime_root(Path(repo_root)) / "hvs_manual_release_receipt.jsonl"


def read_post_delivery_events(*, audit_log_path: Any) -> tuple[PostDeliveryAuditEvent, ...]:
    path = Path(audit_log_path)
    if ".." in path.parts or "://" in str(path) or "\x00" in str(path):
        raise ValueError("unsafe post-delivery store path")
    if not path.is_file():
        return ()
    seen: set[str] = set()
    result: list[PostDeliveryAuditEvent] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = PostDeliveryAuditEvent(**json.loads(line))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"malformed post-delivery event at line {n}") from exc
        if event.event_id in seen:
            raise ValueError("conflicting duplicate post-delivery event id")
        seen.add(event.event_id)
        result.append(event)
    return tuple(result)


def append_post_delivery_event(
    *, audit_log_path: Any, event: PostDeliveryAuditEvent
) -> PostDeliveryAuditEvent:
    existing = read_post_delivery_events(audit_log_path=audit_log_path)
    for seen in existing:
        if seen.event_id == event.event_id:
            if seen.to_dict() == event.to_dict():
                return seen
            raise ValueError("conflicting duplicate post-delivery event id")
    path = Path(audit_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(event.to_dict(), sort_keys=True, separators=(",", ":")) + "\n")
    return event


def make_post_delivery_event(
    *,
    event_type: str,
    subject_id: str,
    operator_id: str,
    recorded_at: str,
    record: dict[str, Any],
) -> PostDeliveryAuditEvent:
    """Build a deterministic, schema-validated Stage 8F audit event.

    The event id is derived from the event type + subject id + record payload
    (no timestamp), so identical semantic events are idempotent and conflicting
    events under the same id are rejected.
    """
    from .hvs_manual_release_receipt_models import build_event_id

    event_id = build_event_id(event_type=event_type, subject_id=subject_id, record=record)
    return PostDeliveryAuditEvent(
        schema_version=POST_DELIVERY_EVENT_SCHEMA_VERSION,
        event_id=event_id,
        event_type=event_type,
        subject_id=subject_id,
        operator_id=operator_id,
        recorded_at=recorded_at,
        record=record,
    )
