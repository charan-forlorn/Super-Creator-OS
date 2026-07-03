# First Prospect Mini-Audit Handoff Contract (Stage 4.14)

## Purpose

Stage 4.14 is a **local package-generation layer**. When a Stage 4.13 follow-up decision
recommends a manual mini-audit (`SEND_MINI_AUDIT`, or `ESCALATE_TO_FIRST_CUSTOMER_FLOW`
with explicit opt-in), it generates a deterministic local handoff folder that the operator
manually reviews and sends **outside** SCOS. It answers:

> "If Stage 4.13 decides SEND_MINI_AUDIT or manual escalation is appropriate, can SCOS
> generate a deterministic local handoff package the operator can manually review and send?"

It generates local files only. It never sends messages, never contacts external services,
never keeps a customer database, never touches billing, and never mutates the Stage 4.12 /
Stage 4.13 source artifacts.

## Architecture

```
first_prospect_follow_up_decision.json  (Stage 4.13 output, read-only)
        │
        ▼
create_first_prospect_mini_audit_handoff()
        │  validate decision → load referenced Stage 4.12 execution log
        │  → validate manual-only + no PII → build handoff folder
        ▼
<output_dir>/<handoff_id>/
    mini_audit_handoff_manifest.json
    mini_audit_summary.md
    operator_review_checklist.md
    prospect_context.json
    handoff_message_draft.md
    evidence_index.json
        │
        ▼
operator manually reviews and sends outside SCOS
```

Stage 4.14 may **read** the Stage 4.13 decision artifact, the Stage 4.12 execution log it
references, and optional local evidence files it references. It must not send messages,
call outreach/CRM/network/billing tools, create customer-portal behavior, mutate the
4.12/4.13 artifacts, generate hidden business strategy, or use the real clock, random,
uuid, network, or environment-dependent output.

## Public API

```python
from scos.commercial.first_prospect_mini_audit_handoff import (
    create_first_prospect_mini_audit_handoff,
)

create_first_prospect_mini_audit_handoff(
    *,
    decision_path,                       # str | pathlib.Path — Stage 4.13 decision file
    checked_at: str,                     # explicit caller-supplied timestamp string
    output_dir,                          # str | pathlib.Path — parent for the handoff folder
    allow_escalation_handoff: bool = False,
    require_human_review: bool = True,
    overwrite: bool = False,
) -> FirstProspectMiniAuditHandoffResult | FirstProspectMiniAuditHandoffError
```

- `decision_path` must exist and be a file. `http(s)://` paths are rejected.
- `checked_at` must be a non-empty string (no real clock is ever read).
- The handoff folder `<output_dir>/<handoff_id>/` is created only after all hard
  validations pass. Nothing is written outside `output_dir`.
- `overwrite=False` fails deterministically (`OUTPUT_EXISTS`) if the handoff folder exists.
  `overwrite=True` overwrites only the Stage 4.14 artifacts inside the handoff folder.

## Model contracts

All models are immutable (`@dataclass(frozen=True)`), reuse the Stage 4.1 `FrozenMap`, and
serialize via `to_dict()` with explicit key order (tuples → lists, nested dataclasses via
their own `to_dict()`, `FrozenMap` → plain dict). Callers write JSON with
`sort_keys=True, indent=2` plus a trailing newline.

`FIRST_PROSPECT_MINI_AUDIT_HANDOFF_SCHEMA_VERSION = 1`

**MiniAuditHandoffCheck** — `check_name, status, severity, artifact_path, error_kind,
error_detail, metadata`. `status ∈ {success, failure, skipped}`,
`severity ∈ {info, warning, error}`.

**MiniAuditHandoffArtifact** — `artifact_name, artifact_type, path, required, description,
metadata`. `artifact_type ∈ {manifest, markdown, json, checklist, evidence, summary}`.

**FirstProspectMiniAuditHandoffResult** — `ok, schema_version, accepted, handoff_id,
prospect_id, decision_id, execution_log_id, checked_at, output_dir, manifest_path,
artifacts, checks, blockers, metadata`.

**FirstProspectMiniAuditHandoffError** — `ok, schema_version, error_kind, error_detail,
failed_check, checks, blockers, metadata`.

## Input decision assumptions & normalization

Stage 4.14 aligns to the **actual** Stage 4.13 output (it never changes Stage 4.13).
Required decision keys: `schema_version, decision_id, prospect_id, checked_at, action,
source_execution_log_path, checks, blockers, metadata`, where `action` is an object with an
`action` string. Safe prospect context is read from the referenced Stage 4.12 execution log:

| Handoff context field | Stage 4.12 execution-log source |
| --- | --- |
| `business_display_name` | `prospect.display_name` |
| `market_category` | `prospect.business_type` |
| `response_status` | `response_status.status` |
| `next_action` | `response_status.next_action` |

## Allowed Stage 4.13 actions

- `SEND_MINI_AUDIT` → handoff allowed.
- `ESCALATE_TO_FIRST_CUSTOMER_FLOW` → handoff allowed **only** when
  `allow_escalation_handoff=True`.
