"""Stage 8K engagement activation and production kickoff authorization gate."""

from __future__ import annotations

import inspect
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from scos.control_center import hvs_commercial_acceptance_service as acceptance_service
from scos.control_center import hvs_commercial_proposal_service as proposal_service
from scos.control_center import hvs_engagement_activation_models as models
from scos.control_center import hvs_engagement_activation_service as service
from scos.control_center.hvs_commercial_acceptance_store import (
    commercial_acceptance_path,
    read_commercial_acceptance_events,
)
from scos.control_center.hvs_engagement_activation_models import (
    APPROVED_FOR_PROJECT_INITIALIZATION,
    DEPOSIT_REQUIRED_BEFORE_START,
    ENGAGEMENT_ACTIVATION_EVENT_SCHEMA_VERSION,
    EVT_ENGAGEMENT_ACTIVATION_CREATED,
    INPUT_FINAL_PRODUCTION_BRIEF,
    PAYMENT_NOT_REQUIRED_BEFORE_START,
    PAYMENT_REQUIREMENT_UNKNOWN,
    READINESS_READY,
    READINESS_WAITING_FOR_CUSTOMER_INPUT,
    READINESS_WAITING_FOR_PAYMENT,
)
from scos.control_center.hvs_engagement_activation_store import (
    engagement_activation_path,
    read_engagement_activation_events,
)
from scos.control_center.tests.test_hvs_commercial_proposal_handoff import (
    _request,
    qualified_opportunity,
)


@pytest.fixture
def accepted_source(qualified_opportunity):
    repo, opportunity, lineage = qualified_opportunity
    created = proposal_service.create_proposal_preparation(repo_root=repo, **_request(opportunity, lineage))
    assert created.ok
    assert proposal_service.submit_for_internal_review(
        proposal_preparation_id=created.proposal.proposal_preparation_id,
        operator_id="operator-8k-review",
        repo_root=repo,
        recorded_at="2026-07-10",
    ).ok
    approved = proposal_service.approve_for_manual_presentation(
        proposal_preparation_id=created.proposal.proposal_preparation_id,
        operator_id="operator-8k-approver",
        repo_root=repo,
        recorded_at="2026-07-10",
        as_of="2026-07-10",
    )
    assert approved.ok
    handoff = proposal_service.create_manual_commercial_handoff(
        proposal_preparation_id=approved.proposal.proposal_preparation_id,
        operator_id="operator-8k-handoff",
        repo_root=repo,
        recorded_at="2026-07-10",
    )
    assert handoff.ok
    presentation = acceptance_service.record_manual_proposal_presentation(
        proposal_preparation_id=approved.proposal.proposal_preparation_id,
        commercial_handoff_package_id=handoff.handoff.handoff_id,
        presentation_channel="VIDEO_CALL",
        presentation_date="2026-07-12",
        presented_by_operator_id="operator-8k-presenter",
        evidence_reference="presentation-evidence-8k",
        customer_participant_reference="customer-contact-8k",
        operator_note="Manual presentation completed.",
        manual_action_confirmed=True,
        repo_root=repo,
        recorded_at="2026-07-12",
    )
    assert presentation.ok
    decision = acceptance_service.record_customer_commercial_decision(
        presentation_record_id=presentation.presentation.presentation_record_id,
        decision_type="ACCEPTED",
        decision_date="2026-07-13",
        recorded_by_operator_id="operator-8k-decision",
        evidence_reference="acceptance-evidence-8k",
        approved_proposal_content_hash=approved.proposal.deterministic_content_hash,
        customer_decision_reference="customer-decision-ref-8k",
        accepted_total="1000.00",
        accepted_currency="USD",
        accepted_scope_hash=approved.proposal.commercial_scope_id,
        accepted_payment_terms=approved.proposal.payment_terms,
        accepted_revision_terms=approved.proposal.revision_terms,
        accepted_tax="0.00",
        accepted_discount="0.00",
        repo_root=repo,
        recorded_at="2026-07-13",
    )
    assert decision.ok
    return repo, approved.proposal, handoff.handoff, presentation.presentation, decision.decision, decision.acceptance


def _activation(repo: Path, acceptance, **overrides):
    data = {
        "commercial_acceptance_id": acceptance.commercial_acceptance_id,
        "operator_id": "operator-8k",
        "repo_root": repo,
        "recorded_at": "2026-07-14",
        "target_start_date": "2026-07-20",
        "target_completion_date": "2026-07-31",
        "production_dependency_notes": ("Customer assets received through approved manual evidence.",),
        "production_risk_notes": ("Schedule depends on final brief completeness.",),
    }
    data.update(overrides)
    return service.create_engagement_activation(**data)


def _make_ready_no_payment(repo: Path, activation_id: str):
    current = service.inspect_engagement_activation(engagement_activation_id=activation_id, repo_root=repo).activation
    if current.payment_start_requirement == PAYMENT_REQUIREMENT_UNKNOWN:
        payment = service.record_payment_start_requirement(
            engagement_activation_id=activation_id,
            payment_start_requirement=PAYMENT_NOT_REQUIRED_BEFORE_START,
            operator_id="operator-8k-payment",
            repo_root=repo,
            recorded_at="2026-07-14",
        )
        assert payment.ok
    requirement = service.add_customer_input_requirement(
        engagement_activation_id=activation_id,
        requirement_type=INPUT_FINAL_PRODUCTION_BRIEF,
        description="Final operator-reviewed production brief.",
        operator_id="operator-8k-input",
        repo_root=repo,
        recorded_at="2026-07-14",
    )
    assert requirement.ok
    input_id = requirement.activation.customer_input_requirements[0].customer_input_requirement_id
    confirmed = service.confirm_customer_input_requirement(
        engagement_activation_id=activation_id,
        customer_input_requirement_id=input_id,
        operator_id="operator-8k-input",
        evidence_reference="evidence-final-brief-8k",
        confirmation_date="2026-07-14",
        repo_root=repo,
        recorded_at="2026-07-14",
    )
    assert confirmed.ok
    return confirmed.activation


@pytest.fixture
def accepted_source_factory(qualified_opportunity):
    repo, opportunity, lineage = qualified_opportunity

    def build(suffix: str):
        created = proposal_service.create_proposal_preparation(
            repo_root=repo,
            **_request(
                opportunity,
                lineage,
                title=f"Renewal proposal {suffix}",
                scope_summary=f"One renewal delivery package {suffix}.",
                deliverables=({"description": f"Renewal delivery package {suffix}", "quantity": "1", "unit": "package", "evidence_reference": "scope-evidence-8i"},),
                line_items=({"description": f"Renewal package {suffix}", "quantity": "1", "unit_price": "1000.00", "scope_key": f"renewal-service-{suffix}"},),
                commercial_recipient_reference=f"customer-commercial-{suffix}",
                operator_id=f"operator-{suffix}",
            ),
        )
        assert created.ok
        assert proposal_service.submit_for_internal_review(
            proposal_preparation_id=created.proposal.proposal_preparation_id,
            operator_id=f"operator-review-{suffix}",
            repo_root=repo,
            recorded_at="2026-07-10",
        ).ok
        approved = proposal_service.approve_for_manual_presentation(
            proposal_preparation_id=created.proposal.proposal_preparation_id,
            operator_id=f"operator-approver-{suffix}",
            repo_root=repo,
            recorded_at="2026-07-10",
            as_of="2026-07-10",
        )
        assert approved.ok
        handoff = proposal_service.create_manual_commercial_handoff(
            proposal_preparation_id=approved.proposal.proposal_preparation_id,
            operator_id=f"operator-handoff-{suffix}",
            repo_root=repo,
            recorded_at="2026-07-10",
        )
        assert handoff.ok
        presentation = acceptance_service.record_manual_proposal_presentation(
            proposal_preparation_id=approved.proposal.proposal_preparation_id,
            commercial_handoff_package_id=handoff.handoff.handoff_id,
            presentation_channel="VIDEO_CALL",
            presentation_date="2026-07-12",
            presented_by_operator_id=f"operator-presenter-{suffix}",
            evidence_reference=f"presentation-evidence-{suffix}",
            customer_participant_reference=f"customer-contact-{suffix}",
            operator_note="Manual presentation completed.",
            manual_action_confirmed=True,
            repo_root=repo,
            recorded_at="2026-07-12",
        )
        assert presentation.ok
        decision = acceptance_service.record_customer_commercial_decision(
            presentation_record_id=presentation.presentation.presentation_record_id,
            decision_type="ACCEPTED",
            decision_date="2026-07-13",
            recorded_by_operator_id=f"operator-decision-{suffix}",
            evidence_reference=f"acceptance-evidence-{suffix}",
            approved_proposal_content_hash=approved.proposal.deterministic_content_hash,
            customer_decision_reference=f"customer-decision-ref-{suffix}",
            accepted_total="1000.00",
            accepted_currency="USD",
            accepted_scope_hash=approved.proposal.commercial_scope_id,
            accepted_payment_terms=approved.proposal.payment_terms,
            accepted_revision_terms=approved.proposal.revision_terms,
            accepted_tax="0.00",
            accepted_discount="0.00",
            repo_root=repo,
            recorded_at="2026-07-13",
        )
        assert decision.ok
        return repo, approved.proposal, handoff.handoff, presentation.presentation, decision.decision, decision.acceptance

    return build


