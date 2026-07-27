"""SCOS Cohort 10I — regression tests for paid-pilot CLI audit + restore-drill.

These tests lock in the operator-truth contract verified by the R1 read-only
review:

  D1  The browser readiness route must surface the AUTHORITATIVE Python
      projection (never derived client-side). Covered by the bridge/route
      tests in apps/control-center; here we assert the CLI emits the
      projection with the correct keys so the bridge can forward it.
  D2  The restore drill must append a durable RESTORE_VERIFIED audit event so
      readiness can reach READY_FOR_CONTROLLED_PILOT.
  D3  Every authoritative transition (rights/qa/approve/package) must write an
      append-only audit event (no silent drop).

The flow is driven through the real CLI entrypoint (subprocess) to mirror the
Next.js bridge path exactly.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON = Path(sys.executable)
CLI = "scos.control_center.hvs_paid_pilot_delivery_cli"


def _cli(store_path: Path, operation: str, **kw):
    payload = {"store_path": str(store_path), **kw}
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT), "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.run(
        [str(PYTHON), "-m", CLI, operation],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert proc.returncode in (0, 1), f"{operation} crashed: {proc.stderr[-500:]}"
    return json.loads(proc.stdout.strip() or "{}")


def _audit_events(audit_path: Path):
    if not audit_path.is_file():
        return []
    out = []
    for line in audit_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


@pytest.fixture
def env(tmp_path: Path):
    store = tmp_path / "paid-pilot-delivery-v1.json"
    artifact = tmp_path / "artifact.mp4"
    artifact.write_bytes(b"SCOS-COHORT-10I-AUDIT-RESTORE-DRILL-" * 200)
    sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    did = "scos-hvs-pp-delivery-cli-regression"
    return {
        "store": store,
        "artifact": artifact,
        "sha": sha,
        "did": did,
        "audit": store.parent / "paid-pilot-audit-v1.jsonl",
    }


def test_cli_writes_audit_on_every_transition_and_reaches_controlled_pilot(env):
    did = env["did"]
    sha = env["sha"]

    # Drive the authoritative transition chain via the real CLI entrypoint.
    _cli(env["store"], "rights-review", delivery_id=did, project_id="p", operator_id="op",
         reviewed_at="t", entries=[{"asset_kind": "video", "description": "d",
         "known_source": True, "permitted": True}], attestation="x")
    _cli(env["store"], "qa", delivery_id=did, qa_report_id="qa1", qa_state="QA_PASSED",
         artifact_id="a1", artifact_sha256=sha, recorded_at="t")
    _cli(env["store"], "approve", delivery_id=did, operator_id="op", decided_at="t",
         decision="APPROVED_FOR_DELIVERY", source_render_attempt_id="att1",
         artifact_identity="a1", artifact_sha256=sha, artifact_size=env["artifact"].stat().st_size,
         media_profile="vertical_9_16", qa_record_id="qa1", qa_state="QA_PASSED",
         rights_revision="r1", rights_status="RIGHTS_APPROVED", recorded_at="t")
    pkg = _cli(env["store"], "create-package", delivery_id=did, project_id="p",
               hvs_project_id="h", attempt_id="att1", profile_id="vertical_9_16",
               qa_report_id="qa1", artifact_path=str(env["artifact"]), operator_id="op",
               recorded_at="t", rights_revision="r1", rights_status="RIGHTS_APPROVED")
    assert pkg["ok"] is True
    pkg_sha = pkg["package_sha256"]

    # D3: every transition wrote an append-only audit event (4 so far).
    events = _audit_events(env["audit"])
    types = [e["event_type"] for e in events]
    assert "RIGHTS_REVIEWED" in types
    assert "QA_APPLIED" in types
    assert "DELIVERY_APPROVED" in types
    assert "PACKAGE_CREATED" in types
    # No absolute local paths / secrets leaked into the audit.
    blob = env["audit"].read_text(encoding="utf-8")
    assert "C:" not in blob and "http://" not in blob and "https://" not in blob

    # Pre-restore: ready for internal rehearsal, but restore drill not yet done.
    pre = _cli(env["store"], "readiness", delivery_id=did)
    assert pre["readiness_state"] == "READY_FOR_INTERNAL_REHEARSAL"
    # The restore-drill check reflects the not-yet-verified state (no hard blocker).
    restore_check = next(c for c in pre["checks"] if c["name"] == "restore_drill")
    assert restore_check["passed"] is False
    assert restore_check["reason_code"] == "RESTORE_NOT_VERIFIED"

    # Restore drill into a fresh root with the package sha256.
    restore_root = env["store"].parent / "restore"
    res = _cli(env["store"], "restore", delivery_id=did, restore_root=str(restore_root),
               expected_package_sha256=pkg_sha)
    assert res["ok"] is True

    # D2: restore drill appended a durable RESTORE_VERIFIED audit event.
    events = _audit_events(env["audit"])
    types = [e["event_type"] for e in events]
    assert "RESTORE_VERIFIED" in types  # exactly one per successful drill

    # Post-restore: readiness now reaches READY_FOR_CONTROLLED_PILOT.
    post = _cli(env["store"], "readiness", delivery_id=did)
    assert post["readiness_state"] == "READY_FOR_CONTROLLED_PILOT"
    assert post["blocking_reasons"] == []

    # D1: the authoritative projection is emitted with the keys the bridge
    # forwards (so the browser never derives readiness itself).
    assert post["record"] is not None
    assert set(post.keys()) >= {"readiness_state", "checks", "blocking_reasons",
                                 "package_sha256", "backup_sha256", "audit_sha256"}


def test_cli_restore_rejects_non_empty_root_fail_closed(env):
    did = env["did"]
    sha = env["sha"]
    _cli(env["store"], "rights-review", delivery_id=did, project_id="p", operator_id="op",
         reviewed_at="t", entries=[{"asset_kind": "video", "description": "d",
         "known_source": True, "permitted": True}], attestation="x")
    _cli(env["store"], "qa", delivery_id=did, qa_report_id="qa1", qa_state="QA_PASSED",
         artifact_id="a1", artifact_sha256=sha, recorded_at="t")
    _cli(env["store"], "approve", delivery_id=did, operator_id="op", decided_at="t",
         decision="APPROVED_FOR_DELIVERY", source_render_attempt_id="att1",
         artifact_identity="a1", artifact_sha256=sha, artifact_size=env["artifact"].stat().st_size,
         media_profile="vertical_9_16", qa_record_id="qa1", qa_state="QA_PASSED",
         rights_revision="r1", rights_status="RIGHTS_APPROVED", recorded_at="t")
    pkg = _cli(env["store"], "create-package", delivery_id=did, project_id="p",
               hvs_project_id="h", attempt_id="att1", profile_id="vertical_9_16",
               qa_report_id="qa1", artifact_path=str(env["artifact"]), operator_id="op",
               recorded_at="t", rights_revision="r1", rights_status="RIGHTS_APPROVED")
    pkg_sha = pkg["package_sha256"]

    restore_root = env["store"].parent / "restore-populated"
    restore_root.mkdir(parents=True, exist_ok=True)
    (restore_root / "stray.txt").write_text("not empty")

    res = _cli(env["store"], "restore", delivery_id=did, restore_root=str(restore_root),
               expected_package_sha256=pkg_sha)
    assert res["ok"] is False
    assert res["error_code"] == "RESTORE_ROOT_NOT_EMPTY"
    # No RESTORE_VERIFIED appended for a failed drill.
    types = [e["event_type"] for e in _audit_events(env["audit"])]
    assert "RESTORE_VERIFIED" not in types
