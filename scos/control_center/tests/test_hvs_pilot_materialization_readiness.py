from __future__ import annotations

import json
from pathlib import Path

from scos.control_center.hvs_pilot_materialization import build_materialization_state
from scos.control_center.hvs_pilot_identity import derive_canonical_id
from scos.control_center.hvs_pilot_render_readiness import evaluate_render_readiness


def _packet() -> dict:
    return {
        "pilot_id": "PILOT-2026-001",
        "customer_ref": "CUST-A1",
        "project_ref": "PILOT-2026-001-PROJ-01",
        "target_output_profile": "vertical_9_16",
        "delivery_method": "MANUAL_OPERATOR_HANDOFF_ONLY",
        "external_action_restrictions": {"publishing": "NOT_AUTHORIZED", "upload": "NOT_AUTHORIZED"},
        "project_identity": {"project_title": "Promo", "output_profile": "vertical_9_16", "duration_seconds": 30.974943},
        "content_rights_declaration": {"font_policy": "OPEN_SOURCE_APPROVED"},
        "approved_customer_assets": [
            {"asset_id": "asset-01", "safe_name": "product-front.jpg", "declared_purpose": "product", "rights_declaration": "Owned", "privacy_classification": "STANDARD_COMMERCIAL"},
            {"asset_id": "asset-02", "safe_name": "customer-logo.png", "declared_purpose": "logo", "rights_declaration": "Owned", "privacy_classification": "STANDARD_COMMERCIAL"},
            {"asset_id": "asset-03", "safe_name": "promo-music-31s.mp3", "declared_purpose": "music", "rights_declaration": "Owned", "privacy_classification": "STANDARD_COMMERCIAL"},
        ],
    }


def test_materialization_faithful(tmp_path: Path):
    pid = "spp-aa11bb22cc33"
    proj = build_materialization_state(
        canonical_internal_project_id=pid, external_project_ref="PILOT-2026-001-PROJ-01",
        pilot_id="PILOT-2026-001", customer_ref="CUST-A1", packet=_packet(),
        materialization_store_path=str(tmp_path / "mat.json"),
        contracts_dir=str(tmp_path / "_contracts"),
    )
    # No canary, no mock, no fixed 12s.
    assert proj["canary_label"] is None
    assert proj["mock_references"] == []
    assert proj["output_profile"] == "vertical_9_16"
    assert proj["dimensions"] == "1080x1920"
    assert proj["duration_seconds"] == 30.0
    assert proj["audio_duration_seconds"] == 30.974943
    assert proj["font_family"] == "Noto Sans Thai"
    assert set(proj["asset_safe_names"]) == {"product-front.jpg", "customer-logo.png", "promo-music-31s.mp3"}
    contract = json.loads((tmp_path / "_contracts" / f"{pid}.materialization.json").read_text(encoding="utf-8"))
    blob = json.dumps(contract)
    assert "Cohort 10D" not in blob and "mock://" not in blob and "12.0" not in blob
    assert contract["timeline"]["duration_seconds"] == 30.0
    assert contract["timeline"]["resolution"] == "1080x1920"


def test_render_readiness_ready(tmp_path: Path):
    pid = "spp-aa11bb22cc33"
    build_materialization_state(
        canonical_internal_project_id=pid, external_project_ref="PILOT-2026-001-PROJ-01",
        pilot_id="PILOT-2026-001", customer_ref="CUST-A1", packet=_packet(),
        materialization_store_path=str(tmp_path / "mat.json"),
        contracts_dir=str(tmp_path / "_contracts"),
    )
    # Admission record
    adm = tmp_path / "adm.json"
    adm.write_text(json.dumps({
        "schema_version": "x", "packet_sha256": "abc", "pilot_id": "PILOT-2026-001",
        "customer_ref": "CUST-A1", "project_ref": "PILOT-2026-001-PROJ-01", "asset_count": 3,
        "asset_safe_names": ["product-front.jpg", "customer-logo.png", "promo-music-31s.mp3"], "gates": [], "projection": {},
    }), encoding="utf-8")
    # HVS project dir + empty output root.
    hvs = tmp_path / "hvs-projects"
    (hvs / pid).mkdir(parents=True)
    out = tmp_path / "output"
    out.mkdir()
    res = evaluate_render_readiness(
        admission_store_path=str(adm), materialization_store_path=str(tmp_path / "mat.json"),
        hvs_projects_root=str(hvs), output_root=str(out),
        canonical_internal_project_id=pid, external_project_ref="PILOT-2026-001-PROJ-01",
    )
    assert res.ok is True, res.error_code
    assert res.state == "READY_FOR_RENDER"
    assert res.projection["render_action"] == "DISABLED_PRE_AUTHORIZATION"


