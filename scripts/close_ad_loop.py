"""Production loop closure for the AI Automation advertisement."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path("C:/Workspace/super-creator-os")
RUN_ID = "ai-auto-ad-c1b9427f"
WORK = REPO / "scos" / "work" / RUN_ID

sys.path.insert(0, str(REPO))

from scos.control_center.production_loop_capability import (
    ProductionLoopRequest,
    execute_production_loop,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# Primary artifact
primary = WORK / "renders" / f"{RUN_ID}_final.mp4"
assert primary.is_file(), f"primary artifact missing: {primary}"

print(f"Artifact: {primary}")
print(f"SHA256: {sha256(primary)}")

# Build production loop request
request = ProductionLoopRequest(
    repo_root=REPO,
    task_id=f"task-{RUN_ID}",
    run_id=RUN_ID,
    artifact_path=primary,
)

# Execute production loop closure
result = execute_production_loop(request)

print(f"\nProduction Loop Status: {result.status}")
print(f"Capability: {result.capability_id}")
print(f"Task: {result.task['task_id']}")
print(f"Artifact ID: {result.artifact['artifact_id']}")
print(f"Staging: {result.staging['staged_path']} ({result.staging['action']})")
print(f"Telemetry: {result.telemetry['status']}")
print(f"Evidence: {result.evidence['path']}")
print(f"Bundle ID: {result.evidence['bundle_id']}")
print(f"Seal SHA256: {result.evidence['seal_sha256'][:32]}...")

# Save receipt
receipt_path = WORK / "evidence" / "production_loop_receipt.json"
receipt_path.parent.mkdir(parents=True, exist_ok=True)
with open(receipt_path, "w") as f:
    json.dump(result.to_dict(), f, indent=2)

print(f"\nReceipt saved: {receipt_path}")

# Also update main manifest with closure
manifest_path = WORK / "manifest.json"
manifest = json.loads(manifest_path.read_text())
manifest["production_loop"] = {
    "status": result.status,
    "bundle_id": result.evidence["bundle_id"],
    "seal_sha256": result.evidence["seal_sha256"],
    "artifact_id": result.artifact["artifact_id"],
    "staged": result.staging["action"],
    "telemetry_status": result.telemetry["status"],
}
manifest["final_sha256"] = sha256(primary)

with open(manifest_path, "w") as f:
    json.dump(manifest, f, indent=2)

print("\nProduction loop closure COMPLETE.")
