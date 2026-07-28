"""Video Studio bridge-specific process supervision for SCOS.

This module only invokes the certified ``Invoke-VideoStudioBridge.ps1`` with a
fixed PowerShell host, fixed working directory, list arguments, and bounded
output capture. It is intentionally not a generic command runner.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

CONTRACT_VERSION = "2026-07-24.phase2.v1"
CONTRACT_DIGEST = "b66cdc3acc9b30f22b93f799bcc273fa2f56e6d7cd76f4c64b3343aefdb21e09"
VIDEO_STUDIO_ROOT = Path(r"C:\Workspace\video-studio-projects")
BRIDGE_RELATIVE_PATH = Path("tools") / "Invoke-VideoStudioBridge.ps1"
EXPECTED_BRIDGE_SHA256 = "5fe4876b527bbac9467efec0445f1fea73f197b2827dd5f941b6239c10da3e59"

ALLOWED_ACTIONS = (
    "Start",
    "Status",
    "Approve",
    "RequestRevision",
    "Resume",
    "Recover",
    "GetArtifacts",
    "GetDelivery",
)
READ_ONLY_ACTIONS = frozenset({"Status", "GetArtifacts", "GetDelivery"})
DECISION_ACTIONS = frozenset({"Approve", "RequestRevision", "Recover"})
LONG_ACTIONS = frozenset({"Start", "Resume"})
CERTIFIED_EXIT_CODES = frozenset({0, 20, 21, 30, 40, 50, 52, 60, 61, 70, 71, 80, 90})
ALLOWED_POWERSHELL_HOSTS = frozenset({"pwsh.exe", "powershell.exe"})

READ_ONLY_TIMEOUT_SECONDS = 60
DECISION_TIMEOUT_SECONDS = 120
LONG_TIMEOUT_SECONDS = 1800
STDOUT_LIMIT_BYTES = 1_048_576
STDERR_LIMIT_BYTES = 65_536
STDERR_EXCERPT_BYTES = 4_000


class VideoStudioProcessError(RuntimeError):
    """Raised for process-supervision binding or integrity failures."""


@dataclass(frozen=True)
class VideoStudioBridgeIdentity:
    scos_project_id: str
    video_project_id: str
    integration_job_id: str
    correlation_id: str

    def to_args(self) -> tuple[str, ...]:
        return (
            "-ScosProjectId",
            self.scos_project_id,
            "-VideoProjectId",
            self.video_project_id,
            "-IntegrationJobId",
            self.integration_job_id,
            "-CorrelationId",
            self.correlation_id,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "scos_project_id": self.scos_project_id,
            "video_project_id": self.video_project_id,
            "integration_job_id": self.integration_job_id,
            "correlation_id": self.correlation_id,
        }


@dataclass(frozen=True)
class VideoStudioProcessConfig:
    video_studio_root: Path = VIDEO_STUDIO_ROOT
    bridge_relative_path: Path = BRIDGE_RELATIVE_PATH
    expected_bridge_sha256: str = EXPECTED_BRIDGE_SHA256
    contract_version: str = CONTRACT_VERSION
    contract_digest: str = CONTRACT_DIGEST
    read_only_timeout_seconds: int = READ_ONLY_TIMEOUT_SECONDS
    decision_timeout_seconds: int = DECISION_TIMEOUT_SECONDS
    long_timeout_seconds: int = LONG_TIMEOUT_SECONDS
    stdout_limit_bytes: int = STDOUT_LIMIT_BYTES
    stderr_limit_bytes: int = STDERR_LIMIT_BYTES
    stderr_excerpt_bytes: int = STDERR_EXCERPT_BYTES

    @property
    def bridge_path(self) -> Path:
        return self.video_studio_root / self.bridge_relative_path

    @property
    def working_directory(self) -> Path:
        return self.video_studio_root

    def timeout_for(self, action: str) -> int:
        if action in READ_ONLY_ACTIONS:
            return self.read_only_timeout_seconds
        if action in DECISION_ACTIONS:
            return self.decision_timeout_seconds
        if action in LONG_ACTIONS:
            return self.long_timeout_seconds
        raise VideoStudioProcessError(f"UNKNOWN_ACTION: {action}")


@dataclass(frozen=True)
class VideoStudioProcessResult:
    action: str
    argv_metadata: tuple[tuple[str, str], ...]
    pid: int | None
    started_at: str
    finished_at: str
    duration_ms: int
    timed_out: bool
    process_exit_code: int | None
    stdout_bytes: int
    stderr_bytes: int
    stdout_truncated: bool
    stderr_truncated: bool
    stdout_text: str
    stderr_excerpt: str
    launch_error: str | None
    envelope: dict[str, Any] | None
    error_code: str | None
    cleanup_attempted: bool = False
    cleanup_succeeded: bool | None = None

    @property
    def ok(self) -> bool:
        return self.error_code is None and self.envelope is not None and not self.timed_out

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "argv_metadata": dict(self.argv_metadata),
            "pid": self.pid,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "timed_out": self.timed_out,
            "process_exit_code": self.process_exit_code,
            "stdout_bytes": self.stdout_bytes,
            "stderr_bytes": self.stderr_bytes,
            "stdout_truncated": self.stdout_truncated,
            "stderr_truncated": self.stderr_truncated,
            "stdout_text": self.stdout_text,
            "stderr_excerpt": self.stderr_excerpt,
            "launch_error": self.launch_error,
            "envelope": self.envelope,
            "error_code": self.error_code,
            "cleanup_attempted": self.cleanup_attempted,
            "cleanup_succeeded": self.cleanup_succeeded,
        }


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _within_root(root: Path, path: Path) -> bool:
    root_resolved = root.resolve(strict=False)
    path_resolved = path.resolve(strict=False)
    try:
        path_resolved.relative_to(root_resolved)
    except ValueError:
        return False
    return True


def _decode_strict_utf8(data: bytes) -> tuple[str | None, str | None]:
    if data.startswith(b"\xef\xbb\xbf"):
        return None, "STDOUT_BOM_REJECTED"
    try:
        return data.decode("utf-8"), None
    except UnicodeDecodeError:
        return None, "STDOUT_UTF8_DECODE_FAILED"


def parse_single_json_object(stdout_text: str) -> tuple[dict[str, Any] | None, str | None]:
    if not stdout_text or not stdout_text.strip():
        return None, "STDOUT_EMPTY"
    decoder = json.JSONDecoder()
    stripped = stdout_text.strip()
    try:
        value, end = decoder.raw_decode(stripped)
    except json.JSONDecodeError:
        return None, "STDOUT_JSON_INVALID"
    if not isinstance(value, dict):
        return None, "STDOUT_JSON_NOT_OBJECT"
    if stripped[end:].strip():
        return None, "STDOUT_MULTIPLE_OR_TRAILING_CONTENT"
    return value, None


class VideoStudioProcessSupervisor:
    """Run one certified Video Studio bridge action with fixed process bindings."""

    def __init__(
        self,
        *,
        config: VideoStudioProcessConfig | None = None,
        popen_factory: Callable[..., Any] = subprocess.Popen,
        host_resolver: Callable[[], Path] | None = None,
    ) -> None:
        self._config = config or VideoStudioProcessConfig()
        self._popen_factory = popen_factory
        self._host_resolver = host_resolver or self._resolve_powershell_host
        self._verified_bridge_sha256: str | None = None

    @property
    def config(self) -> VideoStudioProcessConfig:
        return self._config

    def describe_binding(self) -> dict[str, Any]:
        host = self._host_resolver()
        return {
            "video_studio_root": str(self._config.video_studio_root),
            "bridge_path": str(self._config.bridge_path),
            "expected_bridge_sha256": self._config.expected_bridge_sha256,
            "contract_version": self._config.contract_version,
            "contract_digest": self._config.contract_digest,
            "powershell_host": str(host),
            "working_directory": str(self._config.working_directory),
            "timeouts": {
                "read_only_seconds": self._config.read_only_timeout_seconds,
                "decision_seconds": self._config.decision_timeout_seconds,
                "long_seconds": self._config.long_timeout_seconds,
            },
            "stdout_limit_bytes": self._config.stdout_limit_bytes,
            "stderr_limit_bytes": self._config.stderr_limit_bytes,
            "caller_overridable_values": [],
            "environment_key_names": ("PSModulePath", "NO_COLOR"),
        }

    def verify_bridge_integrity(self) -> dict[str, Any]:
        root = self._config.video_studio_root.resolve(strict=False)
        bridge = self._config.bridge_path.resolve(strict=False)
        if not root.is_dir():
            return {"ok": False, "error_code": "VIDEO_STUDIO_ROOT_MISSING", "path": str(root)}
        if not _within_root(root, bridge):
            return {"ok": False, "error_code": "BRIDGE_PATH_OUTSIDE_ROOT", "path": str(bridge)}
        if bridge.is_symlink():
            return {"ok": False, "error_code": "BRIDGE_SYMLINK_REJECTED", "path": str(bridge)}
        if not bridge.is_file():
            return {"ok": False, "error_code": "BRIDGE_NOT_REGULAR_FILE", "path": str(bridge)}
        actual = sha256_file(bridge)
        if actual != self._config.expected_bridge_sha256:
            return {
                "ok": False,
                "error_code": "BRIDGE_HASH_MISMATCH",
                "expected_sha256": self._config.expected_bridge_sha256,
                "actual_sha256": actual,
            }
        self._verified_bridge_sha256 = actual
        return {"ok": True, "bridge_sha256": actual, "bridge_path": str(bridge)}

    def run(
        self,
        *,
        action: str,
        identity: VideoStudioBridgeIdentity,
        input_path: Path | None = None,
    ) -> VideoStudioProcessResult:
        started_at = _now_iso()
        start = time.monotonic()
        if action not in ALLOWED_ACTIONS:
            return self._blocked(action, started_at, start, "UNKNOWN_ACTION")
        integrity = self.verify_bridge_integrity()
        if not integrity["ok"]:
            return self._blocked(action, started_at, start, str(integrity["error_code"]))

        host = self._host_resolver()
        host_error = self._validate_host(host)
        if host_error:
            return self._blocked(action, started_at, start, host_error)

        argv = self._build_argv(host, action, identity, input_path)
        argv_metadata = self._argv_metadata(host, action, bool(input_path))
        pid: int | None = None
        proc = None
        try:
            proc = self._popen_factory(
                argv,
                cwd=str(self._config.working_directory),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self._process_environment(),
                shell=False,
            )
            pid = getattr(proc, "pid", None)
            stdout_bytes, stderr_bytes = proc.communicate(timeout=self._config.timeout_for(action))
            exit_code = int(getattr(proc, "returncode", -1))
        except subprocess.TimeoutExpired:
            cleanup_ok = self._terminate_owned_process(proc)
            stdout_bytes, stderr_bytes = self._communicate_after_cleanup(proc)
            return self._result(
                action=action,
                argv_metadata=argv_metadata,
                pid=pid,
                started_at=started_at,
                start=start,
                timed_out=True,
                process_exit_code=None,
                stdout_bytes=stdout_bytes,
                stderr_bytes=stderr_bytes,
                launch_error=None,
                envelope=None,
                error_code="PROCESS_TIMEOUT",
                cleanup_attempted=True,
                cleanup_succeeded=cleanup_ok,
            )
        except OSError as exc:
            return self._result(
                action=action,
                argv_metadata=argv_metadata,
                pid=pid,
                started_at=started_at,
                start=start,
                timed_out=False,
                process_exit_code=None,
                stdout_bytes=b"",
                stderr_bytes=b"",
                launch_error=exc.__class__.__name__,
                envelope=None,
                error_code="PROCESS_START_FAILED",
            )

        stdout_limit_exceeded = len(stdout_bytes) > self._config.stdout_limit_bytes
        stderr_limit_exceeded = len(stderr_bytes) > self._config.stderr_limit_bytes
        if stdout_limit_exceeded:
            return self._result(
                action=action,
                argv_metadata=argv_metadata,
                pid=pid,
                started_at=started_at,
                start=start,
                timed_out=False,
                process_exit_code=exit_code,
                stdout_bytes=stdout_bytes,
                stderr_bytes=stderr_bytes,
                launch_error=None,
                envelope=None,
                error_code="STDOUT_LIMIT_EXCEEDED",
            )

        stdout_text, decode_error = _decode_strict_utf8(stdout_bytes)
        if decode_error:
            return self._result(
                action=action,
                argv_metadata=argv_metadata,
                pid=pid,
                started_at=started_at,
                start=start,
                timed_out=False,
                process_exit_code=exit_code,
                stdout_bytes=stdout_bytes,
                stderr_bytes=stderr_bytes,
                launch_error=None,
                envelope=None,
                error_code=decode_error,
            )
        envelope, parse_error = parse_single_json_object(stdout_text or "")
        if parse_error:
            return self._result(
                action=action,
                argv_metadata=argv_metadata,
                pid=pid,
                started_at=started_at,
                start=start,
                timed_out=False,
                process_exit_code=exit_code,
                stdout_bytes=stdout_bytes,
                stderr_bytes=stderr_bytes,
                launch_error=None,
                envelope=None,
                error_code=parse_error,
            )
        reconcile_error = self._basic_reconcile(action, identity, exit_code, envelope)
        return self._result(
            action=action,
            argv_metadata=argv_metadata,
            pid=pid,
            started_at=started_at,
            start=start,
            timed_out=False,
            process_exit_code=exit_code,
            stdout_bytes=stdout_bytes,
            stderr_bytes=stderr_bytes,
            launch_error=None,
            envelope=envelope if reconcile_error is None else None,
            error_code=reconcile_error,
            stderr_limit_exceeded=stderr_limit_exceeded,
        )

    def _resolve_powershell_host(self) -> Path:
        fixed_windows_powershell = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
        if fixed_windows_powershell.is_file():
            return fixed_windows_powershell
        for name in ("powershell.exe", "pwsh.exe"):
            found = shutil.which(name)
            if found:
                return Path(found)
        return fixed_windows_powershell

    def _validate_host(self, host: Path) -> str | None:
        resolved = host.resolve(strict=False)
        if resolved.name.lower() not in ALLOWED_POWERSHELL_HOSTS:
            return "POWERSHELL_HOST_NOT_ALLOWLISTED"
        if not resolved.is_file():
            return "POWERSHELL_HOST_NOT_FILE"
        return None

    def _build_argv(
        self,
        host: Path,
        action: str,
        identity: VideoStudioBridgeIdentity,
        input_path: Path | None,
    ) -> list[str]:
        argv = [
            str(host.resolve(strict=False)),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self._config.bridge_path.resolve(strict=False)),
            "-Action",
            action,
        ]
        if input_path is not None:
            argv.extend(("-InputPath", str(input_path)))
        argv.extend(identity.to_args())
        return argv

    def _process_environment(self) -> dict[str, str]:
        env = dict(os.environ)
        user_profile = os.environ.get("USERPROFILE")
        module_paths = []
        if user_profile:
            module_paths.append(str(Path(user_profile) / "Documents" / "WindowsPowerShell" / "Modules"))
        module_paths.extend(
            [
                r"C:\Program Files\WindowsPowerShell\Modules",
                r"C:\WINDOWS\system32\WindowsPowerShell\v1.0\Modules",
            ]
        )
        env["PSModulePath"] = ";".join(module_paths)
        env["NO_COLOR"] = "1"
        return env

    def _argv_metadata(
        self,
        host: Path,
        action: str,
        has_input_path: bool,
    ) -> tuple[tuple[str, str], ...]:
        return (
            ("host_basename", host.name.lower()),
            ("bridge_basename", self._config.bridge_path.name),
            ("action", action),
            ("has_input_path", str(has_input_path).lower()),
            ("uses_shell", "false"),
            ("working_directory", str(self._config.working_directory)),
        )

    def _basic_reconcile(
        self,
        action: str,
        identity: VideoStudioBridgeIdentity,
        process_exit_code: int,
        envelope: dict[str, Any],
    ) -> str | None:
        envelope_exit = envelope.get("exit_code")
        if process_exit_code not in CERTIFIED_EXIT_CODES:
            return "PROCESS_EXIT_CODE_UNKNOWN"
        if envelope_exit not in CERTIFIED_EXIT_CODES:
            return "ENVELOPE_EXIT_CODE_UNKNOWN"
        if process_exit_code != envelope_exit:
            return "PROCESS_ENVELOPE_EXIT_MISMATCH"
        expected = {
            "action": action,
            "scos_project_id": identity.scos_project_id,
            "video_project_id": identity.video_project_id,
            "integration_job_id": identity.integration_job_id,
            "correlation_id": identity.correlation_id,
        }
        for key, value in expected.items():
            if envelope.get(key) != value:
                return f"ENVELOPE_{key.upper()}_MISMATCH"
        if envelope.get("contract_version") != self._config.contract_version:
            return "ENVELOPE_CONTRACT_VERSION_MISMATCH"
        if envelope.get("ok") is True and envelope.get("error") is not None:
            return "ENVELOPE_OK_WITH_ERROR"
        if envelope.get("ok") is False and not isinstance(envelope.get("error"), dict):
            return "ENVELOPE_ERROR_REQUIRED"
        return None

    def _terminate_owned_process(self, proc: Any) -> bool:
        if proc is None:
            return False
        try:
            proc.kill()
            return True
        except Exception:
            return False

    def _communicate_after_cleanup(self, proc: Any) -> tuple[bytes, bytes]:
        if proc is None:
            return b"", b""
        try:
            return proc.communicate(timeout=5)
        except Exception:
            return b"", b""

    def _blocked(
        self,
        action: str,
        started_at: str,
        start: float,
        error_code: str,
    ) -> VideoStudioProcessResult:
        return self._result(
            action=action,
            argv_metadata=(),
            pid=None,
            started_at=started_at,
            start=start,
            timed_out=False,
            process_exit_code=None,
            stdout_bytes=b"",
            stderr_bytes=b"",
            launch_error=None,
            envelope=None,
            error_code=error_code,
        )

    def _result(
        self,
        *,
        action: str,
        argv_metadata: tuple[tuple[str, str], ...],
        pid: int | None,
        started_at: str,
        start: float,
        timed_out: bool,
        process_exit_code: int | None,
        stdout_bytes: bytes,
        stderr_bytes: bytes,
        launch_error: str | None,
        envelope: dict[str, Any] | None,
        error_code: str | None,
        cleanup_attempted: bool = False,
        cleanup_succeeded: bool | None = None,
        stderr_limit_exceeded: bool | None = None,
    ) -> VideoStudioProcessResult:
        finished_at = _now_iso()
        stdout_truncated = len(stdout_bytes) > self._config.stdout_limit_bytes
        stderr_truncated = (
            len(stderr_bytes) > self._config.stderr_limit_bytes
            if stderr_limit_exceeded is None
            else stderr_limit_exceeded
        )
        stdout_text = ""
        if not stdout_truncated:
            decoded, decode_error = _decode_strict_utf8(stdout_bytes)
            stdout_text = "" if decode_error else (decoded or "")
        stderr_excerpt = stderr_bytes[: self._config.stderr_excerpt_bytes].decode(
            "utf-8",
            errors="replace",
        )
        return VideoStudioProcessResult(
            action=action,
            argv_metadata=argv_metadata,
            pid=pid,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=int((time.monotonic() - start) * 1000),
            timed_out=timed_out,
            process_exit_code=process_exit_code,
            stdout_bytes=len(stdout_bytes),
            stderr_bytes=len(stderr_bytes),
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            stdout_text=stdout_text,
            stderr_excerpt=stderr_excerpt,
            launch_error=launch_error,
            envelope=envelope,
            error_code=error_code,
            cleanup_attempted=cleanup_attempted,
            cleanup_succeeded=cleanup_succeeded,
        )
