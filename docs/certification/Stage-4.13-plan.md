# Stage 4.13 — First Prospect Follow-up Decision Gate (Certification Plan)

## Scope

Add a local-only, read-only decision gate over Stage 4.12's
`prospect_execution_log.json`. Given the first-prospect execution evidence, it
deterministically decides the operator's next **manual** action and, optionally, writes
`first_prospect_follow_up_decision.json`. It is a decision gate only — no side effects
beyond the optional local report.

Deliverables:
- `scos/commercial/follow_up_models.py` — immutable models + constants.
- `scos/commercial/first_prospect_follow_up_decision.py` — `decide_first_prospect_follow_up`.
- `scos/commercial/tests/test_first_prospect_follow_up_decision.py` — plain-script suite.
- `docs/specification/FIRST_PROSPECT_FOLLOW_UP_DECISION_CONTRACT.md` — the contract.
- `scos/commercial/__init__.py` — lazy exports only (no eager imports, no knowledge import).

## Assumptions

- Stage 4.12 output is the sole input. Its actual (nested) shape is authoritative; Stage
  4.13 normalizes to it (`prospect.prospect_id`, `response_status.status/.next_action/
  .follow_up_due/.blocker_summary`) and does not change Stage 4.12.
- `checked_at` is always supplied explicitly by the caller (no clock is read).
- A single recorded `blocker_summary` maps to a 0-or-1-element `blockers` tuple.

## Architecture boundary

- Read-only over Stage 4.12; never mutates the source log or any Stage 4.1–4.12 artifact.
- Stdlib only + Stage 4.1 `FrozenMap`. Allowed imports: `pathlib`, `json`, `hashlib`,
  `re`, `typing`, `dataclasses`, `FrozenMap`, `follow_up_models`.
- No import of KnowledgeService / lower knowledge engines / Stage 4 report or delivery
  builders / outreach-sending utilities / network or cloud libraries.

## No-SaaS / no-network / no-LLM rules

- No network, cloud, SaaS, or auth/permission-server calls. `http(s)://` paths rejected.
- No LLM usage; the gate is a deterministic rule table, not an evaluator.
- Deterministic outputs only — no real clock, random, uuid, or environment-dependent data.

## No-CRM / no-scraping / no-auto-DM / no-billing rules

- No CRM, no lead scraping/enrichment, no auto-DM, no email/LINE automation, no message
  sending, no billing, no dashboard, no customer portal.
- A detected non-manual/automation signal inside an inspected log yields a `BLOCKED`
  decision (`accepted=False`, `priority=urgent`), never an automated action.
- `ESCALATE_TO_FIRST_CUSTOMER_FLOW` is a recommendation label only; it triggers no real
  Stage 4.6 / 4.8 / customer flow.
- A static forbidden-token scan (executable source only) guards against network / vendor /
  scraping / CRM / auto-message / knowledge-engine / billing / `auth` tokens.

## No real customer PII

Direct personal-data keys (`phone`, `email`, `address`, `personal_name`, `personal_id`,
`national_id`, `tax_id`) anywhere in the inspected log are rejected with
`SENSITIVE_METADATA`. Generic business display aliases are allowed.

## Required test commands

```
.venv\Scripts\python.exe scos\commercial\tests\test_first_outreach_launch_kit.py
.venv\Scripts\python.exe scos\commercial\tests\test_operator_practice_lab.py
.venv\Scripts\python.exe scos\commercial\tests\test_launch_certification_pack.py
.venv\Scripts\python.exe scos\commercial\tests\test_first_paid_customer_dry_run.py
.venv\Scripts\python.exe scos\commercial\tests\test_monetization_readiness.py
.venv\Scripts\python.exe scos\commercial\tests\test_customer_kit.py
.venv\Scripts\python.exe scos\commercial\tests\test_acceptance_gate.py
.venv\Scripts\python.exe scos\commercial\tests\test_commercial_run_orchestrator.py
.venv\Scripts\python.exe scos\commercial\tests\test_cli.py
.venv\Scripts\python.exe scos\commercial\tests\test_report_builder.py
.venv\Scripts\python.exe scos\commercial\tests\test_delivery_package.py
.venv\Scripts\python.exe scos\commercial\tests\test_first_prospect_execution_log.py
.venv\Scripts\python.exe scos\commercial\tests\test_first_prospect_follow_up_decision.py
.venv\Scripts\python.exe scos\knowledge\tests\test_knowledge_service.py
```

## Remaining risks

- Stage 4.12's output shape is a hard dependency; a future Stage 4.12 rename would require
  updating Stage 4.13's normalization map (and its documented table), never the reverse.
- The response-status → action table is intentionally conservative; new Stage 4.12 statuses
  would surface as `INVALID_RESPONSE_STATUS` until the map is extended.
- Automation-signal detection is key-name based; deliberately obfuscated signals are out of
  scope (the manual-only guardrail is an operator aid, not an adversarial filter).

## PASS criteria

- All 14 required suites pass with 0 failures (Stage 4.13 suite is 74 checks, 0 failures).
- No Certified Core, `scos/knowledge` implementation, or Stage 4.1–4.12 contract changes.
- The source execution log is byte-for-byte unchanged after a decision run.
- The executable source contains none of the forbidden tokens.

## Note

Stage 4.13 is a **manual decision gate only**. It reads Stage 4.12 output, recommends a
manual next action, and optionally records that recommendation locally. It alters no
Stage 4.1–4.12 contract and performs no CRM / scraping / auto-DM / billing / SaaS /
dashboard / network / LLM behavior.
