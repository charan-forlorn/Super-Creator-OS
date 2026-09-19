"""Read-only bridge to SCOS Control Center's authoritative local Brand Kit store.
No browser paths, network calls, or inferred fallback data are accepted.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BRAND_KIT_SCHEMA_VERSION = 1
STORE_KIND = "scos.brand_kit.v1"


@dataclass(frozen=True)
class BrandProfile:
    brand_kit_id: str
    schema_version: int
    name: str
    primary: str
    secondary: str
    accent: str
    neutrals: tuple[str, ...]
    heading_font: str
    body_font: str
    logo_asset_ref: str
    cta_label: str
    cta_target: str

    def fingerprint(self) -> str:
        payload = {
            "brand_kit_id": self.brand_kit_id,
            "schema_version": self.schema_version,
            "name": self.name,
            "colors": {
                "primary": self.primary,
                "secondary": self.secondary,
                "accent": self.accent,
                "neutrals": self.neutrals,
            },
            "fonts": {"heading": self.heading_font, "body": self.body_font},
            "logo_asset_ref": self.logo_asset_ref,
            "cta": {"label": self.cta_label, "target": self.cta_target},
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class BrandKitError(ValueError):
    pass


def canonical_store_path(repo_root: Path) -> Path:
    return (repo_root / "memory" / "runtime" / "control-center" / "brand-kit-v1.json").resolve()


def load_brand_profiles(repo_root: Path) -> tuple[str, tuple[BrandProfile, ...]]:
    path = canonical_store_path(repo_root)
    if not path.exists():
        return "EMPTY", ()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BrandKitError(f"brand kit store unavailable/corrupt: {exc}") from exc
    if not isinstance(data, dict):
        raise BrandKitError("brand kit store envelope must be an object")
    if data.get("store_kind") not in (None, STORE_KIND):
        raise BrandKitError("brand kit store_kind mismatch")
    if data.get("schema_version") != BRAND_KIT_SCHEMA_VERSION:
        raise BrandKitError("brand kit schema version unsupported")
    records = data.get("records")
    if not isinstance(records, list):
        raise BrandKitError("brand kit records must be an array")
    if not records:
        return "EMPTY", ()
    out: list[BrandProfile] = []
    for raw in records:
        if not isinstance(raw, dict):
            raise BrandKitError("brand kit record must be an object")
        colors = raw.get("colors") or {}
        fonts = raw.get("fonts") or {}
        logo = raw.get("logo") or {}
        cta = raw.get("basic_cta") or {}
        required = {
            "brand_kit_id": raw.get("brand_kit_id"),
            "schema_version": raw.get("schema_version"),
            "name": raw.get("name"),
            "primary": colors.get("primary"),
            "secondary": colors.get("secondary"),
            "accent": colors.get("accent"),
            "heading": fonts.get("heading"),
            "body": fonts.get("body"),
            "logo_asset_ref": logo.get("asset_ref"),
            "cta_label": cta.get("label"),
            "cta_target": cta.get("target"),
        }
        if any(value in (None, "") for value in required.values()):
            raise BrandKitError(f"incomplete brand kit: {raw.get('brand_kit_id')!r}")
        if raw.get("schema_version") != BRAND_KIT_SCHEMA_VERSION:
            raise BrandKitError("brand kit record schema mismatch")
        out.append(
            BrandProfile(
                brand_kit_id=str(raw["brand_kit_id"]),
                schema_version=int(raw["schema_version"]),
                name=str(raw["name"]),
                primary=str(colors["primary"]),
                secondary=str(colors["secondary"]),
                accent=str(colors["accent"]),
                neutrals=tuple(str(x) for x in colors.get("neutrals", ())),
                heading_font=str(fonts["heading"]),
                body_font=str(fonts["body"]),
                logo_asset_ref=str(logo["asset_ref"]),
                cta_label=str(cta["label"]),
                cta_target=str(cta["target"]),
            )
        )
    return "AVAILABLE_WITH_DATA", tuple(sorted(out, key=lambda x: x.brand_kit_id))


def resolve_brand_profile(repo_root: Path, brand_kit_id: str | None) -> BrandProfile | None:
    if not brand_kit_id:
        return None
    status, records = load_brand_profiles(repo_root)
    if status != "AVAILABLE_WITH_DATA":
        raise BrandKitError(f"brand kit {brand_kit_id!r} requested but store status is {status}")
    for record in records:
        if record.brand_kit_id == brand_kit_id:
            return record
    raise BrandKitError(f"brand kit not found: {brand_kit_id}")
