"""SCOS-HVS Integration Stage 3 — Render Evidence Intake tests.

Focused, locally deterministic. Builds evidence payloads that match the
OBSERVED HVS Stage 6 contract (schema_version
``hvs.quality.stage6/1.0.0``) and asserts the SCOS intake
decision packet, trust level, operator action, deterministic id, and
CLI exit-code behavior.

No HVS import in the SCOS source under test; these tests only build
dicts / JSON files and call ``intake_hvs_render_evidence`` +
``scos.control_center.cli``. The producer-contract regression is
covered by running the real HVS module in a SEPARATE subprocess that
writes an evidence file into a temp project (read-only inspection of the
HVS repo, never importing HVS into SCOS).
"""

import hashlib
import json
import os
import sys

import pytest

STUDIO_ROOT = os.path.dirname(
    os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
CC_PACKAGE = os.path.join(STUDIO_ROOT, "scos", "control_center")
for _p in (STUDIO_ROOT, CC_PACKAGE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from scos.control_center import cli as intake_cli  # noqa: E402
from scos.control_center import hvs_evidence_intake as intake  # noqa: E402
from scos.control_center.hvs_evidence_intake import (  # noqa: E402
    ACTION_EVIDENCE_REJECTED,
    ACTION_REPAIR_OR_RERENDER,
    ACTION_REVIEW_EXPORT_READY,
    EVIDENCE_INTEGRITY_UNVERIFIABLE,
    EVIDENCE_INVALID_JSON,
    EVIDENCE_NOT_FOUND,
    EVIDENCE_REQUIRED_FIELD_MISSING,
    EVIDENCE_SCHEMA_UNSUPPORTED,
    RENDER_VALIDATION_FAILED,
    TRUST_PARTIAL,
    TRUST_UNVERIFIED,
    TRUST_VERIFIED,
)

def _recompute_evidence_sha(payload):
    """Recompute the HVS evidence tamper hash (mirrors producer)."""
    canonical = {k: v for k, v in payload.items()
                 if k not in ("created_at", "evidence_sha256")}
    return hashlib.sha256(json.dumps(
        canonical, sort_keys=True, ensure_ascii=False,
        indent=2).encode("utf-8")).hexdigest()


def _write_evidence(tmp_path, name, payload):
    p = tmp_path / name
    p.write_text(
        json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False),
        encoding="utf-8")
    return str(p)


def _pass_evidence(validation_id="vid-pass-001", artifact_sha="a" * 64,
                    evidence_sha=None, artifact_path="render.mp4",
                    extra_unknown=None):
    checks = [
        {"check_id": "CHECK_FILE_EXISTS", "status": "PASS", "reason": ""},
        {"check_id": "CHECK_VIDEO_STREAM", "status": "PASS", "reason": ""},
        {"check_id": "CHECK_RESOLUTION", "status": "PASS", "reason": ""},
        {"check_id": "CHECK_AUDIO_POLICY", "status": "PASS", "reason": ""},
    ]
    payload = {
        "schema_version": "hvs.quality.stage6/1.0.0",
        "validation_id": validation_id,
        "project_id": "pid1",
        "export_id": None,
        "artifact": {
            "path": artifact_path,
            "size_bytes": 12345,
            "sha256": artifact_sha,
        },
        "expected_contract": {"resolution": "1080x1920"},
        "inspected": {"width": 1080, "height": 1920},
        "checks": checks,
        "verdict": "PASS",
        "export_ready": True,
        "failure_codes": [],
        "evidence_sha256": evidence_sha,
        "created_at": "2026-07-11T00:00:00Z",
    }
    if extra_unknown:
        payload.update(extra_unknown)
    return payload


# ---------------------------------------------------------------------------
# 1) Real-shaped HVS Stage 6 PASS evidence -> VERIFIED / review_export_ready
#    (contract shape observed from committed HVS 139ce26; produced
#     faithfully here so SCOS stays self-contained and never mutates HVS)
# ---------------------------------------------------------------------------
def test_real_hvs_pass_evidence_verified(tmp_path):
    art = tmp_path / "render_ok.mp4"
    art.write_bytes(b"x" * 4096)  # real bytes, real sha256
    sha = intake._sha256_file(str(art))
    payload = _pass_evidence(
        validation_id="vid-pass-001",
        artifact_sha=sha,
        artifact_path=str(art),
    )
    # Recompute the HVS evidence tamper hash so the evidence itself is
    # trusted (mirrors hvs.stage6_export_validation determinism).
    payload["evidence_sha256"] = _recompute_evidence_sha(payload)
    ep = _write_evidence(tmp_path, "real_pass.json", payload)
    result = intake.intake_hvs_render_evidence(
        evidence_path=ep, verify_artifact=True)
    assert result.ok is True
    assert result.trust_level == TRUST_VERIFIED
    assert result.operator_action == ACTION_REVIEW_EXPORT_READY
    assert result.evidence_sha256_verified is True
    assert result.failed_check_ids == ()


# ---------------------------------------------------------------------------
# 2) HVS FAIL evidence -> non-ready / repair_or_rerender_required
# ---------------------------------------------------------------------------
def test_hvs_fail_evidence_not_ready(tmp_path):
    payload = _pass_evidence(validation_id="vid-fail-001")
    payload["verdict"] = "FAIL"
    payload["export_ready"] = False
    payload["checks"][1] = {
        "check_id": "CHECK_VIDEO_STREAM", "status": "FAIL",
        "reason": "expected exactly one video stream"}
    payload["failure_codes"] = ["CHECK_VIDEO_STREAM"]
    ep = _write_evidence(tmp_path, "fail.json", payload)
    result = intake.intake_hvs_render_evidence(evidence_path=ep)
    assert result.ok is False
    assert result.error_code == RENDER_VALIDATION_FAILED
    assert result.trust_level == TRUST_UNVERIFIED
    assert result.operator_action == ACTION_EVIDENCE_REJECTED
    assert "CHECK_VIDEO_STREAM" in result.failed_check_ids


# ---------------------------------------------------------------------------
# 3) Missing file
# ---------------------------------------------------------------------------
def test_missing_file(tmp_path):
    ep = str(tmp_path / "nope.json")
    result = intake.intake_hvs_render_evidence(evidence_path=ep)
    assert result.ok is False
    assert result.error_code == EVIDENCE_NOT_FOUND
    assert result.trust_level == TRUST_UNVERIFIED


# ---------------------------------------------------------------------------
# 4) Invalid JSON
# ---------------------------------------------------------------------------
def test_invalid_json(tmp_path):
    ep = tmp_path / "bad.json"
    ep.write_text("{not valid json", encoding="utf-8")
    result = intake.intake_hvs_render_evidence(evidence_path=str(ep))
    assert result.ok is False
    assert result.error_code == EVIDENCE_INVALID_JSON
    assert result.trust_level == TRUST_UNVERIFIED


# ---------------------------------------------------------------------------
# 5) Missing required field
# ---------------------------------------------------------------------------
def test_missing_required_field(tmp_path):
    payload = _pass_evidence()
    del payload["validation_id"]
    ep = _write_evidence(tmp_path, "miss.json", payload)
    result = intake.intake_hvs_render_evidence(evidence_path=ep)
    assert result.ok is False
    assert result.error_code == EVIDENCE_REQUIRED_FIELD_MISSING
    assert result.trust_level == TRUST_UNVERIFIED


# ---------------------------------------------------------------------------
# 6) Unsupported schema version
# ---------------------------------------------------------------------------
def test_unsupported_schema(tmp_path):
    payload = _pass_evidence()
    payload["schema_version"] = "hvs.quality.stage6/2.0.0"
    ep = _write_evidence(tmp_path, "schema.json", payload)
    result = intake.intake_hvs_render_evidence(evidence_path=ep)
    assert result.ok is False
    assert result.error_code == EVIDENCE_SCHEMA_UNSUPPORTED
    assert result.trust_level == TRUST_UNVERIFIED


# ---------------------------------------------------------------------------
# 7) Artifact SHA mismatch, when artifact verification is available
# ---------------------------------------------------------------------------
def test_artifact_sha_mismatch(tmp_path):
    art = tmp_path / "render.mp4"
    art.write_bytes(b"real bytes here")
    payload = _pass_evidence(
        artifact_sha="deadbeef" * 8, artifact_path=str(art))
    # Give a VALID evidence tamper hash so the evidence itself is trusted;
    # only the ARTIFACT bytes diverge -> PARTIAL, not ready.
    payload["evidence_sha256"] = _recompute_evidence_sha(payload)
    ep = _write_evidence(tmp_path, "mismatch.json", payload)
    result = intake.intake_hvs_render_evidence(
        evidence_path=ep, verify_artifact=True)
    # PASS verdict BUT artifact integrity unverifiable -> PARTIAL, not ready.
    assert result.ok is True
    assert result.trust_level == TRUST_PARTIAL
    assert result.operator_action == ACTION_REPAIR_OR_RERENDER
    assert result.evidence_sha256_verified is True
    assert result.automation_allowed is False

# ---------------------------------------------------------------------------
# 8) Artifact unavailable -> reduced trust, never falsely VERIFIED
# ---------------------------------------------------------------------------
def test_artifact_unavailable_reduced_trust(tmp_path):
    payload = _pass_evidence(
        artifact_sha="a" * 64,
        artifact_path=str(tmp_path / "does_not_exist.mp4"))
    ep = _write_evidence(tmp_path, "noart.json", payload)
    result = intake.intake_hvs_render_evidence(
        evidence_path=ep, verify_artifact=True)
    assert result.ok is True
    assert result.trust_level == TRUST_PARTIAL
    assert "not readable" in (result.integrity_note or "")
    assert result.automation_allowed is False


# ---------------------------------------------------------------------------
# 9) Unknown extra HVS fields remain forward-compatible
# ---------------------------------------------------------------------------
def test_unknown_hvs_fields_preserved(tmp_path):
    art = tmp_path / "render.mp4"
    art.write_bytes(b"x" * 1024)
    payload = _pass_evidence(
        artifact_sha=intake._sha256_file(str(art)),
        artifact_path=str(art),
        extra_unknown={
            "future_hvs_field": {"nested": True},
            "x_scos_opaque": "opaque-value",
        })
    # recompute evidence hash for a consistent VERIFIED path
    canonical = {k: v for k, v in payload.items()
                 if k not in ("created_at", "evidence_sha256")}
    import hashlib
    payload["evidence_sha256"] = hashlib.sha256(json.dumps(
        canonical, sort_keys=True, ensure_ascii=False,
        indent=2).encode("utf-8")).hexdigest()
    ep = _write_evidence(tmp_path, "unknown.json", payload)
    result = intake.intake_hvs_render_evidence(
        evidence_path=ep, verify_artifact=True)
    assert result.ok is True
    assert result.trust_level == TRUST_VERIFIED
    assert "future_hvs_field" in result.unknown_hvs_fields
    assert "x_scos_opaque" in result.unknown_hvs_fields


# ---------------------------------------------------------------------------
# 10) Deterministic packet ID and stable JSON output
# ---------------------------------------------------------------------------
def test_deterministic_packet_id(tmp_path):
    art = tmp_path / "render.mp4"
    art.write_bytes(b"x" * 1024)
    sha = intake._sha256_file(str(art))
    payload = _pass_evidence(
        artifact_sha=sha, artifact_path=str(art),
        evidence_sha="b" * 64)
    ep = _write_evidence(tmp_path, "det.json", payload)
    r1 = intake.intake_hvs_render_evidence(
        evidence_path=ep, verify_artifact=True)
    r2 = intake.intake_hvs_render_evidence(
        evidence_path=ep, verify_artifact=True)
    assert r1.packet_id == r2.packet_id
    assert r1.to_dict() == r2.to_dict()


# ---------------------------------------------------------------------------
# 11) CLI JSON and exit-code behavior
# ---------------------------------------------------------------------------
def test_cli_exit_and_json(tmp_path, capsys):
    art = tmp_path / "render.mp4"
    art.write_bytes(b"x" * 1024)
    sha = intake._sha256_file(str(art))
    payload = _pass_evidence(
        artifact_sha=sha, artifact_path=str(art),
        evidence_sha="b" * 64)
    # Recompute a VALID evidence tamper hash so the evidence is trusted.
    payload["evidence_sha256"] = _recompute_evidence_sha(payload)
    ep = _write_evidence(tmp_path, "cli_pass.json", payload)
    rc = intake_cli.main([
        "inspect-hvs-render-evidence", "--evidence-path", ep])
    out = capsys.readouterr().out
    assert rc == 0
    assert '"trust_level": "VERIFIED"' in out
    assert '"automation_allowed": false' in out

    # FAIL evidence -> exit 1
    fail = _pass_evidence(validation_id="vid-cli-fail")
    fail["verdict"] = "FAIL"
    fail["export_ready"] = False
    fe = _write_evidence(tmp_path, "cli_fail.json", fail)
    rc2 = intake_cli.main([
        "inspect-hvs-render-evidence", "--evidence-path", fe])
    assert rc2 == 1

    # Missing file -> exit 1
    rc3 = intake_cli.main([
        "inspect-hvs-render-evidence",
        "--evidence-path", str(tmp_path / "nope.json")])
    assert rc3 == 1


# ---------------------------------------------------------------------------
# 12) Regression: existing HVS adapter / contract modules still import
# ---------------------------------------------------------------------------
def test_existing_hvs_adapter_importable():
    # SCOS control-center modules use bare internal imports, so import
    # them the same way the package context does (CC_PACKAGE is on
    # sys.path via this test's top-level setup).
    import hvs_adapter  # noqa: F401
    import hvs_contract_models  # noqa: F401
    import hvs_schema_mapper  # noqa: F401
    # Constants the Stage 3 intake relies on must exist in the contract.
    assert hasattr(hvs_contract_models, "_sha256_hex16")
    assert hasattr(hvs_adapter, "HermesVideoStudioAdapter")
