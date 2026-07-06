"""test_state_repository.py - SCOS Stage 6.3 state repository suite.

Plain executable script (no pytest). Covers deterministic sha256-derived
ids, repository write helpers, and snapshot retrieval through the
repository facade.

Run: python scos/control_center/tests/test_state_repository.py
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
from state_models import DurableStateError  # noqa: E402
from state_repository import ControlCenterStateRepository  # noqa: E402

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


def _new_repo(tmp: Path) -> ControlCenterStateRepository:
    store = SQLiteStateStore(repo_root=tmp)
    repo = ControlCenterStateRepository(store)
    repo.initialize_state("t0")
    return repo


def test_1_deterministic_ids_are_stable() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="scos_state_repo_"))
    try:
        repo = _new_repo(tmp)
        first = repo.record_backend_request(
            request_id="req-1",
            request_type="health_check",
            session_id=None,
            payload_json="{}",
            created_at="t1",
        )
        check("first request stored", first.command_id.startswith("cmd_"))
        duplicate = repo.record_backend_request(
            request_id="req-1",
            request_type="health_check",
            session_id=None,
            payload_json="{}",
            created_at="t1",
        )
        check(
            "same inputs produce duplicate_id error (stable id)",
            isinstance(duplicate, DurableStateError)
            and duplicate.error_kind == "duplicate_id",
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_2_record_session_and_approval_and_result() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="scos_state_repo_"))
    try:
        repo = _new_repo(tmp)
        session = repo.record_session_state(
            session_key="task-1:agent-1", status="planned", created_at="t1"
        )
        check("session recorded", session.status == "planned")

        approval = repo.record_operator_approval(
            approval_key="approval-1",
            approval_type="command_approval",
            subject_type="command",
            subject_id="cmd-1",
            decision="approved",
            decided_by="operator",
            decided_at="t2",
        )
        check("approval recorded", approval.decision == "approved")

        result = repo.record_agent_result(
            result_key="result-1",
            result_type="verification",
            subject_type="command",
            subject_id="cmd-1",
            verdict="pass",
            created_at="t3",
        )
        check("result recorded", result.verdict == "pass")

        event = repo.append_control_center_event(
            event_key="event-1",
            event_type="command_state_changed",
            source="control_center",
            subject_type="command",
            subject_id="cmd-1",
            sequence=0,
            created_at="t4",
        )
        check("event appended", event.sequence == 0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_3_get_current_state_snapshot() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="scos_state_repo_"))
    try:
        repo = _new_repo(tmp)
        repo.record_session_state(
            session_key="task-1:agent-1", status="planned", created_at="t1"
        )
        snapshot = repo.get_current_state_snapshot("t2")
        check("snapshot is dict", isinstance(snapshot, dict))
        check("snapshot wal enabled", snapshot.get("wal_enabled") is True)
        check("snapshot counts sessions", snapshot["counts"]["sessions"] == 1)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    tests = [
        test_1_deterministic_ids_are_stable,
        test_2_record_session_and_approval_and_result,
        test_3_get_current_state_snapshot,
    ]
    for test in tests:
        print(f"{test.__name__}:")
        test()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
