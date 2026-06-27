# Glossary — Canonical Terminology

> **Status:** ACTIVE (seeded Phase 2.5, finalized Phase 2.8). The **single** home for
> engineering vocabulary. **One official term, one definition.** Synonyms are listed only
> to redirect to the official term. `TERMINOLOGY.md` (Phase 8 spec) will be a spec-facing
> view that points here — there must never be two competing definitions (per
> `TRACEABILITY_STANDARD.md`).
>
> Rule: if a term is used in any spec/EKB doc and matters, it has exactly one entry here.

## Core system terms

| Term (official) | Definition | Not to be called |
|---|---|---|
| **Super Creator OS** | The whole system: a local-first, offline AI Creative Studio that turns a brief + assets into platform-ready short-form video and a memory record. (EV-001) | "the app", "AutoNEX" (historical name) |
| **Creative Director (role)** | The AI's primary role: it directs, plans, and critiques; it does not render. (EV-002, DD-008) | "the editor AI" |
| **Execution layer** | The video half: ffmpeg + numpy code that ingests, analyzes, and renders. Offline, no ML weights. (EV-005, DD-005) | "render layer", "video side" |
| **Learning layer** | The knowledge half: stdlib-only code for memory, recommendation, telemetry, evaluation. (EV-005) | "AI layer", "brain" (informal only) |
| **Memory** | The persistent project knowledge store under `memory/` (`database.json` + schemas + telemetry). The two layers join only here. (EV-005, EV-013) | "the DB" (use *Memory store* for the mechanism) |
| **Memory store (write path)** | The single hardened append mechanism (`safe_append`) — the only approved writer. (EV-017, DD-002) | "the writer", "save function" |
| **Memory record** | One JSON object = one project, matching schema v1 (+ optional v2). (EV-013, EV-014) | "entry", "row" |
| **Creative seed** | The recommendation output: hooks + specs + benchmark reused from the nearest-niche prior record. (EV-024, CAP-015) | "recommendation blob" |
| **Telemetry** | **Observed** platform metrics only; predicted values are rejected at capture. (EV-040, DD-003) | "metrics" (ambiguous), "stats" |
| **Calibrated benchmark** | The observed-vs-predicted calibration value intended to steer the next decision. (EV-025) | "the score" |
| **Learning loop** | The intended cycle telemetry→evaluate→calibrate→recommend→render→record. Currently **open**. (EV-024) | "feedback loop" (use the official term) |
| **Provenance** | The `loop_run_id`-bearing metadata that makes a record join-able to telemetry. (EV-026) | "tracking id" |

## Pipeline & workflow terms

| Term (official) | Definition |
|---|---|
| **Orchestrator** | The prompt (`skills/orchestrator/SKILL.md`) that coordinates the 15-step pipeline. It is a *document*, not a service. (EV-006, DD-007) |
| **Skill** | A prompt-defined role contract under `skills/` (orchestrator, storytelling, video-editor, qa-reviewer, retention-expert, social-media-manager). (EV-012) |
| **Workflow (pipeline)** | The 15 ordered steps Brief→…→Archive. (EV-009) |
| **WF-1** | Auto highlight detection + narrative episode extraction. (EV-011) |
| **WF-2** | Auto short generation + music montage. (EV-011) |
| **WF-3** | Observed telemetry capture (the measurement arm, not synthesis). (EV-011) |
| **EDL** | Edit Decision List — the structured timeline that produces a render. (EV-054) |
| **Hook** | The first 1–2 seconds engineered to stop the scroll. (EV-003) |
| **Highlight candidate** | A signal-grounded ("loud + high motion") moment proposed by WF-1. (EV-020) |
| **Episode** | A buildup→climax→resolution narrative unit from WF-1. (EV-021) |

## Integration & infrastructure terms

| Term (official) | Definition |
|---|---|
| **video-use engine** | The conversation-driven render/grade/transcribe engine at `integrations/video-use/`. Present & runnable in HEAD. (EV-018, CAP-020) |
| **MCP surface** | The 11-tool FastMCP server (`scos_video_mcp.py`) exposing ffmpeg operations. (EV-019) |
| **Event spine** | The append-only JSONL audit log of loop events (`events.jsonl`). (EV-021/CAP-021) |
| **EKB** | Engineering Knowledge Base — the `_knowledge/` registers + glossary connecting layers. (`EKB_MANIFEST.md`) |
| **Evidence (EV)** | One atomic, repository-verifiable fact, ID `EV-xxx`. (`EVIDENCE_REGISTER.md`) |
| **Decision (DD)** | One recorded design/governance decision, ID `DD-xxx`. (`DECISION_REGISTER.md`) |
| **Capability (CAP)** | One distinct system capability, ID `CAP-xxx`. (`CAPABILITY_INVENTORY.md`) |

## Governance & lineage terms

| Term (official) | Definition |
|---|---|
| **Repository truth** | The principle that running code/tests/committed data in **HEAD** outranks any document. (DD-010) |
| **Lineage** | A distinct commit ancestry. **HEAD lineage** = current checkout `6bec9c4`; **h1-foundation lineage** = the audited, unmerged 24-commit history. (EV-032) |
| **Lineage-B module** | A module whose source exists only in unmerged history (orphaned `.pyc` in HEAD). (EV-033, DD-009) |
| **Additive discipline** | Never edit a core file in place; extend additively. (EV-038, DD-001) |
| **Maturity level (L0–L5)** | The single capability-readiness scale. (`MATURITY_MODEL.md`, DD-012) |
| **Provisional maturity** | A capability's L-level assessed as-of-HEAD before full registry attribution. (`CAPABILITY_INVENTORY.md`) |

**Total: 40 canonical terms.** No synonyms left undefined; each term has exactly one
definition. Conflicts, if found later, resolve here (single source). ✓
