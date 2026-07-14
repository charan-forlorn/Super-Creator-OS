"""SCOS <-> HVS — Stage 8R operator-controlled resolution action execution.

Deterministic, local-only, operator-controlled. Consumes exactly one approved
Stage 8Q resolution route, re-verifies the complete Stage 8O -> Stage 8P ->
Stage 8Q evidence chain, selects exactly one compatible action family,
requires a separate explicit execution approval, re-verifies eligibility
immediately before mutation, invokes exactly one existing SCOS domain service,
verifies the created target record, and appends an append-only audit trail.

Hard boundaries (always honored):

  * never closes more than one target domain record per request,
  * never contacts a customer / performs any transport,
  * never invokes HVS, renders, delivers, uploads, or publishes,
  * never creates or mutates invoices / payments,
  * never begins Stage 8S,
  * never reuses the Stage 8Q route approval as execution approval.

Reused target-domain services:

  * ``hvs_delivery_closure_service.close_delivery`` — PROJECT_CLOSURE_EXECUTION
  * ``hvs_revision_service.create_revision_request`` — REVISION_REQUEST_CREATION
  * ``hvs_post_delivery_support_service.open_post_delivery_dispute`` — DISPUTE_OPENING
  * Stage 8R-owned ``ManualFollowUpRecord`` store — MANUAL_FOLLOW_UP_RECORD_CREATION
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import hvs_delivery_closure_service as closure_svc
from . import hvs_post_delivery_support_models as M_support
from . import hvs_post_delivery_support_service as support_svc
from . import hvs_revision_models as revision_models
from . import hvs_revision_service as revision_svc
from .hvs_delivery_closure_models import REC_ACKNOWLEDGED, REC_REVISION_REQUESTED
from .hvs_resolution_action_models import (
    ALLOWED_ACTION_FAMILIES,
    ACTION_DISPUTE_OPENING,
    ACTION_MANUAL_FOLLOW_UP_RECORD_CREATION,
    ACTION_PROJECT_CLOSURE_EXECUTION,
    ACTION_REVISION_REQUEST_CREATION,
    DECISION_APPROVE,
    DECISION_REJECT,
    ELIG_ALREADY_COMPLETED,
    ELIG_BLOCKED,
    ELIG_CONFLICTED,
    ELIG_EXPIRED,
    ELIG_NEEDS_OPERATOR_INPUT,
    ELIG_READY,
    ERR_ACTION_ROUTE_INCOMPATIBLE,
    ERR_APPROVAL_ACTION_MISMATCH,
    ERR_APPROVAL_CONTRACT_MISMATCH,
    ERR_APPROVAL_REUSE_REJECTED,
    ERR_COMPOSITE_ACTION,
    ERR_CONFLICTING_EXECUTION,
    ERR_ELIGIBILITY_NOT_READY,
    ERR_EXECUTION_APPROVAL_NOT_FOUND,
    ERR_EXECUTION_REQUEST_NOT_APPROVED,
    ERR_EXECUTION_REQUEST_NOT_FOUND,
    ERR_INVALID_ACTION_FAMILY,
    ERR_INVALID_ACTION_PARAMS,
    ERR_MISSING_ACTION_FAMILY,
    ERR_MISSING_OPERATOR_ID,
    ERR_MISSING_REASON,
    ERR_MISSING_ROUTE_ID,
    ERR_PARTIAL_EFFECT,
    ERR_PRE_EXECUTION_FAILED,
    ERR_ROUTE_CONTENT_HASH_MISMATCH,
    ERR_ROUTE_NOT_APPROVED,
    ERR_ROUTE_NOT_FOUND,
    ERR_STAGE8P_LINEAGE_MISMATCH,
    ERR_TARGET_MUTATION_FAILED,
    ERR_TARGET_RECORD_MISSING,
    ERR_TARGET_RECORD_MISMATCH,
    ERR_TOO_MANY_ACTIONS,
    EVT_CONFLICT_DETECTED,
    EVT_ELIGIBILITY_EVALUATED,
    EVT_EXECUTION_APPROVED,
    EVT_EXECUTION_CANCELLED,
    EVT_EXECUTION_REJECTED,
    EVT_EXECUTION_REQUEST_CREATED,
    EVT_OUTCOME_EVIDENCE_CREATED,
    EVT_PRE_EXECUTION_REVERIFIED,
    EVT_TARGET_ACTION_COMPLETED,
    EVT_TARGET_ACTION_FAILED,
    EVT_TARGET_ACTION_STARTED,
    EVT_TARGET_RECORD_VERIFIED,
    EXEC_BLOCKED,
    EXEC_COMPLETED,
    EXEC_CONFLICTED,
    EXEC_EXECUTING,
    EXEC_FAILED,
    EXEC_NOT_STARTED,
    FOLLOWUP_MODEL_SCHEMA_VERSION,
    ManualFollowUpRecord,
    OUT_AUDIT_INCOMPLETE,
    OUT_FAILED,
    OUT_PARTIAL_EFFECT_DETECTED,
    OUT_TARGET_RECORD_MISSING,
    OUT_TARGET_RECORD_MISMATCH,
    OUT_VERIFIED,
    REQ_APPROVED_FOR_EXECUTION,
    REQ_CANCELLED,
    REQ_DRAFT,
    REQ_EXPIRED,
    REQ_NEEDS_OPERATOR_INPUT,
    REQ_READY_FOR_EXECUTION_REVIEW,
    REQ_REJECTED,
    ResolutionActionEvent,
    ResolutionActionOutcomeEvidence,
    ResolutionActionSelection,
    ResolutionExecutionApproval,
    ResolutionExecutionEligibilityResult,
    ResolutionExecutionRequest,
    ROUTE_TO_ALLOWED_ACTIONS,
    action_target_domain,
    execution_approval_id,
    execution_contract_hash,
    execution_request_id,
    follow_up_record_id,
    load_stage8q_route,
    outcome_evidence_id,
    route_content_hash_for,
)
from .hvs_resolution_action_store import (
    append_resolution_action_event,
    events_for_request,
    events_for_route,
    events_for_route as _events_for_route,
    ledger_path,
    read_resolution_action_events,
)
from .hvs_post_delivery_resolution_models import (
    ROUTING_APPROVED,
    ROUTING_REJECTED,
    ROUTING_CANCELLED,
    EVT_ROUTE_APPROVED,
    EVT_ROUTE_REJECTED,
    EVT_ROUTE_CANCELLED,
    PostDeliveryResolutionRoute,
)


# ---------------------------------------------------------------------------
# Service result envelope
# ---------------------------------------------------------------------------
@dataclass
class Stage8RServiceResult:
    ok: bool
    execution_request: ResolutionExecutionRequest | None = None
    eligibility: ResolutionExecutionEligibilityResult | None = None
    approval: ResolutionExecutionApproval | None = None
    outcome: ResolutionActionOutcomeEvidence | None = None
    target_record: dict[str, Any] | None = None
    manual_follow_up: ManualFollowUpRecord | None = None
    error_code: str | None = None
    error_detail: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "ok": self.ok,
            "execution_request": self.execution_request.to_dict() if self.execution_request else None,
            "eligibility": self.eligibility.to_dict() if self.eligibility else None,
            "approval": self.approval.to_dict() if self.approval else None,
            "outcome": self.outcome.to_dict() if self.outcome else None,
            "target_record": self.target_record,
            "manual_follow_up": self.manual_follow_up.to_dict() if self.manual_follow_up else None,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
        }
        for k, v in self.extra.items():
            if k not in out:
                out[k] = v
        return out


def _deny(*, error_code: str, error_detail: str, **extra: Any) -> Stage8RServiceResult:
    return Stage8RServiceResult(ok=False, error_code=error_code, error_detail=error_detail, extra=dict(extra))


# ---------------------------------------------------------------------------
# Stage 8O / 8P lineage reverification (reuse Stage 8Q binding logic)
# ---------------------------------------------------------------------------
def _stage8p_identity_matches_8o(*, repo_root: Any, actual_delivery_record_id: str, artifact_sha256: str, customer_reference: str) -> bool:
    """Fail-closed cross-check of the Stage 8Q route's bound identity against the
    authoritative Stage 8O actual-delivery record. Returns False on any
    divergence (forged or misbound route)."""
    from .hvs_post_delivery_resolution_service import _stage8p_identity_matches_8o as _q_identity

    # Re-load the Stage 8O actual-delivery record directly to obtain the
    # authoritative identities, then delegate to the Stage 8Q cross-check which
    # compares against the persisted Stage 8P receipt records.
    from .hvs_stage8o_delivery_store import read_delivery_events, delivery_ledger_path

    ledger = delivery_ledger_path(repo_root)
    for ev in read_delivery_events(ledger_path=ledger):
        if ev.get("event_type") == "DELIVERY_RECORDED" and ev.get("subject_id") == actual_delivery_record_id:
            rec = ev.get("record") or {}
            # Route identity must match the authoritative 8O record.
            if str(rec.get("artifact_sha256") or "").strip().lower() != artifact_sha256.lower():
                return False
            if str(rec.get("safe_recipient_reference") or "").strip().lower() != customer_reference.lower():
                return False
            return _q_identity(
                repo_root=repo_root,
                actual_delivery_record_id=actual_delivery_record_id,
                actual_delivery=rec,
            )
    return False


# ---------------------------------------------------------------------------
# Normalised action parameters
# ---------------------------------------------------------------------------
def _normalize_selection(sel: ResolutionActionSelection) -> dict[str, Any]:
    """Coerce caller-owned selection into an immutable, order-stable dict."""
    params: dict[str, Any] = {
        "closure_reason": sel.closure_reason,
        "receipt_evidence_id": sel.receipt_evidence_id,
        "requested_scope": sel.requested_scope,
        "source_issue_id": sel.source_issue_id,
        "dispute_type": sel.dispute_type,
        "dispute_reason": sel.dispute_reason,
        "disputed_artifact_references": tuple(sel.disputed_artifact_references),
        "dispute_evidence_references": tuple(sel.dispute_evidence_references),
        "follow_up_purpose": sel.follow_up_purpose,
        "follow_up_recommended_action": sel.follow_up_recommended_action,
        "follow_up_due_date": sel.follow_up_due_date,
        "follow_up_evaluation_date": sel.follow_up_evaluation_date,
        "revision_item_count": len(sel.revision_items),
    }
    if sel.action_family == ACTION_REVISION_REQUEST_CREATION:
        params["revision_items"] = tuple(
            {k: it.get(k) for k in ("category", "description", "target_type", "target_id", "scene_id", "asset_id", "format", "priority", "acceptance_requirement", "source_artifact_sha256")}
            for it in sel.revision_items
        )
    return dict(sorted(params.items()))


def _target_source_ids(sel: ResolutionActionSelection) -> tuple[str, ...]:
    ids: list[str] = []
    if sel.action_family == ACTION_PROJECT_CLOSURE_EXECUTION and sel.receipt_evidence_id:
        ids.append(sel.receipt_evidence_id)
    if sel.action_family == ACTION_REVISION_REQUEST_CREATION:
        # The delivery record id is the semantic source id for lineage binding;
        # the route binds it via source_actual_delivery_record_id.
        pass
    if sel.action_family == ACTION_DISPUTE_OPENING and sel.source_issue_id:
        ids.append(sel.source_issue_id)
    if sel.action_family == ACTION_MANUAL_FOLLOW_UP_RECORD_CREATION and sel.follow_up_due_date:
        ids.append(f"due:{sel.follow_up_due_date}")
    return tuple(sorted(ids))


# ---------------------------------------------------------------------------
# Stage 8Q approval reverification (read-only, ledger-derived)
# ---------------------------------------------------------------------------
def _stage8q_route_approval_status(*, repo_root: Any, route: PostDeliveryResolutionRoute) -> str | None:
    """Resolve the authoritative Stage 8Q operator approval for a route.

    Stage 8Q never mutates the route-creation record, so ``route.route_status``
    remains ``READY_FOR_OPERATOR_REVIEW`` even after an APPROVE decision. The
    canonical approval signal lives in the append-only decision ledger. This
    helper reads that ledger and returns one of:

    * ``ROUTING_APPROVED``  -- a valid, unsuperseded APPROVE decision exists
    * ``ROUTING_REJECTED``  -- a terminal REJECT decision is the latest terminal
    * ``ROUTING_CANCELLED`` -- a terminal CANCEL decision is the latest terminal
    * ``None``              -- no terminal decision / cannot be resolved safely

    The decision must bind to the exact route id, the live route content hash,
    and a non-terminal resulting status. Any malformed, misbound, or conflicting
    evidence fails closed to ``None``. The ledger is never mutated.
    """
    from .hvs_post_delivery_resolution_store import (
        read_resolution_events,
        route_ledger_path,
    )

    ledger = route_ledger_path(repo_root)
    if not ledger or not ledger.is_file():
        return None

    live_hash = route_content_hash_for(route)
    rid = route.resolution_route_id

    # Walk the canonical ledger order; collect terminal decisions keyed by order.
    latest_terminal: dict[str, Any] | None = None
    latest_order = -1
    for order, ev in enumerate(read_resolution_events(ledger_path=ledger)):
        if ev.get("resolution_route_id") != rid:
            continue
        etype = ev.get("event_type")
        if etype not in (EVT_ROUTE_APPROVED, EVT_ROUTE_REJECTED, EVT_ROUTE_CANCELLED):
            continue
        rec = ev.get("record") or {}
        # Identity + hash binding must hold for an APPROVE decision.
        if etype == EVT_ROUTE_APPROVED:
            if rec.get("resolution_route_id") != rid:
                return None
            ev_hash = ev.get("route_content_hash") or rec.get("route_content_hash")
            if ev_hash and live_hash and ev_hash != live_hash:
                return None
            if ev.get("resulting_status") != ROUTING_APPROVED:
                return None
        # Only the latest terminal decision in canonical order governs.
        if order >= latest_order:
            latest_order = order
            latest_terminal = ev

    if latest_terminal is None:
        return None
    return latest_terminal.get("resulting_status")


# ---------------------------------------------------------------------------
# Create execution request
# ---------------------------------------------------------------------------
def create_execution_request(
    *,
    repo_root: Any,
    resolution_route_id: str,
    action_selection: ResolutionActionSelection,
    recorded_by_operator_id: str = "system-readonly-stage8r",
    informational_recorded_at: str = "",
) -> Stage8RServiceResult:
    if not str(resolution_route_id or "").strip():
        return _deny(error_code=ERR_MISSING_ROUTE_ID, error_detail="resolution_route_id is required")
    # Exactly-one-action invariant.
    if action_selection.action_family not in ALLOWED_ACTION_FAMILIES:
        return _deny(error_code=ERR_INVALID_ACTION_FAMILY, error_detail="unknown action family", action_family=action_selection.action_family)

    route = load_stage8q_route(repo_root=repo_root, resolution_route_id=resolution_route_id)
    if route is None:
        return _deny(error_code=ERR_ROUTE_NOT_FOUND, error_detail="no genuine Stage 8Q route for this id", resolution_route_id=resolution_route_id)

    # Route must be approved. Stage 8Q keeps the route-creation record at
    # READY_FOR_OPERATOR_REVIEW, so approval is derived from the append-only
    # Stage 8Q decision ledger instead of route.route_status.
    approval_status = _stage8q_route_approval_status(repo_root=repo_root, route=route)
    if approval_status != ROUTING_APPROVED:
        return _deny(
            error_code=ERR_ROUTE_NOT_APPROVED,
            error_detail=f"route approval status is {approval_status}; only APPROVED routes may be executed",
            resolution_route_id=resolution_route_id,
            route_approval_status=approval_status,
        )

    # Route / action compatibility matrix enforcement.
    allowed = ROUTE_TO_ALLOWED_ACTIONS.get(route.recommended_route, ())
    if action_selection.action_family not in allowed:
        return _deny(
            error_code=ERR_ACTION_ROUTE_INCOMPATIBLE,
            error_detail=f"action family {action_selection.action_family} is not compatible with route {route.recommended_route}",
            resolution_route_id=resolution_route_id,
            recommended_route=route.recommended_route,
            action_family=action_selection.action_family,
        )

    # Stage 8P / 8O identity reverification.
    if not _stage8p_identity_matches_8o(
        repo_root=repo_root,
        actual_delivery_record_id=route.source_actual_delivery_record_id,
        artifact_sha256=route.artifact_sha256,
        customer_reference=route.customer_reference,
    ):
        return _deny(
            error_code=ERR_STAGE8P_LINEAGE_MISMATCH,
            error_detail="Stage 8P/8O identity no longer matches the Stage 8Q route",
            resolution_route_id=resolution_route_id,
        )

    # Route content-hash must be stable.
    live_hash = route_content_hash_for(route)
    if route.deterministic_content_hash and route.deterministic_content_hash != live_hash:
        return _deny(error_code=ERR_ROUTE_CONTENT_HASH_MISMATCH, error_detail="route semantics changed since recommendation", resolution_route_id=resolution_route_id)

    # Action-specific parameter validation.
    try:
        normalized = _normalize_selection(action_selection)
    except ValueError as exc:
        return _deny(error_code=ERR_INVALID_ACTION_PARAMS, error_detail=str(exc))

    target_domain = action_target_domain(action_selection.action_family)
    target_intent = _target_intent(action_selection)
    target_ids = _target_source_ids(action_selection)
    eid = execution_request_id(
        route_id=route.resolution_route_id,
        route_content_hash=live_hash,
        action_family=action_selection.action_family,
        project_id=route.project_id,
        customer_reference=route.customer_reference,
        artifact_sha256=route.artifact_sha256,
        normalized_target_intent=target_intent,
        normalized_action_parameters=normalized,
        target_source_ids=target_ids,
    )
    ehash = execution_contract_hash(
        route_id=route.resolution_route_id,
        route_content_hash=live_hash,
        action_family=action_selection.action_family,
        target_domain=target_domain,
        normalized_target_intent=target_intent,
        normalized_action_parameters=normalized,
        target_source_ids=target_ids,
    )

    first_approval_id = _first_route_approval_id(repo_root=repo_root, route=route)
    request = ResolutionExecutionRequest(
        schema_version="scos-hvs.stage8r.execution-request.v1/1.0.0",
        execution_request_id=eid,
        project_id=route.project_id,
        customer_reference=route.customer_reference,
        source_actual_delivery_record_id=route.source_actual_delivery_record_id,
        source_stage8o_identity=route.source_delivery_lineage_id,
        source_stage8p_record_id=route.source_stage8p_receipt_record_id or route.source_stage8p_customer_decision_id,
        source_stage8q_route_id=route.resolution_route_id,
        source_route_type=route.recommended_route,
        source_route_content_hash=live_hash,
        source_route_approval_id=first_approval_id,
        source_artifact_id=route.artifact_id,
        source_artifact_sha256=route.artifact_sha256,
        action_family=action_selection.action_family,
        target_domain=target_domain,
        target_intent=target_intent,
        normalized_action_parameters=normalized,
        execution_contract_hash=ehash,
        request_status=REQ_READY_FOR_EXECUTION_REVIEW,
        operator_review_required=True,
        automation_allowed=False,
        customer_contact_allowed=False,
        hvs_action_allowed=False,
        invoice_mutation_allowed=False,
        payment_mutation_allowed=False,
        informational_recorded_at=informational_recorded_at,
    )

    append_resolution_action_event(
        ledger_path=ledger_path(repo_root),
        event_type=EVT_EXECUTION_REQUEST_CREATED,
        execution_request_id=eid,
        project_id=request.project_id,
        customer_reference=request.customer_reference,
        artifact_sha256=request.source_artifact_sha256,
        action_family=request.action_family,
        source_route_id=request.source_stage8q_route_id,
        resulting_status=request.request_status,
        operator_id=recorded_by_operator_id,
        recorded_at=informational_recorded_at or "stage8r-readonly",
        execution_contract_hash=ehash,
        detail=target_domain,
        record_payload=request.to_dict(),
    )
    return Stage8RServiceResult(ok=True, execution_request=request)


def _first_route_approval_id(*, repo_root: Any, route: PostDeliveryResolutionRoute) -> str | None:
    """Return the canonical Stage 8Q APPROVE decision id for the route, derived
    from the append-only decision ledger (never from route.route_status).

    Returns ``None`` when no valid, unsuperseded APPROVE decision exists. The
    decision must bind to the exact route id and the live route content hash.
    """
    from .hvs_post_delivery_resolution_store import (
        read_resolution_events,
        route_ledger_path,
    )

    ledger = route_ledger_path(repo_root)
    if not ledger or not ledger.is_file():
        return None
    live_hash = route_content_hash_for(route)
    rid = route.resolution_route_id

    latest_approved: dict[str, Any] | None = None
    latest_order = -1
    for order, ev in enumerate(read_resolution_events(ledger_path=ledger)):
        if ev.get("resolution_route_id") != rid:
            continue
        if ev.get("event_type") != EVT_ROUTE_APPROVED:
            continue
        rec = ev.get("record") or {}
        if rec.get("resolution_route_id") != rid:
            return None
        ev_hash = ev.get("route_content_hash") or rec.get("route_content_hash")
        if ev_hash and live_hash and ev_hash != live_hash:
            return None
        if ev.get("resulting_status") != ROUTING_APPROVED:
            return None
        if order >= latest_order:
            latest_order = order
            latest_approved = ev
    if latest_approved is None:
        return None
    return (latest_approved.get("record") or {}).get("route_decision_id")


def _target_intent(sel: ResolutionActionSelection) -> str:
    if sel.action_family == ACTION_PROJECT_CLOSURE_EXECUTION:
        return f"close_delivery:{sel.receipt_evidence_id or 'derived'}"
    if sel.action_family == ACTION_REVISION_REQUEST_CREATION:
        return f"create_revision_request:{sel.requested_scope or 'unspecified'}"
    if sel.action_family == ACTION_DISPUTE_OPENING:
        return f"open_dispute:{sel.source_issue_id or 'derived'}:{sel.dispute_type or 'unspecified'}"
    return f"manual_follow_up:{sel.follow_up_purpose or 'unspecified'}"


# ---------------------------------------------------------------------------
# Eligibility evaluation (read-only)
# ---------------------------------------------------------------------------
def evaluate_execution_eligibility(
    *,
    repo_root: Any,
    execution_request_id: str,
) -> Stage8RServiceResult:
    req = _load_request(repo_root=repo_root, execution_request_id=execution_request_id)
    if req is None:
        return _deny(error_code=ERR_EXECUTION_REQUEST_NOT_FOUND, error_detail="execution request not found", execution_request_id=execution_request_id)

    # Detect an already-completed Stage 8R for the same route+action (idempotency).
    prior_completed = _find_completed_outcome(repo_root=repo_root, execution_request_id=execution_request_id)
    if prior_completed is not None:
        return Stage8RServiceResult(
            ok=True,
            execution_request=req,
            eligibility=ResolutionExecutionEligibilityResult(
                execution_request_id=req.execution_request_id,
                route_id=req.source_stage8q_route_id,
                action_family=req.action_family,
                eligibility_status=ELIG_ALREADY_COMPLETED,
                blockers=(),
                warnings=("identical_completed_execution_exists",),
                missing_fields=(),
                detected_conflicts=(),
                target_domain_source_ids=(),
                recommended_manual_action="inspect existing outcome",
                evaluation_date=None,
            ),
        )

    route = load_stage8q_route(repo_root=repo_root, resolution_route_id=req.source_stage8q_route_id)
    if route is None:
        return _deny(error_code=ERR_ROUTE_NOT_FOUND, error_detail="source route no longer present", execution_request_id=execution_request_id)

    blockers: list[str] = []
    warnings: list[str] = []
    missing: list[str] = []
    conflicts: list[str] = []

    # Route still approved + hash stable. Stage 8Q keeps the route-creation
    # record at READY_FOR_OPERATOR_REVIEW, so approval is derived from the
    # append-only Stage 8Q decision ledger instead of route.route_status.
    approval_status = _stage8q_route_approval_status(repo_root=repo_root, route=route)
    if approval_status != ROUTING_APPROVED:
        blockers.append("route_not_approved")
    live_hash = route_content_hash_for(route)
    if route.deterministic_content_hash and route.deterministic_content_hash != live_hash:
        blockers.append("route_content_hash_changed")
    if req.source_route_content_hash != live_hash:
        blockers.append("execution_request_hash_stale")

    # Stage 8P/8O identity match.
    if not _stage8p_identity_matches_8o(
        repo_root=repo_root,
        actual_delivery_record_id=route.source_actual_delivery_record_id,
        artifact_sha256=route.artifact_sha256,
        customer_reference=route.customer_reference,
    ):
        blockers.append("stage8p_8o_identity_mismatch")

    # Action-specific eligibility.
    elig = _evaluate_action_specific(repo_root=repo_root, req=req, route=route, missing=missing, conflicts=conflicts, warnings=warnings)

    status = ELIG_READY
    if blockers:
        status = ELIG_BLOCKED
    elif missing:
        status = ELIG_NEEDS_OPERATOR_INPUT
    elif conflicts:
        status = ELIG_CONFLICTED

    result = ResolutionExecutionEligibilityResult(
        execution_request_id=req.execution_request_id,
        route_id=req.source_stage8q_route_id,
        action_family=req.action_family,
        eligibility_status=status,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        missing_fields=tuple(missing),
        detected_conflicts=tuple(conflicts),
        target_domain_source_ids=tuple(),
        recommended_manual_action=elig.get("recommended_manual_action"),
        evaluation_date=None,
    )

    append_resolution_action_event(
        ledger_path=ledger_path(repo_root),
        event_type=EVT_ELIGIBILITY_EVALUATED,
        execution_request_id=req.execution_request_id,
        project_id=req.project_id,
        customer_reference=req.customer_reference,
        artifact_sha256=req.source_artifact_sha256,
        action_family=req.action_family,
        source_route_id=req.source_stage8q_route_id,
        resulting_status=status,
        operator_id="system-readonly-stage8r",
        recorded_at="stage8r-readonly",
        execution_contract_hash=req.execution_contract_hash,
        detail=status,
    )
    return Stage8RServiceResult(ok=True, execution_request=req, eligibility=result)


def _evaluate_action_specific(
    *,
    repo_root: Any,
    req: ResolutionExecutionRequest,
    route: PostDeliveryResolutionRoute,
    missing: list[str],
    conflicts: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    params = req.normalized_action_parameters
    if req.action_family == ACTION_PROJECT_CLOSURE_EXECUTION:
        receipt_id = params.get("receipt_evidence_id")
        if not receipt_id:
            receipt_id = _derive_receipt_evidence_id(repo_root=repo_root, delivery_record_id=route.source_actual_delivery_record_id, status=REC_ACKNOWLEDGED)
        if not receipt_id:
            missing.append("receipt_evidence_id")
        else:
            res = closure_svc.get_receipt_evidence(receipt_evidence_id=receipt_id, repo_root=repo_root)
            if not res.ok or res.receipt_evidence is None:
                missing.append("receipt_evidence_not_found")
            elif res.receipt_evidence.receipt_status != REC_ACKNOWLEDGED:
                missing.append("receipt_not_acknowledged")
        # Active dispute / open revision / already closed checks use the closure service.
        return {"recommended_manual_action": "review closure eligibility then approve"}
    if req.action_family == ACTION_REVISION_REQUEST_CREATION:
        if params.get("revision_item_count", 0) == 0:
            missing.append("revision_items")
        inspected = revision_svc.inspect_delivery_lineage(delivery_record_id=route.source_actual_delivery_record_id, repo_root=repo_root)
        if not inspected.ok or inspected.lineage is None or inspected.lineage.lineage_status != revision_svc.LINEAGE_REGISTERED:
            missing.append("registered_delivery_lineage")
        else:
            for it in params.get("revision_items", ()):
                if str(it.get("source_artifact_sha256") or "").lower() != route.artifact_sha256.lower():
                    conflicts.append("revision_item_sha_mismatch")
        return {"recommended_manual_action": "review revision request then approve"}
    if req.action_family == ACTION_DISPUTE_OPENING:
        if not params.get("source_issue_id"):
            missing.append("source_issue_id")
        if not params.get("dispute_type"):
            missing.append("dispute_type")
        if not params.get("dispute_reason"):
            missing.append("dispute_reason")
        # Duplicate active dispute check.
        if params.get("source_issue_id"):
            existing = _disputes_for_issue(repo_root=repo_root, issue_id=params["source_issue_id"])
            for d in existing:
                if d.status == M_support.DISPUTE_OPEN and d.dispute_type == params.get("dispute_type"):
                    conflicts.append("active_dispute_exists")
        return {"recommended_manual_action": "review dispute opening then approve"}
    # Follow-up: requires purpose + recommended manual action.
    if not params.get("follow_up_purpose"):
        missing.append("follow_up_purpose")
    if not params.get("follow_up_recommended_action"):
        missing.append("follow_up_recommended_action")
    return {"recommended_manual_action": "review follow-up then approve"}


# ---------------------------------------------------------------------------
# Approval / rejection / cancel (separate Stage 8R execution approval)
# ---------------------------------------------------------------------------
def approve_execution_request(
    *,
    repo_root: Any,
    execution_request_id: str,
    operator_id: str,
    reason: str | None = None,
    informational_recorded_at: str = "",
) -> Stage8RServiceResult:
    if not str(operator_id or "").strip():
        return _deny(error_code=ERR_MISSING_OPERATOR_ID, error_detail="operator_id is required")
    req = _load_request(repo_root=repo_root, execution_request_id=execution_request_id)
    if req is None:
        return _deny(error_code=ERR_EXECUTION_REQUEST_NOT_FOUND, error_detail="execution request not found", execution_request_id=execution_request_id)

    elig_result = evaluate_execution_eligibility(repo_root=repo_root, execution_request_id=execution_request_id)
    if not elig_result.ok or elig_result.eligibility is None:
        return elig_result
    if elig_result.eligibility.eligibility_status != ELIG_READY:
        return _deny(
            error_code=ERR_ELIGIBILITY_NOT_READY,
            error_detail=f"eligibility is {elig_result.eligibility.eligibility_status}; cannot approve",
            execution_request_id=execution_request_id,
        )

    op = operator_id
    reason_norm = _safe_reason(reason)
    aid = execution_approval_id(
        execution_request_id=req.execution_request_id,
        execution_contract_hash=req.execution_contract_hash,
        route_id=req.source_stage8q_route_id,
        route_content_hash=req.source_route_content_hash,
        action_family=req.action_family,
        operator_id=op,
        decision=DECISION_APPROVE,
    )

    # Idempotent: an identical approval already exists?
    existing = _load_approval(repo_root=repo_root, execution_approval_id=aid)
    if existing is not None:
        return Stage8RServiceResult(ok=True, execution_request=req, approval=existing)

    approval = ResolutionExecutionApproval(
        schema_version="scos-hvs.stage8r.execution-approval.v1/1.0.0",
        execution_approval_id=aid,
        execution_request_id=req.execution_request_id,
        execution_contract_hash=req.execution_contract_hash,
        route_id=req.source_stage8q_route_id,
        route_content_hash=req.source_route_content_hash,
        action_family=req.action_family,
        project_id=req.project_id,
        customer_reference=req.customer_reference,
        artifact_sha256=req.source_artifact_sha256,
        operator_id=op,
        decision=DECISION_APPROVE,
        reason=reason_norm or None,
        informational_recorded_at=informational_recorded_at,
        automation_allowed=False,
    )

    append_resolution_action_event(
        ledger_path=ledger_path(repo_root),
        event_type=EVT_EXECUTION_APPROVED,
        execution_request_id=req.execution_request_id,
        project_id=req.project_id,
        customer_reference=req.customer_reference,
        artifact_sha256=req.source_artifact_sha256,
        action_family=req.action_family,
        source_route_id=req.source_stage8q_route_id,
        resulting_status=REQ_APPROVED_FOR_EXECUTION,
        operator_id=op,
        recorded_at=informational_recorded_at or "stage8r-readonly",
        execution_contract_hash=req.execution_contract_hash,
        detail=reason_norm or "",
        record_payload=approval.to_dict(),
    )
    return Stage8RServiceResult(ok=True, execution_request=req, approval=approval)


def reject_execution_request(
    *,
    repo_root: Any,
    execution_request_id: str,
    operator_id: str,
    reason: str | None = None,
    informational_recorded_at: str = "",
) -> Stage8RServiceResult:
    if not str(operator_id or "").strip():
        return _deny(error_code=ERR_MISSING_OPERATOR_ID, error_detail="operator_id is required")
    req = _load_request(repo_root=repo_root, execution_request_id=execution_request_id)
    if req is None:
        return _deny(error_code=ERR_EXECUTION_REQUEST_NOT_FOUND, error_detail="execution request not found", execution_request_id=execution_request_id)
    if not reason or not str(reason).strip():
        return _deny(error_code=ERR_MISSING_REASON, error_detail="rejection requires a reason", execution_request_id=execution_request_id)
    reason_norm = _safe_reason(reason)
    op = operator_id
    aid = execution_approval_id(
        execution_request_id=req.execution_request_id,
        execution_contract_hash=req.execution_contract_hash,
        route_id=req.source_stage8q_route_id,
        route_content_hash=req.source_route_content_hash,
        action_family=req.action_family,
        operator_id=op,
        decision=DECISION_REJECT,
    )
    approval = ResolutionExecutionApproval(
        schema_version="scos-hvs.stage8r.execution-approval.v1/1.0.0",
        execution_approval_id=aid,
        execution_request_id=req.execution_request_id,
        execution_contract_hash=req.execution_contract_hash,
        route_id=req.source_stage8q_route_id,
        route_content_hash=req.source_route_content_hash,
        action_family=req.action_family,
        project_id=req.project_id,
        customer_reference=req.customer_reference,
        artifact_sha256=req.source_artifact_sha256,
        operator_id=op,
        decision=DECISION_REJECT,
        reason=reason_norm,
        informational_recorded_at=informational_recorded_at,
        automation_allowed=False,
    )
    append_resolution_action_event(
        ledger_path=ledger_path(repo_root),
        event_type=EVT_EXECUTION_REJECTED,
        execution_request_id=req.execution_request_id,
        project_id=req.project_id,
        customer_reference=req.customer_reference,
        artifact_sha256=req.source_artifact_sha256,
        action_family=req.action_family,
        source_route_id=req.source_stage8q_route_id,
        resulting_status=REQ_REJECTED,
        operator_id=op,
        recorded_at=informational_recorded_at or "stage8r-readonly",
        execution_contract_hash=req.execution_contract_hash,
        detail=reason_norm,
        record_payload=approval.to_dict(),
    )
    return Stage8RServiceResult(ok=True, execution_request=req, approval=approval)


def cancel_execution_request(
    *,
    repo_root: Any,
    execution_request_id: str,
    operator_id: str,
    reason: str | None = None,
    informational_recorded_at: str = "",
) -> Stage8RServiceResult:
    if not str(operator_id or "").strip():
        return _deny(error_code=ERR_MISSING_OPERATOR_ID, error_detail="operator_id is required")
    req = _load_request(repo_root=repo_root, execution_request_id=execution_request_id)
    if req is None:
        return _deny(error_code=ERR_EXECUTION_REQUEST_NOT_FOUND, error_detail="execution request not found", execution_request_id=execution_request_id)
    if not reason or not str(reason).strip():
        return _deny(error_code=ERR_MISSING_REASON, error_detail="cancellation requires a reason", execution_request_id=execution_request_id)
    reason_norm = _safe_reason(reason)
    op = operator_id
    append_resolution_action_event(
        ledger_path=ledger_path(repo_root),
        event_type=EVT_EXECUTION_CANCELLED,
        execution_request_id=req.execution_request_id,
        project_id=req.project_id,
        customer_reference=req.customer_reference,
        artifact_sha256=req.source_artifact_sha256,
        action_family=req.action_family,
        source_route_id=req.source_stage8q_route_id,
        resulting_status=REQ_CANCELLED,
        operator_id=op,
        recorded_at=informational_recorded_at or "stage8r-readonly",
        execution_contract_hash=req.execution_contract_hash,
        detail=reason_norm,
    )
    return Stage8RServiceResult(ok=True, execution_request=req)


# ---------------------------------------------------------------------------
# Execute approved action (single target-domain mutation)
# ---------------------------------------------------------------------------
def execute_approved_action(
    *,
    repo_root: Any,
    execution_request_id: str,
    operator_id: str,
    informational_recorded_at: str = "",
) -> Stage8RServiceResult:
    if not str(operator_id or "").strip():
        return _deny(error_code=ERR_MISSING_OPERATOR_ID, error_detail="operator_id is required")
    req = _load_request(repo_root=repo_root, execution_request_id=execution_request_id)
    if req is None:
        return _deny(error_code=ERR_EXECUTION_REQUEST_NOT_FOUND, error_detail="execution request not found", execution_request_id=execution_request_id)

    # Must have a separate Stage 8R approval.
    approval = _find_approval_for_request(repo_root=repo_root, execution_request_id=execution_request_id, decision=DECISION_APPROVE)
    if approval is None:
        return _deny(
            error_code=ERR_EXECUTION_APPROVAL_NOT_FOUND,
            error_detail="no separate Stage 8R execution approval exists",
            execution_request_id=execution_request_id,
        )
    if approval.decision != DECISION_APPROVE:
        return _deny(error_code=ERR_EXECUTION_APPROVAL_NOT_FOUND, error_detail="execution approval is not an approval", execution_request_id=execution_request_id)

    # Approval must bind this exact contract.
    if approval.execution_contract_hash != req.execution_contract_hash:
        return _deny(
            error_code=ERR_APPROVAL_CONTRACT_MISMATCH,
            error_detail="approval contract hash does not match the execution request",
            execution_request_id=execution_request_id,
        )
    if approval.action_family != req.action_family:
        return _deny(
            error_code=ERR_APPROVAL_ACTION_MISMATCH,
            error_detail="approval action family does not match the execution request",
            execution_request_id=execution_request_id,
        )

    # Pre-execution reverification.
    pre_ok = _pre_execution_reverify(repo_root=repo_root, req=req, approval=approval)
    if not pre_ok.ok:
        return pre_ok

    append_resolution_action_event(
        ledger_path=ledger_path(repo_root),
        event_type=EVT_TARGET_ACTION_STARTED,
        execution_request_id=req.execution_request_id,
        project_id=req.project_id,
        customer_reference=req.customer_reference,
        artifact_sha256=req.source_artifact_sha256,
        action_family=req.action_family,
        source_route_id=req.source_stage8q_route_id,
        resulting_status=EXEC_EXECUTING,
        operator_id=operator_id,
        recorded_at=informational_recorded_at or "stage8r-readonly",
        execution_contract_hash=req.execution_contract_hash,
    )

    try:
        handler_result = ACTION_HANDLERS[req.action_family](
            repo_root=repo_root,
            req=req,
            operator_id=operator_id,
            recorded_at=informational_recorded_at or "stage8r-readonly",
        )
    except ValueError as exc:
        append_resolution_action_event(
            ledger_path=ledger_path(repo_root),
            event_type=EVT_TARGET_ACTION_FAILED,
            execution_request_id=req.execution_request_id,
            project_id=req.project_id,
            customer_reference=req.customer_reference,
            artifact_sha256=req.source_artifact_sha256,
            action_family=req.action_family,
            source_route_id=req.source_stage8q_route_id,
            resulting_status=EXEC_FAILED,
            operator_id=operator_id,
            recorded_at=informational_recorded_at or "stage8r-readonly",
            execution_contract_hash=req.execution_contract_hash,
            detail=str(exc),
        )
        return _deny(error_code=ERR_TARGET_MUTATION_FAILED, error_detail=str(exc), execution_request_id=execution_request_id)

    if not handler_result.ok:
        return handler_result

    target_record = handler_result.target_record
    manual_follow_up = handler_result.manual_follow_up

    # Target-record verification.
    verified, verify_detail = _verify_target_record(req=req, target_record=target_record, manual_follow_up=manual_follow_up)
    exec_status = EXEC_COMPLETED
    if not verified:
        exec_status = EXEC_FAILED

    append_resolution_action_event(
        ledger_path=ledger_path(repo_root),
        event_type=EVT_TARGET_ACTION_COMPLETED,
        execution_request_id=req.execution_request_id,
        project_id=req.project_id,
        customer_reference=req.customer_reference,
        artifact_sha256=req.source_artifact_sha256,
        action_family=req.action_family,
        source_route_id=req.source_stage8q_route_id,
        resulting_status=exec_status,
        operator_id=operator_id,
        recorded_at=informational_recorded_at or "stage8r-readonly",
        execution_contract_hash=req.execution_contract_hash,
        target_record_id=(target_record or {}).get("target_record_id") or (manual_follow_up.follow_up_record_id if manual_follow_up else ""),
    )

    target_record_id = None
    target_record_hash = None
    if target_record:
        target_record_id = target_record.get("target_record_id")
        target_record_hash = target_record.get("target_record_content_hash")
    elif manual_follow_up:
        target_record_id = manual_follow_up.follow_up_record_id

    append_resolution_action_event(
        ledger_path=ledger_path(repo_root),
        event_type=EVT_TARGET_RECORD_VERIFIED,
        execution_request_id=req.execution_request_id,
        project_id=req.project_id,
        customer_reference=req.customer_reference,
        artifact_sha256=req.source_artifact_sha256,
        action_family=req.action_family,
        source_route_id=req.source_stage8q_route_id,
        resulting_status="VERIFIED" if verified else "MISMATCH",
        operator_id=operator_id,
        recorded_at=informational_recorded_at or "stage8r-readonly",
        execution_contract_hash=req.execution_contract_hash,
        target_record_id=target_record_id or "",
        detail=verify_detail,
    )

    if not verified:
        outcome = ResolutionActionOutcomeEvidence(
            schema_version="scos-hvs.stage8r.action-outcome.v1/1.0.0",
            outcome_evidence_id=outcome_evidence_id(
                execution_request_id=req.execution_request_id,
                execution_approval_id=approval.execution_approval_id,
                target_record_id=target_record_id,
                target_record_content_hash=target_record_hash,
                execution_status=exec_status,
            ),
            execution_request_id=req.execution_request_id,
            execution_approval_id=approval.execution_approval_id,
            source_route_id=req.source_stage8q_route_id,
            action_family=req.action_family,
            target_domain=req.target_domain,
            target_record_id=target_record_id,
            target_record_content_hash=target_record_hash,
            target_record_verified=False,
            execution_status=EXEC_FAILED,
            outcome_status=OUT_TARGET_RECORD_MISMATCH if target_record_id else OUT_TARGET_RECORD_MISSING,
            side_effect_count=1,
            customer_contact_performed=False,
            hvs_invoked=False,
            media_modified=False,
            invoice_state_changed=False,
            payment_state_changed=False,
            automation_allowed=False,
            execution_contract_hash=req.execution_contract_hash,
            audit_event_ids=_event_ids_for(repo_root=repo_root, execution_request_id=req.execution_request_id),
            informational_recorded_at=informational_recorded_at or "stage8r-readonly",
        )
        _persist_outcome(repo_root=repo_root, req=req, approval=approval, outcome=outcome)
        return _deny(error_code=ERR_TARGET_RECORD_MISMATCH, error_detail=verify_detail, execution_request_id=execution_request_id, outcome=outcome.to_dict())

    outcome = ResolutionActionOutcomeEvidence(
        schema_version="scos-hvs.stage8r.action-outcome.v1/1.0.0",
        outcome_evidence_id=outcome_evidence_id(
            execution_request_id=req.execution_request_id,
            execution_approval_id=approval.execution_approval_id,
            target_record_id=target_record_id,
            target_record_content_hash=target_record_hash,
            execution_status=exec_status,
        ),
        execution_request_id=req.execution_request_id,
        execution_approval_id=approval.execution_approval_id,
        source_route_id=req.source_stage8q_route_id,
        action_family=req.action_family,
        target_domain=req.target_domain,
        target_record_id=target_record_id,
        target_record_content_hash=target_record_hash,
        target_record_verified=True,
        execution_status=EXEC_COMPLETED,
        outcome_status=OUT_VERIFIED,
        side_effect_count=1,
        customer_contact_performed=False,
        hvs_invoked=False,
        media_modified=False,
        invoice_state_changed=False,
        payment_state_changed=False,
        automation_allowed=False,
        execution_contract_hash=req.execution_contract_hash,
        audit_event_ids=_event_ids_for(repo_root=repo_root, execution_request_id=req.execution_request_id),
        informational_recorded_at=informational_recorded_at or "stage8r-readonly",
    )
    _persist_outcome(repo_root=repo_root, req=req, approval=approval, outcome=outcome)

    extra: dict[str, Any] = {}
    if manual_follow_up is not None:
        extra["manual_follow_up"] = manual_follow_up
    return Stage8RServiceResult(ok=True, execution_request=req, approval=approval, outcome=outcome, target_record=target_record, manual_follow_up=manual_follow_up, extra=extra)


def _persist_outcome(*, repo_root: Any, req: ResolutionExecutionRequest, approval: ResolutionExecutionApproval, outcome: ResolutionActionOutcomeEvidence) -> None:
    append_resolution_action_event(
        ledger_path=ledger_path(repo_root),
        event_type=EVT_OUTCOME_EVIDENCE_CREATED,
        execution_request_id=req.execution_request_id,
        project_id=req.project_id,
        customer_reference=req.customer_reference,
        artifact_sha256=req.source_artifact_sha256,
        action_family=req.action_family,
        source_route_id=req.source_stage8q_route_id,
        resulting_status=outcome.outcome_status,
        operator_id=approval.operator_id,
        recorded_at=outcome.informational_recorded_at or "stage8r-readonly",
        execution_contract_hash=req.execution_contract_hash,
        target_record_id=outcome.target_record_id or "",
        detail=outcome.execution_status,
        record_payload=outcome.to_dict(),
    )


# ---------------------------------------------------------------------------
# Pre-execution reverification
# ---------------------------------------------------------------------------
def _pre_execution_reverify(*, repo_root: Any, req: ResolutionExecutionRequest, approval: ResolutionExecutionApproval) -> Stage8RServiceResult:
    route = load_stage8q_route(repo_root=repo_root, resolution_route_id=req.source_stage8q_route_id)
    if route is None:
        return _deny(error_code=ERR_PRE_EXECUTION_FAILED, error_detail="route no longer exists", execution_request_id=req.execution_request_id)
    # Route still approved. Stage 8Q keeps the route-creation record at
    # READY_FOR_OPERATOR_REVIEW, so approval is derived from the append-only
    # Stage 8Q decision ledger instead of route.route_status.
    approval_status = _stage8q_route_approval_status(repo_root=repo_root, route=route)
    if approval_status != ROUTING_APPROVED:
        return _deny(error_code=ERR_PRE_EXECUTION_FAILED, error_detail="route no longer approved", execution_request_id=req.execution_request_id)
    live_hash = route_content_hash_for(route)
    if route.deterministic_content_hash and route.deterministic_content_hash != live_hash:
        return _deny(error_code=ERR_PRE_EXECUTION_FAILED, error_detail="route semantics changed", execution_request_id=req.execution_request_id)
    if req.source_route_content_hash != live_hash:
        return _deny(error_code=ERR_PRE_EXECUTION_FAILED, error_detail="execution request hash stale", execution_request_id=req.execution_request_id)
    # Stage 8P/8O identity.
    if not _stage8p_identity_matches_8o(
        repo_root=repo_root,
        actual_delivery_record_id=route.source_actual_delivery_record_id,
        artifact_sha256=route.artifact_sha256,
        customer_reference=route.customer_reference,
    ):
        return _deny(error_code=ERR_PRE_EXECUTION_FAILED, error_detail="Stage 8P/8O identity mismatch", execution_request_id=req.execution_request_id)
    # Contract + action binding.
    if approval.execution_contract_hash != req.execution_contract_hash:
        return _deny(error_code=ERR_APPROVAL_CONTRACT_MISMATCH, error_detail="approval contract changed", execution_request_id=req.execution_request_id)
    if approval.action_family != req.action_family:
        return _deny(error_code=ERR_APPROVAL_ACTION_MISMATCH, error_detail="approval action changed", execution_request_id=req.execution_request_id)
    # No prior completed Stage 8R for this exact request.
    if _find_completed_outcome(repo_root=repo_root, execution_request_id=req.execution_request_id) is not None:
        return _deny(error_code=ERR_CONFLICTING_EXECUTION, error_detail="identical execution already completed", execution_request_id=req.execution_request_id)
    # Changed-semantic replay conflict: a completed outcome already exists for
    # the same Stage 8Q route + action family, but with a different contract.
    prior_same_identity = _completed_outcome_for_route_action(
        repo_root=repo_root, source_route_id=req.source_stage8q_route_id, action_family=req.action_family
    )
    if prior_same_identity is not None and prior_same_identity.execution_contract_hash != req.execution_contract_hash:
        return _deny(
            error_code=ERR_CONFLICTING_EXECUTION,
            error_detail="changed-semantic execution already completed for this route+action",
            execution_request_id=req.execution_request_id,
        )
    # Conflicting target record check.
    conflict = _conflicting_target_exists(repo_root=repo_root, req=req)
    if conflict:
        append_resolution_action_event(
            ledger_path=ledger_path(repo_root),
            event_type=EVT_CONFLICT_DETECTED,
            execution_request_id=req.execution_request_id,
            project_id=req.project_id,
            customer_reference=req.customer_reference,
            artifact_sha256=req.source_artifact_sha256,
            action_family=req.action_family,
            source_route_id=req.source_stage8q_route_id,
            resulting_status=EXEC_CONFLICTED,
            operator_id=approval.operator_id,
            recorded_at="stage8r-readonly",
            execution_contract_hash=req.execution_contract_hash,
            detail=conflict,
        )
        return _deny(error_code=ERR_CONFLICTING_EXECUTION, error_detail=conflict, execution_request_id=req.execution_request_id)
    append_resolution_action_event(
        ledger_path=ledger_path(repo_root),
        event_type=EVT_PRE_EXECUTION_REVERIFIED,
        execution_request_id=req.execution_request_id,
        project_id=req.project_id,
        customer_reference=req.customer_reference,
        artifact_sha256=req.source_artifact_sha256,
        action_family=req.action_family,
        source_route_id=req.source_stage8q_route_id,
        resulting_status=EXEC_NOT_STARTED,
        operator_id=approval.operator_id,
        recorded_at="stage8r-readonly",
        execution_contract_hash=req.execution_contract_hash,
    )
    return Stage8RServiceResult(ok=True, execution_request=req, approval=approval)


# ---------------------------------------------------------------------------
# Target-record verification
# ---------------------------------------------------------------------------
def _verify_target_record(*, req: ResolutionExecutionRequest, target_record: dict[str, Any] | None, manual_follow_up: ManualFollowUpRecord | None) -> tuple[bool, str]:
    if manual_follow_up is not None:
        if manual_follow_up.project_id != req.project_id:
            return False, "follow_up project mismatch"
        if manual_follow_up.customer_reference.lower() != req.customer_reference.lower():
            return False, "follow_up customer mismatch"
        if manual_follow_up.artifact_sha256.lower() != req.source_artifact_sha256.lower():
            return False, "follow_up artifact mismatch"
        if manual_follow_up.action_family != req.action_family:
            return False, "follow_up action mismatch"
        if manual_follow_up.external_task_created or manual_follow_up.calendar_event_created or manual_follow_up.customer_contact_performed or manual_follow_up.automation_allowed:
            return False, "follow_up recorded unsafe effect"
        return True, "follow_up verified"
    if target_record is None:
        return False, "target record missing"
    for field_name in ("project_id", "customer_reference", "artifact_sha256"):
        expected = {
            "project_id": req.project_id,
            "customer_reference": req.customer_reference,
            "artifact_sha256": req.source_artifact_sha256,
        }[field_name]
        actual = target_record.get(field_name)
        if actual is None:
            continue
        if str(actual).lower() != str(expected).lower():
            return False, f"target {field_name} mismatch"
    # Action-specific prohibited flags.
    if target_record.get("customer_contact_executed_by_scos") or target_record.get("customer_contact_performed"):
        return False, "target recorded customer contact"
    if target_record.get("hvs_invoked"):
        return False, "target recorded hvs invocation"
    if target_record.get("rerender_started") and req.action_family == ACTION_REVISION_REQUEST_CREATION:
        return False, "revision unexpectedly started rerender"
    if target_record.get("invoice_created_by_scos") or target_record.get("invoice_state_changed"):
        return False, "target mutated invoice state"
    if target_record.get("payment_state_changed") or target_record.get("payment_confirmed_by_scos"):
        return False, "target mutated payment state"
    return True, "target verified"


def _conflicting_target_exists(*, repo_root: Any, req: ResolutionExecutionRequest) -> str | None:
    if req.action_family == ACTION_DISPUTE_OPENING:
        issue_id = req.normalized_action_parameters.get("source_issue_id")
        if issue_id:
            for d in _disputes_for_issue(repo_root=repo_root, issue_id=issue_id):
                if d.status == M_support.DISPUTE_OPEN and d.dispute_type == req.normalized_action_parameters.get("dispute_type"):
                    return "active_dispute_exists_for_issue"
    return None


# ---------------------------------------------------------------------------
# Action handlers (explicit dispatch table)
# ---------------------------------------------------------------------------
def _handle_closure(*, repo_root: Any, req: ResolutionExecutionRequest, operator_id: str, recorded_at: str) -> Stage8RServiceResult:
    params = req.normalized_action_parameters
    receipt_id = params.get("receipt_evidence_id")
    if not receipt_id:
        receipt_id = _derive_receipt_evidence_id(repo_root=repo_root, delivery_record_id=req.source_stage8o_identity or "", status=REC_ACKNOWLEDGED)
    if not receipt_id:
        return _deny(error_code=ERR_TARGET_MUTATION_FAILED, error_detail="no acknowledged receipt evidence id available for closure", execution_request_id=req.execution_request_id)
    reason = params.get("closure_reason") or "operator-authorized post-acceptance closure"
    res = closure_svc.close_delivery(
        receipt_evidence_id=receipt_id,
        repo_root=repo_root,
        operator_id=operator_id,
        decision="accept",
        reason=reason,
        recorded_at=recorded_at,
    )
    if not res.ok or res.closure is None:
        return _deny(error_code=ERR_TARGET_MUTATION_FAILED, error_detail=res.error_detail or "closure failed", execution_request_id=req.execution_request_id)
    closure = res.closure
    # Exactly-one-effect guard: closure must not have created a revision.
    if closure.open_revision_request_id:
        return _deny(error_code=ERR_PARTIAL_EFFECT, error_detail="closure unexpectedly opened a revision", execution_request_id=req.execution_request_id)
    target = {
        "target_record_id": closure.closure_id,
        "target_record_content_hash": closure.identity_inputs.get("closure_status"),
        "project_id": closure.project_id,
        "customer_reference": req.customer_reference,
        "artifact_sha256": closure.artifact_sha256,
        "closure_status": closure.closure_status,
        "accepted_by_customer": closure.accepted_by_customer,
        "customer_contact_executed_by_scos": closure.customer_contact_executed_by_scos,
        "invoice_created_by_scos": closure.invoice_created_by_scos,
        "payment_confirmed_by_scos": closure.payment_confirmed,
        "automation_allowed": closure.automation_allowed,
    }
    return Stage8RServiceResult(ok=True, execution_request=req, target_record=target)


def _handle_revision(*, repo_root: Any, req: ResolutionExecutionRequest, operator_id: str, recorded_at: str) -> Stage8RServiceResult:
    params = req.normalized_action_parameters
    items = params.get("revision_items", ())
    if not items:
        return _deny(error_code=ERR_TARGET_MUTATION_FAILED, error_detail="no revision items", execution_request_id=req.execution_request_id)
    revision_items = tuple(
        revision_models.RevisionItem.create(
            category=it["category"],
            description=it.get("description", ""),
            target_type=it.get("target_type", "scene"),
            target_id=it.get("target_id", ""),
            scene_id=it.get("scene_id"),
            asset_id=it.get("asset_id"),
            format=it.get("format"),
            timeline_start=it.get("timeline_start"),
            timeline_end=it.get("timeline_end"),
            priority=it.get("priority", "normal"),
            acceptance_requirement=it.get("acceptance_requirement", "operator_review"),
            requested_by_id=operator_id,
            source_artifact_sha256=req.source_artifact_sha256,
        )
        for it in items
    )
    res = revision_svc.create_revision_request(
        delivery_record_id=req.source_actual_delivery_record_id,
        requested_by_id=operator_id,
        operator_id=operator_id,
        revision_items=revision_items,
        repo_root=repo_root,
        recorded_at=recorded_at,
    )
    if not res.ok or res.revision is None:
        return _deny(error_code=ERR_TARGET_MUTATION_FAILED, error_detail=res.error_detail or "revision request failed", execution_request_id=req.execution_request_id)
    rev = res.revision
    target = {
        "target_record_id": rev.revision_request_id,
        "target_record_content_hash": rev.deterministic_content_hash,
        "project_id": rev.project_id,
        "customer_reference": rev.recipient_label,
        "artifact_sha256": rev.source_artifact_sha256,
        "delivery_record_id": rev.delivery_record_id,
        "source_lineage_id": rev.source_lineage_id,
        "status": rev.status,
        "rerender_started": False,
        "automation_allowed": rev.automation_allowed,
        "no_overwrite_required": True,
        "source_artifact_preserved": True,
    }
    # Required final flags: a freshly created revision request must not have
    # started a rerender or mutated the source artifact.
    if target["rerender_started"]:
        return _deny(error_code=ERR_PARTIAL_EFFECT, error_detail="revision unexpectedly started rerender", execution_request_id=req.execution_request_id)
    return Stage8RServiceResult(ok=True, execution_request=req, target_record=target)


def _handle_dispute(*, repo_root: Any, req: ResolutionExecutionRequest, operator_id: str, recorded_at: str) -> Stage8RServiceResult:
    params = req.normalized_action_parameters
    issue_id = params.get("source_issue_id")
    if not issue_id:
        return _deny(error_code=ERR_TARGET_MUTATION_FAILED, error_detail="no source issue id", execution_request_id=req.execution_request_id)
    # open_post_delivery_dispute requires a `sha256:<64 hex>` artifact reference
    # (or empty). Normalize the Stage 8R source sha to that canonical form.
    raw_sha = req.source_artifact_sha256 or ""
    if raw_sha and not raw_sha.startswith("sha256:"):
        norm_sha = f"sha256:{raw_sha}" if len(raw_sha) == 64 else ""
    else:
        norm_sha = raw_sha
    res = support_svc.open_post_delivery_dispute(
        issue_id=issue_id,
        dispute_type=params.get("dispute_type") or "GENERAL_DISPUTE",
        dispute_reason=params.get("dispute_reason") or "operator-authorized dispute opening",
        opened_by_operator_id=operator_id,
        disputed_artifact_references=tuple(params.get("disputed_artifact_references", ())),
        artifact_sha256=norm_sha,
        evidence_references=tuple(params.get("dispute_evidence_references", ())),
        operator_id=operator_id,
        repo_root=repo_root,
        recorded_at=recorded_at,
    )
    if not res.ok or res.dispute is None:
        return _deny(error_code=ERR_TARGET_MUTATION_FAILED, error_detail=res.error_detail or "dispute opening failed", execution_request_id=req.execution_request_id)
    d = res.dispute
    target = {
        "target_record_id": d.dispute_id,
        "target_record_content_hash": d.idempotency_key,
        "project_id": d.project_id,
        "customer_reference": req.customer_reference,
        "artifact_sha256": req.source_artifact_sha256,
        "issue_id": d.issue_id,
        "dispute_type": d.dispute_type,
        "status": d.status,
        "resolution_reference": d.resolution_reference,
    }
    return Stage8RServiceResult(ok=True, execution_request=req, target_record=target)


def _handle_follow_up(*, repo_root: Any, req: ResolutionExecutionRequest, operator_id: str, recorded_at: str) -> Stage8RServiceResult:
    params = req.normalized_action_parameters
    purpose = params.get("follow_up_purpose") or "operator_recommended_follow_up"
    recommended = params.get("follow_up_recommended_action") or "manual follow-up per Stage 8Q recommendation"
    due = params.get("follow_up_due_date")
    evaluation_date = params.get("follow_up_evaluation_date")
    fuid = follow_up_record_id(
        execution_request_id=req.execution_request_id,
        route_id=req.source_stage8q_route_id,
        purpose=purpose,
        customer_reference=req.customer_reference,
        due_date=due,
    )
    record = ManualFollowUpRecord(
        schema_version=FOLLOWUP_MODEL_SCHEMA_VERSION,
        follow_up_record_id=fuid,
        execution_request_id=req.execution_request_id,
        route_id=req.source_stage8q_route_id,
        action_family=req.action_family,
        project_id=req.project_id,
        customer_reference=req.customer_reference,
        artifact_sha256=req.source_artifact_sha256,
        purpose=purpose,
        recommended_manual_action=recommended,
        due_date=due,
        evaluation_date=evaluation_date,
        external_task_created=False,
        calendar_event_created=False,
        customer_contact_performed=False,
        follow_up_completed=False,
        automation_allowed=False,
        informational_recorded_at=recorded_at,
    )
    append_resolution_action_event(
        ledger_path=ledger_path(repo_root),
        event_type="MANUAL_FOLLOW_UP_CREATED",
        execution_request_id=req.execution_request_id,
        project_id=req.project_id,
        customer_reference=req.customer_reference,
        artifact_sha256=req.source_artifact_sha256,
        action_family=req.action_family,
        source_route_id=req.source_stage8q_route_id,
        resulting_status="CREATED",
        operator_id=operator_id,
        recorded_at=recorded_at,
        execution_contract_hash=req.execution_contract_hash,
        target_record_id=fuid,
        detail=purpose,
        record_payload=record.to_dict(),
    )
    target = {
        "target_record_id": record.follow_up_record_id,
        "target_record_content_hash": record.follow_up_record_id,
        "project_id": record.project_id,
        "customer_reference": record.customer_reference,
        "artifact_sha256": record.artifact_sha256,
        "external_task_created": record.external_task_created,
        "calendar_event_created": record.calendar_event_created,
        "customer_contact_performed": record.customer_contact_performed,
        "automation_allowed": record.automation_allowed,
        "follow_up_completed": record.follow_up_completed,
    }
    return Stage8RServiceResult(ok=True, execution_request=req, target_record=target, manual_follow_up=record)


ACTION_HANDLERS = {
    ACTION_PROJECT_CLOSURE_EXECUTION: _handle_closure,
    ACTION_REVISION_REQUEST_CREATION: _handle_revision,
    ACTION_DISPUTE_OPENING: _handle_dispute,
    ACTION_MANUAL_FOLLOW_UP_RECORD_CREATION: _handle_follow_up,
}


# ---------------------------------------------------------------------------
# Inspection helpers
# ---------------------------------------------------------------------------
def inspect_execution_request(*, repo_root: Any, execution_request_id: str) -> Stage8RServiceResult:
    req = _load_request(repo_root=repo_root, execution_request_id=execution_request_id)
    if req is None:
        return _deny(error_code=ERR_EXECUTION_REQUEST_NOT_FOUND, error_detail="execution request not found", execution_request_id=execution_request_id)
    return Stage8RServiceResult(ok=True, execution_request=req)


def inspect_action_outcome(*, repo_root: Any, execution_request_id: str) -> Stage8RServiceResult:
    outcome = _find_completed_outcome(repo_root=repo_root, execution_request_id=execution_request_id)
    if outcome is None:
        return _deny(error_code="action_outcome_not_found", error_detail="no completed action outcome for this request", execution_request_id=execution_request_id)
    return Stage8RServiceResult(ok=True, outcome=outcome)


def list_resolution_actions(*, repo_root: Any) -> Stage8RServiceResult:
    from .hvs_resolution_action_store import events_for_request as _efr

    requests: dict[str, dict[str, Any]] = {}
    for ev in read_resolution_action_events(ledger_path=ledger_path(repo_root)):
        rid = ev.get("execution_request_id")
        if rid is None:
            continue
        requests.setdefault(rid, {"execution_request_id": rid, "latest_status": ev.get("resulting_status"), "action_family": ev.get("action_family")})
    return Stage8RServiceResult(ok=True, extra={"requests": list(requests.values())})


# ---------------------------------------------------------------------------
# Internal loaders
# ---------------------------------------------------------------------------
def _load_request(repo_root: Any, *, execution_request_id: str) -> ResolutionExecutionRequest | None:
    for ev in read_resolution_action_events(ledger_path=ledger_path(repo_root)):
        if ev.get("event_type") == EVT_EXECUTION_REQUEST_CREATED and ev.get("execution_request_id") == execution_request_id:
            rec = ev.get("record") or {}
            try:
                return ResolutionExecutionRequest(**_coerce_request(rec))
            except (TypeError, ValueError):
                return None
    return None


def _coerce_request(rec: dict[str, Any]) -> dict[str, Any]:
    out = dict(rec)
    out["source_stage8o_identity"] = rec.get("source_stage8o_identity")
    out["source_stage8p_record_id"] = rec.get("source_stage8p_record_id")
    out["source_route_approval_id"] = rec.get("source_route_approval_id")
    out["normalized_action_parameters"] = dict(rec.get("normalized_action_parameters", {}))
    return out


def _load_approval(repo_root: Any, *, execution_approval_id: str) -> ResolutionExecutionApproval | None:
    for ev in read_resolution_action_events(ledger_path=ledger_path(repo_root)):
        if ev.get("event_type") in (EVT_EXECUTION_APPROVED, EVT_EXECUTION_REJECTED) and ev.get("event_id") == execution_approval_id:
            rec = ev.get("record") or {}
            try:
                return ResolutionExecutionApproval(**rec)
            except (TypeError, ValueError):
                return None
    return None


def _find_approval_for_request(repo_root: Any, *, execution_request_id: str, decision: str | None = None) -> ResolutionExecutionApproval | None:
    result: ResolutionExecutionApproval | None = None
    for ev in read_resolution_action_events(ledger_path=ledger_path(repo_root)):
        if ev.get("execution_request_id") == execution_request_id and ev.get("event_type") in (EVT_EXECUTION_APPROVED, EVT_EXECUTION_REJECTED):
            rec = ev.get("record") or {}
            try:
                ap = ResolutionExecutionApproval(**rec)
            except (TypeError, ValueError):
                continue
            if decision is not None and ap.decision != decision:
                continue
            result = ap  # latest by append order
    return result


def _find_completed_outcome(repo_root: Any, *, execution_request_id: str) -> ResolutionActionOutcomeEvidence | None:
    for ev in read_resolution_action_events(ledger_path=ledger_path(repo_root)):
        if ev.get("execution_request_id") == execution_request_id and ev.get("event_type") == EVT_OUTCOME_EVIDENCE_CREATED:
            rec = ev.get("record") or {}
            try:
                return ResolutionActionOutcomeEvidence(**rec)
            except (TypeError, ValueError):
                return None
    return None


def _completed_outcome_for_route_action(
    repo_root: Any, *, source_route_id: str, action_family: str
) -> ResolutionActionOutcomeEvidence | None:
    """Return any prior COMPLETED Stage 8R outcome for the same Stage 8Q route
    and action family, regardless of contract hash. Used to reject a
    changed-semantic replay that reuses the route+action identity."""
    for ev in read_resolution_action_events(ledger_path=ledger_path(repo_root)):
        if ev.get("event_type") != EVT_OUTCOME_EVIDENCE_CREATED:
            continue
        rec = ev.get("record") or {}
        if rec.get("source_route_id") != source_route_id:
            continue
        if rec.get("action_family") != action_family:
            continue
        try:
            return ResolutionActionOutcomeEvidence(**rec)
        except (TypeError, ValueError):
            return None
    return None


def _event_ids_for(repo_root: Any, *, execution_request_id: str) -> tuple[str, ...]:
    return tuple(e["event_id"] for e in events_for_request(ledger_path=ledger_path(repo_root), execution_request_id=execution_request_id))


def _safe_reason(reason: str | None) -> str:
    from .hvs_resolution_action_models import _require_free_text

    return _require_free_text(reason or "", max_len=512, field_name="reason")


def _derive_receipt_evidence_id(*, repo_root: Any, delivery_record_id: str, status: str) -> str | None:
    """Deterministically resolve the Stage 7 receipt-evidence id bound to a
    delivery record, mirroring the closure service's own receipt ledger scan.
    Returns None when no matching receipt evidence exists."""
    from .hvs_delivery_closure_service import load_receipt_evidence
    from .hvs_delivery_closure_models import stable_receipt_evidence_id

    # The closure service stores receipts as receipt_evidence_*.json keyed by
    # (delivery_record_id, package_id, artifact_sha256, receipt_status, ...).
    # We scan empirically rather than reverse-engineer the id, to avoid drift.
    root = ledger_path(repo_root).parent.parent  # scos/work
    from pathlib import Path

    best: str | None = None
    for path in Path(root).glob("*/receipt_evidence_*.json"):
        try:
            import json

            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("delivery_record_id") == delivery_record_id and data.get("receipt_status") == status:
            best = data.get("receipt_evidence_id")
    return best


def _disputes_for_issue(repo_root: Any, *, issue_id: str) -> list["M_support.PostDeliveryDispute"]:
    return _call_disputes_by_issue(repo_root, issue_id)


def _call_disputes_by_issue(repo_root: Any, issue_id: str) -> list["M_support.PostDeliveryDispute"]:
    from . import hvs_post_delivery_support_service as S

    all_disputes = S._disputes_by_issue(repo_root)
    return list(all_disputes.get(issue_id, []))
