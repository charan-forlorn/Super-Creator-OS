# Cohort 5 Pytest Cache Warning Resolution Certification

**Verdict:** PASS - documentation and invocation repair.
**Cohort status:** COHORT 5 PYTEST WARNING REPAIR CERTIFIED.
**Scope:** diagnose `PytestConfigWarning: Unknown config option: cache_dir`,
preserve valid pytest configuration, and document the supported warning-free
invocation. No source, product-test, dependency, runtime, or canonical-memory
change is part of this cohort.

## Baseline

Fresh preflight on July 15, 2026 observed:

- Repository root: `C:/Workspace/super-creator-os`.
- Branch: `main`.
- Starting HEAD:
  `3a8397d1e847530ad8ffc1b19e5d173b74602422`.
- Starting subject:
  `docs(practice): document runtime isolation contract`.
- Relationship: `main...origin/main`, 51 ahead, 0 behind.
- Staged state: empty.
- Protected pre-existing state: modified `memory/database.json`; untracked
  `.pytest-tmp-cohort3-*` directories; untracked
  `apps/control-center/design-references/` and `apps/control-center/public/`.

Production state matched the certified baseline:

- `memory/database.json`: SHA-256
  `996bd578b9ed4a4cf17ca3f7c1b573dd130ddcedd94137b18b742fbf90922a1d`,
  27 total records, 22 `practice-loop` records.
- `memory/runtime/practice-render.jsonl`: SHA-256
  `049462058c1e8263b52553c7f37d7291dd91e50014c588f2f601779677087358`,
  3155 bytes, 3 records.
- `memory/runtime/.practice-render.jsonl.integrity.json`: SHA-256
  `9ff1d10567aec148a030c4d7915b660d544df83cc9dcf288da9e101d0c132d68`,
  232 bytes.
