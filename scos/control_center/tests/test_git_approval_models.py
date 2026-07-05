"""test_git_approval_models.py - SCOS Stage 5.8 git approval model suite.

Plain executable script (no pytest). Covers deterministic serialization,
tuple/FrozenMap immutability, invalid enum rejection, and explicit key
ordering for all ten Stage 5.8 models.

Run: python scos/control_center/tests/test_git_approval_models.py
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
sys.path.insert(0, str(_PACKAGE))

from git_approval_models import (  # noqa: E402
    GIT_APPROVAL_SCHEMA_VERSION,
    CommitApprovalDecision,
    CommitProposal,
    GitApprovalError,
    GitApprovalEvent,
    GitChangedFile,
    GitEvidenceSnapshot,
    GitTestEvidence,
    PushApprovalDecision,
    PushProposal,
    PushReadinessSnapshot,
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


def _raises_frozen_error(fn) -> bool:
    try:
        fn()
        return False
    except dataclasses.FrozenInstanceError:
        return True


def _make_changed_file(**overrides) -> GitChangedFile:
    kwargs = dict(
        path="scos/control_center/git_approval_models.py",
        change_type="added",
        summary="new Stage 5.8 models file",
    )
    kwargs.update(overrides)
    return GitChangedFile.of(**kwargs)


def _make_test_evidence(**overrides) -> GitTestEvidence:
    kwargs = dict(
        evidence_id="ev-1",
        command_label="python test_git_approval_models.py",
        status="passed",
        summary="12 passed",
        passed_count=12,
    )
    kwargs.update(overrides)
    return GitTestEvidence.of(**kwargs)


def _make_snapshot(**overrides) -> GitEvidenceSnapshot:
    kwargs = dict(
        snapshot_id="ges-1",
        task_id="task-58",
        session_id="sess-58",
        branch="main",
        head_commit="09fd1cd8",
        origin_main_commit="09fd1cd8",
        created_at="2026-07-06T10:00:00Z",
        changed_files=(_make_changed_file(),),
        test_evidence=(_make_test_evidence(),),
    )
    kwargs.update(overrides)
    return GitEvidenceSnapshot.of(**kwargs)


def _make_commit_proposal(**overrides) -> CommitProposal:
    kwargs = dict(
        proposal_id="cp-1",
        snapshot_id="ges-1",
        task_id="task-58",
        session_id="sess-58",
        commit_message="feat(control-center): add Stage 5.8 git approval gate",
        commit_title="add Stage 5.8 git approval gate",
        files_to_commit=("a.py", "b.py"),
        evidence_summary="2 changed files",
        test_summary="1 passed",
        risk_level="low",
        proposed_at="2026-07-06T10:05:00Z",
    )
    kwargs.update(overrides)
    return CommitProposal.of(**kwargs)


def _make_commit_decision(**overrides) -> CommitApprovalDecision:
    kwargs = dict(
        decision_id="cad-1",
        proposal_id="cp-1",
        decision="approved",
        decided_by="operator",
        decided_at="2026-07-06T10:06:00Z",
        reason="looks good",
    )
    kwargs.update(overrides)
    return CommitApprovalDecision.of(**kwargs)


def _make_push_snapshot(**overrides) -> PushReadinessSnapshot:
    kwargs = dict(
        push_snapshot_id="prs-1",
        branch="main",
        head_commit="abc123",
        origin_main_commit="09fd1cd8",
        ahead_by=1,
        behind_by=0,
        working_tree_clean=True,
        latest_commit_message="feat(control-center): add Stage 5.8 git approval gate",
        created_at="2026-07-06T10:07:00Z",
    )
    kwargs.update(overrides)
    return PushReadinessSnapshot.of(**kwargs)


def _make_push_proposal(**overrides) -> PushProposal:
    kwargs = dict(
        push_proposal_id="pp-1",
        commit_decision_id="cad-1",
        push_snapshot_id="prs-1",
        proposed_at="2026-07-06T10:08:00Z",
    )
    kwargs.update(overrides)
    return PushProposal.of(**kwargs)


def _make_push_decision(**overrides) -> PushApprovalDecision:
    kwargs = dict(
        push_decision_id="pad-1",
        push_proposal_id="pp-1",
        decision="approved",
        decided_by="operator",
        decided_at="2026-07-06T10:09:00Z",
        reason="ready",
        manual_command="git push origin main",
    )
    kwargs.update(overrides)
    return PushApprovalDecision.of(**kwargs)


def _make_event(**overrides) -> GitApprovalEvent:
    kwargs = dict(
        event_id="gae-1",
        event_type="git_evidence_snapshot_created",
        task_id="task-58",
        session_id="sess-58",
        related_id="ges-1",
        summary="snapshot created",
        created_at="2026-07-06T10:00:01Z",
    )
    kwargs.update(overrides)
    return GitApprovalEvent.of(**kwargs)


def test_1_schema_version_constant() -> None:
    check("schema version is 1", GIT_APPROVAL_SCHEMA_VERSION == 1)


def test_2_changed_file() -> None:
    changed = _make_changed_file()
    check("changed file to_dict key order", list(changed.to_dict().keys()) == [
        "path", "change_type", "staged", "summary", "metadata",
    ])
    check(
        "rejects invalid change_type",
        _raises(lambda: _make_changed_file(change_type="bogus")),
    )
    check(
        "rejects absolute path",
        _raises(lambda: _make_changed_file(path="/etc/passwd")),
    )
    check(
        "rejects drive-letter path",
        _raises(lambda: _make_changed_file(path="C:\\repo\\file.py")),
    )
    check(
        "rejects URL-like path",
        _raises(lambda: _make_changed_file(path="https://example.com/file.py")),
    )
    check("immutable path", _raises_frozen_error(lambda: setattr(changed, "path", "x")))


def test_3_test_evidence() -> None:
    evidence = _make_test_evidence()
    check("evidence to_dict key order", list(evidence.to_dict().keys()) == [
        "evidence_id", "command_label", "status", "summary", "passed_count",
        "failed_count", "warning_count", "output_path", "metadata",
    ])
    check(
        "rejects invalid status",
        _raises(lambda: _make_test_evidence(status="bogus")),
    )
    check(
        "rejects negative passed_count",
        _raises(lambda: _make_test_evidence(passed_count=-1)),
    )
    check(
        "immutable status",
        _raises_frozen_error(lambda: setattr(evidence, "status", "failed")),
    )


def test_4_evidence_snapshot() -> None:
    snapshot = _make_snapshot()
    check("snapshot ok True", snapshot.ok is True)
    check("snapshot changed_files is tuple", isinstance(snapshot.changed_files, tuple))
    check("snapshot test_evidence is tuple", isinstance(snapshot.test_evidence, tuple))
    check(
        "snapshot to_dict key order",
        list(snapshot.to_dict().keys()) == [
            "ok", "schema_version", "snapshot_id", "task_id", "session_id",
            "source_intake_id", "branch", "head_commit", "origin_main_commit",
            "is_clean_before_stage", "has_remote_only_commits", "changed_files",
            "test_evidence", "risk_flags", "created_at", "metadata",
        ],
    )
    check(
        "rejects non-GitChangedFile entries",
        _raises(lambda: _make_snapshot(changed_files=({"path": "x"},))),
    )
    check(
        "immutable branch",
        _raises_frozen_error(lambda: setattr(snapshot, "branch", "dev")),
    )


def test_5_commit_proposal() -> None:
    proposal = _make_commit_proposal()
    check("proposal approval_required True", proposal.approval_required is True)
    check(
        "rejects invalid risk_level",
        _raises(lambda: _make_commit_proposal(risk_level="extreme")),
    )
    check(
        "rejects multiline commit_message",
        _raises(lambda: _make_commit_proposal(commit_message="feat(x): a\nb")),
    )
    check(
        "rejects approval_required False",
        _raises(lambda: _make_commit_proposal(approval_required=False)),
    )
    check(
        "files_to_commit is tuple",
        isinstance(proposal.files_to_commit, tuple),
    )


def test_6_commit_approval_decision() -> None:
    approved = _make_commit_decision(manual_command="git add a.py\ngit commit -m \"x\"")
    check("approved decision keeps manual_command", approved.manual_command is not None)
    check(
        "rejects invalid decision",
        _raises(lambda: _make_commit_decision(decision="maybe")),
    )
    check(
        "rejects manual_command on non-approved decision",
        _raises(
            lambda: _make_commit_decision(
                decision="rejected", manual_command="git commit -m x"
            )
        ),
    )


def test_7_push_readiness_snapshot() -> None:
    snapshot = _make_push_snapshot()
    check("push snapshot ahead_by int", isinstance(snapshot.ahead_by, int))
    check(
        "push snapshot to_dict key order",
        list(snapshot.to_dict().keys()) == [
            "ok", "schema_version", "push_snapshot_id", "branch", "head_commit",
            "origin_main_commit", "ahead_by", "behind_by",
            "has_remote_only_commits", "working_tree_clean",
            "latest_commit_message", "created_at", "metadata",
        ],
    )
    check(
        "rejects negative ahead_by",
        _raises(lambda: _make_push_snapshot(ahead_by=-1)),
    )


def test_8_push_proposal() -> None:
    proposal = _make_push_proposal()
    check("push proposal branch is main", proposal.branch == "main")
    check("push proposal remote is origin", proposal.remote == "origin")
    check(
        "push proposal proposed_command exact",
        proposal.proposed_command == "git push origin main",
    )
    check(
        "rejects non-main branch",
        _raises(lambda: _make_push_proposal(branch="develop")),
    )
    check(
        "rejects force push command",
        _raises(
            lambda: _make_push_proposal(proposed_command="git push origin main --force")
        ),
    )


def test_9_push_approval_decision() -> None:
    decision = _make_push_decision()
    check(
        "push decision manual_command exact",
        decision.manual_command == "git push origin main",
    )
    check(
        "rejects wrong manual_command text",
        _raises(
            lambda: _make_push_decision(manual_command="git push origin main --force")
        ),
    )
    check(
        "rejects manual_command on rejected decision",
        _raises(
            lambda: _make_push_decision(
                decision="rejected", manual_command="git push origin main"
            )
        ),
    )


def test_10_event_and_error() -> None:
    event = _make_event()
    check(
        "rejects invalid event_type",
        _raises(lambda: _make_event(event_type="bogus_event")),
    )
    error = GitApprovalError.of("invalid_branch", "branch must be main", "build_commit_proposal")
    check("error ok False", error.ok is False)
    check(
        "rejects invalid error_kind",
        _raises(
            lambda: GitApprovalError.of("not_a_kind", "detail", "stage")
        ),
    )
    check(
        "event to_dict key order",
        list(event.to_dict().keys()) == [
            "ok", "schema_version", "event_id", "event_type", "task_id",
            "session_id", "related_id", "summary", "created_at", "metadata",
        ],
    )


def main() -> int:
    tests = [
        test_1_schema_version_constant,
        test_2_changed_file,
        test_3_test_evidence,
        test_4_evidence_snapshot,
        test_5_commit_proposal,
        test_6_commit_approval_decision,
        test_7_push_readiness_snapshot,
        test_8_push_proposal,
        test_9_push_approval_decision,
        test_10_event_and_error,
    ]
    for test in tests:
        print(f"{test.__name__}:")
        test()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
