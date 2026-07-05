# Git Commit / Push Approval Gate Contract (Stage 5.8)

## Purpose

Defines the deterministic, local-only shape for turning an approved AI
result / operator evidence into a safe commit and push **proposal** that an
operator reviews and approves before ever typing a real git command. This
stage is the approval/proposal layer only: it produces `CommitProposal`,
`CommitApprovalDecision`, `PushProposal`, and `PushApprovalDecision` objects
plus an append-only `GitApprovalEvent` timeline — it never runs `git add`,
`git commit`, `git push`, creates a tag/release, or calls a network/GitHub
API.

## Scope

- Modeling a `GitEvidenceSnapshot` of local git/test state (branch, HEAD,
  origin/main, changed files, test evidence, risk flags).
- Building a `CommitProposal` from that snapshot with a conventional-commit
  message, sorted file list, evidence/test summaries, and a computed risk
  level.
- Recording an operator `CommitApprovalDecision` (approved / rejected /
  needs_changes / blocked), with inert `git add` + `git commit` guidance text
  produced only when approved.
- Modeling a `PushReadinessSnapshot` (ahead/behind counts, remote-only-commit
  flag, working-tree-clean flag).
- Building a `PushProposal` — always exactly `git push origin main`, gated on
  an approved commit decision and a safe push-readiness snapshot.
- Recording an operator `PushApprovalDecision`, with inert `git push origin
  main` guidance text produced only when approved.
- An append-only `GitApprovalEvent` JSONL timeline via `GitApprovalStore`.

## Non-goals

No real git execution (no `git add`/`commit`/`push`/`tag`/`stash`/`reset`/
`rebase`/`merge`/`clean`/`checkout`), no subprocess, no GitHub API, no
network, no browser/GUI/clipboard automation, no backend server, no API
routes, no database, no WebSocket, no polling, no timers, no background
workers, no live remote monitoring.

## Data Models

Defined in `scos/control_center/git_approval_models.py`
(`GIT_APPROVAL_SCHEMA_VERSION = 1`):

- `GitChangedFile` — repo-relative `path`, `change_type`
  (added/modified/deleted/renamed/copied/unknown), `staged`, `summary`,
  `metadata`. Rejects absolute paths, drive-letter paths, and URL-like paths.
- `GitTestEvidence` — `evidence_id`, `command_label`, `status`
  (passed/failed/skipped/unknown), `summary`, `passed_count`,
  `failed_count`, `warning_count`, optional `output_path`, `metadata`.
- `GitEvidenceSnapshot` — `snapshot_id`, `task_id`, `session_id`, optional
  `source_intake_id` (a Stage 5.7 `AIResultIntakeRecord.intake_id`),
  `branch`, `head_commit`, `origin_main_commit`,
  `is_clean_before_stage`, `has_remote_only_commits`, tuples of
  `changed_files`/`test_evidence`, `risk_flags`, `created_at`, `metadata`.
- `CommitProposal` — `proposal_id`, `snapshot_id`, `commit_message` (single
  line, conventional-commit style), `commit_title`, `commit_body`, sorted
  `files_to_commit`, `evidence_summary`, `test_summary`, `risk_level`
  (low/medium/high/blocked), `approval_required` (always `True`),
  `proposed_at`, `metadata`.
- `CommitApprovalDecision` — `decision_id`, `proposal_id`, `decision`
  (approved/rejected/needs_changes/blocked), `decided_by`, `decided_at`,
  `reason`, optional `manual_command` (guidance text, present only when
  `decision == "approved"`), `metadata`.
- `PushReadinessSnapshot` — `push_snapshot_id`, `branch`, `head_commit`,
  `origin_main_commit`, `ahead_by`, `behind_by`, `has_remote_only_commits`,
  `working_tree_clean`, `latest_commit_message`, `created_at`, `metadata`.
- `PushProposal` — `push_proposal_id`, `commit_decision_id`,
  `push_snapshot_id`, `branch` (always `"main"`), `remote` (always
  `"origin"`), `refspec` (always `"main"`), `proposed_command` (always
  exactly `"git push origin main"`), `risk_level`, `approval_required`
  (always `True`), `proposed_at`, `metadata`.
- `PushApprovalDecision` — `push_decision_id`, `push_proposal_id`,
  `decision`, `decided_by`, `decided_at`, `reason`, optional
  `manual_command` (always exactly `"git push origin main"` when present),
  `metadata`.
- `GitApprovalEvent` — `event_id`, `event_type` (one of
  `git_evidence_snapshot_created` / `commit_proposal_created` /
  `commit_approval_recorded` / `push_readiness_snapshot_created` /
  `push_proposal_created` / `push_approval_recorded` / `git_gate_blocked`),
  `task_id`, `session_id`, `related_id`, `summary`, `created_at`, `metadata`.
- `GitApprovalError` — a structured rejection (`error_kind`, `error_detail`,
  `failed_stage`, `metadata`), returned instead of raising for every expected
  validation failure.

All dataclasses are frozen; collections are tuples; `metadata` is a
`FrozenMap` (reused from `operator_packet_review_models.FrozenMap`, per the
existing Stage 5.5 convention). `to_dict()` uses explicit key order and
serializes tuples as lists and `FrozenMap` as a plain dict.

## State Flow

