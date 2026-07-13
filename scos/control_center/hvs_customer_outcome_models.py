"""Immutable Stage 8H customer-success evidence models.

Models contain no transport, filesystem, media, or external-system behaviour.
They validate the small, inspectable evidence records used by the local service.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from .hvs_post_delivery_support_models import _safe_customer_reference, _safe_date, _safe_text
from .hvs_rerender_dispatch_models import _safe_id


CUSTOMER_SUCCESS_SCHEMA_VERSION = "scos-hvs.customer-success.v1/1.0.0"
CUSTOMER_SUCCESS_EVENT_SCHEMA_VERSION = "scos-hvs.customer-success-event.v1/1.0.0"
PRIORITY_SCORE_VERSION = "scos-hvs.opportunity-priority/1.0.0"

OUTCOME_RECORDED = "OUTCOME_RECORDED"
OUTCOME_INCOMPLETE = "OUTCOME_INCOMPLETE"
OUTCOME_DISPUTED = "OUTCOME_DISPUTED"
OUTCOME_SUPERSEDED = "OUTCOME_SUPERSEDED"
ALLOWED_OUTCOME_STATUSES = (OUTCOME_RECORDED, OUTCOME_INCOMPLETE, OUTCOME_DISPUTED, OUTCOME_SUPERSEDED)

CONSENT_PENDING = "CONSENT_PENDING"
CONSENT_GRANTED = "CONSENT_GRANTED"
CONSENT_DENIED = "CONSENT_DENIED"
CONSENT_REVOKED = "CONSENT_REVOKED"
CONSENT_EXPIRED = "CONSENT_EXPIRED"
CONSENT_SUPERSEDED = "CONSENT_SUPERSEDED"
ALLOWED_CONSENT_STATUSES = (CONSENT_PENDING, CONSENT_GRANTED, CONSENT_DENIED, CONSENT_REVOKED, CONSENT_EXPIRED, CONSENT_SUPERSEDED)

RENEWAL = "RENEWAL"
FOLLOW_ON_PROJECT = "FOLLOW_ON_PROJECT"
UPSELL = "UPSELL"
REFERRAL = "REFERRAL"
SUPPORT_FOLLOW_UP = "SUPPORT_FOLLOW_UP"
NO_OPPORTUNITY = "NO_OPPORTUNITY"
ALLOWED_OPPORTUNITY_TYPES = (RENEWAL, FOLLOW_ON_PROJECT, UPSELL, REFERRAL, SUPPORT_FOLLOW_UP, NO_OPPORTUNITY)

IDENTIFIED = "IDENTIFIED"
QUALIFIED = "QUALIFIED"
DEFERRED = "DEFERRED"
DECLINED = "DECLINED"
CONVERTED = "CONVERTED"
CANCELLED = "CANCELLED"
SUPERSEDED = "SUPERSEDED"
ALLOWED_OPPORTUNITY_STATUSES = (IDENTIFIED, QUALIFIED, DEFERRED, DECLINED, CONVERTED, CANCELLED, SUPERSEDED)

HIGH = "HIGH"
MEDIUM = "MEDIUM"
LOW = "LOW"
BLOCKED = "BLOCKED"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def stable_id(prefix: str, payload: dict[str, Any]) -> str:
    return prefix + "-" + hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()[:32]


def _safe_optional_text(field: str, value: str | None, *, allow_slash: bool = False) -> str | None:
    if value is None or value == "":
        return None
    _safe_text(field, value, allow_slash=allow_slash)
    return value


def _safe_string_tuple(field: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise ValueError(f"{field} must be a tuple")
    for value in values:
        _safe_id(field, value)
    return values


def _safe_rating(field: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
        raise ValueError(f"{field} must be an integer from 1 through 5")
    return value


def normalize_money(value: Any, *, field: str) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        money = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a decimal amount") from exc
    if not money.is_finite() or money < Decimal("0"):
        raise ValueError(f"{field} must be a non-negative finite decimal")
    return money


def normalize_currency(value: str | None, *, required: bool) -> str | None:
    if value is None or value == "":
        if required:
            raise ValueError("currency is required when estimated_value is present")
        return None
    if not isinstance(value, str) or re.fullmatch(r"[A-Z]{3}", value) is None:
        raise ValueError("currency must be an uppercase ISO-4217 code")
    return value


@dataclass(frozen=True)
class CustomerOutcomeReview:
    outcome_review_id: str
    project_id: str
    revision_id: str
    revised_delivery_id: str
    release_execution_id: str
    receipt_confirmation_id: str
    post_delivery_closure_id: str
    commercial_closure_id: str
    customer_reference: str
    recorded_by_operator_id: str
    review_status: str
    satisfaction_rating: int
    delivery_quality_rating: int
    communication_rating: int
    timeliness_rating: int
    business_outcome_status: str
    business_outcome_summary: str
    measurable_outcomes: tuple[dict[str, str], ...]
    unresolved_concerns: tuple[str, ...]
    evidence_references: tuple[str, ...]
    metadata: dict[str, str]
    idempotency_key: str
    recorded_at: str
    created_at: str
    schema_version: str = CUSTOMER_SUCCESS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CUSTOMER_SUCCESS_SCHEMA_VERSION:
            raise ValueError("outcome review schema version mismatch")
        if self.review_status not in ALLOWED_OUTCOME_STATUSES:
            raise ValueError("invalid outcome review status")
        for field in ("outcome_review_id", "project_id", "revision_id", "revised_delivery_id", "release_execution_id", "receipt_confirmation_id", "post_delivery_closure_id", "commercial_closure_id", "recorded_by_operator_id", "idempotency_key"):
            _safe_id(field, getattr(self, field))
        _safe_customer_reference("customer_reference", self.customer_reference)
        for field in ("satisfaction_rating", "delivery_quality_rating", "communication_rating", "timeliness_rating"):
            _safe_rating(field, getattr(self, field))
        _safe_text("business_outcome_status", self.business_outcome_status)
        _safe_text("business_outcome_summary", self.business_outcome_summary)
        for item in self.measurable_outcomes:
            if not isinstance(item, dict) or set(item) - {"metric", "value", "unit"} or not item.get("metric"):
                raise ValueError("measurable outcomes must contain only metric, value, and unit")
            for key, value in item.items():
                _safe_text(f"measurable_outcome.{key}", value)
        for item in self.unresolved_concerns:
            _safe_text("unresolved_concern", item)
        _safe_string_tuple("evidence_reference", self.evidence_references)
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dict")
        _safe_date("recorded_at", self.recorded_at)
        _safe_date("created_at", self.created_at)

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["measurable_outcomes"] = [dict(value) for value in self.measurable_outcomes]
        data["unresolved_concerns"] = list(self.unresolved_concerns)
        data["evidence_references"] = list(self.evidence_references)
        return data


@dataclass(frozen=True)
class PortfolioConsent:
    portfolio_consent_id: str
    outcome_review_id: str
    project_id: str
    revised_delivery_id: str
    customer_reference: str
    consent_status: str
    consent_scope: str
    allowed_artifact_references: tuple[str, ...]
    allowed_formats: tuple[str, ...]
    allowed_usage_contexts: tuple[str, ...]
    brand_name_usage: bool
    logo_usage: bool
    customer_name_usage: bool
    performance_metric_usage: bool
    anonymization_required: bool
    anonymization_rules: tuple[str, ...]
    attribution_requirement: str | None
    valid_from: str
    expires_at: str | None
    recorded_by_operator_id: str
    consent_basis: str
    evidence_references: tuple[str, ...]
    idempotency_key: str
    created_at: str
    schema_version: str = CUSTOMER_SUCCESS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CUSTOMER_SUCCESS_SCHEMA_VERSION or self.consent_status not in ALLOWED_CONSENT_STATUSES:
            raise ValueError("invalid portfolio consent")
        for field in ("portfolio_consent_id", "outcome_review_id", "project_id", "revised_delivery_id", "recorded_by_operator_id", "idempotency_key"):
            _safe_id(field, getattr(self, field))
        _safe_customer_reference("customer_reference", self.customer_reference)
        _safe_text("consent_scope", self.consent_scope)
        _safe_string_tuple("allowed_artifact_reference", self.allowed_artifact_references)
        _safe_string_tuple("allowed_format", self.allowed_formats)
        _safe_string_tuple("allowed_usage_context", self.allowed_usage_contexts)
        for rule in self.anonymization_rules:
            _safe_text("anonymization_rule", rule)
        if self.anonymization_required and not self.anonymization_rules:
            raise ValueError("anonymization rules are required when anonymization is required")
        if self.consent_status == CONSENT_GRANTED and (not self.allowed_artifact_references or not self.allowed_usage_contexts):
            raise ValueError("granted portfolio consent requires explicit artifacts and usage contexts")
        _safe_optional_text("attribution_requirement", self.attribution_requirement)
        _safe_date("valid_from", self.valid_from)
        if self.expires_at:
            _safe_date("expires_at", self.expires_at)
            if self.expires_at < self.valid_from:
                raise ValueError("portfolio consent expiry precedes valid_from")
        _safe_text("consent_basis", self.consent_basis)
        _safe_string_tuple("evidence_reference", self.evidence_references)
        _safe_date("created_at", self.created_at)

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        for field in ("allowed_artifact_references", "allowed_formats", "allowed_usage_contexts", "anonymization_rules", "evidence_references"):
            data[field] = list(data[field])
        return data


@dataclass(frozen=True)
class TestimonialConsent:
    testimonial_consent_id: str
    outcome_review_id: str
    project_id: str
    customer_reference: str
    testimonial_reference: str
    testimonial_text_hash: str
    testimonial_text_preview: str | None
    consent_status: str
    approved_usage_contexts: tuple[str, ...]
    approved_edits: tuple[str, ...]
    attribution_name: str | None
    attribution_role: str | None
    attribution_company: str | None
    anonymization_required: bool
    valid_from: str
    expires_at: str | None
    recorded_by_operator_id: str
    consent_basis: str
    evidence_references: tuple[str, ...]
    idempotency_key: str
    created_at: str
    schema_version: str = CUSTOMER_SUCCESS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CUSTOMER_SUCCESS_SCHEMA_VERSION or self.consent_status not in ALLOWED_CONSENT_STATUSES:
            raise ValueError("invalid testimonial consent")
        for field in ("testimonial_consent_id", "outcome_review_id", "project_id", "testimonial_reference", "recorded_by_operator_id", "idempotency_key"):
            _safe_id(field, getattr(self, field))
        _safe_customer_reference("customer_reference", self.customer_reference)
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", self.testimonial_text_hash):
            raise ValueError("testimonial_text_hash must be sha256:<64 lowercase hex>")
        _safe_optional_text("testimonial_text_preview", self.testimonial_text_preview)
        _safe_string_tuple("approved_usage_context", self.approved_usage_contexts)
        _safe_string_tuple("approved_edit", self.approved_edits)
        if self.consent_status == CONSENT_GRANTED and not self.approved_usage_contexts:
            raise ValueError("granted testimonial consent requires usage contexts")
        for field in ("attribution_name", "attribution_role", "attribution_company"):
            _safe_optional_text(field, getattr(self, field))
        _safe_date("valid_from", self.valid_from)
        if self.expires_at:
            _safe_date("expires_at", self.expires_at)
            if self.expires_at < self.valid_from:
                raise ValueError("testimonial consent expiry precedes valid_from")
        _safe_text("consent_basis", self.consent_basis)
        _safe_string_tuple("evidence_reference", self.evidence_references)
        _safe_date("created_at", self.created_at)

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        for field in ("approved_usage_contexts", "approved_edits", "evidence_references"):
            data[field] = list(data[field])
        return data


@dataclass(frozen=True)
class ConsentRevocation:
    revocation_id: str
    consent_type: str
    consent_id: str
    revoked_by_operator_id: str
    revocation_reason: str
    evidence_references: tuple[str, ...]
    idempotency_key: str
    created_at: str
    schema_version: str = CUSTOMER_SUCCESS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CUSTOMER_SUCCESS_SCHEMA_VERSION or self.consent_type not in ("PORTFOLIO", "TESTIMONIAL"):
            raise ValueError("invalid consent revocation")
        for field in ("revocation_id", "consent_id", "revoked_by_operator_id", "idempotency_key"):
            _safe_id(field, getattr(self, field))
        _safe_text("revocation_reason", self.revocation_reason)
        _safe_string_tuple("evidence_reference", self.evidence_references)
        _safe_date("created_at", self.created_at)

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["evidence_references"] = list(self.evidence_references)
        return data


@dataclass(frozen=True)
class Opportunity:
    opportunity_id: str
    opportunity_type: str
    project_id: str
    customer_reference: str
    commercial_closure_id: str
    outcome_review_id: str
    source_issue_ids: tuple[str, ...]
    source_evidence_references: tuple[str, ...]
    opportunity_status: str
    opportunity_summary: str
    recommended_offer: str | None
    estimated_value: Decimal | None
    currency: str | None
    confidence_level: int
    urgency: str
    target_follow_up_date: str | None
    priority_score: int | None
    score_version: str
    scoring_reasons: tuple[str, ...]
    assigned_operator_id: str | None
    created_by_operator_id: str
    idempotency_key: str
    created_at: str
    schema_version: str = CUSTOMER_SUCCESS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CUSTOMER_SUCCESS_SCHEMA_VERSION or self.opportunity_type not in ALLOWED_OPPORTUNITY_TYPES or self.opportunity_status not in ALLOWED_OPPORTUNITY_STATUSES:
            raise ValueError("invalid opportunity")
        for field in ("opportunity_id", "project_id", "commercial_closure_id", "outcome_review_id", "created_by_operator_id", "idempotency_key"):
            _safe_id(field, getattr(self, field))
        _safe_customer_reference("customer_reference", self.customer_reference)
        _safe_string_tuple("source_issue_id", self.source_issue_ids)
        _safe_string_tuple("source_evidence_reference", self.source_evidence_references)
        _safe_text("opportunity_summary", self.opportunity_summary)
        _safe_optional_text("recommended_offer", self.recommended_offer)
        if self.estimated_value is not None and (not isinstance(self.estimated_value, Decimal) or self.estimated_value < 0):
            raise ValueError("estimated_value must be a non-negative Decimal")
        normalize_currency(self.currency, required=self.estimated_value is not None)
        if isinstance(self.confidence_level, bool) or not isinstance(self.confidence_level, int) or not 1 <= self.confidence_level <= 5:
            raise ValueError("confidence_level must be an integer from 1 through 5")
        if self.urgency not in ("LOW", "MEDIUM", "HIGH"):
            raise ValueError("urgency must be LOW, MEDIUM, or HIGH")
        if self.target_follow_up_date:
            _safe_date("target_follow_up_date", self.target_follow_up_date)
        if self.priority_score is not None and (not isinstance(self.priority_score, int) or not 0 <= self.priority_score <= 100):
            raise ValueError("priority_score must be an integer from 0 through 100")
        _safe_text("score_version", self.score_version, allow_slash=True)
        for reason in self.scoring_reasons:
            _safe_text("scoring_reason", reason)
        if self.assigned_operator_id:
            _safe_id("assigned_operator_id", self.assigned_operator_id)
        _safe_date("created_at", self.created_at)

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["estimated_value"] = str(self.estimated_value) if self.estimated_value is not None else None
        for field in ("source_issue_ids", "source_evidence_references", "scoring_reasons"):
            data[field] = list(data[field])
        return data


@dataclass(frozen=True)
class OpportunityQualification:
    qualification_id: str
    opportunity_id: str
    status: str
    confirmed_by_operator_id: str
    reason: str
    idempotency_key: str
    created_at: str
    schema_version: str = CUSTOMER_SUCCESS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CUSTOMER_SUCCESS_SCHEMA_VERSION or self.status not in ALLOWED_OPPORTUNITY_STATUSES:
            raise ValueError("invalid opportunity qualification")
        for field in ("qualification_id", "opportunity_id", "confirmed_by_operator_id", "idempotency_key"):
            _safe_id(field, getattr(self, field))
        _safe_text("reason", self.reason)
        _safe_date("created_at", self.created_at)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)
