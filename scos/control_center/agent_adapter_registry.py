"""SCOS Stage 5.3 AI agent adapter registry.

A static, deterministic catalogue of the five contract-only adapters
(ChatGPT, Claude Code, Codex, Hermes, manual clipboard fallback) with
lookup and routing helpers. This module does not launch, call, or drive
any of the named runtimes, does not probe the local environment, and does
not check which apps are installed — it only holds a fixed-order tuple of
adapter instances and picks among them by declared capability.

``manual_clipboard`` is always present and always enabled: it is the
universal fallback, so at least one adapter can serve every task type
regardless of which named agent integrations exist yet.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid,
no network, no process launch, no environment probing.
"""

from __future__ import annotations

try:
    from .agent_adapter_contracts import (
        BaseAgentAdapter,
        ChatGPTContractAdapter,
        ClaudeCodeContractAdapter,
        CodexContractAdapter,
        HermesContractAdapter,
        ManualClipboardContractAdapter,
    )
    from .agent_adapter_models import AgentAdapterCapability, AgentAdapterRequest
except ImportError:  # direct-module execution (tests insert the package dir)
    from agent_adapter_contracts import (
        BaseAgentAdapter,
        ChatGPTContractAdapter,
        ClaudeCodeContractAdapter,
        CodexContractAdapter,
        HermesContractAdapter,
        ManualClipboardContractAdapter,
    )
    from agent_adapter_models import AgentAdapterCapability, AgentAdapterRequest

AGENT_ADAPTER_REGISTRY_SCHEMA_VERSION = 1

MANUAL_CLIPBOARD_AGENT_NAME = "manual_clipboard"

# task_type -> (preferred agent_name, fallback-eligible alternate agent_name or None)
_PRIMARY_ROUTING: dict[str, str] = {
    "planning": "chatgpt",
    "implementation": "claude_code",
    "review": "codex",
    "audit": "hermes",
    "status_update": "chatgpt",
    "prompt_build": "chatgpt",
    "release_gate": "codex",
    "git_review": "codex",
    "manual_handoff": "manual_clipboard",
}

# task types where an explicit preferred_agent may pick a second valid agent
_ALTERNATE_ROUTING: dict[str, tuple[str, ...]] = {
    "prompt_build": ("chatgpt", "claude_code"),
    "release_gate": ("codex", "claude_code"),
}


class AgentAdapterRegistry:
    """Deterministic, read-only lookup over a fixed set of agent adapters."""

    def __init__(self, adapters: tuple[BaseAgentAdapter, ...]):
        self._adapters: tuple[BaseAgentAdapter, ...] = tuple(adapters)
        manual_adapters = [
            adapter
            for adapter in self._adapters
            if adapter.agent_name() == MANUAL_CLIPBOARD_AGENT_NAME
        ]
        if not manual_adapters:
            raise ValueError(
                "AgentAdapterRegistry requires a manual_clipboard fallback adapter"
            )
        self._manual_adapter: BaseAgentAdapter = manual_adapters[0]

    def list_adapters(self) -> tuple[BaseAgentAdapter, ...]:
        """Return every registered adapter, in fixed declaration order."""
        return self._adapters

    def list_capabilities(self) -> tuple[AgentAdapterCapability, ...]:
        """Return every capability from every adapter, in fixed declaration order."""
        capabilities: list[AgentAdapterCapability] = []
        for adapter in self._adapters:
            capabilities.extend(adapter.capabilities())
        return tuple(capabilities)

    def find_adapter(
        self, agent_name: str, runtime_type: str, task_type: str
    ) -> BaseAgentAdapter | None:
        """Return the adapter matching all three keys, or ``None``.

        Result is deterministic: the first adapter (in fixed declaration
        order) whose ``agent_name()`` matches and whose capabilities declare
        both ``runtime_type`` and ``task_type``.
        """
        for adapter in self._adapters:
            if adapter.agent_name() != agent_name:
                continue
            for capability in adapter.capabilities():
                if (
                    capability.runtime_type == runtime_type
                    and task_type in capability.task_types
                ):
                    return adapter
        return None

    def _adapter_for_agent(self, agent_name: str) -> BaseAgentAdapter | None:
        for adapter in self._adapters:
            if adapter.agent_name() == agent_name:
                return adapter
        return None

    def _adapter_supports_task(
        self, adapter: BaseAgentAdapter, task_type: str
    ) -> bool:
        return any(
            task_type in capability.task_types for capability in adapter.capabilities()
        )

    def recommend_adapter(
        self, task_type: str, preferred_agent: str | None = None
    ) -> BaseAgentAdapter:
        """Recommend the best adapter for ``task_type``.

        Routing order:
        1. If ``preferred_agent`` is given and is a valid alternate for
           ``task_type`` (or the primary routing target), and that adapter
           supports ``task_type``, use it.
        2. Otherwise use the primary routing target for ``task_type``, if
           that adapter supports it.
        3. Otherwise fall back to ``manual_clipboard`` (always available).
        """
        candidates: list[str] = []
        if preferred_agent is not None:
            allowed_alternates = _ALTERNATE_ROUTING.get(task_type, ())
            primary = _PRIMARY_ROUTING.get(task_type)
            if preferred_agent == primary or preferred_agent in allowed_alternates:
                candidates.append(preferred_agent)
        primary = _PRIMARY_ROUTING.get(task_type)
        if primary is not None and primary not in candidates:
            candidates.append(primary)

        for agent_name in candidates:
            adapter = self._adapter_for_agent(agent_name)
            if adapter is not None and self._adapter_supports_task(adapter, task_type):
                return adapter

        return self._manual_adapter

    def validate_request(self, request: AgentAdapterRequest) -> tuple[str, ...]:
        """Return a tuple of problem strings; empty tuple means valid.

        Allowed-value enforcement for each field already happened in
        ``AgentAdapterRequest.__post_init__``; this only checks adapter
        availability for the request's declared agent/runtime/task triple.
        """
        adapter = self.find_adapter(
            request.agent_name, request.runtime_type, request.task_type
        )
        if adapter is None:
            return (
                f"no registered adapter supports agent_name={request.agent_name!r}, "
                f"runtime_type={request.runtime_type!r}, "
                f"task_type={request.task_type!r}",
            )
        return adapter.validate_request(request)


def create_default_agent_adapter_registry() -> AgentAdapterRegistry:
    """Build the default registry: one adapter per named agent, in fixed order."""
    return AgentAdapterRegistry(
        (
            ChatGPTContractAdapter(),
            ClaudeCodeContractAdapter(),
            CodexContractAdapter(),
            HermesContractAdapter(),
            ManualClipboardContractAdapter(),
        )
    )
