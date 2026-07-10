"""SCOS <-> Hermes Video Studio (HVS) deterministic schema-contract models.

Stage 2 cross-project integration: a *versioned, pure-translation* contract
between a SCOS edit timeline / render request and the HVS project/timeline
payload shape.

This module is the ONLY place that defines the canonical SCOS-side timeline
representation consumed by Stage 2. SCOS has no pre-existing edit-timeline /
scene / caption / asset-reference / render-preset model (the only timeline-ish
primitives in the repo are ``scos.render.base.RenderRequest`` / ``RenderClip``,
which carry filesystem paths + a float duration only, and ``ScenePlanner``'s
plain-dict output). Rather than invent a *duplicate* of an existing model,
Stage 2 introduces the dedicated, contract-scoped models below. They are
deliberately small and map 1:1 onto the observed HVS schema semantics.

Design rules (mirrors the SCOS Control Center convention):

* frozen dataclasses; collections are immutable tuples (no mutable dict/list is
  ever exposed from a model instance).
* ``to_dict()`` uses explicit key order and serializes tuples as lists.
* deterministic, stdlib-only hashing (sha256 hexdigest[:16]) — no clock, no
  random, no uuid, no network, no file I/O, no subprocess, no HVS import.
* canonical internal timing unit is **integer milliseconds**; the HVS boundary
  uses seconds rounded to 3 decimals (``round(x, 3)``), mirroring
  ``hvs.core.timeline_models.build_scene``.
* HVS audit-only fields (``created_at``, ``source_agent``, ``stage``,
  ``status``, ``artifact_id``) are NOT part of the deterministic identity and
  are intentionally excluded from the hash (matching HVS ``util.deterministic_hash``).

Local-first, deterministic, stdlib-only. No clock, no random, no uuid.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Tuple


# --- Contract identity -------------------------------------------------------
SCOS_HVS_TIMELINE_CONTRACT_NAME = "scos-hvs.timeline"
SCOS_HVS_TIMELINE_CONTRACT_VERSION = "1"
SCOS_HVS_TIMELINE_CONTRACT_ID = (
    f"{SCOS_HVS_TIMELINE_CONTRACT_NAME}.v{SCOS_HVS_TIMELINE_CONTRACT_VERSION}"
)

# --- HVS schema contract constants (read-only; from hvs/schemas/*.json) --------
HVS_SCHEMA_VERSION = "2.0.0"
HVS_TIMELINE_STAGE = 2
HVS_STATUS_PLANNED = "planned"
HVS_SOURCE_AGENT = "storyboard_agent"

# hvs/schemas/timeline.schema.json -> resolution enum
HVS_RESOLUTION_VALUES: Tuple[str, ...] = ("1080x1920", "1920x1080", "1080x1080")
# hvs/schemas/timeline.schema.json -> fps enum
HVS_FPS_VALUES: Tuple[int, ...] = (24, 25, 30, 60)
# hvs/schemas/timeline.schema.json -> scene_count integer min 3, max 6.
# NOTE: hvs/core/timeline_models.py sets MIN_SCENES=3 / MAX_SCENES=10, but the
# authoritative read-only *schema* contract bounds scene_count to 3..6. Stage 2
# enforces the schema contract (3..6) and documents the discrepancy.
HVS_SCENE_COUNT_MIN = 3
HVS_SCENE_COUNT_MAX = 6

# SCOS render-preset vocabulary introduced by Stage 2 (no prior SCOS preset
# model existed). Each supported SCOS preset maps to exactly one HVS preset.
SCOS_RENDER_PRESETS: Tuple[str, ...] = ("draft", "standard", "fast")
HVS_PRESET_VALUES: Tuple[str, ...] = ("draft", "standard", "fast", "high_quality")
SCOS_PRESET_TO_HVS: dict[str, str] = {
    "draft": "draft",
    "standard": "standard",
    "fast": "fast",
}
HVS_PRESET_TO_SCOS: dict[str, str] = {v: k for k, v in SCOS_PRESET_TO_HVS.items()}

# Reserved extension-metadata block key carried inside the HVS payload. It holds
# SCOS fields that have no natural HVS location (request/run ids, preset,
# caption timing, asset identity, contract version, metadata). The HVS schemas
# do not set ``additionalProperties: false``, so this block is tolerated by the
# read-only schema validator while remaining clearly namespaced.
X_SCOS_KEY = "x_scos"

# Canonical internal timing unit for deterministic identity input.
CANONICAL_TIMING_UNIT = "milliseconds"

# Stage 2 does NOT invent a timestamp. This sentinel marks the ``created_at``
# slot (required by the HVS schema) as intentionally-unfilled so the mapping
# stays deterministic. Real ``created_at`` fill-in is an explicit Stage 3
# (production) concern, never Stage 2. The value is excluded from the
# deterministic identity / hash.
HVS_CREATED_AT_PLACEHOLDER = None


# --- Hashing -----------------------------------------------------------------
def _sha256_hex16(*parts: Any) -> str:
    """Deterministic sha256 hexdigest[:16] over stable semantic parts only.

    Mirrors the SCOS Control Center ``_stable_id``/HVS ``deterministic_hash``
    convention. Volatile inputs (elapsed time, pid, random uuid, temp paths,
    created_at, source_agent, stage, status, artifact_id) are NEVER passed.
    """
    h = hashlib.sha256()
    for part in parts:
        h.update(str(part).encode("utf-8"))
    return h.hexdigest()[:16]


# --- DateTime / audit exclusion note -----------------------------------------
# The HVS contract requires ``created_at`` (date-time). Stage 2 does NOT invent
# a timestamp: it serializes ``created_at`` as ``None`` (omitted in canonical
# serialization / hash) so the mapping stays deterministic. Real HVS fill-in of
# ``created_at`` is explicitly a Stage 3 (production) concern, not Stage 2.


# --- Canonical SCOS input model (Stage 2 edit timeline / render request) ------
@dataclass(frozen=True)
class SCOSAssetRef:
    """A logical asset reference inside a SCOS scene.

    The *logical identity* is ``asset_id`` (never a filesystem path). ``path``
    is optional and only consulted for path-traversal validation; it is NOT part
    of the deterministic identity. ``asset_type`` is preserved exactly.
    """

    asset_id: str
    asset_type: str
    path: str | None = None
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_id", str(self.asset_id))
        object.__setattr__(self, "asset_type", str(self.asset_type))
        object.__setattr__(self, "path", None if self.path is None else str(self.path))
        object.__setattr__(
            self, "metadata", _string_pairs("metadata", self.metadata)
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "asset_id": self.asset_id,
            "asset_type": self.asset_type,
        }
        if self.path is not None:
            out["path"] = self.path
        if self.metadata:
            out["metadata"] = [[k, v] for k, v in self.metadata]
        return out


@dataclass(frozen=True)
class SCOSCaption:
    """A caption bound to one SCOS scene, in canonical milliseconds."""

    scene_id: str
    text: str
    start_ms: int
    end_ms: int
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "scene_id", str(self.scene_id))
        object.__setattr__(self, "text", str(self.text))
        object.__setattr__(self, "start_ms", int(self.start_ms))
        object.__setattr__(self, "end_ms", int(self.end_ms))
        object.__setattr__(
            self, "metadata", _string_pairs("metadata", self.metadata)
        )

    def to_dict(self) -> dict[str, Any]:
        out = {
            "scene_id": self.scene_id,
            "text": self.text,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
        }
        if self.metadata:
            out["metadata"] = [[k, v] for k, v in self.metadata]
        return out


@dataclass(frozen=True)
class SCOSScene:
    """One timeline scene, in canonical milliseconds.

    ``end_ms`` is derived (start_ms + duration_ms); it is never stored
    independently so forward/round-trip timing cannot diverge.
    """

    scene_id: str
    order: int
    start_ms: int
    duration_ms: int
    intent: str
    visual_description: str
    text_overlay: str
    asset_refs: tuple[SCOSAssetRef, ...] = ()
    captions: tuple[SCOSCaption, ...] = ()
    transition: str = "cut"
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "scene_id", str(self.scene_id))
        object.__setattr__(self, "order", int(self.order))
        object.__setattr__(self, "start_ms", int(self.start_ms))
        object.__setattr__(self, "duration_ms", int(self.duration_ms))
        object.__setattr__(self, "intent", str(self.intent))
        object.__setattr__(self, "visual_description", str(self.visual_description))
        object.__setattr__(self, "text_overlay", str(self.text_overlay))
        object.__setattr__(
            self, "asset_refs", tuple(self.asset_refs)
        )
        object.__setattr__(self, "captions", tuple(self.captions))
        object.__setattr__(self, "transition", str(self.transition))
        object.__setattr__(
            self, "metadata", _string_pairs("metadata", self.metadata)
        )

    @property
    def end_ms(self) -> int:
        return self.start_ms + self.duration_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "order": self.order,
            "start_ms": self.start_ms,
            "duration_ms": self.duration_ms,
            "end_ms": self.end_ms,
            "intent": self.intent,
            "visual_description": self.visual_description,
            "text_overlay": self.text_overlay,
            "asset_refs": [a.to_dict() for a in self.asset_refs],
            "captions": [c.to_dict() for c in self.captions],
            "transition": self.transition,
            "metadata": [[k, v] for k, v in self.metadata],
        }


@dataclass(frozen=True)
class SCOSRenderTimelineProject:
    """Canonical SCOS edit-timeline / render-request representation for Stage 2.

    ``total_duration_ms`` is derived as the sum of scene durations (the
    contiguous plan policy used by HVS). ``request_id`` / ``run_id`` are
    correlation references only and are NOT part of the deterministic identity.
    """

    project_id: str
    width: int
    height: int
    fps: int
    scenes: tuple[SCOSScene, ...] = ()
    request_id: str | None = None
    run_id: str | None = None
    selected_preset: str = "standard"
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", str(self.project_id))
        object.__setattr__(self, "width", int(self.width))
        object.__setattr__(self, "height", int(self.height))
        object.__setattr__(self, "fps", int(self.fps))
        object.__setattr__(self, "scenes", tuple(self.scenes))
        object.__setattr__(
            self, "request_id", None if self.request_id is None else str(self.request_id)
        )
        object.__setattr__(
            self, "run_id", None if self.run_id is None else str(self.run_id)
        )
        object.__setattr__(self, "selected_preset", str(self.selected_preset))
        object.__setattr__(
            self, "metadata", _string_pairs("metadata", self.metadata)
        )

    @property
    def resolution(self) -> str:
        return f"{self.width}x{self.height}"

    @property
    def total_duration_ms(self) -> int:
        return sum(scene.duration_ms for scene in self.scenes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "request_id": self.request_id,
            "run_id": self.run_id,
            "width": self.width,
            "height": self.height,
            "resolution": self.resolution,
            "fps": self.fps,
            "selected_preset": self.selected_preset,
            "total_duration_ms": self.total_duration_ms,
            "scene_count": len(self.scenes),
            "scenes": [s.to_dict() for s in self.scenes],
            "metadata": [[k, v] for k, v in self.metadata],
        }


# --- Structured error / result models ----------------------------------------
@dataclass(frozen=True)
class HVSMappingError:
    """Deterministic, structured rejection for an invalid mapping operation."""

    error_kind: str
    error_detail: str
    field: str | None = None
    context: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "error_kind", str(self.error_kind))
        object.__setattr__(self, "error_detail", str(self.error_detail))
        object.__setattr__(
            self, "field", None if self.field is None else str(self.field)
        )
        object.__setattr__(self, "context", _string_pairs("context", self.context))

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_kind": self.error_kind,
            "error_detail": self.error_detail,
            "field": self.field,
            "context": [[k, v] for k, v in self.context],
        }


@dataclass(frozen=True)
class HVSMappingResult:
    """Result wrapper: exactly one of ``payload`` / ``error`` is non-None.

    ``payload_model`` (optional) carries the reconstructed SCOS model when the
    mapping produced one (e.g. ``map_hvs_to_scos``). It is never required for
    the SCOS->HVS direction.
    """

    ok: bool
    payload: dict[str, Any] | None = None
    error: HVSMappingError | None = None
    payload_model: Any | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        if self.error is not None:
            object.__setattr__(self, "error", HVSMappingError(**self.error.to_dict()))

    @staticmethod
    def success(payload: dict[str, Any]) -> "HVSMappingResult":
        return HVSMappingResult(ok=True, payload=payload)

    @staticmethod
    def success_payload_model(model: Any) -> "HVSMappingResult":
        # Carries the typed reconstructed model; ``payload`` stays None for the
        # reverse (HVS->SCOS) direction since the model itself is the result.
        return HVSMappingResult(ok=True, payload=None, payload_model=model)

    @staticmethod
    def failure(
        error_kind: str,
        error_detail: str,
        *,
        field: str | None = None,
        context: tuple[tuple[str, str], ...] = (),
    ) -> "HVSMappingResult":
        return HVSMappingResult(
            ok=False,
            error=HVSMappingError(
                error_kind=error_kind,
                error_detail=error_detail,
                field=field,
                context=tuple(context),
            ),
        )


@dataclass(frozen=True)
class HVSValidationIssue:
    severity: str  # "error" | "warning"
    field: str
    message: str


@dataclass(frozen=True)
class HVSValidationResult:
    ok: bool
    issues: tuple[HVSValidationIssue, ...]

    @staticmethod
    def of(
        issues: tuple[HVSValidationIssue, ...],
    ) -> "HVSValidationResult":
        return HVSValidationResult(
            ok=not any(i.severity == "error" for i in issues), issues=tuple(issues)
        )


@dataclass(frozen=True)
class HVSRoundTripResult:
    """Semantic-equivalence result for a SCOS->HVS->SCOS round trip."""

    equivalent: bool
    scos_in_hash: str
    scos_out_hash: str
    diffs: tuple[str, ...] = ()
    hvs_payload: dict[str, Any] | None = None
    scos_reconstructed: SCOSRenderTimelineProject | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "equivalent", bool(self.equivalent))
        object.__setattr__(self, "diffs", tuple(self.diffs))


# --- helpers -----------------------------------------------------------------
def _string_pairs(field_name: str, value: Any) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    if isinstance(value, dict):
        items = value.items()
    else:
        items = value
    pairs: list[tuple[str, str]] = []
    for item in items:
        pair = tuple(item)
        if len(pair) != 2:
            raise ValueError(
                f"{field_name} entries must be (key, value) pairs, got {item!r}"
            )
        pairs.append((str(pair[0]), str(pair[1])))
    return tuple(pairs)


def _require_resolution(width: int, height: int) -> str | None:
    """Return the supported HVS resolution string or None if unsupported."""
    candidate = f"{int(width)}x{int(height)}"
    return candidate if candidate in HVS_RESOLUTION_VALUES else None


def _require_fps(fps: int) -> bool:
    return int(fps) in HVS_FPS_VALUES


def _ms_to_s(ms: int) -> float:
    """Canonical ms -> seconds with HVS 3-decimal rounding."""
    return round(ms / 1000.0, 3)


def _s_to_ms(seconds: float) -> int:
    """HVS seconds -> canonical ms (inverse of ``_ms_to_s`` rounding)."""
    return int(round(float(seconds) * 1000.0))


def _reject_path_traversal(path: str | None, field_name: str) -> str | None:
    """Reject ``..`` parent-directory traversal in accepted path fields.

    Returns None if ``path`` is None/empty; otherwise returns the normalized
    (POSIX-separated) path. Returns an error-kind string if traversal is found
    (caller decides how to surface it).
    """
    if path is None or path == "":
        return None
    normalized = path.replace("\\", "/")
    if ".." in [seg for seg in normalized.split("/") if seg != ""]:
        return "path_traversal"
    return normalized
