"""SCOS Stage 5.7 AI Result Intake & ChatGPT Status Update Loop builder.

Pure, side-effect-free functions that turn pasted/imported agent result text
into an ``AIResultIntakeRecord``, then derive a ``ChatGPTStatusUpdatePacket``
(a manual-handoff status update body — never sent anywhere by this module), a
``ProjectStateUpdate``, and a conservative ``NextActionDecision``.

This module NEVER executes AI, calls an API, automates a desktop app/browser,
touches a clipboard, opens a network connection, or auto-dispatches a
recommended action — every function here only ever produces data for a human
(or a later stage) to act on.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid.
"""

from __future__ import annotations

import hashlib
from typing import Any

try:
    from .result_intake_models import (
        AI_RESULT_INTAKE_SCHEMA_VERSION,
        AIResultIntakeError,
        AIResultIntakeRecord,
        ALLOWED_SOURCE_AGENTS,
        ChatGPTStatusUpdatePacket,
        NextActionDecision,
        ProjectStateUpdate,
        ResultIntakeArtifact,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from result_intake_models import (
        AI_RESULT_INTAKE_SCHEMA_VERSION,
        AIResultIntakeError,
        AIResultIntakeRecord,
        ALLOWED_SOURCE_AGENTS,
        ChatGPTStatusUpdatePacket,
        NextActionDecision,
        ProjectStateUpdate,
        ResultIntakeArtifact,
    )

RESULT_INTAKE_BUILDER_SCHEMA_VERSION = 1

_ID_DIGEST_LENGTH = 16
_MAX_NORMALIZED_SUMMARY_LENGTH = 2000

# Verdict keyword markers, checked in strict precedence order:
# BLOCKED > FAIL > NEEDS_FIX > PARTIAL > PASS. The first matching tier wins;
# unmatched but substantial text becomes NEEDS_REVIEW; near-empty/unreadable
# text becomes UNKNOWN.
_BLOCKED_MARKERS = (
    "blocked",
    "blocker:",
    "cannot proceed",
    "waiting on",
    "stuck on",
    "permission denied",
)
_FAIL_MARKERS = (
    "fail:",
    "failed",
    "failure",
    "error:",
    "exception",
    "broken",
    "verdict: fail",
)
_NEEDS_FIX_MARKERS = (
    "needs fix",
    "needs_fix",
    "fix required",
    "bug found",
    "issue found",
    "verdict: needs_fix",
)
_PARTIAL_MARKERS = (
    "partial",
    "partially",
    "some tests fail",
    "incomplete",
    "verdict: partial",
)
_PASS_MARKERS = (
    "pass:",
    "passed",
    "all tests pass",
    "success",
    "verdict: pass",
)

_MIN_ANALYZABLE_LENGTH = 3

_TESTS_SUMMARY_PREFIXES = ("tests:", "test summary:", "test results:")
_CHANGED_FILES_PREFIXES = ("changed files:", "files changed:", "changed_files:")
_BLOCKER_LINE_PREFIXES = ("blocker:", "blockers:")
_WARNING_LINE_PREFIXES = ("warning:", "warnings:")

# Verdicts that mean "operator review needed" even if the caller did not set
# operator_review_required explicitly.
_ALWAYS_REVIEW_VERDICTS = ("BLOCKED", "FAIL", "NEEDS_FIX", "NEEDS_REVIEW", "UNKNOWN")


def _fail(
    error_kind: str,
    error_detail: str,
    failed_step: str,
    *,
    intake_id: str | None = None,
    metadata: Any = None,
) -> AIResultIntakeError:
    return AIResultIntakeError.of(
        error_kind, error_detail, failed_step, intake_id=intake_id, metadata=metadata
    )


def _check_nonempty(field_name: str, value: Any) -> AIResultIntakeError | None:
    if value is None or not str(value).strip():
        return _fail(
            "empty_required_field", f"{field_name} must not be empty", field_name
        )
    return None


def _check_agent(field_name: str, value: Any) -> AIResultIntakeError | None:
    if value not in ALLOWED_SOURCE_AGENTS:
        return _fail(
            "invalid_source_agent",
            f"{field_name}={value!r} is not a recognized source agent",
            field_name,
        )
    return None


def _check_collection(field_name: str, value: Any) -> AIResultIntakeError | None:
    if value is not None and not isinstance(value, (tuple, list)):
        return _fail(
            "invalid_collection_type", f"{field_name} must be a tuple or list", field_name
        )
    return None


def _stable_digest(parts) -> str:
    return hashlib.sha256(
        "|".join("" if part is None else str(part) for part in parts).encode("utf-8")
    ).hexdigest()[:_ID_DIGEST_LENGTH]


def _derive_intake_id(
    *, session_id, task_id, source_agent, source_runtime_id, title, raw_result_text, created_at
) -> str:
    digest = _stable_digest(
        (session_id, task_id, source_agent, source_runtime_id, title, raw_result_text, created_at)
    )
    return f"ri-{digest}"


def _derive_update_packet_id(
    *, intake_id, target_runtime_id, requested_chatgpt_action, created_at
) -> str:
    digest = _stable_digest(
        (intake_id, target_runtime_id, requested_chatgpt_action, created_at)
    )
    return f"cgu-{digest}"


def _derive_state_update_id(
    *, intake_id, previous_stage, current_stage, updated_at
) -> str:
    digest = _stable_digest((intake_id, previous_stage, current_stage, updated_at))
    return f"psu-{digest}"


def _derive_next_action_id(*, intake_id, created_at) -> str:
    digest = _stable_digest((intake_id, created_at))
    return f"nad-{digest}"


def _normalize_summary(raw_text: str, max_len: int = _MAX_NORMALIZED_SUMMARY_LENGTH) -> str:
    collapsed = " ".join(raw_text.split())
    if len(collapsed) > max_len:
        return collapsed[:max_len].rstrip() + "..."
    return collapsed


def _extract_single_line_value(lines: list[str], prefixes: tuple[str, ...]) -> str:
    for line in lines:
        stripped = line.strip()
        lowered = stripped.lower()
        for prefix in prefixes:
            if lowered.startswith(prefix):
                return stripped[len(prefix):].strip(" :")
    return ""


def _extract_marked_lines(lines: list[str], prefixes: tuple[str, ...]) -> tuple[str, ...]:
    results: list[str] = []
    for line in lines:
        stripped = line.strip()
        lowered = stripped.lower()
        for prefix in prefixes:
            if lowered.startswith(prefix):
                content = stripped[len(prefix):].strip(" :")
                if content:
                    results.append(content)
                break
    return tuple(results)


def classify_verdict(raw_text: str) -> str:
    """Classify ``raw_text`` into an ``ALLOWED_VERDICTS`` value.

    Precedence: BLOCKED > FAIL > NEEDS_FIX > PARTIAL > PASS. Text with no
    recognizable marker but enough content to have been read becomes
    NEEDS_REVIEW. Near-empty/unreadable text becomes UNKNOWN.
    """
    stripped = raw_text.strip()
    if len(stripped) < _MIN_ANALYZABLE_LENGTH:
        return "UNKNOWN"
    lowered = stripped.lower()
    for marker in _BLOCKED_MARKERS:
        if marker in lowered:
            return "BLOCKED"
    for marker in _FAIL_MARKERS:
        if marker in lowered:
            return "FAIL"
    for marker in _NEEDS_FIX_MARKERS:
        if marker in lowered:
            return "NEEDS_FIX"
    for marker in _PARTIAL_MARKERS:
        if marker in lowered:
            return "PARTIAL"
    for marker in _PASS_MARKERS:
        if marker in lowered:
            return "PASS"
    return "NEEDS_REVIEW"


def _classify_confidence(raw_text: str, verdict: str) -> str:
    """Deterministic, conservative confidence heuristic.

    Longer, more structured text (multiple lines) yields higher confidence.
    Ambiguous verdicts (NEEDS_REVIEW, UNKNOWN) are always low confidence.
    """
    if verdict in ("NEEDS_REVIEW", "UNKNOWN"):
        return "low"
    line_count = len([line for line in raw_text.splitlines() if line.strip()])
    if line_count >= 4:
        return "high"
    if line_count >= 2:
        return "medium"
    return "low"


def build_result_intake_record(
    *,
    session_id: str,
    task_id: str,
    source_agent: str,
    source_runtime_id: str,
    raw_result_text: str,
    created_at: str,
    title: str,
    source_packet_id: str | None = None,
    source_result_packet_id: str | None = None,
    artifacts=None,
    metadata=None,
) -> AIResultIntakeRecord | AIResultIntakeError:
    for check in (
        _check_agent("source_agent", source_agent),
        _check_nonempty("session_id", session_id),
        _check_nonempty("task_id", task_id),
        _check_nonempty("source_runtime_id", source_runtime_id),
        _check_nonempty("raw_result_text", raw_result_text),
        _check_nonempty("created_at", created_at),
        _check_nonempty("title", title),
        _check_collection("artifacts", artifacts),
    ):
        if check is not None:
            return check

    resolved_artifacts = tuple(artifacts or ())
    for artifact in resolved_artifacts:
        if not isinstance(artifact, ResultIntakeArtifact):
            return _fail(
                "invalid_artifact_type",
                "artifacts entries must be ResultIntakeArtifact instances",
                "artifacts",
            )

    lines = raw_result_text.splitlines()
    verdict = classify_verdict(raw_result_text)
    confidence = _classify_confidence(raw_result_text, verdict)
    normalized_summary = _normalize_summary(raw_result_text)
    blockers = _extract_marked_lines(lines, _BLOCKER_LINE_PREFIXES)
    warnings = _extract_marked_lines(lines, _WARNING_LINE_PREFIXES)
    tests_summary = _extract_single_line_value(lines, _TESTS_SUMMARY_PREFIXES)
    changed_files_summary = _extract_single_line_value(lines, _CHANGED_FILES_PREFIXES)
    operator_review_required = verdict in _ALWAYS_REVIEW_VERDICTS or bool(blockers)

    intake_id = _derive_intake_id(
        session_id=session_id,
        task_id=task_id,
        source_agent=source_agent,
        source_runtime_id=source_runtime_id,
        title=title,
        raw_result_text=raw_result_text,
        created_at=created_at,
    )

    status = "review_required" if operator_review_required else "intake_recorded"

    try:
        return AIResultIntakeRecord.of(
            intake_id,
            session_id,
            task_id,
            source_agent,
            source_runtime_id,
            title,
            raw_result_text,
            normalized_summary,
            verdict,
            confidence,
            created_at,
            status,
            source_packet_id=source_packet_id,
            source_result_packet_id=source_result_packet_id,
            artifacts=resolved_artifacts,
            blockers=blockers,
            warnings=warnings,
            tests_summary=tests_summary,
            changed_files_summary=changed_files_summary,
            operator_review_required=operator_review_required,
            metadata=metadata,
        )
    except ValueError as exc:
        return _fail("contract_violation", str(exc), "AIResultIntakeRecord.of")


def _evidence_refs_from_intake(intake_record: AIResultIntakeRecord) -> tuple[str, ...]:
    refs: list[str] = []
    for artifact in intake_record.artifacts:
        refs.append(artifact.path or artifact.artifact_id)
    return tuple(refs)


def _compose_status_update_body(
    *,
    intake_record: AIResultIntakeRecord,
    requested_chatgpt_action: str,
    evidence_refs: tuple[str, ...],
) -> str:
    blockers_text = (
        "\n".join(f"- {item}" for item in intake_record.blockers)
        if intake_record.blockers
        else "None"
    )
    warnings_text = (
        "\n".join(f"- {item}" for item in intake_record.warnings)
        if intake_record.warnings
        else "None"
    )
    evidence_text = "\n".join(f"- {ref}" for ref in evidence_refs) if evidence_refs else "None"
    return (
        f"Session: {intake_record.session_id}\n"
        f"Task: {intake_record.task_id}\n"
        f"Source Agent: {intake_record.source_agent}\n"
        f"Verdict: {intake_record.verdict}\n"
        "\n"
        "Summary:\n"
        f"{intake_record.normalized_summary}\n"
        "\n"
        "Blockers:\n"
        f"{blockers_text}\n"
        "\n"
        "Warnings:\n"
        f"{warnings_text}\n"
        "\n"
        f"Tests: {intake_record.tests_summary or 'Not reported'}\n"
        f"Changed Files: {intake_record.changed_files_summary or 'Not reported'}\n"
        "\n"
        "Evidence:\n"
        f"{evidence_text}\n"
        "\n"
        f"Requested ChatGPT Action: {requested_chatgpt_action}\n"
        "\n"
        "Constraints:\n"
        "- Do not assume hidden files.\n"
        "- Do not claim work committed/pushed unless evidence says so.\n"
        "- Produce next action only from provided evidence."
    )


def build_chatgpt_status_update_packet(
    *,
    intake_record: AIResultIntakeRecord,
    target_runtime_id: str,
    created_at: str,
    requested_chatgpt_action: str,
    metadata=None,
) -> ChatGPTStatusUpdatePacket | AIResultIntakeError:
    if not isinstance(intake_record, AIResultIntakeRecord):
        return _fail(
            "contract_violation",
            "intake_record must be an AIResultIntakeRecord",
            "intake_record",
        )
    for check in (
        _check_nonempty("target_runtime_id", target_runtime_id),
        _check_nonempty("created_at", created_at),
        _check_nonempty("requested_chatgpt_action", requested_chatgpt_action),
    ):
        if check is not None:
            return check

    evidence_refs = _evidence_refs_from_intake(intake_record)
    status_update_body = _compose_status_update_body(
        intake_record=intake_record,
        requested_chatgpt_action=requested_chatgpt_action,
        evidence_refs=evidence_refs,
    )
    update_packet_id = _derive_update_packet_id(
        intake_id=intake_record.intake_id,
        target_runtime_id=target_runtime_id,
        requested_chatgpt_action=requested_chatgpt_action,
        created_at=created_at,
    )

    merged_metadata = list(metadata or ())
    merged_metadata.append(("source_agent", intake_record.source_agent))

    try:
        return ChatGPTStatusUpdatePacket.of(
            update_packet_id,
            intake_record.intake_id,
            intake_record.session_id,
            intake_record.task_id,
            target_runtime_id,
            intake_record.title,
            status_update_body,
            intake_record.verdict,
            intake_record.normalized_summary,
            requested_chatgpt_action,
            created_at,
            "ready_for_chatgpt_update",
            evidence_refs=evidence_refs,
            metadata=merged_metadata,
        )
    except ValueError as exc:
        return _fail(
            "contract_violation",
            str(exc),
            "ChatGPTStatusUpdatePacket.of",
            intake_id=intake_record.intake_id,
        )


def _metadata_flag(metadata: Any, key: str) -> bool:
    if metadata is None:
        return False
    if isinstance(metadata, dict):
        items = metadata.items()
    else:
        items = metadata
    for pair_key, pair_value in items:
        if pair_key == key:
            if isinstance(pair_value, bool):
                return pair_value
            return str(pair_value).strip().lower() == "true"
    return False


# verdict -> (task_status, stage_status), used when no override flag applies.
_VERDICT_STATE_MAP: dict[str, tuple[str, str]] = {
    "BLOCKED": ("blocked", "blocked"),
    "FAIL": ("needs_fix", "needs_review"),
    "NEEDS_FIX": ("needs_fix", "needs_review"),
    "NEEDS_REVIEW": ("review_required", "needs_review"),
    "PARTIAL": ("review_required", "needs_review"),
    "PASS": ("approved", "active"),
    "UNKNOWN": ("review_required", "needs_review"),
}


def build_project_state_update(
    *,
    intake_record: AIResultIntakeRecord,
    previous_stage: str,
    current_stage: str,
    updated_at: str,
    metadata=None,
) -> ProjectStateUpdate | AIResultIntakeError:
    if not isinstance(intake_record, AIResultIntakeRecord):
        return _fail(
            "contract_violation",
            "intake_record must be an AIResultIntakeRecord",
            "intake_record",
        )
    for check in (
        _check_nonempty("previous_stage", previous_stage),
        _check_nonempty("current_stage", current_stage),
        _check_nonempty("updated_at", updated_at),
    ):
        if check is not None:
            return check

    verdict = intake_record.verdict
    task_status, stage_status = _VERDICT_STATE_MAP.get(
        verdict, ("review_required", "needs_review")
    )

    ready_for_commit = _metadata_flag(metadata, "ready_for_commit")
    stage_complete = _metadata_flag(metadata, "stage_complete")

    if verdict == "PASS" and ready_for_commit:
        task_status = "ready_for_commit"
    if verdict == "PASS" and stage_complete:
        stage_status = "complete"

    state_update_id = _derive_state_update_id(
        intake_id=intake_record.intake_id,
        previous_stage=previous_stage,
        current_stage=current_stage,
        updated_at=updated_at,
    )
    summary = (
        f"{intake_record.source_agent} reported {verdict} for task "
        f"{intake_record.task_id} at stage {current_stage}."
    )

    try:
        return ProjectStateUpdate.of(
            state_update_id,
            intake_record.intake_id,
            intake_record.session_id,
            intake_record.task_id,
            previous_stage,
            current_stage,
            task_status,
            stage_status,
            intake_record.source_agent,
            verdict,
            summary,
            updated_at,
            evidence_refs=_evidence_refs_from_intake(intake_record),
            metadata=metadata,
        )
    except ValueError as exc:
        return _fail(
            "contract_violation",
            str(exc),
            "ProjectStateUpdate.of",
            intake_id=intake_record.intake_id,
        )


def build_next_action_decision(
    *,
    intake_record: AIResultIntakeRecord,
    created_at: str,
    target_runtime_id_map=None,
    metadata=None,
) -> NextActionDecision | AIResultIntakeError:
    if not isinstance(intake_record, AIResultIntakeRecord):
        return _fail(
            "contract_violation",
            "intake_record must be an AIResultIntakeRecord",
            "intake_record",
        )
    check = _check_nonempty("created_at", created_at)
    if check is not None:
        return check

    verdict = intake_record.verdict
    source_agent = intake_record.source_agent
    ready_for_commit = _metadata_flag(metadata, "ready_for_commit")
    stage_complete = _metadata_flag(metadata, "stage_complete")

    if verdict == "BLOCKED":
        recommended_action = "hold_blocked"
        target_agent = None
        reason = "Result is BLOCKED; no automatic routing until unblocked."
    elif ready_for_commit and verdict == "PASS":
        recommended_action = "prepare_commit_gate"
        target_agent = None
        reason = "Result is PASS and ready_for_commit flag is set."
    elif stage_complete and verdict == "PASS":
        recommended_action = "mark_stage_complete"
        target_agent = None
        reason = "Result is PASS and stage_complete flag is set."
    elif verdict in ("FAIL", "NEEDS_FIX") and source_agent in ("codex", "hermes"):
        recommended_action = "send_to_claude_fix"
        target_agent = "claude_code"
        reason = f"{source_agent} reported {verdict}; route to Claude Code for a fix."
    elif verdict in ("FAIL", "NEEDS_FIX") and source_agent == "claude_code":
        recommended_action = "request_operator_review"
        target_agent = None
        reason = (
            "claude_code reported "
            f"{verdict}; conservative default is operator review, not "
            "automatic re-routing."
        )
    elif verdict == "PASS" and source_agent == "claude_code":
        recommended_action = "send_to_codex_review"
        target_agent = "codex"
        reason = "claude_code reported PASS; route to Codex for review."
    elif verdict == "PASS" and source_agent == "codex":
        recommended_action = "send_to_hermes_audit"
        target_agent = "hermes"
        reason = "codex reported PASS; route to Hermes for audit."
    elif verdict == "PASS" and source_agent == "hermes":
        recommended_action = "send_to_chatgpt_status_update"
        target_agent = "chatgpt"
        reason = "hermes reported PASS; route to ChatGPT for a status update."
    elif verdict == "NEEDS_REVIEW":
        recommended_action = "request_operator_review"
        target_agent = None
        reason = "Result verdict is unclear (NEEDS_REVIEW); operator review required."
    else:
        recommended_action = "request_operator_review"
        target_agent = None
        reason = f"No specific routing rule for verdict={verdict!r}/agent={source_agent!r}."

    target_runtime_id = None
    if target_agent is not None and target_runtime_id_map:
        target_runtime_id = (
            target_runtime_id_map.get(target_agent)
            if isinstance(target_runtime_id_map, dict)
            else None
        )

    requires_operator_approval = recommended_action != "no_action"

    next_action_id = _derive_next_action_id(
        intake_id=intake_record.intake_id, created_at=created_at
    )

    try:
        return NextActionDecision.of(
            next_action_id,
            intake_record.intake_id,
            intake_record.session_id,
            intake_record.task_id,
            recommended_action,
            "normal" if verdict not in ("BLOCKED", "FAIL") else "high",
            reason,
            created_at,
            target_agent=target_agent,
            target_runtime_id=target_runtime_id,
            requires_operator_approval=requires_operator_approval,
            metadata=metadata,
        )
    except ValueError as exc:
        return _fail(
            "contract_violation",
            str(exc),
            "NextActionDecision.of",
            intake_id=intake_record.intake_id,
        )
