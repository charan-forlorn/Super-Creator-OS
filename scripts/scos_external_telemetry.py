"""SCOS external platform telemetry activation CLI.

Read-only external observation path. It never publishes, dispatches, stores OAuth
secrets, or marks Human approval. Currently implements YouTube Analytics v2.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from integrations.learning.telemetry_receipt import build_telemetry_receipt
from integrations.learning.youtube_oauth_store import DEFAULT_STORE, credential_exists
from integrations.learning.youtube_api_telemetry import (
    YouTubeAnalyticsClient,
    YouTubeAnalyticsRequest,
    YouTubeObservationTarget,
    YouTubeObservedTelemetryAdapter,
)


def _load_targets(path: Path) -> tuple[YouTubeObservationTarget, ...]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("targets") if isinstance(data, dict) else data
    if not isinstance(rows, list) or not rows:
        raise ValueError("targets JSON must contain a non-empty list")
    out = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("each target must be an object")
        out.append(YouTubeObservationTarget(
            video_id=str(row.get("video_id") or "").strip(),
            loop_run_id=str(row.get("loop_run_id") or "").strip(),
            project_name=str(row.get("project_name") or "").strip(),
        ))
    if any(not x.video_id or not x.loop_run_id or not x.project_name for x in out):
        raise ValueError("each target requires video_id, loop_run_id, project_name")
    return tuple(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="SCOS read-only external platform telemetry")
    ap.add_argument("--platform", default="youtube_shorts", choices=["youtube_shorts"])
    ap.add_argument("--channel-id", required=True)
    ap.add_argument("--start-date", required=True)
    ap.add_argument("--end-date", required=True)
    ap.add_argument("--targets", required=True, help="JSON file with video_id/loop_run_id/project_name")
    ap.add_argument("--access-token-env", default="SCOS_YOUTUBE_ANALYTICS_ACCESS_TOKEN")
    ap.add_argument("--oauth-store", default=str(DEFAULT_STORE))
    ap.add_argument("--export-snapshot", required=True, help="JSON snapshot of measured API observations")
    ap.add_argument("--telemetry", default=None)
    ap.add_argument("--db", default=None)
    ap.add_argument("--receipt", default=None)
    ap.add_argument("--collected-at", default=None)
    args = ap.parse_args()

    token = os.environ.get(args.access_token_env, "").strip()
    credential_source = "environment"
    if token:
        client = YouTubeAnalyticsClient(token)
    elif credential_exists(args.oauth_store):
        credential_source = "encrypted_dpapi_store"
        client = YouTubeAnalyticsClient.from_secure_store(args.oauth_store)
    else:
        print(json.dumps({
            "status": "BLOCKED",
            "reason": "YOUTUBE_ANALYTICS_AUTH_REQUIRED",
            "platform": args.platform,
            "access_token_env": args.access_token_env,
            "oauth_store": args.oauth_store,
            "credential_source": "none",
            "secret_material_read": False,
            "publish_or_dispatch_performed": False,
            "human_approval_inferred": False,
        }, ensure_ascii=False, indent=2))
        return 2

    targets = _load_targets(Path(args.targets))
    adapter = YouTubeObservedTelemetryAdapter(client)
    request = YouTubeAnalyticsRequest(
        channel_id=args.channel_id,
        start_date=args.start_date,
        end_date=args.end_date,
        video_ids=tuple(x.video_id for x in targets),
    )
    rows = client.query_rows(request)
    observations = adapter.build_observations(rows, targets, collected_at=args.collected_at)
    export_snapshot = Path(args.export_snapshot)
    export_snapshot.parent.mkdir(parents=True, exist_ok=True)
    export_snapshot.write_text(json.dumps(observations, ensure_ascii=False, indent=2), encoding="utf-8")
    receipt = None
    if args.receipt or args.db or args.telemetry:
        if not (args.receipt and args.db and args.telemetry):
            raise SystemExit("--receipt, --db, and --telemetry must be supplied together")
        receipt = build_telemetry_receipt(
            export_path=export_snapshot,
            db_path=args.db,
            telemetry_path=args.telemetry,
            receipt_path=args.receipt,
            source="api",
        )
    status = receipt.get("status") if receipt else ("OBSERVATIONS_EXPORTED" if observations else "BLOCKED")
    print(json.dumps({
        "status": status,
        "platform": args.platform,
        "rows_received": len(rows),
        "observations_built": len(observations),
        "credential_source": credential_source,
        "export_snapshot": str(export_snapshot),
        "receipt_status": receipt.get("status") if receipt else None,
        "receipt_path": args.receipt if receipt else None,
        "publish_or_dispatch_performed": False,
        "human_approval_inferred": False,
    }, ensure_ascii=False, indent=2))
    return 0 if observations and (receipt is None or receipt.get("status") in {"OBSERVATIONS_JOINED", "ORPHAN_OBSERVATIONS"}) else 1


if __name__ == "__main__":
    raise SystemExit(main())
