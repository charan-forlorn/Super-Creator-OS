"""highlight_engine.py — WF-1 Auto Highlight Detection Engine (offline, deterministic).

Transforms a raw video into highlight_candidates.json WITHOUT human intervention,
by fusing offline signals (audio RMS energy + visual motion energy + onset novelty),
detecting peaks, and expanding them into scored candidate segments.

No paid APIs, no network, no ML weights — stdlib + ffmpeg + numpy only (deps the
project already declares). This generalizes the project's own documented method
("RMS-per-second peak = kill/teamfight") into a multi-signal, normalized fusion.

CHALLENGED ASSUMPTIONS (honest design, no placeholder logic):
  - "commentator excitement / crowd": raw gameplay has game SFX + the kill-announcer
    voice line, not commentary — both are captured by audio ENERGY + ONSET.
  - "kill banners / score changes / UI text": reliable offline detection needs OCR or
    per-game templates. That is the pluggable `VisualEventDetector` interface here,
    NOT faked. Semantic labels (e.g. "double kill") are emitted ONLY when a real
    visual detector is supplied; otherwise reasons are signal-grounded and honest.

ADDITIVE: new module + new output file. Touches no moat asset, no schema, no core.

CLI:
  python integrations/highlight/highlight_engine.py --video <path> \
      --out highlight_candidates.json [--top-n 5] [--window 0.5] [--pre-roll 6] [--post-roll 3]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Protocol

import numpy as np


# ===========================================================================
# Config
# ===========================================================================
@dataclass
class HighlightConfig:
    window_s: float = 0.5           # analysis window (timeline resolution)
    audio_sr: int = 16000           # mono PCM sample rate for energy
    motion_fps: int = 8             # decode fps for motion energy
    motion_size: int = 128          # downscaled square for motion (cheap + smooth)
    pre_roll_s: float = 6.0         # build-up captured before a peak
    post_roll_s: float = 3.0        # payoff captured after a peak
    threshold_k: float = 1.0        # peak threshold = mean + k*std of fused signal
    min_separation_s: float = 6.0   # non-max suppression spacing between peaks
    w_audio: float = 0.45           # fusion weights (sum need not be 1; normalized after)
    w_motion: float = 0.35
    w_onset: float = 0.20
    max_candidates: int | None = None


# ===========================================================================
# Pluggable visual-event detector interface (REAL interface, not faked)
# ===========================================================================
class VisualEventDetector(Protocol):
    """Returns semantic UI events as list of {"t": float, "label": str, "weight": float}.

    A production backend (OCR via tesseract/easyocr, or per-game template matching)
    implements this to label kill banners / score changes / objectives. Plug it into
    detect_highlights(visual_detector=...). Until then NullVisualDetector is used and
    candidate reasons stay signal-grounded (no fabricated semantics)."""
    def detect(self, video_path: Path, cfg: HighlightConfig) -> list[dict]: ...


class NullVisualDetector:
    """Default: no semantic events. Honest no-op — the engine still runs fully on
    audio+motion fusion; it simply omits game-specific labels it cannot verify."""
    def detect(self, video_path: Path, cfg: HighlightConfig) -> list[dict]:
        return []


# ===========================================================================
# Signal extraction (real, deterministic, ffmpeg-backed)
# ===========================================================================
def _ffprobe_duration(path: Path) -> float:
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True)
    try:
        return float(p.stdout.strip())
    except (ValueError, AttributeError):
        return 0.0


def extract_audio_energy(path: Path, cfg: HighlightConfig) -> tuple[np.ndarray, np.ndarray]:
    """Per-window RMS energy of the audio track (0 if no audio). Deterministic."""
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(cfg.audio_sr),
         "-f", "s16le", "-"], capture_output=True)
    buf = p.stdout
    if not buf:
        return np.array([]), np.array([])
    samples = np.frombuffer(buf, np.int16).astype(np.float32) / 32768.0
    hop = int(cfg.audio_sr * cfg.window_s)
    n = len(samples) // hop
    if n < 1:
        return np.array([]), np.array([])
    frames = samples[:n * hop].reshape(n, hop)
    rms = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-9)
    times = np.arange(n) * cfg.window_s
    return times, rms


def extract_motion_energy(path: Path, cfg: HighlightConfig) -> tuple[np.ndarray, np.ndarray]:
    """Per-window visual motion energy (mean abs frame-diff at low res). Captures
    combat density, rapid camera movement, scene energy — works for hard cuts AND
    smooth animation (no scene-cut dependency)."""
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-vf",
         f"scale={cfg.motion_size}:{cfg.motion_size},fps={cfg.motion_fps},format=gray",
         "-f", "rawvideo", "-"], capture_output=True)
    buf = p.stdout
    fr = cfg.motion_size ** 2
    n = len(buf) // fr
    if n < 2:
        return np.array([]), np.array([])
    arr = np.frombuffer(buf[:n * fr], np.uint8).reshape(n, fr).astype(np.float32)
    diff = np.abs(np.diff(arr, axis=0)).mean(axis=1) / 255.0      # per-frame, len n-1
    per_win = max(1, int(round(cfg.window_s * cfg.motion_fps)))
    m = len(diff) // per_win
    if m < 1:
        return np.array([]), np.array([])
    win = diff[:m * per_win].reshape(m, per_win).mean(axis=1)
    times = np.arange(m) * cfg.window_s
    return times, win


# ===========================================================================
# Fusion math (pure functions — unit-tested without any asset)
# ===========================================================================
def norm01(x: np.ndarray) -> np.ndarray:
    """Robust 0..1 scaling via 5th/95th percentile (outlier-resistant)."""
    if len(x) == 0:
        return x
    lo, hi = np.percentile(x, 5), np.percentile(x, 95)
    if hi - lo < 1e-9:
        return np.zeros_like(x)
    return np.clip((x - lo) / (hi - lo), 0.0, 1.0)


def onset(x: np.ndarray) -> np.ndarray:
    """Positive derivative — the ONSET of action (energy rising = event start)."""
    if len(x) == 0:
        return x
    d = np.diff(x, prepend=x[:1])
    return np.clip(d, 0.0, None)


def _align(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n = min(len(a), len(b))
    return a[:n], b[:n]


def fuse(audio: np.ndarray, motion: np.ndarray, cfg: HighlightConfig) -> np.ndarray:
    """Weighted fusion of normalized energy + onset into one 0..1 saliency curve."""
    if len(audio) == 0 and len(motion) == 0:
        return np.array([])
    if len(audio) == 0:
        audio = np.zeros_like(motion)
    if len(motion) == 0:
        motion = np.zeros_like(audio)
    audio, motion = _align(audio, motion)
    na, nm = norm01(audio), norm01(motion)
    on = 0.5 * (norm01(onset(audio)) + norm01(onset(motion)))
    w = np.array([cfg.w_audio, cfg.w_motion, cfg.w_onset], dtype=np.float32)
    w = w / (w.sum() + 1e-9)
    fused = w[0] * na + w[1] * nm + w[2] * on
    return norm01(fused)


def detect_peaks(fused: np.ndarray, times: np.ndarray, cfg: HighlightConfig) -> list[int]:
    """Adaptive local maxima above mean+k*std, with non-max suppression by spacing."""
    if len(fused) == 0:
        return []
    thr = float(fused.mean() + cfg.threshold_k * fused.std())
    local: list[int] = []
    for i in range(len(fused)):
        if fused[i] < thr:
            continue
        lo, hi = max(0, i - 1), min(len(fused), i + 2)
        if fused[i] >= fused[lo:hi].max():
            local.append(i)
    local.sort(key=lambda i: -fused[i])          # strongest first
    chosen: list[int] = []
    for i in local:
        if all(abs(times[i] - times[j]) >= cfg.min_separation_s for j in chosen):
            chosen.append(i)
    return sorted(chosen)


def _reason(na_i: float, nm_i: float, visual_label: str | None) -> str:
    parts = []
    if visual_label:
        parts.append(visual_label)
    if na_i >= 0.6 and nm_i >= 0.6:
        parts.append("audio+motion energy spike (likely teamfight/combat)")
    elif na_i >= 0.6:
        parts.append("audio energy spike (likely kill / announcer cue)")
    elif nm_i >= 0.6:
        parts.append("motion spike (rapid action / camera movement)")
    else:
        parts.append("elevated combined activity")
    return "; ".join(parts)


def _merge_overlaps(cands: list[dict]) -> list[dict]:
    """Merge candidates whose [start,end] overlap; keep the higher score + union span."""
    if not cands:
        return []
    s = sorted(cands, key=lambda c: c["start"])
    out = [dict(s[0])]
    for c in s[1:]:
        last = out[-1]
        if c["start"] <= last["end"]:
            last["end"] = max(last["end"], c["end"])
            if c["score"] > last["score"]:
                last["score"], last["peak"], last["reason"] = c["score"], c["peak"], c["reason"]
                last["signals"] = c["signals"]
        else:
            out.append(dict(c))
    return out


def peaks_to_candidates(peaks: list[int], fused: np.ndarray, times: np.ndarray,
                        na: np.ndarray, nm: np.ndarray, cfg: HighlightConfig,
                        duration: float, visual_events: list[dict]) -> list[dict]:
    if not peaks:
        return []
    out: list[dict] = []
    for i in peaks:
        t = float(times[i])
        start = max(0.0, t - cfg.pre_roll_s)
        end = min(duration or (t + cfg.post_roll_s), t + cfg.post_roll_s)
        # absolute saliency on the normalized fused curve (0..1 -> 0..100), so scores
        # DISCRIMINATE between peaks instead of all collapsing to ~100.
        score = int(round(100 * float(fused[i])))
        vlabel = next((e["label"] for e in visual_events
                       if abs(e.get("t", -1e9) - t) <= cfg.window_s * 2), None)
        out.append({
            "start": round(start, 2),
            "end": round(end, 2),
            "score": score,
            "peak": round(t, 2),
            "reason": _reason(float(na[i]), float(nm[i]), vlabel),
            "signals": {"audio": round(float(na[i]), 3), "motion": round(float(nm[i]), 3),
                        "fused": round(float(fused[i]), 3)},
        })
    out = _merge_overlaps(out)
    return sorted(out, key=lambda c: -c["score"])


# ===========================================================================
# Orchestration
# ===========================================================================
def detect_highlights(video_path: str | Path, cfg: HighlightConfig | None = None,
                      visual_detector: VisualEventDetector | None = None) -> list[dict]:
    """Raw video -> scored highlight candidates. Pure read; writes nothing."""
    cfg = cfg or HighlightConfig()
    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(f"video not found: {path}")
    duration = _ffprobe_duration(path)
    _, a_energy = extract_audio_energy(path, cfg)
    _, m_energy = extract_motion_energy(path, cfg)
    fused = fuse(a_energy, m_energy, cfg)
    if len(fused) == 0:
        return []
    times = np.arange(len(fused)) * cfg.window_s
    a_al, m_al = _align(a_energy if len(a_energy) else np.zeros_like(fused),
                        m_energy if len(m_energy) else np.zeros_like(fused))
    na, nm = norm01(a_al)[:len(fused)], norm01(m_al)[:len(fused)]
    if len(na) < len(fused):
        na = np.pad(na, (0, len(fused) - len(na)))
    if len(nm) < len(fused):
        nm = np.pad(nm, (0, len(fused) - len(nm)))
    detector = visual_detector or NullVisualDetector()
    visual_events = detector.detect(path, cfg)
    peaks = detect_peaks(fused, times, cfg)
    cands = peaks_to_candidates(peaks, fused, times, na, nm, cfg, duration, visual_events)
    if cfg.max_candidates is not None:
        cands = cands[:cfg.max_candidates]
    return cands


def main() -> int:
    import os
    os.environ.setdefault("PYTHONUTF8", "1")
    ap = argparse.ArgumentParser(description="WF-1 Auto Highlight Detection Engine")
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", default="highlight_candidates.json")
    ap.add_argument("--top-n", type=int, default=None)
    ap.add_argument("--window", type=float, default=0.5)
    ap.add_argument("--pre-roll", type=float, default=6.0)
    ap.add_argument("--post-roll", type=float, default=3.0)
    ap.add_argument("--threshold-k", type=float, default=1.0)
    ap.add_argument("--min-separation", type=float, default=6.0)
    a = ap.parse_args()
    cfg = HighlightConfig(window_s=a.window, pre_roll_s=a.pre_roll, post_roll_s=a.post_roll,
                          threshold_k=a.threshold_k, min_separation_s=a.min_separation,
                          max_candidates=a.top_n)
    cands = detect_highlights(a.video, cfg)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(cands, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"detected {len(cands)} highlight candidate(s) -> {a.out}")
    for c in cands:
        print(f"  [{c['score']:>3}] {c['start']:>6.1f}-{c['end']:<6.1f}s  peak={c['peak']:<5}  {c['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
