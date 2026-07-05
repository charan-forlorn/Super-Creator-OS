"""test_operator_approval.py - SCOS Stage 5.1 operator approval gate suite.

Plain executable script (no pytest). Covers approving valid drafts, refusing
invalid drafts, rejection records, approved-command creation guards
(approved=True required, command_id match required), and deterministic
approval ids.

Run: python scos/control_center/tests/test_operator_approval.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent

sys.path.insert(0, str(_PACKAGE))

from command_models import ApprovedCommand, CommandDraft  # noqa: E402
from operator_approval import (  # noqa: E402
    CONTROL_CENTER_OPERATOR_APPROVAL_SCHEMA_VERSION,
    approve_command,
    create_approved_command,
    reject_command,
)

_PASS = 0
_FAIL = 0

_APPROVED_AT = "2026-07-05T10:05:00Z"


def check(name: str, cond: bool) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}")


def _draft(**overrides) -> CommandDraft:
    payload = {
        "command_id": "cmd-001",
        "command_type": "RUN_SMOKE_CHECK",
        "requested_by": "operator-a",
        "created_at": "2026-07-05T10:00:00Z",
        "summary": "Run the Tier 1 smoke check",
        "args": (),
        "metadata": (("origin", "control-center"),),
    }
    payload.update(overrides)
    return CommandDraft.of(**payload)


def test_schema_version() -> None:
    print("\n[1] schema version")
    check("schema version is 1", CONTROL_CENTER_OPERATOR_APPROVAL_SCHEMA_VERSION == 1)


def test_approve_valid_draft() -> None:
    print("\n[2] approve valid draft")
    approval = approve_command(
        draft=_draft(),
        approved_by="operator-a",
        approved_at=_APPROVED_AT,
        reason="reviewed and safe",
    )
    check("approved flag set", approval.approved is True)
    check("command id copied", approval.command_id == "cmd-001")
    check("approved_at explicit", approval.approved_at == _APPROVED_AT)
    check("approval id prefixed", approval.approval_id.startswith("apr-"))


def test_reject_invalid_draft() -> None:
    print("\n[3] never approve an invalid draft")
    invalid = _draft(command_type="NOT_A_TYPE")
    try:
        approve_command(
            draft=invalid,
            approved_by="operator-a",
            approved_at=_APPROVED_AT,
            reason="should not work",
        )
        check("invalid draft approval raises", False)
    except ValueError as exc:
        check("invalid draft approval raises", str(exc).startswith("INVALID_DRAFT:"))
    rejection = reject_command(
        draft=invalid,
        rejected_by="operator-a",
        rejected_at=_APPROVED_AT,
        reason="unknown command type",
    )
    check("rejection recorded for invalid draft", rejection.approved is False)
    check("rejection reason kept", rejection.reason == "unknown command type")


def test_create_approved_command_guards() -> None:
    print("\n[4] create_approved_command guards")
    draft = _draft()
    approval = approve_command(
        draft=draft, approved_by="operator-a", approved_at=_APPROVED_AT, reason="ok"
    )
    approved = create_approved_command(draft=draft, approval=approval)
    check("approved command created", isinstance(approved, ApprovedCommand))
    check("draft args carried over", approved.args == draft.args)
    check("approver carried over", approved.approved_by == "operator-a")

    rejection = reject_command(
        draft=draft, rejected_by="operator-a", rejected_at=_APPROVED_AT, reason="no"
    )
    outcome = create_approved_command(draft=draft, approval=rejection)
    check(
        "approved=False fails",
        isinstance(outcome, tuple)
        and outcome[0] is None
        and outcome[1].startswith("APPROVAL_NOT_GRANTED:"),
    )

    other = _draft(command_id="cmd-999")
    outcome = create_approved_command(draft=other, approval=approval)
    check(
        "command_id mismatch fails",
        isinstance(outcome, tuple)
        and outcome[0] is None
        and outcome[1].startswith("COMMAND_ID_MISMATCH:"),
    )


def test_deterministic_approval_id() -> None:
    print("\n[5] deterministic approval_id")
    first = approve_command(
        draft=_draft(), approved_by="operator-a", approved_at=_APPROVED_AT, reason="ok"
    )
    second = approve_command(
        draft=_draft(), approved_by="operator-a", approved_at=_APPROVED_AT, reason="ok"
    )
    check("same inputs -> same id", first.approval_id == second.approval_id)
    other_operator = approve_command(
        draft=_draft(), approved_by="operator-b", approved_at=_APPROVED_AT, reason="ok"
    )
    check("different approver -> different id", first.approval_id != other_operator.approval_id)
    rejection = reject_command(
        draft=_draft(), rejected_by="operator-a", rejected_at=_APPROVED_AT, reason="no"
    )
    check("approve vs reject -> different id", first.approval_id != rejection.approval_id)


def main() -> int:
    test_schema_version()
    test_approve_valid_draft()
    test_reject_invalid_draft()
    test_create_approved_command_guards()
    test_deterministic_approval_id()
    print(f"\n RESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
