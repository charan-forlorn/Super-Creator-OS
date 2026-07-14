"""SCOS <-> Hermes Video Studio (HVS) — Stage 8Q post-delivery resolution routing.

Stage 8Q consumes a verified Stage 8P post-delivery aggregate outcome and
determines the next safe INTERNAL route. It is a deterministic, local-only,
operator-controlled resolution-routing and recommendation contract.

Stage 8Q:

  * never closes a project,
  * never creates a revision automatically (revision eligibility != revision),
  * never creates a dispute automatically (issue qualification != dispute),
  * never resolves an issue automatically,
  * never contacts a customer, sends a reminder, or performs any transport,
  * never mutates payment / invoice state,
  * never invokes HVS, renders, delivers, uploads, or publishes,
  * never begins Stage 8R.

It binds every route to one Stage 8P aggregate outcome and the exact Stage 8O
delivery lineage (actual-delivery record, authorization, package, lineage,
artifact SHA-256), reusing the repository's deterministic identity helpers
(``canonical_json`` / ``stable_id``) and the safe-text discipline of Stage 8P /
Stage 8O. ``automation_allowed`` is always ``False``. No clock, no random, no
uuid, no network, no subprocess.

Recommendation != Execution at every layer.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from .hvs_commercial_proposal_models import canonical_json, stable_id
from .hvs_customer_outcome_models import validate_calendar_date


# --- schema / identity -------------------------------------------------------
STAGE8Q_SCHEMA_VERSION = "scos-hvs.stage8q.resolution-routing.v1/1.0.0"
ROUTE_MODEL_SCHEMA_VERSION = "scos-hvs.stage8q.route.v1/1.0.0"
DECISION_MODEL_SCHEMA_VERSION = "scos-hvs.stage8q.decision.v1/1.0.0"
EVENT_SCHEMA_VERSION = "scos-hvs.stage8q.event.v1/1.0.0"
READINESS_SCHEMA_VERSION = "scos-hvs.stage8q.readiness.v1/1.0.0"

# Deterministic runtime root under the gitignored scos/work tree.
DEFAULT_RESOLUTION_RELATIVE = "scos/work/hvs_stage8q_post_delivery_resolution"
LEDGER_NAME = "stage8q_post_delivery_resolution_ledger.jsonl"

# --- Routing status ----------------------------------------------------------
ROUTING_DRAFT = "DRAFT"
ROUTING_NEEDS_OPERATOR_INPUT = "NEEDS_OPERATOR_INPUT"
ROUTING_READY_FOR_OPERATOR_REVIEW = "READY_FOR_OPERATOR_REVIEW"
ROUTING_APPROVED = "APPROVED"
ROUTING_REJECTED = "REJECTED"
ROUTING_CANCELLED = "CANCELLED"
ROUTING_BLOCKED = "BLOCKED"
ROUTING_EXPIRED = "EXPIRED"
ALLOWED_ROUTING_STATUSES = (
    ROUTING_DRAFT,
    ROUTING_NEEDS_OPERATOR_INPUT,
    ROUTING_READY_FOR_OPERATOR_REVIEW,
    ROUTING_APPROVED,
    ROUTING_REJECTED,
    ROUTING_CANCELLED,
    ROUTING_BLOCKED,
    ROUTING_EXPIRED,
)

# --- Recommended route -------------------------------------------------------
ROUTE_CLOSURE_ELIGIBILITY_REVIEW = "CLOSURE_ELIGIBILITY_REVIEW"
ROUTE_MANUAL_ACCEPTANCE_FOLLOW_UP = "MANUAL_ACCEPTANCE_FOLLOW_UP"
ROUTE_MANUAL_RECEIPT_FOLLOW_UP = "MANUAL_RECEIPT_FOLLOW_UP"
ROUTE_CUSTOMER_REJECTION_RESOLUTION_REVIEW = "CUSTOMER_REJECTION_RESOLUTION_REVIEW"
ROUTE_SUPPORT_REVIEW = "SUPPORT_REVIEW"
ROUTE_DEFECT_REVIEW = "DEFECT_REVIEW"
ROUTE_DISPUTE_ELIGIBILITY_REVIEW = "DISPUTE_ELIGIBILITY_REVIEW"
ROUTE_REVISION_ELIGIBILITY_REVIEW = "REVISION_ELIGIBILITY_REVIEW"
ROUTE_OPERATOR_INVESTIGATION = "OPERATOR_INVESTIGATION"
ROUTE_NO_ACTION_REQUIRED = "NO_ACTION_REQUIRED"
ROUTE_BLOCKED = "BLOCKED"
ALLOWED_RECOMMENDED_ROUTES = (
    ROUTE_CLOSURE_ELIGIBILITY_REVIEW,
    ROUTE_MANUAL_ACCEPTANCE_FOLLOW_UP,
    ROUTE_MANUAL_RECEIPT_FOLLOW_UP,
    ROUTE_CUSTOMER_REJECTION_RESOLUTION_REVIEW,
    ROUTE_SUPPORT_REVIEW,
    ROUTE_DEFECT_REVIEW,
    ROUTE_DISPUTE_ELIGIBILITY_REVIEW,
    ROUTE_REVISION_ELIGIBILITY_REVIEW,
    ROUTE_OPERATOR_INVESTIGATION,
    ROUTE_NO_ACTION_REQUIRED,
    ROUTE_BLOCKED,
)

# --- Closure eligibility -----------------------------------------------------
CLOSURE_ELIGIBLE = "ELIGIBLE_FOR_CLOSURE_RECOMMENDATION"
CLOSURE_NOT_ELIGIBLE = "NOT_ELIGIBLE"
CLOSURE_NEEDS_OPERATOR_INPUT = "NEEDS_OPERATOR_INPUT"
CLOSURE_BLOCKED = "BLOCKED"
ALLOWED_CLOSURE_ELIGIBILITY = (
    CLOSURE_ELIGIBLE,
    CLOSURE_NOT_ELIGIBLE,
    CLOSURE_NEEDS_OPERATOR_INPUT,
    CLOSURE_BLOCKED,
)

# --- Issue qualification ------------------------------------------------------
ISSUE_SUPPORT_CANDIDATE = "SUPPORT_CANDIDATE"
ISSUE_DEFECT_CANDIDATE = "DEFECT_CANDIDATE"
ISSUE_DISPUTE_CANDIDATE = "DISPUTE_CANDIDATE"
ISSUE_REVISION_CANDIDATE = "REVISION_CANDIDATE"
ISSUE_GENERAL_RESOLUTION_REVIEW = "GENERAL_RESOLUTION_REVIEW"
ISSUE_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
ISSUE_BLOCKED = "BLOCKED"
ALLOWED_ISSUE_QUALIFICATIONS = (
    ISSUE_SUPPORT_CANDIDATE,
    ISSUE_DEFECT_CANDIDATE,
    ISSUE_DISPUTE_CANDIDATE,
    ISSUE_REVISION_CANDIDATE,
    ISSUE_GENERAL_RESOLUTION_REVIEW,
    ISSUE_INSUFFICIENT_EVIDENCE,
    ISSUE_BLOCKED,
)

# --- Revision eligibility ----------------------------------------------------
REVISION_ELIGIBLE = "ELIGIBLE"
REVISION_NOT_ELIGIBLE = "NOT_ELIGIBLE"
REVISION_NEEDS_OPERATOR_INPUT = "NEEDS_OPERATOR_INPUT"
REVISION_BLOCKED = "BLOCKED"
ALLOWED_REVISION_ELIGIBILITY = (
    REVISION_ELIGIBLE,
    REVISION_NOT_ELIGIBLE,
    REVISION_NEEDS_OPERATOR_INPUT,
    REVISION_BLOCKED,
)

# --- Operator decision actions ----------------------------------------------
DECISION_APPROVE_CLOSURE_RECOMMENDATION = "APPROVE_CLOSURE_RECOMMENDATION"
DECISION_APPROVE_MANUAL_FOLLOW_UP_RECOMMENDATION = "APPROVE_MANUAL_FOLLOW_UP_RECOMMENDATION"
DECISION_APPROVE_SUPPORT_REVIEW_ROUTE = "APPROVE_SUPPORT_REVIEW_ROUTE"
DECISION_APPROVE_DEFECT_REVIEW_ROUTE = "APPROVE_DEFECT_REVIEW_ROUTE"
DECISION_APPROVE_DISPUTE_ELIGIBILITY_REVIEW = "APPROVE_DISPUTE_ELIGIBILITY_REVIEW"
DECISION_APPROVE_REVISION_ELIGIBILITY_REVIEW = "APPROVE_REVISION_ELIGIBILITY_REVIEW"
DECISION_REJECT_ROUTE_RECOMMENDATION = "REJECT_ROUTE_RECOMMENDATION"
DECISION_CANCEL_ROUTE_REVIEW = "CANCEL_ROUTE_REVIEW"
ALLOWED_DECISION_ACTIONS = (
    DECISION_APPROVE_CLOSURE_RECOMMENDATION,
    DECISION_APPROVE_MANUAL_FOLLOW_UP_RECOMMENDATION,
    DECISION_APPROVE_SUPPORT_REVIEW_ROUTE,
    DECISION_APPROVE_DEFECT_REVIEW_ROUTE,
    DECISION_APPROVE_DISPUTE_ELIGIBILITY_REVIEW,
    DECISION_APPROVE_REVISION_ELIGIBILITY_REVIEW,
    DECISION_REJECT_ROUTE_RECOMMENDATION,
    DECISION_CANCEL_ROUTE_REVIEW,
)

# --- Append-only event types -------------------------------------------------
EVT_ROUTE_CREATED = "ROUTE_CREATED"
EVT_ROUTE_REEVALUATED = "ROUTE_REEVALUATED"
EVT_ROUTE_APPROVED = "ROUTE_APPROVED"
EVT_ROUTE_REJECTED = "ROUTE_REJECTED"
EVT_ROUTE_CANCELLED = "ROUTE_CANCELLED"
ALLOWED_EVENT_TYPES = (
    EVT_ROUTE_CREATED,
    EVT_ROUTE_REEVALUATED,
    EVT_ROUTE_APPROVED,
    EVT_ROUTE_REJECTED,
    EVT_ROUTE_CANCELLED,
)

# --- Safe issue-category mapping (reuses Stage 8G vocabulary) ----------------
# Imported lazily in the service to avoid a hard module dependency at import
# time; declared here for clarity.
ISSUE_CATEGORY_TO_QUALIFICATION: dict[str, str] = {
    # DEFECT_CANDIDATE sources
    "PRODUCTION_DEFECT": ISSUE_DEFECT_CANDIDATE,
    "ARTIFACT_INTEGRITY_DEFECT": ISSUE_DEFECT_CANDIDATE,
    "DELIVERY_PROCESS_DEFECT": ISSUE_DEFECT_CANDIDATE,
    # REVISION_CANDIDATE sources (requested change, not claimed defect)
    "CUSTOMER_REVISION_REQUEST": ISSUE_REVISION_CANDIDATE,
    "SCOPE_CHANGE": ISSUE_REVISION_CANDIDATE,
    "CONTENT_CHANGE": ISSUE_REVISION_CANDIDATE,
    "FORMAT_CHANGE": ISSUE_REVISION_CANDIDATE,
    # SUPPORT_CANDIDATE
    "SUPPORT_QUESTION": ISSUE_SUPPORT_CANDIDATE,
    # DISPUTE_CANDIDATE
    "DISPUTE": ISSUE_DISPUTE_CANDIDATE,
    # General (explicit but unmapped to a narrower action)
    "UNSUPPORTED_REQUEST": ISSUE_GENERAL_RESOLUTION_REVIEW,
}

# --- error codes -------------------------------------------------------------
ERR_MISSING_OPERATOR_ID = "missing_operator_id"
ERR_MISSING_SOURCE_BINDING = "missing_source_binding"
ERR_MISSING_DELIVERY_RECORD_ID = "missing_actual_delivery_record_id"
ERR_DELIVERY_RECORD_NOT_FOUND = "actual_delivery_record_not_found"
ERR_STAGE8P_NOT_VERIFIED = "stage8p_evidence_not_verified"
ERR_UNKNOWN_AGGREGATE_OUTCOME = "unknown_stage8p_aggregate_outcome"
ERR_FORGED_RECEIPT = "forged_stage8p_receipt"
ERR_FORGED_DECISION = "forged_stage8p_decision"
ERR_ARTIFACT_SHA_MISMATCH = "artifact_sha_mismatch"
ERR_CUSTOMER_REFERENCE_MISMATCH = "customer_reference_mismatch"
ERR_DELIVERY_LINEAGE_MISMATCH = "delivery_lineage_mismatch"
ERR_CONFLICTING_DECISIONS = "conflicting_stage8p_decisions"
ERR_UNSAFE_ISSUE_CONTENT = "unsafe_issue_content"
ERR_UNSAFE_EVIDENCE_REFERENCE = "unsafe_evidence_reference"
ERR_MISSING_ISSUE_SUMMARY = "missing_issue_summary"
ERR_INVALID_ROUTE_STATUS = "invalid_routing_status"
ERR_INVALID_RECOMMENDED_ROUTE = "invalid_recommended_route"
ERR_INVALID_CLOSURE_ELIGIBILITY = "invalid_closure_eligibility"
ERR_INVALID_ISSUE_QUALIFICATION = "invalid_issue_qualification"
ERR_INVALID_REVISION_ELIGIBILITY = "invalid_revision_eligibility"
ERR_INVALID_DECISION_ACTION = "invalid_decision_action"
ERR_ROUTE_NOT_FOUND = "resolution_route_not_found"
ERR_DECISION_REQUIRES_REASON = "decision_requires_reason"
ERR_ROUTE_CONTENT_CONFLICT = "changed_route_semantics_conflict"
ERR_DECISION_ALREADY_FINAL = "route_decision_already_final"
ERR_MISSING_DECISION_HASH = "missing_route_content_hash"
ERR_ROUTE_HASH_MISMATCH = "route_content_hash_mismatch"
ERR_UNSAFE_FREE_TEXT = "unsafe_free_text"
ERR_UNKNOWN_SCHEMA_VERSION = "unknown_stage8q_schema_version"
ERR_MISSING_EVALUATION_DATE = "missing_evaluation_date"
ERR_INVALID_EVALUATION_DATE = "invalid_evaluation_date"


# --- safe input normalization ------------------------------------------------
def _bounded(value: Any, *, max_len: int = 512, field_name: str = "field") -> str:
    if value is None or value == "":
        return ""
    if not isinstance(value, str) or len(value) > max_len:
        raise ValueError(f"{field_name} must be a bounded string")
    if "\x00" in value or "\r" in value or "\n" in value or "\\" in value or ".." in value:
        raise ValueError(f"{field_name} contains unsafe text")
    return value


def _require_member(value: str, allowed: tuple[str, ...], code: str, detail: str) -> str:
    if value not in allowed:
        raise ValueError(f"{code}: {detail}")
    return value


def _require_operator_id(operator_id: str) -> str:
    value = _bounded(operator_id, max_len=256, field_name="operator_id")
    if not value:
        raise ValueError("operator_id is required")
    return value


def _require_nonempty(value: str, *, field_name: str) -> str:
    v = _bounded(value, max_len=256, field_name=field_name)
    if not v:
        raise ValueError(f"{field_name} is required")
    return v


def _require_date(value: str, *, field_name: str) -> str:
    v = _bounded(value, max_len=64, field_name=field_name)
    if not v:
        raise ValueError(f"{field_name} is required")
    validate_calendar_date(field_name, v)
    return v


def _require_evidence_reference(value: str) -> str:
    """Reject secret-like / command-like / URL-like / traversal / injection."""
    v = _bounded(value, max_len=256, field_name="safe_evidence_reference")
    if not v:
        raise ValueError("safe_evidence_reference is required")
    lowered = v.lower()
    if "://" in lowered:
        raise ValueError("safe_evidence_reference must not be a URL")
    for token in ("password", "secret", "token=", "api_key", "apikey", "credential"):
        if token in lowered:
            raise ValueError("safe_evidence_reference must not contain secret-like text")
    if any(c in v for c in ("|", ";", "&", "$", "(", ")", "<", ">", "`", "..", "\n", "\r", "\x00")):
        raise ValueError("safe_evidence_reference must not contain command-like or unsafe characters")
    return v


def _require_issue_summary(value: str, *, max_len: int = 512) -> str:
    v = _bounded(value, max_len=max_len, field_name="issue_summary")
    if not v:
        raise ValueError("issue summary is required")
    if "\x00" in v or "\r" in v or "\n" in v:
        raise ValueError("issue summary must not contain newline or null content")
    lowered = v.lower()
    for token in ("password", "secret", "token=", "api_key", "apikey", "credential"):
        if token in lowered:
            raise ValueError("issue summary must not contain secret-like text")
    return v


def _require_free_text(value: str, *, max_len: int = 512, field_name: str) -> str:
    if value is None:
        return ""
    v = _bounded(str(value).strip(), max_len=max_len, field_name=field_name)
    if not v:
        return ""
    if "\x00" in v or "\r" in v or "\n" in v:
        raise ValueError(f"{field_name} must not contain newline or null content")
    lowered = v.lower()
    for token in ("password", "secret", "token=", "api_key", "apikey", "credential"):
        if token in lowered:
            raise ValueError(f"{field_name} must not contain secret-like text")
    return v


def _immutable_hash(value: str) -> str:
    v = _bounded(value, max_len=128, field_name="artifact_sha256")
    if len(v) != 64:
        raise ValueError("artifact_sha256 must be a 64-char SHA-256 hex digest")
    return v.lower()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Source binding (immutable view over verified Stage 8P + Stage 8O evidence)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PostDeliverySourceBinding:
    """Immutable semantic inputs that define a Stage 8Q route identity.

    Built only from a verified Stage 8P aggregate outcome and the bound Stage 8O
    delivery lineage. Never carries mutable caller-owned structures.
    """

    schema_version: str
    project_id: str
    customer_reference: str
    actual_delivery_record_id: str
    delivery_package_id: str
    delivery_authorization_id: str
    render_completion_id: str
    delivery_lineage_id: str | None
    artifact_id: str
    artifact_sha256: str
    source_stage8p_receipt_record_id: str | None
    source_stage8p_customer_decision_id: str | None
    source_stage8p_aggregate_outcome: str
    stage8p_deterministic_content_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


# ---------------------------------------------------------------------------
# Closure eligibility (read-only evaluation result)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ClosureEligibilityResult:
    closure_eligibility_status: str
    eligible: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    evaluation_date: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "closure_eligibility_status": self.closure_eligibility_status,
            "eligible": self.eligible,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "evaluation_date": self.evaluation_date,
        }


# ---------------------------------------------------------------------------
# Issue qualification (read-only evaluation result)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class IssueQualificationResult:
    issue_qualification: str
    confirmed: bool
    defect_confirmed: bool
    dispute_created: bool
    revision_created: bool
    hvs_invoked: bool
    insufficient_evidence: bool
    evaluation_date: str | None
    safe_evidence_reference: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_qualification": self.issue_qualification,
            "confirmed": self.confirmed,
            "defect_confirmed": self.defect_confirmed,
            "dispute_created": self.dispute_created,
            "revision_created": self.revision_created,
            "hvs_invoked": self.hvs_invoked,
            "insufficient_evidence": self.insufficient_evidence,
            "evaluation_date": self.evaluation_date,
            "safe_evidence_reference": self.safe_evidence_reference,
        }


# ---------------------------------------------------------------------------
# Revision eligibility (read-only evaluation result, Stage 8B contract reuse)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RevisionQualificationResult:
    revision_eligibility_status: str
    eligible: bool
    successor_version_persisted: bool
    revision_created: bool
    rerender_authorized: bool
    hvs_invoked: bool
    free_revision_inferred: bool
    cost_inferred: bool
    evaluation_date: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "revision_eligibility_status": self.revision_eligibility_status,
            "eligible": self.eligible,
            "successor_version_persisted": self.successor_version_persisted,
            "revision_created": self.revision_created,
            "rerender_authorized": self.rerender_authorized,
            "hvs_invoked": self.hvs_invoked,
            "free_revision_inferred": self.free_revision_inferred,
            "cost_inferred": self.cost_inferred,
            "evaluation_date": self.evaluation_date,
        }


# ---------------------------------------------------------------------------
# Follow-up recommendation (manual action only; never contact)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FollowUpRecommendation:
    route_kind: str
    recommended_manual_action: str
    customer_contact_authorized: bool
    customer_contact_performed: bool
    reminder_scheduled: bool
    acceptance_inferred: bool
    closure_recommended: bool
    evaluation_date: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "route_kind": self.route_kind,
            "recommended_manual_action": self.recommended_manual_action,
            "customer_contact_authorized": self.customer_contact_authorized,
            "customer_contact_performed": self.customer_contact_performed,
            "reminder_scheduled": self.reminder_scheduled,
            "acceptance_inferred": self.acceptance_inferred,
            "closure_recommended": self.closure_recommended,
            "evaluation_date": self.evaluation_date,
        }


# ---------------------------------------------------------------------------
# Resolution route (the durable recommendation record)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PostDeliveryResolutionRoute:
    schema_version: str
    resolution_route_id: str
    project_id: str
    customer_reference: str
    source_stage8p_receipt_record_id: str | None
    source_stage8p_customer_decision_id: str | None
    source_stage8p_aggregate_outcome: str
    source_actual_delivery_record_id: str
    source_delivery_package_id: str
    source_delivery_authorization_id: str
    source_render_completion_id: str
    source_delivery_lineage_id: str | None
    artifact_id: str
    artifact_sha256: str
    route_status: str
    recommended_route: str
    closure_eligibility_status: str | None
    issue_qualification: str | None
    revision_eligibility_status: str | None
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    required_operator_actions: tuple[str, ...]
    safe_evidence_references: tuple[str, ...]
    manual_action_required: bool
    customer_contact_authorized: bool = False
    customer_contact_performed: bool = False
    project_closure_authorized: bool = False
    project_closed: bool = False
    revision_creation_authorized: bool = False
    revision_created: bool = False
    dispute_creation_authorized: bool = False
    dispute_created: bool = False
    rerender_authorized: bool = False
    hvs_invoked: bool = False
    invoice_state_changed: bool = False
    payment_state_changed: bool = False
    automation_allowed: bool = False
    deterministic_content_hash: str = ""
    informational_evaluation_date: str = ""
    informational_recorded_at: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != ROUTE_MODEL_SCHEMA_VERSION:
            raise ValueError("resolution route schema version mismatch")
        _require_member(self.route_status, ALLOWED_ROUTING_STATUSES, ERR_INVALID_ROUTE_STATUS, self.route_status)
        _require_member(self.recommended_route, ALLOWED_RECOMMENDED_ROUTES, ERR_INVALID_RECOMMENDED_ROUTE, self.recommended_route)
        if self.closure_eligibility_status is not None:
            _require_member(self.closure_eligibility_status, ALLOWED_CLOSURE_ELIGIBILITY, ERR_INVALID_CLOSURE_ELIGIBILITY, self.closure_eligibility_status)
        if self.issue_qualification is not None:
            _require_member(self.issue_qualification, ALLOWED_ISSUE_QUALIFICATIONS, ERR_INVALID_ISSUE_QUALIFICATION, self.issue_qualification)
        if self.revision_eligibility_status is not None:
            _require_member(self.revision_eligibility_status, ALLOWED_REVISION_ELIGIBILITY, ERR_INVALID_REVISION_ELIGIBILITY, self.revision_eligibility_status)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "resolution_route_id": self.resolution_route_id,
            "project_id": self.project_id,
            "customer_reference": self.customer_reference,
            "source_stage8p_receipt_record_id": self.source_stage8p_receipt_record_id,
            "source_stage8p_customer_decision_id": self.source_stage8p_customer_decision_id,
            "source_stage8p_aggregate_outcome": self.source_stage8p_aggregate_outcome,
            "source_actual_delivery_record_id": self.source_actual_delivery_record_id,
            "source_delivery_package_id": self.source_delivery_package_id,
            "source_delivery_authorization_id": self.source_delivery_authorization_id,
            "source_render_completion_id": self.source_render_completion_id,
            "source_delivery_lineage_id": self.source_delivery_lineage_id,
            "artifact_id": self.artifact_id,
            "artifact_sha256": self.artifact_sha256,
            "route_status": self.route_status,
            "recommended_route": self.recommended_route,
            "closure_eligibility_status": self.closure_eligibility_status,
            "issue_qualification": self.issue_qualification,
            "revision_eligibility_status": self.revision_eligibility_status,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "required_operator_actions": list(self.required_operator_actions),
            "safe_evidence_references": list(self.safe_evidence_references),
            "manual_action_required": self.manual_action_required,
            "customer_contact_authorized": self.customer_contact_authorized,
            "customer_contact_performed": self.customer_contact_performed,
            "project_closure_authorized": self.project_closure_authorized,
            "project_closed": self.project_closed,
            "revision_creation_authorized": self.revision_creation_authorized,
            "revision_created": self.revision_created,
            "dispute_creation_authorized": self.dispute_creation_authorized,
            "dispute_created": self.dispute_created,
            "rerender_authorized": self.rerender_authorized,
            "hvs_invoked": self.hvs_invoked,
            "invoice_state_changed": self.invoice_state_changed,
            "payment_state_changed": self.payment_state_changed,
            "automation_allowed": self.automation_allowed,
            "deterministic_content_hash": self.deterministic_content_hash,
            "informational_evaluation_date": self.informational_evaluation_date,
            "informational_recorded_at": self.informational_recorded_at,
        }


# ---------------------------------------------------------------------------
# Operator decision (authorization evidence only; never executes)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PostDeliveryRouteDecision:
    schema_version: str
    route_decision_id: str
    resolution_route_id: str
    decision_action: str
    operator_id: str
    reason: str | None
    route_content_hash: str
    resulting_status: str
    route_executed: bool = False
    project_closed: bool = False
    revision_created: bool = False
    dispute_created: bool = False
    customer_contact_performed: bool = False
    hvs_invoked: bool = False
    automation_allowed: bool = False
    informational_recorded_at: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != DECISION_MODEL_SCHEMA_VERSION:
            raise ValueError("route decision schema version mismatch")
        _require_member(self.decision_action, ALLOWED_DECISION_ACTIONS, ERR_INVALID_DECISION_ACTION, self.decision_action)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "route_decision_id": self.route_decision_id,
            "resolution_route_id": self.resolution_route_id,
            "decision_action": self.decision_action,
            "operator_id": self.operator_id,
            "reason": self.reason,
            "route_content_hash": self.route_content_hash,
            "resulting_status": self.resulting_status,
            "route_executed": self.route_executed,
            "project_closed": self.project_closed,
            "revision_created": self.revision_created,
            "dispute_created": self.dispute_created,
            "customer_contact_performed": self.customer_contact_performed,
            "hvs_invoked": self.hvs_invoked,
            "automation_allowed": self.automation_allowed,
            "informational_recorded_at": self.informational_recorded_at,
        }


# ---------------------------------------------------------------------------
# Read-only readiness view (no mutation)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Stage8QReadinessView:
    schema_version: str
    resolution_route_id: str | None
    project_id: str
    customer_reference: str
    actual_delivery_record_id: str
    artifact_sha256: str
    source_stage8p_aggregate_outcome: str
    recommended_route: str | None
    route_status: str | None
    closure_eligibility_status: str | None
    issue_qualification: str | None
    revision_eligibility_status: str | None
    operator_decision_id: str | None
    operator_decision_status: str | None
    evaluation_date: str | None
    # Boundary flags always false for Stage 8Q.
    customer_contact_authorized: bool = False
    customer_contact_performed: bool = False
    project_closure_authorized: bool = False
    project_closed: bool = False
    revision_creation_authorized: bool = False
    revision_created: bool = False
    dispute_creation_authorized: bool = False
    dispute_created: bool = False
    rerender_authorized: bool = False
    hvs_invoked: bool = False
    invoice_state_changed: bool = False
    payment_state_changed: bool = False
    automation_allowed: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != READINESS_SCHEMA_VERSION:
            raise ValueError("stage8q readiness schema version mismatch")
        if self.recommended_route is not None:
            _require_member(self.recommended_route, ALLOWED_RECOMMENDED_ROUTES, ERR_INVALID_RECOMMENDED_ROUTE, self.recommended_route)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "resolution_route_id": self.resolution_route_id,
            "project_id": self.project_id,
            "customer_reference": self.customer_reference,
            "actual_delivery_record_id": self.actual_delivery_record_id,
            "artifact_sha256": self.artifact_sha256,
            "source_stage8p_aggregate_outcome": self.source_stage8p_aggregate_outcome,
            "recommended_route": self.recommended_route,
            "route_status": self.route_status,
            "closure_eligibility_status": self.closure_eligibility_status,
            "issue_qualification": self.issue_qualification,
            "revision_eligibility_status": self.revision_eligibility_status,
            "operator_decision_id": self.operator_decision_id,
            "operator_decision_status": self.operator_decision_status,
            "evaluation_date": self.evaluation_date,
            "customer_contact_authorized": self.customer_contact_authorized,
            "customer_contact_performed": self.customer_contact_performed,
            "project_closure_authorized": self.project_closure_authorized,
            "project_closed": self.project_closed,
            "revision_creation_authorized": self.revision_creation_authorized,
            "revision_created": self.revision_created,
            "dispute_creation_authorized": self.dispute_creation_authorized,
            "dispute_created": self.dispute_created,
            "rerender_authorized": self.rerender_authorized,
            "hvs_invoked": self.hvs_invoked,
            "invoice_state_changed": self.invoice_state_changed,
            "payment_state_changed": self.payment_state_changed,
            "automation_allowed": self.automation_allowed,
        }


# ---------------------------------------------------------------------------
# Append-only event
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PostDeliveryResolutionEvent:
    schema_version: str
    event_id: str
    event_type: str
    resolution_route_id: str
    project_id: str
    actual_delivery_record_id: str
    artifact_sha256: str
    source_aggregate_outcome: str
    recommended_route: str
    resulting_status: str
    operator_id: str
    informational_recorded_at: str
    deterministic_content_hash: str = ""
    route_content_hash: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != EVENT_SCHEMA_VERSION:
            raise ValueError("stage8q event schema version mismatch")
        _require_member(self.event_type, ALLOWED_EVENT_TYPES, "invalid_event_type", self.event_type)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "resolution_route_id": self.resolution_route_id,
            "project_id": self.project_id,
            "actual_delivery_record_id": self.actual_delivery_record_id,
            "artifact_sha256": self.artifact_sha256,
            "source_aggregate_outcome": self.source_aggregate_outcome,
            "recommended_route": self.recommended_route,
            "resulting_status": self.resulting_status,
            "operator_id": self.operator_id,
            "informational_recorded_at": self.informational_recorded_at,
            "deterministic_content_hash": self.deterministic_content_hash,
            "route_content_hash": self.route_content_hash,
        }


# ---------------------------------------------------------------------------
# Deterministic identity builders (no volatile inputs)
# ---------------------------------------------------------------------------
def resolution_route_id(*, binding: PostDeliverySourceBinding, recommended_route: str,
                        closure_eligibility_status: str | None, issue_qualification: str | None,
                        revision_eligibility_status: str | None, evaluation_date: str | None,
                        normalized_qualification: str) -> str:
    return stable_id(
        "scos-hvs-stage8q-route",
        {
            "actual_delivery_record_id": binding.actual_delivery_record_id,
            "delivery_package_id": binding.delivery_package_id,
            "delivery_authorization_id": binding.delivery_authorization_id,
            "delivery_lineage_id": binding.delivery_lineage_id or "",
            "artifact_sha256": binding.artifact_sha256.lower(),
            "source_stage8p_receipt_record_id": binding.source_stage8p_receipt_record_id or "",
            "source_stage8p_customer_decision_id": binding.source_stage8p_customer_decision_id or "",
            "source_stage8p_aggregate_outcome": binding.source_stage8p_aggregate_outcome,
            "recommended_route": recommended_route,
            "closure_eligibility_status": closure_eligibility_status or "",
            "issue_qualification": issue_qualification or "",
            "revision_eligibility_status": revision_eligibility_status or "",
            "evaluation_date": evaluation_date or "",
            "normalized_qualification": normalized_qualification,
        },
    )


def route_decision_id(*, resolution_route_id: str, route_content_hash: str,
                      decision_action: str, normalized_reason: str) -> str:
    return stable_id(
        "scos-hvs-stage8q-decision",
        {
            "resolution_route_id": resolution_route_id,
            "route_content_hash": route_content_hash,
            "decision_action": decision_action,
            "normalized_reason": normalized_reason,
        },
    )


def resolution_event_id(*, event_type: str, resolution_route_id: str, record: dict[str, Any]) -> str:
    return stable_id(
        "scos-hvs-stage8q-event",
        {"event_type": event_type, "resolution_route_id": resolution_route_id, "record": record},
    )


def route_content_hash(route: dict[str, Any]) -> str:
    """Deterministic content hash over the route, excluding volatile fields."""
    volatile = {
        "deterministic_content_hash",
        "informational_evaluation_date",
        "informational_recorded_at",
    }
    canonical = canonical_json({k: v for k, v in route.items() if k not in volatile})
    return stable_id("scos-hvs-stage8q-content", {"record": canonical})


__all__ = [
    "STAGE8Q_SCHEMA_VERSION",
    "ROUTE_MODEL_SCHEMA_VERSION",
    "DECISION_MODEL_SCHEMA_VERSION",
    "EVENT_SCHEMA_VERSION",
    "READINESS_SCHEMA_VERSION",
    "DEFAULT_RESOLUTION_RELATIVE",
    "LEDGER_NAME",
    "ROUTING_DRAFT",
    "ROUTING_NEEDS_OPERATOR_INPUT",
    "ROUTING_READY_FOR_OPERATOR_REVIEW",
    "ROUTING_APPROVED",
    "ROUTING_REJECTED",
    "ROUTING_CANCELLED",
    "ROUTING_BLOCKED",
    "ROUTING_EXPIRED",
    "ALLOWED_ROUTING_STATUSES",
    "ROUTE_CLOSURE_ELIGIBILITY_REVIEW",
    "ROUTE_MANUAL_ACCEPTANCE_FOLLOW_UP",
    "ROUTE_MANUAL_RECEIPT_FOLLOW_UP",
    "ROUTE_CUSTOMER_REJECTION_RESOLUTION_REVIEW",
    "ROUTE_SUPPORT_REVIEW",
    "ROUTE_DEFECT_REVIEW",
    "ROUTE_DISPUTE_ELIGIBILITY_REVIEW",
    "ROUTE_REVISION_ELIGIBILITY_REVIEW",
    "ROUTE_OPERATOR_INVESTIGATION",
    "ROUTE_NO_ACTION_REQUIRED",
    "ROUTE_BLOCKED",
    "ALLOWED_RECOMMENDED_ROUTES",
    "CLOSURE_ELIGIBLE",
    "CLOSURE_NOT_ELIGIBLE",
    "CLOSURE_NEEDS_OPERATOR_INPUT",
    "CLOSURE_BLOCKED",
    "ALLOWED_CLOSURE_ELIGIBILITY",
    "ISSUE_SUPPORT_CANDIDATE",
    "ISSUE_DEFECT_CANDIDATE",
    "ISSUE_DISPUTE_CANDIDATE",
    "ISSUE_REVISION_CANDIDATE",
    "ISSUE_GENERAL_RESOLUTION_REVIEW",
    "ISSUE_INSUFFICIENT_EVIDENCE",
    "ISSUE_BLOCKED",
    "ALLOWED_ISSUE_QUALIFICATIONS",
    "REVISION_ELIGIBLE",
    "REVISION_NOT_ELIGIBLE",
    "REVISION_NEEDS_OPERATOR_INPUT",
    "REVISION_BLOCKED",
    "ALLOWED_REVISION_ELIGIBILITY",
    "DECISION_APPROVE_CLOSURE_RECOMMENDATION",
    "DECISION_APPROVE_MANUAL_FOLLOW_UP_RECOMMENDATION",
    "DECISION_APPROVE_SUPPORT_REVIEW_ROUTE",
    "DECISION_APPROVE_DEFECT_REVIEW_ROUTE",
    "DECISION_APPROVE_DISPUTE_ELIGIBILITY_REVIEW",
    "DECISION_APPROVE_REVISION_ELIGIBILITY_REVIEW",
    "DECISION_REJECT_ROUTE_RECOMMENDATION",
    "DECISION_CANCEL_ROUTE_REVIEW",
    "ALLOWED_DECISION_ACTIONS",
    "EVT_ROUTE_CREATED",
    "EVT_ROUTE_REEVALUATED",
    "EVT_ROUTE_APPROVED",
    "EVT_ROUTE_REJECTED",
    "EVT_ROUTE_CANCELLED",
    "ALLOWED_EVENT_TYPES",
    "ISSUE_CATEGORY_TO_QUALIFICATION",
    "ERR_MISSING_OPERATOR_ID",
    "ERR_MISSING_SOURCE_BINDING",
    "ERR_MISSING_DELIVERY_RECORD_ID",
    "ERR_DELIVERY_RECORD_NOT_FOUND",
    "ERR_STAGE8P_NOT_VERIFIED",
    "ERR_UNKNOWN_AGGREGATE_OUTCOME",
    "ERR_FORGED_RECEIPT",
    "ERR_FORGED_DECISION",
    "ERR_ARTIFACT_SHA_MISMATCH",
    "ERR_CUSTOMER_REFERENCE_MISMATCH",
    "ERR_DELIVERY_LINEAGE_MISMATCH",
    "ERR_CONFLICTING_DECISIONS",
    "ERR_UNSAFE_ISSUE_CONTENT",
    "ERR_UNSAFE_EVIDENCE_REFERENCE",
    "ERR_MISSING_ISSUE_SUMMARY",
    "ERR_INVALID_ROUTE_STATUS",
    "ERR_INVALID_RECOMMENDED_ROUTE",
    "ERR_INVALID_CLOSURE_ELIGIBILITY",
    "ERR_INVALID_ISSUE_QUALIFICATION",
    "ERR_INVALID_REVISION_ELIGIBILITY",
    "ERR_INVALID_DECISION_ACTION",
    "ERR_ROUTE_NOT_FOUND",
    "ERR_DECISION_REQUIRES_REASON",
    "ERR_ROUTE_CONTENT_CONFLICT",
    "ERR_DECISION_ALREADY_FINAL",
    "ERR_MISSING_DECISION_HASH",
    "ERR_ROUTE_HASH_MISMATCH",
    "ERR_UNSAFE_FREE_TEXT",
    "ERR_UNKNOWN_SCHEMA_VERSION",
    "ERR_MISSING_EVALUATION_DATE",
    "ERR_INVALID_EVALUATION_DATE",
    "_bounded",
    "_require_member",
    "_require_operator_id",
    "_require_nonempty",
    "_require_date",
    "_require_evidence_reference",
    "_require_issue_summary",
    "_require_free_text",
    "_immutable_hash",
    "sha256_bytes",
    "PostDeliverySourceBinding",
    "ClosureEligibilityResult",
    "IssueQualificationResult",
    "RevisionQualificationResult",
    "FollowUpRecommendation",
    "PostDeliveryResolutionRoute",
    "PostDeliveryRouteDecision",
    "Stage8QReadinessView",
    "PostDeliveryResolutionEvent",
    "resolution_route_id",
    "route_decision_id",
    "resolution_event_id",
    "route_content_hash",
]
