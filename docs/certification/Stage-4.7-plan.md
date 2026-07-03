# Stage 4.7 - Monetization Readiness Review (Certification Plan)

## Scope

Stage 4.7 adds a local-only, deterministic, read-only monetization readiness
review over the Stage 4.5 acceptance report and Stage 4.6 first customer
operating kit.

New files:

- `scos/commercial/monetization_models.py`
- `scos/commercial/monetization_readiness.py`
- `scos/commercial/tests/test_monetization_readiness.py`
- `docs/specification/MONETIZATION_READINESS_REVIEW_CONTRACT.md`
- `docs/certification/Stage-4.7-plan.md`

Modified:

- `scos/commercial/__init__.py` for lazy Stage 4.7 exports only.

## Entry Criteria

- Branch is `main`.
- `HEAD` matches `origin/main`.
- Dirty files are limited to the Stage 4.7 allowlist.
- Stage 4.1-4.6 tests remain available as regression gates.

## Implementation Scope

The review API is:

```python
review_monetization_readiness(
    *,
    acceptance_report_path,
    operating_kit_path,
    checked_at: str,
    output_path=None,
    require_pricing=True,
    require_offer=True,
    require_delivery_artifacts=True,
    require_handoff_script=True,
    require_risk_checklist=True,
)
```

It records ordered checks, computes seven categories x 10 points for
`max_score = 70`, produces concrete gaps, and returns GO / CONDITIONAL_GO /
NO_GO. It may write `monetization_readiness_report.json` only when
`output_path` is provided and validation completes.

## Acceptance Compatibility

Stage 4.7 accepts:

- real Stage 4.5 reports using `ok`, `overall_status`, `created_at`, and `checks`
- spec-shape reports using `accepted`, `checked_at`, and `checks`

The loader derives `accepted` from explicit `accepted` when present; otherwise it
uses `ok is True and overall_status == "PASS"`. It derives the acceptance checked
timestamp from explicit `checked_at` when present; otherwise from `created_at`.

## Risk Requirement

Risk readiness requires an explicit `risk_checklist.md` or `risks.md` file in the
kit directory or referenced by `customer_kit_manifest.json`. It is never inferred
from `operator_sop.md` or pre-run checks. A default Stage 4.6 kit without a risk
checklist can correctly produce `ready=False` and `NO_GO`.

## Decision Rules

- `GO`: no blocking gaps, score >= 60, accepted report.
- `CONDITIONAL_GO`: no blocking gaps, no critical/blocking acceptance failure,
  score >= 50, accepted report, only non-blocking gaps remain.
- `NO_GO`: anything else.

Any blocking gap in offer, pricing, workflow, delivery, acceptance, risk, or
handoff readiness forces `NO_GO`.

## Test Gates

Run exactly:

```
.venv\Scripts\python.exe scos\commercial\tests\test_report_builder.py
.venv\Scripts\python.exe scos\commercial\tests\test_delivery_package.py
.venv\Scripts\python.exe scos\commercial\tests\test_cli.py
.venv\Scripts\python.exe scos\commercial\tests\test_commercial_run_orchestrator.py
.venv\Scripts\python.exe scos\commercial\tests\test_acceptance_gate.py
.venv\Scripts\python.exe scos\commercial\tests\test_customer_kit.py
.venv\Scripts\python.exe scos\commercial\tests\test_monetization_readiness.py
.venv\Scripts\python.exe scos\knowledge\tests\test_knowledge_service.py
.venv\Scripts\python.exe scos\knowledge\tests\test_learning_index.py
.venv\Scripts\python.exe scos\knowledge\tests\test_query_engine.py
.venv\Scripts\python.exe scos\knowledge\tests\test_explain_engine.py
.venv\Scripts\python.exe scos\knowledge\tests\test_insight_engine.py
```

Acceptance requires all pass with 0 failures.

## Boundary Rules

- Python standard library only.
- No SaaS, network, cloud, auth, payment, or LLM behavior.
- No Certified Core changes.
- No `scos/knowledge` implementation changes.
- No Stage 4.1-4.6 contract changes.
- No source artifact mutation.
- No eager imports in `scos/commercial/__init__.py`.
- No commit, push, tag, release, pull, merge, rebase, reset, stash, clean, or
  branch switch as part of this stage.

## Exit Criteria

- Stage 4.7 model, review, lazy exports, tests, and docs are present.
- The review remains local-only, deterministic, and read-only.
- Regression commands above pass.
- Final report includes changed files, git status, diff stat, and no-commit/no-
  history-operation confirmations.