def test_render_readiness_no_admission(tmp_path: Path):
    pid = "spp-aa11bb22cc33"
    res = evaluate_render_readiness(
        admission_store_path=str(tmp_path / "missing.json"), materialization_store_path=str(tmp_path / "missing.json"),
        hvs_projects_root=str(tmp_path / "hvs"), output_root=str(tmp_path / "out"),
        canonical_internal_project_id=pid, external_project_ref="PILOT-2026-001-PROJ-01",
    )
    assert res.ok is False
    assert res.error_code == "NO_ADMISSION"


def _seed_materialization_and_admission(tmp_path: Path, pid: str, project_ref: str):
    build_materialization_state(
        canonical_internal_project_id=pid, external_project_ref=project_ref,
        pilot_id="PILOT-2026-001", customer_ref="CUST-A1", packet=_packet(),
        materialization_store_path=str(tmp_path / "mat.json"),
        contracts_dir=str(tmp_path / "_contracts"),
    )
    adm = tmp_path / "adm.json"
    adm.write_text(json.dumps({
        "schema_version": "x", "packet_sha256": "abc", "pilot_id": "PILOT-2026-001",
        "customer_ref": "CUST-A1", "project_ref": project_ref, "asset_count": 3,
        "asset_safe_names": ["product-front.jpg", "customer-logo.png", "promo-music-31s.mp3"], "gates": [], "projection": {},
    }), encoding="utf-8")
    hvs = tmp_path / "hvs-projects"
    (hvs / pid).mkdir(parents=True)
    out = tmp_path / "output"
    out.mkdir()
    return adm, hvs, out


def test_render_readiness_derives_canonical_id_server_side(tmp_path: Path):
    """§6/§7: server derives canonical id from external ref; browser need not send it."""
    pid = derive_canonical_id("PILOT-2026-001-PROJ-01")
    adm, hvs, out = _seed_materialization_and_admission(tmp_path, pid, "PILOT-2026-001-PROJ-01")
    # No canonical_internal_project_id supplied -> derived from external ref.
    res = evaluate_render_readiness(
        admission_store_path=str(adm), materialization_store_path=str(tmp_path / "mat.json"),
        hvs_projects_root=str(hvs), output_root=str(out),
        canonical_internal_project_id="", external_project_ref="PILOT-2026-001-PROJ-01",
    )
    assert res.ok is True, res.error_code
    assert res.state == "READY_FOR_RENDER"
    assert res.projection["canonical_internal_project_id"] == pid


def test_render_readiness_valid_external_ref_ready(tmp_path: Path):
    """§7.4: valid external ref reaches READY_FOR_RENDER (identity continuity)."""
    pid = "spp-aa11bb22cc33"
    adm, hvs, out = _seed_materialization_and_admission(tmp_path, pid, "PILOT-2026-001-PROJ-01")
    res = evaluate_render_readiness(
        admission_store_path=str(adm), materialization_store_path=str(tmp_path / "mat.json"),
        hvs_projects_root=str(hvs), output_root=str(out),
        canonical_internal_project_id=pid, external_project_ref="PILOT-2026-001-PROJ-01",
    )
    assert res.ok is True
    assert res.projection["external_project_ref"] == "PILOT-2026-001-PROJ-01"
    assert res.projection["canonical_internal_project_id"] == pid


def test_render_readiness_missing_mapping_fails_closed(tmp_path: Path):
    """§7.5: external ref with no admission/mapping fails closed."""
    pid = "spp-aa11bb22cc33"
    build_materialization_state(
        canonical_internal_project_id=pid, external_project_ref="PILOT-2026-001-PROJ-01",
        pilot_id="PILOT-2026-001", customer_ref="CUST-A1", packet=_packet(),
        materialization_store_path=str(tmp_path / "mat.json"),
        contracts_dir=str(tmp_path / "_contracts"),
    )
    hvs = tmp_path / "hvs-projects"
    (hvs / pid).mkdir(parents=True)
    out = tmp_path / "output"
    out.mkdir()
    res = evaluate_render_readiness(
        admission_store_path=str(tmp_path / "missing.json"), materialization_store_path=str(tmp_path / "mat.json"),
        hvs_projects_root=str(hvs), output_root=str(out),
        canonical_internal_project_id="", external_project_ref="PILOT-2026-001-PROJ-01",
    )
    assert res.ok is False
    assert res.error_code == "NO_ADMISSION"


def test_render_readiness_conflicting_identity_fails_closed(tmp_path: Path):
    """§7.6: external ref / canonical id mismatch fails closed."""
    pid = derive_canonical_id("PILOT-2026-001-PROJ-01")
    adm, hvs, out = _seed_materialization_and_admission(tmp_path, pid, "PILOT-2026-001-PROJ-01")
    res = evaluate_render_readiness(
        admission_store_path=str(adm), materialization_store_path=str(tmp_path / "mat.json"),
        hvs_projects_root=str(hvs), output_root=str(out),
        canonical_internal_project_id=pid, external_project_ref="OTHER-PROJ-99",
    )
    assert res.ok is False
    assert res.error_code in ("PROJECT_IDENTITY_MISMATCH", "NO_MATERIALIZATION")
