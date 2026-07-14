"""SCOS <-> HVS — Stage 8R append-only local persistence.

Mirrors the Stage 8P / 8O / 8Q store discipline: append-only JSONL ledger
under the gitignored ``scos/work/`` runtime root, immutable prior records,
deterministic ids, idempotent replay, conflicting-replay rejection, read-only
inspection. No media bytes, secrets, customer-message bodies, or HVS project
data are ever staged.

Runtime paths are gitignored; only small JSON records are written here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .hvs_resolution_action_models import EVENT_SCHEMA_VERSION, resolution_action_event_id


_RUNTIME_RELATIVE = "scos/work/hvs_stage8r_resolution_action"
_LEDGER_NAME = "stage8r_resolution_action_ledger.jsonl"


def _validate_path(path: Any) -> Path:
    value = Path(path)
    text = str(value)
    if ".." in value.parts or "://" in text or "\x00" in text:
        raise ValueError("unsafe stage8r resolution store path")
    return value


def _runtime_root(repo_root: Any) -> Path:
    return Path(repo_root).resolve() / _RUNTIME_RELATIVE


def ledger_path(repo_root: Any) -> Path:
    return _runtime_root(repo_root) / _LEDGER_NAME


def _validate_event(event: dict[str, Any]) -> None:
    if event.get("schema_version") != EVENT_SCHEMA_VERSION:
        raise ValueError("stage8r resolution event schema version mismatch")
    if not isinstance(event.get("event_id"), str) or not event["event_id"]:
        raise ValueError("stage8r resolution event missing deterministic id")
    if not isinstance(event.get("event_type"), str):
        raise ValueError("stage8r resolution event missing type")


def read_resolution_action_events(*, ledger_path: Any) -> tuple[dict[str, Any], ...]:
    """Read all events, failing safely on malformed or truncated lines.

    A malformed JSON line or duplicate event id is a hard error (fail closed).
    No silent repair and no rewriting of prior events.
    """
    path = _validate_path(ledger_path)
    if not path.is_file():
        return ()
    events: list[dict[str, Any]] = []
    seen: set[str] = set()
    raw = path.read_text(encoding="utf-8")
    if raw and not raw.endswith("\n"):
        raise ValueError("truncated stage8r resolution ledger line")
    for number, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
            _validate_event(event)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"malformed stage8r resolution event at line {number}") from exc
        if event["event_id"] in seen:
            raise ValueError("conflicting stage8r resolution event")
        seen.add(event["event_id"])
        events.append(event)
    return tuple(events)


def append_resolution_action_event(
    *,
    ledger_path: Any,
    event_type: str,
    execution_request_id: str,
    project_id: str,
    customer_reference: str,
    artifact_sha256: str,
    action_family: str,
    source_route_id: str,
    resulting_status: str,
    operator_id: str,
    recorded_at: str,
    execution_contract_hash: str = "",
    target_record_id: str = "",
    detail: str = "",
    record_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = {
        "event_type": event_type,
        "execution_request_id": execution_request_id,
        "project_id": project_id,
        "customer_reference": customer_reference,
        "artifact_sha256": artifact_sha256,
        "action_family": action_family,
        "source_route_id": source_route_id,
        "resulting_status": resulting_status,
        "execution_contract_hash": execution_contract_hash,
        "target_record_id": target_record_id,
        "detail": detail,
    }
    event = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "event_id": resolution_action_event_id(
            event_type=event_type,
            execution_request_id=execution_request_id,
            record=summary,
        ),
        "event_type": event_type,
        "execution_request_id": execution_request_id,
        "project_id": project_id,
        "customer_reference": customer_reference,
        "artifact_sha256": artifact_sha256,
        "action_family": action_family,
        "source_route_id": source_route_id,
        "resulting_status": resulting_status,
        "operator_id": operator_id,
        "informational_recorded_at": recorded_at,
        "execution_contract_hash": execution_contract_hash,
        "target_record_id": target_record_id,
        "detail": detail,
        "record": record_payload if record_payload is not None else None,
    }
    _validate_event(event)
    for existing in read_resolution_action_events(ledger_path=ledger_path):
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


def latest_event_for_request(*, ledger_path: Any, execution_request_id: str) -> dict[str, Any] | None:
    result: dict[str, Any] | None = None
    for event in read_resolution_action_events(ledger_path=ledger_path):
        if event.get("execution_request_id") == execution_request_id:
            result = event
    return result


def events_for_request(*, ledger_path: Any, execution_request_id: str) -> tuple[dict[str, Any], ...]:
    return tuple(
        e
        for e in read_resolution_action_events(ledger_path=ledger_path)
        if e.get("execution_request_id") == execution_request_id
    )


def events_by_type(*, ledger_path: Any, event_type: str) -> tuple[dict[str, Any], ...]:
    return tuple(
        e
        for e in read_resolution_action_events(ledger_path=ledger_path)
        if e.get("event_type") == event_type
    )


def events_for_route(*, ledger_path: Any, source_route_id: str) -> tuple[dict[str, Any], ...]:
    return tuple(
        e
        for e in read_resolution_action_events(ledger_path=ledger_path)
        if e.get("source_route_id") == source_route_id
    )
