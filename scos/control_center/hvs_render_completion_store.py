"""Stage 8N — append-only local persistence for render completion.

Mirrors the Stage 8M / Stage 8L store discipline: append-only JSONL ledger
under the gitignored ``scos/work/`` runtime root, immutable prior events,
deterministic ids, idempotent replay, conflicting-replay rejection, read-only
inspection.

Runtime paths are gitignored; no media bytes, secrets, or HVS project data are
ever staged.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .hvs_commercial_proposal_models import _safe_text, stable_id
from .hvs_render_completion_models import (
    STAGE8N_EVENT_SCHEMA_VERSION,
    ALLOWED_EVENT_TYPES,
    RenderCompletionEventType,
)
from datetime import date, datetime


def _validate_recorded_at(value: Any) -> None:
    """Tolerant date/datetime check: a Stage 8N informational timestamp may be
    an ISO calendar date OR a full ISO datetime (excluded from deterministic
    identity, so both are accepted)."""
    if not isinstance(value, str):
        raise ValueError("recorded_at must be an ISO date or datetime string")
    try:
        date.fromisoformat(value)
        return
    except ValueError:
        pass
    try:
        datetime.fromisoformat(value)
        return
    except ValueError as exc:
        raise ValueError("recorded_at must be an ISO date or datetime") from exc

_RUNTIME_RELATIVE = "scos/work/hvs_render_completion"
_LEDGER_NAME = "render_completion.jsonl"


def _runtime_root(repo_root: Any) -> Path:
    return Path(repo_root).resolve() / _RUNTIME_RELATIVE


def render_completion_path(repo_root: Any) -> Path:
    return _runtime_root(repo_root) / _LEDGER_NAME


def _validate_path(path: Any) -> Path:
    value = Path(path)
    text = str(value)
    if ".." in value.parts or "://" in text or "\x00" in text:
        raise ValueError("unsafe render completion store path")
    return value


def _validate_event(event: dict[str, Any]) -> None:
    if event.get("schema_version") != STAGE8N_EVENT_SCHEMA_VERSION:
        raise ValueError("render completion event schema version mismatch")
    if event.get("event_type") not in ALLOWED_EVENT_TYPES:
        raise ValueError("unsupported render completion event type")
    for field in ("event_id", "subject_id", "operator_id"):
        _safe_text(field, event.get(field))
    _validate_recorded_at(event.get("recorded_at"))
    if not isinstance(event.get("record"), dict):
        raise ValueError("render completion event record must be a dict")


def read_render_completion_events(*, audit_log_path: Any) -> tuple[dict[str, Any], ...]:
    path = _validate_path(audit_log_path)
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
            raise ValueError(f"malformed render completion event at line {number}") from exc
        if event["event_id"] in seen:
            raise ValueError("conflicting render completion event")
        seen.add(event["event_id"])
        events.append(event)
    return tuple(events)


def append_render_completion_event(
    *,
    audit_log_path: Any,
    event_type: str,
    subject_id: str,
    operator_id: str,
    recorded_at: str,
    record: dict[str, Any],
) -> dict[str, Any]:
    event = {
        "schema_version": STAGE8N_EVENT_SCHEMA_VERSION,
        "event_id": stable_id(
            "scos-hvs-render-completion-event",
            {"event_type": event_type, "subject_id": subject_id, "record": record},
        ),
        "event_type": event_type,
        "subject_id": subject_id,
        "operator_id": operator_id,
        "recorded_at": recorded_at,
        "record": record,
    }
    _validate_event(event)
    for existing in read_render_completion_events(audit_log_path=audit_log_path):
        if existing["event_id"] == event["event_id"]:
            # Deterministic id match => identical semantic event (idempotent
            # replay). The serialized record may differ only by tuple/list
            # normalization on JSON round-trip, which is not a real conflict.
            return existing
    path = _validate_path(audit_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        )
    return event


def latest_by_type(*, audit_log_path: Any, event_type: str) -> dict[str, Any] | None:
    """Return the most recent event of a given type, or None."""
    latest: dict[str, Any] | None = None
    for event in read_render_completion_events(audit_log_path=audit_log_path):
        if event["event_type"] == event_type:
            latest = event
    return latest


def latest_render_completion_evidence(*, audit_log_path: Any) -> dict[str, Any] | None:
    return latest_by_type(
        audit_log_path=audit_log_path,
        event_type=RenderCompletionEventType.RENDER_COMPLETION_EVIDENCE_CREATED,
    )