```
Approved AI result / operator evidence
        -> build_git_evidence_snapshot(...)   [git_evidence_snapshot.py]
        -> GitEvidenceSnapshot
        -> build_commit_proposal(...)         [git_approval_builder.py]
        -> CommitProposal
        -> record_commit_approval_decision(...)
        -> CommitApprovalDecision
        -> build_push_readiness_snapshot(...) [git_evidence_snapshot.py]
        -> PushReadinessSnapshot
        -> build_push_proposal(...)           [git_approval_builder.py]
        -> PushProposal
        -> record_push_approval_decision(...)
        -> PushApprovalDecision
        -> build_git_approval_event(...) at each step -> GitApprovalStore
        -> Static Control Center UI
```

## Commit Proposal Rules

- `commit_message` must start with one of: `feat(`, `fix(`, `docs(`,
  `test(`, `chore(`, `refactor(`, `perf(`, `build(`, `ci(`.
- `commit_message` must be a single line (no `\n`).
- `commit_message` must not contain shell operators: `&&`, `||`, `;`, `|`,
  `>`, `<`, `` ` ``, `$`.
- `files_to_commit` is derived from `snapshot.changed_files`, sorted by path.
- The proposal is rejected (`missing_test_evidence`) if the snapshot has no
  `GitTestEvidence` entry with `status == "passed"`.
- The proposal is rejected (`remote_only_commits`) if
  `snapshot.has_remote_only_commits` is `True`.
- The proposal is rejected (`blocked_risk`) if `snapshot.risk_flags` contains
  any of `critical`, `unsafe_git_state`, `missing_tests`,
  `remote_only_commits`.
- `risk_level` is computed deterministically: `blocked` (handled via
  rejection above) > `high` (any failed test evidence) > `medium` (any test
  evidence with `warning_count > 0`) > `low` (otherwise).

## Commit Approval Rules

- Only `decision == "approved"` produces a `manual_command`:
  `git add <files>` followed by `git commit -m "<commit_message>"`.
- `rejected` / `needs_changes` / `blocked` decisions always have
  `manual_command is None`.
- `record_commit_approval_decision` never executes the manual command it
  produces — it is guidance text only.

## Push Proposal Rules

- Requires `commit_decision.decision == "approved"` (`missing_approval`
  otherwise).
- Requires `push_snapshot.branch == "main"`, `ahead_by >= 1`,
  `behind_by == 0`, `has_remote_only_commits is False`, and
  `working_tree_clean is True` (`invalid_branch` / `unsafe_push` /
  `dirty_worktree` / `remote_only_commits` otherwise).
- `proposed_command` is always exactly `git push origin main`; the model
  layer rejects any other string (no `--force`, `--force-with-lease`, tags,
  or releases can ever be represented).

## Push Approval Rules

- Only `decision == "approved"` produces `manual_command`, always exactly
  `git push origin main`.
- `rejected` / `needs_changes` / `blocked` decisions always have
  `manual_command is None`.
- `record_push_approval_decision` never executes the manual command it
  produces.

## Safety Rules

- No function in `git_approval_models.py`, `git_evidence_snapshot.py`,
  `git_approval_builder.py`, or `git_approval_store.py` calls `subprocess`,
  `os.system`, or any process/shell execution API.
- Every git-fact field (branch, commit hashes, ahead/behind counts, clean
  flags) is caller-supplied; this stage never inspects the real repository.
- `git push origin main` and `git commit -m "..."` only ever exist as
  string values on frozen dataclasses — never passed to an execution layer.

## Forbidden Operations

`git add`, `git commit`, `git push`, `git tag`, `gh release`, `git stash`,
`git reset`, `git rebase`, `git merge`, `git clean`, `git checkout` (branch
switching), force push, and any GitHub/network API call.

## Deterministic ID Rules

Every id is a `sha256`-derived, caller-input-stable string — no clock, no
random, no uuid is ever read:

- `snapshot_id = "ges-" + sha256(task_id|session_id|branch|head_commit|origin_main_commit|created_at)[:16]`
- `push_snapshot_id = "prs-" + sha256(branch|head_commit|origin_main_commit|ahead_by|behind_by|created_at)[:16]`
- `proposal_id = "cp-" + sha256(snapshot_id|commit_message|proposed_at)[:16]`
- `decision_id = "cad-" + sha256(proposal_id|decision|decided_by|decided_at)[:16]`
- `push_proposal_id = "pp-" + sha256(commit_decision_id|push_snapshot_id|proposed_at)[:16]`
- `push_decision_id = "pad-" + sha256(push_proposal_id|decision|decided_by|decided_at)[:16]`
- `event_id = "gae-" + sha256(event_type|related_id|created_at)[:16]`

Identical inputs always produce identical ids.

## Operator-Only Execution Rule

Every "command" this stage produces (`manual_command` on
`CommitApprovalDecision`/`PushApprovalDecision`) is inert guidance text for a
human operator to type into their own terminal. No function in this stage
ever invokes a subprocess, shell, or command runner with that text. Actual
`git add`/`git commit`/`git push` execution remains entirely operator-
controlled unless a future, explicitly approved command-bridge stage adds
allowlisted execution (mirroring Stage 5.1's `run_approved_command`
pattern, but that is out of scope here).

## Relation to Stage 5.1 / 5.7

Stage 5.8 sits after Stage 5.7 (AI Result Intake & ChatGPT Status Update
Loop) and reuses Stage 5.1's "draft -> approval -> allowlisted execution"
philosophy conceptually, but does not import Stage 5.1 models directly —
`GitEvidenceSnapshot.source_intake_id` accepts a Stage 5.7
`AIResultIntakeRecord.intake_id` only as a plain string reference. Stage 5.8
never imports or mutates Stage 5.1-5.7 models directly, and never touches
`scos.commercial` or `scos.knowledge`.
