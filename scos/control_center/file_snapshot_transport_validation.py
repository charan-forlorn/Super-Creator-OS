"""Stage 8.2 validation for manual file snapshot refresh transport."""

from __future__ import annotations

from pathlib import Path

_URL_MARKERS = ("://", "http:", "https:", "ws:", "wss:", "ftp:", "file:")
_FORBIDDEN_TOKENS = (
    "Web" + "Socket",
    "Event" + "Source",
    "set" + "Interval",
    "set" + "Timeout",
    "fet" + "ch",
    "XML" + "HttpRequest",
    "axi" + "os",
    "sub" + "process",
    "os." + "system",
    "shell" + "=True",
    "requ" + "ests",
    "http." + "server",
    "socket" + "server",
)


def validate_no_url_path(path_value: str) -> tuple[bool, tuple[str, ...]]:
    text = str(path_value)
    lowered = text.lower()
    errors = tuple(
        f"path must not contain URL or remote marker: {marker}"
        for marker in _URL_MARKERS
        if marker in lowered
    )
    return not errors, errors


def validate_path_contained(*, parent, child) -> bool:
    try:
        parent_path = Path(parent).resolve()
        child_path = Path(child).resolve()
        child_path.relative_to(parent_path)
    except (OSError, ValueError):
        return False
    return True


def validate_local_repo_root(repo_root) -> tuple[bool, tuple[str, ...]]:
    ok, errors = validate_no_url_path(str(repo_root))
    all_errors = list(errors)
    root = Path(repo_root).resolve()
    if not root.exists() or not root.is_dir():
        all_errors.append(f"repo_root must be an existing local directory: {repo_root}")
    return not all_errors and ok, tuple(sorted(all_errors))


def validate_snapshot_output_path(*, repo_root, output_path) -> tuple[bool, tuple[str, ...]]:
    all_errors: list[str] = []
    ok, errors = validate_no_url_path(str(output_path))
    all_errors.extend(errors)
    root_ok, root_errors = validate_local_repo_root(repo_root)
    all_errors.extend(root_errors)
    if root_ok:
        root = Path(repo_root).resolve()
        path = Path(output_path)
        resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
        if not validate_path_contained(parent=root, child=resolved):
            all_errors.append("output_path must resolve inside repo_root")
        if resolved.exists() and resolved.is_dir():
            all_errors.append("output_path must be a file path, not a directory")
    return ok and not all_errors, tuple(sorted(set(all_errors)))


def validate_checked_at(checked_at: str) -> tuple[bool, tuple[str, ...]]:
    text = str(checked_at)
    errors: list[str] = []
    if not text.strip():
        errors.append("checked_at must be caller-supplied and non-empty")
    ok, path_errors = validate_no_url_path(text)
    errors.extend(path_errors)
    return ok and not errors, tuple(sorted(set(errors)))


def validate_payload_is_json_object(payload: dict) -> tuple[bool, tuple[str, ...]]:
    if not isinstance(payload, dict):
        return False, ("payload must be a JSON object",)
    return True, ()


def validate_no_forbidden_transport_behavior(source_text: str) -> tuple[bool, tuple[str, ...]]:
    text = str(source_text)
    findings = tuple(
        f"forbidden transport behavior token found: {token}"
        for token in _FORBIDDEN_TOKENS
        if token in text
    )
    return not findings, findings


__all__ = sorted(
    (
        "validate_checked_at",
        "validate_local_repo_root",
        "validate_no_forbidden_transport_behavior",
        "validate_no_url_path",
        "validate_path_contained",
        "validate_payload_is_json_object",
        "validate_snapshot_output_path",
    )
)
