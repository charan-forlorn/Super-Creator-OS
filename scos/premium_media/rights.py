"""Fail-closed media rights registry.
No asset is eligible for commercial/ad output without explicit, machine-readable rights.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .models import MediaAsset, RightsClass


class RightsError(ValueError):
    """Raised when an asset cannot legally be used for the requested output scope."""


def validate_asset_for_publish(asset: MediaAsset, *, platform: str, for_ad: bool) -> None:
    rights = asset.rights
    if rights is None:
        raise RightsError(f"{asset.asset_id}: missing rights record")
    if not rights.source_url:
        raise RightsError(f"{asset.asset_id}: missing source URL")
    if not rights.license_name:
        raise RightsError(f"{asset.asset_id}: missing license name")
    if rights.rights_class in {RightsClass.UNKNOWN, RightsClass.PROHIBITED, RightsClass.NONCOMMERCIAL}:
        raise RightsError(f"{asset.asset_id}: rights class {rights.rights_class.value} is not publishable")
    if for_ad and not rights.commercial_ok:
        raise RightsError(f"{asset.asset_id}: commercial use is not cleared")
    if rights.allowed_platforms and platform not in rights.allowed_platforms:
        raise RightsError(
            f"{asset.asset_id}: platform {platform!r} is outside allowed scope "
            f"{rights.allowed_platforms}"
        )
    if rights.rights_class == RightsClass.CC_BY and not rights.attribution_required:
        raise RightsError(f"{asset.asset_id}: CC-BY record must require attribution")
    if rights.expires_at and not rights.expires_at.strip():
        raise RightsError(f"{asset.asset_id}: malformed expiry metadata")


def validate_manifest_for_publish(assets: Iterable[MediaAsset], *, platform: str, for_ad: bool) -> list[str]:
    errors: list[str] = []
    for asset in assets:
        try:
            validate_asset_for_publish(asset, platform=platform, for_ad=for_ad)
        except RightsError as exc:
            errors.append(str(exc))
    return errors


def manifest_entry(asset: MediaAsset) -> dict:
    rights = asset.rights
    return {
        "asset_id": asset.asset_id,
        "path": asset.path,
        "media_type": asset.media_type,
        "duration_s": asset.duration_s,
        "tags": list(asset.tags),
        "language": asset.language,
        "sha256": asset.sha256,
        "rights": None if rights is None else {
            "source_url": rights.source_url,
            "license_name": rights.license_name,
            "rights_class": rights.rights_class.value,
            "commercial_ok": rights.commercial_ok,
            "allowed_platforms": list(rights.allowed_platforms),
            "attribution_required": rights.attribution_required,
            "attribution_text": rights.attribution_text,
            "evidence_url": rights.evidence_url,
            "license_version": rights.license_version,
            "expires_at": rights.expires_at,
            "notes": rights.notes,
        },
        "metadata": asset.metadata,
    }


class AssetRegistry:
    """Append/update registry with deterministic JSON serialization."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> list[MediaAsset]:
        if not self.path.exists():
            return []
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return [self._from_entry(item) for item in raw.get("assets", [])]

    def save(self, assets: Iterable[MediaAsset]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": 1, "assets": [manifest_entry(a) for a in assets]}
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def upsert(self, asset: MediaAsset) -> None:
        assets = self.load()
        replaced = False
        out: list[MediaAsset] = []
        for item in assets:
            if item.asset_id == asset.asset_id:
                out.append(asset)
                replaced = True
            else:
                out.append(item)
        if not replaced:
            out.append(asset)
        self.save(out)

    @staticmethod
    def _from_entry(item: dict) -> MediaAsset:
        rights_raw = item.get("rights")
        rights = None
        if rights_raw:
            rights = __import__("scos.premium_media.models", fromlist=["AssetRights"]).AssetRights(
                source_url=rights_raw["source_url"],
                license_name=rights_raw["license_name"],
                rights_class=RightsClass(rights_raw["rights_class"]),
                commercial_ok=bool(rights_raw["commercial_ok"]),
                allowed_platforms=tuple(rights_raw.get("allowed_platforms", ())),
                attribution_required=bool(rights_raw.get("attribution_required", False)),
                attribution_text=rights_raw.get("attribution_text", ""),
                evidence_url=rights_raw.get("evidence_url", ""),
                license_version=rights_raw.get("license_version", ""),
                expires_at=rights_raw.get("expires_at"),
                notes=rights_raw.get("notes", ""),
            )
        return MediaAsset(
            asset_id=item["asset_id"],
            path=item["path"],
            media_type=item["media_type"],
            duration_s=item.get("duration_s"),
            tags=tuple(item.get("tags", ())),
            language=item.get("language"),
            sha256=item.get("sha256", ""),
            rights=rights,
            metadata=item.get("metadata", {}),
        )
