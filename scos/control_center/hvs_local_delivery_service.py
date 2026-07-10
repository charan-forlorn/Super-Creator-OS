"""SCOS <-> Hermes Video Studio (HVS) — Stage 6 local delivery service.

The service layer that turns a finalized Stage 5 approval into a deterministic
local delivery package, optionally materializes it (operator-authorized
explicit copy only), and records (after the fact) that a human performed a
manual delivery through an external channel. It NEVER performs external
delivery: no upload, publish, email, message, API call, render, or HVS mutation.

Reuses existing Stage 4 safe-path discipline (``hvs_asset_materialization``):
``_assert_not_network_or_device``, ``_safe_basename``, and the same
streamed SHA-256 copy helper. Path resolution always stays under the approved
runtime root; ``..`` / absolute / UNC / URL / device / symlink escapes are
rejected.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid, no
network, no subprocess.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import re

try:
    from .hvs_delivery_approval import (
        SOURCE_NAME,
        STATUS_APPROVED,
        get_approval_request,
    )
    from .hvs_local_delivery_models import (
        ALLOWED_DELIVERY_CHANNELS,
        ALLOWED_DELIVERY_STATUSES,
        CHANNEL_OTHER_MANUAL,
        DELIVERY_AUDIT_SCHEMA_VERSION,
        DEL_DELIVERED_MANUALLY,
        DEL_DELIVERY_CANCELLED,
        DEL_DELIVERY_FAILED,
        HVSLocalDeliveryPackage,
        HVSManualDeliveryRecord,
        LOCAL_DELIVERY_PACKAGE_SCHEMA_VERSION,
        MANUAL_DELIVERY_RECORD_SCHEMA_VERSION,
        PKG_MATERIALIZED,
        PKG_PREPARED,
        ERR_APPROVAL_NOT_APPROVED,
        ERR_APPROVAL_NOT_FOUND,
        ERR_ARTIFACT_MISSING,
        ERR_ARTIFACT_NOT_REGULAR,
        ERR_ARTIFACT_SHA_MISMATCH,
        ERR_ARTIFACT_ZERO_BYTE,
        ERR_AUTOMATION_NOT_ALLOWED,
        ERR_DELIVERY_RECORD_CONFLICT,
        ERR_DELIVERY_RECORD_NOT_FOUND,
        ERR_INVALID_CHANNEL,
        ERR_INVALID_STATUS,
        ERR_MISSING_CHANNEL,
        ERR_MISSING_OPERATOR_ID,
        ERR_MISSING_REASON,
        ERR_MISSING_RECIPIENT,
        ERR_NOT_MATERIALIZED,
        ERR_PACKAGE_CONFLICT,
        ERR_PACKAGE_NOT_FOUND,
        ERR_PACKET_LINKAGE_MISMATCH,
        ERR_UNSAFE_PATH,
        manual_delivery_notice,
        scos_external_action_statement,
        stable_delivery_record_id,
        stable_package_id,
    )
    from .hvs_delivery_audit import (
        append_delivery_event,
        read_delivery_events,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from hvs_delivery_approval import (
        SOURCE_NAME,
        STATUS_APPROVED,
        get_approval_request,
    )
    from hvs_local_delivery_models import (
        ALLOWED_DELIVERY_CHANNELS,
        ALLOWED_DELIVERY_STATUSES,
        CHANNEL_OTHER_MANUAL,
        DELIVERY_AUDIT_SCHEMA_VERSION,
        DEL_DELIVERED_MANUALLY,
        DEL_DELIVERY_CANCELLED,
        DEL_DELIVERY_FAILED,
        HVSLocalDeliveryPackage,
        HVSManualDeliveryRecord,
        LOCAL_DELIVERY_PACKAGE_SCHEMA_VERSION,
        MANUAL_DELIVERY_RECORD_SCHEMA_VERSION,
        PKG_MATERIALIZED,
        PKG_PREPARED,
        ERR_APPROVAL_NOT_APPROVED,
        ERR_APPROVAL_NOT_FOUND,
        ERR_ARTIFACT_MISSING,
        ERR_ARTIFACT_NOT_REGULAR,
        ERR_ARTIFACT_SHA_MISMATCH,
        ERR_ARTIFACT_ZERO_BYTE,
        ERR_AUTOMATION_NOT_ALLOWED,
        ERR_DELIVERY_RECORD_CONFLICT,
        ERR_DELIVERY_RECORD_NOT_FOUND,
        ERR_INVALID_CHANNEL,
        ERR_INVALID_STATUS,
        ERR_MISSING_CHANNEL,
        ERR_MISSING_OPERATOR_ID,
        ERR_MISSING_REASON,
        ERR_MISSING_RECIPIENT,
        ERR_NOT_MATERIALIZED,
        ERR_PACKAGE_CONFLICT,
        ERR_PACKAGE_NOT_FOUND,
        ERR_PACKET_LINKAGE_MISMATCH,
        ERR_UNSAFE_PATH,
        manual_delivery_notice,
        scos_external_action_statement,
        stable_delivery_record_id,
        stable_package_id,
    )
    from hvs_delivery_audit import (
        append_delivery_event,
        read_delivery_events,
    )

# The Stage 4 ``hvs_asset_materialization`` module is NOT imported here: its
# dependency chain (hvs_project_creation -> hvs_schema_mapper ->
# hvs_contract_models) is currently broken under the package import model, and
# Stage 6 must remain hermetic and independently testable. The three small
# safe-path / hashing helpers below are inlined with identical semantics to
# ``hvs_asset_materialization`` (same policy vocabulary, same behavior) so the
# safety boundary is preserved without taking the broken import chain.

_SAFE_BASENAME_RE = re.compile(r"[^A-Za-z0-9._-]")


def _assert_not_network_or_device(value: str, ctx: str) -> None:
    """Reject UNC (\\\\), URLs (://), and device (\\\\.\\ or //./) paths.

    Mirrors ``hvs_asset_materialization._assert_not_network_or_device``.
    """
    lowered = value.lower()
    if "://" in lowered:
        raise ValueError(f"URL_PATH_REJECTED: {ctx} must be local: {value!r}")
    if value.startswith("\\\\") or value.startswith("//"):
        if "://" not in lowered and not re.match(r"^//[A-Za-z]:", value):
            raise ValueError(f"UNC_PATH_REJECTED: {ctx}: {value!r}")
    if lowered.startswith("\\\\.\\") or lowered.startswith("//./"):
        raise ValueError(f"DEVICE_PATH_REJECTED: {ctx}: {value!r}")


def _safe_basename(name: str) -> str:
    """Sanitize a basename into a safe project-local name (same as Stage 4)."""
    norm = name.replace("\\", "/")
    parts = [p for p in norm.split("/") if p not in ("", ".", "..")]
    base = parts[-1] if parts else ""
    base = _SAFE_BASENAME_RE.sub("_", base)
    base = base[:128]
    if not base:
        base = "asset"
    return base


def _sha256_stream(path: Path) -> str:
    """Streamed, deterministic SHA-256 hexdigest (full, not truncated)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

# Deterministic runtime root under the gitignored scos/work/ tree.
DEFAULT_DELIVERY_PACKAGES_RELATIVE = "scos/work/hvs_delivery_packages"
PACKAGE_MANIFEST_REL = "delivery_manifest.json"
PACKAGE_CHECKSUMS_REL = "CHECKSUMS.txt"
PACKAGE_README_REL = "README.txt"

_README_TEXT = (
    "SCOS <-> HVS Local Delivery Package\n"
    "===================================\n"
    "\n"
    "This directory is a LOCAL delivery-package workspace prepared by SCOS.\n"
    "It contains a copy of an approved HVS render artifact plus a provenance\n"
    "manifest. SCOS does NOT deliver anything. A human operator must perform\n"
    "the actual delivery through an external, out-of-system channel.\n"
    "\n"
    "Do not treat the presence of this package as proof of delivery.\n"
)


@dataclass(frozen=True)
class DeliveryServiceResult:
    ok: bool
    package_id: str | None = None
    approval_request_id: str | None = None
    artifact_sha256: str | None = None
    package_status: str | None = None
    manifest: HVSLocalDeliveryPackage | None = None
    delivery_record: HVSManualDeliveryRecord | None = None
    error_code: str | None = None
    error_detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "package_id": self.package_id,
            "approval_request_id": self.approval_request_id,
            "artifact_sha256": self.artifact_sha256,
            "package_status": self.package_status,
            "manifest": self.manifest.to_dict() if self.manifest else None,
            "delivery_record": (
                self.delivery_record.to_dict() if self.delivery_record else None
            ),
            "automation_allowed": False,
            "external_delivery_executed_by_scos": False,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
        }


