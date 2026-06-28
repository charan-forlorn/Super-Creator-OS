"""Deterministic visual generator — hash-driven vertical gradient PNG.

Pure stdlib + numpy (no PIL, no ffmpeg). The PNG is encoded by hand (signature +
IHDR + IDAT + IEND) so output is byte-identical for the same seed and dimensions:
`zlib.compress` is deterministic for a fixed input and level, and PNG carries no
timestamps.
"""

from __future__ import annotations

import hashlib
import struct
import zlib
from pathlib import Path

import numpy as np

from scos.assets.models import AssetConfig

_PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _seed_colors(seed_text: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    """Two distinct RGB colors deterministically derived from the seed."""
    h = hashlib.sha256(seed_text.encode("utf-8")).digest()
    top = (h[0], h[1], h[2])
    # Second color from a different slice; nudge to guarantee visible contrast.
    bot = ((h[3] + 96) % 256, (h[4] + 96) % 256, (h[5] + 96) % 256)
    return top, bot


def _gradient_rgb(width: int, height: int, seed_text: str) -> np.ndarray:
    """Build an (H, W, 3) uint8 vertical gradient between two seeded colors."""
    top, bot = _seed_colors(seed_text)
    t = np.linspace(0.0, 1.0, height, dtype=np.float64)[:, None]   # (H,1)
    top_arr = np.array(top, dtype=np.float64)
    bot_arr = np.array(bot, dtype=np.float64)
    col = top_arr[None, :] * (1.0 - t) + bot_arr[None, :] * t       # (H,3)
    col = np.rint(col).astype(np.uint8)
    return np.broadcast_to(col[:, None, :], (height, width, 3)).copy()


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def _encode_png(rgb: np.ndarray) -> bytes:
    """Encode an (H, W, 3) uint8 array to PNG bytes (8-bit RGB, filter 0)."""
    height, width, _ = rgb.shape
    # Prepend a 0 filter byte to each scanline.
    raw = np.concatenate(
        [np.zeros((height, 1), dtype=np.uint8), rgb.reshape(height, width * 3)],
        axis=1,
    ).tobytes()
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit, color type 2 (RGB)
    idat = zlib.compress(raw, 9)
    return _PNG_SIG + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


def generate_gradient_png(out_path: Path, cfg: AssetConfig, seed_text: str) -> Path:
    """Write a deterministic 1080x1920 (per cfg) gradient PNG. Returns the path."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rgb = _gradient_rgb(cfg.width, cfg.height, seed_text)
    out_path.write_bytes(_encode_png(rgb))
    return out_path
