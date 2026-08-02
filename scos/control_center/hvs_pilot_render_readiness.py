"""Pre-render readiness authority for an admitted paid-pilot project (§6.F).

READ-ONLY. Verifies that an admitted packet, a materialized project, and the
required approved assets are all present and consistent BEFORE any render.

It does NOT issue a render authorization and does NOT invoke a renderer. It only
returns a browser-safe verdict projection.

This is a DISTINCT capability from the post-render delivery readiness authority
(``hvs_paid_pilot_readiness``) and must not reuse or rename it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .hvs_pilot_identity import derive_canonical_id

SCHEMA_VERSION = "scos-hvs.pilot-render-readiness.v1/1.0.0"

# Required packet-approved assets for the PILOT-2026-001 contract.
REQUIRED_ASSET_SAFE_NAMES = ("product-front.jpg", "customer-logo.png", "promo-music-31s.mp3")
REQUIRED_OUTPUT_PROFILE = "vertical_9_16"
REQUIRED_DIMENSIONS = "1080x1920"
DURATION_LOWER = 29.0
DURATION_UPPER = 31.0
# Approved Thai-capable font families (open-source approved).
APPROVED_THAI_FONTS = (
    "noto sans thai", "noto sans thai ui", "leelawadee ui", "tahoma", "thsarabun", "garuda", "loma", "waree",
)


@dataclass(frozen=True)
class ReadinessCheck:
    token: str
    passed: bool
    reason_code: str
    detail: str


@dataclass(frozen=True)
class RenderReadinessResult:
    ok: bool
    state: str  # READY_FOR_RENDER | NOT_READY | BLOCKED
    error_code: Optional[str]
    detail: Optional[str]
    checks: tuple[ReadinessCheck, ...] = ()
    projection: dict[str, Any] = field(default_factory=dict)

    def to_response(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "state": self.state,
            "error_code": self.error_code,
            "detail": self.detail,
            "checks": [c.__dict__ for c in self.checks],
            "projection": self.projection,
        }


def _safe_load_json(p: Path) -> Optional[dict[str, Any]]:
    try:
        if not p.is_file():
            return None
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def evaluate_render_readiness(
    *,
    admission_store_path: str,
    materialization_store_path: str,
    hvs_projects_root: str,
    output_root: str,
    canonical_internal_project_id: str = "",
    external_project_ref: str = "",
) -> RenderReadinessResult:
    checks: list[ReadinessCheck] = []

    # The canonical internal ID is derived server-side from the admitted
    # external project_ref; it is never trusted from a request body. If the
    # caller (server route) did not pre-resolve it, derive it here.
    if not canonical_internal_project_id:
        canonical_internal_project_id = derive_canonical_id(external_project_ref)

    # 1. Admitted packet exists
    admission = _safe_load_json(Path(admission_store_path))
    packet_ok = admission is not None and admission.get("packet_sha256")
    checks.append(ReadinessCheck("ADMITTED_PACKET", packet_ok, "OK" if packet_ok else "ADMISSION_RECORD_MISSING",
                                "packet admission record present" if packet_ok else "no admission record"))
    if not packet_ok:
        return _fail(checks, "NO_ADMISSION", "packet not admitted")

    # 2. Project identity matches
    adm_ref = admission.get("project_ref")
    id_ok = adm_ref == external_project_ref
    checks.append(ReadinessCheck("PROJECT_IDENTITY", id_ok, "OK" if id_ok else "PROJECT_REF_MISMATCH",
                                f"admitted {adm_ref} vs expected {external_project_ref}"))
    if not id_ok:
        return _fail(checks, "PROJECT_IDENTITY_MISMATCH", "project_ref mismatch")

    # 3. Materialization exists
    materialization = _safe_load_json(Path(materialization_store_path))
    mat_ok = materialization is not None and materialization.get("canonical_internal_project_id") == canonical_internal_project_id
    checks.append(ReadinessCheck("MATERIALIZATION", mat_ok, "OK" if mat_ok else "MATERIALIZATION_RECORD_MISSING",
                                "materialization record present" if mat_ok else "no materialization record"))
    if not mat_ok:
        return _fail(checks, "NO_MATERIALIZATION", "materialization not found")

    # 4. HVS project directory exists and parses
    hvs_root = Path(hvs_projects_root)
    hvs_proj_dir = hvs_root / canonical_internal_project_id
    hvs_ok = hvs_proj_dir.is_dir()
    # Browser-facing detail must NOT expose the absolute operator filesystem path;
    # report only the canonical subdir name (relative, non-sensitive).
    hvs_detail = f"hvs-projects/{canonical_internal_project_id}" if hvs_ok else "HVS project directory absent"
    checks.append(ReadinessCheck("HVS_PROJECT_DIR", hvs_ok, "OK" if hvs_ok else "HVS_PROJECT_DIR_MISSING",
                                hvs_detail))
    if not hvs_ok:
        return _fail(checks, "HVS_PROJECT_DIR_MISSING", "HVS project directory not found")

    # 5. Approved assets bound (by safe_name, packet-faithful)
    bound_names = set(materialization.get("asset_safe_names", []))
    assets_ok = set(REQUIRED_ASSET_SAFE_NAMES) <= bound_names
    missing = [n for n in REQUIRED_ASSET_SAFE_NAMES if n not in bound_names]
    checks.append(ReadinessCheck("APPROVED_ASSETS_BOUND", assets_ok, "OK" if assets_ok else "ASSETS_NOT_BOUND",
                                ("all required assets bound" if assets_ok else f"missing: {missing}")))
    if not assets_ok:
        return _fail(checks, "ASSETS_NOT_BOUND", f"missing approved assets: {missing}")

    # 6. Profile + duration match packet
    prof = materialization.get("output_profile")
    prof_ok = prof == REQUIRED_OUTPUT_PROFILE
    checks.append(ReadinessCheck("OUTPUT_PROFILE", prof_ok, "OK" if prof_ok else "PROFILE_MISMATCH",
                                f"profile {prof} vs required {REQUIRED_OUTPUT_PROFILE}"))
    dur = float(materialization.get("duration_seconds", 0) or 0)
    dur_ok = DURATION_LOWER <= dur <= DURATION_UPPER
    checks.append(ReadinessCheck("DURATION", dur_ok, "OK" if dur_ok else "DURATION_OUT_OF_RANGE",
                                f"{dur}s vs required {DURATION_LOWER}-{DURATION_UPPER}s"))
    if not (prof_ok and dur_ok):
        return _fail(checks, "PROFILE_OR_DURATION_MISMATCH", "profile/duration mismatch")

    # 7. Dimensions present
    dims = materialization.get("dimensions")
    dims_ok = dims == REQUIRED_DIMENSIONS
    checks.append(ReadinessCheck("DIMENSIONS", dims_ok, "OK" if dims_ok else "DIMENSIONS_MISMATCH",
                                f"{dims} vs required {REQUIRED_DIMENSIONS}"))

    # 8. Font supports required Thai text
    font = str(materialization.get("font_family", "")).strip().lower()
    font_ok = font in APPROVED_THAI_FONTS
    checks.append(ReadinessCheck("THAI_FONT", font_ok, "OK" if font_ok else "FONT_NOT_THAI_APPROVED",
                                f"font '{font}' {'approved' if font_ok else 'not in approved Thai set'}"))

    # 9. Audio metadata valid (duration within range)
    audio_dur = float(materialization.get("audio_duration_seconds", 0) or 0)
    audio_ok = DURATION_LOWER <= audio_dur <= DURATION_UPPER
    checks.append(ReadinessCheck("AUDIO_METADATA", audio_ok, "OK" if audio_ok else "AUDIO_METADATA_INVALID",
                                f"audio {audio_dur}s vs required {DURATION_LOWER}-{DURATION_UPPER}s"))

    # 10. Output root valid and EMPTY
    out_root = Path(output_root)
    out_ok = out_root.is_dir()
    try:
        empty = out_ok and not any(out_root.iterdir())
    except Exception:
        empty = False
    checks.append(ReadinessCheck("OUTPUT_ROOT_EMPTY", out_ok and empty, "OK" if (out_ok and empty) else "OUTPUT_ROOT_NOT_EMPTY",
                                "output root exists and is empty" if (out_ok and empty) else "output root missing or not empty"))

    # 11. No render attempt exists (read-only guard)
    attempt_marker = hvs_proj_dir / "RENDER_ATTEMPT.json"
    no_render = not attempt_marker.exists()
    checks.append(ReadinessCheck("NO_RENDER_ATTEMPT", no_render, "OK" if no_render else "RENDER_ATTEMPT_PRESENT",
                                "no render attempt marker" if no_render else "render attempt already present"))

    hard_fail = not (out_ok and empty and no_render and font_ok and audio_ok and dims_ok)
    if hard_fail:
        return _fail(checks, "RENDER_READINESS_INCOMPLETE", "one or more hard readiness checks failed")

    projection = {
        "schema_version": SCHEMA_VERSION,
        "canonical_internal_project_id": canonical_internal_project_id,
        "external_project_ref": external_project_ref,
        "output_profile": prof,
        "dimensions": dims,
        "duration_seconds": dur,
        "audio_duration_seconds": audio_dur,
        "font_family": materialization.get("font_family"),
        "asset_safe_names": sorted(bound_names),
        "render_action": "DISABLED_PRE_AUTHORIZATION",
    }
    return RenderReadinessResult(
        ok=True, state="READY_FOR_RENDER", error_code=None, detail=None,
        checks=tuple(checks), projection=projection,
    )


def _fail(checks: list[ReadinessCheck], code: str, detail: str) -> RenderReadinessResult:
    return RenderReadinessResult(ok=False, state="NOT_READY", error_code=code, detail=detail, checks=tuple(checks))
