"""Stage 8S — read-only lifecycle release CLI commands.

Three strictly read-only commands are exposed here and registered into the
shared ``cli.py`` parser via :func:`register`:

* ``inspect-hvs-lifecycle``   — full read-only lifecycle view (state, blockers,
                                next action, identity chain, boundary flags).
* ``verify-hvs-lifecycle``    — non-mutating consistency verification across
                                stages (fail-closed on contradiction).
* ``inspect-hvs-next-action`` — exactly one allowed next operator action.

These commands are inspection-only: they call the read-only
:mod:`hvs_lifecycle_release_service`, perform no HVS mutation, no network, no
customer contact, and never infer completion that lacks authoritative evidence.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from .hvs_lifecycle_release_models import LifecycleVerification


def _emit(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False))


def _snapshot_payload(repo_root, project_id: str) -> dict[str, Any]:
    from .hvs_lifecycle_release_service import inspect_lifecycle

    snap = inspect_lifecycle(repo_root=repo_root, project_id=project_id)
    return {
        "ok": True,
        "command": "inspect-hvs-lifecycle",
        "project_id": snap.project_id,
        "current_stage": snap.current_stage,
        "state": snap.state,
        "last_verified_record": snap.last_verified_record,
        "blockers": list(snap.blockers),
        "next_action": snap.next_action,
        "hvs_invoked": snap.hvs_invoked,
        "render_artifact_verified": snap.render_artifact_verified,
        "delivery_occurred": snap.delivery_occurred,
        "customer_outcome_recorded": snap.customer_outcome_recorded,
        "resolution_route_approved": snap.resolution_route_approved,
        "stage8r_target_action_completed": snap.stage8r_target_action_completed,
        "identity_chain": snap.identity_chain,
        "boundary_flags": snap.boundary_flags,
        "stages": [s.__dict__ for s in snap.stages],
    }


def _resolve_repo_root(args: argparse.Namespace):
    if getattr(args, "repo_root", None):
        return args.repo_root
    from .cli import _repo_root

    return _repo_root()


def _cmd_inspect_lifecycle(args: argparse.Namespace) -> int:
    _emit(_snapshot_payload(_resolve_repo_root(args), args.project_id))
    return 0


def _cmd_verify_lifecycle(args: argparse.Namespace) -> int:
    from .hvs_lifecycle_release_service import inspect_lifecycle

    snap = inspect_lifecycle(repo_root=_resolve_repo_root(args), project_id=args.project_id)
    conflicts: list[str] = []
    if snap.state == "CONFLICTED":
        conflicts.append("contradictory_authoritative_records")
    if snap.state == "UNKNOWN" and snap.stages:
        conflicts.append("no_authoritative_records_for_project")
    ok = snap.state in ("READY", "BLOCKED", "COMPLETED") and not conflicts
    result = LifecycleVerification(
        project_id=snap.project_id,
        ok=ok,
        conflicts=tuple(conflicts),
        notes=(f"state={snap.state}", f"next_action={snap.next_action}"),
    )
    _emit({
        "ok": result.ok,
        "command": "verify-hvs-lifecycle",
        "project_id": result.project_id,
        "verified": result.ok,
        "conflicts": list(result.conflicts),
        "notes": list(result.notes),
        "state": snap.state,
    })
    return 0 if result.ok else 1


def _cmd_inspect_next_action(args: argparse.Namespace) -> int:
    from .hvs_lifecycle_release_service import inspect_lifecycle

    snap = inspect_lifecycle(repo_root=_resolve_repo_root(args), project_id=args.project_id)
    _emit({
        "ok": True,
        "command": "inspect-hvs-next-action",
        "project_id": snap.project_id,
        "current_stage": snap.current_stage,
        "state": snap.state,
        "next_action": snap.next_action,
        "blockers": list(snap.blockers),
    })
    return 0


def register(sub: argparse._SubParsersAction) -> None:  # type: ignore[name-defined]
    """Register the three read-only lifecycle commands into the CLI parser."""

    def _add(name: str, help_text: str, handler):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--project-id", required=True, help="SCOS project id to inspect")
        p.add_argument("--repo-root", dest="repo_root", default=None,
                       help="override SCOS repo root (testing)")
        p.set_defaults(func=handler)

    _add("inspect-hvs-lifecycle",
         "Read-only full lifecycle view (state, blockers, next action, IDs, hashes).",
         _cmd_inspect_lifecycle)
    _add("verify-hvs-lifecycle",
         "Non-mutating cross-stage consistency verification (fail-closed).",
         _cmd_verify_lifecycle)
    _add("inspect-hvs-next-action",
         "Expose exactly one allowed next operator action (read-only).",
         _cmd_inspect_next_action)
