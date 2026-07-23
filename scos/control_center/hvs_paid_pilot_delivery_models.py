"""SCOS Cohort 10H — paid-pilot delivery domain models.

Single authoritative delivery-state model for the paid-pilot golden journey.
Reuses the Cohort 10G QA engine and package builder; this module only defines
the delivery/rights/backup/handoff state, deterministic identifiers, and the
lifecycle vocabulary required by the Control Center API contracts.

Stdlib-only. Deterministic. No clock/random/uuid/network/subprocess.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Optional, Tuple

# --- schema / identity -------------------------------------------------------
DELIVERY_SCHEMA_VERSION = "scos-hvs.paid-pilot-delivery.v1/1.0.0"

# --- delivery lifecycle states (master §7) ----------------------------------
DELIVERY_NOT_REQUESTED = "DELIVERY_NOT_REQUESTED"
DELIVERY_BLOCKED_QA_REQUIRED = "DELIVERY_BLOCKED_QA_REQUIRED"
DELIVERY_BLOCKED_QA_FAILED = "DELIVERY_BLOCKED_QA_FAILED"
DELIVERY_BLOCKED_RIGHTS_INCOMPLETE = "DELIVERY_BLOCKED_RIGHTS_INCOMPLETE"
DELIVERY_AWAITING_OPERATOR_APPROVAL = "DELIVERY_AWAITING_OPERATOR_APPROVAL"
DELIVERY_REJECTED = "DELIVERY_REJECTED"
DELIVERY_APPROVED = "DELIVERY_APPROVED"
DELIVERY_PACKAGE_CREATING = "DELIVERY_PACKAGE_CREATING"
DELIVERY_PACKAGE_READY = "DELIVERY_PACKAGE_READY"
DELIVERY_PACKAGE_FAILED_CONFIRMED = "DELIVERY_PACKAGE_FAILED_CONFIRMED"
DELIVERY_PACKAGE_OUTCOME_UNKNOWN = "DELIVERY_PACKAGE_OUTCOME_UNKNOWN"
DELIVERY_PACKAGE_CORRUPT = "DELIVERY_PACKAGE_CORRUPT"
DELIVERY_PACKAGE_INCOMPATIBLE = "DELIVERY_PACKAGE_INCOMPATIBLE"
DELIVERY_BACKUP_READY = "DELIVERY_BACKUP_READY"
DELIVERY_READY_FOR_MANUAL_HANDOFF = "DELIVERY_READY_FOR_MANUAL_HANDOFF"

ALLOWED_DELIVERY_STATES = (
    DELIVERY_NOT_REQUESTED,
    DELIVERY_BLOCKED_QA_REQUIRED,
    DELIVERY_BLOCKED_QA_FAILED,
    DELIVERY_BLOCKED_RIGHTS_INCOMPLETE,
    DELIVERY_AWAITING_OPERATOR_APPROVAL,
    DELIVERY_REJECTED,
    DELIVERY_APPROVED,
    DELIVERY_PACKAGE_CREATING,
    DELIVERY_PACKAGE_READY,
    DELIVERY_PACKAGE_FAILED_CONFIRMED,
    DELIVERY_PACKAGE_OUTCOME_UNKNOWN,
    DELIVERY_PACKAGE_CORRUPT,
    DELIVERY_PACKAGE_INCOMPATIBLE,
    DELIVERY_BACKUP_READY,
    DELIVERY_READY_FOR_MANUAL_HANDOFF,
)

# --- rights checklist outcomes (master §10) ---------------------------------
RIGHTS_NOT_REVIEWED = "RIGHTS_NOT_REVIEWED"
RIGHTS_INCOMPLETE = "RIGHTS_INCOMPLETE"
RIGHTS_BLOCKED = "RIGHTS_BLOCKED"
RIGHTS_APPROVED = "RIGHTS_APPROVED"

ALLOWED_RIGHTS_STATES = (
    RIGHTS_NOT_REVIEWED,
    RIGHTS_INCOMPLETE,
    RIGHTS_BLOCKED,
    RIGHTS_APPROVED,
)

# --- operator decision states (master §11) ----------------------------------
APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
APPROVED_FOR_DELIVERY = "APPROVED_FOR_DELIVERY"
REJECTED_REWORK_REQUIRED = "REJECTED_REWORK_REQUIRED"

ALLOWED_OPERATOR_DECISIONS = (
    APPROVAL_REQUIRED,
    APPROVED_FOR_DELIVERY,
    REJECTED_REWORK_REQUIRED,
)

# --- QA states (mirror Cohort 10G vocabulary, reused not redefined) ---------
QA_NOT_RUN = "QA_NOT_RUN"
QA_RUNNING = "QA_RUNNING"
QA_PASSED = "QA_PASSED"
QA_FAILED_CONFIRMED = "QA_FAILED_CONFIRMED"
QA_OUTCOME_UNKNOWN = "QA_OUTCOME_UNKNOWN"
QA_ARTIFACT_MISSING = "QA_ARTIFACT_MISSING"
QA_ARTIFACT_CORRUPT = "QA_ARTIFACT_CORRUPT"

# --- retention classification (master §9.4) ----------------------------------
RETENTION_KEEP_UNTIL_OPERATOR_ARCHIVES = "KEEP_UNTIL_OPERATOR_ARCHIVES"
RETENTION_KEEP_FOR_PAID_PILOT_REVIEW = "KEEP_FOR_PAID_PILOT_REVIEW"
RETENTION_MANUAL_PURGE_REQUIRED = "MANUAL_PURGE_REQUIRED"

ALLOWED_RETENTION_CLASSES = (
    RETENTION_KEEP_UNTIL_OPERATOR_ARCHIVES,
    RETENTION_KEEP_FOR_PAID_PILOT_REVIEW,
    RETENTION_MANUAL_PURGE_REQUIRED,
)

# --- error codes -------------------------------------------------------------
ERR_MISSING_OPERATOR_ID = "MISSING_OPERATOR_ID"
ERR_RIGHTS_NOT_APPROVED = "RIGHTS_NOT_APPROVED"
ERR_QA_NOT_PASSED = "QA_NOT_PASSED"
ERR_ALREADY_DECIDED = "ALREADY_DECIDED"
ERR_PACKAGE_CONFLICT = "PACKAGE_CONFLICT"
ERR_PACKAGE_NOT_READY = "PACKAGE_NOT_READY"
ERR_BACKUP_MISMATCH = "BACKUP_MISMATCH"
ERR_UNSAFE_NAME = "UNSAFE_NAME"

_DIGEST_LENGTH = 16


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _short_id(text: str) -> str:
    return _sha256_hex(text)[:_DIGEST_LENGTH]


def stable_delivery_id(
    *, project_id: str, source_render_attempt_id: str,
    artifact_sha256: str, qa_record_id: str, media_profile: str,
) -> str:
    """Deterministic delivery identity (content-derived, no clock/uuid)."""
    return "scos-hvs-pp-delivery-" + _short_id("|".join([
        "delivery", project_id, source_render_attempt_id,
        artifact_sha256, qa_record_id, media_profile,
    ]))


def stable_rights_revision(
    *, project_id: str, operator_id: str, reviewed_at: str,
    entries_fingerprint: str,
) -> str:
    return "scos-hvs-pp-rights-" + _short_id("|".join([
        "rights", project_id, operator_id, reviewed_at, entries_fingerprint,
    ]))


def stable_package_revision(
    *, delivery_id: str, artifact_sha256: str, qa_record_id: str,
    rights_revision: str, operator_decision: str,
) -> str:
    return "scos-hvs-pp-pkg-" + _short_id("|".join([
        "package", delivery_id, artifact_sha256, qa_record_id,
        rights_revision, operator_decision,
    ]))


def stable_backup_id(*, package_id: str, package_sha256: str) -> str:
    return "scos-hvs-pp-backup-" + _short_id("|".join([
        "backup", package_id, package_sha256,
    ]))


def safe_delivery_filename(delivery_id: str) -> str:
    """Deterministic, safe zip filename (no path components)."""
    base = delivery_id.replace("scos-hvs-pp-delivery-", "pp-delivery-")
    cleaned = "".join(c if (c.isalnum() or c in "-_") else "_" for c in base)
    return (cleaned or "pp-delivery")[:96] + ".zip"


@dataclass(frozen=True)
class RightsChecklistEntry:
    """One asset rights declaration (master §10)."""

    asset_kind: str
    description: str
    known_source: bool
    permitted: bool
    attribution_note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_kind": self.asset_kind,
            "description": self.description,
            "known_source": self.known_source,
            "permitted": self.permitted,
            "attribution_note": self.attribution_note,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RightsChecklistEntry":
        return cls(
            asset_kind=str(d.get("asset_kind", "")),
            description=str(d.get("description", "")),
            known_source=bool(d.get("known_source", False)),
            permitted=bool(d.get("permitted", False)),
            attribution_note=str(d.get("attribution_note", "")),
        )


@dataclass(frozen=True)
class RightsChecklist:
    """Authoritative rights checklist revision."""

    revision: str
    delivery_id: str
    project_id: str
    operator_id: str
    reviewed_at: str
    status: str
    entries: Tuple[RightsChecklistEntry, ...]
    attestation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": DELIVERY_SCHEMA_VERSION,
            "revision": self.revision,
            "delivery_id": self.delivery_id,
            "project_id": self.project_id,
            "operator_id": self.operator_id,
            "reviewed_at": self.reviewed_at,
            "status": self.status,
            "entries": [e.to_dict() for e in self.entries],
            "attestation": self.attestation,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RightsChecklist":
        return cls(
            revision=str(d.get("revision", "")),
            delivery_id=str(d.get("delivery_id", "")),
            project_id=str(d.get("project_id", "")),
            operator_id=str(d.get("operator_id", "")),
            reviewed_at=str(d.get("reviewed_at", "")),
            status=str(d.get("status", RIGHTS_NOT_REVIEWED)),
            entries=tuple(RightsChecklistEntry.from_dict(e) for e in d.get("entries", [])),
            attestation=str(d.get("attestation", "")),
        )


@dataclass(frozen=True)
class DeliveryBackupReceipt:
    """Immutable backup verification receipt (master §9.3)."""

    backup_id: str
    package_id: str
    package_sha256: str
    backup_sha256: str
    created_at: str
    protection_class: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "backup_id": self.backup_id,
            "package_id": self.package_id,
            "package_sha256": self.package_sha256,
            "backup_sha256": self.backup_sha256,
            "created_at": self.created_at,
            "protection_class": self.protection_class,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DeliveryBackupReceipt":
        return cls(
            backup_id=str(d.get("backup_id", "")),
            package_id=str(d.get("package_id", "")),
            package_sha256=str(d.get("package_sha256", "")),
            backup_sha256=str(d.get("backup_sha256", "")),
            created_at=str(d.get("created_at", "")),
            protection_class=str(d.get("protection_class", "")),
        )


@dataclass(frozen=True)
class PaidPilotDeliveryRecord:
    """Single authoritative paid-pilot delivery record (master §7)."""

    schema_version: str
    delivery_id: str
    project_id: str
    source_render_attempt_id: str
    artifact_identity: str
    artifact_sha256: str
    artifact_size: int
    media_profile: str
    qa_record_id: str
    qa_state: str
    operator_id: str
    operator_decision: str
    rights_checklist_revision: str
    rights_status: str
    package_revision: str
    package_sha256: str
    backup_receipt: Optional[DeliveryBackupReceipt]
    retention_class: str
    created_at: str
    updated_at: str
    state: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "delivery_id": self.delivery_id,
            "project_id": self.project_id,
            "source_render_attempt_id": self.source_render_attempt_id,
            "artifact_identity": self.artifact_identity,
            "artifact_sha256": self.artifact_sha256,
            "artifact_size": self.artifact_size,
            "media_profile": self.media_profile,
            "qa_record_id": self.qa_record_id,
            "qa_state": self.qa_state,
            "operator_id": self.operator_id,
            "operator_decision": self.operator_decision,
            "rights_checklist_revision": self.rights_checklist_revision,
            "rights_status": self.rights_status,
            "package_revision": self.package_revision,
            "package_sha256": self.package_sha256,
            "backup_receipt": self.backup_receipt.to_dict() if self.backup_receipt else None,
            "retention_class": self.retention_class,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "state": self.state,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PaidPilotDeliveryRecord":
        raw_backup = d.get("backup_receipt")
        return cls(
            schema_version=str(d.get("schema_version", DELIVERY_SCHEMA_VERSION)),
            delivery_id=str(d.get("delivery_id", "")),
            project_id=str(d.get("project_id", "")),
            source_render_attempt_id=str(d.get("source_render_attempt_id", "")),
            artifact_identity=str(d.get("artifact_identity", "")),
            artifact_sha256=str(d.get("artifact_sha256", "")),
            artifact_size=int(d.get("artifact_size", 0) or 0),
            media_profile=str(d.get("media_profile", "")),
            qa_record_id=str(d.get("qa_record_id", "")),
            qa_state=str(d.get("qa_state", QA_NOT_RUN)),
            operator_id=str(d.get("operator_id", "")),
            operator_decision=str(d.get("operator_decision", APPROVAL_REQUIRED)),
            rights_checklist_revision=str(d.get("rights_checklist_revision", "")),
            rights_status=str(d.get("rights_status", RIGHTS_NOT_REVIEWED)),
            package_revision=str(d.get("package_revision", "")),
            package_sha256=str(d.get("package_sha256", "")),
            backup_receipt=DeliveryBackupReceipt.from_dict(raw_backup) if raw_backup else None,
            retention_class=str(d.get("retention_class", RETENTION_MANUAL_PURGE_REQUIRED)),
            created_at=str(d.get("created_at", "")),
            updated_at=str(d.get("updated_at", "")),
            state=str(d.get("state", DELIVERY_NOT_REQUESTED)),
        )
