"""test_work_session_store.py - SCOS Stage 5.2 JSONL work session store suite.

Plain executable script (no pytest). Covers append/load round-tripping,
append-only semantics (latest snapshot per session_id wins), missing-file
behavior, and invalid-line error handling.

Run: python scos/control_center/tests/test_work_session_store.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent

sys.path.insert(0, str(_PACKAGE))

from work_session_manager import create_work_session, transition_status  # noqa: E402
from work_session_models import AIWorkSession, AIWorkTask  # noqa: E402
from work_session_store import (  # noqa: E402
    WORK_SESSION_STORE_SCHEMA_VERSION,
    append_event,
    append_session,
    list_sessions,
    load_session,
    load_sessions,
)

_PASS = 0
_FAIL = 0


def check(name: str, cond: bool) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}")


def _task() -> AIWorkTask:
    return AIWorkTask.of(
        "task-500",
        "Persist a work session",
        "prompt_build",
        "Build a prompt for review",
        "n/a",
        "stage-5.2",
    )


def test_schema_version() -> None:
    print("\n[1] schema version")
    check("schema version is 1", WORK_SESSION_STORE_SCHEMA_VERSION == 1)


def test_append_and_load_round_trip(tmp_dir: Path) -> None:
    print("\n[2] append_session / load_sessions round trip")
    sessions_path = tmp_dir / "sessions.jsonl"
    sessions: dict[str, AIWorkSession] = {}
    created = create_work_session(
        sessions=sessions,
        session_id="session-500",
        task=_task(),
        created_at="2026-07-06T09:00:00Z",
    )
    digest_one = append_session(sessions_path=sessions_path, session=created)
    check("append returns a hex digest", isinstance(digest_one, str) and len(digest_one) == 64)

    loaded = load_sessions(sessions_path=sessions_path)
    check("one session loaded", len(loaded) == 1)
    check("loaded session matches appended session", loaded[0] == created)

    digest_two = append_session(sessions_path=sessions_path, session=created)
    check("appending identical session is deterministic (same digest)", digest_one == digest_two)


def test_latest_snapshot_wins(tmp_dir: Path) -> None:
    print("\n[3] append-only: latest snapshot per session_id wins")
    sessions_path = tmp_dir / "sessions_multi.jsonl"
    sessions: dict[str, AIWorkSession] = {}
    created = create_work_session(
        sessions=sessions,
        session_id="session-600",
        task=_task(),
        created_at="2026-07-06T09:00:00Z",
    )
    append_session(sessions_path=sessions_path, session=created)

    queued = transition_status(
        sessions=sessions,
        session_id="session-600",
        new_status="queued",
        updated_at="2026-07-06T09:01:00Z",
    )
    append_session(sessions_path=sessions_path, session=queued)

    loaded = load_sessions(sessions_path=sessions_path)
    check("still one distinct session_id", len(loaded) == 1)
    check("latest status (queued) wins over draft", loaded[0].status == "queued")

    single = load_session(sessions_path=sessions_path, session_id="session-600")
    check("load_session returns the latest snapshot", single is not None and single.status == "queued")
    check(
        "load_session returns None for unknown id",
        load_session(sessions_path=sessions_path, session_id="does-not-exist") is None,
    )
    check("list_sessions returns the one session_id", list_sessions(sessions_path=sessions_path) == ("session-600",))


def test_missing_file_reads_empty(tmp_dir: Path) -> None:
    print("\n[4] missing file reads as empty store")
    missing_path = tmp_dir / "does_not_exist.jsonl"
    check("load_sessions on missing file is empty", load_sessions(sessions_path=missing_path) == ())
    check("list_sessions on missing file is empty", list_sessions(sessions_path=missing_path) == ())
    check("load_session on missing file is None", load_session(sessions_path=missing_path, session_id="x") is None)


def test_append_event(tmp_dir: Path) -> None:
    print("\n[5] append_event")
    events_path = tmp_dir / "events.jsonl"
    digest = append_event(
        events_path=events_path,
        event={
            "event_type": "SESSION_CREATED",
            "session_id": "session-700",
            "created_at": "2026-07-06T09:00:00Z",
        },
    )
    check("append_event returns a hex digest", isinstance(digest, str) and len(digest) == 64)
    try:
        append_event(events_path=events_path, event="not-a-dict")
        check("non-dict event rejected", False)
    except ValueError:
        check("non-dict event rejected", True)


def test_invalid_line_raises(tmp_dir: Path) -> None:
    print("\n[6] invalid JSONL line raises a stable error")
    bad_path = tmp_dir / "bad_sessions.jsonl"
    bad_path.write_text("not-json\n", encoding="utf-8", newline="\n")
    try:
        load_sessions(sessions_path=bad_path)
        check("invalid line raises ValueError", False)
    except ValueError as exc:
        check("invalid line raises ValueError", "INVALID_SESSION_LINE" in str(exc))


def main() -> int:
    tmp_dir = Path(tempfile.mkdtemp(prefix="scos_stage52_store_"))
    try:
        test_schema_version()
        test_append_and_load_round_trip(tmp_dir)
        test_latest_snapshot_wins(tmp_dir)
        test_missing_file_reads_empty(tmp_dir)
        test_append_event(tmp_dir)
        test_invalid_line_raises(tmp_dir)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    print(f"\n RESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
