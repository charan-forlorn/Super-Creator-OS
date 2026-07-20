"""Cohort 10E — bounded Python service bridge for controlled HVS render.

This module is the SINGLE production entrypoint the Next.js render routes
call via a ``child_process`` bridge. It owns NO browser-facing logic and
performs NO authorization decisions of its own: authorization, capability
issuance, capability consumption, attempt persistence, single-active-render
enforcement, exact replay containment, identity gate, persistent
RENDER_SUCCEEDED/UNKNOWN outcome, and artifact projection are delegated to
the authoritative :mod:`scos.control_center.hvs_render_execution_service`
and its :class:`RenderAttemptStore`. The ONLY real HVS render mutation
boundary is the existing :class:`HermesVideoStudioAdapter.render_project`
(reached through ``render-hyperframes`` via the Stage 8.5 gate), and the
ONLY artifact validation is the existing
:func:`scos.control_center.hvs_render_completion_service.verify_render_artifact`.

This is the mandated Cohort 10E repair path:

    Next.js route
      -> child_process -> python -m scos.control_center.hvs_render_cli
        -> RenderAttemptStore   (authorization / capability / attempt truth)
        -> hvs_render_execution_service.render
        -> HermesVideoStudioAdapter.render_project  (sole real HVS render)
        -> verify_render_artifact                (technical artifact proof)

Safety:
  * The HVS render goes through the adapter's Stage 8.5 gate; the Cohort-10E
    authorization record is translated into a Stage 8.5 decision
    (``stage85_from_cohort10e_authorization``) so the adapter gate stays the
    last common fail-closed point before the HVS child process.
  * ``output_root`` / ``projects_root`` are OPT-IN isolation hooks used ONLY
    by the controlled canary (an isolated OS-temp root). Production callers
    pass ``None`` and the adapter writes under the real HVS STUDIO_ROOT.
  * No publish / upload / external network / render-hyperframes outside the
    adapter is ever invoked here.
"""

from __future__ import annotations

import hashlib
import json
import os
import struct
import sys
from pathlib import Path
from typing import Any

from .hvs_render_plan_models import (
    DECISION_AUTHORIZED,
    RENDER_SCHEMA_VERSION,
    OPERATION_RENDER_HVS_PROJECT,
    HvsRenderAuthorization,
)
from .hvs_render_attempt_store import RenderAttemptStore
from .hvs_render_execution_service import (
    build_render_plan,
    issue_authorization,
    normalized_hvs_project_name,
    reconcile_render,
    render,
)
from .hvs_adapter import HermesVideoStudioAdapter, HVSAdapterConfig


def _require_project_identity(args: dict[str, Any]) -> "tuple[str | None, int | None, str | None]":
    """Validate the required project identity fields (fail-closed).

    Returns ``(project_id, project_revision, error_code)``. On a missing /
    malformed required field, ``project_id``/``project_revision`` are ``None``
    and ``error_code`` is a precise, non-secret code (``REQUEST_MALFORMED``).
    Mirrors the Cohort-10D materialization CLI guard so a malformed request
    yields a structured verdict instead of an uncaught ``KeyError`` that the
    TS bridge would surface opaquely as ``BRIDGE_FAILED``.
    """
    project_id = str(args.get("project_id") or "")
    if not project_id:
        return (None, None, "REQUEST_MALFORMED")
    raw_revision = args.get("project_revision")
    if not isinstance(raw_revision, int) or isinstance(raw_revision, bool) or raw_revision < 0:
        return (None, None, "REQUEST_MALFORMED")
    return (project_id, int(raw_revision), None)


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _resolve_hyperframes_identity() -> "tuple[str | None, str | None]":
    """Resolve the EXPLICIT, server-controlled HyperFrames identity.

    Returns ``(canonical_abs_path, error_code)``. ``canonical_abs_path`` is the
    validated absolute launcher; ``error_code`` is a stable NON-SECRET code on
    failure (the absolute path is never returned in the code).

    The identity is read ONLY from the trusted server process environment
    (``SCOS_HYPERFRAMES_BIN``). It is never accepted from request data, query,
    header, cookie, or any browser origin. An absent or invalid identity fails
    closed with no HVS child process and no PATH-based fallback to a bare
    ``hyperframes`` name.
    """
    raw = os.environ.get("SCOS_HYPERFRAMES_BIN")
    if not raw or not raw.strip():
        return (None, "HF_IDENTITY_MISSING")
    canon, err = HermesVideoStudioAdapter.validate_tool_path(
        raw, require_approved_root=True
    )
    return (canon, err)


