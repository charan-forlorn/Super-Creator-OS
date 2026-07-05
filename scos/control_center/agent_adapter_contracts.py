"""SCOS Stage 5.3 AI Agent Adapter contracts.

Defines the adapter boundary — ``BaseAgentAdapter`` — and five contract-only
adapters (ChatGPT, Claude Code, Codex, Hermes, manual clipboard fallback)
that describe capability, validate requests, and build deterministic result
records. NONE of these adapters send anything anywhere: there is no
network call, no API call, no browser automation, no GUI automation, no
clipboard access, no process launch. Every method only reads its own
declared capabilities and the caller-supplied request/output values and
returns a plain dataclass.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid,
no network, no subprocess, no file I/O.
"""

from __future__ import annotations

try:
    from .agent_adapter_models import (
        AgentAdapterCapability,
        AgentAdapterError,
        AgentAdapterRequest,
        AgentAdapterResult,
        ALLOWED_ADAPTER_TASK_TYPES,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from agent_adapter_models import (
        AgentAdapterCapability,
        AgentAdapterError,
        AgentAdapterRequest,
        AgentAdapterResult,
        ALLOWED_ADAPTER_TASK_TYPES,
    )

AGENT_ADAPTER_CONTRACT_SCHEMA_VERSION = 1


class BaseAgentAdapter:
    """Contract every AI agent adapter must implement.

    This base class provides shared, side-effect-free helpers
    (``validate_request``, ``prepare_prompt``, ``simulate_send``,
    ``capture_result``) built only from a subclass's own declared
    ``capabilities()``. It never sends, calls, launches, or reads anything
    external — every method here is a pure function of its inputs.
    """

    def adapter_id(self) -> str:
        raise NotImplementedError

    def agent_name(self) -> str:
        raise NotImplementedError

    def runtime_type(self) -> str:
        raise NotImplementedError

    def capabilities(self) -> tuple[AgentAdapterCapability, ...]:
        raise NotImplementedError

    def _capability_for(self, runtime_type: str) -> AgentAdapterCapability | None:
        for capability in self.capabilities():
            if capability.runtime_type == runtime_type:
                return capability
        return None

    def validate_request(self, request: AgentAdapterRequest) -> tuple[str, ...]:
        """Return a tuple of problem strings; empty tuple means valid.

        Only checks this adapter's own capability surface against the
        request — allowed-value enforcement for each field is already done
        by ``AgentAdapterRequest.__post_init__``.
        """
        problems: list[str] = []
        if request.agent_name != self.agent_name():
            problems.append(
                f"request.agent_name {request.agent_name!r} does not match "
                f"adapter agent_name {self.agent_name()!r}"
            )
        capability = self._capability_for(request.runtime_type)
        if capability is None:
            problems.append(
                f"adapter {self.adapter_id()!r} declares no capability for "
                f"runtime_type {request.runtime_type!r}"
            )
            return tuple(problems)
        if request.task_type not in capability.task_types:
            problems.append(
                f"adapter {self.adapter_id()!r} does not support task_type "
                f"{request.task_type!r} for runtime_type {request.runtime_type!r}"
            )
        if (
            request.delivery_mode == "manual_clipboard"
            and not capability.supports_manual_fallback
        ):
            problems.append(
                f"adapter {self.adapter_id()!r} does not support manual_clipboard "
                "delivery"
            )
        return tuple(problems)

    def prepare_prompt(
        self, request: AgentAdapterRequest
    ) -> AgentAdapterResult | AgentAdapterError:
        """Build a deterministic 'prepared' result. Sends nothing."""
        problems = self.validate_request(request)
        if problems:
            return AgentAdapterError.of(
                "contract_violation",
                "; ".join(problems),
                "prepare_prompt",
                request_id=request.request_id,
            )
        return AgentAdapterResult.of(
            result_id=f"{request.request_id}-prepared",
            request_id=request.request_id,
            session_id=request.session_id,
            agent_name=request.agent_name,
            runtime_id=request.runtime_id,
            status="prepared",
            result_type=request.expected_result_type,
            result_summary=f"Prompt prepared for {request.agent_name} "
            f"({request.task_type})",
            created_at=request.created_at,
            next_action="send prompt to adapter (simulated)",
        )

    def simulate_send(
        self, request: AgentAdapterRequest, *, created_at: str
    ) -> AgentAdapterResult | AgentAdapterError:
        """Build a deterministic 'simulated_sent' or 'waiting_for_operator'
        result. Sends nothing — no network, no clipboard, no process."""
        problems = self.validate_request(request)
        if problems:
            return AgentAdapterError.of(
                "contract_violation",
                "; ".join(problems),
                "simulate_send",
                request_id=request.request_id,
            )
        capability = self._capability_for(request.runtime_type)
        if request.delivery_mode == "manual_clipboard":
            return AgentAdapterResult.of(
                result_id=f"{request.request_id}-sent",
                request_id=request.request_id,
                session_id=request.session_id,
                agent_name=request.agent_name,
                runtime_id=request.runtime_id,
                status="waiting_for_operator",
                result_type=request.expected_result_type,
                result_summary="Prompt packet ready for manual clipboard handoff",
                created_at=created_at,
                next_action="operator copies prompt to the target app manually",
            )
        return AgentAdapterResult.of(
            result_id=f"{request.request_id}-sent",
            request_id=request.request_id,
            session_id=request.session_id,
            agent_name=request.agent_name,
            runtime_id=request.runtime_id,
            status="simulated_sent",
            result_type=request.expected_result_type,
            result_summary=f"Simulated send to {request.agent_name} "
            f"({capability.runtime_type if capability else request.runtime_type})",
            created_at=created_at,
            next_action="await simulated result capture",
        )

    def capture_result(
        self,
        request: AgentAdapterRequest,
        *,
        output_text: str | None,
        output_path: str | None = None,
        created_at: str,
    ) -> AgentAdapterResult | AgentAdapterError:
        """Build a deterministic result from caller-supplied output only.

        Never reads a clipboard, file, or network resource — ``output_text``
        / ``output_path`` are plain caller-supplied strings.
        """
        problems = self.validate_request(request)
        if problems:
            return AgentAdapterError.of(
                "contract_violation",
                "; ".join(problems),
                "capture_result",
                request_id=request.request_id,
            )
        if output_text is None and output_path is None:
            return AgentAdapterResult.of(
                result_id=f"{request.request_id}-result",
                request_id=request.request_id,
                session_id=request.session_id,
                agent_name=request.agent_name,
                runtime_id=request.runtime_id,
                status="waiting_for_operator",
                result_type=request.expected_result_type,
                result_summary="No simulated output supplied yet",
                created_at=created_at,
                next_action="operator supplies result text or path",
            )
        return AgentAdapterResult.of(
            result_id=f"{request.request_id}-result",
            request_id=request.request_id,
            session_id=request.session_id,
            agent_name=request.agent_name,
            runtime_id=request.runtime_id,
            status="result_ready",
            result_type=request.expected_result_type,
            result_summary=f"Simulated result captured for {request.agent_name}",
            output_text=output_text,
            output_path=output_path,
            created_at=created_at,
            next_action="attach result to work session",
        )


class ChatGPTContractAdapter(BaseAgentAdapter):
    """Contract-only adapter for ChatGPT: planning, status, summaries, prompt building."""

    def adapter_id(self) -> str:
        return "chatgpt-contract"

    def agent_name(self) -> str:
        return "chatgpt"

    def runtime_type(self) -> str:
        return "chatgpt_app"

    def capabilities(self) -> tuple[AgentAdapterCapability, ...]:
        task_types = (
            "planning",
            "status_update",
            "result_summary",
            "prompt_build",
        )
        return (
            AgentAdapterCapability.of(
                "chatgpt-app-cap",
                "chatgpt",
                "chatgpt_app",
                task_types=task_types,
                supports_prompt_delivery=True,
                supports_result_capture=True,
                supports_status_check=False,
                supports_manual_fallback=False,
            ),
            AgentAdapterCapability.of(
                "chatgpt-web-cap",
                "chatgpt",
                "chatgpt_web",
                task_types=task_types,
                supports_prompt_delivery=True,
                supports_result_capture=True,
                supports_status_check=False,
                supports_manual_fallback=False,
            ),
        )


class ClaudeCodeContractAdapter(BaseAgentAdapter):
    """Contract-only adapter for Claude Code: implementation, prompt building, release gates."""

    def adapter_id(self) -> str:
        return "claude-code-contract"

    def agent_name(self) -> str:
        return "claude_code"

    def runtime_type(self) -> str:
        return "claude_code_cli"

    def capabilities(self) -> tuple[AgentAdapterCapability, ...]:
        task_types = (
            "implementation",
            "prompt_build",
            "release_gate",
        )
        return (
            AgentAdapterCapability.of(
                "claude-code-cli-cap",
                "claude_code",
                "claude_code_cli",
                task_types=task_types,
                supports_prompt_delivery=True,
                supports_result_capture=True,
                supports_status_check=True,
                supports_manual_fallback=False,
            ),
            AgentAdapterCapability.of(
                "claude-code-vscode-cap",
                "claude_code",
                "claude_code_vscode",
                task_types=task_types,
                supports_prompt_delivery=True,
                supports_result_capture=True,
                supports_status_check=True,
                supports_manual_fallback=False,
            ),
        )


class CodexContractAdapter(BaseAgentAdapter):
    """Contract-only adapter for Codex: review, git review, release gates."""

    def adapter_id(self) -> str:
        return "codex-contract"

    def agent_name(self) -> str:
        return "codex"

    def runtime_type(self) -> str:
        return "codex_cli"

    def capabilities(self) -> tuple[AgentAdapterCapability, ...]:
        task_types = (
            "review",
            "git_review",
            "release_gate",
        )
        return (
            AgentAdapterCapability.of(
                "codex-cli-cap",
                "codex",
                "codex_cli",
                task_types=task_types,
                supports_prompt_delivery=True,
                supports_result_capture=True,
                supports_status_check=False,
                supports_manual_fallback=False,
            ),
            AgentAdapterCapability.of(
                "codex-app-cap",
                "codex",
                "codex_app",
                task_types=task_types,
                supports_prompt_delivery=True,
                supports_result_capture=True,
                supports_status_check=False,
                supports_manual_fallback=False,
            ),
        )


class HermesContractAdapter(BaseAgentAdapter):
    """Contract-only adapter for Hermes: audits, status updates."""

    def adapter_id(self) -> str:
        return "hermes-contract"

    def agent_name(self) -> str:
        return "hermes"

    def runtime_type(self) -> str:
        return "hermes_cli"

    def capabilities(self) -> tuple[AgentAdapterCapability, ...]:
        return (
            AgentAdapterCapability.of(
                "hermes-cli-cap",
                "hermes",
                "hermes_cli",
                task_types=("audit", "status_update"),
                supports_prompt_delivery=True,
                supports_result_capture=True,
                supports_status_check=True,
                supports_manual_fallback=False,
            ),
        )


class ManualClipboardContractAdapter(BaseAgentAdapter):
    """Always-available manual clipboard fallback adapter.

    Supports every allowed task type as a fallback and always advertises
    manual fallback support. It never reads or writes a real clipboard —
    it only models the "operator copies text manually" step as data.
    """

    def adapter_id(self) -> str:
        return "manual-clipboard-contract"

    def agent_name(self) -> str:
        return "manual_clipboard"

    def runtime_type(self) -> str:
        return "manual_clipboard"

    def capabilities(self) -> tuple[AgentAdapterCapability, ...]:
        return (
            AgentAdapterCapability.of(
                "manual-clipboard-cap",
                "manual_clipboard",
                "manual_clipboard",
                task_types=ALLOWED_ADAPTER_TASK_TYPES,
                supports_prompt_delivery=True,
                supports_result_capture=True,
                supports_status_check=False,
                supports_manual_fallback=True,
            ),
        )
