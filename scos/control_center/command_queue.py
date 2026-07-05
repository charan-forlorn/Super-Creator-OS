"""SCOS Stage 5.1 local command queue (JSONL, append-only).

Approved commands are appended one JSON object per line to a local JSONL
file (UTF-8, LF). The queue is strictly append-only: this module never
deletes, truncates, or rewrites existing lines. Each append returns the
SHA-256 of the written line so callers can record provenance.

Local-first, deterministic, stdlib-only. No clock, no random, no network.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

try:
    from .command_models import ApprovedCommand
except ImportError:  # direct-module execution (tests insert the package dir)
    from command_models import ApprovedCommand

CONTROL_CENTER_COMMAND_QUEUE_SCHEMA_VERSION = 1

_URL_PREFIXES = ("http://", "https://")
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")


def _ensure_local_path(path: Any, label: str) -> Path:
    """Coerce ``path`` (str or Path) to a local Path; reject URL-like strings."""
    if isinstance(path, str):
        text = path.strip()
        if text.lower().startswith(_URL_PREFIXES) or _SCHEME_RE.match(text):
            raise ValueError(f"URL_PATH_REJECTED: {label} must be a local path")
        return Path(text)
    if isinstance(path, Path):
        return path
    raise ValueError(f"INVALID_PATH: {label} must be a str or pathlib.Path")


def _jsonl_line(payload: dict) -> str:
    # One compact object per line; key order is the model's explicit
    # to_dict() order, which is deterministic by construction.
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _append_jsonl_line(path: Any, label: str, payload: dict) -> str:
    """Append one JSON object line to ``path``; return the line's SHA-256 hex."""
    target = _ensure_local_path(path, label)
    target.parent.mkdir(parents=True, exist_ok=True)
    line = _jsonl_line(payload)
    with open(target, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(line + "\n")
    return hashlib.sha256(line.encode("utf-8")).hexdigest()


def _read_jsonl_objects(path: Any, label: str, error_code: str) -> tuple[dict, ...]:
    """Read all JSON object lines from ``path``, skipping blank lines.

    Raises a controlled ``ValueError`` with a stable message for lines that
    are not valid JSON objects. A missing file reads as an empty queue/log.
    """
    target = _ensure_local_path(path, label)
    if not target.is_file():
        return ()
    objects: list[dict] = []
    text = target.read_text(encoding="utf-8")
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            raise ValueError(
                f"{error_code}: line {line_number} is not valid JSON"
            ) from None
        if not isinstance(payload, dict):
            raise ValueError(
                f"{error_code}: line {line_number} is not a JSON object"
            )
        objects.append(payload)
    return tuple(objects)


def _pairs_from_lists(value: Any) -> tuple[tuple[str, str], ...]:
    return tuple((str(pair[0]), str(pair[1])) for pair in (value or ()))


def append_approved_command(
    *,
    queue_path,
    approved_command: ApprovedCommand,
) -> str:
    """Append one approved command to the queue; return the line's SHA-256."""
    if not isinstance(approved_command, ApprovedCommand):
        raise ValueError(
            "NOT_AN_APPROVED_COMMAND: only ApprovedCommand instances may be queued"
        )
    return _append_jsonl_line(queue_path, "queue_path", approved_command.to_dict())


def read_command_queue(
    *,
    queue_path,
) -> tuple[ApprovedCommand, ...]:
    """Read every queued approved command in append order (blank lines skipped)."""
    payloads = _read_jsonl_objects(queue_path, "queue_path", "INVALID_QUEUE_LINE")
    commands: list[ApprovedCommand] = []
    for payload in payloads:
        commands.append(
            ApprovedCommand(
                command_id=payload.get("command_id", ""),
                command_type=payload.get("command_type", ""),
                approved_by=payload.get("approved_by", ""),
                approved_at=payload.get("approved_at", ""),
                args=_pairs_from_lists(payload.get("args")),
                metadata=_pairs_from_lists(payload.get("metadata")),
            )
        )
    return tuple(commands)
