"""Canonical bounded HyperFrames execution driver for SCOS.

This driver consumes the approved local HyperFrames CLI directly. It does not
create an orchestrator, approval system, or external publication path.

The HAIOS control plane owns routing, artifact identity, evidence, and HumanGate.
SCOS owns this media-runtime boundary: validate -> render -> probe.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Any

from scos.media_binaries import resolve_ffmpeg, resolve_ffprobe

APPROVED_HYPERFRAMES_ROOT = Path(r"C:\Tools\hyperframes-0.7.45")
APPROVED_HYPERFRAMES_VERSION = "0.7.45"
APPROVED_HYPERFRAMES_FRAGMENT = "hyperframes-0.7.45"
HYPERFRAMES_ENV = "SCOS_HYPERFRAMES_BIN"
DEFAULT_TIMEOUT_SECONDS = 900
DRIVER_ID = "scos-hyperframes-cli-driver"

class HyperFramesDriverError(RuntimeError):
    """Raised when the approved HyperFrames boundary cannot be proven."""


@dataclass(frozen=True, slots=True)
class HyperFramesExecutionResult:
    run_id: str
    project_root: str
    artifact_path: str
    artifact_sha256: str
    artifact_size: int
    tool_version: str
    node_version: str
    media_probe: dict[str, Any]
    qa_result: dict[str, Any]
    temporal_qa: dict[str, Any]
    provenance: dict[str, Any]

    def artifact_evidence(self) -> dict[str, Any]:
        return {
            "artifact_id": f"hyperframes:{self.run_id}:{self.artifact_sha256[:16]}",
            "run_id": self.run_id,
            "artifact_sha256": self.artifact_sha256,
            "artifact_path": self.artifact_path,
            "artifact_size": self.artifact_size,
            "manifest": {
                "run_id": self.run_id,
                "engine": "hyperframes",
                "engine_version": self.tool_version,
            },
            "media_probe": self.media_probe,
            "qa_result": self.qa_result,
            "temporal_qa": self.temporal_qa,
            "provenance": self.provenance,
            "observed_at": self.provenance["observed_at"],
            "approval_state": "PENDING_HUMAN",
            "delivery_id": f"delivery:hyperframes:{self.run_id}:{self.artifact_sha256[:16]}",
            "publish_attempt_id": None,
            "platform_state": "NOT_SUBMITTED",
            "readback_state": "NOT_AVAILABLE",
        }


def _canonical_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


CONTRACT_DIGEST = _canonical_digest(
    {
        "driver_id": DRIVER_ID,
        "tool_root_fragment": APPROVED_HYPERFRAMES_FRAGMENT,
        "tool_version": APPROVED_HYPERFRAMES_VERSION,
        "commands": ["lint", "validate", "render", "ffprobe"],
        "render": {"format": "mp4", "fps": 30, "quality": "standard", "workers": 1},
    }
)


def _resolved_launcher() -> Path:
    raw = os.environ.get(HYPERFRAMES_ENV)
    candidate = Path(raw) if raw else APPROVED_HYPERFRAMES_ROOT / "node_modules" / ".bin" / "hyperframes.cmd"
    if candidate.is_dir():
        candidate = candidate / "hyperframes.cmd"
    try:
        launcher = candidate.resolve(strict=True)
    except OSError as exc:
        raise HyperFramesDriverError("HYPERFRAMES_LAUNCHER_MISSING") from exc
    if not launcher.is_file() or launcher.name.lower() != "hyperframes.cmd":
        raise HyperFramesDriverError("HYPERFRAMES_LAUNCHER_INVALID")
    try:
        launcher.relative_to(APPROVED_HYPERFRAMES_ROOT.resolve(strict=True))
    except ValueError as exc:
        raise HyperFramesDriverError("HYPERFRAMES_LAUNCHER_OUTSIDE_APPROVED_ROOT") from exc
    return launcher


def _safe_runtime_env(launcher: Path) -> tuple[dict[str, str], str]:
    node = shutil.which("node", path=os.environ.get("PATH", ""))
    if not node:
        raise HyperFramesDriverError("NODE_RUNTIME_MISSING")
    node_path = Path(node).resolve(strict=True)
    env: dict[str, str] = {}
    for key in ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "TEMP", "TMP", "PATHEXT"):
        value = os.environ.get(key)
        if value:
            env[key] = value
    ffmpeg_path = Path(resolve_ffmpeg()).resolve(strict=True)
    ffprobe_path = Path(resolve_ffprobe()).resolve(strict=True)
    system_root = env.get("SYSTEMROOT") or env.get("WINDIR")
    if not system_root:
        raise HyperFramesDriverError("WINDOWS_RUNTIME_ROOT_MISSING")
    system_dirs = [Path(system_root) / "System32"]
    env["PATH"] = os.pathsep.join(
        [
            str(node_path.parent),
            str(launcher.parent),
            str(ffmpeg_path.parent),
            str(ffprobe_path.parent),
            *(str(item) for item in system_dirs if item.is_dir()),
        ]
    )
    return env, str(node_path)


def _run(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_seconds: int,
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            argv,
            cwd=str(cwd),
            shell=False,
            capture_output=True,
            text=False,
            timeout=timeout_seconds,
            input=b"",
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise HyperFramesDriverError("HYPERFRAMES_COMMAND_TIMEOUT") from exc
    except (OSError, ValueError) as exc:
        raise HyperFramesDriverError("HYPERFRAMES_COMMAND_LAUNCH_FAILED") from exc


def _decode(output: bytes, limit: int = 4000) -> str:
    return (output or b"")[-limit:].decode("utf-8", errors="replace")


def _assert_success(name: str, proc: subprocess.CompletedProcess[bytes]) -> str:
    stdout = _decode(proc.stdout)
    if proc.returncode != 0:
        raise HyperFramesDriverError(f"HYPERFRAMES_{name.upper()}_FAILED:{proc.returncode}")
    return stdout
def _validate_launcher(
    launcher: Path,
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_seconds: int,
) -> tuple[str, str]:
    version = _assert_success(
        "version",
        _run([str(launcher), "--version"], cwd=cwd, env=env, timeout_seconds=timeout_seconds),
    ).strip()
    if version != APPROVED_HYPERFRAMES_VERSION:
        raise HyperFramesDriverError("HYPERFRAMES_VERSION_MISMATCH")

    node_path = env["PATH"].split(os.pathsep, 1)[0]
    node_version = _assert_success(
        "node",
        _run(
            [str(Path(node_path) / "node.exe"), "--version"],
            cwd=cwd,
            env=env,
            timeout_seconds=timeout_seconds,
        ),
    ).strip()
    if not node_version.startswith(("v22.", "v23.", "v24.")):
        raise HyperFramesDriverError("NODE_VERSION_UNQUALIFIED")
    return version, node_version


def _probe_artifact(path: Path, *, ffprobe: str, cwd: Path, env: dict[str, str], timeout_seconds: int) -> dict[str, Any]:
    proc = _run(
        [
            ffprobe,
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries",
            "stream=codec_name,width,height,r_frame_rate,nb_frames,duration",
            "-show_entries",
            "format=duration,size",
            "-of", "json",
            str(path),
        ],
        cwd=cwd,
        env=env,
        timeout_seconds=timeout_seconds,
    )
    raw = _assert_success("ffprobe", proc)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HyperFramesDriverError("FFPROBE_JSON_INVALID") from exc
    streams = payload.get("streams")
    if not isinstance(streams, list) or len(streams) != 1:
        raise HyperFramesDriverError("VIDEO_STREAM_REQUIRED")
    stream = streams[0]
    fmt = payload.get("format")
    if not isinstance(fmt, dict):
        raise HyperFramesDriverError("FORMAT_PROBE_REQUIRED")
    probe = {
        "codec": stream.get("codec_name"),
        "width": int(stream.get("width", 0)),
        "height": int(stream.get("height", 0)),
        "r_frame_rate": str(stream.get("r_frame_rate", "")),
        "nb_frames": int(stream.get("nb_frames", 0)),
        "duration": float(fmt.get("duration", stream.get("duration", 0.0))),
        "size": int(fmt.get("size", 0)),
        "container": "mp4",
    }
    if probe["codec"] != "h264" or probe["width"] <= 0 or probe["height"] <= 0:
        raise HyperFramesDriverError("MEDIA_PROBE_UNQUALIFIED")
    if probe["size"] <= 0 or path.stat().st_size != probe["size"]:
        raise HyperFramesDriverError("ARTIFACT_SIZE_MISMATCH")
    return probe


def _temporal_qa(probe: dict[str, Any]) -> dict[str, Any]:
    rate = probe["r_frame_rate"]
    if rate not in {"30/1", "30000/1000"}:
        raise HyperFramesDriverError("TEMPORAL_FPS_UNQUALIFIED")
    frames = int(probe["nb_frames"])
    duration = float(probe["duration"])
    expected = round(duration * 30)
    frame_delta = abs(frames - expected)
    duration_delta = abs(duration - (frames / 30))
    if frames <= 0 or frame_delta > 1 or duration_delta > (1 / 30):
        raise HyperFramesDriverError("TEMPORAL_QA_FAILED")
    return {
        "status": "PASS",
        "fps": 30,
        "frame_count": frames,
        "duration_seconds": duration,
        "expected_frames": expected,
        "frame_count_delta": frame_delta,
        "duration_delta_seconds": duration_delta,
        "cfr": True,
    }


def render_hyperframes(
    *,
    run_id: str,
    project_root: str | Path,
    output_path: str | Path | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> HyperFramesExecutionResult:
    if not isinstance(run_id, str) or not run_id.strip():
        raise HyperFramesDriverError("RUN_ID_REQUIRED")
    if type(timeout_seconds) is not int or timeout_seconds <= 0:
        raise HyperFramesDriverError("TIMEOUT_INVALID")

    project = Path(project_root).resolve(strict=True)
    if not project.is_dir():
        raise HyperFramesDriverError("PROJECT_ROOT_REQUIRED")
    index = project / "index.html"
    if not index.is_file():
        raise HyperFramesDriverError("HYPERFRAMES_PROJECT_ENTRY_MISSING")
    launcher = _resolved_launcher()
    env, node_version = _safe_runtime_env(launcher)
    tool_version, node_version = _validate_launcher(
        launcher,
        cwd=project,
        env=env,
        timeout_seconds=timeout_seconds,
    )

    if output_path is None:
        output = project / "renders" / f"{run_id}.mp4"
    else:
        output = Path(output_path).resolve(strict=False)
    renders_root = (project / "renders").resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        output.relative_to(renders_root)
    except ValueError as exc:
        raise HyperFramesDriverError("OUTPUT_OUTSIDE_PROJECT_RENDERS") from exc

    lint = _run(
        [str(launcher), "lint"],
        cwd=project,
        env=env,
        timeout_seconds=timeout_seconds,
    )
    lint_out = _assert_success("lint", lint)

    validate = _run(
        [str(launcher), "validate"],
        cwd=project,
        env=env,
        timeout_seconds=timeout_seconds,
    )
    validate_out = _assert_success("validate", validate)

    render = _run(
        [
            str(launcher),
            "render",
            "--output", str(output),
            "--format", "mp4",
            "--fps", "30",
            "--quality", "standard",
            "--workers", "1",
        ],
        cwd=project,
        env=env,
        timeout_seconds=timeout_seconds,
    )
    render_out = _assert_success("render", render)

    if not output.is_file() or output.stat().st_size <= 0:
        raise HyperFramesDriverError("ARTIFACT_MISSING")

    ffprobe = resolve_ffprobe()
    media_probe = _probe_artifact(
        output,
        ffprobe=ffprobe,
        cwd=project,
        env=env,
        timeout_seconds=timeout_seconds,
    )
    temporal_qa = _temporal_qa(media_probe)
    artifact_bytes = output.read_bytes()
    digest = hashlib.sha256(artifact_bytes).hexdigest()
    observed_at = datetime.now(timezone.utc).isoformat()
    qa_result = {
        "passed": True,
        "checks": ["lint", "validate"],
        "lint_exit_code": lint.returncode,
        "validate_exit_code": validate.returncode,
        "lint_output_digest": hashlib.sha256(lint_out.encode("utf-8")).hexdigest(),
        "validate_output_digest": hashlib.sha256(validate_out.encode("utf-8")).hexdigest(),
        "render_output_digest": hashlib.sha256(render_out.encode("utf-8")).hexdigest(),
    }
    provenance = {
        "run_id": run_id,
        "source": "scos.hyperframes_driver",
        "driver_id": DRIVER_ID,
        "engine": "hyperframes",
        "engine_version": tool_version,
        "node_version": node_version,
        "contract_digest": CONTRACT_DIGEST,
        "observed_at": observed_at,
    }
    return HyperFramesExecutionResult(
        run_id=run_id,
        project_root=str(project),
        artifact_path=str(output),
        artifact_sha256=digest,
        artifact_size=output.stat().st_size,
        tool_version=tool_version,
        node_version=node_version,
        media_probe=media_probe,
        qa_result=qa_result,
        temporal_qa=temporal_qa,
        provenance=provenance,
    )


__all__ = [
    "APPROVED_HYPERFRAMES_ROOT",
    "APPROVED_HYPERFRAMES_VERSION",
    "CONTRACT_DIGEST",
    "DRIVER_ID",
    "HyperFramesDriverError",
    "HyperFramesExecutionResult",
    "render_hyperframes",
]