def _resolve_node_identity() -> "tuple[str | None, str | None]":
    """Resolve an explicit, server-controlled Node executable identity (optional).

    Read ONLY from ``SCOS_NODE_BIN``. Never request-derived. Optional: the
    HyperFrames ``.cmd`` launcher resolves ``node`` from PATH when no bundled
    node is present, so this is only needed when the synthetic render PATH must
    pin node explicitly. Returns ``(canonical_abs_path, error_code)``.
    """
    raw = os.environ.get("SCOS_NODE_BIN")
    if not raw or not raw.strip():
        return (None, None)
    canon, err = HermesVideoStudioAdapter.validate_tool_path(
        raw, require_approved_root=False
    )
    return (canon, err)


def _store(store_path: "str | None") -> RenderAttemptStore:
    if store_path:
        return RenderAttemptStore(store_path=Path(store_path))
    return RenderAttemptStore()


SAFE_OUTPUT_ROOT_ALIAS = "isolated-render-root"
CERTIFIED_HVS_HEAD = "5d684584ee8b774466182c71fca0d1b2cc6f7b88"

def _safe_error(code: str) -> dict[str, Any]:
    return {"ok": False, "error_code": code}

def _resolve_render_output_root() -> "tuple[str | None, str | None]":
    raw = os.environ.get("SCOS_RENDER_OUTPUT_ROOT")
    if raw is None or not raw.strip():
        return (None, "RENDER_OUTPUT_ROOT_MISSING")
    candidate = Path(raw)
    if not candidate.is_absolute():
        return (None, "RENDER_OUTPUT_ROOT_INVALID")
    try:
        resolved = candidate.resolve(strict=False)
    except (OSError, ValueError):
        return (None, "RENDER_OUTPUT_ROOT_INVALID")
    normalized = str(resolved).replace("\\", "/")
    forbidden = ("C:/Workspace/super-creator-os", "C:/Workspace/hermes-video-studio")
    if any(normalized.startswith(f) for f in forbidden):
        return (None, "RENDER_OUTPUT_ROOT_FORBIDDEN")
    if "/AppData/Local/Temp/" not in normalized and "/Temp/" not in normalized and "scos-render" not in normalized.lower():
        return (None, "RENDER_OUTPUT_ROOT_FORBIDDEN")
    return (str(resolved), None)

def _git_dir(candidate: Path) -> Path:
    git_ref = candidate / ".git"
    if git_ref.is_file():
        content = git_ref.read_text(encoding="utf-8").strip()
        if not content.startswith("gitdir:"):
            raise RuntimeError("SCOS_HVS_REPO_PATH gitdir malformed")
        git_dir = Path(content.split(":", 1)[1].strip())
        return git_dir if git_dir.is_absolute() else (candidate / git_dir).resolve(strict=False)
    if git_ref.is_dir():
        return git_ref
    raise RuntimeError("SCOS_HVS_REPO_PATH is not a git worktree")

def _common_git_dir(linked_git_dir: Path) -> "Path | None":
    """Resolve the shared (common) Git directory for a linked worktree.

    For a regular repository the ``.git`` is a directory and there is no
    ``commondir``; the common directory equals the linked directory.
    For a ``git worktree`` the linked gitdir contains a ``commondir`` pointer
    (relative to the linked gitdir) pointing at the shared repository
    metadata. Returns ``None`` when no ``commondir`` is present so callers
    fall back to linked-only resolution (regular repo semantics).
    """
    commondir = linked_git_dir / "commondir"
    if not commondir.is_file():
        return None
    rel = commondir.read_text(encoding="utf-8").strip()
    if not rel:
        return None
    resolved = (linked_git_dir / rel).resolve(strict=False)
    if resolved == linked_git_dir.resolve(strict=False):
        return None
    return resolved


