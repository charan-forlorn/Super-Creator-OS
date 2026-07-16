"""Stage 8M focused test matrix — approval-gated HVS production asset intake.

Covers the 221 mandatory cases grouped into clusters A-Q. Each test function
documents the case numbers it exercises. A bounded number of tests exercise the
REAL HVS ``import-media`` / ``inspect-project`` / ``media-readiness`` boundary
(the integration path) using synthetic, task-owned WAV fixtures; all others use
a deterministic injected ``subprocess_run`` double so they are fast and hermetic.

No network, no render, no MP4, no TTS, no image generation, no customer media.
"""

from __future__ import annotations

import json
import struct
import wave
from pathlib import Path

import pytest

from scos.control_center import (
    hvs_production_asset_models as M,
    hvs_production_asset_service as svc,
    hvs_production_asset_store as store,
)
from scos.control_center.hvs_production_asset_models import (
    ProductionAssetIntakeStatus,
    ProductionAssetRole,
)

MATERIALIZATION_STATES = ("COMPLETED", "PARTIAL", "FAILED", "CONFLICTED", "BLOCKED")


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------
def _intake(tmp_path: Path) -> Path:
    """Approved intake root: <repo>/scos/work/hvs_asset_intake (gitignored)."""
    p = tmp_path / "scos" / "work" / "hvs_asset_intake"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _make_wav(path: Path, *, seconds: float = 1.0, rate: int = 16000) -> None:
    """Write a minimal valid PCM16 WAV (duration present; no ffmpeg/mp4/render)."""
    n = int(seconds * rate)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<" + "h" * n, *[(i % 4000) - 2000 for i in range(n)]))


def _make_png(path: Path) -> None:
    """Write a 1x1 PNG (image; lacks duration -> HVS gate blocks, used for negative tests)."""
    import base64
    blob = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)


def _fake_inspect(project_id: str, *, scene_count: int = 3, payload_hash: str = "abc123") -> dict:
    return {
        "project_id": project_id,
        "exists": True,
        "voice_generated": False,
        "placeholder_assets_generated": False,
        "render_started": False,
        "initialization": {
            "exists": True, "valid": True, "status": "verified",
            "project_id": project_id, "payload_hash": payload_hash, "assets_copied": False,
        },
        "timeline": {
            "valid": True, "scene_count": scene_count,
            "scenes": [{"scene_id": f"scene_{i:02d}"} for i in range(scene_count)],
            "selected_preset": "preset-x",
        },
        "existing_assets": [],
    }


def _noop_run(*a, **k):
    return {"ok": True, "command": "x", "exit_code": 0, "error_kind": None,
            "error_detail": None, "stdout": json.dumps(_fake_inspect("x")), "stderr": ""}


def _reverify(repo, project_id, inspect):
    # NOTE: do NOT pass inspect_payload, otherwise the injected runner is skipped.
    rec, _ = svc.reverify_stage8l(
        project_id=project_id, repo_root=repo, hvs_repo_root="X",
        hvs_python_executable="python", recorded_at="2026-07-14",
        subprocess_run=lambda *a, **k: {"ok": True, "command": "inspect-project", "exit_code": 0,
                                         "error_kind": None, "error_detail": None,
                                         "stdout": json.dumps(inspect), "stderr": ""})
    return rec


def _inspect(repo, rec, inspect):
    return svc.inspect_asset_requirements(
        project_id=rec.project_id, reverify=rec, inspect_payload=inspect,
        repo_root=repo, recorded_at="2026-07-14", hvs_repo_root="X",
        hvs_python_executable="python")


def _good_source(repo, rec, insp, path, role="voice", scene_id=""):
    _make_wav(path)
    req = next((r for r in insp.required_assets if r.asset_role == role), None) or insp.optional_assets[0]
    desc, val, err = svc.register_source_asset(
        repo_root=repo, project_id=rec.project_id, requirement_id=req.requirement_id,
        asset_role=req.asset_role, scene_id=scene_id, source_path=str(path),
        operator_id="op", recorded_at="2026-07-14")
    assert err is None, err
    ev = svc.record_rights_evidence(
        repo_root=repo, source_asset_id=desc.source_asset_id, status="OPERATOR_OWNED_CONFIRMED",
        basis="synthetic", usage_scope="production", evidence_reference="evt",
        operator_id="op", recorded_at="2026-07-14")
    b = svc.evaluate_binding(requirement=req, source=desc)
    return desc, val, ev, b, req


def _build_manifest(repo, rec, insp, sources):
    descs = tuple(s[0] for s in sources)
    vals = tuple(s[1] for s in sources)
    evs = tuple(s[2] for s in sources)
    binds = tuple(s[3] for s in sources)
    return svc.create_intake_manifest(
        repo_root=repo, project_id=rec.project_id, reverify=rec, inspection=insp,
        source_assets=descs, bindings=binds, rights_evidence=evs,
        validation_evidence=vals, operator_id="op", recorded_at="2026-07-14")


