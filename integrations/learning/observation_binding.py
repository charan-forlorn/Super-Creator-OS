"""Render-to-platform observation binding.

Fail-closed bridge from a real SCOS premium render provenance artifact to
platform telemetry. It proves the artifact bytes still match their sealed SHA-256
and exposes the immutable causal identifiers used by telemetry evidence.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
import re

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class ObservationBindingError(ValueError):
    """Raised when render provenance cannot be trusted for telemetry binding."""


@dataclass(frozen=True)
class ObservationBinding:
    project_name: str
    loop_run_id: str
    graph_fingerprint: str
    artifact_sha256: str
    platform_content_id: str
    provenance_path: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ObservationBindingError(f"{field} must be a 64-character SHA-256 hex digest")
    return value.lower()


def load_render_binding(
    provenance_path: str | Path,
    *,
    platform_content_id: str,
    expected_loop_run_id: str | None = None,
) -> ObservationBinding:
    path = Path(provenance_path).resolve()
    if not path.is_file():
        raise ObservationBindingError(f"PROVENANCE_NOT_FOUND: {path}")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ObservationBindingError(f"PROVENANCE_UNREADABLE: {path}") from exc

    handoff = manifest.get("learning_handoff")
    if not isinstance(handoff, dict):
        raise ObservationBindingError("LEARNING_HANDOFF_MISSING")
    loop_run_id = handoff.get("loop_run_id")
    graph_fingerprint = handoff.get("graph_fingerprint")
    artifact_sha = _require_sha(handoff.get("artifact_sha256"), "learning_handoff.artifact_sha256")
    manifest_sha = _require_sha(manifest.get("output_sha256"), "output_sha256")
    if artifact_sha != manifest_sha:
        raise ObservationBindingError("ARTIFACT_SHA_MANIFEST_MISMATCH")
    if not isinstance(loop_run_id, str) or not loop_run_id:
        raise ObservationBindingError("LOOP_RUN_ID_MISSING")
    if expected_loop_run_id is not None and loop_run_id != expected_loop_run_id:
        raise ObservationBindingError("LOOP_RUN_ID_MISMATCH")
    if not isinstance(graph_fingerprint, str) or not _SHA256_RE.fullmatch(graph_fingerprint):
        raise ObservationBindingError("GRAPH_FINGERPRINT_INVALID")
    if not isinstance(platform_content_id, str) or not platform_content_id.strip():
        raise ObservationBindingError("PLATFORM_CONTENT_ID_REQUIRED")

    output_raw = manifest.get("output")
    if not isinstance(output_raw, str) or not output_raw:
        raise ObservationBindingError("OUTPUT_PATH_MISSING")
    output = Path(output_raw)
    if not output.is_file():
        raise ObservationBindingError(f"ARTIFACT_NOT_FOUND: {output}")
    actual_sha = _sha256(output)
    if actual_sha != artifact_sha:
        raise ObservationBindingError("ARTIFACT_SHA_BYTES_MISMATCH")

    return ObservationBinding(
        project_name=str(manifest.get("extra", {}).get("project_name") or output.stem),
        loop_run_id=loop_run_id,
        graph_fingerprint=graph_fingerprint.lower(),
        artifact_sha256=artifact_sha,
        platform_content_id=platform_content_id.strip(),
        provenance_path=str(path),
    )
