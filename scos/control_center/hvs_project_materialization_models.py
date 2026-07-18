"""Cohort 10D — controlled HVS project materialization authorization
contracts (pure, stdlib-only, no I/O, no clock, no subprocess).

These are the AUTHORITATIVE, immutable authorization + single-use
capability + deterministic materialization-plan models for the one-shot
transition of an approved SCOS project-preparation record into a
deterministic HVS project workspace.

No module here touches the filesystem, spawns a subprocess, reaches
the network, or performs a render. They are pure value objects +
deterministic hash/validation helpers so the authorization auditor,
capability auditor, persistence auditor, and security auditor can all
inspect the exact same bytes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional

# --------------------------------------------------------------------------
# Canonical constants (shared 1:1 with the TypeScript client mirror)
# --------------------------------------------------------------------------

MATERIALIZATION_SCHEMA_VERSION = 1

# The single authorizable materialization operation.
OPERATION_MATERIALIZE_HVS_PROJECT = "MATERIALIZE_HVS_PROJECT"
ALLOWED_OPERATIONS = (OPERATION_MATERIALIZE_HVS_PROJECT,)

# Authorization decision vocabulary (fail-closed default).
DECISION_AUTHORIZED = "AUTHORIZED"
# Every other decision is a denial / non-grant. Listed explicitly so a
# reviewer can enumerate exactly which decisions are NOT AUTHORIZED.
DECISION_DENIED = "DENIED"
DECISION_UNAVAILABLE = "UNAVAILABLE"
DECISION_MALFORMED = "MALFORMED"
DECISION_STALE = "STALE"
DECISION_EXPIRED = "EXPIRED"
DECISION_CONSUMED = "CONSUMED"
DECISION_REVISION_MISMATCH = "REVISION_MISMATCH"
DECISION_PLAN_MISMATCH = "PLAN_MISMATCH"
DECISION_DESTINATION_MISMATCH = "DESTINATION_MISMATCH"
AUTHORIZED_DECISIONS = (DECISION_AUTHORIZED,)
NON_AUTHORIZED_DECISIONS = (
    DECISION_DENIED,
    DECISION_UNAVAILABLE,
    DECISION_MALFORMED,
    DECISION_STALE,
    DECISION_EXPIRED,
    DECISION_CONSUMED,
    DECISION_REVISION_MISMATCH,
    DECISION_PLAN_MISMATCH,
    DECISION_DESTINATION_MISMATCH,
)
ALL_DECISIONS = AUTHORIZED_DECISIONS + NON_AUTHORIZED_DECISIONS

# Materialization outcome state machine (Cohort 10D §12).
STATE_MATERIALIZATION_NOT_REQUESTED = "MATERIALIZATION_NOT_REQUESTED"
STATE_MATERIALIZATION_AUTHORIZATION_REQUIRED = "MATERIALIZATION_AUTHORIZATION_REQUIRED"
STATE_MATERIALIZATION_AUTHORIZED = "MATERIALIZATION_AUTHORIZED"
STATE_MATERIALIZATION_STARTING = "MATERIALIZATION_STARTING"
STATE_HVS_PROJECT_MATERIALIZED = "HVS_PROJECT_MATERIALIZED"
STATE_MATERIALIZATION_FAILED_CONFIRMED = "MATERIALIZATION_FAILED_CONFIRMED"
STATE_MATERIALIZATION_OUTCOME_UNKNOWN = "MATERIALIZATION_OUTCOME_UNKNOWN"
STATE_MATERIALIZATION_RECONCILIATION_REQUIRED = "MATERIALIZATION_RECONCILIATION_REQUIRED"

# Valid terminal + intermediate transitions (every other transition is rejected).
MATERIALIZATION_TRANSITIONS: dict[str, tuple[str, ...]] = {
    STATE_MATERIALIZATION_NOT_REQUESTED: (
        STATE_MATERIALIZATION_AUTHORIZATION_REQUIRED,
    ),
    STATE_MATERIALIZATION_AUTHORIZATION_REQUIRED: (
        STATE_MATERIALIZATION_AUTHORIZED,
        STATE_MATERIALIZATION_FAILED_CONFIRMED,
    ),
    STATE_MATERIALIZATION_AUTHORIZED: (
        STATE_MATERIALIZATION_STARTING,
        STATE_MATERIALIZATION_FAILED_CONFIRMED,
    ),
    STATE_MATERIALIZATION_STARTING: (
        STATE_HVS_PROJECT_MATERIALIZED,
        STATE_MATERIALIZATION_FAILED_CONFIRMED,
        STATE_MATERIALIZATION_OUTCOME_UNKNOWN,
    ),
    STATE_HVS_PROJECT_MATERIALIZED: (
        STATE_MATERIALIZATION_RECONCILIATION_REQUIRED,
    ),
    STATE_MATERIALIZATION_FAILED_CONFIRMED: (
        STATE_MATERIALIZATION_AUTHORIZATION_REQUIRED,
    ),
    STATE_MATERIALIZATION_OUTCOME_UNKNOWN: (
        STATE_MATERIALIZATION_RECONCILIATION_REQUIRED,
        STATE_HVS_PROJECT_MATERIALIZED,
        STATE_MATERIALIZATION_FAILED_CONFIRMED,
    ),
    STATE_MATERIALIZATION_RECONCILIATION_REQUIRED: (
        STATE_HVS_PROJECT_MATERIALIZED,
        STATE_MATERIALIZATION_FAILED_CONFIRMED,
        STATE_MATERIALIZATION_OUTCOME_UNKNOWN,
    ),
}

# Reconciliation classifications (read-only inspection, Cohort 10D §14).
RECONCILED_CONFIRMED_MATERIALIZED = "CONFIRMED_MATERIALIZED"
RECONCILED_CONFIRMED_NOT_MATERIALIZED = "CONFIRMED_NOT_MATERIALIZED"
RECONCILED_STILL_UNKNOWN = "STILL_UNKNOWN"
RECONCILED_IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
RECONCILED_CORRUPT_MATERIALIZATION = "CORRUPT_MATERIALIZATION"

# Error taxonomy (stable, non-secret reason codes).
ERR_AUTHORIZATION_MISSING = "AUTHORIZATION_MISSING"
ERR_AUTHORIZATION_MALFORMED = "AUTHORIZATION_MALFORMED"
ERR_AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"
ERR_AUTHORIZATION_STALE = "AUTHORIZATION_STALE"
ERR_AUTHORIZATION_EXPIRED = "AUTHORIZATION_EXPIRED"
ERR_AUTHORIZATION_CONSUMED = "AUTHORIZATION_CONSUMED"
ERR_AUTHORIZATION_REVISION_MISMATCH = "AUTHORIZATION_REVISION_MISMATCH"
ERR_AUTHORIZATION_PLAN_MISMATCH = "AUTHORIZATION_PLAN_MISMATCH"
ERR_AUTHORIZATION_DESTINATION_MISMATCH = "AUTHORIZATION_DESTINATION_MISMATCH"
ERR_AUTHORIZATION_OPERATION_MISMATCH = "AUTHORIZATION_OPERATION_MISMATCH"
ERR_CAPABILITY_MISSING = "CAPABILITY_MISSING"
ERR_CAPABILITY_MALFORMED = "CAPABILITY_MALFORMED"
ERR_CAPABILITY_CONSUMED = "CAPABILITY_CONSUMED"
ERR_CAPABILITY_EXPIRED = "CAPABILITY_EXPIRED"
ERR_CAPABILITY_REVISION_MISMATCH = "CAPABILITY_REVISION_MISMATCH"
ERR_CAPABILITY_PLAN_MISMATCH = "CAPABILITY_PLAN_MISMATCH"
ERR_CAPABILITY_DESTINATION_MISMATCH = "CAPABILITY_DESTINATION_MISMATCH"
ERR_CAPABILITY_OPERATION_MISMATCH = "CAPABILITY_OPERATION_MISMATCH"
ERR_PREREQUISITE_UNMET = "PREREQUISITE_UNMET"
ERR_INFLIGHT_ATTEMPT = "INFLIGHT_ATTEMPT"
ERR_HVS_INIT_FAILED = "HVS_INIT_FAILED"
ERR_RECONCILE_REQUIRED = "RECONCILE_REQUIRED"

# Short-lived authorization/capability lifetime (seconds). Bounded so a
# captured authorization cannot be replayed far in the future.
DEFAULT_TTL_SECONDS = 300


# --------------------------------------------------------------------------
# Deterministic helpers
# --------------------------------------------------------------------------

def _canonical_json(value: Any) -> str:
    """Sort-keyed deterministic JSON (mirrors HVS contract hashing)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _require_in(value: Any, allowed: tuple[str, ...], field: str) -> Optional[str]:
    if value not in allowed:
        return f"{field} must be one of {list(allowed)}, got {value!r}"
    return None


