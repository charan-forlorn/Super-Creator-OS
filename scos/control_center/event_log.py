"""SCOS Stage 5.1 command event log (JSONL, append-only).

Every command lifecycle transition is recorded as one deterministic
``CommandEvent`` per JSONL line (UTF-8, LF, append-only). Event ids are
content-derived (SHA-256 over command_id + event_type + created_at +
message), so replaying the same lifecycle always yields the same log.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid.
"""

from __future__ import annotations

import hashlib

try:
    from .command_models import CommandEvent
    from .command_queue import _append_jsonl_line, _pairs_from_lists, _read_jsonl_objects
except ImportError:  # direct-module execution (tests insert the package dir)
    from command_models import CommandEvent
    from command_queue import _append_jsonl_line, _pairs_from_lists, _read_jsonl_objects

CONTROL_CENTER_EVENT_LOG_SCHEMA_VERSION = 1

_EVENT_ID_DIGEST_LENGTH = 16


def make_command_event(
    *,
    command_id: str,
    event_type: str,
    created_at: str,
    status: str,
    message: str,
    metadata: tuple[tuple[str, str], ...] = (),
) -> CommandEvent:
    """Build a ``CommandEvent`` with a deterministic content-derived event id.

    ``created_at`` must be supplied explicitly (no clock is read). Invalid
    ``event_type`` / ``status`` values are rejected by the model itself.
    """
    digest = hashlib.sha256(
        "|".join((command_id, event_type, created_at, message)).encode("utf-8")
    ).hexdigest()[:_EVENT_ID_DIGEST_LENGTH]
    return CommandEvent.of(
        event_id=f"evt-{digest}",
        command_id=command_id,
        event_type=event_type,
        created_at=created_at,
        status=status,
        message=message,
        metadata=metadata,
    )


def append_command_event(
    *,
    event_log_path,
    event: CommandEvent,
) -> str:
    """Append one event to the log; return the written line's SHA-256 hex."""
    if not isinstance(event, CommandEvent):
        raise ValueError("NOT_A_COMMAND_EVENT: only CommandEvent instances may be logged")
    return _append_jsonl_line(event_log_path, "event_log_path", event.to_dict())


def read_command_events(
    *,
    event_log_path,
) -> tuple[CommandEvent, ...]:
    """Read every logged event in append order (blank lines skipped)."""
    payloads = _read_jsonl_objects(
        event_log_path, "event_log_path", "INVALID_EVENT_LINE"
    )
    events: list[CommandEvent] = []
    for payload in payloads:
        events.append(
            CommandEvent(
                event_id=payload.get("event_id", ""),
                command_id=payload.get("command_id", ""),
                event_type=payload.get("event_type", ""),
                created_at=payload.get("created_at", ""),
                status=payload.get("status", ""),
                message=payload.get("message", ""),
                metadata=_pairs_from_lists(payload.get("metadata")),
            )
        )
    return tuple(events)
