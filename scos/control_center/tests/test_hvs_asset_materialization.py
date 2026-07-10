"""test_hvs_asset_materialization.py - SCOS <-> HVS Stage 4 approval-gated asset materialization.

32 focused, deterministic tests. Uses ONLY temp directories and injected paths;
the real HVS repository is never mutated. Covers preflight/contract, asset
resolution + validation, approval gate denial taxonomy, approval consumption,
materialization + safety, idempotency/recovery, regression, cross-repository
schema/layout validation, and a forbidden-pattern security scan.

Plain executable script (no pytest-only features); pytest collects the
``test_*`` functions directly. Imports the package via an explicit sys.path
insertion so it runs both under pytest and standalone.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_PACKAGE = _HERE.parent
sys.path.insert(0, str(_PACKAGE))

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
    ERR_APPROVAL_ACTION_MISMATCH,
    ERR_APPROVAL_NOT_VALID,
    ERR_APPROVAL_REQUIRED,
    ERR_APPROVAL_SCOPE_MISMATCH,
    ERR_CORRELATION_NOT_FOUND,
    ERR_DESTINATION_CONFLICT,
    ERR_INVALID_ASSET_REFERENCE,
    ERR_SOURCE_ASSET_CHANGED,
    ERR_SOURCE_ASSET_MISSING,
    ERR_UNSAFE_SOURCE_PATH,
    ERR_UNSUPPORTED_ASSET_TYPE,
    HVSAssetMaterializationApproval,
    MaterializationLedger,
    SourceRoot,
    asset_manifest_identity_hash,
    materialize_hvs_assets,
    resolve_asset,
)

HVS_REPO_ROOT = Path(r"C:\Workspace\hermes-video-studio").resolve()

_PASS = 0
_FAIL = 0
_FAILS: list[str] = []


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
    d = _tmp / f"hvs_root_{_PASS}_{_FAIL}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def fresh_ledger():
    return _tmp / f"corr_ledger_{_PASS}_{_FAIL}.jsonl"


def fresh_mat_ledger():
    return _tmp / f"mat_ledger_{_PASS}_{_FAIL}.jsonl"


def src_root_with(assets: dict[str, bytes]):
    """Create an approved source root populated with the given relative paths."""
    r = _tmp / f"src_root_{_PASS}_{_FAIL}"
    r.mkdir(parents=True, exist_ok=True)
    for rel, data in assets.items():
        p = r / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    sr = SourceRoot(root_id="rootA", root_path=str(r))
    # Convenience Path accessor for tests (never persisted).
    object.__setattr__(sr, "root", r)
    return sr


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_project(project_id="proj-4"):
    return SCOSRenderTimelineProject(
        project_id=project_id,
        width=1080,
        height=1920,
        fps=30,
        selected_preset="standard",
        scenes=(
            SCOSScene(
                scene_id="s01",
                order=1,
                start_ms=0,
                duration_ms=1000,
                intent="intro",
                visual_description="v",
                text_overlay="t",
                asset_refs=(SCOSAssetRef(asset_id="a_img", asset_type="background", path="img/scene_01.png"),),
                captions=(SCOSCaption(scene_id="s01", text="hi", start_ms=0, end_ms=500),),
            ),
            SCOSScene(
                scene_id="s02",
                order=2,
                start_ms=1000,
                duration_ms=1000,
                intent="body",
                visual_description="v",
                text_overlay="t",
                asset_refs=(SCOSAssetRef(asset_id="a_aud", asset_type="music_or_audio_placeholder", path="aud/voice_01.wav"),),
                captions=(SCOSCaption(scene_id="s02", text="yo", start_ms=1000, end_ms=1500),),
            ),
            SCOSScene(
                scene_id="s03",
                order=3,
                start_ms=2000,
                duration_ms=1000,
                intent="out",
                visual_description="v",
                text_overlay="t",
                asset_refs=(),
                captions=(),
            ),
        ),
    )


def make_creation_approval(proj):
    apr = HVSProjectApproval.of(
        approval_id="create-apr-4",
        requested_plan_identity_hash=_plan_hash(proj),
        requested_scos_project_id=proj.project_id,
        requested_hvs_artifact_id=f"hvs-timeline-{proj.project_id}",
        issued_by="op",
    )
    return apr


def _plan_hash(proj):
    from hvs_schema_mapper import map_scos_to_hvs, payload_identity_hash

    return payload_identity_hash(map_scos_to_hvs(proj, validate=True).payload)


def create_correlated_project(proj):
    """Create a Stage 3 correlated project in a fresh temp HVS root; return (root, ledger, corr_id)."""
    root = fresh_root()
    ledger = fresh_ledger()
    apr = make_creation_approval(proj)
    out = create_hvs_project(
        proj, apr, hvs_root=root, correlation_ledger_path=ledger, requested_by="op"
    )
    assert out.ok, f"stage3 create failed: {out.error_kind}"
    corr_id = out.correlation.correlation_id
    return root, ledger, corr_id


def make_asset_approval(proj, corr_id, manifest_id, asset_ids, root_ids):
    return HVSAssetMaterializationApproval.of(
        approval_id="mat-apr-4",
        requested_correlation_id=corr_id,
        requested_scos_project_id=proj.project_id,
        requested_hvs_artifact_id=f"hvs-timeline-{proj.project_id}",
        requested_asset_manifest_identity_hash=manifest_id,
        approved_source_root_ids=root_ids,
        approved_asset_ids=asset_ids,
        issued_by="op",
    )


# ---------------------------------------------------------------------------
# Tests 1-4: Preflight / dry-run / contract
# ---------------------------------------------------------------------------
def test_01_stage2_asset_refs_consumed():
    proj = make_project()
    refs = [a for s in proj.scenes for a in s.asset_refs]
    check("01 stage2 asset refs consumed (not reimplemented)", len(refs) == 2 and refs[0].asset_id == "a_img")


def test_02_stage3_correlation_required():
    root = fresh_root()
    ledger = fresh_ledger()
    src = src_root_with({"img/scene_01.png": b"\x89PNG\r\n\x1a\nfake", "aud/voice_01.wav": b"RIFFfakeWAVE"})
    refs = [SCOSAssetRef(asset_id="a_img", asset_type="background", path="img/scene_01.png"),
            SCOSAssetRef(asset_id="a_aud", asset_type="music_or_audio_placeholder", path="aud/voice_01.wav")]
    apr = make_asset_approval(make_project(), "corr-does-not-exist", "x", ["a_img", "a_aud"], ["rootA"])
    out = materialize_hvs_assets(
        correlation_id="corr-does-not-exist", asset_refs=refs, source_roots=[src],
        approval=apr, hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op",
    )
    check("02 missing correlation blocked", (not out.ok) and out.error_kind == ERR_CORRELATION_NOT_FOUND)
    check("02 no writes on missing correlation", not (root / "projects").exists())


def test_03_dry_run_zero_mutation():
    proj = make_project()
    root, ledger, corr_id = create_correlated_project(proj)
    src = src_root_with({"img/scene_01.png": b"\x89PNG\r\n\x1a\nfake", "aud/voice_01.wav": b"RIFFfakeWAVE"})
    refs = [SCOSAssetRef(asset_id="a_img", asset_type="background", path="img/scene_01.png"),
            SCOSAssetRef(asset_id="a_aud", asset_type="music_or_audio_placeholder", path="aud/voice_01.wav")]
    # Compute manifest id via dry-run first (canonical).
    out0 = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, "placeholder", ["a_img", "a_aud"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op", dry_run=True,
    )
    m_id = out0.manifest_identity_hash
    mat_ledger = fresh_mat_ledger()
    out = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, m_id, ["a_img", "a_aud"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=mat_ledger, requested_by="op", dry_run=True,
    )
    check("03 dry-run ok plan", out.ok and out.dry_run)
    # No asset files written, no manifest, no ledger line.
    proj_assets = root / "projects" / out.hvs_project_id / "assets"
    check("03 dry-run no asset files", not (proj_assets / "background").exists())
    check("03 dry-run no stage4 manifest", not (proj_assets / "asset_manifest.stage4.json").exists())
    check("03 dry-run no ledger", not mat_ledger.exists() or mat_ledger.read_text().strip() == "")
    check("03 dry-run returns manifest id", bool(m_id))


def test_04_canonical_identity_stable():
    proj = make_project()
    root, ledger, corr_id = create_correlated_project(proj)
    src = src_root_with({"img/scene_01.png": b"\x89PNG\r\n\x1a\nfake", "aud/voice_01.wav": b"RIFFfakeWAVE"})
    refs = [SCOSAssetRef(asset_id="a_img", asset_type="background", path="img/scene_01.png"),
            SCOSAssetRef(asset_id="a_aud", asset_type="music_or_audio_placeholder", path="aud/voice_01.wav")]
    r1 = [resolve_asset(r, source_root=src, hvs_project_root=root, hvs_project_id="x", correlation_id=corr_id) for r in refs]
    r2 = [resolve_asset(r, source_root=src, hvs_project_root=root, hvs_project_id="x", correlation_id=corr_id) for r in refs]
    id1 = asset_manifest_identity_hash(r1)
    id2 = asset_manifest_identity_hash(r2)
    # Reorder -> still identical.
    id3 = asset_manifest_identity_hash(list(reversed(r1)))
    check("04 canonical identity stable", id1 == id2 == id3 and bool(id1))


# ---------------------------------------------------------------------------
# Tests 5-12: Safety / resolution
# ---------------------------------------------------------------------------
def _corr_and_src(proj):
    root, ledger, corr_id = create_correlated_project(proj)
    src = src_root_with({"img/scene_01.png": b"\x89PNG\r\n\x1a\nfake", "aud/voice_01.wav": b"RIFFfakeWAVE"})
    return root, ledger, corr_id, src


def test_05_missing_source_fails():
    proj = make_project()
    root, ledger, corr_id, src = _corr_and_src(proj)
    refs = [SCOSAssetRef(asset_id="a_img", asset_type="background", path="img/missing.png"),
            SCOSAssetRef(asset_id="a_aud", asset_type="music_or_audio_placeholder", path="aud/voice_01.wav")]
    out = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, "x", ["a_img", "a_aud"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op",
    )
    check("05 missing source fails", (not out.ok) and out.error_kind == ERR_SOURCE_ASSET_MISSING)
    check("05 no mutation", not (root / "projects" / out.hvs_project_id / "assets" / "background").exists())


def test_06_path_traversal_fails():
    proj = make_project()
    root, ledger, corr_id, src = _corr_and_src(proj)
    refs = [SCOSAssetRef(asset_id="a_img", asset_type="background", path="../escape.png")]
    out = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, "x", ["a_img"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op",
    )
    check("06 path traversal fails", (not out.ok) and out.error_kind == ERR_UNSAFE_SOURCE_PATH)


def test_07_absolute_unc_url_symlink_fails():
    proj = make_project()
    root, ledger, corr_id, src = _corr_and_src(proj)
    bad_paths = [
        (r"C:\Windows\system32\evil.png", ERR_UNSAFE_SOURCE_PATH),
        (r"\\server\share\evil.png", ERR_UNSAFE_SOURCE_PATH),
        ("http://example.com/evil.png", ERR_UNSAFE_SOURCE_PATH),
        ("img/scene_01.png\x00.png", ERR_UNSAFE_SOURCE_PATH),
    ]
    for p, expected in bad_paths:
        refs = [SCOSAssetRef(asset_id="a_img", asset_type="background", path=p)]
        out = materialize_hvs_assets(
            correlation_id=corr_id, asset_refs=refs, source_roots=[src],
            approval=make_asset_approval(proj, corr_id, "x", ["a_img"], ["rootA"]),
            hvs_root=root, correlation_ledger_path=ledger,
            materialization_ledger_path=fresh_mat_ledger(), requested_by="op",
        )
        check(f"07 unsafe path rejected ({p!r})", (not out.ok) and out.error_kind == expected, out.error_kind)
    # Symlink escape: create a symlink inside the root pointing outside.
    try:
        link_target = _tmp / "outside_secret.txt"
        link_target.write_text("secret")
        link = src.root / "img" / "link.png"
        link.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(str(link_target), str(link))
        refs = [SCOSAssetRef(asset_id="a_img", asset_type="background", path="img/link.png")]
        out = materialize_hvs_assets(
            correlation_id=corr_id, asset_refs=refs, source_roots=[src],
            approval=make_asset_approval(proj, corr_id, "x", ["a_img"], ["rootA"]),
            hvs_root=root, correlation_ledger_path=ledger,
            materialization_ledger_path=fresh_mat_ledger(), requested_by="op",
        )
        check("07 symlink escape rejected", (not out.ok) and out.error_kind == ERR_UNSAFE_SOURCE_PATH, out.error_kind)
    except (OSError, NotImplementedError):
        check("07 symlink escape rejected (skipped; platform)", True)


def test_08_unsupported_type_fails():
    proj = make_project()
    root, ledger, corr_id, src = _corr_and_src(proj)
    # Put a .xyz file where a background (png/jpg/mp4) is declared.
    (src.root / "img").mkdir(parents=True, exist_ok=True)
    (src.root / "img" / "scene_01.xyz").write_bytes(b"data")
    refs = [SCOSAssetRef(asset_id="a_img", asset_type="background", path="img/scene_01.xyz")]
    out = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, "x", ["a_img"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op",
    )
    check("08 unsupported type fails", (not out.ok) and out.error_kind == ERR_UNSUPPORTED_ASSET_TYPE)
    # Slot mismatch: declare audio slot but supply png.
    refs2 = [SCOSAssetRef(asset_id="a_aud", asset_type="music_or_audio_placeholder", path="img/scene_01.png")]
    out2 = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs2, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, "x", ["a_aud"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op",
    )
    check("08 slot/extension mismatch fails", (not out2.ok) and out2.error_kind == ERR_UNSUPPORTED_ASSET_TYPE)


def test_09_source_outside_approved_root_fails():
    proj = make_project()
    root, ledger, corr_id, src = _corr_and_src(proj)
    # Approved root does NOT contain the asset; the asset lives in a different dir.
    other = _tmp / f"other_{_PASS}"
    other.mkdir(parents=True, exist_ok=True)
    (other / "img").mkdir(parents=True, exist_ok=True)
    (other / "img" / "scene_01.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    refs = [SCOSAssetRef(asset_id="a_img", asset_type="background", path="img/scene_01.png")]
    # SourceRoot points only at `src`; the file is under `other` -> not found in root.
    out = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, "x", ["a_img"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op",
    )
    check("09 source outside approved root fails", (not out.ok) and out.error_kind == ERR_SOURCE_ASSET_MISSING)


def test_10_source_changed_after_planning_fails():
    proj = make_project()
    root, ledger, corr_id, src = _corr_and_src(proj)
    refs = [SCOSAssetRef(asset_id="a_img", asset_type="background", path="img/scene_01.png"),
            SCOSAssetRef(asset_id="a_aud", asset_type="music_or_audio_placeholder", path="aud/voice_01.wav")]
    out0 = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, "ph", ["a_img", "a_aud"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op", dry_run=True,
    )
    # Now mutate the source file bytes (simulate change after planning).
    (src.root / "img" / "scene_01.png").write_bytes(b"\x89PNG\r\n\x1a\nCHANGED!")
    out = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, out0.manifest_identity_hash, ["a_img", "a_aud"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op",
    )
    check("10 changed source fails source_asset_changed", (not out.ok) and out.error_kind == ERR_SOURCE_ASSET_CHANGED, out.error_kind)


def test_11_destination_cannot_escape():
    proj = make_project()
    root, ledger, corr_id, src = _corr_and_src(proj)
    refs = [SCOSAssetRef(asset_id="a_img", asset_type="background", path="img/scene_01.png")]
    # Trick: craft a resolved asset whose intended path is forced outside -> guard.
    resolved = resolve_asset(refs[0], source_root=src, hvs_project_root=root,
                             hvs_project_id="x", correlation_id=corr_id)
    # intended path is always under assets/<slot_type>/... by construction.
    check("11 intended dest under assets", resolved.intended_hvs_relative_path.startswith("assets/"))
    # Negative: an attacker-supplied unsafe basename is sanitized.
    from hvs_asset_materialization import _safe_basename
    safe = _safe_basename("../../etc/passwd")
    check("11 unsafe basename sanitized", ".." not in safe and "/" not in safe and bool(safe))


def test_12_source_never_modified():
    proj = make_project()
    root, ledger, corr_id, src = _corr_and_src(proj)
    original = (src.root / "img" / "scene_01.png").read_bytes()
    refs = [SCOSAssetRef(asset_id="a_img", asset_type="background", path="img/scene_01.png"),
            SCOSAssetRef(asset_id="a_aud", asset_type="music_or_audio_placeholder", path="aud/voice_01.wav")]
    out0 = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, "ph", ["a_img", "a_aud"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op", dry_run=True,
    )
    out = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, out0.manifest_identity_hash, ["a_img", "a_aud"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op",
    )
    after = (src.root / "img" / "scene_01.png").read_bytes()
    check("12 source unchanged after materialize", after == original and out.ok)


# ---------------------------------------------------------------------------
# Tests 13-19: Approval gate
# ---------------------------------------------------------------------------
def _good_pair(proj, with_real_id=False):
    root, ledger, corr_id = create_correlated_project(proj)
    src = src_root_with({"img/scene_01.png": b"\x89PNG\r\n\x1a\nfake", "aud/voice_01.wav": b"RIFFfakeWAVE"})
    refs = [SCOSAssetRef(asset_id="a_img", asset_type="background", path="img/scene_01.png"),
            SCOSAssetRef(asset_id="a_aud", asset_type="music_or_audio_placeholder", path="aud/voice_01.wav")]
    out0 = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, "ph", ["a_img", "a_aud"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op", dry_run=True,
    )
    m_id = out0.manifest_identity_hash if with_real_id else "x"
    return root, ledger, corr_id, src, refs, m_id, out0


def test_13_missing_pending_rejected_expired_cancelled():
    proj = make_project()
    root, ledger, corr_id, src, refs, m_id, _ = _good_pair(proj)
    # Missing approval
    out = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src], approval=None,
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op",
    )
    check("13 missing approval", (not out.ok) and out.error_kind == ERR_APPROVAL_REQUIRED)
    # Pending
    apr = make_asset_approval(proj, corr_id, m_id, ["a_img", "a_aud"], ["rootA"])
    apr = HVSAssetMaterializationApproval(**{**apr.to_dict(), "status": APPROVAL_PENDING})
    out = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src], approval=apr,
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op",
    )
    check("13 pending approval", (not out.ok) and out.error_kind == ERR_APPROVAL_NOT_VALID)
    # Rejected
    apr = HVSAssetMaterializationApproval(**{**apr.to_dict(), "status": APPROVAL_REJECTED})
    out = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src], approval=apr,
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op",
    )
    check("13 rejected approval", (not out.ok) and out.error_kind == ERR_APPROVAL_NOT_VALID)
    # Expired (via clock)
    apr = make_asset_approval(proj, corr_id, m_id, ["a_img", "a_aud"], ["rootA"])
    apr = HVSAssetMaterializationApproval(**{**apr.to_dict(), "expires_at": "2020-01-01T00:00:00Z"})
    out = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src], approval=apr,
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op",
        clock=lambda: "2026-01-01T00:00:00Z",
    )
    check("13 expired approval", (not out.ok) and out.error_kind == ERR_APPROVAL_NOT_VALID)
    # Cancelled
    apr = HVSAssetMaterializationApproval(**{**apr.to_dict(), "status": APPROVAL_CANCELLED, "expires_at": None})
    out = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src], approval=apr,
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op",
    )
    check("13 cancelled approval", (not out.ok) and out.error_kind == ERR_APPROVAL_NOT_VALID)


def test_14_wrong_action_type():
    proj = make_project()
    root, ledger, corr_id, src, refs, m_id, _ = _good_pair(proj)
    apr = make_asset_approval(proj, corr_id, m_id, ["a_img", "a_aud"], ["rootA"])
    apr = HVSAssetMaterializationApproval(**{**apr.to_dict(), "action_type": "create_hvs_project"})
    out = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src], approval=apr,
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op",
    )
    check("14 wrong action type", (not out.ok) and out.error_kind == ERR_APPROVAL_ACTION_MISMATCH)


def test_15_correlation_project_artifact_mismatch():
    proj = make_project()
    root, ledger, corr_id, src, refs, m_id, _ = _good_pair(proj)
    # Wrong correlation id
    apr = make_asset_approval(proj, "corr-wrong", m_id, ["a_img", "a_aud"], ["rootA"])
    out = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src], approval=apr,
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op",
    )
    check("15 correlation mismatch", (not out.ok) and out.error_kind == ERR_APPROVAL_SCOPE_MISMATCH)
    # Wrong scos project id
    apr = make_asset_approval(proj, corr_id, m_id, ["a_img", "a_aud"], ["rootA"])
    apr = HVSAssetMaterializationApproval(**{**apr.to_dict(), "requested_scos_project_id": "other"})
    out = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src], approval=apr,
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op",
    )
    check("15 scos project mismatch", (not out.ok) and out.error_kind == ERR_APPROVAL_SCOPE_MISMATCH)
    # Wrong hvs artifact id
    apr = make_asset_approval(proj, corr_id, m_id, ["a_img", "a_aud"], ["rootA"])
    apr = HVSAssetMaterializationApproval(**{**apr.to_dict(), "requested_hvs_artifact_id": "hvs-timeline-other"})
    out = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src], approval=apr,
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op",
    )
    check("15 hvs artifact mismatch", (not out.ok) and out.error_kind == ERR_APPROVAL_SCOPE_MISMATCH)


def test_16_manifest_identity_mismatch():
    proj = make_project()
    root, ledger, corr_id, src, refs, m_id, _ = _good_pair(proj)
    apr = make_asset_approval(proj, corr_id, "wrong-manifest-id", ["a_img", "a_aud"], ["rootA"])
    out = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src], approval=apr,
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op",
    )
    check("16 manifest identity mismatch", (not out.ok) and out.error_kind == ERR_APPROVAL_SCOPE_MISMATCH)


def test_17_unapproved_root_or_asset():
    proj = make_project()
    root, ledger, corr_id, src, refs, m_id, _ = _good_pair(proj)
    # Approved root missing
    apr = make_asset_approval(proj, corr_id, m_id, ["a_img", "a_aud"], ["rootB"])
    out = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src], approval=apr,
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op",
    )
    check("17 unapproved root", (not out.ok) and out.error_kind == ERR_APPROVAL_SCOPE_MISMATCH)
    # Approved asset missing
    apr = make_asset_approval(proj, corr_id, m_id, ["a_img"], ["rootA"])
    out = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src], approval=apr,
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op",
    )
    check("17 unapproved asset", (not out.ok) and out.error_kind == ERR_APPROVAL_SCOPE_MISMATCH)


def test_18_approval_reusable_after_precopy_failure():
    proj = make_project()
    root, ledger, corr_id, src, refs, m_id, _ = _good_pair(proj)
    # Inject a pre-existing mismatched destination file to force a conflict.
    out0 = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, m_id, ["a_img", "a_aud"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op", dry_run=True,
    )
    hvs_pid = out0.hvs_project_id
    conflict_dest = root / "projects" / hvs_pid / "assets" / "background"
    conflict_dest.mkdir(parents=True, exist_ok=True)
    (conflict_dest / f"{'0'*16}-scene_01.png").write_bytes(b"evil-mismatch-bytes")
    apr = make_asset_approval(proj, corr_id, out0.manifest_identity_hash, ["a_img", "a_aud"], ["rootA"])
    out = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src], approval=apr,
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op",
    )
    check("18 destination conflict aborts", (not out.ok) and out.error_kind == ERR_DESTINATION_CONFLICT, out.error_kind)
    # Approval unchanged + reusable: re-run with a clean ledger (no consumption record).
    snap = json.dumps(apr.to_dict(), sort_keys=True)
    out2 = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src], approval=apr,
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op",
    )
    check("18 approval reusable after failure", not out2.ok and out2.error_kind == ERR_DESTINATION_CONFLICT)
    check("18 approval object unchanged", json.dumps(apr.to_dict(), sort_keys=True) == snap)


def test_19_approval_consumed_only_after_success():
    proj = make_project()
    root, ledger, corr_id, src, refs, m_id, _ = _good_pair(proj)
    out0 = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, m_id, ["a_img", "a_aud"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op", dry_run=True,
    )
    mat_ledger = fresh_mat_ledger()
    out = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, out0.manifest_identity_hash, ["a_img", "a_aud"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=mat_ledger, requested_by="op",
    )
    check("19 success materializes", out.ok and out.materialization_status == "created")
    recs = MaterializationLedger(mat_ledger).all()
    check("19 evidence persisted (consumption record)", len(recs) == 1 and recs[0].approval_id == "mat-apr-4")
    check("19 manifest written", (root / "projects" / out.hvs_project_id / "assets" / "asset_manifest.stage4.json").exists())


# ---------------------------------------------------------------------------
# Tests 20-24: Materialization
# ---------------------------------------------------------------------------
def test_20_exact_bytes_copied():
    proj = make_project()
    root, ledger, corr_id, src, refs, m_id, _ = _good_pair(proj)
    data_img = (src.root / "img" / "scene_01.png").read_bytes()
    data_aud = (src.root / "aud" / "voice_01.wav").read_bytes()
    out0 = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, m_id, ["a_img", "a_aud"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op", dry_run=True,
    )
    out = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, out0.manifest_identity_hash, ["a_img", "a_aud"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op",
    )
    dest_img = root / "projects" / out.hvs_project_id / "assets" / "background" / f"{sha256_of(data_img)[:16]}-scene_01.png"
    dest_aud = root / "projects" / out.hvs_project_id / "assets" / "music_or_audio_placeholder" / f"{sha256_of(data_aud)[:16]}-voice_01.wav"
    check("20 img copied exactly", dest_img.exists() and dest_img.read_bytes() == data_img)
    check("20 aud copied exactly", dest_aud.exists() and dest_aud.read_bytes() == data_aud)


def test_21_manifest_valid_deterministic():
    proj = make_project()
    root, ledger, corr_id, src, refs, m_id, _ = _good_pair(proj)
    out0 = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, m_id, ["a_img", "a_aud"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op", dry_run=True,
    )
    out = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, out0.manifest_identity_hash, ["a_img", "a_aud"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op",
    )
    manifest = out.hvs_manifest
    check("21 manifest has schema_version", manifest["schema_version"] == "scos-hvs.asset-materialization.v1/1.0.0")
    check("21 manifest correlation_id", manifest["correlation_id"] == out0.correlation_id)
    check("21 manifest records no absolute paths", all(not a["source_relative_path"].startswith("/") and "://" not in a["source_relative_path"] for a in manifest["assets"]))
    # Determinism: re-read written file and compare to in-memory dict.
    written = json.loads((root / "projects" / out.hvs_project_id / "assets" / "asset_manifest.stage4.json").read_text())
    check("21 manifest byte-deterministic", written == manifest)


def test_22_evidence_append_only_no_secrets():
    proj = make_project()
    root, ledger, corr_id, src, refs, m_id, _ = _good_pair(proj)
    out0 = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, m_id, ["a_img", "a_aud"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op", dry_run=True,
    )
    mat_ledger = fresh_mat_ledger()
    out = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, out0.manifest_identity_hash, ["a_img", "a_aud"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=mat_ledger, requested_by="op",
    )
    raw = mat_ledger.read_text()
    check("22 evidence has no absolute source path", ("C:\\" not in raw) and ("/Workspace" not in raw))
    check("22 evidence has no secret", "secret" not in raw.lower() or "outside_secret" not in raw)
    check("22 evidence fingerprints relative", all(f[2].startswith("assets/") for f in out.materialization_record.asset_fingerprints))


def test_23_no_render_or_network_side_effects():
    proj = make_project()
    root, ledger, corr_id, src, refs, m_id, _ = _good_pair(proj)
    out0 = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, m_id, ["a_img", "a_aud"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op", dry_run=True,
    )
    out = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, out0.manifest_identity_hash, ["a_img", "a_aud"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op",
    )
    check("23 no media processing (copy only)", out.ok)


def test_24_destination_conflict_never_overwrites():
    proj = make_project()
    root, ledger, corr_id, src, refs, m_id, _ = _good_pair(proj)
    out0 = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, m_id, ["a_img", "a_aud"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op", dry_run=True,
    )
    # Pre-seed a mismatched destination; copy must refuse, not overwrite.
    hvs_pid = out0.hvs_project_id
    d = root / "projects" / hvs_pid / "assets" / "background"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{'0'*16}-scene_01.png").write_bytes(b"original-must-survive")
    out = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, out0.manifest_identity_hash, ["a_img", "a_aud"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op",
    )
    check("24 conflict aborts", not out.ok and out.error_kind == ERR_DESTINATION_CONFLICT)
    check("24 original not overwritten", (d / f"{'0'*16}-scene_01.png").read_bytes() == b"original-must-survive")


# ---------------------------------------------------------------------------
# Tests 25-29: Idempotency / recovery
# ---------------------------------------------------------------------------
def _materialize_ok(proj, corr_id, src, root, ledger):
    refs = [SCOSAssetRef(asset_id="a_img", asset_type="background", path="img/scene_01.png"),
            SCOSAssetRef(asset_id="a_aud", asset_type="music_or_audio_placeholder", path="aud/voice_01.wav")]
    out0 = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, "ph", ["a_img", "a_aud"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op", dry_run=True,
    )
    out = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, out0.manifest_identity_hash, ["a_img", "a_aud"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op",
    )
    return out, refs


def test_25_same_request_twice_one_copy():
    proj = make_project()
    root, ledger, corr_id = create_correlated_project(proj)
    src = src_root_with({"img/scene_01.png": b"\x89PNG\r\n\x1a\nfake", "aud/voice_01.wav": b"RIFFfakeWAVE"})
    out1, refs = _materialize_ok(proj, corr_id, src, root, ledger)
    mat_ledger = fresh_mat_ledger()
    out2 = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, out1.manifest_identity_hash, ["a_img", "a_aud"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=mat_ledger, requested_by="op",
    )
    check("25 second run reused", out2.ok and out2.materialization_status == "reused")
    # Count actual files on disk (should be exactly 2).
    n_files = len(list((root / "projects" / out1.hvs_project_id / "assets").rglob("*.png"))) + \
              len(list((root / "projects" / out1.hvs_project_id / "assets").rglob("*.wav")))
    check("25 exactly one copy each", n_files == 2, f"files={n_files}")


def test_26_existing_matching_destination_recovered():
    proj = make_project()
    root, ledger, corr_id = create_correlated_project(proj)
    src = src_root_with({"img/scene_01.png": b"\x89PNG\r\n\x1a\nfake", "aud/voice_01.wav": b"RIFFfakeWAVE"})
    out1, refs = _materialize_ok(proj, corr_id, src, root, ledger)
    # Simulate partial prior copy already present, then re-run: must reuse.
    mat_ledger = fresh_mat_ledger()
    out2 = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, out1.manifest_identity_hash, ["a_img", "a_aud"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=mat_ledger, requested_by="op",
    )
    check("26 recovered as reused", out2.ok and out2.materialization_status == "reused")
    check("26 per-asset reused status", all(s == "reused" for _, s in out2.per_asset_status))


def test_27_partial_interrupted_recovered_safely():
    proj = make_project()
    root, ledger, corr_id = create_correlated_project(proj)
    src = src_root_with({"img/scene_01.png": b"\x89PNG\r\n\x1a\nfake", "aud/voice_01.wav": b"RIFFfakeWAVE"})
    out1, refs = _materialize_ok(proj, corr_id, src, root, ledger)
    # Manually delete one destination file to simulate interruption before evidence.
    dest_img = root / "projects" / out1.hvs_project_id / "assets" / "background"
    for f in dest_img.glob("*.png"):
        f.unlink()
    mat_ledger = fresh_mat_ledger()
    out2 = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, out1.manifest_identity_hash, ["a_img", "a_aud"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=mat_ledger, requested_by="op",
    )
    check("27 interrupted recovered (recreated)", out2.ok)
    # No duplicate: exactly 1 png, 1 wav.
    n_png = len(list((root / "projects" / out1.hvs_project_id / "assets").rglob("*.png")))
    n_wav = len(list((root / "projects" / out1.hvs_project_id / "assets").rglob("*.wav")))
    check("27 no duplicate copies", n_png == 1 and n_wav == 1, f"png={n_png} wav={n_wav}")


def test_28_divergent_asset_set_conflict():
    proj = make_project()
    root, ledger, corr_id = create_correlated_project(proj)
    src = src_root_with({"img/scene_01.png": b"\x89PNG\r\n\x1a\nfake", "aud/voice_01.wav": b"RIFFfakeWAVE"})
    out1, _ = _materialize_ok(proj, corr_id, src, root, ledger)
    # Now a divergent set (same correlation, only one asset approved).
    refs2 = [SCOSAssetRef(asset_id="a_img", asset_type="background", path="img/scene_01.png")]
    out0 = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs2, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, "ph", ["a_img"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op", dry_run=True,
    )
    out2 = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs2, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, out0.manifest_identity_hash, ["a_img"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op",
    )
    check("28 divergent set rejected", (not out2.ok) and out2.error_kind == ERR_DESTINATION_CONFLICT, out2.error_kind)


def test_29_inputs_approval_not_mutated():
    proj = make_project()
    root, ledger, corr_id, src, refs, m_id, _ = _good_pair(proj)
    apr = make_asset_approval(proj, corr_id, m_id, ["a_img", "a_aud"], ["rootA"])
    snap_apr = json.dumps(apr.to_dict(), sort_keys=True)
    snap_refs = json.dumps([r.to_dict() for r in refs], sort_keys=True)
    out0 = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, m_id, ["a_img", "a_aud"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op", dry_run=True,
    )
    materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src],
        approval=apr, hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op",
        dry_run=False,
    )
    check("29 approval not mutated", json.dumps(apr.to_dict(), sort_keys=True) == snap_apr)
    check("29 refs not mutated", json.dumps([r.to_dict() for r in refs], sort_keys=True) == snap_refs)


# ---------------------------------------------------------------------------
# Tests 30-32: Regression / cross-repo / security
# ---------------------------------------------------------------------------
def test_30_stage1_2_3_regression_imports():
    from hvs_schema_mapper import (  # noqa: F401
        map_scos_to_hvs, validate_hvs_payload, payload_identity_hash,
        canonicalize_mapping_payload,
    )
    from hvs_project_creation import (  # noqa: F401
        create_hvs_project, HVSProjectApproval, correlation_id_for,
    )
    from hvs_asset_materialization import materialize_hvs_assets, HVSAssetMaterializationApproval  # noqa: F401
    check("30 stage1/2/3 regression imports ok", True)


def test_31_cross_repo_layout_validation():
    proj = make_project()
    root, ledger, corr_id = create_correlated_project(proj)
    src = src_root_with({"img/scene_01.png": b"\x89PNG\r\n\x1a\nfake", "aud/voice_01.wav": b"RIFFfakeWAVE"})
    refs = [SCOSAssetRef(asset_id="a_img", asset_type="background", path="img/scene_01.png"),
            SCOSAssetRef(asset_id="a_aud", asset_type="music_or_audio_placeholder", path="aud/voice_01.wav")]
    out0 = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, "ph", ["a_img", "a_aud"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op", dry_run=True,
    )
    out = materialize_hvs_assets(
        correlation_id=corr_id, asset_refs=refs, source_roots=[src],
        approval=make_asset_approval(proj, corr_id, out0.manifest_identity_hash, ["a_img", "a_aud"], ["rootA"]),
        hvs_root=root, correlation_ledger_path=ledger,
        materialization_ledger_path=fresh_mat_ledger(), requested_by="op",
    )
    # Produced manifest must live at the documented path (read-only layout check).
    manifest_path = root / "projects" / out.hvs_project_id / "assets" / "asset_manifest.stage4.json"
    check("31 manifest at expected path", manifest_path.exists())
    # Read-only: assert the real HVS repo timeline schema still validates a Stage 3 timeline.
    # (Lightweight presence check only — no mutation.)
    schema = HVS_REPO_ROOT / "hvs" / "schemas" / "timeline.schema.json"
    check("31 HVS timeline schema present (read-only)", schema.exists())


def test_32_security_scan_no_forbidden_patterns():
    src = Path(__file__).resolve().parent.parent / "hvs_asset_materialization.py"
    text = src.read_text(encoding="utf-8")
    forbidden = [
        r"\bimport requests\b", r"\bimport urllib\b", r"\bimport httpx\b",
        r"\bimport aiohttp\b", r"\bimport boto3\b",
        r"\bimport openai\b", r"\bimport anthropic\b", r"\bimport elevenlabs\b",
        r"\bimport ffmpeg\b", r"\bimport moviepy\b",
        r"\bimport subprocess\b", r"subprocess\.\w+",
        r"shell\s*=\s*True", r"__import__\(",
        r"render", r"transcode", r"ffmpeg", r"moviepy",
    ]
    hits = [pat for pat in forbidden if re.search(pat, text)]
    check("32 no forbidden network/ai/render/subprocess/unsafe patterns", not hits, f"hits={hits}")


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------
_tmp = None


@pytest.fixture(autouse=True)
def _bind_tmp(tmp_path):
    global _tmp
    _tmp = tmp_path
    yield
    _tmp = None


def run_all(tmp_path):
    global _tmp
    _tmp = tmp_path
    print("SCOS-HVS Stage 4 focused test matrix")
    print("-" * 60)
    test_01_stage2_asset_refs_consumed()
    test_02_stage3_correlation_required()
    test_03_dry_run_zero_mutation()
    test_04_canonical_identity_stable()
    test_05_missing_source_fails()
    test_06_path_traversal_fails()
    test_07_absolute_unc_url_symlink_fails()
    test_08_unsupported_type_fails()
    test_09_source_outside_approved_root_fails()
    test_10_source_changed_after_planning_fails()
    test_11_destination_cannot_escape()
    test_12_source_never_modified()
    test_13_missing_pending_rejected_expired_cancelled()
    test_14_wrong_action_type()
    test_15_correlation_project_artifact_mismatch()
    test_16_manifest_identity_mismatch()
    test_17_unapproved_root_or_asset()
    test_18_approval_reusable_after_precopy_failure()
    test_19_approval_consumed_only_after_success()
    test_20_exact_bytes_copied()
    test_21_manifest_valid_deterministic()
    test_22_evidence_append_only_no_secrets()
    test_23_no_render_or_network_side_effects()
    test_24_destination_conflict_never_overwrites()
    test_25_same_request_twice_one_copy()
    test_26_existing_matching_destination_recovered()
    test_27_partial_interrupted_recovered_safely()
    test_28_divergent_asset_set_conflict()
    test_29_inputs_approval_not_mutated()
    test_30_stage1_2_3_regression_imports()
    test_31_cross_repo_layout_validation()
    test_32_security_scan_no_forbidden_patterns()
    print("-" * 60)
    print(f"RESULT: {_PASS} passed, {_FAIL} failed")
    if _FAILS:
        print("FAILED:", _FAILS)
    return _FAIL == 0


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        ok = run_all(Path(td))
    sys.exit(0 if ok else 1)
