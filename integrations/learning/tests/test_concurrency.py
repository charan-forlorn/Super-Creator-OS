"""test_concurrency.py — regression suite for the P0-4 concurrency hotfix.

Proves the fixes from memory_concurrency_audit.md (Option A) actually hold, using
REAL OS processes (not threads — the GIL would hide the race). Each store is hit by
N concurrent writer processes; with the cross-process file lock the final state must
be exactly complete (no lost update) and leave no shared-temp debris.

Reproduces / guards:
  - concurrent writers          -> N processes append to one store at once
  - lost-update race (3.1, 3.5) -> assert final count == every write (none dropped)
  - temp-file collision (3.3)   -> assert no leftover "*.tmp" + store stays valid JSON
  - lock primitive              -> nested acquire times out (mutual exclusion works)

100% isolated: tempfile dirs only. Never touches production memory.

No pytest. Run standalone:
    python integrations/learning/tests/test_concurrency.py
Exit 0 if all pass, 1 otherwise.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PKG = _HERE.parent                                   # integrations/learning
sys.path.insert(0, str(_PKG))

import _filelock as FL                                 # noqa: E402

_PASS, _FAIL = 0, 0

# Tunables — small enough to be fast, large enough to force real overlap.
N_WORKERS = 6
N_APPENDS = 8


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  PASS  {name}")
    else:
        _FAIL += 1
        print(f"  FAIL  {name}")


# A self-contained worker. Each process loops N_APPENDS times against `target`.
# mode "db"/"telemetry": distinct rows per (idx, j) -> total == N*M expected.
# mode "anchor": the SAME phrase every time -> frequency must sum to N*M (the
#                strongest lost-update check: concurrent read-modify-write counters).
_WORKER = r'''
import sys
mode, learn, target, idx, n = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5])
sys.path.insert(0, learn)
ok = 0
if mode == "db":
    import memory_writer as MW
    for j in range(n):
        rec = {"project_name": f"w{idx}_r{j}", "product_niche": "Gaming (MOBA)",
               "hook_successful": "h", "editing_specs": "e", "retention_score": 80,
               "lesson_learned": "l",
               "created_at": f"2026-06-16T{idx:02d}:00:{j:02d}.000Z"}
        good, _ = MW.safe_append(rec, target)
        ok += 1 if good else 0
elif mode == "telemetry":
    import telemetry as TEL
    for j in range(n):
        row = {"loop_run_id": f"k::w{idx}_r{j}", "project_name": f"w{idx}",
               "platform": "tiktok",
               "collected_at": f"2026-06-19T{idx:02d}:00:{j:02d}Z",
               "avg_watch_pct": 50}
        good, _ = TEL.append_telemetry(row, path=target)
        ok += 1 if good else 0
elif mode == "anchor":
    import anchor_library as AL
    for j in range(n):
        good, _, _ = AL.record_project_anchors(
            "Gaming (MOBA)", [{"label": "Pentakill", "kind": "callout"}],
            80, True, path=target)
        ok += 1 if good else 0
print(ok)
'''


def _spawn_writers(mode: str, target: Path, worker_py: Path) -> list[int]:
    """Launch N_WORKERS processes at once; return each worker's success count."""
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    procs = []
    for idx in range(N_WORKERS):
        procs.append(subprocess.Popen(
            [sys.executable, str(worker_py), mode, str(_PKG), str(target),
             str(idx), str(N_APPENDS)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env))
    counts = []
    for p in procs:
        out, err = p.communicate(timeout=120)
        if p.returncode != 0:
            print(f"        ! worker crashed (rc={p.returncode}): {err.strip()[:200]}")
            counts.append(-1)
        else:
            counts.append(int((out or "0").strip() or 0))
    return counts


def _tmp_debris(d: Path) -> list[str]:
    """Any leftover atomic-write temp files == a collision/abort bug."""
    return [p.name for p in d.iterdir() if p.name.endswith(".tmp")]


def test_lock_primitive():
    print("\n[c1] _filelock — exclusive: a 2nd acquire of the same lock times out")
    with tempfile.TemporaryDirectory() as d:
        target = Path(d) / "x.json"
        target.write_text("[]", encoding="utf-8")
        with FL.file_lock(target, timeout=2):
            timed_out = False
            try:
                with FL.file_lock(target, timeout=0.4):   # held elsewhere -> must block
                    pass
            except FL.LockTimeout:
                timed_out = True
            check("nested acquire raises LockTimeout (mutual exclusion holds)", timed_out)
        # released after the with-block -> now acquirable again
        reacquired = False
        with FL.file_lock(target, timeout=2):
            reacquired = True
        check("lock re-acquirable after release", reacquired)


def test_db_concurrent_no_lost_update():
    print(f"\n[c2] database.json — {N_WORKERS} writers x {N_APPENDS} appends, no lost update")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        db = d / "database.json"
        db.write_text("[]", encoding="utf-8")
        worker = d / "worker.py"
        worker.write_text(_WORKER, encoding="utf-8")

        counts = _spawn_writers("db", db, worker)
        expected = N_WORKERS * N_APPENDS
        check("all workers exited cleanly", all(c >= 0 for c in counts))
        check(f"every write reported success ({sum(counts)}/{expected})",
              sum(counts) == expected)

        arr = json.loads(db.read_text(encoding="utf-8"))
        check(f"LOST-UPDATE GUARD: db has all {expected} records (none dropped)",
              len(arr) == expected)
        names = {r["project_name"] for r in arr}
        check("every distinct record is present", len(names) == expected)
        check("TEMP-COLLISION GUARD: no leftover *.tmp files", _tmp_debris(d) == [])

        # the integrity marker must still validate the final DB (marker stayed in
        # lock-step with the file across all concurrent writers)
        sys.path.insert(0, str(_PKG))
        import memory_writer as MW
        okv, _ = MW.verify_db_integrity(db)
        check("integrity marker valid after concurrent writes", okv)


def test_telemetry_concurrent_no_lost_update():
    print(f"\n[c3] telemetry.json — {N_WORKERS} writers x {N_APPENDS} rows, no lost update")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        tele = d / "telemetry.json"
        tele.write_text("[]", encoding="utf-8")
        worker = d / "worker.py"
        worker.write_text(_WORKER, encoding="utf-8")

        counts = _spawn_writers("telemetry", tele, worker)
        expected = N_WORKERS * N_APPENDS
        check("all workers exited cleanly", all(c >= 0 for c in counts))
        rows = json.loads(tele.read_text(encoding="utf-8"))
        check(f"LOST-UPDATE GUARD: telemetry has all {expected} rows", len(rows) == expected)
        check("TEMP-COLLISION GUARD: no leftover *.tmp files", _tmp_debris(d) == [])


def test_anchor_concurrent_counter_no_lost_increment():
    print(f"\n[c4] anchor_library — {N_WORKERS} writers increment ONE counter, none lost")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        lib = d / "highlight_anchor_library.json"
        lib.write_text("{}", encoding="utf-8")
        worker = d / "worker.py"
        worker.write_text(_WORKER, encoding="utf-8")

        counts = _spawn_writers("anchor", lib, worker)
        expected = N_WORKERS * N_APPENDS
        check("all workers exited cleanly", all(c >= 0 for c in counts))

        data = json.loads(lib.read_text(encoding="utf-8"))
        anchors = data.get("Gaming (MOBA)", {}).get("anchors", [])
        penta = next((a for a in anchors if a["phrase"] == "Pentakill"), None)
        check("the shared anchor exists exactly once (no duplicate rows)",
              sum(1 for a in anchors if a["phrase"] == "Pentakill") == 1)
        check(f"LOST-INCREMENT GUARD: frequency summed to {expected} "
              f"(got {penta['frequency'] if penta else 'n/a'})",
              penta is not None and penta["frequency"] == expected)
        check("use_count also summed correctly",
              penta is not None and penta["use_count"] == expected)
        check("TEMP-COLLISION GUARD: no leftover *.tmp files", _tmp_debris(d) == [])


def main():
    os.environ.setdefault("PYTHONUTF8", "1")
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    print("=" * 64)
    print(" SUPER CREATOR OS — MEMORY CONCURRENCY REGRESSION (P0-4)")
    print("=" * 64)
    test_lock_primitive()
    test_db_concurrent_no_lost_update()
    test_telemetry_concurrent_no_lost_update()
    test_anchor_concurrent_counter_no_lost_increment()
    print("\n" + "=" * 64)
    print(f" RESULT: {_PASS} passed, {_FAIL} failed")
    print("=" * 64)
    return 1 if _FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
