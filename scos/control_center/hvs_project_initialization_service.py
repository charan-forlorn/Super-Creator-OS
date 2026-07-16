"""Stage 8L approval-gated HVS project initialization service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .hvs_adapter import (
    HVSAdapterConfig,
    HermesVideoStudioAdapter,
    Stage8_5AdapterAuthorization,
    Stage8_5AuthorizationError,
)
from .hvs_commercial_proposal_models import _safe_text, canonical_json, stable_id
from .hvs_contract_models import SCOSAssetRef, SCOSCaption, SCOSRenderTimelineProject, SCOSScene
from .hvs_engagement_activation_models import (
    APPROVED_FOR_PROJECT_INITIALIZATION,
    EVT_ENGAGEMENT_APPROVED,
    PAYMENT_CONFIRMATION_PENDING,
    PAYMENT_REQUIREMENT_DECLARED,
    PAYMENT_SATISFIED_BY_OPERATOR_CONFIRMATION,
    PAYMENT_NOT_APPLICABLE,
    PAYMENT_NOT_REQUIRED_BEFORE_START,
    PRODUCTION_KICKOFF_AUTHORIZATION_SCHEMA_VERSION,
    canonical_content_hash,
)
from .hvs_engagement_activation_service import _activations, _eligibility, _events, _authorizations
from .hvs_project_creation import correlation_id_for
from .hvs_project_initialization_models import (
    EVT_PROJECT_INITIALIZATION_CONFLICT,
    EVT_PROJECT_INITIALIZATION_PREPARED,
    EVT_PROJECT_INITIALIZATION_VERIFIED,
    HVS_INITIALIZATION_CONTRACT_NAME,
    HVS_INITIALIZATION_CONTRACT_SCHEMA_VERSION,
    HVS_INITIALIZATION_CONTRACT_VERSION,
    HVSProjectInitializationEvidence,
    HVSProjectInitializationResult,
    INITIALIZATION_CONFLICT,
    INITIALIZATION_PREPARED,
    INITIALIZATION_REJECTED,
    INITIALIZATION_VERIFIED,
    PROJECT_INITIALIZATION_SCHEMA_VERSION,
    ProductionInitializationContract,
    ProductionInitializationInput,
    ProductionSceneInput,
    content_hash,
    hvs_project_id_for_authorization,
    initialization_contract_id,
)
from .hvs_project_initialization_store import (
    append_project_initialization_event,
    project_initialization_path,
    read_project_initialization_events,
    write_initialization_contract_file,
)
from .hvs_schema_mapper import map_scos_to_hvs, payload_identity_hash


@dataclass(frozen=True)
class Stage8LEligibility:
    ok: bool
    blockers: tuple[str, ...]
    authorization: Any | None = None
    activation: Any | None = None


def _deny(code: str, detail: str, *, blockers: tuple[str, ...] = ()) -> HVSProjectInitializationResult:
    return HVSProjectInitializationResult(False, error_code=code, error_detail=detail, blockers=blockers)


def _is_payment_ready(authorization: Any) -> bool:
    if authorization.payment_start_requirement == PAYMENT_NOT_REQUIRED_BEFORE_START:
        return authorization.payment_requirement_status == PAYMENT_NOT_APPLICABLE
    return authorization.payment_requirement_status == PAYMENT_SATISFIED_BY_OPERATOR_CONFIRMATION


def verify_stage8l_eligibility(
    *, production_kickoff_authorization_id: str, repo_root: Any
) -> Stage8LEligibility:
    repo = Path(repo_root)
    authorization_id = _safe_text("production_kickoff_authorization_id", production_kickoff_authorization_id)
    authorization = _authorizations(repo).get(authorization_id)
    blockers: list[str] = []
    if authorization is None:
        return Stage8LEligibility(False, ("AUTHORIZATION_NOT_FOUND",))
    if authorization.schema_version != PRODUCTION_KICKOFF_AUTHORIZATION_SCHEMA_VERSION:
        blockers.append("AUTHORIZATION_SCHEMA_MISMATCH")
    payload = authorization.to_dict()
    payload.pop("deterministic_content_hash", None)
    if canonical_content_hash(payload) != authorization.deterministic_content_hash:
        blockers.append("AUTHORIZATION_CONTENT_HASH_MISMATCH")
    activation = _activations(repo).get(authorization.engagement_activation_id)
    if activation is None:
        blockers.append("ENGAGEMENT_ACTIVATION_NOT_FOUND")
    else:
        if activation.engagement_status != APPROVED_FOR_PROJECT_INITIALIZATION:
            blockers.append("ACTIVATION_NOT_APPROVED_FOR_PROJECT_INITIALIZATION")
        if activation.deterministic_content_hash != authorization.engagement_content_hash:
            blockers.append("ENGAGEMENT_CONTENT_HASH_MISMATCH")
        if activation.project_created or activation.hvs_invoked or activation.render_started or activation.assets_copied:
            blockers.append("ACTIVATION_EXTERNAL_ACTION_FLAG_SET")
        if not activation.manual_project_initialization_required:
            blockers.append("MANUAL_PROJECT_INITIALIZATION_NOT_REQUIRED")
        if activation.automation_allowed:
            blockers.append("ACTIVATION_AUTOMATION_ALLOWED")
        approval_events = tuple(
            event
            for event in _events(repo)
            if event.event_type == EVT_ENGAGEMENT_APPROVED and event.event_id == authorization.approval_event_id
        )
        if not approval_events:
            blockers.append("APPROVAL_EVENT_NOT_FOUND")
        _acceptance, _proposal, _handoff, _presentation, _decision, lineage_blockers = _eligibility(
            repo, activation.source_commercial_acceptance_id, authorization.recorded_at
        )
        blockers.extend(lineage_blockers)
    if not authorization.project_initialization_authorized:
        blockers.append("PROJECT_INITIALIZATION_NOT_AUTHORIZED")
    if authorization.project_initialization_performed or authorization.project_created or authorization.hvs_invoked:
        blockers.append("AUTHORIZATION_ALREADY_PERFORMED")
    if authorization.render_started or authorization.assets_copied or authorization.automation_allowed:
        blockers.append("AUTHORIZATION_EXTERNAL_ACTION_FLAG_SET")
    if not _is_payment_ready(authorization):
        blockers.append("PAYMENT_READINESS_NOT_SATISFIED")
    if authorization.payment_requirement_status in (PAYMENT_CONFIRMATION_PENDING, PAYMENT_REQUIREMENT_DECLARED):
        blockers.append("PAYMENT_PENDING")
    if authorization.customer_input_status != "SATISFIED_BY_OPERATOR_CONFIRMATION":
        blockers.append("CUSTOMER_INPUT_NOT_VERIFIED")
    return Stage8LEligibility(not blockers, tuple(sorted(set(blockers))), authorization, activation)


def _build_scos_project(
    *, hvs_project_id: str, production_input: ProductionInitializationInput, authorization: Any
) -> SCOSRenderTimelineProject:
    scenes: list[SCOSScene] = []
    start_ms = 0
    for order, item in enumerate(production_input.scenes):
        asset_refs = tuple(
            SCOSAssetRef(
                asset_id=_safe_text("asset_id", asset.get("asset_id")),
                asset_type=_safe_text("asset_type", asset.get("asset_type")),
                path=asset.get("path") or asset.get("asset_path"),
            )
            for asset in item.asset_refs
        )
        captions = tuple(
            SCOSCaption(
                scene_id=item.scene_id,
                text=_safe_text("caption_text", caption.get("text")),
                start_ms=int(caption.get("start_ms")),
                end_ms=int(caption.get("end_ms")),
            )
            for caption in item.captions
        )
        scenes.append(
            SCOSScene(
                scene_id=_safe_text("scene_id", item.scene_id),
                order=order,
                start_ms=start_ms,
                duration_ms=int(item.duration_ms),
                intent=_safe_text("intent", item.intent),
                visual_description=_safe_text("visual_description", item.visual_description),
                text_overlay=_safe_text("text_overlay", item.text_overlay),
                asset_refs=asset_refs,
                captions=captions,
                transition="cut",
            )
        )
        start_ms += int(item.duration_ms)
    return SCOSRenderTimelineProject(
        project_id=hvs_project_id,
        width=int(production_input.width),
        height=int(production_input.height),
        fps=int(production_input.fps),
        scenes=tuple(scenes),
        request_id=authorization.production_kickoff_authorization_id,
        run_id=authorization.engagement_activation_id,
        selected_preset=production_input.selected_preset,
        metadata=(
            ("scos_project_id", authorization.project_id),
            ("commercial_scope_id", authorization.commercial_scope_id),
            ("production_kickoff_authorization_id", authorization.production_kickoff_authorization_id),
        ),
    )


def build_production_initialization_contract(
    *,
    production_kickoff_authorization_id: str,
    production_input: ProductionInitializationInput,
    repo_root: Any,
) -> HVSProjectInitializationResult:
    try:
        eligibility = verify_stage8l_eligibility(
            production_kickoff_authorization_id=production_kickoff_authorization_id,
            repo_root=repo_root,
        )
        if not eligibility.ok:
            return _deny("STAGE8L_ELIGIBILITY_BLOCKED", ",".join(eligibility.blockers), blockers=eligibility.blockers)
        title = _safe_text("title", production_input.title)
        language = _safe_text("language", production_input.language)
        if language not in ("en", "th"):
            raise ValueError("language must be en or th")
        hvs_project_id = hvs_project_id_for_authorization(production_kickoff_authorization_id)
        scos_project = _build_scos_project(
            hvs_project_id=hvs_project_id,
            production_input=production_input,
            authorization=eligibility.authorization,
        )
        mapped = map_scos_to_hvs(scos_project, validate=True)
        if not mapped.ok:
            return _deny("STAGE2_MAPPING_FAILED", mapped.error.error_detail if mapped.error else "Stage 2 mapping failed")
        stage2_payload = mapped.payload
        stage2_hash = payload_identity_hash(stage2_payload)
        hvs_contract = {
            "schema_version": HVS_INITIALIZATION_CONTRACT_SCHEMA_VERSION,
            "contract_name": HVS_INITIALIZATION_CONTRACT_NAME,
            "contract_version": HVS_INITIALIZATION_CONTRACT_VERSION,
            "project": {
                "project_id": hvs_project_id,
                "title": title,
                "language": language,
                "metadata": {
                    "scos_project_id": eligibility.authorization.project_id,
                    "production_kickoff_authorization_id": production_kickoff_authorization_id,
                },
            },
            "timeline": stage2_payload,
            "metadata": {
                "source": "scos-stage8l",
                "engagement_activation_id": eligibility.authorization.engagement_activation_id,
                "commercial_scope_id": eligibility.authorization.commercial_scope_id,
            },
        }
        core = {
            "production_kickoff_authorization_id": production_kickoff_authorization_id,
            "engagement_activation_id": eligibility.authorization.engagement_activation_id,
            "scos_project_id": eligibility.authorization.project_id,
            "hvs_project_id": hvs_project_id,
            "title": title,
            "language": language,
            "stage2_payload_hash": stage2_hash,
            "hvs_initialization_contract": hvs_contract,
        }
        contract_hash = content_hash(core)
        contract_id = initialization_contract_id({"content_hash": contract_hash, "hvs_project_id": hvs_project_id})
        contract = ProductionInitializationContract(
            PROJECT_INITIALIZATION_SCHEMA_VERSION,
            contract_id,
            production_kickoff_authorization_id,
            eligibility.authorization.engagement_activation_id,
            eligibility.authorization.project_id,
            hvs_project_id,
            title,
            language,
            stage2_hash,
            contract_hash,
            hvs_contract,
        )
        return HVSProjectInitializationResult(True, contract=contract)
    except ValueError as exc:
        return _deny("INVALID_PRODUCTION_INPUT", str(exc))


def prepare_hvs_project_initialization(
    *,
    production_kickoff_authorization_id: str,
    production_input: ProductionInitializationInput,
    operator_id: str,
    repo_root: Any,
    recorded_at: str,
) -> HVSProjectInitializationResult:
    try:
        operator = _safe_text("operator_id", operator_id)
        result = build_production_initialization_contract(
            production_kickoff_authorization_id=production_kickoff_authorization_id,
            production_input=production_input,
            repo_root=repo_root,
        )
        if not result.ok or result.contract is None:
            return result
        write_initialization_contract_file(
            repo_root=repo_root,
            contract_id=result.contract.initialization_contract_id,
            contract=result.contract.hvs_initialization_contract,
        )
        append_project_initialization_event(
            audit_log_path=project_initialization_path(repo_root),
            event_type=EVT_PROJECT_INITIALIZATION_PREPARED,
            subject_id=result.contract.initialization_contract_id,
            operator_id=operator,
            recorded_at=recorded_at,
            record=result.contract.to_dict() | {"initialization_status": INITIALIZATION_PREPARED},
        )
        return result
    except ValueError as exc:
        return _deny("INVALID_INPUT", str(exc))


def _semantic_matches(contract: ProductionInitializationContract, init_payload: dict[str, Any], inspect_payload: dict[str, Any]) -> bool:
    initialized = inspect_payload.get("initialization") or {}
    timeline = inspect_payload.get("timeline") or {}
    return (
        init_payload.get("requested_project_id") == contract.hvs_project_id
        and init_payload.get("actual_project_id") == contract.hvs_project_id
        and init_payload.get("actual_payload_hash") == contract.stage2_payload_hash
        and init_payload.get("expected_payload_hash") == contract.stage2_payload_hash
        and init_payload.get("project_verified") is True
        and inspect_payload.get("project_id") == contract.hvs_project_id
        and inspect_payload.get("title") == contract.title
        and inspect_payload.get("language") == contract.language
        and timeline.get("valid") is True
        and initialized.get("payload_hash") == contract.stage2_payload_hash
        and inspect_payload.get("voice_generated") is False
        and inspect_payload.get("placeholder_assets_generated") is False
        and inspect_payload.get("render_started") is False
    )


def initialize_hvs_project(
    *,
    production_kickoff_authorization_id: str,
    production_input: ProductionInitializationInput,
    operator_id: str,
    repo_root: Any,
    hvs_repo_root: Any,
    hvs_python_executable: Any,
    recorded_at: str,
    approve_initialization: bool,
    adapter: HermesVideoStudioAdapter | None = None,
    stage85_authorization: Any = None,
) -> HVSProjectInitializationResult:
    # --- Stage 8.5 authorization gate (Cohort 9F) ---------------------------
    # Evaluated FIRST, before any filesystem/project/persistent side effect.
    # The explicit operator/engagement approval (approve_initialization) is a
    # necessary but NOT sufficient precondition; a valid, correctly bound
    # Stage 8.5 activation decision (produced by
    # evaluate_adapter_activation_authorization) is also required before any
    # mutating HVS operation. Fail-closed: missing/malformed/unknown/denied/
    # stale/mismatched authorization prevents even the contract-manifest write.
    if approve_initialization is not True:
        return _deny("INITIALIZATION_APPROVAL_REQUIRED", "explicit operator initialization approval is required")
    if not isinstance(stage85_authorization, Stage8_5AdapterAuthorization):
        # Accept a raw result dict or AdapterActivationAuthorizationResult and
        # normalize it; a missing decision fails closed.
        stage85_authorization = Stage8_5AdapterAuthorization.from_result(
            stage85_authorization, operation="initialize-project", target=""
        )
    try:
        stage85_authorization.require_for(operation="initialize-project", target="")
    except Stage8_5AuthorizationError as exc:
        return _deny("STAGE85_AUTHORIZATION_BLOCKED", exc.reason)
    try:
        operator = _safe_text("operator_id", operator_id)
        prepared = prepare_hvs_project_initialization(
            production_kickoff_authorization_id=production_kickoff_authorization_id,
            production_input=production_input,
            operator_id=operator,
            repo_root=repo_root,
            recorded_at=recorded_at,
        )
        if not prepared.ok or prepared.contract is None:
            return prepared
        contract = prepared.contract
        contract_path = write_initialization_contract_file(
            repo_root=repo_root,
            contract_id=contract.initialization_contract_id,
            contract=contract.hvs_initialization_contract,
        )
        hvs_adapter = adapter or HermesVideoStudioAdapter(
            HVSAdapterConfig(
                hvs_repo_path=str(hvs_repo_root),
                python_executable=str(hvs_python_executable),
                timeout_seconds=120,
                require_repo_local_python=True,
            ),
            stage85_authorization=stage85_authorization,
        )
        init_result = hvs_adapter.initialize_project(
            project_id=contract.hvs_project_id,
            contract_path=str(contract_path),
            expected_payload_hash=contract.stage2_payload_hash,
            approve_initialization=True,
            request_id=contract.initialization_contract_id,
            stage85_authorization=stage85_authorization,
        )
        init_payload = init_result.get("payload") or {}
        if init_result.get("ok") is not True:
            status = INITIALIZATION_CONFLICT if init_payload.get("status") == "conflict" else INITIALIZATION_REJECTED
            evidence = _evidence(
                contract=contract,
                status=status,
                init_result=init_result,
                inspect_result=None,
                semantic_ok=False,
                error_code=init_payload.get("error_code") or init_result.get("error_kind"),
                error_detail=init_payload.get("error_detail") or init_result.get("error_detail"),
            )
            if status == INITIALIZATION_CONFLICT:
                _append_evidence(repo_root, operator, recorded_at, EVT_PROJECT_INITIALIZATION_CONFLICT, evidence)
            return HVSProjectInitializationResult(False, contract=contract, evidence=evidence, error_code=evidence.error_code, error_detail=evidence.error_detail, blockers=(status,))
        inspect_result = hvs_adapter.inspect_project(
            project_id=contract.hvs_project_id,
            request_id=contract.initialization_contract_id,
        )
        inspect_payload = inspect_result.get("payload") or {}
        semantic_ok = inspect_result.get("ok") is True and _semantic_matches(contract, init_payload, inspect_payload)
        evidence = _evidence(
            contract=contract,
            status=INITIALIZATION_VERIFIED if semantic_ok else INITIALIZATION_REJECTED,
            init_result=init_result,
            inspect_result=inspect_result,
            semantic_ok=semantic_ok,
            error_code=None if semantic_ok else "SEMANTIC_VERIFICATION_FAILED",
            error_detail=None if semantic_ok else "HVS inspection did not match the SCOS initialization contract",
        )
        if not semantic_ok:
            return HVSProjectInitializationResult(False, contract=contract, evidence=evidence, error_code=evidence.error_code, error_detail=evidence.error_detail, blockers=("SEMANTIC_VERIFICATION_FAILED",))
        _append_evidence(repo_root, operator, recorded_at, EVT_PROJECT_INITIALIZATION_VERIFIED, evidence)
        return HVSProjectInitializationResult(True, contract=contract, evidence=evidence)
    except ValueError as exc:
        return _deny("INVALID_INPUT", str(exc))


def _evidence(
    *,
    contract: ProductionInitializationContract,
    status: str,
    init_result: dict[str, Any],
    inspect_result: dict[str, Any] | None,
    semantic_ok: bool,
    error_code: str | None,
    error_detail: str | None,
) -> HVSProjectInitializationEvidence:
    init_payload = init_result.get("payload") or {}
    inspect_exit = None if inspect_result is None else inspect_result.get("exit_code")
    return HVSProjectInitializationEvidence(
        schema_version=PROJECT_INITIALIZATION_SCHEMA_VERSION,
        initialization_contract_id=contract.initialization_contract_id,
        production_kickoff_authorization_id=contract.production_kickoff_authorization_id,
        engagement_activation_id=contract.engagement_activation_id,
        scos_project_id=contract.scos_project_id,
        hvs_project_id=contract.hvs_project_id,
        stage2_payload_hash=contract.stage2_payload_hash,
        initialization_status=status,
        hvs_initialize_exit_code=init_result.get("exit_code"),
        hvs_inspect_exit_code=inspect_exit,
        project_created=bool(init_payload.get("project_created")),
        identical_replay=bool(init_payload.get("identical_replay")),
        project_verified=bool(init_payload.get("project_verified")),
        semantic_comparison_passed=semantic_ok,
        correlation_id=correlation_id_for(contract.stage2_payload_hash),
        hvs_project_relative_path=f"projects/{contract.hvs_project_id}",
        error_code=error_code,
        error_detail=error_detail,
    )


def _append_evidence(repo_root: Any, operator_id: str, recorded_at: str, event_type: str, evidence: HVSProjectInitializationEvidence) -> None:
    append_project_initialization_event(
        audit_log_path=project_initialization_path(repo_root),
        event_type=event_type,
        subject_id=evidence.initialization_contract_id,
        operator_id=operator_id,
        recorded_at=recorded_at,
        record=evidence.to_dict(),
    )


def list_project_initialization_evidence(*, repo_root: Any) -> tuple[dict[str, Any], ...]:
    return tuple(event.record for event in read_project_initialization_events(audit_log_path=project_initialization_path(repo_root)))


def production_input_from_dict(data: dict[str, Any]) -> ProductionInitializationInput:
    scenes = tuple(
        ProductionSceneInput(
            scene_id=str(item["scene_id"]),
            duration_ms=int(item["duration_ms"]),
            intent=str(item["intent"]),
            visual_description=str(item["visual_description"]),
            text_overlay=str(item["text_overlay"]),
            asset_refs=tuple(dict(asset) for asset in item.get("asset_refs", ())),
            captions=tuple(dict(caption) for caption in item.get("captions", ())),
        )
        for item in data.get("scenes", ())
    )
    return ProductionInitializationInput(
        title=str(data["title"]),
        language=str(data.get("language", "en")),
        width=int(data.get("width", 1080)),
        height=int(data.get("height", 1920)),
        fps=int(data.get("fps", 30)),
        selected_preset=str(data.get("selected_preset", "standard")),
        scenes=scenes,
    )