def _read_symbolic_ref(linked_git_dir: Path, ref: str) -> str:
    """Resolve a ``ref:`` target deterministically without shelling out.

    Search order (worktree-aware, fail-closed):
      1. linked-gitdir loose ref (worktree-private when valid)
      2. common-gitdir loose ref
      3. linked-gitdir packed-refs
      4. common-gitdir packed-refs
    Returns the resolved commit SHA. Raises on any unreadable/missing/ambiguous
    state. Never infers or synthesizes a commit.
    """
    common = _common_git_dir(linked_git_dir)
    search_dirs = [linked_git_dir]
    if common is not None and common.resolve(strict=False) != linked_git_dir.resolve(strict=False):
        search_dirs.append(common)

    # Loose refs first, across linked then common directories.
    for d in search_dirs:
        ref_file = d / ref
        if ref_file.is_file():
            return ref_file.read_text(encoding="utf-8").strip()

    # Packed refs next, across the same directories.
    for d in search_dirs:
        packed = d / "packed-refs"
        if packed.is_file():
            for line in packed.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not line or line.startswith("#"):
                    continue
                # Skip peeled/packed object lines ( "SHA^{}" ) and annotated
                # tag deref lines ( "SHA objectname" without a refs/ path ).
                if " " not in line:
                    continue
                sha, name = line.split(" ", 1)
                name = name.strip()
                if name == ref:
                    return sha

    raise RuntimeError("SCOS_HVS_REPO_PATH HEAD ref missing")


def _read_git_head(candidate: Path) -> str:
    git_dir = _git_dir(candidate)
    head_text = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    if head_text.startswith("ref:"):
        ref = head_text.split(" ", 1)[1].strip()
        return _read_symbolic_ref(git_dir, ref)
    return head_text

def _blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def _blob_sha1_autocrlf_normalized(path: Path) -> "str | None":
    """Best-effort git-autocrlf-aware blob SHA.

    Git with ``core.autocrlf`` (or equivalent) normalizes line endings
    (CRLF -> LF) before computing the blob SHA, so a clean working tree on a
    Windows checkout has CRLF on disk but an LF-normalized index blob. A
    worktree is still *clean* under git in that case, so we accept the
    normalized blob as equivalent. Returns ``None`` for non-text/binary
    content where normalization is unsafe. Never mutates files.
    """
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data:  # binary: normalization is undefined
        return None
    normalized = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha1(b"blob " + str(len(normalized)).encode("ascii") + b"\0" + normalized).hexdigest()


def _index_tracked_paths_clean(candidate: Path, git_dir: Path) -> bool:
    index = git_dir / "index"
    if not index.exists():
        return False
    data = index.read_bytes()
    if len(data) < 12 or data[:4] != b"DIRC":
        return False
    version, count = struct.unpack(">II", data[4:12])
    if version not in (2, 3):
        return False
    pos = 12
    for _ in range(count):
        start = pos
        if pos + 62 > len(data):
            return False
        mode = struct.unpack(">I", data[pos+24:pos+28])[0]
        sha = data[pos+40:pos+60].hex()
        flags = struct.unpack(">H", data[pos+60:pos+62])[0]
        name_len = flags & 0x0FFF
        pos += 62
        if name_len == 0x0FFF:
            end = data.index(b"\0", pos)
            name = data[pos:end].decode("utf-8", errors="surrogateescape")
            pos = end
        else:
            name = data[pos:pos+name_len].decode("utf-8", errors="surrogateescape")
            pos += name_len
        pos += 1
        while (pos - start) % 8:
            pos += 1
        if mode == 0o160000:
            continue
        f = candidate / name
        if not f.is_file():
            return False
        if _blob_sha1(f) != sha:
            # Git normalizes line endings (e.g. core.autocrlf) before hashing,
            # so a clean Windows checkout has CRLF on disk but an LF-normalized
            # index blob. Accept the autocrlf-normalized blob as equivalent; a
            # genuine content mutation still differs after normalization.
            norm = _blob_sha1_autocrlf_normalized(f)
            if norm is None or norm != sha:
                return False
    return True

def _validate_clean_certified_hvs_repo(candidate: Path) -> None:
    git_dir = _git_dir(candidate)
    head = _read_git_head(candidate)
    if head != CERTIFIED_HVS_HEAD:
        raise RuntimeError("SCOS_HVS_REPO_PATH is not the certified HVS commit")
    if (git_dir / "index.lock").exists():
        raise RuntimeError("SCOS_HVS_REPO_PATH has an active git lock")
    if not _index_tracked_paths_clean(candidate, git_dir):
        raise RuntimeError("SCOS_HVS_REPO_PATH tracked tree is not clean")

