"""Stage 8I local commercial proposal preparation and handoff contract."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from scos.control_center import hvs_customer_outcome_service as outcomes
from scos.control_center.hvs_delivery_lineage_models import (
    BASIS_ORIGINAL_DELIVERY_CONFIRMED,
    DELIVERY_LINEAGE_EVENT_SCHEMA_VERSION,
    DELIVERY_LINEAGE_SCHEMA_VERSION,
    EVT_LINEAGE_REGISTERED,
    LINEAGE_REGISTERED,
    SUPERSESSION_NOT_YET_SUPERSEDED,
    DeliveryLineageEvent,
    DeliveryLineageRecord,
    stable_artifact_id,
    stable_lineage_event_id,
    stable_lineage_id,
)
from scos.control_center.hvs_delivery_lineage_store import (
    append_lineage_event,
    lineage_audit_path,
)
from scos.control_center.hvs_post_delivery_support_service import (
    record_commercial_closure,
    register_post_delivery_support_policy,
)
from scos.control_center.tests.test_hvs_post_delivery_support_authorization import _closed_context


def _register_lineage(repo: Path, *, project_id: str):
    artifact_sha256 = hashlib.sha256(b"stage-8i-synthetic-artifact").hexdigest()
    artifact_id = stable_artifact_id(artifact_sha256=artifact_sha256)
    lineage_id = stable_lineage_id(
        project_id=project_id,
        delivery_record_id="delivery-record-8i",
        delivery_closure_id="delivery-closure-8i",
        artifact_id=artifact_id,
        artifact_sha256=artifact_sha256,
        delivery_version_sequence=1,
        parent_lineage_id=None,
    )
    record = DeliveryLineageRecord(
        schema_version=DELIVERY_LINEAGE_SCHEMA_VERSION,
        lineage_id=lineage_id,
        project_id=project_id,
        recipient_label="synthetic-customer",
        delivery_record_id="delivery-record-8i",
        delivery_closure_id="delivery-closure-8i",
        artifact_id=artifact_id,
        artifact_sha256=artifact_sha256,
        delivery_version_sequence=1,
        delivery_version_display="v1",
        parent_lineage_id=None,
        parent_artifact_id=None,
        parent_artifact_sha256=None,
        parent_delivery_version_sequence=None,
        lineage_status=LINEAGE_REGISTERED,
        supersession_status=SUPERSESSION_NOT_YET_SUPERSEDED,
        registered_by_operator_id="operator-8i",
        registration_basis=BASIS_ORIGINAL_DELIVERY_CONFIRMED,
        evidence_reference="lineage-evidence-8i",
        registration_reason="synthetic certified lineage",
        deterministic_content_hash="synthetic-content-hash",
        registered_at="2026-07-01",
    )
    event = DeliveryLineageEvent(
        schema_version=DELIVERY_LINEAGE_EVENT_SCHEMA_VERSION,
        event_id=stable_lineage_event_id(
            event_type=EVT_LINEAGE_REGISTERED,
            lineage_id=lineage_id,
            delivery_record_id=record.delivery_record_id,
            detail="synthetic registered lineage",
        ),
        event_type=EVT_LINEAGE_REGISTERED,
        delivery_record_id=record.delivery_record_id,
        lineage_id=lineage_id,
        resulting_status=LINEAGE_REGISTERED,
        operator_id="operator-8i",
        recorded_at="2026-07-01",
        automation_allowed=False,
        detail="synthetic registered lineage",
        record=record.to_dict(),
    )
    append_lineage_event(audit_log_path=lineage_audit_path(repo), event=event)
    return record


@pytest.fixture
def qualified_opportunity(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / "scos" / "work").mkdir(parents=True)
    _ctx, _acc, authorization, _release, _receipt, _audit = _closed_context(repo)
    policy = register_post_delivery_support_policy(
        authorization_id=authorization.authorization_id,
        support_window_start="2026-07-01",
        support_window_end="2026-08-01",
        policy_type="STANDARD",
        included_issue_categories=("SUPPORT_QUESTION",),
        excluded_issue_categories=(),
        created_by_operator_id="operator-8i",
        policy_version="scos-hvs-support/1.0.0",
        repo_root=repo,
        recorded_at="2026-07-01",
    ).policy
    closure = record_commercial_closure(
        authorization_id=authorization.authorization_id,
        closure_basis="no_open_items",
        closed_by_operator_id="operator-8i",
        support_policy_id=policy.support_policy_id,
        repo_root=repo,
        recorded_at="2026-07-02",
    ).closure
    outcome = outcomes.record_customer_outcome(
        commercial_closure_id=closure.commercial_closure_id,
        customer_reference="customer-8i",
        recorded_by_operator_id="operator-8i",
        satisfaction_rating=5,
        delivery_quality_rating=5,
        communication_rating=5,
        timeliness_rating=5,
        business_outcome_status="ACHIEVED",
        business_outcome_summary="Synthetic delivery achieved its outcome.",
        evidence_references=("outcome-evidence-8i",),
        repo_root=repo,
        recorded_at="2026-07-03",
    ).record
    opportunity = outcomes.create_opportunity(
        opportunity_type="RENEWAL",
        commercial_closure_id=closure.commercial_closure_id,
        outcome_review_id=outcome.outcome_review_id,
        customer_reference="customer-8i",
        opportunity_summary="Renew the successful delivery service.",
        confidence_level=5,
        urgency="HIGH",
        created_by_operator_id="operator-8i",
        source_evidence_references=("scope-evidence-8i",),
        estimated_value="1000.00",
        currency="USD",
        repo_root=repo,
        created_at="2026-07-03",
    ).record
    qualification = outcomes.qualify_opportunity(
        opportunity_id=opportunity.opportunity_id,
        status="QUALIFIED",
        confirmed_by_operator_id="operator-8i",
        reason="Explicit operator qualification.",
        operator_confirmation=True,
        repo_root=repo,
        created_at="2026-07-03",
    )
    assert qualification.ok
    return repo, opportunity, _register_lineage(repo, project_id=closure.project_id)


def _request(opportunity, lineage, **overrides):
    data = {
        "opportunity_id": opportunity.opportunity_id,
        "delivery_lineage_id": lineage.lineage_id,
        "title": "Renewal proposal",
        "objective": "Continue the validated delivery service.",
        "scope_summary": "One renewal delivery package.",
        "deliverables": ({"description": "Renewal delivery package", "quantity": "1", "unit": "package", "evidence_reference": "scope-evidence-8i"},),
        "exclusions": ("New media production is excluded.",),
        "assumptions": ("Customer supplies approved source material.",),
        "line_items": ({"description": "Renewal package", "quantity": "1", "unit_price": "1000.00", "scope_key": "renewal-service"},),
        "currency": "USD",
        "tax_amount": "0.00",
        "tax_treatment": "tax amount explicitly supplied; treatment requires operator review",
        "discount_amount": "0.00",
        "payment_terms": "Due by manual commercial agreement.",
        "revision_terms": "One revision is included.",
        "validity_start_date": "2026-07-10",
        "validity_end_date": "2026-07-31",
        "operator_id": "operator-8i",
        "recorded_at": "2026-07-10",
    }
    data.update(overrides)
    return data


def test_qualified_renewal_converts_then_requires_readiness_and_operator_approval(qualified_opportunity):
    from scos.control_center import hvs_commercial_proposal_service as service

    repo, opportunity, lineage = qualified_opportunity
    source_before = outcomes.inspect_customer_success_lineage(project_id=opportunity.project_id, repo_root=repo)
    created = service.create_proposal_preparation(repo_root=repo, **_request(opportunity, lineage))
    readiness = service.evaluate_proposal_readiness(
        proposal_preparation_id=created.proposal.proposal_preparation_id,
        repo_root=repo,
        as_of="2026-07-10",
    )
    submitted = service.submit_for_internal_review(
        proposal_preparation_id=created.proposal.proposal_preparation_id,
        operator_id="operator-8i",
        repo_root=repo,
        recorded_at="2026-07-10",
    )
    approved = service.approve_for_manual_presentation(
        proposal_preparation_id=created.proposal.proposal_preparation_id,
        operator_id="operator-approver-8i",
        repo_root=repo,
        recorded_at="2026-07-10",
        as_of="2026-07-10",
    )
    handoff = service.create_manual_commercial_handoff(
        proposal_preparation_id=created.proposal.proposal_preparation_id,
        operator_id="operator-8i",
        repo_root=repo,
        recorded_at="2026-07-10",
    )

    assert created.ok and created.proposal.proposal_status == "DRAFT"
    assert readiness.state == "READY" and readiness.automation_allowed is False
    assert submitted.proposal.proposal_status == "READY_FOR_INTERNAL_REVIEW"
    assert approved.proposal.proposal_status == "APPROVED_FOR_MANUAL_PRESENTATION"
    assert handoff.handoff.manual_presentation_required is True
    assert handoff.handoff.proposal_sent is False
    assert handoff.handoff.customer_contacted is False
    assert handoff.handoff.invoice_created is False
    assert handoff.handoff.payment_link_created is False
    assert handoff.handoff.hvs_invoked is False
    assert outcomes.inspect_customer_success_lineage(project_id=opportunity.project_id, repo_root=repo) == source_before


def test_incomplete_commercial_input_needs_operator_input_and_cannot_be_approved(qualified_opportunity):
    from scos.control_center import hvs_commercial_proposal_service as service

    repo, opportunity, lineage = qualified_opportunity
    created = service.create_proposal_preparation(
        repo_root=repo,
        **_request(opportunity, lineage, line_items=()),
    )
    readiness = service.evaluate_proposal_readiness(
        proposal_preparation_id=created.proposal.proposal_preparation_id,
        repo_root=repo,
        as_of="2026-07-10",
    )
    approved = service.approve_for_manual_presentation(
        proposal_preparation_id=created.proposal.proposal_preparation_id,
        operator_id="operator-approver-8i",
        repo_root=repo,
        recorded_at="2026-07-10",
        as_of="2026-07-10",
    )
    handoff = service.create_manual_commercial_handoff(
        proposal_preparation_id=created.proposal.proposal_preparation_id,
        operator_id="operator-8i",
        repo_root=repo,
        recorded_at="2026-07-10",
    )

    assert created.ok
    assert readiness.state == "NEEDS_OPERATOR_INPUT"
    assert "LINE_ITEMS_REQUIRED" in readiness.blockers
    assert not approved.ok and approved.error_code == "READINESS_NOT_READY"
    assert not handoff.ok and handoff.error_code == "HANDOFF_REQUIRES_APPROVAL"


def test_expiry_blocks_approval_and_handoff_without_mutating_the_draft(qualified_opportunity):
    from scos.control_center import hvs_commercial_proposal_service as service

    repo, opportunity, lineage = qualified_opportunity
    created = service.create_proposal_preparation(repo_root=repo, **_request(opportunity, lineage))
    readiness = service.evaluate_proposal_readiness(
        proposal_preparation_id=created.proposal.proposal_preparation_id,
        repo_root=repo,
        as_of="2026-08-01",
    )
    approved = service.approve_for_manual_presentation(
        proposal_preparation_id=created.proposal.proposal_preparation_id,
        operator_id="operator-approver-8i",
        repo_root=repo,
        recorded_at="2026-08-01",
        as_of="2026-08-01",
    )

    assert readiness.state == "EXPIRED"
    assert not approved.ok and approved.error_code == "PROPOSAL_EXPIRED"
    assert service.inspect_proposal_preparation(
        proposal_preparation_id=created.proposal.proposal_preparation_id, repo_root=repo
    ).proposal.proposal_status == "DRAFT"


def test_identical_replay_is_idempotent_and_changed_scope_conflicts(qualified_opportunity):
    from scos.control_center import hvs_commercial_proposal_service as service

    repo, opportunity, lineage = qualified_opportunity
    request = _request(opportunity, lineage)
    first = service.create_proposal_preparation(repo_root=repo, **request)
    replay = service.create_proposal_preparation(repo_root=repo, **request)
    conflict = service.create_proposal_preparation(
        repo_root=repo,
        **_request(opportunity, lineage, scope_summary="A changed scope."),
    )

    assert replay.ok and replay.duplicate_of == first.proposal.proposal_preparation_id
    assert not conflict.ok and conflict.error_code == "CONFLICTING_COMMERCIAL_SCOPE"
    assert service.inspect_proposal_preparation(
        proposal_preparation_id=first.proposal.proposal_preparation_id, repo_root=repo
    ).proposal.scope_summary == "One renewal delivery package."


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("currency", "ZZZ", "INVALID_INPUT"),
        ("line_items", ({"description": "Renewal", "quantity": "0", "unit_price": "1", "scope_key": "renewal-service"},), "INVALID_INPUT"),
        ("discount_amount", "1001.00", "INVALID_INPUT"),
        ("objective", "unsafe\nobjective", "INVALID_INPUT"),
    ],
)
def test_invalid_commercial_input_is_rejected_without_a_proposal(qualified_opportunity, field, value, expected):
    from scos.control_center import hvs_commercial_proposal_service as service

    repo, opportunity, lineage = qualified_opportunity
    result = service.create_proposal_preparation(
        repo_root=repo, **_request(opportunity, lineage, **{field: value})
    )
    assert not result.ok and result.error_code == expected


def test_only_qualified_commercial_opportunities_are_convertible(qualified_opportunity):
    from scos.control_center import hvs_commercial_proposal_service as service

    repo, opportunity, lineage = qualified_opportunity
    opportunity_status = service.evaluate_opportunity_eligibility(
        opportunity_id=opportunity.opportunity_id,
        delivery_lineage_id=lineage.lineage_id,
        repo_root=repo,
    )
    assert opportunity_status.eligible is True


def test_cli_inspects_a_local_proposal_without_external_action(qualified_opportunity, monkeypatch, capsys):
    from scos.control_center import cli
    from scos.control_center import hvs_commercial_proposal_service as service

    repo, opportunity, lineage = qualified_opportunity
    created = service.create_proposal_preparation(repo_root=repo, **_request(opportunity, lineage))
    monkeypatch.setattr(cli, "_repo_root", lambda: repo)

    assert cli.main([
        "inspect-hvs-commercial-proposal",
        "--proposal-preparation-id", created.proposal.proposal_preparation_id,
    ]) == 0
    output = capsys.readouterr().out
    assert '"automation_allowed": false' in output
    assert '"proposal_sent": false' in output


def _cli_create_args(opportunity, lineage, *, recipient=None):
    request = _request(opportunity, lineage, commercial_recipient_reference=recipient)
    return [
        "create-hvs-commercial-proposal",
        "--opportunity-id", request["opportunity_id"],
        "--delivery-lineage-id", request["delivery_lineage_id"],
        "--title", request["title"],
        "--objective", request["objective"],
        "--scope-summary", request["scope_summary"],
        "--deliverables-json", json.dumps(request["deliverables"]),
        "--exclusions", ",".join(request["exclusions"]),
        "--assumptions", ",".join(request["assumptions"]),
        "--line-items-json", json.dumps(request["line_items"]),
        "--currency", request["currency"],
        "--tax-amount", request["tax_amount"],
        "--tax-treatment", request["tax_treatment"],
        "--discount-amount", request["discount_amount"],
        "--payment-terms", request["payment_terms"],
        "--revision-terms", request["revision_terms"],
        "--validity-start-date", request["validity_start_date"],
        "--validity-end-date", request["validity_end_date"],
        "--operator-id", request["operator_id"],
        "--recorded-at", request["recorded_at"],
    ] + (["--commercial-recipient-reference", recipient] if recipient else [])


def _cli_json(capsys):
    return json.loads(capsys.readouterr().out)


def test_cli_proves_complete_local_lifecycle_and_terminal_branches(qualified_opportunity, monkeypatch, capsys):
    from scos.control_center import cli

    repo, opportunity, lineage = qualified_opportunity
    monkeypatch.setattr(cli, "_repo_root", lambda: repo)

    assert cli.main(_cli_create_args(opportunity, lineage)) == 0
    proposal_id = _cli_json(capsys)["proposal"]["proposal_preparation_id"]
    assert cli.main(["inspect-hvs-commercial-proposal", "--proposal-preparation-id", proposal_id]) == 0
    assert _cli_json(capsys)["proposal"]["proposal_status"] == "DRAFT"
    assert cli.main(["evaluate-hvs-commercial-proposal-readiness", "--proposal-preparation-id", proposal_id, "--as-of", "2026-07-10"]) == 0
    assert _cli_json(capsys)["state"] == "READY"
    assert cli.main(["list-hvs-commercial-proposal-review-queue", "--as-of", "2026-07-10"]) == 0
    assert _cli_json(capsys)["items"][0]["proposal_preparation_id"] == proposal_id
    assert cli.main(["request-hvs-commercial-proposal-review", "--proposal-preparation-id", proposal_id, "--operator-id", "operator-8i", "--recorded-at", "2026-07-10"]) == 0
    assert _cli_json(capsys)["proposal"]["proposal_status"] == "READY_FOR_INTERNAL_REVIEW"
    assert cli.main(["approve-hvs-commercial-proposal", "--proposal-preparation-id", proposal_id, "--operator-id", "operator-approver-8i", "--as-of", "2026-07-10", "--recorded-at", "2026-07-10"]) == 0
    assert _cli_json(capsys)["proposal"]["proposal_status"] == "APPROVED_FOR_MANUAL_PRESENTATION"
    assert cli.main(["create-hvs-manual-commercial-handoff", "--proposal-preparation-id", proposal_id, "--operator-id", "operator-8i", "--recorded-at", "2026-07-10"]) == 0
    handoff = _cli_json(capsys)["handoff"]
    assert handoff["manual_presentation_required"] is True
    assert all(handoff[field] is False for field in ("proposal_sent", "customer_contacted", "customer_acceptance_recorded", "invoice_created", "payment_link_created", "payment_state_changed", "hvs_invoked", "automation_allowed"))

    assert cli.main(_cli_create_args(opportunity, lineage, recipient="customer-8i-reject")) == 0
    rejected_id = _cli_json(capsys)["proposal"]["proposal_preparation_id"]
    assert cli.main(["reject-hvs-commercial-proposal", "--proposal-preparation-id", rejected_id, "--operator-id", "operator-approver-8i", "--reason", "Commercial terms need revision", "--recorded-at", "2026-07-10"]) == 0
    assert _cli_json(capsys)["proposal"]["decision_reason"] == "Commercial terms need revision"

    assert cli.main(_cli_create_args(opportunity, lineage, recipient="customer-8i-cancel")) == 0
    cancelled_id = _cli_json(capsys)["proposal"]["proposal_preparation_id"]
    assert cli.main(["cancel-hvs-commercial-proposal", "--proposal-preparation-id", cancelled_id, "--operator-id", "operator-8i", "--reason", "Customer timing changed", "--recorded-at", "2026-07-10"]) == 0
    assert _cli_json(capsys)["proposal"]["proposal_status"] == "CANCELLED"


def test_review_queue_is_deterministic_and_excludes_terminal_proposals(qualified_opportunity):
    from scos.control_center import hvs_commercial_proposal_service as service

    repo, opportunity, lineage = qualified_opportunity
    first = service.create_proposal_preparation(repo_root=repo, **_request(opportunity, lineage))
    second = service.create_proposal_preparation(repo_root=repo, **_request(opportunity, lineage, commercial_recipient_reference="customer-8i-queue"))
    assert service.submit_for_internal_review(proposal_preparation_id=first.proposal.proposal_preparation_id, operator_id="operator-8i", repo_root=repo, recorded_at="2026-07-10").ok
    queue = service.list_proposal_review_queue(repo_root=repo, as_of="2026-07-10")
    assert [item["proposal_preparation_id"] for item in queue] == [first.proposal.proposal_preparation_id, second.proposal.proposal_preparation_id]
    assert queue[0]["recommended_manual_action"] == "APPROVE_OR_REJECT_INTERNAL_REVIEW"
    assert service.approve_for_manual_presentation(proposal_preparation_id=first.proposal.proposal_preparation_id, operator_id="operator-approver-8i", repo_root=repo, recorded_at="2026-07-10", as_of="2026-07-10").ok
    assert [item["proposal_preparation_id"] for item in service.list_proposal_review_queue(repo_root=repo, as_of="2026-07-10")] == [second.proposal.proposal_preparation_id]


def test_terminal_decisions_require_safe_reasons_and_submit_is_not_repeatable(qualified_opportunity):
    from scos.control_center import hvs_commercial_proposal_service as service

    repo, opportunity, lineage = qualified_opportunity
    created = service.create_proposal_preparation(repo_root=repo, **_request(opportunity, lineage))
    missing_reason = service.reject_proposal(proposal_preparation_id=created.proposal.proposal_preparation_id, operator_id="operator-8i", reason="", repo_root=repo, recorded_at="2026-07-10")
    assert not missing_reason.ok and missing_reason.error_code == "REASON_REQUIRED"
    submitted = service.submit_for_internal_review(proposal_preparation_id=created.proposal.proposal_preparation_id, operator_id="operator-8i", repo_root=repo, recorded_at="2026-07-10")
    replay = service.submit_for_internal_review(proposal_preparation_id=created.proposal.proposal_preparation_id, operator_id="operator-8i", repo_root=repo, recorded_at="2026-07-10")
    assert submitted.ok
    assert not replay.ok and replay.error_code == "INVALID_TRANSITION"
    rejected = service.reject_proposal(proposal_preparation_id=created.proposal.proposal_preparation_id, operator_id="operator-8i", reason="Scope requires internal revision", repo_root=repo, recorded_at="2026-07-10")
    assert rejected.ok and rejected.proposal.decision_reason == "Scope requires internal revision"
    assert not service.cancel_proposal(proposal_preparation_id=created.proposal.proposal_preparation_id, operator_id="operator-8i", reason="Too late", repo_root=repo, recorded_at="2026-07-10").ok


@pytest.mark.parametrize(
    ("as_of", "state", "blocker"),
    [("2026-07-09", "BLOCKED", "PROPOSAL_NOT_YET_VALID"), ("not-a-date", "BLOCKED", "INVALID_AS_OF_DATE"), ("2026-08-01", "EXPIRED", "PROPOSAL_EXPIRED")],
)
def test_readiness_validates_evaluation_date(qualified_opportunity, as_of, state, blocker):
    from scos.control_center import hvs_commercial_proposal_service as service

    repo, opportunity, lineage = qualified_opportunity
    created = service.create_proposal_preparation(repo_root=repo, **_request(opportunity, lineage))
    readiness = service.evaluate_proposal_readiness(proposal_preparation_id=created.proposal.proposal_preparation_id, repo_root=repo, as_of=as_of)
    assert readiness.state == state and readiness.blockers == (blocker,)


def test_optional_commercial_fields_are_part_of_content_identity(qualified_opportunity):
    from scos.control_center import hvs_commercial_proposal_service as service

    repo, opportunity, lineage = qualified_opportunity
    first = service.create_proposal_preparation(repo_root=repo, **_request(opportunity, lineage, dependency_notes=("Customer approval is required.",)))
    changed = service.create_proposal_preparation(repo_root=repo, **_request(opportunity, lineage, dependency_notes=("Legal approval is required.",)))
    assert first.ok
    assert not changed.ok and changed.error_code == "CONFLICTING_COMMERCIAL_SCOPE"


@pytest.mark.parametrize(
    ("field", "value"),
    [("recorded_at", "2026-02-30"), ("estimated_completion_date", "2026-07-09")],
)
def test_invalid_proposal_dates_are_rejected(qualified_opportunity, field, value):
    from scos.control_center import hvs_commercial_proposal_service as service

    repo, opportunity, lineage = qualified_opportunity
    result = service.create_proposal_preparation(repo_root=repo, **_request(opportunity, lineage, **{field: value}, estimated_start_date="2026-07-10" if field == "estimated_completion_date" else None))
    assert not result.ok and result.error_code == "INVALID_INPUT"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("commercial_recipient_reference", "unsafe\\recipient"),
        ("deliverables", ("not-an-object",)),
        ("line_items", ("not-an-object",)),
        ("exclusions", "not-a-list"),
    ],
)
def test_direct_service_rejects_invalid_commercial_container_and_recipient_inputs(qualified_opportunity, field, value):
    from scos.control_center import hvs_commercial_proposal_service as service

    repo, opportunity, lineage = qualified_opportunity
    result = service.create_proposal_preparation(repo_root=repo, **_request(opportunity, lineage, **{field: value}))
    assert not result.ok and result.error_code == "INVALID_INPUT"


def test_store_rejects_malformed_events(qualified_opportunity):
    from scos.control_center.hvs_commercial_proposal_store import commercial_proposal_path, read_commercial_proposal_events

    repo, _opportunity, _lineage = qualified_opportunity
    path = commercial_proposal_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not-json\n", encoding="utf-8")
    with pytest.raises(ValueError, match="malformed commercial proposal event"):
        read_commercial_proposal_events(audit_log_path=path)


def test_eligibility_fails_closed_for_each_source_contract(qualified_opportunity, monkeypatch):
    from scos.control_center import hvs_commercial_proposal_service as service

    repo, opportunity, lineage = qualified_opportunity
    assert service.evaluate_opportunity_eligibility(opportunity_id="missing", delivery_lineage_id=lineage.lineage_id, repo_root=repo).blockers == ("OPPORTUNITY_NOT_FOUND",)
    assert service.evaluate_opportunity_eligibility(opportunity_id=opportunity.opportunity_id, delivery_lineage_id="missing", repo_root=repo).blockers == ("DELIVERY_LINEAGE_INVALID",)

    with monkeypatch.context() as patch:
        patch.setattr(outcomes, "_qualifications", lambda _repo: {})
        assert service.evaluate_opportunity_eligibility(opportunity_id=opportunity.opportunity_id, delivery_lineage_id=lineage.lineage_id, repo_root=repo).blockers == ("OPPORTUNITY_NOT_QUALIFIED",)
    with monkeypatch.context() as patch:
        patch.setattr(outcomes, "_opportunities", lambda _repo: {opportunity.opportunity_id: replace(opportunity, opportunity_type="SUPPORT_FOLLOW_UP")})
        assert service.evaluate_opportunity_eligibility(opportunity_id=opportunity.opportunity_id, delivery_lineage_id=lineage.lineage_id, repo_root=repo).blockers == ("OPPORTUNITY_TYPE_NOT_COMMERCIAL",)
    with monkeypatch.context() as patch:
        patch.setattr(outcomes, "_opportunities", lambda _repo: {opportunity.opportunity_id: replace(opportunity, opportunity_type="REFERRAL")})
        assert service.evaluate_opportunity_eligibility(opportunity_id=opportunity.opportunity_id, delivery_lineage_id=lineage.lineage_id, repo_root=repo).blockers == ("REFERRAL_RECIPIENT_REQUIRED",)
    with monkeypatch.context() as patch:
        patch.setattr(outcomes, "_commercial_closure", lambda *_args: None)
        assert service.evaluate_opportunity_eligibility(opportunity_id=opportunity.opportunity_id, delivery_lineage_id=lineage.lineage_id, repo_root=repo).blockers == ("COMMERCIAL_CLOSURE_INVALID",)
    with monkeypatch.context() as patch:
        patch.setattr(outcomes, "_has_unresolved_dispute", lambda *_args: True)
        result = service.evaluate_opportunity_eligibility(opportunity_id=opportunity.opportunity_id, delivery_lineage_id=lineage.lineage_id, repo_root=repo)
        assert result.blockers == ("PRIORITY_BLOCKED", "UNRESOLVED_DISPUTE")
    outcome = outcomes._outcomes(repo)[opportunity.outcome_review_id]
    with monkeypatch.context() as patch:
        patch.setattr(outcomes, "_outcomes", lambda _repo: {opportunity.outcome_review_id: replace(outcome, unresolved_concerns=("Needs resolution",))})
        assert service.evaluate_opportunity_eligibility(opportunity_id=opportunity.opportunity_id, delivery_lineage_id=lineage.lineage_id, repo_root=repo).blockers == ("UNRESOLVED_CUSTOMER_CONCERNS",)
    with monkeypatch.context() as patch:
        patch.setattr(service, "_lineage", lambda *_args: replace(lineage, project_id="other-project"))
        assert service.evaluate_opportunity_eligibility(opportunity_id=opportunity.opportunity_id, delivery_lineage_id=lineage.lineage_id, repo_root=repo).blockers == ("DELIVERY_LINEAGE_MISMATCH",)
