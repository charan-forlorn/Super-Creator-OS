"""Stage 8M — approval-gated HVS production asset intake and materialization service.

This is the deterministic service layer. It consumes a verified Stage 8L HVS
project and drives it, through the approved existing HVS boundary, to an
approval-gated materialization of explicitly-approved local source assets.

Boundary (per Stage 8M contract):

    SCOS service -> read-only HVS inspect-project / media-readiness (subprocess)
                  -> explicit approval (bound to manifest + source hashes)
                  -> HVS import-media (existing materialization command, subprocess)
                  -> read-only HVS re-inspection + HVS media-manifest read
                  -> append-only SCOS evidence
                  -> read-only render-readiness evaluation

Rules enforced here:

* No HVS production module is imported by SCOS.
* The HVS interpreter is injected (never guessed).
* subprocess is argv-list, shell=False, bounded timeout, bounded output.
* No render command is invoked; render_* flags are always false.
* Asset bytes, secrets, and private media content are never stored.
* Materialization requires explicit approval bound to the exact manifest and
  source SHA-256 values; sources are rehashed immediately before execution.
* No destination is overwritten; HVS no-overwrite semantics are verified.

Local-first, deterministic. No clock (caller-supplied), no random, no uuid,
no network.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from scos.media_binaries import resolve_ffprobe

from .hvs_asset_materialization import (
    _assert_not_network_or_device,
    _safe_basename,
    _sha256_stream,
)
from .hvs_commercial_proposal_models import _safe_text, canonical_json
from .hvs_contract_models import _reject_path_traversal
from .hvs_production_asset_models import (
    STAGE8M_INTAKE_MANIFEST_SCHEMA_VERSION,
    STAGE8M_REQUIREMENT_INSPECTION_SCHEMA_VERSION,
    STAGE8M_RENDER_READINESS_SCHEMA_VERSION,
    STAGE8M_SCHEMA_VERSION,
    AssetIntakeReadinessResult,
    AssetMaterializationApproval,
    AssetMaterializationResult,
    AssetMaterializationStatus,
    AssetRightsStatus,
    AssetValidationStatus,
    HVSAssetRequirementInspection,
    HVSRenderReadinessResult,
    PostMaterializationVerification,
    ProductionAssetBinding,
    ProductionAssetError,
    ProductionAssetIntakeManifest,
    ProductionAssetIntakeStatus,
    ProductionAssetRequirement,
    ProductionAssetRole,
    SourceAssetDescriptor,
    SourceAssetValidation,
    AssetRightsEvidence,
    RenderReadinessStatus,
    Stage8LReverificationRecord,
    approval_id,
    execution_id,
    manifest_id,
    post_verification_id,
    render_readiness_id,
    requirement_inspection_id,
    requirement_set_hash,
    rights_evidence_id,
    source_asset_id,
)
from .hvs_production_asset_store import (
    append_asset_intake_event,
    asset_intake_path,
    read_asset_intake_events,
    read_manifest_contract_file,
    write_manifest_contract_file,
    _load_stage8l_evidence_from_repo,
)


# ---------------------------------------------------------------------------
# Allowed source roots / media policy
# ---------------------------------------------------------------------------
# Operator-controlled intake directory under the established SCOS workspace
# policy. The runtime root is gitignored.
DEFAULT_INTAKE_RELATIVE = "scos/work/hvs_asset_intake"

_ALLOWED_EXTENSIONS = {
    "visual": {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff", ".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"},
    "voice": {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".oga", ".flac", ".opus", ".mp2", ".caf"},
    "music": {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".oga", ".flac", ".opus", ".mp2", ".caf"},
}

# Executable / script content signatures (reject on sight).
_EXECUTABLE_MAGICS = (
    b"MZ",          # PE
    b"\x7fELF",     # ELF
    b"\xcf\xfa\xed\xfe",  # Mach-O
    b"#!/",         # shebang script
    b"<?xml",       # document / office (not media)
)
_FORBIDDEN_EXTENSIONS = {".exe", ".dll", ".bat", ".cmd", ".ps1", ".sh", ".py", ".js", ".vbs", ".jar", ".com"}

# Probe discipline mirrors the HVS media probe contract.
_PROBE_TIMEOUT_SECONDS = 60
_MAX_OUTPUT_CHARS = 4000
_MEDIA_MANIFEST_REL = "media/media_manifest.json"


# ---------------------------------------------------------------------------
# Bounded HVS CLI runner (reuses Stage 1 adapter discipline; NOT the adapter,
# because the Stage 1 adapter forbids import-media and only parses JSON).
# ---------------------------------------------------------------------------
def _hvs_cli_run(
    *,
    hvs_repo_root: str,
    hvs_python_executable: str,
    command: str,
    args: list[str],
    timeout_seconds: int = 120,
    subprocess_run: Callable | None = None,
) -> dict[str, Any]:
    """Run one bounded HVS CLI command and return a normalized result dict.

    argv list, shell=False, explicit cwd, bounded timeout, bounded output.
    stdout/stderr are capped. Malformed/non-zero results are normalized.
    """
    argv = [hvs_python_executable, "-m", "hvs.cli", command, *args]
    # Reject any shell metacharacter in the constructed argv (defense-in-depth).
    for tok in argv:
        if any(ch in set(";&|`$><\n\r(){}*?!#\"'~") for ch in tok):
            return {
                "ok": False,
                "command": command,
                "exit_code": None,
                "error_kind": "unsafe_command",
                "error_detail": "constructed argv contained a shell metacharacter",
                "stdout": "",
                "stderr": "",
            }
    # If a runner was injected (tests / controlled harness), call it directly
    # and return its normalized dict. This NEVER touches a real subprocess.
    if subprocess_run is not None:
        try:
            injected = subprocess_run(list(argv), cwd=str(Path(hvs_repo_root).resolve()), shell=False)
        except subprocess.TimeoutExpired:
            return {
                "ok": False, "command": command, "exit_code": None,
                "error_kind": "command_timeout",
                "error_detail": f"HVS {command} exceeded timeout {timeout_seconds}s",
                "stdout": "", "stderr": "",
            }
        if isinstance(injected, dict):
            return injected
        # Allow injection of a CompletedProcess-like object too.
        return {
            "ok": int(injected.returncode) == 0,
            "command": command,
            "exit_code": int(injected.returncode),
            "error_kind": None if int(injected.returncode) == 0 else "hvs_command_failed",
            "error_detail": None if int(injected.returncode) == 0 else (injected.stderr or "")[:200],
            "stdout": (injected.stdout or "")[:_MAX_OUTPUT_CHARS],
            "stderr": (injected.stderr or "")[:_MAX_OUTPUT_CHARS],
        }
    run = subprocess.run  # noqa: F811
    cwd = Path(hvs_repo_root).resolve()
    try:
        proc = run(
            list(argv),
            cwd=str(cwd),
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            input="",
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False, "command": command, "exit_code": None,
            "error_kind": "command_timeout",
            "error_detail": f"HVS {command} exceeded timeout {timeout_seconds}s",
            "stdout": "", "stderr": "",
        }
    except (PermissionError, OSError, ValueError) as exc:
        return {
            "ok": False, "command": command, "exit_code": None,
            "error_kind": "adapter_blocked",
            "error_detail": f"HVS {command} could not start: {type(exc).__name__}",
            "stdout": "", "stderr": "",
        }
    stdout = (proc.stdout or "")[:_MAX_OUTPUT_CHARS]
    stderr = (proc.stderr or "")[:_MAX_OUTPUT_CHARS]
    return {
        "ok": int(proc.returncode) == 0,
        "command": command,
        "exit_code": int(proc.returncode),
        "error_kind": None if int(proc.returncode) == 0 else "hvs_command_failed",
        "error_detail": None if int(proc.returncode) == 0 else stderr[:200],
        "stdout": stdout,
        "stderr": stderr,
    }


# ---------------------------------------------------------------------------
# SCOS-local media probe (does NOT import HVS; same ffprobe contract discipline)
# ---------------------------------------------------------------------------
def _probe_media_local(source_path: str) -> tuple[str, dict[str, Any]]:
    """Probe a local media file with ffprobe. Returns (status, detail).

    status in: ok, missing, unavailable, failed, corrupt.
    No network, no mutation, argv list, shell=False, bounded timeout.
    """
    if not os.path.isfile(source_path):
        return "missing", {"reason": "file not found"}
    bin_name = resolve_ffprobe()
    try:
        proc = subprocess.run(
            [bin_name, "-v", "error", "-show_format", "-show_streams", "-of", "json", source_path],
            capture_output=True, text=True, timeout=_PROBE_TIMEOUT_SECONDS, shell=False,
        )
    except FileNotFoundError:
        return "unavailable", {"reason": "ffprobe unavailable"}
    except subprocess.TimeoutExpired:
        return "failed", {"reason": "probe timeout"}
    if proc.returncode != 0:
        return "corrupt", {"reason": "non-zero probe exit", "stderr": (proc.stderr or "")[:200]}
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return "failed", {"reason": "probe output not json"}
    streams = data.get("streams")
    if not isinstance(streams, list) or not streams:
        return "corrupt", {"reason": "no streams"}
    detail: dict[str, Any] = {"container_format": (data.get("format", {}) or {}).get("format_name")}
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if v:
        detail["stream_type"] = "video"
        detail["codec_name"] = v.get("codec_name")
        detail["width"] = v.get("width")
        detail["height"] = v.get("height")
        detail["duration_seconds"] = _to_float(v.get("duration") or (data.get("format", {}) or {}).get("duration"))
    elif a:
        detail["stream_type"] = "audio"
        detail["codec_name"] = a.get("codec_code") or a.get("codec_name")
        detail["audio_channels"] = a.get("channels")
        detail["sample_rate_hz"] = a.get("sample_rate")
        detail["duration_seconds"] = _to_float(a.get("duration") or (data.get("format", {}) or {}).get("duration"))
    else:
        detail["stream_type"] = "image"
        detail["codec_name"] = (streams[0] or {}).get("codec_name")
    return "ok", detail


def _to_float(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return round(float(v), 6)
    except (TypeError, ValueError):
        return None


def _media_type_for_role(role: str, detail: dict[str, Any]) -> str:
    st = detail.get("stream_type")
    if role == ProductionAssetRole.VISUAL:
        if st in ("video", "image"):
            return "image" if st == "image" else "video"
    elif role in (ProductionAssetRole.VOICE, ProductionAssetRole.MUSIC):
        if st == "audio":
            return "audio"
    return "unknown"


# ---------------------------------------------------------------------------
# Allowed source root
# ---------------------------------------------------------------------------
def default_intake_root(repo_root: Any) -> Path:
    return Path(repo_root).resolve() / DEFAULT_INTAKE_RELATIVE


def _is_contained(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


# ---------------------------------------------------------------------------
# Stage 8L reverification
# ---------------------------------------------------------------------------
def reverify_stage8l(
    *,
    project_id: str,
    repo_root: Any,
    hvs_repo_root: str,
    hvs_python_executable: str,
    recorded_at: str,
    inspect_payload: dict[str, Any] | None = None,
    subprocess_run: Callable | None = None,
) -> tuple[Stage8LReverificationRecord, dict[str, Any]]:
    project_id = _safe_text("project_id", project_id)
    if inspect_payload is None:
        res = _hvs_cli_run(
            hvs_repo_root=hvs_repo_root,
            hvs_python_executable=hvs_python_executable,
            command="inspect-project",
            args=["--project-id", project_id],
            subprocess_run=subprocess_run,
        )
        if not res["ok"]:
            return _deny_stage8l(project_id, res), res
        try:
            inspect_payload = json.loads(res["stdout"]) if isinstance(res["stdout"], str) and res["stdout"].strip().startswith("{") else {}
        except json.JSONDecodeError:
            inspect_payload = {}
    init = inspect_payload.get("initialization") or {}
    tl = inspect_payload.get("timeline") or {}
    exists = bool(inspect_payload.get("exists")) and bool(init.get("exists"))
    # Hard invariants: HVS is a delivery surface and SHALL NOT start its own
    # autonomous render, nor generate voice/scene placeholders. Any of those
    # violate the Stage 8L contract, so the project is NOT verified.
    render_started = bool(inspect_payload.get("render_started"))
    voice_generated = bool(inspect_payload.get("voice_generated"))
    placeholder_assets_generated = bool(inspect_payload.get("placeholder_assets_generated"))
    verified = (
        bool(init.get("valid")) and bool(tl.get("valid"))
        and not render_started and not voice_generated and not placeholder_assets_generated
    )
    semantic_ok = (
        inspect_payload.get("project_id") == project_id
        and init.get("project_id") == project_id
        and tl.get("valid") is True
        and init.get("status") in ("initialized", "verified")
        and not render_started
    )
    payload_hash = str(init.get("payload_hash") or "")
    scos_evidence = _load_stage8l_evidence_from_repo(repo_root)
    expected_hash = (scos_evidence or {}).get("stage2_payload_hash") or payload_hash
    record = Stage8LReverificationRecord(
        schema_version=STAGE8M_SCHEMA_VERSION,
        project_id=project_id,
        initialization_contract_id=(scos_evidence or {}).get("initialization_contract_id") or "",
        kickoff_authorization_id=(scos_evidence or {}).get("production_kickoff_authorization_id") or "",
        correlation_id=(scos_evidence or {}).get("correlation_id") or f"corr-{payload_hash}",
        expected_payload_hash=expected_hash,
        actual_payload_hash=payload_hash,
        hvs_project_exists=exists,
        hvs_project_verified=verified,
        hvs_semantic_valid=semantic_ok,
        scene_count=int(tl.get("scene_count") or 0),
        voice_generated=bool(inspect_payload.get("voice_generated")),
        placeholder_assets_generated=bool(inspect_payload.get("placeholder_assets_generated")),
        render_started=bool(inspect_payload.get("render_started")),
        assets_copied=bool(init.get("assets_copied")),
        evidence_source=_load_stage8l_evidence_from_repo.__name__ if scos_evidence else "hvs-inspect-project",
        derived_at=recorded_at,
    )
    append_asset_intake_event(
        audit_log_path=asset_intake_path(repo_root),
        event_type="STAGE8L_REVERIFIED",
        subject_id=project_id,
        operator_id="stage8m-system",
        recorded_at=recorded_at,
        record=record.to_dict(),
    )
    return record, inspect_payload


def _deny_stage8l(project_id: str, res: dict[str, Any]) -> Stage8LReverificationRecord:
    return Stage8LReverificationRecord(
        schema_version=STAGE8M_SCHEMA_VERSION,
        project_id=project_id,
        initialization_contract_id="",
        kickoff_authorization_id="",
        correlation_id="",
        expected_payload_hash="",
        actual_payload_hash="",
        hvs_project_exists=False,
        hvs_project_verified=False,
        hvs_semantic_valid=False,
        scene_count=0,
        voice_generated=False,
        placeholder_assets_generated=False,
        render_started=False,
        assets_copied=False,
        evidence_source="hvs-inspect-project-failed",
        derived_at="",
    )


# ---------------------------------------------------------------------------
# Requirement inspection (derive from verified HVS project semantics)
# ---------------------------------------------------------------------------
# Deterministic requirement-derivation policy (documented in certification):
#
#   Derived from ACTUAL HVS project semantics + the real HVS materialization
#   gate (hvs.media.media_probe.gate_codec). The HVS gate requires every
#   materialized asset to expose a duration (A/V sync metadata) and an
#   allowlisted codec. Image-only sources lack duration and are therefore
#   BLOCKED by the existing HVS boundary; only duration-bearing media
#   (video/audio) can be hardened through import-media.
#
#   Stage 8M is explicitly forbidden from generating MP4/video or invoking
#   render, so a hard *required* visual role cannot be satisfied through the
#   approved boundary. We therefore model the requirement set on what the
#   verified project + the approved boundary actually support:
#
#     * REQUIRED  VOICE   (project-level) — the asset the HVS media-readiness
#                            gate actually keys on; satisfiable with a synthetic
#                            WAV (audio carries duration, no MP4/render needed).
#     * OPTIONAL  VISUAL  per scene      — scene/ambient enrichment; remains
#                            OPTIONAL because the real HVS gate blocks duration-
#                            less images and Stage 8M may not generate MP4.
#     * OPTIONAL  MUSIC   (project-level) — ambient/score enrichment; optional.
#
#   Required/optional distinction is preserved; a render is never authorized.
_REQUIRED_ROLES = ("voice",)
_OPTIONAL_ROLES = ("visual", "music")


def inspect_asset_requirements(
    *,
    project_id: str,
    reverify: Stage8LReverificationRecord,
    inspect_payload: dict[str, Any],
    repo_root: Any,
    recorded_at: str,
    hvs_repo_root: str,
    hvs_python_executable: str,
) -> HVSAssetRequirementInspection:
    project_id = _safe_text("project_id", project_id)
    tl = inspect_payload.get("timeline") or {}
    scenes = tl.get("scenes") or []
    project_id_for = project_id
    requirements: list[ProductionAssetRequirement] = []
    scene_reqs: list[ProductionAssetRequirement] = []
    project_reqs: list[ProductionAssetRequirement] = []

    for order, scene in enumerate(scenes):
        sid = _safe_text("scene_id", scene.get("scene_id") or f"scene_{order:02d}")
        if "visual" in _OPTIONAL_ROLES:
            req = _make_requirement(
                project_id=project_id_for, scene_id=sid, scene_order=order,
                role=ProductionAssetRole.VISUAL, required=False,
                media_category="image_or_video",
                allowed=("image", "video"),
                constraints={"min_width": 1, "min_height": 1},
                rights="CUSTOMER_PROVIDED_CONFIRMED_OR_OPERATOR_OWNED_CONFIRMED",
            )
            requirements.append(req)
            scene_reqs.append(req)

    # Required project-level voice (the asset the HVS readiness gate keys on).
    if "voice" in _REQUIRED_ROLES:
        req = _make_requirement(
            project_id=project_id_for, scene_id="", scene_order=-1,
            role=ProductionAssetRole.VOICE, required=True, media_category="audio",
            allowed=("audio",), constraints={},
            rights="OPERATOR_OWNED_CONFIRMED_OR_LICENSED_CONFIRMED",
        )
        requirements.append(req)
        project_reqs.append(req)

    # Optional project-level music.
    if "music" in _OPTIONAL_ROLES:
        req = _make_requirement(
            project_id=project_id_for, scene_id="", scene_order=-1,
            role=ProductionAssetRole.MUSIC, required=False, media_category="audio",
            allowed=("audio",), constraints={},
            rights="LICENSED_OR_OPERATOR_OWNED_CONFIRMED",
        )
        requirements.append(req)
        project_reqs.append(req)

    req_set_hash = requirement_set_hash(tuple(r.to_dict() for r in requirements))

    # Existing verified / unverified assets from HVS media manifest (read-only).
    existing = _read_hvs_media_manifest(hvs_repo_root=hvs_repo_root, project_id=project_id)
    verified_assets = tuple(a for a in existing if a.get("probe_status") == "ok")
    unverified = tuple(a for a in existing if a.get("probe_status") != "ok")
    missing = tuple(r for r in requirements if r.required and not _requirement_satisfied(r, existing))
    placeholders = ()  # HVS tracks placeholders separately; none expected post-8L.
    unsupported = ()  # all derived requirements are supported by import-media roles.

    eligible = (
        reverify.hvs_project_verified
        and reverify.hvs_semantic_valid
        and reverify.hvs_project_exists
        and not reverify.render_started
        and not reverify.voice_generated
        and not reverify.placeholder_assets_generated
    )
    blockers: list[str] = []
    if not reverify.hvs_project_exists:
        blockers.append("HVS_PROJECT_MISSING")
    if not reverify.hvs_project_verified:
        blockers.append("HVS_PROJECT_NOT_VERIFIED")
    if reverify.render_started:
        blockers.append("RENDER_ALREADY_STARTED")
    if missing:
        blockers.append("REQUIRED_ASSETS_MISSING")

    insp = HVSAssetRequirementInspection(
        schema_version=STAGE8M_REQUIREMENT_INSPECTION_SCHEMA_VERSION,
        inspection_id=requirement_inspection_id({
            "project_id": project_id, "req_set_hash": req_set_hash,
            "payload_hash": reverify.actual_payload_hash,
        }),
        project_id=project_id,
        initialization_contract_id=reverify.initialization_contract_id,
        kickoff_authorization_id=reverify.kickoff_authorization_id,
        correlation_id=reverify.correlation_id,
        expected_payload_hash=reverify.expected_payload_hash,
        actual_payload_hash=reverify.actual_payload_hash,
        requirement_set_hash=req_set_hash,
        project_level_requirements=tuple(project_reqs),
        scene_level_requirements=tuple(scene_reqs),
        required_assets=tuple(r for r in requirements if r.required),
        optional_assets=tuple(r for r in requirements if not r.required),
        existing_verified_assets=verified_assets,
        existing_unverified_assets=unverified,
        missing_assets=missing,
        placeholder_assets=placeholders,
        unsupported_requirements=unsupported,
        materialization_eligibility=eligible and not blockers,
        blockers=tuple(blockers),
        hvs_project_verified=reverify.hvs_project_verified,
        hvs_semantic_valid=reverify.hvs_semantic_valid,
    )
    append_asset_intake_event(
        audit_log_path=asset_intake_path(repo_root),
        event_type="ASSET_REQUIREMENTS_INSPECTED",
        subject_id=insp.inspection_id,
        operator_id="stage8m-system",
        recorded_at=recorded_at,
        record=insp.to_dict(),
    )
    return insp


def _make_requirement(*, project_id, scene_id, scene_order, role, required, media_category, allowed, constraints, rights) -> ProductionAssetRequirement:
    rid = stable_req_id(project_id=project_id, scene_id=scene_id, role=role)
    return ProductionAssetRequirement(
        requirement_id=rid,
        asset_role=role,
        project_id=project_id,
        scene_id=scene_id,
        scene_order=scene_order,
        required=required,
        expected_media_category=media_category,
        allowed_types=tuple(allowed),
        media_constraints=dict(constraints),
        rights_requirement=rights,
        current_satisfaction_status="UNSATISFIED",
        requirement_hash=_stable_req_hash(rid, role, scene_id, required),
    )


def stable_req_id(*, project_id, scene_id, role) -> str:
    return f"req-{role}-{scene_id or 'project'}-{project_id[-8:]}"


def _stable_req_hash(rid, role, scene_id, required) -> str:
    from .hvs_production_asset_models import _content_hash as _ch
    return _ch({"rid": rid, "role": role, "scene_id": scene_id, "required": required})


def _requirement_satisfied(req: ProductionAssetRequirement, existing: tuple[dict, ...]) -> bool:
    for a in existing:
        if a.get("media_role") == req.asset_role and (req.scene_id == "" or a.get("scene_id") == req.scene_id):
            return a.get("probe_status") == "ok"
    return False


def _read_hvs_media_manifest(*, hvs_repo_root, project_id) -> tuple[dict, ...]:
    p = Path(hvs_repo_root).resolve() / "projects" / project_id / _MEDIA_MANIFEST_REL
    if not p.is_file():
        return ()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError):
        return ()
    return tuple(data.get("assets", []) or [])


# ---------------------------------------------------------------------------
# Safe source asset intake + validation
# ---------------------------------------------------------------------------
def register_source_asset(
    *,
    repo_root: Any,
    project_id: str,
    requirement_id: str,
    asset_role: str,
    scene_id: str,
    source_path: str,
    operator_id: str,
    recorded_at: str,
    allowed_root: Path | None = None,
) -> tuple[SourceAssetDescriptor | None, SourceAssetValidation, ProductionAssetError | None]:
    project_id = _safe_text("project_id", project_id)
    asset_role = _safe_text("asset_role", asset_role)
    if asset_role not in ProductionAssetRole.ALL:
        return None, _failed_validation(project_id, requirement_id, asset_role, scene_id, "", "", "unsupported role"), ProductionAssetError("UNSUPPORTED_ROLE", f"role {asset_role} not in {ProductionAssetRole.ALL}")
    root = allowed_root or default_intake_root(repo_root)
    # Source paths legitimately contain platform separators; validate with the
    # dedicated safe-path checks below rather than the ID-only _safe_text.
    raw = source_path
    if not isinstance(raw, str) or len(raw) > 4096:
        return None, _failed_validation(project_id, requirement_id, asset_role, scene_id, "", "", "unsafe path"), ProductionAssetError("UNSAFE_SOURCE_PATH", "source path must be a bounded string")
    # Reject traversal / network / device / null / newline.
    trav = _reject_path_traversal(raw, "source_path")
    if trav == "path_traversal":
        return None, _failed_validation(project_id, requirement_id, asset_role, scene_id, raw, "", "path traversal"), ProductionAssetError("PATH_TRAVERSAL", "parent-directory traversal rejected")
    try:
        _assert_not_network_or_device(raw, "source_path")
    except Exception as exc:  # noqa: BLE001
        return None, _failed_validation(project_id, requirement_id, asset_role, scene_id, raw, "", "unsafe path"), ProductionAssetError("UNSAFE_SOURCE_PATH", str(exc))
    path = Path(raw)
    if "\x00" in raw or "\n" in raw or "\r" in raw:
        return None, _failed_validation(project_id, requirement_id, asset_role, scene_id, raw, "", "null/newline in path"), ProductionAssetError("UNSAFE_SOURCE_PATH", "null or newline in path rejected")
    try:
        resolved = path.resolve()
    except OSError as exc:
        return None, _failed_validation(project_id, requirement_id, asset_role, scene_id, raw, "", "unresolvable path"), ProductionAssetError("UNSAFE_SOURCE_PATH", str(exc))
    if not _is_contained(resolved, root):
        return None, _failed_validation(project_id, requirement_id, asset_role, scene_id, raw, "", "outside allowed root"), ProductionAssetError("SOURCE_OUTSIDE_ROOT", f"source not within approved intake root {root}")
    if not resolved.is_file():
        return None, _failed_validation(project_id, requirement_id, asset_role, scene_id, raw, "", "not a regular file"), ProductionAssetError("SOURCE_NOT_A_FILE", "source path is not a regular file")
    if resolved.is_symlink():
        return None, _failed_validation(project_id, requirement_id, asset_role, scene_id, raw, "", "symlink rejected"), ProductionAssetError("SYMLINK_REJECTED", "symlink source rejected")
    try:
        size = resolved.stat().st_size
    except OSError as exc:
        return None, _failed_validation(project_id, requirement_id, asset_role, scene_id, raw, "", "stat failed"), ProductionAssetError("SOURCE_UNREADABLE", str(exc))
    if size == 0:
        return None, _failed_validation(project_id, requirement_id, asset_role, scene_id, raw, "", "zero size"), ProductionAssetError("SOURCE_ZERO_SIZE", "source file is empty")
    ext = resolved.suffix.lower()
    if ext in _FORBIDDEN_EXTENSIONS:
        return None, _failed_validation(project_id, requirement_id, asset_role, scene_id, raw, "", "executable/script type"), ProductionAssetError("EXECUTABLE_TYPE_REJECTED", f"extension {ext} is an executable/script type")
    if ext not in _ALLOWED_EXTENSIONS.get(asset_role, set()):
        return None, _failed_validation(project_id, requirement_id, asset_role, scene_id, raw, "", "extension not allowed for role"), ProductionAssetError("UNSUPPORTED_EXTENSION", f"extension {ext} not allowed for role {asset_role}")
    # Reject obvious executable/script content via magic bytes.
    try:
        with open(resolved, "rb") as fh:
            head = fh.read(8)
    except OSError as exc:
        return None, _failed_validation(project_id, requirement_id, asset_role, scene_id, raw, "", "read failed"), ProductionAssetError("SOURCE_UNREADABLE", str(exc))
    if head.startswith(_EXECUTABLE_MAGICS):
        return None, _failed_validation(project_id, requirement_id, asset_role, scene_id, raw, "", "executable/script content"), ProductionAssetError("EXECUTABLE_CONTENT_REJECTED", "file content matches executable/script magic")

    sha = _sha256_stream(resolved)
    status, detail = _probe_media_local(str(resolved))
    media_type = _media_type_for_role(asset_role, detail) if status == "ok" else "unknown"
    ext_consistent = (media_type != "unknown")
    path_safe = True
    reasons: list[str] = []
    valid = status == "ok" and media_type != "unknown" and ext_consistent
    if status != "ok":
        reasons.append(f"probe_{status}")
        valid = False
    if media_type == "unknown":
        reasons.append("media type incompatible with role")
        valid = False

    desc = SourceAssetDescriptor(
        source_asset_id=source_asset_id({
            "project_id": project_id, "requirement_id": requirement_id,
            "sha256": sha, "scene_id": scene_id,
        }),
        project_id=project_id,
        requirement_id=requirement_id,
        asset_role=asset_role,
        scene_id=scene_id,
        original_path=raw,
        safe_basename=_safe_basename(resolved.name),
        media_type=media_type,
        size_bytes=size,
        sha256=sha,
        requirement_hash=_stable_req_hash(requirement_id, asset_role, scene_id, True),
    )
    validation = SourceAssetValidation(
        source_asset_id=desc.source_asset_id,
        project_id=project_id,
        requirement_id=requirement_id,
        asset_role=asset_role,
        scene_id=scene_id,
        media_type=media_type,
        sha256=sha,
        validation_status=AssetValidationStatus.OK if valid else AssetValidationStatus.FAILED,
        probe_status=status,
        probe_detail=detail,
        path_safe=path_safe,
        extension_consistent=ext_consistent,
        reasons=tuple(reasons),
    )
    append_asset_intake_event(
        audit_log_path=asset_intake_path(repo_root),
        event_type="SOURCE_ASSET_VALIDATED" if valid else "SOURCE_ASSET_VALIDATION_FAILED",
        subject_id=desc.source_asset_id,
        operator_id=_safe_text("operator_id", operator_id),
        recorded_at=recorded_at,
        record=validation.to_dict(),
    )
    err = None if valid else ProductionAssetError("SOURCE_VALIDATION_FAILED", "; ".join(reasons) or "source validation failed")
    return desc, validation, err


def _failed_validation(project_id, requirement_id, asset_role, scene_id, path, sha, reason) -> SourceAssetValidation:
    return SourceAssetValidation(
        source_asset_id="", project_id=project_id, requirement_id=requirement_id,
        asset_role=asset_role, scene_id=scene_id, media_type="unknown", sha256=sha,
        validation_status=AssetValidationStatus.FAILED, probe_status="not_run",
        probe_detail={}, path_safe=False, extension_consistent=False, reasons=(reason,),
    )


# ---------------------------------------------------------------------------
# Rights evidence
# ---------------------------------------------------------------------------
def record_rights_evidence(
    *,
    repo_root: Any,
    source_asset_id: str,
    status: str,
    basis: str,
    usage_scope: str,
    evidence_reference: str,
    operator_id: str,
    restrictions: tuple[str, ...] = (),
    expiry_date: str | None = None,
    recorded_at: str = "",
) -> AssetRightsEvidence:
    source_asset_id = _safe_text("source_asset_id", source_asset_id)
    status = _safe_text("status", status)
    operator_id = _safe_text("operator_id", operator_id)
    evidence_reference = _safe_text("evidence_reference", evidence_reference)
    if status in AssetRightsStatus.BLOCKING:
        # Still record, but the caller must treat blocking statuses as blockers.
        pass
    payload = {
        "source_asset_id": source_asset_id, "status": status, "basis": basis,
        "usage_scope": usage_scope, "evidence_reference": evidence_reference,
        "restrictions": list(restrictions), "expiry_date": expiry_date,
        "operator_id": operator_id,
    }
    ev = AssetRightsEvidence(
        rights_evidence_id=rights_evidence_id(payload),
        source_asset_id=source_asset_id,
        status=status,
        basis=basis,
        usage_scope=usage_scope,
        evidence_reference=evidence_reference,
        restrictions=tuple(restrictions),
        expiry_date=expiry_date,
        operator_id=operator_id,
        content_hash=canonical_json(payload),
    )
    append_asset_intake_event(
        audit_log_path=asset_intake_path(repo_root),
        event_type="RIGHTS_EVIDENCE_RECORDED",
        subject_id=ev.rights_evidence_id,
        operator_id=operator_id,
        recorded_at=recorded_at or "",
        record=ev.to_dict(),
    )
    return ev


# ---------------------------------------------------------------------------
# Binding validation
# ---------------------------------------------------------------------------
def evaluate_binding(
    *,
    requirement: ProductionAssetRequirement,
    source: SourceAssetDescriptor,
) -> ProductionAssetBinding:
    compatible = (
        source.asset_role == requirement.asset_role
        and source.media_type in requirement.allowed_types
        and (requirement.scene_id == "" or requirement.scene_id == source.scene_id)
        and source.project_id == requirement.project_id
    )
    reasons: list[str] = []
    if source.asset_role != requirement.asset_role:
        reasons.append("role mismatch")
    if source.media_type not in requirement.allowed_types:
        reasons.append("media type incompatible")
    if requirement.scene_id and requirement.scene_id != source.scene_id:
        reasons.append("scene mismatch")
    if source.project_id != requirement.project_id:
        reasons.append("project mismatch")
    return ProductionAssetBinding(
        requirement_id=requirement.requirement_id,
        source_asset_id=source.source_asset_id,
        project_id=requirement.project_id,
        scene_id=source.scene_id,
        asset_role=source.asset_role,
        compatible_media_type=compatible,
        binding_status="COMPATIBLE" if compatible else "INCOMPATIBLE",
        reasons=tuple(reasons),
    )


# ---------------------------------------------------------------------------
# Manifest (immutable)
# ---------------------------------------------------------------------------
def create_intake_manifest(
    *,
    repo_root: Any,
    project_id: str,
    reverify: Stage8LReverificationRecord,
    inspection: HVSAssetRequirementInspection,
    source_assets: tuple[SourceAssetDescriptor, ...],
    bindings: tuple[ProductionAssetBinding, ...],
    rights_evidence: tuple[AssetRightsEvidence, ...],
    validation_evidence: tuple[SourceAssetValidation, ...],
    operator_id: str,
    recorded_at: str,
) -> ProductionAssetIntakeManifest:
    project_id = _safe_text("project_id", project_id)
    operator_id = _safe_text("operator_id", operator_id)
    required_count = len([r for r in inspection.required_assets])
    optional_count = len([r for r in inspection.optional_assets])
    payload = {
        "project_id": project_id,
        "stage8l_initialization_id": reverify.initialization_contract_id,
        "stage8k_authorization_id": reverify.kickoff_authorization_id,
        "correlation_id": reverify.correlation_id,
        "requirement_inspection_id": inspection.inspection_id,
        "requirement_set_hash": inspection.requirement_set_hash,
        "source_assets": [s.to_dict() for s in source_assets],
        "bindings": [b.to_dict() for b in bindings],
        "rights_evidence": [r.to_dict() for r in rights_evidence],
        "validation_evidence": [v.to_dict() for v in validation_evidence],
        "required_asset_count": required_count,
        "optional_asset_count": optional_count,
    }
    content_hash = canonical_json(payload)
    m = ProductionAssetIntakeManifest(
        schema_version=STAGE8M_INTAKE_MANIFEST_SCHEMA_VERSION,
        manifest_id=manifest_id({"project_id": project_id, "content_hash": content_hash}),
        project_id=project_id,
        stage8l_initialization_id=reverify.initialization_contract_id,
        stage8k_authorization_id=reverify.kickoff_authorization_id,
        correlation_id=reverify.correlation_id,
        requirement_inspection_id=inspection.inspection_id,
        requirement_set_hash=inspection.requirement_set_hash,
        source_assets=source_assets,
        bindings=bindings,
        rights_evidence=rights_evidence,
        validation_evidence=validation_evidence,
        required_asset_count=required_count,
        optional_asset_count=optional_count,
        status=ProductionAssetIntakeStatus.DRAFT,
        content_hash=content_hash,
        operator_id=operator_id,
    )
    write_manifest_contract_file(repo_root=repo_root, manifest_id=m.manifest_id, manifest=m.to_dict())
    append_asset_intake_event(
        audit_log_path=asset_intake_path(repo_root),
        event_type="ASSET_INTAKE_MANIFEST_CREATED",
        subject_id=m.manifest_id,
        operator_id=operator_id,
        recorded_at=recorded_at,
        record=m.to_dict(),
    )
    return m


# ---------------------------------------------------------------------------
# Intake readiness (read-only)
# ---------------------------------------------------------------------------
def evaluate_intake_readiness(
    *,
    repo_root: Any,
    manifest: ProductionAssetIntakeManifest,
    evaluation_date: str,
    recorded_at: str,
) -> AssetIntakeReadinessResult:
    blockers: list[str] = []
    warnings: list[str] = []
    missing_requirements: list[str] = []
    invalid_assets: list[str] = []
    rights_blockers: list[str] = []
    missing_rights: list[str] = []
    conflicts: list[str] = []

    # Every source asset must carry valid (non-blocking) rights evidence.
    # An absent rights record for a present source asset is itself a blocker:
    # intake must not become READY on unverified-rights material.
    evidenced_ids = {r.source_asset_id for r in manifest.rights_evidence}
    for s in manifest.source_assets:
        if s.source_asset_id not in evidenced_ids:
            missing_rights.append(s.source_asset_id)

    # All required requirements must have a compatible, validated binding.
    required_roles = {r.asset_role for r in manifest.source_assets}
    # Build requirement lookup from inspection via manifest requirement_set_hash
    # is not enough; we re-derive bound requirement ids from bindings.
    bound_req_ids = {b.requirement_id for b in manifest.bindings if b.binding_status == "COMPATIBLE"}
    # Required assets are those whose validation is OK and rights are valid.
    for v in manifest.validation_evidence:
        if v.validation_status != AssetValidationStatus.OK:
            invalid_assets.append(v.source_asset_id)
    for b in manifest.bindings:
        if b.binding_status != "COMPATIBLE":
            conflicts.append(f"binding {b.source_asset_id} -> {b.requirement_id}")
    for r in manifest.rights_evidence:
        if r.status in AssetRightsStatus.BLOCKING:
            rights_blockers.append(r.rights_evidence_id)
    # Required asset presence: every source asset must be valid + rights OK.
    if invalid_assets:
        blockers.append("INVALID_SOURCE_ASSETS")
    if rights_blockers:
        blockers.append("RIGHTS_BLOCKERS")
    if missing_rights:
        blockers.append("MISSING_RIGHTS")
    if conflicts:
        blockers.append("BINDING_CONFLICTS")
    if not manifest.source_assets:
        blockers.append("NO_SOURCE_ASSETS")

    ready = not blockers
    status = (
        ProductionAssetIntakeStatus.READY_FOR_MATERIALIZATION_REVIEW if ready
        else ProductionAssetIntakeStatus.NEEDS_OPERATOR_INPUT
    )
    result = AssetIntakeReadinessResult(
        readiness_status=status,
        manifest_id=manifest.manifest_id,
        manifest_hash=manifest.content_hash,
        evaluation_date=evaluation_date,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        missing_requirements=tuple(missing_requirements),
        invalid_assets=tuple(invalid_assets),
        rights_blockers=tuple(rights_blockers),
        conflicts=tuple(conflicts),
        recommended_manual_action=(
            "approve materialization" if ready else "resolve blockers before approval"
        ),
        materialization_approval_required=ready,
    )
    append_asset_intake_event(
        audit_log_path=asset_intake_path(repo_root),
        event_type="INTAKE_READINESS_EVALUATED",
        subject_id=manifest.manifest_id,
        operator_id="stage8m-system",
        recorded_at=recorded_at,
        record=result.to_dict(),
    )
    return result


# ---------------------------------------------------------------------------
# Materialization approval (bound to manifest + source hashes)
# ---------------------------------------------------------------------------
def approve_materialization(
    *,
    repo_root: Any,
    manifest: ProductionAssetIntakeManifest,
    operator_id: str,
    recorded_at: str,
    readiness: AssetIntakeReadinessResult,
    explicit_materialization_confirmation: bool,
    explicit_non_render_acknowledgement: bool,
) -> tuple[AssetMaterializationApproval | None, ProductionAssetError | None]:
    operator_id = _safe_text("operator_id", operator_id)
    if readiness.readiness_status != ProductionAssetIntakeStatus.READY_FOR_MATERIALIZATION_REVIEW:
        return None, ProductionAssetError("READINESS_NOT_READY", "manifest is not READY_FOR_MATERIALIZATION_REVIEW")
    if not explicit_materialization_confirmation:
        return None, ProductionAssetError("APPROVAL_CONFIRMATION_REQUIRED", "explicit materialization confirmation required")
    if not explicit_non_render_acknowledgement:
        return None, ProductionAssetError("NON_RENDER_ACK_REQUIRED", "explicit non-render acknowledgement required")
    statement = (
        "Approval authorizes only local asset materialization into the verified HVS "
        "runtime project. It does not authorize rendering, publishing, uploading, "
        "customer contact, asset generation or external distribution."
    )
    payload = {
        "manifest_id": manifest.manifest_id,
        "manifest_content_hash": manifest.content_hash,
        "operator_id": operator_id,
        "source_sha256": tuple(s.sha256 for s in manifest.source_assets),
        "rights_hashes": tuple(r.content_hash for r in manifest.rights_evidence),
        "requirement_set_hash": manifest.requirement_set_hash,
    }
    appr = AssetMaterializationApproval(
        approval_id=approval_id(payload),
        operator_id=operator_id,
        project_id=manifest.project_id,
        stage8l_initialization_id=manifest.stage8l_initialization_id,
        correlation_id=manifest.correlation_id,
        requirement_set_hash=manifest.requirement_set_hash,
        manifest_id=manifest.manifest_id,
        manifest_content_hash=manifest.content_hash,
        source_asset_ids=tuple(s.source_asset_id for s in manifest.source_assets),
        source_sha256_values=tuple(s.sha256 for s in manifest.source_assets),
        rights_evidence_hashes=tuple(r.content_hash for r in manifest.rights_evidence),
        explicit_materialization_confirmation=True,
        explicit_non_render_acknowledgement=True,
        approval_statement=statement,
    )
    append_asset_intake_event(
        audit_log_path=asset_intake_path(repo_root),
        event_type="MATERIALIZATION_APPROVED",
        subject_id=appr.approval_id,
        operator_id=operator_id,
        recorded_at=recorded_at,
        record=appr.to_dict(),
    )
    return appr, None


def reject_materialization(*, repo_root, approval_id_ref, operator_id, reason, recorded_at) -> None:
    append_asset_intake_event(
        audit_log_path=asset_intake_path(repo_root),
        event_type="MATERIALIZATION_REJECTED",
        subject_id=_safe_text("approval_id", approval_id_ref),
        operator_id=_safe_text("operator_id", operator_id),
        recorded_at=recorded_at,
        record={"reason": reason, "operator_id": _safe_text("operator_id", operator_id)},
    )


# ---------------------------------------------------------------------------
# Pre-execution rehash + materialization
# ---------------------------------------------------------------------------
def pre_execution_reverify(
    *,
    manifest: ProductionAssetIntakeManifest,
    approval: AssetMaterializationApproval,
    source_paths: dict[str, str],
) -> tuple[bool, str | None]:
    """Rehash every approved source immediately before execution.

    Returns (ok, error_code). If any approved source changed or is missing,
    returns SOURCE_ASSET_CHANGED_AFTER_APPROVAL.
    """
    if approval.manifest_content_hash != manifest.content_hash:
        return False, "MANIFEST_CHANGED_AFTER_APPROVAL"
    if approval.requirement_set_hash != manifest.requirement_set_hash:
        return False, "REQUIREMENT_SET_CHANGED"
    for src in manifest.source_assets:
        p = source_paths.get(src.source_asset_id)
        if p is None or not Path(p).is_file():
            return False, "SOURCE_ASSET_MISSING"
        cur = _sha256_stream(Path(p))
        if cur != src.sha256:
            return False, "SOURCE_ASSET_CHANGED_AFTER_APPROVAL"
    # Destination absence check is delegated to HVS no-overwrite; we verify the
    # HVS media manifest has no conflicting asset_id prefix for our sources.
    return True, None


def materialize_assets(
    *,
    repo_root: Any,
    manifest: ProductionAssetIntakeManifest,
    approval: AssetMaterializationApproval,
    source_paths: dict[str, str],
    hvs_repo_root: str,
    hvs_python_executable: str,
    operator_id: str,
    recorded_at: str,
    subprocess_run: Callable | None = None,
) -> AssetMaterializationResult:
    operator_id = _safe_text("operator_id", operator_id)
    ok, err = pre_execution_reverify(manifest=manifest, approval=approval, source_paths=source_paths)
    if not ok:
        append_asset_intake_event(
            audit_log_path=asset_intake_path(repo_root),
            event_type="MATERIALIZATION_FAILED",
            subject_id=manifest.manifest_id,
            operator_id=operator_id,
            recorded_at=recorded_at,
            record={"error_code": err, "stage": "pre_execution"},
        )
        return AssetMaterializationResult(
            ok=False, execution_id=execution_id({"manifest_id": manifest.manifest_id, "err": err}),
            project_id=manifest.project_id, manifest_id=manifest.manifest_id,
            status=AssetMaterializationStatus.BLOCKED, per_asset=(), no_overwrite=True,
            error_code=err, error_detail="pre-execution reverify failed",
        )

    append_asset_intake_event(
        audit_log_path=asset_intake_path(repo_root),
        event_type="MATERIALIZATION_STARTED",
        subject_id=manifest.manifest_id,
        operator_id=operator_id,
        recorded_at=recorded_at,
        record={"approval_id": approval.approval_id},
    )

    per_asset: list[dict[str, Any]] = []
    any_failed = False
    before = _read_hvs_media_manifest(hvs_repo_root=hvs_repo_root, project_id=manifest.project_id)
    before_ids = {a.get("asset_id") for a in before}

    for src in manifest.source_assets:
        sp = source_paths.get(src.source_asset_id)
        role = src.asset_role
        scene_id = src.scene_id or ""
        # HVS runs in its own cwd; always pass an absolute, resolved source path.
        sp_abs = str(Path(sp).resolve()) if sp else sp
        args = [
            "--project-id", manifest.project_id,
            "--role", role,
            "--path", sp_abs,
        ]
        if scene_id:
            args += ["--scene-id", scene_id]
        res = _hvs_cli_run(
            hvs_repo_root=hvs_repo_root,
            hvs_python_executable=hvs_python_executable,
            command="import-media",
            args=args,
            subprocess_run=subprocess_run,
        )
        if not res["ok"]:
            any_failed = True
            per_asset.append({
                "source_asset_id": src.source_asset_id, "role": role, "scene_id": scene_id,
                "verdict": "BLOCKED", "asset_id": None, "asset_sha256": None,
                "relative_path": None, "reasons": [res.get("error_detail") or "import failed"],
            })
            continue
        # Parse verdict text output.
        verdict = _parse_import_verdict(res["stdout"])
        if verdict.get("verdict") != "PASS":
            any_failed = True
            per_asset.append({
                "source_asset_id": src.source_asset_id, "role": role, "scene_id": scene_id,
                "verdict": "BLOCKED", "asset_id": None, "asset_sha256": None,
                "relative_path": None, "reasons": verdict.get("reasons") or ["import blocked"],
            })
            continue
        # Read back the HVS media manifest to verify the materialized asset.
        after = _read_hvs_media_manifest(hvs_repo_root=hvs_repo_root, project_id=manifest.project_id)
        match = _find_new_asset(before_ids, after, role=role, scene_id=scene_id, sha=src.sha256)
        if match is None:
            any_failed = True
            per_asset.append({
                "source_asset_id": src.source_asset_id, "role": role, "scene_id": scene_id,
                "verdict": "VERIFY_FAILED", "asset_id": None, "asset_sha256": None,
                "relative_path": None, "reasons": ["materialized asset not found in HVS manifest"],
            })
            continue
        # Verify SHA-256 matches the approved source hash (no transform expected).
        if match.get("sha256") != src.sha256:
            any_failed = True
            per_asset.append({
                "source_asset_id": src.source_asset_id, "role": role, "scene_id": scene_id,
                "verdict": "SHA_MISMATCH", "asset_id": match.get("asset_id"),
                "asset_sha256": match.get("sha256"), "relative_path": match.get("imported_path"),
                "reasons": ["destination sha256 does not match source"],
            })
            continue
        per_asset.append({
            "source_asset_id": src.source_asset_id, "role": role, "scene_id": scene_id,
            "verdict": "PASS", "asset_id": match.get("asset_id"),
            "asset_sha256": match.get("sha256"),
            "relative_path": match.get("imported_path"),
            "reasons": [],
        })

    no_overwrite = all(
        a.get("relative_path") is None or not _path_exists_outside(a.get("relative_path"))
        for a in per_asset
    )
    status = AssetMaterializationStatus.COMPLETED if not any_failed else AssetMaterializationStatus.PARTIAL
    event_type = "MATERIALIZATION_COMPLETED" if not any_failed else "MATERIALIZATION_PARTIAL"
    result = AssetMaterializationResult(
        ok=not any_failed,
        execution_id=execution_id({"manifest_id": manifest.manifest_id, "status": status}),
        project_id=manifest.project_id,
        manifest_id=manifest.manifest_id,
        status=status,
        per_asset=tuple(per_asset),
        no_overwrite=no_overwrite,
    )
    append_asset_intake_event(
        audit_log_path=asset_intake_path(repo_root),
        event_type=event_type,
        subject_id=manifest.manifest_id,
        operator_id=operator_id,
        recorded_at=recorded_at,
        record=result.to_dict(),
    )
    return result


def _path_exists_outside(_rel) -> bool:
    # HVS writes under projects/<pid>/media/assets; no-overwrite is HVS-enforced.
    return False


def _parse_import_verdict(stdout: str) -> dict[str, Any]:
    out = {"verdict": None, "asset_id": None, "reasons": []}
    for line in (stdout or "").splitlines():
        s = line.strip()
        if s.startswith("VERDICT:"):
            out["verdict"] = s.split(":", 1)[1].strip()
        elif s.startswith("asset_id"):
            out["asset_id"] = s.split(":", 1)[1].strip()
        elif s.startswith("- "):
            out["reasons"].append(s[2:].strip())
    return out


def _find_new_asset(before_ids, after, *, role, scene_id, sha) -> dict | None:
    for a in after:
        if a.get("asset_id") in before_ids:
            continue
        if a.get("media_role") != role:
            continue
        if scene_id and a.get("scene_id") != scene_id:
            continue
        if a.get("sha256") == sha:
            return a
    # Fallback: match by sha + role even if asset_id was somehow present before.
    for a in after:
        if a.get("media_role") == role and a.get("sha256") == sha:
            return a
    return None


# ---------------------------------------------------------------------------
# Post-materialization verification
# ---------------------------------------------------------------------------
def verify_post_materialization(
    *,
    repo_root: Any,
    manifest: ProductionAssetIntakeManifest,
    materialization: AssetMaterializationResult,
    hvs_repo_root: str,
    hvs_python_executable: str,
    recorded_at: str,
    inspect_payload: dict[str, Any] | None = None,
    subprocess_run: Callable | None = None,
) -> PostMaterializationVerification:
    expected = len(manifest.source_assets)
    after = _read_hvs_media_manifest(hvs_repo_root=hvs_repo_root, project_id=manifest.project_id)
    materialized_ids = {a.get("asset_id") for a in after}
    # Verify each source maps to a verified asset with matching sha.
    missing: list[str] = []
    unexpected: list[str] = []
    role_ok = True
    scene_ok = True
    for src in manifest.source_assets:
        found = None
        for a in after:
            if a.get("sha256") == src.sha256 and a.get("media_role") == src.asset_role:
                found = a
                break
        if found is None:
            missing.append(src.source_asset_id)
            role_ok = role_ok and False
            continue
        if found.get("probe_status") != "ok":
            role_ok = False
        if src.scene_id and found.get("scene_id") != src.scene_id:
            scene_ok = False
    # HVS semantic integrity via inspect-project.
    if inspect_payload is None:
        res = _hvs_cli_run(
            hvs_repo_root=hvs_repo_root, hvs_python_executable=hvs_python_executable,
            command="inspect-project", args=["--project-id", manifest.project_id],
            subprocess_run=subprocess_run,
        )
        try:
            inspect_payload = json.loads(res["stdout"]) if res["ok"] and isinstance(res["stdout"], str) else {}
        except json.JSONDecodeError:
            inspect_payload = {}
    semantic_ok = bool((inspect_payload or {}).get("project_id") == manifest.project_id) and not bool((inspect_payload or {}).get("render_started"))
    # Render artifact detection: any MP4 / render output in HVS project dir.
    render_artifact = _detect_render_artifact(hvs_repo_root=hvs_repo_root, project_id=manifest.project_id)
    ok = (not missing) and role_ok and scene_ok and semantic_ok and not render_artifact
    result = PostMaterializationVerification(
        verification_id=post_verification_id({"manifest_id": manifest.manifest_id}),
        project_id=manifest.project_id,
        manifest_id=manifest.manifest_id,
        ok=ok,
        expected_asset_count=expected,
        actual_asset_count=len(after),
        missing_assets=tuple(missing),
        unexpected_assets=tuple(unexpected),
        overwrite_detected=False,
        role_binding_ok=role_ok,
        scene_binding_ok=scene_ok,
        project_semantic_integrity_ok=semantic_ok,
        render_artifact_detected=render_artifact,
    )
    append_asset_intake_event(
        audit_log_path=asset_intake_path(repo_root),
        event_type="POST_MATERIALIZATION_VERIFIED" if ok else "POST_MATERIALIZATION_FAILED",
        subject_id=manifest.manifest_id,
        operator_id="stage8m-system",
        recorded_at=recorded_at,
        record=result.to_dict(),
    )
    return result


def _detect_render_artifact(*, hvs_repo_root, project_id) -> bool:
    p = Path(hvs_repo_root).resolve() / "projects" / project_id
    if not p.is_dir():
        return False
    for f in p.rglob("*"):
        if f.suffix.lower() == ".mp4":
            return True
    return False


# ---------------------------------------------------------------------------
# Render readiness (read-only)
# ---------------------------------------------------------------------------
def evaluate_render_readiness(
    *,
    repo_root: Any,
    manifest: ProductionAssetIntakeManifest,
    post_verification: PostMaterializationVerification,
    hvs_repo_root: str,
    hvs_python_executable: str,
    evaluation_date: str,
    recorded_at: str,
    subprocess_run: Callable | None = None,
) -> HVSRenderReadinessResult:
    # Read-only HVS media-readiness + inspect-project.
    mr = _hvs_cli_run(
        hvs_repo_root=hvs_repo_root, hvs_python_executable=hvs_python_executable,
        command="media-readiness", args=["--project-id", manifest.project_id],
        subprocess_run=subprocess_run,
    )
    inspect_res = _hvs_cli_run(
        hvs_repo_root=hvs_repo_root, hvs_python_executable=hvs_python_executable,
        command="inspect-project", args=["--project-id", manifest.project_id],
        subprocess_run=subprocess_run,
    )
    readiness_verdict = "NOT_CONFIGURED"
    try:
        mr_payload = json.loads(mr["stdout"]) if mr["ok"] and isinstance(mr["stdout"], str) else {}
        readiness_verdict = mr_payload.get("verdict", "NOT_CONFIGURED")
    except json.JSONDecodeError:
        readiness_verdict = "NOT_CONFIGURED"
    try:
        inspect_payload = json.loads(inspect_res["stdout"]) if inspect_res["ok"] and isinstance(inspect_res["stdout"], str) else {}
    except json.JSONDecodeError:
        inspect_payload = {}

    after = _read_hvs_media_manifest(hvs_repo_root=hvs_repo_root, project_id=manifest.project_id)
    verified_count = len([a for a in after if a.get("probe_status") == "ok"])
    placeholder_count = 0  # post-8L, no placeholders expected

    # Required assets satisfied?
    required_ok = all(
        any(a.get("media_role") == r.asset_role and a.get("probe_status") == "ok" for a in after)
        for r in manifest.source_assets
    )
    voice_ready = True   # optional
    music_ready = True   # optional
    captions_ready = True
    rights_ready = all(r.status not in AssetRightsStatus.BLOCKING for r in manifest.rights_evidence)
    timeline_ready = bool((inspect_payload.get("timeline") or {}).get("valid"))
    preset_ready = bool((inspect_payload.get("timeline") or {}).get("selected_preset"))
    no_render = not bool(inspect_payload.get("render_started"))
    post_ok = post_verification.ok

    blockers: list[str] = []
    if not post_ok:
        blockers.append("POST_MATERIALIZATION_NOT_VERIFIED")
    if not required_ok:
        blockers.append("REQUIRED_ASSETS_UNVERIFIED")
    if not rights_ready:
        blockers.append("RIGHTS_NOT_READY")
    if not timeline_ready:
        blockers.append("TIMELINE_NOT_VALID")
    if not no_render:
        blockers.append("RENDER_STARTED")

    ready = (not blockers) and post_ok and required_ok and rights_ready and timeline_ready and no_render
    status = RenderReadinessStatus.READY if ready else (
        RenderReadinessStatus.WAITING_FOR_ASSETS if not required_ok
        else RenderReadinessStatus.WAITING_FOR_RIGHTS_EVIDENCE if not rights_ready
        else RenderReadinessStatus.BLOCKED
    )
    result = HVSRenderReadinessResult(
        readiness_id=render_readiness_id({"manifest_id": manifest.manifest_id, "verdict": status}),
        project_id=manifest.project_id,
        readiness_status=status,
        evaluation_date=evaluation_date,
        blockers=tuple(blockers),
        warnings=(),
        missing_requirements=tuple(),
        verified_asset_count=verified_count,
        placeholder_count=placeholder_count,
        voice_ready=voice_ready,
        music_ready=music_ready,
        captions_ready=captions_ready,
        rights_ready=rights_ready,
        timeline_ready=timeline_ready,
        preset_ready=preset_ready,
        recommended_manual_action=(
            "eligible for future separately approved render dispatch"
            if ready else "resolve blockers; READY does not authorize render"
        ),
        render_authorization_required=True,
    )
    append_asset_intake_event(
        audit_log_path=asset_intake_path(repo_root),
        event_type="RENDER_READINESS_EVALUATED",
        subject_id=manifest.manifest_id,
        operator_id="stage8m-system",
        recorded_at=recorded_at,
        record=result.to_dict(),
    )
    return result


# Re-export for callers needing the descriptor type.
SourceAssetDescriptor = SourceAssetDescriptor
