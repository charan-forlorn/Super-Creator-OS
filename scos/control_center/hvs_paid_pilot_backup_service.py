"""SCOS Cohort 10H — delivery backup service (master §9.3).

Creates one SCOS-owned immutable backup copy of an approved delivery package
in a SEPARATE logical root from the active package. The backup is finalized
atomically, verified content-equivalent (same SHA-256), and produces a
read-only verification receipt.

Boundaries:
  * backup root is server-controlled (different logical dir under the gitignored
    runtime tree; never an absolute path supplied by the browser)
  * no automatic deletion
  * no network, no subprocess
  * package hash is computed AFTER finalization and must equal the backup hash
  * conflicting/partial state never appears as ready

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

from scos.control_center.hvs_paid_pilot_delivery_models import (  # noqa: E402
    DELIVERY_BACKUP_READY,
    DELIVERY_PACKAGE_CORRUPT,
    DELIVERY_SCHEMA_VERSION,
    DeliveryBackupReceipt,
    stable_backup_id,
)

# Logical roots (server-resolved). Both live under the gitignored runtime tree
# but in DIFFERENT directories so a single logical root failure does not take
# out both copies. This is single-physical-disk protection (truthfully reported).
DEFAULT_PACKAGE_ROOT_RELATIVE = "memory/runtime/control-center/paid-pilot-packages"
DEFAULT_BACKUP_ROOT_RELATIVE = "memory/runtime/control-center/paid-pilot-backups"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_zip_name(name: str) -> str:
    """Reject path traversal / absolute components in zip member names."""
    if not name:
        raise ValueError("empty zip member name")
    if name.startswith("/") or name.startswith("\\") or ".." in name.split("/"):
        raise ValueError("unsafe zip member name")
    return name


def read_package_zip(*, package_path: Path) -> tuple[bytes, str]:
    """Read a package zip and return (bytes, sha256). Validates member names."""
    if not package_path.is_file() or package_path.is_symlink():
        raise ValueError("package is not a regular file")
    data = package_path.read_bytes()
    with zipfile.ZipFile(package_path) as zf:
        for info in zf.infolist():
            _safe_zip_name(info.filename)
            if info.is_dir():
                continue
            # Detect symlinks/devices via the POSIX mode stored in the
            # high 16 bits of external_attr (0o120000 = symlink).
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000 or stat.S_ISLNK(mode):
                raise ValueError("archive contains symlink member")
    return data, _sha256_bytes(data)


def finalize_backup(
    *,
    package_path: Path,
    backup_root: Path,
    delivery_id: str,
    package_sha256: str,
    created_at: str,
    protection_class: str = "SINGLE_DISK_DUAL_ROOT_NO_CLOUD",
) -> DeliveryBackupReceipt:
    """Create the immutable backup copy and verify content equality.

    Raises ValueError on any integrity mismatch (caller maps to
    DELIVERY_PACKAGE_CORRUPT). Never silently succeeds.
    """
    data, computed_sha = read_package_zip(package_path=package_path)
    if computed_sha.lower() != package_sha256.lower():
        raise ValueError("package hash mismatch before backup")

    backup_root = Path(backup_root)
    backup_root.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_zip_name(delivery_id + ".zip")
    target = backup_root / safe_name

    # Atomic write: temp file then replace.
    tmp = backup_root / (safe_name + f".tmp.{__import__('os').getpid()}")
    tmp.write_bytes(data)
    verified = _sha256_file(tmp)
    if verified.lower() != package_sha256.lower():
        tmp.unlink(missing_ok=True)
        raise ValueError("backup hash mismatch after write")
    shutil.move(str(tmp), str(target))

    backup_id = stable_backup_id(package_id=delivery_id, package_sha256=package_sha256)
    return DeliveryBackupReceipt(
        backup_id=backup_id,
        package_id=delivery_id,
        package_sha256=package_sha256,
        backup_sha256=verified,
        created_at=created_at,
        protection_class=protection_class,
    )


def verify_backup(
    *,
    delivery_id: str,
    backup_root: Path,
    expected_package_sha256: str,
) -> tuple[bool, Optional[str]]:
    """Read-only verification of an existing backup copy.

    Returns (ok, backup_sha256). No mutation.
    """
    target = Path(backup_root) / (delivery_id + ".zip")
    if not target.is_file():
        return (False, None)
    try:
        _data, sha = read_package_zip(package_path=target)
    except (ValueError, OSError):
        return (False, None)
    return (sha.lower() == expected_package_sha256.lower(), sha)