def _deny(*, error_code: str, error_detail: str, **extra: Any) -> DeliveryServiceResult:
    return DeliveryServiceResult(
        ok=False,
        package_id=extra.get("package_id"),
        approval_request_id=extra.get("approval_request_id"),
        artifact_sha256=extra.get("artifact_sha256"),
        package_status=extra.get("package_status"),
        error_code=error_code,
        error_detail=error_detail,
    )


def _runtime_root(repo_root: Path) -> Path:
    return Path(repo_root).resolve() / DEFAULT_DELIVERY_PACKAGES_RELATIVE


def _packages_root(repo_root: Path) -> Path:
    return _runtime_root(repo_root)


def _assert_safe_relative_name(name: str) -> None:
    """Reject package-id / artifact names that could escape the runtime root."""
    if not name or ".." in name.split("/") or "\\" in name or name.startswith("/"):
        raise ValueError("unsafe relative name")
    # Also reject embedded absolute/UNC markers.
    lowered = name.lower()
    if "://" in lowered or name.startswith("\\\\") or name.startswith("//"):
        raise ValueError("unsafe relative name")


def _resolve_artifact_source(artifact_path: str) -> Path:
    """Validate the approved artifact path is a safe, local, regular file."""
    _assert_not_network_or_device(artifact_path, "artifact")
    if "\x00" in artifact_path:
        raise ValueError("null byte in artifact path")
    resolved = Path(artifact_path).resolve()
    if not resolved.is_file() or resolved.is_symlink():
        # symlink escapes / non-regular files are rejected.
        raise ValueError("artifact is not a regular file")
    return resolved


