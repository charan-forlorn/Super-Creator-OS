"""SCOS Cohort 10G — golden render models (pure, stdlib-only, no I/O).

Authoritative, versioned value objects for the three-profile controlled
render matrix, the media-QA schema, and the delivery-package identity.

This module is the structural mirror of ``hvs_render_plan_models`` (Cohort
10E) but widened from the single ``vertical`` profile to the three
representative profiles the Cohort 10G objective requires:

    * vertical_9_16   (1080x1920 @30)  — supported vertical profile
    * square_1_1      (1080x1080 @30)  — supported square profile
    * landscape_16_9  (1920x1080 @30)  — supported landscape profile

The profile dimensions, fps, codecs and durations are derived 1:1 from the
authoritative HVS render-pack contract (``hvs/renderers/render_pack.py``:
``RENDER_PACK_FORMATS``). SCOS never invents profile values; it mirrors the
HVS registry so the renderer output and the QA expectations stay in lockstep.

No filesystem access, no subprocess, no clock, no network, no random. Pure
value objects + deterministic helpers so every reviewer inspects identical
bytes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional

# --------------------------------------------------------------------------
# Versioning
# --------------------------------------------------------------------------
GOLDEN_RENDER_SCHEMA_VERSION = 1
MEDIA_QA_SCHEMA_VERSION = 1
DELIVERY_PACKAGE_SCHEMA_VERSION = 1

# --------------------------------------------------------------------------
# Supported three-profile registry (mirrors HVS RENDER_PACK_FORMATS)
# --------------------------------------------------------------------------
PROFILE_VERSION = 1
SUPPORTED_PROFILE_IDS = ("vertical_9_16", "square_1_1", "landscape_16_9")


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
    # HyperFrames resolution preset token (portrait/square/landscape).
    hf_resolution: str
    # Human-readable platform targets (provenance only; never authoritative).
    platforms: tuple[str, ...] = ()

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
            "hf_resolution": self.hf_resolution,
            "platforms": list(self.platforms),
        }


RENDER_PROFILES: dict[str, RenderProfile] = {
    "vertical_9_16": RenderProfile(
        profile_id="vertical_9_16",
        version=PROFILE_VERSION,
        resolution="1080x1920",
        width=1080,
        height=1920,
        fps=30,
        video_codec="h264",
        pixel_format="yuv420p",
        hf_resolution="portrait",
        platforms=("TikTok", "Instagram Reels", "YouTube Shorts"),
    ),
    "square_1_1": RenderProfile(
        profile_id="square_1_1",
        version=PROFILE_VERSION,
        resolution="1080x1080",
        width=1080,
        height=1080,
        fps=30,
        video_codec="h264",
        pixel_format="yuv420p",
        hf_resolution="square",
        platforms=("Instagram Feed", "Facebook Feed"),
    ),
    "landscape_16_9": RenderProfile(
        profile_id="landscape_16_9",
        version=PROFILE_VERSION,
        resolution="1920x1080",
        width=1920,
        height=1080,
        fps=30,
        video_codec="h264",
        pixel_format="yuv420p",
        hf_resolution="landscape",
        platforms=("YouTube", "Website"),
    ),
}


def is_supported_profile(profile_id: str) -> bool:
    return profile_id in SUPPORTED_PROFILE_IDS


def get_profile(profile_id: str) -> Optional[RenderProfile]:
    return RENDER_PROFILES.get(profile_id)


# --------------------------------------------------------------------------
# Render state machine (extends Cohort 10E vocabulary for the matrix)
# --------------------------------------------------------------------------
STATE_NOT_REQUESTED = "RENDER_NOT_REQUESTED"
STATE_AUTHORIZATION_REQUIRED = "RENDER_AUTHORIZATION_REQUIRED"
STATE_AUTHORIZED = "RENDER_AUTHORIZED"
STATE_RUNNING = "RENDER_RUNNING"
STATE_SUCCEEDED = "RENDER_SUCCEEDED"
STATE_FAILED_CONFIRMED = "RENDER_FAILED_CONFIRMED"
STATE_OUTCOME_UNKNOWN = "RENDER_OUTCOME_UNKNOWN"

# QA states (Cohort 10G §8.1)
QA_NOT_RUN = "QA_NOT_RUN"
QA_RUNNING = "QA_RUNNING"
QA_PASSED = "QA_PASSED"
QA_FAILED_CONFIRMED = "QA_FAILED_CONFIRMED"
QA_UNAVAILABLE = "QA_UNAVAILABLE"

# Delivery states (Cohort 10G §8.1)
DELIVERY_APPROVAL_REQUIRED = "DELIVERY_APPROVAL_REQUIRED"
DELIVERY_APPROVED = "DELIVERY_APPROVED"
DELIVERY_REJECTED = "DELIVERY_REJECTED"
DELIVERY_PACKAGE_READY = "DELIVERY_PACKAGE_READY"
DELIVERY_PACKAGE_FAILED = "DELIVERY_PACKAGE_FAILED"

# State-machine rules (fail-closed; explicit only).
RENDER_TRANSITIONS: dict[str, tuple[str, ...]] = {
    STATE_NOT_REQUESTED: (STATE_AUTHORIZATION_REQUIRED,),
    STATE_AUTHORIZATION_REQUIRED: (STATE_AUTHORIZED, STATE_FAILED_CONFIRMED),
    STATE_AUTHORIZED: (STATE_RUNNING, STATE_FAILED_CONFIRMED),
    STATE_RUNNING: (STATE_SUCCEEDED, STATE_FAILED_CONFIRMED, STATE_OUTCOME_UNKNOWN),
    STATE_SUCCEEDED: (),
    STATE_FAILED_CONFIRMED: (STATE_AUTHORIZATION_REQUIRED,),
    STATE_OUTCOME_UNKNOWN: (STATE_SUCCEEDED, STATE_FAILED_CONFIRMED),
}
QA_TRANSITIONS: dict[str, tuple[str, ...]] = {
    QA_NOT_RUN: (QA_RUNNING,),
    QA_RUNNING: (QA_PASSED, QA_FAILED_CONFIRMED, QA_UNAVAILABLE),
    QA_PASSED: (),
    QA_FAILED_CONFIRMED: (QA_RUNNING,),
    QA_UNAVAILABLE: (QA_RUNNING,),
}
DELIVERY_TRANSITIONS: dict[str, tuple[str, ...]] = {
    DELIVERY_APPROVAL_REQUIRED: (DELIVERY_APPROVED, DELIVERY_REJECTED, DELIVERY_PACKAGE_FAILED),
    DELIVERY_APPROVED: (DELIVERY_PACKAGE_READY, DELIVERY_PACKAGE_FAILED, DELIVERY_REJECTED),
    DELIVERY_REJECTED: (DELIVERY_APPROVAL_REQUIRED,),
    DELIVERY_PACKAGE_READY: (),
    DELIVERY_PACKAGE_FAILED: (DELIVERY_APPROVAL_REQUIRED,),
}


def is_valid_render_transition(frm: str, to: str) -> bool:
    allowed = RENDER_TRANSITIONS.get(frm)
    return allowed is not None and to in allowed


def is_valid_qa_transition(frm: str, to: str) -> bool:
    allowed = QA_TRANSITIONS.get(frm)
    return allowed is not None and to in allowed


def is_valid_delivery_transition(frm: str, to: str) -> bool:
    allowed = DELIVERY_TRANSITIONS.get(frm)
    return allowed is not None and to in allowed


# --------------------------------------------------------------------------
# QA threshold policy (Cohort 10G §8.5 — derived, documented, no magic)
# --------------------------------------------------------------------------
# All thresholds are derived from the supported profiles: fps=30, and the
# HVS batch duration tolerance (0.15s) reused from the existing render-batch
# verification contract (``hvs/renderers/real_render_batch.py``).
QA_POLICY = {
    "schema_version": MEDIA_QA_SCHEMA_VERSION,
    "duration_tolerance_seconds": 0.15,
    "fps_expected": 30,
    # Black-frame: a frame whose mean luminance < this fraction is "black".
    # 0.02 == ~5/255 mean luma; derived from yuv420p 8-bit range.
    "black_luma_threshold": 0.02,
    # Frozen-frame: consecutive sampled frames with ~identical hash (>= this
    # fraction of the whole clip) indicate a stuck/frozen render.
    "frozen_max_identical_fraction": 0.90,
    # Silence: audio stream mean absolute amplitude below this fraction of
    # full scale across the clip is "silence" (only when audio is required).
    "silence_amplitude_threshold": 0.001,
    # Clipping: peak sample amplitude above this fraction triggers clipping.
    "clip_peak_threshold": 0.99,
    # Safe-zone: title/body copy must stay within this inner fraction of the
    # frame for the safe placement check (Thai / caption text).
    "safe_zone_inner_fraction": 0.90,
    # Frame sampling rate for black/frozen detection (frames sampled per sec).
    "sample_frames_per_second": 5,
}


# --------------------------------------------------------------------------
# QA report schema (Cohort 10G §8.3)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class QaCheck:
    name: str
    status: str  # PASS | FAIL | WARN | SKIP
    detail: str
    measured: Optional[Any] = None
    expected: Optional[Any] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "measured": self.measured,
            "expected": self.expected,
        }


@dataclass(frozen=True)
class QaReport:
    schema_version: int
    qa_report_id: str
    project_id: str
    hvs_project_id: str
    attempt_id: str
    artifact_id: str
    artifact_checksum: str
    profile_id: str
    started_at: str
    completed_at: str
    checks: tuple[QaCheck, ...]
    overall_state: str
    failure_codes: tuple[str, ...]
    tool_versions: dict[str, str]
    safe_evidence_summary: dict[str, Any]
    policy_version: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "qa_report_id": self.qa_report_id,
            "project_id": self.project_id,
            "hvs_project_id": self.hvs_project_id,
            "attempt_id": self.attempt_id,
            "artifact_id": self.artifact_id,
            "artifact_checksum": self.artifact_checksum,
            "profile_id": self.profile_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "checks": [c.to_dict() for c in self.checks],
            "overall_state": self.overall_state,
            "failure_codes": list(self.failure_codes),
            "tool_versions": self.tool_versions,
            "safe_evidence_summary": self.safe_evidence_summary,
            "policy_version": self.policy_version,
        }


# --------------------------------------------------------------------------
# Deterministic helpers
# --------------------------------------------------------------------------
def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def derive_qa_report_id(
    *, project_id: str, attempt_id: str, artifact_checksum: str, profile_id: str
) -> str:
    """Deterministic QA report id (replay returns identical id)."""
    return _sha256_hex(
        _canonical_json(
            {
                "project_id": project_id,
                "attempt_id": attempt_id,
                "artifact_checksum": artifact_checksum,
                "profile_id": profile_id,
                "schema": MEDIA_QA_SCHEMA_VERSION,
            }
        )
    )[:32]


def derive_artifact_id(*, hvs_project_id: str, profile_id: str, attempt_id: str) -> str:
    return _sha256_hex(
        _canonical_json(
            {
                "hvs_project_id": hvs_project_id,
                "profile_id": profile_id,
                "attempt_id": attempt_id,
            }
        )
    )[:24]


def derive_delivery_id(*, qa_report_id: str, artifact_checksum: str) -> str:
    return _sha256_hex(
        _canonical_json(
            {"qa_report_id": qa_report_id, "artifact_checksum": artifact_checksum}
        )
    )[:24]