def _hvs_repo_path() -> str:
    """Resolve the required certified HVS worktree from trusted server env only."""
    override = os.environ.get("SCOS_HVS_REPO_PATH")
    if override is None or not override.strip():
        raise RuntimeError("SCOS_HVS_REPO_PATH is required")
    candidate = Path(override)
    if not candidate.is_absolute():
        raise RuntimeError("SCOS_HVS_REPO_PATH must be an absolute path")
    try:
        candidate = candidate.resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"SCOS_HVS_REPO_PATH cannot be resolved: {type(exc).__name__}")
    if not candidate.is_dir():
        raise RuntimeError("SCOS_HVS_REPO_PATH is not a directory")
    _validate_clean_certified_hvs_repo(candidate)
    return str(candidate)

def _make_adapter(hvs_repo_path: str, python_executable: str) -> HermesVideoStudioAdapter:
    cfg = HVSAdapterConfig(
        hvs_repo_path=hvs_repo_path,
        python_executable=python_executable,
        operation="render-hyperframes",
        timeout_seconds=300,
    )
    return HermesVideoStudioAdapter(cfg)


def _hvs_render_factory(
    hvs_repo_path: str,
    python_executable: str,
    output_root: "str | None",
    projects_root: "str | None",
    auth: "HvsRenderAuthorization | None",
    now_iso: "str | None" = None,
) -> Any:
    """Return the real HVS render callable wired to the existing adapter.

    The adapter's Stage 8.5 gate is derived from the Cohort-10E
    authorization record so the adapter remains the last common fail-closed
    point before the HVS child process. The isolation root is taken ONLY from
    the factory closure; the authoritative service passes
    ``kwargs["output_root_identity"]`` which maps to the adapter's
    ``output_root`` isolution hook.
    """
    adapter = _make_adapter(hvs_repo_path, python_executable)
    _iso_root = output_root or projects_root
    _now_iso_ts = now_iso or _now_iso()
    # Resolve the EXPLICIT, server-controlled HyperFrames identity ONCE, at
    # factory construction. Both hf_bin and node_bin are None unless the
    # trusted server environment supplies valid, approved identities.
    hf_bin, _hf_err = _resolve_hyperframes_identity()
    node_bin, _node_err = _resolve_node_identity()
    auth_dict = auth.to_dict() if auth is not None else {}
    auth_dict["_now_iso"] = _now_iso_ts

    def _render(**kwargs: Any) -> dict[str, Any]:
        project_id = str(kwargs.get("project_id"))
        fmt = str(kwargs.get("format") or "vertical")
        request_id = str(kwargs.get("request_id") or project_id)
        # Map the server-resolved isolated roots onto the adapter isolation hooks.
        # The materialized project lives under projects_root; the artifact is
        # written under output_root. They are distinct isolated OS-temp roots.
        projects_root = kwargs.get("projects_root") or _iso_root
        output_root = kwargs.get("output_root_identity") or _iso_root
        result = adapter.render_project(
            project_id=project_id,
            fmt=fmt,
            request_id=request_id,
            output_root=output_root,
            projects_root=projects_root,
            cohort10e_authorization=auth_dict,
            hyperframes_bin=hf_bin,
            node_bin=node_bin,
        )
        payload = result.get("payload") or {}
        out = payload.get("output_path") or payload.get("output_relative_path")
        return {
            "ok": bool(result.get("ok")),
            "command": "render-hyperframes",
            "exit_code": result.get("exit_code"),
            "render_id": payload.get("render_id"),
            "output_relative_path": out,
            "error_detail": result.get("error_detail"),
        }

    return _render