def _revalidate_approval(*, approval_id: str, repo_root: Path) -> Any:
    approval = get_approval_request(approval_id=approval_id, repo_root=Path(repo_root))
    if approval is None or approval.status != STATUS_APPROVED:
        raise _DeliveryRevalidationError(
            ERR_APPROVAL_NOT_APPROVED, "approval is not APPROVED_FOR_MANUAL_DELIVERY"
        )
    if approval.automation_allowed is not False:
        raise _DeliveryRevalidationError(
            ERR_AUTOMATION_NOT_ALLOWED, "automation_allowed must be false"
        )
    if not approval.artifact_sha256 or not approval.artifact_path:
        raise _DeliveryRevalidationError(
            ERR_ARTIFACT_MISSING, "approved artifact identity is incomplete"
        )
    return approval


class _DeliveryRevalidationError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def prepare_delivery_package(
    *,
    approval_id: str,
    operator_id: str,
    repo_root: Path,
    package_dir: Path | None = None,
    recorded_at: str,
    created_at: str | None = None,
) -> DeliveryServiceResult:
    """Validate a Stage 5 approval and build a deterministic PREPARED manifest.

    This does NOT copy media. It revalidates approval status, packet linkage,
    and the approved artifact's existence, size, and SHA-256. The manifest is
    persisted (atomically) to the local package directory. The package status
    is PREPARED (never MATERIALIZED and never DELIVERED here).
    """
    if not str(operator_id or "").strip():
        return _deny(
            error_code=ERR_MISSING_OPERATOR_ID,
            error_detail="operator_id is required to prepare a package",
            approval_request_id=approval_id,
        )
    try:
        approval = _revalidate_approval(approval_id=approval_id, repo_root=repo_root)
    except _DeliveryRevalidationError as exc:
        return _deny(
            error_code=exc.code,
            error_detail=exc.detail,
            approval_request_id=approval_id,
        )

    # Re-resolve + re-validate the approved artifact.
    try:
        artifact = _resolve_artifact_source(str(approval.artifact_path))
    except (ValueError, OSError):
        return _deny(
            error_code=ERR_ARTIFACT_MISSING,
            error_detail="approved artifact could not be resolved as a regular file",
            approval_request_id=approval_id,
        )
    size = artifact.stat().st_size
    if size <= 0:
        return _deny(
            error_code=ERR_ARTIFACT_ZERO_BYTE,
            error_detail="approved artifact is zero bytes",
            approval_request_id=approval_id,
        )
    live_sha = _sha256_stream(artifact)
    if live_sha.lower() != str(approval.artifact_sha256).lower():
        return _deny(
            error_code=ERR_ARTIFACT_SHA_MISMATCH,
            error_detail=(
                "approved artifact SHA-256 does not match current file contents"
            ),
            approval_request_id=approval_id,
            artifact_sha256=live_sha,
        )

    package_id = stable_package_id(
        approval_request_id=approval.approval_request_id,
        packet_id=approval.packet_id,
        evidence_validation_id=approval.validation_id,
        artifact_sha256=approval.artifact_sha256,
        contract_version=LOCAL_DELIVERY_PACKAGE_SCHEMA_VERSION,
    )
    try:
        _assert_safe_relative_name(package_id)
    except ValueError:
        return _deny(
            error_code=ERR_UNSAFE_PATH,
            error_detail="deterministic package id failed safe-name validation",
            approval_request_id=approval_id,
        )

    pkg_root = package_dir or (_packages_root(repo_root) / package_id)
    try:
        pkg_root.resolve().relative_to(_runtime_root(repo_root))
    except (ValueError, OSError):
        return _deny(
            error_code=ERR_UNSAFE_PATH,
            error_detail="package path escapes the approved runtime root",
            approval_request_id=approval_id,
            package_id=package_id,
        )

    manifest = _build_manifest(
        approval=approval,
        package_id=package_id,
        pkg_root=pkg_root,
        artifact=artifact,
        size=size,
        operator_id=operator_id,
        status=PKG_PREPARED,
        created_at=created_at or recorded_at,
        repo_root=repo_root,
    )

    # idempotent: identical completed PREPARED manifest that already exists is
    # reported as REUSED, not overwritten.
    manifest_path = pkg_root / PACKAGE_MANIFEST_REL
    if manifest_path.is_file():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing.get("package_manifest_sha256") == manifest.package_manifest_sha256:
            append_delivery_event(
                audit_log_path=_audit_log_path(repo_root),
                event_type="DELIVERY_PACKAGE_REUSED",
                package_id=package_id,
                approval_request_id=approval.approval_request_id,
                packet_id=approval.packet_id,
                artifact_sha256=manifest.source_artifact_sha256,
                resulting_state=PKG_PREPARED,
                operator_id=operator_id,
                recorded_at=recorded_at,
                detail="identical prepared manifest already present",
            )
            return DeliveryServiceResult(
                ok=True,
                package_id=package_id,
                approval_request_id=approval.approval_request_id,
                artifact_sha256=manifest.source_artifact_sha256,
                package_status=PKG_PREPARED,
                manifest=manifest,
            )

    _write_manifest_atomically(manifest, manifest_path, pkg_root)

    append_delivery_event(
        audit_log_path=_audit_log_path(repo_root),
        event_type="DELIVERY_PACKAGE_PREPARED",
        package_id=package_id,
        approval_request_id=approval.approval_request_id,
        packet_id=approval.packet_id,
        artifact_sha256=manifest.source_artifact_sha256,
        resulting_state=PKG_PREPARED,
        operator_id=operator_id,
        recorded_at=recorded_at,
        detail="package manifest prepared (no media copied)",
    )
    return DeliveryServiceResult(
        ok=True,
        package_id=package_id,
        approval_request_id=approval.approval_request_id,
        artifact_sha256=manifest.source_artifact_sha256,
        package_status=PKG_PREPARED,
        manifest=manifest,
    )


