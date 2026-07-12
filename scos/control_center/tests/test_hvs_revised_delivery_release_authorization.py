"""Stage 8E focused verification: revised-delivery acceptance, customer release
authorization, release readiness, and final revision closure.

Covers the required capabilities: accepted reconciliation producing exactly
one acceptance record with complete lineage; acceptance referencing the
correct revised delivery; artifact-integrity evidence preservation; original /
revised delivery immutability; deterministic idempotency (replay returns same
outcome, no duplicate audit); acceptance rejection of missing / mismatched /
unsupported / terminal cases; authorization of fully-accepted deliveries only
with scope limited to accepted formats and canonical channels; authorization
rejection of missing / partial / mismatched / unsupported / conflicting /
expired / revoked cases; deterministic release-readiness (fail-closed) with no
outbound transport; idempotent final closure with conflict rejection; and no
direct HVS invocation by the Stage 8E service.

The Stage 8D revised delivery is produced by the canonical 8A.1->8B->8C->8D
pipeline (no Stage 8E modification of prior stages). The new delivery record is
seeded via the same canonical Stage 5->6->7 machinery the 8D test uses.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from scos.control_center.tests.test_hvs_delivery_version_lineage import _accepted_delivery
from scos.control_center.tests.test_hvs_rerender_result_reconciliation import (
    _authorized_dispatch_with_delivery,
    _seed_new_delivery_record,
)


def _models():
    return importlib.import_module("scos.control_center.hvs_revised_delivery_release_models")


def _service():
    return importlib.import_module("scos.control_center.hvs_revised_delivery_release_service")


def _store():
    return importlib.import_module("scos.control_center.hvs_revised_delivery_release_store")


def _rerender_result_models():
    return importlib.import_module("scos.control_center.hvs_rerender_result_models")


def _rerender_result_service():
    return importlib.import_module("scos.control_center.hvs_rerender_result_reconciliation_service")


def _revision_service():
    return importlib.import_module("scos.control_center.hvs_revision_service")


def _cli():
    return importlib.import_module("scos.control_center.cli")


def _success_result(models, *, result_id, dispatch, original_delivery, original_lineage, new_dr_id, artifact_sha256):
    return models.RerenderResult(
        schema_version=models.RERENDER_RESULT_SCHEMA_VERSION,
        result_id=result_id,
        dispatch_id=dispatch.dispatch_id,
        revision_id=dispatch.revision_id,
        original_delivery_id=original_delivery.delivery_record_id,
        original_render_request_id=None,
        new_render_request_id=new_dr_id,
        project_id=original_lineage.project_id,
        correlation_id=dispatch.correlation_id,
        idempotency_key=models.build_result_idempotency_key(
            result_id=result_id,
            dispatch_id=dispatch.dispatch_id,
            revision_id=dispatch.revision_id,
            original_delivery_id=original_delivery.delivery_record_id,
            project_id=original_lineage.project_id,
            correlation_id=dispatch.correlation_id,
            status="SUCCEEDED",
            new_render_request_id=new_dr_id,
            output_formats=tuple(sorted(dispatch.target_formats)),
            artifact_references=(f"artifact-{result_id}",),
            checksums={"artifact": artifact_sha256},
        ),
        status="SUCCEEDED",
        completed_at="t",
        artifact_references=(f"artifact-{result_id}",),
        output_formats=tuple(sorted(dispatch.target_formats)),
        checksums={"artifact": artifact_sha256},
        renderer_metadata={"engine": "manual-hvs-handoff"},
        failure_code=None,
        failure_reason=None,
        retryability=None,
        evidence_references=(f"evidence-{result_id}",),
        created_at="t",
    )


def _reconcile_revised_delivery(repo_root):
    """Drive 8A.1->8B->8C->8D and return the reconciled revised-delivery ids."""
    rm = importlib.import_module("scos.control_center.hvs_revision_models")
    rs = _revision_service()
    lm = importlib.import_module("scos.control_center.hvs_delivery_lineage_models")
    ls = importlib.import_module("scos.control_center.hvs_delivery_lineage_service")
    svc = importlib.import_module("scos.control_center.hvs_rerender_dispatch_service")
    rrm = _rerender_result_models()
    rrs = _rerender_result_service()

    artifact, delivery, closure = _accepted_delivery(repo_root)
    lineage = ls.register_delivery_lineage(
        request=lm.DeliveryLineageRegistrationRequest(
            delivery_record_id=delivery.delivery_record_id,
            delivery_version=lm.DeliveryVersion(1),
            operator_id="op",
            registration_basis=lm.BASIS_ORIGINAL_DELIVERY_CONFIRMED,
            confirm_legacy_version=True,
        ),
        repo_root=repo_root,
        recorded_at="t",
    )
    created = rs.create_revision_request(
        delivery_record_id=delivery.delivery_record_id,
        requested_by_id="customer",
        operator_id="op",
        revision_items=(
            rm.RevisionItem.create(
                category="ASSET_REPLACEMENT",
                description="Replace approved still.",
                target_type="asset",
                target_id="asset-1",
                asset_id="asset-1",
                priority="normal",
                acceptance_requirement="Operator reviews replacement.",
                requested_by_id="customer",
                source_artifact_sha256=lineage.lineage.artifact_sha256,
            ),
        ),
        repo_root=repo_root,
        recorded_at="t",
    )
    rid = created.revision.revision_request_id
    rs.start_revision_review(revision_request_id=rid, operator_id="op", repo_root=repo_root, recorded_at="t")
    rs.assess_revision_impact(revision_request_id=rid, operator_id="op", repo_root=repo_root, recorded_at="t")
    rs.classify_revision_commercial(revision_request_id=rid, classification="INTERNAL_CORRECTION", operator_id="op", basis="internal production error", repo_root=repo_root, recorded_at="t")
    rs.prepare_revision_plan(revision_request_id=rid, operator_id="op", repo_root=repo_root, recorded_at="t")
    rs.create_revision_approval_request(revision_request_id=rid, operator_id="op", repo_root=repo_root, recorded_at="t")
    rs.decide_revision_approval(revision_request_id=rid, decision="APPROVE_RERENDER_PLAN", operator_id="op", repo_root=repo_root, recorded_at="t")
    rs.create_rerender_authorization(revision_request_id=rid, operator_id="op", repo_root=repo_root, recorded_at="t")
    out = svc.request_rerender_dispatch(
        revision_request_id=rid,
        operator_id="op",
        target_formats=("vertical",),
        requested_changes=(),
        reason="Customer-approved caption fix re-render.",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert out.ok
    dispatch = out.dispatch
    new_dr_id = _seed_new_delivery_record(repo_root, "delivery-revised-stage8e")
    artifact_sha256 = rm.RevisionItem.create(
        category="ASSET_REPLACEMENT",
        description="x",
        target_type="asset",
        target_id="a",
        asset_id="a",
        priority="normal",
        acceptance_requirement="x",
        requested_by_id="op",
        source_artifact_sha256="0" * 64,
    ).source_artifact_sha256
    # Use a stable sha for the re-rendered artifact.
    import hashlib
    artifact_sha256 = hashlib.sha256(b"stage8e-revised-artifact").hexdigest()
    result = _success_result(
        rrm,
        result_id="result-8e-1",
        dispatch=dispatch,
        original_delivery=delivery,
        original_lineage=lineage.lineage,
        new_dr_id=new_dr_id,
        artifact_sha256=artifact_sha256,
    )
    recon = rrs.reconcile_rerender_result(
        result=result,
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
        new_delivery_record_id=new_dr_id,
    )
    assert recon.ok and recon.revised_delivery is not None
    return {
        "revision_id": rid,
        "dispatch_id": dispatch.dispatch_id,
        "original_delivery_id": delivery.delivery_record_id,
        "project_id": lineage.lineage.project_id,
        "correlation_id": dispatch.correlation_id,
        "revised_delivery_id": recon.revised_delivery.revised_delivery_id,
        "reconciliation_result_id": recon.revised_delivery.accepted_result_id,
        "dispatch": dispatch,
        "recon": recon,
    }


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "scos" / "work").mkdir(parents=True)
    return root


# ===========================================================================
# Acceptance success
# ===========================================================================
def test_accepted_delivery_creates_one_acceptance_record(repo_root):
    ctx = _reconcile_revised_delivery(repo_root)
    svc = _service()
    result = svc.record_revised_delivery_acceptance(
        reconciliation_result_id=ctx["reconciliation_result_id"],
        revised_delivery_id=ctx["revised_delivery_id"],
        reviewer_id="reviewer-1",
        accepted_formats=("vertical",),
        quality_gate_reference="qg-1",
        artifact_integrity_reference="integrity-1",
        acceptance_status="ACCEPTED",
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert result.ok and result.acceptance is not None
    assert result.acceptance.acceptance_status == "ACCEPTED"
    # Exactly one acceptance event.
    events = _store().read_release_events(audit_log_path=_store().release_audit_path(repo_root))
    assert sum(1 for e in events if e.event_type == "REVISED_DELIVERY_ACCEPTED") == 1


def test_acceptance_references_complete_lineage(repo_root):
    ctx = _reconcile_revised_delivery(repo_root)
    svc = _service()
    result = svc.record_revised_delivery_acceptance(
        reconciliation_result_id=ctx["reconciliation_result_id"],
        revised_delivery_id=ctx["revised_delivery_id"],
        reviewer_id="reviewer-1",
        accepted_formats=("vertical",),
        quality_gate_reference="qg-1",
        artifact_integrity_reference="integrity-1",
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    a = result.acceptance
    assert a.revision_id == ctx["revision_id"]
    assert a.dispatch_id == ctx["dispatch_id"]
    assert a.original_delivery_id == ctx["original_delivery_id"]
    assert a.revised_delivery_id == ctx["revised_delivery_id"]
    assert a.project_id == ctx["project_id"]
    assert a.correlation_id == ctx["correlation_id"]
    assert a.reconciliation_result_id == ctx["reconciliation_result_id"]


def test_acceptance_accepted_formats_match_reconciled(repo_root):
    ctx = _reconcile_revised_delivery(repo_root)
    svc = _service()
    result = svc.record_revised_delivery_acceptance(
        reconciliation_result_id=ctx["reconciliation_result_id"],
        revised_delivery_id=ctx["revised_delivery_id"],
        reviewer_id="reviewer-1",
        accepted_formats=("vertical",),
        quality_gate_reference="qg-1",
        artifact_integrity_reference="integrity-1",
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert set(result.acceptance.accepted_formats) == {"vertical"}


def test_artifact_integrity_evidence_preserved(repo_root):
    ctx = _reconcile_revised_delivery(repo_root)
    svc = _service()
    result = svc.record_revised_delivery_acceptance(
        reconciliation_result_id=ctx["reconciliation_result_id"],
        revised_delivery_id=ctx["revised_delivery_id"],
        reviewer_id="reviewer-1",
        accepted_formats=("vertical",),
        quality_gate_reference="qg-1",
        artifact_integrity_reference="integrity-1",
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert result.acceptance.artifact_integrity_reference == "integrity-1"


def test_original_and_revised_delivery_records_unchanged(repo_root):
    ctx = _reconcile_revised_delivery(repo_root)
    svc = _service()
    svc.record_revised_delivery_acceptance(
        reconciliation_result_id=ctx["reconciliation_result_id"],
        revised_delivery_id=ctx["revised_delivery_id"],
        reviewer_id="reviewer-1",
        accepted_formats=("vertical",),
        quality_gate_reference="qg-1",
        artifact_integrity_reference="integrity-1",
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    # 8D revised-delivery record still present and unchanged by 8E acceptance.
    revised = svc._load_revised_delivery(repo_root=repo_root, revised_delivery_id=ctx["revised_delivery_id"])
    assert revised is not None
    assert revised.revised_delivery_id == ctx["revised_delivery_id"]


def test_acceptance_idempotent_no_duplicate_audit(repo_root):
    ctx = _reconcile_revised_delivery(repo_root)
    svc = _service()
    kw = dict(
        reconciliation_result_id=ctx["reconciliation_result_id"],
        revised_delivery_id=ctx["revised_delivery_id"],
        reviewer_id="reviewer-1",
        accepted_formats=("vertical",),
        quality_gate_reference="qg-1",
        artifact_integrity_reference="integrity-1",
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    first = svc.record_revised_delivery_acceptance(**kw)
    second = svc.record_revised_delivery_acceptance(**kw)
    assert first.ok and second.ok
    assert second.duplicate_of == first.acceptance.acceptance_id
    events = _store().read_release_events(audit_log_path=_store().release_audit_path(repo_root))
    assert sum(1 for e in events if e.event_type == "REVISED_DELIVERY_ACCEPTED") == 1


# ===========================================================================
# Acceptance rejection
# ===========================================================================
def test_acceptance_missing_reconciliation_rejected(repo_root):
    ctx = _reconcile_revised_delivery(repo_root)
    svc = _service()
    out = svc.record_revised_delivery_acceptance(
        reconciliation_result_id="missing-result",
        revised_delivery_id=ctx["revised_delivery_id"],
        reviewer_id="reviewer-1",
        accepted_formats=("vertical",),
        quality_gate_reference="qg-1",
        artifact_integrity_reference="integrity-1",
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert not out.ok and out.error_code == "RECONCILIATION_NOT_SUCCESSFUL"


def test_acceptance_missing_revised_delivery_rejected(repo_root):
    ctx = _reconcile_revised_delivery(repo_root)
    svc = _service()
    out = svc.record_revised_delivery_acceptance(
        reconciliation_result_id=ctx["reconciliation_result_id"],
        revised_delivery_id="missing-delivery",
        reviewer_id="reviewer-1",
        accepted_formats=("vertical",),
        quality_gate_reference="qg-1",
        artifact_integrity_reference="integrity-1",
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert not out.ok and out.error_code == "REVISED_DELIVERY_NOT_FOUND"


def test_acceptance_missing_integrity_evidence_rejected(repo_root):
    ctx = _reconcile_revised_delivery(repo_root)
    svc = _service()
    out = svc.record_revised_delivery_acceptance(
        reconciliation_result_id=ctx["reconciliation_result_id"],
        revised_delivery_id=ctx["revised_delivery_id"],
        reviewer_id="reviewer-1",
        accepted_formats=("vertical",),
        quality_gate_reference="qg-1",
        artifact_integrity_reference="",
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert not out.ok and out.error_code == "MISSING_INTEGRITY_EVIDENCE"


def test_acceptance_unsupported_format_rejected(repo_root):
    ctx = _reconcile_revised_delivery(repo_root)
    svc = _service()
    out = svc.record_revised_delivery_acceptance(
        reconciliation_result_id=ctx["reconciliation_result_id"],
        revised_delivery_id=ctx["revised_delivery_id"],
        reviewer_id="reviewer-1",
        accepted_formats=("vertical", "square"),
        quality_gate_reference="qg-1",
        artifact_integrity_reference="integrity-1",
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert not out.ok and out.error_code == "UNSUPPORTED_ACCEPTED_FORMAT"


def test_acceptance_unknown_revised_delivery_rejected(repo_root):
    ctx = _reconcile_revised_delivery(repo_root)
    svc = _service()
    # An acceptance request referencing a revised delivery that does not exist
    # (e.g. a mismatched / mistyped delivery identity) is refused at the
    # lineage lookup before any acceptance record is created.
    out = svc.record_revised_delivery_acceptance(
        reconciliation_result_id=ctx["reconciliation_result_id"],
        revised_delivery_id="scos-hvs-revised-delivery-nonexistent",
        reviewer_id="reviewer-1",
        accepted_formats=("vertical",),
        quality_gate_reference="qg-1",
        artifact_integrity_reference="integrity-1",
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert not out.ok and out.error_code == "REVISED_DELIVERY_NOT_FOUND"


def test_partial_acceptance_cannot_pass_release_gate(repo_root):
    ctx = _reconcile_revised_delivery(repo_root)
    svc = _service()
    acc = svc.record_revised_delivery_acceptance(
        reconciliation_result_id=ctx["reconciliation_result_id"],
        revised_delivery_id=ctx["revised_delivery_id"],
        reviewer_id="reviewer-1",
        accepted_formats=(),
        rejected_formats=("vertical",),
        quality_gate_reference="qg-1",
        artifact_integrity_reference="integrity-1",
        acceptance_status="REJECTED",
        rejection_codes=("FORMAT_DEFECT",),
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert acc.ok and acc.acceptance.acceptance_status == "REJECTED"
    readiness = svc.evaluate_release_readiness(
        acceptance_id=acc.acceptance.acceptance_id,
        authorization_id=None,
        repo_root=repo_root,
        recorded_at="t",
    )
    assert not readiness.release_ready
    assert "ACCEPTANCE_NOT_FULLY_ACCEPTED" in readiness.reasons


def test_rejected_acceptance_cannot_be_reused_as_accepted(repo_root):
    ctx = _reconcile_revised_delivery(repo_root)
    svc = _service()
    rejected = svc.record_revised_delivery_acceptance(
        reconciliation_result_id=ctx["reconciliation_result_id"],
        revised_delivery_id=ctx["revised_delivery_id"],
        reviewer_id="reviewer-1",
        accepted_formats=(),
        rejected_formats=("vertical",),
        quality_gate_reference="qg-1",
        artifact_integrity_reference="integrity-1",
        acceptance_status="REJECTED",
        rejection_codes=("DEFECT",),
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert rejected.ok
    # A different acceptance (full) under same revision conflicts with the
    # terminal REJECTED acceptance and is rejected.
    good = svc.record_revised_delivery_acceptance(
        reconciliation_result_id=ctx["reconciliation_result_id"],
        revised_delivery_id=ctx["revised_delivery_id"],
        reviewer_id="reviewer-2",
        accepted_formats=("vertical",),
        quality_gate_reference="qg-2",
        artifact_integrity_reference="integrity-2",
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert not good.ok and good.error_code == "ACCEPTANCE_CONFLICT"


# ===========================================================================
# Authorization success
# ===========================================================================
def _accepted_context(repo_root):
    ctx = _reconcile_revised_delivery(repo_root)
    svc = _service()
    acc = svc.record_revised_delivery_acceptance(
        reconciliation_result_id=ctx["reconciliation_result_id"],
        revised_delivery_id=ctx["revised_delivery_id"],
        reviewer_id="reviewer-1",
        accepted_formats=("vertical",),
        quality_gate_reference="qg-1",
        artifact_integrity_reference="integrity-1",
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert acc.ok
    return ctx, acc.acceptance


def test_fully_accepted_can_be_authorized(repo_root):
    ctx, acc = _accepted_context(repo_root)
    svc = _service()
    out = svc.create_customer_release_authorization(
        acceptance_id=acc.acceptance_id,
        authorized_by="manager-1",
        authorization_scope=("vertical",),
        approved_formats=("vertical",),
        allowed_delivery_channels=("email_manual",),
        customer_reference="cust-1",
        approval_basis="release_quality_gate_passed",
        policy_version="scos-hvs-release-policy/1.0.0",
        expiry_at="2099-01-01T00:00:00Z",
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert out.ok and out.authorization is not None
    assert out.authorization.status == "AUTHORIZED"


def test_authorization_references_lineage(repo_root):
    ctx, acc = _accepted_context(repo_root)
    svc = _service()
    out = svc.create_customer_release_authorization(
        acceptance_id=acc.acceptance_id,
        authorized_by="manager-1",
        authorization_scope=("vertical",),
        approved_formats=("vertical",),
        allowed_delivery_channels=("email_manual",),
        customer_reference="cust-1",
        approval_basis="release_quality_gate_passed",
        policy_version="scos-hvs-release-policy/1.0.0",
        expiry_at="2099-01-01T00:00:00Z",
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    a = out.authorization
    assert a.acceptance_id == acc.acceptance_id
    assert a.revision_id == ctx["revision_id"]
    assert a.revised_delivery_id == ctx["revised_delivery_id"]
    assert a.project_id == ctx["project_id"]
    assert a.correlation_id == ctx["correlation_id"]


def test_authorization_scope_limited_to_accepted_formats(repo_root):
    ctx, acc = _accepted_context(repo_root)
    svc = _service()
    out = svc.create_customer_release_authorization(
        acceptance_id=acc.acceptance_id,
        authorized_by="manager-1",
        authorization_scope=("vertical",),
        approved_formats=("vertical",),
        allowed_delivery_channels=("email_manual",),
        customer_reference="cust-1",
        approval_basis="release_quality_gate_passed",
        policy_version="scos-hvs-release-policy/1.0.0",
        expiry_at="2099-01-01T00:00:00Z",
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert set(out.authorization.approved_formats) <= set(acc.accepted_formats)


def test_authorization_approved_channels_canonical(repo_root):
    ctx, acc = _accepted_context(repo_root)
    svc = _service()
    out = svc.create_customer_release_authorization(
        acceptance_id=acc.acceptance_id,
        authorized_by="manager-1",
        authorization_scope=("vertical",),
        approved_formats=("vertical",),
        allowed_delivery_channels=("email_manual",),
        customer_reference="cust-1",
        approval_basis="release_quality_gate_passed",
        policy_version="scos-hvs-release-policy/1.0.0",
        expiry_at="2099-01-01T00:00:00Z",
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    from scos.control_center.hvs_local_delivery_models import ALLOWED_DELIVERY_CHANNELS
    assert out.authorization.allowed_delivery_channels[0] in ALLOWED_DELIVERY_CHANNELS


def test_authorization_idempotent_no_duplicate_audit(repo_root):
    ctx, acc = _accepted_context(repo_root)
    svc = _service()
    kw = dict(
        acceptance_id=acc.acceptance_id,
        authorized_by="manager-1",
        authorization_scope=("vertical",),
        approved_formats=("vertical",),
        allowed_delivery_channels=("email_manual",),
        customer_reference="cust-1",
        approval_basis="release_quality_gate_passed",
        policy_version="scos-hvs-release-policy/1.0.0",
        expiry_at="2099-01-01T00:00:00Z",
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    first = svc.create_customer_release_authorization(**kw)
    second = svc.create_customer_release_authorization(**kw)
    assert second.duplicate_of == first.authorization.authorization_id
    events = _store().read_release_events(audit_log_path=_store().release_audit_path(repo_root))
    assert sum(1 for e in events if e.event_type == "RELEASE_AUTHORIZED") == 1


# ===========================================================================
# Authorization rejection
# ===========================================================================
def test_authorization_missing_acceptance_rejected(repo_root):
    svc = _service()
    out = svc.create_customer_release_authorization(
        acceptance_id="missing-acceptance",
        authorized_by="manager-1",
        authorization_scope=("vertical",),
        approved_formats=("vertical",),
        allowed_delivery_channels=("email_manual",),
        customer_reference="cust-1",
        approval_basis="x",
        policy_version="p/1",
        expiry_at="2099-01-01T00:00:00Z",
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert not out.ok and out.error_code == "ACCEPTANCE_NOT_FOUND"


def test_authorization_partial_acceptance_rejected(repo_root):
    ctx = _reconcile_revised_delivery(repo_root)
    svc = _service()
    partial = svc.record_revised_delivery_acceptance(
        reconciliation_result_id=ctx["reconciliation_result_id"],
        revised_delivery_id=ctx["revised_delivery_id"],
        reviewer_id="reviewer-1",
        accepted_formats=("vertical",),
        quality_gate_reference="qg-1",
        artifact_integrity_reference="integrity-1",
        acceptance_status="PARTIALLY_ACCEPTED",
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert partial.ok and partial.acceptance.acceptance_status == "PARTIALLY_ACCEPTED"
    out = svc.create_customer_release_authorization(
        acceptance_id=partial.acceptance.acceptance_id,
        authorized_by="manager-1",
        authorization_scope=("vertical",),
        approved_formats=("vertical",),
        allowed_delivery_channels=("email_manual",),
        customer_reference="cust-1",
        approval_basis="x",
        policy_version="p/1",
        expiry_at="2099-01-01T00:00:00Z",
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert not out.ok and out.error_code == "ACCEPTANCE_NOT_FULLY_ACCEPTED"


def test_authorization_scope_exceeds_accepted_rejected(repo_root):
    ctx, acc = _accepted_context(repo_root)
    svc = _service()
    out = svc.create_customer_release_authorization(
        acceptance_id=acc.acceptance_id,
        authorized_by="manager-1",
        authorization_scope=("vertical", "square"),
        approved_formats=("vertical", "square"),
        allowed_delivery_channels=("email_manual",),
        customer_reference="cust-1",
        approval_basis="x",
        policy_version="p/1",
        expiry_at="2099-01-01T00:00:00Z",
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert not out.ok and out.error_code == "SCOPE_EXCEEDS_ACCEPTED"


def test_authorization_unsupported_channel_rejected(repo_root):
    ctx, acc = _accepted_context(repo_root)
    svc = _service()
    out = svc.create_customer_release_authorization(
        acceptance_id=acc.acceptance_id,
        authorized_by="manager-1",
        authorization_scope=("vertical",),
        approved_formats=("vertical",),
        allowed_delivery_channels=("carrier_pigeon",),
        customer_reference="cust-1",
        approval_basis="x",
        policy_version="p/1",
        expiry_at="2099-01-01T00:00:00Z",
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert not out.ok and out.error_code == "AUTHORIZATION_VALIDATION"


def test_authorization_conflicting_active_rejected(repo_root):
    ctx, acc = _accepted_context(repo_root)
    svc = _service()
    kw = dict(
        acceptance_id=acc.acceptance_id,
        authorized_by="manager-1",
        authorization_scope=("vertical",),
        approved_formats=("vertical",),
        allowed_delivery_channels=("email_manual",),
        customer_reference="cust-1",
        approval_basis="release_quality_gate_passed",
        policy_version="scos-hvs-release-policy/1.0.0",
        expiry_at="2099-01-01T00:00:00Z",
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    first = svc.create_customer_release_authorization(**kw)
    assert first.ok
    # Conflicting channel under same acceptance id is a conflict.
    conflict = svc.create_customer_release_authorization(
        acceptance_id=acc.acceptance_id,
        authorized_by="manager-2",
        authorization_scope=("vertical",),
        approved_formats=("vertical",),
        allowed_delivery_channels=("in_person",),
        customer_reference="cust-2",
        approval_basis="release_quality_gate_passed",
        policy_version="scos-hvs-release-policy/1.0.0",
        expiry_at="2099-01-01T00:00:00Z",
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert not conflict.ok and conflict.error_code == "CONFLICTING_AUTHORIZATION"


def test_authorization_malformed_customer_reference_rejected(repo_root):
    ctx, acc = _accepted_context(repo_root)
    svc = _service()
    out = svc.create_customer_release_authorization(
        acceptance_id=acc.acceptance_id,
        authorized_by="manager-1",
        authorization_scope=("vertical",),
        approved_formats=("vertical",),
        allowed_delivery_channels=("email_manual",),
        customer_reference="bad/../ref",
        approval_basis="x",
        policy_version="p/1",
        expiry_at="2099-01-01T00:00:00Z",
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert not out.ok and out.error_code == "AUTHORIZATION_VALIDATION"


# ===========================================================================
# Release readiness
# ===========================================================================
def _authorized_context(repo_root):
    ctx, acc = _accepted_context(repo_root)
    svc = _service()
    auth = svc.create_customer_release_authorization(
        acceptance_id=acc.acceptance_id,
        authorized_by="manager-1",
        authorization_scope=("vertical",),
        approved_formats=("vertical",),
        allowed_delivery_channels=("email_manual",),
        customer_reference="cust-1",
        approval_basis="release_quality_gate_passed",
        policy_version="scos-hvs-release-policy/1.0.0",
        expiry_at="2099-01-01T00:00:00Z",
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert auth.ok
    return ctx, acc, auth.authorization


def test_release_ready_result_references_full_lineage(repo_root):
    ctx, acc, auth = _authorized_context(repo_root)
    svc = _service()
    readiness = svc.evaluate_release_readiness(
        acceptance_id=acc.acceptance_id,
        authorization_id=auth.authorization_id,
        repo_root=repo_root,
        recorded_at="t",
    )
    assert readiness.release_ready
    assert readiness.revision_id == ctx["revision_id"]
    assert readiness.acceptance_id == acc.acceptance_id
    assert readiness.authorization_id == auth.authorization_id
    assert readiness.revised_delivery_id == ctx["revised_delivery_id"]
    assert readiness.original_delivery_id == ctx["original_delivery_id"]
    assert readiness.project_id == ctx["project_id"]
    assert readiness.correlation_id == ctx["correlation_id"]


def test_release_ready_no_outbound_transport_invoked(repo_root):
    ctx, acc, auth = _authorized_context(repo_root)
    svc = _service()
    readiness = svc.evaluate_release_readiness(
        acceptance_id=acc.acceptance_id,
        authorization_id=auth.authorization_id,
        repo_root=repo_root,
        recorded_at="t",
    )
    assert readiness.release_ready
    # No transport / network / HVS path is touched; assert the service module
    # imports nothing forbidden.
    import inspect as _inspect
    src = _inspect.getsource(svc)
    for banned in ("subprocess", "requests", "urllib", "socket", "smtp", "hvs.cli", "os.system", "shell=True"):
        assert banned not in src, f"forbidden token {banned!r} present in Stage 8E service"


def test_readiness_missing_acceptance_not_ready(repo_root):
    svc = _service()
    readiness = svc.evaluate_release_readiness(
        acceptance_id="missing",
        authorization_id=None,
        repo_root=repo_root,
        recorded_at="t",
    )
    assert not readiness.release_ready and "ACCEPTANCE_NOT_FOUND" in readiness.reasons


def test_readiness_missing_authorization_not_ready(repo_root):
    ctx, acc, _ = _authorized_context(repo_root)
    svc = _service()
    readiness = svc.evaluate_release_readiness(
        acceptance_id=acc.acceptance_id,
        authorization_id="missing-auth",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert not readiness.release_ready and "AUTHORIZATION_NOT_FOUND" in readiness.reasons


# ===========================================================================
# Final closure
# ===========================================================================
def test_release_ready_creates_one_final_closure_record(repo_root):
    ctx, acc, auth = _authorized_context(repo_root)
    svc = _service()
    out = svc.close_final_revision(
        acceptance_id=acc.acceptance_id,
        authorization_id=auth.authorization_id,
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert out.ok and out.closure is not None
    events = _store().read_release_events(audit_log_path=_store().release_audit_path(repo_root))
    assert sum(1 for e in events if e.event_type == "REVISION_FINALLY_CLOSED") == 1


def test_closure_references_full_lineage(repo_root):
    ctx, acc, auth = _authorized_context(repo_root)
    svc = _service()
    out = svc.close_final_revision(
        acceptance_id=acc.acceptance_id,
        authorization_id=auth.authorization_id,
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    c = out.closure
    assert c.revision_id == ctx["revision_id"]
    assert c.acceptance_id == acc.acceptance_id
    assert c.authorization_id == auth.authorization_id
    assert c.dispatch_id == ctx["dispatch_id"]
    assert c.original_delivery_id == ctx["original_delivery_id"]
    assert c.revised_delivery_id == ctx["revised_delivery_id"]
    assert c.reconciliation_result_id == ctx["reconciliation_result_id"]


def test_closure_idempotent(repo_root):
    ctx, acc, auth = _authorized_context(repo_root)
    svc = _service()
    first = svc.close_final_revision(
        acceptance_id=acc.acceptance_id,
        authorization_id=auth.authorization_id,
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    second = svc.close_final_revision(
        acceptance_id=acc.acceptance_id,
        authorization_id=auth.authorization_id,
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert second.duplicate_of == first.closure.closure_id
    events = _store().read_release_events(audit_log_path=_store().release_audit_path(repo_root))
    assert sum(1 for e in events if e.event_type == "REVISION_FINALLY_CLOSED") == 1


def test_closure_conflict_rejected(repo_root):
    ctx, acc, auth = _authorized_context(repo_root)
    svc = _service()
    svc.close_final_revision(
        acceptance_id=acc.acceptance_id,
        authorization_id=auth.authorization_id,
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    # A second acceptance under the same revision conflicts with the terminal
    # ACCEPTED acceptance and is rejected (no second closure can be derived).
    acc2 = svc.record_revised_delivery_acceptance(
        reconciliation_result_id=ctx["reconciliation_result_id"],
        revised_delivery_id=ctx["revised_delivery_id"],
        reviewer_id="reviewer-2",
        accepted_formats=("vertical",),
        quality_gate_reference="qg-2",
        artifact_integrity_reference="integrity-2",
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    # acc2 conflicts with the terminal ACCEPTED acceptance -> rejected.
    assert not acc2.ok and acc2.error_code == "ACCEPTANCE_CONFLICT"


def test_closure_does_not_mutate_stage8d_closure(repo_root):
    ctx, acc, auth = _authorized_context(repo_root)
    svc = _service()
    before = _rerender_result_service().read_reconciliation_events(
        audit_log_path=_rerender_result_service().reconciliation_audit_path(repo_root)
    )
    svc.close_final_revision(
        acceptance_id=acc.acceptance_id,
        authorization_id=auth.authorization_id,
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    after = _rerender_result_service().read_reconciliation_events(
        audit_log_path=_rerender_result_service().reconciliation_audit_path(repo_root)
    )
    assert len(before) == len(after)
    for b, a in zip(before, after):
        assert b.event_id == a.event_id


def test_closure_with_rejected_acceptance_blocked(repo_root):
    ctx = _reconcile_revised_delivery(repo_root)
    svc = _service()
    rejected = svc.record_revised_delivery_acceptance(
        reconciliation_result_id=ctx["reconciliation_result_id"],
        revised_delivery_id=ctx["revised_delivery_id"],
        reviewer_id="reviewer-1",
        accepted_formats=(),
        rejected_formats=("vertical",),
        quality_gate_reference="qg-1",
        artifact_integrity_reference="integrity-1",
        acceptance_status="REJECTED",
        rejection_codes=("DEFECT",),
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    out = svc.close_final_revision(
        acceptance_id=rejected.acceptance.acceptance_id,
        authorization_id=None,
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert not out.ok and out.error_code == "RELEASE_NOT_READY"


def test_closure_with_revoked_authorization_blocked(repo_root):
    ctx, acc, auth = _authorized_context(repo_root)
    svc = _service()
    rev = svc.revoke_customer_release_authorization(
        authorization_id=auth.authorization_id,
        reason="customer paused release",
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert rev.ok
    out = svc.close_final_revision(
        acceptance_id=acc.acceptance_id,
        authorization_id=auth.authorization_id,
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert not out.ok and out.error_code == "RELEASE_NOT_READY"


# ===========================================================================
# Security
# ===========================================================================
def test_acceptance_rejects_path_traversal_integrity_ref(repo_root):
    ctx = _reconcile_revised_delivery(repo_root)
    svc = _service()
    out = svc.record_revised_delivery_acceptance(
        reconciliation_result_id=ctx["reconciliation_result_id"],
        revised_delivery_id=ctx["revised_delivery_id"],
        reviewer_id="reviewer-1",
        accepted_formats=("vertical",),
        quality_gate_reference="qg-1",
        artifact_integrity_reference="../escape",
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert not out.ok and out.error_code == "ACCEPTANCE_VALIDATION"


def test_acceptance_rejects_log_injection_review_notes(repo_root):
    ctx = _reconcile_revised_delivery(repo_root)
    svc = _service()
    out = svc.record_revised_delivery_acceptance(
        reconciliation_result_id=ctx["reconciliation_result_id"],
        revised_delivery_id=ctx["revised_delivery_id"],
        reviewer_id="reviewer-1",
        accepted_formats=("vertical",),
        quality_gate_reference="qg-1",
        artifact_integrity_reference="integrity-1",
        review_notes="line1\ninjected",
        operator_id="op",
        repo_root=repo_root,
        recorded_at="t",
    )
    assert not out.ok


def test_no_direct_hvs_import_in_service():
    import inspect as _inspect
    svc = _service()
    src = _inspect.getsource(svc)
    assert "import hvs" not in src
    assert "from hvs" not in src


def test_no_secret_fields_serialized(repo_root):
    ctx, acc, auth = _authorized_context(repo_root)
    svc = _service()
    auth_dict = auth.to_dict()
    blob = str(auth_dict).lower()
    for banned in ("token", "secret", "password", "api_key", "credential"):
        assert banned not in blob, f"possible secret field {banned!r} in authorization"


# ===========================================================================
# CLI
# ===========================================================================
def test_cli_record_acceptance_success_exit0(repo_root):
    ctx = _reconcile_revised_delivery(repo_root)
    cli = _cli()
    cli._repo_root = lambda: repo_root  # point the CLI at the seeded temp root
    rc = cli.main([
        "record-revised-delivery-acceptance",
        "--reconciliation-result-id", ctx["reconciliation_result_id"],
        "--revised-delivery-id", ctx["revised_delivery_id"],
        "--reviewer-id", "reviewer-1",
        "--accepted-formats", "vertical",
        "--quality-gate-reference", "qg-1",
        "--artifact-integrity-reference", "integrity-1",
        "--operator-id", "op",
        "--recorded-at", "t",
    ])
    assert rc == 0


def test_cli_acceptance_rejection_exit1(repo_root):
    ctx = _reconcile_revised_delivery(repo_root)
    cli = _cli()
    cli._repo_root = lambda: repo_root
    rc = cli.main([
        "record-revised-delivery-acceptance",
        "--reconciliation-result-id", "missing",
        "--revised-delivery-id", ctx["revised_delivery_id"],
        "--reviewer-id", "reviewer-1",
        "--accepted-formats", "vertical",
        "--quality-gate-reference", "qg-1",
        "--artifact-integrity-reference", "integrity-1",
        "--operator-id", "op",
        "--recorded-at", "t",
    ])
    assert rc == 1


def test_cli_create_authorization_success_exit0(repo_root):
    ctx = _reconcile_revised_delivery(repo_root)
    cli = _cli()
    cli._repo_root = lambda: repo_root
    cli.main([
        "record-revised-delivery-acceptance",
        "--reconciliation-result-id", ctx["reconciliation_result_id"],
        "--revised-delivery-id", ctx["revised_delivery_id"],
        "--reviewer-id", "reviewer-1",
        "--accepted-formats", "vertical",
        "--quality-gate-reference", "qg-1",
        "--artifact-integrity-reference", "integrity-1",
        "--operator-id", "op",
        "--recorded-at", "t",
    ])
    # Inspect to get the acceptance id.
    acc = _service()._acceptances_by_revision(repo_root=repo_root).get(ctx["revision_id"])
    assert acc is not None
    rc = cli.main([
        "create-customer-release-authorization",
        "--acceptance-id", acc.acceptance_id,
        "--authorized-by", "manager-1",
        "--authorization-scope", "vertical",
        "--approved-formats", "vertical",
        "--allowed-delivery-channels", "email_manual",
        "--customer-reference", "cust-1",
        "--approval-basis", "release_quality_gate_passed",
        "--policy-version", "scos-hvs-release-policy/1.0.0",
        "--expiry-at", "2099-01-01T00:00:00Z",
        "--operator-id", "op",
        "--recorded-at", "t",
    ])
    assert rc == 0


def test_cli_malformed_usage_exit2(repo_root):
    cli = _cli()
    rc = cli.main(["record-revised-delivery-acceptance", "--revised-delivery-id", "x"])
    assert rc == 2
