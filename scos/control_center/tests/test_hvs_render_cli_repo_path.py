"""Focused tests for the trusted HVS repository override resolver.

Covers ``scos.control_center.hvs_render_cli._hvs_repo_path`` and the
fail-closed bridge response. Uses only temporary directories; neither real
HVS workspace (certified worktree or dirty original) is touched.

Contract under test (Cohort 10E identity wiring):
  * ``SCOS_HVS_REPO_PATH`` is read only from the trusted server process env.
  * A valid absolute directory override is used by both ``cmd_execute`` and
    ``cmd_reconcile`` (via the shared resolver).
  * Missing override preserves the existing default behavior.
  * Relative / empty / nonexistent / file (non-directory) overrides fail
    closed and NEVER fall back to the default dirty HVS repo.
  * The fail-closed error response does not leak the absolute path.
"""
from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
sys.path.insert(0, str(_PACKAGE))

from scos.control_center import hvs_render_cli as cli  # noqa: E402


def _import_fresh():
    """Re-import the module so env changes are observed fresh."""
    import scos.control_center.hvs_render_cli as m

    return importlib.reload(m)


def test_valid_absolute_clean_certified_override_is_used(monkeypatch, tmp_path):
    repo = tmp_path / "hvs-cert"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    (repo / "README.md").write_text("certified", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b.c", "-c", "user.name=t", "commit", "-q", "-m", "init"], check=True)
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, text=True, capture_output=True).stdout.strip()
    monkeypatch.setenv("SCOS_HVS_REPO_PATH", str(repo))
    m = _import_fresh()
    monkeypatch.setattr(m, "CERTIFIED_HVS_HEAD", head)
    assert os.path.normpath(m._hvs_repo_path()) == os.path.normpath(str(repo))


def test_missing_override_fails_closed(monkeypatch):
    monkeypatch.delenv("SCOS_HVS_REPO_PATH", raising=False)
    m = _import_fresh()
    with pytest.raises(RuntimeError):
        m._hvs_repo_path()


def test_relative_override_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("SCOS_HVS_REPO_PATH", "relative/hvs")
    m = _import_fresh()
    with pytest.raises(RuntimeError):
        m._hvs_repo_path()


def test_empty_override_fails_closed(monkeypatch):
    monkeypatch.setenv("SCOS_HVS_REPO_PATH", "   ")
    m = _import_fresh()
    with pytest.raises(RuntimeError):
        m._hvs_repo_path()


def test_nonexistent_override_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("SCOS_HVS_REPO_PATH", str(tmp_path / "does-not-exist"))
    m = _import_fresh()
    with pytest.raises(RuntimeError):
        m._hvs_repo_path()


def test_file_instead_of_directory_fails_closed(monkeypatch, tmp_path):
    f = tmp_path / "not-a-dir.txt"
    f.write_text("x")
    monkeypatch.setenv("SCOS_HVS_REPO_PATH", str(f))
    m = _import_fresh()
    with pytest.raises(RuntimeError):
        m._hvs_repo_path()


def test_invalid_override_never_falls_back_to_default(monkeypatch, tmp_path):
    monkeypatch.setenv("SCOS_HVS_REPO_PATH", str(tmp_path / "nope"))
    m = _import_fresh()
    with pytest.raises(RuntimeError):
        m._hvs_repo_path()
    # Sanity: the call site (cmd_execute / cmd_reconcile) must not silently
    # substitute the default. We assert the resolver cannot return the default
    # when an invalid override is set.
    default = str(Path(__file__).resolve().parents[3] / "hermes-video-studio")
    try:
        got = m._hvs_repo_path()
        assert got != default, "invalid override must not fall back to default"
    except RuntimeError:
        pass  # expected fail-closed


