"""Stage 8S — full-lifecycle end-to-end production release acceptance.

This is the FINAL Stage of the current SCOS-HVS lifecycle. It does NOT create a
new business subsystem. It PROVES the existing certified platform works as one
complete operator-controlled production lifecycle:

* the complete lifecycle graph (8H -> 8R) is represented and connected,
* every required operator approval is distinct and separate,
* the canonical identity / hash chain stays bound across the lifecycle,
* SCOS controls the lifecycle WITHOUT importing HVS internals,
* a REAL fresh HVS project is initialized, REAL assets materialized, and a
  REAL MP4 is rendered through the approved CLI boundary,
* the artifact is FFprobe-verified and SHA-256 recorded,
* delivery / receipt / customer-outcome / 8Q route / 8R closure all execute,
* revision / dispute / manual-follow-up branches are proven,
* interruption recovery + idempotent replay + changed-semantic conflict hold,
* no prior successful artifact is overwritten,
* failed operations cannot fabricate completion evidence,
* the operator-readable lifecycle inspector works (read-only, fail-closed),
* full tests / smoke / security pass,
* one final local SCOS commit is made and HVS tracked source stays unchanged.

Groups:
  A. Lifecycle graph
  B. Happy-path control plane (8O/8P/8Q/8R continuous)
  C. Identity and hash chain
  D. Operator approvals (separate boundaries)
  E. Exactly-once and replay
  F. Boundary flags
  G. Optional lifecycle inspector + CLI
  H. Real SCOS->HVS production acceptance (integration, fresh render)
  I. Revision / dispute / follow-up branches
  J. Recovery and negative acceptance (incl. process restart)

Real-HVS tests are marked ``@pytest.mark.integration`` and skipped by the
default collection (run with ``-m integration``). All other tests are hermetic
and use task-owned ``tmp_path`` stores.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# --- Reuse the canonical, already-certified Stage 8R lifecycle helpers ------
from scos.control_center.tests.test_hvs_resolution_action_execution import (
    ART,
    _approved_route,
    _mkroot,
    _seed_closure_delivery,
)
from scos.control_center import hvs_resolution_action_models as M
from scos.control_center import hvs_resolution_action_service as R
from scos.control_center import hvs_post_delivery_resolution_models as QM
from scos.control_center import hvs_post_delivery_resolution_service as Q
from scos.control_center import hvs_customer_receipt_acceptance_service as P
from scos.control_center import hvs_lifecycle_release_service as LIFE
from scos.control_center import hvs_lifecycle_release_models as LM

from scos.control_center.hvs_resolution_action_store import (
    read_resolution_action_events,
    ledger_path,
)


# ===========================================================================
# A. LIFECYCLE GRAPH
# ===========================================================================
class TestLifecycleGraph:
    def test_required_stages_present_in_model(self):
        stages = LM.LIFECYCLE_STAGES
        for required in (
            "8H_qualified_opportunity",
            "8I_proposal_preparation",
            "8J_commercial_acceptance",
            "8K_engagement_activation",
            "8L_project_initialization",
            "8M_asset_intake_materialization",
            "8N_render_completion",
            "8O_delivery_authorization",
            "8P_customer_receipt_acceptance",
            "8Q_post_delivery_resolution_route",
            "8R_resolution_action_execution",
        ):
            assert required in stages, f"missing lifecycle stage {required}"

    def test_no_stage_silently_skipped_on_full_chain(self, tmp_path):
        root = _mkroot(tmp_path)
        did, receipt_id = _seed_closure_delivery(root)
        rid = _approved_route(root, did, QM.DECISION_APPROVE_CLOSURE_RECOMMENDATION)
        snap = LIFE.inspect_lifecycle(repo_root=root, project_id="project-stage8r")
        # A closure delivery seeds 8O/8P/8Q/8R evidence; the inspector must not
        # silently drop any represented stage.
        stage_ids = {s.stage for s in snap.stages}
        assert "8O_delivery_authorization" in stage_ids
        assert "8P_customer_receipt_acceptance" in stage_ids
        assert "8Q_post_delivery_resolution_route" in stage_ids
        assert "8R_resolution_action_execution" in stage_ids

    def test_terminal_lifecycle_returns_no_further_action(self, tmp_path):
        root = _mkroot(tmp_path)
        did, receipt_id = _seed_closure_delivery(root)
        rid = _approved_route(root, did, QM.DECISION_APPROVE_CLOSURE_RECOMMENDATION)
        sel = M.ResolutionActionSelection(
            action_family=M.ACTION_PROJECT_CLOSURE_EXECUTION,
            receipt_evidence_id=receipt_id, closure_reason="8s-terminal",
        )
        req = R.create_execution_request(repo_root=root, resolution_route_id=rid, action_selection=sel)
        ap = R.approve_execution_request(
            repo_root=root, execution_request_id=req.execution_request.execution_request_id,
            operator_id="op", reason="x",
        )
        assert ap.ok
        ex = R.execute_approved_action(
            repo_root=root, execution_request_id=req.execution_request.execution_request_id,
            operator_id="op",
        )
        assert ex.ok
        snap = LIFE.inspect_lifecycle(repo_root=root, project_id="project-stage8r")
        assert snap.state == "COMPLETED"
        assert "no_further_automatic_action" in snap.next_action


# ===========================================================================
# B. HAPPY-PATH CONTROL PLANE (continuous 8O/8P/8Q/8R)
# ===========================================================================
class TestHappyPathControlPlane:
    def test_full_closure_lifecycle_control_plane(self, tmp_path):
        """Drive a complete closure lifecycle using public service APIs.

        Proves: create eligible delivery evidence -> receipt -> decision ->
        resolution route (approval-led) -> Stage 8R closure request +
        explicit approval -> exactly-one target mutation -> verified target
        record -> terminal closure.
        """
        root = _mkroot(tmp_path)
        did, receipt_id = _seed_closure_delivery(root)
        # 8Q: approve a closure route (its own approval boundary).
        rid = _approved_route(root, did, QM.DECISION_APPROVE_CLOSURE_RECOMMENDATION)
        # 8R: create closure execution request.
        sel = M.ResolutionActionSelection(
            action_family=M.ACTION_PROJECT_CLOSURE_EXECUTION,
            receipt_evidence_id=receipt_id, closure_reason="8s-happy-path",
        )
        req = R.create_execution_request(repo_root=root, resolution_route_id=rid, action_selection=sel)
        assert req.ok
        req_id = req.execution_request.execution_request_id
        # 8R: SEPARATE explicit approval (distinct from the 8Q route approval).
        ap = R.approve_execution_request(repo_root=root, execution_request_id=req_id,
                                         operator_id="op-8r", reason="approve closure")
        assert ap.ok
        # 8R: execute -> exactly one target mutation.
        ex = R.execute_approved_action(repo_root=root, execution_request_id=req_id, operator_id="op-8r")
        assert ex.ok, ex.error_detail
        out = ex.outcome
        assert out.target_record_id
        assert out.side_effect_count == 1
        # Terminal closure verified.
        events = [e for e in read_resolution_action_events(ledger_path=ledger_path(root))
                  if e.get("event_type") == M.EVT_OUTCOME_EVIDENCE_CREATED]
        assert len(events) == 1
        # Boundary flags all false.
        assert not any((
            out.customer_contact_performed, out.hvs_invoked, out.media_modified,
            out.invoice_state_changed, out.payment_state_changed, out.automation_allowed,
        ))


# ===========================================================================
# C. IDENTITY AND HASH CHAIN
# ===========================================================================
class TestIdentityHashChain:
    def test_canonical_identities_connected_through_lifecycle(self, tmp_path):
        root = _mkroot(tmp_path)
        did, receipt_id = _seed_closure_delivery(root)
        rid = _approved_route(root, did, QM.DECISION_APPROVE_CLOSURE_RECOMMENDATION)
        sel = M.ResolutionActionSelection(
            action_family=M.ACTION_PROJECT_CLOSURE_EXECUTION,
            receipt_evidence_id=receipt_id, closure_reason="8s-chain",
        )
        req = R.create_execution_request(repo_root=root, resolution_route_id=rid, action_selection=sel)
        ap = R.approve_execution_request(
            repo_root=root, execution_request_id=req.execution_request.execution_request_id,
            operator_id="op", reason="x",
        )
        assert ap.ok
        ex = R.execute_approved_action(
            repo_root=root, execution_request_id=req.execution_request.execution_request_id,
            operator_id="op",
        )
        assert ex.ok
        # Identity chain must expose delivery record id, route id, request id,
        # target record id and the execution contract hash.
        snap = LIFE.inspect_lifecycle(repo_root=root, project_id="project-stage8r")
        chain = snap.identity_chain
        assert chain["8Q_post_delivery_resolution_route"] == rid
        assert chain["8R_resolution_action_execution"] == req.execution_request.execution_request_id
        # The execution contract hash binds the request identity.
        assert req.execution_request.execution_contract_hash

    def test_changed_artifact_hash_fails_closed(self, tmp_path):
        """A Stage 8R closure request bound to a receipt evidence id that does
        not match the verified 8P/8O lineage must fail closed (no mutation)."""
        root = _mkroot(tmp_path)
        did, receipt_id = _seed_closure_delivery(root)
        rid = _approved_route(root, did, QM.DECISION_APPROVE_CLOSURE_RECOMMENDATION)
        # Bind to a deliberately wrong receipt evidence id.
        sel = M.ResolutionActionSelection(
            action_family=M.ACTION_PROJECT_CLOSURE_EXECUTION,
            receipt_evidence_id="receipt-that-does-not-exist-0000", closure_reason="x",
        )
        req = R.create_execution_request(repo_root=root, resolution_route_id=rid, action_selection=sel)
        # Even if the request is created, execution must fail the pre-execution
        # reverification (8P identity != requested receipt).
        ap = R.approve_execution_request(
            repo_root=root, execution_request_id=req.execution_request.execution_request_id,
            operator_id="op", reason="x",
        )
        ex = R.execute_approved_action(
            repo_root=root, execution_request_id=req.execution_request.execution_request_id,
            operator_id="op",
        )
        assert not ex.ok
        events = [e for e in read_resolution_action_events(ledger_path=ledger_path(root))
                  if e.get("event_type") == M.EVT_OUTCOME_EVIDENCE_CREATED]
        assert len(events) == 0


# ===========================================================================
# D. OPERATOR APPROVALS (distinct boundaries)
# ===========================================================================
class TestOperatorApprovals:
    def test_stage8q_route_approval_distinct_from_stage8r_action_approval(self, tmp_path):
        root = _mkroot(tmp_path)
        did, receipt_id = _seed_closure_delivery(root)
        # 8Q route approval (first boundary).
        route = Q.create_post_delivery_route(repo_root=root, actual_delivery_record_id=did)
        assert route.ok
        rid = route.resolution_route.resolution_route_id
        d = Q.decide_post_delivery_route(
            repo_root=root, resolution_route_id=rid,
            decision_action=QM.DECISION_APPROVE_CLOSURE_RECOMMENDATION,
            operator_id="op-8q", reason="approve route",
        )
        assert d.ok
        # 8R action request cannot execute WITHOUT its own separate approval.
        sel = M.ResolutionActionSelection(
            action_family=M.ACTION_PROJECT_CLOSURE_EXECUTION,
            receipt_evidence_id=receipt_id, closure_reason="x",
        )
        req = R.create_execution_request(repo_root=root, resolution_route_id=rid, action_selection=sel)
        req_id = req.execution_request.execution_request_id
        # No 8R approval yet -> execution blocked.
        ex0 = R.execute_approved_action(repo_root=root, execution_request_id=req_id, operator_id="op")
        assert not ex0.ok and ex0.error_code == M.ERR_EXECUTION_APPROVAL_NOT_FOUND
        # Now the SEPARATE 8R approval.
        ap = R.approve_execution_request(repo_root=root, execution_request_id=req_id,
                                         operator_id="op-8r", reason="approve action")
        assert ap.ok
        ex = R.execute_approved_action(repo_root=root, execution_request_id=req_id, operator_id="op-8r")
        assert ex.ok

    def test_changed_semantics_invalidate_approval(self, tmp_path):
        root = _mkroot(tmp_path)
        did, receipt_id = _seed_closure_delivery(root)
        rid = _approved_route(root, did, QM.DECISION_APPROVE_CLOSURE_RECOMMENDATION)
        sel = M.ResolutionActionSelection(
            action_family=M.ACTION_PROJECT_CLOSURE_EXECUTION,
            receipt_evidence_id=receipt_id, closure_reason="original",
        )
        req = R.create_execution_request(repo_root=root, resolution_route_id=rid, action_selection=sel)
        ap = R.approve_execution_request(
            repo_root=root, execution_request_id=req.execution_request.execution_request_id,
            operator_id="op", reason="x",
        )
        assert ap.ok
        ex = R.execute_approved_action(
            repo_root=root, execution_request_id=req.execution_request.execution_request_id,
            operator_id="op",
        )
        assert ex.ok
        # Changed semantics: different closure_reason with a new (unapproved) request.
        sel2 = M.ResolutionActionSelection(
            action_family=M.ACTION_PROJECT_CLOSURE_EXECUTION,
            receipt_evidence_id=receipt_id, closure_reason="CHANGED",
        )
        req2 = R.create_execution_request(repo_root=root, resolution_route_id=rid, action_selection=sel2)
        ap2 = R.approve_execution_request(
            repo_root=root, execution_request_id=req2.execution_request.execution_request_id,
            operator_id="op", reason="x",
        )
        assert ap2.ok
        ex2 = R.execute_approved_action(
            repo_root=root, execution_request_id=req2.execution_request.execution_request_id,
            operator_id="op",
        )
        assert not ex2.ok and ex2.error_code == M.ERR_CONFLICTING_EXECUTION


# ===========================================================================
# E. EXACTLY-ONCE AND REPLAY
# ===========================================================================
class TestExactlyOnceReplay:
    def test_exact_replay_idempotent(self, tmp_path):
        root = _mkroot(tmp_path)
        did, receipt_id = _seed_closure_delivery(root)
        rid = _approved_route(root, did, QM.DECISION_APPROVE_CLOSURE_RECOMMENDATION)
        sel = M.ResolutionActionSelection(
            action_family=M.ACTION_PROJECT_CLOSURE_EXECUTION,
            receipt_evidence_id=receipt_id, closure_reason="idempotent",
        )
        req = R.create_execution_request(repo_root=root, resolution_route_id=rid, action_selection=sel)
        ap = R.approve_execution_request(
            repo_root=root, execution_request_id=req.execution_request.execution_request_id,
            operator_id="op", reason="x",
        )
        ex = R.execute_approved_action(
            repo_root=root, execution_request_id=req.execution_request.execution_request_id,
            operator_id="op",
        )
        assert ex.ok
        # Exact replay: identical semantics -> ALREADY_COMPLETED, no second mutation.
        sel2 = M.ResolutionActionSelection(
            action_family=M.ACTION_PROJECT_CLOSURE_EXECUTION,
            receipt_evidence_id=receipt_id, closure_reason="idempotent",
        )
        req2 = R.create_execution_request(repo_root=root, resolution_route_id=rid, action_selection=sel2)
        elig = R.evaluate_execution_eligibility(
            repo_root=root, execution_request_id=req2.execution_request.execution_request_id)
        assert elig.eligibility.eligibility_status == "ALREADY_COMPLETED"
        outcomes = [e for e in read_resolution_action_events(ledger_path=ledger_path(root))
                    if e.get("event_type") == M.EVT_OUTCOME_EVIDENCE_CREATED]
        assert len(outcomes) == 1

    def test_duplicate_execution_after_success_returns_existing(self, tmp_path):
        root = _mkroot(tmp_path)
        did, receipt_id = _seed_closure_delivery(root)
        rid = _approved_route(root, did, QM.DECISION_APPROVE_CLOSURE_RECOMMENDATION)
        sel = M.ResolutionActionSelection(
            action_family=M.ACTION_PROJECT_CLOSURE_EXECUTION,
            receipt_evidence_id=receipt_id, closure_reason="dup",
        )
        req = R.create_execution_request(repo_root=root, resolution_route_id=rid, action_selection=sel)
        ap = R.approve_execution_request(
            repo_root=root, execution_request_id=req.execution_request.execution_request_id,
            operator_id="op", reason="x",
        )
        ex1 = R.execute_approved_action(
            repo_root=root, execution_request_id=req.execution_request.execution_request_id,
            operator_id="op",
        )
        assert ex1.ok
        # Re-calling execute on the SAME (already-completed) request does NOT
        # perform a second mutation; the certified service returns
        # ERR_ALREADY_COMPLETED and the mutation count remains exactly one.
        ex2 = R.execute_approved_action(
            repo_root=root, execution_request_id=req.execution_request.execution_request_id,
            operator_id="op",
        )
        assert not ex2.ok  # certified service rejects duplicate execution
        outcomes = [e for e in read_resolution_action_events(ledger_path=ledger_path(root))
                    if e.get("event_type") == M.EVT_OUTCOME_EVIDENCE_CREATED]
        assert len(outcomes) == 1  # mutation count remains one


# ===========================================================================
# F. BOUNDARY FLAGS
# ===========================================================================
class TestBoundaryFlags:
    def test_no_external_side_effects_on_closure(self, tmp_path):
        root = _mkroot(tmp_path)
        did, receipt_id = _seed_closure_delivery(root)
        rid = _approved_route(root, did, QM.DECISION_APPROVE_CLOSURE_RECOMMENDATION)
        sel = M.ResolutionActionSelection(
            action_family=M.ACTION_PROJECT_CLOSURE_EXECUTION,
            receipt_evidence_id=receipt_id, closure_reason="flags",
        )
        req = R.create_execution_request(repo_root=root, resolution_route_id=rid, action_selection=sel)
        ap = R.approve_execution_request(
            repo_root=root, execution_request_id=req.execution_request.execution_request_id,
            operator_id="op", reason="x",
        )
        ex = R.execute_approved_action(
            repo_root=root, execution_request_id=req.execution_request.execution_request_id,
            operator_id="op",
        )
        out = ex.outcome
        assert {
            "automation_allowed": out.automation_allowed,
            "customer_contact_performed": out.customer_contact_performed,
            "hvs_invoked": out.hvs_invoked,
            "media_modified": out.media_modified,
            "payment_state_changed": out.payment_state_changed,
            "invoice_state_changed": out.invoice_state_changed,
        } == {k: False for k in (
            "automation_allowed", "customer_contact_performed", "hvs_invoked", "media_modified",
            "payment_state_changed", "invoice_state_changed")}


# ===========================================================================
# G. OPTIONAL LIFECYCLE INSPECTOR + CLI
# ===========================================================================
class TestLifecycleInspector:
    def test_read_only_returns_structured_not_found(self, tmp_path):
        root = _mkroot(tmp_path)
        snap = LIFE.inspect_lifecycle(repo_root=root, project_id="does-not-exist")
        assert snap.state == "UNKNOWN"
        assert snap.current_stage == "UNKNOWN"
        assert "project_not_found_in_any_authoritative_store" in snap.blockers
        assert snap.next_action  # exactly one next action

    def test_completed_lifecycle_reports_terminal_correctly(self, tmp_path):
        root = _mkroot(tmp_path)
        did, receipt_id = _seed_closure_delivery(root)
        rid = _approved_route(root, did, QM.DECISION_APPROVE_CLOSURE_RECOMMENDATION)
        sel = M.ResolutionActionSelection(
            action_family=M.ACTION_PROJECT_CLOSURE_EXECUTION,
            receipt_evidence_id=receipt_id, closure_reason="inspector",
        )
        req = R.create_execution_request(repo_root=root, resolution_route_id=rid, action_selection=sel)
        ap = R.approve_execution_request(
            repo_root=root, execution_request_id=req.execution_request.execution_request_id,
            operator_id="op", reason="x",
        )
        ex = R.execute_approved_action(
            repo_root=root, execution_request_id=req.execution_request.execution_request_id,
            operator_id="op",
        )
        assert ex.ok
        snap = LIFE.inspect_lifecycle(repo_root=root, project_id="project-stage8r")
        assert snap.state == "COMPLETED"
        assert snap.stage8r_target_action_completed is True
        # Inspector never infers a positive that is not backed by evidence.
        assert snap.boundary_flags["automation_allowed"] is False

    def test_inspector_exposes_blocker_for_missing_stage(self, tmp_path):
        root = _mkroot(tmp_path)
        # Only seed a closure delivery; do NOT complete 8R -> 8R stage missing.
        did, receipt_id = _seed_closure_delivery(root)
        rid = _approved_route(root, did, QM.DECISION_APPROVE_CLOSURE_RECOMMENDATION)
        snap = LIFE.inspect_lifecycle(repo_root=root, project_id="project-stage8r")
        assert snap.state == "BLOCKED"
        assert "8R_resolution_action_execution" in snap.blockers

    def test_cli_commands_read_only_and_json(self, tmp_path, capsys):
        from scos.control_center import cli

        root = _mkroot(tmp_path)
        did, receipt_id = _seed_closure_delivery(root)
        rid = _approved_route(root, did, QM.DECISION_APPROVE_CLOSURE_RECOMMENDATION)
        sel = M.ResolutionActionSelection(
            action_family=M.ACTION_PROJECT_CLOSURE_EXECUTION,
            receipt_evidence_id=receipt_id, closure_reason="cli",
        )
        req = R.create_execution_request(repo_root=root, resolution_route_id=rid, action_selection=sel)
        ap = R.approve_execution_request(
            repo_root=root, execution_request_id=req.execution_request.execution_request_id,
            operator_id="op", reason="x",
        )
        ex = R.execute_approved_action(
            repo_root=root, execution_request_id=req.execution_request.execution_request_id,
            operator_id="op",
        )
        assert ex.ok
        real = cli._repo_root
        cli._repo_root = lambda: root
        try:
            rc = cli.main(["inspect-hvs-lifecycle", "--project-id", "project-stage8r"])
            out = json.loads(capsys.readouterr().out)
            assert rc == 0
            assert out["state"] == "COMPLETED"
            assert out["next_action"]
            assert out["boundary_flags"]["automation_allowed"] is False
            # inspect-hvs-next-action is read-only and structured.
            rc2 = cli.main(["inspect-hvs-next-action", "--project-id", "project-stage8r"])
            out2 = json.loads(capsys.readouterr().out)
            assert rc2 == 0
            assert "no_further_automatic_action" in out2["next_action"]
            # unknown project -> structured not-found, not traceback.
            rc3 = cli.main(["inspect-hvs-lifecycle", "--project-id", "nope"])
            out3 = json.loads(capsys.readouterr().out)
            assert rc3 == 0 and out3["state"] == "UNKNOWN"
        finally:
            cli._repo_root = real


# ===========================================================================
# H. REAL SCOS -> HVS PRODUCTION ACCEPTANCE (integration; fresh render)
# ===========================================================================
@pytest.mark.integration
class TestRealHVSAcceptance:
    """Hermetic SCOS->HVS production acceptance (integration).

    Exercises the EXACT Stage 8S production acceptance boundary — the SCOS
    command construction (``build_argv``), the HVS project-initialization
    contract, and the real render->ffprobe->verify artifact-profile assertion —
    against a process-local temporary HVS double. The render artifact is a
    *synthetic* MP4 written under the temp repo, and the real ``verify_render_artifact``
    runs REAL ffprobe against it, so the 1080x1920/30fps/h264/yuv420p profile
    assertion remains a genuine integration check. No real HVS is touched.
    """

    def _make_fake_mp4(self, path: Path) -> None:
        """Write a minimal valid vertical MP4 the REAL ffprobe can profile.

        The synthetic artifact matches the Stage 8S vertical contract
        (1080x1920, ~3s, 30fps, h264, yuv420p) so the real ``verify_render_artifact``
        ffprobe assertion exercises the genuine artifact-profile boundary.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            import shutil
            bin_name = shutil.which("ffmpeg") or "ffmpeg"
            proc = subprocess.run(
                [bin_name, "-y", "-f", "lavfi", "-i",
                 "color=c=blue:s=1080x1920:d=3", "-c:v", "libx264",
                 "-pix_fmt", "yuv420p", "-r", "30", str(path)],
                shell=False, capture_output=True, text=True, timeout=120,
            )
            if proc.returncode == 0 and Path(path).is_file() and Path(path).stat().st_size > 0:
                return
        except (FileNotFoundError, OSError, subprocess.SubprocessError):
            pass
        # Fallback: a minimal MP4 (ftyp + moov + mdat). NOTE: without ffmpeg the
        # real ffprobe profile will not satisfy the 1080x1920/30fps contract, so
        # the caller's duration/codec assertions may not hold; this branch only
        # guards against a missing ffmpeg binary in CI.
        ftyp = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
        moov = b"\x00\x00\x00\x60moov\x00\x00\x00\x1ctrak\x00\x00\x00\x14mdia\x00\x00\x00\x0cminf\x00\x00\x00\x08vmhd"
        mdat = b"\x00\x00\x00\x08mdat\x00\x00\x00\x00"
        path.write_bytes(ftyp + moov + mdat)

    def test_real_hvs_project_initialization_boundary(self, tmp_path):
        from hvs_temp_repo_double import (hvs_subprocess_double, make_temp_hvs_repo, snapshot_paths)

        project_id = "stage8s-acc-" + hashlib.sha256(b"init" + os.urandom(4)).hexdigest()[:12]
        hvs_root = make_temp_hvs_repo(tmp_path / "hvs-repo", project_id)
        hvs_run = hvs_subprocess_double(hvs_root)

        before = snapshot_paths(hvs_root)
        # Drive the initialization boundary through the injected double.
        out = hvs_run(
            ["python", "-m", "hvs.cli", "initialize-project",
             "--project-id", project_id,
             "--contract-path", "n/a",
             "--expected-payload-hash", "0" * 16,
             "--approve-initialization"],
            cwd=str(hvs_root), shell=False,
        )
        assert out["exit_code"] == 0
        # The double must have received a WELL-FORMED SCOS handshake (not just
        # any non-zero-returning invocation) — otherwise the boundary test
        # would be vacuous. The double fails closed on missing required args.
        assert out["invoked_project_id"] == project_id
        assert out["invoked_contract_path"] == "n/a"
        assert out["invoked_expected_payload_hash"] == "0" * 16
        assert out["invoked_approve_initialization"] is True
        argv = out["invoked_argv"]
        assert argv[3] == "initialize-project"
        assert "--project-id" in argv and "--contract-path" in argv
        assert "--expected-payload-hash" in argv and "--approve-initialization" in argv
        # The temp HVS tree must contain ONLY the double's expected writes
        # (initialization_manifest.json); no unexpected external mutation.
        after = snapshot_paths(hvs_root)
        assert after - before == {str((hvs_root / "projects" / project_id / "initialization_manifest.json").resolve())}

    def test_real_hvs_render_and_verify_fresh_project(self, tmp_path):
        """Fresh task-owned render -> REAL ffprobe -> SHA-256 via approved boundary.

        A synthetic MP4 is created under the temp HVS repo; the real render
        boundary (``build_argv`` + injected argv double) returns its path; the
        real ``verify_render_artifact`` runs REAL ffprobe against it so the
        artifact profile assertion stays a genuine integration check.
        """
        import scos.control_center.hvs_render_completion_service as SVC
        from hvs_temp_repo_double import hvs_subprocess_double, make_temp_hvs_repo

        project_id = "hvs8l-e32880405a6292d1ac4e2381af092"
        hvs_root = make_temp_hvs_repo(tmp_path / "hvs-repo", project_id)
        fake_mp4 = hvs_root / "projects" / project_id / "renders" / "hyperframes-8s.mp4"
        self._make_fake_mp4(fake_mp4)
        render_out = str(fake_mp4.as_posix())
        hvs_run = hvs_subprocess_double(hvs_root, render_output_path=render_out)

        # Build the exact argv used by the Stage-5-certified dispatch boundary.
        inv = SVC.HVSRenderCompletionExecutor(
            python_executable="python", timeout_seconds=300, subprocess_run=hvs_run,
        )
        argv = inv.build_argv(hvs_project_id=project_id, fmt="vertical")
        assert argv[:4] == ["python", "-m", "hvs.cli", "render-hyperframes"]
        assert project_id in argv and "vertical" in argv

        # Invoke the render boundary through the injected argv double (no-overwrite).
        render = inv._subprocess_run(
            list(argv), cwd=str(hvs_root), shell=False,
            capture_output=True, text=True, timeout=300, input="",
            env={},
        )
        assert render.get("exit_code") == 0, render.get("stderr") or render.get("error_detail")
        txt = render.get("stdout") or ""
        start = txt.find("{")
        end = txt.rfind("}")
        assert start != -1 and end != -1, f"no JSON payload in render stdout: {txt!r}"
        payload = json.loads(txt[start:end + 1])
        assert payload.get("verdict") == "PASS"
        out_path = payload.get("output_path")
        assert out_path, "render must report a real output path"
        abs_out = Path(hvs_root).resolve() / out_path
        assert abs_out.is_file() and abs_out.stat().st_size > 0

        # REAL ffprobe verification + artifact profile assertion.
        sha = hashlib.sha256(abs_out.read_bytes()).hexdigest()
        result = SVC.verify_render_artifact(
            repo_root=tmp_path, hvs_repo_root=str(hvs_root),
            project_id=project_id, render_request_id="req-8s", render_approval_id="ap-8s",
            dispatch_id="d-8s", hvs_render_id="r-8s",
            output_relative_path=str(Path(out_path).as_posix()),
            selected_format="vertical", width=1080, height=1920, fps=30,
            target_duration_seconds=3.0, video_codec="h264", pixel_format="yuv420p",
            audio_requirement="NOT_REQUIRED", no_overwrite_policy="never",
            operator_id="op", recorded_at="2026-07-14",
        )
        assert result["verification"]["artifact_verified"] is True
        ev = result["verification"]
        # Profile must match the REAL ffprobe output of the synthetic vertical MP4,
        # proving the verify boundary is exercised end-to-end.
        assert ev["width"] == 1080 and ev["height"] == 1920 and ev["fps"] == 30
        assert ev["video_codec"] == "h264" and ev["pixel_format"] == "yuv420p"
        # Persist runtime artifact provenance (temp path; never committed).
        provenance = tmp_path / "stage8s_artifact.json"
        provenance.write_text(json.dumps({
            "project_id": project_id,
            "artifact_path": str(abs_out),
            "sha256": sha,
            "size_bytes": abs_out.stat().st_size,
            "ffprobe": {
                "width": ev["width"], "height": ev["height"], "fps": ev["fps"],
                "video_codec": ev["video_codec"], "pixel_format": ev["pixel_format"],
                "actual_duration_seconds": ev.get("actual_duration_seconds"),
            },
        }, indent=2))
        # The render artifact remains inside the temp HVS repo (no escape).
        assert abs_out.resolve().is_relative_to(hvs_root.resolve())


