"""Stage 7.5 deterministic read surface transport decision gate."""

from __future__ import annotations

import hashlib
import json

try:
    from .transport_decision_models import (
        TRANSPORT_ANALYSIS_OPTIONS,
        TRANSPORT_DECISION_VALUES,
        TransportDecisionError,
        TransportDecisionRecord,
        TransportOptionAnalysis,
    )
except ImportError:  # direct-module execution
    from transport_decision_models import (
        TRANSPORT_ANALYSIS_OPTIONS,
        TRANSPORT_DECISION_VALUES,
        TransportDecisionError,
        TransportDecisionRecord,
        TransportOptionAnalysis,
    )

_DEFAULT_TRANSPORT = "STATIC_MOCK_FALLBACK"

_NEXT_STAGE_CONTROLS = (
    "append-only decision evidence",
    "auth and CSRF review for any future HTTP route",
    "deterministic event schema",
    "frontend coverage for loading, empty, degraded, and error states",
    "localhost-only operator boundary",
    "operator approval before implementation",
    "rollback and kill switch plan",
    "security scan before activation",
)

_FORBIDDEN_UNTIL_APPROVAL = (
    "ADAPTER DISPATCH",
    "BACKGROUND WORKERS",
    "CLOUD OR NETWORK PRODUCT BEHAVIOR",
    "FRONTEND RUNTIME TRANSPORT",
    "HTTP CLIENT CALLS",
    "HTTP ROUTES",
    "POLLING",
    "SSE EVENT STREAM",
    "STATE EVENT APPROVAL AUDIT OR QUEUE MUTATION",
    "TIMER LOOPS",
    "WEBSOCKET",
)

_ROLLBACK_PLAN = (
    "keep Stage 7.4 static projection available",
    "remove any later transport entry point as a single-stage revert",
    "return UI projection to deterministic fixture data",
    "run focused control center tests and security scan after rollback",
)

_WARNINGS = (
    "Stage 7.5 is a decision gate only; live UI sync remains forbidden until a later explicit implementation stage.",
    "WEBSOCKET, SSE, and POLLING are allowed only as future decisions with operator approval and controls.",
)


def _stable_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _stable_id(*parts: object) -> str:
    payload = "|".join(str(part) for part in parts)
    return "rstd-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _validate_decided_at(decided_at: str) -> str | None:
    if not str(decided_at).strip():
        return "decided_at must be caller-supplied and non-empty"
    return None


def create_transport_option_analysis(
    *,
    option: str,
    allowed: bool,
    security_risk: str,
    operational_risk: str,
    localhost_boundary: str,
    required_controls: tuple[str, ...] = (),
    forbidden_behaviors: tuple[str, ...] = (),
    test_expectations: tuple[str, ...] = (),
    rollback_requirements: tuple[str, ...] = (),
    notes: tuple[str, ...] = (),
) -> TransportOptionAnalysis | TransportDecisionError:
    if option not in TRANSPORT_ANALYSIS_OPTIONS:
        return TransportDecisionError.of(
            "INVALID_TRANSPORT_OPTION",
            f"option must be one of {list(TRANSPORT_ANALYSIS_OPTIONS)}",
            checked_at="",
        )
    try:
        return TransportOptionAnalysis(
            option=option,
            allowed=allowed,
            security_risk=security_risk,
            operational_risk=operational_risk,
            localhost_boundary=localhost_boundary,
            required_controls=required_controls,
            forbidden_behaviors=forbidden_behaviors,
            test_expectations=test_expectations,
            rollback_requirements=rollback_requirements,
            notes=notes,
        )
    except ValueError as exc:
        return TransportDecisionError.of(
            "INVALID_TRANSPORT_ANALYSIS",
            str(exc),
            checked_at="",
        )


def _analysis_set() -> tuple[TransportOptionAnalysis, ...]:
    analyses = (
        create_transport_option_analysis(
            option="NO_LIVE_TRANSPORT",
            allowed=True,
            security_risk="lowest; no listener or browser runtime channel is introduced",
            operational_risk="lowest; Stage 7.4 static projection remains deterministic",
            localhost_boundary="manual local projection only; no runtime channel",
            required_controls=("preserve static fallback", "document later activation gate"),
            forbidden_behaviors=_FORBIDDEN_UNTIL_APPROVAL,
            test_expectations=("deterministic decision ID", "static scan rejects runtime transport tokens"),
            rollback_requirements=("no rollback needed beyond preserving Stage 7.4 fallback",),
            notes=("preferred Stage 7.5 decision",),
        ),
        create_transport_option_analysis(
            option="WEBSOCKET",
            allowed=False,
            security_risk="high; persistent bidirectional channel requires separate origin and auth review",
            operational_risk="high; reconnect and lifecycle behavior can hide stale state",
            localhost_boundary="future localhost-only approval required before implementation",
            required_controls=_NEXT_STAGE_CONTROLS,
            forbidden_behaviors=("implementation in Stage 7.5", "runtime listener", "adapter dispatch"),
            test_expectations=("future tests must prove local-only bind", "future tests must prove fallback"),
            rollback_requirements=("future implementation must have a kill switch",),
            notes=("allowed later only by explicit next-stage approval",),
        ),
        create_transport_option_analysis(
            option="SSE",
            allowed=False,
            security_risk="medium; one-way HTTP stream still needs auth, origin, and data exposure review",
            operational_risk="medium; long-lived stream behavior can become stale without visible failure",
            localhost_boundary="future localhost-only approval required before implementation",
            required_controls=_NEXT_STAGE_CONTROLS,
            forbidden_behaviors=("implementation in Stage 7.5", "runtime stream", "adapter dispatch"),
            test_expectations=("future tests must prove fallback", "future tests must reject remote origins"),
            rollback_requirements=("future implementation must fall back to static projection",),
            notes=("allowed later only by explicit next-stage approval",),
        ),
        create_transport_option_analysis(
            option="POLLING",
            allowed=False,
            security_risk="medium; repeated reads through an HTTP route require auth and rate review",
            operational_risk="medium; repeated refresh can create noisy local load and stale illusions",
            localhost_boundary="future localhost-only approval required before implementation",
            required_controls=_NEXT_STAGE_CONTROLS,
            forbidden_behaviors=("implementation in Stage 7.5", "timer loop", "adapter dispatch"),
            test_expectations=("future tests must prove bounded cadence", "future tests must prove fallback"),
            rollback_requirements=("future implementation must stop refresh loops immediately",),
            notes=("allowed later only by explicit next-stage approval",),
        ),
    )
    errors = tuple(item for item in analyses if isinstance(item, TransportDecisionError))
    if errors:
        raise ValueError(errors[0].message)
    return tuple(item for item in analyses if isinstance(item, TransportOptionAnalysis))


