"""Stable render interface for SCOS Stage 1.

The orchestrator depends on THIS module (a small, typed contract) — never on any
`integrations/` renderer directly. Concrete backends (see `video_use_backend.py`)
implement `RenderBackend` and are free to invoke an external engine; the rest of
SCOS only knows the interface.

Design rules honoured here:
  * typed dataclasses, no magic values (all encode constants live on `RenderProfile`)
  * one stable method — `RenderBackend.render(request) -> RenderResult`
  * a single exception type (`RenderError`) for every hard failure, so the
    orchestrator's existing error boundary records `render: failed` cleanly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

CAMERA_MOTIONS = {
    "static",
    "push_in",
    "pull_out",
    "drift_left",
    "drift_right",
    "drift_up",
    "drift_down",
}


class RenderError(Exception):
    """Raised on any unrecoverable render failure.

    Covers: missing/empty input media, engine (subprocess) failure, and output
    validation failure. Callers in SCOS catch this (or let it propagate to the
    pipeline error boundary) rather than inspecting backend internals.
    """


@dataclass(frozen=True)
class RenderProfile:
    """Output encode target. Single source of truth for render constants.

    The vendored engine owns the *final* encode (grade, loudnorm, x264 settings).
    These values describe the canvas the bridge builds intermediate scene clips at
    and the geometry the backend validates the final file against.
    """

    width: int = 1080
    height: int = 1920
    fps: int = 30
    # CRF for the intermediate still->clip encode only. The engine re-encodes the
    # final master with its own quality ladder; keeping this modest avoids wasting
    # cycles on a clip that gets re-encoded downstream.
    intermediate_crf: int = 20
    # Grade passed through to the engine EDL ("none" | "auto" | preset | raw filter).
    grade: str = "none"

    @property
    def resolution(self) -> str:
        return f"{self.width}x{self.height}"


@dataclass(frozen=True)
class ShotSpec:
    """Canonical shot contract shared by deterministic and generative renderers.

    Deterministic rendering consumes the visual/audio/motion fields today.
    The remaining fields are carried end-to-end for a future generative backend.
    """

    scene_id: str
    visual_path: Path
    audio_path: Path | None
    duration_s: float
    motion: str = "static"
    motion_strength: float = 0.08
    camera: str = "locked"
    action: str = ""
    environment: str = ""
    lighting: str = ""
    style: str = ""
    prompt: str = ""
    references: tuple[str, ...] = ()
    start_frame: Path | None = None
    end_frame: Path | None = None
    generation_backend: str = "deterministic"
    continuity_group: str = ""

    def __post_init__(self) -> None:
        if self.duration_s <= 0:
            raise RenderError(f"scene {self.scene_id}: non-positive duration {self.duration_s}")
        if self.motion not in CAMERA_MOTIONS:
            raise RenderError(f"scene {self.scene_id}: unsupported camera motion '{self.motion}'")
        if not 0.0 <= self.motion_strength <= 0.5:
            raise RenderError(
                f"scene {self.scene_id}: motion_strength must be within [0, 0.5]"
            )
        if not self.generation_backend.strip():
            raise RenderError(f"scene {self.scene_id}: generation_backend must be non-empty")


@dataclass(frozen=True)
class GeneratedShot:
    """Result contract returned by a generative video backend."""

    scene_id: str
    video_path: Path
    duration_s: float
    provider: str
    task_id: str | None = None
    info: str = ""


class GenerativeBackend(ABC):
    """Provider-neutral generation contract built on the same ShotSpec."""

    @property
    @abstractmethod
    def backend_id(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def generate(
        self,
        shot: ShotSpec,
        profile: RenderProfile,
        output_path: Path,
    ) -> GeneratedShot:
        """Generate one shot and return a verified local video artifact."""
        raise NotImplementedError


# Backward-compatible name for existing render callers and tests.
RenderClip = ShotSpec


@dataclass
class RenderRequest:
    """Everything a backend needs to produce one video."""

    run_id: str
    clips: list[ShotSpec]
    output_path: Path
    work_dir: Path
    profile: RenderProfile = field(default_factory=RenderProfile)


@dataclass
class RenderResult:
    """Outcome of a successful render (failures raise `RenderError`)."""

    success: bool
    video_path: Path | None
    duration_s: float | None = None
    width: int | None = None
    height: int | None = None
    fps: int | None = None
    info: str = ""


class RenderBackend(ABC):
    """The contract SCOS depends on. Implementations may use any local engine."""

    @abstractmethod
    def render(self, request: RenderRequest) -> RenderResult:
        """Produce `request.output_path` from `request.clips`.

        Must raise `RenderError` on any unrecoverable failure and must only
        return a `RenderResult(success=True, ...)` once the output file has been
        verified to exist and be non-empty.
        """
        raise NotImplementedError