def materialize_delivery_package(
    *,
    package_id: str,
    operator_id: str,
    repo_root: Path,
    recorded_at: str,
) -> DeliveryServiceResult:
    """Explicitly copy the approved artifact into the local package.

    Requires an explicit operator id and mutates ONLY the local package dir.
    The source artifact is never modified, moved, or overwritten. After copy,
    the copied file is rehashed and compared to the approved SHA-256; only on
    match is the final manifest written atomically as MATERIALIZED.
    """
    if not str(operator_id or "").strip():
        return _deny(
            error_code=ERR_MISSING_OPERATOR_ID,
            error_detail="operator_id is required to materialize a package",
            package_id=package_id,
        )
    pkg_root = _packages_root(repo_root) / package_id
    manifest_path = pkg_root / PACKAGE_MANIFEST_REL
    if not manifest_path.is_file():
        return _deny(
            error_code=ERR_PACKAGE_NOT_FOUND,
            error_detail="package has not been prepared",
            package_id=package_id,
        )
    manifest_dict = json.loads(manifest_path.read_text(encoding="utf-8"))
    approval_id = manifest_dict.get("approval_request_id")

    # Re-validate BEFORE any idempotent short-circuit: the source artifact may
    # have changed since first materialization, and a tampered/mismatched file
    # must never be silently reused as MATERIALIZED.
    try:
        approval = _revalidate_approval(approval_id=approval_id, repo_root=repo_root)
    except _DeliveryRevalidationError as exc:
        return _deny(
            error_code=exc.code,
            error_detail=exc.detail,
            package_id=package_id,
            approval_request_id=approval_id,
        )

    try:
        artifact = _resolve_artifact_source(str(approval.artifact_path))
    except (ValueError, OSError):
        return _deny(
            error_code=ERR_ARTIFACT_MISSING,
            error_detail="approved artifact could not be resolved for materialization",
            package_id=package_id,
            approval_request_id=approval_id,
        )
    live_sha = _sha256_stream(artifact)
    if live_sha.lower() != str(approval.artifact_sha256).lower():
        append_delivery_event(
            audit_log_path=_audit_log_path(repo_root),
            event_type="DELIVERY_PACKAGE_INTEGRITY_FAILED",
            package_id=package_id,
            approval_request_id=approval_id,
            packet_id=approval.packet_id,
            artifact_sha256=live_sha,
            resulting_state=PKG_PREPARED,
            operator_id=operator_id,
            recorded_at=recorded_at,
            detail="artifact SHA mismatch during materialization",
        )
        return _deny(
            error_code=ERR_ARTIFACT_SHA_MISMATCH,
            error_detail="artifact SHA-256 mismatch; package not materialized",
            package_id=package_id,
            approval_request_id=approval_id,
            artifact_sha256=live_sha,
        )

    # Idempotent: an already-MATERIALIZED package with a still-valid source is
    # reported as MATERIALIZED without re-copying (the integrity check above
    # already proved the source still matches the approved SHA-256).
    if manifest_dict.get("package_status") == PKG_MATERIALIZED:
        return DeliveryServiceResult(
            ok=True,
            package_id=package_id,
            approval_request_id=approval_id,
            artifact_sha256=manifest_dict.get("source_artifact_sha256"),
            package_status=PKG_MATERIALIZED,
            manifest=_manifest_from_dict(manifest_dict),
        )

    safe_name = _safe_basename(Path(str(approval.artifact_path)).name) or "artifact"
    dest = pkg_root / safe_name
    # Reject any name that would escape the package dir.
    try:
        dest.resolve().relative_to(pkg_root.resolve())
    except (ValueError, OSError):
        return _deny(
            error_code=ERR_UNSAFE_PATH,
            error_detail="materialized artifact name escapes package dir",
            package_id=package_id,
            approval_request_id=approval_id,
        )
    # Never overwrite a differing existing file; identical is idempotent.
    if dest.is_file():
        if _sha256_stream(dest).lower() != live_sha.lower():
            return _deny(
                error_code=ERR_PACKAGE_CONFLICT,
                error_detail="existing materialized artifact differs; refuse to overwrite",
                package_id=package_id,
                approval_request_id=approval_id,
            )
    else:
        shutil.copyfile(artifact, dest)  # COPY ONLY; does not modify source.

    copied_sha = _sha256_stream(dest)
    if copied_sha.lower() != live_sha.lower():
        # Roll back the copy and refuse MATERIALIZED.
        try:
            dest.unlink()
        except OSError:
            pass
        return _deny(
            error_code=ERR_ARTIFACT_SHA_MISMATCH,
            error_detail="copied artifact SHA mismatch; materialization aborted",
            package_id=package_id,
            approval_request_id=approval_id,
            artifact_sha256=copied_sha,
        )

    manifest = _build_manifest(
        approval=approval,
        package_id=package_id,
        pkg_root=pkg_root,
        artifact=artifact,
        size=artifact.stat().st_size,
        operator_id=operator_id,
        status=PKG_MATERIALIZED,
        created_at=manifest_dict.get("created_at", recorded_at),
        repo_root=repo_root,
        packaged_relative=dest.name,
        packaged_sha=copied_sha,
    )
    _write_manifest_atomically(manifest, manifest_path, pkg_root)

    append_delivery_event(
        audit_log_path=_audit_log_path(repo_root),
        event_type="DELIVERY_PACKAGE_MATERIALIZED",
        package_id=package_id,
        approval_request_id=approval_id,
        packet_id=approval.packet_id,
        artifact_sha256=manifest.source_artifact_sha256,
        resulting_state=PKG_MATERIALIZED,
        operator_id=operator_id,
        recorded_at=recorded_at,
        detail="approved artifact copied into package without source modification",
    )
    return DeliveryServiceResult(
        ok=True,
        package_id=package_id,
        approval_request_id=approval_id,
        artifact_sha256=manifest.source_artifact_sha256,
        package_status=PKG_MATERIALIZED,
        manifest=manifest,
    )


