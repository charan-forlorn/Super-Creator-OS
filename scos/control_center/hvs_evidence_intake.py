"""SCOS <-> Hermes Video Studio (HVS) — Stage 3 Render Evidence Intake.

Intake and decision stage only. SCOS ingests a REAL HVS Stage 6
render-validation evidence JSON file (produced by
``hvs.quality.stage6_export_validation.validate_export``), validates its
contract, derives a stable operator-facing decision packet, and explicitly
distinguishes:

* export technically ready
* export failed validation
* evidence invalid or incompatible
* evidence cannot be trusted

This module is the SCOS-owned bridge. It does NOT import any HVS
package, does NOT render video, does NOT export media, does NOT modify
HVS artifacts, does NOT call external services, and does NOT execute Git
actions. It reads ONE explicit caller-provided local JSON path only.

Trust model (deterministic, local facts only):
* VERIFIED  — schema supported, verdict PASS, evidence hash checks out,
              and artifact SHA-256 is verified against the evidence (when the
              artifact is locally readable).
* PARTIAL   — schema supported and contract-valid, but artifact integrity
              could not be fully verified (artifact missing/unreadable), so a
              reduced-trust state is reported precisely.
* UNVERIFIED — malformed / missing / incompatible / FAIL verdict / evidence
              hash mismatch. Never mapped to a ready result.

Operator actions (stable):
* review_export_ready          — export technically ready; operator reviews.
* review_render_failures       — HVS reported a FAIL verdict.
* repair_or_rerender_required  — verdict FAIL / integrity unverifiable.
* evidence_rejected           — evidence invalid / untrusted.

Local-first, deterministic, stdlib-only. No clock (``created_at`` is
caller-supplied), no random, no uuid, no network, no subprocess, no
HVS import.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# --- HVS Stage 6 evidence contract (read from the committed producer) -----
HVS_STAGE6_SCHEMA_VERSION = "hvs.quality.stage6/1.0.0"
SUPPORTED_SCHEMA_VERSIONS = (HVS_STAGE6_SCHEMA_VERSION,)

# --- SCOS decision-packet identity -------------------------------------------
SCOS_HVS_EVIDENCE_SCHEMA_VERSION = 1
SOURCE_NAME = "hermes_video_studio"

# --- Stable exit / error codes (machine-readable) ----------------------------
EVIDENCE_NOT_FOUND = "EVIDENCE_NOT_FOUND"
EVIDENCE_INVALID_JSON = "EVIDENCE_INVALID_JSON"
EVIDENCE_SCHEMA_UNSUPPORTED = "EVIDENCE_SCHEMA_UNSUPPORTED"
EVIDENCE_REQUIRED_FIELD_MISSING = "EVIDENCE_REQUIRED_FIELD_MISSING"
EVIDENCE_INTEGRITY_UNVERIFIABLE = "EVIDENCE_INTEGRITY_UNVERIFIABLE"
RENDER_VALIDATION_FAILED = "RENDER_VALIDATION_FAILED"
EXPORT_READY = "EXPORT_READY"

# --- Trust levels -----------------------------------------------------------
TRUST_VERIFIED = "VERIFIED"
TRUST_PARTIAL = "PARTIAL"
TRUST_UNVERIFIED = "UNVERIFIED"

# --- Operator actions --------------------------------------------------------
ACTION_REVIEW_EXPORT_READY = "review_export_ready"
ACTION_REVIEW_RENDER_FAILURES = "review_render_failures"
ACTION_REPAIR_OR_RERENDER = "repair_or_rerender_required"
ACTION_EVIDENCE_REJECTED = "evidence_rejected"

_MAX_HASH_DIGEST = 16


def _stable_id(*parts: Any) -> str:
    """Deterministic sha256-prefixed id from stable caller/evidence inputs.

    Mirrors ``HermesVideoStudioAdapter._stable_id`` and
    ``hvs_contract_models._sha256_hex16``. Volatile inputs (elapsed
    time, pid, random uuid, absolute temp paths) are NEVER passed.
    """
    text = "|".join(str(p) for p in parts)
    return "scos-hvs-evidence-" + hashlib.sha256(
        text.encode("utf-8")).hexdigest()[:_MAX_HASH_DIGEST]


def _sha256_file(path: str) -> str | None:
    """SHA-256 over the actual artifact bytes; None if unreadable."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


# --- Required contract fields (HVS Stage 6 producer, observed) ----------
_REQUIRED_TOP = (
    "schema_version",
    "validation_id",
    "verdict",
    "export_ready",
    "artifact",
    "checks",
)
_REQUIRED_ARTIFACT = ("path", "sha256")
_REQUIRED_CHECK = ("check_id", "status")


