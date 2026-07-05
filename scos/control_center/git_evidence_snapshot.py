"""SCOS Stage 5.8 Git Evidence Snapshot builder.

Pure, side-effect-free functions that turn caller-supplied facts about local
git/test state into a ``GitEvidenceSnapshot`` or ``PushReadinessSnapshot``.

This module NEVER runs a subprocess, never executes an actual git command,
never mutates the filesystem, never opens a network connection, and never
reads the real clock/random/uuid state. Every field (branch, commit hashes,
ahead/behind counts, timestamps) must be supplied by the caller, typically
sourced from operator-provided ``git status``/``git rev-parse`` evidence.

Local-first, deterministic, stdlib-only.
"""

from __future__ import annotations

import hashlib
from typing import Any

try:
    from .git_approval_models import (
        GIT_APPROVAL_SCHEMA_VERSION,
        GitApprovalError,
        GitChangedFile,
        GitEvidenceSnapshot,
        GitTestEvidence,
        PushReadinessSnapshot,
        _validate_repo_relative_path,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from git_approval_models import (
        GIT_APPROVAL_SCHEMA_VERSION,
        GitApprovalError,
        GitChangedFile,
        GitEvidenceSnapshot,
        GitTestEvidence,
        PushReadinessSnapshot,
        _validate_repo_relative_path,
    )

GIT_EVIDENCE_SNAPSHOT_SCHEMA_VERSION = 1

_ID_DIGEST_LENGTH = 16
_REQUIRED_BRANCH = "main"


def _fail(
    error_kind: str,
    error_detail: str,
    failed_stage: str,
    *,
    metadata: Any = None,
) -> GitApprovalError:
    return GitApprovalError.of(error_kind, error_detail, failed_stage, metadata=metadata)


def _check_nonempty(field_name: str, value: Any, failed_stage: str) -> GitApprovalError | None:
    if value is None or not str(value).strip():
        return _fail(
            "empty_required_field", f"{field_name} must not be empty", failed_stage
        )
    return None


def _check_collection(
    field_name: str, value: Any, failed_stage: str
) -> GitApprovalError | None:
    if value is not None and not isinstance(value, (tuple, list)):
        return _fail(
            "invalid_collection_type", f"{field_name} must be a tuple or list", failed_stage
        )
    return None


def _stable_digest(parts) -> str:
    return hashlib.sha256(
        "|".join("" if part is None else str(part) for part in parts).encode("utf-8")
    ).hexdigest()[:_ID_DIGEST_LENGTH]


def _derive_snapshot_id(
    *, task_id, session_id, branch, head_commit, origin_main_commit, created_at
) -> str:
    digest = _stable_digest(
        (task_id, session_id, branch, head_commit, origin_main_commit, created_at)
    )
    return f"ges-{digest}"


def _derive_push_snapshot_id(
    *, branch, head_commit, origin_main_commit, ahead_by, behind_by, created_at
) -> str:
    digest = _stable_digest(
        (branch, head_commit, origin_main_commit, ahead_by, behind_by, created_at)
    )
    return f"prs-{digest}"


def _build_changed_file(entry: dict) -> GitChangedFile | GitApprovalError:
    if not isinstance(entry, dict):
        return _fail(
            "invalid_file_path", "changed_files entries must be dicts", "changed_files"
        )
    path = entry.get("path")
    if not isinstance(path, str) or not path.strip():
        return _fail(
            "invalid_file_path", "changed file path must be a non-empty string", "changed_files"
        )
    try:
        _validate_repo_relative_path("path", path)
    except ValueError as exc:
        return _fail("invalid_file_path", str(exc), "changed_files")
    try:
        return GitChangedFile.of(
            path,
            entry.get("change_type", "unknown"),
            entry.get("summary", ""),
            staged=bool(entry.get("staged", False)),
            metadata=entry.get("metadata"),
        )
    except ValueError as exc:
        return _fail("contract_violation", str(exc), "GitChangedFile.of")


def _build_test_evidence(entry: dict) -> GitTestEvidence | GitApprovalError:
    if not isinstance(entry, dict):
        return _fail(
            "missing_test_evidence", "test_evidence entries must be dicts", "test_evidence"
        )
    try:
        return GitTestEvidence.of(
            entry.get("evidence_id", ""),
            entry.get("command_label", ""),
            entry.get("status", "unknown"),
            entry.get("summary", ""),
            passed_count=int(entry.get("passed_count", 0)),
            failed_count=int(entry.get("failed_count", 0)),
            warning_count=int(entry.get("warning_count", 0)),
            output_path=entry.get("output_path"),
            metadata=entry.get("metadata"),
        )
    except ValueError as exc:
        return _fail("contract_violation", str(exc), "GitTestEvidence.of")


def build_git_evidence_snapshot(
    *,
    task_id: str,
    session_id: str,
    source_intake_id: str | None,
    branch: str,
    head_commit: str,
    origin_main_commit: str,
    is_clean_before_stage: bool,
    has_remote_only_commits: bool,
    changed_files: tuple[dict, ...],
    test_evidence: tuple[dict, ...],
    created_at: str,
    metadata: dict | None = None,
) -> GitEvidenceSnapshot | GitApprovalError:
    for check in (
        _check_nonempty("task_id", task_id, "git_evidence_snapshot"),
        _check_nonempty("session_id", session_id, "git_evidence_snapshot"),
        _check_nonempty("branch", branch, "git_evidence_snapshot"),
        _check_nonempty("head_commit", head_commit, "git_evidence_snapshot"),
        _check_nonempty("origin_main_commit", origin_main_commit, "git_evidence_snapshot"),
        _check_nonempty("created_at", created_at, "git_evidence_snapshot"),
        _check_collection("changed_files", changed_files, "git_evidence_snapshot"),
        _check_collection("test_evidence", test_evidence, "git_evidence_snapshot"),
    ):
        if check is not None:
            return check

    if branch != _REQUIRED_BRANCH:
        return _fail(
            "invalid_branch",
            f"branch must be {_REQUIRED_BRANCH!r}, got {branch!r}",
            "git_evidence_snapshot",
        )

    if has_remote_only_commits:
        return _fail(
            "remote_only_commits",
            "cannot build an evidence snapshot while remote has commits not "
            "present locally; fetch/rebase manually first",
            "git_evidence_snapshot",
        )

    resolved_changed_files: list[GitChangedFile] = []
    for entry in changed_files or ():
        built = _build_changed_file(entry)
        if isinstance(built, GitApprovalError):
            return built
        resolved_changed_files.append(built)

    if not resolved_changed_files:
        return _fail(
            "empty_required_field",
            "changed_files must not be empty for commit proposal readiness",
            "git_evidence_snapshot",
        )

    resolved_test_evidence: list[GitTestEvidence] = []
    for entry in test_evidence or ():
        built = _build_test_evidence(entry)
        if isinstance(built, GitApprovalError):
            return built
        resolved_test_evidence.append(built)

    if not any(evidence.status == "passed" for evidence in resolved_test_evidence):
        return _fail(
            "missing_test_evidence",
            "test_evidence must include at least one passed evidence item "
            "before a commit can be proposed",
            "git_evidence_snapshot",
        )

    risk_flags: list[str] = []
    if not is_clean_before_stage:
        risk_flags.append("unsafe_git_state")
    if any(evidence.status == "failed" for evidence in resolved_test_evidence):
        risk_flags.append("failed_tests")

    snapshot_id = _derive_snapshot_id(
        task_id=task_id,
        session_id=session_id,
        branch=branch,
        head_commit=head_commit,
        origin_main_commit=origin_main_commit,
        created_at=created_at,
    )

    try:
        return GitEvidenceSnapshot.of(
            snapshot_id,
            task_id,
            session_id,
            branch,
            head_commit,
            origin_main_commit,
            created_at,
            source_intake_id=source_intake_id,
            is_clean_before_stage=is_clean_before_stage,
            has_remote_only_commits=has_remote_only_commits,
            changed_files=tuple(resolved_changed_files),
            test_evidence=tuple(resolved_test_evidence),
            risk_flags=tuple(risk_flags),
            metadata=metadata,
        )
    except ValueError as exc:
        return _fail("contract_violation", str(exc), "GitEvidenceSnapshot.of")


def build_push_readiness_snapshot(
    *,
    branch: str,
    head_commit: str,
    origin_main_commit: str,
    ahead_by: int,
    behind_by: int,
    has_remote_only_commits: bool,
    working_tree_clean: bool,
    latest_commit_message: str,
    created_at: str,
    metadata: dict | None = None,
) -> PushReadinessSnapshot | GitApprovalError:
    for check in (
        _check_nonempty("branch", branch, "push_readiness_snapshot"),
        _check_nonempty("head_commit", head_commit, "push_readiness_snapshot"),
        _check_nonempty(
            "origin_main_commit", origin_main_commit, "push_readiness_snapshot"
        ),
        _check_nonempty("created_at", created_at, "push_readiness_snapshot"),
    ):
        if check is not None:
            return check

    if branch != _REQUIRED_BRANCH:
        return _fail(
            "invalid_branch",
            f"branch must be {_REQUIRED_BRANCH!r}, got {branch!r}",
            "push_readiness_snapshot",
        )

    try:
        ahead_by_int = int(ahead_by)
        behind_by_int = int(behind_by)
    except (TypeError, ValueError):
        return _fail(
            "validation_error",
            "ahead_by/behind_by must be integers",
            "push_readiness_snapshot",
        )

    if ahead_by_int < 0 or behind_by_int < 0:
        return _fail(
            "validation_error",
            "ahead_by/behind_by must be >= 0",
            "push_readiness_snapshot",
        )

    push_snapshot_id = _derive_push_snapshot_id(
        branch=branch,
        head_commit=head_commit,
        origin_main_commit=origin_main_commit,
        ahead_by=ahead_by_int,
        behind_by=behind_by_int,
        created_at=created_at,
    )

    try:
        return PushReadinessSnapshot.of(
            push_snapshot_id,
            branch,
            head_commit,
            origin_main_commit,
            ahead_by_int,
            behind_by_int,
            bool(working_tree_clean),
            latest_commit_message,
            created_at,
            has_remote_only_commits=bool(has_remote_only_commits),
            metadata=metadata,
        )
    except ValueError as exc:
        return _fail("contract_violation", str(exc), "PushReadinessSnapshot.of")
