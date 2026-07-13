# SCOS-HVS Integration Stage 8L Project Initialization Materialization

## 1. Stage Objective

Stage 8L consumes a certified Stage 8K Production Kickoff Authorization, builds an immutable Production Initialization Contract, maps it through the certified Stage 2 SCOS-to-HVS mapper, and initializes exactly one HVS project through the certified HVS `initialize-project` CLI. The stage stops at `HVS_PROJECT_INITIALIZED_AND_VERIFIED`.

Stage 8L does not authorize assets, voice, placeholders, rendering, delivery, customer contact, invoicing, payment-provider access, or Stage 8M.

## 2. Baselines

- Starting SCOS baseline: `8ab47094014c78f634e1cd66e5a430d591078269`
- Actual compatible SCOS baseline before edits: `8ab47094014c78f634e1cd66e5a430d591078269`
- SCOS branch: `main`
- Starting HVS Stage 8L.0 baseline: `2d55b371656c45c18e24a997a69025abd21b675e`
- HVS branch: `main`
- HVS source policy: read-only; no HVS commit authorized.

## 3. Architecture Blocker Resolved By Stage 8L.0

HVS Stage 8L.0 supplied the previously missing safe mutation boundary:

- exact caller-supplied project ID
- versioned Stage 2-compatible payload intake
- expected payload-hash verification
- explicit `--approve-initialization`
- transactional minimum-project creation
- post-creation `inspect-project`
- identical replay idempotency
- changed-semantic conflict detection
- no voice, placeholders, assets, render, or MP4

## 4. Architecture Reused

- Stage 1 adapter reused: `HermesVideoStudioAdapter`
- Stage 2 mapper reused: `map_scos_to_hvs` and `payload_identity_hash`
- Stage 3 correlation logic reused: `correlation_id_for`
- Stage 4 asset boundary preserved: all asset/render flags remain false
- Stage 8K authorization reused and reverified
- HVS Stage 8L.0 `initialize-project` used
- HVS `inspect-project` used
- Backward-compatible extensions: adapter JSON command helpers and repo-local interpreter validation flag
- Duplicate mapper added: NO
- Stage 3 direct filesystem creator used: NO
- HVS legacy `create-project` used: NO

## 5. Contracts

Stage 8L adds:

- `ProductionInitializationInput`: explicit operator production title, language, resolution, fps, preset, and scenes.
- `ProductionInitializationContract`: immutable SCOS contract carrying authorization identity, engagement identity, SCOS project ID, deterministic HVS project ID, Stage 2 payload hash, HVS initialization contract, and false asset/render flags.
- `HVSProjectInitializationEvidence`: append-only verified, replay, rejected, or conflict evidence with HVS exit codes, semantic comparison result, correlation ID, and safe relative HVS project path.

The HVS initialization contract uses:

- schema version: `hvs.project-initialization.v1`
- contract name: `scos-hvs.project-initialization`
- contract version: `1`
- exact HVS project ID in `project.project_id`
- certified Stage 2 timeline payload in `timeline`

## 6. Eligibility Contract

Stage 8L re-verifies before mutation:

- kickoff authorization exists and has a valid schema/content hash
- engagement activation exists and is `APPROVED_FOR_PROJECT_INITIALIZATION`
- activation content hash matches authorization
- approval event exists
- proposal, acceptance, handoff, presentation, decision, delivery, and artifact lineage remain valid through Stage 8K eligibility
- payment readiness is satisfied or not applicable
- customer input is satisfied by operator confirmation
- `project_initialization_authorized=true`
- `project_initialization_performed=false`
- `manual_project_initialization_required=true`
- `automation_allowed=false`
- project, HVS, asset, and render flags remain false

Blocked eligibility invokes no HVS mutation.

## 7. Deterministic Project And Payload

- HVS project ID derivation: `hvs_project_id_for_authorization(production_kickoff_authorization_id)`
- Direct acceptance project ID: `hvs8l-e32880405a6292d1ac4e1f68997d085f`
- Expected payload hash derivation: Stage 2 `payload_identity_hash`
- Direct acceptance expected payload hash: `61831ed3c2f9bbd3`
- Payload file location: ignored SCOS runtime storage under `scos/work/.../hvs_project_initialization_contracts`
- Payload writer is idempotent and rejects conflicting same-ID file content.

