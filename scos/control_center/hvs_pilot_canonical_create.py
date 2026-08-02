"""Canonical paid-pilot project creation orchestrator (bridge for §6.E/§6.F).

Connects the already-implemented authorities into one authoritative browser
journey:

    valid packet admission (hvs_pilot_packet_admission)
      -> canonical spp-* identity (hvs_pilot_identity)
      -> HVS project directory (task-owned)
      -> packet-faithful materialization (hvs_pilot_materialization)
      -> (read-only render-readiness is verified separately, post-create)

This module is the SINGLE writer for the canonical project. It is invoked
server-side only; the browser never supplies filesystem paths. The
``project_ref`` is taken from the durable admission record, never from a
browser body.

No render authorization, no renderer invocation, no external egress.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .hvs_pilot_identity import IdentityStore, build_mapping, derive_canonical_id
from .hvs_pilot_materialization import build_materialization_state


def _load_admission(admission_store_path: str) -> dict[str, Any]:
    p = Path(admission_store_path)
    if not p.is_file():
        raise ValueError("NO_ADMISSION_RECORD")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise ValueError(f"ADMISSION_UNREADABLE:{e}")


def _load_packet(packet_path: str) -> dict[str, Any]:
    p = Path(packet_path)
    if not p.is_file():
        raise ValueError("PACKET_NOT_FOUND")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        raise ValueError(f"PACKET_UNREADABLE:{e}")


def create_canonical_project(
    *,
    admission_store_path: str,
    identity_store_path: str,
    materialization_store_path: str,
    hvs_projects_root: str,
    output_root: str,
    contracts_dir: str,
    packet_path: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """Create exactly one canonical project from an admitted packet.

    Returns a browser-safe result. Fails closed on any gate failure.
    """
    # 1. Admission must exist (gate: PACKET_ADMISSION).
    admission = _load_admission(admission_store_path)
    project_ref = admission.get("project_ref")
    pilot_id = admission.get("pilot_id")
    customer_ref = admission.get("customer_ref")
    packet_sha256 = admission.get("packet_sha256")
    if not (project_ref and pilot_id and customer_ref):
        return {"ok": False, "error_code": "ADMISSION_INCOMPLETE",
                "detail": "admission record missing required identity fields"}

    # 2. Canonical identity (exact replay -> no second write; conflict -> fail closed).
    canonical_id = derive_canonical_id(project_ref)
    mapping = build_mapping(
        external_project_ref=project_ref,
        pilot_id=pilot_id,
        customer_ref=customer_ref,
        packet_sha256=packet_sha256 or "",
    )
    store = IdentityStore(Path(identity_store_path))
    wrote_new, conflict = store.persist(mapping)
    if conflict:
        return {"ok": False, "error_code": "CONFLICTING_IDENTITY_REPLAY",
                "detail": "canonical identity already mapped to a different record",
                "canonical_internal_project_id": canonical_id}
    if not wrote_new:
        # Exact replay: same external project_ref already mapped to the same
        # canonical identity. No second write (fail-closed by construction).
        return {"ok": True, "replay": True, "canonical_internal_project_id": canonical_id,
                "pilot_safe_id": canonical_id, "project_safe_id": canonical_id,
                "admission_packet_sha256": packet_sha256,
                "next_safe_action": "Review technical evidence; no render/delivery is authorized."}

    # 3. HVS project directory (task-owned, canonical id).
    hvs_root = Path(hvs_projects_root)
    proj_dir = hvs_root / canonical_id
    try:
        proj_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return {"ok": False, "error_code": "HVS_PROJECT_DIR_CREATE_FAILED",
                "detail": f"could not create project directory: {e}",
                "canonical_internal_project_id": canonical_id}

    # 4. Packet-faithful materialization (writes materialization state + contract).
    try:
        packet = _load_packet(packet_path)
        mat_projection = build_materialization_state(
            canonical_internal_project_id=canonical_id,
            external_project_ref=project_ref,
            pilot_id=pilot_id,
            customer_ref=customer_ref,
            packet=packet,
            materialization_store_path=materialization_store_path,
            contracts_dir=contracts_dir,
        )
    except ValueError as e:
        return {"ok": False, "error_code": "MATERIALIZATION_FAILED",
                "detail": str(e), "canonical_internal_project_id": canonical_id}
    except Exception as e:
        return {"ok": False, "error_code": "MATERIALIZATION_ERROR",
                "detail": f"materialization error: {e}",
                "canonical_internal_project_id": canonical_id}

    return {
        "ok": True,
        "replay": False,
        "canonical_internal_project_id": canonical_id,
        "pilot_safe_id": canonical_id,
        "project_safe_id": canonical_id,
        "external_project_ref": project_ref,
        "admission_packet_sha256": packet_sha256,
        "materialization": mat_projection,
        "next_safe_action": "Review technical evidence; no render/delivery is authorized.",
    }