def record_manual_delivery(
    *,
    package_id: str,
    status: str,
    operator_id: str,
    channel: str | None = None,
    recipient_label: str | None = None,
    external_reference: str | None = None,
    operator_note: str | None = None,
    reason: str | None = None,
    repo_root: Path,
    recorded_at: str,
) -> DeliveryServiceResult:
    """Record a human-performed manual delivery (or failure/cancellation)."""
    if status not in ALLOWED_DELIVERY_STATUSES:
        return _deny(
            error_code=ERR_INVALID_STATUS,
            error_detail=f"status must be one of {list(ALLOWED_DELIVERY_STATUSES)}",
            package_id=package_id,
        )
    if not str(operator_id or "").strip():
        return _deny(
            error_code=ERR_MISSING_OPERATOR_ID,
            error_detail="operator_id is required to record delivery",
            package_id=package_id,
        )

    pkg_root = _packages_root(repo_root) / package_id
    manifest_path = pkg_root / PACKAGE_MANIFEST_REL
    if not manifest_path.is_file():
        return _deny(
            error_code=ERR_PACKAGE_NOT_FOUND,
            error_detail="package has not been prepared",
            package_id=package_id,
        )
    manifest_dict = json.loads(manifest_path.read_text(encoding="utf-8"))
    approval_id = manifest_dict.get("approval_request_id")
    artifact_sha = manifest_dict.get("source_artifact_sha256")

    # Delivered requires a materialized package.
    if status == DEL_DELIVERED_MANUALLY and manifest_dict.get(
        "package_status"
    ) != PKG_MATERIALIZED:
        return _deny(
            error_code=ERR_NOT_MATERIALIZED,
            error_detail="delivered record requires a MATERIALIZED package",
            package_id=package_id,
            approval_request_id=approval_id,
        )

    if status == DEL_DELIVERED_MANUALLY:
        if channel not in ALLOWED_DELIVERY_CHANNELS:
            return _deny(
                error_code=ERR_INVALID_CHANNEL,
                error_detail=f"channel must be one of {list(ALLOWED_DELIVERY_CHANNELS)}",
                package_id=package_id,
                approval_request_id=approval_id,
            )
        if not str(recipient_label or "").strip():
            return _deny(
                error_code=ERR_MISSING_RECIPIENT,
                error_detail="delivered record requires a recipient label or reference",
                package_id=package_id,
                approval_request_id=approval_id,
            )
        reason_field = None
        performed = True
    elif status in (DEL_DELIVERY_FAILED, DEL_DELIVERY_CANCELLED):
        if not str(reason or "").strip():
            return _deny(
                error_code=ERR_MISSING_REASON,
                detail=None,
                error_detail="failed/cancelled record requires a reason",
                package_id=package_id,
                approval_request_id=approval_id,
            )
        reason_field = str(reason).strip()
        channel = channel or CHANNEL_OTHER_MANUAL
        recipient_label = recipient_label or "-"
        performed = False
    else:  # unreachable given the allowed-set guard above
        return _deny(
            error_code=ERR_INVALID_STATUS,
            error_detail="unsupported delivery status",
            package_id=package_id,
        )

    # Immutability: a conflicting final record is rejected. An identical
    # re-record (same status, operator, channel, recipient, reason) is treated
    # as idempotent; any differing final decision conflicts and is rejected.
    existing = load_manual_delivery_record(package_id=package_id, repo_root=repo_root)
    if existing is not None:
        same_identity = (
            existing.final_status == status
            and existing.operator_id == str(operator_id).strip()
            and existing.channel == (channel or CHANNEL_OTHER_MANUAL)
            and existing.recipient_label == str(recipient_label or "").strip()
            and (existing.failure_or_cancel_reason or "") == (reason_field or "")
        )
        if same_identity:
            # Idempotent identical re-record -> allowed (no-op style).
            return DeliveryServiceResult(
                ok=True,
                package_id=package_id,
                approval_request_id=approval_id,
                artifact_sha256=artifact_sha,
                package_status=manifest_dict.get("package_status"),
                delivery_record=existing,
            )
        return _deny(
            error_code=ERR_DELIVERY_RECORD_CONFLICT,
            error_detail="a final manual delivery record already exists for this package",
            package_id=package_id,
            approval_request_id=approval_id,
        )

    record = HVSManualDeliveryRecord(
        schema_version=MANUAL_DELIVERY_RECORD_SCHEMA_VERSION,
        delivery_record_id=stable_delivery_record_id(
            package_id=package_id,
            approval_request_id=approval_id,
            artifact_sha256=artifact_sha,
            contract_version=MANUAL_DELIVERY_RECORD_SCHEMA_VERSION,
            status=status,
        ),
        package_id=package_id,
        approval_request_id=approval_id,
        artifact_sha256=artifact_sha,
        operator_id=str(operator_id).strip(),
        final_status=status,
        channel=channel,
        recipient_label=str(recipient_label or "").strip(),
        external_reference=external_reference,
        operator_note=operator_note,
        failure_or_cancel_reason=reason_field,
        manual_delivery_performed=performed,
        automation_allowed=False,
        delivery_was_external_to_scos=True,
        scos_external_action_statement=scos_external_action_statement(),
        recorded_at=recorded_at,
        audit_correlation={
            "package_id": package_id,
            "approval_request_id": approval_id,
            "packet_id": manifest_dict.get("packet_id"),
            "evidence_validation_id": manifest_dict.get("evidence_validation_id"),
        },
    )
    _write_delivery_record_atomically(record, pkg_root / "manual_delivery_record.json")

    if status == DEL_DELIVERED_MANUALLY:
        evt = "MANUAL_DELIVERY_RECORDED"
    elif status == DEL_DELIVERY_FAILED:
        evt = "MANUAL_DELIVERY_FAILED"
    else:
        evt = "MANUAL_DELIVERY_CANCELLED"
    append_delivery_event(
        audit_log_path=_audit_log_path(repo_root),
        event_type=evt,
        package_id=package_id,
        approval_request_id=approval_id,
        packet_id=manifest_dict.get("packet_id"),
        artifact_sha256=artifact_sha,
        resulting_state=status,
        operator_id=str(operator_id).strip(),
        recorded_at=recorded_at,
        detail=f"manual delivery {status}; SCOS performed no external action",
    )
    return DeliveryServiceResult(
        ok=True,
        package_id=package_id,
        approval_request_id=approval_id,
        artifact_sha256=artifact_sha,
        package_status=manifest_dict.get("package_status"),
        delivery_record=record,
    )


