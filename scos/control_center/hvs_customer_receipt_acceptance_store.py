"""SCOS <-> HVS — Stage 8P append-only local persistence.

Mirrors the Stage 8O / Stage 8N store discipline: append-only JSONL ledger
under the gitignored ``scos/work/`` runtime root, immutable prior records,
deterministic ids, idempotent replay, conflicting-replay rejection, read-only
inspection. No media bytes, secrets, or HVS project data are ever staged.

Runtime paths are gitignored; only small JSON records are written here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .hvs_customer_receipt_acceptance_models import (
    POST_RECEIPT_EVENT_SCHEMA_VERSION,
    post_receipt_event_id,
)


_RUNTIME_RELATIVE = "scos/work/hvs_stage8p_receipt_acceptance"
_LEDGER_NAME = "stage8p_receipt_acceptance_ledger.jsonl"


def _validate_path(path: Any) -> Path:
    value = Path(path)
    text = str(value)
    if ".." in value.parts or "://" in text or "\x00" in text:
        raise ValueError("unsafe stage8p receipt/acceptance store path")
    return value


def _runtime_root(repo_root: Any) -> Path:
    return Path(repo_root).resolve() / _RUNTIME_RELATIVE


def receipt_ledger_path(repo_root: Any) -> Path:
    return _runtime_root(repo_root) / _LEDGER_NAME


def _validate_event(event: dict[str, Any]) -> None:
    if event.get("schema_version") != POST_RECEIPT_EVENT_SCHEMA_VERSION:
        raise ValueError("stage8p post-receipt event schema version mismatch")
    if not isinstance(event.get("event_id"), str) or not event["event_id"]:
        raise ValueError("stage8p post-receipt event missing deterministic id")
    if not isinstance(event.get("event_type"), str):
        raise ValueError("stage8p post-receipt event missing type")


def read_receipt_events(*, ledger_path: Any) -> tuple[dict[str, Any], ...]:
    """Read all events, failing safely on malformed or truncated lines.

    A malformed JSON line or duplicate event id is a hard error (fail closed).
    No silent repair and no rewriting of prior events.
    """
    path = _validate_path(ledger_path)
    if not path.is_file():
        return ()
    events: list[dict[str, Any]] = []
    seen: set[str] = set()
    # Detect a truncated (non-empty, non-newline-terminated) final line.
    raw = path.read_text(encoding="utf-8")
    if raw and not raw.endswith("\n"):
        raise ValueError("truncated stage8p post-receipt ledger line")
    for number, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
            _validate_event(event)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"malformed stage8p post-receipt event at line {number}") from exc
        if event["event_id"] in seen:
            raise ValueError("conflicting stage8p post-receipt event")
        seen.add(event["event_id"])
        events.append(event)
    return tuple(events)


def append_receipt_event(
    *,
    ledger_path: Any,
    event_type: str,
    aggregate_id: str,
    project_id: str,
    actual_delivery_record_id: str,
    artifact_sha256: str,
    operator_id: str,
    resulting_status: str,
    recorded_at: str,
    package_id: str | None = None,
    record_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = {
        "event_type": event_type,
        "aggregate_id": aggregate_id,
        "project_id": project_id,
        "actual_delivery_record_id": actual_delivery_record_id,
        "package_id": package_id,
        "artifact_sha256": artifact_sha256,
        "operator_id": operator_id,
        "resulting_status": resulting_status,
    }
    event = {
        "schema_version": POST_RECEIPT_EVENT_SCHEMA_VERSION,
        "event_id": post_receipt_event_id(
            event_type=event_type, aggregate_id=aggregate_id, record=summary
        ),
        "event_type": event_type,
        "aggregate_id": aggregate_id,
        "project_id": project_id,
        "actual_delivery_record_id": actual_delivery_record_id,
        "package_id": package_id,
        "artifact_sha256": artifact_sha256,
        "resulting_status": resulting_status,
        "operator_id": operator_id,
        "informational_recorded_at": recorded_at,
        "deterministic_content_hash": record_payload.get("deterministic_content_hash", "")
        if isinstance(record_payload, dict)
        else "",
        "automation_allowed": False,
        "record": record_payload if record_payload is not None else None,
    }
    _validate_event(event)
    for existing in read_receipt_events(ledger_path=ledger_path):
        if existing["event_id"] == event["event_id"]:
            # Deterministic id match => identical semantic event (idempotent replay).
            return existing
    path = _validate_path(ledger_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        )
    return event


def latest_event_for_aggregate(*, ledger_path: Any, aggregate_id: str) -> dict[str, Any] | None:
    result: dict[str, Any] | None = None
    for event in read_receipt_events(ledger_path=ledger_path):
        if event.get("aggregate_id") == aggregate_id:
            result = event
    return result


def events_for_actual_delivery(*, ledger_path: Any, actual_delivery_record_id: str) -> tuple[dict[str, Any], ...]:
    return tuple(
        e
        for e in read_receipt_events(ledger_path=ledger_path)
        if e.get("actual_delivery_record_id") == actual_delivery_record_id
    )


def latest_event_by_type(*, ledger_path: Any, event_type: str) -> dict[str, Any] | None:
    result: dict[str, Any] | None = None
    for event in read_receipt_events(ledger_path=ledger_path):
        if event.get("event_type") == event_type:
            result = event
    return result
