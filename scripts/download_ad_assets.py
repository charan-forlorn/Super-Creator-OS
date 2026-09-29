"""Download external stock assets for the AI Automation advertisement."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

OUT = Path("C:/Workspace/super-creator-os/scos/work/ai-auto-ad-c1b9427f/external_assets")
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
            return None
        if not path.exists() or path.stat().st_size < 1000:
            print(f"    EMPTY")
            path.unlink(missing_ok=True)
            return None
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        rec = {
            "filename": name,
            "source": source,
            "url": url,
            "license": license_type,
            "sha256": sha,
            "size_bytes": path.stat().st_size,
            "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            **meta
        }
        MANIFEST.append(rec)
        print(f"    OK: {sha[:16]} ({path.stat().st_size / 1024:.1f} KB)")
        return rec
    except Exception as exc:
        print(f"    ERROR: {exc}")
        return None

# Pexels video download URLs (direct CDN links from video pages)
# These are direct CDN URLs that don't require login
ASSETS = [
    # Technology data server room
    ("tech_data_center.mp4", "https://videos.pexels.com/video-files/3770033/3770033-uhd_2560_1440_30fps.mp4"),
    # Futuristic technology abstract
    ("futuristic_tech.mp4", "https://videos.pexels.com/video-files/3141208/3141208-uhd_2560_1440_25fps.mp4"),
    # Digital interface / coding
    ("coding_screen.mp4", "https://videos.pexels.com/video-files/1093662/1093662-uhd_2560_1440_30fps.mp4"),
]

for name, url in ASSETS:
    download(name, url, "Pexels", "Pexels Free License (commercial use permitted)")

# Save manifest
with open(OUT / "manifest.json", "w") as f:
    json.dump(MANIFEST, f, indent=2)
print(f"\nDownloaded {len(MANIFEST)} / {len(ASSETS)} assets.")
