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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

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
from . import hvs_paid_pilot_audit as _audit  # noqa: E402


def _audit_log_path(store_path: str | None) -> Path:
    base = Path(store_path) if store_path else PaidPilotDeliveryStore()._store_path
    return base.parent / "paid-pilot-audit-v1.jsonl"


def _append_audit(
    *, store_path: str | None, delivery_id: str, actor: str,
    transition: str, previous_state: str, new_state: str,
    result: str, correlation_key: str, recorded_at: str, detail: str = "",
) -> None:
    try:
        _audit.append_audit_event(
            audit_log_path=_audit_log_path(store_path),
            event_type=transition,
            delivery_id=delivery_id, actor=actor, transition=transition,
            previous_state=previous_state, new_state=new_state, result=result,
            correlation_key=correlation_key, recorded_at=recorded_at, detail=detail,
        )
    except Exception:
        # Audit must never break the authoritative transition.
        pass


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
            _append_audit(
                store_path=str(args.get("store_path")),
                delivery_id=checklist.delivery_id, actor=operator_id,
                transition="RIGHTS_REVIEWED", previous_state="",
                new_state=checklist.status, result="OK",
                correlation_key=checklist.revision, recorded_at=reviewed_at,
            )
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
        return _emit_with_audit(
            res, store_path=str(args.get("store_path")), transition="QA_APPLIED",
            actor="local-solo-operator", recorded_at=str(args.get("recorded_at", "")),
            correlation_key=str(args.get("qa_report_id", "")),
        )

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
        return _emit_with_audit(
            res, store_path=str(args.get("store_path")), transition="DELIVERY_APPROVED",
            actor=str(args.get("operator_id", "local-solo-operator")),
            recorded_at=str(args.get("recorded_at", "")),
            correlation_key=str(args.get("source_render_attempt_id", "")),
        )

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
        return _emit_with_audit(
            res, store_path=str(args.get("store_path")), transition="PACKAGE_CREATED",
            actor=str(args.get("operator_id", "local-solo-operator")),
            recorded_at=str(args.get("recorded_at", "")),
            correlation_key=str(args.get("attempt_id", "")),
        )

    if op == "mark-handoff-ready":
        res = mark_ready_for_handoff(store=store, delivery_id=str(args.get("delivery_id", "")))
        return _emit_with_audit(
            res, store_path=str(args.get("store_path")), transition="HANDOFF_READY",
            actor="local-solo-operator", recorded_at=_now_iso(),
            correlation_key=str(args.get("delivery_id", "")),
        )

    if op == "get":
        rec = store.get(str(args.get("delivery_id", "")))
        if rec is None:
            return _print(_fail("DELIVERY_NOT_FOUND"))
        return _print(_ok(record=rec.to_dict()))

    if op == "readiness":
        # Authoritative readiness projection (Cohort 10I). The browser must
        # never derive readiness itself; it consumes this server-computed
        # projection so the Python authority remains the single source of truth.
        from .hvs_paid_pilot_readiness import compute_readiness

        delivery_id = str(args.get("delivery_id", ""))
        if not delivery_id:
            return _print(_fail("MISSING_DELIVERY_ID"))
        projection = compute_readiness(store=store, delivery_id=delivery_id)
        rec = store.get(delivery_id)
        out = projection.to_dict()
        # Bridge envelope carries the projection under browser-safe keys and
        # always includes the record (so the route can distinguish
        # "no record" from "record exists but not ready").
        out["readiness_state"] = out.pop("state")
        out["record"] = rec.to_dict() if rec is not None else None
        return _print(_ok(**out))

    if op == "restore":
        # Authoritative restore drill: restore the delivery package into a
        # FRESH isolated root and, on success, append a RESTORE_VERIFIED audit
        # event so readiness can certify the drill. Server-resolved roots only.
        from .hvs_paid_pilot_restore import restore_to_fresh_root
        from .hvs_paid_pilot_delivery_service import (
            DEFAULT_BACKUP_ROOT_RELATIVE,
            DEFAULT_PACKAGE_ROOT_RELATIVE,
        )

        delivery_id = str(args.get("delivery_id", ""))
        restore_root = str(args.get("restore_root", "")) or None
        expected_package_sha256 = str(args.get("expected_package_sha256", "")) or None
        if not delivery_id or not restore_root:
            return _print(_fail("MISSING_RESTORE_ARGS", "delivery_id and restore_root required"))
        if not expected_package_sha256:
            return _print(_fail("MISSING_RESTORE_ARGS", "expected_package_sha256 required"))
        repo_root = Path(__file__).resolve().parents[2]
        pkg_root = Path(str(args.get("package_root", "")) or (repo_root / DEFAULT_PACKAGE_ROOT_RELATIVE))
        bkp_root = Path(str(args.get("backup_root", "")) or (repo_root / DEFAULT_BACKUP_ROOT_RELATIVE))
        rr = restore_to_fresh_root(
            delivery_id=delivery_id,
            package_root=pkg_root,
            backup_root=bkp_root,
            restore_root=Path(restore_root),
            expected_package_sha256=expected_package_sha256,
        )
        if rr.ok:
            _audit.append_audit_event(
                audit_log_path=_audit_log_path(str(args.get("store_path"))),
                event_type="RESTORE_VERIFIED",
                delivery_id=delivery_id, actor="local-solo-operator",
                transition="RESTORE_DRILL", previous_state="", new_state="RESTORE_VERIFIED",
                result="OK", correlation_key=delivery_id,
                recorded_at=_now_iso(),
                detail=f"restored_root={restore_root}",
            )
        return _print(_ok(
            ok=rr.ok, delivery_id=delivery_id,
            error_code=None if rr.ok else rr.error_code,
            restored_root=rr.restored_root,
            inventory=list(rr.inventory),
            package_sha256=rr.package_sha256,
            backup_sha256=rr.backup_sha256,
        ))

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


def _emit_with_audit(res, *, store_path, transition, actor, recorded_at, correlation_key=""):
    """Emit the service result and append a durable audit event on success."""
    if res.ok and res.record is not None:
        _append_audit(
            store_path=store_path, delivery_id=res.record.delivery_id, actor=actor,
            transition=transition, previous_state="", new_state=res.record.state,
            result="OK", correlation_key=correlation_key or res.record.delivery_id,
            recorded_at=recorded_at,
        )
    return _emit(res)


def _print(payload: dict[str, Any]) -> int:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
