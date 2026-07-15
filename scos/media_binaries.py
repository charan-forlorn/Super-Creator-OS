"""Central resolver for media executables (ffmpeg / ffprobe).

Problem this fixes
------------------
SCOS previously invoked ffmpeg/ffprobe via bare argv tokens
(``["ffmpeg", ...]``) or a fragile ``shutil.which(x) or x`` fallback that
silently degraded to ambient-PATH resolution. That made production and
integration behavior depend on the *launching* process's PATH, which is not
hermetic and is fragile on clean CI hosts or containers.

This module is the single source of truth for resolving the absolute executable
path used in every subprocess argv list. It never executes anything, never
shells out, and never hardcodes a user-specific path.

Resolution precedence
----------------------
1. explicit ``configured`` argument (highest priority);
2. environment override (``SCOS_FFMPEG_BIN`` / ``SCOS_FFPROBE_BIN``);
3. ``shutil.which(name)`` PATH discovery;
4. fail closed with a stable :class:`MediaBinaryResolutionError`.

If an explicit override (argument or env) is supplied but invalid, we do
**not** silently fall back to PATH — that would defeat the operator's intent.
Only the implicit PATH discovery (no override supplied) may fail softly into
the final failure path.

Security contract
-----------------
* argv-list only; callers pass the returned ``str`` into a list, never into a
  shell string. No shell is ever spawned by this module.
* Resolution performs only existence/type checks (``os.path`` / ``pathlib``).
  The executable is never run during resolution.
* Returned paths are normalized via ``os.path.abspath`` so downstream code
  cannot be ambushed by a relative, cwd-dependent token.
* No user-specific absolute path is baked into this module.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Mapping
from os import PathLike
from typing import Final

__all__ = (
    "FFMPEG_ENV",
    "FFPROBE_ENV",
    "MediaBinaryResolutionError",
    "resolve_media_binary",
    "resolve_ffmpeg",
    "resolve_ffprobe",
)

FFMPEG_ENV: Final[str] = "SCOS_FFMPEG_BIN"
FFPROBE_ENV: Final[str] = "SCOS_FFPROBE_BIN"

# Canonical bare binary names used for implicit PATH discovery when no override
# is supplied.
_FFMPEG_NAME: Final[str] = "ffmpeg"
_FFPROBE_NAME: Final[str] = "ffprobe"


class MediaBinaryResolutionError(RuntimeError):
    """Raised when a required media executable cannot be resolved.

    Carries a stable, actionable message so operators can diagnose missing
    binaries or invalid overrides without guessing.
    """


def _as_text(value: str | PathLike[str] | None) -> str | None:
    if value is None:
        return None
    # PathLike -> str via os.fspath keeps Windows backslash spelling intact.
    return os.fspath(value)


def _validate(candidate: str, name: str, source: str) -> str:
    """Validate a resolved candidate path.

    Returns the normalized absolute path on success. Raises
    :class:`MediaBinaryResolutionError` with a stable message otherwise.
    """
    if not candidate:
        raise MediaBinaryResolutionError(
            f"{name}: resolved empty executable path from {source}; "
            f"set {name.upper()}_BIN or ensure {name} is on PATH"
        )
    normalized = os.path.abspath(candidate)
    if not os.path.exists(normalized):
        raise MediaBinaryResolutionError(
            f"{name}: executable not found at resolved path '{normalized}' "
            f"(source: {source}); install {name} or point {name.upper()}_BIN at it"
        )
    if os.path.isdir(normalized):
        raise MediaBinaryResolutionError(
            f"{name}: resolved path '{normalized}' is a directory, not an "
            f"executable (source: {source})"
        )
    if not os.path.isfile(normalized):
        raise MediaBinaryResolutionError(
            f"{name}: resolved path '{normalized}' is not a regular file "
            f"(source: {source})"
        )
    return normalized


def resolve_media_binary(
    name: str,
    *,
    configured: str | PathLike[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Resolve an absolute path for a media executable.

    Precedence:
        1. explicit ``configured`` argument;
        2. ``SCOS_<NAME>_BIN`` environment override;
        3. ``shutil.which(name)`` PATH discovery;
        4. fail closed.

    An invalid explicit override (argument or env) is a hard error — we do
    not fall back to PATH. Implicit PATH discovery (no override supplied) may
    simply fail, surfacing the final actionable error.

    Args:
        name: bare binary name used for implicit PATH discovery (e.g. "ffmpeg").
        configured: explicit path/name override. Highest priority.
        environ: optional mapping to read env overrides from (defaults to
            ``os.environ``). Injectable for isolated tests.

    Returns:
        Normalized absolute executable path (``str``).

    Raises:
        MediaBinaryResolutionError: when no valid executable can be resolved.
    """
    if not name:
        raise MediaBinaryResolutionError("resolve_media_binary requires a non-empty name")

    env = os.environ if environ is None else environ

    # 1) explicit argument. Note: an explicit empty string is treated as
    # an INVALID override (fail-closed), distinct from ``configured=None``
    # which means "no explicit argument, fall through". This prevents a
    # misconfiguration (operator passing "") from silently degrading to
    # ambient PATH discovery.
    configured_text = _as_text(configured)
    if configured_text is not None:
        return _validate(configured_text, name, "explicit configured argument")

    # 2) environment override (SCOS_<NAME>_BIN).
    env_key = f"SCOS_{name.upper()}_BIN"
    env_value = env.get(env_key) if env is not None else None
    if env_value:
        return _validate(env_value, name, f"environment override {env_key}")

    # 3) implicit PATH discovery. Honor the PATH from the supplied
    # environment (or os.environ) so an operator-provided PATH and the
    # injected test environment are both respected, matching the precedence
    # of the explicit/env overrides above.
    path_env = env.get("PATH") if env is not None else None
    which = shutil.which(name, path=path_env)
    if which:
        # shutil.which already validates executability on PATH; normalize anyway.
        return _validate(which, name, "shutil.which PATH discovery")

    # 4) fail closed.
    raise MediaBinaryResolutionError(
        f"{name}: could not resolve executable. Provide an explicit path via the "
        f"configured argument or the {env_key} environment variable, or ensure "
        f"{name} is installed and discoverable on PATH."
    )


def resolve_ffmpeg(
    configured: str | PathLike[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Resolve the ffmpeg executable (see :func:`resolve_media_binary`)."""
    return resolve_media_binary(_FFMPEG_NAME, configured=configured, environ=environ)


def resolve_ffprobe(
    configured: str | PathLike[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Resolve the ffprobe executable (see :func:`resolve_media_binary`)."""
    return resolve_media_binary(_FFPROBE_NAME, configured=configured, environ=environ)
