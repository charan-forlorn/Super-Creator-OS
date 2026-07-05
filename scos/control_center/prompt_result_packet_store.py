"""SCOS Stage 5.4 local prompt/result packet store (JSONL, append-only).

Prompt packets, result packets, and routing decisions are appended one JSON
object per line to local JSONL files (UTF-8, LF). The store is strictly
append-only: this module never deletes, truncates, or rewrites existing
lines.

Unlike ``work_session_store.py`` (which replays "latest snapshot wins" per
``session_id`` because a session mutates over its lifecycle), packets and
routing decisions are immutable, single-write records — a follow-up prompt
always gets its own distinct ``packet_id``. So every loader here is a simple
"one line -> one dataclass, in append order" replay with no de-dup pass.

No SQLite, no database, no server, no file locks, no background workers.

Local-first, deterministic, stdlib-only. No clock, no random, no network.
"""

from __future__ import annotations

from typing import Any

try:
    from .command_queue import _append_jsonl_line, _read_jsonl_objects
    from .prompt_result_packet_models import (
        PacketContextReference,
        PacketRoutingDecision,
        PromptPacket,
        ResultArtifactReference,
        ResultPacket,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from command_queue import _append_jsonl_line, _read_jsonl_objects
    from prompt_result_packet_models import (
        PacketContextReference,
        PacketRoutingDecision,
        PromptPacket,
        ResultArtifactReference,
        ResultPacket,
    )

PROMPT_RESULT_PACKET_STORE_SCHEMA_VERSION = 1

# Document-only default paths: no function in this module reads or writes
# to these automatically. Callers pass an explicit `path` to every function.
DEFAULT_PROMPT_PACKETS_PATH = "scos/work/control_center/prompt_packets.jsonl"
DEFAULT_RESULT_PACKETS_PATH = "scos/work/control_center/result_packets.jsonl"
DEFAULT_PACKET_ROUTING_DECISIONS_PATH = (
    "scos/work/control_center/packet_routing_decisions.jsonl"
)


def _pairs_from_lists(value: Any) -> tuple[tuple[str, str], ...]:
    return tuple((str(pair[0]), str(pair[1])) for pair in (value or ()))


def _context_ref_from_dict(payload: dict) -> PacketContextReference:
    return PacketContextReference.of(
        payload.get("ref_id", ""),
        payload.get("ref_type", ""),
        payload.get("title", ""),
        payload.get("summary", ""),
        path=payload.get("path"),
        required=bool(payload.get("required", False)),
        sha256=payload.get("sha256"),
        metadata=_pairs_from_lists(payload.get("metadata")),
    )


def _artifact_from_dict(payload: dict) -> ResultArtifactReference:
    return ResultArtifactReference.of(
        payload.get("artifact_id", ""),
        payload.get("artifact_type", ""),
        payload.get("summary", ""),
        path=payload.get("path"),
        sha256=payload.get("sha256"),
        required=bool(payload.get("required", False)),
        metadata=_pairs_from_lists(payload.get("metadata")),
    )


def _prompt_packet_from_dict(payload: dict) -> PromptPacket:
    return PromptPacket.of(
        payload.get("packet_id", ""),
        payload.get("packet_type", ""),
        payload.get("session_id", ""),
        payload.get("task_id", ""),
        payload.get("source_agent", ""),
        payload.get("target_agent", ""),
        payload.get("target_runtime_id", ""),
        payload.get("title", ""),
        payload.get("objective", ""),
        payload.get("prompt_body", ""),
        payload.get("created_at", ""),
        payload.get("status", "drafted"),
        ok=bool(payload.get("ok", True)),
        schema_version=int(payload.get("schema_version", 1)),
        context_refs=tuple(
            _context_ref_from_dict(ref) for ref in payload.get("context_refs", ())
        ),
        constraints=tuple(payload.get("constraints", ())),
        expected_result_format=payload.get(
            "expected_result_format", "structured_report"
        ),
        expected_artifacts=tuple(payload.get("expected_artifacts", ())),
        metadata=_pairs_from_lists(payload.get("metadata")),
    )


def _result_packet_from_dict(payload: dict) -> ResultPacket:
    return ResultPacket.of(
        payload.get("result_packet_id", ""),
        payload.get("prompt_packet_id", ""),
        payload.get("session_id", ""),
        payload.get("task_id", ""),
        payload.get("source_agent", ""),
        payload.get("target_agent", ""),
        payload.get("result_type", ""),
        payload.get("verdict", ""),
        payload.get("summary", ""),
        payload.get("created_at", ""),
        payload.get("status", "received"),
        ok=bool(payload.get("ok", True)),
        schema_version=int(payload.get("schema_version", 1)),
        artifacts=tuple(
            _artifact_from_dict(artifact) for artifact in payload.get("artifacts", ())
        ),
        blockers=tuple(payload.get("blockers", ())),
        next_action=payload.get("next_action"),
        recommended_next_agent=payload.get("recommended_next_agent"),
        metadata=_pairs_from_lists(payload.get("metadata")),
    )


def _routing_decision_from_dict(payload: dict) -> PacketRoutingDecision:
    return PacketRoutingDecision.of(
        payload.get("decision_id", ""),
        payload.get("source_result_packet_id", ""),
        payload.get("next_agent", ""),
        payload.get("next_packet_type", ""),
        payload.get("reason", ""),
        priority=payload.get("priority", "normal"),
        requires_operator_approval=bool(
            payload.get("requires_operator_approval", True)
        ),
        metadata=_pairs_from_lists(payload.get("metadata")),
    )


def append_prompt_packet(*, path, packet: PromptPacket) -> str:
    """Append one prompt packet; return the written line's SHA-256 hex."""
    if not isinstance(packet, PromptPacket):
        raise ValueError(
            "NOT_A_PROMPT_PACKET: only PromptPacket instances may be stored"
        )
    return _append_jsonl_line(path, "path", packet.to_dict())


def append_result_packet(*, path, packet: ResultPacket) -> str:
    """Append one result packet; return the written line's SHA-256 hex."""
    if not isinstance(packet, ResultPacket):
        raise ValueError(
            "NOT_A_RESULT_PACKET: only ResultPacket instances may be stored"
        )
    return _append_jsonl_line(path, "path", packet.to_dict())


def append_packet_routing_decision(*, path, decision: PacketRoutingDecision) -> str:
    """Append one routing decision; return the written line's SHA-256 hex."""
    if not isinstance(decision, PacketRoutingDecision):
        raise ValueError(
            "NOT_A_ROUTING_DECISION: only PacketRoutingDecision instances may be stored"
        )
    return _append_jsonl_line(path, "path", decision.to_dict())


def load_prompt_packets(*, path) -> tuple[PromptPacket, ...]:
    """Replay every stored line into one PromptPacket each, in append order."""
    payloads = _read_jsonl_objects(path, "path", "INVALID_PROMPT_PACKET_LINE")
    return tuple(_prompt_packet_from_dict(payload) for payload in payloads)


def load_result_packets(*, path) -> tuple[ResultPacket, ...]:
    """Replay every stored line into one ResultPacket each, in append order."""
    payloads = _read_jsonl_objects(path, "path", "INVALID_RESULT_PACKET_LINE")
    return tuple(_result_packet_from_dict(payload) for payload in payloads)


def load_packet_routing_decisions(*, path) -> tuple[PacketRoutingDecision, ...]:
    """Replay every stored line into one PacketRoutingDecision each, in append order."""
    payloads = _read_jsonl_objects(path, "path", "INVALID_ROUTING_DECISION_LINE")
    return tuple(_routing_decision_from_dict(payload) for payload in payloads)
