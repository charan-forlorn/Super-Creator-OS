# Approval-Aware Operator Command Views Contract

Stage: 7.6 - Approval-Aware Operator Command Views / Read-Only Execution
Evidence Surface.

## Purpose

Stage 7.6 lets the local operator inspect command approval and execution
evidence without changing command execution behavior or weakening the Stage 6
approval and audit boundaries.

The stage is read-only. It does not approve, deny, run, retry, route, dispatch,
or mutate commands.

## Non-Goals

- no new command execution path
- no approval or denial writes
- no queue, event, approval, audit, state, or schema mutation
- no live UI sync transport
- no backend route or server
- no real adapter activation
- no network, cloud, SaaS, payment, CRM, or customer portal behavior
- no auth or API key behavior

## Read-Only Guarantee

Stage 7.6 backend functions accept caller-supplied evidence and return
immutable read models. They do not accept output paths and do not write files.
The frontend uses deterministic local fixture data only.

## Approval-State Lifecycle

Allowed approval states:

- `pending`
- `approved`
- `denied`
- `missing_approval`
- `tampered`
- `executed`
- `blocked`
- `unknown`

Rules:

- `pending` is visible and not executable by Stage 7.6.
- `approved` is visible but not run by Stage 7.6.
- `denied` is terminal for the current command instance.
- `missing_approval` is terminal for the current command instance.
- `tampered` is terminal and produces a security blocker.
- `executed` is terminal for the completed action instance.
- `blocked` displays the exact blocker and provides no bypass path.
- `unknown` is warning evidence, never healthy evidence.

## Public Models

- `OperatorCommandEvidenceReference`
- `OperatorCommandApprovalState`
- `ExecutionEvidenceRecord`
- `OperatorCommandView`
- `OperatorCommandViewTotals`
- `OperatorCommandViewSnapshot`

All Python models are frozen dataclasses with deterministic `to_dict()`
output.

## Public Functions

- `classify_approval_state`
- `classify_execution_state`
- `build_execution_evidence_record`
- `build_operator_command_view`
- `build_operator_command_view_snapshot`
- `validate_operator_command_view_inputs`
- `render_operator_command_view_markdown`

## Evidence Reference Schema

Evidence references include:

- reference id
- reference type
- source stage
- local path or logical source name
- existence flag
- readability flag
- optional digest

## UI Safety Rules

The UI may show command id, command type, approval state, execution state,
audit state, required manual action, terminal-state indicator, blockers,
warnings, and evidence references.

The UI must not show controls that perform approval, denial, execution, retry,
dispatch, transport, or network behavior.

## Forbidden Behaviors

Stage 7.6 must not introduce WebSocket, SSE/EventSource, polling, timers,
background workers, Next.js API routes, backend socket servers, adapter
dispatch, command execution, store mutation, or cloud/network behavior.

## Test Plan

Tests cover pending, approved, denied, missing approval, tampered, executed,
blocked, unknown evidence, missing optional evidence, missing required
evidence, deterministic ids, stable dictionaries, rejected output paths, no
SQLite mutation, no JSONL append/write, no command execution, frontend safety,
and forbidden token scans where practical.

## Stage 7.7 Handoff

Stage 7.7 may define adapter activation preflight only. It must not use Stage
7.6 visibility as permission to dispatch real adapters or execute commands.
