"""Stage 8F manual release execution, customer receipt confirmation, and
post-delivery audit closure contracts; evidence recording only, no customer
contact, no outbound transport, no HVS execution.

This module defines the SCOS-side immutable, deterministic models for the
*final* phase of the SCOS–HVS integration: recording that an authorized
revised delivery was released to the customer through a manual channel,
recording that the customer confirmed receipt, and closing the post-delivery
audit.

Design reuses the canonical contracts of adjacent stages:

  * ``_safe_id`` / ``_safe_optional_id`` / ``ALLOWED_TARGET_FORMATS`` from the
    Stage 8C dispatch models (identical safe-logical-identifier policy)
  * ``ALLOWED_DELIVERY_CHANNELS`` from the Stage 6 local-delivery models
    (canonical outbound channel allowlist)
  * the deterministic sha256-prefixed id style (no time / random)
  * frozen dataclasses, canonical JSON serialization, append-only audit events
  * Stage 8E release evidence (acceptance / authorization / final closure) as
    the authoritative gating lineage

Stage 8F deliberately does NOT import or invoke HVS, does NOT render media, does
NOT create a second delivery-version / revision / dispatch / reconciliation /
approval / audit subsystem, and performs NO customer contact or delivery
transport. It constructs internal manual-release, receipt, and audit-closure
evidence only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

# Reuse the Stage 8C safe-id policy and the bounded target-format allowlist so
# the 8F vocabulary shares one source of truth with adjacent stages.
from .hvs_rerender_dispatch_models import (  # noqa: F401
    ALLOWED_TARGET_FORMATS,
    _safe_id,
    _safe_optional_id,
)
# Reuse the canonical Stage 6 manual delivery-channel allowlist so 8F can only
# record releases through channels the repository already governs.
from .hvs_local_delivery_models import (  # noqa: F401
    ALLOWED_DELIVERY_CHANNELS,
)

POST_DELIVERY_SCHEMA_VERSION = "scos-hvs.post-delivery.v1/1.0.0"
POST_DELIVERY_EVENT_SCHEMA_VERSION = "scos-hvs.post-delivery-event.v1/1.0.0"

# --- Manual release execution status (Stage 8F state machine) ---------------
RELEASE_EXEC_PENDING = "PENDING"
RELEASE_EXEC_RECORDED = "RECORDED"
RELEASE_EXEC_FAILED = "FAILED"
RELEASE_EXEC_CANCELLED = "CANCELLED"
ALLOWED_RELEASE_EXEC_STATUSES = (
    RELEASE_EXEC_PENDING,
    RELEASE_EXEC_RECORDED,
    RELEASE_EXEC_FAILED,
    RELEASE_EXEC_CANCELLED,
)

# --- Customer receipt confirmation status (Stage 8F state machine) ----------
RECEIPT_PENDING = "PENDING"
RECEIPT_CONFIRMED = "CONFIRMED"
RECEIPT_DECLINED = "DECLINED"
RECEIPT_UNREACHABLE = "UNREACHABLE"
ALLOWED_RECEIPT_STATUSES = (
    RECEIPT_PENDING,
    RECEIPT_CONFIRMED,
    RECEIPT_DECLINED,
    RECEIPT_UNREACHABLE,
)

# --- Post-delivery audit status (Stage 8F state machine) --------------------
AUDIT_OPEN = "OPEN"
AUDIT_READY = "READY"
AUDIT_CLOSED = "CLOSED"
AUDIT_REJECTED = "REJECTED"
ALLOWED_AUDIT_STATUSES = (
    AUDIT_OPEN,
    AUDIT_READY,
    AUDIT_CLOSED,
    AUDIT_REJECTED,
)

# --- Append-only Stage 8F lifecycle audit event types -----------------------
EVT_MANUAL_RELEASE_RECORDED = "MANUAL_RELEASE_RECORDED"
EVT_MANUAL_RELEASE_REJECTED = "MANUAL_RELEASE_REJECTED"
EVT_CUSTOMER_RECEIPT_CONFIRMED = "CUSTOMER_RECEIPT_CONFIRMED"
EVT_CUSTOMER_RECEIPT_REJECTED = "CUSTOMER_RECEIPT_REJECTED"
EVT_POST_DELIVERY_AUDIT_EVALUATED = "POST_DELIVERY_AUDIT_EVALUATED"
EVT_POST_DELIVERY_AUDIT_REJECTED = "POST_DELIVERY_AUDIT_REJECTED"
EVT_POST_DELIVERY_AUDIT_CLOSED = "POST_DELIVERY_AUDIT_CLOSED"
EVT_DUPLICATE_REQUEST_DETECTED = "DUPLICATE_REQUEST_DETECTED"
EVT_CONFLICTING_REQUEST_REJECTED = "CONFLICTING_REQUEST_REJECTED"
ALLOWED_POST_DELIVERY_EVENT_TYPES = (
    EVT_MANUAL_RELEASE_RECORDED,
    EVT_MANUAL_RELEASE_REJECTED,
    EVT_CUSTOMER_RECEIPT_CONFIRMED,
    EVT_CUSTOMER_RECEIPT_REJECTED,
    EVT_POST_DELIVERY_AUDIT_EVALUATED,
    EVT_POST_DELIVERY_AUDIT_REJECTED,
    EVT_POST_DELIVERY_AUDIT_CLOSED,
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
    content silently — it raises ``ValueError`` so the service fails closed.
    """
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} must be a non-empty safe reference")
    lowered = text.lower()
    for token in _UNSAFE_TEXT_TOKENS:
        if token in lowered:
            raise ValueError(f"{field} must be a safe reference (rejected token {token!r})")
    return text


