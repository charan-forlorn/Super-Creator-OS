"""Stage 7.2 immutable models for read surface coherence checks.

The coherence gate verifies the Stage 7.1 read surface against local Stage 6
evidence. Models are frozen and serialize deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

READ_SURFACE_COHERENCE_SCHEMA_VERSION = 1

CHECK_STATUSES = ("success", "warning", "failure")
CHECK_SEVERITIES = ("info", "warning", "error", "critical")
ISSUE_SEVERITIES = ("warning", "error", "critical")
GO_NO_GO_VALUES = ("GO", "NO_GO")


def _pairs(value: Any) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    pairs: list[tuple[str, str]] = []
    for item in value:
        pair = tuple(item)
        if len(pair) != 2:
            raise ValueError(f"metadata entries must be pairs, got {item!r}")
        pairs.append((str(pair[0]), str(pair[1])))
    return tuple(sorted(pairs, key=lambda pair: pair[0]))


def _require_allowed(field_name: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ValueError(f"{field_name} must be one of {list(allowed)}, got {value!r}")


@dataclass(frozen=True)
class ReadSurfaceContractCheck:
    check_id: str
    check_name: str
    status: str
    severity: str
    summary: str
    source_stage: str
    references: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "check_id", str(self.check_id))
        object.__setattr__(self, "check_name", str(self.check_name))
        object.__setattr__(self, "status", str(self.status))
        object.__setattr__(self, "severity", str(self.severity))
        object.__setattr__(self, "summary", str(self.summary))
        object.__setattr__(self, "source_stage", str(self.source_stage))
        object.__setattr__(self, "references", tuple(sorted(str(item) for item in self.references)))
        object.__setattr__(self, "metadata", _pairs(self.metadata))
        _require_allowed("status", self.status, CHECK_STATUSES)
        _require_allowed("severity", self.severity, CHECK_SEVERITIES)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "check_name": self.check_name,
            "status": self.status,
            "severity": self.severity,
            "summary": self.summary,
            "source_stage": self.source_stage,
            "references": list(self.references),
            "metadata": [[key, value] for key, value in self.metadata],
        }


@dataclass(frozen=True)
class ReadSurfaceCoherenceIssue:
    issue_id: str
    issue_type: str
    severity: str
    message: str
    source_reference: str
    read_surface_reference: str
    blocker: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "issue_id", str(self.issue_id))
        object.__setattr__(self, "issue_type", str(self.issue_type))
        object.__setattr__(self, "severity", str(self.severity))
        object.__setattr__(self, "message", str(self.message))
        object.__setattr__(self, "source_reference", str(self.source_reference))
        object.__setattr__(self, "read_surface_reference", str(self.read_surface_reference))
        object.__setattr__(self, "blocker", bool(self.blocker))
        _require_allowed("severity", self.severity, ISSUE_SEVERITIES)

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "issue_type": self.issue_type,
            "severity": self.severity,
            "message": self.message,
            "source_reference": self.source_reference,
            "read_surface_reference": self.read_surface_reference,
            "blocker": self.blocker,
        }


@dataclass(frozen=True)
class ReadSurfaceCoherenceReport:
    report_id: str
    checked_at: str
    accepted: bool
    go_no_go: str
    readiness_score: int
    contract_checks: tuple[ReadSurfaceContractCheck, ...]
    coherence_issues: tuple[ReadSurfaceCoherenceIssue, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "report_id", str(self.report_id))
        object.__setattr__(self, "checked_at", str(self.checked_at))
        object.__setattr__(self, "accepted", bool(self.accepted))
        object.__setattr__(self, "go_no_go", str(self.go_no_go))
        object.__setattr__(self, "readiness_score", int(self.readiness_score))
        object.__setattr__(
            self,
            "contract_checks",
            tuple(sorted(self.contract_checks, key=lambda item: item.check_id)),
        )
        object.__setattr__(
            self,
            "coherence_issues",
            tuple(sorted(self.coherence_issues, key=lambda item: item.issue_id)),
        )
        object.__setattr__(self, "blockers", tuple(sorted(str(item) for item in self.blockers)))
        object.__setattr__(self, "warnings", tuple(sorted(str(item) for item in self.warnings)))
        _require_allowed("go_no_go", self.go_no_go, GO_NO_GO_VALUES)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "checked_at": self.checked_at,
            "accepted": self.accepted,
            "go_no_go": self.go_no_go,
            "readiness_score": self.readiness_score,
            "contract_checks": [check.to_dict() for check in self.contract_checks],
            "coherence_issues": [issue.to_dict() for issue in self.coherence_issues],
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class ReadSurfaceCoherenceError:
    error_code: str
    message: str
    checked_at: str
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "error_code", str(self.error_code))
        object.__setattr__(self, "message", str(self.message))
        object.__setattr__(self, "checked_at", str(self.checked_at))
        object.__setattr__(self, "blockers", tuple(sorted(str(item) for item in self.blockers)))

    @staticmethod
    def of(
        error_code: str,
        message: str,
        *,
        checked_at: str,
        blockers: tuple[str, ...] = (),
    ) -> "ReadSurfaceCoherenceError":
        return ReadSurfaceCoherenceError(
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
        "CHECK_SEVERITIES",
        "CHECK_STATUSES",
        "GO_NO_GO_VALUES",
        "ISSUE_SEVERITIES",
        "READ_SURFACE_COHERENCE_SCHEMA_VERSION",
        "ReadSurfaceCoherenceError",
        "ReadSurfaceCoherenceIssue",
        "ReadSurfaceCoherenceReport",
        "ReadSurfaceContractCheck",
    )
)
