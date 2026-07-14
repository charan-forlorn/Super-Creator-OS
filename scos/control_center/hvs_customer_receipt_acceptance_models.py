"""SCOS <-> Hermes Video Studio (HVS) — Stage 8P customer receipt confirmation,
delivered-artifact reverification, and acceptance / issue-intake gate.

Stage 8P runs ONLY after Stage 8O has recorded an actual manual delivery. It
provides a deterministic, local-only, operator-controlled contract for what
happened AFTER delivery:

    A. whether the customer confirmed receipt,
    B. whether the received artifact identity matches the delivered artifact,
    C. whether the customer accepted the delivery,
    D. whether the customer rejected it,
    E. whether the customer raised an issue / revision-review request,
    F. whether no customer response has yet been received.

Stage 8P is EVIDENCE, DECISION-INTAKE and AUTHORIZATION-BOUNDARY only. It:

  * never contacts the customer, sends reminders, or performs any transport,
  * never automatically accepts work, opens a revision, closes a project,
  * never mutates payment / invoice state,
  * never invokes HVS, renders, delivers, uploads, or publishes,
  * never creates a dispute automatically (issue intake != dispute),
  * never creates a Stage 8B revision request automatically
    (revision-review request != revision).

It binds every record to one Stage 8O actual-delivery record, one delivery
authorization, one delivery package, and the exact artifact SHA-256 — reusing
the repository's deterministic identity helpers (``canonical_json`` /
``stable_id``) and the safe-text discipline of Stage 8O. ``automation_allowed``
is always ``False``. No clock, no random, no uuid, no network, no subprocess.

Local-first, deterministic, stdlib-only.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from .hvs_commercial_proposal_models import _safe_text, canonical_json, stable_id


# --- schema / identity -------------------------------------------------------
STAGE8P_SCHEMA_VERSION = "scos-hvs.stage8p.receipt-acceptance.v1/1.0.0"
RECEIPT_RECORD_SCHEMA_VERSION = "scos-hvs.stage8p.receipt-record.v1/1.0.0"
DECISION_RECORD_SCHEMA_VERSION = "scos-hvs.stage8p.decision-record.v1/1.0.0"
ISSUE_INTAKE_SCHEMA_VERSION = "scos-hvs.stage8p.issue-intake.v1/1.0.0"
REVISION_REVIEW_SCHEMA_VERSION = "scos-hvs.stage8p.revision-review.v1/1.0.0"
READINESS_SCHEMA_VERSION = "scos-hvs.stage8p.readiness.v1/1.0.0"
POST_RECEIPT_EVENT_SCHEMA_VERSION = "scos-hvs.stage8p.event.v1/1.0.0"

# Deterministic runtime root under the gitignored scos/work tree.
DEFAULT_RECEIPT_ACCEPTANCE_RELATIVE = "scos/work/hvs_stage8p_receipt_acceptance"

# --- Receipt status (Stage 8P receipt record) --------------------------------
RECEIPT_NOT_RECORDED = "NOT_RECORDED"
RECEIPT_PENDING = "RECEIPT_PENDING"
RECEIPT_CONFIRMED = "RECEIPT_CONFIRMED"
RECEIPT_REJECTED_AS_INVALID = "RECEIPT_REJECTED_AS_INVALID"
RECEIPT_IDENTITY_CONFLICT = "RECEIPT_IDENTITY_CONFLICT"
ALLOWED_RECEIPT_STATUSES = (
    RECEIPT_NOT_RECORDED,
    RECEIPT_PENDING,
    RECEIPT_CONFIRMED,
    RECEIPT_REJECTED_AS_INVALID,
    RECEIPT_IDENTITY_CONFLICT,
)

# --- Customer decision status ------------------------------------------------
DECISION_NO_DECISION = "NO_DECISION"
DECISION_ACCEPTED = "ACCEPTED"
DECISION_REJECTED = "REJECTED"
DECISION_ISSUE_REPORTED = "ISSUE_REPORTED"
DECISION_REVISION_REVIEW_REQUESTED = "REVISION_REVIEW_REQUESTED"
ALLOWED_DECISION_STATUSES = (
    DECISION_NO_DECISION,
    DECISION_ACCEPTED,
    DECISION_REJECTED,
    DECISION_ISSUE_REPORTED,
    DECISION_REVISION_REVIEW_REQUESTED,
)

# --- Receipt evidence types (controlled, never arbitrary) --------------------
EVIDENCE_CUSTOMER_WRITTEN_CONFIRMATION = "CUSTOMER_WRITTEN_CONFIRMATION"
EVIDENCE_CUSTOMER_VERBAL_RECORDED_BY_OPERATOR = "CUSTOMER_VERBAL_CONFIRMATION_RECORDED_BY_OPERATOR"
EVIDENCE_CUSTOMER_PORTAL_IMPORTED_MANUALLY = "CUSTOMER_PORTAL_CONFIRMATION_IMPORTED_MANUALLY"
EVIDENCE_SIGNED_RECEIPT_REFERENCE = "SIGNED_RECEIPT_REFERENCE"
EVIDENCE_DELIVERY_CHANNEL_ACKNOWLEDGEMENT = "DELIVERY_CHANNEL_ACKNOWLEDGEMENT"
EVIDENCE_OTHER_OPERATOR_VERIFIED = "OTHER_OPERATOR_VERIFIED_RECEIPT_EVIDENCE"
ALLOWED_RECEIPT_EVIDENCE_TYPES = (
    EVIDENCE_CUSTOMER_WRITTEN_CONFIRMATION,
    EVIDENCE_CUSTOMER_VERBAL_RECORDED_BY_OPERATOR,
    EVIDENCE_CUSTOMER_PORTAL_IMPORTED_MANUALLY,
    EVIDENCE_SIGNED_RECEIPT_REFERENCE,
    EVIDENCE_DELIVERY_CHANNEL_ACKNOWLEDGEMENT,
    EVIDENCE_OTHER_OPERATOR_VERIFIED,
)

# --- Aggregate post-receipt outcome (read-only view only) --------------------
OUTCOME_RECEIPT_NOT_CONFIRMED = "RECEIPT_NOT_CONFIRMED"
OUTCOME_RECEIPT_CONFIRMED_ACCEPTANCE_PENDING = "RECEIPT_CONFIRMED_ACCEPTANCE_PENDING"
OUTCOME_ACCEPTED_BY_CUSTOMER = "ACCEPTED_BY_CUSTOMER"
OUTCOME_REJECTED_BY_CUSTOMER = "REJECTED_BY_CUSTOMER"
OUTCOME_ISSUE_REPORTED = "ISSUE_REPORTED"
OUTCOME_REVISION_REVIEW_REQUESTED = "REVISION_REVIEW_REQUESTED"
OUTCOME_DELIVERY_IDENTITY_CONFLICT = "DELIVERY_IDENTITY_CONFLICT"
OUTCOME_BLOCKED = "BLOCKED"
ALLOWED_POST_RECEIPT_OUTCOMES = (
    OUTCOME_RECEIPT_NOT_CONFIRMED,
    OUTCOME_RECEIPT_CONFIRMED_ACCEPTANCE_PENDING,
    OUTCOME_ACCEPTED_BY_CUSTOMER,
    OUTCOME_REJECTED_BY_CUSTOMER,
    OUTCOME_ISSUE_REPORTED,
    OUTCOME_REVISION_REVIEW_REQUESTED,
    OUTCOME_DELIVERY_IDENTITY_CONFLICT,
    OUTCOME_BLOCKED,
)

# --- Append-only event types -------------------------------------------------
EVT_RECEIPT_CONFIRMED = "RECEIPT_CONFIRMED"
EVT_RECEIPT_REJECTED = "RECEIPT_REJECTED"
EVT_CUSTOMER_ACCEPTED = "CUSTOMER_ACCEPTED"
EVT_CUSTOMER_REJECTED = "CUSTOMER_REJECTED"
EVT_CUSTOMER_ISSUE_REPORTED = "CUSTOMER_ISSUE_REPORTED"
EVT_CUSTOMER_REVISION_REVIEW_REQUESTED = "CUSTOMER_REVISION_REVIEW_REQUESTED"
ALLOWED_POST_RECEIPT_EVENT_TYPES = (
    EVT_RECEIPT_CONFIRMED,
    EVT_RECEIPT_REJECTED,
    EVT_CUSTOMER_ACCEPTED,
    EVT_CUSTOMER_REJECTED,
    EVT_CUSTOMER_ISSUE_REPORTED,
    EVT_CUSTOMER_REVISION_REVIEW_REQUESTED,
)


# --- error codes -------------------------------------------------------------
ERR_MISSING_OPERATOR_ID = "missing_operator_id"
ERR_MISSING_DELIVERY_RECORD_ID = "missing_actual_delivery_record_id"
ERR_DELIVERY_RECORD_NOT_FOUND = "actual_delivery_record_not_found"
ERR_DELIVERY_RECORD_INVALID = "actual_delivery_record_invalid"
ERR_DELIVERY_NOT_FINAL = "actual_delivery_not_final"
ERR_DELIVERY_CANCELLED = "actual_delivery_cancelled"
ERR_AUTH_NOT_VALID = "delivery_authorization_not_valid"
ERR_PACKAGE_NOT_VALID = "delivery_package_not_valid"
ERR_ARTIFACT_NOT_VERIFIED = "source_artifact_not_verified"
ERR_ARTIFACT_SHA_MISMATCH = "artifact_sha_mismatch"
ERR_PACKAGE_ID_MISMATCH = "package_id_mismatch"
ERR_DELIVERY_RECORD_ID_MISMATCH = "delivery_record_id_mismatch"
ERR_CUSTOMER_REFERENCE_MISMATCH = "customer_reference_mismatch"
ERR_LEGACY_LINEAGE = "unknown_legacy_lineage"
ERR_CONFLICTING_RECEIPT = "conflicting_receipt_replay"
ERR_MISSING_CONFIRMATION_DATE = "missing_receipt_confirmation_date"
ERR_MISSING_EVIDENCE_REFERENCE = "missing_safe_evidence_reference"
ERR_UNSAFE_EVIDENCE_REFERENCE = "unsafe_evidence_reference"
ERR_INVALID_EVIDENCE_TYPE = "invalid_receipt_evidence_type"
ERR_UNSAFE_RECEIPT_BODY = "unsafe_receipt_body"
ERR_CUSTOMER_SHA_MISMATCH = "customer_artifact_sha_mismatch"
ERR_MISSING_DECISION_DATE = "missing_decision_date"
ERR_MISSING_REJECTION_REASON = "missing_rejection_reason"
ERR_MISSING_ISSUE_SUMMARY = "missing_issue_summary"
ERR_MISSING_REVISION_REASON = "missing_revision_review_reason"
ERR_DECISION_BEFORE_RECEIPT = "decision_before_receipt"
ERR_RECEIPT_IMMUTABLE = "receipt_record_immutable"
ERR_DECISION_CONFLICT = "changed_decision_conflict"
ERR_INVALID_TRANSITION = "invalid_decision_transition"
ERR_UNSAFE_ISSUE_CONTENT = "unsafe_issue_content"
ERR_INVALID_OUTCOME = "invalid_post_receipt_outcome"
ERR_UNKNOWN_SCHEMA_VERSION = "unknown_stage8p_schema_version"


# --- safe input normalization ------------------------------------------------
def _require_member(value: str, allowed: tuple[str, ...], code: str, detail: str) -> str:
    if value not in allowed:
        raise ValueError(f"{code}: {detail}")
    return value


def _bounded_optional(value: Any, *, max_len: int = 512, field_name: str = "field") -> str:
    """Like Stage 8O ``_immutable_text_optional`` but rejects CR/LF/null/control
    fragments without depending on Stage 8O's import surface (keeps 8P self-contained)."""
    if value is None or value == "":
        return ""
    if not isinstance(value, str) or len(value) > max_len:
        raise ValueError(f"{field_name} must be a bounded string")
    if "\x00" in value or "\r" in value or "\n" in value or "\\" in value or ".." in value:
        raise ValueError(f"{field_name} contains unsafe text")
    return value