def _safe_text(field: str, value: Any) -> str:
    """Validate free-text fields (allow slashes/dots, reject CR/LF/null and
    path-traversal fragments)."""
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} must be a non-empty reference")
    lowered = text.lower()
    for token in ("..", "\\", "://", "\n", "\r", "\x00"):
        if token in lowered:
            raise ValueError(f"{field} contains an unsafe fragment (rejected token {token!r})")
    return text


def _safe_log_text(field: str, value: Any | None) -> str | None:
    """Validate free-text content as log-injection-safe (no CR/LF/null)."""
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
class ManualReleaseExecution:
    """Immutable record that an authorized revised delivery was released to the
    customer through a manual channel.

    This is **evidence recording only**. Stage 8F does NOT perform the release,
    contact the customer, send an email, upload media, publish, or execute any
    delivery transport. It records that the operator performed the manual
    release against an existing Stage 8E authorization. Identity is derived ONLY
    from stable semantic inputs so replay is idempotent.
    """

    schema_version: str
    release_id: str
    authorization_id: str
    acceptance_id: str
    revision_id: str
    revised_delivery_id: str
    original_delivery_id: str
    project_id: str
    correlation_id: str
    released_by: str
    released_at: str
    release_channel: str
    released_formats: tuple[str, ...]
    customer_reference: str
    release_method_reference: str
    status: str
    idempotency_key: str
    evidence_references: tuple[str, ...]
    metadata: dict[str, Any]
    created_at: str

    def __post_init__(self) -> None:
        if self.schema_version != POST_DELIVERY_SCHEMA_VERSION:
            raise ValueError("release schema version mismatch")
        if self.status not in ALLOWED_RELEASE_EXEC_STATUSES:
            raise ValueError(f"invalid release status {self.status!r}")
        for field in (
            "release_id",
            "authorization_id",
            "acceptance_id",
            "revision_id",
            "revised_delivery_id",
            "original_delivery_id",
            "project_id",
            "correlation_id",
            "released_by",
            "release_method_reference",
        ):
            _safe_id(field, getattr(self, field))
        _safe_customer_reference("customer_reference", self.customer_reference)
        _safe_text("release_method_reference", self.release_method_reference)
        object.__setattr__(self, "release_channel", _require_allowed_channel(self.release_channel))
        object.__setattr__(
            self,
            "released_formats",
            tuple(_require_allowed_format(f) for f in self.released_formats),
        )
        object.__setattr__(
            self,
            "evidence_references",
            tuple(_safe_optional_id("evidence_reference", e) or "" for e in self.evidence_references if e),
        )
        object.__setattr__(self, "metadata", _normalize_optional_metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["released_formats"] = list(self.released_formats)
        data["evidence_references"] = list(self.evidence_references)
        data["metadata"] = dict(self.metadata)
        return data


@dataclass(frozen=True)
class CustomerReceiptConfirmation:
    """Immutable record that the customer confirmed receipt of the released
    revised delivery.

    This is **evidence recording only**. Stage 8F does NOT contact the customer,
    send a message, or invoke any transport. It records that a receipt
    confirmation was observed (e.g. a manual operator entry or a logged inbound
    acknowledgment). Identity is derived ONLY from stable semantic inputs.
    """

    schema_version: str
    receipt_id: str
    release_id: str
    authorization_id: str
    acceptance_id: str
    revision_id: str
    revised_delivery_id: str
    project_id: str
    correlation_id: str
    customer_reference: str
    confirmed_by: str
    confirmed_at: str
    receipt_status: str
    received_formats: tuple[str, ...]
    receipt_channel: str | None
    confirmation_reference: str
    receipt_notes: str | None
    evidence_references: tuple[str, ...]
    metadata: dict[str, Any]
    created_at: str

    def __post_init__(self) -> None:
        if self.schema_version != POST_DELIVERY_SCHEMA_VERSION:
            raise ValueError("receipt schema version mismatch")
        if self.receipt_status not in ALLOWED_RECEIPT_STATUSES:
            raise ValueError(f"invalid receipt status {self.receipt_status!r}")
        for field in (
            "receipt_id",
            "release_id",
            "authorization_id",
            "acceptance_id",
            "revision_id",
            "revised_delivery_id",
            "project_id",
            "correlation_id",
            "confirmed_by",
            "confirmation_reference",
        ):
            _safe_id(field, getattr(self, field))
        _safe_customer_reference("customer_reference", self.customer_reference)
        _safe_text("confirmation_reference", self.confirmation_reference)
        object.__setattr__(
            self,
            "received_formats",
            tuple(_require_allowed_format(f) for f in self.received_formats),
        )
        if self.receipt_channel is not None:
            object.__setattr__(self, "receipt_channel", _require_allowed_channel(self.receipt_channel))
        object.__setattr__(self, "receipt_notes", _safe_log_text("receipt_notes", self.receipt_notes))
        object.__setattr__(
            self,
            "evidence_references",
            tuple(_safe_optional_id("evidence_reference", e) or "" for e in self.evidence_references if e),
        )
        object.__setattr__(self, "metadata", _normalize_optional_metadata(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["received_formats"] = list(self.received_formats)
        data["evidence_references"] = list(self.evidence_references)
        data["metadata"] = dict(self.metadata)
        return data


@dataclass(frozen=True)
class PostDeliveryAuditClosure:
    """Immutable post-delivery audit readiness evaluation and closure event.

    Binds the complete post-delivery lineage: authorization, acceptance,
    revision, dispatch, reconciliation, deliveries, release execution, and
    receipt confirmation. Append-only; created exactly once per audit content.
    """

    schema_version: str
    audit_id: str
    release_id: str | None
    receipt_id: str | None
    authorization_id: str
    acceptance_id: str
    revision_id: str
    dispatch_id: str | None
    reconciliation_result_id: str | None
    original_delivery_id: str
    revised_delivery_id: str
    project_id: str
    correlation_id: str
    audit_ready: bool
    closure_decision: str
    reasons: tuple[str, ...]
    evidence_references: tuple[str, ...]
    closed_by: str
    closed_at: str
    created_at: str

    def __post_init__(self) -> None:
        if self.schema_version != POST_DELIVERY_SCHEMA_VERSION:
            raise ValueError("audit schema version mismatch")
        if self.closure_decision not in ALLOWED_AUDIT_STATUSES:
            raise ValueError(f"invalid audit closure decision {self.closure_decision!r}")
        for field in (
            "audit_id",
            "release_id",
            "receipt_id",
            "authorization_id",
            "acceptance_id",
            "revision_id",
            "dispatch_id",
            "reconciliation_result_id",
            "original_delivery_id",
            "revised_delivery_id",
            "project_id",
            "correlation_id",
            "closed_by",
        ):
            _safe_optional_id(field, getattr(self, field))
        object.__setattr__(
            self,
            "reasons",
            tuple(str(r).strip() for r in self.reasons if str(r).strip()),
        )
        object.__setattr__(
            self,
            "evidence_references",
            tuple(_safe_optional_id("evidence_reference", e) or "" for e in self.evidence_references if e),
        )

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["reasons"] = list(self.reasons)
        data["evidence_references"] = list(self.evidence_references)
        return data


@dataclass(frozen=True)
class PostDeliveryAuditEvent:
    """One append-only Stage 8F lifecycle audit event."""

    schema_version: str
    event_id: str
    event_type: str
    subject_id: str
    operator_id: str
    recorded_at: str
    record: dict[str, Any]

    def __post_init__(self) -> None:
        if self.event_type not in ALLOWED_POST_DELIVERY_EVENT_TYPES:
            raise ValueError(f"invalid post-delivery event type {self.event_type!r}")

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


# --- Deterministic idempotency builders (no timestamps) ----------------------
def build_release_id(
    *,
    authorization_id: str,
    acceptance_id: str,
    revision_id: str,
    revised_delivery_id: str,
    original_delivery_id: str,
    released_formats: tuple[str, ...],
    release_channel: str,
    customer_reference: str,
    release_method_reference: str,
) -> str:
    return _stable_id(
        "scos-hvs-manual-release",
        {
            "authorization_id": authorization_id,
            "acceptance_id": acceptance_id,
            "revision_id": revision_id,
            "revised_delivery_id": revised_delivery_id,
            "original_delivery_id": original_delivery_id,
            "released_formats": tuple(sorted(released_formats)),
            "release_channel": release_channel,
            "customer_reference": customer_reference,
            "release_method_reference": release_method_reference,
        },
    )


def build_release_idempotency_key(
    *,
    release_id: str,
    authorization_id: str,
    acceptance_id: str,
    revision_id: str,
    revised_delivery_id: str,
    original_delivery_id: str,
    project_id: str,
    correlation_id: str,
    released_formats: tuple[str, ...],
    release_channel: str,
    customer_reference: str,
    status: str,
) -> str:
    return _stable_id(
        "scos-hvs-manual-release-ik",
        {
            "release_id": release_id,
            "authorization_id": authorization_id,
            "acceptance_id": acceptance_id,
            "revision_id": revision_id,
            "revised_delivery_id": revised_delivery_id,
            "original_delivery_id": original_delivery_id,
            "project_id": project_id,
            "correlation_id": correlation_id,
            "released_formats": tuple(sorted(released_formats)),
            "release_channel": release_channel,
            "customer_reference": customer_reference,
            "status": status,
        },
    )


def build_receipt_id(
    *,
    release_id: str,
    authorization_id: str,
    acceptance_id: str,
    revision_id: str,
    revised_delivery_id: str,
    received_formats: tuple[str, ...],
    receipt_status: str,
    customer_reference: str,
) -> str:
    return _stable_id(
        "scos-hvs-customer-receipt",
        {
            "release_id": release_id,
            "authorization_id": authorization_id,
            "acceptance_id": acceptance_id,
            "revision_id": revision_id,
            "revised_delivery_id": revised_delivery_id,
            "received_formats": tuple(sorted(received_formats)),
            "receipt_status": receipt_status,
            "customer_reference": customer_reference,
        },
    )


def build_audit_id(
    *,
    release_id: str | None,
    receipt_id: str | None,
    authorization_id: str,
    acceptance_id: str,
    revision_id: str,
    dispatch_id: str | None,
    reconciliation_result_id: str | None,
    original_delivery_id: str,
    revised_delivery_id: str,
    project_id: str,
    correlation_id: str,
    audit_ready: bool,
    closure_decision: str,
) -> str:
    return _stable_id(
        "scos-hvs-post-delivery-audit",
        {
            "release_id": release_id,
            "receipt_id": receipt_id,
            "authorization_id": authorization_id,
            "acceptance_id": acceptance_id,
            "revision_id": revision_id,
            "dispatch_id": dispatch_id,
            "reconciliation_result_id": reconciliation_result_id,
            "original_delivery_id": original_delivery_id,
            "revised_delivery_id": revised_delivery_id,
            "project_id": project_id,
            "correlation_id": correlation_id,
            "audit_ready": audit_ready,
            "closure_decision": closure_decision,
        },
    )


def build_event_id(*, event_type: str, subject_id: str, record: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"event_type": event_type, "subject_id": subject_id, "record": record},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"scos-hvs-post-delivery-evt-{_sha256_hex(canonical)[:16]}"
