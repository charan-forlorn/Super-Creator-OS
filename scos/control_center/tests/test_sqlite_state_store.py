"""test_sqlite_state_store.py - SCOS Stage 6.3 SQLite WAL state store suite.

Plain executable script (no pytest). Covers WAL mode verification,
deterministic ordering, duplicate-id/missing-record error handling, and
persistence round trips for all five durable record types.

Run: python scos/control_center/tests/test_sqlite_state_store.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
sys.path.insert(0, str(_PACKAGE))

from sqlite_state_store import SQLiteStateStore  # noqa: E402
from state_models import (  # noqa: E402
    DurableApprovalRecord,
    DurableCommandRecord,
    DurableEventRecord,
    DurableResultRecord,
    DurableSessionRecord,
    DurableStateError,
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


def test_1_initialize_enables_wal() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="scos_state_store_"))
    try:
        store = SQLiteStateStore(repo_root=tmp, db_path=Path("state/cc.sqlite3"))
        error = store.initialize(applied_at="2026-07-07T00:00:00Z")
        check("initialize succeeds", error is None)
        health = store.health_snapshot(checked_at="2026-07-07T00:01:00Z")
        check("health ok", health["ok"] is True)
        check("wal enabled", health["wal_enabled"] is True)
        check("db file created", store.db_path.is_file())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_2_commands_round_trip_and_ordering() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="scos_state_store_"))
    try:
        store = SQLiteStateStore(repo_root=tmp)
        store.initialize(applied_at="t0")
        first = DurableCommandRecord.of("cmd-a", "health_check", "draft", "t1")
        second = DurableCommandRecord.of("cmd-b", "health_check", "draft", "t2")
        store.insert_command(second)
        store.insert_command(first)
        commands = store.list_commands()
        check(
            "commands ordered by created_at then id",
            [c.command_id for c in commands] == ["cmd-a", "cmd-b"],
        )
        fetched = store.get_command("cmd-a")
        check("get_command returns record", fetched.command_id == "cmd-a")
        missing = store.get_command("cmd-missing")
        check("missing command is DurableStateError", isinstance(missing, DurableStateError))
        check("missing error_kind is not_found", missing.error_kind == "not_found")
        duplicate = store.insert_command(first)
        check("duplicate command is DurableStateError", isinstance(duplicate, DurableStateError))
        check("duplicate error_kind", duplicate.error_kind == "duplicate_id")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_3_sessions_round_trip_and_filter() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="scos_state_store_"))
    try:
        store = SQLiteStateStore(repo_root=tmp)
        store.initialize(applied_at="t0")
        store.insert_session(DurableSessionRecord.of("s-1", "planned", "t1"))
        store.insert_session(DurableSessionRecord.of("s-2", "working", "t2"))
        planned = store.list_sessions(status="planned")
        check("filter by status", [s.session_id for s in planned] == ["s-1"])
        missing = store.get_session("s-missing")
        check("missing session error", isinstance(missing, DurableStateError))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_4_events_append_and_sequence_order() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="scos_state_store_"))
    try:
        store = SQLiteStateStore(repo_root=tmp)
        store.initialize(applied_at="t0")
        store.append_event(
            DurableEventRecord.of("evt-2", "x", "s", "command", "cmd-1", "t2", 2)
        )
        store.append_event(
            DurableEventRecord.of("evt-1", "x", "s", "command", "cmd-1", "t1", 1)
        )
        events = store.list_events(subject_type="command", subject_id="cmd-1")
        check(
            "events ordered by sequence",
            [e.event_id for e in events] == ["evt-1", "evt-2"],
        )
        duplicate = store.append_event(
            DurableEventRecord.of("evt-1", "x", "s", "command", "cmd-1", "t1", 1)
        )
        check("duplicate event error", isinstance(duplicate, DurableStateError))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_5_approvals_and_results_round_trip() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="scos_state_store_"))
    try:
        store = SQLiteStateStore(repo_root=tmp)
        store.initialize(applied_at="t0")
        store.insert_approval(
            DurableApprovalRecord.of(
                "appr-1", "command_approval", "command", "cmd-1", "approved",
                "operator", "t1",
            )
        )
        approvals = store.list_approvals(subject_type="command", subject_id="cmd-1")
        check("approval persisted", len(approvals) == 1)

        store.insert_result(
            DurableResultRecord.of(
                "res-1", "verification", "command", "cmd-1", "pass", "t1"
            )
        )
        results = store.list_results(subject_type="command", subject_id="cmd-1")
        check("result persisted", len(results) == 1)
        check("result verdict preserved", results[0].verdict == "pass")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_6_rejects_path_escaping_repo_root() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="scos_state_store_"))
    try:
        raised = False
        try:
            SQLiteStateStore(repo_root=tmp, db_path=Path("../outside.sqlite3"))
        except ValueError:
            raised = True
        check("escaping path rejected at construction", raised)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    tests = [
        test_1_initialize_enables_wal,
        test_2_commands_round_trip_and_ordering,
        test_3_sessions_round_trip_and_filter,
        test_4_events_append_and_sequence_order,
        test_5_approvals_and_results_round_trip,
        test_6_rejects_path_escaping_repo_root,
    ]
    for test in tests:
        print(f"{test.__name__}:")
        test()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
