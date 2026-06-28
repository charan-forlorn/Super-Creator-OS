"""SCOS Stage 2 — AssetBuilder v2 (style-aware deterministic generator).

Upgrades v1 from fixed gradient + seed-only tone to STYLE-CONDITIONED assets: for
each scene it queries the Stage-2 StyleMemoryEngine (read-only) and derives the PNG
colors + WAV frequency/envelope from the retrieved style profile — while keeping
v1's run_id rule, output paths, and asset contract so EditComposer + the FFmpeg
engine consume it unchanged.

Determinism: every adaptive choice is a pure function of the style profile and a
sha256 of (scene_id, topic). No RNG, no FFmpeg, no external/cloud APIs.

Nothing here modifies v1, StyleMemoryEngine, EditComposer, or the engine — all are
imported read-only or untouched.
"""

from __future__ import annotations

import hashlib
import json
import logging
import wave
from pathlib import Path

import numpy as np

# Read-only reuse of v1 + Stage-2 building blocks (never modified):
from scos.assets.asset_builder import _derive_run_id          # run_id compatibility
from scos.assets.image_gen import _encode_png                 # proven deterministic PNG encoder
from scos.assets.models import Asset, AssetConfig
from scos.memory.style_memory import StyleMemoryEngine

log = logging.getLogger("scos.assets.asset_builder_v2")

# Repo root: scos/assets/asset_builder_v2.py -> parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ASSETS_DIR = _REPO_ROOT / "scos" / "work" / "assets"

_ENGINE_NAME = "asset_builder_v2"
_PACING_BASELINE = 1.0      # pacing at which envelope modulation depth is ~0
_FREQ_OFFSET_HZ = 40.0      # +/- deterministic per-scene frequency jitter


# --------------------------------------------------------------------------- #
# deterministic derivation helpers (sha256 only)
# --------------------------------------------------------------------------- #
def _digest(*parts: str) -> bytes:
    return hashlib.sha256("|".join(parts).encode("utf-8")).digest()


def _palette_to_rgb(palette) -> np.ndarray:
    """Reduce a style palette to a single base RGB (float64, 0..255).

    Accepts a flat [r,g,b] or a list of [r,g,b] triples (averaged). Hex strings
    ('#rrggbb' / 'rrggbb') are supported too. Falls back to mid-grey.
    """
    try:
        if palette and isinstance(palette[0], (list, tuple)):
            arr = np.array([[float(c) for c in trip[:3]] for trip in palette], dtype=np.float64)
            base = arr.mean(axis=0)
        elif palette and isinstance(palette[0], str):
            triples = []
            for h in palette:
                h = h.lstrip("#")
                triples.append([int(h[i:i + 2], 16) for i in (0, 2, 4)])
            base = np.array(triples, dtype=np.float64).mean(axis=0)
        else:
            base = np.array([float(c) for c in palette[:3]], dtype=np.float64)
        if base.shape != (3,):
            raise ValueError
    except (ValueError, IndexError, TypeError):
        base = np.array([128.0, 128.0, 128.0])
    return np.clip(base, 0.0, 255.0)


def _clip_rgb(arr: np.ndarray) -> tuple[int, int, int]:
    a = np.clip(np.rint(arr), 0, 255).astype(np.uint8)
    return int(a[0]), int(a[1]), int(a[2])


# --------------------------------------------------------------------------- #
# adaptive generators
# --------------------------------------------------------------------------- #
def _adaptive_gradient_png(out_path: Path, cfg: AssetConfig, style: dict,
                           scene_id: str, topic: str) -> None:
    """Style-conditioned vertical gradient, encoded with v1's PNG encoder."""
    base = _palette_to_rgb(style.get("avg_color_palette", [128, 128, 128]))
    var = _digest(scene_id, topic)
    pacing = float(style.get("scene_pacing_profile", _PACING_BASELINE))

    # color_a: base nudged by a small signed offset (var[0:3] -> [-16, +15]).
    off_a = (np.frombuffer(var[0:3], dtype=np.uint8).astype(np.float64) % 32) - 16.0
    color_a = _clip_rgb(base + off_a)

    # color_b: base shifted by (var[3:6]-128) scaled by pacing influence.
    pacing_factor = 0.25 * pacing                      # baseline pacing 1.0 -> 0.25
    off_b = (np.frombuffer(var[3:6], dtype=np.uint8).astype(np.float64) - 128.0) * pacing_factor
    color_b = _clip_rgb(base + off_b)

    h, w = cfg.height, cfg.width
    t = np.linspace(0.0, 1.0, h, dtype=np.float64)[:, None]            # (H,1)
    col = (np.array(color_a, dtype=np.float64)[None, :] * (1.0 - t)
           + np.array(color_b, dtype=np.float64)[None, :] * t)        # (H,3)
    col = np.rint(col).astype(np.uint8)
    rgb = np.broadcast_to(col[:, None, :], (h, w, 3)).copy()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(_encode_png(rgb))


