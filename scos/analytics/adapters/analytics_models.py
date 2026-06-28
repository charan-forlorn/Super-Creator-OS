"""SCOS Stage 3.1 — canonical analytics data model.

`NormalizedAnalytics` is the single platform-independent schema every adapter
converts into. Downstream consumers (FeedbackEngine, Learning) must only ever see
this shape — never platform-specific rows. Pure stdlib, immutable, deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass(frozen=True)
class NormalizedAnalytics:
    """One video's analytics, normalized across platforms.

    Units are canonical: *_seconds in seconds; `retention_rate` and `ctr` are
    fractions in [0, 1]; counts are integers; `publish_time` is an ISO-8601 string.
    `metadata` carries adapter-safe extras (kept empty by default so unknown CSV
    columns are ignored, not leaked).
    """

    video_id: str
    platform: str
    publish_time: str
    views: int
    watch_time_seconds: float
    average_view_duration: float
    retention_rate: float
    ctr: float
    likes: int
    comments: int
    shares: int
    subscribers_gained: int
    duration_seconds: float
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Deterministic dict form (stable key order via dataclass field order)."""
        return asdict(self)
