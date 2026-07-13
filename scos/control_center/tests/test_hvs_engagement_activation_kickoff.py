"""Stage 8K engagement activation and production kickoff authorization gate."""

from __future__ import annotations

import inspect
import json
from dataclasses import replace
from pathlib import Path

import pytest

from scos.control_center import hvs_commercial_acceptance_service as acceptance_service
from scos.control_center import hvs_commercial_proposal_service as proposal_service
from scos.control_center import hvs_engagement_activation_service as service
from scos.control_center.hvs_commercial_acceptance_store import (
    commercial_acceptance_path,
    read_commercial_acceptance_events,
)
from scos.control_center.hvs_engagement_activation_models import (
    APPROVED_FOR_PROJECT_INITIALIZATION,
    DEPOSIT_REQUIRED_BEFORE_START,
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


def test_activation_rejects_invalid_lineage_without_writing_stage8k(accepted_source, monkeypatch):
    repo, proposal, _handoff, _presentation, _decision, acceptance = accepted_source
    monkeypatch.setattr(service, "_records", lambda _repo: {proposal.proposal_preparation_id: replace(proposal, deterministic_content_hash="f" * 64)})

    result = _activation(repo, acceptance)

    assert not result.ok
    assert result.error_code == "ACCEPTANCE_INELIGIBLE"
    assert "PROPOSAL_CONTENT_HASH_MISMATCH" in result.blockers
    assert read_engagement_activation_events(audit_log_path=engagement_activation_path(repo)) == ()


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


def test_static_security_boundaries_have_no_forbidden_integrations():
    modules = (
        service,
        __import__("scos.control_center.hvs_engagement_activation_models", fromlist=["*"]),
        __import__("scos.control_center.hvs_engagement_activation_store", fromlist=["*"]),
    )
    combined = "\n".join(inspect.getsource(module) for module in modules)

    for forbidden in ("subprocess", "shell=True", "os.system", "requests", "urllib", "httpx", "socket", "smtplib", "webhook", "slack", "import hvs", "from hvs", "python -m hvs", "hvs.cli"):
        assert forbidden not in combined
    assert "hermes-video-studio" not in combined
    assert "project_created=True" not in combined
    assert "render_started=True" not in combined
    assert "payment_processed=True" not in combined
