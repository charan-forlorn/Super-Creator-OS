"""SCOS Stage 5.3 AI agent adapter simulator.

Deterministic, local-only simulation of one adapter request's lifecycle:
validate -> select adapter -> prepare prompt -> simulate send -> simulate
result capture, emitting one ``AgentAdapterSimulationEvent`` per step. This
module never calls a real AI, never touches the network, never reads or
writes a real clipboard, and never inspects installed applications — every
event is built purely from the caller-supplied request and registry.

Local-first, deterministic, stdlib-only. No clock, no random, no uuid,
no file writes (tests may pass a tempdir path as plain string data, but
this module never opens it).
"""

from __future__ import annotations

try:
    from .agent_adapter_models import (
        AgentAdapterError,
        AgentAdapterRequest,
        AgentAdapterResult,
        AgentAdapterSimulationEvent,
    )
    from .agent_adapter_registry import AgentAdapterRegistry
except ImportError:  # direct-module execution (tests insert the package dir)
    from agent_adapter_models import (
        AgentAdapterError,
        AgentAdapterRequest,
        AgentAdapterResult,
        AgentAdapterSimulationEvent,
    )
    from agent_adapter_registry import AgentAdapterRegistry

AGENT_ADAPTER_SIMULATOR_SCHEMA_VERSION = 1


def simulate_agent_adapter_request(
    *,
    registry: AgentAdapterRegistry,
    request: AgentAdapterRequest,
    created_at: str,
    simulated_output_text: str | None = None,
    simulated_output_path: str | None = None,
) -> AgentAdapterResult | AgentAdapterError:
    """Run the full request -> result simulation, returning only the final result.

    Validates the request, selects a compatible adapter (falling back to
    manual_clipboard), and drives prepare_prompt -> simulate_send ->
    capture_result. Returns the terminal ``AgentAdapterResult``, or an
    ``AgentAdapterError`` if validation or any step fails.
    """
    problems = registry.validate_request(request)
    if problems:
        return AgentAdapterError.of(
            "contract_violation",
            "; ".join(problems),
            "validate_request",
            request_id=request.request_id,
        )

    adapter = registry.find_adapter(
        request.agent_name, request.runtime_type, request.task_type
    ) or registry.recommend_adapter(request.task_type, request.agent_name)

    prepared = adapter.prepare_prompt(request)
    if isinstance(prepared, AgentAdapterError):
        return prepared

    sent = adapter.simulate_send(request, created_at=created_at)
    if isinstance(sent, AgentAdapterError):
        return sent

    return adapter.capture_result(
        request,
        output_text=simulated_output_text,
        output_path=simulated_output_path,
        created_at=created_at,
    )


def simulate_adapter_lifecycle(
    *,
    registry: AgentAdapterRegistry,
    request: AgentAdapterRequest,
    created_at: str,
    simulated_output_text: str | None = None,
    simulated_output_path: str | None = None,
) -> tuple[AgentAdapterSimulationEvent, ...] | AgentAdapterError:
    """Run the full lifecycle, returning every deterministic event step.

    Event sequence on success: request_created -> request_validated ->
    adapter_selected -> prompt_prepared -> (manual_clipboard_ready |
    simulated_sent) -> result_ready (or ``blocked`` if the captured result's
    status is ``failed``/``blocked``).

    Returns an ``AgentAdapterError`` (no events emitted) if validation fails
    before any step, or if a downstream adapter step returns an error.
    """
    events: list[AgentAdapterSimulationEvent] = []

    def _event_id(step: str) -> str:
        return f"{request.request_id}-evt-{len(events) + 1}-{step}"

    problems = registry.validate_request(request)
    if problems:
        return AgentAdapterError.of(
            "contract_violation",
            "; ".join(problems),
            "validate_request",
            request_id=request.request_id,
        )

    events.append(
        AgentAdapterSimulationEvent.of(
            _event_id("request_created"),
            request.request_id,
            request.session_id,
            request.agent_name,
            "request_created",
            "accepted",
            f"Adapter request {request.request_id} created for "
            f"{request.agent_name} ({request.task_type})",
            created_at,
        )
    )
    events.append(
        AgentAdapterSimulationEvent.of(
            _event_id("request_validated"),
            request.request_id,
            request.session_id,
            request.agent_name,
            "request_validated",
            "accepted",
            "Request passed registry validation",
            created_at,
        )
    )

    adapter = registry.find_adapter(
        request.agent_name, request.runtime_type, request.task_type
    ) or registry.recommend_adapter(request.task_type, request.agent_name)
    events.append(
        AgentAdapterSimulationEvent.of(
            _event_id("adapter_selected"),
            request.request_id,
            request.session_id,
            request.agent_name,
            "adapter_selected",
            "accepted",
            f"Selected adapter {adapter.adapter_id()} "
            f"({adapter.agent_name()}/{adapter.runtime_type()})",
            created_at,
        )
    )

    prepared = adapter.prepare_prompt(request)
    if isinstance(prepared, AgentAdapterError):
        return prepared
    events.append(
        AgentAdapterSimulationEvent.of(
            _event_id("prompt_prepared"),
            request.request_id,
            request.session_id,
            request.agent_name,
            "prompt_prepared",
            prepared.status,
            prepared.result_summary,
            created_at,
        )
    )

    sent = adapter.simulate_send(request, created_at=created_at)
    if isinstance(sent, AgentAdapterError):
        return sent
    if sent.status == "waiting_for_operator":
        events.append(
            AgentAdapterSimulationEvent.of(
                _event_id("manual_clipboard_ready"),
                request.request_id,
                request.session_id,
                request.agent_name,
                "manual_clipboard_ready",
                sent.status,
                sent.result_summary,
                created_at,
            )
        )
    else:
        events.append(
            AgentAdapterSimulationEvent.of(
                _event_id("simulated_sent"),
                request.request_id,
                request.session_id,
                request.agent_name,
                "simulated_sent",
                sent.status,
                sent.result_summary,
                created_at,
            )
        )

    captured = adapter.capture_result(
        request,
        output_text=simulated_output_text,
        output_path=simulated_output_path,
        created_at=created_at,
    )
    if isinstance(captured, AgentAdapterError):
        return captured
    events.append(
        AgentAdapterSimulationEvent.of(
            _event_id("result_simulated"),
            request.request_id,
            request.session_id,
            request.agent_name,
            "result_simulated",
            captured.status,
            captured.result_summary,
            created_at,
        )
    )

    if captured.status in ("failed", "blocked"):
        events.append(
            AgentAdapterSimulationEvent.of(
                _event_id("blocked"),
                request.request_id,
                request.session_id,
                request.agent_name,
                "blocked",
                captured.status,
                "Simulated result capture did not reach result_ready",
                created_at,
            )
        )
    else:
        events.append(
            AgentAdapterSimulationEvent.of(
                _event_id("result_ready"),
                request.request_id,
                request.session_id,
                request.agent_name,
                "result_ready",
                captured.status,
                captured.result_summary,
                created_at,
            )
        )

    return tuple(events)
