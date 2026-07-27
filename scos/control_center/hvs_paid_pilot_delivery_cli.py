"""SCOS Cohort 10H — bounded Python service bridge for paid-pilot delivery.

Single production entrypoint the Next.js delivery routes call via a
``child_process`` bridge. It owns NO browser-facing logic and performs NO
authorization decisions of its own: rights review, operator approval, package
sealing, backup receipt, and manual-handoff status are delegated to the
authoritative ``hvs_paid_pilot_delivery_service`` + ``PaidPilotDeliveryStore``.

Bridge contract (mirrors Cohort 10E hvs_render_cli):
  Next.js route
    -> child_process -> python -m scos.control_center.hvs_paid_pilot_delivery_cli
      -> PaidPilotDeliveryStore (single-writer delivery truth)
      -> hvs_paid_pilot_delivery_service (business transitions)
      -> hvs_paid_pilot_backup_service (immutable backup + receipt)
      -> hvs_paid_pilot_media_qa_link (reuse Cohort 10G QA engine)

Stdlib-only. Deterministic. Fail-closed. No network/subprocess for delivery.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from .hvs_paid_pilot_delivery_models import (  # noqa: E402
    APPROVED_FOR_DELIVERY,
    REJECTED_REWORK_REQUIRED,
    RIGHTS_APPROVED,
    RIGHTS_INCOMPLETE,
    RIGHTS_NOT_REVIEWED,
    RightsChecklistEntry,
    stable_delivery_id,
)
from .hvs_paid_pilot_delivery_service import (  # noqa: E402
    apply_qa_result,
    approve_delivery,
    create_package,
    mark_ready_for_handoff,
    submit_rights_checklist,
)
from .hvs_paid_pilot_delivery_store import PaidPilotDeliveryStore  # noqa: E402


def _fail(code: str, detail: str | None = None) -> dict[str, Any]:
    return {"ok": False, "error_code": code, "detail": detail}


def _ok(**kw: Any) -> dict[str, Any]:
    return {"ok": True, **kw}


def _parse_stdin() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    return json.loads(raw)


def _store(store_path: str | None = None) -> PaidPilotDeliveryStore:
    if store_path:
        return PaidPilotDeliveryStore(store_path=Path(store_path))
    return PaidPilotDeliveryStore()


def main() -> int:
    if len(sys.argv) < 2:
        print(json.dumps(_fail("MISSING_OPERATION")))
        return 2
    op = sys.argv[1]
    try:
        args = _parse_stdin()
    except Exception:
        print(json.dumps(_fail("REQUEST_MALFORMED", "invalid json")))
        return 2

    store = _store(args.get("store_path"))

    if op == "rights-review":
        project_id = str(args.get("project_id", ""))
        operator_id = str(args.get("operator_id", "local-solo-operator"))
        reviewed_at = str(args.get("reviewed_at", ""))
        delivery_id = str(args.get("delivery_id", "")) or stable_delivery_id(
            project_id=project_id, source_render_attempt_id="rights",
            artifact_sha256="rights-draft", qa_record_id="rights", media_profile="rights",
        )
        try:
            entries = tuple(
                RightsChecklistEntry(
                    asset_kind=str(e.get("asset_kind", "")),
                    description=str(e.get("description", "")),
                    known_source=bool(e.get("known_source", False)),
                    permitted=bool(e.get("permitted", False)),
                    attribution_note=str(e.get("attribution_note", "")),
                )
                for e in args.get("entries", [])
            )
            checklist = submit_rights_checklist(
                store=store,
                delivery_id=delivery_id,
                project_id=project_id,
                operator_id=operator_id,
                reviewed_at=reviewed_at,
                entries=list(entries),
                attestation=str(args.get("attestation", "")),
            )
            rec = store.get(checklist.delivery_id)
            return _print(_ok(
                revision=checklist.revision,
                delivery_id=checklist.delivery_id,
                status=checklist.status,
                record=rec.to_dict() if rec else None,
            ))
        except ValueError as exc:
            return _print(_fail("RIGHTS_REVIEW_INVALID", str(exc)))

    if op == "qa":
        res = apply_qa_result(
            store=store,
            delivery_id=str(args.get("delivery_id", "")),
            qa_report_id=str(args.get("qa_report_id", "")),
            qa_state=str(args.get("qa_state", "")),
            artifact_id=str(args.get("artifact_id", "")),
            artifact_sha256=str(args.get("artifact_sha256", "")),
            recorded_at=str(args.get("recorded_at", "")),
        )
        return _emit(res)

    if op == "approve":
        res = approve_delivery(
            store=store,
            delivery_id=str(args.get("delivery_id", "")),
            operator_id=str(args.get("operator_id", "local-solo-operator")),
            decided_at=str(args.get("decided_at", "")),
            decision=str(args.get("decision", "")),
            source_render_attempt_id=str(args.get("source_render_attempt_id", "")),
            artifact_identity=str(args.get("artifact_identity", "")),
            artifact_sha256=str(args.get("artifact_sha256", "")),
            artifact_size=int(args.get("artifact_size", 0) or 0),
            media_profile=str(args.get("media_profile", "")),
            qa_record_id=str(args.get("qa_record_id", "")),
            qa_state=str(args.get("qa_state", "")),
            rights_revision=str(args.get("rights_revision", "")),
            rights_status=str(args.get("rights_status", "")),
            recorded_at=str(args.get("recorded_at", "")),
        )
        return _emit(res)

    if op == "create-package":
        res = create_package(
            store=store,
            delivery_id=str(args.get("delivery_id", "")),
            project_id=str(args.get("project_id", "")),
            hvs_project_id=str(args.get("hvs_project_id", "")),
            attempt_id=str(args.get("attempt_id", "")),
            profile_id=str(args.get("profile_id", "")),
            qa_report_id=str(args.get("qa_report_id", "")),
            artifact_path=str(args.get("artifact_path", "")),
            operator_id=str(args.get("operator_id", "local-solo-operator")),
            recorded_at=str(args.get("recorded_at", "")),
            rights_revision=str(args.get("rights_revision", "")),
            rights_status=str(args.get("rights_status", "")),
            retention_class=str(args.get("retention_class", "MANUAL_PURGE_REQUIRED")),
        )
        return _emit(res)

    if op == "mark-handoff-ready":
        res = mark_ready_for_handoff(store=store, delivery_id=str(args.get("delivery_id", "")))
        return _emit(res)

    if op == "get":
        rec = store.get(str(args.get("delivery_id", "")))
        if rec is None:
            return _print(_fail("DELIVERY_NOT_FOUND"))
        return _print(_ok(record=rec.to_dict()))

    if op == "list":
        return _print(_ok(records=[r.to_dict() for r in store.list_all()]))

    return _print(_fail("UNKNOWN_OPERATION", op))


def _emit(res):
    if res.ok:
        return _print(_ok(
            record=res.record.to_dict() if res.record else None,
            package_sha256=res.package_sha256,
            package_path=res.package_path,
            backup_receipt=res.backup_receipt.to_dict() if res.backup_receipt else None,
        ))
    return _print(_fail(res.error_code or "DELIVERY_FAILED", res.error_detail))


def _print(payload: dict[str, Any]) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
