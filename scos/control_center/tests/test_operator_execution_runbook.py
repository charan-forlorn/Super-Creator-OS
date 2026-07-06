"""test_operator_execution_runbook.py - SCOS Stage 5.9 builder suite.

Plain executable script (no pytest). Covers commit/push runbook step counts,
deterministic IDs, str-vs-sequence commands, verdict/outcome classification,
and structured-error returns.

Run: python scos/control_center/tests/test_operator_execution_runbook.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
sys.path.insert(0, str(_PACKAGE))

from operator_execution_models import (  # noqa: E402
    CommandExecutionCapture,
    ManualCommandRunbook,
    OperatorExecutionError,
    OperatorExecutionOutcome,
)
from operator_execution_runbook import (  # noqa: E402
    capture_manual_command_result,
    classify_operator_execution_outcome,
    create_git_commit_runbook,
    create_git_push_runbook,
    create_manual_command_runbook,
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


def _commit_runbook():
    return create_git_commit_runbook(
        session_id="sess-59",
        task_id="task-59",
        commit_message="feat(control-center): add Stage 5.9 local operator execution console",
        staged_paths=["scos/control_center/operator_execution_models.py"],
        created_at="2026-07-06T00:00:00Z",
        source_approval_id="cad-abc",
        source_commit_proposal_id="cp-abc",
    )


def _push_runbook():
    return create_git_push_runbook(
        session_id="sess-59",
        task_id="task-59",
        remote_name="origin",
        branch_name="main",
        created_at="2026-07-06T00:00:00Z",
        source_approval_id="pad-abc",
        source_push_proposal_id="pp-abc",
    )


def test_1_commit_runbook_shape():
    rb = _commit_runbook()
    check("returns runbook", isinstance(rb, ManualCommandRunbook))
    check("6 command steps", len(rb.command_steps) == 6)
    check("7 safety checks", len(rb.safety_checks) == 7)
    check("runbook_type commit", rb.runbook_type == "commit_runbook")
    check("step 5 is git_commit", rb.command_steps[4].command_type == "git_commit")
    check("id prefix rb-", rb.runbook_id.startswith("rb-"))
    check("no push step present", all("git push" not in s.command for s in rb.command_steps))


def test_2_push_runbook_shape():
    rb = _push_runbook()
    check("returns runbook", isinstance(rb, ManualCommandRunbook))
    check("11 command steps", len(rb.command_steps) == 11)
    check("7 safety checks", len(rb.safety_checks) == 7)
    check("runbook_type push", rb.runbook_type == "push_runbook")
    check("a push step is critical", any(
        s.command_type == "git_push" and s.risk_level == "critical" for s in rb.command_steps))


def test_3_deterministic_ids():
    a = _commit_runbook()
    b = _commit_runbook()
    check("runbook_id deterministic", a.runbook_id == b.runbook_id)
    check("step ids deterministic", [s.step_id for s in a.command_steps] ==
          [s.step_id for s in b.command_steps])


def test_4_generic_commands_str_and_sequence():
    r1 = create_manual_command_runbook(
        session_id="s", task_id="t", title="T", objective="o",
        commands="pnpm build", created_at="2026")
    r2 = create_manual_command_runbook(
        session_id="s", task_id="t", title="T", objective="o",
        commands=["pnpm lint", "pnpm build"], created_at="2026")
    check("str command -> 1 step", isinstance(r1, ManualCommandRunbook) and len(r1.command_steps) == 1)
    check("sequence commands -> 2 steps", isinstance(r2, ManualCommandRunbook) and len(r2.command_steps) == 2)
    check("bad runbook_type errors", isinstance(create_manual_command_runbook(
        session_id="s", task_id="t", title="T", objective="o", commands="x",
        created_at="2026", runbook_type="bogus"), OperatorExecutionError))
    check("bad shell errors", isinstance(create_manual_command_runbook(
        session_id="s", task_id="t", title="T", objective="o", commands="x",
        created_at="2026", shell="zsh"), OperatorExecutionError))
    check("empty commands errors", isinstance(create_manual_command_runbook(
        session_id="s", task_id="t", title="T", objective="o", commands=[],
        created_at="2026"), OperatorExecutionError))
    check("secret metadata errors", isinstance(create_manual_command_runbook(
        session_id="s", task_id="t", title="T", objective="o", commands="x",
        created_at="2026", metadata={"token": "y"}), OperatorExecutionError))


def _capture(rb, summary, raw, exit_text="exit 0"):
    return capture_manual_command_result(
        runbook=rb, operator_reported_command="git commit",
        pasted_output_summary=summary, raw_output_excerpt=raw,
        exit_status_text=exit_text, captured_at="2026-07-06T01:00:00Z")


def test_5_capture_classification():
    rb = _commit_runbook()
    good = _capture(rb, "committed", "[main a1b2c3] working tree clean")
    check("clear success -> PASS", isinstance(good, CommandExecutionCapture) and good.verdict == "PASS")

    warned = _capture(rb, "committed", "[main a1b2c3] warning: CRLF replaced")
    check("success + warning -> PASS_WITH_WARNINGS", warned.verdict == "PASS_WITH_WARNINGS")

    failed = _capture(rb, "boom", "error: pathspec did not match")
    check("clear failure -> FAIL", failed.verdict == "FAIL")

    blocked = _capture(rb, "denied", "remote: permission denied; push rejected")
    check("rejected -> BLOCKED", blocked.verdict == "BLOCKED")

    vague = _capture(rb, "done", "some unrelated text")
    check("vague -> NEEDS_REVIEW", vague.verdict == "NEEDS_REVIEW")

    empty = _capture(rb, "", "")
    check("empty -> UNKNOWN", empty.verdict == "UNKNOWN")

    check("url evidence path errors", isinstance(capture_manual_command_result(
        runbook=rb, operator_reported_command="c", pasted_output_summary="s",
        raw_output_excerpt="r", exit_status_text="e", captured_at="2026",
        evidence_paths=["https://x"]), OperatorExecutionError))
    check("non-runbook errors", isinstance(capture_manual_command_result(
        runbook="not-a-runbook", operator_reported_command="c",
        pasted_output_summary="s", raw_output_excerpt="r", exit_status_text="e",
        captured_at="2026"), OperatorExecutionError))


def test_6_outcome_classification():
    rb = _commit_runbook()
    good = _capture(rb, "committed", "[main a1b2c3] working tree clean")
    outcome = classify_operator_execution_outcome(
        runbook=rb, capture=good, created_at="2026-07-06T02:00:00Z")
    check("PASS -> command_succeeded", isinstance(outcome, OperatorExecutionOutcome)
          and outcome.outcome == "command_succeeded")
    check("PASS routes chatgpt", outcome.recommended_next_agent == "chatgpt")
    check("PASS clean -> no operator review", outcome.operator_review_required is False)
    check("outcome id prefix oeo-", outcome.outcome_id.startswith("oeo-"))

    failed = _capture(rb, "boom", "error: nope")
    fout = classify_operator_execution_outcome(
        runbook=rb, capture=failed, created_at="2026-07-06T02:00:00Z")
    check("FAIL -> command_failed", fout.outcome == "command_failed")
    check("FAIL routes codex", fout.recommended_next_agent == "codex")
    check("FAIL requires review", fout.operator_review_required is True)

    # capture from a different runbook -> contract error
    other = _push_runbook()
    check("mismatched runbook errors", isinstance(classify_operator_execution_outcome(
        runbook=other, capture=good, created_at="2026"), OperatorExecutionError))


def main() -> int:
    tests = [
        test_1_commit_runbook_shape,
        test_2_push_runbook_shape,
        test_3_deterministic_ids,
        test_4_generic_commands_str_and_sequence,
        test_5_capture_classification,
        test_6_outcome_classification,
    ]
    for test in tests:
        print(f"{test.__name__}:")
        test()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
