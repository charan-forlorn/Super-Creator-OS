"""test_event_log.py - SCOS Stage 5.1 command event log suite.

Plain executable script (no pytest). Covers event creation, deterministic
content-derived event ids, JSONL append/read round-trips, invalid status
rejection, and URL path rejection. Uses a temporary directory for every log
file.

Run: python scos/control_center/tests/test_event_log.py
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent

sys.path.insert(0, str(_PACKAGE))

from event_log import (  # noqa: E402
    CONTROL_CENTER_EVENT_LOG_SCHEMA_VERSION,
    append_command_event,
    make_command_event,
    read_command_events,
)

_PASS = 0
_FAIL = 0

_CREATED_AT = "2026-07-05T10:10:00Z"


def check(name: str, cond: bool) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}")


def _event(event_type: str = "COMMAND_QUEUED", message: str = "queued"):
    return make_command_event(
        command_id="cmd-001",
        event_type=event_type,
        created_at=_CREATED_AT,
        status="pending",
        message=message,
        metadata=(("origin", "runner"),),
    )


def test_schema_version() -> None:
    print("\n[1] schema version")
    check("schema version is 1", CONTROL_CENTER_EVENT_LOG_SCHEMA_VERSION == 1)


def test_make_event() -> None:
    print("\n[2] make_command_event")
    event = _event()
    check("event id prefixed", event.event_id.startswith("evt-"))
    check("fields carried", event.command_id == "cmd-001" and event.message == "queued")
    expected = hashlib.sha256(
        "|".join(("cmd-001", "COMMAND_QUEUED", _CREATED_AT, "queued")).encode("utf-8")
    ).hexdigest()[:16]
    check("event id content-derived", event.event_id == f"evt-{expected}")


def test_event_id_deterministic() -> None:
    print("\n[3] deterministic event_id")
    check("same inputs -> same id", _event().event_id == _event().event_id)
    check("different message -> different id", _event().event_id != _event(message="other").event_id)
    check(
        "different type -> different id",
        _event().event_id != _event(event_type="COMMAND_STARTED").event_id,
    )


def test_invalid_values() -> None:
    print("\n[4] invalid status / event_type rejected")
    try:
        make_command_event(
            command_id="cmd-001",
            event_type="COMMAND_QUEUED",
            created_at=_CREATED_AT,
            status="sideways",
            message="x",
        )
        check("invalid status rejected", False)
    except ValueError:
        check("invalid status rejected", True)
    try:
        make_command_event(
            command_id="cmd-001",
            event_type="NOT_AN_EVENT",
            created_at=_CREATED_AT,
            status="pending",
            message="x",
        )
        check("invalid event_type rejected", False)
    except ValueError:
        check("invalid event_type rejected", True)


def test_append_and_read(tmp: Path) -> None:
    print("\n[5] append/read JSONL")
    log = tmp / "events" / "log.jsonl"
    digest = append_command_event(event_log_path=log, event=_event())
    check("digest is sha256 hex", len(digest) == 64)
    append_command_event(event_log_path=log, event=_event(event_type="COMMAND_STARTED", message="started"))
    events = read_command_events(event_log_path=log)
    check("two events read back", len(events) == 2)
    check("round-trip equality", events[0] == _event())
    check("append order preserved", events[1].event_type == "COMMAND_STARTED")
    text = log.read_text(encoding="utf-8")
    check("LF line endings only", "\r" not in text)
    with open(log, "a", encoding="utf-8", newline="\n") as handle:
        handle.write("\n")
    check("blank lines skipped", len(read_command_events(event_log_path=log)) == 2)

    broken = tmp / "broken.jsonl"
    broken.write_text("{oops\n", encoding="utf-8")
    try:
        read_command_events(event_log_path=broken)
        check("invalid line raises controlled error", False)
    except ValueError as exc:
        check(
            "invalid line raises controlled error",
            str(exc) == "INVALID_EVENT_LINE: line 1 is not valid JSON",
        )


def test_url_path_rejected() -> None:
    print("\n[6] URL path rejection")
    try:
        append_command_event(event_log_path="https://example.com/log.jsonl", event=_event())
        check("append rejects URL path", False)
    except ValueError as exc:
        check("append rejects URL path", str(exc).startswith("URL_PATH_REJECTED:"))
    try:
        read_command_events(event_log_path="http://example.com/log.jsonl")
        check("read rejects URL path", False)
    except ValueError as exc:
        check("read rejects URL path", str(exc).startswith("URL_PATH_REJECTED:"))


def main() -> int:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        test_schema_version()
        test_make_event()
        test_event_id_deterministic()
        test_invalid_values()
        test_append_and_read(tmp)
        test_url_path_rejected()
    print(f"\n RESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
