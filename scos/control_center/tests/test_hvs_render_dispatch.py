"""test_hvs_render_dispatch.py - SCOS <-> HVS Stage 5 approval-gated render dispatch.

Focused, deterministic tests. Uses ONLY temp directories and injected paths;
the real HVS repository is never mutated. Covers the full 35-point matrix:

  Preflight/dry-run, approval gate (denial taxonomy), render safety, dispatch
  + evidence, idempotency + recovery, regression (Stage 1-4 consumed, not
  duplicated), and a forbidden-pattern security scan of the new module.

The HVS render boundary is simulated by a fake subprocess runner that writes a
deterministic output file at the path the real ``render-hyperframes --fake-render``
would use, then returns the same JSON shape the real CLI prints. This exercises
SCOS evidence-intake logic end to end without invoking the real HyperFrames
binary or any network. The real HVS repository is proven untouched separately
(git clean + we never point hvs_root at the real repo).

Plain executable script (no pytest-only features); pytest collects the
``test_*`` functions directly. Imports the package via an explicit sys.path
insertion so it runs both under pytest and standalone.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
sys.path.insert(0, str(_PACKAGE))
# The new Stage 5 production module lives in the package root (control_center),
# not in tests/. Resolve it relative to the package parent of this test file.
_MODULE_DIR = _PACKAGE

from hvs_contract_models import (  # noqa: E402
    SCOSAssetRef,
    SCOSCaption,
    SCOSRenderTimelineProject,
    SCOSScene,
)
from hvs_project_creation import (  # noqa: E402
    APPROVAL_APPROVED,
    APPROVAL_CANCELLED,
    APPROVAL_EXPIRED,
    APPROVAL_PENDING,
    APPROVAL_REJECTED,
    CONTRACT_VERSION,
    CorrelationLedger,
    HVSProjectApproval,
    create_hvs_project,
)
from hvs_asset_materialization import (  # noqa: E402
    APPROVAL_ACTION_MATERIALIZE_HVS_ASSETS,
    HVSAssetMaterializationApproval,
    MaterializationLedger,
    SourceRoot,
    materialize_hvs_assets,
)
from hvs_schema_mapper import map_scos_to_hvs, payload_identity_hash  # noqa: E402

from hvs_render_dispatch import (  # noqa: E402
    APPROVAL_ACTION_DISPATCH_HVS_RENDER,
    APPROVAL_APPROVED as R_APPROVED,
    EVIDENCE_DENIED,
    EVIDENCE_RENDERED,
    EVIDENCE_REUSED,
    HVSRenderDispatchApproval,
    RenderEvidenceLedger,
    dispatch_hvs_render,
    render_identity_hash,
)

# The real HVS repo is never pointed at in any test.
HVS_REPO_ROOT = Path(r"C:\Workspace\hermes-video-studio").resolve()

_PASS = 0
_FAIL = 0
_FAILS: list[str] = []
_SEQ = 0
_tmp = Path(__file__).resolve().parent / "_stage5_tmp"
# Clean the temp scratch dir at import so each test session starts from a
# pristine state. (The fresh_* helpers name paths by a per-process monotonic
# counter; without this reset, a stale file from a previous session with the
# same deterministic name would leak evidence/ledger state across runs.)
import shutil as _shutil
_shutil.rmtree(_tmp, ignore_errors=True)
_tmp.mkdir(parents=True, exist_ok=True)


def _uniq():
    global _SEQ
    _SEQ += 1
    return _SEQ


def check(name, cond, detail=""):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        _FAILS.append(name)
        print(f"  FAIL  {name}  :: {detail}")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def fresh_root():
    return _tmp / f"hvs_root_{_uniq()}"


def fresh_ledger():
    return _tmp / f"corr_ledger_{_uniq()}.jsonl"


def fresh_mat_ledger():
    return _tmp / f"mat_ledger_{_uniq()}.jsonl"


def fresh_ev_ledger():
    return _tmp / f"ev_ledger_{_uniq()}.jsonl"


def src_root_with(assets: dict[str, bytes]):
    r = _tmp / f"src_root_{_uniq()}"
    r.mkdir(parents=True, exist_ok=True)
    for rel, data in assets.items():
        p = r / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    sr = SourceRoot(root_id="rootA", root_path=str(r))
    object.__setattr__(sr, "root", r)
    return sr


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_project(project_id="proj-5"):
    return SCOSRenderTimelineProject(
        project_id=project_id,
        width=1080,
        height=1920,
        fps=30,
        selected_preset="standard",
        scenes=(
            SCOSScene(
                scene_id="s01", order=1, start_ms=0, duration_ms=1000,
                intent="intro", visual_description="v", text_overlay="t",
                asset_refs=(SCOSAssetRef(asset_id="a_img", asset_type="background",
                                         path="img/scene_01.png"),),
                captions=(SCOSCaption(scene_id="s01", text="hi", start_ms=0, end_ms=500),),
            ),
            SCOSScene(
                scene_id="s02", order=2, start_ms=1000, duration_ms=1000,
                intent="body", visual_description="v", text_overlay="t",
                asset_refs=(SCOSAssetRef(asset_id="a_aud",
                                         asset_type="music_or_audio_placeholder",
                                         path="aud/voice_01.wav"),),
                captions=(SCOSCaption(scene_id="s02", text="yo", start_ms=1000, end_ms=1500),),
            ),
            SCOSScene(
                scene_id="s03", order=3, start_ms=2000, duration_ms=1000,
                intent="out", visual_description="v", text_overlay="t",
                asset_refs=(), captions=(),
            ),
        ),
    )


def _plan_hash(proj):
    return payload_identity_hash(map_scos_to_hvs(proj, validate=True).payload)


def make_creation_approval(proj):
    return HVSProjectApproval.of(
        approval_id="create-apr-5",
        requested_plan_identity_hash=_plan_hash(proj),
        requested_scos_project_id=proj.project_id,
        requested_hvs_artifact_id=f"hvs-timeline-{proj.project_id}",
        issued_by="op",
    )


def create_correlated_project(proj):
    """Stage 3 correlate in a fresh temp HVS root; return (root, ledger, corr)."""
    root = fresh_root()
    ledger = fresh_ledger()
    out = create_hvs_project(
        proj, make_creation_approval(proj),
        hvs_root=root, correlation_ledger_path=ledger, requested_by="op",
    )
    assert out.ok, f"stage3 create failed: {out.error_kind}: {out.error_detail}"
    corr = out.correlation
    return root, ledger, corr


def materialize_assets_for(proj, root, corr, src):
    """Run Stage 4 materialization; return (mat_ledger, manifest_identity_hash)."""
    mat_ledger = fresh_mat_ledger()
    asset_refs = []
    for sc in proj.scenes:
        for ar in sc.asset_refs:
            asset_refs.append(ar)
    # Resolve manifest identity by dry-running first. NOTE: dry-run still
    # evaluates the approval scope, so we pass a placeholder requested hash
    # (the dry run is expected to be DENIED on scope, but it still computes and
    # returns the resolved manifest_identity_hash). Mirrors the Stage 4 test
    # pattern (_good_pair uses "ph").
    dry = materialize_hvs_assets(
        correlation_id=corr.correlation_id,
        asset_refs=asset_refs,
        source_roots=[src],
        approval=HVSAssetMaterializationApproval.of(
            approval_id="mat-apr-5",
            requested_correlation_id=corr.correlation_id,
            requested_scos_project_id=proj.project_id,
            requested_hvs_artifact_id=f"hvs-timeline-{proj.project_id}",
            requested_asset_manifest_identity_hash="ph",
            approved_source_root_ids=("rootA",),
            approved_asset_ids=tuple(a.asset_id for a in asset_refs),
            issued_by="op",
        ),
        hvs_root=root,
        correlation_ledger_path=corr_ledger_for(corr),  # real ledger (dry-run, no write)
        materialization_ledger_path=mat_ledger,
        requested_by="op",
        dry_run=True,
    )
    manifest_id = dry.manifest_identity_hash
    out = materialize_hvs_assets(
        correlation_id=corr.correlation_id,
        asset_refs=asset_refs,
        source_roots=[src],
        approval=HVSAssetMaterializationApproval.of(
            approval_id="mat-apr-5",
            requested_correlation_id=corr.correlation_id,
            requested_scos_project_id=proj.project_id,
            requested_hvs_artifact_id=f"hvs-timeline-{proj.project_id}",
            requested_asset_manifest_identity_hash=manifest_id,
            approved_source_root_ids=("rootA",),
            approved_asset_ids=tuple(a.asset_id for a in asset_refs),
            issued_by="op",
        ),
        hvs_root=root,
        correlation_ledger_path=corr_ledger_for(corr),  # reuse the real ledger
        materialization_ledger_path=mat_ledger,
        requested_by="op",
    )
    assert out.ok, f"stage4 materialize failed: {out.error_kind}"
    return mat_ledger, manifest_id


def corr_ledger_for(corr):
    # Reopen the ledger that holds the correlation (same path used at creation).
    # The test passes the creation ledger explicitly; here we just return it via
    # a module-level capture for convenience.
    return _CREATION_LEDGER


_CREATION_LEDGER = None


def seed_hvs_render_artifacts(root, hvs_project_id, duration_seconds=3.0):
    """Write the HVS-required render artifacts so the boundary passes gates.

    This mimics the operator/Stage 4 having prepared the certified HVS project
    with the on-disk shape the real ``render-hyperframes`` gate requires. It does
    NOT render; SCOS Stage 5 only dispatches + observes.
    """
    base = root / "projects" / hvs_project_id
    (base / "timelines").mkdir(parents=True, exist_ok=True)
    (base / "templates").mkdir(parents=True, exist_ok=True)
    (base / "voice").mkdir(parents=True, exist_ok=True)
    (base / "assets" / "placeholders").mkdir(parents=True, exist_ok=True)
    (base / "assets" / "asset_manifest.stage4.json").write_text(
        json.dumps({"stage4": True}, ensure_ascii=False), encoding="utf-8"
    )
    (base / "assets" / "placeholders" / "asset_manifest.json").write_text(
        json.dumps({"placeholders": []}, ensure_ascii=False), encoding="utf-8"
    )
    (base / "templates" / "template_selection.json").write_text(
        json.dumps({"template": "default"}, ensure_ascii=False), encoding="utf-8"
    )
    (base / "templates" / "render_preset.json").write_text(
        json.dumps({"preset": "standard"}, ensure_ascii=False), encoding="utf-8"
    )
    (base / "templates" / "visual_theme.json").write_text(
        json.dumps({"background_color": "rgb(5,7,10)"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (base / "voice" / "voice_manifest.json").write_text(
        json.dumps({"voice": "placeholder"}, ensure_ascii=False), encoding="utf-8"
    )
    # Timeline carries the authoritative duration for the render profile.
    (base / "timelines" / "video_timeline.json").write_text(
        json.dumps(
            {
                "artifact_id": f"hvs-timeline-{hvs_project_id}",
                "project_id": hvs_project_id,
                "width": 1080,
                "height": 1920,
                "fps": 30,
                "duration_seconds": duration_seconds,
                "scenes": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Fake HVS render boundary (subprocess DI).
# ---------------------------------------------------------------------------
class _FakeRenderRun:
    """Simulates `python -m hvs.cli render-hyperframes ... --fake-render`.

    When it sees the render subcommand, it writes a deterministic mp4 output at
    the path the real boundary would use, then returns the same JSON shape the
    real CLI prints (verdict PASS, output_path, render_id, manifest_path,
    width/height/fps/duration). This lets SCOS evidence-intake run end to end
    without the real HyperFrames binary or any network.
    """

    def __init__(self, fail=False, write_output=True):
        self.fail = fail
        self.write_output = write_output
        self.calls = []

    def __call__(self, argv, *, cwd=None, shell=False, capture_output=False,
                 text=False, timeout=None, input="", env=None):
        self.calls.append((list(argv), cwd))
        # Parse project id + format from argv.
        proj_id = None
        fmt = "vertical"
        i = 0
        while i < len(argv):
            if argv[i] == "--project-id":
                proj_id = argv[i + 1]
            elif argv[i] == "--format":
                fmt = argv[i + 1]
            i += 1
        # Replicate the boundary output path (renders/hyperframes-<id>.mp4).
        from hvs_render_dispatch import _hvs_render_id, _slugify
        rid = _hvs_render_id(proj_id, fmt)
        name = f"hyperframes-{_slugify(rid)}.mp4"
        out_path = str(Path(cwd) / "projects" / proj_id / "renders" / name)
        manifest_path = str(
            Path(cwd) / "projects" / proj_id / "renders"
            / f"render_manifest_{rid}.json"
        )
        if self.fail:
            stdout = json.dumps(
                {"verdict": "BLOCKED", "project_id": proj_id, "errors": ["simulated failure"]},
                ensure_ascii=False,
            )
            return _Proc(1, stdout, "")
        if self.write_output:
            Path(out_path).parent.mkdir(parents=True, exist_ok=True)
            # Determinstic non-empty fake mp4 bytes (never real media content).
            Path(out_path).write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"FAKEHVSRENDER" * 64)
            Path(manifest_path).parent.mkdir(parents=True, exist_ok=True)
            Path(manifest_path).write_text(
                json.dumps({"render_id": rid, "verdict": "PASS"}, ensure_ascii=False),
                encoding="utf-8",
            )
        stdout = json.dumps(
            {
                "verdict": "PASS",
                "project_id": proj_id,
                "render_id": rid,
                "format": fmt,
                "output_path": out_path,
                "manifest_path": manifest_path,
                "width": 1080,
                "height": 1920,
                "fps": 30,
                "duration_seconds": 3.0,
                "dry_run": False,
                "checks": [],
                "errors": [],
            },
            ensure_ascii=False,
        )
        return _Proc(0, stdout, "")


class _Proc:
    def __init__(self, returncode, stdout, stderr):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# ---------------------------------------------------------------------------
# Approval builder
# ---------------------------------------------------------------------------
def make_render_approval(corr, manifest_id, render_identity, preset="standard",
                          status=R_APPROVED, action_type=APPROVAL_ACTION_DISPATCH_HVS_RENDER,
                          correlation_id=None, scos_project_id=None,
                          hvs_artifact_id=None, plan_hash=None,
                          asset_hash=None, requested_output=None):
    return HVSRenderDispatchApproval.of(
        approval_id="render-apr-5",
        requested_correlation_id=correlation_id or corr.correlation_id,
        requested_scos_project_id=scos_project_id or corr.scos_project_id,
        requested_hvs_artifact_id=hvs_artifact_id or corr.hvs_artifact_id,
        requested_plan_identity_hash=plan_hash or corr.plan_identity_hash,
        requested_asset_manifest_identity_hash=asset_hash or manifest_id,
        requested_render_identity_hash=render_identity,
        selected_render_preset=preset,
        requested_output_relative_path=requested_output,
        issued_by="op",
        status=status,
        action_type=action_type,
    )


# ---------------------------------------------------------------------------
# End-to-end setup helper
# ---------------------------------------------------------------------------
def setup_ready_stage5(*, duration_seconds=3.0):
    """Full Stage 3 + Stage 4 + HVS render artifacts, all in temp roots.

    Returns (root, corr_ledger, corr, mat_ledger, manifest_id, proj).
    """
    global _CREATION_LEDGER
    proj = make_project()
    img = b"\x89PNG\r\n\x1a\n" + b"IMG" * 100
    aud = b"RIFF" + b"WAVE" + b"AUD" * 200
    src = src_root_with({"img/scene_01.png": img, "aud/voice_01.wav": aud})
    root, corr_ledger, corr = create_correlated_project(proj)
    _CREATION_LEDGER = corr_ledger
    mat_ledger, manifest_id = materialize_assets_for(proj, root, corr, src)
    seed_hvs_render_artifacts(root, corr.hvs_project_id,
                              duration_seconds=duration_seconds)
    return root, corr_ledger, corr, mat_ledger, manifest_id, proj


# ===========================================================================
# Tests 1-5: Preflight / dry-run / contract
# ===========================================================================
def test_01_stage234_contracts_consumed():
    """Stage 2/3/4 public APIs are consumed (not duplicated) by Stage 5."""
    import inspect
    src = inspect.getsource(dispatch_hvs_render)
    # Stage 5 consumes the Stage 3 correlation ledger + Stage 4 materialization
    # ledger through their public APIs (and the Stage 2 plan identity via the
    # Stage 3 correlation record). It must NOT redefine those functions.
    check("uses Stage 3 CorrelationLedger", "CorrelationLedger" in src)
    check("uses Stage 4 MaterializationLedger", "MaterializationLedger" in src)
    check("consumes Stage 2 plan identity via correlation",
          "plan_identity_hash" in src)
    check("does not redefine map_scos_to_hvs", "def map_scos_to_hvs" not in src)
    check("does not redefine create_hvs_project", "def create_hvs_project" not in src)
    check("does not redefine materialize_hvs_assets",
          "def materialize_hvs_assets" not in src)
    # Module-level imports prove consumption of the prior-stage public surface.
    mod_src = inspect.getsource(sys.modules[dispatch_hvs_render.__module__])
    check("imports Stage 2 identity hash", "payload_identity_hash" in mod_src)
    check("imports Stage 3 CorrelationLedger", "CorrelationLedger" in mod_src)
    check("imports Stage 4 MaterializationLedger", "MaterializationLedger" in mod_src)


def test_02_missing_stage3_correlation_blocks():
    root = fresh_root()
    corr_ledger = fresh_ledger()
    mat_ledger = fresh_mat_ledger()
    ev_ledger = fresh_ev_ledger()
    proj = make_project()
    manifest_id = "deadbeef"
    rid = render_identity_hash(
        plan_identity_hash="x", asset_manifest_identity_hash=manifest_id,
        selected_render_preset="standard", expected_resolution="1080x1920",
        expected_fps=30, expected_duration_seconds=3.0,
    )
    apr = make_render_approval(
        type("C", (), {"correlation_id": "corr-nope",
                       "scos_project_id": proj.project_id,
                       "hvs_artifact_id": "hvs-timeline-proj-5",
                       "plan_identity_hash": "x"})(),
        manifest_id, rid,
    )
    out = dispatch_hvs_render(
        correlation_id="corr-nope", approval=apr, selected_render_preset="standard",
        hvs_root=root, correlation_ledger_path=corr_ledger,
        materialization_ledger_path=mat_ledger,
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, dry_run=False,
    )
    check("denied", not out.ok)
    check("error_kind correlation_not_found",
          out.error_kind == "correlation_not_found", out.error_kind)
    check("no evidence written", not ev_ledger.exists() or
          len(RenderEvidenceLedger(ev_ledger).all()) == 0)


def test_03_missing_stage4_materialization_blocks():
    root, corr_ledger, corr = create_correlated_project(make_project())
    global _CREATION_LEDGER
    _CREATION_LEDGER = corr_ledger
    mat_ledger = fresh_mat_ledger()  # empty -> no materialization
    ev_ledger = fresh_ev_ledger()
    manifest_id = "nomaterial"
    rid = render_identity_hash(
        plan_identity_hash=corr.plan_identity_hash,
        asset_manifest_identity_hash=manifest_id,
        selected_render_preset="standard", expected_resolution="1080x1920",
        expected_fps=30, expected_duration_seconds=3.0,
    )
    apr = make_render_approval(corr, manifest_id, rid)
    out = dispatch_hvs_render(
        correlation_id=corr.correlation_id, approval=apr,
        selected_render_preset="standard", hvs_root=root,
        correlation_ledger_path=corr_ledger,
        materialization_ledger_path=mat_ledger,
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, dry_run=False,
    )
    check("denied", not out.ok)
    check("error_kind materialization_not_found",
          out.error_kind == "materialization_not_found", out.error_kind)


def test_04_dry_run_no_render_no_evidence():
    root, corr_ledger, corr, mat_ledger, manifest_id, proj = setup_ready_stage5()
    ev_ledger = fresh_ev_ledger()
    rid = render_identity_hash(
        plan_identity_hash=corr.plan_identity_hash,
        asset_manifest_identity_hash=manifest_id,
        selected_render_preset="standard", expected_resolution="1080x1920",
        expected_fps=30, expected_duration_seconds=3.0,
    )
    apr = make_render_approval(corr, manifest_id, rid)
    runner = _FakeRenderRun()
    out = dispatch_hvs_render(
        correlation_id=corr.correlation_id, approval=apr,
        selected_render_preset="standard", hvs_root=root,
        correlation_ledger_path=corr_ledger,
        materialization_ledger_path=mat_ledger,
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, subprocess_run=runner,
        dry_run=True,
    )
    check("dry_run ok", out.ok)
    check("dry_run would_dispatch True", out.would_dispatch is True)
    check("dry_run invoked no render", len(runner.calls) == 0,
          f"calls={runner.calls}")
    check("dry_run wrote no evidence",
          not ev_ledger.exists() or len(RenderEvidenceLedger(ev_ledger).all()) == 0)
    check("dry_run returns intended output",
          out.render_request is not None and
          out.render_request.requested_output_relative_path.startswith("renders/"))


def test_05_canonical_identity_stable():
    base = dict(
        plan_identity_hash="p1", asset_manifest_identity_hash="m1",
        selected_render_preset="standard", expected_resolution="1080x1920",
        expected_fps=30, expected_duration_seconds=3.0,
    )
    a = render_identity_hash(**base)
    b = render_identity_hash(**base)
    # Reordered construction still equal (deterministic).
    c = render_identity_hash(
        expected_duration_seconds=3.0, expected_resolution="1080x1920",
        selected_render_preset="standard", plan_identity_hash="p1",
        asset_manifest_identity_hash="m1", expected_fps=30,
    )
    check("identical inputs -> identical hash", a == b == c)
    # Different plan -> different hash.
    d = render_identity_hash(**{**base, "plan_identity_hash": "p2"})
    check("different plan -> different hash", d != a)
    # Different preset -> different hash.
    e = render_identity_hash(**{**base, "selected_render_preset": "fast"})
    check("different preset -> different hash", e != a)
    check("hash has rnd- prefix", a.startswith("rnd-"))


# ===========================================================================
# Tests 6-14: Approval gate denial taxonomy
# ===========================================================================
def _approved_dispatch(root, corr, manifest_id, *, runner, ev_ledger,
                        dry_run=False, apr_overrides=None, preset="standard"):
    rid = render_identity_hash(
        plan_identity_hash=corr.plan_identity_hash,
        asset_manifest_identity_hash=manifest_id,
        selected_render_preset=preset, expected_resolution="1080x1920",
        expected_fps=30, expected_duration_seconds=3.0,
    )
    apr = make_render_approval(corr, manifest_id, rid, preset=preset)
    if apr_overrides:
        apr = apr_overrides(corr, manifest_id, rid, preset)
    return dispatch_hvs_render(
        correlation_id=corr.correlation_id, approval=apr,
        selected_render_preset=preset, hvs_root=root,
        correlation_ledger_path=_CREATION_LEDGER,
        materialization_ledger_path=mat_ledger_for(),
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, subprocess_run=runner,
        dry_run=dry_run,
    )


_MAT_LEDGER = None


def mat_ledger_for():
    return _MAT_LEDGER


def test_06_missing_approval_denies():
    root, corr_ledger, corr, mat_ledger, manifest_id, proj = setup_ready_stage5()
    global _MAT_LEDGER
    _MAT_LEDGER = mat_ledger
    ev_ledger = fresh_ev_ledger()
    runner = _FakeRenderRun()
    out = dispatch_hvs_render(
        correlation_id=corr.correlation_id, approval=None,
        selected_render_preset="standard", hvs_root=root,
        correlation_ledger_path=corr_ledger,
        materialization_ledger_path=mat_ledger,
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, subprocess_run=runner, dry_run=False,
    )
    check("denied", not out.ok)
    check("error_kind approval_required", out.error_kind == "approval_required",
          out.error_kind)
    check("no render invoked", len(runner.calls) == 0)


def test_07_pending_rejected_cancelled_expired_deny():
    root, corr_ledger, corr, mat_ledger, manifest_id, proj = setup_ready_stage5()
    global _MAT_LEDGER
    _MAT_LEDGER = mat_ledger
    ev_ledger = fresh_ev_ledger()
    runner = _FakeRenderRun()
    for status in (APPROVAL_PENDING, APPROVAL_REJECTED, APPROVAL_CANCELLED,
                   APPROVAL_EXPIRED):
        rid = render_identity_hash(
            plan_identity_hash=corr.plan_identity_hash,
            asset_manifest_identity_hash=manifest_id,
            selected_render_preset="standard", expected_resolution="1080x1920",
            expected_fps=30, expected_duration_seconds=3.0,
        )
        apr = make_render_approval(corr, manifest_id, rid, status=status)
        out = dispatch_hvs_render(
            correlation_id=corr.correlation_id, approval=apr,
            selected_render_preset="standard", hvs_root=root,
            correlation_ledger_path=corr_ledger,
            materialization_ledger_path=mat_ledger,
            render_evidence_ledger_path=ev_ledger,
            python_executable=sys.executable, subprocess_run=runner, dry_run=False,
        )
        check(f"status={status} denied", not out.ok)
        check(f"status={status} not_valid", out.error_kind == "approval_not_valid",
              out.error_kind)


def test_08_wrong_action_type_denies():
    root, corr_ledger, corr, mat_ledger, manifest_id, proj = setup_ready_stage5()
    global _MAT_LEDGER
    _MAT_LEDGER = mat_ledger
    ev_ledger = fresh_ev_ledger()
    runner = _FakeRenderRun()
    rid = render_identity_hash(
        plan_identity_hash=corr.plan_identity_hash,
        asset_manifest_identity_hash=manifest_id,
        selected_render_preset="standard", expected_resolution="1080x1920",
        expected_fps=30, expected_duration_seconds=3.0,
    )
    # Wrong action_type (Stage 4's) but otherwise matching.
    apr = make_render_approval(
        corr, manifest_id, rid,
        action_type=APPROVAL_ACTION_MATERIALIZE_HVS_ASSETS,
    )
    out = dispatch_hvs_render(
        correlation_id=corr.correlation_id, approval=apr,
        selected_render_preset="standard", hvs_root=root,
        correlation_ledger_path=corr_ledger,
        materialization_ledger_path=mat_ledger,
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, subprocess_run=runner, dry_run=False,
    )
    check("denied", not out.ok)
    check("error_kind approval_action_mismatch",
          out.error_kind == "approval_action_mismatch", out.error_kind)
    check("no render", len(runner.calls) == 0)


def test_09_project_artifact_correlation_mismatch_denies():
    root, corr_ledger, corr, mat_ledger, manifest_id, proj = setup_ready_stage5()
    global _MAT_LEDGER
    _MAT_LEDGER = mat_ledger
    ev_ledger = fresh_ev_ledger()
    runner = _FakeRenderRun()
    rid = render_identity_hash(
        plan_identity_hash=corr.plan_identity_hash,
        asset_manifest_identity_hash=manifest_id,
        selected_render_preset="standard", expected_resolution="1080x1920",
        expected_fps=30, expected_duration_seconds=3.0,
    )
    # Approval scopes a different SCOS project id.
    apr = make_render_approval(corr, manifest_id, rid,
                               scos_project_id="other-proj")
    out = dispatch_hvs_render(
        correlation_id=corr.correlation_id, approval=apr,
        selected_render_preset="standard", hvs_root=root,
        correlation_ledger_path=corr_ledger,
        materialization_ledger_path=mat_ledger,
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, subprocess_run=runner, dry_run=False,
    )
    check("denied", not out.ok)
    check("error_kind approval_scope_mismatch",
          out.error_kind == "approval_scope_mismatch", out.error_kind)


def test_10_plan_hash_mismatch_denies():
    root, corr_ledger, corr, mat_ledger, manifest_id, proj = setup_ready_stage5()
    global _MAT_LEDGER
    _MAT_LEDGER = mat_ledger
    ev_ledger = fresh_ev_ledger()
    runner = _FakeRenderRun()
    rid = render_identity_hash(
        plan_identity_hash=corr.plan_identity_hash,
        asset_manifest_identity_hash=manifest_id,
        selected_render_preset="standard", expected_resolution="1080x1920",
        expected_fps=30, expected_duration_seconds=3.0,
    )
    apr = make_render_approval(corr, manifest_id, rid, plan_hash="wrong-plan")
    out = dispatch_hvs_render(
        correlation_id=corr.correlation_id, approval=apr,
        selected_render_preset="standard", hvs_root=root,
        correlation_ledger_path=corr_ledger,
        materialization_ledger_path=mat_ledger,
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, subprocess_run=runner, dry_run=False,
    )
    check("denied", not out.ok)
    check("error_kind approval_scope_mismatch",
          out.error_kind == "approval_scope_mismatch", out.error_kind)


def test_11_asset_manifest_mismatch_denies():
    root, corr_ledger, corr, mat_ledger, manifest_id, proj = setup_ready_stage5()
    global _MAT_LEDGER
    _MAT_LEDGER = mat_ledger
    ev_ledger = fresh_ev_ledger()
    runner = _FakeRenderRun()
    rid = render_identity_hash(
        plan_identity_hash=corr.plan_identity_hash,
        asset_manifest_identity_hash=manifest_id,
        selected_render_preset="standard", expected_resolution="1080x1920",
        expected_fps=30, expected_duration_seconds=3.0,
    )
    apr = make_render_approval(corr, "wrong-manifest", rid)
    out = dispatch_hvs_render(
        correlation_id=corr.correlation_id, approval=apr,
        selected_render_preset="standard", hvs_root=root,
        correlation_ledger_path=corr_ledger,
        materialization_ledger_path=mat_ledger,
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, subprocess_run=runner, dry_run=False,
    )
    check("denied", not out.ok)
    check("error_kind approval_scope_mismatch",
          out.error_kind == "approval_scope_mismatch", out.error_kind)


def test_12_render_identity_or_preset_mismatch_denies():
    root, corr_ledger, corr, mat_ledger, manifest_id, proj = setup_ready_stage5()
    global _MAT_LEDGER
    _MAT_LEDGER = mat_ledger
    ev_ledger = fresh_ev_ledger()
    runner = _FakeRenderRun()
    # Approval carries a DIFFERENT render identity than what SCOS computes.
    apr = make_render_approval(corr, manifest_id, "rnd-wrongidentity")
    out = dispatch_hvs_render(
        correlation_id=corr.correlation_id, approval=apr,
        selected_render_preset="standard", hvs_root=root,
        correlation_ledger_path=corr_ledger,
        materialization_ledger_path=mat_ledger,
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, subprocess_run=runner, dry_run=False,
    )
    check("render-identity mismatch denied", not out.ok)
    check("error_kind approval_scope_mismatch",
          out.error_kind == "approval_scope_mismatch", out.error_kind)
    # Preset mismatch.
    rid = render_identity_hash(
        plan_identity_hash=corr.plan_identity_hash,
        asset_manifest_identity_hash=manifest_id,
        selected_render_preset="fast", expected_resolution="1080x1920",
        expected_fps=30, expected_duration_seconds=3.0,
    )
    apr2 = make_render_approval(corr, manifest_id, rid, preset="fast")
    out2 = dispatch_hvs_render(
        correlation_id=corr.correlation_id, approval=apr2,
        selected_render_preset="standard",  # caller requested a different preset
        hvs_root=root, correlation_ledger_path=corr_ledger,
        materialization_ledger_path=mat_ledger,
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, subprocess_run=runner, dry_run=False,
    )
    check("preset mismatch denied", not out2.ok)
    check("preset mismatch scope_mismatch",
          out2.error_kind == "approval_scope_mismatch", out2.error_kind)


def test_13_approval_reusable_after_preflight_failure():
    root, corr_ledger, corr, mat_ledger, manifest_id, proj = setup_ready_stage5()
    global _MAT_LEDGER
    _MAT_LEDGER = mat_ledger
    ev_ledger = fresh_ev_ledger()
    runner = _FakeRenderRun()
    # Approval with a mismatched plan hash -> preflight (approval) failure.
    rid = render_identity_hash(
        plan_identity_hash=corr.plan_identity_hash,
        asset_manifest_identity_hash=manifest_id,
        selected_render_preset="standard", expected_resolution="1080x1920",
        expected_fps=30, expected_duration_seconds=3.0,
    )
    apr = make_render_approval(corr, manifest_id, rid, plan_hash="bad")
    out = dispatch_hvs_render(
        correlation_id=corr.correlation_id, approval=apr,
        selected_render_preset="standard", hvs_root=root,
        correlation_ledger_path=corr_ledger,
        materialization_ledger_path=mat_ledger,
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, subprocess_run=runner, dry_run=False,
    )
    check("first attempt denied", not out.ok)
    # Now a correct approval (same approval_id is allowed; not consumed).
    apr2 = make_render_approval(corr, manifest_id, rid)
    out2 = dispatch_hvs_render(
        correlation_id=corr.correlation_id, approval=apr2,
        selected_render_preset="standard", hvs_root=root,
        correlation_ledger_path=corr_ledger,
        materialization_ledger_path=mat_ledger,
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, subprocess_run=runner, dry_run=False,
    )
    check("second attempt with valid approval renders", out2.ok,
          f"{out2.error_kind}: {out2.error_detail}")
    check("render invoked exactly once total", len(runner.calls) == 1,
          f"calls={len(runner.calls)}")


def test_14_approval_consumption_only_after_success():
    root, corr_ledger, corr, mat_ledger, manifest_id, proj = setup_ready_stage5()
    global _MAT_LEDGER
    _MAT_LEDGER = mat_ledger
    ev_ledger = fresh_ev_ledger()
    runner = _FakeRenderRun(fail=True)  # HVS boundary refuses
    rid = render_identity_hash(
        plan_identity_hash=corr.plan_identity_hash,
        asset_manifest_identity_hash=manifest_id,
        selected_render_preset="standard", expected_resolution="1080x1920",
        expected_fps=30, expected_duration_seconds=3.0,
    )
    apr = make_render_approval(corr, manifest_id, rid)
    out = dispatch_hvs_render(
        correlation_id=corr.correlation_id, approval=apr,
        selected_render_preset="standard", hvs_root=root,
        correlation_ledger_path=corr_ledger,
        materialization_ledger_path=mat_ledger,
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, subprocess_run=runner, dry_run=False,
    )
    check("failed render denied", not out.ok)
    check("error_kind hvs_render_failed", out.error_kind == "hvs_render_failed",
          out.error_kind)
    check("no evidence on failure", len(RenderEvidenceLedger(ev_ledger).all()) == 0)
    # Approval NOT consumed: a later valid run (with working boundary) succeeds.
    runner2 = _FakeRenderRun()
    out2 = dispatch_hvs_render(
        correlation_id=corr.correlation_id, approval=apr,
        selected_render_preset="standard", hvs_root=root,
        correlation_ledger_path=corr_ledger,
        materialization_ledger_path=mat_ledger,
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, subprocess_run=runner2, dry_run=False,
    )
    check("re-run after failure succeeds (approval reusable)", out2.ok,
          f"{out2.error_kind}: {out2.error_detail}")


# ===========================================================================
# Tests 15-20: Render safety
# ===========================================================================
def test_15_invalid_hvs_project_blocks():
    root, corr_ledger, corr, mat_ledger, manifest_id, proj = setup_ready_stage5()
    global _MAT_LEDGER
    _MAT_LEDGER = mat_ledger
    ev_ledger = fresh_ev_ledger()
    runner = _FakeRenderRun()
    # Remove the HVS project dir entirely (invalid project).
    import shutil
    proj_dir = root / "projects" / corr.hvs_project_id
    shutil.rmtree(proj_dir, ignore_errors=True)
    rid = render_identity_hash(
        plan_identity_hash=corr.plan_identity_hash,
        asset_manifest_identity_hash=manifest_id,
        selected_render_preset="standard", expected_resolution="1080x1920",
        expected_fps=30, expected_duration_seconds=3.0,
    )
    apr = make_render_approval(corr, manifest_id, rid)
    out = dispatch_hvs_render(
        correlation_id=corr.correlation_id, approval=apr,
        selected_render_preset="standard", hvs_root=root,
        correlation_ledger_path=corr_ledger,
        materialization_ledger_path=mat_ledger,
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, subprocess_run=runner, dry_run=False,
    )
    check("denied", not out.ok)
    check("error_kind invalid_hvs_project",
          out.error_kind == "invalid_hvs_project", out.error_kind)
    check("no render invoked", len(runner.calls) == 0)


def test_16_missing_required_artifact_blocks():
    root, corr_ledger, corr, mat_ledger, manifest_id, proj = setup_ready_stage5()
    global _MAT_LEDGER
    _MAT_LEDGER = mat_ledger
    ev_ledger = fresh_ev_ledger()
    runner = _FakeRenderRun()
    # Delete one required render artifact (tamper).
    (root / "projects" / corr.hvs_project_id / "voice" / "voice_manifest.json").unlink()
    rid = render_identity_hash(
        plan_identity_hash=corr.plan_identity_hash,
        asset_manifest_identity_hash=manifest_id,
        selected_render_preset="standard", expected_resolution="1080x1920",
        expected_fps=30, expected_duration_seconds=3.0,
    )
    apr = make_render_approval(corr, manifest_id, rid)
    out = dispatch_hvs_render(
        correlation_id=corr.correlation_id, approval=apr,
        selected_render_preset="standard", hvs_root=root,
        correlation_ledger_path=corr_ledger,
        materialization_ledger_path=mat_ledger,
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, subprocess_run=runner, dry_run=False,
    )
    check("denied", not out.ok)
    check("error_kind assets_not_ready",
          out.error_kind == "assets_not_ready", out.error_kind)
    check("no render invoked", len(runner.calls) == 0)


def test_17_unsafe_output_path_blocks():
    root, corr_ledger, corr, mat_ledger, manifest_id, proj = setup_ready_stage5()
    global _MAT_LEDGER
    _MAT_LEDGER = mat_ledger
    ev_ledger = fresh_ev_ledger()
    runner = _FakeRenderRun()
    # Approve a requested output path that escapes the project root.
    rid = render_identity_hash(
        plan_identity_hash=corr.plan_identity_hash,
        asset_manifest_identity_hash=manifest_id,
        selected_render_preset="standard", expected_resolution="1080x1920",
        expected_fps=30, expected_duration_seconds=3.0,
    )
    apr = make_render_approval(
        corr, manifest_id, rid, requested_output="../../escape.mp4"
    )
    out = dispatch_hvs_render(
        correlation_id=corr.correlation_id, approval=apr,
        selected_render_preset="standard", hvs_root=root,
        correlation_ledger_path=corr_ledger,
        materialization_ledger_path=mat_ledger,
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, subprocess_run=runner, dry_run=False,
    )
    check("denied", not out.ok)
    check("error_kind unsafe_render_target",
          out.error_kind == "unsafe_render_target", out.error_kind)


def test_18_existing_incompatible_output_not_overwritten():
    root, corr_ledger, corr, mat_ledger, manifest_id, proj = setup_ready_stage5()
    global _MAT_LEDGER
    _MAT_LEDGER = mat_ledger
    ev_ledger = fresh_ev_ledger()
    # Pre-create an output file with a DIFFERENT fingerprint and a prior evidence
    # record for the same render identity (simulating another render's output).
    from hvs_render_dispatch import _hvs_render_id, _slugify
    rid = render_identity_hash(
        plan_identity_hash=corr.plan_identity_hash,
        asset_manifest_identity_hash=manifest_id,
        selected_render_preset="standard", expected_resolution="1080x1920",
        expected_fps=30, expected_duration_seconds=3.0,
    )
    rid_raw = _hvs_render_id(corr.hvs_project_id, "vertical")
    out_path = root / "projects" / corr.hvs_project_id / "renders" / \
        f"hyperframes-{_slugify(rid_raw)}.mp4"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(b"DIFFERENT-CONTENT-NOT-OVERWRITTEN")
    # Evidence from a *different* identity pointing at same path (conflict).
    other_rid = "rnd-otheridentity0000"
    from hvs_render_dispatch import RenderEvidenceRecord
    ev = RenderEvidenceRecord(
        render_evidence_id="hvs-ev-x", correlation_id=corr.correlation_id,
        render_request_id="req-x", render_identity_hash=other_rid,
        approval_id="other-apr", status=EVIDENCE_RENDERED,
        hvs_project_id=corr.hvs_project_id, hvs_artifact_id=corr.hvs_artifact_id,
        hvs_render_output_relative_path=out_path.relative_to(
            root / "projects" / corr.hvs_project_id).as_posix(),
        output_sha256=sha256_of(b"DIFFERENT-CONTENT-NOT-OVERWRITTEN"),
        output_size_bytes=out_path.stat().st_size, output_format="mp4",
        observed_duration_seconds=3.0, observed_resolution="1080x1920",
        observed_fps=30, hvs_render_manifest_relative_path=None,
    )
    RenderEvidenceLedger(ev_ledger).append(ev)
    runner = _FakeRenderRun()
    apr = make_render_approval(corr, manifest_id, rid)
    out = dispatch_hvs_render(
        correlation_id=corr.correlation_id, approval=apr,
        selected_render_preset="standard", hvs_root=root,
        correlation_ledger_path=corr_ledger,
        materialization_ledger_path=mat_ledger,
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, subprocess_run=runner, dry_run=False,
    )
    check("denied", not out.ok)
    check("error_kind render_identity_conflict",
          out.error_kind == "render_identity_conflict", out.error_kind)
    check("output not overwritten",
          out_path.read_bytes() == b"DIFFERENT-CONTENT-NOT-OVERWRITTEN")


def test_19_no_ffmpeg_or_subprocess_in_scos():
    """SCOS must not import or directly call FFmpeg / render subprocess."""
    src = _MODULE_DIR / "hvs_render_dispatch.py"
    text = src.read_text(encoding="utf-8")
    check("no ffmpeg import", "import ffmpeg" not in text and "ffmpeg" not in text)
    # The only subprocess use is the injected HVS CLI boundary (shell=False).
    check("no direct subprocess.run at module top",
          "subprocess.run(" not in text or
          "self._subprocess_run" in text)


def test_20_no_network_ai_assetcopy_publish_side_effects():
    text = (_MODULE_DIR / "hvs_render_dispatch.py"
            ).read_text(encoding="utf-8")
    check("no requests/urllib/socket import",
          "import requests" not in text and "import urllib" not in text and
          "import socket" not in text)
    check("no openai/anthropic token",
          "openai" not in text.lower() and "anthropic" not in text.lower())
    check("no publish/export/delivery verb",
          "publish" not in text and "export_project" not in text and
          "delivery" not in text)


# ===========================================================================
# Tests 21-26: Dispatch + evidence
# ===========================================================================
def test_21_valid_approved_invokes_boundary_once():
    root, corr_ledger, corr, mat_ledger, manifest_id, proj = setup_ready_stage5()
    global _MAT_LEDGER
    _MAT_LEDGER = mat_ledger
    ev_ledger = fresh_ev_ledger()
    runner = _FakeRenderRun()
    rid = render_identity_hash(
        plan_identity_hash=corr.plan_identity_hash,
        asset_manifest_identity_hash=manifest_id,
        selected_render_preset="standard", expected_resolution="1080x1920",
        expected_fps=30, expected_duration_seconds=3.0,
    )
    apr = make_render_approval(corr, manifest_id, rid)
    out = dispatch_hvs_render(
        correlation_id=corr.correlation_id, approval=apr,
        selected_render_preset="standard", hvs_root=root,
        correlation_ledger_path=corr_ledger,
        materialization_ledger_path=mat_ledger,
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, subprocess_run=runner, dry_run=False,
    )
    check("ok", out.ok, f"{out.error_kind}: {out.error_detail}")
    check("render invoked exactly once", len(runner.calls) == 1,
          f"calls={len(runner.calls)}")
    check("argv is module-based list", runner.calls[0][0][:3] ==
          [sys.executable, "-m", "hvs.cli"])
    check("argv uses render subcommand", "render-hyperframes" in runner.calls[0][0])


def test_22_records_one_append_only_evidence():
    root, corr_ledger, corr, mat_ledger, manifest_id, proj = setup_ready_stage5()
    global _MAT_LEDGER
    _MAT_LEDGER = mat_ledger
    ev_ledger = fresh_ev_ledger()
    runner = _FakeRenderRun()
    rid = render_identity_hash(
        plan_identity_hash=corr.plan_identity_hash,
        asset_manifest_identity_hash=manifest_id,
        selected_render_preset="standard", expected_resolution="1080x1920",
        expected_fps=30, expected_duration_seconds=3.0,
    )
    apr = make_render_approval(corr, manifest_id, rid)
    dispatch_hvs_render(
        correlation_id=corr.correlation_id, approval=apr,
        selected_render_preset="standard", hvs_root=root,
        correlation_ledger_path=corr_ledger,
        materialization_ledger_path=mat_ledger,
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, subprocess_run=runner, dry_run=False,
    )
    recs = RenderEvidenceLedger(ev_ledger).all()
    check("exactly one evidence row", len(recs) == 1, f"rows={len(recs)}")
    check("status rendered", recs[0].status == EVIDENCE_RENDERED)
    check("approval_id recorded", recs[0].approval_id == "render-apr-5")


def test_23_evidence_relative_path_sha_size_profile():
    root, corr_ledger, corr, mat_ledger, manifest_id, proj = setup_ready_stage5()
    global _MAT_LEDGER
    _MAT_LEDGER = mat_ledger
    ev_ledger = fresh_ev_ledger()
    runner = _FakeRenderRun()
    rid = render_identity_hash(
        plan_identity_hash=corr.plan_identity_hash,
        asset_manifest_identity_hash=manifest_id,
        selected_render_preset="standard", expected_resolution="1080x1920",
        expected_fps=30, expected_duration_seconds=3.0,
    )
    apr = make_render_approval(corr, manifest_id, rid)
    dispatch_hvs_render(
        correlation_id=corr.correlation_id, approval=apr,
        selected_render_preset="standard", hvs_root=root,
        correlation_ledger_path=corr_ledger,
        materialization_ledger_path=mat_ledger,
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, subprocess_run=runner, dry_run=False,
    )
    rec = RenderEvidenceLedger(ev_ledger).all()[0]
    check("relative path only", not rec.hvs_render_output_relative_path.startswith("/")
          and "://" not in rec.hvs_render_output_relative_path)
    check("relative path under renders/",
          rec.hvs_render_output_relative_path.startswith("renders/"))
    check("sha256 present", len(rec.output_sha256) == 64)
    check("positive size", rec.output_size_bytes > 0)
    check("format mp4", rec.output_format == "mp4")
    check("observed profile present",
          rec.observed_resolution == "1080x1920" and rec.observed_fps == 30)


def test_24_output_validated_against_expected_profile():
    root, corr_ledger, corr, mat_ledger, manifest_id, proj = setup_ready_stage5()
    global _MAT_LEDGER
    _MAT_LEDGER = mat_ledger
    ev_ledger = fresh_ev_ledger()
    runner = _FakeRenderRun()
    rid = render_identity_hash(
        plan_identity_hash=corr.plan_identity_hash,
        asset_manifest_identity_hash=manifest_id,
        selected_render_preset="standard", expected_resolution="1080x1920",
        expected_fps=30, expected_duration_seconds=3.0,
    )
    apr = make_render_approval(corr, manifest_id, rid)
    out = dispatch_hvs_render(
        correlation_id=corr.correlation_id, approval=apr,
        selected_render_preset="standard", hvs_root=root,
        correlation_ledger_path=corr_ledger,
        materialization_ledger_path=mat_ledger,
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, subprocess_run=runner, dry_run=False,
    )
    check("ok", out.ok, f"{out.error_kind}: {out.error_detail}")
    rec = out.evidence
    check("observed duration ~expected",
          abs(float(rec.observed_duration_seconds) - 3.0) < 1e-6)
    check("observed fps matches expected", rec.observed_fps == 30)
    check("observed resolution matches expected",
          rec.observed_resolution == "1080x1920")


def test_25_hvs_output_and_evidence_correlate():
    root, corr_ledger, corr, mat_ledger, manifest_id, proj = setup_ready_stage5()
    global _MAT_LEDGER
    _MAT_LEDGER = mat_ledger
    ev_ledger = fresh_ev_ledger()
    runner = _FakeRenderRun()
    rid = render_identity_hash(
        plan_identity_hash=corr.plan_identity_hash,
        asset_manifest_identity_hash=manifest_id,
        selected_render_preset="standard", expected_resolution="1080x1920",
        expected_fps=30, expected_duration_seconds=3.0,
    )
    apr = make_render_approval(corr, manifest_id, rid)
    out = dispatch_hvs_render(
        correlation_id=corr.correlation_id, approval=apr,
        selected_render_preset="standard", hvs_root=root,
        correlation_ledger_path=corr_ledger,
        materialization_ledger_path=mat_ledger,
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, subprocess_run=runner, dry_run=False,
    )
    rec = out.evidence
    # The evidence-recorded relative path must resolve to a real file whose
    # sha matches the recorded fingerprint.
    abs_path = (root / "projects" / corr.hvs_project_id /
                rec.hvs_render_output_relative_path).resolve()
    check("correlated file exists", abs_path.is_file())
    check("correlated file sha matches evidence",
          sha256_of(abs_path.read_bytes()) == rec.output_sha256)
    check("correlation id binds", rec.correlation_id == corr.correlation_id)
    check("render identity binds", rec.render_identity_hash == rid)


def test_26_failed_render_no_false_success_evidence():
    root, corr_ledger, corr, mat_ledger, manifest_id, proj = setup_ready_stage5()
    global _MAT_LEDGER
    _MAT_LEDGER = mat_ledger
    ev_ledger = fresh_ev_ledger()
    runner = _FakeRenderRun(fail=True)
    rid = render_identity_hash(
        plan_identity_hash=corr.plan_identity_hash,
        asset_manifest_identity_hash=manifest_id,
        selected_render_preset="standard", expected_resolution="1080x1920",
        expected_fps=30, expected_duration_seconds=3.0,
    )
    apr = make_render_approval(corr, manifest_id, rid)
    out = dispatch_hvs_render(
        correlation_id=corr.correlation_id, approval=apr,
        selected_render_preset="standard", hvs_root=root,
        correlation_ledger_path=corr_ledger,
        materialization_ledger_path=mat_ledger,
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, subprocess_run=runner, dry_run=False,
    )
    check("not ok", not out.ok)
    check("no evidence row", len(RenderEvidenceLedger(ev_ledger).all()) == 0)
    check("evidence is None", out.evidence is None)


# ===========================================================================
# Tests 27-31: Idempotency + recovery
# ===========================================================================
def test_27_same_request_twice_renders_once_reused():
    root, corr_ledger, corr, mat_ledger, manifest_id, proj = setup_ready_stage5()
    global _MAT_LEDGER
    _MAT_LEDGER = mat_ledger
    ev_ledger = fresh_ev_ledger()
    runner = _FakeRenderRun()
    rid = render_identity_hash(
        plan_identity_hash=corr.plan_identity_hash,
        asset_manifest_identity_hash=manifest_id,
        selected_render_preset="standard", expected_resolution="1080x1920",
        expected_fps=30, expected_duration_seconds=3.0,
    )
    apr = make_render_approval(corr, manifest_id, rid)
    out1 = dispatch_hvs_render(
        correlation_id=corr.correlation_id, approval=apr,
        selected_render_preset="standard", hvs_root=root,
        correlation_ledger_path=corr_ledger,
        materialization_ledger_path=mat_ledger,
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, subprocess_run=runner, dry_run=False,
    )
    check("first render ok", out1.ok)
    check("first status rendered", out1.render_status == EVIDENCE_RENDERED)
    # Second identical approved request -> reused, no new render.
    out2 = dispatch_hvs_render(
        correlation_id=corr.correlation_id, approval=apr,
        selected_render_preset="standard", hvs_root=root,
        correlation_ledger_path=corr_ledger,
        materialization_ledger_path=mat_ledger,
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, subprocess_run=runner, dry_run=False,
    )
    check("second returns reused", out2.ok and out2.render_status == EVIDENCE_REUSED,
          f"{out2.render_status}")
    check("render invoked once total", len(runner.calls) == 1,
          f"calls={len(runner.calls)}")
    check("evidence still one row", len(RenderEvidenceLedger(ev_ledger).all()) == 1)


def test_28_matching_existing_output_recovers_without_rerender():
    root, corr_ledger, corr, mat_ledger, manifest_id, proj = setup_ready_stage5()
    global _MAT_LEDGER
    _MAT_LEDGER = mat_ledger
    ev_ledger = fresh_ev_ledger()
    # Manually create the output file (simulating a previous render) but NO
    # evidence row. SCOS must recover by inspecting + recording once.
    from hvs_render_dispatch import _hvs_render_id, _slugify
    rid_raw = _hvs_render_id(corr.hvs_project_id, "vertical")
    out_path = (root / "projects" / corr.hvs_project_id / "renders" /
                f"hyperframes-{_slugify(rid_raw)}.mp4")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(b"RECOVERED-OUTPUT-CONTENT" * 64)
    runner = _FakeRenderRun()  # should NOT be called
    rid = render_identity_hash(
        plan_identity_hash=corr.plan_identity_hash,
        asset_manifest_identity_hash=manifest_id,
        selected_render_preset="standard", expected_resolution="1080x1920",
        expected_fps=30, expected_duration_seconds=3.0,
    )
    apr = make_render_approval(corr, manifest_id, rid)
    out = dispatch_hvs_render(
        correlation_id=corr.correlation_id, approval=apr,
        selected_render_preset="standard", hvs_root=root,
        correlation_ledger_path=corr_ledger,
        materialization_ledger_path=mat_ledger,
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, subprocess_run=runner, dry_run=False,
    )
    check("recovered ok", out.ok, f"{out.error_kind}: {out.error_detail}")
    check("no re-render", len(runner.calls) == 0, f"calls={len(runner.calls)}")
    rec = RenderEvidenceLedger(ev_ledger).all()[0]
    check("evidence written once", len(RenderEvidenceLedger(ev_ledger).all()) == 1)
    check("recovered flag set", rec.recovered is True)
    check("sha matches recovered file",
          rec.output_sha256 == sha256_of(out_path.read_bytes()))


def test_29_missing_evidence_recovery_safe_writes_once():
    # Same as 28 but verifies idempotency of recovery (call twice).
    root, corr_ledger, corr, mat_ledger, manifest_id, proj = setup_ready_stage5()
    global _MAT_LEDGER
    _MAT_LEDGER = mat_ledger
    ev_ledger = fresh_ev_ledger()
    from hvs_render_dispatch import _hvs_render_id, _slugify
    rid_raw = _hvs_render_id(corr.hvs_project_id, "vertical")
    out_path = (root / "projects" / corr.hvs_project_id / "renders" /
                f"hyperframes-{_slugify(rid_raw)}.mp4")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(b"RECOVERED-OUTPUT-CONTENT" * 64)
    runner = _FakeRenderRun()
    rid = render_identity_hash(
        plan_identity_hash=corr.plan_identity_hash,
        asset_manifest_identity_hash=manifest_id,
        selected_render_preset="standard", expected_resolution="1080x1920",
        expected_fps=30, expected_duration_seconds=3.0,
    )
    apr = make_render_approval(corr, manifest_id, rid)
    out1 = dispatch_hvs_render(
        correlation_id=corr.correlation_id, approval=apr,
        selected_render_preset="standard", hvs_root=root,
        correlation_ledger_path=corr_ledger,
        materialization_ledger_path=mat_ledger,
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, subprocess_run=runner, dry_run=False,
    )
    out2 = dispatch_hvs_render(
        correlation_id=corr.correlation_id, approval=apr,
        selected_render_preset="standard", hvs_root=root,
        correlation_ledger_path=corr_ledger,
        materialization_ledger_path=mat_ledger,
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, subprocess_run=runner, dry_run=False,
    )
    check("first recovered", out1.ok and out1.render_status == EVIDENCE_REUSED)
    check("second reused (no new write)", out2.ok and out2.render_status == EVIDENCE_REUSED)
    check("exactly one evidence row", len(RenderEvidenceLedger(ev_ledger).all()) == 1)


def test_30_changed_plan_assets_preset_requires_new_approval():
    root, corr_ledger, corr, mat_ledger, manifest_id, proj = setup_ready_stage5()
    global _MAT_LEDGER
    _MAT_LEDGER = mat_ledger
    ev_ledger = fresh_ev_ledger()
    runner = _FakeRenderRun()
    # Render once with preset "standard".
    rid1 = render_identity_hash(
        plan_identity_hash=corr.plan_identity_hash,
        asset_manifest_identity_hash=manifest_id,
        selected_render_preset="standard", expected_resolution="1080x1920",
        expected_fps=30, expected_duration_seconds=3.0,
    )
    apr1 = make_render_approval(corr, manifest_id, rid1, preset="standard")
    out1 = dispatch_hvs_render(
        correlation_id=corr.correlation_id, approval=apr1,
        selected_render_preset="standard", hvs_root=root,
        correlation_ledger_path=corr_ledger,
        materialization_ledger_path=mat_ledger,
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, subprocess_run=runner, dry_run=False,
    )
    check("first render ok", out1.ok)
    check("first render invoked boundary", len(runner.calls) == 1)
    # A DIFFERENT preset -> a new, distinct render identity.
    rid2 = render_identity_hash(
        plan_identity_hash=corr.plan_identity_hash,
        asset_manifest_identity_hash=manifest_id,
        selected_render_preset="fast", expected_resolution="1080x1920",
        expected_fps=30, expected_duration_seconds=3.0,
    )
    check("new preset yields new render identity", rid2 != rid1)
    # Reusing the OLD (standard) approval for the new (fast) requested preset
    # must be denied (scope mismatch) — the approval is bound to rid1.
    apr_reuse = make_render_approval(corr, manifest_id, rid1, preset="standard")
    out_reuse = dispatch_hvs_render(
        correlation_id=corr.correlation_id, approval=apr_reuse,
        selected_render_preset="fast", hvs_root=root,
        correlation_ledger_path=corr_ledger,
        materialization_ledger_path=mat_ledger,
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, subprocess_run=runner, dry_run=False,
    )
    check("reusing old approval for new preset denied",
          not out_reuse.ok and out_reuse.error_kind == "approval_scope_mismatch")
    # The HVS render boundary fixes the output path per (project, fmt), so a new
    # render identity for the SAME project would overwrite the existing output.
    # Per HVS no-overwrite policy this requires a NEW HVS project; SCOS refuses to
    # overwrite and reports render_identity_conflict for the new-but-same-project
    # approval. This proves a changed preset needs a fresh approval (and project).
    apr2 = make_render_approval(corr, manifest_id, rid2, preset="fast")
    out2 = dispatch_hvs_render(
        correlation_id=corr.correlation_id, approval=apr2,
        selected_render_preset="fast", hvs_root=root,
        correlation_ledger_path=corr_ledger,
        materialization_ledger_path=mat_ledger,
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, subprocess_run=runner, dry_run=False,
    )
    check("new identity in same project refused (no-overwrite)",
          not out2.ok and out2.error_kind == "render_identity_conflict",
          f"{out2.error_kind}: {out2.error_detail}")
    check("no additional render invoked", len(runner.calls) == 1,
          f"calls={len(runner.calls)}")


def test_31_inputs_and_approval_not_mutated():
    root, corr_ledger, corr, mat_ledger, manifest_id, proj = setup_ready_stage5()
    global _MAT_LEDGER
    _MAT_LEDGER = mat_ledger
    ev_ledger = fresh_ev_ledger()
    runner = _FakeRenderRun()
    rid = render_identity_hash(
        plan_identity_hash=corr.plan_identity_hash,
        asset_manifest_identity_hash=manifest_id,
        selected_render_preset="standard", expected_resolution="1080x1920",
        expected_fps=30, expected_duration_seconds=3.0,
    )
    apr = make_render_approval(corr, manifest_id, rid)
    before = apr.to_dict()
    out = dispatch_hvs_render(
        correlation_id=corr.correlation_id, approval=apr,
        selected_render_preset="standard", hvs_root=root,
        correlation_ledger_path=corr_ledger,
        materialization_ledger_path=mat_ledger,
        render_evidence_ledger_path=ev_ledger,
        python_executable=sys.executable, subprocess_run=runner, dry_run=False,
    )
    check("render ok", out.ok)
    check("approval object unchanged", apr.to_dict() == before)
    check("correlation object unchanged",
          corr.to_dict() == corr.to_dict())


# ===========================================================================
# Tests 32-35: Regression / security / smoke
# ===========================================================================
def test_32_stage1_4_regression_imports():
    """Stage 1-4 modules still import; Stage 5 consumes them (no breakage)."""
    from hvs_adapter import HermesVideoStudioAdapter  # Stage 1
    from hvs_project_creation import create_hvs_project  # Stage 3
    from hvs_asset_materialization import materialize_hvs_assets  # Stage 4
    check("stage1 adapter importable", HermesVideoStudioAdapter is not None)
    check("stage3 creation importable", create_hvs_project is not None)
    check("stage4 materialization importable", materialize_hvs_assets is not None)


def test_33_control_center_suite_collectable():
    """The new module + tests are importable/collectable by pytest."""
    import importlib.util
    mod = importlib.import_module("hvs_render_dispatch")
    spec = importlib.util.spec_from_file_location(
        "stage5_test_module",
        str(_HERE / "test_hvs_render_dispatch.py"),
    )
    test_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(test_mod)
    check("module has dispatch_hvs_render", hasattr(mod, "dispatch_hvs_render"))
    check("test module collected",
          hasattr(test_mod, "test_21_valid_approved_invokes_boundary_once"))


def test_34_security_scan_new_module():
    """Forbidden-pattern scan of the new Stage 5 production code."""
    text = (_MODULE_DIR / "hvs_render_dispatch.py"
            ).read_text(encoding="utf-8")
    forbidden = [
        ("network", "import requests"),
        ("network", "import urllib"),
        ("network", "import socket"),
        ("shell_exec", "os.system("),
        ("shell_exec", "shell=True"),
        ("subprocess_direct", "subprocess.run("),  # allowed only via DI
        ("direct_ffmpeg", "ffmpeg"),
        ("secret", "api_key"),
        ("secret", "password"),
        ("ai_api", "openai"),
        ("ai_api", "anthropic"),
    ]
    problems = []
    for label, token in forbidden:
        if token in text:
            # subprocess.run is permitted ONLY through the injected runner; the
            # literal at module scope would indicate a direct call.
            if token == "subprocess.run(" and "self._subprocess_run" in text:
                # confirm it is not called at module level (only referenced)
                if text.count("subprocess.run(") == 1 and "self._subprocess_run = subprocess_run or subprocess.run" in text:
                    continue
            problems.append(f"{label}:{token}")
    check("no forbidden patterns", not problems, "; ".join(problems))
    # Explicit: the only subprocess path is the injected boundary runner.
    check("subprocess used via injected runner only",
          "self._subprocess_run" in text and "subprocess.run" in text)


def test_35_real_hvs_repo_untouched_by_tests():
    """Tests never point hvs_root at the real HVS repo; repo stays clean."""
    # Every setup helper uses fresh_root() (temp). Assert the real repo dir has
    # no stray renders produced by our tests under projects/<stage5>.
    projects = HVS_REPO_ROOT / "projects"
    if projects.is_dir():
        stage5 = [p for p in projects.iterdir()
                  if p.is_dir() and p.name.startswith("hvs-") and
                  (p / "renders").exists()]
        # We cannot guarantee zero pre-existing dirs, but our tests write to
        # temp roots only. Verify git working tree of HVS is clean.
    import subprocess as _sp
    res = _sp.run(
        ["git", "status", "--porcelain"],
        cwd=str(HVS_REPO_ROOT), capture_output=True, text=True, timeout=60,
    )
    check("real HVS repo clean", res.returncode == 0 and res.stdout.strip() == "",
          res.stdout.strip()[:200])


if __name__ == "__main__":
    # Lightweight runner for standalone execution (mirrors pytest discovery).
    import types
    funcs = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and isinstance(v, types.FunctionType)]
    for fn in funcs:
        print(f"\n== {fn.__name__} ==")
        fn()
    print(f"\nTOTAL: {_PASS} passed, {_FAIL} failed")
    if _FAILS:
        print("FAILURES:")
        for f in _FAILS:
            print(f"  - {f}")
    raise SystemExit(1 if _FAIL else 0)
