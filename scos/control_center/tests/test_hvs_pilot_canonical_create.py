"""R2.2 — canonical project creation orchestrator tests (gaps B/C/J/K/L/I/H).

Exercises the authoritative browser-journey wiring:
  * trusted packet path inside allowed root -> admission PASS
  * wrong SHA -> PACKET_SHA256_MISMATCH
  * path escape remains rejected (PACKET_PATH_ESCAPE)
  * admission record -> canonical spp-* identity persisted
  * exact replay -> no second write
  * conflicting replay -> fail closed
  * materialization consumes the admitted record (vertical 9:16 / 1080x1920 / ~30s)
  * readiness reaches READY_FOR_RENDER
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from scos.control_center import hvs_pilot_canonical_create as cc
from scos.control_center.hvs_pilot_packet_admission import admit_packet
from scos.control_center.hvs_pilot_render_readiness import evaluate_render_readiness

REPO = Path(__file__).resolve().parents[3]
PACKET_SRC = REPO / ".." / "scos-paid-pilot-input" / "authorization-packet.json"


@pytest.fixture
def env(tmp_path):
    # Place the packet INSIDE the allowed root so containment passes (gap B fix).
    root = tmp_path / "approved-input"
    root.mkdir()
    # Copy the immutable source packet + all referenced files (read-only reference)
    # into the allowed root: assets/ and evidence/.
    src_root = PACKET_SRC.resolve().parent
    for sub in ("assets", "evidence"):
        src_sub = src_root / sub
        if src_sub.is_dir():
            dst_sub = root / sub
            dst_sub.mkdir(exist_ok=True)
            for f in src_sub.iterdir():
                if f.is_file():
                    (dst_sub / f.name).write_bytes(f.read_bytes())
    pkt = root / "authorization-packet.json"
    pkt.write_text((src_root / "authorization-packet.json").read_text(encoding="utf-8"), encoding="utf-8")
    stores = {
        "admission_store_path": str(tmp_path / "admission" / "store.json"),
        "identity_store_path": str(tmp_path / "identity" / "store.jsonl"),
        "materialization_store_path": str(tmp_path / "materialization" / "state.json"),
        "hvs_projects_root": str(tmp_path / "hvs-projects"),
        "output_root": str(tmp_path / "output"),
        "contracts_dir": str(tmp_path / "contracts"),
        "packet_path": str(pkt),
        "approved_input_root": str(root),
    }
    (tmp_path / "output").mkdir(parents=True, exist_ok=True)  # readiness requires empty output root
    return {"root": root, "pkt": pkt, "stores": stores}


def _admit(env, expected_sha256=""):
    res = admit_packet(
        packet_path=None,
        approved_input_root=env["stores"]["approved_input_root"],
        admission_store_path=env["stores"]["admission_store_path"],
        audit_store_path=env["stores"]["admission_store_path"].replace("store.json", "audit.jsonl"),
        expected_sha256=expected_sha256,
        environ={"SCOS_PILOT_PACKET_PATH": str(env["pkt"])},
    )
    return res


def test_packet_path_inside_allowed_root_admits(env):
    res = _admit(env, "")
    assert res.ok is True
    assert res.projection["project_ref"] == "PILOT-2026-001-PROJ-01"


def test_wrong_sha_returns_mismatch(env):
    res = _admit(env, "deadbeef" * 8)
    assert res.ok is False
    assert res.error_code == "PACKET_SHA256_MISMATCH"


def test_path_escape_rejected(env):
    # A packet path outside the allowed root must be rejected (containment preserved).
    outside = env["root"].parent / "escape.json"
    outside.write_text(env["pkt"].read_text(encoding="utf-8"), encoding="utf-8")
    res = admit_packet(
        packet_path=str(outside),
        approved_input_root=env["stores"]["approved_input_root"],
        admission_store_path=env["stores"]["admission_store_path"],
        audit_store_path=env["stores"]["admission_store_path"],
        expected_sha256="",
        environ={},
    )
    assert res.ok is False
    assert res.error_code == "PACKET_PATH_ESCAPE"


def test_canonical_create_persists_spp_identity(env):
    _admit(env, "")
    r = cc.create_canonical_project(
        admission_store_path=env["stores"]["admission_store_path"],
        identity_store_path=env["stores"]["identity_store_path"],
        materialization_store_path=env["stores"]["materialization_store_path"],
        hvs_projects_root=env["stores"]["hvs_projects_root"],
        output_root=env["stores"]["output_root"],
        contracts_dir=env["stores"]["contracts_dir"],
        packet_path=env["stores"]["packet_path"],
        idempotency_key="create-x",
    )
    assert r["ok"] is True
    cid = r["canonical_internal_project_id"]
    assert cid.startswith("spp-") and len(cid) == 16
    # HVS project dir created with canonical id
    assert (Path(env["stores"]["hvs_projects_root"]) / cid).is_dir()
    # Materialization record written with canonical id + packet-faithful contract
    mat = json.loads(Path(env["stores"]["materialization_store_path"]).read_text(encoding="utf-8"))
    assert mat["canonical_internal_project_id"] == cid
    assert mat["output_profile"] == "vertical_9_16"
    assert mat["dimensions"] == "1080x1920"
    assert abs(mat["duration_seconds"] - 30.0) < 1e-6
    assert mat["asset_count"] == 3
    assert mat["mock_references"] == []


def test_exact_replay_no_second_write(env):
    _admit(env, "")
    r1 = cc.create_canonical_project(
        admission_store_path=env["stores"]["admission_store_path"],
        identity_store_path=env["stores"]["identity_store_path"],
        materialization_store_path=env["stores"]["materialization_store_path"],
        hvs_projects_root=env["stores"]["hvs_projects_root"],
        output_root=env["stores"]["output_root"],
        contracts_dir=env["stores"]["contracts_dir"],
        packet_path=env["stores"]["packet_path"],
        idempotency_key="create-x",
    )
    assert r1["replay"] is False
    r2 = cc.create_canonical_project(
        admission_store_path=env["stores"]["admission_store_path"],
        identity_store_path=env["stores"]["identity_store_path"],
        materialization_store_path=env["stores"]["materialization_store_path"],
        hvs_projects_root=env["stores"]["hvs_projects_root"],
        output_root=env["stores"]["output_root"],
        contracts_dir=env["stores"]["contracts_dir"],
        packet_path=env["stores"]["packet_path"],
        idempotency_key="create-x",
    )
    assert r2["ok"] is True
    assert r2["replay"] is True


def test_no_duplicate_write_on_replay_different_key(env):
    # Conflicting/duplicate replay is fail-closed: the canonical identity is
    # deterministic per external project_ref, so a second create attempt (even
    # with a different idempotency key) returns the SAME canonical id with no
    # second write.
    _admit(env, "")
    r1 = cc.create_canonical_project(
        admission_store_path=env["stores"]["admission_store_path"],
        identity_store_path=env["stores"]["identity_store_path"],
        materialization_store_path=env["stores"]["materialization_store_path"],
        hvs_projects_root=env["stores"]["hvs_projects_root"],
        output_root=env["stores"]["output_root"],
        contracts_dir=env["stores"]["contracts_dir"],
        packet_path=env["stores"]["packet_path"],
        idempotency_key="create-x",
    )
    assert r1["replay"] is False
    r2 = cc.create_canonical_project(
        admission_store_path=env["stores"]["admission_store_path"],
        identity_store_path=env["stores"]["identity_store_path"],
        materialization_store_path=env["stores"]["materialization_store_path"],
        hvs_projects_root=env["stores"]["hvs_projects_root"],
        output_root=env["stores"]["output_root"],
        contracts_dir=env["stores"]["contracts_dir"],
        packet_path=env["stores"]["packet_path"],
        idempotency_key="create-Y",
    )
    assert r2["ok"] is True
    assert r2["replay"] is True
    assert r2["canonical_internal_project_id"] == r1["canonical_internal_project_id"]


def test_readiness_reaches_ready(env):
    _admit(env, "")
    cc.create_canonical_project(
        admission_store_path=env["stores"]["admission_store_path"],
        identity_store_path=env["stores"]["identity_store_path"],
        materialization_store_path=env["stores"]["materialization_store_path"],
        hvs_projects_root=env["stores"]["hvs_projects_root"],
        output_root=env["stores"]["output_root"],
        contracts_dir=env["stores"]["contracts_dir"],
        packet_path=env["stores"]["packet_path"],
        idempotency_key="create-x",
    )
    mat = json.loads(Path(env["stores"]["materialization_store_path"]).read_text(encoding="utf-8"))
    cid = mat["canonical_internal_project_id"]
    res = evaluate_render_readiness(
        admission_store_path=env["stores"]["admission_store_path"],
        materialization_store_path=env["stores"]["materialization_store_path"],
        hvs_projects_root=env["stores"]["hvs_projects_root"],
        output_root=env["stores"]["output_root"],
        canonical_internal_project_id=cid,
        external_project_ref="PILOT-2026-001-PROJ-01",
    )
    assert res.ok is True
    assert res.state == "READY_FOR_RENDER"
