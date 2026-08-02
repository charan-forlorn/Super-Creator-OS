from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
CLI = "scos.control_center.hvs_guided_pilot_intake_cli"
ENV_PREFIX = "SCOS_PILOT_"

# Shared operator roots that must NEVER appear in a browser-facing response.
SHARED_ROOT_MARKERS = (
    "C:/Workspace/scos-paid-pilot",
    "C:\\Workspace\\scos-paid-pilot",
    "scos-paid-pilot-evidence",
)

ROOT_SUFFIXES = (
    "INTAKE_STORE", "PACKET_ADMISSION_STORE", "AUDIT_STORE", "AUTHORIZATION_STORE",
    "MATERIALIZATION_STATE", "HVS_PROJECTS_ROOT", "RENDER_READINESS_STATE",
    "OUTPUT_ROOT", "APPROVED_INPUT_ROOT", "INTAKE_RUNTIME_BASE", "INTAKE_EVIDENCE_BASE",
)

# Keys that identify a server filesystem root. None may cross the browser boundary.
FORBIDDEN_PROJECTION_KEYS = (
    "roots", "runtime_root", "evidence_root", "input_root", "approved_input_root",
    "hvs_projects_root", "output_root", "downloads_root", "backup_root", "restore_root",
    "store_path", "admission_store", "identity_store", "materialization_store",
    "readiness_store", "contracts_root",
)


def _sanitized_env(extra: dict | None = None) -> dict:
    """Build a subprocess env with EVERY SCOS_PILOT_* variable removed first.

    R2.1C section 9: tests must not rely on the parent terminal being clean. A
    stale exported SCOS_PILOT_* value in the parent process previously turned a
    fail-closed assertion green.
    """
    e = {k: v for k, v in os.environ.items() if not k.startswith(ENV_PREFIX)}
    e["PYTHONPATH"] = str(REPO)
    e["PYTHONDONTWRITEBYTECODE"] = "1"
    e["TZ"] = "UTC"
    if extra:
        e.update(extra)
    return e


def _run_raw(op: str, payload: dict, env: dict | None = None) -> tuple[str, str, int]:
    p = subprocess.run(
        [sys.executable, "-B", "-m", CLI, op],
        input=json.dumps(payload), capture_output=True, text=True,
        env=_sanitized_env(env), cwd=str(REPO),
    )
    return p.stdout, p.stderr, p.returncode


def _run(op: str, payload: dict, env: dict | None = None) -> dict:
    out, err, rc = _run_raw(op, payload, env)
    try:
        return json.loads(out.strip() or "{}")
    except Exception:
        return {"_raw": out, "_rc": rc, "_err": err}


def _setup_env(tmp_path: Path) -> dict:
    """All task-owned roots resolved server-side from environment (B1/B2)."""
    inp = tmp_path / "approved-input"
    (inp / "assets").mkdir(parents=True)
    for n, d in {
        "product-front.jpg": b"imgdata",
        "customer-logo.png": b"pngdata",
        "promo-music-31s.mp3": b"mp3data",
    }.items():
        (inp / n).write_bytes(d)
    env = {
        f"{ENV_PREFIX}INTAKE_STORE": str(tmp_path / "intake-store.json"),
        f"{ENV_PREFIX}PACKET_ADMISSION_STORE": str(tmp_path / "adm.json"),
        f"{ENV_PREFIX}AUDIT_STORE": str(tmp_path / "audit.jsonl"),
        f"{ENV_PREFIX}AUTHORIZATION_STORE": str(tmp_path / "auth.json"),
        f"{ENV_PREFIX}MATERIALIZATION_STATE": str(tmp_path / "mat.json"),
        f"{ENV_PREFIX}HVS_PROJECTS_ROOT": str(tmp_path / "hvs-projects"),
        f"{ENV_PREFIX}RENDER_READINESS_STATE": str(tmp_path / "rr.json"),
        f"{ENV_PREFIX}OUTPUT_ROOT": str(tmp_path / "output"),
        f"{ENV_PREFIX}APPROVED_INPUT_ROOT": str(inp),
        f"{ENV_PREFIX}INTAKE_RUNTIME_BASE": str(tmp_path / "runtime"),
        f"{ENV_PREFIX}INTAKE_EVIDENCE_BASE": str(tmp_path / "evidence"),
    }
    return env


