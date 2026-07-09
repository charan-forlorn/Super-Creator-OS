"""Pure validation helpers for the Stage 7.1 read surface."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

try:
    from .read_surface_models import ALLOWED_READ_SURFACE_QUERY_TYPES
except ImportError:  # direct-module execution
    from read_surface_models import ALLOWED_READ_SURFACE_QUERY_TYPES

_URL_PREFIXES = ("http://", "https://", "ftp://", "ws://", "wss://")
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
_KNOWN_URL_SCHEMES = ("http", "https", "ftp", "ws", "wss")
_COLLAPSED_SCHEME_RE = re.compile(
    r"^(" + "|".join(_KNOWN_URL_SCHEMES) + r"):[\\/]", re.IGNORECASE
)
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T[^\\/\s]+$")


def validate_no_url_path(value: Any, *, field_name: str = "path") -> str | None:
    text = str(value).strip()
    lowered = text.lower()
    if lowered.startswith(_URL_PREFIXES) or _SCHEME_RE.match(text):
        return f"{field_name} must be a local filesystem path"
    if _COLLAPSED_SCHEME_RE.match(text):
        return f"{field_name} must be a local filesystem path"
    return None


def validate_query_type(query_type: str) -> str | None:
    if query_type not in ALLOWED_READ_SURFACE_QUERY_TYPES:
        return (
            "query_type must be one of "
            f"{list(ALLOWED_READ_SURFACE_QUERY_TYPES)}, got {query_type!r}"
        )
    return None


def validate_limit(limit: int) -> str | None:
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return "limit must be an integer"
    if value < 1 or value > 500:
        return "limit must be between 1 and 500"
    return None


def validate_requested_at(requested_at: str) -> str | None:
    if not str(requested_at).strip():
        return "requested_at is required"
    if not _TIMESTAMP_RE.match(str(requested_at)):
        return "requested_at must be a caller-supplied timestamp string"
    return None


def validate_checked_at(checked_at: str) -> str | None:
    if not str(checked_at).strip():
        return "checked_at is required"
    if not _TIMESTAMP_RE.match(str(checked_at)):
        return "checked_at must be a caller-supplied timestamp string"
    return None


def validate_repo_root_local(repo_root: Any) -> str | None:
    if repo_root is None or not str(repo_root).strip():
        return "repo_root is required"
    url_error = validate_no_url_path(repo_root, field_name="repo_root")
    if url_error:
        return url_error
    try:
        root = Path(repo_root).resolve()
    except (OSError, ValueError) as exc:
        return f"repo_root could not be resolved: {exc}"
    if not root.exists():
        return f"repo_root does not exist: {root}"
    if not root.is_dir():
        return f"repo_root must be a directory: {root}"
    return None


def resolve_repo_path(repo_root: Any, artifact_path: Any, *, field_name: str) -> Path:
    error = validate_no_url_path(artifact_path, field_name=field_name)
    if error:
        raise ValueError(error)
    root = Path(repo_root).resolve()
    candidate = Path(artifact_path)
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise ValueError(f"{field_name} must resolve inside repo_root") from None
    return resolved


def validate_read_only_boundary(*, repo_root: Any, references: tuple[Any, ...] = ()) -> dict:
    root_error = validate_repo_root_local(repo_root)
    blockers: list[str] = []
    warnings: list[str] = []
    if root_error:
        blockers.append(root_error)
        return {
            "ok": False,
            "blockers": tuple(blockers),
            "warnings": tuple(warnings),
            "write_operations_allowed": False,
            "output_path_allowed": False,
        }

    root = Path(repo_root).resolve()
    for reference in references:
        path = str(getattr(reference, "path", reference))
        try:
            resolved = resolve_repo_path(root, path, field_name="reference_path")
        except ValueError as exc:
            blockers.append(str(exc))
            continue
        if not resolved.exists():
            warnings.append(f"missing_reference:{resolved}")

    return {
        "ok": not blockers,
        "blockers": tuple(sorted(blockers)),
        "warnings": tuple(sorted(warnings)),
        "write_operations_allowed": False,
        "output_path_allowed": False,
    }


__all__ = sorted(
    (
        "resolve_repo_path",
        "validate_checked_at",
        "validate_limit",
        "validate_no_url_path",
        "validate_query_type",
        "validate_read_only_boundary",
        "validate_repo_root_local",
        "validate_requested_at",
    )
)
