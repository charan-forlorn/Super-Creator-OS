"""SCOS Stage 2.2 — Feedback & Scoring Engine.

Closes the SCOS loop: reads a completed render bundle (MP4 + v2 manifest + assets),
computes deterministic heuristic scores, and emits style-update deltas for a future
caller to feed back into the StyleMemoryEngine.

This engine is STANDALONE — stdlib only, no `scos.*` imports, no ffmpeg, no RNG. It
NEVER mutates the StyleMemoryEngine; it only returns an update payload. It operates on
existing outputs only (reads files, generates nothing).
"""

from __future__ import annotations

import array
import json
import math
import os
import struct
import wave
import zlib
from pathlib import Path

# Repo root: scos/analytics/feedback_engine.py -> parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[2]
_STORE_PATH = _REPO_ROOT / "scos" / "work" / "analytics" / "feedback_log.json"

# Delta bounds (documented, deterministic).
_FREQ_DELTA_MAX = 50.0
_PACING_DELTA_MAX = 0.5
_PALETTE_SHIFT_MAX = 32


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _resolve(path_str: str) -> Path:
    p = Path(path_str)
    return p if p.is_absolute() else (_REPO_ROOT / p)


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _stddev(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))


def _coeff_var(xs: list[float]) -> float:
    m = _mean(xs)
    return (_stddev(xs) / m) if m > 1e-9 else 0.0