def _ready_draft(env: dict, title: str = "Real Promo") -> str:
    d = _run("draft", {
        "safe_project_title": title, "selected_template": "Vertical Product Promo",
        "deadline": "2026-08-15", "commercial_reference": "x",
        "rights_answers": {"asset_owner": "Owned", "identifiable_person": "No",
                           "voice_used": "Not used", "music_used": "Not used",
                           "font_policy": "Licensed"},
        "privacy_answers": {"health_data": "No", "financial_data": "No",
                            "government_identifiers": "No", "child_information": "No"},
    }, env)
    assert d.get("ok"), d
    return d["draft"]["draft_id"]


# --------------------------------------------------------------------------
# Structural leak assertions
# --------------------------------------------------------------------------

def _assert_no_forbidden_keys(obj, path="$"):
    """Structured (not substring) assertion: no root-identity key is projected."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            assert k not in FORBIDDEN_PROJECTION_KEYS, f"root key '{k}' leaked at {path}"
            _assert_no_forbidden_keys(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _assert_no_forbidden_keys(v, f"{path}[{i}]")


def _assert_no_absolute_path(obj, env: dict, path="$"):
    """No absolute path and no configured env VALUE may appear in the response."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            _assert_no_absolute_path(v, env, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _assert_no_absolute_path(v, env, f"{path}[{i}]")
    elif isinstance(obj, str):
        s = obj
        assert not (len(s) > 2 and s[1] == ":" and s[2] in "\\/"), f"absolute path at {path}: {s}"
        assert not s.startswith("\\\\"), f"UNC path at {path}: {s}"
        for var, val in env.items():
            if var.startswith(ENV_PREFIX) and val:
                assert val not in s, f"env value of {var} leaked at {path}"


def _assert_serialized_clean(raw: str, env: dict):
    """Defense in depth: whole-response serialized leak check."""
    for marker in SHARED_ROOT_MARKERS:
        assert marker not in raw, f"shared operator root leaked: {marker}"
    for var, val in env.items():
        if var.startswith(ENV_PREFIX) and val:
            assert val not in raw, f"env value of {var} leaked in serialized response"


def _assert_browser_safe(op: str, payload: dict, env: dict):
    raw, err, rc = _run_raw(op, payload, env)
    res = json.loads(raw.strip())
    _assert_no_forbidden_keys(res)
    _assert_no_absolute_path(res, env)
    _assert_serialized_clean(raw, env)
    assert err.strip() == "", f"{op} polluted stderr: {err[:200]}"
    return res


# --------------------------------------------------------------------------
# R2.1C regression: shared-root fallback + browser path redaction
# --------------------------------------------------------------------------

@pytest.mark.parametrize("op", ["draft", "asset", "consent", "validate"])
def test_no_root_leak_in_browser_projection_for_every_operation(tmp_path: Path, op: str):
    """FAILS against the committed two-path behavior (validate_draft -> roots(pid))."""
    env = _setup_env(tmp_path)
    did = _ready_draft(env, title=f"Leak Probe {op}")
    payloads = {
        "draft": {"safe_project_title": "Leak Probe draft", "deadline": "2026-08-15"},
        "asset": {"draft_id": did, "asset_file": "product-front.jpg"},
        "consent": {"draft_id": did, "safe_reference": "consent.txt",
                    "evidence_text": "ok", "explicit_consent_confirmed": True},
        "validate": {"draft_id": did},
    }
    res = _assert_browser_safe(op, payloads[op], env)
    gen = (res.get("draft") or {}).get("generated") or {}
    assert "roots" not in gen, f"generated.roots projected to browser on op={op}"


