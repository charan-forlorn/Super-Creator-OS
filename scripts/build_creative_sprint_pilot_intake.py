"""Build the manual customer-input starter from a verified Creative Sprint offer."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scos.commercial.creative_sprint_pilot_intake import (
    build_creative_sprint_pilot_intake,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Turn a verified Creative Sprint offer into a manual paid-pilot intake starter."
    )
    parser.add_argument("offer_manifest")
    parser.add_argument("--output-dir")
    args = parser.parse_args()

    result = build_creative_sprint_pilot_intake(
        offer_manifest_path=args.offer_manifest,
        output_dir=args.output_dir,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
