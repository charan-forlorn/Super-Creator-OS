"""SCOS Stage 2.3 — Learning Policy (rules, decoupled from the Coordinator).

Holds ALL decision rules and safety bounds so the LearningCoordinator never hard-codes
policy. The Coordinator orchestrates (apply / persist / audit / rollback) and asks this
policy two questions:

  * evaluate(style, feedback)  -> what to change (or why to reject)
  * enforce_safety(proposed)   -> is it safe; clamp into bounds

Pure, deterministic, stdlib only. Swapping policy = swapping this file; the Coordinator
is unchanged.
"""

from __future__ import annotations

import math

# ---- policy thresholds ----
QUALITY_REJECT = 0.50
RETENTION_HIGH, RETENTION_LOW = 0.80, 0.40
ENGAGEMENT_LOW = 0.50
STYLE_MATCH_LOW = 0.50

# ---- safety bounds ----
FREQ_MIN, FREQ_MAX = 100.0, 2000.0
PACING_MIN, PACING_MAX = 0.5, 2.0
RGB_MIN, RGB_MAX = 0, 255


def _is_finite_number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class LearningPolicy:
    """Deterministic, rule-based learning policy."""

    # ------------------------------------------------------------------ #
    # decision: what (if anything) to change
    # ------------------------------------------------------------------ #
    def evaluate(self, style: dict, feedback: dict) -> dict:
        """Return a decision:
            {"action": "propose"|"reject", "penalize": bool, "reason": str, "proposed": {...}}
        `penalize` tells the Coordinator whether a reject should lower confidence
        (true for quality rejects, false for "nothing to do").
        """
        quality = float(feedback.get("quality_score", 0.0))
        if quality < QUALITY_REJECT:
            return {"action": "reject", "penalize": True,
                    "reason": f"quality {quality:.3f} < {QUALITY_REJECT}", "proposed": {}}

        updates = feedback.get("derived_style_updates", {}) or {}
        proposed = self._propose(style, feedback, updates)
        if not proposed:
            return {"action": "reject", "penalize": False,
                    "reason": "no actionable update under policy", "proposed": {}}
        return {"action": "propose", "penalize": False,
                "reason": "policy applied", "proposed": proposed}

    def _propose(self, style: dict, feedback: dict, updates: dict) -> dict:
        proposed: dict = {}
        retention = float(feedback.get("retention_score", 0.0))
        engagement = float(feedback.get("engagement_score", 0.0))
        style_match = float(feedback.get("style_match_score", 0.0))

        # pacing: high retention reinforces, low retention reduces
        pacing = float(style.get("scene_pacing_profile", 1.0))
        pace_delta = float(updates.get("scene_pacing_delta", 0.0))
        if retention >= RETENTION_HIGH:
            new_pace = pacing + abs(pace_delta)
        elif retention <= RETENTION_LOW:
            new_pace = pacing - abs(pace_delta)
        else:
            new_pace = pacing
        if new_pace != pacing:
            proposed["scene_pacing_profile"] = new_pace

        # frequency: only adjust when engagement is low
        bias = float(style.get("audio_frequency_bias", 440.0))
        freq_delta = float(updates.get("audio_frequency_bias_delta", 0.0))
        if engagement < ENGAGEMENT_LOW and freq_delta != 0.0:
            proposed["audio_frequency_bias"] = bias + freq_delta

        # palette: only shift when style match is low
        hint = updates.get("palette_shift_hint") or []
        if style_match < STYLE_MATCH_LOW and any(h != 0 for h in hint):
            base = list(style.get("avg_color_palette", [128, 128, 128]))
            new_palette = list(base)
            for i in range(min(len(new_palette), len(hint))):
                if isinstance(new_palette[i], (int, float)):
                    new_palette[i] = int(round(new_palette[i] + hint[i]))
            if new_palette != base:
                proposed["avg_color_palette"] = new_palette

        return proposed

    # ------------------------------------------------------------------ #
    # safety: validity + clamping
    # ------------------------------------------------------------------ #
    def enforce_safety(self, proposed: dict) -> dict:
        """Return {"valid": bool, "reason": str|None, "clamped": [fields], "proposed": {...}}.

        Invalid (NaN/Inf/negative freq/non-int RGB) -> valid False (reject). Otherwise
        clamp freq/pacing/palette into bounds and report which fields were clamped.
        """
        out = dict(proposed)

        if "audio_frequency_bias" in out:
            v = out["audio_frequency_bias"]
            if not _is_finite_number(v):
                return {"valid": False, "reason": "audio_frequency_bias not finite",
                        "clamped": [], "proposed": proposed}
            if v < 0:
                return {"valid": False, "reason": "negative frequency",
                        "clamped": [], "proposed": proposed}
        if "scene_pacing_profile" in out:
            v = out["scene_pacing_profile"]
            if not _is_finite_number(v):
                return {"valid": False, "reason": "scene_pacing_profile not finite",
                        "clamped": [], "proposed": proposed}
        if "avg_color_palette" in out:
            pal = out["avg_color_palette"]
            if not isinstance(pal, list) or not all(isinstance(c, int) for c in pal):
                return {"valid": False, "reason": "invalid RGB (non-int)",
                        "clamped": [], "proposed": proposed}

        clamped: list[str] = []
        if "audio_frequency_bias" in out:
            c = _clamp(out["audio_frequency_bias"], FREQ_MIN, FREQ_MAX)
            if c != out["audio_frequency_bias"]:
                out["audio_frequency_bias"] = c; clamped.append("audio_frequency_bias")
        if "scene_pacing_profile" in out:
            c = _clamp(out["scene_pacing_profile"], PACING_MIN, PACING_MAX)
            if c != out["scene_pacing_profile"]:
                out["scene_pacing_profile"] = c; clamped.append("scene_pacing_profile")
        if "avg_color_palette" in out:
            pal = out["avg_color_palette"]
            new_pal = [int(_clamp(c, RGB_MIN, RGB_MAX)) for c in pal]
            if new_pal != pal:
                out["avg_color_palette"] = new_pal; clamped.append("avg_color_palette")

        return {"valid": True, "reason": None, "clamped": clamped, "proposed": out}
