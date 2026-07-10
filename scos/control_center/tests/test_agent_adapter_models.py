"""test_agent_adapter_models.py - SCOS Stage 5.3 agent adapter model suite.

Plain executable script (no pytest). Covers to_dict key order, frozen
immutability, tuple serialization, deterministic factories, and enum
enforcement for all five Stage 5.3 models.

Run: python scos/control_center/tests/test_agent_adapter_models.py
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
sys.path.insert(0, str(_PACKAGE))

from agent_adapter_models import (  # noqa: E402
    AI_AGENT_ADAPTER_SCHEMA_VERSION,
    ALLOWED_ADAPTER_AGENT_NAMES,
    ALLOWED_ADAPTER_ERROR_KINDS,
    ALLOWED_ADAPTER_EVENT_TYPES,
    ALLOWED_ADAPTER_RUNTIME_TYPES,
    ALLOWED_ADAPTER_STATUSES,
    ALLOWED_ADAPTER_TASK_TYPES,
    ALLOWED_DELIVERY_MODES,
    ALLOWED_RESULT_TYPES,
    AgentAdapterCapability,
    AgentAdapterError,
    AgentAdapterRequest,
    AgentAdapterResult,
    AgentAdapterSimulationEvent,
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


def _make_capability() -> AgentAdapterCapability:
    return AgentAdapterCapability.of(
        "cap-1",
        "chatgpt",
        "chatgpt_app",
        task_types=("planning", "status_update"),
        supports_prompt_delivery=True,
        supports_result_capture=True,
        supports_status_check=False,
        supports_manual_fallback=False,
        metadata={"note": "test"},
    )


def _make_request(**overrides) -> AgentAdapterRequest:
    kwargs = dict(
        request_id="req-001",
        session_id="session-001",
        task_id="task-001",
        agent_name="chatgpt",
        runtime_id="chatgpt-app",
        runtime_type="chatgpt_app",
        task_type="planning",
        prompt_text="Draft a plan for Stage 5.4.",
        input_summary="Stage 5.3 acceptance summary",
        created_at="2026-07-06T10:00:00Z",
        delivery_mode="contract_only",
        expected_result_type="plan",
    )
    kwargs.update(overrides)
    return AgentAdapterRequest.of(**kwargs)


def test_schema_version_and_constants() -> None:
    check("schema version is 1", AI_AGENT_ADAPTER_SCHEMA_VERSION == 1)
    check("6 allowed agent names", len(ALLOWED_ADAPTER_AGENT_NAMES) == 6)
    check("manual_clipboard is an allowed agent name", "manual_clipboard" in ALLOWED_ADAPTER_AGENT_NAMES)
    check("hermes_video_studio is an allowed agent name", "hermes_video_studio" in ALLOWED_ADAPTER_AGENT_NAMES)
    check("10 allowed runtime types", len(ALLOWED_ADAPTER_RUNTIME_TYPES) == 10)
    check("11 allowed task types", len(ALLOWED_ADAPTER_TASK_TYPES) == 11)
    check("3 allowed delivery modes", len(ALLOWED_DELIVERY_MODES) == 3)
    check("11 allowed result types", len(ALLOWED_RESULT_TYPES) == 11)
    check("7 allowed statuses", len(ALLOWED_ADAPTER_STATUSES) == 7)
    check("14 allowed error kinds", len(ALLOWED_ADAPTER_ERROR_KINDS) == 14)
    check("9 allowed event types", len(ALLOWED_ADAPTER_EVENT_TYPES) == 9)


def test_capability_model() -> None:
    capability = _make_capability()
    check(
        "capability to_dict key order",
        list(capability.to_dict().keys())
        == [
            "capability_id",
            "agent_name",
            "runtime_type",
            "task_types",
            "supports_prompt_delivery",
            "supports_result_capture",
            "supports_status_check",
            "supports_manual_fallback",
            "metadata",
        ],
    )
    check("capability task_types serialized as list", capability.to_dict()["task_types"] == ["planning", "status_update"])
    check("capability metadata serialized as list of pairs", capability.to_dict()["metadata"] == [["note", "test"]])
    check(
        "capability frozen",
        _raises_frozen_error(lambda: setattr(capability, "agent_name", "codex")),
    )
    try:
        AgentAdapterCapability.of("cap-x", "not-an-agent", "chatgpt_app", task_types=())
        check("invalid agent_name rejected", False)
    except ValueError:
        check("invalid agent_name rejected", True)
    try:
        AgentAdapterCapability.of("cap-x", "chatgpt", "not-a-runtime", task_types=())
        check("invalid runtime_type rejected", False)
    except ValueError:
        check("invalid runtime_type rejected", True)
    try:
        AgentAdapterCapability.of("cap-x", "chatgpt", "chatgpt_app", task_types=("not-a-task",))
        check("invalid task_type rejected", False)
    except ValueError:
        check("invalid task_type rejected", True)


def _raises_frozen_error(fn) -> bool:
    try:
        fn()
        return False
    except dataclasses.FrozenInstanceError:
        return True


def test_request_model() -> None:
    request = _make_request()
    check(
        "request to_dict key order",
        list(request.to_dict().keys())
        == [
            "request_id",
            "session_id",
            "task_id",
            "agent_name",
            "runtime_id",
            "runtime_type",
            "task_type",
            "prompt_text",
            "input_summary",
            "created_at",
            "delivery_mode",
            "expected_result_type",
            "metadata",
        ],
    )
    check("request frozen", _raises_frozen_error(lambda: setattr(request, "task_type", "review")))
    try:
        _make_request(agent_name="not-an-agent")
        check("invalid agent_name rejected", False)
    except ValueError:
        check("invalid agent_name rejected", True)
    try:
        _make_request(delivery_mode="not-a-mode")
        check("invalid delivery_mode rejected", False)
    except ValueError:
        check("invalid delivery_mode rejected", True)
    try:
        _make_request(expected_result_type="not-a-result-type")
        check("invalid expected_result_type rejected", False)
    except ValueError:
        check("invalid expected_result_type rejected", True)
    try:
        _make_request(prompt_text="Go read https://example.com for context.")
        check("unsafe prompt with URL rejected", False)
    except ValueError:
        check("unsafe prompt with URL rejected", True)
    try:
        _make_request(prompt_text="Go read http://example.com for context.")
        check("unsafe prompt with http URL rejected", False)
    except ValueError:
        check("unsafe prompt with http URL rejected", True)
    safe_request = _make_request(prompt_text="Plan the next stage without any links.")
    check("safe prompt accepted", safe_request.prompt_text == "Plan the next stage without any links.")


def test_result_model() -> None:
    result = AgentAdapterResult.of(
        "result-001",
        "req-001",
        "session-001",
        "chatgpt",
        "chatgpt-app",
        "result_ready",
        "plan",
        "Plan drafted",
        "2026-07-06T10:05:00Z",
        output_text="1. Do X\n2. Do Y",
        next_action="attach to session",
    )
    check(
        "result to_dict key order",
        list(result.to_dict().keys())
        == [
            "result_id",
            "request_id",
            "session_id",
            "agent_name",
            "runtime_id",
            "status",
            "result_type",
            "result_summary",
            "output_text",
            "output_path",
            "created_at",
            "next_action",
            "metadata",
        ],
    )
    check("result output_path defaults to None", result.output_path is None)
    check("result frozen", _raises_frozen_error(lambda: setattr(result, "status", "failed")))
    try:
        AgentAdapterResult.of(
            "r", "req", "s", "chatgpt", "rt", "not-a-status", "plan", "x", "2026-01-01T00:00:00Z"
        )
        check("invalid status rejected", False)
    except ValueError:
        check("invalid status rejected", True)
    try:
        AgentAdapterResult.of(
            "r", "req", "s", "chatgpt", "rt", "result_ready", "not-a-result-type", "x", "2026-01-01T00:00:00Z"
        )
        check("invalid result_type rejected", False)
    except ValueError:
        check("invalid result_type rejected", True)


def test_error_model() -> None:
    error = AgentAdapterError.of(
        "contract_violation", "bad request", "validate_request", request_id="req-001"
    )
    check(
        "error to_dict key order",
        list(error.to_dict().keys())
        == [
            "ok",
            "schema_version",
            "error_kind",
            "error_detail",
            "failed_step",
            "request_id",
            "metadata",
        ],
    )
    check("error ok defaults to False", error.ok is False)
    check("error schema_version defaults", error.schema_version == AI_AGENT_ADAPTER_SCHEMA_VERSION)
    check("error frozen", _raises_frozen_error(lambda: setattr(error, "ok", True)))
    try:
        AgentAdapterError.of("not-a-kind", "detail", "step")
        check("invalid error_kind rejected", False)
    except ValueError:
        check("invalid error_kind rejected", True)


def test_event_model() -> None:
    event = AgentAdapterSimulationEvent.of(
        "evt-1",
        "req-001",
        "session-001",
        "chatgpt",
        "request_created",
        "accepted",
        "Request created",
        "2026-07-06T10:00:00Z",
    )
    check(
        "event to_dict key order",
        list(event.to_dict().keys())
        == [
            "event_id",
            "request_id",
            "session_id",
            "agent_name",
            "event_type",
            "status_after",
            "message",
            "created_at",
            "metadata",
        ],
    )
    check("event frozen", _raises_frozen_error(lambda: setattr(event, "event_type", "blocked")))
    try:
        AgentAdapterSimulationEvent.of(
            "evt-2", "req", "s", "chatgpt", "not-an-event", "accepted", "x", "2026-01-01T00:00:00Z"
        )
        check("invalid event_type rejected", False)
    except ValueError:
        check("invalid event_type rejected", True)
    try:
        AgentAdapterSimulationEvent.of(
            "evt-3", "req", "s", "chatgpt", "request_created", "not-a-status", "x", "2026-01-01T00:00:00Z"
        )
        check("invalid status_after rejected", False)
    except ValueError:
        check("invalid status_after rejected", True)


def main() -> int:
    test_schema_version_and_constants()
    test_capability_model()
    test_request_model()
    test_result_model()
    test_error_model()
    test_event_model()
    print(f"\n RESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