def _hvs_inspector_factory(
    hvs_repo_path: str,
    python_executable: str,
    projects_root: "str | None",
) -> Any:
    adapter = _make_adapter(hvs_repo_path, python_executable)
    _iso_root = projects_root

    def _inspect(**kwargs: Any) -> dict[str, Any]:
        project_id = str(kwargs.get("project_id"))
        result = adapter.inspect_project(
            project_id=project_id,
            request_id=str(kwargs.get("request_id") or project_id),
            projects_root=_iso_root,
        )
        payload = result.get("payload") or {}
        # Reused by reconciliation: surface artifact presence/checksum if the
        # inspector reports it; otherwise default to project presence only.
        return {
            "ok": bool(result.get("ok")),
            "exists": bool(payload.get("exists")),
            "valid": bool(payload.get("valid")),
            "project_id": project_id,
            "artifact_exists": bool(payload.get("artifact_exists")),
            "artifact_sha256": payload.get("artifact_sha256") or "",
            "artifact_size_bytes": int(payload.get("artifact_size_bytes") or 0),
        }

    return _inspect


def _artifact_validator_factory() -> Any:
    """Reuse the existing technical artifact validator (Cohort 8N)."""
    from .hvs_render_completion_service import verify_render_artifact

    def _validate(**kwargs: Any) -> dict[str, Any]:
        # verify_render_artifact appends to an audit log; under canary it is
        # fine. The function returns {"ok", "verification", "blockers"}.
        try:
            return verify_render_artifact(**kwargs)
        except Exception as exc:  # defensive: never crash the authority
            return {
                "ok": False,
                "verification": {"artifact_verified": False, "verification_status": "UNEXPECTED_OUTPUT"},
                "blockers": (f"validator_error:{type(exc).__name__}",),
            }

    return _validate


def cmd_projection(args: dict[str, Any]) -> dict[str, Any]:
    store = _store(args.get("store_path"))
    project_id = str(args.get("project_id") or "")
    if not project_id:
        return {"ok": False, "error_code": "PROJECT_NOT_FOUND", "projection": None}
    result = store.read()
    if result["status"] == "EMPTY":
        attempts: list = []
        auths: list = []
    elif result["status"] != "AVAILABLE_WITH_DATA":
        return {"ok": False, "error_code": result.get("status", "STORE_UNAVAILABLE"), "projection": None}
    else:
        attempts = [a for a in result["data"]["attempts"].values() if a.get("project_id") == project_id]
        auths = [a for a in result["data"].get("authorizations", {}).values() if a.get("project_id") == project_id]
    truth_state = "RENDER_NOT_REQUESTED"
    terminal = next((a for a in attempts if a.get("state") == "RENDER_SUCCEEDED"), None)
    if terminal:
        truth_state = "RENDER_SUCCEEDED"
    else:
        unknown = next((a for a in attempts if a.get("state") == "RENDER_OUTCOME_UNKNOWN"), None)
        running = next((a for a in attempts if a.get("state") == "RENDER_RUNNING"), None)
        starting = next((a for a in attempts if a.get("state") == "RENDER_STARTING"), None)
        authorized = next((a for a in attempts if a.get("state") == "RENDER_AUTHORIZED"), None)
        failed = next((a for a in attempts if a.get("state") == "RENDER_FAILED_CONFIRMED"), None)
        rec = next((a for a in attempts if a.get("state") == "RENDER_RECONCILIATION_REQUIRED"), None)
        if unknown:
            truth_state = "RENDER_OUTCOME_UNKNOWN"
        elif running:
            truth_state = "RENDER_RUNNING"
        elif starting:
            truth_state = "RENDER_STARTING"
        elif authorized:
            truth_state = "RENDER_AUTHORIZED"
        elif rec:
            truth_state = "RENDER_RECONCILIATION_REQUIRED"
        elif failed:
            truth_state = "RENDER_FAILED_CONFIRMED"
        # Authorization-aware truth state: an AUTHORIZED authorization with no
        # terminal/running/starting attempt means the operator may execute.
        if truth_state == "RENDER_NOT_REQUESTED":
            authorized_auth = next(
                (a for a in auths if a.get("decision") == "AUTHORIZED"), None
            )
            if authorized_auth is not None:
                truth_state = "RENDER_AUTHORIZED"
    # Deterministic render plan projection (server-resolved; no browser content).
    plan = build_render_plan(
        project_id=project_id,
        project_revision=int(args.get("project_revision") or 2),
        materialization_attempt_id=str(args.get("materialization_attempt_id") or "mat-unknown"),
        materialization_plan_hash=str(args.get("materialization_plan_hash") or ""),
        render_profile_id="vertical",
        output_root_identity=SAFE_OUTPUT_ROOT_ALIAS,
        now_iso=_now_iso(),
    )
    return {
        "ok": True,
        "projection": {
            "project_id": project_id,
            "truth_state": truth_state,
            "current_revision": attempts[-1].get("project_revision") if attempts else None,
            "plan": {
                "plan_schema_version": RENDER_SCHEMA_VERSION,
                "project_id": plan.project_id,
                "project_revision": plan.project_revision,
                "materialization_attempt_id": plan.materialization_attempt_id,
                "materialization_plan_hash": plan.materialization_plan_hash,
                "render_profile_id": plan.render_profile_id,
                "hvs_project_name": plan.hvs_project_name,
                "output_root_identity": plan.output_root_identity,
                "profile_metadata": plan.profile_metadata,
                "expected_output_filename": plan.expected_output_filename,
                "expected_output_relative_path": plan.expected_output_relative_path,
                "forbidden_operations": list(plan.forbidden_operations),
                "plan_hash": plan.plan_hash,
            },
            "attempts": attempts,
            "authorization": ({**auths[-1], "capability_id": f"cap-{auths[-1].get('render_plan_hash','')[:16]}", "attempt_id": f"att-{auths[-1].get('render_plan_hash','')[16:32]}"} if auths else None),
        },
    }


