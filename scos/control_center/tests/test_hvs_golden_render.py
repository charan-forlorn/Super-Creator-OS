"""Cohort 10G — focused tests for golden render models + service (QA + delivery).

These tests verify:
  * profile registry mirrors HVS (3 profiles, exact dims/fps);
  * deterministic id derivation (replay returns identical ids);
  * QA battery on a REAL rendered artifact (ffprobe + frame/audio sampling);
  * delivery package is sealed/redacted (relative paths, checksums, rights);
  * orchestrator performs exactly one real HVS render (stubbed runner) and
    persists an attempt; a missing artifact fails closed (no success).

Plain pytest collection (no relative imports) — matches repo convention.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Repo convention: import via the absolute package path (scos.control_center
# is a package; pytest runs from the repo root). The testpaths in pytest.ini
# include `scos`, so the `scos` package is importable as-is.
from scos.control_center.hvs_golden_render_models import (  # noqa: E402
    QA_PASSED,
    QA_POLICY,
    derive_artifact_id,
    derive_delivery_id,
    derive_qa_report_id,
    get_profile,
    is_supported_profile,
    RENDER_PROFILES,
    SUPPORTED_PROFILE_IDS,
)
from scos.control_center.hvs_golden_render_service import (  # noqa: E402
    GoldenRenderAttempt,
    GoldenRenderStore,
    build_delivery_package,
    execute_golden_render,
    resolve_hyperframes_bin_dir,
    run_media_qa,
)


def pytest_skip(msg):
    import pytest
    pytest.skip(msg)


def test_profiles_mirror_hvs_contract():
    assert SUPPORTED_PROFILE_IDS == ("vertical_9_16", "square_1_1", "landscape_16_9")
    v = get_profile("vertical_9_16")
    assert (v.width, v.height, v.fps) == (1080, 1920, 30)
    s = get_profile("square_1_1")
    assert (s.width, s.height, s.fps) == (1080, 1080, 30)
    l = get_profile("landscape_16_9")
    assert (l.width, l.height, l.fps) == (1920, 1080, 30)
    assert all(is_supported_profile(p) for p in SUPPORTED_PROFILE_IDS)
    assert not is_supported_profile("diagonal_2_3")


def test_deterministic_ids_replay_stable():
    kw = dict(project_id="p1", attempt_id="a1",
              artifact_checksum="c1", profile_id="vertical_9_16")
    assert derive_qa_report_id(**kw) == derive_qa_report_id(**kw)
    assert derive_artifact_id(hvs_project_id="h1", profile_id="square_1_1",
                              attempt_id="a1") == derive_artifact_id(
        hvs_project_id="h1", profile_id="square_1_1", attempt_id="a1")
    assert derive_delivery_id(qa_report_id="q1", artifact_checksum="c1") == \
        derive_delivery_id(qa_report_id="q1", artifact_checksum="c1")


def test_resolve_hyperframes_bin_dir_approved_root():
    d = resolve_hyperframes_bin_dir()
    assert "hyperframes-0.7.45" in d
    assert Path(d).is_dir()


def _real_artifact() -> Path:
    cand = Path(r"C:\Users\chara\AppData\Local\Temp\hf_proof8\out.mp4")
    if not cand.is_file():
        pytest_skip("real render fixture missing (run de-risk render first)")
    return cand


def test_media_qa_on_real_artifact():
    art = _real_artifact()
    qa = run_media_qa(
        project_id="p1", hvs_project_id="h1", attempt_id="a1",
        profile_id="vertical_9_16", artifact_path=str(art),
        recorded_at="2026-07-21T00:00:00Z",
        tool_versions={"ffprobe": "8.1.2", "ffmpeg": "8.1.2", "hyperframes": "0.7.45"},
    )
    d = qa.to_dict()
    names = {c["name"] for c in d["checks"]}
    assert "artifact_exists" in names
    assert "video_codec" in names
    assert "width" in names and "height" in names
    w = next(c for c in d["checks"] if c["name"] == "width")
    h = next(c for c in d["checks"] if c["name"] == "height")
    assert w["status"] == "PASS" and h["status"] == "PASS"
    chk = next(c for c in d["checks"] if c["name"] == "checksum")
    assert chk["status"] == "PASS" and len(chk["measured"]) == 16
    qa2 = run_media_qa(
        project_id="p1", hvs_project_id="h1", attempt_id="a1",
        profile_id="vertical_9_16", artifact_path=str(art),
        recorded_at="2026-07-21T00:00:00Z",
        tool_versions={"ffprobe": "8.1.2", "ffmpeg": "8.1.2", "hyperframes": "0.7.45"},
    )
    assert qa2.qa_report_id == qa.qa_report_id
    assert (qa.overall_state == "QA_PASSED") == (len(qa.failure_codes) == 0)


def test_delivery_package_sealed_and_redacted():
    art = _real_artifact()
    store = GoldenRenderStore(store_path=tempfile.mkdtemp() + "/attempts.jsonl")
    qa = run_media_qa(
        project_id="p1", hvs_project_id="h1", attempt_id="a1",
        profile_id="vertical_9_16", artifact_path=str(art),
        recorded_at="2026-07-21T00:00:00Z",
        tool_versions={"ffprobe": "8.1.2", "ffmpeg": "8.1.2", "hyperframes": "0.7.45"},
    )
    att = GoldenRenderAttempt(
        project_id="p1", hvs_project_id="h1", attempt_id="a1",
        profile_id="vertical_9_16", operator_id="op1", authorization_id="az1",
        render_state="RENDER_SUCCEEDED", qa_state=QA_PASSED,
        delivery_state="DELIVERY_APPROVAL_REQUIRED",
        artifact_id=qa.artifact_id, artifact_checksum=qa.artifact_checksum,
        artifact_relative_path="projects/h1/render_batches/x/outputs/vertical_9_16.mp4",
        qa_report_id=qa.qa_report_id, delivery_id="", recorded_at="2026-07-21T00:00:00Z",
    )
    out = tempfile.mkdtemp()
    pkg = build_delivery_package(
        project_id="p1", hvs_project_id="h1", attempt=att, qa_report=qa,
        artifact_path=str(art), output_dir=out, operator_id="op1",
        recorded_at="2026-07-21T00:00:00Z", caption_text="ดื่มนำ้ให้เพียงพอ",
    )
    assert pkg["ok"] is True
    assert pkg["delivery_state"] == "DELIVERY_PACKAGE_READY"
    man = pkg["manifest"]
    assert man["paths_relative"] is True
    assert any("C:" in str(v) for v in man.values()) is False
    assert man["files"][0]["sha256"] == qa.artifact_checksum
    pkg_dir = Path(pkg["delivery_dir"])
    assert (pkg_dir / "delivery_manifest.json").is_file()
    assert (pkg_dir / "qa_report.json").is_file()
    assert (pkg_dir / "README.md").is_file()
    media = list(pkg_dir.glob("*.mp4"))
    assert len(media) == 1 and media[0].stat().st_size > 0


def test_orchestrator_single_real_render_stubbed():
    store = GoldenRenderStore(store_path=tempfile.mkdtemp() + "/attempts.jsonl")
    calls = []

    def fake_run(*, python_executable, hvs_repo_root, hvs_project_id, profile_id,
                 timeout_seconds, hyperframes_bin_dir):
        calls.append(profile_id)
        root = Path(hvs_repo_root)
        batch = root / "projects" / hvs_project_id / "render_batches" / "b1" / "outputs"
        batch.mkdir(parents=True, exist_ok=True)
        mp4 = batch / f"{profile_id}.mp4"
        mp4.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2000)
        return ({"verdict": "PASS", "renderer_called": True}, "{}", 0)

    res = execute_golden_render(
        project_id="p1", hvs_project_id="h1", profile_id="vertical_9_16",
        operator_id="op1", authorization_id="az1", hvs_repo_root=tempfile.mkdtemp(),
        store=store, recorded_at="2026-07-21T00:00:00Z", hvs_cli_run=fake_run,
    )
    assert res.ok is True
    assert len(calls) == 1  # exactly ONE real render
    assert res.attempt.render_state == "RENDER_SUCCEEDED"
    assert res.qa_report is not None


def test_orchestrator_missing_artifact_fails_closed():
    store = GoldenRenderStore(store_path=tempfile.mkdtemp() + "/attempts.jsonl")

    def fake_run_no_artifact(*, python_executable, hvs_repo_root, hvs_project_id,
                             profile_id, timeout_seconds, hyperframes_bin_dir):
        return ({"verdict": "PASS", "renderer_called": True}, "{}", 0)

    res = execute_golden_render(
        project_id="p1", hvs_project_id="h1", profile_id="square_1_1",
        operator_id="op1", authorization_id="az1", hvs_repo_root=tempfile.mkdtemp(),
        store=store, recorded_at="2026-07-21T00:00:00Z", hvs_cli_run=fake_run_no_artifact,
    )
    assert res.ok is False
    assert res.attempt.render_state == "RENDER_FAILED_CONFIRMED"
    assert res.error_code == "ARTIFACT_NOT_FOUND"


def test_unsupported_profile_rejected():
    store = GoldenRenderStore(store_path=tempfile.mkdtemp() + "/attempts.jsonl")
    res = execute_golden_render(
        project_id="p1", hvs_project_id="h1", profile_id="diagonal_2_3",
        operator_id="op1", authorization_id="az1", hvs_repo_root=tempfile.mkdtemp(),
        store=store, recorded_at="2026-07-21T00:00:00Z",
    )
    assert res.ok is False
    assert res.error_code == "PROFILE_UNSUPPORTED"
