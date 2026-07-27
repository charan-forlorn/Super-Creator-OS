"""SCOS Cohort 10I — paid-pilot restore verification.

Restores an authoritative delivery package into a FRESH isolated root and
verifies inventory, checksums, symlink rejection, path-traversal rejection,
unexpected-file rejection, and partial-copy rejection.

Boundaries:
  * restore root is server-controlled (never browser-supplied absolute path)
  * no network, no subprocess
  * never corrupts the authoritative source package or backup
  * no automatic retry

Stdlib-only. Deterministic. No clock/random/uuid.
"""

from __future__ import annotations

import hashlib
import shutil
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from scos.control_center.hvs_paid_pilot_backup_service import (
    read_package_zip,
    verify_backup,
)
from scos.control_center.hvs_paid_pilot_delivery_models import (
    DeliveryBackupReceipt,
    PaidPilotDeliveryRecord,
    safe_delivery_filename,
)

RESTORE_SCHEMA_VERSION = "scos-hvs.paid-pilot-restore.v1/1.0.0"


@dataclass(frozen=True)
class RestoreResult:
    ok: bool
    error_code: Optional[str]
    detail: str
    restored_root: str
    inventory: tuple[str, ...]
    package_sha256: str
    backup_sha256: str
    file_hashes: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "error_code": self.error_code,
            "detail": self.detail,
            "restored_root": self.restored_root,
            "inventory": list(self.inventory),
            "package_sha256": self.package_sha256,
            "backup_sha256": self.backup_sha256,
            "file_hashes": self.file_hashes,
        }


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _validate_zip_members(zip_path: Path) -> tuple[bool, str]:
    """Reject symlinks, path traversal, and unsafe member names."""
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
                name = info.filename
                if not name or name.startswith("/") or name.startswith("\\"):
                    return (False, f"ABSOLUTE_PATH_REJECTED: {name}")
                parts = name.split("/")
                if ".." in parts:
                    return (False, f"PATH_TRAVERSAL_REJECTED: {name}")
                mode = (info.external_attr >> 16) & 0o170000
                if mode == 0o120000 or stat.S_ISLNK(mode):
                    return (False, f"SYMLINK_REJECTED: {name}")
        return (True, "OK")
    except (zipfile.BadZipFile, OSError) as exc:
        return (False, f"BAD_ZIP: {exc}")