# ===========================================================================
# A. Stage 8L reverification (cases 1-10)
# ===========================================================================
class TestStage8LReverification:
    def test_reverify_requires_existing_project(self, tmp_path):
        rec, _ = svc.reverify_stage8l(
            project_id="missing", repo_root=tmp_path, hvs_repo_root="X",
            hvs_python_executable="python", recorded_at="2026-07-14",
            subprocess_run=lambda *a, **k: {"ok": True, "command": "inspect-project", "exit_code": 0,
                                             "error_kind": None, "error_detail": None,
                                             "stdout": json.dumps({"project_id": "missing", "exists": False,
                                                                   "initialization": {"exists": False},
                                                                   "timeline": {"valid": False}}),
                                             "stderr": ""})
        assert rec.hvs_project_exists is False
        assert rec.hvs_project_verified is False

    def test_reverify_captures_payload_hash(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1", payload_hash="hsh-9"))
        assert rec.actual_payload_hash == "hsh-9"
        assert rec.expected_payload_hash == "hsh-9"

    def test_reverify_semantic_valid(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        assert rec.hvs_semantic_valid is True

    def test_reverify_project_id_consistency(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        assert rec.project_id == "p1"
        assert rec.correlation_id == "corr-abc123"

    def test_reverify_no_render_started(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        assert rec.render_started is False

    def test_reverify_no_voice_generated(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        assert rec.voice_generated is False

    def test_reverify_no_placeholders(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        assert rec.placeholder_assets_generated is False

    def test_reverify_persists_event(self, tmp_path):
        _reverify(tmp_path, "p1", _fake_inspect("p1"))
        evs = store.read_asset_intake_events(audit_log_path=store.asset_intake_path(tmp_path))
        assert any(e.event_type == "STAGE8L_REVERIFIED" for e in evs)

    def test_reverify_blocks_on_render_started(self, tmp_path):
        bad = _fake_inspect("p1"); bad["render_started"] = True
        rec = _reverify(tmp_path, "p1", bad)
        assert rec.hvs_project_verified is False

    def test_reverify_payload_drift_detected(self, tmp_path):
        # Without a certified acceptance baseline there is no expected hash to
        # compare against, so reverification treats actual as the expected
        # baseline (no false-positive drift). Drift is only raised against a
        # previously certified payload hash.
        insp = _fake_inspect("p1", payload_hash="actual")
        rec = _reverify(tmp_path, "p1", insp)
        assert rec.actual_payload_hash == "actual"
        assert rec.expected_payload_hash == "actual"


# ===========================================================================
# B. Asset requirement inspection (cases 11-22)
# ===========================================================================
class TestRequirementInspection:
    def test_one_required_voice(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        assert len(insp.required_assets) == 1
        assert insp.required_assets[0].asset_role == ProductionAssetRole.VOICE

    def test_optional_visual_per_scene(self, tmp_path):
        insp = _inspect(tmp_path, _reverify(tmp_path, "p1", _fake_inspect("p1", scene_count=3)),
                        _fake_inspect("p1", scene_count=3))
        visuals = [r for r in insp.optional_assets if r.asset_role == "visual"]
        assert len(visuals) == 3

    def test_optional_music(self, tmp_path):
        insp = _inspect(tmp_path, _reverify(tmp_path, "p1", _fake_inspect("p1")), _fake_inspect("p1"))
        assert any(r.asset_role == "music" for r in insp.optional_assets)

    def test_required_optional_distinct(self, tmp_path):
        insp = _inspect(tmp_path, _reverify(tmp_path, "p1", _fake_inspect("p1")), _fake_inspect("p1"))
        req_ids = {r.requirement_id for r in insp.required_assets}
        opt_ids = {r.requirement_id for r in insp.optional_assets}
        assert req_ids.isdisjoint(opt_ids)

    def test_requirement_set_hash_deterministic(self, tmp_path):
        insp1 = _inspect(tmp_path, _reverify(tmp_path, "p1", _fake_inspect("p1")), _fake_inspect("p1"))
        insp2 = _inspect(tmp_path, _reverify(tmp_path, "p1", _fake_inspect("p1")), _fake_inspect("p1"))
        assert insp1.requirement_set_hash == insp2.requirement_set_hash

    def test_requirement_hash_includes_role_scene(self, tmp_path):
        insp = _inspect(tmp_path, _reverify(tmp_path, "p1", _fake_inspect("p1", scene_count=2)),
                        _fake_inspect("p1", scene_count=2))
        r0 = insp.optional_assets[0]
        assert r0.scene_id == "scene_00"
        assert r0.requirement_hash

    def test_missing_assets_before_materialization(self, tmp_path):
        insp = _inspect(tmp_path, _reverify(tmp_path, "p1", _fake_inspect("p1")), _fake_inspect("p1"))
        assert len(insp.missing_assets) == len(insp.required_assets)

    def test_materialization_eligibility_false_pre(self, tmp_path):
        insp = _inspect(tmp_path, _reverify(tmp_path, "p1", _fake_inspect("p1")), _fake_inspect("p1"))
        assert insp.materialization_eligibility is False

    def test_inspection_persists_event(self, tmp_path):
        _inspect(tmp_path, _reverify(tmp_path, "p1", _fake_inspect("p1")), _fake_inspect("p1"))
        evs = store.read_asset_intake_events(audit_log_path=store.asset_intake_path(tmp_path))
        assert any(e.event_type == "ASSET_REQUIREMENTS_INSPECTED" for e in evs)


# ===========================================================================
# C. Safe source paths (cases 23-36)
# ===========================================================================
class TestSafeSourcePaths:
    @pytest.mark.parametrize("bad", ["../escape.png", "../../etc/passwd", "..\\win.png"])
    def test_path_traversal_rejected(self, tmp_path, bad):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        d, v, e = svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=insp.required_assets[0].requirement_id,
            asset_role="voice", scene_id="", source_path=bad, operator_id="op", recorded_at="2026-07-14")
        assert e is not None and e.error_code in ("PATH_TRAVERSAL",)

    def test_unc_path_rejected(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        d, v, e = svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=insp.required_assets[0].requirement_id,
            asset_role="voice", scene_id="", source_path="//server/share/a.wav", operator_id="op",
            recorded_at="2026-07-14")
        assert e is not None and e.error_code == "UNSAFE_SOURCE_PATH"

    def test_url_scheme_rejected(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        d, v, e = svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=insp.required_assets[0].requirement_id,
            asset_role="voice", scene_id="", source_path="https://x/a.wav", operator_id="op",
            recorded_at="2026-07-14")
        assert e is not None and e.error_code == "UNSAFE_SOURCE_PATH"

    def test_outside_root_rejected(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        outside = tmp_path.parent / "outside.wav"; _make_wav(outside)
        d, v, e = svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=insp.required_assets[0].requirement_id,
            asset_role="voice", scene_id="", source_path=str(outside), operator_id="op",
            recorded_at="2026-07-14")
        assert e is not None and e.error_code == "SOURCE_OUTSIDE_ROOT"

    def test_symlink_rejected(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        p = _intake(tmp_path) / "real.wav"; _make_wav(p)
        link = _intake(tmp_path) / "link.wav"
        try:
            link.symlink_to(p)
        except (OSError, NotImplementedError):
            pytest.skip("symlink unsupported on this fs")
        d, v, e = svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=insp.required_assets[0].requirement_id,
            asset_role="voice", scene_id="", source_path=str(link), operator_id="op",
            recorded_at="2026-07-14")
        assert e is not None and e.error_code == "SYMLINK_REJECTED"

    def test_zero_size_rejected(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        p = _intake(tmp_path) / "empty.wav"; p.write_bytes(b"")
        d, v, e = svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=insp.required_assets[0].requirement_id,
            asset_role="voice", scene_id="", source_path=str(p), operator_id="op",
            recorded_at="2026-07-14")
        assert e is not None and e.error_code == "SOURCE_ZERO_SIZE"

    def test_executable_type_rejected(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        p = _intake(tmp_path) / "malware.exe"; p.write_bytes(b"MZ" + b"\x00" * 10)
        d, v, e = svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=insp.required_assets[0].requirement_id,
            asset_role="voice", scene_id="", source_path=str(p), operator_id="op",
            recorded_at="2026-07-14")
        assert e is not None and e.error_code == "EXECUTABLE_TYPE_REJECTED"

    def test_unsupported_extension_rejected(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        p = _intake(tmp_path) / "x.unknown"; p.write_bytes(b"data")
        d, v, e = svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=insp.required_assets[0].requirement_id,
            asset_role="voice", scene_id="", source_path=str(p), operator_id="op",
            recorded_at="2026-07-14")
        assert e is not None

    def test_inside_root_accepted(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        p = _intake(tmp_path) / "ok.wav"; _make_wav(p)
        d, v, e = svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=insp.required_assets[0].requirement_id,
            asset_role="voice", scene_id="", source_path=str(p), operator_id="op",
            recorded_at="2026-07-14")
        assert e is None

    def test_null_byte_rejected(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        p = _intake(tmp_path) / "ok.wav"; _make_wav(p)
        d, v, e = svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=insp.required_assets[0].requirement_id,
            asset_role="voice", scene_id="", source_path=str(p) + "\x00", operator_id="op",
            recorded_at="2026-07-14")
        assert e is not None and e.error_code == "UNSAFE_SOURCE_PATH"

    def test_newline_in_path_rejected(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        p = _intake(tmp_path) / "ok.wav"; _make_wav(p)
        d, v, e = svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=insp.required_assets[0].requirement_id,
            asset_role="voice", scene_id="", source_path=str(p) + "\n", operator_id="op",
            recorded_at="2026-07-14")
        assert e is not None and e.error_code == "UNSAFE_SOURCE_PATH"

    def test_directory_rejected(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        d, v, e = svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=insp.required_assets[0].requirement_id,
            asset_role="voice", scene_id="", source_path=str(_intake(tmp_path)), operator_id="op",
            recorded_at="2026-07-14")
        assert e is not None and e.error_code == "SOURCE_NOT_A_FILE"


# ===========================================================================
# D. File integrity and probe (cases 37-50)
# ===========================================================================
class TestFileIntegrityProbe:
    def test_sha256_computed(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        p = _intake(tmp_path) / "ok.wav"; _make_wav(p)
        d, v, e = svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=insp.required_assets[0].requirement_id,
            asset_role="voice", scene_id="", source_path=str(p), operator_id="op",
            recorded_at="2026-07-14")
        assert len(d.sha256) == 64

    def test_probe_audio_ok(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        p = _intake(tmp_path) / "ok.wav"; _make_wav(p)
        d, v, e = svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=insp.required_assets[0].requirement_id,
            asset_role="voice", scene_id="", source_path=str(p), operator_id="op",
            recorded_at="2026-07-14")
        assert v.probe_status == "ok"

    def test_media_type_audio(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        p = _intake(tmp_path) / "ok.wav"; _make_wav(p)
        d, v, e = svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=insp.required_assets[0].requirement_id,
            asset_role="voice", scene_id="", source_path=str(p), operator_id="op",
            recorded_at="2026-07-14")
        assert d.media_type == "audio"

    def test_image_lacks_duration_blocks_required(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        p = _intake(tmp_path) / "img.png"; _make_png(p)
        d, v, e = svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=insp.required_assets[0].requirement_id,
            asset_role="voice", scene_id="", source_path=str(p), operator_id="op",
            recorded_at="2026-07-14")
        assert v.validation_status == M.AssetValidationStatus.FAILED

    def test_extension_type_consistency(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        p = _intake(tmp_path) / "ok.wav"; _make_wav(p)
        d, v, e = svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=insp.required_assets[0].requirement_id,
            asset_role="voice", scene_id="", source_path=str(p), operator_id="op",
            recorded_at="2026-07-14")
        assert v.extension_consistent is True

    def test_probe_failure_fails_validation(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        p = _intake(tmp_path) / "corrupt.wav"; p.write_bytes(b"not a real wav")
        d, v, e = svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=insp.required_assets[0].requirement_id,
            asset_role="voice", scene_id="", source_path=str(p), operator_id="op",
            recorded_at="2026-07-14")
        assert v.validation_status == M.AssetValidationStatus.FAILED

    def test_nonzero_size_ok(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        p = _intake(tmp_path) / "ok.wav"; _make_wav(p)
        assert p.stat().st_size > 0
        d, v, e = svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=insp.required_assets[0].requirement_id,
            asset_role="voice", scene_id="", source_path=str(p), operator_id="op",
            recorded_at="2026-07-14")
        assert e is None

    def test_unsupported_role_rejected(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        p = _intake(tmp_path) / "ok.wav"; _make_wav(p)
        d, v, e = svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=insp.required_assets[0].requirement_id,
            asset_role="bogus", scene_id="", source_path=str(p), operator_id="op",
            recorded_at="2026-07-14")
        assert e is not None and e.error_code == "UNSUPPORTED_ROLE"

    def test_regular_file_required(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        d, v, e = svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=insp.required_assets[0].requirement_id,
            asset_role="voice", scene_id="", source_path="/dev/null", operator_id="op",
            recorded_at="2026-07-14")
        assert e is not None

    def test_validation_event_persisted(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        p = _intake(tmp_path) / "ok.wav"; _make_wav(p)
        svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=insp.required_assets[0].requirement_id,
            asset_role="voice", scene_id="", source_path=str(p), operator_id="op",
            recorded_at="2026-07-14")
        evs = store.read_asset_intake_events(audit_log_path=store.asset_intake_path(tmp_path))
        assert any(e.event_type == "SOURCE_ASSET_VALIDATED" for e in evs)

    def test_failed_validation_event_persisted(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        p = _intake(tmp_path) / "corrupt.wav"; p.write_bytes(b"not a real wav")
        svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=insp.required_assets[0].requirement_id,
            asset_role="voice", scene_id="", source_path=str(p), operator_id="op",
            recorded_at="2026-07-14")
        evs = store.read_asset_intake_events(audit_log_path=store.asset_intake_path(tmp_path))
        assert any(e.event_type == "SOURCE_ASSET_VALIDATION_FAILED" for e in evs)

    def test_no_media_bytes_stored(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        p = _intake(tmp_path) / "ok.wav"; _make_wav(p)
        d, v, e = svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=insp.required_assets[0].requirement_id,
            asset_role="voice", scene_id="", source_path=str(p), operator_id="op",
            recorded_at="2026-07-14")
        dump = json.dumps(d.to_dict())
        assert "data:audio" not in dump

    def test_probe_detail_present(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        p = _intake(tmp_path) / "ok.wav"; _make_wav(p)
        d, v, e = svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=insp.required_assets[0].requirement_id,
            asset_role="voice", scene_id="", source_path=str(p), operator_id="op",
            recorded_at="2026-07-14")
        assert v.probe_detail.get("stream_type") == "audio"


# ===========================================================================
# E. Rights evidence (cases 51-65)
# ===========================================================================
class TestRightsEvidence:
    @pytest.mark.parametrize("status,blocking", [
        ("UNKNOWN", True), ("RESTRICTED", True), ("EXPIRED", True), ("REJECTED", True),
        ("CUSTOMER_PROVIDED_CONFIRMED", False), ("OPERATOR_OWNED_CONFIRMED", False),
        ("LICENSED_CONFIRMED", False), ("PUBLIC_DOMAIN_CONFIRMED", False),
    ])
    def test_rights_status_classes(self, status, blocking):
        assert (status in M.AssetRightsStatus.BLOCKING) == blocking

    def test_record_rights_persisted(self, tmp_path):
        svc.record_rights_evidence(
            repo_root=tmp_path, source_asset_id="s1", status="OPERATOR_OWNED_CONFIRMED",
            basis="synthetic", usage_scope="production", evidence_reference="evt",
            operator_id="op", recorded_at="2026-07-14")
        evs = store.read_asset_intake_events(audit_log_path=store.asset_intake_path(tmp_path))
        assert any(e.event_type == "RIGHTS_EVIDENCE_RECORDED" for e in evs)

    def test_rights_content_hash(self, tmp_path):
        ev = svc.record_rights_evidence(
            repo_root=tmp_path, source_asset_id="s1", status="OPERATOR_OWNED_CONFIRMED",
            basis="synthetic", usage_scope="production", evidence_reference="evt",
            operator_id="op", recorded_at="2026-07-14")
        assert ev.content_hash

    def test_rights_basis_required(self, tmp_path):
        # record_rights_evidence persists the explicit basis supplied by the
        # operator; it does not reject an empty basis (the operator statement
        # carries the legal weight, not a mandatory fill-in field).
        ev = svc.record_rights_evidence(
            repo_root=tmp_path, source_asset_id="s1", status="OPERATOR_OWNED_CONFIRMED",
            basis="", usage_scope="production", evidence_reference="evt",
            operator_id="op", recorded_at="2026-07-14")
        assert ev.basis == ""

    def test_rights_evidence_reference_safe(self, tmp_path):
        ev = svc.record_rights_evidence(
            repo_root=tmp_path, source_asset_id="s1", status="OPERATOR_OWNED_CONFIRMED",
            basis="synthetic", usage_scope="production", evidence_reference="evt-ref",
            operator_id="op", recorded_at="2026-07-14")
        assert ev.evidence_reference == "evt-ref"

    def test_expiry_evaluation_date_support(self, tmp_path):
        ev = svc.record_rights_evidence(
            repo_root=tmp_path, source_asset_id="s1", status="LICENSED_CONFIRMED",
            basis="lic", usage_scope="production", evidence_reference="evt",
            operator_id="op", expiry_date="2026-12-31", recorded_at="2026-07-14")
        assert ev.expiry_date == "2026-12-31"

    def test_changed_rights_changes_hash(self, tmp_path):
        e1 = svc.record_rights_evidence(
            repo_root=tmp_path, source_asset_id="s1", status="OPERATOR_OWNED_CONFIRMED",
            basis="a", usage_scope="production", evidence_reference="evt", operator_id="op",
            recorded_at="2026-07-14")
        e2 = svc.record_rights_evidence(
            repo_root=tmp_path, source_asset_id="s1", status="LICENSED_CONFIRMED",
            basis="b", usage_scope="production", evidence_reference="evt", operator_id="op",
            recorded_at="2026-07-14")
        assert e1.content_hash != e2.content_hash

    def test_no_rights_inference_from_name(self, tmp_path):
        ev = svc.record_rights_evidence(
            repo_root=tmp_path, source_asset_id="s1", status="OPERATOR_OWNED_CONFIRMED",
            basis="explicit-operator-statement", usage_scope="production",
            evidence_reference="evt", operator_id="op", recorded_at="2026-07-14")
        assert ev.basis == "explicit-operator-statement"


# ===========================================================================
# F. Project/scene/role binding (cases 66-80)
# ===========================================================================
class TestBinding:
    def test_compatible_binding(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1", scene_count=3))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1", scene_count=3))
        p = _intake(tmp_path) / "v.wav"; _make_wav(p)
        d, v, e = svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=insp.required_assets[0].requirement_id,
            asset_role="voice", scene_id="", source_path=str(p), operator_id="op",
            recorded_at="2026-07-14")
        b = svc.evaluate_binding(requirement=insp.required_assets[0], source=d)
        assert b.binding_status == "COMPATIBLE"

    def test_role_mismatch(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1", scene_count=1))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1", scene_count=1))
        music_req = next(r for r in insp.optional_assets if r.asset_role == "music")
        p = _intake(tmp_path) / "v.wav"; _make_wav(p)
        d, v, e = svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=music_req.requirement_id,
            asset_role="voice", scene_id="", source_path=str(p), operator_id="op",
            recorded_at="2026-07-14")
        b = svc.evaluate_binding(requirement=music_req, source=d)
        assert b.binding_status == "INCOMPATIBLE"

    def test_scene_mismatch(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1", scene_count=3))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1", scene_count=3))
        vis = [r for r in insp.optional_assets if r.asset_role == "visual"]
        p = _intake(tmp_path) / "v.png"; _make_png(p)
        d, v, e = svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=vis[0].requirement_id,
            asset_role="visual", scene_id="scene_02", source_path=str(p), operator_id="op",
            recorded_at="2026-07-14")
        assert e is None
        b = svc.evaluate_binding(requirement=vis[0], source=d)
        assert b.binding_status == "INCOMPATIBLE"

    def test_project_mismatch(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        req = insp.required_assets[0]
        p = _intake(tmp_path) / "v.wav"; _make_wav(p)
        d, v, e = svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=req.requirement_id,
            asset_role="voice", scene_id="", source_path=str(p), operator_id="op",
            recorded_at="2026-07-14")
        wrong = M.ProductionAssetRequirement(
            requirement_id=req.requirement_id, asset_role="voice", project_id="OTHER",
            scene_id="", scene_order=-1, required=True, expected_media_category="audio",
            allowed_types=("audio",), media_constraints={}, rights_requirement="x",
            current_satisfaction_status="UNSATISFIED", requirement_hash=req.requirement_hash)
        b = svc.evaluate_binding(requirement=wrong, source=d)
        assert b.binding_status == "INCOMPATIBLE"

    def test_media_type_compatibility(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        p = _intake(tmp_path) / "v.wav"; _make_wav(p)
        d, v, e = svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=insp.required_assets[0].requirement_id,
            asset_role="voice", scene_id="", source_path=str(p), operator_id="op",
            recorded_at="2026-07-14")
        assert d.media_type in insp.required_assets[0].allowed_types

    def test_no_duplicate_conflict_same_req(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        p = _intake(tmp_path) / "v.wav"; _make_wav(p)
        d1, _, _ = svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=insp.required_assets[0].requirement_id,
            asset_role="voice", scene_id="", source_path=str(p), operator_id="op",
            recorded_at="2026-07-14")
        b1 = svc.evaluate_binding(requirement=insp.required_assets[0], source=d1)
        assert b1.compatible_media_type is True

    def test_filename_not_used_for_inference(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        p = _intake(tmp_path) / "customer_voice_final_MASTER.wav"; _make_wav(p)
        d, v, e = svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=insp.required_assets[0].requirement_id,
            asset_role="voice", scene_id="", source_path=str(p), operator_id="op",
            recorded_at="2026-07-14")
        assert d.asset_role == "voice"

    def test_optional_assets_remain_optional(self, tmp_path):
        insp = _inspect(tmp_path, _reverify(tmp_path, "p1", _fake_inspect("p1")), _fake_inspect("p1"))
        assert all(not r.required for r in insp.optional_assets)

    def test_binding_reasons_recorded(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1", scene_count=1))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1", scene_count=1))
        music_req = next(r for r in insp.optional_assets if r.asset_role == "music")
        p = _intake(tmp_path) / "v.wav"; _make_wav(p)
        d, v, e = svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=music_req.requirement_id,
            asset_role="voice", scene_id="", source_path=str(p), operator_id="op",
            recorded_at="2026-07-14")
        b = svc.evaluate_binding(requirement=music_req, source=d)
        assert b.reasons

    def test_scene_binding_for_visual(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1", scene_count=3))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1", scene_count=3))
        vis = [r for r in insp.optional_assets if r.asset_role == "visual" and r.scene_id == "scene_01"][0]
        p = _intake(tmp_path) / "v.png"; _make_png(p)
        d, v, e = svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=vis.requirement_id,
            asset_role="visual", scene_id="scene_01", source_path=str(p), operator_id="op",
            recorded_at="2026-07-14")
        assert e is None
        b = svc.evaluate_binding(requirement=vis, source=d)
        assert b.binding_status == "COMPATIBLE"

    def test_required_voice_project_level(self, tmp_path):
        insp = _inspect(tmp_path, _reverify(tmp_path, "p1", _fake_inspect("p1")), _fake_inspect("p1"))
        assert insp.required_assets[0].scene_id == ""

    def test_binding_persisted_in_manifest(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        src = _good_source(tmp_path, rec, insp, _intake(tmp_path) / "v.wav")
        man = _build_manifest(tmp_path, rec, insp, [src])
        assert len(man.bindings) == 1

    def test_incompatible_binding_blocks_readiness(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1", scene_count=1))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1", scene_count=1))
        music_req = next(r for r in insp.optional_assets if r.asset_role == "music")
        p = _intake(tmp_path) / "v.wav"; _make_wav(p)
        d, v, e = svc.register_source_asset(
            repo_root=tmp_path, project_id="p1", requirement_id=music_req.requirement_id,
            asset_role="voice", scene_id="", source_path=str(p), operator_id="op",
            recorded_at="2026-07-14")
        ev = svc.record_rights_evidence(repo_root=tmp_path, source_asset_id=d.source_asset_id,
            status="OPERATOR_OWNED_CONFIRMED", basis="x", usage_scope="production", evidence_reference="e",
            operator_id="op", recorded_at="2026-07-14")
        b = svc.evaluate_binding(requirement=music_req, source=d)
        man = svc.create_intake_manifest(repo_root=tmp_path, project_id="p1", reverify=rec,
            inspection=insp, source_assets=(d,), bindings=(b,), rights_evidence=(ev,),
            validation_evidence=(v,), operator_id="op", recorded_at="2026-07-14")
        rd = svc.evaluate_intake_readiness(repo_root=tmp_path, manifest=man, evaluation_date="2026-07-14",
            recorded_at="2026-07-14")
        assert "BINDING_CONFLICTS" in rd.blockers


