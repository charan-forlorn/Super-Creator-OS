# Phase 2.9 — Repository Intelligence Enhancement (Backlog)

> **Status:** ✅ BUILT in Phase 2.9 (all five delivered, plus four additional artifacts the
> expanded Phase 2.9 task added). Originally recorded in Phase 2.8. Gaps closed are tracked
> in `AI_READINESS.md` §5 (re-assessment). This file is retained for history.
>
> **Delivery map (recorded → built):**
> - `REPOSITORY_MODEL.md` → ✅ `../_repository_model/REPOSITORY_MODEL.md`
> - `DOCUMENT_LIFECYCLE.md` → ✅ `DOCUMENT_LIFECYCLE.md`
> - `CHANGE_IMPACT.md` → ✅ `CHANGE_IMPACT.md`
> - `KNOWLEDGE_RETRIEVAL.md` → ✅ `KNOWLEDGE_RETRIEVAL.md`
> - `knowledge.graph.json` → ✅ `knowledge.graph.json`
> - **Added by the expanded 2.9 task:** `AI_QUERY_PROTOCOL.md`, `CONTEXT_COMPRESSION.md`,
>   `MEMORY_ACCESS_POLICY.md`, `PROMPT_PROTOCOL.md`.

---

## Deliverables

| # | Artifact | Purpose | Closes gap |
|---|---|---|---|
| 1 | **`REPOSITORY_MODEL.md`** | Formal model of the repo's physical + logical structure: directory taxonomy, the two **lineages** (HEAD vs unmerged `h1-foundation`), `.py`-vs-`.pyc` presence map, and module→owner mapping. Makes the lineage hazard (EV-032/033/034, DD-009) a first-class, queryable model. | AI_READINESS §3.4; surfaces the split-brain structurally |
| 2 | **`DOCUMENT_LIFECYCLE.md`** | The state machine every doc moves through — `PLACEHOLDER → DRAFT → RATIFIED → SUPERSEDED` — with who advances each transition, entry/exit criteria, and review cadence. Operationalizes the status fields already used across the EKB and `AUTHORITY_MODEL.md` §4. | governance completeness |
| 3 | **`CHANGE_IMPACT.md`** | Impact-analysis rules: given a change to a `CAP`/module/doc, deterministically list the affected `EV`/`DD`/`CAP` and downstream documents (blast-radius). Enables safe autonomous edits. | AI_READINESS §3.3 (autonomous planning) |
| 4 | **`KNOWLEDGE_RETRIEVAL.md`** | Retrieval/query protocol for agents over the EKB: how to find the right `EV`/`DD`/`CAP`/term efficiently, ranking heuristics, tiered summaries for **context compression**, and small-context fallbacks. | AI_READINESS §3.2, §3.5 (retrieval + compression) |
| 5 | **`knowledge.graph.json`** | Machine-readable serialization of `KNOWLEDGE_GRAPH.md` (nodes + typed edges as JSON) for programmatic consumption by agents/tools/visualizers. Schema to mirror the node/edge vocabulary in `KNOWLEDGE_GRAPH.md` §1–§5. | AI_READINESS §3.1 (machine-readable graph) |

## Sequencing & dependencies

- Build order: `REPOSITORY_MODEL` → `DOCUMENT_LIFECYCLE` → `CHANGE_IMPACT` →
  `KNOWLEDGE_RETRIEVAL` → `knowledge.graph.json` (the JSON last, so it serializes the final
  graph state).
- All five must comply with `TRACEABILITY_STANDARD.md` (cite `EV`/`DD`/`CAP`).
- `knowledge.graph.json` should be **generated**, ideally by a small script, so it stays in
  sync with `KNOWLEDGE_GRAPH.md` (candidate future capability).

## Acceptance criteria for Phase 2.9

- ✓ Lineage model in `REPOSITORY_MODEL.md` matches a live `git`/filesystem check.
- ✓ Every EKB doc carries a lifecycle state per `DOCUMENT_LIFECYCLE.md`.
- ✓ `CHANGE_IMPACT.md` can be applied to ≥1 worked example (e.g. "restore the learning
  spine" → list impacted `CAP`/`EV`/docs).
- ✓ `knowledge.graph.json` validates and round-trips with `KNOWLEDGE_GRAPH.md`.

**Do not begin Phase 2.9 until Phase 2.8 is approved and Phase 3 sequencing is confirmed
with the user.**
