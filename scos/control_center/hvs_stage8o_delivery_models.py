"""SCOS <-> Hermes Video Studio (HVS) — Stage 8O delivery package, authorization, and record.

Stage 8O is an OPERATOR-CONTROLLED delivery-package + manual-delivery-authorization
+ actual-delivery-recording workflow for a previously certified Stage 8N render
artifact. It explicitly enforces THREE SEPARATE BOUNDARIES:

    A. DELIVERY PACKAGE CREATION   (prepare / materialize / verify -> PACKAGE_READY)
    B. MANUAL DELIVERY AUTHORIZATION (explicit operator decision, never transport)
    C. ACTUAL MANUAL DELIVERY RECORD (explicit human-performed-delivery confirmation)

None of these collapse into the others. Creating a package never authorizes
delivery; authorizing delivery never performs delivery; recording a delivery
never implies customer receipt or acceptance. SCOS performs NO transport: no
upload, publish, email, message, webhook, browser, SFTP, or customer contact.

The implementation binds to certified Stage 8N render-completion evidence via
the genuine artifact path and a recomputed SHA-256 (never trusts the runtime
record alone). It reuses the repository's deterministic identity helpers
(``canonical_json`` / ``stable_id``), the safe path discipline
(``_assert_not_network_or_device`` / ``_safe_basename``), and the streamed
SHA-256 copy helper (``_sha256_stream``). ``automation_allowed`` is always
``False``. No clock, no random, no uuid, no network, no subprocess.

Local-first, deterministic, stdlib-only.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from .hvs_asset_materialization import (
    _assert_not_network_or_device,
    _safe_basename,
    _sha256_stream,
)
from .hvs_commercial_proposal_models import _safe_text, canonical_json, stable_id


# --- schema / identity -------------------------------------------------------
STAGE8O_SCHEMA_VERSION = "scos-hvs.stage8o.delivery.v1/1.0.0"
PACKAGE_CONTRACT_SCHEMA_VERSION = "scos-hvs.stage8o.package-contract.v1/1.0.0"
PACKAGE_MANIFEST_SCHEMA_VERSION = "scos-hvs.stage8o.package-manifest.v1/1.0.0"
AUTH_REQUEST_SCHEMA_VERSION = "scos-hvs.stage8o.auth-request.v1/1.0.0"
AUTH_DECISION_SCHEMA_VERSION = "scos-hvs.stage8o.auth-decision.v1/1.0.0"
DELIVERY_RECORD_SCHEMA_VERSION = "scos-hvs.stage8o.delivery-record.v1/1.0.0"
DELIVERY_EVENT_SCHEMA_VERSION = "scos-hvs.stage8o.delivery-event.v1/1.0.0"

# Deterministic runtime root under the gitignored scos/work tree.
DEFAULT_DELIVERY_PACKAGES_RELATIVE = "scos/work/hvs_stage8o_delivery_packages"

# Package preparation states.
PKG_DRAFT = "PACKAGE_DRAFT"
PKG_PREPARED = "PACKAGE_PREPARED"
PKG_MATERIALIZING = "PACKAGE_MATERIALIZING"
PKG_MATERIALIZED = "PACKAGE_MATERIALIZED"
PKG_VERIFYING = "PACKAGE_VERIFYING"
PKG_READY = "PACKAGE_READY"
PKG_CONFLICTED = "PACKAGE_CONFLICTED"
PKG_FAILED = "PACKAGE_FAILED"
PKG_CANCELLED = "PACKAGE_CANCELLED"
ALLOWED_PACKAGE_STATUSES = (
    PKG_DRAFT,
    PKG_PREPARED,
    PKG_MATERIALIZING,
    PKG_MATERIALIZED,
    PKG_VERIFYING,
    PKG_READY,
    PKG_CONFLICTED,
    PKG_FAILED,
    PKG_CANCELLED,
)
# States after which a package is considered "ready" for authorization.
PACKAGE_READY_STATES = (PKG_READY,)

# Authorization states.
AUTH_PENDING = "AUTHORIZATION_PENDING"
AUTH_APPROVED = "APPROVED_FOR_MANUAL_DELIVERY"
AUTH_REJECTED = "REJECTED_FOR_MANUAL_DELIVERY"
AUTH_CANCELLED = "AUTHORIZATION_CANCELLED"
AUTH_EXPIRED = "AUTHORIZATION_EXPIRED"
ALLOWED_AUTH_STATUSES = (
    AUTH_PENDING,
    AUTH_APPROVED,
    AUTH_REJECTED,
    AUTH_CANCELLED,
    AUTH_EXPIRED,
)

# Actual delivery-record states.
DEL_NOT_DELIVERED = "NOT_DELIVERED"
DEL_DELIVERED_MANUALLY = "DELIVERED_MANUALLY"
DEL_RECORD_REJECTED = "DELIVERY_RECORD_REJECTED"
DEL_RECORD_CONFLICTED = "DELIVERY_RECORD_CONFLICTED"
ALLOWED_DELIVERY_STATUSES = (
    DEL_NOT_DELIVERED,
    DEL_DELIVERED_MANUALLY,
    DEL_RECORD_REJECTED,
    DEL_RECORD_CONFLICTED,
)

# Manual delivery methods (describe a future HUMAN action only; never invoked).
METHOD_IN_PERSON = "IN_PERSON"
METHOD_REMOVABLE_MEDIA = "REMOVABLE_MEDIA"
METHOD_MANUAL_EMAIL = "MANUAL_EMAIL"
METHOD_MANUAL_CLOUD_SHARE = "MANUAL_CLOUD_SHARE"
METHOD_MANUAL_MESSAGING_PLATFORM = "MANUAL_MESSAGING_PLATFORM"
METHOD_MANUAL_CUSTOMER_PORTAL = "MANUAL_CUSTOMER_PORTAL"
METHOD_OTHER_MANUAL = "OTHER_MANUAL"
ALLOWED_DELIVERY_METHODS = (
    METHOD_IN_PERSON,
    METHOD_REMOVABLE_MEDIA,
    METHOD_MANUAL_EMAIL,
    METHOD_MANUAL_CLOUD_SHARE,
    METHOD_MANUAL_MESSAGING_PLATFORM,
    METHOD_MANUAL_CUSTOMER_PORTAL,
    METHOD_OTHER_MANUAL,
)

# Stable audit event types.
EVT_PACKAGE_PREPARED = "PACKAGE_PREPARED"
EVT_PACKAGE_MATERIALIZATION_STARTED = "PACKAGE_MATERIALIZATION_STARTED"
EVT_PACKAGE_MATERIALIZED = "PACKAGE_MATERIALIZED"
EVT_PACKAGE_REUSED = "PACKAGE_REUSED"
EVT_PACKAGE_VERIFIED = "PACKAGE_VERIFIED"
EVT_PACKAGE_INTEGRITY_FAILED = "PACKAGE_INTEGRITY_FAILED"
EVT_PACKAGE_CONFLICTED = "PACKAGE_CONFLICTED"
EVT_PACKAGE_CANCELLED = "PACKAGE_CANCELLED"
EVT_AUTHORIZATION_REQUESTED = "AUTHORIZATION_REQUESTED"
EVT_AUTHORIZATION_APPROVED = "AUTHORIZATION_APPROVED"
EVT_AUTHORIZATION_REJECTED = "AUTHORIZATION_REJECTED"
EVT_AUTHORIZATION_CANCELLED = "AUTHORIZATION_CANCELLED"
EVT_AUTHORIZATION_EXPIRED = "AUTHORIZATION_EXPIRED"
EVT_DELIVERY_RECORDED = "DELIVERY_RECORDED"
EVT_DELIVERY_RECORD_REPLAYED = "DELIVERY_RECORD_REPLAYED"
EVT_DELIVERY_RECORD_REJECTED = "DELIVERY_RECORD_REJECTED"
EVT_DELIVERY_RECORD_CONFLICTED = "DELIVERY_RECORD_CONFLICTED"
ALLOWED_DELIVERY_EVENT_TYPES = (
    EVT_PACKAGE_PREPARED,
    EVT_PACKAGE_MATERIALIZATION_STARTED,
    EVT_PACKAGE_MATERIALIZED,
    EVT_PACKAGE_REUSED,
    EVT_PACKAGE_VERIFIED,
    EVT_PACKAGE_INTEGRITY_FAILED,
    EVT_PACKAGE_CONFLICTED,
    EVT_PACKAGE_CANCELLED,
    EVT_AUTHORIZATION_REQUESTED,
    EVT_AUTHORIZATION_APPROVED,
    EVT_AUTHORIZATION_REJECTED,
    EVT_AUTHORIZATION_CANCELLED,
    EVT_AUTHORIZATION_EXPIRED,
    EVT_DELIVERY_RECORDED,
    EVT_DELIVERY_RECORD_REPLAYED,
    EVT_DELIVERY_RECORD_REJECTED,
    EVT_DELIVERY_RECORD_CONFLICTED,
)


# --- error codes -------------------------------------------------------------
ERR_MISSING_OPERATOR_ID = "missing_operator_id"
ERR_MISSING_RECIPIENT = "missing_recipient"
ERR_UNSAFE_RECIPIENT = "unsafe_recipient_reference"
ERR_MISSING_METHOD = "missing_method"
ERR_INVALID_METHOD = "invalid_delivery_method"
ERR_MISSING_REASON = "missing_reason"
ERR_MISSING_CONFIRMATION = "missing_human_delivery_confirmation"
ERR_UNSAFE_PATH = "unsafe_path"
ERR_ARTIFACT_MISSING = "artifact_missing"
ERR_ARTIFACT_NOT_REGULAR = "artifact_not_regular"
ERR_ARTIFACT_ZERO_BYTE = "artifact_zero_byte"
ERR_ARTIFACT_SHA_MISMATCH = "artifact_sha_mismatch"
ERR_ARTIFACT_SYMLINK = "artifact_is_symlink"
ERR_COMPLETION_NOT_FOUND = "completion_evidence_not_found"
ERR_COMPLETION_NOT_COMPLETE = "render_not_completed"
ERR_COMPLETION_NOT_VERIFIED = "artifact_not_verified"
ERR_COMPLETION_DELIVERY_AUTHORIZED = "completion_delivery_already_authorized"
ERR_COMPLETION_PUBLISH_AUTHORIZED = "completion_publishing_already_authorized"
ERR_COMPLETION_AUTOMATION = "completion_automation_not_false"
ERR_PROJECT_MISMATCH = "project_id_mismatch"
ERR_PACKAGE_CONFLICT = "package_conflict"
ERR_PACKAGE_NOT_FOUND = "package_not_found"
ERR_PACKAGE_NOT_READY = "package_not_ready"
ERR_PACKAGE_NOT_MATERIALIZED = "package_not_materialized"
ERR_NOT_MATERIALIZED = "not_materialized"
ERR_AUTH_NOT_FOUND = "authorization_request_not_found"
ERR_AUTH_NOT_PENDING = "authorization_not_pending"
ERR_AUTH_ALREADY_DECIDED = "authorization_already_decided"
ERR_AUTH_REJECTED = "authorization_rejected"
ERR_AUTH_CANCELLED = "authorization_cancelled"
ERR_AUTH_EXPIRED = "authorization_expired"
ERR_DELIVERY_CONFLICT = "delivery_record_conflict"
ERR_DELIVERY_NOT_AUTHORIZED = "delivery_not_authorized"
ERR_DELIVERY_REPLAYED = "delivery_record_replayed"
ERR_UNEXPECTED_FILES = "unexpected_package_files"


def _require_member(value: str, allowed: tuple[str, ...], code: str, detail: str) -> None:
    if value not in allowed:
        raise ValueError(f"{code}: {detail}")


def _immutable_text(field_name: str, value: Any, *, required: bool = True, max_len: int = 512) -> str:
    if value is None or value == "":
        if required:
            raise ValueError(f"{field_name} is required")
        return ""
    if not isinstance(value, str) or len(value) > max_len:
        raise ValueError(f"{field_name} must be a bounded string")
    if "\x00" in value or "\r" in value or "\n" in value or "\\" in value or ".." in value:
        raise ValueError(f"{field_name} contains unsafe text")
    return value


def _immutable_text_optional(field_name: str, value: Any, *, max_len: int = 512) -> str:
    return _immutable_text(field_name, value, required=False, max_len=max_len)


def _immutable_hash(field_name: str, value: Any) -> str:
    value = _immutable_text(field_name, value, required=True, max_len=128)
    if len(value) != 64:
        raise ValueError(f"{field_name} must be a 64-char SHA-256 hex digest")
    return value.lower()


# ---------------------------------------------------------------------------
# Stage 8N render-evidence binding (read-only provenance)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Stage8ORenderEvidenceBinding:
    """Immutable read-only provenance back to the exact Stage 8N completion evidence."""

    project_id: str
    completion_evidence_id: str
    render_request_id: str
    render_approval_id: str
    render_dispatch_id: str
    hvs_project_id: str
    artifact_id: str
    artifact_sha256: str
    source_artifact_size: int
    completion_status: str
    artifact_verified: bool
    delivery_authorized: bool
    publishing_authorized: bool
    automation_allowed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "completion_evidence_id": self.completion_evidence_id,
            "render_request_id": self.render_request_id,
            "render_approval_id": self.render_approval_id,
            "render_dispatch_id": self.render_dispatch_id,
            "hvs_project_id": self.hvs_project_id,
            "artifact_id": self.artifact_id,
            "artifact_sha256": self.artifact_sha256,
            "source_artifact_size": self.source_artifact_size,
            "completion_status": self.completion_status,
            "artifact_verified": self.artifact_verified,
            "delivery_authorized": self.delivery_authorized,
            "publishing_authorized": self.publishing_authorized,
            "automation_allowed": self.automation_allowed,
        }


# ---------------------------------------------------------------------------
# Delivery package contract (Boundary A)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DeliveryPackageContract:
    """Immutable delivery-package contract. Package creation NEVER authorizes delivery."""

    schema_version: str
    delivery_package_id: str
    package_contract_hash: str
    project_id: str
    hvs_project_id: str
    correlation_id: str
    completion_evidence_id: str
    render_request_id: str
    render_approval_id: str
    artifact_id: str
    artifact_sha256: str
    source_artifact_size: int
    source_artifact_display_path: str
    artifact_filename: str
    artifact_media_type: str
    package_revision: int
    package_status: str
    package_runtime_root: str
    package_manifest_filename: str
    package_content_hash: str
    # Boundary truth: every package starts with delivery/auth flags false.
    manual_delivery_required: bool = True
    delivery_authorized: bool = False
    delivery_performed: bool = False
    customer_receipt_confirmed: bool = False
    customer_acceptance_recorded: bool = False
    publishing_performed: bool = False
    upload_performed: bool = False
    external_delivery_executed_by_scos: bool = False
    automation_allowed: bool = False
    # Informational, excluded from deterministic identity.
    recorded_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "delivery_package_id": self.delivery_package_id,
            "package_contract_hash": self.package_contract_hash,
            "project_id": self.project_id,
            "hvs_project_id": self.hvs_project_id,
            "correlation_id": self.correlation_id,
            "completion_evidence_id": self.completion_evidence_id,
            "render_request_id": self.render_request_id,
            "render_approval_id": self.render_approval_id,
            "artifact_id": self.artifact_id,
            "artifact_sha256": self.artifact_sha256,
            "source_artifact_size": self.source_artifact_size,
            "source_artifact_display_path": self.source_artifact_display_path,
            "artifact_filename": self.artifact_filename,
            "artifact_media_type": self.artifact_media_type,
            "package_revision": self.package_revision,
            "package_status": self.package_status,
            "package_runtime_root": self.package_runtime_root,
            "package_manifest_filename": self.package_manifest_filename,
            "package_content_hash": self.package_content_hash,
            "manual_delivery_required": self.manual_delivery_required,
            "delivery_authorized": self.delivery_authorized,
            "delivery_performed": self.delivery_performed,
            "customer_receipt_confirmed": self.customer_receipt_confirmed,
            "customer_acceptance_recorded": self.customer_acceptance_recorded,
            "publishing_performed": self.publishing_performed,
            "upload_performed": self.upload_performed,
            "external_delivery_executed_by_scos": self.external_delivery_executed_by_scos,
            "automation_allowed": self.automation_allowed,
            "recorded_at": self.recorded_at,
        }


# ---------------------------------------------------------------------------
# Package manifest (materialized file)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DeliveryPackageManifest:
    """Deterministic manifest materialized inside the package directory."""

    schema_version: str
    package_id: str
    package_contract_hash: str
    source_artifact_id: str
    source_artifact_sha256: str
    packaged_artifact_filename: str
    packaged_artifact_sha256: str
    packaged_artifact_size: int
    package_manifest_hash: str
    content_file_list: tuple[str, ...]
    stage8n_completion_evidence_id: str
    created_by_system: str
    manual_delivery_warning: str
    no_transport_statement: str
    no_customer_receipt_statement: str
    automation_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "package_id": self.package_id,
            "package_contract_hash": self.package_contract_hash,
            "source_artifact_id": self.source_artifact_id,
            "source_artifact_sha256": self.source_artifact_sha256,
            "packaged_artifact_filename": self.packaged_artifact_filename,
            "packaged_artifact_sha256": self.packaged_artifact_sha256,
            "packaged_artifact_size": self.packaged_artifact_size,
            "package_manifest_hash": self.package_manifest_hash,
            "content_file_list": list(self.content_file_list),
            "stage8n_completion_evidence_id": self.stage8n_completion_evidence_id,
            "created_by_system": self.created_by_system,
            "manual_delivery_warning": self.manual_delivery_warning,
            "no_transport_statement": self.no_transport_statement,
            "no_customer_receipt_statement": self.no_customer_receipt_statement,
            "automation_allowed": self.automation_allowed,
        }


# ---------------------------------------------------------------------------
# Manual delivery authorization request (Boundary B)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ManualDeliveryAuthorizationRequest:
    """Explicit operator-facing authorization request. Never performs delivery."""

    schema_version: str
    authorization_request_id: str
    delivery_package_id: str
    package_contract_hash: str
    package_content_hash: str
    package_verification_id: str
    artifact_sha256: str
    project_id: str
    safe_recipient_reference: str
    allowed_manual_delivery_method: str
    authorization_status: str
    requested_operator_id: str
    authorization_validity: str
    scope_statement: str
    automation_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "authorization_request_id": self.authorization_request_id,
            "delivery_package_id": self.delivery_package_id,
            "package_contract_hash": self.package_contract_hash,
            "package_content_hash": self.package_content_hash,
            "package_verification_id": self.package_verification_id,
            "artifact_sha256": self.artifact_sha256,
            "project_id": self.project_id,
            "safe_recipient_reference": self.safe_recipient_reference,
            "allowed_manual_delivery_method": self.allowed_manual_delivery_method,
            "authorization_status": self.authorization_status,
            "requested_operator_id": self.requested_operator_id,
            "authorization_validity": self.authorization_validity,
            "scope_statement": self.scope_statement,
            "automation_allowed": self.automation_allowed,
        }


# ---------------------------------------------------------------------------
# Authorization decision (approve / reject)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ManualDeliveryAuthorizationDecision:
    """Explicit approve/reject decision. Binds exact package hash + artifact hash."""

    schema_version: str
    authorization_decision_id: str
    authorization_request_id: str
    delivery_package_id: str
    package_content_hash: str
    decision: str
    operator_id: str
    rejection_reason: str | None
    approval_note: str | None
    decision_recorded_at: str
    external_delivery_executed_by_scos: bool = False
    automation_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "authorization_decision_id": self.authorization_decision_id,
            "authorization_request_id": self.authorization_request_id,
            "delivery_package_id": self.delivery_package_id,
            "package_content_hash": self.package_content_hash,
            "decision": self.decision,
            "operator_id": self.operator_id,
            "rejection_reason": self.rejection_reason,
            "approval_note": self.approval_note,
            "decision_recorded_at": self.decision_recorded_at,
            "external_delivery_executed_by_scos": self.external_delivery_executed_by_scos,
            "automation_allowed": self.automation_allowed,
        }


# ---------------------------------------------------------------------------
# Actual manual delivery record (Boundary C)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ActualManualDeliveryRecord:
    """Records that an operator asserts a human performed delivery outside SCOS.

    Created ONLY after valid authorization AND explicit human-delivery
    confirmation. Does NOT imply customer receipt or acceptance.
    """

    schema_version: str
    manual_delivery_record_id: str
    authorization_request_id: str
    authorization_decision_id: str
    delivery_package_id: str
    package_content_hash: str
    completion_evidence_id: str
    artifact_sha256: str
    project_id: str
    safe_recipient_reference: str
    manual_delivery_method: str
    operator_id: str
    human_delivery_confirmation: bool
    delivery_recorded_at: str
    external_evidence_reference: str
    operator_note: str
    delivery_status: str
    manual_delivery_performed: bool
    external_delivery_executed_by_scos: bool = False
    customer_receipt_confirmed: bool = False
    customer_acceptance_recorded: bool = False
    publishing_performed: bool = False
    invoice_state_changed: bool = False
    payment_state_changed: bool = False
    automation_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "manual_delivery_record_id": self.manual_delivery_record_id,
            "authorization_request_id": self.authorization_request_id,
            "authorization_decision_id": self.authorization_decision_id,
            "delivery_package_id": self.delivery_package_id,
            "package_content_hash": self.package_content_hash,
            "completion_evidence_id": self.completion_evidence_id,
            "artifact_sha256": self.artifact_sha256,
            "project_id": self.project_id,
            "safe_recipient_reference": self.safe_recipient_reference,
            "manual_delivery_method": self.manual_delivery_method,
            "operator_id": self.operator_id,
            "human_delivery_confirmation": self.human_delivery_confirmation,
            "delivery_recorded_at": self.delivery_recorded_at,
            "external_evidence_reference": self.external_evidence_reference,
            "operator_note": self.operator_note,
            "delivery_status": self.delivery_status,
            "manual_delivery_performed": self.manual_delivery_performed,
            "external_delivery_executed_by_scos": self.external_delivery_executed_by_scos,
            "customer_receipt_confirmed": self.customer_receipt_confirmed,
            "customer_acceptance_recorded": self.customer_acceptance_recorded,
            "publishing_performed": self.publishing_performed,
            "invoice_state_changed": self.invoice_state_changed,
            "payment_state_changed": self.payment_state_changed,
            "automation_allowed": self.automation_allowed,
        }


# ---------------------------------------------------------------------------
# Append-only delivery event
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Stage8ODeliveryEvent:
    """One append-only, deterministic lifecycle event."""

    schema_version: str
    event_id: str
    event_type: str
    package_id: str | None
    package_content_hash: str | None
    authorization_request_id: str | None
    authorization_decision_id: str | None
    delivery_record_id: str | None
    completion_evidence_id: str
    artifact_sha256: str
    operator_id: str
    resulting_status: str
    reason: str
    recorded_at: str
    automation_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "package_id": self.package_id,
            "package_content_hash": self.package_content_hash,
            "authorization_request_id": self.authorization_request_id,
            "authorization_decision_id": self.authorization_decision_id,
            "delivery_record_id": self.delivery_record_id,
            "completion_evidence_id": self.completion_evidence_id,
            "artifact_sha256": self.artifact_sha256,
            "operator_id": self.operator_id,
            "resulting_status": self.resulting_status,
            "reason": self.reason,
            "recorded_at": self.recorded_at,
            "automation_allowed": self.automation_allowed,
        }


# ---------------------------------------------------------------------------
# Deterministic identity helpers (no volatile inputs)
# ---------------------------------------------------------------------------
def delivery_package_id(
    *,
    project_id: str,
    completion_evidence_id: str,
    artifact_id: str,
    artifact_sha256: str,
    artifact_filename: str,
    contract_version: str,
    package_revision: int = 1,
) -> str:
    return stable_id(
        "scos-hvs-stage8o-package",
        {
            "project_id": project_id,
            "completion_evidence_id": completion_evidence_id,
            "artifact_id": artifact_id,
            "artifact_sha256": artifact_sha256.lower(),
            "artifact_filename": artifact_filename,
            "contract_version": contract_version,
            "package_revision": package_revision,
        },
    )


def package_contract_hash(*, contract: dict[str, Any]) -> str:
    """Deterministic contract hash over immutable semantic fields only."""
    return stable_id(
        "scos-hvs-stage8o-pkg-contract",
        {
            "package": canonical_json(
                {
                    k: contract.get(k)
                    for k in (
                        "delivery_package_id",
                        "project_id",
                        "hvs_project_id",
                        "correlation_id",
                        "completion_evidence_id",
                        "render_request_id",
                        "render_approval_id",
                        "artifact_id",
                        "artifact_sha256",
                        "source_artifact_size",
                        "source_artifact_display_path",
                        "artifact_filename",
                        "artifact_media_type",
                        "package_revision",
                        "package_runtime_root",
                        "package_manifest_filename",
                    )
                }
            )
        },
    )


def package_content_hash(
    *,
    package_id: str,
    manifest_hash: str,
    packaged_artifact_sha256: str,
    packaged_artifact_size: int,
    content_file_list: tuple[str, ...],
) -> str:
    return stable_id(
        "scos-hvs-stage8o-pkg-content",
        {
            "package_id": package_id,
            "manifest_hash": manifest_hash,
            "packaged_artifact_sha256": packaged_artifact_sha256.lower(),
            "packaged_artifact_size": packaged_artifact_size,
            "content_file_list": sorted(content_file_list),
        },
    )


def package_manifest_hash(*, manifest: dict[str, Any]) -> str:
    return stable_id(
        "scos-hvs-stage8o-manifest",
        {
            "manifest": canonical_json(
                {
                    k: manifest.get(k)
                    for k in (
                        "package_id",
                        "package_contract_hash",
                        "source_artifact_id",
                        "source_artifact_sha256",
                        "packaged_artifact_filename",
                        "packaged_artifact_sha256",
                        "packaged_artifact_size",
                        "content_file_list",
                        "stage8n_completion_evidence_id",
                    )
                }
            )
        },
    )


def authorization_request_id(
    *,
    package_id: str,
    package_contract_hash: str,
    package_content_hash: str,
    artifact_sha256: str,
    recipient_reference: str,
    method: str,
) -> str:
    return stable_id(
        "scos-hvs-stage8o-auth-req",
        {
            "package_id": package_id,
            "package_contract_hash": package_contract_hash,
            "package_content_hash": package_content_hash,
            "artifact_sha256": artifact_sha256.lower(),
            "safe_recipient_reference": recipient_reference,
            "allowed_manual_delivery_method": method,
        },
    )


def authorization_decision_id(
    *,
    authorization_request_id: str,
    decision: str,
    operator_id: str,
    rejection_reason: str | None,
) -> str:
    return stable_id(
        "scos-hvs-stage8o-auth-dec",
        {
            "authorization_request_id": authorization_request_id,
            "decision": decision,
            "operator_id": operator_id,
            "rejection_reason": rejection_reason,
        },
    )


def actual_delivery_record_id(
    *,
    authorization_decision_id: str,
    package_id: str,
    package_content_hash: str,
    artifact_sha256: str,
    recipient_reference: str,
    method: str,
    operator_id: str,
    human_confirmation: bool,
    external_evidence_reference: str,
) -> str:
    return stable_id(
        "scos-hvs-stage8o-delivery",
        {
            "authorization_decision_id": authorization_decision_id,
            "package_id": package_id,
            "package_content_hash": package_content_hash,
            "artifact_sha256": artifact_sha256.lower(),
            "safe_recipient_reference": recipient_reference,
            "manual_delivery_method": method,
            "operator_id": operator_id,
            "human_delivery_confirmation": bool(human_confirmation),
            "external_evidence_reference": external_evidence_reference,
        },
    )


def delivery_event_id(*, event_type: str, subject_id: str, record: dict[str, Any]) -> str:
    return stable_id(
        "scos-hvs-stage8o-event",
        {"event_type": event_type, "subject_id": subject_id, "record": record},
    )


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_recipient_reference(value: str) -> str:
    """Reject secret-like, command-like, or URL-like recipient references."""
    value = _immutable_text("safe_recipient_reference", value, required=True, max_len=256)
    lowered = value.lower()
    if "://" in lowered:
        raise ValueError("recipient reference must not be a URL")
    for token in ("password", "secret", "token=", "api_key", "apikey", "credential"):
        if token in lowered:
            raise ValueError("recipient reference must not contain secret-like text")
    if any(c in value for c in ("|", ";", "&", "$", "(", ")", "<", ">")):
        raise ValueError("recipient reference must not contain command-like characters")
    return value


def _safe_external_evidence_reference(value: str) -> str:
    if value is None or value == "":
        return ""
    value = _immutable_text_optional("external_evidence_reference", value, max_len=256)
    lowered = value.lower()
    if "://" in lowered and any(p in lowered for p in ("sig", "token", "key", "secret")):
        raise ValueError("external evidence reference must not contain signed-credential URLs")
    for token in ("password", "secret", "token=", "api_key", "apikey", "credential"):
        if token in lowered:
            raise ValueError("external evidence reference must not contain secret-like text")
    if any(c in value for c in ("|", ";", "&", "$", "<", ">")):
        raise ValueError("external evidence reference must not contain command-like characters")
    return value


def _safe_other_manual_description(value: str) -> str:
    value = _immutable_text("other_manual_description", value, required=True, max_len=256)
    for token in ("password", "secret", "token=", "api_key", "apikey", "credential"):
        if token in value.lower():
            raise ValueError("other_manual description must not contain secret-like text")
    if any(c in value for c in ("|", ";", "&", "$", "(", ")", "<", ">")):
        raise ValueError("other_manual description must not contain command-like characters")
    return value


def resolve_artifact_source(artifact_path: str) -> Any:
    """Validate the approved source artifact is a safe, local, regular file.

    Rejects UNC/network/device/URL paths, null bytes, symlinks, and escapes.
    Returns the resolved ``Path`` (the caller must still check size + hash).
    """
    from pathlib import Path

    _assert_not_network_or_device(artifact_path, "stage8o-artifact")
    if "\x00" in artifact_path:
        raise ValueError("null byte in artifact path")
    resolved = Path(artifact_path).resolve()
    if resolved.is_symlink():
        raise ValueError("artifact is a symlink (escape risk)")
    if not resolved.is_file():
        raise ValueError("artifact is not a regular file")
    return resolved


# Re-export reused helpers for the service/store modules (single import surface).
__all__ = [
    "STAGE8O_SCHEMA_VERSION",
    "PACKAGE_CONTRACT_SCHEMA_VERSION",
    "PACKAGE_MANIFEST_SCHEMA_VERSION",
    "AUTH_REQUEST_SCHEMA_VERSION",
    "AUTH_DECISION_SCHEMA_VERSION",
    "DELIVERY_RECORD_SCHEMA_VERSION",
    "DELIVERY_EVENT_SCHEMA_VERSION",
    "DEFAULT_DELIVERY_PACKAGES_RELATIVE",
    "PKG_DRAFT",
    "PKG_PREPARED",
    "PKG_MATERIALIZING",
    "PKG_MATERIALIZED",
    "PKG_VERIFYING",
    "PKG_READY",
    "PKG_CONFLICTED",
    "PKG_FAILED",
    "PKG_CANCELLED",
    "ALLOWED_PACKAGE_STATUSES",
    "PACKAGE_READY_STATES",
    "AUTH_PENDING",
    "AUTH_APPROVED",
    "AUTH_REJECTED",
    "AUTH_CANCELLED",
    "AUTH_EXPIRED",
    "ALLOWED_AUTH_STATUSES",
    "DEL_NOT_DELIVERED",
    "DEL_DELIVERED_MANUALLY",
    "DEL_RECORD_REJECTED",
    "DEL_RECORD_CONFLICTED",
    "ALLOWED_DELIVERY_STATUSES",
    "METHOD_IN_PERSON",
    "METHOD_REMOVABLE_MEDIA",
    "METHOD_MANUAL_EMAIL",
    "METHOD_MANUAL_CLOUD_SHARE",
    "METHOD_MANUAL_MESSAGING_PLATFORM",
    "METHOD_MANUAL_CUSTOMER_PORTAL",
    "METHOD_OTHER_MANUAL",
    "ALLOWED_DELIVERY_METHODS",
    "EVT_PACKAGE_PREPARED",
    "EVT_PACKAGE_MATERIALIZATION_STARTED",
    "EVT_PACKAGE_MATERIALIZED",
    "EVT_PACKAGE_REUSED",
    "EVT_PACKAGE_VERIFIED",
    "EVT_PACKAGE_INTEGRITY_FAILED",
    "EVT_PACKAGE_CONFLICTED",
    "EVT_PACKAGE_CANCELLED",
    "EVT_AUTHORIZATION_REQUESTED",
    "EVT_AUTHORIZATION_APPROVED",
    "EVT_AUTHORIZATION_REJECTED",
    "EVT_AUTHORIZATION_CANCELLED",
    "EVT_AUTHORIZATION_EXPIRED",
    "EVT_DELIVERY_RECORDED",
    "EVT_DELIVERY_RECORD_REPLAYED",
    "EVT_DELIVERY_RECORD_REJECTED",
    "EVT_DELIVERY_RECORD_CONFLICTED",
    "ALLOWED_DELIVERY_EVENT_TYPES",
    "ERR_MISSING_OPERATOR_ID",
    "ERR_MISSING_RECIPIENT",
    "ERR_UNSAFE_RECIPIENT",
    "ERR_MISSING_METHOD",
    "ERR_INVALID_METHOD",
    "ERR_MISSING_REASON",
    "ERR_MISSING_CONFIRMATION",
    "ERR_UNSAFE_PATH",
    "ERR_ARTIFACT_MISSING",
    "ERR_ARTIFACT_NOT_REGULAR",
    "ERR_ARTIFACT_ZERO_BYTE",
    "ERR_ARTIFACT_SHA_MISMATCH",
    "ERR_ARTIFACT_SYMLINK",
    "ERR_COMPLETION_NOT_FOUND",
    "ERR_COMPLETION_NOT_COMPLETE",
    "ERR_COMPLETION_NOT_VERIFIED",
    "ERR_COMPLETION_DELIVERY_AUTHORIZED",
    "ERR_COMPLETION_PUBLISH_AUTHORIZED",
    "ERR_COMPLETION_AUTOMATION",
    "ERR_PROJECT_MISMATCH",
    "ERR_PACKAGE_CONFLICT",
    "ERR_PACKAGE_NOT_FOUND",
    "ERR_PACKAGE_NOT_READY",
    "ERR_PACKAGE_NOT_MATERIALIZED",
    "ERR_NOT_MATERIALIZED",
    "ERR_AUTH_NOT_FOUND",
    "ERR_AUTH_NOT_PENDING",
    "ERR_AUTH_ALREADY_DECIDED",
    "ERR_AUTH_REJECTED",
    "ERR_AUTH_CANCELLED",
    "ERR_AUTH_EXPIRED",
    "ERR_DELIVERY_CONFLICT",
    "ERR_DELIVERY_NOT_AUTHORIZED",
    "ERR_DELIVERY_REPLAYED",
    "ERR_UNEXPECTED_FILES",
    "Stage8ORenderEvidenceBinding",
    "DeliveryPackageContract",
    "DeliveryPackageManifest",
    "ManualDeliveryAuthorizationRequest",
    "ManualDeliveryAuthorizationDecision",
    "ActualManualDeliveryRecord",
    "Stage8ODeliveryEvent",
    "delivery_package_id",
    "package_contract_hash",
    "package_content_hash",
    "package_manifest_hash",
    "authorization_request_id",
    "authorization_decision_id",
    "actual_delivery_record_id",
    "delivery_event_id",
    "sha256_bytes",
    "resolve_artifact_source",
    "_safe_recipient_reference",
    "_safe_external_evidence_reference",
    "_safe_other_manual_description",
    "_assert_not_network_or_device",
    "_safe_basename",
    "_sha256_stream",
    "canonical_json",
    "stable_id",
]
