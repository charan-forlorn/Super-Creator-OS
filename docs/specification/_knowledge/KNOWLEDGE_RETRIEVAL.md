# Knowledge Retrieval Protocol

> **Status:** ACTIVE (Phase 2.9.2). The **canonical** retrieval protocol for AI agents over
> the Engineering Knowledge Base. **Extends** (does not replace) `REPOSITORY_INTELLIGENCE.md`
> (Phase 2.8), which remains the agent-etiquette/stale-evidence reference. Governance:
> `AUTHORITY_MODEL.md`. Citation rules: `TRACEABILITY_STANDARD.md`.
>
> **Prime directive:** the **EKB is the primary knowledge source**; the repository is
> *verification storage*, consulted to confirm — never the first stop.

---

## 1. Required search order

> **Canonical (Phase 2.9):** this section is the **single authoritative retrieval order**
> for the whole knowledge system. It **supersedes** the earlier sequence in
> [`REPOSITORY_INTELLIGENCE.md`](REPOSITORY_INTELLIGENCE.md) §1 (retained there for history).


```
1. Authority      → AUTHORITY_MODEL.md         (which layer/source is allowed to answer this)
2. Evidence       → EVIDENCE_REGISTER.md (EV)  (atomic facts)
3. Decision       → DECISION_REGISTER.md (DD)  (why it is so)
4. Capability     → CAPABILITY_REGISTRY.md (CAP) (what exists + maturity + owner)
5. Repository     → integrations/**, memory/** (verify the cited paths ONLY)
6. Historical     → project_audit/*, EVIDENCE_LEDGER §0 (audit/lineage context)
7. External       → outside sources (last resort; offline-first DD-006)
```

Stop at the earliest level that fully answers the question. Descend only to fill a gap.
**Repository (5) is entered only to verify an already-found EV path**, never to discover
facts from scratch.

## 2. Retrieval priority

| Priority | Prefer | Over |
|---|---|---|
| 1 | Higher authority layer (for *intent*) | lower layer |
| 2 | HIGH/`V` evidence (for *current facts*) | MED/`A` evidence |
| 3 | HEAD facts | unmerged-lineage facts |
| 4 | Capability registry maturity | raw prose impressions |
| 5 | Most recently verified | older verification |

## 3. Confidence scoring (report with every answer)

| Inputs used | Reported confidence |
|---|---|
| HIGH/`V` EV, path confirmed in HEAD | **Confirmed** |
| MED/`A` EV, not re-verified | **Likely (audit-sourced — re-verify)** |
| capability `[hist:…]` / `.pyc`-only path | **Not present in current checkout** |
| no citation found | **Unverified** |

Confidence of an answer = the **weakest** evidence it relies on (`TRACEABILITY_STANDARD.md` §4).

## 4. Conflict resolution

Apply `TRACEABILITY_STANDARD.md` §5 / `REPOSITORY_INTELLIGENCE.md` §5:
1. Live `V` beats `A` for current facts. 2. HEAD beats unmerged lineage. 3. Higher authority
beats lower for intent. 4. Tie → most recently verified; **log which evidence won and why**.

## 5. Stale-evidence handling

- Any `A`-basis EV about the learning spine / WF / MCP / `render_to_memory` is
  **stale-risk** (EV-033) → must be re-verified against HEAD before use.
- An EV whose source file changed after its verification date is **stale** → re-verify.
- If re-verification is impossible in-session → downgrade to "per audit/history (unverified
  in HEAD)".

## 6. Fallback behavior (when the EKB cannot answer)

1. Widen within the EKB (try a sibling register / the glossary / the graph).
2. Drop to Repository (level 5) **only to verify**, and if a new fact is discovered there,
   **propose a new `EV`** (append-only) rather than asserting it loosely.
3. If still unanswered → respond **"Not enough evidence."** (project rule) and state what
   would resolve it. Never fabricate.

## 7. Worked retrieval (example)

Q: *"Is the memory write-path production-ready?"*
- (1) Authority: this is a *current-state* question → Implementation truth, mediated by the
  capability registry.
- (2–4) Evidence EV-017 (hardened) + Decision DD-002 (single path) + Capability CAP-014 →
  maturity **L2 as-of-HEAD** with `[hist:L5]`.
- (5) Repository: confirm `integrities/learning/memory_writer.py` is **`.pyc`-only** (EV-033).
- Answer: *"No — production-grade on the unmerged lineage (L5 there), but **L2 in HEAD**
  because its source isn't checked out (EV-033/DD-009). Confidence: Confirmed."* Repository
  was used last, only to confirm. ✓