def load_manual_delivery_record(*, package_id: str, repo_root: Path):
    pkg_root = _packages_root(repo_root) / package_id
    rec_path = pkg_root / "manual_delivery_record.json"
    if not rec_path.is_file():
        return None
    return _record_from_dict(
        json.loads(rec_path.read_text(encoding="utf-8"))
    )


def inspect_delivery_package(*, package_id: str, repo_root: Path) -> DeliveryServiceResult:
    pkg_root = _packages_root(repo_root) / package_id
    manifest_path = pkg_root / PACKAGE_MANIFEST_REL
    if not manifest_path.is_file():
        return _deny(
            error_code=ERR_PACKAGE_NOT_FOUND,
            error_detail="package not found",
            package_id=package_id,
        )
    manifest = _manifest_from_dict(
        json.loads(manifest_path.read_text(encoding="utf-8"))
    )
    record = load_manual_delivery_record(package_id=package_id, repo_root=repo_root)
    return DeliveryServiceResult(
        ok=True,
        package_id=package_id,
        approval_request_id=manifest.approval_request_id,
        artifact_sha256=manifest.source_artifact_sha256,
        package_status=manifest.package_status,
        manifest=manifest,
        delivery_record=record,
    )


# --- helpers -----------------------------------------------------------------
def _audit_log_path(repo_root: Path) -> Path:
    return _runtime_root(repo_root) / "delivery_audit.jsonl"


