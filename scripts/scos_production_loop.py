"""Hermes-facing CLI for the deterministic SCOS production-loop capability."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scos.control_center.production_loop_capability import (
    ProductionLoopRequest,
    execute_production_loop,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reconcile, seal, stage, observe, and evidence one SCOS production run."
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--telemetry-export")
    parser.add_argument("--telemetry-db")
    parser.add_argument("--telemetry-path")
    parser.add_argument("--evidence-path")
    parser.add_argument("--source", choices=("manual", "api"), default="manual")
    return parser

def main() -> int:
    args = build_parser().parse_args()
    root = Path(args.repo_root).resolve()

    request = ProductionLoopRequest(
        repo_root=root,
        task_id=args.task_id,
        run_id=args.run_id,
        artifact_path=(root / args.artifact).resolve()
        if not Path(args.artifact).is_absolute()
        else Path(args.artifact).resolve(),
        telemetry_export_path=(
            (root / args.telemetry_export).resolve()
            if args.telemetry_export and not Path(args.telemetry_export).is_absolute()
            else Path(args.telemetry_export).resolve()
            if args.telemetry_export
            else None
        ),
        telemetry_db_path=(
            (root / args.telemetry_db).resolve()
            if args.telemetry_db and not Path(args.telemetry_db).is_absolute()
            else Path(args.telemetry_db).resolve()
            if args.telemetry_db
            else None
        ),
        telemetry_path=(
            (root / args.telemetry_path).resolve()
            if args.telemetry_path and not Path(args.telemetry_path).is_absolute()
            else Path(args.telemetry_path).resolve()
            if args.telemetry_path
            else None
        ),
        evidence_path=(
            (root / args.evidence_path).resolve()
            if args.evidence_path and not Path(args.evidence_path).is_absolute()
            else Path(args.evidence_path).resolve()
            if args.evidence_path
            else None
        ),
        source=args.source,
    )
    try:
        result = execute_production_loop(request)
    except Exception as exc:
        print(json.dumps(
            {"status": "BLOCKED", "error": f"{type(exc).__name__}: {exc}"},
            ensure_ascii=False,
            indent=2,
        ))
        return 1
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
