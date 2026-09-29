"""Download external stock assets from Pixabay CDN."""
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

def download(name, url, source, license_type, creator="", **meta):
    path = OUT / name
    if path.exists() and path.stat().st_size > 1000:
        print(f"  {name}: already exists ({path.stat().st_size / 1024:.1f} KB)")
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        return {
            "filename": name, "source": source, "url": url, "license": license_type,
            "sha256": sha, "size_bytes": path.stat().st_size,
            "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"), "creator": creator, **meta
        }
    print(f"  downloading {name}...")
    try:
        result = subprocess.run(
            ["curl", "-fsSL", "-o", str(path), url],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            print(f"    FAILED: {result.stderr[:300]}")
            if path.exists(): path.unlink(missing_ok=True)
            return None
        if not path.exists() or path.stat().st_size < 1000:
            print(f"    EMPTY")
            path.unlink(missing_ok=True)
            return None
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        rec = {
            "filename": name, "source": source, "url": url, "license": license_type,
            "sha256": sha, "size_bytes": path.stat().st_size,
            "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"), "creator": creator, **meta
        }
        MANIFEST.append(rec)
        print(f"    OK: {sha[:16]} ({path.stat().st_size / 1024:.1f} KB)")
        return rec
    except Exception as exc:
        print(f"    ERROR: {exc}")
        return None

# Pixabay CDN direct links (from page extraction)
PIXABAY_ASSETS = [
    ("ai_technology_203986.mp4", "https://cdn.pixabay.com/video/2024/03/12/203986-923133871_large.mp4", "olenchic", "AI Technology digital abstract"),
    ("ai_robot_215500.mp4", "https://cdn.pixabay.com/video/2024/06/06/215500_large.mp4", "riaz-baloch", "AI Robot technology"),
    ("matrix_network_47802.mp4", "https://cdn.pixabay.com/video/2020/08/21/47802-451812879_large.mp4", "ChristianBodhi", "Matrix computer network communication"),
    ("matrix_characters_2321.mp4", "https://cdn.pixabay.com/video/2016/02/29/2321-157183751_large.mp4", "Unknown", "Matrix computer screen characters"),
    ("golden_particles_48569.mp4", "https://cdn.pixabay.com/video/2020/08/30/48569-454825064_large.mp4", "Unknown", "Golden particles overlay decoration"),
]

for name, url, creator, desc in PIXABAY_ASSETS:
    rec = download(name, url, "Pixabay", "Pixabay Content License (free for commercial use)", creator=creator, description=desc)
    if rec and rec not in MANIFEST:
        pass  # already added inside download()

# Also try to find more Pexels videos via different approach
print("\nTrying additional sources...")

# Try Mixkit restricted (free for personal use) - we'll note license
# Mixkit's colorful data scrolling (personal use only)
download(
    "colorful_data_scrolling.mp4",
    "https://assets.mixkit.co/videos/21053/21053-720.mp4",  # This may not work directly
    "Mixkit",
    "Mixkit Restricted License (personal use only - NOT for commercial ads)",
    contributor="Baldasaridstock",
    note="RESTRICTED: personal use only, excluded from commercial advertisement unless upgraded"
)

# Save manifest
manifest_path = OUT / "manifest.json"
existing = []
if manifest_path.exists():
    existing = json.loads(manifest_path.read_text())
    # Merge: add new entries not already in existing by sha256
    existing_shas = {r["sha256"] for r in existing}
    for r in MANIFEST:
        if r["sha256"] not in existing_shas:
            existing.append(r)
else:
    existing = MANIFEST

with open(manifest_path, "w") as f:
    json.dump(existing, f, indent=2)

print(f"\nManifest: {len(existing)} total assets recorded.")
print(f"Commercial-use ready: {sum(1 for r in existing if 'Restricted' not in r.get('license', '') and 'personal' not in r.get('license', '').lower())}")
