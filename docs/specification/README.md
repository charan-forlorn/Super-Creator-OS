# Specification Layer — Super Creator OS

> **Status:** Workspace initialized (Phase 1 complete). Documents below are
> **placeholders** to be populated in sequence by Phases 3–13.
>
> **Authority:** This folder is the single source of truth for every future
> architectural and implementation decision. Where a document here conflicts with
> any other documentation in the repository, **the most recently ratified document
> in this folder wins** — except that all documents here are themselves subordinate
> to **repository evidence** (running code, tests, committed data). If evidence
> contradicts a specification, the evidence is correct and the specification must be
> corrected.

## Method

- **Repository First** — every statement traces to a file, function, commit, or
  audit report in this repo.
- **Evidence Driven** — no invented architecture, no inferred undocumented behavior.
- **Read Before Write** — specifications describe what *is* (and what is explicitly
  *planned* in tracked documents), never what would be nice.
- Where evidence is insufficient, the document says **"Not enough evidence."**

## Document Index

| # | Document | Populated by | Status |
|---|---|---|---|
| 1 | [PROJECT_CONSTITUTION.md](PROJECT_CONSTITUTION.md) | Phase 3 | placeholder |
| 2 | [SYSTEM_SPEC.md](SYSTEM_SPEC.md) | Phase 4 | placeholder |
| 3 | [PRODUCT_SPEC.md](PRODUCT_SPEC.md) | Phase 5 | placeholder |
| 4 | [DESIGN_PRINCIPLES.md](DESIGN_PRINCIPLES.md) | Phase 6 | placeholder |
| 5 | [DOMAIN_MODEL.md](DOMAIN_MODEL.md) | Phase 7 | placeholder |
| 6 | [TERMINOLOGY.md](TERMINOLOGY.md) | Phase 8 | placeholder |
| 7 | [QUALITY_ATTRIBUTES.md](QUALITY_ATTRIBUTES.md) | Phase 9 | placeholder |
| 8 | [NON_FUNCTIONAL_REQUIREMENTS.md](NON_FUNCTIONAL_REQUIREMENTS.md) | Phase 10 | placeholder |
| 9 | [SUCCESS_CRITERIA.md](SUCCESS_CRITERIA.md) | Phase 11 | placeholder |
| 10 | [DECISION_PRINCIPLES.md](DECISION_PRINCIPLES.md) | Phase 12 | placeholder |
| 11 | [ROADMAP.md](ROADMAP.md) | Phase 13 | placeholder |

## Engineering Knowledge Base (`_knowledge/`)

The traceability spine and knowledge-system infrastructure. Specs cite these; agents
consume these. See [_knowledge/EKB_MANIFEST.md](_knowledge/EKB_MANIFEST.md).

