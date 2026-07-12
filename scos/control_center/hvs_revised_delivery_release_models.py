"""Stage 8E revised-delivery acceptance, customer release authorization, and
final revision closure contracts; no HVS execution, no outbound transport.

This module defines the SCOS-side immutable, deterministic models for taking a
Stage 8D reconciled revised delivery through internal acceptance review,
explicit customer-release authorization, a deterministic release-readiness
decision, and final revision closure.

Design reuses the canonical contracts of adjacent stages:

  * ``_safe_id`` / ``_safe_optional_id`` / ``ALLOWED_TARGET_FORMATS`` from the
    Stage 8C dispatch models (identical safe-logical-identifier policy)
  * ``ALLOWED_DELIVERY_CHANNELS`` from the Stage 6 local-delivery models
    (canonical outbound channel allowlist)
  * the deterministic sha256-prefixed id style (no time / random)
  * frozen dataclasses, canonical JSON serialization, append-only audit events

Stage 8E deliberately does NOT import or invoke HVS, does NOT render media, does
NOT create a second delivery-version / revision / dispatch / reconciliation /
approval / or audit subsystem, and performs NO customer contact or delivery
transport. It constructs internal authorization and readiness evidence only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

# Reuse the Stage 8C safe-id policy and the bounded target-format allowlist so
# the acceptance / authorization vocabulary shares one source of truth with the
# adjacent dispatch + reconciliation stages.
from .hvs_rerender_dispatch_models import (  # noqa: F401
    ALLOWED_TARGET_FORMATS,
    _safe_id,
    _safe_optional_id,
)
# Reuse the canonical Stage 6 manual delivery-channel allowlist so the
# authorization can only approve channels the repository already governs.
from .hvs_local_delivery_models import (  # noqa: F401
    ALLOWED_DELIVERY_CHANNELS,
)

RELEASE_SCHEMA_VERSION = "scos-hvs.revised-delivery-release.v1/1.0.0"
RELEASE_EVENT_SCHEMA_VERSION = "scos-hvs.revised-delivery-release-event.v1/1.0.0"

# --- Revised-delivery acceptance status (Stage 8E state machine) ------------
ACCEPTANCE_PENDING_REVIEW = "PENDING_REVIEW"
ACCEPTANCE_ACCEPTED = "ACCEPTED"
ACCEPTANCE_PARTIALLY_ACCEPTED = "PARTIALLY_ACCEPTED"
ACCEPTANCE_REJECTED = "REJECTED"
ACCEPTANCE_CANCELLED = "CANCELLED"
ACCEPTANCE_SUPERSEDED = "SUPERSEDED"
ALLOWED_ACCEPTANCE_STATUSES = (
    ACCEPTANCE_PENDING_REVIEW,
    ACCEPTANCE_ACCEPTED,
    ACCEPTANCE_PARTIALLY_ACCEPTED,
    ACCEPTANCE_REJECTED,
    ACCEPTANCE_CANCELLED,
    ACCEPTANCE_SUPERSEDED,
)

# --- Customer release authorization status (Stage 8E state machine) ----------
AUTH_PENDING = "PENDING"
AUTH_AUTHORIZED = "AUTHORIZED"
AUTH_REJECTED = "REJECTED"
AUTH_REVOKED = "REVOKED"
AUTH_EXPIRED = "EXPIRED"
AUTH_CANCELLED = "CANCELLED"
AUTH_SUPERSEDED = "SUPERSEDED"
ALLOWED_AUTH_STATUSES = (
    AUTH_PENDING,
    AUTH_AUTHORIZED,
    AUTH_REJECTED,
    AUTH_REVOKED,
    AUTH_EXPIRED,
    AUTH_CANCELLED,
    AUTH_SUPERSEDED,
)

# --- Append-only Stage 8E lifecycle audit event types -----------------------
EVT_REVISED_DELIVERY_REVIEW_REQUESTED = "REVISED_DELIVERY_REVIEW_REQUESTED"
EVT_REVISED_DELIVERY_ACCEPTED = "REVISED_DELIVERY_ACCEPTED"
EVT_REVISED_DELIVERY_PARTIALLY_ACCEPTED = "REVISED_DELIVERY_PARTIALLY_ACCEPTED"
EVT_REVISED_DELIVERY_REJECTED = "REVISED_DELIVERY_REJECTED"
EVT_RELEASE_AUTHORIZATION_REQUESTED = "RELEASE_AUTHORIZATION_REQUESTED"
EVT_RELEASE_AUTHORIZED = "RELEASE_AUTHORIZED"
EVT_RELEASE_AUTHORIZATION_REJECTED = "RELEASE_AUTHORIZATION_REJECTED"
EVT_RELEASE_AUTHORIZATION_REVOKED = "RELEASE_AUTHORIZATION_REVOKED"
EVT_RELEASE_AUTHORIZATION_EXPIRED = "RELEASE_AUTHORIZATION_EXPIRED"
EVT_RELEASE_READINESS_EVALUATED = "RELEASE_READINESS_EVALUATED"
EVT_RELEASE_READINESS_REJECTED = "RELEASE_READINESS_REJECTED"
EVT_RELEASE_READY = "RELEASE_READY"
EVT_REVISION_FINALLY_CLOSED = "REVISION_FINALLY_CLOSED"
EVT_DUPLICATE_REQUEST_DETECTED = "DUPLICATE_REQUEST_DETECTED"
EVT_CONFLICTING_REQUEST_REJECTED = "CONFLICTING_REQUEST_REJECTED"
ALLOWED_RELEASE_EVENT_TYPES = (
    EVT_REVISED_DELIVERY_REVIEW_REQUESTED,
    EVT_REVISED_DELIVERY_ACCEPTED,
    EVT_REVISED_DELIVERY_PARTIALLY_ACCEPTED,
    EVT_REVISED_DELIVERY_REJECTED,
    EVT_RELEASE_AUTHORIZATION_REQUESTED,
    EVT_RELEASE_AUTHORIZED,
    EVT_RELEASE_AUTHORIZATION_REJECTED,
    EVT_RELEASE_AUTHORIZATION_REVOKED,
    EVT_RELEASE_AUTHORIZATION_EXPIRED,
    EVT_RELEASE_READINESS_EVALUATED,
    EVT_RELEASE_READINESS_REJECTED,
    EVT_RELEASE_READY,
    EVT_REVISION_FINALLY_CLOSED,
    EVT_DUPLICATE_REQUEST_DETECTED,
    EVT_CONFLICTING_REQUEST_REJECTED,
)

# Tokens rejected in safe text fields (path / shell / URL / injection fragments).
_UNSAFE_TEXT_TOKENS = ("..", "\\", "/", "://", ";", "|", "$", "`", "\n", "\r")
_LOG_INJECTION_TOKENS = ("\n", "\r", "\x00")


def _sha256_hex(value: Any) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _stable_id(prefix: str, payload: dict[str, Any]) -> str:
    return f"{prefix}-{_sha256_hex(payload)[:16]}"


def _safe_customer_reference(field: str, value: Any) -> str:
    """Validate a customer reference as a safe logical identifier.

    Rejects empty values and any path / shell / URL fragment, plus newline /
    carriage-return log-injection content. Never raises on attacker-controlled
    content silently — it raises ``ValueError`` so the service can fail closed.
    """
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} must be a non-empty safe reference")
    lowered = text.lower()
    for token in _UNSAFE_TEXT_TOKENS:
        if token in lowered:
            raise ValueError(
                f"{field} must be a safe reference (rejected token {token!r})"
            )
    return text


def _safe_text(field: str, value: Any) -> str:
    """Validate free-text policy fields (allow slashes/dots, reject CR/LF/null
    and path-traversal fragments)."""
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} must be a non-empty reference")
    lowered = text.lower()
    for token in ("..", "\\", "://", "\n", "\r", "\x00"):
        if token in lowered:
            raise ValueError(f"{field} contains an unsafe fragment (rejected token {token!r})")
    return text


def _safe_log_text(field: str, value: Any | None) -> str | None:
    """Validate free-text review content as log-injection-safe (no CR/LF/null)."""
    if value is None:
        return None
    text = str(value)
    for token in _LOG_INJECTION_TOKENS:
        if token in text:
            raise ValueError(f"{field} must not contain newline or null content")
    return text


def _require_allowed_format(fmt: str) -> str:
    text = str(fmt or "").strip().lower()
    if text not in ALLOWED_TARGET_FORMATS:
        raise ValueError(f"output format {fmt!r} is not an allowed delivery variant")
    return text


def _require_allowed_channel(channel: str) -> str:
    text = str(channel or "").strip().lower()
    if text not in ALLOWED_DELIVERY_CHANNELS:
        raise ValueError(f"delivery channel {channel!r} is not an allowed manual channel")
    return text


def _normalize_optional_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if metadata is None:
        return {}
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be a JSON object")
    return dict(metadata)


@dataclass(frozen=True)
class RevisedDeliveryAcceptance:
    """Immutable, serializable internal acceptance of a Stage 8D revised delivery.

    Identity is derived ONLY from stable semantic inputs (no timestamps / run
    identifiers) so identical semantic acceptance requests always resolve to the
    same acceptance identity and replays are idempotent.
    """

    schema_version: str
    acceptance_id: str
    revision_id: str
    dispatch_id: str
    reconciliation_result_id: str
    original_delivery_id: str
    revised_delivery_id: str
    project_id: str
    correlation_id: str
    reviewer_id: str
    review_started_at: str
    reviewed_at: str
    acceptance_status: str
    accepted_formats: tuple[str, ...]
    rejected_formats: tuple[str, ...]
    quality_gate_reference: str
    artifact_integrity_reference: str
    review_notes: str | None
    rejection_codes: tuple[str, ...]
    evidence_references: tuple[str, ...]
    metadata: dict[str, Any]
    created_at: str

    def __post_init__(self) -> None:
        if self.schema_version != RELEASE_SCHEMA_VERSION:
            raise ValueError("acceptance schema version mismatch")
        if self.acceptance_status not in ALLOWED_ACCEPTANCE_STATUSES:
            raise ValueError(f"invalid acceptance status {self.acceptance_status!r}")
        # Lineage identifiers are safe logical identifiers.
        for field in (
            "acceptance_id",
            "revision_id",
            "dispatch_id",
            "reconciliation_result_id",
            "original_delivery_id",
            "revised_delivery_id",
            "project_id",
            "correlation_id",
            "reviewer_id",
            "quality_gate_reference",
            "artifact_integrity_reference",
        ):
            _safe_id(field, getattr(self, field))
        # Formats are bounded to the canonical target-format allowlist.
        object.__setattr__(
            self,
            "accepted_formats",
            tuple(_require_allowed_format(f) for f in self.accepted_formats),
        )
        object.__setattr__(
            self,
            "rejected_formats",
            tuple(_require_allowed_format(f) for f in self.rejected_formats),
        )
        object.__setattr__(
            self,
            "rejection_codes",
            tuple(str(c).strip() for c in self.rejection_codes if str(c).strip()),
        )
        object.__setattr__(
            self,
            "evidence_references",
            tuple(_safe_optional_id("evidence_reference", e) or "" for e in self.evidence_references if e),
        )
        object.__setattr__(self, "review_notes", _safe_log_text("review_notes", self.review_notes))
        object.__setattr__(self, "metadata", _normalize_optional_metadata(self.metadata))
        # Full acceptance may not carry rejection codes.
        if self.acceptance_status == ACCEPTANCE_ACCEPTED and self.rejection_codes:
            raise ValueError("fully accepted delivery must not carry rejection codes")
        if self.acceptance_status == ACCEPTANCE_REJECTED and not self.rejection_codes:
            raise ValueError("rejected acceptance requires rejection codes")
        # Accepted + rejected format sets must be disjoint.
        accepted = set(self.accepted_formats)
        rejected = set(self.rejected_formats)
        if accepted & rejected:
            raise ValueError("a format cannot be both accepted and rejected")

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["accepted_formats"] = list(self.accepted_formats)
        data["rejected_formats"] = list(self.rejected_formats)
        data["rejection_codes"] = list(self.rejection_codes)
        data["evidence_references"] = list(self.evidence_references)
        data["metadata"] = dict(self.metadata)
        return data


@dataclass(frozen=True)
class CustomerReleaseAuthorization:
    """Immutable authorization evidence permitting release of an accepted revised
    delivery to a customer.

    This is authorization evidence only. It does NOT contact the customer, send
    an email, upload media, publish, or execute any delivery transport. Identity
    is derived ONLY from stable semantic inputs so replay is idempotent.
    """

    schema_version: str
    authorization_id: str
    acceptance_id: str
    revision_id: str
    revised_delivery_id: str
    project_id: str
    correlation_id: str
    authorized_by: str
    authorized_at: str
    authorization_scope: tuple[str, ...]
    approved_formats: tuple[str, ...]
    allowed_delivery_channels: tuple[str, ...]
    customer_reference: str
    expiry_at: str
    approval_basis: str
    policy_version: str
    status: str
    idempotency_key: str
    evidence_references: tuple[str, ...]
    metadata: dict[str, Any]
    created_at: str

    def __post_init__(self) -> None:
        if self.schema_version != RELEASE_SCHEMA_VERSION:
            raise ValueError("authorization schema version mismatch")
        if self.status not in ALLOWED_AUTH_STATUSES:
            raise ValueError(f"invalid authorization status {self.status!r}")
        for field in (
            "authorization_id",
            "acceptance_id",
            "revision_id",
            "revised_delivery_id",
            "project_id",
            "correlation_id",
            "authorized_by",
        ):
            _safe_id(field, getattr(self, field))
        _safe_text("approval_basis", self.approval_basis)
        _safe_text("policy_version", self.policy_version)
        _safe_customer_reference("customer_reference", self.customer_reference)
        object.__setattr__(
            self,
            "authorization_scope",
            tuple(_require_allowed_format(f) for f in self.authorization_scope),
        )
        object.__setattr__(
            self,
            "approved_formats",
            tuple(_require_allowed_format(f) for f in self.approved_formats),
        )
        object.__setattr__(
            self,
            "allowed_delivery_channels",
            tuple(_require_allowed_channel(c) for c in self.allowed_delivery_channels),
        )
        object.__setattr__(
            self,
            "evidence_references",
            tuple(_safe_optional_id("evidence_reference", e) or "" for e in self.evidence_references if e),
        )
        object.__setattr__(self, "metadata", _normalize_optional_metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["authorization_scope"] = list(self.authorization_scope)
        data["approved_formats"] = list(self.approved_formats)
        data["allowed_delivery_channels"] = list(self.allowed_delivery_channels)
        data["evidence_references"] = list(self.evidence_references)
        data["metadata"] = dict(self.metadata)
        return data


@dataclass(frozen=True)
class ReleaseReadinessDecision:
    """Deterministic release-readiness evaluation result (fail-closed)."""

    schema_version: str
    decision_id: str
    release_ready: bool
    revision_id: str
    dispatch_id: str | None
    reconciliation_result_id: str | None
    acceptance_id: str | None
    authorization_id: str | None
    revised_delivery_id: str | None
    original_delivery_id: str | None
    project_id: str | None
    correlation_id: str | None
    reasons: tuple[str, ...]
    evaluated_at: str
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["reasons"] = list(self.reasons)
        data["metadata"] = dict(self.metadata)
        return data


@dataclass(frozen=True)
class FinalRevisionClosure:
    """Immutable final revision closure event binding the complete release
    lineage. Append-only; created exactly once per revision release content."""

    schema_version: str
    closure_id: str
    revision_id: str
    approval_id: str | None
    dispatch_id: str
    reconciliation_result_id: str
    original_delivery_id: str
    revised_delivery_id: str
    acceptance_id: str
    authorization_id: str
    release_ready: bool
    correlation_id: str
    evidence_references: tuple[str, ...]
    closed_at: str
    created_at: str

    def __post_init__(self) -> None:
        if self.schema_version != RELEASE_SCHEMA_VERSION:
            raise ValueError("closure schema version mismatch")
        for field in (
            "closure_id",
            "revision_id",
            "dispatch_id",
            "reconciliation_result_id",
            "original_delivery_id",
            "revised_delivery_id",
            "acceptance_id",
            "authorization_id",
            "correlation_id",
        ):
            _safe_id(field, getattr(self, field))
        object.__setattr__(
            self,
            "evidence_references",
            tuple(_safe_optional_id("evidence_reference", e) or "" for e in self.evidence_references if e),
        )

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["evidence_references"] = list(self.evidence_references)
        return data


@dataclass(frozen=True)
class ReleaseAuditEvent:
    """One append-only Stage 8E lifecycle audit event."""

    schema_version: str
    event_id: str
    event_type: str
    subject_id: str
    operator_id: str
    recorded_at: str
    record: dict[str, Any]

    def __post_init__(self) -> None:
        if self.event_type not in ALLOWED_RELEASE_EVENT_TYPES:
            raise ValueError(f"invalid release event type {self.event_type!r}")

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


# --- Deterministic idempotency builders (no timestamps) ----------------------
def build_acceptance_id(
    *,
    reconciliation_result_id: str,
    revised_delivery_id: str,
    revision_id: str,
    dispatch_id: str,
    original_delivery_id: str,
    accepted_formats: tuple[str, ...],
    rejected_formats: tuple[str, ...],
    reviewer_id: str,
    quality_gate_reference: str,
    artifact_integrity_reference: str,
    acceptance_status: str,
) -> str:
    return _stable_id(
        "scos-hvs-revised-delivery-acceptance",
        {
            "reconciliation_result_id": reconciliation_result_id,
            "revised_delivery_id": revised_delivery_id,
            "revision_id": revision_id,
            "dispatch_id": dispatch_id,
            "original_delivery_id": original_delivery_id,
            "accepted_formats": tuple(sorted(accepted_formats)),
            "rejected_formats": tuple(sorted(rejected_formats)),
            "reviewer_id": reviewer_id,
            "quality_gate_reference": quality_gate_reference,
            "artifact_integrity_reference": artifact_integrity_reference,
            "acceptance_status": acceptance_status,
        },
    )


def build_authorization_id(
    *,
    acceptance_id: str,
    authorization_scope: tuple[str, ...],
    approved_formats: tuple[str, ...],
    allowed_delivery_channels: tuple[str, ...],
    customer_reference: str,
    authorized_by: str,
    approval_basis: str,
    policy_version: str,
) -> str:
    return _stable_id(
        "scos-hvs-customer-release-authorization",
        {
            "acceptance_id": acceptance_id,
            "authorization_scope": tuple(sorted(authorization_scope)),
            "approved_formats": tuple(sorted(approved_formats)),
            "allowed_delivery_channels": tuple(sorted(allowed_delivery_channels)),
            "customer_reference": customer_reference,
            "authorized_by": authorized_by,
            "approval_basis": approval_basis,
            "policy_version": policy_version,
        },
    )


def build_authorization_idempotency_key(
    *,
    acceptance_id: str,
    authorization_scope: tuple[str, ...],
    approved_formats: tuple[str, ...],
    allowed_delivery_channels: tuple[str, ...],
    customer_reference: str,
    authorized_by: str,
    approval_basis: str,
    policy_version: str,
) -> str:
    return _stable_id(
        "scos-hvs-customer-release-authorization-idem",
        {
            "acceptance_id": acceptance_id,
            "authorization_scope": tuple(sorted(authorization_scope)),
            "approved_formats": tuple(sorted(approved_formats)),
            "allowed_delivery_channels": tuple(sorted(allowed_delivery_channels)),
            "customer_reference": customer_reference,
            "authorized_by": authorized_by,
            "approval_basis": approval_basis,
            "policy_version": policy_version,
        },
    )


def build_readiness_id(*, acceptance_id: str, authorization_id: str | None) -> str:
    return _stable_id(
        "scos-hvs-release-readiness",
        {"acceptance_id": acceptance_id, "authorization_id": authorization_id or ""},
    )


def build_closure_id(
    *,
    revision_id: str,
    acceptance_id: str,
    authorization_id: str,
    reconciliation_result_id: str,
) -> str:
    return _stable_id(
        "scos-hvs-final-revision-closure",
        {
            "revision_id": revision_id,
            "acceptance_id": acceptance_id,
            "authorization_id": authorization_id,
            "reconciliation_result_id": reconciliation_result_id,
        },
    )