# --------------------------------------------------------------------------- #
# real-output readers (stdlib only)
# --------------------------------------------------------------------------- #
def _png_avg_rgb(path: Path, sample_rows: int = 24) -> tuple[float, float, float]:
    """Average (R,G,B) of a SCOS PNG (8-bit RGB, filter-0 scanlines).

    Deterministic; samples evenly-spaced rows for speed. Returns mid-grey on any
    decode anomaly (robust, never raises into scoring).
    """
    try:
        data = path.read_bytes()
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            return (128.0, 128.0, 128.0)
        width, height, bit_depth, color_type = struct.unpack(">IIBB", data[16:26])
        if bit_depth != 8 or color_type != 2:
            return (128.0, 128.0, 128.0)
        # Concatenate IDAT payloads.
        idat = bytearray()
        off = 8
        while off + 8 <= len(data):
            length = struct.unpack(">I", data[off:off + 4])[0]
            tag = data[off + 4:off + 8]
            start = off + 8
            if tag == b"IDAT":
                idat += data[start:start + length]
            off = start + length + 4  # + CRC
            if tag == b"IEND":
                break
        raw = zlib.decompress(bytes(idat))
        stride = 1 + width * 3
        if len(raw) < stride * height:
            return (128.0, 128.0, 128.0)
        rows = range(0, height, max(1, height // sample_rows))
        rs = gs = bs = 0.0
        n = 0
        for r in rows:
            base = r * stride
            if raw[base] != 0:          # filter byte must be 0 for literal pixels
                continue
            # First pixel represents the row (SCOS rows are constant color).
            px = base + 1
            rs += raw[px]; gs += raw[px + 1]; bs += raw[px + 2]
            n += 1
        if n == 0:
            return (128.0, 128.0, 128.0)
        return (rs / n, gs / n, bs / n)
    except (OSError, zlib.error, struct.error, ValueError):
        return (128.0, 128.0, 128.0)


def _wav_freq(path: Path) -> float:
    """Estimate dominant frequency (Hz) via zero-crossing rate. Deterministic."""
    try:
        with wave.open(str(path), "rb") as w:
            sr = w.getframerate()
            n = w.getnframes()
            ch = w.getnchannels()
            sw = w.getsampwidth()
            frames = w.readframes(n)
        if sr <= 0 or n <= 1 or sw != 2:
            return 0.0
        samples = array.array("h")
        samples.frombytes(frames)
        if ch > 1:
            samples = samples[::ch]          # left channel
        crossings = 0
        prev = samples[0]
        for s in samples[1:]:
            if (prev < 0 <= s) or (prev > 0 >= s):
                crossings += 1
            prev = s
        duration = len(samples) / sr
        return (crossings / 2.0) / duration if duration > 0 else 0.0
    except (OSError, wave.Error, ValueError):
        return 0.0


# --------------------------------------------------------------------------- #
# engine
# --------------------------------------------------------------------------- #
class FeedbackEngine:
    """Deterministic feedback & scoring over completed SCOS render bundles."""

    def __init__(self, store_path: Path | str = _STORE_PATH) -> None:
        self.store_path = Path(store_path)

    # ---- public API --------------------------------------------------------
    def evaluate(self, run_bundle: dict) -> dict:
        run_id = run_bundle["run_id"]
        manifest = self._load_manifest(run_bundle["manifest_path"])
        self._require_mp4(run_bundle.get("mp4_path"))

        assets = run_bundle.get("assets") or manifest.get("assets") or []
        if not assets:
            raise ValueError(f"run {run_id}: no assets to evaluate")

        durations = [float(a["duration"]) for a in assets]
        freqs = [_wav_freq(_resolve(a["audio_path"])) for a in assets]
        rgbs = [_png_avg_rgb(_resolve(a["image_path"])) for a in assets]

        retention = self._retention(durations)
        engagement = self._engagement(freqs, rgbs)
        style_match = self._style_match(manifest, freqs, rgbs)
        quality = round(0.4 * retention + 0.3 * engagement + 0.3 * style_match, 6)

        scores = {
            "run_id": run_id,
            "retention_score": retention,
            "engagement_score": engagement,
            "style_match_score": style_match,
            "quality_score": quality,
        }
        content_type = (run_bundle.get("content_type")
                        or manifest.get("content_type") or "default")
        scores["derived_style_updates"] = self.to_style_update(scores, manifest, content_type)
        return scores

    def to_style_update(self, scores: dict, manifest: dict,
                        content_type: str | None = None) -> dict:
        ct = (content_type or scores.get("content_type")
              or manifest.get("content_type") or "default")
        retention = scores["retention_score"]
        engagement = scores["engagement_score"]
        style_match = scores["style_match_score"]

        # retention high -> reinforce pacing (positive); centered at 0.5.
        pacing_delta = round((retention - 0.5) * 2.0 * _PACING_DELTA_MAX, 6)
        # engagement low -> increase audio variance hint (larger as engagement drops).
        freq_delta = round((1.0 - engagement) * _FREQ_DELTA_MAX, 6)
        # style_match low -> stronger palette stabilization hint.
        shift_mag = int(round((1.0 - style_match) * _PALETTE_SHIFT_MAX))
        palette_hint = [shift_mag, shift_mag, shift_mag]

        return {
            "content_type": ct,
            "audio_frequency_bias_delta": _clamp(freq_delta, -_FREQ_DELTA_MAX, _FREQ_DELTA_MAX),
            "scene_pacing_delta": _clamp(pacing_delta, -_PACING_DELTA_MAX, _PACING_DELTA_MAX),
            "palette_shift_hint": [max(-_PALETTE_SHIFT_MAX, min(_PALETTE_SHIFT_MAX, v))
                                   for v in palette_hint],
        }

    def persist_feedback(self, result: dict) -> None:
        """Append-only upsert by run_id: unique, sorted by run_id, valid JSON."""
        log = self._load_log()
        log[result["run_id"]] = result          # upsert -> no duplicates
        ordered = [log[k] for k in sorted(log)]
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        tmp.write_text(json.dumps(ordered, sort_keys=True, indent=2, ensure_ascii=False),
                       encoding="utf-8")
        os.replace(tmp, self.store_path)

    # ---- scoring -----------------------------------------------------------
    def _retention(self, durations: list[float]) -> float:
        if not durations:
            return 0.0
        # Balanced pacing -> low coeff of variation -> higher score.
        cv = _coeff_var(durations)
        # Abrupt changes: mean abs consecutive delta normalized by mean duration.
        m = _mean(durations)
        if len(durations) > 1 and m > 1e-9:
            abrupt = _mean([abs(durations[i] - durations[i - 1])
                            for i in range(1, len(durations))]) / m
        else:
            abrupt = 0.0
        return round(_clamp(1.0 - 0.6 * cv - 0.4 * abrupt), 6)

    def _engagement(self, freqs: list[float], rgbs: list[tuple]) -> float:
        # Audio frequency diversity (normalized spread).
        freq_div = _clamp(_coeff_var([f for f in freqs if f > 0]) / 0.5)
        # Visual variation: mean RGB delta between consecutive scenes / 255.
        if len(rgbs) > 1:
            deltas = []
            for i in range(1, len(rgbs)):
                deltas.append(sum(abs(rgbs[i][c] - rgbs[i - 1][c]) for c in range(3)) / 3.0)
            visual_var = _clamp(_mean(deltas) / 255.0 * 4.0)
        else:
            visual_var = 0.0
        return round(_clamp(0.5 * freq_div + 0.5 * visual_var), 6)

    def _style_match(self, manifest: dict, freqs: list[tuple], rgbs: list[tuple]) -> float:
        # Style-aware manifest expected to be internally consistent.
        base = 0.5
        if manifest.get("style_enabled") and manifest.get("engine") == "asset_builder_v2":
            base = 0.7
        # Consistency: tighter per-scene RGB spread -> higher match.
        if len(rgbs) > 1:
            channel_cv = _mean([_coeff_var([rgb[c] for rgb in rgbs]) for c in range(3)])
            consistency = _clamp(1.0 - channel_cv)
        else:
            consistency = 1.0
        return round(_clamp(0.5 * base + 0.5 * consistency), 6)

    # ---- io helpers --------------------------------------------------------
    @staticmethod
    def _load_manifest(manifest_path: str) -> dict:
        p = _resolve(manifest_path)
        if not p.exists():
            raise ValueError(f"manifest not found: {p}")
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"manifest is not an object: {p}")
        return data

    @staticmethod
    def _require_mp4(mp4_path: str | None) -> None:
        if not mp4_path:
            raise ValueError("run_bundle missing mp4_path")
        p = _resolve(mp4_path)
        if not p.exists() or p.stat().st_size == 0:
            raise ValueError(f"render output missing/empty: {p}")

    def _load_log(self) -> dict:
        if not self.store_path.exists():
            return {}
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        if isinstance(data, list):
            return {r["run_id"]: r for r in data if isinstance(r, dict) and "run_id" in r}
        return {}
