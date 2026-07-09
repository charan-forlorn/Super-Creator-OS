"""Stage 7.8 immutable final closure gate models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

STAGE7_CLOSURE_SCHEMA_VERSION = 1

STAGE7_GO_NO_GO_VALUES = ("GO", "NO_GO", "BLOCKED")
STAGE7_CLOSURE_STATUSES = ("pass", "warning", "blocker", "skipped")
STAGE7_CLOSURE_CATEGORIES = (
    "artifact",
    "compatibility",
    "safety",
    "testing",
    "frontend",
    "security",
    "handoff",
)


def _require_allowed(field_name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ValueError(f"{field_name} must be one of {list(allowed)}, got {value!r}")


def _strings(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    return tuple(sorted(str(value) for value in values))


def _pairs(values: Any) -> tuple[tuple[str, str], ...]:
    if values is None:
        return ()
    pairs: list[tuple[str, str]] = []
    for value in values:
        pair = tuple(value)
        if len(pair) != 2:
            raise ValueError(f"metadata entries must be pairs, got {value!r}")
        pairs.append((str(pair[0]), str(pair[1])))
    return tuple(sorted(pairs, key=lambda pair: pair[0]))


@dataclass(frozen=True)
class Stage7ClosureArtifact:
    artifact_id: str
    stage: str
    artifact_type: str
    path: str
    required: bool
    exists: bool
    readable: bool
    digest: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_id", str(self.artifact_id))
        object.__setattr__(self, "stage", str(self.stage))
        object.__setattr__(self, "artifact_type", str(self.artifact_type))
        object.__setattr__(self, "path", str(self.path))
        object.__setattr__(self, "required", bool(self.required))
        object.__setattr__(self, "exists", bool(self.exists))
        object.__setattr__(self, "readable", bool(self.readable))
        object.__setattr__(self, "digest", None if self.digest is None else str(self.digest))

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "stage": self.stage,
            "artifact_type": self.artifact_type,
            "path": self.path,
            "required": self.required,
            "exists": self.exists,
            "readable": self.readable,
            "digest": self.digest,
        }


@dataclass(frozen=True)
class Stage7ClosureCheck:
    check_id: str
    check_name: str
    category: str
    status: str
    summary: str
    required: bool
    references: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "check_id", str(self.check_id))
        object.__setattr__(self, "check_name", str(self.check_name))
        object.__setattr__(self, "category", str(self.category))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "summary", str(self.summary))
        object.__setattr__(self, "required", bool(self.required))
        object.__setattr__(self, "references", _strings(self.references))
        object.__setattr__(self, "metadata", _pairs(self.metadata))
        _require_allowed("category", self.category, STAGE7_CLOSURE_CATEGORIES)
        _require_allowed("status", self.status, STAGE7_CLOSURE_STATUSES)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "check_name": self.check_name,
            "category": self.category,
            "status": self.status,
            "summary": self.summary,
            "required": self.required,
            "references": list(self.references),
            "metadata": [[key, value] for key, value in self.metadata],
        }


@dataclass(frozen=True)
class Stage7ClosureResult:
    gate_id: str
    gate_name: str
    checked_at: str
    go_no_go: str
    readiness_score: int
    accepted: bool
    stage_closed: bool
    stage_number: str
    latest_commit: str | None
    required_artifacts: tuple[Stage7ClosureArtifact, ...]
    optional_artifacts: tuple[Stage7ClosureArtifact, ...]
    stage_results: tuple[Stage7ClosureCheck, ...]
    compatibility_results: tuple[Stage7ClosureCheck, ...]
    safety_results: tuple[Stage7ClosureCheck, ...]
    test_results: tuple[Stage7ClosureCheck, ...]
    frontend_check_results: tuple[Stage7ClosureCheck, ...]
    security_results: tuple[Stage7ClosureCheck, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    inspected_artifacts: tuple[Stage7ClosureArtifact, ...]
    deferred_items: tuple[str, ...]
    forbidden_items_rejected: tuple[str, ...]
    stage8_handoff_path: str | None
    report_path: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "gate_id", str(self.gate_id))
        object.__setattr__(self, "gate_name", str(self.gate_name))
        object.__setattr__(self, "checked_at", str(self.checked_at))
        object.__setattr__(self, "go_no_go", str(self.go_no_go))
        object.__setattr__(self, "readiness_score", int(self.readiness_score))
        object.__setattr__(self, "accepted", bool(self.accepted))
        object.__setattr__(self, "stage_closed", bool(self.stage_closed))
        object.__setattr__(self, "stage_number", str(self.stage_number))
        object.__setattr__(self, "latest_commit", None if self.latest_commit is None else str(self.latest_commit))
        for field_name in (
            "required_artifacts",
            "optional_artifacts",
            "inspected_artifacts",
        ):
            object.__setattr__(
                self,
                field_name,
                tuple(sorted(getattr(self, field_name), key=lambda item: item.artifact_id)),
            )
        for field_name in (
            "stage_results",
            "compatibility_results",
            "safety_results",
            "test_results",
            "frontend_check_results",
            "security_results",
        ):
            object.__setattr__(
                self,
                field_name,
                tuple(sorted(getattr(self, field_name), key=lambda item: item.check_id)),
            )
        object.__setattr__(self, "blockers", _strings(self.blockers))
        object.__setattr__(self, "warnings", _strings(self.warnings))
        object.__setattr__(self, "deferred_items", _strings(self.deferred_items))
        object.__setattr__(self, "forbidden_items_rejected", _strings(self.forbidden_items_rejected))
        object.__setattr__(
            self,
            "stage8_handoff_path",
            None if self.stage8_handoff_path is None else str(self.stage8_handoff_path),
        )
        object.__setattr__(self, "report_path", None if self.report_path is None else str(self.report_path))
        _require_allowed("go_no_go", self.go_no_go, STAGE7_GO_NO_GO_VALUES)
        if self.go_no_go == "GO" and self.readiness_score != 100:
            raise ValueError("GO requires readiness_score=100")
        if self.go_no_go == "BLOCKED" and not 0 <= self.readiness_score <= 69:
            raise ValueError("BLOCKED requires readiness_score between 0 and 69")
        if self.go_no_go == "NO_GO" and not 70 <= self.readiness_score <= 99:
            raise ValueError("NO_GO requires readiness_score between 70 and 99")
        if self.stage_closed and not (self.go_no_go == "GO" and self.accepted):
            raise ValueError("stage_closed=True requires GO and accepted=True")

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "gate_name": self.gate_name,
            "checked_at": self.checked_at,
            "go_no_go": self.go_no_go,
            "readiness_score": self.readiness_score,
            "accepted": self.accepted,
            "stage_closed": self.stage_closed,
            "stage_number": self.stage_number,
            "latest_commit": self.latest_commit,
            "required_artifacts": [artifact.to_dict() for artifact in self.required_artifacts],
            "optional_artifacts": [artifact.to_dict() for artifact in self.optional_artifacts],
            "stage_results": [check.to_dict() for check in self.stage_results],
            "compatibility_results": [check.to_dict() for check in self.compatibility_results],
            "safety_results": [check.to_dict() for check in self.safety_results],
            "test_results": [check.to_dict() for check in self.test_results],
            "frontend_check_results": [check.to_dict() for check in self.frontend_check_results],
            "security_results": [check.to_dict() for check in self.security_results],
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "inspected_artifacts": [artifact.to_dict() for artifact in self.inspected_artifacts],
            "deferred_items": list(self.deferred_items),
            "forbidden_items_rejected": list(self.forbidden_items_rejected),
            "stage8_handoff_path": self.stage8_handoff_path,
            "report_path": self.report_path,
        }


@dataclass(frozen=True)
class Stage7ClosureError:
    error_code: str
    message: str
    checked_at: str
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "error_code", str(self.error_code))
        object.__setattr__(self, "message", str(self.message))
        object.__setattr__(self, "checked_at", str(self.checked_at))
        object.__setattr__(self, "blockers", _strings(self.blockers))

    @staticmethod
    def of(
        error_code: str,
        message: str,
        *,
        checked_at: str,
        blockers: tuple[str, ...] = (),
    ) -> "Stage7ClosureError":
        return Stage7ClosureError(
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
        "STAGE7_CLOSURE_CATEGORIES",
        "STAGE7_CLOSURE_SCHEMA_VERSION",
        "STAGE7_CLOSURE_STATUSES",
        "STAGE7_GO_NO_GO_VALUES",
        "Stage7ClosureArtifact",
        "Stage7ClosureCheck",
        "Stage7ClosureError",
        "Stage7ClosureResult",
    )
)