def _require_operator_id(operator_id: str) -> str:
    value = _bounded_optional(operator_id, max_len=256, field_name="operator_id")
    if not value:
        raise ValueError("operator_id is required")
    return value


def _require_date(value: str, *, field_name: str) -> str:
    value = _bounded_optional(value, max_len=64, field_name=field_name)
    if not value:
        raise ValueError(f"{field_name} is required")
    return value


def _require_evidence_reference(value: str) -> str:
    """Reject secret-like / command-like / URL-like / traversal / injection
    evidence references.

    Evidence references are stable, non-sensitive pointers only (e.g. an
    operator-side note id, a signed-receipt reference id). They must never
    carry credentials, tokens, URLs with embedded secrets, shell metachars,
    path traversal, or newline / null log-injection content.
    """
    value = _bounded_optional(value, max_len=256, field_name="safe_evidence_reference")
    if not value:
        raise ValueError("safe_evidence_reference is required")
    lowered = value.lower()
    if "://" in lowered:
        raise ValueError("safe_evidence_reference must not be a URL")
    for token in ("password", "secret", "token=", "api_key", "apikey", "credential"):
        if token in lowered:
            raise ValueError("safe_evidence_reference must not contain secret-like text")
    if any(c in value for c in ("|", ";", "&", "$", "(", ")", "<", ">", "`", "\\", "..", "\n", "\r", "\x00")):
        raise ValueError("safe_evidence_reference must not contain command-like or unsafe characters")
    return value