@dataclass(frozen=True)
class HVSEvidenceIntakeResult:
    """Deterministic SCOS decision packet for one HVS Stage 6 evidence file.

    When ``ok`` is False the packet is a rejection
    (``trust_level == UNVERIFIED``,
    ``operator_action == evidence_rejected``) and ``error_code`` is set.
    """

    ok: bool
    packet_id: str
    source: str
    schema_version: str | None
    validation_id: str | None
    project_id: str | None
    verdict: str | None
    export_ready: bool | None
    trust_level: str
    operator_action: str
    automation_allowed: bool
    evidence_path: str
    artifact_path: str | None
    artifact_sha256: str | None
    artifact_size_bytes: int | None
    failed_check_ids: tuple[str, ...]
    failed_reasons: tuple[str, ...]
    evidence_sha256: str | None
    evidence_sha256_verified: bool | None
    integrity_note: str | None
    unknown_hvs_fields: tuple[str, ...]
    error_code: str | None
    error_detail: str | None
    raw_evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": SCOS_HVS_EVIDENCE_SCHEMA_VERSION,
            "packet_id": self.packet_id,
            "source": self.source,
            "hvs": {
                "schema_version": self.schema_version,
                "validation_id": self.validation_id,
                "project_id": self.project_id,
                "verdict": self.verdict,
                "export_ready": self.export_ready,
                "evidence_sha256": self.evidence_sha256,
                "evidence_sha256_verified": self.evidence_sha256_verified,
            },
            "artifact": {
                "path": self.artifact_path,
                "sha256": self.artifact_sha256,
                "size_bytes": self.artifact_size_bytes,
            },
            "failed_check_ids": list(self.failed_check_ids),
            "failed_reasons": list(self.failed_reasons),
            "trust_level": self.trust_level,
            "operator_action": self.operator_action,
            "automation_allowed": self.automation_allowed,
            "integrity_note": self.integrity_note,
            "unknown_hvs_fields": list(self.unknown_hvs_fields),
            "evidence_path": self.evidence_path,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
        }


def _reject(
    *,
    evidence_path: str,
    error_code: str,
    error_detail: str,
    schema_version: str | None = None,
    validation_id: str | None = None,
    project_id: str | None = None,
    verdict: str | None = None,
    export_ready: bool | None = None,
    artifact_path: str | None = None,
    artifact_sha256: str | None = None,
    artifact_size_bytes: int | None = None,
    failed_check_ids: tuple[str, ...] = (),
    failed_reasons: tuple[str, ...] = (),
    evidence_sha256: str | None = None,
    integrity_note: str | None = None,
    unknown_hvs_fields: tuple[str, ...] = (),
    raw_evidence: dict[str, Any] | None = None,
) -> HVSEvidenceIntakeResult:
    pid = _stable_id(
        "reject", evidence_path, error_code,
        validation_id or "", schema_version or "")
    return HVSEvidenceIntakeResult(
        ok=False,
        packet_id=pid,
        source=SOURCE_NAME,
        schema_version=schema_version,
        validation_id=validation_id,
        project_id=project_id,
        verdict=verdict,
        export_ready=export_ready,
        trust_level=TRUST_UNVERIFIED,
        operator_action=ACTION_EVIDENCE_REJECTED,
        automation_allowed=False,
        evidence_path=evidence_path,
        artifact_path=artifact_path,
        artifact_sha256=artifact_sha256,
        artifact_size_bytes=artifact_size_bytes,
        failed_check_ids=tuple(failed_check_ids),
        failed_reasons=tuple(failed_reasons),
        evidence_sha256=evidence_sha256,
        evidence_sha256_verified=None,
        integrity_note=integrity_note,
        unknown_hvs_fields=tuple(unknown_hvs_fields),
        error_code=error_code,
        error_detail=error_detail,
        raw_evidence=raw_evidence or {},
    )


def _preserve_unknown(evidence: dict[str, Any]) -> tuple[str, ...]:
    """Return HVS top-level keys SCOS does not depend on (forward-compat)."""
    known = frozenset(_REQUIRED_TOP) | frozenset({
        "expected_contract", "inspected", "failure_codes",
        "created_at", "evidence_path", "evidence_written",
        "evidence_already_exists",
    })
    return tuple(sorted(k for k in evidence.keys() if k not in known))


