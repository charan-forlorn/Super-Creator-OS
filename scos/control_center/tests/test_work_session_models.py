"""test_work_session_models.py - SCOS Stage 5.2 work session model suite.

Plain executable script (no pytest). Covers to_dict key order, frozen
immutability, tuple serialization, deterministic factories, and enum
enforcement for all five Stage 5.2 models.

Run: python scos/control_center/tests/test_work_session_models.py
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent

sys.path.insert(0, str(_PACKAGE))

from work_session_models import (  # noqa: E402
    AI_WORK_SESSION_SCHEMA_VERSION,
    ALLOWED_AGENT_NAMES,
    ALLOWED_PRIORITIES,
    ALLOWED_RUNTIME_TYPES,
    ALLOWED_SESSION_STATUSES,
    ALLOWED_TASK_TYPES,
    MANUAL_CLIPBOARD_RUNTIME_ID,
    AgentAssignment,
    AgentRuntime,
    AIWorkSession,
    AIWorkSessionError,
    AIWorkTask,
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


def _runtime() -> AgentRuntime:
    return AgentRuntime.of(
        "claude-code-cli",
        "claude_code",
        "claude_code_cli",
        "Claude Code (CLI)",
        supported_task_types=("planning", "implementation"),
        enabled=True,
        metadata=(("origin", "built-in"),),
    )


def _task() -> AIWorkTask:
    return AIWorkTask.of(
        "task-001",
        "Draft Stage 5.2 contract",
        "planning",
        "Produce the AI Work Session Manager contract",
        "Stage 5.2 requirements from the operator",
        "stage-5.2",
        priority="high",
        metadata=(("origin", "operator"),),
    )


def _assignment() -> AgentAssignment:
    return AgentAssignment.of(
        "asn-001",
        "task-001",
        "claude_code",
        "claude-code-cli",
        "best available runtime for planning tasks",
        "2026-07-06T09:00:00Z",
        metadata=(("k", "v"),),
    )


def _session() -> AIWorkSession:
    return AIWorkSession.of(
        "session-001",
        _task(),
        "draft",
        "2026-07-06T09:00:00Z",
        "2026-07-06T09:00:00Z",
        metadata=(("k", "v"),),
    )


def test_schema_version_and_constants() -> None:
    print("\n[1] schema version + allowed constants")
    check("schema version is 1", AI_WORK_SESSION_SCHEMA_VERSION == 1)
    check("four agent names", len(ALLOWED_AGENT_NAMES) == 4)
    check("eight runtime types", len(ALLOWED_RUNTIME_TYPES) == 8)
    check("nine task types", len(ALLOWED_TASK_TYPES) == 9)
    check("four priorities", len(ALLOWED_PRIORITIES) == 4)
    check("thirteen session statuses", len(ALLOWED_SESSION_STATUSES) == 13)
    check("manual_clipboard constant matches runtime type", MANUAL_CLIPBOARD_RUNTIME_ID == "manual_clipboard")
    check("manual_clipboard always in runtime types", "manual_clipboard" in ALLOWED_RUNTIME_TYPES)


def test_to_dict_key_order() -> None:
    print("\n[2] to_dict explicit key order")
    check(
        "AgentRuntime key order",
        list(_runtime().to_dict().keys())
        == [
            "runtime_id",
            "agent_name",
            "runtime_type",
            "display_name",
            "supported_task_types",
            "enabled",
            "metadata",
        ],
    )
    check(
        "AIWorkTask key order",
        list(_task().to_dict().keys())
        == [
            "task_id",
            "title",
            "task_type",
            "objective",
            "input_summary",
            "source_stage",
            "priority",
            "metadata",
        ],
    )
    check(
        "AgentAssignment key order",
        list(_assignment().to_dict().keys())
        == [
            "assignment_id",
            "task_id",
            "agent_name",
            "runtime_id",
            "reason",
            "assigned_at",
            "metadata",
        ],
    )
    check(
        "AIWorkSession key order",
        list(_session().to_dict().keys())
        == [
            "session_id",
            "schema_version",
            "task",
            "assignment",
            "status",
            "created_at",
            "updated_at",
            "result_summary",
            "next_action",
            "metadata",
        ],
    )
    error = AIWorkSessionError.of("UNKNOWN_SESSION", "no such session", "assign_runtime")
    check(
        "AIWorkSessionError key order",
        list(error.to_dict().keys())
        == ["ok", "schema_version", "error_kind", "error_detail", "failed_step", "metadata"],
    )
    check("session assignment is None by default", _session().to_dict()["assignment"] is None)


def test_immutability() -> None:
    print("\n[3] frozen immutability")
    session = _session()
    frozen = 0
    for field_name, value in (("status", "queued"), ("result_summary", "x"), ("metadata", ())):
        try:
            setattr(session, field_name, value)
        except dataclasses.FrozenInstanceError:
            frozen += 1
    check("AIWorkSession fields frozen", frozen == 3)
    runtime = _runtime()
    try:
        runtime.enabled = False
        check("AgentRuntime frozen", False)
    except dataclasses.FrozenInstanceError:
        check("AgentRuntime frozen", True)


def test_tuple_serialization_and_no_mutables() -> None:
    print("\n[4] tuple serialization + no mutable fields")
    task = AIWorkTask.of(
        "task-002",
        "Review",
        "review",
        "Review the draft",
        "n/a",
        "stage-5.2",
        metadata={"origin": "operator"},
    )
    check("dict metadata normalized to tuple pairs", task.metadata == (("origin", "operator"),))
    payload = task.to_dict()
    check("metadata serialized as list of lists", payload["metadata"] == [["origin", "operator"]])
    runtime = AgentRuntime.of(
        "codex-cli",
        "codex",
        "codex_cli",
        "Codex (CLI)",
        supported_task_types=["implementation", "review"],
    )
    check(
        "list supported_task_types normalized to tuple",
        runtime.supported_task_types == ("implementation", "review"),
    )
    for model in (task, _runtime(), _assignment(), _session()):
        mutable = [
            field.name
            for field in dataclasses.fields(model)
            if isinstance(getattr(model, field.name), (dict, list, set))
        ]
        check(f"{type(model).__name__} exposes no mutable fields", mutable == [])


def test_deterministic_factories() -> None:
    print("\n[5] deterministic factories")
    check("AIWorkTask.of deterministic", _task() == _task())
    check("AIWorkSession.of deterministic", _session() == _session())
    check("to_dict deterministic", _session().to_dict() == _session().to_dict())


def test_model_enforcement() -> None:
    print("\n[6] enum enforcement")
    try:
        AgentRuntime.of("r", "not_an_agent", "claude_code_cli", "X")
        check("invalid agent_name rejected", False)
    except ValueError:
        check("invalid agent_name rejected", True)
    try:
        AgentRuntime.of("r", "claude_code", "not_a_runtime_type", "X")
        check("invalid runtime_type rejected", False)
    except ValueError:
        check("invalid runtime_type rejected", True)
    try:
        AgentRuntime.of("r", "claude_code", "claude_code_cli", "X", supported_task_types=("not_a_task",))
        check("invalid supported_task_types entry rejected", False)
    except ValueError:
        check("invalid supported_task_types entry rejected", True)
    try:
        AIWorkTask.of("t", "T", "not_a_task_type", "obj", "in", "stage")
        check("invalid task_type rejected", False)
    except ValueError:
        check("invalid task_type rejected", True)
    try:
        AIWorkTask.of("t", "T", "planning", "obj", "in", "stage", priority="sideways")
        check("invalid priority rejected", False)
    except ValueError:
        check("invalid priority rejected", True)
    try:
        AgentAssignment.of("a", "t", "not_an_agent", "r", "reason", "2026-01-01T00:00:00Z")
        check("invalid assignment agent_name rejected", False)
    except ValueError:
        check("invalid assignment agent_name rejected", True)
    try:
        AIWorkSession.of("s", _task(), "not_a_status", "t", "t")
        check("invalid session status rejected", False)
    except ValueError:
        check("invalid session status rejected", True)
    try:
        AIWorkSession.of("s", "not-a-task", "draft", "t", "t")
        check("non-AIWorkTask task rejected", False)
    except ValueError:
        check("non-AIWorkTask task rejected", True)
    try:
        AIWorkSession.of("s", _task(), "draft", "t", "t", assignment="not-an-assignment")
        check("non-AgentAssignment assignment rejected", False)
    except ValueError:
        check("non-AgentAssignment assignment rejected", True)


def main() -> int:
    test_schema_version_and_constants()
    test_to_dict_key_order()
    test_immutability()
    test_tuple_serialization_and_no_mutables()
    test_deterministic_factories()
    test_model_enforcement()
    print(f"\n RESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