## 8. Operator Gate And Adapter Boundary

Initialization requires:

- explicit operator ID
- explicit recorded date
- explicit production input JSON or service input
- explicit `approve_initialization=True`
- HVS repo root with `hvs/cli`
- HVS repository-local Python executable when used for mutating Stage 8L commands

Adapter guarantees:

- argv list
- `shell=False`
- bounded timeout
- bounded stdout/stderr excerpts
- empty environment
- no HVS Python package import
- only `initialize-project` and `inspect-project` for Stage 8L JSON commands

## 9. HVS Result Validation And Semantic Comparison

SCOS does not trust exit code alone. Verification requires:

- requested project ID equals contract HVS project ID
- actual project ID equals contract HVS project ID
- expected payload hash equals contract Stage 2 payload hash
- actual payload hash equals contract Stage 2 payload hash
- HVS reports `project_verified=true`
- `inspect-project` succeeds
- inspected title, language, project ID, timeline validity, and initialization payload hash match
- inspected voice, placeholders, assets, and render flags remain false

## 10. Replay, Conflict, And No-Overwrite

- Exact replay uses the same authorization identity, same project ID, same contract ID, and same payload hash.
- Exact replay is idempotent: `project_created=false`, `identical_replay=true`, `project_verified=true`.
- Changed semantic replay uses the same HVS project ID but different contract semantics and is rejected as `PROJECT_INITIALIZATION_CONFLICT`.
- Existing conflicting HVS project content is not overwritten.

## 11. Direct Synthetic Acceptance

Synthetic acceptance evidence:

- Kickoff authorization ID: `scos-hvs-production-kickoff-authorization-a8a88f9fb761fd51bd3767d507962be0`
- Initialization contract ID: `scos-hvs-stage8l-contract-779468238d05c46fd2468d2f5098bdf2`
- Expected HVS project ID: `hvs8l-e32880405a6292d1ac4e1f68997d085f`
- Requested HVS project ID: `hvs8l-e32880405a6292d1ac4e1f68997d085f`
- Actual HVS project ID: `hvs8l-e32880405a6292d1ac4e1f68997d085f`
- Expected payload hash: `61831ed3c2f9bbd3`
- Actual payload hash: `61831ed3c2f9bbd3`
- Wrong-hash pre-mutation result: `PAYLOAD_HASH_MISMATCH`, exit 1, `project_created=false`
- Valid initialization exit code: 0
- Inspection exit code: 0
- `project_created`: true
- `identical_replay`: false for first initialization
- `project_verified`: true
- Semantic comparison: true
- Exact replay: exit 0, `project_created=false`, `identical_replay=true`, `project_verified=true`
- Changed semantic replay: `PROJECT_INITIALIZATION_CONFLICT`, exit 1, no overwrite
- Task-owned HVS project path: `projects/hvs8l-e32880405a6292d1ac4e1f68997d085f`
- HVS project files: `initialization_manifest.json`, `project_brief.json`, `timelines/video_timeline.json`
- HVS ignore evidence: `.gitignore:37:projects/`

## 12. Negative Acceptance

Proven by focused tests and direct acceptance:

- invalid authorization invokes no HVS mutation
- missing approval invokes no HVS mutation
- missing or invalid production input cannot produce verified evidence
- Stage 2 mapping failure cannot produce verified evidence
- malformed HVS inspection cannot become verified
- HVS non-zero exit cannot become verified
- inspection mismatch cannot become verified
- wrong expected payload hash is rejected before HVS mutation
- changed semantic replay returns conflict
- legacy `create-project` is never invoked
- Stage 3 direct filesystem creation is never invoked
- render is never invoked
- asset materialization is never invoked

## 13. Safety Confirmations

- HVS initializer used: `initialize-project`
- Legacy `create-project` used: NO
- Stage 3 direct-filesystem materialization used: NO
- HVS project created: YES, exactly one successful task-owned synthetic acceptance project
- Exact project ID honored: YES
- Payload hash matched: YES
- Project inspected: YES
- Semantic comparison passed: YES
- Exact replay idempotent: YES
- Changed semantic replay conflicted: YES
- Voice generated: NO
- Placeholders generated: NO
- Assets copied: NO
- Asset materialization authorized: NO
- Render authorized: NO
- Render started: NO
- MP4 created: NO
- HVS source modified: NO
- HVS commit created: NO
- Customer contacted: NO
- Invoice issued: NO
- Payment link created: NO
- Payment processed: NO
- Network used: NO
- Push performed: NO
- Stage 8M started: NO

