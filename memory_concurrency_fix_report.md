# Memory Concurrency Hotfix — Implementation Report (P0-4, Option A)

**Source of truth:** `memory_concurrency_audit.md` (QA Reviewer findings).
**Scope delivered:** the approved **Option A** minimal-change hotfix — cross-platform
file locking + temp-collision elimination across the three JSON memory stores, plus a
new multi-process regression suite.
**Date:** 2026-06-23 · **Branch:** `master` @ `db2bf4f` (working tree).
**Test result:** **full suite green — 58/58 in `run_suite.py`** (incl. delegated DQ 47,
e2e 17, concurrency 16) **+ evaluator 8 + telemetry_capture 18 standalone. 0 failures.**

---

## 1. What was implemented (maps 1:1 to the requirements)

| # | Requirement | Delivered |
|---|---|---|
| 1 | Cross-platform lock, Windows + Linux, **stdlib only** | New `integrations/learning/_filelock.py`: `msvcrt.locking` (Windows) / `fcntl.flock` (POSIX), no third-party dep — preserves the stdlib-only learning spine. |
| 2 | Lock covers read → validate → modify → write → **marker** | `safe_append` now wraps the *entire* `verify_db_integrity → read → validate → backup → atomic write → `_write_marker`` section in one `file_lock`. Marker is refreshed **inside** the lock, closing the os.replace/marker gap (audit 3.2). |
| 3 | Eliminate shared temp-file collisions | All three atomic writers now use a **unique** temp name `"<file>.<pid>.<uuid8>.tmp"` instead of the fixed `"<file>.tmp"` (audit 3.3). |
| 4 | Protect `database.json`, `anchor_library`, `telemetry` | Lock + unique-temp applied to `memory_writer.safe_append`, `anchor_library.record_project_anchors`, `telemetry.append_telemetry`. |
| 5 | Preserve schema, APIs, tests | No on-disk schema change. All public signatures + `(ok, info[, list])` return shapes unchanged. Lock-timeout is caught internally and surfaced as a normal `ok=False` return — **no new exception leaks to callers**. All pre-existing tests still pass unmodified. |
| 6 | New regression tests: concurrent writers, lost-update, temp-collision | New `tests/test_concurrency.py` — real multi-process writers against each store. |

**Hardening discovered during testing (kept):** a bounded retry around `os.replace`
(`atomic_replace`) to absorb **transient Windows `ERROR_ACCESS_DENIED`** during rapid
successive replaces (AV/indexer/handle-release races). This is a real Windows
atomic-write hazard the concurrency test surfaced; without it the telemetry path failed
intermittently (~1 in 3 runs) **even though no record was ever lost** — i.e. it was an OS
flake, not a logic bug. POSIX never hits the retry path.

---

## 2. Files changed

### New files
| File | Purpose |
|---|---|
| `integrations/learning/_filelock.py` | Stdlib cross-platform advisory `file_lock(target, timeout)` context manager + `atomic_replace()` (Windows-retry) + `lock_path_for()` + `LockTimeout`. ~120 LOC. |
| `integrations/learning/tests/test_concurrency.py` | Multi-process regression suite (4 test groups, 16 checks). |
| `memory_concurrency_fix_report.md` | This report. |

### Modified files (diffstat: 4 files, +122 / −66)
| File | Change |
|---|---|
| `integrations/learning/memory_writer.py` | Import `_filelock`; split `safe_append` → thin lock wrapper + `_safe_append_locked` (whole critical section under the lock; `LockTimeout`→`ok=False`); unique temp name; `atomic_replace`. |
| `integrations/learning/telemetry.py` | Import `_filelock` + `uuid`; `append_telemetry` read→dedup→backup→write now inside `file_lock`; unique temp name; `atomic_replace`. |
| `integrations/learning/anchor_library.py` | Import `_filelock` + `uuid`; `record_project_anchors` load→mutate→backup→write inside `file_lock`; unique temp name; `atomic_replace`. |
| `integrations/learning/tests/run_suite.py` | Added `test_concurrency_subprocess()` step `[9]` so the concurrency suite runs as part of the full gate. |

**Not touched (by design):** on-disk schema, `validators.py`, the `_WRITE_TOKEN`
integrity-marker design, `render_to_memory.py` (already routes through `safe_append`),
`event_bus.py` (append-mode JSONL, out of P0-4 scope), `archive_manager.py` (write-once,
per-dir, not an RMW store).

---

## 3. Tests added

`tests/test_concurrency.py` — 16 checks, real OS processes (threads would let the GIL
hide the race):

| Group | What it proves | Key assertion |
|---|---|---|
| `[c1]` lock primitive | Mutual exclusion actually excludes | A 2nd acquire of a held lock raises `LockTimeout`; re-acquirable after release. |
| `[c2]` database.json | **Concurrent writers + lost-update + temp-collision** | 6 procs × 8 distinct appends → **all 48 records present** (none dropped); no leftover `*.tmp`; integrity marker still valid. |
| `[c3]` telemetry.json | Concurrent writers, no lost row | 6 × 8 distinct rows → all 48 present; no `*.tmp` debris. |
| `[c4]` anchor_library | **Lost-increment** (concurrent counter RMW) | 6 × 8 increments of the **same** anchor → `frequency == 48` and `use_count == 48` (the strongest lost-update check); single row, no debris. |

