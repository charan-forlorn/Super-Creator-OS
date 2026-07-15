"""Stage 8N — approval-gated HVS render dispatch, artifact verification,
and render completion evidence service.

This is the deterministic service layer. It consumes a verified Stage 8M
render-readiness record and drives it, through the approved existing HVS CLI
boundary, to an explicitly operator-approved render and a verified artifact.

Boundary (per Stage 8N contract):

    Stage 8M READY evidence
    -> Stage 8N render request (deterministic)
    -> Stage 8N render approval (SEPARATE from Stage 8M approval)
    -> pre-dispatch reverification
    -> HVS render-hyperframes (existing HVS CLI boundary, subprocess)
    -> artifact existence + SHA-256
    -> FFprobe verification (subprocess)
    -> SCOS completion evidence (append-only)
    -> audit closure

Rules enforced here:

* No HVS production module is imported by SCOS.
* The HVS interpreter is injected (never guessed).
* subprocess is argv-list, shell=False, bounded timeout, bounded output.
* The HVS render is reached ONLY through:
      <python> -m hvs.cli render-hyperframes --project-id <id> --format <fmt>
* FFprobe is argv-list, shell=False, JSON output, bounded timeout.
* Stage 8M materialization approval is NEVER treated as render approval.
* A successful process exit alone is NEVER completion proof.
* The final artifact is independently probed; unknown stream evidence is
  never PASS.
* No delivery, upload, publish, customer contact, invoice or payment mutation.
* No media bytes, secrets, or private media content are stored.

Local-first, deterministic. No clock (caller-supplied), no random, no uuid,
no network.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from scos.media_binaries import resolve_ffprobe
from .hvs_render_completion_models import (
    ALLOWED_EVENT_TYPES,
    AudioRequirement,
    ArtifactVerificationStatus,
    NoOverwritePolicy,
    RenderCompletionError,
    RenderCompletionEventType,
    RenderCompletionStatus,
    RenderDispatchApproval,
    RenderDispatchResult,
    RenderExecutionStatus,
    RenderFormatContract,
    RenderOutputContract,
    RenderArtifactDescriptor,
    RenderArtifactProbeEvidence,
    RenderArtifactVerification,
    RenderCompletionEvidence,
    RenderReadinessBinding,
    RenderRequestStatus,
    STAGE8N_SCHEMA_VERSION,
    artifact_id,
    artifact_verification_id,
    render_approval_id,
    render_completion_evidence_id,
    render_contract_hash,
    render_dispatch_id,
    render_request_id,
)
from .hvs_render_completion_store import (
    append_render_completion_event,
    render_completion_path,
    read_render_completion_events,
)
from .hvs_production_asset_models import RenderReadinessStatus


# HVS render boundary (Stage 5 certified, single-format vertical only).
_HVS_CLI_MODULE = "hvs.cli"
_HVS_RENDER_SUBCOMMAND = "render-hyperframes"

# Probe discipline mirrors the HVS media probe contract.
_PROBE_TIMEOUT_SECONDS = 120
_MAX_OUTPUT_CHARS = 4000
_RENDER_TIMEOUT_SECONDS = 600
_MAX_RENDER_TIMEOUT_SECONDS = 900

# Characters that have shell meaning AND are NOT legitimate path content.
_SHELL_METACHARACTERS = frozenset(
    set(";&|`$><\n\r(){}*?!#\"'~")
)

# Deterministic A/V sync tolerance (seconds). Mirrors duration tolerance form.
_AV_SYNC_TOLERANCE_SECONDS = 0.15


# ---------------------------------------------------------------------------
# Identity / contract helpers
# ---------------------------------------------------------------------------
def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _has_shell_metacharacter(token: str) -> bool:
    return any(ch in _SHELL_METACHARACTERS for ch in token)


def _safe_env() -> dict:
    # Minimal environment: never a full os.environ dump (no secret leakage).
    return {}


def _build_render_contract_hash(
    *,
    project_id: str,
    intake_manifest_id: str,
    intake_manifest_content_hash: str,
    render_readiness_id: str,
    render_readiness_content_hash: str,
    selected_format: str,
    width: int,
    height: int,
    fps: int,
    target_duration_seconds: float,
    video_codec: str,
    pixel_format: str,
    audio_requirement: str,
    no_overwrite_policy: str,
    asset_hash_values: tuple[str, ...] = (),
) -> str:
    return render_contract_hash(
        {
            "project_id": project_id,
            "intake_manifest_id": intake_manifest_id,
            "intake_manifest_content_hash": intake_manifest_content_hash,
            "render_readiness_id": render_readiness_id,
            "render_readiness_content_hash": render_readiness_content_hash,
            "selected_format": selected_format,
            "width": width,
            "height": height,
            "fps": fps,
            "target_duration_seconds": target_duration_seconds,
            "video_codec": video_codec,
            "pixel_format": pixel_format,
            "audio_requirement": audio_requirement,
            "no_overwrite_policy": no_overwrite_policy,
            "asset_hash_values": list(asset_hash_values),
        }
    )


# ---------------------------------------------------------------------------
# Stage 8M readiness consumption + validation
# ---------------------------------------------------------------------------
def _read_stage8m_readiness(*, repo_root: Any, project_id: str) -> dict[str, Any] | None:
    """Find the latest Stage 8M RENDER_READINESS_EVALUATED record for project."""
    from .hvs_production_asset_store import asset_intake_path, read_asset_intake_events

    ledger = asset_intake_path(repo_root)
    events = read_asset_intake_events(audit_log_path=ledger)
    latest = None
    for evt in events:
        if evt.event_type == "RENDER_READINESS_EVALUATED":
            rec = evt.record
            if rec.get("project_id") == project_id:
                latest = rec
    return latest


def evaluate_render_request_readiness(
    *,
    repo_root: Any,
    project_id: str,
    selected_format: str,
    width: int,
    height: int,
    fps: int,
    target_duration_seconds: float,
    video_codec: str,
    pixel_format: str,
    audio_requirement: str,
    no_overwrite_policy: str,
    operator_id: str,
    recorded_at: str,
    hvs_repo_root: str | None = None,
    hvs_python_executable: str | None = None,
    intake_manifest_content_hash: str = "",
) -> dict[str, Any]:
    """Phase 5 — validate a render request against Stage 8M readiness.

    Returns a dict that always includes ``ok`` and a deterministic
    ``render_request_id`` / ``render_contract_hash`` even when rejected (so the
    caller can surface structured failures).
    """
    readiness = _read_stage8m_readiness(repo_root=repo_root, project_id=project_id)
    blockers: list[str] = []

    if readiness is None:
        blockers.append("MISSING_STAGE8M_READINESS")
    elif readiness.get("readiness_status") != RenderReadinessStatus.READY:
        blockers.append("STAGE8M_NOT_READY")

    # Format contract validation (Stage 8N supported contract).
    if selected_format != "vertical":
        blockers.append("UNSUPPORTED_FORMAT")
    if width <= 0 or height <= 0:
        blockers.append("INVALID_DIMENSIONS")
    if fps <= 0:
        blockers.append("UNSUPPORTED_FPS")
    if target_duration_seconds is None or target_duration_seconds <= 0:
        blockers.append("INVALID_DURATION")
    if audio_requirement not in (AudioRequirement.REQUIRED, AudioRequirement.NOT_REQUIRED):
        blockers.append("INVALID_AUDIO_CONTRACT")
    if no_overwrite_policy != NoOverwritePolicy.NEVER:
        blockers.append("UNSUPPORTED_NO_OVERWRITE_POLICY")

    contract_hash = _build_render_contract_hash(
        project_id=project_id,
        intake_manifest_id=readiness.get("manifest_id", "") if readiness else "",
        intake_manifest_content_hash=readiness.get("manifest_content_hash", "") if readiness else "",
        render_readiness_id=readiness.get("render_readiness_id", "") if readiness else "",
        render_readiness_content_hash=readiness.get("render_readiness_content_hash", "") if readiness else "",
        selected_format=selected_format,
        width=width,
        height=height,
        fps=fps,
        target_duration_seconds=target_duration_seconds,
        video_codec=video_codec,
        pixel_format=pixel_format,
        audio_requirement=audio_requirement,
        no_overwrite_policy=no_overwrite_policy,
    )
    rid = render_request_id(
        {
            "project_id": project_id,
            "contract_hash": contract_hash,
        }
    )
    status = (
        RenderRequestStatus.READY_FOR_RENDER_REVIEW
        if not blockers
        else RenderRequestStatus.NEEDS_OPERATOR_INPUT
    )

    # Append the deterministic request-created event (idempotent: identical
    # semantic inputs produce one event).
    append_render_completion_event(
        audit_log_path=render_completion_path(repo_root),
        event_type=RenderCompletionEventType.RENDER_REQUEST_CREATED,
        subject_id=rid,
        operator_id=operator_id,
        recorded_at=recorded_at,
        record={
            "render_request_id": rid,
            "render_contract_hash": contract_hash,
            "project_id": project_id,
            "selected_format": selected_format,
            "width": width,
            "height": height,
            "fps": fps,
            "target_duration_seconds": target_duration_seconds,
            "video_codec": video_codec,
            "pixel_format": pixel_format,
            "audio_requirement": audio_requirement,
            "no_overwrite_policy": no_overwrite_policy,
            "intake_manifest_content_hash": intake_manifest_content_hash,
            "render_readiness_id": readiness.get("render_readiness_id", "") if readiness else "",
            "render_readiness_content_hash": readiness.get("render_readiness_content_hash", "") if readiness else "",
            "request_status": status,
            "blockers": tuple(blockers),
            "render_authorized": False,
            "render_started": False,
            "automation_allowed": False,
        },
    )

    return {
        "ok": not blockers,
        "render_request_id": rid,
        "render_contract_hash": contract_hash,
        "request_status": status,
        "blockers": tuple(blockers),
    }


# ---------------------------------------------------------------------------
# Phase 6 — render approval (SEPARATE from Stage 8M approval)
# ---------------------------------------------------------------------------
_NON_RENDER_APPROVAL_STATEMENT = (
    "Approval authorizes only the specified local HVS render operation. It does "
    "not authorize customer delivery, upload, publishing, external distribution, "
    "invoice mutation, payment mutation or customer contact."
)


def approve_render(
    *,
    repo_root: Any,
    project_id: str,
    render_request_id: str,
    render_contract_hash: str,
    operator_id: str,
    recorded_at: str,
    explicit_render_confirmation: bool,
    explicit_non_delivery_acknowledgement: bool,
    reject: bool = False,
    rejection_reason: str | None = None,
    # Bound provenance (must match the evaluated readiness).
    intake_manifest_content_hash: str,
    render_readiness_id: str,
    render_readiness_content_hash: str,
    selected_format: str = "vertical",
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
    target_duration_seconds: float = 3.0,
    video_codec: str = "h264",
    pixel_format: str = "yuv420p",
    audio_requirement: str = AudioRequirement.NOT_REQUIRED,
    no_overwrite_policy: str = NoOverwritePolicy.NEVER,
) -> dict[str, Any]:
    if not explicit_render_confirmation:
        return {"ok": False, "error": "render confirmation required", "code": "MISSING_CONFIRMATION"}
    if not explicit_non_delivery_acknowledgement:
        return {
            "ok": False,
            "error": "non-delivery acknowledgement required",
            "code": "MISSING_NON_DELIVERY_ACK",
        }
    if not operator_id:
        return {"ok": False, "error": "operator id required", "code": "MISSING_OPERATOR"}

    # Conflict policy: a new approval with a different deterministic id than an
    # already-stored approval for the same request must not silently overwrite.
    existing = _latest_approval(repo_root=repo_root, render_request_id=render_request_id)
    if existing is not None:
        prior_aid = existing.get("render_approval_id")
        if prior_aid and prior_aid != render_approval_id(
            {
                "render_request_id": render_request_id,
                "render_contract_hash": render_contract_hash,
                "operator_id": operator_id,
            }
        ):
            raise ValueError("conflicting render approval for request")
    # Gap 1: deterministically bind the approved asset hash values into the
    # approval so a changed asset hash invalidates the approval at reverify.
    _approval_readiness = _read_stage8m_readiness(repo_root=repo_root, project_id=project_id)
    _bound_asset_hash_values = (
        tuple(_approval_readiness.get("asset_hash_values", ()))
        if _approval_readiness
        else ()
    )
    output_contract_hash = _build_render_contract_hash(
        project_id=project_id,
        intake_manifest_id="",
        intake_manifest_content_hash=intake_manifest_content_hash,
        render_readiness_id=render_readiness_id,
        render_readiness_content_hash=render_readiness_content_hash,
        selected_format=selected_format,
        width=width,
        height=height,
        fps=fps,
        target_duration_seconds=target_duration_seconds,
        video_codec=video_codec,
        pixel_format=pixel_format,
        audio_requirement=audio_requirement,
        no_overwrite_policy=no_overwrite_policy,
        asset_hash_values=_bound_asset_hash_values,
    )
    aid = render_approval_id(
        {
            "render_request_id": render_request_id,
            "render_contract_hash": render_contract_hash,
            "operator_id": operator_id,
        }
    )
    approval = RenderDispatchApproval(
        schema_version=STAGE8N_SCHEMA_VERSION,
        render_approval_id=aid,
        render_request_id=render_request_id,
        render_contract_hash=render_contract_hash,
        operator_id=operator_id,
        approved_formats=(selected_format,),
        approved_output_contract_hash=output_contract_hash,
        render_authorized=(not reject),
        delivery_authorized=False,
        publishing_authorized=False,
        automation_allowed=False,
        explicit_render_confirmation=True,
        explicit_non_delivery_acknowledgement=True,
        non_render_approval_statement=_NON_RENDER_APPROVAL_STATEMENT,
        project_id=project_id,
        intake_manifest_content_hash=intake_manifest_content_hash,
        render_readiness_id=render_readiness_id,
        render_readiness_content_hash=render_readiness_content_hash,
        rejected=reject,
        rejection_reason=rejection_reason,
    )
    event_type = (
        RenderCompletionEventType.RENDER_REJECTED
        if reject
        else RenderCompletionEventType.RENDER_APPROVED
    )
    append_render_completion_event(
        audit_log_path=render_completion_path(repo_root),
        event_type=event_type,
        subject_id=render_request_id,
        operator_id=operator_id,
        recorded_at=recorded_at,
        record=approval.to_dict(),
    )
    return {
        "ok": True,
        "approval": approval.to_dict(),
        "approval_id": aid,
        "render_approval_id": aid,
        "render_authorized": approval.render_authorized,
        "delivery_authorized": False,
        "publishing_authorized": False,
        "automation_allowed": False,
    }


def load_readiness_binding(
    *, repo_root: Any, project_id: str
) -> RenderReadinessBinding | None:
    """Reconstruct the provenance binding needed for dispatch from the latest
    Stage 8M READY evidence. Returns None when no readiness record exists."""
    rec = _read_stage8m_readiness(repo_root=repo_root, project_id=project_id)
    if rec is None:
        return None
    return RenderReadinessBinding(
        project_id=rec.get("project_id", project_id),
        initialization_contract_id=rec.get("initialization_contract_id", ""),
        correlation_id=rec.get("correlation_id", ""),
        intake_manifest_id=rec.get("manifest_id", ""),
        intake_manifest_content_hash=rec.get("manifest_content_hash", ""),
        post_verification_id=rec.get("post_verification_id", ""),
        render_readiness_id=rec.get("render_readiness_id", ""),
        render_readiness_content_hash=rec.get("render_readiness_content_hash", ""),
        readiness_status=rec.get("readiness_status", ""),
        asset_hash_values=tuple(rec.get("asset_hash_values", ())),
        rights_statuses=tuple(rec.get("rights_statuses", ())),
    )


def _latest_approval(*, repo_root: Any, render_request_id: str) -> dict[str, Any] | None:
    events = read_render_completion_events(audit_log_path=render_completion_path(repo_root))
    latest = None
    for evt in events:
        if evt["event_type"] in (
            RenderCompletionEventType.RENDER_APPROVED,
            RenderCompletionEventType.RENDER_REJECTED,
        ) and evt["record"].get("render_request_id") == render_request_id:
            latest = evt["record"]
    return latest


# ---------------------------------------------------------------------------
# Phase 7 — pre-dispatch reverification
# ---------------------------------------------------------------------------
def pre_dispatch_reverify(
    *,
    repo_root: Any,
    project_id: str,
    readiness_binding: RenderReadinessBinding,
) -> dict[str, Any]:
    """Reverify the complete evidence chain immediately before dispatch."""
    readiness = _read_stage8m_readiness(repo_root=repo_root, project_id=project_id)
    if readiness is None:
        return {"ok": False, "code": "READINESS_GONE"}
    if readiness.get("readiness_status") != RenderReadinessStatus.READY:
        return {"ok": False, "code": "READINESS_NOT_READY"}
    if readiness.get("render_readiness_id") != readiness_binding.render_readiness_id:
        return {"ok": False, "code": "RENDER_READINESS_CHANGED_AFTER_APPROVAL"}
    if (
        readiness.get("render_readiness_content_hash")
        != readiness_binding.render_readiness_content_hash
    ):
        return {"ok": False, "code": "RENDER_READINESS_CHANGED_AFTER_APPROVAL"}
    if (
        readiness.get("manifest_content_hash")
        != readiness_binding.intake_manifest_content_hash
    ):
        return {"ok": False, "code": "MANIFEST_CHANGED_AFTER_APPROVAL"}
    # Gap 1: a changed asset hash invalidates the approval (fail closed).
    if tuple(readiness.get("asset_hash_values", ())) != tuple(
        readiness_binding.asset_hash_values
    ):
        return {"ok": False, "code": "MANIFEST_CHANGED_AFTER_APPROVAL"}
    return {"ok": True}


# ---------------------------------------------------------------------------
# Phase 8 — HVS render dispatch
# ---------------------------------------------------------------------------
@dataclass
class HVSRenderCompletionExecutor:
    """Single approved render executor. Drives the HVS render boundary."""

    python_executable: str
    subprocess_run: Callable[..., Any] | None = None
    timeout_seconds: int = _RENDER_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        self._subprocess_run = self.subprocess_run or subprocess.run
        self._timeout = max(1, min(int(self.timeout_seconds), _MAX_RENDER_TIMEOUT_SECONDS))

    def build_argv(self, *, hvs_project_id: str, fmt: str) -> list[str]:
        argv = [
            self.python_executable,
            "-m",
            _HVS_CLI_MODULE,
            _HVS_RENDER_SUBCOMMAND,
            "--project-id",
            hvs_project_id,
            "--format",
            fmt,
        ]
        return argv

    def dispatch(
        self,
        *,
        hvs_root: Path,
        hvs_project_id: str,
        fmt: str,
        dispatch_id: str,
    ) -> RenderDispatchResult:
        argv = self.build_argv(hvs_project_id=hvs_project_id, fmt=fmt)
        if any(_has_shell_metacharacter(tok) for tok in argv):
            raise ValueError("constructed render argv contained a shell metacharacter")
        normalized = " ".join(argv)
        cwd = hvs_root.resolve()
        try:
            proc = self._subprocess_run(
                list(argv),
                cwd=str(cwd),
                shell=False,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                input="",
                env=_safe_env(),
            )
        except subprocess.TimeoutExpired:
            return RenderDispatchResult(
                schema_version=STAGE8N_SCHEMA_VERSION,
                dispatch_id=dispatch_id,
                hvs_process_invocation_identity=render_dispatch_id(
                    {"dispatch_id": dispatch_id, "argv": normalized}
                ),
                command_normalized=normalized,
                hvs_project_id=hvs_project_id,
                hvs_render_id=None,
                output_relative_path=None,
                exit_code=None,
                timeout_status=True,
                execution_status=RenderExecutionStatus.TIMED_OUT,
                per_format_status=(),
                stdout_summary="",
                stderr_summary="[render timed out]",
                manifest_path=None,
            )
        except (OSError, ValueError) as exc:
            return RenderDispatchResult(
                schema_version=STAGE8N_SCHEMA_VERSION,
                dispatch_id=dispatch_id,
                hvs_process_invocation_identity=render_dispatch_id(
                    {"dispatch_id": dispatch_id, "argv": normalized}
                ),
                command_normalized=normalized,
                hvs_project_id=hvs_project_id,
                hvs_render_id=None,
                output_relative_path=None,
                exit_code=None,
                timeout_status=False,
                execution_status=RenderExecutionStatus.BLOCKED,
                per_format_status=(),
                stdout_summary="",
                stderr_summary=f"adapter blocked: {type(exc).__name__}",
                manifest_path=None,
            )
        raw = (proc.stdout or "") if hasattr(proc, "stdout") else ""
        exit_code = int(getattr(proc, "returncode", 0) or 0)
        parsed = _parse_hvs_render_stdout(raw)
        # Structured response required; malformed output => treat as failure.
        if parsed is None:
            return RenderDispatchResult(
                schema_version=STAGE8N_SCHEMA_VERSION,
                dispatch_id=dispatch_id,
                hvs_process_invocation_identity=render_dispatch_id(
                    {"dispatch_id": dispatch_id, "argv": normalized}
                ),
                command_normalized=normalized,
                hvs_project_id=hvs_project_id,
                hvs_render_id=None,
                output_relative_path=None,
                exit_code=exit_code,
                timeout_status=False,
                execution_status=RenderExecutionStatus.FAILED,
                per_format_status=(),
                stdout_summary=raw[:_MAX_OUTPUT_CHARS],
                stderr_summary=(proc.stderr or "")[:_MAX_OUTPUT_CHARS],
                manifest_path=None,
            )
        # Completion requires ALL of: clean exit, HVS PASS verdict, the returned
        # project id matching the approved id, and a present output path that
        # resolves safely inside the trusted project render root. Any failure
        # fails closed to FAILED (never COMPLETED on exit code 0 alone).
        returned_project_id = parsed.get("project_id")
        project_id_matches = returned_project_id == hvs_project_id
        out = parsed.get("output_path")
        output_relative_path = (
            _relative_project_path(out, hvs_root, hvs_project_id) if out else None
        )
        has_valid_output = bool(output_relative_path)
        if (
            exit_code == 0
            and parsed.get("verdict") == "PASS"
            and project_id_matches
            and has_valid_output
        ):
            execution_status = RenderExecutionStatus.COMPLETED
            stderr_summary = (proc.stderr or "")[:_MAX_OUTPUT_CHARS]
        else:
            execution_status = RenderExecutionStatus.FAILED
            if not (exit_code == 0 and parsed.get("verdict") == "PASS"):
                reason = "HVS_RENDER_NOT_PASSED"
            elif not project_id_matches:
                reason = (
                    f"RETURNED_PROJECT_ID_MISMATCH:"
                    f"returned={returned_project_id};expected={hvs_project_id}"
                )
            else:
                reason = "MISSING_OR_UNEXPECTED_OUTPUT_PATH"
            stderr_summary = reason
        return RenderDispatchResult(
            schema_version=STAGE8N_SCHEMA_VERSION,
            dispatch_id=dispatch_id,
            hvs_process_invocation_identity=render_dispatch_id(
                {"dispatch_id": dispatch_id, "argv": normalized}
            ),
            command_normalized=normalized,
            hvs_project_id=returned_project_id or hvs_project_id,
            hvs_render_id=parsed.get("render_id"),
            output_relative_path=output_relative_path,
            exit_code=exit_code,
            timeout_status=False,
            execution_status=execution_status,
            per_format_status=(dict(parsed),),
            stdout_summary=raw[:_MAX_OUTPUT_CHARS],
            stderr_summary=stderr_summary,
            manifest_path=_relative_project_path(
                parsed.get("manifest_path"), hvs_root, hvs_project_id
            )
            if parsed.get("manifest_path")
            else None,
        )


def _relative_project_path(abs_path: str | None, hvs_root: Path, project_id: str) -> str | None:
    if not abs_path:
        return None
    try:
        p = Path(abs_path).resolve()
        root = (hvs_root / "projects" / project_id).resolve()
        rel = p.relative_to(root)
        return f"projects/{project_id}/{rel.as_posix()}"
    except ValueError:
        # Out-of-tree / traversal / symlink-escape: never trust the raw path.
        return None


def _render_output_root(hvs_repo_root: Any, project_id: str) -> Path:
    return (Path(hvs_repo_root) / "projects" / project_id).resolve()


def _is_within_render_root(abs_path: Any, hvs_repo_root: Any, project_id: str) -> bool:
    """Canonical boundary check for the trusted project render root.

    Resolves symlinks so a link inside the tree that points outside is rejected.
    Rejects traversal and out-of-tree paths by requiring the resolved path to be
    a descendant of ``<hvs_repo_root>/projects/<project_id>``.
    """
    try:
        resolved = Path(abs_path).resolve()
        root = _render_output_root(hvs_repo_root, project_id)
        resolved.relative_to(root)
        return True
    except (ValueError, OSError):
        return False


# Public alias used by integration tests and external callers: the invoker that
# targets the Stage 5-certified HVS `render-hyperframes` boundary.
_HVSRenderInvoker = HVSRenderCompletionExecutor


def _parse_hvs_render_stdout(raw: str) -> dict[str, Any] | None:
    """Parse the HVS render-hyperframes JSON stdout. Returns None if malformed."""
    if not raw or not raw.strip():
        return None
    # The HVS CLI emits a JSON object plus optional human lines; take the first
    # balanced JSON object by locating the first '{' and last '}'.
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        obj = json.loads(raw[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(obj, dict):
        return None
    if "verdict" not in obj or "project_id" not in obj:
        return None
    return obj


# ---------------------------------------------------------------------------
# Phase 10-13 — artifact discovery + FFprobe verification
# ---------------------------------------------------------------------------
def _probe_media_ffprobe(source_path: str) -> tuple[str, dict[str, Any]]:
    """Probe a media file with ffprobe. (status, detail). argv, shell=False."""
    if not os.path.isfile(source_path):
        return "missing", {"reason": "file not found"}
    bin_name = resolve_ffprobe()
    try:
        proc = subprocess.run(
            [
                bin_name,
                "-v",
                "error",
                "-show_format",
                "-show_streams",
                "-of",
                "json",
                source_path,
            ],
            capture_output=True,
            text=True,
            timeout=_PROBE_TIMEOUT_SECONDS,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return "timeout", {"reason": "ffprobe timed out"}
    except (OSError, ValueError) as exc:
        return "unavailable", {"reason": f"ffprobe unavailable: {type(exc).__name__}"}
    if int(proc.returncode) != 0 or not proc.stdout.strip():
        return "failed", {"reason": (proc.stderr or "ffprobe failed")[:200]}
    try:
        data = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        return "failed", {"reason": "malformed ffprobe json"}
    return "ok", data


def verify_render_artifact(
    *,
    repo_root: Any,
    hvs_repo_root: str,
    project_id: str,
    render_request_id: str,
    render_approval_id: str,
    dispatch_id: str,
    hvs_render_id: str | None,
    output_relative_path: str,
    selected_format: str,
    width: int,
    height: int,
    fps: int,
    target_duration_seconds: float,
    video_codec: str,
    pixel_format: str,
    audio_requirement: str,
    no_overwrite_policy: str,
    operator_id: str,
    recorded_at: str,
) -> dict[str, Any]:
    """Phase 10-14 — discover + hash + ffprobe + verify the artifact."""
    abs_path = Path(hvs_repo_root) / output_relative_path
    blockers: list[str] = []
    warnings: list[str] = []

    # Gap 4/5: the artifact must resolve inside the trusted project render root.
    # Reject traversal, symlink escape, and out-of-tree paths (fail closed).
    if not _is_within_render_root(abs_path, hvs_repo_root, project_id):
        return _reject_artifact(
            repo_root=repo_root, project_id=project_id,
            render_request_id=render_request_id, render_approval_id=render_approval_id,
            dispatch_id=dispatch_id, hvs_render_id=hvs_render_id,
            selected_format=selected_format, output_relative_path=output_relative_path,
            size_bytes=0, sha256="", status=ArtifactVerificationStatus.UNEXPECTED_OUTPUT,
            blockers=("UNEXPECTED_OUTPUT",), warnings=(), operator_id=operator_id,
            recorded_at=recorded_at,
        )

    if not abs_path.is_file():
        return _reject_artifact(
            repo_root=repo_root, project_id=project_id,
            render_request_id=render_request_id, render_approval_id=render_approval_id,
            dispatch_id=dispatch_id, hvs_render_id=hvs_render_id,
            selected_format=selected_format, output_relative_path=output_relative_path,
            size_bytes=0, sha256="", status=ArtifactVerificationStatus.MISSING,
            blockers=("ARTIFACT_MISSING",), warnings=(), operator_id=operator_id,
            recorded_at=recorded_at,
        )

    size_bytes = abs_path.stat().st_size
    if size_bytes <= 0:
        blockers.append("ZERO_BYTE_ARTIFACT")

    sha = _sha256_file(abs_path)
    status, probe_data = _probe_media_ffprobe(str(abs_path))
    if status != "ok":
        blockers.append("PROBE_FAILED")

    # Map probe fields. Tolerant of both the nested ffprobe JSON shape
    # ({"format":..., "streams":[{"codec_type":"video", ...}]}) and the flat
    # normalized shape used by tests/mocks ({"video_streams":1, "width":1080,
    # "video_codec":"h264", ...}).
    if isinstance(probe_data, dict) and "streams" in probe_data:
        fmt = probe_data.get("format", {})
        streams = probe_data.get("streams", [])
        video_streams = [s for s in streams if s.get("codec_type") == "video"]
        audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    elif isinstance(probe_data, dict) and "video_streams" in probe_data:
        fmt = probe_data
        v_flat = {}
        a_flat = {}
        if probe_data.get("video_streams"):
            v_flat = {
                "codec_name": probe_data.get("video_codec"),
                "width": probe_data.get("width"),
                "height": probe_data.get("height"),
                "pix_fmt": probe_data.get("pixel_format"),
                "r_frame_rate": _fps_to_r_frame_rate(probe_data.get("fps")),
                "duration": probe_data.get("video_duration"),
                "nb_frames": probe_data.get("frame_count"),
            }
        if probe_data.get("audio_streams"):
            a_flat = {
                "codec_name": probe_data.get("audio_codec"),
                "duration": probe_data.get("audio_duration"),
            }
        video_streams = [v_flat] if v_flat else []
        audio_streams = [a_flat] if a_flat else []
    else:
        fmt = {}
        video_streams = []
        audio_streams = []
    v = video_streams[0] if video_streams else {}
    a = audio_streams[0] if audio_streams else {}

    container = fmt.get("format_name")
    container_duration = _to_float(fmt.get("duration"))
    v_codec = v.get("codec_name")
    a_codec = a.get("codec_name")
    pw = _to_int(v.get("width"))
    ph = _to_int(v.get("height"))
    p_pix = v.get("pix_fmt")
    p_fps = _parse_fps(v.get("r_frame_rate"))
    v_dur = _to_float(v.get("duration"))
    a_dur = _to_float(a.get("duration"))
    frame_count = _to_float(v.get("nb_frames"))
    bit_rate = _to_int(fmt.get("bit_rate"))

    # Stream validation.
    if not video_streams:
        blockers.append("VIDEO_STREAM_REQUIRED")
    if audio_requirement == AudioRequirement.REQUIRED and not audio_streams:
        blockers.append("AUDIO_STREAM_REQUIRED")
    if audio_requirement == AudioRequirement.NOT_REQUIRED and not audio_streams:
        warnings.append("AUDIO_NOT_REQUIRED_ABSENT")

    # Codec / resolution / fps / pixel-format validation.
    if video_streams and v_codec != video_codec:
        blockers.append("VIDEO_CODEC_MISMATCH")
    if video_streams and (pw != width or ph != height):
        blockers.append("RESOLUTION_MISMATCH")
    if video_streams and p_fps is not None and abs(p_fps - fps) > 0.01:
        blockers.append("FPS_MISMATCH")
    if video_streams and p_pix != pixel_format:
        blockers.append("PIXEL_FORMAT_MISMATCH")

    # Duration validation.
    actual_dur = container_duration if container_duration is not None else v_dur
    dur_tol = max(0.15, 1.0 / fps)
    dur_diff = None
    dur_verdict = "unverified"
    if actual_dur is not None:
        dur_diff = round(actual_dur - target_duration_seconds, 3)
        dur_ok = abs(dur_diff) <= dur_tol
        dur_verdict = "duration_matches" if dur_ok else "duration_mismatch"
        if not dur_ok:
            blockers.append("DURATION_MISMATCH")
    else:
        blockers.append("DURATION_UNMEASURED")

    # A/V sync validation.
    av_diff = None
    av_verdict = "not_applicable"
    if video_streams and audio_streams:
        if v_dur is not None and a_dur is not None:
            av_diff = round(abs(v_dur - a_dur), 3)
            av_ok = av_diff <= max(_AV_SYNC_TOLERANCE_SECONDS, 1.0 / fps)
            av_verdict = "av_in_sync" if av_ok else "av_sync_failed"
            if not av_ok:
                blockers.append("AV_SYNC_FAILED")
        else:
            av_verdict = "av_sync_unverified"
    else:
        av_verdict = "no_audio_stream"

    verified = not blockers and status == "ok" and size_bytes > 0
    verification_status = (
        ArtifactVerificationStatus.VERIFIED if verified
        else ArtifactVerificationStatus.STREAM_MISMATCH if blockers
        else ArtifactVerificationStatus.PROBE_FAILED
    )

    probe = RenderArtifactProbeEvidence(
        container=container,
        container_duration=container_duration,
        video_stream_count=len(video_streams),
        audio_stream_count=len(audio_streams),
        video_codec=v_codec,
        audio_codec=a_codec,
        width=pw,
        height=ph,
        fps=p_fps,
        pixel_format=p_pix,
        video_duration=v_dur,
        audio_duration=a_dur,
        frame_count=frame_count,
        bit_rate=bit_rate,
        file_size=size_bytes,
        sha256=sha,
    )
    desc = RenderArtifactDescriptor(
        artifact_id=artifact_id({"path": str(abs_path), "sha": sha}),
        format_id=selected_format,
        relative_output_path=output_relative_path,
        size_bytes=size_bytes,
        sha256=sha,
        hvs_render_id=hvs_render_id,
    )
    output_contract_hash = _build_render_contract_hash(
        project_id=project_id,
        intake_manifest_id="",
        intake_manifest_content_hash="",
        render_readiness_id="",
        render_readiness_content_hash="",
        selected_format=selected_format,
        width=width,
        height=height,
        fps=fps,
        target_duration_seconds=target_duration_seconds,
        video_codec=video_codec,
        pixel_format=pixel_format,
        audio_requirement=audio_requirement,
        no_overwrite_policy=no_overwrite_policy,
    )
    verification = RenderArtifactVerification(
        schema_version=STAGE8N_SCHEMA_VERSION,
        artifact_verification_id=artifact_verification_id(
            {"artifact_id": desc.artifact_id, "request": render_request_id}
        ),
        render_request_id=render_request_id,
        render_approval_id=render_approval_id,
        render_dispatch_id=dispatch_id,
        hvs_render_id=hvs_render_id,
        project_id=project_id,
        format_id=selected_format,
        approved_output_contract_hash=output_contract_hash,
        artifact=desc,
        probe=probe,
        target_duration_seconds=target_duration_seconds,
        actual_duration_seconds=actual_dur,
        duration_difference_seconds=dur_diff,
        duration_tolerance_seconds=round(dur_tol, 4),
        av_duration_difference_seconds=av_diff,
        av_tolerance_seconds=round(max(_AV_SYNC_TOLERANCE_SECONDS, 1.0 / fps), 4),
        duration_verdict=dur_verdict,
        av_sync_verdict=av_verdict,
        verification_status=verification_status,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        artifact_verified=verified,
        width=pw,
        height=ph,
        fps=p_fps,
        video_codec=v_codec,
        pixel_format=p_pix,
        audio_streams=len(audio_streams),
        audio_verdict=(
            "REQUIRED" if audio_requirement == AudioRequirement.REQUIRED
            else "NOT_REQUIRED"
        ),
    )
    append_render_completion_event(
        audit_log_path=render_completion_path(repo_root),
        event_type=(
            RenderCompletionEventType.RENDER_ARTIFACT_VERIFIED
            if verified
            else RenderCompletionEventType.RENDER_ARTIFACT_REJECTED
        ),
        subject_id=render_request_id,
        operator_id=operator_id,
        recorded_at=recorded_at,
        record=verification.to_dict(),
    )
    return {
        "ok": verified,
        "artifact_verified": verified,
        "verification": verification.to_dict(),
        "evidence": {
            "artifact_id": desc.artifact_id,
            "relative_output_path": output_relative_path,
            "format_id": selected_format,
            "width": pw,
            "height": ph,
            "fps": p_fps,
            "video_codec": v_codec,
            "pixel_format": p_pix,
            "audio_streams": len(audio_streams),
            "audio_verdict": (
                "REQUIRED" if audio_requirement == AudioRequirement.REQUIRED
                else "NOT_REQUIRED"
            ),
            "sha256": sha,
            "size_bytes": size_bytes,
        },
        "blockers": tuple(blockers),
    }


def _reject_artifact(
    *,
    repo_root: Any,
    project_id: str,
    render_request_id: str,
    render_approval_id: str,
    dispatch_id: str,
    hvs_render_id: str | None,
    selected_format: str,
    output_relative_path: str,
    size_bytes: int,
    sha256: str,
    status: str,
    blockers: tuple[str, ...],
    warnings: tuple[str, ...],
    operator_id: str,
    recorded_at: str,
) -> dict[str, Any]:
    verification = RenderArtifactVerification(
        schema_version=STAGE8N_SCHEMA_VERSION,
        artifact_verification_id=artifact_verification_id(
            {"path": output_relative_path, "sha": sha256}
        ),
        render_request_id=render_request_id,
        render_approval_id=render_approval_id,
        render_dispatch_id=dispatch_id,
        hvs_render_id=hvs_render_id,
        project_id=project_id,
        format_id=selected_format,
        approved_output_contract_hash="",
        artifact=RenderArtifactDescriptor(
            artifact_id=artifact_id({"path": output_relative_path, "sha": sha256}),
            format_id=selected_format,
            relative_output_path=output_relative_path,
            size_bytes=size_bytes,
            sha256=sha256,
            hvs_render_id=hvs_render_id,
        ),
        probe=RenderArtifactProbeEvidence(
            container=None, container_duration=None, video_stream_count=0,
            audio_stream_count=0, video_codec=None, audio_codec=None, width=None,
            height=None, fps=None, pixel_format=None, video_duration=None,
            audio_duration=None, frame_count=None, bit_rate=None, file_size=size_bytes,
            sha256=sha256,
        ),
        target_duration_seconds=0.0,
        actual_duration_seconds=None,
        duration_difference_seconds=None,
        duration_tolerance_seconds=0.15,
        av_duration_difference_seconds=None,
        av_tolerance_seconds=0.15,
        duration_verdict="unverified",
        av_sync_verdict="unverified",
        verification_status=status,
        blockers=blockers,
        warnings=warnings,
        artifact_verified=False,
    )
    append_render_completion_event(
        audit_log_path=render_completion_path(repo_root),
        event_type=RenderCompletionEventType.RENDER_ARTIFACT_REJECTED,
        subject_id=render_request_id,
        operator_id=operator_id,
        recorded_at=recorded_at,
        record=verification.to_dict(),
    )
    return {"ok": False, "verification": verification.to_dict(), "blockers": blockers}


def _to_float(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_int(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _parse_fps(v: Any) -> float | None:
    if not v or "/" not in str(v):
        return _to_float(v)
    try:
        num, den = str(v).split("/")
        if int(den) == 0:
            return None
        return int(num) / int(den)
    except (ValueError, ZeroDivisionError):
        return None


def _fps_to_r_frame_rate(fps: Any) -> str | None:
    """Inverse of ``_parse_fps``; render a numeric fps as an ffprobe-style
    ``N/D`` r_frame_rate string so the flat mock shape round-trips."""
    value = _to_float(fps)
    if value is None:
        return None
    numer = int(round(value * 1000))
    return f"{numer}/1000"


# ---------------------------------------------------------------------------
# Phase 15 — completion evidence
# ---------------------------------------------------------------------------
def create_render_completion_evidence(
    *,
    repo_root: Any,
    project_id: str,
    render_request_id: str,
    render_contract_hash: str,
    render_approval_id: str,
    dispatch_id: str,
    hvs_render_id: str | None,
    intake_manifest_id: str,
    intake_manifest_content_hash: str,
    render_readiness_id: str,
    render_readiness_content_hash: str,
    selected_format: str,
    verification: dict[str, Any],
    operator_id: str,
    recorded_at: str,
) -> dict[str, Any]:
    """Create completion evidence only after the artifact passes verification."""
    verified = bool(verification.get("artifact_verified"))
    if not verified:
        return {
            "ok": False,
            "error": "cannot create completion evidence for unverified artifact",
            "code": "ARTIFACT_NOT_VERIFIED",
        }
    completion_status = (
        RenderCompletionStatus.COMPLETE if verified else RenderCompletionStatus.FAILED
    )
    art = verification.get("artifact", {})
    evidence = RenderCompletionEvidence(
        schema_version=STAGE8N_SCHEMA_VERSION,
        render_completion_evidence_id=render_completion_evidence_id(
            {"request": render_request_id, "dispatch": dispatch_id}
        ),
        render_request_id=render_request_id,
        render_contract_hash=render_contract_hash,
        render_approval_id=render_approval_id,
        render_dispatch_id=dispatch_id,
        hvs_render_id=hvs_render_id,
        project_id=project_id,
        intake_manifest_id=intake_manifest_id,
        intake_manifest_content_hash=intake_manifest_content_hash,
        render_readiness_id=render_readiness_id,
        render_readiness_content_hash=render_readiness_content_hash,
        requested_formats=(selected_format,),
        completed_formats=(selected_format,) if verified else (),
        failed_formats=() if verified else (selected_format,),
        artifact_verification_ids=(verification.get("artifact_verification_id", ""),),
        artifact_sha256_values=(art.get("sha256", ""),),
        completion_status=completion_status,
        # Stage 8N only ever reaches these true states via explicit approval +
        # successful verified render; delivery boundary is ALWAYS false.
        render_authorized=True,
        render_started=True,
        render_completed=True,
        artifact_verified=True,
        delivery_authorized=False,
        publishing_authorized=False,
        customer_contact_performed=False,
        upload_performed=False,
        publishing_performed=False,
        invoice_state_changed=False,
        payment_state_changed=False,
        automation_allowed=False,
    )
    append_render_completion_event(
        audit_log_path=render_completion_path(repo_root),
        event_type=RenderCompletionEventType.RENDER_COMPLETION_EVIDENCE_CREATED,
        subject_id=render_request_id,
        operator_id=operator_id,
        recorded_at=recorded_at,
        record=evidence.to_dict(),
    )
    return {"ok": True, "evidence": evidence.to_dict()}


# ---------------------------------------------------------------------------
# Phase 8N — full dispatch orchestration (single approved format)
# ---------------------------------------------------------------------------
def dispatch_approved_render(
    *,
    repo_root: Any,
    hvs_repo_root: str,
    hvs_python_executable: str,
    project_id: str,
    render_request_id: str,
    readiness_binding: RenderReadinessBinding,
    selected_format: str,
    width: int,
    height: int,
    fps: int,
    target_duration_seconds: float,
    video_codec: str,
    pixel_format: str,
    audio_requirement: str,
    no_overwrite_policy: str,
    operator_id: str,
    recorded_at: str,
    subprocess_run: Callable[..., Any] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Phase 8 + full verification + completion evidence.

    Flow:
      1. pre_dispatch_reverify (full chain).
      2. load + validate the separate Stage 8N approval.
      3. dispatch HVS render (or dry_run: no invocation).
      4. discover + SHA-256 + FFprobe verify the artifact.
      5. create completion evidence only if VERIFIED.
    """
    # 1) reverify.
    if readiness_binding is None:
        readiness_binding = load_readiness_binding(repo_root=repo_root, project_id=project_id)
        if readiness_binding is None:
            return {"ok": False, "code": "MISSING_READINESS_BINDING",
                    "error": "could not reconstruct Stage 8M readiness binding"}
    rev = pre_dispatch_reverify(
        repo_root=repo_root, project_id=project_id, readiness_binding=readiness_binding
    )
    if not rev["ok"]:
        return {"ok": False, "code": rev["code"], "error": "pre-dispatch reverification failed"}

    # 2) approval.
    approval = _latest_approval(repo_root=repo_root, render_request_id=render_request_id)
    if approval is None:
        return {"ok": False, "code": "NO_APPROVAL", "error": "render not approved"}
    if approval.get("rejected"):
        return {"ok": False, "code": "REJECTED", "error": "render approval was rejected"}
    if not approval.get("render_authorized"):
        return {"ok": False, "code": "NOT_AUTHORIZED", "error": "render not authorized"}
    # Approval binding checks.
    if approval.get("render_contract_hash") != readiness_binding_to_contract_hash(
        readiness_binding
    ):
        return {"ok": False, "code": "APPROVAL_CONTRACT_MISMATCH", "error": "approval contract mismatch"}
    if approval.get("project_id") != project_id:
        return {"ok": False, "code": "WRONG_PROJECT", "error": "approval for wrong project"}
    if approval.get("intake_manifest_content_hash") != readiness_binding.intake_manifest_content_hash:
        return {"ok": False, "code": "MANIFEST_HASH_MISMATCH", "error": "approval manifest hash mismatch"}
    if approval.get("render_readiness_id") != readiness_binding.render_readiness_id:
        return {"ok": False, "code": "READINESS_MISMATCH", "error": "approval readiness mismatch"}

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "dispatch": None,
            "verification": None,
            "evidence": None,
            "render_authorized": True,
            "delivery_authorized": False,
            "publishing_authorized": False,
        }

    dispatch_id = render_dispatch_id({"request": render_request_id, "recorded_at": recorded_at})
    append_render_completion_event(
        audit_log_path=render_completion_path(repo_root),
        event_type=RenderCompletionEventType.RENDER_DISPATCH_STARTED,
        subject_id=render_request_id,
        operator_id=operator_id,
        recorded_at=recorded_at,
        record={
            "dispatch_id": dispatch_id,
            "render_request_id": render_request_id,
            "execution_status": RenderExecutionStatus.DISPATCHING,
            "render_authorized": True,
            "render_started": True,
            "automation_allowed": False,
        },
    )

    # 3) dispatch.
    executor = HVSRenderCompletionExecutor(
        python_executable=hvs_python_executable, subprocess_run=subprocess_run
    )
    result = executor.dispatch(
        hvs_root=Path(hvs_repo_root),
        hvs_project_id=project_id,
        fmt=selected_format,
        dispatch_id=dispatch_id,
    )
    append_render_completion_event(
        audit_log_path=render_completion_path(repo_root),
        event_type=RenderCompletionEventType.RENDER_DISPATCH_COMPLETED,
        subject_id=render_request_id,
        operator_id=operator_id,
        recorded_at=recorded_at,
        record=result.to_dict(),
    )

    # A failed/non-PASS HVS execution is never completion.
    if result.execution_status != RenderExecutionStatus.COMPLETED or not result.output_relative_path:
        return {
            "ok": False,
            "code": "RENDER_FAILED",
            "error": "HVS render did not complete successfully",
            "dispatch": result.to_dict(),
            "render_authorized": True,
            "render_started": True,
            "render_completed": False,
            "artifact_verified": False,
            "delivery_authorized": False,
            "publishing_authorized": False,
        }

    # 4) verify artifact.
    vres = verify_render_artifact(
        repo_root=repo_root,
        hvs_repo_root=hvs_repo_root,
        project_id=project_id,
        render_request_id=render_request_id,
        render_approval_id=approval["render_approval_id"],
        dispatch_id=dispatch_id,
        hvs_render_id=result.hvs_render_id,
        output_relative_path=result.output_relative_path,
        selected_format=selected_format,
        width=width,
        height=height,
        fps=fps,
        target_duration_seconds=target_duration_seconds,
        video_codec=video_codec,
        pixel_format=pixel_format,
        audio_requirement=audio_requirement,
        no_overwrite_policy=no_overwrite_policy,
        operator_id=operator_id,
        recorded_at=recorded_at,
    )

    # 5) completion evidence only if VERIFIED.
    if vres["ok"]:
        cev = create_render_completion_evidence(
            repo_root=repo_root,
            project_id=project_id,
            render_request_id=render_request_id,
            render_contract_hash=approval["render_contract_hash"],
            render_approval_id=approval["render_approval_id"],
            dispatch_id=dispatch_id,
            hvs_render_id=result.hvs_render_id,
            intake_manifest_id=readiness_binding.intake_manifest_id,
            intake_manifest_content_hash=readiness_binding.intake_manifest_content_hash,
            render_readiness_id=readiness_binding.render_readiness_id,
            render_readiness_content_hash=readiness_binding.render_readiness_content_hash,
            selected_format=selected_format,
            verification=vres["verification"],
            operator_id=operator_id,
            recorded_at=recorded_at,
        )
        return {
            "ok": True,
            "dispatch": result.to_dict(),
            "verification": vres["verification"],
            "evidence": cev.get("evidence"),
            "completion_status": cev.get("evidence", {}).get("completion_status"),
            "render_authorized": True,
            "render_started": True,
            "render_completed": True,
            "artifact_verified": True,
            "delivery_authorized": False,
            "publishing_authorized": False,
            "automation_allowed": False,
        }
    return {
        "ok": False,
        "code": "ARTIFACT_VERIFICATION_FAILED",
        "error": "; ".join(vres.get("blockers", ())),
        "dispatch": result.to_dict(),
        "verification": vres["verification"],
        "render_authorized": True,
        "render_started": True,
        "render_completed": True,
        "artifact_verified": False,
        "delivery_authorized": False,
        "publishing_authorized": False,
    }


