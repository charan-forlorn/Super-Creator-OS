"""SCOS <-> Hermes Video Studio (HVS) — Stage 6 local delivery package models.

Deterministic, operator-controlled, LOCAL-ONLY delivery-package preparation
and append-only recording of human-performed manual delivery. Stage 6 NEVER
uploads, publishes, emails, messages, renders, mutates HVS, or performs any
external delivery. It prepares a safe local package directory and lets the
operator record (after the fact) that a human delivered the artifact through
an out-of-system channel.

Boundary (consistent with Stage 1-5 cross-project architecture):

    Verified HVS evidence
      -> SCOS decision packet
      -> Stage 5 operator approval (APPROVED_FOR_MANUAL_DELIVERY)
      -> Stage 6 local delivery manifest
      -> optional explicit local package materialization (operator-authorized)
      -> human performs external delivery
      -> operator records manual delivery result
      -> append-only audit evidence

Hard rules enforced here:
* Only APPROVED_FOR_MANUAL_DELIVERY may create a package.
* Preparation validates the full contract and builds a deterministic manifest
  but does NOT copy media.
* Package ids and delivery-record ids are content-derived (no clock/random/
  uuid/pid/tempdir/username/elapsed-time/mutable-destination).
* automation_allowed is always false; manual_delivery_required stays true
  until a valid final manual delivery record exists.
* No network, no subprocess, no shell, no upload/publish/email/message.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid, no
network, no subprocess.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

# --- schema / identity -------------------------------------------------------
LOCAL_DELIVERY_PACKAGE_SCHEMA_VERSION = "scos-hvs.local-delivery-package.v1/1.0.0"
MANUAL_DELIVERY_RECORD_SCHEMA_VERSION = "scos-hvs.manual-delivery-record.v1/1.0.0"
DELIVERY_AUDIT_SCHEMA_VERSION = "scos-hvs.delivery-audit-event.v1/1.0.0"

SOURCE_NAME = "hermes_video_studio"

# Package preparation states.
PKG_NOT_CREATED = "NOT_CREATED"
PKG_PREPARED = "PREPARED"
PKG_MATERIALIZED = "MATERIALIZED"
ALLOWED_PACKAGE_STATES = (PKG_NOT_CREATED, PKG_PREPARED, PKG_MATERIALIZED)

# Manual delivery record states.
DEL_NOT_RECORDED = "NOT_RECORDED"
DEL_DELIVERED_MANUALLY = "DELIVERED_MANUALLY"
DEL_DELIVERY_FAILED = "DELIVERY_FAILED"
DEL_DELIVERY_CANCELLED = "DELIVERY_CANCELLED"
ALLOWED_DELIVERY_STATUSES = (
    DEL_DELIVERED_MANUALLY,
    DEL_DELIVERY_FAILED,
    DEL_DELIVERY_CANCELLED,
)

# Manual delivery channels (describe what the HUMAN did; never invoke them).
CHANNEL_IN_PERSON = "in_person"
CHANNEL_REMOVABLE_MEDIA = "removable_media"
CHANNEL_LOCAL_NETWORK_MANUAL = "local_network_manual"
CHANNEL_CUSTOMER_PORTAL_MANUAL = "customer_portal_manual"
CHANNEL_CLOUD_STORAGE_MANUAL = "cloud_storage_manual"
CHANNEL_EMAIL_MANUAL = "email_manual"
CHANNEL_MESSAGING_MANUAL = "messaging_manual"
CHANNEL_OTHER_MANUAL = "other_manual"
ALLOWED_DELIVERY_CHANNELS = (
    CHANNEL_IN_PERSON,
    CHANNEL_REMOVABLE_MEDIA,
    CHANNEL_LOCAL_NETWORK_MANUAL,
    CHANNEL_CUSTOMER_PORTAL_MANUAL,
    CHANNEL_CLOUD_STORAGE_MANUAL,
    CHANNEL_EMAIL_MANUAL,
    CHANNEL_MESSAGING_MANUAL,
    CHANNEL_OTHER_MANUAL,
)

# Stable audit event types.
EVT_PACKAGE_PREPARED = "DELIVERY_PACKAGE_PREPARED"
EVT_PACKAGE_MATERIALIZED = "DELIVERY_PACKAGE_MATERIALIZED"
EVT_PACKAGE_REUSED = "DELIVERY_PACKAGE_REUSED"
EVT_PACKAGE_INTEGRITY_FAILED = "DELIVERY_PACKAGE_INTEGRITY_FAILED"
EVT_MANUAL_DELIVERY_RECORDED = "MANUAL_DELIVERY_RECORDED"
EVT_MANUAL_DELIVERY_FAILED = "MANUAL_DELIVERY_FAILED"
EVT_MANUAL_DELIVERY_CANCELLED = "MANUAL_DELIVERY_CANCELLED"
EVT_DELIVERY_RECORD_REJECTED = "DELIVERY_RECORD_REJECTED"
ALLOWED_DELIVERY_EVENT_TYPES = (
    EVT_PACKAGE_PREPARED,
    EVT_PACKAGE_MATERIALIZED,
    EVT_PACKAGE_REUSED,
    EVT_PACKAGE_INTEGRITY_FAILED,
    EVT_MANUAL_DELIVERY_RECORDED,
    EVT_MANUAL_DELIVERY_FAILED,
    EVT_MANUAL_DELIVERY_CANCELLED,
    EVT_DELIVERY_RECORD_REJECTED,
)

# --- error codes -------------------------------------------------------------
ERR_APPROVAL_NOT_APPROVED = "approval_not_approved"
ERR_APPROVAL_NOT_FOUND = "approval_not_found"
ERR_PACKET_LINKAGE_MISMATCH = "packet_linkage_mismatch"
ERR_ARTIFACT_MISSING = "artifact_missing"
ERR_ARTIFACT_ZERO_BYTE = "artifact_zero_byte"
ERR_ARTIFACT_SHA_MISMATCH = "artifact_sha_mismatch"
ERR_ARTIFACT_NOT_REGULAR = "artifact_not_regular"
ERR_UNSAFE_PATH = "unsafe_path"
ERR_PACKAGE_CONFLICT = "package_conflict"
ERR_PACKAGE_NOT_FOUND = "package_not_found"
ERR_NOT_MATERIALIZED = "not_materialized"
ERR_MISSING_OPERATOR_ID = "missing_operator_id"
ERR_MISSING_CHANNEL = "missing_channel"
ERR_MISSING_RECIPIENT = "missing_recipient"
ERR_MISSING_REASON = "missing_reason"
ERR_INVALID_STATUS = "invalid_status"
ERR_INVALID_CHANNEL = "invalid_channel"
ERR_DELIVERY_RECORD_CONFLICT = "delivery_record_conflict"
ERR_DELIVERY_RECORD_NOT_FOUND = "delivery_record_not_found"
ERR_AUTOMATION_NOT_ALLOWED = "automation_not_allowed"

_DIGEST_LENGTH = 16
_MANUAL_DELIVERY_NOTICE = (
    "This package is prepared for human-performed manual delivery only. "
    "SCOS performed no automated distribution."
)
_SCOS_EXTERNAL_ACTION_STATEMENT = (
    "SCOS did not execute the delivery. The delivery was performed by a "
    "human operator through an external, out-of-system channel."
)


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_hex16(text: str) -> str:
    return _sha256_hex(text)[:_DIGEST_LENGTH]


def _require_nonempty(field: str, value: str | None) -> None:
    if not str(value or "").strip():
        raise ValueError(f"{field} must not be empty")


def _require_allowed(field: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ValueError(f"{field} must be one of {list(allowed)}, got {value!r}")


def stable_package_id(
    *,
    approval_request_id: str,
    packet_id: str | None,
    evidence_validation_id: str | None,
    artifact_sha256: str | None,
    contract_version: str,
) -> str:
    """Deterministic package id from stable semantic values.

    Identical valid inputs always yield the same package id. Volatile fields
    (timestamps, pids, machine/user names, temp dirs, random uuids, mutable
    destination paths) are explicitly excluded.
    """
    canon = "|".join(
        [
            "package",
            approval_request_id,
            packet_id or "",
            evidence_validation_id or "",
            artifact_sha256 or "",
            contract_version,
        ]
    )
    return "scos-hvs-delivery-" + _sha256_hex16(canon)


def stable_delivery_record_id(
    *,
    package_id: str,
    approval_request_id: str,
    artifact_sha256: str | None,
    contract_version: str,
    status: str,
) -> str:
    """Deterministic manual-delivery record id (no timestamp dependency)."""
    canon = "|".join(
        [
            "manual-delivery",
            package_id,
            approval_request_id,
            artifact_sha256 or "",
            contract_version,
            status,
        ]
    )
    return "scos-hvs-delivery-rec-" + _sha256_hex16(canon)


def stable_delivery_event_id(
    *,
    event_type: str,
    package_id: str,
    approval_request_id: str,
    packet_id: str | None,
    artifact_sha256: str | None,
    operator_id: str | None,
    resulting_state: str | None,
) -> str:
    """Deterministic delivery audit event id (no timestamp dependency)."""
    canon = "|".join(
        [
            event_type,
            package_id,
            approval_request_id,
            packet_id or "",
            artifact_sha256 or "",
            operator_id or "",
            resulting_state or "",
        ]
    )
    return "dlevt-" + _sha256_hex16(canon)


@dataclass(frozen=True)
class HVSLocalDeliveryPackage:
    """A deterministic local delivery-package manifest."""

    schema_version: str
    package_id: str
    approval_request_id: str
    packet_id: str | None
    evidence_id: str | None
    evidence_validation_id: str | None
    source_system: str
    source_project_id: str | None
    artifact_display_name: str
    source_artifact_display_path: str
    source_artifact_sha256: str
    source_artifact_size: int
    package_status: str
    package_relative_path: str
    packaged_artifact_relative_path: str | None
    packaged_artifact_sha256: str | None
    package_manifest_sha256: str
    prepared_by_operator_id: str
    automation_allowed: bool
    manual_delivery_required: bool
    manual_delivery_notice: str
    created_at: str
    identity_inputs: dict[str, Any]
    audit_correlation: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "package_id": self.package_id,
            "approval_request_id": self.approval_request_id,
            "packet_id": self.packet_id,
            "evidence_id": self.evidence_id,
            "evidence_validation_id": self.evidence_validation_id,
            "source_system": self.source_system,
            "source_project_id": self.source_project_id,
            "artifact_display_name": self.artifact_display_name,
            "source_artifact_display_path": self.source_artifact_display_path,
            "source_artifact_sha256": self.source_artifact_sha256,
            "source_artifact_size": self.source_artifact_size,
            "package_status": self.package_status,
            "package_relative_path": self.package_relative_path,
            "packaged_artifact_relative_path": self.packaged_artifact_relative_path,
            "packaged_artifact_sha256": self.packaged_artifact_sha256,
            "package_manifest_sha256": self.package_manifest_sha256,
            "prepared_by_operator_id": self.prepared_by_operator_id,
            "automation_allowed": self.automation_allowed,
            "manual_delivery_required": self.manual_delivery_required,
            "manual_delivery_notice": self.manual_delivery_notice,
            "created_at": self.created_at,
            "identity_inputs": self.identity_inputs,
            "audit_correlation": self.audit_correlation,
        }


@dataclass(frozen=True)
class HVSManualDeliveryRecord:
    """An immutable operator-entered manual-delivery record."""

    schema_version: str
    delivery_record_id: str
    package_id: str
    approval_request_id: str
    artifact_sha256: str
    operator_id: str
    final_status: str
    channel: str
    recipient_label: str
    external_reference: str | None
    operator_note: str | None
    failure_or_cancel_reason: str | None
    manual_delivery_performed: bool
    automation_allowed: bool
    delivery_was_external_to_scos: bool
    scos_external_action_statement: str
    recorded_at: str
    audit_correlation: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "delivery_record_id": self.delivery_record_id,
            "package_id": self.package_id,
            "approval_request_id": self.approval_request_id,
            "artifact_sha256": self.artifact_sha256,
            "operator_id": self.operator_id,
            "final_status": self.final_status,
            "channel": self.channel,
            "recipient_label": self.recipient_label,
            "external_reference": self.external_reference,
            "operator_note": self.operator_note,
            "failure_or_cancel_reason": self.failure_or_cancel_reason,
            "manual_delivery_performed": self.manual_delivery_performed,
            "automation_allowed": self.automation_allowed,
            "delivery_was_external_to_scos": self.delivery_was_external_to_scos,
            "scos_external_action_statement": self.scos_external_action_statement,
            "recorded_at": self.recorded_at,
            "audit_correlation": self.audit_correlation,
        }


@dataclass(frozen=True)
class DeliveryAuditEvent:
    """One append-only delivery audit event (deterministic id, no timestamp in id)."""

    schema_version: str
    event_id: str
    event_type: str
    package_id: str
    approval_request_id: str
    packet_id: str | None
    artifact_sha256: str
    resulting_state: str
    operator_id: str | None
    recorded_at: str
    automation_allowed: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "package_id": self.package_id,
            "approval_request_id": self.approval_request_id,
            "packet_id": self.packet_id,
            "artifact_sha256": self.artifact_sha256,
            "resulting_state": self.resulting_state,
            "operator_id": self.operator_id,
            "recorded_at": self.recorded_at,
            "automation_allowed": self.automation_allowed,
            "detail": self.detail,
        }


def manual_delivery_notice() -> str:
    return _MANUAL_DELIVERY_NOTICE


def scos_external_action_statement() -> str:
    return _SCOS_EXTERNAL_ACTION_STATEMENT
