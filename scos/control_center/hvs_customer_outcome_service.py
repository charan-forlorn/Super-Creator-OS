"""Stage 8H customer-success evidence services.

This module is deliberately local-only.  It records append-only customer
outcome, consent, and opportunity evidence; it never contacts a customer or
performs publication, HVS, payment, or network work.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .hvs_customer_outcome_models import (
    BLOCKED,
    HIGH,
    INSUFFICIENT_EVIDENCE,
    LOW,
    MEDIUM,
    PRIORITY_SCORE_VERSION,
    ALLOWED_OPPORTUNITY_STATUSES,
    CANCELLED,
    CONSENT_GRANTED,
    CONSENT_REVOKED,
    CONVERTED,
    CustomerOutcomeReview,
    ConsentRevocation,
    DECLINED,
    FOLLOW_ON_PROJECT,
    IDENTIFIED,
    NO_OPPORTUNITY,
    Opportunity,
    OpportunityQualification,
    PortfolioConsent,
    QUALIFIED,
    RENEWAL,
    SUPERSEDED,
    TestimonialConsent,
    normalize_currency,
    normalize_money,
    stable_id,
)
from .hvs_customer_outcome_store import (
    append_customer_success_event,
    customer_success_path,
    make_customer_success_event,
    read_customer_success_events,
)
from .hvs_post_delivery_support_models import (
    COMMERCIAL_CLOSED,
    DISPUTE_TERMINAL_STATUSES,
    PostDeliveryCommercialClosure,
    PostDeliveryDispute,
)
from .hvs_post_delivery_support_store import (
    post_delivery_support_path,
    read_post_delivery_support_events,
)


EVT_OUTCOME_RECORDED = "OUTCOME_RECORDED"
EVT_PORTFOLIO_CONSENT_RECORDED = "PORTFOLIO_CONSENT_RECORDED"
EVT_TESTIMONIAL_CONSENT_RECORDED = "TESTIMONIAL_CONSENT_RECORDED"
EVT_CONSENT_REVOKED = "CONSENT_REVOKED"
EVT_OPPORTUNITY_IDENTIFIED = "OPPORTUNITY_IDENTIFIED"
EVT_OPPORTUNITY_QUALIFIED = "OPPORTUNITY_QUALIFIED"


@dataclass(frozen=True)
class CustomerSuccessResult:
    ok: bool
    record: Any = None
    duplicate_of: str | None = None
    error_code: str | None = None
    error_detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "record": self.record.to_dict() if hasattr(self.record, "to_dict") else self.record,
            "duplicate_of": self.duplicate_of,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
            "automation_allowed": False,
        }


def _deny(code: str, detail: str) -> CustomerSuccessResult:
    return CustomerSuccessResult(False, error_code=code, error_detail=detail)


def _events(repo_root: Any):
    return read_customer_success_events(audit_log_path=customer_success_path(Path(repo_root)))


def _tuple_dict(data: dict[str, Any], *fields: str) -> dict[str, Any]:
    copy = dict(data)
    for field in fields:
        copy[field] = tuple(copy.get(field) or ())
    return copy


def _outcomes(repo_root: Any) -> dict[str, CustomerOutcomeReview]:
    records: dict[str, CustomerOutcomeReview] = {}
    for event in _events(repo_root):
        if event.event_type == EVT_OUTCOME_RECORDED:
            data = _tuple_dict(event.record, "measurable_outcomes", "unresolved_concerns", "evidence_references")
            data["measurable_outcomes"] = tuple(dict(item) for item in data["measurable_outcomes"])
            records[data["outcome_review_id"]] = CustomerOutcomeReview(**data)
    return records


def _portfolio_consents(repo_root: Any) -> dict[str, PortfolioConsent]:
    records: dict[str, PortfolioConsent] = {}
    for event in _events(repo_root):
        if event.event_type == EVT_PORTFOLIO_CONSENT_RECORDED:
            data = _tuple_dict(event.record, "allowed_artifact_references", "allowed_formats", "allowed_usage_contexts", "anonymization_rules", "evidence_references")
            records[data["portfolio_consent_id"]] = PortfolioConsent(**data)
    return records


def _testimonial_consents(repo_root: Any) -> dict[str, TestimonialConsent]:
    records: dict[str, TestimonialConsent] = {}
    for event in _events(repo_root):
        if event.event_type == EVT_TESTIMONIAL_CONSENT_RECORDED:
            data = _tuple_dict(event.record, "approved_usage_contexts", "approved_edits", "evidence_references")
            records[data["testimonial_consent_id"]] = TestimonialConsent(**data)
    return records


def _revocations(repo_root: Any) -> dict[str, ConsentRevocation]:
    records: dict[str, ConsentRevocation] = {}
    for event in _events(repo_root):
        if event.event_type == EVT_CONSENT_REVOKED:
            data = _tuple_dict(event.record, "evidence_references")
            item = ConsentRevocation(**data)
            records[item.consent_id] = item
    return records


def _opportunities(repo_root: Any) -> dict[str, Opportunity]:
    records: dict[str, Opportunity] = {}
    for event in _events(repo_root):
        if event.event_type == EVT_OPPORTUNITY_IDENTIFIED:
            data = _tuple_dict(event.record, "source_issue_ids", "source_evidence_references", "scoring_reasons")
            value = data.get("estimated_value")
            data["estimated_value"] = Decimal(value) if value is not None else None
            records[data["opportunity_id"]] = Opportunity(**data)
    return records


def _qualifications(repo_root: Any) -> dict[str, OpportunityQualification]:
    records: dict[str, OpportunityQualification] = {}
    for event in _events(repo_root):
        if event.event_type == EVT_OPPORTUNITY_QUALIFIED:
            item = OpportunityQualification(**event.record)
            records[item.opportunity_id] = item
    return records


def _commercial_closure(repo_root: Any, commercial_closure_id: str) -> PostDeliveryCommercialClosure | None:
    for event in read_post_delivery_support_events(audit_log_path=post_delivery_support_path(Path(repo_root))):
        if event.event_type != "COMMERCIAL_CLOSURE_RECORDED":
            continue
        record = PostDeliveryCommercialClosure(**_tuple_dict(event.record, "issue_ids", "dispute_ids", "reopen_ids", "outstanding_actions", "evidence_references"))
        if record.commercial_closure_id == commercial_closure_id:
            return record
    return None


def _has_unresolved_dispute(repo_root: Any, closure: PostDeliveryCommercialClosure) -> bool:
    """Check current Stage 8G dispute evidence, including post-closure intake."""
    disputes: dict[str, PostDeliveryDispute] = {}
    for event in read_post_delivery_support_events(audit_log_path=post_delivery_support_path(Path(repo_root))):
        if event.event_type not in ("DISPUTE_OPENED", "DISPUTE_RESOLVED"):
            continue
        record = PostDeliveryDispute(**_tuple_dict(event.record, "disputed_artifact_references", "evidence_references"))
        if record.project_id == closure.project_id:
            disputes[record.dispute_id] = record
    return any(item.status not in DISPUTE_TERMINAL_STATUSES for item in disputes.values())


def _append(repo_root: Any, event_type: str, subject_id: str, operator_id: str, recorded_at: str, record: Any) -> None:
    event = make_customer_success_event(event_type=event_type, subject_id=subject_id, operator_id=operator_id, recorded_at=recorded_at, record=record.to_dict())
    append_customer_success_event(audit_log_path=customer_success_path(Path(repo_root)), event=event)


def _same(existing: Any, candidate: Any) -> bool:
    left, right = existing.to_dict(), candidate.to_dict()
    for field in ("created_at", "recorded_at"):
        left.pop(field, None)
        right.pop(field, None)
    return left == right


def _require_closed_lineage(repo_root: Any, commercial_closure_id: str) -> PostDeliveryCommercialClosure | CustomerSuccessResult:
    closure = _commercial_closure(repo_root, commercial_closure_id)
    if closure is None:
        return _deny("COMMERCIAL_CLOSURE_NOT_FOUND", "commercial closure evidence was not found")
    if closure.closure_status != COMMERCIAL_CLOSED:
        return _deny("COMMERCIAL_CLOSURE_NOT_CLOSED", "customer-success evidence requires a commercially closed lineage")
    from .hvs_manual_release_receipt_service import _audit_exists

    if not _audit_exists(repo_root=Path(repo_root), audit_id=closure.post_delivery_closure_id):
        return _deny("COMMERCIAL_CLOSURE_LINEAGE_INVALID", "commercial closure is not backed by Stage 8F audit evidence")
    if _has_unresolved_dispute(repo_root, closure):
        return _deny("UNRESOLVED_DISPUTE", "an active post-delivery dispute blocks positive customer-success evidence")
    return closure


def record_customer_outcome(*, commercial_closure_id: str, customer_reference: str, recorded_by_operator_id: str, satisfaction_rating: int, delivery_quality_rating: int, communication_rating: int, timeliness_rating: int, business_outcome_status: str, business_outcome_summary: str, repo_root: Any, measurable_outcomes: tuple[dict[str, str], ...] = (), unresolved_concerns: tuple[str, ...] = (), evidence_references: tuple[str, ...] = (), metadata: dict[str, str] | None = None, idempotency_key: str = "", recorded_at: str = "t") -> CustomerSuccessResult:
    closure = _require_closed_lineage(repo_root, commercial_closure_id)
    if isinstance(closure, CustomerSuccessResult):
        return closure
    key = idempotency_key or stable_id("outcome-key", {"closure": commercial_closure_id, "customer": customer_reference})
    record_id = stable_id("scos-hvs-outcome-review", {"commercial_closure_id": commercial_closure_id, "idempotency_key": key})
    try:
        record = CustomerOutcomeReview(
            outcome_review_id=record_id, project_id=closure.project_id, revision_id=closure.revision_id,
            revised_delivery_id=closure.revised_delivery_id, release_execution_id=closure.release_execution_id,
            receipt_confirmation_id=closure.receipt_confirmation_id, post_delivery_closure_id=closure.post_delivery_closure_id,
            commercial_closure_id=commercial_closure_id, customer_reference=customer_reference,
            recorded_by_operator_id=recorded_by_operator_id, review_status="OUTCOME_RECORDED",
            satisfaction_rating=satisfaction_rating, delivery_quality_rating=delivery_quality_rating,
            communication_rating=communication_rating, timeliness_rating=timeliness_rating,
            business_outcome_status=business_outcome_status, business_outcome_summary=business_outcome_summary,
            measurable_outcomes=tuple(measurable_outcomes), unresolved_concerns=tuple(unresolved_concerns),
            evidence_references=tuple(evidence_references), metadata=dict(metadata or {}), idempotency_key=key,
            recorded_at=recorded_at, created_at=recorded_at,
        )
    except ValueError as exc:
        return _deny("OUTCOME_REVIEW_VALIDATION", str(exc))
    existing = _outcomes(repo_root).get(record_id)
    if existing:
        return CustomerSuccessResult(True, existing, duplicate_of=record_id) if _same(existing, record) else _deny("CONFLICTING_OUTCOME_REVIEW", "idempotency key already identifies different outcome evidence")
    _append(repo_root, EVT_OUTCOME_RECORDED, record_id, recorded_by_operator_id, recorded_at, record)
    return CustomerSuccessResult(True, record)


def record_portfolio_consent(*, outcome_review_id: str, customer_reference: str, consent_status: str, consent_scope: str, allowed_artifact_references: tuple[str, ...], allowed_formats: tuple[str, ...], allowed_usage_contexts: tuple[str, ...], brand_name_usage: bool, logo_usage: bool, customer_name_usage: bool, performance_metric_usage: bool, anonymization_required: bool, anonymization_rules: tuple[str, ...], recorded_by_operator_id: str, consent_basis: str, repo_root: Any, attribution_requirement: str | None = None, valid_from: str = "t", expires_at: str | None = None, evidence_references: tuple[str, ...] = (), idempotency_key: str = "", created_at: str = "t") -> CustomerSuccessResult:
    outcome = _outcomes(repo_root).get(outcome_review_id)
    if not outcome:
        return _deny("OUTCOME_REVIEW_NOT_FOUND", "portfolio consent requires recorded outcome evidence")
    if not set(allowed_artifact_references).issubset({outcome.revised_delivery_id}):
        return _deny("ARTIFACT_OUTSIDE_DELIVERED_LINEAGE", "portfolio artifacts must be the delivered lineage reference")
    key = idempotency_key or stable_id("portfolio-key", {"outcome": outcome_review_id, "scope": consent_scope})
    record_id = stable_id("scos-hvs-portfolio-consent", {"outcome_review_id": outcome_review_id, "idempotency_key": key})
    try:
        record = PortfolioConsent(record_id, outcome_review_id, outcome.project_id, outcome.revised_delivery_id, customer_reference, consent_status, consent_scope, tuple(allowed_artifact_references), tuple(allowed_formats), tuple(allowed_usage_contexts), brand_name_usage, logo_usage, customer_name_usage, performance_metric_usage, anonymization_required, tuple(anonymization_rules), attribution_requirement, valid_from, expires_at, recorded_by_operator_id, consent_basis, tuple(evidence_references), key, created_at)
    except ValueError as exc:
        return _deny("PORTFOLIO_CONSENT_VALIDATION", str(exc))
    existing = _portfolio_consents(repo_root).get(record_id)
    if existing:
        return CustomerSuccessResult(True, existing, duplicate_of=record_id) if _same(existing, record) else _deny("CONFLICTING_PORTFOLIO_CONSENT", "idempotency key already identifies different consent evidence")
    _append(repo_root, EVT_PORTFOLIO_CONSENT_RECORDED, record_id, recorded_by_operator_id, created_at, record)
    return CustomerSuccessResult(True, record)


def record_testimonial_consent(*, outcome_review_id: str, customer_reference: str, testimonial_reference: str, testimonial_text_hash: str, consent_status: str, approved_usage_contexts: tuple[str, ...], approved_edits: tuple[str, ...], anonymization_required: bool, recorded_by_operator_id: str, consent_basis: str, repo_root: Any, testimonial_text_preview: str | None = None, attribution_name: str | None = None, attribution_role: str | None = None, attribution_company: str | None = None, valid_from: str = "t", expires_at: str | None = None, evidence_references: tuple[str, ...] = (), idempotency_key: str = "", created_at: str = "t") -> CustomerSuccessResult:
    outcome = _outcomes(repo_root).get(outcome_review_id)
    if not outcome:
        return _deny("OUTCOME_REVIEW_NOT_FOUND", "testimonial consent requires recorded outcome evidence")
    key = idempotency_key or stable_id("testimonial-key", {"outcome": outcome_review_id, "reference": testimonial_reference})
    record_id = stable_id("scos-hvs-testimonial-consent", {"outcome_review_id": outcome_review_id, "idempotency_key": key})
    try:
        record = TestimonialConsent(record_id, outcome_review_id, outcome.project_id, customer_reference, testimonial_reference, testimonial_text_hash, testimonial_text_preview, consent_status, tuple(approved_usage_contexts), tuple(approved_edits), attribution_name, attribution_role, attribution_company, anonymization_required, valid_from, expires_at, recorded_by_operator_id, consent_basis, tuple(evidence_references), key, created_at)
    except ValueError as exc:
        return _deny("TESTIMONIAL_CONSENT_VALIDATION", str(exc))
    existing = _testimonial_consents(repo_root).get(record_id)
    if existing:
        return CustomerSuccessResult(True, existing, duplicate_of=record_id) if _same(existing, record) else _deny("CONFLICTING_TESTIMONIAL_CONSENT", "idempotency key already identifies different consent evidence")
    _append(repo_root, EVT_TESTIMONIAL_CONSENT_RECORDED, record_id, recorded_by_operator_id, created_at, record)
    return CustomerSuccessResult(True, record)


def revoke_consent(*, consent_type: str, consent_id: str, revoked_by_operator_id: str, revocation_reason: str, repo_root: Any, evidence_references: tuple[str, ...] = (), idempotency_key: str = "", created_at: str = "t") -> CustomerSuccessResult:
    if consent_type == "PORTFOLIO":
        exists = consent_id in _portfolio_consents(repo_root)
    elif consent_type == "TESTIMONIAL":
        exists = consent_id in _testimonial_consents(repo_root)
    else:
        return _deny("CONSENT_TYPE_INVALID", "consent_type must be PORTFOLIO or TESTIMONIAL")
    if not exists:
        return _deny("CONSENT_NOT_FOUND", "consent evidence was not found")
    key = idempotency_key or stable_id("revocation-key", {"type": consent_type, "consent": consent_id})
    record_id = stable_id("scos-hvs-consent-revocation", {"consent_id": consent_id, "idempotency_key": key})
    try:
        record = ConsentRevocation(record_id, consent_type, consent_id, revoked_by_operator_id, revocation_reason, tuple(evidence_references), key, created_at)
    except ValueError as exc:
        return _deny("CONSENT_REVOCATION_VALIDATION", str(exc))
    existing = _revocations(repo_root).get(consent_id)
    if existing:
        return CustomerSuccessResult(True, existing, duplicate_of=existing.revocation_id) if _same(existing, record) else _deny("CONFLICTING_CONSENT_REVOCATION", "consent already has different revocation evidence")
    _append(repo_root, EVT_CONSENT_REVOKED, record_id, revoked_by_operator_id, created_at, record)
    return CustomerSuccessResult(True, record)


def create_opportunity(*, opportunity_type: str, commercial_closure_id: str, outcome_review_id: str, customer_reference: str, opportunity_summary: str, confidence_level: int, urgency: str, created_by_operator_id: str, repo_root: Any, source_issue_ids: tuple[str, ...] = (), source_evidence_references: tuple[str, ...] = (), recommended_offer: str | None = None, estimated_value: Any = None, currency: str | None = None, target_follow_up_date: str | None = None, assigned_operator_id: str | None = None, idempotency_key: str = "", created_at: str = "t") -> CustomerSuccessResult:
    closure = _require_closed_lineage(repo_root, commercial_closure_id)
    if isinstance(closure, CustomerSuccessResult):
        return closure
    outcome = _outcomes(repo_root).get(outcome_review_id)
    if not outcome or outcome.commercial_closure_id != commercial_closure_id:
        return _deny("OUTCOME_LINEAGE_INVALID", "opportunity outcome must belong to the commercial closure")
    key = idempotency_key or stable_id("opportunity-key", {"closure": commercial_closure_id, "outcome": outcome_review_id, "type": opportunity_type})
    record_id = stable_id("scos-hvs-opportunity", {"commercial_closure_id": commercial_closure_id, "idempotency_key": key})
    try:
        money = normalize_money(estimated_value, field="estimated_value")
        cur = normalize_currency(currency, required=money is not None)
        priority = evaluate_opportunity_priority(
            satisfaction_rating=outcome.satisfaction_rating, delivery_quality_rating=outcome.delivery_quality_rating,
            business_outcome_status=outcome.business_outcome_status, estimated_value=money or "0",
            urgency=urgency, confidence_level=confidence_level, unresolved_concerns=outcome.unresolved_concerns,
            unresolved_dispute=False, active_support_issue=False,
        )
        record = Opportunity(record_id, opportunity_type, closure.project_id, customer_reference, commercial_closure_id, outcome_review_id, tuple(source_issue_ids), tuple(source_evidence_references), IDENTIFIED, opportunity_summary, recommended_offer, money, cur, confidence_level, urgency, target_follow_up_date, priority["score"], priority["score_version"], tuple(priority["scoring_reasons"]), assigned_operator_id, created_by_operator_id, key, created_at)
    except ValueError as exc:
        return _deny("OPPORTUNITY_VALIDATION", str(exc))
    existing = _opportunities(repo_root).get(record_id)
    if existing:
        return CustomerSuccessResult(True, existing, duplicate_of=record_id) if _same(existing, record) else _deny("CONFLICTING_OPPORTUNITY", "idempotency key already identifies different opportunity evidence")
    _append(repo_root, EVT_OPPORTUNITY_IDENTIFIED, record_id, created_by_operator_id, created_at, record)
    return CustomerSuccessResult(True, record)


def qualify_opportunity(*, opportunity_id: str, status: str, confirmed_by_operator_id: str, reason: str, repo_root: Any, operator_confirmation: bool = False, idempotency_key: str = "", created_at: str = "t") -> CustomerSuccessResult:
    if status not in ALLOWED_OPPORTUNITY_STATUSES:
        return _deny("OPPORTUNITY_STATUS_INVALID", "status is not a valid opportunity status")
    if status == CONVERTED and not operator_confirmation:
        return _deny("CONVERSION_REQUIRES_OPERATOR_CONFIRMATION", "converted status requires explicit operator confirmation")
    if opportunity_id not in _opportunities(repo_root):
        return _deny("OPPORTUNITY_NOT_FOUND", "opportunity evidence was not found")
    key = idempotency_key or stable_id("qualification-key", {"opportunity": opportunity_id, "status": status})
    record_id = stable_id("scos-hvs-opportunity-qualification", {"opportunity_id": opportunity_id, "idempotency_key": key})
    try:
        record = OpportunityQualification(record_id, opportunity_id, status, confirmed_by_operator_id, reason, key, created_at)
    except ValueError as exc:
        return _deny("OPPORTUNITY_QUALIFICATION_VALIDATION", str(exc))
    existing = _qualifications(repo_root).get(opportunity_id)
    if existing:
        return CustomerSuccessResult(True, existing, duplicate_of=existing.qualification_id) if _same(existing, record) else _deny("CONFLICTING_OPPORTUNITY_QUALIFICATION", "opportunity already has different qualification evidence")
    _append(repo_root, EVT_OPPORTUNITY_QUALIFIED, record_id, confirmed_by_operator_id, created_at, record)
    return CustomerSuccessResult(True, record)


def portfolio_readiness(*, portfolio_consent_id: str, repo_root: Any, as_of: str) -> dict[str, Any]:
    consent = _portfolio_consents(repo_root).get(portfolio_consent_id)
    if not consent:
        return {"portfolio_ready": False, "blocking_reasons": ["CONSENT_NOT_FOUND"], "manual_review_required": True, "automation_allowed": False}
    blockers: list[str] = []
    if consent.consent_status != CONSENT_GRANTED:
        blockers.append("CONSENT_NOT_GRANTED")
    if portfolio_consent_id in _revocations(repo_root):
        blockers.append("CONSENT_REVOKED")
    if consent.expires_at and consent.expires_at < as_of:
        blockers.append("CONSENT_EXPIRED")
    return {"portfolio_ready": not blockers, "consent_status": CONSENT_REVOKED if "CONSENT_REVOKED" in blockers else consent.consent_status, "allowed_artifacts": list(consent.allowed_artifact_references), "allowed_contexts": list(consent.allowed_usage_contexts), "identity_usage": {"brand_name": consent.brand_name_usage, "logo": consent.logo_usage, "customer_name": consent.customer_name_usage, "performance_metric": consent.performance_metric_usage}, "anonymization_required": consent.anonymization_required, "attribution_requirement": consent.attribution_requirement, "blocking_reasons": blockers, "manual_review_required": True, "automation_allowed": False}


def testimonial_readiness(*, testimonial_consent_id: str, testimonial_text_hash: str, repo_root: Any, as_of: str, requested_edit: str | None = None) -> dict[str, Any]:
    consent = _testimonial_consents(repo_root).get(testimonial_consent_id)
    if not consent:
        return {"testimonial_ready": False, "blocking_reasons": ["CONSENT_NOT_FOUND"], "manual_review_required": True, "automation_allowed": False}
    blockers: list[str] = []
    match = consent.testimonial_text_hash == testimonial_text_hash
    if not match:
        blockers.append("TESTIMONIAL_HASH_MISMATCH")
    if requested_edit and requested_edit not in consent.approved_edits:
        blockers.append("EDIT_NOT_APPROVED")
    if consent.consent_status != CONSENT_GRANTED:
        blockers.append("CONSENT_NOT_GRANTED")
    if testimonial_consent_id in _revocations(repo_root):
        blockers.append("CONSENT_REVOKED")
    if consent.expires_at and consent.expires_at < as_of:
        blockers.append("CONSENT_EXPIRED")
    return {"testimonial_ready": not blockers, "consent_status": CONSENT_REVOKED if "CONSENT_REVOKED" in blockers else consent.consent_status, "text_hash_match": match, "approved_contexts": list(consent.approved_usage_contexts), "attribution_rules": {"name": consent.attribution_name, "role": consent.attribution_role, "company": consent.attribution_company}, "anonymization_required": consent.anonymization_required, "blocking_reasons": blockers, "manual_review_required": True, "automation_allowed": False}


def opportunity_readiness(*, opportunity_id: str, repo_root: Any) -> dict[str, Any]:
    opportunity = _opportunities(repo_root).get(opportunity_id)
    if not opportunity:
        return {"opportunity_eligible": False, "blockers": ["OPPORTUNITY_NOT_FOUND"], "automation_allowed": False}
    qualification = _qualifications(repo_root).get(opportunity_id)
    status = qualification.status if qualification else opportunity.opportunity_status
    closure = _commercial_closure(repo_root, opportunity.commercial_closure_id)
    blockers = [] if status not in (CANCELLED, DECLINED, SUPERSEDED, CONVERTED) else ["OPPORTUNITY_TERMINAL"]
    if closure is None:
        blockers.append("COMMERCIAL_CLOSURE_NOT_FOUND")
    elif _has_unresolved_dispute(repo_root, closure):
        blockers.append("UNRESOLVED_DISPUTE")
    return {"opportunity_eligible": not blockers, "opportunity_type": opportunity.opportunity_type, "priority": {"score": opportunity.priority_score, "band": HIGH if (opportunity.priority_score or 0) >= 75 else MEDIUM if (opportunity.priority_score or 0) >= 45 else LOW}, "blockers": blockers, "next_manual_action": "REVIEW_AND_CONTACT_MANUALLY" if not blockers else "NO_ACTION", "automation_allowed": False}


def list_manual_follow_up_queue(*, repo_root: Any, as_of: str) -> list[dict[str, Any]]:
    qualifications = _qualifications(repo_root)
    items: list[dict[str, Any]] = []
    opportunities = _opportunities(repo_root)
    outcomes = _outcomes(repo_root)
    for opportunity in opportunities.values():
        status = qualifications[opportunity.opportunity_id].status if opportunity.opportunity_id in qualifications else opportunity.opportunity_status
        if opportunity.opportunity_type == NO_OPPORTUNITY or status in (CANCELLED, DECLINED, SUPERSEDED, CONVERTED):
            continue
        due = opportunity.target_follow_up_date
        score = opportunity.priority_score or 0
        if due is None:
            due_state, days = "UNSCHEDULED", None
        else:
            days = (date.fromisoformat(due) - date.fromisoformat(as_of)).days
            due_state = "OVERDUE" if days < 0 else "DUE_SOON" if days <= 7 else "FUTURE"
        items.append({"queue_item_id": stable_id("scos-hvs-follow-up", {"opportunity_id": opportunity.opportunity_id}), "item_type": "OPPORTUNITY", "opportunity_id": opportunity.opportunity_id, "customer_reference": opportunity.customer_reference, "project_id": opportunity.project_id, "opportunity_type": opportunity.opportunity_type, "priority_score": opportunity.priority_score, "priority_band": HIGH if score >= 75 else MEDIUM if score >= 45 else LOW, "target_follow_up_date": due, "days_until_due": days, "due_state": due_state, "overdue": due_state == "OVERDUE", "blocking_reasons": [], "recommended_manual_action": "REVIEW_AND_CONTACT_MANUALLY", "automation_allowed": False})
    portfolio_by_outcome = {item.outcome_review_id for item in _portfolio_consents(repo_root).values()}
    testimonial_by_outcome = {item.outcome_review_id for item in _testimonial_consents(repo_root).values()}
    for outcome in outcomes.values():
        if outcome.outcome_review_id not in portfolio_by_outcome or outcome.outcome_review_id not in testimonial_by_outcome:
            items.append({"queue_item_id": stable_id("scos-hvs-consent-review", {"outcome_review_id": outcome.outcome_review_id}), "item_type": "MISSING_CONSENT_REVIEW", "opportunity_id": None, "customer_reference": outcome.customer_reference, "project_id": outcome.project_id, "opportunity_type": None, "priority_score": None, "priority_band": INSUFFICIENT_EVIDENCE, "target_follow_up_date": None, "days_until_due": None, "due_state": "UNSCHEDULED", "overdue": False, "blocking_reasons": ["PORTFOLIO_OR_TESTIMONIAL_CONSENT_MISSING"], "recommended_manual_action": "RECORD_EXPLICIT_CONSENT_DECISION", "automation_allowed": False})
        if outcome.unresolved_concerns:
            items.append({"queue_item_id": stable_id("scos-hvs-outcome-review", {"outcome_review_id": outcome.outcome_review_id}), "item_type": "UNRESOLVED_OUTCOME_REVIEW", "opportunity_id": None, "customer_reference": outcome.customer_reference, "project_id": outcome.project_id, "opportunity_type": None, "priority_score": None, "priority_band": INSUFFICIENT_EVIDENCE, "target_follow_up_date": None, "days_until_due": None, "due_state": "UNSCHEDULED", "overdue": False, "blocking_reasons": ["UNRESOLVED_CONCERNS"], "recommended_manual_action": "REVIEW_CUSTOMER_OUTCOME_MANUALLY", "automation_allowed": False})
    for consent in (*_portfolio_consents(repo_root).values(), *_testimonial_consents(repo_root).values()):
        expires_at = consent.expires_at
        if expires_at and 0 <= (date.fromisoformat(expires_at) - date.fromisoformat(as_of)).days <= 7:
            consent_id = getattr(consent, "portfolio_consent_id", None) or getattr(consent, "testimonial_consent_id")
            items.append({"queue_item_id": stable_id("scos-hvs-expiring-consent", {"consent_id": consent_id}), "item_type": "EXPIRING_CONSENT_REVIEW", "opportunity_id": None, "customer_reference": consent.customer_reference, "project_id": consent.project_id, "opportunity_type": None, "priority_score": None, "priority_band": MEDIUM, "target_follow_up_date": expires_at, "days_until_due": (date.fromisoformat(expires_at) - date.fromisoformat(as_of)).days, "due_state": "DUE_SOON", "overdue": False, "blocking_reasons": ["CONSENT_EXPIRING"], "recommended_manual_action": "REVIEW_CONSENT_EXPIRY_MANUALLY", "automation_allowed": False})
    return sorted(items, key=lambda item: (item["item_type"] != "MISSING_CONSENT_REVIEW", item["due_state"] != "OVERDUE", item["target_follow_up_date"] or "9999-12-31", -int(item["priority_score"] or 0), item["queue_item_id"]))


def inspect_customer_success_lineage(*, project_id: str | None, repo_root: Any) -> dict[str, Any]:
    outcomes = [record.to_dict() for record in _outcomes(repo_root).values() if project_id is None or record.project_id == project_id]
    portfolios = [record.to_dict() for record in _portfolio_consents(repo_root).values() if project_id is None or record.project_id == project_id]
    testimonials = [record.to_dict() for record in _testimonial_consents(repo_root).values() if project_id is None or record.project_id == project_id]
    opportunities = [record.to_dict() for record in _opportunities(repo_root).values() if project_id is None or record.project_id == project_id]
    return {"project_id": project_id, "outcome_reviews": outcomes, "portfolio_consents": portfolios, "testimonial_consents": testimonials, "consent_revocations": [record.to_dict() for record in _revocations(repo_root).values()], "opportunities": opportunities, "qualifications": [record.to_dict() for record in _qualifications(repo_root).values()], "automation_allowed": False}


def evaluate_opportunity_priority(**inputs):
    """Return a versioned, pure priority decision from explicit inputs.

    The calculation deliberately does not infer satisfaction or intent.  A
    missing required rating is insufficient evidence; an unresolved dispute is
    a hard block regardless of the otherwise positive evidence.
    """
    required = ("satisfaction_rating", "delivery_quality_rating", "business_outcome_status", "urgency", "confidence_level")
    missing = tuple(field for field in required if inputs.get(field) is None)
    if missing:
        return {
            "score": None,
            "score_version": PRIORITY_SCORE_VERSION,
            "priority_band": INSUFFICIENT_EVIDENCE,
            "scoring_reasons": (),
            "blocking_reasons": tuple("MISSING_" + field.upper() for field in missing),
            "recommended_manual_action": "RECORD_MISSING_OUTCOME_EVIDENCE",
            "automation_allowed": False,
        }
    if inputs.get("unresolved_dispute"):
        return {
            "score": 0,
            "score_version": PRIORITY_SCORE_VERSION,
            "priority_band": BLOCKED,
            "scoring_reasons": (),
            "blocking_reasons": ("UNRESOLVED_DISPUTE",),
            "recommended_manual_action": "RESOLVE_DISPUTE_BEFORE_FOLLOW_UP",
            "automation_allowed": False,
        }
    try:
        satisfaction = int(inputs["satisfaction_rating"])
        quality = int(inputs["delivery_quality_rating"])
        confidence = int(inputs["confidence_level"])
    except (TypeError, ValueError) as exc:
        raise ValueError("ratings and confidence_level must be integers") from exc
    if any(value < 1 or value > 5 for value in (satisfaction, quality, confidence)):
        raise ValueError("ratings and confidence_level must be integers from 1 through 5")
    urgency = str(inputs["urgency"])
    if urgency not in ("LOW", "MEDIUM", "HIGH"):
        raise ValueError("urgency must be LOW, MEDIUM, or HIGH")
    outcome = str(inputs["business_outcome_status"])
    outcome_points = {"ACHIEVED": 15, "PARTIALLY_ACHIEVED": 8, "NOT_MEASURED": 0}.get(outcome)
    if outcome_points is None:
        raise ValueError("business_outcome_status must be ACHIEVED, PARTIALLY_ACHIEVED, or NOT_MEASURED")
    try:
        value = Decimal(str(inputs.get("estimated_value") or "0"))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("estimated_value must be a decimal amount") from exc
    if not value.is_finite() or value < 0:
        raise ValueError("estimated_value must be a non-negative finite decimal")
    score = satisfaction * 8 + quality * 5 + confidence * 3 + outcome_points
    reasons = [f"SATISFACTION_{satisfaction}", f"DELIVERY_QUALITY_{quality}", f"CONFIDENCE_{confidence}", "BUSINESS_OUTCOME_" + outcome]
    if value >= Decimal("1000"):
        score += 4
        reasons.append("COMMERCIAL_VALUE_1000_PLUS")
    urgency_points = {"LOW": 0, "MEDIUM": 3, "HIGH": 6}[urgency]
    score += urgency_points
    reasons.append("URGENCY_" + urgency)
    concerns = tuple(inputs.get("unresolved_concerns") or ())
    if concerns:
        score -= min(15, 5 * len(concerns))
        reasons.append("UNRESOLVED_CONCERNS_PENALTY")
    if inputs.get("active_support_issue"):
        score -= 10
        reasons.append("ACTIVE_SUPPORT_ISSUE_PENALTY")
    score = max(0, min(100, score))
    band = HIGH if score >= 75 else MEDIUM if score >= 45 else LOW
    return {
        "score": score,
        "score_version": PRIORITY_SCORE_VERSION,
        "priority_band": band,
        "scoring_reasons": tuple(reasons),
        "blocking_reasons": (),
        "recommended_manual_action": "REVIEW_AND_CONTACT_MANUALLY",
        "automation_allowed": False,
    }