def test_created_project_response_is_root_free_but_state_is_task_owned(tmp_path: Path):
    """After creation the browser sees no path, yet real state lives under task roots."""
    env = _setup_env(tmp_path)
    did = _ready_draft(env, "Created Promo")
    for n in ("product-front.jpg", "customer-logo.png", "promo-music-31s.mp3"):
        _run("asset", {"draft_id": did, "asset_file": n}, env)
    _run("consent", {"draft_id": did, "safe_reference": "consent.txt",
                     "evidence_text": "ok", "explicit_consent_confirmed": True}, env)
    _run("validate", {"draft_id": did}, env)
    res = _assert_browser_safe("create", {"draft_id": did, "idempotency_key": "k1"}, env)
    assert res.get("ok") and res.get("replay") is False
    gen = res["draft"]["generated"]
    assert "roots" not in gen
    # A bounded, non-path status may still confirm isolation was provisioned.
    assert gen.get("runtime_isolation", {}).get("status") == "SERVER_MANAGED"
    # Internally, roots WERE used: evidence exists under the task-owned base only.
    ev = Path(env[f"{ENV_PREFIX}INTAKE_EVIDENCE_BASE"])
    assert len(list(ev.rglob("admission-packet.json"))) == 1


def test_get_operation_is_root_free(tmp_path: Path):
    env = _setup_env(tmp_path)
    did = _ready_draft(env, "Get Promo")
    res = _assert_browser_safe("get", {"draft_id": did}, env)
    assert res.get("ok")


# --------------------------------------------------------------------------
# Original R2.1 behavior (preserved)
# --------------------------------------------------------------------------

def test_real_asset_admission_only_no_synthetic(tmp_path: Path):
    env = _setup_env(tmp_path)
    did = _ready_draft(env, "Real Promo")
    r = _run("asset", {"draft_id": did, "asset_file": "product-front.jpg"}, env)
    assert r.get("ok")
    s = _run("sample-asset", {"draft_id": did}, env)
    assert not s.get("ok") and s.get("error_code") == "SAMPLE_ASSET_REJECTED_IN_REAL_MODE"
    t = _run("asset", {"draft_id": did, "asset_file": "customer-logo.png",
                       "evidence_base": "/evil", "file_path": "/etc/passwd"}, env)
    assert t.get("ok")


def test_exactly_one_creation_and_replay_idempotency(tmp_path: Path):
    env = _setup_env(tmp_path)
    did = _ready_draft(env, "Real Promo2")
    for n in ("product-front.jpg", "customer-logo.png", "promo-music-31s.mp3"):
        _run("asset", {"draft_id": did, "asset_file": n}, env)
    _run("consent", {"draft_id": did, "safe_reference": "consent.txt",
                     "evidence_text": "ok", "explicit_consent_confirmed": True}, env)
    _run("validate", {"draft_id": did}, env)
    c1 = _run("create", {"draft_id": did, "idempotency_key": "k1"}, env)
    assert c1.get("ok") and c1.get("replay") is False
    c2 = _run("create", {"draft_id": did, "idempotency_key": "k1"}, env)
    assert c2.get("ok") and c2.get("replay") is True
    c3 = _run("create", {"draft_id": did, "idempotency_key": "k2"}, env)
    assert not c3.get("ok") and c3.get("error_code") == "CONFLICTING_REPLAY_REJECTED"
    ev = Path(env[f"{ENV_PREFIX}INTAKE_EVIDENCE_BASE"])
    assert len(list(ev.rglob("admission-packet.json"))) == 1


# --------------------------------------------------------------------------
# Fail-closed root configuration
# --------------------------------------------------------------------------

