"""Immutable local-only Stage 8J commercial acceptance models."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .hvs_commercial_proposal_models import canonical_json, stable_id
from .hvs_invoice_models import money_to_json


COMMERCIAL_ACCEPTANCE_SCHEMA_VERSION = "scos-hvs.commercial-acceptance.v1/1.0.0"
COMMERCIAL_ACCEPTANCE_EVENT_SCHEMA_VERSION = "scos-hvs.commercial-acceptance-event.v1/1.0.0"

CHANNEL_IN_PERSON = "IN_PERSON"
CHANNEL_VIDEO_CALL = "VIDEO_CALL"
CHANNEL_PHONE = "PHONE"
CHANNEL_EMAIL_MANUAL = "EMAIL_MANUAL"
CHANNEL_MESSAGING_MANUAL = "MESSAGING_MANUAL"
CHANNEL_CUSTOMER_PORTAL_MANUAL = "CUSTOMER_PORTAL_MANUAL"
CHANNEL_OTHER_MANUAL = "OTHER_MANUAL"
ALLOWED_PRESENTATION_CHANNELS = (
    CHANNEL_IN_PERSON,
    CHANNEL_VIDEO_CALL,
    CHANNEL_PHONE,
    CHANNEL_EMAIL_MANUAL,
    CHANNEL_MESSAGING_MANUAL,
    CHANNEL_CUSTOMER_PORTAL_MANUAL,
    CHANNEL_OTHER_MANUAL,
)

DECISION_ACCEPTED = "ACCEPTED"
DECISION_REJECTED = "REJECTED"
DECISION_NEGOTIATION_REQUESTED = "NEGOTIATION_REQUESTED"
DECISION_PROPOSAL_REVISION_REQUESTED = "PROPOSAL_REVISION_REQUESTED"
DECISION_NO_RESPONSE = "NO_RESPONSE"
DECISION_DEFERRED = "DEFERRED"
ALLOWED_DECISION_TYPES = (
    DECISION_ACCEPTED,
    DECISION_REJECTED,
    DECISION_NEGOTIATION_REQUESTED,
    DECISION_PROPOSAL_REVISION_REQUESTED,
    DECISION_NO_RESPONSE,
    DECISION_DEFERRED,
)

ACCEPTED_VERIFIED = "ACCEPTED_VERIFIED"
ACCEPTANCE_BLOCKED = "ACCEPTANCE_BLOCKED"
SUPERSEDED_BY_NEGOTIATION = "SUPERSEDED_BY_NEGOTIATION"
WITHDRAWN = "WITHDRAWN"

READY_FOR_MANUAL_INVOICE_AND_KICKOFF = "READY_FOR_MANUAL_INVOICE_AND_KICKOFF"
NEEDS_OPERATOR_INPUT = "NEEDS_OPERATOR_INPUT"
BLOCKED = "BLOCKED"
NOT_ACCEPTED = "NOT_ACCEPTED"
EXPIRED = "EXPIRED"
NEGOTIATION_REQUIRED = "NEGOTIATION_REQUIRED"

EVT_PROPOSAL_PRESENTATION_RECORDED = "PROPOSAL_PRESENTATION_RECORDED"
EVT_CUSTOMER_DECISION_RECORDED = "CUSTOMER_DECISION_RECORDED"
EVT_COMMERCIAL_ACCEPTANCE_VERIFIED = "COMMERCIAL_ACCEPTANCE_VERIFIED"
EVT_PROPOSAL_PRESENTATION_REPLAYED = "PROPOSAL_PRESENTATION_REPLAYED"
EVT_PROPOSAL_PRESENTATION_CONFLICT_DETECTED = "PROPOSAL_PRESENTATION_CONFLICT_DETECTED"
EVT_CUSTOMER_DECISION_CONFLICT_DETECTED = "CUSTOMER_DECISION_CONFLICT_DETECTED"
EVT_COMMERCIAL_ACCEPTANCE_BLOCKED = "COMMERCIAL_ACCEPTANCE_BLOCKED"
EVT_NEGOTIATION_REQUESTED = "NEGOTIATION_REQUESTED"
EVT_PROPOSAL_REVISION_REQUESTED = "PROPOSAL_REVISION_REQUESTED"
EVT_PROPOSAL_REJECTED_BY_CUSTOMER = "PROPOSAL_REJECTED_BY_CUSTOMER"
EVT_PROPOSAL_NO_RESPONSE_RECORDED = "PROPOSAL_NO_RESPONSE_RECORDED"


def _hash_record(payload: dict[str, Any]) -> str:
    return stable_id("scos-hvs-commercial-acceptance-content", payload)


def presentation_id(payload: dict[str, Any]) -> str:
    return stable_id("scos-hvs-proposal-presentation", payload)


def customer_decision_id(payload: dict[str, Any]) -> str:
    return stable_id("scos-hvs-customer-decision", payload)


def commercial_acceptance_id(payload: dict[str, Any]) -> str:
    return stable_id("scos-hvs-commercial-acceptance", payload)


@dataclass(frozen=True)
class ProposalPresentationRecord:
    schema_version: str
    presentation_record_id: str
    proposal_preparation_id: str
    commercial_handoff_package_id: str
    approved_proposal_content_hash: str
    opportunity_id: str
    commercial_scope_id: str
    project_id: str
    customer_reference: str
    source_delivery_lineage_id: str
    source_artifact_id: str
    source_artifact_sha256: str
    presentation_channel: str
    presentation_date: str
    presented_by_operator_id: str
    customer_participant_reference: str | None
    evidence_reference: str | None
    operator_note: str | None
    manual_action_confirmed: bool
    communication_performed_by_system: bool
    automation_allowed: bool
    deterministic_content_hash: str
    recorded_at: str

    def to_dict(self) -> dict[str, Any]:
        return {**self.__dict__, "communication_performed_by_system": False, "automation_allowed": False}


@dataclass(frozen=True)
class CustomerDecisionRecord:
    schema_version: str
    customer_decision_id: str
    presentation_record_id: str
    proposal_preparation_id: str
    approved_proposal_content_hash: str
    customer_reference: str
    decision_type: str
    decision_date: str
    recorded_by_operator_id: str
    evidence_reference: str
    customer_decision_reference: str | None
    accepted_total: Decimal | None
    accepted_currency: str | None
    accepted_scope_hash: str | None
    requested_changes: tuple[str, ...]
    rejection_reason: str | None
    follow_up_date: str | None
    deferred_reason: str | None
    automation_allowed: bool
    customer_contact_performed_by_system: bool
    deterministic_content_hash: str
    recorded_at: str

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["requested_changes"] = list(self.requested_changes)
        data["accepted_total"] = None if self.accepted_total is None else money_to_json(self.accepted_total, self.accepted_currency or "")
        data["automation_allowed"] = False
        data["customer_contact_performed_by_system"] = False
        return data


@dataclass(frozen=True)
class CommercialAcceptanceRecord:
    schema_version: str
    commercial_acceptance_id: str
    customer_decision_id: str
    presentation_record_id: str
    proposal_preparation_id: str
    commercial_handoff_package_id: str
    approved_proposal_content_hash: str
    accepted_scope_hash: str
    opportunity_id: str
    commercial_scope_id: str
    project_id: str
    customer_reference: str
    source_delivery_lineage_id: str
    source_artifact_id: str
    source_artifact_sha256: str
    accepted_subtotal: Decimal
    accepted_discount: Decimal
    accepted_tax: Decimal
    accepted_total: Decimal
    accepted_currency: str
    accepted_payment_terms: str
    accepted_revision_terms: str
    accepted_validity_reference: str
    customer_decision_date: str
    acceptance_evidence_reference: str
    recorded_by_operator_id: str
    acceptance_status: str
    ready_for_manual_invoice: bool
    ready_for_manual_project_kickoff: bool
    manual_invoice_required: bool
    manual_project_kickoff_required: bool
    invoice_created: bool
    payment_link_created: bool
    payment_state_changed: bool
    project_created: bool
    hvs_invoked: bool
    render_started: bool
    customer_contact_performed_by_system: bool
    automation_allowed: bool
    deterministic_content_hash: str
    recorded_at: str

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        for key in ("accepted_subtotal", "accepted_discount", "accepted_tax", "accepted_total"):
            data[key] = money_to_json(getattr(self, key), self.accepted_currency)
        for key in (
            "invoice_created",
            "payment_link_created",
            "payment_state_changed",
            "project_created",
            "hvs_invoked",
            "render_started",
            "customer_contact_performed_by_system",
            "automation_allowed",
        ):
            data[key] = False
        return data


@dataclass(frozen=True)
class CommercialAcceptanceReadiness:
    proposal_preparation_id: str
    readiness_status: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    missing_fields: tuple[str, ...]
    commercial_acceptance_id: str | None
    ready_for_manual_invoice: bool
    ready_for_manual_project_kickoff: bool
    manual_invoice_required: bool
    manual_project_kickoff_required: bool
    invoice_created: bool
    payment_link_created: bool
    payment_state_changed: bool
    project_created: bool
    hvs_invoked: bool
    render_started: bool
    customer_contact_performed_by_system: bool
    automation_allowed: bool
    recommended_manual_action: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_preparation_id": self.proposal_preparation_id,
            "readiness_status": self.readiness_status,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "missing_fields": list(self.missing_fields),
            "commercial_acceptance_id": self.commercial_acceptance_id,
            "ready_for_manual_invoice": self.ready_for_manual_invoice,
            "ready_for_manual_project_kickoff": self.ready_for_manual_project_kickoff,
            "manual_invoice_required": self.manual_invoice_required,
            "manual_project_kickoff_required": self.manual_project_kickoff_required,
            "invoice_created": False,
            "payment_link_created": False,
            "payment_state_changed": False,
            "project_created": False,
            "hvs_invoked": False,
            "render_started": False,
            "customer_contact_performed_by_system": False,
            "automation_allowed": False,
            "recommended_manual_action": self.recommended_manual_action,
        }


@dataclass(frozen=True)
class CommercialAcceptanceEvent:
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
class CommercialAcceptanceError:
    error_code: str
    error_detail: str
    blockers: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"error_code": self.error_code, "error_detail": self.error_detail, "blockers": list(self.blockers)}


def presentation_from_dict(data: dict[str, Any]) -> ProposalPresentationRecord:
    return ProposalPresentationRecord(**data)


def decision_from_dict(data: dict[str, Any]) -> CustomerDecisionRecord:
    value = dict(data)
    value["requested_changes"] = tuple(value.get("requested_changes", ()))
    value["accepted_total"] = None if value.get("accepted_total") is None else Decimal(str(value["accepted_total"]))
    return CustomerDecisionRecord(**value)


def acceptance_from_dict(data: dict[str, Any]) -> CommercialAcceptanceRecord:
    value = dict(data)
    for key in ("accepted_subtotal", "accepted_discount", "accepted_tax", "accepted_total"):
        value[key] = Decimal(str(value[key]))
    return CommercialAcceptanceRecord(**value)


def canonical_content_hash(payload: dict[str, Any]) -> str:
    return _hash_record({"payload": canonical_json(payload)})
