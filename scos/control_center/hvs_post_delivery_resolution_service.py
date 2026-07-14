"""SCOS <-> HVS — Stage 8Q post-delivery resolution routing service.

Deterministic, local-only, operator-controlled. Consumes a verified Stage 8P
aggregate outcome, reverifies the bound Stage 8O delivery lineage, and produces
an internal route recommendation plus explicit operator-authorization evidence.

Hard boundaries (always honored):

  * never closes a project,
  * never creates a revision (revision eligibility != revision),
  * never creates a dispute (issue qualification != dispute),
  * never resolves an issue,
  * never contacts a customer / sends a reminder,
  * never mutates invoice / payment state,
  * never invokes HVS, renders, delivers, uploads, or publishes,
  * never begins Stage 8R.

Read-only reuse:

  * Stage 8P readiness + eligibility reverification
    (``build_acceptance_readiness_view``, ``inspect_stage8p_eligibility``)
  * Stage 8O actual-delivery lineage (read-only)
  * Stage 8B revision constants (bounded-scope validation only)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .hvs_customer_receipt_acceptance_models import (
    OUTCOME_ACCEPTED_BY_CUSTOMER,
    OUTCOME_RECEIPT_CONFIRMED_ACCEPTANCE_PENDING,
    OUTCOME_RECEIPT_NOT_CONFIRMED,
    OUTCOME_REJECTED_BY_CUSTOMER,
    OUTCOME_ISSUE_REPORTED,
    OUTCOME_REVISION_REVIEW_REQUESTED,
    OUTCOME_DELIVERY_IDENTITY_CONFLICT,
    OUTCOME_BLOCKED,
    ALLOWED_POST_RECEIPT_OUTCOMES,
)
from .hvs_customer_receipt_acceptance_service import (
    build_acceptance_readiness_view,
    inspect_stage8p_eligibility,
)
from .hvs_customer_receipt_acceptance_store import (
    read_receipt_events,
    receipt_ledger_path,
)
from .hvs_post_delivery_resolution_models import (
    ALLOWED_CLOSURE_ELIGIBILITY,
    ALLOWED_ISSUE_QUALIFICATIONS,
    ALLOWED_RECOMMENDED_ROUTES,
    ALLOWED_REVISION_ELIGIBILITY,
    ALLOWED_ROUTING_STATUSES,
    ClosureEligibilityResult,
    CLOSURE_BLOCKED,
    CLOSURE_ELIGIBLE,
    CLOSURE_NEEDS_OPERATOR_INPUT,
    CLOSURE_NOT_ELIGIBLE,
    DECISION_APPROVE_CLOSURE_RECOMMENDATION,
    DECISION_APPROVE_DEFECT_REVIEW_ROUTE,
    DECISION_APPROVE_DISPUTE_ELIGIBILITY_REVIEW,
    DECISION_APPROVE_MANUAL_FOLLOW_UP_RECOMMENDATION,
    DECISION_APPROVE_REVISION_ELIGIBILITY_REVIEW,
    DECISION_APPROVE_SUPPORT_REVIEW_ROUTE,
    DECISION_CANCEL_ROUTE_REVIEW,
    DECISION_REJECT_ROUTE_RECOMMENDATION,
    EVT_ROUTE_APPROVED,
    EVT_ROUTE_CANCELLED,
    EVT_ROUTE_CREATED,
    EVT_ROUTE_REEVALUATED,
    EVT_ROUTE_REJECTED,
    FollowUpRecommendation,
    ISSUE_BLOCKED,
    ISSUE_DEFECT_CANDIDATE,
    ISSUE_DISPUTE_CANDIDATE,
    ISSUE_GENERAL_RESOLUTION_REVIEW,
    ISSUE_INSUFFICIENT_EVIDENCE,
    ISSUE_REVISION_CANDIDATE,
    ISSUE_SUPPORT_CANDIDATE,
    ISSUE_CATEGORY_TO_QUALIFICATION,
    IssueQualificationResult,
    LEDGER_NAME,
    PostDeliveryResolutionRoute,
    PostDeliveryRouteDecision,
    PostDeliverySourceBinding,
    ROUTE_BLOCKED,
    ROUTE_CLOSURE_ELIGIBILITY_REVIEW,
    ROUTE_CUSTOMER_REJECTION_RESOLUTION_REVIEW,
    ROUTE_DEFECT_REVIEW,
    ROUTE_DISPUTE_ELIGIBILITY_REVIEW,
    ROUTE_MANUAL_ACCEPTANCE_FOLLOW_UP,
    ROUTE_MANUAL_RECEIPT_FOLLOW_UP,
    ROUTE_NO_ACTION_REQUIRED,
    ROUTE_OPERATOR_INVESTIGATION,
    ROUTE_REVISION_ELIGIBILITY_REVIEW,
    ROUTE_SUPPORT_REVIEW,
    REVISION_BLOCKED,
    REVISION_ELIGIBLE,
    REVISION_NEEDS_OPERATOR_INPUT,
    REVISION_NOT_ELIGIBLE,
    RevisionQualificationResult,
    ROUTING_APPROVED,
    ROUTING_BLOCKED,
    ROUTING_CANCELLED,
    ROUTING_DRAFT,
    ROUTING_NEEDS_OPERATOR_INPUT,
    ROUTING_READY_FOR_OPERATOR_REVIEW,
    ROUTING_REJECTED,
    Stage8QReadinessView,
    _require_date,
    _require_evidence_reference,
    _require_free_text,
    _require_issue_summary,
    _require_nonempty,
    _require_operator_id,
    _require_member,
    route_content_hash,
    route_decision_id,
    resolution_route_id,
)
from .hvs_post_delivery_resolution_store import (
    append_resolution_event,
    latest_event_for_route,
    read_resolution_events,
    route_ledger_path,
)
from .hvs_stage8o_delivery_store import read_delivery_events, delivery_ledger_path
from .hvs_revision_models import ITEM_CATEGORIES, SCOPES


# ---------------------------------------------------------------------------
# Service result envelope
# ---------------------------------------------------------------------------
@dataclass
class Stage8QServiceResult:
    ok: bool
    resolution_route: PostDeliveryResolutionRoute | None = None
    closure_eligibility: ClosureEligibilityResult | None = None
    issue_qualification: IssueQualificationResult | None = None
    revision_qualification: RevisionQualificationResult | None = None
    follow_up: FollowUpRecommendation | None = None
    decision: PostDeliveryRouteDecision | None = None
    readiness: Stage8QReadinessView | None = None
    eligible: bool | None = None
    error_code: str | None = None
    error_detail: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "ok": self.ok,
            "resolution_route": self.resolution_route.to_dict() if self.resolution_route else None,
            "closure_eligibility": self.closure_eligibility.to_dict() if self.closure_eligibility else None,
            "issue_qualification": self.issue_qualification.to_dict() if self.issue_qualification else None,
            "revision_qualification": self.revision_qualification.to_dict() if self.revision_qualification else None,
            "follow_up": self.follow_up.to_dict() if self.follow_up else None,
            "decision": self.decision.to_dict() if self.decision else None,
            "readiness": self.readiness.to_dict() if self.readiness else None,
            "eligible": self.eligible,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
        }
        for k, v in self.extra.items():
            if k not in out:
                out[k] = v
        return out


def _deny(*, error_code: str, error_detail: str, **extra: Any) -> Stage8QServiceResult:
    return Stage8QServiceResult(ok=False, error_code=error_code, error_detail=error_detail, extra=dict(extra))


# ---------------------------------------------------------------------------
# Stage 8O actual-delivery binding loader (read-only)
# ---------------------------------------------------------------------------
def _load_8o_actual_delivery(*, repo_root: Any, actual_delivery_record_id: str) -> dict[str, Any] | None:
    ledger = delivery_ledger_path(repo_root)
    for ev in read_delivery_events(ledger_path=ledger):
        if ev.get("event_type") == "DELIVERY_RECORDED" and ev.get("subject_id") == actual_delivery_record_id:
            return ev.get("record") or {}
    return None


def _stage8p_identity_matches_8o(
    *,
    repo_root: Any,
    actual_delivery_record_id: str,
    actual_delivery: dict[str, Any],
) -> bool:
    """Fail-closed cross-check of persisted Stage 8P identity vs Stage 8O.

    Loads the authoritative Stage 8P receipt/decision records directly from the
    receipt ledger and verifies each carries the same customer reference and
    artifact SHA-256 as the Stage 8O actual-delivery record. Returns ``False``
    when any persisted Stage 8P record diverges (forged or misbound aggregate).
    """
    ledger = receipt_ledger_path(repo_root)
    events = read_receipt_events(ledger_path=ledger)
    o_cust = str(actual_delivery.get("safe_recipient_reference") or "").strip().lower()
    o_sha = str(actual_delivery.get("artifact_sha256") or "").strip().lower()
    matched = False
    for ev in events:
        if ev.get("actual_delivery_record_id") != actual_delivery_record_id:
            continue
        rec = ev.get("record") or {}
        r_cust = str(rec.get("customer_reference") or "").strip().lower()
        r_sha = str(rec.get("artifact_sha256") or "").strip().lower()
        if not r_cust and not r_sha:
            continue
        if o_cust and r_cust and r_cust != o_cust:
            return False
        if o_sha and r_sha and r_sha != o_sha:
            return False
        matched = True
    # No persisted Stage 8P identity to cross-check (e.g. RECEIPT_NOT_CONFIRMED
    # with no record) is allowed; a mismatch is the only hard reject.
    return matched or True


def build_source_binding(
    *,
    repo_root: Any,
    actual_delivery_record_id: str,
) -> PostDeliverySourceBinding | None:
    """Construct an immutable source binding from verified Stage 8P + Stage 8O.

    Returns ``None`` when the Stage 8P aggregate / Stage 8O lineage cannot be
    reverified. Callers must treat ``None`` as a hard fail-closed condition.
    """
    if not str(actual_delivery_record_id or "").strip():
        return None
    readiness = build_acceptance_readiness_view(
        repo_root=repo_root, actual_delivery_record_id=actual_delivery_record_id
    )
    rec = _load_8o_actual_delivery(repo_root=repo_root, actual_delivery_record_id=actual_delivery_record_id)
    if rec is None:
        return None
    sha = str(rec.get("artifact_sha256") or "")
    if len(sha) != 64:
        return None
    outcome = readiness.outcome
    if outcome not in ALLOWED_POST_RECEIPT_OUTCOMES:
        return None
    # Re-load the authoritative Stage 8P receipt/decision records directly and
    # cross-verify their identity against the Stage 8O actual-delivery record.
    # The Stage 8P readiness view does not surface raw identity fields, so we
    # compare the canonical receipt record instead. A mismatch means the Stage
    # 8P aggregate was forged or bound to a different delivery (fail closed).
    receipt_matches = _stage8p_identity_matches_8o(repo_root=repo_root, actual_delivery_record_id=actual_delivery_record_id, actual_delivery=rec)
    if not receipt_matches:
        return None
    return PostDeliverySourceBinding(
        schema_version="scos-hvs.stage8q.source-binding.v1/1.0.0",
        project_id=readiness.project_id or str(rec.get("project_id") or ""),
        customer_reference=readiness.customer_reference or str(rec.get("safe_recipient_reference") or ""),
        actual_delivery_record_id=actual_delivery_record_id,
        delivery_package_id=str(rec.get("delivery_package_id") or ""),
        delivery_authorization_id=str(rec.get("authorization_request_id") or ""),
        render_completion_id=str(rec.get("source_render_completion_id") or ""),
        delivery_lineage_id=str(rec.get("delivery_lineage_id") or "") or None,
        artifact_id=readiness.artifact_id or str(rec.get("artifact_id") or ""),
        artifact_sha256=sha.lower(),
        source_stage8p_receipt_record_id=readiness.receipt_record_id,
        source_stage8p_customer_decision_id=readiness.customer_decision_id,
        source_stage8p_aggregate_outcome=outcome,
    )


# ---------------------------------------------------------------------------
# Source eligibility (reverify Stage 8P + 8O before any route)
# ---------------------------------------------------------------------------
def inspect_stage8q_eligibility(
    *,
    repo_root: Any,
    actual_delivery_record_id: str,
) -> Stage8QServiceResult:
    if not str(actual_delivery_record_id or "").strip():
        return _deny(error_code="missing_actual_delivery_record_id", error_detail="actual_delivery_record_id is required")
    # Re-verify Stage 8P / 8O delivery identity (fails closed on forged/invalid).
    eligibility = inspect_stage8p_eligibility(
        repo_root=repo_root, actual_delivery_record_id=actual_delivery_record_id
    )
    if not eligibility.ok:
        return _deny(
            error_code="stage8p_evidence_not_verified",
            error_detail=eligibility.error_detail or "Stage 8P / 8O evidence failed reverification",
            actual_delivery_record_id=actual_delivery_record_id,
        )
    binding = build_source_binding(repo_root=repo_root, actual_delivery_record_id=actual_delivery_record_id)
    if binding is None:
        return _deny(
            error_code="stage8p_evidence_not_verified",
            error_detail="could not construct immutable source binding from verified evidence",
            actual_delivery_record_id=actual_delivery_record_id,
        )
    return Stage8QServiceResult(ok=True, eligible=True, extra={"actual_delivery_record_id": actual_delivery_record_id})


# ---------------------------------------------------------------------------
# Routing classification (pure, deterministic)
# ---------------------------------------------------------------------------
def classify_route(*, aggregate_outcome: str) -> str:
    _require_member(aggregate_outcome, ALLOWED_POST_RECEIPT_OUTCOMES, "unknown_stage8p_aggregate_outcome", aggregate_outcome)
    return {
        OUTCOME_ACCEPTED_BY_CUSTOMER: ROUTE_CLOSURE_ELIGIBILITY_REVIEW,
        OUTCOME_RECEIPT_CONFIRMED_ACCEPTANCE_PENDING: ROUTE_MANUAL_ACCEPTANCE_FOLLOW_UP,
        OUTCOME_RECEIPT_NOT_CONFIRMED: ROUTE_MANUAL_RECEIPT_FOLLOW_UP,
        OUTCOME_REJECTED_BY_CUSTOMER: ROUTE_CUSTOMER_REJECTION_RESOLUTION_REVIEW,
        OUTCOME_ISSUE_REPORTED: ROUTE_SUPPORT_REVIEW,
        OUTCOME_REVISION_REVIEW_REQUESTED: ROUTE_REVISION_ELIGIBILITY_REVIEW,
        OUTCOME_DELIVERY_IDENTITY_CONFLICT: ROUTE_OPERATOR_INVESTIGATION,
        OUTCOME_BLOCKED: ROUTE_BLOCKED,
    }[aggregate_outcome]


# ---------------------------------------------------------------------------
# Closure eligibility (read-only, acceptance alone insufficient)
# ---------------------------------------------------------------------------
def evaluate_closure_eligibility(
    *,
    binding: PostDeliverySourceBinding,
    issue_reported: bool = False,
    open_revision_review: bool = False,
    rejection_present: bool = False,
    identity_conflict: bool = False,
    conflicting_decision: bool = False,
    delivery_invalidated: bool = False,
    dispute_active: bool = False,
    support_blocker_active: bool = False,
    commercial_payment_blocker_active: bool = False,
    evaluation_date: str | None = None,
) -> ClosureEligibilityResult:
    blockers: list[str] = []
    warnings: list[str] = []
    if delivery_invalidated:
        blockers.append("delivery_invalidated")
    if issue_reported:
        blockers.append("unresolved_issue_reported")
    if open_revision_review:
        blockers.append("open_revision_review")
    if rejection_present:
        blockers.append("customer_rejection_present")
    if identity_conflict:
        blockers.append("delivery_identity_conflict")
    if conflicting_decision:
        blockers.append("conflicting_customer_decision")
    if dispute_active:
        blockers.append("active_dispute")
    if support_blocker_active:
        blockers.append("unresolved_support_blocker")
    if commercial_payment_blocker_active:
        blockers.append("mandatory_commercial_or_payment_blocker")
    if evaluation_date is not None:
        _require_date(evaluation_date, field_name="evaluation_date")
    if blockers:
        return ClosureEligibilityResult(
            closure_eligibility_status=CLOSURE_NOT_ELIGIBLE,
            eligible=False,
            blockers=tuple(blockers),
            warnings=tuple(warnings),
            evaluation_date=evaluation_date,
        )
    warnings.append("commercial_payment_dispute_support_state_not_independently_reverified_by_stage8q")
    warnings.append("operator_authorization_required_before_any_closure_action")
    return ClosureEligibilityResult(
        closure_eligibility_status=CLOSURE_ELIGIBLE,
        eligible=True,
        blockers=(),
        warnings=tuple(warnings),
        evaluation_date=evaluation_date,
    )


# ---------------------------------------------------------------------------
# Issue qualification (classification, never confirmation)
# ---------------------------------------------------------------------------
def qualify_reported_issue(
    *,
    issue_summary: str | None = None,
    issue_category: str | None = None,
    safe_evidence_reference: str | None = None,
    evaluation_date: str | None = None,
) -> IssueQualificationResult:
    if issue_summary is not None:
        issue_summary = _require_issue_summary(issue_summary)
    if safe_evidence_reference is not None:
        safe_evidence_reference = _require_evidence_reference(safe_evidence_reference)
    if evaluation_date is not None:
        _require_date(evaluation_date, field_name="evaluation_date")

    category = None
    if issue_category is not None:
        category = _require_nonempty(issue_category, field_name="issue_category")
        if category not in ISSUE_CATEGORY_TO_QUALIFICATION:
            category = None  # unknown category => not forced into a narrow bucket

    if (issue_summary is None or not issue_summary) and category is None:
        return IssueQualificationResult(
            issue_qualification=ISSUE_INSUFFICIENT_EVIDENCE,
            confirmed=False,
            defect_confirmed=False,
            dispute_created=False,
            revision_created=False,
            hvs_invoked=False,
            insufficient_evidence=True,
            evaluation_date=evaluation_date,
            safe_evidence_reference=safe_evidence_reference,
        )

    if category is not None:
        qualification = ISSUE_CATEGORY_TO_QUALIFICATION[category]
    elif issue_summary:
        # Explicit but unmapped free-text => general resolution review (no force).
        qualification = ISSUE_GENERAL_RESOLUTION_REVIEW
    else:  # pragma: no cover - guarded above
        qualification = ISSUE_INSUFFICIENT_EVIDENCE

    if qualification not in ALLOWED_ISSUE_QUALIFICATIONS:
        qualification = ISSUE_BLOCKED

    return IssueQualificationResult(
        issue_qualification=qualification,
        confirmed=False,  # classification is never confirmation
        defect_confirmed=(qualification == ISSUE_DEFECT_CANDIDATE),  # candidate, not verdict
        dispute_created=False,
        revision_created=False,
        hvs_invoked=False,
        insufficient_evidence=False,
        evaluation_date=evaluation_date,
        safe_evidence_reference=safe_evidence_reference,
    )


# ---------------------------------------------------------------------------
# Revision eligibility (Stage 8B contract reuse, read-only)
# ---------------------------------------------------------------------------
def evaluate_revision_eligibility(
    *,
    binding: PostDeliverySourceBinding,
    revision_request_valid: bool = True,
    requested_scope: str | None = None,
    conflicting_final_decision: bool = False,
    evaluation_date: str | None = None,
) -> RevisionQualificationResult:
    if evaluation_date is not None:
        _require_date(evaluation_date, field_name="evaluation_date")
    # Known delivery lineage required.
    if not binding.delivery_lineage_id:
        return RevisionQualificationResult(
            revision_eligibility_status=REVISION_BLOCKED,
            eligible=False,
            successor_version_persisted=False,
            revision_created=False,
            rerender_authorized=False,
            hvs_invoked=False,
            free_revision_inferred=False,
            cost_inferred=False,
            evaluation_date=evaluation_date,
        )
    # Artifact identity must be valid (64-char SHA, unchanged).
    if len(binding.artifact_sha256) != 64:
        return RevisionQualificationResult(
            revision_eligibility_status=REVISION_BLOCKED,
            eligible=False,
            successor_version_persisted=False,
            revision_created=False,
            rerender_authorized=False,
            hvs_invoked=False,
            free_revision_inferred=False,
            cost_inferred=False,
            evaluation_date=evaluation_date,
        )
    if conflicting_final_decision:
        return RevisionQualificationResult(
            revision_eligibility_status=REVISION_NOT_ELIGIBLE,
            eligible=False,
            successor_version_persisted=False,
            revision_created=False,
            rerender_authorized=False,
            hvs_invoked=False,
            free_revision_inferred=False,
            cost_inferred=False,
            evaluation_date=evaluation_date,
        )
    # Bounded requested scope required.
    scope = None
    if requested_scope is not None:
        scope = _require_free_text(requested_scope, max_len=256, field_name="requested_scope")
    if requested_scope is not None and not scope:
        return RevisionQualificationResult(
            revision_eligibility_status=REVISION_NEEDS_OPERATOR_INPUT,
            eligible=False,
            successor_version_persisted=False,
            revision_created=False,
            rerender_authorized=False,
            hvs_invoked=False,
            free_revision_inferred=False,
            cost_inferred=False,
            evaluation_date=evaluation_date,
        )
    status = REVISION_ELIGIBLE if revision_request_valid else REVISION_NOT_ELIGIBLE
    return RevisionQualificationResult(
        revision_eligibility_status=status,
        eligible=revision_request_valid,
        successor_version_persisted=False,  # never persisted by 8Q
        revision_created=False,  # never created by 8Q
        rerender_authorized=False,  # never authorized by 8Q
        hvs_invoked=False,
        free_revision_inferred=False,  # never inferred
        cost_inferred=False,  # never inferred
        evaluation_date=evaluation_date,
    )


# ---------------------------------------------------------------------------
# Follow-up recommendation (manual action only; never contact)
# ---------------------------------------------------------------------------
def build_follow_up_recommendation(
    *,
    route_kind: str,
    recommended_manual_action: str,
    evaluation_date: str | None = None,
) -> FollowUpRecommendation:
    _require_member(route_kind, ALLOWED_RECOMMENDED_ROUTES, "invalid_route_kind", route_kind)
    action = _require_free_text(recommended_manual_action, max_len=512, field_name="recommended_manual_action")
    if evaluation_date is not None:
        _require_date(evaluation_date, field_name="evaluation_date")
    return FollowUpRecommendation(
        route_kind=route_kind,
        recommended_manual_action=action,
        customer_contact_authorized=False,
        customer_contact_performed=False,
        reminder_scheduled=False,
        acceptance_inferred=False,
        closure_recommended=False,
        evaluation_date=evaluation_date,
    )


# ---------------------------------------------------------------------------
# Route creation (append-only recommendation; no execution)
# ---------------------------------------------------------------------------
def create_post_delivery_route(
    *,
    repo_root: Any,
    actual_delivery_record_id: str,
    issue_summary: str | None = None,
    issue_category: str | None = None,
    safe_evidence_reference: str | None = None,
    revision_request_valid: bool = True,
    requested_scope: str | None = None,
    dispute_active: bool = False,
    support_blocker_active: bool = False,
    commercial_payment_blocker_active: bool = False,
    evaluation_date: str | None = None,
    recorded_by_operator_id: str = "system-readonly-stage8q",
    informational_recorded_at: str = "",
) -> Stage8QServiceResult:
    eligibility = inspect_stage8q_eligibility(
        repo_root=repo_root, actual_delivery_record_id=actual_delivery_record_id
    )
    if not eligibility.ok:
        return eligibility
    binding = build_source_binding(repo_root=repo_root, actual_delivery_record_id=actual_delivery_record_id)
    if binding is None:  # pragma: no cover - guarded by eligibility
        return _deny(error_code="stage8p_evidence_not_verified", error_detail="source binding unavailable")
    if evaluation_date is not None:
        _require_date(evaluation_date, field_name="evaluation_date")

    outcome = binding.source_stage8p_aggregate_outcome
    recommended_route = classify_route(aggregate_outcome=outcome)

    closure_eligibility_status = None
    issue_qualification = None
    revision_eligibility_status = None
    blockers: list[str] = []
    warnings: list[str] = []
    required_actions: list[str] = []

    if outcome == OUTCOME_DELIVERY_IDENTITY_CONFLICT:
        recommended_route = ROUTE_OPERATOR_INVESTIGATION
        blockers.append("delivery_identity_conflict")
        required_actions.append("operator_investigation_required")
    elif outcome == OUTCOME_BLOCKED:
        recommended_route = ROUTE_BLOCKED
        blockers.append("source_blocked")
        required_actions.append("preserve_blocker_no_mutation")
    elif outcome == OUTCOME_ACCEPTED_BY_CUSTOMER:
        closure = evaluate_closure_eligibility(
            binding=binding,
            issue_reported=False,
            open_revision_review=False,
            rejection_present=False,
            identity_conflict=False,
            conflicting_decision=False,
            delivery_invalidated=False,
            dispute_active=dispute_active,
            support_blocker_active=support_blocker_active,
            commercial_payment_blocker_active=commercial_payment_blocker_active,
            evaluation_date=evaluation_date,
        )
        closure_eligibility_status = closure.closure_eligibility_status
        blockers.extend(closure.blockers)
        warnings.extend(closure.warnings)
        required_actions.append("explicit_operator_closure_authorization_required")
    elif outcome == OUTCOME_REJECTED_BY_CUSTOMER:
        required_actions.append("operator_resolution_review_required")
        required_actions.append("preserve_rejection_evidence")
    elif outcome == OUTCOME_ISSUE_REPORTED:
        qual = qualify_reported_issue(
            issue_summary=issue_summary,
            issue_category=issue_category,
            safe_evidence_reference=safe_evidence_reference,
            evaluation_date=evaluation_date,
        )
        issue_qualification = qual.issue_qualification
        if issue_qualification == ISSUE_DEFECT_CANDIDATE:
            recommended_route = ROUTE_DEFECT_REVIEW
        elif issue_qualification == ISSUE_DISPUTE_CANDIDATE:
            recommended_route = ROUTE_DISPUTE_ELIGIBILITY_REVIEW
        else:
            recommended_route = ROUTE_SUPPORT_REVIEW
        required_actions.append("operator_issue_qualification_review_required")
    elif outcome == OUTCOME_REVISION_REVIEW_REQUESTED:
        rev = evaluate_revision_eligibility(
            binding=binding,
            revision_request_valid=revision_request_valid,
            requested_scope=requested_scope,
            conflicting_final_decision=False,
            evaluation_date=evaluation_date,
        )
        revision_eligibility_status = rev.revision_eligibility_status
        required_actions.append("operator_revision_eligibility_review_required")

    normalized_qualification = "|".join(
        [
            issue_qualification or "",
            revision_eligibility_status or "",
            closure_eligibility_status or "",
        ]
    )
    rid = resolution_route_id(
        binding=binding,
        recommended_route=recommended_route,
        closure_eligibility_status=closure_eligibility_status,
        issue_qualification=issue_qualification,
        revision_eligibility_status=revision_eligibility_status,
        evaluation_date=evaluation_date,
        normalized_qualification=normalized_qualification,
    )

    route_status = ROUTING_READY_FOR_OPERATOR_REVIEW
    if recommended_route in (ROUTE_BLOCKED, ROUTE_OPERATOR_INVESTIGATION):
        route_status = ROUTING_BLOCKED

    route = PostDeliveryResolutionRoute(
        schema_version="scos-hvs.stage8q.route.v1/1.0.0",
        resolution_route_id=rid,
        project_id=binding.project_id,
        customer_reference=binding.customer_reference,
        source_stage8p_receipt_record_id=binding.source_stage8p_receipt_record_id,
        source_stage8p_customer_decision_id=binding.source_stage8p_customer_decision_id,
        source_stage8p_aggregate_outcome=outcome,
        source_actual_delivery_record_id=binding.actual_delivery_record_id,
        source_delivery_package_id=binding.delivery_package_id,
        source_delivery_authorization_id=binding.delivery_authorization_id,
        source_render_completion_id=binding.render_completion_id,
        source_delivery_lineage_id=binding.delivery_lineage_id,
        artifact_id=binding.artifact_id,
        artifact_sha256=binding.artifact_sha256,
        route_status=route_status,
        recommended_route=recommended_route,
        closure_eligibility_status=closure_eligibility_status,
        issue_qualification=issue_qualification,
        revision_eligibility_status=revision_eligibility_status,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        required_operator_actions=tuple(required_actions),
        safe_evidence_references=tuple([safe_evidence_reference] if safe_evidence_reference else []),
        manual_action_required=bool(required_actions),
        customer_contact_authorized=False,
        customer_contact_performed=False,
        project_closure_authorized=False,
        project_closed=False,
        revision_creation_authorized=False,
        revision_created=False,
        dispute_creation_authorized=False,
        dispute_created=False,
        rerender_authorized=False,
        hvs_invoked=False,
        invoice_state_changed=False,
        payment_state_changed=False,
        automation_allowed=False,
        informational_evaluation_date=evaluation_date or "",
        informational_recorded_at=informational_recorded_at,
    )

    # Compute deterministic content hash and persist append-only event.
    c_hash = route_content_hash(route.to_dict())
    route = route.__class__(**{**route.to_dict(), "deterministic_content_hash": c_hash})
    append_resolution_event(
        ledger_path=route_ledger_path(repo_root),
        event_type=EVT_ROUTE_CREATED,
        resolution_route_id=rid,
        project_id=route.project_id,
        actual_delivery_record_id=route.source_actual_delivery_record_id,
        artifact_sha256=route.artifact_sha256,
        source_aggregate_outcome=route.source_stage8p_aggregate_outcome,
        recommended_route=route.recommended_route,
        resulting_status=route.route_status,
        operator_id=recorded_by_operator_id,
        recorded_at=informational_recorded_at or "stage8q-readonly",
        route_content_hash=c_hash,
        record_payload=route.to_dict(),
    )
    return Stage8QServiceResult(ok=True, resolution_route=route, eligible=True)


# ---------------------------------------------------------------------------
# Route inspection (read-only)
# ---------------------------------------------------------------------------
def inspect_post_delivery_route(*, repo_root: Any, resolution_route_id: str) -> Stage8QServiceResult:
    rid = _require_nonempty(resolution_route_id, field_name="resolution_route_id")
    created = None
    for ev in read_resolution_events(ledger_path=route_ledger_path(repo_root)):
        if ev.get("resolution_route_id") == rid and ev.get("event_type") == EVT_ROUTE_CREATED:
            created = ev
            break
    if created is None:
        return _deny(error_code="resolution_route_not_found", error_detail="no route event for this id", resolution_route_id=rid)
    record = created.get("record") or {}
    route = PostDeliveryResolutionRoute(**record)
    return Stage8QServiceResult(ok=True, resolution_route=route)


# ---------------------------------------------------------------------------
# Operator decision (authorization evidence only; never executes)
# ---------------------------------------------------------------------------
def _route_execution_guard(route: PostDeliveryResolutionRoute) -> None:
    # Explicit invariant assertion: a Stage 8Q decision never mutates downstream.
    assert not route.project_closed
    assert not route.revision_created
    assert not route.dispute_created
    assert not route.customer_contact_performed
    assert not route.hvs_invoked
    assert not route.invoice_state_changed
    assert not route.payment_state_changed
    assert not route.automation_allowed


_ROUTE_DECISION_TARGET_STATUS = {
    DECISION_APPROVE_CLOSURE_RECOMMENDATION: ROUTING_APPROVED,
    DECISION_APPROVE_MANUAL_FOLLOW_UP_RECOMMENDATION: ROUTING_APPROVED,
    DECISION_APPROVE_SUPPORT_REVIEW_ROUTE: ROUTING_APPROVED,
    DECISION_APPROVE_DEFECT_REVIEW_ROUTE: ROUTING_APPROVED,
    DECISION_APPROVE_DISPUTE_ELIGIBILITY_REVIEW: ROUTING_APPROVED,
    DECISION_APPROVE_REVISION_ELIGIBILITY_REVIEW: ROUTING_APPROVED,
    DECISION_REJECT_ROUTE_RECOMMENDATION: ROUTING_REJECTED,
    DECISION_CANCEL_ROUTE_REVIEW: ROUTING_CANCELLED,
}


def decide_post_delivery_route(
    *,
    repo_root: Any,
    resolution_route_id: str,
    decision_action: str,
    operator_id: str,
    reason: str | None = None,
    informational_recorded_at: str = "",
) -> Stage8QServiceResult:
    rid = _require_nonempty(resolution_route_id, field_name="resolution_route_id")
    action = _require_member(decision_action, tuple(_ROUTE_DECISION_TARGET_STATUS), "invalid_decision_action", decision_action)
    op = _require_operator_id(operator_id)

    inspect = inspect_post_delivery_route(repo_root=repo_root, resolution_route_id=rid)
    if not inspect.ok:
        return inspect
    route = inspect.resolution_route
    _route_execution_guard(route)

    prior = latest_event_for_route(ledger_path=route_ledger_path(repo_root), resolution_route_id=rid)
    prior_status = (prior or {}).get("resulting_status")
    if prior_status in (ROUTING_APPROVED, ROUTING_REJECTED, ROUTING_CANCELLED):
        return _deny(
            error_code="route_decision_already_final",
            error_detail="route decision is already final; decisions are immutable",
            resolution_route_id=rid,
        )

    if action in (DECISION_REJECT_ROUTE_RECOMMENDATION, DECISION_CANCEL_ROUTE_REVIEW):
        if not reason or not str(reason).strip():
            return _deny(error_code="decision_requires_reason", error_detail="rejection/cancellation requires a reason", resolution_route_id=rid)
        reason_norm = _require_free_text(reason, max_len=512, field_name="reason")
    else:
        reason_norm = _require_free_text(reason or "", max_len=512, field_name="reason")

    c_hash = route_content_hash(route.to_dict())
    resulting_status = _ROUTE_DECISION_TARGET_STATUS[action]
    # Approval binds the exact route content hash; a mismatch rejects.
    if action.startswith("APPROVE_") and route.deterministic_content_hash and route.deterministic_content_hash != c_hash:
        return _deny(error_code="route_content_hash_mismatch", error_detail="route semantics changed since recommendation", resolution_route_id=rid)

    did = route_decision_id(
        resolution_route_id=rid,
        route_content_hash=c_hash,
        decision_action=action,
        normalized_reason=reason_norm,
    )
    decision = PostDeliveryRouteDecision(
        schema_version="scos-hvs.stage8q.decision.v1/1.0.0",
        route_decision_id=did,
        resolution_route_id=rid,
        decision_action=action,
        operator_id=op,
        reason=reason_norm or None,
        route_content_hash=c_hash,
        resulting_status=resulting_status,
        route_executed=False,
        project_closed=False,
        revision_created=False,
        dispute_created=False,
        customer_contact_performed=False,
        hvs_invoked=False,
        automation_allowed=False,
        informational_recorded_at=informational_recorded_at,
    )
    event_type = {
        ROUTING_APPROVED: EVT_ROUTE_APPROVED,
        ROUTING_REJECTED: EVT_ROUTE_REJECTED,
        ROUTING_CANCELLED: EVT_ROUTE_CANCELLED,
    }[resulting_status]
    append_resolution_event(
        ledger_path=route_ledger_path(repo_root),
        event_type=event_type,
        resolution_route_id=rid,
        project_id=route.project_id,
        actual_delivery_record_id=route.source_actual_delivery_record_id,
        artifact_sha256=route.artifact_sha256,
        source_aggregate_outcome=route.source_stage8p_aggregate_outcome,
        recommended_route=route.recommended_route,
        resulting_status=resulting_status,
        operator_id=op,
        recorded_at=informational_recorded_at or "stage8q-readonly",
        route_content_hash=c_hash,
        record_payload=decision.to_dict(),
    )
    return Stage8QServiceResult(ok=True, decision=decision, resolution_route=route)


# ---------------------------------------------------------------------------
# Readiness view (read-only; no mutation)
# ---------------------------------------------------------------------------
def build_stage8q_readiness_view(*, repo_root: Any, actual_delivery_record_id: str) -> Stage8QServiceResult:
    eligibility = inspect_stage8q_eligibility(
        repo_root=repo_root, actual_delivery_record_id=actual_delivery_record_id
    )
    if not eligibility.ok:
        return eligibility
    binding = build_source_binding(repo_root=repo_root, actual_delivery_record_id=actual_delivery_record_id)
    if binding is None:  # pragma: no cover
        return _deny(error_code="stage8p_evidence_not_verified", error_detail="source binding unavailable")
    recommended_route = classify_route(aggregate_outcome=binding.source_stage8p_aggregate_outcome)
    rid = resolution_route_id(
        binding=binding,
        recommended_route=recommended_route,
        closure_eligibility_status=None,
        issue_qualification=None,
        revision_eligibility_status=None,
        evaluation_date=None,
        normalized_qualification="",
    )
    ev = latest_event_for_route(ledger_path=route_ledger_path(repo_root), resolution_route_id=rid)
    operator_decision_id = None
    operator_decision_status = None
    if ev is not None:
        operator_decision_status = ev.get("resulting_status")
        rec = ev.get("record") or {}
        operator_decision_id = rec.get("route_decision_id")
    view = Stage8QReadinessView(
        schema_version="scos-hvs.stage8q.readiness.v1/1.0.0",
        resolution_route_id=rid,
        project_id=binding.project_id,
        customer_reference=binding.customer_reference,
        actual_delivery_record_id=binding.actual_delivery_record_id,
        artifact_sha256=binding.artifact_sha256,
        source_stage8p_aggregate_outcome=binding.source_stage8p_aggregate_outcome,
        recommended_route=recommended_route,
        route_status=operator_decision_status,
        closure_eligibility_status=None,
        issue_qualification=None,
        revision_eligibility_status=None,
        operator_decision_id=operator_decision_id,
        operator_decision_status=operator_decision_status,
        evaluation_date=None,
    )
    return Stage8QServiceResult(ok=True, readiness=view, eligible=True)
