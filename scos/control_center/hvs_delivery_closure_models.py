"""SCOS <-> HVS Stage 7 delivery closure models."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .hvs_local_delivery_models import _require_allowed, _require_nonempty, _sha256_hex16

CUSTOMER_RECEIPT_EVIDENCE_SCHEMA_VERSION = (
    "scos-hvs.customer-receipt-evidence.v1/1.0.0"
)
DELIVERY_REVISION_REQUEST_SCHEMA_VERSION = (
    "scos-hvs.delivery-revision-request.v1/1.0.0"
)
DELIVERY_CLOSURE_SCHEMA_VERSION = "scos-hvs.delivery-closure.v1/1.0.0"

REC_NOT_RECORDED = "NOT_RECORDED"
REC_ACKNOWLEDGED = "RECEIPT_ACKNOWLEDGED"
REC_REVISION_REQUESTED = "REVISION_REQUESTED"
REC_DELIVERY_REJECTED = "DELIVERY_REJECTED"
REC_UNCONFIRMED = "RECEIPT_UNCONFIRMED"
ALLOWED_RECEIPT_STATUSES = (
    REC_NOT_RECORDED,
    REC_ACKNOWLEDGED,
    REC_REVISION_REQUESTED,
    REC_DELIVERY_REJECTED,
    REC_UNCONFIRMED,
)

SOURCE_VERBAL = "verbal_confirmation"
SOURCE_IN_PERSON = "in_person_confirmation"
SOURCE_EMAIL_OBSERVED = "customer_email_observed_by_operator"
SOURCE_MESSAGE_OBSERVED = "customer_message_observed_by_operator"
SOURCE_PORTAL_OBSERVED = "customer_portal_observed_by_operator"
SOURCE_SIGNED_DOC_OBSERVED = "signed_document_observed_by_operator"
SOURCE_TRACKING_OBSERVED = "delivery_tracking_observed_by_operator"
SOURCE_NONE_AVAILABLE = "no_confirmation_available"
SOURCE_OTHER_OBSERVED = "other_operator_observed"
ALLOWED_EVIDENCE_SOURCE_TYPES = (
    SOURCE_VERBAL,
    SOURCE_IN_PERSON,
    SOURCE_EMAIL_OBSERVED,
    SOURCE_MESSAGE_OBSERVED,
    SOURCE_PORTAL_OBSERVED,
    SOURCE_SIGNED_DOC_OBSERVED,
    SOURCE_TRACKING_OBSERVED,
    SOURCE_NONE_AVAILABLE,
    SOURCE_OTHER_OBSERVED,
)

CHANGE_TEXT = "text"
CHANGE_CAPTION = "caption"
CHANGE_TIMING = "timing"
CHANGE_IMAGE = "image"
CHANGE_VIDEO = "video"
CHANGE_AUDIO = "audio"
CHANGE_BRANDING = "branding"
CHANGE_FORMAT = "format"
CHANGE_FACTUAL = "factual_correction"
CHANGE_OTHER = "other"
ALLOWED_CHANGE_CATEGORIES = (
    CHANGE_TEXT,
    CHANGE_CAPTION,
    CHANGE_TIMING,
    CHANGE_IMAGE,
    CHANGE_VIDEO,
    CHANGE_AUDIO,
    CHANGE_BRANDING,
    CHANGE_FORMAT,
    CHANGE_FACTUAL,
    CHANGE_OTHER,
)

CLOSURE_OPEN = "OPEN"
CLOSURE_ACCEPTED = "ACCEPTED_AND_CLOSED"
CLOSURE_REVISION_OPEN = "REVISION_OPEN"
CLOSURE_REJECTED = "REJECTED_AND_CLOSED"
CLOSURE_WITHOUT_CONFIRMATION = "CLOSED_WITHOUT_CONFIRMATION"
CLOSURE_CANCELLED = "CANCELLED_BY_OPERATOR"
ALLOWED_CLOSURE_STATUSES = (
    CLOSURE_OPEN,
    CLOSURE_ACCEPTED,
    CLOSURE_REVISION_OPEN,
    CLOSURE_REJECTED,
    CLOSURE_WITHOUT_CONFIRMATION,
    CLOSURE_CANCELLED,
)

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_RAW_PAYLOAD_MARKERS = (
    "-----original message-----",
    "from:",
    "to:",
    "subject:",
    "message-id:",
    "mime-version:",
    "begin forwarded message",
    "chat export",
    "transcript:",
)


def _normalize_text(value: str | None) -> str:
    return " ".join(_CONTROL_RE.sub(" ", str(value or "")).split())


def _safe_short_label(field: str, value: str | None, max_len: int = 128) -> str:
    text = _normalize_text(value)
    _require_nonempty(field, text)
    if len(text) > max_len:
        raise ValueError(f"{field} is too long")
    if any(ch in text for ch in ("/", "\\", "\x00")) or ".." in text:
        raise ValueError(f"{field} must be a safe short label")
    return text


def _safe_optional_label(field: str, value: str | None, max_len: int = 256) -> str | None:
    if value is None:
        return None
    text = _normalize_text(value)
    if not text:
        return None
    if len(text) > max_len:
        raise ValueError(f"{field} is too long")
    if "\x00" in text:
        raise ValueError(f"{field} is unsafe")
    return text


def _safe_summary(field: str, value: str | None, max_len: int = 2000) -> str:
    text = _normalize_text(value)
    _require_nonempty(field, text)
    if len(text) > max_len:
        raise ValueError(f"{field} is too long")
    lowered = text.lower()
    marker_count = sum(1 for marker in _RAW_PAYLOAD_MARKERS if marker in lowered)
    if marker_count >= 2 or "\n\n" in str(value or ""):
        raise ValueError(f"{field} must be a short operator summary, not raw payload")
    return text


def normalize_categories(categories: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    seen: list[str] = []
    for category in categories:
        cat = _normalize_text(category)
        _require_allowed("change_category", cat, ALLOWED_CHANGE_CATEGORIES)
        if cat not in seen:
            seen.append(cat)
    if not seen:
        raise ValueError("at least one change category is required")
    return tuple(sorted(seen))


def stable_receipt_evidence_id(
    *,
    delivery_record_id: str,
    package_id: str,
    artifact_sha256: str,
    receipt_status: str,
    evidence_source_type: str,
    statement_text: str,
    contract_version: str = CUSTOMER_RECEIPT_EVIDENCE_SCHEMA_VERSION,
) -> str:
    canon = "|".join(
        [
            "customer-receipt",
            delivery_record_id,
            package_id,
            artifact_sha256,
            receipt_status,
            _normalize_text(evidence_source_type).lower(),
            _sha256_hex16(_normalize_text(statement_text).lower()),
            contract_version,
        ]
    )
    return "scos-hvs-receipt-" + _sha256_hex16(canon)


def stable_revision_request_id(
    *,
    receipt_evidence_id: str,
    package_id: str,
    artifact_sha256: str,
    revision_summary: str,
    requested_change_categories: tuple[str, ...],
    revision_round: int,
    contract_version: str = DELIVERY_REVISION_REQUEST_SCHEMA_VERSION,
) -> str:
    canon = "|".join(
        [
            "delivery-revision",
            receipt_evidence_id,
            package_id,
            artifact_sha256,
            _normalize_text(revision_summary).lower(),
            ",".join(sorted(requested_change_categories)),
            str(revision_round),
            contract_version,
        ]
    )
    return "scos-hvs-revision-" + _sha256_hex16(canon)


def stable_closure_id(
    *,
    receipt_evidence_id: str,
    delivery_record_id: str,
    package_id: str,
    artifact_sha256: str,
    closure_status: str,
    contract_version: str = DELIVERY_CLOSURE_SCHEMA_VERSION,
) -> str:
    canon = "|".join(
        [
            "delivery-closure",
            receipt_evidence_id,
            delivery_record_id,
            package_id,
            artifact_sha256,
            closure_status,
            contract_version,
        ]
    )
    return "scos-hvs-closure-" + _sha256_hex16(canon)


@dataclass(frozen=True)
class HVSCustomerReceiptEvidence:
    schema_version: str
    receipt_evidence_id: str
    package_id: str
    delivery_record_id: str
    approval_request_id: str
    packet_id: str | None
    project_id: str | None
    artifact_sha256: str
    receipt_status: str
    evidence_source_type: str
    operator_id: str
    customer_reference_label: str
    customer_statement_summary: str
    revision_summary: str | None
    rejection_reason: str | None
    external_reference: str | None
    evidence_observed_at: str
    recorded_at: str
    operator_asserted: bool
    externally_verified_by_scos: bool
    customer_contact_executed_by_scos: bool
    automation_allowed: bool
    identity_inputs: dict[str, Any]
    audit_correlation: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class HVSDeliveryRevisionRequest:
    schema_version: str
    revision_request_id: str
    receipt_evidence_id: str
    package_id: str
    project_id: str | None
    artifact_sha256: str
    operator_id: str
    revision_summary: str
    requested_change_categories: list[str]
    priority: str
    due_date: str | None
    revision_round: int
    status: str
    rendering_not_started: bool
    automation_allowed: bool
    recorded_at: str
    audit_correlation: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class HVSDeliveryClosure:
    schema_version: str
    closure_id: str
    receipt_evidence_id: str
    delivery_record_id: str
    package_id: str
    approval_request_id: str
    project_id: str | None
    artifact_sha256: str
    closure_status: str
    operator_id: str
    closure_reason: str
    accepted_by_customer: bool
    payment_confirmed: bool
    revenue_recognized_by_scos: bool
    invoice_created_by_scos: bool
    customer_contact_executed_by_scos: bool
    automation_allowed: bool
    manual_follow_up_required: bool
    open_revision_request_id: str | None
    recorded_at: str
    identity_inputs: dict[str, Any]
    audit_correlation: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)
