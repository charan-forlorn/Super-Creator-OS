"""test_agent_adapter_contracts.py - SCOS Stage 5.3 agent adapter contract suite.

Plain executable script (no pytest). Covers identity/capability declarations
and the validate_request / prepare_prompt / simulate_send / capture_result
lifecycle for all five contract-only adapters.

Run: python scos/control_center/tests/test_agent_adapter_contracts.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
sys.path.insert(0, str(_PACKAGE))

from agent_adapter_contracts import (  # noqa: E402
    ChatGPTContractAdapter,
    ClaudeCodeContractAdapter,
    CodexContractAdapter,
    HermesContractAdapter,
    ManualClipboardContractAdapter,
)
from agent_adapter_models import (  # noqa: E402
    ALLOWED_ADAPTER_TASK_TYPES,
    AgentAdapterError,
    AgentAdapterRequest,
    AgentAdapterResult,
)

_PASS = 0
_FAIL = 0


def check(name: str, cond: bool) -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}")


def _request(agent_name, runtime_type, task_type, *, delivery_mode="contract_only", **overrides):
    kwargs = dict(
        request_id="req-001",
        session_id="session-001",
        task_id="task-001",
        agent_name=agent_name,
        runtime_id="rt-001",
        runtime_type=runtime_type,
        task_type=task_type,
        prompt_text="Do the work without any links.",
        input_summary="input",
        created_at="2026-07-06T10:00:00Z",
        delivery_mode=delivery_mode,
        expected_result_type="result_summary",
    )
    kwargs.update(overrides)
    return AgentAdapterRequest.of(**kwargs)


def test_identity_and_capabilities() -> None:
    chatgpt = ChatGPTContractAdapter()
    check("chatgpt agent_name", chatgpt.agent_name() == "chatgpt")
    check("chatgpt runtime_type", chatgpt.runtime_type() == "chatgpt_app")
    check("chatgpt has 2 capabilities", len(chatgpt.capabilities()) == 2)
    check(
        "chatgpt roles: planning/status_update/result_summary/prompt_build",
        set(chatgpt.capabilities()[0].task_types)
        == {"planning", "status_update", "result_summary", "prompt_build"},
    )

    claude = ClaudeCodeContractAdapter()
    check("claude_code agent_name", claude.agent_name() == "claude_code")
    check(
        "claude_code roles: implementation/prompt_build/release_gate",
        set(claude.capabilities()[0].task_types) == {"implementation", "prompt_build", "release_gate"},
    )

    codex = CodexContractAdapter()
    check("codex agent_name", codex.agent_name() == "codex")
    check(
        "codex roles: review/git_review/release_gate",
        set(codex.capabilities()[0].task_types) == {"review", "git_review", "release_gate"},
    )

    hermes = HermesContractAdapter()
    check("hermes agent_name", hermes.agent_name() == "hermes")
    check(
        "hermes roles: audit/status_update",
        set(hermes.capabilities()[0].task_types) == {"audit", "status_update"},
    )

    manual = ManualClipboardContractAdapter()
    check("manual_clipboard agent_name", manual.agent_name() == "manual_clipboard")
    check(
        "manual_clipboard supports every allowed task type",
        set(manual.capabilities()[0].task_types) == set(ALLOWED_ADAPTER_TASK_TYPES),
    )
    check(
        "manual_clipboard advertises manual fallback support",
        manual.capabilities()[0].supports_manual_fallback is True,
    )


def test_validate_request() -> None:
    chatgpt = ChatGPTContractAdapter()
    good = _request("chatgpt", "chatgpt_app", "planning")
    check("chatgpt validates a supported request", chatgpt.validate_request(good) == ())

    unsupported_task = _request("chatgpt", "chatgpt_app", "implementation")
    check(
        "chatgpt rejects unsupported task_type",
        len(chatgpt.validate_request(unsupported_task)) == 1,
    )

    wrong_agent = _request("codex", "chatgpt_app", "planning")
    check(
        "chatgpt rejects mismatched agent_name",
        len(ChatGPTContractAdapter().validate_request(wrong_agent)) >= 1,
    )

    manual = ManualClipboardContractAdapter()
    manual_request = _request(
        "manual_clipboard", "manual_clipboard", "manual_handoff", delivery_mode="manual_clipboard"
    )
    check("manual_clipboard validates manual delivery request", manual.validate_request(manual_request) == ())


def test_lifecycle_methods() -> None:
    chatgpt = ChatGPTContractAdapter()
    request = _request("chatgpt", "chatgpt_app", "planning", expected_result_type="plan")

    prepared = chatgpt.prepare_prompt(request)
    check("prepare_prompt returns AgentAdapterResult for valid request", isinstance(prepared, AgentAdapterResult))
    check("prepare_prompt status is prepared", prepared.status == "prepared")

    sent = chatgpt.simulate_send(request, created_at="2026-07-06T10:01:00Z")
    check("simulate_send returns AgentAdapterResult for valid request", isinstance(sent, AgentAdapterResult))
    check("simulate_send status is simulated_sent (non-manual delivery)", sent.status == "simulated_sent")

    captured = chatgpt.capture_result(
        request,
        output_text="1. Plan A\n2. Plan B",
        created_at="2026-07-06T10:02:00Z",
    )
    check("capture_result returns AgentAdapterResult for valid request", isinstance(captured, AgentAdapterResult))
    check("capture_result status is result_ready with output supplied", captured.status == "result_ready")
    check("capture_result carries output_text through", captured.output_text == "1. Plan A\n2. Plan B")

    no_output = chatgpt.capture_result(request, output_text=None, created_at="2026-07-06T10:02:00Z")
    check(
        "capture_result waits for operator when no output supplied",
        no_output.status == "waiting_for_operator",
    )

    bad_request = _request("chatgpt", "chatgpt_app", "implementation")
    bad_prepared = chatgpt.prepare_prompt(bad_request)
    check("prepare_prompt returns AgentAdapterError for unsupported task", isinstance(bad_prepared, AgentAdapterError))

    manual = ManualClipboardContractAdapter()
    manual_request = _request(
        "manual_clipboard", "manual_clipboard", "manual_handoff", delivery_mode="manual_clipboard"
    )
    manual_sent = manual.simulate_send(manual_request, created_at="2026-07-06T10:01:00Z")
    check(
        "manual_clipboard simulate_send waits for operator",
        isinstance(manual_sent, AgentAdapterResult) and manual_sent.status == "waiting_for_operator",
    )


def main() -> int:
    test_identity_and_capabilities()
    test_validate_request()
    test_lifecycle_methods()
    print(f"\n RESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
