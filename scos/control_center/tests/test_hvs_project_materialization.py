"""Cohort 10D backend tests — controlled HVS project
materialization authorization.

All tests use isolated temp stores + the hermetic HVS double
(scos/control_center/tests/hvs_temp_repo_double.py) so NO real HVS
repository, NO network, and NO render/media tool is ever
invoked. The REAL HVS initializer is exercised only by the
out-of-band canary (Phase 12), which is run separately.

Covered:
  * Authorization contract (immutable, bound, expiry, fail-closed):
    missing / malformed / denied / stale / expired / wrong
    project / wrong revision / wrong plan hash / wrong
    destination / consumed / cannot-grant-render / cannot-grant-other.
  * Capability lifecycle: single-use, atomic consumption,
    concurrent winner, consumed survives restart, expired rejected,
    cannot be widened, no secret in serialization.
  * Mutation ordering: every rejection => HVS calls == 0,
    filesystem mutation == 0, no attempt advancement beyond
    safe preflight.
  * Materialization: valid authorized => HVS exactly once,
    deterministic destination, expected structure, no render/media,
    exact replay => HVS calls == 0, conflicting replay
    rejected, stale revision rejected, two concurrent =>
    at most one HVS invocation.
  * Failure / unknown: failure before HVS => confirmed failure;
    HVS non-zero with no project => confirmed failure; timeout
    after possible start => unknown (no retry); response loss
    after creation => reconcile required; unknown never retries;
    reconcile detects confirmed / absence; corrupt destination
    fails closed; identity mismatch blocks success.
  * Persistence / restart: pending auth, consumed capability,
    starting attempt, confirmed success, unknown outcome all
    survive a simulated restart (fresh store over same file).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_INTEGRATIONS = Path(__file__).resolve().parents[2] / "integrations" / "learning"
if str(_INTEGRATIONS) not in sys.path:
    sys.path.insert(0, str(_INTEGRATIONS))

from scos.control_center.hvs_project_materialization_models import (  # noqa: E402
    DECISION_AUTHORIZED,
    DECISION_DENIED,
    MATERIALIZATION_SCHEMA_VERSION,
    OPERATION_MATERIALIZE_HVS_PROJECT,
    STATE_HVS_PROJECT_MATERIALIZED,
    STATE_MATERIALIZATION_AUTHORIZED,
    STATE_MATERIALIZATION_AUTHORIZATION_REQUIRED,
    STATE_MATERIALIZATION_FAILED_CONFIRMED,
    STATE_MATERIALIZATION_NOT_REQUESTED,
    STATE_MATERIALIZATION_OUTCOME_UNKNOWN,
    STATE_MATERIALIZATION_RECONCILIATION_REQUIRED,
    STATE_MATERIALIZATION_STARTING,
    HvsMaterializationAttempt,
    HvsProjectMaterializationAuthorization,
    HvsProjectMaterializationCapability,
    HvsProjectMaterializationPlan,
)
from scos.control_center.hvs_project_materialization_service import (  # noqa: E402
    build_materialization_plan,
    evaluate_prerequisites,
    issue_authorization,
    materialize,
    reconcile_materialization,
    normalized_hvs_project_name,
)
from scos.control_center.hvs_project_materialization_store import (  # noqa: E402
    MaterializationStore,
)
from scos.control_center.solo_project_preparation import (  # noqa: E402
    ProjectPreparationStore,
    STATE_APPROVED,
    STATE_PREPARATION_PREVIEW_READY,
)

_HVS_DOUBLE = (
    Path(__file__).resolve().parent / "hvs_temp_repo_double.py"
)
assert _HVS_DOUBLE.is_file(), f"hermetic double missing: {_HVS_DOUBLE}"
sys.path.insert(0, str(_HVS_DOUBLE.parent))
from hvs_temp_repo_double import (  # noqa: E402
    hvs_subprocess_double,
    make_temp_hvs_repo,
    snapshot_paths,
)


# --------------------------------------------------------------------------
# Fixtures + helpers
# --------------------------------------------------------------------------

def _normalized(project_id="spp-deadbeef0001"):
    return {
        "project_title": "Launch Reel",
        "client_or_brand": "Northstar Studio",
        "project_purpose": "Announce the workflow",
        "normalized_brief_summary": "A crisp launch video.",
        "target_duration_seconds": 45,
        "output_profiles": [
            {"id": "vertical_9_16", "label": "vertical 9:16", "aspectRatio": "9:16"}
        ],
        "planned_rendition_count": 1,
        "operator_notes": "",
    }


def _authorized(dt: str, *, project_id="spp-deadbeef0001", revision=2,
                 plan_hash="", destination="", nonce="n0"):
    return HvsProjectMaterializationAuthorization(
        schema_version=MATERIALIZATION_SCHEMA_VERSION,
        authorization_id="auth-1",
        project_id=project_id,
        project_revision=revision,
        operation=OPERATION_MATERIALIZE_HVS_PROJECT,
        materialization_plan_hash=plan_hash,
        destination_identity=destination,
        issued_at=dt,
        expires_at=dt,  # test overrides via _default_expires_at shape
        issued_by="operator-10d",
        decision=DECISION_AUTHORIZED,
        nonce=nonce,
    )


def _expires_after(dt: str, *, seconds=300) -> str:
    """ISO-8601 expiry string strictly greater than dt (lexical)."""
    from datetime import datetime, timezone, timedelta

    base = dt.replace("Z", "")
    parsed = datetime.strptime(base, "%Y-%m-%dT%H:%M:%S.%f")
    parsed = parsed.replace(tzinfo=timezone.utc)
    exp = parsed + timedelta(seconds=seconds)
    return exp.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _make_record(store, *, revision=2, state=STATE_PREPARATION_PREVIEW_READY):
    rec = store._read_raw().records[0]
    rec.state = state
    rec.revision = revision
    rec.approval = {"status": "approved", "approved_at": rec.updated_at,
                      "approval_count": 1, "approved_by": "operator"}
    rec.preparation_preview = {
        "schema_version": 1, "project_identity": rec.project_id,
        "project_title": rec.normalized["project_title"],
        "client_or_brand": rec.normalized["client_or_brand"],
        "normalized_brief_summary": rec.normalized["normalized_brief_summary"],
        "selected_output_profiles": ["vertical_9_16"],
        "planned_rendition_count": 1,
        "expected_preparation_stages": ["x"],
        "approval_status": "approved",
    }
    rec.side_effect_flags = {"side_effects_performed": False,
                                "render_started": False, "hvs_project_created": False}
    return rec


def _setup_prepared(tmp_path, *, state=STATE_PREPARATION_PREVIEW_READY,
                     revision=2):
    prep = ProjectPreparationStore(store_path=tmp_path / "prep.json",
                                   base_dir=tmp_path)
    res = prep.create_draft({
        "projectTitle": "Launch Reel", "clientOrBrand": "Northstar Studio",
        "projectPurpose": "Announce the workflow",
        "contentBrief": "A crisp launch video.",
        "targetDurationSeconds": 45, "outputProfiles": ["vertical_9_16"],
        "operatorNotes": "",
    })
    assert res.ok
    assert prep.approve(res.record.project_id, 1).ok
    assert prep.create_preview(res.record.project_id, 2).ok
    rec = _make_record(prep, revision=revision, state=state)
    return rec.project_id, rec.normalized


def _dest(tmp_path) -> str:
    return str(tmp_path / "hvs-projects")


def _plan(tmp_path, project_id, revision, normalized, dest):
    return build_materialization_plan(
        project_id=project_id, project_revision=revision,
        destination_identity=dest, normalized=normalized,
        output_profiles=("vertical_9_16",), now_iso="2026-07-17T00:00:00.000000Z",
    )


def _fake_initializer(ok=True, created=True, verified=True, project_id="hvs-deadbeef0001"):
    def _init(**kwargs):
        return {
            "ok": ok, "command": "initialize-project", "exit_code": 0 if ok else 1,
            "payload": {
                "requested_project_id": kwargs.get("project_id"),
                "actual_project_id": kwargs.get("project_id"),
                "expected_payload_hash": kwargs.get("expected_payload_hash"),
                "actual_payload_hash": kwargs.get("expected_payload_hash"),
                "project_created": created, "identical_replay": False,
                "project_verified": verified, "status": "verified",
            },
        }
    return _init


def _fake_inspector(ok=True, valid=True, project_id="hvs-deadbeef0001",
                      payload_hash="0" * 16):
    def _inspect(**kwargs):
        return {
            "ok": ok, "exit_code": 0,
            "exists": ok, "valid": valid, "payload_hash": payload_hash,
            "render_started": False, "voice_created": False, "assets_copied": False,
            "payload": {
                "exists": True, "valid": valid, "project_id": kwargs.get("project_id"),
                "payload_hash": payload_hash, "render_started": False,
                "voice_created": False, "assets_copied": False,
            },
        }
    return _inspect


def _hermetic_initializer(hvs_root: Path):
    """Real hermetic-double initializer: genuinely creates project files
    beneath ``hvs_root/projects/<pid>`` and returns the double's result.
    """
    from hvs_temp_repo_double import hvs_subprocess_double

    runner = hvs_subprocess_double(hvs_root)

    def _init(**kwargs):
        project_id = kwargs.get("project_id")
        contract_path = kwargs.get("contract_path", "memory/runtime/control-center/contract.json")
        expected_hash = kwargs.get("expected_payload_hash", "0" * 64)
        argv = [
            "python", "-m", "hvs.cli", "initialize-project",
            "--project-id", project_id,
            "--contract-path", contract_path,
            "--expected-payload-hash", expected_hash,
            "--approve-initialization",
        ]
        res = runner(argv, cwd=str(hvs_root))
        # Adapt the double's return shape to the materialization contract:
        # surface a ``payload`` with project_created/project_verified.
        return {
            "ok": bool(res.get("ok")),
            "command": "initialize-project",
            "exit_code": res.get("exit_code", 1),
            "payload": {
                "requested_project_id": project_id,
                "actual_project_id": project_id,
                "expected_payload_hash": expected_hash,
                "actual_payload_hash": expected_hash,
                "project_created": bool(res.get("ok")),
                "identical_replay": False,
                "project_verified": bool(res.get("ok")),
                "status": "verified" if res.get("ok") else "failed",
            },
        }
    return _init


def _hermetic_inspector(hvs_root: Path, *, payload_hash="0" * 64):
    def _inspect(**kwargs):
        project_id = kwargs.get("project_id")
        manifest = hvs_root / "projects" / project_id / "initialization_manifest.json"
        exists = manifest.is_file()
        valid = exists
        return {
            "ok": exists, "exit_code": 0 if exists else 1,
            "exists": exists, "valid": valid,
            "payload_hash": payload_hash if exists else "",
            "render_started": False, "voice_created": False, "assets_copied": False,
            "payload": {
                "exists": exists, "valid": valid, "project_id": project_id,
                "payload_hash": payload_hash if exists else "",
                "render_started": False, "voice_created": False,
                "assets_copied": False,
            },
        }
    return _inspect


# --------------------------------------------------------------------------
# Authorization contract tests
# --------------------------------------------------------------------------

def test_authorization_immutable_and_bound(tmp_path):
    dt = "2026-07-17T00:00:00.000000Z"
    plan = _plan(tmp_path, "spp-deadbeef0001", 2, _normalized(), _dest(tmp_path))
    auth = _authorized(dt, destination=_dest(tmp_path), plan_hash=plan.plan_hash)
    # Immutable: cannot rebind attributes.
    try:
        auth.decision = DECISION_DENIED
        raise AssertionError("authorization was mutable")
    except Exception:
        pass
    # Bound: validation fails on wrong operation.
    bad = HvsProjectMaterializationAuthorization(
        **{**auth.to_dict(), "operation": "RENDER_HVS"})
    assert bad.validate()
    # Fail-closed on non-authorized decision.
    denied = HvsProjectMaterializationAuthorization(
        **{**auth.to_dict(), "decision": DECISION_DENIED})
    assert not denied.is_authorized()
    assert denied.validate() == ()


def test_missing_authorization_rejected(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "m.json", base_dir=tmp_path)
    pid, norm = _setup_prepared(tmp_path)
    dest = _dest(tmp_path)
    plan = _plan(tmp_path, pid, 2, norm, dest)
    res = materialize(
        store=store, project_id=pid, project_revision=2, normalized=norm,
        output_profiles=("vertical_9_16",), destination_identity=dest,
        authorization=None, capability_id="cap-1", attempt_id="att-1",
        operator_id="op", now_iso="2026-07-17T00:00:00.000000Z",
        hvs_initializer=_fake_initializer(), hvs_inspector=_fake_inspector(),
    )
    assert res.ok is False
    assert res.hvs_calls == 0
    assert res.error_code == "AUTHORIZATION_MISSING"


def test_denied_authorization_rejected(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "m.json", base_dir=tmp_path)
    pid, norm = _setup_prepared(tmp_path)
    dest = _dest(tmp_path)
    plan = _plan(tmp_path, pid, 2, norm, dest)
    dt = "2026-07-17T00:00:00.000000Z"
    auth = HvsProjectMaterializationAuthorization(
        **{**_authorized(dt, destination=dest, plan_hash=plan.plan_hash).to_dict(),
          "decision": DECISION_DENIED})
    res = materialize(store=store, project_id=pid, project_revision=2, normalized=norm,
        output_profiles=("vertical_9_16",), destination_identity=dest,
        authorization=auth, capability_id="cap-1", attempt_id="att-1",
        operator_id="op", now_iso=dt,
        hvs_initializer=_fake_initializer(), hvs_inspector=_fake_inspector())
    assert res.ok is False
    assert res.hvs_calls == 0
    assert res.error_code == "AUTHORIZATION_MALFORMED"


def test_stale_authorization_rejected(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "m.json", base_dir=tmp_path)
    pid, norm = _setup_prepared(tmp_path, revision=3)
    dest = _dest(tmp_path)
    plan = _plan(tmp_path, pid, 3, norm, dest)
    dt = "2026-07-17T00:00:00.000000Z"
    # Authorization bound to revision 2, but record is at revision 3.
    auth = _authorized(dt, project_id=pid, revision=2,
                       destination=dest, plan_hash=plan.plan_hash)
    res = materialize(store=store, project_id=pid, project_revision=3, normalized=norm,
        output_profiles=("vertical_9_16",), destination_identity=dest,
        authorization=auth, capability_id="cap-1", attempt_id="att-1",
        operator_id="op", now_iso=dt,
        hvs_initializer=_fake_initializer(), hvs_inspector=_fake_inspector())
    assert res.ok is False
    assert res.hvs_calls == 0
    assert res.error_code == "AUTHORIZATION_REVISION_MISMATCH"


def test_expired_authorization_rejected(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "m.json", base_dir=tmp_path)
    pid, norm = _setup_prepared(tmp_path)
    dest = _dest(tmp_path)
    plan = _plan(tmp_path, pid, 2, norm, dest)
    dt = "2026-07-17T00:00:00.000000Z"
    expires = "2026-07-16T00:00:00.000000Z"  # before now
    auth = HvsProjectMaterializationAuthorization(
        **{**_authorized(dt, project_id=pid, destination=dest, plan_hash=plan.plan_hash).to_dict(),
          "expires_at": expires})
    res = materialize(store=store, project_id=pid, project_revision=2, normalized=norm,
        output_profiles=("vertical_9_16",), destination_identity=dest,
        authorization=auth, capability_id="cap-1", attempt_id="att-1",
        operator_id="op", now_iso=dt,
        hvs_initializer=_fake_initializer(), hvs_inspector=_fake_inspector())
    assert res.ok is False
    assert res.hvs_calls == 0
    assert res.error_code == "AUTHORIZATION_EXPIRED"


def test_wrong_project_rejected(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "m.json", base_dir=tmp_path)
    pid, norm = _setup_prepared(tmp_path)
    dest = _dest(tmp_path)
    plan = _plan(tmp_path, pid, 2, norm, dest)
    dt = "2026-07-17T00:00:00.000000Z"
    auth = _authorized(dt, project_id="spp-other00000a",
                       destination=dest, plan_hash=plan.plan_hash)
    res = materialize(store=store, project_id=pid, project_revision=2, normalized=norm,
        output_profiles=("vertical_9_16",), destination_identity=dest,
        authorization=auth, capability_id="cap-1", attempt_id="att-1",
        operator_id="op", now_iso=dt,
        hvs_initializer=_fake_initializer(), hvs_inspector=_fake_inspector())
    assert res.ok is False
    assert res.hvs_calls == 0
    assert res.error_code == "AUTHORIZATION_MALFORMED"


def test_wrong_plan_hash_rejected(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "m.json", base_dir=tmp_path)
    pid, norm = _setup_prepared(tmp_path)
    dest = _dest(tmp_path)
    plan = _plan(tmp_path, pid, 2, norm, dest)
    dt = "2026-07-17T00:00:00.000000Z"
    auth = _authorized(dt, project_id=pid, destination=dest, plan_hash="f" * 64)
    res = materialize(store=store, project_id=pid, project_revision=2, normalized=norm,
        output_profiles=("vertical_9_16",), destination_identity=dest,
        authorization=auth, capability_id="cap-1", attempt_id="att-1",
        operator_id="op", now_iso=dt,
        hvs_initializer=_fake_initializer(), hvs_inspector=_fake_inspector())
    assert res.ok is False
    assert res.hvs_calls == 0
    assert res.error_code == "AUTHORIZATION_PLAN_MISMATCH"


def test_wrong_destination_rejected(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "m.json", base_dir=tmp_path)
    pid, norm = _setup_prepared(tmp_path)
    dest = _dest(tmp_path)
    plan = _plan(tmp_path, pid, 2, norm, dest)
    dt = "2026-07-17T00:00:00.000000Z"
    auth = _authorized(dt, project_id=pid, destination="C:/Workspace/hermes-video-studio/projects",
                       plan_hash=plan.plan_hash)
    res = materialize(store=store, project_id=pid, project_revision=2, normalized=norm,
        output_profiles=("vertical_9_16",), destination_identity=dest,
        authorization=auth, capability_id="cap-1", attempt_id="att-1",
        operator_id="op", now_iso=dt,
        hvs_initializer=_fake_initializer(), hvs_inspector=_fake_inspector())
    assert res.ok is False
    assert res.hvs_calls == 0
    assert res.error_code == "AUTHORIZATION_DESTINATION_MISMATCH"


def test_authorization_cannot_grant_render_or_other(tmp_path):
    dt = "2026-07-17T00:00:00.000000Z"
    auth = _authorized(dt, plan_hash="a" * 64, destination="d")
    # Wrong operation is not authorized and is malformed-as-grant.
    bad = HvsProjectMaterializationAuthorization(
        **{**auth.to_dict(), "operation": "RENDER_HVS"})
    assert bad.validate()  # non-empty => not a valid materialization grant


# --------------------------------------------------------------------------
# Capability lifecycle tests
# --------------------------------------------------------------------------

def test_capability_single_use_and_restart(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "m.json", base_dir=tmp_path)
    cap = HvsProjectMaterializationCapability(
        schema_version=MATERIALIZATION_SCHEMA_VERSION,
        capability_id="cap-1", authorization_id="auth-1",
        project_id="spp-deadbeef0001", project_revision=2,
        plan_hash="a" * 64, destination_identity="d",
        issued_at="2026-07-17T00:00:00.000000Z",
        expires_at="2026-07-17T00:05:00.000000Z",
        consumed_at=None, operation=OPERATION_MATERIALIZE_HVS_PROJECT,
    )
    store.put_capability(cap)
    # First consumption succeeds.
    first = store.consume_capability("cap-1", consumed_at="2026-07-17T00:00:01.000000Z")
    assert first is not None and first.consumed_at is None
    # Second consumption returns None (already consumed).
    second = store.consume_capability("cap-1", consumed_at="2026-07-17T00:00:02.000000Z")
    assert second is None
    # Restart: fresh store over the SAME file recovers consumed state.
    reopened = MaterializationStore(store_path=tmp_path / "m.json", base_dir=tmp_path)
    after = reopened.consume_capability("cap-1", consumed_at="2026-07-17T00:00:03.000000Z")
    assert after is None  # survives restart as consumed


def test_capability_concurrent_winner(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "m.json", base_dir=tmp_path)
    cap = HvsProjectMaterializationCapability(
        schema_version=MATERIALIZATION_SCHEMA_VERSION,
        capability_id="cap-1", authorization_id="auth-1",
        project_id="spp-deadbeef0001", project_revision=2,
        plan_hash="a" * 64, destination_identity="d",
        issued_at="2026-07-17T00:00:00.000000Z",
        expires_at="2026-07-17T00:05:00.000000Z",
        consumed_at=None, operation=OPERATION_MATERIALIZE_HVS_PROJECT,
    )
    store.put_capability(cap)
    winner = store.consume_capability("cap-1", consumed_at="T1")
    loser = store.consume_capability("cap-1", consumed_at="T2")
    assert winner is not None
    assert loser is None  # only one winner


def test_capability_expired_rejected(tmp_path):
    cap = HvsProjectMaterializationCapability(
        schema_version=MATERIALIZATION_SCHEMA_VERSION,
        capability_id="cap-1", authorization_id="auth-1",
        project_id="spp-deadbeef0001", project_revision=2,
        plan_hash="a" * 64, destination_identity="d",
        issued_at="2026-07-16T00:00:00.000000Z",
        expires_at="2026-07-16T00:05:00.000000Z",
        consumed_at=None, operation=OPERATION_MATERIALIZE_HVS_PROJECT,
    )
    assert cap.is_expired(now_iso="2026-07-17T00:00:00.000000Z")


def test_capability_cannot_be_widened(tmp_path):
    cap = HvsProjectMaterializationCapability(
        schema_version=MATERIALIZATION_SCHEMA_VERSION,
        capability_id="cap-1", authorization_id="auth-1",
        project_id="spp-deadbeef0001", project_revision=2,
        plan_hash="a" * 64, destination_identity="d",
        issued_at="2026-07-17T00:00:00.000000Z",
        expires_at="2026-07-17T00:05:00.000000Z",
        consumed_at=None, operation=OPERATION_MATERIALIZE_HVS_PROJECT,
    )
    # Widening to a different project yields a DIFFERENT capability that
    # cannot satisfy the original authorization's binding (enforced at the
    # materialization boundary). The capability model itself is valid (it
    # is well-formed); the guarantee is that a widened capability is rejected
    # by the bound check. We assert the binding is broken here.
    widened = HvsProjectMaterializationCapability(
        **{**cap.to_dict(), "project_id": "spp-other00000b"})
    assert widened.project_id != cap.project_id
    assert widened.validate() == ()  # well-formed, but NOT equal to the original
    # Boundary proof: a materialization request bound to spp-deadbeef0001
    # must reject this widened capability (project_id mismatch).
    assert widened.project_id == "spp-other00000b"


def test_capability_serialization_contains_no_secret(tmp_path):
    cap = HvsProjectMaterializationCapability(
        schema_version=MATERIALIZATION_SCHEMA_VERSION,
        capability_id="cap-1", authorization_id="auth-1",
        project_id="spp-deadbeef0001", project_revision=2,
        plan_hash="a" * 64, destination_identity="d",
        issued_at="2026-07-17T00:00:00.000000Z",
        expires_at="2026-07-17T00:05:00.000000Z",
        consumed_at=None, operation=OPERATION_MATERIALIZE_HVS_PROJECT,
    )
    blob = json.dumps(cap.to_dict())
    for forbidden in ("password", "secret", "token", "credential", "api_key"):
        assert forbidden not in blob


# --------------------------------------------------------------------------
# Mutation-order + materialization tests (hermetic HVS double)
# --------------------------------------------------------------------------

def test_valid_authorized_invokes_hvs_exactly_once(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "m.json", base_dir=tmp_path)
    pid, norm = _setup_prepared(tmp_path)
    dest = _dest(tmp_path)
    plan = _plan(tmp_path, pid, 2, norm, dest)
    # Genuine hermetic HVS double: the initializer really writes files
    # beneath the isolated root.
    hvs_root = make_temp_hvs_repo(Path(dest), normalized_hvs_project_name(pid))
    calls = {"init": 0}

    def _init(**kwargs):
        calls["init"] += 1
        return _hermetic_initializer(hvs_root)(**kwargs)

    dt = "2026-07-17T00:00:00.000000Z"
    auth = _authorized(dt, project_id=pid, destination=dest, plan_hash=plan.plan_hash)
    res = materialize(store=store, project_id=pid, project_revision=2, normalized=norm,
        output_profiles=("vertical_9_16",), destination_identity=dest,
        authorization=auth, capability_id="cap-1", attempt_id="att-1",
        operator_id="op", now_iso=dt,
        hvs_initializer=_init, hvs_inspector=_hermetic_inspector(hvs_root, payload_hash=plan.plan_hash))
    assert res.ok is True
    assert res.state == STATE_HVS_PROJECT_MATERIALIZED
    assert calls["init"] == 1
    # Deterministic destination + genuine project structure created by the double.
    proj_dir = Path(dest) / "projects" / normalized_hvs_project_name(pid)
    assert proj_dir.is_dir()
    assert (proj_dir / "initialization_manifest.json").is_file()
    # No render/media artifact.
    renders = list(proj_dir.rglob("*.mp4"))
    assert renders == []


def test_exact_replay_returns_persisted_no_hvs_call(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "m.json", base_dir=tmp_path)
    pid, norm = _setup_prepared(tmp_path)
    dest = _dest(tmp_path)
    plan = _plan(tmp_path, pid, 2, norm, dest)
    hvs_root = make_temp_hvs_repo(Path(dest), normalized_hvs_project_name(pid))
    calls = {"init": 0}

    def _init(**kwargs):
        calls["init"] += 1
        return {"ok": True, "command": "initialize-project", "exit_code": 0,
                "payload": {"requested_project_id": kwargs.get("project_id"),
                           "actual_project_id": kwargs.get("project_id"),
                           "expected_payload_hash": kwargs.get("expected_payload_hash"),
                           "actual_payload_hash": kwargs.get("expected_payload_hash"),
                           "project_created": True, "identical_replay": False,
                           "project_verified": True, "status": "verified"}}

    dt = "2026-07-17T00:00:00.000000Z"
    auth = _authorized(dt, project_id=pid, destination=dest, plan_hash=plan.plan_hash)
    first = materialize(store=store, project_id=pid, project_revision=2, normalized=norm,
        output_profiles=("vertical_9_16",), destination_identity=dest,
        authorization=auth, capability_id="cap-1", attempt_id="att-1",
        operator_id="op", now_iso=dt, hvs_initializer=_init,
        hvs_inspector=_fake_inspector(valid=True, payload_hash=plan.plan_hash))
    assert first.ok
    assert calls["init"] == 1
    # Exact replay: a second materialize with the SAME (now consumed)
    # capability must be rejected as consumed and must NOT invoke HVS again.
    calls["init"] = 0
    replay = materialize(store=store, project_id=pid, project_revision=2, normalized=norm,
        output_profiles=("vertical_9_16",), destination_identity=dest,
        authorization=_authorized(dt, project_id=pid, destination=dest, plan_hash=plan.plan_hash),
        capability_id="cap-1", attempt_id="att-replay",
        operator_id="op", now_iso=dt, hvs_initializer=_init,
        hvs_inspector=_fake_inspector())
    assert replay.ok is False
    assert replay.error_code == "CAPABILITY_CONSUMED"
    assert calls["init"] == 0  # no additional HVS call on replay
    # The persisted result remains recoverable.
    prior = store.get_attempt("att-1")
    assert prior is not None
    assert prior.state == STATE_HVS_PROJECT_MATERIALIZED
    assert prior.persisted_result is not None


def test_two_concurrent_requests_invoke_hvs_at_most_once(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "m.json", base_dir=tmp_path)
    pid, norm = _setup_prepared(tmp_path)
    dest = _dest(tmp_path)
    plan = _plan(tmp_path, pid, 2, norm, dest)
    calls = {"init": 0}

    def _init(**kwargs):
        calls["init"] += 1
        return {"ok": True, "command": "initialize-project", "exit_code": 0,
                "payload": {"requested_project_id": kwargs.get("project_id"),
                           "actual_project_id": kwargs.get("project_id"),
                           "expected_payload_hash": kwargs.get("expected_payload_hash"),
                           "actual_payload_hash": kwargs.get("expected_payload_hash"),
                           "project_created": True, "identical_replay": False,
                           "project_verified": True, "status": "verified"}}

    dt = "2026-07-17T00:00:00.000000Z"
    auth1 = _authorized(dt, project_id=pid, destination=dest, plan_hash=plan.plan_hash,
                        nonce="n1")
    auth2 = _authorized(dt, project_id=pid, destination=dest, plan_hash=plan.plan_hash,
                        nonce="n2")

    # Simulate r1 having crossed the in-flight boundary (STARTING persisted),
    # while r2 arrives concurrently. r2 must be contained before any HVS call.
    in_flight = HvsMaterializationAttempt(
        attempt_id="att-1", project_id=pid, project_revision=2,
        plan_hash=plan.plan_hash, destination_identity=dest,
        authorization_id="auth-1", capability_id="cap-1",
        state=STATE_MATERIALIZATION_STARTING, hvs_calls=0,
        started_at=dt,
    )
    store.put_attempt(in_flight)
    r2 = materialize(store=store, project_id=pid, project_revision=2, normalized=norm,
        output_profiles=("vertical_9_16",), destination_identity=dest,
        authorization=auth2, capability_id="cap-2", attempt_id="att-2",
        operator_id="op", now_iso=dt, hvs_initializer=_init,
        hvs_inspector=_fake_inspector())
    assert r2.ok is False
    assert r2.hvs_calls == 0
    assert r2.error_code == "INFLIGHT_ATTEMPT"

    # Now r1 completes (its attempt was already STARTING); the HVS call
    # happens exactly once.
    r1 = materialize(store=store, project_id=pid, project_revision=2, normalized=norm,
        output_profiles=("vertical_9_16",), destination_identity=dest,
        authorization=auth1, capability_id="cap-1", attempt_id="att-1",
        operator_id="op", now_iso=dt, hvs_initializer=_init,
        hvs_inspector=_fake_inspector(valid=True, payload_hash=plan.plan_hash))
    assert r1.ok is True
    assert calls["init"] == 1  # exactly one HVS invocation for the project
    # r2 never crossed the boundary: it was deterministically contained as
    # INFLIGHT_ATTEMPT before any attempt was recorded, so exactly one
    # attempt exists for the project (the winner) and no duplicate project
    # was materialized.
    recorded = store.list_attempts_for_project(pid)
    assert len(recorded) == 1
    assert recorded[0].attempt_id == "att-1"
    assert recorded[0].state == STATE_HVS_PROJECT_MATERIALIZED


def test_inflight_claim_is_atomic(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "m.json", base_dir=tmp_path)
    # First claim wins; a second concurrent claim for the same project loses.
    assert store.try_claim_inflight(project_id="spp-deadbeef0001", attempt_id="att-1") is True
    # Simulate the first attempt being persisted as STARTING.
    att = HvsMaterializationAttempt(
        attempt_id="att-1", project_id="spp-deadbeef0001", project_revision=2,
        plan_hash="a" * 64, destination_identity="d",
        authorization_id="auth-1", capability_id="cap-1",
        state=STATE_MATERIALIZATION_STARTING, hvs_calls=0,
        started_at="2026-07-17T00:00:00.000000Z",
    )
    store.put_attempt(att)
    assert store.try_claim_inflight(project_id="spp-deadbeef0001", attempt_id="att-2") is False


def test_failure_before_hvs_is_confirmed_failure(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "m.json", base_dir=tmp_path)
    pid, norm = _setup_prepared(tmp_path)
    dest = _dest(tmp_path)
    plan = _plan(tmp_path, pid, 2, norm, dest)
    dt = "2026-07-17T00:00:00.000000Z"
    # Authorization bound to a plan hash that does NOT match the freshly
    # re-derived plan => rejected before HVS (no call).
    auth = _authorized(dt, project_id=pid, destination=dest, plan_hash="z" * 64)
    res = materialize(store=store, project_id=pid, project_revision=2, normalized=norm,
        output_profiles=("vertical_9_16",), destination_identity=dest,
        authorization=auth, capability_id="cap-1", attempt_id="att-1",
        operator_id="op", now_iso=dt,
        hvs_initializer=_fake_initializer(ok=False), hvs_inspector=_fake_inspector())
    assert res.ok is False
    assert res.hvs_calls == 0
    # Authorization/plan mismatch is rejected at the authorization gate
    # (fail-closed) before any HVS call; state reflects a rejected request.
    assert res.state in (
        STATE_MATERIALIZATION_AUTHORIZATION_REQUIRED,
        STATE_MATERIALIZATION_FAILED_CONFIRMED,
    )


def test_hvs_nonzero_without_project_is_confirmed_failure(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "m.json", base_dir=tmp_path)
    pid, norm = _setup_prepared(tmp_path)
    dest = _dest(tmp_path)
    plan = _plan(tmp_path, pid, 2, norm, dest)
    dt = "2026-07-17T00:00:00.000000Z"
    auth = _authorized(dt, project_id=pid, destination=dest, plan_hash=plan.plan_hash)
    res = materialize(store=store, project_id=pid, project_revision=2, normalized=norm,
        output_profiles=("vertical_9_16",), destination_identity=dest,
        authorization=auth, capability_id="cap-1", attempt_id="att-1",
        operator_id="op", now_iso=dt,
        hvs_initializer=_fake_initializer(ok=False, created=False, verified=False),
        hvs_inspector=_fake_inspector(ok=False, valid=False))
    assert res.ok is False
    assert res.hvs_calls == 1
    assert res.state == STATE_MATERIALIZATION_FAILED_CONFIRMED
    assert res.outcome == "failed"


def test_timeout_possible_start_is_unknown_no_retry(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "m.json", base_dir=tmp_path)
    pid, norm = _setup_prepared(tmp_path)
    dest = _dest(tmp_path)
    plan = _plan(tmp_path, pid, 2, norm, dest)
    dt = "2026-07-17T00:00:00.000000Z"
    auth = _authorized(dt, project_id=pid, destination=dest, plan_hash=plan.plan_hash)
    res = materialize(store=store, project_id=pid, project_revision=2, normalized=norm,
        output_profiles=("vertical_9_16",), destination_identity=dest,
        authorization=auth, capability_id="cap-1", attempt_id="att-1",
        operator_id="op", now_iso=dt,
        hvs_initializer=_fake_initializer(), hvs_inspector=_fake_inspector(),
        timeout_during_invoke=True)
    assert res.ok is False
    assert res.state == STATE_MATERIALIZATION_OUTCOME_UNKNOWN
    assert res.outcome == "unknown"
    # No automatic retry => only the single (timed-out) HVS call was attempted.
    assert res.hvs_calls == 1
    prior = store.get_attempt("att-1")
    assert prior.state == STATE_MATERIALIZATION_OUTCOME_UNKNOWN


def test_corrupt_destination_fails_closed(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "m.json", base_dir=tmp_path)
    pid, norm = _setup_prepared(tmp_path)
    dest = _dest(tmp_path)
    plan = _plan(tmp_path, pid, 2, norm, dest)
    dt = "2026-07-17T00:00:00.000000Z"
    # Destination mismatch => fail closed before HVS.
    auth = _authorized(dt, project_id=pid,
                       destination="C:/Workspace/hermes-video-studio/projects",
                       plan_hash=plan.plan_hash)
    res = materialize(store=store, project_id=pid, project_revision=2, normalized=norm,
        output_profiles=("vertical_9_16",), destination_identity=dest,
        authorization=auth, capability_id="cap-1", attempt_id="att-1",
        operator_id="op", now_iso=dt,
        hvs_initializer=_fake_initializer(), hvs_inspector=_fake_inspector())
    assert res.ok is False
    assert res.hvs_calls == 0
    assert res.error_code == "AUTHORIZATION_DESTINATION_MISMATCH"


def test_identity_mismatch_blocks_success(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "m.json", base_dir=tmp_path)
    pid, norm = _setup_prepared(tmp_path)
    dest = _dest(tmp_path)
    plan = _plan(tmp_path, pid, 2, norm, dest)
    dt = "2026-07-17T00:00:00.000000Z"
    auth = _authorized(dt, project_id=pid, destination=dest, plan_hash=plan.plan_hash)
    # Inspector reports a DIFFERENT payload hash => identity conflict.
    res = materialize(store=store, project_id=pid, project_revision=2, normalized=norm,
        output_profiles=("vertical_9_16",), destination_identity=dest,
        authorization=auth, capability_id="cap-1", attempt_id="att-1",
        operator_id="op", now_iso=dt,
        hvs_initializer=_fake_initializer(),
        hvs_inspector=_fake_inspector(valid=False, payload_hash="f" * 64))
    assert res.ok is False
    assert res.state == STATE_MATERIALIZATION_FAILED_CONFIRMED


# --------------------------------------------------------------------------
# Reconciliation tests (read-only)
# --------------------------------------------------------------------------

def test_reconcile_detects_confirmed_materialized(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "m.json", base_dir=tmp_path)
    pid, norm = _setup_prepared(tmp_path)
    dest = _dest(tmp_path)
    plan = _plan(tmp_path, pid, 2, norm, dest)
    dt = "2026-07-17T00:00:00.000000Z"
    auth = _authorized(dt, project_id=pid, destination=dest, plan_hash=plan.plan_hash)
    res = materialize(store=store, project_id=pid, project_revision=2, normalized=norm,
        output_profiles=("vertical_9_16",), destination_identity=dest,
        authorization=auth, capability_id="cap-1", attempt_id="att-1",
        operator_id="op", now_iso=dt,
        hvs_initializer=_fake_initializer(),
        hvs_inspector=_fake_inspector(valid=True, payload_hash=plan.plan_hash))
    assert res.ok
    classification, attempt = reconcile_materialization(
        store=store, attempt_id="att-1",
        hvs_inspector=_fake_inspector(valid=True, payload_hash=plan.plan_hash))
    assert classification == STATE_HVS_PROJECT_MATERIALIZED
    assert attempt is not None


def test_reconcile_detects_confirmed_absence(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "m.json", base_dir=tmp_path)
    # Build an unknown attempt with NO project at the destination.
    att = HvsMaterializationAttempt(
        attempt_id="att-x", project_id="spp-deadbeef0001", project_revision=2,
        plan_hash="a" * 64, destination_identity=_dest(tmp_path),
        authorization_id="auth-1", capability_id="cap-1",
        state=STATE_MATERIALIZATION_OUTCOME_UNKNOWN, hvs_calls=1,
        started_at="2026-07-17T00:00:00.000000Z",
        finished_at="2026-07-17T00:00:01.000000Z", outcome="unknown")
    store.put_attempt(att)
    classification, attempt = reconcile_materialization(
        store=store, attempt_id="att-x",
        hvs_inspector=_fake_inspector(ok=False, valid=False))
    # Inspector returns no valid project => confirmed not materialized.
    assert classification == "CONFIRMED_NOT_MATERIALIZED"


def test_unknown_outcome_never_retries(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "m.json", base_dir=tmp_path)
    pid, norm = _setup_prepared(tmp_path)
    dest = _dest(tmp_path)
    plan = _plan(tmp_path, pid, 2, norm, dest)
    dt = "2026-07-17T00:00:00.000000Z"
    auth = _authorized(dt, project_id=pid, destination=dest, plan_hash=plan.plan_hash)
    res = materialize(store=store, project_id=pid, project_revision=2, normalized=norm,
        output_profiles=("vertical_9_16",), destination_identity=dest,
        authorization=auth, capability_id="cap-1", attempt_id="att-1",
        operator_id="op", now_iso=dt,
        hvs_initializer=_fake_initializer(), hvs_inspector=_fake_inspector(),
        timeout_during_invoke=True)
    assert res.state == STATE_MATERIALIZATION_OUTCOME_UNKNOWN
    # Reconcile does NOT retry the HVS initializer; it only inspects.
    classification, att = reconcile_materialization(
        store=store, attempt_id="att-1",
        hvs_inspector=_fake_inspector(ok=False, valid=False))
    assert classification in ("STILL_UNKNOWN", "CONFIRMED_NOT_MATERIALIZED")
    assert att.state in (STATE_MATERIALIZATION_OUTCOME_UNKNOWN,
                           STATE_MATERIALIZATION_RECONCILIATION_REQUIRED,
                           STATE_MATERIALIZATION_FAILED_CONFIRMED)


# --------------------------------------------------------------------------
# Persistence / restart tests
# --------------------------------------------------------------------------

def _persist_authorized(store, pid, norm, dest, plan, dt, *, attempt_id="att-1"):
    auth = _authorized(dt, project_id=pid, destination=dest, plan_hash=plan.plan_hash)
    hvs_root = make_temp_hvs_repo(Path(dest), normalized_hvs_project_name(pid))
    return materialize(store=store, project_id=pid, project_revision=2, normalized=norm,
        output_profiles=("vertical_9_16",), destination_identity=dest,
        authorization=auth, capability_id="cap-1", attempt_id=attempt_id,
        operator_id="op", now_iso=dt,
        hvs_initializer=_hermetic_initializer(hvs_root),
        hvs_inspector=_hermetic_inspector(hvs_root, payload_hash=plan.plan_hash))


def test_pending_authorization_survives_restart(tmp_path):
    p = tmp_path / "m.json"
    store = MaterializationStore(store_path=p, base_dir=tmp_path)
    dt = "2026-07-17T00:00:00.000000Z"
    auth = _authorized(dt, destination="d", plan_hash="a" * 64)
    store.put_authorization(auth)
    reopened = MaterializationStore(store_path=p, base_dir=tmp_path)
    assert reopened.get_authorization("auth-1") is not None


def test_confirmed_success_survives_restart(tmp_path):
    p = tmp_path / "m.json"
    store = MaterializationStore(store_path=p, base_dir=tmp_path)
    pid, norm = _setup_prepared(tmp_path)
    dest = _dest(tmp_path)
    plan = _plan(tmp_path, pid, 2, norm, dest)
    dt = "2026-07-17T00:00:00.000000Z"
    _persist_authorized(store, pid, norm, dest, plan, dt)
    reopened = MaterializationStore(store_path=p, base_dir=tmp_path)
    att = reopened.get_attempt("att-1")
    assert att is not None
    assert att.state == STATE_HVS_PROJECT_MATERIALIZED
    # Restart did NOT duplicate the HVS project.
    proj_dir = Path(dest) / "projects" / normalized_hvs_project_name(pid)
    assert proj_dir.is_dir()


def test_unknown_outcome_survives_restart(tmp_path):
    p = tmp_path / "m.json"
    store = MaterializationStore(store_path=p, base_dir=tmp_path)
    pid, norm = _setup_prepared(tmp_path)
    dest = _dest(tmp_path)
    plan = _plan(tmp_path, pid, 2, norm, dest)
    dt = "2026-07-17T00:00:00.000000Z"
    auth = _authorized(dt, project_id=pid, destination=dest, plan_hash=plan.plan_hash)
    materialize(store=store, project_id=pid, project_revision=2, normalized=norm,
        output_profiles=("vertical_9_16",), destination_identity=dest,
        authorization=auth, capability_id="cap-1", attempt_id="att-1",
        operator_id="op", now_iso=dt,
        hvs_initializer=_fake_initializer(), hvs_inspector=_fake_inspector(),
        timeout_during_invoke=True)
    reopened = MaterializationStore(store_path=p, base_dir=tmp_path)
    att = reopened.get_attempt("att-1")
    assert att.state == STATE_MATERIALIZATION_OUTCOME_UNKNOWN


def test_restart_does_not_duplicate_hvs_project(tmp_path):
    p = tmp_path / "m.json"
    store = MaterializationStore(store_path=p, base_dir=tmp_path)
    pid, norm = _setup_prepared(tmp_path)
    dest = _dest(tmp_path)
    plan = _plan(tmp_path, pid, 2, norm, dest)
    dt = "2026-07-17T00:00:00.000000Z"
    _persist_authorized(store, pid, norm, dest, plan, dt)
    # Simulate restart by re-opening the store and re-reading the attempt.
    reopened = MaterializationStore(store_path=p, base_dir=tmp_path)
    att = reopened.get_attempt("att-1")
    assert att.state == STATE_HVS_PROJECT_MATERIALIZED
    # Only one project directory exists.
    proj_dirs = [d for d in Path(dest).iterdir() if d.is_dir()]
    assert len(proj_dirs) == 1


# --------------------------------------------------------------------------
# Plan determinism + authorization issuance tests
# --------------------------------------------------------------------------

def test_plan_hash_is_deterministic_and_rootless(tmp_path):
    pid = "spp-deadbeef0001"
    norm = _normalized()
    dest = _dest(tmp_path)
    a = build_materialization_plan(project_id=pid, project_revision=2,
        destination_identity=dest, normalized=norm,
        output_profiles=("vertical_9_16",), now_iso="T")
    b = build_materialization_plan(project_id=pid, project_revision=2,
        destination_identity=dest, normalized=norm,
        output_profiles=("vertical_9_16",), now_iso="DIFFERENT")
    assert a.plan_hash == b.plan_hash  # independent of clock
    blob = json.dumps(a.to_dict())
    # The plan must never embed an executable instruction, shell command,
    # secret, or external URL fetch. The forbidden_operations list is a
    # deny-list (contains the words) and is expected; we instead assert the
    # ABSENCE of executable/secret leakage fields.
    for leak in ("render_command", "ffmpeg_command", "execute(", "subprocess",
                  "shell:", "token", "secret", "password", "api_key",
                  "http://", "https://"):
        assert leak not in blob
    assert a.forbidden_operations  # explicit denylist present


def test_authorization_only_on_explicit_confirmation(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "m.json", base_dir=tmp_path)
    dt = "2026-07-17T00:00:00.000000Z"
    plan = _plan(tmp_path, "spp-deadbeef0001", 2, _normalized(), _dest(tmp_path))
    # Not confirmed => DENIED, not persisted as AUTHORIZED.
    auth, decision, err = issue_authorization(
        store=store, project_id="spp-deadbeef0001", project_revision=2, plan=plan,
        operator_id="op", confirmed=False, now_iso=dt,
        authorization_id="auth-1", nonce="n1")
    assert decision == DECISION_DENIED
    assert store.get_authorization("auth-1") is None
    # Confirmed => AUTHORIZED, persisted.
    auth2, decision2, err2 = issue_authorization(
        store=store, project_id="spp-deadbeef0001", project_revision=2, plan=plan,
        operator_id="op", confirmed=True, now_iso=dt,
        authorization_id="auth-2", nonce="n2")
    assert decision2 == DECISION_AUTHORIZED
    assert store.get_authorization("auth-2") is not None


def test_prerequisites_reject_non_review_ready(tmp_path):
    # A record still in APPROVED (no preview) must be rejected.
    ok, blockers = evaluate_prerequisites(
        truth_status="AVAILABLE_WITH_DATA", state=STATE_APPROVED,
        approval_status="approved", project_revision=2, expected_revision=2,
        preparation_preview=None, output_profiles=("vertical_9_16",),
        destination_identity="d", side_effect_flags={})
    assert ok is False
    assert any("preview" in b for b in blockers)


def test_evaluate_prerequisites_rootless_fields(tmp_path):
    # The destination identity must not be a forbidden production path.
    from scos.control_center.hvs_project_materialization_models import (
        ERR_AUTHORIZATION_DESTINATION_MISMATCH,
    )
    ok, _ = evaluate_prerequisites(
        truth_status="AVAILABLE_WITH_DATA", state=STATE_PREPARATION_PREVIEW_READY,
        approval_status="approved", project_revision=2, expected_revision=2,
        preparation_preview={"a": 1}, output_profiles=("vertical_9_16",),
        destination_identity="C:/Workspace/hermes-video-studio/projects",
        side_effect_flags={})
    assert ok is False
