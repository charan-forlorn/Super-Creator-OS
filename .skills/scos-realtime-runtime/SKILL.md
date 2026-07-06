# Skill: scos-realtime-runtime

## Purpose
Design local-first realtime runtime for the Control Center: deterministic event contracts, replayable logs, and graceful degradation.

## When to Use
- Adding live updates, progress streams, or event feeds to the Control Center.
- Choosing transport (polling, SSE, WebSocket, file-watch) for a stage.
- Debugging state drift between backend events and UI display.

## Core Rules
- Start with a deterministic event contract before any transport decision.
- Prefer append-only JSONL event log before database complexity.
- All state is derived by replaying events; events must be replayable and ordered.
- Realtime must degrade to manual refresh — the fallback path is part of the design, not an afterthought.
- Local-first: no external network services; timers only if the stage explicitly requires them.
- Every failure mode (stale log, partial write, missed event) has a defined recovery.

## Required Output
- Realtime Goal
- Event Types
- Event Schema
- State Derivation
- Transport Options
- Fallback Mode
- Failure Modes
- Test Plan
- UI Mapping
- Claude Code Prompt

## Prompt Template
```
Act as SCOS Realtime Runtime Designer.
Goal: <what must update live>. Existing events/contracts: <paste or reference>.
Produce the Required Output. Event Schema as JSONL line examples.
State Derivation as pure replay rules. Test Plan must include a replay test
and a fallback-mode test.
```

## Anti-Scope-Drift Rules
- Design only the events the stated goal needs; no speculative event types.
- No transport upgrade (e.g., polling → WebSocket) beyond what the stage requires.
- Do not touch the storage contract of certified stages; extend additively.

## Token-Saving Rules
- One JSONL example line per event type.
- Reference existing event contracts by path instead of re-listing them.
- Transport Options: one line each with a pick and a reason — no essays.
