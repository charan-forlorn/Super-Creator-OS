"""Hermetic, process-local HVS double for integration tests.

This module provides a *temporary* HVS repository stand-in so the SCOS
``integration``-marked tests can exercise the exact SCOS-to-HVS boundary
(command construction, path propagation, subprocess invocation, manifest
read-back, sha256 verification, event persistence) **without** touching the
operator's real ``C:/Workspace/hermes-video-studio`` repository.

Contract fidelity
-----------------
The double emulates only the *public* HVS CLI contract used by the tests:

* ``import-media``  — writes a deterministic asset entry into the temp
  project's ``media/media_manifest.json`` and prints the same
  ``VERDICT: PASS`` / ``asset_id:`` stdout shape the real CLI prints, so
  ``materialize_assets`` independently reads the manifest back and verifies
  the sha256 against the approved source (no tautology).
* ``initialize-project`` — writes a minimal ``initialization_manifest.json``
  and returns exit code 0 (rejects malformed args with a non-zero exit).
* ``render-hyperframes`` — returns exit code 0 with a JSON payload
  ``{"verdict": "PASS", "output_path": <temp mp4>}`` so the caller's
  real ``verify_render_artifact`` (which runs REAL ffprobe on the temp file)
  stays a genuine integration assertion.

Security / isolation guarantees
--------------------------------
* Every write goes beneath ``<temp hvs root>/projects/<pid>/...``.
* No real HVS repo, no network, no shell, no registry, no PATH change.
* The double rejects unknown commands and unexpected required arguments with
  a non-zero result instead of silently passing.
* The injected runner is a plain ``Callable`` honored by SCOS's existing
  ``subprocess_run`` seam; SCOS never spawns a real subprocess when it is set.

This is a TEST-ONLY support module. It is never imported by production code.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable

_MEDIA_MANIFEST_REL = "media/media_manifest.json"
_INIT_MANIFEST_REL = "initialization_manifest.json"


def make_temp_hvs_repo(root: Path, project_id: str) -> Path:
    """Create a minimal temp HVS repo root with one empty project dir.

    Returns the temp HVS root (everything below it is test-owned).
    """
    root = Path(root)
    proj = root / "projects" / project_id
    (proj / "media").mkdir(parents=True, exist_ok=True)
    (proj / "renders").mkdir(parents=True, exist_ok=True)
    return root


def _read_manifest(hvs_root: Path, project_id: str) -> dict[str, Any]:
    p = hvs_root / "projects" / project_id / _MEDIA_MANIFEST_REL
    if not p.is_file():
        return {"assets": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError, OSError):
        return {"assets": []}


def _write_manifest(hvs_root: Path, project_id: str, data: dict[str, Any]) -> None:
    p = hvs_root / "projects" / project_id / _MEDIA_MANIFEST_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _asset_id_for(project_id: str, role: str, sha: str) -> str:
    return hashlib.sha256(f"{project_id}:{role}:{sha}".encode("utf-8")).hexdigest()[:32]


def _cmd_import_media(hvs_root: Path, argv: list[str]) -> dict[str, Any]:
    """Emulate ``python -m hvs.cli import-media`` against the temp repo."""
    # argv shape: [py, -m, hvs.cli, import-media, --project-id, PID,
    #              --role, ROLE, --path, ABS, (--scene-id, SID)?]
    parsed = _parse_kwargs(argv[4:])
    project_id = parsed.get("--project-id")
    role = parsed.get("--role")
    source_path = parsed.get("--path")
    if not project_id or not role or not source_path:
        return _fail("import-media", "missing required argument")
    src = Path(source_path)
    if not src.is_file():
        return _fail("import-media", f"source not found: {source_path}")
    sha = hashlib.sha256(src.read_bytes()).hexdigest()
    # Mirror the real HVS role vocabulary used by SCOS media manifest reads.
    manifest = _read_manifest(hvs_root, project_id)
    asset_id = _asset_id_for(project_id, role, sha)
    scene_id = parsed.get("--scene-id", "")
    asset = {
        "asset_id": asset_id,
        "media_role": role,
        "scene_id": scene_id or "",
        "sha256": sha,
        "imported_path": f"projects/{project_id}/media/assets/{asset_id}",
        "probe_status": "ok",
    }
    manifest.setdefault("assets", [])
    manifest["assets"].append(asset)
    _write_manifest(hvs_root, project_id, manifest)
    stdout = f"VERDICT: PASS\n  project_id : {project_id}\n  role       : {role}\n  asset_id   : {asset_id}\n"
    return {"ok": True, "command": "import-media", "exit_code": 0,
            "error_kind": None, "error_detail": None, "stdout": stdout, "stderr": ""}


def _cmd_initialize_project(hvs_root: Path, argv: list[str]) -> dict[str, Any]:
    """Emulate ``python -m hvs.cli initialize-project`` against the temp repo."""
    parsed = _parse_kwargs(argv[4:])
    project_id = parsed.get("--project-id")
    if not project_id:
        return _fail("initialize-project", "missing required argument --project-id")
    proj = hvs_root / "projects" / project_id
    proj.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "hvs.project-initialization.v1",
        "project_id": project_id,
        "status": "initialized",
        "network_used": False,
        "render_started": False,
        "assets_copied": False,
        "placeholder_assets_created": False,
        "voice_created": False,
        "contract_name": "scos-hvs.project-initialization",
        "contract_version": "1",
        "contract_semantic_hash": "0" * 64,
        "payload_hash": "0" * 16,
        "timeline_relative_path": "timelines/video_timeline.json",
    }
    (proj / _INIT_MANIFEST_REL).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    stdout = f"Initialized project: {project_id}\n"
    return {"ok": True, "command": "initialize-project", "exit_code": 0,
            "error_kind": None, "error_detail": None, "stdout": stdout, "stderr": ""}


def _cmd_render_hyperframes(hvs_root: Path, argv: list[str], *,
                            output_path: str | None = None) -> dict[str, Any]:
    """Emulate ``python -m hvs.cli render-hyperframes``.

    Returns a JSON payload with ``verdict: PASS`` and an ``output_path`` that
    points at the temp render artifact. The caller performs REAL ffprobe on
    that file, so the artifact profile assertion remains a genuine check.
    """
    parsed = _parse_kwargs(argv[4:])
    project_id = parsed.get("--project-id")
    fmt = parsed.get("--format")
    if not project_id or not fmt:
        return _fail("render-hyperframes", "missing required argument")
    out = output_path or f"projects/{project_id}/renders/hyperframes-{project_id[:8]}.mp4"
    payload = json.dumps({"verdict": "PASS", "output_path": out}, ensure_ascii=False)
    stdout = payload + "\n"
    return {"ok": True, "command": "render-hyperframes", "exit_code": 0,
            "error_kind": None, "error_detail": None, "stdout": stdout, "stderr": ""}


def _parse_kwargs(tokens: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.startswith("--"):
            key = tok
            if i + 1 < len(tokens) and not tokens[i + 1].startswith("--"):
                out[key] = tokens[i + 1]
                i += 2
            else:
                out[key] = ""
                i += 1
        else:
            i += 1
    return out


def _fail(command: str, detail: str) -> dict[str, Any]:
    return {"ok": False, "command": command, "exit_code": 1,
            "error_kind": "hvs_command_failed", "error_detail": detail,
            "stdout": "", "stderr": detail}


def hvs_subprocess_double(hvs_root: Path, *, render_output_path: str | None = None) -> Callable:
    """Return a ``subprocess_run``-compatible double bound to a temp HVS root.

    The returned callable accepts ``(argv, cwd=..., shell=...)`` and dispatches
    only the HVS CLI commands the integration tests use. Unknown commands and
    malformed argv are failed closed (non-zero), never silently passed.
    """
    root = Path(hvs_root).resolve()

    def _runner(argv, *, cwd: str | None = None, shell: bool = False, **_kw):  # noqa: ANN001
        if shell:
            return _fail("hvs", "shell invocation rejected by hermetic double")
        argv = list(argv)
        if len(argv) < 4 or argv[1:3] != ["-m", "hvs.cli"]:
            return _fail("hvs", "unexpected argv prefix")
        command = argv[3]
        if command == "import-media":
            return _cmd_import_media(root, argv)
        if command == "initialize-project":
            return _cmd_initialize_project(root, argv)
        if command == "render-hyperframes":
            return _cmd_render_hyperframes(root, argv, output_path=render_output_path)
        return _fail(command, "unsupported HVS command in hermetic double")

    return _runner


def snapshot_paths(root: Path) -> set[str]:
    """Return the set of normalized file paths beneath ``root`` (for
    before/after integrity comparison in tests)."""
    root = Path(root)
    if not root.exists():
        return set()
    out: set[str] = set()
    for p in root.rglob("*"):
        if p.is_file():
            out.add(str(p.resolve()))
    return out
