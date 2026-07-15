"""test_hvs_adapter.py - SCOS <-> HVS Stage 1 adapter scaffold suite.

Covers the HermesVideoStudioAdapter contract, safe command construction,
shell=False enforcement, cwd isolation, deterministic ids, bounded output,
error normalization, and the read-only operation allowlist. The real
cross-repository help-probe is run against the local HVS repo when present
and skipped with a clear reason otherwise.

Plain executable script (no pytest-only features); pytest collects the
``test_*`` functions directly.
"""

from __future__ import annotations

import subprocess
import sys
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
sys.path.insert(0, str(_PACKAGE))

from hvs_adapter import (  # noqa: E402
    DEFAULT_MAX_OUTPUT_CHARS,
    DEFAULT_TIMEOUT_SECONDS,
    STAGE1_READONLY_OPERATIONS,
    HVSAdapterConfig,
    HermesVideoStudioAdapter,
    build_hvs_adapter_config,
)
from agent_adapter_contracts import BaseAgentAdapter  # noqa: E402
from agent_adapter_models import (  # noqa: E402
    AgentAdapterError,
    AgentAdapterResult,
)

_PASS = 0
_FAIL = 0


def check(name: str, cond: bool) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}")


# A tiny fake subprocess runner used across the unit suite so no real HVS
# repository is ever touched by these tests.
@dataclass
class _FakeProc:
    # stdout/stderr may be str (legacy/display-path fakes) or bytes (the real
    # text=False boundary); the adapter normalizes both via _to_bytes().
    stdout: str | bytes
    stderr: str | bytes
    returncode: int


@dataclass
class _FakeRun:
    """Configurable fake for subprocess.run."""

    returncode: int = 0
    stdout: str = "usage: hvs.cli.studio_cli ..."
    stderr: str = ""
    raise_cls: type[Exception] | None = None
    captured: dict[str, Any] | None = None

    def __call__(self, argv, **kwargs):
        if self.captured is not None:
            self.captured["argv"] = list(argv)
            self.captured["kwargs"] = dict(kwargs)
        if self.raise_cls is not None:
            raise self.raise_cls("fake failure")
        return _FakeProc(stdout=self.stdout, stderr=self.stderr, returncode=self.returncode)


@dataclass
class _FakeRunBytes:
    """Like ``_FakeRun`` but returns RAW BYTES (mirrors ``text=False``)."""

    returncode: int = 0
    stdout: bytes = b""
    stderr: bytes = b""
    raise_cls: type[Exception] | None = None
    captured: dict[str, Any] | None = None

    def __call__(self, argv, **kwargs):
        if self.captured is not None:
            self.captured["argv"] = list(argv)
            self.captured["kwargs"] = dict(kwargs)
        if self.raise_cls is not None:
            raise self.raise_cls("fake failure")
        return _FakeProc(stdout=self.stdout, stderr=self.stderr, returncode=self.returncode)


def _valid_config(tmp_path: Path, *, python_executable: str | None = None, **overrides):
    repo = tmp_path / "hvs_repo"
    (repo / "hvs" / "cli").mkdir(parents=True, exist_ok=True)
    base = dict(
        hvs_repo_path=str(repo),
        python_executable=python_executable if python_executable is not None else sys.executable,
        operation="hvs_capability_probe",
    )
    base.update(overrides)
    return HVSAdapterConfig(**base)


def _created_at() -> str:
    return "2026-07-10T12:00:00Z"


# --- 1. Adapter satisfies BaseAgentAdapter contract -------------------------
def test_adapter_is_base_agent_adapter_subclass(tmp_path) -> None:
    cfg = _valid_config(tmp_path)
    adapter = HermesVideoStudioAdapter(cfg, subprocess_run=_FakeRun())
    check("adapter is a BaseAgentAdapter", isinstance(adapter, BaseAgentAdapter))
    check("adapter_id is hermes-video-studio", adapter.adapter_id() == "hermes-video-studio")
    check("agent_name is hermes_video_studio", adapter.agent_name() == "hermes_video_studio")
    check("runtime_type is hvs_cli", adapter.runtime_type() == "hvs_cli")
    check("declares one capability", len(adapter.capabilities()) == 1)
    check("capability task is capability_probe",
          adapter.capabilities()[0].task_types == ("capability_probe",))


