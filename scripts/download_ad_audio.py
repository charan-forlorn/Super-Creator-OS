"""Download audio assets for the AI Automation advertisement."""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path

OUT = Path("C:/Workspace/super-creator-os/scos/work/ai-auto-ad-c1b9427f/audio")
OUT.mkdir(parents=True, exist_ok=True)

MANIFEST = []

def download(name, url, source, license_type, **meta):
    path = OUT / name
    print(f"  downloading {name}...")
    try:
        result = subprocess.run(
            ["curl", "-fsSL", "-o", str(path), url],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            print(f"    FAILED: {result.stderr[:200]}")
            if path.exists(): path.unlink(missing_ok=True)
            return None
        if not path.exists() or path.stat().st_size < 100:
            print(f"    EMPTY")
            path.unlink(missing_ok=True)
            return None
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        rec = {
            "filename": name, "source": source, "url": url, "license": license_type,
            "sha256": sha, "size_bytes": path.stat().st_size,
            "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"), **meta
        }
        MANIFEST.append(rec)
        print(f"    OK: {sha[:16]} ({path.stat().st_size / 1024:.1f} KB)")
        return rec
    except Exception as exc:
        print(f"    ERROR: {exc}")
        return None

# MixClap CC0 transition sound effects
SFX = [
    ("whoosh.mp3", "https://www.mixclap.com/transitionEffects/whoosh.mp3", "Stereo whoosh - CC0"),
    ("whoosh_fast.mp3", "https://www.mixclap.com/transitionEffects/whoosh-fast.mp3", "Fast whoosh - CC0"),
    ("noise_sweep.mp3", "https://www.mixclap.com/transitionEffects/noise-sweep.mp3", "Noise sweep - CC0"),
    ("riser.mp3", "https://www.mixclap.com/transitionEffects/riser.mp3", "Cinematic riser - CC0"),
    ("riser_impact.mp3", "https://www.mixclap.com/transitionEffects/riser-impact.mp3", "Riser + impact - CC0"),
]

for name, url, desc in SFX:
    download(name, url, "MixClap / Freesound", "CC0 (public domain - no attribution required)", description=desc)

# Try Pixabay music (may need direct CDN)
# Pixabay CDN URLs follow pattern: https://cdn.pixabay.com/audio/YYYY/MM/DD/audio-XXXXXX_XXXXX.mp3
# For "Modern Futuristic Technology" by MondaMusic (ID 512861)
# Common pattern - try a few possible CDN paths
PIXABAY_MUSIC = [
    ("music_futuristic_512861.mp3", "https://cdn.pixabay.com/download/audio/2026/04/07/audio_ae7c4cb59f.mp3?filename=electronic-modern-futuristic-technology-512861.mp3", "MondaMusic", "Modern Futuristic Technology"),
    ("music_corporate_futuristic_522421.mp3", "https://cdn.pixabay.com/download/audio/2025/01/21/audio_3a2e7e8e7c.mp3?filename=corporate-futuristic-522421.mp3", "AtlasAudio", "Corporate Futuristic"),
]

print("\nTrying Pixabay music download...")
for name, url, creator, title in PIXABAY_MUSIC:
    rec = download(name, url, "Pixabay", "Pixabay Content License (free for commercial use)",
                   creator=creator, title=title, note="May be placeholder - will fall back to procedural music if needed")

# Save manifest
with open(OUT / "audio_manifest.json", "w") as f:
    json.dump(MANIFEST, f, indent=2)
print(f"\nAudio manifest: {len(MANIFEST)} assets.")
