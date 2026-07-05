"""test_work_session_manager.py - SCOS Stage 5.2 work session manager suite.

Plain executable script (no pytest). Covers session creation, runtime
assignment, valid/invalid status transitions, unknown-runtime and
unsupported-task-type rejection, duplicate session id rejection, terminal
session immutability, and the manual_clipboard fallback path.

Run: python scos/control_center/tests/test_work_session_manager.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent

sys.path.insert(0, str(_PACKAGE))

from work_session_manager import (  # noqa: E402
    ALLOWED_TRANSITIONS,
    TERMINAL_STATUSES,
    WORK_SESSION_MANAGER_SCHEMA_VERSION,
    assign_runtime,
    cancel_session,
    complete_session,
    create_work_session,
    transition_status,
    validate_transition,
)
from work_session_models import AIWorkSession, AIWorkSessionError, AIWorkTask  # noqa: E402

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


def _task(task_type: str = "planning") -> AIWorkTask:
    return AIWorkTask.of(
        "task-001",
        "Draft Stage 5.2 contract",
        task_type,
        "Produce the AI Work Session Manager contract",
        "Stage 5.2 requirements from the operator",
        "stage-5.2",
    )


def test_schema_version() -> None:
    print("\n[1] schema version")
    check("schema version is 1", WORK_SESSION_MANAGER_SCHEMA_VERSION == 1)


def test_validate_transition() -> None:
    print("\n[2] validate_transition")
    check("draft -> queued allowed", validate_transition("draft", "queued") == (True, None))
    ok, error = validate_transition("draft", "done")
    check("draft -> done rejected", not ok and error is not None)
    ok, error = validate_transition("not_a_status", "draft")
    check("unknown current_status rejected", not ok and error is not None)
    check("cancelled is terminal (no outgoing)", ALLOWED_TRANSITIONS["cancelled"] == ())
    check("done is terminal (no outgoing)", ALLOWED_TRANSITIONS["done"] == ())
    for status in TERMINAL_STATUSES:
        check(f"{status} has no allowed transitions", ALLOWED_TRANSITIONS[status] == ())


def test_create_work_session() -> None:
    print("\n[3] create_work_session")
    sessions: dict[str, AIWorkSession] = {}
    result = create_work_session(
        sessions=sessions,
        session_id="session-001",
        task=_task(),
        created_at="2026-07-06T09:00:00Z",
    )
    check("returns AIWorkSession", isinstance(result, AIWorkSession))
    check("initial status is draft", isinstance(result, AIWorkSession) and result.status == "draft")
    check("session registered in sessions dict", sessions.get("session-001") is result)

    duplicate = create_work_session(
        sessions=sessions,
        session_id="session-001",
        task=_task(),
        created_at="2026-07-06T09:05:00Z",
    )
    check("duplicate session_id rejected", isinstance(duplicate, AIWorkSessionError))
    check(
        "duplicate rejection has stable error_kind",
        isinstance(duplicate, AIWorkSessionError) and duplicate.error_kind == "DUPLICATE_SESSION_ID",
    )
    check("original session untouched by duplicate attempt", sessions["session-001"] is result)

    bad_task = create_work_session(
        sessions=sessions,
        session_id="session-002",
        task="not-a-task",
        created_at="2026-07-06T09:00:00Z",
    )
    check("non-AIWorkTask rejected", isinstance(bad_task, AIWorkSessionError))


def test_assign_runtime() -> None:
    print("\n[4] assign_runtime")
    sessions: dict[str, AIWorkSession] = {}
    create_work_session(
        sessions=sessions,
        session_id="session-010",
        task=_task("planning"),
        created_at="2026-07-06T09:00:00Z",
    )
    assigned = assign_runtime(
        sessions=sessions,
        session_id="session-010",
        runtime_id="claude-code-cli",
        assignment_id="asn-010",
        reason="best fit for planning",
        assigned_at="2026-07-06T09:01:00Z",
    )
    check("assignment succeeds", isinstance(assigned, AIWorkSession))
    check(
        "status becomes assigned",
        isinstance(assigned, AIWorkSession) and assigned.status == "assigned",
    )
    check(
        "assignment attached",
        isinstance(assigned, AIWorkSession)
        and assigned.assignment is not None
        and assigned.assignment.runtime_id == "claude-code-cli",
    )

    unknown_session = assign_runtime(
        sessions=sessions,
        session_id="does-not-exist",
        runtime_id="claude-code-cli",
        assignment_id="asn-x",
        reason="x",
        assigned_at="2026-07-06T09:01:00Z",
    )
    check(
        "unknown session rejected",
        isinstance(unknown_session, AIWorkSessionError)
        and unknown_session.error_kind == "UNKNOWN_SESSION",
    )

    sessions_unknown_runtime: dict[str, AIWorkSession] = {}
    create_work_session(
        sessions=sessions_unknown_runtime,
        session_id="session-011",
        task=_task("planning"),
        created_at="2026-07-06T09:00:00Z",
    )
    unknown_runtime = assign_runtime(
        sessions=sessions_unknown_runtime,
        session_id="session-011",
        runtime_id="does-not-exist",
        assignment_id="asn-011",
        reason="x",
        assigned_at="2026-07-06T09:02:00Z",
    )
    check(
        "unknown runtime rejected",
        isinstance(unknown_runtime, AIWorkSessionError)
        and unknown_runtime.error_kind == "UNKNOWN_RUNTIME",
    )
    check(
        "session remains draft after unknown-runtime rejection",
        sessions_unknown_runtime["session-011"].status == "draft"
        and sessions_unknown_runtime["session-011"].assignment is None,
    )

    sessions2: dict[str, AIWorkSession] = {}
    create_work_session(
        sessions=sessions2,
        session_id="session-020",
        task=_task("status_update"),
        created_at="2026-07-06T09:00:00Z",
    )
    unsupported = assign_runtime(
        sessions=sessions2,
        session_id="session-020",
        runtime_id="codex-cli",
        assignment_id="asn-020",
        reason="x",
        assigned_at="2026-07-06T09:01:00Z",
    )
    check(
        "unsupported task_type rejected",
        isinstance(unsupported, AIWorkSessionError)
        and unsupported.error_kind == "UNSUPPORTED_TASK_TYPE",
    )

    fallback = assign_runtime(
        sessions=sessions2,
        session_id="session-020",
        runtime_id="manual-clipboard",
        assignment_id="asn-021",
        reason="no dedicated runtime yet; hand off manually",
        assigned_at="2026-07-06T09:02:00Z",
    )
    check(
        "manual_clipboard fallback succeeds for any task_type",
        isinstance(fallback, AIWorkSession) and fallback.status == "assigned",
    )
    check(
        "manual_clipboard assignment recorded",
        isinstance(fallback, AIWorkSession)
        and fallback.assignment is not None
        and fallback.assignment.runtime_id == "manual-clipboard",
    )

    invalid_status = assign_runtime(
        sessions=sessions,
        session_id="session-010",
        runtime_id="claude-code-cli",
        assignment_id="asn-030",
        reason="x",
        assigned_at="2026-07-06T09:03:00Z",
    )
    check(
        "reassign while already assigned rejected",
        isinstance(invalid_status, AIWorkSessionError)
        and invalid_status.error_kind == "INVALID_STATUS_FOR_ASSIGNMENT",
    )


def test_transition_status() -> None:
    print("\n[5] transition_status")
    sessions: dict[str, AIWorkSession] = {}
    create_work_session(
        sessions=sessions,
        session_id="session-100",
        task=_task("implementation"),
        created_at="2026-07-06T09:00:00Z",
    )
    step1 = transition_status(
        sessions=sessions,
        session_id="session-100",
        new_status="queued",
        updated_at="2026-07-06T09:01:00Z",
    )
    check("draft -> queued succeeds", isinstance(step1, AIWorkSession) and step1.status == "queued")

    invalid = transition_status(
        sessions=sessions,
        session_id="session-100",
        new_status="done",
        updated_at="2026-07-06T09:02:00Z",
    )
    check(
        "queued -> done rejected",
        isinstance(invalid, AIWorkSessionError) and invalid.error_kind == "INVALID_TRANSITION",
    )
    check(
        "session status unchanged after invalid transition",
        sessions["session-100"].status == "queued",
    )

    assign_runtime(
        sessions=sessions,
        session_id="session-100",
        runtime_id="codex-cli",
        assignment_id="asn-100",
        reason="implementation work",
        assigned_at="2026-07-06T09:03:00Z",
    )
    for status, updated_at in (
        ("sent_to_agent", "2026-07-06T09:04:00Z"),
        ("agent_working", "2026-07-06T09:05:00Z"),
        ("result_ready", "2026-07-06T09:06:00Z"),
        ("review_required", "2026-07-06T09:07:00Z"),
        ("approved", "2026-07-06T09:08:00Z"),
    ):
        result = transition_status(
            sessions=sessions,
            session_id="session-100",
            new_status=status,
            updated_at=updated_at,
        )
        check(f"transition to {status} succeeds", isinstance(result, AIWorkSession) and result.status == status)

    done = complete_session(
        sessions=sessions,
        session_id="session-100",
        updated_at="2026-07-06T09:09:00Z",
        result_summary="implementation complete, tests pass",
    )
    check("complete_session reaches done", isinstance(done, AIWorkSession) and done.status == "done")
    check(
        "complete_session sets result_summary",
        isinstance(done, AIWorkSession) and done.result_summary == "implementation complete, tests pass",
    )

    mutate_after_done = transition_status(
        sessions=sessions,
        session_id="session-100",
        new_status="queued",
        updated_at="2026-07-06T09:10:00Z",
    )
    check(
        "terminal session never mutated",
        isinstance(mutate_after_done, AIWorkSessionError)
        and mutate_after_done.error_kind == "SESSION_ALREADY_COMPLETED",
    )
    check("session remains done after mutation attempt", sessions["session-100"].status == "done")


def test_cancel_session() -> None:
    print("\n[6] cancel_session")
    sessions: dict[str, AIWorkSession] = {}
    create_work_session(
        sessions=sessions,
        session_id="session-200",
        task=_task("audit"),
        created_at="2026-07-06T09:00:00Z",
    )
    cancelled = cancel_session(
        sessions=sessions,
        session_id="session-200",
        updated_at="2026-07-06T09:01:00Z",
        reason="no longer needed",
    )
    check("cancel_session succeeds from draft", isinstance(cancelled, AIWorkSession) and cancelled.status == "cancelled")
    check(
        "cancel_session records reason as result_summary",
        isinstance(cancelled, AIWorkSession) and cancelled.result_summary == "no longer needed",
    )

    already = cancel_session(
        sessions=sessions,
        session_id="session-200",
        updated_at="2026-07-06T09:02:00Z",
        reason="again",
    )
    check(
        "cancelling an already-cancelled session rejected",
        isinstance(already, AIWorkSessionError) and already.error_kind == "SESSION_ALREADY_COMPLETED",
    )

    unknown = cancel_session(
        sessions=sessions,
        session_id="does-not-exist",
        updated_at="2026-07-06T09:01:00Z",
        reason="x",
    )
    check(
        "cancelling unknown session rejected",
        isinstance(unknown, AIWorkSessionError) and unknown.error_kind == "UNKNOWN_SESSION",
    )


def test_complete_session_requires_approved() -> None:
    print("\n[7] complete_session requires approved status")
    sessions: dict[str, AIWorkSession] = {}
    create_work_session(
        sessions=sessions,
        session_id="session-300",
        task=_task("review"),
        created_at="2026-07-06T09:00:00Z",
    )
    premature = complete_session(
        sessions=sessions,
        session_id="session-300",
        updated_at="2026-07-06T09:01:00Z",
        result_summary="too early",
    )
    check(
        "complete_session from draft rejected",
        isinstance(premature, AIWorkSessionError) and premature.error_kind == "INVALID_TRANSITION",
    )


def main() -> int:
    test_schema_version()
    test_validate_transition()
    test_create_work_session()
    test_assign_runtime()
    test_transition_status()
    test_cancel_session()
    test_complete_session_requires_approved()
    print(f"\n RESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