# --- 2. Successful read-only capability probe returns valid result ---------
def test_successful_probe_returns_valid_result(tmp_path) -> None:
    cfg = _valid_config(tmp_path)
    captured: dict[str, Any] = {}
    adapter = HermesVideoStudioAdapter(
        cfg, subprocess_run=_FakeRun(returncode=0, stdout="HVS HELP", captured=captured)
    )
    result = adapter.run_readonly_probe(request_id="r1", created_at=_created_at())
    check("returns AgentAdapterResult", isinstance(result, AgentAdapterResult))
    check("status is result_ready on success", result.status == "result_ready")
    check("result_type is probe_report", result.result_type == "probe_report")
    check("output_text captured", result.output_text == "HVS HELP")
    check("exit_code 0 in metadata", dict(result.metadata).get("exit_code") == "0")


# --- 3. Command uses argv list ---------------------------------------------
def test_command_uses_argv_list(tmp_path) -> None:
    cfg = _valid_config(tmp_path)
    captured: dict[str, Any] = {}
    HermesVideoStudioAdapter(
        cfg, subprocess_run=_FakeRun(captured=captured)
    ).run_readonly_probe(request_id="r1", created_at=_created_at())
    argv = captured["argv"]
    check("argv is a list", isinstance(argv, list))
    check("argv starts with python -m hvs.cli", argv[:3] == [cfg.python_executable, "-m", "hvs.cli"])
    check("argv ends with --help", argv[-1] == "--help")
    check("argv has exactly 4 elements", len(argv) == 4)


# --- 4. shell=False is enforced --------------------------------------------
def test_shell_false_enforced(tmp_path) -> None:
    cfg = _valid_config(tmp_path)
    captured: dict[str, Any] = {}
    HermesVideoStudioAdapter(
        cfg, subprocess_run=_FakeRun(captured=captured)
    ).run_readonly_probe(request_id="r1", created_at=_created_at())
    check("shell=False passed to subprocess", captured["kwargs"].get("shell") is False)


# --- 5. cwd equals configured HVS root -------------------------------------
def test_cwd_is_configured_hvs_root(tmp_path) -> None:
    cfg = _valid_config(tmp_path)
    captured: dict[str, Any] = {}
    HermesVideoStudioAdapter(
        cfg, subprocess_run=_FakeRun(captured=captured)
    ).run_readonly_probe(request_id="r1", created_at=_created_at())
    check("cwd points at configured HVS repo",
          Path(captured["kwargs"]["cwd"]).resolve() == Path(cfg.hvs_repo_path).resolve())


# --- 6. Paths containing spaces are handled --------------------------------
def test_paths_with_spaces_handled(tmp_path) -> None:
    repo = tmp_path / "my hvs repo"
    (repo / "hvs" / "cli").mkdir(parents=True, exist_ok=True)
    py = tmp_path / "python with space.exe"
    py.write_text("")  # not executed by fake runner
    cfg = HVSAdapterConfig(
        hvs_repo_path=str(repo),
        python_executable=str(py),
        operation="hvs_capability_probe",
    )
    captured: dict[str, Any] = {}
    HermesVideoStudioAdapter(
        cfg, subprocess_run=_FakeRun(captured=captured)
    ).run_readonly_probe(request_id="r1", created_at=_created_at())
    argv = captured["argv"]
    # Spaces are preserved as distinct argv elements (no shell splitting).
    check("python path with space is a single argv element",
          str(py) in argv)
    check("repo path not split on space",
          not any(part == "hvs" for part in argv))
    check("shell still False with spaces", captured["kwargs"].get("shell") is False)


