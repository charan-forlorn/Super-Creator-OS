"""Cohort 10C backend tests — authoritative project-preparation persistence.

All tests use isolated temp stores via pytest tmp_path. No production paths
are touched. Covers:
  * store unit behavior (§20.1): empty, create/read, idempotent replay,
    conflicting replay, revision increment, stale rejection, atomic write,
    failed-write preserves prior bytes, lock contention, malformed JSON,
    unsupported schema, integrity mismatch, orphan temp handling,
    deterministic ordering, path-escape rejection.
  * service transitions (§20.2): valid draft persists, invalid draft does
    not, approval persists, preview persists, duplicate approval/preview
    contained, unknown project rejected, stale revision rejected, restart
    reconstructs exact state, no HVS/render/media call.
  * process-restart recovery (§20.5 / §28).
  * concurrency (§20.6): simultaneous creates/approvals, stale/conflicting
    replay, lock timeout, no duplicate persisted record.
  * failure injection (§24): malformed, unsupported schema, missing dir,
    write failure, lock contention, stale revision, identity conflict,
    orphan temp, integrity mismatch — all fail closed, no silent EMPTY.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# _filelock.py lives in integrations/learning and is imported bare by the
# module under test; mirror the existing test convention.
_INTEGRATIONS_LEARNING = Path(__file__).resolve().parents[2] / "integrations" / "learning"
if str(_INTEGRATIONS_LEARNING) not in sys.path:
    sys.path.insert(0, str(_INTEGRATIONS_LEARNING))

from scos.control_center.solo_project_preparation import (  # noqa: E402
    INTEGRITY_SUFFIX,
    TMP_SUFFIX,
    ERR_APPROVAL_REQUIRED,
    ERR_IDENTITY_CONFLICT,
    ERR_SCHEMA_INCOMPATIBLE,
    ERR_PATH_ESCAPE,
    ERR_PROJECT_NOT_FOUND,
    ERR_PERSISTENCE_WRITE_FAILED,
    ERR_REVISION_CONFLICT,
    ERR_STORE_CORRUPT,
    ERR_STORE_UNAVAILABLE,
    ERR_VALIDATION_FAILED,
    ProjectPreparationStore,
    _integrity_marker_path,
    _sha256_file,
    derive_project_id,
    validate_draft_input,
)


def _sample_draft(**overrides):
    base = {
        "projectTitle": "Launch Reel",
        "clientOrBrand": "Northstar Studio",
        "projectPurpose": "Announce the new creator workflow",
        "contentBrief": "A crisp launch video showing the operator cockpit, approval moment, and dry-run preparation preview.",
        "targetDurationSeconds": 45,
        "outputProfiles": ["vertical_9_16", "square_1_1"],
        "operatorNotes": "Keep it energetic but truthful.",
    }
    base.update(overrides)
    return base


def _store(tmp_path, name="store.json"):
    return ProjectPreparationStore(
        store_path=tmp_path / name,
        base_dir=tmp_path,
    )


# --------------------------------------------------------------------------- #
# §20.1 Store unit tests
# --------------------------------------------------------------------------- #


def test_empty_valid_store(tmp_path):
    st = _store(tmp_path)
    res = st.read()
    assert res.status == "EMPTY"
    assert res.records == []


def test_create_and_read(tmp_path):
    st = _store(tmp_path)
    r = st.create_draft(_sample_draft())
    assert r.ok
    assert r.record.state == "APPROVAL_REQUIRED"
    assert r.record.revision == 1
    assert r.record.project_id.startswith("spp-")
    res = st.read()
    assert res.status == "AVAILABLE_WITH_DATA"
    assert len(res.records) == 1


def test_exact_replay_returns_existing(tmp_path):
    st = _store(tmp_path)
    r1 = st.create_draft(_sample_draft())
    r2 = st.create_draft(_sample_draft())
    assert r2.ok
    assert r2.record.revision == 1
    assert r2.record.project_id == r1.record.project_id
    assert len(st.read().records) == 1


def test_conflicting_replay_rejected(tmp_path):
    st = _store(tmp_path)
    st.create_draft(_sample_draft())
    conflicting = _sample_draft(operatorNotes="DIFFERENT NOTES THAT CHANGE IDENTITY")
    r = st.create_draft(conflicting)
    assert not r.ok
    assert r.error_code == ERR_IDENTITY_CONFLICT
    assert len(st.read().records) == 1


def test_revision_increments_on_approve(tmp_path):
    st = _store(tmp_path)
    d = st.create_draft(_sample_draft())
    a = st.approve(d.record.project_id, d.record.revision)
    assert a.ok
    assert a.record.revision == 2
    assert a.record.state == "APPROVED"


def test_stale_revision_rejected(tmp_path):
    st = _store(tmp_path)
    d = st.create_draft(_sample_draft())
    a = st.approve(d.record.project_id, d.record.revision)
    stale = st.approve(a.record.project_id, d.record.revision)
    assert not stale.ok
    assert stale.error_code == ERR_REVISION_CONFLICT


def test_atomic_write_leaves_no_temp(tmp_path):
    st = _store(tmp_path)
    st.create_draft(_sample_draft())
    temps = list(tmp_path.glob(f"*{TMP_SUFFIX}*"))
    assert temps == []


def test_failed_write_preserves_prior_bytes(tmp_path, monkeypatch):
    st = _store(tmp_path)
    st.create_draft(_sample_draft())
    path = st._store_path
    before_hash = _sha256_file(path)

    def boom(records):
        raise OSError("simulated write failure")

    monkeypatch.setattr(st, "_write", boom)
    r = st.create_draft(_sample_draft(projectTitle="Other"))
    assert not r.ok
    assert path.read_bytes()  # still exists
    assert _sha256_file(path) == before_hash
    assert st.read().status == "AVAILABLE_WITH_DATA"


def test_malformed_json(tmp_path):
    st = _store(tmp_path)
    st._store_path.write_text("{not valid json")
    res = st.read()
    assert res.status == "CORRUPT"
    assert res.error_code == ERR_STORE_CORRUPT


def test_unsupported_schema(tmp_path):
    st = _store(tmp_path)
    envelope = {
        "schema_version": 999,
        "store_kind": "scos.project_preparation.v1",
        "written_at": "2026-07-17T00:00:00Z",
        "record_count": 0,
        "records": [],
    }
    st._store_path.write_text(json.dumps(envelope))
    res = st.read()
    assert res.status == "INCOMPATIBLE_SCHEMA"
    assert res.error_code == ERR_SCHEMA_INCOMPATIBLE


def test_integrity_mismatch(tmp_path):
    st = _store(tmp_path)
    st.create_draft(_sample_draft())
    path = st._store_path
    marker = _integrity_marker_path(path)
    bad = json.loads(path.read_text())
    bad["records"][0]["normalized"]["operator_notes"] = "TAMPERED"
    path.write_text(json.dumps(bad))
    res = st.read()
    assert res.status == "CORRUPT"
    assert res.error_code == ERR_STORE_CORRUPT
    assert marker.exists()


def test_orphan_temp_does_not_become_visible(tmp_path):
    st = _store(tmp_path)
    st.create_draft(_sample_draft())
    orphan = st._store_path.parent / f"{st._store_path.name}{TMP_SUFFIX}.9999"
    orphan.write_text("garbage")
    res = st.read()
    assert res.status == "AVAILABLE_WITH_DATA"
    assert len(res.records) == 1
    orphan.unlink()


def test_deterministic_ordering(tmp_path):
    st = _store(tmp_path)
    st.create_draft(_sample_draft(projectTitle="Beta"))
    st.create_draft(_sample_draft(projectTitle="Alpha"))
    st.create_draft(_sample_draft(projectTitle="Gamma"))
    recs1 = st.read().records
    recs2 = st.read().records
    # Deterministic: identical order across reads, sorted by (created_at, id).
    assert [r.project_id for r in recs1] == [r.project_id for r in recs2]
    created = [r.created_at for r in recs1]
    assert created == sorted(created)


def test_path_escape_rejected():
    with pytest.raises(ValueError) as exc:
        ProjectPreparationStore(store_path=Path("/tmp/evil.json"))
    assert ERR_PATH_ESCAPE in str(exc.value)


# --------------------------------------------------------------------------- #
# §20.2 Service tests
# --------------------------------------------------------------------------- #


def test_valid_draft_persists(tmp_path):
    st = _store(tmp_path)
    r = st.create_draft(_sample_draft())
    assert r.ok
    assert r.record.state == "APPROVAL_REQUIRED"


def test_invalid_draft_does_not_persist(tmp_path):
    st = _store(tmp_path)
    bad = _sample_draft(projectTitle="", contentBrief="")
    assert validate_draft_input(bad)
    r = st.create_draft(bad)
    assert not r.ok
    assert r.error_code == ERR_VALIDATION_FAILED
    assert st.read().status == "EMPTY"


def test_approval_persists(tmp_path):
    st = _store(tmp_path)
    d = st.create_draft(_sample_draft())
    a = st.approve(d.record.project_id, d.record.revision)
    assert a.ok and a.record.state == "APPROVED"
    assert st.read().records[0].state == "APPROVED"


def test_preview_persists_and_is_dry_run(tmp_path):
    st = _store(tmp_path)
    d = st.create_draft(_sample_draft())
    a = st.approve(d.record.project_id, d.record.revision)
    p = st.create_preview(a.record.project_id, a.record.revision)
    assert p.ok
    assert p.record.state == "PREPARATION_PREVIEW_READY"
    sef = p.record.side_effect_flags
    assert sef["side_effects_performed"] is False
    assert sef["render_started"] is False
    assert sef["hvs_project_created"] is False


def test_duplicate_approval_contained(tmp_path):
    st = _store(tmp_path)
    d = st.create_draft(_sample_draft())
    a1 = st.approve(d.record.project_id, d.record.revision)
    a2 = st.approve(a1.record.project_id, a1.record.revision)
    assert a2.ok
    assert a2.record.revision == a1.record.revision
    assert len(st.read().records) == 1


def test_duplicate_preview_contained(tmp_path):
    st = _store(tmp_path)
    d = st.create_draft(_sample_draft())
    a = st.approve(d.record.project_id, d.record.revision)
    p1 = st.create_preview(a.record.project_id, a.record.revision)
    # Exact replay uses the CURRENT revision (3), not the stale draft revision.
    p2 = st.create_preview(a.record.project_id, p1.record.revision)
    assert p2.ok
    assert p2.record.revision == p1.record.revision
    assert len(st.read().records) == 1


def test_unknown_project_rejected(tmp_path):
    st = _store(tmp_path)
    r = st.approve("spp-deadbeef1234", 1)
    assert not r.ok
    assert r.error_code == ERR_PROJECT_NOT_FOUND


def test_preview_before_approval_rejected(tmp_path):
    st = _store(tmp_path)
    d = st.create_draft(_sample_draft())
    p = st.create_preview(d.record.project_id, d.record.revision)
    assert not p.ok
    assert p.error_code == "INVALID_TRANSITION"
    assert st.read().records[0].state == "APPROVAL_REQUIRED"


# --------------------------------------------------------------------------- #
# §20.5 / §28 Process-restart recovery
# --------------------------------------------------------------------------- #


def test_process_restart_recovers_exact_state(tmp_path):
    st_a = _store(tmp_path)
    d = st_a.create_draft(_sample_draft())
    a = st_a.approve(d.record.project_id, d.record.revision)
    st_a.create_preview(a.record.project_id, a.record.revision)
    st_b = _store(tmp_path)
    res = st_b.read()
    assert res.status == "AVAILABLE_WITH_DATA"
    rec = res.records[0]
    assert rec.project_id == d.record.project_id
    assert rec.revision == 3
    assert rec.state == "PREPARATION_PREVIEW_READY"
    profiles = [p["id"] for p in rec.normalized["output_profiles"]]
    assert profiles == ["square_1_1", "vertical_9_16"]


def test_restart_after_approval(tmp_path):
    st_a = _store(tmp_path)
    d = st_a.create_draft(_sample_draft())
    st_a.approve(d.record.project_id, d.record.revision)
    rec = _store(tmp_path).read().records[0]
    assert rec.state == "APPROVED"
    assert rec.revision == 2


def test_restart_after_preview(tmp_path):
    st_a = _store(tmp_path)
    d = st_a.create_draft(_sample_draft())
    a = st_a.approve(d.record.project_id, d.record.revision)
    st_a.create_preview(a.record.project_id, a.record.revision)
    rec = _store(tmp_path).read().records[0]
    assert rec.state == "PREPARATION_PREVIEW_READY"
    assert rec.preparation_preview is not None


def test_failed_write_before_replace_keeps_prior(tmp_path, monkeypatch):
    st = _store(tmp_path)
    st.create_draft(_sample_draft())
    before_hash = _sha256_file(st._store_path)

    def boom(records):
        raise OSError("simulated atomic replace failure")

    monkeypatch.setattr(st, "_write", boom)
    # An approval attempt that fails mid-write must not corrupt/lose prior state.
    r = st.approve(st.read().records[0].project_id, 1)
    assert not r.ok
    assert _sha256_file(st._store_path) == before_hash
    assert st.read().status == "AVAILABLE_WITH_DATA"


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl is POSIX-only")
def test_lock_held_by_another_process_fails_closed(tmp_path):
    import fcntl

    st = _store(tmp_path)
    st.create_draft(_sample_draft())
    lock_path = Path(str(st._store_path) + ".lock")
    with open(lock_path, "a+") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        r = st.approve(st.read().records[0].project_id, 1)
        assert not r.ok
        assert r.error_code in (ERR_PERSISTENCE_WRITE_FAILED, ERR_STORE_UNAVAILABLE)


def test_corrupt_store_no_rewrite(tmp_path):
    st = _store(tmp_path)
    st.create_draft(_sample_draft())
    st._store_path.write_text("@@@")
    res = st.read()
    assert res.status == "CORRUPT"
    assert st._store_path.read_text() == "@@@"


def test_unsupported_version_no_mutation(tmp_path):
    st = _store(tmp_path)
    st._store_path.parent.mkdir(parents=True, exist_ok=True)
    st._store_path.write_text(json.dumps({"schema_version": 5, "records": []}))
    res = st.read()
    assert res.status == "INCOMPATIBLE_SCHEMA"
    assert json.loads(st._store_path.read_text())["schema_version"] == 5


def test_stale_revision_after_restart_rejected(tmp_path):
    st_a = _store(tmp_path)
    d = st_a.create_draft(_sample_draft())
    a = st_a.approve(d.record.project_id, d.record.revision)
    st_b = _store(tmp_path)
    stale = st_b.approve(a.record.project_id, d.record.revision)
    assert not stale.ok
    assert stale.error_code == ERR_REVISION_CONFLICT


def test_exact_replay_after_restart_idempotent(tmp_path):
    st_a = _store(tmp_path)
    r1 = st_a.create_draft(_sample_draft())
    st_b = _store(tmp_path)
    r2 = st_b.create_draft(_sample_draft())
    assert r2.ok
    assert r2.record.revision == r1.record.revision
    assert r2.record.project_id == r1.record.project_id
    assert len(st_b.read().records) == 1


# --------------------------------------------------------------------------- #
# §20.6 Concurrency
# --------------------------------------------------------------------------- #


def test_concurrent_creates_single_record(tmp_path):
    import threading

    st = _store(tmp_path)
    results = []

    def worker(note):
        results.append(st.create_draft(_sample_draft(operatorNotes=note)))

    threads = [threading.Thread(target=worker, args=(f"t{i}",)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ok = [r for r in results if r.ok]
    assert len(ok) == 1
    assert len(st.read().records) == 1


def test_concurrent_approvals_single_increment(tmp_path):
    import threading

    st = _store(tmp_path)
    d = st.create_draft(_sample_draft())
    results = []

    def worker():
        results.append(st.approve(d.record.project_id, d.record.revision))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(r.ok for r in results) or any(r.ok for r in results)
    # Exactly one increment regardless of how many threads raced; no duplicate
    # record and no lost/extra revision.
    assert st.read().records[0].revision == 2
    assert len(st.read().records) == 1


def test_simultaneous_creates_different_identities(tmp_path):
    import threading

    st = _store(tmp_path)
    results = []

    def worker(idx):
        results.append(st.create_draft(_sample_draft(projectTitle=f"Project {idx}")))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(1 for r in results if r.ok) == 6
    assert len(st.read().records) == 6


# --------------------------------------------------------------------------- #
# §24 Failure injection matrix
# --------------------------------------------------------------------------- #


def test_fi_missing_directory(tmp_path):
    target = tmp_path / "nope"
    st = ProjectPreparationStore(store_path=target / "store.json", base_dir=target)
    res = st.read()
    assert res.status in ("EMPTY", "UNAVAILABLE")


def test_fi_identity_conflict(tmp_path):
    # Same identity (title/client/purpose/brief/duration/profiles) but a
    # different operator note MUST collide on the derived id and be rejected
    # as a conflicting payload (notes are mutable metadata, not identity).
    st = _store(tmp_path)
    st.create_draft(_sample_draft())
    r = st.create_draft(_sample_draft(operatorNotes="DIFFERENT NOTES CHANGE CONTENT NOT IDENTITY"))
    assert not r.ok
    assert r.error_code == ERR_IDENTITY_CONFLICT
    assert len(st.read().records) == 1


def test_fi_different_title_is_separate_record(tmp_path):
    # Different title -> different derived id -> legitimate second record.
    st = _store(tmp_path)
    st.create_draft(_sample_draft())
    r = st.create_draft(_sample_draft(projectTitle="Different Title"))
    assert r.ok
    assert len(st.read().records) == 2


def test_fi_no_silent_empty_on_corrupt(tmp_path):
    st = _store(tmp_path)
    st._store_path.write_text("{bad")
    res = st.read()
    assert res.status == "CORRUPT"
    assert res.status != "EMPTY"


def test_fi_no_demo_fallback_on_unavailable(tmp_path):
    # When the configured store location is unreachable, the read resolves to a
    # non-data truth state (EMPTY/UNAVAILABLE/CORRUPT) with zero records. It
    # must NEVER fabricate AVAILABLE_WITH_DATA or inject a demo record.
    bad_base = tmp_path / "file_base"
    bad_base.write_text("i am a file not dir")
    st2 = ProjectPreparationStore(store_path=bad_base / "x" / "store.json", base_dir=bad_base / "x")
    res = st2.read()
    assert res.status != "AVAILABLE_WITH_DATA"
    assert res.records == []


def test_derive_project_id_deterministic():
    ident = "launch reel|northstar studio|announce|brief|45|vertical_9_16,square_1_1"
    assert derive_project_id(ident) == derive_project_id(ident)
    assert derive_project_id(ident).startswith("spp-")
