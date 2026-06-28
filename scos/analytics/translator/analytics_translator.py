"""SCOS Stage 3.2 — Analytics Translator (orchestration only).

Bridges platform-independent analytics (`NormalizedAnalytics`) into the exact feedback
payload the certified FeedbackEngine / LearningCoordinator already consume. It contains
NO learning logic and NO conversion formulas — every formula lives in
`translation_rules.py`, injected via the constructor.

Pure orchestration: validate input → delegate to the rules → assemble a deterministic
payload. No persistence, no learning, no style updates, no coordinator calls. Input is
never mutated.
"""

from __future__ import annotations

import math

from translation_rules import TranslationRules

# Attributes a NormalizedAnalytics record must expose to be translatable.
_REQUIRED_ATTRS = (
    "video_id", "platform", "views", "ctr", "retention_rate",
    "likes", "comments", "shares", "subscribers_gained",
    "watch_time_seconds", "average_view_duration", "duration_seconds",
)
_NONNEG_COUNTS = ("views", "likes", "comments", "shares", "subscribers_gained")
_NONNEG_FLOATS = ("watch_time_seconds", "average_view_duration", "duration_seconds")
_UNIT_FRACTIONS = ("ctr", "retention_rate")


class TranslationError(Exception):
    """Raised on invalid analytics input. Never silently repairs data."""


class AnalyticsTranslator:
    """Deterministic analytics → feedback-payload translator."""

    def __init__(self, policy: TranslationRules | None = None) -> None:
        self.policy = policy or TranslationRules()

    def translate(self, records: list, content_type: str | None = None) -> dict:
        """Translate List[NormalizedAnalytics] into a single feedback payload.

        Returns ONLY the feedback contract; raises TranslationError on invalid input.
        """
        self._validate(records)

        agg = self.policy.aggregate(records)
        retention = self.policy.retention_score(agg)
        engagement = self.policy.engagement_score(agg)
        quality = self.policy.quality_score(agg)
        style_match = self.policy.style_match_score(agg)
        updates = self.policy.derived_style_updates(retention, engagement, style_match)

        return {
            "content_type": self.policy.content_type(records, content_type),
            "quality_score": quality,
            "engagement_score": engagement,
            "retention_score": retention,
            "style_match_score": style_match,
            "derived_style_updates": updates,
        }

    # ------------------------------------------------------------------ #
    # validation (deterministic; never auto-fixes)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _validate(records: list) -> None:
        if not isinstance(records, list) or not records:
            raise TranslationError("no records: expected a non-empty List[NormalizedAnalytics]")

        for i, r in enumerate(records):
            for attr in _REQUIRED_ATTRS:
                if not hasattr(r, attr):
                    raise TranslationError(f"record {i}: missing required field: {attr}")

            vid = getattr(r, "video_id", f"#{i}")
            for attr in _NONNEG_COUNTS:
                v = getattr(r, attr)
                if not _finite(v):
                    raise TranslationError(f"record {vid}: {attr} is not finite: {v!r}")
                if v < 0:
                    raise TranslationError(f"record {vid}: negative {attr}: {v}")
            for attr in _NONNEG_FLOATS:
                v = getattr(r, attr)
                if not _finite(v):
                    raise TranslationError(f"record {vid}: {attr} is not finite: {v!r}")
                if v < 0:
                    raise TranslationError(f"record {vid}: negative {attr}: {v}")
            for attr in _UNIT_FRACTIONS:
                v = getattr(r, attr)
                if not _finite(v):
                    raise TranslationError(f"record {vid}: {attr} is not finite: {v!r}")
                if not (0.0 <= v <= 1.0):
                    raise TranslationError(f"record {vid}: {attr} outside [0,1]: {v}")


def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
