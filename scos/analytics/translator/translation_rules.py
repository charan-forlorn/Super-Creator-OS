"""SCOS Stage 3.2 — translation rules (policy).

Owns EVERY analytics→learning-signal conversion formula. Pure, deterministic,
stateless: no randomness, no timestamps, no I/O. Changing translation behavior means
editing ONLY this file; the orchestrator (analytics_translator.py) is unaffected.

All scores are fractions in [0, 1]; derived deltas are bounded to the certified-core
ranges so the produced payload behaves predictably in LearningPolicy/Coordinator.
"""

from __future__ import annotations

# ---- score scaling (deterministic constants) ----
CTR_FULL = 0.10            # 10% CTR  -> ctr_score 1.0
ENGAGEMENT_FULL = 0.10     # 10% (likes+comments+shares)/views -> engagement 1.0

# ---- derived-signal bounds (match certified core) ----
FREQ_DELTA_MAX = 50.0
PACING_DELTA_MAX = 0.5
PALETTE_SHIFT_MAX = 32

_ROUND = 6


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


class TranslationRules:
    """Deterministic conversion policy. Inject a subclass to change behavior."""

    # ------------------------------------------------------------------ #
    # aggregation
    # ------------------------------------------------------------------ #
    def aggregate(self, records: list) -> dict:
        """Reduce a batch of normalized records to view-weighted rate metrics."""
        total_views = sum(r.views for r in records)
        if total_views > 0:
            retention = sum(r.retention_rate * r.views for r in records) / total_views
            ctr = sum(r.ctr * r.views for r in records) / total_views
            engagements = sum((r.likes + r.comments + r.shares) for r in records)
            engagement_rate = engagements / total_views
        else:
            n = len(records)
            retention = sum(r.retention_rate for r in records) / n
            ctr = sum(r.ctr for r in records) / n
            engagement_rate = 0.0
        return {"retention": retention, "ctr": ctr,
                "engagement_rate": engagement_rate, "views": total_views}

    # ------------------------------------------------------------------ #
    # scores (each in [0,1])
    # ------------------------------------------------------------------ #
    def retention_score(self, agg: dict) -> float:
        return round(_clamp(agg["retention"]), _ROUND)

    def ctr_score(self, agg: dict) -> float:
        return round(_clamp(agg["ctr"] / CTR_FULL), _ROUND)

    def engagement_score(self, agg: dict) -> float:
        return round(_clamp(agg["engagement_rate"] / ENGAGEMENT_FULL), _ROUND)

    def quality_score(self, agg: dict) -> float:
        q = (0.4 * self.retention_score(agg)
             + 0.3 * self.ctr_score(agg)
             + 0.3 * self.engagement_score(agg))
        return round(_clamp(q), _ROUND)

    def style_match_score(self, agg: dict) -> float:
        r, c, e = self.retention_score(agg), self.ctr_score(agg), self.engagement_score(agg)
        mean3 = (r + c + e) / 3.0
        spread = max(r, c, e) - min(r, c, e)          # alignment of the three signals
        return round(_clamp(0.6 * mean3 + 0.4 * (1.0 - spread)), _ROUND)

    # ------------------------------------------------------------------ #
    # derived style-update recommendations (bounded; never applied here)
    # ------------------------------------------------------------------ #
    def derived_style_updates(self, retention: float, engagement: float,
                              style_match: float) -> dict:
        # high retention -> positive pacing; centered at 0.5
        pacing = _clamp((retention - 0.5) * 2.0 * PACING_DELTA_MAX,
                        -PACING_DELTA_MAX, PACING_DELTA_MAX)
        # low engagement -> positive audio-frequency push
        freq = _clamp((1.0 - engagement) * FREQ_DELTA_MAX, -FREQ_DELTA_MAX, FREQ_DELTA_MAX)
        # low style match -> stronger palette shift hint
        mag = int(round((1.0 - style_match) * PALETTE_SHIFT_MAX))
        mag = max(-PALETTE_SHIFT_MAX, min(PALETTE_SHIFT_MAX, mag))
        return {
            "audio_frequency_bias_delta": round(freq, _ROUND),
            "scene_pacing_delta": round(pacing, _ROUND),
            "palette_shift_hint": [mag, mag, mag],
        }

    # ------------------------------------------------------------------ #
    # content type resolution
    # ------------------------------------------------------------------ #
    def content_type(self, records: list, override: str | None) -> str:
        if override:
            return override
        meta_ct = getattr(records[0], "metadata", {}) or {}
        return meta_ct.get("content_type") or getattr(records[0], "platform", "default") or "default"