def test_create_activation_reverifies_acceptance_lineage_and_preserves_boundaries(accepted_source):
    repo, proposal, handoff, presentation, decision, acceptance = accepted_source
    acceptance_events_before = read_commercial_acceptance_events(audit_log_path=commercial_acceptance_path(repo))

    result = _activation(repo, acceptance)

    assert result.ok
    activation = result.activation
    assert activation.source_commercial_acceptance_id == acceptance.commercial_acceptance_id
    assert activation.source_proposal_preparation_id == proposal.proposal_preparation_id
    assert activation.source_proposal_content_hash == proposal.deterministic_content_hash
    assert activation.source_commercial_handoff_id == handoff.handoff_id
    assert activation.source_presentation_record_id == presentation.presentation_record_id
    assert activation.source_customer_decision_id == decision.customer_decision_id
    assert activation.source_delivery_record_id == proposal.source_delivery_record_id
    assert activation.source_artifact_sha256 == proposal.source_artifact_sha256
    assert activation.accepted_total_amount == proposal.total_amount
    assert activation.payment_start_requirement == PAYMENT_REQUIREMENT_UNKNOWN
    assert activation.automation_allowed is False
    assert activation.project_created is False
    assert activation.hvs_invoked is False
    assert activation.render_started is False
    assert activation.assets_copied is False
    assert activation.invoice_issued is False
    assert activation.payment_link_created is False
    assert activation.payment_processed is False
    assert read_commercial_acceptance_events(audit_log_path=commercial_acceptance_path(repo)) == acceptance_events_before


@pytest.mark.parametrize(
    ("mutation", "expected_blocker"),
    [
        ("acceptance_not_verified", "COMMERCIAL_ACCEPTANCE_NOT_VERIFIED"),
        ("acceptance_not_ready", "ACCEPTANCE_NOT_READY_FOR_MANUAL_PROJECT_KICKOFF"),
        ("acceptance_external_flag", "ACCEPTANCE_EXTERNAL_ACTION_FLAG_SET"),
        ("proposal_missing", "PROPOSAL_NOT_FOUND"),
        ("handoff_missing", "HANDOFF_NOT_FOUND"),
        ("presentation_missing", "PRESENTATION_NOT_FOUND"),
        ("decision_missing", "CUSTOMER_DECISION_NOT_FOUND"),
        ("proposal_unapproved", "PROPOSAL_NOT_APPROVED_FOR_MANUAL_PRESENTATION"),
        ("proposal_cancelled", "PROPOSAL_NOT_APPROVED_FOR_MANUAL_PRESENTATION"),
        ("proposal_hash", "PROPOSAL_CONTENT_HASH_MISMATCH"),
        ("proposal_scope", "COMMERCIAL_SCOPE_MISMATCH"),
        ("project_id", "PROJECT_ID_MISMATCH"),
        ("customer_reference", "CUSTOMER_REFERENCE_MISMATCH"),
        ("delivery_lineage", "DELIVERY_LINEAGE_MISMATCH"),
        ("artifact_sha", "ARTIFACT_LINEAGE_MISMATCH"),
        ("accepted_total", "ACCEPTED_TOTAL_OR_CURRENCY_MISMATCH"),
        ("accepted_currency", "ACCEPTED_TOTAL_OR_CURRENCY_MISMATCH"),
        ("price_component", "ACCEPTED_PRICE_COMPONENT_MISMATCH"),
        ("payment_terms", "ACCEPTED_PAYMENT_TERMS_MISMATCH"),
        ("revision_terms", "ACCEPTED_REVISION_TERMS_MISMATCH"),
        ("proposal_expired_on_decision", "PROPOSAL_NOT_VALID_ON_DECISION_DATE"),
        ("handoff_id", "HANDOFF_ID_MISMATCH"),
        ("handoff_hash", "HANDOFF_CONTENT_HASH_MISMATCH"),
        ("handoff_external_flag", "HANDOFF_EXTERNAL_ACTION_FLAG_SET"),
        ("presentation_not_manual", "PRESENTATION_NOT_MANUAL"),
        ("presentation_hash", "PRESENTATION_CONTENT_HASH_MISMATCH"),
        ("presentation_external_flag", "PRESENTATION_EXTERNAL_ACTION_FLAG_SET"),
        ("decision_not_accepted", "CUSTOMER_DECISION_NOT_ACCEPTED"),
        ("decision_presentation", "CUSTOMER_DECISION_PRESENTATION_MISMATCH"),
        ("decision_hash", "CUSTOMER_DECISION_CONTENT_HASH_MISMATCH"),
        ("decision_total", "CUSTOMER_DECISION_TOTAL_OR_CURRENCY_MISMATCH"),
        ("decision_currency", "CUSTOMER_DECISION_TOTAL_OR_CURRENCY_MISMATCH"),
        ("decision_scope", "CUSTOMER_DECISION_SCOPE_MISMATCH"),
        ("decision_external_flag", "CUSTOMER_DECISION_EXTERNAL_ACTION_FLAG_SET"),
        ("conflicting_acceptance", "CONFLICTING_COMMERCIAL_ACCEPTANCE"),
    ],
)
def test_eligibility_rejects_specific_source_contract_gaps_without_side_effects(accepted_source, monkeypatch, mutation, expected_blocker):
    repo, proposal, handoff, presentation, decision, acceptance = accepted_source
    acceptance_events_before = read_commercial_acceptance_events(audit_log_path=commercial_acceptance_path(repo))
    proposal_records_before = proposal_service._records(repo)
    patch_acceptance = acceptance
    patch_proposal = proposal
    patch_handoff = handoff
    patch_presentation = presentation
    patch_decision = decision

    if mutation == "acceptance_not_verified":
        patch_acceptance = replace(acceptance, acceptance_status="ACCEPTANCE_BLOCKED")
    elif mutation == "acceptance_not_ready":
        patch_acceptance = replace(acceptance, ready_for_manual_project_kickoff=False)
    elif mutation == "acceptance_external_flag":
        patch_acceptance = replace(acceptance, hvs_invoked=True)
    elif mutation == "proposal_missing":
        monkeypatch.setattr(service, "_records", lambda _repo: {})
    elif mutation == "handoff_missing":
        monkeypatch.setattr(service, "_handoffs", lambda _repo: {})
    elif mutation == "presentation_missing":
        monkeypatch.setattr(service, "_presentations", lambda _repo: {})
    elif mutation == "decision_missing":
        monkeypatch.setattr(service, "_decisions", lambda _repo: {})
    elif mutation == "proposal_unapproved":
        patch_proposal = replace(proposal, proposal_status="DRAFT")
    elif mutation == "proposal_cancelled":
        patch_proposal = replace(proposal, proposal_status="CANCELLED")
    elif mutation == "proposal_hash":
        patch_proposal = replace(proposal, deterministic_content_hash="f" * 64)
    elif mutation == "proposal_scope":
        patch_proposal = replace(proposal, commercial_scope_id="other-scope")
    elif mutation == "project_id":
        patch_proposal = replace(proposal, project_id="other-project")
    elif mutation == "customer_reference":
        patch_proposal = replace(proposal, customer_reference="other-customer")
    elif mutation == "delivery_lineage":
        patch_proposal = replace(proposal, source_delivery_lineage_id="other-lineage")
    elif mutation == "artifact_sha":
        patch_proposal = replace(proposal, source_artifact_sha256="0" * 64)
    elif mutation == "accepted_total":
        patch_proposal = replace(proposal, total_amount=Decimal("999.99"))
    elif mutation == "accepted_currency":
        patch_proposal = replace(proposal, currency="EUR")
    elif mutation == "price_component":
        patch_proposal = replace(proposal, tax_amount=Decimal("1.00"))
    elif mutation == "payment_terms":
        patch_proposal = replace(proposal, payment_terms="Different terms.")
    elif mutation == "revision_terms":
        patch_proposal = replace(proposal, revision_terms="Different revision terms.")
    elif mutation == "proposal_expired_on_decision":
        patch_proposal = replace(proposal, validity_end_date="2026-07-12")
    elif mutation == "handoff_id":
        patch_handoff = replace(handoff, handoff_id="other-handoff")
    elif mutation == "handoff_hash":
        patch_handoff = replace(handoff, approved_content_hash="e" * 64)
    elif mutation == "handoff_external_flag":
        patch_handoff = replace(handoff, payment_link_created=True)
    elif mutation == "presentation_not_manual":
        patch_presentation = replace(presentation, manual_action_confirmed=False)
    elif mutation == "presentation_hash":
        patch_presentation = replace(presentation, approved_proposal_content_hash="d" * 64)
    elif mutation == "presentation_external_flag":
        patch_presentation = replace(presentation, automation_allowed=True)
    elif mutation == "decision_not_accepted":
        patch_decision = replace(decision, decision_type="REJECTED")
    elif mutation == "decision_presentation":
        patch_decision = replace(decision, presentation_record_id="other-presentation")
    elif mutation == "decision_hash":
        patch_decision = replace(decision, approved_proposal_content_hash="c" * 64)
    elif mutation == "decision_total":
        patch_decision = replace(decision, accepted_total=Decimal("999.99"))
    elif mutation == "decision_currency":
        patch_decision = replace(decision, accepted_currency="EUR")
    elif mutation == "decision_scope":
        patch_decision = replace(decision, accepted_scope_hash="other-scope")
    elif mutation == "decision_external_flag":
        patch_decision = replace(decision, customer_contact_performed_by_system=True)
    elif mutation == "conflicting_acceptance":
        other = replace(acceptance, commercial_acceptance_id="other-acceptance")
        monkeypatch.setattr(service, "_acceptances", lambda _repo: {acceptance.commercial_acceptance_id: acceptance, other.commercial_acceptance_id: other})

    if mutation not in ("proposal_missing",):
        monkeypatch.setattr(service, "_records", lambda _repo: {proposal.proposal_preparation_id: patch_proposal})
    if mutation not in ("handoff_missing",):
        monkeypatch.setattr(service, "_handoffs", lambda _repo: {proposal.proposal_preparation_id: patch_handoff})
    if mutation not in ("presentation_missing",):
        monkeypatch.setattr(service, "_presentations", lambda _repo: {presentation.presentation_record_id: patch_presentation})
    if mutation not in ("decision_missing",):
        monkeypatch.setattr(service, "_decisions", lambda _repo: {decision.customer_decision_id: patch_decision})
    if mutation != "conflicting_acceptance":
        monkeypatch.setattr(service, "_acceptances", lambda _repo: {acceptance.commercial_acceptance_id: patch_acceptance})

    result = _activation(repo, acceptance)

    assert not result.ok
    assert result.error_code == "ACCEPTANCE_INELIGIBLE"
    assert expected_blocker in result.blockers
    assert read_engagement_activation_events(audit_log_path=engagement_activation_path(repo)) == ()
    assert read_commercial_acceptance_events(audit_log_path=commercial_acceptance_path(repo)) == acceptance_events_before
    assert proposal_service._records(repo) == proposal_records_before


