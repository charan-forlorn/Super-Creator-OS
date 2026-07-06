"""SCOS Stage 5.6 cross-agent workflow router JSONL route store.

Append-only JSONL persistence for cross-agent route plans.
"""

from __future__ import annotations
from typing import Tuple, Optional, Mapping, Any
import json

try:
    from .workflow_router_models import (
        CrossAgentRoutePlan,
        RoutingDecision,
        RoutePlanStep,
        FrozenMap,
        WorkflowRouterError,
        CROSS_AGENT_WORKFLOW_ROUTER_SCHEMA_VERSION,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from workflow_router_models import (
        CrossAgentRoutePlan,
        RoutingDecision,
        RoutePlanStep,
        FrozenMap,
        WorkflowRouterError,
        CROSS_AGENT_WORKFLOW_ROUTER_SCHEMA_VERSION,
    )
import os


_JSON_SEP = (",", ":")


def _validate_path(path: str) -> None:
    if not isinstance(path, str) or "://" in path:
        raise ValueError("invalid path")


def append_route_plan(path: str, route_plan: CrossAgentRoutePlan) -> None:
    _validate_path(path)
    dirname = os.path.dirname(path)
    if dirname and not os.path.exists(dirname):
        os.makedirs(dirname, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        # deterministic serialization
        line = json.dumps(route_plan.to_dict(), sort_keys=True, separators=(",", ":"))
        f.write(line + "\n")


def _dict_to_route_plan(d: Mapping[str, Any]) -> CrossAgentRoutePlan:
    nd = dict(d)
    nd_next = nd["next_decision"]
    rd = RoutingDecision(
        ok=nd_next["ok"],
        schema_version=nd_next["schema_version"],
        decision_id=nd_next["decision_id"],
        session_id=nd_next["session_id"],
        source_packet_id=nd_next.get("source_packet_id"),
        source_result_packet_id=nd_next.get("source_result_packet_id"),
        source_agent=nd_next.get("source_agent"),
        target_agent=nd_next.get("target_agent"),
        target_runtime_id=nd_next.get("target_runtime_id"),
        route_rule_id=nd_next.get("route_rule_id"),
        route_reason=nd_next.get("route_reason"),
        next_packet_type=nd_next.get("next_packet_type"),
        requires_operator_review=nd_next.get("requires_operator_review"),
        decision_status=nd_next.get("decision_status"),
        created_at=nd_next.get("created_at"),
        metadata=FrozenMap(nd_next.get("metadata", {})),
    )

    steps = tuple(
        RoutePlanStep(
            step_id=s["step_id"],
            step_order=s["step_order"],
            source_agent=s["source_agent"],
            target_agent=s["target_agent"],
            packet_type=s["packet_type"],
            status=s["status"],
            decision_id=s.get("decision_id"),
            metadata=FrozenMap(s.get("metadata", {})),
        )
        for s in nd.get("steps", [])
    )

    plan = CrossAgentRoutePlan(
        ok=nd.get("ok", True),
        schema_version=nd.get("schema_version", CROSS_AGENT_WORKFLOW_ROUTER_SCHEMA_VERSION),
        route_plan_id=nd.get("route_plan_id"),
        session_id=nd.get("session_id"),
        task_id=nd.get("task_id"),
        current_agent=nd.get("current_agent"),
        current_packet_id=nd.get("current_packet_id"),
        current_result_packet_id=nd.get("current_result_packet_id"),
        next_decision=rd,
        steps=steps,
        created_at=nd.get("created_at"),
        status=nd.get("status"),
        metadata=FrozenMap(nd.get("metadata", {})),
    )
    return plan


def load_route_plans(path: str) -> Tuple[CrossAgentRoutePlan, ...]:
    _validate_path(path)
    if not os.path.exists(path):
        return tuple()
    plans = []
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception as e:
                raise ValueError(f"invalid json line: {e}")
            plans.append(_dict_to_route_plan(d))
    return tuple(plans)


def find_route_plan(path: str, route_plan_id: str) -> Optional[CrossAgentRoutePlan]:
    plans = load_route_plans(path)
    for p in plans:
        if p.route_plan_id == route_plan_id:
            return p
    return None


def load_latest_route_plan_for_session(path: str, session_id: str) -> Optional[CrossAgentRoutePlan]:
    plans = load_route_plans(path)
    for p in reversed(plans):
        if p.session_id == session_id:
            return p
    return None
