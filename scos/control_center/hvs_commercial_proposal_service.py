"""Stage 8I local proposal preparation, approval, and manual handoff service."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import Any

from . import hvs_customer_outcome_service as outcomes
from .hvs_commercial_proposal_models import *
from .hvs_commercial_proposal_models import _safe_text
from .hvs_commercial_proposal_store import commercial_proposal_path, read_commercial_proposal_events, append_commercial_proposal_event
from .hvs_delivery_lineage_models import DeliveryLineageRecord, EVT_LINEAGE_REGISTERED, LINEAGE_REGISTERED
from .hvs_delivery_lineage_store import lineage_audit_path, read_lineage_events
from .hvs_invoice_models import normalize_currency, normalize_money, quantize_money


@dataclass(frozen=True)
class ProposalServiceResult:
    ok: bool
    proposal: ProposalPreparation | None = None
    readiness: ProposalReadinessResult | None = None
    handoff: CommercialHandoffPackage | None = None
    eligibility: Any = None
    duplicate_of: str | None = None
    error_code: str | None = None
    error_detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "proposal": self.proposal.to_dict() if self.proposal else None, "readiness": self.readiness.to_dict() if self.readiness else None, "handoff": self.handoff.to_dict() if self.handoff else None, "eligibility": self.eligibility.to_dict() if hasattr(self.eligibility, "to_dict") else self.eligibility, "duplicate_of": self.duplicate_of, "error_code": self.error_code, "error_detail": self.error_detail, "automation_allowed": False, "proposal_sent": False, "customer_contacted": False, "hvs_invoked": False}


@dataclass(frozen=True)
class ProposalEligibilityResult:
    eligible: bool
    blockers: tuple[str, ...]
    opportunity: Any = None
    lineage: DeliveryLineageRecord | None = None
    def to_dict(self): return {"eligible": self.eligible, "blockers": list(self.blockers), "automation_allowed": False}


def _deny(code: str, detail: str, **kwargs) -> ProposalServiceResult: return ProposalServiceResult(False, error_code=code, error_detail=detail, **kwargs)


def _records(repo: Path) -> dict[str, ProposalPreparation]:
    records = {}
    for event in read_commercial_proposal_events(audit_log_path=commercial_proposal_path(repo)):
        if event.event_type != EVT_MANUAL_HANDOFF_CREATED:
            records[event.record["proposal_preparation_id"]] = proposal_from_dict(event.record)
    return records


def _handoffs(repo: Path) -> dict[str, CommercialHandoffPackage]:
    result = {}
    for event in read_commercial_proposal_events(audit_log_path=commercial_proposal_path(repo)):
        if event.event_type == EVT_MANUAL_HANDOFF_CREATED:
            data = dict(event.record); data["total_amount"] = Decimal(str(data["total_amount"])); data["source_lineage"] = dict(data["source_lineage"])
            result[data["proposal_preparation_id"]] = CommercialHandoffPackage(**data)
    return result


def _lineage(repo: Path, lineage_id: str) -> DeliveryLineageRecord | None:
    for event in read_lineage_events(audit_log_path=lineage_audit_path(repo)):
        if event.event_type == EVT_LINEAGE_REGISTERED and event.record:
            record = DeliveryLineageRecord(**event.record)
            if record.lineage_id == lineage_id: return record
    return None


def evaluate_opportunity_eligibility(*, opportunity_id: str, delivery_lineage_id: str, repo_root: Any, commercial_recipient_reference: str | None = None) -> ProposalEligibilityResult:
    repo = Path(repo_root); blockers = []
    opportunity = outcomes._opportunities(repo).get(opportunity_id)
    if not opportunity: return ProposalEligibilityResult(False, ("OPPORTUNITY_NOT_FOUND",))
    qualification = outcomes._qualifications(repo).get(opportunity_id)
    if not qualification or qualification.status != "QUALIFIED": blockers.append("OPPORTUNITY_NOT_QUALIFIED")
    if opportunity.opportunity_type not in ("RENEWAL", "FOLLOW_ON_PROJECT", "UPSELL", "REFERRAL"): blockers.append("OPPORTUNITY_TYPE_NOT_COMMERCIAL")
    if opportunity.opportunity_type == "REFERRAL" and not commercial_recipient_reference: blockers.append("REFERRAL_RECIPIENT_REQUIRED")
    closure = outcomes._commercial_closure(repo, opportunity.commercial_closure_id)
    if not closure or closure.closure_status != "COMMERCIALLY_CLOSED": blockers.append("COMMERCIAL_CLOSURE_INVALID")
    elif outcomes._has_unresolved_dispute(repo, closure): blockers.append("UNRESOLVED_DISPUTE")
    outcome = outcomes._outcomes(repo).get(opportunity.outcome_review_id)
    if not outcome or outcome.unresolved_concerns: blockers.append("UNRESOLVED_CUSTOMER_CONCERNS")
    priority = outcomes.evaluate_opportunity_priority(satisfaction_rating=getattr(outcome, "satisfaction_rating", None), delivery_quality_rating=getattr(outcome, "delivery_quality_rating", None), business_outcome_status=getattr(outcome, "business_outcome_status", None), urgency=opportunity.urgency, confidence_level=opportunity.confidence_level, unresolved_concerns=getattr(outcome, "unresolved_concerns", ()), unresolved_dispute=bool(closure and outcomes._has_unresolved_dispute(repo, closure)), active_support_issue=False)
    if priority["priority_band"] in ("BLOCKED", "INSUFFICIENT_EVIDENCE"): blockers.append("PRIORITY_" + priority["priority_band"])
    lineage = _lineage(repo, delivery_lineage_id)
    if not lineage or lineage.lineage_status != LINEAGE_REGISTERED: blockers.append("DELIVERY_LINEAGE_INVALID")
    elif lineage.project_id != opportunity.project_id or len(lineage.artifact_sha256) != 64: blockers.append("DELIVERY_LINEAGE_MISMATCH")
    return ProposalEligibilityResult(not blockers, tuple(sorted(set(blockers))), opportunity, lineage)


def _build_deliverables(items, evidence):
    if not isinstance(items, (tuple, list)):
        raise ValueError("deliverables must be a list of objects")
    result = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("deliverables must contain objects")
        desc = _safe_text("deliverable description", item.get("description")); unit = _safe_text("deliverable unit", item.get("unit")); ref = _safe_text("deliverable evidence_reference", item.get("evidence_reference"))
        if ref not in evidence: raise ValueError("deliverable evidence_reference is not in opportunity evidence")
        qty = normalize_money(item.get("quantity"), field="deliverable quantity", min_value=Decimal("0"))
        if qty <= 0: raise ValueError("deliverable quantity must be positive")
        result.append(ProposalDeliverable(desc, qty, unit, ref))
    return tuple(result)


def _build_lines(items, currency):
    if not isinstance(items, (tuple, list)):
        raise ValueError("line_items must be a list of objects")
    result = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("line_items must contain objects")
        desc = _safe_text("line item description", item.get("description")); scope = _safe_text("line item scope_key", item.get("scope_key")); qty = normalize_money(item.get("quantity"), field="line item quantity", min_value=Decimal("0")); price = normalize_money(item.get("unit_price"), field="line item unit_price", min_value=Decimal("0"))
        if qty <= 0: raise ValueError("line item quantity must be positive")
        total = quantize_money(qty * price, currency)
        if item.get("line_total") is not None and normalize_money(item["line_total"], field="line_total", min_value=Decimal("0")) != total: raise ValueError("line_total must equal quantity times unit_price")
        result.append(ProposalLineItem(stable_id("scos-hvs-proposal-line", {"description": desc, "quantity": str(qty), "unit_price": str(price), "scope": scope}), desc, qty, price, total, scope))
    return tuple(result)


def create_proposal_preparation(*, opportunity_id: str, delivery_lineage_id: str, repo_root: Any, title: str, objective: str, scope_summary: str, deliverables: tuple[dict[str, Any], ...], exclusions: tuple[str, ...], assumptions: tuple[str, ...], line_items: tuple[dict[str, Any], ...], currency: str, tax_amount: Any, tax_treatment: str, discount_amount: Any, payment_terms: str, revision_terms: str, validity_start_date: str, validity_end_date: str, operator_id: str, recorded_at: str, estimated_start_date: str | None = None, estimated_completion_date: str | None = None, dependency_notes: tuple[str, ...] = (), risk_notes: tuple[str, ...] = (), commercial_recipient_reference: str | None = None) -> ProposalServiceResult:
    repo = Path(repo_root)
    try:
        commercial_recipient_reference = _safe_text("commercial_recipient_reference", commercial_recipient_reference, required=False) or None
    except ValueError as exc:
        return _deny("INVALID_INPUT", str(exc))
    eligibility = evaluate_opportunity_eligibility(opportunity_id=opportunity_id, delivery_lineage_id=delivery_lineage_id, repo_root=repo, commercial_recipient_reference=commercial_recipient_reference)
    if not eligibility.eligible: return _deny("OPPORTUNITY_INELIGIBLE", ",".join(eligibility.blockers), eligibility=eligibility)
    try:
        cur = normalize_currency(currency); title = _safe_text("title", title); objective = _safe_text("objective", objective); scope = _safe_text("scope_summary", scope_summary); terms = _safe_text("payment_terms", payment_terms); revisions = _safe_text("revision_terms", revision_terms); treatment = _safe_text("tax_treatment", tax_treatment); operator_id = _safe_text("operator_id", operator_id); recorded_at = validate_calendar_date("recorded_at", recorded_at)
        start = validate_calendar_date("validity_start_date", validity_start_date); end = validate_calendar_date("validity_end_date", validity_end_date)
        if end < start: raise ValueError("validity_end_date precedes validity_start_date")
        for value in (estimated_start_date, estimated_completion_date):
            if value: validate_calendar_date("estimated date", value)
        if estimated_start_date and estimated_completion_date and estimated_completion_date < estimated_start_date:
            raise ValueError("estimated_completion_date precedes estimated_start_date")
        deliverable_values = _build_deliverables(deliverables, eligibility.opportunity.source_evidence_references)
        if not deliverable_values: raise ValueError("at least one deliverable is required")
        if not isinstance(exclusions, (tuple, list)) or not isinstance(assumptions, (tuple, list)):
            raise ValueError("exclusions and assumptions must be lists of strings")
        exclusions = tuple(_safe_text("exclusion", x) for x in exclusions); assumptions = tuple(_safe_text("assumption", x) for x in assumptions)
        if not exclusions or not assumptions: raise ValueError("explicit exclusions and assumptions are required")
        lines = _build_lines(line_items, cur); tax = quantize_money(normalize_money(tax_amount, field="tax_amount", min_value=Decimal("0")), cur); discount = quantize_money(normalize_money(discount_amount, field="discount_amount", min_value=Decimal("0")), cur)
        subtotal = quantize_money(sum((line.line_total for line in lines), Decimal("0")), cur); total = quantize_money(subtotal - discount + tax, cur)
        if discount > subtotal or total < 0: raise ValueError("discount or total is invalid")
    except ValueError as exc: return _deny("INVALID_INPUT", str(exc))
    opportunity, lineage = eligibility.opportunity, eligibility.lineage
    scope_id = stable_id("scos-hvs-commercial-scope", {"opportunity": opportunity_id, "customer": commercial_recipient_reference or opportunity.customer_reference, "lineage": lineage.lineage_id})
    dependency_notes = tuple(_safe_text("dependency_note", x) for x in dependency_notes)
    risk_notes = tuple(_safe_text("risk_note", x) for x in risk_notes)
    semantics = {"scope": scope, "title": title, "objective": objective, "deliverables": [x.to_dict() for x in deliverable_values], "exclusions": exclusions, "assumptions": assumptions, "lines": [x.to_dict(currency=cur) for x in lines], "currency": cur, "tax": str(tax), "tax_treatment": treatment, "discount": str(discount), "payment_terms": terms, "revision_terms": revisions, "validity": (start, end), "estimated_dates": (estimated_start_date, estimated_completion_date), "dependency_notes": dependency_notes, "risk_notes": risk_notes}
    content_hash = hashlib.sha256(canonical_json(semantics).encode("utf-8")).hexdigest()
    proposal_id = stable_id("scos-hvs-proposal", {"commercial_scope_id": scope_id, "content_hash": content_hash})
    existing = next((value for value in _records(repo).values() if value.commercial_scope_id == scope_id), None)
    if existing:
        if existing.proposal_preparation_id == proposal_id: return ProposalServiceResult(True, proposal=existing, duplicate_of=proposal_id)
        return _deny("CONFLICTING_COMMERCIAL_SCOPE", "commercial scope already has different proposal content", proposal=existing)
    proposal = ProposalPreparation(COMMERCIAL_PROPOSAL_SCHEMA_VERSION, proposal_id, scope_id, opportunity.project_id, commercial_recipient_reference or opportunity.customer_reference, opportunity_id, opportunity.opportunity_type, opportunity.outcome_review_id, lineage.lineage_id, lineage.delivery_record_id, lineage.artifact_id, lineage.artifact_sha256, opportunity.commercial_closure_id, DRAFT, title, objective, scope, deliverable_values, exclusions, assumptions, lines, subtotal, discount, tax, total, cur, treatment, start, end, estimated_start_date, estimated_completion_date, terms, revisions, dependency_notes, risk_notes, True, True, False, content_hash, recorded_at, recorded_at)
    append_commercial_proposal_event(audit_log_path=commercial_proposal_path(repo), event_type=EVT_PROPOSAL_PREPARED, subject_id=proposal_id, operator_id=operator_id, recorded_at=recorded_at, record=proposal.to_dict())
    return ProposalServiceResult(True, proposal=proposal, eligibility=eligibility)


def inspect_proposal_preparation(*, proposal_preparation_id: str, repo_root: Any) -> ProposalServiceResult:
    proposal = _records(Path(repo_root)).get(proposal_preparation_id)
    return ProposalServiceResult(True, proposal=proposal) if proposal else _deny("PROPOSAL_NOT_FOUND", "proposal preparation not found")


def evaluate_proposal_readiness(*, proposal_preparation_id: str, repo_root: Any, as_of: str) -> ProposalReadinessResult:
    proposal = _records(Path(repo_root)).get(proposal_preparation_id)
    if not proposal: return ProposalReadinessResult(proposal_preparation_id, READINESS_BLOCKED, ("PROPOSAL_NOT_FOUND",), (), "CREATE_A_VALID_PROPOSAL")
    try:
        as_of = validate_calendar_date("as_of", as_of)
    except ValueError:
        return ProposalReadinessResult(proposal_preparation_id, READINESS_BLOCKED, ("INVALID_AS_OF_DATE",), (), "SUPPLY_A_VALID_AS_OF_DATE")
    if as_of < proposal.validity_start_date: return ProposalReadinessResult(proposal_preparation_id, READINESS_BLOCKED, ("PROPOSAL_NOT_YET_VALID",), (), "WAIT_OR_PREPARE_A_VALID_PROPOSAL")
    if as_of > proposal.validity_end_date: return ProposalReadinessResult(proposal_preparation_id, READINESS_EXPIRED, ("PROPOSAL_EXPIRED",), (), "PREPARE_A_NEW_PROPOSAL")
    eligibility = evaluate_opportunity_eligibility(opportunity_id=proposal.opportunity_id, delivery_lineage_id=proposal.source_delivery_lineage_id, repo_root=repo_root)
    if not eligibility.eligible: return ProposalReadinessResult(proposal_preparation_id, READINESS_BLOCKED, eligibility.blockers, (), "RESOLVE_SOURCE_BLOCKERS")
    needs = []
    if not proposal.line_items: needs.append("LINE_ITEMS_REQUIRED")
    if not proposal.tax_treatment: needs.append("TAX_TREATMENT_REQUIRED")
    return ProposalReadinessResult(proposal_preparation_id, READINESS_NEEDS_OPERATOR_INPUT if needs else READY, tuple(needs), (), "COMPLETE_COMMERCIAL_INPUT" if needs else "SUBMIT_FOR_INTERNAL_REVIEW")


def _transition(*, proposal_preparation_id, repo_root, operator_id, recorded_at, target, event_type, reason=None, as_of=None):
    repo = Path(repo_root); proposal = _records(repo).get(proposal_preparation_id)
    if not proposal: return _deny("PROPOSAL_NOT_FOUND", "proposal preparation not found")
    try:
        operator_id = _safe_text("operator_id", operator_id)
        recorded_at = validate_calendar_date("recorded_at", recorded_at)
    except ValueError as exc:
        return _deny("INVALID_INPUT", str(exc), proposal=proposal)
    if proposal.proposal_status in (APPROVED_FOR_MANUAL_PRESENTATION, REJECTED, CANCELLED, EXPIRED): return _deny("INVALID_TRANSITION", "proposal is decided or expired", proposal=proposal)
    readiness = evaluate_proposal_readiness(proposal_preparation_id=proposal_preparation_id, repo_root=repo, as_of=as_of or recorded_at)
    if target == READY_FOR_INTERNAL_REVIEW:
        if proposal.proposal_status != DRAFT: return _deny("INVALID_TRANSITION", "submission requires a draft proposal", proposal=proposal, readiness=readiness)
        if readiness.state != READY: return _deny("READINESS_NOT_READY", "proposal is not ready for review", proposal=proposal, readiness=readiness)
    if target == APPROVED_FOR_MANUAL_PRESENTATION:
        if readiness.state == READINESS_EXPIRED: return _deny("PROPOSAL_EXPIRED", "expired proposal cannot be approved", proposal=proposal, readiness=readiness)
        if proposal.proposal_status != READY_FOR_INTERNAL_REVIEW or readiness.state != READY: return _deny("READINESS_NOT_READY", "approval requires ready internal review", proposal=proposal, readiness=readiness)
    if target in (REJECTED, CANCELLED) and not reason: return _deny("REASON_REQUIRED", "rejection or cancellation requires a reason", proposal=proposal)
    try:
        reason = _safe_text("reason", reason) if reason is not None else None
    except ValueError as exc:
        return _deny("INVALID_INPUT", str(exc), proposal=proposal)
    updated = replace(proposal, proposal_status=target, updated_at=recorded_at, decision_reason=reason)
    append_commercial_proposal_event(audit_log_path=commercial_proposal_path(repo), event_type=event_type, subject_id=proposal_preparation_id, operator_id=operator_id, recorded_at=recorded_at, record=updated.to_dict())
    return ProposalServiceResult(True, proposal=updated, readiness=readiness)


def submit_for_internal_review(*, proposal_preparation_id: str, operator_id: str, repo_root: Any, recorded_at: str) -> ProposalServiceResult:
    return _transition(proposal_preparation_id=proposal_preparation_id, operator_id=operator_id, repo_root=repo_root, recorded_at=recorded_at, target=READY_FOR_INTERNAL_REVIEW, event_type=EVT_PROPOSAL_SUBMITTED)
def approve_for_manual_presentation(*, proposal_preparation_id: str, operator_id: str, repo_root: Any, recorded_at: str, as_of: str) -> ProposalServiceResult:
    return _transition(proposal_preparation_id=proposal_preparation_id, operator_id=operator_id, repo_root=repo_root, recorded_at=recorded_at, target=APPROVED_FOR_MANUAL_PRESENTATION, event_type=EVT_PROPOSAL_APPROVED, as_of=as_of)
def reject_proposal(*, proposal_preparation_id: str, operator_id: str, reason: str, repo_root: Any, recorded_at: str) -> ProposalServiceResult:
    return _transition(proposal_preparation_id=proposal_preparation_id, operator_id=operator_id, repo_root=repo_root, recorded_at=recorded_at, target=REJECTED, event_type=EVT_PROPOSAL_REJECTED, reason=reason)
def cancel_proposal(*, proposal_preparation_id: str, operator_id: str, reason: str, repo_root: Any, recorded_at: str) -> ProposalServiceResult:
    return _transition(proposal_preparation_id=proposal_preparation_id, operator_id=operator_id, repo_root=repo_root, recorded_at=recorded_at, target=CANCELLED, event_type=EVT_PROPOSAL_CANCELLED, reason=reason)


def create_manual_commercial_handoff(*, proposal_preparation_id: str, operator_id: str, repo_root: Any, recorded_at: str) -> ProposalServiceResult:
    repo = Path(repo_root); proposal = _records(repo).get(proposal_preparation_id)
    if not proposal: return _deny("PROPOSAL_NOT_FOUND", "proposal preparation not found")
    try:
        operator_id = _safe_text("operator_id", operator_id)
        recorded_at = validate_calendar_date("recorded_at", recorded_at)
    except ValueError as exc:
        return _deny("INVALID_INPUT", str(exc), proposal=proposal)
    if proposal.proposal_status != APPROVED_FOR_MANUAL_PRESENTATION: return _deny("HANDOFF_REQUIRES_APPROVAL", "proposal must be approved for manual presentation", proposal=proposal)
    existing = _handoffs(repo).get(proposal_preparation_id)
    if existing: return ProposalServiceResult(True, proposal=proposal, handoff=existing, duplicate_of=existing.handoff_id)
    approval = next(event for event in read_commercial_proposal_events(audit_log_path=commercial_proposal_path(repo)) if event.event_type == EVT_PROPOSAL_APPROVED and event.subject_id == proposal_preparation_id)
    handoff = CommercialHandoffPackage(stable_id("scos-hvs-commercial-handoff", {"proposal": proposal_preparation_id, "hash": proposal.deterministic_content_hash, "approval": approval.event_id}), proposal_preparation_id, proposal.commercial_scope_id, proposal.deterministic_content_hash, approval.event_id, {"outcome_review_id": proposal.source_outcome_review_id, "delivery_lineage_id": proposal.source_delivery_lineage_id, "delivery_record_id": proposal.source_delivery_record_id, "artifact_id": proposal.source_artifact_id, "artifact_sha256": proposal.source_artifact_sha256, "commercial_closure_id": proposal.source_commercial_closure_id}, proposal.currency, proposal.total_amount, True, False, False, False, False, False, False, False, False, recorded_at)
    append_commercial_proposal_event(audit_log_path=commercial_proposal_path(repo), event_type=EVT_MANUAL_HANDOFF_CREATED, subject_id=handoff.handoff_id, operator_id=operator_id, recorded_at=recorded_at, record=handoff.to_dict())
    return ProposalServiceResult(True, proposal=proposal, handoff=handoff)


def list_proposal_review_queue(*, repo_root: Any, as_of: str) -> list[dict[str, Any]]:
    """Return deterministic local review work; this never contacts a customer."""
    try:
        as_of = validate_calendar_date("as_of", as_of)
    except ValueError:
        return [{"item_type": "INVALID_AS_OF_DATE", "blocking_reasons": ["INVALID_AS_OF_DATE"], "recommended_manual_action": "SUPPLY_A_VALID_AS_OF_DATE", "automation_allowed": False}]
    items: list[dict[str, Any]] = []
    for proposal in _records(Path(repo_root)).values():
        if proposal.proposal_status not in (DRAFT, READY_FOR_INTERNAL_REVIEW):
            continue
        readiness = evaluate_proposal_readiness(proposal_preparation_id=proposal.proposal_preparation_id, repo_root=repo_root, as_of=as_of)
        action = "APPROVE_OR_REJECT_INTERNAL_REVIEW" if proposal.proposal_status == READY_FOR_INTERNAL_REVIEW and readiness.state == READY else readiness.recommended_manual_action
        items.append({"queue_item_id": stable_id("scos-hvs-commercial-proposal-review", {"proposal_preparation_id": proposal.proposal_preparation_id}), "item_type": "COMMERCIAL_PROPOSAL_REVIEW", "proposal_preparation_id": proposal.proposal_preparation_id, "project_id": proposal.project_id, "customer_reference": proposal.customer_reference, "proposal_status": proposal.proposal_status, "readiness_state": readiness.state, "blocking_reasons": list(readiness.blockers), "warnings": list(readiness.warnings), "validity_end_date": proposal.validity_end_date, "recommended_manual_action": action, "automation_allowed": False})
    return sorted(items, key=lambda item: (item["proposal_status"] != READY_FOR_INTERNAL_REVIEW, item["readiness_state"] != READY, item["validity_end_date"], item["proposal_preparation_id"]))
