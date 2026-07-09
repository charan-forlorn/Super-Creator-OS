# Read-Only Execution Evidence Surface Contract

Stage: 7.6 - Read-Only Execution Evidence Surface.

## Purpose

This contract defines how Stage 7.6 classifies command execution evidence for
operator inspection while preserving Stage 6 command runner, allowlist,
approval persistence, and append-only audit behavior.

## Read-Only Boundary

Stage 7.6 reads or receives evidence and returns view models. It does not
write SQLite, JSONL, approval, audit, queue, event, state, schema, or result
artifacts. It does not run commands.

## Execution Evidence Classification

Allowed execution states:

- `not_executed`
- `executed`
- `blocked_missing_approval`
- `blocked_denied`
- `blocked_tampered_approval`
- `blocked_not_allowlisted`
- `blocked_validation_failed`
- `unknown`

Classification rules:

- Missing approval blocks execution evidence.
- Denied approval blocks execution evidence.
- Tampered approval blocks execution evidence with a security blocker.
- Non-allowlisted command type blocks execution evidence.
- Failed validation blocks execution evidence.
- Present execution events mark the action instance as executed.
- Unknown evidence remains unknown and is never reported as healthy.

## Audit and Event Evidence

Audit states:

- `audited`
- `missing`
- `tampered`
- `unknown`

Event states:

- `present`
- `missing`
- `unknown`

Missing or tampered audit evidence is a blocker. Unknown audit evidence is a
warning. Event evidence is displayed as local evidence only and does not imply
permission to run anything.

## Terminal-State Rules

Terminal command instances:

- denied
- missing approval
- tampered approval
- blocked
- executed

Terminal states do not expose retry or execution affordances. A new command
draft must be created manually if work is still required.

## UI Projection Rules

The frontend projection uses static deterministic mock data. It may show
evidence and next manual action text. It must not show action buttons that
approve, deny, execute, retry, dispatch, or route work.

## Forbidden Behaviors

- no writes
- no schema changes
- no command execution
- no shell or process spawning
- no browser, GUI, or clipboard automation
- no live transport
- no network/cloud/SaaS/payment/CRM behavior
- no adapter activation

## Stage 7.7 Handoff

Stage 7.7 should treat this evidence surface as inspection input for adapter
activation preflight. It must separately prove approval evidence, secret
handling, simulator fallback, manual fallback, audit records, rollback, and
security review before any future activation decision.