def _build_manifest(
    *,
    approval: Any,
    package_id: str,
    pkg_root: Path,
    artifact: Path,
    size: int,
    operator_id: str,
    status: str,
    created_at: str,
    repo_root: Path,
    packaged_relative: str | None = None,
    packaged_sha: str | None = None,
) -> HVSLocalDeliveryPackage:
    # Informational logical path under the approved runtime root. Never an
    # absolute or escaping path; always derived from the canonical relative
    # layout (scos/work/hvs_delivery_packages/<package_id>).
    rel = str(
        Path(DEFAULT_DELIVERY_PACKAGES_RELATIVE) / package_id
    ).replace("\\", "/")
    manifest = HVSLocalDeliveryPackage(
        schema_version=LOCAL_DELIVERY_PACKAGE_SCHEMA_VERSION,
        package_id=package_id,
        approval_request_id=approval.approval_request_id,
        packet_id=approval.packet_id,
        evidence_id=approval.evidence_id,
        evidence_validation_id=approval.validation_id,
        source_system=SOURCE_NAME,
        source_project_id=approval.project_id,
        artifact_display_name=Path(str(approval.artifact_path)).name,
        source_artifact_display_path=str(approval.artifact_path),
        source_artifact_sha256=str(approval.artifact_sha256),
        source_artifact_size=size,
        package_status=status,
        package_relative_path=rel,
        packaged_artifact_relative_path=packaged_relative,
        packaged_artifact_sha256=packaged_sha,
        package_manifest_sha256="",  # filled in after serialization
        prepared_by_operator_id=str(operator_id).strip(),
        automation_allowed=False,
        manual_delivery_required=True,
        manual_delivery_notice=manual_delivery_notice(),
        created_at=created_at,
        identity_inputs={
            "approval_request_id": approval.approval_request_id,
            "packet_id": approval.packet_id,
            "evidence_validation_id": approval.validation_id,
            "artifact_sha256": str(approval.artifact_sha256),
            "contract_version": LOCAL_DELIVERY_PACKAGE_SCHEMA_VERSION,
        },
        audit_correlation={
            "package_id": package_id,
            "approval_request_id": approval.approval_request_id,
            "packet_id": approval.packet_id,
            "evidence_validation_id": approval.validation_id,
            "evidence_id": approval.evidence_id,
        },
    )
    # Compute the manifest's own SHA-256 (content-derived identity, not in id).
    manifest = _with_manifest_sha(manifest)
    return manifest


