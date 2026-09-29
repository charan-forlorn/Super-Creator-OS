"""Build a customer-ready Creative Sprint offer from one verified SCOS run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scos.commercial.creative_sprint_offer import (
    DEFAULT_DELIVERY_WINDOW,
    DEFAULT_PRICE,
    build_creative_sprint_offer,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Package a verified SCOS production run as a manual Creative Sprint offer."
    )
    parser.add_argument("production_root", help="SCOS production-run directory")
    parser.add_argument("--price", default=DEFAULT_PRICE)
    parser.add_argument("--delivery-window", default=DEFAULT_DELIVERY_WINDOW)
    parser.add_argument("--no-copy", action="store_true")
    args = parser.parse_args()

    result = build_creative_sprint_offer(
        production_root=args.production_root,
        price=args.price,
        delivery_window=args.delivery_window,
        copy_artifacts=not args.no_copy,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
