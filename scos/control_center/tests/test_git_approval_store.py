"""test_git_approval_store.py - SCOS Stage 5.8 git approval store suite.

Plain executable script (no pytest). Covers append-only JSONL persistence,
immutable tuple returns, lazy directory creation, and stable JSON output.

Run: python scos/control_center/tests/test_git_approval_store.py
"""

from __future__ import annotations

import shutil
import sys
import tempfile
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
from git_approval_store import GitApprovalStore  # noqa: E402
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


def _raises(fn, exc_type=ValueError) -> bool:
    try:
        fn()
        return False
    except exc_type:
        return True


def _build_full_lifecycle():
    snapshot = build_git_evidence_snapshot(
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
    proposal = build_commit_proposal(
        snapshot=snapshot,
        commit_message="feat(control-center): add Stage 5.8 git approval gate",
        proposed_at="2026-07-06T10:05:00Z",
    )
    commit_decision = record_commit_approval_decision(
        proposal=proposal,
        decision="approved",
        decided_by="operator",
        decided_at="2026-07-06T10:06:00Z",
        reason="looks good",
    )
    push_snapshot = build_push_readiness_snapshot(
        branch="main",
        head_commit="abc123",
        origin_main_commit="09fd1cd8",
        ahead_by=1,
        behind_by=0,
        has_remote_only_commits=False,
        working_tree_clean=True,
        latest_commit_message=proposal.commit_message,
        created_at="2026-07-06T10:07:00Z",
    )
    push_proposal = build_push_proposal(
        commit_decision=commit_decision,
        push_snapshot=push_snapshot,
        proposed_at="2026-07-06T10:08:00Z",
    )
    push_decision = record_push_approval_decision(
        proposal=push_proposal,
        decision="approved",
        decided_by="operator",
        decided_at="2026-07-06T10:09:00Z",
        reason="ready",
    )
    event = build_git_approval_event(
        event_type="git_evidence_snapshot_created",
        task_id="task-58",
        session_id="sess-58",
        related_id=snapshot.snapshot_id,
        summary="snapshot created",
        created_at="2026-07-06T10:00:01Z",
    )
    return snapshot, proposal, commit_decision, push_proposal, push_decision, event


def test_1_append_and_list_roundtrip() -> None:
    tmp = tempfile.mkdtemp(prefix="scos-git-approval-")
    try:
        store = GitApprovalStore(tmp)
        _snapshot, proposal, commit_decision, push_proposal, push_decision, event = (
            _build_full_lifecycle()
        )

        store.append_commit_proposal(proposal)
        store.append_commit_decision(commit_decision)
        store.append_push_proposal(push_proposal)
        store.append_push_decision(push_decision)
        store.append_event(event)

        check(
            "commit proposal round-trips",
            store.list_commit_proposals()[0].to_dict() == proposal.to_dict(),
        )
        check(
            "commit decision round-trips",
            store.list_commit_decisions()[0].to_dict() == commit_decision.to_dict(),
        )
        check(
            "push proposal round-trips",
            store.list_push_proposals()[0].to_dict() == push_proposal.to_dict(),
        )
        check(
            "push decision round-trips",
            store.list_push_decisions()[0].to_dict() == push_decision.to_dict(),
        )
        check("event round-trips", store.list_events()[0].to_dict() == event.to_dict())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_2_lists_are_immutable_tuples() -> None:
    tmp = tempfile.mkdtemp(prefix="scos-git-approval-")
    try:
        store = GitApprovalStore(tmp)
        _snapshot, proposal, commit_decision, push_proposal, push_decision, event = (
            _build_full_lifecycle()
        )
        store.append_commit_proposal(proposal)
        store.append_event(event)
        check("list_commit_proposals returns tuple", isinstance(store.list_commit_proposals(), tuple))
        check("list_events returns tuple", isinstance(store.list_events(), tuple))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_3_parent_dir_auto_created() -> None:
    tmp = tempfile.mkdtemp(prefix="scos-git-approval-")
    try:
        nested = Path(tmp) / "nested" / "deeper"
        store = GitApprovalStore(nested)
        check("nested dir does not exist before append", not nested.exists())
        _snapshot, proposal, *_ = _build_full_lifecycle()
        store.append_commit_proposal(proposal)
        check("nested dir created after append", nested.is_dir())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_4_list_only_creates_nothing() -> None:
    tmp = tempfile.mkdtemp(prefix="scos-git-approval-")
    try:
        missing_root = Path(tmp) / "does-not-exist-yet"
        store = GitApprovalStore(missing_root)
        check("list_events on missing root returns empty tuple", store.list_events() == ())
        check(
            "list_commit_proposals on missing root returns empty tuple",
            store.list_commit_proposals() == (),
        )
        check("missing root still does not exist", not missing_root.exists())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_5_append_only_and_stable_json() -> None:
    tmp = tempfile.mkdtemp(prefix="scos-git-approval-")
    try:
        store = GitApprovalStore(tmp)
        _snapshot, proposal, commit_decision, *_ = _build_full_lifecycle()
        store.append_commit_proposal(proposal)
        store.append_commit_proposal(proposal)
        lines = (Path(tmp) / "git_commit_proposals.jsonl").read_text(encoding="utf-8").splitlines()
        check("append-only keeps both lines", len(lines) == 2)
        check("stable JSON output is byte-identical", lines[0] == lines[1])
        check(
            "rejects wrong type for append_commit_proposal",
            _raises(lambda: store.append_commit_proposal(commit_decision)),
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_6_rejects_url_root() -> None:
    check(
        "rejects http:// root",
        _raises(lambda: GitApprovalStore("http://example.com/data")),
    )
    check(
        "rejects https:// root",
        _raises(lambda: GitApprovalStore("https://example.com/data")),
    )


def test_7_multiple_event_types_preserved() -> None:
    tmp = tempfile.mkdtemp(prefix="scos-git-approval-")
    try:
        store = GitApprovalStore(tmp)
        for event_type in (
            "git_evidence_snapshot_created",
            "commit_proposal_created",
            "commit_approval_recorded",
            "push_readiness_snapshot_created",
            "push_proposal_created",
            "push_approval_recorded",
            "git_gate_blocked",
        ):
            event = build_git_approval_event(
                event_type=event_type,
                task_id="task-58",
                session_id="sess-58",
                related_id="rel-1",
                summary=f"{event_type} happened",
                created_at="2026-07-06T10:00:00Z",
            )
            store.append_event(event)
        events = store.list_events()
        check("all seven events stored", len(events) == 7)
        check(
            "event types preserved in order",
            [event.event_type for event in events]
            == [
                "git_evidence_snapshot_created",
                "commit_proposal_created",
                "commit_approval_recorded",
                "push_readiness_snapshot_created",
                "push_proposal_created",
                "push_approval_recorded",
                "git_gate_blocked",
            ],
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    tests = [
        test_1_append_and_list_roundtrip,
        test_2_lists_are_immutable_tuples,
        test_3_parent_dir_auto_created,
        test_4_list_only_creates_nothing,
        test_5_append_only_and_stable_json,
        test_6_rejects_url_root,
        test_7_multiple_event_types_preserved,
    ]
    for test in tests:
        print(f"{test.__name__}:")
        test()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
