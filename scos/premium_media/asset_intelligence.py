"""Local-first asset intelligence: index, rights eligibility, and deterministic ranking.

No network access is performed here. Acquisition remains an explicit operator
step; this layer ranks assets that already exist in the authoritative registry.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import MediaAsset
from .rights import RightsError, validate_asset_for_publish


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
