# Memory Subsystem — Concurrency Audit (P0-4)

**Scope:** Eliminate the highest-risk production blocker first — `P0-4: Memory has no
locking and may suffer lost-update races under concurrent access` (from
`production_readiness_audit.md`).
**Method:** QA Reviewer skill discipline (`skills/qa-reviewer/SKILL.md`) — read-only,
evidence-based. **No code was modified. No fixes were implemented.**
**Date:** 2026-06-23 · **Branch:** `master` @ `db2bf4f`
**Reviewer hats:** Staff QA · Concurrency/Systems · DevOps (cross-platform).

> **Verdict:** P0-4 is **real and confirmed**. The memory layer guarantees *no torn
> files* (atomic `os.replace`) but provides **no mutual exclusion**. Under two or more
> concurrent writers the read→modify→write window is unprotected, so a committed record
> can be **silently overwritten (lost update)**. The blast radius is **larger than the
> original audit stated** — the same defect exists in **three** independent JSON stores
> (`database.json`, `highlight_anchor_library.json`, `telemetry.json`), and a **shared
> fixed `*.tmp` filename** adds a second, independent corruption race. Likelihood is
> **low today** (single-user, sequential CLI) but **certain** the moment a second
> process/user/scheduler writes — which is exactly the public-deployment bar.

---

## 1. Every code path that writes to memory

Traced from `grep` of `safe_append | atomic_write | _write_marker | database.json` plus
direct read of each writer. "Guarded" = goes through the `_WRITE_TOKEN` + integrity
marker; "RMW" = read-modify-write (the lost-update-prone shape).

