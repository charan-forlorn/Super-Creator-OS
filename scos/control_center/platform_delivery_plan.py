"""Deterministic platform/brand delivery planning; no external dispatch.

This module prepares a publish-ready plan from an already verified artifact.
It does not upload, publish, call Buffer, contact a platform, or become the
artifact/evidence authority. The artifact SHA and upstream delivery lineage
remain authoritative.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from typing import Any

PLAN_SCHEMA_VERSION = 1
STATE_READY_FOR_MANUAL_PUBLISH = "READY_FOR_MANUAL_PUBLISH"
STATE_BLOCKED = "BLOCKED"

PLATFORM_FORMATS: dict[str, dict[str, Any]] = {
    "vertical_9_16": {"platform_family": "tiktok_ig_yt_shorts", "width": 1080, "height": 1920, "fps": 30},
    "square_1_1": {"platform_family": "ig_fb_feed", "width": 1080, "height": 1080, "fps": 30},
    "landscape_16_9": {"platform_family": "youtube_website", "width": 1920, "height": 1080, "fps": 30},
}


def _stable_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class BrandPresentationSpec:
    brand_profile_id: str
    logo_asset_id: str | None
    primary_color: str | None
    accent_color: str | None
    font_family: str | None
    tone_label: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PlatformVariant:
    format_id: str
    platform_family: str
    width: int
    height: int
    fps: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PlatformDeliveryPlan:
    schema_version: int
    plan_id: str
    source_artifact_id: str
    source_artifact_sha256: str
    brand: BrandPresentationSpec
    variants: tuple[PlatformVariant, ...]
    caption: str
    title: str
    hashtags: tuple[str, ...]
    state: str
    external_dispatch_allowed: bool
    human_publish_required: bool
    blockers: tuple[str, ...]
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "source_artifact_id": self.source_artifact_id,
            "source_artifact_sha256": self.source_artifact_sha256,
            "brand": self.brand.to_dict(),
            "variants": [item.to_dict() for item in self.variants],
            "caption": self.caption,
            "title": self.title,
            "hashtags": list(self.hashtags),
            "state": self.state,
            "external_dispatch_allowed": self.external_dispatch_allowed,
            "human_publish_required": self.human_publish_required,
            "blockers": list(self.blockers),
            "content_hash": self.content_hash,
        }


def platform_variant(format_id: str) -> PlatformVariant:
    try:
        raw = PLATFORM_FORMATS[format_id]
    except KeyError as exc:
        raise ValueError(f"unsupported platform format: {format_id!r}") from exc
    return PlatformVariant(format_id=format_id, **raw)


def build_platform_delivery_plan(
    *,
    source_artifact_id: str,
    source_artifact_sha256: str,
    brand: BrandPresentationSpec,
    format_ids: tuple[str, ...],
    title: str,
    caption: str,
    hashtags: tuple[str, ...] = (),
    expected_artifact_sha256: str | None = None,
) -> PlatformDeliveryPlan:
    blockers: list[str] = []
    artifact_sha = str(source_artifact_sha256 or "").strip().lower()
    if len(artifact_sha) != 64 or any(c not in "0123456789abcdef" for c in artifact_sha):
        blockers.append("INVALID_ARTIFACT_SHA256")
    if expected_artifact_sha256 and artifact_sha != expected_artifact_sha256.strip().lower():
        blockers.append("ARTIFACT_SHA256_MISMATCH")
    if not source_artifact_id.strip():
        blockers.append("MISSING_ARTIFACT_ID")
    if not brand.brand_profile_id.strip():
        blockers.append("MISSING_BRAND_PROFILE_ID")
    if not title.strip():
        blockers.append("MISSING_TITLE")
    if not caption.strip():
        blockers.append("MISSING_CAPTION")
    if not format_ids:
        blockers.append("NO_PLATFORM_VARIANTS")

    variants: list[PlatformVariant] = []
    for format_id in format_ids:
        try:
            variants.append(platform_variant(format_id))
        except ValueError:
            blockers.append(f"UNSUPPORTED_FORMAT:{format_id}")

    unique_variants = {item.format_id: item for item in variants}
    variants = [unique_variants[key] for key in sorted(unique_variants)]

    payload = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "source_artifact_id": source_artifact_id,
        "source_artifact_sha256": artifact_sha,
        "brand": brand.to_dict(),
        "variants": [item.to_dict() for item in variants],
        "title": title.strip(),
        "caption": caption.strip(),
        "hashtags": [item.strip() for item in hashtags if item.strip()],
    }
    content_hash = _stable_hash(payload)
    plan_id = f"scos-platform-plan-{content_hash[:16]}"
    state = STATE_READY_FOR_MANUAL_PUBLISH if not blockers else STATE_BLOCKED

    return PlatformDeliveryPlan(
        schema_version=PLAN_SCHEMA_VERSION,
        plan_id=plan_id,
        source_artifact_id=source_artifact_id,
        source_artifact_sha256=artifact_sha,
        brand=brand,
        variants=tuple(variants),
        caption=caption.strip(),
        title=title.strip(),
        hashtags=tuple(item.strip() for item in hashtags if item.strip()),
        state=state,
        external_dispatch_allowed=False,
        human_publish_required=True,
        blockers=tuple(sorted(set(blockers))),
        content_hash=content_hash,
    )


def validate_artifact_binding(
    plan: PlatformDeliveryPlan,
    *,
    actual_artifact_sha256: str,
) -> tuple[str, ...]:
    blockers: list[str] = []
    actual = str(actual_artifact_sha256 or "").strip().lower()
    if actual != plan.source_artifact_sha256:
        blockers.append("ARTIFACT_SHA256_MISMATCH")
    if plan.state == STATE_BLOCKED:
        blockers.extend(plan.blockers)
    return tuple(sorted(set(blockers)))


__all__ = [
    "BrandPresentationSpec",
    "PLAN_SCHEMA_VERSION",
    "PLATFORM_FORMATS",
    "PlatformDeliveryPlan",
    "PlatformVariant",
    "STATE_BLOCKED",
    "STATE_READY_FOR_MANUAL_PUBLISH",
    "build_platform_delivery_plan",
    "platform_variant",
    "validate_artifact_binding",
]