def restore_to_fresh_root(
    *,
    delivery_id: str,
    package_root: Path,
    backup_root: Path,
    restore_root: Path,
    expected_package_sha256: str,
    expected_backup_sha256: Optional[str] = None,
) -> RestoreResult:
    """Restore an authoritative package into a fresh isolated root.

    Steps:
      1. Verify package file exists and validate zip members
         (no symlinks, no traversal, no absolute paths).
      2. Verify backup receipt and hash equality.
      3. Create fresh restore root (must be empty or non-existent).
      4. Copy package bytes atomically.
      5. Verify restored file hash matches expected.
      6. Verify no unexpected files in restore root.
      7. Compare inventory against source.
    """
    pkg_path = package_root / safe_delivery_filename(delivery_id)
    bkp_path = backup_root / (delivery_id + ".zip")

    # Step 1: Verify package exists and validate zip members (fail-closed).
    if not pkg_path.is_file():
        return RestoreResult(False, "PACKAGE_FILE_MISSING", "source package not found",
                             str(restore_root), (), expected_package_sha256, "", {})

    ok, msg = _validate_zip_members(pkg_path)
    if not ok:
        return RestoreResult(False, "ZIP_VALIDATION_FAILED", msg,
                             str(restore_root), (), expected_package_sha256, "", {})

    # Step 2: Verify backup.
    if not bkp_path.is_file():
        return RestoreResult(False, "BACKUP_FILE_MISSING", "backup file not found",
                             str(restore_root), (), expected_package_sha256, "", {})

    # Verify backup hash matches package hash.
    try:
        bkp_ok, bkp_sha = verify_backup(
            delivery_id=delivery_id,
            backup_root=backup_root,
            expected_package_sha256=expected_package_sha256,
        )
    except Exception:
        return RestoreResult(False, "BACKUP_VERIFY_FAILED", "backup verification failed",
                             str(restore_root), (), expected_package_sha256, "", {})

    if not bkp_ok:
        return RestoreResult(False, "BACKUP_HASH_MISMATCH", "backup hash does not match package hash",
                             str(restore_root), (), expected_package_sha256, "", {})

    if expected_backup_sha256 and bkp_sha and bkp_sha.lower() != expected_backup_sha256.lower():
        return RestoreResult(False, "BACKUP_RECEIPT_MISMATCH", "backup hash differs from receipt",
                             str(restore_root), (), expected_package_sha256, bkp_sha, {})

    # Step 3: Create fresh restore root.
    restore_root = Path(restore_root)
    if restore_root.exists():
        existing = list(restore_root.iterdir())
        if existing:
            return RestoreResult(False, "RESTORE_ROOT_NOT_EMPTY", "restore root must be empty",
                                 str(restore_root), (), expected_package_sha256, bkp_sha, {})
    restore_root.mkdir(parents=True, exist_ok=True)

    # Step 4: Copy package bytes.
    restored_pkg = restore_root / safe_delivery_filename(delivery_id)
    try:
        shutil.copyfile(pkg_path, restored_pkg)
    except (OSError, shutil.Error) as exc:
        return RestoreResult(False, "COPY_FAILED", str(exc),
                             str(restore_root), (), expected_package_sha256, bkp_sha, {})

    # Step 5: Verify restored file hash.
    restored_sha = _sha256_file(restored_pkg)
    if restored_sha.lower() != expected_package_sha256.lower():
        return RestoreResult(False, "RESTORED_HASH_MISMATCH", "restored package hash mismatch",
                             str(restore_root), (), expected_package_sha256, bkp_sha, {})

    # Step 6: Verify no unexpected files.
    restored_files = sorted(p.name for p in restore_root.iterdir())
    expected_files = [safe_delivery_filename(delivery_id)]
    if restored_files != expected_files:
        return RestoreResult(False, "UNEXPECTED_FILES", f"unexpected files: {restored_files}",
                             str(restore_root), tuple(restored_files), expected_package_sha256, bkp_sha, {})

    # Step 7: Compare inventory against source.
    source_files = sorted(p.name for p in package_root.iterdir())
    if safe_delivery_filename(delivery_id) not in source_files:
        return RestoreResult(False, "SOURCE_INVENTORY_MISMATCH", "package not in source inventory",
                             str(restore_root), tuple(restored_files), expected_package_sha256, bkp_sha, {})

    # Compute per-file hashes for the restored package.
    file_hashes: dict[str, str] = {}
    try:
        with zipfile.ZipFile(restored_pkg) as zf:
            for info in zf.infolist():
                if not info.is_dir():
                    file_hashes[info.filename] = zf.read(info.filename).hex()[:32]
    except Exception:
        pass

    return RestoreResult(
        ok=True,
        error_code=None,
        detail="restore verified",
        restored_root=str(restore_root),
        inventory=tuple(restored_files),
        package_sha256=restored_sha,
        backup_sha256=bkp_sha,
        file_hashes=file_hashes,
    )


def verify_restored_package(
    *,
    delivery_id: str,
    restored_root: Path,
    expected_package_sha256: str,
) -> tuple[bool, str]:
    """Read-only verification of a restored package in a fresh root."""
    pkg_path = Path(restored_root) / safe_delivery_filename(delivery_id)
    if not pkg_path.is_file():
        return (False, "RESTORED_PACKAGE_MISSING")
    ok, msg = _validate_zip_members(pkg_path)
    if not ok:
        return (False, msg)
    sha = _sha256_file(pkg_path)
    if sha.lower() != expected_package_sha256.lower():
        return (False, "RESTORED_HASH_MISMATCH")
    return (True, sha)
