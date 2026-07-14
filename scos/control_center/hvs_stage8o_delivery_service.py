"""SCOS <-> HVS — Stage 8O delivery-package + manual-authorization + delivery-record service.

Orchestrates the THREE SEPARATE STAGE 8O BOUNDARIES:

    A. prepare_delivery_package / materialize_delivery_package / verify_delivery_package
    B. create_manual_delivery_authorization_request / approve_manual_delivery /
       reject_manual_delivery
    C. record_actual_manual_delivery

Every mutation:
1. validates inputs,
2. loads current state,
3. re-verifies upstream Stage 8N evidence (including a live SHA-256 recompute),
4. enforces the state transition,
5. detects idempotent replay,
6. detects conflict,
7. appends a deterministic append-only event,
8. returns structured output,
9. preserves automation_allowed=False.

SCOS performs NO transport, no upload, no publish, no customer contact, no HVS
mutation, no render. Local-first, deterministic, stdlib-only.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .hvs_render_completion_service import inspect_render_completion
from .hvs_render_completion_store import render_completion_path
from .hvs_asset_materialization import AssetResolutionError
from .hvs_stage8o_delivery_models import (
    AUTH_APPROVED,
    AUTH_CANCELLED,
    AUTH_DECISION_SCHEMA_VERSION,
    AUTH_EXPIRED,
    AUTH_PENDING,
    AUTH_REJECTED,
    AUTH_REQUEST_SCHEMA_VERSION,
    ALLOWED_AUTH_STATUSES,
    ALLOWED_DELIVERY_EVENT_TYPES,
    ALLOWED_DELIVERY_METHODS,
    ALLOWED_DELIVERY_STATUSES,
    ALLOWED_PACKAGE_STATUSES,
    DEL_DELIVERED_MANUALLY,
    DEL_NOT_DELIVERED,
    DELIVERY_RECORD_SCHEMA_VERSION,
    DEFAULT_DELIVERY_PACKAGES_RELATIVE,
    ERR_ARTIFACT_MISSING,
    ERR_ARTIFACT_NOT_REGULAR,
    ERR_ARTIFACT_SHA_MISMATCH,
    ERR_ARTIFACT_SYMLINK,
    ERR_ARTIFACT_ZERO_BYTE,
    ERR_AUTH_ALREADY_DECIDED,
    ERR_AUTH_CANCELLED,
    ERR_AUTH_EXPIRED,
    ERR_AUTH_NOT_FOUND,
    ERR_AUTH_NOT_PENDING,
    ERR_AUTH_REJECTED,
    ERR_COMPLETION_AUTOMATION,
    ERR_COMPLETION_DELIVERY_AUTHORIZED,
    ERR_COMPLETION_NOT_COMPLETE,
    ERR_COMPLETION_NOT_FOUND,
    ERR_COMPLETION_NOT_VERIFIED,
    ERR_COMPLETION_PUBLISH_AUTHORIZED,
    ERR_DELIVERY_CONFLICT,
    ERR_DELIVERY_NOT_AUTHORIZED,
    ERR_DELIVERY_REPLAYED,
    ERR_MISSING_CONFIRMATION,
    ERR_MISSING_METHOD,
    ERR_MISSING_OPERATOR_ID,
    ERR_MISSING_REASON,
    ERR_MISSING_RECIPIENT,
    ERR_NOT_MATERIALIZED,
    ERR_PACKAGE_CONFLICT,
    ERR_PACKAGE_NOT_FOUND,
    ERR_PACKAGE_NOT_MATERIALIZED,
    ERR_PACKAGE_NOT_READY,
    ERR_INVALID_METHOD,
    ERR_PROJECT_MISMATCH,
    ERR_UNEXPECTED_FILES,
    ERR_UNSAFE_RECIPIENT,
    PACKAGE_CONTRACT_SCHEMA_VERSION,
    PACKAGE_MANIFEST_SCHEMA_VERSION,
    PKG_CANCELLED,
    PKG_CONFLICTED,
    PKG_FAILED,
    PKG_MATERIALIZED,
    PKG_MATERIALIZING,
    PKG_PREPARED,
    PKG_READY,
    PKG_VERIFYING,
    STAGE8O_SCHEMA_VERSION,
    ActualManualDeliveryRecord,
    DeliveryPackageContract,
    DeliveryPackageManifest,
    ManualDeliveryAuthorizationDecision,
    ManualDeliveryAuthorizationRequest,
    Stage8ORenderEvidenceBinding,
    _safe_external_evidence_reference,
    _safe_other_manual_description,
    _safe_recipient_reference,
    actual_delivery_record_id,
    authorization_decision_id as auth_decision_id_fn,
    authorization_request_id as auth_request_id_fn,
    canonical_json,
    delivery_package_id,
    package_content_hash as pkg_content_hash_fn,
    package_contract_hash as pkg_contract_hash_fn,
    package_manifest_hash as pkg_manifest_hash_fn,
    resolve_artifact_source,
    sha256_bytes,
    stable_id,
    _safe_text,
    _immutable_text,
)

# Stable audit event types (mirrors models.ALLOWED_DELIVERY_EVENT_TYPES).
EVT_PKG_PREPARED = "PACKAGE_PREPARED"
EVT_PKG_MATERIALIZATION_STARTED = "PACKAGE_MATERIALIZATION_STARTED"
EVT_PKG_MATERIALIZED = "PACKAGE_MATERIALIZED"
EVT_PKG_REUSED = "PACKAGE_REUSED"
EVT_PKG_VERIFIED = "PACKAGE_VERIFIED"
EVT_PKG_INTEGRITY_FAILED = "PACKAGE_INTEGRITY_FAILED"
EVT_PKG_CONFLICTED = "PACKAGE_CONFLICTED"
EVT_PKG_CANCELLED = "PACKAGE_CANCELLED"
EVT_PKG_FAILED = "PACKAGE_FAILED"
EVT_AUTH_REQUESTED = "AUTHORIZATION_REQUESTED"
EVT_AUTH_APPROVED = "AUTHORIZATION_APPROVED"
EVT_AUTH_REJECTED = "AUTHORIZATION_REJECTED"
EVT_AUTH_CANCELLED = "AUTHORIZATION_CANCELLED"
EVT_AUTH_EXPIRED = "AUTHORIZATION_EXPIRED"
EVT_DELIVERY_RECORDED = "DELIVERY_RECORDED"
EVT_DELIVERY_RECORD_REPLAYED = "DELIVERY_RECORD_REPLAYED"
EVT_DELIVERY_RECORD_REJECTED = "DELIVERY_RECORD_REJECTED"
EVT_DELIVERY_RECORD_CONFLICTED = "DELIVERY_RECORD_CONFLICTED"

METHOD_OTHER_MANUAL = "OTHER_MANUAL"
from .hvs_stage8o_delivery_store import (
    append_delivery_event,
    delivery_ledger_path,
    events_for_authorization,
    events_for_package,
    latest_event_by_type,
    latest_event_for_subject,
    read_delivery_events,
)


PACKAGE_MANIFEST_REL = "delivery_package_manifest.json"
PACKAGE_README_REL = "README.txt"
PACKAGE_CHECKSUMS_REL = "CHECKSUMS.txt"

_README_TEXT = (
    "SCOS <-> HVS Stage 8O Local Delivery Package\n"
    "===========================================\n"
    "\n"
    "This directory is a LOCAL delivery-package workspace prepared by SCOS from a\n"
    "certified Stage 8N render artifact. It contains a byte-identical copy of the\n"
    "approved artifact plus a provenance manifest. SCOS does NOT deliver anything.\n"
    "A human operator must perform the actual delivery through an external,\n"
    "out-of-system channel after explicit manual-delivery authorization.\n"
    "\n"
    "Do not treat the presence of this package as proof of delivery, receipt,\n"
    "or acceptance.\n"
)

# Expected package files (relative names) when materialized.
_EXPECTED_PACKAGE_FILES = (PACKAGE_MANIFEST_REL, PACKAGE_README_REL, PACKAGE_CHECKSUMS_REL)


@dataclass(frozen=True)
class Stage8OServiceResult:
    ok: bool
    delivery_package_id: str | None = None
    package_status: str | None = None
    package_content_hash: str | None = None
    package_contract_hash: str | None = None
    authorization_request_id: str | None = None
    authorization_status: str | None = None
    authorization_decision_id: str | None = None
    delivery_record_id: str | None = None
    delivery_status: str | None = None
    artifact_sha256: str | None = None
    package_path: str | None = None
    manifest_path: str | None = None
    error_code: str | None = None
    error_detail: str | None = None
    replayed: bool = False
    safe_recipient_reference: str | None = None
    allowed_manual_delivery_method: str | None = None
    manual_delivery_method: str | None = None
    operator_id: str | None = None
    external_evidence_reference: str | None = None
    manual_delivery_performed: bool = False
    external_delivery_executed_by_scos: bool = False
    delivery_authorized: bool = False
    delivery_performed: bool = False
    customer_receipt_confirmed: bool = False
    customer_acceptance_recorded: bool = False
    publishing_performed: bool = False
    invoice_state_changed: bool = False
    payment_state_changed: bool = False
    automation_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "delivery_package_id": self.delivery_package_id,
            "package_status": self.package_status,
            "package_content_hash": self.package_content_hash,
            "package_contract_hash": self.package_contract_hash,
            "authorization_request_id": self.authorization_request_id,
            "authorization_status": self.authorization_status,
            "authorization_decision_id": self.authorization_decision_id,
            "delivery_record_id": self.delivery_record_id,
            "delivery_status": self.delivery_status,
            "artifact_sha256": self.artifact_sha256,
            "package_path": self.package_path,
            "manifest_path": self.manifest_path,
            "safe_recipient_reference": self.safe_recipient_reference,
            "allowed_manual_delivery_method": self.allowed_manual_delivery_method,
            "manual_delivery_method": self.manual_delivery_method,
            "operator_id": self.operator_id,
            "external_evidence_reference": self.external_evidence_reference,
            "manual_delivery_performed": self.manual_delivery_performed,
            "external_delivery_executed_by_scos": self.external_delivery_executed_by_scos,
            "delivery_authorized": self.delivery_authorized,
            "delivery_performed": self.delivery_performed,
            "manual_delivery_required": True,
            "customer_receipt_confirmed": self.customer_receipt_confirmed,
            "customer_acceptance_recorded": self.customer_acceptance_recorded,
            "publishing_performed": self.publishing_performed,
            "invoice_state_changed": self.invoice_state_changed,
            "payment_state_changed": self.payment_state_changed,
            "automation_allowed": self.automation_allowed,
            "replayed": self.replayed,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
        }


def _deny(*, error_code: str, error_detail: str, **extra: Any) -> Stage8OServiceResult:
    return Stage8OServiceResult(ok=False, error_code=error_code, error_detail=error_detail, **extra)


def _runtime_root(repo_root: Any) -> Path:
    return Path(repo_root).resolve() / DEFAULT_DELIVERY_PACKAGES_RELATIVE


def _packages_root(repo_root: Any) -> Path:
    return _runtime_root(repo_root)


def _assert_safe_relative_name(name: str) -> None:
    if not name or ".." in name.split("/") or "\\" in name or name.startswith("/"):
        raise ValueError("unsafe relative name")
    lowered = name.lower()
    if "://" in lowered or name.startswith("\\\\") or name.startswith("//"):
        raise ValueError("unsafe relative name")


def _resolve_package_dir(repo_root: Any, package_id: str) -> Path:
    _assert_safe_relative_name(package_id)
    return _packages_root(repo_root) / package_id


def _load_completion_binding(
    *, repo_root: Any, completion_evidence_id: str, project_id: str, artifact_path: str
) -> Stage8ORenderEvidenceBinding:
    """Load + reverify genuine Stage 8N completion evidence; recompute source hash."""
    ledger = render_completion_path(repo_root)
    rec = inspect_render_completion(
        repo_root=repo_root, render_request_id=completion_evidence_id
    )
    if not rec.get("ok"):
        raise _Stage8OBlocked(ERR_COMPLETION_NOT_FOUND, "no Stage 8N completion evidence found")
    if not rec.get("artifact_verified"):
        raise _Stage8OBlocked(ERR_COMPLETION_NOT_VERIFIED, "artifact verification is not VERIFIED")
    if rec.get("completion_status") != "COMPLETE":
        raise _Stage8OBlocked(ERR_COMPLETION_NOT_COMPLETE, "render execution is not COMPLETE")
    if rec.get("delivery_authorized"):
        raise _Stage8OBlocked(
            ERR_COMPLETION_DELIVERY_AUTHORIZED, "Stage 8N evidence shows delivery already authorized"
        )
    if rec.get("publishing_authorized"):
        raise _Stage8OBlocked(
            ERR_COMPLETION_PUBLISH_AUTHORIZED, "Stage 8N evidence shows publishing already authorized"
        )
    if rec.get("automation_allowed") is not False:
        raise _Stage8OBlocked(ERR_COMPLETION_AUTOMATION, "automation_allowed must be false")
    if rec.get("project_id") and rec["project_id"] != project_id:
        raise _Stage8OBlocked(ERR_PROJECT_MISMATCH, "project_id mismatch with 8N evidence")

    # Live recompute of source artifact identity.
    try:
        src = resolve_artifact_source(artifact_path)
    except (ValueError, AssetResolutionError) as exc:
        raise _Stage8OBlocked(ERR_ARTIFACT_MISSING, str(exc)) from exc
    if src.is_symlink():
        raise _Stage8OBlocked(ERR_ARTIFACT_SYMLINK, "artifact is a symlink")
    size = src.stat().st_size
    if size <= 0:
        raise _Stage8OBlocked(ERR_ARTIFACT_ZERO_BYTE, "artifact is zero bytes")
    live_sha = sha256_bytes(src.read_bytes())
    certified_sha = str(rec.get("artifact_sha256_values", [""])[0] or "").lower()
    if certified_sha and live_sha.lower() != certified_sha:
        raise _Stage8OBlocked(
            ERR_ARTIFACT_SHA_MISMATCH, "live artifact SHA-256 does not match certified Stage 8N hash"
        )

    # The genuine HVS project identity is the certified Stage 8N project id.
    # The Stage 8N completion record keeps the provenance under ``project_id``
    # (it does NOT carry a separate ``hvs_project_id`` field); we therefore
    # copy it from ``rec["project_id"]`` rather than a missing field.
    hvs_project_id = str(rec.get("hvs_project_id") or rec.get("project_id") or project_id)
    return Stage8ORenderEvidenceBinding(
        project_id=project_id,
        completion_evidence_id=completion_evidence_id,
        render_request_id=str(rec.get("render_request_id", "")),
        render_approval_id=str(rec.get("render_approval_id", "")),
        render_dispatch_id=str(rec.get("render_dispatch_id", "")),
        hvs_project_id=hvs_project_id,
        artifact_id=str(rec.get("artifact_id", "")),
        artifact_sha256=live_sha,
        source_artifact_size=size,
        completion_status=str(rec.get("completion_status", "")),
        artifact_verified=bool(rec.get("artifact_verified")),
        delivery_authorized=False,
        publishing_authorized=False,
        automation_allowed=False,
    )


class _Stage8OBlocked(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _find_event(ledger_path: Path, event_type: str, subject_id: str) -> dict[str, Any] | None:
    for ev in read_delivery_events(ledger_path=ledger_path):
        if ev.get("subject_id") == subject_id and ev["event_type"] == event_type:
            return ev
    return None


def _latest_status_for_subject(ledger_path: Path, subject_id: str) -> str | None:
    ev = latest_event_for_subject(ledger_path=ledger_path, subject_id=subject_id)
    return ev["resulting_status"] if ev else None


# ---------------------------------------------------------------------------
# BOUNDARY A — Delivery package
# ---------------------------------------------------------------------------
def prepare_delivery_package(
    *,
    repo_root: Any,
    completion_evidence_id: str,
    project_id: str,
    artifact_path: str,
    operator_id: str,
    recorded_at: str,
) -> Stage8OServiceResult:
    if not str(operator_id or "").strip():
        return _deny(error_code=ERR_MISSING_OPERATOR_ID, error_detail="operator_id is required")
    try:
        binding = _load_completion_binding(
            repo_root=repo_root,
            completion_evidence_id=completion_evidence_id,
            project_id=project_id,
            artifact_path=artifact_path,
        )
    except _Stage8OBlocked as exc:
        return _deny(error_code=exc.code, error_detail=exc.detail)

    ledger = delivery_ledger_path(repo_root)
    artifact_filename = Path(artifact_path).name
    pkg_id = delivery_package_id(
        project_id=binding.project_id,
        completion_evidence_id=binding.completion_evidence_id,
        artifact_id=binding.artifact_id,
        artifact_sha256=binding.artifact_sha256,
        artifact_filename=artifact_filename,
        contract_version=PACKAGE_CONTRACT_SCHEMA_VERSION,
        package_revision=1,
    )
    try:
        _assert_safe_relative_name(pkg_id)
    except ValueError:
        return _deny(error_code=ERR_UNSAFE_PATH, error_detail="deterministic package id unsafe")

    # Idempotent: existing prepared contract for identical inputs.
    existing = _find_event(ledger, EVT_PKG_PREPARED, pkg_id)
    if existing is not None:
        contract = _load_contract(repo_root, pkg_id)
        if contract is None:
            contract = DeliveryPackageContract(**(existing.get("record") or {}))
        if contract is not None and contract.artifact_sha256 == binding.artifact_sha256 and contract.package_status in (
            PKG_PREPARED,
            PKG_MATERIALIZED,
            PKG_READY,
        ):
            return Stage8OServiceResult(
                ok=True,
                delivery_package_id=pkg_id,
                package_status=contract.package_status,
                package_content_hash=contract.package_content_hash,
                package_contract_hash=contract.package_contract_hash,
                artifact_sha256=contract.artifact_sha256,
                replayed=True,
            )

    contract = DeliveryPackageContract(
        schema_version=PACKAGE_CONTRACT_SCHEMA_VERSION,
        delivery_package_id=pkg_id,
        package_contract_hash="",  # filled after identity is final
        project_id=binding.project_id,
        hvs_project_id=binding.hvs_project_id,
        correlation_id=binding.completion_evidence_id,
        completion_evidence_id=binding.completion_evidence_id,
        render_request_id=binding.render_request_id,
        render_approval_id=binding.render_approval_id,
        artifact_id=binding.artifact_id,
        artifact_sha256=binding.artifact_sha256,
        source_artifact_size=binding.source_artifact_size,
        source_artifact_display_path=artifact_path,
        artifact_filename=artifact_filename,
        artifact_media_type="video/mp4",
        package_revision=1,
        package_status=PKG_PREPARED,
        package_runtime_root=str(_packages_root(repo_root) / pkg_id),
        package_manifest_filename=PACKAGE_MANIFEST_REL,
        package_content_hash="",  # not yet materialized
        recorded_at=recorded_at,
    )
    contract_hash = pkg_contract_hash_fn(contract=contract.to_dict())
    final = DeliveryPackageContract(**{**contract.to_dict(), "package_contract_hash": contract_hash})
    append_delivery_event(
        ledger_path=ledger,
        event_type=EVT_PKG_PREPARED,
        subject_id=pkg_id,
        completion_evidence_id=binding.completion_evidence_id,
        artifact_sha256=binding.artifact_sha256,
        operator_id=operator_id,
        resulting_status=PKG_PREPARED,
        reason="package contract prepared from certified 8N evidence",
        recorded_at=recorded_at,
        package_id=pkg_id,
        package_content_hash=final.package_content_hash,
        record_payload=final.to_dict(),
    )
    # Persist the immutable contract as a sidecar JSON (runtime-only, ignored).
    _persist_contract(repo_root, final)
    return Stage8OServiceResult(
        ok=True,
        delivery_package_id=pkg_id,
        package_status=PKG_PREPARED,
        package_content_hash=final.package_content_hash,
        package_contract_hash=final.package_contract_hash,
        artifact_sha256=final.artifact_sha256,
    )


def _load_contract(repo_root: Any, package_id: str) -> DeliveryPackageContract | None:
    path = _resolve_package_dir(repo_root, package_id) / "package_contract.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    return DeliveryPackageContract(**data)


def _persist_contract(repo_root: Any, contract: DeliveryPackageContract) -> None:
    d = _resolve_package_dir(repo_root, contract.delivery_package_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "package_contract.json").write_text(
        json.dumps(contract.to_dict(), ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )


def materialize_delivery_package(
    *,
    repo_root: Any,
    delivery_package_id: str,
    artifact_path: str,
    operator_id: str,
    recorded_at: str,
) -> Stage8OServiceResult:
    if not str(operator_id or "").strip():
        return _deny(error_code=ERR_MISSING_OPERATOR_ID, error_detail="operator_id is required")
    contract = _load_contract(repo_root, delivery_package_id)
    if contract is None:
        return _deny(
            error_code=ERR_PACKAGE_NOT_FOUND,
            error_detail="package contract not found",
            delivery_package_id=delivery_package_id,
        )
    if contract.package_status in (PKG_CANCELLED, PKG_CONFLICTED, PKG_FAILED):
        return _deny(
            error_code=ERR_PACKAGE_CONFLICT,
            error_detail=f"package is in terminal state {contract.package_status}",
            delivery_package_id=delivery_package_id,
        )

    ledger = delivery_ledger_path(repo_root)
    pkg_dir = _resolve_package_dir(repo_root, delivery_package_id)

    # Re-verify the source artifact live (never trust prior hash).
    try:
        src = resolve_artifact_source(artifact_path)
    except (ValueError, AssetResolutionError) as exc:
        return _deny(error_code=ERR_ARTIFACT_MISSING, error_detail=str(exc), delivery_package_id=delivery_package_id)
    if src.is_symlink():
        return _deny(error_code=ERR_ARTIFACT_SYMLINK, error_detail="artifact is symlink", delivery_package_id=delivery_package_id)
    size = src.stat().st_size
    if size <= 0:
        return _deny(error_code=ERR_ARTIFACT_ZERO_BYTE, error_detail="artifact zero bytes", delivery_package_id=delivery_package_id)
    live_sha = sha256_bytes(src.read_bytes())
    if live_sha.lower() != contract.artifact_sha256.lower():
        return _deny(
            error_code=ERR_ARTIFACT_SHA_MISMATCH,
            error_detail="source hash changed since contract creation",
            delivery_package_id=delivery_package_id,
            artifact_sha256=live_sha,
        )

    append_delivery_event(
        ledger_path=ledger,
        event_type=EVT_PKG_MATERIALIZATION_STARTED,
        subject_id=delivery_package_id,
        completion_evidence_id=contract.completion_evidence_id,
        artifact_sha256=contract.artifact_sha256,
        operator_id=operator_id,
        resulting_status=PKG_MATERIALIZING,
        reason="materialization started",
        recorded_at=recorded_at,
        package_id=delivery_package_id,
        package_content_hash=contract.package_content_hash,
    )

    # Idempotent reuse: all expected files byte-identical and contract-identical.
    dest = pkg_dir / contract.artifact_filename
    if dest.is_file():
        existing_sha = sha256_bytes(dest.read_bytes())
        if existing_sha.lower() == live_sha.lower() and dest.stat().st_size == size:
            # Reuse path.
            return _finish_materialize(
                repo_root=repo_root,
                contract=contract,
                ledger=ledger,
                operator_id=operator_id,
                recorded_at=recorded_at,
                reused=True,
                pkg_dir=pkg_dir,
                artifact_filename=contract.artifact_filename,
                live_sha=live_sha,
                size=size,
            )
        # Different content at the same path => conflict (never overwrite).
        append_delivery_event(
            ledger_path=ledger,
            event_type=EVT_PKG_CONFLICTED,
            subject_id=delivery_package_id,
            completion_evidence_id=contract.completion_evidence_id,
            artifact_sha256=contract.artifact_sha256,
            operator_id=operator_id,
            resulting_status=PKG_CONFLICTED,
            reason="conflicting package content present; not overwritten",
            recorded_at=recorded_at,
            package_id=delivery_package_id,
            package_content_hash=contract.package_content_hash,
        )
        return _deny(
            error_code=ERR_PACKAGE_CONFLICT,
            error_detail="destination exists with conflicting content; not overwritten",
            delivery_package_id=delivery_package_id,
        )

    try:
        pkg_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        copied_sha = sha256_bytes(dest.read_bytes())
        if copied_sha.lower() != live_sha.lower() or dest.stat().st_size != size:
            raise _Stage8OBlocked(ERR_PACKAGE_CONFLICT, "copy verification failed")
        (pkg_dir / PACKAGE_README_REL).write_text(_README_TEXT, encoding="utf-8")
        (pkg_dir / PACKAGE_CHECKSUMS_REL).write_text(
            f"{copied_sha}  {contract.artifact_filename}\n", encoding="utf-8"
        )
    except _Stage8OBlocked as exc:
        append_delivery_event(
            ledger_path=ledger,
            event_type=EVT_PKG_FAILED,
            subject_id=delivery_package_id,
            completion_evidence_id=contract.completion_evidence_id,
            artifact_sha256=contract.artifact_sha256,
            operator_id=operator_id,
            resulting_status=PKG_FAILED,
            reason=exc.detail,
            recorded_at=recorded_at,
            package_id=delivery_package_id,
            package_content_hash=contract.package_content_hash,
        )
        return _deny(error_code=exc.code, error_detail=exc.detail, delivery_package_id=delivery_package_id)
    except OSError as exc:
        return _deny(error_code=ERR_PACKAGE_CONFLICT, error_detail=f"materialization failed: {exc}", delivery_package_id=delivery_package_id)

    return _finish_materialize(
        repo_root=repo_root,
        contract=contract,
        ledger=ledger,
        operator_id=operator_id,
        recorded_at=recorded_at,
        reused=False,
        pkg_dir=pkg_dir,
        artifact_filename=contract.artifact_filename,
        live_sha=live_sha,
        size=size,
    )


EVT_PKG_FAILED = "PACKAGE_FAILED"


def _finish_materialize(
    *,
    repo_root: Any,
    contract: DeliveryPackageContract,
    ledger: Path,
    operator_id: str,
    recorded_at: str,
    reused: bool,
    pkg_dir: Path,
    artifact_filename: str,
    live_sha: str,
    size: int,
) -> Stage8OServiceResult:
    manifest = DeliveryPackageManifest(
        schema_version=PACKAGE_MANIFEST_SCHEMA_VERSION,
        package_id=contract.delivery_package_id,
        package_contract_hash=contract.package_contract_hash,
        source_artifact_id=contract.artifact_id,
        source_artifact_sha256=contract.artifact_sha256,
        packaged_artifact_filename=artifact_filename,
        packaged_artifact_sha256=live_sha,
        packaged_artifact_size=size,
        package_manifest_hash="",  # filled below
        content_file_list=(artifact_filename, PACKAGE_MANIFEST_REL, PACKAGE_README_REL, PACKAGE_CHECKSUMS_REL),
        stage8n_completion_evidence_id=contract.completion_evidence_id,
        created_by_system="scos-stage8o-delivery",
        manual_delivery_warning="Package creation does NOT authorize delivery. A human must perform delivery after explicit authorization.",
        no_transport_statement="SCOS performs no transport: no upload, publish, email, message, webhook, or customer contact.",
        no_customer_receipt_statement="This package is not proof of customer receipt or acceptance.",
    )
    manifest_hash = pkg_manifest_hash_fn(manifest=manifest.to_dict())
    final_manifest = DeliveryPackageManifest(
        **{**manifest.to_dict(), "package_manifest_hash": manifest_hash}
    )
    (pkg_dir / PACKAGE_MANIFEST_REL).write_text(
        json.dumps(final_manifest.to_dict(), ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    content_hash = pkg_content_hash_fn(
        package_id=contract.delivery_package_id,
        manifest_hash=manifest_hash,
        packaged_artifact_sha256=live_sha,
        packaged_artifact_size=size,
        content_file_list=final_manifest.content_file_list,
    )
    updated = DeliveryPackageContract(
        **{**contract.to_dict(), "package_status": PKG_MATERIALIZED, "package_content_hash": content_hash}
    )
    _persist_contract(repo_root, updated)
    append_delivery_event(
        ledger_path=ledger,
        event_type=EVT_PKG_REUSED if reused else EVT_PKG_MATERIALIZED,
        subject_id=contract.delivery_package_id,
        completion_evidence_id=contract.completion_evidence_id,
        artifact_sha256=contract.artifact_sha256,
        operator_id=operator_id,
        resulting_status=PKG_MATERIALIZED,
        reason="package materialized (byte-identical copy + manifest)",
        recorded_at=recorded_at,
        package_id=contract.delivery_package_id,
        package_content_hash=content_hash,
    )
    return Stage8OServiceResult(
        ok=True,
        delivery_package_id=contract.delivery_package_id,
        package_status=PKG_MATERIALIZED,
        package_content_hash=content_hash,
        package_contract_hash=contract.package_contract_hash,
        artifact_sha256=contract.artifact_sha256,
        package_path=str(pkg_dir),
        manifest_path=str(pkg_dir / PACKAGE_MANIFEST_REL),
        replayed=reused,
    )


def verify_delivery_package(
    *,
    repo_root: Any,
    delivery_package_id: str,
    operator_id: str,
    recorded_at: str,
) -> Stage8OServiceResult:
    if not str(operator_id or "").strip():
        return _deny(error_code=ERR_MISSING_OPERATOR_ID, error_detail="operator_id is required")
    contract = _load_contract(repo_root, delivery_package_id)
    if contract is None:
        return _deny(error_code=ERR_PACKAGE_NOT_FOUND, error_detail="package contract not found", delivery_package_id=delivery_package_id)
    if contract.package_status not in (PKG_MATERIALIZED, PKG_READY):
        return _deny(error_code=ERR_NOT_MATERIALIZED, error_detail="package not materialized", delivery_package_id=delivery_package_id)

    ledger = delivery_ledger_path(repo_root)
    pkg_dir = _resolve_package_dir(repo_root, delivery_package_id)
    manifest_path = pkg_dir / PACKAGE_MANIFEST_REL
    if not manifest_path.is_file():
        return _deny(error_code=ERR_PACKAGE_NOT_MATERIALIZED, error_detail="manifest missing", delivery_package_id=delivery_package_id)

    try:
        mdata = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = DeliveryPackageManifest(**mdata)
    except (ValueError, OSError) as exc:
        return _deny(error_code=ERR_PACKAGE_NOT_MATERIALIZED, error_detail=f"malformed manifest: {exc}", delivery_package_id=delivery_package_id)

    if manifest.package_id != contract.delivery_package_id:
        return _deny(error_code=ERR_PACKAGE_CONFLICT, error_detail="manifest package id mismatch", delivery_package_id=delivery_package_id)
    if manifest.package_contract_hash != contract.package_contract_hash:
        return _deny(error_code=ERR_PACKAGE_CONFLICT, error_detail="manifest contract hash mismatch", delivery_package_id=delivery_package_id)
    if mdata.get("package_manifest_hash") != pkg_manifest_hash_fn(manifest=manifest.to_dict()):
        return _deny(error_code=ERR_PACKAGE_CONFLICT, error_detail="manifest hash mismatch", delivery_package_id=delivery_package_id)

    packaged = pkg_dir / manifest.packaged_artifact_filename
    if not packaged.is_file() or packaged.is_symlink():
        return _deny(error_code=ERR_ARTIFACT_NOT_REGULAR, error_detail="packaged artifact missing or not regular", delivery_package_id=delivery_package_id)
    if packaged.stat().st_size <= 0:
        return _deny(error_code=ERR_ARTIFACT_ZERO_BYTE, error_detail="packaged artifact zero bytes", delivery_package_id=delivery_package_id)
    packaged_sha = sha256_bytes(packaged.read_bytes())
    if packaged_sha.lower() != manifest.packaged_artifact_sha256.lower():
        return _deny(error_code=ERR_ARTIFACT_SHA_MISMATCH, error_detail="packaged sha mismatch", delivery_package_id=delivery_package_id)
    if packaged.stat().st_size != manifest.packaged_artifact_size:
        return _deny(error_code=ERR_ARTIFACT_SHA_MISMATCH, error_detail="packaged size mismatch", delivery_package_id=delivery_package_id)
    if manifest.packaged_artifact_sha256.lower() != contract.artifact_sha256.lower():
        return _deny(error_code=ERR_PACKAGE_CONFLICT, error_detail="source-to-package binding mismatch", delivery_package_id=delivery_package_id)

    # Fail closed on unexpected extra files.
    actual_files = {p.name for p in pkg_dir.iterdir() if p.is_file()}
    expected = set(_EXPECTED_PACKAGE_FILES) | {manifest.packaged_artifact_filename, "package_contract.json"}
    unexpected = actual_files - expected
    if unexpected:
        return _deny(error_code=ERR_UNEXPECTED_FILES, error_detail=f"unexpected package files: {sorted(unexpected)}", delivery_package_id=delivery_package_id)

    content_hash = pkg_content_hash_fn(
        package_id=contract.delivery_package_id,
        manifest_hash=manifest.package_manifest_hash,
        packaged_artifact_sha256=packaged_sha,
        packaged_artifact_size=manifest.packaged_artifact_size,
        content_file_list=manifest.content_file_list,
    )
    updated = DeliveryPackageContract(
        **{**contract.to_dict(), "package_status": PKG_READY, "package_content_hash": content_hash}
    )
    _persist_contract(repo_root, updated)
    append_delivery_event(
        ledger_path=ledger,
        event_type=EVT_PKG_VERIFIED,
        subject_id=delivery_package_id,
        completion_evidence_id=contract.completion_evidence_id,
        artifact_sha256=contract.artifact_sha256,
        operator_id=operator_id,
        resulting_status=PKG_READY,
        reason="package integrity verified; PACKAGE_READY",
        recorded_at=recorded_at,
        package_id=delivery_package_id,
        package_content_hash=content_hash,
    )
    return Stage8OServiceResult(
        ok=True,
        delivery_package_id=delivery_package_id,
        package_status=PKG_READY,
        package_content_hash=content_hash,
        package_contract_hash=contract.package_contract_hash,
        artifact_sha256=contract.artifact_sha256,
        package_path=str(pkg_dir),
        manifest_path=str(manifest_path),
    )


# ---------------------------------------------------------------------------
# BOUNDARY B — Manual delivery authorization
# ---------------------------------------------------------------------------
def create_manual_delivery_authorization_request(
    *,
    repo_root: Any,
    delivery_package_id: str,
    recipient_reference: str,
    delivery_method: str,
    operator_id: str,
    recorded_at: str,
    other_manual_description: str | None = None,
    authorization_validity: str = "",
) -> Stage8OServiceResult:
    if not str(operator_id or "").strip():
        return _deny(error_code=ERR_MISSING_OPERATOR_ID, error_detail="operator_id is required")
    contract = _load_contract(repo_root, delivery_package_id)
    if contract is None:
        return _deny(error_code=ERR_PACKAGE_NOT_FOUND, error_detail="package not found", delivery_package_id=delivery_package_id)
    if contract.package_status != PKG_READY:
        return _deny(error_code=ERR_PACKAGE_NOT_READY, error_detail="package must be PACKAGE_READY", delivery_package_id=delivery_package_id)
    if contract.package_content_hash in (None, ""):
        return _deny(error_code=ERR_PACKAGE_NOT_READY, error_detail="package content hash missing", delivery_package_id=delivery_package_id)
    if delivery_method not in ALLOWED_DELIVERY_METHODS:
        return _deny(error_code=ERR_INVALID_METHOD, error_detail="unsupported delivery method", delivery_package_id=delivery_package_id)
    try:
        recipient = _safe_recipient_reference(recipient_reference)
    except ValueError as exc:
        return _deny(error_code=ERR_UNSAFE_RECIPIENT, error_detail=str(exc), delivery_package_id=delivery_package_id)
    if not recipient:
        return _deny(error_code=ERR_MISSING_RECIPIENT, error_detail="recipient reference required", delivery_package_id=delivery_package_id)
    if delivery_method == METHOD_OTHER_MANUAL:
        if not other_manual_description:
            return _deny(error_code=ERR_MISSING_REASON, error_detail="other_manual requires a safe description", delivery_package_id=delivery_package_id)
        try:
            _safe_other_manual_description(other_manual_description)
        except ValueError as exc:
            return _deny(error_code=ERR_UNSAFE_RECIPIENT, error_detail=str(exc), delivery_package_id=delivery_package_id)

    ledger = delivery_ledger_path(repo_root)
    req_id = auth_request_id_fn(
        package_id=contract.delivery_package_id,
        package_contract_hash=contract.package_contract_hash,
        package_content_hash=contract.package_content_hash,
        artifact_sha256=contract.artifact_sha256,
        recipient_reference=recipient,
        method=delivery_method,
    )
    # Idempotent replay.
    existing = _find_event(ledger, EVT_AUTH_REQUESTED, req_id)
    if existing is not None:
        req = ManualDeliveryAuthorizationRequest(**existing["record"])
        if req.authorization_status == AUTH_PENDING:
            return Stage8OServiceResult(
                ok=True,
                delivery_package_id=delivery_package_id,
                authorization_request_id=req_id,
                authorization_status=AUTH_PENDING,
                package_content_hash=contract.package_content_hash,
                artifact_sha256=contract.artifact_sha256,
                replayed=True,
            )
        return _deny(
            error_code=ERR_AUTH_ALREADY_DECIDED,
            error_detail=f"authorization request already decided ({req.authorization_status})",
            delivery_package_id=delivery_package_id,
            authorization_request_id=req_id,
        )

    req = ManualDeliveryAuthorizationRequest(
        schema_version=AUTH_REQUEST_SCHEMA_VERSION,
        authorization_request_id=req_id,
        delivery_package_id=contract.delivery_package_id,
        package_contract_hash=contract.package_contract_hash,
        package_content_hash=contract.package_content_hash,
        package_verification_id=stable_id("scos-hvs-stage8o-verify", {"package_id": contract.delivery_package_id}),
        artifact_sha256=contract.artifact_sha256,
        project_id=contract.project_id,
        safe_recipient_reference=recipient,
        allowed_manual_delivery_method=delivery_method,
        authorization_status=AUTH_PENDING,
        requested_operator_id=operator_id,
        authorization_validity=authorization_validity,
        scope_statement=(
            "Approval permits only a future human-performed delivery. It does not "
            "send, upload, publish or contact the recipient."
        ),
    )
    append_delivery_event(
        ledger_path=ledger,
        event_type=EVT_AUTH_REQUESTED,
        subject_id=req_id,
        completion_evidence_id=contract.completion_evidence_id,
        artifact_sha256=contract.artifact_sha256,
        operator_id=operator_id,
        resulting_status=AUTH_PENDING,
        reason="manual delivery authorization requested",
        recorded_at=recorded_at,
        package_id=delivery_package_id,
        package_content_hash=contract.package_content_hash,
        authorization_request_id=req_id,
        record_payload=req.to_dict(),
    )
    return Stage8OServiceResult(
        ok=True,
        delivery_package_id=delivery_package_id,
        authorization_request_id=req_id,
        authorization_status=AUTH_PENDING,
        package_content_hash=contract.package_content_hash,
        artifact_sha256=contract.artifact_sha256,
        safe_recipient_reference=recipient,
        allowed_manual_delivery_method=delivery_method,
    )


METHOD_OTHER_MANUAL = "OTHER_MANUAL"


def inspect_manual_delivery_authorization(
    *, repo_root: Any, authorization_request_id: str
) -> Stage8OServiceResult:
    ledger = delivery_ledger_path(repo_root)
    ev = _find_event(ledger, EVT_AUTH_REQUESTED, authorization_request_id)
    if ev is None:
        return _deny(error_code=ERR_AUTH_NOT_FOUND, error_detail="authorization request not found")
    # Find latest decision for this request.
    status = AUTH_PENDING
    decision_ev = None
    for e in events_for_authorization(ledger_path=ledger, authorization_request_id=authorization_request_id):
        if e["event_type"] in (EVT_AUTH_APPROVED, EVT_AUTH_REJECTED, EVT_AUTH_CANCELLED, EVT_AUTH_EXPIRED):
            decision_ev = e
            status = e["resulting_status"]
    return Stage8OServiceResult(
        ok=True,
        authorization_request_id=authorization_request_id,
        authorization_status=status,
        delivery_package_id=ev.get("package_id"),
        package_content_hash=ev.get("package_content_hash"),
        artifact_sha256=ev.get("artifact_sha256"),
        authorization_decision_id=decision_ev["authorization_decision_id"] if decision_ev else None,
    )


def _load_auth_request(repo_root: Any, authorization_request_id: str) -> tuple[ManualDeliveryAuthorizationRequest | None, str | None]:
    ledger = delivery_ledger_path(repo_root)
    ev = _find_event(ledger, EVT_AUTH_REQUESTED, authorization_request_id)
    if ev is None:
        return None, None
    status = AUTH_PENDING
    for e in events_for_authorization(ledger_path=ledger, authorization_request_id=authorization_request_id):
        if e["event_type"] in (EVT_AUTH_APPROVED, EVT_AUTH_REJECTED, EVT_AUTH_CANCELLED, EVT_AUTH_EXPIRED):
            status = e["resulting_status"]
    return ManualDeliveryAuthorizationRequest(**ev["record"]), status


def _recompute_live_package_binding(
    *, repo_root: Any, package_id: str
) -> tuple[DeliveryPackageContract, str, str]:
    """Recompute the LIVE package content hash + artifact SHA-256 from the
    materialized package directory. Fail closed on any integrity problem.

    Used by approval, rejection and actual-delivery recording to detect package
    or artifact drift between the authorization binding and the live state.
    Read-only: appends no events and never mutates package status.
    """
    contract = _load_contract(repo_root, package_id)
    if contract is None:
        raise _Stage8OBlocked(ERR_PACKAGE_NOT_FOUND, "package contract not found")
    if contract.package_status != PKG_READY:
        raise _Stage8OBlocked(ERR_PACKAGE_NOT_READY, "package no longer PACKAGE_READY")
    if not contract.package_content_hash:
        raise _Stage8OBlocked(ERR_PACKAGE_NOT_READY, "package content hash missing")
    pkg_dir = _resolve_package_dir(repo_root, package_id)
    manifest_path = pkg_dir / PACKAGE_MANIFEST_REL
    if not manifest_path.is_file():
        raise _Stage8OBlocked(ERR_PACKAGE_NOT_MATERIALIZED, "manifest missing")
    try:
        mdata = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = DeliveryPackageManifest(**mdata)
    except (ValueError, OSError) as exc:
        raise _Stage8OBlocked(ERR_PACKAGE_NOT_MATERIALIZED, f"malformed manifest: {exc}")
    if manifest.package_id != contract.delivery_package_id:
        raise _Stage8OBlocked(ERR_PACKAGE_CONFLICT, "manifest package id mismatch")
    if manifest.package_contract_hash != contract.package_contract_hash:
        raise _Stage8OBlocked(ERR_PACKAGE_CONFLICT, "manifest contract hash mismatch")
    if mdata.get("package_manifest_hash") != pkg_manifest_hash_fn(manifest=manifest.to_dict()):
        raise _Stage8OBlocked(ERR_PACKAGE_CONFLICT, "manifest hash mismatch")
    packaged = pkg_dir / manifest.packaged_artifact_filename
    if not packaged.is_file() or packaged.is_symlink():
        raise _Stage8OBlocked(ERR_ARTIFACT_NOT_REGULAR, "packaged artifact missing or not regular")
    if packaged.stat().st_size <= 0:
        raise _Stage8OBlocked(ERR_ARTIFACT_ZERO_BYTE, "packaged artifact zero bytes")
    live_artifact_sha = sha256_bytes(packaged.read_bytes())
    live_content_hash = pkg_content_hash_fn(
        package_id=contract.delivery_package_id,
        manifest_hash=manifest.package_manifest_hash,
        packaged_artifact_sha256=live_artifact_sha,
        packaged_artifact_size=manifest.packaged_artifact_size,
        content_file_list=manifest.content_file_list,
    )
    # Package/artifact drift fails closed before finer artifact checks.
    if live_content_hash != contract.package_content_hash:
        raise _Stage8OBlocked(ERR_PACKAGE_CONFLICT, "package content hash drift detected")
    if live_artifact_sha.lower() != manifest.packaged_artifact_sha256.lower():
        raise _Stage8OBlocked(ERR_ARTIFACT_SHA_MISMATCH, "packaged artifact SHA mismatch")
    if manifest.packaged_artifact_sha256.lower() != contract.artifact_sha256.lower():
        raise _Stage8OBlocked(ERR_PACKAGE_CONFLICT, "source-to-package binding mismatch")
    return contract, live_content_hash, live_artifact_sha


def approve_manual_delivery(
    *,
    repo_root: Any,
    authorization_request_id: str,
    operator_id: str,
    recorded_at: str,
    approval_note: str | None = None,
) -> Stage8OServiceResult:
    if not str(operator_id or "").strip():
        return _deny(error_code=ERR_MISSING_OPERATOR_ID, error_detail="operator_id is required")
    req, status = _load_auth_request(repo_root, authorization_request_id)
    if req is None:
        return _deny(error_code=ERR_AUTH_NOT_FOUND, error_detail="authorization request not found")
    ledger = delivery_ledger_path(repo_root)
    # Reverify the LIVE package binding before any decision (fail closed on drift).
    try:
        contract, live_content_hash, live_artifact_sha = _recompute_live_package_binding(
            repo_root=repo_root, package_id=req.delivery_package_id
        )
    except _Stage8OBlocked as exc:
        return _deny(
            error_code=exc.code,
            error_detail=exc.detail,
            delivery_package_id=req.delivery_package_id,
            authorization_request_id=authorization_request_id,
        )
    if live_content_hash != req.package_content_hash:
        return _deny(
            error_code=ERR_PACKAGE_CONFLICT,
            error_detail="package content hash no longer matches authorization binding",
            delivery_package_id=req.delivery_package_id,
            authorization_request_id=authorization_request_id,
        )
    if live_artifact_sha != req.artifact_sha256:
        return _deny(
            error_code=ERR_ARTIFACT_SHA_MISMATCH,
            error_detail="artifact hash no longer matches authorization binding",
            delivery_package_id=req.delivery_package_id,
            authorization_request_id=authorization_request_id,
        )

    # Idempotent exact replay (same request + same operator => prior decision).
    # Decision events are keyed by authorization_request_id; replay is found by
    # the prior decision id recorded on the matching decision event.
    dec_id = auth_decision_id_fn(
        authorization_request_id=authorization_request_id,
        decision=AUTH_APPROVED,
        operator_id=operator_id,
        rejection_reason=None,
    )
    existing_dec = None
    for e in events_for_authorization(ledger_path=ledger, authorization_request_id=authorization_request_id):
        if e["event_type"] == EVT_AUTH_APPROVED and e.get("authorization_decision_id") == dec_id:
            existing_dec = e
            break
    if existing_dec is not None:
        return Stage8OServiceResult(
            ok=True,
            delivery_package_id=req.delivery_package_id,
            authorization_request_id=authorization_request_id,
            authorization_status=AUTH_APPROVED,
            authorization_decision_id=dec_id,
            package_content_hash=req.package_content_hash,
            artifact_sha256=req.artifact_sha256,
            replayed=True,
        )
    # A prior decision exists but with different semantics => conflict (fail closed).
    if status != AUTH_PENDING:
        if status == AUTH_REJECTED:
            return _deny(error_code=ERR_AUTH_REJECTED, error_detail="request was rejected", authorization_request_id=authorization_request_id)
        if status == AUTH_CANCELLED:
            return _deny(error_code=ERR_AUTH_CANCELLED, error_detail="request was cancelled", authorization_request_id=authorization_request_id)
        if status == AUTH_EXPIRED:
            return _deny(error_code=ERR_AUTH_EXPIRED, error_detail="request expired", authorization_request_id=authorization_request_id)
        return _deny(error_code=ERR_AUTH_ALREADY_DECIDED, error_detail=f"request already decided ({status})", authorization_request_id=authorization_request_id)

    dec = ManualDeliveryAuthorizationDecision(
        schema_version=AUTH_DECISION_SCHEMA_VERSION,
        authorization_decision_id=dec_id,
        authorization_request_id=authorization_request_id,
        delivery_package_id=req.delivery_package_id,
        package_content_hash=req.package_content_hash,
        decision=AUTH_APPROVED,
        operator_id=operator_id,
        rejection_reason=None,
        approval_note=None,
        decision_recorded_at=recorded_at,
        external_delivery_executed_by_scos=False,
        automation_allowed=False,
    )
    append_delivery_event(
        ledger_path=ledger,
        event_type=EVT_AUTH_APPROVED,
        subject_id=authorization_request_id,
        completion_evidence_id=contract.completion_evidence_id,
        artifact_sha256=contract.artifact_sha256,
        operator_id=operator_id,
        resulting_status=AUTH_APPROVED,
        reason="manual delivery authorized (explicit operator decision; no transport)",
        recorded_at=recorded_at,
        package_id=req.delivery_package_id,
        package_content_hash=req.package_content_hash,
        authorization_request_id=authorization_request_id,
        authorization_decision_id=dec_id,
        record_payload=dec.to_dict(),
    )
    return Stage8OServiceResult(
        ok=True,
        delivery_package_id=req.delivery_package_id,
        authorization_request_id=authorization_request_id,
        authorization_status=AUTH_APPROVED,
        authorization_decision_id=dec_id,
        package_content_hash=req.package_content_hash,
        artifact_sha256=req.artifact_sha256,
        safe_recipient_reference=req.safe_recipient_reference,
        allowed_manual_delivery_method=req.allowed_manual_delivery_method,
    )


def reject_manual_delivery(
    *,
    repo_root: Any,
    authorization_request_id: str,
    operator_id: str,
    reason: str,
    recorded_at: str,
) -> Stage8OServiceResult:
    if not str(operator_id or "").strip():
        return _deny(error_code=ERR_MISSING_OPERATOR_ID, error_detail="operator_id is required")
    if not str(reason or "").strip():
        return _deny(error_code=ERR_MISSING_REASON, error_detail="rejection reason is required",
                     authorization_request_id=authorization_request_id)
    reason_safe = _immutable_text("rejection_reason", reason, required=True, max_len=512)
    req, status = _load_auth_request(repo_root, authorization_request_id)
    if req is None:
        return _deny(error_code=ERR_AUTH_NOT_FOUND, error_detail="authorization request not found")
    ledger = delivery_ledger_path(repo_root)
    # Reverify the LIVE package binding before any decision (fail closed on drift).
    try:
        contract, _live_content_hash, _live_artifact_sha = _recompute_live_package_binding(
            repo_root=repo_root, package_id=req.delivery_package_id
        )
    except _Stage8OBlocked as exc:
        return _deny(
            error_code=exc.code,
            error_detail=exc.detail,
            delivery_package_id=req.delivery_package_id,
            authorization_request_id=authorization_request_id,
        )
    dec_id = auth_decision_id_fn(
        authorization_request_id=authorization_request_id,
        decision=AUTH_REJECTED,
        operator_id=operator_id,
        rejection_reason=reason_safe,
    )
    # Exact replay => prior identical rejection (decision events are keyed by
    # authorization_request_id; match the prior decision id on the event).
    existing_dec = None
    for e in events_for_authorization(ledger_path=ledger, authorization_request_id=authorization_request_id):
        if e["event_type"] == EVT_AUTH_REJECTED and e.get("authorization_decision_id") == dec_id:
            existing_dec = e
            break
    if existing_dec is not None:
        return Stage8OServiceResult(
            ok=True,
            delivery_package_id=req.delivery_package_id,
            authorization_request_id=authorization_request_id,
            authorization_status=AUTH_REJECTED,
            authorization_decision_id=dec_id,
            package_content_hash=req.package_content_hash,
            artifact_sha256=req.artifact_sha256,
            replayed=True,
        )
    # Prior decision with different semantics => conflict (fail closed).
    if status != AUTH_PENDING:
        return _deny(error_code=ERR_AUTH_ALREADY_DECIDED, error_detail=f"request already decided ({status})", authorization_request_id=authorization_request_id)

    dec = ManualDeliveryAuthorizationDecision(
        schema_version=AUTH_DECISION_SCHEMA_VERSION,
        authorization_decision_id=dec_id,
        authorization_request_id=authorization_request_id,
        delivery_package_id=req.delivery_package_id,
        package_content_hash=req.package_content_hash,
        decision=AUTH_REJECTED,
        operator_id=operator_id,
        rejection_reason=reason_safe,
        approval_note=None,
        decision_recorded_at=recorded_at,
        external_delivery_executed_by_scos=False,
        automation_allowed=False,
    )
    append_delivery_event(
        ledger_path=ledger,
        event_type=EVT_AUTH_REJECTED,
        subject_id=authorization_request_id,
        completion_evidence_id=contract.completion_evidence_id if contract else req.delivery_package_id,
        artifact_sha256=req.artifact_sha256,
        operator_id=operator_id,
        resulting_status=AUTH_REJECTED,
        reason=f"manual delivery rejected: {reason_safe}",
        recorded_at=recorded_at,
        package_id=req.delivery_package_id,
        package_content_hash=req.package_content_hash,
        authorization_request_id=authorization_request_id,
        authorization_decision_id=dec_id,
        record_payload=dec.to_dict(),
    )
    return Stage8OServiceResult(
        ok=True,
        delivery_package_id=req.delivery_package_id,
        authorization_request_id=authorization_request_id,
        authorization_status=AUTH_REJECTED,
        authorization_decision_id=dec_id,
        package_content_hash=req.package_content_hash,
        artifact_sha256=req.artifact_sha256,
        safe_recipient_reference=req.safe_recipient_reference,
        allowed_manual_delivery_method=req.allowed_manual_delivery_method,
    )


# ---------------------------------------------------------------------------
# BOUNDARY C — Actual manual delivery record
# ---------------------------------------------------------------------------
def record_actual_manual_delivery(
    *,
    repo_root: Any,
    authorization_request_id: str,
    operator_id: str,
    delivery_method: str,
    recipient_reference: str,
    human_delivery_confirmation: bool,
    recorded_at: str,
    external_evidence_reference: str = "",
    operator_note: str = "",
) -> Stage8OServiceResult:
    if not str(operator_id or "").strip():
        return _deny(error_code=ERR_MISSING_OPERATOR_ID, error_detail="operator_id is required")
    if not human_delivery_confirmation:
        return _deny(error_code=ERR_MISSING_CONFIRMATION, error_detail="explicit human-delivery confirmation required")
    if delivery_method not in ALLOWED_DELIVERY_METHODS:
        return _deny(error_code=ERR_INVALID_METHOD, error_detail="unsupported delivery method")
    try:
        recipient = _safe_recipient_reference(recipient_reference)
    except ValueError as exc:
        return _deny(error_code=ERR_UNSAFE_RECIPIENT, error_detail=str(exc))
    if not recipient:
        return _deny(error_code=ERR_MISSING_RECIPIENT, error_detail="recipient reference required")
    try:
        ext_ref = _safe_external_evidence_reference(external_evidence_reference)
    except ValueError as exc:
        return _deny(error_code=ERR_UNSAFE_RECIPIENT, error_detail=str(exc))
    note = _immutable_text("operator_note", operator_note, required=False, max_len=512)

    req, status = _load_auth_request(repo_root, authorization_request_id)
    if req is None:
        return _deny(error_code=ERR_AUTH_NOT_FOUND, error_detail="authorization request not found")
    if status != AUTH_APPROVED:
        if status == AUTH_REJECTED:
            return _deny(error_code=ERR_AUTH_REJECTED, error_detail="authorization was rejected; no delivery record", authorization_request_id=authorization_request_id)
        if status == AUTH_EXPIRED:
            return _deny(error_code=ERR_AUTH_EXPIRED, error_detail="authorization expired; no delivery record", authorization_request_id=authorization_request_id)
        if status == AUTH_CANCELLED:
            return _deny(error_code=ERR_AUTH_CANCELLED, error_detail="authorization cancelled; no delivery record", authorization_request_id=authorization_request_id)
        return _deny(error_code=ERR_DELIVERY_NOT_AUTHORIZED, error_detail="authorization is not APPROVED_FOR_MANUAL_DELIVERY", authorization_request_id=authorization_request_id)

    ledger = delivery_ledger_path(repo_root)
    # Reverify the LIVE package binding before recording (fail closed on drift).
    try:
        contract, live_content_hash, live_artifact_sha = _recompute_live_package_binding(
            repo_root=repo_root, package_id=req.delivery_package_id
        )
    except _Stage8OBlocked as exc:
        return _deny(
            error_code=exc.code,
            error_detail=exc.detail,
            delivery_package_id=req.delivery_package_id,
            authorization_request_id=authorization_request_id,
        )
    if live_content_hash != req.package_content_hash:
        return _deny(
            error_code=ERR_PACKAGE_CONFLICT,
            error_detail="package drift; authorization invalid",
            delivery_package_id=req.delivery_package_id,
            authorization_request_id=authorization_request_id,
        )
    if live_artifact_sha != req.artifact_sha256:
        return _deny(
            error_code=ERR_ARTIFACT_SHA_MISMATCH,
            error_detail="artifact drift; authorization invalid",
            delivery_package_id=req.delivery_package_id,
            authorization_request_id=authorization_request_id,
        )
    if req.safe_recipient_reference != recipient:
        return _deny(error_code=ERR_DELIVERY_CONFLICT, error_detail="recipient reference mismatch", delivery_package_id=req.delivery_package_id, authorization_request_id=authorization_request_id)
    if req.allowed_manual_delivery_method != delivery_method:
        return _deny(error_code=ERR_DELIVERY_CONFLICT, error_detail="delivery method mismatch", delivery_package_id=req.delivery_package_id, authorization_request_id=authorization_request_id)

    # Find the decision id for this approved request.
    dec_id = None
    for e in events_for_authorization(ledger_path=ledger, authorization_request_id=authorization_request_id):
        if e["event_type"] == EVT_AUTH_APPROVED:
            dec_id = e["authorization_decision_id"]
    if not dec_id:
        return _deny(error_code=ERR_AUTH_NOT_FOUND, error_detail="authorization decision not found", authorization_request_id=authorization_request_id)

    rec_id = actual_delivery_record_id(
        authorization_decision_id=dec_id,
        package_id=contract.delivery_package_id,
        package_content_hash=contract.package_content_hash,
        artifact_sha256=contract.artifact_sha256,
        recipient_reference=recipient,
        method=delivery_method,
        operator_id=operator_id,
        human_confirmation=True,
        external_evidence_reference=ext_ref,
    )
    # Idempotent replay.
    existing_rec = _find_event(ledger, EVT_DELIVERY_RECORDED, rec_id)
    if existing_rec is not None:
        rec = ActualManualDeliveryRecord(**existing_rec["record"])
        return Stage8OServiceResult(
            ok=True,
            delivery_package_id=rec.delivery_package_id,
            authorization_request_id=authorization_request_id,
            authorization_decision_id=rec.authorization_decision_id,
            delivery_record_id=rec_id,
            delivery_status=rec.delivery_status,
            package_content_hash=rec.package_content_hash,
            artifact_sha256=rec.artifact_sha256,
            safe_recipient_reference=rec.safe_recipient_reference,
            allowed_manual_delivery_method=rec.manual_delivery_method,
            manual_delivery_method=rec.manual_delivery_method,
            operator_id=rec.operator_id,
            external_evidence_reference=rec.external_evidence_reference,
            manual_delivery_performed=rec.manual_delivery_performed,
            external_delivery_executed_by_scos=rec.external_delivery_executed_by_scos,
            delivery_authorized=False,
            delivery_performed=False,
            customer_receipt_confirmed=rec.customer_receipt_confirmed,
            customer_acceptance_recorded=rec.customer_acceptance_recorded,
            publishing_performed=rec.publishing_performed,
            invoice_state_changed=rec.invoice_state_changed,
            payment_state_changed=rec.payment_state_changed,
            automation_allowed=rec.automation_allowed,
            replayed=True,
        )

    record = ActualManualDeliveryRecord(
        schema_version=DELIVERY_RECORD_SCHEMA_VERSION,
        manual_delivery_record_id=rec_id,
        authorization_request_id=authorization_request_id,
        authorization_decision_id=dec_id,
        delivery_package_id=contract.delivery_package_id,
        package_content_hash=contract.package_content_hash,
        completion_evidence_id=contract.completion_evidence_id,
        artifact_sha256=contract.artifact_sha256,
        project_id=contract.project_id,
        safe_recipient_reference=recipient,
        manual_delivery_method=delivery_method,
        operator_id=operator_id,
        human_delivery_confirmation=True,
        delivery_recorded_at=recorded_at,
        external_evidence_reference=ext_ref,
        operator_note=note,
        delivery_status=DEL_DELIVERED_MANUALLY,
        manual_delivery_performed=True,
        external_delivery_executed_by_scos=False,
        customer_receipt_confirmed=False,
        customer_acceptance_recorded=False,
        publishing_performed=False,
        invoice_state_changed=False,
        payment_state_changed=False,
        automation_allowed=False,
    )
    append_delivery_event(
        ledger_path=ledger,
        event_type=EVT_DELIVERY_RECORDED,
        subject_id=rec_id,
        completion_evidence_id=contract.completion_evidence_id,
        artifact_sha256=contract.artifact_sha256,
        operator_id=operator_id,
        resulting_status=DEL_DELIVERED_MANUALLY,
        reason="operator asserts human performed delivery outside SCOS",
        recorded_at=recorded_at,
        package_id=contract.delivery_package_id,
        package_content_hash=contract.package_content_hash,
        authorization_request_id=authorization_request_id,
        authorization_decision_id=dec_id,
        delivery_record_id=rec_id,
        record_payload=record.to_dict(),
    )
    return Stage8OServiceResult(
        ok=True,
        delivery_package_id=contract.delivery_package_id,
        authorization_request_id=authorization_request_id,
        authorization_decision_id=dec_id,
        delivery_record_id=rec_id,
        delivery_status=DEL_DELIVERED_MANUALLY,
        package_content_hash=contract.package_content_hash,
        artifact_sha256=contract.artifact_sha256,
        safe_recipient_reference=record.safe_recipient_reference,
        allowed_manual_delivery_method=record.manual_delivery_method,
        manual_delivery_method=record.manual_delivery_method,
        operator_id=record.operator_id,
        external_evidence_reference=record.external_evidence_reference,
        manual_delivery_performed=record.manual_delivery_performed,
        external_delivery_executed_by_scos=record.external_delivery_executed_by_scos,
        delivery_authorized=False,
        delivery_performed=False,
        customer_receipt_confirmed=record.customer_receipt_confirmed,
        customer_acceptance_recorded=record.customer_acceptance_recorded,
        publishing_performed=record.publishing_performed,
        invoice_state_changed=record.invoice_state_changed,
        payment_state_changed=record.payment_state_changed,
        automation_allowed=record.automation_allowed,
    )


def inspect_actual_manual_delivery(
    *, repo_root: Any, delivery_record_id: str
) -> Stage8OServiceResult:
    ledger = delivery_ledger_path(repo_root)
    ev = _find_event(ledger, EVT_DELIVERY_RECORDED, delivery_record_id)
    if ev is None:
        return _deny(error_code=ERR_PACKAGE_NOT_FOUND, error_detail="delivery record not found")
    rec = ActualManualDeliveryRecord(**ev["record"])
    return Stage8OServiceResult(
        ok=True,
        delivery_record_id=delivery_record_id,
        delivery_status=rec.delivery_status,
        delivery_package_id=rec.delivery_package_id,
        authorization_request_id=rec.authorization_request_id,
        authorization_decision_id=rec.authorization_decision_id,
        package_content_hash=rec.package_content_hash,
        artifact_sha256=rec.artifact_sha256,
    )


def list_delivery_events(*, repo_root: Any) -> tuple[dict[str, Any], ...]:
    return read_delivery_events(ledger_path=delivery_ledger_path(repo_root))