| # | Writer (entry point) | Target file | Shape | Guard | Lock |
|---|---|---|---|---|---|
| 1 | `memory_writer.safe_append()` → `_atomic_write_json()` ([memory_writer.py:90](integrations/learning/memory_writer.py#L90),[132](integrations/learning/memory_writer.py#L132)) | `memory/database.json` | **RMW** (read→validate→append→replace) | ✅ token + sha256 marker | ❌ **none** |
| 2 | `anchor_library.record_project_anchors()` → `_atomic_write()` ([anchor_library.py:77](integrations/learning/anchor_library.py#L77),[118](integrations/learning/anchor_library.py#L118)) | `memory/highlight_anchor_library.json` | **RMW** (read→mutate counters→replace) | ❌ none | ❌ **none** |
| 3 | `telemetry.append_telemetry()` → `_atomic_write()` ([telemetry.py:65](integrations/learning/telemetry.py#L65),[94](integrations/learning/telemetry.py#L94)) | `memory/telemetry.json` | **RMW** (read→append→replace) | ❌ none | ❌ **none** |
| 4 | `event_bus.EventBus.emit()` ([event_bus.py:45](integrations/learning/event_bus.py#L45)) | `integrations/learning/events.jsonl` | append (`open("a")`) | n/a | ❌ none (OS append) |
| 5 | `archive_manager.archive_project()` ([archive_manager.py:34](integrations/learning/archive_manager.py#L34)) | `archive/<pid>/manifest.json` | write-once (per-dir, ts-versioned) | n/a | ❌ none |
| 6 | `render_to_memory.atomic_write_json()` ([render_to_memory.py:295](integrations/adapter/render_to_memory.py#L295)) | — | **dead code** (defined, unused; `main()` routes through `safe_append` at [:368](integrations/adapter/render_to_memory.py#L368)) | ❌ no token | ❌ none |

**Orchestration callers** (who invokes the above, often in one logical "job"):
- `learning_manager.process_project()` calls **#1 → #5 → #2 → #4** in sequence within a
  single process ([learning_manager.py:114–134](integrations/learning/learning_manager.py#L114)).
  One job therefore mutates **three separate files non-atomically** (no cross-file
  transaction).
- `render_to_memory.main()` (legacy CLI) calls **#1** only.
- `telemetry.py main()` calls **#3** standalone (post-publish, hours/days later — a
  naturally *separate* process from the render job).
- Orchestrator `STEP 15` doctrine ([orchestrator/SKILL.md:29–40](skills/orchestrator/SKILL.md#L29))
  mandates the single safe path but **assumes, never enforces, one writer at a time.**

**Confirmed absence of any locking primitive** across the whole repo:
`grep -E "fcntl|msvcrt|flock|filelock|threading.Lock|multiprocessing"` → **0 hits** in
source (only match is the audit doc itself). `filelock`/`portalocker` are **not in
`requirements.txt`** and **not installed in `.venv`**.

---

## 2. Can concurrent writes actually occur?

**In-process:** No. There are no threads, no `multiprocessing`, no async. `EventBus`
dispatch is synchronous and single-threaded. So *within one Python process* writes are
serialized by the GIL + sequential control flow.

**Across processes:** **Yes — and this is the real exposure.** Every writer is a
separate `python …` invocation. Nothing prevents two from overlapping:

- **Batch / automation:** the SCOS automation directives (`/autopilot`, `/nextstep`) and
  any `automation_blueprint.yaml`-style driver can fan out multiple render jobs.
- **MCP + CLI overlap:** the MCP server (`scos_video_mcp.py`) runs as a long-lived
  process while a human runs `learning_manager.py` from a shell — different PIDs, same
  `database.json`.
- **Telemetry vs render:** `telemetry.py` (writer #3) is *designed* to run later/out of
  band; if a 72h telemetry collection coincides with a new render's `safe_append`, two
  processes touch `memory/` at once.
- **Public/multi-user deploy (the asked bar):** any web/worker/queue topology = N
  concurrent writers by definition.

The original audit's framing ("Single-writer design is correct *today* but undeclared as
a hard constraint") is accurate. **Today the invariant holds by luck of usage, not by
construction.**

---

## 3. Exact race-condition scenarios

### Architecture diagram — the unprotected critical section

```
                    memory/database.json  (single JSON array, system-of-record)
                    .database.json.integrity.json  (sha256 + count marker)
                                  ▲
                                  │  read → validate → append → os.replace → write marker
                                  │  (NObody holds a lock across these steps)
              ┌───────────────────┴───────────────────┐
              │                                       │
   Process A (render job)                  Process B (2nd render / telemetry / MCP)
   safe_append(rec_A)                      safe_append(rec_B)
   ─────────────────────                   ─────────────────────
   t1 verify_integrity ✔ (hash=M0)
                                           t2 verify_integrity ✔ (hash=M0)   ← both pass
   t3 db = read() → [r1..rN]
                                           t4 db = read() → [r1..rN]         ← both see N
   t5 write [r1..rN, rec_A]  (N+1)
   t6 write marker = sha(N+1 incl A)
                                           t7 write [r1..rN, rec_B] (N+1)    ← rec_A GONE
                                           t8 write marker = sha(N+1 incl B) ← marker now
                                                                               MATCHES B's file
   RESULT: rec_A is permanently lost. Integrity check on the next read PASSES,
           because B re-stamped the marker over its own (wrong) file. Silent.
```

### Scenario 3.1 — Classic lost update (primary, HIGH)
Sequence above. Both writers pass the *start-of-call* integrity check (file still equals
marker `M0`), both read `N` records, both compute `N+1`, last `os.replace` wins. The loser's
record vanishes. Because writer #1 **re-writes the marker last**, the sha256 tamper guard
**re-blesses the corrupted result** — so the very mechanism meant to detect out-of-band
writes *masks* the loss instead of catching it. **The atomic write does not help: each
individual write is atomic, but the pair of writes is not serializable.**

### Scenario 3.2 — Spurious integrity trip / fail-closed read (MEDIUM)
The marker is updated **after** `os.replace`, not atomically with it
([memory_writer.py:132–134](integrations/learning/memory_writer.py#L132)). Window:

```
A: os.replace(database.json)  ← file is now N+1
   << reader R calls verify_db_integrity() here >>   file=sha(N+1), marker=sha(N) → MISMATCH
A: _write_marker()            ← file and marker reconciled
```
A concurrent **reader** (or a second writer's `verify_db_integrity`) landing in that
millisecond sees a hash mismatch and **fails closed** with *"written outside
safe_append"* — a false tamper alarm / transient outage with no runbook (this is R-6's
concurrency twin).

### Scenario 3.3 — Shared temp-file collision (HIGH, independent of 3.1)
All three RMW writers build the temp path as a **fixed name**:
`path.with_suffix(path.suffix + ".tmp")` → always `database.json.tmp` /
`telemetry.json.tmp` / `highlight_anchor_library.json.tmp`
([memory_writer.py:85](integrations/learning/memory_writer.py#L85),
[telemetry.py:52](integrations/learning/telemetry.py#L52),
[anchor_library.py:50](integrations/learning/anchor_library.py#L50)). Two concurrent
writers of the same store write to the **same** `*.tmp`:

```
A: tmp.write_text(  bytes_A  )            ← tmp = [..rec_A]
B: tmp.write_text(  bytes_B  )            ← tmp clobbered = [..rec_B]
A: os.replace(tmp → db)                   ← db = B's bytes (A replaces with B's content!)
B: os.replace(tmp → db)                   ← Windows: may raise (file in use) → unhandled
```
On POSIX this yields *content/identity mismatch* (A's replace ships B's bytes); on Windows
`os.replace` can raise `PermissionError`/`FileExistsError` mid-flight (no retry/handling),
crashing the job and potentially leaving a `.tmp` turd. This is a **second race**, not
fixed merely by adding a lock around the read step — it needs a **unique** temp name too.

### Scenario 3.4 — Cross-file partial update (MEDIUM)
`learning_manager.process_project` writes `database.json` (✔) then
`highlight_anchor_library.json` then archives. A crash or a concurrent loser between #1
and #2 leaves **DB updated but anchor library not** (or vice-versa) — the stores drift
out of sync. There is no journal/rollback spanning the three files.

### Scenario 3.5 — Anchor/telemetry silent loss with *zero* evidence (HIGH for those files)
Writers #2 and #3 have **no token guard and no integrity marker at all**. The lost-update
of 3.1 applies to them with **no tamper-evidence whatsoever** — a dropped anchor count or
telemetry row is undetectable after the fact. The original P0-4 named only
`database.json`; the defect is **broader**.

---

## 4. Potential lost-update sequences (summary table)

| Seq | Trigger | Files affected | Outcome | Detectable? |
|---|---|---|---|---|
| 3.1 | 2 writers, overlapping RMW | database.json | 1 record silently lost | ❌ marker re-blessed |
| 3.2 | writer + reader in marker gap | database.json | false "tamper" → fail-closed read | ⚠️ surfaces as outage |
| 3.3 | 2 writers, same `*.tmp` | any of the 3 stores | wrong-content replace / Windows crash | ⚠️ partial |
| 3.4 | crash/loser between DB & anchor write | DB ↔ anchor lib | stores drift / inconsistent | ❌ |
| 3.5 | 2 writers, overlapping RMW | anchor lib / telemetry | row/counter lost | ❌ no marker exists |

---

## 5. Is file locking sufficient?

**A lock is necessary and — placed correctly — sufficient for scenarios 3.1, 3.2, 3.4,
3.5. It is *not* sufficient by itself for 3.3.** Conditions:

1. **The lock must span the entire critical section** — acquire **before** the
   `read()` and release **after** the marker write. Locking only the `os.replace` (or
   only the write) leaves the read→write TOCTOU open and changes nothing. The read is the
   start of the critical section.
2. **Marker write must move inside the lock**, immediately after `os.replace`, so 3.2's
   gap is never observable to another lock holder, and readers must take a **shared/read
   path** consistent with the writer (or tolerate the gap).
3. **The temp filename must become unique** (PID + monotonic/uuid suffix) regardless of
   locking — 3.3 is a filename-aliasing bug, orthogonal to mutual exclusion. (A lock
   *would* serialize same-store writers enough to hide it, but uniqueness is the correct,
   defense-in-depth fix and protects against lock-bypass/stale-lock cases.)
4. **Lock granularity = per target file** (one lock for `database.json`, etc.). For 3.4
   (cross-file consistency) a coarser **job-level** lock, or accepting eventual
   consistency, is a design choice (see Option B).
5. **Advisory, not mandatory:** OS file locks here are advisory — they only work if
   **every** writer honors them. Since `safe_append` is already doctrinally the only
   write path, routing the lock through it (and the other two `_atomic_write`s) covers
   all in-repo writers.

**Locking does NOT replace** the existing atomic write or integrity marker — it composes
with them. Atomic write still prevents torn files; the marker still catches out-of-band
edits; the lock adds the missing *serializability*.

---

## 6. Cross-platform locking strategy (Windows / Linux)

The repo is Windows-centric today (`vu.py` UTF-8 shim, font assumptions) but CI/cloud is
Linux. The lock must work on both. Three viable mechanisms:

| Mechanism | Windows | Linux | Notes |
|---|---|---|---|
| **stdlib `msvcrt.locking` + `fcntl.flock`** (platform shim) | `msvcrt.locking(fd, LK_LOCK, ...)` | `fcntl.flock(fd, LOCK_EX)` | **No new dependency.** Preserves the "stdlib-only learning spine" invariant. ~30 lines, platform-branched. `flock` releases on process death (crash-safe); Windows mandatory byte-range lock also releases on handle close. |
| **`filelock` library** | ✅ | ✅ | Battle-tested, timeout + stale handling built in. **Adds a third-party dep** to a layer that is currently dependency-free — conflicts with the SCOS "additive, stdlib spine" invariant and R-3 (unpinned-dep concern). |
| **`portalocker`** | ✅ | ✅ | Same trade-off as `filelock`. |

**Recommended mechanism: stdlib platform shim** — lock an adjacent sidecar
`memory/.<name>.lock` (never the data file itself, so the lock handle is independent of
the atomic-replace dance). Use a **blocking acquire with a bounded timeout** (e.g. 10 s)
and a clear error on timeout. On Linux `flock` auto-releases if the holder dies; on
Windows close-on-exit covers the same — both avoid permanent stale locks for the common
crash case. Document a manual `.lock` removal in the runbook for the rare hung-handle case.

> Windows caveat: `os.replace` over a file that another process holds **open** can fail.
> The sidecar-lock design avoids this because the lock is on `.lock`, not on the data
> file, and only one writer is ever inside the critical section to call `os.replace`.

---

## 7. Severity assessment

| Axis | Rating | Basis |
|---|---|---|
| **Impact** | **HIGH** | Silent permanent data loss in the system-of-record. This is the *one* failure the entire "trust core" (validate + atomic + tamper-evidence + append-only) exists to prevent; the marker even *masks* it (3.1). |
| **Likelihood (today)** | **LOW** | Single-user, sequential CLI; no in-process concurrency. The window only opens with overlapping processes. |
| **Likelihood (asked bar: public/multi-user)** | **HIGH→CERTAIN** | Any 2nd writer (worker, scheduler, MCP+CLI, telemetry-vs-render) opens it deterministically. |
| **Detectability** | **POOR** | 3.1 re-blesses the marker; 3.5 has no marker at all. Loss is invisible post-hoc. |
| **Blast radius** | **WIDER than P0-4 stated** | 3 stores, not 1; plus an independent `*.tmp` race and cross-file drift. |
| **Reversibility** | **Partial** | `_db_backups/` timestamped copies exist, but recovery is manual, unbounded (R-5), and racy itself. |

**Overall: confirmed P0 for the public-deployment bar. Correctly *not* a P0 for the
single-user local tool** (matches the audit's dual-bar framing). The fix is small and
well-contained, with no schema or data-format change.

---

## 8. Recommended implementation

Both options keep the JSON-file system-of-record and the append-only/atomic/marker
guarantees intact (honoring the SCOS v4 charter: additive, don't destabilize, stdlib
spine). They differ in how far they generalize.

### Option A — Minimal-change fix (close the lost-update window)

A small, surgical change confined to the three RMW writers.

1. **Add a stdlib cross-platform lock helper** (new ~30-line `integrations/learning/_filelock.py`,
   `msvcrt`/`fcntl` shim, context-manager API).
2. **`safe_append`:** wrap the section from the `db = read()` through `_write_marker()` in
   `with file_lock(memory/.database.json.lock, timeout=10):`. Move `_write_marker`
   **inside** the lock (it already is sequentially; just ensure it's within the `with`).
3. **`anchor_library.record_project_anchors`** and **`telemetry.append_telemetry`:** same
   wrap around their read→mutate→`_atomic_write`.
4. **Unique temp name** in all three `_atomic_write*`: `…suffix + f".{os.getpid()}.tmp"`
   (or `uuid4().hex`) to kill scenario 3.3.
5. **One concurrency regression test:** spawn N processes each appending a distinct
   record; assert final count == N (no loss). This is the test that actually proves the
   fix and currently does not exist.

*Not addressed by A:* cross-file atomicity (3.4) and a unified writer abstraction — A
accepts per-file locks and leaves the 3-file job non-transactional (documented as a known
limitation).

### Option B — Production-grade architecture

Everything in A, plus generalization and operability:

1. **Single `MemoryStore` / `FileMutex` utility** that *all* JSON-store writers go
   through — one place owns lock + atomic-write + unique-tmp + marker, eliminating the
   three near-duplicate `_atomic_write` implementations (also pays down the audit's
   "de-dupe" theme).
2. **Job-level lock option** so `learning_manager.process_project` can serialize the
   DB+anchor+telemetry triple under one critical section (closes 3.4), or an explicit
   documented eventual-consistency contract if not.
3. **Lock timeout + stale-lock policy + structured error** surfaced through the logging
   that P0-3 will add (no silent hangs).
4. **Declared single-writer-per-store invariant** in `memory/schema.md` + a startup
   self-check, so the constraint is enforced, not assumed.
5. **Marker write made crash-consistent** with the replace (write marker to `.tmp`,
   `os.replace` both, or fold count+sha into the same atomic step) — closes R-6 + 3.2
   together.
6. **Concurrency test matrix** (multi-process, crash-injection between replace and
   marker, Windows + Linux in CI) + a documented recovery runbook.
7. *(Optional, larger)* evaluate **SQLite WAL** as the system-of-record for true
   multi-writer ACID — but this **breaks the "one JSON file, stdlib-only" invariant** and
   should be a separate, explicitly-approved decision, **not** bundled into the P0 fix.

### Comparison

| Dimension | Option A (minimal) | Option B (production-grade) |
|---|---|---|
| **Safety** | Closes 3.1, 3.2, 3.3, 3.5. Leaves 3.4 (cross-file) documented-but-open. | Closes all five, plus R-6; enforces the invariant. |
| **Complexity** | Low. ~3 wrap sites + 1 helper + unique tmp + 1 test. No new dep, no schema change. | Medium. New abstraction, refactor of 3 writers, CI matrix, runbook. Risk of touching working code. |
| **Maintenance burden** | Low, but three lock-sites can drift (same defect that produced 3 copies of `_atomic_write`). | Lower long-term: one writer to reason about; higher upfront. |
| **Deployment risk** | **Minimal blast radius** — additive, behind the existing safe path, easy to review/revert. Matches "smallest blast radius first." | Higher — broader diff over the trust core; needs the concurrency CI to land first to be trusted. |

### Final recommendation

**Ship Option A now as the P0-4 fix; schedule Option B's items 1–6 as the immediate
follow-up; treat B-7 (SQLite) as a separate, deferred architecture decision.**

Rationale, gated through the SCOS v4 charter (additive, don't destabilize, smallest blast
radius, stdlib spine) and the audit's own "NEXT ACTIONS" ordering ("File lock around
`safe_append` — small, well-bounded change"):

- A **fully closes the named blocker** (3.1) plus two findings the original audit
  under-counted (3.3 tmp race, 3.5 unguarded sibling stores) with a **minimal, reviewable,
  stdlib-only** diff and the **regression test that currently doesn't exist** — without
  adding a dependency or changing a single byte of the on-disk schema.
- The one gap A leaves (3.4 cross-file atomicity) is **lower severity** (drift, not silent
  primary-record loss) and is cleanly addressed by B-2 next.
- B-1 (single writer utility) and B-5 (marker/replace crash-consistency, which also
  retires R-6) are the **highest-value B items** and should follow immediately, but
  bundling the full refactor into the P0 raises deployment risk over the trust core for no
  additional protection against the actual blocker.
- B-7 (SQLite) conflicts with a standing invariant and must not ride in on a P0 hotfix.

**Concrete first move (Option A):** add the stdlib `file_lock` helper, wrap the critical
section in `safe_append` + the two sibling writers, switch to unique `*.tmp` names, and
land the multi-process "append N → expect N" regression test. Small, bounded, reversible —
and it converts the memory layer's single-writer assumption from *luck* into *enforcement*.

---
*Read-only audit — no source files were modified, no fixes implemented. Deliverable: this
file only. Conclusions are grounded in the cited repository lines.*
