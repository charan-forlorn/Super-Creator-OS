"""SCOS Stage 5.2 built-in AI agent runtime registry.

A static, read-only catalogue of declared AI agent runtime surfaces. This
module does not launch, call, or drive any of the named runtimes — it only
describes them so ``work_session_manager`` has a deterministic set of valid
``runtime_id`` values to assign against.

``manual_clipboard`` is always present and always enabled: it is the
universal fallback runtime (the operator manually copies a prompt out and
pastes a result back in), so at least one runtime supports every task type
regardless of which named agent integrations exist yet.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid,
no network, no process launch.
"""

from __future__ import annotations

try:
    from .work_session_models import AgentRuntime, ALLOWED_TASK_TYPES
except ImportError:  # direct-module execution (tests insert the package dir)
    from work_session_models import AgentRuntime, ALLOWED_TASK_TYPES

RUNTIME_REGISTRY_SCHEMA_VERSION = 1

_ALL_TASK_TYPES = ALLOWED_TASK_TYPES

_BUILT_IN_RUNTIMES: tuple[AgentRuntime, ...] = (
    AgentRuntime.of(
        "chatgpt-app",
        "chatgpt",
        "chatgpt_app",
        "ChatGPT (desktop app)",
        supported_task_types=(
            "planning",
            "review",
            "audit",
            "status_update",
            "prompt_build",
            "result_summary",
        ),
        enabled=True,
    ),
    AgentRuntime.of(
        "chatgpt-web",
        "chatgpt",
        "chatgpt_web",
        "ChatGPT (web)",
        supported_task_types=(
            "planning",
            "review",
            "audit",
            "status_update",
            "prompt_build",
            "result_summary",
        ),
        enabled=True,
    ),
    AgentRuntime.of(
        "claude-code-cli",
        "claude_code",
        "claude_code_cli",
        "Claude Code (CLI)",
        supported_task_types=(
            "planning",
            "implementation",
            "review",
            "audit",
            "release_gate",
        ),
        enabled=True,
    ),
    AgentRuntime.of(
        "claude-code-vscode",
        "claude_code",
        "claude_code_vscode",
        "Claude Code (VS Code extension)",
        supported_task_types=(
            "planning",
            "implementation",
            "review",
            "audit",
        ),
        enabled=True,
    ),
    AgentRuntime.of(
        "codex-cli",
        "codex",
        "codex_cli",
        "Codex (CLI)",
        supported_task_types=(
            "implementation",
            "review",
            "audit",
        ),
        enabled=True,
    ),
    AgentRuntime.of(
        "codex-app",
        "codex",
        "codex_app",
        "Codex (app)",
        supported_task_types=(
            "implementation",
            "review",
        ),
        enabled=True,
    ),
    AgentRuntime.of(
        "hermes-cli",
        "hermes",
        "hermes_cli",
        "Hermes (CLI)",
        supported_task_types=(
            "planning",
            "status_update",
            "result_summary",
        ),
        enabled=True,
    ),
    AgentRuntime.of(
        "manual-clipboard",
        "chatgpt",
        "manual_clipboard",
        "Manual clipboard handoff",
        supported_task_types=_ALL_TASK_TYPES,
        enabled=True,
    ),
)

_BY_ID: dict[str, AgentRuntime] = {runtime.runtime_id: runtime for runtime in _BUILT_IN_RUNTIMES}


def list_runtimes() -> tuple[AgentRuntime, ...]:
    """Return every registered runtime, in fixed declaration order."""
    return _BUILT_IN_RUNTIMES


def get_runtime(runtime_id: str) -> AgentRuntime | None:
    """Return the runtime registered under ``runtime_id``, or ``None``."""
    return _BY_ID.get(str(runtime_id))


def find_runtimes_for_task(task_type: str) -> tuple[AgentRuntime, ...]:
    """Return enabled runtimes that declare support for ``task_type``.

    Result order is fixed declaration order. An unsupported/unknown
    ``task_type`` simply yields an empty tuple (this is a read-only lookup,
    not a validation gate — the manager rejects unknown task types).
    """
    return tuple(
        runtime
        for runtime in _BUILT_IN_RUNTIMES
        if runtime.enabled and task_type in runtime.supported_task_types
    )
