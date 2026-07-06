# Manual Command Runbook Contract (Stage 5.9)

Schemas and deterministic rules for the Stage 5.9 operator runbook layer.
`OPERATOR_EXECUTION_SCHEMA_VERSION = 1`. All models are immutable frozen
dataclasses in `scos/control_center/operator_execution_models.py`; collections
are tuples and `metadata` is a `FrozenMap`. `to_dict()` uses explicit key
order, serializes tuples as lists, nested models via their own `to_dict()`,
and `FrozenMap` as a plain dict.

## Runbook schema — `ManualCommandRunbook`

`ok`, `schema_version`, `runbook_id`, `source_approval_id?`,
`source_commit_proposal_id?`, `source_push_proposal_id?`, `session_id`,
`task_id`, `title`, `objective`, `command_summary`, `runbook_type`,
`created_at`, `status`, `safety_checks[]`, `command_steps[]`,
`expected_outputs[]`, `blocked_reasons[]`, `operator_notes[]`, `metadata`.

- `runbook_type` ∈ `commit_runbook`, `push_runbook`, `verification_runbook`,
  `release_check_runbook`, `recovery_runbook`, `general_manual_command`.
- `status` ∈ `drafted`, `ready_for_operator`, `blocked`, `executed_manually`,
  `result_captured`, `verified`, `failed`, `archived`.

## Command step schema — `RunbookCommandStep`

`step_id`, `step_order` (positive int), `title`, `command` (non-empty),
`command_type`, `shell`, `working_directory` (explicit, non-URL),
`requires_manual_copy` (default `true`), `requires_operator_confirmation`
(default `true`), `expected_result_hint`, `risk_level`, `metadata`.

- `command_type` ∈ `git_status`, `git_diff`, `git_add`, `git_commit`,
  `git_fetch`, `git_push`, `test`, `build`, `lint`, `security_scan`,
  `verification`, `informational`, `unknown`.
- `shell` ∈ `powershell`, `cmd`, `bash`, `python`, `manual`.
- `risk_level` ∈ `low`, `medium`, `high`, `critical`.
- The `command` is never executed by SCOS.

## Safety check schema — `ExecutionSafetyCheck`

`check_id`, `title`, `description`, `status`, `severity`, `required`,
`operator_instruction`, `metadata`. Instructions/evidence only — no check runs
a command.

- `status` ∈ `pending`, `passed`, `failed`, `skipped`, `requires_review`.
- `severity` ∈ `info`, `warning`, `error`, `critical`.

## Capture schema — `CommandExecutionCapture`

`ok`, `schema_version`, `capture_id`, `runbook_id`, `session_id`, `task_id`,
`operator_reported_command`, `pasted_output_summary`, `raw_output_excerpt`
(text only), `exit_status_text`, `verdict`, `captured_at`, `evidence_paths[]`
(non-URL), `warnings[]`, `blockers[]`, `metadata`.

- `verdict` ∈ `PASS`, `PASS_WITH_WARNINGS`, `NEEDS_REVIEW`, `NEEDS_FIX`,
  `BLOCKED`, `FAIL`, `UNKNOWN`.

## Outcome schema — `OperatorExecutionOutcome`

`ok`, `schema_version`, `outcome_id`, `runbook_id`, `capture_id`,
`session_id`, `task_id`, `outcome`, `summary`, `recommended_next_action`,
`recommended_next_agent?`, `operator_review_required`, `created_at`,
`metadata`.

- `outcome` ∈ `command_succeeded`, `command_succeeded_with_warnings`,
  `command_failed`, `command_blocked`, `command_needs_review`,
  `command_needs_fix`, `command_unknown`.
- `recommended_next_agent` ∈ `chatgpt`, `claude_code`, `codex`, `hermes`,
  `operator`, or `null`.

## Error schema — `OperatorExecutionError`

`ok` (default `false`), `schema_version`, `error_kind`, `error_detail`,
`failed_step`, `metadata`. Returned by builder functions instead of raising.

## Deterministic ID rules

Every id is `"<prefix>-" + sha256("|".join(stable, normalized, inputs))[:16]`
where `None` normalizes to `""`. Prefixes: runbook `rb-`, step `rbs-`, safety
check `rbc-`, capture `cap-`, outcome `oeo-`. Same inputs → same id. No clock,
no random, no uuid. `created_at` / `captured_at` are caller-supplied.

## Command risk classification

`git_commit` steps are `high`; `git_push` steps are `critical`; git status/diff
/fetch inspection steps are `medium`; generic informational/verification steps
default `low`–`medium`. Risk is advisory metadata for the operator, never a
gate that executes anything.

## Commit runbook template

Six ordered steps (text only):

1. `git status --short --untracked-files=all`
2. `git add <approved staged paths>`
3. `git diff --cached --stat`
4. `git diff --cached --name-only`
5. `git commit -m "<approved commit message>"`
6. `git status -sb`

Default safety checks: confirm branch is main; working tree contains only
expected Stage files; staged files match the approved proposal; commit message
matches the approved proposal; tests were reviewed; operator approval exists;
no push happens during the commit runbook.

## Push runbook template

Eleven ordered steps (text only):

1. `git fetch origin`
2. `git status -sb`
3. `git rev-parse HEAD`
4. `git rev-parse origin/main`
5. `git log --oneline --left-right main...origin/main`
6. `git push <remote_name> <branch_name>`
7. `git fetch origin`
8. `git status -sb`
9. `git rev-parse HEAD`
10. `git rev-parse origin/main`
11. `git log --oneline -6`

Default safety checks: confirm commit exists locally; no remote-only commit
exists; branch is main; HEAD state is understood; push approval exists; no
force push is used; post-push verification will be run.

## Verification runbook template

A `verification_runbook` (or generic `general_manual_command`) built via
`create_manual_command_runbook` from one or more approved commands (e.g.
`.venv\Scripts\python.exe scripts\test_smoke.py`). Steps carry the supplied
shell/working directory; a single default safety check confirms an approval
exists. When no approval backs the runbook, it should be surfaced as `blocked`
with explicit `blocked_reasons`.

## Forbidden behavior

No command execution; no `subprocess` / `os.system` / `pty`; no shell-out; no
terminal emulator; no clipboard read/write; no network / `requests` / `urllib`
/ `socket`; no real git inspection from Stage 5.9; no database; no clock,
random, or uuid; no mutable exposed fields; no secrets stored; no URL paths.

## PASS / BLOCKED / FAIL classification guidance

The classifier lowercases and joins the pasted summary, raw excerpt, and
exit-status text, then applies simple documented rules (not tuned to one
format):

- Empty output → `UNKNOWN`.
- Contains `rejected` or `permission denied` → `BLOCKED` (blocker recorded).
- Contains a failure marker (`error:`, `fatal:`, `failed`) without an explicit
  block → `FAIL`.
- Otherwise, contains a success marker (`nothing to commit`, `[main`,
  `main -> main`, `head == origin/main`, `working tree clean`) → `PASS`, or
  `PASS_WITH_WARNINGS` when warning markers are present.
- Output present but no clear signal → `NEEDS_REVIEW`.

`operator_review_required` stays `true` for every verdict except a clean `PASS`
with no warnings and no blockers.