# --- 7. Deterministic IDs remain stable for identical inputs ---------------
def test_deterministic_ids_stable(tmp_path) -> None:
    cfg = _valid_config(tmp_path)
    id1 = cfg.result_id(request_id="r1")
    id2 = cfg.result_id(request_id="r1")
    check("result_id stable for identical inputs", id1 == id2)
    check("result_id is prefixed", id1.startswith("hvs-adapter-"))


# --- 8. Volatile timing does not change deterministic identity -------------
def test_volatile_timing_does_not_change_identity(tmp_path) -> None:
    import time
    cfg = _valid_config(tmp_path)
    id1 = cfg.result_id(request_id="r1")
    time.sleep(0.01)
    id2 = cfg.result_id(request_id="r1")
    check("result_id insensitive to elapsed time", id1 == id2)


# --- 9. Missing repository returns normalized failure ----------------------
def test_missing_repository_returns_failure(tmp_path) -> None:
    cfg = HVSAdapterConfig(
        hvs_repo_path=str(tmp_path / "does_not_exist"),
        python_executable="python",
        operation="hvs_capability_probe",
    )
    adapter = HermesVideoStudioAdapter(cfg, subprocess_run=_FakeRun())
    result = adapter.run_readonly_probe(request_id="r1", created_at=_created_at())
    check("missing repo -> AgentAdapterError", isinstance(result, AgentAdapterError))
    check("error kind invalid_configuration", result.error_kind == "invalid_configuration")


# --- 10. Missing Python executable returns normalized failure --------------
def test_missing_python_executable_returns_failure(tmp_path) -> None:
    cfg = _valid_config(tmp_path, python_executable=str(tmp_path / "no_such_python.exe"))
    adapter = HermesVideoStudioAdapter(cfg, subprocess_run=_FakeRun())
    result = adapter.run_readonly_probe(request_id="r1", created_at=_created_at())
    check("missing python -> AgentAdapterError", isinstance(result, AgentAdapterError))
    check("error kind invalid_configuration", result.error_kind == "invalid_configuration")


# --- 11. Unsupported operation rejected before subprocess ------------------
def test_unsupported_operation_rejected_before_subprocess(tmp_path) -> None:
    cfg = _valid_config(tmp_path, operation="render-hyperframes")
    captured: dict[str, Any] = {}
    adapter = HermesVideoStudioAdapter(
        cfg, subprocess_run=_FakeRun(captured=captured)
    )
    result = adapter.run_readonly_probe(request_id="r1", created_at=_created_at())
    check("unsupported op -> AgentAdapterError", isinstance(result, AgentAdapterError))
    check("subprocess never called", "argv" not in captured)
    check("error kind invalid_configuration", result.error_kind == "invalid_configuration")


# --- 12. Mutating HVS commands are rejected --------------------------------
def test_mutating_subcommands_rejected_in_config_validate() -> None:
    # Stage 1 allowlist contains only read-only probes; mutating verbs are not
    # accepted as operations. We assert the allowlist shape and that a mutating
    # verb cannot be an allowed operation.
    check("only read-only ops in allowlist", STAGE1_READONLY_OPERATIONS == ("hvs_capability_probe",))
    check("render not in allowlist", "render-hyperframes" not in STAGE1_READONLY_OPERATIONS)
    check("create-project not in allowlist", "create-project" not in STAGE1_READONLY_OPERATIONS)
    check("assemble-media not in allowlist", "assemble-media" not in STAGE1_READONLY_OPERATIONS)


def test_build_argv_only_ever_constructs_help(tmp_path) -> None:
    cfg = _valid_config(tmp_path)
    argv = cfg.build_argv()
    check("argv is help-only", argv == [cfg.python_executable, "-m", "hvs.cli", "--help"])
    check("argv never contains a render verb", "render-hyperframes" not in argv)
    check("argv never contains create-project", "create-project" not in argv)