def _require_issue_summary(value: str, *, max_len: int = 512) -> str:
    value = _bounded_optional(value, max_len=max_len, field_name="issue_summary")
    if not value:
        raise ValueError("issue summary is required")
    # Issue free-text must not carry CR/LF or null (log injection) but may carry
    # limited punctuation; reject control fragments only.
    if "\x00" in value or "\r" in value or "\n" in value:
        raise ValueError("issue summary must not contain newline or null content")
    for token in ("password", "secret", "token=", "api_key", "apikey", "credential"):
        if token in value.lower():
            raise ValueError("issue summary must not contain secret-like text")
    return value


def _immutable_hash(value: str) -> str:
    value = _bounded_optional(value, max_len=128, field_name="artifact_sha256")
    if len(value) != 64:
        raise ValueError("artifact_sha256 must be a 64-char SHA-256 hex digest")
    return value.lower()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Receipt record (immutable once confirmed)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CustomerReceiptRecord:
    """Operator-recorded evidence that the customer confirmed receipt of the
    Stage 8O-delivered artifact. Binds to one Stage 8O actual-delivery record,
    one authorization, one package, and the exact artifact SHA-256.

    Never implies acceptance. Never performs customer contact.
    """

    schema_version: str
    receipt_record_id: str
    project_id: str
    customer_reference: str
    source_render_completion_id: str
    source_delivery_package_id: str
    source_delivery_authorization_id: str
    source_actual_delivery_record_id: str
    source_delivery_lineage_id: str | None
    artifact_id: str
    artifact_sha256: str
    receipt_status: str
    receipt_evidence_type: str
    safe_evidence_reference: str
    customer_confirmed_artifact_sha256: str | None
    receipt_confirmation_date: str
    recorded_by_operator_id: str
    customer_contact_performed: bool = False
    external_action_performed: bool = False
    automation_allowed: bool = False
    deterministic_content_hash: str = ""
    informational_recorded_at: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != RECEIPT_RECORD_SCHEMA_VERSION:
            raise ValueError("receipt record schema version mismatch")
        if self.receipt_status not in ALLOWED_RECEIPT_STATUSES:
            raise ValueError(f"invalid receipt status {self.receipt_status!r}")
        if self.receipt_evidence_type not in ALLOWED_RECEIPT_EVIDENCE_TYPES:
            raise ValueError(f"invalid receipt evidence type {self.receipt_evidence_type!r}")

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


