"""narrative_engine.py — WF-1 v2: Narrative Episode Engine (story-aware highlights).

Evolves WF-1 from PEAK DETECTION to STORY EXTRACTION. Instead of returning the instant
of max saliency +/- a fixed roll, it reconstructs the narrative EPISODE around each
peak — buildup (onset) -> climax (peak) -> resolution — rejects payoff-only flashes
(Buildup Sufficiency Gate), scores narrative shape (Arc Score), and emits a structured
segment WF-2 uses to place an anticipation hook + a timed payoff callout.

ADDITIVE: reuses the v1 signal engine (highlight_engine: audio/motion/fuse). Does NOT
modify v1. New schema. ffmpeg + numpy only.

Maps directly onto the SCOS story model:  HOOK -> BUILD -> PEAK -> RESOLUTION.

CLI:
  python integrations/highlight/narrative_engine.py --video <v> --out episodes.json [--top-n 3]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from highlight_engine import (  # noqa: E402  (reuse v1 signal engine — not modified)
    HighlightConfig, extract_audio_energy, extract_motion_energy, fuse, detect_peaks,
    _ffprobe_duration,
)


@dataclass
class NarrativeConfig:
    window_s: float = 0.5
    min_separation_s: float = 5.0   # distinct climaxes must be >= this apart (NMS)
    threshold_k: float = 0.4        # peak threshold = mean + k*std (lower = more climaxes)
    valley_pct: float = 35.0        # buildup_start = trace back to this energy valley
    min_buildup_s: float = 4.0      # Buildup Sufficiency Gate: build must precede peak
    resolution_pad_s: float = 2.5   # payoff/aftermath kept after the climax
    min_clip_s: float = 12.0
    max_clip_s: float = 18.0
    hook_window_s: float = 2.0      # anticipation-hook slot at the clip start
    max_episodes: int | None = None


# ---------------------------------------------------------------------------
def _arc_score(seg: np.ndarray, peak_val: float, buildup_s: float,
               cfg: NarrativeConfig) -> tuple[int, float]:
    """Reward a RISING ramp into the peak + peak strength + buildup completeness."""
    if len(seg) >= 2:
        diffs = np.diff(seg)
        positive_frac = float((diffs > 0).mean())
        rise = float(np.clip(seg[-1] - seg[0], 0, 1))
        ramp = 0.5 * positive_frac + 0.5 * rise
    else:
        ramp = 0.0
    completeness = float(np.clip(buildup_s / cfg.min_buildup_s, 0, 1))
    arc = 0.5 * peak_val + 0.3 * ramp + 0.2 * completeness
    return int(round(100 * arc)), round(ramp, 3)


def detect_episodes(video_path: str | Path, cfg: NarrativeConfig | None = None) -> list[dict]:
    """Raw video -> story episodes. PEAK-ANCHORED: each distinct climax gets its own
    episode, with buildup traced BACK to the preceding energy valley. This is what
    keeps a late climax (e.g. the Double Kill) from being swallowed by an earlier,
    stronger peak in the same action-dense run. Pure read."""
    cfg = cfg or NarrativeConfig()
    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(path)
    hc = HighlightConfig(window_s=cfg.window_s, min_separation_s=cfg.min_separation_s,
                         threshold_k=cfg.threshold_k)
    duration = _ffprobe_duration(path)
    _, a_e = extract_audio_energy(path, hc)
    _, m_e = extract_motion_energy(path, hc)
    fused = fuse(a_e, m_e, hc)
    if len(fused) == 0:
        return []
    times = np.arange(len(fused)) * cfg.window_s
    valley = float(np.percentile(fused, cfg.valley_pct))
    max_back = int(round(cfg.max_clip_s / cfg.window_s))
    out: list[dict] = []

    for peak_i in detect_peaks(fused, times, hc):           # one episode per distinct climax
        peak_t = float(times[peak_i])
        # --- trace BACK to the valley where the rise to this climax began ---
        i = peak_i
        limit = max(0, peak_i - max_back)
        while i > limit and fused[i] > valley:
            i -= 1
        onset_t = float(times[i])
        if peak_t - onset_t < cfg.min_buildup_s:            # guarantee context even if no deep valley
            onset_t = max(0.0, peak_t - cfg.min_buildup_s)
        buildup = peak_t - onset_t

        # --- Buildup Sufficiency Gate ---
        if buildup < cfg.min_buildup_s:
            continue

        clip_end = min(duration or (peak_t + cfg.resolution_pad_s), peak_t + cfg.resolution_pad_s)
        clip_start = onset_t
        if clip_end - clip_start > cfg.max_clip_s:
            clip_start = clip_end - cfg.max_clip_s          # trim quiet buildup tail, never payoff
        if clip_end - clip_start < cfg.min_clip_s:
            clip_start = max(0.0, clip_end - cfg.min_clip_s)
        if peak_t - clip_start < cfg.min_buildup_s:
            clip_start = max(0.0, peak_t - cfg.min_buildup_s)

        onset_idx = int(round(clip_start / cfg.window_s))
        score, ramp = _arc_score(fused[onset_idx:peak_i + 1], float(fused[peak_i]), buildup, cfg)
        climax_offset = round(peak_t - clip_start, 2)
        out.append({
            "start": round(clip_start, 2),
            "end": round(clip_end, 2),
            "duration": round(clip_end - clip_start, 2),
            "buildup_start": round(clip_start, 2),
            "climax_t": round(peak_t, 2),
            "resolution_end": round(clip_end, 2),
            "climax_offset": climax_offset,                 # for WF-2 timed payoff callout
            "hook_window": {"start": round(clip_start, 2),
                            "end": round(clip_start + cfg.hook_window_s, 2)},
            "score": int(round(100 * float(fused[peak_i]))),
            "arc_score": score,
            "peak": round(peak_t, 2),
            "ramp_quality": ramp,
            "reason": "buildup -> climax payoff (audio+motion narrative arc)",
            "signals": {"peak_fused": round(float(fused[peak_i]), 3),
                        "buildup_s": round(buildup, 2)},
        })

    # detect_peaks already NMS-separates climaxes by >= min_separation_s, so each
    # episode has a DISTINCT climax. Context-clips may overlap (different payoffs) —
    # that is intended; the consumer selects which climax to cut. Rank by arc.
    out.sort(key=lambda e: -e["arc_score"])               # rank by NARRATIVE quality, not peak
    if cfg.max_episodes is not None:
        out = out[:cfg.max_episodes]
    return out


def main() -> int:
    os.environ.setdefault("PYTHONUTF8", "1")
    ap = argparse.ArgumentParser(description="WF-1 v2 Narrative Episode Engine")
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", default="episodes.json")
    ap.add_argument("--top-n", type=int, default=None)
    ap.add_argument("--min-buildup", type=float, default=4.0)
    ap.add_argument("--max-clip", type=float, default=18.0)
    a = ap.parse_args()
    cfg = NarrativeConfig(min_buildup_s=a.min_buildup, max_clip_s=a.max_clip, max_episodes=a.top_n)
    eps = detect_episodes(a.video, cfg)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(eps, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"detected {len(eps)} narrative episode(s) -> {a.out}")
    for e in eps:
        print(f"  [arc {e['arc_score']:>3} | peak {e['score']:>3}] {e['start']:>5.1f}-{e['end']:<5.1f}s "
              f"({e['duration']:.1f}s)  climax@{e['climax_t']}  buildup={e['signals']['buildup_s']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
