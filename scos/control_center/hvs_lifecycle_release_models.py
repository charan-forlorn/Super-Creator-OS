"""Stage 8S — read-only full-lifecycle release inspector models.

These models are PURE DATA. They carry the operator-readable lifecycle status
returned by :mod:`hvs_lifecycle_release_service`. The inspector NEVER mutates
any stage record, never imports HVS, never touches the network, and never infers
completion: every field is derived from existing authoritative append-only
evidence.

Lifecycle states (operator vocabulary):

* ``READY``        — upstream steps complete, next operator action is allowed.
* ``BLOCKED``      — a required approval/evidence is missing; exact blocker set.
* ``CONFLICTED``   — contradictory or mismatched authoritative records.
* ``COMPLETED``    — terminal lifecycle reached (Stage 8R action verified).
* ``UNKNOWN``      — project id not found in any authoritative store.

This module contains no business mutation logic and no duplicate state machine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Ordered canonical lifecycle stages (8H -> 8R). The inspector walks this list
# and reports the first stage that is not yet satisfied as the "blocker".
LIFECYCLE_STAGES = (
    "8H_qualified_opportunity",
    "8I_proposal_preparation",
    "8J_commercial_acceptance",
    "8K_engagement_activation",
    "8L_project_initialization",
    "8M_asset_intake_materialization",
    "8N_render_completion",
    "8O_delivery_authorization",
    "8P_customer_receipt_acceptance",
    "8Q_post_delivery_resolution_route",
    "8R_resolution_action_execution",
)


# Distinct approval boundaries the inspector must confirm are SEPARATE.
APPROVAL_BOUNDARIES = (
    "commercial_handoff",
    "engagement_project_initialization",
    "asset_materialization",
    "render",
    "delivery_release",
    "stage8q_routing",
    "stage8r_action_execution",
)


@dataclass(frozen=True)
class StageEvidence:
    """Aggregated authoritative evidence for a single lifecycle stage."""

    stage: str
    present: bool
    status: str = ""  # e.g. VERIFIED / READY / APPROVED / COMPLETED
    record_id: str = ""
    content_hash: str = ""
    detail: str = ""


@dataclass(frozen=True)
class LifecycleSnapshot:
    """Read-only, operator-facing full-lifecycle view. No mutations."""  # noqa: D401

    project_id: str
    current_stage: str  # canonical stage id (or "UNKNOWN")
    state: str  # READY / BLOCKED / CONFLICTED / COMPLETED / UNKNOWN
    last_verified_record: dict[str, str] = field(default_factory=dict)
    blockers: tuple[str, ...] = ()
    next_action: str = ""  # exactly one allowed next operator action
    stages: tuple[StageEvidence, ...] = ()
    identity_chain: dict[str, str] = field(default_factory=dict)  # id/hash bindings
    boundary_flags: dict[str, bool] = field(default_factory=dict)
    hvs_invoked: bool = False
    render_artifact_verified: bool = False
    delivery_occurred: bool = False
    customer_outcome_recorded: bool = False
    resolution_route_approved: bool = False
    stage8r_target_action_completed: bool = False


@dataclass(frozen=True)
class LifecycleVerification:
    """Result of a non-mutating consistency verification across stages."""

    project_id: str
    ok: bool
    conflicts: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
