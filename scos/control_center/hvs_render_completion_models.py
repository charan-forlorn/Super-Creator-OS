"""Stage 8N — approval-gated HVS render dispatch, artifact verification,
and render completion evidence.

This is the deterministic service contract that converts verified Stage 8M
render-readiness into a verified media artifact:

    Stage 8M READY evidence
    -> Stage 8N render request (deterministic)
    -> Stage 8N render approval (SEPARATE from Stage 8M approval)
    -> pre-dispatch reverification
    -> HVS render invocation (approved CLI boundary only)
    -> artifact existence + SHA-256
    -> FFprobe stream/duration/A-V-sync verification
    -> render completion evidence (append-only)
    -> audit closure

Hard architecture rules (per the Stage 8N contract):

* SCOS never imports hvs.* or writes into the HVS repository.
* SCOS drives HVS ONLY through the bounded, Stage-5-certified CLI boundary:
      <hvs_python> -m hvs.cli render-hyperframes --project-id <id> --format <fmt>
  via subprocess(argv-list, shell=False, explicit cwd, bounded timeout).
* FFprobe is invoked via subprocess(argv-list, shell=False, bounded timeout),
  JSON output only. Never shell=True, never os.system.
* No delivery, upload, publish, customer contact, invoice or payment mutation
  is ever performed or authorized by Stage 8N.
* Stage 8M materialization approval is NEVER treated as render approval.
* render_authorized / render_started / render_completed / artifact_verified are
  only ever set true as a consequence of an explicit, separate Stage 8N
  approval and a successfully verified render.
* delivery_authorized / publishing_authorized / customer_contact_performed /
  upload_performed / publishing_performed / invoice/payment flags are ALWAYS
  false in every Stage 8N record.
* The models are frozen dataclasses following SCOS convention. Timestamps are
  caller-supplied and excluded from semantic identities. No clock, no random,
  no uuid, no network.

Local-first, deterministic, stdlib-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .hvs_commercial_proposal_models import canonical_json, stable_id


# ---------------------------------------------------------------------------
# Schema / version identities
# ---------------------------------------------------------------------------
STAGE8N_SCHEMA_VERSION = "scos-hvs.render-completion-stage8n.v1/1.0.0"
STAGE8N_EVENT_SCHEMA_VERSION = "scos-hvs.render-completion-event.v1/1.0.0"

STAGE8N_CONTRACT_VERSION = "1.0.0"
STAGE8N_SEMANTIC_VERSION = "1.0.0"

# Reuse the Stage 8M derivation convention so Stage 8N keys off the exact same
# verified HVS project ID / correlation ID.
STAGE8N_REVERIFICATION_SOURCE = "scos-stage8n-from-stage8m-readiness"


# ---------------------------------------------------------------------------
# Enumerations (frozen string-enum tuples, matching SCOS convention)
# ---------------------------------------------------------------------------
class RenderRequestStatus:
    DRAFT = "DRAFT"
    NEEDS_OPERATOR_INPUT = "NEEDS_OPERATOR_INPUT"
    READY_FOR_RENDER_REVIEW = "READY_FOR_RENDER_REVIEW"
    APPROVED_FOR_RENDER = "APPROVED_FOR_RENDER"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class RenderExecutionStatus:
    NOT_STARTED = "NOT_STARTED"
    DISPATCHING = "DISPATCHING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"
    TIMED_OUT = "TIMED_OUT"
    CONFLICTED = "CONFLICTED"
    BLOCKED = "BLOCKED"


class ArtifactVerificationStatus:
    NOT_VERIFIED = "NOT_VERIFIED"
    VERIFIED = "VERIFIED"
    MISSING = "MISSING"
    ZERO_BYTE = "ZERO_BYTE"
    PROBE_FAILED = "PROBE_FAILED"
    STREAM_MISMATCH = "STREAM_MISMATCH"
    CODEC_MISMATCH = "CODEC_MISMATCH"
    RESOLUTION_MISMATCH = "RESOLUTION_MISMATCH"
    FPS_MISMATCH = "FPS_MISMATCH"
    DURATION_MISMATCH = "DURATION_MISMATCH"
    AV_SYNC_FAILED = "AV_SYNC_FAILED"
    HASH_MISMATCH = "HASH_MISMATCH"
    UNEXPECTED_OUTPUT = "UNEXPECTED_OUTPUT"


class RenderCompletionStatus:
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CONFLICTED = "CONFLICTED"
    BLOCKED = "BLOCKED"


class AudioRequirement:
    REQUIRED = "REQUIRED"
    NOT_REQUIRED = "NOT_REQUIRED"


class NoOverwritePolicy:
    NEVER = "never"


# Event types for the append-only Stage 8N store.
class RenderCompletionEventType:
    RENDER_REQUEST_CREATED = "RENDER_REQUEST_CREATED"
    RENDER_REQUEST_REPLAYED = "RENDER_REQUEST_REPLAYED"
    RENDER_REQUEST_CONFLICT_DETECTED = "RENDER_REQUEST_CONFLICT_DETECTED"
    RENDER_READINESS_REVERIFIED = "RENDER_READINESS_REVERIFIED"
    RENDER_APPROVED = "RENDER_APPROVED"
    RENDER_REJECTED = "RENDER_REJECTED"
    RENDER_DISPATCH_STARTED = "RENDER_DISPATCH_STARTED"
    RENDER_DISPATCH_FAILED = "RENDER_DISPATCH_FAILED"
    RENDER_DISPATCH_TIMED_OUT = "RENDER_DISPATCH_TIMED_OUT"
    RENDER_DISPATCH_COMPLETED = "RENDER_DISPATCH_COMPLETED"
    RENDER_ARTIFACT_DISCOVERED = "RENDER_ARTIFACT_DISCOVERED"
    RENDER_ARTIFACT_VERIFIED = "RENDER_ARTIFACT_VERIFIED"
    RENDER_ARTIFACT_REJECTED = "RENDER_ARTIFACT_REJECTED"
    RENDER_COMPLETION_EVIDENCE_CREATED = "RENDER_COMPLETION_EVIDENCE_CREATED"
    RENDER_BATCH_PARTIAL = "RENDER_BATCH_PARTIAL"


ALLOWED_EVENT_TYPES = frozenset(
    {
        RenderCompletionEventType.RENDER_REQUEST_CREATED,
        RenderCompletionEventType.RENDER_REQUEST_REPLAYED,
        RenderCompletionEventType.RENDER_REQUEST_CONFLICT_DETECTED,
        RenderCompletionEventType.RENDER_READINESS_REVERIFIED,
        RenderCompletionEventType.RENDER_APPROVED,
        RenderCompletionEventType.RENDER_REJECTED,
        RenderCompletionEventType.RENDER_DISPATCH_STARTED,
        RenderCompletionEventType.RENDER_DISPATCH_FAILED,
        RenderCompletionEventType.RENDER_DISPATCH_TIMED_OUT,
        RenderCompletionEventType.RENDER_DISPATCH_COMPLETED,
        RenderCompletionEventType.RENDER_ARTIFACT_DISCOVERED,
        RenderCompletionEventType.RENDER_ARTIFACT_VERIFIED,
        RenderCompletionEventType.RENDER_ARTIFACT_REJECTED,
        RenderCompletionEventType.RENDER_COMPLETION_EVIDENCE_CREATED,
        RenderCompletionEventType.RENDER_BATCH_PARTIAL,
    }
)


# ---------------------------------------------------------------------------
# Identity helpers (deterministic, no volatile inputs)
# ---------------------------------------------------------------------------
def _content_hash(payload: dict[str, Any]) -> str:
    return stable_id("scos-hvs-stage8n-content", {"payload": canonical_json(payload)})


def render_request_id(payload: dict[str, Any]) -> str:
    return stable_id("scos-hvs-stage8n-req", payload)


def render_contract_hash(payload: dict[str, Any]) -> str:
    return stable_id("scos-hvs-stage8n-contract", payload)


def render_approval_id(payload: dict[str, Any]) -> str:
    return stable_id("scos-hvs-stage8n-approval", payload)


def render_dispatch_id(payload: dict[str, Any]) -> str:
    return stable_id("scos-hvs-stage8n-dispatch", payload)


def artifact_id(payload: dict[str, Any]) -> str:
    return stable_id("scos-hvs-stage8n-artifact", payload)


def artifact_verification_id(payload: dict[str, Any]) -> str:
    return stable_id("scos-hvs-stage8n-verify", payload)


def render_completion_evidence_id(payload: dict[str, Any]) -> str:
    return stable_id("scos-hvs-stage8n-complete", payload)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RenderFormatContract:
    format_id: str
    width: int
    height: int
    fps: int
    target_duration_seconds: float
    video_codec: str
    pixel_format: str
    audio_requirement: str  # AudioRequirement.*
    no_overwrite_policy: str  # NoOverwritePolicy.*

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_id": self.format_id,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "target_duration_seconds": self.target_duration_seconds,
            "video_codec": self.video_codec,
            "pixel_format": self.pixel_format,
            "audio_requirement": self.audio_requirement,
            "no_overwrite_policy": self.no_overwrite_policy,
        }


@dataclass(frozen=True)
class RenderOutputContract:
    """Exact approved output semantics (used in approval binding + verification)."""

    project_id: str
    hvs_render_root_relative: str  # relative output path under HVS project render root
    no_overwrite_policy: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "hvs_render_root_relative": self.hvs_render_root_relative,
            "no_overwrite_policy": self.no_overwrite_policy,
        }


@dataclass(frozen=True)
class HVSRenderDispatchRequest:
    """Immutable render request. Identity derives from semantic inputs only."""

    schema_version: str
    render_request_id: str
    render_contract_hash: str
    project_id: str
    initialization_contract_id: str
    correlation_id: str
    intake_manifest_id: str
    intake_manifest_content_hash: str
    post_verification_id: str
    render_readiness_id: str
    render_readiness_content_hash: str
    selected_format: str
    format_contract: RenderFormatContract
    output_contract: RenderOutputContract
    request_status: str
    render_authorized: bool = False
    render_started: bool = False
    automation_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "render_request_id": self.render_request_id,
            "render_contract_hash": self.render_contract_hash,
            "project_id": self.project_id,
            "initialization_contract_id": self.initialization_contract_id,
            "correlation_id": self.correlation_id,
            "intake_manifest_id": self.intake_manifest_id,
            "intake_manifest_content_hash": self.intake_manifest_content_hash,
            "post_verification_id": self.post_verification_id,
            "render_readiness_id": self.render_readiness_id,
            "render_readiness_content_hash": self.render_readiness_content_hash,
            "selected_format": self.selected_format,
            "format_contract": self.format_contract.to_dict(),
            "output_contract": self.output_contract.to_dict(),
            "request_status": self.request_status,
            # Boundary: request alone never authorizes render.
            "render_authorized": False,
            "render_started": False,
            "automation_allowed": False,
        }


@dataclass(frozen=True)
class RenderReadinessBinding:
    """Provenance binding back to the exact Stage 8M readiness evidence."""

    project_id: str
    initialization_contract_id: str
    correlation_id: str
    intake_manifest_id: str
    intake_manifest_content_hash: str
    post_verification_id: str
    render_readiness_id: str
    render_readiness_content_hash: str
    readiness_status: str
    asset_hash_values: tuple[str, ...]
    rights_statuses: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "initialization_contract_id": self.initialization_contract_id,
            "correlation_id": self.correlation_id,
            "intake_manifest_id": self.intake_manifest_id,
            "intake_manifest_content_hash": self.intake_manifest_content_hash,
            "post_verification_id": self.post_verification_id,
            "render_readiness_id": self.render_readiness_id,
            "render_readiness_content_hash": self.render_readiness_content_hash,
            "readiness_status": self.readiness_status,
            "asset_hash_values": list(self.asset_hash_values),
            "rights_statuses": list(self.rights_statuses),
        }


@dataclass(frozen=True)
class RenderDispatchApproval:
    """Explicit, SEPARATE Stage 8N render approval. Binds the exact contract."""

    schema_version: str
    render_approval_id: str
    render_request_id: str
    render_contract_hash: str
    operator_id: str
    approved_formats: tuple[str, ...]
    approved_output_contract_hash: str
    render_authorized: bool
    delivery_authorized: bool
    publishing_authorized: bool
    automation_allowed: bool
    explicit_render_confirmation: bool
    explicit_non_delivery_acknowledgement: bool
    non_render_approval_statement: str
    # Bound provenance (invalidates approval if any of these change).
    project_id: str
    intake_manifest_content_hash: str
    render_readiness_id: str
    render_readiness_content_hash: str
    # Optional rejection context.
    rejected: bool = False
    rejection_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "render_approval_id": self.render_approval_id,
            "render_request_id": self.render_request_id,
            "render_contract_hash": self.render_contract_hash,
            "operator_id": self.operator_id,
            "approved_formats": list(self.approved_formats),
            "approved_output_contract_hash": self.approved_output_contract_hash,
            "render_authorized": self.render_authorized,
            "delivery_authorized": self.delivery_authorized,
            "publishing_authorized": self.publishing_authorized,
            "automation_allowed": self.automation_allowed,
            "explicit_render_confirmation": self.explicit_render_confirmation,
            "explicit_non_delivery_acknowledgement": self.explicit_non_delivery_acknowledgement,
            "non_render_approval_statement": self.non_render_approval_statement,
            "project_id": self.project_id,
            "intake_manifest_content_hash": self.intake_manifest_content_hash,
            "render_readiness_id": self.render_readiness_id,
            "render_readiness_content_hash": self.render_readiness_content_hash,
            "rejected": self.rejected,
            "rejection_reason": self.rejection_reason,
        }


@dataclass(frozen=True)
class RenderDispatchResult:
    """Structured HVS execution evidence (never exit-code alone)."""

    schema_version: str
    dispatch_id: str
    hvs_process_invocation_identity: str
    command_normalized: str
    hvs_project_id: str
    hvs_render_id: str | None
    output_relative_path: str | None
    exit_code: int | None
    timeout_status: bool
    execution_status: str
    per_format_status: tuple[dict[str, Any], ...]
    stdout_summary: str
    stderr_summary: str
    manifest_path: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dispatch_id": self.dispatch_id,
            "hvs_process_invocation_identity": self.hvs_process_invocation_identity,
            "command_normalized": self.command_normalized,
            "hvs_project_id": self.hvs_project_id,
            "hvs_render_id": self.hvs_render_id,
            "output_relative_path": self.output_relative_path,
            "exit_code": self.exit_code,
            "timeout_status": self.timeout_status,
            "execution_status": self.execution_status,
            "per_format_status": [dict(p) for p in self.per_format_status],
            "stdout_summary": self.stdout_summary,
            "stderr_summary": self.stderr_summary,
            "manifest_path": self.manifest_path,
        }


@dataclass(frozen=True)
class RenderArtifactDescriptor:
    artifact_id: str
    format_id: str
    relative_output_path: str
    size_bytes: int
    sha256: str
    hvs_render_id: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "format_id": self.format_id,
            "relative_output_path": self.relative_output_path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "hvs_render_id": self.hvs_render_id,
        }


@dataclass(frozen=True)
class RenderArtifactProbeEvidence:
    container: str | None
    container_duration: float | None
    video_stream_count: int
    audio_stream_count: int
    video_codec: str | None
    audio_codec: str | None
    width: int | None
    height: int | None
    fps: float | None
    pixel_format: str | None
    video_duration: float | None
    audio_duration: float | None
    frame_count: float | None
    bit_rate: int | None
    file_size: int
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "container": self.container,
            "container_duration": self.container_duration,
            "video_stream_count": self.video_stream_count,
            "audio_stream_count": self.audio_stream_count,
            "video_codec": self.video_codec,
            "audio_codec": self.audio_codec,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "pixel_format": self.pixel_format,
            "video_duration": self.video_duration,
            "audio_duration": self.audio_duration,
            "frame_count": self.frame_count,
            "bit_rate": self.bit_rate,
            "file_size": self.file_size,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class RenderArtifactVerification:
    schema_version: str
    artifact_verification_id: str
    render_request_id: str
    render_approval_id: str
    render_dispatch_id: str
    hvs_render_id: str | None
    project_id: str
    format_id: str
    approved_output_contract_hash: str
    artifact: RenderArtifactDescriptor
    probe: RenderArtifactProbeEvidence
    target_duration_seconds: float
    actual_duration_seconds: float | None
    duration_difference_seconds: float | None
    duration_tolerance_seconds: float
    av_duration_difference_seconds: float | None
    av_tolerance_seconds: float
    duration_verdict: str
    av_sync_verdict: str
    verification_status: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    artifact_verified: bool
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    video_codec: str | None = None
    pixel_format: str | None = None
    audio_streams: int = 0
    audio_verdict: str = "NOT_REQUIRED"
    delivery_authorized: bool = False
    publishing_authorized: bool = False
    automation_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifact_verification_id": self.artifact_verification_id,
            "render_request_id": self.render_request_id,
            "render_approval_id": self.render_approval_id,
            "render_dispatch_id": self.render_dispatch_id,
            "hvs_render_id": self.hvs_render_id,
            "project_id": self.project_id,
            "format_id": self.format_id,
            "approved_output_contract_hash": self.approved_output_contract_hash,
            "artifact": self.artifact.to_dict(),
            "probe": self.probe.to_dict(),
            "target_duration_seconds": self.target_duration_seconds,
            "actual_duration_seconds": self.actual_duration_seconds,
            "duration_difference_seconds": self.duration_difference_seconds,
            "duration_tolerance_seconds": self.duration_tolerance_seconds,
            "av_duration_difference_seconds": self.av_duration_difference_seconds,
            "av_tolerance_seconds": self.av_tolerance_seconds,
            "duration_verdict": self.duration_verdict,
            "av_sync_verdict": self.av_sync_verdict,
            "verification_status": self.verification_status,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "artifact_verified": self.artifact_verified,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "video_codec": self.video_codec,
            "pixel_format": self.pixel_format,
            "audio_streams": self.audio_streams,
            "audio_verdict": self.audio_verdict,
            "delivery_authorized": False,
            "publishing_authorized": False,
            "automation_allowed": False,
        }


@dataclass(frozen=True)
class RenderCompletionEvidence:
    schema_version: str
    render_completion_evidence_id: str
    render_request_id: str
    render_contract_hash: str
    render_approval_id: str
    render_dispatch_id: str
    hvs_render_id: str | None
    project_id: str
    intake_manifest_id: str
    intake_manifest_content_hash: str
    render_readiness_id: str
    render_readiness_content_hash: str
    requested_formats: tuple[str, ...]
    completed_formats: tuple[str, ...]
    failed_formats: tuple[str, ...]
    artifact_verification_ids: tuple[str, ...]
    artifact_sha256_values: tuple[str, ...]
    completion_status: str
    render_authorized: bool
    render_started: bool
    render_completed: bool
    artifact_verified: bool
    delivery_authorized: bool
    publishing_authorized: bool
    customer_contact_performed: bool
    upload_performed: bool
    publishing_performed: bool
    invoice_state_changed: bool
    payment_state_changed: bool
    automation_allowed: bool

    def to_dict(self) -> dict[str, Any]:
        # Every Stage 8N record keeps the non-delivery boundary explicit.
        return {
            "schema_version": self.schema_version,
            "render_completion_evidence_id": self.render_completion_evidence_id,
            "render_request_id": self.render_request_id,
            "render_contract_hash": self.render_contract_hash,
            "render_approval_id": self.render_approval_id,
            "render_dispatch_id": self.render_dispatch_id,
            "hvs_render_id": self.hvs_render_id,
            "project_id": self.project_id,
            "intake_manifest_id": self.intake_manifest_id,
            "intake_manifest_content_hash": self.intake_manifest_content_hash,
            "render_readiness_id": self.render_readiness_id,
            "render_readiness_content_hash": self.render_readiness_content_hash,
            "requested_formats": list(self.requested_formats),
            "completed_formats": list(self.completed_formats),
            "failed_formats": list(self.failed_formats),
            "artifact_verification_ids": list(self.artifact_verification_ids),
            "artifact_sha256_values": list(self.artifact_sha256_values),
            "completion_status": self.completion_status,
            "render_authorized": self.render_authorized,
            "render_started": self.render_started,
            "render_completed": self.render_completed,
            "artifact_verified": self.artifact_verified,
            "delivery_authorized": False,
            "publishing_authorized": False,
            "customer_contact_performed": False,
            "upload_performed": False,
            "publishing_performed": False,
            "invoice_state_changed": False,
            "payment_state_changed": False,
            "automation_allowed": False,
        }


@dataclass(frozen=True)
class RenderCompletionError:
    kind: str
    detail: str
    code: str

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "detail": self.detail, "code": self.code}
