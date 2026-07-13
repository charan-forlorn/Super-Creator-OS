"""Stage 8J manual proposal presentation and commercial acceptance gate."""

from __future__ import annotations

import inspect
import json
from dataclasses import replace
from pathlib import Path

import pytest

from scos.control_center import hvs_commercial_acceptance_service as service
from scos.control_center import hvs_commercial_proposal_service as proposal_service
from scos.control_center.hvs_commercial_acceptance_store import (
    commercial_acceptance_path,
    read_commercial_acceptance_events,
)
from scos.control_center.hvs_commercial_proposal_store import (
    commercial_proposal_path,
    read_commercial_proposal_events,
)
from scos.control_center.tests.test_hvs_commercial_proposal_handoff import (
    _request,
    qualified_opportunity,
)


@pytest.fixture
def approved_package(qualified_opportunity):
    repo, opportunity, lineage = qualified_opportunity
    created = proposal_service.create_proposal_preparation(repo_root=repo, **_request(opportunity, lineage))
    assert created.ok
    assert proposal_service.submit_for_internal_review(
        proposal_preparation_id=created.proposal.proposal_preparation_id,
        operator_id="operator-8j",
        repo_root=repo,
        recorded_at="2026-07-10",
    ).ok
    approved = proposal_service.approve_for_manual_presentation(
        proposal_preparation_id=created.proposal.proposal_preparation_id,
        operator_id="operator-approver-8j",
        repo_root=repo,
        recorded_at="2026-07-10",
        as_of="2026-07-10",
    )
    assert approved.ok
    handoff = proposal_service.create_manual_commercial_handoff(
        proposal_preparation_id=created.proposal.proposal_preparation_id,
        operator_id="operator-8j",
        repo_root=repo,
        recorded_at="2026-07-10",
    )
    assert handoff.ok
    return repo, approved.proposal, handoff.handoff


def _presentation(repo: Path, proposal, handoff, **overrides):
    data = {
        "proposal_preparation_id": proposal.proposal_preparation_id,
        "commercial_handoff_package_id": handoff.handoff_id,
        "presentation_channel": "VIDEO_CALL",
        "presentation_date": "2026-07-12",
        "presented_by_operator_id": "operator-presenter-8j",
        "evidence_reference": "presentation-evidence-8j",
        "customer_participant_reference": "customer-contact-8j",
        "operator_note": "Manual presentation completed by the operator.",
        "manual_action_confirmed": True,
        "repo_root": repo,
        "recorded_at": "2026-07-12",
    }
    data.update(overrides)
    return service.record_manual_proposal_presentation(**data)


def _accepted_decision(repo: Path, proposal, presentation, **overrides):
    data = {
        "presentation_record_id": presentation.presentation_record_id,
        "decision_type": "ACCEPTED",
        "decision_date": "2026-07-13",
        "recorded_by_operator_id": "operator-decision-8j",
        "evidence_reference": "acceptance-evidence-8j",
        "approved_proposal_content_hash": proposal.deterministic_content_hash,
        "customer_decision_reference": "customer-decision-ref-8j",
        "accepted_total": "1000.00",
        "accepted_currency": "USD",
        "accepted_scope_hash": proposal.commercial_scope_id,
        "accepted_payment_terms": proposal.payment_terms,
        "accepted_revision_terms": proposal.revision_terms,
        "accepted_tax": "0.00",
        "accepted_discount": "0.00",
        "repo_root": repo,
        "recorded_at": "2026-07-13",
    }
    data.update(overrides)
    return service.record_customer_commercial_decision(**data)


