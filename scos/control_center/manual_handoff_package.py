"""SCOS Stage 5.5 deterministic manual handoff package generation.

Creates local files an operator can manually use with the target AI/runtime.
This module writes only the generated package files under the caller-supplied
output directory. It never touches clipboard state, opens apps, launches
processes, calls a network API, or mutates any packet store.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

try:
    from .operator_packet_review_models import (
        ALLOWED_HANDOFF_MODES,
        ALLOWED_REVIEW_AGENT_NAMES,
        OPERATOR_PACKET_REVIEW_SCHEMA_VERSION,
        ManualHandoffInstruction,
        ManualHandoffPackage,
        OperatorPacketReviewError,
        derive_manual_handoff_id,
    )
except ImportError:  # direct-module execution (tests insert the package dir)
    from operator_packet_review_models import (
        ALLOWED_HANDOFF_MODES,
        ALLOWED_REVIEW_AGENT_NAMES,
        OPERATOR_PACKET_REVIEW_SCHEMA_VERSION,
        ManualHandoffInstruction,
        ManualHandoffPackage,
        OperatorPacketReviewError,
        derive_manual_handoff_id,
    )

MANUAL_HANDOFF_PACKAGE_SCHEMA_VERSION = 1

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


def _fail(
    error_kind: str, error_detail: str, failed_step: str, *, checks=(), metadata=None
) -> OperatorPacketReviewError:
    return OperatorPacketReviewError.of(
        error_kind,
        error_detail,
        failed_step,
        checks=checks,
        metadata=metadata,
    )


def _packet_id(packet: Any) -> str | None:
    return getattr(packet, "packet_id", None) or getattr(packet, "prompt_packet_id", None)


def _result_packet_id(packet: Any) -> str | None:
    return getattr(packet, "result_packet_id", None)


def _routing_decision_id(routing_decision: Any) -> str | None:
    if routing_decision is None:
        return None
    return getattr(routing_decision, "decision_id", None)


def _packet_title(packet: Any) -> str:
    return str(getattr(packet, "title", "Result packet handoff"))


def _packet_objective(packet: Any) -> str:
    return str(getattr(packet, "objective", getattr(packet, "summary", "")))


def _packet_prompt_body(packet: Any) -> str:
    if hasattr(packet, "prompt_body"):
        return str(packet.prompt_body)
    return (
        "Review the source result packet and continue the requested manual "
        "handoff using the summary and artifacts below.\n\n"
        f"Result summary: {getattr(packet, 'summary', '')}"
    )


def _context_refs(packet: Any) -> tuple[Any, ...]:
    return tuple(getattr(packet, "context_refs", ()) or ())


def _artifact_refs(packet: Any) -> tuple[Any, ...]:
    return tuple(getattr(packet, "artifacts", ()) or ())


def _routing_reason(routing_decision: Any) -> str | None:
    if routing_decision is None:
        return None
    return getattr(routing_decision, "reason", None)


def _string_list(value: Any) -> tuple[str, ...]:
    return tuple(str(item) for item in (value or ()))


def _write_lf(path: Path, text: str) -> None:
    path.write_text(text.replace("\r\n", "\n").replace("\r", "\n"), encoding="utf-8")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_instructions(handoff_id: str) -> tuple[ManualHandoffInstruction, ...]:
    details = (
        ("Open the target AI/runtime manually.", "Use the named runtime outside SCOS."),
        ("Paste or provide the prompt manually.", "Use prompt.md as the source text."),
        ("Wait for the AI result.", "Do not rely on SCOS to poll or capture it."),
        (
            "Save the result back into SCOS as a ResultPacket.",
            "Use the Stage 5.4 packet contract for the returned result.",
        ),
        (
            "Do not let the AI commit/push without operator approval.",
            "Any repo mutation still requires explicit operator approval.",
        ),
    )
    instructions: list[ManualHandoffInstruction] = []
    for index, (title, detail) in enumerate(details, start=1):
        digest = hashlib.sha256(f"{handoff_id}|{index}|{title}".encode("utf-8")).hexdigest()[:16]
        instructions.append(
            ManualHandoffInstruction.of(
                instruction_id=f"ophi-{digest}",
                step_order=index,
                title=title,
                detail=detail,
                required=True,
            )
        )
    return tuple(instructions)


def _prompt_markdown(packet: Any, target_agent: str) -> str:
    constraints = _string_list(getattr(packet, "constraints", ()))
    expected_artifacts = _string_list(getattr(packet, "expected_artifacts", ()))
    return "\n".join(
        (
            f"# Manual Handoff Prompt for {target_agent}",
            "",
            f"## Packet Title",
            _packet_title(packet),
            "",
            "## Objective",
            _packet_objective(packet),
            "",
            "## Prompt Body",
            _packet_prompt_body(packet),
            "",
            "## Expected Result Format",
            str(getattr(packet, "expected_result_format", "structured_result_packet")),
            "",
            "## Expected Artifacts",
            *(f"- {artifact}" for artifact in expected_artifacts),
            *(() if expected_artifacts else ("- None specified",)),
            "",
            "## Constraints",
            *(f"- {constraint}" for constraint in constraints),
            *(() if constraints else ("- None specified",)),
            "",
        )
    )


def _context_markdown(packet: Any, routing_decision: Any) -> str:
    packet_id = _packet_id(packet) or ""
    result_packet_id = _result_packet_id(packet)
    lines = [
        "# Manual Handoff Context Summary",
        "",
        f"- Source packet id: {packet_id}",
        f"- Source result packet id: {result_packet_id or 'None'}",
        f"- Routing reason: {_routing_reason(routing_decision) or 'None'}",
        "",
        "## Context References",
    ]
    refs = _context_refs(packet)
    if refs:
        for ref in refs:
            lines.append(
                f"- {getattr(ref, 'ref_id', '')}: {getattr(ref, 'title', '')} "
                f"({getattr(ref, 'ref_type', '')}) - {getattr(ref, 'summary', '')}"
            )
    else:
        lines.append("- None")
    lines.extend(["", "## Artifact References"])
    artifacts = _artifact_refs(packet)
    if artifacts:
        for artifact in artifacts:
            lines.append(
                f"- {getattr(artifact, 'artifact_id', '')}: "
                f"{getattr(artifact, 'artifact_type', '')} - "
                f"{getattr(artifact, 'summary', '')}"
            )
    else:
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)


def _instructions_markdown(instructions: tuple[ManualHandoffInstruction, ...]) -> str:
    lines = ["# Manual Handoff Instructions", ""]
    for instruction in instructions:
        lines.append(f"{instruction.step_order}. {instruction.title}")
        lines.append(f"   {instruction.detail}")
    lines.append("")
    return "\n".join(lines)


def _manifest_payload(
    *,
    handoff_id: str,
    source_packet_id: str,
    source_result_packet_id: str | None,
    routing_decision_id: str | None,
    target_agent: str,
    target_runtime_id: str,
    handoff_mode: str,
    created_at: str,
    files: tuple[Path, ...],
) -> dict[str, Any]:
    return {
        "created_at": created_at,
        "files": [
            {"path": path.name, "sha256": _sha256_file(path)}
            for path in sorted(files, key=lambda item: item.name)
        ],
        "handoff_id": handoff_id,
        "handoff_mode": handoff_mode,
        "routing_decision_id": routing_decision_id,
        "schema_version": OPERATOR_PACKET_REVIEW_SCHEMA_VERSION,
        "source_packet_id": source_packet_id,
        "source_result_packet_id": source_result_packet_id,
        "target_agent": target_agent,
        "target_runtime_id": target_runtime_id,
    }


def create_manual_handoff_package(
    *,
    packet,
    routing_decision=None,
    target_agent: str,
    target_runtime_id: str,
    output_dir,
    created_at: str,
    handoff_mode: str = "manual_clipboard",
    metadata=None,
) -> ManualHandoffPackage | OperatorPacketReviewError:
    if target_agent not in ALLOWED_REVIEW_AGENT_NAMES:
        return _fail(
            "unsupported_agent",
            f"target_agent={target_agent!r} is not recognized",
            "target_agent",
        )
    if handoff_mode not in ALLOWED_HANDOFF_MODES:
        return _fail(
            "contract_violation",
            f"handoff_mode={handoff_mode!r} is not recognized",
            "handoff_mode",
        )
    if not str(target_runtime_id).strip():
        return _fail(
            "missing_required_field",
            "target_runtime_id must not be empty",
            "target_runtime_id",
        )
    if not str(created_at).strip():
        return _fail(
            "missing_required_field",
            "created_at must be caller-supplied",
            "created_at",
        )

    source_packet_id = _packet_id(packet)
    if not source_packet_id:
        return _fail(
            "invalid_packet",
            "packet must expose packet_id or prompt_packet_id",
            "packet",
        )
    source_result_packet_id = _result_packet_id(packet)
    routing_decision_id = _routing_decision_id(routing_decision)
    try:
        base_dir = _ensure_local_path(output_dir, "output_dir")
    except ValueError as exc:
        return _fail("unsafe_path", str(exc), "output_dir")

    handoff_id = derive_manual_handoff_id(
        source_packet_id=source_packet_id,
        source_result_packet_id=source_result_packet_id,
        routing_decision_id=routing_decision_id,
        target_agent=target_agent,
        target_runtime_id=target_runtime_id,
        handoff_mode=handoff_mode,
        created_at=created_at,
    )
    try:
        base_resolved = base_dir.resolve()
        package_dir = (base_dir / f"handoff_{handoff_id}").resolve()
        if base_resolved != package_dir and base_resolved not in package_dir.parents:
            return _fail(
                "unsafe_path",
                "handoff package path escaped output_dir",
                "package_dir",
            )
        package_dir.mkdir(parents=True, exist_ok=True)

        instructions = _make_instructions(handoff_id)
        prompt_path = package_dir / "prompt.md"
        context_path = package_dir / "context_summary.md"
        instruction_path = package_dir / "handoff_instructions.md"
        manifest_path = package_dir / "handoff_manifest.json"

        _write_lf(prompt_path, _prompt_markdown(packet, target_agent))
        _write_lf(context_path, _context_markdown(packet, routing_decision))
        _write_lf(instruction_path, _instructions_markdown(instructions))
        manifest = _manifest_payload(
            handoff_id=handoff_id,
            source_packet_id=source_packet_id,
            source_result_packet_id=source_result_packet_id,
            routing_decision_id=routing_decision_id,
            target_agent=target_agent,
            target_runtime_id=target_runtime_id,
            handoff_mode=handoff_mode,
            created_at=created_at,
            files=(prompt_path, context_path, instruction_path),
        )
        _write_lf(
            manifest_path,
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        )
        return ManualHandoffPackage(
            ok=True,
            schema_version=OPERATOR_PACKET_REVIEW_SCHEMA_VERSION,
            handoff_id=handoff_id,
            source_packet_id=source_packet_id,
            source_result_packet_id=source_result_packet_id,
            routing_decision_id=routing_decision_id,
            target_agent=target_agent,
            target_runtime_id=target_runtime_id,
            handoff_mode=handoff_mode,
            created_at=created_at,
            prompt_path=str(prompt_path),
            context_summary_path=str(context_path),
            instruction_path=str(instruction_path),
            manifest_path=str(manifest_path),
            instructions=instructions,
            metadata=metadata,
        )
    except OSError as exc:
        return _fail("handoff_failed", str(exc), "write_package")
