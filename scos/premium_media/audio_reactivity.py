"""R3 real-byte audio reactivity with deterministic onset and tempo analysis."""
from __future__ import annotations
import math, struct, subprocess
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class EnergyEvent:
    time_s: float
    strength: float

@dataclass(frozen=True)
class BeatEvent:
    time_s: float
    strength: float

@dataclass(frozen=True)
class AudioReactiveAnalysis:
    duration_s: float
    sample_rate: int
    window_s: float
    rms: tuple[float, ...]
    events: tuple[EnergyEvent, ...]
    bpm: float | None = None
    tempo_confidence: float = 0.0
    beats: tuple[BeatEvent, ...] = ()

    def to_props(self):
        return {
            "duration_s": self.duration_s,
            "sample_rate": self.sample_rate,
            "window_s": self.window_s,
            "events": [e.__dict__ for e in self.events],
            "bpm": self.bpm,
            "tempo_confidence": self.tempo_confidence,
            "beats": [b.__dict__ for b in self.beats],
        }

def _decode_mono_pcm(path: str | Path, sample_rate: int = 8000) -> bytes:
    p = Path(path).resolve()
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(p), "-ac", "1", "-ar", str(sample_rate), "-f", "s16le", "-"],
        capture_output=True, timeout=180,
    )
    if proc.returncode:
        raise RuntimeError((proc.stderr or b"decode failed")[-2000:].decode(errors="replace"))
    if not proc.stdout:
        raise ValueError("audio decode produced no PCM bytes")
    return proc.stdout

def _median(values: list[float]) -> float:
    ordered = sorted(values)
    if not ordered: return 0.0
    n = len(ordered)
    mid = n // 2
    return ordered[mid] if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2

def _detect_onsets(rms: tuple[float, ...], window_s: float) -> tuple[BeatEvent, ...]:
    if len(rms) < 5: return ()
    baseline = max(_median(list(rms)), 1e-4)
    peaks: list[BeatEvent] = []
    last_idx = -10_000
    min_gap = max(2, int(0.20 / window_s))
    for i in range(1, len(rms) - 1):
        novelty = max(0.0, rms[i] - rms[i - 1])
        local_max = rms[i] >= rms[i - 1] and rms[i] > rms[i + 1]
        if not local_max or novelty <= baseline * 0.08 or rms[i] < baseline * 1.15:
            continue
        if i - last_idx < min_gap:
            if peaks and novelty > peaks[-1].strength:
                peaks[-1] = BeatEvent(i * window_s, min(1.0, novelty / max(baseline, 1e-6)))
                last_idx = i
            continue
        strength = min(1.0, max(0.0, novelty / max(baseline, 1e-6)))
        peaks.append(BeatEvent(i * window_s, strength))
        last_idx = i
    return tuple(peaks)

def _estimate_tempo(beats: tuple[BeatEvent, ...]) -> tuple[float | None, float]:
    if len(beats) < 3: return None, 0.0
    intervals = [b.time_s - a.time_s for a, b in zip(beats, beats[1:]) if 0.25 <= b.time_s - a.time_s <= 2.0]
    if not intervals: return None, 0.0
    median_interval = _median(intervals)
    if median_interval <= 0: return None, 0.0
    bpm = 60.0 / median_interval
    while bpm < 70.0: bpm *= 2.0
    while bpm > 180.0: bpm /= 2.0
    deviations = [abs((60.0 / i) - bpm) for i in intervals]
    median_dev = _median(deviations)
    confidence = max(0.0, min(1.0, 1.0 - median_dev / max(bpm, 1e-6)))
    return round(bpm, 3), round(confidence, 4)

def analyze_audio(path: str | Path, sample_rate: int = 8000, window_s: float = 0.05) -> AudioReactiveAnalysis:
    raw = _decode_mono_pcm(path, sample_rate)
    step = max(1, int(sample_rate * window_s))
    vals: list[float] = []
    for i in range(0, len(raw) - 1, step * 2):
        block = raw[i:i + step * 2]
        n = len(block) // 2
        if not n: continue
        samples = struct.unpack("<" + "h" * n, block[:n * 2])
        vals.append(math.sqrt(sum(x * x for x in samples) / (n * 32768.0) ** 2))
    rms = tuple(vals)
    baseline = _median(vals)
    floor = max(min(vals) if vals else 0.0, 0.002)
    threshold = max(floor * 1.8, baseline * 1.25, 0.008)
    events = tuple(
        EnergyEvent(i * window_s, min(1.0, v / max(threshold, 1e-6)))
        for i, v in enumerate(vals) if v > threshold
    )
    beats = _detect_onsets(rms, window_s)
    bpm, confidence = _estimate_tempo(beats)
    return AudioReactiveAnalysis(
        len(raw) / 2 / sample_rate, sample_rate, window_s, rms, events, bpm, confidence, beats
    )