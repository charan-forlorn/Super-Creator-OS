# Control Center Command Bridge Contract (Stage 5.1)

## Purpose

Define the first local-first bridge between the SCOS Control Center concept and
the local SCOS command system. Stage 5.1 answers one question:

> Can an operator create a safe local command draft, validate it, approve it,
> queue it, run only allowed local commands, and record deterministic
> command/result events?

The bridge realizes the Stage 4.18 design in
`CONTROL_CENTER_COMMAND_API_DESIGN.md` for a single, narrow slice: local
verification commands only, gated by explicit human approval, with append-only
JSONL state readable without any server.

## Scope

- Package: `scos/control_center/` (Python stdlib only).
- Modules: `command_models`, `command_validation`, `operator_approval`,
  `command_queue`, `event_log`, `command_runner`.
- Schema versions: every module exports a `*_SCHEMA_VERSION = 1` constant;
  changes are additive-only.
- The package never imports `scos.commercial` or `scos.knowledge` in-process.
  The Stage 4.19 gate is reached only through an allowlisted subprocess.

## Non-goals

Stage 5.1 is NOT: a SaaS feature, a backend/API server, a database (no SQLite),
WebSocket or polling, real agent dispatch, CRM, payment/billing/invoicing, a
customer portal, automation sending (email/LINE/DM), or LLM calls. It changes
no Stage 4 public contract and mutates no Stage 4 artifact.

## Command lifecycle

```
CommandDraft
  -> CommandValidation        (validate_command_draft)
  -> OperatorApproval         (approve_command / reject_command)
  -> ApprovedCommand          (create_approved_command)
  -> LocalCommandQueue JSONL  (append_approved_command)
  -> CommandRunner allowlist  (run_approved_command)
  -> CommandResult
  -> CommandEventLog JSONL    (append_command_event)
```

Lifecycle events (`COMMAND_DRAFTED`, `COMMAND_VALIDATED`, `COMMAND_REJECTED`,
`COMMAND_APPROVED`, `COMMAND_QUEUED`, `COMMAND_STARTED`, `COMMAND_COMPLETED`,
`COMMAND_FAILED`, `COMMAND_BLOCKED`) are recorded in the event log; see
`CONTROL_CENTER_EVENT_LOG_CONTRACT.md`.

## Allowed command types

Exactly six types are allowlisted; everything else is rejected at validation
and blocked (never executed) at the runner:

| Command type | Effect |
| --- | --- |
| `RUN_SMOKE_CHECK` | Run `scripts/test_smoke.py` with the local interpreter |
| `RUN_RELEASE_CHECK` | Run `scripts/test_release.py` |
| `RUN_SECURITY_SCAN` | Run `scripts/security_scan_baseline.py` |
| `RUN_STAGE4_FINAL_GATE` | Run the Stage 4.19 final release gate via `python -c` (requires `checked_at` arg) |
| `OPEN_STAGE5_HANDOFF` | Verify `docs/roadmap/STAGE5_HANDOFF.md` exists (no external app is opened) |
| `GENERATE_STATUS_SNAPSHOT` | Read-only git queries: `status --short --untracked-files=all`, `rev-parse HEAD`, `rev-parse origin/main`, `branch --show-current` |

Interpreter selection prefers `.venv/Scripts/python.exe` under the repo root
when present, else the current interpreter (same rule as the Stage 4.19 gate).

## Forbidden commands

Draft text (summary, arg keys/values, metadata) is scanned case-insensitively
for forbidden command markers: git mutation commands (push / commit / reset /
clean / rebase / merge / stash), destructive file commands (`rm -rf`,
`del /f`, `format`), network fetch tools (`curl`, `wget`), encoded PowerShell,
money/relationship-system words (payment, billing, invoice, crm), automation
sending (send_email, send_line, auto_dm), and network/release words (network,
webhook, cloud_deploy, deploy, vercel deploy). Any match rejects the draft.
The canonical marker list is `FORBIDDEN_COMMAND_TEXT` in
`scos/control_center/command_validation.py` (markers are fragment-assembled in
source per the repo static-scan convention). Additionally, arg values may not
be URLs and may not contain shell-injection characters
(`; & | > < ` $` and newlines).

## Approval requirement

No command executes without an explicit human operator approval; see
`OPERATOR_APPROVAL_GATE_CONTRACT.md`. The runner accepts only
`ApprovedCommand` instances, and an `ApprovedCommand` can only be produced by
`create_approved_command` from a valid draft plus a granting
`OperatorApproval` with a matching `command_id`.

## JSONL queue contract

- `append_approved_command(queue_path=..., approved_command=...) -> str`
  appends exactly one compact JSON object line (UTF-8, LF) and returns the
  line's SHA-256 hex digest.
- Key order per line is the model's explicit `to_dict()` order:
  `command_id, command_type, approved_by, approved_at, args, metadata`
  (`args`/`metadata` serialize as lists of `[key, value]` pairs).
- The queue is append-only: existing lines are never deleted or rewritten.
- Parent directories are created as needed; `queue_path` may be `str` or
  `pathlib.Path`; URL paths raise `URL_PATH_REJECTED: ...`.
- `read_command_queue(queue_path=...)` returns commands in append order,
  skipping blank lines. An invalid line raises the stable
  `INVALID_QUEUE_LINE: line <n> is not valid JSON`. A missing file reads as an
  empty queue.

## Local-only constraints

- Python stdlib only; no network, no server, no database, no WebSocket.
- No real clock (`created_at` / `approved_at` / `started_at` / `finished_at`
  are always caller-supplied), no random, no uuid; all ids are SHA-256
  content-derived.
- Subprocesses use list arguments only (`shell=True` is never used), a finite
  deterministic timeout (900 s), and captured output truncated to 4000-char
  excerpts.
- `dry_run=True` never spawns a subprocess; the planned command appears only
  in result metadata.
- The only writes are appends to the caller-supplied queue/event-log paths.

## Stage 5.1 acceptance criteria

1. All six Stage 5.1 test scripts pass
   (`scos/control_center/tests/test_*.py`, plain executable style).
2. A valid draft flows end-to-end: validate -> approve -> queue -> dry-run ->
   `COMMAND_STARTED` + `COMMAND_COMPLETED` events in the JSONL log.
3. An invalid or forbidden draft can never produce an `ApprovedCommand`.
4. An unknown command type and a `RUN_STAGE4_FINAL_GATE` without `checked_at`
   produce blocked results and `COMMAND_BLOCKED` events, never execution.
5. Identical inputs produce byte-identical queue lines, event lines, and ids.
6. Existing Stage 4 checks (`scripts/test_smoke.py`,
   `scripts/security_scan_baseline.py`, `scripts/test_release.py`) still pass
   unchanged.
