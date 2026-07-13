"""Immutable local-only Stage 8I commercial proposal preparation models."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .hvs_customer_outcome_models import validate_calendar_date
from .hvs_invoice_models import money_to_json


COMMERCIAL_PROPOSAL_SCHEMA_VERSION = "scos-hvs.commercial-proposal.v1/1.0.0"
COMMERCIAL_PROPOSAL_EVENT_SCHEMA_VERSION = "scos-hvs.commercial-proposal-event.v1/1.0.0"

DRAFT = "DRAFT"
NEEDS_OPERATOR_INPUT = "NEEDS_OPERATOR_INPUT"
READY_FOR_INTERNAL_REVIEW = "READY_FOR_INTERNAL_REVIEW"
APPROVED_FOR_MANUAL_PRESENTATION = "APPROVED_FOR_MANUAL_PRESENTATION"
REJECTED = "REJECTED"
CANCELLED = "CANCELLED"
EXPIRED = "EXPIRED"
ALLOWED_PROPOSAL_STATUSES = (DRAFT, NEEDS_OPERATOR_INPUT, READY_FOR_INTERNAL_REVIEW, APPROVED_FOR_MANUAL_PRESENTATION, REJECTED, CANCELLED, EXPIRED)

READY = "READY"
READINESS_NEEDS_OPERATOR_INPUT = "NEEDS_OPERATOR_INPUT"
READINESS_BLOCKED = "BLOCKED"
READINESS_EXPIRED = "EXPIRED"

EVT_PROPOSAL_PREPARED = "PROPOSAL_PREPARED"
EVT_PROPOSAL_SUBMITTED = "PROPOSAL_SUBMITTED"
EVT_PROPOSAL_APPROVED = "PROPOSAL_APPROVED"
EVT_PROPOSAL_REJECTED = "PROPOSAL_REJECTED"
EVT_PROPOSAL_CANCELLED = "PROPOSAL_CANCELLED"
EVT_MANUAL_HANDOFF_CREATED = "MANUAL_HANDOFF_CREATED"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def stable_id(prefix: str, payload: Any) -> str:
    return prefix + "-" + hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:32]


def _safe_text(field: str, value: Any, *, required: bool = True) -> str:
    if value is None or value == "":
        if required:
            raise ValueError(f"{field} is required")
        return ""
    if not isinstance(value, str) or len(value) > 512:
        raise ValueError(f"{field} must be a bounded string")
    if "\x00" in value or "\r" in value or "\n" in value or ".." in value or "\\" in value:
        raise ValueError(f"{field} contains unsafe text")
    return value


@dataclass(frozen=True)
class ProposalDeliverable:
    description: str
    quantity: Decimal
    unit: str
    evidence_reference: str

    def to_dict(self) -> dict[str, str]:
        return {"description": self.description, "quantity": str(self.quantity), "unit": self.unit, "evidence_reference": self.evidence_reference}


@dataclass(frozen=True)
class ProposalLineItem:
    line_item_id: str
    description: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal
    scope_key: str

    def to_dict(self, *, currency: str) -> dict[str, str]:
        return {"line_item_id": self.line_item_id, "description": self.description, "quantity": str(self.quantity), "unit_price": money_to_json(self.unit_price, currency), "line_total": money_to_json(self.line_total, currency), "scope_key": self.scope_key}


@dataclass(frozen=True)
class ProposalPreparation:
    schema_version: str
    proposal_preparation_id: str
    commercial_scope_id: str
    project_id: str
    customer_reference: str
    opportunity_id: str
    opportunity_type: str
    source_outcome_review_id: str
    source_delivery_lineage_id: str
    source_delivery_record_id: str
    source_artifact_id: str
    source_artifact_sha256: str
    source_commercial_closure_id: str
    proposal_status: str
    title: str
    objective: str
    scope_summary: str
    deliverables: tuple[ProposalDeliverable, ...]
    exclusions: tuple[str, ...]
    assumptions: tuple[str, ...]
    line_items: tuple[ProposalLineItem, ...]
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    currency: str
    tax_treatment: str
    validity_start_date: str
    validity_end_date: str
    estimated_start_date: str | None
    estimated_completion_date: str | None
    payment_terms: str
    revision_terms: str
    dependency_notes: tuple[str, ...]
    risk_notes: tuple[str, ...]
    operator_review_required: bool
    manual_presentation_required: bool
    automation_allowed: bool
    deterministic_content_hash: str
    created_at: str
    updated_at: str
    decision_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["deliverables"] = [item.to_dict() for item in self.deliverables]
        data["line_items"] = [item.to_dict(currency=self.currency) for item in self.line_items]
        for key in ("subtotal", "discount_amount", "tax_amount", "total_amount"):
            data[key] = money_to_json(getattr(self, key), self.currency)
        for key in ("exclusions", "assumptions", "dependency_notes", "risk_notes"):
            data[key] = list(getattr(self, key))
        data["automation_allowed"] = False
        return data


@dataclass(frozen=True)
class ProposalReadinessResult:
    proposal_preparation_id: str
    state: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    recommended_manual_action: str
    automation_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"proposal_preparation_id": self.proposal_preparation_id, "state": self.state, "blockers": list(self.blockers), "warnings": list(self.warnings), "recommended_manual_action": self.recommended_manual_action, "automation_allowed": False}


@dataclass(frozen=True)
class CommercialHandoffPackage:
    handoff_id: str
    proposal_preparation_id: str
    commercial_scope_id: str
    approved_content_hash: str
    approval_event_id: str
    source_lineage: dict[str, str]
    currency: str
    total_amount: Decimal
    manual_presentation_required: bool
    proposal_sent: bool
    customer_contacted: bool
    customer_acceptance_recorded: bool
    invoice_created: bool
    payment_link_created: bool
    payment_state_changed: bool
    hvs_invoked: bool
    automation_allowed: bool
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {**self.__dict__, "source_lineage": dict(self.source_lineage), "total_amount": money_to_json(self.total_amount, self.currency), "automation_allowed": False}


@dataclass(frozen=True)
class CommercialProposalEvent:
    schema_version: str
    event_id: str
    event_type: str
    subject_id: str
    operator_id: str
    recorded_at: str
    record: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def proposal_from_dict(data: dict[str, Any]) -> ProposalPreparation:
    currency = data["currency"]
    return ProposalPreparation(
        **{key: data[key] for key in ("schema_version", "proposal_preparation_id", "commercial_scope_id", "project_id", "customer_reference", "opportunity_id", "opportunity_type", "source_outcome_review_id", "source_delivery_lineage_id", "source_delivery_record_id", "source_artifact_id", "source_artifact_sha256", "source_commercial_closure_id", "proposal_status", "title", "objective", "scope_summary", "currency", "tax_treatment", "validity_start_date", "validity_end_date", "estimated_start_date", "estimated_completion_date", "payment_terms", "revision_terms", "operator_review_required", "manual_presentation_required", "automation_allowed", "deterministic_content_hash", "created_at", "updated_at")},
        deliverables=tuple(ProposalDeliverable(item["description"], Decimal(str(item["quantity"])), item["unit"], item["evidence_reference"]) for item in data["deliverables"]),
        exclusions=tuple(data["exclusions"]), assumptions=tuple(data["assumptions"]), dependency_notes=tuple(data.get("dependency_notes", ())), risk_notes=tuple(data.get("risk_notes", ())),
        line_items=tuple(ProposalLineItem(item["line_item_id"], item["description"], Decimal(str(item["quantity"])), Decimal(str(item["unit_price"])), Decimal(str(item["line_total"])), item["scope_key"]) for item in data["line_items"]),
        subtotal=Decimal(str(data["subtotal"])), discount_amount=Decimal(str(data["discount_amount"])), tax_amount=Decimal(str(data["tax_amount"])), total_amount=Decimal(str(data["total_amount"])),
        decision_reason=data.get("decision_reason"),
    )
