"""Incrementally index local media into the canonical Premium Media AssetRegistry."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scos.premium_media.asset_intelligence import LocalAssetIndexer
from scos.premium_media.rights import AssetRegistry


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", action="append", required=True, type=Path)
    ap.add_argument("--registry", type=Path, required=True)
    args = ap.parse_args()
    report = LocalAssetIndexer(AssetRegistry(args.registry)).refresh(args.root)
    print(json.dumps({
        "registry_path": str(report.registry_path.resolve()),
        "scanned": report.scanned,
        "indexed": report.indexed,
        "reused": report.reused,
        "deduplicated": report.deduplicated,
        "skipped": report.skipped,
        "rights_sidecars": report.rights_sidecars,
        "errors": list(report.errors),
    }, ensure_ascii=False, indent=2))
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