def test_missing_env_fails_closed(tmp_path: Path):
    """Without task-owned roots configured, the CLI must NOT fall back."""
    d = _run("draft", {"safe_project_title": "X", "deadline": "2026-08-15"})
    assert d.get("error_code") == "TASK_ROOTS_UNAVAILABLE", d


def test_missing_env_test_inherits_no_parent_scos_pilot_variables(tmp_path: Path):
    """Contamination regression (R2.1C section 9).

    A misleading SCOS_PILOT_* value in the PARENT process must not make the
    missing-environment case pass falsely: the subprocess env is sanitized.
    """
    poisoned = dict(os.environ)
    poisoned[f"{ENV_PREFIX}INTAKE_STORE"] = str(tmp_path / "poison.json")
    poisoned[f"{ENV_PREFIX}INTAKE_EVIDENCE_BASE"] = str(tmp_path / "poison-ev")
    prior = {k: os.environ.get(k) for k in poisoned if k.startswith(ENV_PREFIX)}
    try:
        for k in prior:
            os.environ[k] = poisoned[k]
        assert any(k.startswith(ENV_PREFIX) for k in os.environ), "parent not contaminated"
        sanitized = _sanitized_env()
        assert not [k for k in sanitized if k.startswith(ENV_PREFIX)], "sanitizer leaked vars"
        d = _run("draft", {"safe_project_title": "X", "deadline": "2026-08-15"})
        assert d.get("error_code") == "TASK_ROOTS_UNAVAILABLE", d
    finally:
        for k, v in prior.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@pytest.mark.parametrize("suffix", ROOT_SUFFIXES)
def test_each_missing_required_root_fails_closed(tmp_path: Path, suffix: str):
    env = _setup_env(tmp_path)
    env.pop(f"{ENV_PREFIX}{suffix}")
    d = _run("draft", {"safe_project_title": "X", "deadline": "2026-08-15"}, env)
    assert d.get("error_code") == "TASK_ROOTS_UNAVAILABLE", (suffix, d)
    assert not d.get("ok")


@pytest.mark.parametrize("bad", ["relative/path", "./rel", ""])
def test_relative_root_fails_closed(tmp_path: Path, bad: str):
    env = _setup_env(tmp_path)
    env[f"{ENV_PREFIX}INTAKE_STORE"] = bad
    d = _run("draft", {"safe_project_title": "X", "deadline": "2026-08-15"}, env)
    assert not d.get("ok")
    assert d.get("error_code") == "TASK_ROOTS_UNAVAILABLE", d


def test_repository_local_root_fails_closed(tmp_path: Path):
    """A root inside the git repository must be rejected (no repo-local fallback)."""
    env = _setup_env(tmp_path)
    env[f"{ENV_PREFIX}INTAKE_STORE"] = str(REPO / "scos" / "r21c-should-not-exist.json")
    d = _run("draft", {"safe_project_title": "X", "deadline": "2026-08-15"}, env)
    assert not d.get("ok")
    assert d.get("error_code") == "TASK_ROOTS_UNAVAILABLE", d
    assert not (REPO / "scos" / "r21c-should-not-exist.json").exists()


def test_error_response_does_not_leak_paths_or_env(tmp_path: Path):
    env = _setup_env(tmp_path)
    env[f"{ENV_PREFIX}INTAKE_STORE"] = "relative/path"
    raw, err, _ = _run_raw("draft", {"safe_project_title": "X"}, env)
    res = json.loads(raw.strip())
    assert not res.get("ok")
    _assert_no_absolute_path(res, env)
    _assert_serialized_clean(raw, env)
    assert err.strip() == ""


# --------------------------------------------------------------------------
# Malformed / unknown input and machine protocol
# --------------------------------------------------------------------------

def test_unknown_operation_and_malformed_input(tmp_path: Path):
    env = _setup_env(tmp_path)
    d = _run("definitely-not-an-op", {}, env)
    assert not d.get("ok") and d.get("error_code") == "UNKNOWN_OPERATION"
    p = subprocess.run(
        [sys.executable, "-B", "-m", CLI, "draft"], input="{not json",
        capture_output=True, text=True, env=_sanitized_env(env), cwd=str(REPO),
    )
    res = json.loads(p.stdout.strip())
    assert res.get("error_code") == "REQUEST_MALFORMED"


