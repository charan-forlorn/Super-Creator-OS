"""SCOS Stage 2 — Style Memory Engine.

Persists video "style profiles" locally and retrieves the best style per content
type, so a future AssetBuilder v2 can generate on-brand assets. Storage + retrieval
only — no ML, no external/cloud APIs, stdlib only.

Store: scos/work/memory/style_memory.json (valid JSON, deterministic ordering,
unique style_id, persists across runs).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

# Repo root: scos/memory/style_memory.py -> parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[2]
STORE_PATH = _REPO_ROOT / "scos" / "work" / "memory" / "style_memory.json"

# Style profile schema (field -> accepted python type(s)).
_FIELD_TYPES: dict[str, tuple[type, ...]] = {
    "style_id": (str,),
    "content_type": (str,),
    "avg_color_palette": (list,),
    "audio_frequency_bias": (int, float),
    "scene_pacing_profile": (int, float),
    "retention_score": (int, float),
    "created_at": (int,),
}
REQUIRED_FIELDS = tuple(_FIELD_TYPES)

# Defaults for a synthesized fallback style.
DEFAULT_PALETTE = [128, 128, 128]
DEFAULT_FREQ = 440.0
DEFAULT_PACING = 1.0
DEFAULT_RETENTION = 0.5


def _now() -> int:
    """Integer wall-clock timestamp (no float drift)."""
    return int(time.time())


class StyleMemoryEngine:
    """Local, deterministic store of style profiles keyed by unique ``style_id``."""

    def __init__(self, store_path: Path | str = STORE_PATH) -> None:
        self.store_path = Path(store_path)
        self._styles: list[dict] = self._load()

    # ---- persistence -------------------------------------------------------
    def _load(self) -> list[dict]:
        if not self.store_path.exists():
            return []
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        return data if isinstance(data, list) else []

    def _save(self) -> None:
        # Deterministic on-disk order: sorted by style_id, stable key order.
        ordered = sorted(self._styles, key=lambda s: s["style_id"])
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(ordered, sort_keys=True, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp, self.store_path)  # atomic on same filesystem

    # ---- validation --------------------------------------------------------
    @staticmethod
    def _validate(profile: dict) -> None:
        missing = [f for f in REQUIRED_FIELDS if f not in profile]
        if missing:
            raise ValueError(f"style profile missing fields: {missing}")
        for field, types in _FIELD_TYPES.items():
            # bool is a subclass of int — reject it for numeric fields explicitly.
            if isinstance(profile[field], bool) or not isinstance(profile[field], types):
                raise ValueError(
                    f"field '{field}' must be {', '.join(t.__name__ for t in types)}, "
                    f"got {type(profile[field]).__name__}"
                )

    def _index_of(self, style_id: str) -> int:
        for i, s in enumerate(self._styles):
            if s["style_id"] == style_id:
                return i
        return -1

    # ---- public API --------------------------------------------------------
    def record_video_metrics(self, style_profile: dict) -> None:
        """Append a new style profile. Rejects duplicate ``style_id``."""
        profile = dict(style_profile)
        profile.setdefault("created_at", _now())
        self._validate(profile)
        if self._index_of(profile["style_id"]) != -1:
            raise ValueError(f"duplicate style_id: {profile['style_id']!r}")
        # Normalize created_at to int (no float drift).
        profile["created_at"] = int(profile["created_at"])
        self._styles.append(profile)
        self._save()

    def get_style(self, content_type: str) -> dict:
        """Return the best style for ``content_type`` (highest retention_score,
        tie-break lowest style_id), or a synthesized default if none match."""
        matches = [s for s in self._styles if s.get("content_type") == content_type]
        if matches:
            best = max(matches, key=lambda s: (s["retention_score"],
                                               _neg_key(s["style_id"])))
            return dict(best)
        return {
            "style_id": "default",
            "content_type": content_type,
            "avg_color_palette": list(DEFAULT_PALETTE),
            "audio_frequency_bias": DEFAULT_FREQ,
            "scene_pacing_profile": DEFAULT_PACING,
            "retention_score": DEFAULT_RETENTION,
            "created_at": _now(),
        }

    def update_style(self, style_id: str, updates: dict) -> None:
        """Partial update of an existing style; preserves unmodified fields."""
        idx = self._index_of(style_id)
        if idx == -1:
            raise ValueError(f"unknown style_id: {style_id!r}")
        merged = dict(self._styles[idx])
        merged.update(updates)
        merged["style_id"] = style_id  # identity is immutable
        if "created_at" in merged:
            merged["created_at"] = int(merged["created_at"])
        self._validate(merged)
        self._styles[idx] = merged
        self._save()

    def list_styles(self) -> list:
        """All styles, deterministically sorted by ``style_id`` (copies)."""
        return [dict(s) for s in sorted(self._styles, key=lambda s: s["style_id"])]


def _neg_key(style_id: str):
    """Sort helper: make 'lowest style_id wins' a tie-breaker inside max().

    Returns a value that is LARGER for a smaller style_id, so that within
    max(key=(retention, _neg_key(id))) the smallest id is preferred on ties.
    """
    # Compare by inverted code points; pad-free reverse ordering via a tuple of
    # negated ordinals keeps it total and deterministic.
    return tuple(-ord(c) for c in style_id)
