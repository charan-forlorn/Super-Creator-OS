"""SCOS Stage 3.3 — Learning Pipeline data model + diagnostics.

Pure constants, the deterministic failure type, and small assembly helpers shared by
the orchestrator. NO business logic, NO learning rules, NO I/O. Keeping the report /
result shape here makes ordering a single source of truth and keeps
`learning_pipeline.py` focused on workflow only.

Pure stdlib, deterministic.
"""

from __future__ import annotations

# Bumped only when the report/result contract changes (stable, not a timestamp).
PIPELINE_VERSION = "3.3.0"

REPORT_FILENAME = "learning_report.json"

# Execution status (top-level contract field).
STATUS_SUCCESS = "SUCCESS"
STATUS_FAILURE = "FAILURE"

# Coordinator decisions surfaced unchanged from the certified core.
DECISION_APPLY = "APPLY"
DECISION_CLAMP = "CLAMP"
DECISION_REJECT = "REJECT"

# A decision that means the style memory was actually updated.
_APPLIED_DECISIONS = frozenset({DECISION_APPLY, DECISION_CLAMP})

# Score keys carried through translator -> feedback -> coordinator unchanged.
_SCORE_KEYS = ("retention_score", "engagement_score", "style_match_score", "quality_score")


class PipelineError(Exception):
    """A deterministic, stage-tagged failure.

    Carries the failing stage and an ordered list of diagnostic strings so the
    orchestrator can stop immediately and report exactly what broke — never a
    partial success, never a silent recovery.
    """

    def __init__(self, stage: str, errors: list[str]) -> None:
        self.stage = stage
        self.errors = [str(e) for e in errors]
        super().__init__(f"[{stage}] " + "; ".join(self.errors))


def learning_applied(decision: str) -> bool:
    """True iff the coordinator actually mutated the style (APPLY/CLAMP)."""
    return decision in _APPLIED_DECISIONS


def feedback_summary(feedback: dict) -> dict:
    """Deterministic, minimal feedback snapshot for the report."""
    summary = {"run_id": feedback.get("run_id")}
    for key in _SCORE_KEYS:
        summary[key] = feedback.get(key)
    return summary


def decision_record(decision_out: dict) -> dict:
    """Flatten the coordinator's return into a stable report sub-object."""
    return {
        "decision": decision_out.get("decision"),
        "reason": decision_out.get("reason"),
        "audit_id": decision_out.get("audit_id"),
        "style_version": decision_out.get("updated_style", {}).get("style_version"),
        "timestamp": decision_out.get("timestamp"),
    }
