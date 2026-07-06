"""SCOS Stage 5.6 cross-agent workflow router.

Deterministic route rule defaults and next-agent route planning for the
cross-agent workflow router.
"""

from __future__ import annotations
from typing import Optional, Mapping, Any, Tuple, Dict

try:
    from .workflow_router_models import (
        AgentRouteRule,
        CrossAgentRoutePlan,
        RoutePlanStep,
        RoutingDecision,
        WorkflowRouterError,
        CROSS_AGENT_WORKFLOW_ROUTER_SCHEMA_VERSION,
        FrozenMap,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from workflow_router_models import (
        AgentRouteRule,
        CrossAgentRoutePlan,
        RoutePlanStep,
        RoutingDecision,
        WorkflowRouterError,
        CROSS_AGENT_WORKFLOW_ROUTER_SCHEMA_VERSION,
        FrozenMap,
    )
import hashlib


MANUAL_CLIPBOARD_RUNTIME_ID = "manual_clipboard"


def create_default_agent_route_rules() -> Tuple[AgentRouteRule, ...]:
    rules = []
    # 1 ChatGPT planning result -> Claude Code implementation prompt
    rules.append(
        AgentRouteRule.of(
            rule_id="chatgpt_planning_to_claude_impl",
            name="chatgpt planning -> claude implementation",
            source_agent="chatgpt",
            source_packet_type="planning_prompt",
            result_status="success",
            review_decision=None,
            target_agent="claude_code",
            target_packet_type="implementation_prompt",
            priority="normal",
            requires_operator_review=True,
            enabled=True,
        )
    )
    # 2 Claude Code implementation result -> Codex review prompt
    rules.append(
        AgentRouteRule.of(
            rule_id="claude_impl_to_codex_review",
            name="claude impl -> codex review",
            source_agent="claude_code",
            source_packet_type="implementation_prompt",
            result_status="success",
            review_decision=None,
            target_agent="codex",
            target_packet_type="review_prompt",
            priority="normal",
            requires_operator_review=True,
            enabled=True,
        )
    )
    # 3 Claude Code implementation blocked -> ChatGPT status update prompt
    rules.append(
        AgentRouteRule.of(
            rule_id="claude_impl_blocked_to_chatgpt_status",
            name="claude blocked -> chatgpt status",
            source_agent="claude_code",
            source_packet_type=None,
            result_status="blocked",
            review_decision=None,
            target_agent="chatgpt",
            target_packet_type="status_update_prompt",
            priority="high",
            requires_operator_review=True,
            enabled=True,
        )
    )
    # 4 Codex review pass -> Hermes audit prompt
    rules.append(
        AgentRouteRule.of(
            rule_id="codex_pass_to_hermes_audit",
            name="codex pass -> hermes audit",
            source_agent="codex",
            source_packet_type="review_prompt",
            result_status="pass",
            review_decision=None,
            target_agent="hermes",
            target_packet_type="audit_prompt",
            priority="normal",
            requires_operator_review=True,
            enabled=True,
        )
    )
    # 5 Codex review fail -> Claude Code revision prompt
    rules.append(
        AgentRouteRule.of(
            rule_id="codex_fail_to_claude_revision",
            name="codex fail -> claude revision",
            source_agent="codex",
            source_packet_type="review_prompt",
            result_status="fail",
            review_decision=None,
            target_agent="claude_code",
            target_packet_type="implementation_prompt",
            priority="normal",
            requires_operator_review=True,
            enabled=True,
        )
    )
    # 6 Hermes audit pass -> ChatGPT result summary prompt
    rules.append(
        AgentRouteRule.of(
            rule_id="hermes_pass_to_chatgpt_summary",
            name="hermes pass -> chatgpt summary",
            source_agent="hermes",
            source_packet_type="audit_prompt",
            result_status="pass",
            review_decision=None,
            target_agent="chatgpt",
            target_packet_type="result_summary_prompt",
            priority="normal",
            requires_operator_review=True,
            enabled=True,
        )
    )
    # 7 Hermes audit fail -> Codex review prompt
    rules.append(
        AgentRouteRule.of(
            rule_id="hermes_fail_to_codex_review",
            name="hermes fail -> codex review",
            source_agent="hermes",
            source_packet_type="audit_prompt",
            result_status="fail",
            review_decision=None,
            target_agent="codex",
            target_packet_type="review_prompt",
            priority="normal",
            requires_operator_review=True,
            enabled=True,
        )
    )
    # 8 Any blocked result -> ChatGPT status update prompt
    rules.append(
        AgentRouteRule.of(
            rule_id="any_blocked_to_chatgpt_status",
            name="any blocked -> chatgpt status",
            source_agent="any",
            source_packet_type=None,
            result_status="blocked",
            review_decision=None,
            target_agent="chatgpt",
            target_packet_type="status_update_prompt",
            priority="urgent",
            requires_operator_review=True,
            enabled=True,
        )
    )
    # 9 Any needs_revision operator decision -> source agent revision prompt
    rules.append(
        AgentRouteRule.of(
            rule_id="operator_needs_revision_to_source",
            name="operator needs_revision -> source revision",
            source_agent="any",
            source_packet_type=None,
            result_status=None,
            review_decision="needs_revision",
            target_agent="source_agent",
            target_packet_type="same_as_source",
            priority="normal",
            requires_operator_review=True,
            enabled=True,
        )
    )
    # 10 Any rejected operator decision -> blocked/manual handoff to operator
    rules.append(
        AgentRouteRule.of(
            rule_id="operator_rejected_to_operator_handoff",
            name="operator rejected -> operator manual handoff",
            source_agent="any",
            source_packet_type=None,
            result_status=None,
            review_decision="rejected",
            target_agent="operator",
            target_packet_type="manual_handoff_prompt",
            priority="urgent",
            requires_operator_review=False,
            enabled=True,
        )
    )
    return tuple(rules)


def _hash_hex(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"|")
    return h.hexdigest()


def _pick_runtime_for_agent(target_agent: str, runtime_registry: Optional[Mapping[str, Mapping[str, Any]]]) -> str:
    if runtime_registry:
        candidates = [rid for rid, meta in runtime_registry.items() if meta.get("enabled") and meta.get("agent") == target_agent]
        if candidates:
            candidates.sort()
            return candidates[0]
    return MANUAL_CLIPBOARD_RUNTIME_ID


def plan_next_agent_route(
    *,
    session_id: str,
    task_id: str,
    source_packet: Mapping[str, Any],
    result_packet: Optional[Mapping[str, Any]] = None,
    operator_review: Optional[Mapping[str, Any]] = None,
    route_rules: Optional[Tuple[AgentRouteRule, ...]] = None,
    runtime_registry: Optional[Mapping[str, Mapping[str, Any]]] = None,
    created_at: str,
) -> CrossAgentRoutePlan | WorkflowRouterError:
    # Validation
    if not created_at:
        return WorkflowRouterError(
            ok=False,
            schema_version=CROSS_AGENT_WORKFLOW_ROUTER_SCHEMA_VERSION,
            error_kind="validation",
            error_detail="created_at is required",
            failed_step="validation",
            session_id=session_id,
            packet_id=source_packet.get("packet_id") if source_packet else None,
        )

    route_rules = route_rules or create_default_agent_route_rules()

    # normalize inputs
    src_agent = source_packet.get("source_agent") or source_packet.get("agent") or source_packet.get("source")
    src_packet_type = source_packet.get("packet_type") or source_packet.get("type")
    src_packet_id = source_packet.get("packet_id") or source_packet.get("id")
    result_status = None
    result_id = None
    if result_packet:
        result_status = result_packet.get("result_status") or result_packet.get("status")
        result_id = result_packet.get("result_packet_id") or result_packet.get("id")

    # Priority checks
    decision_rule = None

    # 1. rejected operator decision
    if operator_review and operator_review.get("decision") == "rejected":
        # find rejected rule
        for r in route_rules:
            if r.review_decision == "rejected":
                decision_rule = r
                break

    # 2. needs_revision operator decision
    if decision_rule is None and operator_review and operator_review.get("decision") == "needs_revision":
        for r in route_rules:
            if r.review_decision == "needs_revision":
                decision_rule = r
                break

    # 3. blocked result
    if decision_rule is None and result_status == "blocked":
        # prefer exact source_agent blocked rule
        for r in route_rules:
            if r.result_status == "blocked" and (r.source_agent == src_agent or r.source_agent == "any"):
                decision_rule = r
                break

    # 4. exact match source_agent + packet_type + result_status
    if decision_rule is None and result_status is not None and src_packet_type is not None:
        for r in route_rules:
            if r.source_agent in (src_agent, "any") and r.source_packet_type == src_packet_type and r.result_status == result_status:
                decision_rule = r
                break

    # 5. source_agent + result_status
    if decision_rule is None and result_status is not None:
        for r in route_rules:
            if r.source_agent in (src_agent, "any") and r.result_status == result_status:
                decision_rule = r
                break

    # 6. fallback to ChatGPT status_update_prompt with blocked status
    if decision_rule is None:
        for r in route_rules:
            if r.rule_id == "any_blocked_to_chatgpt_status":
                decision_rule = r
                break

    if decision_rule is None:
        return WorkflowRouterError(
            ok=False,
            schema_version=CROSS_AGENT_WORKFLOW_ROUTER_SCHEMA_VERSION,
            error_kind="no_rule",
            error_detail="no routing rule matched",
            failed_step="matching",
            session_id=session_id,
            packet_id=src_packet_id,
        )

    # Determine resolved target agent and packet_type
    target_agent = decision_rule.target_agent
    target_packet_type = decision_rule.target_packet_type

    # special handling for rules that reference source_agent or same_as_source
    if target_agent == "source_agent":
        target_agent = src_agent
    if target_packet_type == "same_as_source":
        target_packet_type = src_packet_type

    # runtime selection
    target_runtime_id = _pick_runtime_for_agent(target_agent, runtime_registry)

    # decision id deterministic
    decision_id = _hash_hex(session_id or "", task_id or "", str(src_packet_id or ""), created_at or "", decision_rule.rule_id)

    decision_status = "proposed"
    if decision_rule.requires_operator_review:
        decision_status = "review_required"
    if operator_review and operator_review.get("decision") == "rejected":
        decision_status = "rejected"
    if operator_review and operator_review.get("decision") == "needs_revision":
        decision_status = "review_required"

    route_reason = f"matched_rule:{decision_rule.rule_id}"

    routing_decision = RoutingDecision(
        ok=True,
        schema_version=CROSS_AGENT_WORKFLOW_ROUTER_SCHEMA_VERSION,
        decision_id=decision_id,
        session_id=session_id,
        source_packet_id=src_packet_id,
        source_result_packet_id=result_id,
        source_agent=src_agent,
        target_agent=target_agent,
        target_runtime_id=target_runtime_id,
        route_rule_id=decision_rule.rule_id,
        route_reason=route_reason,
        next_packet_type=target_packet_type,
        requires_operator_review=decision_rule.requires_operator_review,
        decision_status=decision_status,
        created_at=created_at,
        metadata=_ensure_metadata(decision_rule),
    )

    # step
    step_id = _hash_hex("step", decision_id, "1")
    step = RoutePlanStep(
        step_id=step_id,
        step_order=1,
        source_agent=src_agent,
        target_agent=target_agent,
        packet_type=target_packet_type,
        status="proposed" if decision_status == "proposed" else "review_required",
        decision_id=decision_id,
        metadata=FrozenMap({"rule_id": decision_rule.rule_id}),
    )

    route_plan_id = _hash_hex(session_id or "", task_id or "", src_packet_id or "", decision_id)

    plan = CrossAgentRoutePlan(
        ok=True,
        schema_version=CROSS_AGENT_WORKFLOW_ROUTER_SCHEMA_VERSION,
        route_plan_id=route_plan_id,
        session_id=session_id,
        task_id=task_id,
        current_agent=src_agent,
        current_packet_id=src_packet_id,
        current_result_packet_id=result_id,
        next_decision=routing_decision,
        steps=(step,),
        created_at=created_at,
        status=("blocked" if decision_status == "rejected" else "active"),
        metadata=FrozenMap({}),
    )

    return plan


def _ensure_metadata(rule: AgentRouteRule) -> FrozenMap:
    md = {"rule_name": rule.name, "priority": rule.priority}
    return FrozenMap(md)
