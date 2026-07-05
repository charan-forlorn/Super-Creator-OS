# AI Result Intake Contract (Stage 5.7)

## Purpose

Defines the deterministic, local-only shape for taking a pasted/imported
result from Claude Code, Codex, Hermes, ChatGPT, or the operator, and turning
it into a normalized `AIResultIntakeRecord`. This is a manual-handoff intake
layer: no result is fetched automatically, no clipboard is read, and no AI
agent is dispatched by any function documented here.

## Models

Defined in `scos/control_center/result_intake_models.py`:

- `ResultIntakeArtifact` — one piece of evidence attached to an intake
  (artifact id/type/title/path/summary/sha256/required/metadata).
- `AIResultIntakeRecord` — the normalized intake: session/task ids, source
  agent + runtime, optional links back to a Stage 5.4 prompt/result packet,
  raw + normalized summary, verdict, confidence, artifacts, blockers,
  warnings, tests/changed-files summaries, `operator_review_required`,
  timestamps, and status.
- `AIResultIntakeError` — a structured rejection (`error_kind`,
  `error_detail`, `failed_step`, optional `intake_id`).

All fields are validated against fixed allow-lists
(`ALLOWED_SOURCE_AGENTS`, `ALLOWED_VERDICTS`, `ALLOWED_CONFIDENCE_LEVELS`,
`ALLOWED_INTAKE_STATUSES`, `ALLOWED_ARTIFACT_TYPES`,
`ALLOWED_INTAKE_ERROR_KINDS`). Every dataclass is frozen; collections are
tuples; `metadata` is a `FrozenMap` (reused from
`operator_packet_review_models.FrozenMap`, per the existing Stage 5.5
convention — no new map class was introduced). `to_dict()` uses explicit key
order and serializes tuples as lists and `FrozenMap` as a plain dict.

`source_agent="operator"` means a manual pasted/imported result source only —
it is never an automated agent runtime.

## Verdict Classification

`result_intake_builder.classify_verdict(raw_text)` applies a strict,
case-insensitive keyword precedence over the raw result text:

```
BLOCKED > FAIL > NEEDS_FIX > PARTIAL > PASS
```

- The first matching tier wins (e.g. text containing both a FAIL marker and a
  NEEDS_FIX marker classifies as FAIL).
- Text with no recognizable marker, but with enough content to have been
  read, classifies as `NEEDS_REVIEW`.
- Near-empty or unreadable text (fewer than 3 non-whitespace characters)
  classifies as `UNKNOWN`.

`operator_review_required` is always `true` for `BLOCKED`, `FAIL`,
`NEEDS_FIX`, `NEEDS_REVIEW`, and `UNKNOWN`, and also `true` whenever any
blocker line was extracted, regardless of verdict.

## Deterministic ID Rules

Every id in this stage is a `sha256`-derived, caller-input-stable string —
no clock, no random, no uuid is ever read:

- `intake_id = "ri-" + sha256(session_id|task_id|source_agent|source_runtime_id|title|raw_result_text|created_at)[:16]`
- `update_packet_id = "cgu-" + sha256(intake_id|target_runtime_id|requested_chatgpt_action|created_at)[:16]`
- `state_update_id = "psu-" + sha256(intake_id|previous_stage|current_stage|updated_at)[:16]`
- `next_action_id = "nad-" + sha256(intake_id|created_at)[:16]`

Identical inputs always produce identical ids; this makes the JSONL store
idempotent-friendly for replay/debugging.

## Manual Intake Flow

```
Agent / Operator result text (pasted/imported by the operator)
        -> build_result_intake_record(...)        [result_intake_builder.py]
        -> AIResultIntakeRecord
        -> build_chatgpt_status_update_packet(...) [result_intake_builder.py]
        -> build_project_state_update(...)         [result_intake_builder.py]
        -> build_next_action_decision(...)         [result_intake_builder.py]
        -> ResultIntakeStore.append_*(...)          [result_intake_store.py]
        -> Static Control Center UI
```

Every step is a pure function or a local append; no step in this chain calls
a network API, opens a browser/app, automates a GUI, or reads/writes a
clipboard.

## No AI Dispatch / Clipboard / Network

- `result_intake_builder.py`, `result_intake_models.py`,
  `result_intake_store.py`, `chatgpt_status_update.py`, and
  `project_state_update.py` contain no HTTP client, subprocess call,
  clipboard API, browser automation, or background worker.
- URL-like artifact paths (`http://`, `https://`) are rejected at
  `ResultIntakeArtifact` construction time.
- Metadata keys containing secret-bearing markers (`api_key`, `token`,
  `secret`, `password`, `private_key`) are rejected by `FrozenMap.of(...)`.

## Operator Review Rule

`AIResultIntakeRecord.operator_review_required` is the single source of
truth for whether a human must look at a result before it proceeds. The
Stage 5.7 UI always surfaces this flag; no downstream artifact (ChatGPT
status update packet, project state update, next action decision) is ever
auto-approved on the record's behalf.

## Error Model

Every builder function returns either the requested model instance or an
`AIResultIntakeError` (never raises for expected validation failures).
`error_kind` is one of `ALLOWED_INTAKE_ERROR_KINDS`
(`invalid_source_agent`, `invalid_artifact_type`, `invalid_verdict`,
`invalid_confidence`, `invalid_status`, `invalid_target_agent`,
`invalid_chatgpt_action`, `invalid_task_status`, `invalid_stage_status`,
`invalid_recommended_action`, `invalid_priority`, `missing_required_field`,
`empty_required_field`, `unsafe_path`, `unsafe_metadata`,
`invalid_collection_type`, `contract_violation`).

## JSONL Store Contract

`scos/control_center/result_intake_store.py` defines `ResultIntakeStore`, a
class rooted at a caller-supplied `root_dir` (str or `Path`; URL-like roots
are rejected). It manages four append-only JSONL files:

- `result_intake.jsonl`
- `chatgpt_status_updates.jsonl`
- `project_state_updates.jsonl`
- `next_action_decisions.jsonl`

Rules:

- One deterministic JSON object per line:
  `json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))`.
- Directories are created lazily, only on the first `append_*` call.
  `list_*` methods never create a directory or file — a missing file reads
  as an empty tuple.
- A malformed JSONL line raises a deterministic `ValueError` naming the line
  number and the specific record type that failed to parse.
- UTF-8 only, no file locks, no SQLite, no server, no background worker.
