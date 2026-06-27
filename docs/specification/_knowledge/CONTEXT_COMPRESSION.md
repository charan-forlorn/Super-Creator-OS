# Context Compression Layer

> **Status:** ACTIVE (Phase 2.9.4). Tiered context levels so agents load only as much as a
> task needs — protecting context windows and enabling small/local models. Pairs with
> `KNOWLEDGE_RETRIEVAL.md`. Token budgets are **rough order-of-magnitude** guides, not
> guarantees.

---

## 1. The levels (most detail → most compressed)

| Level | Name | What it is | Source | Rough tokens | Use when |
|---|---|---|---|---|---|
| **L0** | Repository | Raw source/data files | `integrations/**`, `memory/**` | 10k–100k+ | Verifying a path, reading actual code (last resort) |
| **L1** | Knowledge | Full EKB docs | `_knowledge/*.md`, `_evidence/*` | 2k–6k each | Deep reasoning about one area |
| **L2** | Capability | One `CAP` registry row + its `EV`/`DD` | `CAPABILITY_REGISTRY.md` | 100–300 | "What is X, is it real, who owns it" |
| **L3** | Decision | One `DD` + cited `EV` | `DECISION_REGISTER.md` | 50–150 | "Why is it this way / may I change it" |
| **L4** | Summary | Per-doc abstract / section map | manifests + summaries | 30–80 | Orienting; choosing where to descend |
| **L5** | Token-Optimized | IDs + one-line facts only | registers' ID columns | 5–20 | Tight budgets; multi-hop planning; small LLMs |

## 2. When to use each level

- **Start at L4** (summaries) to orient, then **descend only as far as the question needs.**
- **L5** for autonomous planners doing many lookups (carry IDs, expand on demand).
- **L2/L3** for most single-capability or single-decision questions — usually sufficient.
- **L1** only when composing a spec or reasoning across a whole subsystem.
- **L0** only to *verify* a fact already located via L1–L3 (per `AI_QUERY_PROTOCOL.md` step 6);
  never to discover facts.

## 3. Retrieval strategy (progressive disclosure)

```
need = classify(question)            # AI_QUERY_PROTOCOL step 1
ctx  = load(L4 summaries)            # cheap orientation
while not answerable(ctx) and level > L0:
    ctx += descend_one_level(toward the cited EV/DD/CAP)
answer using the shallowest sufficient level
```

Prefer **breadth at L4/L5** (scan many items cheaply) before **depth at L1/L0** (expensive).

## 4. Compression mapping to existing artifacts

| Level | Concretely load |
|---|---|
| L5 | ID columns of `EVIDENCE_REGISTER`/`DECISION_REGISTER`/`CAPABILITY_INVENTORY`; `knowledge.graph.json` node ids |
| L4 | `EKB_MANIFEST.md`, the section maps (e.g. `EVIDENCE_LEDGER` annotation block), table headers |
| L3 | a single `DD` row + its `EV` |
| L2 | a single `CAP` registry row |
| L1 | the full target `.md` |
| L0 | the cited repository path |

## 5. Budget guidance

| Agent context | Strategy |
|---|---|
| Large (Claude Code, ≥100k) | L4 → L1 freely; load several docs |
| Medium (~32k) | L4 → L2/L3; avoid loading >2 full docs |
| Small / local (≤8k) | L5 + targeted L2/L3 only; never load L0 wholesale |

## 6. Notes & deferrals

- Per-doc **abstracts** and a generated **L5 index** would sharpen this further; recorded
  for Phase 2.95+ (the `KNOWLEDGE_RETRIEVAL`/graph tooling). For now, L4/L5 are assembled
  from existing tables and `knowledge.graph.json`.
- Compression never changes meaning: a compressed claim still carries its `EV`/`DD`/`CAP`
  citation (`TRACEABILITY_STANDARD.md`).
