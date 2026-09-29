"""Local Wan VACE INT4 provider behind a process boundary."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

from scos.render.base import GeneratedShot, GenerativeBackend, RenderError, RenderProfile, ShotSpec

BACKEND_ID = "wan2.1-vace-1.3b-int4"
DEFAULT_MODEL = Path(r"C:\Workspace\models\Wan2.1-VACE-1.3B-int4")
DEFAULT_PYTHON = Path(r"C:\Workspace\super-creator-os\.venv-video-gen\Scripts\python.exe")
DEFAULT_WORKER = Path(r"C:\Workspace\super-creator-os\integrations\video_generation\wan_vace_worker.py")


def _stable_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _seed_for_shot(shot: ShotSpec, model_signature: str) -> int:
    payload = {
        "scene_id": shot.scene_id,
        "duration_s": round(shot.duration_s, 6),
        "visual": str(shot.visual_path.resolve()),
        "action": shot.action,
        "environment": shot.environment,
        "lighting": shot.lighting,
        "style": shot.style,
        "prompt": shot.prompt,
        "references": list(shot.references),
        "continuity_group": shot.continuity_group,
        "model": model_signature,
    }
    return int(hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()[:8], 16)

def _model_signature(root: Path) -> str:
    metadata = (
        "model_index.json",
        "transformer/config.json",
        "text_encoder/config.json",
        "vae/config.json",
        "tokenizer/tokenizer_config.json",
    )
    weights = (
        "text_encoder/model.safetensors",
        "transformer/diffusion_pytorch_model.safetensors",
        "vae/diffusion_pytorch_model.safetensors",
    )
    digest = hashlib.sha256()
    for rel in metadata:
        path = root / rel
        if not path.is_file():
            raise RenderError(f"generative model metadata missing: {path}")
        digest.update(rel.encode("utf-8"))
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    for rel in weights:
        path = root / rel
        if not path.is_file() or path.stat().st_size <= 0:
            raise RenderError(f"generative model weight missing: {path}")
        digest.update(rel.encode("utf-8"))
        digest.update(str(path.stat().st_size).encode("ascii"))
    return digest.hexdigest()


def _ffprobe(path: Path) -> dict[str, object]:
    if not path.is_file() or path.stat().st_size <= 0:
        raise RenderError(f"generated shot missing or empty: {path}")
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries",
            "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate",
            "-of", "json", str(path),
        ],
        capture_output=True, text=True, check=False, timeout=20,
    )
    if proc.returncode != 0:
        raise RenderError(f"ffprobe failed: {proc.stderr.strip()[-500:]}")
    data = json.loads(proc.stdout)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    return {
        "duration_s": float(data.get("format", {}).get("duration") or 0.0),
        "width": video.get("width"),
        "height": video.get("height"),
        "fps": video.get("r_frame_rate"),
        "video_codec": video.get("codec_name"),
    }

class WanVaceBackend(GenerativeBackend):
    @property
    def backend_id(self) -> str:
        return BACKEND_ID

    def __init__(
        self,
        *,
        model_dir: Path | None = None,
        python_executable: Path | None = None,
        worker_path: Path | None = None,
        height: int = 480,
        width: int = 832,
        fps: int = 16,
        steps: int = 6,
        guidance_scale: float = 4.0,
        max_duration_s: float = 2.25,
    ) -> None:
        self.model_dir = Path(os.getenv("SCOS_WAN_VACE_MODEL_DIR", model_dir or DEFAULT_MODEL))
        self.python_executable = Path(
            os.getenv("SCOS_VIDEO_GEN_PYTHON", python_executable or DEFAULT_PYTHON)
        )
        self.worker_path = Path(worker_path or DEFAULT_WORKER)
        self.height = int(os.getenv("SCOS_WAN_VACE_HEIGHT", height))
        self.width = int(os.getenv("SCOS_WAN_VACE_WIDTH", width))
        self.fps = int(os.getenv("SCOS_WAN_VACE_FPS", fps))
        self.steps = int(os.getenv("SCOS_WAN_VACE_STEPS", steps))
        self.guidance_scale = float(os.getenv("SCOS_WAN_VACE_GUIDANCE", guidance_scale))
        self.max_duration_s = float(os.getenv("SCOS_WAN_VACE_MAX_DURATION_S", max_duration_s))
        self.load_mode = os.getenv("SCOS_WAN_VACE_LOAD_MODE", "auto").lower()
        self.adaptive_resolution = os.getenv("SCOS_WAN_VACE_ADAPTIVE_RESOLUTION", "1").lower() not in {"0", "false", "off"}
        if self.load_mode not in {"auto", "cuda", "cpu_offload"}:
            raise RenderError("SCOS_WAN_VACE_LOAD_MODE must be auto, cuda, or cpu_offload")
        self._signature: str | None = None

    @property
    def model_signature(self) -> str:
        if self._signature is None:
            self._signature = _model_signature(self.model_dir)
        return self._signature

    def preflight(self) -> dict[str, object]:
        errors: list[str] = []
        if not self.python_executable.is_file():
            errors.append(f"python runtime missing: {self.python_executable}")
        if not self.worker_path.is_file():
            errors.append(f"worker missing: {self.worker_path}")
        try:
            signature = self.model_signature
        except RenderError as exc:
            errors.append(str(exc))
            signature = None
        return {
            "available": not errors,
            "errors": errors,
            "model_signature": signature,
        }

    def _reference_image(self, shot: ShotSpec) -> Path:
        candidates = [shot.visual_path]
        for value in shot.references:
            candidate = Path(value)
            if not candidate.is_absolute():
                candidate = self.model_dir.parent.parent / candidate
            candidates.append(candidate)
        for candidate in candidates:
            if candidate.is_file() and candidate.stat().st_size > 0:
                return candidate.resolve()
        raise RenderError(f"scene {shot.scene_id}: no usable reference image")

    def _frames_for_duration(self, duration_s: float) -> int:
        if duration_s > self.max_duration_s:
            raise RenderError(
                f"scene {duration_s:.3f}s exceeds {self.max_duration_s:.3f}s "
                "local-provider limit"
            )
        target = max(9, round(duration_s * self.fps))
        return max(9, 4 * round((target - 1) / 4) + 1)

    def generate(
        self,
        shot: ShotSpec,
        profile: RenderProfile,
        output_path: Path,
    ) -> GeneratedShot:
        check = self.preflight()
        if not check["available"]:
            raise RenderError("; ".join(str(v) for v in check["errors"]))
        if shot.start_frame is not None or shot.end_frame is not None:
            raise RenderError(
                f"scene {shot.scene_id}: start/end frames unsupported by {self.backend_id}"
            )

        reference = self._reference_image(shot)
        frames = self._frames_for_duration(shot.duration_s)
        seed = _seed_for_shot(shot, self.model_signature)
        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        gen_height, gen_width = self.height, self.width
        if profile.height > profile.width and gen_width > gen_height:
            gen_height, gen_width = gen_width, gen_height
        elif profile.width > profile.height and gen_height > gen_width:
            gen_height, gen_width = gen_width, gen_height

        job = {
            "scene_id": shot.scene_id,
            "model_dir": str(self.model_dir),
            "reference_image": str(reference),
            "prompt": shot.prompt or shot.action or shot.style or "cinematic product motion",
            "output_path": str(output_path),
            "height": gen_height,
            "width": gen_width,
            "fps": self.fps,
            "num_frames": frames,
            "num_inference_steps": self.steps,
            "guidance_scale": self.guidance_scale,
            "seed": seed,
            "load_mode": self.load_mode,
            "adaptive_resolution": self.adaptive_resolution,
        }

        job_file = output_path.with_suffix(".wan-job.json")
        job_file.write_text(
            json.dumps(job, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        try:
            proc = subprocess.run(
                [
                    str(self.python_executable),
                    str(self.worker_path),
                    "--job-file",
                    str(job_file),
                ],
                cwd=str(self.model_dir.parent.parent),
                capture_output=True,
                text=True,
                check=False,
                timeout=max(600, int(shot.duration_s * 600)),
            )
        finally:
            try:
                job_file.unlink()
            except FileNotFoundError:
                pass
        combined = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            raise RenderError(
                f"{self.backend_id} worker failed (exit {proc.returncode}): "
                f"{combined.strip()[-1200:]}"
            )
        lines = [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]
        if not lines:
            raise RenderError(f"{self.backend_id} worker returned no result")
        try:
            result = json.loads(lines[-1])
        except json.JSONDecodeError as exc:
            raise RenderError(
                f"{self.backend_id} worker returned invalid JSON: {lines[-1][-500:]}"
            ) from exc
        if result.get("status") != "PASS":
            raise RenderError(
                f"{self.backend_id} worker returned {result.get('status')}: "
                f"{result.get('error')}"
            )
        probe = _ffprobe(output_path)
        motion_score = result.get("motion_score")
        duration = float(probe["duration_s"])
        if duration + 0.05 < shot.duration_s:
            raise RenderError(
                f"generated duration {duration:.3f}s < target {shot.duration_s:.3f}s"
            )
        return GeneratedShot(
            scene_id=shot.scene_id,
            video_path=output_path,
            duration_s=duration,
            provider=self.backend_id,
            task_id=f"{self.backend_id}:{seed}",
            info=(
                f"seed={seed}; frames={frames}; motion_score={motion_score}; "
                f"load_mode={result.get('load_mode')}; peak_vram_mib={result.get('peak_vram_mib')}; "
                f"effective={result.get('effective_width')}x{result.get('effective_height')}; "
                f"adaptive_resolution={result.get('adaptive_resolution')}; "
                f"model={self.model_signature[:16]}; "
                f"probe={probe['width']}x{probe['height']}@{probe['fps']}"
            ),
        )


__all__ = ["BACKEND_ID", "WanVaceBackend"]