def test_presentation_eligibility_records_manual_evidence_and_preserves_sources(approved_package):
    repo, proposal, handoff = approved_package
    proposal_events_before = read_commercial_proposal_events(audit_log_path=commercial_proposal_path(repo))
    result = _presentation(repo, proposal, handoff)

    assert result.ok
    assert result.presentation.proposal_preparation_id == proposal.proposal_preparation_id
    assert result.presentation.commercial_handoff_package_id == handoff.handoff_id
    assert result.presentation.approved_proposal_content_hash == proposal.deterministic_content_hash
    assert result.presentation.opportunity_id == proposal.opportunity_id
    assert result.presentation.commercial_scope_id == proposal.commercial_scope_id
    assert result.presentation.project_id == proposal.project_id
    assert result.presentation.customer_reference == proposal.customer_reference
    assert result.presentation.source_delivery_lineage_id == proposal.source_delivery_lineage_id
    assert result.presentation.source_artifact_id == proposal.source_artifact_id
    assert result.presentation.source_artifact_sha256 == proposal.source_artifact_sha256
    assert result.presentation.manual_action_confirmed is True
    assert result.presentation.communication_performed_by_system is False
    assert result.presentation.automation_allowed is False
    assert read_commercial_proposal_events(audit_log_path=commercial_proposal_path(repo)) == proposal_events_before


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("DRAFT", "PROPOSAL_NOT_APPROVED_FOR_MANUAL_PRESENTATION"),
        ("READY_FOR_INTERNAL_REVIEW", "PROPOSAL_NOT_APPROVED_FOR_MANUAL_PRESENTATION"),
        ("REJECTED", "PROPOSAL_NOT_APPROVED_FOR_MANUAL_PRESENTATION"),
        ("CANCELLED", "PROPOSAL_NOT_APPROVED_FOR_MANUAL_PRESENTATION"),
    ],
)
def test_presentation_rejects_unapproved_terminal_or_cancelled_proposals(approved_package, monkeypatch, status, expected):
    repo, proposal, handoff = approved_package
    monkeypatch.setattr(
        service,
        "_records",
        lambda _repo: {proposal.proposal_preparation_id: replace(proposal, proposal_status=status)},
    )
    result = _presentation(repo, proposal, handoff)

    assert not result.ok
    assert result.error_code == "PRESENTATION_INELIGIBLE"
    assert expected in result.blockers
    assert read_commercial_acceptance_events(audit_log_path=commercial_acceptance_path(repo)) == ()


@pytest.mark.parametrize(
    ("mutation", "blocker"),
    [
        ("missing_handoff", "HANDOFF_NOT_FOUND"),
        ("handoff_id", "HANDOFF_ID_MISMATCH"),
        ("content_hash", "HANDOFF_CONTENT_HASH_MISMATCH"),
        ("scope", "HANDOFF_SCOPE_MISMATCH"),
        ("artifact_sha", "SOURCE_ARTIFACT_SHA_MISMATCH"),
        ("customer", "HANDOFF_CONTENT_HASH_MISMATCH"),
    ],
)
def test_presentation_rejects_mismatched_handoff_and_lineage(approved_package, monkeypatch, mutation, blocker):
    repo, proposal, handoff = approved_package
    if mutation == "missing_handoff":
        monkeypatch.setattr(service, "_handoffs", lambda _repo: {})
    elif mutation == "handoff_id":
        result = _presentation(repo, proposal, handoff, commercial_handoff_package_id="other-handoff")
        assert not result.ok and blocker in result.blockers
        return
    elif mutation == "content_hash":
        monkeypatch.setattr(service, "_handoffs", lambda _repo: {proposal.proposal_preparation_id: replace(handoff, approved_content_hash="x" * 64)})
    elif mutation == "scope":
        monkeypatch.setattr(service, "_handoffs", lambda _repo: {proposal.proposal_preparation_id: replace(handoff, commercial_scope_id="other-scope")})
    elif mutation == "artifact_sha":
        monkeypatch.setattr(service, "_handoffs", lambda _repo: {proposal.proposal_preparation_id: replace(handoff, source_lineage={**handoff.source_lineage, "artifact_sha256": "0" * 64})})
    else:
        monkeypatch.setattr(service, "_records", lambda _repo: {proposal.proposal_preparation_id: replace(proposal, deterministic_content_hash="y" * 64)})
    result = _presentation(repo, proposal, handoff)

    assert not result.ok
    assert blocker in result.blockers


