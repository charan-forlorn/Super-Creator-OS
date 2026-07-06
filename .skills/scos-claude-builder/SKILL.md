# Skill: scos-claude-builder

## Purpose
Generate implementation prompts optimized for Claude Code: exact scope, exact files, exact tests, exact report format.

## When to Use
- Architecture is approved and a stage/task needs to be built.
- A defect fix has been authorized and needs a minimal, scoped build prompt.
- Handing work from ChatGPT (PM/architect) to Claude Code.

## Core Rules
- Every build prompt starts with the Git preflight gate (see scos-git-safety-gate).
- Scope = exact file paths, split into Allowed and Forbidden.
- Builder implements and tests but never certifies or approves its own work.
- No hidden broad refactor: touch only listed files; report anything else needed.
- No network/API/timer/fetch unless the stage explicitly requires it.
- Prefer static/mock UI before real integration.
- The prompt must define the exact Final Report Format so output is machine-comparable.

## Required Output
- Stage Name
- Context
- Objective
- Preflight
- Scope
- Files to Inspect
- Implementation Tasks
- Test Commands
- Acceptance Criteria
- Forbidden Actions
- Final Report Format

## Prompt Template
```
Act as SCOS Build Prompt Generator.
Stage: <N>. Approved design: <paste or reference architecture output>.
Emit a single Claude Code prompt containing the Required Output sections.
Context max 5 lines. Tasks numbered and file-scoped. Forbidden Actions must
include: no commit/push without authorization, no dependency changes,
no edits outside Scope, no test deletion.
```

## Anti-Scope-Drift Rules
- Each Implementation Task names its target file(s); taskless files and fileless tasks are both errors.
- If mid-build a needed change falls outside Scope: stop, report, await re-scope.
- Never fold "improvements" into the prompt beyond the approved design.

## Token-Saving Rules
- Context section is a 5-line max summary; link docs instead of pasting them.
- Files to Inspect is the minimal read set, not the whole module.
- Test Commands: minimal set for the task plus one full-gate command, nothing more.
