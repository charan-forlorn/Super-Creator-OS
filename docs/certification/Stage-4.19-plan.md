# Stage 4.19 Plan — Stage 4 Final Commercial Release Gate & Stage 5 Handoff

## Stage goal

Create the final local-only Stage 4 release gate that verifies whether the
complete Stage 4 commercial foundation (4.1–4.18) is ready to close and hand
off to Stage 5. Stage 4.19 answers: *"Is Stage 4 complete, commercially
coherent, locally verifiable, security-baselined, and ready for Stage 5
execution planning?"* It is a certification / release-gate / handoff stage
only, and it explicitly closes Stage 4.

## Scope

- `run_stage4_final_release_gate(...)` — read-only certification over
  contract docs, executable source, Stage 4.18 hardening assets, the
  stage-over-fragmentation rule, the optional approved local scripts, and a
  static forbidden-behavior scan.
- Deterministic readiness scoring (max 100) with a GO / CONDITIONAL_GO /
  NO_GO verdict and `stage_closed` semantics.
- Deterministic gate-report JSON artifact (`stage4_final_release_gate.json`).
- Ten deterministic Stage 5 handoff items plus `docs/roadmap/STAGE5_HANDOFF.md`.

## Non-goals

Stage 4.19 does not rebuild reports or delivery packages, does not run
outreach or generate customer messages, does not send anything, and does not
create customer data. It adds no new commercial feature flow.

## Allowed files

Created: `scos/commercial/release_gate_models.py`,
`scos/commercial/stage4_final_release_gate.py`,
`scos/commercial/tests/test_stage4_final_release_gate.py`,
`docs/specification/STAGE4_FINAL_RELEASE_GATE_CONTRACT.md`,
`docs/certification/Stage-4.19-plan.md`,
`docs/certification/Stage-4-final-commercial-release.md`,
`docs/roadmap/STAGE5_HANDOFF.md`.
Modified: `scos/commercial/__init__.py` (lazy-export additions only; the
existing PEP 562 architecture and every Stage 4.1–4.18 export are preserved,
with no eager imports and no knowledge import at package import time).

## Architecture boundary

Stage 4.19 is a read-only certification layer over the commercial system:

```
Stage 4.1–4.18 source / contracts / scripts / docs
  -> Stage4FinalReleaseGate
  -> artifact checks -> contract checks -> test strategy checks -> security baseline checks
  -> Stage 4 final release gate result
  -> Stage 5 handoff package
```

It may inspect `scos/commercial/`, `scos/commercial/tests/`,
`docs/specification/`, `docs/certification/`, `docs/security/`,
`docs/testing/`, `docs/roadmap/`, and `scripts/`. Its only write is the gate
report at the caller-supplied `output_path`.

`subprocess` is the single documented exception to the commercial
no-subprocess convention: allowed only inside
`stage4_final_release_gate.py`, and only for read-only git queries and the
approved local scripts (`test_smoke.py`, `security_scan_baseline.py`,
`test_release.py`).

## Boundary rules (non-negotiable)

- No SaaS, no network, no cloud, no LLM calls, no CRM, no payment capture,
  no billing, no invoice generation, no customer portal.
- No backend/API server, no database, no WebSocket, no polling, no real
  agent dispatch, no live Control Center integration.
- No Certified Core changes; no `scos/knowledge` implementation changes.
- No Stage 4.1–4.18 public contract breaks; no mutation of existing Stage 4
  artifacts.
- Python stdlib only; deterministic outputs only (no clock/random/uuid).
- No Stage 4.20+ may be created — Stage 4 ends at 4.19; future work moves to
  the Stage 5 backlog. The gate enforces this with its marker scan.

## Required test commands

```
.venv\Scripts\python.exe scos\commercial\tests\test_stage4_final_release_gate.py
.venv\Scripts\python.exe scos\commercial\tests\test_domain_models.py
.venv\Scripts\python.exe scos\commercial\tests\test_validation.py
.venv\Scripts\python.exe scos\commercial\tests\test_manifest_tools.py
.venv\Scripts\python.exe scos\commercial\tests\test_report_builder.py
.venv\Scripts\python.exe scos\commercial\tests\test_delivery_package.py
.venv\Scripts\python.exe scos\commercial\tests\test_cli.py
.venv\Scripts\python.exe scos\commercial\tests\test_commercial_run_orchestrator.py
.venv\Scripts\python.exe scos\commercial\tests\test_acceptance_gate.py
.venv\Scripts\python.exe scos\commercial\tests\test_first_customer_conversion_handoff.py
.venv\Scripts\python.exe scos\knowledge\tests\test_knowledge_service.py
.venv\Scripts\python.exe scripts\test_smoke.py
.venv\Scripts\python.exe scripts\security_scan_baseline.py
```

## Release script strategy

`scripts/test_release.py` is the heavier release tier (it chains smoke, the
Stage 4.18 unit suites, representative regression suites, and the security
baseline). The gate's `run_release_script` flag therefore defaults to False;
run the script manually before tagging or pushing a release:
`.venv\Scripts\python.exe scripts\test_release.py`.

## Security scan baseline strategy

`scripts/security_scan_baseline.py` is run by the gate by default
(`run_security_scan=True`). It scans executable/config scope only (docs are
deliberately excluded), redacts its own findings, and any failure produces a
gate blocker. All scan tokens in Stage 4.19 executable source are assembled
from string fragments so the baseline scan never flags the gate itself.

## PASS criteria

- All required test commands above pass with 0 failures.
- The gate run over this repository reports GO (score >= 90, zero blockers)
  once the Stage 4.19 files are present — with `require_clean_git=False`
  while the Stage 4.19 files are still uncommitted, and with the full git
  policy after commit.
- The gate report JSON is byte-identical across repeat runs.
- No mutation of any inspected file; no Certified Core or knowledge changes.

## Remaining risks

- The git-state policy check depends on a local git binary; on machines
  without git the gate deterministically fails closed (GIT_UNAVAILABLE).
- The forbidden-behavior scan is import-level; behavior hidden behind
  dynamic imports would evade it (accepted for a local-first stdlib gate;
  the security baseline scan and reviews complement it).
- Readiness scoring treats flag-skipped script checks at half weight; a
  fully-skipped run can still reach CONDITIONAL_GO. The JSON records every
  skip transparently.

## Would-be commit message

```
feat(commercial): add Stage 4.19 final commercial release gate
```