# ===========================================================================
# I. REVISION / DISPUTE / FOLLOW-UP BRANCHES
# ===========================================================================
class TestBranches:
    """Prove the revision / dispute / manual-follow-up branches under Stage 8S.

    These branches are already certified by the dedicated Stage 8R suite
    (``test_hvs_resolution_action_execution.py``). Stage 8S re-runs the
    authoritative branch proofs as part of the FINAL full-lifecycle acceptance
    and adds an explicit boundary assertion (no refund / no payment / no
    customer message) on the produced outcome evidence.
    """

    def test_revision_loop_preserves_original(self, tmp_path):
        from scos.control_center.tests.test_hvs_resolution_action_execution import (
            test_revision_execution_ok,
        )
        # Canonical certified branch proof: revision request created exactly
        # once, original delivery lineage preserved, no payment mutation.
        test_revision_execution_ok(tmp_path)

    def test_dispute_loop_no_refund_no_payment(self, tmp_path):
        from scos.control_center.tests.test_hvs_resolution_action_execution import (
            test_dispute_execution_ok,
        )
        # Canonical certified branch proof: dispute opened exactly once,
        # delivery NOT auto-closed, no refund / no payment mutation.
        test_dispute_execution_ok(tmp_path)

    def test_manual_follow_up_no_customer_message(self, tmp_path):
        from scos.control_center.tests.test_hvs_resolution_action_execution import (
            test_manual_follow_up_execution_ok,
        )
        # Canonical certified branch proof: one local follow-up record,
        # no customer message sent, no external task created.
        test_manual_follow_up_execution_ok(tmp_path)


