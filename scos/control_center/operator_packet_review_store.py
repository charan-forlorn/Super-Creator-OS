"""SCOS Stage 5.5 local operator packet review JSONL store.

Append-only deterministic JSONL persistence for operator packet decisions and
review results. No SQLite, no file locks, no background workers, no hidden
paths, and no automatic reads/writes to default locations.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

try:
    from .operator_packet_review_models import (
        OPERATOR_PACKET_REVIEW_SCHEMA_VERSION,
        ManualHandoffInstruction,
        ManualHandoffPackage,
        OperatorPacketDecision,
        OperatorPacketReviewResult,
        PacketReviewCheck,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from operator_packet_review_models import (
        OPERATOR_PACKET_REVIEW_SCHEMA_VERSION,
        ManualHandoffInstruction,
        ManualHandoffPackage,
        OperatorPacketDecision,
        OperatorPacketReviewResult,
        PacketReviewCheck,
    )

OPERATOR_PACKET_REVIEW_STORE_SCHEMA_VERSION = 1

DEFAULT_OPERATOR_PACKET_DECISIONS_PATH = (
    "scos/work/control_center/operator_packet_decisions.jsonl"
)
DEFAULT_OPERATOR_PACKET_REVIEW_RESULTS_PATH = (
    "scos/work/control_center/operator_packet_review_results.jsonl"
)
DEFAULT_MANUAL_HANDOFFS_DIR = "scos/work/control_center/manual_handoffs/"

_URL_PREFIXES = ("http://", "https://")
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")


def _ensure_local_path(path: Any, label: str) -> Path:
    if isinstance(path, str):
        text = path.strip()
        if text.lower().startswith(_URL_PREFIXES) or _SCHEME_RE.match(text):
            raise ValueError(f"URL_PATH_REJECTED: {label} must be a local path")
        return Path(text)
    if isinstance(path, Path):
        return path
    raise ValueError(f"INVALID_PATH: {label} must be a str or pathlib.Path")


def _jsonl_line(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _append_jsonl(path: Any, label: str, payload: dict) -> None:
    target = _ensure_local_path(path, label)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(_jsonl_line(payload) + "\n")


def _read_jsonl(path: Any, label: str, error_code: str) -> tuple[dict, ...]:
    target = _ensure_local_path(path, label)
    if not target.is_file():
        return ()
    objects: list[dict] = []
    for line_number, line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            raise ValueError(
                f"{error_code}: line {line_number} is not valid JSON"
            ) from None
        if not isinstance(payload, dict):
            raise ValueError(f"{error_code}: line {line_number} is not a JSON object")
        objects.append(payload)
    return tuple(objects)


def _check_from_dict(payload: dict) -> PacketReviewCheck:
    return PacketReviewCheck.of(
        payload.get("check_name", ""),
        payload.get("status", ""),
        payload.get("severity", ""),
        packet_id=payload.get("packet_id"),
        error_kind=payload.get("error_kind"),
        error_detail=payload.get("error_detail"),
        metadata=payload.get("metadata"),
    )


def _instruction_from_dict(payload: dict) -> ManualHandoffInstruction:
    return ManualHandoffInstruction.of(
        instruction_id=payload.get("instruction_id", ""),
        step_order=int(payload.get("step_order", 0)),
        title=payload.get("title", ""),
        detail=payload.get("detail", ""),
        required=bool(payload.get("required", True)),
        metadata=payload.get("metadata"),
    )


def _manual_handoff_from_dict(payload: dict) -> ManualHandoffPackage:
    return ManualHandoffPackage(
        ok=bool(payload.get("ok", True)),
        schema_version=int(payload.get("schema_version", OPERATOR_PACKET_REVIEW_SCHEMA_VERSION)),
        handoff_id=payload.get("handoff_id", ""),
        source_packet_id=payload.get("source_packet_id", ""),
        source_result_packet_id=payload.get("source_result_packet_id"),
        routing_decision_id=payload.get("routing_decision_id"),
        target_agent=payload.get("target_agent", ""),
        target_runtime_id=payload.get("target_runtime_id", ""),
        handoff_mode=payload.get("handoff_mode", ""),
        created_at=payload.get("created_at", ""),
        prompt_path=payload.get("prompt_path", ""),
        context_summary_path=payload.get("context_summary_path", ""),
        instruction_path=payload.get("instruction_path", ""),
        manifest_path=payload.get("manifest_path", ""),
        instructions=tuple(
            _instruction_from_dict(item) for item in payload.get("instructions", ())
        ),
        metadata=payload.get("metadata"),
    )


def _decision_from_dict(payload: dict) -> OperatorPacketDecision:
    return OperatorPacketDecision(
        decision_id=payload.get("decision_id", ""),
        packet_id=payload.get("packet_id", ""),
        routing_decision_id=payload.get("routing_decision_id"),
        decision=payload.get("decision", ""),
        decided_by=payload.get("decided_by", ""),
        decided_at=payload.get("decided_at", ""),
        reason=payload.get("reason", ""),
        target_agent=payload.get("target_agent"),
        target_runtime_id=payload.get("target_runtime_id"),
        requires_manual_handoff=bool(payload.get("requires_manual_handoff", False)),
        checks=tuple(_check_from_dict(item) for item in payload.get("checks", ())),
        metadata=payload.get("metadata"),
    )


def _review_result_from_dict(payload: dict) -> OperatorPacketReviewResult:
    handoff_payload = payload.get("handoff_package")
    return OperatorPacketReviewResult(
        ok=bool(payload.get("ok", True)),
        schema_version=int(payload.get("schema_version", OPERATOR_PACKET_REVIEW_SCHEMA_VERSION)),
        review_id=payload.get("review_id", ""),
        packet_id=payload.get("packet_id", ""),
        result_packet_id=payload.get("result_packet_id"),
        routing_decision_id=payload.get("routing_decision_id"),
        reviewed_at=payload.get("reviewed_at", ""),
        decision=_decision_from_dict(payload.get("decision", {})),
        handoff_package=(
            _manual_handoff_from_dict(handoff_payload)
            if isinstance(handoff_payload, dict)
            else None
        ),
        checks=tuple(_check_from_dict(item) for item in payload.get("checks", ())),
        output_path=payload.get("output_path"),
        metadata=payload.get("metadata"),
    )


def append_operator_packet_decision(path, decision) -> None:
    if not isinstance(decision, OperatorPacketDecision):
        raise ValueError(
            "NOT_AN_OPERATOR_PACKET_DECISION: only OperatorPacketDecision instances may be stored"
        )
    _append_jsonl(path, "path", decision.to_dict())


def append_operator_packet_review_result(path, result) -> None:
    if not isinstance(result, OperatorPacketReviewResult):
        raise ValueError(
            "NOT_AN_OPERATOR_PACKET_REVIEW_RESULT: only OperatorPacketReviewResult instances may be stored"
        )
    _append_jsonl(path, "path", result.to_dict())


def load_operator_packet_decisions(path) -> tuple[OperatorPacketDecision, ...]:
    payloads = _read_jsonl(path, "path", "INVALID_OPERATOR_PACKET_DECISION_LINE")
    return tuple(_decision_from_dict(payload) for payload in payloads)


def load_operator_packet_review_results(path) -> tuple[OperatorPacketReviewResult, ...]:
    payloads = _read_jsonl(path, "path", "INVALID_OPERATOR_PACKET_REVIEW_RESULT_LINE")
    return tuple(_review_result_from_dict(payload) for payload in payloads)