def test_fail_closed_response_does_not_leak_path(monkeypatch, capsys, tmp_path):
    bad = tmp_path / "leak-target"
    monkeypatch.setenv("SCOS_HVS_REPO_PATH", str(bad))
    out_root = tmp_path / "scos-render-output"
    out_root.mkdir()
    monkeypatch.setenv("SCOS_RENDER_OUTPUT_ROOT", str(out_root))
    m = _import_fresh()
    # Exercise the real _main entrypoint with a valid command so the resolver
    # runs and the fail-closed wrapper emits a structured verdict.
    monkeypatch.setattr(sys, "argv", ["hvs_render_cli", "execute"])
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO(
        json.dumps({"project_id": "spp-abcdef123456", "project_revision": 2})))
    rc = m._main()
    assert rc == 0  # transport success; verdict travels inside JSON
    out = json.loads(capsys.readouterr().out)
    assert out == {"ok": False, "error_code": "HVS_REPO_PATH_INVALID"}
    assert str(bad) not in json.dumps(out)
    assert "leak-target" not in json.dumps(out)


def test_execute_and_reconcile_share_resolver(monkeypatch, tmp_path):
    """Both command paths resolve through the same _hvs_repo_path."""
    repo = tmp_path / "hvs-cert"
    repo.mkdir()
    monkeypatch.setenv("SCOS_HVS_REPO_PATH", str(repo))
    m = _import_fresh()
    # Source inspection: both commands call _hvs_repo_path() with no arg.
    import inspect

    for fn_name in ("cmd_execute", "cmd_reconcile"):
        src = inspect.getsource(getattr(m, fn_name))
        assert "_hvs_repo_path()" in src


# --- Cohort 10E explicit HyperFrames identity wiring -----------------------
def _outside_repo_hf_dir() -> Path:
    """A task-owned dir guaranteed OUTSIDE the production repository root.

    The production ``validate_tool_path`` rejects any identity under its
    repo root (``hvs_adapter.__file__`` parents[3]). To stay hermetic and
    environment-independent we place the fake launcher in a *sibling* of that
    root (a sibling can never be under the root), falling back to the OS temp
    dir only when the sibling location is not writable. Auto-disposable.
    """
    import scos.control_center.hvs_adapter as _ha

    repo_root = Path(_ha.__file__).resolve().parents[3]
    sibling = repo_root.parent / f"scos-hf-probe-{os.getpid()}"
    try:
        sibling.mkdir(parents=True, exist_ok=True)
        return sibling
    except OSError:
        pass
    return Path(tempfile.mkdtemp(prefix="scos-hf-probe-"))


def test_resolve_hyperframes_identity_reads_only_trusted_env(monkeypatch):
    # A valid, approved launcher identity is resolved from SCOS_HYPERFRAMES_BIN.
    # The identity MUST live OUTSIDE the repository root (production fails
    # closed on any inside-repo identity). Use a task-owned dir guaranteed to
    # sit outside the production repo root, independent of checkout location.
    with tempfile.TemporaryDirectory(dir=_outside_repo_hf_dir()) as d:
        tool = Path(d) / "hyperframes-0.7.45" / "node_modules" / ".bin"
        tool.mkdir(parents=True)
        hf = tool / "hyperframes.cmd"
        hf.write_bytes(("@echo off" + chr(13) + chr(10)).encode())
        monkeypatch.setenv("SCOS_HYPERFRAMES_BIN", str(hf))
        m = _import_fresh()
        canon, err = m._resolve_hyperframes_identity()
        assert err is None
        assert canon == str(hf)


def test_resolve_hyperframes_identity_missing_fails_closed(monkeypatch):
    monkeypatch.delenv("SCOS_HYPERFRAMES_BIN", raising=False)
    m = _import_fresh()
    canon, err = m._resolve_hyperframes_identity()
    assert canon is None
    assert err == "HF_IDENTITY_MISSING"