# ---------------------------------------------------------------------------
# Customer decision record (immutable once final)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CustomerDecisionRecord:
    """Operator-recorded customer decision (accept / reject / issue / revision
    review) bound to a confirmed receipt. Never closes the project, never
    mutates invoice/payment, never creates a revision or dispute.
    """

    schema_version: str
    customer_decision_id: str
    receipt_record_id: str
    actual_delivery_record_id: str
    delivery_package_id: str
    project_id: str
    customer_reference: str
    artifact_id: str
    artifact_sha256: str
    decision_status: str
    decision_date: str
    acceptance_scope: str | None
    rejection_reason: str | None
    issue_summary: str | None
    revision_review_reason: str | None
    safe_evidence_reference: str
    recorded_by_operator_id: str
    project_closed: bool = False
    revision_created: bool = False
    dispute_created: bool = False
    invoice_state_changed: bool = False
    payment_state_changed: bool = False
    customer_contact_performed: bool = False
    external_action_performed: bool = False
    automation_allowed: bool = False
    deterministic_content_hash: str = ""
    informational_recorded_at: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != DECISION_RECORD_SCHEMA_VERSION:
            raise ValueError("decision record schema version mismatch")
        if self.decision_status not in ALLOWED_DECISION_STATUSES:
            raise ValueError(f"invalid decision status {self.decision_status!r}")

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