Stability: concurrency suite run **5× consecutively → 16/16 each time** after the
`atomic_replace` hardening (pre-hardening it failed ~1/3 on Windows telemetry).

**Existing tests:** unchanged and still green — `run_suite` `[6b]` `safe_append`, `[6c]`
write-guard/tamper-evidence, `[4]` telemetry append/dedup, e2e loop closure (exercises the
real `render_to_memory` CLI → locked `safe_append`), DQ suite, evaluator, telemetry_capture.

How to run:
```bash
python integrations/learning/tests/run_suite.py            # full gate (incl. concurrency)
python integrations/learning/tests/test_concurrency.py     # just the P0-4 regression
```

---

## 4. Before / after risk assessment

| Audit scenario | Before | After |
|---|---|---|
| **3.1 Silent lost update** (database.json) | **HIGH** — two writers read N, last replace wins, record dropped; marker re-blessed so loss is invisible. | **Closed** — critical section serialized by exclusive lock; `[c2]` proves all 48 survive. |
| **3.2 Spurious integrity trip / marker gap** | MEDIUM — reader in the os.replace→marker window sees a false "tamper". | **Closed** — marker refreshed inside the lock; no other lock-holder can observe the gap. |
| **3.3 Shared `*.tmp` collision** | **HIGH** — fixed temp name; concurrent writers clobber bytes / crash on Windows. | **Closed** — per-write `<pid>.<uuid>` temp names; `[c2/c3/c4]` assert zero `*.tmp` debris. |
| **3.5 Anchor/telemetry lost update (no marker)** | **HIGH**, undetectable | **Closed** — both now locked; `[c3]`/`[c4]` prove no lost row / no lost increment. |
| Windows `os.replace` transient AV/handle flake | latent (masked by single-writer usage) | **Mitigated** — bounded `atomic_replace` retry; 5× stable. |

**Residual concurrency posture:** the three stores are now **individually
serializable** under arbitrary multi-process load. The lost-update blocker named in
P0-4 is eliminated, and the blast radius the audit flagged beyond the original ticket
(anchor + telemetry + temp race) is covered in the same change.

**API/compat risk:** low. No signature or return-shape change; lock contention degrades
to the existing `ok=False` path; lock files are auto-created sidecars released on handle
close (incl. process death), so a crash leaves no permanent stale lock.

---

## 5. Remaining limitations (explicitly out of Option A scope)

1. **Cross-file (job-level) atomicity — NOT addressed (audit 3.4).**
   `learning_manager.process_project` still writes `database.json`, then
   `highlight_anchor_library.json`, then archives as **three separately-locked**
   operations. A crash or lost race *between* them can still leave the DB updated but the
   anchor library not (stores drift). Each file is internally consistent; the *set* is not
   transactional. → **Option B item 2** (job-level lock or declared eventual consistency).

2. **Advisory, not mandatory.** The lock only excludes writers that call it. All in-repo
   writers now do, but a future writer that bypasses `safe_append`/`append_telemetry`/
   `record_project_anchors` and writes the file directly would not be excluded. (The
   `_WRITE_TOKEN` guard still blocks direct `database.json` writes; anchor/telemetry have
   no such guard.) → consider extending the token guard, or **Option B item 1** (single
   `MemoryStore` all writers must route through).

3. **Marker not yet crash-atomic with the data write (R-6 unchanged).** The lock closes
   the *concurrency* gap, but a hard crash *between* `atomic_replace(db)` and
   `_write_marker` still leaves a stale marker → next read fails closed with no runbook.
   → **Option B item 5** (fold sha+count into the same atomic step) + recovery runbook.

4. **Lock-wait is bounded, then rejects.** On >10s contention, the write returns
   `ok=False "lock busy"` rather than queueing indefinitely. Correct for a CLI, but a
   high-throughput multi-writer deployment would want a tunable/longer timeout or a queue.

5. **Three near-duplicate `_atomic_write` implementations remain.** Option A deliberately
   patched them in place (minimal blast radius) rather than unifying them. The lock-site
   logic can still drift across the three. → **Option B item 1** consolidation.

6. **Not a substitute for a real multi-writer DB.** If the system ever needs true
   high-concurrency ACID, SQLite-WAL (Option B-7) remains the larger, separately-approved
   architectural decision — intentionally **not** bundled into this P0 hotfix, since it
   breaks the "one JSON file, stdlib-only" invariant.

---

## 6. Bottom line

Option A is implemented, tested, and green. The **named P0-4 blocker (silent
lost-update on `database.json`) is closed**, along with the two under-counted siblings
(anchor/telemetry stores and the shared-temp race) and a Windows replace flake found in
testing. The change is **additive, stdlib-only, schema-stable, API-stable**, and proven
by a **real multi-process** regression suite wired into the standard gate. The remaining
items above are the documented, lower-severity follow-ups for Option B — none of them
re-open the lost-update race this hotfix was approved to eliminate.

---
*Implementation + tests + report delivered. Full suite re-run after every change; final
state 58/58 (run_suite) with all delegated and standalone suites passing.*
