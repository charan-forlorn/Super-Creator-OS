"""test_operator_execution_models.py - SCOS Stage 5.9 model suite.

Plain executable script (no pytest). Covers immutable dataclass construction,
defaults, deterministic serialization, URL/secret rejection, and tuple-as-list
serialization for the operator execution / manual command runbook models.

Run: python scos/control_center/tests/test_operator_execution_models.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
sys.path.insert(0, str(_PACKAGE))

from operator_execution_models import (  # noqa: E402
    OPERATOR_EXECUTION_SCHEMA_VERSION,
    CommandExecutionCapture,
    ExecutionSafetyCheck,
    ManualCommandRunbook,
    OperatorExecutionError,
    OperatorExecutionOutcome,
    RunbookCommandStep,
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


def _raises(fn, exc_type=ValueError) -> bool:
    try:
        fn()
        return False
    except exc_type:
        return True


def _step() -> RunbookCommandStep:
    return RunbookCommandStep.of(
        "rbs-1", 1, "Inspect", "git status -sb", "git_status",
        expected_result_hint="clean tree",
    )


def _check() -> ExecutionSafetyCheck:
    return ExecutionSafetyCheck.of(
        "rbc-1", "Confirm branch is main", "Branch must be main",
        severity="critical", operator_instruction="run git status -sb",
    )


def test_1_step_defaults_and_validation():
    step = _step()
    check("requires_manual_copy defaults True", step.requires_manual_copy is True)
    check("requires_operator_confirmation defaults True", step.requires_operator_confirmation is True)
    check("step_order stored", step.step_order == 1)
    check("positive step_order enforced", _raises(lambda: RunbookCommandStep.of(
        "s", 0, "t", "c", "git_status")))
    check("empty command rejected", _raises(lambda: RunbookCommandStep.of(
        "s", 1, "t", "  ", "git_status")))
    check("bad command_type rejected", _raises(lambda: RunbookCommandStep.of(
        "s", 1, "t", "c", "nope")))
    check("bad shell rejected", _raises(lambda: RunbookCommandStep.of(
        "s", 1, "t", "c", "git_status", shell="zsh")))
    check("bad risk_level rejected", _raises(lambda: RunbookCommandStep.of(
        "s", 1, "t", "c", "git_status", risk_level="extreme")))
    check("url working_directory rejected", _raises(lambda: RunbookCommandStep.of(
        "s", 1, "t", "c", "git_status", working_directory="https://x/y")))


def test_2_step_to_dict_deterministic():
    step = _step()
    d = step.to_dict()
    keys = list(d.keys())
    expected = [
        "step_id", "step_order", "title", "command", "command_type", "shell",
        "working_directory", "requires_manual_copy", "requires_operator_confirmation",
        "expected_result_hint", "risk_level", "metadata",
    ]
    check("to_dict key order stable", keys == expected)
    check("metadata is plain dict", isinstance(d["metadata"], dict))


def test_3_safety_check():
    c = _check()
    check("status defaults pending", c.status == "pending")
    check("bad status rejected", _raises(lambda: ExecutionSafetyCheck.of(
        "id", "t", "d", status="nope")))
    check("bad severity rejected", _raises(lambda: ExecutionSafetyCheck.of(
        "id", "t", "d", severity="nope")))
    check("to_dict has required flag", c.to_dict()["required"] is True)


def test_4_runbook_serialization():
    runbook = ManualCommandRunbook.of(
        "rb-1", "sess", "task", "Title", "obj", "summary",
        "commit_runbook", "2026-07-06T00:00:00Z", "ready_for_operator",
        safety_checks=(_check(),),
        command_steps=(_step(),),
        expected_outputs=("a", "b"),
    )
    d = runbook.to_dict()
    check("schema_version present", d["schema_version"] == OPERATOR_EXECUTION_SCHEMA_VERSION)
    check("command_steps serialized as list of dicts", isinstance(d["command_steps"], list)
          and isinstance(d["command_steps"][0], dict))
    check("safety_checks serialized as list", isinstance(d["safety_checks"], list))
    check("expected_outputs tuple->list", d["expected_outputs"] == ["a", "b"])
    check("bad runbook_type rejected", _raises(lambda: ManualCommandRunbook.of(
        "rb", "s", "t", "T", "o", "s", "bogus", "2026", "drafted")))
    check("bad status rejected", _raises(lambda: ManualCommandRunbook.of(
        "rb", "s", "t", "T", "o", "s", "commit_runbook", "2026", "bogus")))
    check("wrong step type rejected", _raises(lambda: ManualCommandRunbook.of(
        "rb", "s", "t", "T", "o", "s", "commit_runbook", "2026", "drafted",
        command_steps=("not-a-step",))))


def test_5_capture_serialization_and_rejection():
    cap = CommandExecutionCapture.of(
        "cap-1", "rb-1", "sess", "task", "git status -sb",
        "clean", "nothing to commit, working tree clean", "exit 0", "PASS",
        "2026-07-06T00:00:00Z", warnings=("w",), blockers=(),
    )
    d = cap.to_dict()
    check("verdict stored", d["verdict"] == "PASS")
    check("warnings tuple->list", d["warnings"] == ["w"])
    check("bad verdict rejected", _raises(lambda: CommandExecutionCapture.of(
        "cap", "rb", "s", "t", "c", "o", "r", "e", "MAYBE", "2026")))
    check("url evidence_path rejected", _raises(lambda: CommandExecutionCapture.of(
        "cap", "rb", "s", "t", "c", "o", "r", "e", "PASS", "2026",
        evidence_paths=("http://evil/x",))))
    check("secret metadata rejected", _raises(lambda: CommandExecutionCapture.of(
        "cap", "rb", "s", "t", "c", "o", "r", "e", "PASS", "2026",
        metadata={"api_key": "x"})))
    check("access_key metadata rejected (5.9 superset)", _raises(lambda: CommandExecutionCapture.of(
        "cap", "rb", "s", "t", "c", "o", "r", "e", "PASS", "2026",
        metadata={"access_key": "x"})))
    check("credential metadata rejected (5.9 superset)", _raises(lambda: CommandExecutionCapture.of(
        "cap", "rb", "s", "t", "c", "o", "r", "e", "PASS", "2026",
        metadata={"credential": "x"})))


def test_6_outcome_and_error():
    outcome = OperatorExecutionOutcome.of(
        "oeo-1", "rb-1", "cap-1", "sess", "task",
        "command_succeeded", "ok", "record_result", "2026-07-06T00:00:00Z",
        recommended_next_agent="chatgpt", operator_review_required=False,
    )
    d = outcome.to_dict()
    check("outcome stored", d["outcome"] == "command_succeeded")
    check("next_agent stored", d["recommended_next_agent"] == "chatgpt")
    check("None next_agent allowed", OperatorExecutionOutcome.of(
        "o", "rb", "cap", "s", "t", "command_unknown", "s", "a", "2026",
        recommended_next_agent=None).recommended_next_agent is None)
    check("bad outcome rejected", _raises(lambda: OperatorExecutionOutcome.of(
        "o", "rb", "cap", "s", "t", "bogus", "s", "a", "2026")))
    check("bad next_agent rejected", _raises(lambda: OperatorExecutionOutcome.of(
        "o", "rb", "cap", "s", "t", "command_unknown", "s", "a", "2026",
        recommended_next_agent="skynet")))

    err = OperatorExecutionError.of("validation_error", "bad", "step")
    check("error ok defaults False", err.ok is False)
    check("error to_dict shape", err.to_dict()["error_kind"] == "validation_error")
    check("bad error_kind rejected", _raises(lambda: OperatorExecutionError.of(
        "not-a-kind", "d", "s")))


def main() -> int:
    tests = [
        test_1_step_defaults_and_validation,
        test_2_step_to_dict_deterministic,
        test_3_safety_check,
        test_4_runbook_serialization,
        test_5_capture_serialization_and_rejection,
        test_6_outcome_and_error,
    ]
    for test in tests:
        print(f"{test.__name__}:")
        test()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
