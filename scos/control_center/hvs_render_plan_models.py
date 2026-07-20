"""Cohort 10E — controlled HVS project render authorization contracts
(pure, stdlib-only, no I/O, no clock, no subprocess).

These are the AUTHORITATIVE, immutable authorization + single-use
capability + deterministic render-plan + durable-attempt models for the
controlled, operator-confirmed render of one trusted materialized HVS
project from Control Center.

This module is the structural mirror of
``hvs_project_materialization_models.py`` (Cohort 10D): it owns the same
contract shape (revision/project/plan/materialization-bound authorization,
single-use capability, deterministic plan hash, durable attempt record,
explicit state machine) but for RENDER instead of MATERIALIZE. No module
here touches the filesystem, spawns a subprocess, reaches the network, or
performs a render. They are pure value objects + deterministic
hash/validation helpers so the authorization auditor, capability auditor,
persistence auditor, and security auditor can all inspect the exact same
bytes.

The render is bound to the materialization that produced the HVS project:
every attempt carries ``materialization_attempt_id`` and
``materialization_plan_hash`` so a render can only be authorized against a
trusted, currently-revision-current, confirmed materialization.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional

# --------------------------------------------------------------------------
# Canonical constants (shared 1:1 with the TypeScript client mirror)
# --------------------------------------------------------------------------

RENDER_SCHEMA_VERSION = 1

# The single authorizable render operation.
OPERATION_RENDER_HVS_PROJECT = "RENDER_HVS_PROJECT"
ALLOWED_OPERATIONS = (OPERATION_RENDER_HVS_PROJECT,)

# Authorization decision vocabulary (fail-closed default).
DECISION_AUTHORIZED = "AUTHORIZED"
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

# Render state machine (Cohort 10E §6.2). Explicit states only; no generic
# COMPLETED. Invalid transitions fail closed.
STATE_RENDER_NOT_REQUESTED = "RENDER_NOT_REQUESTED"
STATE_RENDER_AUTHORIZATION_REQUIRED = "RENDER_AUTHORIZATION_REQUIRED"
STATE_RENDER_AUTHORIZED = "RENDER_AUTHORIZED"
STATE_RENDER_STARTING = "RENDER_STARTING"
STATE_RENDER_RUNNING = "RENDER_RUNNING"
STATE_ARTIFACT_DISCOVERED = "ARTIFACT_DISCOVERED"
STATE_ARTIFACT_VALIDATED = "ARTIFACT_VALIDATED"
STATE_RENDER_SUCCEEDED = "RENDER_SUCCEEDED"
STATE_RENDER_FAILED_CONFIRMED = "RENDER_FAILED_CONFIRMED"
STATE_RENDER_OUTCOME_UNKNOWN = "RENDER_OUTCOME_UNKNOWN"
STATE_RENDER_RECONCILIATION_REQUIRED = "RENDER_RECONCILIATION_REQUIRED"

RENDER_TRANSITIONS: dict[str, tuple[str, ...]] = {
    STATE_RENDER_NOT_REQUESTED: (STATE_RENDER_AUTHORIZATION_REQUIRED,),
    STATE_RENDER_AUTHORIZATION_REQUIRED: (
        STATE_RENDER_AUTHORIZED,
        STATE_RENDER_FAILED_CONFIRMED,
    ),
    STATE_RENDER_AUTHORIZED: (
        STATE_RENDER_STARTING,
        STATE_RENDER_FAILED_CONFIRMED,
    ),
    STATE_RENDER_STARTING: (
        STATE_RENDER_RUNNING,
        STATE_RENDER_FAILED_CONFIRMED,
        STATE_RENDER_OUTCOME_UNKNOWN,
    ),
    STATE_RENDER_RUNNING: (
        STATE_ARTIFACT_DISCOVERED,
        STATE_RENDER_FAILED_CONFIRMED,
        STATE_RENDER_OUTCOME_UNKNOWN,
    ),
    STATE_ARTIFACT_DISCOVERED: (
        STATE_ARTIFACT_VALIDATED,
        STATE_RENDER_FAILED_CONFIRMED,
        STATE_RENDER_OUTCOME_UNKNOWN,
    ),
    STATE_ARTIFACT_VALIDATED: (
        STATE_RENDER_SUCCEEDED,
        STATE_RENDER_FAILED_CONFIRMED,
    ),
    STATE_RENDER_SUCCEEDED: (),
    STATE_RENDER_FAILED_CONFIRMED: (STATE_RENDER_AUTHORIZATION_REQUIRED,),
    STATE_RENDER_OUTCOME_UNKNOWN: (
        STATE_RENDER_RECONCILIATION_REQUIRED,
        STATE_RENDER_SUCCEEDED,
        STATE_RENDER_FAILED_CONFIRMED,
    ),
    STATE_RENDER_RECONCILIATION_REQUIRED: (
        STATE_RENDER_SUCCEEDED,
        STATE_RENDER_FAILED_CONFIRMED,
        STATE_RENDER_OUTCOME_UNKNOWN,
    ),
}

# Reconciliation classifications (read-only inspection, Cohort 10E §8).
RECONCILED_SUCCEEDED = "RENDER_SUCCEEDED"
RECONCILED_FAILED_CONFIRMED = "RENDER_FAILED_CONFIRMED"
RECONCILED_STILL_UNKNOWN = "RENDER_OUTCOME_UNKNOWN"
RECONCILED_ATTEMPT_NOT_FOUND = "ATTEMPT_NOT_FOUND"
RECONCILED_INSPECT_FAILED = "INSPECT_FAILED"
RECONCILED_RECONCILE_REQUIRED = "RECONCILE_REQUIRED"

# Error taxonomy (stable, non-secret reason codes, Cohort 10E §6.5).
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
ERR_INFLIGHT_ATTEMPT = "RENDER_ALREADY_ACTIVE"
ERR_HVS_RENDER_FAILED = "RENDER_START_FAILED"
ERR_RECONCILE_REQUIRED = "RECONCILE_REQUIRED"

# Explicit render-side error vocabulary (Cohort 10E §6.5 / §10).
ERR_PROJECT_NOT_READY = "PROJECT_NOT_READY"
ERR_PROJECT_REVISION_CONFLICT = "PROJECT_REVISION_CONFLICT"
ERR_MATERIALIZATION_NOT_CONFIRMED = "MATERIALIZATION_NOT_CONFIRMED"
ERR_RENDER_PROFILE_UNSUPPORTED = "RENDER_PROFILE_UNSUPPORTED"
ERR_RENDER_PLAN_MISMATCH = "RENDER_PLAN_MISMATCH"
ERR_RENDER_ALREADY_ACTIVE = "RENDER_ALREADY_ACTIVE"
ERR_TOOLCHAIN_UNAVAILABLE = "TOOLCHAIN_UNAVAILABLE"
ERR_DISK_CAPACITY_INSUFFICIENT = "DISK_CAPACITY_INSUFFICIENT"
ERR_HVS_PROJECT_NOT_FOUND = "HVS_PROJECT_NOT_FOUND"
ERR_ARTIFACT_NOT_FOUND = "ARTIFACT_NOT_FOUND"
ERR_ARTIFACT_VALIDATION_FAILED = "ARTIFACT_VALIDATION_FAILED"
ERR_STORE_UNAVAILABLE = "STORE_UNAVAILABLE"
ERR_STORE_CORRUPT = "STORE_CORRUPT"
ERR_SCHEMA_INCOMPATIBLE = "SCHEMA_INCOMPATIBLE"
ERR_LOCK_UNAVAILABLE = "LOCK_UNAVAILABLE"

# Short-lived authorization/capability lifetime (seconds). Bounded so a
# captured authorization cannot be replayed far in the future.
DEFAULT_TTL_SECONDS = 300

# Render profiles (versioned, supported). Cohort 10E supports a single,
# deterministic, certified render profile to keep the renderer contract
# closed and the artifact validation deterministic.
RENDER_PROFILE_VERSION = 1
SUPPORTED_RENDER_PROFILE_IDS = ("vertical",)


@dataclass(frozen=True)
class RenderProfile:
    """Versioned, supported render profile (resolution / fps / codec)."""

    profile_id: str
    version: int
    resolution: str
    width: int
    height: int
    fps: int
    video_codec: str
    pixel_format: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "version": self.version,
            "resolution": self.resolution,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "video_codec": self.video_codec,
            "pixel_format": self.pixel_format,
        }


# Canonical supported render profile registry (Cohort 10E §6.3 + §9).
RENDER_PROFILES: dict[str, RenderProfile] = {
    "vertical": RenderProfile(
        profile_id="vertical",
        version=RENDER_PROFILE_VERSION,
        resolution="1080x1920",
        width=1080,
        height=1920,
        fps=30,
        video_codec="h264",
        pixel_format="yuv420p",
    ),
}


def is_supported_render_profile(profile_id: str) -> bool:
    return profile_id in SUPPORTED_RENDER_PROFILE_IDS


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


def is_valid_render_transition(from_state: str, to_state: str) -> bool:
    allowed = RENDER_TRANSITIONS.get(from_state)
    if allowed is None:
        return False
    return to_state in allowed


# --------------------------------------------------------------------------
# Authorization (immutable, single-use binding)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class HvsRenderAuthorization:
    """Immutable, revision/project/plan/materialization-bound authorization.

    Issued by the authoritative server AFTER the operator's explicit
    confirmation. Immutable after issuance: a replay of the same bytes is
    the same authorization; it can never be widened, rebound, or
    re-decided. A denied/unknown decision fails closed at every mutating
    boundary.
    """

    schema_version: int
    authorization_id: str
    project_id: str
    project_revision: int
    materialization_attempt_id: str
    materialization_plan_hash: str
    render_profile_id: str
    render_plan_hash: str
    output_root_identity: str
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
            "materialization_attempt_id",
            "materialization_plan_hash",
            "render_profile_id",
            "render_plan_hash",
            "output_root_identity",
            "issued_at",
            "expires_at",
            "issued_by",
            "decision",
            "nonce",
        ):
            object.__setattr__(self, name, str(getattr(self, name)))

    def is_authorized(self) -> bool:
        return self.decision == DECISION_AUTHORIZED

    def validate(self) -> tuple[str, ...]:
        """Return problem strings; empty tuple means well-formed + AUTHORIZED."""
        problems: list[str] = []
        if _require_in(self.decision, ALL_DECISIONS, "decision"):
            problems.append(_require_in(self.decision, ALL_DECISIONS, "decision"))  # type: ignore[arg-type]
        if self.operation() != OPERATION_RENDER_HVS_PROJECT:
            problems.append("operation must be RENDER_HVS_PROJECT")
        if not self.authorization_id:
            problems.append("authorization_id required")
        if not self.project_id:
            problems.append("project_id required")
        if self.project_revision < 1:
            problems.append("project_revision must be >= 1")
        if not self.materialization_attempt_id:
            problems.append("materialization_attempt_id required")
        if not self.materialization_plan_hash:
            problems.append("materialization_plan_hash required")
        if not self.render_profile_id:
            problems.append("render_profile_id required")
        if not self.render_plan_hash:
            problems.append("render_plan_hash required")
        if not self.output_root_identity:
            problems.append("output_root_identity required")
        if not self.nonce:
            problems.append("nonce required (replay boundary)")
        if not self.issued_at or not self.expires_at:
            problems.append("issued_at and expires_at required")
        return tuple(sorted(set(problems)))

    def operation(self) -> str:
        return OPERATION_RENDER_HVS_PROJECT

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "authorization_id": self.authorization_id,
            "project_id": self.project_id,
            "project_revision": self.project_revision,
            "materialization_attempt_id": self.materialization_attempt_id,
            "materialization_plan_hash": self.materialization_plan_hash,
            "render_profile_id": self.render_profile_id,
            "render_plan_hash": self.render_plan_hash,
            "output_root_identity": self.output_root_identity,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "issued_by": self.issued_by,
            "decision": self.decision,
            "nonce": self.nonce,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HvsRenderAuthorization":
        return cls(
            schema_version=int(data["schema_version"]),
            authorization_id=str(data["authorization_id"]),
            project_id=str(data["project_id"]),
            project_revision=int(data["project_revision"]),
            materialization_attempt_id=str(data.get("materialization_attempt_id") or ""),
            materialization_plan_hash=str(data.get("materialization_plan_hash") or ""),
            render_profile_id=str(data.get("render_profile_id") or ""),
            render_plan_hash=str(data.get("render_plan_hash") or ""),
            output_root_identity=str(data.get("output_root_identity") or ""),
            issued_at=str(data["issued_at"]),
            expires_at=str(data["expires_at"]),
            issued_by=str(data.get("issued_by") or ""),
            decision=str(data["decision"]),
            nonce=str(data.get("nonce") or ""),
        )


@dataclass(frozen=True)
class HvsRenderCapability:
    """Single-use execution capability bound to one authorization + attempt.

    Cannot authorize another render, another project/revision/destination,
    and can only be consumed once.
    """

    schema_version: int
    capability_id: str
    authorization_id: str
    project_id: str
    project_revision: int
    materialization_attempt_id: str
    materialization_plan_hash: str
    render_profile_id: str
    render_plan_hash: str
    output_root_identity: str
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
        if self.operation != OPERATION_RENDER_HVS_PROJECT:
            problems.append("capability operation must be RENDER_HVS_PROJECT")
        if not self.capability_id:
            problems.append("capability_id required")
        if not self.authorization_id:
            problems.append("authorization_id required")
        if not self.project_id:
            problems.append("project_id required")
        if self.project_revision < 1:
            problems.append("project_revision must be >= 1")
        if not self.materialization_attempt_id:
            problems.append("materialization_attempt_id required")
        if not self.render_plan_hash:
            problems.append("render_plan_hash required")
        if not self.output_root_identity:
            problems.append("output_root_identity required")
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
            "materialization_attempt_id": self.materialization_attempt_id,
            "materialization_plan_hash": self.materialization_plan_hash,
            "render_profile_id": self.render_profile_id,
            "render_plan_hash": self.render_plan_hash,
            "output_root_identity": self.output_root_identity,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "consumed_at": self.consumed_at,
            "operation": self.operation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HvsRenderCapability":
        return cls(
            schema_version=int(data["schema_version"]),
            capability_id=str(data["capability_id"]),
            authorization_id=str(data["authorization_id"]),
            project_id=str(data["project_id"]),
            project_revision=int(data["project_revision"]),
            materialization_attempt_id=str(data.get("materialization_attempt_id") or ""),
            materialization_plan_hash=str(data.get("materialization_plan_hash") or ""),
            render_profile_id=str(data.get("render_profile_id") or ""),
            render_plan_hash=str(data.get("render_plan_hash") or ""),
            output_root_identity=str(data.get("output_root_identity") or ""),
            issued_at=str(data["issued_at"]),
            expires_at=str(data["expires_at"]),
            consumed_at=data.get("consumed_at") or None,
            operation=str(data["operation"]),
        )


# --------------------------------------------------------------------------
# Render plan (deterministic, reviewable, hashable)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class HvsRenderPlan:
    """Deterministic render plan (Cohort 10E §6.1).

    The preview displayed to the operator and the plan executed after
    authorization carry the SAME canonical hash. The plan never contains
    platform credentials, secrets, arbitrary shell commands,
    browser-supplied filesystem destinations, unvalidated absolute asset
    paths, publish commands, or external URL fetch instructions.
    """

    plan_schema_version: int
    project_id: str
    project_revision: int
    materialization_attempt_id: str
    materialization_plan_hash: str
    render_profile_id: str
    hvs_project_name: str
    output_root_identity: str
    profile_metadata: dict[str, Any]
    expected_output_filename: str
    expected_output_relative_path: str
    forbidden_operations: tuple[str, ...]
    plan_hash: str

    def canonical_content(self) -> dict[str, Any]:
        """The hashable content (excludes the plan_hash field itself).

        The plan hash binds to the authorization-relevant plan CONTENT
        (render profile, revision, output identity), not to the attempt
        instance. Excluding materialization_attempt_id keeps the hash stable
        across attempts of the same plan, so a projection computed without a
        specific attempt id matches an authorization issued for a concrete
        attempt id.
        """
        return {
            "plan_schema_version": self.plan_schema_version,
            "project_id": self.project_id,
            "project_revision": self.project_revision,
            "materialization_plan_hash": self.materialization_plan_hash,
            "render_profile_id": self.render_profile_id,
            "hvs_project_name": self.hvs_project_name,
            "output_root_identity": self.output_root_identity,
            "profile_metadata": self.profile_metadata,
            "expected_output_filename": self.expected_output_filename,
            "expected_output_relative_path": self.expected_output_relative_path,
            "forbidden_operations": list(self.forbidden_operations),
        }

    def compute_hash(self) -> str:
        return _sha256_hex(_canonical_json(self.canonical_content()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_schema_version": self.plan_schema_version,
            "project_id": self.project_id,
            "project_revision": self.project_revision,
            "materialization_attempt_id": self.materialization_attempt_id,
            "materialization_plan_hash": self.materialization_plan_hash,
            "render_profile_id": self.render_profile_id,
            "hvs_project_name": self.hvs_project_name,
            "output_root_identity": self.output_root_identity,
            "profile_metadata": self.profile_metadata,
            "expected_output_filename": self.expected_output_filename,
            "expected_output_relative_path": self.expected_output_relative_path,
            "forbidden_operations": list(self.forbidden_operations),
            "plan_hash": self.plan_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HvsRenderPlan":
        return cls(
            plan_schema_version=int(data["plan_schema_version"]),
            project_id=str(data["project_id"]),
            project_revision=int(data["project_revision"]),
            materialization_attempt_id=str(data.get("materialization_attempt_id") or ""),
            materialization_plan_hash=str(data.get("materialization_plan_hash") or ""),
            render_profile_id=str(data.get("render_profile_id") or ""),
            hvs_project_name=str(data.get("hvs_project_name") or ""),
            output_root_identity=str(data.get("output_root_identity") or ""),
            profile_metadata=dict(data.get("profile_metadata") or {}),
            expected_output_filename=str(data.get("expected_output_filename") or ""),
            expected_output_relative_path=str(data.get("expected_output_relative_path") or ""),
            forbidden_operations=tuple(data.get("forbidden_operations") or ()),
            plan_hash=str(data["plan_hash"]),
        )


# --------------------------------------------------------------------------
# Durable attempt record (persisted to the cohort render-attempt store)
# --------------------------------------------------------------------------

@dataclass
class HvsRenderAttempt:
    """One render attempt with exact materialization/plan/revision binding."""

    attempt_id: str
    project_id: str
    project_revision: int
    materialization_attempt_id: str
    materialization_plan_hash: str
    render_profile_id: str
    render_plan_hash: str
    authorization_id: str
    capability_id: str
    output_root_identity: str
    state: str
    hvs_calls: int
    render_calls: int = 0
    attempt_schema_version: int = RENDER_SCHEMA_VERSION
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    process_identity: Optional[str] = None
    reconciliation_count: int = 0
    outcome: Optional[str] = None
    error_code: Optional[str] = None
    error_detail: Optional[str] = None
    artifact_descriptor: Optional[dict[str, Any]] = None
    persisted_result: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "project_id": self.project_id,
            "project_revision": self.project_revision,
            "materialization_attempt_id": self.materialization_attempt_id,
            "materialization_plan_hash": self.materialization_plan_hash,
            "render_profile_id": self.render_profile_id,
            "render_plan_hash": self.render_plan_hash,
            "authorization_id": self.authorization_id,
            "capability_id": self.capability_id,
            "output_root_identity": self.output_root_identity,
            "state": self.state,
            "hvs_calls": self.hvs_calls,
            "render_calls": self.render_calls,
            "attempt_schema_version": self.attempt_schema_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "process_identity": self.process_identity,
            "reconciliation_count": self.reconciliation_count,
            "outcome": self.outcome,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
            "artifact_descriptor": self.artifact_descriptor,
            "persisted_result": self.persisted_result,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HvsRenderAttempt":
        return cls(
            attempt_id=str(data["attempt_id"]),
            project_id=str(data["project_id"]),
            project_revision=int(data["project_revision"]),
            materialization_attempt_id=str(data.get("materialization_attempt_id") or ""),
            materialization_plan_hash=str(data.get("materialization_plan_hash") or ""),
            render_profile_id=str(data.get("render_profile_id") or ""),
            render_plan_hash=str(data.get("render_plan_hash") or ""),
            authorization_id=str(data.get("authorization_id") or ""),
            capability_id=str(data.get("capability_id") or ""),
            output_root_identity=str(data.get("output_root_identity") or ""),
            state=str(data["state"]),
            hvs_calls=int(data.get("hvs_calls") or 0),
            render_calls=int(data.get("render_calls") or 0),
            attempt_schema_version=int(data.get("attempt_schema_version") or RENDER_SCHEMA_VERSION),
            created_at=data.get("created_at") or None,
            updated_at=data.get("updated_at") or None,
            started_at=data.get("started_at") or None,
            finished_at=data.get("finished_at") or None,
            process_identity=data.get("process_identity") or None,
            reconciliation_count=int(data.get("reconciliation_count") or 0),
            outcome=data.get("outcome") or None,
            error_code=data.get("error_code") or None,
            error_detail=data.get("error_detail") or None,
            artifact_descriptor=data.get("artifact_descriptor") or None,
            persisted_result=data.get("persisted_result") or None,
        )


__all__ = sorted(
    (
        "RENDER_SCHEMA_VERSION",
        "OPERATION_RENDER_HVS_PROJECT",
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
        "ALL_DECISIONS",
        "STATE_RENDER_NOT_REQUESTED",
        "STATE_RENDER_AUTHORIZATION_REQUIRED",
        "STATE_RENDER_AUTHORIZED",
        "STATE_RENDER_STARTING",
        "STATE_RENDER_RUNNING",
        "STATE_ARTIFACT_DISCOVERED",
        "STATE_ARTIFACT_VALIDATED",
        "STATE_RENDER_SUCCEEDED",
        "STATE_RENDER_FAILED_CONFIRMED",
        "STATE_RENDER_OUTCOME_UNKNOWN",
        "STATE_RENDER_RECONCILIATION_REQUIRED",
        "RENDER_TRANSITIONS",
        "RECONCILED_SUCCEEDED",
        "RECONCILED_FAILED_CONFIRMED",
        "RECONCILED_STILL_UNKNOWN",
        "RECONCILED_ATTEMPT_NOT_FOUND",
        "RECONCILED_INSPECT_FAILED",
        "RECONCILED_RECONCILE_REQUIRED",
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
        "ERR_HVS_RENDER_FAILED",
        "ERR_RECONCILE_REQUIRED",
        "ERR_PROJECT_NOT_READY",
        "ERR_PROJECT_REVISION_CONFLICT",
        "ERR_MATERIALIZATION_NOT_CONFIRMED",
        "ERR_RENDER_PROFILE_UNSUPPORTED",
        "ERR_RENDER_PLAN_MISMATCH",
        "ERR_RENDER_ALREADY_ACTIVE",
        "ERR_TOOLCHAIN_UNAVAILABLE",
        "ERR_DISK_CAPACITY_INSUFFICIENT",
        "ERR_HVS_PROJECT_NOT_FOUND",
        "ERR_ARTIFACT_NOT_FOUND",
        "ERR_ARTIFACT_VALIDATION_FAILED",
        "ERR_STORE_UNAVAILABLE",
        "ERR_STORE_CORRUPT",
        "ERR_SCHEMA_INCOMPATIBLE",
        "ERR_LOCK_UNAVAILABLE",
        "DEFAULT_TTL_SECONDS",
        "RENDER_PROFILE_VERSION",
        "SUPPORTED_RENDER_PROFILE_IDS",
        "RENDER_PROFILES",
        "RenderProfile",
        "is_supported_render_profile",
        "is_valid_render_transition",
        "HvsRenderAuthorization",
        "HvsRenderCapability",
        "HvsRenderPlan",
        "HvsRenderAttempt",
    )
)
