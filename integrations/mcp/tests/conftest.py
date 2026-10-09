"""conftest.py — fixtures for the local SCOS MCP surface tests.

Import-path contract
--------------------
``integrations/mcp/`` is a flat module directory (no package ``__init__`` for the
modules themselves), so tests import the modules by inserting the directory into
``sys.path`` — the same way ``integrations/shortgen/tests`` imports its engine.
The ``mcp`` package itself (``mcp.server.fastmcp``) comes from the project venv.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_MCP_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = _MCP_DIR.parents[1]

for _p in (str(_REPO_ROOT), str(_MCP_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import mcp_allow_root as G  # noqa: E402
import scos_video_mcp as M  # noqa: E402  (real module under test)


@pytest.fixture()
def allow_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A real directory used as the MCP allow-root for one test."""
    root = tmp_path / "allow"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv(G.ALLOW_ROOT_ENV, str(root))
    return root.resolve()


@pytest.fixture()
def mcp_module(monkeypatch: pytest.MonkeyPatch, allow_root: Path) -> Any:
    """The real MCP module object, with the allow-root pinned via the env."""
    # Pin the guard's boundary for every call made during this test.
    assert G.get_allow_root() == allow_root
    return M


@pytest.fixture(scope="module")
def _ffmpeg() -> Path:
    return Path(M.FFMPEG)


@pytest.fixture(scope="module")
def sample_video(
    tmp_path_factory: pytest.TempPathFactory, _ffmpeg: Path
) -> Path:
    """A real, tiny (1s, 64x64, 5fps) testsrc mp4 created by the resolved ffmpeg."""
    base = tmp_path_factory.mktemp("scos_mcp_assets")
    out = base / "sample.mp4"
    rc = subprocess.run(
        [str(_ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "testsrc=duration=1:size=64x64:rate=5",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(out)],
        capture_output=True, text=True,
    )
    if rc.returncode != 0 or not out.exists():
        pytest.skip(f"ffmpeg unavailable for asset generation: {rc.stderr[:200]}")
    return out
