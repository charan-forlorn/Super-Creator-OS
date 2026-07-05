# SCOS Architecture Boundary Constitution

## Purpose

This document defines binding architecture boundaries for the Super Creator OS
(SCOS) repository. It exists to prevent the product runtime from becoming
entangled with the tooling used to build it, and to give every future
contributor — human or AI agent — an unambiguous answer to "where does this
code belong, and what may it depend on?"

This is a normative document. The rules below are requirements, not
suggestions. A change that violates them is an architecture defect and should
be treated as a blocking review issue, not a style nit.

## The Three Layers

### Layer 1 — Runtime Product Layer

**Responsibility:** the actual SCOS product that runs for end users and
customers — pipeline execution, rendering, learning, qualification,
commercial delivery, replay, analytics, knowledge and repository management.

**Lives in:** `scos/` (excluding `scos/control_center/`, which is Layer 3),
and any end-user-facing surfaces under `apps/` that are not operator tooling.

**Allowed dependencies:**
- Other Runtime Product Layer modules.
- Standard libraries and declared third-party packages.
- Operator Tools Layer output, but only by consuming an explicit, versioned
  contract (e.g. a schema/event format defined under
  `docs/specification/*_CONTRACT.md`) — never by importing Operator Tools
  Layer code directly.

**Forbidden dependencies:**
- Anything from `.claude/`, `.agents/`, `.codex/`, `.continue/`.
- Anything from `development/` (ai, playbooks, governance, checklists,
  benchmarks, evaluation, templates, examples, anti-patterns).
- `integrations/` agent/dev tooling, `skills/`, `discovered_skills/`,
  `scripts/` (dev/release scripts), `analysis/`, `project_audit/`.
- Any AI session- or agent-orchestration code, including the AI Work Session
  Manager (see Rule 3 below).

**Example modules:** `scos/pipeline`, `scos/render`, `scos/core`,
`scos/commercial`, `scos/qualification`, `scos/learning`, `scos/knowledge`,
`scos/repository`, `scos/replay`, `scos/analytics`, `scos/assets`.

### Layer 2 — Development Framework Layer

**Responsibility:** everything used to build, evaluate, and improve SCOS —
agent playbooks, governance documents, benchmarks, evaluation harnesses,
coding-agent skills, checklists, and templates. None of this is shipped to,
or executed by, the product at runtime.

**Lives in:** `.claude/`, `.agents/`, `.codex/`, `.continue/`,
`development/` (ai, playbooks, governance, checklists, benchmarks,
evaluation, templates, examples, anti-patterns), `skills/`,
`discovered_skills/`, `integrations/` (the agent/adapter/MCP tooling used to
build the product), `scripts/` (dev/test/release scripts), `analysis/`,
`project_audit/`.

**Allowed dependencies:**
- Other Development Framework Layer components.
- Read-only introspection of Runtime Product Layer code and docs for
  analysis or code-generation purposes. An agent reading `scos/` in order to
  write or review code is a workflow action, not a runtime import, and does
  not violate this constitution.

**Forbidden dependencies:**
- This layer must never become a runtime dependency of the shipped product.
  The Runtime Product Layer must never import from it (see Rule 1).

**Example modules:** `development/playbooks/`, `development/governance/`,
`.claude/settings.local.json`, `skills/*`, `scripts/test_smoke.py`,
`scripts/security_scan_baseline.py`.

### Layer 3 — Operator Tools Layer

**Responsibility:** tools used by human operators (or operator-facing
agents) to observe, command, and approve actions against the Runtime Product
Layer — without embedding product logic itself, and without becoming a
back door through which Development Framework code reaches the runtime.

**Lives in:** `scos/control_center/`, `apps/control-center/`.

**Allowed dependencies:**
- Explicit, documented contracts only. The existing pattern in
  `docs/specification/CONTROL_CENTER_COMMAND_BRIDGE_CONTRACT.md`,
  `CONTROL_CENTER_EVENT_LOG_CONTRACT.md`, and
  `OPERATOR_APPROVAL_GATE_CONTRACT.md` is exactly this: a defined
  command/event schema, not direct imports of Runtime Product Layer or
  Development Framework Layer internals.

**Forbidden dependencies:**
- Reaching into Runtime Product Layer internals directly, bypassing the
  command/event contract.
- Importing Development Framework Layer code (playbooks, agent
  orchestration) into the operator runtime path.

**Example modules:** `scos/control_center/command_runner.py`,
`command_models.py`, `event_log.py`, `command_queue.py`,
`operator_approval.py`, `command_validation.py`,
`apps/control-center/components/*`.

## Explicit Rules

1. The Runtime Product Layer MUST NOT import, require, or otherwise take a
   runtime dependency on any Development Framework Layer module or file.

2. The Operator Tools Layer MAY coordinate between the Runtime Product Layer
   and the Development Framework Layer, but only through explicit, versioned
   contracts (documents under `docs/specification/*_CONTRACT.md` or
   equivalent schema files) — never via direct code imports across layers.

3. The AI Work Session Manager (Stage 5.2 and beyond) belongs to the
   Development Framework Layer / Operator Tools coordination boundary. It is
   a tool for managing how work gets done *on* SCOS, not a part of the
   product SCOS *is*. It must not be imported by, or embedded into, the
   Runtime Product Layer.

4. Stage 5.2 — and any future stage building on the Control Center / Work
   Session Manager track — MUST NOT alter Runtime Product Layer behavior.
   Its scope is limited to the Operator Tools Layer and Development
   Framework Layer coordination surfaces.

5. Any new cross-layer capability must be introduced as a new explicit
   contract document under `docs/specification/`, reviewed before
   implementation — never as an ad hoc import.

## Guiding Principles

- **Deterministic:** layer boundaries and contracts must produce the same
  result given the same input — no hidden state crossing layers.
- **Local-first:** operator and development tooling operates against local
  state by default; no silent network or external calls introduced across a
  boundary.
- **Approval-first:** any action from the Operator Tools Layer that affects
  Runtime Product Layer state requires an explicit approval step, mirroring
  the existing `OPERATOR_APPROVAL_GATE_CONTRACT.md` pattern.

## Closing Note

This constitution is binding for all future contributors and coding agents
working in this repository. Violations discovered in review should be
treated as architecture defects, not style nits.
