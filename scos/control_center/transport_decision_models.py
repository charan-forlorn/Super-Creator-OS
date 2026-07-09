"""Stage 7.5 immutable models for read surface transport decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

TRANSPORT_DECISION_SCHEMA_VERSION = 1

TRANSPORT_ANALYSIS_OPTIONS = ("NO_LIVE_TRANSPORT", "WEBSOCKET", "SSE", "POLLING")
TRANSPORT_DECISION_VALUES = (
    "NO_LIVE_TRANSPORT",
    "WEBSOCKET_ALLOWED_LATER",
    "SSE_ALLOWED_LATER",
    "POLLING_ALLOWED_LATER",
)
TRANSPORT_GO_NO_GO_VALUES = ("GO", "NO_GO")


def _string_tuple(values: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    return tuple(sorted(str(value) for value in values))


def _require_allowed(field_name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ValueError(f"{field_name} must be one of {list(allowed)}, got {value!r}")


@dataclass(frozen=True)
class TransportOptionAnalysis:
    option: str
    allowed: bool
    security_risk: str
    operational_risk: str
    localhost_boundary: str
    required_controls: tuple[str, ...]
    forbidden_behaviors: tuple[str, ...]
    test_expectations: tuple[str, ...]
    rollback_requirements: tuple[str, ...]
    notes: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "option", str(self.option))
        object.__setattr__(self, "allowed", bool(self.allowed))
        object.__setattr__(self, "security_risk", str(self.security_risk))
        object.__setattr__(self, "operational_risk", str(self.operational_risk))
        object.__setattr__(self, "localhost_boundary", str(self.localhost_boundary))
        object.__setattr__(self, "required_controls", _string_tuple(self.required_controls))
        object.__setattr__(self, "forbidden_behaviors", _string_tuple(self.forbidden_behaviors))
        object.__setattr__(self, "test_expectations", _string_tuple(self.test_expectations))
        object.__setattr__(self, "rollback_requirements", _string_tuple(self.rollback_requirements))
        object.__setattr__(self, "notes", _string_tuple(self.notes))
        _require_allowed("option", self.option, TRANSPORT_ANALYSIS_OPTIONS)

    def to_dict(self) -> dict[str, Any]:
        return {
            "option": self.option,
            "allowed": self.allowed,
            "security_risk": self.security_risk,
            "operational_risk": self.operational_risk,
            "localhost_boundary": self.localhost_boundary,
            "required_controls": list(self.required_controls),
            "forbidden_behaviors": list(self.forbidden_behaviors),
            "test_expectations": list(self.test_expectations),
            "rollback_requirements": list(self.rollback_requirements),
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class TransportDecisionRecord:
    decision_id: str
    decision: str
    decided_at: str
    accepted: bool
    go_no_go: str
    readiness_score: int
    default_transport: str
    analyses: tuple[TransportOptionAnalysis, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    required_next_stage_controls: tuple[str, ...]
    forbidden_until_next_approval: tuple[str, ...]
    rollback_plan: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_id", str(self.decision_id))
        object.__setattr__(self, "decision", str(self.decision))
        object.__setattr__(self, "decided_at", str(self.decided_at))
        object.__setattr__(self, "accepted", bool(self.accepted))
        object.__setattr__(self, "go_no_go", str(self.go_no_go))
        object.__setattr__(self, "readiness_score", int(self.readiness_score))
        object.__setattr__(self, "default_transport", str(self.default_transport))
        object.__setattr__(
            self,
            "analyses",
            tuple(sorted(self.analyses, key=lambda analysis: analysis.option)),
        )
        object.__setattr__(self, "blockers", _string_tuple(self.blockers))
        object.__setattr__(self, "warnings", _string_tuple(self.warnings))
        object.__setattr__(
            self,
            "required_next_stage_controls",
            _string_tuple(self.required_next_stage_controls),
        )
        object.__setattr__(
            self,
            "forbidden_until_next_approval",
            _string_tuple(self.forbidden_until_next_approval),
        )
        object.__setattr__(self, "rollback_plan", _string_tuple(self.rollback_plan))
        _require_allowed("decision", self.decision, TRANSPORT_DECISION_VALUES)
        _require_allowed("go_no_go", self.go_no_go, TRANSPORT_GO_NO_GO_VALUES)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "decision": self.decision,
            "decided_at": self.decided_at,
            "accepted": self.accepted,
            "go_no_go": self.go_no_go,
            "readiness_score": self.readiness_score,
            "default_transport": self.default_transport,
            "analyses": [analysis.to_dict() for analysis in self.analyses],
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "required_next_stage_controls": list(self.required_next_stage_controls),
            "forbidden_until_next_approval": list(self.forbidden_until_next_approval),
            "rollback_plan": list(self.rollback_plan),
        }


@dataclass(frozen=True)
class TransportDecisionError:
    error_code: str
    message: str
    checked_at: str
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "error_code", str(self.error_code))
        object.__setattr__(self, "message", str(self.message))
        object.__setattr__(self, "checked_at", str(self.checked_at))
        object.__setattr__(self, "blockers", _string_tuple(self.blockers))

    @staticmethod
    def of(
        error_code: str,
        message: str,
        *,
        checked_at: str,
        blockers: tuple[str, ...] = (),
    ) -> "TransportDecisionError":
        return TransportDecisionError(
            error_code=error_code,
            message=message,
            checked_at=checked_at,
            blockers=blockers or (message,),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "checked_at": self.checked_at,
            "blockers": list(self.blockers),
        }


__all__ = sorted(
    (
        "TRANSPORT_ANALYSIS_OPTIONS",
        "TRANSPORT_DECISION_SCHEMA_VERSION",
        "TRANSPORT_DECISION_VALUES",
        "TRANSPORT_GO_NO_GO_VALUES",
        "TransportDecisionError",
        "TransportDecisionRecord",
        "TransportOptionAnalysis",
    )
)
