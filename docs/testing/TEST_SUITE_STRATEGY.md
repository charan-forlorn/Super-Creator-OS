# SCOS Test Suite Strategy (Stage 4.18)

Stage 4.18 splits the commercial test workload into four tiers so the local
operator can pick speed vs. depth deliberately instead of always running
everything. All tiers are local-first, stdlib-only, deterministic, and
network-free. Commands assume the repo root and the project venv.

## Tier 1 — Smoke

**Purpose:** fast import/API sanity for the local operator. Answers one
question: "is the commercial package importable and are the shared helpers
alive?" in seconds.

**When to run:** after every edit session, before any other tier, and as the
first step of any orchestrated check.

**Command:**

```
.venv\Scripts\python.exe scripts\test_smoke.py
```

**Expected runtime:** < 5 seconds.

**What smoke must NOT include:**

- No artifact generation outside a `TemporaryDirectory`.
- No import that resolves the Stage 3.9 knowledge layer (e.g. resolving
  `build_commercial_report` eagerly imports `knowledge_service`; smoke only
  verifies the name is exported). The lazy-import guarantee
  (`scos.knowledge` absent from `sys.modules`) is itself a smoke assertion.
- No subprocess, no git, no slow filesystem walks, no regression fixtures.

## Tier 2 — Regression

**Purpose:** stage-specific correctness and no contract drift. Each Stage
4.x feature has a plain-assert suite under `scos/commercial/tests/` that
exercises its full contract (valid inputs, error kinds, determinism,
boundary rejection).

**When to run:** after changing any commercial module, run the suite for
that stage plus its direct neighbors; run the representative set below
before any handoff or review.

**Commands (representative set):**

```
.venv\Scripts\python.exe scos\commercial\tests\test_report_builder.py
.venv\Scripts\python.exe scos\commercial\tests\test_delivery_package.py
.venv\Scripts\python.exe scos\commercial\tests\test_cli.py
.venv\Scripts\python.exe scos\commercial\tests\test_first_customer_conversion_handoff.py
```

Stage 4.18 additions:

```
.venv\Scripts\python.exe scos\commercial\tests\test_domain_models.py
.venv\Scripts\python.exe scos\commercial\tests\test_validation.py
.venv\Scripts\python.exe scos\commercial\tests\test_manifest_tools.py
```

**Expected runtime:** seconds per suite; under a minute for the
representative set. (`test_report_builder.py` requires `scos/knowledge` on
`sys.path`, which the suite arranges itself.)

## Tier 3 — Certification

**Purpose:** determinism, artifact integrity, contract validation, and stage
gate proof. This is the evidence tier: byte-identical reruns, manifest
checksum verification, static source scans for forbidden tokens, and the
per-stage exit criteria recorded in `docs/certification/Stage-4.x-plan.md`.

**When to run:** when closing a stage (its plan's "Verification plan" and
"Exit criteria" sections), and before declaring any stage gate passed.

**Command examples:**

```
REM full commercial test directory, every suite must exit 0
for %f in (scos\commercial\tests\test_*.py) do .venv\Scripts\python.exe %f

REM import safety proof
.venv\Scripts\python.exe -c "import sys, scos.commercial as c; assert not any(m.startswith('scos.knowledge') for m in sys.modules)"
```

**Expected runtime:** minutes (full directory plus static scans).

## Tier 4 — Release

**Purpose:** pre-push/pre-deploy final safety: git working-tree state,
smoke, the Stage 4.18 unit suites, the representative regression set, and
the security scan baseline, in one deterministic orchestration.

**When to run:** before any commit/push/tag decision by the operator, and
as the entry point for the Stage 4.19 final release gate.

**Command:**

```
.venv\Scripts\python.exe scripts\test_release.py
```

**Expected runtime:** one to a few minutes (superset of smoke + the
representative regression set + the security scan).

The release script never mutates the repo: git use is limited to a
read-only `git status --porcelain` (dirty paths are reported as WARN, not
mutated), and no commit/push/tag is ever performed.

## How Stage 4.19 should use this strategy

Stage 4.19 (Final Commercial Release Gate & Stage 5 Handoff) consumes this
strategy as its gating skeleton:

1. Run the release tier (`scripts/test_release.py`) as the entry check.
2. Expand the regression step from the representative set to the FULL
   `scos/commercial/tests/` directory (see the `TODO(Stage 4.19)` hooks in
   `scripts/test_release.py`).
3. Attach the certification tier evidence (determinism reruns, manifest
   checksums via `scos.commercial.manifest_tools`, static scans) to the
   Stage 4.19 gate record.
4. Record the security scan baseline result
   (`scripts/security_scan_baseline.py`) and the release-provenance
   checklist from `docs/security/SECURITY_HARDENING_BASELINE.md` as gate
   artifacts.

No tier introduces network, database, CRM/payment/billing behavior, LLM
calls, or agent dispatch; those remain out of scope for all of Stage 4.
