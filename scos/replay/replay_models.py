"""SCOS Stage 3.4 — Analytics Replay Engine data model + diagnostics.

Pure constants, the fatal failure type, and small assembly helpers shared by the
replay orchestrator. NO business logic, NO learning rules, NO I/O. Keeping the
report/result shape here makes ordering a single source of truth and keeps
`analytics_replay.py` focused on workflow only.

Pure stdlib, deterministic.
"""

from __future__ import annotations

# Bumped only when the report/result contract changes (stable, not a timestamp).
REPLAY_VERSION = 1

REPORT_FILENAME = "replay_report.json"

# Top-level replay status. Unlike Stage 3.3, a replay always finishes with PASS
# unless a FATAL error aborts it entirely (no report-of-record is written then) —
# per-record problems are recorded as FAIL results, never as an overall failure.
STATUS_PASS = "PASS"

# Per-record decisions. APPLY/CLAMP/REJECT are surfaced unchanged from the
# certified LearningCoordinator. FAIL is a Stage-3.4-only addition: any per-record
# processing problem (bad data, an "unsafe" coordinator rejection, an asset
# regeneration error) that must NOT abort the rest of the replay.
DECISION_APPLY = "APPLY"
DECISION_CLAMP = "CLAMP"
DECISION_REJECT = "REJECT"
DECISION_FAIL = "FAIL"

# A decision that means the style memory was actually updated.
_APPLIED_DECISIONS = frozenset({DECISION_APPLY, DECISION_CLAMP})


class ReplayFatalError(Exception):
    """A deterministic, stage-tagged failure that aborts the WHOLE replay.

    Reserved for the 3 truly fatal categories: an unreadable dataset file, a
    broken adapter wiring, or a corrupted report store. Any other problem (a bad
    row, an unsafe coordinator rejection, a failed asset regen) is recorded as a
    per-record FAIL result instead — it never raises out of the engine.
    """

    def __init__(self, stage: str, errors: list[str]) -> None:
        self.stage = stage
        self.errors = [str(e) for e in errors]
        super().__init__(f"[{stage}] " + "; ".join(self.errors))


def learning_applied(decision: str) -> bool:
    """True iff the coordinator actually mutated the style (APPLY/CLAMP)."""
    return decision in _APPLIED_DECISIONS


def result_record(
    record_id: str,
    decision: str,
    *,
    style_id: str | None = None,
    quality_score: float | None = None,
    run_id: str | None = None,
    asset_hash: str | None = None,
    timestamp: int = 0,
    error: str | None = None,
    session_id: str | None = None,
) -> dict:
    """Build one replay result entry. Every key is always present (uniform
    schema across success and FAIL entries) so downstream consumers never have
    to branch on which keys exist."""
    return {
        "record_id": record_id,
        "decision": decision,
        "style_id": style_id,
        "quality_score": quality_score,
        "run_id": run_id,
        "asset_hash": asset_hash,
        "timestamp": timestamp,
        "error": error,
        "session_id": session_id,
    }


def report(
    status: str,
    records_processed: int,
    records_applied: int,
    records_rejected: int,
    styles_updated: int,
    results: list[dict],
    session_id: str | None,
) -> dict:
    """Assemble the replay report contract.

    ``session_id`` is additive on top of the originally specified schema
    (status/records_processed/records_applied/records_rejected/styles_updated/
    replay_version/results): it lets a caller later filter the certified
    learning_audit.json / style_history.json by run_id prefix (every per-record
    run_id is tagged with this same session_id) without scanning unrelated
    replay runs — without requiring any change to the certified Coordinator's
    own audit/history schema.
    """
    return {
        "status": status,
        "records_processed": records_processed,
        "records_applied": records_applied,
        "records_rejected": records_rejected,
        "styles_updated": styles_updated,
        "replay_version": REPLAY_VERSION,
        "session_id": session_id,
        "results": results,
    }