def test_presentation_requires_confirmation_operator_valid_date_and_channel(approved_package):
    repo, proposal, handoff = approved_package

    assert _presentation(repo, proposal, handoff, manual_action_confirmed=False).error_code == "INVALID_INPUT"
    assert _presentation(repo, proposal, handoff, presented_by_operator_id="").error_code == "INVALID_INPUT"
    assert _presentation(repo, proposal, handoff, presentation_date="2026-02-30").error_code == "INVALID_INPUT"
    assert _presentation(repo, proposal, handoff, presentation_channel="AUTO_EMAIL").error_code == "INVALID_INPUT"
    assert _presentation(repo, proposal, handoff, presentation_date="2026-08-01").error_code == "PROPOSAL_EXPIRED"
    assert read_commercial_acceptance_events(audit_log_path=commercial_acceptance_path(repo)) == ()


def test_presentation_identity_replay_conflict_and_no_system_communication(approved_package):
    repo, proposal, handoff = approved_package
    first = _presentation(repo, proposal, handoff)
    replay = _presentation(repo, proposal, handoff)
    changed = _presentation(repo, proposal, handoff, presentation_channel="PHONE")

    assert first.ok
    assert replay.ok and replay.duplicate_of == first.presentation.presentation_record_id
    assert changed.ok
    assert changed.presentation.presentation_record_id != first.presentation.presentation_record_id
    assert all(
        not event.record.get(flag, False)
        for event in read_commercial_acceptance_events(audit_log_path=commercial_acceptance_path(repo))
        for flag in ("communication_performed_by_system", "automation_allowed")
    )


@pytest.mark.parametrize(
    ("decision", "kwargs", "field"),
    [
        ("ACCEPTED", {}, "acceptance"),
        ("REJECTED", {"rejection_reason": "Customer declined.", "accepted_total": None, "accepted_currency": None, "accepted_scope_hash": None}, "decision"),
        ("NEGOTIATION_REQUESTED", {"requested_changes": ("Change payment timing.",), "accepted_total": None, "accepted_currency": None, "accepted_scope_hash": None}, "decision"),
        ("PROPOSAL_REVISION_REQUESTED", {"requested_changes": ("Revise deliverables.",), "accepted_total": None, "accepted_currency": None, "accepted_scope_hash": None}, "decision"),
        ("NO_RESPONSE", {"follow_up_date": "2026-07-20", "accepted_total": None, "accepted_currency": None, "accepted_scope_hash": None}, "decision"),
        ("DEFERRED", {"deferred_reason": "Customer board review pending.", "accepted_total": None, "accepted_currency": None, "accepted_scope_hash": None}, "decision"),
    ],
)
def test_customer_decision_state_machine_records_all_outcomes(approved_package, decision, kwargs, field):
    repo, proposal, handoff = approved_package
    presentation = _presentation(repo, proposal, handoff).presentation
    result = _accepted_decision(repo, proposal, presentation, decision_type=decision, **kwargs)

    assert result.ok
    assert result.decision.decision_type == decision
    assert result.decision.customer_contact_performed_by_system is False
    assert result.decision.automation_allowed is False
    assert getattr(result, field) is not None
    if decision != "ACCEPTED":
        assert result.acceptance is None
        assert service.evaluate_commercial_acceptance_readiness(
            proposal_preparation_id=proposal.proposal_preparation_id,
            repo_root=repo,
            evaluation_date="2026-07-13",
        ).ready_for_manual_invoice is False


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"presentation_record_id": "missing"}, "PRESENTATION_NOT_FOUND"),
        ({"recorded_by_operator_id": ""}, "INVALID_INPUT"),
        ({"evidence_reference": ""}, "INVALID_INPUT"),
        ({"decision_date": "2026-02-30"}, "INVALID_INPUT"),
        ({"approved_proposal_content_hash": "bad-hash"}, "CONTENT_HASH_MISMATCH"),
    ],
)
def test_decision_requires_prior_presentation_operator_evidence_date_and_hash(approved_package, kwargs, code):
    repo, proposal, handoff = approved_package
    presentation = _presentation(repo, proposal, handoff).presentation
    result = _accepted_decision(repo, proposal, presentation, **kwargs)

    assert not result.ok
    assert result.error_code == code


