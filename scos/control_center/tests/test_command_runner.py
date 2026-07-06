"""test_command_runner.py - SCOS Stage 5.1 allowlisted command runner suite.

Plain executable script (no pytest). Only dry-run and blocked paths are
exercised: ``subprocess.run`` is replaced with a guard that raises if any
test ever tries to spawn a real process, so this suite is fast, offline, and
side-effect free (queue/event files live in a temporary directory).

Run: python scos/control_center/tests/test_command_runner.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent

sys.path.insert(0, str(_PACKAGE))

import command_runner  # noqa: E402
from command_models import ApprovedCommand, CommandDraft  # noqa: E402
from command_runner import (  # noqa: E402
    COMMAND_TIMEOUT_SECONDS,
    CONTROL_CENTER_COMMAND_RUNNER_SCHEMA_VERSION,
    run_approved_command,
)
from event_log import read_command_events  # noqa: E402

_PASS = 0
_FAIL = 0

_STARTED_AT = "2026-07-05T10:20:00Z"
_FINISHED_AT = "2026-07-05T10:21:00Z"


class _SubprocessGuard:
    """Fails the suite if any code path tries to spawn a real subprocess."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("subprocess.run must never be called in this suite")


_GUARD = _SubprocessGuard()


@pytest.fixture(autouse=True)
def _guarded_subprocess():
    """Patch command_runner.subprocess.run only for this module's tests.

    The guard must not leak into other test modules that run later in the
    same pytest session (e.g. test_stage5_final_certification.py's
    read-only integration test, which spawns real subprocesses).
    """
    original_run = command_runner.subprocess.run
    _GUARD.calls = 0
    command_runner.subprocess.run = _GUARD
    try:
        yield
    finally:
        command_runner.subprocess.run = original_run


def check(name: str, cond: bool) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}")


def _approved(command_type: str = "RUN_SMOKE_CHECK", args=()) -> ApprovedCommand:
    return ApprovedCommand.of(
        command_id="cmd-001",
        command_type=command_type,
        approved_by="operator-a",
        approved_at="2026-07-05T10:05:00Z",
        args=args,
    )


def _run(command: ApprovedCommand, *, event_log_path=None, dry_run=True):
    return run_approved_command(
        repo_root=".",
        approved_command=command,
        started_at=_STARTED_AT,
        finished_at=_FINISHED_AT,
        event_log_path=event_log_path,
        dry_run=dry_run,
    )


def test_schema_version() -> None:
    print("\n[1] schema version + finite timeout")
    check("schema version is 1", CONTROL_CENTER_COMMAND_RUNNER_SCHEMA_VERSION == 1)
    check("timeout finite and deterministic", COMMAND_TIMEOUT_SECONDS == 900)


def test_dry_run_never_executes() -> None:
    print("\n[2] dry_run does not execute subprocess")
    for command_type in (
        "RUN_SMOKE_CHECK",
        "RUN_RELEASE_CHECK",
        "RUN_SECURITY_SCAN",
        "OPEN_STAGE5_HANDOFF",
        "GENERATE_STATUS_SNAPSHOT",
    ):
        result = _run(_approved(command_type))
        check(f"{command_type} dry-run ok", result.ok and result.exit_code == 0)
    gate = _approved("RUN_STAGE4_FINAL_GATE", args=(("checked_at", "2026-07-05T10:00:00Z"),))
    result = _run(gate)
    check("RUN_STAGE4_FINAL_GATE dry-run ok", result.ok)
    check("no subprocess was ever spawned", _GUARD.calls == 0)


def test_dry_run_plan_metadata() -> None:
    print("\n[3] planned command in metadata, deterministic")
    first = _run(_approved("GENERATE_STATUS_SNAPSHOT"))
    second = _run(_approved("GENERATE_STATUS_SNAPSHOT"))
    check("dry-run result deterministic", first == second)
    metadata = dict(first.metadata)
    check("dry_run flag recorded", metadata.get("dry_run") == "true")
    planned = metadata.get("planned_command", "")
    check("plan lists read-only git status", "git status --short --untracked-files=all" in planned)
    check("plan lists rev-parse HEAD", "git rev-parse HEAD" in planned)
    check("plan lists branch query", "git branch --show-current" in planned)
    smoke_plan = dict(_run(_approved()).metadata).get("planned_command", "")
    check("smoke plan targets scripts/test_smoke.py", smoke_plan.endswith("scripts/test_smoke.py"))
    handoff_plan = dict(_run(_approved("OPEN_STAGE5_HANDOFF")).metadata).get("planned_command", "")
    check(
        "handoff plan is a file-existence check only",
        handoff_plan == "verify docs/roadmap/STAGE5_HANDOFF.md exists",
    )


