# AI Business Production — Governed Production Loop R1

## Canonical flow

`intake -> HAIOS qualification binding -> live machine observation -> capability admission -> adaptive route -> Ollama generation -> ai-core structural/semantic validation -> existing CommandBus execution -> observed execution telemetry -> durable evidence seal`

The feature does not introduce a second orchestrator or mutation path. `CommandBus` remains the existing single mutation path.

## Route admission

A route is eligible only when the current machine observation, qualification evidence, cost policy, currentness, health, licence, hardware fit, and evidence references are all valid. UNKNOWN or missing evidence fails closed.

Each routed decision carries:
- `routeDecisionId`
- `loopRunId`
- capability identity/version
- provider/model/version
- qualification evidence references

## Adaptive routing

Eligible candidates are ordered deterministically by:
1. explicit priority
2. observed success rate
3. observed latency
4. provider/model lexical tie-break

Observed history is filtered by `contractRevision`, a SHA-256 hash of the current AI generation contract. Historical observations produced under older generation assumptions are not reused for current routing.

## Real telemetry

Each execution record contains:
- `loopRunId`
- `routeDecisionId`
- provider/model/version
- generation and execution status
- duration
- request/response hashes
- project before/after hashes
- executed CommandBus command types
- qualification and machine-evidence references
- `contractRevision`

Evidence is sealed with a deterministic SHA-256 over canonical payload bytes.

## Verified live observations — 2026-09-18

- `qwen3:4b`, current contract: `276d67fd-9189-4b67-8f0e-4e69d5cca69b`, COMPLETED, 3968 ms.
- `qwen3:14b`, current contract: `f437706e-d0d0-4f2b-9b2f-e0b5ed83675d`, COMPLETED, 23030 ms.
- Auto-routed current-contract run selected `qwen3:4b`: `4c512782-b4ff-4aa0-9f9c-a5f40ef29028`, COMPLETED, 5278 ms.
- Final repeated auto-route smoke selected `qwen3:4b`: `7cd070a7-2b69-4f2a-907d-55b96f9f21f3`, COMPLETED, 4544 ms.
- Earlier pre-contract failures are retained as historical evidence but excluded from current routing because they lack the current `contractRevision`.

## Verification

- `@haios/ai-providers`: 31 tests passed.
- Workspace typecheck: passed across 6 package projects.
- Workspace tests: project-model 29, command-system 79, timeline 14, media-engine 17, ai-core 9, ai-providers 31.
- Workspace builds: passed across the 6 package projects.
- HAIOS bridge remains intact in this worktree.

## Open gates outside this feature

This feature closes the AI execution/routing/telemetry engineering gate. It does not fabricate external social-platform/business telemetry; the existing SCOS M1-M2 external data gate remains open until a real published observation is causally joined to a provenance-bearing `loop_run_id`.
