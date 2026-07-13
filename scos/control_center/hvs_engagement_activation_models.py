"""Immutable local-only Stage 8K engagement activation models."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .hvs_commercial_proposal_models import canonical_json, stable_id
from .hvs_invoice_models import money_to_json


ENGAGEMENT_ACTIVATION_SCHEMA_VERSION = "scos-hvs.engagement-activation.v1/1.0.0"
ENGAGEMENT_ACTIVATION_EVENT_SCHEMA_VERSION = "scos-hvs.engagement-activation-event.v1/1.0.0"
PRODUCTION_KICKOFF_AUTHORIZATION_SCHEMA_VERSION = "scos-hvs.production-kickoff-authorization.v1/1.0.0"

DRAFT = "DRAFT"
NEEDS_OPERATOR_INPUT = "NEEDS_OPERATOR_INPUT"
WAITING_FOR_PAYMENT_CONFIRMATION = "WAITING_FOR_PAYMENT_CONFIRMATION"
WAITING_FOR_CUSTOMER_INPUT = "WAITING_FOR_CUSTOMER_INPUT"
READY_FOR_PRODUCTION_REVIEW = "READY_FOR_PRODUCTION_REVIEW"
APPROVED_FOR_PROJECT_INITIALIZATION = "APPROVED_FOR_PROJECT_INITIALIZATION"
REJECTED = "REJECTED"
CANCELLED = "CANCELLED"
EXPIRED = "EXPIRED"
TERMINAL_ENGAGEMENT_STATUSES = (APPROVED_FOR_PROJECT_INITIALIZATION, REJECTED, CANCELLED, EXPIRED)

PAYMENT_NOT_REQUIRED_BEFORE_START = "PAYMENT_NOT_REQUIRED_BEFORE_START"
DEPOSIT_REQUIRED_BEFORE_START = "DEPOSIT_REQUIRED_BEFORE_START"
FULL_PAYMENT_REQUIRED_BEFORE_START = "FULL_PAYMENT_REQUIRED_BEFORE_START"
PAYMENT_REQUIREMENT_UNKNOWN = "PAYMENT_REQUIREMENT_UNKNOWN"
ALLOWED_PAYMENT_START_REQUIREMENTS = (
    PAYMENT_NOT_REQUIRED_BEFORE_START,
    DEPOSIT_REQUIRED_BEFORE_START,
    FULL_PAYMENT_REQUIRED_BEFORE_START,
    PAYMENT_REQUIREMENT_UNKNOWN,
)

PAYMENT_NOT_APPLICABLE = "NOT_APPLICABLE"
PAYMENT_REQUIREMENT_DECLARED = "REQUIREMENT_DECLARED"
PAYMENT_CONFIRMATION_PENDING = "CONFIRMATION_PENDING"
PAYMENT_SATISFIED_BY_OPERATOR_CONFIRMATION = "SATISFIED_BY_OPERATOR_CONFIRMATION"
PAYMENT_BLOCKED = "BLOCKED"
PAYMENT_DISPUTED = "DISPUTED"
ALLOWED_PAYMENT_REQUIREMENT_STATUSES = (
    PAYMENT_NOT_APPLICABLE,
    PAYMENT_REQUIREMENT_DECLARED,
    PAYMENT_CONFIRMATION_PENDING,
    PAYMENT_SATISFIED_BY_OPERATOR_CONFIRMATION,
    PAYMENT_BLOCKED,
    PAYMENT_DISPUTED,
)

INPUT_FINAL_PRODUCTION_BRIEF = "FINAL_PRODUCTION_BRIEF"
INPUT_SOURCE_ASSETS = "SOURCE_ASSETS"
INPUT_BRAND_GUIDELINES = "BRAND_GUIDELINES"
INPUT_APPROVAL_CONTACT = "APPROVAL_CONTACT"
INPUT_PRODUCTION_CONSTRAINTS = "PRODUCTION_CONSTRAINTS"
INPUT_OTHER = "OTHER"
ALLOWED_CUSTOMER_INPUT_TYPES = (
    INPUT_FINAL_PRODUCTION_BRIEF,
    INPUT_SOURCE_ASSETS,
    INPUT_BRAND_GUIDELINES,
    INPUT_APPROVAL_CONTACT,
    INPUT_PRODUCTION_CONSTRAINTS,
    INPUT_OTHER,
)

INPUT_PENDING = "PENDING"
INPUT_SATISFIED_BY_OPERATOR_CONFIRMATION = "SATISFIED_BY_OPERATOR_CONFIRMATION"
INPUT_BLOCKED = "BLOCKED"
INPUT_WAIVED_BY_OPERATOR = "WAIVED_BY_OPERATOR"
ALLOWED_CUSTOMER_INPUT_STATUSES = (
    INPUT_PENDING,
    INPUT_SATISFIED_BY_OPERATOR_CONFIRMATION,
    INPUT_BLOCKED,
    INPUT_WAIVED_BY_OPERATOR,
)

READINESS_READY = "READY"
READINESS_NEEDS_OPERATOR_INPUT = "NEEDS_OPERATOR_INPUT"
READINESS_WAITING_FOR_PAYMENT = "WAITING_FOR_PAYMENT_CONFIRMATION"
READINESS_WAITING_FOR_CUSTOMER_INPUT = "WAITING_FOR_CUSTOMER_INPUT"
READINESS_BLOCKED = "BLOCKED"
READINESS_NOT_APPROVED = "NOT_APPROVED"
READINESS_EXPIRED = "EXPIRED"

REVIEW_APPROVE_PROJECT_INITIALIZATION = "APPROVE_PROJECT_INITIALIZATION"
REVIEW_REJECT_PROJECT_INITIALIZATION = "REJECT_PROJECT_INITIALIZATION"
REVIEW_CANCEL_ACTIVATION = "CANCEL_ACTIVATION"
ALLOWED_REVIEW_DECISIONS = (
    REVIEW_APPROVE_PROJECT_INITIALIZATION,
    REVIEW_REJECT_PROJECT_INITIALIZATION,
    REVIEW_CANCEL_ACTIVATION,
)

EVT_ENGAGEMENT_ACTIVATION_CREATED = "ENGAGEMENT_ACTIVATION_CREATED"
EVT_PAYMENT_REQUIREMENT_RECORDED = "PAYMENT_REQUIREMENT_RECORDED"
EVT_PAYMENT_READINESS_CONFIRMED = "PAYMENT_READINESS_CONFIRMED"
EVT_CUSTOMER_INPUT_REQUIREMENT_ADDED = "CUSTOMER_INPUT_REQUIREMENT_ADDED"
EVT_CUSTOMER_INPUT_CONFIRMED = "CUSTOMER_INPUT_CONFIRMED"
EVT_PRODUCTION_REVIEW_REQUESTED = "PRODUCTION_REVIEW_REQUESTED"
EVT_ENGAGEMENT_APPROVED = "ENGAGEMENT_APPROVED"
EVT_ENGAGEMENT_REJECTED = "ENGAGEMENT_REJECTED"
EVT_ENGAGEMENT_CANCELLED = "ENGAGEMENT_CANCELLED"
EVT_PRODUCTION_KICKOFF_AUTHORIZATION_CREATED = "PRODUCTION_KICKOFF_AUTHORIZATION_CREATED"


def _hash_record(payload: dict[str, Any]) -> str:
    return stable_id("scos-hvs-engagement-activation-content", payload)


def canonical_content_hash(payload: dict[str, Any]) -> str:
    return _hash_record({"payload": canonical_json(payload)})


def engagement_activation_id(payload: dict[str, Any]) -> str:
    return stable_id("scos-hvs-engagement-activation", payload)


def customer_input_requirement_id(payload: dict[str, Any]) -> str:
    return stable_id("scos-hvs-customer-input-requirement", payload)


def production_kickoff_authorization_id(payload: dict[str, Any]) -> str:
    return stable_id("scos-hvs-production-kickoff-authorization", payload)


def _freeze_mapping(data: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((str(key), str(value)) for key, value in data.items()))


def _thaw_mapping(data: tuple[tuple[str, str], ...]) -> dict[str, str]:
    return {key: value for key, value in data}


@dataclass(frozen=True)
class CustomerInputRequirement:
    customer_input_requirement_id: str
    requirement_type: str
    description: str
    required: bool
    input_status: str
    evidence_reference: str | None
    confirmed_by_operator_id: str | None
    confirmation_date: str | None
    waiver_reason: str | None
    recorded_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class ProductionScheduleTerms:
    target_start_date: str | None
    target_completion_date: str | None
    production_dependency_notes: tuple[str, ...]
    production_risk_notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_start_date": self.target_start_date,
            "target_completion_date": self.target_completion_date,
            "production_dependency_notes": list(self.production_dependency_notes),
            "production_risk_notes": list(self.production_risk_notes),
        }


@dataclass(frozen=True)
class EngagementActivation:
    schema_version: str
    engagement_activation_id: str
    commercial_scope_id: str
    project_id: str
    customer_reference: str
    source_opportunity_id: str
    source_proposal_preparation_id: str
    source_proposal_content_hash: str
    source_commercial_handoff_id: str
    source_presentation_record_id: str
    source_customer_decision_id: str
    source_commercial_acceptance_id: str
    source_delivery_lineage_id: str
    source_delivery_record_id: str
    source_artifact_id: str
    source_artifact_sha256: str
    engagement_status: str
    accepted_scope_summary: str
    accepted_deliverables: tuple[tuple[tuple[str, str], ...], ...]
    accepted_exclusions: tuple[str, ...]
    accepted_assumptions: tuple[str, ...]
    accepted_subtotal: Decimal
    accepted_discount_amount: Decimal
    accepted_tax_amount: Decimal
    accepted_total_amount: Decimal
    accepted_currency: str
    accepted_payment_terms: str
    accepted_revision_terms: str
    payment_start_requirement: str
    required_payment_amount: Decimal | None
    required_payment_currency: str | None
    payment_requirement_status: str
    payment_evidence_reference: str | None
    customer_input_requirements: tuple[CustomerInputRequirement, ...]
    target_start_date: str | None
    target_completion_date: str | None
    production_dependency_notes: tuple[str, ...]
    production_risk_notes: tuple[str, ...]
    operator_review_required: bool
    manual_project_initialization_required: bool
    project_created: bool
    hvs_invoked: bool
    render_started: bool
    assets_copied: bool
    customer_contact_performed_by_system: bool
    invoice_issued: bool
    payment_link_created: bool
    payment_processed: bool
    automation_allowed: bool
    deterministic_content_hash: str
    created_at: str
    updated_at: str
    approval_operator_id: str | None = None
    approval_event_id: str | None = None
    approval_recorded_at: str | None = None
    decision_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["accepted_deliverables"] = [_thaw_mapping(item) for item in self.accepted_deliverables]
        data["customer_input_requirements"] = [item.to_dict() for item in self.customer_input_requirements]
        for key in ("accepted_subtotal", "accepted_discount_amount", "accepted_tax_amount", "accepted_total_amount"):
            data[key] = money_to_json(getattr(self, key), self.accepted_currency)
        data["required_payment_amount"] = None if self.required_payment_amount is None else money_to_json(self.required_payment_amount, self.required_payment_currency or self.accepted_currency)
        for key in (
            "project_created",
            "hvs_invoked",
            "render_started",
            "assets_copied",
            "customer_contact_performed_by_system",
            "invoice_issued",
            "payment_link_created",
            "payment_processed",
            "automation_allowed",
        ):
            data[key] = False
        return data


@dataclass(frozen=True)
class EngagementReadinessResult:
    engagement_activation_id: str
    readiness_status: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    missing_fields: tuple[str, ...]
    ready_for_production_review: bool
    ready_for_project_initialization_authorization: bool
    payment_requirement_status: str
    customer_input_status: str
    recommended_manual_action: str
    project_created: bool
    hvs_invoked: bool
    render_started: bool
    assets_copied: bool
    customer_contact_performed_by_system: bool
    invoice_issued: bool
    payment_link_created: bool
    payment_processed: bool
    automation_allowed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "engagement_activation_id": self.engagement_activation_id,
            "readiness_status": self.readiness_status,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "missing_fields": list(self.missing_fields),
            "ready_for_production_review": self.ready_for_production_review,
            "ready_for_project_initialization_authorization": self.ready_for_project_initialization_authorization,
            "payment_requirement_status": self.payment_requirement_status,
            "customer_input_status": self.customer_input_status,
            "recommended_manual_action": self.recommended_manual_action,
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


@dataclass(frozen=True)
class ProductionKickoffAuthorization:
    schema_version: str
    production_kickoff_authorization_id: str
    engagement_activation_id: str
    engagement_content_hash: str
    approval_event_id: str
    approved_by_operator_id: str
    approved_at: str
    commercial_scope_id: str
    project_id: str
    customer_reference: str
    source_opportunity_id: str
    source_proposal_preparation_id: str
    source_proposal_content_hash: str
    source_commercial_handoff_id: str
    source_presentation_record_id: str
    source_customer_decision_id: str
    source_commercial_acceptance_id: str
    source_delivery_lineage_id: str
    source_delivery_record_id: str
    source_artifact_id: str
    source_artifact_sha256: str
    accepted_total_amount: Decimal
    accepted_currency: str
    payment_start_requirement: str
    payment_requirement_status: str
    customer_input_status: str
    project_initialization_authorized: bool
    project_initialization_performed: bool
    project_created: bool
    hvs_invoked: bool
    render_started: bool
    assets_copied: bool
    customer_contact_performed_by_system: bool
    invoice_issued: bool
    payment_link_created: bool
    payment_processed: bool
    automation_allowed: bool
    deterministic_content_hash: str
    recorded_at: str

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["accepted_total_amount"] = money_to_json(self.accepted_total_amount, self.accepted_currency)
        data["project_initialization_authorized"] = True
        for key in (
            "project_initialization_performed",
            "project_created",
            "hvs_invoked",
            "render_started",
            "assets_copied",
            "customer_contact_performed_by_system",
            "invoice_issued",
            "payment_link_created",
            "payment_processed",
            "automation_allowed",
        ):
            data[key] = False
        return data


@dataclass(frozen=True)
class EngagementActivationEvent:
    schema_version: str
    event_id: str
    event_type: str
    subject_id: str
    operator_id: str
    recorded_at: str
    record: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class EngagementActivationError:
    error_code: str
    error_detail: str
    blockers: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"error_code": self.error_code, "error_detail": self.error_detail, "blockers": list(self.blockers)}


def customer_input_requirement_from_dict(data: dict[str, Any]) -> CustomerInputRequirement:
    return CustomerInputRequirement(**data)


def activation_from_dict(data: dict[str, Any]) -> EngagementActivation:
    value = dict(data)
    for key in ("accepted_subtotal", "accepted_discount_amount", "accepted_tax_amount", "accepted_total_amount"):
        value[key] = Decimal(str(value[key]))
    value["required_payment_amount"] = None if value.get("required_payment_amount") is None else Decimal(str(value["required_payment_amount"]))
    value["accepted_deliverables"] = tuple(_freeze_mapping(dict(item)) for item in value.get("accepted_deliverables", ()))
    value["accepted_exclusions"] = tuple(value.get("accepted_exclusions", ()))
    value["accepted_assumptions"] = tuple(value.get("accepted_assumptions", ()))
    value["production_dependency_notes"] = tuple(value.get("production_dependency_notes", ()))
    value["production_risk_notes"] = tuple(value.get("production_risk_notes", ()))
    value["customer_input_requirements"] = tuple(customer_input_requirement_from_dict(item) for item in value.get("customer_input_requirements", ()))
    return EngagementActivation(**value)


def authorization_from_dict(data: dict[str, Any]) -> ProductionKickoffAuthorization:
    value = dict(data)
    value["accepted_total_amount"] = Decimal(str(value["accepted_total_amount"]))
    return ProductionKickoffAuthorization(**value)
