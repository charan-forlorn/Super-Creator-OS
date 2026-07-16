"""Stage 8L approval-gated HVS project initialization materialization."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

from scos.control_center import cli
from scos.control_center import hvs_engagement_activation_service as stage8k
from scos.control_center import hvs_project_initialization_service as service
from scos.control_center.hvs_engagement_activation_models import (
    INPUT_FINAL_PRODUCTION_BRIEF,
    PAYMENT_NOT_REQUIRED_BEFORE_START,
)
from scos.control_center.hvs_project_initialization_models import (
    INITIALIZATION_CONFLICT,
    INITIALIZATION_VERIFIED,
    hvs_project_id_for_authorization,
)
from scos.control_center.hvs_project_initialization_store import (
    project_initialization_path,
    read_project_initialization_events,
)
from scos.control_center.tests.test_hvs_engagement_activation_kickoff import (
    _activation,
    accepted_source,
)
from scos.control_center.tests.test_hvs_commercial_proposal_handoff import qualified_opportunity
from scos.control_center.hvs_adapter import (
    Stage8_5AdapterAuthorization,
    Stage8_5AuthorizationError,
)


def _production_input(title: str = "Stage 8L Synthetic Production"):
    scenes = tuple(
        service.ProductionSceneInput(
            scene_id=f"scene_{idx:02d}",
            duration_ms=1000,
            intent=f"intent-{idx}",
            visual_description=f"visual-{idx}",
            text_overlay=f"text-{idx}",
        )
        for idx in range(3)
    )
    return service.ProductionInitializationInput(title=title, language="en", scenes=scenes)


def _authorize(repo: Path, acceptance):
    activation = _activation(repo, acceptance).activation
    payment = stage8k.record_payment_start_requirement(
        engagement_activation_id=activation.engagement_activation_id,
        payment_start_requirement=PAYMENT_NOT_REQUIRED_BEFORE_START,
        operator_id="operator-8l-payment",
        repo_root=repo,
        recorded_at="2026-07-14",
    )
    requirement = stage8k.add_customer_input_requirement(
        engagement_activation_id=activation.engagement_activation_id,
        requirement_type=INPUT_FINAL_PRODUCTION_BRIEF,
        description="Final production brief.",
        operator_id="operator-8l-input",
        repo_root=repo,
        recorded_at="2026-07-14",
    )
    confirmed = stage8k.confirm_customer_input_requirement(
        engagement_activation_id=activation.engagement_activation_id,
        customer_input_requirement_id=requirement.activation.customer_input_requirements[0].customer_input_requirement_id,
        operator_id="operator-8l-input",
        evidence_reference="evidence-final-brief-8l",
        confirmation_date="2026-07-14",
        repo_root=repo,
        recorded_at="2026-07-14",
    )
    reviewed = stage8k.request_production_review(
        engagement_activation_id=confirmed.activation.engagement_activation_id,
        operator_id="operator-8l-review",
        repo_root=repo,
        recorded_at="2026-07-14",
        evaluation_date="2026-07-14",
    )
    approved = stage8k.decide_engagement_activation(
        engagement_activation_id=reviewed.activation.engagement_activation_id,
        decision="approve",
        operator_id="operator-8l-approve",
        repo_root=repo,
        recorded_at="2026-07-14",
    )
    authorization = stage8k.create_production_kickoff_authorization(
        engagement_activation_id=approved.activation.engagement_activation_id,
        operator_id="operator-8l-approve",
        repo_root=repo,
        recorded_at="2026-07-14",
    )
    return authorization.authorization


class _FakeAdapter:
    def __init__(self, *, conflict: bool = False, malformed_inspect: bool = False):
        self.calls = []
        self.conflict = conflict
        self.malformed_inspect = malformed_inspect

    def initialize_project(self, **kwargs):
        self.calls.append(("initialize-project", dict(kwargs)))
        if self.conflict:
            return {
                "ok": False,
                "exit_code": 1,
                "payload": {
                    "status": "conflict",
                    "error_code": "PROJECT_INITIALIZATION_CONFLICT",
                    "error_detail": "existing project metadata differs from contract",
                },
            }
        return {
            "ok": True,
            "exit_code": 0,
            "payload": {
                "requested_project_id": kwargs["project_id"],
                "actual_project_id": kwargs["project_id"],
                "expected_payload_hash": kwargs["expected_payload_hash"],
                "actual_payload_hash": kwargs["expected_payload_hash"],
                "project_created": True,
                "identical_replay": False,
                "project_verified": True,
                "status": "verified",
            },
        }

    def inspect_project(self, **kwargs):
        self.calls.append(("inspect-project", dict(kwargs)))
        init = self.calls[0][1]
        title = "wrong" if self.malformed_inspect else "Stage 8L Synthetic Production"
        return {
            "ok": True,
            "exit_code": 0,
            "payload": {
                "exists": True,
                "project_id": kwargs["project_id"],
                "title": title,
                "language": "en",
                "timeline": {"valid": True},
                "initialization": {"payload_hash": init["expected_payload_hash"]},
                "voice_generated": False,
                "placeholder_assets_generated": False,
                "render_started": False,
            },
        }


def _valid_stage85_authorization() -> Stage8_5AdapterAuthorization:
    # A correctly bound, AUTHORIZED_IN_PRINCIPLE decision for initialize-project.
    # Built directly from Stage8_5AdapterAuthorization so the service gate's
    # require_for() passes; this mirrors a decision produced by the Stage 8.5
    # evaluate_adapter_activation_authorization gate (now invoked before any
    # mutating HVS operation).
    return Stage8_5AdapterAuthorization(
        "AUTHORIZED_IN_PRINCIPLE", operation="initialize-project", target=""
    )


def test_build_contract_reverifies_stage8k_and_maps_stage2(accepted_source):
    repo, _proposal, _handoff, _presentation, _decision, acceptance = accepted_source
    authorization = _authorize(repo, acceptance)

    out = service.build_production_initialization_contract(
        production_kickoff_authorization_id=authorization.production_kickoff_authorization_id,
        production_input=_production_input(),
        repo_root=repo,
    )

    assert out.ok
    contract = out.contract
    assert contract.hvs_project_id == hvs_project_id_for_authorization(authorization.production_kickoff_authorization_id)
    assert contract.hvs_initialization_contract["contract_name"] == "scos-hvs.project-initialization"
    assert contract.hvs_initialization_contract["timeline"]["project_id"] == contract.hvs_project_id
    assert contract.stage2_payload_hash
    assert contract.asset_materialization_authorized is False
    assert contract.render_started is False


def test_invalid_authorization_and_missing_approval_do_not_invoke_hvs(accepted_source):
    repo, _proposal, _handoff, _presentation, _decision, acceptance = accepted_source
    authorization = _authorize(repo, acceptance)
    fake = _FakeAdapter()

    invalid = service.initialize_hvs_project(
        production_kickoff_authorization_id="missing",
        production_input=_production_input(),
        operator_id="operator-8l",
        repo_root=repo,
        hvs_repo_root="hvs",
        hvs_python_executable="py",
        recorded_at="2026-07-14",
        approve_initialization=True,
        adapter=fake,
    )
    missing_approval = service.initialize_hvs_project(
        production_kickoff_authorization_id=authorization.production_kickoff_authorization_id,
        production_input=_production_input(),
        operator_id="operator-8l",
        repo_root=repo,
        hvs_repo_root="hvs",
        hvs_python_executable="py",
        recorded_at="2026-07-14",
        approve_initialization=False,
        adapter=fake,
    )

    # The invalid authorization id fails closed (eligibility or the Stage 8.5
    # gate, whichever is reached first); the key invariant is no HVS invocation.
    assert invalid.error_code in ("STAGE8L_ELIGIBILITY_BLOCKED", "STAGE85_AUTHORIZATION_BLOCKED")
    assert missing_approval.error_code == "INITIALIZATION_APPROVAL_REQUIRED"
    assert fake.calls == []


def test_successful_initialization_invokes_only_initialize_and_inspect_and_persists_evidence(accepted_source):
    repo, _proposal, _handoff, _presentation, _decision, acceptance = accepted_source
    authorization = _authorize(repo, acceptance)
    fake = _FakeAdapter()

    out = service.initialize_hvs_project(
        production_kickoff_authorization_id=authorization.production_kickoff_authorization_id,
        production_input=_production_input(),
        operator_id="operator-8l",
        repo_root=repo,
        hvs_repo_root="hvs",
        hvs_python_executable="py",
        recorded_at="2026-07-14",
        approve_initialization=True,
        adapter=fake,
        stage85_authorization=_valid_stage85_authorization(),
    )

    assert out.ok
    assert [call[0] for call in fake.calls] == ["initialize-project", "inspect-project"]
    assert fake.calls[0][1]["approve_initialization"] is True
    assert out.evidence.initialization_status == INITIALIZATION_VERIFIED
    assert out.evidence.project_created is True
    assert out.evidence.semantic_comparison_passed is True
    events = read_project_initialization_events(audit_log_path=project_initialization_path(repo))
    assert events[-1].record["initialization_status"] == INITIALIZATION_VERIFIED


def test_hvs_conflict_and_inspection_mismatch_cannot_become_verified(accepted_source):
    repo, _proposal, _handoff, _presentation, _decision, acceptance = accepted_source
    authorization = _authorize(repo, acceptance)
    conflict_adapter = _FakeAdapter(conflict=True)
    mismatch_adapter = _FakeAdapter(malformed_inspect=True)

    conflict = service.initialize_hvs_project(
        production_kickoff_authorization_id=authorization.production_kickoff_authorization_id,
        production_input=_production_input(title="Changed title"),
        operator_id="operator-8l",
        repo_root=repo,
        hvs_repo_root="hvs",
        hvs_python_executable="py",
        recorded_at="2026-07-14",
        approve_initialization=True,
        adapter=conflict_adapter,
        stage85_authorization=_valid_stage85_authorization(),
    )
    mismatch = service.initialize_hvs_project(
        production_kickoff_authorization_id=authorization.production_kickoff_authorization_id,
        production_input=_production_input(),
        operator_id="operator-8l",
        repo_root=repo,
        hvs_repo_root="hvs",
        hvs_python_executable="py",
        recorded_at="2026-07-14",
        approve_initialization=True,
        adapter=mismatch_adapter,
        stage85_authorization=_valid_stage85_authorization(),
    )

    assert not conflict.ok
    assert conflict.evidence.initialization_status == INITIALIZATION_CONFLICT
    assert conflict.error_code == "PROJECT_INITIALIZATION_CONFLICT"
    assert not mismatch.ok
    assert mismatch.error_code == "SEMANTIC_VERIFICATION_FAILED"
    assert mismatch.evidence.semantic_comparison_passed is False


def test_cli_initialization_command_requires_explicit_input_and_passes_operator_gate(tmp_path, monkeypatch, capsys):
    production_input = tmp_path / "production.json"
    production_input.write_text(json.dumps(_production_input().to_dict()), encoding="utf-8")
    calls = []

    class _Outcome:
        ok = True

        def to_dict(self):
            return {"ok": True, "evidence": {"initialization_status": INITIALIZATION_VERIFIED}}

    def fake_initialize(**kwargs):
        calls.append(kwargs)
        return _Outcome()

    monkeypatch.setattr(cli, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(service, "initialize_hvs_project", fake_initialize)

    code = cli.main(
        [
            "initialize-hvs-project",
            "--authorization-id",
            "auth-123",
            "--production-input-json",
            str(production_input),
            "--operator-id",
            "operator-8l",
            "--recorded-at",
            "2026-07-14",
            "--hvs-repo-root",
            "C:/Workspace/hermes-video-studio",
            "--hvs-python-executable",
            "C:/Workspace/hermes-video-studio/.venv/Scripts/python.exe",
            "--approve-initialization",
        ]
    )

    assert code == cli.EXIT_OK
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert calls[0]["production_kickoff_authorization_id"] == "auth-123"
    assert calls[0]["production_input"].title == "Stage 8L Synthetic Production"
    assert calls[0]["operator_id"] == "operator-8l"
    assert calls[0]["approve_initialization"] is True


def _contract_dir(repo: Path) -> Path:
    return repo / "memory" / "runtime" / "hvs_project_initialization_contracts"


def test_missing_stage85_authorization_blocks_before_manifest_write(accepted_source):
    repo, _proposal, _handoff, _presentation, _decision, acceptance = accepted_source
    authorization = _authorize(repo, acceptance)
    fake = _FakeAdapter()
    before = list(_contract_dir(repo).glob("*.json"))

    out = service.initialize_hvs_project(
        production_kickoff_authorization_id=authorization.production_kickoff_authorization_id,
        production_input=_production_input(),
        operator_id="operator-8l",
        repo_root=repo,
        hvs_repo_root="hvs",
        hvs_python_executable="py",
        recorded_at="2026-07-14",
        approve_initialization=True,
        adapter=fake,
        stage85_authorization=None,  # missing Stage 8.5 decision
    )

    assert not out.ok
    assert out.error_code == "STAGE85_AUTHORIZATION_BLOCKED"
    assert fake.calls == []  # no HVS invocation at all
    after = list(_contract_dir(repo).glob("*.json"))
    assert after == before  # no contract manifest written


def test_denied_stage85_authorization_blocks_before_manifest_write(accepted_source):
    repo, _proposal, _handoff, _presentation, _decision, acceptance = accepted_source
    authorization = _authorize(repo, acceptance)
    fake = _FakeAdapter()
    denied = Stage8_5AdapterAuthorization("DENIED", operation="initialize-project", target="")
    before = list(_contract_dir(repo).glob("*.json"))

    out = service.initialize_hvs_project(
        production_kickoff_authorization_id=authorization.production_kickoff_authorization_id,
        production_input=_production_input(),
        operator_id="operator-8l",
        repo_root=repo,
        hvs_repo_root="hvs",
        hvs_python_executable="py",
        recorded_at="2026-07-14",
        approve_initialization=True,
        adapter=fake,
        stage85_authorization=denied,
    )

    assert not out.ok
    assert out.error_code == "STAGE85_AUTHORIZATION_BLOCKED"
    assert fake.calls == []
    assert list(_contract_dir(repo).glob("*.json")) == before


def test_operation_mismatch_stage85_authorization_blocks(accepted_source):
    repo, _proposal, _handoff, _presentation, _decision, acceptance = accepted_source
    authorization = _authorize(repo, acceptance)
    fake = _FakeAdapter()
    # Authorization bound to a different operation cannot authorize init, even
    # at the service layer (operation-level gate). Target binding is enforced
    # at the adapter layer (test_stage8l_initialize_target_mismatch).
    mismatched = Stage8_5AdapterAuthorization(
        "AUTHORIZED_IN_PRINCIPLE", operation="inspect-project", target=""
    )

    out = service.initialize_hvs_project(
        production_kickoff_authorization_id=authorization.production_kickoff_authorization_id,
        production_input=_production_input(),
        operator_id="operator-8l",
        repo_root=repo,
        hvs_repo_root="hvs",
        hvs_python_executable="py",
        recorded_at="2026-07-14",
        approve_initialization=True,
        adapter=fake,
        stage85_authorization=mismatched,
    )

    assert not out.ok
    assert out.error_code == "STAGE85_AUTHORIZATION_BLOCKED"
    assert fake.calls == []


def test_static_boundaries_exclude_legacy_creator_render_assets_network_and_hvs_imports():
    combined = "\n".join(
        inspect.getsource(module)
        for module in (
            service,
            __import__("scos.control_center.hvs_project_initialization_models", fromlist=["*"]),
            __import__("scos.control_center.hvs_project_initialization_store", fromlist=["*"]),
        )
    )
    forbidden = (
        "create-project",
        "cmd_new",
        "generate_placeholders",
        "generate_voice",
        "render_hyperframes",
        "ffmpeg",
        "hyperframes",
        "materialize_asset",
        "copy_asset",
        "requests",
        "httpx",
        "urllib",
        "socket",
        "from hvs",
        "import hvs",
        "os.system",
        "shell=True",
    )
    assert not [token for token in forbidden if token in combined]