| File | Role |
|---|---|
| [_knowledge/EKB_MANIFEST.md](_knowledge/EKB_MANIFEST.md) | Index, ID namespaces, usage |
| [_knowledge/EVIDENCE_REGISTER.md](_knowledge/EVIDENCE_REGISTER.md) | `EV-xxx` atomic evidence |
| [_knowledge/DECISION_REGISTER.md](_knowledge/DECISION_REGISTER.md) | `DD-xxx` design/governance decisions |
| [_knowledge/CAPABILITY_INVENTORY.md](_knowledge/CAPABILITY_INVENTORY.md) | `CAP-xxx` capability spine |
| [_knowledge/CAPABILITY_REGISTRY.md](_knowledge/CAPABILITY_REGISTRY.md) | Capability governance record (Phase 2.8) |
| [_knowledge/GLOSSARY.md](_knowledge/GLOSSARY.md) | Canonical terminology |
| [_knowledge/AUTHORITY_MODEL.md](_knowledge/AUTHORITY_MODEL.md) | Layer hierarchy & change rights (2.8) |
| [_knowledge/MATURITY_MODEL.md](_knowledge/MATURITY_MODEL.md) | L0–L5 maturity + A/B/C map (2.8) |
| [_knowledge/DOCUMENT_DEPENDENCY_MAP.md](_knowledge/DOCUMENT_DEPENDENCY_MAP.md) | Doc dependencies (2.8) |
| [_knowledge/KNOWLEDGE_GRAPH.md](_knowledge/KNOWLEDGE_GRAPH.md) | Full knowledge graph (2.8) |
| [_knowledge/TRACEABILITY_STANDARD.md](_knowledge/TRACEABILITY_STANDARD.md) | Citation rules (2.8) |
| [_knowledge/REPOSITORY_INTELLIGENCE.md](_knowledge/REPOSITORY_INTELLIGENCE.md) | How agents explore the repo (2.8) |
| [_knowledge/KNOWLEDGE_QUALITY_METRICS.md](_knowledge/KNOWLEDGE_QUALITY_METRICS.md) | Knowledge scores (2.8) |
| [_knowledge/AI_READINESS.md](_knowledge/AI_READINESS.md) | AI/agent readiness assessment (2.8) |
| [_knowledge/KNOWLEDGE_AUDIT_REPORT.md](_knowledge/KNOWLEDGE_AUDIT_REPORT.md) | Phase 2.6 audit findings |
| [_knowledge/PHASE_2_9_BACKLOG.md](_knowledge/PHASE_2_9_BACKLOG.md) | Repository-Intelligence backlog (built in 2.9) |

## Repository Intelligence Layer (`_repository_model/` + `_knowledge/`, Phase 2.9)

AI-native layer so agents query the EKB first and the repository only to verify.

| File | Role |
|---|---|
| [_repository_model/REPOSITORY_MODEL.md](_repository_model/REPOSITORY_MODEL.md) | Repo structure, two lineages, module registry |
| [_knowledge/KNOWLEDGE_RETRIEVAL.md](_knowledge/KNOWLEDGE_RETRIEVAL.md) | Canonical retrieval protocol (search order) |
| [_knowledge/AI_QUERY_PROTOCOL.md](_knowledge/AI_QUERY_PROTOCOL.md) | 8-step agent query pipeline |
| [_knowledge/CONTEXT_COMPRESSION.md](_knowledge/CONTEXT_COMPRESSION.md) | L0–L5 context tiers |
| [_knowledge/CHANGE_IMPACT.md](_knowledge/CHANGE_IMPACT.md) | Blast-radius / impact analysis |
| [_knowledge/DOCUMENT_LIFECYCLE.md](_knowledge/DOCUMENT_LIFECYCLE.md) | Doc state machine + ownership |
| [_knowledge/MEMORY_ACCESS_POLICY.md](_knowledge/MEMORY_ACCESS_POLICY.md) | Per-role memory access rules |
| [_knowledge/PROMPT_PROTOCOL.md](_knowledge/PROMPT_PROTOCOL.md) | Mandatory prompt structure |
| [_knowledge/knowledge.graph.json](_knowledge/knowledge.graph.json) | Machine-readable graph (deterministic) |

## Authority

Document precedence is defined in [_knowledge/AUTHORITY_MODEL.md](_knowledge/AUTHORITY_MODEL.md):
Vision → Constitution → Specification → Architecture → Standards → Implementation →
Testing → Deployment → Operations. All claims must cite Evidence/Decision/Capability IDs
per [_knowledge/TRACEABILITY_STANDARD.md](_knowledge/TRACEABILITY_STANDARD.md).

## Primary evidence base

- `source/_Super Creator OS V.1.md` — original mission/vision/principles
- `project_audit/*.md` — 12 read-only audit reports (architecture, memory,
  learning loop, video intelligence, testing, security, performance, git,
  merge readiness, production readiness, next steps, project health)
- `skills/*/SKILL.md` — the 6 skill/role contracts and the orchestrator
- `memory/schema.md`, `memory/schema_v2_extension.md` — data contracts
- `workflow-map.md` — the 15-step pipeline