# --------------------------------------------------------------------------
# Authorization (immutable, single-use binding)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class HvsProjectMaterializationAuthorization:
    """Immutable, revision/project/plan/destination-bound authorization.

    Issued by the authoritative server AFTER the operator's explicit
    confirmation. Immutable after issuance: a replay of the same bytes
    is the same authorization; it can never be widened, rebound, or
    re-decided. A denied/unknown decision fails closed at every
    mutating boundary.
    """

    schema_version: int
    authorization_id: str
    project_id: str
    project_revision: int
    operation: str
    materialization_plan_hash: str
    destination_identity: str
    issued_at: str
    expires_at: str
    issued_by: str
    decision: str
    nonce: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "project_revision", int(self.project_revision))
        for name in (
            "authorization_id",
            "project_id",
            "operation",
            "materialization_plan_hash",
            "destination_identity",
            "issued_at",
            "expires_at",
            "issued_by",
            "decision",
            "nonce",
        ):
            object.__setattr__(self, name, str(getattr(self, name)))

    # --- validity ---------------------------------------------------------
    def is_authorized(self) -> bool:
        return self.decision == DECISION_AUTHORIZED

    def validate(self) -> tuple[str, ...]:
        """Return problem strings; empty tuple means well-formed + AUTHORIZED."""
        problems: list[str] = []
        if _require_in(self.decision, ALL_DECISIONS, "decision"):
            problems.append(_require_in(self.decision, ALL_DECISIONS, "decision"))  # type: ignore[arg-type]
        if self.operation != OPERATION_MATERIALIZE_HVS_PROJECT:
            problems.append("operation must be MATERIALIZE_HVS_PROJECT")
        if not self.authorization_id:
            problems.append("authorization_id required")
        if not self.project_id:
            problems.append("project_id required")
        if self.project_revision < 1:
            problems.append("project_revision must be >= 1")
        if not self.materialization_plan_hash:
            problems.append("materialization_plan_hash required")
        if not self.destination_identity:
            problems.append("destination_identity required")
        if not self.nonce:
            problems.append("nonce required (replay boundary)")
        if not self.issued_at or not self.expires_at:
            problems.append("issued_at and expires_at required")
        if self.is_authorized() and self.operation != OPERATION_MATERIALIZE_HVS_PROJECT:
            problems.append("authorized decision must bind to MATERIALIZE_HVS_PROJECT")
        return tuple(sorted(set(problems)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "authorization_id": self.authorization_id,
            "project_id": self.project_id,
            "project_revision": self.project_revision,
            "operation": self.operation,
            "materialization_plan_hash": self.materialization_plan_hash,
            "destination_identity": self.destination_identity,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "issued_by": self.issued_by,
            "decision": self.decision,
            "nonce": self.nonce,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HvsProjectMaterializationAuthorization":
        return cls(
            schema_version=int(data["schema_version"]),
            authorization_id=str(data["authorization_id"]),
            project_id=str(data["project_id"]),
            project_revision=int(data["project_revision"]),
            operation=str(data["operation"]),
            materialization_plan_hash=str(data["materialization_plan_hash"]),
            destination_identity=str(data["destination_identity"]),
            issued_at=str(data["issued_at"]),
            expires_at=str(data["expires_at"]),
            issued_by=str(data["issued_by"]),
            decision=str(data["decision"]),
            nonce=str(data["nonce"]),
        )


@dataclass(frozen=True)
class HvsProjectMaterializationCapability:
    """Single-use execution capability bound to one authorization + attempt.

    Cannot authorize rendering, FFmpeg/FFprobe/Chromium/HyperFrames,
    another project/revision/destination, and can only be consumed once.
    """

    schema_version: int
    capability_id: str
    authorization_id: str
    project_id: str
    project_revision: int
    plan_hash: str
    destination_identity: str
    issued_at: str
    expires_at: str
    consumed_at: Optional[str]
    operation: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "project_revision", int(self.project_revision))
        object.__setattr__(self, "consumed_at", str(self.consumed_at) if self.consumed_at else None)

    def is_consumed(self) -> bool:
        return self.consumed_at is not None and self.consumed_at != ""

    def is_expired(self, *, now_iso: str) -> bool:
        """True if expires_at is before now_iso (ISO-8601 lexical compare)."""
        return self.expires_at < now_iso

    def validate(self) -> tuple[str, ...]:
        problems: list[str] = []
        if self.operation != OPERATION_MATERIALIZE_HVS_PROJECT:
            problems.append("capability operation must be MATERIALIZE_HVS_PROJECT")
        if not self.capability_id:
            problems.append("capability_id required")
        if not self.authorization_id:
            problems.append("authorization_id required")
        if not self.project_id:
            problems.append("project_id required")
        if self.project_revision < 1:
            problems.append("project_revision must be >= 1")
        if not self.plan_hash:
            problems.append("plan_hash required")
        if not self.destination_identity:
            problems.append("destination_identity required")
        if self.is_consumed():
            problems.append("capability already consumed")
        return tuple(sorted(set(problems)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "capability_id": self.capability_id,
            "authorization_id": self.authorization_id,
            "project_id": self.project_id,
            "project_revision": self.project_revision,
            "plan_hash": self.plan_hash,
            "destination_identity": self.destination_identity,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "consumed_at": self.consumed_at,
            "operation": self.operation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HvsProjectMaterializationCapability":
        return cls(
            schema_version=int(data["schema_version"]),
            capability_id=str(data["capability_id"]),
            authorization_id=str(data["authorization_id"]),
            project_id=str(data["project_id"]),
            project_revision=int(data["project_revision"]),
            plan_hash=str(data["plan_hash"]),
            destination_identity=str(data["destination_identity"]),
            issued_at=str(data["issued_at"]),
            expires_at=str(data["expires_at"]),
            consumed_at=data.get("consumed_at") or None,
            operation=str(data["operation"]),
        )


# --------------------------------------------------------------------------
# Materialization plan (deterministic, reviewable, hashable)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class HvsProjectMaterializationPlan:
    """Deterministic materialization plan (Cohort 10D §8).

    The preview displayed to the operator and the plan executed after
    authorization carry the SAME canonical hash. The plan never contains
    platform credentials, secrets, arbitrary shell commands, browser-supplied
    filesystem destinations, unvalidated absolute asset paths, render
    commands, publish commands, or external URL fetch instructions.
    """

    plan_schema_version: int
    project_id: str
    project_revision: int
    normalized_hvs_project_name: str
    destination_identity: str
    project_metadata: dict[str, Any]
    scene_plan_refs: tuple[str, ...]
    asset_manifest_refs: tuple[str, ...]
    voice_audio_refs: tuple[str, ...]
    output_profiles: tuple[str, ...]
    expected_files: tuple[str, ...]
    expected_directories: tuple[str, ...]
    forbidden_operations: tuple[str, ...]
    plan_hash: str

    def canonical_content(self) -> dict[str, Any]:
        """The hashable content (excludes the plan_hash field itself)."""
        return {
            "plan_schema_version": self.plan_schema_version,
            "project_id": self.project_id,
            "project_revision": self.project_revision,
            "normalized_hvs_project_name": self.normalized_hvs_project_name,
            "destination_identity": self.destination_identity,
            "project_metadata": self.project_metadata,
            "scene_plan_refs": list(self.scene_plan_refs),
            "asset_manifest_refs": list(self.asset_manifest_refs),
            "voice_audio_refs": list(self.voice_audio_refs),
            "output_profiles": list(self.output_profiles),
            "expected_files": list(self.expected_files),
            "expected_directories": list(self.expected_directories),
            "forbidden_operations": list(self.forbidden_operations),
        }

    def compute_hash(self) -> str:
        return _sha256_hex(_canonical_json(self.canonical_content()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_schema_version": self.plan_schema_version,
            "project_id": self.project_id,
            "project_revision": self.project_revision,
            "normalized_hvs_project_name": self.normalized_hvs_project_name,
            "destination_identity": self.destination_identity,
            "project_metadata": self.project_metadata,
            "scene_plan_refs": list(self.scene_plan_refs),
            "asset_manifest_refs": list(self.asset_manifest_refs),
            "voice_audio_refs": list(self.voice_audio_refs),
            "output_profiles": list(self.output_profiles),
            "expected_files": list(self.expected_files),
            "expected_directories": list(self.expected_directories),
            "forbidden_operations": list(self.forbidden_operations),
            "plan_hash": self.plan_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HvsProjectMaterializationPlan":
        return cls(
            plan_schema_version=int(data["plan_schema_version"]),
            project_id=str(data["project_id"]),
            project_revision=int(data["project_revision"]),
            normalized_hvs_project_name=str(data["normalized_hvs_project_name"]),
            destination_identity=str(data["destination_identity"]),
            project_metadata=dict(data.get("project_metadata") or {}),
            scene_plan_refs=tuple(data.get("scene_plan_refs") or ()),
            asset_manifest_refs=tuple(data.get("asset_manifest_refs") or ()),
            voice_audio_refs=tuple(data.get("voice_audio_refs") or ()),
            output_profiles=tuple(data.get("output_profiles") or ()),
            expected_files=tuple(data.get("expected_files") or ()),
            expected_directories=tuple(data.get("expected_directories") or ()),
            forbidden_operations=tuple(data.get("forbidden_operations") or ()),
            plan_hash=str(data["plan_hash"]),
        )


# --------------------------------------------------------------------------
# Durable attempt record (persisted to the cohort materialization store)
# --------------------------------------------------------------------------

@dataclass
class HvsMaterializationAttempt:
    """One materialization attempt with exact revision/plan/destination binding."""

    attempt_id: str
    project_id: str
    project_revision: int
    plan_hash: str
    destination_identity: str
    authorization_id: str
    capability_id: str
    state: str
    hvs_calls: int
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    outcome: Optional[str] = None
    error_code: Optional[str] = None
    error_detail: Optional[str] = None
    persisted_result: Optional[dict[str, Any]] = None
    expected_payload_hash: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "project_id": self.project_id,
            "project_revision": self.project_revision,
            "plan_hash": self.plan_hash,
            "destination_identity": self.destination_identity,
            "authorization_id": self.authorization_id,
            "capability_id": self.capability_id,
            "state": self.state,
            "hvs_calls": self.hvs_calls,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "outcome": self.outcome,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
            "persisted_result": self.persisted_result,
            "expected_payload_hash": self.expected_payload_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HvsMaterializationAttempt":
        return cls(
            attempt_id=str(data["attempt_id"]),
            project_id=str(data["project_id"]),
            project_revision=int(data["project_revision"]),
            plan_hash=str(data["plan_hash"]),
            destination_identity=str(data["destination_identity"]),
            authorization_id=str(data.get("authorization_id") or ""),
            capability_id=str(data.get("capability_id") or ""),
            state=str(data["state"]),
            hvs_calls=int(data.get("hvs_calls") or 0),
            started_at=data.get("started_at") or None,
            finished_at=data.get("finished_at") or None,
            outcome=data.get("outcome") or None,
            error_code=data.get("error_code") or None,
            error_detail=data.get("error_detail") or None,
            persisted_result=data.get("persisted_result"),
            expected_payload_hash=data.get("expected_payload_hash") or None,
        )


__all__ = sorted(
    (
        "MATERIALIZATION_SCHEMA_VERSION",
        "OPERATION_MATERIALIZE_HVS_PROJECT",
        "ALLOWED_OPERATIONS",
        "DECISION_AUTHORIZED",
        "DECISION_DENIED",
        "DECISION_UNAVAILABLE",
        "DECISION_MALFORMED",
        "DECISION_STALE",
        "DECISION_EXPIRED",
        "DECISION_CONSUMED",
        "DECISION_REVISION_MISMATCH",
        "DECISION_PLAN_MISMATCH",
        "DECISION_DESTINATION_MISMATCH",
        "AUTHORIZED_DECISIONS",
        "NON_AUTHORIZED_DECISIONS",
        "ALL_DECISIONS",
        "STATE_MATERIALIZATION_NOT_REQUESTED",
        "STATE_MATERIALIZATION_AUTHORIZATION_REQUIRED",
        "STATE_MATERIALIZATION_AUTHORIZED",
        "STATE_MATERIALIZATION_STARTING",
        "STATE_HVS_PROJECT_MATERIALIZED",
        "STATE_MATERIALIZATION_FAILED_CONFIRMED",
        "STATE_MATERIALIZATION_OUTCOME_UNKNOWN",
        "STATE_MATERIALIZATION_RECONCILIATION_REQUIRED",
        "MATERIALIZATION_TRANSITIONS",
        "RECONCILED_CONFIRMED_MATERIALIZED",
        "RECONCILED_CONFIRMED_NOT_MATERIALIZED",
        "RECONCILED_STILL_UNKNOWN",
        "RECONCILED_IDENTITY_CONFLICT",
        "RECONCILED_CORRUPT_MATERIALIZATION",
        "ERR_AUTHORIZATION_MISSING",
        "ERR_AUTHORIZATION_MALFORMED",
        "ERR_AUTHORIZATION_DENIED",
        "ERR_AUTHORIZATION_STALE",
        "ERR_AUTHORIZATION_EXPIRED",
        "ERR_AUTHORIZATION_CONSUMED",
        "ERR_AUTHORIZATION_REVISION_MISMATCH",
        "ERR_AUTHORIZATION_PLAN_MISMATCH",
        "ERR_AUTHORIZATION_DESTINATION_MISMATCH",
        "ERR_AUTHORIZATION_OPERATION_MISMATCH",
        "ERR_CAPABILITY_MISSING",
        "ERR_CAPABILITY_MALFORMED",
        "ERR_CAPABILITY_CONSUMED",
        "ERR_CAPABILITY_EXPIRED",
        "ERR_CAPABILITY_REVISION_MISMATCH",
        "ERR_CAPABILITY_PLAN_MISMATCH",
        "ERR_CAPABILITY_DESTINATION_MISMATCH",
        "ERR_CAPABILITY_OPERATION_MISMATCH",
        "ERR_PREREQUISITE_UNMET",
        "ERR_INFLIGHT_ATTEMPT",
        "ERR_HVS_INIT_FAILED",
        "ERR_RECONCILE_REQUIRED",
        "DEFAULT_TTL_SECONDS",
        "HvsProjectMaterializationAuthorization",
        "HvsProjectMaterializationCapability",
        "HvsProjectMaterializationPlan",
        "HvsMaterializationAttempt",
        # --- Cohort 10E downstream render-input materialization ----------
        "OPERATION_MATERIALIZE_HVS_RENDER_INPUTS",
        "STATE_HVS_PROJECT_INITIALIZING",
        "STATE_HVS_PROJECT_INITIALIZED",
        "STATE_HVS_RENDER_INPUTS_AUTHORIZATION_REQUIRED",
        "STATE_HVS_RENDER_INPUTS_AUTHORIZED",
        "STATE_HVS_RENDER_INPUTS_MATERIALIZING",
        "STATE_HVS_RENDER_INPUTS_MATERIALIZED",
        "STATE_HVS_RENDER_INPUTS_FAILED_CONFIRMED",
        "STATE_HVS_RENDER_INPUTS_OUTCOME_UNKNOWN",
        "STATE_HVS_RENDER_INPUTS_RECONCILIATION_REQUIRED",
        "STATE_HVS_RENDER_READY",
        "STATE_HVS_RENDER_NOT_READY",
        "RENDER_INPUTS_TRANSITIONS",
        "RENDER_READY_REQUIRED_ARTIFACTS",
        "HvsRenderInputsAuthorization",
        "HvsRenderInputsCapability",
        "HvsRenderInputsAttempt",
        "evaluate_render_inputs_readiness",
        "ERR_RENDER_INPUTS_AUTHORIZATION_MISSING",
        "ERR_RENDER_INPUTS_AUTHORIZATION_MALFORMED",
        "ERR_RENDER_INPUTS_AUTHORIZATION_DENIED",
        "ERR_RENDER_INPUTS_AUTHORIZATION_EXPIRED",
        "ERR_RENDER_INPUTS_AUTHORIZATION_CONSUMED",
        "ERR_RENDER_INPUTS_AUTHORIZATION_REVISION_MISMATCH",
        "ERR_RENDER_INPUTS_AUTHORIZATION_OPERATION_MISMATCH",
        "ERR_RENDER_INPUTS_AUTHORIZATION_IDENTITY_MISMATCH",
        "ERR_RENDER_INPUTS_CAPABILITY_MISSING",
        "ERR_RENDER_INPUTS_CAPABILITY_MALFORMED",
        "ERR_RENDER_INPUTS_CAPABILITY_CONSUMED",
        "ERR_RENDER_INPUTS_CAPABILITY_EXPIRED",
        "ERR_RENDER_INPUTS_CAPABILITY_REVISION_MISMATCH",
        "ERR_RENDER_INPUTS_CAPABILITY_OPERATION_MISMATCH",
        "ERR_RENDER_INPUTS_CAPABILITY_IDENTITY_MISMATCH",
        "ERR_RENDER_INPUTS_INITIALIZATION_MISSING",
        "ERR_RENDER_INPUTS_PARTIAL",
        "ERR_RENDER_INPUTS_CONFLICT",
        "ERR_RENDER_INPUTS_HVS_FAILED",
        "ERR_RENDER_INPUTS_OUTCOME_UNKNOWN",
        "ERR_RENDER_INPUTS_RECONCILE_REQUIRED",
    )
)


# ==========================================================================
# Cohort 10E — Downstream render-input materialization contracts
# --------------------------------------------------------------------------
# A NARROW operation that runs AFTER a successful HVS project initialization.
# It materializes the three downstream render-input artifacts
# (template_selection.json, voice_manifest.json, asset_manifest.json) for an
# already-initialized project, then validates render-readiness (all five
# render-required artifacts present). It never renders, never invokes
# HyperFrames/Chromium/FFmpeg, never reaches the network, and never writes
# SCOS/HVS state other than its own persisted attempt + the HVS artifacts
# produced by the certified `materialize-render-inputs` HVS command.
#
# This is a SEPARATE authority state machine from the full project
# materialization (Cohort 10D). Initialization success is NOT render-readiness.
# ==========================================================================

# The single authorizable downstream operation.
OPERATION_MATERIALIZE_HVS_RENDER_INPUTS = "MATERIALIZE_HVS_RENDER_INPUTS"
RENDER_INPUTS_ALLOWED_OPERATIONS = (OPERATION_MATERIALIZE_HVS_RENDER_INPUTS,)

# Initialization is a prerequisite lifecycle gate, kept distinct from readiness.
STATE_HVS_PROJECT_INITIALIZING = "HVS_PROJECT_INITIALIZING"
STATE_HVS_PROJECT_INITIALIZED = "HVS_PROJECT_INITIALIZED"

# Downstream render-input materialization state machine (Cohort 10E).
STATE_HVS_RENDER_INPUTS_AUTHORIZATION_REQUIRED = "HVS_RENDER_INPUTS_AUTHORIZATION_REQUIRED"
STATE_HVS_RENDER_INPUTS_AUTHORIZED = "HVS_RENDER_INPUTS_AUTHORIZED"
STATE_HVS_RENDER_INPUTS_MATERIALIZING = "HVS_RENDER_INPUTS_MATERIALIZING"
STATE_HVS_RENDER_INPUTS_MATERIALIZED = "HVS_RENDER_INPUTS_MATERIALIZED"
STATE_HVS_RENDER_INPUTS_FAILED_CONFIRMED = "HVS_RENDER_INPUTS_FAILED_CONFIRMED"
STATE_HVS_RENDER_INPUTS_OUTCOME_UNKNOWN = "HVS_RENDER_INPUTS_OUTCOME_UNKNOWN"
STATE_HVS_RENDER_INPUTS_RECONCILIATION_REQUIRED = "HVS_RENDER_INPUTS_RECONCILIATION_REQUIRED"

# Render readiness (read-only gate, all five render-required artifacts valid).
STATE_HVS_RENDER_READY = "HVS_RENDER_READY"
STATE_HVS_RENDER_NOT_READY = "HVS_RENDER_NOT_READY"

# Required render-ready artifacts (3 init + 3 downstream) — mirrors the HVS
# hyperframes_gate.REQUIRED_ARTIFACTS contract.
RENDER_READY_REQUIRED_ARTIFACTS = (
    "project_brief.json",
    "timelines/video_timeline.json",
    "templates/template_selection.json",
    "voice/voice_manifest.json",
    "assets/placeholders/asset_manifest.json",
)

# Valid downstream render-input transitions (every other transition rejected).
RENDER_INPUTS_TRANSITIONS: dict[str, tuple[str, ...]] = {
    STATE_HVS_PROJECT_INITIALIZING: (STATE_HVS_PROJECT_INITIALIZED,),
    STATE_HVS_PROJECT_INITIALIZED: (
        STATE_HVS_RENDER_INPUTS_AUTHORIZATION_REQUIRED,
    ),
    STATE_HVS_RENDER_INPUTS_AUTHORIZATION_REQUIRED: (
        STATE_HVS_RENDER_INPUTS_AUTHORIZED,
        STATE_HVS_RENDER_INPUTS_FAILED_CONFIRMED,
    ),
    STATE_HVS_RENDER_INPUTS_AUTHORIZED: (
        STATE_HVS_RENDER_INPUTS_MATERIALIZING,
        STATE_HVS_RENDER_INPUTS_FAILED_CONFIRMED,
    ),
    STATE_HVS_RENDER_INPUTS_MATERIALIZING: (
        STATE_HVS_RENDER_INPUTS_MATERIALIZED,
        STATE_HVS_RENDER_INPUTS_FAILED_CONFIRMED,
        STATE_HVS_RENDER_INPUTS_OUTCOME_UNKNOWN,
    ),
    STATE_HVS_RENDER_INPUTS_MATERIALIZED: (
        STATE_HVS_RENDER_READY,
        STATE_HVS_RENDER_NOT_READY,
        STATE_HVS_RENDER_INPUTS_RECONCILIATION_REQUIRED,
    ),
    STATE_HVS_RENDER_INPUTS_FAILED_CONFIRMED: (
        STATE_HVS_RENDER_INPUTS_AUTHORIZATION_REQUIRED,
    ),
    STATE_HVS_RENDER_INPUTS_OUTCOME_UNKNOWN: (
        STATE_HVS_RENDER_INPUTS_RECONCILIATION_REQUIRED,
        STATE_HVS_RENDER_INPUTS_MATERIALIZED,
        STATE_HVS_RENDER_INPUTS_FAILED_CONFIRMED,
    ),
    STATE_HVS_RENDER_INPUTS_RECONCILIATION_REQUIRED: (
        STATE_HVS_RENDER_INPUTS_MATERIALIZED,
        STATE_HVS_RENDER_INPUTS_FAILED_CONFIRMED,
        STATE_HVS_RENDER_INPUTS_OUTCOME_UNKNOWN,
        STATE_HVS_RENDER_READY,
        STATE_HVS_RENDER_NOT_READY,
    ),
    STATE_HVS_RENDER_READY: (
        STATE_HVS_RENDER_INPUTS_RECONCILIATION_REQUIRED,
    ),
    STATE_HVS_RENDER_NOT_READY: (
        STATE_HVS_RENDER_INPUTS_RECONCILIATION_REQUIRED,
        STATE_HVS_RENDER_READY,
    ),
}

# Downstream-specific error taxonomy (stable, non-secret reason codes).
ERR_RENDER_INPUTS_AUTHORIZATION_MISSING = "RENDER_INPUTS_AUTHORIZATION_MISSING"
ERR_RENDER_INPUTS_AUTHORIZATION_MALFORMED = "RENDER_INPUTS_AUTHORIZATION_MALFORMED"
ERR_RENDER_INPUTS_AUTHORIZATION_DENIED = "RENDER_INPUTS_AUTHORIZATION_DENIED"
ERR_RENDER_INPUTS_AUTHORIZATION_EXPIRED = "RENDER_INPUTS_AUTHORIZATION_EXPIRED"
ERR_RENDER_INPUTS_AUTHORIZATION_CONSUMED = "RENDER_INPUTS_AUTHORIZATION_CONSUMED"
ERR_RENDER_INPUTS_AUTHORIZATION_REVISION_MISMATCH = "RENDER_INPUTS_AUTHORIZATION_REVISION_MISMATCH"
ERR_RENDER_INPUTS_AUTHORIZATION_OPERATION_MISMATCH = "RENDER_INPUTS_AUTHORIZATION_OPERATION_MISMATCH"
ERR_RENDER_INPUTS_AUTHORIZATION_IDENTITY_MISMATCH = "RENDER_INPUTS_AUTHORIZATION_IDENTITY_MISMATCH"
ERR_RENDER_INPUTS_CAPABILITY_MISSING = "RENDER_INPUTS_CAPABILITY_MISSING"
ERR_RENDER_INPUTS_CAPABILITY_MALFORMED = "RENDER_INPUTS_CAPABILITY_MALFORMED"
ERR_RENDER_INPUTS_CAPABILITY_CONSUMED = "RENDER_INPUTS_CAPABILITY_CONSUMED"
ERR_RENDER_INPUTS_CAPABILITY_EXPIRED = "RENDER_INPUTS_CAPABILITY_EXPIRED"
ERR_RENDER_INPUTS_CAPABILITY_REVISION_MISMATCH = "RENDER_INPUTS_CAPABILITY_REVISION_MISMATCH"
ERR_RENDER_INPUTS_CAPABILITY_OPERATION_MISMATCH = "RENDER_INPUTS_CAPABILITY_OPERATION_MISMATCH"
ERR_RENDER_INPUTS_CAPABILITY_IDENTITY_MISMATCH = "RENDER_INPUTS_CAPABILITY_IDENTITY_MISMATCH"
ERR_RENDER_INPUTS_INITIALIZATION_MISSING = "RENDER_INPUTS_INITIALIZATION_MISSING"
ERR_RENDER_INPUTS_PARTIAL = "RENDER_INPUTS_PARTIAL"
ERR_RENDER_INPUTS_CONFLICT = "RENDER_INPUTS_CONFLICT"
ERR_RENDER_INPUTS_HVS_FAILED = "RENDER_INPUTS_HVS_FAILED"
ERR_RENDER_INPUTS_OUTCOME_UNKNOWN = "RENDER_INPUTS_OUTCOME_UNKNOWN"
ERR_RENDER_INPUTS_RECONCILE_REQUIRED = "RENDER_INPUTS_RECONCILE_REQUIRED"


@dataclass(frozen=True)
class HvsRenderInputsAuthorization:
    """Immutable, bound authorization for the downstream render-input op.

    Mirrors ``HvsProjectMaterializationAuthorization`` but binds to the
    distinct ``MATERIALIZE_HVS_RENDER_INPUTS`` operation. The authorization
    is NOT reused from initialization or rendering; it must bind to the exact
    source project, hvs project, revision, initialization fingerprint, and the
    downstream operation.
    """

    schema_version: int
    authorization_id: str
    source_project_id: str
    hvs_project_id: str
    project_revision: int
    operation: str
    initialization_fingerprint: str
    destination_identity: str
    issued_at: str
    expires_at: str
    issued_by: str
    decision: str
    nonce: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "project_revision", int(self.project_revision))
        object.__setattr__(self, "source_project_id", str(self.source_project_id))
        object.__setattr__(self, "hvs_project_id", str(self.hvs_project_id))
        object.__setattr__(self, "operation", str(self.operation))
        object.__setattr__(self, "initialization_fingerprint", str(self.initialization_fingerprint))
        object.__setattr__(self, "destination_identity", str(self.destination_identity))
        object.__setattr__(self, "decision", str(self.decision))
        object.__setattr__(self, "nonce", str(self.nonce))

    def is_authorized(self) -> bool:
        return self.decision == DECISION_AUTHORIZED

    def is_expired(self, *, now_iso: str) -> bool:
        return self.expires_at < now_iso

    def validate(self) -> tuple[str, ...]:
        problems: list[str] = []
        if self.operation != OPERATION_MATERIALIZE_HVS_RENDER_INPUTS:
            problems.append("operation must be MATERIALIZE_HVS_RENDER_INPUTS")
        if not self.authorization_id:
            problems.append("authorization_id required")
        if not self.source_project_id:
            problems.append("source_project_id required")
        if not self.hvs_project_id:
            problems.append("hvs_project_id required")
        if self.project_revision < 1:
            problems.append("project_revision must be >= 1")
        if not self.initialization_fingerprint:
            problems.append("initialization_fingerprint required")
        # destination_identity is an OPT-IN isolation hook. Empty is permitted
        # (production writes under STUDIO_ROOT); only a non-empty value is
        # bound for identity comparison.
        if self.is_authorized() and self.operation != OPERATION_MATERIALIZE_HVS_RENDER_INPUTS:
            problems.append("authorized decision must bind to MATERIALIZE_HVS_RENDER_INPUTS")
        return tuple(sorted(set(problems)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "authorization_id": self.authorization_id,
            "source_project_id": self.source_project_id,
            "hvs_project_id": self.hvs_project_id,
            "project_revision": self.project_revision,
            "operation": self.operation,
            "initialization_fingerprint": self.initialization_fingerprint,
            "destination_identity": self.destination_identity,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "issued_by": self.issued_by,
            "decision": self.decision,
            "nonce": self.nonce,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HvsRenderInputsAuthorization":
        return cls(
            schema_version=int(data["schema_version"]),
            authorization_id=str(data["authorization_id"]),
            source_project_id=str(data["source_project_id"]),
            hvs_project_id=str(data["hvs_project_id"]),
            project_revision=int(data["project_revision"]),
            operation=str(data["operation"]),
            initialization_fingerprint=str(data["initialization_fingerprint"]),
            destination_identity=str(data["destination_identity"]),
            issued_at=str(data["issued_at"]),
            expires_at=str(data["expires_at"]),
            issued_by=str(data["issued_by"]),
            decision=str(data["decision"]),
            nonce=str(data["nonce"]),
        )


@dataclass(frozen=True)
class HvsRenderInputsCapability:
    """Single-use execution capability for the downstream render-input op."""

    schema_version: int
    capability_id: str
    authorization_id: str
    source_project_id: str
    hvs_project_id: str
    project_revision: int
    initialization_fingerprint: str
    destination_identity: str
    issued_at: str
    expires_at: str
    consumed_at: Optional[str]
    operation: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "project_revision", int(self.project_revision))
        object.__setattr__(self, "consumed_at", str(self.consumed_at) if self.consumed_at else None)

    def is_consumed(self) -> bool:
        return self.consumed_at is not None and self.consumed_at != ""

    def is_expired(self, *, now_iso: str) -> bool:
        return self.expires_at < now_iso

    def validate(self) -> tuple[str, ...]:
        problems: list[str] = []
        if self.operation != OPERATION_MATERIALIZE_HVS_RENDER_INPUTS:
            problems.append("capability operation must be MATERIALIZE_HVS_RENDER_INPUTS")
        if not self.capability_id:
            problems.append("capability_id required")
        if not self.authorization_id:
            problems.append("authorization_id required")
        if not self.hvs_project_id:
            problems.append("hvs_project_id required")
        if self.project_revision < 1:
            problems.append("project_revision must be >= 1")
        if not self.initialization_fingerprint:
            problems.append("initialization_fingerprint required")
        if not self.destination_identity:
            problems.append("destination_identity required")
        if self.is_consumed():
            problems.append("capability already consumed")
        return tuple(sorted(set(problems)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "capability_id": self.capability_id,
            "authorization_id": self.authorization_id,
            "source_project_id": self.source_project_id,
            "hvs_project_id": self.hvs_project_id,
            "project_revision": self.project_revision,
            "initialization_fingerprint": self.initialization_fingerprint,
            "destination_identity": self.destination_identity,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "consumed_at": self.consumed_at,
            "operation": self.operation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HvsRenderInputsCapability":
        return cls(
            schema_version=int(data["schema_version"]),
            capability_id=str(data["capability_id"]),
            authorization_id=str(data["authorization_id"]),
            source_project_id=str(data["source_project_id"]),
            hvs_project_id=str(data["hvs_project_id"]),
            project_revision=int(data["project_revision"]),
            initialization_fingerprint=str(data["initialization_fingerprint"]),
            destination_identity=str(data["destination_identity"]),
            issued_at=str(data["issued_at"]),
            expires_at=str(data["expires_at"]),
            consumed_at=data.get("consumed_at") or None,
            operation=str(data["operation"]),
        )


@dataclass(frozen=True)
class HvsRenderInputsAttempt:
    """Authoritative persisted downstream render-input materialization attempt."""

    attempt_id: str
    source_project_id: str
    hvs_project_id: str
    project_revision: int
    initialization_fingerprint: str
    destination_identity: str
    authorization_id: str
    capability_id: str
    operation: str
    state: str
    hvs_calls: int
    started_at: Optional[str]
    finished_at: Optional[str]
    outcome: Optional[str]
    error_code: Optional[str]
    error_detail: Optional[str]
    expected_payload_hash: str
    created_artifacts: tuple[str, ...]
    replayed: bool
    persisted_result: Optional[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "source_project_id": self.source_project_id,
            "hvs_project_id": self.hvs_project_id,
            "project_revision": self.project_revision,
            "initialization_fingerprint": self.initialization_fingerprint,
            "destination_identity": self.destination_identity,
            "authorization_id": self.authorization_id,
            "capability_id": self.capability_id,
            "operation": self.operation,
            "state": self.state,
            "hvs_calls": self.hvs_calls,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "outcome": self.outcome,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
            "expected_payload_hash": self.expected_payload_hash,
            "created_artifacts": list(self.created_artifacts),
            "replayed": self.replayed,
            "persisted_result": self.persisted_result,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HvsRenderInputsAttempt":
        return cls(
            attempt_id=str(data["attempt_id"]),
            source_project_id=str(data["source_project_id"]),
            hvs_project_id=str(data["hvs_project_id"]),
            project_revision=int(data["project_revision"]),
            initialization_fingerprint=str(data["initialization_fingerprint"]),
            destination_identity=str(data["destination_identity"]),
            authorization_id=str(data["authorization_id"]),
            capability_id=str(data["capability_id"]),
            operation=str(data["operation"]),
            state=str(data["state"]),
            hvs_calls=int(data["hvs_calls"]),
            started_at=data.get("started_at") or None,
            finished_at=data.get("finished_at") or None,
            outcome=data.get("outcome") or None,
            error_code=data.get("error_code") or None,
            error_detail=data.get("error_detail") or None,
            expected_payload_hash=str(data.get("expected_payload_hash", "")),
            created_artifacts=tuple(data.get("created_artifacts", [])),
            replayed=bool(data.get("replayed", False)),
            persisted_result=data.get("persisted_result"),
        )


def evaluate_render_inputs_readiness(
    *,
    hvs_project_exists: bool,
    present_artifacts: tuple[str, ...],
    expected_artifacts: tuple[str, ...] = RENDER_READY_REQUIRED_ARTIFACTS,
) -> tuple[bool, tuple[str, ...]]:
    """Read-only render-readiness validation.

    ``present_artifacts`` is a tuple of RELATIVE artifact paths that exist and
    are valid in the project. The gate requires ALL ``expected_artifacts``
    (the five render-required artifacts: 3 init + 3 downstream) to be present.
    A complete, valid five-artifact project => render-ready. A partial or
    conflicting artifact state => not ready (never success).
    """
    blockers: list[str] = []
    if not hvs_project_exists:
        blockers.append(ERR_RENDER_INPUTS_INITIALIZATION_MISSING)
    missing = [a for a in expected_artifacts if a not in present_artifacts]
    if missing:
        blockers.append("missing_required_artifacts:" + ",".join(missing))
    return (not blockers, tuple(sorted(set(blockers))))