- `memory/runtime/.practice-render.jsonl.lock`: SHA-256
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`,
  0 bytes.
- Runtime integrity verifier:
  `verify_runtime_integrity("memory/runtime/practice-render.jsonl")` returned
  `(True, "ok")`.

## Configuration Inventory

- `pytest.ini:11` owns the active pytest cache setting:
  `cache_dir = scos/work/.pytest_cache`.
- `pytest.ini:12` owns active default deselection:
  `addopts = -m "not integration"`.
- `conftest.py` registers the `local_acceptance` marker and compatibility
  fixtures; it does not alter cacheprovider.
- Historical certification docs record prior warnings and some
  `-p no:cacheprovider` invocations. Those records were preserved as historical
  evidence.
- `docs/runbooks/SCOS-HVS-production-operations.md` is the active operator
  runbook for pytest commands.

## Root Cause

Classification: `INVOCATION_INDUCED`.

`cache_dir` is a valid pytest option when pytest's built-in
`_pytest.cacheprovider` plugin is enabled. Disabling that plugin with
`-p no:cacheprovider` removes the registration owner for `cache_dir`, while
pytest still reads `pytest.ini`. The result is:

```text
PytestConfigWarning: Unknown config option: cache_dir
```

The repository configuration was not defective. Removing `cache_dir` would
discard a valid cache redirection that Stage 0 introduced to avoid root
`.pytest_cache` problems.

## Reproduction Matrix

All diagnostic runs used `.venv\Scripts\python.exe`, pytest 9.1.1, and a unique
Windows system-temp root created from `$env:TEMP`.

| Experiment | Cacheprovider | Cache handling | Basetemp | Exit | Result | Warning result |
| --- | --- | --- | --- | --- | --- | --- |
| A: focused supported command | enabled | `-o cache_dir=<SYSTEM_TEMP>\cache-enabled` | `<SYSTEM_TEMP>\base-enabled` | 0 | 1 passed | 0 warnings; `PytestConfigWarning` promoted to error |
| B: disabled cacheprovider | disabled with `-p no:cacheprovider` | repository `pytest.ini` still contains `cache_dir` | `<SYSTEM_TEMP>\base-disabled` | 0 | 1 passed | 1 `PytestConfigWarning`: unknown `cache_dir` |
| C: supported practice suite | enabled | `-o cache_dir=<SYSTEM_TEMP>\cache-normal` | `<SYSTEM_TEMP>\base-normal` | 0 | 18 passed | 0 warnings; `PytestConfigWarning` promoted to error |

Registration evidence:

- `.venv\Scripts\python.exe -m pytest --help` lists
  `cache_dir (string): Cache directory path`.
- `.venv\Scripts\python.exe -m pytest --trace-config -q --collect-only
  scripts\tests\test_practice_render_loop.py` registers
  `_pytest.cacheprovider`.
- With `-p no:cacheprovider`, the dedicated `cache_dir` configuration option is
  absent from the configuration-options section.

## Repair Decision

Selected repair:

1. Preserve `pytest.ini`.
2. Do not edit historical certification evidence.
3. Update the active production operations runbook so supported pytest commands
   keep cacheprovider enabled, redirect `cache_dir` to a unique system-temp
   directory, redirect `--basetemp` to the same system-temp root, and promote
   `PytestConfigWarning` to an error.
4. Add this Cohort 5 certification record.

Rejected alternatives:

- Removing `cache_dir`: rejected because the option is valid when its owning
  plugin is enabled.
- Disabling cacheprovider: rejected because it causes the warning under this
  repository configuration.
- Editing historical Stage 8 or Cohort 4 records: rejected because they are
  evidence of prior runs, not active operator instructions.

Allow-list:

- `docs/runbooks/SCOS-HVS-production-operations.md`
- `docs/certification/Cohort-5-pytest-cache-warning-resolution.md`

## Supported Invocation

Use this pattern for certification and operator pytest runs:

```powershell
cd C:\Workspace\super-creator-os
$pytestRoot = Join-Path $env:TEMP ("scos-pytest-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $pytestRoot | Out-Null

.venv\Scripts\python.exe -m pytest <TEST_PATHS> -q `
  -o "cache_dir=$pytestRoot\cache" `
  --basetemp "$pytestRoot\base" `
  -W error::pytest.PytestConfigWarning
```

Do not add `-p no:cacheprovider` to this repository's supported pytest
verification commands.

## Verification Evidence

Fresh diagnostic verification before this document was created:

- Focused supported diagnostic:
  `.venv\Scripts\python.exe -m pytest
  scripts\tests\test_practice_render_loop.py::test_dry_run_writes_neither_canonical_nor_runtime
  -q -o "cache_dir=<SYSTEM_TEMP>\cache-enabled" --basetemp
  "<SYSTEM_TEMP>\base-enabled" -W error::pytest.PytestConfigWarning` -> exit 0,
  1 passed, 0 failed, 0 errors, 0 `PytestConfigWarning`.
- Disabled-cacheprovider diagnostic:
  `.venv\Scripts\python.exe -m pytest
  scripts\tests\test_practice_render_loop.py::test_dry_run_writes_neither_canonical_nor_runtime
  -q -p no:cacheprovider --basetemp "<SYSTEM_TEMP>\base-disabled"` -> exit 0,
  1 passed, 0 failed, 0 errors, 1 `PytestConfigWarning`.
- Supported practice suite:
  `.venv\Scripts\python.exe -m pytest scripts\tests\test_practice_render_loop.py
  -q -o "cache_dir=<SYSTEM_TEMP>\cache-normal" --basetemp
  "<SYSTEM_TEMP>\base-normal" -W error::pytest.PytestConfigWarning` -> exit 0,
  18 passed, 0 failed, 0 errors, 0 `PytestConfigWarning`.

Fresh post-repair certification verification:

- Focused Practice Loop suite:
  `.venv\Scripts\python.exe -m pytest scripts\tests\test_practice_render_loop.py
  -q -o "cache_dir=<SYSTEM_TEMP>\focused-cache" --basetemp
  "<SYSTEM_TEMP>\focused-base" -W error::pytest.PytestConfigWarning` -> exit 0,
  18 passed, 0 failed, 0 errors, 0 `PytestConfigWarning`.
- Affected runtime/memory/cleanup cluster:
  `.venv\Scripts\python.exe -m pytest
  integrations\learning\tests\test_runtime_journal.py
  integrations\learning\tests\test_memory_store.py
  scripts\tests\test_video_job_cleanup.py
  scripts\tests\test_practice_render_loop.py -q -o
  "cache_dir=<SYSTEM_TEMP>\cluster-cache" --basetemp
  "<SYSTEM_TEMP>\cluster-base" -W error::pytest.PytestConfigWarning` -> exit 0,
  46 passed, 0 failed, 0 errors, 0 `PytestConfigWarning`.
- Canonical safe-append regression:
  `.venv\Scripts\python.exe -m pytest
  integrations\learning\tests\run_suite.py::test_memory_writer_safe_append -q
  -o "cache_dir=<SYSTEM_TEMP>\canonical-cache" --basetemp
  "<SYSTEM_TEMP>\canonical-base" -W error::pytest.PytestConfigWarning` -> exit
  0, 1 passed, 0 failed, 0 errors, 0 `PytestConfigWarning`.
- Configuration sanity:
  `.venv\Scripts\python.exe -m pytest --help` showed
  `cache_dir (string): Cache directory path`.
- Pytest configuration guard:
  `.venv\Scripts\python.exe -m pytest
  scripts\tests\test_pytest_collection_config.py -q -o
  "cache_dir=<SYSTEM_TEMP>\config-cache" --basetemp
  "<SYSTEM_TEMP>\config-base" -W error::pytest.PytestConfigWarning` -> exit 0,
  2 passed, 0 failed, 0 errors, 0 `PytestConfigWarning`.

## Production Preservation

The diagnostic runs preserved:

- canonical SHA-256:
  `996bd578b9ed4a4cf17ca3f7c1b573dd130ddcedd94137b18b742fbf90922a1d`;
- runtime journal SHA-256:
  `049462058c1e8263b52553c7f37d7291dd91e50014c588f2f601779677087358`;
- runtime marker SHA-256:
  `9ff1d10567aec148a030c4d7915b660d544df83cc9dcf288da9e101d0c132d68`;
- runtime lock SHA-256:
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`;
- runtime integrity: `(True, "ok")`.

Production state changed: no.

## Safety Confirmation

No source edit, product-test edit, pytest configuration edit, dependency edit,
runtime append, canonical mutation, migration, deletion, cleanup, reset,
restore, stash, amend, push, scheduler, render, install, network, or external
service occurred during this repair.