def test_activation_rejects_invalid_lineage_without_writing_stage8k(accepted_source, monkeypatch):
    repo, proposal, _handoff, _presentation, _decision, acceptance = accepted_source
    monkeypatch.setattr(service, "_records", lambda _repo: {proposal.proposal_preparation_id: replace(proposal, deterministic_content_hash="f" * 64)})

    result = _activation(repo, acceptance)

    assert not result.ok
    assert result.error_code == "ACCEPTANCE_INELIGIBLE"
    assert "PROPOSAL_CONTENT_HASH_MISMATCH" in result.blockers
    assert read_engagement_activation_events(audit_log_path=engagement_activation_path(repo)) == ()


def test_activation_replay_is_idempotent_only_for_same_semantic_content(accepted_source):
    repo, _proposal, _handoff, _presentation, _decision, acceptance = accepted_source
    first = _activation(repo, acceptance)
    replay = _activation(repo, acceptance, recorded_at="2026-07-15")
    changed_schedule = _activation(repo, acceptance, target_completion_date="2026-08-01")

    assert first.ok
    assert replay.ok
    assert replay.duplicate_of == first.activation.engagement_activation_id
    assert replay.activation.deterministic_content_hash == first.activation.deterministic_content_hash
    assert not changed_schedule.ok
    assert changed_schedule.error_code == "ACTIVATION_CONFLICT"
    assert "ACTIVATION_CONFLICT" in changed_schedule.blockers
    assert len(read_engagement_activation_events(audit_log_path=engagement_activation_path(repo))) == 1


@pytest.mark.parametrize(
    ("field", "value", "fragment"),
    [
        ("target_start_date", "not-a-date", "ISO calendar date"),
        ("target_completion_date", "2026-02-30", "ISO calendar date"),
        ("target_completion_date", "2026-07-19", "target_start_date must be on or before target_completion_date"),
        ("recorded_at", "2026-02-30", "ISO calendar date"),
        ("production_dependency_notes", ("unsafe\nnote",), "contains unsafe text"),
        ("operator_id", "", "operator_id is required"),
    ],
)
def test_activation_schedule_and_text_inputs_are_explicit_and_safe(accepted_source, field, value, fragment):
    repo, _proposal, _handoff, _presentation, _decision, acceptance = accepted_source
    result = _activation(repo, acceptance, **{field: value})

    assert not result.ok
    assert result.error_code == "INVALID_INPUT"
    assert fragment in result.error_detail
    assert read_engagement_activation_events(audit_log_path=engagement_activation_path(repo)) == ()


def test_activation_optional_schedule_is_not_inferred_and_unicode_is_preserved(accepted_source):
    repo, _proposal, _handoff, _presentation, _decision, acceptance = accepted_source
    result = _activation(
        repo,
        acceptance,
        target_start_date=None,
        target_completion_date=None,
        production_dependency_notes=("オペレーター確認済み",),
        production_risk_notes=("Brand nuance ✓",),
    )

    assert result.ok
    assert result.activation.target_start_date is None
    assert result.activation.target_completion_date is None
    assert "オペレーター確認済み" in result.activation.production_dependency_notes
    assert result.activation.manual_project_initialization_required is True
    assert result.activation.automation_allowed is False


