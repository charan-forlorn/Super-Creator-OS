"""Stage 8C immutable re-render dispatch request contract; no HVS execution.

This module defines the SCOS-side immutable model for an approval-gated
revision re-render dispatch request. It converts an APPROVED Stage 8B revision
into a deterministic, serializable dispatch request that preserves complete
lineage between:

  * original delivery (delivery_record_id / lineage)
  * revision request (revision_request_id)
  * approval decision (approval_decision_id)
  * re-render authorization (rerender_authorization_id)
  * this re-render dispatch request (dispatch_id)
  * the resulting dispatch result (populated by the dispatch store / service)

The Stage 8C flow deliberately stops at the established manual HVS operator
boundary. Stage 8B's ``RerenderAuthorizationPacket`` carries
``manual_dispatch_required=True`` / ``automation_allowed=False``; the canonical
revision re-render path is therefore the manual HVS handoff, NOT the Stage 5
automated render. Stage 8C constructs and validates the dispatch request,
persists SCOS-side lineage + append-only audit evidence, and never invokes HVS.

Design mirrors Stage 8B / Stage 8A.1 conventions:

  * frozen dataclasses, deterministic sha256-prefixed ids (no time / random)
  * safe logical identifier validation (no path / shell / URL fragments)
  * no secrets, no media paths, no network, no subprocess
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

RERENDER_DISPATCH_SCHEMA_VERSION = "scos-hvs.rerender-dispatch.v1/1.0.0"
RERENDER_DISPATCH_EVENT_SCHEMA_VERSION = "scos-hvs.rerender-dispatch-event.v1/1.0.0"

# --- Re-render dispatch status (Stage 8C state machine) ----------------------
DISPATCH_REQUESTED = "RERENDER_DISPATCH_REQUESTED"
DISPATCH_REJECTED = "RERENDER_DISPATCH_REJECTED"
DISPATCH_READY = "RERENDER_DISPATCH_READY"
DISPATCH_CREATED = "RERENDER_DISPATCH_CREATED"
DISPATCH_FAILED = "RERENDER_DISPATCH_FAILED"
DISPATCH_COMPLETED = "RERENDER_DISPATCH_COMPLETED"
DISPATCH_DUPLICATE = "RERENDER_DISPATCH_DUPLICATE"
ALLOWED_DISPATCH_STATUSES = (
    DISPATCH_REQUESTED,
    DISPATCH_REJECTED,
    DISPATCH_READY,
    DISPATCH_CREATED,
    DISPATCH_FAILED,
    DISPATCH_COMPLETED,
    DISPATCH_DUPLICATE,
)

# --- Revision-side source states Stage 8C depends on -------------------------
REVISION_APPROVED = "APPROVED_FOR_RERENDER_PLANNING"
REVISION_CANCELLED = "CANCELLED"
REVISION_SUPERSEDED = "SUPERSEDED"

# --- Allowed target delivery-variant / format tokens -------------------------
ALLOWED_TARGET_FORMATS = (
    "vertical",
    "square",
    "horizontal",
    "captions",
    "thumbnail",
    "raw_master",
)
# Requested changes categories are bounded to Stage 8B item categories.
ALLOWED_CHANGE_CATEGORIES = (
    "TEXT_CHANGE",
    "CAPTION_CHANGE",
    "TIMING_CHANGE",
    "ASSET_REPLACEMENT",
    "AUDIO_CHANGE",
    "MUSIC_CHANGE",
    "VOICE_CHANGE",
    "LAYOUT_CHANGE",
    "BRANDING_CHANGE",
    "FORMAT_CHANGE",
    "DURATION_CHANGE",
    "COMPLIANCE_CHANGE",
    "TECHNICAL_CORRECTION",
)

# --- Append-only audit event types (Stage 8C lifecycle) ----------------------
EVT_RERENDER_DISPATCH_REQUESTED = "RERENDER_DISPATCH_REQUESTED"
EVT_RERENDER_DISPATCH_REJECTED = "RERENDER_DISPATCH_REJECTED"
EVT_RERENDER_DISPATCH_APPROVED = "RERENDER_DISPATCH_APPROVED"
EVT_RERENDER_DISPATCH_CREATED = "RERENDER_DISPATCH_CREATED"
EVT_RERENDER_DISPATCH_DUPLICATE = "RERENDER_DISPATCH_DUPLICATE"
EVT_RERENDER_DISPATCH_FAILED = "RERENDER_DISPATCH_FAILED"
EVT_RERENDER_DISPATCH_COMPLETED = "RERENDER_DISPATCH_COMPLETED"
ALLOWED_RERENDER_DISPATCH_EVENT_TYPES = (
    EVT_RERENDER_DISPATCH_REQUESTED,
    EVT_RERENDER_DISPATCH_REJECTED,
    EVT_RERENDER_DISPATCH_APPROVED,
    EVT_RERENDER_DISPATCH_CREATED,
    EVT_RERENDER_DISPATCH_DUPLICATE,
    EVT_RERENDER_DISPATCH_FAILED,
    EVT_RERENDER_DISPATCH_COMPLETED,
)

# Tokens that must never appear in a safe logical identifier (path / shell /
# URL / injection fragments). Mirrors Stage 8B ``_safe_id`` policy.
_UNSAFE_IDENTIFIER_TOKENS = ("..", "\\", "/", "://", ";", "|", "$", "`")


def _safe_id(field: str, value: Any) -> str:
    """Validate a safe logical identifier (project / delivery / revision id).

    Rejects empty values and any path / shell / URL fragment. Never raises on
    presence of attacker-controlled content silently — it raises ``ValueError``
    so the service can fail closed.
    """
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} must be a non-empty safe logical identifier")
    lowered = text.lower()
    for token in _UNSAFE_IDENTIFIER_TOKENS:
        if token in lowered:
            raise ValueError(
                f"{field} must be a safe logical identifier (rejected token {token!r})"
            )
    return text


def _safe_optional_id(field: str, value: Any | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return _safe_id(field, text)


def _safe_format(value: str) -> str:
    text = str(value or "").strip().lower()
    if text not in ALLOWED_TARGET_FORMATS:
        raise ValueError(f"target format {value!r} is not an allowed delivery variant")
    return text


def _sha256_hex(value: Any) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _stable_id(prefix: str, payload: dict[str, Any]) -> str:
    return f"{prefix}-{_sha256_hex(payload)[:16]}"


@dataclass(frozen=True)
class RequestedChange:
    """One bounded requested change carried into the re-render dispatch."""

    change_id: str
    category: str
    description: str
    target_format: str | None
    target_id: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "category", str(self.category).strip().upper())
        if self.category not in ALLOWED_CHANGE_CATEGORIES:
            raise ValueError(f"requested change category {self.category!r} is not allowed")
        if not str(self.description or "").strip():
            raise ValueError("requested change description is required")
        object.__setattr__(
            self, "target_format", _safe_optional_id("target_format", self.target_format)
        )
        object.__setattr__(self, "target_id", _safe_optional_id("target_id", self.target_id))
        object.__setattr__(
            self,
            "change_id",
            _stable_id(
                "scos-hvs-rerender-change",
                {
                    "category": self.category,
                    "description": str(self.description).strip(),
                    "target_format": self.target_format,
                    "target_id": self.target_id,
                },
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class RerenderDispatchRequest:
    """Immutable, serializable approved-revision re-render dispatch request.

    Binds the complete lineage from original delivery through approval to this
    re-render dispatch request. The ``idempotency_key`` is derived ONLY from
    stable semantic inputs (no timestamps / run identifiers) so identical
    semantic requests always resolve to the same dispatch identity.
    """

    schema_version: str
    dispatch_id: str
    revision_id: str
    delivery_id: str
    original_render_request_id: str | None
    original_correlation_id: str | None
    project_id: str
    requested_by: str
    approved_by: str
    approval_id: str
    approval_decision_id: str
    approval_timestamp: str
    requested_changes: tuple[RequestedChange, ...]
    target_formats: tuple[str, ...]
    reason: str
    created_at: str
    correlation_id: str
    idempotency_key: str
    status: str
    metadata: dict[str, Any]

    def __post_init__(self) -> None:
        if self.status not in ALLOWED_DISPATCH_STATUSES:
            raise ValueError(f"invalid dispatch status {self.status!r}")
        if self.schema_version != RERENDER_DISPATCH_SCHEMA_VERSION:
            raise ValueError("dispatch schema version mismatch")

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["requested_changes"] = [c.to_dict() for c in self.requested_changes]
        return data


@dataclass(frozen=True)
class RerenderDispatchAuditEvent:
    """One append-only Stage 8C lifecycle audit event."""

    schema_version: str
    event_id: str
    event_type: str
    dispatch_id: str
    operator_id: str
    recorded_at: str
    record: dict[str, Any]

    def __post_init__(self) -> None:
        if self.event_type not in ALLOWED_RERENDER_DISPATCH_EVENT_TYPES:
            raise ValueError(f"invalid re-render dispatch event type {self.event_type!r}")

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def build_idempotency_key(
    *,
    revision_id: str,
    delivery_id: str,
    approval_decision_id: str,
    target_formats: tuple[str, ...],
    change_fingerprint: str,
) -> str:
    """Deterministic idempotency identity from stable semantic inputs only.

    Excludes timestamps, run identifiers, dispatch ids, and operator ids so
    that replaying the same approved semantic request yields the same key.
    """
    return _stable_id(
        "scos-hvs-rerender-idem",
        {
            "revision_id": revision_id,
            "delivery_id": delivery_id,
            "approval_decision_id": approval_decision_id,
            "target_formats": tuple(sorted(target_formats)),
            "change_fingerprint": change_fingerprint,
        },
    )


def change_fingerprint(changes: tuple[RequestedChange, ...]) -> str:
    return _sha256_hex(
        sorted(
            (c.category, str(c.description).strip(), c.target_format, c.target_id)
            for c in changes
        )
    )


def dispatch_id_for(idempotency_key: str) -> str:
    return _stable_id("scos-hvs-rerender-dispatch", {"idem": idempotency_key})


def safe_decimal_text(value: Any | None) -> str | None:
    """Return a canonical decimal string or None (no float drift)."""
    if value is None or str(value).strip() == "":
        return None
    try:
        return str(Decimal(str(value)))
    except (Decimal.InvalidOperation, ValueError, TypeError):
        return None
