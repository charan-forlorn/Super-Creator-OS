"""SCOS <-> Hermes Video Studio (HVS) adapter — Stage 1 read-only scaffold.

This module is the ONLY integration point SCOS exposes to the Hermes Video
Studio production engine (repo C:\\Workspace\\hermes-video-studio). It does not
import any HVS Python package, never writes into the HVS repository, and can
ONLY drive HVS through its read-only CLI entry point:

    <python_executable> -m hvs.cli [--help | <command> --help]

Boundary (per the cross-project integration architecture decision):

    SCOS -> HermesVideoStudioAdapter -> subprocess(shell=False)
          -> HVS CLI -> structured SCOS AgentAdapterResult

Stage 1 scope is deliberately tiny:

* discover and validate an HVS repository + Python executable,
* build deterministic, argument-list-based HVS CLI commands,
* run ONLY approved read-only capability probes (help/capability),
* return a normalized existing SCOS ``AgentAdapterResult``,
* normalize every failure (missing repo, missing python, CLI unavailable,
  unsupported op, invalid config, timeout, non-zero exit, malformed output,
  permission error, unexpected exception) into a structured failure,
* bound captured stdout/stderr so unbounded CLI output never reaches SCOS
  events or memory.

It does NOT:

* import hvs.* or any HVS internal module,
* create HVS projects, assemble media, render, publish, export or hand off,
* change the SCOS default renderer (VideoUseStudioBackend),
* perform any schema mapping or timeline translation,
* send anything over a network (no requests/urllib/socket/http imports).

The adapter is intentionally NOT registered in the default
``AgentAdapterRegistry``, so it never changes runtime adapter selection or
becomes the default agent for any task. It is instantiated explicitly in
tests and by future (post-Stage-1) callers behind an authorization gate.

Local-first, deterministic, stdlib-only. No clock (``created_at`` is
caller-supplied), no random, no uuid, no network, no file I/O except the
subprocess stdout/stderr it reads back from the CLI.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from .agent_adapter_contracts import BaseAgentAdapter
    from .agent_adapter_models import (
        AI_AGENT_ADAPTER_SCHEMA_VERSION,
        AgentAdapterCapability,
        AgentAdapterError,
        AgentAdapterRequest,
        AgentAdapterResult,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from agent_adapter_contracts import BaseAgentAdapter
    from agent_adapter_models import (
        AI_AGENT_ADAPTER_SCHEMA_VERSION,
        AgentAdapterCapability,
        AgentAdapterError,
        AgentAdapterRequest,
        AgentAdapterResult,
    )


# --- Operation allowlist (Stage 1) -------------------------------------------
# Only read-only capability/help probes are permitted. These produce no
# project, state, media, cache, or render output and never mutate HVS.
STAGE1_READONLY_OPERATIONS = ("hvs_capability_probe",)

_HVS_MODULE = "hvs.cli"
_HVS_REPO_INDICATOR = Path("hvs") / "cli"

# Maximum captured stdout/stderr bytes retained per result (bounded evidence).
DEFAULT_MAX_OUTPUT_CHARS = 4000

# Hard ceiling on command timeout (seconds) to keep probes finite and safe.
DEFAULT_TIMEOUT_SECONDS = 60
_MAX_TIMEOUT_SECONDS = 600

# --- subprocess text-encoding boundary (deterministic, locale-independent) --
# The HVS CLI may emit non-UTF-8 bytes on Windows (e.g. a cp1252 0x97 em dash).
# We therefore capture RAW BYTES (never ``text=True``): the internal subprocess
# reader thread then only copies bytes and never decodes, so it can never raise
# ``UnicodeDecodeError`` in a background thread. Decoding happens HERE, in the
# main thread, under explicit control:
#
#   * Display text (stdout/stderr excerpts) uses ``errors="backslashreplace"`` so
#     it is lossy-but-safe and can NEVER raise, regardless of host encoding.
#   * Control-plane JSON is decoded STRICTLY (``errors="strict"``). A non-UTF-8
#     byte (the cp1252 0x97 case) makes the parse fail closed as
#     ``malformed_output`` instead of being silently accepted or crashing a
#     reader thread.
#
# This is encoding-agnostic: it does not depend on
# ``locale.getpreferredencoding()`` and reproduces on utf-8 and cp1252 hosts.
_OUTPUT_TEXT_ENCODING = "utf-8"
_OUTPUT_TEXT_ERRORS = "backslashreplace"
_OUTPUT_JSON_ERRORS = "strict"


def _to_bytes(value: object) -> bytes:
    """Normalize a subprocess output field into raw bytes.

    ``subprocess.run(..., capture_output=True, text=False)`` returns ``bytes`` or
    ``None``. Centralizing this keeps the strict/known byte boundary explicit and
    lets the decode step below stay total over its inputs.
    """
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode(_OUTPUT_TEXT_ENCODING, errors=_OUTPUT_TEXT_ERRORS)
    return str(value).encode(_OUTPUT_TEXT_ENCODING, errors=_OUTPUT_TEXT_ERRORS)


def _decode_output(value: object, *, max_chars: int) -> str:
    """Decode captured bytes into display-safe text without raising.

    Uses ``errors="backslashreplace"`` so an unexpected byte (e.g. cp1252 0x97)
    is escaped (``\\x97``) rather than crashing a background reader thread or
    raising ``UnicodeDecodeError``. The result is bounded to ``max_chars``.
    """
    return _to_bytes(value).decode(
        _OUTPUT_TEXT_ENCODING, errors=_OUTPUT_TEXT_ERRORS
    )[:max_chars]

# Marker tokens that indicate a mutating / forbidden HVS subcommand. Stage 1
# rejects any request for these so the adapter can never drive a write.
_FORBIDDEN_HVS_SUBCOMMANDS = frozenset(
    {
        "create-project",
        "assemble-media",
        "export-project",
        "render-hyperframes",
        "plan-real-render-batch",
        "run-real-render-batch",
        "create-render-pack",
        "verify-real-render-output",
        "create-handoff-package",
        "import-media",
        "certify-mvp",
        "backup-project",
        "dashboard",
        "release-gate",
    }
)

# Characters that have shell meaning AND are NOT legitimate path content.
# NOTE: backslash and forward slash are intentionally absent — they are valid
# path separators on Windows / POSIX and, with shell=False + list argv, are
# never interpreted by a shell, so they are not an injection vector here.
# The remaining set covers real command-injection / shell-control tokens.
_SHELL_METACHARACTERS = frozenset(
    set(";&|`$><\n\r(){}*?!#\"'~")
)


def _stable_id(prefix: str, *parts: Any) -> str:
    """Deterministic sha256-prefixed id from stable caller/config inputs.

    Mirrors the convention used across the SCOS Control Center (e.g.
    credential_redaction._stable_id). Volatile inputs (elapsed time, pid,
    random uuid, absolute temp paths) are NEVER passed here.
    """
    text = "|".join(str(part) for part in parts)
    return prefix + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _has_shell_metacharacter(token: str) -> bool:
    return any(ch in _SHELL_METACHARACTERS for ch in token)


def _is_contained(path: Path, root: Path) -> bool:
    """True only if ``path`` is exactly ``root`` or lives inside it."""
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class HVSAdapterConfig:
    """Injectable, testable adapter configuration.

    All paths are explicit. No value is hard-coded to a specific user's home
    directory; a Windows default may only come from configuration or an
    explicit factory.
    """

    hvs_repo_path: str
    python_executable: str
    operation: str = "hvs_capability_probe"
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS
    cli_module: str = _HVS_MODULE
    require_repo_local_python: bool = False

    def __post_init__(self) -> None:
        # Normalize to strings defensively (dataclass is frozen, use object.setattr).
        object.__setattr__(self, "hvs_repo_path", str(self.hvs_repo_path))
        object.__setattr__(self, "python_executable", str(self.python_executable))
        object.__setattr__(self, "operation", str(self.operation))
        object.__setattr__(self, "cli_module", str(self.cli_module))
        object.__setattr__(self, "timeout_seconds", int(self.timeout_seconds))
        object.__setattr__(self, "max_output_chars", int(self.max_output_chars))
        object.__setattr__(self, "require_repo_local_python", bool(self.require_repo_local_python))

    # --- validation ---------------------------------------------------------
    def validate(self) -> tuple[str, ...]:
        """Return problem strings; empty tuple means the config is usable."""
        problems: list[str] = []

        if not self.hvs_repo_path:
            problems.append("hvs_repo_path is required")
            return tuple(problems)
        repo = Path(self.hvs_repo_path)
        if not repo.exists():
            problems.append(f"hvs_repo_path does not exist: {repo}")
            return tuple(problems)
        if not repo.is_dir():
            problems.append(f"hvs_repo_path is not a directory: {repo}")
            return tuple(problems)
        # The configured repo must actually contain the HVS CLI entry point.
        if not (repo / _HVS_REPO_INDICATOR).exists():
            problems.append(
                f"hvs_repo_path does not contain {_HVS_REPO_INDICATOR.as_posix()}: {repo}"
            )
            return tuple(problems)

        if not self.python_executable:
            problems.append("python_executable is required")
        else:
            py = Path(self.python_executable)
            # The executable must either exist as a file OR be resolvable on
            # PATH (e.g. "python"/"python3"). We never guess or synthesize a
            # default; "resolvable" means shutil.which finds a concrete path.
            import shutil

            if not py.exists() and shutil.which(self.python_executable) is None:
                problems.append(
                    f"python_executable not found and not resolvable on PATH: "
                    f"{self.python_executable}"
                )
            if self.require_repo_local_python:
                try:
                    py_resolved = py.resolve()
                    repo_resolved = repo.resolve()
                    py_resolved.relative_to(repo_resolved)
                except ValueError:
                    problems.append("python_executable must be inside hvs_repo_path for mutating operations")
                if not py.is_file():
                    problems.append("python_executable must be an existing file for mutating operations")

        if self.operation not in STAGE1_READONLY_OPERATIONS:
            problems.append(
                f"unsupported operation {self.operation!r}; "
                f"Stage 1 allowlist is {tuple(STAGE1_READONLY_OPERATIONS)}"
            )

        if self.timeout_seconds <= 0 or self.timeout_seconds > _MAX_TIMEOUT_SECONDS:
            problems.append(
                f"timeout_seconds must be in (0, {_MAX_TIMEOUT_SECONDS}], "
                f"got {self.timeout_seconds}"
            )

        if self.max_output_chars <= 0:
            problems.append(
                f"max_output_chars must be positive, got {self.max_output_chars}"
            )

        if not self.cli_module:
            problems.append("cli_module is required")
        elif _has_shell_metacharacter(self.cli_module):
            problems.append("cli_module must not contain shell metacharacters")

        return tuple(problems)

    # --- command construction ----------------------------------------------
    def build_argv(self) -> list[str]:
        """Build the argv list for the allowed read-only probe.

        Always returns a list (never a string). shell=False is enforced by the
        caller. Paths with spaces are preserved as single argv elements — no
        shell-level path joining ever occurs.
        """
        argv = [self.python_executable, "-m", self.cli_module, "--help"]
        return argv

    def result_id(self, *, request_id: str = "dry-run") -> str:
        """Deterministic correlation id derived from stable config values.

        Excludes elapsed time, process id, random uuid, and temp paths. Two
        identical configurations + operation produce identical ids, so the
        evidence hash is stable across runs.
        """
        return _stable_id(
            "hvs-adapter-",
            self.hvs_repo_path,
            self.python_executable,
            self.cli_module,
            self.operation,
            request_id,
        )


class HermesVideoStudioAdapter(BaseAgentAdapter):
    """Read-only SCOS adapter for the Hermes Video Studio production engine.

    Implements the existing ``BaseAgentAdapter`` contract so it can produce a
    valid ``AgentAdapterResult``. All substantive work is a read-only HVS CLI
    help/capability probe executed via ``subprocess.run`` with
    ``shell=False`` and an explicit, isolated ``cwd`` (the configured HVS
    root). The adapter never mutates HVS and never imports HVS internals.
    """

    def __init__(self, config: HVSAdapterConfig, *, subprocess_run=None) -> None:
        self._config = config
        # Dependency injection point: tests pass a fake runner. The default is
        # the real subprocess.run with shell=False enforced at call time.
        self._subprocess_run = subprocess_run or subprocess.run
        # Latest validated config snapshot (for structured failure metadata).
        self._last_validation: tuple[str, ...] = config.validate()

    # --- BaseAgentAdapter identity ------------------------------------------
    def adapter_id(self) -> str:
        return "hermes-video-studio"

    def agent_name(self) -> str:
        return "hermes_video_studio"

    def runtime_type(self) -> str:
        return "hvs_cli"

    def capabilities(self) -> tuple[AgentAdapterCapability, ...]:
        # Stage 1: a single read-only capability-probe capability. The adapter
        # does NOT advertise prompt delivery / result capture / status check.
        return (
            AgentAdapterCapability.of(
                "hvs-cli-cap",
                "hermes_video_studio",
                "hvs_cli",
                task_types=("capability_probe",),
                supports_prompt_delivery=False,
                supports_result_capture=False,
                supports_status_check=False,
                supports_manual_fallback=False,
                metadata=(
                    ("integration", "scos-hvs-stage1"),
                    ("scope", "read_only_capability_probe"),
                    ("cli_module", self._config.cli_module),
                ),
            ),
        )

    # --- core dry-run / probe -----------------------------------------------
    def run_readonly_probe(
        self,
        *,
        request_id: str = "dry-run",
        created_at: str,
    ) -> AgentAdapterResult | AgentAdapterError:
        """Validate, optionally execute the read-only probe, normalize result.

        This is Stage 1's dry-run contract: it validates configuration,
        constructs the allowed command, executes the read-only capability
        probe (unless ``execute=False``), and returns a normalized
        ``AgentAdapterResult`` carrying success/failure, adapter identity,
        operation, exit code, bounded stdout/stderr summary, timing-free
        deterministic correlation evidence, and bounded internal metadata.
        """
        if created_at is None or created_at == "":
            return AgentAdapterError.of(
                "missing_required_field",
                "created_at is required and must be caller-supplied",
                "run_readonly_probe",
                request_id=request_id,
            )

        problems = self._config.validate()
        if problems:
            return self._failure(
                "invalid_configuration",
                "; ".join(problems),
                "validate_config",
                request_id=request_id,
                created_at=created_at,
            )

        argv = self._config.build_argv()
        if any(_has_shell_metacharacter(tok) for tok in argv):
            return self._failure(
                "unsafe_command",
                "constructed argv contained a shell metacharacter",
                "build_argv",
                request_id=request_id,
                created_at=created_at,
                argv=argv,
            )

        cwd = Path(self._config.hvs_repo_path).resolve()
        max_chars = self._config.max_output_chars
        try:
            proc = self._subprocess_run(
                list(argv),
                cwd=str(cwd),
                shell=False,
                capture_output=True,
                # Raw bytes: the internal reader thread never decodes, so it
                # cannot raise UnicodeDecodeError on cp1252 output (e.g. 0x97).
                # Decoding happens below, in the main thread, under our control.
                text=False,
                timeout=self._config.timeout_seconds,
                # No stdin inheritance; empty input stream only.
                input="",
                env=self._safe_env(),
            )
        except subprocess.TimeoutExpired:
            return self._failure(
                "command_timeout",
                f"HVS capability probe exceeded timeout "
                f"{self._config.timeout_seconds}s",
                "subprocess.run",
                request_id=request_id,
                created_at=created_at,
                argv=argv,
                cwd=str(cwd),
            )
        except PermissionError as exc:
            return self._failure(
                "permission_error",
                f"could not execute HVS capability probe: {type(exc).__name__}",
                "subprocess.run",
                request_id=request_id,
                created_at=created_at,
                argv=argv,
                cwd=str(cwd),
            )
        except (OSError, ValueError) as exc:
            # Missing executable, bad cwd, or other environment failure.
            return self._failure(
                "adapter_blocked",
                f"HVS capability probe could not start: {type(exc).__name__}",
                "subprocess.run",
                request_id=request_id,
                created_at=created_at,
                argv=argv,
                cwd=str(cwd),
            )
        except Exception as exc:  # noqa: BLE001 - boundary must not leak raw trace
            return self._failure(
                "adapter_blocked",
                f"unexpected error during HVS capability probe: "
                f"{type(exc).__name__}",
                "subprocess.run",
                request_id=request_id,
                created_at=created_at,
                argv=argv,
                cwd=str(cwd),
            )

        stdout = _decode_output(proc.stdout, max_chars=max_chars)
        stderr = _decode_output(proc.stderr, max_chars=max_chars)
        exit_code = int(proc.returncode)
        ok = exit_code == 0

        summary = (
            f"HVS capability probe {'succeeded' if ok else 'failed'} "
            f"(exit={exit_code})"
        )
        return AgentAdapterResult.of(
            result_id=self._config.result_id(request_id=request_id),
            request_id=request_id,
            session_id="scos-hvs-stage1",
            agent_name=self.agent_name(),
            runtime_id="hvs-cli",
            status="result_ready" if ok else "failed",
            result_type="probe_report",
            result_summary=summary,
            output_text=stdout if ok else None,
            output_path=None,
            created_at=created_at,
            next_action=(
                "no further action in Stage 1 (read-only probe only)"
                if ok
                else "review HVS CLI availability and configuration"
            ),
            metadata=(
                ("operation", self._config.operation),
                ("exit_code", str(exit_code)),
                ("argv", " ".join(argv)),
                ("cwd", str(cwd)),
                ("stdout_excerpt", stdout[:200]),
                ("stderr_excerpt", stderr[:200]),
                ("stage", "scos-hvs-stage1"),
            ),
        )

    # --- helpers ------------------------------------------------------------
    def _safe_env(self):
        """Explicitly minimal environment: never a full os.environ dump.

        We pass ``env={}`` so the child gets no inherited shell environment,
        secrets, or variables. This is the safest choice for a read-only probe
        and guarantees no secret values reach the subprocess command line.
        """
        return {}

    def _run_json_command(
        self,
        *,
        command: str,
        args: list[str],
        request_id: str,
    ) -> dict[str, Any]:
        """Run one approved HVS JSON command through the bounded CLI boundary."""
        if command not in {"initialize-project", "inspect-project"}:
            return {
                "ok": False,
                "command": command,
                "exit_code": None,
                "payload": None,
                "error_kind": "unsupported_operation",
                "error_detail": "unsupported HVS command",
            }
        problems = self._config.validate()
        if problems:
            return {
                "ok": False,
                "command": command,
                "exit_code": None,
                "payload": None,
                "error_kind": "invalid_configuration",
                "error_detail": "; ".join(problems),
            }
        argv = [self._config.python_executable, "-m", self._config.cli_module, command, *args]
        if any(_has_shell_metacharacter(tok) for tok in argv):
            return {
                "ok": False,
                "command": command,
                "exit_code": None,
                "payload": None,
                "error_kind": "unsafe_command",
                "error_detail": "constructed argv contained a shell metacharacter",
            }
        cwd = Path(self._config.hvs_repo_path).resolve()
        try:
            proc = self._subprocess_run(
                list(argv),
                cwd=str(cwd),
                shell=False,
                capture_output=True,
                # Raw bytes: the internal reader thread never decodes, so it
                # cannot raise UnicodeDecodeError on cp1252 output (e.g. 0x97).
                # Control-plane JSON is decoded STRICTLY below.
                text=False,
                timeout=self._config.timeout_seconds,
                input="",
                env=self._safe_env(),
            )
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "command": command,
                "exit_code": None,
                "payload": None,
                "error_kind": "command_timeout",
                "error_detail": f"HVS {command} exceeded timeout {self._config.timeout_seconds}s",
            }
        except PermissionError:
            return {
                "ok": False,
                "command": command,
                "exit_code": None,
                "payload": None,
                "error_kind": "permission_error",
                "error_detail": f"could not execute HVS {command}",
            }
        except (OSError, ValueError) as exc:
            return {
                "ok": False,
                "command": command,
                "exit_code": None,
                "payload": None,
                "error_kind": "adapter_blocked",
                "error_detail": f"HVS {command} could not start: {type(exc).__name__}",
            }
        stdout = _decode_output(proc.stdout, max_chars=self._config.max_output_chars)
        stderr = _decode_output(proc.stderr, max_chars=self._config.max_output_chars)
        # Strict-decode the raw control-plane bytes. A non-UTF-8 byte (cp1252
        # 0x97) raises UnicodeDecodeError, which we normalize as malformed_output
        # so corrupt/foreign-encoded control-plane JSON is REJECTED, never
        # silently accepted and never crashes a background reader thread.
        try:
            raw_text = _to_bytes(proc.stdout).decode(
                _OUTPUT_TEXT_ENCODING, errors=_OUTPUT_JSON_ERRORS
            )
        except UnicodeDecodeError:
            return {
                "ok": False,
                "command": command,
                "exit_code": int(proc.returncode),
                "payload": None,
                "stdout_excerpt": stdout[:200],
                "stderr_excerpt": stderr[:200],
                "error_kind": "malformed_output",
                "error_detail": "HVS control-plane output is not valid UTF-8 (non-UTF-8 bytes such as cp1252 0x97 present)",
            }
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError:
            return {
                "ok": False,
                "command": command,
                "exit_code": int(proc.returncode),
                "payload": None,
                "stdout_excerpt": stdout[:200],
                "stderr_excerpt": stderr[:200],
                "error_kind": "malformed_output",
                "error_detail": "HVS command did not return JSON",
            }
        return {
            "ok": int(proc.returncode) == 0,
            "command": command,
            "exit_code": int(proc.returncode),
            "payload": payload,
            "stdout_excerpt": stdout[:200],
            "stderr_excerpt": stderr[:200],
            "error_kind": None if int(proc.returncode) == 0 else "hvs_command_failed",
            "error_detail": None if int(proc.returncode) == 0 else str(payload.get("error_detail") or stderr[:200]),
            "request_id": request_id,
        }

    def initialize_project(
        self,
        *,
        project_id: str,
        contract_path: str,
        expected_payload_hash: str,
        approve_initialization: bool,
        request_id: str,
    ) -> dict[str, Any]:
        args = [
            "--project-id",
            str(project_id),
            "--contract-path",
            str(contract_path),
            "--expected-payload-hash",
            str(expected_payload_hash),
        ]
        if approve_initialization:
            args.append("--approve-initialization")
        return self._run_json_command(command="initialize-project", args=args, request_id=request_id)

    def inspect_project(self, *, project_id: str, request_id: str) -> dict[str, Any]:
        return self._run_json_command(
            command="inspect-project",
            args=["--project-id", str(project_id)],
            request_id=request_id,
        )

    def _failure(
        self,
        error_kind: str,
        error_detail: str,
        failed_step: str,
        *,
        request_id: str,
        created_at: str,
        argv: list[str] | None = None,
        cwd: str | None = None,
    ) -> AgentAdapterError:
        metadata: list[tuple[str, str]] = [
            ("adapter_id", self.adapter_id()),
            ("operation", self._config.operation),
            ("stage", "scos-hvs-stage1"),
        ]
        if argv is not None:
            # argv is a safe, allowlisted list; record it for audit evidence.
            metadata.append(("argv", " ".join(argv)))
        if cwd is not None:
            metadata.append(("cwd", cwd))
        return AgentAdapterError.of(
            error_kind,
            error_detail,
            failed_step,
            ok=False,
            schema_version=AI_AGENT_ADAPTER_SCHEMA_VERSION,
            request_id=request_id,
            metadata=tuple(metadata),
        )

    # --- Stage 2 planning surface (no activation, no subprocess) ------------
    def plan_hvs_contract_payload(self, scos_project) -> "AgentAdapterResult | AgentAdapterError":
        """Produce a Stage 2 HVS-compatible contract payload from a SCOS project.

        Stage 2 planning only. This method does NOT invoke the HVS CLI, does NOT
        create an HVS project, does NOT write any file, and performs NO
        subprocess. It delegates to the pure deterministic mapper
        (``scos.control_center.hvs_schema_mapper``) and returns the result
        wrapped as a normal ``AgentAdapterResult`` (``result_type="plan"``) or a
        structured ``AgentAdapterError`` on invalid input.

        This is a read-only planning affordance: it never changes adapter
        activation defaults, render backend selection, or the allowlisted
        read-only operation set. It is NOT registered as a production route.
        """
        if scos_project is None:
            return self._failure(
                "missing_required_field",
                "scos_project is required",
                "plan_hvs_contract_payload",
                request_id="plan",
                created_at="plan",
            )
        # Lazy import keeps the Stage 1 subprocess profile unchanged: the mapper
        # is only loaded when planning is actually requested.
        try:
            from hvs_schema_mapper import map_scos_to_hvs
        except Exception as exc:  # noqa: BLE001 - boundary must not leak trace
            return self._failure(
                "adapter_blocked",
                f"Stage 2 mapper unavailable: {type(exc).__name__}",
                "plan_hvs_contract_payload",
                request_id="plan",
                created_at="plan",
            )
        result = map_scos_to_hvs(scos_project, validate=True)
        if not result.ok:
            return AgentAdapterError.of(
                "contract_violation",
                result.error.error_detail,
                "plan_hvs_contract_payload",
                ok=False,
                schema_version=AI_AGENT_ADAPTER_SCHEMA_VERSION,
                request_id="plan",
                metadata=(
                    ("stage", "scos-hvs-stage2"),
                    ("error_kind", result.error.error_kind),
                    ("field", result.error.field or ""),
                ),
            )
        return AgentAdapterResult.of(
            result_id=self._config.result_id(request_id="plan-stage2"),
            request_id="plan-stage2",
            session_id="scos-hvs-stage2",
            agent_name=self.agent_name(),
            runtime_id="hvs-cli",
            status="result_ready",
            result_type="plan",
            result_summary="Stage 2 HVS contract payload planned (no render, no project creation)",
            output_text=None,
            output_path=None,
            created_at="plan",
            next_action="no further action in Stage 2 (planning only)",
            metadata=(
                ("stage", "scos-hvs-stage2"),
                ("contract_id", result.payload.get("deterministic_hash", "")),
                ("resolution", str(result.payload.get("resolution", ""))),
                ("fps", str(result.payload.get("fps", ""))),
                ("scene_count", str(result.payload.get("scene_count", ""))),
            ),
        )

    # --- contract compliance note -------------------------------------------
    # BaseAgentAdapter also declares prepare_prompt / simulate_send /
    # capture_result. Those are intentionally NOT overridden: the HVS adapter
    # is a read-only capability probe and never delivers prompts or captures
    # operator-supplied results. Callers use ``run_readonly_probe``. The base
    # methods remain available (and would fail validation for this adapter's
    # agent_name/runtime_type/task_type if misused), preserving the contract.


def build_hvs_adapter_config(
    hvs_repo_path: str,
    python_executable: str,
    *,
    operation: str = "hvs_capability_probe",
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
    cli_module: str = _HVS_MODULE,
) -> HVSAdapterConfig:
    """Explicit factory for HVS adapter configuration.

    No global constant embeds a user's home directory; every value is an
    explicit argument. A Windows default path may be supplied by the caller or
    by a higher-level factory, never forced here.
    """
    return HVSAdapterConfig(
        hvs_repo_path=hvs_repo_path,
        python_executable=python_executable,
        operation=operation,
        timeout_seconds=timeout_seconds,
        max_output_chars=max_output_chars,
        cli_module=cli_module,
    )


__all__ = [
    "STAGE1_READONLY_OPERATIONS",
    "HVSAdapterConfig",
    "HermesVideoStudioAdapter",
    "build_hvs_adapter_config",
]
