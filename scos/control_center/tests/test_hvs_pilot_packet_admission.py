from __future__ import annotations

import json
from pathlib import Path

import pytest

from scos.control_center.hvs_pilot_packet_admission import admit_packet
from scos.control_center.hvs_pilot_roots import resolve_task_owned_roots, RootConfigInvalid

REAL_PACKET_SHA = "c4784164704988cd7ab6b20bd315c0e67d80b06aadf714a3a3427f4a92dc8c02"


def _make_inputs(tmp_path: Path) -> tuple[Path, Path]:
    """Create an approved-input root mirroring the real packet assets."""
    root = tmp_path / "approved-input"
    (root / "assets").mkdir(parents=True)
    (root / "evidence").mkdir(parents=True)
    # Identity evidence file the packet references.
    (root / "evidence" / "PILOT-2026-001-self-authorization.txt").write_text("identity evidence 2026-08-01T12:29:15Z\n", encoding="utf-8")
    assets = {
        "product-front.jpg": b"\xff\xd8\xff\xe0productfront",
        "customer-logo.png": b"\x89PNG\r\n\x1alogobytes",
        "promo-music-31s.mp3": b"ID3 mp3audio-bytes" * 4000,
    }
    for name, data in assets.items():
        (root / "assets" / name).write_bytes(data)
    return root, root / "assets"


def _packet(root: Path, *, sha_override=None) -> dict:
    return {
        "schema_version": "1.0.0",
        "packet_type": "SCOS_PILOT01_REAL_CUSTOMER_AUTHORIZATION",
        "pilot_id": "PILOT-2026-001",
        "customer_ref": "CUST-A1",
        "project_ref": "PILOT-2026-001-PROJ-01",
        "customer_identity_evidence_reference": "evidence/PILOT-2026-001-self-authorization.txt",
        "customer_identity_evidence_sha256": "9c48c0ee3d4d0abf58522fcc5045d8b0ad09dd695957b527d7d2bd0b87e6cc09",
        "operator_approval_timestamp": "2026-08-01T15:41:06Z",
        "project_identity": {
            "project_title": "โปรโมชันสินค้าเดือนสิงหาคม",
            "output_profile": "vertical_9_16",
            "duration": "30s",
        },
        "target_output_profile": "vertical_9_16",
        "approved_customer_assets": [
            {"asset_id": "asset-01", "safe_name": "product-front.jpg", "source_location_reference": "assets/product-front.jpg",
             "declared_purpose": "product", "source_classification": "OPERATOR_OWNED",
             "sha256": "69443c5d5c904a71932095a19a77e4468e419a0781f81ac5ee9291b501cb0145",
             "size_bytes": 17, "rights_declaration": "Owned", "privacy_classification": "STANDARD_COMMERCIAL"},
            {"asset_id": "asset-02", "safe_name": "customer-logo.png", "source_location_reference": "assets/customer-logo.png",
             "declared_purpose": "logo", "source_classification": "OPERATOR_OWNED",
             "sha256": "b548c619c8fe07dc87b36e04713866b8afff13751f30a560b3ba9399ddc165b4",
             "size_bytes": 13, "rights_declaration": "Owned", "privacy_classification": "STANDARD_COMMERCIAL"},
            {"asset_id": "asset-03", "safe_name": "promo-music-31s.mp3", "source_location_reference": "assets/promo-music-31s.mp3",
             "declared_purpose": "music", "source_classification": "OPERATOR_GENERATED",
             "sha256": "a1a78268158917a457eaeaf4f8da0ee42fbfbf150997f0693c12a3bdd9d9e53a",
             "size_bytes": 48000, "rights_declaration": "Owned", "privacy_classification": "STANDARD_COMMERCIAL"},
        ],
        "content_rights_declaration": {"asset_owner": "Owned", "identifiable_person": "No", "voice_used": "Not used", "music_used": "Owned", "font_policy": "OPEN_SOURCE_APPROVED"},
        "privacy": {"health_data": "No", "financial_data": "No", "government_identifiers": "No", "child_information": "No", "privacy_classification": "STANDARD_COMMERCIAL"},
        "delivery_method": "MANUAL_OPERATOR_HANDOFF_ONLY",
        "retention_requirement": "Retain customer assets for 30 days after operator handoff.",
        "external_action_restrictions": {"publishing": "NOT_AUTHORIZED", "upload": "NOT_AUTHORIZED", "external_delivery": "NOT_AUTHORIZED",
                                         "customer_notification": "NOT_AUTHORIZED", "deployment": "NOT_AUTHORIZED"},
        "required_packet_decisions": {"CUSTOMER_DATA_AUTHORIZED": True, "PUBLISHING_AUTHORIZED": False},
    }