def test_unapproved_command_rejected() -> None:
    print("\n[4] unapproved command rejected")
    draft = CommandDraft.of(
        command_id="cmd-001",
        command_type="RUN_SMOKE_CHECK",
        requested_by="operator-a",
        created_at="2026-07-05T10:00:00Z",
        summary="draft only, never approved",
    )
    try:
        _run(draft)  # type: ignore[arg-type]
        check("draft cannot run", False)
    except ValueError as exc:
        check("draft cannot run", str(exc).startswith("NOT_AN_APPROVED_COMMAND:"))
    check("no subprocess was ever spawned", _GUARD.calls == 0)


def test_unknown_and_forbidden_types_blocked(tmp: Path) -> None:
    print("\n[5] unknown/forbidden command types blocked")
    log = tmp / "blocked-events.jsonl"
    unknown = _approved("LAUNCH_ROCKETS")
    # Even with dry_run=False a non-allowlisted type must never execute.
    result = _run(unknown, event_log_path=log, dry_run=False)
    check("unknown type not ok", result.ok is False)
    check("unknown type exit_code -1", result.exit_code == -1)
    check("blocked flag in metadata", dict(result.metadata).get("blocked") == "true")
    events = read_command_events(event_log_path=log)
    check("COMMAND_BLOCKED logged", [e.event_type for e in events] == ["COMMAND_BLOCKED"])
    check("blocked status recorded", events[0].status == "blocked")
    check("no subprocess was ever spawned", _GUARD.calls == 0)


def test_gate_requires_checked_at(tmp: Path) -> None:
    print("\n[6] RUN_STAGE4_FINAL_GATE requires checked_at")
    log = tmp / "gate-events.jsonl"
    gate = _approved("RUN_STAGE4_FINAL_GATE", args=())
    result = _run(gate, event_log_path=log, dry_run=False)
    check("missing checked_at blocked", result.ok is False and result.exit_code == -1)
    check(
        "blocked reason recorded",
        dict(result.metadata).get("blocked_reason") == "missing required arg: checked_at",
    )
    events = read_command_events(event_log_path=log)
    check("only COMMAND_BLOCKED logged", [e.event_type for e in events] == ["COMMAND_BLOCKED"])
    blank = _approved("RUN_STAGE4_FINAL_GATE", args=(("checked_at", "   "),))
    check("blank checked_at blocked", _run(blank, dry_run=False).ok is False)
    check("no subprocess was ever spawned", _GUARD.calls == 0)


def test_event_log_lifecycle_dry_run(tmp: Path) -> None:
    print("\n[7] event log records started/completed (dry-run)")
    log = tmp / "lifecycle-events.jsonl"
    result = _run(_approved(), event_log_path=log, dry_run=True)
    check("dry-run result ok", result.ok)
    events = read_command_events(event_log_path=log)
    check(
        "STARTED then COMPLETED",
        [e.event_type for e in events] == ["COMMAND_STARTED", "COMMAND_COMPLETED"],
    )
    check("started uses started_at", events[0].created_at == _STARTED_AT)
    check("completed uses finished_at", events[1].created_at == _FINISHED_AT)
    check("statuses pending then success", [e.status for e in events] == ["pending", "success"])
    again = tmp / "lifecycle-events-2.jsonl"
    _run(_approved(), event_log_path=again, dry_run=True)
    check(
        "event ids deterministic across runs",
        [e.event_id for e in read_command_events(event_log_path=again)]
        == [e.event_id for e in events],
    )
    check("no subprocess was ever spawned", _GUARD.calls == 0)


def main() -> int:
    original_run = command_runner.subprocess.run
    _GUARD.calls = 0
    command_runner.subprocess.run = _GUARD
    try:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            test_schema_version()
            test_dry_run_never_executes()
            test_dry_run_plan_metadata()
            test_unapproved_command_rejected()
            test_unknown_and_forbidden_types_blocked(tmp)
            test_gate_requires_checked_at(tmp)
            test_event_log_lifecycle_dry_run(tmp)
    finally:
        command_runner.subprocess.run = original_run
    print(f"\n RESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