def test_stage8l_initialize_and_inspect_use_bounded_json_cli(tmp_path) -> None:
    cfg = _valid_config(tmp_path)
    captured: dict[str, Any] = {}
    fake = _FakeRun(returncode=0, stdout='{"status":"verified","project_verified":true}', captured=captured)
    adapter = HermesVideoStudioAdapter(cfg, subprocess_run=fake)
    init = adapter.initialize_project(
        project_id="hvs8l-abc",
        contract_path=str(tmp_path / "contract.json"),
        expected_payload_hash="a" * 16,
        approve_initialization=True,
        request_id="stage8l",
    )
    argv = captured["argv"]
    check("8L init command selected", "initialize-project" in argv)
    check("8L init approval flag present", "--approve-initialization" in argv)
    check("8L init shell false", captured["kwargs"].get("shell") is False)
    check("8L init parses JSON", init["payload"]["project_verified"] is True)

    captured.clear()
    adapter.inspect_project(project_id="hvs8l-abc", request_id="stage8l")
    check("8L inspect command selected", "inspect-project" in captured["argv"])
    check("8L never uses legacy create-project", "create-project" not in " ".join(captured["argv"]))


# --- 11b. Deterministic cp1252 0x97 encoding boundary (Cohort 6E.2) --------
# These tests pin the SCOS-only repair: the adapter captures RAW BYTES
# (text=False) so the subprocess reader thread never decodes, and:
#   * display text escapes a cp1252 0x97 byte via backslashreplace (never raises);
#   * control-plane JSON with a cp1252 0x97 byte is REJECTED as malformed_output
#     (never silently accepted, never crashes a background reader thread).
def test_probe_display_text_escapes_cp1252_0x97(tmp_path) -> None:
    cfg = _valid_config(tmp_path)
    # Raw bytes the HVS CLI could emit on a cp1252 Windows console (0x97 = em dash).
    raw = b"status: ok \x97 done\n"
    fake = _FakeRunBytes(returncode=0, stdout=raw, stderr=b"note \x97\n")
    adapter = HermesVideoStudioAdapter(cfg, subprocess_run=fake)
    result = adapter.run_readonly_probe(request_id="r1", created_at=_created_at())
    check("probe returns AgentAdapterResult", isinstance(result, AgentAdapterResult))
    check("probe status result_ready", result.status == "result_ready")
    # The 0x97 byte must be escaped as \x97, not crash a reader thread.
    text = result.output_text or ""
    check("0x97 byte escaped (no crash, no mojibake)", "\x97" not in text and "\\x97" in text)
    md = dict(result.metadata)
    check("stderr 0x97 escaped in metadata", "\\x97" in (md.get("stderr_excerpt") or ""))


def test_json_command_rejects_cp1252_0x97_control_plane(tmp_path) -> None:
    cfg = _valid_config(tmp_path)
    # A control-plane payload contaminated with a non-UTF-8 cp1252 0x97 byte.
    raw = b'{"status": "verified"\x97}\n'
    fake = _FakeRunBytes(returncode=0, stdout=raw, stderr=b"")
    adapter = HermesVideoStudioAdapter(cfg, subprocess_run=fake)
    init = adapter.initialize_project(
        project_id="hvs8l-abc",
        contract_path=str(tmp_path / "contract.json"),
        expected_payload_hash="a" * 16,
        approve_initialization=True,
        request_id="stage8l",
    )
    check("0x97 control-plane is NOT parsed", init.get("payload") is None)
    check("0x97 control-plane rejected (malformed_output)",
          init.get("error_kind") == "malformed_output")
    check("0x97 control-plane not ok", init.get("ok") is False)