@pytest.mark.parametrize(
    ("requirement", "amount", "currency", "ok", "fragment"),
    [
        (PAYMENT_NOT_REQUIRED_BEFORE_START, None, None, True, None),
        (DEPOSIT_REQUIRED_BEFORE_START, "250.00", "USD", True, None),
        (DEPOSIT_REQUIRED_BEFORE_START, "0.00", "USD", False, "deposit amount"),
        (DEPOSIT_REQUIRED_BEFORE_START, "1250.00", "USD", False, "must not exceed"),
        (DEPOSIT_REQUIRED_BEFORE_START, "250.00", "EUR", False, "match accepted currency"),
        ("FULL_PAYMENT_REQUIRED_BEFORE_START", "999.99", "USD", False, "must equal accepted total"),
        ("FULL_PAYMENT_REQUIRED_BEFORE_START", "1000.00", "USD", True, None),
        (PAYMENT_REQUIREMENT_UNKNOWN, None, None, True, None),
    ],
)
def test_payment_requirement_contract_uses_explicit_decimal_amounts_and_matching_currency(accepted_source, requirement, amount, currency, ok, fragment):
    repo, _proposal, _handoff, _presentation, _decision, acceptance = accepted_source
    activation = _activation(repo, acceptance).activation

    result = service.record_payment_start_requirement(
        engagement_activation_id=activation.engagement_activation_id,
        payment_start_requirement=requirement,
        operator_id="operator-8k-payment",
        repo_root=repo,
        recorded_at="2026-07-14",
        required_payment_amount=amount,
        required_payment_currency=currency,
    )

    assert result.ok is ok
    if ok:
        assert result.activation.payment_start_requirement in (requirement, "FULL_PAYMENT_REQUIRED_BEFORE_START")
        assert result.activation.payment_processed is False
    else:
        assert fragment in result.error_detail


def test_payment_confirmation_requires_safe_operator_evidence_and_exact_terms(accepted_source):
    repo, _proposal, _handoff, _presentation, _decision, acceptance = accepted_source
    activation = _activation(repo, acceptance).activation
    payment = service.record_payment_start_requirement(
        engagement_activation_id=activation.engagement_activation_id,
        payment_start_requirement=DEPOSIT_REQUIRED_BEFORE_START,
        required_payment_amount="250.00",
        required_payment_currency="USD",
        operator_id="operator-8k-payment",
        repo_root=repo,
        recorded_at="2026-07-14",
    ).activation

    mismatch = service.confirm_payment_readiness(
        engagement_activation_id=payment.engagement_activation_id,
        operator_id="operator-8k-payment",
        evidence_reference="evidence-deposit-8k",
        confirmed_amount="200.00",
        confirmed_currency="USD",
        confirmation_date="2026-07-14",
        repo_root=repo,
        recorded_at="2026-07-14",
    )
    unsafe = service.confirm_payment_readiness(
        engagement_activation_id=payment.engagement_activation_id,
        operator_id="operator-8k-payment",
        evidence_reference="secret-token-payment",
        confirmed_amount="250.00",
        confirmed_currency="USD",
        confirmation_date="2026-07-14",
        repo_root=repo,
        recorded_at="2026-07-14",
    )
    confirmed = service.confirm_payment_readiness(
        engagement_activation_id=payment.engagement_activation_id,
        operator_id="operator-8k-payment",
        evidence_reference="evidence-deposit-8k",
        confirmed_amount="250.00",
        confirmed_currency="USD",
        confirmation_date="2026-07-14",
        repo_root=repo,
        recorded_at="2026-07-14",
    )

    assert mismatch.error_code == "PAYMENT_CONFIRMATION_MISMATCH"
    assert unsafe.error_code == "INVALID_INPUT"
    assert confirmed.ok
    assert confirmed.activation.payment_processed is False
    assert confirmed.activation.payment_evidence_reference == "evidence-deposit-8k"


@pytest.mark.parametrize(
    ("kwargs", "code", "fragment"),
    [
        ({"operator_id": ""}, "INVALID_INPUT", "operator_id is required"),
        ({"evidence_reference": ""}, "INVALID_INPUT", "evidence_reference is required"),
        ({"evidence_reference": "card-number-4111111111111111"}, "INVALID_INPUT", "secrets"),
        ({"evidence_reference": "bank-login-reference"}, "INVALID_INPUT", "secrets"),
        ({"evidence_reference": "provider-reference"}, "INVALID_INPUT", "secrets"),
        ({"evidence_reference": "https://provider.example/evidence"}, "INVALID_INPUT", "provider data"),
        ({"confirmed_amount": "200.00"}, "PAYMENT_CONFIRMATION_MISMATCH", "match declared amount"),
        ({"confirmed_amount": "NaN"}, "INVALID_INPUT", "finite"),
        ({"confirmed_amount": "Infinity"}, "INVALID_INPUT", "finite"),
        ({"confirmed_amount": 250.0}, "INVALID_INPUT", "must not be a float"),
        ({"confirmed_currency": "EUR"}, "PAYMENT_CONFIRMATION_MISMATCH", "match declared amount"),
        ({"confirmation_date": "2026-02-30"}, "INVALID_INPUT", "ISO calendar date"),
    ],
)
def test_payment_confirmation_rejects_unsafe_or_mismatched_confirmation_inputs(accepted_source, kwargs, code, fragment):
    repo, _proposal, _handoff, _presentation, _decision, acceptance = accepted_source
    activation = _activation(repo, acceptance).activation
    payment = service.record_payment_start_requirement(
        engagement_activation_id=activation.engagement_activation_id,
        payment_start_requirement=DEPOSIT_REQUIRED_BEFORE_START,
        required_payment_amount="250.00",
        required_payment_currency="USD",
        operator_id="operator-8k-payment",
        repo_root=repo,
        recorded_at="2026-07-14",
    ).activation
    data = {
        "engagement_activation_id": payment.engagement_activation_id,
        "operator_id": "operator-8k-payment",
        "evidence_reference": "evidence-deposit-8k",
        "confirmed_amount": "250.00",
        "confirmed_currency": "USD",
        "confirmation_date": "2026-07-14",
        "repo_root": repo,
        "recorded_at": "2026-07-14",
    }
    data.update(kwargs)

    before = read_engagement_activation_events(audit_log_path=engagement_activation_path(repo))
    result = service.confirm_payment_readiness(**data)

    assert not result.ok
    assert result.error_code == code
    assert fragment in result.error_detail
    assert read_engagement_activation_events(audit_log_path=engagement_activation_path(repo)) == before


def test_readiness_waits_for_explicit_customer_input_and_then_becomes_ready(accepted_source):
    repo, _proposal, _handoff, _presentation, _decision, acceptance = accepted_source
    activation = _activation(repo, acceptance).activation
    assert service.record_payment_start_requirement(
        engagement_activation_id=activation.engagement_activation_id,
        payment_start_requirement=PAYMENT_NOT_REQUIRED_BEFORE_START,
        operator_id="operator-8k-payment",
        repo_root=repo,
        recorded_at="2026-07-14",
    ).ok
    requirement = service.add_customer_input_requirement(
        engagement_activation_id=activation.engagement_activation_id,
        requirement_type=INPUT_FINAL_PRODUCTION_BRIEF,
        description="Final production brief.",
        operator_id="operator-8k-input",
        repo_root=repo,
        recorded_at="2026-07-14",
    )
    pending = service.evaluate_engagement_readiness(
        engagement_activation_id=activation.engagement_activation_id,
        repo_root=repo,
        evaluation_date="2026-07-14",
    )

    assert pending.readiness_status == READINESS_WAITING_FOR_CUSTOMER_INPUT
    assert service.request_production_review(
        engagement_activation_id=activation.engagement_activation_id,
        operator_id="operator-8k-review",
        repo_root=repo,
        recorded_at="2026-07-14",
        evaluation_date="2026-07-14",
    ).error_code == "READINESS_BLOCKED"

    confirmed = service.confirm_customer_input_requirement(
        engagement_activation_id=activation.engagement_activation_id,
        customer_input_requirement_id=requirement.activation.customer_input_requirements[0].customer_input_requirement_id,
        operator_id="operator-8k-input",
        evidence_reference="evidence-final-brief-8k",
        confirmation_date="2026-07-14",
        repo_root=repo,
        recorded_at="2026-07-14",
    )
    ready = service.evaluate_engagement_readiness(
        engagement_activation_id=activation.engagement_activation_id,
        repo_root=repo,
        evaluation_date="2026-07-14",
    )

    assert confirmed.ok
    assert ready.readiness_status == READINESS_READY
    assert ready.ready_for_production_review is True
    assert ready.project_created is False
    assert ready.payment_processed is False


