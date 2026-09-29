# Skill: scos-control-center-ui

## Purpose
Design Control Center UI as an operator-first command center: every panel maps to backend state and gives the operator status, evidence, risk, and a next action.

## When to Use
- Adding or redesigning a Control Center screen or panel.
- Mapping a new backend state machine into the UI.
- Preparing a mock-first UI stage before real integration.

## Core Rules
- UI must reflect the backend state machine — no UI-only states.
- Every panel shows: status, evidence, risk, and next action.
- Design empty, error, and blocked states before the happy path.
- Prefer static/mock UI before real integration; mock data shape must match the real contract.
- Operator actions are explicit and deterministic; no hidden auto-actions.
- No network/API/timer/fetch in the mock stage.

## Required Output
- User Flow
- Screen Sections
- Panel Contracts
- State Mapping
- Empty/Error/Blocked States
- Operator Actions
- Mock Data Shape
- Acceptance Criteria
- Claude Build Prompt

## Prompt Template
```
Act as SCOS Control Center UI Designer.
Feature: <panel/screen>. Backend states: <paste state machine or event contract>.
Produce the Required Output. State Mapping as backend-state → panel-display table.
Mock Data Shape as JSON matching the real contract. Build prompt is mock-first
and file-scoped.
```

## Anti-Scope-Drift Rules
- Design only the requested panel/screen; adjacent panels untouched.
- No new backend states invented for UI convenience — flag gaps instead.
- No visual polish tasks beyond the panel contract.

## Token-Saving Rules
- Panel Contracts as compact tables, one row per element.
- Reference the existing design system/components instead of describing styles.
- One representative mock record per shape, not full datasets.
