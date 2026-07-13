"""Stage 8H customer-success evidence contract tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from scos.control_center import hvs_customer_outcome_service as service
from scos.control_center.hvs_customer_outcome_store import (
    customer_success_path,
    read_customer_success_events,
)
from scos.control_center.hvs_post_delivery_support_service import (
    record_commercial_closure,
    register_post_delivery_support_policy,
)
from scos.control_center.tests.test_hvs_post_delivery_support_authorization import _closed_context


def test_stage_8h_service_module_is_available():
    assert importlib.util.find_spec(
        "scos.control_center.hvs_customer_outcome_service"
    ) is not None


def test_priority_evaluator_is_exposed():
    assert callable(getattr(service, "evaluate_opportunity_priority", None))


def test_stage_8h_models_module_is_available():
    assert importlib.util.find_spec(
        "scos.control_center.hvs_customer_outcome_models"
    ) is not None


def test_priority_scoring_is_deterministic_and_explains_its_result():
    inputs = {
        "satisfaction_rating": 5,
        "delivery_quality_rating": 5,
        "business_outcome_status": "ACHIEVED",
        "estimated_value": "1000.00",
        "urgency": "HIGH",
        "confidence_level": 5,
        "unresolved_concerns": (),
        "unresolved_dispute": False,
        "active_support_issue": False,
    }
    first = service.evaluate_opportunity_priority(**inputs)
    second = service.evaluate_opportunity_priority(**inputs)
    assert first == second
    assert first["score_version"] == "scos-hvs.opportunity-priority/1.0.0"
    assert first["priority_band"] == "HIGH"
    assert first["automation_allowed"] is False
    assert first["scoring_reasons"]


def test_stage_8h_recording_service_surface_is_exposed():
    for name in (
        "record_customer_outcome",
        "record_portfolio_consent",
        "record_testimonial_consent",
        "revoke_consent",
        "create_opportunity",
        "qualify_opportunity",
        "portfolio_readiness",
        "testimonial_readiness",
        "list_manual_follow_up_queue",
        "inspect_customer_success_lineage",
    ):
        assert callable(getattr(service, name, None)), name


@pytest.fixture
def closed_lineage(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / "scos" / "work").mkdir(parents=True)
    ctx, _acc, auth, _release, _receipt, _audit = _closed_context(repo)
    policy = register_post_delivery_support_policy(
        authorization_id=auth.authorization_id,
        support_window_start="2026-01-01",
        support_window_end="2026-02-01",
        policy_type="STANDARD",
        included_issue_categories=("SUPPORT_QUESTION",),
        excluded_issue_categories=(),
        created_by_operator_id="operator-1",
        policy_version="scos-hvs-support/1.0.0",
        repo_root=repo,
        recorded_at="2026-01-02",
    ).policy
    closure = record_commercial_closure(
        authorization_id=auth.authorization_id,
        closure_basis="no_open_items",
        closed_by_operator_id="operator-1",
        support_policy_id=policy.support_policy_id,
        repo_root=repo,
        recorded_at="2026-01-03",
    ).closure
    assert closure is not None
    return repo, ctx, closure


def _outcome(repo, closure, *, key="review-1"):
    return service.record_customer_outcome(
        commercial_closure_id=closure.commercial_closure_id,
        customer_reference="customer-1",
        recorded_by_operator_id="operator-1",
        satisfaction_rating=5,
        delivery_quality_rating=5,
        communication_rating=4,
        timeliness_rating=5,
        business_outcome_status="ACHIEVED",
        business_outcome_summary="target reached",
        measurable_outcomes=({"metric": "leads", "value": "12", "unit": "count"},),
        evidence_references=("evidence-1",),
        idempotency_key=key,
        repo_root=repo,
        recorded_at="2026-01-04",
    )


def test_outcome_review_requires_closed_lineage_and_explicit_bounded_ratings(closed_lineage):
    repo, _ctx, closure = closed_lineage
    valid = _outcome(repo, closure)
    assert valid.ok
    assert valid.record.commercial_closure_id == closure.commercial_closure_id
    bad = service.record_customer_outcome(
        commercial_closure_id=closure.commercial_closure_id,
        customer_reference="customer-1",
        recorded_by_operator_id="operator-1",
        satisfaction_rating=6,
        delivery_quality_rating=5,
        communication_rating=4,
        timeliness_rating=5,
        business_outcome_status="ACHIEVED",
        business_outcome_summary="target reached",
        repo_root=repo,
    )
    assert not bad.ok and bad.error_code == "OUTCOME_REVIEW_VALIDATION"


def test_outcome_replay_is_idempotent_and_conflict_is_rejected(closed_lineage):
    repo, _ctx, closure = closed_lineage
    first = _outcome(repo, closure)
    replay = _outcome(repo, closure)
    assert replay.ok and replay.duplicate_of == first.record.outcome_review_id
    conflict = service.record_customer_outcome(
        commercial_closure_id=closure.commercial_closure_id,
        customer_reference="customer-1",
        recorded_by_operator_id="operator-1",
        satisfaction_rating=1,
        delivery_quality_rating=5,
        communication_rating=4,
        timeliness_rating=5,
        business_outcome_status="ACHIEVED",
        business_outcome_summary="target reached",
        idempotency_key="review-1",
        repo_root=repo,
    )
    assert not conflict.ok and conflict.error_code == "CONFLICTING_OUTCOME_REVIEW"


def test_portfolio_consent_is_scoped_explicit_and_revocation_or_expiry_blocks_readiness(closed_lineage):
    repo, _ctx, closure = closed_lineage
    outcome = _outcome(repo, closure).record
    outside = service.record_portfolio_consent(
        outcome_review_id=outcome.outcome_review_id, customer_reference="customer-1",
        consent_status="CONSENT_GRANTED", consent_scope="case-study",
        allowed_artifact_references=("other-delivery",), allowed_formats=("vertical",),
        allowed_usage_contexts=("website",), brand_name_usage=False, logo_usage=False,
        customer_name_usage=False, performance_metric_usage=False, anonymization_required=True,
        anonymization_rules=("remove names",), recorded_by_operator_id="operator-1",
        consent_basis="signed", repo_root=repo,
    )
    assert not outside.ok and outside.error_code == "ARTIFACT_OUTSIDE_DELIVERED_LINEAGE"
    consent = service.record_portfolio_consent(
        outcome_review_id=outcome.outcome_review_id, customer_reference="customer-1",
        consent_status="CONSENT_GRANTED", consent_scope="case-study",
        allowed_artifact_references=(outcome.revised_delivery_id,), allowed_formats=("vertical",),
        allowed_usage_contexts=("website",), brand_name_usage=False, logo_usage=False,
        customer_name_usage=False, performance_metric_usage=False, anonymization_required=True,
        anonymization_rules=("remove names",), recorded_by_operator_id="operator-1",
        consent_basis="signed", valid_from="2026-01-01", expires_at="2026-01-02", repo_root=repo,
    ).record
    assert service.portfolio_readiness(portfolio_consent_id=consent.portfolio_consent_id, repo_root=repo, as_of="2026-01-01")["portfolio_ready"]
    assert "CONSENT_EXPIRED" in service.portfolio_readiness(portfolio_consent_id=consent.portfolio_consent_id, repo_root=repo, as_of="2026-01-03")["blocking_reasons"]
    revoked = service.revoke_consent(consent_type="PORTFOLIO", consent_id=consent.portfolio_consent_id, revoked_by_operator_id="operator-1", revocation_reason="customer withdrew", repo_root=repo)
    assert revoked.ok
    assert "CONSENT_REVOKED" in service.portfolio_readiness(portfolio_consent_id=consent.portfolio_consent_id, repo_root=repo, as_of="2026-01-01")["blocking_reasons"]


def test_testimonial_consent_is_separate_and_binds_exact_text_hash(closed_lineage):
    repo, _ctx, closure = closed_lineage
    outcome = _outcome(repo, closure).record
    consent = service.record_testimonial_consent(
        outcome_review_id=outcome.outcome_review_id, customer_reference="customer-1",
        testimonial_reference="statement-1", testimonial_text_hash="sha256:" + "a" * 64,
        consent_status="CONSENT_GRANTED", approved_usage_contexts=("website",), approved_edits=("TYPO_FIX",),
        anonymization_required=True, recorded_by_operator_id="operator-1", consent_basis="written",
        attribution_name="Anonymous", repo_root=repo,
    ).record
    mismatch = service.testimonial_readiness(testimonial_consent_id=consent.testimonial_consent_id, testimonial_text_hash="sha256:" + "b" * 64, repo_root=repo, as_of="2026-01-01")
    assert not mismatch["testimonial_ready"] and "TESTIMONIAL_HASH_MISMATCH" in mismatch["blocking_reasons"]
    assert service.testimonial_readiness(testimonial_consent_id=consent.testimonial_consent_id, testimonial_text_hash="sha256:" + "a" * 64, requested_edit="TYPO_FIX", repo_root=repo, as_of="2026-01-01")["testimonial_ready"]


def test_opportunity_is_precise_idempotent_and_queue_evaluation_does_not_mutate(closed_lineage):
    repo, _ctx, closure = closed_lineage
    outcome = _outcome(repo, closure).record
    kwargs = dict(
        opportunity_type="RENEWAL", commercial_closure_id=closure.commercial_closure_id,
        outcome_review_id=outcome.outcome_review_id, customer_reference="customer-1",
        opportunity_summary="renew service", confidence_level=5, urgency="HIGH",
        created_by_operator_id="operator-1", estimated_value="123.45", currency="USD",
        target_follow_up_date="2026-01-05", idempotency_key="opp-1", repo_root=repo,
    )
    first = service.create_opportunity(**kwargs)
    replay = service.create_opportunity(**kwargs)
    assert first.ok and replay.duplicate_of == first.record.opportunity_id
    assert str(first.record.estimated_value) == "123.45"
    before = read_customer_success_events(audit_log_path=customer_success_path(repo))
    queue = service.list_manual_follow_up_queue(repo_root=repo, as_of="2026-01-06")
    after = read_customer_success_events(audit_log_path=customer_success_path(repo))
    assert queue[0]["overdue"] is True and before == after
    denied = service.qualify_opportunity(opportunity_id=first.record.opportunity_id, status="CONVERTED", confirmed_by_operator_id="operator-1", reason="accepted", repo_root=repo)
    assert not denied.ok and denied.error_code == "CONVERSION_REQUIRES_OPERATOR_CONFIRMATION"


def test_cli_priority_is_machine_readable_and_has_no_external_side_effect(capsys):
    from scos.control_center import cli

    rc = cli.main(["evaluate-opportunity-priority", "--inputs-json", '{"satisfaction_rating":5,"delivery_quality_rating":5,"business_outcome_status":"ACHIEVED","estimated_value":"1000","urgency":"HIGH","confidence_level":5}'])
    assert rc == 0
    assert '"automation_allowed": false' in capsys.readouterr().out
