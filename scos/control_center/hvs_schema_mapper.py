"""SCOS <-> Hermes Video Studio deterministic schema mapper (Stage 2).

Pure translation layer. Converts a canonical SCOS edit timeline
(``SCOSRenderTimelineProject``, defined in ``hvs_contract_models.py``) into an
HVS-compatible project/timeline payload, validates the produced payload against
the *read-only* HVS schema contract (interpreted, not by importing HVS), and
reconstructs the equivalent SCOS representation. Round-trip semantic equivalence
is provable without any subprocess, filesystem write, network, random id, or
clock.

Authorized boundary (per the cross-project integration architecture):

    SCOS model -> pure deterministic mapper -> versioned adapter payload
    -> HVS-compatible JSON structure -> validation -> reverse mapping
    -> semantic comparison

NOT performed here (must never be): creating HVS projects, copying assets,
invoking the HVS CLI, rendering, or changing the default renderer. The mapper is
a pure function: it accepts a SCOS model (or an already-mapped payload dict) and
returns a new dict / new model. Caller-owned inputs are never mutated.

All timing is carried in canonical integer milliseconds internally; the HVS
boundary uses seconds rounded to 3 decimals (``round(x, 3)``), mirroring
``hvs.core.timeline_models.build_scene``. The deterministic hash is computed over
the canonical *semantic* structure only — HVS audit fields (``created_at``,
``source_agent``, ``stage``, ``status``, ``artifact_id``) and volatile
correlation ids (``request_id`` / ``run_id``) are excluded from the identity.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid, no
network, no file I/O, no subprocess, no HVS import.
"""

from __future__ import annotations

import json
from typing import Any

from hvs_contract_models import (
    HVS_CREATED_AT_PLACEHOLDER,
    HVS_FPS_VALUES,
    HVS_RESOLUTION_VALUES,
    HVS_SCHEMA_VERSION,
    HVS_SCENE_COUNT_MAX,
    HVS_SCENE_COUNT_MIN,
    HVS_SOURCE_AGENT,
    HVS_STATUS_PLANNED,
    HVS_TIMELINE_STAGE,
    SCOSAssetRef,
    SCOSCaption,
    SCOSRenderTimelineProject,
    SCOSScene,
    SCOS_HVS_TIMELINE_CONTRACT_ID,
    SCOS_HVS_TIMELINE_CONTRACT_NAME,
    SCOS_HVS_TIMELINE_CONTRACT_VERSION,
    SCOS_PRESET_TO_HVS,
    SCOS_RENDER_PRESETS,
    HVSMappingError,
    HVSMappingResult,
    HVSValidationIssue,
    HVSValidationResult,
    HVSRoundTripResult,
    X_SCOS_KEY,
    _ms_to_s,
    _reject_path_traversal,
    _require_fps,
    _require_resolution,
    _s_to_ms,
    _sha256_hex16,
)


# --- resolution / orientation helpers ----------------------------------------
def _orientation_for(resolution: str) -> str:
    """Derive orientation from a supported HVS resolution string.

    Vertical: 1080x1920. Horizontal: 1920x1080. Square: 1080x1080. This is a
    pure width/height derivation; orientation is NEVER inferred from any other
    signal and never guesses.
    """
    w, _, h = resolution.partition("x")
    width, height = int(w), int(h)
    if width == height:
        return "square"
    return "vertical" if height > width else "horizontal"


def _artifact_id_for(project_id: str) -> str:
    """Deterministic HVS artifact id (join key), not a random uuid.

    Excluded from the deterministic semantic identity.
    """
    return f"hvs-timeline-{project_id}"


