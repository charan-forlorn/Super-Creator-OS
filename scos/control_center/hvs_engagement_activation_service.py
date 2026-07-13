"""Stage 8K local engagement activation and kickoff authorization service."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import Any

from .hvs_commercial_acceptance_models import ACCEPTED_VERIFIED, DECISION_ACCEPTED
from .hvs_commercial_acceptance_service import _acceptances, _decisions, _presentations
from .hvs_commercial_proposal_models import APPROVED_FOR_MANUAL_PRESENTATION, _safe_text, stable_id
from .hvs_commercial_proposal_service import _handoffs, _records
from .hvs_customer_outcome_models import validate_calendar_date
from .hvs_engagement_activation_models import *
from .hvs_engagement_activation_models import _freeze_mapping
from .hvs_engagement_activation_store import (
    append_engagement_activation_event,
    engagement_activation_path,
    read_engagement_activation_events,
)
from .hvs_invoice_models import normalize_currency, normalize_money, quantize_money


@dataclass(frozen=True)
class EngagementActivationServiceResult:
    ok: bool
    activation: EngagementActivation | None = None
    readiness: EngagementReadinessResult | None = None
    authorization: ProductionKickoffAuthorization | None = None
    duplicate_of: str | None = None
    error_code: str | None = None
    error_detail: str | None = None
    blockers: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "activation": self.activation.to_dict() if self.activation else None,
            "readiness": self.readiness.to_dict() if self.readiness else None,
            "authorization": self.authorization.to_dict() if self.authorization else None,
            "duplicate_of": self.duplicate_of,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
            "blockers": list(self.blockers),
            "project_created": False,
            "hvs_invoked": False,
            "render_started": False,
            "assets_copied": False,
            "customer_contact_performed_by_system": False,
            "invoice_issued": False,
            "payment_link_created": False,
            "payment_processed": False,
            "automation_allowed": False,
        }


def _deny(code: str, detail: str, **kwargs: Any) -> EngagementActivationServiceResult:
    return EngagementActivationServiceResult(False, error_code=code, error_detail=detail, **kwargs)


def _events(repo: Path) -> tuple[EngagementActivationEvent, ...]:
    return read_engagement_activation_events(audit_log_path=engagement_activation_path(repo))


def _activations(repo: Path) -> dict[str, EngagementActivation]:
    records: dict[str, EngagementActivation] = {}
    for event in _events(repo):
        if event.event_type != EVT_PRODUCTION_KICKOFF_AUTHORIZATION_CREATED:
            record = activation_from_dict(event.record)
            records[record.engagement_activation_id] = record
    return records


def _authorizations(repo: Path) -> dict[str, ProductionKickoffAuthorization]:
    records: dict[str, ProductionKickoffAuthorization] = {}
    for event in _events(repo):
        if event.event_type == EVT_PRODUCTION_KICKOFF_AUTHORIZATION_CREATED:
            record = authorization_from_dict(event.record)
            records[record.production_kickoff_authorization_id] = record
    return records


def _last_event_id(repo: Path, subject_id: str, event_type: str) -> str | None:
    found = None
    for event in _events(repo):
        if event.subject_id == subject_id and event.event_type == event_type:
            found = event.event_id
    return found


def _append(repo: Path, event_type: str, subject_id: str, operator_id: str, recorded_at: str, record: dict[str, Any]) -> EngagementActivationEvent:
    return append_engagement_activation_event(
        audit_log_path=engagement_activation_path(repo),
        event_type=event_type,
        subject_id=subject_id,
        operator_id=operator_id,
        recorded_at=recorded_at,
        record=record,
    )


def _required_operator(value: Any) -> str:
    return _safe_text("operator_id", value)


def _optional_text(field: str, value: Any) -> str | None:
    text = _safe_text(field, value, required=False)
    return text or None


def _safe_evidence(value: Any) -> str:
    text = _safe_text("evidence_reference", value)
    lowered = text.lower().replace("-", "_")
    forbidden = (
        "secret",
        "token",
        "password",
        "api_key",
        "apikey",
        "private_key",
        "bearer",
        "card_number",
        "cvv",
        "cvc",
        "bank_login",
        "raw_media",
        "private_media",
        "provider",
    )
    if any(item in lowered for item in forbidden):
        raise ValueError("evidence_reference must not contain secrets, card data, provider data, or private media markers")
    if "://" in text and not text.startswith("evidence-"):
        raise ValueError("evidence_reference must be a safe local evidence reference")
    return text


def _notes(field: str, values: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    return tuple(_safe_text(field, item) for item in (values or ()))


def _date_optional(field: str, value: Any) -> str | None:
    if value in (None, ""):
        return None
    return validate_calendar_date(field, value)


def _money(value: Any, currency: str, field: str) -> Decimal:
    return quantize_money(normalize_money(value, field=field, min_value=Decimal("0")), currency)


def _normalize_payment_requirement(value: str) -> str:
    text = _safe_text("payment_start_requirement", value).upper().replace("-", "_")
    aliases = {
        "NONE": PAYMENT_NOT_REQUIRED_BEFORE_START,
        "NOT_REQUIRED": PAYMENT_NOT_REQUIRED_BEFORE_START,
        "NO_PAYMENT_REQUIRED": PAYMENT_NOT_REQUIRED_BEFORE_START,
        "DEPOSIT": DEPOSIT_REQUIRED_BEFORE_START,
        "FULL": FULL_PAYMENT_REQUIRED_BEFORE_START,
        "FULL_PAYMENT": FULL_PAYMENT_REQUIRED_BEFORE_START,
        "UNKNOWN": PAYMENT_REQUIREMENT_UNKNOWN,
    }
    text = aliases.get(text, text)
    if text not in ALLOWED_PAYMENT_START_REQUIREMENTS:
        raise ValueError("payment_start_requirement is unsupported")
    return text


def _normalize_input_type(value: str) -> str:
    text = _safe_text("requirement_type", value).upper().replace("-", "_")
    if text not in ALLOWED_CUSTOMER_INPUT_TYPES:
        raise ValueError("requirement_type is unsupported")
    return text


def _customer_input_status(activation: EngagementActivation) -> str:
    required = tuple(item for item in activation.customer_input_requirements if item.required)
    if any(item.input_status == INPUT_BLOCKED for item in required):
        return INPUT_BLOCKED
    if any(item.input_status == INPUT_PENDING for item in required):
        return INPUT_PENDING
    return INPUT_SATISFIED_BY_OPERATOR_CONFIRMATION


def _derive_status(activation: EngagementActivation) -> str:
    if activation.engagement_status in TERMINAL_ENGAGEMENT_STATUSES:
        return activation.engagement_status
    if activation.payment_start_requirement == PAYMENT_REQUIREMENT_UNKNOWN or activation.payment_requirement_status in (PAYMENT_BLOCKED, PAYMENT_REQUIREMENT_DECLARED, PAYMENT_DISPUTED):
        return NEEDS_OPERATOR_INPUT
    if activation.payment_requirement_status == PAYMENT_CONFIRMATION_PENDING:
        return WAITING_FOR_PAYMENT_CONFIRMATION
    if _customer_input_status(activation) in (INPUT_PENDING, INPUT_BLOCKED):
        return WAITING_FOR_CUSTOMER_INPUT
    if activation.engagement_status == READY_FOR_PRODUCTION_REVIEW:
        return READY_FOR_PRODUCTION_REVIEW
    return DRAFT


def _content_hash(activation: EngagementActivation) -> str:
    payload = activation.to_dict()
    for key in ("deterministic_content_hash", "created_at", "updated_at", "approval_recorded_at", "approval_event_id"):
        payload.pop(key, None)
    return canonical_content_hash(payload)


def _with_hash(activation: EngagementActivation, *, updated_at: str) -> EngagementActivation:
    candidate = replace(activation, updated_at=updated_at)
    return replace(candidate, deterministic_content_hash=_content_hash(candidate))


def _eligibility(repo: Path, commercial_acceptance_id: str, as_of: str):
    acceptances = _acceptances(repo)
    acceptance = acceptances.get(commercial_acceptance_id)
    blockers: list[str] = []
    if not acceptance:
        return None, None, None, None, None, ("COMMERCIAL_ACCEPTANCE_NOT_FOUND",)
    if acceptance.acceptance_status != ACCEPTED_VERIFIED:
        blockers.append("COMMERCIAL_ACCEPTANCE_NOT_VERIFIED")
    if not acceptance.ready_for_manual_project_kickoff:
        blockers.append("ACCEPTANCE_NOT_READY_FOR_MANUAL_PROJECT_KICKOFF")
    if acceptance.invoice_created or acceptance.payment_link_created or acceptance.payment_state_changed or acceptance.project_created or acceptance.hvs_invoked or acceptance.render_started or acceptance.customer_contact_performed_by_system or acceptance.automation_allowed:
        blockers.append("ACCEPTANCE_EXTERNAL_ACTION_FLAG_SET")
    proposal = _records(repo).get(acceptance.proposal_preparation_id)
    handoff = _handoffs(repo).get(acceptance.proposal_preparation_id)
    presentation = _presentations(repo).get(acceptance.presentation_record_id)
    decision = _decisions(repo).get(acceptance.customer_decision_id)
    if not proposal:
        blockers.append("PROPOSAL_NOT_FOUND")
    if not handoff:
        blockers.append("HANDOFF_NOT_FOUND")
    if not presentation:
        blockers.append("PRESENTATION_NOT_FOUND")
    if not decision:
        blockers.append("CUSTOMER_DECISION_NOT_FOUND")
    if proposal:
        if proposal.proposal_status != APPROVED_FOR_MANUAL_PRESENTATION:
            blockers.append("PROPOSAL_NOT_APPROVED_FOR_MANUAL_PRESENTATION")
        if proposal.deterministic_content_hash != acceptance.approved_proposal_content_hash:
            blockers.append("PROPOSAL_CONTENT_HASH_MISMATCH")
        if proposal.commercial_scope_id != acceptance.commercial_scope_id or proposal.commercial_scope_id != acceptance.accepted_scope_hash:
            blockers.append("COMMERCIAL_SCOPE_MISMATCH")
        if proposal.project_id != acceptance.project_id:
            blockers.append("PROJECT_ID_MISMATCH")
        if proposal.customer_reference != acceptance.customer_reference:
            blockers.append("CUSTOMER_REFERENCE_MISMATCH")
        if proposal.source_delivery_lineage_id != acceptance.source_delivery_lineage_id:
            blockers.append("DELIVERY_LINEAGE_MISMATCH")
        if proposal.source_artifact_id != acceptance.source_artifact_id or proposal.source_artifact_sha256 != acceptance.source_artifact_sha256:
            blockers.append("ARTIFACT_LINEAGE_MISMATCH")
        if proposal.currency != acceptance.accepted_currency or proposal.total_amount != acceptance.accepted_total:
            blockers.append("ACCEPTED_TOTAL_OR_CURRENCY_MISMATCH")
        if proposal.subtotal != acceptance.accepted_subtotal or proposal.discount_amount != acceptance.accepted_discount or proposal.tax_amount != acceptance.accepted_tax:
            blockers.append("ACCEPTED_PRICE_COMPONENT_MISMATCH")
        if proposal.payment_terms != acceptance.accepted_payment_terms:
            blockers.append("ACCEPTED_PAYMENT_TERMS_MISMATCH")
        if proposal.revision_terms != acceptance.accepted_revision_terms:
            blockers.append("ACCEPTED_REVISION_TERMS_MISMATCH")
        if acceptance.customer_decision_date > proposal.validity_end_date or acceptance.customer_decision_date < proposal.validity_start_date:
            blockers.append("PROPOSAL_NOT_VALID_ON_DECISION_DATE")
        if as_of > proposal.validity_end_date and acceptance.customer_decision_date > proposal.validity_end_date:
            blockers.append("PROPOSAL_EXPIRED")
        if proposal.automation_allowed:
            blockers.append("PROPOSAL_AUTOMATION_ALLOWED")
    if handoff:
        if handoff.handoff_id != acceptance.commercial_handoff_package_id:
            blockers.append("HANDOFF_ID_MISMATCH")
        if handoff.approved_content_hash != acceptance.approved_proposal_content_hash:
            blockers.append("HANDOFF_CONTENT_HASH_MISMATCH")
        if handoff.invoice_created or handoff.payment_link_created or handoff.payment_state_changed or handoff.hvs_invoked or handoff.automation_allowed:
            blockers.append("HANDOFF_EXTERNAL_ACTION_FLAG_SET")
    if presentation:
        if not presentation.manual_action_confirmed:
            blockers.append("PRESENTATION_NOT_MANUAL")
        if presentation.approved_proposal_content_hash != acceptance.approved_proposal_content_hash:
            blockers.append("PRESENTATION_CONTENT_HASH_MISMATCH")
        if presentation.communication_performed_by_system or presentation.automation_allowed:
            blockers.append("PRESENTATION_EXTERNAL_ACTION_FLAG_SET")
    if decision:
        if decision.decision_type != DECISION_ACCEPTED:
            blockers.append("CUSTOMER_DECISION_NOT_ACCEPTED")
        if decision.presentation_record_id != acceptance.presentation_record_id:
            blockers.append("CUSTOMER_DECISION_PRESENTATION_MISMATCH")
        if decision.approved_proposal_content_hash != acceptance.approved_proposal_content_hash:
            blockers.append("CUSTOMER_DECISION_CONTENT_HASH_MISMATCH")
        if decision.accepted_total != acceptance.accepted_total or decision.accepted_currency != acceptance.accepted_currency:
            blockers.append("CUSTOMER_DECISION_TOTAL_OR_CURRENCY_MISMATCH")
        if decision.accepted_scope_hash != acceptance.accepted_scope_hash:
            blockers.append("CUSTOMER_DECISION_SCOPE_MISMATCH")
        if decision.customer_contact_performed_by_system or decision.automation_allowed:
            blockers.append("CUSTOMER_DECISION_EXTERNAL_ACTION_FLAG_SET")
    for other in acceptances.values():
        if other.commercial_acceptance_id != commercial_acceptance_id and other.proposal_preparation_id == acceptance.proposal_preparation_id:
            blockers.append("CONFLICTING_COMMERCIAL_ACCEPTANCE")
    return acceptance, proposal, handoff, presentation, decision, tuple(sorted(set(blockers)))


def create_engagement_activation(
    *,
    commercial_acceptance_id: str,
    operator_id: str,
    repo_root: Any,
    recorded_at: str,
    target_start_date: str | None = None,
    target_completion_date: str | None = None,
    production_dependency_notes: tuple[str, ...] | list[str] | None = None,
    production_risk_notes: tuple[str, ...] | list[str] | None = None,
) -> EngagementActivationServiceResult:
    repo = Path(repo_root)
    try:
        commercial_acceptance_id = _safe_text("commercial_acceptance_id", commercial_acceptance_id)
        operator = _required_operator(operator_id)
        recorded_at = validate_calendar_date("recorded_at", recorded_at)
        start_date = _date_optional("target_start_date", target_start_date)
        completion_date = _date_optional("target_completion_date", target_completion_date)
        if start_date and completion_date and start_date > completion_date:
            raise ValueError("target_start_date must be on or before target_completion_date")
        dependency_notes = _notes("production_dependency_notes", production_dependency_notes)
        risk_notes = _notes("production_risk_notes", production_risk_notes)
    except ValueError as exc:
        return _deny("INVALID_INPUT", str(exc))
    acceptance, proposal, handoff, presentation, decision, blockers = _eligibility(repo, commercial_acceptance_id, recorded_at)
    if blockers:
        return _deny("ACCEPTANCE_INELIGIBLE", ",".join(blockers), blockers=blockers)
    identity = {
        "commercial_acceptance_id": acceptance.commercial_acceptance_id,
        "proposal_preparation_id": proposal.proposal_preparation_id,
        "proposal_content_hash": proposal.deterministic_content_hash,
        "customer_decision_id": decision.customer_decision_id,
    }
    activation_id = engagement_activation_id(identity)
    existing = _activations(repo).get(activation_id)
    if existing:
        return EngagementActivationServiceResult(True, activation=existing, duplicate_of=activation_id)
    for current in _activations(repo).values():
        if current.source_commercial_acceptance_id == acceptance.commercial_acceptance_id:
            return _deny("ACTIVATION_CONFLICT", "commercial acceptance already has an engagement activation", activation=current, blockers=("ACTIVATION_CONFLICT",))
    activation = EngagementActivation(
        ENGAGEMENT_ACTIVATION_SCHEMA_VERSION,
        activation_id,
        acceptance.commercial_scope_id,
        acceptance.project_id,
        acceptance.customer_reference,
        acceptance.opportunity_id,
        proposal.proposal_preparation_id,
        proposal.deterministic_content_hash,
        handoff.handoff_id,
        presentation.presentation_record_id,
        decision.customer_decision_id,
        acceptance.commercial_acceptance_id,
        acceptance.source_delivery_lineage_id,
        proposal.source_delivery_record_id,
        acceptance.source_artifact_id,
        acceptance.source_artifact_sha256,
        NEEDS_OPERATOR_INPUT,
        proposal.scope_summary,
        tuple(_freeze_mapping(item.to_dict()) for item in proposal.deliverables),
        tuple(proposal.exclusions),
        tuple(proposal.assumptions),
        acceptance.accepted_subtotal,
        acceptance.accepted_discount,
        acceptance.accepted_tax,
        acceptance.accepted_total,
        acceptance.accepted_currency,
        acceptance.accepted_payment_terms,
        acceptance.accepted_revision_terms,
        PAYMENT_REQUIREMENT_UNKNOWN,
        None,
        None,
        PAYMENT_BLOCKED,
        None,
        (),
        start_date,
        completion_date,
        dependency_notes,
        risk_notes,
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
        False,
        "",
        recorded_at,
        recorded_at,
    )
    activation = _with_hash(activation, updated_at=recorded_at)
    _append(repo, EVT_ENGAGEMENT_ACTIVATION_CREATED, activation.engagement_activation_id, operator, recorded_at, activation.to_dict())
    return EngagementActivationServiceResult(True, activation=activation)


def _require_mutable_activation(repo: Path, engagement_activation_id: str) -> EngagementActivation | EngagementActivationServiceResult:
    activation = _activations(repo).get(engagement_activation_id)
    if not activation:
        return _deny("ACTIVATION_NOT_FOUND", "engagement activation was not found", blockers=("ACTIVATION_NOT_FOUND",))
    if activation.engagement_status in TERMINAL_ENGAGEMENT_STATUSES:
        return _deny("ACTIVATION_TERMINAL", "terminal engagement activation cannot be changed", activation=activation, blockers=("ACTIVATION_TERMINAL",))
    return activation


def record_payment_start_requirement(
    *,
    engagement_activation_id: str,
    payment_start_requirement: str,
    operator_id: str,
    repo_root: Any,
    recorded_at: str,
    required_payment_amount: Any = None,
    required_payment_currency: str | None = None,
) -> EngagementActivationServiceResult:
    repo = Path(repo_root)
    try:
        activation_id = _safe_text("engagement_activation_id", engagement_activation_id)
        requirement = _normalize_payment_requirement(payment_start_requirement)
        operator = _required_operator(operator_id)
        recorded_at = validate_calendar_date("recorded_at", recorded_at)
    except ValueError as exc:
        return _deny("INVALID_INPUT", str(exc))
    activation = _require_mutable_activation(repo, activation_id)
    if isinstance(activation, EngagementActivationServiceResult):
        return activation
    try:
        amount, currency, status = None, None, PAYMENT_BLOCKED
        if requirement == PAYMENT_NOT_REQUIRED_BEFORE_START:
            if required_payment_amount not in (None, "") or required_payment_currency not in (None, ""):
                raise ValueError("payment not required must not include an amount or currency")
            status = PAYMENT_NOT_APPLICABLE
        elif requirement == PAYMENT_REQUIREMENT_UNKNOWN:
            if required_payment_amount not in (None, "") or required_payment_currency not in (None, ""):
                raise ValueError("unknown payment requirement must not include an amount or currency")
            status = PAYMENT_BLOCKED
        else:
            currency = normalize_currency(required_payment_currency)
            if currency != activation.accepted_currency:
                raise ValueError("required_payment_currency must match accepted currency")
            amount = _money(required_payment_amount, currency, "required_payment_amount")
            if amount > activation.accepted_total_amount:
                raise ValueError("required_payment_amount must not exceed accepted total")
            if requirement == DEPOSIT_REQUIRED_BEFORE_START and amount <= Decimal("0"):
                raise ValueError("deposit amount must be greater than zero")
            if requirement == FULL_PAYMENT_REQUIRED_BEFORE_START and amount != activation.accepted_total_amount:
                raise ValueError("full payment amount must equal accepted total")
            status = PAYMENT_CONFIRMATION_PENDING
    except ValueError as exc:
        return _deny("INVALID_INPUT", str(exc), activation=activation)
    candidate = replace(
        activation,
        payment_start_requirement=requirement,
        required_payment_amount=amount,
        required_payment_currency=currency,
        payment_requirement_status=status,
        payment_evidence_reference=None,
    )
    candidate = replace(candidate, engagement_status=_derive_status(candidate))
    candidate = _with_hash(candidate, updated_at=recorded_at)
    _append(repo, EVT_PAYMENT_REQUIREMENT_RECORDED, candidate.engagement_activation_id, operator, recorded_at, candidate.to_dict())
    return EngagementActivationServiceResult(True, activation=candidate)


def confirm_payment_readiness(
    *,
    engagement_activation_id: str,
    operator_id: str,
    evidence_reference: str,
    confirmed_amount: Any,
    confirmed_currency: str,
    confirmation_date: str,
    repo_root: Any,
    recorded_at: str,
) -> EngagementActivationServiceResult:
    repo = Path(repo_root)
    try:
        activation_id = _safe_text("engagement_activation_id", engagement_activation_id)
        operator = _required_operator(operator_id)
        evidence = _safe_evidence(evidence_reference)
        confirmation_date = validate_calendar_date("confirmation_date", confirmation_date)
        recorded_at = validate_calendar_date("recorded_at", recorded_at)
    except ValueError as exc:
        return _deny("INVALID_INPUT", str(exc))
    activation = _require_mutable_activation(repo, activation_id)
    if isinstance(activation, EngagementActivationServiceResult):
        return activation
    if activation.payment_start_requirement not in (DEPOSIT_REQUIRED_BEFORE_START, FULL_PAYMENT_REQUIRED_BEFORE_START):
        return _deny("PAYMENT_CONFIRMATION_NOT_APPLICABLE", "payment confirmation applies only to deposit or full-payment requirements", activation=activation, blockers=("PAYMENT_CONFIRMATION_NOT_APPLICABLE",))
    try:
        currency = normalize_currency(confirmed_currency)
        amount = _money(confirmed_amount, currency, "confirmed_amount")
    except ValueError as exc:
        return _deny("INVALID_INPUT", str(exc), activation=activation)
    if currency != activation.required_payment_currency or amount != activation.required_payment_amount:
        return _deny("PAYMENT_CONFIRMATION_MISMATCH", "confirmed payment readiness must match declared amount and currency", activation=activation, blockers=("PAYMENT_CONFIRMATION_MISMATCH",))
    candidate = replace(activation, payment_requirement_status=PAYMENT_SATISFIED_BY_OPERATOR_CONFIRMATION, payment_evidence_reference=evidence)
    candidate = replace(candidate, engagement_status=_derive_status(candidate))
    candidate = _with_hash(candidate, updated_at=recorded_at)
    _append(repo, EVT_PAYMENT_READINESS_CONFIRMED, candidate.engagement_activation_id, operator, recorded_at, candidate.to_dict())
    return EngagementActivationServiceResult(True, activation=candidate)


def add_customer_input_requirement(
    *,
    engagement_activation_id: str,
    requirement_type: str,
    description: str,
    operator_id: str,
    repo_root: Any,
    recorded_at: str,
    required: bool = True,
) -> EngagementActivationServiceResult:
    repo = Path(repo_root)
    try:
        activation_id = _safe_text("engagement_activation_id", engagement_activation_id)
        requirement_type = _normalize_input_type(requirement_type)
        description = _safe_text("description", description)
        operator = _required_operator(operator_id)
        recorded_at = validate_calendar_date("recorded_at", recorded_at)
        if not isinstance(required, bool):
            raise ValueError("required must be boolean")
    except ValueError as exc:
        return _deny("INVALID_INPUT", str(exc))
    activation = _require_mutable_activation(repo, activation_id)
    if isinstance(activation, EngagementActivationServiceResult):
        return activation
    requirement_id = customer_input_requirement_id({"engagement_activation_id": activation_id, "requirement_type": requirement_type, "description": description})
    for item in activation.customer_input_requirements:
        if item.customer_input_requirement_id == requirement_id:
            return EngagementActivationServiceResult(True, activation=activation, duplicate_of=requirement_id)
    requirement = CustomerInputRequirement(requirement_id, requirement_type, description, required, INPUT_PENDING, None, None, None, None, recorded_at, recorded_at)
    candidate = replace(activation, customer_input_requirements=tuple(sorted((*activation.customer_input_requirements, requirement), key=lambda item: item.customer_input_requirement_id)))
    candidate = replace(candidate, engagement_status=_derive_status(candidate))
    candidate = _with_hash(candidate, updated_at=recorded_at)
    _append(repo, EVT_CUSTOMER_INPUT_REQUIREMENT_ADDED, candidate.engagement_activation_id, operator, recorded_at, candidate.to_dict())
    return EngagementActivationServiceResult(True, activation=candidate)


def confirm_customer_input_requirement(
    *,
    engagement_activation_id: str,
    customer_input_requirement_id: str,
    operator_id: str,
    evidence_reference: str,
    confirmation_date: str,
    repo_root: Any,
    recorded_at: str,
) -> EngagementActivationServiceResult:
    repo = Path(repo_root)
    try:
        activation_id = _safe_text("engagement_activation_id", engagement_activation_id)
        requirement_id = _safe_text("customer_input_requirement_id", customer_input_requirement_id)
        operator = _required_operator(operator_id)
        evidence = _safe_evidence(evidence_reference)
        confirmation_date = validate_calendar_date("confirmation_date", confirmation_date)
        recorded_at = validate_calendar_date("recorded_at", recorded_at)
    except ValueError as exc:
        return _deny("INVALID_INPUT", str(exc))
    activation = _require_mutable_activation(repo, activation_id)
    if isinstance(activation, EngagementActivationServiceResult):
        return activation
    updated: list[CustomerInputRequirement] = []
    found = False
    for item in activation.customer_input_requirements:
        if item.customer_input_requirement_id == requirement_id:
            found = True
            updated.append(replace(item, input_status=INPUT_SATISFIED_BY_OPERATOR_CONFIRMATION, evidence_reference=evidence, confirmed_by_operator_id=operator, confirmation_date=confirmation_date, updated_at=recorded_at))
        else:
            updated.append(item)
    if not found:
        return _deny("CUSTOMER_INPUT_REQUIREMENT_NOT_FOUND", "customer input requirement was not found", activation=activation, blockers=("CUSTOMER_INPUT_REQUIREMENT_NOT_FOUND",))
    candidate = replace(activation, customer_input_requirements=tuple(sorted(updated, key=lambda item: item.customer_input_requirement_id)))
    candidate = replace(candidate, engagement_status=_derive_status(candidate))
    candidate = _with_hash(candidate, updated_at=recorded_at)
    _append(repo, EVT_CUSTOMER_INPUT_CONFIRMED, candidate.engagement_activation_id, operator, recorded_at, candidate.to_dict())
    return EngagementActivationServiceResult(True, activation=candidate)


def evaluate_engagement_readiness(*, engagement_activation_id: str, repo_root: Any, evaluation_date: str) -> EngagementReadinessResult:
    repo = Path(repo_root)
    activation_id = _safe_text("engagement_activation_id", engagement_activation_id)
    validate_calendar_date("evaluation_date", evaluation_date)
    activation = _activations(repo).get(activation_id)
    if not activation:
        return EngagementReadinessResult(activation_id, READINESS_BLOCKED, ("ACTIVATION_NOT_FOUND",), (), ("engagement_activation_id",), False, False, "UNKNOWN", "UNKNOWN", "Create or select a valid engagement activation.", False, False, False, False, False, False, False, False, False)
    blockers: list[str] = []
    missing: list[str] = []
    if activation.engagement_status == EXPIRED:
        blockers.append("ACTIVATION_EXPIRED")
    if activation.engagement_status in (REJECTED, CANCELLED):
        blockers.append("ACTIVATION_TERMINAL")
    if activation.payment_start_requirement == PAYMENT_REQUIREMENT_UNKNOWN:
        blockers.append("PAYMENT_REQUIREMENT_UNKNOWN")
        missing.append("payment_start_requirement")
    if activation.payment_requirement_status in (PAYMENT_BLOCKED, PAYMENT_DISPUTED, PAYMENT_REQUIREMENT_DECLARED):
        blockers.append(f"PAYMENT_{activation.payment_requirement_status}")
    if activation.payment_requirement_status == PAYMENT_CONFIRMATION_PENDING:
        blockers.append("PAYMENT_CONFIRMATION_PENDING")
    input_status = _customer_input_status(activation)
    if input_status == INPUT_PENDING:
        blockers.append("CUSTOMER_INPUT_PENDING")
    if input_status == INPUT_BLOCKED:
        blockers.append("CUSTOMER_INPUT_BLOCKED")
    if activation.target_start_date and activation.target_completion_date and activation.target_start_date > activation.target_completion_date:
        blockers.append("INVALID_TARGET_DATE_RANGE")
    if blockers:
        if "PAYMENT_CONFIRMATION_PENDING" in blockers:
            status = READINESS_WAITING_FOR_PAYMENT
            action = "Record explicit operator-confirmed payment readiness evidence before review."
        elif "CUSTOMER_INPUT_PENDING" in blockers or "CUSTOMER_INPUT_BLOCKED" in blockers:
            status = READINESS_WAITING_FOR_CUSTOMER_INPUT
            action = "Resolve explicit customer-input requirements before review."
        elif "ACTIVATION_EXPIRED" in blockers:
            status = READINESS_EXPIRED
            action = "Create a new activation from a still-valid acceptance."
        else:
            status = READINESS_NEEDS_OPERATOR_INPUT
            action = "Complete explicit payment and activation inputs before review."
    else:
        status = READINESS_READY
        action = "Request internal operator production review."
    ready = status == READINESS_READY
    return EngagementReadinessResult(
        activation.engagement_activation_id,
        status,
        tuple(sorted(set(blockers))),
        (),
        tuple(sorted(set(missing))),
        ready,
        activation.engagement_status == APPROVED_FOR_PROJECT_INITIALIZATION,
        activation.payment_requirement_status,
        input_status,
        action,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
    )


def request_production_review(*, engagement_activation_id: str, operator_id: str, repo_root: Any, recorded_at: str, evaluation_date: str) -> EngagementActivationServiceResult:
    repo = Path(repo_root)
    try:
        activation_id = _safe_text("engagement_activation_id", engagement_activation_id)
        operator = _required_operator(operator_id)
        recorded_at = validate_calendar_date("recorded_at", recorded_at)
        evaluation_date = validate_calendar_date("evaluation_date", evaluation_date)
    except ValueError as exc:
        return _deny("INVALID_INPUT", str(exc))
    activation = _require_mutable_activation(repo, activation_id)
    if isinstance(activation, EngagementActivationServiceResult):
        return activation
    readiness = evaluate_engagement_readiness(engagement_activation_id=activation_id, repo_root=repo, evaluation_date=evaluation_date)
    if readiness.readiness_status != READINESS_READY:
        return _deny("READINESS_BLOCKED", "engagement activation is not ready for production review", activation=activation, readiness=readiness, blockers=readiness.blockers)
    candidate = _with_hash(replace(activation, engagement_status=READY_FOR_PRODUCTION_REVIEW), updated_at=recorded_at)
    _append(repo, EVT_PRODUCTION_REVIEW_REQUESTED, candidate.engagement_activation_id, operator, recorded_at, candidate.to_dict())
    return EngagementActivationServiceResult(True, activation=candidate, readiness=readiness)


def decide_engagement_activation(
    *,
    engagement_activation_id: str,
    decision: str,
    operator_id: str,
    repo_root: Any,
    recorded_at: str,
    reason: str | None = None,
) -> EngagementActivationServiceResult:
    repo = Path(repo_root)
    try:
        activation_id = _safe_text("engagement_activation_id", engagement_activation_id)
        decision = _safe_text("decision", decision).upper().replace("-", "_")
        aliases = {"APPROVE": REVIEW_APPROVE_PROJECT_INITIALIZATION, "REJECT": REVIEW_REJECT_PROJECT_INITIALIZATION, "CANCEL": REVIEW_CANCEL_ACTIVATION}
        decision = aliases.get(decision, decision)
        if decision not in ALLOWED_REVIEW_DECISIONS:
            raise ValueError("decision is unsupported")
        operator = _required_operator(operator_id)
        recorded_at = validate_calendar_date("recorded_at", recorded_at)
        reason_text = _optional_text("reason", reason)
        if decision in (REVIEW_REJECT_PROJECT_INITIALIZATION, REVIEW_CANCEL_ACTIVATION) and not reason_text:
            raise ValueError("reason is required for rejection or cancellation")
    except ValueError as exc:
        return _deny("INVALID_INPUT", str(exc))
    activation = _activations(repo).get(activation_id)
    if not activation:
        return _deny("ACTIVATION_NOT_FOUND", "engagement activation was not found", blockers=("ACTIVATION_NOT_FOUND",))
    if activation.engagement_status in TERMINAL_ENGAGEMENT_STATUSES:
        if decision == REVIEW_APPROVE_PROJECT_INITIALIZATION and activation.engagement_status == APPROVED_FOR_PROJECT_INITIALIZATION:
            return EngagementActivationServiceResult(True, activation=activation, duplicate_of=activation.engagement_activation_id)
        return _deny("ACTIVATION_TERMINAL", "terminal engagement activation cannot be changed", activation=activation, blockers=("ACTIVATION_TERMINAL",))
    if decision == REVIEW_APPROVE_PROJECT_INITIALIZATION:
        if activation.engagement_status != READY_FOR_PRODUCTION_REVIEW:
            return _deny("REVIEW_REQUIRED", "activation must be ready for production review before approval", activation=activation, blockers=("REVIEW_REQUIRED",))
        event_id = stable_id("scos-hvs-engagement-approval-event-ref", {"engagement_activation_id": activation.engagement_activation_id, "operator_id": operator, "recorded_at": recorded_at})
        candidate = replace(activation, engagement_status=APPROVED_FOR_PROJECT_INITIALIZATION, approval_operator_id=operator, approval_event_id=event_id, approval_recorded_at=recorded_at)
        event_type = EVT_ENGAGEMENT_APPROVED
    elif decision == REVIEW_REJECT_PROJECT_INITIALIZATION:
        candidate = replace(activation, engagement_status=REJECTED, decision_reason=reason_text)
        event_type = EVT_ENGAGEMENT_REJECTED
    else:
        candidate = replace(activation, engagement_status=CANCELLED, decision_reason=reason_text)
        event_type = EVT_ENGAGEMENT_CANCELLED
    candidate = _with_hash(candidate, updated_at=recorded_at)
    event = _append(repo, event_type, candidate.engagement_activation_id, operator, recorded_at, candidate.to_dict())
    if event_type == EVT_ENGAGEMENT_APPROVED:
        candidate = _with_hash(replace(candidate, approval_event_id=event.event_id), updated_at=recorded_at)
        _append(repo, event_type, candidate.engagement_activation_id, operator, recorded_at, candidate.to_dict())
    return EngagementActivationServiceResult(True, activation=candidate)


def create_production_kickoff_authorization(*, engagement_activation_id: str, operator_id: str, repo_root: Any, recorded_at: str) -> EngagementActivationServiceResult:
    repo = Path(repo_root)
    try:
        activation_id = _safe_text("engagement_activation_id", engagement_activation_id)
        operator = _required_operator(operator_id)
        recorded_at = validate_calendar_date("recorded_at", recorded_at)
    except ValueError as exc:
        return _deny("INVALID_INPUT", str(exc))
    activation = _activations(repo).get(activation_id)
    if not activation:
        return _deny("ACTIVATION_NOT_FOUND", "engagement activation was not found", blockers=("ACTIVATION_NOT_FOUND",))
    if activation.engagement_status != APPROVED_FOR_PROJECT_INITIALIZATION:
        return _deny("APPROVAL_REQUIRED", "activation must be approved before kickoff authorization", activation=activation, blockers=("APPROVAL_REQUIRED",))
    approval_event_id = activation.approval_event_id or _last_event_id(repo, activation.engagement_activation_id, EVT_ENGAGEMENT_APPROVED)
    if not approval_event_id:
        return _deny("APPROVAL_EVENT_NOT_FOUND", "approved activation lacks an approval event", activation=activation, blockers=("APPROVAL_EVENT_NOT_FOUND",))
    input_status = _customer_input_status(activation)
    auth_id = production_kickoff_authorization_id({"engagement_activation_id": activation.engagement_activation_id, "engagement_content_hash": activation.deterministic_content_hash, "approval_event_id": approval_event_id})
    existing = _authorizations(repo).get(auth_id)
    if existing:
        return EngagementActivationServiceResult(True, activation=activation, authorization=existing, duplicate_of=auth_id)
    authorization = ProductionKickoffAuthorization(
        PRODUCTION_KICKOFF_AUTHORIZATION_SCHEMA_VERSION,
        auth_id,
        activation.engagement_activation_id,
        activation.deterministic_content_hash,
        approval_event_id,
        activation.approval_operator_id or operator,
        activation.approval_recorded_at or recorded_at,
        activation.commercial_scope_id,
        activation.project_id,
        activation.customer_reference,
        activation.source_opportunity_id,
        activation.source_proposal_preparation_id,
        activation.source_proposal_content_hash,
        activation.source_commercial_handoff_id,
        activation.source_presentation_record_id,
        activation.source_customer_decision_id,
        activation.source_commercial_acceptance_id,
        activation.source_delivery_lineage_id,
        activation.source_delivery_record_id,
        activation.source_artifact_id,
        activation.source_artifact_sha256,
        activation.accepted_total_amount,
        activation.accepted_currency,
        activation.payment_start_requirement,
        activation.payment_requirement_status,
        input_status,
        True,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
        "",
        recorded_at,
    )
    payload = authorization.to_dict()
    payload.pop("deterministic_content_hash", None)
    authorization = replace(authorization, deterministic_content_hash=canonical_content_hash(payload))
    _append(repo, EVT_PRODUCTION_KICKOFF_AUTHORIZATION_CREATED, authorization.production_kickoff_authorization_id, operator, recorded_at, authorization.to_dict())
    return EngagementActivationServiceResult(True, activation=activation, authorization=authorization)


def inspect_engagement_activation(*, engagement_activation_id: str, repo_root: Any) -> EngagementActivationServiceResult:
    try:
        activation_id = _safe_text("engagement_activation_id", engagement_activation_id)
    except ValueError as exc:
        return _deny("INVALID_INPUT", str(exc))
    activation = _activations(Path(repo_root)).get(activation_id)
    if not activation:
        return _deny("ACTIVATION_NOT_FOUND", "engagement activation was not found", blockers=("ACTIVATION_NOT_FOUND",))
    return EngagementActivationServiceResult(True, activation=activation)


def inspect_production_kickoff_authorization(*, production_kickoff_authorization_id: str, repo_root: Any) -> EngagementActivationServiceResult:
    try:
        authorization_id = _safe_text("production_kickoff_authorization_id", production_kickoff_authorization_id)
    except ValueError as exc:
        return _deny("INVALID_INPUT", str(exc))
    authorization = _authorizations(Path(repo_root)).get(authorization_id)
    if not authorization:
        return _deny("AUTHORIZATION_NOT_FOUND", "production kickoff authorization was not found", blockers=("AUTHORIZATION_NOT_FOUND",))
    activation = _activations(Path(repo_root)).get(authorization.engagement_activation_id)
    return EngagementActivationServiceResult(True, activation=activation, authorization=authorization)


def list_engagement_activation_queue(*, repo_root: Any, evaluation_date: str) -> tuple[dict[str, Any], ...]:
    repo = Path(repo_root)
    validate_calendar_date("evaluation_date", evaluation_date)
    rows = []
    for activation in sorted(_activations(repo).values(), key=lambda item: item.engagement_activation_id):
        readiness = evaluate_engagement_readiness(engagement_activation_id=activation.engagement_activation_id, repo_root=repo, evaluation_date=evaluation_date)
        rows.append({
            "engagement_activation_id": activation.engagement_activation_id,
            "commercial_acceptance_id": activation.source_commercial_acceptance_id,
            "project_id": activation.project_id,
            "customer_reference": activation.customer_reference,
            "engagement_status": activation.engagement_status,
            "readiness_status": readiness.readiness_status,
            "blockers": list(readiness.blockers),
            "automation_allowed": False,
        })
    return tuple(rows)