@pytest.mark.parametrize(
    ("kwargs", "blocker"),
    [
        ({"approved_proposal_content_hash": "z" * 64}, "CONTENT_HASH_MISMATCH"),
        ({"accepted_total": "999.99"}, "ACCEPTED_TOTAL_MISMATCH"),
        ({"accepted_currency": "EUR"}, "ACCEPTED_CURRENCY_MISMATCH"),
        ({"accepted_scope_hash": "other-scope"}, "ACCEPTED_SCOPE_MISMATCH"),
        ({"accepted_payment_terms": "Changed terms."}, "PAYMENT_TERMS_CHANGED"),
        ({"accepted_revision_terms": "Changed revisions."}, "REVISION_TERMS_CHANGED"),
        ({"accepted_tax": "1.00"}, "TAX_CHANGED"),
        ({"accepted_discount": "1.00"}, "DISCOUNT_CHANGED"),
        ({"requested_changes": ("Partial acceptance.",)}, "ACCEPTANCE_CONTRADICTED_BY_CHANGE_FIELDS"),
    ],
)
def test_exact_acceptance_rejects_modified_content_commercial_terms_and_partial_acceptance(approved_package, kwargs, blocker):
    repo, proposal, handoff = approved_package
    presentation = _presentation(repo, proposal, handoff).presentation
    result = _accepted_decision(repo, proposal, presentation, **kwargs)

    assert not result.ok
    assert blocker in result.blockers
    assert not service._acceptances(repo)


def test_exact_acceptance_creates_verified_record_and_readiness(approved_package):
    repo, proposal, handoff = approved_package
    presentation = _presentation(repo, proposal, handoff).presentation
    result = _accepted_decision(repo, proposal, presentation)
    readiness = service.evaluate_commercial_acceptance_readiness(
        proposal_preparation_id=proposal.proposal_preparation_id,
        repo_root=repo,
        evaluation_date="2026-07-13",
    )

    assert result.ok and result.acceptance.acceptance_status == "ACCEPTED_VERIFIED"
    assert result.acceptance.approved_proposal_content_hash == proposal.deterministic_content_hash
    assert result.acceptance.accepted_scope_hash == proposal.commercial_scope_id
    assert result.acceptance.acceptance_evidence_reference == "acceptance-evidence-8j"
    assert result.acceptance.opportunity_id == proposal.opportunity_id
    assert result.acceptance.commercial_scope_id == proposal.commercial_scope_id
    assert result.acceptance.source_delivery_lineage_id == proposal.source_delivery_lineage_id
    assert result.acceptance.source_artifact_sha256 == proposal.source_artifact_sha256
    assert result.acceptance.accepted_total == proposal.total_amount
    assert result.acceptance.accepted_currency == proposal.currency
    assert result.acceptance.accepted_payment_terms == proposal.payment_terms
    assert result.acceptance.accepted_revision_terms == proposal.revision_terms
    assert readiness.readiness_status == "READY_FOR_MANUAL_INVOICE_AND_KICKOFF"
    assert readiness.commercial_acceptance_id == result.acceptance.commercial_acceptance_id
    assert readiness.ready_for_manual_invoice is True
    assert readiness.ready_for_manual_project_kickoff is True
    assert readiness.manual_invoice_required is True
    assert readiness.manual_project_kickoff_required is True
    assert all(
        getattr(result.acceptance, field) is False
        for field in (
            "invoice_created",
            "payment_link_created",
            "payment_state_changed",
            "project_created",
            "hvs_invoked",
            "render_started",
            "customer_contact_performed_by_system",
            "automation_allowed",
        )
    )


def test_acceptance_replay_is_idempotent_and_conflicting_decision_is_rejected(approved_package):
    repo, proposal, handoff = approved_package
    presentation = _presentation(repo, proposal, handoff).presentation
    first = _accepted_decision(repo, proposal, presentation)
    replay = _accepted_decision(repo, proposal, presentation)
    conflict = _accepted_decision(repo, proposal, presentation, evidence_reference="new-evidence-8j")

    assert replay.ok and replay.duplicate_of == first.decision.customer_decision_id
    assert replay.acceptance.commercial_acceptance_id == first.acceptance.commercial_acceptance_id
    assert not conflict.ok and conflict.error_code == "CUSTOMER_DECISION_CONFLICT"
    assert len(service._acceptances(repo)) == 1


