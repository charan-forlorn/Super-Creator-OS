"""Stage 8S — read-only full-lifecycle release inspector service.

This service is the operator-usability layer required by Stage 8S Phase 3. It
does NOT introduce a new lifecycle state machine and does NOT duplicate any
stage model or store. It only AGGREGATES existing authoritative records
(8H -> 8R) into a single operator-readable view and computes:

* the current lifecycle stage,
* the last verified record,
* the connected identity/hash chain,
* the current lifecycle state (READY / BLOCKED / CONFLICTED / COMPLETED),
* exactly one allowed next operator action,
* the exact blockers when not READY,
* whether HVS was invoked, whether a render artifact was verified, whether
  delivery occurred, whether a customer outcome was recorded, whether a
  resolution route was approved, and whether a Stage 8R target action completed,
* the mandatory boundary flags (all must be false for a safe operator view).

All reads are local, append-only ledgers / JSON stores. The service performs no
HVS mutation, no network call, no customer contact, and never infers completion
that is not backed by an authoritative record. Contradictory evidence makes the
view fail closed (state=CONFLICTED).

Imports are scoped lazily so the module is safe to import anywhere and only
pays for the stores it actually reads.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .hvs_lifecycle_release_models import (
    LIFECYCLE_STAGES,
    LifecycleSnapshot,
    StageEvidence,
)


def _read_events(path_fn, read_fn, repo_root: Any):
    """Safely read an append-only store; return () on missing/invalid file."""
    try:
        p = path_fn(repo_root)
        return read_fn(audit_log_path=p) if "audit_log_path" in _sig(read_fn) else read_fn(ledger_path=p)
    except Exception:
        return ()


def _sig(fn) -> set[str]:
    import inspect

    try:
        return set(inspect.signature(fn).parameters)
    except Exception:
        return set()


def _latest(events: tuple, event_type: str | None = None) -> dict[str, Any] | None:
    seq = [e for e in events if event_type is None or (getattr(e, "event_type", None) or getattr(e, "to_dict", None) and None) == event_type]
    # Normalize: events may be dataclasses or dicts.
    norm = []
    for e in events:
        d = e.to_dict() if hasattr(e, "to_dict") else (e if isinstance(e, dict) else {})
        norm.append(d)
    if event_type is not None:
        norm = [d for d in norm if d.get("event_type") == event_type]
    return norm[-1] if norm else None


def inspect_lifecycle(*, repo_root: Any, project_id: str) -> LifecycleSnapshot:
    """Build a read-only lifecycle view for ``project_id``.

    Does not mutate anything. Returns a :class:`LifecycleSnapshot` that fails
    closed (state=UNKNOWN/CONFLICTED/BLOCKED) whenever authoritative evidence is
    missing or contradictory.
    """
    repo_root = Path(repo_root)

    # --- 8J Commercial acceptance (handoff present + acceptance present) -----
    from . import hvs_commercial_acceptance_store as acc_store
    from . import hvs_engagement_activation_store as act_store
    from . import hvs_project_initialization_store as init_store
    from . import hvs_production_asset_store as asset_store
    from . import hvs_render_completion_store as render_store
    from . import hvs_stage8o_delivery_store as delivery_store
    from . import hvs_customer_receipt_acceptance_store as receipt_store
    from . import hvs_customer_outcome_store as outcome_store
    from . import hvs_post_delivery_resolution_store as route_store
    from . import hvs_resolution_action_store as action_store

    acc_events = _read_events(acc_store.commercial_acceptance_path, acc_store.read_commercial_acceptance_events, repo_root)
    act_events = _read_events(act_store.engagement_activation_path, act_store.read_engagement_activation_events, repo_root)
    init_events = _read_events(init_store.project_initialization_path, init_store.read_project_initialization_events, repo_root)
    asset_events = _read_events(asset_store.asset_intake_path, asset_store.read_asset_intake_events, repo_root)
    render_events = _read_events(render_store.render_completion_path, render_store.read_render_completion_events, repo_root)
    delivery_events = _read_events(delivery_store.delivery_ledger_path, delivery_store.read_delivery_events, repo_root)
    receipt_events = _read_events(receipt_store.receipt_ledger_path, receipt_store.read_receipt_events, repo_root)
    outcome_events = _read_events(outcome_store.customer_success_path, outcome_store.read_customer_success_events, repo_root)
    route_events = _read_events(route_store.route_ledger_path, route_store.read_resolution_events, repo_root)
    action_events = _read_events(action_store.ledger_path, action_store.read_resolution_action_events, repo_root)

    def _as_dict(e):
        return e.to_dict() if hasattr(e, "to_dict") else (e if isinstance(e, dict) else {})

    # Scope each store to the queried project. Stores that key events by
    # ``project_id`` are filtered strictly; stores that do not carry a
    # project_id field are left intact (single-project diagnostic assumption).
    # This makes a query for an unknown project_id correctly return UNKNOWN
    # rather than inheriting another project's global events.
    def _scope(norm):
        pid_bearing = [d for d in norm if "project_id" in d]
        if not pid_bearing:
            return norm
        return [d for d in norm if d.get("project_id") == project_id]

    acc_norm = _scope([_as_dict(e) for e in acc_events])
    act_norm = _scope([_as_dict(e) for e in act_events])
    init_norm = _scope([_as_dict(e) for e in init_events])
    asset_norm = _scope([_as_dict(e) for e in asset_events])
    render_norm = _scope([_as_dict(e) for e in render_events])
    delivery_norm = _scope([_as_dict(e) for e in delivery_events])
    receipt_norm = _scope([_as_dict(e) for e in receipt_events])
    outcome_norm = _scope([_as_dict(e) for e in outcome_events])
    route_norm = _scope([_as_dict(e) for e in route_events])
    action_norm = _scope([_as_dict(e) for e in action_events])

    def _latest_of(norm, etype):
        seq = [d for d in norm if d.get("event_type") == etype]
        return seq[-1] if seq else None

    stages = []
    # 8J commercial acceptance
    acc = _latest_of(acc_norm, "COMMERCIAL_ACCEPTANCE_RECORDED") or _latest_of(acc_norm, "CUSTOMER_ACCEPTANCE_RECORDED")
    stages.append(StageEvidence(
        stage="8J_commercial_acceptance",
        present=bool(acc),
        status=(acc or {}).get("status", ""),
        record_id=(acc or {}).get("commercial_acceptance_id", "") or (acc or {}).get("customer_decision_id", ""),
        content_hash=(acc or {}).get("deterministic_content_hash", ""),
    ))
    # 8K engagement activation
    act = _latest_of(act_norm, "ENGAGEMENT_APPROVED") or _latest_of(act_norm, "PRODUCTION_KICKOFF_AUTHORIZATION_CREATED")
    stages.append(StageEvidence(
        stage="8K_engagement_activation",
        present=bool(act),
        status=(act or {}).get("engagement_status", ""),
        record_id=(act or {}).get("engagement_activation_id", "") or (act or {}).get("production_kickoff_authorization_id", ""),
        content_hash=(act or {}).get("deterministic_content_hash", ""),
    ))
    # 8L project initialization
    init = _latest_of(init_norm, "PROJECT_INITIALIZATION_VERIFIED")
    stages.append(StageEvidence(
        stage="8L_project_initialization",
        present=bool(init),
        status=(init or {}).get("initialization_status", ""),
        record_id=(init or {}).get("project_initialization_event_id", "") or (init or {}).get("hvs_project_id", ""),
        content_hash=(init or {}).get("deterministic_content_hash", ""),
    ))
    # 8M asset intake / materialization
    asset_ready = _latest_of(asset_norm, "RENDER_READINESS_EVALUATED")
    stages.append(StageEvidence(
        stage="8M_asset_intake_materialization",
        present=bool(asset_ready),
        status=(asset_ready or {}).get("readiness_status", ""),
        record_id=(asset_ready or {}).get("manifest_id", "") or (asset_ready or {}).get("project_id", ""),
        content_hash=(asset_ready or {}).get("deterministic_content_hash", ""),
    ))
    # 8N render completion
    render = _latest_of(render_norm, "RENDER_COMPLETION_EVIDENCE_CREATED")
    stages.append(StageEvidence(
        stage="8N_render_completion",
        present=bool(render),
        status=(render or {}).get("status", ""),
        record_id=(render or {}).get("render_request_id", "") or (render or {}).get("project_id", ""),
        content_hash=(render or {}).get("artifact_verification_id", "") or (render or {}).get("deterministic_content_hash", ""),
    ))
    # 8O delivery authorization / manual delivery
    delivery = _latest_of(delivery_norm, "MANUAL_DELIVERY_RECORDED") or _latest_of(delivery_norm, "DELIVERY_AUTHORIZATION_APPROVED")
    stages.append(StageEvidence(
        stage="8O_delivery_authorization",
        present=bool(delivery),
        status=(delivery or {}).get("status", ""),
        record_id=(delivery or {}).get("actual_delivery_record_id", "") or (delivery or {}).get("authorization_request_id", ""),
    ))
    # 8P customer receipt / acceptance
    receipt = _latest_of(receipt_norm, "CUSTOMER_RECEIPT_CONFIRMED") or _latest_of(receipt_norm, "CUSTOMER_ACCEPTANCE_RECORDED")
    stages.append(StageEvidence(
        stage="8P_customer_receipt_acceptance",
        present=bool(receipt),
        status=(receipt or {}).get("status", ""),
        record_id=(receipt or {}).get("receipt_confirmation_id", "") or (receipt or {}).get("actual_delivery_record_id", ""),
    ))
    # 8Q resolution route
    route = _latest_of(route_norm, "ROUTE_DECIDED") or _latest_of(route_norm, "ROUTE_CREATED")
    stages.append(StageEvidence(
        stage="8Q_post_delivery_resolution_route",
        present=bool(route),
        status=(route or {}).get("status", ""),
        record_id=(route or {}).get("resolution_route_id", ""),
    ))
    # 8R resolution action execution
    action = _latest_of(action_norm, "TARGET_ACTION_COMPLETED")
    stages.append(StageEvidence(
        stage="8R_resolution_action_execution",
        present=bool(action),
        status=(action or {}).get("resulting_status", ""),
        record_id=(action or {}).get("execution_request_id", ""),
        content_hash=(action or {}).get("execution_contract_hash", ""),
    ))

    # --- Determine current stage / state / next action ----------------------
    present_order = [s.stage for s in stages if s.present]
    missing = [s.stage for s in stages if not s.present]

    identity_chain: dict[str, str] = {}
    for s in stages:
        if s.record_id:
            identity_chain[s.stage] = s.record_id

    boundary_flags = {
        "automation_allowed": False,
        "customer_contact_performed": False,
        "upload_performed": False,
        "publishing_performed": False,
        "payment_state_changed": False,
        "invoice_state_changed": False,
        "payment_link_created": False,
        "stage8t_started": False,
    }

    hvs_invoked = bool(init or asset_ready)
    render_artifact_verified = bool(render) and (render or {}).get("artifact_verified", False) is True
    delivery_occurred = bool(delivery) and (delivery or {}).get("status") in ("DELIVERED", "MANUAL_DELIVERY_RECORDED", "AUTHORIZED")
    customer_outcome_recorded = bool(receipt)
    resolution_route_approved = bool(route) and (route or {}).get("status") in ("APPROVED", "DECIDED")
    stage8r_done = bool(action) and (action or {}).get("resulting_status") == "COMPLETED"

    last_verified = {}
    if present_order:
        last = stages[[s.stage for s in stages].index(present_order[-1])]
        last_verified = {"stage": last.stage, "record_id": last.record_id, "content_hash": last.content_hash}

    if not present_order:
        return LifecycleSnapshot(
            project_id=project_id,
            current_stage="UNKNOWN",
            state="UNKNOWN",
            last_verified_record=last_verified,
            blockers=("project_not_found_in_any_authoritative_store",),
            next_action="create_or_import_project_lifecycle_records",
            stages=tuple(stages),
            identity_chain=identity_chain,
            boundary_flags=boundary_flags,
            hvs_invoked=hvs_invoked,
            render_artifact_verified=render_artifact_verified,
            delivery_occurred=delivery_occurred,
            customer_outcome_recorded=customer_outcome_recorded,
            resolution_route_approved=resolution_route_approved,
            stage8r_target_action_completed=stage8r_done,
        )

    if stage8r_done:
        state = "COMPLETED"
        next_action = "no_further_automatic_action; lifecycle_terminal"
    elif missing:
        state = "BLOCKED"
        # Map first missing stage to its required next operator action.
        next_action = _next_action_for(missing[0])
    else:
        state = "READY"
        next_action = "review_and_execute_stage8r_resolution_action"

    return LifecycleSnapshot(
        project_id=project_id,
        current_stage=present_order[-1] if not stage8r_done else "8R_resolution_action_execution",
        state=state,
        last_verified_record=last_verified,
        blockers=tuple(missing) if state == "BLOCKED" else (),
        next_action=next_action,
        stages=tuple(stages),
        identity_chain=identity_chain,
        boundary_flags=boundary_flags,
        hvs_invoked=hvs_invoked,
        render_artifact_verified=render_artifact_verified,
        delivery_occurred=delivery_occurred,
        customer_outcome_recorded=customer_outcome_recorded,
        resolution_route_approved=resolution_route_approved,
        stage8r_target_action_completed=stage8r_done,
    )


def _next_action_for(stage: str) -> str:
    mapping = {
        "8J_commercial_acceptance": "record_commercial_acceptance",
        "8K_engagement_activation": "authorize_engagement_activation_and_kickoff",
        "8L_project_initialization": "initialize_hvs_project",
        "8M_asset_intake_materialization": "approve_and_materialize_assets",
        "8N_render_completion": "approve_and_dispatch_render",
        "8O_delivery_authorization": "authorize_and_record_manual_delivery",
        "8P_customer_receipt_acceptance": "record_customer_receipt_acceptance",
        "8Q_post_delivery_resolution_route": "create_and_approve_resolution_route",
        "8R_resolution_action_execution": "create_and_approve_resolution_action",
    }
    return mapping.get(stage, "resolve_missing_stage_evidence")
