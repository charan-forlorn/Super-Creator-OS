# Local Operator Execution Console Contract (Stage 5.9)

## Purpose

Stage 5.9 turns an **already-approved** `manual_command` / `proposed_command`
(produced by the Stage 5.8 Git Commit / Push Approval Gate) into a safe,
deterministic **operator runbook**: ordered command steps plus a safety
checklist that a human runs manually outside SCOS. It then captures the
operator's pasted-back output, classifies the outcome, and preserves
deterministic JSONL evidence.

It answers: *When SCOS proposes a manual command after approval, how does the
operator safely see the exact command, understand the required pre-checks,
copy/run it manually outside SCOS, paste the result back, classify the
outcome, and preserve deterministic evidence?*

## Non-goals

Stage 5.9 is **NOT**: automatic command execution, a terminal emulator, shell
integration, clipboard automation, browser/GUI automation, a backend server,
real git execution by AI, real AI dispatch, or any SaaS/cloud/API/network
behavior. It never runs a command.

## Architecture boundary

```
Stage 5.8 Commit/Push Approval Gate
        ↓  (approved manual_command / proposed_command)
create_git_commit_runbook / create_git_push_runbook / create_manual_command_runbook
        ↓
ManualCommandRunbook  (safety checks + ordered command steps)
        ↓
Operator runs the command MANUALLY, outside SCOS
        ↓
capture_manual_command_result  →  CommandExecutionCapture (pasted output)
        ↓
classify_operator_execution_outcome  →  OperatorExecutionOutcome
        ↓
operator_execution_store (append-only JSONL evidence)
        ↓
Control Center UI (static mirror)
```

## Relation to Stage 5.8 Git Commit / Push Approval Gate

Stage 5.8 decides *whether* a commit/push is approved and emits inert command
guidance. Stage 5.9 consumes that approval and renders *how* to run it safely.
Stage 5.9 imports no Stage 5.8 module and breaks no Stage 5.8 public contract;
it references Stage 5.8 identifiers only as opaque strings
(`source_approval_id`, `source_commit_proposal_id`, `source_push_proposal_id`).

## Local-only manual execution rules

- Every command is instructional text. The operator copies it and runs it
  themselves, outside SCOS.
- Approval must exist before a command is used. Push approval is **separate**
  from commit approval.
- Results are pasted back manually; SCOS never reads a terminal or process.

## No automatic command execution rule

Stage 5.9 code imports none of `subprocess`, `os.system`, `pty`, `socket`,
`requests`, or `urllib`. No function runs, spawns, or shells out to a command.

## No clipboard automation rule

No `navigator.clipboard`, no OS clipboard read/write. The UI "copy" affordance
is inert text ("Copy manually from the command block").

## No terminal emulator rule

There is no PTY, no terminal widget, no live process stream. The runbook is a
static list of steps and expected-output hints.

## Operator runbook lifecycle

`drafted → ready_for_operator → (blocked) → executed_manually →
result_captured → verified | failed → archived`. Stage 5.9 constructs runbooks
in `ready_for_operator` (or `blocked` when preconditions are missing); later
statuses are set by the caller as the operator progresses.

## Result capture lifecycle

The operator pastes: the command they actually ran, a short summary, a raw
output excerpt (text only), and an exit-status string. The builder derives a
deterministic `verdict` and any warnings/blockers. Secrets must never be
pasted; secret-like metadata keys and URL evidence paths are rejected.

## Outcome classification

The verdict maps deterministically to an `outcome`, a
`recommended_next_action`, and an optional `recommended_next_agent`
(`chatgpt` / `claude_code` / `codex` / `hermes` / `operator` / none).
`operator_review_required` stays `true` unless the verdict is a clean `PASS`
with no warnings and no blockers. See
`MANUAL_COMMAND_RUNBOOK_CONTRACT.md` for the PASS/BLOCKED/FAIL rules.

## Safety model

- All models are immutable (frozen dataclasses; tuples, not lists; `FrozenMap`
  metadata). No mutable field is exposed.
- All IDs are deterministic `sha256(...)[:16]` digests of caller-supplied
  stable inputs, with typed prefixes (`rb-`, `rbs-`, `rbc-`, `cap-`, `oeo-`).
- `created_at` / `captured_at` are caller-supplied strings. No clock, no
  random, no uuid.
- Invalid inputs return a structured `OperatorExecutionError` (`ok=false`)
  rather than raising across the public API.
- Secret-like metadata keys are rejected: `api_key`, `token`, `secret`,
  `password`, `private_key`, `access_key`, `credential`. URL paths
  (`http://` / `https://` / any `scheme://`) are rejected wherever a local
  path is expected.

## JSONL storage paths

Callers pass an explicit local file path. Documented default work paths:

- `scos/work/control_center/manual_command_runbooks.jsonl`
- `scos/work/control_center/command_execution_captures.jsonl`
- `scos/work/control_center/operator_execution_outcomes.jsonl`

Lines are `json.dumps(sort_keys=True, separators=(",", ":"))`, UTF-8, LF
newline, append-only. Parent directories are created on first append. Missing
files load as an empty tuple. Malformed JSONL fails fast with a deterministic
`ValueError`. No SQLite, no locks, no background workers, no database.

## Frontend constraints

The Control Center "Execution Console" section is a static deterministic
mirror. It uses local React props/state only — no `fetch`, `XMLHttpRequest`,
`axios`, `WebSocket`, `EventSource`, `setInterval`, `setTimeout`, `Date.now`,
`Math.random`, `crypto.randomUUID`, `localStorage`, `sessionStorage`,
`navigator.clipboard`, `"use server"`, `app/api`, `route.ts`, or
`middleware.ts`. The UI makes the manual-execution boundary explicit.
