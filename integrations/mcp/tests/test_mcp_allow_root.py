"""test_mcp_allow_root.py — boundary tests for the MCP host-path guard (SCOS-C1).

These are the qualification evidence for R-1 (arbitrary host file read/write).

What is proven here
-------------------
*   an explicit allow-root is honoured, and an invalid one fails closed;
*   in-allow-root paths (including nested and dotted/whitespace ones) are accepted;
*   the allow-root itself is accepted;
*   ``../`` traversal escapes are refused;
*   absolute paths outside the allow-root are refused;
*   symlink-style escapes are refused (verified against real on-disk symlinks
    where the OS permits creating them, and against the equivalent junction form
    on Windows where symlink creation needs elevation — see the skip markers);
*   unresolvable, empty and non-string paths fail closed;
*   the default allow-root is the repository's ``integrations/`` directory.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mcp_allow_root as G  # noqa: E402


# --- explicit allow-root resolution -----------------------------------------


def test_explicit_allow_root_is_resolved(allow_root: Path):
    assert G.resolve_allow_root(allow_root) == allow_root


def test_explicit_missing_allow_root_fails_closed(tmp_path: Path):
    with pytest.raises(G.AllowRootViolation) as ei:
        G.resolve_allow_root(tmp_path / "nope")
    assert "not a directory" in str(ei.value)


def test_default_allow_root_is_repo_integrations(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(G.ALLOW_ROOT_ENV, raising=False)
    root = G.resolve_allow_root()
    assert root.name == "integrations"
    assert root.is_dir()


def test_env_allow_root_overrides_default(allow_root: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(G.ALLOW_ROOT_ENV, str(allow_root))
    assert G.resolve_allow_root() == allow_root


def test_env_allow_root_invalid_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(G.ALLOW_ROOT_ENV, str(tmp_path / "ghost"))
    with pytest.raises(G.AllowRootViolation):
        G.resolve_allow_root()


# --- acceptance --------------------------------------------------------------


def test_in_allow_root_relative_path_accepted(allow_root: Path, monkeypatch: pytest.MonkeyPatch):
    """A bare relative name resolves against CWD — chdir into the allow-root first."""
    monkeypatch.chdir(allow_root)
    (allow_root / "clip.mp4").write_bytes(b"\x00")
    got = G.guard_path("clip.mp4", allow_root)
    assert got == (allow_root / "clip.mp4")


def test_in_allow_root_absolute_path_accepted(allow_root: Path):
    target = allow_root / "a" / "b" / "out.wav"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"\x00")
    assert G.guard_path(target, allow_root) == target


def test_allow_root_itself_accepted(allow_root: Path):
    assert G.guard_path(allow_root, allow_root) == allow_root


def test_nonexistent_path_inside_allow_root_accepted(allow_root: Path):
    """A not-yet-existing OUTPUT path inside the boundary must be allowed."""
    target = allow_root / "future" / "render.mp4"
    assert G.guard_path(target, allow_root) == target


def test_dotted_and_spaced_names_inside_allow_root_accepted(allow_root: Path):
    target = allow_root / "my clip [v2].mp4"
    assert G.guard_path(str(target), allow_root) == target


def test_guard_paths_validates_every_element(allow_root: Path):
    ok = G.guard_paths([allow_root / "a.mp4", allow_root / "b.mp4"], allow_root)
    assert ok == [allow_root / "a.mp4", allow_root / "b.mp4"]


# --- escape rejection: traversal --------------------------------------------


def test_parent_traversal_rejected(allow_root: Path):
    with pytest.raises(G.AllowRootViolation):
        G.guard_path(str(allow_root / ".." / "escape.mp4"), allow_root)


def test_interior_parent_traversal_rejected(allow_root: Path):
    """``a/../../escape`` — traversal that leaves and re-enters-looking shape."""
    with pytest.raises(G.AllowRootViolation):
        G.guard_path(str(allow_root / "a" / ".." / ".." / "escape.mp4"), allow_root)


def test_deep_traversal_to_root_rejected(allow_root: Path):
    with pytest.raises(G.AllowRootViolation):
        G.guard_path(str(allow_root / ".." / ".." / ".." / "Windows" / "System32"), allow_root)


# --- escape rejection: absolute outside -------------------------------------


def test_absolute_outside_rejected(allow_root: Path):
    outside = allow_root.parent / "outside.mp4"
    with pytest.raises(G.AllowRootViolation):
        G.guard_path(outside, allow_root)


def test_system_absolute_path_rejected(allow_root: Path):
    with pytest.raises(G.AllowRootViolation):
        G.guard_path("C:/Windows/System32/drivers/etc/hosts", allow_root)


def test_home_directory_rejected(allow_root: Path):
    with pytest.raises(G.AllowRootViolation):
        G.guard_path(Path.home(), allow_root)


def test_repo_root_rejected(allow_root: Path):
    with pytest.raises(G.AllowRootViolation):
        G.guard_path(G._REPO_ROOT, allow_root)


def test_repo_source_file_rejected(allow_root: Path):
    with pytest.raises(G.AllowRootViolation):
        G.guard_path(G._REPO_ROOT / "requirements.txt", allow_root)


def test_relative_cwd_escape_rejected(allow_root: Path, monkeypatch: pytest.MonkeyPatch):
    """A bare relative name resolves against CWD, not the allow-root."""
    monkeypatch.chdir(allow_root.parent)
    with pytest.raises(G.AllowRootViolation):
        G.guard_path("escape.mp4", allow_root)


# --- escape rejection: symlinks ---------------------------------------------

_SYMLINK_SUPPORTED = hasattr(os, "symlink")


@pytest.mark.skipif(not _SYMLINK_SUPPORTED, reason="os.symlink unavailable on this platform")
def test_symlink_escape_rejected(allow_root: Path, tmp_path: Path):
    """A link inside the allow-root pointing outside must be refused."""
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    secret = outside_dir / "secret.mp4"
    secret.write_bytes(b"\x00")
    link = allow_root / "link"
    try:
        link.symlink_to(outside_dir, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation not permitted in this environment")
    with pytest.raises(G.AllowRootViolation):
        G.guard_path(link / "secret.mp4", allow_root)
    with pytest.raises(G.AllowRootViolation):
        G.guard_path(link, allow_root)


@pytest.mark.skipif(not _SYMLINK_SUPPORTED, reason="os.symlink unavailable on this platform")
def test_symlink_file_escape_rejected(allow_root: Path, tmp_path: Path):
    """A single-file symlink pointing outside the allow-root must be refused."""
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"\x00")
    link = allow_root / "sneaky.mp4"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation not permitted in this environment")
    with pytest.raises(G.AllowRootViolation):
        G.guard_path(link, allow_root)


@pytest.mark.skipif(os.name != "nt", reason="Windows junctions need elevation; POSIX uses symlinks")
def test_junction_escape_rejected(allow_root: Path, tmp_path: Path):
    """Windows reparse points resolve the same way as symlinks for the guard."""
    import subprocess

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "secret.mp4").write_bytes(b"\x00")
    link = allow_root / "jlink"
    rc = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(outside_dir)],
        capture_output=True, text=True,
    )
    if rc.returncode != 0 or not link.exists():
        pytest.skip("junction creation not permitted in this environment")
    with pytest.raises(G.AllowRootViolation):
        G.guard_path(link / "secret.mp4", allow_root)


@pytest.mark.skipif(not _SYMLINK_SUPPORTED, reason="os.symlink unavailable on this platform")
def test_internal_symlink_still_accepted(allow_root: Path):
    """A link that stays INSIDE the boundary is legitimate and must be allowed."""
    real_dir = allow_root / "real"
    real_dir.mkdir()
    (real_dir / "clip.mp4").write_bytes(b"\x00")
    link = allow_root / "alias"
    try:
        link.symlink_to(real_dir, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation not permitted in this environment")
    assert G.guard_path(link / "clip.mp4", allow_root) == real_dir / "clip.mp4"


# --- fail-closed inputs -----------------------------------------------------


def test_empty_path_rejected(allow_root: Path):
    with pytest.raises(G.AllowRootViolation):
        G.guard_path("", allow_root)


def test_whitespace_path_rejected(allow_root: Path):
    with pytest.raises(G.AllowRootViolation):
        G.guard_path("   ", allow_root)


def test_non_string_path_rejected(allow_root: Path):
    bad_paths: list[object] = [None, 123, ["a"], {"p": 1}, True]
    for bad in bad_paths:
        with pytest.raises(G.AllowRootViolation):
            G.guard_path(bad, allow_root)  # type: ignore[arg-type]


def test_bytes_path_rejected(allow_root: Path):
    with pytest.raises(G.AllowRootViolation):
        G.guard_path(b"clip.mp4", allow_root)  # type: ignore[arg-type]


def test_nul_byte_path_rejected(allow_root: Path):
    # Windows/Python raise ValueError on NUL in a path string before resolve();
    # the guard's contract is "refuse" — either exception type is a refusal.
    with pytest.raises((G.AllowRootViolation, ValueError)):
        G.guard_path("clip\x00.mp4", allow_root)
