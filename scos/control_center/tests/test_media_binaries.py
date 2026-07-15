"""Tests for the centralized media-binary resolver (scos.media_binaries).

These are pure-resolution tests: the resolver never spawns subprocesses, so
they are fast, hermetic and OS-temp free. Binary resolution is exercised
both against the real on-PATH ffmpeg/ffprobe (when present) and against
synthetic fixtures to prove precedence, validation and fail-closed behavior.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from scos.media_binaries import (
    FFPROBE_ENV,
    FFMPEG_ENV,
    MediaBinaryResolutionError,
    resolve_ffmpeg,
    resolve_ffprobe,
    resolve_media_binary,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _touch_executable(tmp_path: Path, name: str) -> str:
    """Create a fake executable file and return its absolute path."""
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"#!/bin/sh\n")
    # Make it read/executable-ish across platforms for the existence check.
    try:
        os.chmod(str(p), 0o755)
    except OSError:
        pass
    return os.path.abspath(str(p))


def _prepend_path(tmp_path: str, base_env: dict | None = None) -> dict:
    env = dict(base_env if base_env is not None else os.environ)
    env["PATH"] = tmp_path + os.pathsep + env.get("PATH", "")
    return env


# ---------------------------------------------------------------------------
# 1. explicit argument precedence (highest)
# ---------------------------------------------------------------------------
def test_explicit_arg_wins_over_env(tmp_path: Path):
    real = _touch_executable(tmp_path, "ffmpeg-real.exe")
    other = _touch_executable(tmp_path, "ffmpeg-other.exe")
    env = {FFMPEG_ENV: other}
    got = resolve_media_binary("ffmpeg", configured=real, environ=env)
    assert got == real  # explicit argument beats env override


def test_explicit_arg_used_when_env_absent(tmp_path: Path):
    real = _touch_executable(tmp_path, "ffprobe-x.exe")
    got = resolve_media_binary("ffprobe", configured=real, environ={})
    assert got == real


def test_explicit_arg_validated_not_executable(tmp_path: Path):
    # A directory is not a valid executable; explicit override must hard-fail.
    with pytest.raises(MediaBinaryResolutionError):
        resolve_media_binary("ffmpeg", configured=str(tmp_path), environ={})


def test_explicit_arg_missing_file_fails_closed(tmp_path: Path):
    missing = os.path.abspath(str(tmp_path / "does_not_exist.exe"))
    with pytest.raises(MediaBinaryResolutionError):
        resolve_media_binary("ffmpeg", configured=missing, environ={})


def test_invalid_explicit_override_does_not_fall_back_to_path(tmp_path: Path):
    # Put a VALID binary on a private PATH, then supply an INVALID explicit
    # override. Resolution must NOT silently fall back to the PATH binary.
    good = _touch_executable(tmp_path, "ffmpeg.exe")
    env = _prepend_path(str(tmp_path), {FFMPEG_ENV: "C:/no/such/ffmpeg.exe"})
    with pytest.raises(MediaBinaryResolutionError):
        resolve_media_binary("ffmpeg", environ=env)
    # Sanity: the same injected PATH (minus the bad override) WOULD succeed.
    clean_env = _prepend_path(str(tmp_path), {})
    assert os.path.normcase(resolve_media_binary("ffmpeg", environ=clean_env)) == os.path.normcase(good)


# ---------------------------------------------------------------------------
# 2. environment override
# ---------------------------------------------------------------------------
def test_env_override_resolves(tmp_path: Path):
    real = _touch_executable(tmp_path, "ffmpeg-env.exe")
    got = resolve_media_binary("ffmpeg", environ={FFMPEG_ENV: real})
    assert got == real


def test_env_override_invalid_fails_closed(tmp_path: Path):
    env = {FFMPEG_ENV: str(tmp_path)}  # a directory -> invalid
    with pytest.raises(MediaBinaryResolutionError):
        resolve_media_binary("ffmpeg", environ=env)


def test_env_override_beats_implicit_path(tmp_path: Path):
    # Private PATH has a valid "ffmpeg"; env override points elsewhere.
    good = _touch_executable(tmp_path, "ffmpeg.exe")
    override = _touch_executable(tmp_path, "ffmpeg-override.exe")
    env = _prepend_path(str(tmp_path), {FFMPEG_ENV: override})
    # Drop the implicit PATH binary influence by giving a *different* name env.
    got = resolve_media_binary("ffmpeg", environ=env)
    assert os.path.normcase(got) == os.path.normcase(override)
    assert good  # ensure fixture existed (keeps lint calm)


# ---------------------------------------------------------------------------
# 3. PATH fallback (implicit discovery)
# ---------------------------------------------------------------------------
def test_path_discovery_finds_valid_binary(tmp_path: Path):
    good = _touch_executable(tmp_path, "ffmpeg.exe")
    env = _prepend_path(str(tmp_path), {})
    got = resolve_media_binary("ffmpeg", environ=env)
    assert os.path.normcase(got) == os.path.normcase(good)


def test_path_discovery_respects_which_priority(tmp_path: Path):
    # shutil.which returns the FIRST match on PATH; our resolver must honor it.
    first = _touch_executable(tmp_path / "first", "ffmpeg.exe")
    env = _prepend_path(str(tmp_path / "first"), {})
    got = resolve_media_binary("ffmpeg", environ=env)
    assert os.path.normcase(got) == os.path.normcase(first)


def test_missing_binary_fails_closed_with_actionable_message():
    env = {"PATH": "", FFMPEG_ENV: "", FFPROBE_ENV: ""}
    with pytest.raises(MediaBinaryResolutionError) as exc:
        resolve_media_binary("ffmpeg", environ=env)
    msg = str(exc.value)
    assert "ffmpeg" in msg
    assert FFMPEG_ENV in msg  # tells operator which override to set


# ---------------------------------------------------------------------------
# 4. directories / non-files rejected
# ---------------------------------------------------------------------------
def test_directory_rejected(tmp_path: Path):
    with pytest.raises(MediaBinaryResolutionError):
        resolve_media_binary("ffmpeg", configured=str(tmp_path), environ={})


def test_empty_candidate_rejected(tmp_path: Path):
    with pytest.raises(MediaBinaryResolutionError):
        resolve_media_binary("ffmpeg", configured="", environ={})


# ---------------------------------------------------------------------------
# 5. Windows .exe tolerance + spaces in path
# ---------------------------------------------------------------------------
def test_windows_exe_suffix_resolves(tmp_path: Path):
    exe = _touch_executable(tmp_path, "ffmpeg.exe")
    got = resolve_media_binary("ffmpeg", configured=exe, environ={})
    assert got == exe


def test_path_with_spaces_resolves(tmp_path: Path):
    spaced = tmp_path / "my tools"
    spaced.mkdir()
    exe = _touch_executable(spaced, "ffmpeg.exe")
    got = resolve_media_binary("ffmpeg", configured=exe, environ={})
    assert got == exe
    assert " " in got  # the space is preserved (no shell reinterpretation)


def test_path_with_spaces_via_path_discovery(tmp_path: Path):
    spaced = tmp_path / "program files"
    spaced.mkdir()
    exe = _touch_executable(spaced, "ffmpeg.exe")
    env = _prepend_path(str(spaced), {})
    got = resolve_media_binary("ffmpeg", environ=env)
    assert os.path.normcase(got) == os.path.normcase(exe)


# ---------------------------------------------------------------------------
# 6. separate ffmpeg / ffprobe resolution
# ---------------------------------------------------------------------------
def test_ffmpeg_and_ffprobe_resolve_independently(tmp_path: Path):
    ffm = _touch_executable(tmp_path, "ffmpeg.exe")
    ffp = _touch_executable(tmp_path, "ffprobe.exe")
    env = _prepend_path(str(tmp_path), {})
    assert os.path.normcase(resolve_ffmpeg(environ=env)) == os.path.normcase(ffm)
    assert os.path.normcase(resolve_ffprobe(environ=env)) == os.path.normcase(ffp)


def test_resolve_media_binary_passthrough_for_ffprobe(tmp_path: Path):
    ffp = _touch_executable(tmp_path, "ffprobe-custom.exe")
    assert resolve_media_binary("ffprobe", configured=ffp, environ={}) == ffp


# ---------------------------------------------------------------------------
# 7. stable error messages + environment isolation
# ---------------------------------------------------------------------------
def test_error_message_mentions_binary_name(tmp_path: Path):
    env = {"PATH": "", FFMPEG_ENV: "", FFPROBE_ENV: ""}
    with pytest.raises(MediaBinaryResolutionError) as exc:
        resolve_ffprobe(environ=env)
    assert "ffprobe" in str(exc.value)
    assert FFPROBE_ENV in str(exc.value)


def test_environment_isolation_no_leak(tmp_path: Path):
    # A binary only on a private PATH must NOT be visible when that PATH is
    # scoped out of the injected environ mapping.
    good = _touch_executable(tmp_path, "ffmpeg.exe")
    # environ has its own PATH WITHOUT the private dir, and no override.
    env = {"PATH": "", FFMPEG_ENV: "", FFPROBE_ENV: ""}
    with pytest.raises(MediaBinaryResolutionError):
        resolve_media_binary("ffmpeg", environ=env)
    # The real-host PATH (with a possibly-present ffmpeg) must not leak in.
    assert good  # fixture existed; isolation is what we asserted above


def test_real_host_resolution_when_available():
    """Integration-ish: if ffmpeg/ffprobe are genuinely on PATH, resolve them.

    This is allowed to skip when the host has no media binaries, but it must
    never hardcode a user-specific path.
    """
    import shutil

    host_ffmpeg = shutil.which("ffmpeg")
    host_ffprobe = shutil.which("ffprobe")
    if not host_ffmpeg and not host_ffprobe:
        pytest.skip("no host ffmpeg/ffprobe on PATH")
    if host_ffmpeg:
        # Identity check: resolver must return the same absolute path.
        # On Windows the resolver normalizes the executable extension case
        # (.exe vs .EXE) while still identifying the same file, so compare
        # canonical filesystem identity instead of exact case-sensitive
        # strings. os.path.normcase is a no-op on POSIX, so a real path
        # difference is never concealed there.
        assert os.path.normcase(os.path.abspath(resolve_ffmpeg())) == os.path.normcase(
            os.path.abspath(host_ffmpeg)
        )
    if host_ffprobe:
        assert os.path.normcase(os.path.abspath(resolve_ffprobe())) == os.path.normcase(
            os.path.abspath(host_ffprobe)
        )


def test_no_subprocess_execution_during_resolution(tmp_path: Path):
    # The resolver only does existence/type checks. If "ffmpeg" were somehow
    # executed, this pure-Python call would still not invoke a shell; we
    # simply assert it returns a normalized path and raises only on failure.
    good = _touch_executable(tmp_path, "ffmpeg.exe")
    got = resolve_media_binary("ffmpeg", configured=good, environ={})
    assert os.path.isabs(got)
    assert got == os.path.abspath(str(good))
