# Prompt Engineering Standard

> **Status:** ACTIVE (Phase 2.9.8). Every future prompt (skills, agents, sub-agents,
> one-off task prompts) must follow this structure. Prevents inconsistent prompt shapes and
> makes prompts auditable against the EKB. Governance: `AUTHORITY_MODEL.md`; pairs with
> `AI_QUERY_PROTOCOL.md`.

---

## 1. Mandatory prompt structure (9 sections, in order)

| # | Section | Must contain |
|---|---|---|
| 1 | **Role** | The agent's identity/role (per `CAPABILITY_REGISTRY.md` owner roles where applicable) |
| 2 | **Goal** | The single outcome, measurable where possible |
| 3 | **Context** | Relevant EKB facts (cite `EV`/`DD`/`CAP`), not raw repo dumps |
| 4 | **Inputs** | Exact inputs + their sources/paths |
| 5 | **Constraints** | Hard rules: offline (DD-006), additive (DD-001), memory safety (DD-002), no fabrication |
| 6 | **Reasoning Rules** | How to think: follow `AI_QUERY_PROTOCOL.md`; classify→retrieve→validate |
| 7 | **Validation** | Self-checks before output (cross-reference, traceability) |
| 8 | **Expected Output** | Format, required citations, confidence label |
| 9 | **Failure Behaviour** | What to do when blocked: "Not enough evidence", never invent |

A prompt missing any section is **non-compliant** and must be revised before use.

## 2. Template

```
ROLE:        <who the agent is>
GOAL:        <single measurable outcome>
CONTEXT:     <EKB facts with EV/DD/CAP citations; link docs, don't paste repo>
INPUTS:      <inputs + sources/paths>
CONSTRAINTS: offline-first (DD-006); additive-only (DD-001); memory via safe path (DD-002);
             observed-only telemetry (DD-003); cite per TRACEABILITY_STANDARD; no fabrication
REASONING:   classify → retrieve (KNOWLEDGE_RETRIEVAL order) → validate evidence →
             verify repo only to confirm → construct answer
VALIDATION:  every EV/DD/CAP/term/path resolves; intent vs fact separated; confidence set
OUTPUT:      <format>; inline citations; confidence label; caveats (stale/lineage-B)
FAILURE:     if unresolved → "Not enough evidence" + what would resolve it; never guess
```

## 3. Alignment with existing skills

The 6 existing skill prompts (`skills/*/SKILL.md`, EV-012) predate this standard. They are
**not rewritten** here (non-destructive). When any skill is next revised, it should be
brought into this structure. New prompts must comply from creation.

## 4. Anti-patterns (forbidden)

- ❌ Pasting large repository source into Context instead of citing EKB facts.
- ❌ Omitting Failure Behaviour (leads to fabrication under pressure).
- ❌ Mixing intent and fact without separation (violates `AUTHORITY_MODEL.md` §3).
- ❌ Output without citations or confidence (violates `TRACEABILITY_STANDARD.md`).
- ❌ Instructing direct memory writes (violates DD-002 / `MEMORY_ACCESS_POLICY.md`).

## 5. Compliance check

A prompt is compliant when all 9 sections are present, Context cites ≥1 `EV`/`DD`/`CAP`,
Constraints include the offline + additive + memory-safety rules, and Failure Behaviour
forbids fabrication. This check is part of the `DOCUMENT_LIFECYCLE.md` Review gate for any
prompt-bearing document.