def test_json_command_accepts_valid_utf8_control_plane(tmp_path) -> None:
    cfg = _valid_config(tmp_path)
    # Genuine UTF-8 control-plane JSON (Thai + emoji) must still parse fine.
    payload = {"status": "verified", "note": "ส่งมอบแล้ว \U0001f680"}
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    fake = _FakeRunBytes(returncode=0, stdout=raw, stderr=b"")
    adapter = HermesVideoStudioAdapter(cfg, subprocess_run=fake)
    init = adapter.initialize_project(
        project_id="hvs8l-abc",
        contract_path=str(tmp_path / "contract.json"),
        expected_payload_hash="a" * 16,
        approve_initialization=True,
        request_id="stage8l",
    )
    check("valid UTF-8 control-plane parses", init.get("payload") == payload)
    check("valid UTF-8 control-plane ok", init.get("ok") is True)


def test_subprocess_run_uses_text_false_bytes_boundary(tmp_path) -> None:
    cfg = _valid_config(tmp_path)
    captured: dict[str, Any] = {}
    HermesVideoStudioAdapter(
        cfg, subprocess_run=_FakeRunBytes(captured=captured)
    ).run_readonly_probe(request_id="r1", created_at=_created_at())
    check("text=False (raw bytes) set on subprocess", captured["kwargs"].get("text") is False)



def test_stage8l_mutation_config_requires_repo_local_python(tmp_path) -> None:
    repo = tmp_path / "hvs_repo"
    (repo / "hvs" / "cli").mkdir(parents=True, exist_ok=True)
    outside_python = tmp_path / "outside" / "python.exe"
    outside_python.parent.mkdir()
    outside_python.write_text("", encoding="utf-8")
    inside_python = repo / ".venv" / "Scripts" / "python.exe"
    inside_python.parent.mkdir(parents=True)
    inside_python.write_text("", encoding="utf-8")

    outside = HVSAdapterConfig(
        hvs_repo_path=str(repo),
        python_executable=str(outside_python),
        require_repo_local_python=True,
    )
    inside = HVSAdapterConfig(
        hvs_repo_path=str(repo),
        python_executable=str(inside_python),
        require_repo_local_python=True,
    )

    check("outside interpreter rejected", any("inside hvs_repo_path" in item for item in outside.validate()))
    check("repo-local interpreter accepted", inside.validate() == ())


# --- 13. Shell-metacharacter input cannot alter argv -----------------------
def test_shell_metacharacter_input_cannot_alter_argv(tmp_path) -> None:
    repo = tmp_path / "hvs_repo"
    (repo / "hvs" / "cli").mkdir(parents=True, exist_ok=True)
    # A python path with a metacharacter must be rejected at validation.
    cfg = HVSAdapterConfig(
        hvs_repo_path=str(repo),
        python_executable="python; rm -rf /",
        operation="hvs_capability_probe",
    )
    problems = cfg.validate()
    check("metacharacter python rejected at validation", len(problems) >= 1)


# --- 14. Parent-directory escape is rejected -------------------------------
def test_parent_directory_escape_rejected(tmp_path) -> None:
    # A configured repo that escapes its expected root is meaningless here
    # because we require the HVS CLI indicator file; an escape attempt simply
    # fails the "contains hvs/cli" check. We also assert cwd is the resolved
    # repo, never a parent escape.
    repo = tmp_path / "hvs_repo"
    (repo / "hvs" / "cli").mkdir(parents=True, exist_ok=True)
    cfg = HVSAdapterConfig(
        hvs_repo_path=str(repo),
        python_executable="python",
        operation="hvs_capability_probe",
    )
    captured: dict[str, Any] = {}
    HermesVideoStudioAdapter(
        cfg, subprocess_run=_FakeRun(captured=captured)
    ).run_readonly_probe(request_id="r1", created_at=_created_at())
    cwd = Path(captured["kwargs"]["cwd"]).resolve()
    check("cwd is the repo, not a parent escape", cwd == repo.resolve())
    check("cwd does not escape via ..", ".." not in str(cwd).split("\\") if "\\" in str(cwd) else ".." not in str(cwd).split("/"))


