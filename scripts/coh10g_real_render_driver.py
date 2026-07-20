"""Cohort 10G — real 3-profile golden render driver (isolated).

Drives execute_golden_render for vertical/square/landscape against the
isolated HVS copy at C:/Users/chara/AppData/Local/Temp/hvs_iso. Concurrency
is 1 (each project rendered fully before the next begins). Writes a JSON
evidence ledger to the isolated evidence root.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(r"C:\Workspace\super-creator-os")
sys.path.insert(0, str(REPO))

from scos.control_center.hvs_golden_render_service import (
    GoldenRenderStore,
    execute_golden_render,
)

ISO = Path(r"C:\Users\chara\AppData\Local\Temp\hvs_iso")
EVIDENCE = Path(r"C:\Users\chara\AppData\Local\Temp\coh10g_evidence")
EVIDENCE.mkdir(parents=True, exist_ok=True)

PROJECTS = [
    ("coh10g_v", "46a92c8eab20", "vertical_9_16", "operator_nut", "az_v_001"),
    ("coh10g_s", "8f2cc25e260d", "square_1_1", "operator_nut", "az_s_001"),
    ("coh10g_l", "baa42da1063c", "landscape_16_9", "operator_nut", "az_l_001"),
]

STORE = GoldenRenderStore(store_path=str(EVIDENCE / "golden_render_attempts.jsonl"))


def main() -> None:
    ledger = {"started_at": datetime.now(timezone.utc).isoformat(), "renders": []}
    for project_id, hvs_pid, profile, op, az in PROJECTS:
        recorded = datetime.now(timezone.utc).isoformat()
        res = execute_golden_render(
            project_id=project_id,
            hvs_project_id=hvs_pid,
            profile_id=profile,
            operator_id=op,
            authorization_id=az,
            hvs_repo_root=str(ISO),
            store=STORE,
            recorded_at=recorded,
            python_executable="python",
            timeout_seconds=600,
        )
        entry = {
            "project_id": project_id,
            "hvs_project_id": hvs_pid,
            "profile_id": profile,
            "ok": res.ok,
            "error_code": res.error_code,
            "attempt": res.attempt.to_dict() if res.attempt else None,
            "qa_overall_state": res.qa_report.overall_state if res.qa_report else None,
            "qa_report_id": res.qa_report.qa_report_id if res.qa_report else None,
            "qa_failure_codes": list(res.qa_report.failure_codes) if res.qa_report else None,
        }
        # Persist the QA report JSON for evidence.
        if res.qa_report:
            (EVIDENCE / f"qa_{profile}.json").write_text(
                json.dumps(res.qa_report.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        ledger["renders"].append(entry)
        print(f"[{profile}] ok={res.ok} state={entry['attempt']['render_state'] if entry['attempt'] else None} qa={entry['qa_overall_state']}", flush=True)
    ledger["completed_at"] = datetime.now(timezone.utc).isoformat()
    (EVIDENCE / "ledger.json").write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("LEDGER_WRITTEN", flush=True)


if __name__ == "__main__":
    main()
