"""Stage 8G focused verification: post-delivery support policy, issue intake,
deterministic classification, dispute lifecycle, approval-gated reopen, and
commercial closure; fail-closed, append-only, no HVS / no outbound / no
invoice-payment mutation.

The Stage 8F release-ready + post-delivery-audit-closed context is constructed
by reusing the proven Stage 8F test harness so 8G is exercised on the same
upstream evidence.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scos.control_center.tests.test_hvs_manual_release_receipt_authorization import (
    _authorized_context as _e8_authorized_context,
    _reconcile_revised_delivery as _e8_reconcile,
)
from scos.control_center.hvs_revised_delivery_release_service import (
    close_final_revision,
    create_customer_release_authorization,
)
from scos.control_center.hvs_manual_release_receipt_service import (
    close_post_delivery_audit,
    record_customer_receipt,
    record_manual_release,
)
from scos.control_center.hvs_post_delivery_support_service import (
    approve_post_delivery_reopen,
    classify_post_delivery_issue,
    evaluate_commercial_closure,
    inspect_post_delivery_support_lineage,
    open_post_delivery_dispute,
    record_commercial_closure,
    record_post_delivery_issue,
    register_post_delivery_support_policy,
    request_post_delivery_reopen,
    resolve_post_delivery_dispute,
)
from scos.control_center.hvs_post_delivery_support_store import (
    post_delivery_support_path,
    read_post_delivery_support_events,
)
from scos.control_center.hvs_post_delivery_support_models import (
    COMMERCIAL_CLOSED,
    COMMERCIAL_BLOCKED,
    CLASS_COVERED_DEFECT,
    CLASS_COVERED_REVISION,
    CLASS_OUT_OF_SCOPE_CHANGE,
    CLASS_REJECTED_UNSUPPORTED,
    CLASS_SUPPORT_ONLY,
    DISPUTE_OPEN,
    DISPUTE_RESOLVED,
    DISPUTE_REJECTED,
    ISSUE_PRODUCTION_DEFECT,
    ISSUE_CUSTOMER_REVISION_REQUEST,
    ISSUE_DISPUTE,
    ISSUE_SCOPE_CHANGE,
    ISSUE_SUPPORT_QUESTION,
    ISSUE_UNSUPPORTED_REQUEST,
    REOPEN_APPROVED,
    REOPEN_TARGET_NO_REOPEN,
    REOPEN_TARGET_STAGE_8B,
    REOPEN_TARGET_STAGE_8C,
    SUPPORT_POLICY_ACTIVE,
)


def _reconcile_revised_delivery(repo_root: Path) -> dict[str, str]:
    return _e8_reconcile(repo_root)


def _authorized_context(repo_root: Path):
    return _e8_authorized_context(repo_root)


def _closed_context(repo_root):
    """Build a fully closed Stage 8F lineage: acceptance -> authorization ->
    final closure -> manual release -> receipt -> post-delivery audit closed."""
    ctx, acc, auth = _authorized_context(repo_root)
    close_final_revision(
        acceptance_id=acc.acceptance_id, authorization_id=auth.authorization_id,
        operator_id="op", repo_root=repo_root, recorded_at="t",
    )
    rel = record_manual_release(
        authorization_id=auth.authorization_id, released_by="operator-1",
        release_channel="email_manual", released_formats=("vertical",),
        customer_reference="cust-1", release_method_reference="manual-share-1",
        operator_id="op", repo_root=repo_root, recorded_at="t",
    )
    assert rel.ok
    rec = record_customer_receipt(
        release_id=rel.release.release_id, confirmed_by="cs-1", receipt_status="CONFIRMED",
        received_formats=("vertical",), customer_reference="cust-1",
        confirmation_reference="ticket-1", operator_id="op", repo_root=repo_root, recorded_at="t",
    )
    assert rec.ok
    audit = close_post_delivery_audit(
        authorization_id=auth.authorization_id, operator_id="op",
        repo_root=repo_root, recorded_at="t",
    )
    assert audit.ok
    return ctx, acc, auth, rel.release, rec.receipt, audit.audit


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "scos" / "work").mkdir(parents=True)
    return root


# ===========================================================================
# Support policy
# ===========================================================================
def test_register_support_policy_success(repo_root):
    ctx, acc, auth, rel, rec, audit = _closed_context(repo_root)
    out = register_post_delivery_support_policy(
        authorization_id=auth.authorization_id,
        support_window_start="2026-01-01", support_window_end="2026-02-01",
        policy_type="STANDARD", included_issue_categories=("PRODUCTION_DEFECT",),
        excluded_issue_categories=(), created_by_operator_id="op",
        policy_version="scos-hvs-support/1.0.0", repo_root=repo_root, recorded_at="t",
    )
    assert out.ok and out.policy is not None
    assert out.policy.status == SUPPORT_POLICY_ACTIVE
    assert out.policy.project_id == ctx["project_id"]


def test_register_support_policy_idempotent(repo_root):
    ctx, acc, auth, rel, rec, audit = _closed_context(repo_root)
    kw = dict(authorization_id=auth.authorization_id, support_window_start="2026-01-01",
              support_window_end="2026-02-01", policy_type="STANDARD",
              included_issue_categories=("PRODUCTION_DEFECT",), excluded_issue_categories=(),
              created_by_operator_id="op", policy_version="scos-hvs-support/1.0.0",
              repo_root=repo_root, recorded_at="t")
    first = register_post_delivery_support_policy(**kw)
    assert first.ok
    second = register_post_delivery_support_policy(**kw)
    assert second.ok and second.duplicate_of == first.policy.support_policy_id
    events = [e for e in read_post_delivery_support_events(audit_log_path=post_delivery_support_path(repo_root)) if e.event_type == "SUPPORT_POLICY_REGISTERED"]
    assert len(events) == 1


def test_register_support_policy_inverted_window_rejected(repo_root):
    ctx, acc, auth, rel, rec, audit = _closed_context(repo_root)
    out = register_post_delivery_support_policy(
        authorization_id=auth.authorization_id,
        support_window_start="2026-02-01", support_window_end="2026-01-01",  # inverted
        policy_type="STANDARD", included_issue_categories=("PRODUCTION_DEFECT",),
        excluded_issue_categories=(), created_by_operator_id="op",
        policy_version="scos-hvs-support/1.0.0", repo_root=repo_root, recorded_at="t",
    )
    assert not out.ok and out.error_code == "SUPPORT_POLICY_VALIDATION"


def test_register_support_policy_conflicting_rejected(repo_root):
    ctx, acc, auth, rel, rec, audit = _closed_context(repo_root)
    base = dict(authorization_id=auth.authorization_id, support_window_start="2026-01-01",
                support_window_end="2026-02-01", policy_type="STANDARD",
                included_issue_categories=("PRODUCTION_DEFECT",), excluded_issue_categories=(),
                created_by_operator_id="op", policy_version="scos-hvs-support/1.0.0",
                repo_root=repo_root, recorded_at="t")
    assert register_post_delivery_support_policy(**base).ok
    # Same identity (lineage+window+type+version) but different category content -> conflict.
    conflicting = dict(base, included_issue_categories=("SCOPE_CHANGE",))
    out = register_post_delivery_support_policy(**conflicting)
    assert not out.ok and out.error_code == "CONFLICTING_SUPPORT_POLICY"


def test_register_support_policy_audit_not_ready_rejected(repo_root):
    ctx, acc, auth = _authorized_context(repo_root)  # no release/receipt/closure
    out = register_post_delivery_support_policy(
        authorization_id=auth.authorization_id,
        support_window_start="2026-01-01", support_window_end="2026-02-01",
        policy_type="STANDARD", included_issue_categories=("PRODUCTION_DEFECT",),
        excluded_issue_categories=(), created_by_operator_id="op",
        policy_version="scos-hvs-support/1.0.0", repo_root=repo_root, recorded_at="t",
    )
    assert not out.ok and out.error_code == "POST_DELIVERY_AUDIT_NOT_READY"


# ===========================================================================
# Issue intake
# ===========================================================================
def _policy(repo_root, auth):
    return register_post_delivery_support_policy(
        authorization_id=auth.authorization_id, support_window_start="2026-01-01",
        support_window_end="2026-02-01", policy_type="STANDARD",
        included_issue_categories=("PRODUCTION_DEFECT", "CUSTOMER_REVISION_REQUEST",
                                   "SCOPE_CHANGE", "SUPPORT_QUESTION", "DISPUTE",
                                   "UNSUPPORTED_REQUEST"),
        excluded_issue_categories=(), created_by_operator_id="op",
        policy_version="scos-hvs-support/1.0.0", repo_root=repo_root, recorded_at="t",
    ).policy


def test_record_issue_success(repo_root):
    ctx, acc, auth, rel, rec, audit = _closed_context(repo_root)
    pol = _policy(repo_root, auth)
    out = record_post_delivery_issue(
        support_policy_id=pol.support_policy_id, issue_category=ISSUE_PRODUCTION_DEFECT,
        issue_summary="render glitch", recorded_by_operator_id="op",
        customer_reference="cust-1", affected_formats=("vertical",),
        reported_at="2026-01-10", artifact_sha256="sha256:" + "a" * 64,
        repo_root=repo_root, recorded_at="t",
    )
    assert out.ok and out.issue is not None
    assert out.issue.project_id == ctx["project_id"]
    assert out.issue.revision_id == ctx["revision_id"]
    assert out.issue.artifact_sha256 == "sha256:" + "a" * 64


def test_record_issue_idempotent(repo_root):
    ctx, acc, auth, rel, rec, audit = _closed_context(repo_root)
    pol = _policy(repo_root, auth)
    kw = dict(support_policy_id=pol.support_policy_id, issue_category=ISSUE_PRODUCTION_DEFECT,
              issue_summary="render glitch", recorded_by_operator_id="op",
              customer_reference="cust-1", affected_formats=("vertical",),
              reported_at="2026-01-10", repo_root=repo_root, recorded_at="t")
    first = record_post_delivery_issue(**kw)
    second = record_post_delivery_issue(**kw)
    assert second.ok and second.duplicate_of == first.issue.issue_id
    events = [e for e in read_post_delivery_support_events(audit_log_path=post_delivery_support_path(repo_root)) if e.event_type == "ISSUE_RECORDED"]
    assert len(events) == 1


def test_record_issue_unknown_category_rejected(repo_root):
    ctx, acc, auth, rel, rec, audit = _closed_context(repo_root)
    pol = _policy(repo_root, auth)
    out = record_post_delivery_issue(
        support_policy_id=pol.support_policy_id, issue_category="MYSTERY_CATEGORY",
        issue_summary="x", recorded_by_operator_id="op", customer_reference="cust-1",
        affected_formats=("vertical",), reported_at="2026-01-10",
        repo_root=repo_root, recorded_at="t",
    )
    assert not out.ok and out.error_code == "ISSUE_VALIDATION"


def test_record_issue_unsafe_customer_rejected(repo_root):
    ctx, acc, auth, rel, rec, audit = _closed_context(repo_root)
    pol = _policy(repo_root, auth)
    out = record_post_delivery_issue(
        support_policy_id=pol.support_policy_id, issue_category=ISSUE_PRODUCTION_DEFECT,
        issue_summary="x", recorded_by_operator_id="op", customer_reference="../escape",
        affected_formats=("vertical",), reported_at="2026-01-10",
        repo_root=repo_root, recorded_at="t",
    )
    assert not out.ok and out.error_code == "ISSUE_VALIDATION"


def test_record_issue_unsupported_format_rejected(repo_root):
    ctx, acc, auth, rel, rec, audit = _closed_context(repo_root)
    pol = _policy(repo_root, auth)
    out = record_post_delivery_issue(
        support_policy_id=pol.support_policy_id, issue_category=ISSUE_PRODUCTION_DEFECT,
        issue_summary="x", recorded_by_operator_id="op", customer_reference="cust-1",
        affected_formats=("not_a_real_format",), reported_at="2026-01-10",
        repo_root=repo_root, recorded_at="t",
    )
    assert not out.ok and out.error_code == "ISSUE_VALIDATION"


# ===========================================================================
# Classification
# ===========================================================================
def _issue(repo_root, pol, category=ISSUE_PRODUCTION_DEFECT, summary="render glitch"):
    return record_post_delivery_issue(
        support_policy_id=pol.support_policy_id, issue_category=category, issue_summary=summary,
        recorded_by_operator_id="op", customer_reference="cust-1",
        affected_formats=("vertical",), reported_at="2026-01-10",
        artifact_sha256="sha256:" + "a" * 64 if category == ISSUE_PRODUCTION_DEFECT else "",
        repo_root=repo_root, recorded_at="t",
    ).issue


def test_classify_production_defect_covered(repo_root):
    ctx, acc, auth, rel, rec, audit = _closed_context(repo_root)
    pol = _policy(repo_root, auth)
    issue = _issue(repo_root, pol, ISSUE_PRODUCTION_DEFECT)
    out = classify_post_delivery_issue(issue_id=issue.issue_id, classified_by_operator_id="op",
                                        repo_root=repo_root, recorded_at="2026-01-10")
    assert out.ok and out.classification.outcome == CLASS_COVERED_DEFECT
    assert out.classification.target_workflow == REOPEN_TARGET_STAGE_8C


def test_classify_revision_request_routes_8b(repo_root):
    ctx, acc, auth, rel, rec, audit = _closed_context(repo_root)
    pol = _policy(repo_root, auth)
    issue = _issue(repo_root, pol, ISSUE_CUSTOMER_REVISION_REQUEST, "new still")
    out = classify_post_delivery_issue(issue_id=issue.issue_id, classified_by_operator_id="op",
                                        repo_root=repo_root, recorded_at="2026-01-10")
    assert out.ok and out.classification.outcome == CLASS_COVERED_REVISION
    assert out.classification.target_workflow == REOPEN_TARGET_STAGE_8B


def test_classify_scope_change_commercial_review(repo_root):
    ctx, acc, auth, rel, rec, audit = _closed_context(repo_root)
    pol = _policy(repo_root, auth)
    issue = _issue(repo_root, pol, ISSUE_SCOPE_CHANGE, "bigger scope")
    out = classify_post_delivery_issue(issue_id=issue.issue_id, classified_by_operator_id="op",
                                        repo_root=repo_root, recorded_at="2026-01-10")
    assert out.ok and out.classification.outcome == CLASS_OUT_OF_SCOPE_CHANGE


def test_classify_unsupported_rejected(repo_root):
    ctx, acc, auth, rel, rec, audit = _closed_context(repo_root)
    pol = _policy(repo_root, auth)
    issue = _issue(repo_root, pol, ISSUE_UNSUPPORTED_REQUEST, "refund please")
    out = classify_post_delivery_issue(issue_id=issue.issue_id, classified_by_operator_id="op",
                                        repo_root=repo_root, recorded_at="2026-01-10")
    assert out.ok and out.classification.outcome == CLASS_REJECTED_UNSUPPORTED
    assert out.classification.target_workflow == REOPEN_TARGET_NO_REOPEN


def test_classify_support_question_support_only(repo_root):
    ctx, acc, auth, rel, rec, audit = _closed_context(repo_root)
    pol = _policy(repo_root, auth)
    issue = _issue(repo_root, pol, ISSUE_SUPPORT_QUESTION, "how do I")
    out = classify_post_delivery_issue(issue_id=issue.issue_id, classified_by_operator_id="op",
                                        repo_root=repo_root, recorded_at="2026-01-10")
    assert out.ok and out.classification.outcome == CLASS_SUPPORT_ONLY


def test_classify_expired_window_blocks_coverage(repo_root):
    ctx, acc, auth, rel, rec, audit = _closed_context(repo_root)
    pol = _policy(repo_root, auth)
    # report outside the active window (policy window 2026-01-01..2026-02-01)
    issue = _issue(repo_root, pol, ISSUE_PRODUCTION_DEFECT)
    out = classify_post_delivery_issue(issue_id=issue.issue_id, classified_by_operator_id="op",
                                        repo_root=repo_root, recorded_at="2026-03-10")
    assert out.ok and out.classification.outcome == CLASS_OUT_OF_SCOPE_CHANGE


def test_classify_integrity_defect_requires_sha(repo_root):
    ctx, acc, auth, rel, rec, audit = _closed_context(repo_root)
    pol = _policy(repo_root, auth)
    issue = record_post_delivery_issue(
        support_policy_id=pol.support_policy_id, issue_category="ARTIFACT_INTEGRITY_DEFECT",
        issue_summary="corrupt asset", recorded_by_operator_id="op", customer_reference="cust-1",
        affected_formats=("vertical",), reported_at="2026-01-10", artifact_sha256="",
        repo_root=repo_root, recorded_at="t",
    ).issue
    out = classify_post_delivery_issue(issue_id=issue.issue_id, classified_by_operator_id="op",
                                        repo_root=repo_root, recorded_at="2026-01-10")
    assert out.ok and out.classification.outcome == "BLOCKED_INVALID_LINEAGE"


# ===========================================================================
# Dispute
# ===========================================================================
def test_open_and_resolve_dispute(repo_root):
    ctx, acc, auth, rel, rec, audit = _closed_context(repo_root)
    pol = _policy(repo_root, auth)
    issue = _issue(repo_root, pol, ISSUE_DISPUTE, "dispute now")
    dis = open_post_delivery_dispute(issue_id=issue.issue_id, dispute_type="QUALITY",
                                     dispute_reason="unhappy", opened_by_operator_id="op",
                                     repo_root=repo_root, recorded_at="t")
    assert dis.ok and dis.dispute.status == DISPUTE_OPEN
    res = resolve_post_delivery_dispute(dispute_id=dis.dispute.dispute_id,
                                        resolution_status=DISPUTE_RESOLVED,
                                        resolved_by_operator_id="mgr",
                                        resolution_reason="goodwill", repo_root=repo_root, recorded_at="t")
    assert res.ok and res.dispute.status == DISPUTE_RESOLVED
    assert res.dispute.resolved_by_operator_id == "mgr"


def test_open_dispute_duplicate_idempotent(repo_root):
    ctx, acc, auth, rel, rec, audit = _closed_context(repo_root)
    pol = _policy(repo_root, auth)
    issue = _issue(repo_root, pol, ISSUE_DISPUTE, "dispute now")
    kw = dict(issue_id=issue.issue_id, dispute_type="QUALITY", dispute_reason="unhappy",
              opened_by_operator_id="op", repo_root=repo_root, recorded_at="t")
    first = open_post_delivery_dispute(**kw)
    second = open_post_delivery_dispute(**kw)
    assert second.ok and second.duplicate_of == first.dispute.dispute_id


def test_resolve_dispute_requires_operator(repo_root):
    ctx, acc, auth, rel, rec, audit = _closed_context(repo_root)
    pol = _policy(repo_root, auth)
    issue = _issue(repo_root, pol, ISSUE_DISPUTE, "dispute now")
    dis = open_post_delivery_dispute(issue_id=issue.issue_id, dispute_type="QUALITY",
                                     dispute_reason="unhappy", opened_by_operator_id="op",
                                     repo_root=repo_root, recorded_at="t")
    out = resolve_post_delivery_dispute(dispute_id=dis.dispute.dispute_id,
                                        resolution_status=DISPUTE_RESOLVED,
                                        resolved_by_operator_id="", resolution_reason="x",
                                        repo_root=repo_root, recorded_at="t")
    assert not out.ok and out.error_code == "DISPUTE_RESOLUTION_REQUIRES_OPERATOR"


def test_terminal_dispute_immutable(repo_root):
    ctx, acc, auth, rel, rec, audit = _closed_context(repo_root)
    pol = _policy(repo_root, auth)
    issue = _issue(repo_root, pol, ISSUE_DISPUTE, "dispute now")
    dis = open_post_delivery_dispute(issue_id=issue.issue_id, dispute_type="QUALITY",
                                     dispute_reason="unhappy", opened_by_operator_id="op",
                                     repo_root=repo_root, recorded_at="t")
    resolve_post_delivery_dispute(dispute_id=dis.dispute.dispute_id,
                                  resolution_status=DISPUTE_RESOLVED, resolved_by_operator_id="mgr",
                                  resolution_reason="g", repo_root=repo_root, recorded_at="t")
    again = resolve_post_delivery_dispute(dispute_id=dis.dispute.dispute_id,
                                           resolution_status=DISPUTE_REJECTED,
                                           resolved_by_operator_id="mgr2", resolution_reason="g2",
                                           repo_root=repo_root, recorded_at="t")
    assert not again.ok and again.error_code == "DISPUTE_TERMINAL"


# ===========================================================================
# Reopen
# ===========================================================================
def test_reopen_requires_approval_and_stage8b_for_8c(repo_root):
    ctx, acc, auth, rel, rec, audit = _closed_context(repo_root)
    pol = _policy(repo_root, auth)
    issue = _issue(repo_root, pol, ISSUE_CUSTOMER_REVISION_REQUEST, "new still")
    req = request_post_delivery_reopen(issue_id=issue.issue_id, target_workflow=REOPEN_TARGET_STAGE_8B,
                                       reopen_reason="follow-up", reopen_scope="asset-1",
                                       repo_root=repo_root, recorded_at="t")
    assert req.ok and req.reopen.status == "REQUESTED"
    # No Stage 8B approval exists yet for this revision -> Stage 8C route blocked.
    bad = request_post_delivery_reopen(issue_id=issue.issue_id, target_workflow=REOPEN_TARGET_STAGE_8C,
                                        reopen_reason="follow-up", reopen_scope="asset-1",
                                        repo_root=repo_root, recorded_at="t")
    assert not bad.ok and bad.error_code == "STAGE_8B_PREREQUISITES_MISSING"
    # Approval creates routing evidence only; does NOT invoke HVS.
    ap = approve_post_delivery_reopen(reopen_id=req.reopen.reopen_id, approved_by_operator_id="mgr",
                                      approval_reference="appr-1", repo_root=repo_root, recorded_at="t")
    assert ap.ok and ap.reopen.status == REOPEN_APPROVED and ap.hvs_invoked is False


def test_reopen_duplicate_idempotent(repo_root):
    ctx, acc, auth, rel, rec, audit = _closed_context(repo_root)
    pol = _policy(repo_root, auth)
    issue = _issue(repo_root, pol, ISSUE_CUSTOMER_REVISION_REQUEST, "new still")
    kw = dict(issue_id=issue.issue_id, target_workflow=REOPEN_TARGET_STAGE_8B,
              reopen_reason="follow-up", reopen_scope="asset-1", repo_root=repo_root, recorded_at="t")
    first = request_post_delivery_reopen(**kw)
    second = request_post_delivery_reopen(**kw)
    assert second.ok and second.duplicate_of == first.reopen.reopen_id


def test_reopen_invalid_target_rejected(repo_root):
    ctx, acc, auth, rel, rec, audit = _closed_context(repo_root)
    pol = _policy(repo_root, auth)
    issue = _issue(repo_root, pol, ISSUE_CUSTOMER_REVISION_REQUEST, "new still")
    out = request_post_delivery_reopen(issue_id=issue.issue_id, target_workflow="DIRECT_TO_HVS",
                                       reopen_reason="x", reopen_scope="y",
                                       repo_root=repo_root, recorded_at="t")
    assert not out.ok and out.error_code == "REOPEN_TARGET_INVALID"


# ===========================================================================
# Commercial closure
# ===========================================================================
def test_commercial_closure_clean_case_closed(repo_root):
    ctx, acc, auth, rel, rec, audit = _closed_context(repo_root)
    pol = _policy(repo_root, auth)
    # issue that is classified SUPPORT_ONLY and resolved -> no blocker
    issue = record_post_delivery_issue(
        support_policy_id=pol.support_policy_id, issue_category=ISSUE_SUPPORT_QUESTION,
        issue_summary="how to", recorded_by_operator_id="op", customer_reference="cust-1",
        affected_formats=("vertical",), reported_at="2026-01-10", repo_root=repo_root, recorded_at="t").issue
    classify_post_delivery_issue(issue_id=issue.issue_id, classified_by_operator_id="op",
                                 repo_root=repo_root, recorded_at="2026-01-10")
    # resolve the issue terminal
    from scos.control_center.hvs_post_delivery_support_service import _issues_by_id
    # Mark resolved via direct store not exposed; instead close with no conflicts.
    eval_out = evaluate_commercial_closure(authorization_id=auth.authorization_id,
                                           closure_basis="no_open_items", closed_by_operator_id="op",
                                           invoice_state_reference="inv-1", payment_state_reference="pay-1",
                                           repo_root=repo_root, recorded_at="t")
    assert eval_out.ok
    out = record_commercial_closure(authorization_id=auth.authorization_id, closure_basis="no_open_items",
                                     closed_by_operator_id="op", invoice_state_reference="inv-1",
                                     payment_state_reference="pay-1", support_policy_id=pol.support_policy_id,
                                     repo_root=repo_root, recorded_at="t")
    assert out.ok and out.closure.closure_status == COMMERCIAL_CLOSED
    assert out.closure.invoice_state_reference == "inv-1"
    assert out.closure.payment_state_reference == "pay-1"


def test_commercial_closure_unresolved_dispute_blocks(repo_root):
    ctx, acc, auth, rel, rec, audit = _closed_context(repo_root)
    pol = _policy(repo_root, auth)
    issue = _issue(repo_root, pol, ISSUE_DISPUTE, "dispute now")
    open_post_delivery_dispute(issue_id=issue.issue_id, dispute_type="QUALITY",
                               dispute_reason="unhappy", opened_by_operator_id="op",
                               repo_root=repo_root, recorded_at="t")
    out = record_commercial_closure(authorization_id=auth.authorization_id, closure_basis="x",
                                     closed_by_operator_id="op", repo_root=repo_root, recorded_at="t")
    assert not out.ok and out.error_code == "CLOSURE_BLOCKED"
    assert "UNRESOLVED_DISPUTE" in out.reasons


def test_commercial_closure_open_covered_defect_blocks(repo_root):
    ctx, acc, auth, rel, rec, audit = _closed_context(repo_root)
    pol = _policy(repo_root, auth)
    issue = _issue(repo_root, pol, ISSUE_PRODUCTION_DEFECT, "glitch")
    classify_post_delivery_issue(issue_id=issue.issue_id, classified_by_operator_id="op",
                                 repo_root=repo_root, recorded_at="2026-01-10")
    # issue left OPEN (not resolved) -> blocks
    out = record_commercial_closure(authorization_id=auth.authorization_id, closure_basis="x",
                                     closed_by_operator_id="op", repo_root=repo_root, recorded_at="t")
    assert not out.ok and "OPEN_COVERED_DEFECT" in out.reasons


def test_commercial_closure_idempotent(repo_root):
    ctx, acc, auth, rel, rec, audit = _closed_context(repo_root)
    pol = _policy(repo_root, auth)
    issue = record_post_delivery_issue(
        support_policy_id=pol.support_policy_id, issue_category=ISSUE_SUPPORT_QUESTION,
        issue_summary="how to", recorded_by_operator_id="op", customer_reference="cust-1",
        affected_formats=("vertical",), reported_at="2026-01-10", repo_root=repo_root, recorded_at="t").issue
    classify_post_delivery_issue(issue_id=issue.issue_id, classified_by_operator_id="op",
                                 repo_root=repo_root, recorded_at="2026-01-10")
    kw = dict(authorization_id=auth.authorization_id, closure_basis="no_open_items",
              closed_by_operator_id="op", support_policy_id=pol.support_policy_id,
              repo_root=repo_root, recorded_at="t")
    first = record_commercial_closure(**kw)
    second = record_commercial_closure(**kw)
    assert second.ok and second.duplicate_of == first.closure.commercial_closure_id


# ===========================================================================
# Lineage inspection + boundaries
# ===========================================================================
def test_inspect_support_lineage_deterministic(repo_root):
    ctx, acc, auth, rel, rec, audit = _closed_context(repo_root)
    pol = _policy(repo_root, auth)
    issue = _issue(repo_root, pol, ISSUE_SUPPORT_QUESTION, "how to")
    out = inspect_post_delivery_support_lineage(project_id=ctx["project_id"], repo_root=repo_root)
    assert out["project_id"] == ctx["project_id"]
    assert len(out["policies"]) == 1
    assert len(out["issues"]) == 1


def test_no_direct_hvs_invocation_in_source():
    import pathlib

    src = pathlib.Path(__file__).resolve().parent.parent
    for fname in (
        "hvs_post_delivery_support_models.py",
        "hvs_post_delivery_support_service.py",
    ):
        text = (src / fname).read_text(encoding="utf-8")
        # Match only the real HVS package; our local 'hvs_*' modules are allowed.
        for banned in ("import hvs\n", "import hvs ", "import hvs.", "from hvs ", "from hvs.", "hvs.cli"):
            assert banned not in text, f"forbidden token {banned!r} present in {fname}"


def test_no_invoice_payment_mutation_in_source():
    import pathlib

    src = pathlib.Path(__file__).resolve().parent.parent
    text = (src / "hvs_post_delivery_support_service.py").read_text(encoding="utf-8")
    for banned in ("create_invoice", "issue_refund", "mark_paid", "alter_payment", "payment_provider", "stripe", "charge"):
        assert banned not in text, f"forbidden token {banned!r} present"


def test_no_secret_fields_serialized(repo_root):
    ctx, acc, auth, rel, rec, audit = _closed_context(repo_root)
    pol = _policy(repo_root, auth)
    blob = pol.to_dict()
    for banned in ("token", "secret", "password", "api_key", "credential"):
        assert banned not in blob


# ===========================================================================
# CLI
# ===========================================================================
def _cli():
    from scos.control_center import cli

    return cli


def _point_cli_at(repo_root):
    cli = _cli()
    cli._repo_root = lambda: repo_root  # type: ignore[attr-defined]
    return cli


def test_cli_register_support_policy_exit0(repo_root):
    ctx, acc, auth, rel, rec, audit = _closed_context(repo_root)
    cli = _point_cli_at(repo_root)
    rc = cli.main([
        "register-support-policy", "--authorization-id", auth.authorization_id,
        "--support-window-start", "2026-01-01", "--support-window-end", "2026-02-01",
        "--policy-type", "STANDARD", "--included-issue-categories", "PRODUCTION_DEFECT",
        "--policy-version", "scos-hvs-support/1.0.0", "--created-by-operator-id", "op",
        "--recorded-at", "t",
    ])
    assert rc == 0


def test_cli_classify_issue_exit0_and_rejection_exit1(repo_root):
    ctx, acc, auth, rel, rec, audit = _closed_context(repo_root)
    cli = _point_cli_at(repo_root)
    pol = _policy(repo_root, auth)
    ri = cli.main([
        "record-issue", "--support-policy-id", pol.support_policy_id,
        "--issue-category", ISSUE_PRODUCTION_DEFECT, "--issue-summary", "glitch",
        "--recorded-by-operator-id", "op", "--customer-reference", "cust-1",
        "--affected-formats", "vertical", "--reported-at", "2026-01-10",
        "--artifact-sha256", "sha256:" + "a" * 64, "--recorded-at", "t",
    ])
    assert ri == 0
    # issue id is deterministic; derive via lineage inspect
    lineage = inspect_post_delivery_support_lineage(project_id=ctx["project_id"], repo_root=repo_root)
    issue_id = lineage["issues"][0]["issue_id"]
    rc = cli.main(["classify-issue", "--issue-id", issue_id,
                   "--classified-by-operator-id", "op", "--recorded-at", "2026-01-10"])
    assert rc == 0
    bad = cli.main(["classify-issue", "--issue-id", "scos-hvs-issue-missing",
                   "--classified-by-operator-id", "op", "--recorded-at", "t"])
    assert bad == 1


def test_cli_commercial_closure_exit0(repo_root):
    ctx, acc, auth, rel, rec, audit = _closed_context(repo_root)
    cli = _point_cli_at(repo_root)
    pol = _policy(repo_root, auth)
    issue = record_post_delivery_issue(
        support_policy_id=pol.support_policy_id, issue_category=ISSUE_SUPPORT_QUESTION,
        issue_summary="how to", recorded_by_operator_id="op", customer_reference="cust-1",
        affected_formats=("vertical",), reported_at="2026-01-10", repo_root=repo_root, recorded_at="t").issue
    classify_post_delivery_issue(issue_id=issue.issue_id, classified_by_operator_id="op",
                                 repo_root=repo_root, recorded_at="2026-01-10")
    rc = cli.main([
        "create-commercial-closure", "--authorization-id", auth.authorization_id,
        "--closure-basis", "no_open_items", "--closed-by-operator-id", "op",
        "--invoice-state-reference", "inv-1", "--payment-state-reference", "pay-1",
        "--support-policy-id", pol.support_policy_id, "--recorded-at", "t",
    ])
    assert rc == 0


def test_cli_malformed_usage_exit2(repo_root):
    cli = _point_cli_at(repo_root)
    rc = cli.main(["register-support-policy", "--policy-type", "STANDARD"])
    assert rc == 2