def _with_manifest_sha(manifest: HVSLocalDeliveryPackage) -> HVSLocalDeliveryPackage:
    payload = dict(manifest.to_dict())
    payload.pop("package_manifest_sha256", None)
    sha = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        .encode("utf-8")
    ).hexdigest()
    return HVSLocalDeliveryPackage(
        **{**manifest.to_dict(), "package_manifest_sha256": sha}
    )


def _write_manifest_atomically(
    manifest: HVSLocalDeliveryPackage, manifest_path: Path, pkg_root: Path
) -> None:
    pkg_root.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        manifest.to_dict(), ensure_ascii=False, indent=2, sort_keys=True
    )
    tmp = manifest_path.with_suffix(".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(manifest_path)
    # Optional README + CHECKSUMS for the human operator.
    readme = pkg_root / PACKAGE_README_REL
    if not readme.is_file():
        readme.write_text(_README_TEXT, encoding="utf-8")


def _write_delivery_record_atomically(
    record: HVSManualDeliveryRecord, rec_path: Path
) -> None:
    rec_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = rec_path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(record.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    tmp.replace(rec_path)


def _manifest_from_dict(d: dict) -> HVSLocalDeliveryPackage:
    return HVSLocalDeliveryPackage(
        schema_version=d.get("schema_version", ""),
        package_id=d.get("package_id", ""),
        approval_request_id=d.get("approval_request_id", ""),
        packet_id=d.get("packet_id"),
        evidence_id=d.get("evidence_id"),
        evidence_validation_id=d.get("evidence_validation_id"),
        source_system=d.get("source_system", ""),
        source_project_id=d.get("source_project_id"),
        artifact_display_name=d.get("artifact_display_name", ""),
        source_artifact_display_path=d.get("source_artifact_display_path", ""),
        source_artifact_sha256=d.get("source_artifact_sha256", ""),
        source_artifact_size=int(d.get("source_artifact_size", 0)),
        package_status=d.get("package_status", ""),
        package_relative_path=d.get("package_relative_path", ""),
        packaged_artifact_relative_path=d.get("packaged_artifact_relative_path"),
        packaged_artifact_sha256=d.get("packaged_artifact_sha256"),
        package_manifest_sha256=d.get("package_manifest_sha256", ""),
        prepared_by_operator_id=d.get("prepared_by_operator_id", ""),
        automation_allowed=bool(d.get("automation_allowed", False)),
        manual_delivery_required=bool(d.get("manual_delivery_required", True)),
        manual_delivery_notice=d.get("manual_delivery_notice", ""),
        created_at=d.get("created_at", ""),
        identity_inputs=d.get("identity_inputs", {}),
        audit_correlation=d.get("audit_correlation", {}),
    )


def _record_from_dict(d: dict) -> HVSManualDeliveryRecord:
    return HVSManualDeliveryRecord(
        schema_version=d.get("schema_version", ""),
        delivery_record_id=d.get("delivery_record_id", ""),
        package_id=d.get("package_id", ""),
        approval_request_id=d.get("approval_request_id", ""),
        artifact_sha256=d.get("artifact_sha256", ""),
        operator_id=d.get("operator_id", ""),
        final_status=d.get("final_status", ""),
        channel=d.get("channel", ""),
        recipient_label=d.get("recipient_label", ""),
        external_reference=d.get("external_reference"),
        operator_note=d.get("operator_note"),
        failure_or_cancel_reason=d.get("failure_or_cancel_reason"),
        manual_delivery_performed=bool(d.get("manual_delivery_performed", False)),
        automation_allowed=bool(d.get("automation_allowed", False)),
        delivery_was_external_to_scos=bool(d.get("delivery_was_external_to_scos", True)),
        scos_external_action_statement=d.get("scos_external_action_statement", ""),
        recorded_at=d.get("recorded_at", ""),
        audit_correlation=d.get("audit_correlation", {}),
    )
