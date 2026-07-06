"""SCOS Stage 5.9 Operator Execution Runbook builder.

Pure, deterministic functions that turn an already-approved
``manual_command`` / ``proposed_command`` (Stage 5.8) into a
``ManualCommandRunbook`` (ordered steps + safety checklist), capture the
operator's pasted-back result as a ``CommandExecutionCapture``, and classify
the outcome as an ``OperatorExecutionOutcome``.

This module NEVER executes anything. It does not import ``subprocess``,
``os.system``, ``pty``, ``socket``, ``requests``, ``urllib``, or any network
/ clipboard / terminal facility. Command text is instructional only; a human
runs it manually outside SCOS and pastes the result back.

Every function returns either the requested model or an
``OperatorExecutionError`` — invariants degrade to a structured error rather
than raising. All IDs are deterministic sha256 digests of caller-supplied
stable inputs. ``created_at`` / ``captured_at`` are caller-supplied strings;
there is no clock, no random, no uuid.
"""

from __future__ import annotations

import hashlib
from typing import Any

try:
    from .operator_execution_models import (
        ALLOWED_CAPTURE_VERDICTS,
        ALLOWED_RUNBOOK_TYPES,
        ALLOWED_SHELLS,
        CommandExecutionCapture,
        ExecutionSafetyCheck,
        ManualCommandRunbook,
        OperatorExecutionError,
        OperatorExecutionOutcome,
        RunbookCommandStep,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from operator_execution_models import (  # type: ignore[no-redef]
        ALLOWED_CAPTURE_VERDICTS,
        ALLOWED_RUNBOOK_TYPES,
        ALLOWED_SHELLS,
        CommandExecutionCapture,
        ExecutionSafetyCheck,
        ManualCommandRunbook,
        OperatorExecutionError,
        OperatorExecutionOutcome,
        RunbookCommandStep,
    )

OPERATOR_EXECUTION_RUNBOOK_SCHEMA_VERSION = 1

_ID_DIGEST_LENGTH = 16

_FORBIDDEN_URL_MARKERS = ("http://", "https://")

# Stage 5.9 secret-key markers (superset used to guard metadata early in the
# builder, before model construction).
_SECRET_KEY_MARKERS = (
    "api_key",
    "token",
    "secret",
    "password",
    "private_key",
    "access_key",
    "credential",
)

# Deterministic success / failure markers used by the outcome classifier.
# Kept intentionally small and documented; not tuned to any single format.
_SUCCESS_MARKERS = (
    "nothing to commit",
    "[main",
    "main -> main",
    "head == origin/main",
    "working tree clean",
)
_FAILURE_MARKERS = (
    "error:",
    "fatal:",
    "failed",
    "rejected",
    "permission denied",
)
_WARNING_MARKERS = (
    "warning:",
    "warning",
    "deprecated",
)


def _stable_digest(parts: tuple[Any, ...]) -> str:
    return hashlib.sha256(
        "|".join("" if part is None else str(part) for part in parts).encode("utf-8")
    ).hexdigest()[:_ID_DIGEST_LENGTH]


def _derive_runbook_id(*, runbook_type: str, task_id: str, created_at: str, seed: str) -> str:
    return f"rb-{_stable_digest((runbook_type, task_id, created_at, seed))}"


def _derive_step_id(*, runbook_seed: str, step_order: int, command: str) -> str:
    return f"rbs-{_stable_digest((runbook_seed, step_order, command))}"


def _derive_check_id(*, runbook_seed: str, title: str) -> str:
    return f"rbc-{_stable_digest((runbook_seed, title))}"


def _derive_capture_id(*, runbook_id: str, operator_reported_command: str, captured_at: str) -> str:
    return f"cap-{_stable_digest((runbook_id, operator_reported_command, captured_at))}"


def _derive_outcome_id(*, runbook_id: str, capture_id: str, created_at: str) -> str:
    return f"oeo-{_stable_digest((runbook_id, capture_id, created_at))}"


def _fail(
    error_kind: str,
    error_detail: str,
    failed_step: str,
    *,
    metadata: Any = None,
) -> OperatorExecutionError:
    return OperatorExecutionError.of(error_kind, error_detail, failed_step, metadata=metadata)


def _check_nonempty(field_name: str, value: Any, failed_step: str) -> OperatorExecutionError | None:
    if value is None or not str(value).strip():
        return _fail("empty_required_field", f"{field_name} must not be empty", failed_step)
    return None


def _check_no_url(field_name: str, value: str, failed_step: str) -> OperatorExecutionError | None:
    lowered = str(value).lower()
    for marker in _FORBIDDEN_URL_MARKERS:
        if marker in lowered:
            return _fail(
                "invalid_path",
                f"{field_name} must be a local path, not a URL (found {marker!r})",
                failed_step,
            )
    if "://" in lowered:
        return _fail("invalid_path", f"{field_name} must not look like a URL: {value!r}", failed_step)
    return None


def _check_metadata_secrets(metadata: Any, failed_step: str) -> OperatorExecutionError | None:
    if metadata is None:
        return None
    try:
        if hasattr(metadata, "items"):
            items = list(metadata.items())
        else:
            items = [tuple(pair) for pair in metadata]
    except (TypeError, ValueError):
        return _fail("unsafe_metadata", "metadata must be a mapping or (key, value) pairs", failed_step)
    for pair in items:
        if len(pair) != 2:
            return _fail("unsafe_metadata", "metadata entries must be (key, value)", failed_step)
        key = str(pair[0]).lower()
        for marker in _SECRET_KEY_MARKERS:
            if marker in key:
                return _fail(
                    "unsafe_metadata",
                    f"metadata must not contain secret-bearing keys (found {pair[0]!r})",
                    failed_step,
                )
    return None


def _normalize_commands(commands: Any) -> list[str] | None:
    if commands is None:
        return None
    if isinstance(commands, str):
        text = commands.strip()
        return [text] if text else []
    try:
        items = list(commands)
    except TypeError:
        return None
    normalized: list[str] = []
    for item in items:
        normalized.append(str(item))
    return normalized


# --------------------------------------------------------------------------
# Generic manual-command runbook
# --------------------------------------------------------------------------


def create_manual_command_runbook(
    *,
    session_id: str,
    task_id: str,
    title: str,
    objective: str,
    commands: Any,
    created_at: str,
    source_approval_id: str | None = None,
    source_commit_proposal_id: str | None = None,
    source_push_proposal_id: str | None = None,
    runbook_type: str = "general_manual_command",
    working_directory: str = ".",
    shell: str = "powershell",
    expected_outputs: Any = None,
    operator_notes: Any = None,
    metadata: Any = None,
) -> ManualCommandRunbook | OperatorExecutionError:
    stage = "create_manual_command_runbook"

    for check in (
        _check_nonempty("session_id", session_id, stage),
        _check_nonempty("task_id", task_id, stage),
        _check_nonempty("title", title, stage),
        _check_nonempty("created_at", created_at, stage),
        _check_nonempty("working_directory", working_directory, stage),
    ):
        if check is not None:
            return check

    if runbook_type not in ALLOWED_RUNBOOK_TYPES:
        return _fail(
            "invalid_runbook_type",
            f"runbook_type={runbook_type!r} is not one of {list(ALLOWED_RUNBOOK_TYPES)}",
            stage,
        )
    if shell not in ALLOWED_SHELLS:
        return _fail(
            "invalid_shell",
            f"shell={shell!r} is not one of {list(ALLOWED_SHELLS)}",
            stage,
        )

    url_error = _check_no_url("working_directory", working_directory, stage)
    if url_error is not None:
        return url_error

    metadata_error = _check_metadata_secrets(metadata, stage)
    if metadata_error is not None:
        return metadata_error

    normalized_commands = _normalize_commands(commands)
    if normalized_commands is None:
        return _fail(
            "invalid_collection_type",
            "commands must be a str or a sequence of str",
            stage,
        )
    if not normalized_commands:
        return _fail("empty_required_field", "commands must contain at least one command", stage)
    for command in normalized_commands:
        if not command.strip():
            return _fail("empty_required_field", "commands must not contain empty entries", stage)

    seed = "\n".join(normalized_commands)
    runbook_id = _derive_runbook_id(
        runbook_type=runbook_type, task_id=task_id, created_at=created_at, seed=seed
    )

    try:
        steps = tuple(
            RunbookCommandStep.of(
                _derive_step_id(runbook_seed=runbook_id, step_order=index, command=command),
                index,
                f"Step {index}",
                command,
                "unknown",
                shell=shell,
                working_directory=working_directory,
                expected_result_hint="Run manually and paste the exact output back into SCOS.",
                risk_level="medium",
            )
            for index, command in enumerate(normalized_commands, start=1)
        )
        checks = (
            _default_manual_safety_check(runbook_id),
        )
        command_summary = "; ".join(normalized_commands)
        runbook = ManualCommandRunbook.of(
            runbook_id,
            session_id,
            task_id,
            title,
            objective,
            command_summary,
            runbook_type,
            created_at,
            "ready_for_operator",
            source_approval_id=source_approval_id,
            source_commit_proposal_id=source_commit_proposal_id,
            source_push_proposal_id=source_push_proposal_id,
            safety_checks=checks,
            command_steps=steps,
            expected_outputs=expected_outputs,
            operator_notes=operator_notes,
            metadata=metadata,
        )
    except ValueError as exc:
        return _fail("contract_violation", str(exc), stage)
    return runbook


def _default_manual_safety_check(runbook_id: str) -> ExecutionSafetyCheck:
    title = "Confirm the operator approval exists for this command"
    return ExecutionSafetyCheck.of(
        _derive_check_id(runbook_seed=runbook_id, title=title),
        title,
        "SCOS does not execute this command. Confirm the command was approved "
        "before running it manually outside SCOS.",
        severity="critical",
        operator_instruction="Verify the Stage 5.8 approval record before copying any step.",
    )


# --------------------------------------------------------------------------
# Git commit runbook
# --------------------------------------------------------------------------

_COMMIT_SAFETY_TITLES = (
    ("Confirm branch is main", "critical", "Run `git status -sb` and confirm the branch is `main`."),
    (
        "Confirm working tree contains only expected Stage files",
        "error",
        "Compare `git status --short` against the approved file list; stop if anything unexpected appears.",
    ),
    (
        "Confirm staged files match the approved proposal",
        "error",
        "Run `git diff --cached --name-only` and match it against the approved staged paths.",
    ),
    (
        "Confirm commit message matches the approved proposal",
        "error",
        "Copy the commit message from the approved proposal verbatim; do not edit it.",
    ),
    (
        "Confirm tests were reviewed",
        "warning",
        "Confirm the Stage test evidence was reviewed and is green before committing.",
    ),
    (
        "Confirm operator approval exists",
        "critical",
        "Verify the Stage 5.8 commit approval decision is `approved`.",
    ),
    (
        "Confirm no push happens during the commit runbook",
        "critical",
        "This runbook commits only. Do NOT run `git push`; push is a separate approved runbook.",
    ),
)


def create_git_commit_runbook(
    *,
    session_id: str,
    task_id: str,
    commit_message: str,
    staged_paths: Any,
    created_at: str,
    source_approval_id: str | None = None,
    source_commit_proposal_id: str | None = None,
    working_directory: str = ".",
    metadata: Any = None,
) -> ManualCommandRunbook | OperatorExecutionError:
    stage = "create_git_commit_runbook"

    for check in (
        _check_nonempty("session_id", session_id, stage),
        _check_nonempty("task_id", task_id, stage),
        _check_nonempty("commit_message", commit_message, stage),
        _check_nonempty("created_at", created_at, stage),
        _check_nonempty("working_directory", working_directory, stage),
    ):
        if check is not None:
            return check

    if "\n" in commit_message:
        return _fail("validation_error", "commit_message must be a single line", stage)

    url_error = _check_no_url("working_directory", working_directory, stage)
    if url_error is not None:
        return url_error
    metadata_error = _check_metadata_secrets(metadata, stage)
    if metadata_error is not None:
        return metadata_error

    normalized_paths = _normalize_commands(staged_paths)
    if normalized_paths is None:
        return _fail("invalid_collection_type", "staged_paths must be a str or sequence of str", stage)
    if not normalized_paths:
        return _fail("empty_required_field", "staged_paths must contain at least one path", stage)
    for path in normalized_paths:
        if not path.strip():
            return _fail("empty_required_field", "staged_paths must not contain empty entries", stage)
        path_url_error = _check_no_url("staged_paths", path, stage)
        if path_url_error is not None:
            return path_url_error

    add_command = "git add " + " ".join(normalized_paths)
    quoted_message = commit_message.replace('"', '\\"')
    step_specs = (
        ("Inspect working tree", "git status --short --untracked-files=all", "git_status",
         "Shows every tracked/untracked change; confirm only approved files appear."),
        ("Stage the approved files", add_command, "git_add",
         "Stages exactly the approved paths; nothing else should be staged."),
        ("Review staged stat", "git diff --cached --stat", "git_diff",
         "Confirms the staged diff scope matches the approved proposal."),
        ("Review staged file list", "git diff --cached --name-only", "git_diff",
         "Lists staged files; must match the approved staged paths exactly."),
        ("Create the commit", f'git commit -m "{quoted_message}"', "git_commit",
         "Creates the local commit; expect a `[main <hash>]` summary line."),
        ("Confirm post-commit status", "git status -sb", "git_status",
         "Confirms the commit landed and the tree is clean; NO push happens here."),
    )

    seed = "commit|" + "|".join(normalized_paths) + "|" + commit_message
    runbook_id = _derive_runbook_id(
        runbook_type="commit_runbook", task_id=task_id, created_at=created_at, seed=seed
    )

    try:
        steps = tuple(
            RunbookCommandStep.of(
                _derive_step_id(runbook_seed=runbook_id, step_order=index, command=command),
                index,
                title,
                command,
                command_type,
                shell="powershell",
                working_directory=working_directory,
                expected_result_hint=hint,
                risk_level="high" if command_type == "git_commit" else "medium",
            )
            for index, (title, command, command_type, hint) in enumerate(step_specs, start=1)
        )
        checks = tuple(
            ExecutionSafetyCheck.of(
                _derive_check_id(runbook_seed=runbook_id, title=title),
                title,
                instruction,
                severity=severity,
                operator_instruction=instruction,
            )
            for title, severity, instruction in _COMMIT_SAFETY_TITLES
        )
        runbook = ManualCommandRunbook.of(
            runbook_id,
            session_id,
            task_id,
            "Manual git commit runbook",
            f"Commit the approved staged files with message {commit_message!r}.",
            f'{add_command}; git commit -m "{commit_message}"',
            "commit_runbook",
            created_at,
            "ready_for_operator",
            source_approval_id=source_approval_id,
            source_commit_proposal_id=source_commit_proposal_id,
            safety_checks=checks,
            command_steps=steps,
            expected_outputs=(
                "A `[main <hash>]` commit summary line",
                "`git status -sb` shows a clean tree on `main`",
            ),
            operator_notes=(
                "SCOS does not run these commands. Run them manually and paste the output back.",
                "Do NOT push in this runbook; push is a separate approved runbook.",
            ),
            metadata=metadata,
        )
    except ValueError as exc:
        return _fail("contract_violation", str(exc), stage)
    return runbook


# --------------------------------------------------------------------------
# Git push runbook
# --------------------------------------------------------------------------

_PUSH_SAFETY_TITLES = (
    ("Confirm commit exists locally", "critical",
     "Run `git rev-parse HEAD` and confirm the approved commit is present locally."),
    ("Confirm no remote-only commit exists", "error",
     "Run `git log --oneline --left-right main...origin/main` and confirm no remote-only commits."),
    ("Confirm branch is main", "critical", "Run `git status -sb` and confirm the branch is `main`."),
    ("Confirm HEAD state is understood", "warning",
     "Compare `git rev-parse HEAD` and `git rev-parse origin/main` before pushing."),
    ("Confirm push approval exists", "critical",
     "Verify the Stage 5.8 push approval decision is `approved` (separate from commit approval)."),
    ("Confirm no force push is used", "critical",
     "Use a plain `git push`; never add `--force` / `--force-with-lease`."),
    ("Confirm post-push verification will be run", "warning",
     "Plan to re-run fetch + status + rev-parse after the push to verify sync."),
)


def create_git_push_runbook(
    *,
    session_id: str,
    task_id: str,
    remote_name: str,
    branch_name: str,
    created_at: str,
    source_approval_id: str | None = None,
    source_push_proposal_id: str | None = None,
    working_directory: str = ".",
    metadata: Any = None,
) -> ManualCommandRunbook | OperatorExecutionError:
    stage = "create_git_push_runbook"

    for check in (
        _check_nonempty("session_id", session_id, stage),
        _check_nonempty("task_id", task_id, stage),
        _check_nonempty("remote_name", remote_name, stage),
        _check_nonempty("branch_name", branch_name, stage),
        _check_nonempty("created_at", created_at, stage),
        _check_nonempty("working_directory", working_directory, stage),
    ):
        if check is not None:
            return check

    url_error = _check_no_url("working_directory", working_directory, stage)
    if url_error is not None:
        return url_error
    metadata_error = _check_metadata_secrets(metadata, stage)
    if metadata_error is not None:
        return metadata_error

    push_command = f"git push {remote_name} {branch_name}"
    step_specs = (
        ("Fetch latest remote refs", "git fetch origin", "git_fetch",
         "Updates remote-tracking refs; no local changes."),
        ("Inspect status before push", "git status -sb", "git_status",
         "Confirm branch is `main` and the tree is clean."),
        ("Record local HEAD", "git rev-parse HEAD", "git_status",
         "Prints the local commit hash to be pushed."),
        ("Record remote HEAD", "git rev-parse origin/main", "git_status",
         "Prints the remote commit hash for comparison."),
        ("Compare local vs remote", "git log --oneline --left-right main...origin/main", "git_diff",
         "Shows divergence; confirm only local-ahead commits (`<`) exist."),
        ("Push the approved branch", push_command, "git_push",
         "Pushes the approved branch; expect a `main -> main` line. No force."),
        ("Re-fetch after push", "git fetch origin", "git_fetch",
         "Refreshes remote refs after the push."),
        ("Inspect status after push", "git status -sb", "git_status",
         "Confirm the branch is up to date with `origin/main`."),
        ("Record local HEAD after push", "git rev-parse HEAD", "git_status",
         "Prints the local commit hash after push."),
        ("Record remote HEAD after push", "git rev-parse origin/main", "git_status",
         "Should now equal the local HEAD (HEAD == origin/main)."),
        ("Review recent history", "git log --oneline -6", "git_status",
         "Confirms the pushed commit is at the top of history."),
    )

    seed = f"push|{remote_name}|{branch_name}"
    runbook_id = _derive_runbook_id(
        runbook_type="push_runbook", task_id=task_id, created_at=created_at, seed=seed
    )

    try:
        steps = tuple(
            RunbookCommandStep.of(
                _derive_step_id(runbook_seed=runbook_id, step_order=index, command=command),
                index,
                title,
                command,
                command_type,
                shell="powershell",
                working_directory=working_directory,
                expected_result_hint=hint,
                risk_level="critical" if command_type == "git_push" else "medium",
            )
            for index, (title, command, command_type, hint) in enumerate(step_specs, start=1)
        )
        checks = tuple(
            ExecutionSafetyCheck.of(
                _derive_check_id(runbook_seed=runbook_id, title=title),
                title,
                instruction,
                severity=severity,
                operator_instruction=instruction,
            )
            for title, severity, instruction in _PUSH_SAFETY_TITLES
        )
        runbook = ManualCommandRunbook.of(
            runbook_id,
            session_id,
            task_id,
            "Manual git push runbook",
            f"Push {branch_name!r} to {remote_name!r} after separate push approval.",
            push_command,
            "push_runbook",
            created_at,
            "ready_for_operator",
            source_approval_id=source_approval_id,
            source_push_proposal_id=source_push_proposal_id,
            safety_checks=checks,
            command_steps=steps,
            expected_outputs=(
                "A `main -> main` push confirmation line",
                "HEAD == origin/main after the push",
                "`git status -sb` shows the branch up to date",
            ),
            operator_notes=(
                "SCOS does not run these commands. Run them manually and paste the output back.",
                "Push approval is separate from commit approval; never force push.",
            ),
            metadata=metadata,
        )
    except ValueError as exc:
        return _fail("contract_violation", str(exc), stage)
    return runbook


# --------------------------------------------------------------------------
# Result capture
# --------------------------------------------------------------------------


def capture_manual_command_result(
    *,
    runbook: ManualCommandRunbook,
    operator_reported_command: str,
    pasted_output_summary: str,
    raw_output_excerpt: str,
    exit_status_text: str,
    captured_at: str,
    evidence_paths: Any = None,
    metadata: Any = None,
) -> CommandExecutionCapture | OperatorExecutionError:
    stage = "capture_manual_command_result"

    if not isinstance(runbook, ManualCommandRunbook):
        return _fail("contract_violation", "runbook must be a ManualCommandRunbook", stage)

    for check in (
        _check_nonempty("operator_reported_command", operator_reported_command, stage),
        _check_nonempty("captured_at", captured_at, stage),
    ):
        if check is not None:
            return check

    metadata_error = _check_metadata_secrets(metadata, stage)
    if metadata_error is not None:
        return metadata_error

    if evidence_paths is None:
        normalized_paths: list[str] = []
    else:
        normalized_paths = _normalize_commands(evidence_paths)  # type: ignore[assignment]
        if normalized_paths is None:
            return _fail(
                "invalid_collection_type",
                "evidence_paths must be a str or sequence of str",
                stage,
            )
    for path in normalized_paths:
        path_error = _check_no_url("evidence_paths", path, stage)
        if path_error is not None:
            return path_error

    verdict, warnings, blockers = _classify_verdict(
        pasted_output_summary=pasted_output_summary,
        raw_output_excerpt=raw_output_excerpt,
        exit_status_text=exit_status_text,
    )

    capture_id = _derive_capture_id(
        runbook_id=runbook.runbook_id,
        operator_reported_command=operator_reported_command,
        captured_at=captured_at,
    )

    try:
        capture = CommandExecutionCapture.of(
            capture_id,
            runbook.runbook_id,
            runbook.session_id,
            runbook.task_id,
            operator_reported_command,
            pasted_output_summary,
            raw_output_excerpt,
            exit_status_text,
            verdict,
            captured_at,
            evidence_paths=tuple(normalized_paths),
            warnings=warnings,
            blockers=blockers,
            metadata=metadata,
        )
    except ValueError as exc:
        return _fail("contract_violation", str(exc), stage)
    return capture


def _classify_verdict(
    *,
    pasted_output_summary: str,
    raw_output_excerpt: str,
    exit_status_text: str,
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    """Deterministic verdict from pasted output. Documented, simple rules."""

    blob = " ".join(
        (
            str(pasted_output_summary),
            str(raw_output_excerpt),
            str(exit_status_text),
        )
    ).lower()

    warnings: list[str] = []
    blockers: list[str] = []

    has_failure = any(marker in blob for marker in _FAILURE_MARKERS)
    has_success = any(marker in blob for marker in _SUCCESS_MARKERS)
    has_warning = any(marker in blob for marker in _WARNING_MARKERS)

    if "rejected" in blob or "permission denied" in blob:
        blockers.append("Output indicates the operation was rejected or blocked.")
    if has_warning:
        warnings.append("Output contains warning markers; review before proceeding.")

    if has_failure and not blockers:
        blockers.append("Output contains an error/failure marker.")

    if not str(pasted_output_summary).strip() and not str(raw_output_excerpt).strip():
        return "UNKNOWN", tuple(warnings), tuple(blockers)

    if blockers:
        # Distinguish an explicit block from a plain failure.
        if any("rejected" in b.lower() or "blocked" in b.lower() for b in blockers):
            return "BLOCKED", tuple(warnings), tuple(blockers)
        return "FAIL", tuple(warnings), tuple(blockers)

    if has_success:
        if warnings:
            return "PASS_WITH_WARNINGS", tuple(warnings), tuple(blockers)
        return "PASS", tuple(warnings), tuple(blockers)

    # Output present but no clear success/failure signal.
    return "NEEDS_REVIEW", tuple(warnings), tuple(blockers)


# --------------------------------------------------------------------------
# Outcome classification
# --------------------------------------------------------------------------

_VERDICT_TO_OUTCOME = {
    "PASS": ("command_succeeded", "record_result_and_update_chatgpt_status", "chatgpt", False),
    "PASS_WITH_WARNINGS": (
        "command_succeeded_with_warnings",
        "record_result_then_operator_review_warnings",
        "operator",
        True,
    ),
    "NEEDS_REVIEW": ("command_needs_review", "operator_manual_review_required", "operator", True),
    "NEEDS_FIX": ("command_needs_fix", "route_back_to_codex_for_fix", "codex", True),
    "BLOCKED": ("command_blocked", "route_back_to_review_blocked", "operator", True),
    "FAIL": ("command_failed", "route_back_to_codex_for_fix", "codex", True),
    "UNKNOWN": ("command_unknown", "operator_manual_review_required", "operator", True),
}


def classify_operator_execution_outcome(
    *,
    runbook: ManualCommandRunbook,
    capture: CommandExecutionCapture,
    created_at: str,
    metadata: Any = None,
) -> OperatorExecutionOutcome | OperatorExecutionError:
    stage = "classify_operator_execution_outcome"

    if not isinstance(runbook, ManualCommandRunbook):
        return _fail("contract_violation", "runbook must be a ManualCommandRunbook", stage)
    if not isinstance(capture, CommandExecutionCapture):
        return _fail("contract_violation", "capture must be a CommandExecutionCapture", stage)
    if capture.runbook_id != runbook.runbook_id:
        return _fail(
            "contract_violation",
            "capture.runbook_id must match runbook.runbook_id",
            stage,
        )

    nonempty = _check_nonempty("created_at", created_at, stage)
    if nonempty is not None:
        return nonempty
    metadata_error = _check_metadata_secrets(metadata, stage)
    if metadata_error is not None:
        return metadata_error

    if capture.verdict not in ALLOWED_CAPTURE_VERDICTS:
        return _fail(
            "invalid_verdict",
            f"capture.verdict={capture.verdict!r} is not recognized",
            stage,
        )

    outcome_kind, next_action, next_agent, review_required = _VERDICT_TO_OUTCOME[capture.verdict]

    # Any warning or blocker forces operator review regardless of the verdict.
    if capture.warnings or capture.blockers:
        review_required = True

    summary = (
        f"Runbook {runbook.runbook_id} classified as {capture.verdict} "
        f"({len(capture.warnings)} warning(s), {len(capture.blockers)} blocker(s))."
    )

    outcome_id = _derive_outcome_id(
        runbook_id=runbook.runbook_id, capture_id=capture.capture_id, created_at=created_at
    )

    try:
        outcome = OperatorExecutionOutcome.of(
            outcome_id,
            runbook.runbook_id,
            capture.capture_id,
            runbook.session_id,
            runbook.task_id,
            outcome_kind,
            summary,
            next_action,
            created_at,
            recommended_next_agent=next_agent,
            operator_review_required=review_required,
            metadata=metadata,
        )
    except ValueError as exc:
        return _fail("contract_violation", str(exc), stage)
    return outcome
