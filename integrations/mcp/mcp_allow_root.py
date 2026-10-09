"""mcp_allow_root.py — canonical host-path boundary for the local SCOS MCP surface.

Why this exists
---------------
``integrations/mcp/scos_video_mcp.py`` exposes 11 ffmpeg-backed MCP tools, most of
which accept arbitrary host filesystem paths (inputs *and* outputs). Before this
module existed a tool could read or write ANY file the server process could reach
— e.g. ``probe(path="C:/Users/me/.ssh/id_rsa")`` or
``extract_audio(out_path="C:/Windows/System32/drivers/etc/hosts")``. That is the
R-1 risk (arbitrary host file read/write) the closure evidence must retire.

The boundary implemented here is deliberately small, explicit and fail-closed:

1.  One allow-root, resolved from the environment.
2.  Every path a tool receives must resolve (after full symlink/alias expansion)
    INSIDE that allow-root.
3.  Anything else is refused with a stable ``AllowRootViolation`` — the tool never
    touches the filesystem and never invokes ffmpeg.

Resolution order for the allow-root (highest priority first)
------------------------------------------------------------
1. ``SCOS_MCP_ALLOW_ROOT`` environment variable;
2. the ``integrations/`` directory of this repository (the media working area
   the tools were designed for).

Design rules
------------
*   **fail closed.** A missing/invalid allow-root, an unresolvable path, or a
    read error during resolution raises — it never degrades into "allowed".
*   **resolve, don't string-match.** ``Path.resolve()`` expands ``..`` segments,
    junctions and symlinks, so ``allow/a/../../escape`` and a symlinked alias of
    an outside directory are both correctly detected as escapes.
*   **no shell, no execution.** This module only performs ``pathlib``/``os.path``
    operations. It never runs a process and never reads file contents.
*   **portable.** No Windows- or POSIX-only API is required.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = (
    "ALLOW_ROOT_ENV",
    "DEFAULT_ALLOW_ROOT",
    "AllowRootViolation",
    "resolve_allow_root",
    "get_allow_root",
    "guard_path",
    "guard_paths",
)

ALLOW_ROOT_ENV: str = "SCOS_MCP_ALLOW_ROOT"

# ``integrations/mcp/mcp_allow_root.py`` -> parents[2] == repository root.
_REPO_ROOT = Path(__file__).resolve().parents[2]

#: Fallback allow-root: the repository's ``integrations/`` media working area.
DEFAULT_ALLOW_ROOT: Path = _REPO_ROOT / "integrations"


class AllowRootViolation(ValueError):
    """Raised when a requested path escapes the configured allow-root.

    Subclasses :class:`ValueError` so MCP clients see a normal validation-style
    error; ``str(exc)`` is a stable, human-readable reason that names the
    offending path and the active boundary without leaking host internals.
    """

    def __init__(self, path: object, allow_root: Path, reason: str = "outside allow-root") -> None:
        self.path = str(path)
        self.allow_root = str(allow_root)
        self.reason = reason
        super().__init__(
            f"SCOS MCP path guard refused '{self.path}': {reason}. "
            f"All paths must resolve inside the allow-root '{self.allow_root}'."
        )


def resolve_allow_root(explicit: str | os.PathLike[str] | None = None) -> Path:
    """Return the canonical allow-root.

    Precedence: explicit argument > ``SCOS_MCP_ALLOW_ROOT`` env > the repository's
    ``integrations/`` directory. An explicit override that does not name an
    existing directory raises :class:`AllowRootViolation` rather than silently
    falling back — an operator-supplied boundary must never be ignored.
    """
    if explicit is not None:
        candidate = Path(explicit).expanduser()
        if not candidate.is_dir():
            raise AllowRootViolation(candidate, Path("<unset>"), "allow-root is not a directory")
        return candidate.resolve()

    env_value = os.environ.get(ALLOW_ROOT_ENV, "").strip()
    if env_value:
        candidate = Path(env_value).expanduser()
        if not candidate.is_dir():
            raise AllowRootViolation(candidate, Path("<unset>"), "allow-root is not a directory")
        return candidate.resolve()

    if not DEFAULT_ALLOW_ROOT.is_dir():
        raise AllowRootViolation(DEFAULT_ALLOW_ROOT, Path("<unset>"), "default allow-root is missing")
    return DEFAULT_ALLOW_ROOT.resolve()


def get_allow_root() -> Path:
    """Convenience wrapper honouring the environment at call time."""
    return resolve_allow_root()


def guard_path(path: str | os.PathLike[str], allow_root: Path | None = None) -> Path:
    """Validate one path and return its resolved form.

    Returns the fully resolved :class:`~pathlib.Path`, so callers get the
    canonical location for free. Raises :class:`AllowRootViolation` when the
    path resolves outside the allow-root.
    """
    if isinstance(path, bool) or not isinstance(path, str | os.PathLike):
        raise AllowRootViolation(path, allow_root or get_allow_root(), "path is not a string or path")

    text = os.fspath(path)
    if not isinstance(text, str):  # bytes paths are refused: encoding is ambiguous
        raise AllowRootViolation(path, allow_root or get_allow_root(), "bytes paths are not accepted")

    if not text.strip():
        raise AllowRootViolation(path, allow_root or get_allow_root(), "empty path")

    root = (allow_root or get_allow_root()).resolve()

    try:
        resolved = Path(text).expanduser().resolve()
    except OSError as exc:  # permission denied / unresolvable device etc.
        raise AllowRootViolation(path, root, f"path could not be resolved ({exc.__class__.__name__})") from exc

    if resolved != root and root not in resolved.parents:
        raise AllowRootViolation(path, root, "outside allow-root")

    return resolved


def guard_paths(paths, allow_root: Path | None = None) -> list[Path]:
    """Validate an iterable of paths; every element must pass or the call raises."""
    return [guard_path(p, allow_root) for p in paths]