def cmd_authorize(args: dict[str, Any]) -> dict[str, Any]:
    project_id, project_revision, err = _require_project_identity(args)
    if err is not None:
        return {"ok": False, "error_code": err, "detail": "project_id and a non-negative integer project_revision are required"}
    store = _store(args.get("store_path"))
    confirmed = bool(args.get("confirmed"))
    seed = f"{project_id}:{project_revision}:{args.get('materialization_attempt_id') or 'mat-unknown'}:{args.get('materialization_plan_hash') or ''}:{args.get('render_profile_id') or 'vertical'}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    authorization_id = str(args.get("authorization_id") or f"auth-{digest[:16]}")
    nonce = str(args.get("nonce") or digest[16:32])
    operator_id = str(args.get("operator_id") or "local-solo-operator")
    materialization_attempt_id = str(args.get("materialization_attempt_id") or "mat-unknown")
    materialization_plan_hash = str(args.get("materialization_plan_hash") or "")
    render_profile_id = str(args.get("render_profile_id") or "vertical")
    physical_output_root, out_err = _resolve_render_output_root()
    if out_err is not None:
        return {"ok": False, "error_code": out_err}
    output_root_identity = SAFE_OUTPUT_ROOT_ALIAS
    now_iso = _now_iso()
    auth, decision, err = issue_authorization(
        store=store,
        project_id=project_id,
        project_revision=project_revision,
        materialization_attempt_id=materialization_attempt_id,
        materialization_plan_hash=materialization_plan_hash,
        render_profile_id=render_profile_id,
        output_root_identity=output_root_identity,
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
            "operation": auth.operation(),
            "materialization_attempt_id": auth.materialization_attempt_id,
            "render_profile_id": auth.render_profile_id,
            "render_plan_hash": auth.render_plan_hash,
            "output_root_identity": auth.output_root_identity,
            "decision": auth.decision,
            "capability_id": f"cap-{auth.render_plan_hash[:16]}",
            "attempt_id": f"att-{auth.render_plan_hash[16:32]}",
        },
    }