def _score(
    *,
    requested_decision: str,
    blockers: tuple[str, ...],
    allow_transport_implementation: bool,
) -> int:
    if blockers or allow_transport_implementation:
        return min(50, max(0, 50 - (len(blockers) * 5)))
    if requested_decision == "NO_LIVE_TRANSPORT":
        return 100
    return 90


def build_read_surface_transport_decision(
    *,
    decided_at: str,
    requested_decision: str = "NO_LIVE_TRANSPORT",
    allow_transport_implementation: bool = False,
) -> TransportDecisionRecord | TransportDecisionError:
    checked_at = str(decided_at)
    decided_error = _validate_decided_at(checked_at)
    if decided_error:
        return TransportDecisionError.of(
            "INVALID_DECIDED_AT",
            decided_error,
            checked_at=checked_at,
        )
    if requested_decision not in TRANSPORT_DECISION_VALUES:
        return TransportDecisionError.of(
            "INVALID_REQUESTED_DECISION",
            f"requested_decision must be one of {list(TRANSPORT_DECISION_VALUES)}",
            checked_at=checked_at,
        )

    analyses = _analysis_set()
    blockers: tuple[str, ...] = ()
    if allow_transport_implementation:
        blockers = (
            "Stage 7.5 does not approve immediate live UI sync implementation",
        )

    accepted = not blockers
    go_no_go = "GO" if accepted else "NO_GO"
    readiness_score = _score(
        requested_decision=requested_decision,
        blockers=blockers,
        allow_transport_implementation=allow_transport_implementation,
    )
    decision_id = _stable_id(
        checked_at,
        requested_decision,
        bool(allow_transport_implementation),
        _stable_json([analysis.to_dict() for analysis in analyses]),
    )
    return TransportDecisionRecord(
        decision_id=decision_id,
        decision=requested_decision,
        decided_at=checked_at,
        accepted=accepted,
        go_no_go=go_no_go,
        readiness_score=readiness_score,
        default_transport=_DEFAULT_TRANSPORT,
        analyses=analyses,
        blockers=blockers,
        warnings=_WARNINGS,
        required_next_stage_controls=_NEXT_STAGE_CONTROLS,
        forbidden_until_next_approval=_FORBIDDEN_UNTIL_APPROVAL,
        rollback_plan=_ROLLBACK_PLAN,
    )


def validate_transport_decision_gate(
    *,
    decided_at: str,
    allow_transport_implementation: bool = False,
) -> TransportDecisionRecord | TransportDecisionError:
    return build_read_surface_transport_decision(
        decided_at=decided_at,
        requested_decision="NO_LIVE_TRANSPORT",
        allow_transport_implementation=allow_transport_implementation,
    )


def export_transport_decision_markdown(
    *,
    decision: TransportDecisionRecord,
) -> str:
    lines = [
        "# Stage 7.5 Read Surface Transport Decision",
        "",
        f"- Decision ID: `{decision.decision_id}`",
        f"- Decided at: `{decision.decided_at}`",
        f"- Decision: `{decision.decision}`",
        f"- Accepted: `{decision.accepted}`",
        f"- Go/No-Go: `{decision.go_no_go}`",
        f"- Readiness score: `{decision.readiness_score}`",
        f"- Default transport: `{decision.default_transport}`",
        "",
        "## Blockers",
    ]
    lines.extend(f"- {item}" for item in (decision.blockers or ("none",)))
    lines.append("")
    lines.append("## Warnings")
    lines.extend(f"- {item}" for item in (decision.warnings or ("none",)))
    lines.append("")
    lines.append("## Required Next Stage Controls")
    lines.extend(f"- {item}" for item in decision.required_next_stage_controls)
    lines.append("")
    lines.append("## Forbidden Until Next Approval")
    lines.extend(f"- {item}" for item in decision.forbidden_until_next_approval)
    lines.append("")
    lines.append("## Rollback Plan")
    lines.extend(f"- {item}" for item in decision.rollback_plan)
    lines.append("")
    lines.append("## Option Analyses")
    for analysis in decision.analyses:
        lines.append(f"### {analysis.option}")
        lines.append(f"- Allowed now: `{analysis.allowed}`")
        lines.append(f"- Security risk: {analysis.security_risk}")
        lines.append(f"- Operational risk: {analysis.operational_risk}")
        lines.append(f"- Localhost boundary: {analysis.localhost_boundary}")
    return "\n".join(lines) + "\n"


__all__ = sorted(
    (
        "build_read_surface_transport_decision",
        "create_transport_option_analysis",
        "export_transport_decision_markdown",
        "validate_transport_decision_gate",
    )
)
