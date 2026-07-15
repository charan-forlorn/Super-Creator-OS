# Cohort 4 Practice Runtime Isolation Documentation Certification

**Verdict:** PASS - documentation-only certification.
**Cohort status:** COHORT 4 DOCUMENTATION CERTIFIED.
**Scope:** document the certified Cohort 3 runtime-isolation behavior for the
practice-render loop. No source, test, configuration, runtime, or canonical
memory change is part of this cohort.

## Durable Contract

The practice-render loop has two state domains:

- Canonical memory: `memory/database.json`, a reviewed JSON array of project
  learning records. The approved writer is
  `integrations/learning/memory_writer.py::safe_append`.
- Runtime journal: `memory/runtime/practice-render.jsonl`, an append-only JSONL
  journal for local practice attempts from the `practice-loop` engine. The
  approved writer is
  `integrations/learning/runtime_journal.py::append_runtime_record`.

`integrations/learning/memory_store.py` keeps default reads canonical-only.
Runtime reads are explicit (`runtime` or `combined` mode), and combined reads
mark `source_layer`. Runtime writes delegate to the runtime journal writer;
canonical writes delegate to `safe_append`.

The production runtime journal may legitimately exist. Existence alone is not
a failure. The required checks are integrity, path isolation, provenance of the
writer, and byte-identical preservation during isolated tests or certification.

## Runtime-Path Injection and Default Isolation

Practice tests and certification procedures must inject temporary paths for
both canonical memory and the runtime journal. The injected runtime path is the
only place practice records should be written during the test. The temporary
canonical database must remain byte-identical.

The default runtime path is still part of the contract:

- if a production-equivalent default runtime path is absent, it remains absent;
- if a production-equivalent default runtime path already exists, its journal,
  integrity marker, and lock state remain byte-identical;
- a sentinel default runtime state must not receive a fallback write when an
  injected runtime path was provided;
- tests must not assume the real repository runtime journal is absent.

## Operator Safety

Operators must preserve legitimate runtime state. Do not delete, truncate,
migrate, append to, or regenerate `memory/runtime/practice-render.jsonl` merely
to make a test pass. Hash the canonical database, runtime journal, marker, and
lock before and after certification. Any unexpected hash drift is a blocking
condition and must be investigated before committing.

During this documentation cohort, verification is documentation-only plus the
approved local Python tests. It must not run render, scheduler, cleanup,
migration, dependency installation, network, or external-service workflows.

## Cohort 3 Certification Reference

Certified commit:
`a9de5506d316db97f0868e2a132747ebff0318bb`
(`test(practice): verify runtime isolation without assuming absence`).

Cohort 3 repaired a stale test assumption: the real production runtime journal
`memory/runtime/practice-render.jsonl` is not required to be absent. It may
exist as legitimate `EXPECTED_POST_COHORT3_RUNTIME_ACTIVITY`. Runtime integrity
and preservation are checked independently from runtime existence.

Certified Cohort 3 evidence:

- `scripts/tests/test_practice_render_loop.py`: 18 passed.
- Affected runtime/memory/cleanup/practice cluster: 46 passed.
- Canonical safe-append regression: 1 passed.
- Canonical database: SHA-256
  `996bd578b9ed4a4cf17ca3f7c1b573dd130ddcedd94137b18b742fbf90922a1d`,
  27 total records, 22 `practice-loop` records.
- Runtime journal: SHA-256
  `049462058c1e8263b52553c7f37d7291dd91e50014c588f2f601779677087358`,
  3155 bytes, 3 records.
- Runtime marker: SHA-256
  `9ff1d10567aec148a030c4d7915b660d544df83cc9dcf288da9e101d0c132d68`,
  232 bytes.
- Runtime lock: SHA-256
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`,
  0 bytes.

## Fresh Cohort 4 Evidence

Fresh preflight on July 15, 2026 observed:

- Branch: `main`.
- Starting HEAD:
  `a9de5506d316db97f0868e2a132747ebff0318bb`.
- Baseline subject:
  `test(practice): verify runtime isolation without assuming absence`.
- No staged changes.
- Protected pre-existing state: `memory/database.json`,
  `.pytest-tmp-cohort3-*` directories, and
  `apps/control-center/design-references/` plus `apps/control-center/public/`.
- Canonical database: SHA-256
  `996bd578b9ed4a4cf17ca3f7c1b573dd130ddcedd94137b18b742fbf90922a1d`,
  27 total records, 22 `practice-loop` records.
- Runtime journal: SHA-256
  `049462058c1e8263b52553c7f37d7291dd91e50014c588f2f601779677087358`,
  3155 bytes, 3 records.
- Runtime marker:
  `memory/runtime/.practice-render.jsonl.integrity.json`, SHA-256
  `9ff1d10567aec148a030c4d7915b660d544df83cc9dcf288da9e101d0c132d68`,
  232 bytes.
- Runtime lock:
  `memory/runtime/.practice-render.jsonl.lock`, SHA-256
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`,
  0 bytes.

The freshly rerun Cohort 4 test results are recorded in the closing operator
report for the Cohort 4 commit. The test-count lines above are Cohort 3
certification evidence unless explicitly labeled as fresh Cohort 4 evidence.

## Known Warning

`PytestConfigWarning: Unknown config option: cache_dir` is a non-blocking,
pre-existing pytest configuration warning observed in repository certification
history. Cohort 4 records it as a follow-up observation only. It does not fix
or modify pytest configuration.
