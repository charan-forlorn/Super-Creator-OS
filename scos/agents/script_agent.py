"""Turns a raw input prompt into a structured script brief."""

from __future__ import annotations


class ScriptAgent:
    def run(self, input_data: dict) -> dict:
        prompt = input_data["input_prompt"]
        words = prompt.strip().split()

        hook = prompt.strip().rstrip(".") + "."
        main_points = [w.lower() for w in words if len(w) > 3][:5] or ["topic"]
        tone = "energetic" if "!" in prompt else "informative"
        duration_target = max(15, min(60, 10 + 5 * len(main_points)))

        return {
            "hook": hook,
            "main_points": main_points,
            "tone": tone,
            "duration_target": duration_target,
        }