def test_stdout_is_exactly_one_bounded_json_object(tmp_path: Path):
    env = _setup_env(tmp_path)
    raw, err, _ = _run_raw("draft", {"safe_project_title": "P", "deadline": "2026-08-15"}, env)
    assert len([ln for ln in raw.strip().splitlines() if ln.strip()]) == 1
    assert isinstance(json.loads(raw.strip()), dict)
    assert err.strip() == ""


def test_browser_provided_path_fields_are_rejected(tmp_path: Path):
    """Browser path fields must not steer storage: state stays under task roots."""
    env = _setup_env(tmp_path)
    evil = tmp_path / "evil-store.json"
    d = _run("draft", {
        "safe_project_title": "Path Smuggle", "deadline": "2026-08-15",
        "store_path": str(evil), "evidence_base": str(tmp_path / "evil-ev"),
        "runtime_base": str(tmp_path / "evil-rt"),
        "approved_input_root": str(tmp_path / "evil-in"),
        "file_path": str(tmp_path / "evil.png"),
    }, env)
    assert d.get("ok")
    assert not evil.exists(), "browser store_path was honored"
    assert Path(env[f"{ENV_PREFIX}INTAKE_STORE"]).exists()


def test_asset_traversal_is_rejected(tmp_path: Path):
    env = _setup_env(tmp_path)
    did = _ready_draft(env, "Traversal")
    for bad in ("../outside.png", "/abs/product.png", "..\\outside.png"):
        r = _run("asset", {"draft_id": did, "asset_file": bad}, env)
        assert not r.get("ok"), bad
        assert r.get("error_code") in {"ASSET_PATH_REJECTED", "ASSET_PATH_ESCAPE"}, (bad, r)


# --------------------------------------------------------------------------
# Negative side-effect counters
# --------------------------------------------------------------------------

def test_negative_cases_cause_no_side_effects(tmp_path: Path):
    """Every rejected request must create no project and no external effect."""
    env = _setup_env(tmp_path)
    hvs = Path(env[f"{ENV_PREFIX}HVS_PROJECTS_ROOT"])
    out = Path(env[f"{ENV_PREFIX}OUTPUT_ROOT"])
    ev = Path(env[f"{ENV_PREFIX}INTAKE_EVIDENCE_BASE"])

    did = _ready_draft(env, "No Side Effects")
    _run("asset", {"draft_id": did, "asset_file": "../escape.png"}, env)
    _run("create", {"draft_id": did, "idempotency_key": "nope"}, env)  # not ready
    _run("draft", {"safe_project_title": "Z"}, {})                     # no roots
    _run("get", {"draft_id": "draft-does-not-exist"}, env)

    assert list(ev.rglob("admission-packet.json")) == []   # canonical creations = 0
    assert not hvs.exists() or list(hvs.iterdir()) == []   # materialized projects = 0
    assert not out.exists() or list(out.iterdir()) == []   # render outputs = 0
    assert not Path(env[f"{ENV_PREFIX}RENDER_READINESS_STATE"]).exists()
    for marker in SHARED_ROOT_MARKERS:
        assert not Path(marker).joinpath("pilot-no-side-effects").exists()


def test_partial_and_corrupt_store_fail_closed(tmp_path: Path):
    env = _setup_env(tmp_path)
    Path(env[f"{ENV_PREFIX}INTAKE_STORE"]).write_text("{ corrupt", encoding="utf-8")
    raw, err, _ = _run_raw("get", {"draft_id": "draft-x"}, env)
    res = json.loads(raw.strip())
    assert not res.get("ok")
    _assert_serialized_clean(raw, env)
    assert "Traceback" not in err
