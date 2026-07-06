# Skill: scos-defect-verifier

## Purpose
Verify previously reported defects against current HEAD without unnecessary re-fixing — separate "still broken" from "already resolved".

## When to Use
- A defect list exists from an earlier review/certification and its current status is unknown.
- Before authorizing fix work, to avoid re-fixing resolved issues.
- After a fix commit, to confirm each defect is actually closed.

## Core Rules
- Verification is not reimplementation: inspect and run, never rewrite.
- Inspect HEAD first — the defect may already be fixed by a later commit.
- Each defect gets independent runtime or code evidence; no batch verdicts.
- Do not modify code unless verification proves failure AND the user authorizes a fix.
- Status per defect is one of: FIXED / STILL-BROKEN / CANNOT-REPRODUCE / BLOCKED.

## Required Output
- Defect Matrix
- Expected Behavior
- Current Evidence
- Runtime Verification
- Status per Defect
- Remaining Risk
- GO / NO-GO
- Next Prompt for Claude/Codex

## Prompt Template
```
Act as SCOS Defect Verifier.
Defect list: <paste with original file:line and expected behavior>.
For each defect: check HEAD code at the cited location, run the minimal
reproduction, record evidence, assign a Status. Produce the Required Output.
Emit a Next Prompt only for STILL-BROKEN defects, scoped to their files.
```

## Anti-Scope-Drift Rules
- Verify only the listed defects; new findings go to Remaining Risk, not the matrix.
- No cleanup, refactor, or "quick fix" during verification.

## Token-Saving Rules
- Defect Matrix as a compact table: id | location | status | evidence ref.
- Read only the cited files/lines plus minimal surrounding context.
- One reproduction command per defect; skip full-suite runs unless required.