def _write_packet(root: Path, packet: dict, name="authorization-packet.json") -> Path:
    p = root / name
    p.write_text(json.dumps(packet), encoding="utf-8")
    return p


def test_missing_packet_blocked_no_write(tmp_path: Path):
    root, _ = _make_inputs(tmp_path)
    res = admit_packet(approved_input_root=str(root), admission_store_path=str(tmp_path / "adm.json"),
                       audit_store_path=str(tmp_path / "audit.jsonl"), expected_sha256=REAL_PACKET_SHA,
                       environ={"SCOS_PILOT_PACKET_PATH": str(root / "does-not-exist.json")})
    assert res.ok is False
    assert res.error_code in ("PACKET_UNREADABLE", "PACKET_PATH_NOT_CONFIGURED", "PACKET_PATH_ESCAPE")
    assert not (tmp_path / "adm.json").exists()


def test_hash_mismatch_blocked_no_write(tmp_path: Path):
    root, _ = _make_inputs(tmp_path)
    _write_packet(root, _packet(root))
    res = admit_packet(approved_input_root=str(root), admission_store_path=str(tmp_path / "adm.json"),
                       audit_store_path=str(tmp_path / "audit.jsonl"), expected_sha256="0" * 64,
                       environ={"SCOS_PILOT_PACKET_PATH": str(root / "authorization-packet.json")})
    assert res.ok is False
    assert res.error_code == "PACKET_SHA256_MISMATCH"
    assert not (tmp_path / "adm.json").exists()


def test_valid_packet_admission_pass(tmp_path: Path):
    import hashlib
    root, _ = _make_inputs(tmp_path)
    # Recompute real hashes/sizes to match the fixture assets exactly.
    fixes = {}
    for a in _packet(root)["approved_customer_assets"]:
        data = (root / a["source_location_reference"]).read_bytes()
        fixes[a["safe_name"]] = (hashlib.sha256(data).hexdigest(), len(data))
    pkt = _packet(root)
    for a in pkt["approved_customer_assets"]:
        h, sz = fixes[a["safe_name"]]
        a["sha256"] = h
        a["size_bytes"] = sz
    # Fix identity evidence hash too.
    ev = (root / "evidence" / "PILOT-2026-001-self-authorization.txt").read_bytes()
    pkt["customer_identity_evidence_sha256"] = hashlib.sha256(ev).hexdigest()
    pp = _write_packet(root, pkt)
    # The expected SHA is the hash of the exact packet bytes we are admitting.
    expected = hashlib.sha256(pp.read_bytes()).hexdigest()
    res = admit_packet(approved_input_root=str(root), admission_store_path=str(tmp_path / "adm.json"),
                       audit_store_path=str(tmp_path / "audit.jsonl"), expected_sha256=expected,
                       environ={"SCOS_PILOT_PACKET_PATH": str(pp)})
    assert res.ok is True, res.detail
    assert res.projection["asset_count"] == 3
    assert res.projection["project_ref"] == "PILOT-2026-001-PROJ-01"
    # Browser-safe: no absolute path, no full secret hash.
    assert "C:/" not in json.dumps(res.projection) and "/Workspace" not in json.dumps(res.projection)
    assert (tmp_path / "adm.json").is_file()


def test_task_owned_roots_fail_closed_without_env(tmp_path: Path, monkeypatch):
    import os
    for k in list(os.environ):
        if k.startswith("SCOS_PILOT_"):
            monkeypatch.delenv(k, raising=False)
    with pytest.raises(RootConfigInvalid):
        resolve_task_owned_roots()
