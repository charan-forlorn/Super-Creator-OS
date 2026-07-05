"""test_git_approval_builder.py - SCOS Stage 5.8 git approval builder suite.

Plain executable script (no pytest). Covers commit proposal/approval and
push proposal/approval rules end to end, using build_git_evidence_snapshot
to construct realistic snapshots.

Run: python scos/control_center/tests/test_git_approval_builder.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
sys.path.insert(0, str(_PACKAGE))

from git_approval_builder import (  # noqa: E402
    build_commit_proposal,
    build_git_approval_event,
    build_push_proposal,
    record_commit_approval_decision,
    record_push_approval_decision,
)
from git_approval_models import (  # noqa: E402
    GitApprovalError,
    GitChangedFile,
    GitEvidenceSnapshot,
    GitTestEvidence,
)
from git_evidence_snapshot import (  # noqa: E402
    build_git_evidence_snapshot,
    build_push_readiness_snapshot,
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


def _make_snapshot(**overrides):
    kwargs = dict(
        task_id="task-58",
        session_id="sess-58",
        source_intake_id=None,
        branch="main",
        head_commit="09fd1cd8",
        origin_main_commit="09fd1cd8",
        is_clean_before_stage=True,
        has_remote_only_commits=False,
        changed_files=(
            {"path": "scos/control_center/git_approval_models.py", "change_type": "added", "summary": "new"},
            {"path": "scos/control_center/git_approval_builder.py", "change_type": "added", "summary": "new"},
        ),
        test_evidence=(
            {
                "evidence_id": "ev-1",
                "command_label": "python test.py",
                "status": "passed",
                "summary": "ok",
                "passed_count": 40,
            },
        ),
        created_at="2026-07-06T10:00:00Z",
    )
    kwargs.update(overrides)
    return build_git_evidence_snapshot(**kwargs)


def _make_proposal(snapshot=None, **overrides):
    snapshot = snapshot or _make_snapshot()
    kwargs = dict(
        snapshot=snapshot,
        commit_message="feat(control-center): add Stage 5.8 git approval gate",
        proposed_at="2026-07-06T10:05:00Z",
    )
    kwargs.update(overrides)
    return build_commit_proposal(**kwargs)


def test_1_builds_deterministic_proposal_id() -> None:
    snapshot = _make_snapshot()
    first = _make_proposal(snapshot=snapshot)
    second = _make_proposal(snapshot=snapshot)
    check("proposal builds ok", first.ok is True)
    check("proposal id deterministic", first.proposal_id == second.proposal_id)
    check("proposal id has prefix", first.proposal_id.startswith("cp-"))


def test_2_derives_sorted_file_list() -> None:
    proposal = _make_proposal()
    check(
        "files_to_commit is sorted",
        list(proposal.files_to_commit) == sorted(proposal.files_to_commit),
    )
    check("files_to_commit has both files", len(proposal.files_to_commit) == 2)


def test_3_rejects_invalid_commit_message() -> None:
    result = _make_proposal(commit_message="update stuff")
    check("rejects non-conventional message", isinstance(result, GitApprovalError))
    check("error kind is invalid_commit_message", result.error_kind == "invalid_commit_message")


def test_4_rejects_newline_in_commit_message() -> None:
    result = _make_proposal(commit_message="feat(x): a\nb")
    check("rejects multiline message", isinstance(result, GitApprovalError))
    check("error kind is invalid_commit_message", result.error_kind == "invalid_commit_message")


def test_5_rejects_shell_operators() -> None:
    result = _make_proposal(commit_message="feat(x): do a && rm -rf /")
    check("rejects shell operator", isinstance(result, GitApprovalError))
    check("error kind is forbidden_command", result.error_kind == "forbidden_command")


def test_6_rejects_missing_passed_tests() -> None:
    # build_git_evidence_snapshot already requires >=1 passed evidence item,
    # so exercise build_commit_proposal's own independent guard directly
    # against a hand-built GitEvidenceSnapshot with only failed evidence.
    no_passed_snapshot = GitEvidenceSnapshot.of(
        "ges-no-pass",
        "task-58",
        "sess-58",
        "main",
        "09fd1cd8",
        "09fd1cd8",
        "2026-07-06T10:00:00Z",
        changed_files=(
            GitChangedFile.of(
                "scos/control_center/git_approval_models.py", "added", "new"
            ),
        ),
        test_evidence=(
            GitTestEvidence.of(
                "ev-1", "python test.py", "failed", "broken", failed_count=1
            ),
        ),
    )
    result = build_commit_proposal(
        snapshot=no_passed_snapshot,
        commit_message="feat(x): y",
        proposed_at="2026-07-06T10:05:00Z",
    )
    check("rejects proposal with no passed evidence", isinstance(result, GitApprovalError))
    check(
        "error kind is missing_test_evidence",
        result.error_kind == "missing_test_evidence",
    )

    snapshot_with_failure = _make_snapshot(
        test_evidence=(
            {
                "evidence_id": "ev-1",
                "command_label": "python test.py",
                "status": "failed",
                "summary": "broken",
                "failed_count": 1,
            },
            {
                "evidence_id": "ev-2",
                "command_label": "python test2.py",
                "status": "passed",
                "summary": "ok",
                "passed_count": 1,
            },
        )
    )
    proposal = _make_proposal(snapshot=snapshot_with_failure)
    check("high risk_level when a test failed", proposal.risk_level == "high")


def test_7_rejects_blocked_risk_flags() -> None:
    snapshot = _make_snapshot(is_clean_before_stage=False)
    check("snapshot carries unsafe_git_state risk flag", "unsafe_git_state" in snapshot.risk_flags)
    result = build_commit_proposal(
        snapshot=snapshot,
        commit_message="feat(x): y",
        proposed_at="2026-07-06T10:05:00Z",
    )
    check("blocked risk flag rejected", isinstance(result, GitApprovalError))
    check("error kind is blocked_risk", result.error_kind == "blocked_risk")


def test_8_computes_risk_level() -> None:
    clean_snapshot = _make_snapshot()
    low_risk = _make_proposal(snapshot=clean_snapshot)
    check("low risk when all tests pass", low_risk.risk_level == "low")


def test_9_commit_approval_manual_command() -> None:
    proposal = _make_proposal()
    approved = record_commit_approval_decision(
        proposal=proposal,
        decision="approved",
        decided_by="operator",
        decided_at="2026-07-06T10:06:00Z",
        reason="looks good",
    )
    check("approved decision has manual_command", approved.manual_command is not None)
    check("manual_command mentions git add", "git add" in approved.manual_command)
    check("manual_command mentions git commit", "git commit -m" in approved.manual_command)

    rejected = record_commit_approval_decision(
        proposal=proposal,
        decision="rejected",
        decided_by="operator",
        decided_at="2026-07-06T10:06:00Z",
        reason="needs more tests",
    )
    check("rejected decision has no manual_command", rejected.manual_command is None)

    needs_changes = record_commit_approval_decision(
        proposal=proposal,
        decision="needs_changes",
        decided_by="operator",
        decided_at="2026-07-06T10:06:00Z",
        reason="fix lint",
    )
    check("needs_changes decision has no manual_command", needs_changes.manual_command is None)

    blocked = record_commit_approval_decision(
        proposal=proposal,
        decision="blocked",
        decided_by="operator",
        decided_at="2026-07-06T10:06:00Z",
        reason="ci down",
    )
    check("blocked decision has no manual_command", blocked.manual_command is None)
    check(
        "decision id deterministic",
        approved.decision_id
        == record_commit_approval_decision(
            proposal=proposal,
            decision="approved",
            decided_by="operator",
            decided_at="2026-07-06T10:06:00Z",
            reason="looks good",
        ).decision_id,
    )


def _make_commit_decision_approved(proposal):
    return record_commit_approval_decision(
        proposal=proposal,
        decision="approved",
        decided_by="operator",
        decided_at="2026-07-06T10:06:00Z",
        reason="looks good",
    )


def _make_push_snapshot(**overrides):
    kwargs = dict(
        branch="main",
        head_commit="abc123",
        origin_main_commit="09fd1cd8",
        ahead_by=1,
        behind_by=0,
        has_remote_only_commits=False,
        working_tree_clean=True,
        latest_commit_message="feat(control-center): add Stage 5.8 git approval gate",
        created_at="2026-07-06T10:07:00Z",
    )
    kwargs.update(overrides)
    return build_push_readiness_snapshot(**kwargs)


def test_10_push_proposal_requires_approved_commit() -> None:
    proposal = _make_proposal()
    rejected_commit = record_commit_approval_decision(
        proposal=proposal,
        decision="rejected",
        decided_by="operator",
        decided_at="2026-07-06T10:06:00Z",
        reason="no",
    )
    push_snapshot = _make_push_snapshot()
    result = build_push_proposal(
        commit_decision=rejected_commit,
        push_snapshot=push_snapshot,
        proposed_at="2026-07-06T10:08:00Z",
    )
    check("push proposal requires approved commit", isinstance(result, GitApprovalError))
    check("error kind is missing_approval", result.error_kind == "missing_approval")


def test_11_push_proposal_requires_ahead_and_clean_behind() -> None:
    proposal = _make_proposal()
    approved_commit = _make_commit_decision_approved(proposal)

    zero_ahead = build_push_proposal(
        commit_decision=approved_commit,
        push_snapshot=_make_push_snapshot(ahead_by=0),
        proposed_at="2026-07-06T10:08:00Z",
    )
    check("rejects ahead_by == 0", isinstance(zero_ahead, GitApprovalError))
    check("error kind is unsafe_push", zero_ahead.error_kind == "unsafe_push")

    behind = build_push_proposal(
        commit_decision=approved_commit,
        push_snapshot=_make_push_snapshot(behind_by=1),
        proposed_at="2026-07-06T10:08:00Z",
    )
    check("rejects behind_by != 0", isinstance(behind, GitApprovalError))

    dirty = build_push_proposal(
        commit_decision=approved_commit,
        push_snapshot=_make_push_snapshot(working_tree_clean=False),
        proposed_at="2026-07-06T10:08:00Z",
    )
    check("rejects dirty working tree", isinstance(dirty, GitApprovalError))
    check("error kind is dirty_worktree", dirty.error_kind == "dirty_worktree")

    remote_only = build_push_proposal(
        commit_decision=approved_commit,
        push_snapshot=_make_push_snapshot(has_remote_only_commits=True),
        proposed_at="2026-07-06T10:08:00Z",
    )
    check("rejects remote-only commits", isinstance(remote_only, GitApprovalError))


def test_12_push_proposal_exact_command() -> None:
    proposal = _make_proposal()
    approved_commit = _make_commit_decision_approved(proposal)
    push_proposal = build_push_proposal(
        commit_decision=approved_commit,
        push_snapshot=_make_push_snapshot(),
        proposed_at="2026-07-06T10:08:00Z",
    )
    check("push proposal built ok", push_proposal.ok is True)
    check(
        "proposed_command exact",
        push_proposal.proposed_command == "git push origin main",
    )


def test_13_push_approval_manual_command() -> None:
    proposal = _make_proposal()
    approved_commit = _make_commit_decision_approved(proposal)
    push_proposal = build_push_proposal(
        commit_decision=approved_commit,
        push_snapshot=_make_push_snapshot(),
        proposed_at="2026-07-06T10:08:00Z",
    )
    approved_push = record_push_approval_decision(
        proposal=push_proposal,
        decision="approved",
        decided_by="operator",
        decided_at="2026-07-06T10:09:00Z",
        reason="ready",
    )
    check(
        "approved push decision has exact manual_command",
        approved_push.manual_command == "git push origin main",
    )
    rejected_push = record_push_approval_decision(
        proposal=push_proposal,
        decision="rejected",
        decided_by="operator",
        decided_at="2026-07-06T10:09:00Z",
        reason="not yet",
    )
    check("rejected push decision has no manual_command", rejected_push.manual_command is None)
    needs_changes_push = record_push_approval_decision(
        proposal=push_proposal,
        decision="needs_changes",
        decided_by="operator",
        decided_at="2026-07-06T10:09:00Z",
        reason="wait",
    )
    check(
        "needs_changes push decision has no manual_command",
        needs_changes_push.manual_command is None,
    )
    blocked_push = record_push_approval_decision(
        proposal=push_proposal,
        decision="blocked",
        decided_by="operator",
        decided_at="2026-07-06T10:09:00Z",
        reason="ci down",
    )
    check("blocked push decision has no manual_command", blocked_push.manual_command is None)


def test_14_git_approval_event_builder() -> None:
    event = build_git_approval_event(
        event_type="commit_proposal_created",
        task_id="task-58",
        session_id="sess-58",
        related_id="cp-1",
        summary="commit proposal created",
        created_at="2026-07-06T10:05:01Z",
    )
    check("event builds ok", event.ok is True)
    check("event id has prefix", event.event_id.startswith("gae-"))
    invalid = build_git_approval_event(
        event_type="not_a_real_event",
        task_id="task-58",
        session_id="sess-58",
        related_id="cp-1",
        summary="x",
        created_at="2026-07-06T10:05:01Z",
    )
    check("rejects invalid event_type at builder layer", isinstance(invalid, GitApprovalError))


def main() -> int:
    tests = [
        test_1_builds_deterministic_proposal_id,
        test_2_derives_sorted_file_list,
        test_3_rejects_invalid_commit_message,
        test_4_rejects_newline_in_commit_message,
        test_5_rejects_shell_operators,
        test_6_rejects_missing_passed_tests,
        test_7_rejects_blocked_risk_flags,
        test_8_computes_risk_level,
        test_9_commit_approval_manual_command,
        test_10_push_proposal_requires_approved_commit,
        test_11_push_proposal_requires_ahead_and_clean_behind,
        test_12_push_proposal_exact_command,
        test_13_push_approval_manual_command,
        test_14_git_approval_event_builder,
    ]
    for test in tests:
        print(f"{test.__name__}:")
        test()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