## 14. Verification Evidence

- Focused Stage 8L tests: `.venv\Scripts\python.exe -m pytest scos\control_center\tests\test_hvs_project_initialization_materialization.py -q -p no:cacheprovider --tb=short --basetemp=.pytest-tmp-stage8h-stage8l` -> 6 passed
- Adapter tests: `.venv\Scripts\python.exe -m pytest scos\control_center\tests\test_hvs_adapter.py -q -p no:cacheprovider --tb=short --basetemp=.pytest-tmp-stage8h-adapter` -> 33 passed
- Stage 1-4 integration regressions: adapter, schema mapper, project creation, asset materialization -> 142 passed
- Stage 7-8K regressions: selected HVS delivery, invoice, revision, release, support, outcome, proposal, acceptance, and activation tests -> 406 passed
- Stage 8K focused tests: `test_hvs_engagement_activation_kickoff.py` -> 95 passed
- HVS Stage 8L.0 focused regression: `tests/test_stage8l0_exact_project_initialization.py` -> 42 passing tests, exit 0
- Smoke: `.venv\Scripts\python.exe scripts\test_smoke.py` -> 16 passed, 0 failed
- Security scan: `.venv\Scripts\python.exe scripts\security_scan_baseline.py` -> 467 files scanned, 0 findings, PASS
- Scanner tests: `.venv\Scripts\python.exe -m pytest scripts\tests\test_security_scan_baseline.py -q -p no:cacheprovider --tb=short --basetemp=.pytest-tmp-stage8h-security-stage8l` -> 3 passed
- Collection: `.venv\Scripts\python.exe -m pytest --collect-only -q -p no:cacheprovider --basetemp=.pytest-tmp-stage8h-collect-stage8l` -> 1755 tests collected, 0 collection errors
- Full SCOS suite: `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --tb=short --basetemp=.pytest-tmp-stage8h-full-stage8l` -> 1754 passed, 1 skipped
- Direct acceptance: PASS
- Negative acceptance: PASS
- `git diff --check`: exit 0; line-ending warnings only

## 15. Runtime Hygiene

SCOS runtime:

- Stage 8L direct acceptance data stored under ignored `scos/work`.
- Temporary pytest roots use ignored `.pytest-tmp-stage8h-*` names.
- No SCOS runtime JSON/JSONL or payload file is staged for commit.

HVS runtime:

- HVS tracked status after acceptance: clean
- HVS `git diff --check`: clean
- Task-owned project ignored by HVS `.gitignore`
- No media files were found under the task-owned HVS project.
- No `voice`, `assets`, `render`, or `renders` directory exists under the task-owned HVS project.

## 16. Known Warnings

- Pytest warns about unknown config option `cache_dir` in the SCOS and HVS pytest configurations.
- Git reports line-ending warnings for touched SCOS files: LF will be replaced by CRLF the next time Git touches them.
- Non-elevated sandbox reads cannot enumerate the elevated HVS acceptance project directory; escalated read-only verification was used for post-creation hygiene.

## 17. Commit Scope

Approved Stage 8L paths:

- `scos/control_center/hvs_project_initialization_models.py`
- `scos/control_center/hvs_project_initialization_service.py`
- `scos/control_center/hvs_project_initialization_store.py`
- `scos/control_center/tests/test_hvs_project_initialization_materialization.py`
- `scos/control_center/cli.py`
- `scos/control_center/hvs_adapter.py`
- `scos/control_center/hvs_schema_mapper.py`
- `scos/control_center/tests/test_hvs_adapter.py`
- `docs/certification/SCOS-HVS-Integration-Stage-8L-project-initialization-materialization.md`

No runtime JSON/JSONL, temporary payload, HVS runtime project, HVS source, customer data, payment evidence, media, assets, MP4, generated artifact, or Stage 8M code is in scope.

## 18. Final Verdict

PASS - Stage 8L implementation and certification evidence are complete pending the authorized local SCOS commit and post-commit verification.
