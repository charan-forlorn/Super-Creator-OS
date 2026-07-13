"""Stage 8J local proposal presentation, decision, and acceptance service."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from .hvs_commercial_acceptance_models import *
from .hvs_commercial_acceptance_store import (
    append_commercial_acceptance_event,
    commercial_acceptance_path,
    read_commercial_acceptance_events,
)
from .hvs_commercial_proposal_models import (
    APPROVED_FOR_MANUAL_PRESENTATION,
    CANCELLED,
    REJECTED,
    _safe_text,
    stable_id,
)
from .hvs_commercial_proposal_service import _handoffs, _records
from .hvs_customer_outcome_models import validate_calendar_date
from .hvs_invoice_models import normalize_currency, normalize_money, quantize_money


@dataclass(frozen=True)
class CommercialAcceptanceServiceResult:
    ok: bool
    presentation: ProposalPresentationRecord | None = None
    decision: CustomerDecisionRecord | None = None
    acceptance: CommercialAcceptanceRecord | None = None
    readiness: CommercialAcceptanceReadiness | None = None
    duplicate_of: str | None = None
    error_code: str | None = None
    error_detail: str | None = None
    blockers: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "presentation": self.presentation.to_dict() if self.presentation else None,
            "decision": self.decision.to_dict() if self.decision else None,
            "acceptance": self.acceptance.to_dict() if self.acceptance else None,
            "readiness": self.readiness.to_dict() if self.readiness else None,
            "duplicate_of": self.duplicate_of,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
            "blockers": list(self.blockers),
            "invoice_created": False,
            "payment_link_created": False,
            "payment_state_changed": False,
            "project_created": False,
            "hvs_invoked": False,
            "render_started": False,
            "customer_contact_performed_by_system": False,
            "automation_allowed": False,
        }


def _deny(code: str, detail: str, **kwargs: Any) -> CommercialAcceptanceServiceResult:
    return CommercialAcceptanceServiceResult(False, error_code=code, error_detail=detail, **kwargs)


def _events(repo: Path) -> tuple[CommercialAcceptanceEvent, ...]:
    return read_commercial_acceptance_events(audit_log_path=commercial_acceptance_path(repo))


def _presentations(repo: Path) -> dict[str, ProposalPresentationRecord]:
    records: dict[str, ProposalPresentationRecord] = {}
    for event in _events(repo):
        if event.event_type == EVT_PROPOSAL_PRESENTATION_RECORDED:
            record = presentation_from_dict(event.record)
            records[record.presentation_record_id] = record
    return records


def _decisions(repo: Path) -> dict[str, CustomerDecisionRecord]:
    records: dict[str, CustomerDecisionRecord] = {}
    for event in _events(repo):
        if event.event_type == EVT_CUSTOMER_DECISION_RECORDED:
            record = decision_from_dict(event.record)
            records[record.customer_decision_id] = record
    return records


def _acceptances(repo: Path) -> dict[str, CommercialAcceptanceRecord]:
    records: dict[str, CommercialAcceptanceRecord] = {}
    for event in _events(repo):
        if event.event_type == EVT_COMMERCIAL_ACCEPTANCE_VERIFIED:
            record = acceptance_from_dict(event.record)
            records[record.commercial_acceptance_id] = record
    return records


def _same_dict(left: Any, right: Any) -> bool:
    return hasattr(left, "to_dict") and hasattr(right, "to_dict") and left.to_dict() == right.to_dict()


def _optional_text(field: str, value: Any) -> str | None:
    text = _safe_text(field, value, required=False)
    return text or None


def _required_operator(value: Any) -> str:
    return _safe_text("operator_id", value)


def _required_evidence(value: Any) -> str:
    text = _safe_text("evidence_reference", value)
    lowered = text.lower()
    if any(token in lowered for token in ("secret", "token", "password", "apikey", "api_key", "private-message", "raw-message")):
        raise ValueError("evidence_reference must not contain secret or raw private content markers")
    if "://" in text and not text.startswith("evidence-"):
        raise ValueError("evidence_reference must be a safe local evidence reference")
    return text


def _proposal_handoff(repo: Path, proposal_preparation_id: str, handoff_id: str | None = None):
    proposal = _records(repo).get(proposal_preparation_id)
    if not proposal:
        return None, None, ("PROPOSAL_NOT_FOUND",)
    handoff = _handoffs(repo).get(proposal_preparation_id)
    blockers: list[str] = []
    if proposal.proposal_status != APPROVED_FOR_MANUAL_PRESENTATION:
        blockers.append("PROPOSAL_NOT_APPROVED_FOR_MANUAL_PRESENTATION")
    if proposal.proposal_status in (REJECTED, CANCELLED):
        blockers.append("PROPOSAL_TERMINAL")
    if proposal.automation_allowed:
        blockers.append("AUTOMATION_NOT_ALLOWED")
    if not handoff:
        blockers.append("HANDOFF_NOT_FOUND")
    elif handoff_id and handoff.handoff_id != handoff_id:
        blockers.append("HANDOFF_ID_MISMATCH")
    if handoff:
        if handoff.proposal_preparation_id != proposal.proposal_preparation_id:
            blockers.append("HANDOFF_PROPOSAL_MISMATCH")
        if handoff.approved_content_hash != proposal.deterministic_content_hash:
            blockers.append("HANDOFF_CONTENT_HASH_MISMATCH")
        if handoff.commercial_scope_id != proposal.commercial_scope_id:
            blockers.append("HANDOFF_SCOPE_MISMATCH")
        if handoff.currency != proposal.currency or handoff.total_amount != proposal.total_amount:
            blockers.append("HANDOFF_COMMERCIAL_TOTAL_MISMATCH")
        source = dict(handoff.source_lineage)
        if source.get("delivery_lineage_id") != proposal.source_delivery_lineage_id:
            blockers.append("SOURCE_LINEAGE_MISMATCH")
        if source.get("artifact_id") != proposal.source_artifact_id:
            blockers.append("SOURCE_ARTIFACT_MISMATCH")
        if source.get("artifact_sha256") != proposal.source_artifact_sha256:
            blockers.append("SOURCE_ARTIFACT_SHA_MISMATCH")
        if handoff.proposal_sent or handoff.customer_contacted or handoff.customer_acceptance_recorded or handoff.invoice_created or handoff.payment_link_created or handoff.payment_state_changed or handoff.hvs_invoked or handoff.automation_allowed:
            blockers.append("HANDOFF_EXTERNAL_ACTION_FLAG_SET")
    return proposal, handoff, tuple(sorted(set(blockers)))


def record_manual_proposal_presentation(
    *,
    proposal_preparation_id: str,
    commercial_handoff_package_id: str,
    presentation_channel: str,
    presentation_date: str,
    presented_by_operator_id: str,
    evidence_reference: str | None = None,
    customer_participant_reference: str | None = None,
    operator_note: str | None = None,
    manual_action_confirmed: bool,
    repo_root: Any,
    recorded_at: str,
) -> CommercialAcceptanceServiceResult:
    repo = Path(repo_root)
    try:
        proposal_preparation_id = _safe_text("proposal_preparation_id", proposal_preparation_id)
        commercial_handoff_package_id = _safe_text("commercial_handoff_package_id", commercial_handoff_package_id)
        presentation_channel = _safe_text("presentation_channel", presentation_channel).upper()
        if presentation_channel not in ALLOWED_PRESENTATION_CHANNELS:
            raise ValueError("presentation_channel is unsupported")
        presentation_date = validate_calendar_date("presentation_date", presentation_date)
        recorded_at = validate_calendar_date("recorded_at", recorded_at)
        operator = _required_operator(presented_by_operator_id)
        evidence = _required_evidence(evidence_reference) if evidence_reference is not None else None
        participant = _optional_text("customer_participant_reference", customer_participant_reference)
        note = _optional_text("operator_note", operator_note)
        if not manual_action_confirmed:
            raise ValueError("manual presentation confirmation is required")
    except ValueError as exc:
        return _deny("INVALID_INPUT", str(exc))
    proposal, handoff, blockers = _proposal_handoff(repo, proposal_preparation_id, commercial_handoff_package_id)
    if blockers:
        return _deny("PRESENTATION_INELIGIBLE", ",".join(blockers), blockers=blockers)
    if presentation_date > proposal.validity_end_date or presentation_date < proposal.validity_start_date:
        return _deny("PROPOSAL_EXPIRED", "proposal is not valid on presentation date", blockers=("PROPOSAL_EXPIRED",))
    identity = {
        "proposal_preparation_id": proposal.proposal_preparation_id,
        "approved_content_hash": proposal.deterministic_content_hash,
        "commercial_handoff_package_id": handoff.handoff_id,
        "project_id": proposal.project_id,
        "customer_reference": proposal.customer_reference,
        "presentation_channel": presentation_channel,
        "presentation_date": presentation_date,
        "operator_id": operator,
        "evidence_reference": evidence,
    }
    record_id = presentation_id(identity)
    content = {
        **identity,
        "opportunity_id": proposal.opportunity_id,
        "commercial_scope_id": proposal.commercial_scope_id,
        "source_delivery_lineage_id": proposal.source_delivery_lineage_id,
        "source_artifact_id": proposal.source_artifact_id,
        "source_artifact_sha256": proposal.source_artifact_sha256,
        "customer_participant_reference": participant,
    }
    record = ProposalPresentationRecord(
        COMMERCIAL_ACCEPTANCE_SCHEMA_VERSION,
        record_id,
        proposal.proposal_preparation_id,
        handoff.handoff_id,
        proposal.deterministic_content_hash,
        proposal.opportunity_id,
        proposal.commercial_scope_id,
        proposal.project_id,
        proposal.customer_reference,
        proposal.source_delivery_lineage_id,
        proposal.source_artifact_id,
        proposal.source_artifact_sha256,
        presentation_channel,
        presentation_date,
        operator,
        participant,
        evidence,
        note,
        True,
        False,
        False,
        canonical_content_hash(content),
        recorded_at,
    )
    for existing in _presentations(repo).values():
        if existing.presentation_record_id == record.presentation_record_id:
            if _same_dict(existing, record):
                return CommercialAcceptanceServiceResult(True, presentation=existing, duplicate_of=existing.presentation_record_id)
            return _deny("PRESENTATION_CONFLICT", "presentation replay conflicts with existing record", presentation=existing, blockers=("PRESENTATION_CONFLICT",))
        if existing.proposal_preparation_id == proposal.proposal_preparation_id and existing.approved_proposal_content_hash != proposal.deterministic_content_hash:
            return _deny("PRESENTATION_CONFLICT", "conflicting presentation content hash", presentation=existing, blockers=("PRESENTATION_CONFLICT",))
    append_commercial_acceptance_event(audit_log_path=commercial_acceptance_path(repo), event_type=EVT_PROPOSAL_PRESENTATION_RECORDED, subject_id=record.presentation_record_id, operator_id=operator, recorded_at=recorded_at, record=record.to_dict())
    return CommercialAcceptanceServiceResult(True, presentation=record)


def _normalize_decision(value: str) -> str:
    text = _safe_text("decision_type", value).upper().replace("-", "_")
    aliases = {"NEGOTIATION": DECISION_NEGOTIATION_REQUESTED, "REVISION": DECISION_PROPOSAL_REVISION_REQUESTED, "NO_RESPONSE": DECISION_NO_RESPONSE}
    return aliases.get(text, text)


def _accepted_money(value: Any, currency: str, field: str) -> Decimal:
    return quantize_money(normalize_money(value, field=field, min_value=Decimal("0")), currency)


def record_customer_commercial_decision(
    *,
    presentation_record_id: str,
    decision_type: str,
    decision_date: str,
    recorded_by_operator_id: str,
    evidence_reference: str,
    approved_proposal_content_hash: str,
    repo_root: Any,
    recorded_at: str,
    customer_decision_reference: str | None = None,
    accepted_total: Any = None,
    accepted_currency: str | None = None,
    accepted_scope_hash: str | None = None,
    accepted_payment_terms: str | None = None,
    accepted_revision_terms: str | None = None,
    accepted_tax: Any = None,
    accepted_discount: Any = None,
    requested_changes: tuple[str, ...] = (),
    rejection_reason: str | None = None,
    follow_up_date: str | None = None,
    deferred_reason: str | None = None,
) -> CommercialAcceptanceServiceResult:
    repo = Path(repo_root)
    try:
        presentation_record_id = _safe_text("presentation_record_id", presentation_record_id)
        decision = _normalize_decision(decision_type)
        if decision not in ALLOWED_DECISION_TYPES:
            raise ValueError("decision_type is unsupported")
        decision_date = validate_calendar_date("decision_date", decision_date)
        recorded_at = validate_calendar_date("recorded_at", recorded_at)
        operator = _required_operator(recorded_by_operator_id)
        evidence = _required_evidence(evidence_reference)
        supplied_hash = _safe_text("approved_proposal_content_hash", approved_proposal_content_hash)
        customer_ref = _optional_text("customer_decision_reference", customer_decision_reference)
        changes = tuple(_safe_text("requested_changes", item) for item in requested_changes)
        reason = _optional_text("rejection_reason", rejection_reason)
        follow_up = validate_calendar_date("follow_up_date", follow_up_date) if follow_up_date else None
        deferred = _optional_text("deferred_reason", deferred_reason)
    except ValueError as exc:
        return _deny("INVALID_INPUT", str(exc))
    presentation = _presentations(repo).get(presentation_record_id)
    if not presentation:
        return _deny("PRESENTATION_NOT_FOUND", "customer decision requires a prior presentation", blockers=("PRESENTATION_NOT_FOUND",))
    proposal, handoff, blockers = _proposal_handoff(repo, presentation.proposal_preparation_id, presentation.commercial_handoff_package_id)
    if blockers:
        return _deny("DECISION_INELIGIBLE", ",".join(blockers), presentation=presentation, blockers=blockers)
    if supplied_hash != proposal.deterministic_content_hash or supplied_hash != presentation.approved_proposal_content_hash:
        return _deny("CONTENT_HASH_MISMATCH", "decision must bind the exact approved proposal content hash", presentation=presentation, blockers=("CONTENT_HASH_MISMATCH",))
    if decision_date > proposal.validity_end_date:
        return _deny("PROPOSAL_EXPIRED", "proposal is expired on decision date", presentation=presentation, blockers=("PROPOSAL_EXPIRED",))
    if decision == DECISION_REJECTED and not reason:
        return _deny("REJECTION_REASON_REQUIRED", "rejected decision requires a reason", presentation=presentation)
    if decision in (DECISION_NEGOTIATION_REQUESTED, DECISION_PROPOSAL_REVISION_REQUESTED) and not changes:
        return _deny("REQUESTED_CHANGES_REQUIRED", "negotiation or revision requires requested changes", presentation=presentation)
    if decision == DECISION_DEFERRED and not deferred and not follow_up:
        return _deny("DEFERRED_REASON_REQUIRED", "deferred decision requires a reason or future date", presentation=presentation)
    accepted_total_value: Decimal | None = None
    accepted_currency_value: str | None = None
    accepted_scope_value: str | None = None
    if decision == DECISION_ACCEPTED:
        try:
            accepted_currency_value = normalize_currency(accepted_currency)
            accepted_total_value = _accepted_money(accepted_total, accepted_currency_value, "accepted_total")
            accepted_scope_value = _safe_text("accepted_scope_hash", accepted_scope_hash)
            terms = _optional_text("accepted_payment_terms", accepted_payment_terms) or proposal.payment_terms
            revisions = _optional_text("accepted_revision_terms", accepted_revision_terms) or proposal.revision_terms
            tax = _accepted_money(accepted_tax if accepted_tax is not None else proposal.tax_amount, accepted_currency_value, "accepted_tax")
            discount = _accepted_money(accepted_discount if accepted_discount is not None else proposal.discount_amount, accepted_currency_value, "accepted_discount")
        except ValueError as exc:
            return _deny("INVALID_ACCEPTANCE", str(exc), presentation=presentation)
        mismatch = []
        if accepted_total_value != proposal.total_amount:
            mismatch.append("ACCEPTED_TOTAL_MISMATCH")
        if accepted_currency_value != proposal.currency:
            mismatch.append("ACCEPTED_CURRENCY_MISMATCH")
        if accepted_scope_value != proposal.commercial_scope_id:
            mismatch.append("ACCEPTED_SCOPE_MISMATCH")
        if terms != proposal.payment_terms:
            mismatch.append("PAYMENT_TERMS_CHANGED")
        if revisions != proposal.revision_terms:
            mismatch.append("REVISION_TERMS_CHANGED")
        if tax != proposal.tax_amount:
            mismatch.append("TAX_CHANGED")
        if discount != proposal.discount_amount:
            mismatch.append("DISCOUNT_CHANGED")
        if changes or reason:
            mismatch.append("ACCEPTANCE_CONTRADICTED_BY_CHANGE_FIELDS")
        if mismatch:
            return _deny("ACCEPTANCE_REQUIRES_NEGOTIATION_OR_REVISION", ",".join(mismatch), presentation=presentation, blockers=tuple(mismatch))
    identity = {
        "presentation_record_id": presentation.presentation_record_id,
        "proposal_preparation_id": proposal.proposal_preparation_id,
        "approved_content_hash": proposal.deterministic_content_hash,
        "decision_type": decision,
        "decision_date": decision_date,
        "accepted_total": str(accepted_total_value) if accepted_total_value is not None else None,
        "accepted_currency": accepted_currency_value,
        "accepted_scope_hash": accepted_scope_value,
        "requested_changes": changes,
        "rejection_reason": reason,
        "follow_up_date": follow_up,
        "deferred_reason": deferred,
        "evidence_reference": evidence,
    }
    decision_id = customer_decision_id(identity)
    record = CustomerDecisionRecord(
        COMMERCIAL_ACCEPTANCE_SCHEMA_VERSION,
        decision_id,
        presentation.presentation_record_id,
        proposal.proposal_preparation_id,
        proposal.deterministic_content_hash,
        proposal.customer_reference,
        decision,
        decision_date,
        operator,
        evidence,
        customer_ref,
        accepted_total_value,
        accepted_currency_value,
        accepted_scope_value,
        changes,
        reason,
        follow_up,
        deferred,
        False,
        False,
        canonical_content_hash(identity),
        recorded_at,
    )
    for existing in _decisions(repo).values():
        if existing.customer_decision_id == record.customer_decision_id:
            if _same_dict(existing, record):
                acceptance = next((item for item in _acceptances(repo).values() if item.customer_decision_id == existing.customer_decision_id), None)
                return CommercialAcceptanceServiceResult(True, decision=existing, acceptance=acceptance, duplicate_of=existing.customer_decision_id)
            return _deny("CUSTOMER_DECISION_CONFLICT", "decision replay conflicts with existing record", decision=existing)
        if existing.presentation_record_id == presentation.presentation_record_id and existing.customer_decision_id != record.customer_decision_id:
            return _deny("CUSTOMER_DECISION_CONFLICT", "presentation already has a different customer decision", decision=existing)
    append_commercial_acceptance_event(audit_log_path=commercial_acceptance_path(repo), event_type=EVT_CUSTOMER_DECISION_RECORDED, subject_id=record.customer_decision_id, operator_id=operator, recorded_at=recorded_at, record=record.to_dict())
    acceptance = None
    if decision == DECISION_ACCEPTED:
        acceptance = _create_acceptance(repo=repo, proposal=proposal, handoff=handoff, presentation=presentation, decision=record, recorded_at=recorded_at)
    return CommercialAcceptanceServiceResult(True, presentation=presentation, decision=record, acceptance=acceptance)


def _create_acceptance(*, repo: Path, proposal: Any, handoff: Any, presentation: ProposalPresentationRecord, decision: CustomerDecisionRecord, recorded_at: str) -> CommercialAcceptanceRecord:
    identity = {
        "customer_decision_id": decision.customer_decision_id,
        "presentation_record_id": presentation.presentation_record_id,
        "proposal_preparation_id": proposal.proposal_preparation_id,
        "approved_content_hash": proposal.deterministic_content_hash,
        "accepted_scope_hash": decision.accepted_scope_hash,
        "accepted_total": str(decision.accepted_total),
        "accepted_currency": decision.accepted_currency,
        "commercial_scope_id": proposal.commercial_scope_id,
        "source_artifact_sha256": proposal.source_artifact_sha256,
    }
    record_id = commercial_acceptance_id(identity)
    record = CommercialAcceptanceRecord(
        COMMERCIAL_ACCEPTANCE_SCHEMA_VERSION,
        record_id,
        decision.customer_decision_id,
        presentation.presentation_record_id,
        proposal.proposal_preparation_id,
        handoff.handoff_id,
        proposal.deterministic_content_hash,
        decision.accepted_scope_hash or proposal.commercial_scope_id,
        proposal.opportunity_id,
        proposal.commercial_scope_id,
        proposal.project_id,
        proposal.customer_reference,
        proposal.source_delivery_lineage_id,
        proposal.source_artifact_id,
        proposal.source_artifact_sha256,
        proposal.subtotal,
        proposal.discount_amount,
        proposal.tax_amount,
        proposal.total_amount,
        proposal.currency,
        proposal.payment_terms,
        proposal.revision_terms,
        f"{proposal.validity_start_date}:{proposal.validity_end_date}",
        decision.decision_date,
        decision.evidence_reference,
        decision.recorded_by_operator_id,
        ACCEPTED_VERIFIED,
        True,
        True,
        True,
        True,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        canonical_content_hash(identity),
        recorded_at,
    )
    for existing in _acceptances(repo).values():
        if existing.commercial_acceptance_id == record.commercial_acceptance_id:
            if _same_dict(existing, record):
                return existing
            raise ValueError("conflicting commercial acceptance record")
        if existing.proposal_preparation_id == proposal.proposal_preparation_id:
            raise ValueError("proposal already has a commercial acceptance record")
    append_commercial_acceptance_event(audit_log_path=commercial_acceptance_path(repo), event_type=EVT_COMMERCIAL_ACCEPTANCE_VERIFIED, subject_id=record.commercial_acceptance_id, operator_id=decision.recorded_by_operator_id, recorded_at=recorded_at, record=record.to_dict())
    return record


def evaluate_commercial_acceptance_readiness(*, proposal_preparation_id: str, repo_root: Any, evaluation_date: str) -> CommercialAcceptanceReadiness:
    repo = Path(repo_root)
    blockers: list[str] = []
    warnings: list[str] = []
    missing: list[str] = []
    try:
        proposal_preparation_id = _safe_text("proposal_preparation_id", proposal_preparation_id)
        evaluation_date = validate_calendar_date("evaluation_date", evaluation_date)
    except ValueError:
        return _readiness(proposal_preparation_id=str(proposal_preparation_id), status=BLOCKED, blockers=("INVALID_EVALUATION_DATE",), action="SUPPLY_A_VALID_EVALUATION_DATE")
    proposal, handoff, source_blockers = _proposal_handoff(repo, proposal_preparation_id)
    if not proposal:
        return _readiness(proposal_preparation_id=proposal_preparation_id, status=BLOCKED, blockers=("PROPOSAL_NOT_FOUND",), action="CREATE_OR_SELECT_APPROVED_PROPOSAL")
    if evaluation_date > proposal.validity_end_date:
        return _readiness(proposal_preparation_id=proposal_preparation_id, status=EXPIRED, blockers=("PROPOSAL_EXPIRED",), action="PREPARE_REVISED_PROPOSAL")
    blockers.extend(source_blockers)
    presentation = next((item for item in _presentations(repo).values() if item.proposal_preparation_id == proposal_preparation_id), None)
    if not presentation:
        missing.append("PRESENTATION_RECORD")
        return _readiness(proposal_preparation_id=proposal_preparation_id, status=NEEDS_OPERATOR_INPUT, missing=tuple(missing), blockers=tuple(blockers), action="RECORD_MANUAL_PRESENTATION")
    decision = next((item for item in _decisions(repo).values() if item.presentation_record_id == presentation.presentation_record_id), None)
    if not decision:
        missing.append("CUSTOMER_DECISION_RECORD")
        return _readiness(proposal_preparation_id=proposal_preparation_id, status=NEEDS_OPERATOR_INPUT, missing=tuple(missing), blockers=tuple(blockers), action="RECORD_CUSTOMER_DECISION")
    if not decision.evidence_reference:
        missing.append("ACCEPTANCE_EVIDENCE_REFERENCE")
    if decision.decision_type == DECISION_REJECTED:
        return _readiness(proposal_preparation_id=proposal_preparation_id, status=NOT_ACCEPTED, blockers=("CUSTOMER_REJECTED_PROPOSAL",), action="STOP_OR_PREPARE_NEW_PROPOSAL")
    if decision.decision_type in (DECISION_NEGOTIATION_REQUESTED, DECISION_PROPOSAL_REVISION_REQUESTED):
        return _readiness(proposal_preparation_id=proposal_preparation_id, status=NEGOTIATION_REQUIRED, blockers=("NEGOTIATION_OR_REVISION_REQUIRED",), action="RUN_HUMAN_CONTROLLED_REVISION_WORKFLOW")
    if decision.decision_type in (DECISION_NO_RESPONSE, DECISION_DEFERRED):
        return _readiness(proposal_preparation_id=proposal_preparation_id, status=NOT_ACCEPTED, blockers=(decision.decision_type,), action="FOLLOW_UP_MANUALLY")
    if decision.approved_proposal_content_hash != proposal.deterministic_content_hash:
        blockers.append("CONTENT_HASH_MISMATCH")
    if decision.accepted_scope_hash != proposal.commercial_scope_id:
        blockers.append("ACCEPTED_SCOPE_MISMATCH")
    if decision.accepted_total != proposal.total_amount:
        blockers.append("ACCEPTED_TOTAL_MISMATCH")
    if decision.accepted_currency != proposal.currency:
        blockers.append("ACCEPTED_CURRENCY_MISMATCH")
    acceptance = next((item for item in _acceptances(repo).values() if item.customer_decision_id == decision.customer_decision_id), None)
    if not acceptance:
        missing.append("COMMERCIAL_ACCEPTANCE_RECORD")
    if blockers:
        return _readiness(proposal_preparation_id=proposal_preparation_id, status=BLOCKED, blockers=tuple(sorted(set(blockers))), warnings=tuple(warnings), missing=tuple(missing), action="RESOLVE_ACCEPTANCE_BLOCKERS")
    if missing:
        return _readiness(proposal_preparation_id=proposal_preparation_id, status=NEEDS_OPERATOR_INPUT, missing=tuple(missing), action="COMPLETE_ACCEPTANCE_RECORDING")
    return _readiness(proposal_preparation_id=proposal_preparation_id, status=READY_FOR_MANUAL_INVOICE_AND_KICKOFF, acceptance_id=acceptance.commercial_acceptance_id, invoice=True, kickoff=True, manual=True, action="PREPARE_MANUAL_INVOICE_AND_PROJECT_KICKOFF")


def _readiness(
    *,
    proposal_preparation_id: str,
    status: str,
    blockers: tuple[str, ...] = (),
    warnings: tuple[str, ...] = (),
    missing: tuple[str, ...] = (),
    acceptance_id: str | None = None,
    invoice: bool = False,
    kickoff: bool = False,
    manual: bool = False,
    action: str,
) -> CommercialAcceptanceReadiness:
    return CommercialAcceptanceReadiness(
        proposal_preparation_id,
        status,
        blockers,
        warnings,
        missing,
        acceptance_id,
        invoice,
        kickoff,
        manual,
        manual,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        action,
    )


def inspect_customer_commercial_decision(*, customer_decision_id: str, repo_root: Any) -> CommercialAcceptanceServiceResult:
    try:
        customer_decision_id = _safe_text("customer_decision_id", customer_decision_id)
    except ValueError as exc:
        return _deny("INVALID_INPUT", str(exc))
    decision = _decisions(Path(repo_root)).get(customer_decision_id)
    return CommercialAcceptanceServiceResult(True, decision=decision) if decision else _deny("CUSTOMER_DECISION_NOT_FOUND", "customer decision not found")


def inspect_commercial_acceptance(*, commercial_acceptance_id: str, repo_root: Any) -> CommercialAcceptanceServiceResult:
    try:
        commercial_acceptance_id = _safe_text("commercial_acceptance_id", commercial_acceptance_id)
    except ValueError as exc:
        return _deny("INVALID_INPUT", str(exc))
    acceptance = _acceptances(Path(repo_root)).get(commercial_acceptance_id)
    return CommercialAcceptanceServiceResult(True, acceptance=acceptance) if acceptance else _deny("COMMERCIAL_ACCEPTANCE_NOT_FOUND", "commercial acceptance not found")


def list_commercial_decision_queue(*, repo_root: Any, evaluation_date: str) -> list[dict[str, Any]]:
    repo = Path(repo_root)
    try:
        evaluation_date = validate_calendar_date("evaluation_date", evaluation_date)
    except ValueError:
        return [{"item_type": "INVALID_EVALUATION_DATE", "blocking_reasons": ["INVALID_EVALUATION_DATE"], "automation_allowed": False}]
    decisions_by_presentation = {item.presentation_record_id: item for item in _decisions(repo).values()}
    items = []
    for presentation in _presentations(repo).values():
        if presentation.presentation_record_id in decisions_by_presentation:
            continue
        readiness = evaluate_commercial_acceptance_readiness(proposal_preparation_id=presentation.proposal_preparation_id, repo_root=repo, evaluation_date=evaluation_date)
        items.append({
            "queue_item_id": stable_id("scos-hvs-commercial-decision-queue", {"presentation_record_id": presentation.presentation_record_id}),
            "item_type": "CUSTOMER_COMMERCIAL_DECISION_REQUIRED",
            "presentation_record_id": presentation.presentation_record_id,
            "proposal_preparation_id": presentation.proposal_preparation_id,
            "customer_reference": presentation.customer_reference,
            "presentation_date": presentation.presentation_date,
            "readiness_status": readiness.readiness_status,
            "blocking_reasons": list(readiness.blockers),
            "recommended_manual_action": "RECORD_CUSTOMER_DECISION",
            "automation_allowed": False,
        })
    return sorted(items, key=lambda item: (item["presentation_date"], item["presentation_record_id"]))
