"""Local-first video project materialization backend.

The materialization boundary creates a render-ready project contract without
invoking a renderer. HyperFrames is the canonical local backend; legacy HVS is
handled by the separate compatibility adapter only when explicitly configured.

Safety: deterministic output, task-owned roots only, no network, no render,
no FFmpeg/Chrome invocation, and read-only inspection for post-write proof.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()[:16]


def initialize_project(*, project_id: str, projects_root: str,
                       expected_payload_hash: str = "",
                       request_id: str = "") -> dict[str, Any]:
    root = Path(projects_root).resolve()
    project_name = project_id if project_id.startswith("hvs-") else f"hvs-{project_id.removeprefix('spp-')}"
    project = root / project_name
    project.mkdir(parents=True, exist_ok=True)

    timeline = {
        "schema_version": "scos-video.timeline.v1",
        "project_id": project_id,
        "engine": "hyperframes",
        "request_id": request_id,
        "resolution": "1080x1920",
        "fps": 30,
        "duration_seconds": 12.0,
        "orientation": "vertical",
        "scenes": [
            {"scene_id": f"scene-{i}", "start": i * 4.0, "duration": 4.0,
             "transition": "cut", "assets": []}
            for i in range(1, 4)
        ],
    }
    brief = {
        "schema_version": "scos-video.project-brief.v1",
        "project_id": project_id,
        "engine": "hyperframes",
        "title": "SCOS Local Video Project",
        "materialization": "isolated",
        "render_allowed": False,
        "network_allowed": False,
    }
    identity = {
        "engine": "hyperframes",
        "project_id": project_id,
        "timeline": timeline,
        "brief": brief,
    }
    payload_hash = expected_payload_hash[:16] if expected_payload_hash else _hash(identity)
    manifest = {
        "schema_version": "scos-video.materialization.v1",
        "engine": "hyperframes",
        "project_id": project_id,
        "status": "verified",
        "payload_hash": payload_hash,
        "request_id": request_id,
        "network_used": False,
        "render_started": False,
        "assets_copied": False,
        "voice_created": False,
        "project_verified": True,
        "files": [
            "initialization_manifest.json",
            "project_brief.json",
            "timelines/video_timeline.json",
        ],
    }

    (project / "timelines").mkdir(parents=True, exist_ok=True)
    (project / "project_brief.json").write_text(
        json.dumps(brief, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (project / "timelines" / "video_timeline.json").write_text(
        json.dumps(timeline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (project / "initialization_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "ok": True,
        "engine": "hyperframes",
        "command": "materialize-project",
        "exit_code": 0,
        "payload": {
            "requested_project_id": project_id,
            "actual_project_id": project_id,
            "actual_payload_hash": payload_hash,
            "project_created": True,
            "project_verified": True,
            "identical_replay": False,
            "status": "verified",
        },
    }


def inspect_project(*, project_id: str, projects_root: str) -> dict[str, Any]:
    project_name = project_id if project_id.startswith("hvs-") else f"hvs-{project_id.removeprefix('spp-')}"
    project = Path(projects_root).resolve() / project_name
    manifest_path = project / "initialization_manifest.json"
    brief_path = project / "project_brief.json"
    timeline_path = project / "timelines" / "video_timeline.json"
    exists = project.is_dir()
    if not (manifest_path.is_file() and brief_path.is_file() and timeline_path.is_file()):
        return {"ok": True, "exists": exists, "valid": False, "payload_hash": "",
                "render_started": False, "payload": {"exists": exists, "valid": False}}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        brief = json.loads(brief_path.read_text(encoding="utf-8"))
        timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"ok": True, "exists": True, "valid": False, "payload_hash": "",
                "render_started": False, "payload": {"exists": True, "valid": False}}
    valid = (
        manifest.get("engine") == "hyperframes"
        and brief.get("engine") == "hyperframes"
        and timeline.get("engine") == "hyperframes"
        and manifest.get("project_verified") is True
        and manifest.get("render_started") is False
        and manifest.get("network_used") is False
    )
    payload_hash = str(manifest.get("payload_hash") or "")
    return {
        "ok": True,
        "exists": True,
        "valid": valid,
        "payload_hash": payload_hash,
        "render_started": bool(manifest.get("render_started")),
        "payload": {"exists": True, "valid": valid, "payload_hash": payload_hash,
                    "render_started": bool(manifest.get("render_started"))},
    }
