"""Server-controlled task-owned runtime-root resolution for SCOS paid-pilot.

This module is the SINGLE authority that decides where paid-pilot task state is
written. The browser never supplies filesystem paths: every root is resolved
from trusted server-side environment variables here (read by the Python
authority, never forwarded from a request body).

Fail-closed contract:
  * If any required root environment variable is missing, invalid, a path
    traversal, a reparse-point/junction escape, or lives inside a git
    repository, resolution raises ``RootConfigInvalid`` and no shared/default
    evidence root is silently substituted.
  * The historical hard-coded default ``C:/Workspace/scos-paid-pilot-evidence``
    is intentionally NOT used as a fallback. Real-packet admission requires an
    explicit, isolated task-owned root.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_ENV_PREFIX = "SCOS_PILOT_"

# Logical root name -> environment variable suffix. Every one of these is a
# SERVER-side variable; the browser never supplies any of them.
ROOT_ENV_VARS = {
    "intake_store": "INTAKE_STORE",
    "packet_admission_store": "PACKET_ADMISSION_STORE",
    "audit_store": "AUDIT_STORE",
    "authorization_store": "AUTHORIZATION_STORE",
    "materialization_state": "MATERIALIZATION_STATE",
    "hvs_projects_root": "HVS_PROJECTS_ROOT",
    "render_readiness_state": "RENDER_READINESS_STATE",
    "output_root": "OUTPUT_ROOT",
    # Server-owned approved asset source (packet assets are read from here only).
    "approved_input_root": "APPROVED_INPUT_ROOT",
    # Parent bases for the guided-intake create_pilot runtime/evidence layout.
    "intake_runtime_base": "INTAKE_RUNTIME_BASE",
    "intake_evidence_base": "INTAKE_EVIDENCE_BASE",
}


class RootConfigInvalid(Exception):
    """Raised when task-owned roots cannot be resolved fail-closed."""

    def __init__(self, code: str, detail: str):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _has_link_or_reparse(p: Path) -> bool:
    parts = Path(p).resolve().parts
    for i in range(1, len(parts) + 1):
        q = Path(*parts[:i])
        try:
            if q.exists() and q.is_symlink():
                return True
        except OSError:
            return True
        try:
            if os.name == "nt" and q.exists():
                import stat

                if q.stat().st_file_attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
                    return True
        except OSError:
            return True
    return False


def _inside_git(p: Path) -> bool:
    p = Path(p).resolve()
    return any((q / ".git").exists() for q in (p, *p.parents))


def _validate_root(name: str, raw: str) -> Path:
    if not raw or not raw.strip():
        raise RootConfigInvalid("ROOT_NOT_CONFIGURED", f"{name} root is not configured")
    # Reject obvious absolute-escape attempts (bare drive-less absolute on Win/MSYS)
    # BEFORE resolve. A normal drive path like C:\... is allowed (has ":" within).
    if raw.startswith(("/", "\\")) and len(raw) > 1 and ":" not in raw[:3]:
        raise RootConfigInvalid("ROOT_PATH_TRAVERSAL", f"{name} root contains an unsafe segment")
    try:
        resolved = Path(raw).resolve()
    except Exception as e:  # pragma: no cover - defensive
        raise RootConfigInvalid("ROOT_UNRESOLVABLE", f"{name} root cannot be resolved: {e}")
    # After resolution, a genuine traversal would have collapsed any "..". Reject
    # only if the resolved form still carries a parent reference (shouldn't happen)
    # or if the path is a root/unc.
    if ".." in resolved.parts:
        raise RootConfigInvalid("ROOT_PATH_TRAVERSAL", f"{name} root contains an unresolved parent reference")
    if _has_link_or_reparse(resolved):
        raise RootConfigInvalid("ROOT_REPARSE_POINT", f"{name} root resolves through a reparse point")
    if _inside_git(resolved):
        raise RootConfigInvalid("ROOT_INSIDE_GIT", f"{name} root is inside a git repository")
    return resolved


@dataclass(frozen=True)
class TaskOwnedRoots:
    intake_store: Path
    packet_admission_store: Path
    audit_store: Path
    authorization_store: Path
    materialization_state: Path
    hvs_projects_root: Path
    render_readiness_state: Path
    output_root: Path
    approved_input_root: Path
    intake_runtime_base: Path
    intake_evidence_base: Path

    def as_dict(self) -> dict[str, str]:
        return {k: str(v) for k, v in self.__dict__.items()}

    def to_json(self) -> dict[str, Any]:
        return self.as_dict()


def resolve_task_owned_roots(environ: dict[str, str] | None = None) -> TaskOwnedRoots:
    """Resolve all task-owned roots from server environment only.

    Raises ``RootConfigInvalid`` if any root is missing or unsafe. Never falls
    back to a shared evidence root.
    """
    env = environ if environ is not None else dict(os.environ)
    values: dict[str, Path] = {}
    for name, suffix in ROOT_ENV_VARS.items():
        var = f"{_ENV_PREFIX}{suffix}"
        raw = env.get(var)
        if raw is None:
            raise RootConfigInvalid("ROOT_NOT_CONFIGURED", f"required environment variable {var} is not set")
        values[name] = _validate_root(name, raw)
    return TaskOwnedRoots(**values)


def resolve_optional_root(env_var: str, environ: dict[str, str] | None = None) -> Path | None:
    """Resolve a single optional root, or None if unset/invalid (fail-closed to None)."""
    env = environ if environ is not None else dict(os.environ)
    raw = env.get(env_var)
    if not raw:
        return None
    try:
        return _validate_root(env_var, raw)
    except RootConfigInvalid:
        return None
