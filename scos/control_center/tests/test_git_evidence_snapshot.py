"""test_git_evidence_snapshot.py - SCOS Stage 5.8 evidence snapshot builder suite.

Plain executable script (no pytest). Covers deterministic snapshot IDs,
branch/remote-only-commit rejection, path rejection, and push-readiness
validation.

Run: python scos/control_center/tests/test_git_evidence_snapshot.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
sys.path.insert(0, str(_PACKAGE))

from git_approval_models import GitApprovalError  # noqa: E402
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


_VALID_CHANGED_FILES = (
    {"path": "scos/control_center/git_approval_models.py", "change_type": "added", "summary": "new"},
)
_VALID_TEST_EVIDENCE = (
    {
        "evidence_id": "ev-1",
        "command_label": "python test.py",
        "status": "passed",
        "summary": "ok",
        "passed_count": 5,
    },
)


def _build_snapshot(**overrides):
    kwargs = dict(
        task_id="task-58",
        session_id="sess-58",
        source_intake_id=None,
        branch="main",
        head_commit="09fd1cd8",
        origin_main_commit="09fd1cd8",
        is_clean_before_stage=True,
        has_remote_only_commits=False,
        changed_files=_VALID_CHANGED_FILES,
        test_evidence=_VALID_TEST_EVIDENCE,
        created_at="2026-07-06T10:00:00Z",
    )
    kwargs.update(overrides)
    return build_git_evidence_snapshot(**kwargs)


def _build_push_snapshot(**overrides):
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


def test_1_builds_deterministic_snapshot_id() -> None:
    first = _build_snapshot()
    second = _build_snapshot()
    check("snapshot builds ok", first.ok is True)
    check("snapshot id is deterministic", first.snapshot_id == second.snapshot_id)
    check("snapshot id has expected prefix", first.snapshot_id.startswith("ges-"))
    different = _build_snapshot(created_at="2026-07-06T11:00:00Z")
    check("different created_at yields different id", different.snapshot_id != first.snapshot_id)


def test_2_rejects_non_main_branch() -> None:
    result = _build_snapshot(branch="develop")
    check("rejects non-main branch", isinstance(result, GitApprovalError))
    check("error kind is invalid_branch", result.error_kind == "invalid_branch")


def test_3_rejects_remote_only_commits() -> None:
    result = _build_snapshot(has_remote_only_commits=True)
    check("rejects remote-only commits", isinstance(result, GitApprovalError))
    check("error kind is remote_only_commits", result.error_kind == "remote_only_commits")


def test_4_rejects_url_path() -> None:
    result = _build_snapshot(
        changed_files=(
            {"path": "https://example.com/file.py", "change_type": "added", "summary": "x"},
        )
    )
    check("rejects URL-like path", isinstance(result, GitApprovalError))
    check("error kind is invalid_file_path", result.error_kind == "invalid_file_path")


def test_5_rejects_absolute_path() -> None:
    result = _build_snapshot(
        changed_files=(
            {"path": "/etc/passwd", "change_type": "added", "summary": "x"},
        )
    )
    check("rejects absolute path", isinstance(result, GitApprovalError))
    check("error kind is invalid_file_path", result.error_kind == "invalid_file_path")


def test_6_rejects_missing_test_evidence_for_readiness() -> None:
    no_passed = _build_snapshot(
        test_evidence=(
            {
                "evidence_id": "ev-1",
                "command_label": "python test.py",
                "status": "failed",
                "summary": "broken",
                "failed_count": 1,
            },
        )
    )
    check("rejects missing passed evidence", isinstance(no_passed, GitApprovalError))
    check(
        "error kind is missing_test_evidence",
        no_passed.error_kind == "missing_test_evidence",
    )


def test_7_accepts_passed_test_evidence() -> None:
    result = _build_snapshot()
    check("accepts snapshot with passed evidence", result.ok is True)
    check("snapshot has one test evidence entry", len(result.test_evidence) == 1)


def test_8_creates_push_readiness_snapshot() -> None:
    result = _build_push_snapshot()
    check("push readiness snapshot builds ok", result.ok is True)
    check("push readiness snapshot id has prefix", result.push_snapshot_id.startswith("prs-"))
    check("ahead_by preserved", result.ahead_by == 1)


def test_9_rejects_unsafe_push_readiness() -> None:
    non_main = _build_push_snapshot(branch="develop")
    check("rejects non-main branch push snapshot", isinstance(non_main, GitApprovalError))
    check(
        "error kind is invalid_branch",
        non_main.error_kind == "invalid_branch",
    )
    negative_ahead = _build_push_snapshot(ahead_by=-1)
    check("rejects negative ahead_by", isinstance(negative_ahead, GitApprovalError))


def test_10_rejects_empty_changed_files() -> None:
    result = _build_snapshot(changed_files=())
    check("rejects empty changed_files", isinstance(result, GitApprovalError))
    check("error kind is empty_required_field", result.error_kind == "empty_required_field")


def main() -> int:
    tests = [
        test_1_builds_deterministic_snapshot_id,
        test_2_rejects_non_main_branch,
        test_3_rejects_remote_only_commits,
        test_4_rejects_url_path,
        test_5_rejects_absolute_path,
        test_6_rejects_missing_test_evidence_for_readiness,
        test_7_accepts_passed_test_evidence,
        test_8_creates_push_readiness_snapshot,
        test_9_rejects_unsafe_push_readiness,
        test_10_rejects_empty_changed_files,
    ]
    for test in tests:
        print(f"{test.__name__}:")
        test()
    print(f"\n{_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