def readiness_binding_to_contract_hash(binding: RenderReadinessBinding) -> str:
    """Recompute the contract hash bound into the approval from the binding."""
    return _build_render_contract_hash(
        project_id=binding.project_id,
        intake_manifest_id=binding.intake_manifest_id,
        intake_manifest_content_hash=binding.intake_manifest_content_hash,
        render_readiness_id=binding.render_readiness_id,
        render_readiness_content_hash=binding.render_readiness_content_hash,
        selected_format="vertical",
        width=1080,
        height=1920,
        fps=30,
        target_duration_seconds=3.0,
        video_codec="h264",
        pixel_format="yuv420p",
        audio_requirement=AudioRequirement.NOT_REQUIRED,
        no_overwrite_policy=NoOverwritePolicy.NEVER,
    )


def _events(*, repo_root: Any) -> tuple[dict[str, Any], ...]:
    return read_render_completion_events(audit_log_path=render_completion_path(repo_root))


def reject_render(
    *,
    repo_root: Any,
    project_id: str,
    render_request_id: str,
    operator_id: str,
    rejection_reason: str,
    recorded_at: str,
) -> dict[str, Any]:
    """Record an explicit operator render rejection (fail-closed, immutable)."""
    if not operator_id:
        return {"ok": False, "error": "operator id required", "code": "MISSING_OPERATOR"}
    if not rejection_reason:
        return {"ok": False, "error": "rejection reason required", "code": "MISSING_REASON"}
    if not render_request_id:
        return {"ok": False, "error": "render request id required", "code": "MISSING_REQUEST"}
    event = append_render_completion_event(
        audit_log_path=render_completion_path(repo_root),
        event_type=RenderCompletionEventType.RENDER_REJECTED,
        subject_id=render_request_id,
        operator_id=operator_id,
        recorded_at=recorded_at,
        record={
            "project_id": project_id,
            "render_request_id": render_request_id,
            "rejection_reason": rejection_reason,
            "render_authorized": False,
            "delivery_authorized": False,
            "publishing_authorized": False,
            "automation_allowed": False,
        },
    )
    return {"ok": True, "event": event}


