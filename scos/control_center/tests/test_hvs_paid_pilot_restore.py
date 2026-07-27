"""Focused backend tests — SCOS Cohort 10I paid-pilot restore verification.

Local, deterministic, hermetic. Exercises: restore to fresh root, inventory
validation, checksum validation, symlink rejection, path-traversal rejection,
unexpected-file rejection, partial-copy rejection, source/restore identity
comparison.
"""

from __future__ import annotations

import hashlib
import struct
import zipfile
from pathlib import Path

import pytest

from scos.control_center.hvs_paid_pilot_restore import (
    restore_to_fresh_root,
    verify_restored_package,
)
from scos.control_center.hvs_paid_pilot_delivery_models import (
    DeliveryBackupReceipt,
    safe_delivery_filename,
    stable_delivery_id,
)
from scos.control_center.hvs_paid_pilot_backup_service import (
    finalize_backup,
    read_package_zip,
)


@pytest.fixture
def setup_package(tmp_path: Path):
    """Create a source package + backup in isolated roots."""
    pkg_root = tmp_path / "pkg"
    bkp_root = tmp_path / "bkp"
    pkg_root.mkdir()
    bkp_root.mkdir()
    delivery_id = stable_delivery_id(
        project_id="p1", source_render_attempt_id="a1",
        artifact_sha256="x" * 64, qa_record_id="q1", media_profile="vertical_9_16",
    )
    pkg_path = pkg_root / safe_delivery_filename(delivery_id)
    with zipfile.ZipFile(pkg_path, "w") as zf:
        zf.writestr("final.mp4", b"SCOS-ARTIFACT-CONTENT-" * 100)
        zf.writestr("delivery_manifest.json", '{"delivery_id":"test"}')
    pkg_sha = read_package_zip(package_path=pkg_path)[1]
    receipt = finalize_backup(
        package_path=pkg_path, backup_root=bkp_root, delivery_id=delivery_id,
        package_sha256=pkg_sha, created_at="2026-07-21T00:00:00Z",
    )
    return delivery_id, pkg_root, bkp_root, pkg_sha, receipt


def test_restore_to_fresh_root(setup_package, tmp_path):
    delivery_id, pkg_root, bkp_root, pkg_sha, receipt = setup_package
    restore_root = tmp_path / "restore"
    result = restore_to_fresh_root(
        delivery_id=delivery_id,
        package_root=pkg_root,
        backup_root=bkp_root,
        restore_root=restore_root,
        expected_package_sha256=pkg_sha,
        expected_backup_sha256=receipt.backup_sha256,
    )
    assert result.ok is True
    assert result.package_sha256 == pkg_sha
    assert result.backup_sha256 == pkg_sha
    assert safe_delivery_filename(delivery_id) in result.inventory


def test_restore_rejects_non_empty_root(setup_package, tmp_path):
    delivery_id, pkg_root, bkp_root, pkg_sha, receipt = setup_package
    restore_root = tmp_path / "restore"
    restore_root.mkdir()
    (restore_root / "unexpected.txt").write_text("x")
    result = restore_to_fresh_root(
        delivery_id=delivery_id,
        package_root=pkg_root,
        backup_root=bkp_root,
        restore_root=restore_root,
        expected_package_sha256=pkg_sha,
    )
    assert result.ok is False
    assert result.error_code == "RESTORE_ROOT_NOT_EMPTY"


def test_restore_rejects_missing_package(setup_package, tmp_path):
    delivery_id, pkg_root, bkp_root, pkg_sha, receipt = setup_package
    # Remove the package file.
    (pkg_root / safe_delivery_filename(delivery_id)).unlink()
    restore_root = tmp_path / "restore"
    result = restore_to_fresh_root(
        delivery_id=delivery_id,
        package_root=pkg_root,
        backup_root=bkp_root,
        restore_root=restore_root,
        expected_package_sha256=pkg_sha,
    )
    assert result.ok is False
    assert result.error_code == "PACKAGE_FILE_MISSING"


def test_restore_rejects_hash_mismatch(setup_package, tmp_path):
    delivery_id, pkg_root, bkp_root, pkg_sha, receipt = setup_package
    restore_root = tmp_path / "restore"
    result = restore_to_fresh_root(
        delivery_id=delivery_id,
        package_root=pkg_root,
        backup_root=bkp_root,
        restore_root=restore_root,
        expected_package_sha256="b" * 64,  # wrong hash
    )
    assert result.ok is False
    assert result.error_code == "BACKUP_HASH_MISMATCH"


def test_restore_rejects_corrupted_backup(setup_package, tmp_path):
    delivery_id, pkg_root, bkp_root, pkg_sha, receipt = setup_package
    restore_root = tmp_path / "restore"
    # Corrupt the backup file.
    bkp_path = bkp_root / (delivery_id + ".zip")
    bkp_path.write_bytes(b"corrupted-backup-data")
    result = restore_to_fresh_root(
        delivery_id=delivery_id,
        package_root=pkg_root,
        backup_root=bkp_root,
        restore_root=restore_root,
        expected_package_sha256=pkg_sha,
    )
    assert result.ok is False
    assert result.error_code == "BACKUP_VERIFY_FAILED"


