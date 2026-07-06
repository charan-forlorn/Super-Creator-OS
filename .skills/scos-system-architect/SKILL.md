# Skill: scos-system-architect

## Purpose
Design contract-first SCOS architecture before any implementation: components, data models, state machines, and event/UI/storage contracts.

## When to Use
- After requirements are refined (Ready-for-Architecture: YES).
- Before writing any Claude Code build prompt for a non-trivial stage.
- When an existing design needs extension without breaking certified stages.

## Core Rules
- Contracts first: data models, event schema, UI contract, and storage contract are defined before tasks.
- Deterministic local-first: no network/API/timer/fetch unless the stage explicitly requires it.
- Prefer append-only JSONL contracts before database complexity.
- Every state must be enumerable and derivable by replaying events.
- Design must not force changes to certified stages; call out any that would.
- Every contract needs an error/empty/degraded state, not just the happy path.

## Required Output
- Architecture Summary
- Component Boundaries
- Data Models
- State Machine
- Event Contract
- UI Contract
- Storage Contract
- Error Handling
- Test Strategy
- Migration Risk
- Claude Code Build Prompt
- Codex Review Prompt

## Prompt Template
```
Act as SCOS System Architect for Stage <N>.
Refined requirement: <paste>.
Existing constraints: <paste relevant contracts / certified-stage boundaries>.
Produce the Required Output sections. Contracts as schemas/tables, not prose.
The build and review prompts must name exact files.
```

## Anti-Scope-Drift Rules
- Design only what the requirement needs; no speculative extensibility layers.
- Do not redesign existing certified contracts; extend them additively.
- If the design needs a new dependency, stop and flag it — do not assume approval.

## Token-Saving Rules
- Schemas as compact JSON/tables, one field per line.
- Reference existing contract docs by path instead of copying them.
- Build prompt lists only the files to touch and the exact contracts to satisfy.
