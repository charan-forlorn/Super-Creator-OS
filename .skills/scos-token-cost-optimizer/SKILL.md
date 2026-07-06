# Skill: scos-token-cost-optimizer

## Purpose
Reduce token usage and development cost: compress prompts, merge micro-stages, route work to the right agent, and shrink read/test sets.

## When to Use
- Prompts or stage plans have grown repetitive and expensive.
- Planning a stage that risks splitting into many micro-stages.
- Auditing why recent sessions burned excessive context.

## Core Rules
- Prefer exact file scopes over "look around the codebase".
- Remove repeated background — state it once in a doc, reference it thereafter.
- Combine related verification tasks when safe; avoid micro-stages unless risk requires separation.
- Never trade away safety gates (preflight, review, certification) for token savings.
- Optimization must not change scope or acceptance criteria — only how compactly they are expressed.

## Required Output
- Current Token Waste Sources
- Prompt Compression
- Stage Compression
- Agent Routing
- Files to Inspect First
- Files to Avoid
- Minimal Test Set
- Full Gate Test Set
- Optimized Prompt

## Prompt Template
```
Act as SCOS Token Cost Optimizer.
Input: <current prompt / stage plan / session pattern>.
Produce the Required Output. Waste sources ranked by cost. Optimized Prompt
must preserve every gate, scope rule, and acceptance criterion of the input.
```

## Anti-Scope-Drift Rules
- Optimize only the given prompt/plan; do not restructure the project.
- Stage merging requires equal-or-better gate coverage, stated explicitly.
- Files to Avoid is advisory scoping, never a license to skip required checks.

## Token-Saving Rules
- Output the optimized prompt, not a diff narrative about it.
- One line per waste source with its estimated saving.
- Minimal Test Set for iteration; Full Gate Test Set reserved for certification.
