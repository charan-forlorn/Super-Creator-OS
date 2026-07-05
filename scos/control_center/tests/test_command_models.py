"""test_command_models.py - SCOS Stage 5.1 command bridge model suite.

Plain executable script (no pytest). Covers to_dict key order, frozen
immutability, tuple metadata serialization, deterministic factories, and the
no-mutable-field guarantee for all five Stage 5.1 models.

Run: python scos/control_center/tests/test_command_models.py
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent

sys.path.insert(0, str(_PACKAGE))

from command_models import (  # noqa: E402
    ALLOWED_COMMAND_TYPES,
    ALLOWED_EVENT_STATUSES,
    ALLOWED_EVENT_TYPES,
    CONTROL_CENTER_COMMAND_SCHEMA_VERSION,
    ApprovedCommand,
    CommandDraft,
    CommandEvent,
    CommandResult,
    OperatorApproval,
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


def _draft() -> CommandDraft:
    return CommandDraft.of(
        command_id="cmd-001",
        command_type="RUN_SMOKE_CHECK",
        requested_by="operator-a",
        created_at="2026-07-05T10:00:00Z",
        summary="Run the Tier 1 smoke check",
        args=(),
        metadata=(("origin", "control-center"),),
    )


def _event() -> CommandEvent:
    return CommandEvent.of(
        event_id="evt-abc",
        command_id="cmd-001",
        event_type="COMMAND_DRAFTED",
        created_at="2026-07-05T10:00:00Z",
        status="pending",
        message="drafted",
        metadata=(("k", "v"),),
    )


def test_schema_version_and_constants() -> None:
    print("\n[1] schema version + allowed constants")
    check("schema version is 1", CONTROL_CENTER_COMMAND_SCHEMA_VERSION == 1)
    check("six command types", len(ALLOWED_COMMAND_TYPES) == 6)
    check("nine event types", len(ALLOWED_EVENT_TYPES) == 9)
    check("five statuses", len(ALLOWED_EVENT_STATUSES) == 5)


def test_to_dict_key_order() -> None:
    print("\n[2] to_dict explicit key order")
    check(
        "CommandDraft key order",
        list(_draft().to_dict().keys())
        == ["command_id", "command_type", "requested_by", "created_at", "summary", "args", "metadata"],
    )
    approval = OperatorApproval.of(
        approval_id="apr-x",
        command_id="cmd-001",
        approved=True,
        approved_by="operator-a",
        approved_at="2026-07-05T10:05:00Z",
        reason="checks reviewed",
    )
    check(
        "OperatorApproval key order",
        list(approval.to_dict().keys())
        == ["approval_id", "command_id", "approved", "approved_by", "approved_at", "reason", "metadata"],
    )
    approved = ApprovedCommand.of(
        command_id="cmd-001",
        command_type="RUN_SMOKE_CHECK",
        approved_by="operator-a",
        approved_at="2026-07-05T10:05:00Z",
    )
    check(
        "ApprovedCommand key order",
        list(approved.to_dict().keys())
        == ["command_id", "command_type", "approved_by", "approved_at", "args", "metadata"],
    )
    result = CommandResult.of(
        command_id="cmd-001",
        command_type="RUN_SMOKE_CHECK",
        ok=True,
        exit_code=0,
        started_at="2026-07-05T10:06:00Z",
        finished_at="2026-07-05T10:07:00Z",
    )
    check(
        "CommandResult key order",
        list(result.to_dict().keys())
        == [
            "command_id",
            "command_type",
            "ok",
            "exit_code",
            "started_at",
            "finished_at",
            "stdout_excerpt",
            "stderr_excerpt",
            "output_path",
            "metadata",
        ],
    )
    check(
        "CommandEvent key order",
        list(_event().to_dict().keys())
        == ["event_id", "command_id", "event_type", "created_at", "status", "message", "metadata"],
    )


def test_immutability() -> None:
    print("\n[3] frozen immutability")
    draft = _draft()
    frozen = 0
    for field_name, value in (("summary", "changed"), ("args", ()), ("metadata", ())):
        try:
            setattr(draft, field_name, value)
        except dataclasses.FrozenInstanceError:
            frozen += 1
    check("CommandDraft fields frozen", frozen == 3)
    event = _event()
    try:
        event.status = "success"
        check("CommandEvent frozen", False)
    except dataclasses.FrozenInstanceError:
        check("CommandEvent frozen", True)


def test_tuple_serialization_and_no_mutables() -> None:
    print("\n[4] tuple metadata serialization + no mutable fields")
    draft = CommandDraft.of(
        command_id="cmd-002",
        command_type="RUN_STAGE4_FINAL_GATE",
        requested_by="operator-a",
        created_at="2026-07-05T10:00:00Z",
        summary="Run the Stage 4 final gate",
        args={"checked_at": "2026-07-05T10:00:00Z"},
        metadata=[("a", "1"), ("b", "2")],
    )
    check("dict args normalized to tuple pairs", draft.args == (("checked_at", "2026-07-05T10:00:00Z"),))
    check("list metadata normalized to tuple pairs", draft.metadata == (("a", "1"), ("b", "2")))
    payload = draft.to_dict()
    check("args serialized as lists", payload["args"] == [["checked_at", "2026-07-05T10:00:00Z"]])
    check("metadata serialized as lists", payload["metadata"] == [["a", "1"], ["b", "2"]])
    for model in (draft, _event()):
        mutable = [
            field.name
            for field in dataclasses.fields(model)
            if isinstance(getattr(model, field.name), (dict, list, set))
        ]
        check(f"{type(model).__name__} exposes no mutable fields", mutable == [])


def test_deterministic_factories() -> None:
    print("\n[5] deterministic factories")
    check("CommandDraft.of deterministic", _draft() == _draft())
    check("CommandEvent.of deterministic", _event() == _event())
    check("to_dict deterministic", _draft().to_dict() == _draft().to_dict())


def test_model_enforcement() -> None:
    print("\n[6] engine-side enum enforcement")
    try:
        CommandEvent.of("e", "c", "NOT_AN_EVENT", "t", "pending", "m")
        check("invalid event_type rejected", False)
    except ValueError:
        check("invalid event_type rejected", True)
    try:
        CommandEvent.of("e", "c", "COMMAND_DRAFTED", "t", "sideways", "m")
        check("invalid status rejected", False)
    except ValueError:
        check("invalid status rejected", True)
    # Drafts intentionally allow unknown types (validation layer rejects them).
    unknown = CommandDraft.of("c", "NOT_A_TYPE", "op", "t", "s")
    check("draft allows unknown type for validation layer", unknown.command_type == "NOT_A_TYPE")
    try:
        CommandDraft.of("c", "RUN_SMOKE_CHECK", "op", "t", "s", args=(("only-key",),))
        check("malformed arg pair rejected", False)
    except ValueError:
        check("malformed arg pair rejected", True)


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