@pytest.mark.parametrize("requirement_type", models.ALLOWED_CUSTOMER_INPUT_TYPES)
def test_all_implemented_customer_input_types_are_explicit_deterministic_and_unicode_safe(accepted_source, requirement_type):
    repo, _proposal, _handoff, _presentation, _decision, acceptance = accepted_source
    activation = _activation(repo, acceptance).activation
    first = service.add_customer_input_requirement(
        engagement_activation_id=activation.engagement_activation_id,
        requirement_type=requirement_type,
        description=f"Explicit input {requirement_type} ✓",
        operator_id="operator-8k-input",
        repo_root=repo,
        recorded_at="2026-07-14",
    )
    replay = service.add_customer_input_requirement(
        engagement_activation_id=activation.engagement_activation_id,
        requirement_type=requirement_type.lower().replace("_", "-"),
        description=f"Explicit input {requirement_type} ✓",
        operator_id="operator-8k-input",
        repo_root=repo,
        recorded_at="2026-07-14",
    )

    assert first.ok
    requirement = first.activation.customer_input_requirements[0]
    assert requirement.requirement_type == requirement_type
    assert requirement.input_status == models.INPUT_PENDING
    assert "✓" in requirement.description
    assert replay.ok
    assert replay.duplicate_of == requirement.customer_input_requirement_id


@pytest.mark.parametrize(
    ("kwargs", "fragment"),
    [
        ({"requirement_type": "BRAND_LOGO"}, "unsupported"),
        ({"description": ""}, "description is required"),
        ({"description": "unsafe\ninput"}, "contains unsafe text"),
        ({"description": "../input"}, "contains unsafe text"),
        ({"required": "yes"}, "required must be boolean"),
    ],
)
def test_customer_input_requirement_rejects_unsupported_or_unsafe_inputs(accepted_source, kwargs, fragment):
    repo, _proposal, _handoff, _presentation, _decision, acceptance = accepted_source
    activation = _activation(repo, acceptance).activation
    data = {
        "engagement_activation_id": activation.engagement_activation_id,
        "requirement_type": INPUT_FINAL_PRODUCTION_BRIEF,
        "description": "Final production brief.",
        "operator_id": "operator-8k-input",
        "repo_root": repo,
        "recorded_at": "2026-07-14",
    }
    data.update(kwargs)
    result = service.add_customer_input_requirement(**data)

    assert not result.ok
    assert result.error_code == "INVALID_INPUT"
    assert fragment in result.error_detail


@pytest.mark.parametrize(
    ("kwargs", "code", "fragment"),
    [
        ({"operator_id": ""}, "INVALID_INPUT", "operator_id is required"),
        ({"evidence_reference": ""}, "INVALID_INPUT", "evidence_reference is required"),
        ({"evidence_reference": "raw-media-bytes"}, "INVALID_INPUT", "private media"),
        ({"evidence_reference": "secret-token-input"}, "INVALID_INPUT", "secrets"),
        ({"confirmation_date": "not-a-date"}, "INVALID_INPUT", "ISO calendar date"),
        ({"customer_input_requirement_id": "missing"}, "CUSTOMER_INPUT_REQUIREMENT_NOT_FOUND", "not found"),
    ],
)
def test_customer_input_confirmation_requires_safe_operator_evidence_and_valid_requirement(accepted_source, kwargs, code, fragment):
    repo, _proposal, _handoff, _presentation, _decision, acceptance = accepted_source
    activation = _activation(repo, acceptance).activation
    requirement = service.add_customer_input_requirement(
        engagement_activation_id=activation.engagement_activation_id,
        requirement_type=INPUT_FINAL_PRODUCTION_BRIEF,
        description="Final production brief.",
        operator_id="operator-8k-input",
        repo_root=repo,
        recorded_at="2026-07-14",
    ).activation.customer_input_requirements[0]
    data = {
        "engagement_activation_id": activation.engagement_activation_id,
        "customer_input_requirement_id": requirement.customer_input_requirement_id,
        "operator_id": "operator-8k-input",
        "evidence_reference": "evidence-final-brief-8k",
        "confirmation_date": "2026-07-14",
        "repo_root": repo,
        "recorded_at": "2026-07-14",
    }
    data.update(kwargs)
    before = read_engagement_activation_events(audit_log_path=engagement_activation_path(repo))
    result = service.confirm_customer_input_requirement(**data)

    assert not result.ok
    assert result.error_code == code
    assert fragment in result.error_detail
    assert read_engagement_activation_events(audit_log_path=engagement_activation_path(repo)) == before


def test_multiple_customer_inputs_all_must_be_satisfied_for_readiness(accepted_source):
    repo, _proposal, _handoff, _presentation, _decision, acceptance = accepted_source
    activation = _activation(repo, acceptance).activation
    assert service.record_payment_start_requirement(
        engagement_activation_id=activation.engagement_activation_id,
        payment_start_requirement=PAYMENT_NOT_REQUIRED_BEFORE_START,
        operator_id="operator-8k-payment",
        repo_root=repo,
        recorded_at="2026-07-14",
    ).ok
    first = service.add_customer_input_requirement(
        engagement_activation_id=activation.engagement_activation_id,
        requirement_type=models.INPUT_FINAL_PRODUCTION_BRIEF,
        description="Final production brief.",
        operator_id="operator-8k-input",
        repo_root=repo,
        recorded_at="2026-07-14",
    ).activation.customer_input_requirements[0]
    second = service.add_customer_input_requirement(
        engagement_activation_id=activation.engagement_activation_id,
        requirement_type=models.INPUT_BRAND_GUIDELINES,
        description="Brand guidelines.",
        operator_id="operator-8k-input",
        repo_root=repo,
        recorded_at="2026-07-14",
    ).activation.customer_input_requirements
    second = next(item for item in second if item.customer_input_requirement_id != first.customer_input_requirement_id)

    assert service.confirm_customer_input_requirement(
        engagement_activation_id=activation.engagement_activation_id,
        customer_input_requirement_id=first.customer_input_requirement_id,
        operator_id="operator-8k-input",
        evidence_reference="evidence-final-brief-8k",
        confirmation_date="2026-07-14",
        repo_root=repo,
        recorded_at="2026-07-14",
    ).ok
    pending = service.evaluate_engagement_readiness(engagement_activation_id=activation.engagement_activation_id, repo_root=repo, evaluation_date="2026-07-14")
    assert pending.readiness_status == READINESS_WAITING_FOR_CUSTOMER_INPUT

    assert service.confirm_customer_input_requirement(
        engagement_activation_id=activation.engagement_activation_id,
        customer_input_requirement_id=second.customer_input_requirement_id,
        operator_id="operator-8k-input",
        evidence_reference="evidence-brand-guidelines-8k",
        confirmation_date="2026-07-14",
        repo_root=repo,
        recorded_at="2026-07-14",
    ).ok
    ready = service.evaluate_engagement_readiness(engagement_activation_id=activation.engagement_activation_id, repo_root=repo, evaluation_date="2026-07-14")
    assert ready.readiness_status == READINESS_READY


