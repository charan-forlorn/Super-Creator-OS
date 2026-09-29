"""Full render pipeline for AI Automation advertisement."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path("C:/Workspace/super-creator-os")
RUN_ID = "ai-auto-ad-c1b9427f"
WORK = REPO / "scos" / "work" / RUN_ID
STILLS = WORK / "source-assets"
AUDIO = WORK / "audio"
RENDERS = WORK / "renders"
COMPOSITIONS = WORK / "compositions"

# Add repo to path
sys.path.insert(0, str(REPO))

from scos.render.base import (
    RenderError, RenderProfile, RenderRequest, ShotSpec
)
from scos.render.generative_video_backend import GenerativeVideoBackend
from scos.render.video_use_backend import VideoUseBackend
from scos.render.hardware import choose_encoder

# ---- Scene definitions ----
# 7 scenes, ~20s total
# Shot 03 (generative) uses WanVACE backend
# All others use deterministic rendering

SCENES = [
    {
        "scene_id": "shot_01_hook",
        "visual": STILLS / "shot_01_hook.png",
        "duration": 2.0,
        "motion": "push_in",
        "motion_strength": 0.15,
        "generation_backend": "deterministic",
        "text": "CREATIVE PRODUCTION\nSHOULDN'T FEEL MANUAL",
    },
    {
        "scene_id": "shot_02_activate",
        "visual": STILLS / "shot_02_activate.png",
        "duration": 2.5,
        "motion": "push_in",
        "motion_strength": 0.12,
        "generation_backend": "deterministic",
        "text": "AUTOMATE THE LOOP",
    },
    {
        "scene_id": "shot_03_generative_a",
        "visual": STILLS / "shot_03_generative.png",
        "duration": 2.0,
        "motion": "static",
        "motion_strength": 0.0,
        "generation_backend": "wan2.1-vace-1.3b-int4",
        "prompt": "Digital data streams transforming into polished cinematic assets, futuristic technology, smooth motion, high quality, cinematic lighting",
        "action": "data streams forming into polished media",
        "environment": "futuristic digital space",
        "lighting": "cinematic blue and cyan",
        "style": "premium technology advertisement",
        "text": "GENERATE",
    },
    {
        "scene_id": "shot_03_generative_b",
        "visual": STILLS / "shot_03_generative.png",
        "duration": 1.5,
        "motion": "static",
        "motion_strength": 0.0,
        "generation_backend": "wan2.1-vace-1.3b-int4",
        "prompt": "Polished media assets materializing from abstract digital particles, futuristic creation, smooth cinematic motion, blue and cyan lighting",
        "action": "assets materializing from particles",
        "environment": "futuristic digital space",
        "lighting": "cinematic blue and cyan",
        "style": "premium technology advertisement",
        "text": "GENERATE",
    },
    {
        "scene_id": "shot_04_editing",
        "visual": STILLS / "shot_04_editing.png",
        "duration": 4.0,
        "motion": "push_in",
        "motion_strength": 0.1,
        "generation_backend": "deterministic",
        "text": "EDIT  -  TRANSITIONS  -  FX",
    },
    {
        "scene_id": "shot_05_qa",
        "visual": STILLS / "shot_05_qa.png",
        "duration": 3.0,
        "motion": "static",
        "motion_strength": 0.0,
        "generation_backend": "deterministic",
        "text": "PASS  -  VERIFIED  -  OUTPUT READY",
    },
    {
        "scene_id": "shot_06_platforms",
        "visual": STILLS / "shot_06_platforms.png",
        "duration": 3.0,
        "motion": "push_in",
        "motion_strength": 0.08,
        "generation_backend": "deterministic",
        "text": "ONE SOURCE  -  ALL PLATFORMS",
    },
    {
        "scene_id": "shot_07_cta",
        "visual": STILLS / "shot_07_cta.png",
        "duration": 2.0,
        "motion": "static",
        "motion_strength": 0.0,
        "generation_backend": "deterministic",
        "text": "AI AUTOMATION\nFOR CREATIVE PRODUCTION",
    },
]

def build_shot(spec: dict) -> ShotSpec:
    """Build a ShotSpec from scene definition."""
    return ShotSpec(
        scene_id=spec["scene_id"],
        visual_path=Path(spec["visual"]),
        audio_path=None,  # No per-scene audio; music mixed at final stage
        duration_s=spec["duration"],
        motion=spec.get("motion", "static"),
        motion_strength=spec.get("motion_strength", 0.0),
        camera="locked",
        action=spec.get("action", ""),
        environment=spec.get("environment", ""),
        lighting=spec.get("lighting", ""),
        style=spec.get("style", ""),
        prompt=spec.get("prompt", ""),
        generation_backend=spec["generation_backend"],
    )


def render_video(shots: list[ShotSpec], output_path: Path, work_dir: Path) -> dict:
    """Render the full video using GenerativeVideoBackend."""
    profile = RenderProfile(width=1080, height=1920, fps=30)
    request = RenderRequest(
        run_id=RUN_ID,
        clips=shots,
        output_path=output_path,
        work_dir=work_dir,
        profile=profile,
    )
    
    # Use GenerativeVideoBackend (handles both deterministic and generative)
    backend = GenerativeVideoBackend()
    result = backend.render(request)
    
    if not result.success:
        raise RenderError(f"render failed: {result.info}")
    
    return {
        "success": result.success,
        "video_path": str(result.video_path),
        "duration_s": result.duration_s,
        "width": result.width,
        "height": result.height,
        "fps": result.fps,
        "info": result.info,
    }


def mix_audio_video(video_path: Path, audio_path: Path, output_path: Path, duration: float = 20.0):
    """Mix background music into the video."""
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-nostats", "-loglevel", "error",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-map", "0:v:0", "-map", "1:a:0",
        "-t", f"{duration:.3f}",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-shortest",
        "-movflags", "+faststart",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise RenderError(f"audio mix failed: {proc.stderr.strip()[-600:]}")
    return output_path


def probe_video(path: Path) -> dict:
    """Probe video metadata."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate",
        "-of", "json", str(path)
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {proc.stderr}")
    data = json.loads(proc.stdout)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
    return {
        "duration_s": float(data.get("format", {}).get("duration", 0)),
        "size_bytes": int(data.get("format", {}).get("size", 0)),
        "width": video.get("width"),
        "height": video.get("height"),
        "fps": video.get("r_frame_rate"),
        "video_codec": video.get("codec_name"),
        "audio_codec": audio.get("codec_name"),
        "has_audio": bool(audio),
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ============================================================
# MAIN
# ============================================================

print("=" * 60)
print("AI AUTOMATION ADVERTISEMENT — RENDER PIPELINE")
print("=" * 60)

# Build shots
shots = [build_shot(s) for s in SCENES]
total_duration = sum(s.duration_s for s in shots)
print(f"\nScenes: {len(shots)} | Total duration: {total_duration}s")
for s in shots:
    print(f"  {s.scene_id}: {s.duration_s}s [{s.generation_backend}]")

# Step 1: Render video (stills + generative)
print("\n[1/4] Rendering video...")
RENDERS.mkdir(parents=True, exist_ok=True)
video_no_audio = RENDERS / f"{RUN_ID}_no_audio.mp4"
work_dir = WORK / "render_work"

try:
    result = render_video(shots, video_no_audio, work_dir)
    print(f"  OK: {result['width']}x{result['height']}@{result['fps']}fps, {result['duration_s']}s")
    print(f"  Info: {result['info']}")
except RenderError as e:
    print(f"  FAILED: {e}")
    sys.exit(1)

# Step 2: Mix audio
print("\n[2/4] Mixing audio...")
music_path = AUDIO / "music_futuristic_main.wav"
final_video = RENDERS / f"{RUN_ID}_final.mp4"

try:
    mix_audio_video(video_no_audio, music_path, final_video, duration=total_duration)
    print(f"  OK: {final_video}")
except RenderError as e:
    print(f"  FAILED: {e}")
    sys.exit(1)

# Step 3: Probe + verify
print("\n[3/4] Verifying output...")
meta = probe_video(final_video)
sha = sha256_file(final_video)
print(f"  Resolution: {meta['width']}x{meta['height']}")
print(f"  Duration: {meta['duration_s']:.2f}s")
print(f"  FPS: {meta['fps']}")
print(f"  Video codec: {meta['video_codec']}")
print(f"  Audio codec: {meta['audio_codec']}")
print(f"  Has audio: {meta['has_audio']}")
print(f"  SHA256: {sha[:32]}...")

# Technical QA
qa_pass = True
issues = []
if meta["width"] != 1080 or meta["height"] != 1920:
    issues.append(f"Resolution mismatch: {meta['width']}x{meta['height']}")
    qa_pass = False
if abs(meta["duration_s"] - total_duration) > 1.0:
    issues.append(f"Duration mismatch: {meta['duration_s']:.2f}s vs {total_duration}s")
    qa_pass = False
if not meta["has_audio"]:
    issues.append("No audio stream")
    qa_pass = False
if meta["video_codec"] != "h264":
    issues.append(f"Unexpected video codec: {meta['video_codec']}")
    qa_pass = False

if qa_pass:
    print("  TECHNICAL QA: PASS")
else:
    print(f"  TECHNICAL QA: FAIL — {issues}")

# Step 4: Save render manifest
print("\n[4/4] Saving manifest...")
manifest = {
    "run_id": RUN_ID,
    "concept": "AI Automation turns complex creative production into intelligent automated system",
    "target_platforms": ["Instagram Reels", "TikTok"],
    "duration_s": total_duration,
    "resolution": "1080x1920",
    "fps": 30,
    "scenes": [
        {
            "scene_id": s["scene_id"],
            "duration_s": s["duration"],
            "role": s["scene_id"].split("_")[1],
            "generation_backend": s["generation_backend"],
            "text": s.get("text", ""),
        }
        for s in SCENES
    ],
    "generated_shots": ["shot_03_generative"],
    "external_assets_used": [
        "ai_technology_203986.mp4",
        "ai_robot_215500.mp4",
        "matrix_network_47802.mp4",
        "matrix_characters_2321.mp4",
        "golden_particles_48569.mp4",
        "futuristic_tech.mp4",
    ],
    "audio": {
        "music": "music_futuristic_main.wav (procedural, CC0)",
        "sfx": ["whoosh.mp3", "whoosh_fast.mp3", "noise_sweep.mp3", "riser.mp3", "riser_impact.mp3"],
    },
    "render_profile": "1080x1920@30fps, H.264 NVENC, AAC 192k",
    "encoder": choose_encoder().signature,
    "output": {
        "path": str(final_video),
        "sha256": sha,
        "probe": meta,
    },
    "technical_qa": "PASS" if qa_pass else f"FAIL: {issues}",
}

with open(WORK / "manifest.json", "w") as f:
    json.dump(manifest, f, indent=2)

print(f"\n{'=' * 60}")
print(f"RENDER COMPLETE")
print(f"Output: {final_video}")
print(f"SHA256: {sha}")
print(f"QA: {'PASS' if qa_pass else 'FAIL'}")
print(f"{'=' * 60}")