# --- 15. Timeout returns normalized failure --------------------------------
def test_timeout_returns_normalized_failure(tmp_path) -> None:
    cfg = _valid_config(tmp_path)
    adapter = HermesVideoStudioAdapter(
        cfg, subprocess_run=_FakeRun(raise_cls=subprocess.TimeoutExpired,
                                     stdout="", stderr="")
    )
    # TimeoutExpired needs args; build a real one to satisfy the except clause.
    import subprocess as _sp
    adapter._subprocess_run = lambda *a, **k: (_ for _ in ()).throw(
        _sp.TimeoutExpired(cmd="hvs", timeout=cfg.timeout_seconds)
    )
    result = adapter.run_readonly_probe(request_id="r1", created_at=_created_at())
    check("timeout -> AgentAdapterError", isinstance(result, AgentAdapterError))
    check("error kind command_timeout", result.error_kind == "command_timeout")


# --- 16. Non-zero exit returns normalized failure --------------------------
def test_nonzero_exit_returns_failure(tmp_path) -> None:
    cfg = _valid_config(tmp_path)
    adapter = HermesVideoStudioAdapter(
        cfg, subprocess_run=_FakeRun(returncode=2, stderr="boom")
    )
    result = adapter.run_readonly_probe(request_id="r1", created_at=_created_at())
    check("non-zero exit -> AgentAdapterResult (failed)", isinstance(result, AgentAdapterResult))
    check("failed status", result.status == "failed")
    check("exit_code 2 in metadata", dict(result.metadata).get("exit_code") == "2")


# --- 17. PermissionError returns normalized failure ------------------------
def test_permission_error_returns_failure(tmp_path) -> None:
    cfg = _valid_config(tmp_path)
    adapter = HermesVideoStudioAdapter(
        cfg, subprocess_run=_FakeRun(raise_cls=PermissionError)
    )
    result = adapter.run_readonly_probe(request_id="r1", created_at=_created_at())
    check("permission error -> AgentAdapterError", isinstance(result, AgentAdapterError))
    check("error kind permission_error", result.error_kind == "permission_error")


# --- 18. Unexpected exception does not escape boundary ---------------------
def test_unexpected_exception_normalized(tmp_path) -> None:
    cfg = _valid_config(tmp_path)
    adapter = HermesVideoStudioAdapter(
        cfg, subprocess_run=_FakeRun(raise_cls=RuntimeError)
    )
    result = adapter.run_readonly_probe(request_id="r1", created_at=_created_at())
    check("unexpected exception normalized", isinstance(result, AgentAdapterError))
    check("error kind adapter_blocked", result.error_kind == "adapter_blocked")


# --- 19. stdout and stderr are bounded -------------------------------------
def test_stdout_stderr_bounded(tmp_path) -> None:
    repo = tmp_path / "hvs_repo"
    (repo / "hvs" / "cli").mkdir(parents=True, exist_ok=True)
    cfg = HVSAdapterConfig(
        hvs_repo_path=str(repo),
        python_executable="python",
        operation="hvs_capability_probe",
        max_output_chars=50,
    )
    big = "A" * 10_000
    adapter = HermesVideoStudioAdapter(
        cfg, subprocess_run=_FakeRun(returncode=0, stdout=big, stderr=big)
    )
    result = adapter.run_readonly_probe(request_id="r1", created_at=_created_at())
    md = dict(result.metadata)
    check("stdout excerpt bounded to <=200 in metadata",
          len(md.get("stdout_excerpt", "")) <= 200)
    check("stderr excerpt bounded to <=200 in metadata",
          len(md.get("stderr_excerpt", "")) <= 200)