def cmd_execute(args: dict[str, Any]) -> dict[str, Any]:
    project_id, project_revision, err = _require_project_identity(args)
    if err is not None:
        return {"ok": False, "error_code": err, "detail": "project_id and a non-negative integer project_revision are required"}
    store = _store(args.get("store_path"))
    authorization_id = str(args.get("authorization_id") or "")
    capability_id = str(args.get("capability_id") or "")
    attempt_id = str(args.get("attempt_id") or "")
    operator_id = str(args.get("operator_id") or "local-solo-operator")
    materialization_attempt_id = str(args.get("materialization_attempt_id") or "mat-unknown")
    materialization_plan_hash = str(args.get("materialization_plan_hash") or "")
    render_profile_id = str(args.get("render_profile_id") or "vertical")
    physical_output_root, out_err = _resolve_render_output_root()
    if out_err is not None:
        return {"ok": False, "error_code": out_err}
    output_root_identity = SAFE_OUTPUT_ROOT_ALIAS
    projects_root_identity = str(args.get("projects_root_identity") or physical_output_root)
    now_iso = _now_iso()
    hvs_repo_path = _hvs_repo_path()
    python_executable = sys.executable
    authorization = store.get_authorization(authorization_id)
    if authorization is None:
        return {"ok": False, "error_code": "AUTHORIZATION_MISSING"}
    result = render(
        store=store,
        project_id=project_id,
        project_revision=project_revision,
        materialization_attempt_id=materialization_attempt_id,
        materialization_plan_hash=materialization_plan_hash,
        render_profile_id=render_profile_id,
        output_root_identity=output_root_identity,
        projects_root_identity=projects_root_identity,
        physical_output_root_identity=physical_output_root,
        authorization=authorization,
        capability_id=capability_id,
        attempt_id=attempt_id,
        operator_id=operator_id,
        now_iso=now_iso,
        hvs_render=_hvs_render_factory(hvs_repo_path, python_executable, physical_output_root, projects_root_identity, authorization, now_iso),
        hvs_inspector=_hvs_inspector_factory(hvs_repo_path, python_executable, projects_root_identity),
        artifact_validator=_artifact_validator_factory(),
    )
    return result.to_response()


def cmd_reconcile(args: dict[str, Any]) -> dict[str, Any]:
    store = _store(args.get("store_path"))
    attempt_id = str(args.get("attempt_id") or "")
    output_root_identity = str(args.get("output_root_identity") or "ISOLATED_OUTPUT_ROOT")
    hvs_repo_path = _hvs_repo_path()
    python_executable = sys.executable
    classification, attempt = reconcile_render(
        store=store,
        attempt_id=attempt_id,
        hvs_inspector=_hvs_inspector_factory(hvs_repo_path, python_executable, output_root_identity),
    )
    return {
        "ok": True,
        "classification": classification,
        "attempt": attempt.to_dict() if attempt is not None else None,
    }


def cmd_record_transport_unknown(args: dict[str, Any]) -> dict[str, Any]:
    project_id, project_revision, err = _require_project_identity(args)
    if err is not None:
        return {"ok": False, "error_code": err}
    attempt_id = str(args.get("attempt_id") or "")
    if not attempt_id:
        return {"ok": False, "error_code": "REQUEST_MALFORMED"}
    store = _store(args.get("store_path"))
    attempt = store.record_transport_unknown(
        attempt_id=attempt_id,
        project_id=project_id,
        project_revision=project_revision,
        marked_at=_now_iso(),
        error_code="BRIDGE_TIMEOUT",
    )
    if attempt is None:
        return {"ok": False, "error_code": "ATTEMPT_NOT_FOUND", "state": "RENDER_RECONCILIATION_REQUIRED"}
    return {"ok": False, "error_code": "BRIDGE_TIMEOUT", "state": attempt.state, "attempt": attempt.to_dict(), "render_calls": 0, "hvs_calls": 0}

_COMMANDS = {
    "projection": cmd_projection,
    "authorize": cmd_authorize,
    "execute": cmd_execute,
    "reconcile": cmd_reconcile,
    "record-transport-unknown": cmd_record_transport_unknown,
}


def _main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in _COMMANDS:
        sys.stdout.write(json.dumps({"ok": False, "error_code": "UNKNOWN_OPERATION"}))
        return 2
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    try:
        out = _COMMANDS[sys.argv[1]](payload)
    except RuntimeError as exc:
        # Fail-closed resolver errors (e.g. invalid SCOS_HVS_REPO_PATH).
        # Emit a structured verdict only; never leak the resolved absolute
        # path or the exception text in the response.
        out = {"ok": False, "error_code": "HVS_REPO_PATH_INVALID"}
    sys.stdout.write(json.dumps(out, ensure_ascii=False, sort_keys=True))
    # Transport-level success: the structured authority verdict (ok/error_code)
    # travels inside `out`. A non-zero exit is reserved for bridge-level
    # failures (unknown command, unreadable input) so the TS bridge's `ok`
    # reflects whether the authoritative CLI ran, not whether the render itself
    # succeeded.
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