def test_restore_rejects_symlink_in_zip(tmp_path):
    """Symlinks in the package zip must be rejected.

    On Windows (no symlink privilege), we build a normal zip and flip the
    symlink bit in the central directory external_attr so the validator sees it.
    """
    pkg_root = tmp_path / "pkg"
    bkp_root = tmp_path / "bkp"
    pkg_root.mkdir()
    bkp_root.mkdir()
    delivery_id = stable_delivery_id(
        project_id="p1", source_render_attempt_id="a1",
        artifact_sha256="x" * 64, qa_record_id="q1", media_profile="vertical_9_16",
    )
    pkg_path = pkg_root / safe_delivery_filename(delivery_id)
    # Write a normal zip with two members.
    with zipfile.ZipFile(pkg_path, "w") as zf:
        zf.writestr("final.mp4", b"SCOS-ARTIFACT-CONTENT-" * 100)
        zf.writestr("symlink.txt", b"final.mp4")
    # Flip the symlink bit (0o120000) in the second central-directory entry's
    # external_attr (high 16 bits). We locate it by scanning for the member name
    # in the central directory (which appears after the local file headers).
    raw = bytearray(pkg_path.read_bytes())
    marker = b"symlink.txt"
    # Find the LAST occurrence of the name (central directory is at the end).
    idx = raw.rfind(marker)
    assert idx != -1, "member name not found"
    # The central directory signature PK\x01\x02 precedes the name. Search
    # backwards from the name for the most recent central-dir header.
    cd_start = raw.rfind(b"PK\x01\x02", 0, idx + 1)
    assert cd_start != -1, "central directory header not found"
    # Layout after signature: version(2) version(2) flags(2) method(2)
    #   time(2) date(2) crc(4) comp(4) uncomp(4) name_len(2) extra_len(2)
    #   comment_len(2) disk(2) int_attr(2) ext_attr(4) offset(4) name...
    ext_attr_off = cd_start + 2 * 10 + 2 * 3  # 20 + 6 = 26 bytes in
    # Current ext_attr (4 bytes, little-endian) -> set symlink mode (0o120000).
    cur = int.from_bytes(raw[ext_attr_off:ext_attr_off + 4], "little")
    cur = (cur & 0x0000FFFF) | 0o120000
    raw[ext_attr_off:ext_attr_off + 4] = cur.to_bytes(4, "little")
    pkg_path.write_bytes(bytes(raw))
    # Now the zip should be detected as having a symlink member.
    pkg_sha = hashlib.sha256(pkg_path.read_bytes()).hexdigest()
    restore_root = tmp_path / "restore"
    result = restore_to_fresh_root(
        delivery_id=delivery_id,
        package_root=pkg_root,
        backup_root=bkp_root,
        restore_root=restore_root,
        expected_package_sha256=pkg_sha,
    )
    assert result.ok is False
    assert result.error_code == "ZIP_VALIDATION_FAILED"


def test_restore_rejects_path_traversal(tmp_path):
    """Path traversal in the package zip must be rejected."""
    pkg_root = tmp_path / "pkg"
    bkp_root = tmp_path / "bkp"
    pkg_root.mkdir()
    bkp_root.mkdir()
    delivery_id = stable_delivery_id(
        project_id="p1", source_render_attempt_id="a1",
        artifact_sha256="x" * 64, qa_record_id="q1", media_profile="vertical_9_16",
    )
    pkg_path = pkg_root / safe_delivery_filename(delivery_id)
    with zipfile.ZipFile(pkg_path, "w") as zf:
        zf.writestr("final.mp4", b"SCOS-ARTIFACT-CONTENT-" * 100)
        zf.writestr("../../evil.txt", "malicious")
    # Compute hash from raw bytes (not via read_package_zip which validates).
    pkg_sha = hashlib.sha256(pkg_path.read_bytes()).hexdigest()
    restore_root = tmp_path / "restore"
    result = restore_to_fresh_root(
        delivery_id=delivery_id,
        package_root=pkg_root,
        backup_root=bkp_root,
        restore_root=restore_root,
        expected_package_sha256=pkg_sha,
    )
    assert result.ok is False
    assert result.error_code == "ZIP_VALIDATION_FAILED"


def test_verify_restored_package(setup_package, tmp_path):
    delivery_id, pkg_root, bkp_root, pkg_sha, receipt = setup_package
    restore_root = tmp_path / "restore"
    result = restore_to_fresh_root(
        delivery_id=delivery_id,
        package_root=pkg_root,
        backup_root=bkp_root,
        restore_root=restore_root,
        expected_package_sha256=pkg_sha,
    )
    assert result.ok is True
    ok, sha = verify_restored_package(
        delivery_id=delivery_id,
        restored_root=restore_root,
        expected_package_sha256=pkg_sha,
    )
    assert ok is True
    assert sha == pkg_sha


def test_verify_restored_package_missing(tmp_path):
    ok, msg = verify_restored_package(
        delivery_id="scos-hvs-pp-delivery-test",
        restored_root=tmp_path / "nonexistent",
        expected_package_sha256="a" * 64,
    )
    assert ok is False
    assert msg == "RESTORED_PACKAGE_MISSING"
