from __future__ import annotations

from pathlib import Path

from scos.control_center.hvs_pilot_identity import (
    build_mapping, derive_canonical_id, IdentityStore, IdentityMapping,
)


def test_canonical_id_deterministic():
    a = derive_canonical_id("PILOT-2026-001-PROJ-01")
    b = derive_canonical_id("PILOT-2026-001-PROJ-01")
    assert a == b
    assert a.startswith("spp-") and len(a) == 16


def test_exact_replay_no_second_write(tmp_path: Path):
    store = IdentityStore(tmp_path / "identity.jsonl")
    m = build_mapping(external_project_ref="PILOT-2026-001-PROJ-01", pilot_id="PILOT-2026-001",
                      customer_ref="CUST-A1", packet_sha256="deadbeef")
    w1, c1 = store.persist(m)
    assert w1 is True and c1 is None
    # Exact replay: same mapping -> no new write.
    w2, c2 = store.persist(m)
    assert w2 is False and c2 is None
    assert store.find("PILOT-2026-001-PROJ-01").canonical_internal_project_id == m.canonical_internal_project_id
    lines = (tmp_path / "identity.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


def test_conflicting_replay_fails_closed(tmp_path: Path):
    store = IdentityStore(tmp_path / "identity.jsonl")
    # Pre-seed a mapping for a given external ref with a specific canonical id.
    m1 = build_mapping(external_project_ref="PILOT-2026-001-PROJ-01", pilot_id="PILOT-2026-001",
                       customer_ref="CUST-A1", packet_sha256="deadbeef",
                       created_at="2026-08-01T00:00:00.000000Z")
    w1, _ = store.persist(m1)
    assert w1
    # A conflicting replay: identical external ref but a DIFFERENT canonical id
    # (e.g. derived under a different contract version). Must fail closed.
    m2 = IdentityMapping(
        external_project_ref="PILOT-2026-001-PROJ-01", canonical_internal_project_id="spp-different12",
        pilot_id="PILOT-2026-001", customer_ref="CUST-A1", mapping_version="1",
        created_at="2026-08-01T00:00:01.000000Z", packet_sha256="feedface",
    )
    w2, c2 = store.persist(m2)
    assert w2 is False and c2 == "CONFLICTING_IDENTITY_REPLAY"
