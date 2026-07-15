"""Tests for SCOS video-job verify-then-delete orchestrator (Part B).

All tests use temp dirs — never touch the real workspace files. The point is
to prove the safety gate (3 preconditions) and scoped deletion logic are correct.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.video_job_cleanup import (
    archive_exists,
    cleanup,
    learning_record_exists,
    plan_deletion,
    render_output_exists,
    verify_job,
)


def _seed(tmp_path: Path):
    ref = tmp_path / "input" / "reference"
    out = tmp_path / "output"
    archive = tmp_path / "integrations" / "learning" / "archive"
    db = tmp_path / "memory" / "database.json"
    for d in (ref, out, archive):
        d.mkdir(parents=True, exist_ok=True)
    (ref / "IMG_9402.MOV").write_bytes(b"x")
    (out / "rov_double_kill_final.mp4").write_bytes(b"x")
    (archive / "RoV_Double_Kill").mkdir()
    (archive / "RoV_Double_Kill" / "provenance.json").write_text("{}")
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_text(json.dumps([
        {"project_name": "RoV Double Kill - WF-1/2 Auto Short", "retention_score": 70}
    ], ensure_ascii=False))
    return ref, out, archive, db


def test_verify_all_pass(tmp_path: Path):
    ref, out, archive, db = _seed(tmp_path)
    rep = verify_job("RoV Double Kill", output_dir=out, db_path=db, archive_root=archive)
    assert rep["all_pass"] is True
    assert rep["blockers"] == []


def test_verify_fails_when_render_missing(tmp_path: Path):
    ref, out, archive, db = _seed(tmp_path)
    (out / "rov_double_kill_final.mp4").unlink()
    rep = verify_job("RoV Double Kill", output_dir=out, db_path=db, archive_root=archive)
    assert rep["all_pass"] is False
    assert any(k == "render" and not v["ok"] for k, v in rep["checks"].items())


def test_verify_fails_when_archive_empty(tmp_path: Path):
    ref, out, archive, db = _seed(tmp_path)
    (archive / "RoV_Double_Kill" / "provenance.json").unlink()
    rep = verify_job("RoV Double Kill", output_dir=out, db_path=db, archive_root=archive)
    assert rep["all_pass"] is False
    assert rep["checks"]["archive"]["ok"] is False


def test_cleanup_refused_when_preconditions_fail(tmp_path: Path):
    ref, out, archive, db = _seed(tmp_path)
    (out / "rov_double_kill_final.mp4").unlink()  # break precondition
    rep = verify_job("RoV Double Kill", output_dir=out, db_path=db, archive_root=archive)
    src = ref / "IMG_9402.MOV"
    res = cleanup([str(src)], rep, reference_dir=ref, execute=True)
    assert res["refused"] is True
    assert src.exists()  # NOT deleted


def test_cleanup_dry_run_does_not_delete(tmp_path: Path):
    ref, out, archive, db = _seed(tmp_path)
    rep = verify_job("RoV Double Kill", output_dir=out, db_path=db, archive_root=archive)
    src = ref / "IMG_9402.MOV"
    res = cleanup([str(src)], rep, reference_dir=ref, execute=False)
    assert res["dry_run"] is True
    assert res["deleted"] == []
    assert src.exists()  # still present


def test_cleanup_execute_deletes_scoped_source(tmp_path: Path):
    ref, out, archive, db = _seed(tmp_path)
    rep = verify_job("RoV Double Kill", output_dir=out, db_path=db, archive_root=archive)
    src = ref / "IMG_9402.MOV"
    res = cleanup([str(src)], rep, reference_dir=ref, execute=True)
    assert res["deleted"] == [str(src)]
    assert not src.exists()


def test_plan_rejects_files_outside_reference(tmp_path: Path):
    ref, out, archive, db = _seed(tmp_path)
    outside = tmp_path / "secret.MOV"
    outside.write_bytes(b"x")
    plan = plan_deletion([str(outside)], ref)
    assert str(outside) in [p for p, _ in plan["rejected"]]
    assert plan["planned"] == []


def test_plan_rejects_disallowed_extension(tmp_path: Path):
    ref, out, archive, db = _seed(tmp_path)
    bad = ref / "notes.doc"
    bad.write_bytes(b"x")
    plan = plan_deletion([str(bad)], ref)
    assert str(bad) in [p for p, _ in plan["rejected"]]


def test_render_hint_explicit_path(tmp_path: Path):
    out = tmp_path / "output"
    out.mkdir()
    explicit = out / "final_v3.mp4"
    explicit.write_bytes(b"x")
    ok, detail = render_output_exists(out, "Any", render_hint=str(explicit))
    assert ok is True