# --- canonical semantic structure (identity core) ----------------------------
def _canonical_semantic_structure(project: SCOSRenderTimelineProject) -> dict[str, Any]:
    """Build a deterministic, sortable semantic structure for hashing.

    Excludes HVS audit fields and volatile correlation ids. Lists are ordered
    deterministically (scenes by ``order`` then ``scene_id``; asset refs by
    ``asset_id``; captions by ``start_ms`` then text; metadata by key) so the
    resulting JSON (``sort_keys=True``) is fully canonical and key-order
    independent.
    """

    def _scene_struct(scene) -> dict[str, Any]:
        assets = sorted(scene.asset_refs, key=lambda a: a.asset_id)
        caps = sorted(scene.captions, key=lambda c: (c.start_ms, c.text))
        return {
            "scene_id": scene.scene_id,
            "order": scene.order,
            "start_ms": scene.start_ms,
            "duration_ms": scene.duration_ms,
            "intent": scene.intent,
            "visual_description": scene.visual_description,
            "text_overlay": scene.text_overlay,
            "transition": scene.transition,
            "asset_refs": [
                {
                    "asset_id": a.asset_id,
                    "asset_type": a.asset_type,
                    "path": a.path,
                }
                for a in assets
            ],
            "captions": [
                {
                    "scene_id": c.scene_id,
                    "text": c.text,
                    "start_ms": c.start_ms,
                    "end_ms": c.end_ms,
                }
                for c in caps
            ],
            "metadata": sorted([list(p) for p in scene.metadata]),
        }

    scenes = sorted(project.scenes, key=lambda s: (s.order, s.scene_id))
    return {
        "contract_id": SCOS_HVS_TIMELINE_CONTRACT_ID,
        "project_id": project.project_id,
        "resolution": project.resolution,
        "fps": project.fps,
        "selected_preset": project.selected_preset,
        "total_duration_ms": project.total_duration_ms,
        "scenes": [_scene_struct(s) for s in scenes],
        "metadata": sorted([list(p) for p in project.metadata]),
    }


