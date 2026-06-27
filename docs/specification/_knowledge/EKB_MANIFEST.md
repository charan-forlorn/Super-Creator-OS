# Engineering Knowledge Base — Manifest

> **Status:** ACTIVE (built Phase 2.5). **Location:** `docs/specification/_knowledge/`.
> **Baseline:** `HEAD 6bec9c4` (2026-06-27). **Language:** English canonical.
>
> The EKB is the **connective tissue** between the project's layers (Vision →
> Constitution → Specification → Architecture → Standards → Implementation). It holds
> the *structured, ID-bearing* knowledge atoms that every specification document and
> every AI agent must cite. It does **not** redefine strategy (that is the Vision) or
> governance (that is the Constitution) or implementation truth (that is the repository).

---

## What the EKB is

A deterministic, traceable knowledge layer with three registers and a glossary, all keyed
by stable IDs so that any claim, decision, or capability can be traced to repository
evidence and back.

## File structure

| File | Role | Phase |
|---|---|---|
| `EKB_MANIFEST.md` | This file — index, ID namespaces, usage | 2.5 |
| `EVIDENCE_REGISTER.md` | `EV-xxx` — atomic, repo-verifiable evidence | 2.5 |
| `DECISION_REGISTER.md` | `DD-xxx` — recorded design decisions | 2.5 |
| `CAPABILITY_INVENTORY.md` | `CAP-xxx` — capability spine (atoms) | 2.5 |
| `GLOSSARY.md` | canonical one-definition-per-term store | 2.5 / 2.8 |
| `KNOWLEDGE_AUDIT_REPORT.md` | audit of the EKB + specs | 2.6 |
| `AUTHORITY_MODEL.md` | layer hierarchy & change rights | 2.8 |
| `MATURITY_MODEL.md` | L0–L5 + A/B/C→L mapping | 2.8 |
| `CAPABILITY_REGISTRY.md` | enriched governance record per capability | 2.8 |
| `DOCUMENT_DEPENDENCY_MAP.md` | doc→doc dependencies + graph | 2.8 |
| `KNOWLEDGE_GRAPH.md` | full node/edge knowledge graph | 2.8 |
| `TRACEABILITY_STANDARD.md` | citation rules for all future docs | 2.8 |
| `REPOSITORY_INTELLIGENCE.md` | how AI agents explore the repo | 2.8 |
| `KNOWLEDGE_QUALITY_METRICS.md` | measurable knowledge scores | 2.8 |
| `AI_READINESS.md` | readiness for AI/agent consumption (re-assessed 2.9) | 2.8 |
| `PHASE_2_9_BACKLOG.md` | Repository-Intelligence backlog (built in 2.9) | 2.8 |
| **Repository Intelligence Layer (Phase 2.9)** | | |
| `../_repository_model/REPOSITORY_MODEL.md` | repo structure, lineages, module registry | 2.9 |
| `KNOWLEDGE_RETRIEVAL.md` | canonical retrieval protocol (search order) | 2.9 |
| `AI_QUERY_PROTOCOL.md` | agent query pipeline (8 steps) | 2.9 |
| `CONTEXT_COMPRESSION.md` | L0–L5 context tiers | 2.9 |
| `CHANGE_IMPACT.md` | blast-radius / impact analysis | 2.9 |
| `DOCUMENT_LIFECYCLE.md` | doc state machine + ownership | 2.9 |
| `MEMORY_ACCESS_POLICY.md` | per-role memory read/write rules | 2.9 |
| `PROMPT_PROTOCOL.md` | mandatory prompt structure | 2.9 |
| `knowledge.graph.json` | machine-readable graph (deterministic) | 2.9 |

Sibling: `../_evidence/EVIDENCE_LEDGER.md` — the **narrative** evidence source that the
`EVIDENCE_REGISTER` atomizes. The ledger is prose; the register is indexed atoms.

## ID namespaces

- **`EV-xxx`** — Evidence. One atomic, repository-verifiable fact. Carries path(s),
  verification date, confidence. Source of truth = the repository.
- **`DD-xxx`** — Decision. One recorded design/governance decision. Must cite ≥1 `EV`.
- **`CAP-xxx`** — Capability. One distinct system capability. Cites `EV`/`DD` + paths.

IDs are **append-only and immutable** once minted (per `TRACEABILITY_STANDARD.md`). A
superseded item is marked `SUPERSEDED-BY` — never deleted, never renumbered.

## How to use the EKB

- **Writing a spec doc (Phases 3–13):** every claim cites `EV`/`DD`/`CAP` IDs + repo
  paths (see `TRACEABILITY_STANDARD.md`). No undocumented claims.
- **An AI agent answering a question:** resolve terms via `GLOSSARY.md`, find capabilities
  via `CAPABILITY_REGISTRY.md`, verify any claim against the cited `EV` repo path before
  asserting it as current (see `REPOSITORY_INTELLIGENCE.md`).
- **Assessing readiness:** read `MATURITY_MODEL.md` + `CAPABILITY_REGISTRY.md`.

## Governance position

Per `AUTHORITY_MODEL.md`: the EKB sits **below** Vision and Constitution and **beside**
Specification as its evidentiary substrate. It may be *corrected by repository evidence at
any time* (evidence wins) but may **not** originate strategy or governance.
