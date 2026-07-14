"""SCOS <-> HVS — Stage 8O append-only local persistence.

Mirrors the Stage 8N / Stage 8M store discipline: append-only JSONL ledger
under the gitignored ``scos/work/`` runtime root, immutable prior records,
deterministic ids, idempotent replay, conflicting-replay rejection, read-only
inspection. No media bytes, secrets, or HVS project data are ever staged.

Runtime paths are gitignored; only small JSON records are written here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .hvs_stage8o_delivery_models import DELIVERY_EVENT_SCHEMA_VERSION, delivery_event_id


_RUNTIME_RELATIVE = "scos/work/hvs_stage8o_delivery_packages"
_LEDGER_NAME = "stage8o_delivery_ledger.jsonl"


def _validate_path(path: Any) -> Path:
    value = Path(path)
    text = str(value)
    if ".." in value.parts or "://" in text or "\x00" in text:
        raise ValueError("unsafe stage8o delivery store path")
    return value


def _runtime_root(repo_root: Any) -> Path:
    return Path(repo_root).resolve() / _RUNTIME_RELATIVE


def delivery_ledger_path(repo_root: Any) -> Path:
    return _runtime_root(repo_root) / _LEDGER_NAME


def _validate_event(event: dict[str, Any]) -> None:
    if event.get("schema_version") != DELIVERY_EVENT_SCHEMA_VERSION:
        raise ValueError("stage8o delivery event schema version mismatch")
    if not isinstance(event.get("event_id"), str) or not event["event_id"]:
        raise ValueError("stage8o delivery event missing deterministic id")
    if not isinstance(event.get("event_type"), str):
        raise ValueError("stage8o delivery event missing type")


def read_delivery_events(*, ledger_path: Any) -> tuple[dict[str, Any], ...]:
    path = _validate_path(ledger_path)
    if not path.is_file():
        return ()
    events: list[dict[str, Any]] = []
    seen: set[str] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
            _validate_event(event)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"malformed stage8o delivery event at line {number}") from exc
        if event["event_id"] in seen:
            raise ValueError("conflicting stage8o delivery event")
        seen.add(event["event_id"])
        events.append(event)
    return tuple(events)


def append_delivery_event(
    *,
    ledger_path: Any,
    event_type: str,
    subject_id: str,
    completion_evidence_id: str,
    artifact_sha256: str,
    operator_id: str,
    resulting_status: str,
    reason: str,
    recorded_at: str,
    package_id: str | None = None,
    package_content_hash: str | None = None,
    authorization_request_id: str | None = None,
    authorization_decision_id: str | None = None,
    delivery_record_id: str | None = None,
    record_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = {
        "event_type": event_type,
        "subject_id": subject_id,
        "package_id": package_id,
        "package_content_hash": package_content_hash,
        "authorization_request_id": authorization_request_id,
        "authorization_decision_id": authorization_decision_id,
        "delivery_record_id": delivery_record_id,
        "completion_evidence_id": completion_evidence_id,
        "artifact_sha256": artifact_sha256,
        "operator_id": operator_id,
        "resulting_status": resulting_status,
        "reason": reason,
    }
    event = {
        "schema_version": DELIVERY_EVENT_SCHEMA_VERSION,
        "event_id": delivery_event_id(
            event_type=event_type, subject_id=subject_id, record=summary
        ),
        "event_type": event_type,
        "subject_id": subject_id,
        "package_id": package_id,
        "package_content_hash": package_content_hash,
        "authorization_request_id": authorization_request_id,
        "authorization_decision_id": authorization_decision_id,
        "delivery_record_id": delivery_record_id,
        "completion_evidence_id": completion_evidence_id,
        "artifact_sha256": artifact_sha256,
        "operator_id": operator_id,
        "resulting_status": resulting_status,
        "reason": reason,
        "recorded_at": recorded_at,
        "automation_allowed": False,
        "record": record_payload if record_payload is not None else None,
    }
    _validate_event(event)
    for existing in read_delivery_events(ledger_path=ledger_path):
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


def _latest_by_match(
    *,
    ledger_path: Any,
    match_field: str,
    match_value: str,
) -> dict[str, Any] | None:
    result: dict[str, Any] | None = None
    for event in read_delivery_events(ledger_path=ledger_path):
        if event.get(match_field) == match_value:
            result = event
    return result


def latest_event_for_subject(*, ledger_path: Any, subject_id: str) -> dict[str, Any] | None:
    return _latest_by_match(ledger_path=ledger_path, match_field="subject_id", match_value=subject_id)


def latest_event_by_type(*, ledger_path: Any, event_type: str) -> dict[str, Any] | None:
    return _latest_by_match(ledger_path=ledger_path, match_field="event_type", match_value=event_type)


def events_for_package(*, ledger_path: Any, package_id: str) -> tuple[dict[str, Any], ...]:
    return tuple(
        e for e in read_delivery_events(ledger_path=ledger_path) if e.get("package_id") == package_id
    )


def events_for_authorization(*, ledger_path: Any, authorization_request_id: str) -> tuple[dict[str, Any], ...]:
    return tuple(
        e
        for e in read_delivery_events(ledger_path=ledger_path)
        if e.get("authorization_request_id") == authorization_request_id
    )
