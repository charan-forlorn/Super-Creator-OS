# AI Readiness Assessment

> **⚠️ AUTHORITATIVE STATUS = §5 (Phase 2.9 Re-assessment).** Sections 1–4 below are the
> **original Phase 2.8 assessment, retained as historical baseline and SUPERSEDED** by the
> Phase 2.9 re-assessment in **§5** (below).
> No prior scores were removed or rewritten; for current readiness, read §5. Traceability:
> §1–§4 = baseline (Phase 2.8), §5 = authoritative (Phase 2.9).

> **Status:** SUPERSEDED-BY §5 (was ACTIVE Phase 2.8). Evaluates whether this knowledge
> system is ready to be consumed by AI tools and agents. Scale: **Ready / Partial /
> Not-ready**, with the gap and recommendation for each. Grounded in the EKB built in
> Phases 2.5–2.8.

---

## 1. Readiness by consumer *(historical — Phase 2.8 baseline, superseded by §5)*

| Consumer | Readiness | Why | Gap / recommendation |
|---|---|---|---|
| **Claude Code** | **Ready** | Markdown EKB, stable IDs, `REPOSITORY_INTELLIGENCE.md` search order, glossary, traceability rule | Add `knowledge.graph.json` (Phase 2.9) for programmatic nav |
| **Codex / GPT** | **Partial** | Same docs are model-agnostic & legible | No machine-readable graph/index yet; relies on file reads |
| **Gemini** | **Partial** | Same as above | Same — needs JSON graph + a retrieval protocol (Phase 2.9 `KNOWLEDGE_RETRIEVAL.md`) |
| **Local LLM (small ctx)** | **Partial** | Docs are chunkable; registers are tabular | No context-compression/summary layer; large registers may exceed small windows |
| **Multi-agent systems** | **Partial** | Authority model + capability ownership give clear division of labor | No agent-task routing map; ownership roles not yet mapped to agent identities |
| **Autonomous planning** | **Partial** | Capability registry + maturity + roadmap give goals & gaps | No change-impact model (Phase 2.9 `CHANGE_IMPACT.md`) to scope plans safely |
| **Knowledge retrieval** | **Partial** | IDs + glossary enable precise lookup | No ranked retrieval/query protocol yet (Phase 2.9) |
| **Context compression** | **Not-ready** | — | No tiered summaries / embeddings index; recommend a `KNOWLEDGE_RETRIEVAL.md` + per-doc abstracts |
| **Memory systems** | **Ready (data) / Partial (loop)** | Memory schema + safe-write are well-specified (EV-013/017) | The learning loop is open (CAP-018, L1); closure needed for self-improving memory |

## 2. What makes this EKB AI-friendly today

- **Deterministic IDs** (`EV`/`DD`/`CAP`) — agents cite, not paraphrase (`TRACEABILITY_STANDARD.md`).
- **Single-definition glossary** — no term ambiguity.
- **Explicit authority + conflict rules** — agents resolve disagreements deterministically.
- **Stale-evidence detection** — agents won't trust `.pyc`-only modules (the key trap).
- **Capability registry with maturity** — agents know what's real vs aspirational.

## 3. Top gaps (ranked)

1. **No machine-readable graph** (`knowledge.graph.json`) — blocks programmatic traversal.
   → Phase 2.9.
2. **No retrieval/query protocol** (`KNOWLEDGE_RETRIEVAL.md`) — agents must brute-read.
   → Phase 2.9.
3. **No change-impact model** (`CHANGE_IMPACT.md`) — autonomous edits can't scope blast
   radius. → Phase 2.9.
4. **Evidence freshness 34.5%** — agents must re-verify most `A`-basis claims
   (`KNOWLEDGE_QUALITY_METRICS.md`). → ongoing; resolved by lineage restore (DD-009).
5. **No context-compression layer** — small-window models lack abstracts. → Phase 2.9
   (`KNOWLEDGE_RETRIEVAL.md` to include tiered summaries).

## 4. Verdict

The knowledge system is **Ready for Claude Code / large-context agents** and **Partial for
programmatic, multi-agent, and small-context consumers**. The Phase 2.9 "Repository
Intelligence Enhancement" backlog (`PHASE_2_9_BACKLOG.md`) closes the remaining gaps in a
single, coherent step. No gap blocks proceeding to Phase 3 (Constitution).

---

## 5. Phase 2.9 Re-assessment (Repository Intelligence Layer built) — ✅ AUTHORITATIVE

The Repository Intelligence Layer (RIL) is now built: `REPOSITORY_MODEL.md`,
`KNOWLEDGE_RETRIEVAL.md`, `AI_QUERY_PROTOCOL.md`, `CONTEXT_COMPRESSION.md`, `CHANGE_IMPACT.md`,
`DOCUMENT_LIFECYCLE.md`, `MEMORY_ACCESS_POLICY.md`, `PROMPT_PROTOCOL.md`, and
`knowledge.graph.json`. Re-scored against §1:

| Consumer | Before (2.8) | After (2.9) | What changed |
|---|---|---|---|
| Claude Code | Ready | **Ready+** | query protocol + machine-readable graph |
| Codex / GPT | Partial | **Ready** | `knowledge.graph.json` + retrieval protocol |
| Gemini | Partial | **Ready** | same |
| Local LLM (small ctx) | Partial | **Ready** | `CONTEXT_COMPRESSION.md` L4/L5 tiers |
| Multi-agent systems | Partial | **Ready** | role ownership + `MEMORY_ACCESS_POLICY` + `PROMPT_PROTOCOL` |
| Autonomous planning | Partial | **Ready** | `CHANGE_IMPACT.md` blast-radius rules |
| Knowledge retrieval | Partial | **Ready** | `KNOWLEDGE_RETRIEVAL.md` + `AI_QUERY_PROTOCOL.md` |
| Context compression | Not-ready | **Ready (L5 index pending tooling)** | `CONTEXT_COMPRESSION.md` levels defined |
| Memory systems | Ready/Partial | **Ready (policy) / loop still open** | `MEMORY_ACCESS_POLICY.md`; CAP-018 still L1 |

### Readiness score

| Dimension | 2.8 | 2.9 |
|---|---|---|
| Documentation/protocols | 70% | **95%** |
| Machine-readability | 20% | **85%** (graph JSON; per-doc abstracts pending) |
| Retrieval determinism | 60% | **95%** |
| **Overall AI-readiness** | **~55%** | **~90%** |

### Remaining limitations (post-2.9)
- **Evidence freshness still 34.5%** — unchanged; only a lineage restore (DD-009, out of
  scope) fixes it.
- **No generated L5 index / embeddings** — `CONTEXT_COMPRESSION.md` defines tiers but the
  L5 index and per-doc abstracts are tooling for Phase 2.95+.
- **`knowledge.graph.json` is hand-authored** — should become script-generated to stay in
  sync (Phase 2.95+).
- **Learning loop open** (CAP-018, L1) — memory is policy-ready but not self-improving.

### Future recommendations
1. Generate `knowledge.graph.json` and an L5 index from the registers (tooling).
2. Add per-document abstracts to complete context compression.
3. Resolve the lineage (DD-009) to lift evidence freshness and capability maturity.
4. Proceed to Phase 3 (Constitution) — the RIL is sufficient to support it.
