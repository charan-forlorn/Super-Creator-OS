"""Minimal Creative/Asset/Audio/Caption graph that compiles into renderer props.

The graph is intentionally deterministic and carries the learning-loop identity so
render output can be traced back to a brief without inventing telemetry.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CreativeBrief:
    project_id: str
    objective: str
    content_type: str
    language: str = "und"
    duration_s: float = 30.0
    platform_targets: tuple[str, ...] = ()
    loop_run_id: str | None = None


@dataclass(frozen=True)
class SceneNode:
    scene_id: str
    start_s: float
    end_s: float
    title: str = ""
    eyebrow: str = ""
    headline: str = ""
    body: str = ""
    tags: tuple[str, ...] = ()
    accent: str = ""

@dataclass(frozen=True)
class CaptionNode:
    start_ms: int
    end_ms: int
    text: str
    language: str = "und"
    confidence: float | None = None


@dataclass(frozen=True)
class AudioNode:
    asset_id: str
    role: str
    start_s: float = 0.0
    gain_db: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AssetNode:
    asset_id: str
    media_type: str
    path: str
    sha256: str = ""
    rights_evidence: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProductionGraph:
    brief: CreativeBrief
    scenes: tuple[SceneNode, ...] = ()
    captions: tuple[CaptionNode, ...] = ()
    assets: tuple[AssetNode, ...] = ()
    audio: tuple[AudioNode, ...] = ()
    brand_kit_id: str | None = None
    style_profile_id: str | None = None
    master_profile_id: str = "master_vertical_2160"
    delivery_profile_ids: tuple[str, ...] = ()
    render_extras: dict[str, Any] = field(default_factory=dict)
    graph_version: str = "SCOS_PRODUCTION_GRAPH_R1"

    def fingerprint(self) -> str:
        payload = {
            "graph_version": self.graph_version,
            "brief": self.brief.__dict__,
            "scenes": [s.__dict__ for s in self.scenes],
            "captions": [c.__dict__ for c in self.captions],
            "assets": [a.__dict__ for a in self.assets],
            "audio": [a.__dict__ for a in self.audio],
            "brand_kit_id": self.brand_kit_id,
            "style_profile_id": self.style_profile_id,
            "master_profile_id": self.master_profile_id,
            "delivery_profile_ids": self.delivery_profile_ids,
            "render_extras": self.render_extras,
        }
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def to_remotion_props(self) -> dict[str, Any]:
        props = dict(self.render_extras)
        props.update({
            "duration_s": self.brief.duration_s,
            "states": [
                {
                    "start": s.start_s, "end": s.end_s, "title": s.title,
                    "eyebrow": s.eyebrow, "headline": s.headline, "body": s.body,
                    "tags": list(s.tags), "accent": s.accent,
                }
                for s in self.scenes
            ],
            "captions": [
                {"text": c.text, "startMs": c.start_ms, "endMs": c.end_ms, "confidence": c.confidence}
                for c in self.captions
            ],
            "production_graph": {
                "schema_version": self.graph_version,
                "fingerprint": self.fingerprint(),
                "project_id": self.brief.project_id,
                "loop_run_id": self.brief.loop_run_id,
                "brand_kit_id": self.brand_kit_id,
                "style_profile_id": self.style_profile_id,
                "master_profile_id": self.master_profile_id,
                "delivery_profile_ids": list(self.delivery_profile_ids),
            },
        })
        return props

def graph_from_props(props: dict[str, Any]) -> ProductionGraph:
    """Normalize the existing props format into the canonical graph boundary."""
    brief = CreativeBrief(
        project_id=str(props.get("production_graph", {}).get("project_id") or props.get("project_id") or "premium-render"),
        objective=str(props.get("objective") or "create a premium single-screen video"),
        content_type=str(props.get("content_type") or "short_form"),
        language=str(props.get("language") or "und"),
        duration_s=float(props.get("duration_s") or 30.0),
        platform_targets=tuple(props.get("production_graph", {}).get("delivery_profile_ids", ())),
        loop_run_id=props.get("production_graph", {}).get("loop_run_id"),
    )
    scenes = tuple(
        SceneNode(
            scene_id=f"scene-{i:03d}",
            start_s=float(s.get("start", 0)),
            end_s=float(s.get("end", 0)),
            title=str(s.get("title", "")), eyebrow=str(s.get("eyebrow", "")),
            headline=str(s.get("headline", "")), body=str(s.get("body", "")),
            tags=tuple(s.get("tags", ())), accent=str(s.get("accent", "")),
        )
        for i, s in enumerate(props.get("states", ()))
    )
    captions = tuple(CaptionNode(int(c.get("startMs", 0)), int(c.get("endMs", 0)), str(c.get("text", "")), confidence=c.get("confidence")) for c in props.get("captions", ()))
    meta = props.get("production_graph", {})
    return ProductionGraph(brief=brief, scenes=scenes, captions=captions,
                           brand_kit_id=meta.get("brand_kit_id"), style_profile_id=meta.get("style_profile_id"),
                           master_profile_id=str(meta.get("master_profile_id") or "master_vertical_2160"),
                           delivery_profile_ids=tuple(meta.get("delivery_profile_ids", ())),
                           render_extras={k: props[k] for k in ("musicSrc", "sfx") if k in props})