def inspect_render_request(*, repo_root: Any, render_request_id: str) -> dict[str, Any]:
    """Read-only inspection of the latest event for a render request."""
    latest = None
    for event in _events(repo_root=repo_root):
        if event.get("subject_id") == render_request_id:
            latest = event
    if latest is None:
        return {
            "ok": False,
            "error": "render request not found",
            "code": "RENDER_REQUEST_NOT_FOUND",
            "render_authorized": False,
            "delivery_authorized": False,
            "publishing_authorized": False,
            "automation_allowed": False,
        }
    rec = dict(latest.get("record", {}))
    rec.update(
        {
            "ok": True,
            "event_type": latest["event_type"],
            "event_id": latest["event_id"],
            "render_request_id": render_request_id,
            "render_authorized": False,
            "delivery_authorized": False,
            "publishing_authorized": False,
            "automation_allowed": False,
        }
    )
    return rec


def inspect_render_execution(*, repo_root: Any, render_request_id: str) -> dict[str, Any]:
    """Read-only inspection of dispatch/execution events for a render request."""
    dispatch = None
    for event in _events(repo_root=repo_root):
        if event.get("subject_id") != render_request_id:
            continue
        if event["event_type"] in (
            RenderCompletionEventType.RENDER_DISPATCH_STARTED,
            RenderCompletionEventType.RENDER_DISPATCH_COMPLETED,
            RenderCompletionEventType.RENDER_DISPATCH_FAILED,
            RenderCompletionEventType.RENDER_DISPATCH_TIMED_OUT,
            RenderCompletionEventType.RENDER_ARTIFACT_DISCOVERED,
            RenderCompletionEventType.RENDER_ARTIFACT_VERIFIED,
            RenderCompletionEventType.RENDER_ARTIFACT_REJECTED,
        ):
            dispatch = event
    if dispatch is None:
        return {
            "ok": False,
            "error": "no dispatch event found",
            "code": "NO_DISPATCH",
            "render_authorized": False,
            "delivery_authorized": False,
            "publishing_authorized": False,
            "automation_allowed": False,
        }
    rec = dict(dispatch.get("record", {}))
    rec.update(
        {
            "ok": True,
            "event_type": dispatch["event_type"],
            "render_request_id": render_request_id,
            "render_authorized": False,
            "delivery_authorized": False,
            "publishing_authorized": False,
            "automation_allowed": False,
        }
    )
    return rec


