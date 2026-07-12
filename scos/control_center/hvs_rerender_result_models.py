"""Stage 8D immutable re-render result + reconciliation contract; no HVS execution.

This module defines the SCOS-side immutable model for the *result* of a Stage
8C approved re-render dispatch. Stage 8C is the manual HVS handoff boundary;
the re-rendered artifact is produced by a human operator (or a later approved
automation) outside SCOS. Stage 8D consumes the resulting evidence contract and
deterministically reconciles it into the SCOS delivery + revision lineage.

The contract reuses Stage 8C policy vocabulary where possible:

  * safe logical identifier validation (no path / shell / URL fragments)
  * the same bounded target-format allowlist (``ALLOWED_TARGET_FORMATS``)
  * frozen dataclasses, deterministic sha256-prefixed ids (no time / random)
  * no secrets, no media paths, no network, no subprocess

Stage 8D deliberately does NOT import or invoke HVS, does NOT render media, and
does NOT create a second delivery-version subsystem (it delegates the revised
delivery version to the existing Stage 8A.1 lineage registration).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

# Reuse Stage 8C safe-id policy and the bounded target-format allowlist so the
# two adjacent stages share an identical lineage / format vocabulary.
from .hvs_rerender_dispatch_models import (  # noqa: F401
    ALLOWED_TARGET_FORMATS,
    REVISION_SUPERSEDED,  # re-exported so downstream gate/tests reuse one source
    _safe_id,
)
# Reuse Stage 8A.1 delivery-version lineage vocabulary for the revised-delivery
# identity so the successor version is deterministic and consistent with the
# canonical delivery-version subsystem (no second subsystem is created).
from .hvs_delivery_lineage_models import (  # noqa: F401
    SUPERSESSION_NOT_YET_SUPERSEDED,
    SUPERSESSION_SUPERSEDED,
    DeliveryVersion,
    stable_artifact_id,
)

RERENDER_RESULT_SCHEMA_VERSION = "scos-hvs.rerender-result.v1/1.0.0"
RERENDER_RESULT_EVENT_SCHEMA_VERSION = "scos-hvs.rerender-result-event.v1/1.0.0"

# --- Re-render result terminal status ---------------------------------------
RERENDER_RESULT_SUCCEEDED = "SUCCEEDED"
RERENDER_RESULT_FAILED = "FAILED"
ALLOWED_RERENDER_RESULT_STATUSES = (RERENDER_RESULT_SUCCEEDED, RERENDER_RESULT_FAILED)

# --- Failure retryability -----------------------------------------------------
RERENDER_RESULT_RETRYABLE = "RETRYABLE"
RERENDER_RESULT_TERMINAL = "TERMINAL"
ALLOWED_RERENDER_RESULT_RETRYABILITY = (
    RERENDER_RESULT_RETRYABLE,
    RERENDER_RESULT_TERMINAL,
)

# --- Result-acceptable dispatch state (Stage 8C lifecycle) --------------------
# A re-render result may only be reconciled against a dispatch that is still
# awaiting its result. A dispatch that has already been completed/rejected/
# duplicated/failed is terminal and must not receive a conflicting new result.
RERENDER_DISPATCH_RESULT_ACCEPTABLE = "RERENDER_DISPATCH_CREATED"

# --- Append-only reconciliation audit event types (Stage 8D lifecycle) --------
EVT_RERENDER_RESULT_RECEIVED = "RERENDER_RESULT_RECEIVED"
EVT_RERENDER_RESULT_REJECTED = "RERENDER_RESULT_REJECTED"
EVT_RERENDER_RESULT_ACCEPTED = "RERENDER_RESULT_ACCEPTED"
EVT_REVISED_DELIVERY_CREATED = "REVISED_DELIVERY_CREATED"
EVT_DELIVERY_SUPERSEDED = "DELIVERY_SUPERSEDED"
EVT_REVISION_COMPLETED = "REVISION_COMPLETED"
EVT_RERENDER_FAILED = "RERENDER_FAILED"
EVT_RECONCILIATION_DUPLICATE = "RECONCILIATION_DUPLICATE"
EVT_RECONCILIATION_CONFLICT = "RECONCILIATION_CONFLICT"
ALLOWED_RERENDER_RESULT_EVENT_TYPES = (
    EVT_RERENDER_RESULT_RECEIVED,
    EVT_RERENDER_RESULT_REJECTED,
    EVT_RERENDER_RESULT_ACCEPTED,
    EVT_REVISED_DELIVERY_CREATED,
    EVT_DELIVERY_SUPERSEDED,
    EVT_REVISION_COMPLETED,
    EVT_RERENDER_FAILED,
    EVT_RECONCILIATION_DUPLICATE,
    EVT_RECONCILIATION_CONFLICT,
)


def _sha256_hex(value: Any) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _stable_id(prefix: str, payload: dict[str, Any]) -> str:
    return f"{prefix}-{_sha256_hex(payload)[:16]}"


def _safe_optional_id(field: str, value: Any | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return _safe_id(field, text)


def _safe_evidence_reference(field: str, value: Any | None) -> str | None:
    """Validate an evidence reference as a safe logical identifier or None.

    Evidence references are opaque SCOS lineage / checksum references (e.g. a
    lineage id, a sha256 fingerprint label, or a bounded local evidence file
    name). They must never contain path / shell / URL fragments.
    """
    return _safe_optional_id(field, value)


def _safe_artifact_reference(field: str, value: Any) -> str:
    """Validate an artifact reference as a safe logical identifier.

    Rejects empty values and any path / shell / URL fragment so a malicious
    result cannot smuggle a filesystem or network reference into the lineage.
    """
    return _safe_id(field, value)


def _require_allowed_format(fmt: str) -> str:
    text = str(fmt or "").strip().lower()
    if text not in ALLOWED_TARGET_FORMATS:
        raise ValueError(f"output format {fmt!r} is not an allowed delivery variant")
    return text


@dataclass(frozen=True)
class RerenderResult:
    """Immutable, serializable result of a Stage 8C re-render dispatch.

    Binds the full lineage from the original delivery through the revision and
    the approved dispatch to this externally-produced re-render result. The
    ``idempotency_key`` is derived ONLY from stable semantic inputs (no
    timestamps / run identifiers) so identical semantic results always resolve
    to the same reconciliation identity.
    """

    schema_version: str
    result_id: str
    dispatch_id: str
    revision_id: str
    original_delivery_id: str
    original_render_request_id: str | None
    new_render_request_id: str | None
    project_id: str
    correlation_id: str
    idempotency_key: str
    status: str
    completed_at: str
    artifact_references: tuple[str, ...]
    output_formats: tuple[str, ...]
    checksums: dict[str, str]
    renderer_metadata: dict[str, Any]
    failure_code: str | None
    failure_reason: str | None
    retryability: str | None
    evidence_references: tuple[str, ...]
    created_at: str

    def __post_init__(self) -> None:
        if self.schema_version != RERENDER_RESULT_SCHEMA_VERSION:
            raise ValueError("result schema version mismatch")
        if self.status not in ALLOWED_RERENDER_RESULT_STATUSES:
            raise ValueError(f"invalid re-render result status {self.status!r}")
        # Lineage identifiers are safe logical identifiers.
        for field in (
            "result_id",
            "dispatch_id",
            "revision_id",
            "original_delivery_id",
            "project_id",
            "correlation_id",
        ):
            _safe_id(field, getattr(self, field))
        _safe_optional_id("original_render_request_id", self.original_render_request_id)
        _safe_optional_id("new_render_request_id", self.new_render_request_id)
        # Output formats must be a bounded, non-empty allowlist subset.
        if not self.output_formats:
            raise ValueError("at least one output format is required")
        normalized_formats = tuple(_require_allowed_format(f) for f in self.output_formats)
        object.__setattr__(self, "output_formats", normalized_formats)
        # Artifact references must be syntactically safe.
        if not self.artifact_references:
            raise ValueError("at least one artifact reference is required")
        object.__setattr__(
            self,
            "artifact_references",
            tuple(_safe_artifact_reference("artifact_reference", a) for a in self.artifact_references),
        )
        # Evidence references are opaque safe identifiers or None.
        object.__setattr__(
            self,
            "evidence_references",
            tuple(_safe_evidence_reference("evidence_reference", e) for e in self.evidence_references),
        )
        # Success / failure internal consistency.
        if self.status == RERENDER_RESULT_SUCCEEDED:
            if self.failure_code is not None or self.failure_reason is not None:
                raise ValueError("successful result must not carry failure fields")
            if self.retryability is not None:
                raise ValueError("successful result must not carry retryability")
            # Required integrity evidence: at least one checksum/artifact hash.
            if not self.checksums:
                raise ValueError("successful result requires integrity evidence (checksums)")
        elif self.status == RERENDER_RESULT_FAILED:
            if not self.failure_code:
                raise ValueError("failed result requires a failure_code")
            if not self.failure_reason:
                raise ValueError("failed result requires a failure_reason")
            if self.retryability is not None and self.retryability not in ALLOWED_RERENDER_RESULT_RETRYABILITY:
                raise ValueError(f"invalid retryability {self.retryability!r}")

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["artifact_references"] = list(self.artifact_references)
        data["output_formats"] = list(self.output_formats)
        data["evidence_references"] = list(self.evidence_references)
        data["checksums"] = dict(self.checksums)
        data["renderer_metadata"] = dict(self.renderer_metadata)
        return data


@dataclass(frozen=True)
class RerenderResultAuditEvent:
    """One append-only Stage 8D reconciliation lifecycle audit event."""

    schema_version: str
    event_id: str
    event_type: str
    result_id: str
    dispatch_id: str
    operator_id: str
    recorded_at: str
    record: dict[str, Any]

    def __post_init__(self) -> None:
        if self.event_type not in ALLOWED_RERENDER_RESULT_EVENT_TYPES:
            raise ValueError(f"invalid re-render result event type {self.event_type!r}")

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class RevisedDeliveryRecord:
    """Immutable identity of a revised (successor) delivery version created by
    Stage 8D reconciliation.

    The ``revision_version_sequence`` and ``revision_version_display`` are
    derived deterministically from the Stage 8A.1 ``DeliveryVersion`` of the
    registered revised delivery lineage, so no second delivery-version
    subsystem exists. The original delivery remains unmodified.
    """

    schema_version: str
    revised_delivery_id: str
    new_delivery_record_id: str
    revision_version_sequence: int
    revision_version_display: str
    original_delivery_id: str
    superseded_delivery_id: str
    revision_id: str
    dispatch_id: str
    accepted_result_id: str
    lineage_id: str
    artifact_id: str
    artifact_sha256: str
    created_at: str
    supersession_status: str = SUPERSESSION_NOT_YET_SUPERSEDED

    def __post_init__(self) -> None:
        version = DeliveryVersion(self.revision_version_sequence)
        if self.revision_version_display != version.display:
            raise ValueError("revision_version_display must be canonical")
        if self.supersession_status not in (SUPERSESSION_NOT_YET_SUPERSEDED, SUPERSESSION_SUPERSEDED):
            raise ValueError("invalid supersession status")

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class SupersessionRecord:
    """Append-only evidence that one delivery version supersedes another.

    The prior (superseded) delivery version is NEVER physically deleted,
    rewritten, or replaced; this record is the append-only supersession
    evidence linking it to the revised delivery version.
    """

    schema_version: str
    supersession_id: str
    revised_delivery_id: str
    superseding_lineage_id: str
    superseding_delivery_record_id: str
    superseding_version_sequence: int
    superseded_delivery_record_id: str
    superseded_lineage_id: str | None
    superseded_version_sequence: int
    revision_id: str
    dispatch_id: str
    accepted_result_id: str
    created_at: str

    def __post_init__(self) -> None:
        # A delivery version may not supersede itself.
        if self.superseding_delivery_record_id == self.superseded_delivery_record_id:
            raise ValueError("a delivery version cannot supersede itself")
        # Version ordering must advance (no loops).
        if self.superseding_version_sequence <= self.superseded_version_sequence:
            raise ValueError("superseding version must be strictly greater than superseded")

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def build_supersession_id(
    *,
    superseding_delivery_record_id: str,
    superseded_delivery_record_id: str,
) -> str:
    """Deterministic supersession identity (order-sensitive, no self-loop)."""
    return _stable_id(
        "scos-hvs-supersession",
        {
            "superseding": superseding_delivery_record_id,
            "superseded": superseded_delivery_record_id,
        },
    )


def build_revised_delivery_id(*, idempotency_key: str, new_delivery_record_id: str) -> str:
    """Deterministic revised-delivery identity from the result identity + the
    Stage 8A.1 delivery record id it produced."""
    return _stable_id(
        "scos-hvs-revised-delivery",
        {"idem": idempotency_key, "delivery_record_id": new_delivery_record_id},
    )


def build_result_idempotency_key(
    *,
    result_id: str,
    dispatch_id: str,
    revision_id: str,
    original_delivery_id: str,
    project_id: str,
    correlation_id: str,
    status: str,
    new_render_request_id: str | None,
    output_formats: tuple[str, ...],
    artifact_references: tuple[str, ...],
    checksums: dict[str, str],
) -> str:
    """Deterministic idempotency identity from stable semantic inputs only.

    Excludes created_at / completed_at / recorded_at / operator_id / renderer
    metadata so replaying the same semantic result yields the same key.
    """
    return _stable_id(
        "scos-hvs-rerender-result-idem",
        {
            "result_id": result_id,
            "dispatch_id": dispatch_id,
            "revision_id": revision_id,
            "original_delivery_id": original_delivery_id,
            "project_id": project_id,
            "correlation_id": correlation_id,
            "status": status,
            "new_render_request_id": new_render_request_id,
            "output_formats": tuple(sorted(output_formats)),
            "artifact_references": tuple(sorted(artifact_references)),
            "checksums": {k: checksums[k] for k in sorted(checksums)},
        },
    )


def result_id_for(idempotency_key: str) -> str:
    return _stable_id("scos-hvs-rerender-result", {"idem": idempotency_key})