@pytest.mark.parametrize(
    ("decision", "kwargs", "status"),
    [
        ("REJECTED", {"rejection_reason": "Customer declined.", "accepted_total": None, "accepted_currency": None, "accepted_scope_hash": None}, "NOT_ACCEPTED"),
        ("NEGOTIATION_REQUESTED", {"requested_changes": ("Change terms.",), "accepted_total": None, "accepted_currency": None, "accepted_scope_hash": None}, "NEGOTIATION_REQUIRED"),
        ("PROPOSAL_REVISION_REQUESTED", {"requested_changes": ("Revise scope.",), "accepted_total": None, "accepted_currency": None, "accepted_scope_hash": None}, "NEGOTIATION_REQUIRED"),
        ("NO_RESPONSE", {"follow_up_date": "2026-07-20", "accepted_total": None, "accepted_currency": None, "accepted_scope_hash": None}, "NOT_ACCEPTED"),
    ],
)
def test_readiness_non_acceptance_paths_do_not_create_acceptance(approved_package, decision, kwargs, status):
    repo, proposal, handoff = approved_package
    presentation = _presentation(repo, proposal, handoff).presentation
    outcome = _accepted_decision(repo, proposal, presentation, decision_type=decision, **kwargs)
    readiness = service.evaluate_commercial_acceptance_readiness(
        proposal_preparation_id=proposal.proposal_preparation_id,
        repo_root=repo,
        evaluation_date="2026-07-13",
    )

    assert outcome.ok
    assert outcome.acceptance is None
    assert readiness.readiness_status == status
    assert readiness.ready_for_manual_invoice is False
    assert service._acceptances(repo) == {}


def test_readiness_is_read_only_and_reports_missing_or_expired_state(approved_package):
    repo, proposal, handoff = approved_package
    before = read_commercial_acceptance_events(audit_log_path=commercial_acceptance_path(repo))
    missing_presentation = service.evaluate_commercial_acceptance_readiness(
        proposal_preparation_id=proposal.proposal_preparation_id,
        repo_root=repo,
        evaluation_date="2026-07-13",
    )
    expired = service.evaluate_commercial_acceptance_readiness(
        proposal_preparation_id=proposal.proposal_preparation_id,
        repo_root=repo,
        evaluation_date="2026-08-01",
    )

    assert missing_presentation.readiness_status == "NEEDS_OPERATOR_INPUT"
    assert missing_presentation.missing_fields == ("PRESENTATION_RECORD",)
    assert expired.readiness_status == "EXPIRED"
    assert read_commercial_acceptance_events(audit_log_path=commercial_acceptance_path(repo)) == before
    _presentation(repo, proposal, handoff)
    before_after_presentation = read_commercial_acceptance_events(audit_log_path=commercial_acceptance_path(repo))
    missing_decision = service.evaluate_commercial_acceptance_readiness(
        proposal_preparation_id=proposal.proposal_preparation_id,
        repo_root=repo,
        evaluation_date="2026-07-13",
    )
    assert missing_decision.missing_fields == ("CUSTOMER_DECISION_RECORD",)
    assert read_commercial_acceptance_events(audit_log_path=commercial_acceptance_path(repo)) == before_after_presentation


def test_store_append_only_malformed_duplicate_event_and_path_safety(approved_package):
    repo, proposal, handoff = approved_package
    _presentation(repo, proposal, handoff)
    events = read_commercial_acceptance_events(audit_log_path=commercial_acceptance_path(repo))
    path = commercial_acceptance_path(repo)
    path.write_text(path.read_text(encoding="utf-8") + path.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="conflicting commercial acceptance event"):
        read_commercial_acceptance_events(audit_log_path=path)
    with pytest.raises(ValueError, match="unsafe commercial acceptance store path"):
        read_commercial_acceptance_events(audit_log_path=repo / ".." / "escape.jsonl")
    path.write_text("not-json\n", encoding="utf-8")
    with pytest.raises(ValueError, match="malformed commercial acceptance event"):
        read_commercial_acceptance_events(audit_log_path=path)
    assert events