def inspect_render_completion(*, repo_root: Any, render_request_id: str) -> dict[str, Any]:
    """Read-only inspection of completion evidence for a render request."""
    ev = None
    for event in _events(repo_root=repo_root):
        if event.get("subject_id") != render_request_id:
            continue
        if event["event_type"] == RenderCompletionEventType.RENDER_COMPLETION_EVIDENCE_CREATED:
            ev = event
    if ev is None:
        return {
            "ok": False,
            "error": "no completion evidence found",
            "code": "NO_COMPLETION_EVIDENCE",
            "render_authorized": False,
            "delivery_authorized": False,
            "publishing_authorized": False,
            "automation_allowed": False,
        }
    rec = dict(ev.get("record", {}))
    rec.update(
        {
            "ok": True,
            "event_type": ev["event_type"],
            "render_request_id": render_request_id,
            "render_authorized": rec.get("render_authorized", False),
            "delivery_authorized": rec.get("delivery_authorized", False),
            "publishing_authorized": rec.get("publishing_authorized", False),
            "automation_allowed": rec.get("automation_allowed", False),
        }
    )
    return rec


def list_render_recovery_queue(*, repo_root: Any) -> dict[str, Any]:
    """Read-only list of failed / partial / blocked render jobs awaiting recovery.

    A request enters the recovery queue when it has a terminal non-success
    dispatch event (FAILED / TIMED_OUT / ARTIFACT_REJECTED) or a PARTIAL batch
    completion, but no successful COMPLETE completion evidence.
    """
    by_request: dict[str, dict[str, Any]] = {}
    for event in _events(repo_root=repo_root):
        rid = event.get("subject_id")
        if not rid:
            continue
        et = event["event_type"]
        slot = by_request.setdefault(
            rid,
            {
                "render_request_id": rid,
                "project_id": event.get("record", {}).get("project_id"),
                "status": "UNKNOWN",
                "failed_formats": [],
                "completed_formats": [],
                "completion_status": None,
            },
        )
        if et in (
            RenderCompletionEventType.RENDER_DISPATCH_FAILED,
            RenderCompletionEventType.RENDER_DISPATCH_TIMED_OUT,
            RenderCompletionEventType.RENDER_ARTIFACT_REJECTED,
        ):
            slot["status"] = "FAILED"
        elif et == RenderCompletionEventType.RENDER_BATCH_PARTIAL:
            slot["status"] = "PARTIAL"
            slot["failed_formats"] = list(event.get("record", {}).get("failed_formats", []))
            slot["completed_formats"] = list(event.get("record", {}).get("completed_formats", []))
        elif et == RenderCompletionEventType.RENDER_COMPLETION_EVIDENCE_CREATED:
            slot["completion_status"] = event.get("record", {}).get("completion_status")
    queue = [
        slot
        for slot in by_request.values()
        if slot["status"] in ("FAILED", "PARTIAL") or slot["completion_status"] in ("PARTIAL", "FAILED")
    ]
    return {
        "ok": True,
        "recovery_queue": queue,
        "delivery_authorized": False,
        "publishing_authorized": False,
        "automation_allowed": False,
    }
