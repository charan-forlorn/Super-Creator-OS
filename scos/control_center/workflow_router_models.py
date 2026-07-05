from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Mapping, Any, Tuple, Optional
import json

try:
    from collections.abc import Mapping as MappingABC
except Exception:
    from collections import Mapping as MappingABC  # type: ignore


CROSS_AGENT_WORKFLOW_ROUTER_SCHEMA_VERSION = 1


class FrozenMap(MappingABC):
    """A minimal immutable mapping wrapper that serializes as a plain dict."""

    __slots__ = ("_data",)

    def __init__(self, data: Optional[Mapping[str, Any]] = None):
        self._data = dict(data or {})

    def __getitem__(self, key):
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)

    def to_dict(self):
        return dict(self._data)

    def __repr__(self):
        return f"FrozenMap({self._data!r})"


def _ensure_frozendict(d: Optional[Mapping[str, Any]]):
    if d is None:
        return FrozenMap()
    if isinstance(d, FrozenMap):
        return d
    return FrozenMap(d)


@dataclass(frozen=True)
class AgentRouteRule:
    rule_id: str
    name: str
    source_agent: str
    source_packet_type: Optional[str]
    result_status: Optional[str]
    review_decision: Optional[str]
    target_agent: str
    target_packet_type: str
    priority: str
    requires_operator_review: bool
    enabled: bool
    metadata: FrozenMap = field(default_factory=FrozenMap)

    ALLOWED_AGENTS = {"chatgpt", "claude_code", "codex", "hermes", "operator", "any"}
    ALLOWED_PRIORITIES = {"low", "normal", "high", "urgent"}

    def to_dict(self) -> dict:
        keys = [
            "rule_id",
            "name",
            "source_agent",
            "source_packet_type",
            "result_status",
            "review_decision",
            "target_agent",
            "target_packet_type",
            "priority",
            "requires_operator_review",
            "enabled",
            "metadata",
        ]
        out = {k: getattr(self, k) for k in keys}
        out["metadata"] = self.metadata.to_dict()
        return out

    @staticmethod
    def of(**kwargs) -> "AgentRouteRule":
        metadata = _ensure_frozendict(kwargs.pop("metadata", None))
        rule = AgentRouteRule(metadata=metadata, **kwargs)  # type: ignore[arg-type]
        return rule


@dataclass(frozen=True)
class RoutingDecision:
    ok: bool
    schema_version: int
    decision_id: str
    session_id: str
    source_packet_id: str
    source_result_packet_id: Optional[str]
    source_agent: str
    target_agent: str
    target_runtime_id: str
    route_rule_id: str
    route_reason: str
    next_packet_type: str
    requires_operator_review: bool
    decision_status: str
    created_at: str
    metadata: FrozenMap = field(default_factory=FrozenMap)

    def to_dict(self) -> dict:
        keys = [
            "ok",
            "schema_version",
            "decision_id",
            "session_id",
            "source_packet_id",
            "source_result_packet_id",
            "source_agent",
            "target_agent",
            "target_runtime_id",
            "route_rule_id",
            "route_reason",
            "next_packet_type",
            "requires_operator_review",
            "decision_status",
            "created_at",
            "metadata",
        ]
        out = {k: getattr(self, k) for k in keys}
        out["metadata"] = self.metadata.to_dict()
        return out


@dataclass(frozen=True)
class RoutePlanStep:
    step_id: str
    step_order: int
    source_agent: str
    target_agent: str
    packet_type: str
    status: str
    decision_id: Optional[str]
    metadata: FrozenMap = field(default_factory=FrozenMap)

    def to_dict(self) -> dict:
        keys = [
            "step_id",
            "step_order",
            "source_agent",
            "target_agent",
            "packet_type",
            "status",
            "decision_id",
            "metadata",
        ]
        out = {k: getattr(self, k) for k in keys}
        out["metadata"] = self.metadata.to_dict()
        return out


@dataclass(frozen=True)
class CrossAgentRoutePlan:
    ok: bool
    schema_version: int
    route_plan_id: str
    session_id: str
    task_id: str
    current_agent: str
    current_packet_id: str
    current_result_packet_id: Optional[str]
    next_decision: RoutingDecision
    steps: Tuple[RoutePlanStep, ...]
    created_at: str
    status: str
    metadata: FrozenMap = field(default_factory=FrozenMap)

    def to_dict(self) -> dict:
        keys = [
            "ok",
            "schema_version",
            "route_plan_id",
            "session_id",
            "task_id",
            "current_agent",
            "current_packet_id",
            "current_result_packet_id",
            "next_decision",
            "steps",
            "created_at",
            "status",
            "metadata",
        ]
        out = {}
        for k in keys:
            v = getattr(self, k)
            if k == "next_decision":
                out[k] = v.to_dict()
            elif k == "steps":
                out[k] = [s.to_dict() for s in v]
            elif k == "metadata":
                out[k] = self.metadata.to_dict()
            else:
                out[k] = v
        return out


@dataclass(frozen=True)
class WorkflowRouterError:
    ok: bool
    schema_version: int
    error_kind: str
    error_detail: str
    failed_step: str
    session_id: Optional[str]
    packet_id: Optional[str]
    metadata: FrozenMap = field(default_factory=FrozenMap)

    def to_dict(self) -> dict:
        keys = [
            "ok",
            "schema_version",
            "error_kind",
            "error_detail",
            "failed_step",
            "session_id",
            "packet_id",
            "metadata",
        ]
        out = {k: getattr(self, k) for k in keys}
        out["metadata"] = self.metadata.to_dict()
        return out
