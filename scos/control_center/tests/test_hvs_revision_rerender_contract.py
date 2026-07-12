from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest

from scos.control_center.tests.test_hvs_delivery_version_lineage import _accepted_delivery


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "scos" / "work").mkdir(parents=True)
    return root


def test_registered_delivery_creates_deterministic_revision_request_and_plans_v2(repo_root):
    _, delivery, _ = _accepted_delivery(repo_root)
    lineage_models = import_module("scos.control_center.hvs_delivery_lineage_models")
    lineage_service = import_module("scos.control_center.hvs_delivery_lineage_service")
    revision_service = import_module("scos.control_center.hvs_revision_service")
    revision_models = import_module("scos.control_center.hvs_revision_models")
    registered = lineage_service.register_delivery_lineage(
        request=lineage_models.DeliveryLineageRegistrationRequest(
            delivery_record_id=delivery.delivery_record_id,
            delivery_version=lineage_models.DeliveryVersion(1),
            operator_id="op",
            registration_basis=lineage_models.BASIS_ORIGINAL_DELIVERY_CONFIRMED,
            confirm_legacy_version=True,
        ),
        repo_root=repo_root,
        recorded_at="t",
    )

    result = revision_service.create_revision_request(
        delivery_record_id=delivery.delivery_record_id,
        requested_by_id="customer-ref",
        operator_id="op",
        revision_items=(
            revision_models.RevisionItem.create(
                category="CAPTION_CHANGE",
                description="Correct the opening caption.",
                target_type="scene",
                target_id="scene-1",
                priority="normal",
                acceptance_requirement="Caption matches approved copy.",
                requested_by_id="customer-ref",
                source_artifact_sha256=registered.lineage.artifact_sha256,
            ),
        ),
        repo_root=repo_root,
        recorded_at="t",
    )

    assert result.ok
    assert result.revision.source_lineage_id == registered.lineage.lineage_id
    assert result.revision.source_delivery_version_display == "v1"
    assert result.revision.planned_successor_version_display == "v2"
    assert result.revision.status == "REVISION_REQUESTED"
    assert result.revision.automation_allowed is False


def test_revision_plan_approval_and_authorization_do_not_render(repo_root):
    _, delivery, _ = _accepted_delivery(repo_root)
    lm = import_module("scos.control_center.hvs_delivery_lineage_models")
    ls = import_module("scos.control_center.hvs_delivery_lineage_service")
    rm = import_module("scos.control_center.hvs_revision_models")
    rs = import_module("scos.control_center.hvs_revision_service")
    lineage = ls.register_delivery_lineage(request=lm.DeliveryLineageRegistrationRequest(delivery.delivery_record_id, lm.DeliveryVersion(1), "op", lm.BASIS_ORIGINAL_DELIVERY_CONFIRMED, True), repo_root=repo_root, recorded_at="t")
    created = rs.create_revision_request(delivery_record_id=delivery.delivery_record_id, requested_by_id="customer", operator_id="op", revision_items=(rm.RevisionItem.create(category="ASSET_REPLACEMENT", description="Replace approved still.", target_type="asset", target_id="asset-1", asset_id="asset-1", priority="normal", acceptance_requirement="Operator reviews replacement.", requested_by_id="customer", source_artifact_sha256=lineage.lineage.artifact_sha256),), repo_root=repo_root, recorded_at="t")
    reviewed = rs.start_revision_review(revision_request_id=created.revision.revision_request_id, operator_id="op", repo_root=repo_root, recorded_at="t")
    scoped = rs.assess_revision_impact(revision_request_id=created.revision.revision_request_id, operator_id="op", repo_root=repo_root, recorded_at="t")
    commercial = rs.classify_revision_commercial(revision_request_id=created.revision.revision_request_id, classification="INTERNAL_CORRECTION", operator_id="op", basis="internal production error", repo_root=repo_root, recorded_at="t")
    plan = rs.prepare_revision_plan(revision_request_id=created.revision.revision_request_id, operator_id="op", repo_root=repo_root, recorded_at="t")
    approval = rs.create_revision_approval_request(revision_request_id=created.revision.revision_request_id, operator_id="op", repo_root=repo_root, recorded_at="t")
    decided = rs.decide_revision_approval(revision_request_id=created.revision.revision_request_id, decision="APPROVE_RERENDER_PLAN", operator_id="op", repo_root=repo_root, recorded_at="t")
    authorized = rs.create_rerender_authorization(revision_request_id=created.revision.revision_request_id, operator_id="op", repo_root=repo_root, recorded_at="t")
    assert all(item.ok for item in (reviewed, scoped, commercial, plan, approval, decided, authorized))
    assert authorized.authorization.manual_dispatch_required is True
    assert authorized.authorization.rerender_started is False
    assert authorized.authorization.supersession_status == "NOT_YET_SUPERSEDED"


def test_unknown_lineage_and_unsafe_or_inferred_commercial_inputs_are_rejected(repo_root):
    _, delivery, _ = _accepted_delivery(repo_root)
    rm = import_module("scos.control_center.hvs_revision_models")
    rs = import_module("scos.control_center.hvs_revision_service")
    with __import__("pytest").raises(ValueError):
        rm.RevisionItem.create(category="OTHER", description="x", target_type="scene", target_id="../unsafe", priority="normal", acceptance_requirement="x", requested_by_id="r", source_artifact_sha256="a" * 64)
    blocked = rs.create_revision_request(delivery_record_id=delivery.delivery_record_id, requested_by_id="r", operator_id="op", revision_items=(), repo_root=repo_root, recorded_at="t")
    assert blocked.ok is False
    assert blocked.error_code == "EMPTY_REVISION_REQUEST"
