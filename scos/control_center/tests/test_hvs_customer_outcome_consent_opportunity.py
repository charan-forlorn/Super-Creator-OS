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
    open_post_delivery_dispute,
    record_commercial_closure,
    record_post_delivery_issue,
    register_post_delivery_support_policy,
)
from scos.control_center.hvs_post_delivery_support_models import (
    POST_DELIVERY_SUPPORT_SCHEMA_VERSION,
    PostDeliveryCommercialClosure,
)
from scos.control_center.hvs_post_delivery_support_store import (
    append_post_delivery_support_event,
    make_post_delivery_support_event,
    post_delivery_support_path,
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
    renewal_item = next(item for item in queue if item["opportunity_id"] == first.record.opportunity_id)
    assert renewal_item["overdue"] is True and before == after
    denied = service.qualify_opportunity(opportunity_id=first.record.opportunity_id, status="CONVERTED", confirmed_by_operator_id="operator-1", reason="accepted", repo_root=repo)
    assert not denied.ok and denied.error_code == "CONVERSION_REQUIRES_OPERATOR_CONFIRMATION"


def test_cli_priority_is_machine_readable_and_has_no_external_side_effect(capsys):
    from scos.control_center import cli

    rc = cli.main(["evaluate-opportunity-priority", "--inputs-json", '{"satisfaction_rating":5,"delivery_quality_rating":5,"business_outcome_status":"ACHIEVED","estimated_value":"1000","urgency":"HIGH","confidence_level":5}'])
    assert rc == 0
    assert '"automation_allowed": false' in capsys.readouterr().out


def test_outcome_rejects_secret_like_or_private_media_metadata(closed_lineage):
    repo, _ctx, closure = closed_lineage
    for metadata in ({"api_key": "not-allowed"}, {"private_media_bytes": "abc"}):
        result = service.record_customer_outcome(
            commercial_closure_id=closure.commercial_closure_id,
            customer_reference="customer-1", recorded_by_operator_id="operator-1",
            satisfaction_rating=5, delivery_quality_rating=5, communication_rating=5,
            timeliness_rating=5, business_outcome_status="ACHIEVED",
            business_outcome_summary="target reached", metadata=metadata,
            idempotency_key="metadata-" + next(iter(metadata)), repo_root=repo,
        )
        assert not result.ok and result.error_code == "OUTCOME_REVIEW_VALIDATION"


def test_invalid_opportunity_target_date_is_rejected(closed_lineage):
    repo, _ctx, closure = closed_lineage
    outcome = _outcome(repo, closure).record
    result = service.create_opportunity(
        opportunity_type="RENEWAL", commercial_closure_id=closure.commercial_closure_id,
        outcome_review_id=outcome.outcome_review_id, customer_reference="customer-1",
        opportunity_summary="renew", confidence_level=3, urgency="MEDIUM",
        created_by_operator_id="operator-1", target_follow_up_date="not-a-date",
        repo_root=repo,
    )
    assert not result.ok and result.error_code == "OPPORTUNITY_VALIDATION"


def test_outcome_and_opportunity_readiness_block_an_active_post_closure_dispute(closed_lineage):
    repo, _ctx, closure = closed_lineage
    issue = record_post_delivery_issue(
        support_policy_id=closure.support_policy_id, issue_category="DISPUTE",
        issue_summary="quality dispute", recorded_by_operator_id="operator-1",
        customer_reference="customer-1", affected_formats=("vertical",),
        reported_at="2026-01-04", repo_root=repo, recorded_at="2026-01-04",
    ).issue
    dispute = open_post_delivery_dispute(
        issue_id=issue.issue_id, dispute_type="QUALITY", dispute_reason="unresolved",
        opened_by_operator_id="operator-1", repo_root=repo, recorded_at="2026-01-04",
    )
    assert dispute.ok
    outcome = _outcome(repo, closure, key="disputed-outcome")
    assert not outcome.ok and outcome.error_code == "UNRESOLVED_DISPUTE"


def test_queue_surfaces_missing_consent_and_distinguishes_due_states(closed_lineage):
    repo, _ctx, closure = closed_lineage
    outcome = _outcome(repo, closure).record
    renewal = service.create_opportunity(
        opportunity_type="RENEWAL", commercial_closure_id=closure.commercial_closure_id,
        outcome_review_id=outcome.outcome_review_id, customer_reference="customer-1",
        opportunity_summary="renew", confidence_level=3, urgency="MEDIUM",
        created_by_operator_id="operator-1", target_follow_up_date="2026-01-01",
        idempotency_key="past", repo_root=repo,
    )
    future = service.create_opportunity(
        opportunity_type="REFERRAL", commercial_closure_id=closure.commercial_closure_id,
        outcome_review_id=outcome.outcome_review_id, customer_reference="customer-1",
        opportunity_summary="refer", confidence_level=3, urgency="LOW",
        created_by_operator_id="operator-1", target_follow_up_date="2026-02-01",
        idempotency_key="future", repo_root=repo,
    )
    assert renewal.ok and future.ok
    items = service.list_manual_follow_up_queue(repo_root=repo, as_of="2026-01-10")
    assert any(item["opportunity_id"] == renewal.record.opportunity_id and item["due_state"] == "OVERDUE" for item in items)
    assert any(item["opportunity_id"] == future.record.opportunity_id and item["due_state"] == "FUTURE" for item in items)
    assert any(item["item_type"] == "MISSING_CONSENT_REVIEW" for item in items)


@pytest.mark.parametrize("rating", [1, 5])
def test_outcome_rating_boundaries_are_accepted(closed_lineage, rating):
    repo, _ctx, closure = closed_lineage
    result = service.record_customer_outcome(
        commercial_closure_id=closure.commercial_closure_id, customer_reference="customer-1",
        recorded_by_operator_id="operator-1", satisfaction_rating=rating,
        delivery_quality_rating=rating, communication_rating=rating, timeliness_rating=rating,
        business_outcome_status="NOT_MEASURED", business_outcome_summary="measured manually",
        idempotency_key=f"rating-{rating}", repo_root=repo,
    )
    assert result.ok and result.record.satisfaction_rating == rating


@pytest.mark.parametrize("rating", [0, 6, 1.5])
def test_outcome_invalid_rating_values_are_rejected(closed_lineage, rating):
    repo, _ctx, closure = closed_lineage
    result = service.record_customer_outcome(
        commercial_closure_id=closure.commercial_closure_id, customer_reference="customer-1",
        recorded_by_operator_id="operator-1", satisfaction_rating=rating,
        delivery_quality_rating=5, communication_rating=5, timeliness_rating=5,
        business_outcome_status="ACHIEVED", business_outcome_summary="target reached",
        idempotency_key=f"bad-rating-{rating}", repo_root=repo,
    )
    assert not result.ok and result.error_code == "OUTCOME_REVIEW_VALIDATION"


def test_portfolio_and_testimonial_consent_lifecycles_preserve_explicit_scopes(closed_lineage):
    repo, _ctx, closure = closed_lineage
    outcome = _outcome(repo, closure).record
    denied = service.record_portfolio_consent(
        outcome_review_id=outcome.outcome_review_id, customer_reference="customer-1",
        consent_status="CONSENT_DENIED", consent_scope="case-study",
        allowed_artifact_references=(), allowed_formats=(), allowed_usage_contexts=(),
        brand_name_usage=False, logo_usage=False, customer_name_usage=False,
        performance_metric_usage=False, anonymization_required=False, anonymization_rules=(),
        attribution_requirement="anonymous", recorded_by_operator_id="operator-1",
        consent_basis="written", idempotency_key="denied", repo_root=repo,
    )
    assert denied.ok
    assert not service.portfolio_readiness(portfolio_consent_id=denied.record.portfolio_consent_id, repo_root=repo, as_of="2026-01-01")["portfolio_ready"]
    testimonial = service.record_testimonial_consent(
        outcome_review_id=outcome.outcome_review_id, customer_reference="customer-1",
        testimonial_reference="statement-2", testimonial_text_hash="sha256:" + "c" * 64,
        consent_status="CONSENT_GRANTED", approved_usage_contexts=("website",), approved_edits=("TYPO_FIX",),
        attribution_name="Name", attribution_role="Role", attribution_company="Company",
        anonymization_required=True, valid_from="2026-01-01", expires_at="2026-01-02",
        recorded_by_operator_id="operator-1", consent_basis="written", idempotency_key="testimonial-2",
        repo_root=repo,
    )
    assert testimonial.ok
    ready = service.testimonial_readiness(testimonial_consent_id=testimonial.record.testimonial_consent_id, testimonial_text_hash="sha256:" + "c" * 64, repo_root=repo, as_of="2026-01-01")
    assert ready["testimonial_ready"] and ready["attribution_rules"] == {"name": "Name", "role": "Role", "company": "Company"}
    assert "EDIT_NOT_APPROVED" in service.testimonial_readiness(testimonial_consent_id=testimonial.record.testimonial_consent_id, testimonial_text_hash="sha256:" + "c" * 64, requested_edit="REWRITE", repo_root=repo, as_of="2026-01-01")["blocking_reasons"]
    assert "CONSENT_EXPIRED" in service.testimonial_readiness(testimonial_consent_id=testimonial.record.testimonial_consent_id, testimonial_text_hash="sha256:" + "c" * 64, repo_root=repo, as_of="2026-01-03")["blocking_reasons"]


@pytest.mark.parametrize("opportunity_type", ["RENEWAL", "FOLLOW_ON_PROJECT", "UPSELL", "REFERRAL", "SUPPORT_FOLLOW_UP", "NO_OPPORTUNITY"])
def test_every_opportunity_type_is_deterministic_audited_and_local(closed_lineage, opportunity_type):
    repo, _ctx, closure = closed_lineage
    outcome = _outcome(repo, closure, key="outcome-" + opportunity_type).record
    result = service.create_opportunity(
        opportunity_type=opportunity_type, commercial_closure_id=closure.commercial_closure_id,
        outcome_review_id=outcome.outcome_review_id, customer_reference="customer-1",
        opportunity_summary="manual review", confidence_level=1, urgency="LOW",
        created_by_operator_id="operator-1", idempotency_key="opp-" + opportunity_type, repo_root=repo,
    )
    replay = service.create_opportunity(
        opportunity_type=opportunity_type, commercial_closure_id=closure.commercial_closure_id,
        outcome_review_id=outcome.outcome_review_id, customer_reference="customer-1",
        opportunity_summary="manual review", confidence_level=1, urgency="LOW",
        created_by_operator_id="operator-1", idempotency_key="opp-" + opportunity_type, repo_root=repo,
    )
    assert result.ok and replay.duplicate_of == result.record.opportunity_id
    assert result.record.opportunity_type == opportunity_type and result.record.commercial_closure_id == closure.commercial_closure_id
    assert any(event.subject_id == result.record.opportunity_id for event in read_customer_success_events(audit_log_path=customer_success_path(repo)))


def test_scoring_bands_penalties_and_inputs_are_explicit_and_pure():
    common = dict(satisfaction_rating=1, delivery_quality_rating=1, business_outcome_status="NOT_MEASURED", estimated_value="0", urgency="LOW", confidence_level=1)
    low = service.evaluate_opportunity_priority(**common)
    medium = service.evaluate_opportunity_priority(**dict(common, satisfaction_rating=3, delivery_quality_rating=3, business_outcome_status="PARTIALLY_ACHIEVED", urgency="MEDIUM", confidence_level=3))
    high = service.evaluate_opportunity_priority(**dict(common, satisfaction_rating=5, delivery_quality_rating=5, business_outcome_status="ACHIEVED", estimated_value="1000", urgency="HIGH", confidence_level=5))
    blocked = service.evaluate_opportunity_priority(**dict(common, unresolved_dispute=True))
    insufficient = service.evaluate_opportunity_priority(satisfaction_rating=None, delivery_quality_rating=1, business_outcome_status="NOT_MEASURED", urgency="LOW", confidence_level=1)
    penalized = service.evaluate_opportunity_priority(**dict(common, unresolved_concerns=("open",), active_support_issue=True))
    assert (low["priority_band"], medium["priority_band"], high["priority_band"], blocked["priority_band"], insufficient["priority_band"]) == ("LOW", "MEDIUM", "HIGH", "BLOCKED", "INSUFFICIENT_EVIDENCE")
    assert penalized["score"] < low["score"] and blocked["blocking_reasons"] == ("UNRESOLVED_DISPUTE",)
    assert high["score"] > low["score"] and high["automation_allowed"] is False


def test_forged_commercial_closure_without_stage_8f_audit_is_rejected(tmp_path: Path):
    repo = tmp_path / "forged"
    (repo / "scos" / "work").mkdir(parents=True)
    forged = PostDeliveryCommercialClosure(
        schema_version=POST_DELIVERY_SUPPORT_SCHEMA_VERSION, commercial_closure_id="forged-closure",
        project_id="project-1", revision_id="revision-1", revised_delivery_id="delivery-1",
        release_execution_id="release-1", receipt_confirmation_id="receipt-1", post_delivery_closure_id="audit-1",
        support_policy_id="policy-1", issue_ids=(), dispute_ids=(), reopen_ids=(), closure_status="COMMERCIALLY_CLOSED",
        closure_basis="forged", closed_by_operator_id="operator-1", closed_at="2026-01-01", outstanding_actions=(),
        invoice_state_reference=None, payment_state_reference=None, evidence_references=(), idempotency_key="forged", created_at="2026-01-01",
    )
    append_post_delivery_support_event(
        audit_log_path=post_delivery_support_path(repo),
        event=make_post_delivery_support_event(event_type="COMMERCIAL_CLOSURE_RECORDED", subject_id=forged.commercial_closure_id, operator_id="operator-1", recorded_at="2026-01-01", record=forged.to_dict()),
    )
    result = service.record_customer_outcome(
        commercial_closure_id=forged.commercial_closure_id, customer_reference="customer-1",
        recorded_by_operator_id="operator-1", satisfaction_rating=5, delivery_quality_rating=5,
        communication_rating=5, timeliness_rating=5, business_outcome_status="ACHIEVED",
        business_outcome_summary="forged", repo_root=repo,
    )
    assert not result.ok and result.error_code == "COMMERCIAL_CLOSURE_LINEAGE_INVALID"


def test_portfolio_rejects_unsupported_context_and_exposes_identity_scopes(closed_lineage):
    repo, _ctx, closure = closed_lineage
    outcome = _outcome(repo, closure).record
    unsupported = service.record_portfolio_consent(
        outcome_review_id=outcome.outcome_review_id, customer_reference="customer-1",
        consent_status="CONSENT_GRANTED", consent_scope="case-study",
        allowed_artifact_references=(outcome.revised_delivery_id,), allowed_formats=("vertical",),
        allowed_usage_contexts=("unknown-channel",), brand_name_usage=False, logo_usage=False,
        customer_name_usage=False, performance_metric_usage=False, anonymization_required=False,
        anonymization_rules=(), recorded_by_operator_id="operator-1", consent_basis="written", repo_root=repo,
    )
    assert not unsupported.ok and unsupported.error_code == "PORTFOLIO_CONSENT_VALIDATION"
    granted = service.record_portfolio_consent(
        outcome_review_id=outcome.outcome_review_id, customer_reference="customer-1",
        consent_status="CONSENT_GRANTED", consent_scope="case-study",
        allowed_artifact_references=(outcome.revised_delivery_id,), allowed_formats=("vertical",),
        allowed_usage_contexts=("website",), brand_name_usage=True, logo_usage=True,
        customer_name_usage=True, performance_metric_usage=True, anonymization_required=False,
        anonymization_rules=(), attribution_requirement="full attribution", recorded_by_operator_id="operator-1",
        consent_basis="written", idempotency_key="scopes", repo_root=repo,
    )
    assert granted.ok
    readiness = service.portfolio_readiness(portfolio_consent_id=granted.record.portfolio_consent_id, repo_root=repo, as_of="2026-01-01")
    assert readiness["identity_usage"] == {"brand_name": True, "logo": True, "customer_name": True, "performance_metric": True}
    assert readiness["attribution_requirement"] == "full attribution"


def test_queue_surfaces_expiring_consent_and_unresolved_outcome_review(closed_lineage):
    repo, _ctx, closure = closed_lineage
    outcome = service.record_customer_outcome(
        commercial_closure_id=closure.commercial_closure_id, customer_reference="customer-1",
        recorded_by_operator_id="operator-1", satisfaction_rating=3, delivery_quality_rating=3,
        communication_rating=3, timeliness_rating=3, business_outcome_status="NOT_MEASURED",
        business_outcome_summary="awaiting measurement", unresolved_concerns=("confirm impact",),
        idempotency_key="unresolved", repo_root=repo,
    ).record
    consent = service.record_portfolio_consent(
        outcome_review_id=outcome.outcome_review_id, customer_reference="customer-1",
        consent_status="CONSENT_GRANTED", consent_scope="case-study",
        allowed_artifact_references=(outcome.revised_delivery_id,), allowed_formats=("vertical",),
        allowed_usage_contexts=("website",), brand_name_usage=False, logo_usage=False,
        customer_name_usage=False, performance_metric_usage=False, anonymization_required=False,
        anonymization_rules=(), recorded_by_operator_id="operator-1", consent_basis="written",
        valid_from="2026-01-01", expires_at="2026-01-12", idempotency_key="expiring", repo_root=repo,
    )
    assert consent.ok
    items = service.list_manual_follow_up_queue(repo_root=repo, as_of="2026-01-10")
    assert {"EXPIRING_CONSENT_REVIEW", "UNRESOLVED_OUTCOME_REVIEW"}.issubset({item["item_type"] for item in items})


@pytest.mark.parametrize(
    ("estimated_value", "currency", "confidence", "expected"),
    [
        ("12.34", "USD", 1, True),
        ("12.34", "USD", 5, True),
        ("not-money", "USD", 3, False),
        ("-1", "USD", 3, False),
        ("12", None, 3, False),
        ("12", "usd", 3, False),
        ("12", "USD", 0, False),
        ("12", "USD", 6, False),
    ],
)
def test_opportunity_money_currency_and_confidence_validation(closed_lineage, estimated_value, currency, confidence, expected):
    repo, _ctx, closure = closed_lineage
    outcome = _outcome(repo, closure).record
    result = service.create_opportunity(
        opportunity_type="UPSELL", commercial_closure_id=closure.commercial_closure_id,
        outcome_review_id=outcome.outcome_review_id, customer_reference="customer-1",
        opportunity_summary="expand", confidence_level=confidence, urgency="MEDIUM",
        created_by_operator_id="operator-1", estimated_value=estimated_value, currency=currency,
        idempotency_key=f"value-{estimated_value}-{currency}-{confidence}", repo_root=repo,
    )
    assert result.ok is expected
    if not expected:
        assert result.error_code == "OPPORTUNITY_VALIDATION"


def test_consent_replays_conflicts_and_revocations_are_append_only(closed_lineage):
    repo, _ctx, closure = closed_lineage
    outcome = _outcome(repo, closure).record
    kwargs = dict(
        outcome_review_id=outcome.outcome_review_id, customer_reference="customer-1",
        consent_status="CONSENT_GRANTED", consent_scope="case-study",
        allowed_artifact_references=(outcome.revised_delivery_id,), allowed_formats=("vertical",),
        allowed_usage_contexts=("website",), brand_name_usage=False, logo_usage=False,
        customer_name_usage=False, performance_metric_usage=False, anonymization_required=False,
        anonymization_rules=(), recorded_by_operator_id="operator-1", consent_basis="written",
        idempotency_key="portfolio-replay", repo_root=repo,
    )
    first = service.record_portfolio_consent(**kwargs)
    replay = service.record_portfolio_consent(**kwargs)
    conflict = service.record_portfolio_consent(**dict(kwargs, consent_scope="proposal"))
    assert first.ok and replay.duplicate_of == first.record.portfolio_consent_id
    assert not conflict.ok and conflict.error_code == "CONFLICTING_PORTFOLIO_CONSENT"
    before = read_customer_success_events(audit_log_path=customer_success_path(repo))
    revoked = service.revoke_consent(consent_type="PORTFOLIO", consent_id=first.record.portfolio_consent_id, revoked_by_operator_id="operator-1", revocation_reason="withdrawn", repo_root=repo)
    after = read_customer_success_events(audit_log_path=customer_success_path(repo))
    assert revoked.ok and len(after) == len(before) + 1
    assert service._portfolio_consents(repo)[first.record.portfolio_consent_id].consent_status == "CONSENT_GRANTED"


def test_cli_customer_success_commands_are_json_and_use_canonical_exit_codes(closed_lineage, capsys, monkeypatch):
    from scos.control_center import cli

    repo, _ctx, closure = closed_lineage
    monkeypatch.setattr(cli, "_repo_root", lambda: repo)
    outcome_rc = cli.main([
        "record-customer-outcome", "--commercial-closure-id", closure.commercial_closure_id,
        "--customer-reference", "customer-1", "--recorded-by-operator-id", "operator-1",
        "--satisfaction-rating", "5", "--delivery-quality-rating", "5", "--communication-rating", "5",
        "--timeliness-rating", "5", "--business-outcome-status", "ACHIEVED",
        "--business-outcome-summary", "target reached", "--recorded-at", "2026-01-04",
    ])
    outcome = next(iter(service._outcomes(repo).values()))
    portfolio_rc = cli.main([
        "record-portfolio-consent", "--outcome-review-id", outcome.outcome_review_id,
        "--customer-reference", "customer-1", "--consent-status", "CONSENT_GRANTED",
        "--consent-scope", "case-study", "--allowed-artifact-references", outcome.revised_delivery_id,
        "--allowed-formats", "vertical", "--allowed-usage-contexts", "website",
        "--recorded-by-operator-id", "operator-1", "--consent-basis", "written", "--recorded-at", "2026-01-04",
    ])
    portfolio = next(iter(service._portfolio_consents(repo).values()))
    testimonial_rc = cli.main([
        "record-testimonial-consent", "--outcome-review-id", outcome.outcome_review_id,
        "--customer-reference", "customer-1", "--testimonial-reference", "statement-cli",
        "--testimonial-text-hash", "sha256:" + "d" * 64, "--consent-status", "CONSENT_GRANTED",
        "--approved-usage-contexts", "website", "--recorded-by-operator-id", "operator-1",
        "--consent-basis", "written", "--recorded-at", "2026-01-04",
    ])
    testimonial = next(iter(service._testimonial_consents(repo).values()))
    opportunity_rc = cli.main([
        "create-opportunity", "--opportunity-type", "RENEWAL", "--commercial-closure-id", closure.commercial_closure_id,
        "--outcome-review-id", outcome.outcome_review_id, "--customer-reference", "customer-1",
        "--opportunity-summary", "renew", "--confidence-level", "5", "--urgency", "HIGH",
        "--created-by-operator-id", "operator-1", "--recorded-at", "2026-01-04",
    ])
    opportunity = next(iter(service._opportunities(repo).values()))
    assert [outcome_rc, portfolio_rc, testimonial_rc, opportunity_rc] == [0, 0, 0, 0]
    assert cli.main(["inspect-portfolio-readiness", "--portfolio-consent-id", portfolio.portfolio_consent_id, "--as-of", "2026-01-04"]) == 0
    assert cli.main(["inspect-testimonial-readiness", "--testimonial-consent-id", testimonial.testimonial_consent_id, "--testimonial-text-hash", testimonial.testimonial_text_hash, "--as-of", "2026-01-04"]) == 0
    assert cli.main(["qualify-opportunity", "--opportunity-id", opportunity.opportunity_id, "--status", "QUALIFIED", "--confirmed-by-operator-id", "operator-1", "--reason", "reviewed"]) == 0
    assert cli.main(["inspect-opportunity", "--opportunity-id", opportunity.opportunity_id]) == 0
    assert cli.main(["list-manual-follow-up-queue", "--as-of", "2026-01-04"]) == 0
    assert cli.main(["inspect-customer-success-lineage", "--project-id", outcome.project_id]) == 0
    assert cli.main(["record-customer-outcome"]) == 2
    output = capsys.readouterr().out
    assert '"automation_allowed": false' in output and "api_key" not in output


def test_stage_8h_source_has_no_outbound_or_execution_dependency():
    source = Path(service.__file__).read_text(encoding="utf-8")
    store = Path(customer_success_path.__module__.replace(".", "/") + ".py")
    forbidden = ("import requests", "import urllib", "import httpx", "import socket", "import subprocess", "shell=True", "from hvs ", "import hvs\n", "hvs.cli", "smtplib", "webhook")
    assert all(token not in source for token in forbidden)
    assert store.name == "hvs_customer_outcome_store.py"


def test_testimonial_denial_replay_conflict_and_revocation_are_independent(closed_lineage):
    repo, _ctx, closure = closed_lineage
    outcome = _outcome(repo, closure).record
    base = dict(
        outcome_review_id=outcome.outcome_review_id, customer_reference="customer-1",
        testimonial_reference="statement-3", testimonial_text_hash="sha256:" + "e" * 64,
        consent_status="CONSENT_DENIED", approved_usage_contexts=(), approved_edits=(),
        anonymization_required=False, recorded_by_operator_id="operator-1", consent_basis="written",
        idempotency_key="testimonial-denied", repo_root=repo,
    )
    denied = service.record_testimonial_consent(**base)
    replay = service.record_testimonial_consent(**base)
    conflict = service.record_testimonial_consent(**dict(base, consent_status="CONSENT_GRANTED", approved_usage_contexts=("website",)))
    assert denied.ok and replay.duplicate_of == denied.record.testimonial_consent_id
    assert not conflict.ok and conflict.error_code == "CONFLICTING_TESTIMONIAL_CONSENT"
    assert "CONSENT_NOT_GRANTED" in service.testimonial_readiness(testimonial_consent_id=denied.record.testimonial_consent_id, testimonial_text_hash=denied.record.testimonial_text_hash, repo_root=repo, as_of="2026-01-01")["blocking_reasons"]
    granted = service.record_testimonial_consent(**dict(base, testimonial_reference="statement-4", testimonial_text_hash="sha256:" + "f" * 64, consent_status="CONSENT_GRANTED", approved_usage_contexts=("website",), idempotency_key="testimonial-granted"))
    revocation = service.revoke_consent(consent_type="TESTIMONIAL", consent_id=granted.record.testimonial_consent_id, revoked_by_operator_id="operator-1", revocation_reason="withdrawn", repo_root=repo)
    assert revocation.ok
    assert "CONSENT_REVOKED" in service.testimonial_readiness(testimonial_consent_id=granted.record.testimonial_consent_id, testimonial_text_hash=granted.record.testimonial_text_hash, repo_root=repo, as_of="2026-01-01")["blocking_reasons"]


def test_opportunity_readiness_queue_order_and_active_dispute_are_deterministic(closed_lineage):
    repo, _ctx, closure = closed_lineage
    outcome = _outcome(repo, closure).record
    created = []
    for opportunity_type, key in (("SUPPORT_FOLLOW_UP", "a"), ("REFERRAL", "b")):
        created.append(service.create_opportunity(
            opportunity_type=opportunity_type, commercial_closure_id=closure.commercial_closure_id,
            outcome_review_id=outcome.outcome_review_id, customer_reference="customer-1",
            opportunity_summary="manual", confidence_level=3, urgency="MEDIUM",
            created_by_operator_id="operator-1", target_follow_up_date="2026-01-10",
            idempotency_key=key, repo_root=repo,
        ).record)
    first = service.list_manual_follow_up_queue(repo_root=repo, as_of="2026-01-05")
    second = service.list_manual_follow_up_queue(repo_root=repo, as_of="2026-01-05")
    assert first == second and all(item["automation_allowed"] is False for item in first)
    issue = record_post_delivery_issue(
        support_policy_id=closure.support_policy_id, issue_category="DISPUTE", issue_summary="after close",
        recorded_by_operator_id="operator-1", customer_reference="customer-1", affected_formats=("vertical",),
        reported_at="2026-01-05", repo_root=repo, recorded_at="2026-01-05",
    ).issue
    assert open_post_delivery_dispute(issue_id=issue.issue_id, dispute_type="QUALITY", dispute_reason="open", opened_by_operator_id="operator-1", repo_root=repo, recorded_at="2026-01-05").ok
    readiness = service.opportunity_readiness(opportunity_id=created[0].opportunity_id, repo_root=repo)
    assert not readiness["opportunity_eligible"] and "UNRESOLVED_DISPUTE" in readiness["blockers"]


@pytest.mark.parametrize("unsafe", ["../customer", "customer\nlog", "https://customer", "customer;rm"])
def test_unsafe_customer_reference_is_rejected(closed_lineage, unsafe):
    repo, _ctx, closure = closed_lineage
    result = service.record_customer_outcome(
        commercial_closure_id=closure.commercial_closure_id, customer_reference=unsafe,
        recorded_by_operator_id="operator-1", satisfaction_rating=5, delivery_quality_rating=5,
        communication_rating=5, timeliness_rating=5, business_outcome_status="ACHIEVED",
        business_outcome_summary="target", idempotency_key="unsafe-" + str(abs(hash(unsafe))), repo_root=repo,
    )
    assert not result.ok and result.error_code == "OUTCOME_REVIEW_VALIDATION"
