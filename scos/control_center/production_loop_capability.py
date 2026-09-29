"""Deterministic SCOS production-loop closure capability.

Reconciles current task/runtime truth, seals a media artifact, stages a
content-addressed clip, records truthful telemetry state, and seals evidence.
It never publishes, calls external APIs, infers Human approval, or fabricates
observations.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CAPABILITY_ID = "scos.production-loop@1"
SCHEMA_VERSION = 1
OPEN_TELEMETRY = "OPEN_TELEMETRY_DATA_GATE"
SEALED = "SEALED"
SEALED_OPEN = "SEALED_WITH_OPEN_TELEMETRY"
BLOCKED = "BLOCKED"


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(f"path escapes repo_root: {path}") from exc


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _atomic_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + f".tmp.{os.getpid()}")
    shutil.copy2(source, tmp)
    os.replace(tmp, target)


def _run_git(repo_root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()[-400:]}")
    return proc.stdout.strip()


_GENERATED_STATUS_PREFIXES = (
    "?? evidence/production-loop/",
    "?? scos/work/",
    "?? work/",
)


def _git_truth(repo_root: Path) -> dict[str, Any]:
    head = _run_git(repo_root, "rev-parse", "HEAD")
    branch = _run_git(repo_root, "branch", "--show-current")
    raw_status = _run_git(repo_root, "status", "--porcelain=v1", "--untracked-files=all")
    status_lines = [
        line for line in raw_status.splitlines()
        if not line.startswith(_GENERATED_STATUS_PREFIXES)
    ]
    status = "\n".join(status_lines)
    return {
        "head": head,
        "branch": branch,
        "status_lines_sample": status_lines[:50],
        "status_count": len(status_lines),
        "status_truncated": len(status_lines) > 50,
        "status_sha256": _sha256_text(status),
        "ignored_generated_output_prefixes": list(_GENERATED_STATUS_PREFIXES),
    }

def _ffprobe(path: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate",
            "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {proc.stderr.strip()[-400:]}")
    data = json.loads(proc.stdout)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
    return {
        "container_duration_s": data.get("format", {}).get("duration"),
        "size_bytes": int(data.get("format", {}).get("size") or path.stat().st_size),
        "video_codec": video.get("codec_name"),
        "audio_codec": audio.get("codec_name"),
        "width": video.get("width"),
        "height": video.get("height"),
        "fps": video.get("r_frame_rate"),
        "video_streams": sum(1 for s in streams if s.get("codec_type") == "video"),
        "audio_streams": sum(1 for s in streams if s.get("codec_type") == "audio"),
    }


@dataclass(frozen=True)
class ProductionLoopRequest:
    repo_root: Path
    task_id: str
    run_id: str
    artifact_path: Path
    telemetry_export_path: Path | None = None
    telemetry_db_path: Path | None = None
    telemetry_path: Path | None = None
    evidence_path: Path | None = None
    source: str = "manual"

@dataclass(frozen=True)
class ProductionLoopResult:
    status: str
    capability_id: str
    task: dict[str, Any]
    artifact: dict[str, Any]
    staging: dict[str, Any]
    telemetry: dict[str, Any]
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "capability_id": self.capability_id,
            "task": self.task,
            "artifact": self.artifact,
            "staging": self.staging,
            "telemetry": self.telemetry,
            "evidence": self.evidence,
        }


def reconcile_task(request: ProductionLoopRequest, git_truth: dict[str, Any]) -> dict[str, Any]:
    if not request.task_id.strip():
        raise ValueError("task_id is required")
    if not request.run_id.strip():
        raise ValueError("run_id is required")
    run_root = request.repo_root / "scos" / "work" / request.run_id
    artifact = request.artifact_path.resolve()
    task_status = "RUN_FOUND" if run_root.is_dir() else "RUN_DIR_MISSING"
    if not artifact.is_file():
        raise FileNotFoundError(f"artifact missing: {artifact}")
    return {
        "task_id": request.task_id,
        "run_id": request.run_id,
        "run_root": _relative(request.repo_root, run_root) if run_root.exists() else None,
        "run_state": task_status,
        "git": git_truth,
    }


def seal_artifact(request: ProductionLoopRequest) -> dict[str, Any]:
    artifact = request.artifact_path.resolve()
    sha = _sha256(artifact)
    probe = _ffprobe(artifact)
    return {
        "path": _relative(request.repo_root, artifact),
        "sha256": sha,
        "size_bytes": artifact.stat().st_size,
        "probe": probe,
        "artifact_id": f"artifact-{sha[:16]}",
    }

def stage_clip(
    request: ProductionLoopRequest,
    artifact: dict[str, Any],
) -> dict[str, Any]:
    staged_root = request.repo_root / "scos" / "work" / "staged_clips" / request.run_id
    staged = staged_root / f"{artifact['sha256'][:16]}.mp4"
    source = request.repo_root / artifact["path"]
    action = "REUSED"
    if not staged.is_file():
        _atomic_copy(source, staged)
        action = "COPIED"
    staged_sha = _sha256(staged)
    if staged_sha != artifact["sha256"]:
        raise RuntimeError("staged clip SHA-256 mismatch")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "run_id": request.run_id,
        "artifact_id": artifact["artifact_id"],
        "source_path": artifact["path"],
        "source_sha256": artifact["sha256"],
        "staged_path": _relative(request.repo_root, staged),
        "staged_sha256": staged_sha,
        "size_bytes": staged.stat().st_size,
        "action": action,
    }
    _atomic_json(staged.with_suffix(".json"), manifest)
    return manifest


def build_telemetry_state(request: ProductionLoopRequest) -> dict[str, Any]:
    if request.telemetry_export_path is None:
        return {
            "status": OPEN_TELEMETRY,
            "reason": "NO_EXTERNAL_OBSERVATION_EXPORT",
            "learning_qualification": False,
            "receipt_path": None,
        }
    export = request.telemetry_export_path.resolve()
    if not export.is_file():
        return {
            "status": BLOCKED,
            "reason": "TELEMETRY_EXPORT_MISSING",
            "learning_qualification": False,
            "receipt_path": None,
        }
    from integrations.learning.telemetry_receipt import build_telemetry_receipt

    db_path = (
        request.telemetry_db_path.resolve()
        if request.telemetry_db_path
        else request.repo_root / "memory" / "database.json"
    )
    telemetry_path = (
        request.telemetry_path.resolve()
        if request.telemetry_path
        else request.repo_root / "memory" / "telemetry.json"
    )
    receipt_path = request.repo_root / "evidence" / "production-loop" / request.run_id / "telemetry_receipt.json"
    result = build_telemetry_receipt(
        export_path=export,
        db_path=db_path,
        telemetry_path=telemetry_path,
        receipt_path=receipt_path,
        source=request.source,
    )
    return {
        "status": result.get("status", BLOCKED),
        "reason": result.get("reason"),
        "learning_qualification": bool(result.get("learning_qualification", False)),
        "receipt_path": _relative(request.repo_root, receipt_path) if receipt_path.exists() else None,
        "receipt_id": result.get("receipt_id"),
        "export_sha256": result.get("export_sha256"),
        "joined_loop_run_ids": result.get("joined_loop_run_ids", []),
        "orphan_loop_run_ids": result.get("orphan_loop_run_ids", []),
    }

def _evidence_bundle(
    request: ProductionLoopRequest,
    task: dict[str, Any],
    artifact: dict[str, Any],
    staging: dict[str, Any],
    telemetry: dict[str, Any],
) -> dict[str, Any]:
    input_payload = {
        "capability_id": CAPABILITY_ID,
        "task_id": request.task_id,
        "run_id": request.run_id,
        "git_head": task["git"]["head"],
        "git_status_sha256": task["git"]["status_sha256"],
        "artifact_sha256": artifact["sha256"],
        "staged_sha256": staging["staged_sha256"],
        "telemetry_status": telemetry["status"],
        "telemetry_receipt_id": telemetry.get("receipt_id"),
    }
    fingerprint = _sha256_text(_stable_json(input_payload))
    status = SEALED if telemetry["status"] != OPEN_TELEMETRY else SEALED_OPEN
    payload = {
        "schema_version": SCHEMA_VERSION,
        "capability_id": CAPABILITY_ID,
        "status": status,
        "task": task,
        "artifact": artifact,
        "staging": staging,
        "telemetry": telemetry,
        "input_fingerprint": fingerprint,
        "stale_evidence_policy": "invalidate_previous_bundle_when_input_fingerprint_changes",
        "external_dispatch": False,
        "human_approval_inferred": False,
        "bundle_id": f"production-loop-{fingerprint[:16]}",
    }
    seal = _sha256_text(_stable_json(payload))
    payload["seal_sha256"] = seal
    return payload


def seal_evidence(
    request: ProductionLoopRequest,
    bundle: dict[str, Any],
) -> dict[str, Any]:
    path = (
        request.evidence_path.resolve()
        if request.evidence_path
        else request.repo_root / "evidence" / "production-loop" / request.run_id / "production_loop_evidence.json"
    )
    if path.is_file():
        previous = json.loads(path.read_text(encoding="utf-8"))
        if previous.get("seal_sha256") != bundle["seal_sha256"]:
            history = path.with_name("invalidation.jsonl")
            record = {
                "schema_version": SCHEMA_VERSION,
                "event": "STALE_EVIDENCE_INVALIDATED",
                "previous_bundle_id": previous.get("bundle_id"),
                "previous_seal_sha256": previous.get("seal_sha256"),
                "new_bundle_id": bundle["bundle_id"],
                "new_input_fingerprint": bundle["input_fingerprint"],
            }
            with history.open("a", encoding="utf-8") as handle:
                handle.write(_stable_json(record) + "\n")
    _atomic_json(path, bundle)
    written = json.loads(path.read_text(encoding="utf-8"))
    if written.get("seal_sha256") != bundle["seal_sha256"]:
        raise RuntimeError("evidence seal verification failed")
    return {
        "path": _relative(request.repo_root, path),
        "bundle_id": bundle["bundle_id"],
        "seal_sha256": bundle["seal_sha256"],
        "status": bundle["status"],
        "invalidation_log": (
            _relative(request.repo_root, path.with_name("invalidation.jsonl"))
            if path.with_name("invalidation.jsonl").exists()
            else None
        ),
    }

def execute_production_loop(request: ProductionLoopRequest) -> ProductionLoopResult:
    repo_root = request.repo_root.resolve()
    if not repo_root.is_dir():
        raise ValueError(f"repo_root must exist: {repo_root}")
    artifact_path = request.artifact_path.resolve()
    request = ProductionLoopRequest(
        repo_root=repo_root,
        task_id=request.task_id,
        run_id=request.run_id,
        artifact_path=artifact_path,
        telemetry_export_path=request.telemetry_export_path,
        telemetry_db_path=request.telemetry_db_path,
        telemetry_path=request.telemetry_path,
        evidence_path=request.evidence_path,
        source=request.source,
    )
    git_truth = _git_truth(repo_root)
    task = reconcile_task(request, git_truth)
    artifact = seal_artifact(request)
    staging = stage_clip(request, artifact)
    telemetry = build_telemetry_state(request)
    if telemetry["status"] == BLOCKED:
        raise RuntimeError(telemetry["reason"])
    bundle = _evidence_bundle(request, task, artifact, staging, telemetry)
    evidence = seal_evidence(request, bundle)
    status = SEALED if telemetry["status"] != OPEN_TELEMETRY else SEALED_OPEN
    return ProductionLoopResult(
        status=status,
        capability_id=CAPABILITY_ID,
        task=task,
        artifact=artifact,
        staging=staging,
        telemetry=telemetry,
        evidence=evidence,
    )


__all__ = [
    "BLOCKED",
    "CAPABILITY_ID",
    "OPEN_TELEMETRY",
    "ProductionLoopRequest",
    "ProductionLoopResult",
    "SEALED",
    "SEALED_OPEN",
    "execute_production_loop",
    "reconcile_task",
    "seal_artifact",
    "stage_clip",
    "build_telemetry_state",
    "seal_evidence",
]