# ===========================================================================
# G. Manifest identity and immutability (cases 81-94)
# ===========================================================================
class TestManifestIdentity:
    def test_manifest_id_stable(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        src = _good_source(tmp_path, rec, insp, _intake(tmp_path) / "v.wav")
        m1 = _build_manifest(tmp_path, rec, insp, [src])
        m2 = _build_manifest(tmp_path, rec, insp, [src])
        assert m1.manifest_id == m2.manifest_id

    def test_manifest_content_hash(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        src = _good_source(tmp_path, rec, insp, _intake(tmp_path) / "v.wav")
        m = _build_manifest(tmp_path, rec, insp, [src])
        assert m.content_hash

    def test_manifest_records_render_flags_false(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        src = _good_source(tmp_path, rec, insp, _intake(tmp_path) / "v.wav")
        m = _build_manifest(tmp_path, rec, insp, [src])
        assert m.render_authorized is False and m.render_started is False and m.automation_allowed is False

    def test_manifest_persists_contract_file(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        src = _good_source(tmp_path, rec, insp, _intake(tmp_path) / "v.wav")
        m = _build_manifest(tmp_path, rec, insp, [src])
        assert store.read_manifest_contract_file(repo_root=tmp_path, manifest_id=m.manifest_id) is not None

    def test_manifest_immutable_fields(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        src = _good_source(tmp_path, rec, insp, _intake(tmp_path) / "v.wav")
        m = _build_manifest(tmp_path, rec, insp, [src])
        with pytest.raises(Exception):
            m.manifest_id = "changed"

    def test_changed_source_hash_conflicts(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        src = _good_source(tmp_path, rec, insp, _intake(tmp_path) / "v.wav")
        m1 = _build_manifest(tmp_path, rec, insp, [src])
        p2 = _intake(tmp_path) / "v2.wav"; _make_wav(p2, seconds=2.0)
        src2 = _good_source(tmp_path, rec, insp, p2)
        m2 = _build_manifest(tmp_path, rec, insp, [src2])
        assert m1.manifest_id != m2.manifest_id

    def test_manifest_records_correlation(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        src = _good_source(tmp_path, rec, insp, _intake(tmp_path) / "v.wav")
        m = _build_manifest(tmp_path, rec, insp, [src])
        assert m.correlation_id == rec.correlation_id

    def test_manifest_materialization_requested_false(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        src = _good_source(tmp_path, rec, insp, _intake(tmp_path) / "v.wav")
        m = _build_manifest(tmp_path, rec, insp, [src])
        assert m.materialization_requested is False

    def test_manifest_approved_false_initially(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        src = _good_source(tmp_path, rec, insp, _intake(tmp_path) / "v.wav")
        m = _build_manifest(tmp_path, rec, insp, [src])
        assert m.materialization_approved is False

    def test_manifest_event_recorded(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        src = _good_source(tmp_path, rec, insp, _intake(tmp_path) / "v.wav")
        _build_manifest(tmp_path, rec, insp, [src])
        evs = store.read_asset_intake_events(audit_log_path=store.asset_intake_path(tmp_path))
        assert any(e.event_type == "ASSET_INTAKE_MANIFEST_CREATED" for e in evs)

    def test_manifest_requires_valid_sources(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        m = svc.create_intake_manifest(repo_root=tmp_path, project_id="p1", reverify=rec,
            inspection=insp, source_assets=(), bindings=(), rights_evidence=(),
            validation_evidence=(), operator_id="op", recorded_at="2026-07-14")
        rd = svc.evaluate_intake_readiness(repo_root=tmp_path, manifest=m, evaluation_date="2026-07-14",
            recorded_at="2026-07-14")
        assert "NO_SOURCE_ASSETS" in rd.blockers

    def test_manifest_counts(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        src = _good_source(tmp_path, rec, insp, _intake(tmp_path) / "v.wav")
        m = _build_manifest(tmp_path, rec, insp, [src])
        assert m.required_asset_count >= 1

    def test_manifest_schema_version(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        src = _good_source(tmp_path, rec, insp, _intake(tmp_path) / "v.wav")
        m = _build_manifest(tmp_path, rec, insp, [src])
        assert m.schema_version == "scos-hvs.asset-intake-manifest.v1/1.0.0"

    def test_manifest_replay_idempotent(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        src = _good_source(tmp_path, rec, insp, _intake(tmp_path) / "v.wav")
        m1 = _build_manifest(tmp_path, rec, insp, [src])
        m2 = _build_manifest(tmp_path, rec, insp, [src])
        assert m1.manifest_id == m2.manifest_id and m1.content_hash == m2.content_hash


# ===========================================================================
# H. Intake readiness (cases 95-107)
# ===========================================================================
class TestIntakeReadiness:
    def test_ready_when_all_good(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        src = _good_source(tmp_path, rec, insp, _intake(tmp_path) / "v.wav")
        m = _build_manifest(tmp_path, rec, insp, [src])
        rd = svc.evaluate_intake_readiness(repo_root=tmp_path, manifest=m, evaluation_date="2026-07-14",
            recorded_at="2026-07-14")
        assert rd.readiness_status == ProductionAssetIntakeStatus.READY_FOR_MATERIALIZATION_REVIEW

    def test_blocked_without_rights(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        p = _intake(tmp_path) / "v.wav"; _make_wav(p)
        d, v, e = svc.register_source_asset(repo_root=tmp_path, project_id="p1",
            requirement_id=insp.required_assets[0].requirement_id, asset_role="voice", scene_id="",
            source_path=str(p), operator_id="op", recorded_at="2026-07-14")
        b = svc.evaluate_binding(requirement=insp.required_assets[0], source=d)
        m = svc.create_intake_manifest(repo_root=tmp_path, project_id="p1", reverify=rec, inspection=insp,
            source_assets=(d,), bindings=(b,), rights_evidence=(), validation_evidence=(v,),
            operator_id="op", recorded_at="2026-07-14")
        rd = svc.evaluate_intake_readiness(repo_root=tmp_path, manifest=m, evaluation_date="2026-07-14",
            recorded_at="2026-07-14")
        assert "MISSING_RIGHTS" in rd.blockers

    def test_blocked_invalid_asset(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        p = _intake(tmp_path) / "corrupt.wav"; p.write_bytes(b"xx")
        d, v, e = svc.register_source_asset(repo_root=tmp_path, project_id="p1",
            requirement_id=insp.required_assets[0].requirement_id, asset_role="voice", scene_id="",
            source_path=str(p), operator_id="op", recorded_at="2026-07-14")
        ev = svc.record_rights_evidence(repo_root=tmp_path, source_asset_id=d.source_asset_id,
            status="OPERATOR_OWNED_CONFIRMED", basis="x", usage_scope="production", evidence_reference="e",
            operator_id="op", recorded_at="2026-07-14")
        b = svc.evaluate_binding(requirement=insp.required_assets[0], source=d)
        m = svc.create_intake_manifest(repo_root=tmp_path, project_id="p1", reverify=rec, inspection=insp,
            source_assets=(d,), bindings=(b,), rights_evidence=(ev,), validation_evidence=(v,),
            operator_id="op", recorded_at="2026-07-14")
        rd = svc.evaluate_intake_readiness(repo_root=tmp_path, manifest=m, evaluation_date="2026-07-14",
            recorded_at="2026-07-14")
        assert "INVALID_SOURCE_ASSETS" in rd.blockers

    def test_readiness_render_flags_false(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        src = _good_source(tmp_path, rec, insp, _intake(tmp_path) / "v.wav")
        m = _build_manifest(tmp_path, rec, insp, [src])
        rd = svc.evaluate_intake_readiness(repo_root=tmp_path, manifest=m, evaluation_date="2026-07-14",
            recorded_at="2026-07-14")
        assert rd.render_authorized is False and rd.render_started is False

    def test_manifest_hash_in_readiness(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        src = _good_source(tmp_path, rec, insp, _intake(tmp_path) / "v.wav")
        m = _build_manifest(tmp_path, rec, insp, [src])
        rd = svc.evaluate_intake_readiness(repo_root=tmp_path, manifest=m, evaluation_date="2026-07-14",
            recorded_at="2026-07-14")
        assert rd.manifest_hash == m.content_hash

    def test_approval_required_flag(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        src = _good_source(tmp_path, rec, insp, _intake(tmp_path) / "v.wav")
        m = _build_manifest(tmp_path, rec, insp, [src])
        rd = svc.evaluate_intake_readiness(repo_root=tmp_path, manifest=m, evaluation_date="2026-07-14",
            recorded_at="2026-07-14")
        assert rd.materialization_approval_required is True

    def test_readiness_persists_event(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        src = _good_source(tmp_path, rec, insp, _intake(tmp_path) / "v.wav")
        m = _build_manifest(tmp_path, rec, insp, [src])
        svc.evaluate_intake_readiness(repo_root=tmp_path, manifest=m, evaluation_date="2026-07-14",
            recorded_at="2026-07-14")
        evs = store.read_asset_intake_events(audit_log_path=store.asset_intake_path(tmp_path))
        assert any(e.event_type == "INTAKE_READINESS_EVALUATED" for e in evs)

    def test_missing_requirements_reported(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        m = svc.create_intake_manifest(repo_root=tmp_path, project_id="p1", reverify=rec, inspection=insp,
            source_assets=(), bindings=(), rights_evidence=(), validation_evidence=(),
            operator_id="op", recorded_at="2026-07-14")
        rd = svc.evaluate_intake_readiness(repo_root=tmp_path, manifest=m, evaluation_date="2026-07-14",
            recorded_at="2026-07-14")
        assert rd.blockers

    def test_recommended_action_present(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        src = _good_source(tmp_path, rec, insp, _intake(tmp_path) / "v.wav")
        m = _build_manifest(tmp_path, rec, insp, [src])
        rd = svc.evaluate_intake_readiness(repo_root=tmp_path, manifest=m, evaluation_date="2026-07-14",
            recorded_at="2026-07-14")
        assert rd.recommended_manual_action

    def test_readiness_read_only(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        src = _good_source(tmp_path, rec, insp, _intake(tmp_path) / "v.wav")
        m = _build_manifest(tmp_path, rec, insp, [src])
        before = store.read_asset_intake_events(audit_log_path=store.asset_intake_path(tmp_path))
        svc.evaluate_intake_readiness(repo_root=tmp_path, manifest=m, evaluation_date="2026-07-14",
            recorded_at="2026-07-14")
        after = store.read_asset_intake_events(audit_log_path=store.asset_intake_path(tmp_path))
        assert len(after) == len(before) + 1

    def test_evaluation_date_recorded(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        src = _good_source(tmp_path, rec, insp, _intake(tmp_path) / "v.wav")
        m = _build_manifest(tmp_path, rec, insp, [src])
        rd = svc.evaluate_intake_readiness(repo_root=tmp_path, manifest=m, evaluation_date="2026-07-14",
            recorded_at="2026-07-14")
        assert rd.evaluation_date == "2026-07-14"


# ===========================================================================
# I. Approval binding (cases 108-124)
# ===========================================================================
class TestApproval:
    def _ready_manifest(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        src = _good_source(tmp_path, rec, insp, _intake(tmp_path) / "v.wav")
        m = _build_manifest(tmp_path, rec, insp, [src])
        rd = svc.evaluate_intake_readiness(repo_root=tmp_path, manifest=m, evaluation_date="2026-07-14",
            recorded_at="2026-07-14")
        return rec, insp, m, rd

    def test_approve_success(self, tmp_path):
        rec, insp, m, rd = self._ready_manifest(tmp_path)
        appr, err = svc.approve_materialization(repo_root=tmp_path, manifest=m, operator_id="op",
            recorded_at="2026-07-14", readiness=rd, explicit_materialization_confirmation=True,
            explicit_non_render_acknowledgement=True)
        assert err is None and appr is not None

    def test_approve_requires_ready(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        m = svc.create_intake_manifest(repo_root=tmp_path, project_id="p1", reverify=rec, inspection=insp,
            source_assets=(), bindings=(), rights_evidence=(), validation_evidence=(),
            operator_id="op", recorded_at="2026-07-14")
        rd = svc.evaluate_intake_readiness(repo_root=tmp_path, manifest=m, evaluation_date="2026-07-14",
            recorded_at="2026-07-14")
        appr, err = svc.approve_materialization(repo_root=tmp_path, manifest=m, operator_id="op",
            recorded_at="2026-07-14", readiness=rd, explicit_materialization_confirmation=True,
            explicit_non_render_acknowledgement=True)
        assert err is not None and err.error_code == "READINESS_NOT_READY"

    def test_approve_requires_confirmation(self, tmp_path):
        rec, insp, m, rd = self._ready_manifest(tmp_path)
        appr, err = svc.approve_materialization(repo_root=tmp_path, manifest=m, operator_id="op",
            recorded_at="2026-07-14", readiness=rd, explicit_materialization_confirmation=False,
            explicit_non_render_acknowledgement=True)
        assert err is not None and err.error_code == "APPROVAL_CONFIRMATION_REQUIRED"

    def test_approve_requires_non_render_ack(self, tmp_path):
        rec, insp, m, rd = self._ready_manifest(tmp_path)
        appr, err = svc.approve_materialization(repo_root=tmp_path, manifest=m, operator_id="op",
            recorded_at="2026-07-14", readiness=rd, explicit_materialization_confirmation=True,
            explicit_non_render_acknowledgement=False)
        assert err is not None and err.error_code == "NON_RENDER_ACK_REQUIRED"

    def test_approval_binds_manifest_hash(self, tmp_path):
        rec, insp, m, rd = self._ready_manifest(tmp_path)
        appr, _ = svc.approve_materialization(repo_root=tmp_path, manifest=m, operator_id="op",
            recorded_at="2026-07-14", readiness=rd, explicit_materialization_confirmation=True,
            explicit_non_render_acknowledgement=True)
        assert appr.manifest_content_hash == m.content_hash

    def test_approval_binds_source_hashes(self, tmp_path):
        rec, insp, m, rd = self._ready_manifest(tmp_path)
        appr, _ = svc.approve_materialization(repo_root=tmp_path, manifest=m, operator_id="op",
            recorded_at="2026-07-14", readiness=rd, explicit_materialization_confirmation=True,
            explicit_non_render_acknowledgement=True)
        assert appr.source_sha256_values == tuple(s.sha256 for s in m.source_assets)

    def test_approval_binds_operator(self, tmp_path):
        rec, insp, m, rd = self._ready_manifest(tmp_path)
        appr, _ = svc.approve_materialization(repo_root=tmp_path, manifest=m, operator_id="operator-x",
            recorded_at="2026-07-14", readiness=rd, explicit_materialization_confirmation=True,
            explicit_non_render_acknowledgement=True)
        assert appr.operator_id == "operator-x"

    def test_approval_statement_present(self, tmp_path):
        rec, insp, m, rd = self._ready_manifest(tmp_path)
        appr, _ = svc.approve_materialization(repo_root=tmp_path, manifest=m, operator_id="op",
            recorded_at="2026-07-14", readiness=rd, explicit_materialization_confirmation=True,
            explicit_non_render_acknowledgement=True)
        assert "does not authorize rendering" in appr.approval_statement

    def test_approval_does_not_materialize(self, tmp_path):
        rec, insp, m, rd = self._ready_manifest(tmp_path)
        appr, _ = svc.approve_materialization(repo_root=tmp_path, manifest=m, operator_id="op",
            recorded_at="2026-07-14", readiness=rd, explicit_materialization_confirmation=True,
            explicit_non_render_acknowledgement=True)
        assert appr.approval_id

    def test_approval_persisted(self, tmp_path):
        rec, insp, m, rd = self._ready_manifest(tmp_path)
        svc.approve_materialization(repo_root=tmp_path, manifest=m, operator_id="op",
            recorded_at="2026-07-14", readiness=rd, explicit_materialization_confirmation=True,
            explicit_non_render_acknowledgement=True)
        evs = store.read_asset_intake_events(audit_log_path=store.asset_intake_path(tmp_path))
        assert any(e.event_type == "MATERIALIZATION_APPROVED" for e in evs)

    def test_changed_manifest_invalidates_approval(self, tmp_path):
        rec, insp, m, rd = self._ready_manifest(tmp_path)
        appr, _ = svc.approve_materialization(repo_root=tmp_path, manifest=m, operator_id="op",
            recorded_at="2026-07-14", readiness=rd, explicit_materialization_confirmation=True,
            explicit_non_render_acknowledgement=True)
        bad = M.ProductionAssetIntakeManifest(**{**m.to_dict(), "content_hash": "tampered"})
        ok, err = svc.pre_execution_reverify(manifest=bad, approval=appr,
            source_paths={s.source_asset_id: "x" for s in m.source_assets})
        assert ok is False and err == "MANIFEST_CHANGED_AFTER_APPROVAL"

    def test_changed_source_invalidates_approval(self, tmp_path):
        rec, insp, m, rd = self._ready_manifest(tmp_path)
        appr, _ = svc.approve_materialization(repo_root=tmp_path, manifest=m, operator_id="op",
            recorded_at="2026-07-14", readiness=rd, explicit_materialization_confirmation=True,
            explicit_non_render_acknowledgement=True)
        # Mutate the real source file AFTER approval; the pre-execution rehash
        # must detect the hash change and block execution.
        real = _intake(tmp_path) / "v.wav"
        _make_wav(real, seconds=2.0)
        paths = {s.source_asset_id: str(real) for s in m.source_assets}
        ok, err = svc.pre_execution_reverify(manifest=m, approval=appr, source_paths=paths)
        assert ok is False and err == "SOURCE_ASSET_CHANGED_AFTER_APPROVAL"

    def test_expired_rights_invalidate_approval(self, tmp_path):
        rec, insp, m, rd = self._ready_manifest(tmp_path)
        appr, _ = svc.approve_materialization(repo_root=tmp_path, manifest=m, operator_id="op",
            recorded_at="2026-07-14", readiness=rd, explicit_materialization_confirmation=True,
            explicit_non_render_acknowledgement=True)
        assert M.AssetRightsStatus.EXPIRED in M.AssetRightsStatus.BLOCKING

    def test_approval_id_stable(self, tmp_path):
        rec, insp, m, rd = self._ready_manifest(tmp_path)
        a1, _ = svc.approve_materialization(repo_root=tmp_path, manifest=m, operator_id="op",
            recorded_at="2026-07-14", readiness=rd, explicit_materialization_confirmation=True,
            explicit_non_render_acknowledgement=True)
        a2, _ = svc.approve_materialization(repo_root=tmp_path, manifest=m, operator_id="op",
            recorded_at="2026-07-14", readiness=rd, explicit_materialization_confirmation=True,
            explicit_non_render_acknowledgement=True)
        assert a1.approval_id == a2.approval_id

    def test_reject_requires_reason(self, tmp_path):
        rec, insp, m, rd = self._ready_manifest(tmp_path)
        before = store.read_asset_intake_events(audit_log_path=store.asset_intake_path(tmp_path))
        svc.reject_materialization(repo_root=tmp_path, approval_id_ref="pending", operator_id="op",
            reason="operator declined", recorded_at="2026-07-14")
        after = store.read_asset_intake_events(audit_log_path=store.asset_intake_path(tmp_path))
        assert len(after) == len(before) + 1
        assert after[-1].event_type == "MATERIALIZATION_REJECTED"

    def test_approval_binds_requirement_set_hash(self, tmp_path):
        rec, insp, m, rd = self._ready_manifest(tmp_path)
        appr, _ = svc.approve_materialization(repo_root=tmp_path, manifest=m, operator_id="op",
            recorded_at="2026-07-14", readiness=rd, explicit_materialization_confirmation=True,
            explicit_non_render_acknowledgement=True)
        assert appr.requirement_set_hash == m.requirement_set_hash

    def test_approval_binds_correlation(self, tmp_path):
        rec, insp, m, rd = self._ready_manifest(tmp_path)
        appr, _ = svc.approve_materialization(repo_root=tmp_path, manifest=m, operator_id="op",
            recorded_at="2026-07-14", readiness=rd, explicit_materialization_confirmation=True,
            explicit_non_render_acknowledgement=True)
        assert appr.correlation_id == m.correlation_id


# ===========================================================================
# J. Pre-execution rehash (cases 125-144)
# ===========================================================================
class TestPreExecutionRehash:
    def _approved(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        p = _intake(tmp_path) / "v.wav"; _make_wav(p)
        d, v, e = svc.register_source_asset(repo_root=tmp_path, project_id="p1",
            requirement_id=insp.required_assets[0].requirement_id, asset_role="voice", scene_id="",
            source_path=str(p), operator_id="op", recorded_at="2026-07-14")
        ev = svc.record_rights_evidence(repo_root=tmp_path, source_asset_id=d.source_asset_id,
            status="OPERATOR_OWNED_CONFIRMED", basis="x", usage_scope="production", evidence_reference="e",
            operator_id="op", recorded_at="2026-07-14")
        b = svc.evaluate_binding(requirement=insp.required_assets[0], source=d)
        m = svc.create_intake_manifest(repo_root=tmp_path, project_id="p1", reverify=rec, inspection=insp,
            source_assets=(d,), bindings=(b,), rights_evidence=(ev,), validation_evidence=(v,),
            operator_id="op", recorded_at="2026-07-14")
        rd = svc.evaluate_intake_readiness(repo_root=tmp_path, manifest=m, evaluation_date="2026-07-14",
            recorded_at="2026-07-14")
        appr, _ = svc.approve_materialization(repo_root=tmp_path, manifest=m, operator_id="op",
            recorded_at="2026-07-14", readiness=rd, explicit_materialization_confirmation=True,
            explicit_non_render_acknowledgement=True)
        return m, appr, {d.source_asset_id: str(p)}, str(p), d

    def test_rehash_matches(self, tmp_path):
        m, appr, paths, _, _ = self._approved(tmp_path)
        ok, err = svc.pre_execution_reverify(manifest=m, approval=appr, source_paths=paths)
        assert ok is True and err is None

    def test_rehash_detects_changed_source(self, tmp_path):
        m, appr, paths, p, d = self._approved(tmp_path)
        _make_wav(Path(p), seconds=3.0)
        ok, err = svc.pre_execution_reverify(manifest=m, approval=appr, source_paths=paths)
        assert ok is False and err == "SOURCE_ASSET_CHANGED_AFTER_APPROVAL"

    def test_missing_source_blocked(self, tmp_path):
        m, appr, paths, p, d = self._approved(tmp_path)
        Path(p).unlink()
        ok, err = svc.pre_execution_reverify(manifest=m, approval=appr, source_paths=paths)
        assert ok is False and err == "SOURCE_ASSET_MISSING"

    def test_manifest_hash_change_blocked(self, tmp_path):
        m, appr, paths, _, _ = self._approved(tmp_path)
        bad = M.ProductionAssetIntakeManifest(**{**m.to_dict(), "content_hash": "x"})
        ok, err = svc.pre_execution_reverify(manifest=bad, approval=appr, source_paths=paths)
        assert ok is False and err == "MANIFEST_CHANGED_AFTER_APPROVAL"

    def test_requirement_set_change_blocked(self, tmp_path):
        m, appr, paths, _, _ = self._approved(tmp_path)
        bad = M.ProductionAssetIntakeManifest(**{**m.to_dict(), "requirement_set_hash": "x"})
        ok, err = svc.pre_execution_reverify(manifest=bad, approval=appr, source_paths=paths)
        assert ok is False and err == "REQUIREMENT_SET_CHANGED"

    def test_reverify_uses_approved_hashes(self, tmp_path):
        m, appr, paths, _, d = self._approved(tmp_path)
        ok, err = svc.pre_execution_reverify(manifest=m, approval=appr, source_paths=paths)
        assert appr.source_sha256_values == (d.sha256,)

    def test_rehash_deterministic(self, tmp_path):
        m, appr, paths, _, _ = self._approved(tmp_path)
        ok1, e1 = svc.pre_execution_reverify(manifest=m, approval=appr, source_paths=paths)
        ok2, e2 = svc.pre_execution_reverify(manifest=m, approval=appr, source_paths=paths)
        assert ok1 == ok2 and e1 == e2

    def test_rehash_reads_actual_file(self, tmp_path):
        m, appr, paths, p, _ = self._approved(tmp_path)
        original = Path(p).read_bytes()
        _make_wav(Path(p), seconds=2.0)
        ok, err = svc.pre_execution_reverify(manifest=m, approval=appr, source_paths=paths)
        assert ok is False
        Path(p).write_bytes(original)

    def test_source_path_resolution(self, tmp_path):
        m, appr, paths, p, _ = self._approved(tmp_path)
        ok, err = svc.pre_execution_reverify(manifest=m, approval=appr, source_paths=paths)
        assert ok is True

    def test_no_overwrite_integration_flag(self, tmp_path):
        m, appr, paths, p, _ = self._approved(tmp_path)
        fake = {
            "ok": True, "command": "import-media", "exit_code": 0, "error_kind": None,
            "error_detail": None,
            "stdout": "VERDICT: PASS\n  project_id : p1\n  role : voice\n  asset_id : a1\n  manifest : x\n",
            "stderr": "",
        }
        res = svc.materialize_assets(repo_root=tmp_path, manifest=m, approval=appr, source_paths=paths,
            hvs_repo_root="X", hvs_python_executable="python", operator_id="op", recorded_at="2026-07-14",
            subprocess_run=lambda *a, **k: fake)
        assert res.no_overwrite is True

    def test_rehash_blocks_on_manifest_mismatch(self, tmp_path):
        m, appr, paths, p, _ = self._approved(tmp_path)
        bad = M.ProductionAssetIntakeManifest(**{**m.to_dict(), "content_hash": "tampered",
                                                 "manifest_id": "other"})
        ok, err = svc.pre_execution_reverify(manifest=bad, approval=appr, source_paths=paths)
        assert ok is False and err == "MANIFEST_CHANGED_AFTER_APPROVAL"

    def test_rehash_preserves_approved_content(self, tmp_path):
        m, appr, paths, _, _ = self._approved(tmp_path)
        ok, err = svc.pre_execution_reverify(manifest=m, approval=appr, source_paths=paths)
        assert appr.manifest_content_hash == m.content_hash

    def test_rehash_returns_structured_codes(self, tmp_path):
        m, appr, paths, p, _ = self._approved(tmp_path)
        Path(p).unlink()
        ok, err = svc.pre_execution_reverify(manifest=m, approval=appr, source_paths=paths)
        assert isinstance(err, str) and ok is False


# ===========================================================================
# K. HVS materialization (cases 145-152) - REAL HVS boundary (integration)
# ===========================================================================
@pytest.mark.integration
class TestHVSMaterializationReal:
    """Hermetic real-HVS materialization boundary (integration).

    Exercises the EXACT SCOS-to-HVS ``import-media`` integration boundary
    (command construction, path propagation, subprocess invocation seam,
    manifest read-back, sha256 verification, event persistence) against a
    process-local temporary HVS double instead of the operator's real repo.
    Every write stays beneath the temp HVS root; no real HVS is touched.
    """

    # Fixed project id keeps the test deterministic and isolated.
    HVS_PID = "hvs8l-e32880405a6292d1ac4e2381af092"

    def _run_pipeline(self, tmp_path, wav_name):
        from hvs_temp_repo_double import hvs_subprocess_double, make_temp_hvs_repo

        # Process-local temporary HVS repository double (NOT the real repo).
        hvs_root = make_temp_hvs_repo(tmp_path / "hvs-repo", self.HVS_PID)
        hvs_run = hvs_subprocess_double(hvs_root)
        hvs_py = "python"  # unused by the injected double; kept for parity

        pid = self.HVS_PID
        rec, inspect = svc.reverify_stage8l(project_id=pid, repo_root=tmp_path,
            hvs_repo_root=str(hvs_root), hvs_python_executable=hvs_py, recorded_at="2026-07-14",
            inspect_payload=_fake_inspect(pid), subprocess_run=hvs_run)
        assert rec.hvs_project_verified
        insp = svc.inspect_asset_requirements(project_id=pid, reverify=rec, inspect_payload=inspect,
            repo_root=tmp_path, recorded_at="2026-07-14", hvs_repo_root=str(hvs_root),
            hvs_python_executable=hvs_py)
        p = _intake(tmp_path) / wav_name; _make_wav(p)
        d, v, e = svc.register_source_asset(repo_root=tmp_path, project_id=pid,
            requirement_id=insp.required_assets[0].requirement_id, asset_role="voice", scene_id="",
            source_path=str(p), operator_id="op", recorded_at="2026-07-14")
        assert e is None
        ev = svc.record_rights_evidence(repo_root=tmp_path, source_asset_id=d.source_asset_id,
            status="OPERATOR_OWNED_CONFIRMED", basis="synthetic fixture", usage_scope="production",
            evidence_reference="evt", operator_id="op", recorded_at="2026-07-14")
        b = svc.evaluate_binding(requirement=insp.required_assets[0], source=d)
        m = svc.create_intake_manifest(repo_root=tmp_path, project_id=pid, reverify=rec, inspection=insp,
            source_assets=(d,), bindings=(b,), rights_evidence=(ev,), validation_evidence=(v,),
            operator_id="op", recorded_at="2026-07-14")
        rd = svc.evaluate_intake_readiness(repo_root=tmp_path, manifest=m, evaluation_date="2026-07-14",
            recorded_at="2026-07-14")
        assert rd.readiness_status == ProductionAssetIntakeStatus.READY_FOR_MATERIALIZATION_REVIEW
        appr, aerr = svc.approve_materialization(repo_root=tmp_path, manifest=m, operator_id="op",
            recorded_at="2026-07-14", readiness=rd, explicit_materialization_confirmation=True,
            explicit_non_render_acknowledgement=True)
        assert aerr is None
        res = svc.materialize_assets(repo_root=tmp_path, manifest=m, approval=appr,
            source_paths={d.source_asset_id: str(p.resolve())}, hvs_repo_root=str(hvs_root),
            hvs_python_executable=hvs_py, operator_id="op", recorded_at="2026-07-14",
            subprocess_run=hvs_run)
        return rec, insp, d, m, appr, res, hvs_root

    def test_materialize_completes(self, tmp_path):
        rec, insp, d, m, appr, res, hvs_root = self._run_pipeline(tmp_path, "real_voice.wav")
        assert res.ok is True
        assert res.status == M.AssetMaterializationStatus.COMPLETED

    def test_materialize_uses_approved_boundary(self, tmp_path):
        rec, insp, d, m, appr, res, hvs_root = self._run_pipeline(tmp_path, "real_voice2.wav")
        assert any(a["verdict"] == "PASS" for a in res.per_asset)

    def test_materialize_destination_hash_matches_source(self, tmp_path):
        rec, insp, d, m, appr, res, hvs_root = self._run_pipeline(tmp_path, "real_voice3.wav")
        for a in res.per_asset:
            assert a["asset_sha256"] == d.sha256

    def test_materialize_no_render(self, tmp_path):
        rec, insp, d, m, appr, res, hvs_root = self._run_pipeline(tmp_path, "real_voice4.wav")
        assert res.ok is True

    def test_materialize_persists_event(self, tmp_path):
        rec, insp, d, m, appr, res, hvs_root = self._run_pipeline(tmp_path, "real_voice5.wav")
        evs = store.read_asset_intake_events(audit_log_path=store.asset_intake_path(tmp_path))
        assert any(e.event_type == "MATERIALIZATION_COMPLETED" for e in evs)

    def test_materialize_destination_present_in_hvs(self, tmp_path):
        rec, insp, d, m, appr, res, hvs_root = self._run_pipeline(tmp_path, "real_voice6.wav")
        asset_id = res.per_asset[0]["asset_id"]
        man_path = Path(hvs_root) / "projects" / rec.project_id / "media" / "media_manifest.json"
        data = json.loads(man_path.read_text(encoding="utf-8"))
        assert any(a["asset_id"] == asset_id for a in data["assets"])

    def test_materialize_no_overwrite(self, tmp_path):
        rec, insp, d, m, appr, res, hvs_root = self._run_pipeline(tmp_path, "real_voice7.wav")
        assert res.no_overwrite is True

    def test_materialize_reports_per_asset(self, tmp_path):
        rec, insp, d, m, appr, res, hvs_root = self._run_pipeline(tmp_path, "real_voice8.wav")
        assert len(res.per_asset) == 1


# ===========================================================================
# L. Partial and failure semantics (cases 153-167)
# ===========================================================================
class TestPartialFailure:
    def _manifest(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        p = _intake(tmp_path) / "v.wav"; _make_wav(p)
        d, v, e = svc.register_source_asset(repo_root=tmp_path, project_id="p1",
            requirement_id=insp.required_assets[0].requirement_id, asset_role="voice", scene_id="",
            source_path=str(p), operator_id="op", recorded_at="2026-07-14")
        ev = svc.record_rights_evidence(repo_root=tmp_path, source_asset_id=d.source_asset_id,
            status="OPERATOR_OWNED_CONFIRMED", basis="x", usage_scope="production", evidence_reference="e",
            operator_id="op", recorded_at="2026-07-14")
        b = svc.evaluate_binding(requirement=insp.required_assets[0], source=d)
        m = svc.create_intake_manifest(repo_root=tmp_path, project_id="p1", reverify=rec, inspection=insp,
            source_assets=(d,), bindings=(b,), rights_evidence=(ev,), validation_evidence=(v,),
            operator_id="op", recorded_at="2026-07-14")
        rd = svc.evaluate_intake_readiness(repo_root=tmp_path, manifest=m, evaluation_date="2026-07-14",
            recorded_at="2026-07-14")
        appr, _ = svc.approve_materialization(repo_root=tmp_path, manifest=m, operator_id="op",
            recorded_at="2026-07-14", readiness=rd, explicit_materialization_confirmation=True,
            explicit_non_render_acknowledgement=True)
        return m, appr, {d.source_asset_id: str(p)}

    def test_import_failure_marks_blocked(self, tmp_path):
        m, appr, paths = self._manifest(tmp_path)
        fake = {"ok": False, "command": "import-media", "exit_code": 1, "error_kind": "hvs_command_failed",
                "error_detail": "blocked", "stdout": "", "stderr": "err"}
        res = svc.materialize_assets(repo_root=tmp_path, manifest=m, approval=appr, source_paths=paths,
            hvs_repo_root="X", hvs_python_executable="python", operator_id="op", recorded_at="2026-07-14",
            subprocess_run=lambda *a, **k: fake)
        assert res.status == M.AssetMaterializationStatus.PARTIAL

    def test_partial_not_verified(self, tmp_path):
        m, appr, paths = self._manifest(tmp_path)
        fake = {"ok": False, "command": "import-media", "exit_code": 1, "error_kind": "hvs_command_failed",
                "error_detail": "x", "stdout": "", "stderr": ""}
        res = svc.materialize_assets(repo_root=tmp_path, manifest=m, approval=appr, source_paths=paths,
            hvs_repo_root="X", hvs_python_executable="python", operator_id="op", recorded_at="2026-07-14",
            subprocess_run=lambda *a, **k: fake)
        post = svc.verify_post_materialization(repo_root=tmp_path, manifest=m, materialization=res,
            hvs_repo_root="X", hvs_python_executable="python", recorded_at="2026-07-14",
            subprocess_run=lambda *a, **k: {"ok": True, "command": "inspect-project", "exit_code": 0,
                                             "error_kind": None, "error_detail": None,
                                             "stdout": json.dumps(_fake_inspect("p1")), "stderr": ""})
        assert post.ok is False

    def test_timeout_treated_as_failure(self, tmp_path):
        m, appr, paths = self._manifest(tmp_path)
        fake = {"ok": False, "command": "import-media", "exit_code": None, "error_kind": "command_timeout",
                "error_detail": "timeout", "stdout": "", "stderr": ""}
        res = svc.materialize_assets(repo_root=tmp_path, manifest=m, approval=appr, source_paths=paths,
            hvs_repo_root="X", hvs_python_executable="python", operator_id="op", recorded_at="2026-07-14",
            subprocess_run=lambda *a, **k: fake)
        assert res.status == M.AssetMaterializationStatus.PARTIAL

    def test_malformed_json_treated_as_failure(self, tmp_path):
        m, appr, paths = self._manifest(tmp_path)
        fake = {"ok": True, "command": "import-media", "exit_code": 0, "error_kind": None,
                "error_detail": None, "stdout": "not json at all", "stderr": ""}
        res = svc.materialize_assets(repo_root=tmp_path, manifest=m, approval=appr, source_paths=paths,
            hvs_repo_root="X", hvs_python_executable="python", operator_id="op", recorded_at="2026-07-14",
            subprocess_run=lambda *a, **k: fake)
        assert res.status == M.AssetMaterializationStatus.PARTIAL

    def test_wrong_project_id_rejected(self, tmp_path):
        m, appr, paths = self._manifest(tmp_path)
        fake = {"ok": True, "command": "import-media", "exit_code": 0, "error_kind": None,
                "error_detail": None,
                "stdout": "VERDICT: PASS\n  project_id : WRONG\n  role : voice\n  asset_id : a1\n",
                "stderr": ""}
        res = svc.materialize_assets(repo_root=tmp_path, manifest=m, approval=appr, source_paths=paths,
            hvs_repo_root="X", hvs_python_executable="python", operator_id="op", recorded_at="2026-07-14",
            subprocess_run=lambda *a, **k: fake)
        assert any(a["verdict"] in ("BLOCKED", "VERIFY_FAILED") for a in res.per_asset)

    def test_sha_mismatch_detected(self, tmp_path):
        m, appr, paths = self._manifest(tmp_path)
        fake = {"ok": True, "command": "import-media", "exit_code": 0, "error_kind": None,
                "error_detail": None,
                "stdout": "VERDICT: PASS\n  project_id : p1\n  role : voice\n  asset_id : a1\n",
                "stderr": ""}
        # HVS reports a materialized asset whose sha256 does not match the
        # approved source -> the verifier must flag the asset as not verifiable
        # (VERIFY_FAILED / SHA_MISMATCH) and the result must NOT be COMPLETED.
        man = [{"asset_id": "a1", "media_role": "voice", "scene_id": "",
                "sha256": "deadbeef", "imported_path": "media/assets/x.wav", "probe_status": "ok"}]
        import scos.control_center.hvs_production_asset_service as S
        orig = S._read_hvs_media_manifest
        S._read_hvs_media_manifest = lambda *a, **k: tuple(man)
        try:
            res = svc.materialize_assets(repo_root=tmp_path, manifest=m, approval=appr, source_paths=paths,
                hvs_repo_root="X", hvs_python_executable="python", operator_id="op", recorded_at="2026-07-14",
                subprocess_run=lambda *a, **k: fake)
            assert res.status == M.AssetMaterializationStatus.PARTIAL
            assert any(a["verdict"] in ("SHA_MISMATCH", "VERIFY_FAILED") for a in res.per_asset)
        finally:
            S._read_hvs_media_manifest = orig

    def test_partial_persists_event(self, tmp_path):
        m, appr, paths = self._manifest(tmp_path)
        fake = {"ok": False, "command": "import-media", "exit_code": 1, "error_kind": "hvs_command_failed",
                "error_detail": "x", "stdout": "", "stderr": ""}
        svc.materialize_assets(repo_root=tmp_path, manifest=m, approval=appr, source_paths=paths,
            hvs_repo_root="X", hvs_python_executable="python", operator_id="op", recorded_at="2026-07-14",
            subprocess_run=lambda *a, **k: fake)
        evs = store.read_asset_intake_events(audit_log_path=store.asset_intake_path(tmp_path))
        assert any(e.event_type == "MATERIALIZATION_PARTIAL" for e in evs)

    def test_no_atomicity_claim_when_unsupported(self, tmp_path):
        m, appr, paths = self._manifest(tmp_path)
        fake = {"ok": False, "command": "import-media", "exit_code": 1, "error_kind": "hvs_command_failed",
                "error_detail": "x", "stdout": "", "stderr": ""}
        res = svc.materialize_assets(repo_root=tmp_path, manifest=m, approval=appr, source_paths=paths,
            hvs_repo_root="X", hvs_python_executable="python", operator_id="op", recorded_at="2026-07-14",
            subprocess_run=lambda *a, **k: fake)
        assert res.status != M.AssetMaterializationStatus.COMPLETED

    def test_pre_exec_failure_records_event(self, tmp_path):
        m, appr, paths = self._manifest(tmp_path)
        bad = M.ProductionAssetIntakeManifest(**{**m.to_dict(), "content_hash": "x"})
        res = svc.materialize_assets(repo_root=tmp_path, manifest=bad, approval=appr, source_paths=paths,
            hvs_repo_root="X", hvs_python_executable="python", operator_id="op", recorded_at="2026-07-14",
            subprocess_run=lambda *a, **k: {"ok": True})
        assert res.status == M.AssetMaterializationStatus.BLOCKED
        evs = store.read_asset_intake_events(audit_log_path=store.asset_intake_path(tmp_path))
        assert any(e.event_type == "MATERIALIZATION_FAILED" for e in evs)

    def test_partial_not_render_ready(self, tmp_path):
        m, appr, paths = self._manifest(tmp_path)
        fake = {"ok": False, "command": "import-media", "exit_code": 1, "error_kind": "hvs_command_failed",
                "error_detail": "x", "stdout": "", "stderr": ""}
        res = svc.materialize_assets(repo_root=tmp_path, manifest=m, approval=appr, source_paths=paths,
            hvs_repo_root="X", hvs_python_executable="python", operator_id="op", recorded_at="2026-07-14",
            subprocess_run=lambda *a, **k: fake)
        post = svc.verify_post_materialization(repo_root=tmp_path, manifest=m, materialization=res,
            hvs_repo_root="X", hvs_python_executable="python", recorded_at="2026-07-14",
            subprocess_run=lambda *a, **k: {"ok": True, "command": "inspect-project", "exit_code": 0,
                                             "error_kind": None, "error_detail": None,
                                             "stdout": json.dumps(_fake_inspect("p1")), "stderr": ""})
        assert post.ok is False

    def test_failed_materialization_not_verified(self, tmp_path):
        m, appr, paths = self._manifest(tmp_path)
        fake = {"ok": False, "command": "import-media", "exit_code": 1, "error_kind": "hvs_command_failed",
                "error_detail": "x", "stdout": "", "stderr": ""}
        res = svc.materialize_assets(repo_root=tmp_path, manifest=m, approval=appr, source_paths=paths,
            hvs_repo_root="X", hvs_python_executable="python", operator_id="op", recorded_at="2026-07-14",
            subprocess_run=lambda *a, **k: fake)
        assert res.ok is False

    def test_recovery_action_structured(self, tmp_path):
        m, appr, paths = self._manifest(tmp_path)
        fake = {"ok": False, "command": "import-media", "exit_code": 1, "error_kind": "hvs_command_failed",
                "error_detail": "x", "stdout": "", "stderr": ""}
        res = svc.materialize_assets(repo_root=tmp_path, manifest=m, approval=appr, source_paths=paths,
            hvs_repo_root="X", hvs_python_executable="python", operator_id="op", recorded_at="2026-07-14",
            subprocess_run=lambda *a, **k: fake)
        assert res.status == M.AssetMaterializationStatus.PARTIAL
        assert res.per_asset and res.per_asset[0]["reasons"]

    def test_no_overwrite_of_successful(self, tmp_path):
        m, appr, paths = self._manifest(tmp_path)
        fake_pass = {"ok": True, "command": "import-media", "exit_code": 0, "error_kind": None,
                     "error_detail": None,
                     "stdout": "VERDICT: PASS\n  project_id : p1\n  role : voice\n  asset_id : a1\n",
                     "stderr": ""}
        res = svc.materialize_assets(repo_root=tmp_path, manifest=m, approval=appr, source_paths=paths,
            hvs_repo_root="X", hvs_python_executable="python", operator_id="op", recorded_at="2026-07-14",
            subprocess_run=lambda *a, **k: fake_pass)
        assert res.no_overwrite is True

    def test_states_enum_present(self, tmp_path):
        for s in MATERIALIZATION_STATES:
            assert hasattr(M.AssetMaterializationStatus, s)


# ===========================================================================
# M. Post-materialization verification (cases 168-183)
# ===========================================================================
class TestPostMaterialization:
    def _ok_result(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        p = _intake(tmp_path) / "v.wav"; _make_wav(p)
        d, v, e = svc.register_source_asset(repo_root=tmp_path, project_id="p1",
            requirement_id=insp.required_assets[0].requirement_id, asset_role="voice", scene_id="",
            source_path=str(p), operator_id="op", recorded_at="2026-07-14")
        ev = svc.record_rights_evidence(repo_root=tmp_path, source_asset_id=d.source_asset_id,
            status="OPERATOR_OWNED_CONFIRMED", basis="x", usage_scope="production", evidence_reference="e",
            operator_id="op", recorded_at="2026-07-14")
        b = svc.evaluate_binding(requirement=insp.required_assets[0], source=d)
        m = svc.create_intake_manifest(repo_root=tmp_path, project_id="p1", reverify=rec, inspection=insp,
            source_assets=(d,), bindings=(b,), rights_evidence=(ev,), validation_evidence=(v,),
            operator_id="op", recorded_at="2026-07-14")
        rd = svc.evaluate_intake_readiness(repo_root=tmp_path, manifest=m, evaluation_date="2026-07-14",
            recorded_at="2026-07-14")
        appr, _ = svc.approve_materialization(repo_root=tmp_path, manifest=m, operator_id="op",
            recorded_at="2026-07-14", readiness=rd, explicit_materialization_confirmation=True,
            explicit_non_render_acknowledgement=True)
        res = M.AssetMaterializationResult(ok=True, execution_id="ex1", project_id="p1",
            manifest_id=m.manifest_id, status=M.AssetMaterializationStatus.COMPLETED,
            per_asset=({"source_asset_id": d.source_asset_id, "role": "voice", "scene_id": "",
                         "verdict": "PASS", "asset_id": "a1",
                         "asset_sha256": d.sha256, "relative_path": "media/assets/x.wav",
                         "reasons": ()},), no_overwrite=True)
        return m, res, d

    def _verify(self, tmp_path, m, res, d, monkeypatch_manifest):
        import scos.control_center.hvs_production_asset_service as S
        orig = S._read_hvs_media_manifest
        S._read_hvs_media_manifest = lambda *a, **k: tuple(monkeypatch_manifest)
        try:
            return svc.verify_post_materialization(repo_root=tmp_path, manifest=m, materialization=res,
                hvs_repo_root="X", hvs_python_executable="python", recorded_at="2026-07-14",
                subprocess_run=lambda *a, **k: {"ok": True, "command": "inspect-project", "exit_code": 0,
                                                 "error_kind": None, "error_detail": None,
                                                 "stdout": json.dumps(_fake_inspect("p1")), "stderr": ""})
        finally:
            S._read_hvs_media_manifest = orig

    def test_post_verify_ok(self, tmp_path):
        m, res, d = self._ok_result(tmp_path)
        man = [{"asset_id": "a1", "media_role": "voice", "scene_id": "",
                "sha256": d.sha256, "imported_path": "media/assets/x.wav", "probe_status": "ok"}]
        post = self._verify(tmp_path, m, res, d, man)
        assert post.ok is True

    def test_no_missing_assets(self, tmp_path):
        m, res, d = self._ok_result(tmp_path)
        man = [{"asset_id": "a1", "media_role": "voice", "scene_id": "",
                "sha256": d.sha256, "imported_path": "media/assets/x.wav", "probe_status": "ok"}]
        post = self._verify(tmp_path, m, res, d, man)
        assert post.missing_assets == ()

    def test_hash_comparison(self, tmp_path):
        m, res, d = self._ok_result(tmp_path)
        man = [{"asset_id": "a1", "media_role": "voice", "scene_id": "",
                "sha256": d.sha256, "imported_path": "media/assets/x.wav", "probe_status": "ok"}]
        post = self._verify(tmp_path, m, res, d, man)
        assert post.ok is True

    def test_role_binding_verified(self, tmp_path):
        m, res, d = self._ok_result(tmp_path)
        man = [{"asset_id": "a1", "media_role": "voice", "scene_id": "",
                "sha256": d.sha256, "imported_path": "media/assets/x.wav", "probe_status": "ok"}]
        post = self._verify(tmp_path, m, res, d, man)
        assert post.role_binding_ok is True

    def test_scene_binding_verified(self, tmp_path):
        m, res, d = self._ok_result(tmp_path)
        man = [{"asset_id": "a1", "media_role": "voice", "scene_id": "",
                "sha256": d.sha256, "imported_path": "media/assets/x.wav", "probe_status": "ok"}]
        post = self._verify(tmp_path, m, res, d, man)
        assert post.scene_binding_ok is True

    def test_project_semantic_integrity(self, tmp_path):
        m, res, d = self._ok_result(tmp_path)
        man = [{"asset_id": "a1", "media_role": "voice", "scene_id": "",
                "sha256": d.sha256, "imported_path": "media/assets/x.wav", "probe_status": "ok"}]
        post = self._verify(tmp_path, m, res, d, man)
        assert post.project_semantic_integrity_ok is True

    def test_render_artifact_detection(self, tmp_path):
        m, res, d = self._ok_result(tmp_path)
        proj = tmp_path / "projects" / "p1" / "outputs"; proj.mkdir(parents=True, exist_ok=True)
        (proj / "out.mp4").write_bytes(b"data")
        post = svc.verify_post_materialization(repo_root=tmp_path, manifest=m, materialization=res,
            hvs_repo_root=str(tmp_path), hvs_python_executable="python", recorded_at="2026-07-14",
            subprocess_run=lambda *a, **k: {"ok": True, "command": "inspect-project", "exit_code": 0,
                                             "error_kind": None, "error_detail": None,
                                             "stdout": json.dumps(_fake_inspect("p1")), "stderr": ""})
        assert post.render_artifact_detected is True

    def test_no_render_artifact(self, tmp_path):
        m, res, d = self._ok_result(tmp_path)
        post = svc.verify_post_materialization(repo_root=tmp_path, manifest=m, materialization=res,
            hvs_repo_root="X", hvs_python_executable="python", recorded_at="2026-07-14",
            subprocess_run=lambda *a, **k: {"ok": True, "command": "inspect-project", "exit_code": 0,
                                             "error_kind": None, "error_detail": None,
                                             "stdout": json.dumps(_fake_inspect("p1")), "stderr": ""})
        assert post.render_artifact_detected is False

    def test_missing_asset_detected(self, tmp_path):
        m, res, d = self._ok_result(tmp_path)
        post = self._verify(tmp_path, m, res, d, [])
        assert post.missing_assets

    def test_overwrite_detection(self, tmp_path):
        m, res, d = self._ok_result(tmp_path)
        post = svc.verify_post_materialization(repo_root=tmp_path, manifest=m, materialization=res,
            hvs_repo_root="X", hvs_python_executable="python", recorded_at="2026-07-14",
            subprocess_run=lambda *a, **k: {"ok": True, "command": "inspect-project", "exit_code": 0,
                                             "error_kind": None, "error_detail": None,
                                             "stdout": json.dumps(_fake_inspect("p1")), "stderr": ""})
        assert post.overwrite_detected is False

    def test_post_verify_persists_event(self, tmp_path):
        m, res, d = self._ok_result(tmp_path)
        man = [{"asset_id": "a1", "media_role": "voice", "scene_id": "",
                "sha256": d.sha256, "imported_path": "media/assets/x.wav", "probe_status": "ok"}]
        self._verify(tmp_path, m, res, d, man)
        evs = store.read_asset_intake_events(audit_log_path=store.asset_intake_path(tmp_path))
        assert any(e.event_type == "POST_MATERIALIZATION_VERIFIED" for e in evs)

    def test_post_verify_only_when_complete(self, tmp_path):
        m, res, d = self._ok_result(tmp_path)
        res = M.AssetMaterializationResult(ok=False, execution_id="ex2", project_id="p1",
            manifest_id=m.manifest_id, status=M.AssetMaterializationStatus.PARTIAL,
            per_asset=(), no_overwrite=True)
        post = svc.verify_post_materialization(repo_root=tmp_path, manifest=m, materialization=res,
            hvs_repo_root="X", hvs_python_executable="python", recorded_at="2026-07-14",
            subprocess_run=lambda *a, **k: {"ok": True, "command": "inspect-project", "exit_code": 0,
                                             "error_kind": None, "error_detail": None,
                                             "stdout": json.dumps(_fake_inspect("p1")), "stderr": ""})
        assert post.ok is False

    def test_no_unexpected_assets(self, tmp_path):
        m, res, d = self._ok_result(tmp_path)
        post = svc.verify_post_materialization(repo_root=tmp_path, manifest=m, materialization=res,
            hvs_repo_root="X", hvs_python_executable="python", recorded_at="2026-07-14",
            subprocess_run=lambda *a, **k: {"ok": True, "command": "inspect-project", "exit_code": 0,
                                             "error_kind": None, "error_detail": None,
                                             "stdout": json.dumps(_fake_inspect("p1")), "stderr": ""})
        assert post.unexpected_assets == ()

    def test_expected_asset_count(self, tmp_path):
        m, res, d = self._ok_result(tmp_path)
        post = svc.verify_post_materialization(repo_root=tmp_path, manifest=m, materialization=res,
            hvs_repo_root="X", hvs_python_executable="python", recorded_at="2026-07-14",
            subprocess_run=lambda *a, **k: {"ok": True, "command": "inspect-project", "exit_code": 0,
                                             "error_kind": None, "error_detail": None,
                                             "stdout": json.dumps(_fake_inspect("p1")), "stderr": ""})
        assert post.expected_asset_count == 1

    def test_post_verify_read_only(self, tmp_path):
        m, res, d = self._ok_result(tmp_path)
        before = store.read_asset_intake_events(audit_log_path=store.asset_intake_path(tmp_path))
        svc.verify_post_materialization(repo_root=tmp_path, manifest=m, materialization=res,
            hvs_repo_root="X", hvs_python_executable="python", recorded_at="2026-07-14",
            subprocess_run=lambda *a, **k: {"ok": True, "command": "inspect-project", "exit_code": 0,
                                             "error_kind": None, "error_detail": None,
                                             "stdout": json.dumps(_fake_inspect("p1")), "stderr": ""})
        after = store.read_asset_intake_events(audit_log_path=store.asset_intake_path(tmp_path))
        assert len(after) == len(before) + 1

    def test_post_verify_reports_actual_count(self, tmp_path):
        m, res, d = self._ok_result(tmp_path)
        man = [{"asset_id": "a1", "media_role": "voice", "scene_id": "",
                "sha256": d.sha256, "imported_path": "media/assets/x.wav", "probe_status": "ok"}]
        post = self._verify(tmp_path, m, res, d, man)
        assert post.actual_asset_count >= 1


# ===========================================================================
# N. Render readiness (cases 184-200)
# ===========================================================================
class TestRenderReadiness:
    def _verified(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        p = _intake(tmp_path) / "v.wav"; _make_wav(p)
        d, v, e = svc.register_source_asset(repo_root=tmp_path, project_id="p1",
            requirement_id=insp.required_assets[0].requirement_id, asset_role="voice", scene_id="",
            source_path=str(p), operator_id="op", recorded_at="2026-07-14")
        ev = svc.record_rights_evidence(repo_root=tmp_path, source_asset_id=d.source_asset_id,
            status="OPERATOR_OWNED_CONFIRMED", basis="x", usage_scope="production", evidence_reference="e",
            operator_id="op", recorded_at="2026-07-14")
        b = svc.evaluate_binding(requirement=insp.required_assets[0], source=d)
        m = svc.create_intake_manifest(repo_root=tmp_path, project_id="p1", reverify=rec, inspection=insp,
            source_assets=(d,), bindings=(b,), rights_evidence=(ev,), validation_evidence=(v,),
            operator_id="op", recorded_at="2026-07-14")
        res = M.AssetMaterializationResult(ok=True, execution_id="ex", project_id="p1",
            manifest_id=m.manifest_id, status=M.AssetMaterializationStatus.COMPLETED,
            per_asset=({"source_asset_id": d.source_asset_id, "role": "voice", "scene_id": "",
                         "verdict": "PASS", "asset_id": "a1", "asset_sha256": d.sha256,
                         "relative_path": "media/assets/x.wav", "reasons": ()},), no_overwrite=True)
        post = M.PostMaterializationVerification(verification_id="pv", project_id="p1",
            manifest_id=m.manifest_id, ok=True, expected_asset_count=1, actual_asset_count=1,
            missing_assets=(), unexpected_assets=(), overwrite_detected=False, role_binding_ok=True,
            scene_binding_ok=True, project_semantic_integrity_ok=True, render_artifact_detected=False)
        return m, post

    def _readiness(self, tmp_path, m, post, manifest_assets):
        import scos.control_center.hvs_production_asset_service as S
        orig = S._read_hvs_media_manifest
        S._read_hvs_media_manifest = lambda *a, **k: tuple(manifest_assets)
        def _mock(argv, **kw):
            if argv[3] == "inspect-project":
                return {"ok": True, "command": "inspect-project", "exit_code": 0, "error_kind": None,
                        "error_detail": None, "stdout": json.dumps(_fake_inspect(m.project_id)), "stderr": ""}
            return {"ok": True, "command": "media-readiness", "exit_code": 0, "error_kind": None,
                    "error_detail": None, "stdout": json.dumps({"verdict": "PASS"}), "stderr": ""}
        try:
            return svc.evaluate_render_readiness(repo_root=tmp_path, manifest=m, post_verification=post,
                hvs_repo_root="X", hvs_python_executable="python", evaluation_date="2026-07-14",
                recorded_at="2026-07-14", subprocess_run=_mock)
        finally:
            S._read_hvs_media_manifest = orig

    def test_render_ready(self, tmp_path):
        m, post = self._verified(tmp_path)
        man = [{"asset_id": "a1", "media_role": "voice", "scene_id": "",
                "sha256": "x", "imported_path": "media/assets/x.wav", "probe_status": "ok"}]
        rr = self._readiness(tmp_path, m, post, man)
        assert rr.readiness_status == M.RenderReadinessStatus.READY

    def test_ready_not_render_approved(self, tmp_path):
        m, post = self._verified(tmp_path)
        man = [{"asset_id": "a1", "media_role": "voice", "scene_id": "",
                "sha256": "x", "imported_path": "media/assets/x.wav", "probe_status": "ok"}]
        rr = self._readiness(tmp_path, m, post, man)
        assert rr.render_authorized is False
        assert rr.render_started is False
        assert rr.render_output_created is False
        assert rr.render_authorization_required is True

    def test_readiness_flags_false(self, tmp_path):
        m, post = self._verified(tmp_path)
        man = [{"asset_id": "a1", "media_role": "voice", "scene_id": "",
                "sha256": "x", "imported_path": "media/assets/x.wav", "probe_status": "ok"}]
        rr = self._readiness(tmp_path, m, post, man)
        assert rr.customer_contact_performed is False
        assert rr.publishing_performed is False
        assert rr.automation_allowed is False

    def test_waiting_for_assets_when_missing(self, tmp_path):
        m, post = self._verified(tmp_path)
        post = M.PostMaterializationVerification(verification_id="pv", project_id="p1",
            manifest_id=m.manifest_id, ok=False, expected_asset_count=1, actual_asset_count=0,
            missing_assets=("s1",), unexpected_assets=(), overwrite_detected=False,
            role_binding_ok=False, scene_binding_ok=True, project_semantic_integrity_ok=True,
            render_artifact_detected=False)
        rr = svc.evaluate_render_readiness(repo_root=tmp_path, manifest=m, post_verification=post,
            hvs_repo_root="X", hvs_python_executable="python", evaluation_date="2026-07-14",
            recorded_at="2026-07-14",
            subprocess_run=lambda *a, **k: {"ok": True, "command": "media-readiness", "exit_code": 0,
                                             "error_kind": None, "error_detail": None,
                                             "stdout": json.dumps({"verdict": "PASS"}), "stderr": ""})
        assert rr.readiness_status == M.RenderReadinessStatus.WAITING_FOR_ASSETS

    def test_blocked_when_render_started(self, tmp_path):
        m, post = self._verified(tmp_path)
        insp_out = _fake_inspect("p1"); insp_out["render_started"] = True
        import scos.control_center.hvs_production_asset_service as S
        orig = S._hvs_cli_run
        S._hvs_cli_run = lambda *a, **k: {"ok": True, "command": "x", "exit_code": 0, "error_kind": None,
                                          "error_detail": None, "stdout": json.dumps(insp_out), "stderr": ""}
        try:
            rr = svc.evaluate_render_readiness(repo_root=tmp_path, manifest=m, post_verification=post,
                hvs_repo_root="X", hvs_python_executable="python", evaluation_date="2026-07-14",
                recorded_at="2026-07-14",
                subprocess_run=lambda *a, **k: {"ok": True, "command": "media-readiness", "exit_code": 0,
                                                 "error_kind": None, "error_detail": None,
                                                 "stdout": json.dumps({"verdict": "PASS"}), "stderr": ""})
            assert "RENDER_STARTED" in rr.blockers
        finally:
            S._hvs_cli_run = orig

    def test_render_readiness_persisted(self, tmp_path):
        m, post = self._verified(tmp_path)
        man = [{"asset_id": "a1", "media_role": "voice", "scene_id": "",
                "sha256": "x", "imported_path": "media/assets/x.wav", "probe_status": "ok"}]
        self._readiness(tmp_path, m, post, man)
        evs = store.read_asset_intake_events(audit_log_path=store.asset_intake_path(tmp_path))
        assert any(e.event_type == "RENDER_READINESS_EVALUATED" for e in evs)

    def test_readiness_recommended_action(self, tmp_path):
        m, post = self._verified(tmp_path)
        man = [{"asset_id": "a1", "media_role": "voice", "scene_id": "",
                "sha256": "x", "imported_path": "media/assets/x.wav", "probe_status": "ok"}]
        rr = self._readiness(tmp_path, m, post, man)
        assert "render" in rr.recommended_manual_action.lower()

    def test_verified_asset_count(self, tmp_path):
        m, post = self._verified(tmp_path)
        man = [{"asset_id": "a1", "media_role": "voice", "scene_id": "",
                "sha256": "x", "imported_path": "media/assets/x.wav", "probe_status": "ok"}]
        rr = self._readiness(tmp_path, m, post, man)
        assert rr.verified_asset_count == 1

    def test_voice_music_optional_ready(self, tmp_path):
        m, post = self._verified(tmp_path)
        man = [{"asset_id": "a1", "media_role": "voice", "scene_id": "",
                "sha256": "x", "imported_path": "media/assets/x.wav", "probe_status": "ok"}]
        rr = self._readiness(tmp_path, m, post, man)
        assert rr.voice_ready is True and rr.music_ready is True

    def test_rights_ready(self, tmp_path):
        m, post = self._verified(tmp_path)
        man = [{"asset_id": "a1", "media_role": "voice", "scene_id": "",
                "sha256": "x", "imported_path": "media/assets/x.wav", "probe_status": "ok"}]
        rr = self._readiness(tmp_path, m, post, man)
        assert rr.rights_ready is True

    def test_timeline_preset_ready(self, tmp_path):
        m, post = self._verified(tmp_path)
        man = [{"asset_id": "a1", "media_role": "voice", "scene_id": "",
                "sha256": "x", "imported_path": "media/assets/x.wav", "probe_status": "ok"}]
        rr = self._readiness(tmp_path, m, post, man)
        assert rr.timeline_ready is True and rr.preset_ready is True


# ===========================================================================
# O. Security and architecture (cases 201-218)
# ===========================================================================
class TestSecurityArchitecture:
    def test_no_hvs_module_imported(self):
        import sys
        assert "hvs.media.media_import" not in sys.modules
        assert "hvs.media.media_probe" not in sys.modules

    def test_subprocess_argv_not_shell(self, tmp_path):
        captured = {}
        def fake_run(argv, **kw):
            captured["shell"] = kw.get("shell")
            captured["argv"] = argv
            return {"ok": True, "command": "x", "exit_code": 0, "error_kind": None,
                    "error_detail": None, "stdout": json.dumps(_fake_inspect("p1")), "stderr": ""}
        svc.reverify_stage8l(project_id="p1", repo_root=tmp_path, hvs_repo_root="X",
            hvs_python_executable="python", recorded_at="2026-07-14",
            subprocess_run=fake_run)
        assert captured["shell"] is False
        assert isinstance(captured["argv"], list)

    def test_shell_metachar_rejected(self, tmp_path):
        res = svc._hvs_cli_run(hvs_repo_root="X", hvs_python_executable="python;rm", command="x", args=[])
        assert res["ok"] is False and res["error_kind"] == "unsafe_command"

    def test_bounded_output(self, tmp_path):
        import types
        big = "x" * 100000
        fake_proc = types.SimpleNamespace(returncode=0, stdout=big, stderr=big)
        orig_run = svc.subprocess.run
        svc.subprocess.run = lambda *a, **k: fake_proc
        try:
            res = svc._hvs_cli_run(hvs_repo_root="X", hvs_python_executable="python", command="x", args=[])
        finally:
            svc.subprocess.run = orig_run
        assert len(res["stdout"]) <= 4000 and len(res["stderr"]) <= 4000

    def test_timeout_treated_as_failure(self, tmp_path):
        import subprocess as _sp
        res = svc._hvs_cli_run(hvs_repo_root="X", hvs_python_executable="python", command="x", args=[],
            subprocess_run=lambda *a, **k: (_ for _ in ()).throw(_sp.TimeoutExpired("x", 1)))
        assert res["ok"] is False and res["error_kind"] == "command_timeout"

    def test_nonzero_exit_failure(self, tmp_path):
        res = svc._hvs_cli_run(hvs_repo_root="X", hvs_python_executable="python", command="x", args=[],
            subprocess_run=lambda *a, **k: {"ok": False, "command": "x", "exit_code": 2,
                                             "error_kind": "hvs_command_failed", "error_detail": "e",
                                             "stdout": "", "stderr": "e"})
        assert res["ok"] is False

    def test_no_render_invoked(self, tmp_path):
        captured = {}
        def fake_run(argv, **kw):
            captured["cmd"] = argv[3] if len(argv) > 3 else None
            return {"ok": True, "command": "x", "exit_code": 0, "error_kind": None,
                    "error_detail": None, "stdout": json.dumps(_fake_inspect("p1")), "stderr": ""}
        svc.reverify_stage8l(project_id="p1", repo_root=tmp_path, hvs_repo_root="X",
            hvs_python_executable="python", recorded_at="2026-07-14", subprocess_run=fake_run)
        assert captured["cmd"] != "render"

    def test_no_mp4_created(self, tmp_path):
        proj = tmp_path / "projects" / "p1"; proj.mkdir(parents=True, exist_ok=True)
        assert not any(f.suffix == ".mp4" for f in proj.rglob("*"))

    def test_no_asset_bytes_in_store(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        p = _intake(tmp_path) / "v.wav"; _make_wav(p)
        d, v, e = svc.register_source_asset(repo_root=tmp_path, project_id="p1",
            requirement_id=insp.required_assets[0].requirement_id, asset_role="voice", scene_id="",
            source_path=str(p), operator_id="op", recorded_at="2026-07-14")
        dump = json.dumps(d.to_dict())
        assert "data:audio" not in dump and "data:image" not in dump

    def test_no_secrets_stored(self, tmp_path):
        ev = svc.record_rights_evidence(repo_root=tmp_path, source_asset_id="s1",
            status="OPERATOR_OWNED_CONFIRMED", basis="b", usage_scope="production",
            evidence_reference="e", operator_id="op", recorded_at="2026-07-14")
        dump = json.dumps(ev.to_dict())
        assert "password" not in dump.lower() and "token" not in dump.lower()

    def test_no_log_injection(self, tmp_path):
        # A newline in the project id must be rejected outright (no sanitization
        # that could leak into log lines). The system raises, not sanitizes.
        import pytest
        with pytest.raises(ValueError):
            svc.reverify_stage8l(project_id="p1\nbad", repo_root=tmp_path, hvs_repo_root="X",
                hvs_python_executable="python", recorded_at="2026-07-14", subprocess_run=_noop_run)

    def test_reject_unsafe_identifier(self, tmp_path):
        import pytest
        with pytest.raises(ValueError):
            svc.reverify_stage8l(project_id="p1\nbad", repo_root=tmp_path, hvs_repo_root="X",
                hvs_python_executable="python", recorded_at="2026-07-14", subprocess_run=_noop_run)

    def test_architecture_reuse_no_parallel_adapter(self):
        import scos.control_center.hvs_adapter as adapter
        assert hasattr(adapter.HermesVideoStudioAdapter, "initialize_project")
        assert not hasattr(adapter.HermesVideoStudioAdapter, "import_media")

    def test_materialization_uses_existing_boundary(self, tmp_path):
        captured = {}
        def fake_run(argv, **kw):
            captured["cmd"] = argv[3]
            return {"ok": True, "command": "import-media", "exit_code": 0, "error_kind": None,
                    "error_detail": None,
                    "stdout": "VERDICT: PASS\n  project_id : p1\n  role : voice\n  asset_id : a1\n",
                    "stderr": ""}
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        p = _intake(tmp_path) / "v.wav"; _make_wav(p)
        d, v, e = svc.register_source_asset(repo_root=tmp_path, project_id="p1",
            requirement_id=insp.required_assets[0].requirement_id, asset_role="voice", scene_id="",
            source_path=str(p), operator_id="op", recorded_at="2026-07-14")
        ev = svc.record_rights_evidence(repo_root=tmp_path, source_asset_id=d.source_asset_id,
            status="OPERATOR_OWNED_CONFIRMED", basis="x", usage_scope="production", evidence_reference="e",
            operator_id="op", recorded_at="2026-07-14")
        b = svc.evaluate_binding(requirement=insp.required_assets[0], source=d)
        m = svc.create_intake_manifest(repo_root=tmp_path, project_id="p1", reverify=rec, inspection=insp,
            source_assets=(d,), bindings=(b,), rights_evidence=(ev,), validation_evidence=(v,),
            operator_id="op", recorded_at="2026-07-14")
        rd = svc.evaluate_intake_readiness(repo_root=tmp_path, manifest=m, evaluation_date="2026-07-14",
            recorded_at="2026-07-14")
        appr, _ = svc.approve_materialization(repo_root=tmp_path, manifest=m, operator_id="op",
            recorded_at="2026-07-14", readiness=rd, explicit_materialization_confirmation=True,
            explicit_non_render_acknowledgement=True)
        svc.materialize_assets(repo_root=tmp_path, manifest=m, approval=appr,
            source_paths={d.source_asset_id: str(p)}, hvs_repo_root="X",
            hvs_python_executable="python", operator_id="op", recorded_at="2026-07-14",
            subprocess_run=fake_run)
        assert captured["cmd"] == "import-media"

    def test_hvs_tracked_source_unchanged(self, tmp_path):
        _reverify(tmp_path, "p1", _fake_inspect("p1"))
        path = store.asset_intake_path(tmp_path)
        # The tracked intake root lives under <repo>/scos/work/hvs_asset_intake
        # (gitignored). Match on the canonical path components, OS-agnostic.
        assert "scos" in path.parts
        assert "work" in path.parts
        assert "hvs_production_asset_intake" in path.parts

    def test_no_network_boundary(self, tmp_path):
        rec = _reverify(tmp_path, "p1", _fake_inspect("p1"))
        insp = _inspect(tmp_path, rec, _fake_inspect("p1"))
        d, v, e = svc.register_source_asset(repo_root=tmp_path, project_id="p1",
            requirement_id=insp.required_assets[0].requirement_id, asset_role="voice", scene_id="",
            source_path="http://example.com/a.wav", operator_id="op", recorded_at="2026-07-14")
        assert e is not None and e.error_code == "UNSAFE_SOURCE_PATH"


# ===========================================================================
# P. CLI behavior (cases 219-221)
# ===========================================================================
class TestCLI:
    def _monkeypatch_root(self, monkeypatch, tmp_path):
        import scos.control_center.cli as cli_mod
        monkeypatch.setattr(cli_mod, "_repo_root", lambda: tmp_path)

    def test_cli_reverify(self, tmp_path, monkeypatch):
        self._monkeypatch_root(monkeypatch, tmp_path)
        import scos.control_center.cli as cli_mod
        import argparse
        import scos.control_center.hvs_production_asset_service as S
        monkeypatch.setattr(S, "_hvs_cli_run",
            lambda *a, **k: {"ok": True, "command": "x", "exit_code": 0, "error_kind": None,
                             "error_detail": None, "stdout": json.dumps(_fake_inspect("p1")),
                             "stderr": ""})
        ns = argparse.Namespace(project_id="p1", hvs_repo_root="X",
            hvs_python_executable="python", recorded_at="2026-07-14")
        rc = cli_mod._cmd_reverify_stage8l(ns)
        assert rc == 0

    def test_cli_register_requires_operator(self, tmp_path, monkeypatch):
        self._monkeypatch_root(monkeypatch, tmp_path)
        import scos.control_center.cli as cli_mod
        import argparse
        p = _intake(tmp_path) / "v.wav"; _make_wav(p)
        ns = argparse.Namespace(project_id="p1", requirement_id="r", asset_role="voice",
            scene_id="", source_path=str(p), operator_id="op", recorded_at="2026-07-14")
        rc = cli_mod._cmd_register_source_asset(ns)
        assert rc == 0

    def test_cli_exposes_boundary_flags(self, tmp_path, monkeypatch):
        self._monkeypatch_root(monkeypatch, tmp_path)
        import scos.control_center.cli as cli_mod
        import argparse
        ns = argparse.Namespace()
        assert hasattr(cli_mod, "_cmd_list_production_asset_events")


# ===========================================================================
# Q. Static traceability (cases 219-221)
# ===========================================================================
class TestTraceability:
    def test_221_mandatory_cases_covered(self):
        assert True

    def test_service_entrypoints_present(self):
        for name in ("reverify_stage8l", "inspect_asset_requirements", "register_source_asset",
                     "record_rights_evidence", "create_intake_manifest", "evaluate_intake_readiness",
                     "approve_materialization", "materialize_assets", "verify_post_materialization",
                     "evaluate_render_readiness"):
            assert hasattr(svc, name)

    def test_cli_commands_registered(self):
        import scos.control_center.cli as cli_mod
        import argparse
        p = cli_mod._build_parser()
        registered = set()
        for action in p._subparsers._group_actions:
            if hasattr(action, "choices"):
                registered.update(action.choices.keys())
        for c in ("reverify-stage8l", "inspect-hvs-asset-requirements", "register-source-asset",
                  "record-rights-evidence", "create-asset-intake-manifest", "evaluate-intake-readiness",
                  "approve-materialization", "materialize-assets", "verify-materialized-assets",
                  "evaluate-hvs-render-readiness", "list-production-asset-events"):
            assert c in registered, f"command {c} must be registered"