def test_resolve_hyperframes_identity_invalid_fails_closed(monkeypatch):
    # An identity outside the approved 0.7.45 tool root is rejected. Placed
    # outside the repository root so the only failing dimension is the
    # unapproved tool root, not the repo boundary.
    with tempfile.TemporaryDirectory(dir=_outside_repo_hf_dir()) as d:
        bad = Path(d) / "evil" / "node_modules" / ".bin" / "hyperframes.cmd"
        bad.parent.mkdir(parents=True)
        bad.write_bytes(("@echo off" + chr(13) + chr(10)).encode())
        monkeypatch.setenv("SCOS_HYPERFRAMES_BIN", str(bad))
        m = _import_fresh()
        canon, err = m._resolve_hyperframes_identity()
        assert canon is None
        assert err == "HF_IDENTITY_OUTSIDE_APPROVED_ROOT"


def test_resolve_hyperframes_identity_never_falls_back_to_bare_name(monkeypatch, tmp_path):
    # An absent/empty identity yields None — there is NO fallback to a bare
    # "hyperframes" discovery via PATH.
    monkeypatch.setenv("SCOS_HYPERFRAMES_BIN", "")
    m = _import_fresh()
    canon, err = m._resolve_hyperframes_identity()
    assert canon is None
    assert err == "HF_IDENTITY_MISSING"


def test_resolve_hyperframes_identity_error_code_does_not_leak_path(monkeypatch, tmp_path):
    secret = tmp_path / "secret-leak-target" / "hyperframes.cmd"
    secret.parent.mkdir(parents=True)
    secret.write_text("")
    monkeypatch.setenv("SCOS_HYPERFRAMES_BIN", str(secret))
    m = _import_fresh()
    canon, err = m._resolve_hyperframes_identity()
    assert canon is None
    # The stable error code must not embed the absolute path.
    assert err is not None
    assert "secret-leak-target" not in err
    assert str(secret) not in (err or "")


# --- Cohort 10F linked-worktree identity resolution ------------------------
def _git_init_commit(repo, message="init"):
    """Init a repo, commit a file, return the HEAD SHA."""
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    (repo / "README.md").write_text("certified\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=a@b.c", "-c", "user.name=t",
                    "commit", "-q", "-m", message], check=True)
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          check=True, text=True, capture_output=True).stdout.strip()


def _make_worktree(main, wt, branch):
    """Create a linked git worktree at ``wt`` on ``branch`` (shared common dir)."""
    subprocess.run(["git", "-C", str(main), "worktree", "add", "-q", "--force",
                    str(wt), "-b", branch], check=True)


def test_linked_worktree_common_loose_ref_resolves(monkeypatch, tmp_path):
    """Cohort 10F root cause: linked worktree whose branch ref lives only in
    the common gitdir must resolve (reproduces the prior HVS_REPO_PATH_INVALID)."""
    main = tmp_path / "main"
    main.mkdir()
    head = _git_init_commit(main)
    wt = tmp_path / "wt"
    _make_worktree(main, wt, "feature")
    monkeypatch.setenv("SCOS_HVS_REPO_PATH", str(wt))
    m = _import_fresh()
    monkeypatch.setattr(m, "CERTIFIED_HVS_HEAD", head)
    assert m._read_git_head(wt) == head
    assert m._hvs_repo_path() == os.fspath(wt)
    assert not (wt / ".git" / "refs" / "heads" / "feature").exists()  # ref lives in common dir


def test_linked_worktree_common_packed_ref_resolves(monkeypatch, tmp_path):
    """Branch ref packed into common packed-refs still resolves."""
    main = tmp_path / "main"
    main.mkdir()
    head = _git_init_commit(main)
    wt = tmp_path / "wt"
    _make_worktree(main, wt, "feature")
    # Pack the shared refs so the branch ref is no longer a loose ref.
    subprocess.run(["git", "-C", str(main), "pack-refs", "--all"], check=True)
    assert not (main / ".git" / "refs" / "heads" / "feature").exists()
    monkeypatch.setenv("SCOS_HVS_REPO_PATH", str(wt))
    m = _import_fresh()
    monkeypatch.setattr(m, "CERTIFIED_HVS_HEAD", head)
    assert m._read_git_head(wt) == head