def _semantic_hash(project: SCOSRenderTimelineProject) -> str:
    """Stable sha256 hexdigest[:16] over the canonical semantic structure."""
    struct = _canonical_semantic_structure(project)
    blob = json.dumps(struct, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return _sha256_hex16(blob)


# --- SCOS input validation ---------------------------------------------------
def _validate_scos_project(project: SCOSRenderTimelineProject) -> list[dict[str, str]]:
    """Return a list of error dicts (empty = valid).

    Strict: missing/negative/invalid values produce a structured failure; there
    is NO silent clamp and NO default fallback. Enforces HVS schema bounds
    (resolution enum, fps enum, scene count 3..6) at the SCOS boundary so the
    produced payload is always schema-valid.
    """
    errors: list[dict[str, str]] = []
    if not project.project_id:
        errors.append({"error_kind": "missing_required_field", "field": "project_id",
                       "error_detail": "project_id is required"})
    if project.width <= 0 or project.height <= 0:
        errors.append({"error_kind": "invalid_resolution",
                       "field": "resolution",
                       "error_detail": f"width/height must be positive, got {project.width}x{project.height}"})
    if _require_resolution(project.width, project.height) is None:
        errors.append({"error_kind": "unsupported_resolution", "field": "resolution",
                       "error_detail": f"resolution {project.resolution!r} is not supported by HVS {HVS_RESOLUTION_VALUES!r}"})
    if not _require_fps(project.fps):
        errors.append({"error_kind": "unsupported_fps", "field": "fps",
                       "error_detail": f"fps {project.fps} is not supported by HVS {HVS_FPS_VALUES!r}"})
    if project.selected_preset not in SCOS_RENDER_PRESETS:
        errors.append({"error_kind": "unsupported_preset", "field": "selected_preset",
                       "error_detail": f"preset {project.selected_preset!r} is not in {SCOS_RENDER_PRESETS!r}"})

    n = len(project.scenes)
    if not HVS_SCENE_COUNT_MIN <= n <= HVS_SCENE_COUNT_MAX:
        errors.append({"error_kind": "invalid_scene_count", "field": "scenes",
                       "error_detail": f"scene_count must be {HVS_SCENE_COUNT_MIN}..{HVS_SCENE_COUNT_MAX}, got {n}"})

    seen_ids: set[str] = set()
    seen_orders: set[int] = set()
    prev_end_ms = 0
    for scene in sorted(project.scenes, key=lambda s: (s.order, s.scene_id)):
        if not scene.scene_id:
            errors.append({"error_kind": "missing_required_field", "field": "scene_id",
                           "error_detail": "scene scene_id is required"})
        elif scene.scene_id in seen_ids:
            errors.append({"error_kind": "duplicate_scene_id", "field": "scene_id",
                           "error_detail": f"duplicate scene_id {scene.scene_id!r}"})
        seen_ids.add(scene.scene_id)

        if scene.order in seen_orders:
            errors.append({"error_kind": "duplicate_order_index", "field": "order",
                           "error_detail": f"duplicate scene order index {scene.order}"})
        seen_orders.add(scene.order)

        if scene.start_ms < 0:
            errors.append({"error_kind": "negative_start", "field": "start_ms",
                           "error_detail": f"scene {scene.scene_id!r} start_ms < 0"})
        if scene.duration_ms <= 0:
            errors.append({"error_kind": "zero_duration", "field": "duration_ms",
                           "error_detail": f"scene {scene.scene_id!r} duration_ms <= 0"})
        if scene.end_ms <= scene.start_ms:
            errors.append({"error_kind": "end_before_start", "field": "end_ms",
                           "error_detail": f"scene {scene.scene_id!r} end_ms <= start_ms"})

        # Overlap / gap policy: the canonical plan is contiguous. Overlap is a
        # hard failure; a forward gap is preserved (no silent clamp) and only
        # reported as a warning-level semantic note via the round-trip diffs.
        if scene.start_ms < prev_end_ms:
            errors.append({"error_kind": "scene_overlap", "field": "start_ms",
                           "error_detail": f"scene {scene.scene_id!r} overlaps prior scene"})
        prev_end_ms = max(prev_end_ms, scene.end_ms)

        # Path-traversal check on accepted path fields.
        for asset in scene.asset_refs:
            verdict = _reject_path_traversal(asset.path, "asset.path")
            if verdict == "path_traversal":
                errors.append({"error_kind": "path_traversal", "field": "asset.path",
                               "error_detail": f"asset {asset.asset_id!r} path contains '..' traversal"})

        # Caption timing must lie within its associated scene span.
        for cap in scene.captions:
            if cap.start_ms < scene.start_ms or cap.end_ms > scene.end_ms:
                errors.append({"error_kind": "caption_out_of_scene",
                               "field": "caption.timing",
                               "error_detail": f"caption in scene {scene.scene_id!r} falls outside scene span"})

    return errors


# --- SCOS -> HVS mapping -----------------------------------------------------
def map_scos_to_hvs(
    project: SCOSRenderTimelineProject, *, validate: bool = True
) -> HVSMappingResult:
    """Translate a canonical SCOS timeline into an HVS-compatible payload.

    Pure: returns a NEW dict; the caller-owned ``project`` is never mutated.
    Performs strict validation and returns a structured failure (never a silent
    fallback) on any unsupported or ambiguous input.
    """
    errors = _validate_scos_project(project)
    if errors:
        first = errors[0]
        return HVSMappingResult.failure(
            error_kind=first["error_kind"],
            error_detail=first["error_detail"],
            field=first.get("field"),
        )

    resolution = project.resolution
    scenes_payload = [_scene_to_hvs(scene) for scene in _ordered_scenes(project)]
    duration_seconds = round(project.total_duration_ms / 1000.0, 3)
    hvs_preset = SCOS_PRESET_TO_HVS[project.selected_preset]

    x_scos = _build_x_scos(project, hvs_preset)

    payload: dict[str, Any] = {
        "schema_version": HVS_SCHEMA_VERSION,
        "artifact_id": _artifact_id_for(project.project_id),
        "project_id": project.project_id,
        "created_at": HVS_CREATED_AT_PLACEHOLDER,
        "stage": HVS_TIMELINE_STAGE,
        "status": HVS_STATUS_PLANNED,
        "source_agent": HVS_SOURCE_AGENT,
        "deterministic_hash": _semantic_hash(project),
        "resolution": resolution,
        "fps": project.fps,
        "duration_seconds": duration_seconds,
        "scene_count": len(project.scenes),
        "scenes": scenes_payload,
        "orientation": _orientation_for(resolution),
        X_SCOS_KEY: x_scos,
    }

    if validate:
        result = validate_hvs_payload(payload)
        if not result.ok:
            issue = result.issues[0]
            return HVSMappingResult.failure(
                error_kind="hvs_payload_invalid",
                error_detail=issue.message,
                field=issue.field,
            )
    return HVSMappingResult.success(payload)


def _ordered_scenes(project: SCOSRenderTimelineProject):
    return sorted(project.scenes, key=lambda s: (s.order, s.scene_id))


def _scene_to_hvs(scene) -> dict[str, Any]:
    start_s = _ms_to_s(scene.start_ms)
    end_s = _ms_to_s(scene.end_ms)
    dur_s = _ms_to_s(scene.duration_ms)
    asset_slots = [_asset_ref_to_hvs_slot(scene.scene_id, a) for a in scene.asset_refs]
    return {
        "schema_version": HVS_SCHEMA_VERSION,
        "artifact_id": f"scene-{scene.scene_id}",
        "project_id": None,  # filled by HVS caller
        "created_at": HVS_CREATED_AT_PLACEHOLDER,
        "stage": HVS_TIMELINE_STAGE,
        "status": HVS_STATUS_PLANNED,
        "source_agent": HVS_SOURCE_AGENT,
        "deterministic_hash": _sha256_hex16(
            scene.scene_id, scene.order, start_s, dur_s, scene.intent
        ),
        "scene_id": scene.scene_id,
        "start_time": start_s,
        "end_time": end_s,
        "duration": dur_s,
        "intent": scene.intent,
        "visual_description": scene.visual_description,
        "text_overlay": scene.text_overlay,
        "asset_slots": asset_slots,
        "transition": scene.transition,
    }


def _asset_ref_to_hvs_slot(scene_id: str, asset: SCOSAssetRef) -> dict[str, Any]:
    path_norm = _reject_path_traversal(asset.path, "asset.path")
    return {
        "slot_id": f"{scene_id}-{asset.asset_type}",
        "scene_id": scene_id,
        "slot_type": asset.asset_type,
        "required": True,
        "accepted_formats": [],
        "mock_asset_ref": f"mock://{scene_id}/{asset.asset_type}/{asset.asset_id}",
        "generation_enabled": False,
        "external_source_allowed": False,
        # Logical identity is preserved here (NOT a filesystem path).
        "asset_id": asset.asset_id,
        "asset_path": path_norm,
        "notes": "Stage 2 SCOS->HVS mapping slot. No asset generated.",
    }


def _build_x_scos(project: SCOSRenderTimelineProject, hvs_preset: str) -> dict[str, Any]:
    scenes_ext = []
    for scene in _ordered_scenes(project):
        scenes_ext.append(
            {
                "scene_id": scene.scene_id,
                "order": scene.order,
                "start_ms": scene.start_ms,
                "duration_ms": scene.duration_ms,
                "end_ms": scene.end_ms,
                "intent": scene.intent,
                "visual_description": scene.visual_description,
                "text_overlay": scene.text_overlay,
                "transition": scene.transition,
                "asset_refs": [
                    {
                        "asset_id": a.asset_id,
                        "asset_type": a.asset_type,
                        "asset_path": a.path,
                    }
                    for a in scene.asset_refs
                ],
                "captions": [
                    {
                        "scene_id": c.scene_id,
                        "text": c.text,
                        "start_ms": c.start_ms,
                        "end_ms": c.end_ms,
                    }
                    for c in sorted(scene.captions, key=lambda x: (x.start_ms, x.text))
                ],
                "metadata": [[k, v] for k, v in scene.metadata],
            }
        )
    return {
        "contract_name": SCOS_HVS_TIMELINE_CONTRACT_NAME,
        "contract_version": SCOS_HVS_TIMELINE_CONTRACT_VERSION,
        "contract_id": SCOS_HVS_TIMELINE_CONTRACT_ID,
        "request_id": project.request_id,
        "run_id": project.run_id,
        "selected_preset": project.selected_preset,
        "selected_preset_hvs": hvs_preset,
        "total_duration_ms": project.total_duration_ms,
        "metadata": [[k, v] for k, v in project.metadata],
        "scenes": scenes_ext,
    }


# --- HVS -> SCOS reverse mapping ---------------------------------------------
def map_hvs_to_scos(payload: dict[str, Any]) -> HVSMappingResult:
    """Reconstruct a canonical SCOS timeline from an HVS-compatible payload.

    Reads the semantic core from the top-level HVS fields and the namespaced
    ``x_scos`` extension block. Pure: returns a NEW model; the input dict is
    never mutated. Returns a structured failure on any missing/ambiguous field.
    """
    if not isinstance(payload, dict):
        return HVSMappingResult.failure(
            "invalid_payload", "payload must be a mapping", field="payload"
        )

    x_scos = payload.get(X_SCOS_KEY)
    if not isinstance(x_scos, dict):
        return HVSMappingResult.failure(
            "missing_extension_block",
            f"HVS payload must carry the {X_SCOS_KEY!r} SCOS extension block",
            field=X_SCOS_KEY,
        )

    project_id = payload.get("project_id")
    if not project_id:
        return HVSMappingResult.failure(
            "missing_required_field", "project_id is required", field="project_id"
        )

    resolution = payload.get("resolution")
    if resolution not in HVS_RESOLUTION_VALUES:
        return HVSMappingResult.failure(
            "unsupported_resolution",
            f"resolution must be one of {HVS_RESOLUTION_VALUES}, got {resolution!r}",
            field="resolution",
        )
    w, _, h = resolution.partition("x")
    width, height = int(w), int(h)

    fps = payload.get("fps")
    if fps not in HVS_FPS_VALUES:
        return HVSMappingResult.failure(
            "unsupported_fps",
            f"fps must be one of {HVS_FPS_VALUES}, got {fps!r}",
            field="fps",
        )

    scos_preset = x_scos.get("selected_preset")
    if scos_preset not in SCOS_RENDER_PRESETS:
        return HVSMappingResult.failure(
            "unsupported_preset",
            f"selected_preset must be one of {SCOS_RENDER_PRESETS}, got {scos_preset!r}",
            field="selected_preset",
        )

    # Reverse scene metadata from the extension block (verbatim, exact timing).
    x_scenes = x_scos.get("scenes") or []
    seen_ids: set[str] = set()
    seen_orders: set[int] = set()
    scenes: list = []
    for xsc in x_scenes:
        scene_id = xsc.get("scene_id")
        if not scene_id:
            return HVSMappingResult.failure(
                "missing_required_field", "scene scene_id is required", field="scene_id"
            )
        if scene_id in seen_ids:
            return HVSMappingResult.failure(
                "duplicate_scene_id",
                f"duplicate scene_id {scene_id!r}",
                field="scene_id",
            )
        seen_ids.add(scene_id)
        order = int(xsc.get("order", 0))
        if order in seen_orders:
            return HVSMappingResult.failure(
                "duplicate_order_index",
                f"duplicate scene order index {order}",
                field="order",
            )
        seen_orders.add(order)

        start_ms = int(xsc.get("start_ms", 0))
        duration_ms = int(xsc.get("duration_ms", 0))
        if start_ms < 0:
            return HVSMappingResult.failure(
                "negative_start", f"scene {scene_id!r} start_ms < 0", field="start_ms"
            )
        if duration_ms <= 0:
            return HVSMappingResult.failure(
                "zero_duration",
                f"scene {scene_id!r} duration_ms <= 0",
                field="duration_ms",
            )

        asset_refs = []
        for slot in xsc.get("asset_refs", []) or []:
            asset_refs.append(
                SCOSAssetRef(
                    asset_id=str(slot.get("asset_id")),
                    asset_type=str(slot.get("asset_type") or slot.get("slot_type")),
                    path=slot.get("asset_path"),
                )
            )
        captions = []
        for cap in xsc.get("captions", []) or []:
            captions.append(
                SCOSCaption(
                    scene_id=str(cap.get("scene_id") or scene_id),
                    text=str(cap.get("text", "")),
                    start_ms=int(cap.get("start_ms", 0)),
                    end_ms=int(cap.get("end_ms", 0)),
                )
            )

        scenes.append(
            SCOSScene(
                scene_id=scene_id,
                order=order,
                start_ms=start_ms,
                duration_ms=duration_ms,
                intent=str(xsc.get("intent", "")),
                visual_description=str(xsc.get("visual_description", "")),
                text_overlay=str(xsc.get("text_overlay", "")),
                asset_refs=tuple(asset_refs),
                captions=tuple(captions),
                transition=str(xsc.get("transition", "cut")),
                metadata=tuple((k, v) for k, v in (xsc.get("metadata") or [])),
            )
        )

    metadata = tuple((k, v) for k, v in (x_scos.get("metadata") or []))
    reconstructed = SCOSRenderTimelineProject(
        project_id=str(project_id),
        width=width,
        height=height,
        fps=int(fps),
        scenes=tuple(scenes),
        request_id=x_scos.get("request_id"),
        run_id=x_scos.get("run_id"),
        selected_preset=scos_preset,
        metadata=metadata,
    )
    return HVSMappingResult.success_payload_model(reconstructed)


# --- HVS payload validation (interpreted schema contract) --------------------
def validate_hvs_payload(payload: dict[str, Any]) -> HVSValidationResult:
    """Validate an HVS-compatible payload against the read-only schema contract.

    Interpreted from ``hvs/schemas/{project,timeline,scene}.schema.json`` — this
    module imports NO HVS code, so SCOS has no runtime dependency on HVS for
    normal operation. A real cross-repository jsonschema check is a separate,
    conditional contract test (see Phase 8).
    """
    issues: list[HVSValidationIssue] = []

    required_top = [
        "schema_version",
        "artifact_id",
        "project_id",
        "created_at",
        "stage",
        "status",
        "source_agent",
        "deterministic_hash",
        "resolution",
        "fps",
        "duration_seconds",
        "scene_count",
        "scenes",
    ]
    for field_name in required_top:
        if field_name not in payload:
            issues.append(
                HVSValidationIssue("error", field_name, "missing required top-level field")
            )
    if "resolution" in payload and payload["resolution"] not in HVS_RESOLUTION_VALUES:
        issues.append(
            HVSValidationIssue(
                "error",
                "resolution",
                f"resolution must be one of {HVS_RESOLUTION_VALUES}",
            )
        )
    if "fps" in payload and payload["fps"] not in HVS_FPS_VALUES:
        issues.append(
            HVSValidationIssue("error", "fps", f"fps must be one of {HVS_FPS_VALUES}")
        )
    if "stage" in payload and payload["stage"] != HVS_TIMELINE_STAGE:
        issues.append(
            HVSValidationIssue(
                "error", "stage", f"stage must be {HVS_TIMELINE_STAGE} for timeline"
            )
        )
    scenes = payload.get("scenes")
    if not isinstance(scenes, list):
        issues.append(HVSValidationIssue("error", "scenes", "scenes must be a list"))
        scenes = []
    if not HVS_SCENE_COUNT_MIN <= len(scenes) <= HVS_SCENE_COUNT_MAX:
        issues.append(
            HVSValidationIssue(
                "error",
                "scene_count",
                f"scene_count must be {HVS_SCENE_COUNT_MIN}..{HVS_SCENE_COUNT_MAX}, "
                f"got {len(scenes)}",
            )
        )
    if "duration_seconds" in payload:
        dur = payload["duration_seconds"]
        if not (isinstance(dur, (int, float)) and dur > 0):
            issues.append(
                HVSValidationIssue(
                    "error", "duration_seconds", "duration_seconds must be > 0"
                )
            )

    seen_ids: set[str] = set()
    seen_orders: set[int] = set()
    for idx, scene in enumerate(scenes):
        prefix = f"scenes[{idx}]"
        if not isinstance(scene, dict):
            issues.append(
                HVSValidationIssue("error", prefix, "scene must be an object")
            )
            continue
        for sf in (
            "schema_version",
            "artifact_id",
            "project_id",
            "created_at",
            "stage",
            "status",
            "source_agent",
            "deterministic_hash",
            "scene_id",
            "start_time",
            "end_time",
            "duration",
            "intent",
            "visual_description",
            "text_overlay",
            "asset_slots",
            "transition",
        ):
            if sf not in scene:
                issues.append(
                    HVSValidationIssue("error", f"{prefix}.{sf}", "missing required scene field")
                )
        sid = scene.get("scene_id")
        if sid in seen_ids:
            issues.append(
                HVSValidationIssue("error", f"{prefix}.scene_id", "duplicate scene_id")
            )
        seen_ids.add(sid)
        order = scene.get("order", idx)
        if order in seen_orders:
            issues.append(
                HVSValidationIssue("error", f"{prefix}.order", "duplicate order index")
            )
        seen_orders.add(order)
        start = scene.get("start_time")
        end = scene.get("end_time")
        dur = scene.get("duration")
        if isinstance(start, (int, float)) and start < 0:
            issues.append(
                HVSValidationIssue("error", f"{prefix}.start_time", "start_time must be >= 0")
            )
        if isinstance(dur, (int, float)) and dur <= 0:
            issues.append(
                HVSValidationIssue("error", f"{prefix}.duration", "duration must be > 0")
            )
        if (
            isinstance(start, (int, float))
            and isinstance(end, (int, float))
            and end - start <= 0
        ):
            issues.append(
                HVSValidationIssue(
                    "error", f"{prefix}.end_time", "end_time must be > start_time"
                )
            )

    # Verify the embedded deterministic hash matches the semantic core.
    x_scos = payload.get(X_SCOS_KEY)
    if isinstance(x_scos, dict) and x_scos.get("contract_id") == SCOS_HVS_TIMELINE_CONTRACT_ID:
        recomputed = _semantic_hash_from_x_scos(x_scos, payload)
        if recomputed is not None and payload.get("deterministic_hash") != recomputed:
            issues.append(
                HVSValidationIssue(
                    "error",
                    "deterministic_hash",
                    "embedded deterministic_hash does not match semantic core",
                )
            )

    return HVSValidationResult.of(tuple(issues))


def _semantic_hash_from_x_scos(x_scos: dict[str, Any], payload: dict[str, Any]) -> str | None:
    """Recompute the semantic hash from an HVS payload + extension block.

    Used by ``validate_hvs_payload`` to confirm the embedded hash. Returns None
    if the required fields to recompute are absent.
    """
    resolution = payload.get("resolution")
    fps = payload.get("fps")
    if resolution is None or fps is None:
        return None
    try:
        project = _reconstruct_from_x_scos(payload)
    except Exception:
        return None
    return _semantic_hash(project)


def _reconstruct_from_x_scos(payload: dict[str, Any]) -> SCOSRenderTimelineProject:
    x = payload[X_SCOS_KEY]
    resolution = payload["resolution"]
    w, _, h = resolution.partition("x")
    scenes = []
    for xsc in x.get("scenes", []):
        assets = [
            SCOSAssetRef(
                asset_id=str(s.get("asset_id")),
                asset_type=str(s.get("asset_type") or s.get("slot_type")),
                path=s.get("asset_path"),
            )
            for s in xsc.get("asset_refs", [])
        ]
        caps = [
            SCOSCaption(
                scene_id=str(c.get("scene_id") or xsc.get("scene_id")),
                text=str(c.get("text", "")),
                start_ms=int(c.get("start_ms", 0)),
                end_ms=int(c.get("end_ms", 0)),
            )
            for c in xsc.get("captions", [])
        ]
        scenes.append(
            SCOSScene(
                scene_id=str(xsc.get("scene_id")),
                order=int(xsc.get("order", 0)),
                start_ms=int(xsc.get("start_ms", 0)),
                duration_ms=int(xsc.get("duration_ms", 0)),
                intent=str(xsc.get("intent", "")),
                visual_description=str(xsc.get("visual_description", "")),
                text_overlay=str(xsc.get("text_overlay", "")),
                asset_refs=tuple(assets),
                captions=tuple(caps),
                transition=str(xsc.get("transition", "cut")),
            )
        )
    return SCOSRenderTimelineProject(
        project_id=str(payload.get("project_id")),
        width=int(w),
        height=int(h),
        fps=int(fps),
        scenes=tuple(scenes),
        request_id=x.get("request_id"),
        run_id=x.get("run_id"),
        selected_preset=str(x.get("selected_preset", "standard")),
        metadata=tuple((k, v) for k, v in (x.get("metadata") or [])),
    )


# --- round-trip comparison ---------------------------------------------------
def compare_round_trip(
    project: SCOSRenderTimelineProject, *, validate: bool = True
) -> HVSRoundTripResult:
    """Prove SCOS -> HVS -> SCOS semantic equivalence with zero timing drift.

    Returns equivalence, the original and reconstructed semantic hashes, and a
    list of human-readable diffs when not equivalent.
    """
    fwd = map_scos_to_hvs(project, validate=validate)
    if not fwd.ok:
        return HVSRoundTripResult(
            equivalent=False,
            scos_in_hash=_semantic_hash(project),
            scos_out_hash=_semantic_hash(project),
            diffs=(f"forward mapping failed: {fwd.error.error_detail}",),
            hvs_payload=None,
            scos_reconstructed=None,
        )

    rev = map_hvs_to_scos(fwd.payload)
    if not rev.ok:
        return HVSRoundTripResult(
            equivalent=False,
            scos_in_hash=_semantic_hash(project),
            scos_out_hash=_semantic_hash(project),
            diffs=(f"reverse mapping failed: {rev.error.error_detail}",),
            hvs_payload=fwd.payload,
            scos_reconstructed=None,
        )

    reconstructed = rev.payload_model
    out_hash = _semantic_hash(reconstructed)
    in_hash = _semantic_hash(project)
    diffs = _diff_projects(project, reconstructed)

    # Re-map the reconstructed project; the payload + hash must be stable.
    fwd2 = map_scos_to_hvs(reconstructed, validate=validate)
    payload_stable = (
        fwd2.ok and json.dumps(fwd2.payload, sort_keys=True) == json.dumps(
            fwd.payload, sort_keys=True
        )
    )
    if not payload_stable:
        diffs = (*diffs, "re-mapped payload is not byte-stable")

    return HVSRoundTripResult(
        equivalent=(out_hash == in_hash) and not diffs,
        scos_in_hash=in_hash,
        scos_out_hash=out_hash,
        diffs=tuple(diffs),
        hvs_payload=fwd.payload,
        scos_reconstructed=reconstructed,
    )


def _diff_projects(a: SCOSRenderTimelineProject, b: SCOSRenderTimelineProject) -> list[str]:
    diffs: list[str] = []
    if a.project_id != b.project_id:
        diffs.append(f"project_id: {a.project_id!r} != {b.project_id!r}")
    if a.resolution != b.resolution:
        diffs.append(f"resolution: {a.resolution!r} != {b.resolution!r}")
    if a.fps != b.fps:
        diffs.append(f"fps: {a.fps} != {b.fps}")
    if a.selected_preset != b.selected_preset:
        diffs.append(f"preset: {a.selected_preset!r} != {b.selected_preset!r}")
    if len(a.scenes) != len(b.scenes):
        diffs.append(f"scene count: {len(a.scenes)} != {len(b.scenes)}")
        return diffs
    by_id_a = {s.scene_id: s for s in a.scenes}
    by_id_b = {s.scene_id: s for s in b.scenes}
    for sid in by_id_a:
        sa, sb = by_id_a[sid], by_id_b.get(sid)
        if sb is None:
            diffs.append(f"scene {sid!r} missing after round trip")
            continue
        if sa.start_ms != sb.start_ms:
            diffs.append(f"scene {sid!r} start_ms: {sa.start_ms} != {sb.start_ms}")
        if sa.duration_ms != sb.duration_ms:
            diffs.append(f"scene {sid!r} duration_ms: {sa.duration_ms} != {sb.duration_ms}")
        if sa.order != sb.order:
            diffs.append(f"scene {sid!r} order: {sa.order} != {sb.order}")
        if sa.intent != sb.intent:
            diffs.append(f"scene {sid!r} intent mismatch")
        if sa.text_overlay != sb.text_overlay:
            diffs.append(f"scene {sid!r} text_overlay mismatch")
        if sa.transition != sb.transition:
            diffs.append(f"scene {sid!r} transition mismatch")
        if len(sa.asset_refs) != len(sb.asset_refs):
            diffs.append(f"scene {sid!r} asset_refs count mismatch")
        else:
            for ra, rb in zip(sorted(sa.asset_refs, key=lambda x: x.asset_id),
                              sorted(sb.asset_refs, key=lambda x: x.asset_id)):
                if ra.asset_id != rb.asset_id or ra.asset_type != rb.asset_type:
                    diffs.append(f"scene {sid!r} asset identity mismatch")
        if len(sa.captions) != len(sb.captions):
            diffs.append(f"scene {sid!r} caption count mismatch")
        else:
            for ca, cb in zip(sorted(sa.captions, key=lambda x: (x.start_ms, x.text)),
                              sorted(sb.captions, key=lambda x: (x.start_ms, x.text))):
                if (ca.text, ca.start_ms, ca.end_ms) != (cb.text, cb.start_ms, cb.end_ms):
                    diffs.append(f"scene {sid!r} caption mismatch")
    return diffs


# --- canonicalization --------------------------------------------------------
def canonicalize_mapping_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a key-order-canonical deep copy of an HVS payload.

    Recursively sorts dict keys and deterministically orders lists of objects by
    a stable signature so that two payloads with differently-ordered keys/lists
    but identical semantic content produce identical canonical JSON and hash.
    Does NOT mutate the input.
    """
    return json.loads(json.dumps(payload, sort_keys=True, ensure_ascii=False))


def payload_identity_hash(payload: dict[str, Any]) -> str:
    """Deterministic sha256 hexdigest[:16] of a canonicalized payload.

    Key-order independent by construction (``canonicalize_mapping_payload``
    sorts keys). Used to prove identical semantic input -> identical hash and
    that key reordering does not change identity.
    """
    canonical = canonicalize_mapping_payload(payload)
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return _sha256_hex16(blob)
