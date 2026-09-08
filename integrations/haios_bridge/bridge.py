from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

CONTRACT = "HAIOS_SCOS_CREATIVE_JOB_V1"
SCHEMA_VERSION = 1
_ALLOWED_MODES = frozenset({"dry_run", "local"})
_REQUIRED = (
    "schema_version", "contract", "goal_id", "job_id", "project_id", "capability",
    "goal_text", "acceptance_criteria", "requested_at", "workspace", "input_artifacts",
    "execution_mode",
)


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _root(raw: str) -> Path:
    return Path(raw).expanduser().resolve(strict=False)


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _validate_request(request: dict[str, Any]) -> tuple[str, ...]:
    if not isinstance(request, dict):
        return ("REQUEST_OBJECT_REQUIRED",)
    issues = [f"MISSING_{name.upper()}" for name in _REQUIRED if name not in request]
    if issues:
        return tuple(issues)
    if request["schema_version"] != SCHEMA_VERSION:
        issues.append("REQUEST_SCHEMA_VERSION_UNSUPPORTED")
    if request["contract"] != CONTRACT:
        issues.append("REQUEST_CONTRACT_MISMATCH")
    if request["execution_mode"] not in _ALLOWED_MODES:
        issues.append("EXECUTION_MODE_UNSUPPORTED")
    root = _root(request["workspace"])
    for key, raw in request.get("input_artifacts", []):
        path = _root(raw)
        if "://" in str(raw):
            issues.append("INPUT_ARTIFACT_URL_REJECTED")
        elif not _inside(path, root):
            issues.append("INPUT_ARTIFACT_OUT_OF_BOUNDS")
    return tuple(issues)


def _run_pipeline(prompt: str) -> dict[str, Any]:
    from scos.core.orchestrator import run_pipeline
    return run_pipeline(prompt)


def _artifact_record(path: Path, root: Path) -> dict[str, Any] | None:
    if not path.is_file() or not _inside(path.resolve(), root):
        return None
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "kind": path.suffix.lower().lstrip(".") or "file",
        "role": "primary_output",
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": digest,
    }


def run_bridge(request: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    problems = _validate_request(request)
    if problems:
        return {
            "schema_version": SCHEMA_VERSION,
            "contract": CONTRACT,
            "goal_id": request.get("goal_id", ""),
            "job_id": request.get("job_id", ""),
            "project_id": request.get("project_id", ""),
            "status": "BLOCKED",
            "execution_trace": [],
            "artifacts": [],
            "qa": {"status": "NOT_RUN"},
            "learning_events": [],
            "provenance": {"execution": "dry_run" if dry_run else "local", "reason": "REQUEST_REJECTED"},
        }
    root = _root(request["workspace"])
    if dry_run or request["execution_mode"] == "dry_run":
        return {
            "schema_version": SCHEMA_VERSION,
            "contract": CONTRACT,
            "goal_id": request["goal_id"],
            "job_id": request["job_id"],
            "project_id": request["project_id"],
            "status": "BLOCKED",
            "execution_trace": [{"stage": "admission", "status": "validated"}],
            "artifacts": [],
            "qa": {"status": "NOT_RUN"},
            "learning_events": [],
            "provenance": {"execution": "dry_run", "reason": "DRY_RUN_NO_EXECUTION"},
        }
    raw = _run_pipeline(request["goal_text"])
    artifacts: list[dict[str, Any]] = []
    output = raw.get("video_path")
    if output:
        record = _artifact_record(Path(output), root)
        if record is None:
            return {
                "schema_version": SCHEMA_VERSION, "contract": CONTRACT,
                "goal_id": request["goal_id"], "job_id": request["job_id"],
                "project_id": request["project_id"], "status": "BLOCKED",
                "execution_trace": raw.get("execution_trace", []), "artifacts": [],
                "qa": raw.get("qa_report") or {"status": "UNKNOWN"},
                "learning_events": [],
                "provenance": {"execution": "local", "reason": "OUTPUT_OUT_OF_BOUNDS"},
            }
        artifacts.append(record)
    pipeline_status = raw.get("status")
    qa = raw.get("qa_report") or {"status": "UNKNOWN"}
    status = "SUCCEEDED" if pipeline_status == "success" and artifacts else "FAILED"
    return {
        "schema_version": SCHEMA_VERSION,
        "contract": CONTRACT,
        "goal_id": request["goal_id"],
        "job_id": request["job_id"],
        "project_id": request["project_id"],
        "status": status,
        "execution_trace": raw.get("execution_trace", []),
        "artifacts": artifacts,
        "qa": qa,
        "learning_events": [],
        "provenance": {
            "execution": "local",
            "pipeline_status": pipeline_status,
            "contract_digest": hashlib.sha256(_canon(request).encode()).hexdigest(),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--mode", choices=tuple(_ALLOWED_MODES), required=True)
    args = parser.parse_args()
    request_path = Path(args.request).resolve()
    result_path = Path(args.result).resolve()
    request = json.loads(request_path.read_text(encoding="utf-8"))
    result = run_bridge(request, dry_run=args.mode == "dry_run")
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0 if result["status"] in {"SUCCEEDED", "BLOCKED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
