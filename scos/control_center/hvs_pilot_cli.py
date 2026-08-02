"""Server-only CLI entrypoints for the R2.1 paid-pilot admission + readiness boundaries.

Three subcommands:
  admit-packet        -> hvs_pilot_packet_admission.admit_packet
  render-readiness    -> hvs_pilot_render_readiness.evaluate_render_readiness

All roots/environment come from the server (env or explicit server args). The
browser never supplies filesystem paths to these commands.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .hvs_pilot_packet_admission import admit_packet
from .hvs_pilot_render_readiness import evaluate_render_readiness
from .hvs_pilot_canonical_create import create_canonical_project


def _read_payload() -> dict:
    raw = sys.stdin.read()
    return json.loads(raw) if raw.strip() else {}


def cmd_admit(args: dict) -> dict:
    expected = str(args.get("expected_sha256") or "")
    res = admit_packet(
        packet_path=args.get("packet_path"),
        approved_input_root=str(args.get("approved_input_root") or ""),
        admission_store_path=str(args.get("admission_store_path") or ""),
        audit_store_path=str(args.get("audit_store_path") or ""),
        expected_sha256=expected,
    )
    return res.to_response()


def cmd_render_readiness(args: dict) -> dict:
    res = evaluate_render_readiness(
        admission_store_path=str(args.get("admission_store_path") or ""),
        materialization_store_path=str(args.get("materialization_store_path") or ""),
        hvs_projects_root=str(args.get("hvs_projects_root") or ""),
        output_root=str(args.get("output_root") or ""),
        canonical_internal_project_id=str(args.get("canonical_internal_project_id") or ""),
        external_project_ref=str(args.get("external_project_ref") or ""),
    )
    return res.to_response()


def cmd_create_canonical(args: dict) -> dict:
    res = create_canonical_project(
        admission_store_path=str(args.get("admission_store_path") or ""),
        identity_store_path=str(args.get("identity_store_path") or ""),
        materialization_store_path=str(args.get("materialization_store_path") or ""),
        hvs_projects_root=str(args.get("hvs_projects_root") or ""),
        output_root=str(args.get("output_root") or ""),
        contracts_dir=str(args.get("contracts_dir") or ""),
        packet_path=str(args.get("packet_path") or ""),
        idempotency_key=str(args.get("idempotency_key") or ""),
    )
    return res


_COMMANDS = {"admit-packet": cmd_admit, "render-readiness": cmd_render_readiness,
             "create-canonical-project": cmd_create_canonical}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(json.dumps({"ok": False, "error_code": "NO_COMMAND"}))
        return 2
    command = argv[0]
    handler = _COMMANDS.get(command)
    if handler is None:
        print(json.dumps({"ok": False, "error_code": "UNKNOWN_COMMAND", "detail": command}))
        return 2
    try:
        payload = _read_payload()
    except Exception as e:
        print(json.dumps({"ok": False, "error_code": "INPUT_MALFORMED", "detail": str(e)}))
        return 2
    try:
        out = handler(payload)
    except Exception as e:
        print(json.dumps({"ok": False, "error_code": "BRIDGE_ERROR", "detail": type(e).__name__}))
        return 1
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
