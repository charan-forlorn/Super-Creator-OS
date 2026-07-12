"""Immutable, local-only delivery-version lineage contracts for SCOS/HVS.

Stage 8A.1 records an operator-confirmed version only after an existing
completed delivery has been revalidated.  It does not create revisions, invoke
HVS, render, supersede artifacts, or alter commercial records.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


DELIVERY_LINEAGE_SCHEMA_VERSION = "scos-hvs.delivery-lineage.v1/1.0.0"
DELIVERY_LINEAGE_EVENT_SCHEMA_VERSION = "scos-hvs.delivery-lineage-event.v1/1.0.0"

LINEAGE_UNKNOWN = "UNKNOWN"
LINEAGE_REGISTERED = "REGISTERED"
LINEAGE_CONFLICTED = "CONFLICTED"
LINEAGE_INVALID = "INVALID"
ALLOWED_LINEAGE_STATUSES = (LINEAGE_UNKNOWN, LINEAGE_REGISTERED, LINEAGE_CONFLICTED, LINEAGE_INVALID)

SUPERSESSION_CURRENT = "CURRENT"
SUPERSESSION_NOT_YET_SUPERSEDED = "NOT_YET_SUPERSEDED"
SUPERSESSION_SUPERSEDED = "SUPERSEDED"
ALLOWED_SUPERSESSION_STATUSES = (
    SUPERSESSION_CURRENT,
    SUPERSESSION_NOT_YET_SUPERSEDED,
    SUPERSESSION_SUPERSEDED,
)

BASIS_ORIGINAL_DELIVERY_CONFIRMED = "ORIGINAL_DELIVERY_CONFIRMED"
BASIS_EXISTING_EXTERNAL_VERSION_RECORD = "EXISTING_EXTERNAL_VERSION_RECORD"
BASIS_OPERATOR_HISTORICAL_RECONCILIATION = "OPERATOR_HISTORICAL_RECONCILIATION"
BASIS_IMPORTED_CERTIFIED_LINEAGE = "IMPORTED_CERTIFIED_LINEAGE"
BASIS_SUCCESSOR_OF_REGISTERED_DELIVERY = "SUCCESSOR_OF_REGISTERED_DELIVERY"
ALLOWED_REGISTRATION_BASES = (
    BASIS_ORIGINAL_DELIVERY_CONFIRMED,
    BASIS_EXISTING_EXTERNAL_VERSION_RECORD,
    BASIS_OPERATOR_HISTORICAL_RECONCILIATION,
    BASIS_IMPORTED_CERTIFIED_LINEAGE,
    BASIS_SUCCESSOR_OF_REGISTERED_DELIVERY,
)

EVT_LINEAGE_REGISTRATION_REQUESTED = "LINEAGE_REGISTRATION_REQUESTED"
EVT_LINEAGE_REGISTERED = "LINEAGE_REGISTERED"
EVT_LINEAGE_REGISTRATION_REJECTED = "LINEAGE_REGISTRATION_REJECTED"
EVT_SUCCESSOR_VERSION_PLANNED = "SUCCESSOR_VERSION_PLANNED"
EVT_LINEAGE_CONFLICT_DETECTED = "LINEAGE_CONFLICT_DETECTED"
ALLOWED_LINEAGE_EVENT_TYPES = (
    EVT_LINEAGE_REGISTRATION_REQUESTED,
    EVT_LINEAGE_REGISTERED,
    EVT_LINEAGE_REGISTRATION_REJECTED,
    EVT_SUCCESSOR_VERSION_PLANNED,
    EVT_LINEAGE_CONFLICT_DETECTED,
)

ERR_INVALID_INPUT = "INVALID_INPUT"
ERR_NOT_FOUND = "RECORD_NOT_FOUND"
ERR_INELIGIBLE_CLOSURE = "INELIGIBLE_CLOSURE"
ERR_ARTIFACT_SHA_MISMATCH = "ARTIFACT_SHA_MISMATCH"
ERR_DELIVERY_VERSION_UNKNOWN = "DELIVERY_VERSION_UNKNOWN"
ERR_MISSING_OPERATOR_ID = "MISSING_OPERATOR_ID"
ERR_LEGACY_CONFIRMATION_REQUIRED = "LEGACY_VERSION_CONFIRMATION_REQUIRED"
ERR_CONFLICT = "LINEAGE_CONFLICT"
ERR_PARENT_REQUIRED = "PARENT_LINEAGE_REQUIRED"
ERR_PARENT_INVALID = "PARENT_LINEAGE_INVALID"


def _normalized_text(field: str, value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    return text


@dataclass(frozen=True)
class DeliveryVersion:
    """Positive integer delivery sequence with one canonical display form."""

    sequence: int

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence <= 0:
            raise ValueError("delivery version sequence must be a positive integer")

    @property
    def display(self) -> str:
        return f"v{self.sequence}"

    @classmethod
    def parse(cls, value: Any) -> "DeliveryVersion":
        if isinstance(value, bool) or isinstance(value, float):
            raise ValueError("delivery version must be a positive integer")
        if isinstance(value, int):
            return cls(value)
        if not isinstance(value, str):
            raise ValueError("delivery version must be a positive integer")
        text = value.strip()
        digits = text[1:] if text.startswith("v") else text
        if not digits or not digits.isascii() or not digits.isdigit() or (len(digits) > 1 and digits.startswith("0")):
            raise ValueError("delivery version must be a canonical positive integer or v<integer>")
        return cls(int(digits))

    def to_dict(self) -> dict[str, Any]:
        return {"sequence": self.sequence, "display": self.display}


def _stable_id(prefix: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return f"{prefix}-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


def stable_artifact_id(*, artifact_sha256: str) -> str:
    return _stable_id("scos-hvs-artifact", {"artifact_sha256": _normalized_text("artifact_sha256", artifact_sha256).lower()})


def stable_lineage_id(
    *, project_id: str | None, delivery_record_id: str, delivery_closure_id: str,
    artifact_id: str, artifact_sha256: str, delivery_version_sequence: int,
    parent_lineage_id: str | None,
) -> str:
    return _stable_id("scos-hvs-lineage", {
        "artifact_id": _normalized_text("artifact_id", artifact_id),
        "artifact_sha256": _normalized_text("artifact_sha256", artifact_sha256).lower(),
        "delivery_closure_id": _normalized_text("delivery_closure_id", delivery_closure_id),
        "delivery_record_id": _normalized_text("delivery_record_id", delivery_record_id),
        "delivery_version_sequence": DeliveryVersion(delivery_version_sequence).sequence,
        "parent_lineage_id": str(parent_lineage_id or ""),
        "project_id": str(project_id or ""),
    })


def stable_lineage_event_id(*, event_type: str, lineage_id: str | None, delivery_record_id: str | None, detail: str | None) -> str:
    return _stable_id("dllevt", {
        "delivery_record_id": str(delivery_record_id or ""),
        "detail": str(detail or ""),
        "event_type": _normalized_text("event_type", event_type),
        "lineage_id": str(lineage_id or ""),
    })


@dataclass(frozen=True)
class DeliveryLineageRecord:
    schema_version: str
    lineage_id: str
    project_id: str | None
    recipient_label: str | None
    delivery_record_id: str
    delivery_closure_id: str
    artifact_id: str
    artifact_sha256: str
    delivery_version_sequence: int
    delivery_version_display: str
    parent_lineage_id: str | None
    parent_artifact_id: str | None
    parent_artifact_sha256: str | None
    parent_delivery_version_sequence: int | None
    lineage_status: str
    supersession_status: str
    registered_by_operator_id: str
    registration_basis: str
    evidence_reference: str | None
    registration_reason: str | None
    deterministic_content_hash: str
    registered_at: str

    def __post_init__(self) -> None:
        version = DeliveryVersion(self.delivery_version_sequence)
        if self.delivery_version_display != version.display:
            raise ValueError("delivery_version_display must be canonical")
        if self.lineage_status not in ALLOWED_LINEAGE_STATUSES:
            raise ValueError("invalid lineage status")
        if self.supersession_status not in ALLOWED_SUPERSESSION_STATUSES:
            raise ValueError("invalid supersession status")
        if self.registration_basis not in ALLOWED_REGISTRATION_BASES:
            raise ValueError("invalid registration basis")

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class DeliveryLineageRegistrationRequest:
    delivery_record_id: str
    delivery_version: DeliveryVersion
    operator_id: str
    registration_basis: str
    confirm_legacy_version: bool
    evidence_reference: str | None = None
    registration_reason: str | None = None
    parent_lineage_id: str | None = None


@dataclass(frozen=True)
class DeliveryLineageEvent:
    schema_version: str
    event_id: str
    event_type: str
    delivery_record_id: str | None
    lineage_id: str | None
    resulting_status: str
    operator_id: str | None
    recorded_at: str
    automation_allowed: bool
    detail: str | None
    record: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.event_type not in ALLOWED_LINEAGE_EVENT_TYPES:
            raise ValueError("invalid lineage event type")
        if self.automation_allowed is not False:
            raise ValueError("lineage automation_allowed must be false")

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class SuccessorVersionPlan:
    source_lineage_id: str
    source_version: DeliveryVersion
    planned_successor_version: DeliveryVersion
    source_artifact_sha256: str
    supersession_status: str
    persistence_performed: bool
    rerender_started: bool
    automation_allowed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_lineage_id": self.source_lineage_id,
            "source_version": self.source_version.to_dict(),
            "planned_successor_version": self.planned_successor_version.to_dict(),
            "source_artifact_sha256": self.source_artifact_sha256,
            "supersession_status": self.supersession_status,
            "persistence_performed": self.persistence_performed,
            "rerender_started": self.rerender_started,
            "automation_allowed": self.automation_allowed,
        }