def intake_hvs_render_evidence(
    *,
    evidence_path: str,
    verify_artifact: bool = True,
) -> HVSEvidenceIntakeResult:
    """Ingest and decide on one HVS Stage 6 evidence file.

    Reads the JSON at ``evidence_path`` only. Never writes, never shells
    out, never touches HVS. Returns a deterministic decision packet.

    ``verify_artifact`` controls whether artifact SHA-256 is re-checked
    against the live file. When False (or the artifact is unreadable), the
    packet degrades to PARTIAL trust and reports the precise reduced state
    rather than falsely claiming VERIFIED.
    """
    path = Path(evidence_path)
    if not path.exists() or not path.is_file():
        return _reject(
            evidence_path=evidence_path,
            error_code=EVIDENCE_NOT_FOUND,
            error_detail="evidence file does not exist or is not a file",
        )

    try:
        raw = path.read_text(encoding="utf-8")
        evidence = json.loads(raw)
    except (OSError, ValueError) as exc:
        return _reject(
            evidence_path=evidence_path,
            error_code=EVIDENCE_INVALID_JSON,
            error_detail=f"evidence could not be read or parsed: "
                       f"{type(exc).__name__}",
        )

    if not isinstance(evidence, dict):
        return _reject(
            evidence_path=evidence_path,
            error_code=EVIDENCE_INVALID_JSON,
            error_detail="evidence root must be a JSON object",
        )

    # --- schema version ----------------------------------------------------
    schema_version = evidence.get("schema_version")
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        return _reject(
            evidence_path=evidence_path,
            error_code=EVIDENCE_SCHEMA_UNSUPPORTED,
            error_detail=f"supported schema versions "
                       f"{SUPPORTED_SCHEMA_VERSIONS}, got "
                       f"{schema_version!r}",
            schema_version=schema_version,
            validation_id=evidence.get("validation_id"),
            project_id=evidence.get("project_id"),
            raw_evidence=evidence,
        )

    # --- required identity / verdict / checklist / artifact hash ----------
    missing = [k for k in _REQUIRED_TOP if k not in evidence]
    if missing:
        return _reject(
            evidence_path=evidence_path,
            error_code=EVIDENCE_REQUIRED_FIELD_MISSING,
            error_detail=f"missing required evidence field(s): {missing}",
            schema_version=schema_version,
            validation_id=evidence.get("validation_id"),
            project_id=evidence.get("project_id"),
            raw_evidence=evidence,
        )

    artifact = evidence.get("artifact")
    if not isinstance(artifact, dict) or any(
        k not in artifact for k in _REQUIRED_ARTIFACT
    ):
        return _reject(
            evidence_path=evidence_path,
            error_code=EVIDENCE_REQUIRED_FIELD_MISSING,
            error_detail="artifact block missing required field(s): "
                       f"{_REQUIRED_ARTIFACT}",
            schema_version=schema_version,
            validation_id=evidence.get("validation_id"),
            project_id=evidence.get("project_id"),
            raw_evidence=evidence,
        )

    checks = evidence.get("checks")
    if not isinstance(checks, list) or not checks:
        return _reject(
            evidence_path=evidence_path,
            error_code=EVIDENCE_REQUIRED_FIELD_MISSING,
            error_detail="checks must be a non-empty list",
            schema_version=schema_version,
            validation_id=evidence.get("validation_id"),
            project_id=evidence.get("project_id"),
            raw_evidence=evidence,
        )
    for c in checks:
        if not isinstance(c, dict) or any(
            k not in c for k in _REQUIRED_CHECK
        ):
            return _reject(
                evidence_path=evidence_path,
                error_code=EVIDENCE_REQUIRED_FIELD_MISSING,
                error_detail="each check must carry "
                           f"{_REQUIRED_CHECK}",
                schema_version=schema_version,
                validation_id=evidence.get("validation_id"),
                project_id=evidence.get("project_id"),
                raw_evidence=evidence,
            )

    # --- verdict / export_ready are trustworthy only if HVS said so -----
    verdict = evidence.get("verdict")
    export_ready = bool(evidence.get("export_ready"))
    validation_id = evidence.get("validation_id")
    project_id = evidence.get("project_id")
    artifact_path = artifact.get("path")
    artifact_sha = artifact.get("sha256")
    artifact_size = artifact.get("size_bytes")
    evidence_sha = evidence.get("evidence_sha256")

    failed_ids = tuple(
        c.get("check_id") for c in checks if c.get("status") == "FAIL")
    failed_reasons = tuple(
        c.get("reason") or "" for c in checks
        if c.get("status") == "FAIL")

    unknown = _preserve_unknown(evidence)

    # --- evidence tamper-hash check (local, deterministic) --------------
    evidence_hash_verified: bool | None = None
    if evidence_sha:
        canonical = {
            k: v for k, v in evidence.items()
            if k not in ("created_at", "evidence_sha256")
        }
        canonical_blob = json.dumps(
            canonical, sort_keys=True, ensure_ascii=False, indent=2)
        computed = hashlib.sha256(
            canonical_blob.encode("utf-8")).hexdigest()
        evidence_hash_verified = (computed == evidence_sha)

    # --- artifact integrity (only if requested AND readable) -------------
    integrity_note: str | None = None
    artifact_verified = None
    if verify_artifact and artifact_path:
        live_sha = _sha256_file(artifact_path)
        if live_sha is None:
            # Artifact intentionally unavailable / unreadable: reduced trust.
            integrity_note = (
                "artifact file not readable; full artifact integrity "
                "NOT verified")
            artifact_verified = False
        elif live_sha != artifact_sha:
            integrity_note = "artifact SHA-256 mismatch vs evidence"
            artifact_verified = False
        else:
            integrity_note = "artifact SHA-256 verified against evidence"
            artifact_verified = True
    elif verify_artifact and not artifact_path:
        integrity_note = "no artifact path in evidence; cannot verify artifact"
        artifact_verified = False

    # --- decision: FAIL verdict never becomes ready ----------------------
    if verdict != "PASS":
        return _reject(
            evidence_path=evidence_path,
            error_code=RENDER_VALIDATION_FAILED,
            error_detail="HVS render validation verdict was not PASS",
            schema_version=schema_version,
            validation_id=validation_id,
            project_id=project_id,
            verdict=verdict,
            export_ready=export_ready,
            artifact_path=artifact_path,
            artifact_sha256=artifact_sha,
            artifact_size_bytes=artifact_size,
            failed_check_ids=failed_ids,
            failed_reasons=failed_reasons,
            evidence_sha256=evidence_sha,
            integrity_note=integrity_note,
            unknown_hvs_fields=unknown,
            raw_evidence=evidence,
        )

    # --- PASS path: decide trust level ----------------------------------
    # Detect evidence-tamper mismatch explicitly.
    if evidence_hash_verified is False:
        return _reject(
            evidence_path=evidence_path,
            error_code=EVIDENCE_INTEGRITY_UNVERIFIABLE,
            error_detail="evidence tamper hash mismatch; evidence cannot "
                       "be trusted",
            schema_version=schema_version,
            validation_id=validation_id,
            project_id=project_id,
            verdict=verdict,
            export_ready=export_ready,
            artifact_path=artifact_path,
            artifact_sha256=artifact_sha,
            artifact_size_bytes=artifact_size,
            failed_check_ids=failed_ids,
            failed_reasons=failed_reasons,
            evidence_sha256=evidence_sha,
            integrity_note=integrity_note,
            unknown_hvs_fields=unknown,
            raw_evidence=evidence,
        )

    # Trust determination on the PASS path.
    if artifact_verified is True and evidence_hash_verified is True:
        trust = TRUST_VERIFIED
        action = ACTION_REVIEW_EXPORT_READY
        integrity_note = integrity_note or "fully verified"
    elif artifact_verified is False:
        # Artifact not verifiable -> reduced trust, never falsely VERIFIED.
        trust = TRUST_PARTIAL
        action = ACTION_REPAIR_OR_RERENDER
        integrity_note = integrity_note or "artifact integrity unverifiable"
    else:
        # Artifact verification disabled by caller; evidence hash ok.
        trust = TRUST_PARTIAL
        action = ACTION_REVIEW_EXPORT_READY
        integrity_note = integrity_note or (
            "artifact verification disabled; evidence hash verified only")

    packet_id = _stable_id(
        "accept", evidence_path, validation_id or "",
        schema_version or "", verdict or "",
        artifact_sha or "", evidence_sha or "")

    return HVSEvidenceIntakeResult(
        ok=True,
        packet_id=packet_id,
        source=SOURCE_NAME,
        schema_version=schema_version,
        validation_id=validation_id,
        project_id=project_id,
        verdict=verdict,
        export_ready=export_ready,
        trust_level=trust,
        operator_action=action,
        automation_allowed=False,
        evidence_path=evidence_path,
        artifact_path=artifact_path,
        artifact_sha256=artifact_sha,
        artifact_size_bytes=artifact_size,
        failed_check_ids=failed_ids,
        failed_reasons=failed_reasons,
        evidence_sha256=evidence_sha,
        evidence_sha256_verified=evidence_hash_verified,
        integrity_note=integrity_note,
        unknown_hvs_fields=unknown,
        error_code=None,
        error_detail=None,
        raw_evidence=evidence,
    )
