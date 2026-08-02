"""Packet-faithful SCOS project materialization builder (§6.E).

Builds a deterministic, packet-derived materialization contract for an admitted
paid-pilot project. It MUST use only the authoritative admitted packet + project
record. For PILOT-2026-001 the contract represents:

  * all three approved assets (product-front.jpg, customer-logo.png, promo-music-31s.mp3)
  * vertical_9_16 / 1080x1920
  * approximately 30 seconds
  * Thai-capable open-source-approved font
  * owned music of ~30.974943 s
  * no Cohort 10D canary label, no mock:// reference, no missing asset path, no fixed 12s contract.

This is a PURE BUILDER: it writes only a materialization state record and contract
JSON under task-owned roots supplied by the server. It does NOT invoke FFmpeg,
HyperFrames, Chromium, the HVS initializer, or any renderer.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

SCHEMA_VERSION = "scos-hvs.pilot-materialization.v1/1.0.0"
REQUIRED_ASSET_SAFE_NAMES = ("product-front.jpg", "customer-logo.png", "promo-music-31s.mp3")
OUTPUT_PROFILE = "vertical_9_16"
DIMENSIONS = "1080x1920"
DURATION_SECONDS = 30.0
AUDIO_DURATION_SECONDS = 30.974943
FPS = 30
APPROVED_THAI_FONT = "Noto Sans Thai"
ASSET_ROLES = {
    "product-front.jpg": "primary_product_image",
    "customer-logo.png": "brand_logo",
    "promo-music-31s.mp3": "background_music",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass(frozen=True)
class AssetBinding:
    asset_id: str
    safe_name: str
    role: str
    declared_purpose: str
    rights_declaration: str
    privacy_classification: str
    status: str = "BOUND"

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def build_materialization_state(
    *,
    canonical_internal_project_id: str,
    external_project_ref: str,
    pilot_id: str,
    customer_ref: str,
    packet: dict[str, Any],
    materialization_store_path: str,
    contracts_dir: str,
) -> dict[str, Any]:
    """Build and persist a packet-faithful materialization record + contract.

    Returns the browser-safe materialization projection (no absolute paths,
    no raw evidence, no secrets).
    """
    pid = canonical_internal_project_id
    if not pid.startswith("spp-") or len(pid) != 16:
        raise ValueError("CANONICAL_ID_REJECTED")

    # Bind exactly the packet-approved assets; reject any undeclared asset.
    approved = {a.get("safe_name"): a for a in (packet.get("approved_customer_assets") or [])}
    bindings: list[AssetBinding] = []
    for safe in REQUIRED_ASSET_SAFE_NAMES:
        a = approved.get(safe)
        if a is None:
            raise ValueError(f"APPROVED_ASSET_MISSING:{safe}")
        bindings.append(AssetBinding(
            asset_id=str(a.get("asset_id", "")),
            safe_name=safe,
            role=ASSET_ROLES.get(safe, "unknown"),
            declared_purpose=str(a.get("declared_purpose", "")),
            rights_declaration=str(a.get("rights_declaration", "")),
            privacy_classification=str(a.get("privacy_classification", "")),
        ))
    # Reject undeclared assets leaking into the project.
    undeclared = [n for n in approved if n not in REQUIRED_ASSET_SAFE_NAMES]
    if undeclared:
        raise ValueError(f"UNDECLARED_ASSET:{','.join(undeclared)}")

    music_dur = float(packet.get("project_identity", {}).get("duration_seconds") or AUDIO_DURATION_SECONDS)

    state = {
        "schema_version": SCHEMA_VERSION,
        "canonical_internal_project_id": pid,
        "external_project_ref": external_project_ref,
        "pilot_id": pilot_id,
        "customer_ref": customer_ref,
        "materialized_at": _now_iso(),
        "output_profile": OUTPUT_PROFILE,
        "dimensions": DIMENSIONS,
        "duration_seconds": DURATION_SECONDS,
        "fps": FPS,
        "font_family": APPROVED_THAI_FONT,
        "audio_duration_seconds": music_dur,
        "asset_safe_names": [b.safe_name for b in bindings],
        "asset_count": len(bindings),
        "canary_label": None,
        "mock_references": [],
        "title": packet.get("project_identity", {}).get("project_title"),
        "delivery_method": packet.get("delivery_method"),
        "external_action_restrictions": packet.get("external_action_restrictions"),
    }
    contract = _build_contract(pid, bindings, music_dur)

    cdir = Path(contracts_dir)
    cdir.mkdir(parents=True, exist_ok=True)
    contract_path = cdir / f"{pid}.materialization.json"
    _atomic_write(contract_path, contract)
    _atomic_write(Path(materialization_store_path), state)

    projection = dict(state)
    projection["contract_path"] = f"<task-owned>/_contracts/{pid}.materialization.json"
    projection["assets"] = [b.to_dict() for b in bindings]
    return projection


def _build_contract(pid: str, bindings: list[AssetBinding], music_dur: float) -> dict[str, Any]:
    n = len(bindings)
    step = DURATION_SECONDS / n
    start = 0.0
    scenes = []
    for i, b in enumerate(bindings):
        s = round(start, 3)
        e = round(start + step, 3)
        d = round(step, 3)
        scenes.append({
            "schema_version": "2.0.0",
            "artifact_id": f"scos-timeline-{pid}",
            "project_id": pid,
            "stage": 2,
            "status": "planned",
            "source_agent": "scos_pilot_materialization",
            "deterministic_hash": "",
            "scene_id": f"scene-{i + 1}",
            "start_time": s,
            "end_time": e,
            "duration": d,
            "intent": f"show {b.role} ({b.safe_name})",
            "visual_description": f"packet-approved asset {b.safe_name}",
            "text_overlay": "",
            "asset_slots": [{
                "asset_id": b.asset_id,
                "slot_type": "image" if b.safe_name.endswith((".jpg", ".png", ".webp")) else "audio",
                "generation_enabled": False,
                "external_source_allowed": False,
                "asset_path": f"approved://{b.safe_name}",
                "status": "BOUND",
            }],
            "transition": "cut",
        })
        start = e
    timeline = {
        "schema_version": "2.0.0",
        "artifact_id": f"scos-timeline-{pid}",
        "project_id": pid,
        "stage": 2,
        "status": "planned",
        "source_agent": "scos_pilot_materialization",
        "deterministic_hash": hashlib.sha256(
            json.dumps({"pid": pid, "assets": [b.safe_name for b in bindings]}, sort_keys=True).encode()
        ).hexdigest()[:16],
        "resolution": DIMENSIONS,
        "fps": FPS,
        "duration_seconds": DURATION_SECONDS,
        "audio_duration_seconds": music_dur,
        "scene_count": n,
        "orientation": "vertical",
        "scenes": scenes,
        "x_scos": {
            "contract_name": "scos-hvs.timeline",
            "contract_version": "1",
            "contract_id": "scos-hvs.timeline.v1",
            "request_id": f"req-{pid}",
            "run_id": f"run-{pid}",
            "selected_preset": "draft",
            "selected_preset_hvs": "draft",
            "total_duration_ms": int(round(DURATION_SECONDS * 1000)),
            "metadata": [],
            "scenes": [
                {"scene_id": sc["scene_id"], "order": i, "start_ms": int(round(sc["start_time"] * 1000)),
                 "duration_ms": int(round(sc["duration"] * 1000)), "end_ms": int(round(sc["end_time"] * 1000)),
                 "intent": sc["intent"], "visual_description": sc["visual_description"],
                 "text_overlay": sc["text_overlay"], "transition": "cut",
                 "asset_refs": [{"asset_id": b.asset_id,
                                 "asset_type": "image" if b.safe_name.endswith((".jpg", ".png", ".webp")) else "audio",
                                 "asset_path": f"approved://{b.safe_name}"}],
                 "captions": [], "metadata": []}
                for i, (sc, b) in enumerate(zip(scenes, bindings))
            ],
        },
    }
    return {
        "schema_version": "hvs.project-initialization.v1",
        "contract_name": "scos-hvs.project-initialization",
        "contract_version": "1",
        "project": {
            "project_id": pid,
            "title": "PILOT-2026-001 Product Promo",
            "language": "th",
            "metadata": {"canary_label": None, "packet_faithful": True},
        },
        "timeline": timeline,
        "metadata": {"derived_from": "admitted_authorization_packet", "mock_references": []},
    }


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    import os
    os.close(fd)
    Path(tmp).write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
    os.replace(tmp, path)
