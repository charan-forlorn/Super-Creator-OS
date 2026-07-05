"""SCOS Stage 5.5 Operator Packet Review models.

Immutable dataclasses for the local-only operator review layer that sits
above Stage 5.4 prompt/result packets. These models never dispatch AI work,
touch a clipboard, open an app/browser, call a network API, read a clock, use
randomness, or mutate any Stage 5.1 command queue.

Local-first, deterministic, stdlib-only. All ids are caller- or helper-derived
from stable SHA-256 inputs. Timestamps are always caller-supplied strings.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Iterable, Iterator, Mapping

OPERATOR_PACKET_REVIEW_SCHEMA_VERSION = 1

ALLOWED_REVIEW_CHECK_STATUSES = ("success", "failure", "skipped")
ALLOWED_REVIEW_CHECK_SEVERITIES = ("info", "warning", "error", "critical")
ALLOWED_OPERATOR_PACKET_DECISIONS = (
    "approve",
    "reject",
    "request_changes",
    "manual_handoff",
    "blocked",
)
ALLOWED_OPERATOR_DECIDED_BY = ("operator", "simulated_operator")
ALLOWED_REVIEW_AGENT_NAMES = ("chatgpt", "claude_code", "codex", "hermes", "operator")
ALLOWED_HANDOFF_MODES = (
    "manual_clipboard",
    "manual_app",
    "manual_cli",
    "manual_review_only",
)
ALLOWED_REVIEW_ERROR_KINDS = (
    "invalid_packet",
    "invalid_routing_decision",
    "invalid_decision",
    "invalid_decided_by",
    "missing_required_field",
    "unsupported_agent",
    "unsafe_path",
    "unsafe_metadata",
    "validation_failed",
    "handoff_required",
    "handoff_failed",
    "storage_error",
    "contract_violation",
)

_URL_PREFIXES = ("http://", "https://")
_FORBIDDEN_METADATA_KEY_MARKERS = (
    "api_key",
    "token",
    "secret",
    "password",
    "private_key",
)
_ID_DIGEST_LENGTH = 16


def _require_allowed(field_name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ValueError(
            f"{field_name} must be one of {list(allowed)}, got {value!r}"
        )


def _require_nonempty(field_name: str, value: str | None) -> None:
    if value is None or not str(value).strip():
        raise ValueError(f"{field_name} must not be empty")


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _reject_url_value(field_name: str, value: str | None) -> None:
    if value is None:
        return
    lowered = str(value).lower()
    for marker in _URL_PREFIXES:
        if marker in lowered:
            raise ValueError(
                f"{field_name} must be a local value/path, not a URL "
                f"(found {marker!r})"
            )


def _metadata_items(value: Any) -> tuple[tuple[str, Any], ...]:
    if value is None:
        return ()
    if isinstance(value, FrozenMap):
        return tuple(value.items())
    if isinstance(value, Mapping):
        items = value.items()
    else:
        items = value
    pairs: list[tuple[str, Any]] = []
    for item in items:
        pair = tuple(item)
        if len(pair) != 2:
            raise ValueError(f"metadata entries must be (key, value), got {item!r}")
        pairs.append((str(pair[0]), pair[1]))
    return tuple(sorted(pairs, key=lambda pair: pair[0]))


@dataclass(frozen=True)
class FrozenMap(Mapping[str, str]):
    """Tiny immutable string map used only by Stage 5.5 models."""

    _items: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        normalized: list[tuple[str, str]] = []
        for key, value in _metadata_items(self._items):
            normalized.append((str(key), str(value)))
        object.__setattr__(
            self,
            "_items",
            tuple(sorted(normalized, key=lambda pair: pair[0])),
        )

    def __iter__(self) -> Iterator[str]:
        return (key for key, _value in self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __getitem__(self, key: str) -> str:
        for item_key, item_value in self._items:
            if item_key == key:
                return item_value
        raise KeyError(key)

    @staticmethod
    def of(value: Any = None) -> "FrozenMap":
        frozen = FrozenMap(tuple(_metadata_items(value)))
        for key, value_text in frozen.items():
            lowered_key = key.lower()
            for marker in _FORBIDDEN_METADATA_KEY_MARKERS:
                if marker in lowered_key:
                    raise ValueError(
                        f"metadata must not contain secret-bearing keys "
                        f"(found {key!r})"
                    )
            _reject_url_value("metadata", value_text)
        return frozen

    def to_dict(self) -> dict[str, str]:
        return {key: value for key, value in self._items}


def _frozen_map(value: Any = None) -> FrozenMap:
    return FrozenMap.of(value)


def _checks(value: Any) -> tuple["PacketReviewCheck", ...]:
    checks = tuple(value or ())
    for check in checks:
        if not isinstance(check, PacketReviewCheck):
            raise ValueError("checks entries must be PacketReviewCheck instances")
    return checks


def _instructions(value: Any) -> tuple["ManualHandoffInstruction", ...]:
    instructions = tuple(value or ())
    for instruction in instructions:
        if not isinstance(instruction, ManualHandoffInstruction):
            raise ValueError(
                "instructions entries must be ManualHandoffInstruction instances"
            )
    return tuple(sorted(instructions, key=lambda instruction: instruction.step_order))


def _stable_digest(parts: Iterable[Any]) -> str:
    return hashlib.sha256(
        "|".join("" if part is None else str(part) for part in parts).encode("utf-8")
    ).hexdigest()[:_ID_DIGEST_LENGTH]


def derive_operator_decision_id(
    *,
    packet_id: str,
    routing_decision_id: str | None,
    decision: str,
    decided_by: str,
    decided_at: str,
    reason: str,
    target_agent: str | None,
    target_runtime_id: str | None,
    requires_manual_handoff: bool,
) -> str:
    digest = _stable_digest(
        (
            packet_id,
            routing_decision_id,
            decision,
            decided_by,
            decided_at,
            reason,
            target_agent,
            target_runtime_id,
            requires_manual_handoff,
        )
    )
    return f"opd-{digest}"


def derive_manual_handoff_id(
    *,
    source_packet_id: str,
    source_result_packet_id: str | None,
    routing_decision_id: str | None,
    target_agent: str,
    target_runtime_id: str,
    handoff_mode: str,
    created_at: str,
) -> str:
    digest = _stable_digest(
        (
            source_packet_id,
            source_result_packet_id,
            routing_decision_id,
            target_agent,
            target_runtime_id,
            handoff_mode,
            created_at,
        )
    )
    return f"oph-{digest}"


def derive_operator_review_id(
    *,
    packet_id: str,
    result_packet_id: str | None,
    routing_decision_id: str | None,
    reviewed_at: str,
    decision_id: str,
    handoff_id: str | None,
) -> str:
    digest = _stable_digest(
        (
            packet_id,
            result_packet_id,
            routing_decision_id,
            reviewed_at,
            decision_id,
            handoff_id,
        )
    )
    return f"opr-{digest}"


@dataclass(frozen=True)
class PacketReviewCheck:
    check_name: str
    status: str
    severity: str
    packet_id: str | None
    error_kind: str | None
    error_detail: str | None
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "check_name", str(self.check_name))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "severity", str(self.severity))
        object.__setattr__(self, "packet_id", _optional_str(self.packet_id))
        object.__setattr__(self, "error_kind", _optional_str(self.error_kind))
        object.__setattr__(self, "error_detail", _optional_str(self.error_detail))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))
        _require_nonempty("check_name", self.check_name)
        _require_allowed("status", self.status, ALLOWED_REVIEW_CHECK_STATUSES)
        _require_allowed("severity", self.severity, ALLOWED_REVIEW_CHECK_SEVERITIES)

    @staticmethod
    def of(
        check_name: str,
        status: str,
        severity: str,
        *,
        packet_id: str | None = None,
        error_kind: str | None = None,
        error_detail: str | None = None,
        metadata: Any = None,
    ) -> "PacketReviewCheck":
        return PacketReviewCheck(
            check_name=check_name,
            status=status,
            severity=severity,
            packet_id=packet_id,
            error_kind=error_kind,
            error_detail=error_detail,
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_name": self.check_name,
            "status": self.status,
            "severity": self.severity,
            "packet_id": self.packet_id,
            "error_kind": self.error_kind,
            "error_detail": self.error_detail,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class OperatorPacketDecision:
    decision_id: str
    packet_id: str
    routing_decision_id: str | None
    decision: str
    decided_by: str
    decided_at: str
    reason: str
    target_agent: str | None
    target_runtime_id: str | None
    requires_manual_handoff: bool
    checks: tuple[PacketReviewCheck, ...]
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_id", str(self.decision_id))
        object.__setattr__(self, "packet_id", str(self.packet_id))
        object.__setattr__(
            self, "routing_decision_id", _optional_str(self.routing_decision_id)
        )
        object.__setattr__(self, "decision", str(self.decision))
        object.__setattr__(self, "decided_by", str(self.decided_by))
        object.__setattr__(self, "decided_at", str(self.decided_at))
        object.__setattr__(self, "reason", str(self.reason))
        object.__setattr__(self, "target_agent", _optional_str(self.target_agent))
        object.__setattr__(
            self, "target_runtime_id", _optional_str(self.target_runtime_id)
        )
        object.__setattr__(
            self, "requires_manual_handoff", bool(self.requires_manual_handoff)
        )
        object.__setattr__(self, "checks", _checks(self.checks))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))
        _require_nonempty("decision_id", self.decision_id)
        _require_nonempty("packet_id", self.packet_id)
        _require_nonempty("decided_at", self.decided_at)
        _require_nonempty("reason", self.reason)
        _require_allowed("decision", self.decision, ALLOWED_OPERATOR_PACKET_DECISIONS)
        _require_allowed("decided_by", self.decided_by, ALLOWED_OPERATOR_DECIDED_BY)
        if self.target_agent is not None:
            _require_allowed(
                "target_agent", self.target_agent, ALLOWED_REVIEW_AGENT_NAMES
            )
        if self.decision == "manual_handoff" and not self.requires_manual_handoff:
            raise ValueError("requires_manual_handoff must be true for manual_handoff")

    @staticmethod
    def of(
        *,
        packet_id: str,
        routing_decision_id: str | None,
        decision: str,
        decided_by: str,
        decided_at: str,
        reason: str,
        target_agent: str | None = None,
        target_runtime_id: str | None = None,
        requires_manual_handoff: bool | None = None,
        checks: Any = (),
        metadata: Any = None,
    ) -> "OperatorPacketDecision":
        resolved_requires = (
            decision == "manual_handoff"
            if requires_manual_handoff is None
            else bool(requires_manual_handoff)
        )
        decision_id = derive_operator_decision_id(
            packet_id=packet_id,
            routing_decision_id=routing_decision_id,
            decision=decision,
            decided_by=decided_by,
            decided_at=decided_at,
            reason=reason,
            target_agent=target_agent,
            target_runtime_id=target_runtime_id,
            requires_manual_handoff=resolved_requires,
        )
        return OperatorPacketDecision(
            decision_id=decision_id,
            packet_id=packet_id,
            routing_decision_id=routing_decision_id,
            decision=decision,
            decided_by=decided_by,
            decided_at=decided_at,
            reason=reason,
            target_agent=target_agent,
            target_runtime_id=target_runtime_id,
            requires_manual_handoff=resolved_requires,
            checks=_checks(checks),
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "packet_id": self.packet_id,
            "routing_decision_id": self.routing_decision_id,
            "decision": self.decision,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at,
            "reason": self.reason,
            "target_agent": self.target_agent,
            "target_runtime_id": self.target_runtime_id,
            "requires_manual_handoff": self.requires_manual_handoff,
            "checks": [check.to_dict() for check in self.checks],
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class ManualHandoffInstruction:
    instruction_id: str
    step_order: int
    title: str
    detail: str
    required: bool
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "instruction_id", str(self.instruction_id))
        object.__setattr__(self, "step_order", int(self.step_order))
        object.__setattr__(self, "title", str(self.title))
        object.__setattr__(self, "detail", str(self.detail))
        object.__setattr__(self, "required", bool(self.required))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))
        _require_nonempty("instruction_id", self.instruction_id)
        _require_nonempty("title", self.title)
        _require_nonempty("detail", self.detail)
        if self.step_order <= 0:
            raise ValueError("step_order must be a positive int")

    @staticmethod
    def of(
        *,
        instruction_id: str,
        step_order: int,
        title: str,
        detail: str,
        required: bool = True,
        metadata: Any = None,
    ) -> "ManualHandoffInstruction":
        return ManualHandoffInstruction(
            instruction_id=instruction_id,
            step_order=step_order,
            title=title,
            detail=detail,
            required=required,
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "instruction_id": self.instruction_id,
            "step_order": self.step_order,
            "title": self.title,
            "detail": self.detail,
            "required": self.required,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class ManualHandoffPackage:
    ok: bool
    schema_version: int
    handoff_id: str
    source_packet_id: str
    source_result_packet_id: str | None
    routing_decision_id: str | None
    target_agent: str
    target_runtime_id: str
    handoff_mode: str
    created_at: str
    prompt_path: str
    context_summary_path: str
    instruction_path: str
    manifest_path: str
    instructions: tuple[ManualHandoffInstruction, ...]
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "handoff_id", str(self.handoff_id))
        object.__setattr__(self, "source_packet_id", str(self.source_packet_id))
        object.__setattr__(
            self, "source_result_packet_id", _optional_str(self.source_result_packet_id)
        )
        object.__setattr__(
            self, "routing_decision_id", _optional_str(self.routing_decision_id)
        )
        object.__setattr__(self, "target_agent", str(self.target_agent))
        object.__setattr__(self, "target_runtime_id", str(self.target_runtime_id))
        object.__setattr__(self, "handoff_mode", str(self.handoff_mode))
        object.__setattr__(self, "created_at", str(self.created_at))
        object.__setattr__(self, "prompt_path", str(self.prompt_path))
        object.__setattr__(
            self, "context_summary_path", str(self.context_summary_path)
        )
        object.__setattr__(self, "instruction_path", str(self.instruction_path))
        object.__setattr__(self, "manifest_path", str(self.manifest_path))
        object.__setattr__(self, "instructions", _instructions(self.instructions))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))
        _require_nonempty("handoff_id", self.handoff_id)
        _require_nonempty("source_packet_id", self.source_packet_id)
        _require_nonempty("target_runtime_id", self.target_runtime_id)
        _require_nonempty("created_at", self.created_at)
        _require_allowed("target_agent", self.target_agent, ALLOWED_REVIEW_AGENT_NAMES)
        _require_allowed("handoff_mode", self.handoff_mode, ALLOWED_HANDOFF_MODES)
        for field_name in (
            "prompt_path",
            "context_summary_path",
            "instruction_path",
            "manifest_path",
        ):
            _reject_url_value(field_name, getattr(self, field_name))

    @staticmethod
    def of(
        *,
        source_packet_id: str,
        source_result_packet_id: str | None,
        routing_decision_id: str | None,
        target_agent: str,
        target_runtime_id: str,
        handoff_mode: str,
        created_at: str,
        prompt_path: str,
        context_summary_path: str,
        instruction_path: str,
        manifest_path: str,
        instructions: Any,
        metadata: Any = None,
        ok: bool = True,
        schema_version: int = OPERATOR_PACKET_REVIEW_SCHEMA_VERSION,
    ) -> "ManualHandoffPackage":
        handoff_id = derive_manual_handoff_id(
            source_packet_id=source_packet_id,
            source_result_packet_id=source_result_packet_id,
            routing_decision_id=routing_decision_id,
            target_agent=target_agent,
            target_runtime_id=target_runtime_id,
            handoff_mode=handoff_mode,
            created_at=created_at,
        )
        return ManualHandoffPackage(
            ok=ok,
            schema_version=schema_version,
            handoff_id=handoff_id,
            source_packet_id=source_packet_id,
            source_result_packet_id=source_result_packet_id,
            routing_decision_id=routing_decision_id,
            target_agent=target_agent,
            target_runtime_id=target_runtime_id,
            handoff_mode=handoff_mode,
            created_at=created_at,
            prompt_path=prompt_path,
            context_summary_path=context_summary_path,
            instruction_path=instruction_path,
            manifest_path=manifest_path,
            instructions=_instructions(instructions),
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "handoff_id": self.handoff_id,
            "source_packet_id": self.source_packet_id,
            "source_result_packet_id": self.source_result_packet_id,
            "routing_decision_id": self.routing_decision_id,
            "target_agent": self.target_agent,
            "target_runtime_id": self.target_runtime_id,
            "handoff_mode": self.handoff_mode,
            "created_at": self.created_at,
            "prompt_path": self.prompt_path,
            "context_summary_path": self.context_summary_path,
            "instruction_path": self.instruction_path,
            "manifest_path": self.manifest_path,
            "instructions": [
                instruction.to_dict() for instruction in self.instructions
            ],
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class OperatorPacketReviewResult:
    ok: bool
    schema_version: int
    review_id: str
    packet_id: str
    result_packet_id: str | None
    routing_decision_id: str | None
    reviewed_at: str
    decision: OperatorPacketDecision
    handoff_package: ManualHandoffPackage | None
    checks: tuple[PacketReviewCheck, ...]
    output_path: str | None
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "review_id", str(self.review_id))
        object.__setattr__(self, "packet_id", str(self.packet_id))
        object.__setattr__(self, "result_packet_id", _optional_str(self.result_packet_id))
        object.__setattr__(
            self, "routing_decision_id", _optional_str(self.routing_decision_id)
        )
        object.__setattr__(self, "reviewed_at", str(self.reviewed_at))
        if not isinstance(self.decision, OperatorPacketDecision):
            raise ValueError("decision must be an OperatorPacketDecision")
        if self.handoff_package is not None and not isinstance(
            self.handoff_package, ManualHandoffPackage
        ):
            raise ValueError("handoff_package must be ManualHandoffPackage or None")
        object.__setattr__(self, "checks", _checks(self.checks))
        object.__setattr__(self, "output_path", _optional_str(self.output_path))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))
        _require_nonempty("review_id", self.review_id)
        _require_nonempty("packet_id", self.packet_id)
        _require_nonempty("reviewed_at", self.reviewed_at)
        _reject_url_value("output_path", self.output_path)

    @staticmethod
    def of(
        *,
        packet_id: str,
        result_packet_id: str | None,
        routing_decision_id: str | None,
        reviewed_at: str,
        decision: OperatorPacketDecision,
        handoff_package: ManualHandoffPackage | None = None,
        checks: Any = (),
        output_path: str | None = None,
        metadata: Any = None,
        ok: bool = True,
        schema_version: int = OPERATOR_PACKET_REVIEW_SCHEMA_VERSION,
    ) -> "OperatorPacketReviewResult":
        review_id = derive_operator_review_id(
            packet_id=packet_id,
            result_packet_id=result_packet_id,
            routing_decision_id=routing_decision_id,
            reviewed_at=reviewed_at,
            decision_id=decision.decision_id,
            handoff_id=handoff_package.handoff_id if handoff_package else None,
        )
        return OperatorPacketReviewResult(
            ok=ok,
            schema_version=schema_version,
            review_id=review_id,
            packet_id=packet_id,
            result_packet_id=result_packet_id,
            routing_decision_id=routing_decision_id,
            reviewed_at=reviewed_at,
            decision=decision,
            handoff_package=handoff_package,
            checks=_checks(checks),
            output_path=output_path,
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "review_id": self.review_id,
            "packet_id": self.packet_id,
            "result_packet_id": self.result_packet_id,
            "routing_decision_id": self.routing_decision_id,
            "reviewed_at": self.reviewed_at,
            "decision": self.decision.to_dict(),
            "handoff_package": (
                self.handoff_package.to_dict() if self.handoff_package else None
            ),
            "checks": [check.to_dict() for check in self.checks],
            "output_path": self.output_path,
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True)
class OperatorPacketReviewError:
    ok: bool
    schema_version: int
    error_kind: str
    error_detail: str
    failed_step: str
    checks: tuple[PacketReviewCheck, ...]
    metadata: FrozenMap

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "schema_version", int(self.schema_version))
        object.__setattr__(self, "error_kind", str(self.error_kind))
        object.__setattr__(self, "error_detail", str(self.error_detail))
        object.__setattr__(self, "failed_step", str(self.failed_step))
        object.__setattr__(self, "checks", _checks(self.checks))
        object.__setattr__(self, "metadata", _frozen_map(self.metadata))
        _require_allowed("error_kind", self.error_kind, ALLOWED_REVIEW_ERROR_KINDS)
        _require_nonempty("error_detail", self.error_detail)
        _require_nonempty("failed_step", self.failed_step)

    @staticmethod
    def of(
        error_kind: str,
        error_detail: str,
        failed_step: str,
        *,
        checks: Any = (),
        metadata: Any = None,
        ok: bool = False,
        schema_version: int = OPERATOR_PACKET_REVIEW_SCHEMA_VERSION,
    ) -> "OperatorPacketReviewError":
        return OperatorPacketReviewError(
            ok=ok,
            schema_version=schema_version,
            error_kind=error_kind,
            error_detail=error_detail,
            failed_step=failed_step,
            checks=_checks(checks),
            metadata=_frozen_map(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "schema_version": self.schema_version,
            "error_kind": self.error_kind,
            "error_detail": self.error_detail,
            "failed_step": self.failed_step,
            "checks": [check.to_dict() for check in self.checks],
            "metadata": self.metadata.to_dict(),
        }