def test_deposit_required_engagement_waits_for_payment_then_authorizes_without_payment_provider(accepted_source):
    repo, _proposal, _handoff, _presentation, _decision, acceptance = accepted_source
    activation = _activation(repo, acceptance).activation
    payment = service.record_payment_start_requirement(
        engagement_activation_id=activation.engagement_activation_id,
        payment_start_requirement=DEPOSIT_REQUIRED_BEFORE_START,
        required_payment_amount="250.00",
        required_payment_currency="USD",
        operator_id="operator-8k-payment",
        repo_root=repo,
        recorded_at="2026-07-14",
    )
    waiting = service.evaluate_engagement_readiness(
        engagement_activation_id=activation.engagement_activation_id,
        repo_root=repo,
        evaluation_date="2026-07-14",
    )

    assert payment.ok
    assert waiting.readiness_status == READINESS_WAITING_FOR_PAYMENT
    assert service.confirm_payment_readiness(
        engagement_activation_id=activation.engagement_activation_id,
        operator_id="operator-8k-payment",
        evidence_reference="evidence-deposit-8k",
        confirmed_amount="250.00",
        confirmed_currency="USD",
        confirmation_date="2026-07-14",
        repo_root=repo,
        recorded_at="2026-07-14",
    ).ok
    ready_activation = _make_ready_no_payment(repo, activation.engagement_activation_id)
    review = service.request_production_review(
        engagement_activation_id=ready_activation.engagement_activation_id,
        operator_id="operator-8k-review",
        repo_root=repo,
        recorded_at="2026-07-14",
        evaluation_date="2026-07-14",
    )
    approved = service.decide_engagement_activation(
        engagement_activation_id=ready_activation.engagement_activation_id,
        decision="approve",
        operator_id="operator-8k-approver",
        repo_root=repo,
        recorded_at="2026-07-14",
    )
    authorization = service.create_production_kickoff_authorization(
        engagement_activation_id=ready_activation.engagement_activation_id,
        operator_id="operator-8k-approver",
        repo_root=repo,
        recorded_at="2026-07-14",
    )

    assert review.ok
    assert approved.ok
    assert authorization.ok
    assert authorization.authorization.project_initialization_authorized is True
    assert authorization.authorization.project_initialization_performed is False
    assert authorization.authorization.payment_processed is False
    assert authorization.authorization.hvs_invoked is False
    assert authorization.authorization.render_started is False
    assert authorization.authorization.customer_contact_performed_by_system is False


def test_authorization_preserves_lineage_terms_and_approval_event(accepted_source):
    repo, proposal, _handoff, presentation, decision, acceptance = accepted_source
    activation = _activation(repo, acceptance).activation
    ready = _make_ready_no_payment(repo, activation.engagement_activation_id)
    assert service.request_production_review(
        engagement_activation_id=ready.engagement_activation_id,
        operator_id="operator-8k-review",
        repo_root=repo,
        recorded_at="2026-07-14",
        evaluation_date="2026-07-14",
    ).ok
    approved = service.decide_engagement_activation(
        engagement_activation_id=ready.engagement_activation_id,
        decision="approve",
        operator_id="operator-8k-approver",
        repo_root=repo,
        recorded_at="2026-07-14",
    )
    authorization = service.create_production_kickoff_authorization(
        engagement_activation_id=ready.engagement_activation_id,
        operator_id="operator-8k-approver",
        repo_root=repo,
        recorded_at="2026-07-14",
    ).authorization

    assert authorization.engagement_content_hash == approved.activation.deterministic_content_hash
    assert authorization.approval_event_id == approved.activation.approval_event_id
    assert authorization.source_commercial_acceptance_id == acceptance.commercial_acceptance_id
    assert authorization.source_proposal_preparation_id == proposal.proposal_preparation_id
    assert authorization.source_presentation_record_id == presentation.presentation_record_id
    assert authorization.source_customer_decision_id == decision.customer_decision_id
    assert authorization.source_opportunity_id == acceptance.opportunity_id
    assert authorization.source_delivery_lineage_id == acceptance.source_delivery_lineage_id
    assert authorization.source_delivery_record_id == proposal.source_delivery_record_id
    assert authorization.source_artifact_sha256 == acceptance.source_artifact_sha256
    assert authorization.accepted_total_amount == acceptance.accepted_total
    assert authorization.accepted_currency == acceptance.accepted_currency
    assert authorization.payment_start_requirement == PAYMENT_NOT_REQUIRED_BEFORE_START
    assert authorization.customer_input_status == models.INPUT_SATISFIED_BY_OPERATOR_CONFIRMATION
    assert authorization.project_initialization_authorized is True
    assert authorization.project_initialization_performed is False


def test_unknown_payment_policy_blocks_review_and_authorization(accepted_source):
    repo, _proposal, _handoff, _presentation, _decision, acceptance = accepted_source
    activation = _activation(repo, acceptance).activation

    readiness = service.evaluate_engagement_readiness(
        engagement_activation_id=activation.engagement_activation_id,
        repo_root=repo,
        evaluation_date="2026-07-14",
    )
    review = service.request_production_review(
        engagement_activation_id=activation.engagement_activation_id,
        operator_id="operator-8k-review",
        repo_root=repo,
        recorded_at="2026-07-14",
        evaluation_date="2026-07-14",
    )
    authorization = service.create_production_kickoff_authorization(
        engagement_activation_id=activation.engagement_activation_id,
        operator_id="operator-8k-approver",
        repo_root=repo,
        recorded_at="2026-07-14",
    )

    assert readiness.readiness_status == "NEEDS_OPERATOR_INPUT"
    assert "PAYMENT_REQUIREMENT_UNKNOWN" in readiness.blockers
    assert review.error_code == "READINESS_BLOCKED"
    assert authorization.error_code == "APPROVAL_REQUIRED"


def test_terminal_rejected_cancelled_and_expired_activations_cannot_authorize(accepted_source_factory, monkeypatch):
    rejected = accepted_source_factory("reject")
    repo, _proposal, _handoff, _presentation, _decision, acceptance = rejected
    rejected_activation = _activation(repo, acceptance).activation
    reject = service.decide_engagement_activation(
        engagement_activation_id=rejected_activation.engagement_activation_id,
        decision="reject",
        operator_id="operator-8k-reject",
        reason="Operator rejected initialization.",
        repo_root=repo,
        recorded_at="2026-07-14",
    )
    assert reject.ok
    assert service.create_production_kickoff_authorization(
        engagement_activation_id=rejected_activation.engagement_activation_id,
        operator_id="operator-8k-reject",
        repo_root=repo,
        recorded_at="2026-07-14",
    ).error_code == "APPROVAL_REQUIRED"

    cancelled = accepted_source_factory("cancel")
    cancel_activation = _activation(repo, cancelled[-1]).activation
    cancel = service.decide_engagement_activation(
        engagement_activation_id=cancel_activation.engagement_activation_id,
        decision="cancel",
        operator_id="operator-8k-cancel",
        reason="Operator cancelled initialization.",
        repo_root=repo,
        recorded_at="2026-07-14",
    )
    assert cancel.ok
    assert service.decide_engagement_activation(
        engagement_activation_id=cancel_activation.engagement_activation_id,
        decision="approve",
        operator_id="operator-8k-cancel",
        repo_root=repo,
        recorded_at="2026-07-14",
    ).error_code == "ACTIVATION_TERMINAL"

    expired = accepted_source_factory("expire")
    expired_activation = replace(_activation(repo, expired[-1]).activation, engagement_status=models.EXPIRED)
    monkeypatch.setattr(service, "_activations", lambda _repo: {expired_activation.engagement_activation_id: expired_activation})
    assert service.decide_engagement_activation(
        engagement_activation_id=expired_activation.engagement_activation_id,
        decision="approve",
        operator_id="operator-8k-expire",
        repo_root=repo,
        recorded_at="2026-07-14",
    ).error_code == "ACTIVATION_TERMINAL"
    assert service.evaluate_engagement_readiness(
        engagement_activation_id=expired_activation.engagement_activation_id,
        repo_root=repo,
        evaluation_date="2026-07-14",
    ).readiness_status == models.READINESS_EXPIRED


