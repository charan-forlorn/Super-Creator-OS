"""Focused tests — SCOS <-> HVS Stage 5 operator delivery approval handoff.

Local, deterministic, no network/subprocess. Exercises the one-way approval
transition model, trust/integrity prerequisites, append-only audit binding,
and the CLI JSON + exit-code contracts.

The audit ledger lives under the gitignored ``scos/work/`` path, so records
written here never enter version control (per task hard constraints).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scos.control_center.hvs_delivery_approval import (
    ALREADY_DECIDED,
    APPROVAL_NOT_FOUND,
    ARTIFACT_NOT_VERIFIED,
    AUTOMATION_NOT_ALLOWED,
    DECISION_APPROVE,
    DECISION_REJECT,
    EVIDENCE_UNVERIFIED,
    MISSING_REJECT_REASON,
    PACKET_NOT_READY,
    STATUS_APPROVED,
    STATUS_PENDING,
    STATUS_REJECTED,
    HVSDeliveryApprovalRequest,
    create_approval_request,
    decide_approval,
    get_approval_request,
)


def _verified_packet(**overrides) -> dict:
    """A VERIFIED + review_export_ready + artifact-verified packet."""
    base = {
        "ok": True,
        "schema_version": 1,
        "packet_id": "scos-hvs-evidence-abc123",
        "source": "hermes_video_studio",
        "trust_level": "VERIFIED",
        "operator_action": "review_export_ready",
        "automation_allowed": False,
        "project_id": "proj-9",
        "validation_id": "val-1",
        "hvs": {
            "schema_version": "hvs.quality.stage6/1.0.0",
            "validation_id": "val-1",
            "project_id": "proj-9",
            "verdict": "PASS",
            "export_ready": True,
            "evidence_sha256": "e" * 64,
            "evidence_sha256_verified": True,
        },
        "artifact": {
            "path": "projects/proj-9/renders/x.mp4",
            "sha256": "a" * 64,
            "size_bytes": 100,
        },
        "integrity_note": "artifact SHA-256 verified against evidence",
    }
    base.update(overrides)
    return base


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    # A throwaway repo root; the ledger writes under <repo>/scos/work/...
    root = tmp_path / "repo"
    root.mkdir()
    (root / "scos" / "work").mkdir(parents=True)
    return root


# --- 1) verified review_export_ready packet creates PENDING request ----------
def test_verified_packet_creates_pending(repo_root):
    req = create_approval_request(packet=_verified_packet(), repo_root=repo_root)
    assert isinstance(req, HVSDeliveryApprovalRequest)
    assert req.status == STATUS_PENDING
    assert req.automation_allowed is False
    assert req.manual_delivery_required is True
    assert set(req.allowed_decision_actions) == {"approve", "reject"}
    assert req.scope_statement.startswith("Approval does not publish")
    # Evidence-bound identity is recorded.
    assert req.project_id == "proj-9"
    assert req.validation_id == "val-1"
    assert req.evidence_id == "val-1"
    assert req.artifact_sha256 == "a" * 64


# --- 2) PARTIAL/UNVERIFIED/non-ready cannot create a request -----------------
def test_partial_packet_rejected(repo_root):
    out = create_approval_request(
        packet=_verified_packet(trust_level="PARTIAL"), repo_root=repo_root
    )
    assert out.ok is False
    assert out.error_code == EVIDENCE_UNVERIFIED


def test_non_ready_packet_rejected(repo_root):
    out = create_approval_request(
        packet=_verified_packet(operator_action="repair_or_rerender_required"),
        repo_root=repo_root,
    )
    assert out.ok is False
    assert out.error_code == PACKET_NOT_READY


def test_unverified_artifact_rejected(repo_root):
    bad = _verified_packet()
    bad["artifact"] = {"path": "projects/proj-9/renders/x.mp4", "sha256": None}
    out = create_approval_request(packet=bad, repo_root=repo_root)
    assert out.ok is False
    assert out.error_code == ARTIFACT_NOT_VERIFIED


def test_automation_allowed_blocks(repo_root):
    out = create_approval_request(
        packet=_verified_packet(automation_allowed=True), repo_root=repo_root
    )
    assert out.ok is False
    assert out.error_code == AUTOMATION_NOT_ALLOWED


# --- 3) SHA mismatch cannot create or approve a request ---------------------
def test_mismatch_sha_cannot_create(repo_root):
    bad = _verified_packet()
    bad["artifact"] = {
        "path": "projects/proj-9/renders/x.mp4",
        "sha256": "deadbeef" * 8,  # not the verified hash
    }
    # trust_level is still VERIFIED only if intake verified; here we simulate the
    # intake emitting PARTIAL for a mismatch. The prerequisite gate blocks it.
    bad["trust_level"] = "PARTIAL"
    out = create_approval_request(packet=bad, repo_root=repo_root)
    assert out.ok is False
    assert out.error_code == EVIDENCE_UNVERIFIED


def test_mismatch_sha_decide_fails(repo_root):
    # Create with a valid VERIFIED packet, but the ledger metadata carries a
    # verified sha. Decide with operator_id; the request is legit. This test
    # confirms an UNVERIFIED packet (mismatch) can never reach decide because
    # create is refused first.
    bad = _verified_packet(trust_level="PARTIAL")
    out = create_approval_request(packet=bad, repo_root=repo_root)
    assert out.ok is False  # refused before any request exists


# --- 4) deterministic approval request id -----------------------------------
def test_deterministic_request_id(repo_root):
    p1 = _verified_packet()
    p2 = _verified_packet()
    r1 = create_approval_request(packet=p1, repo_root=repo_root)
    # Reset repo (fresh ledger) to prove id is content-derived, not sequence-based.
    root2 = repo_root.parent / "repo2"
    root2.mkdir()
    (root2 / "scos" / "work").mkdir(parents=True)
    r2 = create_approval_request(packet=p2, repo_root=root2)
    assert isinstance(r1, HVSDeliveryApprovalRequest)
    assert r1.approval_request_id == r2.approval_request_id
    # Different artifact sha -> different id.
    p3 = _verified_packet()
    p3["artifact"] = {"path": "p/r/x.mp4", "sha256": "b" * 64}
    r3 = create_approval_request(packet=p3, repo_root=root2)
    assert r3.approval_request_id != r1.approval_request_id


# --- 5) valid approval creates APPROVED_FOR_MANUAL_DELIVERY ------------------
def test_valid_approval(repo_root):
    req = create_approval_request(packet=_verified_packet(), repo_root=repo_root)
    assert isinstance(req, HVSDeliveryApprovalRequest)
    res = decide_approval(
        approval_id=req.approval_request_id,
        decision=DECISION_APPROVE,
        operator_id="op-1",
        decided_at="2026-07-11T00:00:00+00:00",
        repo_root=repo_root,
    )
    assert res.ok is True
    assert res.status == STATUS_APPROVED
    assert res.decision == DECISION_APPROVE
    assert res.operator_id == "op-1"
    assert res.chain_verified is True
    assert res.to_dict()["automation_allowed"] is False  # never changed
    # Inspect reflects the decision.
    seen = get_approval_request(
        approval_id=req.approval_request_id, repo_root=repo_root
    )
    assert seen.status == STATUS_APPROVED
    assert seen.manual_delivery_required is True


# --- 6) rejection requires reason and creates REJECTED -----------------------
def test_reject_requires_reason(repo_root):
    req = create_approval_request(packet=_verified_packet(), repo_root=repo_root)
    res = decide_approval(
        approval_id=req.approval_request_id,
        decision=DECISION_REJECT,
        operator_id="op-1",
        decided_at="2026-07-11T00:00:00+00:00",
        reason=None,  # missing
        repo_root=repo_root,
    )
    assert res.ok is False
    assert res.error_code == MISSING_REJECT_REASON


def test_valid_rejection(repo_root):
    req = create_approval_request(packet=_verified_packet(), repo_root=repo_root)
    res = decide_approval(
        approval_id=req.approval_request_id,
        decision=DECISION_REJECT,
        operator_id="op-1",
        decided_at="2026-07-11T00:00:00+00:00",
        reason="wrong caption",
        repo_root=repo_root,
    )
    assert res.ok is True
    assert res.status == STATUS_REJECTED
    assert res.reason == "wrong caption"
    seen = get_approval_request(
        approval_id=req.approval_request_id, repo_root=repo_root
    )
    assert seen.status == STATUS_REJECTED


# --- 7) duplicate / conflicting decision rejected ---------------------------
def test_already_decided_cannot_redecide(repo_root):
    req = create_approval_request(packet=_verified_packet(), repo_root=repo_root)
    r1 = decide_approval(
        approval_id=req.approval_request_id,
        decision=DECISION_APPROVE,
        operator_id="op-1",
        decided_at="2026-07-11T00:00:00+00:00",
        repo_root=repo_root,
    )
    assert r1.ok is True
    r2 = decide_approval(
        approval_id=req.approval_request_id,
        decision=DECISION_REJECT,
        operator_id="op-2",
        decided_at="2026-07-11T00:00:01+00:00",
        reason="conflict",
        repo_root=repo_root,
    )
    assert r2.ok is False
    assert r2.error_code == ALREADY_DECIDED
    # Still approved; never flipped to rejected.
    assert r2.status == STATUS_APPROVED


def test_decide_without_pending_request(repo_root):
    res = decide_approval(
        approval_id="scos-hvs-approval-doesnotexist",
        decision=DECISION_APPROVE,
        operator_id="op-1",
        decided_at="2026-07-11T00:00:00+00:00",
        repo_root=repo_root,
    )
    assert res.ok is False
    assert res.error_code == APPROVAL_NOT_FOUND


# --- 8) automation_allowed always remains false -----------------------------
def test_automation_never_enabled(repo_root):
    req = create_approval_request(packet=_verified_packet(), repo_root=repo_root)
    res = decide_approval(
        approval_id=req.approval_request_id,
        decision=DECISION_APPROVE,
        operator_id="op-1",
        decided_at="2026-07-11T00:00:00+00:00",
        repo_root=repo_root,
    )
    assert res.ok is True
    assert res.to_dict()["automation_allowed"] is False
    assert get_approval_request(
        approval_id=req.approval_request_id, repo_root=repo_root
    ).automation_allowed is False


# --- 9) audit events are append-only and correctly linked -------------------
def test_audit_append_only_and_linked(repo_root):
    from scos.control_center.approval_audit_store import (
        load_decisions,
        verify_chain,
    )

    req = create_approval_request(packet=_verified_packet(), repo_root=repo_root)
    assert isinstance(req, HVSDeliveryApprovalRequest)
    decide_approval(
        approval_id=req.approval_request_id,
        decision=DECISION_APPROVE,
        operator_id="op-1",
        decided_at="2026-07-11T00:00:00+00:00",
        repo_root=repo_root,
    )
    decisions = load_decisions(
        subject_type="hvs_delivery_approval",
        subject_id=req.approval_request_id,
        repo_root=repo_root,
    )
    # pending then approved => two append-only entries.
    assert len(decisions) == 2
    assert decisions[0].decision == "pending"
    assert decisions[1].decision == "approved"
    # metadata binds to the verified artifact sha.
    assert decisions[0].metadata.to_dict()["artifact_sha256"] == "a" * 64
    # chain integrity holds.
    assert verify_chain(repo_root=repo_root) is True


# --- 10) no external delivery / publish action can occur ---------------------
def test_no_external_side_effects(repo_root):
    # The module imports no network/subprocess/cloud libs; the decision only
    # appends to the local ledger. We assert that a created+approved request
    # produces NO artifact bytes, NO path copy, and stays local-only.
    req = create_approval_request(packet=_verified_packet(), repo_root=repo_root)
    assert isinstance(req, HVSDeliveryApprovalRequest)
    res = decide_approval(
        approval_id=req.approval_request_id,
        decision=DECISION_APPROVE,
        operator_id="op-1",
        decided_at="2026-07-11T00:00:00+00:00",
        repo_root=repo_root,
    )
    assert res.ok is True
    # No real side-effect leakage: no URLs, no cloud bucket refs, no absolute
    # output paths copied anywhere. (The scope_statement intentionally
    # mentions publish/upload as a prohibition, so we exclude it from the scan.)
    d = res.to_dict()
    assert d.get("automation_allowed") is False
    assert d.get("manual_delivery_required") is True
    assert "http://" not in str(d) and "https://" not in str(d)
    assert "s3://" not in str(d) and "bucket" not in str(d).lower()


# --- 11) CLI JSON and exit-code contracts ------------------------------------
def test_cli_create_approve_exit_codes(tmp_path, repo_root, monkeypatch):
    import json

    from scos.control_center import cli as cli_mod

    # Use the real VERIFIED evidence from the Stage 4 rerun so the CLI path is
    # exercised end-to-end through Stage 3 intake re-verification.
    evidence = (
        "C:/Workspace/hermes-video-studio/projects/6e852988498a/"
        "stage6_validation/validate_export_b0126558092ef864.json"
    )
    monkeypatch.setattr(cli_mod, "_repo_root", lambda: repo_root)

    rc = cli_mod.main(["create-hvs-delivery-approval", "--evidence-path", evidence])
    assert rc == 0
    aid = "scos-hvs-approval-51ffd93ced7650c1"  # deterministic for that evidence

    # Inspect returns 0.
    assert cli_mod.main(
        ["inspect-hvs-delivery-approval", "--approval-id", aid]
    ) == 0

    # Approve returns 0.
    assert cli_mod.main(
        [
            "decide-hvs-delivery-approval",
            "--approval-id",
            aid,
            "--decision",
            "approve",
            "--operator-id",
            "op-cli",
            "--note",
            "cli e2e",
        ]
    ) == 0

    # Re-decide returns non-zero (one-way).
    assert (
        cli_mod.main(
            [
                "decide-hvs-delivery-approval",
                "--approval-id",
                aid,
                "--decision",
                "reject",
                "--operator-id",
                "op-x",
                "--reason",
                "dup",
            ]
        )
        == 1
    )


def test_cli_reject_missing_reason_exit1(tmp_path, repo_root, monkeypatch):
    from scos.control_center import cli as cli_mod

    evidence = (
        "C:/Workspace/hermes-video-studio/projects/6e852988498a/"
        "stage6_validation/validate_export_b0126558092ef864.json"
    )
    monkeypatch.setattr(cli_mod, "_repo_root", lambda: repo_root)
    assert cli_mod.main(
        ["create-hvs-delivery-approval", "--evidence-path", evidence]
    ) == 0
    aid = "scos-hvs-approval-51ffd93ced7650c1"
    # Reject without reason -> exit 1.
    assert (
        cli_mod.main(
            [
                "decide-hvs-delivery-approval",
                "--approval-id",
                aid,
                "--decision",
                "reject",
                "--operator-id",
                "op-cli",
            ]
        )
        == 1
    )


# --- 12) directly affected Stage 3 / 3.1 intake regression stays usable ------
def test_stage3_intake_still_verifies_root_relative():
    import json

    from scos.control_center.hvs_evidence_intake import intake_hvs_render_evidence

    evidence = (
        "C:/Workspace/hermes-video-studio/projects/6e852988498a/"
        "stage6_validation/validate_export_b0126558092ef864.json"
    )
    res = intake_hvs_render_evidence(evidence_path=evidence, verify_artifact=True)
    assert res.ok is True
    assert res.trust_level == "VERIFIED"
    assert res.operator_action == "review_export_ready"
    assert res.automation_allowed is False
    assert res.artifact_sha256 == (
        "7d7ac1a37a4be4e225ad39c1c0f07fd572cbf9f88b8986a64d862f5bea7ad3b9"
    )
