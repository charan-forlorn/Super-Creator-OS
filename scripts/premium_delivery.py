"""Render a platform delivery artifact from a sealed Premium Media master."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scos.premium_media.delivery import DELIVERY_PROFILES, delivery_manifest
from scos.premium_media.delivery_render import render_delivery, DeliveryRenderError


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", type=Path, required=True)
    ap.add_argument("--profile", choices=sorted(DELIVERY_PROFILES), required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--print-registry", action="store_true")
    args = ap.parse_args()
    if args.print_registry:
        print(json.dumps(delivery_manifest([args.profile]), ensure_ascii=False, indent=2))
    try:
        result = render_delivery(args.master, args.output, args.profile)
    except DeliveryRenderError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