def test_review_approval_rejection_cancellation_and_authorization_idempotency(accepted_source):
    repo, _proposal, _handoff, _presentation, _decision, acceptance = accepted_source
    activation = _activation(repo, acceptance).activation
    ready = _make_ready_no_payment(repo, activation.engagement_activation_id)

    review = service.request_production_review(
        engagement_activation_id=ready.engagement_activation_id,
        operator_id="operator-8k-review",
        repo_root=repo,
        recorded_at="2026-07-14",
        evaluation_date="2026-07-14",
    )
    missing_operator = service.decide_engagement_activation(
        engagement_activation_id=ready.engagement_activation_id,
        decision="approve",
        operator_id="",
        repo_root=repo,
        recorded_at="2026-07-14",
    )
    approved = service.decide_engagement_activation(
        engagement_activation_id=ready.engagement_activation_id,
        decision="approve",
        operator_id="operator-8k-approver",
        repo_root=repo,
        recorded_at="2026-07-14",
    )
    replay = service.decide_engagement_activation(
        engagement_activation_id=ready.engagement_activation_id,
        decision="approve",
        operator_id="operator-8k-approver",
        repo_root=repo,
        recorded_at="2026-07-14",
    )
    authorization = service.create_production_kickoff_authorization(
        engagement_activation_id=ready.engagement_activation_id,
        operator_id="operator-8k-approver",
        repo_root=repo,
        recorded_at="2026-07-14",
    )
    authorization_replay = service.create_production_kickoff_authorization(
        engagement_activation_id=ready.engagement_activation_id,
        operator_id="operator-8k-approver",
        repo_root=repo,
        recorded_at="2026-07-14",
    )

    assert review.ok
    assert missing_operator.error_code == "INVALID_INPUT"
    assert approved.ok
    assert approved.activation.engagement_status == APPROVED_FOR_PROJECT_INITIALIZATION
    assert replay.ok and replay.duplicate_of == ready.engagement_activation_id
    assert authorization.ok
    assert authorization_replay.ok
    assert authorization_replay.duplicate_of == authorization.authorization.production_kickoff_authorization_id

    rejected_source = accepted_source
    repo2, _proposal2, _handoff2, _presentation2, _decision2, acceptance2 = rejected_source
    other = _activation(repo2, acceptance2)
    assert other.ok and other.duplicate_of


