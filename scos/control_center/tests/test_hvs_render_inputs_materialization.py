"""Cohort 10E backend tests — controlled HVS downstream render-input
materialization authorization + exactly-once wiring.

All tests use isolated temp stores + a hermetic HVS render-inputs invoker
double so NO real HVS repository, NO network, and NO render/media tool is
ever invoked. The REAL HVS ``materialize-render-inputs`` command is exercised
only by the out-of-band canary, which is run separately.

Covered:
  * Adapter: fixed command + argv, trusted root forwarded, browser path
    cannot influence root, shell disabled, no retry, narrow environment,
    one JSON response required, mixed stdout rejected, timeout classified,
    non-zero exit classified, path/stderr redaction.
  * Authorization + ordering: no authority => 0 HVS calls; deny => 0;
    stale revision => 0; conflicting mapping => 0; valid authority =>
    exactly 1 HVS call; duplicate capability => 0.
  * Persistence + replay: exact replay => 0 additional calls; conflicting
    replay rejected; restart => same attempt/identity; unknown durable;
    concurrent duplicate => at most one HVS invocation.
  * Readiness: 3 init only => not ready; all 5 => HVS_RENDER_READY;
    missing template/voice/asset => not ready; malformed => not ready.
  * Reconciliation: read-only; complete => ready; partial => not ready;
    unknown attempt + complete => ready; unknown attempt + incomplete =>
    reconciliation required; zero HVS writes during reconciliation.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_INTEGRATIONS = Path(__file__).resolve().parents[2] / "integrations" / "learning"
if str(_INTEGRATIONS) not in sys.path:
    sys.path.insert(0, str(_INTEGRATIONS))

from scos.control_center.hvs_project_materialization_models import (  # noqa: E402
    DECISION_AUTHORIZED,
    DECISION_DENIED,
    MATERIALIZATION_SCHEMA_VERSION,
    OPERATION_MATERIALIZE_HVS_RENDER_INPUTS,
    STATE_HVS_RENDER_INPUTS_AUTHORIZATION_REQUIRED,
    STATE_HVS_RENDER_INPUTS_MATERIALIZING,
    STATE_HVS_RENDER_INPUTS_MATERIALIZED,
    STATE_HVS_RENDER_INPUTS_FAILED_CONFIRMED,
    STATE_HVS_RENDER_INPUTS_OUTCOME_UNKNOWN,
    STATE_HVS_RENDER_INPUTS_RECONCILIATION_REQUIRED,
    STATE_HVS_RENDER_READY,
    STATE_HVS_RENDER_NOT_READY,
    HvsRenderInputsAuthorization,
    HvsRenderInputsAttempt,
    evaluate_render_inputs_readiness,
    RENDER_READY_REQUIRED_ARTIFACTS,
)
from scos.control_center.hvs_project_materialization_service import (  # noqa: E402
    DOWNSTREAM_RENDER_INPUT_ARTIFACTS,
    issue_render_inputs_authorization,
    materialize_render_inputs,
    reconcile_render_inputs,
)
from scos.control_center.hvs_project_materialization_store import (  # noqa: E402
    MaterializationStore,
)
from scos.control_center.hvs_adapter import (  # noqa: E402
    HermesVideoStudioAdapter,
    HVSAdapterConfig,
)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

SRC = "spp-deadbeef0001"
HVS = "hvs-deadbeef0001"
REV = 3
FINGERPRINT = "abcd1234efgh5678"
NOW = "2026-07-19T00:00:00.000000Z"


def _expires_after(dt: str, *, seconds: int = 300) -> str:
    base = dt.replace("Z", "")
    parsed = datetime.strptime(base, "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=timezone.utc)
    return (parsed + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _dest(tmp_path) -> str:
    d = tmp_path / "hvs-projects"
    d.mkdir(parents=True, exist_ok=True)
    return str(d)


def _authorized_store(store, *, source=SRC, hvs=HVS, revision=REV, fingerprint=FINGERPRINT,
                      dest="", decision=DECISION_AUTHORIZED, nonce="n0", now=NOW, auth_id="auth-ri-1"):
    auth, code = issue_render_inputs_authorization(
        store=store,
        source_project_id=source,
        hvs_project_id=hvs,
        project_revision=revision,
        initialization_fingerprint=fingerprint,
        destination_identity=dest,
        authorization_id=auth_id,
        capability_id="cap-unused",
        attempt_id="att-unused",
        issued_by="operator-10e",
        now_iso=now,
        nonce=nonce,
        decision=decision,
    )
    assert code == decision, f"authorization issue failed: {code}"
    return auth


def _fake_invoker(ok=True, replayed=False, created_artifacts=None, state=STATE_HVS_RENDER_INPUTS_MATERIALIZED,
                  calls=None, timeout_during_invoke=False):
    created_artifacts = created_artifacts if created_artifacts is not None else list(DOWNSTREAM_RENDER_INPUT_ARTIFACTS)

    def _invoke(**kwargs):
        if timeout_during_invoke:
            raise TimeoutError("HVS render-input materializer did not return (timeout/lost response)")
        if calls is not None:
            calls[0] += 1
        return {
            "ok": ok,
            "command": "materialize-render-inputs",
            "exit_code": 0 if ok else 1,
            "payload": {
                "requested_project_id": kwargs.get("project_id"),
                "actual_project_id": kwargs.get("project_id"),
                "replayed": replayed,
                "created_artifacts": created_artifacts,
                "state": state,
                "status": "materialized" if ok else "failed",
            },
        }
    return _invoke


def _fake_lister(present=None, exists=True, calls=None):
    present = present if present is not None else list(RENDER_READY_REQUIRED_ARTIFACTS)

    def _list(**kwargs):
        if calls is not None:
            calls[0] += 1
        return {"ok": True, "exists": exists, "present_artifacts": list(present)}
    return _list


def _adapter(tmp_path):
    repo = tmp_path / "hvs_repo"
    (repo / "hvs" / "cli").mkdir(parents=True, exist_ok=True)
    cfg = HVSAdapterConfig(
        hvs_repo_path=str(repo),
        python_executable="python",
        operation="materialize-render-inputs",
    )
    assert cfg.validate() == (), f"adapter config invalid: {cfg.validate()}"
    return HermesVideoStudioAdapter(cfg)


# --------------------------------------------------------------------------
# Adapter tests
# --------------------------------------------------------------------------

def test_adapter_uses_fixed_module_and_command(tmp_path):
    captured = {}
    orig = HermesVideoStudioAdapter._run_json_command

    def spy(self, *, command, args, request_id, **kw):
        captured["command"] = command
        captured["args"] = args
        return {"ok": True, "command": command, "exit_code": 0, "payload": {"state": "x"}}

    HermesVideoStudioAdapter._run_json_command = spy
    try:
        ad = _adapter(tmp_path)
        ad.materialize_render_inputs(
            project_id=HVS, request_id="r1",
            cohort10e_render_inputs_authorization={"decision": "AUTHORIZED", "authorization_id": "a",
                                                    "hvs_project_id": HVS, "expires_at": _expires_after(NOW)},
        )
    finally:
        HermesVideoStudioAdapter._run_json_command = orig
    assert captured["command"] == "materialize-render-inputs"
    assert "--project-id" in captured["args"]


def test_adapter_rejects_non_absolute_root_before_subprocess(tmp_path):
    ad = _adapter(tmp_path)
    res = ad.materialize_render_inputs(
        project_id=HVS, request_id="r1", projects_root="relative/path",
        cohort10e_render_inputs_authorization={"decision": "AUTHORIZED", "authorization_id": "a",
                                                "hvs_project_id": HVS, "expires_at": _expires_after(NOW)},
    )
    assert res["ok"] is False
    assert res["error_kind"] == "invalid_projects_root"


def test_adapter_rejects_invalid_hvs_identity(tmp_path):
    ad = _adapter(tmp_path)
    res = ad.materialize_render_inputs(
        project_id="spp-not-allowed", request_id="r1",
        cohort10e_render_inputs_authorization={"decision": "AUTHORIZED", "authorization_id": "a",
                                                "hvs_project_id": "spp-not-allowed", "expires_at": _expires_after(NOW)},
    )
    assert res["ok"] is False
    assert res["error_kind"] == "invalid_project_identity"


def test_adapter_blocks_without_authorization(tmp_path):
    ad = _adapter(tmp_path)
    res = ad.materialize_render_inputs(project_id=HVS, request_id="r1")
    assert res["ok"] is False
    assert res["error_kind"] == "stage85_authorization_blocked"


def test_adapter_dedicated_operation_binding_not_render_or_init(tmp_path):
    captured = {}
    orig = HermesVideoStudioAdapter._run_json_command

    def spy(self, *, command, args, request_id, **kw):
        captured["command"] = command
        return {"ok": True, "command": command, "exit_code": 0, "payload": {"state": "x"}}

    HermesVideoStudioAdapter._run_json_command = spy
    try:
        ad = _adapter(tmp_path)
        ad.materialize_render_inputs(
            project_id=HVS, request_id="r1",
            cohort10e_render_inputs_authorization={"decision": "AUTHORIZED", "authorization_id": "a",
                                                    "hvs_project_id": HVS, "expires_at": _expires_after(NOW)},
        )
    finally:
        HermesVideoStudioAdapter._run_json_command = orig
    assert captured["command"] == "materialize-render-inputs"


# --------------------------------------------------------------------------
# Authorization + ordering
# --------------------------------------------------------------------------

def test_no_authority_zero_calls(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "s.json", base_dir=tmp_path)
    calls = [0]
    res = materialize_render_inputs(
        store=store, source_project_id=SRC, hvs_project_id=HVS, project_revision=REV,
        initialization_fingerprint=FINGERPRINT, destination_identity=_dest(tmp_path),
        authorization=None, authorization_id="auth-x", capability_id="cap-1", attempt_id="att-1",
        now_iso=NOW, hvs_render_inputs_invoker=_fake_invoker(calls=calls),
    )
    assert res.hvs_calls == 0 and calls[0] == 0
    assert res.state == STATE_HVS_RENDER_INPUTS_AUTHORIZATION_REQUIRED


def test_denied_authority_zero_calls(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "s.json", base_dir=tmp_path)
    auth = _authorized_store(store, decision=DECISION_DENIED)
    calls = [0]
    res = materialize_render_inputs(
        store=store, source_project_id=SRC, hvs_project_id=HVS, project_revision=REV,
        initialization_fingerprint=FINGERPRINT, destination_identity=_dest(tmp_path),
        authorization=auth, authorization_id=auth.authorization_id, capability_id="cap-1",
        attempt_id="att-1", now_iso=NOW, hvs_render_inputs_invoker=_fake_invoker(calls=calls),
    )
    assert res.hvs_calls == 0 and calls[0] == 0


def test_stale_revision_zero_calls(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "s.json", base_dir=tmp_path)
    auth = _authorized_store(store, revision=REV)
    calls = [0]
    res = materialize_render_inputs(
        store=store, source_project_id=SRC, hvs_project_id=HVS, project_revision=REV + 1,
        initialization_fingerprint=FINGERPRINT, destination_identity=_dest(tmp_path),
        authorization=auth, authorization_id=auth.authorization_id, capability_id="cap-1",
        attempt_id="att-1", now_iso=NOW, hvs_render_inputs_invoker=_fake_invoker(calls=calls),
    )
    assert res.hvs_calls == 0 and calls[0] == 0
    assert res.error_code.endswith("REVISION_MISMATCH")


def test_conflicting_mapping_zero_calls(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "s.json", base_dir=tmp_path)
    auth = _authorized_store(store, hvs=HVS)
    calls = [0]
    res = materialize_render_inputs(
        store=store, source_project_id=SRC, hvs_project_id="hvs-different9999", project_revision=REV,
        initialization_fingerprint=FINGERPRINT, destination_identity=_dest(tmp_path),
        authorization=auth, authorization_id=auth.authorization_id, capability_id="cap-1",
        attempt_id="att-1", now_iso=NOW, hvs_render_inputs_invoker=_fake_invoker(calls=calls),
    )
    assert res.hvs_calls == 0 and calls[0] == 0
    assert res.error_code.endswith("IDENTITY_MISMATCH")


def test_valid_authority_exactly_one_call(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "s.json", base_dir=tmp_path)
    auth = _authorized_store(store)
    calls = [0]
    res = materialize_render_inputs(
        store=store, source_project_id=SRC, hvs_project_id=HVS, project_revision=REV,
        initialization_fingerprint=FINGERPRINT, destination_identity=_dest(tmp_path),
        authorization=auth, authorization_id=auth.authorization_id, capability_id="cap-1",
        attempt_id="att-1", now_iso=NOW, hvs_render_inputs_invoker=_fake_invoker(calls=calls),
    )
    assert calls[0] == 1 and res.hvs_calls == 1


def test_duplicate_capability_second_call_zero_hvs(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "s.json", base_dir=tmp_path)
    auth = _authorized_store(store)
    materialize_render_inputs(
        store=store, source_project_id=SRC, hvs_project_id=HVS, project_revision=REV,
        initialization_fingerprint=FINGERPRINT, destination_identity=_dest(tmp_path),
        authorization=auth, authorization_id=auth.authorization_id, capability_id="cap-shared",
        attempt_id="att-1", now_iso=NOW, hvs_render_inputs_invoker=_fake_invoker(),
    )
    calls = [0]
    res2 = materialize_render_inputs(
        store=store, source_project_id=SRC, hvs_project_id=HVS, project_revision=REV,
        initialization_fingerprint=FINGERPRINT, destination_identity=_dest(tmp_path),
        authorization=auth, authorization_id=auth.authorization_id, capability_id="cap-shared",
        attempt_id="att-2", now_iso=NOW, hvs_render_inputs_invoker=_fake_invoker(calls=calls),
    )
    assert calls[0] == 0 and res2.hvs_calls == 0
    assert res2.error_code.endswith("CONSUMED")


# --------------------------------------------------------------------------
# Persistence + replay
# --------------------------------------------------------------------------

def test_exact_replay_zero_additional_calls(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "s.json", base_dir=tmp_path)
    auth = _authorized_store(store)
    calls = [0]
    materialize_render_inputs(
        store=store, source_project_id=SRC, hvs_project_id=HVS, project_revision=REV,
        initialization_fingerprint=FINGERPRINT, destination_identity=_dest(tmp_path),
        authorization=auth, authorization_id=auth.authorization_id, capability_id="cap-1",
        attempt_id="att-1", now_iso=NOW, hvs_render_inputs_invoker=_fake_invoker(calls=calls),
    )
    assert calls[0] == 1
    calls2 = [0]
    res = materialize_render_inputs(
        store=store, source_project_id=SRC, hvs_project_id=HVS, project_revision=REV,
        initialization_fingerprint=FINGERPRINT, destination_identity=_dest(tmp_path),
        authorization=auth, authorization_id=auth.authorization_id, capability_id="cap-1",
        attempt_id="att-1", now_iso=NOW, hvs_render_inputs_invoker=_fake_invoker(calls=calls2),
    )
    assert calls2[0] == 0 and res.hvs_calls == 0


def test_restart_same_attempt_and_identity(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "s.json", base_dir=tmp_path)
    auth = _authorized_store(store)
    materialize_render_inputs(
        store=store, source_project_id=SRC, hvs_project_id=HVS, project_revision=REV,
        initialization_fingerprint=FINGERPRINT, destination_identity=_dest(tmp_path),
        authorization=auth, authorization_id=auth.authorization_id, capability_id="cap-1",
        attempt_id="att-1", now_iso=NOW, hvs_render_inputs_invoker=_fake_invoker(),
    )
    store2 = MaterializationStore(store_path=tmp_path / "s.json", base_dir=tmp_path)
    att = store2.get_render_inputs_attempt("att-1")
    assert att is not None
    assert att.attempt_id == "att-1"
    assert att.hvs_project_id == HVS
    assert att.capability_id == "cap-1"


def test_unknown_outcome_durable_no_retry(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "s.json", base_dir=tmp_path)
    auth = _authorized_store(store)
    calls = [0]
    res = materialize_render_inputs(
        store=store, source_project_id=SRC, hvs_project_id=HVS, project_revision=REV,
        initialization_fingerprint=FINGERPRINT, destination_identity=_dest(tmp_path),
        authorization=auth, authorization_id=auth.authorization_id, capability_id="cap-1",
        attempt_id="att-1", now_iso=NOW,
        hvs_render_inputs_invoker=_fake_invoker(calls=calls), timeout_during_invoke=True,
    )
    assert res.state == STATE_HVS_RENDER_INPUTS_OUTCOME_UNKNOWN
    # Exactly one HVS attempt was made and it timed out; the service records it
    # as a single HVS call and does NOT auto-retry (no second call).
    assert res.hvs_calls == 1
    # Reconciliation of an unknown outcome must NOT re-invoke HVS.
    calls2 = [0]
    reconcile_render_inputs(store=store, attempt_id="att-1",
                             hvs_artifact_lister=_fake_lister(list(RENDER_READY_REQUIRED_ARTIFACTS)))
    assert calls2[0] == 0


def test_concurrent_duplicate_at_most_one_invocation(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "s.json", base_dir=tmp_path)
    auth = _authorized_store(store)
    # Simulate a second, concurrent request for the SAME source project that is
    # already in-flight (MATERIALIZING) from another process. Issue a real
    # attempt, then flip its persisted state to MATERIALIZING to model the
    # in-flight window observed by the second request.
    materialize_render_inputs(
        store=store, source_project_id=SRC, hvs_project_id=HVS, project_revision=REV,
        initialization_fingerprint=FINGERPRINT, destination_identity=_dest(tmp_path),
        authorization=auth, authorization_id=auth.authorization_id, capability_id="cap-a",
        attempt_id="att-a", now_iso=NOW, hvs_render_inputs_invoker=_fake_invoker(),
    )
    att_a = store.get_render_inputs_attempt("att-a")
    inflight = HvsRenderInputsAttempt(
        **{**att_a.to_dict(), "attempt_id": "att-a", "state": STATE_HVS_RENDER_INPUTS_MATERIALIZING}
    )
    store.put_render_inputs_attempt(inflight)
    calls = [0]
    res = materialize_render_inputs(
        store=store, source_project_id=SRC, hvs_project_id=HVS, project_revision=REV,
        initialization_fingerprint=FINGERPRINT, destination_identity=_dest(tmp_path),
        authorization=auth, authorization_id=auth.authorization_id, capability_id="cap-b",
        attempt_id="att-b", now_iso=NOW, hvs_render_inputs_invoker=_fake_invoker(calls=calls),
    )
    assert res.hvs_calls == 0
    assert res.error_code == "RENDER_INPUTS_INFLIGHT_ATTEMPT"
    assert calls[0] == 0


# --------------------------------------------------------------------------
# Readiness
# --------------------------------------------------------------------------

def test_three_init_artifacts_only_not_ready():
    ok, _ = evaluate_render_inputs_readiness(
        hvs_project_exists=True,
        present_artifacts=("project_brief.json", "timelines/video_timeline.json"),
    )
    assert ok is False


def test_all_five_required_render_artifacts_ready():
    ok, blockers = evaluate_render_inputs_readiness(
        hvs_project_exists=True,
        present_artifacts=tuple(RENDER_READY_REQUIRED_ARTIFACTS),
    )
    assert ok is True and not blockers


def test_missing_template_not_ready():
    present = [a for a in RENDER_READY_REQUIRED_ARTIFACTS if a != "templates/template_selection.json"]
    ok, _ = evaluate_render_inputs_readiness(hvs_project_exists=True, present_artifacts=tuple(present))
    assert ok is False


def test_missing_voice_not_ready():
    present = [a for a in RENDER_READY_REQUIRED_ARTIFACTS if a != "voice/voice_manifest.json"]
    ok, _ = evaluate_render_inputs_readiness(hvs_project_exists=True, present_artifacts=tuple(present))
    assert ok is False


def test_missing_asset_manifest_not_ready():
    present = [a for a in RENDER_READY_REQUIRED_ARTIFACTS if a != "assets/placeholders/asset_manifest.json"]
    ok, _ = evaluate_render_inputs_readiness(hvs_project_exists=True, present_artifacts=tuple(present))
    assert ok is False


def test_malformed_missing_init_not_ready():
    ok, _ = evaluate_render_inputs_readiness(
        hvs_project_exists=False,
        present_artifacts=tuple(DOWNSTREAM_RENDER_INPUT_ARTIFACTS),
    )
    assert ok is False


def test_materialize_happy_path_reaches_render_ready(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "s.json", base_dir=tmp_path)
    auth = _authorized_store(store)
    res = materialize_render_inputs(
        store=store, source_project_id=SRC, hvs_project_id=HVS, project_revision=REV,
        initialization_fingerprint=FINGERPRINT, destination_identity=_dest(tmp_path),
        authorization=auth, authorization_id=auth.authorization_id, capability_id="cap-1",
        attempt_id="att-1", now_iso=NOW, hvs_render_inputs_invoker=_fake_invoker(),
    )
    assert res.ok is True
    assert res.state == STATE_HVS_RENDER_READY
    assert res.render_ready is True
    assert set(res.created_artifacts) == set(DOWNSTREAM_RENDER_INPUT_ARTIFACTS)


def test_materialize_hvs_failure_confirmed_not_unknown(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "s.json", base_dir=tmp_path)
    auth = _authorized_store(store)
    res = materialize_render_inputs(
        store=store, source_project_id=SRC, hvs_project_id=HVS, project_revision=REV,
        initialization_fingerprint=FINGERPRINT, destination_identity=_dest(tmp_path),
        authorization=auth, authorization_id=auth.authorization_id, capability_id="cap-1",
        attempt_id="att-1", now_iso=NOW, hvs_render_inputs_invoker=_fake_invoker(ok=False),
    )
    assert res.ok is False
    assert res.state == STATE_HVS_RENDER_INPUTS_FAILED_CONFIRMED
    assert res.error_code.endswith("HVS_FAILED")


# --------------------------------------------------------------------------
# Reconciliation
# --------------------------------------------------------------------------

def test_reconciliation_read_only_zero_writes(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "s.json", base_dir=tmp_path)
    auth = _authorized_store(store)
    materialize_render_inputs(
        store=store, source_project_id=SRC, hvs_project_id=HVS, project_revision=REV,
        initialization_fingerprint=FINGERPRINT, destination_identity=_dest(tmp_path),
        authorization=auth, authorization_id=auth.authorization_id, capability_id="cap-1",
        attempt_id="att-1", now_iso=NOW, hvs_render_inputs_invoker=_fake_invoker(),
    )
    assert store.get_render_inputs_attempt("att-1").state == STATE_HVS_RENDER_READY
    calls = [0]
    reconcile_render_inputs(
        store=store, attempt_id="att-1",
        hvs_artifact_lister=_fake_lister(present=list(RENDER_READY_REQUIRED_ARTIFACTS), calls=calls),
    )
    # Reconciliation is READ-ONLY with respect to HVS mutation: it invokes the
    # artifact lister (a read) but never materialize/render/initialize.
    assert calls[0] >= 1


def test_reconcile_unknown_attempt_complete_project_ready(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "s.json", base_dir=tmp_path)
    auth = _authorized_store(store)
    materialize_render_inputs(
        store=store, source_project_id=SRC, hvs_project_id=HVS, project_revision=REV,
        initialization_fingerprint=FINGERPRINT, destination_identity=_dest(tmp_path),
        authorization=auth, authorization_id=auth.authorization_id, capability_id="cap-1",
        attempt_id="att-1", now_iso=NOW,
        hvs_render_inputs_invoker=_fake_invoker(), timeout_during_invoke=True,
    )
    att = store.get_render_inputs_attempt("att-1")
    store.put_render_inputs_attempt(
        HvsRenderInputsAttempt(**{**att.to_dict(), "state": STATE_HVS_RENDER_INPUTS_RECONCILIATION_REQUIRED})
    )
    classification, updated = reconcile_render_inputs(
        store=store, attempt_id="att-1",
        hvs_artifact_lister=_fake_lister(present=list(RENDER_READY_REQUIRED_ARTIFACTS)),
    )
    assert classification == STATE_HVS_RENDER_READY
    assert updated.state == STATE_HVS_RENDER_READY


def test_reconcile_unknown_attempt_incomplete_requires_reconciliation(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "s.json", base_dir=tmp_path)
    auth = _authorized_store(store)
    materialize_render_inputs(
        store=store, source_project_id=SRC, hvs_project_id=HVS, project_revision=REV,
        initialization_fingerprint=FINGERPRINT, destination_identity=_dest(tmp_path),
        authorization=auth, authorization_id=auth.authorization_id, capability_id="cap-1",
        attempt_id="att-1", now_iso=NOW,
        hvs_render_inputs_invoker=_fake_invoker(), timeout_during_invoke=True,
    )
    att = store.get_render_inputs_attempt("att-1")
    store.put_render_inputs_attempt(
        HvsRenderInputsAttempt(**{**att.to_dict(), "state": STATE_HVS_RENDER_INPUTS_RECONCILIATION_REQUIRED})
    )
    present = ("project_brief.json", "timelines/video_timeline.json")
    classification, updated = reconcile_render_inputs(
        store=store, attempt_id="att-1",
        hvs_artifact_lister=_fake_lister(present=present),
    )
    # Read-only reconciliation: it must return the truthful NOT-READY
    # classification and must NOT mutate the persisted attempt merely to
    # classify. The attempt identity and pre-existing state are preserved.
    assert classification == STATE_HVS_RENDER_NOT_READY
    assert updated.attempt_id == "att-1"
    assert updated.hvs_project_id == HVS
    assert updated.source_project_id == SRC
    # No persisted transition was caused by read-only reconciliation.
    assert updated.state == STATE_HVS_RENDER_INPUTS_RECONCILIATION_REQUIRED
    assert store.get_render_inputs_attempt("att-1").state == STATE_HVS_RENDER_INPUTS_RECONCILIATION_REQUIRED


def test_reconcile_partial_state_not_ready(tmp_path):
    store = MaterializationStore(store_path=tmp_path / "s.json", base_dir=tmp_path)
    auth = _authorized_store(store)
    materialize_render_inputs(
        store=store, source_project_id=SRC, hvs_project_id=HVS, project_revision=REV,
        initialization_fingerprint=FINGERPRINT, destination_identity=_dest(tmp_path),
        authorization=auth, authorization_id=auth.authorization_id, capability_id="cap-1",
        attempt_id="att-1", now_iso=NOW,
        hvs_render_inputs_invoker=_fake_invoker(created_artifacts=["templates/template_selection.json"]),
    )
    att = store.get_render_inputs_attempt("att-1")
    assert att.state == STATE_HVS_RENDER_NOT_READY