# ---------------------------------------------------------------------------
# Issue intake (append-only, never claims validity / resolution)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DeliveryIssueIntake:
    """Operator-recorded customer-raised issue requiring internal review.

    Evidence intake only. Does NOT create a dispute, revision, or closure.
    """

    schema_version: str
    issue_intake_id: str
    receipt_record_id: str
    customer_decision_id: str | None
    actual_delivery_record_id: str
    delivery_package_id: str
    project_id: str
    customer_reference: str
    artifact_id: str
    artifact_sha256: str
    issue_category: str | None
    issue_summary: str
    decision_date: str
    safe_evidence_reference: str
    recorded_by_operator_id: str
    dispute_created: bool = False
    revision_created: bool = False
    customer_contact_performed: bool = False
    external_action_performed: bool = False
    automation_allowed: bool = False
    deterministic_content_hash: str = ""
    informational_recorded_at: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != ISSUE_INTAKE_SCHEMA_VERSION:
            raise ValueError("issue intake schema version mismatch")

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


# ---------------------------------------------------------------------------
# Revision-review request (authorizes only a future human review, nothing else)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RevisionReviewIntake:
    """Operator-recorded customer-requested revision review.

    Authorizes ONLY a future human review of revision eligibility. Does NOT
    create a Stage 8B revision request, calculate a successor version, approve
    cost, approve re-rendering, or invoke HVS.
    """

    schema_version: str
    revision_review_id: str
    receipt_record_id: str
    customer_decision_id: str | None
    actual_delivery_record_id: str
    delivery_package_id: str
    project_id: str
    customer_reference: str
    artifact_id: str
    artifact_sha256: str
    revision_review_reason: str
    decision_date: str
    safe_evidence_reference: str
    recorded_by_operator_id: str
    revision_created: bool = False
    successor_version_calculated: bool = False
    rerender_approved: bool = False
    hvs_invoked: bool = False
    invoice_state_changed: bool = False
    payment_state_changed: bool = False
    customer_contact_performed: bool = False
    external_action_performed: bool = False
    automation_allowed: bool = False
    deterministic_content_hash: str = ""
    informational_recorded_at: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != REVISION_REVIEW_SCHEMA_VERSION:
            raise ValueError("revision review schema version mismatch")

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


# ---------------------------------------------------------------------------
# Read-only readiness / outcome view
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DeliveryAcceptanceReadiness:
    """Read-only aggregate view over receipt + decision + issue + revision state.

    The final outcome must never imply more than the available evidence.
    """

    schema_version: str
    actual_delivery_record_id: str
    project_id: str
    customer_reference: str
    artifact_id: str
    artifact_sha256: str
    receipt_status: str
    receipt_record_id: str | None
    decision_status: str
    customer_decision_id: str | None
    outcome: str
    # Boundary / truth flags — always false for Stage 8P.
    customer_contact_performed: bool = False
    external_action_performed: bool = False
    hvs_invoked: bool = False
    project_closed: bool = False
    revision_created: bool = False
    dispute_created: bool = False
    invoice_state_changed: bool = False
    payment_state_changed: bool = False
    automation_allowed: bool = False
    informational_recorded_at: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != READINESS_SCHEMA_VERSION:
            raise ValueError("readiness schema version mismatch")
        if self.outcome not in ALLOWED_POST_RECEIPT_OUTCOMES:
            raise ValueError(f"invalid post-receipt outcome {self.outcome!r}")

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


# ---------------------------------------------------------------------------
# Append-only event
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CustomerReceiptAcceptanceEvent:
    """One append-only, deterministic lifecycle event."""

    schema_version: str
    event_id: str
    event_type: str
    aggregate_id: str
    project_id: str
    actual_delivery_record_id: str
    package_id: str | None
    artifact_sha256: str
    resulting_status: str
    operator_id: str
    informational_recorded_at: str
    deterministic_content_hash: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != POST_RECEIPT_EVENT_SCHEMA_VERSION:
            raise ValueError("post-receipt event schema version mismatch")
        if self.event_type not in ALLOWED_POST_RECEIPT_EVENT_TYPES:
            raise ValueError(f"invalid post-receipt event type {self.event_type!r}")

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


