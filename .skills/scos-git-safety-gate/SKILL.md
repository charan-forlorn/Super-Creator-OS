# Skill: scos-git-safety-gate

## Purpose
Enforce a safe Git state before implementation, commit, and push — the mandatory first step of every build/review/release task.

## When to Use
- At the start of every build, review, verification, or release task.
- Before any commit or push.
- After any interrupted or failed session, before resuming work.

## Core Rules
- Run all Required Checks; never assume state from memory or a previous turn.
- Proceed only if: branch is the expected one, HEAD == origin/main (or the declared base), and the working tree is clean — unless the task explicitly expects dirty state (e.g., pre-commit review).
- Never commit or push without explicit user authorization.
- Never force-push, hard-reset, or discard changes without explicit user authorization.
- On any mismatch: report exact values and BLOCKED; do not modify files.

## Required Checks
```
git fetch origin
git branch --show-current
git status --short --untracked-files=all
git rev-parse HEAD
git rev-parse origin/main
git log --oneline -5
```

## Required Output
- Branch
- HEAD
- origin/main
- Sync Status
- Working Tree Status
- Risk
- Proceed / Blocked
- Next Command

## Prompt Template
```
Act as SCOS Git Safety Gate.
Expected branch: <branch>. Expected base: origin/main. Expected tree: <clean|dirty-with-stage-changes>.
Run the Required Checks and emit the Required Output. If any expectation
fails, output Blocked with the exact mismatch and stop.
```

## Anti-Scope-Drift Rules
- This gate only reports and blocks; it never fixes Git state on its own.
- No branch creation, stash, or cleanup unless the user authorizes it as the Next Command.

## Token-Saving Rules
- Output raw command values, one line each — no narration.
- Skip `git log` detail in the report unless there is a mismatch to explain.
