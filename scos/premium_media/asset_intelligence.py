"""Local-first asset intelligence: index, rights eligibility, and deterministic ranking.

No network access is performed here. Acquisition remains an explicit operator
step; this layer ranks assets that already exist in the authoritative registry.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from .intake import sha256_file
from .models import AssetRights, MediaAsset, RightsClass
from .rights import AssetRegistry, RightsError, validate_asset_for_publish


@dataclass(frozen=True)
class AssetQuery:
    media_type: str | None = None
    tags: tuple[str, ...] = ()
    language: str | None = None
    target_duration_s: float | None = None
    platform: str | None = None
    for_ad: bool = False


@dataclass(frozen=True)
class AssetCandidate:
    asset: MediaAsset
    score: float
    reasons: tuple[str, ...]


def _score(asset: MediaAsset, query: AssetQuery) -> tuple[float, tuple[str, ...]]:
    score = 0.0
    reasons: list[str] = []
    if query.media_type:
        if asset.media_type == query.media_type:
            score += 40.0
            reasons.append("media_type")
        else:
            score -= 40.0
    if query.tags:
        overlap = len(set(query.tags).intersection(asset.tags))
        score += overlap * 12.0
        if overlap:
            reasons.append(f"tags:{overlap}")
    if query.language:
        if asset.language == query.language:
            score += 10.0
            reasons.append("language")
        elif asset.language:
            score -= 5.0
    if query.target_duration_s is not None and asset.duration_s is not None:
        delta = abs(asset.duration_s - query.target_duration_s)
        score += max(0.0, 15.0 - delta * 2.0)
        if delta < 0.5:
            reasons.append("duration-close")
    return score, tuple(reasons)


def rank_assets(assets: Iterable[MediaAsset], query: AssetQuery) -> tuple[AssetCandidate, ...]:
    ranked: list[AssetCandidate] = []
    for asset in assets:
        if query.platform:
            try:
                validate_asset_for_publish(asset, platform=query.platform, for_ad=query.for_ad)
            except RightsError:
                continue
        score, reasons = _score(asset, query)
        if asset.sha256:
            score += 2.0
            reasons = reasons + ("sealed-sha256",)
        ranked.append(AssetCandidate(asset=asset, score=score, reasons=reasons))
    ranked.sort(key=lambda c: (-c.score, c.asset.asset_id))
    return tuple(ranked)


def select_best_asset(assets: Iterable[MediaAsset], query: AssetQuery) -> AssetCandidate:
    ranked = rank_assets(assets, query)
    if not ranked:
        raise LookupError("no eligible asset matches query")
    return ranked[0]


_INDEX_EXTENSIONS = {
    ".wav": "audio",
    ".mp3": "audio",
    ".m4a": "audio",
    ".aac": "audio",
    ".flac": "audio",
    ".ogg": "audio",
    ".mp4": "video",
    ".mov": "video",
    ".mkv": "video",
    ".webm": "video",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".ttf": "font",
    ".otf": "font",
    ".woff": "font",
    ".woff2": "font",
}


@dataclass(frozen=True)
class AssetIndexReport:
    registry_path: Path
    scanned: int
    indexed: int
    reused: int
    deduplicated: int
    skipped: int
    rights_sidecars: int
    errors: tuple[str, ...]


class LocalAssetIndexer:
    """Incrementally index local media into the existing authoritative AssetRegistry."""

    def __init__(self, registry: AssetRegistry):
        self.registry = registry

    @staticmethod
    def _media_type(path: Path) -> str | None:
        return _INDEX_EXTENSIONS.get(path.suffix.lower())

    @staticmethod
    def _sidecar_path(path: Path) -> Path:
        return path.with_name(path.name + ".rights.json")

    @staticmethod
    def _read_rights_sidecar(path: Path) -> AssetRights | None:
        sidecar = LocalAssetIndexer._sidecar_path(path)
        if not sidecar.is_file():
            return None
        raw = json.loads(sidecar.read_text(encoding="utf-8-sig"))
        return AssetRights(
            source_url=str(raw["source_url"]),
            license_name=str(raw["license_name"]),
            rights_class=RightsClass(str(raw["rights_class"])),
            commercial_ok=bool(raw["commercial_ok"]),

            allowed_platforms=tuple(str(x) for x in raw.get("allowed_platforms", ())),
            attribution_required=bool(raw.get("attribution_required", False)),
            attribution_text=str(raw.get("attribution_text", "")),
            evidence_url=str(raw.get("evidence_url", "")),
            license_version=str(raw.get("license_version", "")),
            expires_at=raw.get("expires_at"),
            notes=str(raw.get("notes", "")),
        )

    @staticmethod
    def _tags_for_path(path: Path, root: Path) -> tuple[str, ...]:
        try:
            relative = path.resolve().relative_to(root.resolve())
            tags = [part.lower() for part in relative.parts[:-1] if part not in {".", ".."}]
        except ValueError:
            tags = []
        return tuple(dict.fromkeys(tags))


    def refresh(self, roots: Sequence[str | Path]) -> AssetIndexReport:

        existing = {asset.path: asset for asset in self.registry.load()}
        next_assets: dict[str, MediaAsset] = {asset.asset_id: asset for asset in existing.values()}
        scanned = indexed = reused = deduplicated = skipped = rights_sidecars = 0
        errors: list[str] = []
        seen_ids: set[str] = set()

        for root_value in roots:
            root = Path(root_value).resolve()
            if not root.is_dir():
                errors.append(f"missing-root:{root}")
                continue
            for path in sorted(root.rglob("*")):
                if not path.is_file() or path.suffix.lower() not in _INDEX_EXTENSIONS:
                    continue
                scanned += 1
                media_type = self._media_type(path)
                if media_type is None:
                    skipped += 1
                    continue
                try:
                    stat = path.stat()
                    prior = existing.get(str(path))
                    metadata = dict(prior.metadata) if prior is not None else {}
                    if (
                        prior is not None
                        and metadata.get("indexed_size_bytes") == stat.st_size
                        and metadata.get("indexed_mtime_ns") == stat.st_mtime_ns
                    ):
                        next_assets[prior.asset_id] = prior
                        seen_ids.add(prior.asset_id)
                        reused += 1
                        continue
                    sha256 = sha256_file(path)
                    asset_id = f"local-{sha256[:16]}"
                    rights = self._read_rights_sidecar(path)
                    if rights is not None:
                        rights_sidecars += 1
                    if asset_id in seen_ids:
                        current = next_assets[asset_id]
                        if rights is not None and current.rights is None:
                            next_assets[asset_id] = MediaAsset(
                                asset_id=current.asset_id,
                                path=current.path,
                                media_type=current.media_type,
                                duration_s=current.duration_s,
                                tags=current.tags,
                                language=current.language,
                                sha256=current.sha256,
                                rights=rights,
                                metadata={
                                    **current.metadata,
                                    "source_sidecar": str(self._sidecar_path(path)),
                                },
                            )
                        elif rights is not None and current.rights != rights:
                            errors.append(f"rights-conflict:{asset_id}:{path}")
                        deduplicated += 1
                        continue
                    tags = self._tags_for_path(path, root)
                    next_assets[asset_id] = MediaAsset(
                        asset_id=asset_id,
                        path=str(path),
                        media_type=media_type,
                        sha256=sha256,
                        rights=rights,
                        tags=tags,
                        metadata={
                            "indexed_size_bytes": stat.st_size,
                            "indexed_mtime_ns": stat.st_mtime_ns,
                            "indexed_root": str(root),
                            "source_sidecar": str(self._sidecar_path(path)) if rights else None,
                        },
                    )
                    seen_ids.add(asset_id)
                    indexed += 1
                except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
                    errors.append(f"{path}:{exc}")

        self.registry.save(sorted(next_assets.values(), key=lambda asset: asset.asset_id))
        return AssetIndexReport(
            registry_path=self.registry.path,
            scanned=scanned,
            indexed=indexed,
            reused=reused,
            deduplicated=deduplicated,
            skipped=skipped,
            rights_sidecars=rights_sidecars,
            errors=tuple(errors),
        )
