"""SCOS Stage 5.8 Git Commit / Push Approval Gate builder.

Pure, side-effect-free functions that turn a ``GitEvidenceSnapshot`` into a
``CommitProposal``, record an operator's ``CommitApprovalDecision``, turn an
approved commit decision plus a ``PushReadinessSnapshot`` into a
``PushProposal``, and record an operator's ``PushApprovalDecision``.

This module NEVER runs ``git add``, ``git commit``, ``git push``, creates a
tag/release, calls a subprocess, or calls a network/GitHub API. Every
function here only ever produces data plus inert guidance text for a human
operator to type and run themselves.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid.
"""

from __future__ import annotations

import hashlib
from typing import Any

try:
    from .git_approval_models import (
        ALLOWED_APPROVAL_DECISIONS,
        GIT_APPROVAL_SCHEMA_VERSION,
        CommitApprovalDecision,
        CommitProposal,
        GitApprovalError,
        GitApprovalEvent,
        GitEvidenceSnapshot,
        PushApprovalDecision,
        PushProposal,
        PushReadinessSnapshot,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from git_approval_models import (
        ALLOWED_APPROVAL_DECISIONS,
        GIT_APPROVAL_SCHEMA_VERSION,
        CommitApprovalDecision,
        CommitProposal,
        GitApprovalError,
        GitApprovalEvent,
        GitEvidenceSnapshot,
        PushApprovalDecision,
        PushProposal,
        PushReadinessSnapshot,
    )

GIT_APPROVAL_BUILDER_SCHEMA_VERSION = 1

_ID_DIGEST_LENGTH = 16

_ALLOWED_COMMIT_PREFIXES = (
    "feat(",
    "fix(",
    "docs(",
    "test(",
    "chore(",
    "refactor(",
    "perf(",
    "build(",
    "ci(",
)

# Substrings that would let a "commit message" smuggle a second shell command
# if a human ever pasted it verbatim into a terminal.
_FORBIDDEN_MESSAGE_MARKERS = ("&&", "||", ";", "|", ">", "<", "`", "$")

_BLOCKING_RISK_FLAGS = (
    "critical",
    "unsafe_git_state",
    "missing_tests",
    "remote_only_commits",
)

_PUSH_PROPOSED_COMMAND = "git push origin main"


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


def _check_decision(value: Any, failed_stage: str) -> GitApprovalError | None:
    if value not in ALLOWED_APPROVAL_DECISIONS:
        return _fail(
            "invalid_decision",
            f"decision={value!r} is not one of {list(ALLOWED_APPROVAL_DECISIONS)}",
            failed_stage,
        )
    return None


def _stable_digest(parts) -> str:
    return hashlib.sha256(
        "|".join("" if part is None else str(part) for part in parts).encode("utf-8")
    ).hexdigest()[:_ID_DIGEST_LENGTH]


def _derive_proposal_id(*, snapshot_id, commit_message, proposed_at) -> str:
    digest = _stable_digest((snapshot_id, commit_message, proposed_at))
    return f"cp-{digest}"


def _derive_commit_decision_id(*, proposal_id, decision, decided_by, decided_at) -> str:
    digest = _stable_digest((proposal_id, decision, decided_by, decided_at))
    return f"cad-{digest}"


def _derive_push_proposal_id(*, commit_decision_id, push_snapshot_id, proposed_at) -> str:
    digest = _stable_digest((commit_decision_id, push_snapshot_id, proposed_at))
    return f"pp-{digest}"


def _derive_push_decision_id(*, push_proposal_id, decision, decided_by, decided_at) -> str:
    digest = _stable_digest((push_proposal_id, decision, decided_by, decided_at))
    return f"pad-{digest}"


def _derive_event_id(*, event_type, related_id, created_at) -> str:
    digest = _stable_digest((event_type, related_id, created_at))
    return f"gae-{digest}"


def _validate_commit_message(commit_message: str) -> GitApprovalError | None:
    if "\n" in commit_message:
        return _fail(
            "invalid_commit_message",
            "commit_message must be a single line",
            "build_commit_proposal",
        )
    if not commit_message.startswith(_ALLOWED_COMMIT_PREFIXES):
        return _fail(
            "invalid_commit_message",
            f"commit_message must start with one of {list(_ALLOWED_COMMIT_PREFIXES)}",
            "build_commit_proposal",
        )
    for marker in _FORBIDDEN_MESSAGE_MARKERS:
        if marker in commit_message:
            return _fail(
                "forbidden_command",
                f"commit_message must not contain shell operator {marker!r}",
                "build_commit_proposal",
            )
    return None


def build_commit_proposal(
    *,
    snapshot: GitEvidenceSnapshot,
    commit_message: str,
    commit_body: str = "",
    proposed_at: str,
    metadata: dict | None = None,
) -> CommitProposal | GitApprovalError:
    if not isinstance(snapshot, GitEvidenceSnapshot):
        return _fail(
            "contract_violation",
            "snapshot must be a GitEvidenceSnapshot",
            "build_commit_proposal",
        )
    for check in (
        _check_nonempty("commit_message", commit_message, "build_commit_proposal"),
        _check_nonempty("proposed_at", proposed_at, "build_commit_proposal"),
    ):
        if check is not None:
            return check

    message_error = _validate_commit_message(commit_message)
    if message_error is not None:
        return message_error

    if snapshot.has_remote_only_commits:
        return _fail(
            "remote_only_commits",
            "cannot propose a commit while remote has commits not present "
            "locally",
            "build_commit_proposal",
        )

    if not any(evidence.status == "passed" for evidence in snapshot.test_evidence):
        return _fail(
            "missing_test_evidence",
            "at least one passed GitTestEvidence entry is required to "
            "propose a commit",
            "build_commit_proposal",
        )

    for flag in _BLOCKING_RISK_FLAGS:
        if flag in snapshot.risk_flags:
            return _fail(
                "blocked_risk",
                f"snapshot.risk_flags contains blocking flag {flag!r}",
                "build_commit_proposal",
            )

    failed_tests = [
        evidence for evidence in snapshot.test_evidence if evidence.status == "failed"
    ]
    warned_tests = [
        evidence for evidence in snapshot.test_evidence if evidence.warning_count > 0
    ]
    if failed_tests:
        risk_level = "high"
    elif warned_tests:
        risk_level = "medium"
    else:
        risk_level = "low"

    files_to_commit = tuple(sorted(item.path for item in snapshot.changed_files))

    passed_evidence = [
        evidence for evidence in snapshot.test_evidence if evidence.status == "passed"
    ]
    test_summary = (
        f"{len(passed_evidence)} passed, {len(failed_tests)} failed, "
        f"{len(warned_tests)} with warnings across {len(snapshot.test_evidence)} "
        "evidence item(s)"
    )
    evidence_summary = (
        f"{len(snapshot.changed_files)} changed file(s) on branch "
        f"{snapshot.branch!r} at {snapshot.head_commit}"
    )

    commit_title = commit_message.split(":", 1)[-1].strip() if ":" in commit_message else commit_message

    proposal_id = _derive_proposal_id(
        snapshot_id=snapshot.snapshot_id,
        commit_message=commit_message,
        proposed_at=proposed_at,
    )

    try:
        return CommitProposal.of(
            proposal_id,
            snapshot.snapshot_id,
            snapshot.task_id,
            snapshot.session_id,
            commit_message,
            commit_title,
            files_to_commit,
            evidence_summary,
            test_summary,
            risk_level,
            proposed_at,
            commit_body=commit_body,
            metadata=metadata,
        )
    except ValueError as exc:
        return _fail("contract_violation", str(exc), "CommitProposal.of")


def _manual_commit_command(proposal: CommitProposal) -> str:
    file_list = " ".join(proposal.files_to_commit)
    escaped_message = proposal.commit_message.replace('"', '\\"')
    return f'git add {file_list}\ngit commit -m "{escaped_message}"'


def record_commit_approval_decision(
    *,
    proposal: CommitProposal,
    decision: str,
    decided_by: str,
    decided_at: str,
    reason: str,
    metadata: dict | None = None,
) -> CommitApprovalDecision | GitApprovalError:
    if not isinstance(proposal, CommitProposal):
        return _fail(
            "contract_violation",
            "proposal must be a CommitProposal",
            "record_commit_approval_decision",
        )
    for check in (
        _check_decision(decision, "record_commit_approval_decision"),
        _check_nonempty("decided_by", decided_by, "record_commit_approval_decision"),
        _check_nonempty("decided_at", decided_at, "record_commit_approval_decision"),
        _check_nonempty("reason", reason, "record_commit_approval_decision"),
    ):
        if check is not None:
            return check

    decision_id = _derive_commit_decision_id(
        proposal_id=proposal.proposal_id,
        decision=decision,
        decided_by=decided_by,
        decided_at=decided_at,
    )

    manual_command = None
    try:
        if decision == "approved":
            manual_command = _manual_commit_command(proposal)
        return CommitApprovalDecision.of(
            decision_id,
            proposal.proposal_id,
            decision,
            decided_by,
            decided_at,
            reason,
            manual_command=manual_command,
            metadata=metadata,
        )
    except ValueError as exc:
        return _fail("contract_violation", str(exc), "CommitApprovalDecision.of")


def build_push_proposal(
    *,
    commit_decision: CommitApprovalDecision,
    push_snapshot: PushReadinessSnapshot,
    proposed_at: str,
    metadata: dict | None = None,
) -> PushProposal | GitApprovalError:
    if not isinstance(commit_decision, CommitApprovalDecision):
        return _fail(
            "contract_violation",
            "commit_decision must be a CommitApprovalDecision",
            "build_push_proposal",
        )
    if not isinstance(push_snapshot, PushReadinessSnapshot):
        return _fail(
            "contract_violation",
            "push_snapshot must be a PushReadinessSnapshot",
            "build_push_proposal",
        )
    check = _check_nonempty("proposed_at", proposed_at, "build_push_proposal")
    if check is not None:
        return check

    if commit_decision.decision != "approved":
        return _fail(
            "missing_approval",
            "a push may only be proposed once the commit decision is "
            "'approved'",
            "build_push_proposal",
        )
    if push_snapshot.branch != "main":
        return _fail(
            "invalid_branch",
            f"push_snapshot.branch must be 'main', got {push_snapshot.branch!r}",
            "build_push_proposal",
        )
    if push_snapshot.ahead_by < 1:
        return _fail(
            "unsafe_push",
            "push_snapshot.ahead_by must be >= 1 to propose a push",
            "build_push_proposal",
        )
    if push_snapshot.behind_by != 0:
        return _fail(
            "unsafe_push",
            "push_snapshot.behind_by must be 0 to propose a push",
            "build_push_proposal",
        )
    if push_snapshot.has_remote_only_commits:
        return _fail(
            "remote_only_commits",
            "cannot propose a push while remote has commits not present "
            "locally",
            "build_push_proposal",
        )
    if not push_snapshot.working_tree_clean:
        return _fail(
            "dirty_worktree",
            "push_snapshot.working_tree_clean must be True to propose a push",
            "build_push_proposal",
        )

    push_proposal_id = _derive_push_proposal_id(
        commit_decision_id=commit_decision.decision_id,
        push_snapshot_id=push_snapshot.push_snapshot_id,
        proposed_at=proposed_at,
    )

    try:
        return PushProposal.of(
            push_proposal_id,
            commit_decision.decision_id,
            push_snapshot.push_snapshot_id,
            proposed_at,
            risk_level="low",
            metadata=metadata,
        )
    except ValueError as exc:
        return _fail("contract_violation", str(exc), "PushProposal.of")


def record_push_approval_decision(
    *,
    proposal: PushProposal,
    decision: str,
    decided_by: str,
    decided_at: str,
    reason: str,
    metadata: dict | None = None,
) -> PushApprovalDecision | GitApprovalError:
    if not isinstance(proposal, PushProposal):
        return _fail(
            "contract_violation",
            "proposal must be a PushProposal",
            "record_push_approval_decision",
        )
    for check in (
        _check_decision(decision, "record_push_approval_decision"),
        _check_nonempty("decided_by", decided_by, "record_push_approval_decision"),
        _check_nonempty("decided_at", decided_at, "record_push_approval_decision"),
        _check_nonempty("reason", reason, "record_push_approval_decision"),
    ):
        if check is not None:
            return check

    push_decision_id = _derive_push_decision_id(
        push_proposal_id=proposal.push_proposal_id,
        decision=decision,
        decided_by=decided_by,
        decided_at=decided_at,
    )

    manual_command = _PUSH_PROPOSED_COMMAND if decision == "approved" else None

    try:
        return PushApprovalDecision.of(
            push_decision_id,
            proposal.push_proposal_id,
            decision,
            decided_by,
            decided_at,
            reason,
            manual_command=manual_command,
            metadata=metadata,
        )
    except ValueError as exc:
        return _fail("contract_violation", str(exc), "PushApprovalDecision.of")


def build_git_approval_event(
    *,
    event_type: str,
    task_id: str,
    session_id: str,
    related_id: str,
    summary: str,
    created_at: str,
    metadata: dict | None = None,
) -> GitApprovalEvent | GitApprovalError:
    for check in (
        _check_nonempty("event_type", event_type, "build_git_approval_event"),
        _check_nonempty("task_id", task_id, "build_git_approval_event"),
        _check_nonempty("session_id", session_id, "build_git_approval_event"),
        _check_nonempty("related_id", related_id, "build_git_approval_event"),
        _check_nonempty("summary", summary, "build_git_approval_event"),
        _check_nonempty("created_at", created_at, "build_git_approval_event"),
    ):
        if check is not None:
            return check

    event_id = _derive_event_id(
        event_type=event_type, related_id=related_id, created_at=created_at
    )

    try:
        return GitApprovalEvent.of(
            event_id,
            event_type,
            task_id,
            session_id,
            related_id,
            summary,
            created_at,
            metadata=metadata,
        )
    except ValueError as exc:
        return _fail("contract_violation", str(exc), "GitApprovalEvent.of")
