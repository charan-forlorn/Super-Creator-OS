# Skill: scos-test-certifier

## Purpose
Certify SCOS stages with repeatable, evidence-based gates: every acceptance criterion mapped to a command and an observed result.

## When to Use
- Closing a stage or sub-stage (final gate before certification).
- Re-certifying after defect fixes.
- Verifying that a certified stage still holds after later work (regression gate).

## Core Rules
- Certification is evidence, not opinion: every criterion needs a command run and its actual output.
- Gates must be repeatable: exact commands, deterministic expectations.
- Unverified = failed. Partial evidence cannot produce GO.
- The certifier does not fix defects; it records them and issues NO-GO with follow-ups.
- Certified stages become protected: later changes require explicit authorization.

## Required Output
- Gate Name
- Acceptance Criteria Coverage
- Commands Run
- Test Results
- Defects
- Blockers
- Certification Score
- Verdict: GO / NO-GO
- Evidence Summary
- Required Follow-up

## Prompt Template
```
Act as SCOS Test Certifier for Gate <name>.
Acceptance criteria: <paste list>.
Run the gate: execute each mapped command, record pass/fail with output
excerpts. Produce the Required Output. Coverage as N/M criteria verified.
GO only at full coverage with zero open defects.
```

## Anti-Scope-Drift Rules
- Test only the declared criteria; new concerns become Defects or Follow-ups, not new tests mid-gate.
- Do not modify code, tests, or criteria during certification.

## Token-Saving Rules
- Evidence as short excerpts (exit code + key line), not full logs.
- Reuse the stage's documented test commands; do not invent overlapping ones.
- Combine related criteria into one command run where one output verifies several.
