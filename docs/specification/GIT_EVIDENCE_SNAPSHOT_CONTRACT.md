# Git Evidence Snapshot Contract (Stage 5.8)

## Purpose

Defines how caller-supplied facts about local git and test state become a
deterministic `GitEvidenceSnapshot` or `PushReadinessSnapshot`, via
`scos/control_center/git_evidence_snapshot.py`. This module is the only
place Stage 5.8 accepts raw evidence dicts (changed files, test results) and
turns them into validated model instances — it never inspects the real
repository itself.

## Required Evidence Inputs

`build_git_evidence_snapshot(...)` requires:

- `task_id`, `session_id` — non-empty caller identifiers.
- `source_intake_id` — optional Stage 5.7 `AIResultIntakeRecord.intake_id`
  reference, or `None`.
- `branch` — must be exactly `"main"` (`invalid_branch` otherwise).
- `head_commit`, `origin_main_commit` — non-empty commit references
  (typically the output of `git rev-parse HEAD` /
  `git rev-parse origin/main`, supplied by the caller).
- `is_clean_before_stage` — whether the working tree was clean before this
  stage started (typically from `git status --short`).
- `has_remote_only_commits` — whether `origin/main` has commits not present
  locally; `True` always rejects the snapshot (`remote_only_commits`).
- `changed_files` — a tuple of dicts with at least `path`; must not be empty
  (`empty_required_field` otherwise, since an empty change set can never
  become a commit-proposal-ready snapshot).
- `test_evidence` — a tuple of dicts with at least `status`; must include at
  least one entry with `status == "passed"` (`missing_test_evidence`
  otherwise).
- `created_at` — a non-empty, caller-supplied timestamp string.

## Changed File Model

Each `changed_files` entry becomes a `GitChangedFile`:

- `path` must be repo-relative: no leading `/` or `\`, no drive-letter
  prefix (e.g. `C:`), and no URL scheme (`://`) anywhere in the string.
  Violations return `invalid_file_path`.
- `change_type` must be one of `added`, `modified`, `deleted`, `renamed`,
  `copied`, `unknown`.
- `staged` defaults to `False`; `summary` is a required non-empty string.

## Test Evidence Model

Each `test_evidence` entry becomes a `GitTestEvidence`:

- `status` must be one of `passed`, `failed`, `skipped`, `unknown`.
- `passed_count`, `failed_count`, `warning_count` must be non-negative
  integers.
- `output_path` is optional and, if present, must not be a URL.

`risk_flags` on the resulting snapshot are derived, not caller-supplied:
`unsafe_git_state` is added when `is_clean_before_stage` is `False`;
`failed_tests` is added when any test evidence entry has
`status == "failed"`.

## Remote Safety Fields

`has_remote_only_commits` is the single authoritative "is it safe to build
on top of this branch" flag for both `GitEvidenceSnapshot` and
`PushReadinessSnapshot`. Any `True` value always rejects the corresponding
snapshot/proposal build — Stage 5.8 never attempts to reconcile or fetch
remote state itself; the caller (operator or an earlier stage) is
responsible for supplying an accurate value from `git fetch` +
`git rev-list` evidence.

`build_push_readiness_snapshot(...)` additionally requires:

- `branch == "main"` (`invalid_branch` otherwise).
- `ahead_by`, `behind_by` — non-negative integers.
- `working_tree_clean`, `latest_commit_message` — caller-supplied state used
  later by `build_push_proposal` to decide whether a push may be proposed
  (requires `ahead_by >= 1`, `behind_by == 0`,
  `has_remote_only_commits is False`, `working_tree_clean is True`).

## Local-Only Validation Policy

Every check in this module is a pure Python comparison against
caller-supplied strings/booleans/ints. There is no filesystem read, no
environment variable read, no clock read, and no random/uuid generation.
Deterministic ids (`snapshot_id`, `push_snapshot_id`) are `sha256` digests of
the caller-supplied fields, so identical inputs always produce identical
snapshots.

## No Subprocess / No Mutation Policy

`git_evidence_snapshot.py` never imports `subprocess`, never calls
`os.system`, never writes a file, and never calls a network or GitHub API.
Its only job is validating and shaping data the caller already gathered
(e.g. from running `git status`/`git rev-parse`/a test suite themselves) —
gathering that evidence remains an operator or upstream-stage
responsibility, entirely outside this module.