def test_security_boundaries_static_source_and_safe_inputs(approved_package):
    repo, proposal, handoff = approved_package
    source = inspect.getsource(service)

    assert "subprocess" not in source
    assert "shell=True" not in source
    assert "os.system" not in source
    assert "requests" not in source
    assert "urllib" not in source
    assert "httpx" not in source
    assert "socket" not in source
    assert "smtp" not in source.lower()
    assert "slack" not in source.lower()
    assert "webhook" not in source.lower()
    assert "stripe" not in source.lower()
    assert "hermes-video-studio" not in source
    assert "python -m hvs" not in source
    assert _presentation(repo, proposal, handoff, evidence_reference="secret-token").error_code == "INVALID_INPUT"
    assert _presentation(repo, proposal, handoff, presented_by_operator_id="bad\noperator").error_code == "INVALID_INPUT"


def test_cli_success_error_inspection_readiness_and_queue(approved_package, monkeypatch, capsys):
    from scos.control_center import cli

    repo, proposal, handoff = approved_package
    monkeypatch.setattr(cli, "_repo_root", lambda: repo)

    assert cli.main([
        "record-hvs-proposal-presentation",
        "--proposal-id", proposal.proposal_preparation_id,
        "--handoff-id", handoff.handoff_id,
        "--channel", "video_call",
        "--presentation-date", "2026-07-12",
        "--operator-id", "operator-presenter-8j",
        "--evidence-reference", "presentation-evidence-8j",
        "--confirm-manual-presentation",
    ]) == 0
    presentation = json.loads(capsys.readouterr().out)["presentation"]
    assert presentation["automation_allowed"] is False

    assert cli.main(["list-hvs-commercial-decision-queue", "--evaluation-date", "2026-07-13"]) == 0
    assert json.loads(capsys.readouterr().out)["items"][0]["presentation_record_id"] == presentation["presentation_record_id"]

    accepted_args = [
        "record-hvs-customer-commercial-decision",
        "--presentation-id", presentation["presentation_record_id"],
        "--decision", "accepted",
        "--decision-date", "2026-07-13",
        "--operator-id", "operator-decision-8j",
        "--evidence-reference", "acceptance-evidence-8j",
        "--approved-proposal-content-hash", proposal.deterministic_content_hash,
        "--accepted-total", "1000.00",
        "--accepted-currency", "USD",
        "--accepted-scope-hash", proposal.commercial_scope_id,
        "--accepted-payment-terms", proposal.payment_terms,
        "--accepted-revision-terms", proposal.revision_terms,
    ]
    assert cli.main(accepted_args) == 0
    accepted = json.loads(capsys.readouterr().out)
    assert accepted["acceptance"]["ready_for_manual_invoice"] is True
    assert cli.main(["inspect-hvs-customer-commercial-decision", "--decision-id", accepted["decision"]["customer_decision_id"]]) == 0
    assert json.loads(capsys.readouterr().out)["decision"]["decision_type"] == "ACCEPTED"
    assert cli.main(["evaluate-hvs-commercial-acceptance-readiness", "--proposal-id", proposal.proposal_preparation_id, "--evaluation-date", "2026-07-13"]) == 0
    assert json.loads(capsys.readouterr().out)["readiness_status"] == "READY_FOR_MANUAL_INVOICE_AND_KICKOFF"
    assert cli.main(["inspect-hvs-commercial-acceptance", "--acceptance-id", accepted["acceptance"]["commercial_acceptance_id"]]) == 0
    assert json.loads(capsys.readouterr().out)["acceptance"]["hvs_invoked"] is False
    assert cli.main([
        "record-hvs-proposal-presentation",
        "--proposal-id", proposal.proposal_preparation_id,
        "--handoff-id", handoff.handoff_id,
        "--channel", "video_call",
        "--presentation-date", "2026-07-12",
        "--operator-id", "operator-presenter-8j",
    ]) == 1
    assert json.loads(capsys.readouterr().out)["error_code"] == "INVALID_INPUT"