def _adaptive_sine_wav(out_path: Path, cfg: AssetConfig, style: dict,
                       duration: float, scene_id: str) -> None:
    """Style-conditioned tone: freq from style bias + per-scene offset, with a
    pacing-driven amplitude envelope. Fades preserved. 48 kHz mono int16."""
    if duration <= 0:
        raise ValueError(f"audio duration must be positive, got {duration}")

    bias = float(style.get("audio_frequency_bias", 440.0))
    pacing = float(style.get("scene_pacing_profile", _PACING_BASELINE))

    # Deterministic +/- frequency offset from the scene id.
    d = _digest(scene_id)
    frac = int.from_bytes(d[:4], "big") / 0xFFFFFFFF          # 0..1
    freq = max(20.0, bias + (frac * 2.0 - 1.0) * _FREQ_OFFSET_HZ)

    n = max(1, int(round(duration * cfg.sample_rate)))
    t = np.arange(n, dtype=np.float64) / cfg.sample_rate
    sig = np.sin(2.0 * np.pi * freq * t)

    # Pacing envelope: slow amplitude modulation, depth grows with pacing.
    depth = float(np.clip(0.35 * (pacing - _PACING_BASELINE), -0.9, 0.9))
    if abs(depth) > 1e-6:
        mod_rate = 2.0                                        # Hz, fixed (deterministic)
        sig *= (1.0 - depth) + depth * 0.5 * (1.0 + np.sin(2.0 * np.pi * mod_rate * t))

    # Click-free fades (preserved from v1 behavior).
    fade_n = min(n // 2, int(round(cfg.fade_s * cfg.sample_rate)))
    if fade_n > 0:
        ramp = np.linspace(0.0, 1.0, fade_n, dtype=np.float64)
        sig[:fade_n] *= ramp
        sig[-fade_n:] *= ramp[::-1]

    pcm = np.rint(np.clip(sig, -1.0, 1.0) * 0.9 * 32767.0).astype("<i2")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as wv:
        wv.setnchannels(cfg.channels)
        wv.setsampwidth(cfg.sample_width_bytes)
        wv.setframerate(cfg.sample_rate)
        wv.writeframes(pcm.tobytes())


# --------------------------------------------------------------------------- #
# builder
# --------------------------------------------------------------------------- #
class AssetBuilderV2:
    """Style-aware deterministic asset generator (Stage 2)."""

    def __init__(self, style_engine: StyleMemoryEngine | None = None,
                 config: AssetConfig | None = None) -> None:
        self.style_engine = style_engine or StyleMemoryEngine()
        self.cfg = config or AssetConfig()

    def run(self, scene_plan: dict, run_id: str | None = None) -> dict:
        scenes = scene_plan.get("scenes") or []
        if not scenes:
            raise ValueError("scene_plan has no scenes")

        run_id = run_id or _derive_run_id(scene_plan)     # identical to v1
        out_dir = _ASSETS_DIR / run_id
        out_dir.mkdir(parents=True, exist_ok=True)

        assets: list[Asset] = []
        for scene in scenes:
            scene_id = scene["scene_id"]
            topic = scene.get("topic") or scene_id
            duration = round(float(scene["end"]) - float(scene["start"]), 3)
            if duration <= 0:
                raise ValueError(f"scene {scene_id}: non-positive duration {duration}")

            style = self.style_engine.get_style(topic)     # read-only
            image_path = out_dir / f"{scene_id}.png"
            audio_path = out_dir / f"{scene_id}.wav"
            _adaptive_gradient_png(image_path, self.cfg, style, scene_id, topic)
            _adaptive_sine_wav(audio_path, self.cfg, style, duration, scene_id)

            log.info("scene %s style=%s -> %s + %s (%.3fs)", scene_id,
                     style.get("style_id"), image_path.name, audio_path.name, duration)
            assets.append(Asset(scene_id, image_path, audio_path, duration))

        manifest_path = out_dir / "manifest.json"
        self._write_manifest(run_id, assets, manifest_path)

        return {
            "run_id": run_id,
            "assets": [a.to_dict(relative_to=_REPO_ROOT) for a in assets],
            "manifest_path": manifest_path.resolve().relative_to(_REPO_ROOT).as_posix(),
        }

    def _write_manifest(self, run_id: str, assets: list[Asset], manifest_path: Path) -> None:
        ordered = sorted((a.to_dict(relative_to=_REPO_ROOT) for a in assets),
                         key=lambda a: a["scene_id"])
        manifest = {
            "run_id": run_id,
            "engine": _ENGINE_NAME,
            "style_enabled": True,
            "assets": ordered,
        }
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False),
            encoding="utf-8")
        log.info("manifest -> %s (%d assets)", manifest_path, len(ordered))
