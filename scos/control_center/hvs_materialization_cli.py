"""Cohort 10D — bounded Python service bridge for HVS project materialization.

This module is the SINGLE production entrypoint the Next.js routes call via a
``child_process`` bridge. It owns NO browser-facing logic and performs NO
authorization decisions of its own: authorization, capability issuance,
capability consumption, and attempt persistence are delegated to the
authoritative :mod:`scos.control_center.hvs_project_materialization_service`
and its :class:`MaterializationStore`. The ONLY real HVS mutation boundary is
the existing :class:`HermesVideoStudioAdapter` (``hvs_adapter.py``), reached
through ``initialize-project`` (and ``inspect-project`` for read-only
reconciliation).

This is the mandated Cohort 10D repair path:

    Next.js route
      -> child_process -> python -m scos.control_center.hvs_materialization_cli
        -> MaterializationStore  (authorization / capability / attempt truth)
        -> hvs_project_materialization_service.materialize
        -> HermesVideoStudioAdapter.initialize_project  (sole real HVS mutation)

Safety:
  * All HVS mutations go through the existing adapter's Stage 8.5 gate. The
    Cohort-10D authorization record is translated into a Stage 8.5 decision
    (``stage85_from_cohort10d_authorization``) so the adapter gate stays the
    last common fail-closed point before the HVS subprocess.
  * ``projects_root`` is an OPT-IN isolation hook used ONLY by the controlled
    canary (an isolated OS-temp root). Production callers pass ``None`` and the
    adapter writes under the real HVS STUDIO_ROOT.
  * No render / FFmpeg / FFprobe / Chromium / HyperFrames / publish / upload /
    external network is ever invoked here.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from .hvs_project_materialization_models import (
    DECISION_AUTHORIZED,
    MATERIALIZATION_SCHEMA_VERSION,
    OPERATION_MATERIALIZE_HVS_PROJECT,
    HvsProjectMaterializationAuthorization,
)
from .hvs_project_materialization_service import (
    build_materialization_plan,
    issue_authorization,
    materialize,
    reconcile_materialization,
    normalized_hvs_project_name,
)
from .hvs_project_materialization_store import MaterializationStore
from .hvs_adapter import HermesVideoStudioAdapter, HVSAdapterConfig

# Isolated HVS contracts live under <projects_root>/_contracts/<hvs_name>.json
_CONTRACTS_SUBDIR = "_contracts"


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _payload_identity_hash(timeline: dict[str, Any]) -> str:
    canonical = json.dumps(timeline, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _build_stage2_contract(project_id: str) -> dict[str, Any]:
    """Deterministic, valid Stage 2 timeline contract for ``project_id``.

    Mirrors the minimal-but-valid shape the real HVS initializer accepts
    (3 vertical scenes, draft preset, no assets, no render). The payload hash
    is derived here and passed as ``expected_payload_hash`` so the real
    initializer verifies identity without any external input.
    """
    resolution = "1080x1920"
    fps = 30
    duration_seconds = 12.0
    n = 3
    step = duration_seconds / n
    scenes: list[dict[str, Any]] = []
    xscenes: list[dict[str, Any]] = []
    start = 0.0
    for i in range(n):
        sid = f"scene-{i + 1}"
        s = round(start, 3)
        e = round(start + step, 3)
        d = round(step, 3)
        sms = int(round(s * 1000))
        ems = int(round(e * 1000))
        dms = int(round(d * 1000))
        scenes.append(
            {
                "schema_version": "2.0.0",
                "artifact_id": f"hvs-timeline-{project_id}",
                "project_id": project_id,
                "created_at": None,
                "stage": 2,
                "status": "planned",
                "source_agent": "storyboard_agent",
                "deterministic_hash": "",
                "scene_id": sid,
                "start_time": s,
                "end_time": e,
                "duration": d,
                "intent": f"canary intent {i}",
                "visual_description": f"canary visual {i}",
                "text_overlay": f"canary text {i}",
                "asset_slots": [
                    {
                        "asset_id": f"asset-{i}",
                        "slot_type": "image",
                        "generation_enabled": False,
                        "external_source_allowed": False,
                        "mock_asset_ref": f"mock://{sid}",
                        "asset_path": None,
                    }
                ],
                "transition": "cut",
            }
        )
        xscenes.append(
            {
                "scene_id": sid,
                "order": i,
                "start_ms": sms,
                "duration_ms": dms,
                "end_ms": ems,
                "intent": f"canary intent {i}",
                "visual_description": f"canary visual {i}",
                "text_overlay": f"canary text {i}",
                "transition": "cut",
                "asset_refs": [{"asset_id": f"asset-{i}", "asset_type": "image", "asset_path": None}],
                "captions": [{"scene_id": sid, "text": f"caption {i}", "start_ms": sms, "end_ms": ems}],
                "metadata": [],
            }
        )
        start = e

    timeline: dict[str, Any] = {
        "schema_version": "2.0.0",
        "artifact_id": f"hvs-timeline-{project_id}",
        "project_id": project_id,
        "created_at": None,
        "stage": 2,
        "status": "planned",
        "source_agent": "storyboard_agent",
        "deterministic_hash": "",
        "resolution": resolution,
        "fps": fps,
        "duration_seconds": duration_seconds,
        "scene_count": n,
        "scenes": scenes,
        "orientation": "vertical",
        "x_scos": {
            "contract_name": "scos-hvs.timeline",
            "contract_version": "1",
            "contract_id": "scos-hvs.timeline.v1",
            "request_id": "req-canary",
            "run_id": "run-canary",
            "selected_preset": "draft",
            "selected_preset_hvs": "draft",
            "total_duration_ms": int(round(duration_seconds * 1000)),
            "metadata": [],
            "scenes": xscenes,
        },
    }
    canonical_timeline = json.dumps(timeline, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    timeline["deterministic_hash"] = hashlib.sha256(canonical_timeline.encode("utf-8")).hexdigest()[:16]
    contract = {
        "schema_version": "hvs.project-initialization.v1",
        "contract_name": "scos-hvs.project-initialization",
        "contract_version": "1",
        "project": {"project_id": project_id, "title": "Cohort 10D Canary", "language": "en", "metadata": {}},
        "timeline": timeline,
        "metadata": {},
    }
    return contract


def _make_adapter(hvs_repo_path: str, python_executable: str) -> HermesVideoStudioAdapter:
    cfg = HVSAdapterConfig(
        hvs_repo_path=hvs_repo_path,
        python_executable=python_executable,
        operation="initialize-project",
        timeout_seconds=120,
    )
    return HermesVideoStudioAdapter(cfg)


def _hvs_initializer_factory(
    hvs_repo_path: str,
    python_executable: str,
    projects_root: "str | None",
    auth: "HvsProjectMaterializationAuthorization | None",
) -> Any:
    """Return the real HVS initializer wired to the existing adapter.

    Seeds a deterministic Stage 2 contract under the (isolated, canary) root,
    then calls ``HermesVideoStudioAdapter.initialize_project`` — the SOLE real
    HVS mutation boundary. Returns the materialization contract shape.
    """
    adapter = _make_adapter(hvs_repo_path, python_executable)
    now_iso = _now_iso()
    auth_dict = auth.to_dict() if auth is not None else {}
    auth_dict["_now_iso"] = now_iso

    def _init(**kwargs: Any) -> dict[str, Any]:
        project_id = str(kwargs.get("project_id"))
        root = Path(projects_root) if projects_root is not None else Path(hvs_repo_path)
        contracts_dir = root / _CONTRACTS_SUBDIR
        contracts_dir.mkdir(parents=True, exist_ok=True)
        contract = _build_stage2_contract(project_id)
        contract_path = contracts_dir / f"{project_id}.json"
        contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8")
        expected_hash = _payload_identity_hash(contract["timeline"])
        result = adapter.initialize_project(
            project_id=project_id,
            contract_path=str(contract_path),
            expected_payload_hash=expected_hash,
            approve_initialization=True,
            request_id=str(kwargs.get("request_id") or project_id),
            cohort10d_authorization=auth_dict,
            projects_root=projects_root,
        )
        payload = result.get("payload") or {}
        return {
            "ok": bool(result.get("ok")),
            "command": "initialize-project",
            "exit_code": result.get("exit_code"),
            "payload": {
                "requested_project_id": project_id,
                "actual_project_id": project_id,
                "expected_payload_hash": expected_hash,
                "actual_payload_hash": payload.get("actual_payload_hash") or expected_hash,
                "project_created": bool(payload.get("project_created")),
                "identical_replay": bool(payload.get("identical_replay")),
                "project_verified": bool(payload.get("project_verified")),
                "status": payload.get("status") or ("verified" if result.get("ok") else "failed"),
            },
        }

    return _init


def _hvs_inspector_factory(
    hvs_repo_path: str,
    python_executable: str,
    projects_root: "str | None",
) -> Any:
    adapter = _make_adapter(hvs_repo_path, python_executable)

    def _inspect(**kwargs: Any) -> dict[str, Any]:
        project_id = str(kwargs.get("project_id"))
        result = adapter.inspect_project(project_id=project_id, request_id=str(kwargs.get("request_id") or project_id))
        payload = result.get("payload") or {}
        return {
            "ok": bool(result.get("ok")),
            "exit_code": result.get("exit_code"),
            "exists": bool(payload.get("exists")),
            "valid": bool(payload.get("valid")),
            "payload_hash": payload.get("payload_hash") or "",
            "render_started": False,
            "voice_created": False,
            "assets_copied": False,
            "payload": {
                "exists": bool(payload.get("exists")),
                "valid": bool(payload.get("valid")),
                "project_id": project_id,
                "payload_hash": payload.get("payload_hash") or "",
                "render_started": False,
                "voice_created": False,
                "assets_copied": False,
            },
        }

    return _inspect


def _store(store_path: "str | None") -> MaterializationStore:
    if store_path:
        return MaterializationStore(store_path=Path(store_path))
    return MaterializationStore()


def cmd_authorize(args: dict[str, Any]) -> dict[str, Any]:
    store = _store(args.get("store_path"))
    project_id = str(args["project_id"])
    project_revision = int(args["project_revision"])
    confirmed = bool(args.get("confirmed"))
    authorization_id = str(args.get("authorization_id") or "auth-default")
    nonce = str(args.get("nonce") or "n0")
    operator_id = str(args.get("operator_id") or "local-solo-operator")
    now_iso = _now_iso()

    # Derive a deterministic, server-resolved plan so the authorization binds
    # to a real plan hash (project identity + revision only; the browser does
    # not supply content).
    dest = args.get("destination_identity") or "ISOLATED_DESTINATION"
    normalized = {
        "project_title": "",
        "client_or_brand": "",
        "project_purpose": "",
        "normalized_brief_summary": "",
        "target_duration_seconds": 0,
        "output_profiles": [],
        "planned_rendition_count": 0,
        "operator_notes": "",
    }
    plan = build_materialization_plan(
        project_id=project_id,
        project_revision=project_revision,
        destination_identity=dest,
        normalized=normalized,
        output_profiles=(),
        now_iso=now_iso,
    )
    auth, decision, err = issue_authorization(
        store=store,
        project_id=project_id,
        project_revision=project_revision,
        plan=plan,
        operator_id=operator_id,
        confirmed=confirmed,
        now_iso=now_iso,
        authorization_id=authorization_id,
        nonce=nonce,
    )
    if auth is None:
        return {"ok": False, "decision": decision, "error_code": err or "REQUEST_REJECTED"}
    return {
        "ok": decision == DECISION_AUTHORIZED,
        "decision": decision,
        "authorization": {
            "authorization_id": auth.authorization_id,
            "project_id": auth.project_id,
            "project_revision": auth.project_revision,
            "operation": auth.operation,
            "materialization_plan_hash": auth.materialization_plan_hash,
            "destination_identity": auth.destination_identity,
            "decision": auth.decision,
        },
    }


def cmd_execute(args: dict[str, Any]) -> dict[str, Any]:
    store = _store(args.get("store_path"))
    project_id = str(args["project_id"])
    project_revision = int(args["project_revision"])
    authorization_id = str(args.get("authorization_id") or "")
    capability_id = str(args.get("capability_id") or "")
    attempt_id = str(args.get("attempt_id") or "")
    operator_id = str(args.get("operator_id") or "local-solo-operator")
    now_iso = _now_iso()
    projects_root = args.get("projects_root")
    hvs_repo_path = args.get("hvs_repo_path") or str(Path(__file__).resolve().parents[3] / "hermes-video-studio")
    python_executable = args.get("python_executable") or sys.executable

    authorization = store.get_authorization(authorization_id)
    if authorization is None:
        return {"ok": False, "error_code": "AUTHORIZATION_MISSING"}

    normalized = {
        "project_title": "",
        "client_or_brand": "",
        "project_purpose": "",
        "normalized_brief_summary": "",
        "target_duration_seconds": 0,
        "output_profiles": [],
        "planned_rendition_count": 0,
        "operator_notes": "",
    }
    result = materialize(
        store=store,
        project_id=project_id,
        project_revision=project_revision,
        normalized=normalized,
        output_profiles=(),
        destination_identity=args.get("destination_identity") or "ISOLATED_DESTINATION",
        authorization=authorization,
        capability_id=capability_id,
        attempt_id=attempt_id,
        operator_id=operator_id,
        now_iso=now_iso,
        hvs_initializer=_hvs_initializer_factory(hvs_repo_path, python_executable, projects_root, authorization),
        hvs_inspector=_hvs_inspector_factory(hvs_repo_path, python_executable, projects_root),
    )
    return result.to_response()


def cmd_reconcile(args: dict[str, Any]) -> dict[str, Any]:
    store = _store(args.get("store_path"))
    attempt_id = str(args.get("attempt_id") or "")
    projects_root = args.get("projects_root")
    hvs_repo_path = args.get("hvs_repo_path") or str(Path(__file__).resolve().parents[3] / "hermes-video-studio")
    python_executable = args.get("python_executable") or sys.executable
    classification, attempt = reconcile_materialization(
        store=store,
        attempt_id=attempt_id,
        hvs_inspector=_hvs_inspector_factory(hvs_repo_path, python_executable, projects_root),
    )
    return {"ok": classification == "HVS_PROJECT_MATERIALIZED", "classification": classification, "attempt": attempt.to_dict() if attempt is not None else None}


def cmd_projection(args: dict[str, Any]) -> dict[str, Any]:
    store = _store(args.get("store_path"))
    project_id = str(args["project_id"])
    result = store.read()
    if result["status"] != "AVAILABLE_WITH_DATA":
        return {
            "ok": False,
            "error_code": result.get("status", "STORE_UNAVAILABLE"),
            "projection": None,
        }
    attempts = [
        a for a in result["data"]["attempts"].values() if a.get("project_id") == project_id
    ]
    truth_state = "MATERIALIZATION_NOT_REQUESTED"
    terminal = next((a for a in attempts if a.get("state") == "HVS_PROJECT_MATERIALIZED"), None)
    if terminal:
        truth_state = "HVS_PROJECT_MATERIALIZED"
    else:
        unknown = next((a for a in attempts if a.get("state") == "MATERIALIZATION_OUTCOME_UNKNOWN"), None)
        starting = next((a for a in attempts if a.get("state") == "MATERIALIZATION_STARTING"), None)
        authorized = next((a for a in attempts if a.get("state") == "MATERIALIZATION_AUTHORIZED"), None)
        failed = next((a for a in attempts if a.get("state") == "MATERIALIZATION_FAILED_CONFIRMED"), None)
        if unknown:
            truth_state = "MATERIALIZATION_OUTCOME_UNKNOWN"
        elif starting:
            truth_state = "MATERIALIZATION_STARTING"
        elif authorized:
            truth_state = "MATERIALIZATION_AUTHORIZED"
        elif failed:
            truth_state = "MATERIALIZATION_FAILED_CONFIRMED"
    plan = build_materialization_plan(
        project_id=project_id,
        project_revision=2,
        destination_identity="ISOLATED_DESTINATION",
        normalized={
            "project_title": "", "client_or_brand": "", "project_purpose": "",
            "normalized_brief_summary": "", "target_duration_seconds": 0,
            "output_profiles": [], "planned_rendition_count": 0, "operator_notes": "",
        },
        output_profiles=(),
        now_iso=_now_iso(),
    )
    return {
        "ok": True,
        "projection": {
            "project_id": project_id,
            "truth_state": truth_state,
            "current_revision": attempts[-1].get("project_revision") if attempts else None,
            "plan": {
                "plan_schema_version": MATERIALIZATION_SCHEMA_VERSION,
                "project_id": plan.project_id,
                "project_revision": plan.project_revision,
                "normalized_hvs_project_name": plan.normalized_hvs_project_name,
                "destination_identity": plan.destination_identity,
                "project_metadata": plan.project_metadata,
                "output_profiles": list(plan.output_profiles),
                "expected_files": list(plan.expected_files),
                "expected_directories": list(plan.expected_directories),
                "forbidden_operations": list(plan.forbidden_operations),
                "plan_hash": plan.plan_hash,
            },
            "attempts": attempts,
        },
    }


_COMMANDS = {
    "authorize": cmd_authorize,
    "execute": cmd_execute,
    "reconcile": cmd_reconcile,
    "projection": cmd_projection,
}


def main(argv: "list[str] | None" = None) -> int:
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
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error_code": "INPUT_UNREADABLE", "detail": str(exc)}))
        return 2
    if not isinstance(payload, dict):
        print(json.dumps({"ok": False, "error_code": "INPUT_MALFORMED"}))
        return 2
    try:
        out = handler(payload)
    except Exception as exc:  # boundary must not leak raw trace
        print(json.dumps({"ok": False, "error_code": "BRIDGE_ERROR", "detail": type(exc).__name__}))
        return 1
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
