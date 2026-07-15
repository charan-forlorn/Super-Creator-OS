# Memory Access Policy

> **Status:** ACTIVE (Phase 2.9.7). Defines, per agent/role, how the **Memory**
> system-of-record (`memory/`) may be read and written. Anchored to DD-002 (single safe
> write path), DD-004 (immutable v1 contract), DD-003 (observed-only telemetry), and the
> schemas EV-013/EV-014. **Policy only — changes no data, writes no code.**

---

## 1. Non-negotiable invariants (apply to all agents)

1. **All writes go through the single safe write path** (`safe_append`, CAP-014, DD-002).
   No agent may `open(...,'w')` or otherwise mutate `memory/database.json` directly.
2. **v1 contract is immutable** (DD-004, EV-013); only additive v2/v3 optional fields
   (EV-014, DD-001).
3. **Telemetry is observed-only** (DD-003, EV-040); predicted values must never be written
   as telemetry.
4. **Append-only**; existing records are never edited or deleted (EV-017).
5. Reads must use **UTF-8** (EV-015: default cp1252 fails on Thai content).

> Note: in the current checkout the write path is **`.pyc`-only (L2, EV-033)** — this policy
> governs intended access for when it is restored (DD-009); until then, agents must treat
> memory as **read-only** and flag any write attempt.

## 1A. Canonical Memory Versus Practice Runtime Journal

The canonical memory store and the practice runtime journal are separate state
domains.

- `memory/database.json` is the reviewed canonical memory system of record. It
  is a JSON array of project learning records and is owned by
  `integrations/learning/memory_writer.py::safe_append`.
- `memory/runtime/practice-render.jsonl` is mutable local runtime state for the
  daily practice-render loop. It records `practice_render` attempts from the
  `practice-loop` engine and is owned by
  `integrations/learning/runtime_journal.py::append_runtime_record`.
- Runtime integrity is guarded by
  `memory/runtime/.practice-render.jsonl.integrity.json`; the lock file is
  `memory/runtime/.practice-render.jsonl.lock`.
- `integrations/learning/memory_store.py` preserves canonical-only reads by
  default. Runtime-only or combined reads are explicit modes, and writes are
  delegated to the owning layer (`safe_append` for canonical records,
  `append_runtime_record` for runtime records).

The practice runtime journal exists so local practice renders can retain
operational learning without promoting every practice attempt into reviewed
canonical memory. A legitimate production runtime journal may already exist.
Its existence is not a defect; integrity, provenance, and isolation are the
checks that matter.

Tests that exercise practice learning must use injected temporary canonical and
runtime paths. They must not depend on whether the real repository runtime
journal exists, and they must not delete or truncate runtime files merely to
satisfy an absence assumption. During isolated tests:

- the injected runtime path receives practice records;
- the temporary canonical database remains byte-identical;
- an absent production-equivalent default runtime path remains absent;
- pre-existing production-equivalent default runtime state remains
  byte-identical;
- no fallback write occurs beside the default runtime sentinel.

## 2. Access matrix by role

| Role / agent | Read | Write | Memory scope | Notes |
|---|---|---|---|---|
| **Orchestrator** (CAP-023) | ✅ `database.json` (STEP 1) | ✅ via `safe_append` (STEP 15) | full record | the only writer of project records (EV-010) |
| **Practice render loop** | explicit injected runtime/canonical paths | runtime journal via `append_runtime_record` | practice attempts | does not write canonical memory during isolated practice tests |
| **Recommendation** (CAP-015) | ✅ `database.json` | ❌ | read nearest-niche | produces seed, never writes |
| **Telemetry capture** (CAP-016) | ✅ `telemetry.json` | ✅ via `append_telemetry` | observed rows only | rejects predicted (DD-003) |
| **Learning evaluator** (CAP-017) | ✅ db + telemetry | ❌ | calibration read | writes nothing to memory |
| **Adapter / render_to_memory** (CAP-014) | ✅ db | ✅ via `safe_append` | one new record | must stamp provenance (EV-026) |
| **Skills** (storytelling/editor/QA/etc.) | ⚠️ via orchestrator only | ❌ | none direct | never touch memory directly |
| **MCP / video engine** (CAP-019/020) | ❌ | ❌ | none | media only, not memory |
| **External / unknown agents** | ❌ | ❌ | none | no memory access without explicit grant |

## 3. Persistence rules

- One record per project, appended at Archive (STEP 15, EV-010).
- Backups are written to `_db_backups/` per write (EV-017); growth must be bounded
  (DD-013, EV-044) — retention is required before scale.
- Telemetry persists separately in `memory/telemetry.json` (absent today, EV-016).

## 4. Conflict rules

- **Duplicate guard:** `(project_name, created_at)` for records; `(loop_run_id, platform,
  collected_at)` for telemetry (EV-017) — a conflicting write is rejected, not merged.
- **Integrity guard:** a write onto a DB whose sha256 ≠ the tamper marker is **refused**
  (EV-017); the out-of-band edit must be reconciled first.
- **Concurrent writers:** the write-token guard ensures only `safe_append` drives the
  low-level writer (EV-017); agents must serialize through it.

## 5. Validation rules (every write)

Before a write is accepted: schema-validate the new record AND the existing DB
(`validators`, EV-008); enforce append-only post-condition; atomic `os.replace`; refresh
the tamper marker (all EV-017). A write failing any check returns failure — **never a
partial write** (DD-002).

## 6. Agent checklist (memory interaction)

```
- Am I allowed to write this scope?           (§2 matrix)  → if no, stop
- Is the write path present in HEAD?           (EV-033)     → if pyc-only, treat read-only + flag
- Am I adding only additive fields?            (DD-001/004) → if narrowing v1, reject
- Is this telemetry observed (not predicted)?  (DD-003)     → if predicted, reject
- Route through safe_append / append_telemetry (DD-002)     → never direct write
```
