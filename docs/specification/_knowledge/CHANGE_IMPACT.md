# Change Impact Model

> **Status:** ACTIVE (Phase 2.9.5). Given a change to a subsystem/module/doc, determine the
> blast radius: what is upstream, downstream, what breaks, how to migrate, and the risk.
> Enables safe (eventually autonomous) edits. **Describes impact; performs no change**
> (non-destructive). Cites `EV`/`DD`/`CAP`.

---

## 1. How to run an impact analysis

```
1. Identify the change target: a CAP / module / document / EV / DD.
2. Upstream  = what the target depends on   (CAPABILITY_REGISTRY "Depends on" + REPOSITORY_MODEL deps)
3. Downstream= what depends on the target   (CAPABILITY_REGISTRY "Consumed by" + reverse deps)
4. Impact scope = union(upstream blockers, downstream consumers, docs citing its EV/DD/CAP)
5. Breaking? = does it change a frozen contract (v1 schema EV-013/DD-004) or the write path (DD-002)?
6. Migration = additive path (DD-001) or, if unavoidable, a reviewed migration note
7. Risk = f(breaking, maturity gap, evidence freshness)
```

Docs impacted = `grep` the target's `EV`/`DD`/`CAP` IDs across `docs/specification/**`
(the `knowledge.graph.json` edges make this programmatic).

## 2. Per-subsystem impact table

| Subsystem | Upstream deps | Downstream consumers | Breaking risk | Migration | Risk |
|---|---|---|---|---|---|
| **Memory store** (CAP-014) | validators | recall (CAP-015), telemetry (CAP-016), all writers | **HIGH** — frozen v1 contract (DD-004), single write path (DD-002) | additive fields only (DD-001); never edit `safe_append` semantics | **HIGH** |
| **Memory schema** (EV-013/014) | — | every learning module + orchestrator | HIGH if v1 changed; LOW if v2 additive | add optional v2/v3 fields only | HIGH/LOW |
| **Learning loop** (CAP-018) | recommend (CAP-015), evaluator (CAP-017) | next recommendation | MEDIUM — wiring + provenance (EV-025/026) | add `calibrated_benchmark` consumer + stamp provenance | MEDIUM |
| **WF-1 highlight** (CAP-003) | numpy, assets (CAP-002) | narrative (CAP-004), shortgen (CAP-007) | LOW (additive detector) | pluggable `VisualEventDetector` (EV-023) | MEDIUM |
| **WF-2 shortgen** (CAP-007/008) | WF-1, EDL (CAP-006) | export (CAP-013), memory | MEDIUM — font/encode portability | OS-aware fonts; single-pass | MEDIUM |
| **MCP surface** (CAP-019) | mcp, ffmpeg | external clients | MEDIUM — `eval` (EV-046), no allow-list (EV-048) | replace `eval` with fraction parse; add allow-list if remoted | MEDIUM |
| **video-use engine** (CAP-020) | numpy, ffmpeg | grading/captions/MCP | LOW — present & runnable | add tests (no behavior change) | LOW |
| **Skills/prompts** (CAP-005/006/011/012/013/023) | orchestrator | pipeline | LOW — prompt edits | follow `PROMPT_PROTOCOL.md` | LOW |
| **EKB docs** | registers | all specs/agents | LOW — additive | append-only IDs (`TRACEABILITY_STANDARD`) | LOW |

## 3. Worked example — "Restore the learning spine into HEAD" (DD-009)

- **Target:** lineage-B modules → HEAD as `.py` (EV-033/034).
- **Upstream:** committed dependency manifest (EV-031 missing) + CPython 3.11 runtime
  (EV-030 satisfied).
- **Downstream / impact scope:** raises maturity of CAP-003/004/007/008/014/016/017/019/
  021/022 from **L2 → their `[hist:…]`** levels (`MATURITY_MODEL.md`); flips ~36 `A`-basis
  EVs from stale-risk to live-verifiable; updates `REPOSITORY_MODEL.md` §2 presence map;
  may close CAP-018.
- **Breaking?** No — additive (restores absent source); v1 contract untouched (DD-004).
- **Migration:** merge/restore source, add root `requirements.txt`, run smoke render + first
  runtime test, re-verify EVs.
- **Risk:** MEDIUM (large surface, but additive and well-evidenced). This is the project's
  highest-leverage change — but **out of scope here** (hard rule: do not resolve lineage).

## 4. Risk scoring rubric

| Factor | LOW | MEDIUM | HIGH |
|---|---|---|---|
| Contract impact | none | optional/additive | frozen contract (DD-004) or write path (DD-002) |
| Maturity gap | ≤1 level | 2 levels | 3+ levels / L1 loop |
| Evidence freshness | HIGH/`V` | mixed | mostly `A` stale-risk |
| Reversibility | trivial | additive note | irreversible |

Final risk = the **highest** factor present.
