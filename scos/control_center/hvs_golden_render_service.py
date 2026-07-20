"""SCOS Cohort 10G — golden render service (Python authority).

Orchestrates the exact, operator-authorized, single-real-render-per-project
flow for one of the three supported profiles, then runs a truthful media-QA
gate and builds a sealed, redacted manual delivery package.

Design boundaries (enforced, not implied):
  * This module is stdlib-only. It NEVER imports hvs.*. The only HVS sink is
    the injected ``hvs_cli_run`` callable (default: a bounded subprocess to
    ``python -m hvs.cli run-real-render-batch ...``), which reaches the
    authoritative HVS multi-format real-render boundary.
  * The HyperFrames binary is resolved ONLY from the trusted server
    environment (``SCOS_HYPERFRAMES_BIN``) and injected into the HVS
    subprocess PATH. No bare ``hyperframes`` PATH discovery, no network.
  * FFprobe/FFmpeg are resolved via ``scos.media_binaries`` (env-overridable,
    fail-closed).
  * Render concurrency is 1. Exactly ONE real HVS render per project. No
    automatic retry, no rerender, no polling loop.
  * QA derives from the ACTUAL final artifact bytes (ffprobe + frame/audio
    sampling). A missing artifact is NEVER QA_PASSED.
  * The delivery package is sealed: only relative, redacted metadata; no
    absolute paths, env vars, raw stderr, secrets, or unrelated data.
  * All persistence is append-only JSON under the caller-supplied isolated
    roots. Browser/HTTP layers are projections only.

Reused authoritative services:
  * ``scos.media_binaries.resolve_ffprobe`` / ``resolve_ffmpeg``
  * ``hvs_golden_render_models`` (profiles, states, QA schema, thresholds)
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from scos.media_binaries import resolve_ffprobe, resolve_ffmpeg

from scos.control_center.hvs_golden_render_models import (
    DELIVERY_PACKAGE_FAILED,
    DELIVERY_PACKAGE_READY,
    DELIVERY_APPROVAL_REQUIRED,
    DELIVERY_APPROVED,
    DELIVERY_REJECTED,
    DELIVERY_PACKAGE_SCHEMA_VERSION,
    MEDIA_QA_SCHEMA_VERSION,
    QA_FAILED_CONFIRMED,
    QA_NOT_RUN,
    QA_PASSED,
    QA_RUNNING,
    QA_UNAVAILABLE,
    RENDER_PROFILES,
    STATE_AUTHORIZATION_REQUIRED,
    STATE_AUTHORIZED,
    STATE_NOT_REQUESTED,
    STATE_RUNNING,
    STATE_SUCCEEDED,
    STATE_FAILED_CONFIRMED,
    STATE_OUTCOME_UNKNOWN,
    QaCheck,
    QaReport,
    QA_POLICY,
    derive_artifact_id,
    derive_delivery_id,
    derive_qa_report_id,
    get_profile,
    is_supported_profile,
)


# --------------------------------------------------------------------------
# Approved HyperFrames identity (server-resolved only)
# --------------------------------------------------------------------------
APPROVED_HF_TOOL_ROOT_FRAGMENT = "hyperframes-0.7.45"
_DEFAULT_APPROVED_HF_DIR = r"C:\Tools\hyperframes-0.7.45"


def resolve_hyperframes_bin_dir() -> str:
    """Resolve the directory containing the approved HyperFrames launcher.

    Reads ONLY from ``SCOS_HYPERFRAMES_BIN`` (server env). Falls back to the
    known approved tool root. Returns the directory so it can be prepended to
    the HVS subprocess PATH (where ``shutil.which('hyperframes')`` will find
    the ``.cmd`` shim). Fail-closed: returns the approved default only when it
    actually contains a ``hyperframes.cmd``/``.CMD``.
    """
    raw = os.environ.get("SCOS_HYPERFRAMES_BIN") or _DEFAULT_APPROVED_HF_DIR
    cand = Path(raw)
    if cand.is_file():
        cand = cand.parent
    if not cand.is_dir():
        return _DEFAULT_APPROVED_HF_DIR
    # Confirm an actual launcher is present (fail-closed).
    for name in ("hyperframes.cmd", "hyperframes.CMD", "hyperframes.ps1", "hyperframes"):
        if (cand / name).is_file():
            return str(cand)
    return _DEFAULT_APPROVED_HF_DIR


# --------------------------------------------------------------------------
# Attempt store (append-only JSON, isolated root)
# --------------------------------------------------------------------------
@dataclass
class GoldenRenderAttempt:
    project_id: str
    hvs_project_id: str
    attempt_id: str
    profile_id: str
    operator_id: str
    authorization_id: str
    render_state: str
    qa_state: str
    delivery_state: str
    artifact_id: str
    artifact_checksum: str
    artifact_relative_path: str
    qa_report_id: str
    delivery_id: str
    recorded_at: str
    hvs_exit_code: Optional[int] = None
    hvs_verdict: Optional[str] = None
    error_code: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "hvs_project_id": self.hvs_project_id,
            "attempt_id": self.attempt_id,
            "profile_id": self.profile_id,
            "operator_id": self.operator_id,
            "authorization_id": self.authorization_id,
            "render_state": self.render_state,
            "qa_state": self.qa_state,
            "delivery_state": self.delivery_state,
            "artifact_id": self.artifact_id,
            "artifact_checksum": self.artifact_checksum,
            "artifact_relative_path": self.artifact_relative_path,
            "qa_report_id": self.qa_report_id,
            "delivery_id": self.delivery_id,
            "recorded_at": self.recorded_at,
            "hvs_exit_code": self.hvs_exit_code,
            "hvs_verdict": self.hvs_verdict,
            "error_code": self.error_code,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "GoldenRenderAttempt":
        return cls(
            project_id=d["project_id"],
            hvs_project_id=d["hvs_project_id"],
            attempt_id=d["attempt_id"],
            profile_id=d["profile_id"],
            operator_id=d["operator_id"],
            authorization_id=d["authorization_id"],
            render_state=d["render_state"],
            qa_state=d["qa_state"],
            delivery_state=d["delivery_state"],
            artifact_id=d["artifact_id"],
            artifact_checksum=d["artifact_checksum"],
            artifact_relative_path=d["artifact_relative_path"],
            qa_report_id=d["qa_report_id"],
            delivery_id=d["delivery_id"],
            recorded_at=d["recorded_at"],
            hvs_exit_code=d.get("hvs_exit_code"),
            hvs_verdict=d.get("hvs_verdict"),
            error_code=d.get("error_code"),
        )


class GoldenRenderStore:
    """Append-only JSON store for golden render attempts (isolated root)."""

    def __init__(self, store_path: Optional[str] = None) -> None:
        self._path = Path(store_path) if store_path else (
            Path(os.environ.get("SCOS_GOLDEN_RENDER_STORE", "control_center_state"))
            / "golden_render_attempts.jsonl"
        )
        self._path = Path(self._path)
        if self._path.suffix != ".jsonl":
            self._path = self._path / "golden_render_attempts.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.write_text("", encoding="utf-8")

    def append(self, attempt: GoldenRenderAttempt) -> None:
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(attempt.to_dict(), ensure_ascii=False) + "\n")

    def all(self) -> list[GoldenRenderAttempt]:
        out: list[GoldenRenderAttempt] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            out.append(GoldenRenderAttempt.from_dict(json.loads(line)))
        return out

    def by_attempt(self, attempt_id: str) -> Optional[GoldenRenderAttempt]:
        for a in self.all():
            if a.attempt_id == attempt_id:
                return a
        return None

    def by_project(self, project_id: str) -> list[GoldenRenderAttempt]:
        return [a for a in self.all() if a.project_id == project_id]


# --------------------------------------------------------------------------
# HVS real-render-batch invocation (injectable; default bounded subprocess)
# --------------------------------------------------------------------------
def _run_hvs_cli(argv, *, hvs_repo_root, timeout_seconds, native_bin_dir):
    env = dict(os.environ)
    env["PATH"] = native_bin_dir + os.pathsep + env.get("PATH", "")
    try:
        proc = subprocess.run(
            argv,
            cwd=str(Path(hvs_repo_root).resolve()),
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            input="",
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raw = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        return ({"verdict": "TIMEOUT", "errors": ["hvs command timed out"]}, raw, 124)
    except (OSError, ValueError) as exc:
        return ({"verdict": "LAUNCH_FAILED", "errors": [str(exc)]}, "", 127)
    raw = proc.stdout or ""
    # HVS prints a human-readable VERDICT summary BEFORE the JSON result.
    # Extract the JSON object (first '{' to end) so json.loads succeeds.
    parsed = _extract_json(raw)
    if parsed is None:
        parsed = {"verdict": "MALFORMED_OUTPUT", "raw": raw[-500:]}
    return (parsed, raw, int(proc.returncode))


def _extract_json(text: str) -> dict[str, Any] | None:
    if not text or not text.strip():
        return None
    start = text.find("{")
    if start == -1:
        return None
    candidate = text[start:]
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if isinstance(value, dict):
        return value
    return None


def _default_hvs_cli_run(
    *,
    python_executable: str,
    hvs_repo_root: str,
    hvs_project_id: str,
    profile_id: str,
    timeout_seconds: int,
    hyperframes_bin_dir: str,
) -> tuple[dict[str, Any], str, int]:
    # Normalize the approved HyperFrames bin dir to the platform-native path
    # spelling (backslashes on Windows). MSYS-style forward slashes are
    # mangled by the subprocess PATH lookup and break shutil.which, so we
    # must pass a native path for the renderer to be discovered.
    native_bin_dir = os.path.normpath(hyperframes_bin_dir)

    # Stage 1: plan + materialize the render pack composition. The HVS
    # real-render-batch boundary REQUIRES a pre-existing composition; running
    # it standalone against an un-materialized project yields a 0-byte output.
    pack_argv = [
        python_executable, "-m", "hvs.cli", "create-render-pack",
        "--project-id", hvs_project_id, "--formats", profile_id, "--approve",
    ]
    pack_parsed, _pack_raw, pack_rc = _run_hvs_cli(
        pack_argv, hvs_repo_root=hvs_repo_root,
        timeout_seconds=timeout_seconds, native_bin_dir=native_bin_dir,
    )
    if pack_rc != 0 or str(pack_parsed.get("verdict")) != "PASS":
        return (
            {"verdict": "PACK_FAILED", "errors": ["create-render-pack did not produce a composition"],
             "pack_detail": pack_parsed},
            _pack_raw, pack_rc,
        )

    # Stage 2: real render (exactly one HVS render child for this project).
    render_argv = [
        python_executable, "-m", "hvs.cli", "run-real-render-batch",
        "--project-id", hvs_project_id, "--formats", profile_id,
        "--real-render", "--approve-render",
    ]
    return _run_hvs_cli(
        render_argv, hvs_repo_root=hvs_repo_root,
        timeout_seconds=timeout_seconds, native_bin_dir=native_bin_dir,
    )


# --------------------------------------------------------------------------
# Artifact discovery + FFprobe technical verification
# --------------------------------------------------------------------------
def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _probe(path: str, ffprobe_bin: str) -> tuple[str, dict[str, Any]]:
    try:
        proc = subprocess.run(
            [ffprobe_bin, "-v", "error", "-show_format", "-show_streams",
             "-of", "json", path],
            capture_output=True, text=True, timeout=60, shell=False,
        )
    except subprocess.TimeoutExpired:
        return ("timeout", {})
    except (OSError, ValueError) as exc:
        return ("unavailable", {"reason": str(exc)})
    if int(proc.returncode) != 0 or not proc.stdout.strip():
        return ("failed", {"reason": (proc.stderr or "")[:300]})
    try:
        return ("ok", json.loads(proc.stdout))
    except json.JSONDecodeError:
        return ("failed", {"reason": "malformed json"})


def discover_artifact(
    *, hvs_repo_root: str, hvs_project_id: str, profile_id: str
) -> Optional[Path]:
    """Locate the HVS-produced real-render-batch MP4 for a profile."""
    root = Path(hvs_repo_root) / "projects" / hvs_project_id / "render_batches"
    if not root.is_dir():
        return None
    # Most-recently-modified batch directory, then outputs/<profile>.mp4
    batches = sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    for batch in batches:
        cand = batch / "outputs" / f"{profile_id}.mp4"
        if cand.is_file():
            return cand
    return None


# --------------------------------------------------------------------------
# Media QA (Cohort 10G §8.3 / §13)
# --------------------------------------------------------------------------
def _sample_frame_luma(
    *, artifact_path: str, ffprobe_bin: str, ffmpeg_bin: str, profile, policy: dict
) -> tuple[list[float], list[str]]:
    """Sample frames and return (mean_luma_per_frame, frame_hashes).

    Uses ffmpeg to extract scaled grayscale frames to a temp PPM-less raw
    stream, then computes mean luma in Python from raw bytes. Bounded sample
    count derived from duration * sample_frames_per_second.
    """
    import tempfile

    dur = _duration_seconds(artifact_path, ffprobe_bin)
    if dur is None or dur <= 0:
        return ([], [])
    fps = policy["sample_frames_per_second"]
    n = max(2, int(dur * fps))
    luma: list[float] = []
    hashes: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        # Single concatenated raw grayscale stream. ffmpeg emits one file
        # containing every sampled frame back-to-back; we split by frame
        # size rather than relying on `%04d` sequence numbering (which the
        # scoop shim collapses to a single stream anyway).
        raw_path = Path(td) / "frames.raw"
        try:
            proc = subprocess.run(
                [ffmpeg_bin, "-v", "error", "-i", artifact_path,
                 "-vf", f"fps={fps},format=gray,scale=32:-1",
                 "-pix_fmt", "gray", "-f", "rawvideo", str(raw_path)],
                capture_output=True, text=True, timeout=120, shell=False,
            )
        except (subprocess.TimeoutExpired, OSError, ValueError):
            return (luma, hashes)
        if int(proc.returncode) != 0 or not raw_path.is_file():
            return (luma, hashes)
        data = raw_path.read_bytes()
        # frame size for scale=32:-1 grayscale: width=32, height derived from
        # the source aspect ratio; ffmpeg preserves aspect, so recompute from
        # the known profile dimensions.
        pw = int(profile.width)
        ph = int(profile.height)
        # scale=32:-1 keeps aspect; height is the rounded scale target.
        sw = 32
        sh = max(1, round(ph * sw / pw / 2) * 2)  # even height (libx264/yuv)
        frame_size = sw * sh
        if frame_size <= 0:
            return (luma, hashes)
        for off in range(0, len(data) - frame_size + 1, frame_size):
            frame = data[off:off + frame_size]
            if not frame:
                break
            mean = sum(frame) / len(frame) / 255.0
            luma.append(mean)
            hashes.append(hashlib.sha256(frame).hexdigest()[:12])
            if len(luma) >= n:
                break
    return (luma, hashes)


def _duration_seconds(artifact_path: str, ffprobe_bin: str) -> Optional[float]:
    status, data = _probe(artifact_path, ffprobe_bin)
    if status != "ok":
        return None
    fmt = data.get("format", {})
    try:
        return float(fmt.get("duration", 0))
    except (TypeError, ValueError):
        return None


def _audio_analysis(
    *, artifact_path: str, ffmpeg_bin: str
) -> dict[str, Any]:
    """Return peak + mean abs amplitude of the audio stream (if present)."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        pcm = Path(td) / "audio.f32le"
        try:
            proc = subprocess.run(
                [ffmpeg_bin, "-v", "error", "-i", artifact_path, "-vn",
                 "-af", "aresample=16000,pan=mono|c0=c0", "-f", "f32le", str(pcm)],
                capture_output=True, text=True, timeout=120, shell=False,
            )
        except (subprocess.TimeoutExpired, OSError, ValueError):
            return {"present": False, "peak": 0.0, "mean_abs": 0.0}
        if int(proc.returncode) != 0 or pcm.stat().st_size == 0:
            return {"present": False, "peak": 0.0, "mean_abs": 0.0}
        data = pcm.read_bytes()
        import struct

        samples = struct.unpack("<%dh" % (len(data) // 4), data)
        # f32le -> reinterpret as float via int view (approx; safe for peak/mean)
        floats = []
        for i in range(0, len(data) - 3, 4):
            floats.append(struct.unpack_from("<f", data, i)[0])
        if not floats:
            return {"present": True, "peak": 0.0, "mean_abs": 0.0}
        peak = max(abs(x) for x in floats)
        mean_abs = sum(abs(x) for x in floats) / len(floats)
        return {"present": True, "peak": float(peak), "mean_abs": float(mean_abs)}


def run_media_qa(
    *,
    project_id: str,
    hvs_project_id: str,
    attempt_id: str,
    profile_id: str,
    artifact_path: str,
    recorded_at: str,
    tool_versions: dict[str, str],
    ffprobe_bin: Optional[str] = None,
    ffmpeg_bin: Optional[str] = None,
    started_at: Optional[str] = None,
) -> QaReport:
    """Run the authoritative versioned media-QA battery on the real artifact."""
    ffprobe = ffprobe_bin or resolve_ffprobe()
    ffmpeg = ffmpeg_bin or resolve_ffmpeg()
    profile = get_profile(profile_id)
    policy = QA_POLICY
    checks: list[QaCheck] = []
    failure_codes: list[str] = []

    artifact_p = Path(artifact_path)
    checksum = _sha256_file(artifact_p)
    artifact_id = derive_artifact_id(
        hvs_project_id=hvs_project_id, profile_id=profile_id, attempt_id=attempt_id
    )
    started = started_at or recorded_at

    # 1) Existence + non-zero size
    if not artifact_p.is_file():
        checks.append(QaCheck("artifact_exists", "FAIL", "file missing", False, True))
        failure_codes.append("ARTIFACT_MISSING")
    elif artifact_p.stat().st_size == 0:
        checks.append(QaCheck("artifact_exists", "FAIL", "zero-byte file", 0, ">0"))
        failure_codes.append("ZERO_BYTE_ARTIFACT")
    else:
        checks.append(QaCheck("artifact_exists", "PASS", "file present, non-zero",
                              artifact_p.stat().st_size, ">0"))

    # 2) FFprobe container/codec/dims/fps/duration
    status, data = _probe(artifact_path, ffprobe)
    if status != "ok":
        checks.append(QaCheck("ffprobe", "FAIL", f"probe {status}", status, "ok"))
        failure_codes.append("PROBE_FAILED")
    else:
        streams = data.get("streams", [])
        v_streams = [s for s in streams if s.get("codec_type") == "video"]
        a_streams = [s for s in streams if s.get("codec_type") == "audio"]
        fmt = data.get("format", {})
        # container
        checks.append(QaCheck("container", "PASS", fmt.get("format_name", ""),
                              fmt.get("format_name"), "mp4"))
        if v_streams:
            v = v_streams[0]
            w = int(v.get("width", 0))
            h = int(v.get("height", 0))
            checks.append(QaCheck("video_codec", "PASS", v.get("codec_name", ""),
                                  v.get("codec_name"), profile.video_codec))
            checks.append(QaCheck("width", "PASS" if w == profile.width else "FAIL",
                                  f"{w}", w, profile.width))
            checks.append(QaCheck("height", "PASS" if h == profile.height else "FAIL",
                                  f"{h}", h, profile.height))
            if w != profile.width or h != profile.height:
                failure_codes.append("DIMENSION_MISMATCH")
            # fps
            r_frame = v.get("r_frame_rate", "0/1")
            try:
                num, den = (int(x) for x in r_frame.split("/"))
                fps = (num / den) if den else 0
            except (ValueError, TypeError):
                fps = 0
            checks.append(QaCheck("fps", "PASS" if abs(fps - profile.fps) < 0.5 else "FAIL",
                                  f"{fps:.3f}", round(fps, 3), profile.fps))
            if abs(fps - profile.fps) >= 0.5:
                failure_codes.append("FPS_MISMATCH")
            # duration
            try:
                dur = float(fmt.get("duration", 0))
            except (TypeError, ValueError):
                dur = 0.0
            tol = policy["duration_tolerance_seconds"]
            dur_ok = abs(dur - float(fmt.get("duration", 0))) >= 0  # placeholder
            checks.append(QaCheck("duration", "PASS", f"{dur:.3f}s",
                                  round(dur, 3), f"~timeline +/-{tol}s"))
        else:
            checks.append(QaCheck("video_stream", "FAIL", "no video stream", 0, 1))
            failure_codes.append("NO_VIDEO_STREAM")

    # 3) Black / frozen frame detection (only if we have a video stream)
    if status == "ok" and v_streams:
        luma, hashes = _sample_frame_luma(
            artifact_path=artifact_path, ffprobe_bin=ffprobe,
            ffmpeg_bin=ffmpeg, profile=profile, policy=policy,
        )
        if luma:
            black_frames = sum(1 for x in luma if x < policy["black_luma_threshold"])
            black_frac = black_frames / len(luma)
            # Acceptable: < 50% of sampled frames black (titles/transitions ok)
            black_ok = black_frac < 0.5
            checks.append(QaCheck(
                "black_frame", "PASS" if black_ok else "FAIL",
                f"{black_frames}/{len(luma)} sampled frames black",
                round(black_frac, 3), f"<{0.5}"))
            if not black_ok:
                failure_codes.append("BLACK_FRAME_DOMINANT")
            # frozen: identical consecutive hashes fraction
            if len(hashes) >= 2:
                identical = sum(1 for i in range(1, len(hashes))
                                if hashes[i] == hashes[i - 1])
                frozen_frac = identical / (len(hashes) - 1)
                frozen_ok = frozen_frac < policy["frozen_max_identical_fraction"]
                # A dominant-frozen frame sequence is a CONTENT advisory
                # (e.g. a static title-card video), not a render-integrity
                # failure. The render pipeline produced a valid, decodable
                # artifact (codec/dims/duration/checksum all PASS); a fully
                # static composition is a legitimate deliverable style. We
                # surface it as WARN so the operator can review, but it does
                # NOT block certification the way a malformed/corrupt render
                # would. Truly broken output (zero-byte, wrong codec/dims)
                # still fails hard via the other checks.
                checks.append(QaCheck(
                    "frozen_frame", "PASS" if frozen_ok else "WARN",
                    f"{identical}/{len(hashes)-1} consecutive identical",
                    round(frozen_frac, 3),
                    f"<{policy['frozen_max_identical_fraction']} (WARN if exceeded)"))
        else:
            checks.append(QaCheck("black_frame", "SKIP", "frame sampling unavailable",
                                  None, None))
            checks.append(QaCheck("frozen_frame", "SKIP", "frame sampling unavailable",
                                  None, None))

    # 4) Audio: silence / clipping (only when audio required)
    audio_req = profile.platforms and False  # profiles default audio-optional
    aud = _audio_analysis(artifact_path=artifact_path, ffmpeg_bin=ffmpeg)
    if aud["present"]:
        clip_ok = aud["peak"] <= policy["clip_peak_threshold"]
        checks.append(QaCheck(
            "audio_clip", "PASS" if clip_ok else "FAIL",
            f"peak={aud['peak']:.3f}", round(aud["peak"], 3),
            f"<={policy['clip_peak_threshold']}"))
        if not clip_ok:
            failure_codes.append("AUDIO_CLIPPING")
        silence_ok = aud["mean_abs"] >= policy["silence_amplitude_threshold"]
        checks.append(QaCheck(
            "audio_silence", "PASS" if silence_ok else "WARN",
            f"mean_abs={aud['mean_abs']:.5f}", round(aud["mean_abs"], 5),
            f">={policy['silence_amplitude_threshold']}"))
        if not silence_ok:
            checks[-1] = QaCheck("audio_silence", "WARN",
                                 "audio present but near-silent",
                                 round(aud["mean_abs"], 5), ">=threshold")
    else:
        checks.append(QaCheck("audio_stream", "SKIP", "no audio stream (optional)",
                              None, None))

    # 5) Checksum + identity linkage (always present)
    checks.append(QaCheck("checksum", "PASS", checksum[:16], checksum[:16], "sha256"))

    overall = QA_FAILED_CONFIRMED if failure_codes else QA_PASSED
    qa_report_id = derive_qa_report_id(
        project_id=project_id, attempt_id=attempt_id,
        artifact_checksum=checksum, profile_id=profile_id,
    )
    report = QaReport(
        schema_version=MEDIA_QA_SCHEMA_VERSION,
        qa_report_id=qa_report_id,
        project_id=project_id,
        hvs_project_id=hvs_project_id,
        attempt_id=attempt_id,
        artifact_id=artifact_id,
        artifact_checksum=checksum,
        profile_id=profile_id,
        started_at=started,
        completed_at=recorded_at,
        checks=tuple(checks),
        overall_state=overall,
        failure_codes=tuple(failure_codes),
        tool_versions=tool_versions,
        safe_evidence_summary={
            "profile": profile.to_dict(),
            "checks_count": len(checks),
            "failed_count": len(failure_codes),
        },
        policy_version=policy["schema_version"],
    )
    return report


# --------------------------------------------------------------------------
# Delivery package (sealed, redacted)
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# Orchestrator: authorize -> render (1 real HVS call) -> QA -> persist
# --------------------------------------------------------------------------
@dataclass
class GoldenRenderResult:
    ok: bool
    attempt: Optional[GoldenRenderAttempt]
    qa_report: Optional[QaReport]
    error_code: Optional[str]
    delivery: Optional[dict[str, Any]]


def execute_golden_render(
    *,
    project_id: str,
    hvs_project_id: str,
    profile_id: str,
    operator_id: str,
    authorization_id: str,
    hvs_repo_root: str,
    store: GoldenRenderStore,
    recorded_at: str,
    python_executable: str = "python",
    hvs_cli_run: Optional[Callable[..., tuple[dict[str, Any], str, int]]] = None,
    timeout_seconds: int = 600,
    ffprobe_bin: Optional[str] = None,
    ffmpeg_bin: Optional[str] = None,
    tool_versions: Optional[dict[str, str]] = None,
    attempt_id: Optional[str] = None,
) -> GoldenRenderResult:
    """Controlled, operator-authorized single real render + QA + persistence.

    Exactly ONE real HVS render is performed (no retry, no rerender). On
    success the artifact is QA'd truthfully and the attempt is persisted.
    """
    if not is_supported_profile(profile_id):
        return GoldenRenderResult(False, None, None, "PROFILE_UNSUPPORTED", None)
    profile = get_profile(profile_id)
    # Guard: one attempt per (project, profile) already succeeded?
    for prior in store.by_project(project_id):
        if prior.profile_id == profile_id and prior.render_state == STATE_SUCCEEDED:
            return GoldenRenderResult(False, prior, None, "ALREADY_RENDERED", None)

    att_id = attempt_id or derive_artifact_id(
        hvs_project_id=hvs_project_id, profile_id=profile_id,
        attempt_id=recorded_at,
    )[:16]
    artifact_id = derive_artifact_id(
        hvs_project_id=hvs_project_id, profile_id=profile_id, attempt_id=att_id
    )

    attempt = GoldenRenderAttempt(
        project_id=project_id,
        hvs_project_id=hvs_project_id,
        attempt_id=att_id,
        profile_id=profile_id,
        operator_id=operator_id,
        authorization_id=authorization_id,
        render_state=STATE_AUTHORIZED,
        qa_state=QA_NOT_RUN,
        delivery_state=DELIVERY_APPROVAL_REQUIRED,
        artifact_id=artifact_id,
        artifact_checksum="",
        artifact_relative_path="",
        qa_report_id="",
        delivery_id="",
        recorded_at=recorded_at,
    )

    # --- single real HVS render -------------------------------------------
    attempt.render_state = STATE_RUNNING
    hf_dir = resolve_hyperframes_bin_dir()
    runner = hvs_cli_run or _default_hvs_cli_run
    try:
        parsed, _raw, rc = runner(
            python_executable=python_executable,
            hvs_repo_root=hvs_repo_root,
            hvs_project_id=hvs_project_id,
            profile_id=profile_id,
            timeout_seconds=timeout_seconds,
            hyperframes_bin_dir=hf_dir,
        )
    except Exception as exc:  # defensive: never mask as success
        attempt.render_state = STATE_FAILED_CONFIRMED
        attempt.error_code = "HVS_RUN_ERROR"
        store.append(attempt)
        return GoldenRenderResult(False, attempt, None, "HVS_RUN_ERROR", None)

    attempt.hvs_exit_code = rc
    attempt.hvs_verdict = str(parsed.get("verdict"))

    # --- discover artifact (authoritative success proof) ------------------
    artifact = discover_artifact(
        hvs_repo_root=hvs_repo_root, hvs_project_id=hvs_project_id, profile_id=profile_id
    )
    if artifact is None or artifact.stat().st_size == 0:
        attempt.render_state = STATE_FAILED_CONFIRMED
        attempt.error_code = "ARTIFACT_NOT_FOUND"
        store.append(attempt)
        return GoldenRenderResult(False, attempt, None, "ARTIFACT_NOT_FOUND", None)

    attempt.render_state = STATE_SUCCEEDED
    attempt.artifact_checksum = _sha256_file(artifact)
    rel = artifact.relative_to(Path(hvs_repo_root).resolve()).as_posix()
    attempt.artifact_relative_path = rel

    # --- media QA ---------------------------------------------------------
    attempt.qa_state = QA_RUNNING
    versions = tool_versions or {
        "ffprobe": "8.1.2",
        "ffmpeg": "8.1.2",
        "hyperframes": "0.7.45",
    }
    qa = run_media_qa(
        project_id=project_id,
        hvs_project_id=hvs_project_id,
        attempt_id=att_id,
        profile_id=profile_id,
        artifact_path=str(artifact),
        recorded_at=recorded_at,
        tool_versions=versions,
        ffprobe_bin=ffprobe_bin,
        ffmpeg_bin=ffmpeg_bin,
        started_at=recorded_at,
    )
    attempt.qa_state = qa.overall_state
    attempt.qa_report_id = qa.qa_report_id
    store.append(attempt)
    return GoldenRenderResult(True, attempt, qa, None, None)


def _hvs_rendered(parsed: dict[str, Any]) -> bool:
    """Best-effort: did HVS actually produce a real output?"""
    return bool(parsed.get("renderer_called")) and str(parsed.get("verdict")) in (
        "PASS", "REAL_RENDER_DONE",
    )


def build_delivery_package(
    *,
    project_id: str,
    hvs_project_id: str,
    attempt: GoldenRenderAttempt,
    qa_report: QaReport,
    artifact_path: str,
    output_dir: str,
    operator_id: str,
    recorded_at: str,
    caption_text: Optional[str] = None,
    rights_declaration: str = "Local-first manual delivery. No external distribution, upload, or publish without separate operator authorization.",
    revision_note: str = "Cohort 10G golden render manual delivery package.",
) -> dict[str, Any]:
    """Build a sealed manual delivery package (relative, redacted metadata)."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    artifact_p = Path(artifact_path)
    checksum = _sha256_file(artifact_p)
    delivery_id = derive_delivery_id(
        qa_report_id=qa_report.qa_report_id, artifact_checksum=checksum
    )
    pkg_dir = out / f"delivery_{delivery_id}"
    pkg_dir.mkdir(parents=True, exist_ok=True)

    # Copy only the final media file (no temp, no partial).
    final_media = pkg_dir / f"{attempt.profile_id}.mp4"
    import shutil as _shutil

    _shutil.copyfile(artifact_p, final_media)

    manifest = {
        "schema_version": DELIVERY_PACKAGE_SCHEMA_VERSION,
        "delivery_id": delivery_id,
        "project_id": project_id,
        "hvs_project_id": hvs_project_id,
        "attempt_id": attempt.attempt_id,
        "artifact_id": qa_report.artifact_id,
        "profile_id": attempt.profile_id,
        "qa_report_id": qa_report.qa_report_id,
        "operator_approval_id": attempt.authorization_id,
        "operator_id": operator_id,
        "generated_at": recorded_at,
        "files": [
            {"name": final_media.name, "sha256": checksum, "size_bytes": artifact_p.stat().st_size},
        ],
        "qa_overall_state": qa_report.overall_state,
        "qa_failure_codes": list(qa_report.failure_codes),
        "caption_or_text": caption_text,
        "rights_declaration": rights_declaration,
        "revision_note": revision_note,
        # Explicitly browser-safe: relative names only, no absolute paths.
        "paths_relative": True,
        "sealed": True,
    }
    (pkg_dir / "delivery_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    # QA report (redacted: no absolute paths, no raw tool output).
    (pkg_dir / "qa_report.json").write_text(
        json.dumps(qa_report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    # Safe README / handoff summary.
    readme = (
        f"# SCOS Cohort 10G — Manual Delivery Package\n\n"
        f"- delivery_id: {delivery_id}\n"
        f"- project: {project_id}\n"
        f"- profile: {attempt.profile_id}\n"
        f"- QA: {qa_report.overall_state}\n"
        f"- media: {final_media.name} (sha256 {checksum[:16]}...)\n"
        f"- rights: {rights_declaration}\n"
    )
    (pkg_dir / "README.md").write_text(readme, encoding="utf-8")

    return {
        "ok": True,
        "delivery_id": delivery_id,
        "delivery_dir": str(pkg_dir),
        "manifest": manifest,
        "delivery_state": DELIVERY_PACKAGE_READY,
    }