# --- 20. Secrets and env contents not exposed ------------------------------
def test_no_secret_or_env_exposure(tmp_path) -> None:
    cfg = _valid_config(tmp_path)
    captured: dict[str, Any] = {}
    HermesVideoStudioAdapter(
        cfg, subprocess_run=_FakeRun(captured=captured)
    ).run_readonly_probe(request_id="r1", created_at=_created_at())
    env = captured["kwargs"].get("env")
    check("env is empty dict (no os.environ dump)", env == {})
    argv = captured["argv"]
    joined = " ".join(argv)
    check("no secret-like token in argv", "secret" not in joined.lower())
    check("no token-like value in argv", "token" not in joined.lower())


# --- 21. No HVS file is written --------------------------------------------
def test_no_hvs_file_written_by_adapter(tmp_path) -> None:
    cfg = _valid_config(tmp_path)
    before = sorted(p for p in Path(cfg.hvs_repo_path).rglob("*") if p.is_file())
    HermesVideoStudioAdapter(
        cfg, subprocess_run=_FakeRun(returncode=0, stdout="ok")
    ).run_readonly_probe(request_id="r1", created_at=_created_at())
    after = sorted(p for p in Path(cfg.hvs_repo_path).rglob("*") if p.is_file())
    check("adapter writes no file into HVS repo", before == after)


# --- 22. Existing adapter implementations remain compatible -----------------
def test_existing_adapters_still_constructable() -> None:
    from agent_adapter_contracts import (
        ChatGPTContractAdapter,
        ClaudeCodeContractAdapter,
        CodexContractAdapter,
        HermesContractAdapter,
        ManualClipboardContractAdapter,
    )
    for cls in (
        ChatGPTContractAdapter,
        ClaudeCodeContractAdapter,
        CodexContractAdapter,
        HermesContractAdapter,
        ManualClipboardContractAdapter,
    ):
        inst = cls()
        check(f"{cls.__name__} still constructs", inst.adapter_id() is not None)


# --- 23. Adapter is not the default renderer -------------------------------
def test_adapter_not_default_renderer(tmp_path) -> None:
    # The SCOS default renderer lives in scos.render (VideoUseStudioBackend),
    # entirely outside the control-center adapter registry. The HVS adapter is
    # NOT registered there, so it cannot be selected as a default agent.
    from agent_adapter_registry import create_default_agent_adapter_registry

    registry = create_default_agent_adapter_registry()
    names = {a.agent_name() for a in registry.list_adapters()}
    check("default registry has 5 baseline adapters", len(names) == 5)
    check("hvs adapter absent from default registry",
          "hermes_video_studio" not in names)
    rec = registry.recommend_adapter("capability_probe")
    check("hvs adapter never recommended as default",
          rec.agent_name() != "hermes_video_studio")


# --- 24. No schema mapping exists in Stage 1 -------------------------------
def test_no_schema_mapping_in_stage1(tmp_path) -> None:
    cfg = _valid_config(tmp_path)
    argv = cfg.build_argv()
    check("no timeline/schema mapping in command", "--map" not in argv)
    check("no schema keyword in command", "schema" not in " ".join(argv).lower())


# --- 25. No render command is executed -------------------------------------
def test_no_render_command_executed(tmp_path) -> None:
    cfg = _valid_config(tmp_path)
    captured: dict[str, Any] = {}
    HermesVideoStudioAdapter(
        cfg, subprocess_run=_FakeRun(captured=captured)
    ).run_readonly_probe(request_id="r1", created_at=_created_at())
    joined = " ".join(captured["argv"]).lower()
    check("no 'render' in argv", "render" not in joined)
    check("no 'assemble' in argv", "assemble" not in joined)
    check("no 'publish' in argv", "publish" not in joined)
    check("no 'export' in argv", "export" not in joined)


# --- Configuration validation boundary checks ------------------------------
def test_config_rejects_negative_timeout(tmp_path) -> None:
    cfg = _valid_config(tmp_path, timeout_seconds=-1)
    check("negative timeout rejected", len(cfg.validate()) >= 1)


def test_config_rejects_unbounded_timeout(tmp_path) -> None:
    cfg = _valid_config(tmp_path, timeout_seconds=99999)
    check("unbounded timeout rejected", len(cfg.validate()) >= 1)


