"""SCOS Control Center truth gate — backend/currentness qualification only.

The legacy local frontend has been retired. The authoritative Control Center
backend projection remains in scos/control_center/control_center_snapshot.py.
This gate verifies that the read-only projection contract is present, produces
truthful state semantics, and does not leak unsafe fields.

Exit 0 = PASS, 1 = FAIL, 2 = preflight error.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_ALLOWED = {"AVAILABLE_WITH_DATA", "AVAILABLE_EMPTY", "UNAVAILABLE", "DEGRADED", "ERROR"}
_REQUIRED = {
    "schema_version",
    "snapshot_id",
    "generated_at",
    "source_mode",
    "health",
    "queue_summary",
    "approval_summary",
    "project_summary",
    "evidence_summary",
    "recent_activity",
    "degradation_reasons",
}

def main() -> int:
    source = _ROOT / "scos" / "control_center" / "control_center_snapshot.py"
    if not source.is_file():
        print("CONTROL CENTER TRUTH GATE: BLOCKED — source projection missing")
        return 2

    text = source.read_text(encoding="utf-8")
    required_markers = [
        "SOURCE_MODE = \"LIVE_LOCAL_READ_ONLY\"",
        "STATUS_AVAILABLE_WITH_DATA",
        "STATUS_AVAILABLE_EMPTY",
        "STATUS_UNAVAILABLE",
        "def build_control_center_snapshot",
    ]
    missing = [m for m in required_markers if m not in text]
    if missing:
        print("CONTROL CENTER TRUTH GATE: FAIL — missing source markers")
        for item in missing:
            print(f"  missing: {item}")
        return 1

    try:
        sys.path.insert(0, str(_ROOT))
        from scos.control_center.control_center_snapshot import build_control_center_snapshot

        checked_at = datetime.now(timezone.utc).isoformat()
        snapshot = build_control_center_snapshot(
            repo_root=str(_ROOT),
            checked_at=checked_at,
        )
    except Exception as exc:
        print(f"CONTROL CENTER TRUTH GATE: FAIL — projection execution error: {type(exc).__name__}")
        return 1

    missing_keys = sorted(_REQUIRED - set(snapshot))
    if missing_keys:
        print("CONTROL CENTER TRUTH GATE: FAIL — required keys missing")
        for item in missing_keys:
            print(f"  missing key: {item}")
        return 1

    if snapshot.get("source_mode") != "LIVE_LOCAL_READ_ONLY":
        print("CONTROL CENTER TRUTH GATE: FAIL — unexpected source_mode")
        return 1

    failures = []
    for section_name in (
        "health",
        "queue_summary",
        "approval_summary",
        "project_summary",
        "evidence_summary",
        "recent_activity",
    ):
        section = snapshot.get(section_name)
        if not isinstance(section, dict):
            failures.append(f"{section_name}:not_object")
            continue
        status = section.get("status")
        available = section.get("available")
        data = section.get("data")
        reason = section.get("reason_code")
        if status not in _ALLOWED:
            failures.append(f"{section_name}:invalid_status:{status}")
        if status == "AVAILABLE_EMPTY" and available is not True:
            failures.append(f"{section_name}:empty_without_available")
        if status == "UNAVAILABLE" and data is not None:
            failures.append(f"{section_name}:unavailable_with_data")
        if status == "AVAILABLE_EMPTY" and reason not in {"READ_SOURCE_EMPTY", None}:
            failures.append(f"{section_name}:unexpected_empty_reason:{reason}")

    raw = json.dumps(snapshot, ensure_ascii=False)
    for forbidden in ("authorization_token", "access_token", "client_secret", "password", "private_key"):
        if forbidden in raw:
            failures.append(f"unsafe_field:{forbidden}")

    if failures:
        print("CONTROL CENTER TRUTH GATE: FAIL")
        for item in failures:
            print(f"  {item}")
        return 1

    print("CONTROL CENTER TRUTH GATE: PASS")
    print(f"  source_mode : {snapshot['source_mode']}")
    print(f"  snapshot_id : {snapshot['snapshot_id']}")
    print(f"  observed_at : {snapshot['generated_at']}")
    print(f"  schema      : {snapshot['schema_version']}")
    print(f"  degradation : {snapshot.get('degradation_reasons', [])}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
