"""SCOS Stage 5.8 Git Commit / Push Approval Gate models.

Immutable dataclasses that model a deterministic, local-first approval gate
between an approved AI result / operator evidence and an actual git
commit/push. This module NEVER runs ``git add``, ``git commit``, ``git
push``, creates tags/releases, calls a subprocess, mutates git state, or
calls a network/GitHub API. It only models proposals and operator decisions
so a human can execute the real git commands manually.

``FrozenMap`` is reused from ``operator_packet_review_models`` (Stage 5.5)
per the existing project convention: one immutable string-keyed map class
shared across ``scos.control_center`` model modules rather than a new one
per stage.

All collection fields are tuples, so no mutable dict/list is ever exposed
from a model instance. ``to_dict()`` uses explicit key order and serializes
tuples as lists and ``FrozenMap`` as a plain dict.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid,
no subprocess, no network.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from .operator_packet_review_models import FrozenMap
except ImportError:  # direct-module execution (tests insert the package dir)
    from operator_packet_review_models import FrozenMap

GIT_APPROVAL_SCHEMA_VERSION = 1

ALLOWED_CHANGE_TYPES = (
    "added",
    "modified",
    "deleted",
    "renamed",
    "copied",
    "unknown",
)

ALLOWED_TEST_EVIDENCE_STATUSES = ("passed", "failed", "skipped", "unknown")

# Shared by CommitProposal.risk_level and PushProposal.risk_level.
ALLOWED_RISK_LEVELS = ("low", "medium", "high", "blocked")

# Shared by CommitApprovalDecision.decision and PushApprovalDecision.decision.
ALLOWED_APPROVAL_DECISIONS = ("approved", "rejected", "needs_changes", "blocked")

ALLOWED_GIT_APPROVAL_EVENT_TYPES = (
    "git_evidence_snapshot_created",
    "commit_proposal_created",
    "commit_approval_recorded",
    "push_readiness_snapshot_created",
    "push_proposal_created",
    "push_approval_recorded",
    "git_gate_blocked",
)

ALLOWED_GIT_APPROVAL_ERROR_KINDS = (
    "invalid_branch",
    "remote_only_commits",
    "dirty_worktree",
    "missing_test_evidence",
    "blocked_risk",
    "invalid_commit_message",
    "invalid_file_path",
    "forbidden_command",
    "missing_approval",
    "unsafe_push",
    "validation_error",
    "invalid_change_type",
    "invalid_status",
    "invalid_decision",
    "invalid_event_type",
    "invalid_risk_level",
    "invalid_remote",
    "invalid_refspec",
    "empty_required_field",
    "invalid_collection_type",
    "contract_violation",
)

_FORBIDDEN_URL_MARKERS = ("http://", "https://")
_URL_SCHEME_MARKER = "://"


def _require_allowed(field_name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ValueError(f"{field_name} must be one of {list(allowed)}, got {value!r}")


def _require_exact(field_name: str, value: str, expected: str) -> None:
    if value != expected:
        raise ValueError(f"{field_name} must be {expected!r}, got {value!r}")


def _require_nonempty(field_name: str, value: str | None) -> None:
    if value is None or not str(value).strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_non_negative_int(field_name: str, value: int) -> None:
    if int(value) < 0:
        raise ValueError(f"{field_name} must be >= 0, got {value!r}")


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _string_tuple(field_name: str, value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    return tuple(str(item) for item in value)


def _reject_url(field_name: str, value: str | None) -> None:
    if value is None:
        return
    lowered = value.lower()
    for marker in _FORBIDDEN_URL_MARKERS:
        if marker in lowered:
            raise ValueError(
                f"{field_name} must be a local path/value, not a URL "
                f"(found {marker!r})"
            )


def _reject_absolute_path(field_name: str, value: str) -> None:
    if value.startswith("/") or value.startswith("\\"):
        raise ValueError(f"{field_name} must be repo-relative, not absolute: {value!r}")
    if len(value) >= 2 and value[1] == ":" and value[0].isalpha():
        raise ValueError(
            f"{field_name} must be repo-relative, not a drive-letter path: {value!r}"
        )


def _reject_url_like_path(field_name: str, value: str) -> None:
    lowered = value.lower()
    if _URL_SCHEME_MARKER in lowered:
        raise ValueError(f"{field_name} must not look like a URL: {value!r}")
    _reject_url(field_name, value)


def _validate_repo_relative_path(field_name: str, value: str) -> None:
    _require_nonempty(field_name, value)
    _reject_url_like_path(field_name, value)
    _reject_absolute_path(field_name, value)


def _frozen_map(value: Any = None) -> FrozenMap:
    return FrozenMap.of(value)


@dataclass(frozen=True)
class GitChangedFile:
    """One repo-relative file changed as part of a proposed commit."""

    path: str
    change_type: str
    staged: bool
    summary: str
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", str(self.path))
        object.__setattr__(self, "change_type", str(self.change_type))
        object.__setattr__(self, "staged", bool(self.staged))
        object.__setattr__(self, "summary", str(self.summary))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))

        _validate_repo_relative_path("path", self.path)
        _require_allowed("change_type", self.change_type, ALLOWED_CHANGE_TYPES)
        _require_nonempty("summary", self.summary)

    @staticmethod
    def of(
        path: str,
        change_type: str,
        summary: str,
        *,
        staged: bool = False,
        metadata: Any = None,
    ) -> "GitChangedFile":
        return GitChangedFile(
            path=path,
            change_type=change_type,
            staged=staged,
            summary=summary,
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "change_type": self.change_type,
            "staged": self.staged,
            "summary": self.summary,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class GitTestEvidence:
    """One piece of test/command evidence backing a commit proposal."""

    evidence_id: str
    command_label: str
    status: str
    summary: str
    passed_count: int
    failed_count: int
    warning_count: int
    output_path: str | None
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_id", str(self.evidence_id))
        object.__setattr__(self, "command_label", str(self.command_label))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "summary", str(self.summary))
        object.__setattr__(self, "passed_count", int(self.passed_count))
        object.__setattr__(self, "failed_count", int(self.failed_count))
        object.__setattr__(self, "warning_count", int(self.warning_count))
        object.__setattr__(self, "output_path", _optional_str(self.output_path))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))

        _require_nonempty("evidence_id", self.evidence_id)
        _require_nonempty("command_label", self.command_label)
        _require_allowed("status", self.status, ALLOWED_TEST_EVIDENCE_STATUSES)
        _require_non_negative_int("passed_count", self.passed_count)
        _require_non_negative_int("failed_count", self.failed_count)
        _require_non_negative_int("warning_count", self.warning_count)
        _reject_url("output_path", self.output_path)

    @staticmethod
    def of(
        evidence_id: str,
        command_label: str,
        status: str,
        summary: str,
        *,
        passed_count: int = 0,
        failed_count: int = 0,
        warning_count: int = 0,
        output_path: str | None = None,
        metadata: Any = None,
    ) -> "GitTestEvidence":
        return GitTestEvidence(
            evidence_id=evidence_id,
            command_label=command_label,
            status=status,
            summary=summary,
            passed_count=passed_count,
            failed_count=failed_count,
            warning_count=warning_count,
            output_path=output_path,
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "command_label": self.command_label,
            "status": self.status,
            "summary": self.summary,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "warning_count": self.warning_count,
            "output_path": self.output_path,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class GitEvidenceSnapshot:
    """A deterministic snapshot of local git/test state before a commit gate."""

    ok: bool
    schema_version: int
    snapshot_id: str
    task_id: str
    session_id: str
    source_intake_id: str | None
    branch: str
    head_commit: str
    origin_main_commit: str
    is_clean_before_stage: bool
    has_remote_only_commits: bool
    changed_files: tuple[GitChangedFile, ...]
    test_evidence: tuple[GitTestEvidence, ...]
    risk_flags: tuple[str, ...]
    created_at: str
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "snapshot_id", str(self.snapshot_id))
        object.__setattr__(self, "task_id", str(self.task_id))
        object.__setattr__(self, "session_id", str(self.session_id))
        object.__setattr__(self, "source_intake_id", _optional_str(self.source_intake_id))
        object.__setattr__(self, "branch", str(self.branch))
        object.__setattr__(self, "head_commit", str(self.head_commit))
        object.__setattr__(self, "origin_main_commit", str(self.origin_main_commit))
        object.__setattr__(
            self, "is_clean_before_stage", bool(self.is_clean_before_stage)
        )
        object.__setattr__(
            self, "has_remote_only_commits", bool(self.has_remote_only_commits)
        )
        changed_files = tuple(self.changed_files or ())
        for changed_file in changed_files:
            if not isinstance(changed_file, GitChangedFile):
                raise ValueError(
                    "changed_files entries must be GitChangedFile instances"
                )
        object.__setattr__(self, "changed_files", changed_files)
        test_evidence = tuple(self.test_evidence or ())
        for evidence in test_evidence:
            if not isinstance(evidence, GitTestEvidence):
                raise ValueError(
                    "test_evidence entries must be GitTestEvidence instances"
                )
        object.__setattr__(self, "test_evidence", test_evidence)
        object.__setattr__(self, "risk_flags", _string_tuple("risk_flags", self.risk_flags))
        object.__setattr__(self, "created_at", str(self.created_at))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))

        _require_nonempty("snapshot_id", self.snapshot_id)
        _require_nonempty("task_id", self.task_id)
        _require_nonempty("session_id", self.session_id)
        _require_nonempty("branch", self.branch)
        _require_nonempty("head_commit", self.head_commit)
        _require_nonempty("origin_main_commit", self.origin_main_commit)
        _require_nonempty("created_at", self.created_at)

    @staticmethod
    def of(
        snapshot_id: str,
        task_id: str,
        session_id: str,
        branch: str,
        head_commit: str,
        origin_main_commit: str,
        created_at: str,
        *,
        ok: bool = True,
        schema_version: int = GIT_APPROVAL_SCHEMA_VERSION,
        source_intake_id: str | None = None,
        is_clean_before_stage: bool = True,
        has_remote_only_commits: bool = False,
        changed_files: Any = (),
        test_evidence: Any = (),
        risk_flags: Any = (),
        metadata: Any = None,
    ) -> "GitEvidenceSnapshot":
        return GitEvidenceSnapshot(
            ok=ok,
            schema_version=schema_version,
            snapshot_id=snapshot_id,
            task_id=task_id,
            session_id=session_id,
            source_intake_id=source_intake_id,
            branch=branch,
            head_commit=head_commit,
            origin_main_commit=origin_main_commit,
            is_clean_before_stage=is_clean_before_stage,
            has_remote_only_commits=has_remote_only_commits,
            changed_files=tuple(changed_files or ()),
            test_evidence=tuple(test_evidence or ()),
            risk_flags=_string_tuple("risk_flags", risk_flags),
            created_at=created_at,
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "snapshot_id": self.snapshot_id,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "source_intake_id": self.source_intake_id,
            "branch": self.branch,
            "head_commit": self.head_commit,
            "origin_main_commit": self.origin_main_commit,
            "is_clean_before_stage": self.is_clean_before_stage,
            "has_remote_only_commits": self.has_remote_only_commits,
            "changed_files": [item.to_dict() for item in self.changed_files],
            "test_evidence": [item.to_dict() for item in self.test_evidence],
            "risk_flags": list(self.risk_flags),
            "created_at": self.created_at,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class CommitProposal:
    """A proposed (never executed) commit derived from a GitEvidenceSnapshot."""

    ok: bool
    schema_version: int
    proposal_id: str
    snapshot_id: str
    task_id: str
    session_id: str
    commit_message: str
    commit_title: str
    commit_body: str
    files_to_commit: tuple[str, ...]
    evidence_summary: str
    test_summary: str
    risk_level: str
    approval_required: bool
    proposed_at: str
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "proposal_id", str(self.proposal_id))
        object.__setattr__(self, "snapshot_id", str(self.snapshot_id))
        object.__setattr__(self, "task_id", str(self.task_id))
        object.__setattr__(self, "session_id", str(self.session_id))
        object.__setattr__(self, "commit_message", str(self.commit_message))
        object.__setattr__(self, "commit_title", str(self.commit_title))
        object.__setattr__(self, "commit_body", str(self.commit_body))
        object.__setattr__(
            self, "files_to_commit", _string_tuple("files_to_commit", self.files_to_commit)
        )
        object.__setattr__(self, "evidence_summary", str(self.evidence_summary))
        object.__setattr__(self, "test_summary", str(self.test_summary))
        object.__setattr__(self, "risk_level", str(self.risk_level))
        object.__setattr__(self, "approval_required", bool(self.approval_required))
        object.__setattr__(self, "proposed_at", str(self.proposed_at))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))

        _require_nonempty("proposal_id", self.proposal_id)
        _require_nonempty("snapshot_id", self.snapshot_id)
        _require_nonempty("commit_message", self.commit_message)
        _require_nonempty("proposed_at", self.proposed_at)
        if "\n" in self.commit_message:
            raise ValueError("commit_message must be a single line")
        _require_allowed("risk_level", self.risk_level, ALLOWED_RISK_LEVELS)
        if not self.approval_required:
            raise ValueError("approval_required must always be True")

    @staticmethod
    def of(
        proposal_id: str,
        snapshot_id: str,
        task_id: str,
        session_id: str,
        commit_message: str,
        commit_title: str,
        files_to_commit: Any,
        evidence_summary: str,
        test_summary: str,
        risk_level: str,
        proposed_at: str,
        *,
        ok: bool = True,
        schema_version: int = GIT_APPROVAL_SCHEMA_VERSION,
        commit_body: str = "",
        approval_required: bool = True,
        metadata: Any = None,
    ) -> "CommitProposal":
        return CommitProposal(
            ok=ok,
            schema_version=schema_version,
            proposal_id=proposal_id,
            snapshot_id=snapshot_id,
            task_id=task_id,
            session_id=session_id,
            commit_message=commit_message,
            commit_title=commit_title,
            commit_body=commit_body,
            files_to_commit=_string_tuple("files_to_commit", files_to_commit),
            evidence_summary=evidence_summary,
            test_summary=test_summary,
            risk_level=risk_level,
            approval_required=approval_required,
            proposed_at=proposed_at,
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "proposal_id": self.proposal_id,
            "snapshot_id": self.snapshot_id,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "commit_message": self.commit_message,
            "commit_title": self.commit_title,
            "commit_body": self.commit_body,
            "files_to_commit": list(self.files_to_commit),
            "evidence_summary": self.evidence_summary,
            "test_summary": self.test_summary,
            "risk_level": self.risk_level,
            "approval_required": self.approval_required,
            "proposed_at": self.proposed_at,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class CommitApprovalDecision:
    """An operator decision on a CommitProposal.

    ``manual_command`` is guidance text only for the operator to type
    themselves; this stage never executes it.
    """

    ok: bool
    schema_version: int
    decision_id: str
    proposal_id: str
    decision: str
    decided_by: str
    decided_at: str
    reason: str
    manual_command: str | None
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "decision_id", str(self.decision_id))
        object.__setattr__(self, "proposal_id", str(self.proposal_id))
        object.__setattr__(self, "decision", str(self.decision))
        object.__setattr__(self, "decided_by", str(self.decided_by))
        object.__setattr__(self, "decided_at", str(self.decided_at))
        object.__setattr__(self, "reason", str(self.reason))
        object.__setattr__(self, "manual_command", _optional_str(self.manual_command))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))

        _require_allowed("decision", self.decision, ALLOWED_APPROVAL_DECISIONS)
        _require_nonempty("decision_id", self.decision_id)
        _require_nonempty("proposal_id", self.proposal_id)
        _require_nonempty("decided_by", self.decided_by)
        _require_nonempty("decided_at", self.decided_at)
        if self.decision != "approved" and self.manual_command is not None:
            raise ValueError(
                "manual_command must be None unless decision == 'approved'"
            )

    @staticmethod
    def of(
        decision_id: str,
        proposal_id: str,
        decision: str,
        decided_by: str,
        decided_at: str,
        reason: str,
        *,
        ok: bool = True,
        schema_version: int = GIT_APPROVAL_SCHEMA_VERSION,
        manual_command: str | None = None,
        metadata: Any = None,
    ) -> "CommitApprovalDecision":
        return CommitApprovalDecision(
            ok=ok,
            schema_version=schema_version,
            decision_id=decision_id,
            proposal_id=proposal_id,
            decision=decision,
            decided_by=decided_by,
            decided_at=decided_at,
            reason=reason,
            manual_command=manual_command,
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "decision_id": self.decision_id,
            "proposal_id": self.proposal_id,
            "decision": self.decision,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at,
            "reason": self.reason,
            "manual_command": self.manual_command,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class PushReadinessSnapshot:
    """A deterministic snapshot of local push-readiness state."""

    ok: bool
    schema_version: int
    push_snapshot_id: str
    branch: str
    head_commit: str
    origin_main_commit: str
    ahead_by: int
    behind_by: int
    has_remote_only_commits: bool
    working_tree_clean: bool
    latest_commit_message: str
    created_at: str
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "push_snapshot_id", str(self.push_snapshot_id))
        object.__setattr__(self, "branch", str(self.branch))
        object.__setattr__(self, "head_commit", str(self.head_commit))
        object.__setattr__(self, "origin_main_commit", str(self.origin_main_commit))
        object.__setattr__(self, "ahead_by", int(self.ahead_by))
        object.__setattr__(self, "behind_by", int(self.behind_by))
        object.__setattr__(
            self, "has_remote_only_commits", bool(self.has_remote_only_commits)
        )
        object.__setattr__(self, "working_tree_clean", bool(self.working_tree_clean))
        object.__setattr__(
            self, "latest_commit_message", str(self.latest_commit_message)
        )
        object.__setattr__(self, "created_at", str(self.created_at))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))

        _require_nonempty("push_snapshot_id", self.push_snapshot_id)
        _require_nonempty("branch", self.branch)
        _require_nonempty("head_commit", self.head_commit)
        _require_nonempty("origin_main_commit", self.origin_main_commit)
        _require_nonempty("created_at", self.created_at)
        _require_non_negative_int("ahead_by", self.ahead_by)
        _require_non_negative_int("behind_by", self.behind_by)

    @staticmethod
    def of(
        push_snapshot_id: str,
        branch: str,
        head_commit: str,
        origin_main_commit: str,
        ahead_by: int,
        behind_by: int,
        working_tree_clean: bool,
        latest_commit_message: str,
        created_at: str,
        *,
        ok: bool = True,
        schema_version: int = GIT_APPROVAL_SCHEMA_VERSION,
        has_remote_only_commits: bool = False,
        metadata: Any = None,
    ) -> "PushReadinessSnapshot":
        return PushReadinessSnapshot(
            ok=ok,
            schema_version=schema_version,
            push_snapshot_id=push_snapshot_id,
            branch=branch,
            head_commit=head_commit,
            origin_main_commit=origin_main_commit,
            ahead_by=ahead_by,
            behind_by=behind_by,
            has_remote_only_commits=has_remote_only_commits,
            working_tree_clean=working_tree_clean,
            latest_commit_message=latest_commit_message,
            created_at=created_at,
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "push_snapshot_id": self.push_snapshot_id,
            "branch": self.branch,
            "head_commit": self.head_commit,
            "origin_main_commit": self.origin_main_commit,
            "ahead_by": self.ahead_by,
            "behind_by": self.behind_by,
            "has_remote_only_commits": self.has_remote_only_commits,
            "working_tree_clean": self.working_tree_clean,
            "latest_commit_message": self.latest_commit_message,
            "created_at": self.created_at,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class PushProposal:
    """A proposed (never executed) ``git push origin main``."""

    ok: bool
    schema_version: int
    push_proposal_id: str
    commit_decision_id: str
    push_snapshot_id: str
    branch: str
    remote: str
    refspec: str
    proposed_command: str
    risk_level: str
    approval_required: bool
    proposed_at: str
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "push_proposal_id", str(self.push_proposal_id))
        object.__setattr__(self, "commit_decision_id", str(self.commit_decision_id))
        object.__setattr__(self, "push_snapshot_id", str(self.push_snapshot_id))
        object.__setattr__(self, "branch", str(self.branch))
        object.__setattr__(self, "remote", str(self.remote))
        object.__setattr__(self, "refspec", str(self.refspec))
        object.__setattr__(self, "proposed_command", str(self.proposed_command))
        object.__setattr__(self, "risk_level", str(self.risk_level))
        object.__setattr__(self, "approval_required", bool(self.approval_required))
        object.__setattr__(self, "proposed_at", str(self.proposed_at))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))

        _require_nonempty("push_proposal_id", self.push_proposal_id)
        _require_nonempty("commit_decision_id", self.commit_decision_id)
        _require_nonempty("push_snapshot_id", self.push_snapshot_id)
        _require_nonempty("proposed_at", self.proposed_at)
        _require_exact("branch", self.branch, "main")
        _require_exact("remote", self.remote, "origin")
        _require_exact("refspec", self.refspec, "main")
        _require_exact("proposed_command", self.proposed_command, "git push origin main")
        _require_allowed("risk_level", self.risk_level, ALLOWED_RISK_LEVELS)
        if not self.approval_required:
            raise ValueError("approval_required must always be True")

    @staticmethod
    def of(
        push_proposal_id: str,
        commit_decision_id: str,
        push_snapshot_id: str,
        proposed_at: str,
        *,
        ok: bool = True,
        schema_version: int = GIT_APPROVAL_SCHEMA_VERSION,
        branch: str = "main",
        remote: str = "origin",
        refspec: str = "main",
        proposed_command: str = "git push origin main",
        risk_level: str = "low",
        approval_required: bool = True,
        metadata: Any = None,
    ) -> "PushProposal":
        return PushProposal(
            ok=ok,
            schema_version=schema_version,
            push_proposal_id=push_proposal_id,
            commit_decision_id=commit_decision_id,
            push_snapshot_id=push_snapshot_id,
            branch=branch,
            remote=remote,
            refspec=refspec,
            proposed_command=proposed_command,
            risk_level=risk_level,
            approval_required=approval_required,
            proposed_at=proposed_at,
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "push_proposal_id": self.push_proposal_id,
            "commit_decision_id": self.commit_decision_id,
            "push_snapshot_id": self.push_snapshot_id,
            "branch": self.branch,
            "remote": self.remote,
            "refspec": self.refspec,
            "proposed_command": self.proposed_command,
            "risk_level": self.risk_level,
            "approval_required": self.approval_required,
            "proposed_at": self.proposed_at,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class PushApprovalDecision:
    """An operator decision on a PushProposal.

    ``manual_command`` is guidance text only for the operator to type
    themselves; this stage never executes it.
    """

    ok: bool
    schema_version: int
    push_decision_id: str
    push_proposal_id: str
    decision: str
    decided_by: str
    decided_at: str
    reason: str
    manual_command: str | None
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "push_decision_id", str(self.push_decision_id))
        object.__setattr__(self, "push_proposal_id", str(self.push_proposal_id))
        object.__setattr__(self, "decision", str(self.decision))
        object.__setattr__(self, "decided_by", str(self.decided_by))
        object.__setattr__(self, "decided_at", str(self.decided_at))
        object.__setattr__(self, "reason", str(self.reason))
        object.__setattr__(self, "manual_command", _optional_str(self.manual_command))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))

        _require_allowed("decision", self.decision, ALLOWED_APPROVAL_DECISIONS)
        _require_nonempty("push_decision_id", self.push_decision_id)
        _require_nonempty("push_proposal_id", self.push_proposal_id)
        _require_nonempty("decided_by", self.decided_by)
        _require_nonempty("decided_at", self.decided_at)
        if self.decision != "approved" and self.manual_command is not None:
            raise ValueError(
                "manual_command must be None unless decision == 'approved'"
            )
        if self.manual_command is not None:
            _require_exact("manual_command", self.manual_command, "git push origin main")

    @staticmethod
    def of(
        push_decision_id: str,
        push_proposal_id: str,
        decision: str,
        decided_by: str,
        decided_at: str,
        reason: str,
        *,
        ok: bool = True,
        schema_version: int = GIT_APPROVAL_SCHEMA_VERSION,
        manual_command: str | None = None,
        metadata: Any = None,
    ) -> "PushApprovalDecision":
        return PushApprovalDecision(
            ok=ok,
            schema_version=schema_version,
            push_decision_id=push_decision_id,
            push_proposal_id=push_proposal_id,
            decision=decision,
            decided_by=decided_by,
            decided_at=decided_at,
            reason=reason,
            manual_command=manual_command,
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "push_decision_id": self.push_decision_id,
            "push_proposal_id": self.push_proposal_id,
            "decision": self.decision,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at,
            "reason": self.reason,
            "manual_command": self.manual_command,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class GitApprovalEvent:
    """One append-only event in the Stage 5.8 git approval timeline."""

    ok: bool
    schema_version: int
    event_id: str
    event_type: str
    task_id: str
    session_id: str
    related_id: str
    summary: str
    created_at: str
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "event_id", str(self.event_id))
        object.__setattr__(self, "event_type", str(self.event_type))
        object.__setattr__(self, "task_id", str(self.task_id))
        object.__setattr__(self, "session_id", str(self.session_id))
        object.__setattr__(self, "related_id", str(self.related_id))
        object.__setattr__(self, "summary", str(self.summary))
        object.__setattr__(self, "created_at", str(self.created_at))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))

        _require_allowed(
            "event_type", self.event_type, ALLOWED_GIT_APPROVAL_EVENT_TYPES
        )
        _require_nonempty("event_id", self.event_id)
        _require_nonempty("task_id", self.task_id)
        _require_nonempty("session_id", self.session_id)
        _require_nonempty("related_id", self.related_id)
        _require_nonempty("summary", self.summary)
        _require_nonempty("created_at", self.created_at)

    @staticmethod
    def of(
        event_id: str,
        event_type: str,
        task_id: str,
        session_id: str,
        related_id: str,
        summary: str,
        created_at: str,
        *,
        ok: bool = True,
        schema_version: int = GIT_APPROVAL_SCHEMA_VERSION,
        metadata: Any = None,
    ) -> "GitApprovalEvent":
        return GitApprovalEvent(
            ok=ok,
            schema_version=schema_version,
            event_id=event_id,
            event_type=event_type,
            task_id=task_id,
            session_id=session_id,
            related_id=related_id,
            summary=summary,
            created_at=created_at,
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "related_id": self.related_id,
            "summary": self.summary,
            "created_at": self.created_at,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class GitApprovalError:
    """A deterministic, structured rejection for an invalid gate operation."""

    ok: bool
    schema_version: int
    error_kind: str
    error_detail: str
    failed_stage: str
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "error_kind", str(self.error_kind))
        object.__setattr__(self, "error_detail", str(self.error_detail))
        object.__setattr__(self, "failed_stage", str(self.failed_stage))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))
        _require_allowed(
            "error_kind", self.error_kind, ALLOWED_GIT_APPROVAL_ERROR_KINDS
        )

    @staticmethod
    def of(
        error_kind: str,
        error_detail: str,
        failed_stage: str,
        *,
        ok: bool = False,
        schema_version: int = GIT_APPROVAL_SCHEMA_VERSION,
        metadata: Any = None,
    ) -> "GitApprovalError":
        return GitApprovalError(
            ok=ok,
            schema_version=schema_version,
            error_kind=error_kind,
            error_detail=error_detail,
            failed_stage=failed_stage,
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "error_kind": self.error_kind,
            "error_detail": self.error_detail,
            "failed_stage": self.failed_stage,
            "metadata": self.metadata.to_dict(),
        }