- `FOLLOW_UP`, `WAIT`, `CLOSE_NO_GO`, `BLOCKED` → `HANDOFF_NOT_ALLOWED`.

The action allow-list is checked **before** the `accepted` flag, so a `BLOCKED` decision
(which has `accepted=False`) returns `HANDOFF_NOT_ALLOWED`, while a `SEND_MINI_AUDIT`
decision that is not accepted returns `DECISION_NOT_ACCEPTED`.

## Mini-audit handoff package layout

`<output_dir>/<handoff_id>/` with exactly six deterministic files:
`mini_audit_handoff_manifest.json`, `mini_audit_summary.md`,
`operator_review_checklist.md`, `prospect_context.json`, `handoff_message_draft.md`,
`evidence_index.json`. `handoff_id` derives deterministically from
`decision_id | prospect_id | checked_at` (sanitized text + a SHA-256 12-char prefix); no
uuid, random, or clock.

## Artifact schemas

**A. mini_audit_handoff_manifest.json** — `schema_version, handoff_id, prospect_id,
decision_id, execution_log_id, checked_at, source_decision_path,
source_execution_log_path, artifacts, checks, blockers, metadata`.

**B. mini_audit_summary.md** — sections: *Mini-Audit Handoff Summary*, *Prospect Context*,
*Outreach Evidence*, *Recommended Manual Next Step*, *Operator Notes*, *Out of Scope*.

**C. operator_review_checklist.md** — confirm business/display alias is safe, no direct
PII, no unsupported claim, no automated messaging, channel & message manually selected,
handoff reviewed by a human operator.

**D. prospect_context.json** — safe fields only: `prospect_id, business_display_name,
market_category, response_status, next_action, blockers, metadata`.

**E. handoff_message_draft.md** — manual-review warning; a concise draft; no
guaranteed-revenue claim; no automated-sending claim; no personal data; no hidden
strategy; no platform-specific delivery instruction.

**F. evidence_index.json** — `decision_path, execution_log_path, generated_artifacts,
source_artifacts_read_only, no_mutation_confirmed` (always `true`).

## Manual review requirements

The package is manual-review-first. The summary and checklist require an operator to
confirm safety before any message leaves SCOS. `require_human_review` (default `True`) is
recorded in the prospect-context metadata. SCOS never performs the send.

## handoff_message_draft.md limitations

The draft is a starting point only. It contains no guaranteed-result claim, no automated
delivery, no personal data, and no platform-specific instruction, and it carries an
explicit "MANUAL REVIEW REQUIRED" banner directing the operator to review, edit, and send
it themselves.

## Error kinds

`INVALID_ARGUMENTS`, `INPUT_NOT_FOUND`, `INVALID_DECISION`, `DECISION_NOT_ACCEPTED`,
`HANDOFF_NOT_ALLOWED`, `INVALID_EXECUTION_LOG`, `SENSITIVE_METADATA`,
`MANUAL_ONLY_VIOLATION`, `PATH_CONTAINMENT_FAILED`, `OUTPUT_EXISTS`, `OUTPUT_WRITE_FAILED`,
`VALIDATION_FAILED`.

`accepted=True` only when the package is generated and all required checks pass.
`accepted=False` when the package is generated but a blocker (e.g. the referenced
execution log is missing) prevents safe handoff. A hard `Error` is returned only for
cases that prevent package creation.

## Determinism guarantees

- Output is a pure function of the inspected artifacts and the explicit arguments.
- No real clock, random, uuid, network, or environment-dependent output.
- Repeated runs with identical inputs and `overwrite=True` produce byte-identical files.

## Boundary rules

- **Local-only:** filesystem paths only; `http(s)://` rejected; no network, cloud, or SaaS.
- **Manual-only:** SCOS generates the package; the operator reviews and sends it.
- **No real customer PII:** direct personal-data keys (`phone, email, address,
  personal_name, personal_id, national_id, tax_id`) anywhere in the decision, execution-log
  prospect metadata, or mini-audit metadata are rejected. Business display aliases allowed.
- **No CRM / scraping / auto-DM / message-sending / billing / SaaS / dashboard / customer
  portal / network / LLM** behavior. Not automatic outreach. Not an LLM evaluator.
- Never mutates any Stage 4.1–4.13 artifact and never changes their contracts.

## Examples

```python
# SEND_MINI_AUDIT decision → build the handoff package.
create_first_prospect_mini_audit_handoff(
    decision_path="out/first_prospect_follow_up_decision.json",
    checked_at="2026-07-03T07:00:00Z", output_dir="handoffs")

# ESCALATE decision → build only with explicit opt-in.
create_first_prospect_mini_audit_handoff(
    decision_path="out/first_prospect_follow_up_decision.json",
    checked_at="2026-07-03T07:00:00Z", output_dir="handoffs",
    allow_escalation_handoff=True)
```

## Out of scope

CRM, lead scraping/enrichment, auto-DM, email/LINE automation, message sending, billing,
SaaS, dashboards, customer portals, LLM evaluation, network/cloud access, automatic
outreach, and any mutation of Stage 4.1–4.13 artifacts. Stage 4.14 is a manual handoff
package generator only.