def test_store_is_append_only_detects_malformed_events_and_rejects_path_traversal(accepted_source, tmp_path):
    repo, _proposal, _handoff, _presentation, _decision, acceptance = accepted_source
    activation = _activation(repo, acceptance).activation
    events = read_engagement_activation_events(audit_log_path=engagement_activation_path(repo))
    before = tuple(event.to_dict() for event in events)

    inspected = service.inspect_engagement_activation(engagement_activation_id=activation.engagement_activation_id, repo_root=repo)
    service.evaluate_engagement_readiness(engagement_activation_id=activation.engagement_activation_id, repo_root=repo, evaluation_date="2026-07-14")
    service.list_engagement_activation_queue(repo_root=repo, evaluation_date="2026-07-14")
    after = tuple(event.to_dict() for event in read_engagement_activation_events(audit_log_path=engagement_activation_path(repo)))

    assert inspected.ok
    assert before == after
    bad = tmp_path / "malformed.jsonl"
    bad.write_text("{not-json}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="malformed engagement activation event"):
        read_engagement_activation_events(audit_log_path=bad)
    with pytest.raises(ValueError, match="unsafe engagement activation store path"):
        read_engagement_activation_events(audit_log_path=Path("..") / "outside.jsonl")


def test_store_rejects_unknown_schema_duplicate_ids_and_preserves_unicode(accepted_source, tmp_path):
    repo, _proposal, _handoff, _presentation, _decision, acceptance = accepted_source
    activation = _activation(repo, acceptance, production_dependency_notes=("証跡",)).activation
    event = read_engagement_activation_events(audit_log_path=engagement_activation_path(repo))[0]
    assert "証跡" in json.dumps(event.record, ensure_ascii=False)

    unknown_type = tmp_path / "unknown-type.jsonl"
    unknown_payload = {**event.to_dict(), "event_type": "UNKNOWN_EVENT"}
    unknown_type.write_text(json.dumps(unknown_payload) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="malformed engagement activation event"):
        read_engagement_activation_events(audit_log_path=unknown_type)

    bad_schema = tmp_path / "bad-schema.jsonl"
    bad_schema.write_text(json.dumps({**event.to_dict(), "schema_version": "bad-schema"}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="malformed engagement activation event"):
        read_engagement_activation_events(audit_log_path=bad_schema)

    duplicate = tmp_path / "duplicate.jsonl"
    duplicate.write_text(json.dumps(event.to_dict()) + "\n" + json.dumps(event.to_dict()) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="conflicting engagement activation event"):
        read_engagement_activation_events(audit_log_path=duplicate)

    truncated = tmp_path / "truncated.jsonl"
    truncated.write_text(json.dumps(event.to_dict())[:-5] + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="malformed engagement activation event"):
        read_engagement_activation_events(audit_log_path=truncated)

    constructed = models.EngagementActivationEvent(
        ENGAGEMENT_ACTIVATION_EVENT_SCHEMA_VERSION,
        "event-id-8k",
        EVT_ENGAGEMENT_ACTIVATION_CREATED,
        activation.engagement_activation_id,
        "operator-8k",
        "2026-07-14",
        activation.to_dict(),
    )
    assert constructed.to_dict()["event_id"] == "event-id-8k"


def test_cli_lifecycle_json_exit_codes_and_boundaries(accepted_source, monkeypatch, capsys):
    from scos.control_center import cli

    repo, _proposal, _handoff, _presentation, _decision, acceptance = accepted_source
    monkeypatch.setattr(cli, "_repo_root", lambda: repo)

    assert cli.main([
        "create-hvs-engagement-activation",
        "--acceptance-id", acceptance.commercial_acceptance_id,
        "--operator-id", "operator-8k",
        "--target-start-date", "2026-07-20",
        "--target-completion-date", "2026-07-31",
        "--recorded-at", "2026-07-14",
    ]) == 0
    activation = json.loads(capsys.readouterr().out)["activation"]
    activation_id = activation["engagement_activation_id"]
    assert activation["automation_allowed"] is False

    assert cli.main(["evaluate-hvs-engagement-readiness", "--engagement-id", activation_id, "--evaluation-date", "2026-07-14"]) == 1
    assert json.loads(capsys.readouterr().out)["readiness_status"] == "NEEDS_OPERATOR_INPUT"
    assert cli.main(["record-hvs-engagement-payment-requirement", "--engagement-id", activation_id, "--payment-start-requirement", "not-required", "--operator-id", "operator-8k", "--recorded-at", "2026-07-14"]) == 0
    capsys.readouterr()
    assert cli.main(["add-hvs-engagement-customer-input", "--engagement-id", activation_id, "--requirement-type", "FINAL_PRODUCTION_BRIEF", "--description", "Final production brief.", "--operator-id", "operator-8k", "--recorded-at", "2026-07-14"]) == 0
    requirement = json.loads(capsys.readouterr().out)["activation"]["customer_input_requirements"][0]
    assert cli.main(["confirm-hvs-engagement-customer-input", "--engagement-id", activation_id, "--input-requirement-id", requirement["customer_input_requirement_id"], "--operator-id", "operator-8k", "--evidence-reference", "evidence-final-brief-8k", "--confirmation-date", "2026-07-14", "--recorded-at", "2026-07-14"]) == 0
    capsys.readouterr()
    assert cli.main(["evaluate-hvs-engagement-readiness", "--engagement-id", activation_id, "--evaluation-date", "2026-07-14"]) == 0
    assert json.loads(capsys.readouterr().out)["project_created"] is False
    assert cli.main(["request-hvs-engagement-production-review", "--engagement-id", activation_id, "--operator-id", "operator-8k", "--evaluation-date", "2026-07-14", "--recorded-at", "2026-07-14"]) == 0
    capsys.readouterr()
    assert cli.main(["decide-hvs-engagement-activation", "--engagement-id", activation_id, "--decision", "approve", "--operator-id", "operator-8k", "--recorded-at", "2026-07-14"]) == 0
    capsys.readouterr()
    assert cli.main(["create-hvs-production-kickoff-authorization", "--engagement-id", activation_id, "--operator-id", "operator-8k", "--recorded-at", "2026-07-14"]) == 0
    auth = json.loads(capsys.readouterr().out)["authorization"]
    assert auth["project_initialization_authorized"] is True
    assert auth["hvs_invoked"] is False
    assert auth["payment_processed"] is False
    assert cli.main(["inspect-hvs-production-kickoff-authorization", "--authorization-id", auth["production_kickoff_authorization_id"]]) == 0
    assert json.loads(capsys.readouterr().out)["authorization"]["automation_allowed"] is False
    assert cli.main(["list-hvs-engagement-activation-queue", "--evaluation-date", "2026-07-14"]) == 0
    assert json.loads(capsys.readouterr().out)["items"][0]["engagement_activation_id"] == activation_id
    assert cli.main(["record-hvs-engagement-payment-requirement", "--engagement-id", activation_id, "--payment-start-requirement", "deposit", "--operator-id", "", "--recorded-at", "2026-07-14"]) == 1
    assert json.loads(capsys.readouterr().out)["error_code"] == "INVALID_INPUT"


def test_cli_rejection_branches_usage_errors_and_secret_free_output(accepted_source_factory, monkeypatch, capsys):
    from scos.control_center import cli

    repo, _proposal, _handoff, _presentation, _decision, acceptance = accepted_source_factory("cli-reject")
    monkeypatch.setattr(cli, "_repo_root", lambda: repo)

    assert cli.main(["create-hvs-engagement-activation", "--acceptance-id", "missing", "--operator-id", "operator-8k", "--recorded-at", "2026-07-14"]) == 1
    assert json.loads(capsys.readouterr().out)["error_code"] == "ACCEPTANCE_INELIGIBLE"

    assert cli.main(["create-hvs-engagement-activation", "--acceptance-id", acceptance.commercial_acceptance_id, "--operator-id", "operator-8k", "--recorded-at", "2026-07-14"]) == 0
    activation_id = json.loads(capsys.readouterr().out)["activation"]["engagement_activation_id"]

    assert cli.main(["inspect-hvs-engagement-activation", "--engagement-id", activation_id]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["activation"]["manual_project_initialization_required"] is True
    assert inspected["activation"]["automation_allowed"] is False

    assert cli.main(["record-hvs-engagement-payment-requirement", "--engagement-id", activation_id, "--payment-start-requirement", "deposit", "--operator-id", "operator-8k", "--required-payment-amount", "0.00", "--required-payment-currency", "USD", "--recorded-at", "2026-07-14"]) == 1
    assert json.loads(capsys.readouterr().out)["error_code"] == "INVALID_INPUT"

    assert cli.main(["confirm-hvs-engagement-payment-readiness", "--engagement-id", activation_id, "--operator-id", "", "--evidence-reference", "evidence-deposit-8k", "--confirmed-amount", "250.00", "--confirmed-currency", "USD", "--confirmation-date", "2026-07-14", "--recorded-at", "2026-07-14"]) == 1
    assert json.loads(capsys.readouterr().out)["error_code"] == "INVALID_INPUT"

    assert cli.main(["add-hvs-engagement-customer-input", "--engagement-id", activation_id, "--requirement-type", "BRAND_LOGO", "--description", "Logo.", "--operator-id", "operator-8k", "--recorded-at", "2026-07-14"]) == 1
    assert json.loads(capsys.readouterr().out)["error_code"] == "INVALID_INPUT"

    assert cli.main(["confirm-hvs-engagement-customer-input", "--engagement-id", activation_id, "--input-requirement-id", "missing", "--operator-id", "", "--evidence-reference", "evidence-final-brief-8k", "--confirmation-date", "2026-07-14", "--recorded-at", "2026-07-14"]) == 1
    assert json.loads(capsys.readouterr().out)["error_code"] == "INVALID_INPUT"

    assert cli.main(["request-hvs-engagement-production-review", "--engagement-id", activation_id, "--operator-id", "operator-8k", "--evaluation-date", "2026-07-14", "--recorded-at", "2026-07-14"]) == 1
    assert json.loads(capsys.readouterr().out)["error_code"] == "READINESS_BLOCKED"

    assert cli.main(["decide-hvs-engagement-activation", "--engagement-id", activation_id, "--decision", "reject", "--operator-id", "operator-8k", "--reason", "Operator rejected.", "--recorded-at", "2026-07-14"]) == 0
    rejected = json.loads(capsys.readouterr().out)
    assert rejected["activation"]["engagement_status"] == models.REJECTED

    cancel_source = accepted_source_factory("cli-cancel")
    assert cli.main(["create-hvs-engagement-activation", "--acceptance-id", cancel_source[-1].commercial_acceptance_id, "--operator-id", "operator-8k", "--recorded-at", "2026-07-14"]) == 0
    cancel_id = json.loads(capsys.readouterr().out)["activation"]["engagement_activation_id"]
    assert cli.main(["decide-hvs-engagement-activation", "--engagement-id", cancel_id, "--decision", "cancel", "--operator-id", "operator-8k", "--reason", "Operator cancelled.", "--recorded-at", "2026-07-14"]) == 0
    assert json.loads(capsys.readouterr().out)["activation"]["engagement_status"] == models.CANCELLED

    assert cli.main(["create-hvs-production-kickoff-authorization", "--engagement-id", cancel_id, "--operator-id", "operator-8k", "--recorded-at", "2026-07-14"]) == 1
    assert json.loads(capsys.readouterr().out)["error_code"] == "APPROVAL_REQUIRED"

    assert cli.main(["decide-hvs-engagement-activation", "--engagement-id", cancel_id, "--decision", "bogus", "--operator-id", "operator-8k", "--recorded-at", "2026-07-14"]) == 2
    usage = json.loads(capsys.readouterr().out)
    assert usage["error_kind"] == "INVALID_COMMAND"
    assert "secret-token" not in json.dumps(usage).lower()

    assert cli.main(["definitely-not-stage8k"]) == 2
    assert json.loads(capsys.readouterr().out)["error_kind"] == "INVALID_COMMAND"


def test_static_security_boundaries_have_no_forbidden_integrations():
    modules = (
        service,
        __import__("scos.control_center.hvs_engagement_activation_models", fromlist=["*"]),
        __import__("scos.control_center.hvs_engagement_activation_store", fromlist=["*"]),
    )
    combined = "\n".join(inspect.getsource(module) for module in modules)

    for forbidden in ("subprocess", "shell=True", "os.system", "requests", "urllib", "httpx", "socket", "smtplib", "webhook", "slack", "shutil.copy", "copyfile", "copy2", "upload", "publish", "import hvs", "from hvs", "python -m hvs", "hvs.cli"):
        assert forbidden not in combined
    assert "hermes-video-studio" not in combined
    assert "project_created=True" not in combined
    assert "render_started=True" not in combined
    assert "payment_processed=True" not in combined