# ---------------------------------------------------------------------------
# Deterministic identity builders (no volatile inputs)
# ---------------------------------------------------------------------------
def receipt_record_id(
    *,
    actual_delivery_record_id: str,
    delivery_package_id: str,
    artifact_sha256: str,
    customer_reference: str,
    receipt_evidence_type: str,
    safe_evidence_reference: str,
) -> str:
    return stable_id(
        "scos-hvs-stage8p-receipt",
        {
            "actual_delivery_record_id": actual_delivery_record_id,
            "delivery_package_id": delivery_package_id,
            "artifact_sha256": artifact_sha256.lower(),
            "customer_reference": customer_reference,
            "receipt_evidence_type": receipt_evidence_type,
            "safe_evidence_reference": safe_evidence_reference,
        },
    )


def customer_decision_id(
    *,
    receipt_record_id: str,
    actual_delivery_record_id: str,
    artifact_sha256: str,
    decision_status: str,
    semantic_content: str,
    safe_evidence_reference: str,
) -> str:
    return stable_id(
        "scos-hvs-stage8p-decision",
        {
            "receipt_record_id": receipt_record_id,
            "actual_delivery_record_id": actual_delivery_record_id,
            "artifact_sha256": artifact_sha256.lower(),
            "decision_status": decision_status,
            "semantic_content": semantic_content,
            "safe_evidence_reference": safe_evidence_reference,
        },
    )


def issue_intake_id(
    *,
    receipt_record_id: str,
    actual_delivery_record_id: str,
    issue_summary: str,
    safe_evidence_reference: str,
) -> str:
    return stable_id(
        "scos-hvs-stage8p-issue",
        {
            "receipt_record_id": receipt_record_id,
            "actual_delivery_record_id": actual_delivery_record_id,
            "issue_summary": issue_summary,
            "safe_evidence_reference": safe_evidence_reference,
        },
    )


def revision_review_id(
    *,
    receipt_record_id: str,
    actual_delivery_record_id: str,
    revision_review_reason: str,
    safe_evidence_reference: str,
) -> str:
    return stable_id(
        "scos-hvs-stage8p-revision-review",
        {
            "receipt_record_id": receipt_record_id,
            "actual_delivery_record_id": actual_delivery_record_id,
            "revision_review_reason": revision_review_reason,
            "safe_evidence_reference": safe_evidence_reference,
        },
    )


def post_receipt_event_id(*, event_type: str, aggregate_id: str, record: dict[str, Any]) -> str:
    return stable_id(
        "scos-hvs-stage8p-event",
        {"event_type": event_type, "aggregate_id": aggregate_id, "record": record},
    )


def record_content_hash(record: dict[str, Any]) -> str:
    """Deterministic content hash over the record, excluding volatile fields."""
    volatile = {
        "deterministic_content_hash",
        "informational_recorded_at",
    }
    canonical = canonical_json({k: v for k, v in record.items() if k not in volatile})
    return stable_id("scos-hvs-stage8p-content", {"record": canonical})


