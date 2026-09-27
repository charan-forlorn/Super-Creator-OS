from __future__ import annotations
from dataclasses import asdict,dataclass,field
from typing import Any

@dataclass(frozen=True)
class SilenceSpan:
    start: float
    end: float
    duration: float
    kind: str="silence"
    def to_dict(self)->dict[str,Any]: return asdict(self)

@dataclass(frozen=True)
class SceneBoundary:
    time: float
    threshold: float
    evidence: str="scene_change"
    def to_dict(self)->dict[str,Any]: return asdict(self)

@dataclass(frozen=True)
class AdBoundary:
    content_end: float
    trigger_scene_time: float
    confidence: float
    reason: str
    def to_dict(self)->dict[str,Any]: return asdict(self)

@dataclass(frozen=True)
class CadenceStats:
    source_fps: float
    expected_frames: int
    distinct_frames_estimate: int
    duplicate_ratio: float
    cfr: bool
    sampled_pts_monotonic: bool=True
    def to_dict(self)->dict[str,Any]: return asdict(self)

@dataclass(frozen=True)
class MediaSourceProbe:
    path: str; duration_s: float; width: int; height: int; fps: float; frames: int
    video_codec: str; pixel_format: str; color_transfer: str
    audio_codec: str|None; audio_sample_rate: int|None; audio_channels: int|None; has_audio: bool
    cfr: bool = True
    def to_dict(self)->dict[str,Any]: return asdict(self)

@dataclass(frozen=True)
class SubtitleEvidence:
    source: str; status: str; confidence: float|None=None; path: str|None=None; note: str=""
    def to_dict(self)->dict[str,Any]: return asdict(self)

@dataclass
class MediaEvidence:
    source: MediaSourceProbe
    silences: list[SilenceSpan]=field(default_factory=list)
    scene_boundaries: list[SceneBoundary]=field(default_factory=list)
    cadence: CadenceStats|None=None
    subtitles: SubtitleEvidence=field(default_factory=lambda: SubtitleEvidence("none","UNKNOWN"))
    warnings: list[str]=field(default_factory=list)
    ad_boundary: AdBoundary|None=None
    source_sha256: str|None = None
    def to_dict(self)->dict[str,Any]:
        return {"source":self.source.to_dict(),"silences":[x.to_dict() for x in self.silences],
                "scene_boundaries":[x.to_dict() for x in self.scene_boundaries],
                "cadence":self.cadence.to_dict() if self.cadence else None,
                "subtitles":self.subtitles.to_dict(),"warnings":list(self.warnings),
                "ad_boundary":self.ad_boundary.to_dict() if self.ad_boundary else None,
                "source_sha256":self.source_sha256}

@dataclass(frozen=True)
class EditPlan:
    keep_ranges: tuple[tuple[float,float],...]
    silence_threshold_db: float
    silence_min_duration_s: float
    fps_policy: str
    encoder_profile: str
    interpolation_policy: str
    subtitle_policy: str
    output_timeline: str="concatenated"
    ad_boundary_s: float|None=None
    def to_dict(self)->dict[str,Any]: return asdict(self)
