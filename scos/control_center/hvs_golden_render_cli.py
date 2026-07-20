"""Cohort 10G — bounded Python service bridge for the golden render matrix.

This is the SINGLE production entrypoint the Next.js golden-render route
calls via a child_process bridge. It owns NO browser-facing logic and NO
authorization decisions of its own: the authoritative orchestration
(authorization gate, single real HVS render, QA, persistence, delivery) is
delegated to :mod:`scos.control_center.hvs_golden_render_service`.

Mandated transport contract (mirrors hvs_render_cli.py):
  * spawn python -m scos.control_center.hvs_golden_render_cli <op>;
  * request data on stdin as bounded JSON;
  * exactly one structured JSON response on stdout;
  * malformed / empty / oversized output => failure;
  * raw stderr / stack traces / local paths are NEVER returned.

Operations:
  * projection  -> current golden-render truth state for a project;
  * execute     -> operator-authorized single real HVS render + QA + persist;
  * reconcile   -> read-only reconciliation (never rerenders / mutates HVS).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from scos.control_center.hvs_golden_render_models import (
    SUPPORTED_PROFILE_IDS,
    get_profile,
)
from scos.control_center.hvs_golden_render_service import (
    GoldenRenderStore,
    build_delivery_package,
    execute_golden_render,
    resolve_hyperframes_bin_dir,
)


def _emit(obj: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False))
    sys.stdout.flush()


def _read_request() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    return json.loads(raw)


def _require_field(args: dict[str, Any], name: str, pattern: str | None = None) -> str | None:
    val = str(args.get(name) or "")
    if not val:
        return None
    if pattern and __import__("re").fullmatch(pattern, val) is None:
        return None
    return val


def op_projection(args: dict[str, Any]) -> dict[str, Any]:
    project_id = _require_field(args, "project_id", r"^coh10g_[vsl]$")
    if not project_id:
        return {"ok": False, "error_code": "REQUEST_MALFORMED", "detail": "invalid project_id"}
    hvs_pid = _require_field(args, "hvs_project_id", r"^[a-f0-9]{12}$")
    if not hvs_pid:
        return {"ok": False, "error_code": "REQUEST_MALFORMED", "detail": "invalid hvs_project_id"}
    store_path = args.get("store_path")
    store = GoldenRenderStore(store_path=store_path)
    attempts = [a.to_dict() for a in store.by_project(project_id)]
    profile_id = args.get("profile_id") or "vertical_9_16"
    return {
        "ok": True,
        "project_id": project_id,
        "hvs_project_id": hvs_pid,
        "profile_id": profile_id,
        "supported_profiles": list(SUPPORTED_PROFILE_IDS),
        "attempts": attempts,
    }


def op_execute(args: dict[str, Any]) -> dict[str, Any]:
    project_id = _require_field(args, "project_id", r"^coh10g_[vsl]$")
    hvs_pid = _require_field(args, "hvs_project_id", r"^[a-f0-9]{12}$")
    profile_id = _require_field(args, "profile_id", r"^(vertical_9_16|square_1_1|landscape_16_9)$")
    authorization_id = _require_field(args, "authorization_id", r"^[a-z0-9_-]{2,64}$")
    operator_id = _require_field(args, "operator_id", r"^[a-z0-9_-]{2,64}$") or "local-solo-operator"
    if not (project_id and hvs_pid and profile_id and authorization_id):
        return {"ok": False, "error_code": "REQUEST_MALFORMED", "detail": "missing required field"}
    hvs_repo_root = os.environ.get("SCOS_HVS_REPO_PATH") or args.get("hvs_repo_root") or "."
    store_path = args.get("store_path")
    store = GoldenRenderStore(store_path=store_path)
    res = execute_golden_render(
        project_id=project_id,
        hvs_project_id=hvs_pid,
        profile_id=profile_id,
        operator_id=operator_id,
        authorization_id=authorization_id,
        hvs_repo_root=hvs_repo_root,
        store=store,
        recorded_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        python_executable=os.environ.get("SCOS_PYTHON_INTERPRETER") or sys.executable,
        timeout_seconds=int(os.environ.get("SCOS_GOLDEN_RENDER_TIMEOUT", "600")),
    )
    if not res.ok or not res.attempt:
        return {
            "ok": False,
            "error_code": res.error_code or "EXECUTION_FAILED",
            "state": res.attempt.render_state if res.attempt else "RENDER_FAILED_CONFIRMED",
            "attempt": res.attempt.to_dict() if res.attempt else None,
            "qa_report": res.qa_report.to_dict() if res.qa_report else None,
        }
    qa = res.qa_report
    return {
        "ok": True,
        "state": res.attempt.render_state,
        "attempt_id": res.attempt.attempt_id,
        "artifact_id": res.attempt.artifact_id,
        "artifact_checksum": res.attempt.artifact_checksum,
        "artifact_relative_path": res.attempt.artifact_relative_path,
        "render_calls": 1,
        "hvs_calls": 2,
        "qa_overall_state": qa.overall_state if qa else None,
        "qa_report_id": qa.qa_report_id if qa else None,
        "qa_failure_codes": list(qa.failure_codes) if qa else [],
        "attempt": res.attempt.to_dict(),
        "qa_report": qa.to_dict() if qa else None,
    }


def op_reconcile(args: dict[str, Any]) -> dict[str, Any]:
    # Read-only: re-read persisted attempt state. Never rerenders / mutates.
    project_id = _require_field(args, "project_id", r"^coh10g_[vsl]$")
    if not project_id:
        return {"ok": False, "error_code": "REQUEST_MALFORMED", "detail": "invalid project_id"}
    store = GoldenRenderStore(store_path=args.get("store_path"))
    attempts = [a.to_dict() for a in store.by_project(project_id)]
    return {"ok": True, "project_id": project_id, "attempts": attempts, "mutated": False}


_OPERATIONS = {
    "projection": op_projection,
    "execute": op_execute,
    "reconcile": op_reconcile,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in _OPERATIONS:
        _emit({"ok": False, "error_code": "UNKNOWN_OPERATION", "detail": "unknown op"})
        sys.exit(2)
    operation = sys.argv[1]
    try:
        args = _read_request()
    except Exception:
        _emit({"ok": False, "error_code": "REQUEST_MALFORMED", "detail": "invalid json"})
        sys.exit(2)
    try:
        result = _OPERATIONS[operation](args)
    except Exception as exc:  # defensive: never surface raw exception text
        _emit({"ok": False, "error_code": "BRIDGE_INTERNAL", "detail": "internal error"})
        sys.exit(1)
    _emit(result)
    sys.exit(0)


if __name__ == "__main__":
    main()