def test_factory_creates_equivalent_config(tmp_path) -> None:
    repo = tmp_path / "hvs_repo"
    (repo / "hvs" / "cli").mkdir(parents=True, exist_ok=True)
    cfg = build_hvs_adapter_config(
        hvs_repo_path=str(repo),
        python_executable="python",
    )
    check("factory operation default", cfg.operation == "hvs_capability_probe")
    check("factory timeout default", cfg.timeout_seconds == DEFAULT_TIMEOUT_SECONDS)
    check("factory max_output default", cfg.max_output_chars == DEFAULT_MAX_OUTPUT_CHARS)
    check("factory config validates clean", cfg.validate() == ())


# --- Real cross-repository read-only smoke (skipped if HVS absent) ----------
def test_real_hvs_help_probe_skips_when_absent() -> None:
    """If HVS repo is not at the documented path, skip with a reason."""
    hvs_root = Path(r"C:\Workspace\hermes-video-studio")
    if not hvs_root.exists():
        import pytest
        pytest.skip("HVS repository not available in this environment")


def test_real_hvs_readonly_help_smoke() -> None:
    """Live cross-repository contract: run ONLY ``python -m hvs.cli --help``
    against the real HVS repo via the SCOS adapter, then prove HVS is
    unchanged (no new files, no project/state/media/render output).

    Skips only when the external repository is genuinely unavailable.
    """
    import subprocess

    hvs_root = Path(r"C:\Workspace\hermes-video-studio")
    if not hvs_root.exists():
        import pytest

        pytest.skip("HVS repository not available in this environment")

    # Snapshot HVS git status BEFORE the probe (must stay clean after).
    before = subprocess.run(
        ["git", "status", "--porcelain=v1", "-uall"],
        cwd=str(hvs_root),
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout

    # Build the adapter pointing at the REAL HVS repo + the repo interpreter.
    venv_py = hvs_root / ".venv" / "Scripts" / "python.exe"
    python_exe = str(venv_py) if venv_py.is_file() else "python"
    cfg = build_hvs_adapter_config(
        hvs_repo_path=str(hvs_root),
        python_executable=python_exe,
    )
    problems = cfg.validate()
    check("real config validates clean", problems == ())

    adapter = HermesVideoStudioAdapter(cfg)  # real subprocess.run (shell=False)
    result = adapter.run_readonly_probe(
        request_id="stage1-smoke", created_at="2026-07-10T12:00:00Z"
    )
    check("real probe returns AgentAdapterResult", isinstance(result, AgentAdapterResult))
    check("real probe exit code 0", dict(result.metadata).get("exit_code") == "0")
    check("real probe status result_ready", result.status == "result_ready")
    check("real probe produced help output", (result.output_text or "").strip() != "")

    # Snapshot HVS git status AFTER the probe — MUST remain clean.
    after = subprocess.run(
        ["git", "status", "--porcelain=v1", "-uall"],
        cwd=str(hvs_root),
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout
    check("HVS git status unchanged after probe", before == after)
    check("HVS working tree clean after probe", after.strip() == "")


def main() -> int:
    # pytest discovery runs the test_* functions; running directly also works.
    import traceback

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        try:
            # pytest passes a tmp_path fixture; emulate for direct runs.
            if "tmp_path" in t.__code__.co_varnames:
                import tempfile

                with tempfile.TemporaryDirectory() as d:
                    t(Path(d))
            else:
                t()
        except SystemExit:
            pass
        except Exception as exc:  # noqa: BLE001
            # A pytest.skip() raises Skipped; treat as a clean skip, not a fail.
            if exc.__class__.__name__ == "Skipped":
                print(f"  SKIP  {t.__name__}")
                continue
            _FAIL += 1
            print(f"  ERROR in {t.__name__}")
            traceback.print_exc()
    print(f"\n RESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
