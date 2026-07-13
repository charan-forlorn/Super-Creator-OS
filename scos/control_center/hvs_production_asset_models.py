"""Stage 8M — approval-gated HVS production asset intake and materialization.

This module is the Stage 8M contract surface. It defines immutable models for
the deterministic read-only workflow that takes a verified Stage 8L HVS project
through:

    Stage 8L reverification
    -> requirement inspection
    -> safe source asset intake
    -> path / file-safety validation
    -> SHA-256 + media probe
    -> rights and usage evidence validation
    -> project / scene / role binding
    -> intake readiness evaluation
    -> explicit materialization approval (bound to exact manifest + hashes)
    -> pre-execution rehash
    -> HVS asset materialization (existing HVS boundary)
    -> post-materialization verification
    -> SCOS <-> HVS asset correlation
    -> render-readiness assessment (read-only)
    -> append-only certification evidence

Hard architecture rules (per the Stage 8M contract):

* SCOS never imports hvs.* or writes into the HVS repository.
* SCOS drives HVS only through the bounded HVS CLI (``import-media`` for
  materialization, ``inspect-project`` / ``media-readiness`` for read-only
  verification), reusing the Stage 1 adapter's subprocess discipline.
* No rendering is invoked at any point.
* render_authorized / render_started / render_output_created are ALWAYS false.
* No asset bytes, secrets, credentials, or private media content are stored.

The models are frozen dataclasses following the SCOS convention (mirrors
``hvs_project_initialization_models``). Timestamps are caller-supplied and
excluded from semantic identities. No clock, no random, no uuid, no network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .hvs_commercial_proposal_models import canonical_json, stable_id


# ---------------------------------------------------------------------------
# Schema / version identities
# ---------------------------------------------------------------------------
STAGE8M_SCHEMA_VERSION = "scos-hvs.production-asset-intake-stage8m.v1/1.0.0"
STAGE8M_EVENT_SCHEMA_VERSION = "scos-hvs.production-asset-event.v1/1.0.0"
STAGE8M_INTAKE_MANIFEST_SCHEMA_VERSION = "scos-hvs.asset-intake-manifest.v1/1.0.0"
STAGE8M_REQUIREMENT_INSPECTION_SCHEMA_VERSION = (
    "scos-hvs.asset-requirement-inspection.v1/1.0.0"
)
STAGE8M_RENDER_READINESS_SCHEMA_VERSION = "scos-hvs.render-readiness.v1/1.0.0"

STAGE8M_CONTRACT_VERSION = "1.0.0"
STAGE8M_SEMANTIC_VERSION = "1.0.0"

# Reuse the Stage 8L derivation convention so Stage 8M keys off the exact same
# verified HVS project ID / correlation ID.
STAGE8L_REVERIFICATION_SOURCE = "scos-stage8m-from-stage8l-certification"


# ---------------------------------------------------------------------------
# Enumerations (frozen string-enum tuples, matching SCOS convention)
# ---------------------------------------------------------------------------
class ProductionAssetRole:
    VISUAL = "visual"
    VOICE = "voice"
    MUSIC = "music"
    ALL = (VISUAL, VOICE, MUSIC)


class ProductionAssetMediaType:
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


# Intake lifecycle statuses.
class ProductionAssetIntakeStatus:
    DRAFT = "DRAFT"
    NEEDS_OPERATOR_INPUT = "NEEDS_OPERATOR_INPUT"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    READY_FOR_MATERIALIZATION_REVIEW = "READY_FOR_MATERIALIZATION_REVIEW"
    APPROVED_FOR_MATERIALIZATION = "APPROVED_FOR_MATERIALIZATION"
    MATERIALIZATION_IN_PROGRESS = "MATERIALIZATION_IN_PROGRESS"
    MATERIALIZATION_PARTIAL = "MATERIALIZATION_PARTIAL"
    MATERIALIZATION_COMPLETED = "MATERIALIZATION_COMPLETED"
    POST_VERIFICATION_FAILED = "POST_VERIFICATION_FAILED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


# Rights statuses.
class AssetRightsStatus:
    UNKNOWN = "UNKNOWN"
    CUSTOMER_PROVIDED_CONFIRMED = "CUSTOMER_PROVIDED_CONFIRMED"
    OPERATOR_OWNED_CONFIRMED = "OPERATOR_OWNED_CONFIRMED"
    LICENSED_CONFIRMED = "LICENSED_CONFIRMED"
    PUBLIC_DOMAIN_CONFIRMED = "PUBLIC_DOMAIN_CONFIRMED"
    RESTRICTED = "RESTRICTED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"

    # Statuses that block materialization.
    BLOCKING = (
        UNKNOWN,
        RESTRICTED,
        EXPIRED,
        REJECTED,
    )


# Validation / probe statuses.
class AssetValidationStatus:
    OK = "OK"
    FAILED = "FAILED"
    NOT_RUN = "NOT_RUN"


# Materialization execution statuses.
class AssetMaterializationStatus:
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CONFLICTED = "CONFLICTED"
    BLOCKED = "BLOCKED"


# Render-readiness statuses.
class RenderReadinessStatus:
    READY = "READY"
    WAITING_FOR_ASSETS = "WAITING_FOR_ASSETS"
    WAITING_FOR_VOICE = "WAITING_FOR_VOICE"
    WAITING_FOR_RIGHTS_EVIDENCE = "WAITING_FOR_RIGHTS_EVIDENCE"
    NEEDS_OPERATOR_INPUT = "NEEDS_OPERATOR_INPUT"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    BLOCKED = "BLOCKED"
    EXPIRED = "EXPIRED"


# Event types for the append-only Stage 8M store.
class ProductionAssetEventType:
    STAGE8L_REVERIFIED = "STAGE8L_REVERIFIED"
    ASSET_REQUIREMENTS_INSPECTED = "ASSET_REQUIREMENTS_INSPECTED"
    ASSET_INTAKE_MANIFEST_CREATED = "ASSET_INTAKE_MANIFEST_CREATED"
    ASSET_INTAKE_REPLAYED = "ASSET_INTAKE_REPLAYED"
    ASSET_INTAKE_CONFLICT_DETECTED = "ASSET_INTAKE_CONFLICT_DETECTED"
    SOURCE_ASSET_VALIDATED = "SOURCE_ASSET_VALIDATED"
    SOURCE_ASSET_VALIDATION_FAILED = "SOURCE_ASSET_VALIDATION_FAILED"
    RIGHTS_EVIDENCE_RECORDED = "RIGHTS_EVIDENCE_RECORDED"
    INTAKE_READINESS_EVALUATED = "INTAKE_READINESS_EVALUATED"
    MATERIALIZATION_APPROVED = "MATERIALIZATION_APPROVED"
    MATERIALIZATION_REJECTED = "MATERIALIZATION_REJECTED"
    MATERIALIZATION_STARTED = "MATERIALIZATION_STARTED"
    MATERIALIZATION_COMPLETED = "MATERIALIZATION_COMPLETED"
    MATERIALIZATION_PARTIAL = "MATERIALIZATION_PARTIAL"
    MATERIALIZATION_FAILED = "MATERIALIZATION_FAILED"
    POST_MATERIALIZATION_VERIFIED = "POST_MATERIALIZATION_VERIFIED"
    POST_MATERIALIZATION_FAILED = "POST_MATERIALIZATION_FAILED"
    RENDER_READINESS_EVALUATED = "RENDER_READINESS_EVALUATED"


ALLOWED_EVENT_TYPES = frozenset(
    {
        ProductionAssetEventType.STAGE8L_REVERIFIED,
        ProductionAssetEventType.ASSET_REQUIREMENTS_INSPECTED,
        ProductionAssetEventType.ASSET_INTAKE_MANIFEST_CREATED,
        ProductionAssetEventType.ASSET_INTAKE_REPLAYED,
        ProductionAssetEventType.ASSET_INTAKE_CONFLICT_DETECTED,
        ProductionAssetEventType.SOURCE_ASSET_VALIDATED,
        ProductionAssetEventType.SOURCE_ASSET_VALIDATION_FAILED,
        ProductionAssetEventType.RIGHTS_EVIDENCE_RECORDED,
        ProductionAssetEventType.INTAKE_READINESS_EVALUATED,
        ProductionAssetEventType.MATERIALIZATION_APPROVED,
        ProductionAssetEventType.MATERIALIZATION_REJECTED,
        ProductionAssetEventType.MATERIALIZATION_STARTED,
        ProductionAssetEventType.MATERIALIZATION_COMPLETED,
        ProductionAssetEventType.MATERIALIZATION_PARTIAL,
        ProductionAssetEventType.MATERIALIZATION_FAILED,
        ProductionAssetEventType.POST_MATERIALIZATION_VERIFIED,
        ProductionAssetEventType.POST_MATERIALIZATION_FAILED,
        ProductionAssetEventType.RENDER_READINESS_EVALUATED,
    }
)


# ---------------------------------------------------------------------------
# Identity helpers (deterministic, no volatile inputs)
# ---------------------------------------------------------------------------
def _content_hash(payload: dict[str, Any]) -> str:
    return stable_id("scos-hvs-stage8m-content", {"payload": canonical_json(payload)})


def requirement_inspection_id(payload: dict[str, Any]) -> str:
    return stable_id("scos-hvs-stage8m-reqinspect", payload)


def source_asset_id(payload: dict[str, Any]) -> str:
    return stable_id("scos-hvs-stage8m-source", payload)


def rights_evidence_id(payload: dict[str, Any]) -> str:
    return stable_id("scos-hvs-stage8m-rights", payload)


def manifest_id(payload: dict[str, Any]) -> str:
    return stable_id("scos-hvs-stage8m-manifest", payload)


def approval_id(payload: dict[str, Any]) -> str:
    return stable_id("scos-hvs-stage8m-approval", payload)


def execution_id(payload: dict[str, Any]) -> str:
    return stable_id("scos-hvs-stage8m-exec", payload)


def post_verification_id(payload: dict[str, Any]) -> str:
    return stable_id("scos-hvs-stage8m-postverify", payload)


def render_readiness_id(payload: dict[str, Any]) -> str:
    return stable_id("scos-hvs-stage8m-readiness", payload)


def requirement_set_hash(requirements: tuple[dict[str, Any], ...]) -> str:
    return stable_id(
        "scos-hvs-stage8m-reqset",
        {"requirements": [canonical_json(r) for r in requirements]},
    )


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ProductionAssetRequirement:
    requirement_id: str
    asset_role: str
    project_id: str
    scene_id: str
    scene_order: int
    required: bool
    expected_media_category: str
    allowed_types: tuple[str, ...]
    media_constraints: dict[str, Any]
    rights_requirement: str
    current_satisfaction_status: str
    requirement_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "asset_role": self.asset_role,
            "project_id": self.project_id,
            "scene_id": self.scene_id,
            "scene_order": self.scene_order,
            "required": self.required,
            "expected_media_category": self.expected_media_category,
            "allowed_types": list(self.allowed_types),
            "media_constraints": dict(self.media_constraints),
            "rights_requirement": self.rights_requirement,
            "current_satisfaction_status": self.current_satisfaction_status,
            "requirement_hash": self.requirement_hash,
        }


@dataclass(frozen=True)
class HVSAssetRequirementInspection:
    schema_version: str
    inspection_id: str
    project_id: str
    initialization_contract_id: str
    kickoff_authorization_id: str
    correlation_id: str
    expected_payload_hash: str
    actual_payload_hash: str
    requirement_set_hash: str
    project_level_requirements: tuple[ProductionAssetRequirement, ...]
    scene_level_requirements: tuple[ProductionAssetRequirement, ...]
    required_assets: tuple[ProductionAssetRequirement, ...]
    optional_assets: tuple[ProductionAssetRequirement, ...]
    existing_verified_assets: tuple[dict[str, Any], ...]
    existing_unverified_assets: tuple[dict[str, Any], ...]
    missing_assets: tuple[ProductionAssetRequirement, ...]
    placeholder_assets: tuple[dict[str, Any], ...]
    unsupported_requirements: tuple[ProductionAssetRequirement, ...]
    materialization_eligibility: bool
    blockers: tuple[str, ...]
    hvs_project_verified: bool
    hvs_semantic_valid: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "inspection_id": self.inspection_id,
            "project_id": self.project_id,
            "initialization_contract_id": self.initialization_contract_id,
            "kickoff_authorization_id": self.kickoff_authorization_id,
            "correlation_id": self.correlation_id,
            "expected_payload_hash": self.expected_payload_hash,
            "actual_payload_hash": self.actual_payload_hash,
            "requirement_set_hash": self.requirement_set_hash,
            "project_level_requirements": [r.to_dict() for r in self.project_level_requirements],
            "scene_level_requirements": [r.to_dict() for r in self.scene_level_requirements],
            "required_assets": [r.to_dict() for r in self.required_assets],
            "optional_assets": [r.to_dict() for r in self.optional_assets],
            "existing_verified_assets": [dict(a) for a in self.existing_verified_assets],
            "existing_unverified_assets": [dict(a) for a in self.existing_unverified_assets],
            "missing_assets": [r.to_dict() for r in self.missing_assets],
            "placeholder_assets": [dict(a) for a in self.placeholder_assets],
            "unsupported_requirements": [r.to_dict() for r in self.unsupported_requirements],
            "materialization_eligibility": self.materialization_eligibility,
            "blockers": list(self.blockers),
            "hvs_project_verified": self.hvs_project_verified,
            "hvs_semantic_valid": self.hvs_semantic_valid,
            "render_authorized": False,
            "render_started": False,
            "automation_allowed": False,
        }


@dataclass(frozen=True)
class SourceAssetDescriptor:
    source_asset_id: str
    project_id: str
    requirement_id: str
    asset_role: str
    scene_id: str
    original_path: str
    safe_basename: str
    media_type: str
    size_bytes: int
    sha256: str
    requirement_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_asset_id": self.source_asset_id,
            "project_id": self.project_id,
            "requirement_id": self.requirement_id,
            "asset_role": self.asset_role,
            "scene_id": self.scene_id,
            "original_path": self.original_path,
            "safe_basename": self.safe_basename,
            "media_type": self.media_type,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "requirement_hash": self.requirement_hash,
        }


@dataclass(frozen=True)
class AssetRightsEvidence:
    rights_evidence_id: str
    source_asset_id: str
    status: str
    basis: str
    usage_scope: str
    evidence_reference: str
    restrictions: tuple[str, ...]
    expiry_date: str | None
    operator_id: str
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "rights_evidence_id": self.rights_evidence_id,
            "source_asset_id": self.source_asset_id,
            "status": self.status,
            "basis": self.basis,
            "usage_scope": self.usage_scope,
            "evidence_reference": self.evidence_reference,
            "restrictions": list(self.restrictions),
            "expiry_date": self.expiry_date,
            "operator_id": self.operator_id,
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True)
class SourceAssetValidation:
    source_asset_id: str
    project_id: str
    requirement_id: str
    asset_role: str
    scene_id: str
    media_type: str
    sha256: str
    validation_status: str
    probe_status: str
    probe_detail: dict[str, Any]
    path_safe: bool
    extension_consistent: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_asset_id": self.source_asset_id,
            "project_id": self.project_id,
            "requirement_id": self.requirement_id,
            "asset_role": self.asset_role,
            "scene_id": self.scene_id,
            "media_type": self.media_type,
            "sha256": self.sha256,
            "validation_status": self.validation_status,
            "probe_status": self.probe_status,
            "probe_detail": dict(self.probe_detail),
            "path_safe": self.path_safe,
            "extension_consistent": self.extension_consistent,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class ProductionAssetBinding:
    requirement_id: str
    source_asset_id: str
    project_id: str
    scene_id: str
    asset_role: str
    compatible_media_type: bool
    binding_status: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "source_asset_id": self.source_asset_id,
            "project_id": self.project_id,
            "scene_id": self.scene_id,
            "asset_role": self.asset_role,
            "compatible_media_type": self.compatible_media_type,
            "binding_status": self.binding_status,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class ProductionAssetIntakeManifest:
    schema_version: str
    manifest_id: str
    project_id: str
    stage8l_initialization_id: str
    stage8k_authorization_id: str
    correlation_id: str
    requirement_inspection_id: str
    requirement_set_hash: str
    source_assets: tuple[SourceAssetDescriptor, ...]
    bindings: tuple[ProductionAssetBinding, ...]
    rights_evidence: tuple[AssetRightsEvidence, ...]
    validation_evidence: tuple[SourceAssetValidation, ...]
    required_asset_count: int
    optional_asset_count: int
    status: str
    content_hash: str
    operator_id: str
    materialization_requested: bool = False
    materialization_approved: bool = False
    materialization_performed: bool = False
    post_materialization_verified: bool = False
    render_authorized: bool = False
    render_started: bool = False
    automation_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "manifest_id": self.manifest_id,
            "project_id": self.project_id,
            "stage8l_initialization_id": self.stage8l_initialization_id,
            "stage8k_authorization_id": self.stage8k_authorization_id,
            "correlation_id": self.correlation_id,
            "requirement_inspection_id": self.requirement_inspection_id,
            "requirement_set_hash": self.requirement_set_hash,
            "source_assets": [s.to_dict() for s in self.source_assets],
            "bindings": [b.to_dict() for b in self.bindings],
            "rights_evidence": [r.to_dict() for r in self.rights_evidence],
            "validation_evidence": [v.to_dict() for v in self.validation_evidence],
            "required_asset_count": self.required_asset_count,
            "optional_asset_count": self.optional_asset_count,
            "status": self.status,
            "content_hash": self.content_hash,
            "operator_id": self.operator_id,
            "materialization_requested": False,
            "materialization_approved": False,
            "materialization_performed": False,
            "post_materialization_verified": False,
            "render_authorized": False,
            "render_started": False,
            "automation_allowed": False,
        }


@dataclass(frozen=True)
class AssetIntakeReadinessResult:
    readiness_status: str
    manifest_id: str
    manifest_hash: str
    evaluation_date: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    missing_requirements: tuple[str, ...]
    invalid_assets: tuple[str, ...]
    rights_blockers: tuple[str, ...]
    conflicts: tuple[str, ...]
    recommended_manual_action: str
    materialization_approval_required: bool
    materialization_performed: bool = False
    render_authorized: bool = False
    render_started: bool = False
    automation_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "readiness_status": self.readiness_status,
            "manifest_id": self.manifest_id,
            "manifest_hash": self.manifest_hash,
            "evaluation_date": self.evaluation_date,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "missing_requirements": list(self.missing_requirements),
            "invalid_assets": list(self.invalid_assets),
            "rights_blockers": list(self.rights_blockers),
            "conflicts": list(self.conflicts),
            "recommended_manual_action": self.recommended_manual_action,
            "materialization_approval_required": self.materialization_approval_required,
            "materialization_performed": False,
            "render_authorized": False,
            "render_started": False,
            "automation_allowed": False,
        }


@dataclass(frozen=True)
class AssetMaterializationApproval:
    approval_id: str
    operator_id: str
    project_id: str
    stage8l_initialization_id: str
    correlation_id: str
    requirement_set_hash: str
    manifest_id: str
    manifest_content_hash: str
    source_asset_ids: tuple[str, ...]
    source_sha256_values: tuple[str, ...]
    rights_evidence_hashes: tuple[str, ...]
    explicit_materialization_confirmation: bool
    explicit_non_render_acknowledgement: bool
    approval_statement: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "operator_id": self.operator_id,
            "project_id": self.project_id,
            "stage8l_initialization_id": self.stage8l_initialization_id,
            "correlation_id": self.correlation_id,
            "requirement_set_hash": self.requirement_set_hash,
            "manifest_id": self.manifest_id,
            "manifest_content_hash": self.manifest_content_hash,
            "source_asset_ids": list(self.source_asset_ids),
            "source_sha256_values": list(self.source_sha256_values),
            "rights_evidence_hashes": list(self.rights_evidence_hashes),
            "explicit_materialization_confirmation": self.explicit_materialization_confirmation,
            "explicit_non_render_acknowledgement": self.explicit_non_render_acknowledgement,
            "approval_statement": self.approval_statement,
            "render_authorized": False,
            "render_started": False,
            "automation_allowed": False,
        }


@dataclass(frozen=True)
class AssetMaterializationResult:
    ok: bool
    execution_id: str
    project_id: str
    manifest_id: str
    status: str
    per_asset: tuple[dict[str, Any], ...]
    no_overwrite: bool
    error_code: str | None = None
    error_detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "execution_id": self.execution_id,
            "project_id": self.project_id,
            "manifest_id": self.manifest_id,
            "status": self.status,
            "per_asset": [dict(a) for a in self.per_asset],
            "no_overwrite": self.no_overwrite,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
            "render_authorized": False,
            "render_started": False,
            "automation_allowed": False,
        }


@dataclass(frozen=True)
class PostMaterializationVerification:
    verification_id: str
    project_id: str
    manifest_id: str
    ok: bool
    expected_asset_count: int
    actual_asset_count: int
    missing_assets: tuple[str, ...]
    unexpected_assets: tuple[str, ...]
    overwrite_detected: bool
    role_binding_ok: bool
    scene_binding_ok: bool
    project_semantic_integrity_ok: bool
    render_artifact_detected: bool
    error_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "verification_id": self.verification_id,
            "project_id": self.project_id,
            "manifest_id": self.manifest_id,
            "ok": self.ok,
            "expected_asset_count": self.expected_asset_count,
            "actual_asset_count": self.actual_asset_count,
            "missing_assets": list(self.missing_assets),
            "unexpected_assets": list(self.unexpected_assets),
            "overwrite_detected": self.overwrite_detected,
            "role_binding_ok": self.role_binding_ok,
            "scene_binding_ok": self.scene_binding_ok,
            "project_semantic_integrity_ok": self.project_semantic_integrity_ok,
            "render_artifact_detected": self.render_artifact_detected,
            "error_code": self.error_code,
            "render_output_created": False,
            "render_authorized": False,
            "render_started": False,
            "automation_allowed": False,
        }


@dataclass(frozen=True)
class HVSRenderReadinessResult:
    readiness_id: str
    project_id: str
    readiness_status: str
    evaluation_date: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    missing_requirements: tuple[str, ...]
    verified_asset_count: int
    placeholder_count: int
    voice_ready: bool
    music_ready: bool
    captions_ready: bool
    rights_ready: bool
    timeline_ready: bool
    preset_ready: bool
    recommended_manual_action: str
    render_authorization_required: bool = True
    render_authorized: bool = False
    render_started: bool = False
    render_output_created: bool = False
    customer_contact_performed: bool = False
    publishing_performed: bool = False
    automation_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "readiness_id": self.readiness_id,
            "project_id": self.project_id,
            "readiness_status": self.readiness_status,
            "evaluation_date": self.evaluation_date,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "missing_requirements": list(self.missing_requirements),
            "verified_asset_count": self.verified_asset_count,
            "placeholder_count": self.placeholder_count,
            "voice_ready": self.voice_ready,
            "music_ready": self.music_ready,
            "captions_ready": self.captions_ready,
            "rights_ready": self.rights_ready,
            "timeline_ready": self.timeline_ready,
            "preset_ready": self.preset_ready,
            "recommended_manual_action": self.recommended_manual_action,
            "render_authorization_required": True,
            "render_authorized": False,
            "render_started": False,
            "render_output_created": False,
            "customer_contact_performed": False,
            "publishing_performed": False,
            "automation_allowed": False,
        }


@dataclass(frozen=True)
class Stage8LReverificationRecord:
    schema_version: str
    project_id: str
    initialization_contract_id: str
    kickoff_authorization_id: str
    correlation_id: str
    expected_payload_hash: str
    actual_payload_hash: str
    hvs_project_exists: bool
    hvs_project_verified: bool
    hvs_semantic_valid: bool
    scene_count: int
    voice_generated: bool
    placeholder_assets_generated: bool
    render_started: bool
    assets_copied: bool
    evidence_source: str
    derived_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "initialization_contract_id": self.initialization_contract_id,
            "kickoff_authorization_id": self.kickoff_authorization_id,
            "correlation_id": self.correlation_id,
            "expected_payload_hash": self.expected_payload_hash,
            "actual_payload_hash": self.actual_payload_hash,
            "hvs_project_exists": self.hvs_project_exists,
            "hvs_project_verified": self.hvs_project_verified,
            "hvs_semantic_valid": self.hvs_semantic_valid,
            "scene_count": self.scene_count,
            "voice_generated": self.voice_generated,
            "placeholder_assets_generated": self.placeholder_assets_generated,
            "render_started": self.render_started,
            "assets_copied": self.assets_copied,
            "evidence_source": self.evidence_source,
            "derived_at": self.derived_at,
            "render_authorized": False,
            "render_started": False,
            "automation_allowed": False,
        }


@dataclass(frozen=True)
class ProductionAssetEvent:
    schema_version: str
    event_id: str
    event_type: str
    subject_id: str
    operator_id: str
    recorded_at: str
    record: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class ProductionAssetError:
    error_code: str
    error_detail: str
    blockers: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "error_detail": self.error_detail,
            "blockers": list(self.blockers),
            "render_authorized": False,
            "render_started": False,
            "automation_allowed": False,
        }
