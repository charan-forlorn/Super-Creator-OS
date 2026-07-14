"""SCOS <-> HVS — Stage 8R operator-controlled resolution action execution.

Stage 8R consumes exactly one approved Stage 8Q resolution route and executes
exactly one matching internal SCOS action. It is deterministic, local-only and
operator-controlled.

Stage 8R:

  * never contacts a customer / performs any transport,
  * never invokes HVS, renders, delivers, uploads, or publishes,
  * never creates or mutates invoices / payments,
  * never begins Stage 8S,
  * never performs more than one target-domain mutation per request,
  * never reuses the Stage 8Q route approval as its own execution approval.

It binds every execution request to one Stage 8Q route (and the bound Stage 8P
/ Stage 8O evidence chain), reuses the repository's deterministic identity
helpers (``canonical_json`` / ``stable_id``) and the safe-text discipline of
Stage 8Q. ``automation_allowed`` is always ``False``. No clock, no random, no
uuid, no network, no subprocess.

Recommendation != Execution at every layer. A Stage 8Q route approval
authorizes only route selection; a separate Stage 8R execution approval is
required before any mutation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .hvs_commercial_proposal_models import canonical_json, stable_id
from .hvs_customer_outcome_models import validate_calendar_date
from .hvs_post_delivery_resolution_service import (
    inspect_post_delivery_route,
    route_content_hash,
)
from .hvs_post_delivery_resolution_models import (
    ALLOWED_RECOMMENDED_ROUTES,
    PostDeliveryResolutionRoute,
)

# --- schema / identity -------------------------------------------------------
STAGE8R_SCHEMA_VERSION = "scos-hvs.stage8r.resolution-action.v1/1.0.0"
REQUEST_MODEL_SCHEMA_VERSION = "scos-hvs.stage8r.execution-request.v1/1.0.0"
APPROVAL_MODEL_SCHEMA_VERSION = "scos-hvs.stage8r.execution-approval.v1/1.0.0"
OUTCOME_MODEL_SCHEMA_VERSION = "scos-hvs.stage8r.action-outcome.v1/1.0.0"
EVENT_SCHEMA_VERSION = "scos-hvs.stage8r.event.v1/1.0.0"
FOLLOWUP_MODEL_SCHEMA_VERSION = "scos-hvs.stage8r.manual-follow-up.v1/1.0.0"

# Deterministic runtime root under the gitignored scos/work tree.
DEFAULT_RUNTIME_RELATIVE = "scos/work/hvs_stage8r_resolution_action"
LEDGER_NAME = "stage8r_resolution_action_ledger.jsonl"

# --- Action families ---------------------------------------------------------
ACTION_PROJECT_CLOSURE_EXECUTION = "PROJECT_CLOSURE_EXECUTION"
ACTION_REVISION_REQUEST_CREATION = "REVISION_REQUEST_CREATION"
ACTION_DISPUTE_OPENING = "DISPUTE_OPENING"
ACTION_MANUAL_FOLLOW_UP_RECORD_CREATION = "MANUAL_FOLLOW_UP_RECORD_CREATION"
ALLOWED_ACTION_FAMILIES = (
    ACTION_PROJECT_CLOSURE_EXECUTION,
    ACTION_REVISION_REQUEST_CREATION,
    ACTION_DISPUTE_OPENING,
    ACTION_MANUAL_FOLLOW_UP_RECORD_CREATION,
)

# --- Execution request status ------------------------------------------------
REQ_DRAFT = "DRAFT"
REQ_NEEDS_OPERATOR_INPUT = "NEEDS_OPERATOR_INPUT"
REQ_READY_FOR_EXECUTION_REVIEW = "READY_FOR_EXECUTION_REVIEW"
REQ_APPROVED_FOR_EXECUTION = "APPROVED_FOR_EXECUTION"
REQ_REJECTED = "REJECTED"
REQ_CANCELLED = "CANCELLED"
REQ_EXPIRED = "EXPIRED"
ALLOWED_REQUEST_STATUSES = (
    REQ_DRAFT,
    REQ_NEEDS_OPERATOR_INPUT,
    REQ_READY_FOR_EXECUTION_REVIEW,
    REQ_APPROVED_FOR_EXECUTION,
    REQ_REJECTED,
    REQ_CANCELLED,
    REQ_EXPIRED,
)

# --- Execution status --------------------------------------------------------
EXEC_NOT_STARTED = "NOT_STARTED"
EXEC_EXECUTING = "EXECUTING"
EXEC_COMPLETED = "COMPLETED"
EXEC_FAILED = "FAILED"
EXEC_BLOCKED = "BLOCKED"
EXEC_CONFLICTED = "CONFLICTED"
ALLOWED_EXECUTION_STATUSES = (
    EXEC_NOT_STARTED,
    EXEC_EXECUTING,
    EXEC_COMPLETED,
    EXEC_FAILED,
    EXEC_BLOCKED,
    EXEC_CONFLICTED,
)

# --- Outcome status ----------------------------------------------------------
OUT_VERIFIED = "VERIFIED"
OUT_TARGET_RECORD_MISSING = "TARGET_RECORD_MISSING"
OUT_TARGET_RECORD_MISMATCH = "TARGET_RECORD_MISMATCH"
OUT_PARTIAL_EFFECT_DETECTED = "PARTIAL_EFFECT_DETECTED"
OUT_AUDIT_INCOMPLETE = "AUDIT_INCOMPLETE"
OUT_FAILED = "FAILED"
ALLOWED_OUTCOME_STATUSES = (
    OUT_VERIFIED,
    OUT_TARGET_RECORD_MISSING,
    OUT_TARGET_RECORD_MISMATCH,
    OUT_PARTIAL_EFFECT_DETECTED,
    OUT_AUDIT_INCOMPLETE,
    OUT_FAILED,
)

# --- Eligibility status ------------------------------------------------------
ELIG_READY = "READY"
ELIG_NEEDS_OPERATOR_INPUT = "NEEDS_OPERATOR_INPUT"
ELIG_BLOCKED = "BLOCKED"
ELIG_EXPIRED = "EXPIRED"
ELIG_CONFLICTED = "CONFLICTED"
ELIG_ALREADY_COMPLETED = "ALREADY_COMPLETED"
ALLOWED_ELIGIBILITY_STATUSES = (
    ELIG_READY,
    ELIG_NEEDS_OPERATOR_INPUT,
    ELIG_BLOCKED,
    ELIG_EXPIRED,
    ELIG_CONFLICTED,
    ELIG_ALREADY_COMPLETED,
)

# --- Decisions ---------------------------------------------------------------
DECISION_APPROVE = "APPROVE"
DECISION_REJECT = "REJECT"
ALLOWED_DECISIONS = (DECISION_APPROVE, DECISION_REJECT)

# --- Append-only event types -------------------------------------------------
EVT_EXECUTION_REQUEST_CREATED = "EXECUTION_REQUEST_CREATED"
EVT_ELIGIBILITY_EVALUATED = "ELIGIBILITY_EVALUATED"
EVT_EXECUTION_APPROVED = "EXECUTION_APPROVED"
EVT_EXECUTION_REJECTED = "EXECUTION_REJECTED"
EVT_EXECUTION_CANCELLED = "EXECUTION_CANCELLED"
EVT_PRE_EXECUTION_REVERIFIED = "PRE_EXECUTION_REVERIFIED"
EVT_TARGET_ACTION_STARTED = "TARGET_ACTION_STARTED"
EVT_TARGET_ACTION_COMPLETED = "TARGET_ACTION_COMPLETED"
EVT_TARGET_ACTION_FAILED = "TARGET_ACTION_FAILED"
EVT_TARGET_RECORD_VERIFIED = "TARGET_RECORD_VERIFIED"
EVT_OUTCOME_EVIDENCE_CREATED = "OUTCOME_EVIDENCE_CREATED"
EVT_CONFLICT_DETECTED = "CONFLICT_DETECTED"
ALLOWED_EVENT_TYPES = (
    EVT_EXECUTION_REQUEST_CREATED,
    EVT_ELIGIBILITY_EVALUATED,
    EVT_EXECUTION_APPROVED,
    EVT_EXECUTION_REJECTED,
    EVT_EXECUTION_CANCELLED,
    EVT_PRE_EXECUTION_REVERIFIED,
    EVT_TARGET_ACTION_STARTED,
    EVT_TARGET_ACTION_COMPLETED,
    EVT_TARGET_ACTION_FAILED,
    EVT_TARGET_RECORD_VERIFIED,
    EVT_OUTCOME_EVIDENCE_CREATED,
    EVT_CONFLICT_DETECTED,
)

# --- Target-domain intent labels (used in contract hashing) ------------------
TARGET_DOMAIN_CLOSURE = "delivery_closure"
TARGET_DOMAIN_REVISION = "revision_request"
TARGET_DOMAIN_DISPUTE = "post_delivery_dispute"
TARGET_DOMAIN_FOLLOW_UP = "manual_follow_up"

# --- Route -> action-family compatibility matrix ----------------------------
# Real Stage 8Q recommended_route enums mapped to the compatible Stage 8R action
# families. A route that is not present in this matrix (e.g. NO_ACTION_REQUIRED,
# BLOCKED, OPERATOR_INVESTIGATION) is incompatible with every action family.
ROUTE_TO_ALLOWED_ACTIONS: dict[str, tuple[str, ...]] = {
    "CLOSURE_ELIGIBILITY_REVIEW": (ACTION_PROJECT_CLOSURE_EXECUTION,),
    "REVISION_ELIGIBILITY_REVIEW": (ACTION_REVISION_REQUEST_CREATION,),
    "DISPUTE_ELIGIBILITY_REVIEW": (ACTION_DISPUTE_OPENING,),
    "DEFECT_REVIEW": (ACTION_DISPUTE_OPENING,),
    "CUSTOMER_REJECTION_RESOLUTION_REVIEW": (ACTION_DISPUTE_OPENING,),
    "SUPPORT_REVIEW": (ACTION_MANUAL_FOLLOW_UP_RECORD_CREATION,),
    "MANUAL_ACCEPTANCE_FOLLOW_UP": (ACTION_MANUAL_FOLLOW_UP_RECORD_CREATION,),
    "MANUAL_RECEIPT_FOLLOW_UP": (ACTION_MANUAL_FOLLOW_UP_RECORD_CREATION,),
    "OPERATOR_INVESTIGATION": (ACTION_MANUAL_FOLLOW_UP_RECORD_CREATION,),
}

# --- error codes -------------------------------------------------------------
ERR_MISSING_OPERATOR_ID = "missing_operator_id"
ERR_MISSING_ROUTE_ID = "missing_resolution_route_id"
ERR_ROUTE_NOT_FOUND = "resolution_route_not_found"
ERR_ROUTE_NOT_APPROVED = "resolution_route_not_approved"
ERR_ROUTE_CONTENT_HASH_MISMATCH = "route_content_hash_mismatch"
ERR_ROUTE_RECOMMENDATION_MISMATCH = "route_recommendation_mismatch"
ERR_STAGE8P_LINEAGE_MISMATCH = "stage8p_8o_identity_mismatch"
ERR_MISSING_ACTION_FAMILY = "missing_action_family"
ERR_INVALID_ACTION_FAMILY = "invalid_action_family"
ERR_ACTION_ROUTE_INCOMPATIBLE = "action_route_incompatible"
ERR_TOO_MANY_ACTIONS = "too_many_action_families"
ERR_COMPOSITE_ACTION = "composite_action_string"
ERR_MISSING_ACTION_PARAMS = "missing_action_parameters"
ERR_INVALID_ACTION_PARAMS = "invalid_action_parameters"
ERR_EXECUTION_REQUEST_NOT_FOUND = "execution_request_not_found"
ERR_EXECUTION_REQUEST_NOT_APPROVED = "execution_request_not_approved"
ERR_EXECUTION_APPROVAL_NOT_FOUND = "execution_approval_not_found"
ERR_APPROVAL_REQUEST_MISMATCH = "execution_approval_request_mismatch"
ERR_APPROVAL_CONTRACT_MISMATCH = "execution_approval_contract_mismatch"
ERR_APPROVAL_ACTION_MISMATCH = "execution_approval_action_mismatch"
ERR_APPROVAL_REUSE_REJECTED = "execution_approval_reuse_rejected"
ERR_MISSING_REASON = "decision_requires_reason"
ERR_ELIGIBILITY_NOT_READY = "eligibility_not_ready"
ERR_PRE_EXECUTION_FAILED = "pre_execution_reverification_failed"
ERR_TARGET_MUTATION_FAILED = "target_domain_mutation_failed"
ERR_TARGET_RECORD_MISSING = "target_record_missing"
ERR_TARGET_RECORD_MISMATCH = "target_record_mismatch"
ERR_PARTIAL_EFFECT = "partial_effect_detected"
ERR_CONFLICTING_EXECUTION = "conflicting_execution"
ERR_UNSAFE_TEXT = "unsafe_text"
ERR_INVALID_ID = "invalid_identifier"
ERR_INVALID_DATE = "invalid_date"


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


def _require_safe_id(value: str, *, field_name: str, max_len: int = 256) -> str:
    v = _bounded(value, max_len=max_len, field_name=field_name)
    if not v:
        raise ValueError(f"{field_name} is required")
    return v


def _require_date(value: str, *, field_name: str) -> str:
    v = _bounded(value, max_len=64, field_name=field_name)
    if not v:
        raise ValueError(f"{field_name} is required")
    validate_calendar_date(field_name, v)
    return v


def _require_free_text(value: str, *, max_len: int = 512, field_name: str) -> str:
    if value is None:
        return ""
    v = _bounded(str(value).strip(), max_len=max_len, field_name=field_name)
    if not v:
        return ""
    lowered = v.lower()
    for token in ("password", "secret", "token=", "api_key", "apikey", "credential"):
        if token in lowered:
            raise ValueError(f"{field_name} must not contain secret-like text")
    return v


def _require_issue_summary(value: str | None, *, max_len: int = 512) -> str:
    if value is None:
        return ""
    v = _bounded(value, max_len=max_len, field_name="issue_summary")
    if not v:
        raise ValueError("issue summary is required")
    lowered = v.lower()
    for token in ("password", "secret", "token=", "api_key", "apikey", "credential"):
        if token in lowered:
            raise ValueError("issue summary must not contain secret-like text")
    return v


def _immutable_hash(value: str) -> str:
    v = _bounded(value, max_len=128, field_name="artifact_sha256")
    if len(v) != 64:
        raise ValueError("artifact_sha256 must be a 64-char SHA-256 hex digest")
    return v.lower()


# ---------------------------------------------------------------------------
# Action selection (exactly one action family)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ResolutionActionSelection:
    action_family: str
    # Optional explicit normalised parameters validated per family.
    closure_reason: str | None = None
    receipt_evidence_id: str | None = None
    revision_items: tuple[dict[str, Any], ...] = ()
    requested_scope: str | None = None
    source_issue_id: str | None = None
    dispute_type: str | None = None
    dispute_reason: str | None = None
    disputed_artifact_references: tuple[str, ...] = ()
    dispute_evidence_references: tuple[str, ...] = ()
    follow_up_purpose: str | None = None
    follow_up_recommended_action: str | None = None
    follow_up_due_date: str | None = None
    follow_up_evaluation_date: str | None = None

    def __post_init__(self) -> None:
        _require_member(self.action_family, ALLOWED_ACTION_FAMILIES, ERR_INVALID_ACTION_FAMILY, self.action_family)
        _validate_selection_params(self)


def _validate_selection_params(sel: ResolutionActionSelection) -> None:
    if sel.action_family == ACTION_PROJECT_CLOSURE_EXECUTION:
        if sel.receipt_evidence_id:
            _require_safe_id(sel.receipt_evidence_id, field_name="receipt_evidence_id")
        if sel.closure_reason is not None:
            _require_free_text(sel.closure_reason, max_len=512, field_name="closure_reason")
    elif sel.action_family == ACTION_REVISION_REQUEST_CREATION:
        if sel.requested_scope is not None:
            _require_free_text(sel.requested_scope, max_len=256, field_name="requested_scope")
        items = list(sel.revision_items)
        if not (0 <= len(items) <= 64):
            raise ValueError("revision_items must contain between 0 and 64 items")
        for it in items:
            if not isinstance(it, dict):
                raise ValueError("each revision_item must be a mapping")
            for k in ("category", "description", "target_type", "target_id", "priority", "acceptance_requirement"):
                if k in it:
                    _require_free_text(str(it[k]), max_len=256, field_name=f"revision_item.{k}")
            if "source_artifact_sha256" in it:
                _immutable_hash(str(it["source_artifact_sha256"]))
    elif sel.action_family == ACTION_DISPUTE_OPENING:
        if sel.source_issue_id:
            _require_safe_id(sel.source_issue_id, field_name="source_issue_id")
        if sel.dispute_type is not None:
            _require_free_text(sel.dispute_type, max_len=128, field_name="dispute_type")
        if sel.dispute_reason is not None:
            _require_issue_summary(sel.dispute_reason)
        for ref in sel.disputed_artifact_references:
            _require_safe_id(ref, field_name="disputed_artifact_reference")
        for ref in sel.dispute_evidence_references:
            _require_safe_id(ref, field_name="dispute_evidence_reference")
    elif sel.action_family == ACTION_MANUAL_FOLLOW_UP_RECORD_CREATION:
        if sel.follow_up_purpose is not None:
            _require_free_text(sel.follow_up_purpose, max_len=256, field_name="follow_up_purpose")
        if sel.follow_up_recommended_action is not None:
            _require_free_text(sel.follow_up_recommended_action, max_len=512, field_name="follow_up_recommended_action")
        if sel.follow_up_due_date is not None:
            _require_date(sel.follow_up_due_date, field_name="follow_up_due_date")
        if sel.follow_up_evaluation_date is not None:
            _require_date(sel.follow_up_evaluation_date, field_name="follow_up_evaluation_date")


# ---------------------------------------------------------------------------
# Execution request (immutable semantic identity)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ResolutionExecutionRequest:
    schema_version: str
    execution_request_id: str
    project_id: str
    customer_reference: str
    source_actual_delivery_record_id: str
    source_stage8o_identity: str | None
    source_stage8p_record_id: str | None
    source_stage8q_route_id: str
    source_route_type: str
    source_route_content_hash: str
    source_route_approval_id: str | None
    source_artifact_id: str
    source_artifact_sha256: str
    action_family: str
    target_domain: str
    target_intent: str
    normalized_action_parameters: dict[str, Any]
    execution_contract_hash: str
    request_status: str
    operator_review_required: bool
    automation_allowed: bool = False
    customer_contact_allowed: bool = False
    hvs_action_allowed: bool = False
    invoice_mutation_allowed: bool = False
    payment_mutation_allowed: bool = False
    informational_recorded_at: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != REQUEST_MODEL_SCHEMA_VERSION:
            raise ValueError("execution request schema version mismatch")
        _require_member(self.request_status, ALLOWED_REQUEST_STATUSES, "invalid_request_status", self.request_status)
        _require_member(self.action_family, ALLOWED_ACTION_FAMILIES, ERR_INVALID_ACTION_FAMILY, self.action_family)
        if not self.execution_request_id or not self.execution_contract_hash:
            raise ValueError("execution request requires deterministic ids")
        if self.automation_allowed or self.customer_contact_allowed or self.hvs_action_allowed \
                or self.invoice_mutation_allowed or self.payment_mutation_allowed:
            raise ValueError("stage8r request must not permit unsafe effects")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "execution_request_id": self.execution_request_id,
            "project_id": self.project_id,
            "customer_reference": self.customer_reference,
            "source_actual_delivery_record_id": self.source_actual_delivery_record_id,
            "source_stage8o_identity": self.source_stage8o_identity,
            "source_stage8p_record_id": self.source_stage8p_record_id,
            "source_stage8q_route_id": self.source_stage8q_route_id,
            "source_route_type": self.source_route_type,
            "source_route_content_hash": self.source_route_content_hash,
            "source_route_approval_id": self.source_route_approval_id,
            "source_artifact_id": self.source_artifact_id,
            "source_artifact_sha256": self.source_artifact_sha256,
            "action_family": self.action_family,
            "target_domain": self.target_domain,
            "target_intent": self.target_intent,
            "normalized_action_parameters": dict(self.normalized_action_parameters),
            "execution_contract_hash": self.execution_contract_hash,
            "request_status": self.request_status,
            "operator_review_required": self.operator_review_required,
            "automation_allowed": self.automation_allowed,
            "customer_contact_allowed": self.customer_contact_allowed,
            "hvs_action_allowed": self.hvs_action_allowed,
            "invoice_mutation_allowed": self.invoice_mutation_allowed,
            "payment_mutation_allowed": self.payment_mutation_allowed,
            "informational_recorded_at": self.informational_recorded_at,
        }


# ---------------------------------------------------------------------------
# Eligibility result (read-only)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ResolutionExecutionEligibilityResult:
    execution_request_id: str
    route_id: str
    action_family: str
    eligibility_status: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    missing_fields: tuple[str, ...]
    detected_conflicts: tuple[str, ...]
    target_domain_source_ids: tuple[str, ...]
    recommended_manual_action: str | None
    evaluation_date: str | None
    automation_allowed: bool = False

    def __post_init__(self) -> None:
        _require_member(self.eligibility_status, ALLOWED_ELIGIBILITY_STATUSES, "invalid_eligibility_status", self.eligibility_status)

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_request_id": self.execution_request_id,
            "route_id": self.route_id,
            "action_family": self.action_family,
            "eligibility_status": self.eligibility_status,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "missing_fields": list(self.missing_fields),
            "detected_conflicts": list(self.detected_conflicts),
            "target_domain_source_ids": list(self.target_domain_source_ids),
            "recommended_manual_action": self.recommended_manual_action,
            "evaluation_date": self.evaluation_date,
            "automation_allowed": self.automation_allowed,
        }


# ---------------------------------------------------------------------------
# Execution approval (separate from Stage 8Q route approval)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ResolutionExecutionApproval:
    schema_version: str
    execution_approval_id: str
    execution_request_id: str
    execution_contract_hash: str
    route_id: str
    route_content_hash: str
    action_family: str
    project_id: str
    customer_reference: str
    artifact_sha256: str
    operator_id: str
    decision: str
    reason: str | None
    informational_recorded_at: str = ""
    automation_allowed: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != APPROVAL_MODEL_SCHEMA_VERSION:
            raise ValueError("execution approval schema version mismatch")
        _require_member(self.decision, ALLOWED_DECISIONS, "invalid_decision", self.decision)
        if not self.execution_approval_id:
            raise ValueError("execution approval requires a deterministic id")
        if self.automation_allowed:
            raise ValueError("stage8r approval must not permit automation")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "execution_approval_id": self.execution_approval_id,
            "execution_request_id": self.execution_request_id,
            "execution_contract_hash": self.execution_contract_hash,
            "route_id": self.route_id,
            "route_content_hash": self.route_content_hash,
            "action_family": self.action_family,
            "project_id": self.project_id,
            "customer_reference": self.customer_reference,
            "artifact_sha256": self.artifact_sha256,
            "operator_id": self.operator_id,
            "decision": self.decision,
            "reason": self.reason,
            "informational_recorded_at": self.informational_recorded_at,
            "automation_allowed": self.automation_allowed,
        }


# ---------------------------------------------------------------------------
# Local manual follow-up record (narrow Stage 8R-owned record abstraction)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ManualFollowUpRecord:
    schema_version: str
    follow_up_record_id: str
    execution_request_id: str
    route_id: str
    action_family: str
    project_id: str
    customer_reference: str
    artifact_sha256: str
    purpose: str
    recommended_manual_action: str
    due_date: str | None
    evaluation_date: str | None
    external_task_created: bool = False
    calendar_event_created: bool = False
    customer_contact_performed: bool = False
    follow_up_completed: bool = False
    automation_allowed: bool = False
    informational_recorded_at: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != FOLLOWUP_MODEL_SCHEMA_VERSION:
            raise ValueError("manual follow-up schema version mismatch")
        if self.external_task_created or self.calendar_event_created or self.customer_contact_performed \
                or self.follow_up_completed or self.automation_allowed:
            raise ValueError("manual follow-up record must not record any external effect")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "follow_up_record_id": self.follow_up_record_id,
            "execution_request_id": self.execution_request_id,
            "route_id": self.route_id,
            "action_family": self.action_family,
            "project_id": self.project_id,
            "customer_reference": self.customer_reference,
            "artifact_sha256": self.artifact_sha256,
            "purpose": self.purpose,
            "recommended_manual_action": self.recommended_manual_action,
            "due_date": self.due_date,
            "evaluation_date": self.evaluation_date,
            "external_task_created": self.external_task_created,
            "calendar_event_created": self.calendar_event_created,
            "customer_contact_performed": self.customer_contact_performed,
            "follow_up_completed": self.follow_up_completed,
            "automation_allowed": self.automation_allowed,
            "informational_recorded_at": self.informational_recorded_at,
        }


# ---------------------------------------------------------------------------
# Action outcome evidence
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ResolutionActionOutcomeEvidence:
    schema_version: str
    outcome_evidence_id: str
    execution_request_id: str
    execution_approval_id: str
    source_route_id: str
    action_family: str
    target_domain: str
    target_record_id: str | None
    target_record_content_hash: str | None
    target_record_verified: bool
    execution_status: str
    outcome_status: str
    side_effect_count: int
    customer_contact_performed: bool
    hvs_invoked: bool
    media_modified: bool
    invoice_state_changed: bool
    payment_state_changed: bool
    automation_allowed: bool
    audit_event_ids: tuple[str, ...]
    execution_contract_hash: str = ""
    informational_recorded_at: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != OUTCOME_MODEL_SCHEMA_VERSION:
            raise ValueError("action outcome schema version mismatch")
        _require_member(self.execution_status, ALLOWED_EXECUTION_STATUSES, "invalid_execution_status", self.execution_status)
        _require_member(self.outcome_status, ALLOWED_OUTCOME_STATUSES, "invalid_outcome_status", self.outcome_status)
        if self.side_effect_count != 1:
            raise ValueError("stage8r must record exactly one intended side effect")
        if self.customer_contact_performed or self.hvs_invoked or self.media_modified \
                or self.invoice_state_changed or self.payment_state_changed or self.automation_allowed:
            raise ValueError("stage8r outcome must not record any unsafe effect")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "outcome_evidence_id": self.outcome_evidence_id,
            "execution_request_id": self.execution_request_id,
            "execution_approval_id": self.execution_approval_id,
            "source_route_id": self.source_route_id,
            "action_family": self.action_family,
            "target_domain": self.target_domain,
            "target_record_id": self.target_record_id,
            "target_record_content_hash": self.target_record_content_hash,
            "target_record_verified": self.target_record_verified,
            "execution_status": self.execution_status,
            "outcome_status": self.outcome_status,
            "side_effect_count": self.side_effect_count,
            "customer_contact_performed": self.customer_contact_performed,
            "hvs_invoked": self.hvs_invoked,
            "media_modified": self.media_modified,
            "invoice_state_changed": self.invoice_state_changed,
            "payment_state_changed": self.payment_state_changed,
            "automation_allowed": self.automation_allowed,
            "audit_event_ids": list(self.audit_event_ids),
            "execution_contract_hash": self.execution_contract_hash,
            "informational_recorded_at": self.informational_recorded_at,
        }


# ---------------------------------------------------------------------------
# Append-only event
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ResolutionActionEvent:
    schema_version: str
    event_id: str
    event_type: str
    execution_request_id: str
    project_id: str
    customer_reference: str
    artifact_sha256: str
    action_family: str
    source_route_id: str
    resulting_status: str
    operator_id: str
    informational_recorded_at: str
    execution_contract_hash: str = ""
    target_record_id: str = ""
    detail: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != EVENT_SCHEMA_VERSION:
            raise ValueError("stage8r event schema version mismatch")
        _require_member(self.event_type, ALLOWED_EVENT_TYPES, "invalid_event_type", self.event_type)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "execution_request_id": self.execution_request_id,
            "project_id": self.project_id,
            "customer_reference": self.customer_reference,
            "artifact_sha256": self.artifact_sha256,
            "action_family": self.action_family,
            "source_route_id": self.source_route_id,
            "resulting_status": self.resulting_status,
            "operator_id": self.operator_id,
            "informational_recorded_at": self.informational_recorded_at,
            "execution_contract_hash": self.execution_contract_hash,
            "target_record_id": self.target_record_id,
            "detail": self.detail,
        }


# ---------------------------------------------------------------------------
# Deterministic identity builders (no volatile inputs)
# ---------------------------------------------------------------------------
def action_target_domain(action_family: str) -> str:
    return {
        ACTION_PROJECT_CLOSURE_EXECUTION: TARGET_DOMAIN_CLOSURE,
        ACTION_REVISION_REQUEST_CREATION: TARGET_DOMAIN_REVISION,
        ACTION_DISPUTE_OPENING: TARGET_DOMAIN_DISPUTE,
        ACTION_MANUAL_FOLLOW_UP_RECORD_CREATION: TARGET_DOMAIN_FOLLOW_UP,
    }[action_family]


def execution_request_id(
    *,
    route_id: str,
    route_content_hash: str,
    action_family: str,
    project_id: str,
    customer_reference: str,
    artifact_sha256: str,
    normalized_target_intent: str,
    normalized_action_parameters: dict[str, Any],
    target_source_ids: tuple[str, ...],
) -> str:
    return stable_id(
        "scos-hvs-stage8r-execution-request",
        {
            "resolution_route_id": route_id,
            "route_content_hash": route_content_hash,
            "action_family": action_family,
            "project_id": project_id,
            "customer_reference": customer_reference.lower(),
            "artifact_sha256": artifact_sha256.lower(),
            "target_intent": normalized_target_intent,
            "normalized_action_parameters": canonical_json(normalized_action_parameters),
            "target_source_ids": tuple(sorted(target_source_ids)),
        },
    )


def execution_contract_hash(
    *,
    route_id: str,
    route_content_hash: str,
    action_family: str,
    target_domain: str,
    normalized_target_intent: str,
    normalized_action_parameters: dict[str, Any],
    target_source_ids: tuple[str, ...],
) -> str:
    return stable_id(
        "scos-hvs-stage8r-contract",
        {
            "resolution_route_id": route_id,
            "route_content_hash": route_content_hash,
            "action_family": action_family,
            "target_domain": target_domain,
            "target_intent": normalized_target_intent,
            "normalized_action_parameters": canonical_json(normalized_action_parameters),
            "target_source_ids": tuple(sorted(target_source_ids)),
        },
    )


def execution_approval_id(
    *,
    execution_request_id: str,
    execution_contract_hash: str,
    route_id: str,
    route_content_hash: str,
    action_family: str,
    operator_id: str,
    decision: str,
) -> str:
    return stable_id(
        "scos-hvs-stage8r-approval",
        {
            "execution_request_id": execution_request_id,
            "execution_contract_hash": execution_contract_hash,
            "resolution_route_id": route_id,
            "route_content_hash": route_content_hash,
            "action_family": action_family,
            "operator_id": operator_id,
            "decision": decision,
        },
    )


def outcome_evidence_id(
    *,
    execution_request_id: str,
    execution_approval_id: str,
    target_record_id: str | None,
    target_record_content_hash: str | None,
    execution_status: str,
) -> str:
    return stable_id(
        "scos-hvs-stage8r-outcome",
        {
            "execution_request_id": execution_request_id,
            "execution_approval_id": execution_approval_id,
            "target_record_id": target_record_id or "",
            "target_record_content_hash": target_record_content_hash or "",
            "execution_status": execution_status,
        },
    )


def follow_up_record_id(
    *,
    execution_request_id: str,
    route_id: str,
    purpose: str,
    customer_reference: str,
    due_date: str | None,
) -> str:
    return stable_id(
        "scos-hvs-stage8r-follow-up",
        {
            "execution_request_id": execution_request_id,
            "resolution_route_id": route_id,
            "purpose": purpose,
            "customer_reference": customer_reference.lower(),
            "due_date": due_date or "",
        },
    )


def resolution_action_event_id(
    *,
    event_type: str,
    execution_request_id: str,
    record: dict[str, Any],
) -> str:
    return stable_id(
        "scos-hvs-stage8r-event",
        {"event_type": event_type, "execution_request_id": execution_request_id, "record": canonical_json(record)},
    )


def route_content_hash_for(route: PostDeliveryResolutionRoute) -> str:
    return route_content_hash(route.to_dict())


def load_stage8q_route(*, repo_root: Any, resolution_route_id: str) -> PostDeliveryResolutionRoute | None:
    """Load a genuine approved Stage 8Q route (read-only). Returns None if absent."""
    result = inspect_post_delivery_route(repo_root=repo_root, resolution_route_id=resolution_route_id)
    if not result.ok or result.resolution_route is None:
        return None
    return result.resolution_route


__all__ = [
    "STAGE8R_SCHEMA_VERSION",
    "REQUEST_MODEL_SCHEMA_VERSION",
    "APPROVAL_MODEL_SCHEMA_VERSION",
    "OUTCOME_MODEL_SCHEMA_VERSION",
    "EVENT_SCHEMA_VERSION",
    "FOLLOWUP_MODEL_SCHEMA_VERSION",
    "DEFAULT_RUNTIME_RELATIVE",
    "LEDGER_NAME",
    "ACTION_PROJECT_CLOSURE_EXECUTION",
    "ACTION_REVISION_REQUEST_CREATION",
    "ACTION_DISPUTE_OPENING",
    "ACTION_MANUAL_FOLLOW_UP_RECORD_CREATION",
    "ALLOWED_ACTION_FAMILIES",
    "REQ_DRAFT",
    "REQ_NEEDS_OPERATOR_INPUT",
    "REQ_READY_FOR_EXECUTION_REVIEW",
    "REQ_APPROVED_FOR_EXECUTION",
    "REQ_REJECTED",
    "REQ_CANCELLED",
    "REQ_EXPIRED",
    "ALLOWED_REQUEST_STATUSES",
    "EXEC_NOT_STARTED",
    "EXEC_EXECUTING",
    "EXEC_COMPLETED",
    "EXEC_FAILED",
    "EXEC_BLOCKED",
    "EXEC_CONFLICTED",
    "ALLOWED_EXECUTION_STATUSES",
    "OUT_VERIFIED",
    "OUT_TARGET_RECORD_MISSING",
    "OUT_TARGET_RECORD_MISMATCH",
    "OUT_PARTIAL_EFFECT_DETECTED",
    "OUT_AUDIT_INCOMPLETE",
    "OUT_FAILED",
    "ALLOWED_OUTCOME_STATUSES",
    "ELIG_READY",
    "ELIG_NEEDS_OPERATOR_INPUT",
    "ELIG_BLOCKED",
    "ELIG_EXPIRED",
    "ELIG_CONFLICTED",
    "ELIG_ALREADY_COMPLETED",
    "ALLOWED_ELIGIBILITY_STATUSES",
    "DECISION_APPROVE",
    "DECISION_REJECT",
    "ALLOWED_DECISIONS",
    "EVT_EXECUTION_REQUEST_CREATED",
    "EVT_ELIGIBILITY_EVALUATED",
    "EVT_EXECUTION_APPROVED",
    "EVT_EXECUTION_REJECTED",
    "EVT_EXECUTION_CANCELLED",
    "EVT_PRE_EXECUTION_REVERIFIED",
    "EVT_TARGET_ACTION_STARTED",
    "EVT_TARGET_ACTION_COMPLETED",
    "EVT_TARGET_ACTION_FAILED",
    "EVT_TARGET_RECORD_VERIFIED",
    "EVT_OUTCOME_EVIDENCE_CREATED",
    "EVT_CONFLICT_DETECTED",
    "ALLOWED_EVENT_TYPES",
    "TARGET_DOMAIN_CLOSURE",
    "TARGET_DOMAIN_REVISION",
    "TARGET_DOMAIN_DISPUTE",
    "TARGET_DOMAIN_FOLLOW_UP",
    "ROUTE_TO_ALLOWED_ACTIONS",
    "ERR_MISSING_OPERATOR_ID",
    "ERR_MISSING_ROUTE_ID",
    "ERR_ROUTE_NOT_FOUND",
    "ERR_ROUTE_NOT_APPROVED",
    "ERR_ROUTE_CONTENT_HASH_MISMATCH",
    "ERR_ROUTE_RECOMMENDATION_MISMATCH",
    "ERR_STAGE8P_LINEAGE_MISMATCH",
    "ERR_MISSING_ACTION_FAMILY",
    "ERR_INVALID_ACTION_FAMILY",
    "ERR_ACTION_ROUTE_INCOMPATIBLE",
    "ERR_TOO_MANY_ACTIONS",
    "ERR_COMPOSITE_ACTION",
    "ERR_MISSING_ACTION_PARAMS",
    "ERR_INVALID_ACTION_PARAMS",
    "ERR_EXECUTION_REQUEST_NOT_FOUND",
    "ERR_EXECUTION_REQUEST_NOT_APPROVED",
    "ERR_EXECUTION_APPROVAL_NOT_FOUND",
    "ERR_APPROVAL_REQUEST_MISMATCH",
    "ERR_APPROVAL_CONTRACT_MISMATCH",
    "ERR_APPROVAL_ACTION_MISMATCH",
    "ERR_APPROVAL_REUSE_REJECTED",
    "ERR_MISSING_REASON",
    "ERR_ELIGIBILITY_NOT_READY",
    "ERR_PRE_EXECUTION_FAILED",
    "ERR_TARGET_MUTATION_FAILED",
    "ERR_TARGET_RECORD_MISSING",
    "ERR_TARGET_RECORD_MISMATCH",
    "ERR_PARTIAL_EFFECT",
    "ERR_CONFLICTING_EXECUTION",
    "ERR_UNSAFE_TEXT",
    "ERR_INVALID_ID",
    "ERR_INVALID_DATE",
    "_bounded",
    "_require_member",
    "_require_operator_id",
    "_require_nonempty",
    "_require_safe_id",
    "_require_date",
    "_require_free_text",
    "_require_issue_summary",
    "_immutable_hash",
    "ResolutionActionSelection",
    "ResolutionExecutionRequest",
    "ResolutionExecutionEligibilityResult",
    "ResolutionExecutionApproval",
    "ManualFollowUpRecord",
    "ResolutionActionOutcomeEvidence",
    "ResolutionActionEvent",
    "action_target_domain",
    "execution_request_id",
    "execution_contract_hash",
    "execution_approval_id",
    "outcome_evidence_id",
    "follow_up_record_id",
    "resolution_action_event_id",
    "route_content_hash_for",
    "load_stage8q_route",
    "ALLOWED_RECOMMENDED_ROUTES",
]