__all__ = [
    "STAGE8P_SCHEMA_VERSION",
    "RECEIPT_RECORD_SCHEMA_VERSION",
    "DECISION_RECORD_SCHEMA_VERSION",
    "ISSUE_INTAKE_SCHEMA_VERSION",
    "REVISION_REVIEW_SCHEMA_VERSION",
    "READINESS_SCHEMA_VERSION",
    "POST_RECEIPT_EVENT_SCHEMA_VERSION",
    "DEFAULT_RECEIPT_ACCEPTANCE_RELATIVE",
    "RECEIPT_NOT_RECORDED",
    "RECEIPT_PENDING",
    "RECEIPT_CONFIRMED",
    "RECEIPT_REJECTED_AS_INVALID",
    "RECEIPT_IDENTITY_CONFLICT",
    "ALLOWED_RECEIPT_STATUSES",
    "DECISION_NO_DECISION",
    "DECISION_ACCEPTED",
    "DECISION_REJECTED",
    "DECISION_ISSUE_REPORTED",
    "DECISION_REVISION_REVIEW_REQUESTED",
    "ALLOWED_DECISION_STATUSES",
    "EVIDENCE_CUSTOMER_WRITTEN_CONFIRMATION",
    "EVIDENCE_CUSTOMER_VERBAL_RECORDED_BY_OPERATOR",
    "EVIDENCE_CUSTOMER_PORTAL_IMPORTED_MANUALLY",
    "EVIDENCE_SIGNED_RECEIPT_REFERENCE",
    "EVIDENCE_DELIVERY_CHANNEL_ACKNOWLEDGEMENT",
    "EVIDENCE_OTHER_OPERATOR_VERIFIED",
    "ALLOWED_RECEIPT_EVIDENCE_TYPES",
    "OUTCOME_RECEIPT_NOT_CONFIRMED",
    "OUTCOME_RECEIPT_CONFIRMED_ACCEPTANCE_PENDING",
    "OUTCOME_ACCEPTED_BY_CUSTOMER",
    "OUTCOME_REJECTED_BY_CUSTOMER",
    "OUTCOME_ISSUE_REPORTED",
    "OUTCOME_REVISION_REVIEW_REQUESTED",
    "OUTCOME_DELIVERY_IDENTITY_CONFLICT",
    "OUTCOME_BLOCKED",
    "ALLOWED_POST_RECEIPT_OUTCOMES",
    "EVT_RECEIPT_CONFIRMED",
    "EVT_RECEIPT_REJECTED",
    "EVT_CUSTOMER_ACCEPTED",
    "EVT_CUSTOMER_REJECTED",
    "EVT_CUSTOMER_ISSUE_REPORTED",
    "EVT_CUSTOMER_REVISION_REVIEW_REQUESTED",
    "ALLOWED_POST_RECEIPT_EVENT_TYPES",
    "ERR_MISSING_OPERATOR_ID",
    "ERR_MISSING_DELIVERY_RECORD_ID",
    "ERR_DELIVERY_RECORD_NOT_FOUND",
    "ERR_DELIVERY_RECORD_INVALID",
    "ERR_DELIVERY_NOT_FINAL",
    "ERR_DELIVERY_CANCELLED",
    "ERR_AUTH_NOT_VALID",
    "ERR_PACKAGE_NOT_VALID",
    "ERR_ARTIFACT_NOT_VERIFIED",
    "ERR_ARTIFACT_SHA_MISMATCH",
    "ERR_PACKAGE_ID_MISMATCH",
    "ERR_DELIVERY_RECORD_ID_MISMATCH",
    "ERR_CUSTOMER_REFERENCE_MISMATCH",
    "ERR_LEGACY_LINEAGE",
    "ERR_CONFLICTING_RECEIPT",
    "ERR_MISSING_CONFIRMATION_DATE",
    "ERR_MISSING_EVIDENCE_REFERENCE",
    "ERR_UNSAFE_EVIDENCE_REFERENCE",
    "ERR_INVALID_EVIDENCE_TYPE",
    "ERR_UNSAFE_RECEIPT_BODY",
    "ERR_CUSTOMER_SHA_MISMATCH",
    "ERR_MISSING_DECISION_DATE",
    "ERR_MISSING_REJECTION_REASON",
    "ERR_MISSING_ISSUE_SUMMARY",
    "ERR_MISSING_REVISION_REASON",
    "ERR_DECISION_BEFORE_RECEIPT",
    "ERR_RECEIPT_IMMUTABLE",
    "ERR_DECISION_CONFLICT",
    "ERR_INVALID_TRANSITION",
    "ERR_UNSAFE_ISSUE_CONTENT",
    "ERR_INVALID_OUTCOME",
    "ERR_UNKNOWN_SCHEMA_VERSION",
    "CustomerReceiptRecord",
    "CustomerDecisionRecord",
    "DeliveryIssueIntake",
    "RevisionReviewIntake",
    "DeliveryAcceptanceReadiness",
    "CustomerReceiptAcceptanceEvent",
    "sha256_bytes",
    "receipt_record_id",
    "customer_decision_id",
    "issue_intake_id",
    "revision_review_id",
    "post_receipt_event_id",
    "record_content_hash",
]
