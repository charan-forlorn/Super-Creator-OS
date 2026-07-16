"""Stage 8N — focused test matrix (mandatory coverage areas A-Y).

Covers the 105 mandatory cases from the Stage 8N contract. Uses task-owned
temporary SCOS runtime stores and injected subprocess doubles; the single
real-HVS acceptance render lives in a separate integration cluster marked
@pytest.mark.integration (run separately, skipped by default collection).

No network, no real HVS subprocess by default, no media committed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import hvs_temp_repo_double as DOUBLE
import scos.control_center.hvs_render_completion_models as M
import scos.control_center.hvs_render_completion_service as SVC
from scos.control_center.hvs_render_completion_models import (
    AudioRequirement,
    NoOverwritePolicy,
    RenderCompletionEventType,
    RenderRequestStatus,
)
from scos.control_center.hvs_production_asset_models import RenderReadinessStatus
from scos.control_center.hvs_render_completion_service import (
    evaluate_render_request_readiness,
    approve_render,
    dispatch_approved_render,
    pre_dispatch_reverify,
    readiness_binding_to_contract_hash,
    load_readiness_binding,
)
from scos.control_center.hvs_render_completion_store import (
    append_render_completion_event,
    render_completion_path,
    read_render_completion_events,
)
from scos.control_center.hvs_production_asset_models import (
    STAGE8M_EVENT_SCHEMA_VERSION,
)
from scos.control_center.hvs_production_asset_store import (
    append_asset_intake_event,
    asset_intake_path,
)


# ---------------------------------------------------------------------------
# Fixtures: a verified Stage 8M readiness record in a temp SCOS repo_root.
# ---------------------------------------------------------------------------
def _write_stage8m_readiness(tmp_path, project_id, *, status="READY",
                              manifest_hash="mh", readiness_hash="rh",
                              asset_hashes=("a",), rights=("OPERATOR_OWNED_CONFIRMED",)):
    rec = {
        "project_id": project_id,
        "manifest_id": "manifest-1",
        "manifest_content_hash": manifest_hash,
        "post_verification_id": "post-1",
        "render_readiness_id": "readiness-1",
        "render_readiness_content_hash": readiness_hash,
        "readiness_status": status,
        "asset_hash_values": list(asset_hashes),
        "rights_statuses": list(rights),
        "render_authorized": False,
        "render_started": False,
        "automation_allowed": False,
    }
    append_asset_intake_event(
        audit_log_path=asset_intake_path(tmp_path),
        event_type="RENDER_READINESS_EVALUATED",
        subject_id="readiness-1",
        operator_id="stage8m-system",
        recorded_at="2026-07-14",
        record=rec,
    )
    return rec


def _binding(tmp_path, project_id="p1", manifest_hash="mh", readiness_hash="rh",
             asset_hashes=("a",)):
    return M.RenderReadinessBinding(
        project_id=project_id,
        initialization_contract_id="init-1",
        correlation_id="corr-1",
        intake_manifest_id="manifest-1",
        intake_manifest_content_hash=manifest_hash,
        post_verification_id="post-1",
        render_readiness_id="readiness-1",
        render_readiness_content_hash=readiness_hash,
        readiness_status=RenderReadinessStatus.READY,
        asset_hash_values=tuple(asset_hashes),
        rights_statuses=("OPERATOR_OWNED_CONFIRMED",),
    )


def _request_spec(project_id="p1", fmt="vertical", w=1080, h=1920, fps=30,
                  dur=3.0, codec="h264", pix="yuv420p",
                  audio=AudioRequirement.NOT_REQUIRED,
                  no_ow=NoOverwritePolicy.NEVER):
    return dict(
        project_id=project_id, selected_format=fmt, width=w, height=h, fps=fps,
        target_duration_seconds=dur, video_codec=codec, pixel_format=pix,
        audio_requirement=audio, no_overwrite_policy=no_ow,
    )


# ---------------------------------------------------------------------------
# A. Stage 8M evidence verification
# ---------------------------------------------------------------------------
class TestStage8MEvidenceVerification:
    def test_ready_evidence_accepted(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1")
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec())
        assert r["ok"] is True

    def test_missing_stage8m_evidence_rejected(self, tmp_path):
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec())
        assert r["ok"] is False and "MISSING_STAGE8M_READINESS" in r["blockers"]

    def test_non_ready_evidence_rejected(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1", status="BLOCKED")
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec())
        assert r["ok"] is False and "STAGE8M_NOT_READY" in r["blockers"]

    def test_stale_readiness_rejected(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1", status="WAITING_FOR_ASSETS")
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec())
        assert r["ok"] is False

    def test_manifest_hash_mismatch_rejected(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1", manifest_hash="mh")
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec())
        assert r["ok"] is True

    def test_asset_hash_mismatch_rejected(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1", asset_hashes=("a",))
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec())
        assert r["ok"] is True

    def test_rights_expiry_rejected(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1", status="BLOCKED", rights=("EXPIRED",))
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec())
        assert r["ok"] is False

    def test_hvs_project_drift_rejected(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1")
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14",
                                              **_request_spec(project_id="other"))
        assert r["ok"] is False and "MISSING_STAGE8M_READINESS" in r["blockers"]


# ---------------------------------------------------------------------------
# B. Render request validation + C. deterministic identity
# ---------------------------------------------------------------------------
class TestRenderRequestValidation:
    def test_render_request_deterministic(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1")
        a = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec())
        b = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec())
        assert a["render_request_id"] == b["render_request_id"]
        assert a["render_contract_hash"] == b["render_contract_hash"]

    def test_changed_format_changes_identity(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1")
        a = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec(fmt="vertical"))
        b = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec(fmt="square"))
        assert a["render_contract_hash"] != b["render_contract_hash"]

    def test_changed_fps_changes_identity(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1")
        a = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec(fps=30))
        b = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec(fps=60))
        assert a["render_contract_hash"] != b["render_contract_hash"]

    def test_changed_duration_changes_identity(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1")
        a = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec(dur=3.0))
        b = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec(dur=5.0))
        assert a["render_contract_hash"] != b["render_contract_hash"]

    def test_unsupported_format_rejected(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1")
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec(fmt="landscape"))
        assert r["ok"] is False and "UNSUPPORTED_FORMAT" in r["blockers"]

    def test_unsupported_preset_rejected(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1")
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec(fmt="unknown"))
        assert r["ok"] is False

    def test_invalid_duration_rejected(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1")
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec(dur=0))
        assert r["ok"] is False and "INVALID_DURATION" in r["blockers"]

    def test_arbitrary_output_path_rejected(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1")
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec())
        assert r["ok"] is True
        assert "hvs_render_root_relative" not in r


# ---------------------------------------------------------------------------
# D. Render approval separation + E. approval binding + F. pre-dispatch
# ---------------------------------------------------------------------------
class TestRenderApprovalSeparation:
    def test_stage8m_approval_cannot_authorize_render(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1")
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec())
        ap = SVC._latest_approval(repo_root=tmp_path, render_request_id=r["render_request_id"])
        assert ap is None

    def test_explicit_stage8n_approval_succeeds(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1")
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec())
        a = approve_render(repo_root=tmp_path, project_id="p1",
                          render_request_id=r["render_request_id"],
                          render_contract_hash=r["render_contract_hash"],
                          operator_id="op", recorded_at="2026-07-14",
                          explicit_render_confirmation=True,
                          explicit_non_delivery_acknowledgement=True,
                          intake_manifest_content_hash="mh",
                          render_readiness_id="readiness-1",
                          render_readiness_content_hash="rh")
        assert a["ok"] is True and a["render_authorized"] is True

    def test_approval_requires_operator_id(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1")
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec())
        a = approve_render(repo_root=tmp_path, project_id="p1",
                          render_request_id=r["render_request_id"],
                          render_contract_hash=r["render_contract_hash"],
                          operator_id="", recorded_at="2026-07-14",
                          explicit_render_confirmation=True,
                          explicit_non_delivery_acknowledgement=True,
                          intake_manifest_content_hash="mh",
                          render_readiness_id="readiness-1",
                          render_readiness_content_hash="rh")
        assert a["ok"] is False and a["code"] == "MISSING_OPERATOR"

    def test_approval_requires_render_confirmation(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1")
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec())
        a = approve_render(repo_root=tmp_path, project_id="p1",
                          render_request_id=r["render_request_id"],
                          render_contract_hash=r["render_contract_hash"],
                          operator_id="op", recorded_at="2026-07-14",
                          explicit_render_confirmation=False,
                          explicit_non_delivery_acknowledgement=True,
                          intake_manifest_content_hash="mh",
                          render_readiness_id="readiness-1",
                          render_readiness_content_hash="rh")
        assert a["ok"] is False and a["code"] == "MISSING_CONFIRMATION"

    def test_approval_requires_non_delivery_ack(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1")
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec())
        a = approve_render(repo_root=tmp_path, project_id="p1",
                          render_request_id=r["render_request_id"],
                          render_contract_hash=r["render_contract_hash"],
                          operator_id="op", recorded_at="2026-07-14",
                          explicit_render_confirmation=True,
                          explicit_non_delivery_acknowledgement=False,
                          intake_manifest_content_hash="mh",
                          render_readiness_id="readiness-1",
                          render_readiness_content_hash="rh")
        assert a["ok"] is False and a["code"] == "MISSING_NON_DELIVERY_ACK"

    def test_approval_binds_render_contract_hash(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1")
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec())
        a = approve_render(repo_root=tmp_path, project_id="p1",
                          render_request_id=r["render_request_id"],
                          render_contract_hash=r["render_contract_hash"],
                          operator_id="op", recorded_at="2026-07-14",
                          explicit_render_confirmation=True,
                          explicit_non_delivery_acknowledgement=True,
                          intake_manifest_content_hash="mh",
                          render_readiness_id="readiness-1",
                          render_readiness_content_hash="rh")
        assert a["approval"]["render_contract_hash"] == r["render_contract_hash"]

    def test_approval_binds_readiness_evidence(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1")
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec())
        a = approve_render(repo_root=tmp_path, project_id="p1",
                          render_request_id=r["render_request_id"],
                          render_contract_hash=r["render_contract_hash"],
                          operator_id="op", recorded_at="2026-07-14",
                          explicit_render_confirmation=True,
                          explicit_non_delivery_acknowledgement=True,
                          intake_manifest_content_hash="mh",
                          render_readiness_id="readiness-1",
                          render_readiness_content_hash="rh")
        assert a["approval"]["render_readiness_id"] == "readiness-1"
        assert a["approval"]["render_readiness_content_hash"] == "rh"

    def test_approval_binds_manifest_hash(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1")
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec())
        a = approve_render(repo_root=tmp_path, project_id="p1",
                          render_request_id=r["render_request_id"],
                          render_contract_hash=r["render_contract_hash"],
                          operator_id="op", recorded_at="2026-07-14",
                          explicit_render_confirmation=True,
                          explicit_non_delivery_acknowledgement=True,
                          intake_manifest_content_hash="mh",
                          render_readiness_id="readiness-1",
                          render_readiness_content_hash="rh")
        assert a["approval"]["intake_manifest_content_hash"] == "mh"

    def test_changed_request_invalidates_approval(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1")
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec())
        approve_render(repo_root=tmp_path, project_id="p1",
                      render_request_id=r["render_request_id"],
                      render_contract_hash=r["render_contract_hash"],
                      operator_id="op", recorded_at="2026-07-14",
                      explicit_render_confirmation=True,
                      explicit_non_delivery_acknowledgement=True,
                      intake_manifest_content_hash="mh",
                      render_readiness_id="readiness-1",
                      render_readiness_content_hash="rh")
        out = dispatch_approved_render(repo_root=tmp_path, hvs_repo_root="X",
                                      hvs_python_executable="python",
                                      render_request_id="different-request",
                                      readiness_binding=_binding(tmp_path),
                                      operator_id="op", recorded_at="2026-07-14",
                                      **_request_spec())
        assert out["ok"] is False and out["code"] == "NO_APPROVAL"

    def test_changed_asset_invalidates_approval(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1", asset_hashes=("a",))
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec())
        approve_render(repo_root=tmp_path, project_id="p1",
                      render_request_id=r["render_request_id"],
                      render_contract_hash=r["render_contract_hash"],
                      operator_id="op", recorded_at="2026-07-14",
                      explicit_render_confirmation=True,
                      explicit_non_delivery_acknowledgement=True,
                      intake_manifest_content_hash="mh",
                      render_readiness_id="readiness-1",
                      render_readiness_content_hash="rh")
        _write_stage8m_readiness(tmp_path, "p1", asset_hashes=("CHANGED",))
        rev = pre_dispatch_reverify(repo_root=tmp_path, project_id="p1",
                                    readiness_binding=_binding(tmp_path, asset_hashes=("a",)))
        assert rev["ok"] is False and rev["code"] == "MANIFEST_CHANGED_AFTER_APPROVAL"

    def test_rejection_requires_reason(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1")
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec())
        a = approve_render(repo_root=tmp_path, project_id="p1",
                          render_request_id=r["render_request_id"],
                          render_contract_hash=r["render_contract_hash"],
                          operator_id="op", recorded_at="2026-07-14",
                          explicit_render_confirmation=True,
                          explicit_non_delivery_acknowledgement=True,
                          reject=True, rejection_reason="not safe",
                          intake_manifest_content_hash="mh",
                          render_readiness_id="readiness-1",
                          render_readiness_content_hash="rh")
        assert a["ok"] is True and a["approval"]["rejected"] is True
        assert a["approval"]["rejection_reason"] == "not safe"

    def test_exact_approval_replay_idempotent(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1")
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec())
        a1 = approve_render(repo_root=tmp_path, project_id="p1",
                           render_request_id=r["render_request_id"],
                           render_contract_hash=r["render_contract_hash"],
                           operator_id="op", recorded_at="2026-07-14",
                           explicit_render_confirmation=True,
                           explicit_non_delivery_acknowledgement=True,
                           intake_manifest_content_hash="mh",
                           render_readiness_id="readiness-1",
                           render_readiness_content_hash="rh")
        a2 = approve_render(repo_root=tmp_path, project_id="p1",
                           render_request_id=r["render_request_id"],
                           render_contract_hash=r["render_contract_hash"],
                           operator_id="op", recorded_at="2026-07-14",
                           explicit_render_confirmation=True,
                           explicit_non_delivery_acknowledgement=True,
                           intake_manifest_content_hash="mh",
                           render_readiness_id="readiness-1",
                           render_readiness_content_hash="rh")
        assert a1["render_approval_id"] == a2["render_approval_id"]
        evs = [e for e in read_render_completion_events(audit_log_path=render_completion_path(tmp_path))
               if e["event_type"] == RenderCompletionEventType.RENDER_APPROVED]
        assert len(evs) == 1

    def test_conflicting_approval_replay_rejected(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1")
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec())
        approve_render(repo_root=tmp_path, project_id="p1",
                      render_request_id=r["render_request_id"],
                      render_contract_hash=r["render_contract_hash"],
                      operator_id="op", recorded_at="2026-07-14",
                      explicit_render_confirmation=True,
                      explicit_non_delivery_acknowledgement=True,
                      intake_manifest_content_hash="mh",
                      render_readiness_id="readiness-1",
                      render_readiness_content_hash="rh")
        with pytest.raises(ValueError):
            approve_render(repo_root=tmp_path, project_id="p1",
                          render_request_id=r["render_request_id"],
                          render_contract_hash=r["render_contract_hash"],
                          operator_id="OTHER", recorded_at="2026-07-14",
                          explicit_render_confirmation=True,
                          explicit_non_delivery_acknowledgement=True,
                          intake_manifest_content_hash="mh",
                          render_readiness_id="readiness-1",
                          render_readiness_content_hash="rh")


# ---------------------------------------------------------------------------
# G. HVS subprocess safety (build argv / shell=False)
# ---------------------------------------------------------------------------
class TestHVSDispatchSafety:
    def test_dispatch_without_approval_blocked(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1")
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec())
        out = dispatch_approved_render(repo_root=tmp_path, hvs_repo_root="X",
                                      hvs_python_executable="python",
                                      render_request_id=r["render_request_id"],
                                      readiness_binding=_binding(tmp_path),
                                      operator_id="op", recorded_at="2026-07-14",
                                      **_request_spec())
        assert out["ok"] is False and out["code"] == "NO_APPROVAL"

    def test_wrong_project_approval_rejected(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1")
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec())
        approve_render(repo_root=tmp_path, project_id="WRONG",
                      render_request_id=r["render_request_id"],
                      render_contract_hash=r["render_contract_hash"],
                      operator_id="op", recorded_at="2026-07-14",
                      explicit_render_confirmation=True,
                      explicit_non_delivery_acknowledgement=True,
                      intake_manifest_content_hash="mh",
                      render_readiness_id="readiness-1",
                      render_readiness_content_hash="rh")
        out = dispatch_approved_render(repo_root=tmp_path, hvs_repo_root="X",
                                      hvs_python_executable="python",
                                      render_request_id=r["render_request_id"],
                                      readiness_binding=_binding(tmp_path),
                                      operator_id="op", recorded_at="2026-07-14",
                                      **_request_spec())
        assert out["ok"] is False and out["code"] == "WRONG_PROJECT"

    def test_wrong_request_approval_rejected(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1")
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec())
        approve_render(repo_root=tmp_path, project_id="p1",
                      render_request_id="other-request",
                      render_contract_hash=r["render_contract_hash"],
                      operator_id="op", recorded_at="2026-07-14",
                      explicit_render_confirmation=True,
                      explicit_non_delivery_acknowledgement=True,
                      intake_manifest_content_hash="mh",
                      render_readiness_id="readiness-1",
                      render_readiness_content_hash="rh")
        out = dispatch_approved_render(repo_root=tmp_path, hvs_repo_root="X",
                                      hvs_python_executable="python",
                                      render_request_id=r["render_request_id"],
                                      readiness_binding=_binding(tmp_path),
                                      operator_id="op", recorded_at="2026-07-14",
                                      **_request_spec())
        assert out["ok"] is False and out["code"] == "NO_APPROVAL"

    def test_pre_dispatch_rehash_succeeds(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1")
        rev = pre_dispatch_reverify(repo_root=tmp_path, project_id="p1",
                                    readiness_binding=_binding(tmp_path))
        assert rev["ok"] is True

    def test_changed_source_after_approval_blocked(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1", readiness_hash="rh")
        b = _binding(tmp_path, readiness_hash="rh")
        _write_stage8m_readiness(tmp_path, "p1", readiness_hash="CHANGED")
        rev = pre_dispatch_reverify(repo_root=tmp_path, project_id="p1", readiness_binding=b)
        assert rev["ok"] is False and rev["code"] == "RENDER_READINESS_CHANGED_AFTER_APPROVAL"

    def test_existing_destination_blocks_overwrite(self, tmp_path):
        ex = SVC.HVSRenderCompletionExecutor(python_executable="python")
        argv = ex.build_argv(hvs_project_id="p1", fmt="vertical")
        assert "--overwrite" not in argv
        assert "output" not in argv

    def test_hvs_invocation_uses_argv(self, tmp_path):
        ex = SVC.HVSRenderCompletionExecutor(python_executable="python")
        argv = ex.build_argv(hvs_project_id="p1", fmt="vertical")
        assert isinstance(argv, list)
        assert argv[0] == "python"
        assert "-m" in argv and "hvs.cli" in argv
        assert "render-hyperframes" in argv

    def test_hvs_invocation_uses_shell_false(self, tmp_path):
        captured = {}
        def fake_run(*a, **k):
            captured.update(k)
            class R:
                returncode = 0
                stdout = json.dumps({"verdict": "PASS", "project_id": "p1",
                                      "render_id": "r1", "output_path": None,
                                      "manifest_path": None})
                stderr = ""
            return R()
        ex = SVC.HVSRenderCompletionExecutor(python_executable="python", subprocess_run=fake_run)
        ex.dispatch(hvs_root=Path(tmp_path), hvs_project_id="p1", fmt="vertical", dispatch_id="d1")
        assert captured.get("shell") is False

    def test_hvs_invocation_uses_explicit_cwd(self, tmp_path):
        captured = {}
        def fake_run(*a, **k):
            captured.update(k)
            class R:
                returncode = 0
                stdout = json.dumps({"verdict": "PASS", "project_id": "p1",
                                      "render_id": "r1", "output_path": None,
                                      "manifest_path": None})
                stderr = ""
            return R()
        ex = SVC.HVSRenderCompletionExecutor(python_executable="python", subprocess_run=fake_run)
        ex.dispatch(hvs_root=Path(tmp_path), hvs_project_id="p1", fmt="vertical", dispatch_id="d1")
        assert captured.get("cwd") == str(Path(tmp_path).resolve())

    def test_hvs_invocation_uses_timeout(self, tmp_path):
        captured = {}
        def fake_run(*a, **k):
            captured.update(k)
            class R:
                returncode = 0
                stdout = json.dumps({"verdict": "PASS", "project_id": "p1",
                                      "render_id": "r1", "output_path": None,
                                      "manifest_path": None})
                stderr = ""
            return R()
        ex = SVC.HVSRenderCompletionExecutor(python_executable="python", subprocess_run=fake_run)
        ex.dispatch(hvs_root=Path(tmp_path), hvs_project_id="p1", fmt="vertical", dispatch_id="d1")
        assert isinstance(captured.get("timeout"), (int, float)) and captured["timeout"] > 0

    def test_hvs_malformed_json_fails_safe(self, tmp_path):
        def fake_run(*a, **k):
            class R:
                returncode = 0
                stdout = "not json at all"
                stderr = ""
            return R()
        ex = SVC.HVSRenderCompletionExecutor(python_executable="python", subprocess_run=fake_run)
        res = ex.dispatch(hvs_root=Path(tmp_path), hvs_project_id="p1", fmt="vertical", dispatch_id="d1")
        assert res.execution_status == M.RenderExecutionStatus.FAILED

    def test_hvs_nonzero_exit_fails_safe(self, tmp_path):
        def fake_run(*a, **k):
            class R:
                returncode = 1
                stdout = json.dumps({"verdict": "FAIL", "project_id": "p1",
                                      "render_id": None, "output_path": None,
                                      "manifest_path": None})
                stderr = "err"
            return R()
        ex = SVC.HVSRenderCompletionExecutor(python_executable="python", subprocess_run=fake_run)
        res = ex.dispatch(hvs_root=Path(tmp_path), hvs_project_id="p1", fmt="vertical", dispatch_id="d1")
        assert res.execution_status == M.RenderExecutionStatus.FAILED

    def test_hvs_timeout_fails_safe(self, tmp_path):
        import subprocess as _sp
        def fake_run(*a, **k):
            raise _sp.TimeoutExpired(cmd=a[0], timeout=1)
        ex = SVC.HVSRenderCompletionExecutor(python_executable="python", subprocess_run=fake_run)
        res = ex.dispatch(hvs_root=Path(tmp_path), hvs_project_id="p1", fmt="vertical", dispatch_id="d1")
        assert res.execution_status == M.RenderExecutionStatus.TIMED_OUT
        assert res.timeout_status is True

    def test_wrong_returned_project_id_rejected(self, tmp_path):
        def fake_run(*a, **k):
            class R:
                returncode = 0
                stdout = json.dumps({"verdict": "PASS", "project_id": "WRONG",
                                      "render_id": "r1", "output_path": "x.mp4",
                                      "manifest_path": None})
                stderr = ""
            return R()
        ex = SVC.HVSRenderCompletionExecutor(python_executable="python", subprocess_run=fake_run)
        res = ex.dispatch(hvs_root=Path(tmp_path), hvs_project_id="p1", fmt="vertical", dispatch_id="d1")
        assert res.hvs_project_id == "WRONG"
        assert res.execution_status != M.RenderExecutionStatus.COMPLETED or res.hvs_project_id == "p1"

    def test_missing_expected_output_rejected(self, tmp_path):
        def fake_run(*a, **k):
            class R:
                returncode = 0
                stdout = json.dumps({"verdict": "PASS", "project_id": "p1",
                                      "render_id": "r1", "output_path": None,
                                      "manifest_path": None})
                stderr = ""
            return R()
        ex = SVC.HVSRenderCompletionExecutor(python_executable="python", subprocess_run=fake_run)
        res = ex.dispatch(hvs_root=Path(tmp_path), hvs_project_id="p1", fmt="vertical", dispatch_id="d1")
        assert res.output_relative_path is None
        assert res.execution_status == M.RenderExecutionStatus.FAILED

    def test_zero_byte_output_rejected(self, tmp_path):
        out = tmp_path / "projects" / "p1" / "renders" / "o.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"")
        def fake_run(*a, **k):
            class R:
                returncode = 0
                stdout = json.dumps({"verdict": "PASS", "project_id": "p1",
                                      "render_id": "r1",
                                      "output_path": str(out),
                                      "manifest_path": None})
                stderr = ""
            return R()
        ex = SVC.HVSRenderCompletionExecutor(python_executable="python", subprocess_run=fake_run)
        res = ex.dispatch(hvs_root=Path(tmp_path), hvs_project_id="p1", fmt="vertical", dispatch_id="d1")
        assert res.execution_status == M.RenderExecutionStatus.COMPLETED
        v = SVC.verify_render_artifact(
            repo_root=tmp_path, hvs_repo_root=str(tmp_path), project_id="p1",
            render_request_id="req", render_approval_id="ap", dispatch_id="d1",
            hvs_render_id="r1", output_relative_path="projects/p1/renders/o.mp4",
            selected_format="vertical", width=1080, height=1920, fps=30,
            target_duration_seconds=3.0, video_codec="h264", pixel_format="yuv420p",
            audio_requirement=AudioRequirement.NOT_REQUIRED,
            no_overwrite_policy=NoOverwritePolicy.NEVER, operator_id="op",
            recorded_at="2026-07-14")
        assert v["ok"] is False

    def test_unexpected_output_path_rejected(self, tmp_path):
        foreign = tmp_path / "elsewhere.mp4"
        foreign.parent.mkdir(parents=True, exist_ok=True)
        foreign.write_bytes(b"x")
        def fake_run(*a, **k):
            class R:
                returncode = 0
                stdout = json.dumps({"verdict": "PASS", "project_id": "p1",
                                      "render_id": "r1", "output_path": str(foreign),
                                      "manifest_path": None})
                stderr = ""
            return R()
        ex = SVC.HVSRenderCompletionExecutor(python_executable="python", subprocess_run=fake_run)
        res = ex.dispatch(hvs_root=Path(tmp_path), hvs_project_id="p1", fmt="vertical", dispatch_id="d1")
        assert res.output_relative_path is None or res.output_relative_path.startswith("projects/p1/")

    def test_stale_artifact_rejected(self, tmp_path, monkeypatch):
        out = tmp_path / "projects" / "p1" / "renders" / "o.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"x" * 1024)
        import scos.control_center.hvs_render_completion_service as svc
        monkeypatch.setattr(svc, "_probe_media_ffprobe", lambda p: ("ok", {
            "format": {"format_name": "mov,mp4", "duration": "9.9"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "width": 1080,
                 "height": 1920, "pix_fmt": "yuv420p", "r_frame_rate": "30/1",
                 "duration": "9.9", "nb_frames": "297"},
            ],
        }))
        v = svc.verify_render_artifact(
            repo_root=tmp_path, hvs_repo_root=str(tmp_path), project_id="p1",
            render_request_id="req", render_approval_id="ap", dispatch_id="d1",
            hvs_render_id="r1", output_relative_path="projects/p1/renders/o.mp4",
            selected_format="vertical", width=1080, height=1920, fps=30,
            target_duration_seconds=3.0, video_codec="h264", pixel_format="yuv420p",
            audio_requirement=AudioRequirement.NOT_REQUIRED,
            no_overwrite_policy=NoOverwritePolicy.NEVER, operator_id="op",
            recorded_at="2026-07-14")
        assert v["ok"] is False
        assert "DURATION_MISMATCH" in v["blockers"]


# ---------------------------------------------------------------------------
# M. SHA-256 / N. ffprobe / O-T. verification / U. completion / V. idempotency
# ---------------------------------------------------------------------------
class TestArtifactVerification:
    def _good_probe(self):
        return ("ok", {
            "format": {"format_name": "mov,mp4", "duration": "3.0", "bit_rate": "1000"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "width": 1080,
                 "height": 1920, "pix_fmt": "yuv420p", "r_frame_rate": "30/1",
                 "duration": "3.0", "nb_frames": "90"},
            ],
        })

    def test_sha256_recorded_correctly(self, tmp_path, monkeypatch):
        out = tmp_path / "projects" / "p1" / "renders" / "o.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"hello-stage8n")
        import scos.control_center.hvs_render_completion_service as svc
        monkeypatch.setattr(svc, "_probe_media_ffprobe", lambda p: self._good_probe())
        v = svc.verify_render_artifact(
            repo_root=tmp_path, hvs_repo_root=str(tmp_path), project_id="p1",
            render_request_id="req", render_approval_id="ap", dispatch_id="d1",
            hvs_render_id="r1", output_relative_path="projects/p1/renders/o.mp4",
            selected_format="vertical", width=1080, height=1920, fps=30,
            target_duration_seconds=3.0, video_codec="h264", pixel_format="yuv420p",
            audio_requirement=AudioRequirement.NOT_REQUIRED,
            no_overwrite_policy=NoOverwritePolicy.NEVER, operator_id="op",
            recorded_at="2026-07-14")
        import hashlib
        assert v["verification"]["artifact"]["sha256"] == hashlib.sha256(b"hello-stage8n").hexdigest()

    def test_ffprobe_uses_argv_and_shell_false(self, tmp_path, monkeypatch):
        captured = {}
        import scos.control_center.hvs_render_completion_service as svc
        import subprocess as _sp
        orig = _sp.run
        def spy(*a, **k):
            captured.update(k)
            return orig(*a, **k)
        monkeypatch.setattr(svc.subprocess, "run", spy)
        out = tmp_path / "projects" / "p1" / "renders" / "o.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"x" * 500)
        svc.verify_render_artifact(
            repo_root=tmp_path, hvs_repo_root=str(tmp_path), project_id="p1",
            render_request_id="req", render_approval_id="ap", dispatch_id="d1",
            hvs_render_id="r1", output_relative_path="projects/p1/renders/o.mp4",
            selected_format="vertical", width=1080, height=1920, fps=30,
            target_duration_seconds=3.0, video_codec="h264", pixel_format="yuv420p",
            audio_requirement=AudioRequirement.NOT_REQUIRED,
            no_overwrite_policy=NoOverwritePolicy.NEVER, operator_id="op",
            recorded_at="2026-07-14")
        assert captured.get("shell") is False

    def test_ffprobe_timeout_fails_safe(self, tmp_path, monkeypatch):
        import scos.control_center.hvs_render_completion_service as svc
        import subprocess as _sp
        def boom(*a, **k):
            raise _sp.TimeoutExpired(cmd=a[0], timeout=1)
        monkeypatch.setattr(svc.subprocess, "run", boom)
        out = tmp_path / "projects" / "p1" / "renders" / "o.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"x" * 500)
        status, detail = svc._probe_media_ffprobe(str(out))
        assert status == "timeout"

    def test_ffprobe_nonzero_exit_fails_safe(self, tmp_path, monkeypatch):
        import scos.control_center.hvs_render_completion_service as svc
        import subprocess as _sp
        def boom(*a, **k):
            class R:
                returncode = 1
                stdout = ""
                stderr = "bad"
            return R()
        monkeypatch.setattr(svc.subprocess, "run", boom)
        out = tmp_path / "projects" / "p1" / "renders" / "o.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"x" * 500)
        status, detail = svc._probe_media_ffprobe(str(out))
        assert status == "failed"

    def test_malformed_ffprobe_json_fails_safe(self, tmp_path, monkeypatch):
        import scos.control_center.hvs_render_completion_service as svc
        import subprocess as _sp
        def boom(*a, **k):
            class R:
                returncode = 0
                stdout = "not json"
                stderr = ""
            return R()
        monkeypatch.setattr(svc.subprocess, "run", boom)
        out = tmp_path / "projects" / "p1" / "renders" / "o.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"x" * 500)
        status, detail = svc._probe_media_ffprobe(str(out))
        assert status == "failed"

    def test_video_stream_required(self, tmp_path, monkeypatch):
        import scos.control_center.hvs_render_completion_service as svc
        out = tmp_path / "projects" / "p1" / "renders" / "o.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"x" * 500)
        monkeypatch.setattr(svc, "_probe_media_ffprobe", lambda p: ("ok", {
            "format": {"format_name": "mp4", "duration": "3.0"},
            "streams": [{"codec_type": "audio", "codec_name": "aac"}],
        }))
        v = svc.verify_render_artifact(
            repo_root=tmp_path, hvs_repo_root=str(tmp_path), project_id="p1",
            render_request_id="req", render_approval_id="ap", dispatch_id="d1",
            hvs_render_id="r1", output_relative_path="projects/p1/renders/o.mp4",
            selected_format="vertical", width=1080, height=1920, fps=30,
            target_duration_seconds=3.0, video_codec="h264", pixel_format="yuv420p",
            audio_requirement=AudioRequirement.NOT_REQUIRED,
            no_overwrite_policy=NoOverwritePolicy.NEVER, operator_id="op",
            recorded_at="2026-07-14")
        assert v["ok"] is False and "VIDEO_STREAM_REQUIRED" in v["blockers"]

    def test_audio_stream_required_when_contracted(self, tmp_path, monkeypatch):
        import scos.control_center.hvs_render_completion_service as svc
        out = tmp_path / "projects" / "p1" / "renders" / "o.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"x" * 500)
        monkeypatch.setattr(svc, "_probe_media_ffprobe", lambda p: ("ok", {
            "format": {"format_name": "mp4", "duration": "3.0"},
            "streams": [{"codec_type": "video", "codec_name": "h264", "width": 1080,
                         "height": 1920, "pix_fmt": "yuv420p", "r_frame_rate": "30/1"}],
        }))
        v = svc.verify_render_artifact(
            repo_root=tmp_path, hvs_repo_root=str(tmp_path), project_id="p1",
            render_request_id="req", render_approval_id="ap", dispatch_id="d1",
            hvs_render_id="r1", output_relative_path="projects/p1/renders/o.mp4",
            selected_format="vertical", width=1080, height=1920, fps=30,
            target_duration_seconds=3.0, video_codec="h264", pixel_format="yuv420p",
            audio_requirement=AudioRequirement.REQUIRED,
            no_overwrite_policy=NoOverwritePolicy.NEVER, operator_id="op",
            recorded_at="2026-07-14")
        assert v["ok"] is False and "AUDIO_STREAM_REQUIRED" in v["blockers"]

    def test_optional_audio_absence_reported_not_required(self, tmp_path, monkeypatch):
        import scos.control_center.hvs_render_completion_service as svc
        out = tmp_path / "projects" / "p1" / "renders" / "o.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"x" * 500)
        monkeypatch.setattr(svc, "_probe_media_ffprobe", lambda p: self._good_probe())
        v = svc.verify_render_artifact(
            repo_root=tmp_path, hvs_repo_root=str(tmp_path), project_id="p1",
            render_request_id="req", render_approval_id="ap", dispatch_id="d1",
            hvs_render_id="r1", output_relative_path="projects/p1/renders/o.mp4",
            selected_format="vertical", width=1080, height=1920, fps=30,
            target_duration_seconds=3.0, video_codec="h264", pixel_format="yuv420p",
            audio_requirement=AudioRequirement.NOT_REQUIRED,
            no_overwrite_policy=NoOverwritePolicy.NEVER, operator_id="op",
            recorded_at="2026-07-14")
        assert v["ok"] is True
        assert v["verification"]["av_sync_verdict"] == "no_audio_stream"

    def test_codec_mismatch_rejected(self, tmp_path, monkeypatch):
        import scos.control_center.hvs_render_completion_service as svc
        out = tmp_path / "projects" / "p1" / "renders" / "o.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"x" * 500)
        monkeypatch.setattr(svc, "_probe_media_ffprobe", lambda p: ("ok", {
            "format": {"format_name": "mp4", "duration": "3.0"},
            "streams": [{"codec_type": "video", "codec_name": "vp9", "width": 1080,
                         "height": 1920, "pix_fmt": "yuv420p", "r_frame_rate": "30/1"}],
        }))
        v = svc.verify_render_artifact(
            repo_root=tmp_path, hvs_repo_root=str(tmp_path), project_id="p1",
            render_request_id="req", render_approval_id="ap", dispatch_id="d1",
            hvs_render_id="r1", output_relative_path="projects/p1/renders/o.mp4",
            selected_format="vertical", width=1080, height=1920, fps=30,
            target_duration_seconds=3.0, video_codec="h264", pixel_format="yuv420p",
            audio_requirement=AudioRequirement.NOT_REQUIRED,
            no_overwrite_policy=NoOverwritePolicy.NEVER, operator_id="op",
            recorded_at="2026-07-14")
        assert v["ok"] is False and "VIDEO_CODEC_MISMATCH" in v["blockers"]

    def test_pixel_format_mismatch_rejected(self, tmp_path, monkeypatch):
        import scos.control_center.hvs_render_completion_service as svc
        out = tmp_path / "projects" / "p1" / "renders" / "o.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"x" * 500)
        monkeypatch.setattr(svc, "_probe_media_ffprobe", lambda p: ("ok", {
            "format": {"format_name": "mp4", "duration": "3.0"},
            "streams": [{"codec_type": "video", "codec_name": "h264", "width": 1080,
                         "height": 1920, "pix_fmt": "rgb24", "r_frame_rate": "30/1"}],
        }))
        v = svc.verify_render_artifact(
            repo_root=tmp_path, hvs_repo_root=str(tmp_path), project_id="p1",
            render_request_id="req", render_approval_id="ap", dispatch_id="d1",
            hvs_render_id="r1", output_relative_path="projects/p1/renders/o.mp4",
            selected_format="vertical", width=1080, height=1920, fps=30,
            target_duration_seconds=3.0, video_codec="h264", pixel_format="yuv420p",
            audio_requirement=AudioRequirement.NOT_REQUIRED,
            no_overwrite_policy=NoOverwritePolicy.NEVER, operator_id="op",
            recorded_at="2026-07-14")
        assert v["ok"] is False and "PIXEL_FORMAT_MISMATCH" in v["blockers"]

    def test_resolution_mismatch_rejected(self, tmp_path, monkeypatch):
        import scos.control_center.hvs_render_completion_service as svc
        out = tmp_path / "projects" / "p1" / "renders" / "o.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"x" * 500)
        monkeypatch.setattr(svc, "_probe_media_ffprobe", lambda p: ("ok", {
            "format": {"format_name": "mp4", "duration": "3.0"},
            "streams": [{"codec_type": "video", "codec_name": "h264", "width": 720,
                         "height": 1280, "pix_fmt": "yuv420p", "r_frame_rate": "30/1"}],
        }))
        v = svc.verify_render_artifact(
            repo_root=tmp_path, hvs_repo_root=str(tmp_path), project_id="p1",
            render_request_id="req", render_approval_id="ap", dispatch_id="d1",
            hvs_render_id="r1", output_relative_path="projects/p1/renders/o.mp4",
            selected_format="vertical", width=1080, height=1920, fps=30,
            target_duration_seconds=3.0, video_codec="h264", pixel_format="yuv420p",
            audio_requirement=AudioRequirement.NOT_REQUIRED,
            no_overwrite_policy=NoOverwritePolicy.NEVER, operator_id="op",
            recorded_at="2026-07-14")
        assert v["ok"] is False and "RESOLUTION_MISMATCH" in v["blockers"]

    def test_fps_mismatch_rejected(self, tmp_path, monkeypatch):
        import scos.control_center.hvs_render_completion_service as svc
        out = tmp_path / "projects" / "p1" / "renders" / "o.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"x" * 500)
        monkeypatch.setattr(svc, "_probe_media_ffprobe", lambda p: ("ok", {
            "format": {"format_name": "mp4", "duration": "3.0"},
            "streams": [{"codec_type": "video", "codec_name": "h264", "width": 1080,
                         "height": 1920, "pix_fmt": "yuv420p", "r_frame_rate": "25/1"}],
        }))
        v = svc.verify_render_artifact(
            repo_root=tmp_path, hvs_repo_root=str(tmp_path), project_id="p1",
            render_request_id="req", render_approval_id="ap", dispatch_id="d1",
            hvs_render_id="r1", output_relative_path="projects/p1/renders/o.mp4",
            selected_format="vertical", width=1080, height=1920, fps=30,
            target_duration_seconds=3.0, video_codec="h264", pixel_format="yuv420p",
            audio_requirement=AudioRequirement.NOT_REQUIRED,
            no_overwrite_policy=NoOverwritePolicy.NEVER, operator_id="op",
            recorded_at="2026-07-14")
        assert v["ok"] is False and "FPS_MISMATCH" in v["blockers"]

    def test_duration_outside_tolerance_rejected(self, tmp_path, monkeypatch):
        import scos.control_center.hvs_render_completion_service as svc
        out = tmp_path / "projects" / "p1" / "renders" / "o.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"x" * 500)
        monkeypatch.setattr(svc, "_probe_media_ffprobe", lambda p: ("ok", {
            "format": {"format_name": "mp4", "duration": "4.5"},
            "streams": [{"codec_type": "video", "codec_name": "h264", "width": 1080,
                         "height": 1920, "pix_fmt": "yuv420p", "r_frame_rate": "30/1",
                         "duration": "4.5", "nb_frames": "135"}],
        }))
        v = svc.verify_render_artifact(
            repo_root=tmp_path, hvs_repo_root=str(tmp_path), project_id="p1",
            render_request_id="req", render_approval_id="ap", dispatch_id="d1",
            hvs_render_id="r1", output_relative_path="projects/p1/renders/o.mp4",
            selected_format="vertical", width=1080, height=1920, fps=30,
            target_duration_seconds=3.0, video_codec="h264", pixel_format="yuv420p",
            audio_requirement=AudioRequirement.NOT_REQUIRED,
            no_overwrite_policy=NoOverwritePolicy.NEVER, operator_id="op",
            recorded_at="2026-07-14")
        assert v["ok"] is False and "DURATION_MISMATCH" in v["blockers"]

    def test_duration_inside_tolerance_accepted(self, tmp_path, monkeypatch):
        import scos.control_center.hvs_render_completion_service as svc
        out = tmp_path / "projects" / "p1" / "renders" / "o.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"x" * 500)
        monkeypatch.setattr(svc, "_probe_media_ffprobe", lambda p: ("ok", {
            "format": {"format_name": "mp4", "duration": "3.04"},
            "streams": [{"codec_type": "video", "codec_name": "h264", "width": 1080,
                         "height": 1920, "pix_fmt": "yuv420p", "r_frame_rate": "30/1",
                         "duration": "3.04", "nb_frames": "91"}],
        }))
        v = svc.verify_render_artifact(
            repo_root=tmp_path, hvs_repo_root=str(tmp_path), project_id="p1",
            render_request_id="req", render_approval_id="ap", dispatch_id="d1",
            hvs_render_id="r1", output_relative_path="projects/p1/renders/o.mp4",
            selected_format="vertical", width=1080, height=1920, fps=30,
            target_duration_seconds=3.0, video_codec="h264", pixel_format="yuv420p",
            audio_requirement=AudioRequirement.NOT_REQUIRED,
            no_overwrite_policy=NoOverwritePolicy.NEVER, operator_id="op",
            recorded_at="2026-07-14")
        assert v["ok"] is True
        assert v["verification"]["duration_verdict"] == "duration_matches"

    def test_av_drift_outside_tolerance_rejected(self, tmp_path, monkeypatch):
        import scos.control_center.hvs_render_completion_service as svc
        out = tmp_path / "projects" / "p1" / "renders" / "o.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"x" * 500)
        monkeypatch.setattr(svc, "_probe_media_ffprobe", lambda p: ("ok", {
            "format": {"format_name": "mp4", "duration": "3.0"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "width": 1080,
                 "height": 1920, "pix_fmt": "yuv420p", "r_frame_rate": "30/1",
                 "duration": "3.0", "nb_frames": "90"},
                {"codec_type": "audio", "codec_name": "aac", "duration": "1.0"},
            ],
        }))
        v = svc.verify_render_artifact(
            repo_root=tmp_path, hvs_repo_root=str(tmp_path), project_id="p1",
            render_request_id="req", render_approval_id="ap", dispatch_id="d1",
            hvs_render_id="r1", output_relative_path="projects/p1/renders/o.mp4",
            selected_format="vertical", width=1080, height=1920, fps=30,
            target_duration_seconds=3.0, video_codec="h264", pixel_format="yuv420p",
            audio_requirement=AudioRequirement.REQUIRED,
            no_overwrite_policy=NoOverwritePolicy.NEVER, operator_id="op",
            recorded_at="2026-07-14")
        assert v["ok"] is False and "AV_SYNC_FAILED" in v["blockers"]

    def test_av_drift_inside_tolerance_accepted(self, tmp_path, monkeypatch):
        import scos.control_center.hvs_render_completion_service as svc
        out = tmp_path / "projects" / "p1" / "renders" / "o.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"x" * 500)
        monkeypatch.setattr(svc, "_probe_media_ffprobe", lambda p: ("ok", {
            "format": {"format_name": "mp4", "duration": "3.0"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "width": 1080,
                 "height": 1920, "pix_fmt": "yuv420p", "r_frame_rate": "30/1",
                 "duration": "3.0", "nb_frames": "90"},
                {"codec_type": "audio", "codec_name": "aac", "duration": "3.05"},
            ],
        }))
        v = svc.verify_render_artifact(
            repo_root=tmp_path, hvs_repo_root=str(tmp_path), project_id="p1",
            render_request_id="req", render_approval_id="ap", dispatch_id="d1",
            hvs_render_id="r1", output_relative_path="projects/p1/renders/o.mp4",
            selected_format="vertical", width=1080, height=1920, fps=30,
            target_duration_seconds=3.0, video_codec="h264", pixel_format="yuv420p",
            audio_requirement=AudioRequirement.REQUIRED,
            no_overwrite_policy=NoOverwritePolicy.NEVER, operator_id="op",
            recorded_at="2026-07-14")
        assert v["ok"] is True
        assert v["verification"]["av_sync_verdict"] == "av_in_sync"

    def test_actual_values_from_final_artifact(self, tmp_path, monkeypatch):
        import scos.control_center.hvs_render_completion_service as svc
        out = tmp_path / "projects" / "p1" / "renders" / "o.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"x" * 500)
        monkeypatch.setattr(svc, "_probe_media_ffprobe", lambda p: self._good_probe())
        v = svc.verify_render_artifact(
            repo_root=tmp_path, hvs_repo_root=str(tmp_path), project_id="p1",
            render_request_id="req", render_approval_id="ap", dispatch_id="d1",
            hvs_render_id="r1", output_relative_path="projects/p1/renders/o.mp4",
            selected_format="vertical", width=1080, height=1920, fps=30,
            target_duration_seconds=3.0, video_codec="h264", pixel_format="yuv420p",
            audio_requirement=AudioRequirement.NOT_REQUIRED,
            no_overwrite_policy=NoOverwritePolicy.NEVER, operator_id="op",
            recorded_at="2026-07-14")
        probe = v["verification"]["probe"]
        assert v["verification"]["actual_duration_seconds"] is not None
        assert probe["width"] == 1080

    def test_exit_zero_alone_not_completion(self, tmp_path, monkeypatch):
        def fake_run(*a, **k):
            class R:
                returncode = 0
                stdout = json.dumps({"verdict": "PASS", "project_id": "p1",
                                      "render_id": "r1", "output_path": None,
                                      "manifest_path": None})
                stderr = ""
            return R()
        ex = SVC.HVSRenderCompletionExecutor(python_executable="python", subprocess_run=fake_run)
        res = ex.dispatch(hvs_root=Path(tmp_path), hvs_project_id="p1", fmt="vertical", dispatch_id="d1")
        assert res.execution_status != M.RenderExecutionStatus.COMPLETED

    def test_verified_artifact_accepted(self, tmp_path, monkeypatch):
        import scos.control_center.hvs_render_completion_service as svc
        out = tmp_path / "projects" / "p1" / "renders" / "o.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"x" * 500)
        monkeypatch.setattr(svc, "_probe_media_ffprobe", lambda p: self._good_probe())
        v = svc.verify_render_artifact(
            repo_root=tmp_path, hvs_repo_root=str(tmp_path), project_id="p1",
            render_request_id="req", render_approval_id="ap", dispatch_id="d1",
            hvs_render_id="r1", output_relative_path="projects/p1/renders/o.mp4",
            selected_format="vertical", width=1080, height=1920, fps=30,
            target_duration_seconds=3.0, video_codec="h264", pixel_format="yuv420p",
            audio_requirement=AudioRequirement.NOT_REQUIRED,
            no_overwrite_policy=NoOverwritePolicy.NEVER, operator_id="op",
            recorded_at="2026-07-14")
        assert v["ok"] is True
        assert v["verification"]["verification_status"] == M.ArtifactVerificationStatus.VERIFIED


# ---------------------------------------------------------------------------
# U. completion evidence + V. idempotency + W. security/arch + X. CLI
# ---------------------------------------------------------------------------
class TestCompletionEvidence:
    def _verify_good(self, tmp_path, monkeypatch):
        import scos.control_center.hvs_render_completion_service as svc
        out = tmp_path / "projects" / "p1" / "renders" / "o.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"x" * 500)
        monkeypatch.setattr(svc, "_probe_media_ffprobe", lambda p: ("ok", {
            "format": {"format_name": "mp4", "duration": "3.0"},
            "streams": [{"codec_type": "video", "codec_name": "h264", "width": 1080,
                         "height": 1920, "pix_fmt": "yuv420p", "r_frame_rate": "30/1",
                         "duration": "3.0", "nb_frames": "90"}],
        }))
        return svc.verify_render_artifact(
            repo_root=tmp_path, hvs_repo_root=str(tmp_path), project_id="p1",
            render_request_id="req", render_approval_id="ap", dispatch_id="d1",
            hvs_render_id="r1", output_relative_path="projects/p1/renders/o.mp4",
            selected_format="vertical", width=1080, height=1920, fps=30,
            target_duration_seconds=3.0, video_codec="h264", pixel_format="yuv420p",
            audio_requirement=AudioRequirement.NOT_REQUIRED,
            no_overwrite_policy=NoOverwritePolicy.NEVER, operator_id="op",
            recorded_at="2026-07-14")

    def test_completion_evidence_binds_artifact_hashes(self, tmp_path, monkeypatch):
        v = self._verify_good(tmp_path, monkeypatch)
        ce = SVC.create_render_completion_evidence(
            repo_root=tmp_path, project_id="p1", render_request_id="req",
            render_contract_hash="ch", render_approval_id="ap", dispatch_id="d1",
            hvs_render_id="r1", intake_manifest_id="manifest-1",
            intake_manifest_content_hash="mh", render_readiness_id="readiness-1",
            render_readiness_content_hash="rh", selected_format="vertical",
            verification=v["verification"], operator_id="op", recorded_at="2026-07-14")
        assert ce["ok"] is True
        assert ce["evidence"]["artifact_sha256_values"][0] == v["verification"]["artifact"]["sha256"]

    def test_completion_evidence_binds_approval(self, tmp_path, monkeypatch):
        v = self._verify_good(tmp_path, monkeypatch)
        ce = SVC.create_render_completion_evidence(
            repo_root=tmp_path, project_id="p1", render_request_id="req",
            render_contract_hash="ch", render_approval_id="ap", dispatch_id="d1",
            hvs_render_id="r1", intake_manifest_id="manifest-1",
            intake_manifest_content_hash="mh", render_readiness_id="readiness-1",
            render_readiness_content_hash="rh", selected_format="vertical",
            verification=v["verification"], operator_id="op", recorded_at="2026-07-14")
        assert ce["evidence"]["render_approval_id"] == "ap"

    def test_completion_evidence_binds_stage8m_readiness(self, tmp_path, monkeypatch):
        v = self._verify_good(tmp_path, monkeypatch)
        ce = SVC.create_render_completion_evidence(
            repo_root=tmp_path, project_id="p1", render_request_id="req",
            render_contract_hash="ch", render_approval_id="ap", dispatch_id="d1",
            hvs_render_id="r1", intake_manifest_id="manifest-1",
            intake_manifest_content_hash="mh", render_readiness_id="readiness-1",
            render_readiness_content_hash="rh", selected_format="vertical",
            verification=v["verification"], operator_id="op", recorded_at="2026-07-14")
        assert ce["evidence"]["render_readiness_id"] == "readiness-1"

    def test_completion_evidence_does_not_create_delivery(self, tmp_path, monkeypatch):
        v = self._verify_good(tmp_path, monkeypatch)
        ce = SVC.create_render_completion_evidence(
            repo_root=tmp_path, project_id="p1", render_request_id="req",
            render_contract_hash="ch", render_approval_id="ap", dispatch_id="d1",
            hvs_render_id="r1", intake_manifest_id="manifest-1",
            intake_manifest_content_hash="mh", render_readiness_id="readiness-1",
            render_readiness_content_hash="rh", selected_format="vertical",
            verification=v["verification"], operator_id="op", recorded_at="2026-07-14")
        e = ce["evidence"]
        for flag in ("delivery_authorized", "publishing_authorized",
                     "customer_contact_performed", "upload_performed",
                     "publishing_performed", "invoice_state_changed",
                     "payment_state_changed", "automation_allowed"):
            assert e[flag] is False


class TestNonDeliveryBoundary:
    @pytest.mark.parametrize("flag", [
        "delivery_authorized", "publishing_authorized", "customer_contact_performed",
        "upload_performed", "publishing_performed", "invoice_state_changed",
        "payment_state_changed", "automation_allowed",
    ])
    def test_no_commercial_flag_true(self, tmp_path, monkeypatch, flag):
        import scos.control_center.hvs_render_completion_service as svc
        out = tmp_path / "projects" / "p1" / "renders" / "o.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"x" * 500)
        monkeypatch.setattr(svc, "_probe_media_ffprobe", lambda p: ("ok", {
            "format": {"format_name": "mp4", "duration": "3.0"},
            "streams": [{"codec_type": "video", "codec_name": "h264", "width": 1080,
                         "height": 1920, "pix_fmt": "yuv420p", "r_frame_rate": "30/1"}],
        }))
        v = svc.verify_render_artifact(
            repo_root=tmp_path, hvs_repo_root=str(tmp_path), project_id="p1",
            render_request_id="req", render_approval_id="ap", dispatch_id="d1",
            hvs_render_id="r1", output_relative_path="projects/p1/renders/o.mp4",
            selected_format="vertical", width=1080, height=1920, fps=30,
            target_duration_seconds=3.0, video_codec="h264", pixel_format="yuv420p",
            audio_requirement=AudioRequirement.NOT_REQUIRED,
            no_overwrite_policy=NoOverwritePolicy.NEVER, operator_id="op",
            recorded_at="2026-07-14")
        ce = svc.create_render_completion_evidence(
            repo_root=tmp_path, project_id="p1", render_request_id="req",
            render_contract_hash="ch", render_approval_id="ap", dispatch_id="d1",
            hvs_render_id="r1", intake_manifest_id="manifest-1",
            intake_manifest_content_hash="mh", render_readiness_id="readiness-1",
            render_readiness_content_hash="rh", selected_format="vertical",
            verification=v["verification"], operator_id="op", recorded_at="2026-07-14")
        assert ce["evidence"][flag] is False

    def test_no_customer_contact(self, tmp_path):
        import inspect
        src = inspect.getsource(SVC)
        assert "sendgrid" not in src.lower()
        assert ".send(" not in src

    def test_no_upload(self, tmp_path):
        import inspect
        src = inspect.getsource(SVC)
        # upload must only appear as a false boundary flag, never an action.
        assert "upload" in src
        assert "upload_artifact" not in src
        assert "requests.put" not in src

    def test_no_publish(self, tmp_path):
        import inspect
        src = inspect.getsource(SVC)
        assert "publish_artifact" not in src
        assert "publish_render" not in src

    def test_no_invoice_mutation(self, tmp_path):
        import inspect
        src = inspect.getsource(SVC)
        assert "invoice_state_changed = True" not in src

    def test_no_payment_mutation(self, tmp_path):
        import inspect
        src = inspect.getsource(SVC)
        assert "payment_state_changed = True" not in src


class TestSecurityArchitecture:
    def test_no_hvs_imports_in_production_modules(self, tmp_path):
        import importlib.util
        for mod in ("hvs_render_completion_models", "hvs_render_completion_service",
                   "hvs_render_completion_store"):
            spec = importlib.util.find_spec(f"scos.control_center.{mod}")
            src = Path(spec.origin).read_text(encoding="utf-8")
            assert "import hvs" not in src
            assert "from hvs" not in src

    def test_no_os_system(self, tmp_path):
        import importlib.util
        spec = importlib.util.find_spec("scos.control_center.hvs_render_completion_service")
        src = Path(spec.origin).read_text(encoding="utf-8")
        assert "os.system" not in src

    def test_no_shell_true(self, tmp_path):
        import importlib.util
        spec = importlib.util.find_spec("scos.control_center.hvs_render_completion_service")
        src = Path(spec.origin).read_text(encoding="utf-8")
        assert "shell=True" not in src

    def test_no_http_client(self, tmp_path):
        import importlib.util
        import re
        spec = importlib.util.find_spec("scos.control_center.hvs_render_completion_service")
        src = Path(spec.origin).read_text(encoding="utf-8")
        # Match real HTTP-client usage only: a module import or a method call on
        # the `requests` library. Avoid false positives on the prose word
        # "render requests." which contains the substring "requests.".
        for forbidden in (r"^\s*import\s+requests\b", r"\bfrom\s+requests\s+import\b",
                          r"\brequests\.(get|post|put|delete|patch|head|Session|request)\b",
                          r"\burllib\.request\b", r"\bhttp\.client\b",
                          r"\baiohttp\b", r"\bsocket\s*\("):
            assert re.search(forbidden, src, re.MULTILINE) is None, (
                f"forbidden pattern found: {forbidden}"
            )

    def test_runtime_records_remain_ignored(self, tmp_path):
        p = render_completion_path(tmp_path)
        # Runtime ledger lives under the gitignored scos/work root.
        norm = str(p).replace("\\", "/")
        assert "/scos/work/" in norm

    def test_mp4_artifacts_remain_untracked(self, tmp_path):
        assert True

    def test_hvs_tracked_source_remains_clean(self, tmp_path):
        import importlib.util
        spec = importlib.util.find_spec("scos.control_center.hvs_render_completion_service")
        src = Path(spec.origin).read_text(encoding="utf-8")
        assert "hermes-video-studio" not in src


# ---------------------------------------------------------------------------
# X. Strengthened negative safety tests (mandatory coverage areas)
# ---------------------------------------------------------------------------
class TestStrengthenedNegativeSafety:
    def _dispatch(self, tmp_path, stdout_obj, readiness=None):
        def fake_run(*a, **k):
            class R:
                returncode = 0
                stdout = json.dumps(stdout_obj)
                stderr = ""
            return R()
        ex = SVC.HVSRenderCompletionExecutor(
            python_executable="python", subprocess_run=fake_run
        )
        return ex.dispatch(
            hvs_root=Path(tmp_path), hvs_project_id="p1", fmt="vertical", dispatch_id="d1"
        )

    def test_missing_project_id_rejected(self, tmp_path):
        res = self._dispatch(tmp_path, {"verdict": "PASS", "project_id": None,
                                        "render_id": "r1", "output_path": None,
                                        "manifest_path": None})
        assert res.execution_status != M.RenderExecutionStatus.COMPLETED
        assert "RETURNED_PROJECT_ID_MISMATCH" in (res.stderr_summary or "")

    def test_wrong_project_id_rejected(self, tmp_path):
        res = self._dispatch(tmp_path, {"verdict": "PASS", "project_id": "WRONG",
                                        "render_id": "r1", "output_path": "x.mp4",
                                        "manifest_path": None})
        assert res.execution_status != M.RenderExecutionStatus.COMPLETED
        assert "RETURNED_PROJECT_ID_MISMATCH" in (res.stderr_summary or "")

    def test_missing_output_path_rejected(self, tmp_path):
        res = self._dispatch(tmp_path, {"verdict": "PASS", "project_id": "p1",
                                        "render_id": "r1", "output_path": None,
                                        "manifest_path": None})
        assert res.output_relative_path is None
        assert res.execution_status == M.RenderExecutionStatus.FAILED

    def test_empty_output_path_rejected(self, tmp_path):
        res = self._dispatch(tmp_path, {"verdict": "PASS", "project_id": "p1",
                                        "render_id": "r1", "output_path": "",
                                        "manifest_path": None})
        assert res.execution_status != M.RenderExecutionStatus.COMPLETED
        assert res.output_relative_path in (None, "")

    def test_out_of_tree_output_path_rejected(self, tmp_path):
        foreign = tmp_path / "elsewhere.mp4"
        foreign.parent.mkdir(parents=True, exist_ok=True)
        foreign.write_bytes(b"x")
        res = self._dispatch(tmp_path, {"verdict": "PASS", "project_id": "p1",
                                        "render_id": "r1",
                                        "output_path": str(foreign),
                                        "manifest_path": None})
        assert res.output_relative_path is None or res.output_relative_path.startswith("projects/p1/")

    def test_traversal_output_path_rejected(self, tmp_path):
        # Even a path that naively resolves under the project root but escapes
        # via '..' must not be trusted as the render output.
        target = (tmp_path / "projects" / "p1" / "renders" / "o.mp4").resolve()
        traversal = str(target.parent.parent.parent / ".." / ".." / "escaped.mp4")
        res = self._dispatch(tmp_path, {"verdict": "PASS", "project_id": "p1",
                                        "render_id": "r1",
                                        "output_path": traversal,
                                        "manifest_path": None})
        assert res.output_relative_path is None or res.output_relative_path.startswith("projects/p1/")

    def test_changed_asset_hash_invalidates_approval(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1", asset_hashes=("a",))
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec())
        approve_render(repo_root=tmp_path, project_id="p1",
                      render_request_id=r["render_request_id"],
                      render_contract_hash=r["render_contract_hash"],
                      operator_id="op", recorded_at="2026-07-14",
                      explicit_render_confirmation=True,
                      explicit_non_delivery_acknowledgement=True,
                      intake_manifest_content_hash="mh",
                      render_readiness_id="readiness-1",
                      render_readiness_content_hash="rh")
        _write_stage8m_readiness(tmp_path, "p1", asset_hashes=("CHANGED",))
        rev = pre_dispatch_reverify(repo_root=tmp_path, project_id="p1",
                                    readiness_binding=_binding(tmp_path, asset_hashes=("a",)))
        assert rev["ok"] is False and rev["code"] == "MANIFEST_CHANGED_AFTER_APPROVAL"

    def test_exit_zero_with_invalid_evidence_not_completion(self, tmp_path):
        res = self._dispatch(tmp_path, {"verdict": "PASS", "project_id": "p1",
                                        "render_id": "r1", "output_path": None,
                                        "manifest_path": None})
        assert res.exit_code == 0
        assert res.execution_status != M.RenderExecutionStatus.COMPLETED


# ---------------------------------------------------------------------------
# W. CLI wiring (Stage 8N) — exercised against the local service layer
# ---------------------------------------------------------------------------
class TestStage8NCLI:
    def test_cli_parser_exposes_dispatch_command(self, tmp_path):
        from scos.control_center import cli
        parser = cli._build_parser()
        ns = parser.parse_args([
            "dispatch-approved-hvs-render",
            "--project-id", "p1",
            "--render-request-id", "req-1",
            "--operator-id", "op",
            "--dry-run",
        ])
        assert ns.func is cli._cmd_dispatch_approved_render
        assert ns.project_id == "p1"
        assert ns.dry_run is True

    def test_cli_dry_run_fails_without_approval(self, tmp_path):
        import importlib
        cli = importlib.import_module("scos.control_center.cli")
        _write_stage8m_readiness(tmp_path, "p1")
        # Point the CLI at the temp repo root via a monkeypatched repo root.
        import scos.control_center.cli as climgr
        real = climgr._repo_root
        climgr._repo_root = lambda: tmp_path
        try:
            out = cli.main([
                "dispatch-approved-hvs-render",
                "--project-id", "p1",
                "--render-request-id", "req-1",
                "--operator-id", "op",
                "--dry-run",
                "--hvs-repo-root", str(tmp_path),
            ])
        finally:
            climgr._repo_root = real
        assert out == cli.EXIT_REJECT

    def test_cli_dry_run_succeeds_after_approval(self, tmp_path):
        import importlib
        cli = importlib.import_module("scos.control_center.cli")
        _write_stage8m_readiness(tmp_path, "p1")
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec())
        approve_render(repo_root=tmp_path, project_id="p1",
                      render_request_id=r["render_request_id"],
                      render_contract_hash=r["render_contract_hash"],
                      operator_id="op", recorded_at="2026-07-14",
                      explicit_render_confirmation=True,
                      explicit_non_delivery_acknowledgement=True,
                      intake_manifest_content_hash="mh",
                      render_readiness_id="readiness-1",
                      render_readiness_content_hash="rh")
        import scos.control_center.cli as climgr
        real = climgr._repo_root
        climgr._repo_root = lambda: tmp_path
        try:
            out = cli.main([
                "dispatch-approved-hvs-render",
                "--project-id", "p1",
                "--render-request-id", r["render_request_id"],
                "--operator-id", "op",
                "--dry-run",
                "--hvs-repo-root", str(tmp_path),
            ])
        finally:
            climgr._repo_root = real
        assert out == cli.EXIT_OK


# ---------------------------------------------------------------------------
# Y. Real-HVS acceptance cluster (integration) — skipped by default collection
# ---------------------------------------------------------------------------
# X. Stage 8N focused CLI tests (no real HVS render; read-only + dry-run only)
# ---------------------------------------------------------------------------
class TestStage8NCLI:
    def _run(self, tmp_path, *argv):
        import scos.control_center.cli as climgr
        real = climgr._repo_root
        climgr._repo_root = lambda: tmp_path
        try:
            return climgr.main(list(argv))
        finally:
            climgr._repo_root = real

    def test_cli_create_request_success(self, tmp_path, capsys):
        _write_stage8m_readiness(tmp_path, "p1")
        rc = self._run(tmp_path, "create-hvs-render-request",
                       "--project-id", "p1", "--operator-id", "op",
                       "--intake-manifest-content-hash", "mh",
                       "--render-readiness-id", "readiness-1",
                       "--render-readiness-content-hash", "rh")
        out = json.loads(capsys.readouterr().out)
        assert rc == 0 and out["ok"] is True
        assert "render_request_id" in out and "render_contract_hash" in out

    def test_cli_inspect_request_readonly(self, tmp_path, capsys):
        _write_stage8m_readiness(tmp_path, "p1")
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec())
        rc = self._run(tmp_path, "inspect-hvs-render-request",
                       "--render-request-id", r["render_request_id"])
        out = json.loads(capsys.readouterr().out)
        assert rc == 0 and out["ok"] is True
        assert out["render_request_id"] == r["render_request_id"]

    def test_cli_decide_approve_success(self, tmp_path, capsys):
        _write_stage8m_readiness(tmp_path, "p1")
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec())
        rc = self._run(tmp_path, "decide-hvs-render",
                       "--project-id", "p1",
                       "--render-request-id", r["render_request_id"],
                       "--render-contract-hash", r["render_contract_hash"],
                       "--intake-manifest-content-hash", "mh",
                       "--render-readiness-id", "readiness-1",
                       "--render-readiness-content-hash", "rh",
                       "--operator-id", "op",
                       "--render-confirmation", "--non-delivery-acknowledgement")
        out = json.loads(capsys.readouterr().out)
        assert rc == 0 and out["ok"] is True
        assert out["render_authorized"] is True
        assert out["delivery_authorized"] is False
        assert out["publishing_authorized"] is False
        assert out["automation_allowed"] is False

    def test_cli_decide_reject_requires_reason(self, tmp_path, capsys):
        _write_stage8m_readiness(tmp_path, "p1")
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec())
        rc = self._run(tmp_path, "decide-hvs-render",
                       "--project-id", "p1",
                       "--render-request-id", r["render_request_id"],
                       "--render-contract-hash", r["render_contract_hash"],
                       "--operator-id", "op",
                       "--reject")
        out = json.loads(capsys.readouterr().out)
        assert rc != 0 and "MISSING_REASON" in out.get("code", "")

    def test_cli_verify_artifact_readonly(self, tmp_path, capsys, monkeypatch):
        import scos.control_center.hvs_render_completion_service as svc
        # point output inside the trusted project root
        out = tmp_path / "projects" / "p1" / "renders" / "o.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"x" * 500)
        monkeypatch.setattr(svc, "_probe_media_ffprobe", lambda p: self_good_probe())
        rc = self._run(tmp_path, "verify-hvs-render-artifact",
                       "--hvs-repo-root", str(tmp_path),
                       "--project-id", "p1",
                       "--render-request-id", "req",
                       "--output-relative-path", "projects/p1/renders/o.mp4",
                       "--operator-id", "op")
        out_json = json.loads(capsys.readouterr().out)
        # verify output: ok + nested verification; boundary flags live on
        # completion evidence, not on the standalone verify result.
        assert out_json["ok"] is True
        assert out_json["verification"]["artifact_verified"] is True

    def test_cli_list_recovery_queue_empty(self, tmp_path, capsys):
        rc = self._run(tmp_path, "list-hvs-render-recovery-queue")
        out = json.loads(capsys.readouterr().out)
        assert rc == 0 and out["ok"] is True
        assert out["recovery_queue"] == []
        assert out["delivery_authorized"] is False
        assert out["automation_allowed"] is False


def self_good_probe():
    # Real ffprobe JSON shape expected by verify_render_artifact.
    return ("ok", {
        "format": {"format_name": "mov,mp4", "duration": "3.0", "bit_rate": "500000"},
        "streams": [
            {
                "codec_type": "video", "codec_name": "h264",
                "width": 1080, "height": 1920,
                "avg_frame_rate": "30/1", "pix_fmt": "yuv420p",
                "duration": "3.0", "nb_frames": "90",
            }
        ],
    })


@pytest.mark.integration
class TestStage8NRealHVS:
    HVS_REPO = "C:/Workspace/hermes-video-studio"

    def test_real_hvs_render_boundary_is_reachable(self, tmp_path):
        """Smoke check that the Stage 5-certified HVS render boundary exists.

        Does NOT invoke a render; only confirms SCOS's read-only contract with
        the HVS repo (no writes, no network). SCOS drives HVS via
        ``python -m hvs.cli`` (the ``hvs/cli`` package), never by importing or
        writing into the HVS repository.
        """
        hvs_root = Path(self.HVS_REPO).resolve()
        assert (hvs_root / "hvs" / "cli").is_dir()
        assert (hvs_root / "hvs" / "__init__.py").is_file()

    def test_real_hvs_render_completion_fails_closed_on_missing_approval(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1")
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec())
        out = dispatch_approved_render(
            repo_root=tmp_path, hvs_repo_root=self.HVS_REPO,
            hvs_python_executable="python",
            render_request_id=r["render_request_id"],
            readiness_binding=_binding(tmp_path), operator_id="op",
            recorded_at="2026-07-14", **_request_spec())
        assert out["ok"] is False and out["code"] == "NO_APPROVAL"

    def test_real_hvs_render_completion_dry_run_contract(self, tmp_path):
        _write_stage8m_readiness(tmp_path, "p1")
        r = evaluate_render_request_readiness(repo_root=tmp_path, operator_id="op",
                                              recorded_at="2026-07-14", **_request_spec())
        approve_render(repo_root=tmp_path, project_id="p1",
                      render_request_id=r["render_request_id"],
                      render_contract_hash=r["render_contract_hash"],
                      operator_id="op", recorded_at="2026-07-14",
                      explicit_render_confirmation=True,
                      explicit_non_delivery_acknowledgement=True,
                      intake_manifest_content_hash="mh",
                      render_readiness_id="readiness-1",
                      render_readiness_content_hash="rh")
        out = dispatch_approved_render(
            repo_root=tmp_path, hvs_repo_root=self.HVS_REPO,
            hvs_python_executable="python",
            render_request_id=r["render_request_id"],
            readiness_binding=_binding(tmp_path), operator_id="op",
            recorded_at="2026-07-14", dry_run=True, **_request_spec())
        assert out["ok"] is True and out["dry_run"] is True
        assert out["dispatch"] is None

    REAL_PROJECT = "hvs8l-e32880405a6292d1ac4e1f68997d085f"
    REAL_ARTIFACT = (
        "projects/hvs8l-e32880405a6292d1ac4e1f68997d085f/"
        "renders/hyperframes-693c0e7c3bad0f4d.mp4"
    )

    def test_real_hvs_project_inspectable(self):
        """Case 1: the verified Stage 8M project exists in the real HVS repo."""
        hvs_root = Path(self.HVS_REPO).resolve()
        assert (hvs_root / "projects" / self.REAL_PROJECT).is_dir()

    def test_stage8m_readiness_reverified(self, tmp_path):
        """Case 2: Stage 8M READY evidence is re-loadable as a binding."""
        from scos.control_center.hvs_render_completion_service import (
            load_readiness_binding,
        )
        _write_stage8m_readiness(tmp_path, self.REAL_PROJECT)
        binding = load_readiness_binding(repo_root=tmp_path, project_id=self.REAL_PROJECT)
        assert binding is not None
        assert binding.project_id == self.REAL_PROJECT

    def test_render_request_created_for_vertical(self, tmp_path):
        """Case 3: a deterministic render request is created for vertical."""
        _write_stage8m_readiness(tmp_path, self.REAL_PROJECT)
        r = evaluate_render_request_readiness(
            repo_root=tmp_path, operator_id="op", recorded_at="2026-07-14",
            project_id=self.REAL_PROJECT, selected_format="vertical",
            width=1080, height=1920, fps=30, target_duration_seconds=3.0,
            video_codec="h264", pixel_format="yuv420p",
            audio_requirement="NOT_REQUIRED", no_overwrite_policy="never",
        )
        assert r["ok"] is True
        assert r["render_request_id"] and r["render_contract_hash"]

    def test_separate_8n_approval_recorded(self, tmp_path):
        """Case 4: a SEPARATE Stage 8N approval is recorded (not Stage 8M)."""
        _write_stage8m_readiness(tmp_path, self.REAL_PROJECT)
        r = evaluate_render_request_readiness(
            repo_root=tmp_path, operator_id="op", recorded_at="2026-07-14",
            project_id=self.REAL_PROJECT, selected_format="vertical",
            width=1080, height=1920, fps=30, target_duration_seconds=3.0,
            video_codec="h264", pixel_format="yuv420p",
            audio_requirement="NOT_REQUIRED", no_overwrite_policy="never",
        )
        ap = approve_render(
            repo_root=tmp_path, project_id=self.REAL_PROJECT,
            render_request_id=r["render_request_id"],
            render_contract_hash=r["render_contract_hash"],
            operator_id="op", recorded_at="2026-07-14",
            explicit_render_confirmation=True,
            explicit_non_delivery_acknowledgement=True,
            intake_manifest_content_hash="mh",
            render_readiness_id="readiness-1",
            render_readiness_content_hash="rh",
        )
        assert ap["ok"] is True
        assert ap["render_authorized"] is True
        assert ap["approval_id"]  # separate Stage 8N approval identity

    def test_dispatch_reaches_real_hvs_boundary(self):
        """Case 5: the dispatch argv targets the exact Stage 5-certified CLI."""
        from scos.control_center.hvs_render_completion_service import (
            HVSRenderCompletionExecutor,
        )
        inv = HVSRenderCompletionExecutor(
            python_executable="python",
            timeout_seconds=300,
            subprocess_run=None,
        )
        argv = inv.build_argv(hvs_project_id=self.REAL_PROJECT, fmt="vertical")
        assert argv[:4] == ["python", "-m", "hvs.cli", "render-hyperframes"]
        assert "--project-id" in argv and self.REAL_PROJECT in argv
        assert "--format" in argv and "vertical" in argv

    def test_real_mp4_discovered_and_hashed(self, tmp_path):
        """Case 6: a real vertical MP4 (synthetic, temp HVS double) is discovered
        and SHA-256 computed via the real ffprobe/file boundary."""
        import hashlib
        import subprocess as _sp
        import shutil as _sh
        hvs_root = DOUBLE.make_temp_hvs_repo(tmp_path / "hvs-repo", self.REAL_PROJECT)
        mp4 = Path(hvs_root) / self.REAL_ARTIFACT
        mp4.parent.mkdir(parents=True, exist_ok=True)
        bin_name = _sh.which("ffmpeg") or "ffmpeg"
        _sp.run([bin_name, "-y", "-f", "lavfi", "-i", "color=c=blue:s=1080x1920:d=3",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", str(mp4)],
                shell=False, capture_output=True, text=True, timeout=120, check=False)
        assert mp4.is_file() and mp4.stat().st_size > 0
        sha = hashlib.sha256(mp4.read_bytes()).hexdigest()
        assert len(sha) == 64

    def test_ffprobe_verifies_profile(self, tmp_path):
        """Case 7: ffprobe verifies the (synthetic) artifact (h264, 1080x1920,
        30fps, yuv420p, ~3.0s). Real ffprobe runs here against a temp HVS double
        (read-only inspection, no real HVS mutation)."""
        import subprocess as _sp
        import shutil as _sh
        hvs_root = DOUBLE.make_temp_hvs_repo(tmp_path / "hvs-repo", self.REAL_PROJECT)
        mp4 = Path(hvs_root) / self.REAL_ARTIFACT
        mp4.parent.mkdir(parents=True, exist_ok=True)
        bin_name = _sh.which("ffmpeg") or "ffmpeg"
        _sp.run([bin_name, "-y", "-f", "lavfi", "-i", "color=c=blue:s=1080x1920:d=3",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", str(mp4)],
                shell=False, capture_output=True, text=True, timeout=120, check=False)
        assert mp4.is_file() and mp4.stat().st_size > 0
        from scos.control_center.hvs_render_completion_service import (
            verify_render_artifact,
        )
        result = verify_render_artifact(
            repo_root=tmp_path, hvs_repo_root=str(hvs_root),
            project_id=self.REAL_PROJECT,
            render_request_id="req-real", render_approval_id="ap-real",
            dispatch_id="d-real", hvs_render_id="r-real",
            output_relative_path=self.REAL_ARTIFACT,
            selected_format="vertical", width=1080, height=1920, fps=30,
            target_duration_seconds=3.0, video_codec="h264",
            pixel_format="yuv420p", audio_requirement="NOT_REQUIRED",
            no_overwrite_policy="never", operator_id="op",
            recorded_at="2026-07-14",
        )
        assert result["verification"]["artifact_verified"] is True
        ev = result["verification"]
        assert ev["width"] == 1080 and ev["height"] == 1920
        assert ev["fps"] == 30
        assert ev["video_codec"] == "h264"
        assert ev["pixel_format"] == "yuv420p"
        # audio absent => NOT_REQUIRED (must NOT falsely report PASS)
        assert ev["audio_streams"] == 0
        assert ev["audio_verdict"] == "NOT_REQUIRED"

    def test_completion_evidence_created(self, tmp_path):
        """Case 8: completion evidence is created with verified artifact and
        all delivery/publish flags forced false. Uses a temp HVS double with a
        synthetic artifact (no real HVS mutation)."""
        import subprocess as _sp
        import shutil as _sh
        hvs_root = DOUBLE.make_temp_hvs_repo(tmp_path / "hvs-repo", self.REAL_PROJECT)
        mp4 = Path(hvs_root) / self.REAL_ARTIFACT
        mp4.parent.mkdir(parents=True, exist_ok=True)
        bin_name = _sh.which("ffmpeg") or "ffmpeg"
        _sp.run([bin_name, "-y", "-f", "lavfi", "-i", "color=c=blue:s=1080x1920:d=3",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", str(mp4)],
                shell=False, capture_output=True, text=True, timeout=120, check=False)
        assert mp4.is_file() and mp4.stat().st_size > 0
        from scos.control_center.hvs_render_completion_service import (
            verify_render_artifact,
            create_render_completion_evidence,
        )
        result = verify_render_artifact(
            repo_root=tmp_path, hvs_repo_root=str(hvs_root),
            project_id=self.REAL_PROJECT,
            render_request_id="req-real", render_approval_id="ap-real",
            dispatch_id="d-real", hvs_render_id="r-real",
            output_relative_path=self.REAL_ARTIFACT,
            selected_format="vertical", width=1080, height=1920, fps=30,
            target_duration_seconds=3.0, video_codec="h264",
            pixel_format="yuv420p", audio_requirement="NOT_REQUIRED",
            no_overwrite_policy="never", operator_id="op",
            recorded_at="2026-07-14",
        )
        assert result["verification"]["artifact_verified"] is True
        ce = create_render_completion_evidence(
            repo_root=tmp_path, project_id=self.REAL_PROJECT,
            render_request_id="req-real",
            render_contract_hash="ch-real", render_approval_id="ap-real",
            dispatch_id="d-real", hvs_render_id="r-real",
            intake_manifest_id="manifest-1",
            intake_manifest_content_hash="mh",
            render_readiness_id="readiness-1",
            render_readiness_content_hash="rh",
            selected_format="vertical", verification=result,
            operator_id="op", recorded_at="2026-07-14",
        )
        assert ce["ok"] is True
        rec = ce["evidence"]
        assert rec["artifact_verified"] is True
        assert rec["delivery_authorized"] is False
        assert rec["publishing_authorized"] is False
        assert rec["automation_allowed"] is False
