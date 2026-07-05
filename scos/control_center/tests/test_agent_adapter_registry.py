"""test_agent_adapter_registry.py - SCOS Stage 5.3 agent adapter registry suite.

Plain executable script (no pytest). Covers deterministic ordering,
find_adapter/recommend_adapter routing, manual_clipboard fallback, and
validate_request for the default registry.

Run: python scos/control_center/tests/test_agent_adapter_registry.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
sys.path.insert(0, str(_PACKAGE))

from agent_adapter_models import AgentAdapterRequest  # noqa: E402
from agent_adapter_registry import (  # noqa: E402
    AGENT_ADAPTER_REGISTRY_SCHEMA_VERSION,
    create_default_agent_adapter_registry,
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


def test_schema_version() -> None:
    check("registry schema version is 1", AGENT_ADAPTER_REGISTRY_SCHEMA_VERSION == 1)


def test_list_adapters_and_capabilities() -> None:
    registry = create_default_agent_adapter_registry()
    adapters = registry.list_adapters()
    check("registry lists 5 adapters", len(adapters) == 5)
    check(
        "registry adapter order is chatgpt, claude_code, codex, hermes, manual_clipboard",
        [a.agent_name() for a in adapters]
        == ["chatgpt", "claude_code", "codex", "hermes", "manual_clipboard"],
    )
    check("list_adapters is deterministic across calls", registry.list_adapters() == adapters)

    capabilities = registry.list_capabilities()
    check("registry lists capabilities from every adapter", len(capabilities) == 8)
    check(
        "manual_clipboard capability present",
        any(c.agent_name == "manual_clipboard" for c in capabilities),
    )


def test_find_adapter() -> None:
    registry = create_default_agent_adapter_registry()
    found = registry.find_adapter("chatgpt", "chatgpt_app", "planning")
    check("find_adapter finds chatgpt for planning", found is not None and found.agent_name() == "chatgpt")

    missing = registry.find_adapter("chatgpt", "chatgpt_app", "implementation")
    check("find_adapter returns None for unsupported task_type", missing is None)

    missing_runtime = registry.find_adapter("chatgpt", "codex_cli", "planning")
    check("find_adapter returns None for mismatched runtime_type", missing_runtime is None)


def test_recommend_adapter_routing() -> None:
    registry = create_default_agent_adapter_registry()
    routing = {
        "planning": "chatgpt",
        "implementation": "claude_code",
        "review": "codex",
        "audit": "hermes",
        "status_update": "chatgpt",
        "git_review": "codex",
        "manual_handoff": "manual_clipboard",
    }
    for task_type, expected_agent in routing.items():
        adapter = registry.recommend_adapter(task_type)
        check(
            f"recommend_adapter routes {task_type} to {expected_agent}",
            adapter.agent_name() == expected_agent,
        )

    prompt_build_default = registry.recommend_adapter("prompt_build")
    check("recommend_adapter default prompt_build routes to chatgpt", prompt_build_default.agent_name() == "chatgpt")

    prompt_build_alt = registry.recommend_adapter("prompt_build", preferred_agent="claude_code")
    check(
        "recommend_adapter honors preferred_agent for prompt_build",
        prompt_build_alt.agent_name() == "claude_code",
    )

    release_gate_default = registry.recommend_adapter("release_gate")
    check("recommend_adapter default release_gate routes to codex", release_gate_default.agent_name() == "codex")

    release_gate_alt = registry.recommend_adapter("release_gate", preferred_agent="claude_code")
    check(
        "recommend_adapter honors preferred_agent for release_gate",
        release_gate_alt.agent_name() == "claude_code",
    )

    unroutable_preference = registry.recommend_adapter("planning", preferred_agent="hermes")
    check(
        "recommend_adapter ignores an invalid preferred_agent for the task",
        unroutable_preference.agent_name() == "chatgpt",
    )


def test_manual_fallback_and_validation() -> None:
    registry = create_default_agent_adapter_registry()
    manual_only_task = registry.recommend_adapter("manual_handoff")
    check("manual_handoff always routes to manual_clipboard", manual_only_task.agent_name() == "manual_clipboard")

    good_request = _request("chatgpt", "chatgpt_app", "planning")
    check("validate_request returns empty tuple for a valid request", registry.validate_request(good_request) == ())

    bad_request = _request("chatgpt", "chatgpt_app", "implementation")
    problems = registry.validate_request(bad_request)
    check("validate_request returns problems for unsupported task_type", len(problems) >= 1)


def main() -> int:
    test_schema_version()
    test_list_adapters_and_capabilities()
    test_find_adapter()
    test_recommend_adapter_routing()
    test_manual_fallback_and_validation()
    print(f"\n RESULT: {_PASS} passed, {_FAIL} failed")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
