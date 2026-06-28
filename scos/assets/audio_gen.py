"""Deterministic audio generator — voiceover-stub sine tone WAV.

Pure stdlib + numpy. Frequency is derived from a hash of the seed (scene_id), so
each scene gets a stable, distinct tone. Written via stdlib `wave` (16-bit PCM),
which carries no timestamps → byte-identical output for identical inputs.
"""

from __future__ import annotations

import hashlib
import wave
from pathlib import Path

import numpy as np

from scos.assets.models import AssetConfig


def _seed_freq(seed_text: str, cfg: AssetConfig) -> float:
    """Map a hash of the seed into [freq_min, freq_max] (Hz), deterministically."""
    h = hashlib.sha256(seed_text.encode("utf-8")).digest()
    frac = int.from_bytes(h[:4], "big") / 0xFFFFFFFF
    return cfg.freq_min + frac * (cfg.freq_max - cfg.freq_min)


def _samples(duration: float, freq: float, cfg: AssetConfig) -> np.ndarray:
    """Int16 mono sine of `duration` seconds with short fades at both edges."""
    n = max(1, int(round(duration * cfg.sample_rate)))
    t = np.arange(n, dtype=np.float64) / cfg.sample_rate
    wave_f = np.sin(2.0 * np.pi * freq * t)

    # Click-free fades.
    fade_n = min(n // 2, int(round(cfg.fade_s * cfg.sample_rate)))
    if fade_n > 0:
        env = np.ones(n, dtype=np.float64)
        ramp = np.linspace(0.0, 1.0, fade_n, dtype=np.float64)
        env[:fade_n] = ramp
        env[-fade_n:] = ramp[::-1]
        wave_f *= env

    # 0.9 headroom, 16-bit.
    return np.rint(wave_f * 0.9 * 32767.0).astype("<i2")


def generate_sine_wav(out_path: Path, cfg: AssetConfig, duration: float, seed_text: str) -> Path:
    """Write a deterministic mono 48 kHz WAV of `duration` seconds. Returns the path."""
    if duration <= 0:
        raise ValueError(f"audio duration must be positive, got {duration}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    freq = _seed_freq(seed_text, cfg)
    pcm = _samples(duration, freq, cfg)
    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(cfg.channels)
        w.setsampwidth(cfg.sample_width_bytes)
        w.setframerate(cfg.sample_rate)
        w.writeframes(pcm.tobytes())
    return out_path
