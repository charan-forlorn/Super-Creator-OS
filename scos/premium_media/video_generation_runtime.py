"""Governed execution plane for SCOS AI-video provider adapters."""
from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import subprocess
import time
import urllib.parse
import urllib.request
import urllib.error
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from .qc import probe_media
from .telemetry import GenerationTelemetryEvent, JsonlTelemetrySink, now, observed_latency
from .video_generation import GenerationArtifact, GenerationPlan, GenerationTask, ProviderDecision, ReferenceAsset, ShotGenerationSpec


class VideoProviderError(RuntimeError):
    pass


class ProviderContractError(VideoProviderError):
    pass


@dataclass(frozen=True)
class ProviderSubmission:
    provider_task_id: str


@dataclass(frozen=True)
class ProviderPoll:
    state: str
    artifact_uri: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    raw: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class PackedReference:
    reference_id: str
    kind: str
    provider_uri: str
    local_path: str | None = None
    mime_type: str | None = None
    sha256: str | None = None


class JsonHttpClient:
    """Injectable JSON/byte transport used by real adapters and tests."""

    def __init__(self, request_impl: Callable | None = None) -> None:
        self._request_impl = request_impl or self._urllib_request

    @staticmethod
    def _urllib_request(method: str, url: str, headers: Mapping[str, str], body: bytes | None, timeout: float):
        req = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return int(r.status), dict(r.headers.items()), r.read()
        except urllib.error.HTTPError as exc:
            return int(exc.code), dict(exc.headers.items()), exc.read()
        except urllib.error.URLError as exc:
            raise VideoProviderError(f"HTTP transport failed: {exc}") from exc

    def raw(self, method: str, url: str, *, headers: Mapping[str, str] = (), body: bytes | None = None, timeout: float = 30) -> tuple[int, Mapping[str, str], bytes]:
        return self._request_impl(method, url, dict(headers), body, timeout)

    def json(self, method: str, url: str, *, headers: Mapping[str, str] = (), payload: Mapping[str, Any] | None = None, timeout: float = 30) -> Mapping[str, Any]:
        merged = {"accept": "application/json", **dict(headers)}
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
        if body is not None:
            merged.setdefault("content-type", "application/json")
        status, _, raw = self.raw(method, url, headers=merged, body=body, timeout=timeout)
        try:
            data = json.loads(raw.decode()) if raw else {}
        except json.JSONDecodeError as exc:
            raise VideoProviderError(f"invalid JSON from {url}") from exc
        if not 200 <= status < 300:
            raise VideoProviderError(f"{method} {url} HTTP {status}: {data}")
        if not isinstance(data, Mapping):
            raise VideoProviderError(f"unexpected JSON shape from {url}")
        return data

    def download(self, url: str, destination: Path, *, headers: Mapping[str, str] = ()) -> Path:
        status, _, raw = self.raw("GET", url, headers=headers, timeout=300)
        if not 200 <= status < 300 or not raw:
            raise VideoProviderError(f"artifact download failed HTTP {status}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp = destination.with_name("." + destination.name + "." + uuid.uuid4().hex + ".tmp")
        temp.write_bytes(raw)
        temp.replace(destination)
        return destination


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _stable_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _local_path(uri: str) -> Path | None:
    candidate = Path(uri)
    if candidate.exists():
        return candidate
    parsed = urllib.parse.urlparse(uri)
    if parsed.scheme == "file":
        return Path(urllib.request.url2pathname(parsed.path))
    return None


class ReferencePackager:
    def __init__(self, *, max_inline_bytes: int = 10 * 1024 * 1024) -> None:
        self.max_inline_bytes = max_inline_bytes

    def package(self, provider_id: str, ref: ReferenceAsset) -> PackedReference:
        local = _local_path(ref.uri)
        if local is None:
            if provider_id == "google_veo" and not ref.uri.startswith("data:"):
                raise ProviderContractError("Veo requires a local/inline reference in this adapter")
            return PackedReference(ref.reference_id, ref.kind, ref.uri, sha256=ref.sha256)
        if not local.is_file() or local.stat().st_size <= 0:
            raise ProviderContractError(f"reference missing/empty: {local}")
        actual = _sha256_file(local)
        if actual != ref.sha256:
            raise ProviderContractError(f"reference sha256 mismatch for {ref.reference_id}")
        mime = mimetypes.guess_type(local.name)[0] or "application/octet-stream"
        if mime.startswith("video/") and provider_id in {"google_veo", "bytedance_seedance", "runway"}:
            raise ProviderContractError(
                f"{provider_id} local video references require a provider upload/remote-URI adapter"
            )
        if provider_id == "google_veo" and not mime.startswith("image/"):
            raise ProviderContractError("google_veo local references in this adapter must be images")
        if provider_id in {"google_veo", "bytedance_seedance"} and mime.startswith(("image/", "audio/")):
            if local.stat().st_size > self.max_inline_bytes:
                raise ProviderContractError(f"reference too large for inline packaging: {ref.reference_id}")
            payload = base64.b64encode(local.read_bytes()).decode("ascii")
            return PackedReference(ref.reference_id, ref.kind, f"data:{mime};base64,{payload}", str(local), mime, actual)
        return PackedReference(ref.reference_id, ref.kind, ref.uri, str(local), mime, actual)


class VideoProviderAdapter(Protocol):
    provider_id: str
    model_id: str
    def available(self) -> bool: ...
    def validate_spec(self, spec: ShotGenerationSpec) -> tuple[str, ...]: ...
    def submit(self, spec: ShotGenerationSpec, *, prompt: str, packed_references: tuple[PackedReference, ...], idempotency_key: str) -> ProviderSubmission: ...
    def poll(self, provider_task_id: str) -> ProviderPoll: ...
    def download(self, artifact_uri: str, destination: Path) -> Path: ...


class BaseHttpVideoAdapter:
    provider_id: str
    model_id: str
    api_env_var: str

    def __init__(self, *, client: JsonHttpClient | None = None) -> None:
        self.http = client or JsonHttpClient()

    def available(self) -> bool:
        return bool(os.environ.get(self.api_env_var, "").strip())

    def key(self) -> str:
        value = os.environ.get(self.api_env_var, "").strip()
        if not value:
            raise ProviderContractError(f"{self.provider_id}: missing {self.api_env_var}")
        return value


class GoogleVeoAdapter(BaseHttpVideoAdapter):
    provider_id = "google_veo"
    model_id = "veo-3.1-generate-preview"
    api_env_var = "GEMINI_API_KEY"
    base_url = "https://generativelanguage.googleapis.com/v1beta"

    def validate_spec(self, spec: ShotGenerationSpec) -> tuple[str, ...]:
        duration = round(spec.end_s - spec.start_s)
        errors = []
        if duration not in {4, 6, 8}:
            errors.append("Veo duration must be 4/6/8 seconds")
        if spec.references and duration != 8:
            errors.append("Veo reference-image generation requires 8 seconds")
        if spec.aspect_ratio not in {"9:16", "16:9"}:
            errors.append("Veo aspect ratio must be 9:16 or 16:9")
        if sum(r.kind in {"character", "style"} for r in spec.references) > 3:
            errors.append("Veo supports at most 3 reference images in this adapter")
        return tuple(errors)

    @staticmethod
    def _inline(ref: PackedReference) -> dict[str, Any]:
        if not ref.provider_uri.startswith("data:"):
            raise ProviderContractError(f"Veo ref {ref.reference_id} is not inline")
        return {"inlineData": {"mimeType": ref.mime_type or "image/png", "data": ref.provider_uri.split(",", 1)[-1]}}

    def submit(self, spec: ShotGenerationSpec, *, prompt: str, packed_references: tuple[PackedReference, ...], idempotency_key: str) -> ProviderSubmission:
        errors = self.validate_spec(spec)
        if errors:
            raise ProviderContractError("; ".join(errors))
        first = next((r for r in packed_references if r.kind in {"first_frame", "scene"}), None)
        last = next((r for r in packed_references if r.kind == "last_frame"), None)
        instance: dict[str, Any] = {"prompt": prompt}
        if first:
            instance["image"] = self._inline(first)
        if last:
            instance["lastFrame"] = self._inline(last)
        refs = [{"image": self._inline(r), "referenceType": "asset"} for r in packed_references if r.kind in {"character", "style"}]
        params: dict[str, Any] = {"aspectRatio": spec.aspect_ratio, "durationSeconds": str(round(spec.end_s - spec.start_s))}
        if refs:
            params["referenceImages"] = refs
        data = self.http.json("POST", f"{self.base_url}/models/{self.model_id}:predictLongRunning", headers={"x-goog-api-key": self.key(), "x-scoss-idempotency-key": idempotency_key}, payload={"instances": [instance], "parameters": params})
        op = str(data.get("name", "")).strip()
        if not op:
            raise VideoProviderError("Veo did not return an operation name")
        return ProviderSubmission(op)

    def poll(self, provider_task_id: str) -> ProviderPoll:
        data = self.http.json("GET", f"{self.base_url}/{provider_task_id.lstrip('/')}", headers={"x-goog-api-key": self.key()})
        if not data.get("done"):
            return ProviderPoll("running", raw=data)
        if data.get("error"):
            e = data["error"]
            return ProviderPoll("failed", error_code=str(e.get("status", "provider_error")), error_message=str(e), raw=data)
        generated = data.get("response", {}).get("generateVideoResponse", {}).get("generatedSamples", []) or data.get("response", {}).get("generatedVideos", [])
        if not generated:
            return ProviderPoll("failed", error_code="empty_output", error_message="Veo returned no video", raw=data)
        uri = generated[0].get("video", {}).get("uri") or generated[0].get("video", {}).get("url")
        if not uri:
            return ProviderPoll("failed", error_code="missing_output_uri", error_message="Veo returned no video URI", raw=data)
        return ProviderPoll("succeeded", artifact_uri=str(uri), raw=data)

    def download(self, artifact_uri: str, destination: Path) -> Path:
        return self.http.download(artifact_uri, destination, headers={"x-goog-api-key": self.key()})


class SeedanceAdapter(BaseHttpVideoAdapter):
    provider_id = "bytedance_seedance"
    model_id = "dreamina-seedance-2-0-260128"
    api_env_var = "LAS_API_KEY"
    base_url = "https://operator.las.ap-southeast-1.bytepluses.com/api/v1/contents/generations/tasks"

    def validate_spec(self, spec: ShotGenerationSpec) -> tuple[str, ...]:
        seconds = spec.end_s - spec.start_s
        errors = []
        if not 4 <= seconds <= 15:
            errors.append("Seedance 2.0 duration must be 4-15 seconds")
        if spec.aspect_ratio not in {"9:16", "16:9", "1:1", "4:3"}:
            errors.append(f"unsupported Seedance ratio {spec.aspect_ratio}")
        if spec.mode not in {"text_to_video", "image_to_video", "video_to_video", "first_last_frame", "modify"}:
            errors.append(f"unsupported Seedance mode {spec.mode}")
        return tuple(errors)

    def submit(self, spec: ShotGenerationSpec, *, prompt: str, packed_references: tuple[PackedReference, ...], idempotency_key: str) -> ProviderSubmission:
        errors = self.validate_spec(spec)
        if errors:
            raise ProviderContractError("; ".join(errors))
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for ref in packed_references:
            if ref.kind == "audio":
                content.append({"type": "audio_url", "audio_url": {"url": ref.provider_uri}, "role": "reference_audio"})
            elif ref.kind == "video":
                if ref.provider_uri.startswith("data:"):
                    raise ProviderContractError("Seedance cannot accept local video base64")
                content.append({"type": "video_url", "video_url": {"url": ref.provider_uri}, "role": "reference_video"})
            else:
                item: dict[str, Any] = {"type": "image_url", "image_url": {"url": ref.provider_uri}}
                if ref.kind in {"character", "style", "scene"}:
                    item["role"] = "reference_image"
                elif ref.kind in {"first_frame", "last_frame"}:
                    item["role"] = ref.kind
                content.append(item)
        data = self.http.json("POST", self.base_url, headers={"authorization": f"Bearer {self.key()}", "x-scoss-idempotency-key": idempotency_key}, payload={"model": self.model_id, "content": content, "generate_audio": bool(spec.native_audio), "ratio": spec.aspect_ratio, "duration": int(round(spec.end_s - spec.start_s)), "watermark": False})
        task_id = str(data.get("id", "")).strip()
        if not task_id:
            raise VideoProviderError("Seedance did not return task id")
        return ProviderSubmission(task_id)

    def poll(self, provider_task_id: str) -> ProviderPoll:
        data = self.http.json("GET", f"{self.base_url}/{urllib.parse.quote(provider_task_id, safe='')}", headers={"authorization": f"Bearer {self.key()}"})
        status = str(data.get("status", "")).lower()
        if status in {"queued", "running"}:
            return ProviderPoll("running", raw=data)
        if status in {"failed", "cancelled", "expired"}:
            e = data.get("error") or {}
            return ProviderPoll("failed", error_code=str(e.get("code", status)), error_message=str(e.get("message", data.get("error") or status)), raw=data)
        if status == "succeeded":
            uri = (data.get("content") or {}).get("video_url")
            if not uri:
                return ProviderPoll("failed", error_code="missing_output_uri", error_message="Seedance returned no video URL", raw=data)
            return ProviderPoll("succeeded", artifact_uri=str(uri), raw=data)
        return ProviderPoll("failed", error_code="unknown_status", error_message=f"Seedance status {status}", raw=data)

    def download(self, artifact_uri: str, destination: Path) -> Path:
        return self.http.download(artifact_uri, destination)


class RunwayGen45Adapter(BaseHttpVideoAdapter):
    provider_id = "runway"
    model_id = "gen4.5"
    api_env_var = "RUNWAYML_API_SECRET"
    base_url = "https://api.dev.runwayml.com/v1"
    api_version = "2024-11-06"

    def validate_spec(self, spec: ShotGenerationSpec) -> tuple[str, ...]:
        seconds = spec.end_s - spec.start_s
        errors = []
        if not 2 <= seconds <= 10:
            errors.append("Runway Gen-4.5 duration must be 2-10 seconds")
        if spec.aspect_ratio not in {"16:9", "9:16"}:
            errors.append("Runway Gen-4.5 ratio must be 16:9 or 9:16")
        if spec.mode not in {"text_to_video", "image_to_video"}:
            errors.append("Runway adapter currently supports text/image-to-video")
        for r in spec.references:
            if r.kind == "video":
                errors.append("Runway video references require a provider upload adapter")
        return tuple(errors)

    def submit(self, spec: ShotGenerationSpec, *, prompt: str, packed_references: tuple[PackedReference, ...], idempotency_key: str) -> ProviderSubmission:
        errors = self.validate_spec(spec)
        if errors:
            raise ProviderContractError("; ".join(errors))
        image = next((r for r in packed_references if r.kind in {"scene", "first_frame"}), None)
        if image and image.local_path and not image.provider_uri.startswith(("http://", "https://", "runway://")):
            raise ProviderContractError("Runway local references require an upload-enabled adapter path; refusing implicit unsafe upload")
        ratio = {"16:9": "1280:768", "9:16": "768:1280"}[spec.aspect_ratio]
        payload: dict[str, Any] = {"model": self.model_id, "promptText": prompt, "ratio": ratio, "duration": int(round(spec.end_s - spec.start_s))}
        if image:
            payload["promptImage"] = image.provider_uri
        data = self.http.json("POST", f"{self.base_url}/image_to_video", headers={"authorization": f"Bearer {self.key()}", "x-runway-version": self.api_version, "x-scoss-idempotency-key": idempotency_key}, payload=payload)
        task_id = str(data.get("id", "")).strip()
        if not task_id:
            raise VideoProviderError("Runway did not return task id")
        return ProviderSubmission(task_id)

    def poll(self, provider_task_id: str) -> ProviderPoll:
        data = self.http.json("GET", f"{self.base_url}/tasks/{urllib.parse.quote(provider_task_id, safe='')}", headers={"authorization": f"Bearer {self.key()}", "x-runway-version": self.api_version})
        status = str(data.get("status", "")).upper()
        if status in {"PENDING", "THROTTLED", "RUNNING"}:
            return ProviderPoll("running", raw=data)
        if status in {"FAILED", "CANCELED"}:
            return ProviderPoll("failed", error_code=status.lower(), error_message=str(data.get("failure") or data.get("error") or status), raw=data)
        if status == "SUCCEEDED":
            output = data.get("output") or []
            return ProviderPoll("succeeded", artifact_uri=str(output[0]), raw=data) if output else ProviderPoll("failed", error_code="missing_output_uri", error_message="Runway returned no output", raw=data)
        return ProviderPoll("failed", error_code="unknown_status", error_message=f"Runway status {status}", raw=data)

    def download(self, artifact_uri: str, destination: Path) -> Path:
        return self.http.download(artifact_uri, destination)


class ProviderAdapterRegistry:
    def __init__(self, adapters: tuple[VideoProviderAdapter, ...]) -> None:
        self._adapters = {a.provider_id: a for a in adapters}
        if len(self._adapters) != len(adapters):
            raise ValueError("duplicate provider adapter")

    def get(self, provider_id: str) -> VideoProviderAdapter:
        return self._adapters[provider_id]

    def configured(self) -> tuple[str, ...]:
        return tuple(sorted(pid for pid, a in self._adapters.items() if a.available()))

    def resolve(self, spec: ShotGenerationSpec, decision: ProviderDecision) -> tuple[VideoProviderAdapter, str]:
        reasons: list[str] = []
        for pid in (decision.selected_provider_id, *decision.fallback_provider_ids):
            adapter = self._adapters.get(pid)
            if adapter is None:
                reasons.append(pid + ":adapter_missing")
                continue
            if not adapter.available():
                reasons.append(pid + ":not_configured")
                continue
            errors = adapter.validate_spec(spec)
            if errors:
                reasons.append(pid + ":" + "|".join(errors))
                continue
            return adapter, pid
        raise ProviderContractError(f"no executable provider for {spec.shot_id}: {'; '.join(reasons)}")


@dataclass(frozen=True)
class ContinuityReport:
    passed: bool
    metric: float | None
    threshold: float
    reason: str


def _frame_bytes(path: Path, *, last: bool) -> bytes:
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
    if last:
        args += ["-sseof", "-0.20"]
    args += ["-i", str(path), "-frames:v", "1", "-vf", "scale=32:32,format=gray", "-f", "rawvideo", "pipe:1"]
    proc = subprocess.run(args, capture_output=True, timeout=60)
    if proc.returncode != 0 or not proc.stdout:
        raise VideoProviderError(proc.stderr.decode("utf-8", "replace")[-1000:])
    return proc.stdout


def continuity_check(previous: Path, current: Path, *, threshold: float = 0.35) -> ContinuityReport:
    try:
        a, b = _frame_bytes(previous, last=True), _frame_bytes(current, last=False)
    except Exception as exc:
        return ContinuityReport(False, None, threshold, f"boundary sampling failed: {exc}")
    if len(a) != len(b) or not a:
        return ContinuityReport(False, None, threshold, "boundary sample size mismatch")
    mse = sum((x - y) * (x - y) for x, y in zip(a, b)) / (len(a) * 255.0 * 255.0)
    score = 1.0 - min(1.0, mse)
    return ContinuityReport(score >= threshold, score, threshold, "pixel-boundary similarity proxy")



def stage_generated_clips(
    manifest_path: Path,
    remotion_public_dir: Path,
    *,
    subdir: str = "generated-clips",
) -> tuple[dict[str, Any], ...]:
    """Copy sealed generated clips into Remotion public/ with hash-addressed names."""
    if not manifest_path.is_file():
        raise ProviderContractError(f"generated clip manifest missing: {manifest_path}")
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != "SCOS_GENERATED_CLIP_MANIFEST_R1":
        raise ProviderContractError("unsupported generated clip manifest schema")
    destination_root = remotion_public_dir / subdir
    destination_root.mkdir(parents=True, exist_ok=True)
    staged: list[dict[str, Any]] = []
    for entry in raw.get("shots", []):
        artifact = entry.get("artifact") or {}
        source = Path(str(artifact.get("uri", "")))
        expected_sha = str(artifact.get("sha256", ""))
        if not source.is_file() or source.stat().st_size <= 0:
            raise ProviderContractError(f"generated artifact missing: {source}")
        actual_sha = _sha256_file(source)
        if actual_sha != expected_sha:
            raise ProviderContractError(f"generated artifact sha256 mismatch: {source}")
        target_name = f"{entry['shot_id']}-{expected_sha[:16]}.mp4"
        target = destination_root / target_name
        if not target.exists() or _sha256_file(target) != expected_sha:
            temp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
            temp.write_bytes(source.read_bytes())
            if _sha256_file(temp) != expected_sha:
                temp.unlink(missing_ok=True)
                raise ProviderContractError(f"staged generated artifact hash mismatch: {target}")
            temp.replace(target)
        staged.append({
            "shot_id": entry["shot_id"],
            "src": f"{subdir}/{target_name}",
            "sha256": expected_sha,
            "provider_id": entry.get("provider_id"),
            "model_id": entry.get("model_id"),
            "task_id": entry.get("task_id"),
            "duration_s": artifact.get("duration_s"),
            "width": artifact.get("width"),
            "height": artifact.get("height"),
            "continuity_keys": entry.get("continuity_keys", []),
        })
    return tuple(staged)


def write_generation_clip_manifest(
    plan: GenerationPlan,
    tasks: tuple[GenerationTask, ...],
    path: Path,
) -> Path:
    """Seal succeeded generated clips into the renderer-facing visual manifest."""
    errors = plan.validate()
    if errors:
        raise ProviderContractError("; ".join(errors))
    by_shot = {task.shot_id: task for task in tasks}
    entries = []
    for spec in plan.shots:
        task = by_shot.get(spec.shot_id)
        if task is None:
            raise ProviderContractError(f"missing generation task for {spec.shot_id}")
        if task.state != "succeeded" or task.artifact is None:
            raise ProviderContractError(
                f"generation manifest requires succeeded task with artifact: {spec.shot_id}"
            )
        entries.append({
            "shot_id": spec.shot_id,
            "purpose": spec.purpose,
            "start_s": spec.start_s,
            "end_s": spec.end_s,
            "provider_id": task.provider_id,
            "model_id": task.model_id,
            "task_id": task.task_id,
            "artifact": task.artifact.__dict__,
            "continuity_keys": list(spec.continuity_keys),
        })
    payload = {
        "schema_version": "SCOS_GENERATED_CLIP_MANIFEST_R1",
        "project_id": plan.project_id,
        "objective": plan.objective,
        "plan_fingerprint": plan.fingerprint(),
        "shots": entries,
        "human_publish_gate": "NOT_APPROVED",
        "external_publish": "NOT_PERFORMED",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


@dataclass(frozen=True)
class JournalRow:
    task: GenerationTask
    idempotency_key: str
    spec_fingerprint: str
    selected_provider_id: str
    selected_model_id: str
    output_path: str
    continuity_keys: tuple[str, ...] = ()
    continuity_report: ContinuityReport | None = None
    evidence_sha256: str | None = None
    submitted_at: float | None = None
    completed_at: float | None = None

    def to_json(self) -> dict[str, Any]:
        data = {
            "task": self.task.to_props(),
            "idempotency_key": self.idempotency_key,
            "spec_fingerprint": self.spec_fingerprint,
            "selected_provider_id": self.selected_provider_id,
            "selected_model_id": self.selected_model_id,
            "output_path": self.output_path,
            "continuity_keys": list(self.continuity_keys),
            "evidence_sha256": self.evidence_sha256,
            "submitted_at": self.submitted_at,
            "completed_at": self.completed_at,
        }
        if self.continuity_report:
            data["continuity_report"] = self.continuity_report.__dict__
        return data


class TaskJournal:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, task_id: str) -> Path:
        return self.root / "tasks" / f"{task_id}.json"

    def write(self, row: JournalRow) -> None:
        path = self._path(row.task.task_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".tmp")
        tmp.write_text(json.dumps(row.to_json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)

    def read_all(self) -> tuple[JournalRow, ...]:
        directory = self.root / "tasks"
        if not directory.exists():
            return ()
        rows = []
        for path in sorted(directory.glob("*.json")):
            raw = json.loads(path.read_text(encoding="utf-8"))
            tr = raw["task"]
            artifact = GenerationArtifact(**tr["artifact"]) if tr.get("artifact") else None
            task = GenerationTask(task_id=tr["task_id"], shot_id=tr["shot_id"], provider_id=tr["provider_id"], model_id=tr["model_id"], state=tr["state"], attempt=int(tr.get("attempt", 0)), provider_task_id=tr.get("provider_task_id"), error_code=tr.get("error_code"), error_message=tr.get("error_message"), artifact=artifact)
            cr = raw.get("continuity_report")
            continuity = ContinuityReport(bool(cr["passed"]), cr.get("metric"), float(cr["threshold"]), str(cr["reason"])) if cr else None
            rows.append(JournalRow(task, str(raw["idempotency_key"]), str(raw["spec_fingerprint"]), str(raw["selected_provider_id"]), str(raw["selected_model_id"]), str(raw["output_path"]), tuple(raw.get("continuity_keys", ())), continuity, raw.get("evidence_sha256")))
        return tuple(rows)


class VideoGenerationOrchestrator:
    def __init__(self, *, adapters: ProviderAdapterRegistry, journal: TaskJournal, packager: ReferencePackager | None = None, telemetry_sink: JsonlTelemetrySink | None = None) -> None:
        self.adapters, self.journal, self.packager = adapters, journal, packager or ReferencePackager()
        self.telemetry_sink = telemetry_sink

    @staticmethod
    def _idempotency_key(plan: GenerationPlan, spec: ShotGenerationSpec, provider_id: str, attempt: int) -> str:
        return _stable_hash({"plan": plan.fingerprint(), "shot": spec.shot_id, "provider": provider_id, "attempt": attempt, "prompt": spec.prompt})

    @staticmethod
    def _prompt(objective: str, spec: ShotGenerationSpec) -> str:
        from .video_generation import compile_director_prompt
        return compile_director_prompt(objective, spec)

    def submit_plan(self, plan: GenerationPlan, *, output_dir: Path) -> tuple[GenerationTask, ...]:
        errors = plan.validate()
        if errors:
            raise ProviderContractError("; ".join(errors))
        output_dir.mkdir(parents=True, exist_ok=True)
        existing = {r.task.shot_id: r for r in self.journal.read_all()}
        decisions = {d.shot_id: d for d in plan.decisions}
        tasks = []
        for spec in plan.shots:
            prior = existing.get(spec.shot_id)
            if prior and prior.task.state in {"submitted", "running", "succeeded"}:
                tasks.append(prior.task)
                continue
            adapter, provider_id = self.adapters.resolve(spec, decisions[spec.shot_id])
            attempt = 0 if prior is None else prior.task.attempt + 1
            task_id = prior.task.task_id if prior else f"{plan.project_id}-{spec.shot_id}-{uuid.uuid4().hex[:10]}"
            refs = tuple(self.packager.package(provider_id, r) for r in spec.references)
            key = self._idempotency_key(plan, spec, provider_id, attempt)
            sub = adapter.submit(spec, prompt=self._prompt(plan.objective, spec), packed_references=refs, idempotency_key=key)
            task = GenerationTask(task_id, spec.shot_id, provider_id, adapter.model_id, state="queued", attempt=attempt).transition("submitted", provider_task_id=sub.provider_task_id)
            output = output_dir / (f"{spec.shot_id}.attempt{attempt}.mp4" if attempt else f"{spec.shot_id}.mp4")
            submitted_at = now()
            row = JournalRow(
                task, key, _stable_hash(spec.to_props()), provider_id, adapter.model_id,
                str(output), spec.continuity_keys, submitted_at=submitted_at
            )
            if self.telemetry_sink:
                self.telemetry_sink.append(GenerationTelemetryEvent(
                    schema_version="SCOS_GENERATION_TELEMETRY_R1",
                    observed_at=submitted_at,
                    task_id=task.task_id,
                    shot_id=task.shot_id,
                    provider_id=task.provider_id,
                    model_id=task.model_id,
                    attempt=task.attempt,
                    state="submitted",
                ))
            self.journal.write(row)
            tasks.append(task)
        return tuple(tasks)

    @staticmethod
    def _seal(path: Path) -> GenerationArtifact:
        if not path.is_file() or path.stat().st_size <= 0:
            raise VideoProviderError(f"artifact missing/empty: {path}")
        width = height = None
        duration = None
        try:
            p = probe_media(path)
            width, height, duration = p.width, p.height, p.duration_s
        except Exception:
            pass
        return GenerationArtifact(str(path), _sha256_file(path), "video/mp4", width, height, duration)

    def _evidence(self, row: JournalRow, task: GenerationTask, artifact: GenerationArtifact, artifact_uri: str, output_dir: Path) -> str:
        payload = {"schemaVersion": "SCOS_VIDEO_GENERATION_EVIDENCE_R1", "taskId": task.task_id, "shotId": task.shot_id, "providerId": task.provider_id, "modelId": task.model_id, "providerTaskId": task.provider_task_id, "idempotencyKey": row.idempotency_key, "specFingerprint": row.spec_fingerprint, "artifactUri": artifact_uri, "artifact": artifact.__dict__, "continuityReport": row.continuity_report.__dict__ if row.continuity_report else None, "observedAt": time.time()}
        digest = _stable_hash(payload)
        payload["evidenceSha256"] = digest
        root = output_dir / "evidence"
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{task.task_id}.json"
        tmp = path.with_name("." + path.name + "." + uuid.uuid4().hex + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
        return digest

    def reconcile(self, *, output_dir: Path, continuity_threshold: float = 0.35) -> tuple[GenerationTask, ...]:
        rows = list(self.journal.read_all())
        prior: dict[str, Path] = {}
        for row in rows:
            if row.task.state == "succeeded" and row.task.artifact:
                path = Path(row.task.artifact.uri)
                if path.exists():
                    for key in row.continuity_keys:
                        prior[key] = path
        results = []
        for row in rows:
            if row.task.state not in {"submitted", "running"}:
                continue
            adapter = self.adapters.get(row.task.provider_id)
            poll = adapter.poll(row.task.provider_task_id or "")
            task = row.task
            if poll.state == "running":
                if task.state == "submitted":
                    task = task.transition("running")
                self.journal.write(replace(row, task=task))
                results.append(task)
                continue
            if poll.state == "failed":
                completed_at = now()
                task = task.transition("failed", error_code=poll.error_code or "provider_error", error_message=poll.error_message or "provider task failed")
                updated = replace(row, task=task, completed_at=completed_at)
                self.journal.write(updated)
                if self.telemetry_sink:
                    self.telemetry_sink.append(GenerationTelemetryEvent(
                        schema_version="SCOS_GENERATION_TELEMETRY_R1",
                        observed_at=completed_at,
                        task_id=task.task_id,
                        shot_id=task.shot_id,
                        provider_id=task.provider_id,
                        model_id=task.model_id,
                        attempt=task.attempt,
                        state="failed",
                        latency_s=observed_latency(row.submitted_at, completed_at),
                        qc_passed=False,
                        metadata={"error_code": task.error_code},
                    ))
                results.append(task)
                continue
            if poll.state != "succeeded" or not poll.artifact_uri:
                raise ProviderContractError(f"invalid poll result for {task.task_id}: {poll}")
            destination = Path(row.output_path)
            adapter.download(poll.artifact_uri, destination)
            artifact = self._seal(destination)
            continuity = None
            previous = next((prior[k] for k in row.continuity_keys if k in prior), None)
            if previous:
                continuity = continuity_check(previous, destination, threshold=continuity_threshold)
            if continuity and not continuity.passed:
                task = task.transition("failed", error_code="continuity_qc_failed", error_message=continuity.reason, artifact=artifact)
            else:
                task = task.transition("succeeded", artifact=artifact)
                for key in row.continuity_keys:
                    prior[key] = destination
            completed_at = now()
            updated = replace(row, task=task, continuity_report=continuity, completed_at=completed_at)
            evidence = self._evidence(updated, task, artifact, poll.artifact_uri, output_dir)
            final_row = replace(updated, evidence_sha256=evidence)
            self.journal.write(final_row)
            if self.telemetry_sink:
                self.telemetry_sink.append(GenerationTelemetryEvent(
                    schema_version="SCOS_GENERATION_TELEMETRY_R1",
                    observed_at=completed_at,
                    task_id=task.task_id,
                    shot_id=task.shot_id,
                    provider_id=task.provider_id,
                    model_id=task.model_id,
                    attempt=task.attempt,
                    state=task.state,
                    latency_s=observed_latency(row.submitted_at, completed_at),
                    qc_passed=(task.state == "succeeded"),
                    metadata={
                        "artifact_sha256": artifact.sha256,
                        "continuity_score": continuity.score if continuity else None,
                    },
                ))
            results.append(task)
        return tuple(results)

    def retry_failed(self, plan: GenerationPlan, *, output_dir: Path, max_attempts: int = 2) -> tuple[GenerationTask, ...]:
        specs = {s.shot_id: s for s in plan.shots}; decisions = {d.shot_id: d for d in plan.decisions}; result = []
        for row in self.journal.read_all():
            task = row.task
            if task.state != "failed" or task.attempt >= max_attempts:
                continue
            spec, decision = specs.get(task.shot_id), decisions.get(task.shot_id)
            if not spec or not decision:
                continue
            for provider_id in (decision.selected_provider_id, *decision.fallback_provider_ids):
                if provider_id == task.provider_id:
                    continue
                adapter = self.adapters._adapters.get(provider_id)
                if adapter and adapter.available() and not adapter.validate_spec(spec):
                    refs = tuple(self.packager.package(provider_id, r) for r in spec.references)
                    attempt = task.attempt + 1; key = self._idempotency_key(plan, spec, provider_id, attempt)
                    sub = adapter.submit(spec, prompt=self._prompt(plan.objective, spec), packed_references=refs, idempotency_key=key)
                    new_task = GenerationTask(task.task_id, task.shot_id, provider_id, adapter.model_id, state="queued", attempt=attempt).transition("submitted", provider_task_id=sub.provider_task_id)
                    output = output_dir / f"{spec.shot_id}.attempt{attempt}.mp4"
                    self.journal.write(replace(row, task=new_task, idempotency_key=key, selected_provider_id=provider_id, selected_model_id=adapter.model_id, output_path=str(output), continuity_report=None, evidence_sha256=None))
                    result.append(new_task)
                    break
        return tuple(result)


def default_provider_adapters() -> ProviderAdapterRegistry:
    return ProviderAdapterRegistry((GoogleVeoAdapter(), SeedanceAdapter(), RunwayGen45Adapter()))
