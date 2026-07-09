"""Stage 7.7 adapter activation preflight input validation."""

from __future__ import annotations

from pathlib import Path

try:
    from .adapter_activation_preflight_models import (
        PREFLIGHT_ACTIVATION_MODES,
        PREFLIGHT_REJECTED_ACTIVATION_MODES,
        PREFLIGHT_TARGET_ADAPTERS,
        AdapterActivationPreflightError,
    )
except ImportError:  # direct-module execution
    from adapter_activation_preflight_models import (
        PREFLIGHT_ACTIVATION_MODES,
        PREFLIGHT_REJECTED_ACTIVATION_MODES,
        PREFLIGHT_TARGET_ADAPTERS,
        AdapterActivationPreflightError,
    )

_URL_MARKERS = ("://", "http:", "https:", "file:", "ftp:")
_SENSITIVE_MARKERS = (
    "OPEN" + "AI_" + "API_" + "KEY",
    "ANTHROPIC_" + "API_" + "KEY",
    "API_" + "KEY",
    "SEC" + "RET",
    "TOK" + "EN",
    "PASS" + "WORD",
    "COO" + "KIE",
    "sk-",
)


def _has_url_marker(value: str) -> bool:
    lowered = value.lower()
    return any(marker.lower() in lowered for marker in _URL_MARKERS)


def _has_secret_marker(value: str) -> bool:
    upper = value.upper()
    return any(marker.upper() in upper for marker in _SENSITIVE_MARKERS)


def validate_no_secret_or_remote_text(field_name: str, value: object) -> tuple[str, ...]:
    text = "" if value is None else str(value)
    errors: list[str] = []
    if _has_url_marker(text):
        errors.append(f"{field_name} must not contain URL or remote path markers")
    if _has_secret_marker(text):
        errors.append(f"{field_name} must not contain secret/token/credential markers")
    return tuple(errors)


def validate_repo_root(repo_root) -> tuple[Path | None, tuple[str, ...]]:
    errors = validate_no_secret_or_remote_text("repo_root", repo_root)
    if errors:
        return None, errors
    root = Path(repo_root).resolve()
    if not root.exists() or not root.is_dir():
        return None, (f"repo_root must be an existing local directory: {repo_root}",)
    return root, ()


def validate_output_path(repo_root: Path, output_path) -> tuple[Path | None, tuple[str, ...]]:
    if output_path is None:
        return None, ()
    errors = list(validate_no_secret_or_remote_text("output_path", output_path))
    if errors:
        return None, tuple(errors)
    path = Path(output_path)
    resolved = path.resolve() if path.is_absolute() else (repo_root / path).resolve()
    try:
        resolved.relative_to(repo_root)
    except ValueError:
        errors.append("output_path must resolve inside repo_root")
    return (None if errors else resolved), tuple(errors)


def validate_adapter_activation_preflight_inputs(
    *,
    repo_root,
    checked_at: str,
    target_adapter: str | None = None,
    requested_activation_mode: str = "preflight_only",
    allow_real_dispatch: bool = False,
    output_path=None,
) -> tuple[Path | None, Path | None, AdapterActivationPreflightError | None]:
    checked_text = str(checked_at)
    errors: list[str] = []
    if not checked_text.strip():
        errors.append("checked_at must be caller-supplied and non-empty")
    errors.extend(validate_no_secret_or_remote_text("checked_at", checked_at))
    if target_adapter is not None:
        target = str(target_adapter)
        if target not in PREFLIGHT_TARGET_ADAPTERS:
            errors.append(f"target_adapter must be one of {list(PREFLIGHT_TARGET_ADAPTERS)} or None")
        errors.extend(validate_no_secret_or_remote_text("target_adapter", target))
    mode = str(requested_activation_mode)
    if mode in PREFLIGHT_REJECTED_ACTIVATION_MODES:
        errors.append(f"requested_activation_mode {mode!r} is forbidden in Stage 7.7")
    elif mode not in PREFLIGHT_ACTIVATION_MODES:
        errors.append(f"requested_activation_mode must be one of {list(PREFLIGHT_ACTIVATION_MODES)}")
    errors.extend(validate_no_secret_or_remote_text("requested_activation_mode", mode))
    root, root_errors = validate_repo_root(repo_root)
    errors.extend(root_errors)
    resolved_output: Path | None = None
    if root is not None:
        resolved_output, output_errors = validate_output_path(root, output_path)
        errors.extend(output_errors)

    if errors:
        return None, None, AdapterActivationPreflightError.of(
            "INVALID_ADAPTER_PREFLIGHT_INPUT",
            errors[0],
            checked_at=checked_text,
            blockers=tuple(errors),
        )
    return root, resolved_output, None


__all__ = sorted(
    (
        "validate_adapter_activation_preflight_inputs",
        "validate_no_secret_or_remote_text",
        "validate_output_path",
        "validate_repo_root",
    )
)
