"""Stage 8G post-delivery support window, dispute/reopen control, and
commercial closure service; evidence recording only, no customer contact, no
outbound transport, no HVS execution, no invoice/payment mutation.

All domain logic loads canonical Stage 8F evidence (the post-delivery audit
closure) as the authoritative gating lineage, validates end-to-end lineage,
preserves exact reason codes, fails closed, and appends audit evidence. No
broad exception swallowing; no network; no HVS; no invoice/payment mutation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import hvs_post_delivery_support_models as M
from .hvs_post_delivery_support_store import (
    append_post_delivery_support_event,
    make_post_delivery_support_event,
    post_delivery_support_path,
    read_post_delivery_support_events,
)
from .hvs_revision_store import revision_audit_path


# --- Canonical 8B revision-audit approval marker ----------------------------
# Reused read-only to enforce "Stage 8C cannot bypass Stage 8B approval".
EVT_REVISION_APPROVAL_RECORDED = "REVISION_APPROVAL_RECORDED"
EVT_RERENDER_AUTHORIZATION_CREATED = "RERENDER_AUTHORIZATION_CREATED"


@dataclass
class SupportServiceResult:
    ok: bool
    policy: Any = None
    issue: Any = None
    classification: Any = None
    dispute: Any = None
    reopen: Any = None
    closure: Any = None
    duplicate_of: str | None = None
    existing_id: str | None = None
    error_code: str | None = None
    error_detail: str | None = None
    reasons: tuple[str, ...] = ()
    hvs_invoked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "policy_id": self.policy.support_policy_id if self.policy else None,
            "issue_id": self.issue.issue_id if self.issue else None,
            "classification_id": self.classification.classification_id if self.classification else None,
            "dispute_id": self.dispute.dispute_id if self.dispute else None,
            "reopen_id": self.reopen.reopen_id if self.reopen else None,
            "commercial_closure_id": self.closure.commercial_closure_id if self.closure else None,
            "duplicate_of": self.duplicate_of,
            "existing_id": self.existing_id,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
            "reasons": list(self.reasons),
            "hvs_invoked": self.hvs_invoked,
        }


def _deny(*, code: str, detail: str) -> SupportServiceResult:
    return SupportServiceResult(False, error_code=code, error_detail=detail)


# --- 8F evidence loaders (reuse Stage 8F service internals) -----------------
def _load_8f_audit(repo_root: Path, *, authorization_id: str):
    from .hvs_manual_release_receipt_service import evaluate_post_delivery_audit

    out = evaluate_post_delivery_audit(
        authorization_id=authorization_id, operator_id="system",
        repo_root=repo_root, recorded_at="t",
    )
    return out


def _load_8f_release(repo_root: Path, release_execution_id: str):
    from .hvs_manual_release_receipt_service import _release_by_id

    return _release_by_id(repo_root=repo_root, release_id=release_execution_id)


def _load_8f_receipt(repo_root: Path, release_execution_id: str, receipt_confirmation_id: str):
    from .hvs_manual_release_receipt_service import _receipts_by_release

    receipts = _receipts_by_release(repo_root=repo_root)
    rec = receipts.get(release_execution_id)
    if rec is None or rec.receipt_id != receipt_confirmation_id:
        return None
    return rec


def _stage8b_approval_exists(repo_root: Path, revision_id: str) -> bool:
    """Read-only check: a Stage 8B approval already exists for this revision.

    Used to forbid routing directly to Stage 8C unless the required Stage 8B
    approval and lineage prerequisites already exist.
    """
    path = revision_audit_path(Path(repo_root))
    if not path.is_file():
        return False
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except (ValueError, json.JSONDecodeError):
            continue
        if ev.get("event_type") in (EVT_REVISION_APPROVAL_RECORDED, EVT_RERENDER_AUTHORIZATION_CREATED):
            if ev.get("revision_id") == revision_id or ev.get("subject_id") == revision_id:
                return True
    return False


# --- 8G store index helpers --------------------------------------------------
def _policies_by_id(repo_root: Path) -> dict[str, M.PostDeliverySupportPolicy]:
    out: dict[str, M.PostDeliverySupportPolicy] = {}
    for e in read_post_delivery_support_events(audit_log_path=post_delivery_support_path(repo_root)):
        if e.event_type in (M.EVT_SUPPORT_POLICY_REGISTERED, M.EVT_SUPPORT_POLICY_SUPERSEDED):
            rec = M.PostDeliverySupportPolicy(**e.record)
            out[rec.support_policy_id] = rec
    return out


def _issues_by_id(repo_root: Path) -> dict[str, M.PostDeliveryIssue]:
    out: dict[str, M.PostDeliveryIssue] = {}
    for e in read_post_delivery_support_events(audit_log_path=post_delivery_support_path(repo_root)):
        if e.event_type in (M.EVT_ISSUE_RECORDED,):
            rec = M.PostDeliveryIssue(**e.record)
            out[rec.issue_id] = rec
    return out


def _classifications_by_issue(repo_root: Path) -> dict[str, M.PostDeliveryIssueClassification]:
    out: dict[str, M.PostDeliveryIssueClassification] = {}
    for e in read_post_delivery_support_events(audit_log_path=post_delivery_support_path(repo_root)):
        if e.event_type == M.EVT_ISSUE_CLASSIFIED:
            rec = M.PostDeliveryIssueClassification(**e.record)
            out[rec.issue_id] = rec
    return out


def _disputes_by_issue(repo_root: Path) -> dict[str, list[M.PostDeliveryDispute]]:
    out: dict[str, list[M.PostDeliveryDispute]] = {}
    for e in read_post_delivery_support_events(audit_log_path=post_delivery_support_path(repo_root)):
        if e.event_type in (M.EVT_DISPUTE_OPENED, M.EVT_DISPUTE_RESOLVED):
            rec = M.PostDeliveryDispute(**e.record)
            out.setdefault(rec.issue_id, []).append(rec)
    return out


def _reopens_by_issue(repo_root: Path) -> dict[str, list[M.PostDeliveryReopen]]:
    out: dict[str, list[M.PostDeliveryReopen]] = {}
    for e in read_post_delivery_support_events(audit_log_path=post_delivery_support_path(repo_root)):
        if e.event_type in (M.EVT_REOPEN_REQUESTED, M.EVT_REOPEN_APPROVED, M.EVT_REOPEN_REJECTED):
            rec = M.PostDeliveryReopen(**e.record)
            out.setdefault(rec.issue_id, []).append(rec)
    return out


def _closures_by_project(repo_root: Path) -> dict[str, list[M.PostDeliveryCommercialClosure]]:
    out: dict[str, list[M.PostDeliveryCommercialClosure]] = {}
    for e in read_post_delivery_support_events(audit_log_path=post_delivery_support_path(repo_root)):
        if e.event_type == M.EVT_COMMERCIAL_CLOSURE_RECORDED:
            rec = M.PostDeliveryCommercialClosure(**e.record)
            out.setdefault(rec.project_id, []).append(rec)
    return out


# --- A. support-policy registration -----------------------------------------
def register_post_delivery_support_policy(
    *,
    authorization_id: str,
    support_window_start: str,
    support_window_end: str,
    policy_type: str,
    included_issue_categories: tuple[str, ...],
    excluded_issue_categories: tuple[str, ...],
    created_by_operator_id: str,
    policy_version: str,
    revision_allowance_reference: str | None = None,
    commercial_terms_reference: str | None = None,
    evidence_references: tuple[str, ...] = (),
    operator_id: str | None = None,
    repo_root: Any = None,
    recorded_at: str = "t",
) -> SupportServiceResult:
    repo_root = Path(repo_root)
    op = operator_id or created_by_operator_id
    # Stage 8F closure must exist and be ready/closed.
    audit = _load_8f_audit(repo_root, authorization_id=authorization_id)
    if not audit.ok or audit.audit is None or not audit.audit.audit_ready:
        return _deny(code="POST_DELIVERY_AUDIT_NOT_READY",
                     detail="Stage 8F post-delivery audit is not closed")
    closure = audit.audit
    release = _load_8f_release(repo_root, closure.release_id)
    if release is None:
        return _deny(code="RELEASE_NOT_FOUND", detail="referenced manual release missing")
    receipt = _load_8f_receipt(repo_root, closure.release_id, closure.receipt_id)
    if receipt is None:
        return _deny(code="RECEIPT_NOT_FOUND", detail="referenced customer receipt missing")

    policy_id = M.build_support_policy_id(
        project_id=closure.project_id,
        revised_delivery_id=closure.revised_delivery_id,
        release_execution_id=closure.release_id,
        receipt_confirmation_id=closure.receipt_id,
        post_delivery_closure_id=closure.audit_id,
        support_window_start=support_window_start,
        support_window_end=support_window_end,
        policy_type=policy_type,
        policy_version=policy_version,
    )
    existing = _policies_by_id(repo_root).get(policy_id)
    if existing is not None:
        if (existing.support_window_start == support_window_start
                and existing.support_window_end == support_window_end
                and existing.policy_type == policy_type
                and existing.policy_version == policy_version
                and set(existing.included_issue_categories) == set(included_issue_categories)
                and set(existing.excluded_issue_categories) == set(excluded_issue_categories)):
            return SupportServiceResult(True, policy=existing, duplicate_of=existing.support_policy_id)
        return _deny(code="CONFLICTING_SUPPORT_POLICY",
                     detail="a conflicting support policy already exists for this delivery")

    idempotency_key = M.build_support_policy_id(
        project_id=closure.project_id, revised_delivery_id=closure.revised_delivery_id,
        release_execution_id=closure.release_id, receipt_confirmation_id=closure.receipt_id,
        post_delivery_closure_id=closure.audit_id, support_window_start=support_window_start,
        support_window_end=support_window_end, policy_type=policy_type, policy_version=policy_version,
    )
    try:
        policy = M.PostDeliverySupportPolicy(
            schema_version=M.POST_DELIVERY_SUPPORT_SCHEMA_VERSION,
            support_policy_id=policy_id,
            project_id=closure.project_id,
            revision_id=closure.revision_id,
            revised_delivery_id=closure.revised_delivery_id,
            original_delivery_id=closure.original_delivery_id,
            release_execution_id=closure.release_id,
            receipt_confirmation_id=closure.receipt_id,
            post_delivery_closure_id=closure.audit_id,
            support_window_start=support_window_start,
            support_window_end=support_window_end,
            policy_type=policy_type,
            included_issue_categories=tuple(included_issue_categories),
            excluded_issue_categories=tuple(excluded_issue_categories),
            revision_allowance_reference=revision_allowance_reference,
            commercial_terms_reference=commercial_terms_reference,
            policy_version=policy_version,
            created_by_operator_id=created_by_operator_id,
            evidence_references=tuple(evidence_references),
            status=M.SUPPORT_POLICY_ACTIVE,
            idempotency_key=idempotency_key,
            created_at=recorded_at,
        )
    except ValueError as exc:
        return _deny(code="SUPPORT_POLICY_VALIDATION", detail=str(exc))

    event = make_post_delivery_support_event(
        event_type=M.EVT_SUPPORT_POLICY_REGISTERED,
        subject_id=policy_id,
        operator_id=op,
        recorded_at=recorded_at,
        record=policy.to_dict(),
    )
    append_post_delivery_support_event(audit_log_path=post_delivery_support_path(repo_root), event=event)
    return SupportServiceResult(True, policy=policy)


# --- B. issue intake --------------------------------------------------------
def record_post_delivery_issue(
    *,
    support_policy_id: str,
    issue_category: str,
    issue_summary: str,
    recorded_by_operator_id: str,
    customer_reference: str,
    affected_formats: tuple[str, ...],
    reported_at: str,
    issue_details: str = "",
    affected_artifact_references: tuple[str, ...] = (),
    artifact_sha256: str = "",
    requested_resolution: str = "",
    evidence_references: tuple[str, ...] = (),
    operator_id: str | None = None,
    repo_root: Any = None,
    recorded_at: str = "t",
) -> SupportServiceResult:
    repo_root = Path(repo_root)
    op = operator_id or recorded_by_operator_id
    policies = _policies_by_id(repo_root)
    policy = policies.get(support_policy_id)
    if policy is None:
        return _deny(code="SUPPORT_POLICY_NOT_FOUND", detail="referenced support policy missing")
    if policy.status in (M.SUPPORT_POLICY_CANCELLED, M.SUPPORT_POLICY_SUPERSEDED):
        return _deny(code="SUPPORT_POLICY_INACTIVE", detail="support policy is not active")

    issue_id = M.build_issue_id(
        support_policy_id=support_policy_id,
        project_id=policy.project_id,
        revised_delivery_id=policy.revised_delivery_id,
        issue_category=issue_category,
        customer_reference=customer_reference,
        issue_summary=issue_summary,
    )
    existing = _issues_by_id(repo_root).get(issue_id)
    if existing is not None:
        if (existing.issue_category == issue_category
                and existing.customer_reference == customer_reference
                and existing.issue_summary == issue_summary
                and set(existing.affected_formats) == set(affected_formats)):
            return SupportServiceResult(True, issue=existing, duplicate_of=existing.issue_id)
        return _deny(code="CONFLICTING_ISSUE", detail="a conflicting issue already exists")

    idempotency_key = issue_id
    try:
        issue = M.PostDeliveryIssue(
            schema_version=M.POST_DELIVERY_SUPPORT_SCHEMA_VERSION,
            issue_id=issue_id,
            support_policy_id=support_policy_id,
            project_id=policy.project_id,
            revision_id=policy.revision_id,
            revised_delivery_id=policy.revised_delivery_id,
            original_delivery_id=policy.original_delivery_id,
            release_execution_id=policy.release_execution_id,
            receipt_confirmation_id=policy.receipt_confirmation_id,
            post_delivery_closure_id=policy.post_delivery_closure_id,
            customer_reference=customer_reference,
            recorded_by_operator_id=recorded_by_operator_id,
            issue_category=issue_category,
            issue_summary=issue_summary,
            issue_details=issue_details,
            affected_formats=tuple(affected_formats),
            affected_artifact_references=tuple(affected_artifact_references),
            artifact_sha256=artifact_sha256,
            reported_at=reported_at,
            evidence_references=tuple(evidence_references),
            requested_resolution=requested_resolution,
            status=M.ISSUE_OPEN,
            idempotency_key=idempotency_key,
            created_at=recorded_at,
        )
    except ValueError as exc:
        return _deny(code="ISSUE_VALIDATION", detail=str(exc))

    event = make_post_delivery_support_event(
        event_type=M.EVT_ISSUE_RECORDED,
        subject_id=issue_id,
        operator_id=op,
        recorded_at=recorded_at,
        record=issue.to_dict(),
    )
    append_post_delivery_support_event(audit_log_path=post_delivery_support_path(repo_root), event=event)
    return SupportServiceResult(True, issue=issue)


# --- C. issue classification (deterministic, fail-closed) --------------------
def classify_post_delivery_issue(
    *,
    issue_id: str,
    classified_by_operator_id: str,
    operator_id: str | None = None,
    repo_root: Any = None,
    recorded_at: str = "t",
) -> SupportServiceResult:
    repo_root = Path(repo_root)
    op = operator_id or classified_by_operator_id
    issues = _issues_by_id(repo_root)
    issue = issues.get(issue_id)
    if issue is None:
        return _deny(code="ISSUE_NOT_FOUND", detail="referenced issue missing")
    if issue.status in (M.ISSUE_REJECTED, M.ISSUE_CANCELLED, M.ISSUE_RESOLVED):
        return _deny(code="ISSUE_TERMINAL", detail="issue is in a terminal state")

    policy = _policies_by_id(repo_root).get(issue.support_policy_id)
    if policy is None:
        return _deny(code="SUPPORT_POLICY_NOT_FOUND", detail="issue policy missing")
    # Lineage integrity.
    if policy.project_id != issue.project_id or policy.revised_delivery_id != issue.revised_delivery_id:
        return SupportServiceResult(
            True, issue=issue,
            classification=_emit_classification(
                repo_root=repo_root, issue=issue, outcome=M.CLASS_BLOCKED_INVALID_LINEAGE,
                reason_codes=("LINEAGE_MISMATCH",), target_workflow=None, op=op, recorded_at=recorded_at,
            ),
        )

    window_active = policy.status == M.SUPPORT_POLICY_ACTIVE and policy.support_window_start <= recorded_at <= policy.support_window_end
    cat = issue.issue_category

    # Integrity defect requires a bound artifact sha256 (no forged/empty).
    if cat == M.ISSUE_ARTIFACT_INTEGRITY_DEFECT and not issue.artifact_sha256:
        return SupportServiceResult(
            True, issue=issue,
            classification=_emit_classification(
                repo_root=repo_root, issue=issue, outcome=M.CLASS_BLOCKED_INVALID_LINEAGE,
                reason_codes=("MISSING_ARTIFACT_EVIDENCE",), target_workflow=None, op=op, recorded_at=recorded_at,
            ),
        )

    reasons: list[str] = []
    if cat == M.ISSUE_DISPUTE:
        outcome = M.CLASS_DISPUTE_REVIEW_REQUIRED
        target = None
        reasons.append("DISPUTE_ROUTED_TO_REVIEW")
    elif cat in M.COVERED_DEFECT_CATEGORIES:
        if not window_active or cat in policy.excluded_issue_categories:
            outcome = M.CLASS_OUT_OF_SCOPE_CHANGE
            target = M.REOPEN_TARGET_COMMERCIAL_REVIEW
            reasons.append("COVERAGE_EXPIRED_OR_EXCLUDED")
        else:
            outcome = M.CLASS_COVERED_DEFECT
            target = M.REOPEN_TARGET_STAGE_8C
            reasons.append("COVERED_DEFECT_ROUTED_TO_RERENDER")
    elif cat in M.REVISION_FOLLOWUP_CATEGORIES:
        outcome = M.CLASS_COVERED_REVISION
        target = M.REOPEN_TARGET_STAGE_8B
        reasons.append("REVISION_FOLLOWUP_ROUTED_TO_STAGE_8B")
    elif cat == M.ISSUE_SCOPE_CHANGE:
        outcome = M.CLASS_OUT_OF_SCOPE_CHANGE
        target = M.REOPEN_TARGET_COMMERCIAL_REVIEW
        reasons.append("SCOPE_CHANGE_COMMERCIAL_REVIEW")
    elif cat == M.ISSUE_SUPPORT_QUESTION:
        outcome = M.CLASS_SUPPORT_ONLY
        target = M.REOPEN_TARGET_SUPPORT_RESPONSE
        reasons.append("SUPPORT_QUESTION")
    elif cat == M.ISSUE_UNSUPPORTED_REQUEST:
        outcome = M.CLASS_REJECTED_UNSUPPORTED
        target = M.REOPEN_TARGET_NO_REOPEN
        reasons.append("UNSUPPORTED_REQUEST")
    else:
        # Unknown category already rejected at intake; defensive fail-closed.
        return _deny(code="CLASSIFICATION_VALIDATION", detail=f"unknown category {cat!r}")

    classification = _emit_classification(
        repo_root=repo_root, issue=issue, outcome=outcome,
        reason_codes=tuple(reasons), target_workflow=target, op=op, recorded_at=recorded_at,
    )
    return SupportServiceResult(True, issue=issue, classification=classification)


def _emit_classification(*, repo_root, issue, outcome, reason_codes, target_workflow, op, recorded_at):
    classification_id = M.build_classification_id(issue_id=issue.issue_id, classification=outcome)
    existing = _classifications_by_issue(repo_root).get(issue.issue_id)
    if existing is not None:
        if existing.outcome == outcome and set(existing.reason_codes) == set(reason_codes):
            return existing
        # Conflicting classification under same issue -> keep original, reject new.
        raise ValueError("conflicting classification already exists for issue")
    cls = M.PostDeliveryIssueClassification(
        schema_version=M.POST_DELIVERY_SUPPORT_SCHEMA_VERSION,
        classification_id=classification_id,
        issue_id=issue.issue_id,
        project_id=issue.project_id,
        revision_id=issue.revision_id,
        revised_delivery_id=issue.revised_delivery_id,
        outcome=outcome,
        reason_codes=tuple(reason_codes),
        target_workflow=target_workflow,
        classified_by_operator_id=op,
        idempotency_key=classification_id,
        created_at=recorded_at,
    )
    event = make_post_delivery_support_event(
        event_type=M.EVT_ISSUE_CLASSIFIED,
        subject_id=classification_id,
        operator_id=op,
        recorded_at=recorded_at,
        record=cls.to_dict(),
    )
    append_post_delivery_support_event(audit_log_path=post_delivery_support_path(repo_root), event=event)
    return cls


# --- D. dispute open / resolve ----------------------------------------------
def open_post_delivery_dispute(
    *,
    issue_id: str,
    dispute_type: str,
    dispute_reason: str,
    opened_by_operator_id: str,
    disputed_artifact_references: tuple[str, ...] = (),
    artifact_sha256: str = "",
    evidence_references: tuple[str, ...] = (),
    operator_id: str | None = None,
    repo_root: Any = None,
    recorded_at: str = "t",
) -> SupportServiceResult:
    repo_root = Path(repo_root)
    op = operator_id or opened_by_operator_id
    issue = _issues_by_id(repo_root).get(issue_id)
    if issue is None:
        return _deny(code="ISSUE_NOT_FOUND", detail="referenced issue missing")

    dispute_id = M.build_dispute_id(
        issue_id=issue_id, dispute_type=dispute_type, dispute_reason=dispute_reason)
    # Reuse 8F closure lineage for binding.
    existing_disputes = _disputes_by_issue(repo_root).get(issue_id, [])
    for d in existing_disputes:
        if d.dispute_id == dispute_id:
            return SupportServiceResult(True, dispute=d, duplicate_of=d.dispute_id)

    try:
        dispute = M.PostDeliveryDispute(
            schema_version=M.POST_DELIVERY_SUPPORT_SCHEMA_VERSION,
            dispute_id=dispute_id,
            issue_id=issue_id,
            project_id=issue.project_id,
            revised_delivery_id=issue.revised_delivery_id,
            release_execution_id=issue.release_execution_id,
            receipt_confirmation_id=issue.receipt_confirmation_id,
            post_delivery_closure_id=issue.post_delivery_closure_id,
            dispute_type=dispute_type,
            dispute_reason=dispute_reason,
            disputed_artifact_references=tuple(disputed_artifact_references),
            artifact_sha256=artifact_sha256,
            opened_by_operator_id=opened_by_operator_id,
            opened_at=recorded_at,
            status=M.DISPUTE_OPEN,
            resolution_reference=None,
            resolved_by_operator_id=None,
            resolution_reason=None,
            evidence_references=tuple(evidence_references),
            idempotency_key=dispute_id,
            created_at=recorded_at,
        )
    except ValueError as exc:
        return _deny(code="DISPUTE_VALIDATION", detail=str(exc))

    event = make_post_delivery_support_event(
        event_type=M.EVT_DISPUTE_OPENED,
        subject_id=dispute_id,
        operator_id=op,
        recorded_at=recorded_at,
        record=dispute.to_dict(),
    )
    append_post_delivery_support_event(audit_log_path=post_delivery_support_path(repo_root), event=event)
    return SupportServiceResult(True, dispute=dispute)


def resolve_post_delivery_dispute(
    *,
    dispute_id: str,
    resolution_status: str,
    resolved_by_operator_id: str,
    resolution_reason: str,
    resolution_reference: str | None = None,
    operator_id: str | None = None,
    repo_root: Any = None,
    recorded_at: str = "t",
) -> SupportServiceResult:
    repo_root = Path(repo_root)
    op = operator_id or resolved_by_operator_id
    all_disputes: dict[str, M.PostDeliveryDispute] = {}
    for lst in _disputes_by_issue(repo_root).values():
        for d in lst:
            all_disputes[d.dispute_id] = d
    dispute = all_disputes.get(dispute_id)
    if dispute is None:
        return _deny(code="DISPUTE_NOT_FOUND", detail="referenced dispute missing")
    if dispute.status in M.DISPUTE_TERMINAL_STATUSES:
        return _deny(code="DISPUTE_TERMINAL", detail="dispute is in a terminal state")
    if not resolved_by_operator_id:
        return _deny(code="DISPUTE_RESOLUTION_REQUIRES_OPERATOR", detail="operator identity required")
    if resolution_status not in M.ALLOWED_DISPUTE_STATUSES or resolution_status == M.DISPUTE_OPEN:
        return _deny(code="DISPUTE_INVALID_STATUS", detail="invalid resolution status")
    try:
        resolved = M.PostDeliveryDispute(
            schema_version=dispute.schema_version,
            dispute_id=dispute.dispute_id,
            issue_id=dispute.issue_id,
            project_id=dispute.project_id,
            revised_delivery_id=dispute.revised_delivery_id,
            release_execution_id=dispute.release_execution_id,
            receipt_confirmation_id=dispute.receipt_confirmation_id,
            post_delivery_closure_id=dispute.post_delivery_closure_id,
            dispute_type=dispute.dispute_type,
            dispute_reason=dispute.dispute_reason,
            disputed_artifact_references=dispute.disputed_artifact_references,
            artifact_sha256=dispute.artifact_sha256,
            opened_by_operator_id=dispute.opened_by_operator_id,
            opened_at=dispute.opened_at,
            status=resolution_status,
            resolution_reference=resolution_reference,
            resolved_by_operator_id=resolved_by_operator_id,
            resolution_reason=resolution_reason,
            evidence_references=dispute.evidence_references,
            idempotency_key=dispute.idempotency_key,
            created_at=dispute.created_at,
        )
    except ValueError as exc:
        return _deny(code="DISPUTE_VALIDATION", detail=str(exc))

    event = make_post_delivery_support_event(
        event_type=M.EVT_DISPUTE_RESOLVED,
        subject_id=dispute_id,
        operator_id=op,
        recorded_at=recorded_at,
        record=resolved.to_dict(),
    )
    append_post_delivery_support_event(audit_log_path=post_delivery_support_path(repo_root), event=event)
    return SupportServiceResult(True, dispute=resolved)


# --- E. reopen request / approval -------------------------------------------
def request_post_delivery_reopen(
    *,
    issue_id: str,
    target_workflow: str,
    reopen_reason: str,
    reopen_scope: str,
    operator_id: str | None = None,
    repo_root: Any = None,
    recorded_at: str = "t",
) -> SupportServiceResult:
    repo_root = Path(repo_root)
    issue = _issues_by_id(repo_root).get(issue_id)
    if issue is None:
        return _deny(code="ISSUE_NOT_FOUND", detail="referenced issue missing")
    if target_workflow not in M.ALLOWED_REOPEN_TARGETS:
        return _deny(code="REOPEN_TARGET_INVALID", detail="target workflow not allowed")
    # Stage 8C cannot bypass Stage 8B approval prerequisites.
    if target_workflow == M.REOPEN_TARGET_STAGE_8C:
        if not _stage8b_approval_exists(repo_root, issue.revision_id):
            return _deny(code="STAGE_8B_PREREQUISITES_MISSING",
                         detail="cannot route to Stage 8C without Stage 8B approval")
    reopen_id = M.build_reopen_id(
        issue_id=issue_id,
        prior_post_delivery_closure_id=issue.post_delivery_closure_id,
        target_workflow=target_workflow,
        reopen_reason=reopen_reason,
        approval_reference="",
    )
    for lst in _reopens_by_issue(repo_root).get(issue_id, []):
        if lst.reopen_id == reopen_id:
            return SupportServiceResult(True, reopen=lst, duplicate_of=lst.reopen_id)
    try:
        reopen = M.PostDeliveryReopen(
            schema_version=M.POST_DELIVERY_SUPPORT_SCHEMA_VERSION,
            reopen_id=reopen_id,
            issue_id=issue_id,
            dispute_id=None,
            prior_post_delivery_closure_id=issue.post_delivery_closure_id,
            revision_id=issue.revision_id,
            revised_delivery_id=issue.revised_delivery_id,
            project_id=issue.project_id,
            correlation_id=None,
            reopen_reason=reopen_reason,
            reopen_scope=reopen_scope,
            target_workflow=target_workflow,
            approved_by_operator_id="",
            approval_reference="",
            approved_at="",
            status=M.REOPEN_REQUESTED,
            idempotency_key=reopen_id,
            evidence_references=(),
            created_at=recorded_at,
        )
    except ValueError as exc:
        return _deny(code="REOPEN_VALIDATION", detail=str(exc))
    event = make_post_delivery_support_event(
        event_type=M.EVT_REOPEN_REQUESTED,
        subject_id=reopen_id,
        operator_id=operator_id or "system",
        recorded_at=recorded_at,
        record=reopen.to_dict(),
    )
    append_post_delivery_support_event(audit_log_path=post_delivery_support_path(repo_root), event=event)
    return SupportServiceResult(True, reopen=reopen)


def approve_post_delivery_reopen(
    *,
    reopen_id: str,
    approved_by_operator_id: str,
    approval_reference: str,
    operator_id: str | None = None,
    repo_root: Any = None,
    recorded_at: str = "t",
) -> SupportServiceResult:
    repo_root = Path(repo_root)
    op = operator_id or approved_by_operator_id
    all_reopens: dict[str, M.PostDeliveryReopen] = {}
    for lst in _reopens_by_issue(repo_root).values():
        for r in lst:
            all_reopens[r.reopen_id] = r
    reopen = all_reopens.get(reopen_id)
    if reopen is None:
        return _deny(code="REOPEN_NOT_FOUND", detail="referenced reopen missing")
    if reopen.status in M.REOPEN_TERMINAL_STATUSES:
        return _deny(code="REOPEN_TERMINAL", detail="reopen already in terminal state")
    if not approved_by_operator_id:
        return _deny(code="REOPEN_REQUIRES_APPROVAL", detail="explicit approval operator required")
    try:
        approved = M.PostDeliveryReopen(
            schema_version=reopen.schema_version,
            reopen_id=reopen.reopen_id,
            issue_id=reopen.issue_id,
            dispute_id=reopen.dispute_id,
            prior_post_delivery_closure_id=reopen.prior_post_delivery_closure_id,
            revision_id=reopen.revision_id,
            revised_delivery_id=reopen.revised_delivery_id,
            project_id=reopen.project_id,
            correlation_id=reopen.correlation_id,
            reopen_reason=reopen.reopen_reason,
            reopen_scope=reopen.reopen_scope,
            target_workflow=reopen.target_workflow,
            approved_by_operator_id=approved_by_operator_id,
            approval_reference=approval_reference,
            approved_at=recorded_at,
            status=M.REOPEN_APPROVED,
            idempotency_key=reopen.idempotency_key,
            evidence_references=reopen.evidence_references,
            created_at=reopen.created_at,
        )
    except ValueError as exc:
        return _deny(code="REOPEN_VALIDATION", detail=str(exc))
    event = make_post_delivery_support_event(
        event_type=M.EVT_REOPEN_APPROVED,
        subject_id=reopen_id,
        operator_id=op,
        recorded_at=recorded_at,
        record=approved.to_dict(),
    )
    append_post_delivery_support_event(audit_log_path=post_delivery_support_path(repo_root), event=event)
    return SupportServiceResult(True, reopen=approved)


# --- F. commercial closure evaluation / recording ---------------------------
def evaluate_commercial_closure(
    *,
    authorization_id: str,
    closure_basis: str,
    closed_by_operator_id: str,
    invoice_state_reference: str | None = None,
    payment_state_reference: str | None = None,
    outstanding_actions: tuple[str, ...] = (),
    evidence_references: tuple[str, ...] = (),
    operator_id: str | None = None,
    repo_root: Any = None,
    recorded_at: str = "t",
) -> SupportServiceResult:
    repo_root = Path(repo_root)
    audit = _load_8f_audit(repo_root, authorization_id=authorization_id)
    if not audit.ok or audit.audit is None or not audit.audit.audit_ready:
        return SupportServiceResult(
            False, error_code="POST_DELIVERY_AUDIT_NOT_READY",
            error_detail="Stage 8F post-delivery audit is not closed", reasons=("AUDIT_NOT_CLOSED",))
    project_id = audit.audit.project_id
    revision_id = audit.audit.revision_id
    revised_delivery_id = audit.audit.revised_delivery_id

    issues = [i for i in _issues_by_id(repo_root).values() if i.project_id == project_id]
    classifications = _classifications_by_issue(repo_root)
    disputes = [d for lst in _disputes_by_issue(repo_root).values() for d in lst if d.project_id == project_id]
    reopens = [r for lst in _reopens_by_issue(repo_root).values() for r in lst if r.project_id == project_id]
    reasons: list[str] = []

    # Unresolved dispute blocks closure.
    open_disputes = [d for d in disputes if d.status not in M.DISPUTE_TERMINAL_STATUSES]
    if open_disputes:
        reasons.append("UNRESOLVED_DISPUTE")

    # Open covered defect blocks closure.
    for i in issues:
        cls = classifications.get(i.issue_id)
        if cls and cls.outcome in (M.CLASS_COVERED_DEFECT, M.CLASS_COVERED_REVISION):
            if i.status not in (M.ISSUE_RESOLVED, M.ISSUE_REJECTED, M.ISSUE_CANCELLED):
                reasons.append("OPEN_COVERED_DEFECT")

    # Active approved reopen blocks closure.
    if any(r.status == M.REOPEN_APPROVED for r in reopens):
        reasons.append("ACTIVE_APPROVED_REOPEN")

    # Incomplete classifications block closure.
    for i in issues:
        if i.issue_id not in classifications:
            reasons.append("INCOMPLETE_CLASSIFICATION")

    if reasons:
        closure = M.PostDeliveryCommercialClosure(
            schema_version=M.POST_DELIVERY_SUPPORT_SCHEMA_VERSION,
            commercial_closure_id="pending",
            project_id=project_id,
            revision_id=revision_id,
            revised_delivery_id=revised_delivery_id,
            release_execution_id=audit.audit.release_id,
            receipt_confirmation_id=audit.audit.receipt_id,
            post_delivery_closure_id=audit.audit.audit_id,
            support_policy_id="",
            issue_ids=tuple(i.issue_id for i in issues),
            dispute_ids=tuple(d.dispute_id for d in disputes),
            reopen_ids=tuple(r.reopen_id for r in reopens),
            closure_status=M.COMMERCIAL_BLOCKED,
            closure_basis=closure_basis,
            closed_by_operator_id=closed_by_operator_id,
            closed_at=recorded_at,
            outstanding_actions=tuple(outstanding_actions),
            invoice_state_reference=invoice_state_reference,
            payment_state_reference=payment_state_reference,
            evidence_references=tuple(evidence_references),
            idempotency_key="pending",
            created_at=recorded_at,
        )
        return SupportServiceResult(False, closure=closure, error_code="CLOSURE_BLOCKED", reasons=tuple(reasons))

    closure = M.PostDeliveryCommercialClosure(
        schema_version=M.POST_DELIVERY_SUPPORT_SCHEMA_VERSION,
        commercial_closure_id="ready",
        project_id=project_id,
        revision_id=revision_id,
        revised_delivery_id=revised_delivery_id,
        release_execution_id=audit.audit.release_id,
        receipt_confirmation_id=audit.audit.receipt_id,
        post_delivery_closure_id=audit.audit.audit_id,
        support_policy_id="",
        issue_ids=tuple(i.issue_id for i in issues),
        dispute_ids=tuple(d.dispute_id for d in disputes),
        reopen_ids=tuple(r.reopen_id for r in reopens),
        closure_status=M.COMMERCIAL_PENDING,
        closure_basis=closure_basis,
        closed_by_operator_id=closed_by_operator_id,
        closed_at=recorded_at,
        outstanding_actions=tuple(outstanding_actions),
        invoice_state_reference=invoice_state_reference,
        payment_state_reference=payment_state_reference,
        evidence_references=tuple(evidence_references),
        idempotency_key="ready",
        created_at=recorded_at,
    )
    return SupportServiceResult(True, closure=closure, reasons=())


def record_commercial_closure(
    *,
    authorization_id: str,
    closure_basis: str,
    closed_by_operator_id: str,
    invoice_state_reference: str | None = None,
    payment_state_reference: str | None = None,
    outstanding_actions: tuple[str, ...] = (),
    evidence_references: tuple[str, ...] = (),
    support_policy_id: str = "",
    operator_id: str | None = None,
    repo_root: Any = None,
    recorded_at: str = "t",
) -> SupportServiceResult:
    repo_root = Path(repo_root)
    op = operator_id or closed_by_operator_id
    audit = _load_8f_audit(repo_root, authorization_id=authorization_id)
    if not audit.ok or audit.audit is None or not audit.audit.audit_ready:
        return _deny(code="POST_DELIVERY_AUDIT_NOT_READY",
                     detail="Stage 8F post-delivery audit is not closed")
    # Re-run blocking checks identically.
    pre = evaluate_commercial_closure(
        authorization_id=authorization_id, closure_basis=closure_basis,
        closed_by_operator_id=closed_by_operator_id,
        invoice_state_reference=invoice_state_reference,
        payment_state_reference=payment_state_reference,
        outstanding_actions=outstanding_actions,
        evidence_references=evidence_references,
        operator_id=op, repo_root=repo_root, recorded_at=recorded_at,
    )
    if not pre.ok:
        return SupportServiceResult(
            False, closure=pre.closure, error_code="CLOSURE_BLOCKED", reasons=pre.reasons)
    if pre.closure is None:
        return _deny(code="CLOSURE_EVALUATION_FAILED", detail="closure evaluation returned no record")

    closure_id = M.build_commercial_closure_id(
        project_id=pre.closure.project_id,
        revision_id=pre.closure.revision_id,
        revised_delivery_id=pre.closure.revised_delivery_id,
        post_delivery_closure_id=pre.closure.post_delivery_closure_id,
        support_policy_id=support_policy_id,
        closure_basis=closure_basis,
    )
    existing_cls = [c for lst in _closures_by_project(repo_root).values() for c in lst]
    for c in existing_cls:
        if c.commercial_closure_id == closure_id:
            return SupportServiceResult(True, closure=c, duplicate_of=c.commercial_closure_id)
        if (c.project_id == pre.closure.project_id
                and c.revision_id == pre.closure.revision_id
                and c.post_delivery_closure_id == pre.closure.post_delivery_closure_id
                and c.closure_status == M.COMMERCIAL_CLOSED):
            return _deny(code="CONFLICTING_COMMERCIAL_CLOSURE",
                         detail="a commercial closure already exists for this delivery")

    issues = [i for i in _issues_by_id(repo_root).values() if i.project_id == pre.closure.project_id]
    disputes = [d for lst in _disputes_by_issue(repo_root).values() for d in lst if d.project_id == pre.closure.project_id]
    reopens = [r for lst in _reopens_by_issue(repo_root).values() for r in lst if r.project_id == pre.closure.project_id]
    try:
        closure = M.PostDeliveryCommercialClosure(
            schema_version=M.POST_DELIVERY_SUPPORT_SCHEMA_VERSION,
            commercial_closure_id=closure_id,
            project_id=pre.closure.project_id,
            revision_id=pre.closure.revision_id,
            revised_delivery_id=pre.closure.revised_delivery_id,
            release_execution_id=pre.closure.release_execution_id,
            receipt_confirmation_id=pre.closure.receipt_confirmation_id,
            post_delivery_closure_id=pre.closure.post_delivery_closure_id,
            support_policy_id=support_policy_id,
            issue_ids=tuple(i.issue_id for i in issues),
            dispute_ids=tuple(d.dispute_id for d in disputes),
            reopen_ids=tuple(r.reopen_id for r in reopens),
            closure_status=M.COMMERCIAL_CLOSED,
            closure_basis=closure_basis,
            closed_by_operator_id=closed_by_operator_id,
            closed_at=recorded_at,
            outstanding_actions=tuple(outstanding_actions),
            invoice_state_reference=invoice_state_reference,
            payment_state_reference=payment_state_reference,
            evidence_references=tuple(evidence_references),
            idempotency_key=closure_id,
            created_at=recorded_at,
        )
    except ValueError as exc:
        return _deny(code="COMMERCIAL_CLOSURE_VALIDATION", detail=str(exc))

    event = make_post_delivery_support_event(
        event_type=M.EVT_COMMERCIAL_CLOSURE_RECORDED,
        subject_id=closure_id,
        operator_id=op,
        recorded_at=recorded_at,
        record=closure.to_dict(),
    )
    append_post_delivery_support_event(audit_log_path=post_delivery_support_path(repo_root), event=event)
    return SupportServiceResult(True, closure=closure)


# --- Complete post-delivery support lineage inspection ---------------------
def inspect_post_delivery_support_lineage(*, project_id: str | None = None, repo_root: Any = None) -> dict[str, Any]:
    repo_root = Path(repo_root)
    policies = [p for p in _policies_by_id(repo_root).values()
               if project_id is None or p.project_id == project_id]
    issues = [i for i in _issues_by_id(repo_root).values()
              if project_id is None or i.project_id == project_id]
    classifications = _classifications_by_issue(repo_root)
    disputes = [d for lst in _disputes_by_issue(repo_root).values() for d in lst
                if project_id is None or d.project_id == project_id]
    reopens = [r for lst in _reopens_by_issue(repo_root).values() for r in lst
               if project_id is None or r.project_id == project_id]
    closures = [c for lst in _closures_by_project(repo_root).values() for c in lst
                if project_id is None or c.project_id == project_id]
    return {
        "project_id": project_id,
        "policies": [p.to_dict() for p in policies],
        "issues": [i.to_dict() for i in issues],
        "classifications": [classifications[i.issue_id].to_dict() for i in issues if i.issue_id in classifications],
        "disputes": [d.to_dict() for d in disputes],
        "reopens": [r.to_dict() for r in reopens],
        "commercial_closures": [c.to_dict() for c in closures],
    }
