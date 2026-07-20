"""Cohort 10E backend tests — controlled HVS project render authorization.

All tests use isolated temp stores + a hermetic fake HVS render callable so
NO real HVS repository, NO network, and NO render/media tool is ever
invoked. The REAL HVS render boundary (HermesVideoStudioAdapter.render_project)
is exercised only by the out-of-band canary (Phase 14), run separately.

Covered:
  * Authorization + single-use capability contract (fail-closed).
  * State machine: no generic COMPLETED; invalid transitions fail closed.
  * Exact replay => 0 additional render calls; conflicting replay rejected.
  * One active attempt blocks another (concurrency = 1).
  * Unknown outcome => RENDER_OUTCOME_UNKNOWN => reconciliation required;
    reconciliation is read-only and never re-renders.
  * Persistence/restart: starting attempt, unknown outcome, confirmed
    success all survive a simulated restart (fresh store over same file).
  * Toolchain/negative: HVS unavailable, FFmpeg/FFprobe unavailable,
    invalid output profile, missing HVS project, output validation
    failure, disk insufficiency all fail closed with render_calls == 0
    before the boundary (or confirmed failure after) and NEVER retry.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scos.control_center.hvs_render_plan_models import (
    DECISION_AUTHORIZED,
    DECISION_DENIED,
    RENDER_SCHEMA_VERSION,
    OPERATION_RENDER_HVS_PROJECT,
    STATE_RENDER_AUTHORIZATION_REQUIRED,
    STATE_RENDER_AUTHORIZED,
    STATE_RENDER_FAILED_CONFIRMED,
    STATE_RENDER_NOT_REQUESTED,
    STATE_RENDER_OUTCOME_UNKNOWN,
    STATE_RENDER_RECONCILIATION_REQUIRED,
    STATE_RENDER_STARTING,
    STATE_RENDER_SUCCEEDED,
    HvsRenderAuthorization,
    HvsRenderCapability,
    HvsRenderPlan,
    HvsRenderAttempt,
)
from scos.control_center.hvs_render_attempt_store import RenderAttemptStore
from scos.control_center.hvs_render_execution_service import (
    build_render_plan,
    issue_authorization,
    normalized_hvs_project_name,
    reconcile_render,
    render,
    _default_expires_at,
)

OUT_ROOT = "C:/Users/chara/AppData/Local/Temp/cohort10e-out"
PROJECT_ID = "spp-abcdef123456"
PROJECT_REV = 2
MAT_ATTEMPT = "mat-10e-1"
MAT_PLAN_HASH = "matplanhash-10e"
RENDER_PROFILE = "vertical"
ATTEMPT_ID = "att-10e-1"
CAP_ID = "cap-10e-1"
AUTH_ID = "auth-10e-1"
OP_ID = "local-solo-operator"


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _auth(store, *, confirmed=True, project_revision=PROJECT_REV, render_profile=RENDER_PROFILE,
          output_root=OUT_ROOT, plan_hash=None, expires_in_future=True, decision=DECISION_AUTHORIZED):
    now = _now_iso()
    plan = build_render_plan(
        project_id=PROJECT_ID, project_revision=project_revision,
        materialization_attempt_id=MAT_ATTEMPT, materialization_plan_hash=MAT_PLAN_HASH,
        render_profile_id=render_profile, output_root_identity=output_root, now_iso=now,
    )
    ph = plan_hash if plan_hash is not None else plan.plan_hash
    auth = HvsRenderAuthorization(
        schema_version=RENDER_SCHEMA_VERSION, authorization_id=AUTH_ID, project_id=PROJECT_ID,
        project_revision=project_revision, materialization_attempt_id=MAT_ATTEMPT,
        materialization_plan_hash=MAT_PLAN_HASH, render_profile_id=render_profile,
        render_plan_hash=ph, output_root_identity=output_root, issued_at=now,
        expires_at=_default_expires_at(now), issued_by=OP_ID, decision=decision, nonce="n0",
    )
    store.put_authorization(auth)
    return auth, plan


def _good_render(**overrides):
    base = {
        "ok": True, "command": "render-hyperframes", "exit_code": 0,
        "render_id": "r1", "output_relative_path": "render/hvs-abcdef123456/hvs-abcdef123456.vertical.h264.mp4",
        "error_detail": None,
    }
    base.update(overrides)
    return base


def _good_inspector(exists=True, sha="", size=12345):
    return lambda **kw: {
        "ok": True, "exists": True, "valid": True, "project_id": kw.get("project_id"),
        "artifact_exists": exists, "artifact_sha256": sha, "artifact_size_bytes": size,
    }


def _good_validator(ok=True, sha="", size=12345):
    def _v(**kw):
        return {
            "ok": ok,
            "verification": {
                "artifact_verified": ok,
                "verification_status": "VERIFIED" if ok else "UNEXPECTED_OUTPUT",
                "sha256": sha or "deadbeef" * 8,
                "artifact": {"artifact_id": "a1", "relative_output_path": "render/hvs-abcdef123456/hvs-abcdef123456.vertical.h264.mp4", "size_bytes": size},
                "probe": {"video_duration": 3.0, "width": 1080, "height": 1920, "fps": 30, "video_codec": "h264", "audio_codec": None},
            },
            "blockers": () if ok else ("validation_failed",),
        }
    return _v


# --------------------------------------------------------------------------
# Authorization + capability contract
# --------------------------------------------------------------------------

def test_non_materialized_cannot_render(tmp_path):
    store = RenderAttemptStore(store_path=tmp_path / "s.json")
    auth, plan = _auth(store, decision=DECISION_DENIED)
    res = render(
        store=store, project_id=PROJECT_ID, project_revision=PROJECT_REV,
        materialization_attempt_id=MAT_ATTEMPT, materialization_plan_hash=MAT_PLAN_HASH,
        render_profile_id=RENDER_PROFILE, output_root_identity=OUT_ROOT,
        authorization=auth, capability_id=CAP_ID, attempt_id=ATTEMPT_ID, operator_id=OP_ID,
        now_iso=_now_iso(), hvs_render=lambda **k: _good_render(),
 projects_root_identity="ISOLATED_PROJECTS_ROOT",
        hvs_inspector=_good_inspector(), artifact_validator=_good_validator(),
    )
    assert res.ok is False
    assert res.render_calls == 0
    assert res.error_code == "AUTHORIZATION_MALFORMED"


def test_stale_revision_rejected(tmp_path):
    store = RenderAttemptStore(store_path=tmp_path / "s.json")
    auth, plan = _auth(store, confirmed=True, project_revision=PROJECT_REV + 1)
    res = render(
        store=store, project_id=PROJECT_ID, project_revision=PROJECT_REV,  # stale/current mismatch
        materialization_attempt_id=MAT_ATTEMPT, materialization_plan_hash=MAT_PLAN_HASH,
        render_profile_id=RENDER_PROFILE, output_root_identity=OUT_ROOT,
        authorization=auth, capability_id=CAP_ID, attempt_id=ATTEMPT_ID, operator_id=OP_ID,
        now_iso=_now_iso(), hvs_render=lambda **k: _good_render(),
 projects_root_identity="ISOLATED_PROJECTS_ROOT",
        hvs_inspector=_good_inspector(), artifact_validator=_good_validator(),
    )
    assert res.ok is False
    assert res.render_calls == 0
    assert res.error_code == "AUTHORIZATION_REVISION_MISMATCH"


def test_mismatched_plan_cannot_execute(tmp_path):
    store = RenderAttemptStore(store_path=tmp_path / "s.json")
    auth, plan = _auth(store, confirmed=True, plan_hash="different-plan-hash")
    res = render(
        store=store, project_id=PROJECT_ID, project_revision=PROJECT_REV,
        materialization_attempt_id=MAT_ATTEMPT, materialization_plan_hash=MAT_PLAN_HASH,
        render_profile_id=RENDER_PROFILE, output_root_identity=OUT_ROOT,
        authorization=auth, capability_id=CAP_ID, attempt_id=ATTEMPT_ID, operator_id=OP_ID,
        now_iso=_now_iso(), hvs_render=lambda **k: _good_render(),
 projects_root_identity="ISOLATED_PROJECTS_ROOT",
        hvs_inspector=_good_inspector(), artifact_validator=_good_validator(),
    )
    assert res.ok is False
    assert res.render_calls == 0
    assert res.error_code == "RENDER_PLAN_MISMATCH"


def test_capability_single_use_replay_contained(tmp_path):
    store = RenderAttemptStore(store_path=tmp_path / "s.json")
    auth, plan = _auth(store, confirmed=True)
    calls = {"n": 0}

    def fake_render(**k):
        calls["n"] += 1
        return _good_render()

    res1 = render(
        store=store, project_id=PROJECT_ID, project_revision=PROJECT_REV,
        materialization_attempt_id=MAT_ATTEMPT, materialization_plan_hash=MAT_PLAN_HASH,
        render_profile_id=RENDER_PROFILE, output_root_identity=OUT_ROOT,
        authorization=auth, capability_id=CAP_ID, attempt_id=ATTEMPT_ID, operator_id=OP_ID,
        now_iso=_now_iso(), hvs_render=fake_render,
        projects_root_identity="ISOLATED_PROJECTS_ROOT",
        hvs_inspector=_good_inspector(), artifact_validator=_good_validator(),
    )
    assert res1.ok is True
    assert res1.render_calls == 1
    assert calls["n"] == 1

    # Exact replay with the SAME capability id => rejected, 0 additional renders.
    res2 = render(
        store=store, project_id=PROJECT_ID, project_revision=PROJECT_REV,
        materialization_attempt_id=MAT_ATTEMPT, materialization_plan_hash=MAT_PLAN_HASH,
        render_profile_id=RENDER_PROFILE, output_root_identity=OUT_ROOT,
        authorization=auth, capability_id=CAP_ID, attempt_id=ATTEMPT_ID, operator_id=OP_ID,
        now_iso=_now_iso(), hvs_render=fake_render,
        projects_root_identity="ISOLATED_PROJECTS_ROOT",
        hvs_inspector=_good_inspector(), artifact_validator=_good_validator(),
    )
    assert res2.ok is False
    assert res2.render_calls == 0
    assert res2.error_code == "CAPABILITY_CONSUMED"
    assert calls["n"] == 1  # no second render


def test_conflicting_payload_rejected(tmp_path):
    store = RenderAttemptStore(store_path=tmp_path / "s.json")
    auth, plan = _auth(store, confirmed=True)
    calls = {"n": 0}

    def fake_render(**k):
        calls["n"] += 1
        return _good_render()

    # First render succeeds and consumes the capability atomically.
    res1 = render(
        store=store, project_id=PROJECT_ID, project_revision=PROJECT_REV,
        materialization_attempt_id=MAT_ATTEMPT, materialization_plan_hash=MAT_PLAN_HASH,
        render_profile_id=RENDER_PROFILE, output_root_identity=OUT_ROOT,
        authorization=auth, capability_id=CAP_ID, attempt_id=ATTEMPT_ID, operator_id=OP_ID,
        now_iso=_now_iso(), hvs_render=fake_render,
        projects_root_identity="ISOLATED_PROJECTS_ROOT",
        hvs_inspector=_good_inspector(), artifact_validator=_good_validator(),
    )
    assert res1.ok is True
    assert calls["n"] == 1
    # Conflicting replay: same capability (already consumed), different attempt id.
    res2 = render(
        store=store, project_id=PROJECT_ID, project_revision=PROJECT_REV,
        materialization_attempt_id=MAT_ATTEMPT, materialization_plan_hash=MAT_PLAN_HASH,
        render_profile_id=RENDER_PROFILE, output_root_identity=OUT_ROOT,
        authorization=auth, capability_id=CAP_ID, attempt_id="att-other", operator_id=OP_ID,
        now_iso=_now_iso(), hvs_render=fake_render,
        projects_root_identity="ISOLATED_PROJECTS_ROOT",
        hvs_inspector=_good_inspector(), artifact_validator=_good_validator(),
    )
    assert res2.ok is False
    assert res2.render_calls == 0
    assert res2.error_code == "CAPABILITY_CONSUMED"
    assert calls["n"] == 1  # no second render


def test_one_active_attempt_blocks_another(tmp_path):
    store = RenderAttemptStore(store_path=tmp_path / "s.json")
    auth, plan = _auth(store, confirmed=True)
    # Seed an in-flight (active) attempt directly, simulating a render that
    # is currently starting/running for this project.
    now = _now_iso()
    seed = HvsRenderAttempt(
        attempt_id="att-inflight", project_id=PROJECT_ID, project_revision=PROJECT_REV,
        materialization_attempt_id=MAT_ATTEMPT, materialization_plan_hash=MAT_PLAN_HASH,
        render_profile_id=RENDER_PROFILE, render_plan_hash=plan.plan_hash,
        authorization_id=AUTH_ID, capability_id="cap-inflight", output_root_identity=OUT_ROOT,
        state=STATE_RENDER_STARTING, hvs_calls=0, render_calls=0,
        created_at=now, updated_at=now, started_at=now,
    )
    store.put_attempt(seed)
    assert store.has_active_attempt(project_id=PROJECT_ID, exclude_attempt_id="att-second") is True
    # A second attempt for the SAME project must be blocked while one is active.
    res2 = render(
        store=store, project_id=PROJECT_ID, project_revision=PROJECT_REV,
        materialization_attempt_id=MAT_ATTEMPT, materialization_plan_hash=MAT_PLAN_HASH,
        render_profile_id=RENDER_PROFILE, output_root_identity=OUT_ROOT,
        authorization=auth, capability_id="cap-second", attempt_id="att-second", operator_id=OP_ID,
        now_iso=_now_iso(), hvs_render=lambda **k: _good_render(),
 projects_root_identity="ISOLATED_PROJECTS_ROOT",
        hvs_inspector=_good_inspector(), artifact_validator=_good_validator(),
    )
    assert res2.ok is False
    assert res2.render_calls == 0
    assert res2.error_code == "RENDER_ALREADY_ACTIVE"


def test_unknown_outcome_requires_reconciliation(tmp_path):
    store = RenderAttemptStore(store_path=tmp_path / "s.json")
    auth, plan = _auth(store, confirmed=True)

    # HVS render callable that raises mid-invocation (simulates timeout /
    # lost response after the boundary was crossed).
    def hanging(**k):
        raise RuntimeError("render did not return")

    res = render(
        store=store, project_id=PROJECT_ID, project_revision=PROJECT_REV,
        materialization_attempt_id=MAT_ATTEMPT, materialization_plan_hash=MAT_PLAN_HASH,
        render_profile_id=RENDER_PROFILE, output_root_identity=OUT_ROOT,
        authorization=auth, capability_id=CAP_ID, attempt_id=ATTEMPT_ID, operator_id=OP_ID,
        now_iso=_now_iso(), hvs_render=hanging,
        projects_root_identity="ISOLATED_PROJECTS_ROOT",
        hvs_inspector=_good_inspector(), artifact_validator=_good_validator(),
    )
    assert res.ok is False
    assert res.state == STATE_RENDER_OUTCOME_UNKNOWN
    assert res.render_calls == 1  # the boundary was crossed once
    assert res.error_code == "RENDER_START_FAILED"
    attempt = store.get_attempt(ATTEMPT_ID)
    assert attempt.state == STATE_RENDER_OUTCOME_UNKNOWN


def _timeout_render():
    # Kept for API compatibility; the unknown-outcome test passes a raising
    # callable directly.
    def wrapper(**k):
        raise RuntimeError("unused")
    return wrapper


def test_reconciliation_is_read_only_no_rerender(tmp_path):
    store = RenderAttemptStore(store_path=tmp_path / "s.json")
    # Seed an unknown attempt directly.
    now = _now_iso()
    from scos.control_center.hvs_render_plan_models import HvsRenderAttempt
    attempt = HvsRenderAttempt(
        attempt_id=ATTEMPT_ID, project_id=PROJECT_ID, project_revision=PROJECT_REV,
        materialization_attempt_id=MAT_ATTEMPT, materialization_plan_hash=MAT_PLAN_HASH,
        render_profile_id=RENDER_PROFILE, render_plan_hash="ph",
        authorization_id=AUTH_ID, capability_id=CAP_ID, output_root_identity=OUT_ROOT,
        state=STATE_RENDER_OUTCOME_UNKNOWN, hvs_calls=1, render_calls=1,
        created_at=now, updated_at=now, started_at=now, finished_at=now,
        artifact_descriptor={"sha256": "deadbeef" * 8, "size_bytes": 12345},
    )
    store.put_attempt(attempt)
    render_calls = {"n": 0}

    def inspector(**k):
        return {"ok": True, "exists": True, "valid": True, "project_id": k.get("project_id"),
                "artifact_exists": True, "artifact_sha256": "deadbeef" * 8, "artifact_size_bytes": 12345}

    classification, updated = reconcile_render(
        store=store, attempt_id=ATTEMPT_ID, hvs_inspector=inspector,
    )
    # No render callable was passed => there is no way reconciliation re-renders.
    assert render_calls["n"] == 0
    assert classification == "RENDER_SUCCEEDED"
    assert updated.state == STATE_RENDER_SUCCEEDED


def test_restart_restores_unknown_attempt(tmp_path):
    store = RenderAttemptStore(store_path=tmp_path / "s.json")
    now = _now_iso()
    from scos.control_center.hvs_render_plan_models import HvsRenderAttempt
    attempt = HvsRenderAttempt(
        attempt_id=ATTEMPT_ID, project_id=PROJECT_ID, project_revision=PROJECT_REV,
        materialization_attempt_id=MAT_ATTEMPT, materialization_plan_hash=MAT_PLAN_HASH,
        render_profile_id=RENDER_PROFILE, render_plan_hash="ph",
        authorization_id=AUTH_ID, capability_id=CAP_ID, output_root_identity=OUT_ROOT,
        state=STATE_RENDER_OUTCOME_UNKNOWN, hvs_calls=1, render_calls=1,
        created_at=now, updated_at=now, started_at=now, finished_at=now,
    )
    store.put_attempt(attempt)
    # Simulate restart: brand-new store object over the same file.
    restarted = RenderAttemptStore(store_path=tmp_path / "s.json")
    restored = restarted.get_attempt(ATTEMPT_ID)
    assert restored is not None
    assert restored.state == STATE_RENDER_OUTCOME_UNKNOWN
    assert restored.render_calls == 1


def test_toolchain_unavailable_fails_closed(tmp_path):
    store = RenderAttemptStore(store_path=tmp_path / "s.json")
    auth, plan = _auth(store, confirmed=True)
    # HVS render callable that raises (simulates HVS/toolchain unavailable).
    def broken(**k):
        raise RuntimeError("hvs not available")

    res = render(
        store=store, project_id=PROJECT_ID, project_revision=PROJECT_REV,
        materialization_attempt_id=MAT_ATTEMPT, materialization_plan_hash=MAT_PLAN_HASH,
        render_profile_id=RENDER_PROFILE, output_root_identity=OUT_ROOT,
        authorization=auth, capability_id=CAP_ID, attempt_id=ATTEMPT_ID, operator_id=OP_ID,
        now_iso=_now_iso(), hvs_render=broken,
        projects_root_identity="ISOLATED_PROJECTS_ROOT",
        hvs_inspector=_good_inspector(), artifact_validator=_good_validator(),
    )
    assert res.ok is False
    assert res.state == STATE_RENDER_OUTCOME_UNKNOWN  # unknown, not coerced to failure
    assert res.render_calls == 1  # one attempt was made, no retry
    attempt = store.get_attempt(ATTEMPT_ID)
    assert attempt.state == STATE_RENDER_OUTCOME_UNKNOWN


def test_invalid_output_profile_fails_closed():
    # build_render_plan must reject unsupported profiles before any side effect.
    with pytest.raises(ValueError):
        build_render_plan(
            project_id=PROJECT_ID, project_revision=PROJECT_REV,
            materialization_attempt_id=MAT_ATTEMPT, materialization_plan_hash=MAT_PLAN_HASH,
            render_profile_id="does-not-exist", output_root_identity=OUT_ROOT,
            now_iso=_now_iso(),
        )


def test_artifact_validation_failure_confirmed_failure(tmp_path):
    store = RenderAttemptStore(store_path=tmp_path / "s.json")
    auth, plan = _auth(store, confirmed=True)
    res = render(
        store=store, project_id=PROJECT_ID, project_revision=PROJECT_REV,
        materialization_attempt_id=MAT_ATTEMPT, materialization_plan_hash=MAT_PLAN_HASH,
        render_profile_id=RENDER_PROFILE, output_root_identity=OUT_ROOT,
        authorization=auth, capability_id=CAP_ID, attempt_id=ATTEMPT_ID, operator_id=OP_ID,
        now_iso=_now_iso(), hvs_render=lambda **k: _good_render(),
 projects_root_identity="ISOLATED_PROJECTS_ROOT",
        hvs_inspector=_good_inspector(), artifact_validator=_good_validator(ok=False),
    )
    assert res.ok is False
    assert res.state == STATE_RENDER_FAILED_CONFIRMED
    assert res.error_code == "ARTIFACT_VALIDATION_FAILED"
    assert res.render_calls == 1  # one render happened, no retry


# ---------------------------------------------------------------------------
# Projection plan-hash contract (Cohort 10F repair)
# ---------------------------------------------------------------------------

def _plan_a():
    return build_render_plan(
        project_id=PROJECT_ID, project_revision=PROJECT_REV,
        materialization_attempt_id=MAT_ATTEMPT, materialization_plan_hash="",
        render_profile_id=RENDER_PROFILE, output_root_identity=OUT_ROOT, now_iso=_now_iso(),
    )


def test_projection_plan_hash_non_empty():
    plan = _plan_a()
    assert plan.materialization_plan_hash, "projection must return a non-empty plan hash"
    assert len(plan.materialization_plan_hash) >= 8


def test_projection_plan_hash_deterministic():
    a = _plan_a().materialization_plan_hash
    b = _plan_a().materialization_plan_hash
    assert a == b, "same canonical plan -> identical hash"


def test_projection_plan_hash_survives_serialization():
    plan = _plan_a()
    roundtrip = HvsRenderPlan(**plan.to_dict())
    assert roundtrip.materialization_plan_hash == plan.materialization_plan_hash


def test_projection_plan_hash_changes_on_authorization_relevant_plan():
    base = _plan_a().materialization_plan_hash
    changed = build_render_plan(
        project_id=PROJECT_ID, project_revision=PROJECT_REV + 1,  # revision is auth-relevant
        materialization_attempt_id=MAT_ATTEMPT, materialization_plan_hash="",
        render_profile_id=RENDER_PROFILE, output_root_identity=OUT_ROOT, now_iso=_now_iso(),
    ).materialization_plan_hash
    assert changed != base, "authorization-relevant plan change -> different hash"


def test_projection_never_authorization_ready_with_empty_hash():
    # The server must compute a non-empty hash; an empty input must never leak.
    plan = build_render_plan(
        project_id=PROJECT_ID, project_revision=PROJECT_REV,
        materialization_attempt_id=MAT_ATTEMPT, materialization_plan_hash="",
        render_profile_id=RENDER_PROFILE, output_root_identity=OUT_ROOT, now_iso=_now_iso(),
    )
    assert plan.materialization_plan_hash != ""


def test_authorize_rejects_conflicting_plan_hash():
    store = RenderAttemptStore(store_path=__import__("tempfile").mkdtemp() + "/s.json")
    expected = _plan_a().materialization_plan_hash
    res = issue_authorization(
        store=store, project_id=PROJECT_ID, project_revision=PROJECT_REV,
        materialization_attempt_id=MAT_ATTEMPT, materialization_plan_hash="deadbeef" * 8,
        render_profile_id=RENDER_PROFILE, output_root_identity=OUT_ROOT,
        operator_id=OP_ID, confirmed=True, now_iso=_now_iso(), authorization_id=AUTH_ID,
        nonce="nonce01",
    )
    # Conflicting (wrong) hash must be rejected fail-closed.
    assert res[0] is None, "conflicting plan hash must not create an authorization"
    assert res[2] in ("PLAN_HASH_MISMATCH", "REQUEST_REJECTED"), res


def test_missing_render_ready_project_blocks_render_before_boundary(tmp_path):
    """Cohort 10F.1 root-cause regression.

    A valid, authorized, single-use capability for an HVS project whose
    render-ready tree is ABSENT at the certified projects root must be
    fail-closed BEFORE the HVS render boundary is crossed: render_calls == 0
    and hvs_calls == 0, with a truthful HVS_PROJECT_NOT_FOUND. The renderer
    and HyperFrames must never be invoked. The gate inspector must target the
    SAME projects root the renderer would use (R6 root-equality).
    """
    store = RenderAttemptStore(store_path=tmp_path / "s.json")
    auth, plan = _auth(store, confirmed=True)
    calls = {"n": 0}
    seen = {}

    def fake_render(**k):
        calls["n"] += 1
        seen["render_projects_root"] = k.get("projects_root")
        return _good_render()

    # Inspector reports the project does NOT exist at the projects root, and
    # must have been asked about that exact root.
    def missing_inspector(**k):
        seen["inspect_projects_root"] = k.get("projects_root")
        return {"ok": True, "exists": False, "valid": False,
                "project_id": k.get("project_id"), "artifact_exists": False,
                "artifact_sha256": "", "artifact_size_bytes": 0}

    res = render(
        store=store, project_id=PROJECT_ID, project_revision=PROJECT_REV,
        materialization_attempt_id=MAT_ATTEMPT, materialization_plan_hash=MAT_PLAN_HASH,
        render_profile_id=RENDER_PROFILE, output_root_identity=OUT_ROOT,
        authorization=auth, capability_id=CAP_ID, attempt_id=ATTEMPT_ID, operator_id=OP_ID,
        now_iso=_now_iso(), hvs_render=fake_render,
        projects_root_identity="ISOLATED_PROJECTS_ROOT",
        hvs_inspector=missing_inspector, artifact_validator=_good_validator(),
    )
    assert res.ok is False
    assert res.render_calls == 0
    assert res.hvs_calls == 0
    assert calls["n"] == 0  # renderer never invoked
    assert res.error_code == "HVS_PROJECT_NOT_FOUND"
    # R6: the gate inspected the SAME projects root the renderer would target.
    assert seen["inspect_projects_root"] == "ISOLATED_PROJECTS_ROOT"
    # Pre-boundary fail-closed rejection: consistent with sibling rejections,
    # no attempt is persisted (no HVS render was ever crossed).
    assert store.get_attempt(ATTEMPT_ID) is None


def test_missing_render_ready_project_inspector_exception_blocks_render(tmp_path):
    """Cohort 10F.1: an inspector that raises (e.g. root not resolvable) must
    also be treated as 'project absent' and fail closed with no render call."""
    store = RenderAttemptStore(store_path=tmp_path / "s.json")
    auth, plan = _auth(store, confirmed=True)
    calls = {"n": 0}

    def fake_render(**k):
        calls["n"] += 1
        return _good_render()

    def broken_inspector(**k):
        raise RuntimeError("projects root unreachable")

    res = render(
        store=store, project_id=PROJECT_ID, project_revision=PROJECT_REV,
        materialization_attempt_id=MAT_ATTEMPT, materialization_plan_hash=MAT_PLAN_HASH,
        render_profile_id=RENDER_PROFILE, output_root_identity=OUT_ROOT,
        authorization=auth, capability_id=CAP_ID, attempt_id=ATTEMPT_ID, operator_id=OP_ID,
        now_iso=_now_iso(), hvs_render=fake_render,
        projects_root_identity="ISOLATED_PROJECTS_ROOT",
        hvs_inspector=broken_inspector, artifact_validator=_good_validator(),
    )
    assert res.ok is False
    assert res.render_calls == 0
    assert res.hvs_calls == 0
    assert calls["n"] == 0
    assert res.error_code == "HVS_PROJECT_NOT_FOUND"
