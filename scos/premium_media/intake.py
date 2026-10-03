"""Rights-first local media intake.
The importer never infers a license from a URL or filename. Rights evidence is explicit.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from .models import AssetRights, MediaAsset, RightsClass
from .rights import RightsError, validate_asset_for_publish


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ingest_local(
    path: str | Path,
    *,
    asset_id: str,
    media_type: str,
    rights: AssetRights | None,
    tags: tuple[str, ...] = (),
    language: str | None = None,
    duration_s: float | None = None,
    metadata: dict | None = None,
) -> MediaAsset:
    source = Path(path).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    return MediaAsset(
        asset_id=asset_id,
        path=str(source),
        media_type=media_type,
        duration_s=duration_s,
        tags=tags,
        language=language,
        sha256=sha256_file(source),
        rights=rights,
        metadata=metadata or {},
    )


def assert_ad_asset(asset: MediaAsset, platform: str) -> None:
    validate_asset_for_publish(asset, platform=platform, for_ad=True)


def require_explicit_rights(asset: MediaAsset) -> None:
    if asset.rights is None:
        raise RightsError(f"{asset.asset_id}: no rights evidence; asset is not eligible")
    if asset.rights.rights_class == RightsClass.UNKNOWN:
        raise RightsError(f"{asset.asset_id}: rights are explicitly unknown")
