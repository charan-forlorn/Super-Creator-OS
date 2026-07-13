"""Stage 8G post-delivery support window, dispute/reopen control, and
commercial closure contracts; evidence recording only, no customer contact,
no outbound transport, no HVS execution, no invoice/payment mutation.

This module defines the SCOS-side immutable, deterministic models for the
post-delivery support phase of the SCOS–HVS integration. It records:

  * an explicit post-delivery support policy (bounded support window),
  * customer issue / dispute intake,
  * deterministic, fail-closed issue classification,
  * operator-approved reopen routing (back to Stage 8B/8C only when the
    required prior-stage approvals and lineage already exist),
  * commercial-closure evidence (read-only invoice/payment references).

Stage 8G deliberately does NOT import or invoke HVS, does NOT render media,
does NOT contact customers, does NOT send email/messages, does NOT invoke CRM,
does NOT issue refunds, does NOT create invoices, does NOT alter payment state,
and does NOT trigger a delivery transport. It constructs internal
support/dispute/reopen/commercial-closure evidence only.

Design reuses the canonical contracts of adjacent stages:

  * ``_safe_id`` / ``_safe_optional_id`` / ``ALLOWED_TARGET_FORMATS`` /
    ``_require_allowed_format`` from the Stage 8C dispatch models
  * the deterministic sha256-prefixed id style (no time / random)
  * frozen dataclasses, canonical JSON serialization, append-only audit events
  * Stage 8F release/receipt/audit evidence as the authoritative gating lineage
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

# Reuse the Stage 8C safe-id policy and the bounded target-format allowlist so
# the 8G vocabulary shares one source of truth with adjacent stages.
from .hvs_rerender_dispatch_models import (  # noqa: F401
    ALLOWED_TARGET_FORMATS,
    _safe_format,
    _safe_id,
    _safe_optional_id,
)

POST_DELIVERY_SUPPORT_SCHEMA_VERSION = "scos-hvs.post-delivery-support.v1/1.0.0"
POST_DELIVERY_SUPPORT_EVENT_SCHEMA_VERSION = "scos-hvs.post-delivery-support-event.v1/1.0.0"

# --- Support policy status --------------------------------------------------
SUPPORT_POLICY_ACTIVE = "ACTIVE"
SUPPORT_POLICY_EXPIRED = "EXPIRED"
SUPPORT_POLICY_CANCELLED = "CANCELLED"
SUPPORT_POLICY_SUPERSEDED = "SUPERSEDED"
ALLOWED_SUPPORT_POLICY_STATUSES = (
    SUPPORT_POLICY_ACTIVE,
    SUPPORT_POLICY_EXPIRED,
    SUPPORT_POLICY_CANCELLED,
    SUPPORT_POLICY_SUPERSEDED,
)

# --- Issue status -----------------------------------------------------------
ISSUE_OPEN = "OPEN"
ISSUE_CLASSIFIED = "CLASSIFIED"
ISSUE_RESOLVED = "RESOLVED"
ISSUE_REJECTED = "REJECTED"
ISSUE_CANCELLED = "CANCELLED"
ALLOWED_ISSUE_STATUSES = (
    ISSUE_OPEN,
    ISSUE_CLASSIFIED,
    ISSUE_RESOLVED,
    ISSUE_REJECTED,
    ISSUE_CANCELLED,
)

# --- Issue categories (no silent default mapping) ---------------------------
ISSUE_PRODUCTION_DEFECT = "PRODUCTION_DEFECT"
ISSUE_ARTIFACT_INTEGRITY_DEFECT = "ARTIFACT_INTEGRITY_DEFECT"
ISSUE_DELIVERY_PROCESS_DEFECT = "DELIVERY_PROCESS_DEFECT"
ISSUE_CUSTOMER_REVISION_REQUEST = "CUSTOMER_REVISION_REQUEST"
ISSUE_SCOPE_CHANGE = "SCOPE_CHANGE"
ISSUE_CONTENT_CHANGE = "CONTENT_CHANGE"
ISSUE_FORMAT_CHANGE = "FORMAT_CHANGE"
ISSUE_SUPPORT_QUESTION = "SUPPORT_QUESTION"
ISSUE_DISPUTE = "DISPUTE"
ISSUE_UNSUPPORTED_REQUEST = "UNSUPPORTED_REQUEST"
ALLOWED_ISSUE_CATEGORIES = (
    ISSUE_PRODUCTION_DEFECT,
    ISSUE_ARTIFACT_INTEGRITY_DEFECT,
    ISSUE_DELIVERY_PROCESS_DEFECT,
    ISSUE_CUSTOMER_REVISION_REQUEST,
    ISSUE_SCOPE_CHANGE,
    ISSUE_CONTENT_CHANGE,
    ISSUE_FORMAT_CHANGE,
    ISSUE_SUPPORT_QUESTION,
    ISSUE_DISPUTE,
    ISSUE_UNSUPPORTED_REQUEST,
)

# Defect categories that, when covered by policy, route to a revision/render
# follow-up (never directly to HVS).
COVERED_DEFECT_CATEGORIES = (
    ISSUE_PRODUCTION_DEFECT,
    ISSUE_ARTIFACT_INTEGRITY_DEFECT,
    ISSUE_DELIVERY_PROCESS_DEFECT,
)

# Revision-follow-up categories (route to Stage 8B, never directly to HVS).
REVISION_FOLLOWUP_CATEGORIES = (
    ISSUE_CUSTOMER_REVISION_REQUEST,
    ISSUE_CONTENT_CHANGE,
    ISSUE_FORMAT_CHANGE,
)

# --- Classification outcomes ------------------------------------------------
CLASS_COVERED_DEFECT = "COVERED_DEFECT"
CLASS_COVERED_REVISION = "COVERED_REVISION"
CLASS_OUT_OF_SCOPE_CHANGE = "OUT_OF_SCOPE_CHANGE"
CLASS_COMMERCIAL_REVIEW_REQUIRED = "COMMERCIAL_REVIEW_REQUIRED"
CLASS_SUPPORT_ONLY = "SUPPORT_ONLY"
CLASS_DISPUTE_REVIEW_REQUIRED = "DISPUTE_REVIEW_REQUIRED"
CLASS_REJECTED_UNSUPPORTED = "REJECTED_UNSUPPORTED"
CLASS_BLOCKED_INVALID_LINEAGE = "BLOCKED_INVALID_LINEAGE"
ALLOWED_CLASSIFICATION_OUTCOMES = (
    CLASS_COVERED_DEFECT,
    CLASS_COVERED_REVISION,
    CLASS_OUT_OF_SCOPE_CHANGE,
    CLASS_COMMERCIAL_REVIEW_REQUIRED,
    CLASS_SUPPORT_ONLY,
    CLASS_DISPUTE_REVIEW_REQUIRED,
    CLASS_REJECTED_UNSUPPORTED,
    CLASS_BLOCKED_INVALID_LINEAGE,
)

# --- Dispute status ---------------------------------------------------------
DISPUTE_OPEN = "OPEN"
DISPUTE_UNDER_REVIEW = "UNDER_REVIEW"
DISPUTE_RESOLVED = "RESOLVED"
DISPUTE_REJECTED = "REJECTED"
DISPUTE_CANCELLED = "CANCELLED"
DISPUTE_SUPERSEDED = "SUPERSEDED"
ALLOWED_DISPUTE_STATUSES = (
    DISPUTE_OPEN,
    DISPUTE_UNDER_REVIEW,
    DISPUTE_RESOLVED,
    DISPUTE_REJECTED,
    DISPUTE_CANCELLED,
    DISPUTE_SUPERSEDED,
)

DISPUTE_TERMINAL_STATUSES = (
    DISPUTE_RESOLVED,
    DISPUTE_REJECTED,
    DISPUTE_CANCELLED,
    DISPUTE_SUPERSEDED,
)

# --- Reopen status ----------------------------------------------------------
REOPEN_REQUESTED = "REQUESTED"
REOPEN_APPROVED = "APPROVED"
REOPEN_REJECTED = "REJECTED"
REOPEN_CANCELLED = "CANCELLED"
ALLOWED_REOPEN_STATUSES = (
    REOPEN_REQUESTED,
    REOPEN_APPROVED,
    REOPEN_REJECTED,
    REOPEN_CANCELLED,
)

REOPEN_TERMINAL_STATUSES = (
    REOPEN_APPROVED,
    REOPEN_REJECTED,
    REOPEN_CANCELLED,
)

# --- Allowed reopen target workflows (explicit) -----------------------------
REOPEN_TARGET_STAGE_8B = "STAGE_8B_NEW_REVISION"
REOPEN_TARGET_STAGE_8C = "STAGE_8C_APPROVED_RERENDER"
REOPEN_TARGET_COMMERCIAL_REVIEW = "MANUAL_COMMERCIAL_REVIEW"
REOPEN_TARGET_SUPPORT_RESPONSE = "SUPPORT_RESPONSE_ONLY"
REOPEN_TARGET_NO_REOPEN = "NO_REOPEN"
ALLOWED_REOPEN_TARGETS = (
    REOPEN_TARGET_STAGE_8B,
    REOPEN_TARGET_STAGE_8C,
    REOPEN_TARGET_COMMERCIAL_REVIEW,
    REOPEN_TARGET_SUPPORT_RESPONSE,
    REOPEN_TARGET_NO_REOPEN,
)

# --- Commercial closure status ----------------------------------------------
COMMERCIAL_CLOSED = "COMMERCIALLY_CLOSED"
COMMERCIAL_PENDING = "CLOSURE_PENDING"
COMMERCIAL_BLOCKED = "CLOSURE_BLOCKED"
COMMERCIAL_DISPUTED = "DISPUTED"
COMMERCIAL_REOPENED = "REOPENED"
ALLOWED_COMMERCIAL_CLOSURE_STATUSES = (
    COMMERCIAL_CLOSED,
    COMMERCIAL_PENDING,
    COMMERCIAL_BLOCKED,
    COMMERCIAL_DISPUTED,
    COMMERCIAL_REOPENED,
)

# --- Append-only Stage 8G lifecycle audit event types -----------------------
EVT_SUPPORT_POLICY_REGISTERED = "SUPPORT_POLICY_REGISTERED"
EVT_SUPPORT_POLICY_REJECTED = "SUPPORT_POLICY_REJECTED"
EVT_SUPPORT_POLICY_SUPERSEDED = "SUPPORT_POLICY_SUPERSEDED"
EVT_ISSUE_RECORDED = "ISSUE_RECORDED"
EVT_ISSUE_REJECTED = "ISSUE_REJECTED"
EVT_ISSUE_CLASSIFIED = "ISSUE_CLASSIFIED"
EVT_ISSUE_CLASSIFICATION_REJECTED = "ISSUE_CLASSIFICATION_REJECTED"
EVT_DISPUTE_OPENED = "DISPUTE_OPENED"
EVT_DISPUTE_RESOLVED = "DISPUTE_RESOLVED"
EVT_DISPUTE_RESOLUTION_REJECTED = "DISPUTE_RESOLUTION_REJECTED"
EVT_REOPEN_REQUESTED = "REOPEN_REQUESTED"
EVT_REOPEN_APPROVED = "REOPEN_APPROVED"
EVT_REOPEN_REJECTED = "REOPEN_REJECTED"
EVT_COMMERCIAL_CLOSURE_RECORDED = "COMMERCIAL_CLOSURE_RECORDED"
EVT_COMMERCIAL_CLOSURE_REJECTED = "COMMERCIAL_CLOSURE_REJECTED"


# --- Safe identifier / text / sha256 helpers --------------------------------
def _safe_customer_reference(field: str, value: str) -> str:
    _safe_text(field, value, allow_slash=False, allow_at=True)
    return value


def _safe_text(
    field: str,
    value: str,
    *,
    allow_slash: bool = False,
    allow_at: bool = False,
    allow_dot: bool = True,
) -> str:
    if not isinstance(value, str) or value == "":
        raise ValueError(f"{field} must be a non-empty string")
    if len(value) > 512:
        raise ValueError(f"{field} too long")
    if "\x00" in value or "\r" in value or "\n" in value:
        raise ValueError(f"{field} contains control characters")
    if ".." in value or (not allow_slash and "/" in value):
        raise ValueError(f"{field} contains path traversal")
    if "\\" in value:
        raise ValueError(f"{field} contains backslash")
    if not allow_at and "@" in value:
        raise ValueError(f"{field} contains invalid character")
    if not allow_dot and "." in value:
        raise ValueError(f"{field} contains invalid character")
    if value.startswith("-"):
        raise ValueError(f"{field} must not start with hyphen")
    return value


def _safe_sha256(field: str, value: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    if value == "":
        return ""
    if not (value.startswith("sha256:") and len(value) == len("sha256:") + 64):
        raise ValueError(f"{field} must be empty or sha256:<64 hex>")
    hexpart = value[len("sha256:"):]
    if any(c not in "0123456789abcdefABCDEF" for c in hexpart):
        raise ValueError(f"{field} contains non-hex sha256")
    return value


def _safe_date(field: str, value: str) -> str:
    if not isinstance(value, str) or value == "":
        raise ValueError(f"{field} must be a non-empty string")
    if len(value) > 64:
        raise ValueError(f"{field} too long")
    if "\x00" in value or "\r" in value or "\n" in value or ".." in value or "/" in value:
        raise ValueError(f"{field} contains invalid characters")
    return value


def _normalize_optional_metadata(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("metadata must be a dict or None")
    return dict(value)


# --- Deterministic id builders (no timestamps) ------------------------------
def _sha256_of(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p).encode("utf-8"))
        h.update(b"\x1f")
    return h.hexdigest()


def build_support_policy_id(
    *,
    project_id: str,
    revised_delivery_id: str,
    release_execution_id: str,
    receipt_confirmation_id: str,
    post_delivery_closure_id: str,
    support_window_start: str,
    support_window_end: str,
    policy_type: str,
    policy_version: str,
) -> str:
    return "scos-hvs-support-policy-" + _sha256_of(
        project_id, revised_delivery_id, release_execution_id, receipt_confirmation_id,
        post_delivery_closure_id, support_window_start, support_window_end,
        policy_type, policy_version,
    )


def build_issue_id(
    *,
    support_policy_id: str,
    project_id: str,
    revised_delivery_id: str,
    issue_category: str,
    customer_reference: str,
    issue_summary: str,
) -> str:
    return "scos-hvs-issue-" + _sha256_of(
        support_policy_id, project_id, revised_delivery_id, issue_category,
        customer_reference, issue_summary,
    )


def build_classification_id(
    *,
    issue_id: str,
    classification: str,
) -> str:
    return "scos-hvs-issue-class-" + _sha256_of(issue_id, classification)


def build_dispute_id(
    *,
    issue_id: str,
    dispute_type: str,
    dispute_reason: str,
) -> str:
    return "scos-hvs-dispute-" + _sha256_of(issue_id, dispute_type, dispute_reason)


def build_reopen_id(
    *,
    issue_id: str,
    prior_post_delivery_closure_id: str,
    target_workflow: str,
    reopen_reason: str,
    approval_reference: str,
) -> str:
    return "scos-hvs-reopen-" + _sha256_of(
        issue_id, prior_post_delivery_closure_id, target_workflow,
        reopen_reason, approval_reference,
    )


def build_commercial_closure_id(
    *,
    project_id: str,
    revision_id: str,
    revised_delivery_id: str,
    post_delivery_closure_id: str,
    support_policy_id: str,
    closure_basis: str,
) -> str:
    return "scos-hvs-commercial-closure-" + _sha256_of(
        project_id, revision_id, revised_delivery_id, post_delivery_closure_id,
        support_policy_id, closure_basis,
    )


def build_event_id(*, event_type: str, subject_id: str, record: dict[str, Any]) -> str:
    return "scos-hvs-support-evt-" + _sha256_of(
        event_type, subject_id, json.dumps(record, sort_keys=True, separators=(",", ":"))
    )


# --- Append-only audit event ------------------------------------------------
@dataclass(frozen=True)
class PostDeliverySupportEvent:
    schema_version: str
    event_id: str
    event_type: str
    subject_id: str
    operator_id: str
    recorded_at: str
    record: dict[str, Any]

    def __post_init__(self) -> None:
        if self.schema_version != POST_DELIVERY_SUPPORT_EVENT_SCHEMA_VERSION:
            raise ValueError("support event schema version mismatch")
        _safe_id("event_id", self.event_id)
        _safe_id("subject_id", self.subject_id)
        _safe_id("operator_id", self.operator_id)
        _safe_text("event_type", self.event_type, allow_slash=False)
        if not isinstance(self.record, dict):
            raise ValueError("event record must be a dict")

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


# --- Post-delivery support policy -------------------------------------------
@dataclass(frozen=True)
class PostDeliverySupportPolicy:
    schema_version: str
    support_policy_id: str
    project_id: str
    revision_id: str
    revised_delivery_id: str
    original_delivery_id: str | None
    release_execution_id: str
    receipt_confirmation_id: str
    post_delivery_closure_id: str
    support_window_start: str
    support_window_end: str
    policy_type: str
    included_issue_categories: tuple[str, ...]
    excluded_issue_categories: tuple[str, ...]
    revision_allowance_reference: str | None
    commercial_terms_reference: str | None
    policy_version: str
    created_by_operator_id: str
    evidence_references: tuple[str, ...]
    status: str
    idempotency_key: str
    created_at: str

    def __post_init__(self) -> None:
        if self.schema_version != POST_DELIVERY_SUPPORT_SCHEMA_VERSION:
            raise ValueError("support policy schema version mismatch")
        if self.status not in ALLOWED_SUPPORT_POLICY_STATUSES:
            raise ValueError(f"invalid support policy status {self.status!r}")
        for f in (
            "support_policy_id", "project_id", "revision_id", "revised_delivery_id",
            "release_execution_id", "receipt_confirmation_id",
            "post_delivery_closure_id", "created_by_operator_id", "idempotency_key",
        ):
            _safe_id(f, getattr(self, f))
        _safe_text("policy_type", self.policy_type, allow_slash=True)
        _safe_text("policy_version", self.policy_version, allow_slash=True)
        if self.original_delivery_id:
            _safe_id("original_delivery_id", self.original_delivery_id)
        _safe_date("support_window_start", self.support_window_start)
        _safe_date("support_window_end", self.support_window_end)
        # Explicit, validated, deterministic window: start strictly before end.
        if self.support_window_start >= self.support_window_end:
            raise ValueError("support window start must be strictly before end")
        for c in self.included_issue_categories:
            if c not in ALLOWED_ISSUE_CATEGORIES:
                raise ValueError(f"included issue category {c!r} not allowed")
        for c in self.excluded_issue_categories:
            if c not in ALLOWED_ISSUE_CATEGORIES:
                raise ValueError(f"excluded issue category {c!r} not allowed")

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["included_issue_categories"] = list(self.included_issue_categories)
        data["excluded_issue_categories"] = list(self.excluded_issue_categories)
        data["evidence_references"] = list(self.evidence_references)
        return data


# --- Post-delivery issue intake ---------------------------------------------
@dataclass(frozen=True)
class PostDeliveryIssue:
    schema_version: str
    issue_id: str
    support_policy_id: str
    project_id: str
    revision_id: str
    revised_delivery_id: str
    original_delivery_id: str | None
    release_execution_id: str
    receipt_confirmation_id: str
    post_delivery_closure_id: str
    customer_reference: str
    recorded_by_operator_id: str
    issue_category: str
    issue_summary: str
    issue_details: str
    affected_formats: tuple[str, ...]
    affected_artifact_references: tuple[str, ...]
    artifact_sha256: str
    reported_at: str
    evidence_references: tuple[str, ...]
    requested_resolution: str
    status: str
    idempotency_key: str
    created_at: str

    def __post_init__(self) -> None:
        if self.schema_version != POST_DELIVERY_SUPPORT_SCHEMA_VERSION:
            raise ValueError("issue schema version mismatch")
        if self.status not in ALLOWED_ISSUE_STATUSES:
            raise ValueError(f"invalid issue status {self.status!r}")
        if self.issue_category not in ALLOWED_ISSUE_CATEGORIES:
            # Do not silently map unknown categories to a default.
            raise ValueError(f"issue category {self.issue_category!r} not allowed")
        for f in (
            "issue_id", "support_policy_id", "project_id", "revision_id",
            "revised_delivery_id", "release_execution_id", "receipt_confirmation_id",
            "post_delivery_closure_id", "recorded_by_operator_id",
            "issue_summary", "idempotency_key",
        ):
            _safe_id(f, getattr(self, f))
        _safe_text("requested_resolution", self.requested_resolution) if self.requested_resolution else None
        if self.original_delivery_id:
            _safe_id("original_delivery_id", self.original_delivery_id)
        _safe_customer_reference("customer_reference", self.customer_reference)
        _safe_text("issue_details", self.issue_details) if self.issue_details else None
        for f in self.affected_formats:
            _safe_format(f)
        for a in self.affected_artifact_references:
            _safe_id("affected_artifact_reference", a)
        _safe_sha256("artifact_sha256", self.artifact_sha256)
        _safe_date("reported_at", self.reported_at)

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["affected_formats"] = list(self.affected_formats)
        data["affected_artifact_references"] = list(self.affected_artifact_references)
        data["evidence_references"] = list(self.evidence_references)
        return data


# --- Issue classification ----------------------------------------------------
@dataclass(frozen=True)
class PostDeliveryIssueClassification:
    schema_version: str
    classification_id: str
    issue_id: str
    project_id: str
    revision_id: str
    revised_delivery_id: str
    outcome: str
    reason_codes: tuple[str, ...]
    target_workflow: str | None
    classified_by_operator_id: str
    idempotency_key: str
    created_at: str

    def __post_init__(self) -> None:
        if self.schema_version != POST_DELIVERY_SUPPORT_SCHEMA_VERSION:
            raise ValueError("classification schema version mismatch")
        if self.outcome not in ALLOWED_CLASSIFICATION_OUTCOMES:
            raise ValueError(f"invalid classification outcome {self.outcome!r}")
        for f in (
            "classification_id", "issue_id", "project_id", "revision_id",
            "revised_delivery_id", "classified_by_operator_id", "idempotency_key",
        ):
            _safe_id(f, getattr(self, f))
        if self.target_workflow is not None and self.target_workflow not in ALLOWED_REOPEN_TARGETS:
            raise ValueError(f"invalid target workflow {self.target_workflow!r}")
        for rc in self.reason_codes:
            _safe_text("reason_code", rc)

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["reason_codes"] = list(self.reason_codes)
        return data


# --- Dispute record ---------------------------------------------------------
@dataclass(frozen=True)
class PostDeliveryDispute:
    schema_version: str
    dispute_id: str
    issue_id: str
    project_id: str
    revised_delivery_id: str
    release_execution_id: str
    receipt_confirmation_id: str
    post_delivery_closure_id: str
    dispute_type: str
    dispute_reason: str
    disputed_artifact_references: tuple[str, ...]
    artifact_sha256: str
    opened_by_operator_id: str
    opened_at: str
    status: str
    resolution_reference: str | None
    resolved_by_operator_id: str | None
    resolution_reason: str | None
    evidence_references: tuple[str, ...]
    idempotency_key: str
    created_at: str

    def __post_init__(self) -> None:
        if self.schema_version != POST_DELIVERY_SUPPORT_SCHEMA_VERSION:
            raise ValueError("dispute schema version mismatch")
        if self.status not in ALLOWED_DISPUTE_STATUSES:
            raise ValueError(f"invalid dispute status {self.status!r}")
        for f in (
            "dispute_id", "issue_id", "project_id", "revised_delivery_id",
            "release_execution_id", "receipt_confirmation_id",
            "post_delivery_closure_id", "dispute_type", "opened_by_operator_id",
            "idempotency_key",
        ):
            _safe_id(f, getattr(self, f))
        _safe_text("dispute_reason", self.dispute_reason)
        for a in self.disputed_artifact_references:
            _safe_id("disputed_artifact_reference", a)
        _safe_sha256("artifact_sha256", self.artifact_sha256)
        _safe_date("opened_at", self.opened_at)
        if self.resolution_reference:
            _safe_id("resolution_reference", self.resolution_reference)
        if self.resolved_by_operator_id:
            _safe_id("resolved_by_operator_id", self.resolved_by_operator_id)
        if self.resolution_reason:
            _safe_text("resolution_reason", self.resolution_reason)

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["disputed_artifact_references"] = list(self.disputed_artifact_references)
        data["evidence_references"] = list(self.evidence_references)
        return data


# --- Reopen record ----------------------------------------------------------
@dataclass(frozen=True)
class PostDeliveryReopen:
    schema_version: str
    reopen_id: str
    issue_id: str
    dispute_id: str | None
    prior_post_delivery_closure_id: str
    revision_id: str
    revised_delivery_id: str
    project_id: str
    correlation_id: str | None
    reopen_reason: str
    reopen_scope: str
    target_workflow: str
    approved_by_operator_id: str
    approval_reference: str
    approved_at: str
    status: str
    idempotency_key: str
    evidence_references: tuple[str, ...]
    created_at: str

    def __post_init__(self) -> None:
        if self.schema_version != POST_DELIVERY_SUPPORT_SCHEMA_VERSION:
            raise ValueError("reopen schema version mismatch")
        if self.status not in ALLOWED_REOPEN_STATUSES:
            raise ValueError(f"invalid reopen status {self.status!r}")
        if self.target_workflow not in ALLOWED_REOPEN_TARGETS:
            raise ValueError(f"invalid target workflow {self.target_workflow!r}")
        for f in (
            "reopen_id", "issue_id", "prior_post_delivery_closure_id", "revision_id",
            "revised_delivery_id", "project_id", "idempotency_key",
        ):
            _safe_id(f, getattr(self, f))
        if self.approved_by_operator_id:
            _safe_id("approved_by_operator_id", self.approved_by_operator_id)
        if self.approval_reference:
            _safe_text("approval_reference", self.approval_reference, allow_slash=True)
        if self.dispute_id:
            _safe_id("dispute_id", self.dispute_id)
        if self.correlation_id:
            _safe_id("correlation_id", self.correlation_id)
        _safe_text("reopen_reason", self.reopen_reason)
        _safe_text("reopen_scope", self.reopen_scope)
        if self.approved_at:
            _safe_date("approved_at", self.approved_at)

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["evidence_references"] = list(self.evidence_references)
        return data


# --- Commercial closure record ----------------------------------------------
@dataclass(frozen=True)
class PostDeliveryCommercialClosure:
    schema_version: str
    commercial_closure_id: str
    project_id: str
    revision_id: str
    revised_delivery_id: str
    release_execution_id: str
    receipt_confirmation_id: str
    post_delivery_closure_id: str
    support_policy_id: str
    issue_ids: tuple[str, ...]
    dispute_ids: tuple[str, ...]
    reopen_ids: tuple[str, ...]
    closure_status: str
    closure_basis: str
    closed_by_operator_id: str
    closed_at: str
    outstanding_actions: tuple[str, ...]
    invoice_state_reference: str | None
    payment_state_reference: str | None
    evidence_references: tuple[str, ...]
    idempotency_key: str
    created_at: str

    def __post_init__(self) -> None:
        if self.schema_version != POST_DELIVERY_SUPPORT_SCHEMA_VERSION:
            raise ValueError("commercial closure schema version mismatch")
        if self.closure_status not in ALLOWED_COMMERCIAL_CLOSURE_STATUSES:
            raise ValueError(f"invalid commercial closure status {self.closure_status!r}")
        for f in (
            "commercial_closure_id", "project_id", "revision_id", "revised_delivery_id",
            "release_execution_id", "receipt_confirmation_id",
            "post_delivery_closure_id", "closure_basis",
            "closed_by_operator_id", "idempotency_key",
        ):
            _safe_id(f, getattr(self, f))
        if self.support_policy_id:
            _safe_id("support_policy_id", self.support_policy_id)
        for i in self.issue_ids:
            _safe_id("issue_id", i)
        for d in self.dispute_ids:
            _safe_id("dispute_id", d)
        for r in self.reopen_ids:
            _safe_id("reopen_id", r)
        _safe_text("closure_basis", self.closure_basis)
        if self.invoice_state_reference:
            _safe_id("invoice_state_reference", self.invoice_state_reference)
        if self.payment_state_reference:
            _safe_id("payment_state_reference", self.payment_state_reference)

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["issue_ids"] = list(self.issue_ids)
        data["dispute_ids"] = list(self.dispute_ids)
        data["reopen_ids"] = list(self.reopen_ids)
        data["outstanding_actions"] = list(self.outstanding_actions)
        data["evidence_references"] = list(self.evidence_references)
        return data
