"""test_result_intake_builder.py - SCOS Stage 5.7 result intake builder suite.

Plain executable script (no pytest). Covers verdict classification
precedence, deterministic id derivation, URL/secret rejection, ChatGPT status
packet generation, project state mapping, and next action decisions.

Run: python scos/control_center/tests/test_result_intake_builder.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
sys.path.insert(0, str(_PACKAGE))

from result_intake_builder import (  # noqa: E402
    build_chatgpt_status_update_packet,
    build_next_action_decision,
    build_project_state_update,
    build_result_intake_record,
    classify_verdict,
)
from result_intake_models import (  # noqa: E402
    AIResultIntakeError,
    AIResultIntakeRecord,
    ChatGPTStatusUpdatePacket,
    NextActionDecision,
    ProjectStateUpdate,
    ResultIntakeArtifact,
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


def _build_record(**overrides) -> AIResultIntakeRecord:
    kwargs = dict(
        session_id="sess-1",
        task_id="task-1",
        source_agent="claude_code",
        source_runtime_id="runtime-1",
        raw_result_text="All tests passed. Verdict: PASS",
        created_at="2026-07-06T00:00:00Z",
        title="Implementation result",
    )
    kwargs.update(overrides)
    result = build_result_intake_record(**kwargs)
    assert isinstance(result, AIResultIntakeRecord), result
    return result


def test_1_verdict_classification_precedence() -> None:
    print("\n[1] verdict classification precedence")
    check("BLOCKED beats FAIL", classify_verdict("blocked: waiting on operator, also failed") == "BLOCKED")
    check("FAIL beats NEEDS_FIX", classify_verdict("failed: needs fix in module x") == "FAIL")
    check(
        "NEEDS_FIX beats PARTIAL",
        classify_verdict("needs fix; partially complete") == "NEEDS_FIX",
    )
    check("PARTIAL beats PASS", classify_verdict("partially passed, some tests fail") == "PARTIAL")
    check("PASS detected alone", classify_verdict("all tests pass, verdict: pass") == "PASS")


def test_2_verdict_classification_fallbacks() -> None:
    print("\n[2] verdict classification fallbacks")
    check(
        "no marker becomes NEEDS_REVIEW",
        classify_verdict("Implemented the feature and updated the docs today.") == "NEEDS_REVIEW",
    )
    check("near-empty text becomes UNKNOWN", classify_verdict("ok") == "UNKNOWN")
    check("whitespace-only becomes UNKNOWN", classify_verdict("   ") == "UNKNOWN")


def test_3_build_result_intake_record_deterministic_id() -> None:
    print("\n[3] deterministic intake_id")
    first = _build_record()
    second = _build_record()
    check("same inputs produce same intake_id", first.intake_id == second.intake_id)
    third = _build_record(raw_result_text="Different text. Verdict: PASS")
    check("different raw text produces different intake_id", first.intake_id != third.intake_id)
    check("intake_id has expected prefix", first.intake_id.startswith("ri-"))


def _build_record_raw(**overrides):
    kwargs = dict(
        session_id="sess-1",
        task_id="task-1",
        source_agent="claude_code",
        source_runtime_id="runtime-1",
        raw_result_text="All tests passed. Verdict: PASS",
        created_at="2026-07-06T00:00:00Z",
        title="Implementation result",
    )
    kwargs.update(overrides)
    return build_result_intake_record(**kwargs)


def test_4_build_result_intake_record_rejects_bad_input() -> None:
    print("\n[4] build_result_intake_record rejects bad input")
    check(
        "invalid source_agent rejected",
        isinstance(_build_record_raw(source_agent="gemini"), AIResultIntakeError),
    )
    check(
        "empty raw_result_text rejected",
        isinstance(_build_record_raw(raw_result_text="  "), AIResultIntakeError),
    )
    # ResultIntakeArtifact.of itself rejects URL paths at construction time,
    # so exercise that rejection directly rather than passing a bad instance
    # to the builder.
    try:
        ResultIntakeArtifact.of(
            "art-1", "unknown", "bad artifact", "summary", path="https://example.com/evil"
        )
        url_rejected = False
    except ValueError:
        url_rejected = True
    check("url-like artifact path rejected at construction", url_rejected)

    secret_result = _build_record_raw(metadata={"api_key": "sk-123"})
    check("secret-like metadata key rejected", isinstance(secret_result, AIResultIntakeError))


def test_5_extraction_of_blockers_warnings_tests_files() -> None:
    print("\n[5] extraction of blockers/warnings/tests/changed files")
    record = _build_record(
        raw_result_text=(
            "Implementation complete. Verdict: PASS\n"
            "Blocker: none pending\n"
            "Warning: flaky test on CI\n"
            "Tests: 42 passed, 0 failed\n"
            "Changed Files: 3 files updated\n"
        )
    )
    check("blockers extracted", record.blockers == ("none pending",))
    check("warnings extracted", record.warnings == ("flaky test on CI",))
    check("tests_summary extracted", record.tests_summary == "42 passed, 0 failed")
    check("changed_files_summary extracted", record.changed_files_summary == "3 files updated")


def test_6_operator_review_required_rules() -> None:
    print("\n[6] operator_review_required rules")
    passing = _build_record(raw_result_text="All tests pass. Verdict: PASS")
    check("clean PASS does not force review", passing.operator_review_required is False)
    failing = _build_record(raw_result_text="Build failed. Verdict: FAIL")
    check("FAIL forces review", failing.operator_review_required is True)
    ambiguous = _build_record(raw_result_text="Implemented the change and ran it locally today.")
    check("NEEDS_REVIEW forces review", ambiguous.operator_review_required is True)


def test_7_chatgpt_status_update_packet_generation() -> None:
    print("\n[7] ChatGPT status update packet generation")
    record = _build_record()
    packet = build_chatgpt_status_update_packet(
        intake_record=record,
        target_runtime_id="chatgpt-web",
        created_at="2026-07-06T00:05:00Z",
        requested_chatgpt_action="summarize_status",
    )
    check("packet built", isinstance(packet, ChatGPTStatusUpdatePacket))
    check("target_agent is chatgpt", packet.target_agent == "chatgpt")
    check("session/task carried over", packet.session_id == record.session_id and packet.task_id == record.task_id)
    check("source_agent recorded in metadata", packet.metadata.get("source_agent") == record.source_agent)
    check("verdict included in body", record.verdict in packet.status_update_body)
    other = build_chatgpt_status_update_packet(
        intake_record=record,
        target_runtime_id="chatgpt-web",
        created_at="2026-07-06T00:05:00Z",
        requested_chatgpt_action="summarize_status",
    )
    check("deterministic update_packet_id", packet.update_packet_id == other.update_packet_id)


def test_8_project_state_mapping() -> None:
    print("\n[8] project state mapping")
    blocked = _build_record(raw_result_text="Blocked: waiting on operator decision.")
    blocked_state = build_project_state_update(
        intake_record=blocked,
        previous_stage="5.6",
        current_stage="5.7",
        updated_at="2026-07-06T00:10:00Z",
    )
    check("BLOCKED maps to blocked/blocked", isinstance(blocked_state, ProjectStateUpdate)
          and blocked_state.task_status == "blocked" and blocked_state.stage_status == "blocked")

    passing = _build_record(raw_result_text="All tests pass. Verdict: PASS")
    approved_state = build_project_state_update(
        intake_record=passing, previous_stage="5.6", current_stage="5.7", updated_at="t"
    )
    check("PASS defaults to approved", approved_state.task_status == "approved")

    ready_state = build_project_state_update(
        intake_record=passing,
        previous_stage="5.6",
        current_stage="5.7",
        updated_at="t",
        metadata={"ready_for_commit": True},
    )
    check("ready_for_commit flag maps to ready_for_commit", ready_state.task_status == "ready_for_commit")

    complete_state = build_project_state_update(
        intake_record=passing,
        previous_stage="5.6",
        current_stage="5.7",
        updated_at="t",
        metadata={"stage_complete": True},
    )
    check("stage_complete flag maps stage_status to complete", complete_state.stage_status == "complete")


def test_9_next_action_decisions() -> None:
    print("\n[9] next action decisions")
    blocked = _build_record(raw_result_text="Blocked: waiting on operator decision.")
    blocked_decision = build_next_action_decision(intake_record=blocked, created_at="t")
    check(
        "BLOCKED -> hold_blocked with no target",
        isinstance(blocked_decision, NextActionDecision)
        and blocked_decision.recommended_action == "hold_blocked"
        and blocked_decision.target_agent is None,
    )

    codex_fail = _build_record(source_agent="codex", raw_result_text="Review failed: found a bug.")
    codex_decision = build_next_action_decision(intake_record=codex_fail, created_at="t")
    check(
        "codex FAIL -> send_to_claude_fix",
        codex_decision.recommended_action == "send_to_claude_fix"
        and codex_decision.target_agent == "claude_code",
    )

    claude_fail = _build_record(source_agent="claude_code", raw_result_text="Build failed: syntax error.")
    claude_decision = build_next_action_decision(intake_record=claude_fail, created_at="t")
    check(
        "claude_code FAIL -> conservative request_operator_review",
        claude_decision.recommended_action == "request_operator_review",
    )

    claude_pass = _build_record(source_agent="claude_code", raw_result_text="All tests pass. Verdict: PASS")
    claude_pass_decision = build_next_action_decision(intake_record=claude_pass, created_at="t")
    check(
        "claude_code PASS -> send_to_codex_review",
        claude_pass_decision.recommended_action == "send_to_codex_review"
        and claude_pass_decision.target_agent == "codex",
    )

    codex_pass = _build_record(source_agent="codex", raw_result_text="All tests pass. Verdict: PASS")
    codex_pass_decision = build_next_action_decision(intake_record=codex_pass, created_at="t")
    check(
        "codex PASS -> send_to_hermes_audit",
        codex_pass_decision.recommended_action == "send_to_hermes_audit"
        and codex_pass_decision.target_agent == "hermes",
    )

    hermes_pass = _build_record(source_agent="hermes", raw_result_text="All tests pass. Verdict: PASS")
    hermes_pass_decision = build_next_action_decision(intake_record=hermes_pass, created_at="t")
    check(
        "hermes PASS -> send_to_chatgpt_status_update",
        hermes_pass_decision.recommended_action == "send_to_chatgpt_status_update"
        and hermes_pass_decision.target_agent == "chatgpt",
    )

    unclear = _build_record(raw_result_text="Implemented the change and ran it locally today.")
    unclear_decision = build_next_action_decision(intake_record=unclear, created_at="t")
    check(
        "NEEDS_REVIEW -> request_operator_review",
        unclear_decision.recommended_action == "request_operator_review",
    )

    ready_commit_decision = build_next_action_decision(
        intake_record=claude_pass, created_at="t", metadata={"ready_for_commit": True}
    )
    check(
        "ready_for_commit flag -> prepare_commit_gate",
        ready_commit_decision.recommended_action == "prepare_commit_gate",
    )

    stage_complete_decision = build_next_action_decision(
        intake_record=claude_pass, created_at="t", metadata={"stage_complete": True}
    )
    check(
        "stage_complete flag -> mark_stage_complete",
        stage_complete_decision.recommended_action == "mark_stage_complete",
    )

    for decision in (
        blocked_decision,
        codex_decision,
        claude_decision,
        claude_pass_decision,
        codex_pass_decision,
        hermes_pass_decision,
        unclear_decision,
    ):
        check(
            f"{decision.recommended_action} requires operator approval",
            decision.requires_operator_approval is True,
        )


def main() -> int:
    test_1_verdict_classification_precedence()
    test_2_verdict_classification_fallbacks()
    test_3_build_result_intake_record_deterministic_id()
    test_4_build_result_intake_record_rejects_bad_input()
    test_5_extraction_of_blockers_warnings_tests_files()
    test_6_operator_review_required_rules()
    test_7_chatgpt_status_update_packet_generation()
    test_8_project_state_mapping()
    test_9_next_action_decisions()
    print(f"\n RESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