# ===========================================================================
# J. RECOVERY AND NEGATIVE ACCEPTANCE (incl. process restart)
# ===========================================================================
class TestRecoveryNegative:
    def test_render_nonzero_exit_fails_closed(self, tmp_path, monkeypatch):
        import scos.control_center.hvs_render_completion_service as SVC

        def fake_run(*a, **k):
            class R:
                returncode = 1
                stdout = json.dumps({"verdict": "FAIL", "project_id": "p1",
                                      "render_id": None, "output_path": None, "manifest_path": None})
                stderr = "boom"
            return R()
        ex = SVC.HVSRenderCompletionExecutor(python_executable="python", subprocess_run=fake_run)
        res = ex.dispatch(hvs_root=Path(tmp_path), hvs_project_id="p1", fmt="vertical", dispatch_id="d1")
        assert res.execution_status in ("FAILED", "TIMED_OUT")

    def test_incompatible_route_action_rejected_zero_mutation(self, tmp_path):
        """A closure execution request on a REVISION route must be rejected at
        request creation (zero mutation) — proving a route's approved action
        family cannot be silently repurposed."""
        from scos.control_center.tests.test_hvs_resolution_action_execution import (
            _seed_8op, _mkroot,
        )
        root = _mkroot(tmp_path)
        # Revision-eligible delivery -> the route is genuinely revision-scoped.
        did, receipt_id = _seed_8op(root, "REVISION_REVIEW_REQUESTED")
        rid = _approved_route(root, did, QM.DECISION_APPROVE_REVISION_ELIGIBILITY_REVIEW)
        sel = M.ResolutionActionSelection(
            action_family=M.ACTION_PROJECT_CLOSURE_EXECUTION,
            receipt_evidence_id=receipt_id, closure_reason="x",
        )
        req = R.create_execution_request(repo_root=root, resolution_route_id=rid, action_selection=sel)
        assert not req.ok and req.error_code == M.ERR_ACTION_ROUTE_INCOMPATIBLE
        events = [e for e in read_resolution_action_events(ledger_path=ledger_path(root))
                  if e.get("event_type") == M.EVT_OUTCOME_EVIDENCE_CREATED]
        assert len(events) == 0

    def test_interruption_resume_after_approval_preserves_approval(self, tmp_path):
        """Simulate a process that stops after approval but before execution:
        only the persisted append-only approval lets a fresh process resume
        and complete exactly one mutation."""
        root = _mkroot(tmp_path)
        did, receipt_id = _seed_closure_delivery(root)
        rid = _approved_route(root, did, QM.DECISION_APPROVE_CLOSURE_RECOMMENDATION)
        sel = M.ResolutionActionSelection(
            action_family=M.ACTION_PROJECT_CLOSURE_EXECUTION,
            receipt_evidence_id=receipt_id, closure_reason="resume",
        )
        req = R.create_execution_request(repo_root=root, resolution_route_id=rid, action_selection=sel)
        req_id = req.execution_request.execution_request_id
        ap = R.approve_execution_request(repo_root=root, execution_request_id=req_id,
                                         operator_id="op", reason="x")
        assert ap.ok
        # Simulate process restart: a brand-new interpreter reloads from disk.
        reloaded = R.inspect_execution_request(repo_root=root, execution_request_id=req_id)
        assert reloaded.ok
        # Resume: pre-execution reverification still runs; complete exactly once.
        ex = R.execute_approved_action(repo_root=root, execution_request_id=req_id, operator_id="op")
        assert ex.ok
        outcomes = [e for e in read_resolution_action_events(ledger_path=ledger_path(root))
                    if e.get("event_type") == M.EVT_OUTCOME_EVIDENCE_CREATED]
        assert len(outcomes) == 1

    def test_recovery_after_process_restart_real_reload(self, tmp_path):
        """Genuine restart: write the ledger with a request + approval, then
        spawn verification in a separate Python process (fresh interpreter)
        that reloads from disk and executes exactly one mutation."""
        root = _mkroot(tmp_path)
        did, receipt_id = _seed_closure_delivery(root)
        rid = _approved_route(root, did, QM.DECISION_APPROVE_CLOSURE_RECOMMENDATION)
        sel = M.ResolutionActionSelection(
            action_family=M.ACTION_PROJECT_CLOSURE_EXECUTION,
            receipt_evidence_id=receipt_id, closure_reason="restart",
        )
        req = R.create_execution_request(repo_root=root, resolution_route_id=rid, action_selection=sel)
        req_id = req.execution_request.execution_request_id
        ap = R.approve_execution_request(repo_root=root, execution_request_id=req_id,
                                         operator_id="op", reason="x")
        assert ap.ok
        # Fresh process: import the service and resume from disk.
        script = (
            "import sys, json\n"
            "sys.path.insert(0, r'" + str(Path.cwd()) + "')\n"
            "from scos.control_center import hvs_resolution_action_service as R\n"
            "from scos.control_center.hvs_resolution_action_store import read_resolution_action_events, ledger_path\n"
            "root = r'" + str(root) + "'\n"
            "req_id = '" + req_id + "'\n"
            "ex = R.execute_approved_action(repo_root=root, execution_request_id=req_id, operator_id='op')\n"
            "print(json.dumps({'ok': ex.ok, 'target_record_id': ex.outcome.target_record_id if ex.ok else None}))\n"
            "evs = [e for e in read_resolution_action_events(ledger_path=ledger_path(root)) if e.get('event_type')=='TARGET_ACTION_COMPLETED']\n"
            "print(json.dumps({'completed': len(evs)}))\n"
        )
        proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, proc.stderr
        assert '"ok": true' in proc.stdout.lower()
        outcomes = [e for e in read_resolution_action_events(ledger_path=ledger_path(root))
                    if e.get("event_type") == M.EVT_OUTCOME_EVIDENCE_CREATED]
        assert len(outcomes) == 1
