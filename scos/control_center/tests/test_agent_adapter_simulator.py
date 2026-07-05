"""test_agent_adapter_simulator.py - SCOS Stage 5.3 agent adapter simulator suite.

Plain executable script (no pytest). Covers the deterministic lifecycle
event sequence for contract_only/simulated and manual_clipboard delivery
modes, and error handling for invalid requests.

Run: python scos/control_center/tests/test_agent_adapter_simulator.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
sys.path.insert(0, str(_PACKAGE))

from agent_adapter_models import (  # noqa: E402
    AgentAdapterError,
    AgentAdapterRequest,
    AgentAdapterResult,
)
from agent_adapter_registry import create_default_agent_adapter_registry  # noqa: E402
from agent_adapter_simulator import (  # noqa: E402
    simulate_adapter_lifecycle,
    simulate_agent_adapter_request,
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


def _request(agent_name, runtime_type, task_type, *, delivery_mode="contract_only"):
    return AgentAdapterRequest.of(
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


def test_simulate_agent_adapter_request() -> None:
    registry = create_default_agent_adapter_registry()
    request = _request("chatgpt", "chatgpt_app", "planning")
    result = simulate_agent_adapter_request(
        registry=registry,
        request=request,
        created_at="2026-07-06T10:05:00Z",
        simulated_output_text="1. Plan A\n2. Plan B",
    )
    check("simulate_agent_adapter_request returns AgentAdapterResult", isinstance(result, AgentAdapterResult))
    check("simulate_agent_adapter_request reaches result_ready", result.status == "result_ready")

    bad_request = _request("chatgpt", "chatgpt_app", "implementation")
    bad_result = simulate_agent_adapter_request(
        registry=registry, request=bad_request, created_at="2026-07-06T10:05:00Z"
    )
    check(
        "simulate_agent_adapter_request returns AgentAdapterError for unroutable request",
        isinstance(bad_result, AgentAdapterError),
    )


def test_simulate_adapter_lifecycle_contract_only() -> None:
    registry = create_default_agent_adapter_registry()
    request = _request("claude_code", "claude_code_cli", "implementation")
    events = simulate_adapter_lifecycle(
        registry=registry,
        request=request,
        created_at="2026-07-06T10:10:00Z",
        simulated_output_text="Implementation report body",
    )
    check("lifecycle returns a tuple of events", isinstance(events, tuple))
    check(
        "lifecycle event sequence for contract_only delivery",
        [e.event_type for e in events]
        == [
            "request_created",
            "request_validated",
            "adapter_selected",
            "prompt_prepared",
            "simulated_sent",
            "result_simulated",
            "result_ready",
        ],
    )
    check("all events share the request_id", all(e.request_id == request.request_id for e in events))
    check("all events share the session_id", all(e.session_id == request.session_id for e in events))
    check("event ids are unique", len({e.event_id for e in events}) == len(events))
    check("final event status_after is result_ready", events[-1].status_after == "result_ready")


def test_simulate_adapter_lifecycle_manual_clipboard() -> None:
    registry = create_default_agent_adapter_registry()
    request = _request(
        "manual_clipboard", "manual_clipboard", "manual_handoff", delivery_mode="manual_clipboard"
    )
    events = simulate_adapter_lifecycle(
        registry=registry,
        request=request,
        created_at="2026-07-06T10:15:00Z",
        simulated_output_text="Rollback runbook drafted by the operator",
    )
    check(
        "lifecycle event sequence for manual_clipboard delivery",
        [e.event_type for e in events]
        == [
            "request_created",
            "request_validated",
            "adapter_selected",
            "prompt_prepared",
            "manual_clipboard_ready",
            "result_simulated",
            "result_ready",
        ],
    )


def test_simulate_adapter_lifecycle_invalid_request() -> None:
    registry = create_default_agent_adapter_registry()
    bad_request = _request("chatgpt", "chatgpt_app", "implementation")
    result = simulate_adapter_lifecycle(
        registry=registry, request=bad_request, created_at="2026-07-06T10:20:00Z"
    )
    check(
        "lifecycle returns AgentAdapterError for an unroutable request",
        isinstance(result, AgentAdapterError),
    )
    check("lifecycle error carries the request_id", result.request_id == bad_request.request_id)


def main() -> int:
    test_simulate_agent_adapter_request()
    test_simulate_adapter_lifecycle_contract_only()
    test_simulate_adapter_lifecycle_manual_clipboard()
    test_simulate_adapter_lifecycle_invalid_request()
    print(f"\n RESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
