# Skill: scos-doc-writer

## Purpose
Create concise, evidence-based SCOS documentation: stage plans, scope boundaries, certification reports, handoffs, and changelogs.

## When to Use
- A stage opens (Stage Plan, Scope Boundary, Acceptance Criteria).
- A stage closes (Certification Report, Changelog, Release Readiness).
- Work moves between agents or sessions (Handoff, Review Notes).

## Supported Document Types
Stage Plan · Scope Boundary · Acceptance Criteria · Certification Report · Handoff · Review Notes · Changelog · Release Readiness

## Core Rules
- Every claim is backed by evidence: a command, a commit hash, or a file path.
- Documents state what IS, decisions made, and what's next — no speculation.
- One document, one purpose; do not merge document types.
- Convert relative dates to absolute; name exact commits and files.
- Documents live under docs/ following existing project layout; never modify runtime code while documenting.

## Required Output
- Summary
- Scope
- Evidence
- Decisions
- Risks
- Status
- Next Step

## Prompt Template
```
Act as SCOS Doc Writer.
Document type: <type>. Stage: <N>. Source material: <reports/diffs/commits>.
Produce the Required Output sections as the document body. Max 1 page.
Every Evidence line cites a command, commit, or path.
```

## Anti-Scope-Drift Rules
- Document only the stated stage/event; no retro-editing of other documents.
- No new decisions invented while writing — record only decisions already made.

## Token-Saving Rules
- One page maximum; bullets over prose.
- Link to prior documents instead of restating them.
- Evidence as references (command + result line), not pasted logs.