def test_linked_worktree_detached_head_resolves(monkeypatch, tmp_path):
    """Linked worktree with a detached (direct SHA) HEAD resolves."""
    main = tmp_path / "main"
    main.mkdir()
    head = _git_init_commit(main)
    wt = tmp_path / "wt"
    _make_worktree(main, wt, "feature")
    subprocess.run(["git", "-C", str(wt), "checkout", "--detach", head, "-q"], check=True)
    monkeypatch.setenv("SCOS_HVS_REPO_PATH", str(wt))
    m = _import_fresh()
    monkeypatch.setattr(m, "CERTIFIED_HVS_HEAD", head)
    assert m._read_git_head(wt) == head


def test_linked_worktree_malformed_commondir_fails_closed(monkeypatch, tmp_path):
    """A symbolic ref whose ref cannot be resolved fails closed (no inferred SHA)."""
    main = tmp_path / "main"
    main.mkdir()
    head = _git_init_commit(main)
    wt = tmp_path / "wt"
    _make_worktree(main, wt, "feature")
    # Corrupt the linked gitdir's commondir so refs are unreachable.
    linked_gitdir = wt / ".git"
    assert linked_gitdir.is_file(), "worktree .git must be a pointer file"
    gitdir_target = Path(linked_gitdir.read_text(encoding="utf-8").strip().split("gitdir:", 1)[1].strip())
    (gitdir_target / "commondir").write_text("does-not-exist-gitdir\n", encoding="utf-8")
    monkeypatch.setenv("SCOS_HVS_REPO_PATH", str(wt))
    m = _import_fresh()
    monkeypatch.setattr(m, "CERTIFIED_HVS_HEAD", head)
    with pytest.raises(RuntimeError):
        m._read_git_head(wt)


def test_linked_worktree_wrong_certified_commit_rejected(monkeypatch, tmp_path):
    """Native structure valid but resolved SHA differs -> validation rejects."""
    main = tmp_path / "main"
    main.mkdir()
    head = _git_init_commit(main)
    wt = tmp_path / "wt"
    _make_worktree(main, wt, "feature")
    monkeypatch.setenv("SCOS_HVS_REPO_PATH", str(wt))
    m = _import_fresh()
    monkeypatch.setattr(m, "CERTIFIED_HVS_HEAD", "0" * 40)  # deliberately wrong
    with pytest.raises(RuntimeError):
        m._validate_clean_certified_hvs_repo(wt)


def test_linked_worktree_autocrlf_index_accepted(monkeypatch, tmp_path):
    """A clean worktree checked out with CRLF on disk (core.autocrlf) must be
    accepted as clean by the index validator (proves _index_tracked_paths_clean
    honors git line-ending normalization)."""
    main = tmp_path / "main"
    main.mkdir()
    head = _git_init_commit(main)
    wt = tmp_path / "wt"
    _make_worktree(main, wt, "feature")
    monkeypatch.setenv("SCOS_HVS_REPO_PATH", str(wt))
    m = _import_fresh()
    monkeypatch.setattr(m, "CERTIFIED_HVS_HEAD", head)
    # Touch README with CRLF so on-disk differs from the LF index blob.
    (wt / "README.md").write_bytes(b"certified\r\n")
    assert m._index_tracked_paths_clean(wt, m._git_dir(wt)) is True


def test_current_certified_hvs_topology_resolves_read_only(monkeypatch):
    """H (read-only): the real certified worktree resolves to the certified SHA
    via deterministic resolution, without mutating Git metadata."""
    wt = Path("C:/c/Workspace/_worktrees/hvs-downstream-materialization")
    if not wt.exists():
        pytest.skip("certified HVS worktree not present in this environment")
    m = _import_fresh()
    monkeypatch.setattr(m, "CERTIFIED_HVS_HEAD", "5d684584ee8b774466182c71fca0d1b2cc6f7b88")
    assert m._read_git_head(wt) == "5d684584ee8b774466182c71fca0d1b2cc6f7b88"
    m._validate_clean_certified_hvs_repo(wt)  # must not raise
